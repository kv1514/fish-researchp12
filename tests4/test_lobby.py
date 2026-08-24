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
from fish4.web.lobby import MAX_BOT_DELAY, Lobby, Room

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


def test_no_view_carries_the_deal_seed():
    """The seed IS the deal.

    Every hand is a deterministic function of it, so shipping it to a client is
    the same as shipping the other five hands -- and a table code is enough to
    fetch a view without sitting down. Checked recursively, because a nested
    config blob would leak it just as well as a top-level key.
    """
    import json

    def seeds_in(obj, path="view"):
        if isinstance(obj, dict):
            for k, val in obj.items():
                if "seed" in str(k).lower():
                    yield f"{path}.{k}"
                yield from seeds_in(val, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, val in enumerate(obj):
                yield from seeds_in(val, f"{path}[{i}]")

    room = _room(2, "one_team", seed=123456789)
    tokens = _fill(room)
    for seat in [None] + [j["seat"] for j in tokens]:
        v = room.view(seat)
        json.dumps(v)                       # must stay serialisable
        found = list(seeds_in(v))
        assert not found, f"seat {seat} was sent the deal seed at {found}"
        assert room.seed not in _numbers(v), (
            f"seat {seat} was sent the seed value under another name")


def _numbers(obj):
    if isinstance(obj, bool):
        return set()
    if isinstance(obj, int):
        return {obj}
    if isinstance(obj, dict):
        return set().union(*(_numbers(v) for v in obj.values())) or set()
    if isinstance(obj, list) and obj:
        return set().union(*(_numbers(v) for v in obj))
    return set()


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


def test_a_voided_claim_is_not_reported_as_a_win():
    """The one place a sentinel could quietly become a lie.

    A nulled half-suit is NULL_TEAM == -1 inside the engine, which compares
    equal to nothing and unequal to both team numbers, so a client asking
    "did MY team win it?" and falling through to "then the other team did"
    announces the wrong result. The wire format collapses it to null.
    """
    from fish.engine import NULL_TEAM, ClaimEvent
    from fish4.web.lobby import event_dict

    for winner in (0, 1):
        d = event_dict(ClaimEvent(0, 3, (0,) * 6, (0, 2, 4, 0, 2, 4), winner))
        assert d["winner"] == winner and d["void"] is False

    d = event_dict(ClaimEvent(0, 3, (0,) * 6, (0, 2, 4, 1, 3, 5), NULL_TEAM))
    assert d["winner"] is None, f"a void reached the client as {d['winner']!r}"
    assert d["void"] is True
    assert d["winner"] not in (0, 1), "a void is indistinguishable from a win"


def test_a_real_voided_claim_survives_the_round_trip():
    """As above, but through an actual game rather than a synthetic event."""
    from fish.cards import half_suit_cards
    from fish.engine import Claim

    room = _room(1, "one_team", bot_delay=0.0)
    _fill(room)
    st = room.state
    hs = next(h for h in range(9) if st.set_winner[h] is None)
    cards = list(half_suit_cards(hs))
    holders = [st.holder_of(c) for c in cards]
    if len({team_of(h) for h in holders}) != 2:
        return                       # not split across teams in this deal
    seat = st.turn
    team = [p for p in range(NUM_PLAYERS) if team_of(p) == team_of(seat)]
    # a declaration that must be wrong, since the set is not all ours
    room.state.turn = seat
    room.apply(seat, Claim(hs, tuple(team[i % 3] for i in range(6))))
    ev = room.log[-1]
    assert ev["t"] == "claim"
    if ev["void"]:
        assert ev["winner"] is None
    else:
        assert ev["winner"] in (0, 1)


def _bot_on_move(room):
    """Put a bot on move without playing the game out."""
    while room.seats[room.state.turn].kind != "bot":
        room.state.turn = (room.state.turn + 1) % NUM_PLAYERS
    return room.state.turn


def test_a_paused_table_does_not_move():
    room = _room(1, "one_team", bot_delay=12.0)
    _fill(room)
    _bot_on_move(room)
    room.next_bot_at = 0.0                  # the wait is already over
    room.pace(paused=True)
    assert room.step_bot() is False, "a paused engine moved anyway"
    for _ in range(20):
        assert room.step_bot() is False
    room.pace(paused=False)
    assert room.step_bot() is True


def test_pausing_freezes_the_countdown_rather_than_restarting_it():
    """Resuming must give back the time that was left, not a fresh wait."""
    room = _room(1, "one_team", bot_delay=12.0)
    _fill(room)
    _bot_on_move(room)
    room.next_bot_at = time.time() + 3.0    # 3s left of a 12s wait
    room.pace(paused=True)
    assert 2.5 < room.wait_left() <= 3.0, room.wait_left()
    time.sleep(0.35)                        # time passes while paused
    assert 2.5 < room.wait_left() <= 3.0, "the clock ran while paused"
    room.pace(paused=False)
    assert 2.5 < room.wait_left() <= 3.05, room.wait_left()
    assert room.step_bot() is False, "resuming skipped the rest of the wait"


def test_skip_plays_the_next_move_now():
    room = _room(1, "one_team", bot_delay=30.0)
    _fill(room)
    _bot_on_move(room)
    room.next_bot_at = time.time() + 30.0
    assert room.step_bot() is False
    room.pace(skip=True)
    assert room.wait_left() == 0.0
    assert room.step_bot() is True, "skip did not let the engine move"
    assert room.bot_delay == 30.0, "skip must not change the pace permanently"


def test_skip_steps_a_paused_table_without_thawing_it():
    """A frozen table should step, not restart.

    Somebody reading the position one move at a time should not have to
    unfreeze and refreeze around every move.
    """
    room = _room(1, "one_team", bot_delay=20.0)
    _fill(room)
    _bot_on_move(room)
    room.pace(paused=True)
    before = len(room.log)
    room.pace(skip=True)
    assert len(room.log) == before + 1, "step did not play a move"
    assert room.paused is True, "stepping thawed the table"
    assert room.step_bot() is False, "the table kept playing after one step"
    # ...and it can be stepped again. The move may have handed the turn to the
    # human seat, in which case there is no engine move to take, so put one
    # back on move first.
    _bot_on_move(room)
    room.pace(skip=True)
    assert len(room.log) == before + 2, "a second step did not play"
    assert room.paused is True


def test_changing_the_pace_shifts_the_move_already_pending():
    room = _room(1, "one_team", bot_delay=20.0)
    _fill(room)
    _bot_on_move(room)
    room.next_bot_at = time.time() + 20.0
    room.pace(delay=5.0)                    # 15s faster: 5s should remain
    assert 4.0 < room.wait_left() <= 5.2, room.wait_left()
    room.pace(delay=20.0)                   # and back again
    assert 19.0 < room.wait_left() <= 20.2, room.wait_left()


def test_the_pace_is_bounded_at_both_ends():
    room = _room(1, "one_team", bot_delay=10.0)
    _fill(room)
    room.pace(delay=10 ** 9)
    assert room.bot_delay == MAX_BOT_DELAY
    room.pace(delay=-5)
    assert room.bot_delay == 0.0


def test_no_countdown_while_a_person_is_on_move():
    """The wait paces the engines. A human is never on a clock."""
    room = _room(1, "one_team", bot_delay=12.0)
    _fill(room)
    while room.seats[room.state.turn].kind != "human":
        room.state.turn = (room.state.turn + 1) % NUM_PLAYERS
    room.next_bot_at = time.time() + 12.0
    assert room.wait_left() == 0.0, "put a human seat on a countdown"
    v = room.view(0)
    assert v["wait_left"] == 0.0 and v["paused"] is False
    assert v["bot_delay"] == 12.0


def test_the_view_reports_the_clock():
    room = _room(1, "one_team", bot_delay=12.0)
    _fill(room)
    _bot_on_move(room)
    room.next_bot_at = time.time() + 12.0
    v = room.view(0)
    assert 11.0 < v["wait_left"] <= 12.0, v["wait_left"]
    room.pace(paused=True)
    assert room.view(0)["paused"] is True


def test_a_move_made_while_paused_still_gets_its_full_wait():
    """Otherwise the first engine move after a resume arrives instantly.

    apply() used to stamp a wall-clock deadline that the resume path then
    overwrote with whatever had been banked at the moment of pausing, so a
    human who moved during a freeze lost the whole delay.
    """
    from fish.observation import Observation
    from fish4.registry4 import make_agent

    room = _room(1, "one_team", bot_delay=12.0)
    _fill(room)
    room.pace(paused=True)
    room._held = 0.4                        # almost nothing banked
    b = make_agent(("fishbot4", {"opponent_gamma": 0.35}))
    b.begin_game(0, RULES, 5)
    room.state.turn = 0
    room.apply(0, b.act(Observation.from_state(room.state, 0)))
    assert room._held == 12.0, (
        f"a move made while paused banked {room._held}s, not the full delay")
    room.pace(paused=False)
    _bot_on_move(room)
    assert room.wait_left() > 11.0, (
        f"resumed with only {room.wait_left():.1f}s of a 12s wait")
    assert room.step_bot() is False


def test_pausing_before_any_countdown_does_not_bank_a_stale_wait():
    room = _room(1, "one_team", bot_delay=15.0)
    _fill(room)
    room.next_bot_at = 0.0                  # nothing pending
    room.pace(paused=True)
    assert room._held == 0.0
    room.pace(paused=False)
    _bot_on_move(room)
    assert room.wait_left() == 0.0, "invented a wait out of nothing"


def test_a_pace_change_is_reversible_and_does_not_resurrect_elapsed_time():
    """Two properties, and they pull in opposite directions.

    Changing the pace and changing it back must leave the pending move exactly
    where it was -- otherwise nudging the slider steals or gifts time. But a
    wait that expired for real, while the clock was running, must stay expired.
    """
    room = _room(1, "one_team", bot_delay=20.0)
    _fill(room)
    _bot_on_move(room)
    room.next_bot_at = time.time() + 2.0    # 2s left of a 20s wait
    room.pace(delay=1.0)                    # under a 1s pace it is long over
    assert room.wait_left() == 0.0
    room.pace(delay=20.0)
    assert 1.8 < room.wait_left() <= 2.05, (
        f"the round trip left {room.wait_left():.2f}s instead of 2s")

    # ...but real elapsed time is gone for good
    room.pace(delay=1.0)
    time.sleep(2.2)                         # the 2s would have expired anyway
    room.pace(delay=20.0)
    assert room.wait_left() == 0.0, (
        f"resurrected {room.wait_left():.1f}s that had already elapsed")


def test_a_watched_table_is_not_evicted_for_being_quiet():
    """A frozen table, or six people thinking, is not an abandoned table."""
    lob = Lobby(tick=100.0, ttl=0.25)
    try:
        room = lob.create(2, "one_team", "a", RULES, seed=7, bot_delay=0.0)
        _fill(room)
        room.pace(paused=True)
        room.updated -= 10.0                # nothing has happened in ages
        for s_ in room.seats:
            if s_.token:
                s_.last_seen -= 10.0
        assert time.time() - room.last_activity() > lob.ttl
        # ...but somebody polling counts as activity
        room.seat_of([s_ for s_ in room.seats if s_.token][0].token)
        assert time.time() - room.last_activity() < 0.2, (
            "a poll did not count as activity, so the table would be evicted")
    finally:
        lob.stop()


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
