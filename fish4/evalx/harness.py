"""Paired-deal evaluation harness (v0.4).

WHAT IT KEEPS FROM v0.3 (``fish/eval/tournament.py``)
-----------------------------------------------------
The pairing guarantee, unchanged and re-verified by test: every deal is
played twice with the teams swapped, on the SAME shuffled deck, the SAME
starting seat, and the SAME agent RNG seed. Only the policy-to-seat
assignment differs, so the per-deal differential is a paired observation and
deal luck cancels inside it. With ``seat_offsets=(0,)`` this harness
reproduces ``play_matchup`` differential-for-differential (pinned by
``tests4/test_evalx.py::test_matches_v03_tournament_exactly``), so v0.3
numbers remain comparable.

WHAT IT ADDS, AND WHY
---------------------
1. ANTITHETIC SEAT ROTATION (optional). The same deal can additionally be
   replayed from several rotated starting seats, and the deal's statistic
   becomes the mean over those seats. That is guaranteed to reduce variance
   *per deal*; the question nobody asked in v0.3 is whether it reduces
   variance *per unit of compute*, since R seats cost R times as many games.
   Averaging R correlated replicates gives

       Var(deal mean) = sigma^2 * (1 + (R-1) * rho) / R

   so against the alternative of simply playing R times as many independent
   deals the efficiency is ``1 / (1 + (R-1) rho)``: rotation wins only when
   the intra-deal correlation ``rho`` is NEGATIVE. ``VarianceReport``
   estimates rho and reports that ratio with a bootstrap interval instead of
   asserting that the technique works.

   MEASURED (tuned w_turn=0.6,w_scarce=0.2 vs probabilistic, 54-card deck,
   120 deals per spacing, ``results/v04_eval_calibration.json``): IT DOES NOT
   PAY. Offsets (0,2,4) give rho = -0.027 and a compute-matched efficiency of
   1.056 with a 95% bootstrap interval of [0.87, 1.31]; offsets (0,3) give
   rho = +0.149 and 0.871 [0.75, 1.05]. Neither interval excludes 1, and the
   two point estimates straddle it. Rotation does cut per-deal variance
   (x0.32 at R=3, almost the x1/3 of independent replicates) but that is
   arithmetic, not a discovery: it buys nothing you would not get by playing
   three times as many independent deals. It is OFF by default and the extra
   layer is kept only because it makes each pair a lower-variance observation,
   which occasionally matters when the number of DEALS, not games, is the
   scarce resource.

2. TIMEOUTS ARE NEVER SILENT. A deal in which any of its ``2*R`` games hits
   the action cap is dropped whole, because a half-played pair is not a
   paired observation and counting it biases the differential toward the
   side that finished. v0.3 already dropped them but buried the count at the
   end of a summary line; here the drop count and drop rate lead every
   summary, are stored in the result, and crossing ``max_drop_rate`` raises.

3. RESUMABLE, APPEND-ONLY RESULT LOG. Long runs get interrupted. Each deal
   is written to a JSONL file as it completes, prefixed by a header holding
   the configuration hash. Re-running with the same config skips the deals
   already present; re-running with a DIFFERENT config refuses to append
   rather than silently mixing two experiments into one file.

4. PER-PAIR DIFFERENTIALS ARE FIRST-CLASS. ``PairedResult.diffs`` is the
   vector downstream code (the sequential tests, the SD calibration) needs;
   v0.3 dropped it from ``to_dict`` and it could not be recovered from a
   saved result.

Worker count is capped at ``MAX_WORKERS`` (4) because this machine has 8
cores and other jobs run alongside; requesting more is clamped and warned
about rather than honored.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from multiprocessing import Pool
from pathlib import Path
from typing import Optional

from fish.agents import AGENT_REGISTRY
from fish.cards import deck_size, num_half_suits
from fish.rules import RuleConfig
from fish.runner import GameTimeout, play_game

AgentSpec = tuple[str, dict]

#: Hard cap on worker processes: 8 cores total, other jobs running.
MAX_WORKERS = 4

#: Result-log format. Bump when the record shape changes.
LOG_SCHEMA = "evalx-pairs/1"


class ConfigMismatch(Exception):
    """A resume was attempted against a log written for a different config."""


class TooManyDrops(Exception):
    """More pairs were dropped for timeouts than the caller declared tolerable."""


def make_agent(spec: AgentSpec):
    name, kwargs = spec
    return AGENT_REGISTRY[name](**dict(kwargs))


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def _canonical(obj):
    """Sort dict keys and normalize tuples so the config hash is stable
    across runs, Python versions and JSON round-trips."""
    if isinstance(obj, dict):
        return {k: _canonical(obj[k]) for k in sorted(obj)}
    if isinstance(obj, (list, tuple)):
        return [_canonical(v) for v in obj]
    return obj


@dataclass(frozen=True)
class HarnessConfig:
    """Everything that determines the numbers a run produces.

    Two runs whose ``fingerprint()`` agree must produce identical per-pair
    differentials; that property is what makes the resume path safe, and it
    is asserted by test.
    """

    spec_x: AgentSpec
    spec_y: AgentSpec
    n_pairs: int
    rules: dict = field(default_factory=lambda: RuleConfig().to_dict())
    #: Starting-seat offsets replayed for each deal. ``(0,)`` = v0.3 behavior.
    #: Evenly spaced offsets are the natural antithetic choice: with 6 seats,
    #: ``(0, 3)`` puts the deal's first mover on opposite sides of the table.
    seat_offsets: tuple = (0,)
    base_seed: int = 0
    agent_seed_base: int = 0
    max_actions: int = 20000
    n_workers: int = MAX_WORKERS
    #: Fraction of pairs that may be dropped for timeouts before we refuse
    #: to report a differential at all.
    max_drop_rate: float = 0.05

    def __post_init__(self) -> None:
        if not self.seat_offsets:
            raise ValueError("seat_offsets must contain at least one offset")
        if len(set(self.seat_offsets)) != len(self.seat_offsets):
            raise ValueError(f"duplicate seat offsets: {self.seat_offsets}")
        if any(not (0 <= o < 6) for o in self.seat_offsets):
            raise ValueError(f"seat offsets must be in 0..5: {self.seat_offsets}")
        if self.n_workers > MAX_WORKERS:
            print(f"[evalx] n_workers={self.n_workers} clamped to {MAX_WORKERS} "
                  f"(machine budget)", file=sys.stderr)
            object.__setattr__(self, "n_workers", MAX_WORKERS)
        if self.n_workers < 1:
            object.__setattr__(self, "n_workers", 1)
        object.__setattr__(self, "seat_offsets", tuple(self.seat_offsets))
        object.__setattr__(self, "spec_x", (self.spec_x[0], dict(self.spec_x[1])))
        object.__setattr__(self, "spec_y", (self.spec_y[0], dict(self.spec_y[1])))

    # -- derived ------------------------------------------------------------

    @property
    def n_seats(self) -> int:
        return len(self.seat_offsets)

    @property
    def games_per_pair(self) -> int:
        return 2 * self.n_seats

    @property
    def diff_bound(self) -> float:
        """Largest magnitude a per-pair differential can take.

        A pair sums the two swapped games, each of which can differ by at
        most the number of half-suits. The sequential tests need this: their
        guarantees are stated for bounded observations.
        """
        return 2.0 * num_half_suits(self.rules.get("variant", "54"))

    def to_dict(self) -> dict:
        return {
            "spec_x": [self.spec_x[0], dict(self.spec_x[1])],
            "spec_y": [self.spec_y[0], dict(self.spec_y[1])],
            "n_pairs": self.n_pairs,
            "rules": dict(self.rules),
            "seat_offsets": list(self.seat_offsets),
            "base_seed": self.base_seed,
            "agent_seed_base": self.agent_seed_base,
            "max_actions": self.max_actions,
            "n_workers": self.n_workers,
            "max_drop_rate": self.max_drop_rate,
        }

    def fingerprint(self) -> str:
        """Hash of the fields that change the NUMBERS.

        ``n_pairs``, ``n_workers`` and ``max_drop_rate`` are excluded on
        purpose: extending a run from 200 to 400 pairs, or resuming it on a
        machine with a different core budget, must still be able to reuse the
        pairs already played.
        """
        ident = self.to_dict()
        for k in ("n_pairs", "n_workers", "max_drop_rate"):
            ident.pop(k)
        blob = json.dumps(_canonical(ident), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Per-deal work
# ---------------------------------------------------------------------------

@dataclass
class PairRecord:
    """One deal, played at every seat offset with the teams swapped."""

    index: int
    deal_seed: int
    base_seat: int
    agent_seed: int
    seat_diffs: list = field(default_factory=list)   # one entry per seat offset
    x_sets: int = 0
    y_sets: int = 0
    null_sets: int = 0
    actions: int = 0
    timeouts: int = 0
    complete: bool = True
    seconds: float = 0.0

    @property
    def diff(self) -> float:
        """The pair statistic: mean over seat offsets of the swapped-game
        differential. Identical in units to v0.3's per-deal differential, so
        rotated and unrotated runs are directly comparable."""
        if not self.seat_diffs:
            return 0.0
        return sum(self.seat_diffs) / len(self.seat_diffs)

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["diff"] = self.diff
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "PairRecord":
        return cls(index=d["index"], deal_seed=d["deal_seed"],
                   base_seat=d["base_seat"], agent_seed=d["agent_seed"],
                   seat_diffs=list(d["seat_diffs"]), x_sets=d["x_sets"],
                   y_sets=d["y_sets"], null_sets=d["null_sets"],
                   actions=d["actions"], timeouts=d["timeouts"],
                   complete=d["complete"], seconds=d.get("seconds", 0.0))


def _agent_seed_for(deal_agent_seed: int, seat_index: int) -> int:
    """Seat offset 0 keeps the deal's own agent seed, so a one-offset run is
    identical to v0.3. Further offsets derive from the AGENT seed only, never
    from the deal seed: agent randomness must carry no information about the
    hidden layout (see the integrity note in ``fish/runner.py``)."""
    if seat_index == 0:
        return deal_agent_seed
    return random.Random(f"evalx-seat:{deal_agent_seed}:{seat_index}"
                         ).getrandbits(64)


def _play_pair(job) -> dict:
    """Worker entry point: one deal -> one PairRecord dict.

    Runs ``2 * len(seat_offsets)`` games. Any timeout marks the whole record
    incomplete; the caller drops it rather than keeping the half that
    finished.
    """
    (index, spec_x, spec_y, rules_dict, seat_offsets, deal_seed, base_seat,
     deal_agent_seed, max_actions) = job
    t0 = time.perf_counter()
    rng = random.Random(deal_seed)
    deck = list(range(deck_size(rules_dict.get("variant", "54"))))
    rng.shuffle(deck)

    rec = PairRecord(index=index, deal_seed=deal_seed, base_seat=base_seat,
                     agent_seed=deal_agent_seed)
    for j, off in enumerate(seat_offsets):
        seat = (base_seat + off) % 6
        rules = RuleConfig(**{**rules_dict, "starting_player": seat})
        agent_seed = _agent_seed_for(deal_agent_seed, j)
        seat_diff = 0
        for swap in (0, 1):
            agents = []
            for p in range(6):
                on_x = (p % 2 == 0) if swap == 0 else (p % 2 == 1)
                agents.append(make_agent(spec_x if on_x else spec_y))
            try:
                state = play_game(agents, rules, deck_order=deck,
                                  agent_seed=agent_seed,
                                  max_actions=max_actions)
            except GameTimeout:
                rec.timeouts += 1
                rec.complete = False
                continue
            a, b, nulls = state.scores()
            xs, ys = (a, b) if swap == 0 else (b, a)
            rec.x_sets += xs
            rec.y_sets += ys
            rec.null_sets += nulls
            rec.actions += len(state.history)
            seat_diff += xs - ys
        if rec.complete:
            rec.seat_diffs.append(seat_diff)
    if not rec.complete:
        # Partial evidence from a dropped pair is not evidence; clear it so a
        # later reader cannot mistake it for a usable observation.
        rec.seat_diffs = []
    rec.seconds = time.perf_counter() - t0
    return rec.to_dict()


# ---------------------------------------------------------------------------
# Variance accounting for seat rotation
# ---------------------------------------------------------------------------

@dataclass
class VarianceReport:
    """Did antithetic seat rotation actually buy anything?

    ``per_deal_ratio`` is the easy, always-favorable comparison (averaging R
    replicates cannot increase per-deal variance). ``compute_matched_ratio``
    is the one that decides policy: it compares R seats on one deal against R
    independent deals at the same number of games. Values > 1 mean rotation
    wins, < 1 mean it loses.
    """

    n_seats: int
    n_deals: int
    sd_single_seat: float
    sd_deal_mean: float
    intra_deal_corr: float
    per_deal_ratio: float
    compute_matched_ratio: float
    compute_matched_ci: tuple = (float("nan"), float("nan"))

    @property
    def helped(self) -> Optional[bool]:
        """True/False only when the bootstrap interval is decisive."""
        lo, hi = self.compute_matched_ci
        if lo != lo:                       # NaN
            return None
        if lo > 1.0:
            return True
        if hi < 1.0:
            return False
        return None

    def summary(self) -> str:
        if self.n_seats == 1:
            return "seat rotation: not used (1 seat per deal)"
        verdict = {True: "HELPED", False: "DID NOT HELP", None: "UNDECIDED"}[
            self.helped]
        lo, hi = self.compute_matched_ci
        return (f"seat rotation R={self.n_seats}: sd/seat {self.sd_single_seat:.3f} "
                f"-> sd/deal {self.sd_deal_mean:.3f} "
                f"(per-deal variance x{self.per_deal_ratio:.3f}); "
                f"intra-deal corr {self.intra_deal_corr:+.3f}; "
                f"compute-matched efficiency {self.compute_matched_ratio:.3f} "
                f"[{lo:.3f},{hi:.3f}] -> {verdict}")

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["compute_matched_ci"] = list(self.compute_matched_ci)
        d["helped"] = self.helped
        return d


def _rotation_stats(rows: list, r: int) -> tuple:
    flat = [v for row in rows for v in row]
    v_single = statistics.variance(flat)
    v_deal = statistics.variance([sum(row) / r for row in rows])
    if v_single <= 0 or v_deal <= 0:
        return v_single, v_deal, 0.0, 1.0, 1.0
    rho = (r * v_deal / v_single - 1.0) / (r - 1)
    eff = (v_single / r) / v_deal
    return v_single, v_deal, rho, v_deal / v_single, eff


def _variance_report(seat_matrix: list, n_boot: int = 2000,
                     seed: int = 20240404) -> VarianceReport:
    """``seat_matrix`` holds one list of per-seat differentials per deal.

    sigma^2_single is the marginal variance of a single-seat observation,
    sigma^2_deal the variance of the R-seat average. Solving
    ``sigma^2_deal = sigma^2 (1 + (R-1) rho) / R`` for rho gives the
    intra-deal correlation, and ``1/(1+(R-1)rho)`` is the compute-matched
    efficiency. The bootstrap resamples DEALS, which are the independent unit.
    """
    n = len(seat_matrix)
    r = len(seat_matrix[0]) if n else 1
    if n < 2 or r < 2:
        flat = [v for row in seat_matrix for v in row]
        sd = statistics.stdev(flat) if len(flat) > 1 else 0.0
        return VarianceReport(n_seats=r, n_deals=n, sd_single_seat=sd,
                              sd_deal_mean=sd, intra_deal_corr=0.0,
                              per_deal_ratio=1.0, compute_matched_ratio=1.0)

    v_single, v_deal, rho, per_deal, eff = _rotation_stats(seat_matrix, r)

    rng = random.Random(seed)
    boots = []
    for _ in range(n_boot):
        sample = [seat_matrix[rng.randrange(n)] for _ in range(n)]
        try:
            boots.append(_rotation_stats(sample, r)[4])
        except statistics.StatisticsError:
            continue
    boots.sort()
    if boots:
        lo = boots[int(0.025 * len(boots))]
        hi = boots[min(len(boots) - 1, int(0.975 * len(boots)))]
    else:
        lo = hi = float("nan")

    return VarianceReport(
        n_seats=r, n_deals=n, sd_single_seat=math.sqrt(v_single),
        sd_deal_mean=math.sqrt(v_deal), intra_deal_corr=rho,
        per_deal_ratio=per_deal, compute_matched_ratio=eff,
        compute_matched_ci=(lo, hi))


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

def _t_critical(df: int, conf: float = 0.95) -> float:
    """Two-sided Student-t critical value, Cornish-Fisher expansion.

    Same routine as v0.3 (``fish/eval/tournament._t_critical``), duplicated
    rather than imported so this package does not depend on the module it is
    meant to supersede. Agreement with the original is asserted by test.
    """
    if df <= 0:
        return float("inf")
    z = statistics.NormalDist().inv_cdf(0.5 + conf / 2)
    g1 = (z ** 3 + z) / 4
    g2 = (5 * z ** 5 + 16 * z ** 3 + 3 * z) / 96
    g3 = (3 * z ** 7 + 19 * z ** 5 + 17 * z ** 3 - 15 * z) / 384
    return z + g1 / df + g2 / df ** 2 + g3 / df ** 3


@dataclass
class PairedResult:
    config: HarnessConfig
    records: list = field(default_factory=list)      # completed PairRecords
    dropped: list = field(default_factory=list)      # incomplete PairRecords
    wall_clock_s: float = 0.0
    log_path: Optional[str] = None
    reused_pairs: int = 0

    # -- basic accessors ----------------------------------------------------

    @property
    def diffs(self) -> list:
        """Per-pair set differentials in deal order: the vector every
        downstream test consumes."""
        return [r.diff for r in self.records]

    @property
    def n_pairs(self) -> int:
        return len(self.records)

    @property
    def dropped_pairs(self) -> int:
        return len(self.dropped)

    @property
    def timeouts(self) -> int:
        return sum(r.timeouts for r in self.dropped) + sum(
            r.timeouts for r in self.records)

    @property
    def attempted_pairs(self) -> int:
        return self.n_pairs + self.dropped_pairs

    @property
    def drop_rate(self) -> float:
        return self.dropped_pairs / max(1, self.attempted_pairs)

    @property
    def games_played(self) -> int:
        return self.attempted_pairs * self.config.games_per_pair

    @property
    def cpu_seconds_per_pair(self) -> float:
        """Mean single-process CPU time per pair, recorded by the worker.

        Survives a resume, unlike wall clock, because it is stored per record.
        """
        recs = self.records + self.dropped
        return (sum(r.seconds for r in recs) / len(recs)) if recs else 0.0

    @property
    def seconds_per_pair(self) -> float:
        """Wall clock per pair: the number that decides how many pairs an
        experiment can afford.

        Reused (resumed) pairs are excluded from the denominator because they
        cost nothing this run. When EVERY pair was reused there is no wall
        clock to divide, so we fall back to the recorded per-pair CPU time
        divided by the worker count - an estimate, and flagged as one by
        ``seconds_per_pair_is_estimated``.
        """
        fresh = self.attempted_pairs - self.reused_pairs
        if fresh <= 0 or self.wall_clock_s <= 0:
            return self.cpu_seconds_per_pair / max(1, self.config.n_workers)
        return self.wall_clock_s / fresh

    @property
    def seconds_per_pair_is_estimated(self) -> bool:
        fresh = self.attempted_pairs - self.reused_pairs
        return fresh <= 0 or self.wall_clock_s <= 0

    # -- statistics ---------------------------------------------------------

    def mean_diff(self) -> float:
        return statistics.fmean(self.diffs) if self.records else 0.0

    def sd_diff(self) -> float:
        """Per-pair standard deviation of the set differential. Every
        sample-size calculation in this project depends on this number."""
        d = self.diffs
        return statistics.stdev(d) if len(d) > 1 else 0.0

    def diff_mean_ci(self, conf: float = 0.95) -> tuple:
        n = self.n_pairs
        if n == 0:
            return (0.0, float("-inf"), float("inf"))
        m = self.mean_diff()
        if n < 2:
            return (m, float("-inf"), float("inf"))
        se = self.sd_diff() / math.sqrt(n)
        t = _t_critical(n - 1, conf)
        return (m, m - t * se, m + t * se)

    def pair_score(self) -> float:
        """X's paired score in [0,1], ties = 0.5 (the sign-only statistic)."""
        if not self.records:
            return 0.5
        w = sum(1 for d in self.diffs if d > 0)
        t = sum(1 for d in self.diffs if d == 0)
        return (w + 0.5 * t) / self.n_pairs

    def wilson_ci(self, z: float = 1.96) -> tuple:
        n = self.n_pairs
        if n == 0:
            return (0.0, 1.0)
        p = self.pair_score()
        denom = 1 + z * z / n
        centre = (p + z * z / (2 * n)) / denom
        half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
        return (max(0.0, centre - half), min(1.0, centre + half))

    def variance_report(self, n_boot: int = 2000) -> VarianceReport:
        matrix = [r.seat_diffs for r in self.records if r.seat_diffs]
        if not matrix:
            return VarianceReport(self.config.n_seats, 0, 0.0, 0.0, 0.0, 1.0, 1.0)
        return _variance_report(matrix, n_boot=n_boot)

    def min_detectable_effect(self, n_pairs: Optional[int] = None,
                              alpha: float = 0.05, power: float = 0.80) -> float:
        """Two-sided fixed-n MDE at the measured SD:
        ``delta = (z_{alpha/2} + z_beta) * sd / sqrt(n)``."""
        n = n_pairs or self.n_pairs
        if n < 1:
            return float("inf")
        nd = statistics.NormalDist()
        return (nd.inv_cdf(1 - alpha / 2) + nd.inv_cdf(power)) * \
            self.sd_diff() / math.sqrt(n)

    def pairs_needed(self, effect: float, alpha: float = 0.05,
                     power: float = 0.80) -> int:
        """Inverse of ``min_detectable_effect``: fixed-n pairs required."""
        if effect <= 0:
            return -1
        nd = statistics.NormalDist()
        za = nd.inv_cdf(1 - alpha / 2)
        zb = nd.inv_cdf(power)
        return int(math.ceil(((za + zb) * self.sd_diff() / effect) ** 2))

    # -- reporting ----------------------------------------------------------

    def summary(self) -> str:
        """Drop accounting comes FIRST, on purpose. In v0.3 it was the last
        field of a long line and was routinely skimmed past."""
        m, lo, hi = self.diff_mean_ci()
        wlo, whi = self.wilson_ci()
        head = (f"[{self.dropped_pairs} dropped / {self.attempted_pairs} "
                f"attempted = {self.drop_rate:.1%}] ")
        return (head +
                f"{self.config.spec_x[0]} vs {self.config.spec_y[0]}: "
                f"set diff {m:+.3f} [{lo:+.3f},{hi:+.3f}] "
                f"(sd {self.sd_diff():.3f} over {self.n_pairs} pairs), "
                f"pair score {self.pair_score():.3f} [{wlo:.3f},{whi:.3f}], "
                f"{self.config.games_per_pair} games/pair, "
                f"{self.seconds_per_pair:.2f}s/pair wall")

    def check_drops(self) -> None:
        """Raise unless the drop rate is inside the declared tolerance.

        Dropping is unbiased only if timing out is independent of who is
        winning, and it is not: stalls happen in positions where neither side
        can safely claim. So a high drop rate invalidates the differential
        rather than merely shrinking the sample.
        """
        if self.drop_rate > self.config.max_drop_rate:
            raise TooManyDrops(
                f"{self.dropped_pairs}/{self.attempted_pairs} pairs "
                f"({self.drop_rate:.1%}) dropped for timeouts, above the "
                f"declared tolerance {self.config.max_drop_rate:.1%}. Games "
                f"that finish are not a random subset of games, so the "
                f"surviving pairs are a biased subsample and no differential "
                f"is reported.")

    def to_dict(self) -> dict:
        m, lo, hi = self.diff_mean_ci()
        wlo, whi = self.wilson_ci()
        return {
            "config": self.config.to_dict(),
            "config_fingerprint": self.config.fingerprint(),
            "n_pairs": self.n_pairs,
            "dropped_pairs": self.dropped_pairs,
            "drop_rate": self.drop_rate,
            "timeouts": self.timeouts,
            "games_played": self.games_played,
            "mean_diff": m,
            "diff_ci95": [lo, hi],
            "sd_diff": self.sd_diff(),
            "pair_score": self.pair_score(),
            "pair_score_ci95": [wlo, whi],
            "x_sets": sum(r.x_sets for r in self.records),
            "y_sets": sum(r.y_sets for r in self.records),
            "null_sets": sum(r.null_sets for r in self.records),
            "wall_clock_s": self.wall_clock_s,
            "seconds_per_pair": self.seconds_per_pair,
            "seconds_per_pair_is_estimated": self.seconds_per_pair_is_estimated,
            "cpu_seconds_per_pair": self.cpu_seconds_per_pair,
            "reused_pairs": self.reused_pairs,
            "variance_report": self.variance_report().to_dict(),
            "log_path": self.log_path,
        }


# ---------------------------------------------------------------------------
# Append-only, resumable result log
# ---------------------------------------------------------------------------

def _write_line(path: Path, obj: dict) -> None:
    """One record, one write, fsynced.

    A single ``os.write`` to an O_APPEND handle is the closest thing to an
    atomic append available on both Windows and POSIX. Only the PARENT
    process ever writes this file, so a killed run can lose at most the line
    it was mid-write on, and that line is discarded by the JSON parse on
    resume (see ``load_log``).
    """
    blob = (json.dumps(obj, separators=(",", ":")) + "\n").encode("utf-8")
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try:
        os.write(fd, blob)
        os.fsync(fd)
    finally:
        os.close(fd)


def load_log(path) -> tuple:
    """Return ``(header, records)`` from a result log, tolerating a truncated
    final line left behind by an interrupted run."""
    p = Path(path)
    if not p.exists():
        return None, []
    header = None
    records = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            print(f"[evalx] discarding unparseable line in {p} "
                  f"(interrupted run?)", file=sys.stderr)
            continue
        if obj.get("_header"):
            header = obj
        else:
            records.append(PairRecord.from_dict(obj))
    return header, records


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------

def _jobs_for(cfg: HarnessConfig, skip: set) -> list:
    """Build the job list.

    Agent seeds come from a stream seeded only by ``agent_seed_base`` and
    consumed in deal order, so deal ``i`` always receives the same agent seed
    regardless of which subset is being (re)played. That is what makes a
    resumed run bit-identical to an uninterrupted one.
    """
    seed_rng = random.Random(cfg.agent_seed_base)
    jobs = []
    for i in range(cfg.n_pairs):
        agent_seed = seed_rng.getrandbits(64)
        if i in skip:
            continue
        jobs.append((i, cfg.spec_x, cfg.spec_y, dict(cfg.rules),
                     tuple(cfg.seat_offsets), cfg.base_seed + i, i % 6,
                     agent_seed, cfg.max_actions))
    return jobs


def run_paired(cfg: HarnessConfig, log_path=None, resume: bool = True,
               progress: bool = True, progress_every: float = 10.0,
               pool: Optional[Pool] = None) -> PairedResult:
    """Play ``cfg.n_pairs`` paired deals and return the result.

    ``log_path`` enables the resumable append-only log. With ``resume=True``
    (default) an existing log for the SAME configuration is reused and only
    the missing deals are played; a log for a different configuration raises
    ``ConfigMismatch`` rather than being appended to.
    """
    result = PairedResult(config=cfg,
                          log_path=str(log_path) if log_path else None)
    done: dict = {}

    if log_path is not None:
        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        header, existing = load_log(path)
        if header is not None and not resume:
            raise ConfigMismatch(
                f"{path} already exists and resume=False; refusing to append "
                f"to an existing log.")
        if header is not None:
            if header.get("config_fingerprint") != cfg.fingerprint():
                raise ConfigMismatch(
                    f"{path} was written for config "
                    f"{header.get('config_fingerprint')} but this run is "
                    f"{cfg.fingerprint()}. Refusing to mix two experiments in "
                    f"one log; use a different path or delete the old one.")
            for rec in existing:
                done[rec.index] = rec
        else:
            _write_line(path, {"_header": True, "schema": LOG_SCHEMA,
                               "config_fingerprint": cfg.fingerprint(),
                               "config": cfg.to_dict(),
                               "created": time.strftime("%Y-%m-%dT%H:%M:%S")})

    for i in sorted(done):
        if i < cfg.n_pairs:
            (result.records if done[i].complete else result.dropped).append(done[i])
    result.reused_pairs = len(result.records) + len(result.dropped)
    if result.reused_pairs and progress:
        print(f"[evalx] resuming: {result.reused_pairs} pairs already in "
              f"{log_path}", file=sys.stderr)

    jobs = _jobs_for(cfg, set(done))
    if not jobs:
        result.records.sort(key=lambda r: r.index)
        result.dropped.sort(key=lambda r: r.index)
        return result

    t0 = time.time()
    last = t0
    n_done = 0

    def absorb(d: dict) -> None:
        nonlocal n_done, last
        rec = PairRecord.from_dict(d)
        if log_path is not None:
            _write_line(Path(log_path), rec.to_dict())
        (result.records if rec.complete else result.dropped).append(rec)
        n_done += 1
        now = time.time()
        if progress and (now - last >= progress_every or n_done == len(jobs)):
            last = now
            rate = n_done / max(1e-9, now - t0)
            eta = (len(jobs) - n_done) / max(1e-9, rate)
            print(f"[evalx] {n_done}/{len(jobs)} pairs  {rate:.2f} pairs/s  "
                  f"eta {eta / 60:.1f} min  dropped {len(result.dropped)}",
                  file=sys.stderr, flush=True)

    if pool is not None:
        for d in pool.imap_unordered(_play_pair, jobs, chunksize=1):
            absorb(d)
    elif cfg.n_workers > 1:
        with Pool(cfg.n_workers) as p:
            for d in p.imap_unordered(_play_pair, jobs, chunksize=1):
                absorb(d)
    else:
        for j in jobs:
            absorb(_play_pair(j))

    result.wall_clock_s = time.time() - t0
    result.records.sort(key=lambda r: r.index)
    result.dropped.sort(key=lambda r: r.index)

    if result.dropped_pairs and progress:
        print(f"[evalx] WARNING: dropped {result.dropped_pairs} of "
              f"{result.attempted_pairs} pairs ({result.drop_rate:.1%}) "
              f"because a game hit the {cfg.max_actions}-action cap",
              file=sys.stderr)
    return result


__all__ = ["AgentSpec", "MAX_WORKERS", "ConfigMismatch", "TooManyDrops",
           "HarnessConfig", "PairRecord", "PairedResult", "VarianceReport",
           "run_paired", "load_log", "make_agent"]
