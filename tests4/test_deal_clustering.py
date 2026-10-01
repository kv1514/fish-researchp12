"""The deal is the independent unit in every ask_regret harvest.

`harvest` walks games in order and emits every qualifying ply, so "162
positions" is 162 consecutive plies from eight deals. Two things are pinned
here: that `harvest` reports the deal it drew each position from, and that the
history-drop rule used to recover deals for the ARCHIVED files (which predate
the field) reproduces that report exactly.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _harvest(n_games, max_positions):
    import importlib
    import scripts4.ask_regret as AR
    importlib.reload(AR)
    games: list[int] = []
    pos = AR.harvest(n_games, 5, max_positions, games_out=games)
    return pos, games


def test_games_out_is_one_entry_per_position():
    pos, games = _harvest(6, 40)
    assert len(games) == len(pos)


def test_positions_come_from_far_fewer_deals_than_positions():
    """The fact the correction exists for. Forty positions do not come from
    forty deals -- they come from a couple of games sampled tens of plies
    deep, and any interval that divides by 40 is dividing by the wrong number."""
    pos, games = _harvest(20, 40)
    assert len(pos) == 40
    assert len(set(games)) < 8, (
        f"40 positions came from {len(set(games))} deals; if harvest ever "
        "starts spreading across deals this test should be re-thought, not "
        "deleted")


def test_deals_are_contiguous_runs_in_harvest_order():
    """Positions are emitted game by game, ply by ply. Nothing interleaves."""
    _, games = _harvest(20, 60)
    seen = []
    for g in games:
        if not seen or seen[-1] != g:
            seen.append(g)
    assert len(seen) == len(set(seen))
    assert seen == sorted(seen)


def test_history_drop_rule_recovers_the_deal_boundaries_exactly():
    """How the archived result files -- written before `games_out` existed --
    get their deal index back. `history` rises within a deal and drops at the
    next, so a drop marks a boundary. Checked against the harvest's own answer,
    because a segmentation that is merely plausible would silently mis-cluster
    the very intervals it is meant to fix."""
    pos, games = _harvest(20, 60)
    seg, cur, prev = [], 0, -1
    for p in pos:
        h = len(p[4])                      # p[4] is the history tuple
        if h <= prev:
            cur += 1
        seg.append(cur)
        prev = h
    true_b = [i for i in range(1, len(games)) if games[i] != games[i - 1]]
    seg_b = [i for i in range(1, len(seg)) if seg[i] != seg[i - 1]]
    assert seg_b == true_b


def test_harvest_without_games_out_is_unchanged():
    """The out-parameter is additive. Every existing caller passes nothing and
    must get exactly what it got before."""
    import importlib
    import scripts4.ask_regret as AR
    importlib.reload(AR)
    a = AR.harvest(8, 5, 30)
    b, _ = _harvest(8, 30)
    assert len(a) == len(b)
    for x, y in zip(a, b):
        assert x[1] == y[1] and x[3] == y[3] and x[5] == y[5]
