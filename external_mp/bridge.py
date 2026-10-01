"""Bridge: KRAKEN plays Canadian Fish inside MeagerPotato's own engine.

WHY THIS SHAPE. Their repository ships a rules engine (`lib/engine/reduce.ts`)
and a bot (`lib/engine/bots/`), and their own harness already runs bot against
bot. So the duel runs in THEIR engine, with THEIR reducer arbitrating and THEIR
`decide()` playing one team. Only our policy is bridged in. Nothing about the
rules is taken on my reading of their source -- the arbiter is their code.

That choice is deliberate and it is the lesson of this project's worst error: a
previous cross-engine bridge handed the foreign bot a subtly wrong view for
weeks and was worth +3.0833 sets a game to us, which invalidated a published
headline. Running inside the opponent's arbiter removes the entire class.

THE RULES, READ OFF THEIR REDUCER, AND WHY OUR ENGINE CAN SPEAK THEM

    48 cards, 8 books of 6, 6 seats of 8, teams by seat parity
    miss -> the turn passes to the target; hit -> the asker keeps it
    you may not ask for a card you hold; you must hold a card of the book
    a claim names only your own team's seats
    claim resolution is THREE-way:
        any card with an opponent      -> the OPPONENTS score the book
        all on your team, split right  -> you score it
        all on your team, split wrong  -> VOID, nobody scores

That last line is the one that matters. Our engine already has it exactly:
`fish/engine.py::_apply_claim` with `wrong_distribution_outcome="null"` is
their three-way rule term for term, and `variant="48"` gives 8 half-suits. So
`RuleConfig(variant="48", wrong_distribution_outcome="null")` IS their game --
a configuration this project already supports and already used as its default
through the v0.4 era.

It also changes what a claim is worth. Under our usual rules a wrong split
hands the book to the opponents, a two-point swing; here it merely voids, a one
-point loss. Claiming is strictly cheaper in their game, so a gate tuned on
ours is tuned for the wrong price. That is a prediction, not an adjustment, and
it is registered before any duel.

THE CARD MAP IS THEIRS, NOT MINE. `external_mp/cards.json` is dumped from their
`ALL_BOOKS` / `bookCards` / `cardBook`, and the map is checked against our own
`card // 6` half-suit rule for all 48 cards before a single game is played. A
mapping error here is the exact failure mode that cost this project a headline,
so it is a hard assert and not a comment.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, half_suit_of, team_of            # noqa: E402
from fish.engine import (NULL_TEAM, Ask, AskEvent, Claim,            # noqa: E402
                         ClaimEvent, Pass, PassEvent)
from fish.observation import Observation                              # noqa: E402
from fish.rules import RuleConfig                                     # noqa: E402

#: their game, in our engine's words
RULES = RuleConfig(variant="48", wrong_distribution_outcome="null")

_SPEC = json.loads((Path(__file__).parent / "cards.json").read_text())
BOOKS: list[str] = [b["book"] for b in sorted(_SPEC["books"], key=lambda b: b["i"])]
#: their card string -> our card id, built from their own constants
CARD_ID: dict[str, int] = {}
for _b in sorted(_SPEC["books"], key=lambda b: b["i"]):
    for _j, _c in enumerate(_b["cards"]):
        CARD_ID[_c] = _b["i"] * 6 + _j
ID_CARD: dict[int, str] = {v: k for k, v in CARD_ID.items()}
BOOK_INDEX: dict[str, int] = {b: i for i, b in enumerate(BOOKS)}


def _verify_map() -> None:
    """Their book index and our half-suit index must agree on every card.

    Load-bearing. Our card ids are variant-stable with `card // 6` as the
    half-suit, and their books are six cards each in a fixed order; if those two
    facts ever disagree the agent would reason about a different game than the
    one being arbitrated, and every number downstream would be meaningless
    while looking fine.
    """
    if len(CARD_ID) != 48:
        raise SystemExit(f"card map has {len(CARD_ID)} entries, not 48")
    for row in _SPEC["cards"]:
        cid = CARD_ID[row["card"]]
        if half_suit_of(cid) != row["bookIndex"]:
            raise SystemExit(
                f"{row['card']}: their book {row['book']}={row['bookIndex']} "
                f"but our half_suit_of({cid})={half_suit_of(cid)}")
    if sorted(ID_CARD) != list(range(48)):
        raise SystemExit("card ids are not exactly 0..47")


_verify_map()

TEAM_OUTCOME = {"team0": 0, "team1": 1, "void": NULL_TEAM}


def mask(cards) -> int:
    m = 0
    for c in cards:
        m |= 1 << CARD_ID[c]
    return m


def to_history(log: list[dict]) -> tuple:
    """Their public log -> our event tuple.

    Only the three event kinds our belief reads are emitted. Their
    `player_out`, `endgame`, `game_started` and `game_over` carry no card
    information our constraint store does not already have from counts and
    resolutions, and their `designate` has no analogue in our engine; dropping
    them is safe because our belief is driven by asks and claims alone.
    """
    out: list = []
    for ev in log:
        t = ev.get("type")
        if t == "ask":
            out.append(AskEvent(ev["asker"], ev["target"],
                                CARD_ID[ev["card"]], bool(ev["hit"])))
        elif t == "claim":
            bi = BOOK_INDEX[ev["book"]]
            holders = ev["actualHolders"]
            revealed = tuple(holders[c] for c in _SPEC["books"][bi]["cards"])
            declared = tuple(ev["assignments"][c]
                             for c in _SPEC["books"][bi]["cards"])
            out.append(ClaimEvent(ev["claimer"], bi, declared, revealed,
                                  TEAM_OUTCOME[ev["outcome"]]))
        elif t == "pass":
            out.append(PassEvent(ev["from"], ev["to"]))
    return tuple(out)


def to_observation(view: dict) -> Observation:
    """Their SeatView -> our Observation, field for field."""
    sw: list = [None] * 8
    for book, res in (view.get("books") or {}).items():
        if res:
            sw[BOOK_INDEX[book]] = TEAM_OUTCOME[res["outcome"]]
    return Observation(
        player=view["seat"],
        rules=RULES,
        hand=mask(view["hand"]),
        turn=view["turn"],
        hand_counts=tuple(view["counts"]),
        set_winner=tuple(sw),
        history=to_history(view.get("log") or []),
    )


def to_action(act, seat: int, view: dict) -> dict:
    """Our Action -> their GameAction."""
    if isinstance(act, Ask):
        return {"type": "ask", "seat": seat, "target": act.target,
                "card": ID_CARD[act.card]}
    if isinstance(act, Claim):
        bi = act.half_suit
        cards = _SPEC["books"][bi]["cards"]
        return {"type": "claim", "seat": seat, "book": BOOKS[bi],
                "assignments": {c: int(act.assignment[j])
                                for j, c in enumerate(cards)}}
    if isinstance(act, Pass):
        return {"type": "pass", "seat": seat, "to": act.teammate}
    raise SystemExit(f"cannot translate {type(act).__name__} to their action")


def endgame_claim(ag, obs):
    """Their `endgame` admits only a claim, where our engine would PASS.

    THE RULE DIFFERENCE, AND WHY IT IS NOT A POLICY CHOICE. In their engine the
    claiming seat keeps the turn through the endgame and claims the remaining
    books one at a time -- `reduceClaim`'s endgame branch returns the turn to
    the same seat -- and `reducePass` rejects a pass outside `awaitPass`. In
    ours a seat holding no cards while a teammate holds some MUST pass, and
    `FishBot4.act` duly returns one. Their reducer refuses it: WRONG_PHASE.
    That cost two aborted sides on the first power run.

    So the bridge has to translate the TRIGGER, and it translates it to our own
    machinery rather than to a heuristic of its own: `ClaimEvaluator` with this
    agent's own configuration, and `forced_claim()`, which is the method our
    engine uses in exactly this position ("the best declaration available when
    we have no legal ask"). Their bot reaches for its own `forcedClaim` here
    too.

    It also prices their rule correctly without being told: forced_claim reads
    `wrong_distribution_outcome` off the observation, so under their
    void-on-bad-split rule it ranks by p_exact with a wrong split costing 0
    rather than -1. That is our engine's own code doing their arithmetic.
    """
    from fish4.claim4 import ClaimEvaluator
    from fish4.askfeat import DecisionContext
    ag.bel.update(obs)
    post = ag.build_posterior(obs)
    ctx = DecisionContext(obs, ag.bel, post)
    claims = ClaimEvaluator(ag._claim_ctx(ctx), ag.claim_cfg)
    return claims.voluntary_claim() or claims.forced_claim()


def designate(view: dict) -> dict:
    """Their `awaitDesignate`, which our engine has no action for.

    Reached only when the claimant's whole TEAM is out of cards: they must name
    an opponent, who then claims out every remaining book. Our engine has no
    such action, so this is BRIDGE logic and is labelled as such -- it is not
    our policy and must not be read as one. The choice is close to
    inconsequential (the remaining books go to the opponents either way) and is
    made deterministically: the opponent holding the fewest cards.
    """
    seat = view["seat"]
    counts = view["counts"]
    opp = [s for s in range(NUM_PLAYERS)
           if team_of(s) != team_of(seat) and counts[s] > 0]
    if not opp:
        opp = [s for s in range(NUM_PLAYERS) if team_of(s) != team_of(seat)]
    return {"type": "designate", "seat": seat, "to": min(opp, key=lambda s: counts[s])}
