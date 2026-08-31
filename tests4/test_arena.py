"""The arena's guard rails.

The one that matters is the cheat guard: this repository contains agents that
see the true deal, they exist to price a ceiling, and a ceiling number in a
strength ladder is indistinguishable in print from an honest one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arena.roster import (ROSTER, CHEATERS, CheatingAgentRefused, resolve,
                          default_field)
from arena.report import render_matrix


def test_no_cheating_agent_is_in_the_roster():
    for name, entry in ROSTER.items():
        head = entry["spec"][0]
        assert name not in CHEATERS
        assert head not in CHEATERS


def test_the_guard_refuses_a_cheating_agent_added_by_name():
    ROSTER["_probe"] = {"spec": ("oracle_gated", {}), "blurb": "x"}
    try:
        with pytest.raises(CheatingAgentRefused):
            resolve("_probe")
    finally:
        ROSTER.pop("_probe")


def test_the_guard_refuses_a_future_oracle_a_denylist_would_miss():
    """A name-only denylist would pass `oracle_v2`. The substring check is the
    point: the guard has to survive someone adding a new cheating agent."""
    ROSTER["_probe2"] = {"spec": ("oracle_v2_perfect_info", {}), "blurb": "x"}
    try:
        with pytest.raises(CheatingAgentRefused):
            resolve("_probe2")
    finally:
        ROSTER.pop("_probe2")


def test_every_default_field_entry_resolves():
    for name in default_field():
        spec = resolve(name)
        assert isinstance(spec, tuple) and len(spec) == 2


def test_unknown_policy_names_the_known_ones():
    with pytest.raises(KeyError) as e:
        resolve("no-such-policy")
    assert "kraken" in str(e.value)


def test_kraken_resolves_to_the_deployed_champion():
    """If V06_DEPLOYED moves, the arena must follow it rather than pin a
    stale copy -- otherwise the headline policy silently stops being the
    shipped one."""
    from fish4.registry4 import V06_DEPLOYED
    assert resolve("kraken") == V06_DEPLOYED


def test_the_report_flags_a_structural_diagonal():
    """The diagonal note has to be present, because a 50.0% diagonal under the
    harness DEFAULT is a tautology rather than a check."""
    t = {"field": ["a", "b"], "n_deals_per_cell": 10,
         "cells": {"a|a": {"win_rate": 0.5, "margin": 0.0},
                   "a|b": {"win_rate": 0.7, "margin": 1.0},
                   "b|a": {"win_rate": 0.3, "margin": -1.0},
                   "b|b": {"win_rate": 0.5, "margin": 0.0}}}
    out = render_matrix(t)
    assert "INDEPENDENTLY" in out
    assert "50.0%" in out


def test_tournament_declares_its_two_design_choices():
    """Both are load-bearing and both are easy to lose in a refactor."""
    import arena.tournament as T
    src = Path(T.__file__).read_text()
    assert "independent_seeds=True" in src
    assert "base_seed + 1000 * i" in src, "cells must not share deals"
