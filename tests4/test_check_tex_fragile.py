r"""`check_tex` must catch a fragile command inside a caption.

On 2026-08-30 it reported "no structural problems found" on `paper/kraken.tex`
and `pdflatex` then died with ``\url used in a moving argument``: a rewritten
caption used ``\path``, which expands to ``\url`` and is fragile in the moving
argument ``\caption`` writes to the list of tables. The failure is reported at
the caption's CLOSING brace, several lines after the offending command, which
is why it is worth catching before the build rather than reading off a log.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts4"))

from scripts4.check_tex import check

HEAD = "\\documentclass{article}\n\\begin{document}\n"
TAIL = "\\end{document}\n"


def _run(tmp_path, body, name="t.tex"):
    p = tmp_path / name
    p.write_text(HEAD + body + TAIL)
    return check(p)


def test_path_in_a_caption_is_flagged(tmp_path, capsys):
    rc = _run(tmp_path, "\\begin{table}\n\\caption{See \\path{a/b_c.py}.}\n"
                        "\\end{table}\n")
    out = capsys.readouterr().out
    assert "moving argument" in out
    assert rc == 1


def test_texttt_in_a_caption_is_fine(tmp_path, capsys):
    """The repository's own convention, and it must not be flagged."""
    rc = _run(tmp_path, "\\begin{table}\n"
                        "\\caption{See \\texttt{a/b\\_c.py}.}\n\\end{table}\n")
    out = capsys.readouterr().out
    assert "moving argument" not in out
    assert rc == 0


def test_path_in_body_text_is_fine(tmp_path, capsys):
    """`\\path` is used in body text throughout the paper and is correct there.
    A check that flagged it everywhere would be turned off within a day."""
    rc = _run(tmp_path, "Ordinary prose citing \\path{scripts4/thing.py} here.\n")
    out = capsys.readouterr().out
    assert "moving argument" not in out
    assert rc == 0


def test_url_and_verb_in_a_caption_are_flagged_too(tmp_path, capsys):
    for cmd in ("\\url{http://x}", "\\verb|x|"):
        rc = _run(tmp_path, "\\begin{figure}\n\\caption{" + cmd + "}\n"
                            "\\end{figure}\n", name=f"c{len(cmd)}.tex")
        out = capsys.readouterr().out
        assert "moving argument" in out, cmd
        assert rc == 1


def test_a_caption_with_nested_braces_finds_its_own_end(tmp_path, capsys):
    """The scan matches braces, so a caption containing groups must not run on
    into the rest of the document and flag a `\\path` that is really in body
    text after it."""
    rc = _run(tmp_path, "\\begin{table}\n"
                        "\\caption{A \\textbf{bold {nested} bit} and no more.}\n"
                        "\\end{table}\nProse with \\path{a/b.py} after it.\n")
    out = capsys.readouterr().out
    assert "moving argument" not in out
    assert rc == 0


def test_the_real_paper_is_clean(capsys):
    assert check(ROOT / "paper" / "kraken.tex") == 0
