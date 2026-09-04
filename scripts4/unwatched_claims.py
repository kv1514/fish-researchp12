"""Which of the paper's strongest numeric claims does nothing check?

``check_paper_numbers.py`` verifies that every WATCHED figure still matches its
results file. It cannot tell you about a figure nobody thought to watch, and
that is where the real failures have been:

  * the deadlock quartet -- four bolded percentages that appeared in no results
    file at all, one of which had been consumed downstream as a decision bar;
  * the abstract's ``+1.85`` margin over the previous champion, correct but
    unwatchable because it lives in a JSONL and the loader only read JSON;
  * Table~\\ref{tab:exact}, whose rates were computed in the LaTeX from counts
    the pipeline stored, so the printed number was never a stored number.

All three were among the most load-bearing figures in the document, for the
same reason: the numbers a paper repeats most are the ones nobody re-derives.

This inverts the check. It extracts every number the paper asserts inside
``\\textbf`` -- its strongest claims, the ones a reader takes as measured --
and reports the ones the manifest does not pin. The result is a WORKLIST, not
a failure: a version number in bold is not a measurement, and the allow-list
below says which patterns are exempt and why. Anything not exempt and not
watched is a claim with nothing behind it, and should either be watched or
stop being asserted.

Usage: python scripts4/unwatched_claims.py [--strict]
``--strict`` exits 1 when anything is unexplained, for CI.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts4"))

from check_paper_numbers import PAPER, WATCH, _get, _load          # noqa: E402

#: Bold text that carries no measurement, with the reason. Matched as a
#: substring of the \textbf{...} content. A reason is required: an exemption
#: without one is indistinguishable from an oversight, which is the failure
#: this whole module is about.
EXEMPT = {
    "FishBot v0.4": "a version number",
    "FishBot v0.7": "the foreign opponent's name; its margins are watched",
    "KRAKEN v1.0": "this engine's own version; its margins are watched",
    "v0.3 sampler, 512 draws": "a configuration label; its NLL is watched",
    "v0.4 champion": "a row label",
    "v0.4 no-gamma": "a row label",
    "chained: search": "a row label; the estimate itself is watched",
    "100.0\\%": "a saturated column -- every belief-tracking agent is "
                "progress-optimal in every resolved position, so the cell is "
                "the CLAIM rather than a measurement that could drift",
}


def _norm(t: str) -> str:
    return t.replace("\\%", "%").replace("{,}", ",")


def watched_values() -> set:
    out = set()
    for fname, path, fmt, _name, _anchor in WATCH:
        try:
            out.add(fmt.format(_get(_load(fname), path)).lstrip("+"))
        except Exception:
            continue
    return out


def sweep() -> tuple[list, list]:
    text = _norm(PAPER.read_text(encoding="utf-8"))
    watched = watched_values()
    unexplained, exempt = [], []
    seen = set()
    for body in re.findall(r"\\textbf\{([^{}]*)\}", text):
        ctx = " ".join(body.split())
        why = next((r for k, r in EXEMPT.items() if _norm(k) in body), None)
        for m in re.findall(r"[-+]?\d+(?:\.\d+)?%?", body):
            val = m.lstrip("+")
            key = (val, ctx)
            if key in seen:
                continue
            seen.add(key)
            if val in watched:
                continue
            (exempt if why else unexplained).append((val, ctx, why))
    return unexplained, exempt


def main(argv: list[str]) -> int:
    unexplained, exempt = sweep()
    print("which of the paper's bolded numbers does nothing check?\n")
    if exempt:
        print(f"{len(exempt)} exempt (not measurements):")
        for val, ctx, why in exempt:
            print(f"  {val:>9}  {ctx[:40]:<42} {why[:44]}")
        print()
    if not unexplained:
        print("Every bolded number in the paper is either pinned by "
              "scripts4/check_paper_numbers.py\nor exempt with a stated "
              "reason. That is the property that failed three times.")
        return 0
    print(f"{len(unexplained)} bolded number(s) with NOTHING behind them:\n")
    for val, ctx, _ in unexplained:
        print(f"  {val:>9}   in  \\textbf{{{ctx[:58]}}}")
    print("\nEach is either a measurement that should be watched, a value that "
          "should be\nexempted with a reason, or a claim that should stop "
          "being asserted. It is not\nautomatically an error -- but a bolded "
          "number nothing can check is exactly the\nshape of every figure this "
          "project has had to retract.")
    return 1 if "--strict" in argv else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
