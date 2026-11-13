"""Poker-style tables: public quick play, private join codes, and a turn clock.

WHY A SECOND MODULE RATHER THAN AN EDIT OF _room_game
-----------------------------------------------------
The room in ``_room_game`` fixes every seat as person or bot when the table is
made, and deals only when every person has pressed ready. Both are right for
friends arranging a game and wrong for strangers matched by quick play, who
arrive one at a time and cannot be waited on forever. A table here has OPEN
seats that anyone can take while it is seating, and it deals when the host says
so -- or, for a public table, when its countdown runs out -- with every seat
still open becoming a bot.

The existing room routes, their client and their tests are untouched. Both kinds
of document live in the same store; a table is marked ``kind: "table"``.

THE CLOCK RUNS ON BEING LOOKED AT
---------------------------------
There is no process between requests on serverless, so nothing can fire at the
instant a timer expires. Instead every poll from anyone at the table checks the
clock and, if it has run out, makes the move then. Clients poll about once a
second, so a 20-second clock expires within about a second of 20 seconds. The
deadlines are stored as absolute times and each client draws its own countdown
from them, so every seat sees the same clock.

Each person also has a TIME BANK, as in a poker room: when their turn clock runs
out the bank starts draining, and only when that is empty too does the table
move for them. The bank is per game, so a long declaration costs once.

WHAT A TIMEOUT DOES
-------------------
The engine plays the move for them, using ``Session.suggest`` from THEIR seat --
decided only from what that seat could see -- so a timeout never plays with
knowledge the player did not have. Two timeouts in a row marks the seat away,
and an away seat is played at bot speed until its owner says they are back. A
person who stops polling altogether is treated the same way on their turn,
because a table of five must not wait on a phone in somebody's pocket.

THE INFORMATION BOUNDARY IS THE ROOM'S
--------------------------------------
Every per-seat view is ``Session.snapshot`` from that seat, the same definition
the solo build and the room build use. The document's nonce derives every hand
and never leaves the server; the public lobby list is reduced to names and seat
counts before it is returned.
"""

from __future__ import annotations

import secrets
import time

from fish.cards import NUM_PLAYERS, team_of
from fish.rules import RuleConfig

from api import _fairplay as F
from api._engine import CHAMPION_GAMMA, Session, _action_of, narrate
from api._rooms import Conflict, NotFound, clean_name, store

KIND = "table"

#: Turn clock choices, in seconds. 0 is "no limit", offered on private tables
#: only: a public table cannot let one stranger hold five others hostage.
TURN_CHOICES = (10, 15, 20, 30, 45, 60, 90)
TURN_DEFAULT = 20
#: Seconds of time bank per person per game, drawn only after the clock ends.
BANK_SECONDS = 30.0
#: Seconds between engine moves, so a person can follow what the bots do.
PACE_CHOICES = {"fast": 0.9, "normal": 1.6, "slow": 3.0}
PACE_DEFAULT = "normal"

#: Consecutive timeouts before a seat is marked away and played at bot speed.
AWAY_AFTER = 2
#: A seated person's poll refreshes their presence at most this often, so a
#: table of six polling every second writes a handful of times a minute rather
#: than six times a second.
SEEN_EVERY = 8.0
#: Not seen for this long while seating: the seat is freed for someone else.
GONE_LOBBY_PUBLIC = 30.0
GONE_LOBBY_PRIVATE = 60.0
#: Not seen for this long while playing: their turn is played at bot speed.
GONE_PLAYING = 25.0

#: A public table deals this long after it opens, filling with bots, so nobody
#: waits on an empty lobby forever.
PUBLIC_WAIT = 30.0
#: Someone joining a public table near its deadline gets at least this long to
#: look at it, but the whole wait is capped.
PUBLIC_JOIN_GRACE = 12.0
PUBLIC_MAX_WAIT = 90.0

#: Moves of history a seat is SENT. Fish is a memory game: who asked whom for
#: what is public when it happens, and keeping track of it is the skill. So a
#: table shows the last two moves and no more -- enforced here, in what the
#: server sends, because a limit that only the client applied would be one
#: line of devtools away from a full transcript. The end of the game still
#: gets its full ledger (declarations, reveal, ask tally): it is over.
HISTORY_VISIBLE = 2

#: Preset reactions. No free text, on purpose: open chat between strangers is
#: user-generated content, which an App Store build would then need reporting,
#: blocking and moderation for.
EMOTES = ("thumbs", "laugh", "wow", "angry", "fish", "gg", "nice", "think",
          "cry", "fire", "clap", "eyes")
EMOTE_GAP = 1.5
EMOTE_SHOW = 4.0

#: Seats filled in this order on a PRIVATE table, so a group that turns up
#: together sits together ({0,2,4} is one team). Public tables alternate teams
#: instead, so strangers are spread evenly.
PRIVATE_ORDER = (0, 2, 4, 1, 3, 5)
PUBLIC_ORDER = (0, 1, 2, 3, 4, 5)

BOT_NAMES = ("Marlin", "Nori", "Coral", "Reef", "Tide", "Kelp", "Wave",
             "Pike", "Skipper", "Minnow")

RETRIES = 5


# ---------------------------------------------------------------------------
# Construction and seating
# ---------------------------------------------------------------------------

def _seat(i: int) -> dict:
    return {"seat": i, "kind": "open", "name": "", "secret": None,
            "joined": 0.0, "seen": 0.0, "bank": BANK_SECONDS,
            "timeouts": 0, "away": False, "emote": None, "emote_t": 0.0,
            # The player's profile, if they have one: public id, and the
            # rating and games count as of joining (refreshed after each
            # rated game). Shown to the table; used to rate the game.
            "pid": None, "rating": None, "games": 0}


def _clean_turn(turn, public: bool) -> int:
    try:
        t = int(turn)
    except (TypeError, ValueError):
        return TURN_DEFAULT
    if t == 0 and not public:
        return 0
    return t if t in TURN_CHOICES else TURN_DEFAULT


def _clean_pace(pace) -> str:
    return pace if pace in PACE_CHOICES else PACE_DEFAULT


def new_table(host_name: str, public: bool, turn=TURN_DEFAULT,
              pace=PACE_DEFAULT, now: float = None, card=None) -> tuple:
    """A seating table with its creator in the first seat.

    Returns ``(doc, seat, secret)``. The creator is seated immediately, so a
    table always has somebody in it and cannot be made empty to hold a code.
    """
    now = time.time() if now is None else now
    public = bool(public)
    doc = {
        "kind": KIND, "v": 2,
        "phase": "lobby",
        "public": public,
        "host": None,
        "settings": {"turn": _clean_turn(turn, public),
                     "pace": _clean_pace(pace)},
        "seats": [_seat(i) for i in range(NUM_PLAYERS)],
        # Never sent to a client: it derives every hand.
        "nonce": secrets.token_urlsafe(12),
        "log": [],
        "start_seat": 0,
        "game": 0,
        "created": now,
        "touched": now,
        "start_at": (now + PUBLIC_WAIT) if public else None,
        "clock": None,
        "result": None,
    }
    out = join(doc, host_name, now=now, card=card)
    return doc, out["seat"], out["secret"]


def seat_of(doc: dict, secret) -> int | None:
    if not secret:
        return None
    for s in doc["seats"]:
        if s["kind"] == "human" and s["secret"] and secrets.compare_digest(
                str(s["secret"]), str(secret)):
            return s["seat"]
    return None


def _humans(doc: dict) -> list:
    return [s for s in doc["seats"] if s["kind"] == "human"]


def _reassign_host(doc: dict) -> None:
    """The host is the longest-seated person; nobody, if nobody is left."""
    h = doc.get("host")
    if h is not None and doc["seats"][h]["kind"] == "human":
        return
    people = sorted(_humans(doc), key=lambda s: s["joined"])
    doc["host"] = people[0]["seat"] if people else None


def join(doc: dict, name: str, now: float = None, card=None) -> dict:
    """Take an open seat. Returns ``{"seat", "secret"}``.

    The secret is the player's proof that they are that seat, returned once and
    carried on every later request. ``card`` is the player's verified profile
    (``_profiles.seat_card``), or None; one profile sits once per table, so
    nobody can take two seats -- or both sides -- under one rating.
    """
    now = time.time() if now is None else now
    if doc.get("phase") != "lobby":
        raise ValueError("that table has already started")
    if card and any(s.get("pid") == card["pid"] for s in doc["seats"]
                    if s["kind"] == "human"):
        raise ValueError("you're already at that table")
    order = PUBLIC_ORDER if doc.get("public") else PRIVATE_ORDER
    for i in order:
        s = doc["seats"][i]
        if s["kind"] == "open":
            s.update(_seat(i))
            s["kind"] = "human"
            s["secret"] = secrets.token_urlsafe(16)
            s["name"] = clean_name(name, "") or f"Player {i + 1}"
            s["joined"] = s["seen"] = now
            if card:
                s["pid"], s["rating"] = card["pid"], card["rating"]
                s["games"] = int(card.get("games", 0))
            _reassign_host(doc)
            if doc.get("public"):
                _extend_public_wait(doc, now)
            doc["touched"] = now
            return {"seat": i, "secret": s["secret"]}
    raise ValueError("that table is full")


def _extend_public_wait(doc: dict, now: float) -> None:
    """Give a newcomer a moment to look before a public table deals."""
    if doc.get("start_at") is None:
        return
    latest = float(doc["created"]) + PUBLIC_MAX_WAIT
    doc["start_at"] = min(latest, max(float(doc["start_at"]),
                                      now + PUBLIC_JOIN_GRACE))


def _need(doc: dict, secret, *, host: bool = False, phases=None) -> int:
    me = seat_of(doc, secret)
    if me is None:
        raise ValueError("you are not seated at that table")
    if host and doc.get("host") != me:
        raise ValueError("only the host can do that")
    if phases and doc.get("phase") not in phases:
        raise ValueError("not right now")
    return me


def sit(doc: dict, secret, seat: int, now: float = None) -> None:
    """Move to an open seat while seating -- which is how you pick a team."""
    now = time.time() if now is None else now
    me = _need(doc, secret, phases=("lobby",))
    seat = int(seat) % NUM_PLAYERS
    if seat == me:
        return
    target = doc["seats"][seat]
    if target["kind"] != "open":
        raise ValueError("that seat is taken")
    mine = doc["seats"][me]
    moved = dict(mine, seat=seat)
    doc["seats"][seat] = moved
    doc["seats"][me] = _seat(me)
    if doc.get("host") == me:
        doc["host"] = seat
    doc["touched"] = now


def set_seat_kind(doc: dict, secret, seat: int, kind: str,
                  now: float = None) -> None:
    """The host reserves an open seat for a bot, or opens a bot seat again."""
    now = time.time() if now is None else now
    _need(doc, secret, host=True, phases=("lobby",))
    seat = int(seat) % NUM_PLAYERS
    s = doc["seats"][seat]
    if kind == "bot" and s["kind"] == "open":
        s["kind"] = "bot"
        s["name"] = _bot_name(doc, seat)
    elif kind == "open" and s["kind"] == "bot":
        doc["seats"][seat] = _seat(seat)
    else:
        raise ValueError("can't change that seat")
    doc["touched"] = now


def kick(doc: dict, secret, seat: int, now: float = None) -> None:
    now = time.time() if now is None else now
    me = _need(doc, secret, host=True, phases=("lobby",))
    seat = int(seat) % NUM_PLAYERS
    if seat == me or doc["seats"][seat]["kind"] != "human":
        raise ValueError("can't remove that seat")
    doc["seats"][seat] = _seat(seat)
    doc["touched"] = now


def leave(doc: dict, secret, now: float = None) -> None:
    """Leave the table.

    While seating the seat simply opens again. Once dealt, the hand cannot be
    abandoned -- the other five are mid-game -- so a bot takes the seat over,
    under the same name so the table can still follow who holds what.
    """
    now = time.time() if now is None else now
    me = _need(doc, secret)
    s = doc["seats"][me]
    if doc["phase"] == "lobby":
        doc["seats"][me] = _seat(me)
    else:
        # Written down so leaving cannot dodge a rated loss: see _profiles.
        if doc["phase"] == "playing" and str(me) in (
                (doc.get("rated") or {}).get("seats") or {}):
            left = doc.setdefault("left", [])
            if me not in left:
                left.append(me)
        s["kind"] = "bot"
        s["secret"] = None
        s["away"] = False
        # Only THEIR clock changes. Re-arming the clock unconditionally would
        # hand whoever is mid-turn a fresh full clock every time anyone left.
        if (doc["phase"] == "playing"
                and (doc.get("clock") or {}).get("seat") == me):
            _set_clock(doc, now)
    _reassign_host(doc)
    if not _humans(doc):
        doc["phase"] = "closed"
    doc["touched"] = now


def update_settings(doc: dict, secret, turn=None, pace=None,
                    now: float = None) -> None:
    now = time.time() if now is None else now
    _need(doc, secret, host=True, phases=("lobby", "over"))
    st = doc["settings"]
    if turn is not None:
        st["turn"] = _clean_turn(turn, bool(doc.get("public")))
    if pace is not None:
        st["pace"] = _clean_pace(pace)
    doc["touched"] = now


def emote(doc: dict, secret, eid: str, now: float = None) -> None:
    now = time.time() if now is None else now
    me = _need(doc, secret)
    if eid not in EMOTES:
        raise ValueError("unknown emote")
    s = doc["seats"][me]
    if now - float(s.get("emote_t") or 0) < EMOTE_GAP:
        raise ValueError("easy there")
    s["emote"], s["emote_t"] = eid, now
    doc["touched"] = now


def back(doc: dict, secret, now: float = None) -> None:
    """Clear away status, and restart a fresh clock if it is their turn."""
    now = time.time() if now is None else now
    me = _need(doc, secret)
    s = doc["seats"][me]
    s["away"], s["timeouts"], s["seen"] = False, 0, now
    if doc["phase"] == "playing":
        c = doc.get("clock") or {}
        if c.get("seat") == me:
            _set_clock(doc, now)
    doc["touched"] = now


def touch(doc: dict, me: int, now: float) -> bool:
    """Record that a seated person is still here. Throttled; returns changed."""
    s = doc["seats"][me]
    if now - float(s.get("seen") or 0) < SEEN_EVERY:
        return False
    s["seen"] = now
    doc["touched"] = now
    return True


# ---------------------------------------------------------------------------
# Dealing, the clock, and moves
# ---------------------------------------------------------------------------

def _bot_name(doc: dict, seat: int) -> str:
    taken = {s["name"] for s in doc["seats"] if s["kind"] != "open"}
    for i in range(len(BOT_NAMES)):
        n = BOT_NAMES[(seat + i) % len(BOT_NAMES)]
        if n not in taken:
            return n
    return f"Bot {seat + 1}"


def session_for(doc: dict, seat: int) -> Session:
    """The game, rebuilt from the document and viewed from ``seat``.

    Mirrors ``Session.restore`` step for step -- replay, record reveals, then
    reseed at the current ply. The reseed is the livelock fix: without it the
    engine's stochastic choices restart from ply 0 on every request, and a
    position that recurs reproduces the move that produced it.
    """
    rules = RuleConfig(variant="54", starting_player=int(doc["start_seat"]),
                       wrong_distribution_outcome="opponent")
    s = Session(int(seat), str(doc["nonce"]), rules, CHAMPION_GAMMA)
    log = list(doc.get("log") or [])
    s.wire_log = log
    for a in log:
        ev = s.state.apply(s.state.turn, _action_of(a))
        s.log.append(narrate(ev))
        s.note_reveal(ev)
    s.seed_at(len(log))
    return s


def _deal(doc: dict, now: float) -> None:
    for s in doc["seats"]:
        if s["kind"] == "open":
            s["kind"] = "bot"
            s["name"] = _bot_name(doc, s["seat"])
        s["bank"] = BANK_SECONDS
        s["timeouts"] = 0
        s["away"] = False
    doc["nonce"] = secrets.token_urlsafe(12)
    doc["log"] = []
    #: Who made each move: [seat, "h"] for the person, [seat, "e"] for the
    #: engine standing in (timeout, away, gone, or a bot seat).
    doc["by"] = []
    #: Per-move fair-play rows for rated seats; see _fairplay.
    doc["fair"] = []
    doc["left"] = []
    doc["settled"] = None
    # Rated: a public table, and the profiled people at it as of now. Their
    # ratings are written down here because Elo uses the rating at the start
    # of a game, and because a seat that leaves must still be charged.
    seats = {str(s["seat"]): {"pid": s["pid"], "rating": float(s["rating"]),
                              "games": int(s.get("games") or 0)}
             for s in doc["seats"]
             if s["kind"] == "human" and s.get("pid")
             and s.get("rating") is not None}
    doc["rated"] = ({"key": "g" + secrets.token_hex(8), "seats": seats}
                    if doc.get("public") and seats else None)
    doc["game"] = int(doc.get("game") or 0) + 1
    doc["phase"] = "playing"
    doc["result"] = None
    doc["start_at"] = None
    doc["touched"] = now
    _set_clock(doc, now)


def start(doc: dict, secret, now: float = None) -> None:
    now = time.time() if now is None else now
    me = _need(doc, secret, host=True, phases=("lobby",))
    # The host opens. Somebody has to, and starting on a decision of your own
    # beats starting on four engine possessions you then have to reconstruct.
    doc["start_seat"] = me
    _deal(doc, now)


def rematch(doc: dict, secret, now: float = None) -> None:
    """Deal again at the same table. The first seat moves one place left."""
    now = time.time() if now is None else now
    _need(doc, secret, host=True, phases=("over",))
    key = (doc.get("rated") or {}).get("key")
    if key and doc.get("settled") != key:
        # Dealing again replaces the record of the game just played; a rated
        # one has to reach the profiles first. maybe_settle runs in the same
        # request that ends a game, so this only waits out a store hiccup.
        raise ValueError("still saving ratings -- try again in a moment")
    doc["start_seat"] = (int(doc["start_seat"]) + 1) % NUM_PLAYERS
    _deal(doc, now)


def _pace(doc: dict) -> float:
    return PACE_CHOICES[_clean_pace(doc["settings"].get("pace"))]


def _connected(s: dict, now: float) -> bool:
    return now - float(s.get("seen") or 0) < GONE_PLAYING


def _set_clock(doc: dict, now: float, s: Session = None) -> None:
    """Start the clock for whoever is to move now, or end the game."""
    s = s or session_for(doc, 0)
    if s.over:
        a, b, nulls = s.state.scores()
        doc["phase"] = "over"
        doc["clock"] = None
        doc["result"] = {"score": [a, b], "nulled": nulls,
                         "winner": 0 if a > b else 1 if b > a else None,
                         "stopped": bool(s.stopped)}
        return
    seat = int(s.state.turn)
    st = doc["seats"][seat]
    turn = int(doc["settings"].get("turn") or 0)
    auto = (st["kind"] != "human" or st.get("away")
            or not _connected(st, now))
    if auto:
        end = now + _pace(doc)
        doc["clock"] = {"seat": seat, "start": now, "main_end": end,
                        "end": end, "auto": True}
    elif turn <= 0:
        doc["clock"] = {"seat": seat, "start": now, "main_end": None,
                        "end": None, "auto": False}
    else:
        main_end = now + turn
        doc["clock"] = {"seat": seat, "start": now, "main_end": main_end,
                        "end": main_end + max(0.0, float(st["bank"])),
                        "auto": False}


def _engine_move(doc: dict, seat: int) -> None:
    """Our engine plays one move for ``seat``, from that seat's information."""
    s = session_for(doc, seat)
    s.play(s.suggest(), max_moves=0)
    doc["log"] = list(s.wire_log)
    doc.setdefault("by", []).append([seat, "e"])


def act(doc: dict, secret, action, now: float = None,
        focus_lost: bool = False) -> None:
    """A person's own move. Charges the bank for any time past their clock.

    On a rated table the move is also scored for fair play from this seat's
    own information (see _fairplay), BEFORE it is played. ``focus_lost`` is
    the app's report that it went to the background during this turn.
    """
    now = time.time() if now is None else now
    me = _need(doc, secret, phases=("playing",))
    s = session_for(doc, me)
    if s.over:
        raise ValueError("that game is over")
    if s.state.turn != me:
        raise ValueError("not your turn")
    rated = str(me) in ((doc.get("rated") or {}).get("seats") or {})
    row = None
    if rated:
        try:
            row = F.assess(s, action)    # reads the position; changes nothing
        except Exception:                 # pragma: no cover - never block a move
            row = None
    s.play(action, max_moves=0)          # raises on an illegal action
    c = doc.get("clock") or {}
    if row is not None:
        row["o"] = F.outcome(s.log[-1])
        row["s"] = me
        row["f"] = int(bool(focus_lost))
        if c.get("seat") == me and c.get("start"):
            row["t"] = round(max(0.0, now - float(c["start"])), 1)
        doc.setdefault("fair", []).append(row)
    doc.setdefault("by", []).append([me, "h"])
    seat = doc["seats"][me]
    if c.get("seat") == me and not c.get("auto") and c.get("main_end"):
        seat["bank"] = max(0.0, float(seat["bank"])
                           - max(0.0, now - float(c["main_end"])))
    seat["timeouts"], seat["away"], seat["seen"] = 0, False, now
    doc["log"] = list(s.wire_log)
    doc["touched"] = now
    _set_clock(doc, now)


def tick(doc: dict, now: float = None) -> bool:
    """Advance whatever is due. Returns whether the document changed.

    Called on every poll, by whoever polls. It does at most ONE game move, so
    the bots' pace is the table's and cannot be rushed by a client that polls
    harder than the others.
    """
    now = time.time() if now is None else now
    phase = doc.get("phase")
    changed = False

    if phase == "lobby":
        gone = GONE_LOBBY_PUBLIC if doc.get("public") else GONE_LOBBY_PRIVATE
        for s in doc["seats"]:
            if s["kind"] == "human" and now - float(s["seen"] or 0) > gone:
                doc["seats"][s["seat"]] = _seat(s["seat"])
                changed = True
        if changed:
            _reassign_host(doc)
            if not _humans(doc):
                doc["phase"] = "closed"
                doc["touched"] = now
                return True
        people = _humans(doc)
        full = all(s["kind"] != "open" for s in doc["seats"])
        if doc.get("public") and people and (
                full or now >= float(doc.get("start_at") or now)):
            doc["start_seat"] = doc["host"] if doc["host"] is not None else 0
            _deal(doc, now)
            return True
        if changed:
            doc["touched"] = now
        return changed

    if phase != "playing":
        return False

    c = doc.get("clock")
    s = session_for(doc, 0)
    if s.over:
        _set_clock(doc, now, s)
        doc["touched"] = now
        return True
    seat = int(s.state.turn)
    if not c or int(c.get("seat", -1)) != seat:
        _set_clock(doc, now, s)          # repair a stale or missing clock
        doc["touched"] = now
        return True

    st = doc["seats"][seat]
    # A person who has gone quiet mid-turn is not waited on for the full clock.
    if (not c.get("auto") and st["kind"] == "human"
            and not _connected(st, now)):
        c["auto"] = True
        c["end"] = c["main_end"] = min(float(c["end"] or now),
                                        now + _pace(doc))
        changed = True

    end = c.get("end")
    if end is None or now < float(end):
        if changed:
            doc["touched"] = now
        return changed

    if st["kind"] == "human" and not c.get("auto"):
        st["timeouts"] = int(st.get("timeouts") or 0) + 1
        st["bank"] = 0.0
        if st["timeouts"] >= AWAY_AFTER:
            st["away"] = True
    _engine_move(doc, seat)
    doc["touched"] = now
    _set_clock(doc, now)
    return True


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

def _public_seats(doc: dict, me, now: float, counts=None) -> list:
    out = []
    for s in doc["seats"]:
        e = s.get("emote")
        fresh = e and now - float(s.get("emote_t") or 0) < EMOTE_SHOW
        out.append({
            "seat": s["seat"],
            "kind": s["kind"],
            "name": s["name"] if s["kind"] != "open" else "",
            "team": team_of(s["seat"]),
            "me": s["seat"] == me,
            "host": s["seat"] == doc.get("host"),
            "away": bool(s.get("away")),
            "connected": (s["kind"] != "human") or _connected(s, now),
            "bank": round(float(s.get("bank") or 0), 1),
            "emote": ({"id": e, "at": float(s["emote_t"])} if fresh else None),
            "cards": (counts[s["seat"]] if counts else None),
            # A person's public profile id and rating, for the profile sheet.
            "pid": s.get("pid") if s["kind"] == "human" else None,
            "rating": (round(float(s["rating"])) if s["kind"] == "human"
                       and s.get("rating") is not None else None),
        })
    return out


def view(doc: dict, code: str, me, version: int, now: float = None) -> dict:
    """One seat's whole picture of the table. Never carries a secret or nonce."""
    now = time.time() if now is None else now
    phase = doc["phase"]
    out = {
        "kind": KIND, "code": code, "v": version, "now": now,
        "phase": phase, "public": bool(doc.get("public")),
        "me": me, "host": doc.get("host"),
        "settings": dict(doc["settings"]),
        "start_at": doc.get("start_at"),
        "game_no": int(doc.get("game") or 0),
        "clock": None, "game": None, "result": doc.get("result"),
        # Moves made so far. The game's log is only its tail, so this is how a
        # client tells which entries are new since its last poll -- and so
        # which ones to animate.
        "plies": len(doc.get("log") or []),
        # Public tables are rated; this says whether THIS game is.
        "rated": bool(doc.get("rated")) if phase != "lobby"
        else bool(doc.get("public")),
    }
    counts = None
    if phase in ("playing", "over") and me is not None:
        snap = session_for(doc, me).snapshot()
        snap.pop("token", None)
        snap["log"] = list(snap.get("log") or [])[-HISTORY_VISIBLE:]
        snap["history_visible"] = HISTORY_VISIBLE
        counts = snap["hand_counts"]
        out["game"] = snap
        c = doc.get("clock")
        if c and phase == "playing":
            out["clock"] = {k: c.get(k) for k in
                            ("seat", "start", "main_end", "end", "auto")}
    out["seats"] = _public_seats(doc, me, now, counts)
    return out


def lobby_summary(code: str, doc: dict, now: float) -> dict:
    """What the public list may show about a table: no seat secrets, no deal."""
    people = _humans(doc)
    rated = [float(s["rating"]) for s in people if s.get("rating") is not None]
    return {"code": code,
            "players": len(people),
            "open": sum(1 for s in doc["seats"] if s["kind"] == "open"),
            "names": [s["name"] for s in people],
            "turn": doc["settings"].get("turn"),
            "rating": round(sum(rated) / len(rated)) if rated else None,
            "starts_in": max(0.0, float(doc.get("start_at") or now) - now)}


# ---------------------------------------------------------------------------
# Store operations, each retried on a lost compare-and-set
# ---------------------------------------------------------------------------

def mutate(code: str, fn) -> tuple:
    """Read, apply ``fn``, and write only if something changed.

    ``fn(doc)`` returns ``(result, changed)``. A poll that finds nothing due
    writes nothing, which matters: otherwise six players polling once a second
    would be six writes a second, and every one of them a chance to collide
    with the move that actually mattered. Returns ``(doc, result, version)``.
    """
    st = store()
    last = None
    for _ in range(RETRIES):
        version, doc = st.read(code)
        if doc.get("kind") != KIND:
            raise NotFound(code)
        result, changed = fn(doc)
        if not changed:
            return doc, result, version
        try:
            return doc, result, st.write(code, version, doc)
        except Conflict as e:
            last = e
            continue
    raise RuntimeError("the table is busy; try that again") from last


def create(name: str, public: bool, turn=TURN_DEFAULT,
           pace=PACE_DEFAULT, card=None) -> tuple:
    doc, seat, secret = new_table(name, public, turn, pace, card=card)
    code = store().create(doc)
    return code, seat, secret, doc


def open_tables(limit: int = 20) -> list:
    now = time.time()
    rows = store().list_lobbies(limit=limit * 2)
    out = []
    for code, _v, doc in rows:
        if doc.get("kind") != KIND:
            continue
        # One malformed row in a SHARED store must not take the public list
        # down for every player at once. A probe row written while switching
        # the database on had a table's markers and no seats, and summarising
        # it raised KeyError -- a 500 for every Quick Play until it aged out.
        try:
            summ = lobby_summary(code, doc, now)
        except (KeyError, TypeError, ValueError, AttributeError):
            continue
        if summ["open"] > 0 and summ["players"] > 0:
            out.append(summ)
    return out[:limit]


def quick_play(name: str, card=None) -> tuple:
    """Join the fullest public table that still has room, or open a new one.

    Fullest first, because the point of matching is to get a table to six
    people, and spreading arrivals across many half-empty tables does the
    opposite. Among equally full tables, the one whose players are rated
    closest to you. A table about to deal is skipped: joining one with a second
    left would seat the newcomer straight into a hand they never saw coming.
    Returns ``(code, seat, secret, doc, version)``.
    """
    now = time.time()
    mine = float(card["rating"]) if card else None
    cands = [t for t in open_tables(limit=12) if t["starts_in"] > 4.0]
    cands.sort(key=lambda t: (
        -t["players"],
        abs(t["rating"] - mine) if (mine is not None and t.get("rating"))
        else 0.0,
        t["starts_in"]))
    for t in cands[:6]:
        def _join(d):
            tick(d, now)
            if d.get("phase") != "lobby":
                raise ValueError("started")
            return join(d, name, now=now, card=card), True
        try:
            doc, out, version = mutate(t["code"], _join)
            return t["code"], out["seat"], out["secret"], doc, version
        except (ValueError, NotFound, RuntimeError):
            continue
    code, seat, secret, doc = create(name, public=True, card=card)
    return code, seat, secret, doc, 1


def maybe_settle(code: str, doc: dict, version: int) -> tuple:
    """Rate a finished game, once. Returns the (possibly updated) doc, version.

    Whoever polls a finished rated table first applies the result to every
    rated profile -- idempotently, per game -- and then marks the table
    settled with each seat's rating change for the results screen. If a
    profile cannot be reached the table stays unsettled and the next poll
    tries again; nothing is half-applied, because each profile records the
    games it has taken.
    """
    rated = doc.get("rated") or {}
    key = rated.get("key")
    if doc.get("phase") != "over" or not key or doc.get("settled") == key:
        return doc, version
    from api import _profiles as P
    try:
        if P.profiles() is None:
            return doc, version
        changes = P.settle(doc)
    except Exception:                     # pragma: no cover - retried next poll
        return doc, version

    def fn(d):
        if (d.get("rated") or {}).get("key") != key or d.get("settled") == key:
            return None, False
        d["settled"] = key
        res = d.get("result") or {}
        res["ratings"] = {str(k): v for k, v in changes.items()}
        d["result"] = res
        for k, v in changes.items():
            st = d["seats"][int(k)]
            if v.get("rating") is not None and st.get("pid"):
                st["rating"] = float(v["rating"])
                st["games"] = int(st.get("games") or 0) + 1
        return None, True
    try:
        doc, _, version = mutate(code, fn)
    except Exception:                     # pragma: no cover
        pass
    return doc, version
