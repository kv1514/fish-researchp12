"""If the feature basis is the obstacle, which basis is not?

``scripts4/target_feature_fit.py`` established that the eleven-term ask
objective is nearly collinear at these positions: P(success) carries a variance
inflation factor of 13.5, so no fit on this basis identifies its coefficient and
the weights come back unstable however good the target is. That is a second
obstacle to learning the objective, independent of the continuation, and the
continuation fix does nothing about it.

The obvious follow-up is to spend ten more hours of rollouts. This script is the
cheap thing to do first: the existing completed run already holds 3076 scored
asks over 113 positions, and whether a DIFFERENT basis fits better is entirely
answerable from it.

WHAT IS COMPARED. Every basis is scored the same way -- leave-one-POSITION-out
cross-validated within-position R^2. Position-level folds matter: asks inside a
position share worlds, seeds and a value level, so a random split leaks and
would flatter every basis equally and uninformatively.

  full        all eleven terms plus P(success), as the paper fits it
  ridge       the same, L2-penalised, penalty chosen on the SAME folds
  drop-vif    greedily drop the highest-VIF term until every VIF < 5
  pca         principal components of the within-position design, k chosen
              on the folds
  psuccess    P(success) alone -- the paper's headline univariate slope
  top3        the three terms that survive the multivariate fit

WHAT THIS CANNOT SAY. A basis that predicts the rollout target better is not
thereby a basis that PLAYS better; the paper's whole learning section is about
that gap. This ranks candidate bases so the expensive duel goes to the best one,
and it is not itself evidence about play.

Usage: python scripts4/basis_search.py [results/rollout_target.json]
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

VIF_ALARM = 5.0
RIDGE_GRID = (0.0, 0.01, 0.1, 1.0, 10.0, 100.0, 1000.0)


def load(src):
    rows = json.loads(Path(src).read_text())["rows"]
    names = ["p_success"] + [n for n in TERM_NAMES if f"f_{n}" in rows[0]]
    by = {}
    for r in rows:
        by.setdefault(r["position"], []).append(r)
    groups = []
    for pid, g in sorted(by.items()):
        if len(g) < 2:
            continue
        M = np.array([[(r["p_success"] if n == "p_success" else r[f"f_{n}"])
                       for n in names] for r in g], dtype=float)
        y = np.array([r["q"] for r in g], dtype=float)
        # Within-position demeaning IS the fixed-effect transform: it removes
        # each position's own value level, which is what makes asks comparable
        # across positions at all.
        groups.append((pid, M - M.mean(0), y - y.mean()))
    return names, groups


def _vifs(X, names):
    out = {}
    for i, n in enumerate(names):
        y = X[:, i]
        if y.std() < 1e-12:
            out[n] = float("nan")
            continue
        others = np.delete(X, i, axis=1)
        b = np.linalg.lstsq(others, y, rcond=None)[0]
        r2 = 1 - ((y - others @ b) ** 2).sum() / (y ** 2).sum()
        out[n] = 1.0 / max(1e-9, 1.0 - r2)
    return out


def _ridge(X, y, lam):
    p = X.shape[1]
    return np.linalg.solve(X.T @ X + lam * np.eye(p), X.T @ y)


def cv_r2(groups, cols, lam=0.0, pca_k=None, top_k=None):
    """Leave-one-position-out CV. Returns (R^2, per-position squared errors).

    R^2 is computed against the null of predicting zero, which after
    within-position demeaning is the position's own mean -- so this is exactly
    "how much of the WITHIN-position variation is explained out of sample".

    ``top_k`` selects the k strongest terms INSIDE each fold rather than once on
    all the data. That distinction is the whole difference between an honest
    number and a leaked one, and the first version of this script got it wrong:
    it ranked terms by |beta * sd| on the full fit and then "cross-validated"
    the winner, so the selection had already seen every held-out position. That
    is the same selection effect this paper documents six times, arriving inside
    the tool built to escape it. Selecting per fold costs nothing and is right.
    """
    sse = sst = 0.0
    per_pos = []
    for i, (_pid, Xi, yi) in enumerate(groups):
        tr = [g for j, g in enumerate(groups) if j != i]
        Xtr = np.vstack([g[1][:, cols] for g in tr])
        ytr = np.concatenate([g[2] for g in tr])
        Xte = Xi[:, cols]
        if top_k is not None:
            b0 = np.linalg.lstsq(Xtr, ytr, rcond=None)[0]
            strength = np.abs(b0 * Xtr.std(0))
            pick = np.argsort(-strength)[:top_k]
            Xtr, Xte = Xtr[:, pick], Xte[:, pick]
        if pca_k is not None:
            # Rotate on TRAIN only. Fitting the rotation on all the data would
            # leak the held-out position into its own prediction.
            mu = Xtr.mean(0)
            U, S, Vt = np.linalg.svd(Xtr - mu, full_matrices=False)
            V = Vt[:pca_k].T
            Xtr, Xte = (Xtr - mu) @ V, (Xte - mu) @ V
        b = _ridge(Xtr, ytr, lam) if lam > 0 else \
            np.linalg.lstsq(Xtr, ytr, rcond=None)[0]
        pred = Xte @ b
        e = float(((yi - pred) ** 2).sum())
        sse += e
        sst += float((yi ** 2).sum())
        per_pos.append(e)
    r2 = 1 - sse / sst if sst > 0 else float("nan")
    return r2, np.array(per_pos)


def paired_gain(err_a, err_b, sst_total):
    """Is basis A's advantage over B bigger than the spread across positions?

    Both bases are scored on the SAME held-out positions, so the comparison is
    paired and the position's own difficulty cancels exactly -- the same
    argument the duplicate-deal design rests on. Reported as a difference in
    R^2, with a standard error clustered by position.
    """
    d = err_b - err_a                       # positive when A predicts better
    n = len(d)
    mean = float(d.sum() / sst_total)
    se = float(d.std(ddof=1) * np.sqrt(n) / sst_total)
    return mean, se


def main(argv):
    src = Path(argv[0]) if argv else ROOT / "results" / "rollout_target.json"
    names, groups = load(src)
    X = np.vstack([g[1] for g in groups])
    y = np.concatenate([g[2] for g in groups])
    n_pos, n_ask = len(groups), X.shape[0]
    print("which basis actually predicts the rollout target out of sample?\n")
    print(f"source {src.name}   {n_ask} scored asks over {n_pos} positions")
    print(f"folds: leave-one-POSITION-out ({n_pos} folds) -- asks inside a "
          f"position share\nworlds, seeds and a value level, so a random split "
          f"would leak\n")

    allc = list(range(len(names)))
    v = _vifs(X, names)
    bad = sorted((c for c in allc if v[names[c]] > VIF_ALARM),
                 key=lambda c: -v[names[c]])
    print("variance inflation on the full basis:")
    for c in sorted(allc, key=lambda c: -v[names[c]])[:5]:
        flag = "  <- not identified" if v[names[c]] > VIF_ALARM else ""
        print(f"  {names[c]:<10}{v[names[c]]:>7.1f}{flag}")

    # drop-vif: greedily drop the worst offender and recompute, since dropping
    # one term changes every other term's VIF.
    keep = list(allc)
    dropped = []
    while len(keep) > 1:
        vv = _vifs(X[:, keep], [names[c] for c in keep])
        worst = max(keep, key=lambda c: vv[names[c]])
        if vv[names[worst]] <= VIF_ALARM:
            break
        keep.remove(worst)
        dropped.append(names[worst])

    beta = np.linalg.lstsq(X, y, rcond=None)[0]
    ranked = sorted(allc, key=lambda c: -abs(beta[c] * X[:, c].std()))
    p_idx = names.index("p_success")

    # (label, columns, ridge lambda, pca k, per-fold top-k)
    bases = [
        ("full (11 terms + p)", allc, 0.0, None, None),
        ("drop-vif", keep, 0.0, None, None),
        ("p_success alone", [p_idx], 0.0, None, None),
    ]
    for k in (2, 3, 4, 6):
        bases.append((f"top{k} per fold", allc, 0.0, None, k))
    for lam in RIDGE_GRID[1:]:
        bases.append((f"ridge lam={lam:g}", allc, lam, None, None))
    for k in (2, 3, 4, 6, 8):
        if k < len(allc):
            bases.append((f"pca k={k}", allc, 0.0, k, None))

    print(f"\ndrop-vif kept {len(keep)} term(s); dropped in order: "
          f"{', '.join(dropped) if dropped else '(none)'}")
    print(f"strongest on the full fit (for reference only, NOT the CV basis): "
          f"{', '.join(names[c] for c in ranked[:3])}")

    sst_total = float((y ** 2).sum())
    print(f"\n{'basis':<24}{'terms':>7}{'CV R^2':>10}{'vs full':>20}")
    scored = []
    full_err = None
    for label, cols, lam, k, tk in bases:
        r2, err = cv_r2(groups, cols, lam=lam, pca_k=k, top_k=tk)
        if label.startswith("full"):
            full_err = err
        scored.append((label, cols, lam, (k or tk), r2, err))
    for label, cols, lam, k, r2, err in scored:
        if label.startswith("full"):
            cmp = "--"
        else:
            g, se = paired_gain(err, full_err, sst_total)
            z = g / se if se > 0 else 0.0
            cmp = f"{g:+.4f} +/- {se:.4f} ({z:+.1f})"
        print(f"{label:<24}{(k or len(cols)):>7}{r2:>10.4f}{cmp:>20}")

    best = max(scored, key=lambda t: t[4])
    full = next(t for t in scored if t[0].startswith("full"))
    gain, gain_se = (0.0, 0.0) if best[0].startswith("full") else \
        paired_gain(best[5], full_err, sst_total)
    print(f"\nbest: {best[0]}  (CV R^2 {best[4]:.4f})")
    print(f"full basis:                     {full[4]:.4f}")
    print()
    if best[0].startswith("full"):
        print("The full basis is already the best of these out of sample. "
              "Collinearity\nmakes its individual COEFFICIENTS unidentified "
              "without making its\nPREDICTIONS worse -- which is the textbook "
              "consequence and is worth saying\nplainly, because it means a "
              "reduced basis is not the fix and the re-run\nshould look "
              "elsewhere.")
    elif gain - 1.959964 * gain_se > 0:
        print(f"A different basis predicts {gain:+.4f} +/- {gain_se:.4f} better "
              f"out of sample than\nthe one the objective currently uses, and "
              f"the interval excludes zero. That\nis a reason to fit the re-run "
              f"on it -- and NOT yet a reason to ship it:\npredicting the "
              f"rollout target better is not playing better, which is the gap\n"
              f"this paper's whole learning section is about.")
    else:
        print(f"The best basis beats the full one by {gain:+.4f} +/- "
              f"{gain_se:.4f}, an interval that\nCONTAINS ZERO. Ranked by a "
              f"point estimate it wins; measured against the\nspread across "
              f"positions it is not distinguishable. So the honest reading is\n"
              f"that no basis here is demonstrably better, and choosing one on "
              f"this table\nwould be selecting on noise -- the same error this "
              f"paper documents six times.")

    out = {"source": str(src), "n_positions": n_pos, "n_asks": n_ask,
           "vifs": {k: float(x) for k, x in v.items()},
           "drop_vif_kept": [names[c] for c in keep],
           "drop_vif_dropped": dropped,
           "strongest_full_fit": [names[c] for c in ranked[:3]],
           "cv": {label: float(r2) for label, _c, _l, _k, r2, _e in scored},
           "best": best[0], "best_cv_r2": float(best[4]),
           "full_cv_r2": float(full[4]),
           "gain_over_full": float(gain),
           "gain_se": float(gain_se),
           "gain_excludes_zero": bool(gain - 1.959964 * gain_se > 0)}
    dest = ROOT / "results" / "basis_search.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
