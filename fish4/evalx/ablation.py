"""Ablation guard: prove that an "ablation" changes exactly one thing.

THE FAILURE THIS EXISTS TO PREVENT
----------------------------------
v0.3 ran a strategy ablation in which the ablated agent's suit-depth term was
silently normalized by 6 while the baseline's was not. Every cell of that
study therefore compared TWO changes at once. It ran to n=1000 and produced
tight, confident, wrong intervals; nothing in the statistics could have
caught it, because the statistics were correct about the wrong comparison.
The repository now pins that specific case with
``tests/test_tuned_baseline.py``. This module generalizes it into a tool any
future ablation can use before it spends CPU.

THE CHECK
---------
An ablation is well-formed when both of these hold:

1. IDENTITY AT THE DEFAULT. With the ablated parameter at its zero/default
   value the candidate must make the SAME decision as the baseline at every
   position, not merely score similarly. Decision-for-decision equality over
   real game positions is the strongest cheap check available: it catches a
   changed term even when the change is small enough that a 1000-pair duel
   would call the two policies equal.

2. EFFECT AT A NON-ZERO SETTING. With the parameter switched on, at least one
   decision must change. A term that never changes any decision makes an
   ablation that measures nothing, and will still produce a confident
   "no significant difference" that reads like evidence of no effect.

Positions come from REAL PLAY, driven by the baseline itself, so the check is
made on the distribution the ablation will actually be measured on. Both
agents are given identical seats and identical RNG seeds, and (when
equivalent) they consume randomness in the same order, so a divergence means
a genuine behavioural difference rather than a drifting RNG.

WHY THE FIRST DIVERGENCE IS REPORTED IN FULL
--------------------------------------------
"They differ somewhere in 5000 decisions" is not actionable. The failure
message names the game seed, the ply, the seat, the hand, and both chosen
actions, which in practice is enough to reproduce the disagreement in a
single ``play_game`` call.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from multiprocessing import Pool
from typing import Optional, Sequence

from fish.agents import AGENT_REGISTRY
from fish.cards import card_name, mask_to_cards
from fish.engine import Ask, Claim, GameState, Pass
from fish.observation import Observation
from fish.rules import RuleConfig

from .harness import MAX_WORKERS, AgentSpec

#: Games are driven to termination by the baseline; this cap stops the loop in
#: the (rare, real) case where a policy livelocks. See SPEC.md 4.5.
DEFAULT_MAX_PLIES = 3000


class AblationDivergence(AssertionError):
    """Raised when an ablation is not what it claims to be.

    Subclasses AssertionError so it reads naturally inside a test.
    """


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _fmt_action(a) -> str:
    if isinstance(a, Ask):
        return f"ASK p{a.target} for {card_name(a.card)}"
    if isinstance(a, Claim):
        return (f"CLAIM hs{a.half_suit} -> "
                f"({','.join('p' + str(x) for x in a.assignment)})")
    if isinstance(a, Pass):
        return f"PASS to p{a.teammate}"
    return repr(a)


def _fmt_hand(mask: int) -> str:
    return " ".join(card_name(c) for c in mask_to_cards(mask)) or "(empty)"


@dataclass(frozen=True)
class Divergence:
    """One position at which baseline and candidate chose differently."""

    game_index: int
    deal_seed: int
    ply: int
    seat: int
    baseline_action: str
    candidate_action: str
    hand: str
    hand_counts: tuple
    unresolved: tuple
    n_legal_asks: int

    def message(self) -> str:
        return (
            f"first divergence at game {self.game_index} "
            f"(deal_seed={self.deal_seed}), ply {self.ply}, seat "
            f"p{self.seat}\n"
            f"    hand            : {self.hand}\n"
            f"    hand counts     : {list(self.hand_counts)}\n"
            f"    unresolved suits: {list(self.unresolved)}\n"
            f"    legal asks      : {self.n_legal_asks}\n"
            f"    baseline chose  : {self.baseline_action}\n"
            f"    candidate chose : {self.candidate_action}")

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["hand_counts"] = list(self.hand_counts)
        d["unresolved"] = list(self.unresolved)
        return d


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

@dataclass
class IdentityReport:
    baseline_spec: AgentSpec
    candidate_spec: AgentSpec
    n_games: int
    n_positions: int = 0
    n_divergences: int = 0
    first_divergence: Optional[Divergence] = None
    divergences: list = field(default_factory=list)   # up to ``keep`` of them
    seconds: float = 0.0
    errors: list = field(default_factory=list)

    @property
    def identical(self) -> bool:
        return self.n_divergences == 0 and not self.errors

    @property
    def divergence_rate(self) -> float:
        return self.n_divergences / max(1, self.n_positions)

    def summary(self) -> str:
        head = (f"{self.baseline_spec[0]}{self.baseline_spec[1]} vs "
                f"{self.candidate_spec[0]}{self.candidate_spec[1]}: "
                f"{self.n_divergences}/{self.n_positions} decisions differ "
                f"({self.divergence_rate:.2%}) over {self.n_games} games "
                f"in {self.seconds:.1f}s")
        if self.first_divergence is not None:
            head += "\n  " + self.first_divergence.message().replace("\n", "\n  ")
        return head

    def to_dict(self) -> dict:
        return {
            "baseline_spec": [self.baseline_spec[0], dict(self.baseline_spec[1])],
            "candidate_spec": [self.candidate_spec[0], dict(self.candidate_spec[1])],
            "n_games": self.n_games,
            "n_positions": self.n_positions,
            "n_divergences": self.n_divergences,
            "divergence_rate": self.divergence_rate,
            "identical": self.identical,
            "first_divergence": (self.first_divergence.to_dict()
                                 if self.first_divergence else None),
            "seconds": self.seconds,
            "errors": list(self.errors),
        }


# ---------------------------------------------------------------------------
# Comparison over real positions
# ---------------------------------------------------------------------------

def _make(spec: AgentSpec):
    return AGENT_REGISTRY[spec[0]](**dict(spec[1]))


def _compare_one_game(job) -> dict:
    """Play one game driven by the BASELINE, asking both policies at every
    position what they would do.

    Driving with the baseline (rather than a third-party agent) keeps the
    position distribution equal to the one the baseline actually visits,
    which is the distribution a duel between the two would sample from.
    """
    (game_index, baseline_spec, candidate_spec, rules_dict, deal_seed,
     agent_seed, seats, max_plies, stop_on_first, keep) = job
    rules = RuleConfig(**rules_dict)
    state = GameState.deal(rules, seed=deal_seed)

    seed_rng = random.Random(agent_seed)
    base_agents, cand_agents = [], []
    for p in range(6):
        s = seed_rng.getrandbits(64)
        b = _make(baseline_spec)
        c = _make(candidate_spec)
        # IDENTICAL seat and IDENTICAL seed: any difference in behaviour is
        # then attributable to the parameter, not to the RNG.
        b.begin_game(p, rules, s)
        c.begin_game(p, rules, s)
        base_agents.append(b)
        cand_agents.append(c)

    n_positions = 0
    n_divergences = 0
    divergences = []        # at most ``keep`` of them, for the message
    errors = []
    ply = 0
    while not state.is_terminal and ply < max_plies:
        p = state.turn
        obs = Observation.from_state(state, p)
        base_action = base_agents[p].act(obs)
        cand_action = None
        raised = False
        try:
            cand_action = cand_agents[p].act(obs)
        except Exception as exc:                          # noqa: BLE001
            raised = True
            if len(errors) < keep:
                errors.append(
                    f"game {game_index} ply {ply} seat p{p}: candidate raised "
                    f"{type(exc).__name__}: {exc}")
        # Every seat is stepped so the candidate's belief state stays attached
        # from the start of the game (BeliefState refuses truncated histories),
        # but only audited seats count toward the comparison.
        if p in seats:
            n_positions += 1
            if raised or cand_action != base_action:
                n_divergences += 1
                if len(divergences) < keep:
                    divergences.append(Divergence(
                        game_index=game_index, deal_seed=deal_seed, ply=ply,
                        seat=p,
                        baseline_action=_fmt_action(base_action),
                        candidate_action=("<raised>" if raised
                                          else _fmt_action(cand_action)),
                        hand=_fmt_hand(obs.hand),
                        hand_counts=tuple(obs.hand_counts),
                        unresolved=tuple(i for i, w in enumerate(obs.set_winner)
                                         if w is None),
                        n_legal_asks=len(obs.legal_asks()),
                    ).to_dict())
                if stop_on_first:
                    return {"game_index": game_index,
                            "n_positions": n_positions,
                            "n_divergences": n_divergences,
                            "divergences": divergences, "errors": errors,
                            "truncated": True}
        state.apply(p, base_action)
        ply += 1

    return {"game_index": game_index, "n_positions": n_positions,
            "n_divergences": n_divergences, "divergences": divergences,
            "errors": errors, "truncated": False}


def compare_decisions(baseline_spec: AgentSpec, candidate_spec: AgentSpec,
                      n_games: int = 6, seed: int = 4242,
                      rules: Optional[RuleConfig] = None,
                      seats: Sequence[int] = (0, 1, 2, 3, 4, 5),
                      max_plies: int = DEFAULT_MAX_PLIES,
                      stop_on_first: bool = False, keep: int = 5,
                      n_workers: int = 1) -> IdentityReport:
    """Ask both policies for a decision at every position of ``n_games`` games.

    ``seats`` restricts which seats are audited; the default audits all six,
    which is roughly six times more positions per game than the v0.3
    single-seat check for the same simulation cost.

    ``stop_on_first`` is for the identity assertion, where the first
    divergence is already a failure and finishing the run wastes time.
    """
    rules = rules or RuleConfig()
    rules_dict = rules.to_dict()
    seats = tuple(sorted(set(seats)))
    seed_rng = random.Random(seed)
    # Agent seeds are drawn from a stream independent of the deal seeds, as
    # everywhere else in this project (fish/runner.py).
    jobs = [(g, baseline_spec, candidate_spec, rules_dict, seed * 100003 + g,
             seed_rng.getrandbits(64), seats, max_plies, stop_on_first, keep)
            for g in range(n_games)]

    t0 = time.time()
    workers = min(max(1, n_workers), MAX_WORKERS)
    if workers > 1 and n_games > 1:
        with Pool(workers) as pool:
            outs = pool.map(_compare_one_game, jobs)
    else:
        outs = []
        for j in jobs:
            o = _compare_one_game(j)
            outs.append(o)
            if stop_on_first and o["divergences"]:
                break

    report = IdentityReport(baseline_spec=baseline_spec,
                            candidate_spec=candidate_spec, n_games=n_games)
    all_div = []
    for o in outs:
        report.n_positions += o["n_positions"]
        report.n_divergences += o["n_divergences"]
        report.errors.extend(o["errors"])
        all_div.extend(o["divergences"])
    all_div.sort(key=lambda d: (d["game_index"], d["ply"]))
    report.divergences = all_div[:keep]
    if all_div:
        report.first_divergence = Divergence(**all_div[0])
    report.seconds = time.time() - t0
    return report


# ---------------------------------------------------------------------------
# The two assertions
# ---------------------------------------------------------------------------

def check_reduces_to_baseline(baseline_spec: AgentSpec,
                              candidate_spec: AgentSpec, n_games: int = 6,
                              seed: int = 4242, **kw) -> IdentityReport:
    """Decision-for-decision identity check. Returns the report; does not raise."""
    return compare_decisions(baseline_spec, candidate_spec, n_games=n_games,
                             seed=seed, stop_on_first=True, **kw)


def assert_reduces_to_baseline(baseline_spec: AgentSpec,
                               candidate_spec: AgentSpec, n_games: int = 6,
                               seed: int = 4242, **kw) -> IdentityReport:
    """Assert the candidate reduces EXACTLY to the baseline.

    Raises ``AblationDivergence`` naming the first diverging position. Any
    ablation built on a candidate that fails this is confounded: its cells
    compare two changes at once.
    """
    rep = check_reduces_to_baseline(baseline_spec, candidate_spec,
                                    n_games=n_games, seed=seed, **kw)
    if rep.errors:
        raise AblationDivergence(
            f"candidate {candidate_spec} raised where baseline "
            f"{baseline_spec} did not:\n  " + "\n  ".join(rep.errors[:3]))
    if not rep.identical:
        raise AblationDivergence(
            f"ABLATION IS CONFOUNDED: {candidate_spec} does not reduce to "
            f"{baseline_spec}.\n"
            f"{rep.n_divergences} of {rep.n_positions} audited decisions "
            f"differ over {rep.n_games} games.\n"
            f"{rep.first_divergence.message()}\n"
            f"Every cell of an ablation built on this pair would compare two "
            f"changes at once. Fix the candidate before spending CPU on it.")
    return rep


def check_parameter_has_effect(baseline_spec: AgentSpec,
                               candidate_spec: AgentSpec, n_games: int = 6,
                               seed: int = 4242, **kw) -> IdentityReport:
    """Complementary check: does the non-zero setting change anything?"""
    return compare_decisions(baseline_spec, candidate_spec, n_games=n_games,
                             seed=seed, stop_on_first=False, **kw)


def assert_parameter_has_effect(baseline_spec: AgentSpec,
                                candidate_spec: AgentSpec, n_games: int = 6,
                                seed: int = 4242, min_rate: float = 0.0,
                                **kw) -> IdentityReport:
    """Assert the switched-on parameter actually changes decisions.

    ``min_rate`` optionally demands a minimum divergence rate: a term that
    moves one decision in ten thousand is real but cannot plausibly be
    measured by a duel of a few hundred pairs, and saying so up front is
    cheaper than discovering it from a null result.
    """
    rep = check_parameter_has_effect(baseline_spec, candidate_spec,
                                     n_games=n_games, seed=seed, **kw)
    if rep.n_divergences == 0:
        raise AblationDivergence(
            f"ABLATION MEASURES NOTHING: {candidate_spec} made the same "
            f"decision as {baseline_spec} at all {rep.n_positions} audited "
            f"positions over {rep.n_games} games. A duel between them can "
            f"only ever report 'no significant difference', and that result "
            f"would say nothing about the idea being tested.")
    if rep.divergence_rate < min_rate:
        raise AblationDivergence(
            f"{candidate_spec} changes only {rep.divergence_rate:.4%} of "
            f"decisions vs {baseline_spec} ({rep.n_divergences}/"
            f"{rep.n_positions}), below the required {min_rate:.4%}. The "
            f"effect is real but too rare for a duel of practical size to "
            f"resolve.")
    return rep


def assert_ablation_is_clean(baseline_spec: AgentSpec,
                             ablated_spec: AgentSpec,
                             enabled_spec: AgentSpec, n_games: int = 6,
                             seed: int = 4242, **kw) -> tuple:
    """Both halves of the guard in one call.

    ``ablated_spec`` is the candidate with the parameter at its zero/default
    value (must equal the baseline); ``enabled_spec`` is the same candidate
    with it switched on (must differ). Returns ``(identity, effect)`` reports.
    """
    identity = assert_reduces_to_baseline(baseline_spec, ablated_spec,
                                          n_games=n_games, seed=seed, **kw)
    effect = assert_parameter_has_effect(ablated_spec, enabled_spec,
                                         n_games=n_games, seed=seed, **kw)
    return identity, effect


__all__ = ["AblationDivergence", "Divergence", "IdentityReport",
           "compare_decisions", "check_reduces_to_baseline",
           "assert_reduces_to_baseline", "check_parameter_has_effect",
           "assert_parameter_has_effect", "assert_ablation_is_clean"]
