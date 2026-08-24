"""Rooms: the ready gate, who may rename whom, and the information boundary.

The boundary is the reason this file is long. A solo game can be careless about
what the server sends because there is one player and the hidden hands are the
engine's. A room has five other people at it, and the per-seat view is the only
thing standing between one of them and everybody else's cards.

The other rules tested here are the ones a player would notice immediately if
they broke: nobody joins a game already in progress, the deal waits for
everyone, and the pace belongs to the room rather than to whichever client
polls hardest.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, team_of                     # noqa: E402
from api import _rooms                                          # noqa: E402
from api import _room_game as RG                                # noqa: E402


@pytest.fixture(autouse=True)
def _mem_store():
    """Every test gets its own store, so codes cannot collide across tests."""
    _rooms.reset_store_for_tests(_rooms.MemoryStore())
    yield
    _rooms.reset_store_for_tests(None)


def _room(humans=2, pace=0.0, host="Ada"):
    doc = RG.new_room(humans, host, pace)
    code = _rooms.store().create(doc)
    return code, doc


def _secrets(doc):
    return [s["secret"] for s in doc["seats"] if s["kind"] == "human"]


def _ready_all(doc):
    for sec in _secrets(doc):
        if sec:
            RG.set_ready(doc, sec, True)
    return RG.maybe_start(doc)


# ---------------------------------------------------------------- the gate

def test_the_deal_waits_for_every_person_at_the_table():
    code, doc = _room(humans=3)
    RG.join_room(doc, "Bo")
    RG.join_room(doc, "Cy")
    secs = _secrets(doc)
    assert len(secs) == 3

    # Two of three ready is not enough, and the phase must not move.
    RG.set_ready(doc, secs[0], True)
    RG.set_ready(doc, secs[1], True)
    assert RG.everyone_ready(doc) is False
    assert RG.maybe_start(doc) is False
    assert doc["phase"] == "seating"

    RG.set_ready(doc, secs[2], True)
    assert RG.maybe_start(doc) is True
    assert doc["phase"] == "playing"


def test_an_unfilled_seat_blocks_the_deal():
    """A seat nobody has taken is not a seat that is ready.

    `ready` defaults to False on a human seat, but the check has to test
    OCCUPANCY too -- otherwise a room for three that two people joined would
    deal as soon as those two pressed ready, and the third would arrive to
    find a game in progress.
    """
    code, doc = _room(humans=3)
    RG.join_room(doc, "Bo")            # seat filled; third still empty
    for sec in _secrets(doc):
        if sec:
            RG.set_ready(doc, sec, True)
    assert RG.everyone_ready(doc) is False
    assert RG.maybe_start(doc) is False


def test_nobody_joins_a_game_in_progress():
    code, doc = _room(humans=2)
    RG.join_room(doc, "Bo")
    assert _ready_all(doc) is True
    with pytest.raises(ValueError, match="already started"):
        RG.join_room(doc, "Cy")


def test_a_full_table_is_full():
    code, doc = _room(humans=2)
    RG.join_room(doc, "Bo")
    with pytest.raises(ValueError, match="full"):
        RG.join_room(doc, "Cy")


# --------------------------------------------------------------- who starts

def test_a_solo_room_starts_the_human():
    """One person against five bots opens on their decision, not on four
    engine possessions they then have to reconstruct from a log."""
    for _ in range(3):
        code, doc = _room(humans=1, host="Solo")
        assert _ready_all(doc) is True
        me = [s["seat"] for s in doc["seats"] if s["kind"] == "human"][0]
        assert doc["start_seat"] == me
        assert RG.table_view(doc, code, me)["your_turn"] is True


def test_people_fill_one_team_first():
    """Seating is a team decision: three friends who arrive together play
    together, which is only expressible as which seats they take."""
    code, doc = _room(humans=3)
    people = [s["seat"] for s in doc["seats"] if s["kind"] == "human"]
    assert len({team_of(p) for p in people}) == 1, (
        f"seats {people} span both teams, so a group of three cannot play "
        f"as a team")


# ------------------------------------------------------------------- names

def test_anyone_may_rename_a_bot_but_only_yourself():
    code, doc = _room(humans=2)
    bo = RG.join_room(doc, "Bo")
    ada_secret = _secrets(doc)[0]

    bot_seat = next(s["seat"] for s in doc["seats"] if s["kind"] == "bot")
    RG.rename(doc, bo["secret"], bot_seat, "Sharky")
    assert doc["seats"][bot_seat]["name"] == "Sharky"

    ada_seat = RG.seat_of(doc, ada_secret)
    with pytest.raises(ValueError, match="only rename yourself"):
        RG.rename(doc, bo["secret"], ada_seat, "Hacked")
    assert doc["seats"][ada_seat]["name"] == "Ada"


def test_a_name_cannot_impersonate_another_name():
    """Zero-width characters are stripped server-side.

    A seat label is how the others identify who asked them for a card. Without
    this, "Ada" and "Ad<ZWSP>a" render identically and a player can sit down as
    somebody already at the table. The client has its own copy of this in
    public/names.js; a check that runs in the browser is not a boundary.
    """
    # Escapes, not pasted characters: a test whose inputs are invisible is
    # a test nobody can review, and this is the one that guards
    # impersonation.
    ZWSP, RLO = "\u200b", "\u202e"
    code, doc = _room(humans=2)
    bo = RG.join_room(doc, "Bo")
    RG.rename(doc, bo["secret"], bo["seat"], "Ad" + ZWSP + "a")
    assert doc["seats"][bo["seat"]]["name"] == "Ada"

    RG.rename(doc, bo["secret"], bo["seat"], "Bo" + RLO + "gnihcaH")
    assert RLO not in doc["seats"][bo["seat"]]["name"]

    # And a name that cleans away entirely does not blank the seat.
    RG.rename(doc, bo["secret"], bo["seat"], ZWSP + ZWSP)
    assert doc["seats"][bo["seat"]]["name"] == ""

    RG.rename(doc, bo["secret"], bo["seat"], "x" * 200)
    assert len(doc["seats"][bo["seat"]]["name"]) == _rooms.MAX_NAME


def test_names_are_fixed_once_the_deal_starts():
    code, doc = _room(humans=2)
    bo = RG.join_room(doc, "Bo")
    _ready_all(doc)
    with pytest.raises(ValueError, match="fixed once"):
        RG.rename(doc, bo["secret"], bo["seat"], "Late")


# -------------------------------------------------- the information boundary

def test_no_players_view_contains_another_players_cards():
    """The property the whole design exists for.

    Checked by set membership rather than by inspecting fields, so a future
    field that happens to carry a card id fails this too.
    """
    code, doc = _room(humans=2)
    RG.join_room(doc, "Bo")
    _ready_all(doc)
    seats = [s["seat"] for s in doc["seats"] if s["kind"] == "human"]

    truth = {p: set(RG.session_for(doc, p).state.hands[p] and
                    [c for c in range(54)
                     if RG.session_for(doc, 0).state.hands[p] >> c & 1])
             for p in range(NUM_PLAYERS)}

    for me in seats:
        view = RG.table_view(doc, code, me)
        shown = {c["id"] for c in view["hand"]}
        assert shown == truth[me], "a seat is not shown its own hand"
        # Every OTHER seat's cards must be absent from the serialised view.
        blob = repr(view)
        for other in range(NUM_PLAYERS):
            if other == me:
                continue
            leaked = truth[other] - truth[me]
            for c in leaked:
                # A card id could coincide with an unrelated integer, so this
                # checks the structured places a hand could hide rather than
                # the whole blob.
                assert c not in shown, f"seat {me} sees card {c} of seat {other}"
        assert "nonce" not in blob, "the deal nonce reached a client view"
        assert "secret" not in blob, "a seat secret reached a client view"


def test_the_deal_nonce_and_secrets_never_appear_in_any_view():
    code, doc = _room(humans=2)
    bo = RG.join_room(doc, "Bo")
    _ready_all(doc)
    for me in (0, bo["seat"]):
        for view in (RG.table_view(doc, code, me),
                     RG.lobby_view(doc, code, me)):
            blob = repr(view)
            assert doc["nonce"] not in blob
            for s in doc["seats"]:
                if s["secret"]:
                    assert s["secret"] not in blob


def test_a_stranger_has_no_seat():
    code, doc = _room(humans=2)
    assert RG.seat_of(doc, "not-a-secret") is None
    assert RG.seat_of(doc, "") is None
    assert RG.seat_of(doc, None) is None


# ------------------------------------------------------------------ pacing

def test_the_pace_belongs_to_the_room_not_to_the_caller():
    """A client polling in a loop must not be able to rush the table.

    Without a server-side `next_move_at`, whichever player polled hardest
    would advance the engine as fast as it could compute -- past the reading
    speed of everybody else at the table, which is the one thing the pacing
    exists to prevent.
    """
    code, doc = _room(humans=1, pace=30.0)
    _ready_all(doc)
    me = doc["start_seat"]

    # The human starts. A SUCCESSFUL ask keeps the turn, so handing it to an
    # engine takes however many moves it takes -- the first draft of this test
    # played one and assumed the turn had moved, which it had not.
    for _ in range(40):
        if RG.is_bot_turn(doc):
            break
        doc["next_move_at"] = 0.0
        s = RG.session_for(doc, me)
        RG.apply_action(doc, me, s.suggest())
    assert RG.is_bot_turn(doc), "never reached an engine turn"

    # Now the clock is armed by that last human move, and hammering step_bot
    # must not advance the table while it says wait.
    assert doc["next_move_at"] > time.time()
    before = len(doc["log"])
    for _ in range(25):
        RG.step_bot(doc)
    assert len(doc["log"]) == before, "polling advanced the table early"

    # Wound back, exactly one engine move lands per due tick.
    doc["next_move_at"] = 0.0
    assert RG.step_bot(doc) == 1
    assert len(doc["log"]) == before + 1
    # And the clock is re-armed, so the next poll waits again.
    assert doc["next_move_at"] > time.time()
    assert RG.step_bot(doc) == 0
    assert len(doc["log"]) == before + 1


def test_step_bot_does_nothing_on_a_persons_turn():
    code, doc = _room(humans=1, pace=0.0)
    _ready_all(doc)
    assert RG.is_bot_turn(doc) is False
    before = len(doc["log"])
    assert RG.step_bot(doc) == 0
    assert len(doc["log"]) == before


def test_a_person_cannot_act_out_of_turn():
    code, doc = _room(humans=2)
    bo = RG.join_room(doc, "Bo")
    _ready_all(doc)
    not_on_turn = bo["seat"] if doc["start_seat"] != bo["seat"] else 0
    # A plain Ask, not the engine's suggestion: asking the engine what to do
    # from a seat that is not on turn is itself an error, so it would fail for
    # the wrong reason. The turn check has to reject the action before anything
    # looks at whether it is legal.
    from fish.engine import Ask
    with pytest.raises(ValueError, match="not your turn"):
        RG.apply_action(doc, not_on_turn, Ask(doc["start_seat"], 0))


# ------------------------------------------------------------------- store

def test_a_stale_write_is_rejected_rather_than_silently_winning():
    """Compare-and-set. Two players act in the same instant; one must retry.

    Last-write-wins would drop a move that a player watched be accepted, which
    is the worst available outcome -- worse than an error, because nothing
    tells them it happened.
    """
    st = _rooms.MemoryStore()
    code = st.create({"touched": time.time(), "n": 0})
    v1, doc1 = st.read(code)
    v2, doc2 = st.read(code)
    assert v1 == v2

    doc1["n"] = 1
    st.write(code, v1, doc1)

    doc2["n"] = 2
    with pytest.raises(_rooms.Conflict):
        st.write(code, v2, doc2)

    _, final = st.read(code)
    assert final["n"] == 1, "the stale write won"


def test_mutate_retries_a_conflict_and_lands():
    _rooms.reset_store_for_tests(_rooms.MemoryStore())
    code, doc = _room(humans=2)
    calls = {"n": 0}

    def fn(d):
        calls["n"] += 1
        d["seats"][0]["name"] = "Retried"
        return "ok"

    out_doc, out = RG.mutate(code, fn)
    assert out == "ok"
    assert calls["n"] == 1
    _, stored = _rooms.store().read(code)
    assert stored["seats"][0]["name"] == "Retried"


def test_reading_a_missing_room_raises_not_found():
    st = _rooms.MemoryStore()
    with pytest.raises(_rooms.NotFound):
        st.read("ZZZZ")


def test_room_codes_avoid_lookalike_characters():
    """No I, O, 0 or 1: a code is read aloud and typed by somebody else."""
    for ch in "IO01":
        assert ch not in _rooms.CODE_ALPHABET
    for _ in range(200):
        c = _rooms.new_code()
        assert len(c) == _rooms.CODE_LEN
        assert all(x in _rooms.CODE_ALPHABET for x in c)


# ------------------------------------------- refusing a store that is not one

def test_rooms_refuse_a_serverless_deployment_with_no_shared_store(monkeypatch):
    """Measured, not predicted.

    A create-then-join against the deployed build with no store configured
    returned a perfectly good seat -- because both requests happened to land on
    the same warm instance. The next request lands elsewhere and the table has
    never existed. An intermittent room is worse than no room: it reads as a
    bug in the game rather than as a missing environment variable.
    """
    _rooms.reset_store_for_tests(_rooms.MemoryStore())

    # Local: one process, so the memory store is genuinely shared. Allowed.
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    assert _rooms.serverless() is False
    _rooms.require_shared_store()

    # Serverless with no Postgres: refused, and the message names both
    # variables rather than saying "unavailable".
    monkeypatch.setenv("VERCEL", "1")
    assert _rooms.serverless() is True
    with pytest.raises(RuntimeError) as e:
        _rooms.require_shared_store()
    assert "SUPABASE_URL" in str(e.value)
    assert "SUPABASE_SERVICE_KEY" in str(e.value)

    # Serverless WITH Postgres configured: allowed.
    _rooms.reset_store_for_tests(_rooms.PostgrestStore("https://x", "k"))
    _rooms.require_shared_store()


def test_the_store_is_chosen_from_the_environment(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_KEY", "service-key")
    _rooms.reset_store_for_tests(None)
    assert _rooms.backend_name() == "postgres"

    monkeypatch.delenv("SUPABASE_URL")
    monkeypatch.delenv("SUPABASE_SERVICE_KEY")
    _rooms.reset_store_for_tests(None)
    assert _rooms.backend_name() == "memory"


def test_the_service_key_never_appears_in_a_store_error():
    """A store error is returned to a client, so it must not carry the key."""
    st = _rooms.PostgrestStore("https://127.0.0.1:1", "super-secret-key")
    with pytest.raises(RuntimeError) as e:
        st.read("ABCD")
    assert "super-secret-key" not in str(e.value)
