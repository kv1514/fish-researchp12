"""How good is the posterior, measured against the truth it is guessing at?

Every belief metric in v0.3 was indirect: sampler cost, agreement with an exact
endgame solver, or downstream win rate. None of them asked the direct question,
which in simulation we can simply answer, because the hidden hands are sitting
right there in the engine:

    given the public record, how much probability does the agent put on where
    the cards ACTUALLY are?

This script scores several inference configurations on exactly that, over real
positions from real games. The true state is used only to SCORE, never to act -
the same line the v0.3 value network was trained on.

Scores, computed over cards that are still genuinely uncertain (a card the
propagator has already pinned is scored perfectly by everything and would only
dilute the comparison):

* **NLL** - mean of -log P(true holder). The proper score; lower is better.
* **Brier** - mean squared error of the six-way distribution. Bounded, so it is
  robust to a single confident mistake, which NLL is not.
* **top-1** - how often the most likely holder is the real one.
* **calibration** - reliability of the stated probabilities in deciles.

Configurations compared:
  v03-N        v0.3's heuristic sampler with N draws (the incumbent)
  exact-free   the exact DP, ignoring the OR clauses
  sis-N        v0.4's unbiased importance sampler with N draws
  sis-N-gG     the same, with the opponent choice model at gamma = G
"""

from __future__ import annotations

import json
import math
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.beliefs import RESOLVED, BeliefState
from fish.cards import NUM_PLAYERS
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.posterior import Posterior
from fish4.registry4 import make_agent
from scripts4.resultfile import write as write_result

EPS = 1e-9


def v03_marginals(bel, rng, n_samples):
    """Marginals as v0.3 computes them: empirical over its own sampler."""
    M = np.zeros((bel.n, NUM_PLAYERS))
    for _ in range(n_samples):
        hands = bel.sample_current_hands(rng)
        for p in range(NUM_PLAYERS):
            h = hands[p]
            while h:
                low = h & -h
                M[low.bit_length() - 1, p] += 1
                h ^= low
    return M / max(1, n_samples)


def _sis(n, gamma=0.0, depth_mode="initial", count_mode="linear"):
    return lambda bel, rng, obs: Posterior(
        bel, rng, n_draws=n, mode="sample", obs=obs, gamma=gamma,
        depth_mode=depth_mode, count_mode=count_mode).marginals()


def _v03(n):
    return lambda bel, rng, obs: v03_marginals(bel, rng, n)


#: THE CONFIGURATION SET IS AN EXPLICIT SELECTOR, one entry per campaign.
#:
#: It was a single list edited in place across three campaigns, so the script
#: could only ever reproduce whichever campaign ran last: TWELVE of the
#: fourteen rows in `results/posterior_accuracy.json` -- the file that backs
#: this paper's central negative result, and the file
#: `scripts4/check_paper_numbers.py` watches -- had become unproducible by any
#: command in the repository, including `sis-512` at 1.3618, one of the two
#: numbers in the headline comparison. Found by an audit of the paper's
#: reproduction section.
#:
#: The sets are reconstructed from the row names in each results file, which
#: encode their own parameters. One row cannot come back and says so below.
CAMPAIGNS = {
    # results/posterior_accuracy.json -- the gamma sweep at two draw budgets.
    "gamma": [
        ("v03-512", _v03(512)), ("v03-96", _v03(96)), ("v03-32", _v03(32)),
        ("sis-512", _sis(512)),
        ("sis-512-g0.30", _sis(512, 0.30)),
        ("sis-512-g0.45", _sis(512, 0.45)),
        ("sis-512-g0.60", _sis(512, 0.60)),
        ("sis-160", _sis(160)),
        ("sis-160-g0.15", _sis(160, 0.15)),
        ("sis-160-g0.30", _sis(160, 0.30)),
        ("sis-160-g0.45", _sis(160, 0.45)),
        ("sis-160-g0.60", _sis(160, 0.60)),
        ("sis-160-g0.80", _sis(160, 0.80)),
        # ("exact-free", ...) CANNOT BE REGENERATED, and that is deliberate.
        # It was the counting DP run with the OR clauses ignored. `Posterior`
        # now RAISES on mode="exact" wherever a clause is active, because the
        # DP draws from a strict superset of the feasible worlds and reporting
        # that as exact is the worst of the three available outcomes. The row
        # stands in the results file as a measurement of a mode the engine has
        # since removed on purpose; it is not recoverable and must not be
        # quietly re-derived from something else.
    ],
    # results/posterior_accuracy2.json -- count and cap variants.
    "shape": [
        ("v03-512", _v03(512)), ("v03-32", _v03(32)),
        ("sis-160", _sis(160)),
        ("sis-160-g0.35", _sis(160, 0.35)),
        ("sis-160-g0.35-sqrt", _sis(160, 0.35, count_mode="sqrt")),
        ("sis-320-g0.45", _sis(320, 0.45)),
        ("sis-160-g0.70-sqrt", _sis(160, 0.70, count_mode="sqrt")),
        ("sis-320-g0.70-sqrt", _sis(320, 0.70, count_mode="sqrt")),
        ("sis-160-g0.35-cap", _sis(160, 0.35, count_mode="capped")),
        ("sis-160-g1.20-cap", _sis(160, 1.20, count_mode="capped")),
        # The two `-cur` rows of results/posterior_accuracy2.json are NOT
        # reconstructed. They scored NLL 2.221 and 2.644 against a class prior
        # near 1.4 -- far worse than guessing -- and no surviving argument of
        # `Posterior` reproduces that name. Guessing at a configuration and
        # labelling the guess with the original row's name would be worse than
        # leaving the row unproducible, so it is left unproducible and said so.
    ],
    # results/posterior_accuracy3.json -- the at-ask-time depth variants.
    "attime": [
        ("v03-512", _v03(512)),
        ("sis-160", _sis(160)),
        ("sis-160-g0.35", _sis(160, 0.35)),
        ("sis-160-g0.35-attime", _sis(160, 0.35, depth_mode="attime")),
        ("sis-160-g0.70-attime", _sis(160, 0.70, depth_mode="attime")),
        ("sis-160-g1.20-attime", _sis(160, 1.20, depth_mode="attime")),
        ("sis-160-g0.70-attime-sqrt", _sis(160, 0.70, depth_mode="attime",
                                           count_mode="sqrt")),
        ("sis-320-g0.70-attime", _sis(320, 0.70, depth_mode="attime")),
        ("sis-320-g0.45", _sis(320, 0.45)),
    ],
}

#: Which results file each campaign produced, so a reader can go both ways.
CAMPAIGN_FILE = {"gamma": "posterior_accuracy.json",
                 "shape": "posterior_accuracy2.json",
                 "attime": "posterior_accuracy3.json"}

#: The last campaign run, kept as the default so existing invocations are
#: unchanged. Pass --campaign= to reproduce an earlier one.
CONFIGS = CAMPAIGNS["attime"]


class Score:
    __slots__ = ("nll", "brier", "top1", "n", "seconds", "calib")

    def __init__(self):
        self.nll = 0.0
        self.brier = 0.0
        self.top1 = 0
        self.n = 0
        self.seconds = 0.0
        self.calib = defaultdict(lambda: [0.0, 0.0, 0])   # bin -> [p_sum, hits, n]

    def add(self, M, truth, cards):
        for c in cards:
            t = truth[c]
            row = M[c]
            p = float(row[t])
            self.nll += -math.log(max(p, EPS))
            self.brier += float(((row - np.eye(NUM_PLAYERS)[t]) ** 2).sum())
            self.top1 += int(int(np.argmax(row)) == t)
            self.n += 1

    def add_calibration(self, M, truth, cards):
        """Reliability must bin the probability assigned to a FIXED outcome.

        Binning by the probability given to the true holder would make every
        entry a hit by construction and report perfect calibration for any
        model at all.
        """
        for c in cards:
            t = truth[c]
            for p in range(NUM_PLAYERS):
                pr = float(M[c, p])
                b = min(9, int(pr * 10))
                e = self.calib[b]
                e[0] += pr
                e[1] += 1.0 if p == t else 0.0
                e[2] += 1

    def to_dict(self):
        if not self.n:
            return {}
        calib = {str(b): {"mean_p": v[0] / v[2], "freq": v[1] / v[2], "n": v[2]}
                 for b, v in sorted(self.calib.items()) if v[2] > 0}
        return {"nll": self.nll / self.n, "brier": self.brier / self.n,
                "top1": self.top1 / self.n, "n_cards": self.n,
                "seconds": self.seconds,
                "ms_per_decision": None, "calibration": calib}


def true_holder_map(state: GameState):
    truth = {}
    for p in range(NUM_PLAYERS):
        h = state.hands[p]
        while h:
            low = h & -h
            truth[low.bit_length() - 1] = p
            h ^= low
    return truth


def main(n_games: int = 12, stride: int = 3, out: str = None):
    rules = RuleConfig()
    scores = {name: Score() for name, _ in CONFIGS}
    calib = {name: Score() for name, _ in CONFIGS}
    decisions = 0
    ref = ("tuned", {"w_turn": 0.6, "w_scarce": 0.2})
    for g in range(n_games):
        agents = [make_agent(ref) for _ in range(6)]
        ar = random.Random(31_000 + g)
        st = GameState.deal(rules, seed=41_000 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        bels = [BeliefState(rules, observer=p) for p in range(6)]
        step = 0
        while not st.is_terminal and step < 400:
            p = st.turn
            for q in range(NUM_PLAYERS):
                bels[q].update(Observation.from_state(st, q))
            if step % stride == 0:
                obs = Observation.from_state(st, p)
                bel = bels[p]
                truth = true_holder_map(st)
                # score only cards that are still genuinely uncertain for this
                # seat: a pinned card is free marks for every configuration
                cards = [c for c in range(bel.n)
                         if bel.public_loc[c] is None
                         and bel.candidates[c].bit_count() > 1]
                if cards:
                    decisions += 1
                    for name, fn in CONFIGS:
                        rng = random.Random(9_000_000 + 977 * decisions)
                        t0 = time.perf_counter()
                        M = fn(bel, rng, obs)
                        dt = time.perf_counter() - t0
                        scores[name].seconds += dt
                        scores[name].add(M, truth, cards)
                        calib[name].add_calibration(M, truth, cards)
            st.apply(p, agents[p].act(Observation.from_state(st, p)))
            step += 1
        print(f"  game {g+1}/{n_games}: {decisions} scored decisions",
              file=sys.stderr, flush=True)

    rows = []
    for name, _ in CONFIGS:
        d = scores[name].to_dict()
        if not d:
            continue
        d["name"] = name
        d["ms_per_decision"] = 1000.0 * scores[name].seconds / max(1, decisions)
        d["calibration"] = calib[name].to_dict().get("calibration", {})
        rows.append(d)
    rows.sort(key=lambda r: r["nll"])
    print(f"\n{decisions} decisions, {rows[0]['n_cards']} uncertain-card "
          f"predictions each\n")
    print(f"{'config':16s} {'NLL':>8s} {'Brier':>8s} {'top-1':>8s} "
          f"{'ms/dec':>9s}")
    for r in rows:
        print(f"{r['name']:16s} {r['nll']:8.4f} {r['brier']:8.4f} "
              f"{r['top1']:8.4f} {r['ms_per_decision']:9.2f}")
    #: The output path is now an ARGUMENT. It was not, and `__main__` never
    #: passed one, so every invocation wrote `posterior_accuracy3.json` while
    #: `scripts4/check_paper_numbers.py` watches `posterior_accuracy.json` --
    #: a file no documented command could regenerate. Found by an audit of the
    #: paper's reproduction section.
    path = Path(out) if out else ROOT / "results" / "posterior_accuracy3.json"
    payload = {"n_games": n_games, "stride": stride, "decisions": decisions,
               "rows": rows}
    print(f"\nSaved {write_result(path, payload)}")


if __name__ == "__main__":
    camp = next((x.split("=", 1)[1] for x in sys.argv[1:]
                 if x.startswith("--campaign=")), None)
    if camp is not None:
        if camp not in CAMPAIGNS:
            raise SystemExit(f"--campaign= must be one of "
                             f"{sorted(CAMPAIGNS)}; each reproduces the "
                             f"results file named in CAMPAIGN_FILE.")
        CONFIGS = CAMPAIGNS[camp]
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    main(int(a[0]) if a else 12,
         int(a[1]) if len(a) > 1 else 3,
         a[2] if len(a) > 2 else None)
