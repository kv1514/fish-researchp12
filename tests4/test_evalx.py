"""Tests for the v0.4 evaluation infrastructure.

Runtime budget: the whole file is meant to stay under ~90 seconds, which
constrains two things. Real games are expensive, so the game-playing tests
use small n and the cheapest policy pair that still plays real Literature;
and the type-I simulation runs at a reduced repetition count here (the full
>= 4000-rep version lives in ``scripts4/run_typeI_simulation.py`` and its
numbers are quoted in ``fish4/evalx/README.md``). The reduced version still
monitors after EVERY observation, so it fails loudly if the stopping rule is
ever made invalid.

MEASURED: 49 s on an otherwise idle machine, 97 s while a 4-worker study was
running alongside. If it grows past that, the first thing to check is which
policies the harness tests are using - see the note on FAST_X/FAST_Y below.
"""

from __future__ import annotations

import json
import math
import threading
from pathlib import Path

import numpy as np
import pytest

from fish.eval.tournament import _t_critical as _t_critical_v03
from fish.eval.tournament import play_matchup
from fish4.evalx import ablation as ab
from fish4.evalx import registry as reg
from fish4.evalx import sequential as sq
from fish4.evalx.harness import (ConfigMismatch, HarnessConfig, MAX_WORKERS,
                                 PairRecord, PairedResult, TooManyDrops,
                                 _t_critical, _variance_report, load_log,
                                 run_paired)

# The harness is what is under test, not the policies, so the cheapest pair
# that still plays real Literature is the right one. MEASURED at 4 workers=1:
# heuristic-vs-random costs 0.13 s per pair, memory-vs-heuristic 13 s. Using
# the latter (the obvious "two real policies" choice) put this file at 325 s;
# it is now under a minute for the same coverage.
FAST_X = ("heuristic", {})
FAST_Y = ("random", {})


def _cfg(**kw) -> HarnessConfig:
    base = dict(spec_x=FAST_X, spec_y=FAST_Y, n_pairs=4, base_seed=7,
                agent_seed_base=1, n_workers=1)
    base.update(kw)
    return HarnessConfig(**base)


# ===========================================================================
# harness: the pairing guarantee
# ===========================================================================

def test_matches_v03_tournament_exactly():
    """With one seat per deal this harness must reproduce v0.3 exactly.

    This is what makes the two generations of results comparable. If it ever
    breaks, either the pairing changed or the seed plumbing did, and every
    number in PAPER.md becomes incommensurable with the new ones.
    """
    res = run_paired(_cfg(n_pairs=4), progress=False)
    old = play_matchup(FAST_X, FAST_Y, n_deals=4, n_jobs=1, base_seed=7,
                       agent_seed_base=1)
    assert [float(d) for d in res.diffs] == [float(d) for d in old.per_deal_diffs]


def test_run_is_reproducible_from_recorded_seeds():
    a = run_paired(_cfg(n_pairs=3), progress=False)
    b = run_paired(_cfg(n_pairs=3), progress=False)
    assert a.diffs == b.diffs
    assert [r.agent_seed for r in a.records] == [r.agent_seed for r in b.records]


def test_per_pair_differentials_are_exposed():
    """v0.3 dropped the per-deal vector from ``to_dict`` and it could not be
    recovered from a saved result; every sequential test needs it."""
    res = run_paired(_cfg(n_pairs=3), progress=False)
    assert len(res.diffs) == res.n_pairs == 3
    assert all(isinstance(d, float) for d in res.diffs)


# ===========================================================================
# harness: timeouts
# ===========================================================================

def test_incomplete_pairs_are_dropped_and_counted():
    """A 20-action cap guarantees every game times out, so every pair must be
    dropped and none may leak into the statistics."""
    res = run_paired(_cfg(max_actions=20, max_drop_rate=0.0), progress=False)
    assert res.n_pairs == 0
    assert res.dropped_pairs == 4
    assert res.attempted_pairs == 4
    assert res.drop_rate == 1.0
    assert all(r.seat_diffs == [] for r in res.dropped)
    # and the drop count leads the summary rather than trailing it
    assert res.summary().startswith("[4 dropped / 4 attempted")


def test_too_many_drops_refuses_to_report():
    res = run_paired(_cfg(max_actions=20, max_drop_rate=0.0), progress=False)
    with pytest.raises(TooManyDrops, match="biased subsample"):
        res.check_drops()


def test_clean_run_passes_the_drop_check():
    run_paired(_cfg(n_pairs=2), progress=False).check_drops()


# ===========================================================================
# harness: resumable log
# ===========================================================================

def test_resume_reuses_pairs_and_reproduces_the_full_run(tmp_path: Path):
    log = tmp_path / "run.jsonl"
    run_paired(_cfg(n_pairs=2), log_path=log, progress=False)
    resumed = run_paired(_cfg(n_pairs=5), log_path=log, progress=False)
    fresh = run_paired(_cfg(n_pairs=5), progress=False)
    assert resumed.reused_pairs == 2
    assert resumed.diffs == fresh.diffs, (
        "a resumed run must be identical to an uninterrupted one, or the log "
        "is a source of silent drift")


def test_resume_refuses_a_different_configuration(tmp_path: Path):
    log = tmp_path / "run.jsonl"
    run_paired(_cfg(n_pairs=2), log_path=log, progress=False)
    with pytest.raises(ConfigMismatch, match="Refusing to mix"):
        run_paired(_cfg(n_pairs=2, base_seed=999), log_path=log, progress=False)


def test_log_survives_a_torn_final_line(tmp_path: Path):
    log = tmp_path / "run.jsonl"
    run_paired(_cfg(n_pairs=3), log_path=log, progress=False)
    with open(log, "a", encoding="utf-8") as f:
        f.write('{"index": 99, "deal_seed": 1, "partial')     # killed mid-write
    header, records = load_log(log)
    assert header is not None
    assert len(records) == 3


def test_fingerprint_ignores_n_pairs_but_not_the_seeds():
    """Extending a run must reuse its log; changing what is played must not."""
    assert _cfg(n_pairs=4).fingerprint() == _cfg(n_pairs=400).fingerprint()
    assert _cfg(n_pairs=4).fingerprint() != _cfg(n_pairs=4,
                                                 base_seed=8).fingerprint()
    assert _cfg().fingerprint() != _cfg(seat_offsets=(0, 3)).fingerprint()
    assert _cfg().fingerprint() != _cfg(spec_y=("memory", {})).fingerprint()


# ===========================================================================
# harness: workers and configuration validation
# ===========================================================================

def test_worker_count_is_clamped():
    """This machine has 8 cores and other jobs; over-requesting is clamped."""
    assert _cfg(n_workers=32).n_workers == MAX_WORKERS
    assert _cfg(n_workers=0).n_workers == 1


@pytest.mark.parametrize("bad", [(), (0, 0), (0, 9)])
def test_bad_seat_offsets_are_rejected(bad):
    with pytest.raises(ValueError):
        _cfg(seat_offsets=bad)


def test_diff_bound_matches_the_deck():
    """The sequential tests' validity rests on this bound: a pair sums two
    games of at most 9 half-suits each."""
    assert _cfg().diff_bound == 18.0
    from fish.rules import RuleConfig
    assert _cfg(rules=RuleConfig(variant="48").to_dict()).diff_bound == 16.0


# ===========================================================================
# harness: seat rotation and its variance accounting
# ===========================================================================

def test_seat_rotation_records_one_differential_per_seat():
    res = run_paired(_cfg(n_pairs=2, seat_offsets=(0, 3)), progress=False)
    assert res.config.games_per_pair == 4
    for rec in res.records:
        assert len(rec.seat_diffs) == 2
        assert rec.diff == pytest.approx(sum(rec.seat_diffs) / 2)


def test_variance_report_recovers_a_known_correlation():
    """Synthetic seat matrices with a known intra-deal correlation.

    rho > 0 (replicates agree) must report compute-matched efficiency < 1:
    rotation loses to playing more independent deals. rho < 0 must report
    efficiency > 1. Getting this backwards would make the harness recommend
    the technique precisely when it hurts.
    """
    rng = np.random.default_rng(0)
    n, r = 1200, 3

    deal = rng.normal(0, 1, (n, 1))                # shared component
    pos = (deal + rng.normal(0, 0.5, (n, r))).tolist()
    vr_pos = _variance_report(pos, n_boot=60)
    assert vr_pos.intra_deal_corr > 0.5
    assert vr_pos.compute_matched_ratio < 1.0
    assert vr_pos.per_deal_ratio < 1.0             # averaging always helps/deal
    assert vr_pos.helped is False

    # exactly antithetic: the R seats of a deal sum to zero
    ab = rng.normal(0, 1, (n, 2))
    neg = np.column_stack([ab, -ab.sum(axis=1)]).tolist()
    vr_neg = _variance_report(neg, n_boot=60)
    assert vr_neg.intra_deal_corr < 0
    assert vr_neg.compute_matched_ratio > 1.0
    assert vr_neg.helped is True


def test_variance_report_summary_names_the_verdict():
    rng = np.random.default_rng(1)
    rows = [[float(x) for x in rng.normal(0, 1, 2)] for _ in range(50)]
    s = _variance_report(rows, n_boot=100).summary()
    assert "compute-matched efficiency" in s
    assert "intra-deal corr" in s


# ===========================================================================
# harness: statistics
# ===========================================================================

def _synthetic_result(values, **cfgkw) -> PairedResult:
    cfg = _cfg(n_pairs=len(values), **cfgkw)
    res = PairedResult(config=cfg, wall_clock_s=1.0)
    for i, v in enumerate(values):
        res.records.append(PairRecord(index=i, deal_seed=i, base_seat=0,
                                      agent_seed=i, seat_diffs=[v]))
    return res


def test_t_critical_agrees_with_v03():
    for df in (4, 5, 10, 30, 100, 1000):
        assert _t_critical(df) == pytest.approx(_t_critical_v03(df), abs=1e-12)


def test_diff_ci_uses_sample_variance_and_t():
    res = _synthetic_result([2, -1, 3, 0, 1])
    mean, lo, hi = res.diff_mean_ci()
    assert mean == pytest.approx(1.0)
    # sample sd 1.5811, se 0.7071, t(4) = 2.776 -> +/- 1.963
    assert lo == pytest.approx(1.0 - 1.963, abs=0.02)
    assert hi == pytest.approx(1.0 + 1.963, abs=0.02)


def test_pair_score_counts_ties_as_half():
    res = _synthetic_result([1, 1, 0, -1])
    assert res.pair_score() == pytest.approx(0.625)
    lo, hi = res.wilson_ci()
    assert 0 < lo < 0.625 < hi < 1


def test_mde_and_pairs_needed_are_inverses():
    res = _synthetic_result([3, -1, 2, 0, 1, 4, -2, 2])
    n = res.pairs_needed(0.5)
    assert res.min_detectable_effect(n) <= 0.5 + 1e-9
    assert res.min_detectable_effect(n - 1) > 0.5


def test_to_dict_round_trips_through_json():
    res = _synthetic_result([1, 2, -1])
    blob = json.dumps(res.to_dict())
    d = json.loads(blob)
    assert d["n_pairs"] == 3
    assert d["dropped_pairs"] == 0
    assert "sd_diff" in d and "config_fingerprint" in d


# ===========================================================================
# sequential: the procedures themselves
# ===========================================================================

def test_out_of_range_observation_raises_rather_than_voiding_validity():
    cs = sq.EmpiricalBernsteinCS(lower=-18, upper=18)
    with pytest.raises(sq.OutOfBounds):
        cs.update([19.0])
    bt = sq.BettingTest(lower=-18, upper=18)
    with pytest.raises(sq.OutOfBounds):
        bt.update([-25.0])


def test_cs_covers_the_true_mean_and_tightens():
    rng = np.random.default_rng(4)
    cs = sq.EmpiricalBernsteinCS(alpha=0.05, lower=-18, upper=18)
    widths = []
    for i in range(600):
        lo, hi = cs.update([float(np.clip(rng.normal(1.0, 4.0), -18, 18))])
        assert lo[0] <= 1.0 <= hi[0], f"missed the true mean at t={i}"
        widths.append(float(hi[0] - lo[0]))
    assert widths[-1] < widths[20] / 3


def test_running_intersection_never_widens():
    rng = np.random.default_rng(5)
    cs = sq.EmpiricalBernsteinCS(lower=-18, upper=18)
    prev = None
    for _ in range(200):
        lo, hi = cs.update([float(rng.normal(0, 3))])
        if prev is not None:
            assert lo[0] >= prev[0] - 1e-12 and hi[0] <= prev[1] + 1e-12
        prev = (float(lo[0]), float(hi[0]))


def test_vectorized_streams_match_the_scalar_path():
    """The calibration simulation runs many experiments in lockstep; it is
    only evidence about the live procedure if the two are the same code."""
    rng = np.random.default_rng(6)
    data = rng.normal(0.5, 4.0, size=(120, 5)).clip(-18, 18)
    vec_cs = sq.EmpiricalBernsteinCS(lower=-18, upper=18, n_streams=5)
    vec_bt = sq.BettingTest(lower=-18, upper=18, n_streams=5)
    for t in range(data.shape[0]):
        vec_cs.update(data[t])
        vec_bt.update(data[t])
    for s in range(5):
        cs = sq.EmpiricalBernsteinCS(lower=-18, upper=18)
        bt = sq.BettingTest(lower=-18, upper=18)
        for t in range(data.shape[0]):
            cs.update([data[t, s]])
            bt.update([data[t, s]])
        assert cs.interval()[0][0] == pytest.approx(vec_cs.interval()[0][s])
        assert cs.interval()[1][0] == pytest.approx(vec_cs.interval()[1][s])
        assert float(bt.log_e_value[0]) == pytest.approx(
            float(vec_bt.log_e_value[s]))


def test_sequential_test_reports_a_direction_and_stops():
    rng = np.random.default_rng(7)
    t = sq.SequentialTest(alpha=0.05, lower=-18, upper=18, n_max=4000)
    out = t.run(float(np.clip(rng.normal(2.0, 4.0), -18, 18))
                for _ in range(4000))
    assert out.decision == "x_better"
    assert out.stopped and out.n < 4000
    assert "log10(e)" in out.summary()


def test_sequential_test_says_inconclusive_rather_than_guessing():
    rng = np.random.default_rng(8)
    t = sq.SequentialTest(alpha=0.05, lower=-18, upper=18, n_max=60)
    out = t.run(float(np.clip(rng.normal(0.0, 4.0), -18, 18)) for _ in range(60))
    assert out.decision == "inconclusive"


# ===========================================================================
# sequential: calibration (reduced; the full run is in scripts4/)
# ===========================================================================

TYPE_I_REPS = 1500
TYPE_I_STEPS = 600


@pytest.mark.parametrize("method", ["betting", "eb_cs"])
def test_type_i_error_under_continuous_monitoring(method):
    """Monitored after EVERY observation, against a skewed null with the
    same sd as real paired differentials.

    The assertion is on the Clopper-Pearson UPPER limit rather than the point
    estimate, so the test fails when the procedure is genuinely invalid and
    not merely when the simulation was unlucky.
    """
    r = sq.simulate_type_i(sq.two_point_sampler(4.0, skew=0.95),
                           n_reps=TYPE_I_REPS, n_max=TYPE_I_STEPS, alpha=0.05,
                           lower=-18, upper=18, method=method, seed=31337)
    lo, hi = r.binomial_ci()
    assert hi <= 0.05, (f"{method} false-positive rate {r.rate:.3%} "
                        f"(95% CI upper {hi:.3%}) exceeds alpha=5% under "
                        f"continuous monitoring")


def test_type_i_holds_for_a_gaussian_null_too():
    r = sq.simulate_type_i(sq.gaussian_sampler(4.0, half_range=18.0),
                           n_reps=TYPE_I_REPS, n_max=TYPE_I_STEPS,
                           method="betting", seed=999)
    assert r.binomial_ci()[1] <= 0.05


def test_naive_peeking_is_wildly_miscalibrated():
    """The comparator, and the reason this module exists: the fixed-n 95%
    t-interval peeked at every step rejects a true null far above 5%."""
    r = sq.simulate_type_i(sq.gaussian_sampler(4.0, half_range=18.0),
                           n_reps=600, n_max=TYPE_I_STEPS, method="naive_t",
                           seed=1234)
    assert r.rate > 0.20, r.summary()


def test_power_against_a_realistic_alternative():
    """sd 4.0 is the order of the measured per-pair sd; 1.0 sets/pair is an
    effect a strategy change can plausibly produce. Power must be high and
    every rejection must point the right way."""
    r = sq.simulate_power(sq.gaussian_sampler(4.0, mean=1.0, half_range=17.0),
                          n_reps=400, n_max=3000, method="betting", seed=55)
    assert r.correct_rate > 0.80, r.summary()
    assert r.n_correct_sign == r.n_rejected, "a rejection pointed the wrong way"
    assert r.median_stop < 3000


def test_betting_stops_sooner_than_the_confidence_sequence():
    kw = dict(n_reps=300, n_max=4000, seed=77)
    bet = sq.simulate_power(sq.gaussian_sampler(4.0, mean=0.5, half_range=17.0),
                            method="betting", **kw)
    cs = sq.simulate_power(sq.gaussian_sampler(4.0, mean=0.5, half_range=17.0),
                           method="eb_cs", **kw)
    assert bet.correct_rate >= cs.correct_rate
    assert bet.median_stop <= cs.median_stop


def test_empirical_sampler_has_the_requested_mean():
    vals = [3, -1, 7, 0, 2, 9, -4]
    s = sq.empirical_sampler(vals, mean=0.0)
    drawn = s(np.random.default_rng(0), 200, 400)
    assert abs(float(drawn.mean())) < 0.15
    shifted = sq.empirical_sampler(vals, mean=0.3)(
        np.random.default_rng(0), 200, 400)
    assert abs(float(shifted.mean()) - 0.3) < 0.15


def test_clopper_pearson_matches_known_values():
    lo, hi = sq._clopper_pearson(50, 1000)
    assert lo == pytest.approx(0.03734, abs=2e-4)
    assert hi == pytest.approx(0.06539, abs=2e-4)
    assert sq._clopper_pearson(0, 2000)[0] == 0.0
    assert sq._clopper_pearson(2000, 2000)[1] == 1.0


def test_regularized_incomplete_beta_matches_known_values():
    assert sq._betainc_regularized(1, 1, 0.5) == pytest.approx(0.5, abs=1e-6)
    assert sq._betainc_regularized(2, 3, 0.3) == pytest.approx(0.3483, abs=1e-4)


# ===========================================================================
# ablation guard
# ===========================================================================

def test_tuned_with_zero_weights_reduces_to_the_baseline():
    """The v0.3 confound, generalized: audited at all six seats rather than
    one, so a term that only bites in specific seats cannot hide."""
    rep = ab.assert_reduces_to_baseline(("probabilistic", {}), ("tuned", {}),
                                        n_games=2, seed=11)
    assert rep.identical
    assert rep.n_positions > 100, "too few positions to be evidence"


def test_a_confounded_candidate_is_caught_and_the_position_is_named():
    """A candidate that also perturbs the suit-depth term is exactly the v0.3
    bug; the failure must be actionable, not just loud."""
    with pytest.raises(ab.AblationDivergence) as exc:
        ab.assert_reduces_to_baseline(("probabilistic", {}),
                                      ("tuned", {"w_suit": 0.01}),
                                      n_games=2, seed=11)
    msg = str(exc.value)
    assert "ABLATION IS CONFOUNDED" in msg
    assert "first divergence at game" in msg
    assert "ply" in msg and "seat p" in msg
    assert "baseline chose" in msg and "candidate chose" in msg
    assert "compare two changes at once" in msg


def test_a_switched_on_weight_actually_changes_decisions():
    rep = ab.check_parameter_has_effect(("tuned", {}),
                                        ("tuned", {"w_turn": 0.6}),
                                        n_games=2, seed=11)
    assert rep.n_divergences > 0
    assert 0.0 < rep.divergence_rate < 1.0
    assert rep.first_divergence is not None


def test_a_parameter_with_no_effect_is_rejected():
    """An ablation of a term that changes nothing can only ever report 'no
    significant difference', which reads like evidence and is not."""
    with pytest.raises(ab.AblationDivergence, match="MEASURES NOTHING"):
        ab.assert_parameter_has_effect(("tuned", {}),
                                       ("tuned", {"w_deplete": 0.0}),
                                       n_games=1, seed=11)


def test_min_rate_flags_a_term_too_rare_to_measure():
    with pytest.raises(ab.AblationDivergence, match="too rare"):
        ab.assert_parameter_has_effect(("tuned", {}), ("tuned", {"w_turn": 0.6}),
                                       n_games=1, seed=11, min_rate=0.99)


# ===========================================================================
# registry
# ===========================================================================

def _rec(**kw) -> reg.ExperimentRecord:
    base = dict(name="t", kind="matchup",
                agent_specs={"x": ["tuned", {}], "y": ["probabilistic", {}]},
                harness_config={"n_pairs": 4},
                seeds={"deal_seed_base": 1, "agent_seed_base": 2},
                result={"mean_diff": 1.0, "diff_ci95": [0.1, 1.9]},
                wall_clock_s=2.5, evidence_tier="PROMISING")
    base.update(kw)
    return reg.ExperimentRecord(**base)


def test_record_captures_provenance(tmp_path: Path):
    p = tmp_path / "e.jsonl"
    r = reg.record(_rec(), path=p)
    row = reg.load_all(p)[0]
    assert row["id"] == r.id and len(r.id) == 12
    assert row["schema"] == reg.SCHEMA_VERSION
    assert row["commit"] and row["python"] and row["platform"]
    assert row["seeds"]["deal_seed_base"] == 1
    assert row["seeds"]["agent_seed_base"] == 2
    assert row["result"]["diff_ci95"] == [0.1, 1.9]
    assert row["wall_clock_s"] == 2.5
    assert isinstance(row["dirty_worktree"], bool)
    assert row["retracted"] is False


def test_a_record_without_both_seed_streams_is_refused(tmp_path: Path):
    with pytest.raises(reg.RegistryError, match="seeds is required"):
        reg.record(_rec(seeds={}), path=tmp_path / "e.jsonl")


def test_an_unknown_evidence_tier_is_refused(tmp_path: Path):
    with pytest.raises(reg.RegistryError, match="evidence_tier"):
        reg.record(_rec(evidence_tier="PRETTY SURE"), path=tmp_path / "e.jsonl")


def test_retraction_appends_and_never_rewrites(tmp_path: Path):
    p = tmp_path / "e.jsonl"
    r = reg.record(_rec(name="wrong"), path=p)
    before = p.read_bytes()
    reg.retract(r.id, "confounded ablation", by="tester", path=p)
    after = p.read_bytes()
    assert after.startswith(before), "the original record was modified"
    row = reg.load_all(p)[0]
    assert row["retracted"] is True
    assert row["retraction"]["reason"] == "confounded ablation"
    assert row["retraction"]["by"] == "tester"
    assert "RETRACTED" in reg.summary(p)
    assert reg.load_all(p, include_retracted=False) == []


def test_retraction_requires_a_reason_and_a_real_target(tmp_path: Path):
    p = tmp_path / "e.jsonl"
    r = reg.record(_rec(), path=p)
    with pytest.raises(reg.RegistryError, match="must state a reason"):
        reg.retract(r.id, "   ", path=p)
    with pytest.raises(reg.RegistryError, match="no experiment with id"):
        reg.retract("deadbeef0000", "nope", path=p)


def test_verify_flags_structural_damage(tmp_path: Path):
    p = tmp_path / "e.jsonl"
    reg.record(_rec(), path=p)
    assert reg.verify(p) == []
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps({"schema": "from-the-future/9", "id": "x",
                            "record_kind": "experiment",
                            "evidence_tier": "PROMISING",
                            "seeds": {"a": 1}}) + "\n")
        f.write(json.dumps({"schema": reg.SCHEMA_VERSION,
                            "record_kind": "retraction", "id": "y",
                            "targets": "nobody", "reason": "r"}) + "\n")
    problems = reg.verify(p)
    assert any("unknown schema" in s for s in problems)
    assert any("unknown id" in s for s in problems)


def test_concurrent_appends_do_not_interleave(tmp_path: Path):
    """Two scripts recording at once is the normal state of this project."""
    p = tmp_path / "e.jsonl"
    errors = []

    def worker(i):
        try:
            for k in range(5):
                reg.record(_rec(name=f"w{i}-{k}"), path=p)
        except Exception as exc:                       # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 20
    for ln in lines:
        json.loads(ln)                                  # no torn lines
    assert len({r["id"] for r in reg.load_all(p)}) == 20


def test_record_paired_result_pulls_both_seed_streams(tmp_path: Path):
    p = tmp_path / "e.jsonl"
    res = _synthetic_result([1, 2, 3])
    r = reg.record_paired_result("calib", res, kind="calibration", path=p)
    row = reg.get(r.id, p)
    assert row["seeds"]["deal_seed_base"] == res.config.base_seed
    assert row["seeds"]["agent_seed_base"] == res.config.agent_seed_base
    assert row["agent_specs"]["x"][0] == FAST_X[0]
    assert row["result"]["sd_diff"] == pytest.approx(res.sd_diff())
    assert row["harness_config"]["seat_offsets"] == [0]


def test_unparseable_lines_are_skipped_not_fatal(tmp_path: Path):
    p = tmp_path / "e.jsonl"
    reg.record(_rec(), path=p)
    with open(p, "a", encoding="utf-8") as f:
        f.write('{"schema": "evalx-registry/1", "id": "torn')
    assert len(reg.load_all(p)) == 1


# ===========================================================================
# the measured numbers quoted in the README must exist and be consistent
# ===========================================================================

CALIB = Path(__file__).resolve().parents[1] / "results" / \
    "v04_eval_calibration.json"


@pytest.mark.skipif(not CALIB.exists(),
                    reason="run scripts4/measure_calibration.py first")
def test_published_calibration_is_internally_consistent():
    d = json.loads(CALIB.read_text())
    assert d["n_pairs"] >= 150
    assert d["dropped_pairs"] == 0 or d["dropped_pairs"] / d["n_pairs"] < 0.05
    sd = d["sd_per_pair"]
    assert 0.5 < sd < 18.0
    assert np.std(d["per_pair_diffs"], ddof=1) == pytest.approx(sd, rel=1e-9)
    # the MDE table must be the stated formula at the stated sd
    z = 1.959963985 + 0.841621234                       # z_.975 + z_.80
    for row in d["mde_table"]:
        want = math.ceil((z * sd / row["effect_sets_per_pair"]) ** 2)
        assert row["pairs_for_80pct_power"] == want


# ---------------------------------------------------------------------------
# The harness has to be able to measure its own null
# ---------------------------------------------------------------------------

def test_an_A_A_is_degenerate_under_the_default_seat_seeding():
    """Documents the limitation the independent-seeds option exists for.

    With seat-based seeding, one spec against a copy of itself plays a
    bit-identical game in both halves of a pair, so the differential is
    (a - b) + (b - a) = 0 for every deal. That is not a small effect correctly
    measured as zero - it is a point mass, and no amount of sampling learns
    anything from it about how much a cell's estimate moves run to run.
    """
    from fish4.match import play_matchup
    spec = ("fishbot4", {"opponent_gamma": 0.35})
    res = play_matchup(spec, spec, n_deals=6, n_jobs=1, base_seed=5000,
                       agent_seed_base=77)
    assert res.diffs == [0] * 6


def test_independent_seeds_make_the_null_measurable():
    """The same A/A becomes a real random variable, centred on zero."""
    from fish4.match import play_matchup
    spec = ("fishbot4", {"opponent_gamma": 0.35})
    res = play_matchup(spec, spec, n_deals=10, n_jobs=1, base_seed=5000,
                       agent_seed_base=77, independent_seeds=True)
    assert any(d != 0 for d in res.diffs), "still degenerate"
    assert any(d > 0 for d in res.diffs) and any(d < 0 for d in res.diffs)


def test_independent_seeds_are_off_by_default():
    """Turning this on changes every number the harness produces.

    ``results/v04_duels.jsonl`` was built without it, so the default has to stay
    put or the archive stops being comparable with anything measured later.
    """
    import inspect
    from fish4.match import play_matchup
    sig = inspect.signature(play_matchup)
    assert sig.parameters["independent_seeds"].default is False


def test_a_side_carries_its_seeds_into_both_halves_of_the_pair():
    """Seeded by position within the side, not by seat.

    A policy must meet both halves of a duplicate deal with the same randomness,
    or the pairing that the whole design rests on is broken.
    """
    from fish4.match import side_seeds
    a, b = side_seeds(12345, 0), side_seeds(12345, 1)
    assert len(a) == len(b) == 3
    assert not (set(a) & set(b)), "the two sides drew a common seed"
    assert side_seeds(12345, 0) == a, "not reproducible"


def test_per_pair_differentials_survive_serialisation():
    """Without these a run's raw observations cannot be re-analysed at all."""
    from fish4.match import play_matchup
    spec = ("fishbot4", {"opponent_gamma": 0.35})
    res = play_matchup(spec, spec, n_deals=5, n_jobs=1, base_seed=5100,
                       agent_seed_base=9, independent_seeds=True)
    d = json.loads(json.dumps(res.to_dict()))
    assert d["diffs"] == list(res.diffs)
    assert len(d["diffs"]) == d["n_pairs"]
