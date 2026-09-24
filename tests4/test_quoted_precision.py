"""The guard for the failure that happened twice in one day.

A figure whose uncertainty the results file records, quoted in the paper as
though it were exact. `heuristic`'s 72.52% came from a 60-deal screen good to
four points; the dose screen's stuck-turns figure carries a half-width of
1.238 and the paper prints $4.150$. Both were found by reading, which is not a
method.

These tests are mostly about the matcher's ABSTENTIONS. A guard that reports a
71% uncertainty on a figure that has none teaches everyone to ignore it, so
the cases where it must say nothing matter more than the cases where it must
speak.
"""
import subprocess
import sys
from pathlib import Path

import pytest

from scripts4 import check_quoted_precision as Q

ROOT = Path(__file__).resolve().parents[1]


def test_a_block_with_one_float_and_its_interval_has_a_sole_estimate():
    block = {"diff": 0.122, "ci95": [0.1, 0.14], "n_pairs": 2000}
    assert Q._sole_estimate(block, "diff")


def test_counts_are_not_estimates_however_they_are_named():
    """The regression: `n_pairs` slipped a name list and made the matcher
    abstain on a block holding exactly one estimate beside its interval."""
    for count_key in ("n_pairs", "trials", "positions", "k"):
        block = {"diff": 0.122, "ci95": [0.1, 0.14], count_key: 2000}
        assert Q._sole_estimate(block, "diff"), count_key


def test_a_block_with_several_estimates_has_no_sole_estimate():
    """dose_law_table.json's rows: a baseline, an observation and a
    prediction beside ONE interval, which describes only the observation."""
    block = {"baseline": 0.62, "observed": 0.0178, "predicted_refit": 0.018,
             "ci95": [0.0048, 0.0308]}
    for leaf in block:
        assert not Q._sole_estimate(block, leaf)


def test_a_non_dict_has_no_sole_estimate():
    assert not Q._sole_estimate([1, 2, 3], "x")
    assert not Q._sole_estimate(None, "x")


def test_a_name_matched_half_width_is_found():
    payload = {"a": {"fires_per_game": 2.28, "fires_half_width": 0.34,
                     "other": 1.0}}
    half, where = Q.uncertainty_for(payload, "a.fires_per_game")
    assert half == 0.34
    assert where == "a.fires_half_width"


def test_the_leaf_named_half_width_convention_is_found():
    payload = {"m": 0.5, "m_half_width": 0.1, "n": 3.0}
    half, where = Q.uncertainty_for(payload, "m")
    assert (half, where) == (0.1, "m_half_width")


def test_a_bare_interval_is_refused_when_the_block_holds_several_estimates():
    """The abstention this guard needed. Pairing a prediction with an
    observation's interval reported a 71% uncertainty on a figure that has
    none, which is how a guard gets ignored."""
    payload = {"rows": {"baseline": 0.62, "observed": 0.0178,
                        "predicted": 0.018, "ci95": [0.0048, 0.0308]}}
    assert Q.uncertainty_for(payload, "rows.predicted") is None
    assert Q.uncertainty_for(payload, "rows.baseline") is None


def test_a_bare_interval_is_accepted_when_it_can_only_be_the_one_estimate():
    payload = {"effect": {"diff": 0.122, "ci95": [0.10, 0.14],
                          "n_pairs": 2000}}
    half, _ = Q.uncertainty_for(payload, "effect.diff")
    assert half == pytest.approx(0.02)


def test_a_list_indexed_path_does_not_crash_the_matcher():
    """_get coerces a segment to int under a list, so a synthesised key like
    "0_half_width" raises ValueError there rather than missing."""
    payload = {"rows": [{"a": 1.0}, {"a": 2.0}]}
    assert Q.uncertainty_for(payload, "rows.0.a") is None


def test_the_uncertainty_pattern_matches_how_this_paper_writes_intervals():
    for s in (r"$\pm 0.05$", "±0.05", "$[+0.0048, +0.0308]$",
              "a half-width of", "inside its own interval"):
        assert Q.UNCERTAINTY.search(s), s


def test_the_uncertainty_pattern_does_not_match_arbitrary_prose():
    for s in ("the dose is 3.1 signals a game", "$4.150$ stuck turns",
              "table 3 lists five opponents"):
        assert not Q.UNCERTAINTY.search(s), s


def test_a_block_carrying_any_uncertainty_shape_is_detected():
    assert Q._block_has_uncertainty({"x": {"m": 1.0, "ci95": [0, 2]}}, "x.m")
    assert Q._block_has_uncertainty({"x": {"m": 1.0, "m_half_width": 0.5}},
                                    "x.m")
    assert not Q._block_has_uncertainty({"x": {"m": 1.0, "n": 2}}, "x.m")


def test_the_guard_runs_clean_against_the_real_paper():
    """Exit 1 means a watched figure could not be read at all, which is a
    broken manifest rather than a quoting problem."""
    r = subprocess.run([sys.executable,
                        "scripts4/check_quoted_precision.py"],
                       cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "watched figures whose results file records an uncertainty" \
        in r.stdout


def test_the_guard_reports_rather_than_fails():
    """Deliberate. A figure quoted in passing, or one whose interval is given
    in prose this cannot parse, is fine, and a rule strict enough to catch
    every real case would fail on those too. If this ever becomes a hard
    failure the docstring has to change with it."""
    src = Path(Q.__file__).read_text()
    assert "REPORTING, NOT FAILING" in src
    assert "It does not decide that a naked figure is wrong" in src
