"""A structural check on the paper source, since this machine has no TeX.

Catches the errors that would stop a build: unbalanced environments, unbalanced
braces, citations with no bibliography entry, references with no label, and
duplicate labels. It is not a parser and does not pretend to be; it is the
cheapest thing that would have caught every LaTeX mistake actually made here.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

VERBATIM = ("verbatim", "lstlisting", "minted")


def strip_comments(text: str) -> str:
    out = []
    for line in text.splitlines():
        i, esc = 0, False
        cut = len(line)
        while i < len(line):
            if line[i] == "\\":
                i += 2
                continue
            if line[i] == "%":
                cut = i
                break
            i += 1
        out.append(line[:cut])
    return "\n".join(out)


def check(path: Path) -> int:
    raw = path.read_text(encoding="utf-8")
    text = strip_comments(raw)
    problems = []

    # -- environments
    stack = []
    for m in re.finditer(r"\\(begin|end)\{([^}]+)\}", text):
        kind, name = m.group(1), m.group(2)
        line = text[:m.start()].count("\n") + 1
        if kind == "begin":
            stack.append((name, line))
        else:
            if not stack:
                problems.append(f"line {line}: \\end{{{name}}} with nothing open")
            elif stack[-1][0] != name:
                problems.append(
                    f"line {line}: \\end{{{name}}} closes "
                    f"\\begin{{{stack[-1][0]}}} from line {stack[-1][1]}")
                stack.pop()
            else:
                stack.pop()
    for name, line in stack:
        problems.append(f"line {line}: \\begin{{{name}}} never closed")

    # -- braces
    depth, i = 0, 0
    line_no = 1
    while i < len(text):
        ch = text[i]
        if ch == "\n":
            line_no += 1
        elif ch == "\\":
            i += 2
            continue
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth < 0:
                problems.append(f"line {line_no}: unmatched closing brace")
                depth = 0
        i += 1
    if depth:
        problems.append(f"{depth} unclosed brace(s) at end of file")

    # -- citations vs bibliography
    bib = set(re.findall(r"\\bibitem(?:\[[^\]]*\])?\{([^}]+)\}", text))
    cited = set()
    for m in re.finditer(r"\\cite[a-zA-Z]*(?:\[[^\]]*\])*\{([^}]+)\}", text):
        cited.update(k.strip() for k in m.group(1).split(","))
    missing = sorted(cited - bib)
    unused = sorted(bib - cited)
    for k in missing:
        problems.append(f"citation with no \\bibitem: {k}")
    for k in unused:
        problems.append(f"NOTE: \\bibitem never cited: {k}")

    # -- labels and refs
    labels = Counter(re.findall(r"\\label\{([^}]+)\}", text))
    for k, n in labels.items():
        if n > 1:
            problems.append(f"duplicate label: {k} ({n} times)")
    refs = set()
    for m in re.finditer(r"\\(?:ref|eqref|autoref)\{([^}]+)\}", text):
        refs.add(m.group(1))
    for k in sorted(refs - set(labels)):
        problems.append(f"reference to a missing label: {k}")

    # -- a few common breakages
    if "\\begin{document}" not in text:
        problems.append("no \\begin{document}")
    if "\\end{document}" not in text:
        problems.append("no \\end{document}")

    hard = [p for p in problems if not p.startswith("NOTE:")]
    print(f"{path}: {len(text.splitlines())} lines, "
          f"{len(labels)} labels, {len(bib)} bibliography entries, "
          f"{len(cited)} distinct citations")
    for p in problems:
        print("  " + p)
    if not hard:
        print("  no structural problems found")
    return 1 if hard else 0


if __name__ == "__main__":
    paths = [Path(a) for a in sys.argv[1:]] or [
        Path(__file__).resolve().parents[1] / "paper" / "fishbot_v04.tex"]
    sys.exit(max(check(p) for p in paths))
