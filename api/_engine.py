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
The seed determines the deal, so handing it to the browser hands over every
hidden hand: ``GameState.deal`` is deterministic and this repository is public.
The local server does hand it over - acceptable when the only person who could
cheat is the one running it, and not acceptable on a public URL.

An HMAC signature alone does not fix that. Signing authenticates a payload; it
does not conceal one, and a base64 token is readable by whoever holds it. So the
seed is not in the token. The token carries a random *nonce*, and the seed is
derived from it server-side as ``HMAC(secret, nonce)``. The client therefore
holds a value that identifies its game and reveals nothing about the deal, the
server needs no storage to recover it, and a tampered token fails its signature
rather than selecting a deal of the client's choosing.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import random
import secrets

from fish.cards import (HALF_SUIT_NAMES, NUM_PLAYERS, card_name,
                        half_suit_cards, is_red, mask_to_cards, team_of,
                        teammates)
from fish.engine import (Ask, AskEvent, Claim, ClaimEvent, GameState, Pass,
                         PassEvent)
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.registry4 import make_agent

#: Engine strength on the web.
#:
#: This was 160, on the grounds that a 200-pair cell put 320 draws "within noise"
#: of it. That cell could not have found the effect: at 200 pairs its interval
#: was half a set wide and the effect is a third of one. A pre-registered
#: 6000-pair run since measured 480 draws against 160 at +0.340 sets per
#: deal-pair, 95% CI [+0.243, +0.436] -- the largest gain in the project.
#:
#: The reason it can be taken here is that the latency argument survived the
#: correction: a decision is 3.5 ms of fixed work plus 5.8 us per draw, so
#: tripling the sampler costs +1.7 ms, not +9 (results/precision_cost.json).
#: The client asks for one move at a time, so that is invisible against a
#: serverless request budget.
WEB_DRAWS = 480

#: How many narrated log entries the snapshot carries. Named because the trace
#: rebase in _why_for_log must use the SAME number; when it was an inline 60 in
#: two places, the explanations went silent past action 60 and nothing failed.
LOG_TAIL = 60

#: The table plays the strongest configuration this project can assemble from
#: separately demonstrated parts, which is not the same as the strongest
#: measured one and should not be described as it. The belief-space lookahead is
#: worth +0.104 sets per deal-pair, 95% CI [+0.020, +0.189], over a
#: pre-registered 6000-pair run, and it costs about 6.7 ms per decision -- both
#: measured against the champion ALONE. WEB_DRAWS = 480 was demonstrated the
#: same way, also against the champion alone. Their COMBINATION, which is what
#: this table actually runs, has never been played: see
#: jobs/PREREGISTRATION_stack.md, which exists precisely because the lookahead
#: searches a belief the sampler draws and there is a specific reason the two
#: might overlap rather than add.
#:
#: Shipping the combination anyway is a deliberate choice, not an oversight. It
#: is the best available guess, both parts are independently demonstrated, and
#: the visitor is not an experiment. But the comment that used to sit here said
#: "strongest measured", and that was a claim nobody had earned.
#:
#: Deliberately NOT expressed as registry4.V04_STRONGEST: that constant carries
#: opponent_gamma, and gamma is a choice the visitor makes in the lobby. Only
#: the parts the visitor does not choose belong here.
#: The endgame ask correction. The exact solver showed the ask objective picks
#: the wrong move on 51-61% of endgame positions and that the better move is
#: almost always a RISKIER ask; raising the information term when at most two
#: half-suits are live is the one-parameter form of that, fitted against exact
#: values on games this never played. Registered, replicated, and then measured
#: again ON TOP OF the rest of this spec rather than assumed to transfer:
#: +0.1220 sets, 95% CI [+0.0711, +0.1729] over 2000 pairs against WEB_SPEC
#: without it, 15 of 16 blocks positive (results/endgame_ask_stack.json). It
#: stacks slightly LARGER on this base than on the bare champion's +0.0907.
#:
#: THEN RAISED FROM 2 TO 3. A sampled one-ply target -- posterior worlds in
#: place of an enumerated belief -- reproduces the exact target's decisions at a
#: cost of +0.0033 in its own units, so the diagnosis travels past the point
#: where exact solving stops. At m = 3 the engine's ask is beaten on 23 of 24
#: positions and the better ask is riskier on 19 of them; cross-fitting that on
#: independent samples leaves +0.2979 [+0.0966, +0.4992] after 49% of the naive
#: figure turns out to be selection bias. In play the extension is worth
#: +0.3025 sets, 95% CI [+0.2271, +0.3779] over 2000 pre-registered pairs, all
#: eight blocks positive (results/endgame_m3_verdict.json) -- two and a half
#: times what the step from m = 2 was worth. m <= 3 is 17.5% of all decisions
#: against m <= 2's 9.7%.
#: AND FROM 3 TO 4, under prereg/endgame_m_ladder.md, whose stopping rule is
#: fixed in advance: each rung duels k+1 against the shipped k, ships only on a
#: CI clear of zero, and the ladder ends at the first rung that fails. The
#: m = 4 rung: +0.6995 sets, 95% CI [+0.6033, +0.7957] over 2000 pairs, all
#: eight blocks positive (results/endgame_m4_verdict.json). The rungs are
#: GROWING -- +0.1220, +0.3025, +0.6995 -- which is itself evidence the defect
#: was never about the endgame; the ladder continues.
#: THE LADDER ABOVE m = 2 IS REVERTED, and the reason matters more than any
#: rung. Every rung was measured against the SIBLING configuration, whose
#: opponent model conditions on which half-suit a player chooses to ask.
#: Information-seeking asks systematically violate that model, so they poison
#: the sibling's inference -- and the "gains" grew with m because more of the
#: game was spent poisoning. Cross-play against v0.3, a foreign opponent with
#: different inference, on identical seeds:
#:
#:     m = 5 config vs v0.3:  -1.352 (the config wins by 1.35)
#:     m = 9 config vs v0.3:  +2.144 (v0.3 WINS by 2.14)
#:
#: The +4.2790 the m = 9 rung showed against its sibling was deception, not
#: strength -- the first demonstrated in this project, and demonstrated by
#: accident. The bare v0.4 champion beats v0.3 by +1.854, so even the m = 5
#: config may sit BELOW the pre-ladder baseline against foreign opponents; a
#: sweep maps where real strength peaks before anything above m = 2 ships
#: again. m = 2 keeps the exact-solver diagnosis, the offline fit held out by
#: game, and the exploitability check behind it, which no higher rung has.
#: Under the opponent-award baseline the endgame ask correction is
#: WITHDRAWN (endgame_m=0): fitted against void-era solver targets, it
#: re-measures at -0.1040 [-0.2184, +0.0104] against its sibling and a tie
#: against Dylan's v0.7 under the award rule (prereg/rules_award_baseline.md
#: R4 and R2), so it no longer clears the ship bar. fish4/registry4.py
#: names this configuration V06_DEPLOYED; a refit against award-rule
#: targets is queued before anything above m=0 ships again.
#: `claim_forced_exhaustive` shipped into V06_DEPLOYED on 2026-08-28
#: (prereg/forced_exhaustive.md). It is here because the site plays the
#: champion, and it is threaded into Analyser rather than listed as inert
#: because it is NOT inert at 1: it changes the split suggested for a forced
#: declaration at the last live half-suit, which is exactly the panel a player
#: is reading when it matters.
WEB_SPEC = {"w_lookahead": 0.25, "lookahead_depth": 3, "lookahead_beam": 4,
            "endgame_m": 0, "claim_forced_exhaustive": 1}
#: The opponent-model weight the champion carries. Not a knob the client can
#: turn: the site ships one engine, and this is the value every measurement in
#: the paper was taken at.
CHAMPION_GAMMA = 0.35

#: Keys of WEB_SPEC that the Analyser does not implement, and the value each
#: must hold for its absence to be harmless. A key listed here at its inert
#: value changes nothing about the policy, so an explanation built without it
#: still describes what the site plays.
_ANALYSER_INERT = {"endgame_m": 0}


def _analyser_spec() -> dict:
    """WEB_SPEC reduced to what Analyser accepts -- loudly, not silently.

    WEB_SPEC describes the POLICY the site plays. Analyser is a different class
    that EXPLAINS that policy, and it does not implement every knob: endgame_m
    arrived in WEB_SPEC with v0.6 and Analyser has never had it. Splatting the
    whole spec therefore raised TypeError on every call, api/index.py turned it
    into a 500, and the Think button, the auto-analysis checkbox, the posterior
    panel and the declare dialog's suggested split were all dead on the live
    site until an audit caught it. No test covered the path.

    Dropping unknown keys silently would be the worse bug. An explanation of a
    policy the site is not playing is a lie the page tells confidently, and
    endgame_m is queued to ship non-zero once it is refit against award-rule
    targets. So a key may be dropped only while it sits at its inert value;
    anything else raises here, where it is one obvious failure, rather than
    showing a plausible wrong panel there.
    """
    import inspect

    from fish4.analyse import Analyser
    accepted = set(inspect.signature(Analyser.__init__).parameters)
    out, dropped = {}, {}
    for k, v in WEB_SPEC.items():
        (out if k in accepted else dropped)[k] = v
    for k, v in dropped.items():
        if k not in _ANALYSER_INERT:
            raise RuntimeError(
                f"WEB_SPEC key {k!r} is not accepted by Analyser and is not "
                f"registered as inert; the site would explain a policy it is "
                f"not playing. Add it to Analyser or to _ANALYSER_INERT.")
        if v != _ANALYSER_INERT[k]:
            raise RuntimeError(
                f"WEB_SPEC sets {k}={v!r}, but Analyser cannot represent it "
                f"and it is only harmless at {_ANALYSER_INERT[k]!r}. The "
                f"analysis would describe a different policy than the one "
                f"playing. Teach Analyser this knob before shipping it.")
    return out
#: Ceiling on engine moves computed in one request. A human's turn is normally
#: at most a few engine possessions away; this only bounds a pathological game.
MAX_ADVANCE = 400
#: Ceiling on log length accepted from a client, so a replay cannot be made
#: arbitrarily expensive by an oversized request body.
MAX_LOG = 1200


#: Used when FISH_SECRET is unset. Random per process, deliberately: the
#: obvious fallbacks are all things an attacker can read. VERCEL_URL is in the
#: address bar, and a secret derived from it is not a secret - it would let
#: anyone derive every deal.
#:
#: Note this is per PROCESS, not per cold start: two concurrently warm instances
#: sign with different keys, so with FISH_SECRET unset a game dies on the first
#: request that happens to land on a different instance, not merely at recycle
#: time. Verification is fail-closed, so that is availability rather than
#: confidentiality - but it makes the deployment barely usable. Set FISH_SECRET.
_EPHEMERAL_SECRET = secrets.token_bytes(32)


#: Below this, a deploy-time secret is worth less than the random fallback: the
#: attacker gets an oracle from any one token they hold, and can grind it
#: offline. Refusing a short value is better than honouring it.
MIN_SECRET_BYTES = 16


def _secret() -> bytes:
    s = os.environ.get("FISH_SECRET")
    if s and len(s.encode()) >= MIN_SECRET_BYTES:
        return s.encode()
    return _EPHEMERAL_SECRET


def seed_from_nonce(nonce: str) -> int:
    """The deal for a game, recovered from its public nonce.

    Deterministic given the secret, so the server never stores a seed; and
    opaque without it, so the nonce the client carries says nothing about the
    hands. Domain-separated from the signature so the same key cannot be made to
    serve both purposes.
    """
    # The full digest, NOT truncated. seed -> deal is public deterministic code
    # (random.Random(seed).shuffle(deck)), so a small seed space is enumerable
    # offline regardless of the key: at 2**30 there are fewer seeds than there
    # are 9-card hands, so the nine cards the protocol legitimately hands a
    # player pin their own deal uniquely, and a precomputed seed->hands table
    # would break every past and future game and survive rotating FISH_SECRET.
    d = hmac.new(_secret(), b"fish-deal:" + nonce.encode(), hashlib.sha256).digest()
    return int.from_bytes(d, "big")


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
    if not sig.isascii():
        # compare_digest raises TypeError on non-ASCII str, which would escape
        # the ValueError contract this function promises its callers.
        raise ValueError("malformed session token")
    want = hmac.new(_secret(), body.encode(), hashlib.sha256).digest()
    want = base64.urlsafe_b64encode(want).decode().rstrip("=")[:27]
    # Constant time: a timing oracle on the signature is the one way an attacker
    # could work toward a token that decodes to a deal they already know.
    if not hmac.compare_digest(sig, want):
        # Either the token was tampered with, or the signing key changed under
        # it - which is what a cold start does when FISH_SECRET is unset. The
        # two are indistinguishable here and the remedy is the same, so the
        # message is written for the player rather than for the attacker.
        raise ValueError("this game has expired - start a new one")
    pad = "=" * (-len(body) % 4)
    return json.loads(base64.urlsafe_b64decode(body + pad))


def log_hash(actions) -> str:
    """A commitment to the exact action log, for sealing into the token.

    THE HOLE THIS CLOSES
    --------------------
    Sealing the session without sealing the log authenticates *which game* a
    client is playing and nothing about *what happened in it*. Replay applies
    whatever list arrives, and a claim resolves against the true hands and
    reports the holders - which is correct, because a resolved claim is public.
    So a client could post its own valid token with a fabricated log of nine
    claims and read all 54 card locations out of the response. Because the
    function is stateless the fabrication is never persisted: the attacker
    discards the reply and plays the same deal on with perfect information.

    Binding the log costs one hash and no storage, because the token already
    round-trips on every response.

    WHAT THIS DOES **NOT** CLOSE, STATED PLAINLY
    -------------------------------------------
    An earlier version of this docstring said binding the log "also closes the
    take-back: a truncated log no longer verifies, so a bad move cannot be
    replayed away". That is true only of a FORGED log, and it is the more
    comfortable half of the truth.

    Every response hands the client a freshly signed token for the position it
    describes. A client that KEEPS an old token together with the honest log
    that matched it holds a legitimately signed earlier position, and no
    stateless check can refuse it -- the pair verifies because it really was
    issued. Rolling back is therefore not prevented, and the same reasoning
    reopens the peeking oracle through the front door: a declaration is legal
    on any unresolved half-suit whether or not the declarer holds a card in it
    (fish/engine.py has no holding requirement for Claim, unlike Ask), and
    resolving one reveals the true holders, correctly, because a resolved
    declaration is public. Nine restores of one saved pair, each declaring a
    different half-suit and each discarded, read off all 54 card locations
    while the real game stays at ply 0. Reproduced at this layer; see
    tests4/test_web_security.py.

    TWO CONSEQUENCES, NEITHER OF THEM A PATCH
    -----------------------------------------
    For the game: this is a single player against five bots, so the only
    person cheated is the one doing it. That is why it is documented rather
    than treated as an emergency.

    For the RESEARCH, which matters more: transcripts collected from the
    public site are not evidence of honest play and must not be used as
    human-play data. This bears directly on refitting the choice model on the
    deployed population -- a population that can rewind is not the population
    the model would be claiming to describe.

    The real fix needs memory the deployment does not have: one
    nonce -> highest-log-length-seen row, rejecting any token whose log is
    shorter than the longest already observed. That is a single column in the
    same store multiplayer rooms are already blocked on, and it should be
    built when that store exists rather than approximated now.
    """
    raw = json.dumps(actions or [], separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


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
        ct = team_of(ev.claimer)
        # The two ways to be wrong, and they are not the same mistake. The
        # research ledger this mirrors measures them apart because they have
        # different causes: an ALLOCATION error means the claimer's own team
        # held all six and misordered them, and is a failure of placement; an
        # OWNERSHIP error means an opponent still held one, and is a failure
        # of reading the table. Between engines they run 0.268 and 0.650 a
        # game respectively (results/margin_decomposition.json), so a player
        # who only ever sees "wrong" is being shown the smaller half of what
        # went wrong.
        if ev.winner == ct:
            klass = "right"
        elif all(team_of(h) == ct for h in ev.revealed):
            klass = "split"
        else:
            klass = "ownership"
        return {"t": "claim", "claimer": ev.claimer, "hs": ev.half_suit,
                "winner": ev.winner, "klass": klass,
                "declared": [int(h) for h in ev.declared],
                "revealed": [int(h) for h in ev.revealed],
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

    def __init__(self, seat: int, nonce: str, rules: RuleConfig, gamma: float,
                 draws: int = WEB_DRAWS, mode: str = "play"):
        #: "play" seats a human; "spectate" seats nobody -- all six seats are
        #: engines and the client only steps and watches. Spectate is the 3v3
        #: exhibition: Dylan's FishBot v0.7 (github.com/dylann4500/fishbot,
        #: bridged in fish4/dylan_v07.py) on the even seats, this project's
        #: engine on the odd ones. seat is -1 there, which advance() already
        #: treats correctly (no turn ever equals -1, so the engines just play);
        #: everything that would read hands[seat] has to guard it instead,
        #: because Python would silently serve seat 5's hand for -1.
        self.mode = mode
        self.seat = seat if mode == "play" else -1
        self.nonce = nonce
        #: Never sent anywhere. Derived here and used here.
        seed = self.seed = seed_from_nonce(nonce)
        self.rules = rules
        self.gamma = gamma
        self.draws = draws
        self.state = GameState.deal(rules, seed=seed)
        rng = random.Random(seed ^ 0x9E3779B9)
        spec = dict(WEB_SPEC, opponent_gamma=gamma, n_draws=draws)
        self.bots = {}
        for p in range(NUM_PLAYERS):
            if p == self.seat:
                continue
            if mode == "spectate" and p % 2 == 0:
                self.bots[p] = make_agent(("dylan_v07", {}))
            else:
                # Decision traces are captured ONLY in the exhibition. They
                # carry the bot's ranked candidates and its confidence, which
                # is derived from public events plus THAT SEAT'S OWN HAND -- so
                # handing one to a seated human would leak across the
                # information boundary the whole engine is built to respect.
                # In spectate every seat is a bot and nobody has a hand to
                # protect, which is exactly why the exhibition is the place to
                # show reasoning. tests4/test_web_security.py pins this.
                self.bots[p] = make_agent(
                    ("fishbot4", dict(spec, **({"trace": True}
                                               if mode == "spectate" else {}))))
            self.bots[p].begin_game(p, rules, rng.getrandbits(64))
        self._helper_seed = rng.getrandbits(64)
        self._helper = None
        self.log: list = []
        #: card -> the seat that held it, learned as claims resolve. The end of
        #: game cannot be reconstructed from ``state.hands``: terminal means
        #: every half-suit is resolved, and resolving one strips its cards from
        #: every hand, so at terminal the hands are all empty by construction
        #: and a reveal built from them is six empty lists.
        self.revealed: dict[int, int] = {}
        #: wire_log index -> why the bot at that index moved as it did.
        #: Spectate only, and rebuilt per request rather than sealed into the
        #: token: a trace is an explanation of a decision, and a decision that
        #: is being REPLAYED was not made again, so there is nothing honest to
        #: say about it. Only moves generated inside the current request carry
        #: one, which is also why the token stays exactly as it was.
        self.traces: dict[int, dict] = {}
        #: The wire form of every action so far, in order. What the token
        #: commits to, and what the client is expected to send back verbatim.
        self.wire_log: list = []

    # -- reconstruction -------------------------------------------------------

    @classmethod
    def restore(cls, token: str, actions) -> "Session":
        d = unseal(token)
        # starting_player is NOT a separate token field: it is the seated
        # player, which the token already carries as "s". Deriving it here
        # rather than defaulting keeps restore() building the same game
        # new_session() dealt -- a RuleConfig whose starting_player disagreed
        # with the original would put the wrong seat on turn at ply 0, and the
        # first replayed action would then be applied to the wrong player. That
        # fails loudly (IllegalAction) for most logs and, worse, quietly for a
        # log whose first action happens to be legal for both seats.
        mode = d.get("m", "play")
        # A spectate token has no human seat, so the game starts at seat 0;
        # deriving starting_player from -1 would deal seat 5 in on the move.
        start = 0 if mode == "spectate" else int(d["s"]) % NUM_PLAYERS
        # "w" seals the misdeclaration rule into the token so a replay is
        # scored under the rules the game was actually played under, not
        # whatever this deploy's default happens to be. Tokens minted before
        # the field existed were void-era games; they default to "null" so
        # their in-flight scores do not jump mid-game across the deploy.
        rules = RuleConfig(variant=d["v"], claims_any_time=bool(d["a"]),
                           starting_player=start,
                           wrong_distribution_outcome=d.get("w", "null"))
        if log_hash(actions) != d.get("h"):
            # Either the log was altered or it belongs to another game. Both are
            # unrecoverable by retrying, and the two are not worth telling apart
            # for an attacker's benefit.
            raise ValueError("this game has expired - start a new one")
        s = cls(int(d["s"]), str(d["n"]), rules, float(d["g"]),
                mode=d.get("m", "play"))
        if actions:
            if len(actions) > MAX_LOG:
                raise ValueError("action log too long")
            s.wire_log = list(actions)
            for a in actions:
                # Replay APPLIES the recorded action; it never re-derives it.
                # That is what keeps the cost of a request independent of how
                # far into the game it is.
                ev = s.state.apply(s.state.turn, _action_of(a))
                s.log.append(narrate(ev))
                # Replay must rebuild the reveal map too. Every request
                # restores from the token, so without this `revealed` holds
                # only what happened to resolve inside the current request --
                # and the end-of-game panel that shows where each half-suit's
                # cards actually were came back empty on any refresh, which is
                # the one moment a player most wants to check their reading.
                s.note_reveal(ev)
        return s

    def token(self) -> str:
        return seal({"s": self.seat, "n": self.nonce, "g": self.gamma,
                     "v": self.rules.variant,
                     "a": int(bool(self.rules.claims_any_time)),
                     "w": self.rules.wrong_distribution_outcome,
                     "m": self.mode,
                     "h": log_hash(self.wire_log)})

    # -- driving --------------------------------------------------------------

    def advance(self, max_moves: int = MAX_ADVANCE):
        """Let the engines play, recording every move.

        ``max_moves`` stops after that many engine moves rather than running to
        the human's turn. That is what lets the table be paced: a move a client
        never saw arrive is a move the player cannot read, and an engine's whole
        possession delivered as one jump is exactly the thing the local server
        spent a daemon thread avoiding. Here the client asks for one move at a
        time and does the waiting itself, which costs a request per move and no
        server state at all.
        """
        played = []
        n = 0
        cap = min(int(max_moves), MAX_ADVANCE)
        while (not self.state.is_terminal and self.state.turn != self.seat
               and n < cap):
            p = self.state.turn
            action = self.bots[p].act(Observation.from_state(self.state, p))
            ev = self.state.apply(p, action)
            self.log.append(narrate(ev))
            self.note_reveal(ev)
            w = wire_action(ev)
            played.append(w)
            self.wire_log.append(w)
            # Keyed by position in wire_log so the client can line a trace up
            # with the move it explains without the two lists having to stay
            # the same length -- only some seats are traced.
            tr = getattr(self.bots[p], "last_trace", None)
            if tr is not None:
                self.traces[len(self.wire_log) - 1] = dict(tr, seat=p)
            n += 1
        return played

    def play(self, action, max_moves: int = MAX_ADVANCE):
        ev = self.state.apply(self.seat, action)
        self.log.append(narrate(ev))
        self.note_reveal(ev)
        w = wire_action(ev)
        self.wire_log.append(w)
        return [w] + self.advance(max_moves)

    def suggest(self):
        if self.mode == "spectate":
            raise ValueError("no suggestions in spectate mode")
        """What the actual policy would do from our seat - not a re-ranking."""
        if self._helper is None:
            self._helper = make_agent(
                ("fishbot4", dict(WEB_SPEC, opponent_gamma=self.gamma,
                                  n_draws=self.draws)))
            self._helper.begin_game(self.seat, self.rules, self._helper_seed)
        return self._helper.act(self.obs())

    # -- views ----------------------------------------------------------------

    def note_reveal(self, ev) -> None:
        """Record where a resolved half-suit's cards actually were."""
        if isinstance(ev, ClaimEvent):
            for c, holder in zip(half_suit_cards(ev.half_suit), ev.revealed):
                self.revealed[c] = holder

    def _reveal_rows(self) -> list:
        """Where each card sat as its half-suit resolved, one list per seat.

        One builder for both modes. They used to differ -- spectate sent an
        empty dict -- and since `{}` is truthy in JS the client walked it as an
        array and threw at every game over.
        """
        return [[card_name(c) for c in sorted(self.revealed)
                 if self.revealed[c] == p] for p in range(NUM_PLAYERS)]

    def _declarations(self) -> list:
        """Every declaration in the game, in order, whatever the log tail is.

        The log the client is sent is the last LOG_TAIL actions, which in a
        long game drops the early half-suits -- and a ledger with the first
        three declarations missing is worse than no ledger, because it reads
        as a complete one. `self.log` holds the whole narrated history on the
        server, so the ledger is filtered from that rather than from the
        slice.

        No new information: a declaration is public the moment it resolves,
        and every row here was already on the wire when it happened.
        """
        return [r for r in self.log if r.get("t") == "claim"]

    def _ask_tally(self) -> list:
        """Asks and hits per seat, over the WHOLE game, not the log tail.

        Same reason `_declarations` reads `self.log` rather than the slice the
        client is sent, and here the gap is larger: a game runs about a
        hundred asks against a sixty-action tail, so a client-side tally would
        miss roughly the first half of them and present the remainder as the
        total. A hit rate computed over an unmarked subset of the asks is
        worse than no hit rate.

        No new information. Every ask and its outcome was public when it
        happened and was already on the wire; this only spares the client from
        having to have kept it.
        """
        out = [[0, 0] for _ in range(NUM_PLAYERS)]
        for r in self.log:
            if r.get("t") == "ask":
                a = r.get("asker")
                if isinstance(a, int) and 0 <= a < NUM_PLAYERS:
                    out[a][0] += 1
                    if r.get("ok"):
                        out[a][1] += 1
        return out

    def _why_for_log(self) -> dict:
        """Traces rebased onto the log slice the client is actually sent.

        ``self.traces`` is keyed by ABSOLUTE action index, which is the only
        stable key on the server. The snapshot ships ``self.log[-LOG_TAIL:]``,
        so past LOG_TAIL actions the two numberings drift apart by exactly the
        amount trimmed -- and a trace keyed past the end of the list silently
        renders nothing, in the one feature whose whole argument is that a
        misattributed explanation is worse than none. Measured before the fix:
        at 63 actions the keys were 60, 61, 62 against a 60-entry list.

        Rebasing here rather than on the client keeps the wire format honest:
        an index in the payload indexes the payload.
        """
        offset = max(0, len(self.log) - LOG_TAIL)
        out = {}
        for k, v in self.traces.items():
            i = k - offset
            if 0 <= i < LOG_TAIL:
                out[str(i)] = v
        return out

    def obs(self) -> Observation:
        return Observation.from_state(self.state, self.seat)

    def snapshot(self) -> dict:
        st = self.state
        a, b, nulls = st.scores()
        if self.mode == "spectate":
            # No seat, no hand, no perspective: the spectator sees the public
            # table. score.you is Dylan's team (the even seats) so the client
            # can caption the two columns by bot name rather than by "you".
            snap = {
                "token": self.token(),
                "seat": -1, "team": None, "spectate": True,
                "turn": st.turn, "terminal": st.is_terminal,
                "your_turn": False,
                "score": {"you": a, "them": b, "nulled": nulls},
                "hand_counts": list(st.hand_counts()),
                "teammates": [],
                # Why our seats moved as they did, keyed by position in the
                # log AS SENT. Present only in the exhibition, and only for
                # moves generated in THIS request: a replayed move was not
                # decided again, so there is nothing honest to say about it.
                "why": self._why_for_log(),
                "set_winner": [
                    None if w is None else
                    ("ours" if w == 0 else "theirs" if w == 1 else "null")
                    for w in st.set_winner],
                "half_suits": [
                    {"index": i, "name": n,
                     "cards": [{"id": c, "name": card_name(c),
                                "red": is_red(c), "mine": False}
                               for c in half_suit_cards(i)]}
                    for i, n in enumerate(
                        HALF_SUIT_NAMES[:len(st.set_winner)])],
                "hand": [],
                "log": self.log[-LOG_TAIL:],
                "must_pass": False,
            }
            if st.is_terminal:
                # The SAME shape play mode sends: six lists, one per seat.
                # This was an empty dict, and `{}` is truthy in JS, so the
                # client's `if (s.reveal) s.reveal.forEach(...)` threw at every
                # game over -- which broke the exhibition loop, because the
                # throw escaped pace()'s catch and watchGameOver() never ran.
                # The series tally froze and the next deal never started.
                # It can carry the real thing now that restore() rebuilds the
                # reveal map, so the exhibition gets the panel too.
                snap["reveal"] = self._reveal_rows()
                snap["declarations"] = self._declarations()
                snap["ask_tally"] = self._ask_tally()
            return snap
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
            "log": self.log[-LOG_TAIL:],
            "must_pass": bool(st.turn == self.seat and hand == 0
                              and not st.is_terminal),
            # Revealed only once every card is public anyway. Before that the
            # server has the layout and the client does not, which is the whole
            # point of sealing the seed.
            "reveal": self._reveal_rows() if st.is_terminal else None,
            "declarations": (self._declarations()
                             if st.is_terminal else None),
            "ask_tally": self._ask_tally() if st.is_terminal else None,
        }

    def deductions(self) -> dict:
        """What the PUBLIC RECORD alone proves, from this seat's chair.

        This is the one thing the table can hand a player that is not the
        engine's opinion: a derivation they could have made themselves, from
        facts everyone at the table saw. It is therefore not a hint and not a
        leak -- BeliefState(observer=seat) is fed only public events plus this
        seat's own hand, which is exactly the information boundary the whole
        engine is built around.

        Two deliberate omissions. It carries NO probabilities: the analysis
        panel already does estimates, and mixing a proof with a guess in one
        list teaches a player to trust them equally. And it reports only what
        the propagator actually proved, which is a subset of what is provable
        -- so the payload says how many cards remain unresolved rather than
        implying the list is complete.
        """
        if self.mode == "spectate":
            # obs() at seat -1 would quietly build seat 5's view, which is the
            # same trap analysis() guards against. A spectator proof sheet is
            # worth having and needs a public-only observer that does not
            # exist yet; refusing is better than answering as seat 5.
            raise ValueError("no deductions in spectate mode")
        from fish.beliefs import BeliefState

        bel = BeliefState(self.rules, observer=self.seat)
        obs = self.obs()
        bel.update(obs)
        hands = bel.known_current_hands()
        proved = [{"player": p,
                   "cards": sorted(card_name(c) for c in mask_to_cards(hands[p]))}
                  for p in range(NUM_PLAYERS)
                  if p != self.seat and hands[p]]
        at_least_one = [
            {"player": p, "cards": [card_name(c) for c in cards]}
            for cards, p in bel.ors[:12] if p != self.seat]
        unresolved = 0
        for hs, w in enumerate(obs.set_winner):
            if w is not None:
                continue
            for c in half_suit_cards(hs):
                m = bel.current_holder_mask(c)
                if m and m & (m - 1):
                    unresolved += 1
        return {"proved": proved, "at_least_one": at_least_one,
                "n_proved": sum(len(r["cards"]) for r in proved),
                "n_unresolved": unresolved}

    def claim_check(self, half_suit: int, assignment: list) -> dict:
        """Price the split the PLAYER built, before they commit to it.

        Two numbers, and the difference between them is the whole lesson.
        `p_exact` is the probability this precise assignment is right;
        `p_team` is the probability our team holds all six however they are
        split. A player who has those confused declares a half-suit they own
        and hands it away on the ordering -- which is not a hypothetical:
        allocation-class errors are 0.255 a game between engines, and the
        engine's own doomed-ask gate was found reading p_exact while ignoring
        p_team (prereg/stuck_claim_gate.md).

        NOT A LEAK, and the argument is worth stating because it is the one
        thing that could make this route dangerous. The posterior is a
        deterministic function of THIS SEAT'S observation -- BeliefState is
        fed public events plus this seat's own hand and nothing else -- so
        querying it, in any pattern and any number of times, returns a
        function of information the client already holds. A joint is more than
        the marginals the client already receives in `card_table`, but it is
        more of the same estimate, not more of the truth. What it cannot do is
        distinguish two worlds this seat cannot legally distinguish.

        The engine's own answer is returned alongside, and the client is
        responsible for not showing it until the player has committed. That
        ordering is a teaching decision, not a security one; anyone reading
        the wire can see both.
        """
        if self.mode == "spectate":
            raise ValueError("no claim check in spectate mode")
        if self.state.is_terminal:
            return {"terminal": True}
        hs = int(half_suit)
        obs = self.obs()
        if not (0 <= hs < len(obs.set_winner)) or obs.set_winner[hs] is not None:
            raise ValueError("that set is already resolved")
        cards = list(half_suit_cards(hs))
        owners = [int(x) for x in assignment]
        if len(owners) != len(cards):
            raise ValueError(f"expected {len(cards)} owners, got {len(owners)}")
        team = {p for p in range(NUM_PLAYERS) if p % 2 == self.seat % 2}
        for q in owners:
            if q not in team:
                # A declaration names only your own team; the engine would
                # reject it too, and saying so beats returning 0.0 as though
                # it were a probability.
                raise ValueError("every card must be assigned to your own team")

        from fish4.analyse import Analyser
        an = Analyser(self.rules, self.seat, value_model=None,
                      gamma=self.gamma, n_draws=self.draws,
                      seed=self.seed & 0x7FFFFFFF, **_analyser_spec())
        ctx = an.context(obs)
        from fish4.claim4 import ClaimConfig, ClaimEvaluator
        cfg = ClaimConfig()
        yours = float(ctx.post.prob_assignment(cards, owners))
        # the SAME enumeration cap the evaluator uses, so the two p_team
        # figures on screen are the same quantity and not two estimates of it
        team_all = float(ctx.post.prob_all_with(cards, sorted(team),
                                                cfg.max_enumerate))
        r = ClaimEvaluator(ctx, cfg).best_for_half_suit(hs)
        engine = None
        if r is not None:
            theirs = [int(x) for x in r[2].assignment]
            # RE-PRICE the engine's split through the same call, rather than
            # quoting the number it returned. `best_for_half_suit` has two
            # tiers: when the team enumeration exceeds its cap it returns a
            # PRODUCT of per-card marginals, which at the opening it always
            # does. That figure is fine where it is used, because there both
            # halves of the pair are products and stay internally consistent
            # -- but putting it beside an exact joint on the same screen would
            # be two methods wearing one label. Whatever this panel shows, it
            # shows computed one way.
            engine = {"p_exact": round(
                          float(ctx.post.prob_assignment(cards, theirs)), 4),
                      "assignment": theirs,
                      "same": theirs == owners}
        # `prob_assignment` returns exactly 0.0 whenever some card cannot be
        # where the split puts it. That is a PROOF, not a small estimate, and
        # it is the most useful thing this route can say. Reporting it here
        # rather than letting the client infer it from a rounded float is the
        # difference between "unlikely" and "you can see that it is wrong".
        #
        # `public_loc` alone is not enough and the live page proved it: at the
        # opening nothing has moved in public, so every card's `public_loc` is
        # None while the candidate masks already rule most splits out -- most
        # obviously a card in the player's OWN hand assigned to a teammate.
        # `current_holder_mask` is the propagator's full answer and is the
        # same one the proof sheet reads.
        # Which of the six the public record PINS, and which are guesses.
        #
        # This is the distinction the whole allocation problem turns on and it
        # is not visible anywhere on the page. Of the misplaced cards in the
        # disclosure probe, 398 of 398 were cards that had never moved in
        # public (results/margin_decomposition.json): once a team holds all six
        # of a half-suit no opponent may legally ask in it, so nothing further
        # can ever locate the rest, and the split is frozen with exactly the
        # cards that were dealt and never asked for still unknown.
        #
        # A player looking at six dropdowns cannot tell which three of them
        # they are actually choosing. Saying so is not a hint -- a pinned card
        # is pinned BY THE PUBLIC RECORD, derivable by anyone at the table from
        # events they all saw, which is the same boundary `deductions` sits on.
        pinned, free = [], []
        refuted = []
        for c, want in zip(cards, owners):
            try:
                m = ctx.bel.current_holder_mask(c)
            except Exception:
                m = None
            if m and not (m & (m - 1)):
                pinned.append({"card": card_name(c),
                               "player": m.bit_length() - 1})
            else:
                free.append(card_name(c))
            if m and not (m >> want & 1):
                mine = bool(obs.hand >> c & 1)
                if mine:
                    why = "you are holding it yourself"
                elif want == self.seat:
                    why = "it is not in your hand"
                else:
                    why = "the public record places it elsewhere"
                refuted.append({"card": card_name(c), "why": why})
        return {"half_suit": hs, "assignment": owners,
                "p_exact": round(yours, 6), "p_team": round(team_all, 6),
                "impossible": bool(refuted), "refuted": refuted,
                "pinned": pinned, "free": free,
                "engine": engine}

    def analysis(self) -> dict:
        if self.mode == "spectate":
            # There is no "you" to analyse for, and obs() at seat -1 would
            # quietly build seat 5's view.
            raise ValueError("no analysis in spectate mode")
        if self.state.is_terminal:
            return {"terminal": True}
        from fish4.analyse import Analyser
        an = Analyser(self.rules, self.seat, value_model=None,
                      gamma=self.gamma, n_draws=self.draws,
                      seed=self.seed & 0x7FFFFFFF, **_analyser_spec())
        return an.analyse(self.obs()).to_dict()


def new_session(body: dict) -> Session:
    """A fresh game. The client does not get to choose the deal.

    The local server accepts a seed so a position can be reproduced while
    debugging. Honouring that here would let anyone pick a deal they had already
    solved offline, which is the whole thing the nonce exists to prevent, so the
    field is ignored rather than trusted.

    THE CLIENT ALSO DOES NOT CHOOSE THE ENGINE OR THE DECK any more, and the
    reason is worth stating because it removes options rather than adding them.

    The deck was offered as 54 or 48. Every number in the paper, every
    pre-registered run and every calibration table is measured on the 54-card
    variant; the 48-card arm exists in ``fish.rules`` for the rule-variant
    robustness study and has no tuning, no verdict and no claim behind it.
    Offering it as a peer choice implied a parity that was never measured.

    The engine was offered as gamma 0 ("reads only the rules") against gamma
    0.35 ("reads your asks"). That is a strength selector whose weak arm is
    worth -1.9 sets per deal-pair, so it was a button that made the opponent
    worse for no stated reason. One engine ships: the configuration in
    ``WEB_SPEC`` at ``WEB_DRAWS`` draws with the champion's gamma, which is the
    only configuration this project has measured directly against the reference
    (+0.357 sets per deal-pair, 2000 pre-registered pairs).

    ``starting_player`` is the human's seat. A player who deals in and
    immediately watches four engine possessions has to reconstruct the tracking
    from a log; starting them on the move means the game begins with a decision
    they made.
    """
    if body.get("mode") == "spectate":
        # The 3v3 exhibition: Dylan's FishBot v0.7 on seats 0/2/4, this
        # project's engine on 1/3/5, nobody dealt in. The deal is still the
        # server's nonce -- a spectator does not pick the deck either.
        # The misdeclaration rule is pinned rather than inherited so the
        # site's rule is audit-visible here and immune to library-default
        # drift: a misdeclared set is the other team's set.
        rules = RuleConfig(variant="54", starting_player=0,
                           wrong_distribution_outcome="opponent")
        return Session(-1, secrets.token_urlsafe(12), rules, CHAMPION_GAMMA,
                       mode="spectate")
    seat = int(body.get("seat", 0)) % NUM_PLAYERS
    rules = RuleConfig(variant="54", starting_player=seat,
                       wrong_distribution_outcome="opponent")
    return Session(seat, secrets.token_urlsafe(12), rules, CHAMPION_GAMMA)


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
