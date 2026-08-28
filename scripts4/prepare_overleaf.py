r"""Package the paper as an Overleaf-importable project.

Overleaf takes a .zip through "New Project -> Upload Project", so the job is to
make the source portable enough that it compiles on someone else's toolchain
first time. There is no TeX on the machine this was written on, so the checks
here stand in for a compile:

* no stray non-ASCII (a composed accent that pdflatex may or may not like,
  depending on the engine, becomes a LaTeX escape instead),
* explicit inputenc/fontenc rather than relying on a modern default,
* no packages declared that the document never uses, since an unused
  ``algorithm`` package invites a reader to look for algorithm floats,
* no ``\bibliographystyle`` next to an inline ``thebibliography``, which is
  inert but misleading.

Usage:  py scripts4/prepare_overleaf.py
"""

from __future__ import annotations

import re
import sys
import unicodedata
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEX = ROOT / "paper" / "fishbot_v06.tex"
OUT = ROOT / "paper" / "fishbot_v06_overleaf.zip"

# Packages the document loads; each maps to a command that proves it is used.
PROBES = {
    "inputenc": None, "fontenc": None, "geometry": None, "microtype": None,
    "amsmath": r"\begin{equation}", "amssymb": r"\mathbb",
    "amsthm": r"\newtheorem", "booktabs": r"\toprule",
    "hyperref": r"\texorpdfstring", "natbib": r"\citep",
    "multirow": r"\multirow", "xcolor": None,   # pulled in by hyperref colorlinks
    "graphicx": r"\includegraphics", "algorithm": r"\begin{algorithm}",
    "algpseudocode": r"\State",
}


def clean(text: str) -> tuple[str, list]:
    notes = []
    for ch in sorted({c for c in text if ord(c) > 127}):
        name = unicodedata.name(ch, "?")
        repl = {"\u00e9": r"\'e", "\u00e1": r"\'a", "\u00ed": r"\'i",
                "\u00f3": r"\'o", "\u00fa": r"\'u", "\u00e8": r"\`e",
                "\u010d": r"\v{c}", "\u0161": r"\v{s}", "\u017e": r"\v{z}"}.get(ch)
        if repl is None:
            notes.append(f"left as UTF-8: {ch!r} ({name})")
            continue
        text = text.replace(ch, repl)
        notes.append(f"escaped {ch!r} ({name}) -> {repl}")

    if r"\usepackage[utf8]{inputenc}" not in text:
        text = text.replace(r"\usepackage[margin=1in]{geometry}",
                            "\\usepackage[utf8]{inputenc}\n"
                            "\\usepackage[T1]{fontenc}\n"
                            r"\usepackage[margin=1in]{geometry}", 1)
        notes.append("added inputenc + fontenc")

    if r"\bibliographystyle" in text:
        text = re.sub(r"\\bibliographystyle\{[^}]*\}\n?", "", text)
        notes.append(r"removed \bibliographystyle (bibliography is inline)")

    for pkg, probe in PROBES.items():
        if probe is None:
            continue
        decl = "\\usepackage{%s}\n" % pkg
        if decl in text and probe not in text:
            text = text.replace(decl, "")
            notes.append(f"dropped unused package: {pkg}")
    return text, notes


def main() -> int:
    src = TEX.read_text(encoding="utf-8")
    out, notes = clean(src)
    if out != src:
        TEX.write_text(out, encoding="utf-8")
    for n in notes:
        print("  " + n)

    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("main.tex", out)          # Overleaf compiles main.tex by default
        z.writestr("README.txt",
                   "FishBot v0.4\n"
                   "============\n\n"
                   "Overleaf: New Project -> Upload Project -> drop this zip.\n"
                   "It compiles as-is with pdfLaTeX; main.tex is the only source\n"
                   "file and the bibliography is inline, so no bibtex pass and no\n"
                   "external assets are needed.\n\n"
                   "Source and the engine it describes:\n"
                   "  https://github.com/kv1514/fish-researchp12  (branch engine-v2)\n")
    n_lines = len(out.splitlines())
    print(f"\n  main.tex  {n_lines} lines, {len(out)} bytes, "
          f"{sum(1 for c in out if ord(c) > 127)} non-ASCII chars")
    print(f"  wrote {OUT}  ({OUT.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
