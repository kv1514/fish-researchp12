"""Is "the effect grows with draws" the channel, or the instrument?

Registered in full at ``prereg/precision_generality.md``, written after
``prereg/channel_vs_precision.md`` returned REFUTED and before this file
existed.

WHAT IT IS CHECKING, AND WHOSE CLAIM. The channel sweep found the aimed book's
paired gain growing with sampler draws, and I replaced the refuted explanation
with a second one in three files: the gain "tracks how many sampled worlds the
decoder has to reweight". The duller competitor is that ANY paired difference
between two beliefs grows with draws, because at low precision both marginals
are coarse and there is less room for the arms to differ. The channel sweep
cannot tell those apart. Sweeping an unrelated intervention can.

``w_unlocated = -4.0`` against the incumbent, on the champion's own transcripts
with no convention anywhere: structurally unrelated to a code book, OPPOSITE in
sign (it is a harm), and already refuted today, so there is no arm to protect.

THE ANCHOR IS THE 480 CELL, and it is a real reproduction rather than a
courtesy: ``results/unlocated_belief.json`` was written at exactly that
precision, so this instrument has to land on its +0.0422 or it is measuring
something else and the run is void.

Everything about the transcript loop, the card selection and the per-decision
RNG seed is mirrored from ``scripts4/unlocated_belief.py``, whose ``Pool``,
``paired_by_game`` and ``true_holder_map`` are imported rather than copied.

Usage: python scripts4/precision_generality.py [n_games] [stride] [out.json]
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
from fish.engine import GameState                           # noqa: E402
from fish.observation import Observation                    # noqa: E402
from fish.rules import RuleConfig                           # noqa: E402
from fish4.clustered import cluster_ci                      # noqa: E402
from fish4.posterior import Posterior                       # noqa: E402
from fish4.registry4 import V06_DEPLOYED, make_agent        # noqa: E402

from duel import engine_fingerprint                       # noqa: E402
from unlocated_belief import (MIN_CLUSTERS, Pool,           # noqa: E402
                              paired_by_game, true_holder_map)

RULES = RuleConfig(wrong_distribution_outcome="opponent")

#: Fixed by prereg/precision_generality.md.
DRAWS = (180, 360, 480, 720, 1440)
BASE_W = 0.0
ARM_W = -4.0
SEED_DEAL = 720_000
SEED_AGENT = 730_000

#: results/unlocated_belief.json's w=-4.0 NLL, measured at n_draws=480.
ANCHOR_DRAWS = 480
ANCHOR_NLL = 0.0422
ANCHOR_TOL = 0.010


def sweep(n_games: int, stride: int):
    team = {(n, w): Pool() for n in DRAWS for w in (BASE_W, ARM_W)}
    opp = {(n, w): Pool() for n in DRAWS for w in (BASE_W, ARM_W)}
    decisions = 0
    t0 = time.perf_counter()

    for g in range(n_games):
        # Play is ALWAYS the incumbent, exactly as in unlocated_belief.py.
        agents = [make_agent(("kraken", dict(V06_DEPLOYED[1])))
                  for _ in range(NUM_PLAYERS)]
        st = GameState.deal(RULES, seed=SEED_DEAL + g)
        for p, a in enumerate(agents):
            a.begin_game(p, RULES, SEED_AGENT + g * 13 + p)
        bels = [BeliefState(RULES, observer=p) for p in range(NUM_PLAYERS)]
        step = 0
        while not st.is_terminal and step < 400:
            mover = st.turn
            for q in range(NUM_PLAYERS):
                bels[q].update(Observation.from_state(st, q))
            if step % stride == 0:
                obs = Observation.from_state(st, mover)
                bel = bels[mover]
                truth = true_holder_map(st)
                unpinned = [c for c in range(bel.n)
                            if bel.public_loc[c] is None
                            and bel.candidates[c].bit_count() > 1]
                t_cards = [c for c in unpinned
                           if truth[c] % 2 == mover % 2 and truth[c] != mover]
                o_cards = [c for c in unpinned if truth[c] % 2 != mover % 2]
                if t_cards or o_cards:
                    decisions += 1
                    for n in DRAWS:
                        for w in (BASE_W, ARM_W):
                            # unlocated_belief.py's seed expression, so the
                            # 480 cell can reproduce its number rather than
                            # merely resemble it.
                            rng = random.Random(7_100_000 + 977 * decisions)
                            M = Posterior(bel, rng, n_draws=n, obs=obs,
                                          gamma=0.35,
                                          w_unlocated=w).marginals()
                            team[(n, w)].add(M, truth, t_cards, g, decisions)
                            opp[(n, w)].add(M, truth, o_cards, g, decisions)
            st.apply(mover, agents[mover].act(
                Observation.from_state(st, mover)))
            step += 1
        print(f"  game {g + 1}/{n_games}: {decisions} decisions, "
              f"{time.perf_counter() - t0:.0f}s", file=sys.stderr, flush=True)

    return team, opp, decisions


def contrast(team: dict, hi: int, lo: int) -> dict | None:
    def deltas(n):
        b = {(g, d): nll for g, d, nll, _, _ in team[(n, BASE_W)].rows}
        return {(g, d): nll - b[(g, d)]
                for g, d, nll, _, _ in team[(n, ARM_W)].rows if (g, d) in b}

    dhi, dlo = deltas(hi), deltas(lo)
    keys = sorted(set(dhi) & set(dlo))
    if len(keys) < 2:
        return None
    mu, half, k = cluster_ci([dhi[k_] - dlo[k_] for k_ in keys],
                             [k_[0] for k_ in keys])
    withheld = k < MIN_CLUSTERS
    return {"mean": mu,
            "lo": None if (half is None or withheld) else mu - half,
            "hi": None if (half is None or withheld) else mu + half,
            "n_clusters": k, "n_decisions": len(keys),
            "interval_withheld": withheld}


def main(n_games: int = 40, stride: int = 4, out: str | None = None) -> int:
    team, opp, decisions = sweep(n_games, stride)

    cells = []
    for n in DRAWS:
        cells.append({
            "n_draws": n,
            "base_team_nll": team[(n, BASE_W)].mean(2),
            "paired_team": paired_by_game(team[(n, ARM_W)], team[(n, BASE_W)]),
            "paired_opp": paired_by_game(opp[(n, ARM_W)], opp[(n, BASE_W)]),
        })
    D = contrast(team, DRAWS[-1], DRAWS[0])

    print(f"\n=== {decisions} scored decisions, {n_games} games, "
          f"w_unlocated {ARM_W} vs {BASE_W} ===\n")
    print(f"  {'n_draws':>8} {'base team NLL':>14} "
          f"{'paired NLL (95%), + is HARM':>34}")
    for c in cells:
        p = c["paired_team"]["nll"]
        iv = ("interval withheld" if p["lo"] is None
              else f"[{p['lo']:+.4f},{p['hi']:+.4f}]")
        print(f"  {c['n_draws']:>8} {c['base_team_nll']:>14.4f} "
              f"{p['mean']:+.4f} {iv:>25}")

    a = next(c for c in cells
             if c["n_draws"] == ANCHOR_DRAWS)["paired_team"]["nll"]["mean"]
    ok = abs(a - ANCHOR_NLL) <= ANCHOR_TOL
    print(f"\n  anchor, {ANCHOR_DRAWS} draws reproduces {ANCHOR_NLL:+.4f} "
          f"to within {ANCHOR_TOL}: "
          f"{'YES' if ok else 'NO -- RUN IS VOID'} "
          f"(measured {a:+.4f}, off by {abs(a - ANCHOR_NLL):.4f})")

    if D is None or D["lo"] is None:
        verdict = "VOID" if not ok else "SPECIFIC TO THE CHANNEL"
        print("  contrast: interval unavailable")
    else:
        print(f"  D = d_{DRAWS[-1]} - d_{DRAWS[0]}  =  {D['mean']:+.4f} "
              f"[{D['lo']:+.4f},{D['hi']:+.4f}]   k={D['n_clusters']} games, "
              f"{D['n_decisions']} decisions")
        if not ok:
            verdict = "VOID"
        elif D["lo"] > 0:
            verdict = "INSTRUMENT PROPERTY"
        else:
            # prereg: below zero OR covering zero both count for the
            # channel-specific reading. The asymmetry is deliberate and is
            # the harder assignment for the claim being checked.
            verdict = "SPECIFIC TO THE CHANNEL"
    print(f"\n  VERDICT: {verdict}   "
          "(prereg/precision_generality.md fixed these in advance)")

    payload = {
        "prereg": "prereg/precision_generality.md",
        # THE ENGINE DIGEST, and it is here because its absence cost a day.
        # results/convention_posterior.json stored the spec and not the code.
        # A later run at identical seeds gave a different number, the two
        # specs were byte-identical on all seven keys, and three explanations
        # were written for a change in the world. The change was in the code:
        # 6d75ec4 re-priced convention_max_cost from success probability into
        # the ask objective's units, so one label named two senders. A spec
        # fingerprint compares VALUES and cannot see a field's meaning move.
        # This digest can: 4d7896f938dd before that commit, ca40192a1f3a
        # after. results/convention_drift_bisect.json.
        "engine": engine_fingerprint(),

        "n_games": n_games, "stride": stride, "draws": list(DRAWS),
        "base_w": BASE_W, "arm_w": ARM_W, "decisions": decisions,
        "seed_deal": SEED_DEAL, "seed_agent": SEED_AGENT,
        "cells": cells, "contrast": D,
        "anchor": {"n_draws": ANCHOR_DRAWS, "expected": ANCHOR_NLL,
                   "tolerance": ANCHOR_TOL, "measured": a, "passed": ok},
        "verdict": verdict, "spec": V06_DEPLOYED[1],
        "per_decision": {
            f"{n}:{w}": [list(r) for r in team[(n, w)].rows]
            for n in DRAWS for w in (BASE_W, ARM_W)},
    }
    path = Path(out) if out else ROOT / "results" / "precision_generality.json"
    path.write_text(json.dumps(payload, indent=1))
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 40,
                          int(a[1]) if len(a) > 1 else 4,
                          a[2] if len(a) > 2 else None))
