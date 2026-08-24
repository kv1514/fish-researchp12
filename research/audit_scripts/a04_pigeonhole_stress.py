"""A04: adversarial stress of _propagate_or_pigeonhole.

Generates constraint systems ENGINEERED to make the pigeonhole and
subsumption rules fire (tight quotas, several disjoint/overlapping OR groups
per player), then brute-forces the exact solution set and checks the
propagator never removed a genuinely possible owner and never raised a
spurious contradiction.
"""
import sys, random, itertools
sys.path.insert(0, r"C:\Users\vel_k\Documents\fish-engine")
import fish.beliefs as B
from fish.rules import RuleConfig
from fish.beliefs import BeliefState, BeliefContradiction

RULES = RuleConfig()
N, PER, NP = 54, 9, 6

FIRED = {"pigeonhole": 0, "unit": 0}
_orig_ph = BeliefState._propagate_or_pigeonhole
def _spy(self, quota):
    before = list(self.candidates)
    r = _orig_ph(self, quota)
    if r:
        FIRED["pigeonhole"] += 1
    return r
BeliefState._propagate_or_pigeonhole = _spy


def build(rng, k_free):
    true_deal = []
    for p in range(NP):
        true_deal += [p] * PER
    rng.shuffle(true_deal)
    by_owner = {p: [c for c in range(N) if true_deal[c] == p] for p in range(NP)}

    # choose a target player and a tight quota
    p = rng.randrange(NP)
    q = rng.randint(1, 3)
    # free cards: q of p's cards + others
    p_free = rng.sample(by_owner[p], q)
    others = [c for c in range(N) if true_deal[c] != p]
    n_other_free = k_free - q
    o_free = rng.sample(others, n_other_free)
    free = p_free + o_free
    freeset = set(free)

    cand = [1 << true_deal[c] for c in range(N)]
    for c in free:
        m = 1 << true_deal[c]
        extra = rng.sample([x for x in range(NP) if x != true_deal[c]],
                           rng.randint(1, 2))
        for e in extra:
            m |= 1 << e
        if rng.random() < 0.8:
            m |= 1 << p                    # make p a live candidate often
        cand[c] = m

    # q disjoint OR groups for p, each anchored on one of p's free cards
    ors = []
    pool = [c for c in o_free if cand[c] & (1 << p)]
    rng.shuffle(pool)
    cursor = 0
    for anchor in p_free:
        grp = [anchor]
        take = min(rng.randint(1, 2), len(pool) - cursor)
        grp += pool[cursor:cursor + take]
        cursor += take
        ors.append((tuple(sorted(grp)), p))
    # some extra overlapping / subsumed ORs
    for _ in range(rng.randint(0, 3)):
        pp = rng.randrange(NP)
        anch = rng.choice(by_owner[pp])
        extra = [c for c in free if cand[c] & (1 << pp) and c != anch]
        if not extra:
            continue
        grp = tuple(sorted([anch] + rng.sample(extra, min(len(extra),
                                                          rng.randint(1, 2)))))
        ors.append((grp, pp))
    return true_deal, free, cand, ors


def brute(free, cand, ors, pinned):
    fs = set(free)
    quota = [PER] * NP
    for c in range(N):
        if c not in fs:
            quota[pinned[c]] -= 1
    idx = {c: i for i, c in enumerate(free)}
    domains = [[p for p in range(NP) if cand[c] & (1 << p)] for c in free]
    support = {c: 0 for c in free}
    sols = 0
    for combo in itertools.product(*domains):
        qq = quota[:]
        bad = False
        for p in combo:
            qq[p] -= 1
            if qq[p] < 0:
                bad = True
                break
        if bad or any(x for x in qq):
            continue
        okay = True
        for grp, p in ors:
            if not any((combo[idx[c]] if c in idx else pinned[c]) == p
                       for c in grp):
                okay = False
                break
        if not okay:
            continue
        sols += 1
        for i, c in enumerate(free):
            support[c] |= 1 << combo[i]
    return sols, support


def run(trials, k_free, seed):
    rng = random.Random(seed)
    bugs = []
    stats = {"sat": 0, "unsat": 0, "sols": 0}
    for t in range(trials):
        true_deal, free, cand, ors = build(rng, k_free)
        bel = BeliefState(RULES, observer=None)
        bel.candidates = list(cand)
        bel.ors = list(ors)
        raised = None
        try:
            bel._propagate()
        except BeliefContradiction as e:
            raised = str(e)
        sols, support = brute(free, cand, ors, true_deal)
        stats["sols"] += sols
        if sols == 0:
            stats["unsat"] += 1
            continue
        stats["sat"] += 1
        if raised is not None:
            bugs.append(("SPURIOUS CONTRADICTION", t, raised, free,
                         [true_deal[c] for c in free], cand, ors, sols))
            continue
        for c in free:
            miss = support[c] & ~bel.candidates[c]
            if miss:
                bugs.append(("EXCLUDED POSSIBLE OWNER", t, c,
                             support[c], bel.candidates[c], free, cand, ors,
                             sols))
    return bugs, stats


if __name__ == "__main__":
    tot = []
    for k in (6, 7, 8, 9):
        bugs, st = run(500, k, seed=100 + k)
        print(f"k_free={k}: sat={st['sat']} unsat={st['unsat']} "
              f"solutions={st['sols']} bugs={len(bugs)}")
        tot += bugs
    print("pigeonhole rule fired (changed something) in",
          FIRED["pigeonhole"], "propagation passes")
    print("TOTAL SOUNDNESS VIOLATIONS:", len(tot))
    for b in tot[:5]:
        print("  ", b[0], "trial", b[1])
        print("    detail:", b[2:5])
        print("    free:", b[5] if len(b) > 5 else "")
        print("    ors:", b[7] if len(b) > 7 else "")
