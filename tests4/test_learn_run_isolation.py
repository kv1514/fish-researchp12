"""A second learning run must not land on the first one's files.

Every number the paper quotes for the objective-learning line lives in
``results/ask_objective_fit.json`` and ``fish4/learn/FIT.md``. The stages MERGE
into the results file rather than replacing it, so a second run writing to the
same path would not overwrite it cleanly -- it would leave a file that is partly
one experiment and partly another, with nothing in it saying which parts are
which. That is worse than losing it.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts4"))

from learn_ask_objective import (PRIMARY_RUN, REPORT, RESULTS,  # noqa: E402
                                 report_path, results_path)


def test_the_primary_run_keeps_the_unsuffixed_names():
    assert results_path(PRIMARY_RUN) == RESULTS
    assert report_path(PRIMARY_RUN) == REPORT


def test_any_other_run_gets_its_own_files():
    for run in ("v2", "v3", "strong-continuation"):
        r, m = results_path(run), report_path(run)
        assert r != RESULTS, f"run {run!r} would write over the primary results"
        assert m != REPORT, f"run {run!r} would write over the primary report"
        assert run in r.name and run in m.name
        assert r.parent == RESULTS.parent and m.parent == REPORT.parent


def test_saving_a_run_records_which_run_it_was(tmp_path, monkeypatch):
    """A results file that does not name its run is one nobody can audit."""
    import json

    import learn_ask_objective as L
    monkeypatch.setattr(L, "RESULTS", tmp_path / "ask_objective_fit.json")
    L.save_results({"fit": {"x": 1}}, "v2")
    got = json.loads((tmp_path / "ask_objective_fit_v2.json").read_text())
    assert got["run"] == "v2"
    assert not (tmp_path / "ask_objective_fit.json").exists()
