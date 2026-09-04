"""Dylan's ladder, and the guard that keeps his cheat harness out of it.

The extraction itself is small -- their shim always took a SPEC line and their
factory always dispatched a ladder off it, so every released FishBot was one
string away. What needs pinning is the part that is easy to get wrong and
impossible to notice: their `v07x` base is a DELIBERATE CHEAT HARNESS, and
with no `cheat=` option it falls through to a plain V06Agent. A guard that
only looked for the word "cheat" would pass `v07x`, and would then pass
`v07x:cheat=seed` the day someone renamed the option.

A cheating agent in a strength ladder produces a number that looks exactly
like an honest one. Most of this file is therefore about refusals.
"""
import json
from pathlib import Path

import pytest

from fish4 import dylan_ladder as L

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "external_v07" / "UPSTREAM.txt"


def test_the_ladder_is_the_six_releases_in_order():
    assert L.LADDER == ("dylan_v02", "dylan_v03", "dylan_v04",
                        "dylan_v05", "dylan_v06", "dylan_v07")


def test_every_release_resolves_to_a_spec():
    for name in L.LADDER:
        spec = L.spec_for(name)
        assert spec and isinstance(spec, str)


def test_an_unknown_name_is_not_quietly_accepted():
    with pytest.raises(KeyError):
        L.spec_for("dylan_v99")


def test_the_cheat_harness_is_refused_by_base_even_with_no_cheat_option():
    """THE ONE THAT MATTERS. `v07x` alone is a V06Agent in their factory, so a
    marker-only guard would pass it -- and then pass the real cheat the day
    the option was renamed."""
    with pytest.raises(SystemExit):
        L.refuse_if_cheating("v07x")


def test_the_cheat_harness_is_refused_with_its_options():
    for spec in ("v07x:cheat=seed", "v07x:cheat=shared", "v07x:cheat=conv",
                 "v07x:det=12,cheat=seed"):
        with pytest.raises(SystemExit):
            L.refuse_if_cheating(spec)


def test_the_refusal_is_case_insensitive():
    for spec in ("V07X", "V07X:CHEAT=SEED", "v07X:Cheat=Conv"):
        with pytest.raises(SystemExit):
            L.refuse_if_cheating(spec)


def test_every_marker_trips_the_guard():
    for marker in L.CHEAT_MARKERS:
        with pytest.raises(SystemExit):
            L.refuse_if_cheating(f"v06:{marker}=1")


def test_our_own_cheaters_are_refused_by_the_same_names():
    """The markers mirror arena/roster.py, so a spec naming this project's
    oracle is refused on the way in as well as on the way out."""
    for spec in ("oracle", "oracle_gated", "v06:perfect_info=1"):
        with pytest.raises(SystemExit):
            L.refuse_if_cheating(spec)


def test_no_release_trips_its_own_guard():
    """Self-consistency: a guard that refused the ladder would be found the
    first time anyone ran it, but a guard that refused ONE rung might not."""
    for name in L.LADDER:
        L.refuse_if_cheating(L.spec_for(name))


def test_the_markers_cover_every_base_their_factory_calls_a_cheat():
    assert "v07x" in L.BARRED_BASES
    for m in ("cheat", "oracle"):
        assert m in L.CHEAT_MARKERS


def test_v04_uses_the_spec_their_manifest_records_not_a_bare_base():
    """Their research/v04 MANIFEST records policy_spec = v04:mgate=0.008.
    Running bare `v04` would measure a configuration they never published."""
    assert L.spec_for("dylan_v04") == "v04:mgate=0.008"
    assert L.spec_for("dylan_v04") != "v04"


def test_v07_still_resolves_to_the_frozen_spec_file():
    from fish4.dylan_v07 import _load_spec
    assert L.spec_for("dylan_v07") == _load_spec()
    assert L.spec_for("dylan_v07").startswith("v07:")
    assert "allparams=" in L.spec_for("dylan_v07")


def test_the_docstring_states_what_provenance_does_not_establish():
    """Their repo is here as one squashed commit, so the compiled v04/v05/v06
    vectors cannot be checked against the ones their published results used.
    That limit is stated in the module, not discovered by a reader."""
    doc = " ".join(L.__doc__.split())
    assert "SINGLE SQUASHED COMMIT" in doc
    assert "NOT a verified reproduction" in doc


def test_the_upstream_pin_is_recorded():
    assert UPSTREAM.exists()
    text = UPSTREAM.read_text().strip()
    assert "dylann4500/fishbot" in text
    assert len(text.split("@")[-1].strip()) == 40, "no full commit sha pinned"


def _binary():
    from fish4.dylan_v07 import _find_binary
    try:
        return _find_binary()
    except Exception:
        pytest.skip("their decide binary is not present")


def test_make_names_the_agent_after_the_release():
    """Otherwise a rung's numbers file themselves under dylan_v07, which is
    the hazard DylanV07's own docstring warns about."""
    _binary()
    for name in L.LADDER:
        assert L.make(name).name == name


def test_make_gives_each_release_its_own_spec():
    _binary()
    specs = {L.make(n)._spec for n in L.LADDER}
    assert len(specs) == len(L.LADDER), "two rungs share a spec"


SWEEP = ROOT / "results" / "dylan_ladder_sweep.json"


def _sweep():
    if not SWEEP.exists():
        pytest.skip("the ladder sweep has not been run")
    return json.loads(SWEEP.read_text())


def test_the_sweep_covers_the_whole_ladder():
    d = _sweep()
    assert set(d["opponents"]) == set(L.LADDER)
    assert d["descriptive"] is True
    assert d["prereg"] is None


def test_the_sweep_had_no_fallbacks_and_closed_the_identity():
    """A fallback is our arbiter substituting a move their policy did not
    make; on a strength number that is a silent thumb on the scale."""
    d = _sweep()
    for vs, o in d["opponents"].items():
        assert o["fallbacks"] == 0, vs
        assert o["unfinished"] == 0, vs
        assert o["identity_residual_max"] == 0, vs
