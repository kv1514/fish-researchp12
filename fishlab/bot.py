#!/usr/bin/env python3
"""KRAKEN as a FishLab bot package, speaking `fishlab-json-v1` natively.

WHY NOT `kv-json-v1`. FishLab's §8 offers a bridge to this project's own
dialect, and it would have been one manifest line. It is not safe for this bot,
and the reason is measured rather than assumed.

Our `ClaimEvent` carries `revealed`, the TRUE holders at resolution, and
`fish/beliefs.py::_ingest` PINS every one of them into the belief. FishLab
deliberately publishes no true holders on a WRONG declaration -- that is what a
person at the table sees, and it is the right call for the game. So a bridge
must either invent them or omit them. Inventing them means passing the CLAIMED
split as if revealed, and over twelve champion self-play games every wrong
declaration did this:

    strategy "claimed-as-revealed": 5 of 5 raised BeliefContradiction

not sometimes, and not silently -- by the time a wrong declaration resolves the
ask history has usually already excluded one of the claimed seats, so pinning
the claim hits a card whose candidate mask forbids it. KRAKEN would crash at
the first wrong declaration, which happens in most games.

So this speaks FishLab's own protocol, where the question does not arise: a
failed declaration contributes its RESOLUTION (via `set_winner`) and nothing
about holders.

WHAT THE HANDSHAKE IS FOR. The two projects order the deck differently --
ours is clubs-first, FishLab's spades-first -- and number half-suits
differently, and even order the eights differently (`8C 8D 8H 8S` against
`8S 8H 8D 8C`). None of that is hardcoded here. `hello` hands over the whole
deck in engine order and §4 gives the rule that relates the two, so the
mapping is DERIVED and then checked: if the decks disagree this bot refuses to
play rather than guess.
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# In a shipped package the engine is VENDORED beside this file, so HERE is
# enough. In the source tree it lives one directory up. Walking up a few
# levels covers both without the package depending on where it was unzipped.
if not os.path.isdir(os.path.join(HERE, "fish")):
    _d = HERE
    for _ in range(4):
        _d = os.path.dirname(_d)
        if os.path.isdir(os.path.join(_d, "fish")):
            if _d not in sys.path:
                sys.path.insert(0, _d)
            break

VERSION = "1.1"


class Bridge:
    """Holds the deck correspondence and the per-deal state."""

    def __init__(self) -> None:
        self.ready = False
        self.card_of_name: dict[str, int] = {}
        self.their_card_to_ours: list[int] = []
        self.set_to_hs: list[int] = []          # their set index -> our hs
        self.hs_to_set: dict[int, int] = {}
        self.seat = 0
        self.rules = None

    # -- handshake ------------------------------------------------------
    def hello(self, req: dict) -> dict:
        from fish.cards import CARD_NAMES, half_suit_of
        proto = req.get("protocol", "fishlab-json-v1")
        if proto != "fishlab-json-v1":
            return {"error": f"this bot speaks fishlab-json-v1, not {proto!r}"}
        self.card_of_name = {n: i for i, n in enumerate(CARD_NAMES)}
        theirs = list(req.get("cards") or [])
        if len(theirs) != len(CARD_NAMES):
            return {"error": f"deck size {len(theirs)}, expected "
                             f"{len(CARD_NAMES)}"}
        missing = [n for n in theirs if n not in self.card_of_name]
        if missing:
            return {"error": "deck names this bot does not know: "
                             + ", ".join(missing[:6])}
        self.their_card_to_ours = [self.card_of_name[n] for n in theirs]

        # §4: their card at index i is in their set i//6. Derive their set ->
        # our half-suit, and REFUSE if the six do not agree, because a partial
        # correspondence is how a bot ends up declaring the wrong half-suit.
        n_sets = len(theirs) // 6
        self.set_to_hs = []
        for s in range(n_sets):
            ours = {half_suit_of(self.their_card_to_ours[s * 6 + j])
                    for j in range(6)}
            if len(ours) != 1:
                return {"error": f"their set {s} spans our half-suits "
                                 f"{sorted(ours)}; the decks do not correspond"}
            self.set_to_hs.append(ours.pop())
        if len(set(self.set_to_hs)) != n_sets:
            return {"error": "their sets do not map one-to-one onto ours"}
        self.hs_to_set = {h: s for s, h in enumerate(self.set_to_hs)}
        self.ready = True
        return {"ok": True, "name": "KRAKEN", "version": VERSION,
                "protocol": "fishlab-json-v1"}

    # -- translation ----------------------------------------------------
    def _card(self, name: str) -> int:
        try:
            return self.card_of_name[name]
        except KeyError:
            raise ValueError(f"unknown card name {name!r}")

    def _their_pos_to_our_pos(self, their_set: int, j: int) -> int:
        """Within-set index j of THEIR set -> within-set index of OUR half-suit.

        This is the transposition the FishLab docs single out: the engine
        SKIPS an allocation that names the wrong team, so a bot with this
        wrong looks like a bot that has decided never to declare.
        """
        return self.their_card_to_ours[their_set * 6 + j] % 6

    def _history(self, hist: list) -> tuple:
        from fish.engine import AskEvent, ClaimEvent, PassEvent
        out = []
        for e in hist or []:
            t = e.get("t")
            if t == "ask":
                out.append(AskEvent(asker=int(e["actor"]),
                                    target=int(e["target"]),
                                    card=self._card(e["card"]),
                                    success=bool(e["success"])))
            elif t == "pass":
                out.append(PassEvent(player=int(e["actor"]),
                                     teammate=int(e["target"])))
            elif t == "declare":
                if not e.get("success"):
                    # THE POINT OF THIS ADAPTER. A wrong declaration reveals
                    # no holders, so we contribute none. Its RESOLUTION still
                    # reaches the agent through set_winner in the state.
                    continue
                s = int(e["set"])
                hs = self.set_to_hs[s]
                owner = list(e["owner"])
                assign = [0] * 6
                for j, who in enumerate(owner):
                    assign[self._their_pos_to_our_pos(s, j)] = int(who)
                out.append(ClaimEvent(claimer=int(e["actor"]), half_suit=hs,
                                      declared=tuple(assign),
                                      revealed=tuple(assign),
                                      winner=int(e["winner"])))
        return tuple(out)

    def observation(self, state: dict, turn_override=None):
        from fish.observation import Observation
        from fish.rules import RuleConfig
        from fish.cards import NUM_PLAYERS
        seat = int(state["seat"])
        hand = 0
        for n in state.get("hand", []):
            hand |= 1 << self._card(n)
        counts = tuple(int(x) for x in state["hand_counts"])
        if len(counts) != NUM_PLAYERS:
            raise ValueError("hand_counts must have one entry per seat")
        if bin(hand).count("1") != counts[seat]:
            raise ValueError(
                f"hand has {bin(hand).count('1')} cards, hand_counts says "
                f"{counts[seat]}")
        sw_theirs = state["set_winner"]
        sw = [None] * len(sw_theirs)
        for s, w in enumerate(sw_theirs):
            sw[self.set_to_hs[s]] = None if w is None else int(w)
        # FishLab awards a misdeclared half-suit to the other team, which is
        # this project's baseline rule.
        rules = RuleConfig(wrong_distribution_outcome="opponent")
        self.rules = rules
        turn = int(state["turn"]) if turn_override is None else turn_override
        return Observation(player=seat, rules=rules, hand=hand, turn=turn,
                           hand_counts=counts, set_winner=tuple(sw),
                           history=self._history(state.get("history")))

    def _agent(self, obs):
        from fish4.registry4 import KRAKEN_V1, make_agent
        a = make_agent(KRAKEN_V1)
        # Deterministic from the public record alone, so a replayed game
        # replays identically without the host managing seeds.
        a.begin_game(obs.player, obs.rules,
                     1_000_003 + 7919 * len(obs.history) + 31 * obs.player)
        return a

    def _declaration(self, claim) -> dict:
        s = self.hs_to_set[claim.half_suit]
        owner = [0] * 6
        for j in range(6):
            owner[j] = int(claim.assignment[self._their_pos_to_our_pos(s, j)])
        return {"set": s, "owner": owner}

    # -- the four decision requests -------------------------------------
    def ask(self, req: dict) -> dict:
        from fish.engine import Ask
        obs = self.observation(req["state"])
        act = self._agent(obs).act(obs)
        if not isinstance(act, Ask):
            # FishLab asked for an ask. If the policy would rather declare it
            # has already been offered the chance in declare_poll, so falling
            # back to the best legal ask is right -- and answering the wrong
            # question is a fault, not a move.
            legal = obs.legal_asks()
            if not legal:
                return {"error": "no legal ask available"}
            act = legal[0]
        from fish.cards import card_name
        return {"action": "ask", "card": card_name(act.card),
                "target": int(act.target)}

    def declare_poll(self, req: dict) -> dict:
        """Only CERTAIN declarations, which is deliberate.

        The answer is a declaration exactly when the public record alone pins
        every card of a half-suit to a named teammate. A speculative off-turn
        declaration gambles a whole set under the award rule, and a seat that
        is merely confident can wait for its own turn and use the full policy.
        """
        from fish.beliefs import BeliefState
        from fish4.match import _deduced_claim
        obs = self.observation(req["state"])

        class _Seat:
            pass
        seat = _Seat()
        seat.bel = BeliefState(obs.rules, observer=obs.player)
        seat.bel.update(obs)
        claim = _deduced_claim(seat, obs.player, obs)
        if claim is None:
            return {"action": "none"}
        d = self._declaration(claim)
        return {"action": "declare", "confidence": 1.0, **d}

    def pass_turn(self, req: dict) -> dict:
        from fish.engine import Pass
        cands = [int(c) for c in req.get("candidates") or []]
        if not cands:
            return {"error": "pass request offered no candidates"}
        # Every offered candidate is legal BY CONSTRUCTION -- FishLab computed
        # the list. So the scored pass is an improvement on an answer we can
        # always give, and failing to consult the policy must not turn into a
        # fault that stops the game. This is the one place a fallback is
        # right: elsewhere an unanswerable request is reported, because there
        # the engine would be the judge of legality and we would be guessing.
        to = cands[0]
        try:
            obs = self.observation(req["state"])
            act = self._agent(obs).act(obs)
            if isinstance(act, Pass) and int(act.teammate) in cands:
                to = int(act.teammate)
        except Exception as e:              # noqa: BLE001
            print(f"pass: falling back to seat {to}: {type(e).__name__}: {e}",
                  file=sys.stderr, flush=True)
        return {"action": "pass", "to": to}

    def forced(self, req: dict) -> dict:
        """Answer about the half-suit asked about, and report a real number.

        The engine compares our confidence against its own sweeping threshold,
        so clamping to 1.0 would throw away the only thing it wants from us.
        And when `last_resort` is set we must answer: declining hands the
        allocation to a fallback that names every card to one seat, and it is
        recorded as OUR declaration.
        """
        from fish4.claim4 import ClaimEvaluator
        from fish4.askfeat import DecisionContext
        their_set = int(req["set"])
        hs = self.set_to_hs[their_set]
        state = req["state"]
        # `turn` is our own seat in a forced request (§6): the engine has
        # handed us the move without moving the table's turn marker.
        obs = self.observation(state, turn_override=int(state["seat"]))
        agent = self._agent(obs)
        # Build the context the way the agent itself does, rather than
        # constructing a ClaimEvaluator by hand -- an earlier version passed
        # the wrong arity here and the whole forced path failed CLOSED,
        # declining at every last resort. FishLab then books its own
        # all-to-one-seat fallback as OUR declaration.
        agent.bel.update(obs)
        post = agent.build_posterior(obs)
        ctx = DecisionContext(obs, agent.bel, post)
        ev = ClaimEvaluator(agent._claim_ctx(ctx), agent.claim_cfg)
        got = ev.best_for_half_suit(hs)
        if got is None:
            if req.get("last_resort"):
                # Never decline a last resort: the engine's fallback names
                # every card to one seat and books it as ours.
                mine = [p for p in range(6) if p % 2 == obs.player % 2]
                return {"action": "declare", "set": their_set,
                        "owner": [obs.player] * 6, "confidence": 0.0}
            return {"action": "none"}
        p_exact, _p_team, claim = got
        d = self._declaration(claim)
        thr = float(req.get("threshold", 0.0))
        if not req.get("last_resort") and p_exact < thr:
            return {"action": "none"}
        return {"action": "declare", "confidence": float(p_exact), **d}


def handle(br: Bridge, req: dict) -> dict:
    op = str(req.get("op", "")).lower()
    if op == "hello":
        return br.hello(req)
    if op == "new_game":
        br.seat = int(req.get("seat", 0))
        return {"ok": True}
    if not br.ready:
        return {"error": "no hello yet"}
    if op == "ask":
        return br.ask(req)
    if op == "declare_poll":
        return br.declare_poll(req)
    if op == "pass":
        return br.pass_turn(req)
    if op == "forced":
        return br.forced(req)
    return {"error": f"unknown op {op!r}"}


def main() -> int:
    br = Bridge()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception as e:
            out = {"error": f"unparseable request: {e}"}
        else:
            try:
                out = handle(br, req)
            except Exception as e:            # errors are data, never a hang
                out = {"error": f"{type(e).__name__}: {e}"}
        sys.stdout.write(json.dumps(out) + "\n")
        sys.stdout.flush()                     # §3: the classic first failure
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
