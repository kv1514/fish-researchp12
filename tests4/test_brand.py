"""The name lives in one place, and this fails when a copy of it drifts.

A rename that reaches the website but not the paper, or the paper but not the
handout another project is running, produces the worst outcome available: two
names for one engine and no way for a reader to tell whether they are the same
thing.  fish4/brand.py is the single source; these tests are what make it one.

The old name is checked for too.  Left behind in a user-facing file it is not a
harmless stale string -- it is a second name for the shipped engine.
"""
import pathlib
import re

import pytest

from fish4.brand import (NAME, VERSION, VERSION_NUMBER, FULL_NAME, FORMER_NAME,
                         OPPONENT_NAME, CONFIG_UNCHANGED_SINCE,
                         CONFIG_FINGERPRINT)

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: Every file that shows the name to somebody who did not write the code.
SURFACES = [
    "public/index.html",
    "public/app.js",
    "kraken/README.md",
    "kraken/decide.py",
    "paper/kraken.tex",
    "README.md",
]


@pytest.mark.parametrize("rel", SURFACES)
def test_surface_carries_the_name(rel):
    p = ROOT / rel
    assert p.exists(), f"{rel} is listed as a naming surface but does not exist"
    assert NAME in p.read_text(encoding="utf-8"), (
        f"{rel} is a user-facing surface and does not contain {NAME!r}. "
        f"Either it stopped naming the engine or the rename missed it."
    )


@pytest.mark.parametrize("rel", SURFACES)
def test_surface_does_not_carry_the_old_name(rel):
    text = (ROOT / rel).read_text(encoding="utf-8")
    # The paper and the handout may both *mention* the former name, once, to
    # tell a returning reader that this is the same engine. What they may not
    # do is go on using it.
    hits = len(re.findall(re.escape(FORMER_NAME), text))
    allowed = 1 if rel in ("paper/kraken.tex", "kraken/README.md", "README.md") else 0
    assert hits <= allowed, (
        f"{rel} uses the former name {FORMER_NAME!r} {hits} times "
        f"(at most {allowed} allowed, as a note of the rename). "
        f"The shipped engine has one name."
    )
    # The versionless "KV's FishBot" is the same problem. Check it after
    # removing the occurrences the line above already allowed, or the single
    # permitted note of the rename would trip this instead.
    rest = text.replace(FORMER_NAME, "", allowed)
    assert "KV's FishBot" not in rest and "KV&rsquo;s FishBot" not in rest, (
        f"{rel} still says \"KV's FishBot\" outside the one note of the rename."
    )


def test_full_name_is_the_two_parts():
    assert FULL_NAME == f"{NAME} {VERSION}"
    assert VERSION.startswith("v")
    assert VERSION == f"v{VERSION_NUMBER}"


#: Every literal spelling of a version that means "what you are running".
#: ``KRAKEN v1.1`` as a display label, a Python ``VERSION = "1.1"``, and a
#: manifest ``"version": "1.1"``. A version built from the constant --
#: ``f"KRAKEN v{VERSION}"`` -- is deliberately NOT matched: it cannot drift.
_LABELS = [
    re.compile(r'KRAKEN\s+v(\d+\.\d+)'),
    re.compile(r'VERSION\s*=\s*"v?(\d+\.\d+)"'),
    re.compile(r'"version"\s*:\s*"v?(\d+\.\d+)"'),
]

#: Files where a version label states what the reader is running, so every
#: label in them must be the current one. The paper is NOT here: it narrates
#: v0.4 through v1.1 and must be free to say "v1.0" about v1.0.
#:
#: The convention that makes both possible: "KRAKEN v1.0" is a claim about the
#: engine you are running and is checked; a bare "v1.0" is prose about a past
#: release and is not. So a versioned surface CAN discuss an older release --
#: kraken/README.md tells a host its v1.0 results are still comparable -- it
#: just may not put the engine's name in front of the old number.
VERSIONED_SURFACES = [
    "public/index.html",
    "README.md",
    "kraken/README.md",
    "kraken/decide.py",
    "arena/roster.py",
    "arena/README.md",
    "fishlab/fishbot.json",
    "fishlab/bot.py",
]


def _version_labels(text):
    return [m for rx in _LABELS for m in rx.findall(text)]


@pytest.mark.parametrize("rel", VERSIONED_SURFACES)
def test_surface_states_the_current_version(rel):
    """The gap this closes: brand.py said the guard checks the version, and
    for a long time it checked only the NAME. The paper reached v1.1 while
    brand.py, the site, the handout and the arena still said v1.0, and two
    shipped adapters reported DIFFERENT versions for one policy over the wire.
    Nothing failed, because nothing was looking.
    """
    p = ROOT / rel
    assert p.exists(), f"{rel} is listed as a version surface but does not exist"
    found = _version_labels(p.read_text(encoding="utf-8"))
    assert found, (
        f"{rel} is listed as a version surface and states no version at all. "
        f"Either it stopped naming the release or the pattern stopped matching "
        f"it -- and a guard that matches nothing passes silently."
    )
    stale = sorted({v for v in found if v != VERSION_NUMBER})
    assert not stale, (
        f"{rel} states version(s) {stale} but the release is {VERSION_NUMBER}. "
        f"fish4/brand.py is the single source; update the copy, not the source."
    )


def test_the_paper_titles_itself_the_current_version():
    """The paper narrates every version, so only its TITLE is pinned."""
    text = (ROOT / "paper/kraken.tex").read_text(encoding="utf-8")
    head = text[:text.index(r"\begin{document}")]
    assert f"{NAME} {VERSION}" in head, (
        f"paper/kraken.tex does not title itself {NAME} {VERSION}. The paper "
        f"is the release; if it has moved on, fish4/brand.py moves with it."
    )


def test_the_shipped_configuration_is_the_one_the_version_claims():
    """``CONFIG_UNCHANGED_SINCE`` is a claim about the tuple, so pin the tuple.

    v1.1 shipped none of its seven pre-registered directions, which is why the
    arena has one ``kraken`` entry and not two. That is only true while the
    tuple is unchanged -- so this fails the moment it changes, and whoever
    changes it has to move CONFIG_UNCHANGED_SINCE in the same commit rather
    than leave a stale sentence in three READMEs.
    """
    import hashlib
    import json

    from fish4.registry4 import V06_DEPLOYED

    key, cfg = V06_DEPLOYED
    blob = json.dumps([key, dict(sorted(cfg.items()))], separators=(",", ":"))
    got = hashlib.sha256(blob.encode()).hexdigest()[:12]
    assert got == CONFIG_FINGERPRINT, (
        f"the shipped configuration changed ({got} != {CONFIG_FINGERPRINT}).\n"
        f"  now: {blob}\n"
        f"If a knob finally cleared its pre-registered bar: set "
        f"CONFIG_UNCHANGED_SINCE = {VERSION_NUMBER!r} and CONFIG_FINGERPRINT = "
        f"{got!r} together, and give the arena its second entry -- a v1.0 and "
        f"a v1.1 that differ are finally worth duelling. If it changed by "
        f"accident, that is what this test is for."
    )
    if CONFIG_UNCHANGED_SINCE != VERSION_NUMBER:
        assert "kraken-v1.0" not in _roster_names(), (
            "the arena has a separate v1.0 entry while the two versions play "
            "the same tuple; that duel measures harness noise."
        )


def _roster_names():
    from arena.roster import ROSTER

    return set(ROSTER)


def test_both_wire_adapters_report_the_same_version():
    """A host running the handout and a host running the FishLab package must
    not be told they have two different bots. They have one.
    """
    import kraken.decide as decide
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_fishlab_bot", ROOT / "fishlab" / "bot.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert decide.VERSION == VERSION_NUMBER
    assert mod.VERSION == VERSION_NUMBER
    assert decide.decide({"op": "version"})["bot"] == FULL_NAME


def test_the_opponent_is_not_renamed():
    """Their engine is theirs; we do not get to rename it in our copy."""
    assert OPPONENT_NAME == "Dylan's FishBot v0.7"


def test_registry_resolves_both_names_to_one_class():
    """The recorded journals say "fishbot4" and new code says "kraken"."""
    from fish4.registry4 import REGISTRY, KRAKEN_V1, V06_DEPLOYED

    assert REGISTRY["kraken"] is REGISTRY["fishbot4"], (
        "kraken and fishbot4 must be the same class, or every recorded "
        "journal stops replaying to the engine that produced it."
    )
    assert KRAKEN_V1 is V06_DEPLOYED


def test_identifiers_did_not_move_with_the_name():
    """The pre-registration documents name their arms; those names are frozen.

    This is the test that stops a future tidy-up from renaming V06_DEPLOYED or
    the "fishbot4" key. A pre-registration that fixes arm A before the data is
    worth nothing if arm A can be renamed after it.
    """
    from fish4.registry4 import REGISTRY, V06_DEPLOYED

    assert V06_DEPLOYED[0] == "fishbot4", (
        "V06_DEPLOYED's registry key changed. Eight documents under prereg/ "
        "name it; they were written before the data and cannot be edited."
    )
    prereg = sorted((ROOT / "prereg").glob("*.md"))
    naming = [p.name for p in prereg if "V06_DEPLOYED" in p.read_text(encoding="utf-8")]
    assert len(naming) >= 5, (
        f"expected the pre-registration documents to still name V06_DEPLOYED; "
        f"found {len(naming)}: {naming}"
    )
    assert "fishbot4" in REGISTRY
