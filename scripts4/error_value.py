"""What is one avoided misdeclaration actually worth, and what does deferring
a declaration cost when it avoids nothing?

Two experiments in this project moved a declaration ledger decisively and a
set margin not at all: the doomed-ask gate (`prereg/stuck_claim_gate.md`,
wrong declarations -0.0640 [-0.0847, -0.0433], margin +0.0580 [-0.0177,
+0.1337]) and, earlier, the signalling protocol (nulls down 20%, margin
+0.002 [-0.086, +0.090] in the void era). Both were filed as "a real
reduction that buys no sets", which is honest and is not an explanation.

There is a cheap explanation and this measures it. A paired margin is a NET.
An arm that defers declarations does two things at once:

    it avoids some errors            worth +v sets each
    it leaves half-suits live        which costs something per deferral

and the sum is what the duel reports. Regressing the paired margin difference
on the paired ERROR difference separates them: the slope is v, and the
intercept is what the treatment does in games where it avoided no error at
all -- the tempo it spends for nothing.

Both are things this project has assumed rather than measured. The two-sets
arithmetic used throughout (`scripts4/margin_decomposition.py`, both
pre-registrations) is the assumption v = 2, from the award rule: a
misdeclared set goes to the opponents, so getting it right instead is a
two-set swing. That is right about the SET and silent about the position.

WHAT THE INTERCEPT IS, precisely. It is the paired treatment effect on the
deals where the arm avoided no error. Both arms play every deal, so dw is a
deterministic function of the deal and conditioning on it selects DEALS rather
than assignments -- which makes the estimate causal on that subpopulation. It
is not "the cost of deferring in general": the subpopulation is selected by an
outcome, and deals where no error was avoided defer about 30% less often than
average. The per-deferral figure therefore divides by that subpopulation's own
deferral rate, not the overall one.

Reads the journal a paired arm-vs-arm runner already wrote. Costs no games.

    py scripts4/error_value.py [journal.jsonl] [--arms A,B,...]
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# This module reads only results files, so it never needed the repository on
# sys.path -- until it started importing a sibling. Run as a script,
# `python3 scripts4/error_value.py` puts scripts4/ on the path and not the root
# above it, so `import scripts4.journal` fails. The unit test did not catch it
# because pytest already has the root on the path: a module that imports
# cleanly under test can still be a broken script.
sys.path.insert(0, str(ROOT))

from scripts4.journal import result_for  # noqa: E402
DEFAULT = ROOT / "results" / "stuck_gate_journal.jsonl"
BASE = "A_shipped"
#: the value the rest of the project assumes, from the award rule
ASSUMED = 2.0


def _wrong(row, arm):
    return sum(w for _, w in row[arm]["paths"].values())


def _deferred(row, arm, path="gate"):
    a = row[BASE]["paths"].get(path, [0, 0])[0]
    b = row[arm]["paths"].get(path, [0, 0])[0]
    return a - b


def fit(rows, arm) -> dict:
    """OLS of the paired margin difference on the paired error difference."""
    n = len(rows)
    x = [_wrong(r, arm) - _wrong(r, BASE) for r in rows]
    y = [r[arm]["margin"] - r[BASE]["margin"] for r in rows]
    mx, my = sum(x) / n, sum(y) / n
    sxx = sum((v - mx) ** 2 for v in x)
    if sxx == 0:
        return {"arm": arm, "error": "the arm avoided the same number of "
                                     "errors in every game"}
    sxy = sum((u - mx) * (v - my) for u, v in zip(x, y))
    b = sxy / sxx
    a = my - b * mx
    resid = [v - a - b * u for u, v in zip(x, y)]
    s2 = sum(e * e for e in resid) / (n - 2)
    se_b = (s2 / sxx) ** 0.5
    se_a = (s2 * (1.0 / n + mx * mx / sxx)) ** 0.5
    # v is the value of avoiding ONE error, and x counts errors added, so the
    # slope's sign flips
    v, se_v = -b, se_b
    # The deferral rate ON THE DEALS THE INTERCEPT DESCRIBES, not overall.
    # The intercept is the treatment effect where dw == 0, and those deals
    # defer LESS than average -- fewer deferrals means fewer chances to avoid
    # an error, so the selection is not neutral. Dividing the intercept by the
    # overall rate understated the per-deferral cost by about 30%.
    zero = [r for r, d in zip(rows, x) if d == 0]
    defer = (sum(_deferred(r, arm) for r in zero) / len(zero)) if zero else 0.0
    defer_all = sum(_deferred(r, arm) for r in rows) / n

    # The same question without a linear model, because the regressor takes
    # about four values and a straight line through four levels is close to a
    # two-point comparison anyway. The pairing is what makes this causal: both
    # arms play the identical deal, so "games where the error count did not
    # change" is a property of the DEAL, not of an assignment.
    cuts = {}
    for lab, keep in (("no error avoided", lambda d: d == 0),
                      ("one avoided", lambda d: d == -1),
                      ("two or more avoided", lambda d: d <= -2),
                      ("errors ADDED", lambda d: d > 0)):
        sub = [v for u, v in zip(x, y) if keep(u)]
        if not sub:
            continue
        m = sum(sub) / len(sub)
        se = (st.pstdev(sub) / len(sub) ** 0.5) if len(sub) > 1 else 0.0
        cuts[lab] = {"n": len(sub), "mean": m,
                     "ci95": [m - 1.96 * se, m + 1.96 * se]}
    return {
        "cuts": cuts,
        "arm": arm, "n_games": n,
        "value_per_avoided_error": {
            "est": v, "ci95": [v - 1.96 * se_v, v + 1.96 * se_v],
            "assumed": ASSUMED,
            "excludes_assumed": bool(v + 1.96 * se_v < ASSUMED
                                     or v - 1.96 * se_v > ASSUMED)},
        "cost_when_it_avoids_nothing": {
            "est": a, "ci95": [a - 1.96 * se_a, a + 1.96 * se_a]},
        "errors_avoided_per_game": -mx,
        "declarations_deferred_per_game": defer_all,
        "deferred_per_game_where_no_error_avoided": defer,
        "cost_per_deferral": (a / defer if defer else None),
        "margin": my,
        "reconstructed": a + b * mx,
    }


def report(rows, arms) -> dict:
    out = {"n_games": len(rows), "assumed_value": ASSUMED, "arms": {}}
    print(f"\n=== what an avoided misdeclaration is worth ({len(rows):,} "
          f"games) ===")
    print("  the margin an arm reports is a NET: errors avoided times their\n"
          "  value, MINUS whatever deferring costs when it avoids nothing\n")
    for arm in arms:
        f = fit(rows, arm)
        out["arms"][arm] = f
        if "error" in f:
            print(f"  {arm}: {f['error']}")
            continue
        v = f["value_per_avoided_error"]
        c = f["cost_when_it_avoids_nothing"]
        print(f"  {arm}")
        print(f"    value of one avoided error   {v['est']:+.4f}  "
              f"[{v['ci95'][0]:+.4f}, {v['ci95'][1]:+.4f}]   "
              f"(assumed {ASSUMED})")
        print(f"    cost when it avoids nothing  {c['est']:+.4f}  "
              f"[{c['ci95'][0]:+.4f}, {c['ci95'][1]:+.4f}]")
        print(f"    errors avoided/game {f['errors_avoided_per_game']:+.4f}"
              f"   declarations deferred/game "
              f"{f['declarations_deferred_per_game']:+.4f}")
        if f["cost_per_deferral"] is not None:
            print(f"    -> {f['cost_per_deferral']:+.4f} sets per deferred "
                  f"declaration, dividing by the "
                  f"{f['deferred_per_game_where_no_error_avoided']:.4f} "
                  f"deferrals/game on the deals the intercept describes")
        print(f"    net {f['margin']:+.4f}, reconstructed "
              f"{f['reconstructed']:+.4f}")
        print(f"    the same thing without a model, paired margin by how "
              f"many errors the arm avoided:")
        for lab, c in f["cuts"].items():
            print(f"      {lab:<22} n={c['n']:<5} {c['mean']:+.4f}  "
                  f"[{c['ci95'][0]:+.4f}, {c['ci95'][1]:+.4f}]")
    return out


def main(path=None, arms=None) -> int:
    p = Path(path or DEFAULT)
    if not p.exists():
        print(f"{p} not found")
        return 1
    rows = [json.loads(l) for l in p.read_text().splitlines() if l.strip()]
    if not rows:
        print("empty journal")
        return 1
    arms = arms or [k for k in rows[0]
                    if isinstance(rows[0][k], dict) and k != BASE
                    and "margin" in rows[0][k]]
    out = report(rows, arms)
    out["journal"] = p.name
    dest = result_for(p, canonical_journal=Path(DEFAULT),
                      canonical_name="error_value.json")
    dest.write_text(json.dumps(out, indent=1))
    print("\nwrote", dest.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    a = [x for x in argv if not x.startswith("--")]
    kw = {}
    for f in (x for x in argv if x.startswith("--")):
        k, _, v = f[2:].partition("=")
        if k != "arms":
            raise SystemExit(f"unknown flag --{k}")
        kw["arms"] = [z for z in v.split(",") if z]
    raise SystemExit(main(a[0] if a else None, **kw))
