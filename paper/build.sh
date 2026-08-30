#!/usr/bin/env bash
# Build paper/kraken.pdf.
#
# Recorded because a clean container could not build this paper, and the
# failures were not self-explanatory:
#
#   multirow.sty not found          -> texlive-latex-extra
#   "auto expansion is only possible with scalable fonts"
#                                   -> cm-super
#     microtype + [T1]{fontenc} wants Type1 CM fonts; without cm-super the
#     T1 fallback is bitmap, and pdflatex dies with NO output PDF rather
#     than degrading to unexpanded text.
#
# Three passes: hyperref/natbib need two to settle refs, and the third is
# what makes "0 undefined" mean something rather than "not yet resolved".
set -euo pipefail

need() { command -v "$1" >/dev/null || { echo "missing: $1"; exit 1; }; }
need pdflatex

cd "$(dirname "$0")"
for i in 1 2 3; do
  pdflatex -interaction=nonstopmode kraken.tex > "/tmp/paper_pass$i.log" 2>&1 || true
done

log=/tmp/paper_pass3.log
if [ ! -f kraken.pdf ]; then
  echo "no PDF produced; last errors:"
  grep -E '^! ' "$log" | head
  exit 1
fi

# An unresolved \ref renders as "??" and reads like a typo, so it is checked
# rather than eyeballed.
bad=$(grep -cE 'Reference .* undefined|Citation .* undefined' "$log" || true)
pages=$(grep -oE '\([0-9]+ pages' "$log" | tail -1 | tr -d '(' )
echo "built kraken.pdf — $pages, $bad undefined reference(s)/citation(s)"
[ "$bad" -eq 0 ] || { echo "refusing to call that a clean build"; exit 1; }
