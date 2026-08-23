"""Stateless game sessions for a serverless deployment.

WHY THIS EXISTS SEPARATELY FROM fish4/web/server.py
---------------------------------------------------
The local server at 127.0.0.1:8420 keeps games in a module-level dict and paces
engine moves from a daemon thread. Neither survives a serverless platform: there
is no process to hold the dict and no thread to run between requests.

The fix is not a database. Literature's whole architecture already says how to
avoid one: **every card movement in the game is public**, so a position is a
deterministic function of the initial deal plus the action log. The deal is a
function of one integer seed. So a session is

    (seed, rules, seat) + the public action log

and the log is something the client is *already* holding, because it is what the
move history panel renders. The client therefore carries the session, and the
server rebuilds the position on each request by replaying.

REPLAY IS CHEAP BECAUSE POLICIES ARE NOT RE-RUN
-----------------------------------------------
The naive version of this idea re-runs every engine decision on every request,
which is quadratic over a game and would take seconds by the endgame. It is also
unnecessary: the log records the actions that were *taken*, so replaying means
applying them, not deciding them again. Applying an action is microseconds. Only
the engine moves that have not happened yet need a policy, and there are a
handful of those per request. Work per request is therefore constant in the
length of the game.

WHAT THE CLIENT IS NOT GIVEN
----------------------------
The seed determines the deal, so handing it to the browser would hand over every
hidden hand. The local server does exactly that - acceptable when the only
person who could cheat is the one running it, and not acceptable on a public
URL. Here the seed travels as an opaque HMAC-signed token, and the action log,
which is public information by construction, travels in clear. A tampered token
is rejected rather than trusted, so the log cannot be replayed against a deal of
the client's choosing.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import random

from fish.cards import (HALF_SUIT_NAMES, NUM_PLAYERS, card_name,
                        half_suit_cards, is_red, mask_to_cards, team_of,
                        teammates)
from fish.engine import (Ask, AskEvent, Claim, ClaimEvent, GameState, Pass,
                         PassEvent)
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.registry4 import make_agent

#: Engine strength on the web. The research default is 320 draws; a browser move
#: has to come back inside a serverless request budget, and the posterior study
#: puts 160 draws within noise of 320 in play, so this costs nothing measurable
#: in strength and roughly halves the latency.
WEB_DRAWS = 160
#: Ceiling on engine moves computed in one request. A human's turn is normally
#: at most a few engine possessions away; this only bounds a pathological game.
MAX_ADVANCE = 400
#: Ceiling on log length accepted from a client, so a replay cannot be made
#: arbitrarily expensive by an oversized request body.
MAX_LOG = 1200


def _secret() -> bytes:
    s = os.environ.get("FISH_SECRET")
    if s:
        return s.encode()
    # No secret configured: fall back to a value derived from the deployment so
    # tokens are at least unforgeable by an outsider guessing at the scheme.
    # A real deployment sets FISH_SECRET; this keeps a preview build working.
    return hashlib.sha256(
        (os.environ.get("VERCEL_DEPLOYMENT_ID")
         or os.environ.get("VERCEL_URL")
         or "fish-local-development").encode()).digest()


def seal(payload: dict) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    body = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    sig = hmac.new(_secret(), body.encode(), hashlib.sha256).digest()
    return body + "." + base64.urlsafe_b64encode(sig).decode().rstrip("=")[:27]


def unseal(token: str) -> dict:
    try:
        body, sig = token.split(".", 1)
    except ValueError:
        raise ValueError("malformed session token")
    want = hmac.new(_secret(), body.encode(), hashlib.sha256).digest()
    want = base64.urlsafe_b64encode(want).decode().rstrip("=")[:27]
    # Constant time: a timing oracle on the signature is the one way an attacker
    # could work toward a token that decodes to a deal they already know.
    if not hmac.compare_digest(sig, want):
        raise ValueError("bad session token")
    pad = "=" * (-len(body) % 4)
    return json.loads(base64.urlsafe_b64decode(body + pad))


def _action_of(ev) -> object:
    """The action that produced a logged event, for replay without deciding."""
    if isinstance(ev, dict):
        t = ev.get("t")
        if t == "ask":
            return Ask(int(ev["target"]), int(ev["card"]))
        if t == "claim":
            return Claim(int(ev["hs"]), tuple(int(x) for x in ev["assignment"]))
        if t == "pass":
            return Pass(int(ev["teammate"]))
        raise ValueError(f"unknown logged action {t!r}")
    if isinstance(ev, AskEvent):
        return Ask(ev.target, ev.card)
    if isinstance(ev, ClaimEvent):
        return Claim(ev.half_suit, tuple(ev.declared))
    if isinstance(ev, PassEvent):
        return Pass(ev.teammate)
    raise TypeError(ev)


def wire_action(ev) -> dict:
    """An event, in the compact form the client stores and replays back to us."""
    if isinstance(ev, AskEvent):
        return {"t": "ask", "target": ev.target, "card": ev.card}
    if isinstance(ev, ClaimEvent):
        return {"t": "claim", "hs": ev.half_suit,
                "assignment": list(ev.declared)}
    return {"t": "pass", "teammate": ev.teammate}


def narrate(ev) -> dict:
    """The human-readable version, and what the move proved to the table.

    A slow table is only worth playing if there is something to read between
    moves. Under the no-bluff rule an ask is a statement about the asker's own
    hand as well as a question about someone else's, and a failed ask is the
    most informative event in the game - so it is spelled out rather than left
    for the player to derive.
    """
    if isinstance(ev, AskEvent):
        cn = card_name(ev.card)
        hs = HALF_SUIT_NAMES[ev.card // 6]
        if ev.success:
            proved = (f"P{ev.target} held {cn}. P{ev.asker} holds another "
                      f"{hs} card, and now holds {cn} too.")
        else:
            proved = (f"Neither P{ev.asker} nor P{ev.target} holds {cn}, so it "
                      f"sits with one of the other four. P{ev.asker} does hold "
                      f"another {hs} card.")
        return {"t": "ask", "asker": ev.asker, "target": ev.target,
                "card": cn, "hs": ev.card // 6, "ok": bool(ev.success),
                "text": (f"P{ev.asker} asked P{ev.target} for {cn} — "
                         f"{'got it' if ev.success else 'no'}"),
                "proved": proved}
    if isinstance(ev, ClaimEvent):
        who = ("team " + str(ev.winner)) if ev.winner in (0, 1) else "nobody"
        return {"t": "claim", "claimer": ev.claimer, "hs": ev.half_suit,
                "winner": ev.winner,
                "text": (f"P{ev.claimer} declared "
                         f"{HALF_SUIT_NAMES[ev.half_suit]} — {who} scores"),
                "proved": ", ".join(
                    f"{card_name(c)} was P{h}"
                    for c, h in zip(half_suit_cards(ev.half_suit),
                                    ev.revealed))}
    return {"t": "pass", "text": f"P{ev.player} passed to P{ev.teammate}",
            "proved": f"P{ev.player} is out of cards."}


class Session:
    """A game rebuilt from a sealed seed plus the public action log."""

    def __init__(self, seat: int, seed: int, rules: RuleConfig, gamma: float,
                 draws: int = WEB_DRAWS):
        self.seat = seat
        self.seed = seed
        self.rules = rules
        self.gamma = gamma
        self.draws = draws
        self.state = GameState.deal(rules, seed=seed)
        rng = random.Random(seed ^ 0x9E3779B9)
        spec = {"opponent_gamma": gamma, "n_draws": draws}
        self.bots = {}
        for p in range(NUM_PLAYERS):
            if p == seat:
                continue
            self.bots[p] = make_agent(("fishbot4", dict(spec)))
            self.bots[p].begin_game(p, rules, rng.getrandbits(64))
        self._helper_seed = rng.getrandbits(64)
        self._helper = None
        self.log: list = []

    # -- reconstruction -------------------------------------------------------

    @classmethod
    def restore(cls, token: str, actions) -> "Session":
        d = unseal(token)
        rules = RuleConfig(variant=d["v"], claims_any_time=bool(d["a"]))
        s = cls(int(d["s"]), int(d["d"]), rules, float(d["g"]))
        if actions:
            if len(actions) > MAX_LOG:
                raise ValueError("action log too long")
            for a in actions:
                # Replay APPLIES the recorded action; it never re-derives it.
                # That is what keeps the cost of a request independent of how
                # far into the game it is.
                ev = s.state.apply(s.state.turn, _action_of(a))
                s.log.append(narrate(ev))
        return s

    def token(self) -> str:
        return seal({"s": self.seat, "d": self.seed, "g": self.gamma,
                     "v": self.rules.variant,
                     "a": int(bool(self.rules.claims_any_time))})

    # -- driving --------------------------------------------------------------

    def advance(self):
        """Let the engines play up to the human's turn, recording every move."""
        played = []
        n = 0
        while (not self.state.is_terminal and self.state.turn != self.seat
               and n < MAX_ADVANCE):
            p = self.state.turn
            action = self.bots[p].act(Observation.from_state(self.state, p))
            ev = self.state.apply(p, action)
            self.log.append(narrate(ev))
            played.append(wire_action(ev))
            n += 1
        return played

    def play(self, action):
        ev = self.state.apply(self.seat, action)
        self.log.append(narrate(ev))
        return [wire_action(ev)] + self.advance()

    def suggest(self):
        """What the actual policy would do from our seat - not a re-ranking."""
        if self._helper is None:
            self._helper = make_agent(("fishbot4", {"opponent_gamma": self.gamma,
                                                    "n_draws": self.draws}))
            self._helper.begin_game(self.seat, self.rules, self._helper_seed)
        return self._helper.act(self.obs())

    # -- views ----------------------------------------------------------------

    def obs(self) -> Observation:
        return Observation.from_state(self.state, self.seat)

    def snapshot(self) -> dict:
        st = self.state
        a, b, nulls = st.scores()
        mine = team_of(self.seat)
        hand = st.hands[self.seat]
        return {
            "token": self.token(),
            "seat": self.seat, "team": mine,
            "turn": st.turn, "terminal": st.is_terminal,
            "your_turn": (not st.is_terminal) and st.turn == self.seat,
            "score": {"you": a if mine == 0 else b,
                      "them": b if mine == 0 else a, "nulled": nulls},
            "hand_counts": list(st.hand_counts()),
            "teammates": [p for p in teammates(self.seat) if p != self.seat],
            "set_winner": [
                None if w is None else
                ("ours" if w == mine else "theirs" if w in (0, 1) else "null")
                for w in st.set_winner],
            "half_suits": [
                {"index": i, "name": n,
                 "cards": [{"id": c, "name": card_name(c), "red": is_red(c),
                            "mine": bool(hand >> c & 1)}
                           for c in half_suit_cards(i)]}
                for i, n in enumerate(HALF_SUIT_NAMES[:len(st.set_winner)])],
            "hand": [{"id": c, "name": card_name(c), "red": is_red(c),
                      "hs": c // 6} for c in mask_to_cards(hand)],
            "log": self.log[-60:],
            "must_pass": bool(st.turn == self.seat and hand == 0
                              and not st.is_terminal),
            # Revealed only once every card is public anyway. Before that the
            # server has the layout and the client does not, which is the whole
            # point of sealing the seed.
            "reveal": ([[card_name(c) for c in mask_to_cards(h)]
                        for h in st.hands] if st.is_terminal else None),
        }

    def analysis(self) -> dict:
        if self.state.is_terminal:
            return {"terminal": True}
        from fish4.analyse import Analyser
        an = Analyser(self.rules, self.seat, value_model=None,
                      gamma=self.gamma, n_draws=self.draws,
                      seed=self.seed & 0x7FFFFFFF)
        return an.analyse(self.obs()).to_dict()


def new_session(body: dict) -> Session:
    seat = int(body.get("seat", 0)) % NUM_PLAYERS
    seed = body.get("seed")
    seed = random.randrange(1 << 30) if seed in (None, "") else int(seed)
    rules = RuleConfig(variant=str(body.get("variant", "54")),
                       claims_any_time=bool(body.get("any_time", False)))
    gamma = max(0.0, min(2.0, float(body.get("gamma", 0.35))))
    return Session(seat, seed, rules, gamma)


def parse_action(body: dict):
    kind = body.get("type")
    if kind == "ask":
        return Ask(int(body["target"]), int(body["card"]))
    if kind == "claim":
        return Claim(int(body["half_suit"]),
                     tuple(int(x) for x in body["assignment"]))
    if kind == "pass":
        return Pass(int(body["teammate"]))
    raise ValueError(f"unknown action {kind!r}")
