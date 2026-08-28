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

from fish4.brand import NAME, VERSION, FULL_NAME, FORMER_NAME, OPPONENT_NAME

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
