"""The gate has to actually gate, and these tests are how that is known.

A gated cheat that silently leaks into the other channel would produce exactly
the shape of number the experiment is looking for -- a large declare-only
effect -- for entirely the wrong reason. So the checks here are behavioural and
mechanical rather than structural:

  * a DECLARE-mode oracle knows every teammate card when it names a split, so
    it must never name a wrong one. Not "rarely". Never.
  * an ASK-mode oracle's claim channel is honest, so it must misdeclare at
    about the honest rate -- if it also never misdeclares, the cheat is
    reaching the claim channel and the decomposition is void.
  * BOTH mode must reproduce the existing OracleBot(side="team") arm, because
    the whole decomposition is anchored to that published +3.41.
"""

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, half_suit_cards, team_of
from fish.engine import Claim, ClaimEvent, GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.registry4 import V06_DEPLOYED, make_agent

RULES = RuleConfig(wrong_distribution_outcome="opponent")


def _owners(st):
    return [next(q for q in range(NUM_PLAYERS) if st.hands[q] >> c & 1)
            for c in range(54)]


def play(mode, n_games=8, seed0=3_100_000, our_seats=(0, 2, 4)):
    """Play games with our three seats gated, and count declaration outcomes."""
    wrong = right = 0
    for g in range(n_games):
        st = GameState.deal(RULES, seed=seed0 + g)
        owners = _owners(st)
        agents = []
        for p in range(NUM_PLAYERS):
            if p in our_seats and mode is not None:
                a = make_agent(("oracle_gated",
                                dict(V06_DEPLOYED[1], mode=mode)))
                a.see_deal(owners)
            else:
                a = make_agent(("kraken", dict(V06_DEPLOYED[1])))
            a.begin_game(p, RULES, seed0 + 999 + g * 13 + p)
            agents.append(a)
        step = 0
        while not st.is_terminal and step < 400:
            m = st.turn
            st.apply(m, agents[m].act(Observation.from_state(st, m)))
            step += 1
        for ev in st.history:
            if isinstance(ev, ClaimEvent) and ev.claimer in our_seats:
                if ev.winner == team_of(ev.claimer):
                    right += 1
                else:
                    wrong += 1
    return right, wrong


def test_a_declare_mode_oracle_never_names_a_wrong_split():
    """The load-bearing test. Its claim channel is handed every teammate card,
    so a wrong split is not unlikely -- it is impossible. Any failure here means
    the cheat is not reaching the claim channel."""
    right, wrong = play("declare", n_games=10)
    assert right + wrong > 0, "no declarations at all -- test proves nothing"
    assert wrong == 0, f"declare-mode oracle misdeclared {wrong} times"


def test_an_ask_mode_oracle_still_misdeclares():
    """The mirror, and the one that catches a leak. Its claim channel is honest,
    so it must get splits wrong at roughly the honest rate. If this comes back
    zero the gate is inverted or the cheat is reaching both channels."""
    _, wrong_ask = play("ask", n_games=40)
    _, wrong_honest = play(None, n_games=40)
    assert wrong_honest > 0, "the honest engine misdeclared 0 times in 40 " \
                             "games -- widen the sample, this proves nothing"
    assert wrong_ask > 0, ("ask-mode oracle never misdeclared, so its claim "
                           "channel is seeing the truth and the "
                           "decomposition is void")


def test_both_mode_reproduces_the_published_teammate_oracle():
    """BOTH is the anchor: it must play the same games as the OracleBot arm the
    +3.41 was measured with, or the decomposition is anchored to nothing."""
    from fish4.oracle import OracleBot

    for g in range(4):
        seeds = 3_400_000 + g
        moves = {}
        for which in ("gated", "oracle"):
            st = GameState.deal(RULES, seed=seeds)
            owners = _owners(st)
            agents = []
            for p in range(NUM_PLAYERS):
                if p % 2 == 0:
                    if which == "gated":
                        a = make_agent(("oracle_gated",
                                        dict(V06_DEPLOYED[1], mode="both",
                                             side="team")))
                    else:
                        a = OracleBot(side="team", reveal=1.0,
                                      **dict(V06_DEPLOYED[1]))
                    a.see_deal(owners)
                else:
                    a = make_agent(("kraken", dict(V06_DEPLOYED[1])))
                a.begin_game(p, RULES, seeds + 77 + p)
                agents.append(a)
            seq, step = [], 0
            while not st.is_terminal and step < 400:
                m = st.turn
                act = agents[m].act(Observation.from_state(st, m))
                seq.append((m, repr(act)))
                st.apply(m, act)
                step += 1
            moves[which] = seq
        assert moves["gated"] == moves["oracle"], (
            f"game {g}: gated both-mode diverged from OracleBot(side='team') "
            f"at move {next(i for i, (a, b) in enumerate(zip(moves['gated'], moves['oracle'])) if a != b)}")


def test_it_refuses_to_run_as_an_honest_agent():
    a = make_agent(("oracle_gated", dict(V06_DEPLOYED[1], mode="declare")))
    a.begin_game(0, RULES, 1)
    st = GameState.deal(RULES, seed=1)
    with pytest.raises(RuntimeError, match="see_deal"):
        a.act(Observation.from_state(st, 0))


def test_the_two_beliefs_stay_in_step_on_public_events():
    """Both beliefs must ingest every observation. If the honest one falls
    behind, the 'honest' channel is not honest -- it is stale, which is worse
    and would look like a real effect."""
    st = GameState.deal(RULES, seed=3_700_001)
    owners = _owners(st)
    agents = []
    for p in range(NUM_PLAYERS):
        if p % 2 == 0:
            a = make_agent(("oracle_gated",
                            dict(V06_DEPLOYED[1], mode="declare")))
            a.see_deal(owners)
        else:
            a = make_agent(("kraken", dict(V06_DEPLOYED[1])))
        a.begin_game(p, RULES, 4242 + p)
        agents.append(a)
    step = 0
    while not st.is_terminal and step < 120:
        m = st.turn
        st.apply(m, agents[m].act(Observation.from_state(st, m)))
        step += 1
    a = agents[0]
    # the honest belief must know at least everything the public record forces
    for c in range(54):
        if a.bel.public_loc[c] is not None:
            assert a._other.public_loc[c] == a.bel.public_loc[c]
