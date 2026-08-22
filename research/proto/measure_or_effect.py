"""How much do the OR constraints move the posterior?

The exact DP in fish4/counting.py handles candidate masks and quotas exactly
but ignores the OR constraints ("the asker held at least one card of that
half-suit at the time"). This script measures the size of that omission by
comparing, on real positions:

  A. exact OR-free marginals (closed form, from the DP)
  B. OR-conditioned marginals (exact-uniform draws, rejection-filtered on the
     ORs -- these are exactly uniform over the FULL consistent set)
  C. v0.3's sampler marginals (the incumbent)

all against B as ground truth, on positions where the rejection rate is high
enough for B to be measured precisely.
"""

from __future__ import annotations

import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np

from fish4.counting import GroupSystem, Infeasible, NUM_PLAYERS
from fish.agents import AGENT_REGISTRY
from fish.beliefs import BeliefState
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig


def build(bel):
    quotas = [bel.per] * NUM_PLAYERS
    free = []
    for c in range(bel.n):
        cand = bel.candidates[c]
        if cand & (cand - 1) == 0:
            quotas[cand.bit_length() - 1] -= 1
        else:
            free.append(c)
    if not free:
        return None
    index, masks, sizes, cg = {}, [], [], {}
    for c in free:
        m = bel.candidates[c]
        gi = index.get(m)
        if gi is None:
            gi = index[m] = len(masks)
            masks.append(m)
            sizes.append(0)
        sizes[gi] += 1
        cg[c] = gi
    return GroupSystem(masks, sizes, quotas), cg, free, quotas


def draw_world(sysm, cg, free, rng):
    k = sysm.sample_counts(rng)
    by_group = {}
    for c in free:
        by_group.setdefault(cg[c], []).append(c)
    deal = {}
    for g, cards in by_group.items():
        cards = list(cards)
        rng.shuffle(cards)
        i = 0
        for p in range(NUM_PLAYERS):
            for _ in range(int(k[g, p])):
                deal[cards[i]] = p
                i += 1
    return deal


def ok_ors(bel, deal):
    for cards, p in bel.ors:
        good = False
        for c in cards:
            o = deal.get(c)
            if o is None:
                cand = bel.candidates[c]
                if cand & (cand - 1) == 0 and cand.bit_length() - 1 == p:
                    good = True
                    break
            elif o == p:
                good = True
                break
        if not good:
            return False
    return True


def main(n_games=4, min_accept=0.15, target_accepted=4000):
    rules = RuleConfig()
    rng = random.Random(4242)
    dA, dC, dCbias = [], [], []
    linfA, linfC = [], []
    n_used = 0
    for g in range(n_games):
        agents = [AGENT_REGISTRY["tuned"](w_turn=0.6, w_scarce=0.2) for _ in range(6)]
        ar = random.Random(1100 + g)
        st = GameState.deal(rules, seed=800 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        bels = [BeliefState(rules, observer=p) for p in range(6)]
        n = 0
        while not st.is_terminal and n < 400:
            p = st.turn
            for q in range(6):
                bels[q].update(Observation.from_state(st, q))
            bel = bels[p]
            try:
                built = build(bel)
            except Infeasible:
                built = None
            if built is not None and bel.ors:
                sysm, cg, free, quotas = built
                try:
                    E = sysm.expected_counts()
                    # quick acceptance probe
                    probe = 40
                    hits = sum(1 for _ in range(probe)
                               if ok_ors(bel, draw_world(sysm, cg, free, rng)))
                    if hits / probe >= min_accept:
                        n_used += 1
                        exactA = np.zeros((len(free), NUM_PLAYERS))
                        for i, c in enumerate(free):
                            gi = cg[c]
                            exactA[i] = E[gi] / sysm.sizes[gi]
                        # B: OR-conditioned ground truth
                        accB = np.zeros((len(free), NUM_PLAYERS))
                        got = 0
                        tries = 0
                        while got < target_accepted and tries < target_accepted * 30:
                            tries += 1
                            d = draw_world(sysm, cg, free, rng)
                            if not ok_ors(bel, d):
                                continue
                            got += 1
                            for i, c in enumerate(free):
                                accB[i, d[c]] += 1
                        if got < 500:
                            n = n
                        else:
                            accB /= got
                            # C: v0.3 sampler
                            NS = 4000
                            accC = np.zeros((len(free), NUM_PLAYERS))
                            for _ in range(NS):
                                d = bel._sample_initial(rng)
                                for i, c in enumerate(free):
                                    accC[i, d[c]] += 1
                            accC /= NS
                            dA.append(float(np.abs(exactA - accB).sum(axis=1).mean()))
                            dC.append(float(np.abs(accC - accB).sum(axis=1).mean()))
                            linfA.append(float(np.abs(exactA - accB).max()))
                            linfC.append(float(np.abs(accC - accB).max()))
                except Infeasible:
                    pass
            st.apply(p, agents[p].act(Observation.from_state(st, p)))
            n += 1
            if n_used >= 40:
                break
        if n_used >= 40:
            break

    def rep(name, xs):
        if not xs:
            print(f"{name:44s} (no data)")
            return
        xs = sorted(xs)
        print(f"{name:44s} n={len(xs):4d} mean={statistics.mean(xs):.4f} "
              f"med={xs[len(xs)//2]:.4f} p90={xs[int(.9*len(xs))]:.4f} "
              f"max={xs[-1]:.4f}")

    print(f"\npositions compared: {n_used}")
    rep("L1/card:  OR-free exact  vs OR-truth", dA)
    rep("L1/card:  v0.3 sampler   vs OR-truth", dC)
    rep("Linf:     OR-free exact  vs OR-truth", linfA)
    rep("Linf:     v0.3 sampler   vs OR-truth", linfC)


if __name__ == "__main__":
    main()
