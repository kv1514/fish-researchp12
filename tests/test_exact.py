"""Exact-solver tests: ground truth must be genuinely correct.

The solver is the project's only source of absolute (rather than relative)
truth, so it gets hand-verifiable positions where the right answer can be
derived by reasoning, not by trusting the code.
"""

import pytest

from fish.cards import card_id
from fish.engine import Ask, Claim, GameState
from fish.exact import (ExactSolver, SubgameTooLarge, information_is_resolved,
                        make_endgame, position_key, solve_position)
from fish.rules import RuleConfig

from helpers import mask


def test_single_set_all_with_one_player_is_immediate_win():
    """P0 holds all of Low Clubs, opponents have nothing: exactly +1."""
    rules = RuleConfig()
    hands = [mask("2C", "3C", "4C", "5C", "6C", "7C"), 0, 0, 0, 0, 0]
    r = solve_position(make_endgame(rules, [0], hands, turn=0))
    assert r["value"] == 1.0
    assert isinstance(r["action"], Claim)


def test_set_entirely_with_opponents_is_a_loss():
    rules = RuleConfig()
    hands = [0, mask("2C", "3C", "4C"), 0, mask("5C", "6C"), 0, mask("7C")]
    r = solve_position(make_endgame(rules, [0], hands, turn=1))
    assert r["value"] == -1.0


def test_split_set_solver_prefers_winning_line():
    """P0 has 5 of 6 low clubs, P1 has the last. Optimal: take it, claim."""
    rules = RuleConfig()
    hands = [mask("2C", "3C", "4C", "5C", "6C"), mask("7C"), 0, 0, 0, 0]
    r = solve_position(make_endgame(rules, [0], hands, turn=0))
    assert r["value"] == 1.0
    act = r["action"]
    assert isinstance(act, Ask) and act.card == card_id("7C") and act.target == 1


def test_two_sets_is_refused_as_too_large():
    """Honest tractability limit: 12 live cards is ~6^12 placements, so the
    solver must refuse loudly instead of hanging."""
    rules = RuleConfig()
    hands = [
        mask("2C", "3C", "2D"), mask("4C", "3D"), mask("5C", "4D"),
        mask("6C", "5D"), mask("7C", "6D"), mask("7D"),
    ]
    with pytest.raises(SubgameTooLarge):
        solve_position(make_endgame(rules, [0, 1], hands, turn=0))


def test_fish_game_graph_is_cyclic():
    """Structural fact the solver must handle: positions REPEAT, so the state
    space is a cyclic graph, not a tree. Naive backward induction therefore
    never terminates on Fish. Proven by search."""
    rules = RuleConfig()
    hands = [mask("2C", "3C"), mask("4C", "5C"), 0, mask("6C", "7C"), 0, 0]
    root = make_endgame(rules, [0], hands, turn=0)
    solver = ExactSolver(rules)

    def find_cycle(state, path, depth=0):
        k = position_key(state)
        if k in path:
            return True
        if depth >= 10:
            return False
        path = path | {k}
        for act in solver.actions(state):
            if isinstance(act, Claim):
                continue
            if find_cycle(solver._child(state, state.turn, act), path, depth + 1):
                return True
        return False

    assert find_cycle(root, set()), "expected a cycle in the Fish state graph"
    r = solve_position(make_endgame(rules, [0], hands, turn=0))
    assert float(r["value"]).is_integer()


def test_solver_value_is_consistent_with_playing_it_out():
    """Play the solver's own optimal line for BOTH teams; the realized
    differential must equal the computed value.

    Because the graph is cyclic, optimal play may legitimately loop forever
    (a side that can only lose by claiming will stall), so a non-terminating
    line is accepted only when its predicted value is 0.
    """
    rules = RuleConfig()
    hands = [mask("2C", "3C"), mask("4C"), mask("5C"), mask("6C"),
             mask("7C"), 0]
    st = make_endgame(rules, [0], hands, turn=0)
    solver = ExactSolver(rules)
    value, _ = solver.solve(st)
    live = GameState(rules, list(st.hands), st.turn)
    live.set_winner = list(st.set_winner)
    base_a = sum(1 for w in st.set_winner if w == 0)
    base_b = sum(1 for w in st.set_winner if w == 1)
    guard = 0
    while not live.is_terminal and guard < 600:
        _, act = solver.solve(live)
        if act is None:
            break
        live.apply(live.turn, act)
        guard += 1
    if live.is_terminal:
        a, b, _ = live.scores()
        assert (a - base_a) - (b - base_b) == value
    else:
        assert value == 0.0, "a non-terminating optimal line must have value 0"


def test_optimal_actions_all_achieve_the_value():
    rules = RuleConfig()
    hands = [mask("2C", "3C", "4C", "5C"), mask("6C"), 0, mask("7C"), 0, 0]
    st = make_endgame(rules, [0], hands, turn=0)
    solver = ExactSolver(rules)
    val, _ = solver.solve(st)
    opts = solver.optimal_actions(st)
    assert opts
    for act in opts:
        assert abs(solver.action_value(st, act) - val) < 1e-9


def test_make_endgame_validates_card_coverage():
    rules = RuleConfig()
    with pytest.raises(ValueError):
        make_endgame(rules, [0], [mask("2C"), 0, 0, 0, 0, 0], turn=0)
    with pytest.raises(ValueError):
        make_endgame(rules, [0],
                     [mask("2C", "3C", "4C", "5C", "6C", "7C"),
                      mask("2C"), 0, 0, 0, 0], turn=0)


def test_information_resolved_detection():
    rules = RuleConfig()
    st = GameState.deal(rules, seed=4)
    assert not information_is_resolved(st)


def test_score_context_does_not_change_remaining_value():
    """The solver returns the REMAINING differential, so already-banked sets
    must not shift it."""
    rules = RuleConfig()
    hands = [mask("2C", "3C", "4C", "5C", "6C"), mask("7C"), 0, 0, 0, 0]
    a = solve_position(make_endgame(rules, [0], hands, turn=0))
    b = solve_position(make_endgame(rules, [0], hands, turn=0,
                                    resolved={1: 0, 2: 1, 3: 0}))
    assert a["value"] == b["value"]
