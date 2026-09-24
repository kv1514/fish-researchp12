"""A diagnostic that changes the policy is not a diagnostic.

The whole value of a decision trace is that it reports what the engine did.
If switching it on perturbs the RNG, reorders a tie, or takes a different
branch, then the traced games are not the games the paper measured and the
panel explains a policy nobody ships. The first test here is the one that
matters; the rest keep the payload honest once it is on the wire.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, card_id                 # noqa: E402
from fish.engine import Ask, Claim, GameState, Pass         # noqa: E402
from fish.observation import Observation                    # noqa: E402
from fish.rules import RuleConfig                           # noqa: E402
from fish4.registry4 import V06_DEPLOYED, make_agent        # noqa: E402

RULES = RuleConfig(wrong_distribution_outcome="opponent")


def _play(trace: bool, seed: int = 4242):
    spec = (V06_DEPLOYED[0],
            dict(V06_DEPLOYED[1], **({"trace": True} if trace else {})))
    agents = [make_agent(spec) for _ in range(6)]
    st = GameState.deal(RULES, seed=seed)
    for p, a in enumerate(agents):
        a.begin_game(p, RULES, 700 + p)
    moves, traces = [], []
    for _ in range(600):
        if st.is_terminal:
            break
        t = st.turn
        action = agents[t].act(Observation.from_state(st, t))
        moves.append((t, repr(action)))
        traces.append((action, agents[t].last_trace))
        st.apply(t, action)
    return st, moves, traces, agents


def test_tracing_does_not_change_a_single_decision():
    """The load-bearing test: traced and untraced play must be identical."""
    off_state, off_moves, _, _ = _play(False)
    on_state, on_moves, _, _ = _play(True)
    assert off_moves == on_moves, "tracing changed the policy's choices"
    assert off_state.set_winner == on_state.set_winner
    assert len(off_moves) > 50, "fixture too short to be evidence"


def test_tracing_is_bit_identical_across_several_deals():
    """One deal could agree by luck; several sharing every move cannot."""
    for seed in (11, 2027, 98765):
        _, off, _, _ = _play(False, seed)
        _, on, _, _ = _play(True, seed)
        assert off == on, f"divergence on deal {seed}"


def test_an_untraced_agent_never_builds_a_trace():
    _, _, traces, agents = _play(False)
    assert all(t is None for _, t in traces)
    assert all(a.last_trace is None for a in agents)


def test_every_decision_is_traced():
    """A partial trace is worse than none: the gaps are invisible."""
    _, _, traces, _ = _play(True)
    missing = [i for i, (_, t) in enumerate(traces) if t is None]
    assert not missing, f"{len(missing)} untraced decisions at {missing[:5]}"


def test_the_trace_names_the_move_that_actually_happened():
    """Not the top-scoring one -- the one after the tie-break."""
    _, _, traces, _ = _play(True)
    checked = 0
    for action, tr in traces:
        if tr["kind"] == "ask" and isinstance(action, Ask):
            assert tr["chosen"]["target"] == action.target
            assert card_id(tr["chosen"]["card"]) == action.card
            checked += 1
        elif tr["kind"] == "declare" and isinstance(action, Claim):
            holders = tuple(r["holder"] for r in tr["split"])
            assert holders == tuple(action.assignment)
            checked += 1
        elif tr["kind"] == "pass" and isinstance(action, Pass):
            assert tr["teammate"] == action.teammate
            checked += 1
    assert checked > 40


def test_a_tie_group_is_reported_rather_than_hidden():
    """Ties are common and real; presenting rank 0 as preferred invents one."""
    _, _, traces, _ = _play(True)
    asks = [t for _, t in traces if t["kind"] == "ask"]
    assert asks
    assert all(t["tie_group"] >= 1 for t in asks)
    # Where the group is bigger than one, the chosen entry need not be rank 0.
    tied = [t for t in asks if t["tie_group"] > 1]
    assert tied, "fixture never hit a tie; the field would be untested"
    for t in tied:
        chosen = [r for r in t["ranked"] if r["chosen"]]
        # The chosen ask is always named in `chosen`, and appears in `ranked`
        # whenever it is inside the top N.
        assert len(chosen) <= 1


def test_cards_are_names_and_never_indices():
    """Same door rule as the v0.6 package: an index is meaningless off-site."""
    _, _, traces, _ = _play(True)
    for _, tr in traces:
        for row in tr.get("ranked", []):
            assert isinstance(row["card"], str)
            assert card_id(row["card"]) is not None
        for row in tr.get("split", []):
            assert isinstance(row["card"], str)
            assert 0 <= row["holder"] < NUM_PLAYERS
        if "chosen" in tr and isinstance(tr["chosen"], dict):
            assert isinstance(tr["chosen"]["card"], str)


def test_a_trace_survives_json():
    """It is going over a wire; numpy floats and ints do not."""
    _, _, traces, _ = _play(True)
    for _, tr in traces:
        round_tripped = json.loads(json.dumps(tr))
        assert round_tripped == tr


def test_declarations_carry_the_confidence_the_policy_held():
    _, _, traces, _ = _play(True)
    decls = [t for _, t in traces if t["kind"] == "declare"]
    assert decls, "fixture never declared"
    for t in decls:
        assert t["why"]
        assert len(t["split"]) == 6
        if "confidence" in t:
            assert 0.0 <= t["confidence"] <= 1.0
