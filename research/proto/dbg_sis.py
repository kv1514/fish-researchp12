import sys, random, collections
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests4"))
from fish4.sis import SISSampler
from test_sis import enumerate_worlds, path_probability

masks = {0: 3, 1: 20, 2: 30, 3: 3, 4: 30}
quotas = [1, 1, 1, 1, 1, 0]
ors = [((3, 2, 4), 3), ((0, 3, 2), 1), ((4, 3, 1), 2)]
free = [0, 1, 2, 3, 4]
worlds = enumerate_worlds(free, masks, quotas, ors)
print("valid worlds:", len(worlds))
for w in worlds: print("   ", [w[c] for c in free])
s = SISSampler(free, masks, quotas, ors)
print("filtered ors:", s.ors)
print("order:", s.order)
ana = {tuple(w[c] for c in free): path_probability(s, w) for w in worlds}
tot = sum(ana.values()); print("analytic total (P success):", tot)
rng = random.Random(1)
cnt = collections.Counter(); got=0
for _ in range(60000):
    try:
        d, lq, ll = s.draw(rng)
    except Exception:
        continue
    got += 1
    cnt[tuple(d[c] for c in free)] += 1
print("empirical draws:", got)
extra = set(cnt) - set(ana)
print("worlds produced that are NOT valid:", len(extra))
for k in list(extra)[:5]: print("   invalid:", k, cnt[k]/got)
for k in ana:
    print(f"   {k}  analytic {ana[k]/tot:.4f}  empirical {cnt.get(k,0)/got:.4f}")
