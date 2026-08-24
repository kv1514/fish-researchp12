"""What predicts the rollout target once it carries signal -- and what cannot.

With the strong continuation the target is no longer flat (+0.681 against +0.101
for P(success)), so the obvious next question is which of the eleven objective
terms it responds to. Fitting that is one line. Reading it is where the trouble
is, and this script exists to make the trouble visible rather than to report a
ranking.

Univariate, each feature's within-position slope on rollout value looks
informative and several beat P(success). Multivariate, P(success) turns
NEGATIVE. Neither reading survives the diagnostic that belongs beside them: at
these positions P(success) has a variance inflation factor above ten, because it
is computed from the same posterior as the features and correlates with two of
them at +0.85 and +0.74. A regression on this basis cannot identify P(success)'s
coefficient separately from theirs, and a coefficient that is not identified
does not become identified by being reported.

WHY THIS MATTERS FOR THE RE-RUN. The paper diagnosed the failed objective-
learning line as a continuation problem, and that diagnosis was right and the
continuation is fixed. This is a SECOND problem, and fixing the first does
nothing to it: the design matrix is nearly collinear, so the fitted weights are
unstable whatever the target looks like. It is consistent with what v0.4's fit
actually produced -- a `turn` coefficient of 0.157 where play measures 0.60 --
and it is worth knowing before spending another ten hours of rollouts.

Usage: python scripts4/target_feature_fit.py [results/rollout_target.json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts4"))

from fish4.askfeat import TERM_NAMES                          # noqa: E402

from rollout_target import centred_slope                      # noqa: E402

VIF_ALARM = 5.0


def _design(rows, names):
    """Within-position demeaned design matrix, outcome, and cluster labels."""
    by = {}
    for r in rows:
        by.setdefault(r["position"], []).append(r)
    X, Y, G = [], [], []
    for pid, g in by.items():
        if len(g) < 2:
            continue
        M = np.array([[(r["p_success"] if n == "p_success" else r[f"f_{n}"])
                       for n in names] for r in g], dtype=float)
        y = np.array([r["q"] for r in g], dtype=float)
        X.append(M - M.mean(0))
        Y.append(y - y.mean())
        G += [pid] * len(g)
    return np.vstack(X), np.concatenate(Y), np.array(G)


def _clustered(X, Y, G):
    inv = np.linalg.pinv(X.T @ X)
    beta = inv @ X.T @ Y
    res = Y - X @ beta
    meat = np.zeros((X.shape[1], X.shape[1]))
    for pid in np.unique(G):
        m = G == pid
        u = X[m].T @ res[m]
        meat += np.outer(u, u)
    V = inv @ meat @ inv
    return beta, np.sqrt(np.clip(np.diag(V), 0, None))


def main(argv):
    src = Path(argv[0]) if argv else ROOT / "results" / "rollout_target.json"
    rows = json.loads(src.read_text())["rows"]
    names = ["p_success"] + [n for n in TERM_NAMES if f"f_{n}" in rows[0]]

    print("what predicts the rollout target, and what the fit cannot "
          "separate?\n")
    print(f"source {src.name}   {len(rows)} scored asks over "
          f"{len({r['position'] for r in rows})} positions\n")

    # 1. Univariate, one feature at a time.
    print(f"{'feature':<10}{'univariate':>12}{'se':>9}{'|t|':>7}")
    uni = {}
    for n in names:
        key = "p_success" if n == "p_success" else f"f_{n}"
        s = centred_slope([{"position": r["position"], "p_success": r[key],
                            "q": r["q"]} for r in rows])
        if s is None or s["se_clustered"] <= 0:
            continue
        uni[n] = (s["slope"], s["se_clustered"])
    for n, (b, se) in sorted(uni.items(), key=lambda kv: -abs(kv[1][0] / kv[1][1])):
        t = abs(b) / se
        print(f"{n:<10}{b:>+12.4f}{se:>9.4f}{t:>7.2f}{' *' if t > 1.96 else ''}")

    # 2. Multivariate, all at once.
    X, Y, G = _design(rows, names)
    beta, se = _clustered(X, Y, G)
    print(f"\n{'feature':<10}{'multivariate':>14}{'se':>9}{'|t|':>7}{'VIF':>8}")
    vifs = {}
    for i, n in enumerate(names):
        others = np.delete(X, i, axis=1)
        y = X[:, i]
        if y.std() < 1e-12:
            vifs[n] = float("nan")
            continue
        b = np.linalg.lstsq(others, y, rcond=None)[0]
        r2 = 1 - ((y - others @ b) ** 2).sum() / (y ** 2).sum()
        vifs[n] = 1.0 / max(1e-9, 1.0 - r2)
    order = np.argsort(-np.abs(beta / np.where(se > 0, se, np.inf)))
    for i in order:
        t = abs(beta[i]) / se[i] if se[i] > 0 else 0.0
        v = vifs[names[i]]
        flag = " <- not identified" if v > VIF_ALARM else ""
        print(f"{names[i]:<10}{beta[i]:>+14.4f}{se[i]:>9.4f}{t:>7.2f}"
              f"{v:>8.1f}{flag}")

    r2w = 1 - ((Y - X @ beta) ** 2).sum() / (Y ** 2).sum()
    print(f"\nwithin R^2 {r2w:.4f}")

    # 3. The diagnostic that decides how to read the two tables.
    p = names.index("p_success")
    corr = []
    for i, n in enumerate(names):
        if i == p or X[:, i].std() < 1e-12:
            continue
        corr.append((abs(np.corrcoef(X[:, p], X[:, i])[0, 1]), n))
    corr.sort(reverse=True)
    print(f"\nP(success) is collinear with the basis it is being fitted "
          f"beside:")
    for c, n in corr[:3]:
        print(f"  |corr| with {n:<9}{c:.3f}")
    print(f"  variance inflation factor {vifs['p_success']:.1f} "
          f"({100 * (1 - 1 / vifs['p_success']):.1f}% of its within-position "
          f"variation\n  is explained by the other ten terms)")

    print()
    if vifs["p_success"] > VIF_ALARM:
        print("So neither table above identifies P(success)'s own coefficient,")
        print("and its negative multivariate sign is an artefact of that rather")
        print("than a finding. What the data can say is that this feature basis")
        print("is nearly collinear at these positions, so a regression on it")
        print("returns unstable weights no matter how good the target is.")
        print()
        print("That is a SECOND obstacle to learning the objective, independent")
        print("of the continuation. Fixing the continuation -- which is done,")
        print("and worth a factor of seven in the target's slope -- does nothing")
        print("about it. It is also consistent with what the previous fit")
        print("produced: a `turn` coefficient of 0.157 where duplicate-deal play")
        print("measures 0.60.")
    else:
        print("P(success) is identified here, so the multivariate column can be")
        print("read as written.")

    out = {"source": str(src), "n_rows": len(rows),
           "n_positions": len({r["position"] for r in rows}),
           "univariate": {n: {"slope": b, "se": s} for n, (b, s) in uni.items()},
           "multivariate": {n: {"coef": float(beta[i]), "se": float(se[i]),
                                "vif": float(vifs[n])}
                            for i, n in enumerate(names)},
           "within_r2": float(r2w),
           "p_success_vif": float(vifs["p_success"]),
           "p_success_abscorr": {n: float(c) for c, n in corr}}
    dest = ROOT / "results" / "target_feature_fit.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main(sys.argv[1:])
