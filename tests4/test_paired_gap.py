"""``ii_ask_fit.paired_gap`` is the instrument that closed #49, so it is pinned.

The void-era rung that shipped -- ``info = +2.0`` -- was nominated on a point
estimate of +0.0092 with no interval at all. The interval, computed after the
fact, is [-0.0270, +0.0455]. Everything that conclusion rests on is in this
one function, so its arithmetic is tested against a hand-worked case, against
an independent cluster bootstrap, and for the properties it must have.
"""

from __future__ import annotations

import math
import random
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts4.ii_ask_fit import paired_gap


def _row(game, values, feats, ps=None):
    n = len(values)
    return {"game": game, "v": np.array(values, dtype=float),
            "F": np.array(feats, dtype=float),
            "p": np.array(ps if ps is not None else [0.0] * n, dtype=float)}


def test_identical_policies_give_exactly_zero():
    """Two weight vectors that pick the same ask everywhere differ by 0, and
    the interval must be 0 wide -- not merely small. The ladder's ``scale
    k=1.0`` rung relies on this: it is the champion under another name, and an
    interval that failed to collapse there would mean the pairing is broken."""
    rows = [_row(g, [1.0, -2.0], [[1.0], [0.0]]) for g in range(6)]
    w = np.array([0.5])
    mu, hw = paired_gap(rows, w, w)
    assert mu == 0.0
    assert hw == 0.0


def test_mean_is_over_positions_not_games():
    """Games contribute unequal numbers of positions and the estimand is the
    mean over POSITIONS. A game-mean-of-means would weight a one-position game
    like a ten-position one."""
    # game 0: two positions each gaining +1; game 1: one position gaining +4
    rows = [_row(0, [0.0, 1.0], [[0.0], [1.0]]),
            _row(0, [0.0, 1.0], [[0.0], [1.0]]),
            _row(1, [0.0, 4.0], [[0.0], [1.0]])]
    mu, _ = paired_gap(rows, np.array([1.0]), np.array([-1.0]))
    assert mu == pytest.approx((1.0 + 1.0 + 4.0) / 3.0)


def test_clustering_widens_when_games_are_internally_correlated():
    """The whole reason for clustering. Two games, each perfectly internally
    correlated: every position inside a game moves the same way, and the two
    games disagree. Treating the 20 positions as independent would report a
    tiny interval for what is really a two-observation comparison."""
    rows = ([_row(0, [0.0, 1.0], [[0.0], [1.0]]) for _ in range(10)]
            + [_row(1, [0.0, -1.0], [[0.0], [1.0]]) for _ in range(10)])
    w, w0 = np.array([1.0]), np.array([-1.0])
    mu, hw = paired_gap(rows, w, w0)
    assert mu == pytest.approx(0.0)
    flat = [1.0] * 10 + [-1.0] * 10
    iid = 1.96 * (np.std(flat, ddof=1) / math.sqrt(len(flat)))
    assert hw > 4 * iid


def test_matches_a_cluster_bootstrap():
    """The analytic interval is a formula; the bootstrap is not. They should
    agree, and on the real void-era rung they do to three decimals
    (analytic [-0.0270, +0.0455], 20k bootstrap [-0.0257, +0.0449]). Here the
    same check runs on synthetic rows so the test needs no journal."""
    rng = random.Random(11)
    rows = []
    for g in range(40):
        shift = rng.gauss(0.0, 0.6)          # a per-game effect
        for _ in range(rng.randint(1, 8)):
            gain = shift + rng.gauss(0.0, 0.3)
            rows.append(_row(g, [0.0, gain], [[0.0], [1.0]]))
    w, w0 = np.array([1.0]), np.array([-1.0])
    mu, hw = paired_gap(rows, w, w0)

    per = {}
    for r in rows:
        per.setdefault(r["game"], []).append(float(r["v"][1]))
    games = list(per)
    br = random.Random(7)
    draws = []
    for _ in range(4000):
        pick = [per[games[br.randrange(len(games))]] for _ in games]
        n = sum(len(x) for x in pick)
        draws.append(sum(sum(x) for x in pick) / n)
    draws.sort()
    lo, hi = draws[int(0.025 * len(draws))], draws[int(0.975 * len(draws))]
    boot_hw = (hi - lo) / 2.0
    assert hw == pytest.approx(boot_hw, rel=0.20)
    assert mu == pytest.approx(sum(draws) / len(draws), abs=0.05)


def test_single_game_declines_to_invent_an_interval():
    """One cluster is not a sample of clusters. It returns nan rather than a
    number, because a plausible-looking interval from one game is worse than
    no interval -- that is the failure this whole function exists to fix."""
    rows = [_row(0, [0.0, 1.0], [[0.0], [1.0]]) for _ in range(9)]
    mu, hw = paired_gap(rows, np.array([1.0]), np.array([-1.0]))
    assert mu == pytest.approx(1.0)
    assert math.isnan(hw)
