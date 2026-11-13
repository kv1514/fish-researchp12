"""``forced_claim`` scored a declaration with two different distributions.

``best_for_half_suit`` returns ``(p_exact, p_team_holds_all, Claim)``, and its
own docstring explains, three lines before the bug, that "the product of
marginals is not the joint: cards compete for the same quota slots, so per-card
modes can be jointly impossible" -- which is exactly why the MAP split is
shortlisted on the marginals and then SCORED on the posterior.

The second element was not. It stayed ``prod(sum of team marginals per card)``,
an independence product, while the first came from the joint. ``forced_claim``
then computes ``p_split = p_team - p_exact`` and reads it as "ours but wrongly
split" -- a difference between two different distributions, which can come out
negative and was clamped rather than caught. Under the baseline null rule the
ranking is ``p_exact + p_team - 1``, so the product carried EQUAL weight with
the joint.

Measured over 29406 half-suit queries in 60 games (scripts4/claim_joint_gap.py,
results/claim_joint_gap.json), the two disagree on 27902, and on 86% of those
the product OVERSTATES the joint -- by a median of 0.008 and by as much as
0.313. Overstating "our team holds it all" is the direction that makes a
declaration look safer than it is.

It also decides, if rarely. Over the 5885 positions in the same games where
``forced_claim`` could run, the product produced a NEGATIVE "ours but wrongly
split" 7 times -- clamped to zero and never surfaced -- and the joint changes
which half-suit gets declared at 31 of them.
"""

from __future__ import annotations

import random

import numpy as np

from fish.beliefs import BeliefState
from fish.cards import NUM_PLAYERS, half_suit_cards, team_of
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.agent4 import FishBot4
from fish4.askfeat import DecisionContext
from fish4.claim4 import ClaimConfig, ClaimEvaluator
from fish4.posterior import Posterior


def _play_to(seed: int, plies: int):
    """Deal, play `plies` plies, and hand back the acting seat's view."""
    rules = RuleConfig()
    st = GameState.deal(rules, seed=seed)
    agents = [FishBot4(opponent_gamma=0.35) for _ in range(NUM_PLAYERS)]
    for pi, a in enumerate(agents):
        a.begin_game(pi, rules, 6100 + pi)
    bels = [BeliefState(rules, observer=p) for p in range(NUM_PLAYERS)]
    for _ in range(plies):
        if st.is_terminal:
            break
        seat = st.turn
        for p in range(NUM_PLAYERS):
            bels[p].update(Observation.from_state(st, p))
        obs = Observation.from_state(st, seat)
        st.apply(seat, agents[seat].act(obs))
    seat = st.turn
    for p in range(NUM_PLAYERS):
        bels[p].update(Observation.from_state(st, p))
    return st, bels[seat], Observation.from_state(st, seat), seat


def test_prob_all_with_is_a_probability_and_bounds_prob_assignment():
    """P(all six with the team) can never be below P(one specific team split)."""
    st, bel, obs, seat = _play_to(71_000, 30)
    post = Posterior(bel, random.Random(3), n_draws=160, n_worlds=32,
                     obs=obs, gamma=0.35, mode="auto")
    team = [p for p in range(NUM_PLAYERS) if team_of(p) == team_of(seat)]
    ctx = DecisionContext(obs, bel, post)
    ce = ClaimEvaluator(ctx, ClaimConfig())
    seen = 0
    for p_exact, p_team, claim in ce.candidates():
        seen += 1
        assert 0.0 <= p_team <= 1.0 + 1e-9, p_team
        # The whole point: a specific split is one of the ways the half-suit
        # can be entirely ours, so it can never be MORE likely. With the
        # product this could fail; with the joint it cannot.
        assert p_exact <= p_team + 1e-9, (
            f"P(this split) = {p_exact} exceeds P(ours at all) = {p_team}, so "
            f"'ours but wrongly split' is negative")
    assert seen, "fixture produced no claim candidates"


def test_the_independence_product_really_does_differ_from_the_joint():
    """The control. Without it the fix is a preference, not a correction."""
    st, bel, obs, seat = _play_to(71_000, 30)
    post = Posterior(bel, random.Random(3), n_draws=160, n_worlds=32,
                     obs=obs, gamma=0.35, mode="auto")
    M = post.marginals()
    team = [p for p in range(NUM_PLAYERS) if team_of(p) == team_of(seat)]
    gaps = []
    for hs in obs.claimable_half_suits():
        cards = list(half_suit_cards(hs))
        prod = float(np.prod([sum(M[c][p] for p in team) for c in cards]))
        if prod <= 0.0:
            continue
        joint = post.prob_all_with(cards, team, 4096)
        gaps.append(joint - prod)
    assert gaps, "fixture produced no half-suit with positive team mass"
    assert any(abs(g) > 1e-6 for g in gaps), (
        "product and joint agree everywhere here, so this position does not "
        "demonstrate the difference; pick another")


def test_prob_all_with_matches_prob_assignment_when_one_split_is_possible():
    """Sanity: with the team's holding fully pinned, both are exactly 1."""
    st, bel, obs, seat = _play_to(71_000, 30)
    post = Posterior(bel, random.Random(3), n_draws=160, n_worlds=32,
                     obs=obs, gamma=0.35, mode="auto")
    team = [p for p in range(NUM_PLAYERS) if team_of(p) == team_of(seat)]
    # Every card in this seat's own hand is pinned to this seat, hence to the
    # team, so any subset of it is entirely ours with probability exactly 1.
    mine = [c for c in range(post.n) if obs.hand >> c & 1]
    assert len(mine) >= 2, "seat must hold at least two cards"
    assert post.prob_all_with(mine[:2], team, 4096) == 1.0
    assert post.prob_all_with(mine[:2], [seat], 4096) == 1.0
    # And a card the team provably does not hold takes it to exactly 0.
    others = [c for c in range(post.n)
              if not (obs.hand >> c & 1) and bel.public_loc[c] is not None
              and bel.public_loc[c] != -1
              and team_of(bel.public_loc[c]) != team_of(seat)]
    if others:
        assert post.prob_all_with([others[0]], team, 4096) == 0.0


def test_the_claim_screen_does_not_discard_a_claimable_half_suit():
    """The middle tier is an optimisation with a correctness claim inside it.

    ``best_for_half_suit`` skips the joint query when the independence product
    of the per-card MAP marginals is below ``ClaimConfig.screen`` (0.35), and
    returns the PRODUCT as the half-suit's probability. The comment justifying
    it says "most half-suits are nowhere near claimable" -- an assertion about
    a distribution that had never been checked, in a tier whose whole premise
    is that the product and the joint differ.

    If the product understates by enough, a half-suit whose true probability
    clears the 0.97 threshold is returned below 0.35, no claim is made, and
    nothing records that a certain set was left on the table.

    Two games here for the suite's sake; ``scripts4/claim_screen_check.py``
    runs the same measurement at 25 and stores it. At that size the largest
    true joint among 11,687 screened half-suits is 0.58, so the margin is wide
    -- but the gap between product and joint reaches +0.26 on individual
    half-suits, which is why the margin is what makes it safe and not the two
    agreeing.
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts4"))
    from claim_screen_check import measure

    out = measure(n_games=2, seed0=77_000)
    assert out["n_screened"] > 100, "fixture screened almost nothing"
    assert out["n_claimable_but_screened"] == 0, (
        f"{out['n_claimable_but_screened']} half-suits were screened out whose "
        f"true joint clears the {out['threshold']} claim threshold")
    # And the check has to be able to fail: if the product and the joint never
    # differed, this test would pass for the wrong reason.
    assert out["gap_max"] > 1e-6, (
        "product and joint agree on every screened half-suit here, so this "
        "sample cannot demonstrate the hazard")


def test_the_joint_query_does_not_blow_up_a_decision():
    """A correctness fix that made a decision ten times slower would be a
    different kind of problem, so the cost is bounded rather than assumed.

    Measured over 5044 queries in 8 games: mean 0.58 ms, p99 5.0 ms, max
    15.2 ms -- and the exact-DP path, the one that enumerates, tops out at
    2.3 ms. The tail belongs to the SAMPLING path, where the first query at a
    position pays to build the weighted batch that every other query at that
    position then reuses; ``prob_assignment`` pays exactly the same toll and
    the claim evaluator calls it first.

    The enumeration cap has never bound in real play (0 of 5044), which is the
    other thing worth knowing: at three teammates and six cards the worst case
    is 3^6 = 729 assignments against a cap of 4096, so the cap is a backstop
    for a wider variant rather than something the shipped game reaches.
    """
    import random
    import time

    from fish.cards import half_suit_cards
    from fish4.posterior import Posterior

    st, bel, obs, seat = _play_to(81_000, 30)
    post = Posterior(bel, random.Random(5), n_draws=160, n_worlds=32,
                     obs=obs, gamma=0.35, mode="auto")
    team = [p for p in range(NUM_PLAYERS) if team_of(p) == team_of(seat)]
    hss = list(obs.claimable_half_suits())
    assert hss, "fixture has no claimable half-suit"
    # Warm the batch first: the first query at a position builds it, and
    # timing that would be timing the sampler, not this method.
    post.prob_all_with(list(half_suit_cards(hss[0])), team, 4096)
    worst = 0.0
    for hs in hss:
        t0 = time.perf_counter()
        post.prob_all_with(list(half_suit_cards(hs)), team, 4096)
        worst = max(worst, time.perf_counter() - t0)
    assert worst < 0.05, f"a single joint query took {1000 * worst:.1f} ms"
    assert post.stats.capped_set_queries == 0, (
        "the enumeration cap bound here; if that becomes common the fallback "
        "to the independence product is back in the shipped path")
