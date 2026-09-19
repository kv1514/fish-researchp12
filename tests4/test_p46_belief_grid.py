"""The P46 Stage 0 instrument (`scripts4/p46_belief_grid.py`) does what
`prereg/kraken_v12_belief_grid.md` says it does.

Four things the registration's bars rest on, each of which has failed
silently in an earlier programme of this project:

1. The smoke run completes and writes the payload the aggregation reads.
2. Instrumenting a game does not move the champion's transcript, nor its
   live `PosteriorStats` -- validity bar 3 compares the instrument to that
   counter, so the instrument feeding it would be circular.
3. Cells at one budget share particles and differ only in weights; that is
   what makes the grid a paired comparison in the strict sense.
4. The instrument's incumbent cell IS the agent's own `build_posterior` under
   the same RNG seed. A hand-copied argument list is how P43's C3 measured a
   default and reported it as an arm.
"""

from __future__ import annotations

import json
import random
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fish.engine import GameState                                # noqa: E402
from fish.observation import Observation                         # noqa: E402
from fish.rules import RuleConfig                                # noqa: E402
from scripts4 import p46_belief_grid as grid                     # noqa: E402

SCRIPT = ROOT / "scripts4" / "p46_belief_grid.py"
DEAL = grid.DEAL_B0 + 7                          # a self-play deal of the block


def _frozen_position(min_step: int = 24):
    """A KRAKEN seat's (agent, obs, state) at a decision where the incumbent
    takes the sampler, i.e. at least one non-self ask is on record."""
    rules = RuleConfig(**grid.RULES_D)
    agents, scored = grid._make_agents("B", True)
    st = GameState.deal(rules, seed=DEAL)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, grid.AGENT0 + DEAL * 13 + p)
    for step in range(200):
        assert not st.is_terminal
        mover = st.turn
        obs = Observation.from_state(st, mover)
        act = agents[mover].act(obs)
        if mover in scored and step >= min_step:
            probe = grid.build_cell(agents[mover], obs, grid.INCUMBENT, 64,
                                    random.Random(1))
            if not probe.exact:
                return agents[mover], obs, st
        st.apply(mover, act)
    raise AssertionError("no sampled decision reached in 200 actions")


@pytest.fixture(scope="module")
def smoke_result(tmp_path_factory):
    """One smoke run of the instrument, shared by the payload test and the
    aggregation tests below (the run is the slow part)."""
    out = tmp_path_factory.mktemp("p46") / "grid_smoke.json"
    proc = subprocess.run([sys.executable, str(SCRIPT), "--smoke", "--jobs",
                           "2", "--out", str(out)],
                          capture_output=True, text=True, timeout=240)
    assert proc.returncode == 0, proc.stderr[-2000:]
    return json.loads(out.read_text())


def test_smoke_run_writes_the_registered_payload(smoke_result):
    res = smoke_result
    for key in ("prereg", "meta", "summary", "grid", "games", "decisions",
                "calibration_rows", "rows"):
        assert key in res, key
    m = res["meta"]
    assert m["bridge_rev"] == 3
    assert m["smoke"] is True
    assert m["cells"] == [list(c) for c in grid.SMOKE_CELLS]
    assert m["budgets"] == [720]
    assert m["n_games"] == {"A": 2, "B": 1}
    assert m["champion"]["spec"][0] == "fishbot4"
    for k in ("verdicts", "calibration_clause", "validity",
              "opp_lambda_calibration", "opp_lambda_gate", "arm_G_licensed",
              "void_conditions"):
        assert k in res["summary"], k
    # every game finished, and the instrumented replay matched pass 1
    for g in res["games"]:
        assert g["finished"] and g["illegal"] is None
        assert g["transcript_match"] is True
    assert not [v for v in res["summary"]["void_conditions"]
                if "transcript" in v or "unfinished" in v]
    # per-decision rows carry the registered fields, and d is the continuing
    # global index over block A then block B
    row_keys = {"block", "game", "deal", "kv_even", "seat", "d", "excluded",
                "cell", "budget", "pool", "mean_nll", "mean_brier", "top1",
                "n_cards", "ess"}
    assert res["rows"] and all(row_keys <= set(r) for r in res["rows"])
    ds = sorted({d["d"] for d in res["decisions"]})
    assert ds == list(range(len(ds)))
    a_max = max(d["d"] for d in res["decisions"] if d["block"] == "A")
    b_min = min(d["d"] for d in res["decisions"] if d["block"] == "B")
    assert a_max < b_min
    # the incumbent is also scored at 480 in block A only
    b480 = {r["block"] for r in res["rows"] if r["budget"] == 480}
    assert b480 == {"A"}
    assert all(r["cell"] == list(grid.INCUMBENT) for r in res["rows"]
               if r["budget"] == 480)
    # excluded rows are never paired: the paired count equals the
    # non-excluded decision count for the cell
    nonexc = {d["d"] for d in res["decisions"]
              if d["block"] == "A" and not d["excluded"]}
    pe = res["grid"]["A"]["0,0.35,0"]["budgets"]["720"]["pools"]["opp"]
    assert pe["paired_vs_incumbent"]["n_decisions"] <= len(nonexc)
    # block A has two games, so its intervals exist and are clustered on 2
    assert pe["paired_vs_incumbent"]["nll"]["k"] == 2
    assert res["summary"]["validity"]["incumbent_480_n_decisions"] > 0
    assert res["summary"]["opp_lambda_calibration"]["n_half_suits"] > 0
    # the smoke verdict says it is not a verdict; a void condition (two
    # games cannot be expected to pass bar 3) overrides even that, and the
    # unvoided reading is kept beside it
    void = res["summary"]["void_conditions"]
    for v in res["summary"]["verdicts"].values():
        if void:
            assert v["status"] == f"void: {void[0]}"
            assert v["status_if_not_void"].startswith("no verdict")
        else:
            assert v["status"].startswith("no verdict")
        assert v["licenses_arm_G"] is False
    assert res["summary"]["arm_G_licensed"] is False


def test_ess_is_read_off_the_decision_record_once_per_decision(smoke_result):
    """Bar 4's ESS/n ratio and bar 3's instrument mean count every
    non-excluded frozen decision once, whether or not a pool has a card on
    it -- the live counter they are compared to counts every SIS decision."""
    res = smoke_result
    inc = grid.cell_key(grid.INCUMBENT)
    other = grid.cell_key((0.0, 0.35, 0.0))
    for dec in res["decisions"]:
        assert "ess" in dec and inc in dec["ess"]
        assert set(dec["ess"][inc]) >= {"720"}
        if dec["block"] == "A":
            assert "480" in dec["ess"][inc]
        # an excluded decision is the exact path: no batch, no ESS
        if dec["excluded"]:
            assert dec["ess"][inc]["720"] is None
    for block in ("A", "B"):
        decs = [d for d in res["decisions"] if d["block"] == block
                and not d["excluded"]
                and d["ess"][other].get("720") is not None
                and d["ess"][inc].get("720") is not None]
        e = res["grid"][block][other]["budgets"]["720"]["ess"]
        if not decs:
            assert e is None
            continue
        assert e["n_decisions"] == len(decs)
        assert e["mean_ess_over_n"] == pytest.approx(
            sum(d["ess"][other]["720"] for d in decs) / len(decs) / 720)
    a480 = [d["ess"][inc]["480"] for d in res["decisions"]
            if d["block"] == "A" and not d["excluded"]
            and d["ess"][inc].get("480") is not None]
    va = res["summary"]["validity"]
    assert va["incumbent_480_n_decisions"] == len(a480)
    assert va["incumbent_480_mean_ess_over_n"] == pytest.approx(
        sum(a480) / len(a480) / 480)


def test_a_void_grid_licenses_nothing(smoke_result):
    """Registration: any void condition withdraws the cell, and a bar-3
    failure voids the whole grid. The one flag an operator reads to decide
    whether arm G is played must therefore be False on a void grid, and no
    status string may read 'licensed' or 'closed' beside the VOID list."""
    res = smoke_result
    games = [dict(g) for g in res["games"]]
    games[0]["finished"] = False
    agg = grid.aggregate(res["rows"], res["decisions"], games,
                         res["calibration_rows"],
                         [tuple(c) for c in res["meta"]["cells"]],
                         res["meta"]["budgets"], res["meta"]["stride"])
    assert any(v.startswith("unfinished game") for v in agg["void_conditions"])
    assert agg["arm_G_licensed"] is False
    for v in agg["verdicts"].values():
        assert v["status"].startswith("void: ")
        assert v["licenses_arm_G"] is False
    for g in agg["opp_lambda_gate"].values():
        assert g["closed_at_belief_level"] is True and g["void"] is True
    # ...and with the void list forced empty the gating is the only thing
    # that changes: statuses come back to the no-verdict reading
    agg2 = grid.aggregate(res["rows"], res["decisions"], res["games"],
                          res["calibration_rows"],
                          [tuple(c) for c in res["meta"]["cells"]],
                          res["meta"]["budgets"], res["meta"]["stride"])
    for v in agg2["verdicts"].values():
        base = v.get("status_if_not_void", v["status"])
        assert base.startswith("no verdict")


def test_instrument_leaves_transcript_and_live_counters_untouched():
    """Registration: 'the transcript stays the champion's game byte for
    byte'. Also the live `PosteriorStats`, which bar 3 reads."""
    plain = grid.play_game("B", DEAL, True, instrument=False, max_actions=40)
    inst = grid.play_game("B", DEAL, True, d0=0, cells=grid.SMOKE_CELLS,
                          budgets=[720], instrument=True, max_actions=40)
    assert plain["moves"] == inst["moves"]
    assert len(plain["moves"]) == 40
    assert inst["n_frozen"] == plain["n_frozen"] > 0
    assert inst["rows"]
    assert plain["agent_stats"] == inst["agent_stats"]


def test_cells_at_one_budget_share_particles_and_differ_in_weights():
    agent, obs, _st = _frozen_position()
    a = grid.build_cell(agent, obs, (0.35, 0.35, 0.0), 720, random.Random(9))
    b = grid.build_cell(agent, obs, (0.7, 0.35, 0.0), 720, random.Random(9))
    Ma, Mb = a.marginals(), b.marginals()
    assert not a.exact and not b.exact
    ba, bb = a._batch, b._batch
    assert ba is not None and bb is not None and len(ba) == len(bb) > 0
    assert list(ba.order) == list(bb.order)
    assert np.array_equal(ba.picks, bb.picks), "particles differ between cells"
    assert not np.allclose(ba.w, bb.w), "weights identical: cell inert"
    assert not np.array_equal(Ma, Mb)
    assert grid.batch_ess(a) == pytest.approx(float(1.0 / np.sum(ba.w ** 2)))


def test_incumbent_cell_is_the_agents_own_posterior():
    """build_posterior(obs, n_draws=720) and the instrument's incumbent cell
    under the same RNG seed give identical marginals, so every keyword was
    replicated, and gamma_team=0.35 is the agent's gamma_team=None."""
    agent, obs, _st = _frozen_position()
    assert agent.gamma_team is None and agent.opp_lambda == 0.0
    agent.rng = random.Random(4242)
    own = agent.build_posterior(obs, n_draws=720).marginals()
    cell = grid.build_cell(agent, obs, grid.INCUMBENT, 720,
                           random.Random(4242)).marginals()
    assert np.array_equal(own, cell)
    # ...and a non-incumbent cell is not byte-identical to it (withdrawal
    # condition: 'any cell byte-identical to the incumbent where it should
    # differ').
    for other in ((0.0, 0.35, 0.0), (-1.1055, 0.35, 0.0), (0.7, 0.7, 0.0),
                  (0.35, 0.35, 0.9)):
        M = grid.build_cell(agent, obs, other, 720,
                            random.Random(4242)).marginals()
        assert not np.array_equal(M, cell), other


def test_sampler_seeds_are_the_registered_streams():
    assert grid.sampler_seed(720, 0) == 7_200_000
    assert grid.sampler_seed(2880, 3) == 7_250_000 + 977 * 3
    assert grid.sampler_seed(480, 5) == 7_300_000 + 977 * 5
    assert len(grid.CELLS) == 20 and grid.INCUMBENT in grid.CELLS
    assert grid.REFERENCE in grid.CELLS and grid.PROMOTABLE in grid.CELLS
