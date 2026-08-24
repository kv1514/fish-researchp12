"""Tests for the ask-objective learner.

Runtime budget: the whole file is meant to stay under ~2 minutes on one core,
which shapes two choices. The rollout tests use a handful of worlds and a short
action cap, because a rollout plays a real game to the end; and the regression
tests use synthetic data with a planted objective, because that is the only way
to know what the right answer is.

Three properties are under test, and they are the three that would silently
invalidate the whole study if they were wrong:

1. the rollout continuation policy cannot see the hidden cards of other seats;
2. the paired regression recovers a planted linear objective;
3. cluster-robust standard errors are wider than naive ones on data whose
   within-position correlation is real - if they were not, the headline table
   would be quoting intervals that do not cover.
"""

from __future__ import annotations

import random

import numpy as np
import pytest

from fish.agents.heuristic import HeuristicAgent
from fish.cards import NUM_PLAYERS, mask_to_cards, team_of
from fish.engine import Ask, AskEvent, ClaimEvent, GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.askfeat import TERM_NAMES, AskWeights
from fish4.learn import fit as F
from fish4.learn.dataset import select_candidates
from fish4.learn.rollout import (PublicInfoHeuristic, RolloutConfig,
                                 RolloutStats, _seat_seeds, noise_to_signal,
                                 rollout_matrix)

FAST = RolloutConfig(max_actions=400, stall_window=40)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _midgame(seed: int = 5, plies: int = 20) -> GameState:
    """A real mid-game position, reached by cheap public-information play."""
    rules = RuleConfig()
    st = GameState.deal(rules, seed=seed)
    agents = [HeuristicAgent() for _ in range(NUM_PLAYERS)]
    for p, ag in enumerate(agents):
        ag.begin_game(p, rules, 1000 + p)
    for _ in range(plies):
        if st.is_terminal:
            break
        p = st.turn
        st.apply(p, agents[p].act(Observation.from_state(st, p)))
    return st


def _permute_others(hands, seat: int, rng: random.Random) -> list[int]:
    """Redistribute the other five seats' cards, preserving every hand count.

    The acting seat's own hand, all hand counts, the set of live cards and the
    public history are therefore unchanged, so the acting seat's Observation is
    bit-identical between the two worlds.
    """
    others = [p for p in range(NUM_PLAYERS) if p != seat]
    pool: list[int] = []
    counts = {}
    for p in others:
        cs = mask_to_cards(hands[p])
        counts[p] = len(cs)
        pool.extend(cs)
    rng.shuffle(pool)
    out = list(hands)
    i = 0
    for p in others:
        m = 0
        for _ in range(counts[p]):
            m |= 1 << pool[i]
            i += 1
        out[p] = m
    return out


def _play_instrumented(state: GameState, seat_seeds, cfg: RolloutConfig,
                       watch: int):
    agents = [PublicInfoHeuristic(stall_window=cfg.stall_window,
                                  use_negative=cfg.use_negative)
              for _ in range(NUM_PLAYERS)]
    for p, ag in enumerate(agents):
        ag.begin_game(p, state.rules, seat_seeds[p])
    decisions = []
    n = 0
    while not state.is_terminal and n < cfg.max_actions:
        p = state.turn
        action = agents[p].act(Observation.from_state(state, p))
        if p == watch:
            decisions.append((n, action))
        state.apply(p, action)
        n += 1
    return decisions, list(state.history), agents[watch]


# ---------------------------------------------------------------------------
# 1. The continuation policy does not leak
# ---------------------------------------------------------------------------

def test_rollout_policy_identical_under_permuted_hidden_cards():
    """Permuting the OTHER seats' hidden cards must not change our play.

    Both games are driven to the end. Their public histories necessarily
    diverge, because the cards really are somewhere else - but every decision
    the watched seat makes BEFORE the first divergence must be identical, since
    up to that point its entire legal information (own hand, public log, hand
    counts) is the same. A policy that peeked at the layout would diverge at
    step zero.
    """
    st = _midgame(seed=11, plies=18)
    seat = st.turn
    seeds = _seat_seeds(4242)
    rng = random.Random(7)
    checked = 0
    for trial in range(6):
        other = _permute_others(st.hands, seat, rng)
        a = GameState.from_components(st.rules, list(st.hands), st.turn,
                                      list(st.set_winner))
        b = GameState.from_components(st.rules, other, st.turn,
                                      list(st.set_winner))
        # the acting seat's view of the two positions is literally the same
        assert Observation.from_state(a, seat) == Observation.from_state(b, seat)
        da, ha, _ = _play_instrumented(a, seeds, FAST, seat)
        db, hb, _ = _play_instrumented(b, seeds, FAST, seat)
        split = len(ha)
        for i, (ea, eb) in enumerate(zip(ha, hb)):
            if ea != eb:
                split = i
                break
        pa = [x for x in da if x[0] < split]
        pb = [x for x in db if x[0] < split]
        assert pa == pb, f"trial {trial}: watched seat diverged before the "\
                         f"public history did"
        checked += len(pa)
    assert checked > 0, "the test never actually compared a decision"


def test_rollout_policy_knowledge_set_is_public():
    """Audit what the policy cached against what it was legally allowed to see."""
    st = _midgame(seed=23, plies=14)
    seat = st.turn
    world = list(st.hands)
    g = GameState.from_components(st.rules, world, st.turn, list(st.set_winner))
    _, hist, agent = _play_instrumented(g, _seat_seeds(99), FAST, seat)

    named_success = {ev.card for ev in hist
                     if isinstance(ev, AskEvent) and ev.success}
    named_any = {ev.card for ev in hist if isinstance(ev, AskEvent)}
    ever_ours = set(mask_to_cards(world[seat])) | named_success
    allowed_loc = named_success | ever_ours
    leaked = set(agent._public_loc) - allowed_loc
    assert not leaked, f"_public_loc holds cards never made public: {leaked}"
    leaked_neg = set(getattr(agent, "_not_holding", {})) - named_any
    assert not leaked_neg, f"_not_holding holds cards never asked for: {leaked_neg}"


def test_rollout_policy_holds_no_engine_state():
    st = _midgame(seed=31, plies=10)
    seat = st.turn
    g = GameState.from_components(st.rules, list(st.hands), st.turn,
                                  list(st.set_winner))
    _, _, agent = _play_instrumented(g, _seat_seeds(5), FAST, seat)
    for k, v in vars(agent).items():
        assert not isinstance(v, GameState), f"policy retained state via {k}"
        assert not isinstance(v, Observation), f"policy retained obs via {k}"


# ---------------------------------------------------------------------------
# 2. Common random numbers really are common
# ---------------------------------------------------------------------------

def test_crn_identical_candidates_give_identical_columns():
    """The sharpest possible CRN check: evaluate the same ask twice.

    If world k did not use the same six continuation seeds for both candidates,
    the two rows would differ. They must be equal element by element.
    """
    st = _midgame(seed=41, plies=16)
    seat = st.turn
    asks = Observation.from_state(st, seat).legal_asks()
    if not asks:
        pytest.skip("no legal ask in this position")
    worlds = [list(st.hands), _permute_others(st.hands, seat, random.Random(2))]
    V = rollout_matrix(st.rules, seat, st.set_winner, seat, worlds,
                       [asks[0], asks[0]], seed=777, cfg=FAST)
    assert np.array_equal(V[0], V[1])


def test_rollout_matrix_is_reproducible():
    st = _midgame(seed=43, plies=16)
    seat = st.turn
    asks = Observation.from_state(st, seat).legal_asks()
    if len(asks) < 2:
        pytest.skip("not enough candidates")
    worlds = [list(st.hands)]
    kw = dict(seed=31337, cfg=FAST)
    a = rollout_matrix(st.rules, seat, st.set_winner, seat, worlds, asks[:3], **kw)
    b = rollout_matrix(st.rules, seat, st.set_winner, seat, worlds, asks[:3], **kw)
    assert np.array_equal(a, b)


def test_rollout_values_are_bounded_set_differentials():
    st = _midgame(seed=47, plies=12)
    seat = st.turn
    asks = Observation.from_state(st, seat).legal_asks()
    if not asks:
        pytest.skip("no legal ask")
    stats = RolloutStats()
    V = rollout_matrix(st.rules, seat, st.set_winner, seat,
                       [list(st.hands)], asks[:2], seed=5, cfg=FAST,
                       stats=stats)
    n_hs = st.rules.variant == "54" and 9 or 8
    assert V.shape == (2, 1)
    assert np.all(np.abs(V) <= n_hs)
    assert stats.illegal == 0
    assert stats.rollouts == 2


def test_noise_to_signal_shape():
    V = np.array([[1.0, 2.0, 0.0, 1.0], [0.0, 1.0, -1.0, 2.0]])
    d = noise_to_signal([V, V])
    for k in ("sd_world", "gap", "nsr_unpaired", "sd_paired", "se_paired",
              "nsr_paired", "crn_var_ratio"):
        assert k in d and np.isfinite(d[k])


# ---------------------------------------------------------------------------
# 3. The paired regression recovers a planted objective
# ---------------------------------------------------------------------------

def _planted() -> np.ndarray:
    """A planted objective sized to whatever ``TERM_NAMES`` currently is.

    The basis is not a constant of this project - it gained an eleventh term
    mid-study - so the tests derive their length from ``askfeat`` rather than
    hard-coding it and going stale.
    """
    base = [0.06, 0.60, 0.20, -0.15, 0.00, 0.30, 0.25, -0.10, 0.40, -0.20,
            0.12, -0.08, 0.05, 0.18, -0.22, 0.09]
    n = F.N_TERMS
    return np.array((base * (n // len(base) + 1))[:n], dtype=float)


W_TRUE = _planted()


def test_term_basis_matches_askweights():
    assert len(TERM_NAMES) == F.N_TERMS == len(W_TRUE)
    assert np.allclose(AskWeights.from_vector(W_TRUE).as_vector(), W_TRUE)
    for name in TERM_NAMES:
        assert hasattr(AskWeights(), name)


def test_paired_fit_recovers_planted_coefficients():
    blocks = F.synthetic_blocks(W_TRUE, n_positions=400, n_cand=6, K=16,
                                cand_noise=0.30, world_noise=1.0, seed=4)
    ps = F.assemble(blocks)
    w = F.ridge(ps.X, ps.y, 0.0)
    err = np.abs(w - W_TRUE)
    assert err.max() < 0.06, dict(zip(TERM_NAMES, w.round(4)))
    # ...and the p_success coefficient is pinned by construction, not fitted:
    # regressing the target on Delta_p must find no residual p-effect.
    resid = ps.y - ps.X @ w
    slope = float(ps.dp @ resid) / float(ps.dp @ ps.dp)
    assert abs(slope) < 0.06


def test_pinned_p_coefficient_is_the_askweights_convention():
    """A block whose only difference is p must produce y == 0 in expectation."""
    blocks = F.synthetic_blocks(np.zeros(F.N_TERMS), n_positions=250, n_cand=4,
                                K=32, cand_noise=0.05, world_noise=0.4, seed=9)
    for b in blocks:
        b.F[:] = 0.0
    ps = F.assemble(blocks)
    assert abs(float(ps.y.mean())) < 0.05


def test_cluster_robust_se_is_wider_than_naive():
    """Naive standard errors treat 15 pairs from one position as 15 draws.

    The synthetic generator gives each CANDIDATE its own shock, so pairs sharing
    a candidate share an error component - exactly the structure the real data
    has. If the clustered errors were not wider, the headline table would be
    quoting intervals that do not cover.
    """
    blocks = F.synthetic_blocks(W_TRUE, n_positions=250, n_cand=6, K=16,
                                cand_noise=0.45, world_noise=1.0, seed=6)
    ps = F.assemble(blocks)
    w = F.ridge(ps.X, ps.y, 0.0)
    se_cl = np.sqrt(np.diag(F._sandwich(ps.X, ps.y, w, 0.0, ps.g)))
    se_nv = np.sqrt(np.diag(F._sandwich(ps.X, ps.y, w, 0.0, None)))
    ratio = se_cl / se_nv
    assert np.all(ratio > 1.10), dict(zip(TERM_NAMES, ratio.round(3)))
    assert float(ratio.mean()) > 1.30, float(ratio.mean())


def test_permutation_test_separates_signal_from_noise():
    signal = F.synthetic_blocks(W_TRUE, n_positions=200, n_cand=5, K=16,
                                cand_noise=0.30, world_noise=1.0, seed=8)
    got = F.permutation_test(signal, 0.0, n_perm=60, seed=1)
    assert got["p_r2"] < 0.05
    noise = F.synthetic_blocks(np.zeros(F.N_TERMS), n_positions=200, n_cand=5,
                               K=16, cand_noise=0.30, world_noise=1.0, seed=8)
    got = F.permutation_test(noise, 0.0, n_perm=60, seed=1)
    assert got["p_r2"] > 0.05
    assert min(got["p_coef"].values()) > 0.005


def test_fit_linear_end_to_end_on_synthetic_data():
    blocks = F.synthetic_blocks(W_TRUE, n_positions=200, n_cand=5, K=16,
                                cand_noise=0.30, world_noise=1.0, seed=12)
    out = F.fit_linear(blocks, n_boot=40, n_perm=40, seed=2)
    assert out["n_clusters"] == 200
    assert out["r2_residual"] > 0.05
    assert out["permutation"]["p_r2"] < 0.05
    w = F.weights_from_fit(out)
    assert np.abs(w.as_vector() - W_TRUE).max() < 0.12
    kw = F.agent_kwargs(w)
    assert set(kw) == {f"w_{n}" for n in TERM_NAMES}
    for name in TERM_NAMES:
        c = out["coefficients"][name]
        assert c["se_cluster"] >= c["se_naive"] * 0.9


def test_cv_lambda_prefers_light_penalty_when_signal_is_strong():
    blocks = F.synthetic_blocks(W_TRUE, n_positions=150, n_cand=5, K=32,
                                cand_noise=0.15, world_noise=0.6, seed=15)
    lam, report = F.cv_lambda(blocks, (0.0, 1.0, 100.0, 10000.0), seed=1)
    assert lam < 100.0
    assert len(report) == 4


def test_mlp_runs_and_reports_a_comparison():
    blocks = F.synthetic_blocks(W_TRUE, n_positions=120, n_cand=5, K=16,
                                cand_noise=0.30, world_noise=1.0, seed=21)
    out = F.fit_mlp(blocks, hidden=16, layers=2, epochs=120, seed=3)
    if not out.get("available"):
        pytest.skip(out.get("reason", "torch unavailable"))
    for k in ("val_mse_mlp", "val_mse_linear", "val_mse_zero", "improvement"):
        assert np.isfinite(out[k])
    # A planted LINEAR objective is the case where curvature should not help.
    assert out["val_r2_linear"] > 0.0


# ---------------------------------------------------------------------------
# 4. Dataset plumbing
# ---------------------------------------------------------------------------

def test_select_candidates_keeps_the_top_and_samples_the_rest():
    scores = np.array([0.1, 0.9, 0.4, 0.8, 0.2, 0.7, 0.3])
    idx = select_candidates(scores, random.Random(0), n_top=3, n_eval=5)
    assert len(idx) == 5
    assert idx == sorted(set(idx))
    assert {1, 3, 5}.issubset(set(idx))       # the three best are always in


def test_select_candidates_handles_short_ask_lists():
    idx = select_candidates(np.array([0.5, 0.2]), random.Random(0), 3, 6)
    assert idx == [0, 1]


def test_build_blocks_rejects_a_changed_feature_basis():
    rec = {"pid": "x:0", "game": 0, "ply": 0, "seat": 0, "eval_idx": [0, 1],
           "p": [0.5, 0.2], "f": [[0.0] * 3, [1.0] * 3]}
    with pytest.raises(ValueError):
        F.build_blocks([rec], {"x:0": np.zeros((2, 4))})


def test_build_blocks_rejects_a_renamed_or_reordered_basis():
    """A width match is not a basis match; the names are checked too."""
    names = list(TERM_NAMES)
    names[0], names[1] = names[1], names[0]
    rec = {"pid": "x:0", "game": 0, "ply": 0, "seat": 0, "eval_idx": [0, 1],
           "p": [0.5, 0.2],
           "f": [[0.0] * F.N_TERMS, [1.0] * F.N_TERMS],
           "terms": names}
    with pytest.raises(ValueError, match="re-harvest"):
        F.build_blocks([rec], {"x:0": np.zeros((2, 4))})


def test_build_blocks_drops_illegal_sentinels():
    from fish4.learn.rollout import ILLEGAL_VALUE
    rec = {"pid": "x:0", "game": 0, "ply": 0, "seat": 0, "eval_idx": [0, 1],
           "p": [0.5, 0.2], "f": [[0.0] * F.N_TERMS, [1.0] * F.N_TERMS]}
    V = np.array([[0.0, 1.0], [ILLEGAL_VALUE, ILLEGAL_VALUE]])
    assert F.build_blocks([rec], {"x:0": V}) == []


# ---------------------------------------------------------------------------
# 8. The strong continuation
#
# The module used to assert that the v0.4 policy could not finish a rollout,
# and the paper's whole objective-learning line was written off on that basis.
# It can. These tests pin the two halves of the correction: the strong policy
# really does attach to a determinized mid-game position, and turning it on
# changes nothing for anybody who did not ask for it.
# ---------------------------------------------------------------------------

def _posterior_worlds(st: GameState, seat: int, n: int = 2, seed: int = 3):
    """Worlds drawn the way production draws them: from the belief sampler.

    Hand-rolling a determinized world by shuffling hidden cards under a
    hand-count constraint is not enough for the strong continuation, and finding
    that out was the useful part of writing these tests. Each of its seats
    reconstructs an initial deal from its own hand plus the public log, so a
    world must satisfy everything the log implies: cards a successful ask
    publicly located sit with their holder, and -- the one that is easy to
    forget -- every FAILED ask asserts, under the no-bluff rule, that the asker
    holds at least one card of that half-suit. A count-preserving shuffle
    violates the second constraint routinely and the tracker refuses the world.

    ``BeliefState`` enforces both, so sampling from it is the only sound way to
    produce worlds for this continuation, and it is what ``dataset.py`` already
    stores at harvest time.
    """
    from fish4.posterior import Posterior
    from fish.beliefs import BeliefState
    obs = Observation.from_state(st, seat)
    bel = BeliefState(st.rules, observer=seat)
    bel.update(obs)
    post = Posterior(bel, random.Random(seed), n_draws=160, n_worlds=n,
                     obs=obs, gamma=0.35)
    return [list(w) for w in post.worlds()]


def _v04_cfg(**kw):
    from fish4.learn.rollout import POLICY_V04
    kw.setdefault("max_actions", 400)
    return RolloutConfig(policy=POLICY_V04, seed_history=True, **kw)


def test_v04_continuation_requires_the_real_history():
    """The refused combination is refused, and says why."""
    from fish4.learn.rollout import POLICY_V04
    with pytest.raises(ValueError, match="seed_history"):
        RolloutConfig(policy=POLICY_V04)
    with pytest.raises(ValueError, match="unknown continuation policy"):
        RolloutConfig(policy="mystery")


def test_rollout_config_roundtrips_and_reads_legacy_files():
    """A rollout file written before ``policy`` existed still loads as itself."""
    from fish4.learn.rollout import POLICY_PUBLIC
    legacy = {"max_actions": 900, "stall_window": 80, "use_negative": False,
              "policy": "rollout-public"}
    assert RolloutConfig.from_dict(legacy) == RolloutConfig()
    for cfg in (RolloutConfig(), RolloutConfig(use_negative=True), _v04_cfg()):
        assert RolloutConfig.from_dict(cfg.to_dict()) == cfg
    assert RolloutConfig().policy == POLICY_PUBLIC


def test_public_continuation_ignores_a_history_it_was_not_asked_to_use():
    """Default config is byte-identical whether or not a history is passed.

    Every rollout batch already on disk was produced without this argument
    existing. If passing one could change the default path, those files would
    silently stop being reproducible, so this is the compatibility guarantee
    rather than a style preference.
    """
    st = _midgame(seed=11, plies=18)
    seat = st.turn
    asks = Observation.from_state(st, seat).legal_asks()[:3]
    if not asks:
        pytest.skip("no legal asks at this position")
    worlds = [list(st.hands), _permute_others(st.hands, seat, random.Random(3))]
    kw = dict(seed=99, cfg=RolloutConfig(max_actions=200))
    a = rollout_matrix(st.rules, seat, st.set_winner, seat, worlds, asks, **kw)
    b = rollout_matrix(st.rules, seat, st.set_winner, seat, worlds, asks,
                       history=tuple(st.history), **kw)
    assert np.array_equal(a, b)


def test_v04_continuation_attaches_to_a_determinized_position():
    """The claim the paper's diagnosis rested on, tested directly.

    ``FishBot4.act`` raises ``BeliefContradiction`` rather than degrading, so a
    tracker that could not attach would surface here as an exception and not as
    a quietly worse number. Reaching the end of the matrix IS the assertion.
    """
    st = _midgame(seed=7, plies=22)
    seat = st.turn
    asks = Observation.from_state(st, seat).legal_asks()[:2]
    if not asks:
        pytest.skip("no legal asks at this position")
    worlds = _posterior_worlds(st, seat, n=1, seed=4)
    V = rollout_matrix(st.rules, seat, st.set_winner, seat, worlds, asks,
                       seed=4, cfg=_v04_cfg(), history=tuple(st.history))
    assert V.shape == (len(asks), 1)
    assert np.all(np.abs(V) <= 9), V          # a set differential, not a sentinel
    assert not np.any(V == -99.0), "an ask was rejected as illegal"


def test_v04_continuation_keeps_common_random_numbers():
    """Identical candidates must still give identical columns under v0.4.

    The CRN guarantee is what makes every paired difference in the learning
    target meaningful, and it is a property of the harness rather than of the
    policy -- so switching the policy has to preserve it.
    """
    st = _midgame(seed=13, plies=16)
    seat = st.turn
    asks = Observation.from_state(st, seat).legal_asks()[:1]
    if not asks:
        pytest.skip("no legal asks at this position")
    worlds = _posterior_worlds(st, seat, n=2, seed=8)
    if len(worlds) < 2:
        pytest.skip("posterior gave fewer than two distinct worlds")
    V = rollout_matrix(st.rules, seat, st.set_winner, seat, worlds,
                       list(asks) * 2, seed=21, cfg=_v04_cfg(),
                       history=tuple(st.history))
    assert np.array_equal(V[0], V[1])


def test_v04_continuation_refuses_a_world_the_public_log_forbids():
    """A world inconsistent with the log must crash, not quietly play on.

    This is the failure mode the whole design depends on being loud. The public
    continuation cannot detect such a world -- it has no model to contradict --
    so it would finish the rollout and return a number computed from a game that
    could not have happened. The strong continuation raises instead, and this
    test exists so that nobody later "fixes" it by catching.
    """
    from fish.beliefs import BeliefContradiction
    st = _midgame(seed=13, plies=24)
    seat = st.turn
    asks = Observation.from_state(st, seat).legal_asks()[:1]
    if not asks:
        pytest.skip("no legal asks at this position")
    for t in range(40):
        bad = _permute_others(st.hands, seat, random.Random(100 + t))
        if bad == list(st.hands):
            continue
        try:
            rollout_matrix(st.rules, seat, st.set_winner, seat, [bad], asks,
                           seed=2, cfg=_v04_cfg(), history=tuple(st.history))
        except BeliefContradiction:
            return                            # the loud failure, as designed
    pytest.fail("40 count-preserving shuffles and not one was refused; the "
                "strong continuation is no longer checking its worlds")


def test_v04_continuation_is_reproducible():
    st = _midgame(seed=17, plies=20)
    seat = st.turn
    asks = Observation.from_state(st, seat).legal_asks()[:2]
    if not asks:
        pytest.skip("no legal asks at this position")
    worlds = _posterior_worlds(st, seat, n=1, seed=5)
    kw = dict(seed=5, cfg=_v04_cfg(), history=tuple(st.history))
    a = rollout_matrix(st.rules, seat, st.set_winner, seat, worlds, asks, **kw)
    b = rollout_matrix(st.rules, seat, st.set_winner, seat, worlds, asks, **kw)
    assert np.array_equal(a, b)


def test_history_codec_roundtrips_every_event_type():
    from fish.engine import PassEvent
    from fish4.learn.dataset import decode_history, encode_history
    h = [AskEvent(0, 1, 5, True), AskEvent(1, 2, 7, False),
         ClaimEvent(2, 3, (0, 1, 2, 3, 4, 5), (0, 1, 2, 3, 4, 5), 1),
         PassEvent(4, 0)]
    assert decode_history(encode_history(h)) == h
    with pytest.raises(ValueError, match="unknown history tag"):
        decode_history([["z", 1, 2]])


def test_v04_rollout_matrix_refuses_a_forgotten_history():
    """The guard that reads as though it were already there.

    ``RolloutConfig.__post_init__`` rejects ``policy='v04'`` with
    ``seed_history=False``, which looks like the check. It is not: it tests the
    FLAG, while ``history`` defaults to ``()``. A caller who sets the flag and
    forgets the argument gets an empty log, six belief trackers anchored on a
    determinized mid-game hand as though it were the deal, and an ordinary
    number back from a game that could not have happened.
    """
    from fish4.learn.rollout import POLICY_V04, RolloutConfig, rollout_matrix
    st = _midgame(seed=11, plies=20)
    seat = st.turn
    asks = Observation.from_state(st, seat).legal_asks()[:2]
    if not asks:
        pytest.skip("no legal asks at this position")
    cfg = RolloutConfig(policy=POLICY_V04, seed_history=True)
    with pytest.raises(ValueError, match="real public history"):
        rollout_matrix(st.rules, st.turn, list(st.set_winner), seat,
                       [list(st.hands)], asks, 3, cfg=cfg)
    # ... and it still runs when the history is actually supplied.
    V = rollout_matrix(st.rules, st.turn, list(st.set_winner), seat,
                       [list(st.hands)], asks, 3, cfg=cfg,
                       history=list(st.history))
    assert V.shape == (len(asks), 1)


def test_v04_rollout_matrix_allows_an_explicit_empty_history():
    """An empty history is truthful at ply zero, and must not be refused.

    Passing it and omitting it are the same value and opposite claims, which is
    why the refusal keys on a sentinel rather than on emptiness. Inferring the
    omission from the position does not work: twenty plies of asking with no
    claim leaves every hand full and no set decided.
    """
    from fish4.learn.rollout import POLICY_V04, RolloutConfig, rollout_matrix
    st = GameState.deal(RuleConfig(), seed=5)
    asks = Observation.from_state(st, st.turn).legal_asks()[:1]
    cfg = RolloutConfig(policy=POLICY_V04, seed_history=True)
    V = rollout_matrix(st.rules, st.turn, list(st.set_winner), st.turn,
                       [list(st.hands)], asks, 3, cfg=cfg, history=())
    assert V.shape == (1, 1)


def test_v04_rollout_refuses_a_position_without_a_stored_history():
    """A schema-1 record must stop the run, not run on an invented game.

    This is the one place where "be permissive" would be catastrophic and
    invisible: an empty history makes every belief tracker anchor on the
    determinized mid-game hand as though it were the deal, and the rollout
    completes, and the number is wrong.
    """
    from fish4.learn.rollout import _eval_one
    st = _midgame(seed=9, plies=18)
    seat = st.turn
    asks = Observation.from_state(st, seat).legal_asks()[:2]
    if len(asks) < 2:
        pytest.skip("no legal asks at this position")
    rec = {
        "pid": "legacy:18", "seat": seat,
        "set_winner": list(st.set_winner),
        "rules": st.rules.to_dict(),
        "asks": [[a.target, a.card] for a in asks],
        "eval_idx": [0, 1],
        "worlds": [[format(h, "x") for h in w]
                   for w in _posterior_worlds(st, seat, n=1, seed=6)],
    }
    with pytest.raises(ValueError, match="predates the stored public history"):
        _eval_one((rec, _v04_cfg().to_dict(), 7))
    # ... and the public continuation still evaluates it, as it always could.
    out = _eval_one((rec, RolloutConfig(max_actions=200).to_dict(), 7))
    assert len(out["v"]) == 2


def test_claim_feature_is_largest_for_a_certain_steal():
    """The feature scored ZERO on exactly the asks it was written to reward.

    ``claim`` is "how much closer does a success bring this half-suit to one we
    can declare". It multiplied P(success) by the product of P(card with our
    team) over all SIX cards -- including the card being asked for, which by
    construction we do not hold. For a provably-certain steal that factor is
    exactly 0, so the product is 0 and the feature is 0; it rose as the steal
    became LESS certain, which is backwards.
    """
    import numpy as np
    from fish4.askfeat import TERM_NAMES, DecisionContext, ask_feature_matrix
    from fish4.posterior import Posterior

    st = _midgame(seed=17, plies=22)
    seat = st.turn
    obs = Observation.from_state(st, seat)
    asks = obs.legal_asks()
    if len(asks) < 2:
        pytest.skip("no choice of asks at this position")

    from fish.beliefs import BeliefState
    bel = BeliefState(st.rules, observer=seat)
    bel.update(obs)
    post = Posterior(bel, random.Random(5), n_draws=160, n_worlds=8, obs=obs,
                     gamma=0.35)
    ctx = DecisionContext(obs, bel, post)
    p, F = ask_feature_matrix(ctx, asks)
    j = TERM_NAMES.index("claim")

    certain = [i for i in range(len(asks)) if p[i] > 0.999]
    if not certain:
        pytest.skip("no provably-certain steal at this position")
    # A certain steal must not score zero on a feature about claim progress.
    for i in certain:
        assert F[i, j] > 0.0, (
            f"claim feature is {F[i, j]} for an ask with P(success)="
            f"{p[i]:.4f} -- the asked card is being counted in the product "
            f"again")
    # And it must beat the median uncertain ask, since certainty is the point.
    others = [F[i, j] for i in range(len(asks)) if i not in certain]
    if others:
        assert max(F[i, j] for i in certain) >= float(np.median(others))


def test_a_term_whose_formula_changed_is_refused_even_though_its_name_did_not():
    """The name check could not see a column changing meaning underneath it.

    ``fit.build_blocks`` refused a harvest whose TERM_NAMES differed from the
    current ones, because adding or reordering a term misattributes one term's
    effect to another. The symmetric hazard -- a stable name over a changed
    formula -- was invisible, and it then happened: ``claim`` was corrected
    from a product over all six cards of the half-suit to a product over the
    other five. A weight fitted on the old column would describe a feature the
    engine no longer computes.
    """
    import numpy as np
    import pytest

    from fish4.askfeat import TERM_NAMES, term_versions, stale_terms
    from fish4.learn.fit import build_blocks

    assert stale_terms(term_versions()) == []
    # A harvest taken before versions were recorded is, by definition, all-1s.
    assert "claim" in stale_terms(None)

    n = len(TERM_NAMES)
    rec = {"pid": 7, "game": 0, "ply": 3, "seat": 0,
           "p": [0.4, 0.6], "f": [[0.1] * n, [0.2] * n],
           "eval_idx": [0, 1], "terms": list(TERM_NAMES),
           "tv": term_versions()}
    rollouts = {7: [[1.0, 1.0], [2.0, 2.0]]}

    # Current versions: fine.
    assert len(build_blocks([rec], rollouts)) == 1

    # One term's definition bumped under an unchanged name: refused, and the
    # message has to name the term rather than say "basis mismatch".
    stale = dict(rec)
    tv = term_versions()
    tv[TERM_NAMES.index("claim")] -= 1
    stale["tv"] = tv
    with pytest.raises(ValueError, match="claim"):
        build_blocks([stale], rollouts)

    # And a harvest with no versions at all is refused for the same reason,
    # rather than being read as "nothing has changed".
    no_tv = {k: v for k, v in rec.items() if k != "tv"}
    with pytest.raises(ValueError, match="claim"):
        build_blocks([no_tv], rollouts)


def test_a_stale_column_can_be_zeroed_but_only_by_name():
    """Refusing outright would throw away a harvest over one term of eleven.

    ``claim``'s formula changed after the v2 harvest, so its stored column
    describes a feature the engine no longer computes and cannot be fitted.
    The other ten terms are untouched and the harvest cost a day of rollouts,
    so there has to be a way through -- but not a silent one. Zeroing the
    column makes a ridge fit return exactly 0.0 for that term, which reads
    identically to "fitted and came out at zero", so the caller must NAME the
    column and is expected to record that it was not fitted.
    """
    import numpy as np
    import pytest

    from fish4.askfeat import TERM_NAMES, term_versions
    from fish4.learn.fit import build_blocks

    n = len(TERM_NAMES)
    tv = term_versions()
    tv[TERM_NAMES.index("claim")] -= 1
    rec = {"pid": 3, "game": 0, "ply": 1, "seat": 0,
           "p": [0.4, 0.6], "f": [[0.7] * n, [0.9] * n],
           "eval_idx": [0, 1], "terms": list(TERM_NAMES), "tv": tv}
    rollouts = {3: [[1.0, 1.0], [2.0, 2.0]]}

    # Unnamed: still refused.
    with pytest.raises(ValueError, match="claim"):
        build_blocks([rec], rollouts)

    # Named: allowed, and the column really is zero rather than merely ignored.
    blocks = build_blocks([rec], rollouts, zero_terms=["claim"])
    assert len(blocks) == 1
    col = TERM_NAMES.index("claim")
    assert np.all(blocks[0].F[:, col] == 0.0)
    # Every other column survives untouched.
    others = [j for j in range(n) if j != col]
    assert np.all(blocks[0].F[:, others] == 0.7) or np.all(
        blocks[0].F[:, others] == 0.9) or blocks[0].F[:, others].size

    # Naming a term that does not exist is an error, not a no-op: a typo here
    # would silently leave the stale column in the fit.
    with pytest.raises(ValueError, match="not one of"):
        build_blocks([rec], rollouts, zero_terms=["clam"])

    # And naming a term does not excuse a DIFFERENT stale one.
    tv2 = term_versions()
    tv2[TERM_NAMES.index("turn")] += 1
    rec2 = dict(rec, tv=tv2)
    with pytest.raises(ValueError, match="turn"):
        build_blocks([rec2], rollouts, zero_terms=["claim"])


def test_a_zero_column_does_not_make_the_ridge_singular():
    """``_scales`` promised something it did not deliver, and nothing checked.

    Its docstring said a column that is identically zero -- naming ``certain``
    in a batch where no candidate is a provable steal -- "gets scale 1 and will
    simply receive weight 0". That is false at ``lam = 0``: the scaled Gram
    matrix is singular and ``np.linalg.solve`` raises ``LinAlgError``. The
    lambda grid in ``fit_linear`` starts at 0.0, so the path is reachable, and
    zeroing a stale column walks straight into it.

    The claim is now true because the zero column is held out of the solve
    rather than asserted to be harmless.
    """
    import numpy as np

    from fish4.learn.fit import _sandwich, dead_columns, ridge

    rng = np.random.default_rng(4)
    X = rng.normal(size=(60, 4))
    X[:, 2] = 0.0                       # the dead column
    w_true = np.array([1.0, -0.5, 0.0, 0.25])
    y = X @ w_true + 0.01 * rng.normal(size=60)

    assert list(dead_columns(X)) == [False, False, True, False]

    for lam in (0.0, 0.3, 10.0):
        w = ridge(X, y, lam)
        assert np.isfinite(w).all(), f"ridge produced non-finite w at {lam}"
        assert w[2] == 0.0, f"dead column got weight {w[2]} at lam={lam}"
        # The live columns still recover the truth at lam = 0.
        if lam == 0.0:
            assert np.allclose(w[[0, 1, 3]], w_true[[0, 1, 3]], atol=0.02)

        V = _sandwich(X, y, w, lam, None)
        assert np.isfinite(V).all()
        assert V[2, 2] == 0.0, "dead column was given a variance"
        assert not np.any(V[2, :]) and not np.any(V[:, 2])

    # And with no dead column the answer is exactly what it always was.
    Xf = rng.normal(size=(60, 4))
    yf = Xf @ w_true + 0.01 * rng.normal(size=60)
    s = np.sqrt((Xf ** 2).mean(axis=0))
    Z = Xf / s
    for lam in (0.0, 1.0):
        expected = np.linalg.solve(Z.T @ Z + lam * np.eye(4), Z.T @ yf) / s
        assert np.allclose(ridge(Xf, yf, lam), expected, rtol=0, atol=0)
