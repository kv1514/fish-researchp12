"""Rooms, seating and what each seat is allowed to see.

Two things are worth testing here and the rest is plumbing. Seating is a
*team* decision -- "three of us against three bots" is only expressible as a
constraint on which seats the people take -- so the arrangement is checked
against the team partition rather than against a list of seat numbers. And the
per-seat view is the security boundary of the whole web build: it is the only
thing standing between a curious player and everybody else's hand.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, team_of
from fish.rules import RuleConfig
from fish4.web.lobby import Lobby, Room

RULES = RuleConfig()


def _room(humans, arrangement="one_team", **kw):
    kw.setdefault("seed", 20260822)
    kw.setdefault("gamma", 0.35)
    kw.setdefault("bot_delay", 0.0)
    kw.setdefault("hints", True)
    return Room(humans, arrangement, "host", RULES, **kw)


def _fill(room, names=None):
    out = []
    n = len(room.open_seats)
    for i in range(n):
        out.append(room.join((names or [])[i] if names and i < len(names)
                             else f"P{i}"))
    return out


# ---------------------------------------------------------------------------
# seating
# ---------------------------------------------------------------------------

def test_three_humans_form_one_whole_team():
    """The headline request: 3 people against 3 engines."""
    room = _room(3, "one_team")
    assert room.human_seats == [0, 2, 4]
    teams = {team_of(s) for s in room.human_seats}
    assert len(teams) == 1, "the three people must be one team, not a mixture"
    bots = [s for s in range(NUM_PLAYERS) if s not in room.human_seats]
    assert {team_of(s) for s in bots} == {1 - teams.pop()}
    _fill(room)
    assert room.status == "playing"
    assert all(room.seats[s].kind == "bot" for s in bots)
    assert all(s in room.bots for s in bots)


def test_one_team_arrangement_fills_a_side_before_crossing():
    for n in range(1, 7):
        seats = _room(n, "one_team").human_seats
        evens = [s for s in seats if s % 2 == 0]
        odds = [s for s in seats if s % 2]
        assert len(seats) == n
        assert not odds or len(evens) == 3, (
            f"{n} humans: crossed to the other team at {seats} before "
            f"filling the first")


def test_alternate_arrangement_splits_the_people_up():
    seats = _room(4, "alternate").human_seats
    assert seats == [0, 1, 2, 3]
    assert {team_of(s) for s in seats} == {0, 1}


def test_the_game_starts_only_when_every_human_seat_is_taken():
    room = _room(3, "one_team")
    room.join("a"); room.join("b")
    assert room.status == "waiting" and room.state is None
    room.join("c")
    assert room.status == "playing" and room.state is not None
    assert room.join("gatecrasher") is None, "let a seventh player in"


# ---------------------------------------------------------------------------
# what a seat may see
# ---------------------------------------------------------------------------

def test_a_view_never_contains_another_seats_cards():
    room = _room(2, "one_team")
    tokens = _fill(room)
    for j in tokens:
        v = room.view(j["seat"])
        mine = {c["id"] for c in v["hand"]}
        assert mine == {c for c in range(54)
                        if room.state.hands[j["seat"]] >> c & 1}
        for other in range(NUM_PLAYERS):
            if other == j["seat"]:
                continue
            theirs = {c for c in range(54)
                      if room.state.hands[other] >> c & 1}
            assert not (mine & theirs)
        # counts are public; contents are not
        assert v["hand_counts"] == list(room.state.hand_counts())
        assert v.get("reveal") is None, "revealed the deal mid-game"
        assert all(k not in v for k in ("hands", "deal"))


def test_a_stranger_sees_no_cards_at_all():
    room = _room(1)
    _fill(room)
    v = room.view(None)
    assert v["hand"] == [] and v["log"] == [] and v["your_turn"] is False
    assert "hand_counts" not in v and "score" not in v


def test_a_wrong_token_is_not_a_seat():
    room = _room(2)
    good = _fill(room)[0]
    assert room.seat_of(good["token"]) == good["seat"]
    assert room.seat_of("") is None
    assert room.seat_of("0" * len(good["token"])) is None
    assert room.seat_of(good["token"][:-1] + "x") is None


def test_askable_is_exactly_the_legal_asks():
    room = _room(6, "alternate")
    _fill(room)
    seat = room.state.turn
    from fish.observation import Observation
    legal = {a.card for a in
             Observation.from_state(room.state, seat).legal_asks()}
    offered = {c["id"] for g in room.view(seat)["askable"] for c in g["cards"]}
    assert offered == legal, offered ^ legal
    assert room.view((seat + 1) % 6)["askable"] == [], (
        "offered asks to a seat that is not on move")


# ---------------------------------------------------------------------------
# the clock
# ---------------------------------------------------------------------------

def test_bots_move_on_the_clock_and_finish_the_game():
    room = _room(1, "one_team", bot_delay=0.0)
    _fill(room)
    for _ in range(4000):
        if room.status == "finished":
            break
        if room.state.turn == 0:            # play the human seat with its bot
            from fish4.registry4 import make_agent
            from fish.observation import Observation
            b = make_agent(("fishbot4", {"opponent_gamma": 0.35}))
            b.begin_game(0, RULES, 99)
            room.apply(0, b.act(Observation.from_state(room.state, 0)))
        else:
            room.step_bot()
    assert room.status == "finished", "the table never reached a result"
    v = room.view(0)
    assert v["score"]["you"] + v["score"]["them"] + v["score"]["nulled"] == 9
    assert v["reveal"] is not None, "the deal is not shown after the game ends"


def test_bot_delay_actually_delays():
    room = _room(1, "one_team", bot_delay=0.4)
    _fill(room)
    while room.state.turn == 0:             # get a bot on move
        room.state.turn = (room.state.turn + 1) % NUM_PLAYERS
    room.next_bot_at = time.time() + 0.4
    assert room.step_bot() is False, "a bot moved before its clock was up"
    room.next_bot_at = 0.0
    assert room.step_bot() is True


def test_the_lobby_only_lists_joinable_or_live_tables():
    lob = Lobby(tick=100.0)                 # do not race the clock thread
    try:
        a = lob.create(2, "one_team", "a", RULES, seed=1, bot_delay=0.0)
        codes = [r["code"] for r in lob.listing()]
        assert a.code in codes
        assert lob.get(a.code.lower()) is a, "codes must not be case-sensitive"
        assert lob.get("ZZZZ") is None
        row = next(r for r in lob.listing() if r["code"] == a.code)
        assert row["humans"] == 2 and row["bots"] == 4 and row["seats_open"] == 2
        _fill(a)
        row = next(r for r in lob.listing() if r["code"] == a.code)
        assert row["seats_open"] == 0 and row["status"] == "playing"
    finally:
        lob.stop()


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("all lobby tests passed")
