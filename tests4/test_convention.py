"""The pre-play naming convention: encoding, and the two paths that read it.

The one thing these tests exist to prevent is a DEAD TERM READING AS A NULL.
That failure has now happened twice in this project. First in `oppmodel.build`,
where the early return consulted `gamma` but not `gamma_team`, so an entire
sweep row came back bit-identical and looked like a measured negative result.
Then here: the convention's likelihood was wired into `SISSampler._attempt`,
which is the SCALAR sampler and is no longer the path any decision takes --
`sample_batch` calls `draw_batch` in fish4/sisbatch.py, which never materialises
the per-draw deal dict the scalar likelihood reads. The inertness check
faithfully reported the decoder as bit-identical to the incumbent on every seed.
Nothing was broken in a way any existing test could see; the term simply was not
there.

So the load-bearing test in this file is not `is_encoded`. It is
`test_the_live_batch_path_actually_moves_the_posterior`, which asserts that
turning the parameter on changes a real number, and
`test_the_two_implementations_agree_world_by_world`, which is what makes the
scalar version -- now reachable only from tests -- an oracle rather than a
second implementation free to drift.
"""

import random
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.beliefs import BeliefState
from fish.cards import NUM_PLAYERS, half_suit_cards
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.convention import (depth_in, encode_cost, encoded_card,
                              encoded_position_table, is_encoded, legal_cards)
from fish4.posterior import Posterior
from fish4.registry4 import V06_DEPLOYED, make_agent

RULES = RuleConfig(wrong_distribution_outcome="opponent")
BETA = 0.8


def _mask(cards):
    m = 0
    for c in cards:
        m |= 1 << c
    return m


# --------------------------------------------------------------------------
# the encoding itself
# --------------------------------------------------------------------------

def test_the_encoded_card_is_never_one_the_seat_holds():
    """An ask names a card you do NOT hold. A convention that named a held
    card would be illegal to follow, which would make the sender's gate a lie
    and the receiver's forward test unfalsifiable."""
    rng = random.Random(11)
    for _ in range(2000):
        hs = rng.randrange(9)
        cards = list(half_suit_cards(hs))
        hand = _mask(rng.sample(cards, rng.randrange(0, 6)))
        enc = encoded_card(hand, hs)
        assert enc is not None
        assert not (hand >> enc & 1)
        assert enc in cards


def test_a_full_holding_has_nothing_to_say():
    hs = 3
    full = _mask(half_suit_cards(hs))
    assert legal_cards(full, hs) == []
    assert encoded_card(full, hs) is None
    assert is_encoded(full, hs, next(iter(half_suit_cards(hs)))) is False


def test_the_encoding_separates_depths_which_is_the_whole_point():
    """The message is the asker's depth. If two different depths encoded to
    the same card from overlapping holdings the channel would carry nothing,
    so pin that the map is not constant."""
    hs = 0
    seen = {}
    rng = random.Random(5)
    for _ in range(4000):
        k = rng.randrange(0, 6)
        hand = _mask(rng.sample(list(half_suit_cards(hs)), k))
        seen.setdefault(depth_in(hand, hs), set()).add(encoded_card(hand, hs))
    assert len(seen) == 6
    # at least one depth must name a card some other depth never names
    assert len(set().union(*seen.values())) > 1


def test_the_lookup_table_is_the_same_function_as_encoded_card():
    """The vectorised sampler applies the convention through a 64-entry gather
    rather than by calling `encoded_card` per drawn world. If the two ever
    disagree the engine measures one convention and the paper describes
    another, so tie them together for every holding of every half-suit."""
    table = encoded_position_table()
    assert len(table) == 64
    for hs in range(9):
        lo = min(half_suit_cards(hs))
        for mask in range(64):
            hand = 0
            for i in range(6):
                if mask >> i & 1:
                    hand |= 1 << (lo + i)
            enc = encoded_card(hand, hs)
            if enc is None:
                assert table[mask] == -1
            else:
                assert table[mask] == enc - lo


def test_encode_cost_is_zero_exactly_when_the_convention_card_is_best():
    hs = 1
    cards = list(half_suit_cards(hs))
    hand = _mask(cards[:2])
    enc = encoded_card(hand, hs)
    M = [[0.0] * NUM_PLAYERS for _ in range(54)]
    opps = [1, 3, 5]
    for c in cards:
        M[c][1] = 0.2
    M[enc][1] = 0.9
    assert encode_cost(M, hand, hs, opps) == pytest.approx(0.0)
    other = next(c for c in cards if c != enc and not (hand >> c & 1))
    M[other][3] = 0.95
    assert encode_cost(M, hand, hs, opps) == pytest.approx(0.05)


# --------------------------------------------------------------------------
# the part that was actually broken
# --------------------------------------------------------------------------

def _positions(n_games=2, stride=5, limit=10):
    """Real mid-game positions with their observing belief."""
    spec = dict(V06_DEPLOYED[1])
    out = []
    for g in range(n_games):
        agents = [make_agent(("kraken", dict(spec)))
                  for _ in range(NUM_PLAYERS)]
        st = GameState.deal(RULES, seed=990_000 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, RULES, 991_000 + g * 13 + p)
        bels = [BeliefState(RULES, observer=p) for p in range(NUM_PLAYERS)]
        step = 0
        while not st.is_terminal and step < 400 and len(out) < limit:
            mover = st.turn
            for q in range(NUM_PLAYERS):
                bels[q].update(Observation.from_state(st, q))
            if step > 10 and step % stride == 0:
                out.append((bels[mover], Observation.from_state(st, mover),
                            step))
            st.apply(mover, agents[mover].act(Observation.from_state(st,
                                                                    mover)))
            step += 1
        if len(out) >= limit:
            break
    return out


def _marginals(bel, obs, seed, **kw):
    spec = V06_DEPLOYED[1]
    return Posterior(bel, random.Random(seed), n_draws=spec["n_draws"],
                     obs=obs, gamma=spec["opponent_gamma"], **kw).marginals()


def test_beta_zero_is_bit_identical_to_the_incumbent():
    """The inert default. Every parameter in this engine ships at a value that
    reproduces the measured champion exactly, so that a sweep's zero row is the
    champion and not an approximation of it."""
    for bel, obs, step in _positions(limit=6):
        a = _marginals(bel, obs, 4242 + step)
        b = _marginals(bel, obs, 4242 + step, convention_beta=0.0)
        assert (a == b).all()


def test_the_live_batch_path_actually_moves_the_posterior():
    """THE REGRESSION TEST. A decoder wired into a path no decision takes is
    indistinguishable, from the outside, from a decoder that has been measured
    and found to do nothing. Assert the difference."""
    moved = 0
    positions = _positions(limit=10)
    assert positions, "no positions generated"
    for bel, obs, step in positions:
        a = _marginals(bel, obs, 4242 + step)
        b = _marginals(bel, obs, 4242 + step, convention_beta=BETA)
        if any(abs(a[c][p] - b[c][p]) > 1e-9
               for c in range(54) for p in range(NUM_PLAYERS)):
            moved += 1
    # It need not move every position -- our own side may not have asked yet,
    # and a posterior already concentrated cannot move much -- but a decoder
    # that moves NONE of ten real positions is not running.
    assert moved >= 5, f"convention moved only {moved}/{len(positions)}"


def test_the_two_implementations_agree_world_by_world():
    """`OpponentModel.log_convention` is reachable only from the scalar
    sampler, which no decision uses. That is fine as long as it is an ORACLE:
    a slow, obvious, per-world implementation that the fast one is checked
    against. It stops being fine the moment the two can drift, so check them
    against each other on real drawn worlds."""
    import numpy as np

    from fish4.oppmodel import build as build_opponent
    from fish4.convention import encoded_position_table

    table = encoded_position_table()
    checked = 0
    for bel, obs, step in _positions(limit=6):
        free = [c for c in range(54) if bel.candidates[c].bit_count() > 1]
        om, _ = build_opponent(bel, obs, V06_DEPLOYED[1]["opponent_gamma"],
                               convention_beta=BETA, order=free)
        if om is None or not om.convention:
            continue
        post = Posterior(bel, random.Random(77 + step),
                         n_draws=V06_DEPLOYED[1]["n_draws"], n_worlds=24,
                         obs=obs, gamma=V06_DEPLOYED[1]["opponent_gamma"],
                         convention_beta=BETA)
        worlds = post.worlds()
        if not worlds:
            continue
        for w in worlds[:12]:
            # the scalar oracle, straight off the assignment
            deal = {}
            for c in free:
                for q in range(NUM_PLAYERS):
                    if w[q] >> c & 1:
                        deal[c] = q
                        break
            slow = om.log_convention(deal)
            # the vectorised form, one holding mask per ask
            fast = 0.0
            for (asker, hs, card, const_mask, free_cards,
                 _g, _gc, _gf, _t) in om.convention:
                lo = hs * 6
                held = (const_mask >> lo) & 0x3F
                for c in free_cards:
                    if deal.get(c) == asker:
                        held |= 1 << (c - lo)
                if table[held] == card - lo:
                    fast += BETA
            assert abs(slow - fast) < 1e-12
            checked += 1
    assert checked > 0, "no worlds checked -- the oracle test proved nothing"


# --------------------------------------------------------------------------
# the mixture likelihood
# --------------------------------------------------------------------------

def test_the_mixture_scores_a_match_higher_the_more_cards_were_available():
    """The property the flat weight lacks, and the reason it exists.

    Naming the agreed card out of five candidates is stronger evidence of an
    agreement than naming it out of two, because the two-card coincidence is
    likely anyway. The flat weight scores both at `beta`."""
    from fish4.convention import mixture_logp
    q = 0.6
    gaps = [mixture_logp(k, True, q) - mixture_logp(k, False, q)
            for k in range(1, 7)]
    assert gaps == sorted(gaps), gaps
    assert gaps[-1] > gaps[0]


def test_a_non_match_is_not_uninformative_under_the_mixture():
    from fish4.convention import mixture_logp
    q = 0.6
    xs = [mixture_logp(k, False, q) for k in range(1, 7)]
    assert len(set(xs)) == len(xs)
    # fewer legal cards -> any particular one is likelier
    assert xs == sorted(xs, reverse=True)


def test_the_mixture_agrees_with_a_direct_probability():
    import math

    from fish4.convention import mixture_logp
    for q in (0.2, 0.5, 0.9):
        for k in (1, 3, 6):
            assert mixture_logp(k, True, q) == pytest.approx(
                math.log(q + (1 - q) / k))
            assert mixture_logp(k, False, q) == pytest.approx(
                math.log((1 - q) / k))


def test_q_zero_is_bit_identical_to_the_incumbent():
    for bel, obs, step in _positions(limit=6):
        a = _marginals(bel, obs, 4242 + step)
        b = _marginals(bel, obs, 4242 + step, convention_q=0.0)
        assert (a == b).all()


def test_the_mixture_is_live_and_is_not_the_flat_weight():
    """Two assertions in one place because they fail together in the mode that
    matters: a term that is wired but unreachable, and a term that is reachable
    but numerically identical to the one it replaces."""
    moved = differs = 0
    positions = _positions(limit=10)
    for bel, obs, step in positions:
        base = _marginals(bel, obs, 4242 + step)
        mix = _marginals(bel, obs, 4242 + step, convention_q=0.6)
        flat = _marginals(bel, obs, 4242 + step, convention_beta=BETA)
        if any(abs(base[c][p] - mix[c][p]) > 1e-9
               for c in range(54) for p in range(NUM_PLAYERS)):
            moved += 1
        if any(abs(flat[c][p] - mix[c][p]) > 1e-9
               for c in range(54) for p in range(NUM_PLAYERS)):
            differs += 1
    assert moved >= 5, f"mixture moved only {moved}/{len(positions)}"
    assert differs >= 5, f"mixture matched the flat weight on {differs}"


def test_the_mixture_batch_and_scalar_paths_agree():
    """Same oracle discipline as the flat weight: the slow obvious form guards
    the fast one."""
    import math

    from fish4.convention import encoded_position_table
    from fish4.oppmodel import build as build_opponent

    table = encoded_position_table()
    q, checked = 0.6, 0
    for bel, obs, step in _positions(limit=6):
        free = [c for c in range(54) if bel.candidates[c].bit_count() > 1]
        om, _ = build_opponent(bel, obs, V06_DEPLOYED[1]["opponent_gamma"],
                               convention_q=q, order=free)
        if om is None or not om.convention:
            continue
        post = Posterior(bel, random.Random(77 + step),
                         n_draws=V06_DEPLOYED[1]["n_draws"], n_worlds=24,
                         obs=obs, gamma=V06_DEPLOYED[1]["opponent_gamma"],
                         convention_q=q)
        worlds = post.worlds()
        for w in worlds[:12]:
            deal = {}
            for c in free:
                for p in range(NUM_PLAYERS):
                    if w[p] >> c & 1:
                        deal[c] = p
                        break
            slow = om.log_convention(deal)
            fast = 0.0
            for (asker, hs, card, const_mask, free_cards,
                 _g, _gc, _gf, _t) in om.convention:
                lo = hs * 6
                held = (const_mask >> lo) & 0x3F
                for c in free_cards:
                    if deal.get(c) == asker:
                        held |= 1 << (c - lo)
                k = 6 - bin(held).count("1")
                if k > 0:
                    pr = (q if table[held] == card - lo else 0.0) \
                        + (1.0 - q) / k
                    fast += math.log(pr)
            assert abs(slow - fast) < 1e-9
            checked += 1
    assert checked > 0


# --------------------------------------------------------------------------
# aiming the channel
# --------------------------------------------------------------------------

def test_the_aimed_table_is_the_unaimed_one_at_the_unaimed_payload():
    """The two code books share a mechanism and differ only in what they carry,
    so the aimed table must reproduce the unaimed one when handed the unaimed
    payload. If it does not, the two decoders differ for a reason nobody chose.
    """
    from fish4.convention import aimed_position_table, encoded_position_table
    flat, aimed = encoded_position_table(), aimed_position_table()
    for mask in range(64):
        held = bin(mask).count("1")
        k = 6 - held
        if k == 0:
            assert set(aimed[mask]) == {-1}
            continue
        assert aimed[mask][(held - 1) % 7] == flat[mask] or held == 0
        # every payload lands on a card the seat does NOT hold
        for pl in range(7):
            assert not (mask >> aimed[mask][pl] & 1)


def test_the_aimed_book_uses_the_full_width_of_the_channel():
    """A code book that mapped every payload to the same card would transmit
    nothing. With k legal cards it must reach all k of them."""
    from fish4.convention import aimed_position_table
    aimed = aimed_position_table()
    for mask in range(63):
        k = 6 - bin(mask).count("1")
        assert len(set(aimed[mask][:7])) == min(k, 7)


def test_aim_is_inert_without_a_decoder_weight():
    """Aiming changes WHAT is said, not WHETHER anything is. With both weights
    at zero the engine must still be bit-identical to the champion."""
    for bel, obs, step in _positions(limit=6):
        a = _marginals(bel, obs, 4242 + step)
        b = _marginals(bel, obs, 4242 + step, convention_aim=True)
        assert (a == b).all()


def test_aiming_changes_the_posterior_it_produces():
    """The regression test for the third code book. Same weight, same
    positions, different target: if these agree, the aim flag is not reaching
    the decoder."""
    differs = 0
    positions = _positions(limit=10)
    for bel, obs, step in positions:
        plain = _marginals(bel, obs, 4242 + step, convention_q=0.6)
        aimed = _marginals(bel, obs, 4242 + step, convention_q=0.6,
                           convention_aim=True)
        if any(abs(plain[c][p] - aimed[c][p]) > 1e-9
               for c in range(54) for p in range(NUM_PLAYERS)):
            differs += 1
    assert differs >= 5, f"aim changed only {differs}/{len(positions)}"


def test_the_aimed_batch_and_scalar_paths_agree():
    import math

    from fish4.convention import (aimed_position_table, encoded_position,
                                  legal_cards)
    from fish4.oppmodel import build as build_opponent

    table = aimed_position_table()
    q, checked = 0.6, 0
    for bel, obs, step in _positions(limit=6):
        free = [c for c in range(54) if bel.candidates[c].bit_count() > 1]
        om, _ = build_opponent(bel, obs, V06_DEPLOYED[1]["opponent_gamma"],
                               convention_q=q, convention_aim=True, order=free)
        if om is None or not om.convention:
            continue
        post = Posterior(bel, random.Random(77 + step),
                         n_draws=V06_DEPLOYED[1]["n_draws"], n_worlds=24,
                         obs=obs, gamma=V06_DEPLOYED[1]["opponent_gamma"],
                         convention_q=q, convention_aim=True)
        for w in post.worlds()[:12]:
            deal = {}
            for c in free:
                for p in range(NUM_PLAYERS):
                    if w[p] >> c & 1:
                        deal[c] = p
                        break
            slow = om.log_convention(deal)
            fast = 0.0
            for (asker, hs, card, const_mask, free_cards,
                 g_hs, g_const, g_free, _t) in om.convention:
                lo, glo = hs * 6, (g_hs or 0) * 6
                held = (const_mask >> lo) & 0x3F
                for c in free_cards:
                    if deal.get(c) == asker:
                        held |= 1 << (c - lo)
                gheld = (g_const >> glo) & 0x3F
                for c in g_free:
                    if deal.get(c) == asker:
                        gheld |= 1 << (c - glo)
                k = 6 - bin(held).count("1")
                if k > 0:
                    match = table[held][bin(gheld).count("1")] == card - lo
                    fast += math.log((q if match else 0.0) + (1.0 - q) / k)
            assert abs(slow - fast) < 1e-9
            checked += 1
    assert checked > 0


def test_the_aimed_target_is_reconstructed_as_of_the_ask_not_the_present():
    """Sender and receiver must name the same half-suit without communicating,
    and the sender chose it from the public record AS IT WAS. The record moves,
    so a target derived at decode time would be a different half-suit and the
    whole message would be misaddressed. Assert the snapshot is not simply the
    final state."""
    from fish.cards import half_suit_cards, num_half_suits
    from fish4.oppmodel import build as build_opponent

    n_hs = num_half_suits(RULES.variant)
    drifted = seen = 0
    for bel, obs, step in _positions(n_games=3, stride=3, limit=25):
        free = [c for c in range(54) if bel.candidates[c].bit_count() > 1]
        om, _ = build_opponent(bel, obs, V06_DEPLOYED[1]["opponent_gamma"],
                               convention_q=0.6, convention_aim=True,
                               order=free)
        if om is None or not om.convention:
            continue
        unloc = [sum(1 for c in half_suit_cards(h)
                     if bel.public_loc[c] is None) for h in range(n_hs)]
        now = max(range(n_hs), key=lambda h: (unloc[h], -h))
        for row in om.convention:
            seen += 1
            if row[5] is not None and row[5] != now:
                drifted += 1
    assert seen > 0
    assert drifted > 0, ("every recorded target equals the one derived from "
                         "the CURRENT record -- the snapshot is not being taken")
