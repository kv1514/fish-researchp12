"""Emit the belief-space lookahead results table, as LaTeX, from the results file.

The table in the paper is generated rather than typed, for the same reason
``summarise_duels.py`` exists: a number transcribed by hand is a number that can
drift from the run that produced it, and this project has already lost one
result to a confounded cell that nobody could reconstruct afterwards.

    py scripts4/lookahead_table.py            # print the LaTeX
    py scripts4/lookahead_table.py --plain    # the same rows, readable
    py scripts4/lookahead_table.py --write    # splice it into the paper

``--write`` edits paper/fishbot_v04.tex in place, between the sentinel comments,
rather than emitting a file to \input. That is not a style preference:
prepare_overleaf.py packages main.tex as the only source and does not follow
\input, so a separate file would ship an Overleaf bundle with a missing table
and a dangling \ref.

Every row carries the minimum effect its own cell could have resolved, so a
"null" is never read as evidence of absence when it is only absence of evidence.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
#: Per-pair standard deviation, measured over the 4800 A/A pairs of the variance
#: study rather than the 3.869 estimated earlier from far fewer. Every MDE in the
#: table below scales with it, and the settling run was powered against this
#: value, so the table has to use the same one or its "minimum resolvable effect"
#: column would disagree with the design of the run it is reporting.
SD = 3.796

#: (run label, how the paper should name the cell, which block). Order is the
#: order of the table: the screening cells first, then the retests, so the reader
#: meets the apparent winner before they meet its replication.
#:
#: Labels are matched EXACTLY. Substring matching looked fine until the retests
#: existed, at which point "lookahead d3 w0.25 vs champion" also matched
#: "REPLICATE lookahead d3 w0.25 vs champion (fresh seeds)" and the screening row
#: silently rendered the retest's numbers - a table that quietly replaces the
#: result it is supposed to be compared against is worse than no table.
ROWS = [
    ("lookahead d3 w0.25 vs champion",               r"depth 3, $w=0.25$",                 "screen"),
    ("lookahead d2 w0.25 vs champion",               r"depth 2, $w=0.25$",                 "screen"),
    ("lookahead d3 w0.60 vs champion",               r"depth 3, $w=0.60$",                 "screen"),
    ("lookahead d3 w0.25 NO coupling vs champion",   r"depth 3, \emph{no quota coupling}",  "screen"),
    ("REPLICATE lookahead d3 w0.25 vs champion (fresh seeds)",      r"depth 3, $w=0.25$ --- retest", "retest"),
    ("REPLICATE lookahead d3 w0.25 vs champion (second fresh set)", r"\quad --- retest again",       "retest"),
    ("REPLICATE coupling ablation d3 (fresh seeds)",  r"\emph{no coupling} --- retest",     "retest"),
    ("DECISIVE lookahead d3 w0.25 vs champion (A)",    r"depth 3, $w=0.25$ --- decisive A",   "decisive"),
    ("DECISIVE lookahead d3 w0.25 vs champion (B)",    r"\quad --- decisive B",               "decisive"),
] + [
    # The pre-registered settling run: six blocks of 1000, fixed in
    # jobs/PREREGISTRATION_lookahead.md before any of them ran.
    (f"SETTLE lookahead d3 w0.25 block {i}",
     (r"depth 3, $w=0.25$ --- settle, block 1" if i == 0
      else rf"\quad --- block {i + 1}"),
     "settle")
    for i in range(6)
]


def mde(n: int, sd: float = SD) -> float:
    """Smallest effect this many pairs could resolve at 80% power."""
    return float("inf") if not n else (1.959964 + 0.8416212) * sd / math.sqrt(n)


def load() -> list[dict]:
    p = ROOT / "results" / "v04_duels.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()]


def pick(rows: list[dict], label: str):
    """The most recent run with exactly this label, or None if it has not run."""
    hits = [r for r in rows if (r.get("label") or "") == label]
    return hits[-1] if hits else None


def verdict(lo: float, hi: float) -> str:
    if lo > 0:
        return "resolves"
    if hi < 0:
        return "resolves against"
    return "null"


def main(plain: bool = False) -> int:
    rows = load()
    found = [(name, kind, pick(rows, needle)) for needle, name, kind in ROWS]
    missing = [n for n, _, r in found if r is None]

    if plain:
        for name, kind, r in found:
            if r is None:
                print(f"{name:44s}  (not run)")
                continue
            lo, hi = r["diff_ci"]
            print(f"{name:44s} n={r['n_pairs']:<4d} {r['diff_mean']:+7.3f} "
                  f"[{lo:+.3f},{hi:+.3f}] MDE={mde(r['n_pairs']):.2f}  "
                  f"{verdict(lo, hi)}")
        if missing:
            print("\nnot yet run:", "; ".join(missing))
        return 1 if missing else 0

    out = [r"\begin{table}[t]", r"\centering", r"\small",
           r"\begin{tabular}{lrrlr}", r"\toprule",
           r"cell & pairs & set diff & 95\% CI & MDE \\", r"\midrule"]
    for name, kind, r in found:
        if r is None:
            continue
        if kind in ("retest", "decisive") and out[-1] != r"\midrule":
            out.append(r"\midrule")
        lo, hi = r["diff_ci"]
        bold = lo > 0 or hi < 0
        d = f"$\\mathbf{{{r['diff_mean']:+.3f}}}$" if bold else f"${r['diff_mean']:+.3f}$"
        out.append(f"{name} & {r['n_pairs']} & {d} & "
                   f"$[{lo:+.3f}, {hi:+.3f}]$ & {mde(r['n_pairs']):.2f} \\\\")
    out += [r"\bottomrule", r"\end{tabular}",
            r"\caption{Belief-space lookahead against the v0.4 champion, which is"
            r" the identical policy with the bonus disabled. MDE is the smallest"
            r" effect that cell could have resolved at 80\% power, so a null row"
            r" says the run did not detect an effect of that size, not that there"
            r" is none. This table uses the per-pair standard deviation of"
            r" $3.796$ measured over the 4800 A/A pairs reported later in this"
            r" section, rather than the $3.869$ used"
            r" elsewhere in this paper: the settling run was powered against"
            r" $3.796$, and a table reporting a run against a different"
            r" resolution from the one it was designed for would misstate what"
            r" it could see. The two differ by under $2\%$.}",
           r"\label{tab:lookahead}", r"\end{table}"]
    print("\n".join(out))
    if missing:
        print("\n% NOT YET RUN: " + "; ".join(missing), file=sys.stderr)
    return 1 if missing else 0


BEGIN = "% BEGIN lookahead-table (generated by scripts4/lookahead_table.py --write)"
END = "% END lookahead-table"


def write_into_paper() -> int:
    """Splice the table between the sentinels in the paper. Refuses if unrun."""
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        missing = main(plain=False)
    if missing:
        print("refusing to write: some cells have not run", file=sys.stderr)
        return 1
    p = ROOT / "paper" / "fishbot_v04.tex"
    s = p.read_text()
    i, j = s.find(BEGIN), s.find(END)
    if i < 0 or j < 0 or j < i:
        print("sentinels not found in the paper", file=sys.stderr)
        return 2
    p.write_text(s[:i] + BEGIN + "\n" + buf.getvalue().rstrip("\n") + "\n" + s[j:])
    print(f"spliced {buf.getvalue().count(chr(92) + chr(92))} rows into {p}")
    return 0


if __name__ == "__main__":
    if "--write" in sys.argv:
        raise SystemExit(write_into_paper())
    raise SystemExit(main(plain="--plain" in sys.argv))
