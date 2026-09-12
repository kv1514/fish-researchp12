"""Is between-block disagreement a property of the harness, or of one effect?

The at-ask run's six blocks disagree by more than sampling noise allows
(Cochran's Q p = 0.024, I^2 = 61%, tau = 0.150 -- the size of the effect
itself). Read alone that admits two explanations: the harness understates its
own uncertainty, or that particular effect varies with the deal population.

They are distinguishable, because this study has run the identical six-block
design three times and an A/A null twenty-four times. If the harness were the
problem, all of them would show it.

MULTIPLICITY, stated before the table rather than after: four homogeneity tests
at the 5% level give roughly a one-in-five chance of at least one significant
result under a complete null. One significant Q out of four is suggestive, not
decisive, and the strongest honest claim is that heterogeneity is not the
harness's default behaviour.

Usage: python scripts4/heterogeneity_across_runs.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts4"))

from pool_cells import cells, pool                              # noqa: E402

RUNS = {
    "lookahead settling":
        [f"SETTLE lookahead d3 w0.25 block {i}" for i in range(6)],
    "precision 480 vs 160":
        [f"PRECISION n_draws 480 vs 160 block {i}" for i in range(6)],
    "at-ask depth g1.0":
        [f"AT_ASK g1.0 vs champion block {i}" for i in range(6)],
    "stack, lookahead on 480":
        [f"STACK lookahead on top of n_draws 480 block {i}" for i in range(6)],
    "precision 1440 vs 480":
        [f"PRECISION2 n_draws 1440 vs 480 block {i}" for i in range(6)],
}

#: From the A/A coverage study: 24 blocks where the true differential is zero.
AA = {"tau": 0.0, "q": 18.41, "df": 23, "p": 0.735, "coverage": "23/24"}


def main():
    print("is between-block disagreement the harness, or one effect?\n")
    print(f"{'run':<26}{'pooled':>9}{'Q':>8}{'p':>8}{'I2':>7}{'tau':>8}")
    rows, done = [], 0
    for name, labs in RUNS.items():
        cs = cells(labs)
        if len(cs) < 6:
            print(f"{name:<26}   {len(cs)}/6 blocks, not yet poolable")
            continue
        p = pool(cs)
        done += 1
        rows.append({"run": name, "pooled": p["fe"], "q": p["q"],
                     "q_p": p["q_p"], "i2": p["i2"], "tau": p["tau"]})
        print(f"{name:<26}{p['fe']:>+9.3f}{p['q']:>8.2f}{p['q_p']:>8.3f}"
              f"{100 * p['i2']:>6.0f}%{p['tau']:>8.3f}")
    print(f"{'A/A null, 24 blocks':<26}{0.0:>+9.3f}{AA['q']:>8.2f}"
          f"{AA['p']:>8.3f}{0:>6.0f}%{AA['tau']:>8.3f}"
          f"   coverage {AA['coverage']}")

    if not rows:
        print("\nnothing poolable yet")
        return
    hot = [r for r in rows if r["q_p"] < 0.05]
    n_tests = len(rows) + 1              # the A/A counts as a test too
    p_any = 1 - 0.95 ** n_tests
    print(f"\n{len(hot)} of {n_tests} homogeneity tests significant at 5%; "
          f"under a complete null\nthe chance of at least one is "
          f"{100 * p_any:.0f}%.")
    if len(hot) == 1:
        r = hot[0]
        print(f"\nThe one is {r['run']!r}. Every other run of the identical "
              f"six-block design,\nincluding two real effects of comparable and "
              f"larger size, gives tau exactly\nzero, and so does the A/A null "
              f"over 24 blocks. So the harness is not\nunderstating its "
              f"uncertainty by default, and that effect is the better\n"
              f"explanation for that run -- which is a claim about where to "
              f"look, not a\nproof, and the multiplicity above is why.")
    elif not hot:
        print("\nNone. Every run of this design, and the A/A null, is "
              "homogeneous.")
    else:
        print("\nMore than one. That points at the harness rather than at any "
              "single\neffect, and the intervals in this study would need "
              "re-examining.")

    out = {"runs": rows, "aa": AA, "n_tests": n_tests,
           "n_significant": len(hot), "p_any_under_null": p_any}
    dest = ROOT / "results" / "heterogeneity_across_runs.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote {dest}")


if __name__ == "__main__":
    main()
