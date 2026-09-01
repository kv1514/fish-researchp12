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


def test_the_opportunity_is_priced_on_the_arm_that_does_not_signal():
    """The shipped arm is what prices the OPPORTUNITY each opponent creates.
    An arm that signals perturbs the trajectory it is measured on, so every
    figure about the opponent rather than the mechanism -- episodes, their
    hits on us, board ambiguity -- is read off A_shipped."""
    src = (ROOT / "scripts4" / "signal_dose_screen.py").read_text()
    assert screen.ARMS[0] == "A_shipped"
    assert "with signalling\nOFF" in src or "with signalling OFF" in src
    for key in ("episodes", "opp_asks_hit", "ambig_mean"):
        assert f'ci("{key}", "A_shipped")' in src


def test_the_arms_are_read_from_the_registry_not_retyped():
    """A retyped arm drifts from the one that was actually measured."""
    src = (ROOT / "scripts4" / "signal_dose_screen.py").read_text()
    assert "run.ALL_ARMS[arm]" in src
    assert set(screen.ARMS) <= set(run.ALL_ARMS)
    assert run.ALL_ARMS["A_shipped"] == {}


def test_it_runs_the_shipped_configuration_and_not_an_empty_dict():
    """`{}` is a different agent. Measuring the stuck state of an agent
    nobody runs would answer a question nobody asked, and the first draft of
    this screen did exactly that."""
    src = (ROOT / "scripts4" / "signal_dose_screen.py").read_text()
    assert "ours = dict(V06_DEPLOYED[1], trace=True, **run.ALL_ARMS[arm])" in src
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
                "their_hits_on_us_per_game",
                #: the two this pass exists for: whether the protocol extends
                #: the state that triggers it, and the second gate's pass rate
                "stuck_turns_ratio_signal_over_shipped",
                "fires_per_stuck_turn"):
        assert f'"{key}"' in src


def test_it_is_marked_descriptive_and_fixes_no_threshold():
    src = (ROOT / "scripts4" / "signal_dose_screen.py").read_text()
    assert "Descriptive." in src
    assert "descriptive=True" in src
    assert "is not a registration" in src
