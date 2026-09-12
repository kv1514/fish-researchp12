"""The site links to the paper, so the link has to be checked like a route.

WHAT GOES WRONG WITHOUT THIS. The paper is served from `paper/kraken.pdf` and
NOT from `public/`, so that the repository holds exactly one copy and the site
cannot show a stale build. The price of that is three things that can silently
disagree, none of which any other test looks at:

  * `vercel.json` must name the file in `includeFiles` or it is not in the
    function bundle at all, and `/paper.pdf` 404s in production while working
    perfectly in every local check;
  * `scripts4/devserve.py` must apply the same rewrite, or the local server
    disagrees with the deployment about a route -- which is worse than having
    no local server, because the local one is trusted;
  * the page count printed beside the link is a fact about a file, and it goes
    out of date the first time the paper grows.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / "paper" / "kraken.pdf"
INDEX = ROOT / "public" / "index.html"

import sys                                                   # noqa: E402
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts4.devserve import rewrite                        # noqa: E402
from scripts4.pdfpages import page_count                     # noqa: E402


def _vercel() -> dict:
    return json.loads((ROOT / "vercel.json").read_text())


def _brace_expand(pattern: str) -> list[str]:
    """One level of `{a,b,c}`, which is all this project's glob uses.

    Vercel documents includeFiles as a node-glob pattern, and node-glob expands
    braces before matching, so `{fish/**,paper/kraken.pdf}` is two patterns.
    Expanding here rather than substring-matching is the difference between
    checking the file is NAMED and checking it is MATCHED -- a stray brace
    would leave the name present and the pattern broken.
    """
    m = re.search(r"\{([^{}]*)\}", pattern)
    if not m:
        return [pattern]
    out = []
    for alt in m.group(1).split(","):
        out += _brace_expand(pattern[:m.start()] + alt + pattern[m.end():])
    return out


def _glob_re(pattern: str) -> re.Pattern:
    """A glob alternative as a regex: `**` crosses directories, `*` does not."""
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def _matches(pattern: str, path: str) -> bool:
    return any(_glob_re(alt).match(path) for alt in _brace_expand(pattern))


def test_the_paper_is_in_the_function_bundle():
    """Vercel ships only what includeFiles names, and public/ is not it.

    MATCHED, not merely NAMED. The first attempt at this wrote
    `{fish/**,...,paper/kraken.pdf}` -- every alternative a full sub-pattern --
    and a substring check on the file name passed happily while the deployed
    function returned 404 for /paper.pdf, because that is not a form Vercel's
    glob expands. So the check is the match.
    """
    inc = _vercel()["functions"]["api/index.py"]["includeFiles"]
    assert _matches(inc, "paper/kraken.pdf"), (
        f"includeFiles {inc!r} does not match paper/kraken.pdf. The "
        f"/paper.pdf route reads that file at request time; without it in the "
        f"bundle the link 404s in production and nowhere else.")
    # And the pattern did not quietly stop shipping the code the function needs.
    for need in ("api/index.py", "fish/engine.py", "fish4/agent4.py"):
        assert _matches(inc, need), f"includeFiles no longer ships {need}"


def test_vercelignore_lets_the_paper_through():
    """includeFiles cannot include a file the upload never carried.

    `.vercelignore` kept `paper/`, so the whole directory was stripped before
    the build and includeFiles had nothing to match. Nothing failed: the build
    succeeded, the route deployed, and /paper.pdf returned the route's own 404
    on the live site while every check here passed.

    The two lines have to be exactly this shape. A bare `paper/` excludes the
    DIRECTORY, and gitignore semantics never descend into an excluded
    directory, so the negation below it would be unreachable -- which reads as
    correct and is not.
    """
    lines = [l.strip() for l in (ROOT / ".vercelignore").read_text().splitlines()
             if l.strip() and not l.strip().startswith("#")]
    assert "paper/" not in lines, (
        ".vercelignore excludes the directory `paper/`, which makes any "
        "`!paper/kraken.pdf` below it unreachable. Use `paper/*`.")
    assert "!paper/kraken.pdf" in lines, (
        ".vercelignore does not re-include paper/kraken.pdf, so it is stripped "
        "from the upload and /paper.pdf 404s in production.")
    assert "paper/*" in lines, (
        ".vercelignore no longer excludes the rest of paper/; the function "
        "bundle does not need the sources, the figures or the build logs.")


def test_a_paper_change_redeploys_the_site():
    """The ignoreCommand skips a build when no watched path changed.

    The paper is served by the function, so a rebuilt PDF with no other change
    would leave the site serving the previous deployment's copy -- indefinitely,
    since nothing else would trigger a build either.
    """
    cmd = _vercel()["ignoreCommand"]
    assert "paper/kraken.pdf" in cmd, (
        "vercel.json's ignoreCommand does not watch paper/kraken.pdf, so a "
        "rebuilt paper never reaches the site.")


def test_the_rewrite_reaches_the_route():
    """/paper.pdf goes to /api/paper, NOT straight to /api/index?op=paper.

    Measured on the deployment, one variant at a time: /paper, /paper.xyz,
    /paper.pdfx, /paper.PDF and /foo/paper.pdf all returned the PDF, and
    /paper.pdf alone returned 404 -- the single path with a rewrite rule
    pointing at `/api/index?op=paper`. A destination of /api/index is then
    re-matched by the /api/(.*) rule below it, which rebuilds the query as
    op=index, and the op the first rule set is gone. Pointing at /api/paper
    instead lets that second rule do the work it already does correctly for
    every other route.
    """
    assert rewrite("/paper.pdf") == "/api/paper"
    # And the ordinary API routing still works: a rewrite table read from the
    # real file is only useful if it did not shadow what was already there.
    assert rewrite("/api/state") == "/api/index?op=state"
    assert rewrite("/style.css") == "/style.css"


def test_both_shapes_of_the_request_route_to_the_paper():
    """The deployment and the dev server hand the function different things.

    Vercel routes on the PATH: /paper.pdf arrives as /paper.pdf, and the ?op=
    that vercel.json asks it to carry is not what decides the route. The dev
    server applies the rewrite itself and hands over ?op=paper. Nothing
    revealed the difference for the /api/ routes -- with or without the query,
    the last segment of /api/health is "health" -- and it cost a deploy to find
    out, because /paper.pdf reached the function as the route name "paper.pdf",
    matched nothing, and 404ed as though the file were missing.
    """
    from api.index import route_of
    assert route_of("/paper.pdf", "") == "paper"
    assert route_of("/api/paper", "") == "paper"
    assert route_of("/api/index", "op=paper") == "paper"
    assert route_of("/paper.pdf", "op=paper") == "paper"
    # and the routes that were already working still resolve
    assert route_of("/api/health", "") == "health"
    assert route_of("/api/index", "op=health") == "health"
    assert route_of("/api/index", "op=room_join") == "room_join"


def test_the_route_serves_the_bytes_on_disk():
    """Exercise the deployed handler's own code, not a reimplementation."""
    from api.index import handler

    sent = {}

    class Fake:
        def __init__(self):
            self.buf = bytearray()

        def write(self, b):
            self.buf.extend(b)

    fake = Fake()
    h = object.__new__(handler)
    h.wfile = fake
    h.send_response = lambda code: sent.setdefault("code", code)
    h.send_header = lambda k, v: sent.setdefault("h", {}).__setitem__(k, v)
    h.end_headers = lambda: None
    h._send_file(PDF, "application/pdf", "public, max-age=0")

    assert sent["code"] == 200
    assert sent["h"]["Content-Type"] == "application/pdf"
    assert sent["h"]["Content-Length"] == str(PDF.stat().st_size)
    assert bytes(fake.buf) == PDF.read_bytes()


def test_a_missing_file_is_a_404_and_not_a_crash():
    from api.index import handler

    sent = {}
    h = object.__new__(handler)
    h._send = lambda obj, code=200: sent.update(obj=obj, code=code)
    h._send_file(ROOT / "paper" / "no-such-paper.pdf", "application/pdf", "x")
    assert sent["code"] == 404


@pytest.mark.skipif(not PDF.exists(), reason="paper not built")
def test_the_site_states_the_papers_real_length():
    """`118 pages` on the button is a fact about a file. Facts go stale."""
    want = page_count(PDF)
    assert want > 1, (
        f"page_count read {want} pages from the committed PDF, which cannot "
        f"be right -- the counter, not the paper, is what to look at.")
    html = INDEX.read_text(encoding="utf-8")
    # `118&nbsp;pages` in the bar and `118 pages` in the strip: both are the
    # same claim, so both are checked, and the count of them is checked too --
    # a regex that stopped matching would otherwise pass by finding nothing.
    found = [int(m) for m in re.findall(r"(\d+)(?:&nbsp;| )pages", html)]
    assert len(found) >= 2, (
        f"public/index.html states {len(found)} page counts; the bar and the "
        f"paper strip both name one, so a match of fewer than two means the "
        f"pattern stopped finding them rather than that they agree.")
    wrong = sorted({f for f in found if f != want})
    assert not wrong, (
        f"public/index.html says {wrong} pages; paper/kraken.pdf has {want}. "
        f"Rebuild the site copy of the number, not the paper.")
