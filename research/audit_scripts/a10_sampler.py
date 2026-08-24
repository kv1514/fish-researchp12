"""A10: BeliefState sampler checks.

(1) every sampled world replays against the public history (independent
    validator) and reproduces the PUBLIC hand counts;
(2) how far from uniform is the sampler over the consistent set? (the module
    documents "not uniform"; this measures the size of the distortion);
(3) how often does the sampler fail outright in real play?
"""
import sys
import random
import itertools
from collections import Counter

sys.path.insert(0, r"C:\Users\vel_k\Documents\fish-engine")
from fish.rules import RuleConfig
from fish.engine import GameState
from fish.observation import Observation
from fish.beliefs import (BeliefState, BeliefContradiction,
                          validate_deal_against_history)
from fish.agents import AGENT_REGISTRY

RULES = RuleConfig()
N, PER, NP = 54, 9, 6


def hdr(t):
    print()
    print("=" * 72)
    print(t)
    print("=" * 72)
    sys.stdout.flush()


hdr("1. sampled worlds: replay-valid and count-consistent?")
bad_replay = bad_counts = 0
worlds = 0
fails = 0
for g in range(8):
    state = GameState.deal(RULES, seed=300 + g)
    agents = [AGENT_REGISTRY["probabilistic"]() for _ in range(6)]
    rng = random.Random(g)
    for p, a in enumerate(agents):
        a.begin_game(p, RULES, rng.getrandbits(64))
    bels = [BeliefState(RULES, observer=p) for p in range(6)]
    srng = random.Random(4242 + g)
    ply = 0
    while not state.is_terminal and ply < 160:
        for seat in range(6):
            obs = Observation.from_state(state, seat)
            bels[seat].update(obs)
            if ply % 5 == 0:
                for _ in range(4):
                    try:
                        deal = bels[seat]._sample_initial(srng)
                    except BeliefContradiction:
                        fails += 1
                        continue
                    worlds += 1
                    init = [0] * NP
                    for c in range(N):
                        init[deal[c]] |= 1 << c
                    if not validate_deal_against_history(
                            RULES, init, tuple(state.history)):
                        bad_replay += 1
                    # current hands implied by that same initial deal
                    cur = [0] * NP
                    for c in range(N):
                        loc = bels[seat].public_loc[c]
                        if loc == -2:
                            continue
                        cur[deal[c] if loc is None else loc] |= 1 << c
                    if tuple(h.bit_count() for h in cur) != tuple(obs.hand_counts):
                        bad_counts += 1
                    if cur[seat] != obs.hand:
                        bad_counts += 1000
        p = state.turn
        state.apply(p, agents[p].act(Observation.from_state(state, p)))
        ply += 1
print("  worlds sampled:", worlds, " sampler failures:", fails)
print("  count-inconsistent worlds:", bad_counts)
print("  replay-invalid implied deals:", bad_replay)

hdr("2. how non-uniform is the sampler? (exact reference by enumeration)")


def build(rng, k_free, n_ors):
    true_deal = []
    for p in range(NP):
        true_deal += [p] * PER
    rng.shuffle(true_deal)
    free = rng.sample(range(N), k_free)
    cand = [1 << true_deal[c] for c in range(N)]
    for c in free:
        m = 1 << true_deal[c]
        for e in rng.sample([x for x in range(NP) if x != true_deal[c]], 2):
            m |= 1 << e
        cand[c] = m
    ors = []
    for _ in range(n_ors):
        p = rng.randrange(NP)
        anchor = rng.choice([c for c in range(N) if true_deal[c] == p])
        pool = [c for c in free if cand[c] & (1 << p) and c != anchor]
        if len(pool) < 2:
            continue
        ors.append((tuple(sorted([anchor] + rng.sample(pool, 2))), p))
    return true_deal, free, cand, ors


def enumerate_solutions(free, cand, ors, pinned):
    fs = set(free)
    quota = [PER] * NP
    for c in range(N):
        if c not in fs:
            quota[pinned[c]] -= 1
    idx = {c: i for i, c in enumerate(free)}
    doms = [[p for p in range(NP) if cand[c] & (1 << p)] for c in free]
    out = []
    for combo in itertools.product(*doms):
        q = quota[:]
        bad = False
        for p in combo:
            q[p] -= 1
            if q[p] < 0:
                bad = True
                break
        if bad or any(q):
            continue
        if all(any((combo[idx[c]] if c in idx else pinned[c]) == p for c in grp)
               for grp, p in ors):
            out.append(combo)
    return out


rng = random.Random(0)
worst = 0.0
for trial in range(6):
    true_deal, free, cand, ors = build(rng, 6, rng.randint(0, 2))
    bel = BeliefState(RULES, observer=None)
    bel.candidates = list(cand)
    bel.ors = list(ors)
    try:
        bel._propagate()
    except BeliefContradiction:
        continue
    sols = enumerate_solutions(free, bel.candidates, bel.ors, true_deal)
    if len(sols) < 3:
        continue
    uniform = 1.0 / len(sols)
    srng = random.Random(7)
    counts = Counter()
    NS = 20000
    for _ in range(NS):
        deal = bel._sample_initial(srng)
        counts[tuple(deal[c] for c in free)] += 1
    emp = {k: v / NS for k, v in counts.items()}
    unseen = [s for s in sols if s not in emp]
    extra = [k for k in emp if k not in set(sols)]
    ratios = sorted(emp.get(s, 0.0) / uniform for s in sols)
    worst = max(worst, ratios[-1] / max(ratios[0], 1e-9))
    print("  trial %d: %d consistent worlds, %d never sampled, "
          "%d sampled-but-inconsistent, p/uniform in [%.2f, %.2f]"
          % (trial, len(sols), len(unseen), len(extra), ratios[0], ratios[-1]))
print("  worst max/min sampling-probability ratio seen: %.1fx" % worst)
