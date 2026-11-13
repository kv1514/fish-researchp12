"""Pool repeated runs of one configuration, and test whether they agree.

WHY THIS EXISTS
---------------
Running the same duel configuration three times on different seeds produced
+0.570, -0.044 and +0.386 sets per deal-pair. Reading any one of those as "the"
result is the mistake this script exists to prevent, and picking the one that
suits the story is the worse version of it.

Two things have to be asked in order:

1. **Do the cells agree?** Each cell reports a within-run interval, which covers
   the mean of the deals actually played. If the runs differ by more than that
   within-run noise allows, then there is between-run variance the per-cell
   intervals do not model, and pooling them as if they were one sample is
   invalid. Cochran's Q tests exactly this.
2. **Only then, what is the pooled estimate?** A fixed-effect pool assumes one
   true value and is right when Q is unremarkable. When it is not, a
   random-effects pool is the honest one: it adds the estimated between-run
   variance tau^2 to every cell, which widens the interval to reflect that a
   further run would land somewhere new.

The paper already noticed this phenomenon informally --- of its own headline it
says three estimates "span +1.85 to +2.44, wider than their individual intervals
suggest". This quantifies it.

    py scripts4/pool_cells.py "<label>" ["<label>" ...]
    py scripts4/pool_cells.py --lookahead      # the belief-space search cells
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish4.match import _t_critical                      # noqa: E402

Z = 1.959964

#: The three runs of the identical lookahead configuration: one screen at 200
#: pairs and two retests at 500, differing only in their seed streams.
LOOKAHEAD = [
    "lookahead d3 w0.25 vs champion",
    "REPLICATE lookahead d3 w0.25 vs champion (fresh seeds)",
    "REPLICATE lookahead d3 w0.25 vs champion (second fresh set)",
]


def cells(labels: list[str]) -> list[dict]:
    """Load each named cell, with its standard error obtained EXACTLY.

    Two things here were wrong and both were quiet.

    The standard error used to be back-solved from the recorded interval as
    ``(hi - lo) / (2 * 1.959964)``. But ``fish4.match.MatchResult.diff_ci``
    builds that interval with a **t** critical on ``n - 1`` degrees of freedom,
    not a normal one, so every recovered standard error came out inflated -- by
    0.12% at n=1000 and 0.6% at n=200. Small, and it propagated: the same cell's
    per-pair SD came out as 3.796 here and 3.791 in the divergence model, from
    the same thousand numbers. Where the per-pair differentials are stored, the
    standard error is now computed from them directly and nothing is inverted.

    And a repeated label used to resolve silently to ``hits[-1]``. Three labels
    in the results file are duplicated. Silently preferring the last is a way to
    pool a cell nobody meant to pool, so it raises.
    """
    rows = [json.loads(l) for l in
            (ROOT / "results" / "v04_duels.jsonl").read_text().splitlines()
            if l.strip()]
    out = []
    for label in labels:
        hits = [r for r in rows if (r.get("label") or "") == label]
        if not hits:
            print(f"no run with label {label!r}", file=sys.stderr)
            continue
        if len(hits) > 1:
            raise ValueError(
                f"{len(hits)} runs share the label {label!r}. Pooling would "
                f"silently pick one; give them distinct labels.")
        r = hits[0]
        lo, hi = r["diff_ci"]
        n = int(r["n_pairs"])
        d = r.get("diffs")
        if d and len(d) == n and n > 1:
            se = math.sqrt(statistics.variance(d) / n)
        else:
            # No per-pair data: invert the interval with the SAME critical
            # value the harness used to build it.
            se = (hi - lo) / (2 * _t_critical(n - 1, 0.95)) if n > 1 else 0.0
        out.append({"label": label, "n": n, "est": r["diff_mean"],
                    "lo": lo, "hi": hi, "se": se,
                    # Each cell's own per-pair SD. If these agree across cells
                    # then the within-run intervals are fine and any
                    # disagreement is genuinely between runs.
                    "sd": se * math.sqrt(n)})
    return out


def pool(cs: list[dict]) -> dict:
    ws = [1.0 / c["se"] ** 2 for c in cs]
    sw = sum(ws)
    fe = sum(w * c["est"] for w, c in zip(ws, cs)) / sw
    fe_se = 1.0 / math.sqrt(sw)

    q = sum(w * (c["est"] - fe) ** 2 for w, c in zip(ws, cs))
    df = len(cs) - 1
    i2 = max(0.0, (q - df) / q) if q > 0 else 0.0

    # DerSimonian-Laird between-run variance.
    c_ = sw - sum(w * w for w in ws) / sw
    tau2 = max(0.0, (q - df) / c_) if c_ > 0 else 0.0
    ws2 = [1.0 / (c["se"] ** 2 + tau2) for c in cs]
    sw2 = sum(ws2)
    re = sum(w * c["est"] for w, c in zip(ws2, cs)) / sw2
    re_se = 1.0 / math.sqrt(sw2)

    return {"fe": fe, "fe_se": fe_se, "q": q, "df": df, "i2": i2,
            "tau2": tau2, "tau": math.sqrt(tau2), "re": re, "re_se": re_se,
            "q_p": _chi2_sf(q, df)}


def _chi2_sf(x: float, k: int) -> float:
    """Upper tail of chi-square. Exact for the small even/odd k we use."""
    if x <= 0:
        return 1.0
    if k == 1:
        return math.erfc(math.sqrt(x / 2.0))
    if k == 2:
        return math.exp(-x / 2.0)
    # k >= 3: recurse down by two, which terminates at k in {1, 2}.
    return (_chi2_sf(x, k - 2)
            + (x / 2.0) ** (k / 2.0 - 1) * math.exp(-x / 2.0)
            / math.gamma(k / 2.0))


def main(labels: list[str]) -> int:
    cs = cells(labels)
    if len(cs) < 2:
        print("need at least two runs to pool", file=sys.stderr)
        return 2
    print(f"{'run':<58} {'n':>5} {'est':>8} {'95% CI':>19} {'SD':>6}")
    for c in cs:
        print(f"{c['label'][:58]:<58} {c['n']:>5} {c['est']:>+8.3f} "
              f"[{c['lo']:+.3f},{c['hi']:+.3f}] {c['sd']:>6.2f}")

    p = pool(cs)
    print(f"\nagreement between runs")
    print(f"  Cochran Q          {p['q']:.3f} on {p['df']} df, p = {p['q_p']:.4f}")
    print(f"  I^2                {100 * p['i2']:.1f}%   "
          f"(share of spread that is between-run, not sampling)")
    print(f"  tau (between-run)  {p['tau']:.3f} sets per pair")

    lo, hi = p["fe"] - Z * p["fe_se"], p["fe"] + Z * p["fe_se"]
    print(f"\npooled, fixed effect   {p['fe']:+.3f} [{lo:+.3f}, {hi:+.3f}]"
          f"   {'excludes 0' if lo > 0 or hi < 0 else 'includes 0'}")
    lo2, hi2 = p["re"] - Z * p["re_se"], p["re"] + Z * p["re_se"]
    print(f"pooled, random effects {p['re']:+.3f} [{lo2:+.3f}, {hi2:+.3f}]"
          f"   {'excludes 0' if lo2 > 0 or hi2 < 0 else 'includes 0'}")

    if p["q_p"] < 0.05:
        print("\nThe runs do NOT agree within their own intervals, so the "
              "fixed-effect\nline above is not usable: it assumes a single true "
              "value and the data\nreject that. Read the random-effects line.")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    raise SystemExit(main(LOOKAHEAD if not args or args == ["--lookahead"]
                          else args))
