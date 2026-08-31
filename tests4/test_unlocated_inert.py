"""`w_unlocated` must be inert at its default and real at any other value.

prereg/unlocated_belief.md fixes both halves of this before the measurement:

  "If the bit-identity test at w_unlocated = 0.0 fails, no measurement is read
   until it passes. A default that is not inert makes every cell a comparison
   against a moved baseline."

and the converse matters just as much. Three separate bugs once made
`opp_lambda` a no-op, and the two screening cells that measured it were
therefore measuring nothing -- see tests4/test_opp_lambda.py. A knob that
changes no weight at ANY setting produces a grid of identical cells and a
confident null, which is the most expensive kind of wrong answer here.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fish.beliefs import BeliefState                       # noqa: E402
from fish.cards import NUM_PLAYERS                         # noqa: E402
from fish.engine import GameState                          # noqa: E402
from fish.observation import Observation                   # noqa: E402
from fish.rules import RuleConfig                          # noqa: E402
from fish4.oppmodel import build                           # noqa: E402
from fish4.registry4 import V06_DEPLOYED, make_agent       # noqa: E402

RULES = RuleConfig(wrong_distribution_outcome="opponent")


def _position(seed: int = 4242, plies: int = 14):
    """A real mid-game position: belief, observation, and the seat to move."""
    agents = [make_agent(("kraken", dict(V06_DEPLOYED[1])))
              for _ in range(NUM_PLAYERS)]
    st = GameState.deal(RULES, seed=seed)
    for p, a in enumerate(agents):
        a.begin_game(p, RULES, seed + 7 * p)
    bels = [BeliefState(RULES, observer=p) for p in range(NUM_PLAYERS)]
    for _ in range(plies):
        if st.is_terminal:
            break
        mover = st.turn
        for q in range(NUM_PLAYERS):
            bels[q].update(Observation.from_state(st, q))
        st.apply(mover, agents[mover].act(Observation.from_state(st, mover)))
    mover = st.turn
    for q in range(NUM_PLAYERS):
        bels[q].update(Observation.from_state(st, q))
    return bels[mover], Observation.from_state(st, mover)


def _weights(bel, obs, **kw):
    model, _ = build(bel, obs, gamma=0.35, **kw)
    return None if model is None else list(model.weight)


def test_the_default_is_bit_identical_to_the_incumbent():
    bel, obs = _position()
    incumbent = _weights(bel, obs)
    assert incumbent, "the position produced no weights; the test proves nothing"
    explicit = _weights(bel, obs, w_unlocated=0.0)
    assert explicit == incumbent, (
        "w_unlocated=0.0 moved the weights. Every grid cell would then be "
        "compared against a baseline that is not the shipped engine.")


def test_a_live_weight_actually_reaches_the_weights():
    """Guard against the opp_lambda failure: a knob that measures nothing."""
    bel, obs = _position()
    incumbent = _weights(bel, obs)
    live = _weights(bel, obs, w_unlocated=-4.0)
    assert live != incumbent, (
        "w_unlocated=-4.0 changed no weight, so a grid over it would score "
        "identical cells and report a null that means nothing.")


def test_the_factor_is_public_loc_and_not_our_private_candidates():
    """The covariate must be the one the fit scored: common knowledge.

    `candidates` is narrowed by the observing seat's own hand, so it is this
    seat's PRIVATE view. The choice model is a claim about what the ASKER was
    looking at, and scripts4/choice_curve.py recorded `public_loc[c] is None`
    for that reason. Scoring the belief against a differently-defined
    covariate is the transfer error that closed the w_expose direction without
    a game being played.

    Discriminating by the RATIO between the two weight vectors, rather than by
    slot index: OpponentModel carries no (player, half_suit) map -- its
    docstring claimed a `pair_index` that has never existed -- and a test that
    cannot distinguish the two definitions would pass either way.
    """
    seeds = (4242, 11, 907, 5150, 33, 8081)
    for seed in seeds:
        bel, obs = _position(seed=seed)
        w0 = _weights(bel, obs)
        ww = _weights(bel, obs, w_unlocated=-2.0)
        if not w0:
            continue

        def factors(unloc):
            return {round(float(max(unloc(hs), 1)) ** -2.0, 12)
                    for hs in range(bel.n // 6)}

        pub = factors(lambda hs: sum(1 for c in range(hs * 6, hs * 6 + 6)
                                     if bel.public_loc[c] is None))
        priv = factors(lambda hs: sum(1 for c in range(hs * 6, hs * 6 + 6)
                                      if bel.candidates[c].bit_count() > 1))
        ratios = {round(b / a, 12) for a, b in zip(w0, ww) if a}
        assert ratios <= pub, (
            f"seed {seed}: observed weight ratios {sorted(ratios)} are not all "
            f"public_loc factors {sorted(pub)}")
        if pub != priv and not (ratios <= priv):
            return          # discriminated: public yes, private no
    raise AssertionError(
        "no seed produced a position where the public and private counts "
        "disagree, so this test cannot tell the two definitions apart. It "
        "would pass against the wrong covariate; widen `seeds` rather than "
        "letting it stand.")


def test_zero_unlocated_does_not_explode():
    """u = 0 is legal and the exponent is negative; 0 ** -4 is unbounded.

    The clamp is max(u, 1), fixed in the pre-registration rather than after
    seeing a score. This pins the arithmetic directly, since a position with
    every card of a half-suit publicly placed is rare enough that a game-based
    test could pass for a long time without ever reaching one.
    """
    assert float(max(0, 1)) ** -4.0 == 1.0
    assert float(max(1, 1)) ** -4.0 == 1.0
    assert float(max(2, 1)) ** -4.0 == 0.0625
