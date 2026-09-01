"""The screen that explains why the generality run could not answer.

Descriptive, so there is no verdict to pin. What has to be pinned is that it
measures the OPPORTUNITY rather than the mechanism, that it runs the agent
anyone actually ships, that no cheating agent can reach the table, and that
its seed bank is not one a registration has already used.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts4 import signal_dose_screen as screen               # noqa: E402
from scripts4 import signal_vs_defer as run                     # noqa: E402


def test_no_cheating_agent_is_in_the_table():
    assert not set(screen.OPPONENTS) & run.BARRED_OPPONENTS
    assert not any("oracle" in o for o in screen.OPPONENTS)


def test_it_measures_with_signalling_off():
    """The point of the screen. An arm that signals perturbs the trajectory
    it is being measured on, so the dose it reports would be its own."""
    src = (ROOT / "scripts4" / "signal_dose_screen.py").read_text()
    assert "signal_mode" not in src, "the screen must not set the protocol on"
    assert "with signalling OFF" in src


def test_it_runs_the_shipped_configuration_and_not_an_empty_dict():
    """`{}` is a different agent. Measuring the stuck state of an agent
    nobody runs would answer a question nobody asked, and the first draft of
    this screen did exactly that."""
    src = (ROOT / "scripts4" / "signal_dose_screen.py").read_text()
    assert "ours = dict(V06_DEPLOYED[1])" in src
    assert 'make_agent(("fishbot4", ours))' in src


def test_the_seed_bank_is_none_a_registration_has_used():
    used = {r["seed"] for r in run.REGISTRATIONS.values()}
    assert screen.SEED0 == 13_100_000
    assert screen.SEED0 not in used
    assert screen.SEED0 not in (2_400_000, 3_600_000, 9_300_000, 9_700_000,
                                9_900_000, 10_100_000, 12_500_000)


def test_it_covers_the_generality_grid_and_the_standard_opponent():
    """It has to price the opponents the generality run actually used, or it
    explains a dose other than the one that needs explaining."""
    run.select("signal_generality")
    try:
        assert set(run.VS_GRID) <= set(screen.OPPONENTS)
        assert "dylan_v07" in screen.OPPONENTS
    finally:
        run.select("defer_gate_at_power")


def test_the_dose_is_decomposed_rather_than_reported_whole():
    """`stuck turns a game` alone cannot distinguish getting stuck more often
    from staying stuck longer, and those have different follow-ups."""
    src = (ROOT / "scripts4" / "signal_dose_screen.py").read_text()
    for key in ("episodes_per_game", "turns_per_episode",
                "turns_after_first_stuck", "their_hits_on_us_per_game"):
        assert f'"{key}"' in src


def test_it_is_marked_descriptive_and_fixes_no_threshold():
    src = (ROOT / "scripts4" / "signal_dose_screen.py").read_text()
    assert "Descriptive." in src
    assert "descriptive=True" in src
    assert "is not a registration" in src
