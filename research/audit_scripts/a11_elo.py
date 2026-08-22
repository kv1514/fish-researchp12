"""A11: Bradley-Terry rating fit (fish/eval/elo.py).

(1) is the returned point estimate really the MAP optimum (zero gradient of
    the exact log-posterior, verified by finite differences)?
(2) is `stderr` the correct Laplace standard error (numerical Hessian)?
(3) does the fit double-count when a matchup is listed in both directions?
(4) degenerate inputs: unknown anchor, single matchup, n=0 rows.
"""
import sys
import math

import numpy as np

sys.path.insert(0, r"C:\Users\vel_k\Documents\fish-engine")
from fish.eval.elo import fit_ratings, SCALE, _expected


def hdr(t):
    print()
    print("=" * 72)
    print(t)
    print("=" * 72)


def neg_log_post(r, rows, names, prior_sd=1500.0):
    idx = {n: i for i, n in enumerate(names)}
    v = 0.5 * float(np.sum(r ** 2)) / prior_sd ** 2
    for a, b, s, n in rows:
        e = _expected(r[idx[a]] - r[idx[b]])
        e = min(max(e, 1e-15), 1 - 1e-15)
        v -= n * (s * math.log(e) + (1 - s) * math.log(1 - e))
    return v


RESULTS = [
    ("random", "heuristic", 0.10, 200),
    ("random", "memory", 0.02, 200),
    ("random", "probabilistic", 0.00, 120),
    ("heuristic", "memory", 0.28, 200),
    ("heuristic", "probabilistic", 0.15, 120),
    ("memory", "probabilistic", 0.38, 120),
]

hdr("1. Is the fit a stationary point of the exact log-posterior?")
rat = fit_ratings(RESULTS, anchor="random")
names = sorted({n for r in RESULTS for n in (r[0], r[1])})
# undo the anchor shift to recover the raw optimum
shift = rat["random"]["rating"] - 0.0
raw = np.array([rat[n]["rating"] for n in names]) - 200.0
# raw is the internal parameterisation shifted so that random == 0 -> recover
# the parameter vector that fit_ratings actually optimised
base = np.array([rat[n]["rating"] for n in names])
offset = base[names.index("random")] - 0.0
r_hat = base - 200.0 + 0.0  # shift = 200 - r[random]  =>  r = rating - 200
g = np.zeros(len(names))
eps = 1e-4
for i in range(len(names)):
    p = r_hat.copy(); p[i] += eps
    m = r_hat.copy(); m[i] -= eps
    g[i] = (neg_log_post(p, RESULTS, names) - neg_log_post(m, RESULTS, names)) / (2 * eps)
print("  ratings:", {n: round(rat[n]["rating"]) for n in names})
print("  finite-difference gradient of -log posterior at the fit:")
print("   ", np.round(g, 8))
print("  max |grad| = %.2e  (0 means an exact optimum)" % np.max(np.abs(g)))

hdr("2. stderr vs a numerical Laplace standard error")
H = np.zeros((len(names), len(names)))
h = 1e-2
for i in range(len(names)):
    for j in range(len(names)):
        pp = r_hat.copy(); pp[i] += h; pp[j] += h
        pm = r_hat.copy(); pm[i] += h; pm[j] -= h
        mp = r_hat.copy(); mp[i] -= h; mp[j] += h
        mm = r_hat.copy(); mm[i] -= h; mm[j] -= h
        H[i, j] = (neg_log_post(pp, RESULTS, names)
                   - neg_log_post(pm, RESULTS, names)
                   - neg_log_post(mp, RESULTS, names)
                   + neg_log_post(mm, RESULTS, names)) / (4 * h * h)
cov = np.linalg.inv(H)
ai = names.index("random")
for i, n in enumerate(names):
    if n == "random":
        num = math.sqrt(max(0.0, cov[i, i]))
    else:
        num = math.sqrt(max(0.0, cov[i, i] + cov[ai, ai] - 2 * cov[i, ai]))
    print("  %-14s reported %7.2f   numerical %7.2f" %
          (n, rat[n]["stderr"], num))

hdr("3. double counting when a matchup is listed in both directions")
one = fit_ratings([("a", "b", 0.75, 100)], anchor="a")
two = fit_ratings([("a", "b", 0.75, 100), ("b", "a", 0.25, 100)], anchor="a")
print("  once :", {k: (round(v['rating'], 1), round(v['stderr'], 1))
                   for k, v in one.items()})
print("  twice:", {k: (round(v['rating'], 1), round(v['stderr'], 1))
                   for k, v in two.items()})
print("  -> listing the same matchup twice halves the stderr and is NOT")
print("     detected; the caller must supply each pair once (run_tournament")
print("     does, scripts/run_ablations.py should be checked).")

hdr("4. degenerate inputs")
print("  unknown anchor:", {k: round(v["rating"])
                            for k, v in fit_ratings(RESULTS, anchor="nope").items()})
print("  n=0 rows dropped:",
      {k: round(v["rating"])
       for k, v in fit_ratings([("a", "b", 0.9, 0), ("a", "c", 0.7, 50)],
                               anchor="a").items()})
print("  perfect separation:",
      {k: (round(v["rating"]), v["separated"])
       for k, v in fit_ratings([("a", "b", 1.0, 400)], anchor="b").items()})
