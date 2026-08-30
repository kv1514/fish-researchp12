"""Is the DECLARATION taken at the right moment? One-step regret, with claims
in the action set.

THE GAP THIS FILLS
------------------
`scripts4/ask_regret.py` measures one-step regret over the legal asks and
throws away every position where the policy chose to declare:

    if not isinstance(chosen, Ask):
        continue            # a claim: decided from the posterior, not searched

That is honest and it is also a hole. The declaration channel is worth +1.08
sets a game to a teammate oracle on its own (prereg/declaration_timing.md), it
carries 62 of the 63 wrong declarations in the ledger, and no instrument in this
project has ever priced the CHOICE to declare against the alternative of asking.

This runs the identical cross-fitted estimator over an action set that contains
both. `crossfit_regret` is already action-agnostic, and `_rollout` applies
whatever action it is handed and returns None if the engine refuses it, so a
Claim needs no special case: in worlds where the split is wrong the rollout
scores it as the loss it is, and the average over worlds is exactly the price of
declaring on this belief.

WHAT COMES OUT, AND WHY IT IS TWO NUMBERS AND NOT ONE
-----------------------------------------------------
Split by what the policy actually did:

* **it asked** -- regret says what declaring instead would have been worth.
  Positive means we are too slow, which is the direction the teammate oracle's
  move index (39.2 against our 70.6) has been pointing at all session.
* **it declared** -- regret says what asking instead would have been worth.
  Positive means we are too eager, which is the direction the 0.1313 wrong
  declarations a game point at.

They are different errors with opposite cures and a single averaged regret
would cancel them against each other.

Set ASK_REGRET_SPEC=champion to measure V06_DEPLOYED rather than the ask
objective in isolation. The run prints which.

    py scripts4/declare_regret.py [n_positions] [n_worlds] [out.json] [n_games]
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, team_of
from fish.beliefs import BeliefState
from fish.engine import Ask, Claim
from fish.observation import Observation
from fish4.askfeat import DecisionContext
from fish4.claim4 import ClaimConfig, ClaimEvaluator
from fish4.posterior import Posterior
from fish4.registry4 import make_agent
from scripts4.ask_regret import (GAMMA, SPEC, _legal_asks, _rollout,
                                 crossfit_regret, harvest)


def measure(n_positions: int, n_worlds: int, min_resolved: int = 5,
            seed0: int = 6161, n_games: int = 0):
    positions = harvest(n_games or max(60, n_positions // 2), min_resolved,
                        n_positions)
    rows, t0 = [], time.time()
    for pi, (rules, hands, sw, turn, hist, seat) in enumerate(positions):
        obs = Observation(player=seat, rules=rules, hand=hands[seat], turn=turn,
                          hand_counts=tuple(h.bit_count() for h in hands),
                          set_winner=tuple(sw), history=tuple(hist))
        bel = BeliefState(rules, observer=seat)
        bel.update(obs)
        post = Posterior(bel, random.Random(seed0 + pi), n_draws=160,
                         n_worlds=n_worlds, obs=obs, gamma=GAMMA)
        worlds = post.worlds()
        if len(worlds) < 4:
            continue

        actions = list(_legal_asks(obs))
        try:
            cands = ClaimEvaluator(DecisionContext(obs, bel, post),
                                   ClaimConfig()).candidates()
        except Exception:
            cands = []
        claims = [r[2] for r in cands]
        actions += claims
        if len(actions) < 2 or not claims:
            continue            # nothing to declare: not this instrument's case

        agent = make_agent(("fishbot4", SPEC))
        agent.begin_game(seat, rules, seed0 + pi)
        chosen = agent.act(obs)
        if chosen not in actions:
            actions.append(chosen)

        nw = len(worlds)
        seeds = [[(seed0 + 7919 * pi + 31 * wi + p) for p in range(NUM_PLAYERS)]
                 for wi in range(nw)]
        per, illegal = {}, 0
        for a in actions:
            vals = []
            for wi, w in enumerate(worlds):
                v = _rollout(rules, w, turn, sw, hist, a, seat, seeds[wi])
                if v is None:
                    illegal += 1
                vals.append(np.nan if v is None else float(v))
            if not np.all(np.isnan(vals)):
                per[a] = np.asarray(vals, dtype=np.float64)
        if chosen not in per or len(per) < 2:
            continue

        q_all, naive, xf = crossfit_regret(per, chosen)
        if xf is None:
            continue
        # The two decisive sub-questions, each read off the same rollouts.
        qa = [q_all[a] for a in per if isinstance(a, Ask)
              and not np.isnan(q_all[a])]
        qc = [q_all[a] for a in per if isinstance(a, Claim)
              and not np.isnan(q_all[a])]
        rows.append({
            "position": pi, "seat": seat, "n_actions": len(per),
            "n_claims": sum(1 for a in per if isinstance(a, Claim)),
            "chose_claim": int(isinstance(chosen, Claim)),
            "regret": xf, "naive_regret": naive,
            "best_ask": max(qa) if qa else None,
            "best_claim": max(qc) if qc else None,
            "q_chosen": q_all[chosen],
            "illegal_rollouts": illegal})
        c = "CLAIM" if isinstance(chosen, Claim) else "ask  "
        print(f"  pos {pi:3d} chose {c} acts={len(per):3d} "
              f"claims={rows[-1]['n_claims']} regret={xf:+.3f} "
              f"[{time.time()-t0:.0f}s]", flush=True)
    return rows


def _ci(x):
    x = np.asarray([v for v in x if v is not None and not np.isnan(v)],
                   dtype=float)
    if len(x) < 2:
        return float("nan"), float("nan"), len(x)
    return float(x.mean()), float(1.96 * x.std(ddof=1) / len(x) ** 0.5), len(x)


def main(argv):
    import os
    n_positions = int(argv[0]) if argv else 60
    n_worlds = int(argv[1]) if len(argv) > 1 else 16
    dest = Path(argv[2]) if len(argv) > 2 else (
        ROOT / "results" / "declare_regret.json")
    n_games = int(argv[3]) if len(argv) > 3 else 0
    which = ("V06_DEPLOYED (champion)"
             if os.environ.get("ASK_REGRET_SPEC", "").lower() == "champion"
             else "the ask objective in isolation, no lookahead, 160 draws")
    print(f"declaration regret | {n_positions} positions | {n_worlds} worlds\n"
          f"POLICY MEASURED: {which}\n  {SPEC}\n")
    rows = measure(n_positions, n_worlds, n_games=n_games)
    if not rows:
        print("no usable positions")
        return
    print("\n" + "=" * 74)
    print(f"  DECLARATION REGRET, {len(rows)} positions where a claim was")
    print("  available. Positive regret = the policy left value on the table.")
    print("=" * 74)
    out = {"n": len(rows), "spec": SPEC, "n_worlds": n_worlds, "arms": {}}
    print(f"\n  {'what the policy did':<26}{'n':>6}{'regret':>12}{'+/-':>9}")
    for label, sel in (("all positions", rows),
                       ("it ASKED (declare instead?)",
                        [r for r in rows if not r["chose_claim"]]),
                       ("it DECLARED (ask instead?)",
                        [r for r in rows if r["chose_claim"]])):
        m, h, n = _ci([r["regret"] for r in sel])
        print(f"  {label:<26}{n:>6}{m:>+12.4f}{h:>9.4f}")
        out["arms"][label] = {"n": n, "regret": m, "half_width": h}
    # The direct comparison, free from the same rollouts: on positions where
    # the policy asked, how did the best available CLAIM score against the best
    # available ASK? This is the declaration-timing question with no estimator
    # in the way.
    asked = [r for r in rows if not r["chose_claim"]
             and r["best_claim"] is not None and r["best_ask"] is not None]
    if asked:
        d = [r["best_claim"] - r["best_ask"] for r in asked]
        m, h, n = _ci(d)
        print(f"\n  where the policy ASKED, best claim minus best ask:")
        print(f"    {m:+.4f} +/- {h:.4f} over {n} positions")
        print("    positive would mean a declaration was there and was passed")
        print("    over, which is the direction the teammate oracle's move")
        print("    index (39.2 against our 70.6) has pointed at all session.")
        out["best_claim_minus_best_ask_when_asked"] = {
            "mean": m, "half_width": h, "n": n}
    dest.write_text(json.dumps(out | {"rows": rows}, indent=1))
    print("\nwrote", dest)


if __name__ == "__main__":
    main(sys.argv[1:])
