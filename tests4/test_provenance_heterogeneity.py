"""The mixed-pool caveat is now arithmetic, so it can be wrong, so it is tested.

`check_engine_provenance.py` closed for a long time by saying that a mixed pool
"is not automatically wrong -- the blocks may differ by less than their noise",
without ever working out whether they did. The reader got the reassuring
possibility and had to assume the rest. `heterogeneity` computes it; these
tests are what stop it from computing something plausible and wrong.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts4.check_engine_provenance import heterogeneity     # noqa: E402


def _cell(est, half):
    """A duel row as far as heterogeneity is concerned: estimate and 95% CI."""
    return {"diff_mean": est, "diff_ci": [est - half, est + half]}


def test_identical_blocks_have_no_spread():
    q, df, mu, half = heterogeneity([_cell(0.30, 0.10), _cell(0.30, 0.10)])
    assert q == 0.0 and df == 1
    assert abs(mu - 0.30) < 1e-12


def test_blocks_that_disagree_are_caught():
    """The case the check exists for: two programs, opposite real effects.

    Without this, a pool could average +0.5 and -0.5 into a tidy zero and the
    summary would call it agreement.
    """
    q, df, mu, _ = heterogeneity([_cell(+0.50, 0.10), _cell(-0.50, 0.10)])
    assert q > 3.84, f"Q={q} should exceed chi2(0.95, 1)=3.84"
    assert abs(mu) < 1e-9, "the mixture hides in the mean, which is the point"


def test_the_two_live_mixed_pools_agree_within_noise():
    """Pinned from the duel record: these are why no re-block was queued.

    If either stops agreeing, the conclusion that the mixture is harmless stops
    holding with it, and this fails rather than the change passing unnoticed.
    """
    import json

    rows = [json.loads(l) for l
            in (ROOT / "results" / "v04_duels.jsonl").read_text().splitlines()
            if l.strip()]
    for prefix, want_q in (("CLAIM THRESHOLD", 1.35), ("RETAKE BONUS", 0.07)):
        cells = [r for r in rows if r["label"].startswith(prefix)]
        assert len(cells) == 2, f"{prefix}: expected 2 blocks, got {len(cells)}"
        q, df, _, _ = heterogeneity(cells)
        assert df == 1
        assert abs(q - want_q) < 0.01, f"{prefix}: Q moved from {want_q} to {q}"
        assert q < 3.84


def test_a_zero_width_interval_is_refused_rather_than_dividing_by_zero():
    assert heterogeneity([_cell(0.1, 0.0), _cell(0.2, 0.1)]) is None
    assert heterogeneity([_cell(0.1, 0.1)]) is None
