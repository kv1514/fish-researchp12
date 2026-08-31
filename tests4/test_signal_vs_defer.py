"""The additivity instrument must implement its registration, not resemble it.

And one thing this file exists to pin down early: the D_both arm may barely
differ from B_signal BY CONSTRUCTION. `agent4.decide` reaches the signal branch
at p_best <= signal_max_p (0.50) and the gated-declaration branch at
p_best <= 0.0, a strict subset -- so with signalling on, the gate is reachable
only when there is no stuck half-suit or no available signalling ask, and the
defer knob bites on a subset of that. A 40-game smoke run produced B and D
bit-identical. That is a fact about the mechanisms and it has to be visible in
the record rather than discovered again by whoever reads the verdict.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts4"))

from scripts4 import signal_vs_defer as run                    # noqa: E402

PREREG = (ROOT / "prereg" / "signal_vs_defer_additivity.md").read_text()


@pytest.fixture
def four_arm():
    """The additivity registration. The module defaults to the two-arm one, so
    a test about the interaction has to say which registration it is about --
    which is the whole point of making the registration an explicit selector."""
    run.select("signal_vs_defer_additivity")
    yield
    run.select("defer_gate_at_power")


def test_the_registration_predates_the_runner():
    assert "before the arms exist in any runner" in PREREG


@pytest.mark.parametrize("value", ["10,500,000", "2,000 deals x 2 parities",
                                   "+0.1435", "+0.0580"])
def test_the_registration_names_its_constants(value):
    assert value in PREREG


def test_every_registration_has_its_own_seed_and_none_is_reused():
    """Bending one instrument to a second registration by editing constants in
    place is how the 10,100,000 run's primary became someone else's -- its own
    contrast had to be computed by hand afterwards. Each registration names its
    arms, seed and primary in REGISTRATIONS, and --prereg chooses one."""
    from scripts4.signal_gate_confirm import SEED0 as CONFIRM
    from scripts4.signal_deadline import SEED0 as DESCRIPTIVE
    used = [r["seed"] for r in run.REGISTRATIONS.values()]
    assert len(set(used)) == len(used), "two registrations share a seed base"
    barred = {CONFIRM, DESCRIPTIVE, 2_400_000, 9_700_000, 9_900_000,
              10_100_000}
    assert not barred & set(used)
    assert run.REGISTRATIONS["signal_vs_defer_additivity"]["seed"] == 10_500_000
    assert run.REGISTRATIONS["defer_gate_at_power"]["seed"] == 10_900_000


def test_each_registration_declares_its_own_primary():
    a = run.REGISTRATIONS["signal_vs_defer_additivity"]
    b = run.REGISTRATIONS["defer_gate_at_power"]
    assert (a["base"], a["arm"], a["interaction"]) == ("B_signal", "D_both",
                                                       True)
    assert (b["base"], b["arm"], b["interaction"]) == ("A_shipped", "C_defer",
                                                       False)
    assert set(b["arms"]) == {"A_shipped", "C_defer"}, (
        "running the other two arms would spend an hour re-measuring what is "
        "already on disk")


def test_a_null_below_the_registered_precision_refuses_the_power_claim():
    """NULL AT POWER is a claim about PRECISION, not only about covering zero.
    An 8-deal smoke covers zero at +-0.39 and must not borrow the phrase."""
    # spread sized to what 8 deals really produces: the live smoke came back
    # +0.2500 [-0.1369, +0.6369]. The default jitter is deliberately tiny and
    # would make this interval narrow and clear of zero, testing nothing.
    wide = [0.25 + (0.5 if i % 2 else -0.5) for i in range(8)]
    rows = _rows([0.0] * 8, None, wide, None, two_arm=True)
    got = run.report(rows)
    assert "UNDERPOWERED" in got["primary"]["verdict"]
    assert "NULL AT POWER" not in got["primary"]["verdict"]
    assert got["primary"]["half_width"] > run.POWER_TARGET


def test_d_is_exactly_b_and_c_together(four_arm):
    """The interaction is only interpretable if D is the union of the two
    single interventions and nothing else."""
    assert run.ARMS["A_shipped"] == {}
    assert run.ARMS["B_signal"] == run.SIGNAL
    assert run.ARMS["C_defer"] == run.DEFER
    assert run.ARMS["D_both"] == dict(run.SIGNAL, **run.DEFER)
    assert set(run.SIGNAL) & set(run.DEFER) == set(), "the arms must not overlap"


def test_c_defer_is_the_earlier_registration_s_arm_unchanged():
    """So this run also replicates it on the current engine."""
    import json
    d = json.loads((ROOT / "results" / "stuck_gate_confirm.json").read_text())
    assert run.DEFER == d["arms"]["B_defer"]["params"]


def _rows(a, b, c, d, two_arm=False):
    """Per-game margins per arm, with distinguishable ledgers."""
    out = []
    for i in range(len(a)):
        def arm(m, gate):
            return {"margin": m, "terminal": 1, "fallbacks": 0, "signals": 0,
                    "paths": {"voluntary": [4, 0], "gate": [gate, 0]}}
        r = {"deal": i, "kv_even": 0, "rev": 2,
             "A_shipped": arm(a[i], 4), "C_defer": arm(c[i], 2)}
        if not two_arm:
            r["B_signal"] = arm(b[i], 3)
            r["D_both"] = arm(d[i], 1)
        out.append(r)
    return out


def _jitter(v, n=60, phase=0):
    """Not a constant, not identical across arms, and small.

    Three constraints, and getting any of them wrong breaks the fixture rather
    than the code. A zero-variance arm makes every interval a point, so
    `lo <= 0 <= hi` turns on whether 0.058 - 0.058 lands at 1.4e-17. Identical
    jitter in every arm does the same to the CONTRASTS, which is what is
    actually under test. And jitter large next to the effects -- +-0.5 against
    an 0.058 difference -- widens the intervals until no verdict can be
    distinguished from any other. `phase` decorrelates; the scale keeps the
    spread small relative to what the verdicts turn on.
    """
    return [v + ((i + phase) % 3 - 1) * 0.002 for i in range(n)]


def test_a_negative_interaction_is_one_effect(four_arm):
    """D gains nothing on top of B: adding the second intervention buys
    materially less than it buys alone."""
    got = run.report(_rows(_jitter(0.0, phase=0), _jitter(0.1435, phase=1), _jitter(0.0580, phase=2),
                           _jitter(0.1435, phase=1)))
    assert got["interaction"]["ci95"][1] < 0
    assert got["interaction"]["verdict"].startswith("ONE EFFECT")


def test_clean_stacking_is_two_effects(four_arm):
    got = run.report(_rows(_jitter(0.0, phase=0), _jitter(0.1435, phase=1), _jitter(0.0580, phase=2),
                           _jitter(0.2015, phase=0)))
    assert got["interaction"]["verdict"].startswith("TWO EFFECTS")
    assert got["interaction"]["d_above_b"] and got["interaction"]["d_above_c"]


def test_a_failed_replication_withdraws_the_run(four_arm):
    """B_signal must agree with +0.1435 on BOTH uncertainties -- the defect
    that withdrew an earlier run was comparing an interval to a bare point."""
    got = run.report(_rows(_jitter(0.0, phase=0), _jitter(1.5, phase=1), _jitter(0.058), _jitter(1.6, phase=2)))
    assert got["replication"]["passes"] is False
    assert got["interaction"]["verdict"].startswith("WITHDRAWN")


def test_the_replication_gate_carries_the_published_uncertainty():
    mean, half = run.REPLICATE
    assert (mean, half) == (0.1435, 0.0464)
    assert half > 0, "a target without an interval is the defect, not the gate"
    src = (ROOT / "scripts4" / "signal_vs_defer.py").read_text()
    assert "two-sample" in src


def test_identical_arms_refuse_to_report(four_arm):
    """A 40-game smoke run really did produce B and D bit-identical."""
    rows = _rows(_jitter(0.0, phase=0), _jitter(0.1, phase=1), _jitter(0.05, phase=2), _jitter(0.1, phase=1))
    for r in rows:
        r["D_both"]["paths"] = dict(r["B_signal"]["paths"])
    with pytest.raises(SystemExit) as e:
        run.report(rows)
    assert "IDENTICAL" in str(e.value)


def test_the_interaction_is_the_registered_statistic(four_arm):
    src = (ROOT / "scripts4" / "signal_vs_defer.py").read_text()
    assert '(r["D_both"]["margin"] - r["B_signal"]["margin"])' in src
    assert '- (r["C_defer"]["margin"] - r["A_shipped"]["margin"])' in src
    flat = " ".join(PREREG.split())
    assert "I = (D_both - B_signal) - (C_defer - A_shipped)" in flat


def test_the_power_limit_is_registered_in_advance():
    flat = " ".join(PREREG.split())
    assert "finely estimate a partial overlap" in flat
    assert "the honest reading is INCONCLUSIVE" in flat
