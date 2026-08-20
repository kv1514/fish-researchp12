"""Decision-theoretic claim policy tests.

The point of this module is that the claim threshold should be DERIVED, not
assumed, so the tests pin down the properties the derivation must have
rather than any particular number.
"""

import pytest

from fish.agents import EVClaimAgent
from fish.agents.claim_policy import (ClaimEV, best_claim_decision,
                                      claim_now_ev, should_claim, wait_ev)
from fish.rules import RuleConfig
from fish.runner import play_game


def ev(p_exact, p_team=None):
    return ClaimEV(p_exact=p_exact,
                   p_team_holds=p_team if p_team is not None else p_exact,
                   hs=0, claim=object())


def test_claim_ev_is_monotone_in_confidence():
    vals = [claim_now_ev(ev(p)) for p in (0.1, 0.3, 0.5, 0.7, 0.9, 1.0)]
    assert vals == sorted(vals)
    assert claim_now_ev(ev(1.0, 1.0)) == pytest.approx(1.0)


def test_certain_claim_is_always_taken():
    assert should_claim(ev(1.0, 1.0))


def test_hopeless_claim_is_never_taken():
    # opponents certainly hold at least one card
    assert not should_claim(ClaimEV(p_exact=0.0, p_team_holds=0.0, hs=0,
                                    claim=object()))


def test_opponent_rule_makes_claiming_stricter():
    """Under wrong_distribution_outcome='opponent', a mis-split gifts the set,
    so the same confidence must be worth less."""
    c = ev(0.6, 0.9)
    assert claim_now_ev(c, "opponent") < claim_now_ev(c, "null")


def test_threshold_is_derived_and_below_naive_intuition():
    """The EV rule should fire well below the hand-picked 0.97 that the
    baseline agent used; that is the substantive prediction being made."""
    fires = [p for p in [i / 100 for i in range(1, 101)]
             if should_claim(ev(p, min(1.0, p + 0.05)))]
    assert fires, "policy never claims"
    threshold = min(fires)
    assert 0.5 < threshold < 0.95, threshold


def test_wait_is_preferred_when_split_is_resolvable():
    """Team certainly holds the set but the split is unknown: waiting to
    localize it should beat a coin-flip claim."""
    c = ClaimEV(p_exact=0.35, p_team_holds=1.0, hs=0, claim=object())
    assert wait_ev(c) > claim_now_ev(c)


def test_best_claim_decision_picks_largest_gain():
    a = ev(0.99, 1.0)
    b = ev(0.55, 0.6)
    got = best_claim_decision([b, a])
    assert got is not None and got[0] is a.claim


def test_ev_claim_agent_plays_legal_terminating_games():
    rules = RuleConfig()
    for seed in range(3):
        st = play_game([EVClaimAgent() for _ in range(6)], rules, seed=seed,
                       agent_seed=seed * 17 + 3, debug=True)
        assert st.is_terminal
