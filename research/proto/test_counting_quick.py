import sys, random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fish4.counting import GroupSystem, Infeasible, brute_force, group_cards, NUM_PLAYERS

rng = random.Random(7)
bad = 0
for trial in range(400):
    n_cards = rng.randint(3, 11)
    pool = [rng.randint(1, 63) for _ in range(rng.randint(1, 4))]
    card_masks = [rng.choice(pool) for _ in range(n_cards)]
    quotas = [0]*NUM_PLAYERS
    for _ in range(n_cards): quotas[rng.randrange(NUM_PLAYERS)] += 1
    masks, sizes, cg = group_cards(card_masks)
    try:
        s = GroupSystem(masks, sizes, quotas); Z = s.partition()
        E = s.expected_counts() if Z > 0 else None
    except Infeasible:
        Z, E = 0.0, None
    bc, bm = brute_force(card_masks, quotas)
    if abs(Z - bc) > 1e-6*max(1.0, bc):
        print("COUNT MISMATCH", trial, Z, bc); bad += 1; continue
    if bc == 0: continue
    for c in range(n_cards):
        g = cg[c]
        for p in range(NUM_PLAYERS):
            if abs(E[g,p]/sizes[g] - bm[c][p]) > 1e-9:
                print("MARG MISMATCH", trial, c, p, E[g,p]/sizes[g], bm[c][p]); bad += 1; break
        else: continue
        break
print(f"counting: {400-bad}/400 exact matches")

# pinned_partition check
bad2 = 0
for trial in range(200):
    n_cards = rng.randint(3, 9)
    pool = [rng.randint(1, 63) for _ in range(rng.randint(1, 3))]
    card_masks = [rng.choice(pool) for _ in range(n_cards)]
    quotas = [0]*NUM_PLAYERS
    for _ in range(n_cards): quotas[rng.randrange(NUM_PLAYERS)] += 1
    masks, sizes, cg = group_cards(card_masks)
    try:
        s = GroupSystem(masks, sizes, quotas); Z = s.partition()
    except Infeasible: continue
    if Z <= 0: continue
    # pin two random cards to random allowed players
    c1 = rng.randrange(n_cards); p1 = rng.choice([p for p in range(6) if card_masks[c1]>>p&1])
    got = s.pinned_partition([(cg[c1], p1)])
    # brute force
    from itertools import product as iproduct
    choices = [[p for p in range(6) if card_masks[c]>>p&1] for c in range(n_cards)]
    cnt = 0
    for a in iproduct(*choices):
        if a[c1] != p1: continue
        k=[0]*6
        for p in a: k[p]+=1
        if k == list(quotas): cnt += 1
    if abs(got - cnt) > 1e-6*max(1.0,cnt):
        print("PIN MISMATCH", trial, got, cnt); bad2 += 1
print(f"pinned_partition: {200-bad2}/200 ok (of attempted)")
