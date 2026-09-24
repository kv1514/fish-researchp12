"""The prereg-backing guard must actually fail on the case that motivated it.

`f8abe6d` recorded two outcomes and committed no results file, so four figures
that gate the whole convention direction lived only in prose. The guard written
for that is only worth its runtime if it fires on that shape and not on a
healthy one, so both directions are asserted here against synthetic trees
rather than against the repository, which can be fixed under the test.

The interesting case is the third: a document that names its INSTRUMENT and no
file. That is exactly what the two convention pre-registrations did, and it has
to fail, because the instrument's default output existed the whole time holding
a different run.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts4"))

import check_prereg_backing as g                                 # noqa: E402


@pytest.fixture
def tree(tmp_path, monkeypatch):
    """A fake repository root with a prereg/ and results/ under it."""
    (tmp_path / "prereg").mkdir()
    (tmp_path / "results").mkdir()
    monkeypatch.setattr(g, "ROOT", tmp_path)
    monkeypatch.setattr(g, "PREREG", tmp_path / "prereg")
    return tmp_path


def write(tree, name, text):
    (tree / "prereg" / name).write_text(text)


def test_an_outcome_with_no_results_file_is_unbacked(tree):
    write(tree, "a.md", "# Pre-registration\n\n# OUTCOME\n\nIt was -0.0535.\n")
    assert g.main(strict=True) == 1


def test_an_outcome_naming_a_present_file_is_backed(tree):
    (tree / "results" / "a.json").write_text("{}")
    write(tree, "a.md",
          "# Pre-registration\n\n# OUTCOME\n\n`results/a.json`: -0.0535.\n")
    assert g.main(strict=True) == 0


def test_naming_the_instrument_is_not_enough(tree):
    """The defect this guard exists for, stated exactly.

    Both convention pre-registrations named `scripts4/convention_posterior.py`
    and its default output existed -- holding the exploratory run those very
    documents were written to supersede. A script says how a number could be
    made, not which run made it.
    """
    (tree / "results" / "instrument_default.json").write_text("{}")
    write(tree, "a.md", "# Pre-registration\n\n"
          "`scripts4/instrument.py`, 40 games.\n\n# OUTCOME\n\n-0.0535.\n")
    assert g.main(strict=True) == 1


def test_a_named_file_that_is_missing_is_stale_not_backed(tree):
    write(tree, "a.md",
          "# Pre-registration\n\n# OUTCOME\n\n`results/gone.json`: -0.0535.\n")
    assert g.main(strict=True) == 1


def test_a_prereg_with_no_outcome_is_not_audited(tree):
    write(tree, "a.md", "# Pre-registration\n\nRegistered before any run.\n")
    assert g.main(strict=True) == 0


@pytest.mark.parametrize("heading", ["# OUTCOME", "## OUTCOME, recorded 2026",
                                     "# SCREEN OUTCOME", "## CORRECTION",
                                     "# REPRODUCTION, recorded 2026-08-31"])
def test_every_shape_of_outcome_heading_is_audited(tree, heading):
    """A restatement with no file is the same defect as a first statement.

    `# SCREEN OUTCOME` is not decoration: it is the heading a crude
    `^#+ OUTCOME` grep missed on reach_term.md, which was genuinely unbacked.
    """
    write(tree, "a.md", f"# Pre-registration\n\n{heading}\n\n-0.0535.\n")
    assert g.main(strict=True) == 1


def test_the_repository_itself_is_backed():
    """Run against the real tree, which is the point of having the guard."""
    assert g.main(strict=True) == 0


def test_every_exemption_carries_a_reason():
    for name, why in g.EXEMPT.items():
        assert why.strip(), f"{name} is exempt with no reason"
