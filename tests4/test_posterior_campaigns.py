"""Every results file this script produced must still be producible by it.

`CONFIGS` was one list edited in place across three campaigns, so the script
could only reproduce whichever ran last. Twelve of the fourteen rows in
`results/posterior_accuracy.json` -- the file backing the paper's central
negative result, and the file `check_paper_numbers.py` watches -- had become
unproducible by any command in the repository, including `sis-512` at 1.3618,
one of the two numbers in the headline comparison. Found by an audit of the
paper's reproduction section.

Two rows genuinely cannot come back. This file pins WHICH, so the number stays
two rather than growing quietly.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts4 import posterior_accuracy as pa                    # noqa: E402

#: Named here, not merely absent. `exact-free` is unreachable BY DESIGN --
#: `Posterior` now raises on mode="exact" wherever an OR clause is active,
#: because the DP draws from a superset of the feasible worlds and reporting
#: that as exact is the worst of the three outcomes. The two `-cur` rows scored
#: NLL 2.221 and 2.644 against a class prior near 1.4, and no surviving
#: argument of `Posterior` reproduces the name; guessing at a configuration and
#: labelling the guess with the original row's name would be worse than leaving
#: it unproducible.
UNREPRODUCIBLE = {"exact-free", "sis-160-g0.35-cur", "sis-160-g0.70-cur-sqrt"}


@pytest.mark.parametrize("campaign", sorted(pa.CAMPAIGN_FILE))
def test_each_campaign_reproduces_its_results_file(campaign):
    have = {n for n, _ in pa.CAMPAIGNS[campaign]}
    path = ROOT / "results" / pa.CAMPAIGN_FILE[campaign]
    want = {r["name"] for r in json.loads(path.read_text())["rows"]}
    assert want - have <= UNREPRODUCIBLE, (
        f"{path.name} has rows no campaign can produce: {sorted(want - have)}")
    assert not have - want, (
        f"campaign {campaign!r} produces rows that are not in {path.name}: "
        f"{sorted(have - want)}")


def test_the_headline_comparison_is_producible_again():
    """The paper's central negative result is `sis-512` against `v03-512`.
    Both must be in a runnable campaign or the finding cannot be checked."""
    gamma = {n for n, _ in pa.CAMPAIGNS["gamma"]}
    assert {"sis-512", "v03-512"} <= gamma


def test_the_unreproducible_rows_are_exactly_three_and_are_explained():
    src = (ROOT / "scripts4" / "posterior_accuracy.py").read_text()
    every = set()
    for f in pa.CAMPAIGN_FILE.values():
        every |= {r["name"] for r in
                  json.loads((ROOT / "results" / f).read_text())["rows"]}
    produced = {n for c in pa.CAMPAIGNS.values() for n, _ in c}
    assert every - produced == UNREPRODUCIBLE
    flat = " ".join(src.replace("#", " ").split())
    assert "CANNOT BE REGENERATED, and that is deliberate" in flat
    assert "are NOT reconstructed" in flat, (
        "each unreproducible row must carry a reason in the source, or the "
        "set grows quietly")


def test_every_config_is_callable_and_uniquely_named():
    for name, configs in pa.CAMPAIGNS.items():
        names = [n for n, _ in configs]
        assert len(names) == len(set(names)), name
        for _, fn in configs:
            assert callable(fn)


def test_the_campaign_is_a_selector_not_an_edit():
    """A list edited in place is how the twelve rows were lost."""
    src = (ROOT / "scripts4" / "posterior_accuracy.py").read_text()
    assert "--campaign=" in src
    assert "CONFIGS = CAMPAIGNS[" in src


def test_the_output_path_is_an_argument():
    """It was not, so no documented command could write the watched file."""
    src = (ROOT / "scripts4" / "posterior_accuracy.py").read_text()
    assert "a[2] if len(a) > 2 else None" in src
    assert "write_result(path, payload)" in src
