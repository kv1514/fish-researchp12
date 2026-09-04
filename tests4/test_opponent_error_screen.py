"""The screen that decides which opponents a generality test may name.

Descriptive, so there is no verdict to pin. What has to be pinned is that it
cannot quietly include an agent that reads hidden state, that it does not share
deals with any registration it might motivate, and that the quantity it reports
is the one a generality test would need.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts4 import opponent_error_screen as screen            # noqa: E402
from scripts4 import signal_vs_defer as run                     # noqa: E402


def test_no_cheating_agent_is_in_the_table():
    """`oracle` and `oracle_gated` read hidden state. A margin against one is
    a ceiling, not a strength, and it may never sit beside an honest figure.
    Excluded here by name as well as refused by the runner, so a reader does
    not have to know the second fact to trust the first."""
    assert not set(screen.OPPONENTS) & run.BARRED_OPPONENTS
    assert not any("oracle" in o for o in screen.OPPONENTS)


def test_every_named_opponent_exists_in_the_registry():
    from fish4.registry4 import REGISTRY
    for o in screen.OPPONENTS:
        assert o in REGISTRY or o == "self", o


def test_the_runner_refuses_a_cheating_opponent_by_name():
    run.VS = "oracle_gated"
    try:
        with pytest.raises(SystemExit) as e:
            run._opponent()
        assert "hidden state" in str(e.value)
    finally:
        run.VS = "dylan_v07"


def test_the_screen_does_not_share_deals_with_any_registration():
    """A screen that motivates a run and then shares its deals has scored that
    run on its own pilot."""
    used = {r["seed"] for r in run.REGISTRATIONS.values()}
    assert screen.SEED0 not in used
    assert screen.AGENT0 not in {r["agent"] for r in run.REGISTRATIONS.values()}


def test_self_means_the_champions_own_deployed_parameters():
    from fish4.registry4 import V06_DEPLOYED
    run.VS = "self"
    try:
        kind, params = run._opponent()
        assert kind == "fishbot4"
        assert params == dict(V06_DEPLOYED[1])
        assert "signal_mode" not in params, (
            "the arm goes on OUR seats only, or it is a mirror and the margin "
            "is zero by symmetry")
    finally:
        run.VS = "dylan_v07"


def _pair(vs, deal, arm):
    run.VS, prev = vs, run.VS
    try:
        return [run._play(deal, kv, arm)["margin"] for kv in (False, True)]
    finally:
        run.VS = prev


@pytest.mark.parametrize("deal", [12_700_001, 12_700_002])
def test_symmetric_self_play_scores_exactly_zero_over_both_parities(deal):
    """The harness's own null. Identical agents on both sides of the same deal
    must split the nine half-suits the same way whichever parity we call ours,
    so the two margins are exact negatives. If this drifts, every self-play
    reading is measuring the harness."""
    a, b = _pair("self", deal, {})
    assert a == -b, (a, b)


def test_the_screen_reports_the_quantity_a_generality_test_needs():
    """Their per-declaration error rate and the headroom in it -- not just the
    margin, which is what every earlier instrument stopped at."""
    rows = [{"vs": "memory", "deal": 1, "margin": 3, "declares": 4,
             "wrong": 1, "terminal": 1, "ours": 5, "ours_wrong": 0},
            {"vs": "memory", "deal": 2, "margin": 1, "declares": 4,
             "wrong": 0, "terminal": 1, "ours": 5, "ours_wrong": 1}]
    got = screen.report(rows, 1)["opponents"]["memory"]
    assert got["their_err"] == pytest.approx(1 / 8)
    assert got["their_declares_per_game"] == pytest.approx(4.0)
    assert got["theirs_headroom"] == pytest.approx(2 * 7 / 2)
    assert got["our_err"] == pytest.approx(0.1)


def test_the_screen_says_in_its_printed_output_what_a_null_would_mean(capsys):
    """Checked on what it PRINTS, not on its source: a reader of the table
    has to be told that a floor is not a refutation, and a source-string
    assertion passes on a sentence buried in a docstring nobody sees."""
    screen.report([{"vs": "memory", "deal": 1, "margin": 3, "declares": 4,
                    "wrong": 0, "terminal": 1, "ours": 5, "ours_wrong": 0}], 1)
    out = " ".join(capsys.readouterr().out.split())
    assert "has no error rate to raise" in out
    assert "measures the floor, not the mechanism" in out


def test_the_screen_says_it_is_not_a_registration():
    src = (ROOT / "scripts4" / "opponent_error_screen.py").read_text()
    assert "is not a registration" in src
