"""FishBot v0.4: exact-posterior play with a wide, ablatable ask objective.

Relationship to v0.3
--------------------
v0.3's strongest policy sampled 32 worlds from a *biased* sampler, scored asks
as ``P(success) + 0.06*depth + 0.6*turn_risk + 0.2*scarcity``, and claimed at a
fixed 0.97 confidence. Its own diagnosis was that the objective, not the depth
of search, was the binding constraint, and that belief precision had not
saturated (32 -> 96 samples was still worth +0.54 sets per deal-pair).

v0.4 changes three things and holds everything else fixed so the changes are
attributable:

1. **Inference.** Marginals come from exact combinatorial counting over the
   candidate-mask and quota system rather than from a heuristic sampler, with
   the OR constraints handled by a correction whose error is measured rather
   than assumed. See ``counting.py`` and ``posterior.py``.
2. **Objective.** Ten ablatable terms instead of three, all computed from the
   marginals in one vectorised pass. See ``askfeat.py``.
3. **Claiming.** The declared distribution is the exact posterior MAP, not the
   mode of 32 samples, and forced claims maximise expected sets rather than
   confidence. See ``claim4.py``.

Everything an acting policy touches comes from the Observation plus this seat's
own BeliefState, which is derived from public events and this seat's own hand.
``GameState`` is never visible here.
"""

from __future__ import annotations

import random
from typing import Optional

from fish.agents.base import Agent
from .tablebase4 import Tablebase4Mixin
from fish.beliefs import BeliefContradiction, BeliefState
from fish.engine import Action
from fish.observation import Observation

from .askfeat import AskWeights, DecisionContext, score_asks
from .claim4 import ClaimConfig, ClaimEvaluator, choose_pass
from .hsvalue import HalfSuitValue, score_asks_by_value
from .posterior import Posterior, PosteriorStats

#: Value models are small and immutable; six agents per game times thousands of
#: games would otherwise re-parse the same JSON constantly.
_VALUE_CACHE: dict = {}


def _load_value(path):
    if path is None:
        return None
    m = _VALUE_CACHE.get(path)
    if m is None:
        m = _VALUE_CACHE[path] = HalfSuitValue.load(path)
    return m


class FishBot4(Tablebase4Mixin, Agent):
    """The v0.4 policy. Every strategic choice is a constructor argument."""

    name = "fishbot4"

    def __init__(self,
                 # -- inference
                 n_worlds: int = 32,
                 n_draws: int = 160,
                 infer_mode: str = "auto",
                 opponent_gamma: float = 0.0,
                 depth_mode: str = "initial",
                 count_mode: str = "linear",
                 opp_lambda: float = 0.0,
                 # -- ask objective
                 w_suit: float = 0.06,
                 w_turn: float = 0.6,
                 w_scarce: float = 0.2,
                 w_reveal: float = 0.0,
                 w_deplete: float = 0.0,
                 w_expose: float = 0.0,
                 w_claim: float = 0.0,
                 w_info: float = 0.0,
                 w_certain: float = 0.0,
                 w_concent: float = 0.0,
                 w_signal: float = 0.0,
                 # -- learned half-suit value objective
                 objective: str = "linear",
                 hsvalue_path: str = None,
                 w_value: float = 0.0,
                 value_turn: float = 0.0,
                 value_expose: float = 0.0,
                 # -- claiming
                 claim_threshold: float = 0.97,
                 claim_exact: bool = True,
                 claim_exact_candidates: int = 3,
                 # -- adaptive style
                 w_retake: float = 0.0,
                 retake_window: int = 8,
                 w_behind: float = 0.0,
                 # -- belief-space lookahead
                 w_lookahead: float = 0.0,
                 lookahead_depth: int = 1,
                 lookahead_beam: int = 4,
                 lookahead_couple: bool = True,
                 # -- endgame
                 use_tablebase: bool = True,
                 tablebase_max_half_suits: int = 2,
                 # -- misc
                 stall_window: int = 80,
                 smart_pass: bool = False,
                 signal_mode: str = "off",
                 signal_max_p: float = 0.15):
        super().__init__()
        self.n_worlds = n_worlds
        self.n_draws = n_draws
        self.infer_mode = infer_mode
        self.opponent_gamma = opponent_gamma
        self.depth_mode = depth_mode
        self.count_mode = count_mode
        self.opp_lambda = opp_lambda
        self.weights = AskWeights(
            suit=w_suit, turn=w_turn, scarce=w_scarce, reveal=w_reveal,
            deplete=w_deplete, expose=w_expose, claim=w_claim, info=w_info,
            certain=w_certain, concent=w_concent, signal=w_signal)
        self.objective = objective
        self.hsvalue_path = hsvalue_path
        self.w_value = w_value
        self.value_turn = value_turn
        self.value_expose = value_expose
        self.claim_cfg = ClaimConfig(threshold=claim_threshold,
                                     exact_candidates=claim_exact_candidates,
                                     use_exact=claim_exact)
        self.w_retake = w_retake
        self.retake_window = retake_window
        self.w_behind = w_behind
        self.w_lookahead = w_lookahead
        self.lookahead_depth = lookahead_depth
        self.lookahead_beam = lookahead_beam
        self.lookahead_couple = lookahead_couple
        self.use_tablebase = use_tablebase
        self.tablebase_max_half_suits = tablebase_max_half_suits
        self.stall_window = stall_window
        self.smart_pass = smart_pass
        self.signal_mode = signal_mode
        self.signal_max_p = signal_max_p
        self.stats = PosteriorStats()
        self.bel: Optional[BeliefState] = None

    # -- lifecycle -----------------------------------------------------------

    def begin_game(self, player: int, rules, seed: int) -> None:
        super().begin_game(player, rules, seed)
        self.bel = BeliefState(rules, observer=player)

    # -- policy --------------------------------------------------------------

    def act(self, obs: Observation) -> Action:
        self.bel.update(obs)

        # Nothing hidden left? Solve the position instead of estimating it.
        # (Leak-free: the reconstruction uses only public events plus our own
        # hand, and refuses unless every live card is already pinned.)
        exact = self.tablebase_action(obs)
        if exact is not None:
            return exact

        post = Posterior(self.bel, self.rng, n_draws=self.n_draws,
                         n_worlds=self.n_worlds, mode=self.infer_mode,
                         obs=obs, gamma=self.opponent_gamma,
                         depth_mode=self.depth_mode,
                         count_mode=self.count_mode,
                         opp_lambda=self.opp_lambda,
                         stats=self.stats)
        ctx = DecisionContext(obs, self.bel, post)

        if obs.must_pass():
            passes = obs.legal_passes()
            if self.smart_pass:
                pick = choose_pass(ctx, passes)
                if pick is not None:
                    return pick
            return max(passes, key=lambda p: obs.hand_counts[p.teammate])

        claims = ClaimEvaluator(ctx, self.claim_cfg)
        voluntary = claims.voluntary_claim()
        if voluntary is not None:
            return voluntary

        asks = obs.legal_asks()
        stalled = self.stalled(obs, window=self.stall_window)
        if not asks or (stalled and obs.claimable_half_suits()):
            forced = claims.forced_claim()
            if forced is not None:
                return forced
        if not asks:
            raise BeliefContradiction("no legal ask and no claimable half-suit")

        model = _load_value(self.hsvalue_path)
        if self.objective == "value" and model is not None:
            scores = score_asks_by_value(ctx, asks, model,
                                         turn_weight=self.value_turn,
                                         expose_weight=self.value_expose)
            _, p = score_asks(ctx, asks, AskWeights.zeros())
        else:
            # Style adapts to the match before the ask is scored: a team that
            # is behind weighs its tie-breakers differently from one that is
            # ahead. Zero leaves the incumbent weights untouched.
            wts = self.weights
            if self.w_behind:
                from .adaptive import adjust_weights
                wts = adjust_weights(wts, obs, self.w_behind)
            scores, p = score_asks(ctx, asks, wts)
            if self.w_value and model is not None:
                scores = scores + self.w_value * score_asks_by_value(
                    ctx, asks, model)
        # Belief-space lookahead, as an additive bonus rather than a
        # replacement. The bonus is identically zero at depth <= 1, so the
        # baseline is reproduced decision for decision and the weight ablates
        # exactly one idea. See fish4/lookahead.py for why this is the one
        # search design the variance diagnosis does not rule out.
        # Breaking a duel: penalise taking back a card this seat just lost to
        # this same opponent. See fish4/adaptive.py for why this is expected to
        # lose and why it is worth measuring regardless.
        if self.w_retake:
            from .adaptive import retake_flags
            scores = scores - self.w_retake * retake_flags(
                obs, asks, self.retake_window)

        if self.w_lookahead and self.lookahead_depth > 1:
            from .lookahead import lookahead_bonus
            scores = scores + self.w_lookahead * lookahead_bonus(
                ctx, asks, depth=self.lookahead_depth,
                beam=self.lookahead_beam, couple=self.lookahead_couple)
        order = sorted(range(len(asks)), key=lambda i: -scores[i])
        top = scores[order[0]]
        # If the ask we are ABOUT TO MAKE cannot land, it hands over the turn
        # for certain, so a claim is worth considering instead - but only if it
        # is more likely right than wrong, since otherwise it gifts a set on top
        # of the lost turn, which is strictly worse than a doomed ask. v0.3 used
        # the same 0.5 bar.
        #
        # Note what this is NOT. An earlier version of this comment said "if no
        # ask can possibly land", which is a stricter condition - max(p) <= 0 -
        # and not what the line below tests. p[order[0]] is the probability of
        # the highest-SCORING ask, so the gate can open while some other ask
        # could still have landed, and it depends on every objective weight
        # rather than on a fact about the position. The two readings disagree on
        # roughly one decision in a few hundred.
        #
        # The code is left as it is deliberately. Both readings are defensible -
        # "the move I would make is doomed" is a reasonable trigger, not only
        # "every move is doomed" - and which plays better is an empirical
        # question nobody has measured. Changing it would silently move the
        # champion out from under every number in the paper to settle a question
        # by fiat. If it is ever measured, max(p) is the other arm.
        # Signalling. An ask placed in a half-suit our own team fully owns
        # cannot land, so it throws the turn away - but under the no-bluff rule
        # it publicly proves we do not hold the card we asked for, which is the
        # one fact a partner needs to place a split. Measured: a half-suit that
        # is provably ours but unplaceable is nulled 17.5% of the time against
        # 2.8% otherwise, and such half-suits are 27% of all nulls.
        #   "dead"  - only when NO ask anywhere can land, so the turn is free.
        #   "stuck" - also when our best ask is unlikely to land anyway, which
        #             makes the turn cheap rather than free.
        if self.signal_mode != "off":
            from .perpetual import signalling_ask, stuck_half_suits
            cheap = p[order[0]] <= (self.signal_max_p
                                    if self.signal_mode == "stuck" else 0.0)
            if cheap and stuck_half_suits(obs, self.bel, ctx):
                sig = signalling_ask(
                    obs, self.bel, ctx,
                    require_dead=(self.signal_mode == "dead"))
                if sig is not None:
                    return sig

        if p[order[0]] <= 0.0:
            best = claims.best_candidate()
            if best is not None and best[0] >= 0.5:
                return best[2]
        pool = [i for i in order if scores[i] >= top - 1e-9]
        return asks[self.rng.choice(pool)]

    # -- out-of-turn claiming --------------------------------------------------

    def certain_claim(self, obs: Observation):
        """A claim this seat could make with certainty, or None.

        Used only when the rules permit declaring outside your own turn. It is
        deliberately the cheap, purely deductive test - every card of some
        half-suit pinned by this seat's beliefs, all of them on this seat's team
        - because polling five off-turn seats after every action must not cost a
        full posterior each. A seat that merely *suspects* the split waits for
        its own turn, where the full machinery runs.
        """
        from fish.cards import half_suit_cards, team_of
        from fish.engine import Claim
        self.bel.update(obs)
        my_team = team_of(self.player)
        for hs in range(len(obs.set_winner)):
            if obs.set_winner[hs] is not None:
                continue
            assignment = []
            for c in half_suit_cards(hs):
                m = self.bel.current_holder_mask(c)
                if m == 0 or m & (m - 1):
                    break
                holder = m.bit_length() - 1
                if team_of(holder) != my_team:
                    break
                assignment.append(holder)
            else:
                return Claim(hs, tuple(assignment))
        return None

    # -- introspection --------------------------------------------------------

    def diagnostics(self) -> dict:
        return self.stats.to_dict()
