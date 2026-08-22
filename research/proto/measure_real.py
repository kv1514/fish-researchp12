"""Measure the exact-counting prototype on real belief states from real games.

Three questions:
 1. How expensive is the exact DP at real positions?
 2. How often does an exactly-uniform draw (ignoring OR constraints) satisfy
    all the OR constraints? That is the acceptance rate of the rejection
    scheme that would make sampling exactly uniform over the FULL constraint
    set.
 3. How biased is the v0.3 sampler? Compare its marginals against the exact
    ones on positions with no active OR constraints, where the exact answer
    is available in closed form.
"""

from __future__ import annotations

import random
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np

from counting_proto import GroupSystem, Infeasible, NUM_PLAYERS

from fish.agents import AGENT_REGISTRY
from fish.beliefs import BeliefState
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig


def extract_system(bel: BeliefState):
    """Build the group system for the free (unpinned) cards of a belief state."""
    quotas = [bel.per] * NUM_PLAYERS
    free = []
    for c in range(bel.n):
        cand = bel.candidates[c]
        if cand & (cand - 1) == 0:
            quotas[cand.bit_length() - 1] -= 1
        else:
            free.append(c)
    order: dict[int, int] = {}
    masks: list[int] = []
    sizes: list[int] = []
    card_group = {}
    for c in free:
        m = bel.candidates[c]
        if m not in order:
            order[m] = len(masks)
            masks.append(m)
            sizes.append(0)
        gi = order[m]
        sizes[gi] += 1
        card_group[c] = gi
    if not masks:
        return None, {}, quotas, free
    return GroupSystem(masks, sizes, quotas), card_group, quotas, free


def sample_world_from_counts(sysm, card_group, free, k, rng):
    """Turn a group-count matrix into an initial-owner assignment."""
    by_group: dict[int, list[int]] = {}
    for c in free:
        by_group.setdefault(card_group[c], []).append(c)
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


def or_satisfied(bel, deal):
    for cards, p in bel.ors:
        ok = False
        for c in cards:
            owner = deal.get(c)
            if owner is None:
                # pinned card
                cand = bel.candidates[c]
                if cand & (cand - 1) == 0 and cand.bit_length() - 1 == p:
                    ok = True
                    break
            elif owner == p:
                ok = True
                break
        if not ok:
            return False
    return True


def main(n_games=6, agent="tuned", agent_kw=None):
    agent_kw = agent_kw or {"w_turn": 0.6, "w_scarce": 0.2}
    rules = RuleConfig()
    dp_times, sizes_seen, states, accept_rates = [], [], 0, []
    bias_linf, bias_l1, bias_rms = [], [], []
    v03_times, exact_sample_times = [], []
    rng = random.Random(12345)

    for g in range(n_games):
        agents = [AGENT_REGISTRY[agent](**agent_kw) for _ in range(6)]
        ar = random.Random(700 + g)
        st = GameState.deal(rules, seed=400 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        bels = [BeliefState(rules, observer=p) for p in range(6)]
        n = 0
        while not st.is_terminal and n < 400:
            p = st.turn
            for q in range(6):
                bels[q].update(Observation.from_state(st, q))
            bel = bels[p]
            sysm, card_group, quotas, free = extract_system(bel)
            if sysm is not None and sysm.G > 0 and sum(sysm.sizes) > 0:
                states += 1
                try:
                    t0 = time.perf_counter()
                    sysm.forward()
                    sysm.backward()
                    E = sysm.expected_counts()
                    dp_times.append(time.perf_counter() - t0)
                    prod = 1
                    for s in sysm.sizes:
                        prod *= s + 1
                    sizes_seen.append(prod)

                    # -- OR acceptance rate under exact-uniform proposal
                    if bel.ors:
                        ok = 0
                        T = 60
                        for _ in range(T):
                            k = sysm.sample_counts(rng)
                            deal = sample_world_from_counts(
                                sysm, card_group, free, k, rng)
                            if or_satisfied(bel, deal):
                                ok += 1
                        accept_rates.append(ok / T)
                    else:
                        accept_rates.append(1.0)

                    # -- bias of the v0.3 sampler, OR-free positions only
                    if not bel.ors and len(free) >= 3:
                        exact = np.zeros((bel.n, NUM_PLAYERS))
                        for c in free:
                            gi = card_group[c]
                            for pl in range(NUM_PLAYERS):
                                exact[c, pl] = E[gi, pl] / sysm.sizes[gi]
                        NS = 4000
                        emp = np.zeros((bel.n, NUM_PLAYERS))
                        t0 = time.perf_counter()
                        for _ in range(NS):
                            d = bel._sample_initial(rng)
                            for c in free:
                                emp[c, d[c]] += 1
                        v03_times.append((time.perf_counter() - t0) / NS)
                        emp /= NS
                        diff = np.abs(emp[free] - exact[free])
                        bias_linf.append(float(diff.max()))
                        bias_l1.append(float(diff.sum(axis=1).mean()))
                        bias_rms.append(float(np.sqrt((diff ** 2).mean())))

                    # -- exact sampler cost
                    t0 = time.perf_counter()
                    for _ in range(40):
                        sysm.sample_counts(rng)
                    exact_sample_times.append((time.perf_counter() - t0) / 40)
                except Infeasible as e:
                    print("  INFEASIBLE:", e)
            st.apply(p, agents[p].act(Observation.from_state(st, p)))
            n += 1

    def rep(name, xs, scale=1.0, unit=""):
        if not xs:
            print(f"{name:34s} (no data)")
            return
        xs = sorted(x * scale for x in xs)
        print(f"{name:34s} n={len(xs):5d} mean={statistics.mean(xs):9.3f}{unit} "
              f"med={xs[len(xs)//2]:9.3f} p90={xs[int(.9*len(xs))]:9.3f} "
              f"max={xs[-1]:10.3f}")

    print(f"\nStates measured: {states}")
    rep("DP time (fwd+bwd+marginals)", dp_times, 1e3, "ms")
    rep("DP state-space product", sizes_seen)
    rep("exact-uniform draw", exact_sample_times, 1e6, "us")
    rep("v0.3 draw", v03_times, 1e6, "us")
    rep("OR acceptance rate", accept_rates)
    print()
    rep("v0.3 bias  Linf (per card)", bias_linf)
    rep("v0.3 bias  L1  (per card)", bias_l1)
    rep("v0.3 bias  RMS", bias_rms)
    frac = sum(1 for a in accept_rates if a < 0.05) / max(1, len(accept_rates))
    print(f"\nfraction of positions with OR acceptance < 5%: {frac:.3f}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 6)
