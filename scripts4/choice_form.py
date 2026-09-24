"""Is the power law the right shape, or only a shape that fits?

The choice model says P(ask in H) is proportional to depth^alpha. That is one
functional form with one parameter, and fitting it well is not evidence that it
is the right one. The saturated alternative gives every depth value its own free
coefficient; it nests the power law, so it can never fit worse, and it is the
best that ANY model conditioning on depth alone can do.

The gap between them is the shape the power law is missing. It bounds what is
left in the choice model without a new covariate -- which matters because the
covariate turned out to be where the value was: moving from initial-deal depth
to depth at the moment of the ask is worth 4,654 nats on these same decisions.

Reported for both covariates, with convergence stated rather than assumed: a
saturated fit that has not converged reports a gap that is too small, so an
un-converged run is labelled instead of quietly rounded off.

    py scripts4/choice_form.py [max_iters]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts4"))

from choice_curve import design, fit_alpha                       # noqa: E402

MAX_DEPTH = 6


def _relabel(records, key):
    """Point the fitter at a different depth column."""
    return [{**r, "alts": [{**a, "depth0": a[key]} for a in r["alts"]]}
            for r in records]


def saturated(des, max_d=MAX_DEPTH, iters=20000, lr=0.05, tol=1e-9):
    """Free log-propensity per depth value, by gradient descent.

    A multinomial logit with one dummy per depth, ``c[1]`` pinned at 0 for
    identifiability. The gradient of the negative log-likelihood is
    expected-minus-observed counts per depth, which is why this needs no
    Hessian: the objective is convex and the gradient is two scatter-adds.

    The convergence test compares against the PREVIOUS iterate. An earlier
    version compared the objective against itself before stepping, exited on the
    first pass, and reported the uniform likelihood -- which showed up as the
    saturated model fitting worse than the power law it nests, an impossibility
    that is worth keeping as the check.
    """
    pad, LD, ch = des["pad"], des["LD"], des["chosen"]
    D = np.clip(np.rint(np.exp(LD)).astype(int), 0, max_d)
    n = D.shape[0]
    rows = np.arange(n)
    c = np.zeros(max_d + 1)

    def f_and_g(c):
        z = np.where(pad, -np.inf, c[D])
        mx = np.max(z, axis=1, keepdims=True)
        ez = np.exp(np.where(pad, -np.inf, z - mx))
        den = ez.sum(axis=1, keepdims=True)
        p = ez / den
        nll = float(np.sum(mx[:, 0] + np.log(den[:, 0]) - c[D[rows, ch]]))
        g = np.zeros_like(c)
        np.add.at(g, D[~pad], p[~pad])
        np.add.at(g, D[rows, ch], -1.0)
        g[1] = 0.0
        return nll, g

    prev, converged, it = None, False, 0
    for it in range(iters):
        f, g = f_and_g(c)
        if prev is not None and abs(prev - f) < tol:
            converged = True
            break
        prev = f
        c = c - lr * g / n * 20
    return {"nll": f_and_g(c)[0], "coef": c, "iters": it,
            "converged": converged}


def main(argv):
    iters = int(argv[0]) if argv else 20000
    path = ROOT / "results" / "choice_curve_records.json"
    if not path.exists():
        print("no records; run scripts4/choice_curve.py first")
        return 1
    recs = json.loads(path.read_text())
    print(f"{len(recs)} decisions\n")

    out = []
    for key, label in (("depth0", "initial-deal depth"),
                       ("held_now", "depth at the ask")):
        d = _relabel(recs, key)
        power = fit_alpha(d)
        sat = saturated(design(d), iters=iters)
        gap = power["nll"] - sat["nll"]
        assert gap > -1e-6, (
            "the saturated model fits worse than the power law it nests; "
            "the optimiser has not converged")
        rel = np.exp(sat["coef"][1:6] - sat["coef"][1])
        pw = np.array([float(v) ** power["alpha"] for v in range(1, 6)])
        out.append({"covariate": key, "alpha": power["alpha"],
                    "nll_power": power["nll"], "nll_saturated": sat["nll"],
                    "gap_nats": gap, "converged": sat["converged"],
                    "iters": sat["iters"],
                    "saturated_relative": rel.tolist(),
                    "power_relative": pw.tolist()})
        flag = "" if sat["converged"] else "   [NOT CONVERGED - gap is a lower bound]"
        print(f"{label}")
        print(f"   power law  alpha = {power['alpha']:+.3f}   "
              f"nll = {power['nll']:9.1f}")
        print(f"   saturated  (free per depth)      nll = {sat['nll']:9.1f}"
              f"{flag}")
        print(f"   gap = {gap:.1f} nats over {power['n']} decisions")
        print("   relative propensity, depth 1..5")
        print("     saturated  " + "  ".join(f"{v:7.3f}" for v in rel))
        print("     power law  " + "  ".join(f"{v:7.3f}" for v in pw))
        print()

    if len(out) == 2:
        cov = out[0]["nll_power"] - out[1]["nll_power"]
        shape = max(o["gap_nats"] for o in out)
        print(f"changing the COVARIATE is worth {cov:.0f} nats;")
        print(f"unconstraining the SHAPE is worth at most {shape:.0f}.")
        print(f"The covariate matters {cov / max(shape, 1):.0f}x more, so the "
              f"power law is not\nwhat is limiting this model.")
    dest = ROOT / "results" / "choice_form.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
