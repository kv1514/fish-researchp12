"""`fish4.clustered.cluster_ci` is the one place cluster-robust intervals are
computed, so its two corrections are pinned here.

Both were live bugs on 2026-08-30: dividing by the position count rather than
the deal count, and pairing a cluster-robust standard error with 1.96 when the
estimator has three to ten clusters. Fixing only the first replaces one
too-narrow interval with another.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish4.clustered import cluster_ci, fmt
from fish4.match import _t_critical


def test_one_cluster_returns_no_interval():
    """One cluster is not a sample of clusters."""
    mu, hw, k = cluster_ci([1.0, 2.0, 3.0], [7, 7, 7])
    assert mu == pytest.approx(2.0)
    assert hw is None and k == 1
    assert "no interval" in fmt(mu, hw, k)


def test_uses_t_at_k_minus_one_not_1_96():
    """The correction that is easy to miss. With six clusters the normal
    critical value understates the half-width by 31%."""
    vals = [1.0, 1.1, -1.0, -0.9, 0.5, 0.4, -0.5, -0.6, 0.2, 0.3, -0.2, -0.1]
    grps = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5]
    mu, hw, k = cluster_ci(vals, grps)
    assert k == 6
    se = hw / _t_critical(5, 0.95)
    assert hw / (1.96 * se) == pytest.approx(_t_critical(5, 0.95) / 1.96, rel=1e-9)
    assert hw > 1.25 * 1.96 * se


def test_clustering_widens_when_deals_are_internally_correlated():
    """Twenty rows that are really two observations."""
    vals = [1.0] * 10 + [-1.0] * 10
    grps = [0] * 10 + [1] * 10
    mu, hw, k = cluster_ci(vals, grps)
    assert mu == pytest.approx(0.0)
    assert k == 2
    iid = 1.96 * (sum((v - mu) ** 2 for v in vals) / (len(vals) - 1)) ** 0.5 \
        / math.sqrt(len(vals))
    assert hw > 10 * iid


def test_mean_is_over_rows_not_clusters():
    """Unequal cluster sizes must not be reweighted: the estimand is the mean
    over rows."""
    mu, _, _ = cluster_ci([1.0, 1.0, 4.0], [0, 0, 1])
    assert mu == pytest.approx(2.0)


def test_length_mismatch_is_an_error_not_a_zip_truncation():
    """`zip` would silently drop the tail and report an interval over a subset."""
    with pytest.raises(ValueError):
        cluster_ci([1.0, 2.0, 3.0], [0, 1])


def test_identical_values_give_a_zero_width_interval():
    mu, hw, k = cluster_ci([2.0] * 8, [0, 0, 1, 1, 2, 2, 3, 3])
    assert mu == pytest.approx(2.0)
    assert hw == pytest.approx(0.0)
