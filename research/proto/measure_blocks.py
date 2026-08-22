"""Can the OR constraints be folded into the exact DP?

Idea: refine the mask-groups by OR-membership signature. Cards sharing both a
candidate mask AND the same set of OR constraints containing them are still
exchangeable, so the group-count DP still applies - and now each OR
("player p held at least one card of set O") becomes a purely local condition
on player p's step: p must take at least one card from the blocks inside O.

Tractability then depends on
  (a) prod over blocks of (block size + 1)   -- the DP state space, and
  (b) max ORs owned by a single player       -- an extra 2^m local state.

This script measures both on real positions.
"""

from __future__ import annotations

import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fish.agents import AGENT_REGISTRY
from fish.beliefs import BeliefState
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig

NUM_PLAYERS = 6


def block_structure(bel: BeliefState):
    quotas = [bel.per] * NUM_PLAYERS
    free = []
    for c in range(bel.n):
        cand = bel.candidates[c]
        if cand & (cand - 1) == 0:
            quotas[cand.bit_length() - 1] -= 1
        else:
            free.append(c)
    # OR membership signature per free card
    sig = {c: 0 for c in free}
    live_ors = []
    for i, (cards, p) in enumerate(bel.ors):
        live = [c for c in cards if c in sig]
        if not live:
            continue
        live_ors.append((live, p, len(live_ors)))
    for live, p, idx in live_ors:
        for c in live:
            sig[c] |= 1 << idx
    key = {}
    sizes = []
    for c in free:
        k = (bel.candidates[c], sig[c])
        if k not in key:
            key[k] = len(sizes)
            sizes.append(0)
        sizes[key[k]] += 1
    prod_plain = 1
    plain = {}
    for c in free:
        plain[bel.candidates[c]] = plain.get(bel.candidates[c], 0) + 1
    for v in plain.values():
        prod_plain *= v + 1
    prod_ref = 1
    for v in sizes:
        prod_ref *= v + 1
    per_player = [0] * NUM_PLAYERS
    for live, p, idx in live_ors:
        per_player[p] += 1
    return (len(free), len(plain), prod_plain, len(sizes), prod_ref,
            len(live_ors), max(per_player) if live_ors else 0)


def main(n_games=4):
    rules = RuleConfig()
    rows = []
    for g in range(n_games):
        agents = [AGENT_REGISTRY["tuned"](w_turn=0.6, w_scarce=0.2)
                  for _ in range(6)]
        ar = random.Random(900 + g)
        st = GameState.deal(rules, seed=600 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        bels = [BeliefState(rules, observer=p) for p in range(6)]
        n = 0
        while not st.is_terminal and n < 400:
            p = st.turn
            for q in range(6):
                bels[q].update(Observation.from_state(st, q))
            rows.append(block_structure(bels[p]))
            st.apply(p, agents[p].act(Observation.from_state(st, p)))
            n += 1

    names = ["free cards", "plain groups", "plain state prod",
             "refined blocks", "refined state prod", "live ORs",
             "max ORs / player"]
    print(f"\nStates: {len(rows)}")
    for i, name in enumerate(names):
        xs = sorted(r[i] for r in rows)
        print(f"{name:22s} mean={statistics.mean(xs):11.1f} "
              f"med={xs[len(xs)//2]:9.0f} p90={xs[int(.9*len(xs))]:11.0f} "
              f"p99={xs[int(.99*len(xs))]:12.0f} max={xs[-1]:13.0f}")
    over = sum(1 for r in rows if r[4] > 200_000) / len(rows)
    print(f"\nfraction with refined state product > 200k: {over:.4f}")
    over2 = sum(1 for r in rows if r[4] > 2_000_000) / len(rows)
    print(f"fraction with refined state product > 2M:   {over2:.4f}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 4)
