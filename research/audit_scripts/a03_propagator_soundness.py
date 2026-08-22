"""A03: exhaustive soundness check of BeliefState._propagate /
_propagate_or_pigeonhole against brute-force enumeration.

Method (a genuinely reduced setting): build a random constraint system of the
exact shape the belief engine uses -- per-card candidate sets over 6 initial
owners, exact per-player counts (9 each), and OR constraints "at least one of
these cards was initially p's" -- with most cards HARD PINNED so that only k
cards are free. Then:

  * run the real propagator,
  * enumerate every assignment of the k free cards that satisfies
    (candidates AND exact counts AND all ORs),
  * for every card, the union of owners over enumerated solutions is the
    TRUE support; the propagator's candidate set must be a SUPERSET of it.

Any owner in the true support that the propagator removed is a SOUNDNESS bug.
"""
import sys, random, itertools
sys.path.insert(0, r"C:\Users\vel_k\Documents\fish-engine")
from fish.rules import RuleConfig
from fish.beliefs import BeliefState, BeliefContradiction

RULES = RuleConfig()
N, PER, NP = 54, 9, 6


def build_case(rng, k_free, max_cand, n_ors, or_size):
    true_deal = []
    for p in range(NP):
        true_deal += [p] * PER
    rng.shuffle(true_deal)                       # true_deal[c] = owner of c
    free = rng.sample(range(N), k_free)
    freeset = set(free)
    cand = [1 << true_deal[c] for c in range(N)]
    for c in free:
        others = [p for p in range(NP) if p != true_deal[c]]
        extra = rng.sample(others, rng.randint(1, max_cand - 1))
        m = 1 << true_deal[c]
        for p in extra:
            m |= 1 << p
        cand[c] = m
    ors = []
    for _ in range(n_ors):
        p = rng.randrange(NP)
        # must be satisfied by the true deal: include at least one true p-card
        pcards = [c for c in range(N) if true_deal[c] == p]
        anchor = rng.choice(pcards)
        pool = [c for c in range(N) if c != anchor and cand[c] & (1 << p)]
        if len(pool) < or_size - 1:
            continue
        grp = tuple(sorted([anchor] + rng.sample(pool, or_size - 1)))
        ors.append((grp, p))
    return true_deal, free, cand, ors


def brute_force(free, cand, ors, pinned_owner):
    """All owner-assignments of `free` satisfying candidates+counts+ORs."""
    quota = [PER] * NP
    for c in range(N):
        if c not in set(free):
            quota[pinned_owner[c]] -= 1
    domains = [[p for p in range(NP) if cand[c] & (1 << p)] for c in free]
    support = {c: 0 for c in free}
    sols = 0
    idx = {c: i for i, c in enumerate(free)}

    def ok_ors(assign):
        for grp, p in ors:
            hit = False
            for c in grp:
                o = assign[idx[c]] if c in idx else pinned_owner[c]
                if o == p:
                    hit = True
                    break
            if not hit:
                return False
        return True

    for combo in itertools.product(*domains):
        q = quota[:]
        good = True
        for p in combo:
            q[p] -= 1
            if q[p] < 0:
                good = False
                break
        if not good or any(x != 0 for x in q):
            continue
        if not ok_ors(combo):
            continue
        sols += 1
        for i, c in enumerate(free):
            support[c] |= 1 << combo[i]
    return sols, support


def run(trials=400, k_free=8, seed=0):
    rng = random.Random(seed)
    violations = []
    total_sols = 0
    for t in range(trials):
        true_deal, free, cand, ors = build_case(
            rng, k_free, max_cand=3, n_ors=rng.randint(0, 5), or_size=3)
        bel = BeliefState(RULES, observer=None)
        bel.candidates = list(cand)
        bel.ors = list(ors)
        try:
            bel._propagate()
        except BeliefContradiction as e:
            violations.append(("SPURIOUS CONTRADICTION", t, str(e), free,
                               [true_deal[c] for c in free], cand, ors))
            continue
        sols, support = brute_force(free, cand, ors, true_deal)
        total_sols += sols
        if sols == 0:
            continue
        for c in free:
            missing = support[c] & ~bel.candidates[c]
            if missing:
                violations.append(("EXCLUDED POSSIBLE OWNER", t, c,
                                   f"true support {support[c]:06b}, "
                                   f"propagator {bel.candidates[c]:06b}, "
                                   f"removed {missing:06b}",
                                   free, cand, ors))
    return violations, total_sols


if __name__ == "__main__":
    for k in (6, 7, 8):
        v, s = run(trials=300, k_free=k, seed=k)
        print(f"k_free={k}: 300 random systems, {s} enumerated solutions, "
              f"{len(v)} soundness violations")
        for item in v[:3]:
            print("   ", item[0], "trial", item[1], item[2],
                  item[3] if len(item) > 3 else "")
