"""Depth at the moment of the ask, and why it costs nothing.

The opponent model conditions on how deep a player was in the half-suit they
asked in. It uses their depth on the INITIAL DEAL, because that is what the
sampler assigns, and the module has always been explicit that this is a proxy:
cards move, so late in a game the initial deal and the hand they actually held
diverge.

Measured on 17,005 real decisions, the proxy is expensive. Refitting the choice
model on depth at the moment of the ask beats initial-deal depth by 4,654 nats
-- the shipped covariate reaches 1,403 nats above uniform where the same
one-parameter family reaches 6,057.

The reason it costs nothing to fix is a fact about the rules:

    depth_at_ask(p, H) = depth_initial(p, H) + delta(p, H, t)

Cards move only when an ask succeeds, and a successful ask is entirely public --
card, asker and target are all in the log -- so ``delta`` is the same number in
every hypothesised world. The sampler goes on assigning initial deals and the
likelihood adds a constant it knew before drawing anything.

That identity is the whole basis of the mode, so it is tested directly against
the engine rather than assumed, including in the places it could quietly fail:
claims removing cards, the observer's own asks moving cards between other
people's slots, and a failed ask moving nothing.
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fish.beliefs import BeliefState                             # noqa: E402
from fish.cards import NUM_PLAYERS, half_suit_cards, half_suit_of  # noqa: E402
from fish.engine import AskEvent, ClaimEvent, GameState          # noqa: E402
from fish.observation import Observation                         # noqa: E402
from fish.rules import RuleConfig                                # noqa: E402
from fish4.posterior import Posterior                            # noqa: E402
from fish4.registry4 import make_agent                           # noqa: E402

from tests4.test_leakage4 import collect_positions               # noqa: E402

SPEC = {"opponent_gamma": 0.35}


def _public_delta(history, n_hs=9):
    """Net publicly-transferred cards of each half-suit, per player."""
    d = [[0] * n_hs for _ in range(NUM_PLAYERS)]
    for ev in history:
        if isinstance(ev, AskEvent) and ev.success:
            h = half_suit_of(ev.card)
            d[ev.asker][h] += 1
            d[ev.target][h] -= 1
    return d


def _depth(hand, hs):
    return sum(1 for c in half_suit_cards(hs) if hand >> c & 1)


@pytest.mark.parametrize("seed", [4200, 4231, 4262])
def test_initial_depth_plus_the_public_delta_is_the_current_depth(seed):
    """The identity the whole mode rests on, checked against the engine."""
    rules = RuleConfig()
    st = GameState.deal(rules, seed=seed)
    initial = list(st.hands)
    agents = [make_agent(("fishbot4", SPEC)) for _ in range(NUM_PLAYERS)]
    ar = random.Random(seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, ar.getrandbits(64))

    checked = 0
    step = 0
    while not st.is_terminal and step < 300:
        delta = _public_delta(st.history)
        gone = {ev.half_suit for ev in st.history
                if isinstance(ev, ClaimEvent)}
        for q in range(NUM_PLAYERS):
            for h in range(9):
                if h in gone:
                    continue         # a claimed half-suit leaves play entirely
                assert _depth(initial[q], h) + delta[q][h] == _depth(st.hands[q], h), (
                    f"seed {seed} step {step}: seat {q}, half-suit {h}")
                checked += 1
        st.apply(st.turn, agents[st.turn].act(
            Observation.from_state(st, st.turn)))
        step += 1
    assert checked > 500, f"only {checked} triples checked"


def test_a_failed_ask_moves_nothing():
    """The delta must follow the outcome, not the attempt."""
    hist = (AskEvent(asker=1, target=0, card=7, success=False),)
    d = _public_delta(hist)
    assert all(v == 0 for row in d for v in row)


def test_the_observers_own_asks_still_move_cards():
    """They are excluded from the MODEL and not from the world.

    ``build`` skips the observer's own asks when forming slots, because there is
    nothing to infer about a hand it can see. The cards those asks moved still
    moved, and other players' deltas depend on them, so a builder that skipped
    the transfer along with the slot would corrupt every other slot in the
    half-suit.
    """
    from fish4.oppmodel import build
    rules = RuleConfig()
    positions = collect_positions(4, 3, 12)
    found = False
    for rules_, hands, sw, turn, hist, seat in positions:
        if not any(isinstance(e, AskEvent) and e.asker == seat and e.success
                   for e in hist):
            continue
        found = True
        obs = Observation(player=seat, rules=rules_, hand=hands[seat], turn=turn,
                          hand_counts=tuple(h.bit_count() for h in hands),
                          set_winner=tuple(sw), history=hist)
        bel = BeliefState(rules_, observer=seat)
        bel.update(obs)
        om, _ = build(bel, obs, gamma=0.35, depth_mode="at_ask")
        if om is None:
            continue
        assert om.depth_table is not None
        # every entry finite: an unaccounted transfer would drive a depth
        # negative and the log to the 1e-9 floor for a reachable world
        flat = [v for row in om.depth_table for v in row]
        assert all(np.isfinite(v) for v in flat)
    if not found:
        pytest.skip("no harvested position had a successful ask by the seat")


# ---------------------------------------------------------------------------
# The mode itself
# ---------------------------------------------------------------------------

def _marginals(pos, mode, seed, n_draws=160):
    rules, hands, sw, turn, hist, seat = pos
    obs = Observation(player=seat, rules=rules, hand=hands[seat], turn=turn,
                      hand_counts=tuple(h.bit_count() for h in hands),
                      set_winner=tuple(sw), history=hist)
    bel = BeliefState(rules, observer=seat)
    bel.update(obs)
    return np.asarray(Posterior(bel, random.Random(seed), n_draws=n_draws,
                                obs=obs, gamma=0.35,
                                depth_mode=mode).marginals())


def test_the_default_is_still_the_initial_deal():
    import inspect
    from fish4.agent4 import FishBot4
    assert inspect.signature(FishBot4).parameters["depth_mode"].default == "initial"


def test_at_ask_changes_the_posterior_on_most_positions():
    positions = collect_positions(4, 3, 16)
    differed = sum(
        1 for i, p in enumerate(positions)
        if not np.array_equal(_marginals(p, "initial", 900 + i),
                              _marginals(p, "at_ask", 900 + i)))
    assert differed >= len(positions) // 2, (
        f"only {differed}/{len(positions)} positions moved; the mode is not "
        "reaching the likelihood")


def test_the_two_sampler_paths_agree_on_the_new_likelihood():
    """The vectorised path gathers from a table; the scalar one indexes it.

    A mismatch here would be invisible in play -- both produce plausible
    marginals -- and would mean the fast path, which is the one that actually
    runs, is estimating a different posterior from the one the tests validate.
    """
    from fish4.sisbatch import draw_batch
    worst, checked = 0.0, 0
    for mode in ("initial", "at_ask"):
        for i, pos in enumerate(collect_positions(4, 3, 8)):
            rules, hands, sw, turn, hist, seat = pos
            obs = Observation(player=seat, rules=rules, hand=hands[seat],
                              turn=turn,
                              hand_counts=tuple(h.bit_count() for h in hands),
                              set_winner=tuple(sw), history=hist)
            bel = BeliefState(rules, observer=seat)
            bel.update(obs)
            post = Posterior(bel, random.Random(500 + i), n_draws=128, obs=obs,
                             gamma=0.35, depth_mode=mode)
            post.marginals()
            smp = post._sampler
            if smp is None or smp.opponent_model is None or smp._n == 0:
                continue
            om = smp.opponent_model
            picks, _, logl, alive = draw_batch(smp, random.Random(11), 32)
            for r in range(picks.shape[0]):
                if not alive[r]:
                    continue
                depth = [0] * om.n_slots
                for j in range(smp._n):
                    cand = smp._ocand[j]
                    slot = (smp._otilt[j][cand.index(int(picks[r, j]))]
                            if smp._otilt else -1)
                    if slot >= 0:
                        depth[slot] += 1
                worst = max(worst,
                            abs(om.log_likelihood_from_depths(depth)
                                - float(logl[r])))
                checked += 1
    assert checked > 200, f"only {checked} draws compared"
    assert worst < 1e-9, f"paths disagree by {worst:.3e}"


# ---------------------------------------------------------------------------
# The table has to reproduce the weight the parameters describe
#
# gamma, count_mode and gamma_schedule are folded into the per-slot log terms.
# If that folding is wrong the model still runs and still produces plausible
# marginals -- it just weights the evidence differently from what the parameters
# say, which is the kind of error that survives a duel and shows up as an
# unexplained tuning shift months later.
# ---------------------------------------------------------------------------

def test_a_single_ask_slot_reduces_exactly_to_the_incumbent():
    """A slot's FIRST ask always has delta zero, so the two must coincide.

    Delta is the net of that half-suit's publicly transferred cards for that
    player. To have received one before their own first ask in the half-suit,
    they would have had to ask in it earlier -- so the first ask of every slot
    sits at delta zero by construction, and a slot with exactly one ask must
    reproduce the incumbent term for term at every depth.

    This is the check that would catch a sign error or an off-by-one in the
    delta bookkeeping, and it needs no special fixture: single-ask slots are the
    common case.
    """
    from fish4.oppmodel import build
    worst, n_single = 0.0, 0
    for rules, hands, sw, turn, hist, seat in collect_positions(6, 3, 30):
        obs = Observation(player=seat, rules=rules, hand=hands[seat], turn=turn,
                          hand_counts=tuple(h.bit_count() for h in hands),
                          set_winner=tuple(sw), history=hist)
        bel = BeliefState(rules, observer=seat)
        bel.update(obs)
        a, _ = build(bel, obs, gamma=0.35, depth_mode="at_ask")
        b, _ = build(bel, obs, gamma=0.35, depth_mode="initial")
        if a is None or a.depth_table is None:
            continue
        for si in range(a.n_slots):
            if round(b.weight[si] / 0.35) != 1:      # linear counting
                continue
            n_single += 1
            for d in range(len(a.depth_table[si])):
                ref = b.weight[si] * np.log(max(d + b.base[si], 1e-9))
                worst = max(worst, abs(a.depth_table[si][d] - ref))
    assert n_single > 20, f"only {n_single} single-ask slots found"
    assert worst < 1e-12, (
        f"single-ask slots differ from the incumbent by {worst:.3e}")


@pytest.mark.parametrize("count_mode", ["linear", "sqrt", "capped"])
@pytest.mark.parametrize("schedule", [0.0, 1.0])
def test_it_composes_with_the_other_weight_modifiers(count_mode, schedule):
    """Every combination builds, stays finite, and rises with depth.

    Monotonicity is the invariant worth asserting. Each term is
    ``log(d + base + delta)`` scaled by a non-negative multiplier -- gamma times
    a count factor times a schedule factor that is clamped at zero -- so a slot's
    entry can only increase with the depth the sampler gives it. A sign error in
    the folding, or a negative multiplier slipping through, breaks that.

    Note what is NOT asserted: that entries stay away from the ``log(1e-9)``
    floor. An early draft required exactly that and failed, and the code was
    right. The floor appears at any depth where ``d + base + delta <= 0``, which
    describes a player asking in a half-suit they hold nothing of -- forbidden by
    the rules, so the floor is excluding an impossible world rather than
    softening an awkward one. That is what the floor is for, and a test that
    forbade it would have forced the model to entertain worlds the game cannot
    produce.
    """
    from fish4.oppmodel import build
    seen = 0
    for rules, hands, sw, turn, hist, seat in collect_positions(4, 3, 12):
        obs = Observation(player=seat, rules=rules, hand=hands[seat], turn=turn,
                          hand_counts=tuple(h.bit_count() for h in hands),
                          set_winner=tuple(sw), history=hist)
        bel = BeliefState(rules, observer=seat)
        bel.update(obs)
        om, _ = build(bel, obs, gamma=0.35, depth_mode="at_ask",
                      count_mode=count_mode, gamma_schedule=schedule)
        if om is None or om.depth_table is None:
            continue
        for row in om.depth_table:
            assert all(np.isfinite(v) for v in row)
            assert all(a <= b + 1e-12 for a, b in zip(row, row[1:])), (
                f"a slot's likelihood falls as its depth rises: "
                f"{[round(v, 3) for v in row]}")
            seen += 1
    assert seen > 0, "no tables built for this combination"
