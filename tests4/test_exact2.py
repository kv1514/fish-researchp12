"""Tests for the v2 exact solver: ground truth has to be genuinely true.

The whole file is budgeted to run in well under two minutes, which rules out
comparing against ``fish.exact`` on more than a handful of positions (v1 costs
seconds per position). The large-sample cross-check lives in
``fish4.exact2_study`` and its result is recorded in
``results/exact2_cross_check.json``; here we keep a small, deliberately
awkward selection of it plus the checks that are cheap and structural.

Run: py -m pytest tests4/test_exact2.py -q
"""

import json
import os
import random
import sys

import numpy as np
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fish.cards import card_id
from fish.engine import Ask, Claim, GameState, NULL_TEAM, Pass
from fish.exact import (ExactSolver, SubgameTooLarge, live_card_count,
                        make_endgame, solve_position)
from fish.rules import RuleConfig

from fish4 import exact2 as e
from fish4.exact2_study import (abstraction_fuzz, constructive_playout,
                                generate_m1_positions, generate_m2_positions,
                                rebuild, representative_invariance)

RULES = RuleConfig()


def mask(*names):
    m = 0
    for n in names:
        m |= 1 << card_id(n)
    return m


@pytest.fixture(scope="module")
def solver():
    s = e.Exact2Solver(RULES)
    s.table(1)
    s.table(2)          # ~5 s once; every later query is an array lookup
    return s


# ---------------------------------------------------------------------------
# the structural fact the whole rewrite rests on
# ---------------------------------------------------------------------------

def test_live_cards_is_six_times_unresolved():
    """Resolved half-suits leave every hand, so a position never has 7, 8 or 9
    live cards. v1's "about seven live cards" limit was really "one half-suit"."""
    rng = random.Random(0)
    for seed in range(6):
        state = GameState.deal(RULES, seed=seed)
        agents_moves = 0
        while not state.is_terminal and agents_moves < 400:
            unresolved = sum(1 for w in state.set_winner if w is None)
            assert live_card_count(state) == 6 * unresolved
            acts = e.Exact2Solver(RULES).actions(state)
            state.apply(state.turn, rng.choice(acts))
            agents_moves += 1


# ---------------------------------------------------------------------------
# hand-verifiable positions: the answer is derivable without the code
# ---------------------------------------------------------------------------

def test_one_player_holds_a_whole_half_suit(solver):
    hands = [mask("2C", "3C", "4C", "5C", "6C", "7C"), 0, 0, 0, 0, 0]
    st = make_endgame(RULES, [0], hands, turn=0)
    assert solver.value(st) == 1.0
    assert isinstance(solver.solve(st)[1], Claim)


def test_half_suit_entirely_with_opponents_is_a_loss(solver):
    hands = [0, mask("2C", "3C", "4C"), 0, mask("5C", "6C"), 0, mask("7C")]
    st = make_endgame(RULES, [0], hands, turn=1)
    assert solver.value(st) == -1.0


def test_mover_drains_the_last_card_and_claims(solver):
    hands = [mask("2C", "3C", "4C", "5C", "6C"), mask("7C"), 0, 0, 0, 0]
    st = make_endgame(RULES, [0], hands, turn=0)
    assert solver.value(st) == 1.0
    best = solver.optimal_actions(st)
    assert Ask(1, card_id("7C")) in best


def test_score_context_does_not_shift_the_remaining_value(solver):
    hands = [mask("2C", "3C", "4C", "5C", "6C"), mask("7C"), 0, 0, 0, 0]
    a = solver.value(make_endgame(RULES, [0], hands, turn=0))
    b = solver.value(make_endgame(RULES, [0], hands, turn=0,
                                  resolved={1: 0, 2: 1, 3: 0}))
    assert a == b


def test_nulled_half_suit_present_is_handled(solver):
    """A half-suit resolved as NULL is still resolved: it must not appear in
    the layer and must not shift the remaining differential."""
    hands = [mask("2C", "3C"), mask("4C", "5C"), 0, mask("6C", "7C"), 0, 0]
    plain = make_endgame(RULES, [0], hands, turn=0)
    nulled = make_endgame(RULES, [0], hands, turn=0,
                          resolved={1: NULL_TEAM, 2: NULL_TEAM, 3: 1})
    assert solver.value(plain) == solver.value(nulled) == 1.0
    assert e.abstract_state(plain)[1] == e.abstract_state(nulled)[1]


def test_cardless_mover_must_pass_and_keeps_the_value(solver):
    hands = [0, mask("2C", "3C"), mask("4C", "5C", "6C", "7C"), 0, 0, 0]
    st = make_endgame(RULES, [0], hands, turn=0)
    assert st.turn == 0 and st.hands[0] == 0     # P2 has cards, so P0 must pass
    assert solver.actions(st) == [Pass(2)]
    assert solver.value(st) == 1.0


def test_forced_claim_ending(solver):
    """The mover has cards, no opponent has any, so no ask is legal at all."""
    hands = [mask("2C", "3C", "4C"), 0, mask("5C", "6C"), 0, mask("7C"), 0]
    st = make_endgame(RULES, [0], hands, turn=0)
    assert not st.legal_asks(0) and st.must_claim(0)
    acts = solver.actions(st)
    assert acts and all(isinstance(a, Claim) for a in acts)
    assert solver.value(st) == 1.0


def test_team_with_zero_cards(solver):
    hands = [0, mask("2C", "3C", "4C"), 0, mask("5C", "6C", "7C"), 0, 0]
    st = make_endgame(RULES, [0], hands, turn=0)
    assert st.turn == 1                     # normalisation walks to a holder
    assert solver.value(st) == -1.0


# ---------------------------------------------------------------------------
# the new capability
# ---------------------------------------------------------------------------

def test_two_half_suits_v1_refuses_and_v2_solves(solver):
    hands = [mask("2C", "3C", "2D"), mask("4C", "3D"), mask("5C", "4D"),
             mask("6C", "5D"), mask("7C", "6D"), mask("7D")]
    st = make_endgame(RULES, [0, 1], hands, turn=0)
    with pytest.raises(SubgameTooLarge):
        solve_position(st)
    assert solver.value(st) == 2.0          # team 0 is in both, and on move
    assert solver.optimal_actions(st)


def test_two_half_suits_split_footholds_is_a_draw(solver):
    """Team 0 can only ever reach clubs, team 1 only diamonds: one each."""
    hands = [mask("2C", "3C", "4C"), mask("2D", "3D", "4D"),
             mask("5C", "6C", "7C"), mask("5D", "6D", "7D"), 0, 0]
    st = make_endgame(RULES, [0, 1], hands, turn=0)
    assert solver.value(st) == 0.0
    st1 = make_endgame(RULES, [0, 1], hands, turn=1)
    assert solver.value(st1) == 0.0


# ---------------------------------------------------------------------------
# agreement with v1, on a small but awkward selection
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("hands,turn", [
    ([mask("2C", "3C", "4C", "5C", "6C", "7C"), 0, 0, 0, 0, 0], 0),
    ([0, mask("2C", "3C", "4C", "5C", "6C", "7C"), 0, 0, 0, 0], 1),
    ([mask("2C", "3C"), mask("4C", "5C"), 0, mask("6C", "7C"), 0, 0], 0),
    ([mask("2C", "3C", "4C"), 0, mask("5C", "6C"), 0, mask("7C"), 0], 4),
    ([mask("2C", "3C", "4C", "5C"), mask("6C"), 0, mask("7C"), 0, 0], 0),
])
def test_matches_v1_exactly(solver, hands, turn):
    """Kept to at most four card-holding hands on purpose: v1 costs 140 s on a
    six-way split, and the 300-position comparison lives in
    ``results/exact2_cross_check.json`` where it does not gate the test run."""
    st = make_endgame(RULES, [0], list(hands), turn=turn)
    v1 = ExactSolver(RULES)
    value, _ = v1.solve(st)
    assert solver.value(st) == value
    assert (sorted(map(repr, v1.optimal_actions(st)))
            == sorted(map(repr, solver.optimal_actions(st))))


def test_abstraction_matches_the_engine():
    """A wrong symmetry would silently corrupt ground truth, so the abstract
    successors are compared against real engine successors, not argued about."""
    assert abstraction_fuzz(trials=120, seed=17)["n_mismatches"] == 0


def test_value_is_invariant_to_which_cards():
    assert representative_invariance(trials=40, seed=21)["n_mismatches"] == 0


# ---------------------------------------------------------------------------
# cyclic-game semantics
# ---------------------------------------------------------------------------

def test_value_iteration_and_attractors_agree_at_m1():
    """Two independent solutions of the loopy layer: iterate to a fixpoint
    from zero, or compute reachability attractors with no fixpoint at all."""
    moves, exits, is_max, valid = e._layer_slots(1, False, False, None)
    vi, _ = e._value_iterate(moves, exits, is_max, valid)
    attr, ranks = e.solve_layer_attractor(moves, exits, is_max, valid,
                                          [-1, 0, 1])
    assert np.array_equal(vi[valid], attr[valid])
    assert ranks[valid].max() >= 1


def _sweep_factory(moves, exits, is_max, valid):
    n = is_max.shape[0]
    sign = np.where(is_max, 1, -1).astype(np.int32)

    def sweep(values):
        best = np.full(n, e._LOW, dtype=np.int32)
        for m, child in moves:
            best = np.maximum(best, np.where(m, sign * values[child], e._LOW))
        for m, val in exits:
            best = np.maximum(best, np.where(m, sign * val.astype(np.int32),
                                             e._LOW))
        out = sign * best
        out[~valid] = 0
        return out
    return sweep


def test_a_loopy_bellman_operator_can_have_many_fixpoints():
    """Why the zero start is a specification and not a detail.

    Two maximiser states in a cycle, one of them holding a claim worth -1.
    The right value is 0 - loop forever rather than take the losing claim -
    but EVERY constant vector >= -1 is a fixpoint of the Bellman operator, so
    "iterate to a fixpoint" simply does not determine the value. Iterating
    from zero does, and so does the attractor computation.
    """
    is_max = np.array([True, True])
    valid = np.array([True, True])
    moves = [(np.array([True, True]), np.array([1, 0], dtype=np.int32))]
    exits = [(np.array([False, True]), np.array([0, -1], dtype=np.int16))]

    values, _ = e._value_iterate(moves, exits, is_max, valid)
    attractor, _ = e.solve_layer_attractor(moves, exits, is_max, valid,
                                           [-1, 0, 1])
    assert list(values) == [0, 0]
    assert list(attractor) == [0, 0]

    sweep = _sweep_factory(moves, exits, is_max, valid)
    wrong = np.array([5, 5], dtype=np.int32)
    assert np.array_equal(sweep(wrong), wrong), (
        "the optimistic vector really is a fixpoint of the same operator")


def test_fish_layers_have_a_unique_fixpoint_after_all():
    """Measured, and NOT what the general theory guarantees.

    Every initialisation tried - zeros, optimistic, pessimistic, random -
    converges to the same values on a real Fish layer, so v1's answer does not
    depend on its zero start or its sweep order. The reason is structural: a
    Fish layer has no state whose value rests on a cycle, because whoever is on
    move can always force termination (EXACT2.md section 4.3). The general
    guarantee is still absent, which is why the solver keeps the attractor
    cross-check rather than trusting the fixpoint.
    """
    moves, exits, is_max, valid = e._layer_slots(1, False, False, None)
    truth, _ = e.solve_layer_attractor(moves, exits, is_max, valid, [-1, 0, 1])
    sweep = _sweep_factory(moves, exits, is_max, valid)
    n = truth.shape[0]
    rng = np.random.default_rng(0)
    starts = [np.zeros(n, np.int32), np.full(n, 1, np.int32),
              np.full(n, -1, np.int32), np.full(n, 7, np.int32),
              rng.integers(-3, 4, n).astype(np.int32)]
    for start in starts:
        values = start.copy()
        values[~valid] = 0
        for _ in range(300):
            nxt = sweep(values)
            if np.array_equal(nxt, values):
                break
            values = nxt
        assert np.array_equal(values[valid], truth[valid])


def test_gauss_seidel_sweep_order_does_not_matter_in_fish():
    """v1 updates in place in dict order. In a loopy game that is a real risk;
    here it is measured to be safe, on random sweep orders."""
    moves, exits, is_max, valid = e._layer_slots(1, False, False, None)
    truth, _ = e.solve_layer_attractor(moves, exits, is_max, valid, [-1, 0, 1])
    live = np.flatnonzero(valid)
    rng = random.Random(4)
    for trial in range(3):
        order = list(live)
        rng.shuffle(order)
        values = np.zeros(truth.shape[0], dtype=np.int32)
        for _ in range(60):
            before = values.copy()
            for i in order:
                cand = [int(values[child[i]]) for m, child in moves if m[i]]
                cand += [int(val[i]) for m, val in exits if m[i]]
                values[i] = max(cand) if is_max[i] else min(cand)
            if np.array_equal(before, values):
                break
        assert np.array_equal(values[valid], truth[valid])


def test_cycles_exist_but_optimal_play_never_needs_them(solver):
    """The graph really is cyclic - v1's central structural claim - yet the
    exact value is always realised by a line that terminates. Stalling is
    available, never necessary. See EXACT2.md section 4.3."""
    hands = [mask("2C", "3C"), mask("4C", "5C"), 0, mask("6C", "7C"), 0, 0]
    root = make_endgame(RULES, [0], hands, turn=0)

    def find_cycle(state, path, depth=0):
        key = (tuple(state.hands), state.turn, tuple(state.set_winner))
        if key in path:
            return True
        if depth >= 8:
            return False
        path = path | {key}
        for act in solver.actions(state):
            if isinstance(act, Claim):
                continue
            if find_cycle(solver.child(state, act), path, depth + 1):
                return True
        return False

    assert find_cycle(root, set()), "expected a cycle in the Fish state graph"
    value, realised = constructive_playout(root, solver)
    assert value == realised == 1.0


# ---------------------------------------------------------------------------
# the closed form, and playing the value out
# ---------------------------------------------------------------------------

def test_closed_form_is_exact_on_both_full_tables(solver):
    for m in (1, 2):
        table = solver.table(m)
        n = table.values.shape[0]
        idx = np.arange(n)
        turn = idx % 6
        rest = idx // 6
        comps = []
        for _ in range(m):
            comps.append(rest % e.NC)
            rest = rest // e.NC
        comps.reverse()
        f = np.zeros(n, dtype=np.int32)
        for c in comps:
            counts = e.COMP[c]
            has = np.zeros(n, dtype=bool)
            for off in (0, 2, 4):
                has |= counts[np.arange(n), (turn + off) % 6] > 0
            f += has
        pred = (np.where(turn % 2 == 0, 1, -1) * (2 * f - m)).astype(np.int16)
        assert np.array_equal(pred[table.valid], table.values[table.valid])


def test_playing_the_optimal_line_realises_the_value(solver):
    """Play the constructive drain-then-claim strategy for BOTH teams and
    check the realised set differential equals the computed value."""
    for pos in generate_m1_positions(20, seed=77) + generate_m2_positions(20, seed=78):
        state = rebuild(pos, RULES)
        got, realised = constructive_playout(state, solver)
        assert got == realised, (pos, got, realised)


def test_progress_optimal_is_a_subset_of_optimal(solver):
    seen_strict = 0
    for pos in generate_m2_positions(40, seed=79):
        state = rebuild(pos, RULES)
        best = solver.optimal_actions(state)
        prog = solver.progress_optimal_actions(state)
        assert all(a in best for a in prog)
        assert prog or solver.value(state) == 0.0
        seen_strict += len(prog) < len(best)
    assert seen_strict > 0, ("expected some position where a value-preserving "
                            "action makes no progress: that gap is the whole "
                            "point of the distinction")


def test_every_decided_state_has_a_progress_rank(solver):
    """Regression. Restricting the attractor to the thresholds that actually
    occur once left the rank at 0 for every losing state, which silently
    emptied ``progress_optimal_actions``. Checked over the whole table now,
    not on a sample."""
    for m in (1, 2):
        table = solver.table(m)
        decided = table.valid & (table.values != 0)
        assert decided.any()
        assert (table.ranks[decided] > 0).all()
        assert (table.ranks[table.valid & (table.values == 0)] == 0).all()


def test_reachable_solver_agrees_with_the_full_table(solver):
    rng = random.Random(5)
    for _ in range(6):
        comps = (rng.randrange(e.NC), rng.randrange(e.NC))
        turn = rng.randrange(6)
        if e.normalize_turn(turn, e.hand_sizes(comps)) != turn:
            continue
        sol = e.solve_reachable((comps, turn), solver._sub_value,
                                max_states=200_000)
        table = solver.table(2)
        for (c, t), v in sol.values.items():
            assert v == table.value(c, t)


def test_giveaway_claims_never_beat_a_legitimate_line(solver):
    """v1 refuses to generate a claim that hands the half-suit over. That is a
    restriction of the action set, so it is measured, not assumed."""
    plain = e.layer_table(1, giveaway=False)
    wide = e.layer_table(1, giveaway=True)
    assert np.array_equal(plain.values[plain.valid], wide.values[plain.valid])


def test_unsupported_rules_are_refused():
    with pytest.raises(e.UnsupportedRules):
        e.Exact2Solver(RuleConfig(claims_any_time=True))


def test_bluff_asks_change_the_layer_not_the_code():
    bluff = RuleConfig(allow_bluff_asks=True)
    s = e.Exact2Solver(bluff)
    hands = [mask("2C", "3C", "4C", "5C", "6C"), mask("7C"), 0, 0, 0, 0]
    st = make_endgame(bluff, [0], hands, turn=0)
    assert s.value(st) == 1.0


# ---------------------------------------------------------------------------
# the corpus
# ---------------------------------------------------------------------------

CORPUS = os.path.join(ROOT, "results", "exact_positions_v2.json")


@pytest.mark.skipif(not os.path.exists(CORPUS), reason="corpus not built")
def test_corpus_records_reproduce_their_own_ground_truth(solver):
    with open(CORPUS, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    from fish4.exact2_corpus import action_from_dict, state_from_record
    assert payload["schema_version"] == 2
    assert payload["summary"]["n_positions"] >= 300
    rng = random.Random(3)
    sample = rng.sample(payload["positions"], min(60, len(payload["positions"])))
    for rec in sample:
        state = state_from_record(rec)
        assert solver.value(state) == rec["value"]
        got = sorted(map(repr, solver.optimal_actions(state)))
        want = sorted(map(repr, [action_from_dict(d)
                                 for d in rec["optimal_actions"]]))
        assert got == want
        assert rec["live_cards"] == 6 * rec["n_live_half_suits"]
        for d in rec["optimal_actions"]:
            state.check_legal(state.turn, action_from_dict(d))


@pytest.mark.skipif(not os.path.exists(CORPUS), reason="corpus not built")
def test_corpus_covers_the_required_awkward_cases():
    with open(CORPUS, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    tags = payload["summary"]["tag_counts"]
    for required in ("nulled_half_suit_present", "empty_hand_present",
                     "forced_claim", "team_holds_nothing",
                     "stalling_action_is_bellman_optimal"):
        assert tags.get(required, 0) > 0, f"corpus has no {required} position"
    assert payload["summary"]["by_live_half_suits"].get("2", 0) > 0
    assert payload["summary"]["n_information_resolved"] > 0
