"""The deal-luck decomposition, checked against data whose answer we chose.

This file exists because the first version of `deal_component` reported
var(diff)/(var(sum)+var(diff)), which is 0.5 whenever the two parities are
uncorrelated. It printed "49.4% of the outcome is the deal" from a corpus that
says the deal contributes nothing, and it would have printed roughly the same
number from any corpus at all. A statistic that cannot be wrong cannot be
right either.

So each test here builds a synthetic journal with a KNOWN deal effect and
checks the estimator recovers it -- including the case that broke, where the
true effect is zero.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts4"))

import deal_luck as dl  # noqa: E402


def _row(deal, kv_even, margin, *, ask=(26, 50), dec=(5, 5),
         opp_ask=(24, 50), opp_dec=(3, 4)):
    return {"deal": deal, "kv_even": kv_even, "margin": margin,
            "kv": 0, "dylan": 0, "terminal": True, "rev": 2, "fallbacks": 0,
            "ask": {"kv": list(ask), "dy": list(opp_ask)},
            "dec": {"kv": list(dec), "dy": list(opp_dec)},
            "mis": {"kv": 0, "dy": 0}, "anchorless": {"kv": 0, "dy": 0}}


def _corpus(n_deals, deal_sd, noise_sd, seed=7):
    """margin_even = D + e1, margin_odd = -D + e2, with D ~ N(0, deal_sd)."""
    rng = random.Random(seed)
    rows = []
    for d in range(n_deals):
        D = rng.gauss(0.0, deal_sd)
        rows.append(_row(d, True, D + rng.gauss(0.0, noise_sd)))
        rows.append(_row(d, False, -D + rng.gauss(0.0, noise_sd)))
    return rows


def test_zero_deal_effect_reports_zero(capsys):
    """The case the broken estimator called 'about half'."""
    out = dl.deal_component(_corpus(4000, deal_sd=0.0, noise_sd=2.7))
    assert abs(out["deal_share_of_variance"]) < 0.05, out
    lo, hi = out["deal_share_ci95"]
    assert lo < 0.0 < hi, (lo, hi)


def test_dominant_deal_effect_is_recovered(capsys):
    """When the cards really do decide it, the share must approach 1."""
    out = dl.deal_component(_corpus(4000, deal_sd=3.0, noise_sd=0.3))
    assert out["deal_share_of_variance"] > 0.9, out
    assert out["corr_parities"] < -0.9, out


def test_half_and_half(capsys):
    """Equal deal and noise variance puts the share at one half."""
    out = dl.deal_component(_corpus(6000, deal_sd=2.0, noise_sd=2.0))
    assert 0.42 < out["deal_share_of_variance"] < 0.58, out


def test_pairing_efficiency_tracks_the_deal_effect(capsys):
    """Duplication is worth a lot exactly when there is tilt to remove."""
    none = dl.deal_component(_corpus(4000, deal_sd=0.0, noise_sd=2.7))
    lots = dl.deal_component(_corpus(4000, deal_sd=3.0, noise_sd=0.9))
    assert 0.8 < none["pairing_efficiency"] < 1.2, none["pairing_efficiency"]
    assert lots["pairing_efficiency"] > 3.0, lots["pairing_efficiency"]


def test_overdispersion_is_one_for_pure_coin_flips(capsys):
    """Rates generated as fifty fair-ish flips must not look structured."""
    rng = random.Random(11)
    rows = []
    for d in range(3000):
        for ke in (True, False):
            k = sum(1 for _ in range(50) if rng.random() < 0.52)
            rows.append(_row(d, ke, 1, ask=(k, 50)))
    od = dl.overdispersion(rows)
    assert 0.88 < od["our hit rate"]["overdispersion"] < 1.12, od
    lo, hi = od["our hit rate"]["corr_ci95"]
    assert lo < 0.0 < hi, (lo, hi)


def test_overdispersion_sees_a_real_per_deal_difficulty(capsys):
    """A symmetric per-deal rate must show up as overdispersion AND as a
    positive across-parity correlation -- the two instruments have to agree."""
    rng = random.Random(13)
    rows = []
    for d in range(3000):
        p = min(0.9, max(0.1, rng.gauss(0.52, 0.10)))   # a property of the deal
        for ke in (True, False):
            k = sum(1 for _ in range(50) if rng.random() < p)
            rows.append(_row(d, ke, 1, ask=(k, 50)))
    od = dl.overdispersion(rows)["our hit rate"]
    assert od["overdispersion"] > 1.7, od
    assert od["corr_across_parities"] > 0.3, od


def test_pinned_rows_are_labelled(capsys):
    """The score identity's own terms must be marked, or the ranking lies."""
    rows = _corpus(200, deal_sd=1.0, noise_sd=1.0)
    for i, r in enumerate(rows):
        r["margin"] = 1 if i % 3 else -1
    out = dl.loss_modes(rows)
    kinds = {k: v["kind"] for k, v in out["by_statistic"].items()}
    assert kinds["our declarations right"] == "pinned"
    assert kinds["our wrong declarations"] == "pinned"
    assert kinds["our hit rate"] == "free"
    assert out["largest_free_separator"] in {
        k for k, v in kinds.items() if v != "pinned"}


def test_symmetric_self_play_is_refused_not_reported(capsys):
    """The failure that looks like the strongest possible finding.

    When both teams run the identical policy and the agent seeds key on the
    seat, the two parities of a deal are the SAME GAME with the labels
    swapped: margin_odd is exactly -margin_even, var(sum) is 0, and the
    correlation is exactly -1. Reported rather than refused, that reads as
    "the deal decides 100% of the outcome, [100%, 100%]" -- an arithmetic
    identity wearing a confidence interval, which is precisely the mistake
    this project has made before with symmetric arms.
    """
    rng = random.Random(29)
    rows = []
    for d in range(300):
        m = rng.choice([-5, -3, -1, 1, 3, 5])
        rows.append(_row(d, True, m))
        rows.append(_row(d, False, -m))
    with pytest.raises(SystemExit) as e:
        dl.deal_component(rows)
    assert "SAME GAME" in str(e.value)


def test_one_unflipped_deal_is_enough_to_proceed(capsys):
    """The guard must key on the degeneracy, not merely on a strong result.

    A corpus that is genuinely dominated by the deal still has play noise, so
    some deal somewhere breaks the exact -1 relation. Refusing that would
    silence the very finding the estimator exists to report.
    """
    rng = random.Random(31)
    rows = []
    for d in range(300):
        m = rng.choice([-5, -3, -1, 1, 3, 5])
        rows.append(_row(d, True, m))
        rows.append(_row(d, False, -m if d else -m + 2))
    out = dl.deal_component(rows)
    assert out["deal_share_of_variance"] > 0.9, out


def test_loader_can_lift_an_arm_to_the_top_level(tmp_path):
    f = tmp_path / "j.jsonl"
    r = _row(1, True, 0)
    r.pop("margin")
    r["A_shipped"] = {"margin": 3}
    r["B_full"] = {"margin": 4}
    f.write_text(json.dumps(r) + "\n")
    assert dl._load(f, "A_shipped")[0]["margin"] == 3
    assert dl._load(f, "B_full")[0]["margin"] == 4
    with pytest.raises(SystemExit):
        dl._load(f, "C_missing")


def test_loader_refuses_a_foreign_journal(tmp_path):
    f = tmp_path / "j.jsonl"
    f.write_text(json.dumps({"deal": 1, "kv_even": True}) + "\n")
    with pytest.raises(SystemExit):
        dl._load(f)
