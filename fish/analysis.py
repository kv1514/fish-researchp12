"""Parse a legal information state and produce observation-safe move analysis."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Mapping, Sequence

from .agents import SearchAgent, _is_ask
from .belief import _action_card, _action_target
from .core import (
    AskAction,
    AskEvent,
    BadClaimAward,
    ClaimAction,
    ClaimEvent,
    ClaimOutcome,
    ClaimTiming,
    ForcedClaimsStartedEvent,
    GamePhase,
    HouseRules,
    NULL_OWNER,
    PlayerObservation,
    Ruleset,
    SelectForcedClaimerAction,
    SelectSuccessorAction,
    SuccessorSelectedEvent,
    UNRESOLVED,
    opponents,
    team_of,
    teammates,
)
from .runner import make_agent


RESOLUTION_NAMES = {
    "unresolved": UNRESOLVED,
    "a": 0,
    "team_a": 0,
    "b": 1,
    "team_b": 1,
    "null": NULL_OWNER,
    "forfeit": NULL_OWNER,
}


@dataclass(frozen=True, slots=True)
class RankedAction:
    action: Any
    relative_value: float
    acquisition_probability: float | None


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    best_action: Any
    alternatives: tuple[RankedAction, ...]
    beliefs: Mapping[int, Mapping[int | None, float]]
    reasoning: tuple[str, ...]
    value_label: str


def _rules_from_document(document: Mapping[str, Any]) -> Ruleset:
    rule_name = str(document.get("ruleset", "54")).lower()
    house_document = dict(document.get("house_rules", {}))
    house = HouseRules(
        claim_timing=ClaimTiming(house_document.get("claim_timing", "turn_only")),
        mandatory_immediate_claims=bool(
            house_document.get("mandatory_immediate_claims", False)
        ),
        claimant_chooses_next_teammate=bool(
            house_document.get("claimant_chooses_next_teammate", False)
        ),
        allow_owned_card_bluff=bool(house_document.get("allow_owned_card_bluff", False)),
        misdistributed_claim_award=BadClaimAward(
            house_document.get("misdistributed_claim_award", "null")
        ),
        opponent_held_claim_award=BadClaimAward(
            house_document.get("opponent_held_claim_award", "opponent")
        ),
        reveal_claim_distribution=bool(
            house_document.get("reveal_claim_distribution", True)
        ),
        cardless_players_may_claim=bool(
            house_document.get("cardless_players_may_claim", False)
        ),
    )
    if rule_name in ("54", "joker_54", "nine_suit_54", "eights_jokers_54"):
        return Ruleset.joker_54(house)
    if rule_name in ("48", "standard_48", "classic_48"):
        return Ruleset.standard_48(house)
    raise ValueError(f"unsupported ruleset: {rule_name}")


def _card_id(ruleset: Ruleset, value: int | str) -> int:
    return ruleset.card(value).id


def _half_suit_id(ruleset: Ruleset, value: int | str) -> int:
    if isinstance(value, int) or str(value).isdigit():
        result = int(value)
        if not 0 <= result < ruleset.num_half_suits:
            raise ValueError(f"invalid half-suit: {value}")
        return result
    normalized = str(value).strip().lower()
    for half_suit in ruleset.half_suits:
        if half_suit.name.lower() == normalized:
            return half_suit.id
    raise ValueError(f"unknown half-suit: {value}")


def _parse_resolutions(ruleset: Ruleset, raw: Any) -> tuple[int, ...]:
    result = [UNRESOLVED] * ruleset.num_half_suits
    if raw is None:
        return tuple(result)
    if isinstance(raw, Mapping):
        entries = ((_half_suit_id(ruleset, key), value) for key, value in raw.items())
    else:
        if len(raw) != ruleset.num_half_suits:
            raise ValueError("resolved_owners must have one entry per half-suit")
        entries = enumerate(raw)
    for half_suit, value in entries:
        if isinstance(value, str):
            try:
                resolution = RESOLUTION_NAMES[value.lower()]
            except KeyError as exc:
                raise ValueError(f"invalid resolution: {value}") from exc
        else:
            resolution = int(value)
        if resolution not in (UNRESOLVED, 0, 1, NULL_OWNER):
            raise ValueError(f"invalid resolution: {value}")
        result[half_suit] = resolution
    return tuple(result)


def _allocation(ruleset: Ruleset, half_suit: int, raw: Any) -> tuple[int, ...]:
    cards = ruleset.half_suits[half_suit].cards
    if isinstance(raw, Mapping):
        normalized = {_card_id(ruleset, card): int(owner) for card, owner in raw.items()}
        if set(normalized) != set(cards):
            raise ValueError("claim allocation must name exactly the six half-suit cards")
        return tuple(normalized[card] for card in cards)
    if len(raw) != 6:
        raise ValueError("claim allocation must contain six owners")
    return tuple(int(owner) for owner in raw)


def _parse_history(
    ruleset: Ruleset,
    raw_history: Sequence[Mapping[str, Any]],
    current_counts: tuple[int, ...],
) -> tuple[Any, ...]:
    events: list[Any] = []
    for raw in raw_history:
        event_type = str(raw.get("type", "ask")).lower()
        counts = tuple(int(value) for value in raw.get("card_counts", current_counts))
        if len(counts) != 6:
            raise ValueError("event card_counts must contain six values")
        if event_type == "ask":
            asker = int(raw["asker"])
            target = int(raw["target"])
            success = bool(raw["success"])
            turn_after = int(raw.get("turn_after", asker if success else target))
            events.append(
                AskEvent(asker, target, _card_id(ruleset, raw["card"]), success, counts, turn_after)
            )
        elif event_type == "claim":
            half_suit = _half_suit_id(ruleset, raw["half_suit"])
            allocation = _allocation(ruleset, half_suit, raw["allocation"])
            revealed_raw = raw.get("revealed_owners")
            revealed = None if revealed_raw is None else _allocation(ruleset, half_suit, revealed_raw)
            events.append(
                ClaimEvent(
                    int(raw["claimant"]),
                    half_suit,
                    allocation,
                    ClaimOutcome(str(raw["outcome"])),
                    None if raw.get("awarded_team") is None else int(raw["awarded_team"]),
                    revealed,  # type: ignore[arg-type]
                    counts,  # type: ignore[arg-type]
                    int(raw.get("turn_after", raw["claimant"])),
                )
            )
        elif event_type == "successor":
            events.append(
                SuccessorSelectedEvent(
                    int(raw["selector"]), int(raw["successor"]), counts, int(raw["successor"])
                )
            )
        elif event_type == "forced_claims":
            forced = int(raw["forced_claimer"])
            selector = int(raw["selector"])
            events.append(
                ForcedClaimsStartedEvent(selector, forced, team_of(selector), counts, forced)
            )
        else:
            raise ValueError(f"unknown history event type: {event_type}")
    return tuple(events)


def observation_from_dict(document: Mapping[str, Any]) -> PlayerObservation:
    """Validate and construct an observation without inventing a hidden deal."""
    ruleset = _rules_from_document(document)
    player = int(document["player"])
    turn = int(document.get("turn", player))
    if player not in range(6) or turn not in range(6):
        raise ValueError("player and turn must be in 0..5")
    own_hand = tuple(sorted(_card_id(ruleset, card) for card in document["own_hand"]))
    if len(set(own_hand)) != len(own_hand):
        raise ValueError("own_hand contains a duplicate card")
    counts = tuple(int(value) for value in document["card_counts"])
    if len(counts) != 6 or any(value < 0 for value in counts):
        raise ValueError("card_counts must contain six nonnegative values")
    if counts[player] != len(own_hand):
        raise ValueError("the player's public card count must match own_hand")
    resolutions = _parse_resolutions(ruleset, document.get("resolved_owners"))
    unresolved_count = sum(value == UNRESOLVED for value in resolutions)
    if sum(counts) != unresolved_count * 6:
        raise ValueError("card counts do not conserve unresolved cards")
    scores = tuple(int(value) for value in document.get("scores", (0, 0)))
    if len(scores) != 2 or scores != (resolutions.count(0), resolutions.count(1)):
        raise ValueError("scores must equal the resolved half-suits awarded to each team")
    phase = GamePhase(str(document.get("phase", "play")))
    pending_selector = document.get("pending_selector")
    pending_selector = None if pending_selector is None else int(pending_selector)
    forced_claimer = document.get("forced_claimer")
    forced_claimer = None if forced_claimer is None else int(forced_claimer)
    history = _parse_history(ruleset, document.get("history", ()), counts)

    admin: tuple[Any, ...] = ()
    if phase == GamePhase.SELECT_SUCCESSOR and pending_selector == player:
        admin = tuple(
            SelectSuccessorAction(player, candidate)
            for candidate in teammates(player)
            if candidate != player and counts[candidate] > 0
        )
    elif phase == GamePhase.SELECT_FORCED_CLAIMER and pending_selector == player:
        admin = tuple(
            SelectForcedClaimerAction(player, candidate)
            for candidate in opponents(player)
            if counts[candidate] > 0
        )

    claim_allowed = (
        phase == GamePhase.FORCED_CLAIMS and forced_claimer == player
    ) or (
        phase == GamePhase.PLAY
        and counts[player] > 0
        and (ruleset.house_rules.claim_timing == ClaimTiming.ANY_TURN or turn == player)
    )
    mandatory = tuple(
        half_suit.id
        for half_suit in ruleset.half_suits
        if resolutions[half_suit.id] == UNRESOLVED
        and set(half_suit.cards) <= set(own_hand)
    ) if ruleset.house_rules.mandatory_immediate_claims else ()
    legal_claims = tuple(
        half_suit.id
        for half_suit in ruleset.half_suits
        if resolutions[half_suit.id] == UNRESOLVED
        and (not mandatory or half_suit.id in mandatory)
    ) if claim_allowed else ()

    legal_asks: list[AskAction] = []
    if phase == GamePhase.PLAY and turn == player and counts[player] > 0 and not mandatory:
        own = set(own_hand)
        for half_suit in ruleset.half_suits:
            if resolutions[half_suit.id] != UNRESOLVED or not own.intersection(half_suit.cards):
                continue
            for card in half_suit.cards:
                if card in own and not ruleset.house_rules.allow_owned_card_bluff:
                    continue
                for target in opponents(player):
                    if counts[target] > 0:
                        legal_asks.append(AskAction(player, target, card))

    done = unresolved_count == 0
    if done and phase != GamePhase.TERMINAL:
        raise ValueError("a fully resolved observation must use terminal phase")
    return PlayerObservation(
        ruleset,
        player,
        team_of(player),
        own_hand,
        turn,
        phase,
        pending_selector,
        forced_claimer,
        counts,  # type: ignore[arg-type]
        scores,  # type: ignore[arg-type]
        resolutions,
        history,
        tuple(legal_asks),
        legal_claims,
        admin,
        done,
        len(history),
    )


def analyze_observation(
    observation: PlayerObservation,
    *,
    agent_name: str = "search",
    seed: int = 0,
    particle_count: int = 256,
    determinizations: int = 256,
    alternatives: int = 5,
) -> AnalysisResult:
    agent = make_agent(
        agent_name,
        observation.ruleset,
        seed=seed,
        particle_count=particle_count,
        determinizations=determinizations,
    )
    candidates = agent.candidate_actions(observation)
    best = agent.choose_action(observation, candidates)
    if isinstance(agent, SearchAgent):
        ranked = tuple(
            RankedAction(
                estimate.action,
                estimate.value,
                _acquisition_probability(agent, estimate.action),
            )
            for estimate in agent.last_estimates[:alternatives]
        )
        value_label = "sampled retained-turn search value (uncalibrated)"
    else:
        scored = sorted(
            (
                RankedAction(
                    action,
                    float(agent.score_action(observation, action)) if hasattr(agent, "score_action") else 0.0,
                    _acquisition_probability(agent, action),
                )
                for action in candidates
            ),
            key=lambda item: item.relative_value,
            reverse=True,
        )
        ranked = tuple(scored[:alternatives])
        value_label = "policy heuristic value (uncalibrated)"
    belief = getattr(agent, "belief", None)
    beliefs: dict[int, Mapping[int | None, float]] = {}
    if belief is not None:
        for item in ranked:
            card = _action_card(item.action)
            if card is not None and card not in beliefs:
                beliefs[int(card)] = belief.probabilities(card)
    reasoning: list[str] = []
    if _is_ask(best):
        card = int(_action_card(best))
        target = int(_action_target(best))
        probability = _acquisition_probability(agent, best)
        if probability is not None:
            reasoning.append(
                f"Belief particles put {100.0 * probability:.1f}% probability on the target owning the requested card."
            )
        if belief is not None and target not in belief.domains.get(card, ()):
            reasoning.append("Public constraints eliminate this target; this ask is informational/turn-control only.")
        reasoning.append("A success retains the turn; a failure publicly transfers it to the target.")
    elif isinstance(best, ClaimAction):
        reasoning.append("The claim value includes exact teammate-distribution risk, not just team ownership.")
    else:
        reasoning.append("This administrative choice uses only public card counts and phase state.")
    return AnalysisResult(best, ranked, beliefs, tuple(reasoning), value_label)


def _acquisition_probability(agent: Any, action: Any) -> float | None:
    if not _is_ask(action) or not hasattr(agent, "belief"):
        return None
    return float(agent.belief.probability(_action_card(action), _action_target(action)))


def format_action(action: Any, ruleset: Ruleset) -> str:
    if isinstance(action, AskAction):
        return f"ASK Player {action.target} for {ruleset.cards[action.card].name}"
    if isinstance(action, ClaimAction):
        half_suit = ruleset.half_suits[action.half_suit]
        groups: dict[int, list[str]] = {}
        for card, owner in zip(half_suit.cards, action.allocation, strict=True):
            groups.setdefault(owner, []).append(ruleset.cards[card].name)
        detail = "; ".join(
            f"P{owner}: {', '.join(cards)}" for owner, cards in sorted(groups.items())
        )
        return f"CLAIM {half_suit.name} ({detail})"
    if isinstance(action, SelectSuccessorAction):
        return f"SELECT Player {action.successor} as successor"
    if isinstance(action, SelectForcedClaimerAction):
        return f"SELECT Player {action.forced_claimer} as forced claimer"
    return repr(action)


def analysis_as_dict(result: AnalysisResult, ruleset: Ruleset) -> dict[str, Any]:
    return {
        "best_action": format_action(result.best_action, ruleset),
        "value_label": result.value_label,
        "alternatives": [
            {
                "action": format_action(item.action, ruleset),
                "relative_value": item.relative_value,
                "acquisition_probability": item.acquisition_probability,
            }
            for item in result.alternatives
        ],
        "beliefs": {
            ruleset.cards[card].name: {
                ("resolved" if owner is None else f"P{owner}"): probability
                for owner, probability in owners.items()
            }
            for card, owners in result.beliefs.items()
        },
        "reasoning": list(result.reasoning),
    }
