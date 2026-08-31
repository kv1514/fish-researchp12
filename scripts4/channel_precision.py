"""Does the channel's value shrink as the belief it decodes into gets better?

Registered in full at ``prereg/channel_vs_precision.md`` before this file
existed. The grid, the sample size, the statistic and the decision rule are
fixed there and nothing here is free to choose them.

WHY. Re-running the aimed code book today gave a paired NLL of -0.0403 where
-0.0712 was recorded two days earlier on identical seeds, while the BASELINE
teammate NLL improved from 1.3995 to 1.3567. I explained that in three files
as "a message is worth only what the receiver could not already work out" --
from two points, on two engines, eleven commits apart. That is the same shape
as the aimed book's own retracted "neutral" reading, so it gets measured.

WHAT IS SWEPT, AND WHAT IS NOT. The manipulation is the SCORING posterior's
``n_draws`` on fixed transcripts: a lower-variance belief on the same
positions, with the model unchanged. The drift that prompted the question was a
MODEL improvement, not more draws, so this is a nearby axis and not the same
one. The registration says so; this says so; a result here does not confirm the
drift explanation.

THE STATISTIC. The cells score the SAME decisions, so the cross-cell comparison
is paired per decision rather than two intervals compared by eye:

    d_c(i) = NLL_arm(i) - NLL_base(i)     within cell c, negative when it helps
    D(i)   = d_1440(i) - d_180(i)         clustered on the GAME

Gains are negative, so D > 0 is shrinkage -- the direction the claim predicts.

WHAT IT INHERITS. ``Pool``, ``paired_by_game`` and ``true_holder_map`` are
imported from ``scripts4/unlocated_belief.py`` rather than copied, so the two
instruments cannot come to disagree about what an NLL is or what unit an
interval is over. Both cluster on the game through ``fish4.clustered``.

The transcript loop, the card selection and the per-decision RNG seed are
mirrored EXACTLY from ``scripts4/convention_posterior.py``, because the 720
cell has to reproduce a number that instrument already published. Any drift
between the two shows up as the anchor failing, which voids the run.

V1/V2/V3 are not recomputed. They are properties of the transcripts, and the
transcripts here are the ones ``results/convention_replication.json`` already
reports them for.

Usage: python scripts4/channel_precision.py [n_games] [stride] [out.json]
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts4"))

from fish.beliefs import BeliefState                        # noqa: E402
from fish.cards import NUM_PLAYERS                          # noqa: E402
from fish.engine import Ask, GameState                      # noqa: E402
from fish.observation import Observation                    # noqa: E402
from fish.rules import RuleConfig                           # noqa: E402
from fish4.clustered import cluster_ci                      # noqa: E402
from fish4.posterior import Posterior                       # noqa: E402
from fish4.registry4 import V06_DEPLOYED, make_agent        # noqa: E402

from unlocated_belief import (MIN_CLUSTERS, Pool,           # noqa: E402
                              paired_by_game, true_holder_map)

RULES = RuleConfig(wrong_distribution_outcome="opponent")

#: Fixed by prereg/channel_vs_precision.md.
GRID = (180, 360, 720, 1440)
SENDER_GATE = 0.05
BETA = 0.8
SEED_BASE = 880_000

#: The 720 cell is an ANCHOR, not a data point. It has to reproduce
#: results/convention_replication.json's paired NLL for `0.05 aimed`,
#: `flat 0.8`. If it does not, this instrument is measuring something other
#: than the one that produced that figure, and the run is void.
ANCHOR_DRAWS = 720
ANCHOR_NLL = -0.0382
ANCHOR_TOL = 0.010

BASE = "base"
ARM = f"flat {BETA}"


def transcripts_and_scores(n_games: int, stride: int):
    """Play the aimed sender once; score every cell on the same decisions."""
    spec = dict(V06_DEPLOYED[1])
    spec["convention_max_cost"] = SENDER_GATE
    spec["convention_aim"] = True
    spec["convention_book"] = "depth"
    # The decoder is OFF while the games are played. That is what makes the
    # cells comparable: they all score the same positions.
    spec["convention_beta"] = 0.0

    # kw per arm, mirroring convention_posterior.arms_for("aimed"): the
    # baseline carries NO convention keys at all, not `beta = 0`.
    ARMS = ((BASE, {}), (ARM, {"convention_beta": BETA,
                               "convention_aim": True}))

    team = {(n, a): Pool() for n in GRID for a, _ in ARMS}
    opp = {(n, a): Pool() for n in GRID for a, _ in ARMS}
    decisions = 0
    our_asks = 0
    t0 = time.perf_counter()

    for g in range(n_games):
        agents = [make_agent(("kraken", dict(spec)))
                  for _ in range(NUM_PLAYERS)]
        st = GameState.deal(RULES, seed=SEED_BASE + g)
        for p, a in enumerate(agents):
            a.begin_game(p, RULES, SEED_BASE + 10_000 + g * 13 + p)
        bels = [BeliefState(RULES, observer=p) for p in range(NUM_PLAYERS)]
        step = 0
        while not st.is_terminal and step < 400:
            mover = st.turn
            for q in range(NUM_PLAYERS):
                bels[q].update(Observation.from_state(st, q))
            obs = Observation.from_state(st, mover)
            bel = bels[mover]

            if step % stride == 0:
                truth = true_holder_map(st)
                unpinned = [c for c in range(bel.n)
                            if bel.public_loc[c] is None
                            and bel.candidates[c].bit_count() > 1]
                t_cards = [c for c in unpinned
                           if truth[c] % 2 == mover % 2 and truth[c] != mover]
                o_cards = [c for c in unpinned if truth[c] % 2 != mover % 2]
                if t_cards or o_cards:
                    decisions += 1
                    for n_draws in GRID:
                        for label, kw in ARMS:
                            # One seed per DECISION, shared by every arm and
                            # every cell, so a difference is the model or the
                            # draw count and never the stream. Nested by
                            # construction: the 180-draw cell's draws are the
                            # first 180 of the 1440-draw cell's.
                            rng = random.Random(6_400_000 + 977 * decisions)
                            M = Posterior(bel, rng, n_draws=n_draws, obs=obs,
                                          gamma=spec["opponent_gamma"],
                                          **kw).marginals()
                            if t_cards:
                                team[(n_draws, label)].add(
                                    M, truth, t_cards, g, decisions)
                            if o_cards:
                                opp[(n_draws, label)].add(
                                    M, truth, o_cards, g, decisions)

            act = agents[mover].act(obs)
            if isinstance(act, Ask) and (act.target % 2) != (mover % 2):
                our_asks += 1
            st.apply(mover, act)
            step += 1
        print(f"  game {g + 1}/{n_games}: {decisions} decisions, "
              f"{time.perf_counter() - t0:.0f}s", file=sys.stderr, flush=True)

    return team, opp, decisions, our_asks


def contrast(team: dict, hi: int, lo: int) -> dict | None:
    """D(i) = d_hi(i) - d_lo(i), clustered on the game.

    Positive means the arm's advantage over its baseline is SMALLER at ``hi``
    draws than at ``lo`` -- the shrinkage the registration predicts.
    """
    def deltas(n):
        b = {(g, d): nll for g, d, nll, _, _ in team[(n, BASE)].rows}
        return {(g, d): nll - b[(g, d)]
                for g, d, nll, _, _ in team[(n, ARM)].rows if (g, d) in b}

    dhi, dlo = deltas(hi), deltas(lo)
    keys = sorted(set(dhi) & set(dlo))
    if len(keys) < 2:
        return None
    games = [k[0] for k in keys]
    xs = [dhi[k] - dlo[k] for k in keys]
    mu, half, k = cluster_ci(xs, games)
    withheld = k < MIN_CLUSTERS
    return {"mean": mu,
            "lo": None if (half is None or withheld) else mu - half,
            "hi": None if (half is None or withheld) else mu + half,
            "n_clusters": k, "n_decisions": len(xs),
            "interval_withheld": withheld}


def main(n_games: int = 40, stride: int = 4, out: str | None = None) -> int:
    team, opp, decisions, our_asks = transcripts_and_scores(n_games, stride)

    cells = []
    for n in GRID:
        pt = paired_by_game(team[(n, ARM)], team[(n, BASE)])
        po = paired_by_game(opp[(n, ARM)], opp[(n, BASE)])
        cells.append({
            "n_draws": n,
            "base_team_nll": team[(n, BASE)].mean(2),
            "base_team_top1": team[(n, BASE)].mean(3),
            "arm_team_nll": team[(n, ARM)].mean(2),
            "paired_team": pt, "paired_opp": po,
        })

    D = contrast(team, GRID[-1], GRID[0])

    print(f"\n=== {decisions} scored decisions, {n_games} games, "
          f"seed base {SEED_BASE} ===\n")
    print(f"  {'n_draws':>8} {'base team NLL':>14} {'paired NLL (95%)':>30}")
    for c in cells:
        p = c["paired_team"]
        if p is None:
            print(f"  {c['n_draws']:>8} {c['base_team_nll']:>14.4f} "
                  f"{'-- no pairing --':>30}")
            continue
        n = p["nll"]
        iv = ("interval withheld" if n["lo"] is None
              else f"[{n['lo']:+.4f},{n['hi']:+.4f}]")
        print(f"  {c['n_draws']:>8} {c['base_team_nll']:>14.4f} "
              f"{n['mean']:+.4f} {iv:>21}")

    # --- the two pre-registered conditions ------------------------------
    bases = [c["base_team_nll"] for c in cells]
    monotone = all(bases[i] > bases[i + 1] for i in range(len(bases) - 1))
    print(f"\n  condition 1, baseline NLL falls across the grid: "
          f"{'YES' if monotone else 'NO'}   "
          f"({' -> '.join(f'{b:.4f}' for b in bases)})")

    anchor = next(c for c in cells if c["n_draws"] == ANCHOR_DRAWS)
    a = anchor["paired_team"]["nll"]["mean"]
    ok = abs(a - ANCHOR_NLL) <= ANCHOR_TOL
    print(f"  anchor, {ANCHOR_DRAWS} draws reproduces {ANCHOR_NLL:+.4f} "
          f"to within {ANCHOR_TOL}: {'YES' if ok else 'NO -- RUN IS VOID'} "
          f"(measured {a:+.4f}, off by {abs(a - ANCHOR_NLL):.4f})")

    if D is None:
        print("  contrast: not computable")
        verdict = "UNRESOLVED"
    else:
        iv = ("interval withheld" if D["lo"] is None
              else f"[{D['lo']:+.4f},{D['hi']:+.4f}]")
        print(f"\n  D = d_{GRID[-1]} - d_{GRID[0]}  =  {D['mean']:+.4f} {iv}"
              f"   k={D['n_clusters']} games, {D['n_decisions']} decisions")
        if not ok:
            verdict = "VOID"
        elif D["lo"] is None:
            verdict = "UNRESOLVED"
        elif D["lo"] > 0:
            verdict = "SUPPORTED" if monotone else "UNRESOLVED"
        elif D["hi"] < 0:
            verdict = "REFUTED"
        else:
            verdict = "UNRESOLVED"
    print(f"\n  VERDICT: {verdict}   "
          "(prereg/channel_vs_precision.md fixed these in advance)")

    payload = {
        "prereg": "prereg/channel_vs_precision.md",
        "n_games": n_games, "stride": stride, "seed_base": SEED_BASE,
        "grid": list(GRID), "beta": BETA, "sender_gate": SENDER_GATE,
        "decisions": decisions, "our_asks": our_asks,
        "cells": cells, "contrast": D,
        "condition_1_baseline_monotone": monotone,
        "anchor": {"n_draws": ANCHOR_DRAWS, "expected": ANCHOR_NLL,
                   "tolerance": ANCHOR_TOL, "measured": a, "passed": ok},
        "verdict": verdict,
        "spec": V06_DEPLOYED[1],
        # Every per-decision row, with its game, so the contrast above can be
        # recomputed on a different unit without re-running anything. This is
        # the field results/gamma_split.json does not have.
        "per_decision": {
            f"{n}:{label}": [list(r) for r in team[(n, label)].rows]
            for n in GRID for label in (BASE, ARM)},
    }
    path = Path(out) if out else ROOT / "results" / "channel_precision.json"
    path.write_text(json.dumps(payload, indent=1))
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 40,
                          int(a[1]) if len(a) > 1 else 4,
                          a[2] if len(a) > 2 else None))
