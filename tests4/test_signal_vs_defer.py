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
                    "paths": {"voluntary": [4, 0], "gate": [gate, 0]},
                    "opp_declares": 4, "opp_wrong": 1}
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


def test_the_opponent_s_declarations_are_counted():
    """Every instrument in this line dropped them, and the smoke says they are
    where the volume is: the opponent misdeclares about 0.95 times a game
    against our 0.14. A margin that moves without OUR ledger moving has to be
    somewhere, and this is the first place to look."""
    src = (ROOT / "scripts4" / "signal_vs_defer.py").read_text()
    assert '"opp_declares": opp[0], "opp_wrong": opp[1]' in src
    # and the drop is gone: the old form skipped opponent claims entirely
    assert "if not isinstance(ev, ClaimEvent) or not ours:" not in src


def test_the_descriptive_registration_is_marked_descriptive():
    """It fixes no threshold and decides no ship, and the code says so rather
    than leaving a reader to infer it from the absence of a prereg file."""
    src = (ROOT / "scripts4" / "signal_vs_defer.py").read_text()
    block = src[src.index('"where_the_margin_lives"') - 700:
                src.index('"where_the_margin_lives"')]
    assert "DESCRIPTIVE, not a registration" in block
    r = run.REGISTRATIONS["where_the_margin_lives"]
    assert r["seed"] == 11_300_000
    assert set(r["arms"]) == {"A_shipped", "B_signal", "C_defer"}, (
        "signalling and deferral were never played on the same deals; that is "
        "the omission this pairing exists to fix")


# --- prereg/signal_budget.md, and the three withdrawal conditions ----------

BUDGET = (ROOT / "prereg" / "signal_budget.md").read_text()


@pytest.fixture()
def budget():
    run.select("signal_budget")
    yield
    run.select("defer_gate_at_power")


def test_the_budget_registration_names_its_arms_and_seed(budget):
    assert run.SEED0 == 11_700_000 and run.AGENT0 == 117_000
    assert (run.BASE, run.ARM) == ("B_uncapped", "C_budget6")
    assert run.ARMS["B_uncapped"] == run.SIGNAL
    assert run.ARMS["C_budget6"] == dict(run.SIGNAL, signal_budget=6)
    assert run.ARMS["D_budget2"] == dict(run.SIGNAL, signal_budget=2)


def test_the_budget_seed_is_none_of_the_nine_the_registration_bars(budget):
    barred = {r["seed"] for k, r in run.REGISTRATIONS.items()
              if k != "signal_budget"}
    assert run.SEED0 not in barred | {2_400_000, 3_600_000, 9_300_000,
                                      9_700_000, 9_900_000, 10_100_000}


def test_the_uncapped_control_is_the_same_parameters_as_b_signal(budget):
    """Renamed, not re-tuned: a different incumbent would make the
    replication gate compare two different things."""
    assert run.ARMS["B_uncapped"] == run.ALL_ARMS["B_signal"]


def _game(d_us: int, w_us: int, w_them: int, gate: int = 1) -> dict:
    """One possible game, built from the identity rather than asserted at.

    A real per-game margin is `2*(d_us - w_us + w_them) - 9`, an odd integer
    between -9 and +9, and every count below is a whole declaration. So these
    rows are games that could actually have been played, and the identity
    closes on them by construction rather than by a fixture that was tuned
    until the check went quiet.
    """
    vol = d_us - gate
    return {"margin": 2 * (d_us - w_us + w_them) - 9, "terminal": 1,
            "fallbacks": 0, "signals": 0,
            "paths": {"voluntary": [vol, 0], "gate": [gate, w_us]},
            "opp_declares": 9 - d_us, "opp_wrong": w_them}


def _budget_rows(n=200, hi_a=0.72, hi_c=0.75, sig=(8.0, 5.0, 1.8)):
    """Two-point mixtures: `hi_*` is the share of games won by one more set.

    A margin near +2.4 is a mix of +3 and +1 games, and moving the share moves
    the mean by 2 * the share -- which is how a real contrast of a few
    hundredths is actually made.
    """
    out = []
    for i in range(n):
        f = (i + 0.5) / n

        def arm(hi, gate):
            return (_game(5, 0, 1, gate) if f < hi else _game(5, 1, 1, gate))
        out.append({"deal": i, "kv_even": 0, "rev": 2,
                    "A_shipped": arm(0.60, 4),
                    "B_uncapped": arm(hi_a, 3),
                    "C_budget6": arm(hi_c, 2),
                    "D_budget2": arm(0.64, 1)})
    for name, s in zip(("B_uncapped", "C_budget6", "D_budget2"), sig):
        for r in out:
            r[name]["signals"] = s
    return out


def _payload(rows):
    got = run.report(rows)
    got["n_deals"] = len(rows)
    return got


def test_the_fixture_is_made_of_games_that_could_have_been_played(budget):
    """If the fixture cheated, every identity test below would be vacuous."""
    for r in _budget_rows(20):
        for arm in run.ARMS:
            g = r[arm]
            d_us = sum(n for n, _ in g["paths"].values())
            w_us = sum(w for _, w in g["paths"].values())
            assert d_us + g["opp_declares"] == 9
            assert g["margin"] == 2 * (d_us - w_us + g["opp_wrong"]) - 9
            assert g["margin"] % 2 == 1


def test_all_three_withdrawal_checks_pass_on_a_clean_run(budget):
    got = _payload(_budget_rows())
    assert got["replication"]["passes"]
    assert got["manipulation"]["passes"]
    assert got["identity"]["passes"], got["identity"]["problems"]
    assert not got["primary"].get("withdrawn")


def test_a_failed_replication_withdraws_the_budget_run(budget):
    """B_uncapped must reproduce the +0.1435 the registration rests on."""
    got = _payload(_budget_rows(hi_a=0.60))     # B identical to A: no effect
    assert got["replication"]["passes"] is False
    assert got["primary"]["verdict"].startswith("WITHDRAWN")
    assert "replication" in got["primary"]["verdict"]


def test_a_cap_that_did_not_bind_withdraws_the_budget_run(budget):
    """Signals a game must fall strictly B > C > D. An arm whose knob never
    landed has been reported twice in this project already."""
    got = _payload(_budget_rows(sig=(8.0, 8.0, 1.8)))
    assert got["manipulation"]["strictly_decreasing"] is False
    assert got["primary"]["verdict"].startswith("WITHDRAWN")


def test_a_cap_exceeded_withdraws_the_budget_run(budget):
    """Strictly decreasing is not enough: `signal_budget=2` that averages 3.5
    a game means the counter is not counting what the name says."""
    got = _payload(_budget_rows(sig=(9.0, 7.0, 3.5)))
    assert got["manipulation"]["strictly_decreasing"] is True
    assert got["manipulation"]["within_cap"] == {"C_budget6": False,
                                                 "D_budget2": False}
    assert got["primary"]["verdict"].startswith("WITHDRAWN")


def test_a_ledger_that_loses_a_declaration_withdraws_the_budget_run(budget):
    """The defect the identity exists to catch: a declaration path that the
    instrument does not record. The margin still looks fine."""
    rows = _budget_rows()
    for r in rows:
        r["C_budget6"]["paths"]["gate"] = [0, 0]      # drop the gate path
    got = _payload(rows)
    assert got["identity"]["passes"] is False
    assert any("is not 9" in p for p in got["identity"]["problems"])
    assert got["primary"]["verdict"].startswith("WITHDRAWN")


def test_the_identity_check_only_runs_where_a_registration_asks_for_it():
    """The registrations that predate the identity cannot be held to a gate
    they never agreed to, and a gate nobody chose is a gate nobody owns."""
    declared = {k for k, r in run.REGISTRATIONS.items() if r.get("identity")}
    assert declared == {"signal_budget", "signal_generality"}
    predates = {"signal_vs_defer_additivity", "defer_gate_at_power",
                "where_the_margin_lives"}
    assert not declared & predates


def test_the_primary_line_says_it_is_provisional_where_gates_follow(budget,
                                                                    capsys):
    _payload(_budget_rows())
    assert "PROVISIONAL" in capsys.readouterr().out


# --- the opponent axis ----------------------------------------------------

@pytest.fixture()
def generality():
    run.select("signal_generality")
    yield
    run.select("defer_gate_at_power")


def test_the_generality_registration_names_a_grid_and_its_own_size(generality):
    assert run.VS_GRID == ("probabilistic", "memory", "self")
    assert run.REGISTERED_N == 800
    assert run.SEED0 == 12_100_000
    assert set(run.ARMS) == {"A_shipped", "B_signal"}


def test_a_registration_without_a_grid_has_no_opponent_to_choose():
    """`--vs=` on a fixed-opponent registration would be picking the opponent
    after the registration, which is the same defect as picking the arm."""
    for name, r in run.REGISTRATIONS.items():
        if name == "signal_generality":
            continue
        assert "vs_grid" not in r and "vs" not in r


def test_the_sample_size_is_the_registrations_and_not_the_files(generality):
    """Self-play and the weaker policies cost a different amount a game, so
    N_DEALS is a default and not a constant every registration inherits."""
    assert run.REGISTERED_N != run.N_DEALS
    run.select("defer_gate_at_power")
    assert run.REGISTERED_N == run.N_DEALS


def test_every_registration_declares_a_size_that_is_used(generality):
    for name in run.REGISTRATIONS:
        run.select(name)
        assert run.REGISTERED_N >= 400, name
