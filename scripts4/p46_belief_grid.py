"""P46 Stage 0: the belief about SESTINA's cards, scored on the dealt truth.

Registered in `prereg/kraken_v12_belief_grid.md`, which fixes the cells, the
budgets, the seeds, the exclusion and the six bars before any position was
scored. This file is the instrument that document names. It ships nothing and
plays no candidate game.

WHAT IT MEASURES. Play is the champion throughout: `KRAKEN_V1` on one parity
against `("dylan_v07", {})` on the other in block A, six `KRAKEN_V1` seats in
block B. At every 4th decision of a scored seat the position is frozen after
`act()` and before `apply()`, and the seat's own propagated belief is re-read
under every cell of the grid -- `gamma_opp x gamma_team`, plus two
`opp_lambda` values at the incumbent -- and scored against the arbiter's truth
on the cards the propagator has not pinned, in two pools: cards a SESTINA seat
(block A) or an opponent (block B) really holds, and cards a teammate really
holds. NLL is the proper score; Brier and top-1 are carried because NLL is
unbounded and because a belief can win NLL by spreading mass while naming the
holder LESS often. Every cell is paired against the incumbent on the same
decisions, and every interval is clustered by game with
`fish4.clustered.cluster_ci`, because decisions inside one game share a deal,
a seed and a policy realisation.

WHY TWO BUDGETS. Every cell is rebuilt at 720 and at 2,880 draws with the same
sampler seed in every cell at a budget. At `sis_tilt = 0` the model enters the
importance weights only, so cells at one budget share particles and differ
only in weights: a paired comparison in the strict sense. The two budgets
exist because `results/channel_precision_plateau.json` shows the SIGN of an
opponent-pool NLL contrast can depend on effective budget -- a cell that
spreads the log-weights thins the sample, and a thinner sample pays a
finite-sample penalty of unknown size at a fixed nominal budget. Recording
the Kish ESS per row is what lets that penalty be sized rather than guessed.

WHY THE EXCLUSION. At a decision where the incumbent has no non-self ask on
record, `oppmodel.build` returns no model and the incumbent takes the exact
DP. On such a decision a cell with a live model is not the same particles
re-weighted but a different inference method, and a paired contrast there
would be about the method. Those decisions are recorded with `excluded=True`
and enter no paired figure. Cell (0.0, 0.0) is the same story at every
decision, so it is a reference row only and is never paired.

DESIGN OF THE RUN. Two passes over the same games. The first plays every game
uninstrumented and counts its frozen decisions, so each game's global decision
index `d` is known before the second pass builds a single posterior -- the
registration's per-decision sampler seed is `7,200,000 + 977 d` and `d` must
be the continuing global index. The second pass replays each game with the
instrument and compares its transcript to the first, action for action; a
mismatch is recorded as a void condition, since it would mean the instrument
had touched the champion's play. The agent's RNG state is saved and restored
around every instrument posterior, and the instrument's posteriors carry their
own `PosteriorStats` so the live champion's counters are untouched.

Usage:
  python scripts4/p46_belief_grid.py [--deals-a 60] [--deals-b 60]
         [--stride 4] [--jobs 3] [--out results/p46_belief_grid.json]
  python scripts4/p46_belief_grid.py --smoke --out /tmp/x.json
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, half_suit_cards             # noqa: E402
from fish.engine import GameState                               # noqa: E402
from fish.observation import Observation                        # noqa: E402
from fish.rules import RuleConfig                               # noqa: E402
from fish4.clustered import cluster_ci                          # noqa: E402
from fish4.posterior import Posterior, PosteriorStats           # noqa: E402

PREREG = "prereg/kraken_v12_belief_grid.md"

#: The dialect every P43-P46 figure was taken under.
RULES_D = {"wrong_distribution_outcome": "opponent"}
MAX_ACTIONS = 600

#: Seeds, all fixed by the registration and grep-clean at its writing.
DEAL_A0 = 10_600_000
DEAL_B0 = 10_600_500
AGENT0 = 106_000
SAMPLER_720 = 7_200_000
SAMPLER_2880 = 7_250_000
SAMPLER_480 = 7_300_000
SAMPLER_STEP = 977

#: Cells, 20, fixed by the registration: (gamma_opp, gamma_team, opp_lambda).
GAMMA_OPP = [-1.1055, -0.5, 0.0, 0.35, 0.7, 1.0]
GAMMA_TEAM = [0.0, 0.35, 0.7]
LAMBDAS = [0.3, 0.9]
INCUMBENT = (0.35, 0.35, 0.0)
REFERENCE = (0.0, 0.0, 0.0)
CELLS = [(go, gt, 0.0) for go in GAMMA_OPP for gt in GAMMA_TEAM] + \
        [(0.35, 0.35, lam) for lam in LAMBDAS]
BUDGETS = [720, 2880]
#: The incumbent scored once more at the engine's own draw count, block A
#: only, for validity bar 3.
VALIDITY_BUDGET = 480

#: The smoke configuration `--smoke` selects. Tests only.
SMOKE_CELLS = [INCUMBENT, (0.0, 0.35, 0.0), (-1.1055, 0.35, 0.0)]
SMOKE_BUDGETS = [720]

#: The bars, as numbers, fixed by the registration.
ESS_DEGENERACY_BAR = 0.70
ESS_NOT_ROBUST_BAR = 0.25
VALIDITY_TOLERANCE = 0.10
LAMBDA_CALIBRATION_BAR = 0.10
#: The only cell the registration allows to become an arm (arm G).
PROMOTABLE = (0.7, 0.7, 0.0)

EPS = 1e-12
POOLS = ("opp", "team")
SCORES = ("nll", "brier", "top1")


# ---------------------------------------------------------------- helpers

def cell_key(cell) -> str:
    go, gt, lam = cell
    return f"{go:g},{gt:g},{lam:g}"


def sampler_seed(budget: int, d: int) -> int:
    base = {720: SAMPLER_720, 2880: SAMPLER_2880,
            VALIDITY_BUDGET: SAMPLER_480}[budget]
    return base + SAMPLER_STEP * d


def true_holder_map(state: GameState) -> dict[int, int]:
    truth = {}
    for p in range(NUM_PLAYERS):
        h = state.hands[p]
        while h:
            low = h & -h
            truth[low.bit_length() - 1] = p
            h ^= low
    return truth


def build_cell(agent, obs, cell, n_draws: int, rng: random.Random) -> Posterior:
    """The champion's posterior at this decision, re-weighted under ``cell``.

    Every keyword `FishBot4.build_posterior` passes is passed here from the
    same attributes, so the only differences between this and the agent's own
    posterior are the three cell knobs, the draw count and the RNG. The
    incumbent cell must reproduce `agent.build_posterior(obs, n_draws=n)`
    bit for bit under the same RNG seed; `tests4/test_p46_belief_grid.py`
    checks that, because a hand-copied argument list is how this project has
    twice measured something other than what it thought.

    ``stats`` is a fresh counter, never the agent's: bar 3 compares the
    instrument to the LIVE champion's `PosteriorStats`, which the instrument
    must not feed.
    """
    go, gt, lam = cell
    return Posterior(agent.bel, rng, n_draws=n_draws,
                     n_worlds=agent.n_worlds, mode=agent.infer_mode,
                     obs=obs, gamma=go, gamma_team=gt,
                     convention_beta=agent.convention_beta,
                     convention_q=agent.convention_q,
                     convention_aim=agent.convention_aim,
                     convention_book=agent.convention_book,
                     depth_mode=agent.depth_mode,
                     count_mode=agent.count_mode,
                     opp_lambda=lam,
                     gamma_schedule=agent.gamma_schedule,
                     sis_tilt=agent.sis_tilt,
                     silence_delta=agent.silence_delta,
                     stats=PosteriorStats())


def batch_ess(post: Posterior):
    """Kish ESS of the posterior's weighted batch, or None on the exact path.

    `WeightedSample.ess` is `1 / sum(w^2)` over the normalised weights, and
    `Posterior._apply_silence_prior` keeps it current when it re-weights; it
    is read rather than recomputed so the number is the one the engine's own
    counters see.
    """
    b = post._batch
    if b is None or not len(b):
        return None
    ess = getattr(b, "ess", None)
    if ess is None:
        w = b.w
        ess = float(1.0 / (w ** 2).sum())
    return float(ess)


def score_pool(M, truth, cards) -> dict | None:
    """Per-decision mean NLL, Brier and top-1 over ``cards``."""
    if not cards:
        return None
    nll = brier = 0.0
    top1 = 0
    for c in cards:
        row = M[c]
        t = truth[c]
        nll += -math.log(max(float(row[t]), EPS))
        brier += sum((float(row[q]) - (1.0 if q == t else 0.0)) ** 2
                     for q in range(NUM_PLAYERS))
        best = max(range(NUM_PLAYERS), key=lambda q: row[q])
        top1 += int(best == t)
    n = len(cards)
    return {"mean_nll": nll / n, "mean_brier": brier / n,
            "top1": top1 / n, "n_cards": n}


def unpinned_cards(bel) -> list[int]:
    """The same test `scripts4/gamma_split.py` uses: never publicly located
    and more than one candidate holder."""
    return [c for c in range(bel.n)
            if bel.public_loc[c] is None
            and bel.candidates[c].bit_count() > 1]


def calibration_entries(post: Posterior, obs, st, mover: int) -> list[dict]:
    """The `opp_lambda` calibration number at one decision.

    For every live half-suit in which the acting seat holds no card: the
    incumbent's `P(all six with the opponents)` and whether that is TRUE in
    the arbiter's hands.
    """
    opponents = [p for p in range(NUM_PLAYERS) if p % 2 != mover % 2]
    out = []
    for hs, winner in enumerate(obs.set_winner):
        if winner is not None:
            continue
        cards = list(half_suit_cards(hs))
        if any(obs.hand >> c & 1 for c in cards):
            continue
        p = float(post.prob_all_with(cards, opponents))
        truth = all(any(st.hands[q] >> c & 1 for q in opponents)
                    for c in cards)
        out.append({"hs": hs, "p": p, "truth": bool(truth)})
    return out


# ---------------------------------------------------------------- one game

def _make_agents(block: str, kv_even: bool):
    from fish4.registry4 import KRAKEN_V1, make_agent
    if block == "A":
        scored = {p for p in range(NUM_PLAYERS) if (p % 2 == 0) == kv_even}
        agents = [make_agent(KRAKEN_V1) if p in scored
                  else make_agent(("dylan_v07", {})) for p in range(NUM_PLAYERS)]
    else:
        scored = {p for p in range(NUM_PLAYERS) if p % 2 == 0}
        agents = [make_agent(KRAKEN_V1) for _ in range(NUM_PLAYERS)]
    return agents, scored


def play_game(block: str, deal: int, kv_even: bool, d0: int = 0,
              cells=None, budgets=None, stride: int = 4,
              max_actions: int = MAX_ACTIONS, instrument: bool = True) -> dict:
    """Play one champion game; with ``instrument`` freeze every ``stride``-th
    decision of each scored seat and score the grid on it.

    Returns the transcript (``moves``), the per-decision metadata, the scored
    rows, the calibration entries and every KRAKEN seat's live
    `PosteriorStats` at game end. With ``instrument=False`` only the
    transcript, the frozen-decision count and the stats come back, which is
    the first pass of the run.
    """
    cells = list(CELLS if cells is None else cells)
    budgets = list(BUDGETS if budgets is None else budgets)
    rules = RuleConfig(**RULES_D)
    agents, scored = _make_agents(block, kv_even)
    st = GameState.deal(rules, seed=deal)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal * 13 + p)
    game = f"{block}:{deal}:{int(kv_even)}" if block == "A" else f"{block}:{deal}"
    n_dec = {p: 0 for p in scored}
    moves: list[tuple[int, str]] = []
    decisions: list[dict] = []
    rows: list[dict] = []
    calib: list[dict] = []
    d = d0
    n_frozen = 0
    illegal = None
    for _ in range(max_actions):
        if st.is_terminal:
            break
        mover = st.turn
        obs = Observation.from_state(st, mover)
        act = agents[mover].act(obs)
        moves.append((mover, repr(act)))
        if mover in scored:
            k = n_dec[mover]
            n_dec[mover] = k + 1
            if k % stride == 0:
                n_frozen += 1
                if instrument:
                    agent = agents[mover]
                    rng_state = agent.rng.getstate()
                    try:
                        dec, cell_rows, cal = _freeze(
                            block, game, deal, kv_even, mover, d, agent, obs,
                            st, cells, budgets)
                    finally:
                        agent.rng.setstate(rng_state)
                    decisions.append(dec)
                    rows.extend(cell_rows)
                    calib.extend(cal)
                d += 1
        try:
            st.apply(mover, act)
        except Exception as e:                     # IllegalAction is void
            illegal = f"{type(e).__name__}: {e}"
            break
    stats = {p: agents[p].stats.to_dict() for p in range(NUM_PLAYERS)
             if hasattr(agents[p], "stats")}
    return {"block": block, "game": game, "deal": deal, "kv_even": kv_even,
            "moves": moves, "n_frozen": n_frozen, "d0": d0,
            "finished": bool(st.is_terminal), "illegal": illegal,
            "n_actions": len(moves), "decisions": decisions, "rows": rows,
            "calibration": calib, "agent_stats": stats,
            "scored_seats": sorted(scored)}


def _freeze(block, game, deal, kv_even, seat, d, agent, obs, st, cells,
            budgets):
    """Score every cell at every budget on one frozen decision."""
    bel = agent.bel
    truth = true_holder_map(st)
    unp = [c for c in unpinned_cards(bel) if c in truth]
    pools = {
        "team": [c for c in unp if truth[c] % 2 == seat % 2 and truth[c] != seat],
        "opp": [c for c in unp if truth[c] % 2 != seat % 2],
    }
    base = {"block": block, "game": game, "deal": deal, "kv_even": kv_even,
            "seat": seat, "d": d}
    rows = []
    excluded = None
    calib = []
    #: Kish ESS per (cell, budget) on the decision itself, so the bar-4 ratio
    #: and the bar-3 instrument mean count every non-excluded decision once,
    #: whether or not either pool has a card on it.
    ess_by_cell: dict[str, dict[str, float | None]] = {}
    for budget in budgets:
        for cell in cells:
            rng = random.Random(sampler_seed(budget, d))
            post = build_cell(agent, obs, cell, budget, rng)
            M = post.marginals()
            if cell == INCUMBENT:
                if excluded is None:
                    excluded = bool(post.exact)
                if block == "A" and budget == budgets[0]:
                    calib = [dict(e, deal=deal, game=game, seat=seat, d=d,
                                  excluded=excluded)
                             for e in calibration_entries(post, obs, st, seat)]
            ess = batch_ess(post)
            ess_by_cell.setdefault(cell_key(cell), {})[str(budget)] = ess
            for pool in POOLS:
                sc = score_pool(M, truth, pools[pool])
                if sc is None:
                    continue
                rows.append(dict(base, excluded=excluded, cell=list(cell),
                                 budget=budget, pool=pool, ess=ess, **sc))
    if block == "A" and INCUMBENT in cells:
        rng = random.Random(sampler_seed(VALIDITY_BUDGET, d))
        post = build_cell(agent, obs, INCUMBENT, VALIDITY_BUDGET, rng)
        M = post.marginals()
        ess = batch_ess(post)
        ess_by_cell.setdefault(cell_key(INCUMBENT), {})[
            str(VALIDITY_BUDGET)] = ess
        for pool in POOLS:
            sc = score_pool(M, truth, pools[pool])
            if sc is None:
                continue
            rows.append(dict(base, excluded=excluded, cell=list(INCUMBENT),
                             budget=VALIDITY_BUDGET, pool=pool, ess=ess, **sc))
    # `excluded` is None only if the incumbent was not among the cells, which
    # no registered configuration allows; treat it as excluded so nothing is
    # paired on it.
    if excluded is None:
        excluded = True
    for r in rows:
        r["excluded"] = excluded
    dec = dict(base, excluded=excluded, n_unpinned=len(unp),
               n_team=len(pools["team"]), n_opp=len(pools["opp"]),
               ess=ess_by_cell)
    return dec, rows, calib


# ---------------------------------------------------------------- workers

def _count_job(args):
    block, deal, kv_even, stride = args
    r = play_game(block, deal, kv_even, stride=stride, instrument=False)
    return {k: r[k] for k in ("block", "game", "deal", "kv_even", "moves",
                              "n_frozen", "finished", "illegal",
                              "n_actions", "agent_stats", "scored_seats")}


def _score_job(args):
    block, deal, kv_even, d0, cells, budgets, stride = args
    return play_game(block, deal, kv_even, d0=d0, cells=cells,
                     budgets=budgets, stride=stride, instrument=True)


def _run_pool(fn, jobs, n_jobs: int, label: str, t0: float):
    out = []
    if n_jobs > 1:
        with Pool(n_jobs) as pool:
            for i, r in enumerate(pool.imap_unordered(fn, jobs, chunksize=1)):
                out.append(r)
                if (i + 1) % 10 == 0 or i + 1 == len(jobs):
                    print(f"  {label}: {i + 1}/{len(jobs)} games, "
                          f"{time.time() - t0:.0f}s", flush=True)
    else:
        for i, j in enumerate(jobs):
            out.append(fn(j))
            if (i + 1) % 10 == 0 or i + 1 == len(jobs):
                print(f"  {label}: {i + 1}/{len(jobs)} games, "
                      f"{time.time() - t0:.0f}s", flush=True)
    return out


# ---------------------------------------------------------------- aggregation

def _ci(values, groups):
    """(mean, lo, hi, half_width, n, k) clustered by ``groups``; lo/hi None
    when there is only one cluster."""
    if not values:
        return None
    mu, hw, k = cluster_ci(values, groups)
    return {"mean": mu, "lo": None if hw is None else mu - hw,
            "hi": None if hw is None else mu + hw, "half_width": hw,
            "n": len(values), "k": k}


def _below_zero(ci) -> bool:
    """Interval entirely below zero. A missing or zero-width interval never
    qualifies: it is a void condition, not evidence."""
    return (ci is not None and ci["hi"] is not None
            and ci["half_width"] > 0.0 and ci["hi"] < 0.0)


def _above_zero(ci) -> bool:
    return (ci is not None and ci["lo"] is not None
            and ci["half_width"] > 0.0 and ci["lo"] > 0.0)


def _zero_width(ci) -> bool:
    return ci is not None and ci["half_width"] is not None \
        and ci["half_width"] == 0.0


def _index_rows(rows):
    """{(block, cell_key, budget, pool): {d: row}} over NON-excluded rows,
    plus the same over every row (for reference levels)."""
    paired: dict = {}
    every: dict = {}
    for r in rows:
        k = (r["block"], cell_key(r["cell"]), r["budget"], r["pool"])
        every.setdefault(k, {})[r["d"]] = r
        if not r["excluded"]:
            paired.setdefault(k, {})[r["d"]] = r
    return paired, every


def _levels(by_d):
    """Unpaired levels of one (cell, budget, pool), clustered by game."""
    if not by_d:
        return None
    ds = sorted(by_d)
    groups = [by_d[d]["game"] for d in ds]
    out = {"n_decisions": len(ds)}
    for s in SCORES:
        key = {"nll": "mean_nll", "brier": "mean_brier", "top1": "top1"}[s]
        out[s] = _ci([by_d[d][key] for d in ds], groups)
    ess = [by_d[d]["ess"] for d in ds if by_d[d]["ess"] is not None]
    out["mean_ess"] = (sum(ess) / len(ess)) if ess else None
    return out


def _paired(cell_by_d, inc_by_d):
    ds = sorted(set(cell_by_d) & set(inc_by_d))
    if not ds:
        return None
    groups = [cell_by_d[d]["game"] for d in ds]
    out = {"n_decisions": len(ds), "n_games": len(set(groups))}
    for s in SCORES:
        key = {"nll": "mean_nll", "brier": "mean_brier", "top1": "top1"}[s]
        out[s] = _ci([cell_by_d[d][key] - inc_by_d[d][key] for d in ds],
                     groups)
    return out


def _dec_ess(dec, ck: str, budget: int):
    """The Kish ESS recorded on a frozen decision for one (cell, budget),
    None if that cell took the exact path or was not built there."""
    return (dec.get("ess") or {}).get(ck, {}).get(str(budget))


def _ess_ratio(decisions, block: str, ck: str, budget: int):
    """Bar 4: mean ESS/n of a cell relative to the incumbent at the same
    nominal n, over the NON-excluded frozen decisions of ``block`` on which
    both were sampled. Read off the decision records, not the pool rows, so
    a decision with an empty pool still counts once."""
    inc = cell_key(INCUMBENT)
    c, i = [], []
    for dec in decisions:
        if dec["block"] != block or dec["excluded"]:
            continue
        ec, ei = _dec_ess(dec, ck, budget), _dec_ess(dec, inc, budget)
        if ec is None or ei is None:
            continue
        c.append(ec)
        i.append(ei)
    if not c:
        return None
    mc = sum(c) / len(c) / budget
    mi = sum(i) / len(i) / budget
    return {"mean_ess_over_n": mc, "incumbent_mean_ess_over_n": mi,
            "ratio": (mc / mi) if mi > 0 else None, "n_decisions": len(c)}


def aggregate(rows, decisions, games, calibration, cells, budgets,
              stride: int) -> dict:
    """Every bar of the registration, from the per-decision rows."""
    paired_idx, every_idx = _index_rows(rows)
    blocks = sorted({r["block"] for r in rows})
    inc = cell_key(INCUMBENT)
    ref = cell_key(REFERENCE)
    b720, b2880 = 720, 2880
    have_both = b720 in budgets and b2880 in budgets

    # -- per block, per cell, per budget, per pool ---------------------------
    grid: dict = {}
    for block in blocks:
        grid[block] = {}
        for cell in cells:
            ck = cell_key(cell)
            entry = {"cell": list(cell), "paired": ck not in (inc, ref),
                     "budgets": {}}
            for budget in budgets:
                bt: dict = {"pools": {}, "ess": None}
                for pool in POOLS:
                    k = (block, ck, budget, pool)
                    ki = (block, inc, budget, pool)
                    pe = {"level": _levels(every_idx.get(k, {})),
                          "level_non_excluded": _levels(paired_idx.get(k, {}))}
                    if entry["paired"]:
                        pe["paired_vs_incumbent"] = _paired(
                            paired_idx.get(k, {}), paired_idx.get(ki, {}))
                    bt["pools"][pool] = pe
                # ESS is a property of the batch, not of a pool; it is read
                # off the decision record so every non-excluded decision
                # counts once, whichever pools have cards on it.
                bt["ess"] = _ess_ratio(decisions, block, ck, budget)
                entry["budgets"][str(budget)] = bt
            grid[block][ck] = entry

    def pv(block, ck, budget, pool, score):
        e = grid.get(block, {}).get(ck)
        if e is None or not e["paired"]:
            return None
        pe = e["budgets"].get(str(budget), {}).get("pools", {}).get(pool)
        if pe is None:
            return None
        p = pe.get("paired_vs_incumbent")
        return None if p is None else p.get(score)

    def rule1_block(block, ck):
        """Registration bar 1, one block: opp-pool NLL entirely below zero at
        BOTH budgets and no pool's top-1 entirely below zero at either."""
        nll_ok = all(_below_zero(pv(block, ck, b, "opp", "nll"))
                     for b in (b720, b2880))
        top1_ok = not any(_below_zero(pv(block, ck, b, pool, "top1"))
                          for b in (b720, b2880) for pool in POOLS)
        return {"opp_nll_below_zero_both_budgets": nll_ok,
                "no_top1_interval_below_zero": top1_ok,
                "holds": bool(nll_ok and top1_ok)}

    verdicts: dict = {}
    for cell in cells:
        ck = cell_key(cell)
        if ck in (inc, ref):
            continue
        v: dict = {"cell": list(cell)}
        r1 = {block: rule1_block(block, ck) for block in blocks}
        v["rule1"] = r1
        v["rule1_holds_both_blocks"] = (
            have_both and {"A", "B"} <= set(blocks)
            and all(r1[b]["holds"] for b in ("A", "B")))
        # bar 4: ESS/n relative to the incumbent
        ess = {}
        for block in blocks:
            for budget in budgets:
                e = grid[block][ck]["budgets"][str(budget)]["ess"]
                ess[f"{block}:{budget}"] = None if e is None else e["ratio"]
        ratios = [x for x in ess.values() if x is not None]
        v["ess_ratio"] = ess
        v["degeneracy_live"] = bool(ratios) and min(ratios) < ESS_DEGENERACY_BAR
        r720 = [ess.get(f"{b}:{b720}") for b in blocks]
        r720 = [x for x in r720 if x is not None]
        v["not_budget_robust"] = bool(r720) and min(r720) < ESS_NOT_ROBUST_BAR
        # bar 5: sign agreement of opp-pool NLL at 720 and 2880
        signs = {}
        for block in blocks:
            a = pv(block, ck, b720, "opp", "nll")
            b = pv(block, ck, b2880, "opp", "nll")
            if a is None or b is None:
                signs[block] = None
                continue
            signs[block] = {
                "mean_720": a["mean"], "mean_2880": b["mean"],
                "sign_agrees": (a["mean"] < 0) == (b["mean"] < 0),
                "sampling_component_2880_minus_720": b["mean"] - a["mean"]}
        v["budget_robustness"] = signs
        v["sign_agrees_all_blocks"] = (
            have_both and bool(signs)
            and all(s is not None and s["sign_agrees"] for s in signs.values()))
        # bar 3, second half: a non-zero-width interval on at least one pool
        # at 720, per block
        nz = {}
        for block in blocks:
            cis = [pv(block, ck, b720, pool, s)
                   for pool in POOLS for s in SCORES]
            nz[block] = any(c is not None and c["half_width"] is not None
                            and c["half_width"] > 0.0 for c in cis)
        v["nonzero_width_at_720"] = nz
        zw = [f"{block}:{budget}:{pool}:{s}"
              for block in blocks for budget in budgets
              for pool in POOLS for s in SCORES
              if _zero_width(pv(block, ck, budget, pool, s))]
        v["zero_width_intervals"] = zw
        # the verdict string
        if not have_both or not {"A", "B"} <= set(blocks):
            status = "no verdict: the registration's rules need both " \
                     "budgets and both blocks (smoke or partial run)"
        elif not v["rule1_holds_both_blocks"] and not v["sign_agrees_all_blocks"]:
            status = "statement about a budget: opp-pool NLL sign differs " \
                     "between 720 and 2880"
        elif v["not_budget_robust"]:
            status = "not budget-robust: ESS/n at 720 under 0.25 of the " \
                     "incumbent's; neither closed nor licensed"
        elif v["rule1_holds_both_blocks"]:
            status = "licensed" if cell == PROMOTABLE else \
                     "rule 1 holds but the cell is not promotable " \
                     "(registration bar 1: only (0.7, 0.7) can become an arm)"
        else:
            status = "closed"
        v["status"] = status
        v["licenses_arm_G"] = bool(v["rule1_holds_both_blocks"]
                                   and cell == PROMOTABLE
                                   and not v["not_budget_robust"])
        verdicts[ck] = v

    # -- bar 2: calibration clause -------------------------------------------
    twin_c1c = cell_key((-1.1055, 0.35, 0.0))
    c1c = verdicts.get(twin_c1c)
    c1c_licensed = bool(c1c and c1c["rule1_holds_both_blocks"])
    # "fails to fail": the rule does not find the belief twin of a cell that
    # lost -0.90 in play measurably worse, i.e. its block-A opp-pool NLL
    # interval is not entirely above zero at both budgets.
    c1c_fails = have_both and "A" in blocks and all(
        _above_zero(pv("A", twin_c1c, b, "opp", "nll")) for b in (b720, b2880))
    ref_reading = {}
    ref_better = False
    for block in blocks:
        for budget in budgets:
            e = grid[block].get(ref)
            i = grid[block].get(inc)
            if e is None or i is None:
                continue
            lr = e["budgets"][str(budget)]["pools"]["opp"]["level_non_excluded"]
            li = i["budgets"][str(budget)]["pools"]["opp"]["level_non_excluded"]
            if lr is None or li is None:
                continue
            ref_reading[f"{block}:{budget}"] = {
                "reference_opp_nll": lr["nll"]["mean"],
                "incumbent_opp_nll": li["nll"]["mean"],
                "reference_lower": lr["nll"]["mean"] < li["nll"]["mean"]}
    if have_both and "A" in blocks and "B" in blocks:
        ref_better = all(ref_reading.get(f"{b}:{n}", {}).get("reference_lower",
                                                              False)
                         for b in ("A", "B") for n in (b720, b2880))
    calibration_clause = {
        "twin_c1b_reference_reading": ref_reading,
        "twin_c1b_reads_better_than_incumbent_everywhere": ref_better,
        "twin_c1c_licensed": c1c_licensed,
        "twin_c1c_fails_block_A_opp_nll_above_zero_both_budgets": c1c_fails,
        # None when the rule cannot be evaluated (one budget or one block):
        # a clause that cannot be checked is not a clause that failed.
        "uncalibrated": (None if not (have_both and {"A", "B"} <= set(blocks))
                         else bool(ref_better or c1c_licensed
                                   or not c1c_fails)),
        "definition": "uncalibrated if the (0.0, 0.0) reference reads a lower "
                      "opp-pool NLL level than the incumbent at every block "
                      "and budget, or (-1.1055, 0.35) is licensed, or "
                      "(-1.1055, 0.35) is not measurably worse (block-A "
                      "opp-pool paired NLL interval entirely above zero at "
                      "both budgets). If uncalibrated, the grid is "
                      "descriptive and closes nothing.",
    }

    # -- bar 3: validity -----------------------------------------------------
    # The instrument mean is over every non-excluded block-A frozen decision,
    # read off the decision record (not the pool rows), so it is over the
    # same decision set whichever pools have cards on it.
    seen = {}
    for dec in decisions:
        if dec["block"] != "A" or dec["excluded"]:
            continue
        e = _dec_ess(dec, inc, VALIDITY_BUDGET)
        if e is not None:
            seen[dec["d"]] = e
    inst_mean = (sum(seen.values()) / len(seen)) if seen else None
    live_sum = live_n = 0.0
    live_agents = 0
    for g in games:
        if g["block"] != "A":
            continue
        for p in g["scored_seats"]:
            s = g["agent_stats"].get(p) or g["agent_stats"].get(str(p))
            if not s:
                continue
            live_sum += s.get("ess_sum", 0.0)
            live_n += s.get("sis_decisions", 0)
            live_agents += 1
    live_mean = (live_sum / live_n) if live_n else None
    within = None
    if inst_mean is not None and live_mean:
        within = abs(inst_mean - live_mean) / live_mean <= VALIDITY_TOLERANCE
    nonzero_all = all(any(v["nonzero_width_at_720"].values())
                      for v in verdicts.values()) if verdicts else False
    validity = {
        "incumbent_480_mean_ess_over_n": (None if inst_mean is None
                                          else inst_mean / VALIDITY_BUDGET),
        "incumbent_480_n_decisions": len(seen),
        "live_champion_mean_ess_over_n": (None if live_mean is None
                                          else live_mean / VALIDITY_BUDGET),
        "live_champion_sis_decisions": live_n,
        "live_champion_agents": live_agents,
        "relative_gap": (None if not (inst_mean and live_mean)
                         else abs(inst_mean - live_mean) / live_mean),
        "within_tolerance": within,
        "tolerance": VALIDITY_TOLERANCE,
        "every_paired_cell_has_nonzero_width_interval_at_720": nonzero_all,
        "holds": bool(within) and nonzero_all,
        "note": "the live counter mixes in claim-time posteriors and counts "
                "SIS decisions only; the instrument's 480 mean is over its "
                "non-excluded block-A frozen decisions, each counted once",
        "sampler_480_note": f"the 480 validity stream is {SAMPLER_480} + "
                            f"{SAMPLER_STEP}*d, chosen by the instrument "
                            "because the registration fixed the 480 scoring "
                            "but not its seed; the 480 rows enter bar 3 "
                            "only, so the choice cannot touch any paired "
                            "figure",
        "nonzero_width_reading": "a cell passes the second half of bar 3 "
                                 "if any (pool x score) paired interval at "
                                 "720 has non-zero width in ANY block; the "
                                 "per-block reading is recorded per cell "
                                 "under verdicts[cell].nonzero_width_at_720",
    }

    # -- opp_lambda calibration number and bar 6 -----------------------------
    cal_yes = [e for e in calibration if e["truth"]]
    cal_no = [e for e in calibration if not e["truth"]]
    cal = {
        "n_half_suits": len(calibration),
        "n_decisions": len({e["d"] for e in calibration}),
        "truth_yes": _ci([e["p"] for e in cal_yes],
                         [e["deal"] for e in cal_yes]),
        "truth_no": _ci([e["p"] for e in cal_no],
                        [e["deal"] for e in cal_no]),
        "clustered_by": "deal",
    }
    cal_no_mean = cal["truth_no"]["mean"] if cal["truth_no"] else None
    lam_gate = {}
    for lam in LAMBDAS:
        ck = cell_key((0.35, 0.35, lam))
        v = verdicts.get(ck)
        if v is None:
            continue
        open_ = bool(v["rule1_holds_both_blocks"]
                     and cal_no_mean is not None
                     and cal_no_mean > LAMBDA_CALIBRATION_BAR)
        lam_gate[ck] = {"rule1_holds_both_blocks": v["rule1_holds_both_blocks"],
                        "calibration_mean_truth_no": cal_no_mean,
                        "calibration_bar": LAMBDA_CALIBRATION_BAR,
                        "closed_at_belief_level": not open_}

    # -- void conditions -----------------------------------------------------
    void = []
    for g in games:
        if not g["finished"]:
            void.append(f"unfinished game {g['game']}")
        if g.get("illegal"):
            void.append(f"IllegalAction in {g['game']}: {g['illegal']}")
        if g.get("transcript_match") is False:
            void.append(f"transcript differs with instrumentation in "
                        f"{g['game']}")
        for p, s in g["agent_stats"].items():
            if s.get("failures", 0):
                void.append(f"sampler fallback in {g['game']} seat {p}: "
                            f"{s['failures']} failure(s)")
    for ck, v in verdicts.items():
        for z in v["zero_width_intervals"]:
            void.append(f"zero-width interval, cell {ck}, {z}")
    if validity["within_tolerance"] is False:
        void.append("validity bar 3: incumbent-at-480 ESS does not reproduce "
                    "the live champion's within 10%")
    if verdicts and not nonzero_all:
        void.append("validity bar 3: a paired cell has no non-zero-width "
                    "interval at 720")
    # A void grid licenses nothing and reports no verdict: the registration
    # withdraws every cell on any void condition, and a bar-3 failure voids
    # the whole grid. The unvoided reading is kept under `status_if_not_void`
    # so the cause can be found, but no status string can read "licensed" or
    # "closed" beside a VOID list, and no flag an operator reads can be true.
    if void:
        for v in verdicts.values():
            v["status_if_not_void"] = v["status"]
            v["status"] = f"void: {void[0]}"
            v["licenses_arm_G"] = False
        for g_ in lam_gate.values():
            g_["closed_at_belief_level"] = True
            g_["void"] = True
    arm_g = verdicts.get(cell_key(PROMOTABLE), {})
    arm_g_licensed = bool(arm_g.get("licenses_arm_G", False)
                          and calibration_clause["uncalibrated"] is False
                          and not void)

    n_dec = {b: sum(1 for d in decisions if d["block"] == b) for b in blocks}
    n_exc = {b: sum(1 for d in decisions if d["block"] == b and d["excluded"])
             for b in blocks}
    return {"grid": grid, "verdicts": verdicts,
            "calibration_clause": calibration_clause,
            "validity": validity, "opp_lambda_calibration": cal,
            "opp_lambda_gate": lam_gate,
            "arm_G_licensed": arm_g_licensed,
            "void_conditions": void,
            "n_decisions": n_dec, "n_excluded": n_exc,
            "n_games": {b: sum(1 for g in games if g["block"] == b)
                        for b in blocks},
            "stride": stride}


# ---------------------------------------------------------------- driver

def run(deals_a: int, deals_b: int, stride: int, jobs: int, cells, budgets,
        out: Path) -> dict:
    from fish4.dylan_v07 import BRIDGE_REV
    from fish4.registry4 import KRAKEN_V1
    t0 = time.time()
    specs = [("A", DEAL_A0 + i, kv) for i in range(deals_a)
             for kv in (True, False)]
    specs += [("B", DEAL_B0 + i, True) for i in range(deals_b)]
    print(f"P46 belief grid: {len(specs)} games ({2 * deals_a} block A, "
          f"{deals_b} block B), {len(cells)} cells, budgets {budgets}, "
          f"stride {stride}, {jobs} jobs", flush=True)

    # Pass 1: play uninstrumented, count frozen decisions per game so every
    # game's global decision index is known before any posterior is built.
    counts = _run_pool(_count_job, [(b, d, kv, stride) for b, d, kv in specs],
                       jobs, "pass 1 (count)", t0)
    by_game = {c["game"]: c for c in counts}
    d0 = 0
    jobs2 = []
    starts = {}
    for b, d, kv in specs:
        g = f"{b}:{d}:{int(kv)}" if b == "A" else f"{b}:{d}"
        starts[g] = d0
        jobs2.append((b, d, kv, d0, cells, budgets, stride))
        d0 += by_game[g]["n_frozen"]
    print(f"  {d0} frozen decisions to score", flush=True)

    # Pass 2: replay with the instrument; the transcript must not move.
    scored = _run_pool(_score_job, jobs2, jobs, "pass 2 (score)", t0)
    scored.sort(key=lambda r: starts[r["game"]])
    rows, decisions, calibration, games = [], [], [], []
    for r in scored:
        first = by_game[r["game"]]
        r["transcript_match"] = (r["moves"] == first["moves"])
        rows.extend(r["rows"])
        decisions.extend(r["decisions"])
        calibration.extend(r["calibration"])
        games.append({k: r[k] for k in
                      ("block", "game", "deal", "kv_even", "n_frozen", "d0",
                       "finished", "illegal", "n_actions", "agent_stats",
                       "scored_seats", "transcript_match")})
    agg = aggregate(rows, decisions, games, calibration, cells, budgets, stride)
    res = {
        "prereg": PREREG,
        "meta": {
            "bridge_rev": BRIDGE_REV,
            "champion": {"spec": [KRAKEN_V1[0], dict(KRAKEN_V1[1])],
                         "opponent": ["dylan_v07", {}]},
            "rules": RULES_D, "max_actions": MAX_ACTIONS,
            "seeds": {"deal_a0": DEAL_A0, "deal_b0": DEAL_B0,
                      "agent": f"{AGENT0} + deal*13 + seat",
                      "sampler_720": f"{SAMPLER_720} + {SAMPLER_STEP}*d",
                      "sampler_2880": f"{SAMPLER_2880} + {SAMPLER_STEP}*d",
                      "sampler_480": f"{SAMPLER_480} + {SAMPLER_STEP}*d"},
            "deals_a": deals_a, "deals_b": deals_b, "stride": stride,
            "cells": [list(c) for c in cells], "budgets": budgets,
            "validity_budget": VALIDITY_BUDGET,
            "incumbent": list(INCUMBENT), "reference": list(REFERENCE),
            "n_decisions": agg["n_decisions"],
            "n_excluded": agg["n_excluded"],
            "n_games": agg["n_games"],
            "n_rows": len(rows),
            "elapsed_seconds": time.time() - t0,
            "smoke": (len(cells) < len(CELLS) or budgets != BUDGETS),
        },
        "summary": {k: agg[k] for k in
                    ("verdicts", "calibration_clause", "validity",
                     "opp_lambda_calibration", "opp_lambda_gate",
                     "arm_G_licensed", "void_conditions")},
        "grid": agg["grid"],
        "games": games,
        "decisions": decisions,
        "calibration_rows": calibration,
        "rows": rows,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(res, separators=(",", ":")) + "\n")
    _print_summary(res)
    print(f"\nwrote {out}  ({len(rows)} rows, "
          f"{res['meta']['elapsed_seconds']:.0f}s)")
    return res


def _fmt(ci) -> str:
    if ci is None:
        return "       -"
    if ci["lo"] is None:
        return f"{ci['mean']:+.4f} (1 cluster)"
    return f"{ci['mean']:+.4f} [{ci['lo']:+.4f},{ci['hi']:+.4f}]"


def _print_summary(res: dict) -> None:
    s = res["summary"]
    m = res["meta"]
    print(f"\n=== P46 Stage 0, BRIDGE_REV {m['bridge_rev']}: "
          f"{m['n_decisions']} frozen decisions (excluded {m['n_excluded']}), "
          f"games {m['n_games']} ===")
    print("play is the champion; truth scores only; paired on non-excluded "
          "decisions; intervals clustered by game (t at k-1)")
    for block in sorted(res["grid"]):
        for budget in m["budgets"]:
            print(f"\nblock {block}, {budget} draws: cell - incumbent")
            print(f"{'cell':>18} | {'opp NLL':>28} {'opp top1':>28} | "
                  f"{'team NLL':>28} | {'ESS/n ratio':>11}")
            for ck, e in res["grid"][block].items():
                if not e["paired"]:
                    continue
                b = e["budgets"][str(budget)]
                po = b["pools"]["opp"].get("paired_vs_incumbent")
                pt = b["pools"]["team"].get("paired_vs_incumbent")
                er = b["ess"]
                print(f"{ck:>18} | {_fmt(po and po['nll']):>28} "
                      f"{_fmt(po and po['top1']):>28} | "
                      f"{_fmt(pt and pt['nll']):>28} | "
                      f"{(er['ratio'] if er and er['ratio'] is not None else float('nan')):11.3f}")
    print("\nverdicts")
    for ck, v in s["verdicts"].items():
        print(f"  {ck:>18}: {v['status']}")
    cc = s["calibration_clause"]
    print("\ncalibration clause: "
          + {None: "not assessable (needs both budgets and both blocks)",
             True: "UNCALIBRATED -- grid is descriptive",
             False: "satisfied"}[cc["uncalibrated"]])
    va = s["validity"]
    print(f"validity: incumbent@480 ESS/n "
          f"{va['incumbent_480_mean_ess_over_n']}, live champion "
          f"{va['live_champion_mean_ess_over_n']}, within 10%: "
          f"{va['within_tolerance']}; non-zero-width at 720 for every cell: "
          f"{va['every_paired_cell_has_nonzero_width_interval_at_720']}")
    cal = s["opp_lambda_calibration"]
    print(f"opp_lambda calibration, P(all six with opponents): truth-yes "
          f"{_fmt(cal['truth_yes'])}, truth-no {_fmt(cal['truth_no'])} "
          f"over {cal['n_half_suits']} half-suits, deal-clustered")
    for ck, g in s["opp_lambda_gate"].items():
        print(f"  {ck}: {'closed at the belief level' if g['closed_at_belief_level'] else 'OPEN'}")
    print(f"arm G licensed: {s['arm_G_licensed']}"
          + (" (grid void: no cell licenses)" if s["void_conditions"] else ""))
    if s["void_conditions"]:
        print("VOID CONDITIONS (the grid is not reported):")
        for v in s["void_conditions"]:
            print(f"  - {v}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--deals-a", type=int, default=60)
    ap.add_argument("--deals-b", type=int, default=60)
    ap.add_argument("--stride", type=int, default=4)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--out", default="results/p46_belief_grid.json")
    ap.add_argument("--smoke", action="store_true",
                    help="1 deal per block, three cells, 720 draws only; "
                         "for tests, never for a result")
    a = ap.parse_args(argv)
    cells, budgets = CELLS, BUDGETS
    deals_a, deals_b = a.deals_a, a.deals_b
    if a.smoke:
        cells, budgets = SMOKE_CELLS, SMOKE_BUDGETS
        deals_a, deals_b = 1, 1
        if a.out == "results/p46_belief_grid.json":
            print("--smoke refuses to write the registered output path; "
                  "pass --out", file=sys.stderr)
            return 2
    out = Path(a.out)
    if not out.is_absolute():
        out = ROOT / out
    run(deals_a, deals_b, a.stride, a.jobs, cells, budgets, out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
