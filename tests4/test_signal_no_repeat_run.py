"""The instrument must implement prereg/signal_no_repeat.md, not resemble it.

A registration is only worth writing if the code cannot quietly drift from it.
These tests tie the constants and the decision rule to the document, and make
the two pre-registered gates fail the run rather than decorate it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts4"))

from scripts4 import signal_no_repeat_run as run                # noqa: E402

PREREG = (ROOT / "prereg" / "signal_no_repeat.md").read_text()


def test_the_registration_exists_and_predates_the_switch():
    """The document is the authority; the code implements it."""
    assert "Registered 2026-08-31, before the switch exists" in PREREG


@pytest.mark.parametrize("value", ["9,700,000", "2,000 deals", "+2.598",
                                  "9,900,000"])
def test_the_constants_are_the_ones_the_registration_names(value):
    assert value in PREREG


REPLICATION = (ROOT / "prereg" / "signal_value_after_exhaustive.md").read_text()


@pytest.mark.parametrize("value", ["10,100,000", "2,000 deals x 2 parities",
                                   "+0.1220", "+0.0660"])
def test_the_replication_registration_names_its_constants(value):
    assert value in REPLICATION


def test_the_replication_seed_is_none_of_the_four_that_came_before():
    """3,600,000 produced the original; 9,300,000 the descriptive figures;
    9,700,000 was withdrawn; 9,900,000 produced the +0.0660 that motivates
    this one. A registration is not scored on the deals that motivated it."""
    from scripts4.signal_gate_confirm import SEED0 as ORIGINAL
    from scripts4.signal_deadline import SEED0 as DESCRIPTIVE
    assert run.SEED0 == 10_100_000
    assert run.SEED0 not in (ORIGINAL, DESCRIPTIVE, 9_700_000, 9_900_000)


def test_the_replication_states_its_own_power_limit_in_advance():
    """It can answer GONE and cannot cleanly separate SURVIVES from SHRUNK.
    Said before the run so it cannot be presented afterwards as a clean
    discrimination."""
    flat = " ".join(REPLICATION.split())
    assert "powered to answer GONE" in flat
    assert "not powered to distinguish SURVIVES from SHRUNK" in flat


def test_the_code_uses_those_constants():
    #: The seed moves with each registration this instrument serves; the
    #: current one is asserted in test_the_replication_seed_is_none_of_the_
    #: four_that_came_before, which also says why each earlier base is barred.
    assert run.N_DEALS == 2_000
    assert run.REPLICATE == 2.598


def test_the_withdrawn_run_is_kept_and_named_as_withdrawn():
    """Its primary is not evidence, but hiding it would be worse: it is what
    the gate defect was found in."""
    assert (ROOT / "results" / "signal_no_repeat_withdrawn_9700000.json"
            ).exists()
    assert "WITHDRAWN and its primary outcome is\nnot read" in PREREG


def test_the_replication_gate_uses_both_uncertainties():
    """The defect the first run exposed: comparing this run's interval against
    the published POINT means a run can FAIL by gathering more evidence."""
    src = (ROOT / "scripts4" / "signal_no_repeat_run.py").read_text()
    assert "two-sample" in src
    pm, ph, pk = run._published_margin()
    assert (round(pm, 4), pk) == (2.598, 500)
    assert ph > 0.1, "the published side must carry its own uncertainty"


def test_the_published_margin_is_read_not_retyped():
    """A retyped figure keeps agreeing after the thing it anchors to moves."""
    src = (ROOT / "scripts4" / "signal_no_repeat_run.py").read_text()
    assert "signal_gate_journal.jsonl" in src
    assert "cluster_ci([r[REPLICATE_ARM][\"margin\"] for r in rows]" in src


def test_the_seed_base_is_neither_of_the_two_that_motivated_it():
    """A registration must not be scored on the deals that produced the lead
    or on the deals that produced the descriptive figures it rests on."""
    from scripts4.signal_gate_confirm import SEED0 as LEAD
    from scripts4.signal_deadline import SEED0 as DESCRIPTIVE
    assert run.SEED0 not in (LEAD, DESCRIPTIVE)


def test_the_primary_contrast_is_the_switch_against_the_incumbent():
    """Not against A_shipped. A is there for the replication gate and to price
    the mechanism as a whole; the registered question is what the SWITCH buys
    on top of the mechanism."""
    assert (run.BASE, run.ARM) == ("B_incumbent", "C_norepeat")
    assert run.ARMS["C_norepeat"] == dict(run.ARMS["B_incumbent"],
                                          signal_no_repeat=True)


def test_the_incumbent_arm_is_arm_c_of_the_earlier_registration():
    from scripts4.signal_gate_confirm import ARMS as EARLIER
    assert run.ARMS["B_incumbent"] == EARLIER["C_measured"]
    assert run.ARMS["A_shipped"] == {}


def _rows(margins_b, margins_c, fires_b=(20, 18), fires_c=(2, 0)):
    """Minimal rows: (fires, wasted), so distinct = fires - wasted.

    B and C carry DIFFERENT path ledgers even when their margins tie, because
    the distinctness guard is supposed to fire on identical margins AND
    identical ledgers -- and a fixture that trips it would be testing the
    guard rather than the thing under test.
    """
    out = []
    for i, (mb, mc) in enumerate(zip(margins_b, margins_c)):
        def arm(m, f, gate):
            return {"margin": m, "terminal": 1, "fallbacks": 0,
                    "paths": {"voluntary": [4, 0], "gate": [gate, 0]},
                    "forced_by": {}, "fires": f[0],
                    "distinct": f[0] - f[1], "episodes": 1}
        out.append({"deal": i, "kv_even": 0, "rev": 2,
                    "A_shipped": arm(0, (0, 0), 3),
                    "B_incumbent": arm(mb, fires_b, 2),
                    "C_norepeat": arm(mc, fires_c, 1)})
    return out


def test_a_failed_replication_gate_withdraws_the_run(capsys):
    """B must cover +2.598. If it does not, the run is withdrawn rather than
    read -- exactly as the earlier registration required."""
    rows = _rows([0.0] * 40, [0.0] * 40)
    got = run.report(rows)
    assert got["replication"]["passes"] is False
    assert got["primary"]["verdict"].startswith("WITHDRAWN")
    assert "WITHDRAW" in capsys.readouterr().out


def test_a_failed_manipulation_check_withdraws_the_run():
    """A switch that does not reduce fires and waste invalidates any reading
    of the margin, however clean that margin looks."""
    rows = _rows([2.598] * 40, [2.598] * 40, fires_b=(2, 0), fires_c=(20, 18))
    got = run.report(rows)
    assert got["replication"]["passes"] is True
    assert got["manipulation"]["passes"] is False
    assert got["primary"]["verdict"].startswith("WITHDRAWN")


def test_both_gates_passing_lets_the_primary_speak():
    rows = _rows([2.598] * 40, [2.598] * 40)
    got = run.report(rows)
    assert got["replication"]["passes"] and got["manipulation"]["passes"]
    assert got["primary"]["verdict"].startswith("INCONCLUSIVE")


def test_a_clear_positive_is_a_ship_candidate_not_a_ship():
    """A ship-candidate buys a further duel; it does not enter V06_DEPLOYED
    on a single run."""
    rows = _rows([2.598] * 60, [3.598] * 60)
    got = run.report(rows)
    assert got["primary"]["verdict"].startswith("SHIP-CANDIDATE")
    assert "duel" in got["primary"]["verdict"]


def test_a_clear_negative_is_refuted():
    rows = _rows([2.598] * 60, [1.598] * 60)
    got = run.report(rows)
    assert got["primary"]["verdict"].startswith("REFUTED")


def test_identical_arms_refuse_to_report():
    """Two arms that produce identical play are not two arms. This branch has
    already reported two arms at bit-identical margins over 800 deals."""
    rows = _rows([2.598] * 40, [2.598] * 40)
    for r in rows:                       # make the ledgers identical too
        r["C_norepeat"]["paths"] = dict(r["B_incumbent"]["paths"])
    with pytest.raises(SystemExit) as e:
        run.report(rows)
    assert "IDENTICAL" in str(e.value)


def test_the_primary_is_clustered_on_the_deal():
    """Both parities of a deal share a shuffle, so the interval must rest on
    deals rather than on games."""
    src = (ROOT / "scripts4" / "signal_no_repeat_run.py").read_text()
    assert "cluster_ci(d, deals)" in src
    rows = _rows([2.598] * 40, [2.598] * 40)
    assert run.report(rows)["primary"]["n_clusters"] == 40


def test_a_smoke_run_says_so_in_the_payload():
    src = (ROOT / "scripts4" / "signal_no_repeat_run.py").read_text()
    assert 'payload["smoke"] = n_deals != N_DEALS' in src
    assert "SMOKE RUN" in src


def test_the_payload_keeps_per_game_margins():
    """Without them a contrast this registration did not fix -- B against A,
    the mechanism's own value -- can only be reported as a difference of two
    means with no interval, which is exactly what the 9,900,000 run had to do.
    """
    src = (ROOT / "scripts4" / "signal_no_repeat_run.py").read_text()
    assert 'out["games"] = [{"deal": r["deal"]' in src
    rows = _rows([2.598] * 40, [2.598] * 40)
    got = run.report(rows)
    assert len(got["games"]) == 40
    assert set(got["games"][0]) == {"deal", "kv_even", *run.ARMS}
