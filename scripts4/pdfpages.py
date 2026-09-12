"""How many pages a PDF has, without a PDF library.

WHY NOT A LIBRARY. Nothing in this repository depends on one, CI installs only
what requirements files name, and adding pypdf so that one guard can read one
integer is a dependency the deployment would carry for a test. `pdfinfo` is
worse: it is present on this machine and absent on a clean runner, so the guard
that used it would SKIP in CI -- and a guard that silently skips is the failure
this project has already been bitten by once.

HOW IT WORKS. pdflatex writes the page tree into compressed object streams, so
`/Type /Page` does not appear in the raw bytes at all -- a naive grep returns
zero and would make an empty count look like a broken file. Every FlateDecode
stream is therefore inflated and searched, and the uncompressed body is searched
too for PDFs that do not use object streams.

Checked against `pdfinfo` on paper/kraken.pdf: both say 118.
"""
from __future__ import annotations

import re
import zlib
from pathlib import Path

#: `/Type /Page` but never `/Type /Pages` -- the node that counts vs the node
#: that contains it. The lookahead is what keeps the tree root out of the sum.
_PAGE = re.compile(rb"/Type\s*/Page(?![sA-Za-z])")
_STREAM = re.compile(rb"stream\r?\n")


def page_count(path: Path | str) -> int:
    data = Path(path).read_bytes()
    n = len(_PAGE.findall(data))
    for m in _STREAM.finditer(data):
        end = data.find(b"endstream", m.end())
        if end < 0:
            continue
        try:
            n += len(_PAGE.findall(zlib.decompress(data[m.end():end])))
        except zlib.error:
            # Not FlateDecode, or a stream whose /Length disagrees with the
            # keyword scan. Either way there is nothing to read here.
            continue
    return n


if __name__ == "__main__":
    import sys
    for arg in sys.argv[1:]:
        print(page_count(arg), arg)
