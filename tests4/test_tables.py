"""Tables: quick play, join codes, the turn clock, and the information boundary.

A table is what the poker-style app plays on. Unlike a room it seats strangers
one at a time, deals on a host's word or a public countdown, and puts a clock on
every person's turn -- which on serverless is enforced by whoever polls next,
since nothing runs between requests. Most of what can go wrong here is about
time, so the tests pass ``now`` explicitly rather than sleeping.
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, team_of                     # noqa: E402
from api import _rooms                                          # noqa: E402
from api import _tables as T                                    # noqa: E402

T0 = 1_000_000.0


@pytest.fixture(autouse=True)
def _mem_store(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    _rooms.reset_store_for_tests(_rooms.MemoryStore())
    yield
    _rooms.reset_store_for_tests(None)


BANK = 30


def _private(n=1, turn=20, now=T0, bank=BANK):
    doc, seat, sec = T.new_table("Ada", public=False, turn=turn, now=now,
                                 bank=bank)
    secs = [sec]
    for i in range(1, n):
        secs.append(T.join(doc, f"P{i}", now=now)["secret"])
    return doc, secs


def _turn(doc):
    return T.session_for(doc, 0).state.turn


def _keep_alive(doc, now):
    for s in doc["seats"]:
        if s["kind"] == "human":
            s["seen"] = now


# ---------------------------------------------------------------------------
# Seating
# ---------------------------------------------------------------------------

def test_private_tables_seat_friends_on_one_team_first():
    doc, secs = _private(4)
    people = [s["seat"] for s in doc["seats"] if s["kind"] == "human"]
    assert people == [0, 1, 2, 4], people
    assert {team_of(p) for p in (0, 2, 4)} == {0}
    assert doc["host"] == 0


def test_public_tables_alternate_teams_so_strangers_spread_evenly():
    doc, _, _ = T.new_table("Ada", public=True, now=T0)
    for i in range(3):
        T.join(doc, f"P{i}", now=T0)
    people = [s["seat"] for s in doc["seats"] if s["kind"] == "human"]
    assert people == [0, 1, 2, 3]


def test_a_full_table_refuses_a_seventh_person():
    doc, _ = _private(6)
    with pytest.raises(ValueError, match="full"):
        T.join(doc, "Late", now=T0)


def test_nobody_joins_a_hand_in_progress():
    doc, secs = _private(1)
    T.start(doc, secs[0], now=T0)
    with pytest.raises(ValueError, match="started"):
        T.join(doc, "Late", now=T0)


def test_sitting_in_an_open_seat_is_how_you_pick_a_team_and_host_follows():
    doc, secs = _private(2)
    T.sit(doc, secs[0], 5, now=T0)
    assert doc["seats"][5]["kind"] == "human" and doc["seats"][0]["kind"] == "open"
    assert doc["host"] == 5
    with pytest.raises(ValueError, match="taken"):
        T.sit(doc, secs[0], 2, now=T0)


def test_only_the_host_starts_kicks_sets_bots_and_changes_settings():
    doc, secs = _private(2)
    for fn in (lambda: T.start(doc, secs[1], now=T0),
               lambda: T.kick(doc, secs[1], 0, now=T0),
               lambda: T.set_seat_kind(doc, secs[1], 4, "bot", now=T0),
               lambda: T.update_settings(doc, secs[1], turn=45, now=T0)):
        with pytest.raises(ValueError, match="host"):
            fn()
    T.set_seat_kind(doc, secs[0], 4, "bot", now=T0)
    assert doc["seats"][4]["kind"] == "bot"
    T.set_seat_kind(doc, secs[0], 4, "open", now=T0)
    assert doc["seats"][4]["kind"] == "open"
    T.kick(doc, secs[0], 2, now=T0)
    assert doc["seats"][2]["kind"] == "open"
    assert T.seat_of(doc, secs[1]) is None, "a kicked secret must stop working"


def test_starting_fills_every_open_seat_with_a_bot():
    doc, secs = _private(2)
    T.start(doc, secs[0], now=T0)
    kinds = [s["kind"] for s in doc["seats"]]
    assert kinds.count("human") == 2 and kinds.count("bot") == 4
    assert "open" not in kinds
    names = [s["name"] for s in doc["seats"]]
    assert len(set(names)) == NUM_PLAYERS, f"bot names collide: {names}"


# ---------------------------------------------------------------------------
# Public tables deal on their own
# ---------------------------------------------------------------------------

def test_a_public_table_deals_when_its_countdown_ends():
    doc, _, sec = T.new_table("Ada", public=True, now=T0)
    _keep_alive(doc, T0 + T.PUBLIC_WAIT - 1)
    assert not T.tick(doc, T0 + T.PUBLIC_WAIT - 1)
    assert doc["phase"] == "lobby"
    _keep_alive(doc, T0 + T.PUBLIC_WAIT)
    assert T.tick(doc, T0 + T.PUBLIC_WAIT)
    assert doc["phase"] == "playing"
    assert sum(s["kind"] == "bot" for s in doc["seats"]) == 5


def test_a_full_public_table_deals_at_once():
    doc, _, _ = T.new_table("Ada", public=True, now=T0)
    for i in range(5):
        T.join(doc, f"P{i}", now=T0)
    assert T.tick(doc, T0 + 1)
    assert doc["phase"] == "playing"
    assert all(s["kind"] == "human" for s in doc["seats"])


def test_joining_near_the_deadline_gets_a_grace_period_but_the_wait_is_capped():
    doc, _, _ = T.new_table("Ada", public=True, now=T0)
    late = T0 + T.PUBLIC_WAIT - 2
    T.join(doc, "Bo", now=late)
    assert doc["start_at"] == pytest.approx(late + T.PUBLIC_JOIN_GRACE)
    for k in range(20):
        T.join(doc, "X", now=T0 + 85 + k) if any(
            s["kind"] == "open" for s in doc["seats"]) else None
    assert doc["start_at"] <= T0 + T.PUBLIC_MAX_WAIT + 1e-9


def test_a_private_table_never_deals_on_its_own():
    doc, secs = _private(1)
    _keep_alive(doc, T0 + 600)
    T.tick(doc, T0 + 600)
    assert doc["phase"] == "lobby"


def test_a_lobby_seat_nobody_is_polling_is_freed_for_someone_else():
    doc, _, _ = T.new_table("Ada", public=True, now=T0)
    T.join(doc, "Bo", now=T0)
    doc["seats"][0]["seen"] = T0 - T.GONE_LOBBY_PUBLIC - 1     # Ada is gone
    doc["seats"][1]["seen"] = T0
    assert T.tick(doc, T0)
    assert doc["seats"][0]["kind"] == "open"
    assert doc["host"] == 1, "the host must pass to someone still here"


def test_the_last_person_leaving_a_lobby_closes_it():
    doc, secs = _private(1)
    T.leave(doc, secs[0], now=T0)
    assert doc["phase"] == "closed"


# ---------------------------------------------------------------------------
# Quick play and the public list
# ---------------------------------------------------------------------------

def test_quick_play_opens_a_table_when_none_exist_then_fills_it():
    a = T.quick_play("Ada")
    b = T.quick_play("Bo")
    assert a[0] == b[0], "the second player should land at the first table"
    assert b[1] != a[1]


def test_quick_play_prefers_the_fullest_table():
    small = T.quick_play("Ada")[0]
    big, _, _, doc = T.create("Cy", public=True)
    T.mutate(big, lambda d: (T.join(d, "Di"), True))
    code = T.quick_play("Ed")[0]
    assert code == big and code != small


def test_quick_play_never_lands_in_a_private_table():
    code, _, _, _ = T.create("Ada", public=False)
    got = T.quick_play("Bo")[0]
    assert got != code


def test_the_public_list_carries_no_secret_and_no_deal():
    code, _, sec, doc = T.create("Ada", public=True)
    blob = json.dumps(T.open_tables())
    assert code in blob
    assert sec not in blob
    _, stored = _rooms.store().read(code)
    assert stored["nonce"] not in blob


# ---------------------------------------------------------------------------
# The clock
# ---------------------------------------------------------------------------

def _started(turn=20):
    doc, secs = _private(1, turn=turn)
    T.start(doc, secs[0], now=T0)
    assert _turn(doc) == 0, "the host opens"
    return doc, secs


def test_a_persons_clock_is_the_turn_plus_their_whole_bank():
    doc, _ = _started(turn=15)
    c = doc["clock"]
    assert c["seat"] == 0 and not c["auto"]
    assert c["main_end"] == pytest.approx(T0 + 15)
    assert c["end"] == pytest.approx(T0 + 15 + BANK)


def test_nothing_happens_before_the_clock_and_bank_run_out():
    doc, _ = _started(turn=10)
    t = T0 + 10 + BANK - 0.5
    _keep_alive(doc, t)
    assert not T.tick(doc, t)
    assert doc["log"] == []


def test_an_expired_clock_plays_one_move_for_them_and_counts_a_timeout():
    doc, _ = _started(turn=10)
    t = T0 + 10 + BANK + 0.1
    _keep_alive(doc, t)
    assert T.tick(doc, t)
    assert len(doc["log"]) == 1
    me = doc["seats"][0]
    assert me["timeouts"] == 1 and me["bank"] == 0.0 and not me["away"]


def test_acting_late_spends_bank_and_acting_at_all_resets_timeouts():
    doc, secs = _started(turn=10)
    doc["seats"][0]["timeouts"] = 1
    s = T.session_for(doc, 0)
    T.act(doc, secs[0], s.suggest(), now=T0 + 10 + 7.5)
    me = doc["seats"][0]
    assert me["bank"] == pytest.approx(BANK - 7.5)
    assert me["timeouts"] == 0


def test_two_timeouts_in_a_row_mark_a_seat_away_and_back_clears_it():
    doc, secs = _started(turn=10)
    t = T0
    for _ in range(400):
        t += 1.0
        _keep_alive(doc, t)
        T.tick(doc, t)
        if doc["seats"][0]["away"] or doc["phase"] != "playing":
            break
    assert doc["seats"][0]["away"], "two missed turns should mark the seat away"
    T.back(doc, secs[0], now=t)
    assert not doc["seats"][0]["away"] and doc["seats"][0]["timeouts"] == 0


def test_an_away_seat_is_played_at_bot_speed():
    doc, _ = _started(turn=60)
    doc["seats"][0]["away"] = True
    T._set_clock(doc, T0)
    c = doc["clock"]
    assert c["auto"] and c["end"] == pytest.approx(T0 + T._pace(doc))


def test_a_person_who_stops_polling_is_not_waited_on_for_the_full_clock():
    doc, _ = _started(turn=90)
    doc["seats"][0]["seen"] = T0 - T.GONE_PLAYING - 1
    t = T0 + 1
    T.tick(doc, t)                    # notices the disconnection
    assert doc["clock"]["auto"]
    T.tick(doc, t + T._pace(doc) + 0.01)
    assert len(doc["log"]) == 1


def test_bots_move_at_the_tables_pace_and_at_most_once_a_poll():
    doc, secs = _started(turn=20)
    s = T.session_for(doc, 0)
    T.act(doc, secs[0], s.suggest(), now=T0)
    if _turn(doc) == 0:
        pytest.skip("the opening ask hit and kept the turn; covered elsewhere")
    n = len(doc["log"])
    pace = T._pace(doc)
    assert not T.tick(doc, T0 + pace - 0.05)
    assert T.tick(doc, T0 + pace + 0.05)
    assert len(doc["log"]) == n + 1, "one poll must not run several bot moves"


def test_no_limit_is_for_private_tables_only():
    doc, _ = _private(1, turn=0)
    assert doc["settings"]["turn"] == 0
    pub, _, _ = T.new_table("Ada", public=True, turn=0, now=T0)
    assert pub["settings"]["turn"] == T.TURN_DEFAULT
    junk, _, _ = T.new_table("Ada", public=False, turn=7, now=T0)
    assert junk["settings"]["turn"] == T.TURN_DEFAULT


def test_leaving_mid_game_hands_the_seat_to_a_bot_without_resetting_others():
    doc, secs = _private(2, turn=20)
    T.start(doc, secs[0], now=T0)
    clock_before = dict(doc["clock"])
    T.leave(doc, secs[1], now=T0 + 5)      # the person NOT on the move leaves
    assert doc["seats"][2]["kind"] == "bot"
    assert doc["seats"][2]["name"] == "P1", "the table must still recognise the seat"
    assert doc["clock"] == clock_before, "someone leaving must not re-arm the clock"
    assert doc["phase"] == "playing"


def test_a_whole_game_ends_with_a_result_and_rematch_rotates_the_opener():
    doc, secs = _private(2, turn=10)
    T.start(doc, secs[0], now=T0)
    t = T0
    for _ in range(20000):
        t += 1.0
        _keep_alive(doc, t)
        T.tick(doc, t)
        if doc["phase"] != "playing":
            break
    assert doc["phase"] == "over", "the game must end"
    r = doc["result"]
    # First to five: the game ends the moment a team has five of the nine,
    # so a finished table is decided at exactly five (or was stopped).
    assert r["stopped"] or (r["decided"] and max(r["score"]) == T.FIRST_TO)
    old_nonce, old_start = doc["nonce"], doc["start_seat"]
    with pytest.raises(ValueError, match="host"):
        T.rematch(doc, secs[1], now=t)
    T.rematch(doc, secs[0], now=t)
    assert doc["phase"] == "playing" and doc["game"] == 2
    assert doc["nonce"] != old_nonce, "a rematch must be a new deal"
    assert doc["start_seat"] == (old_start + 1) % NUM_PLAYERS
    assert all(s["bank"] == BANK for s in doc["seats"])


def _helper_seeds(session_for, doc, moves=6):
    seeds = []
    for _ in range(moves):
        seeds.append(session_for(doc, 0)._helper_seed)
        T._engine_move(doc, _turn(doc))
    return seeds


def test_replay_reseeds_at_the_current_ply_for_tables():
    """The livelock fix, tested directly rather than through a game ending.

    A game that livelocks still ENDS here, through the idle cap, so "the game
    finished" cannot tell the fix from its absence. What the fix changes is the
    seed: without the reseed every replay restarts the stream at ply 0, so the
    seed is the same at every ply.
    """
    doc, _ = _started()
    seeds = _helper_seeds(T.session_for, doc)
    assert len(set(seeds)) == len(seeds), f"seed did not move with the ply: {seeds}"


def test_replay_reseeds_at_the_current_ply_for_rooms_too():
    from api import _room_game as RG
    doc, _ = _started()
    seeds = _helper_seeds(RG.session_for, doc)
    assert len(set(seeds)) == len(seeds), f"seed did not move with the ply: {seeds}"


# ---------------------------------------------------------------------------
# Emotes
# ---------------------------------------------------------------------------

def test_emotes_are_preset_only_and_rate_limited():
    doc, secs = _private(1)
    T.emote(doc, secs[0], "gg", now=T0)
    with pytest.raises(ValueError, match="easy"):
        T.emote(doc, secs[0], "fish", now=T0 + 0.5)
    with pytest.raises(ValueError, match="unknown"):
        T.emote(doc, secs[0], "<script>", now=T0 + 5)
    v = T.view(doc, "ABCD", 0, 1, now=T0 + 1)
    assert v["seats"][0]["emote"]["id"] == "gg"
    v = T.view(doc, "ABCD", 0, 1, now=T0 + T.EMOTE_SHOW + 1)
    assert v["seats"][0]["emote"] is None


# ---------------------------------------------------------------------------
# The information boundary
# ---------------------------------------------------------------------------

def test_a_seats_view_never_carries_the_nonce_or_any_secret():
    doc, secs = _private(3)
    T.start(doc, secs[0], now=T0)
    for me in (0, 2, 4):
        blob = json.dumps(T.view(doc, "ABCD", me, 1, now=T0))
        assert doc["nonce"] not in blob
        for sec in secs:
            assert sec not in blob


def test_a_seat_sees_its_own_hand_and_only_counts_for_the_others():
    doc, secs = _private(2)
    T.start(doc, secs[0], now=T0)
    s = T.session_for(doc, 0)
    mine = {c for c in range(54) if s.state.hands[0] >> c & 1}
    theirs = {c for c in range(54) if s.state.hands[2] >> c & 1}
    v = T.view(doc, "ABCD", 0, 1, now=T0)
    assert {c["id"] for c in v["game"]["hand"]} == mine
    flagged = {c["id"] for hs in v["game"]["half_suits"] for c in hs["cards"]
               if c["mine"]}
    assert flagged == mine and not (flagged & theirs)
    assert v["seats"][2]["cards"] == len(theirs)


def test_a_seat_is_sent_only_the_last_two_moves_of_history():
    # Fish is a memory game. The limit is in what the SERVER sends, so no
    # client -- ours or a modified one -- can show an older move.
    doc, secs = _private(1)
    T.start(doc, secs[0], now=T0)
    for _ in range(12):
        T._engine_move(doc, _turn(doc))
    full = T.session_for(doc, 0).log
    assert len(full) == 12
    for me in (0,):
        g = T.view(doc, "ABCD", me, 1, now=T0)["game"]
        assert g["log"] == full[-T.HISTORY_VISIBLE:]
        assert len(g["log"]) == T.HISTORY_VISIBLE == 2
        blob = json.dumps(g)
        older = [json.dumps(e) for e in full[:-T.HISTORY_VISIBLE]]
        assert not any(o in blob for o in older if o not in
                       [json.dumps(e) for e in g["log"]])
    # the move counter is still whole, so the client can tell what is new
    assert T.view(doc, "ABCD", 0, 1, now=T0)["plies"] == 12


# ---------------------------------------------------------------------------
# The store: a quiet poll writes nothing, a lost race is retried
# ---------------------------------------------------------------------------

def test_a_poll_that_finds_nothing_due_writes_nothing():
    code, _, sec, _ = T.create("Ada", public=False)
    v0, _ = _rooms.store().read(code)
    _, _, v1 = T.mutate(code, lambda d: (None, False))
    assert v1 == v0 and _rooms.store().read(code)[0] == v0


def test_a_lost_compare_and_set_is_retried_not_dropped():
    code, _, sec, _ = T.create("Ada", public=False)
    st = _rooms.store()
    calls = {"n": 0}

    def racing(d):
        calls["n"] += 1
        if calls["n"] == 1:            # somebody else writes first
            v, other = st.read(code)
            other["touched"] += 1
            st.write(code, v, other)
        d["settings"]["turn"] = 45
        return None, True

    T.mutate(code, racing)
    assert calls["n"] == 2
    assert st.read(code)[1]["settings"]["turn"] == 45


# ---------------------------------------------------------------------------
# Over HTTP, through the real handler
# ---------------------------------------------------------------------------

@pytest.fixture
def server():
    from api.index import handler
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _post(base, op, body, origin=None):
    req = Request(f"{base}/api/index?op={op}", data=json.dumps(body).encode(),
                  headers={"Content-Type": "application/json",
                           **({"Origin": origin} if origin else {})},
                  method="POST")
    try:
        with urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read()), dict(r.headers)
    except Exception as e:                      # HTTPError carries a body
        return e.code, json.loads(e.read()), dict(e.headers)


def test_routes_quick_play_join_poll_and_act_end_to_end(server):
    st, a, _ = _post(server, "t_quick", {"name": "Ada"})
    assert st == 200 and a["table"]["phase"] == "lobby"
    code = a["code"]
    st, b, _ = _post(server, "t_join", {"code": code, "name": "Bo"})
    assert st == 200 and b["table"]["me"] != a["table"]["me"]
    st, out, _ = _post(server, "t_start", {"code": code, "secret": b["secret"]})
    assert st == 400 and "host" in out["error"]
    st, out, _ = _post(server, "t_start", {"code": code, "secret": a["secret"]})
    assert st == 200 and out["table"]["phase"] == "playing"
    st, poll, _ = _post(server, "t_state", {"code": code, "secret": a["secret"]})
    game = poll["table"]["game"]
    assert game["your_turn"], "the host opens"
    hs = game["hand"][0]["hs"]
    card = next(c["id"] for c in game["half_suits"][hs]["cards"]
                if not c["mine"])
    target = next(s["seat"] for s in poll["table"]["seats"]
                  if s["team"] != poll["table"]["seats"][poll["table"]["me"]]["team"]
                  and s["cards"])
    st, after, _ = _post(server, "t_act", {
        "code": code, "secret": a["secret"],
        "action": {"type": "ask", "target": target, "card": card}})
    assert st == 200 and len(after["table"]["game"]["log"]) == 1
    st, out, _ = _post(server, "t_act", {
        "code": code, "secret": "forged",
        "action": {"type": "ask", "target": target, "card": card}})
    assert st == 400 and "not seated" in out["error"]


def test_a_missing_table_is_a_clean_404(server):
    st, out, _ = _post(server, "t_join", {"code": "ZZZZ", "name": "X"})
    assert st == 404 and out["error"] == "no such table"


def test_cors_admits_the_app_shell_and_nobody_else(server):
    _, _, h = _post(server, "t_list", {}, origin="capacitor://localhost")
    assert h.get("Access-Control-Allow-Origin") == "capacitor://localhost"
    _, _, h = _post(server, "t_list", {}, origin="https://evil.example")
    assert "Access-Control-Allow-Origin" not in h
    req = Request(f"{server}/api/index?op=t_state", method="OPTIONS",
                  headers={"Origin": "capacitor://localhost",
                           "Access-Control-Request-Method": "POST"})
    with urlopen(req, timeout=10) as r:
        assert r.status == 204
        assert r.headers["Access-Control-Allow-Origin"] == "capacitor://localhost"
        assert "Content-Type" in r.headers["Access-Control-Allow-Headers"]


def test_tables_refuse_like_rooms_when_deployed_without_a_shared_store(
        server, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    st, out, _ = _post(server, "t_quick", {"name": "Ada"})
    assert st == 503 and "SUPABASE_URL" in out["error"]


def test_solo_step_zero_means_zero_engine_moves(server):
    """`step: 0` must cap the engine at zero moves, not lift the cap.

    The app paces the bots itself, one request per move, so that each move can
    be shown. `step not in (None, "", False)` read 0 as False -- 0 == False in
    Python -- and played every engine move up to the person's turn in the same
    response, so the whole possession arrived at once.
    """
    st, d, _ = _post(server, "new", {"step": 0})
    assert st == 200 and d["your_turn"], "the person opens a solo game"
    hs = d["hand"][0]["hs"]
    card = next(c["id"] for c in d["half_suits"][hs]["cards"] if not c["mine"])
    target = next(p for p in range(1, 6, 2) if d["hand_counts"][p] > 0)
    st, out, _ = _post(server, "act", {
        "token": d["token"], "actions": d["actions"], "step": 0,
        "action": {"type": "ask", "target": target, "card": card}})
    assert st == 200
    assert len(out["actions"]) == 1, (
        f"step 0 played {len(out['actions'])} moves, not just the person's own")


def test_one_malformed_row_does_not_take_down_the_public_list():
    """The store is shared, so the list must survive a row it cannot read.

    Found for real: a probe row written while switching the live database on
    carried kind/public/phase but no seats, and every t_list and Quick Play
    raised KeyError summarising it.
    """
    good, _, _, _ = T.create("Ada", public=True)
    _rooms.store().create({"kind": "table", "public": True, "phase": "lobby",
                           "touched": __import__("time").time()})
    codes = [t["code"] for t in T.open_tables()]
    assert codes == [good]
    assert T.quick_play("Bo")[0] == good


# ---------------------------------------------------------------------------
# First to five
# ---------------------------------------------------------------------------

def test_an_app_game_ends_the_moment_a_team_has_five():
    doc, secs = _private(1)
    T.start(doc, secs[0], now=T0)
    assert doc["first_to"] == T.FIRST_TO == 5
    for _ in range(600):
        s = T.session_for(doc, 0)
        if s.over:
            break
        before = max(s.state.scores()[:2])
        assert before < 5, "play continued after a team had five"
        T._engine_move(doc, _turn(doc))
    T._set_clock(doc, T0)
    s = T.session_for(doc, 0)
    a, b, _ = s.state.scores()
    assert doc["phase"] == "over" and s.decided and max(a, b) == 5
    # the rest were never played -- unless it went 4-4 into the last set
    assert not s.state.is_terminal or sorted((a, b)) == [4, 5]
    assert doc["result"]["winner"] == (0 if a > b else 1)
    # nothing is hidden once it is over: the reveal covers all 54 cards
    v = T.view(doc, "ABCD", 0, 1, now=T0)
    assert sum(len(row) for row in v["game"]["reveal"]) == 54
    # and nobody can move after it
    from fish.engine import Ask
    with pytest.raises(ValueError):
        T.act(doc, secs[0], Ask(1, 0), now=T0)


def test_first_to_rides_in_the_token_and_full_games_are_unchanged():
    from api._engine import Session, new_session, clean_first_to
    s = new_session({"first_to": 5})
    assert s.first_to == 5
    r = Session.restore(s.token(), [])
    assert r.first_to == 5
    full = new_session({})
    assert full.first_to is None
    assert Session.restore(full.token(), []).first_to is None
    # a rule that could name two winners is refused, not honoured
    assert clean_first_to(4) is None and clean_first_to("x") is None
    assert clean_first_to(9) == 9


def test_a_practice_game_dealt_first_to_five_stops_at_five():
    from api._engine import new_session, Session
    s = new_session({"first_to": 5})
    for _ in range(400):
        if s.over:
            break
        if s.state.turn == s.seat:
            s.play(s.suggest(), max_moves=0)
        else:
            s.advance(1)
        # every request rebuilds the game from the token: so must this
        s = Session.restore(s.token(), s.wire_log)
    snap = s.snapshot()
    assert snap["terminal"] and snap["decided"] and snap["first_to"] == 5
    assert max(snap["score"]["you"], snap["score"]["them"]) == 5
    assert not snap["your_turn"]


# ---------------------------------------------------------------------------
# Only the last two moves, in solo games too
# ---------------------------------------------------------------------------

def _solo_play(server, d, moves):
    """Drive a hidden-log solo game through the real routes, as the app does."""
    for _ in range(moves):
        if d["terminal"]:
            break
        body = {"token": d["token"], "actions": [], "step": 0 if d["your_turn"] else 1}
        if d["your_turn"]:
            st, d, _ = _post(server, "auto", body)
        else:
            st, d, _ = _post(server, "step", body)
        assert st == 200, d
        assert d["actions"] == [], "a memory-rule game must not hand out its moves"
        assert len(d["log"]) <= 2
    return d


def test_a_solo_app_game_never_sends_more_than_two_moves(server):
    st, d, _ = _post(server, "new", {"step": 0, "first_to": 5, "history": 2})
    assert st == 200 and d["history_visible"] == 2 and d["actions"] == []
    d = _solo_play(server, d, 30)
    assert d["plies"] > 2 and len(d["log"]) == 2
    # the token is opaque: no card, seat or move is readable in it
    import base64
    body = d["token"].split(".")[0]
    raw = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    assert set(raw) >= {"x", "k", "h"} and raw["k"] == 2
    import zlib
    x = raw["x"]
    blob = base64.urlsafe_b64decode(x + "=" * (-len(x) % 4))
    for skip in (0, 12):
        with pytest.raises(zlib.error):
            zlib.decompress(blob[skip:])
    # and whatever log a client sends is ignored, so it cannot feed one in
    st, same, _ = _post(server, "state", {"token": d["token"],
                                          "actions": [["junk"]]})
    assert st == 200 and same["plies"] == d["plies"]


def test_whole_record_helpers_are_closed_during_a_memory_rule_game(server):
    st, d, _ = _post(server, "new", {"step": 0, "history": 2})
    for op in ("deduce", "analyse"):
        st, out, _ = _post(server, op, {"token": d["token"]})
        assert st == 400 and "last 2 moves" in out["error"], op
    st, out, _ = _post(server, "claimcheck", {"token": d["token"],
                                              "half_suit": 0,
                                              "assignment": [0] * 6})
    assert st == 400 and "last 2 moves" in out["error"]


def test_a_tampered_hidden_log_is_refused(server):
    st, d, _ = _post(server, "new", {"step": 0, "history": 2})
    body, sig = d["token"].split(".")
    flipped = body[:-3] + ("A" if body[-3] != "A" else "B") + body[-2:]
    st, out, _ = _post(server, "state", {"token": flipped + "." + sig})
    assert st == 400 and "expired" in out["error"]


def test_the_research_site_still_gets_the_whole_record(server):
    st, d, _ = _post(server, "new", {"step": 0})
    assert st == 200 and d["history_visible"] is None
    hs = d["hand"][0]["hs"]
    card = next(c["id"] for c in d["half_suits"][hs]["cards"] if not c["mine"])
    target = next(p for p in range(1, 6, 2) if d["hand_counts"][p] > 0)
    st, out, _ = _post(server, "act", {
        "token": d["token"], "actions": d["actions"], "step": 0,
        "action": {"type": "ask", "target": target, "card": card}})
    assert st == 200 and len(out["actions"]) == 1


def test_hidden_log_round_trips_a_whole_game():
    from api._engine import Session, new_session
    s = new_session({"history": 2, "first_to": 5})
    for _ in range(400):
        if s.over:
            break
        if s.state.turn == s.seat:
            s.play(s.suggest(), max_moves=0)
        else:
            s.advance(1)
        s = Session.restore(s.token(), [])      # the client sends nothing back
    snap = s.snapshot()
    assert snap["terminal"] and len(snap["log"]) == 2 and snap["plies"] > 2
    assert sum(len(r) for r in snap["reveal"]) == 54


# ---------------------------------------------------------------------------
# The clock: 20 seconds a move in public; the host's choice in private
# ---------------------------------------------------------------------------

def test_a_public_table_is_twenty_seconds_a_move_with_no_bank():
    doc, secs = None, []
    doc, _, sec = T.new_table("Ada", public=True, turn=90, bank=60, now=T0)
    assert doc["settings"]["turn"] == 20 and doc["settings"]["bank"] == 0
    with pytest.raises(ValueError):
        T.update_settings(doc, "not the host", turn=60, now=T0)
    T.update_settings(doc, sec, turn=60, bank=30, now=T0)
    assert doc["settings"]["turn"] == 20 and doc["settings"]["bank"] == 0
    T.start(doc, sec, now=T0)
    c = doc["clock"]
    if not c["auto"]:
        assert c["main_end"] == pytest.approx(c["start"] + 20)
        assert c["end"] == c["main_end"], "no time bank on a public table"
    assert all(s["bank"] == 0 for s in doc["seats"])


def test_a_private_table_defaults_to_twenty_seconds_and_no_bank():
    doc, secs = _private(1, bank=T.BANK_DEFAULT)
    assert doc["settings"] == {"turn": 20, "bank": 0, "pace": T.PACE_DEFAULT}
    T.start(doc, secs[0], now=T0)
    c = doc["clock"]
    assert c["main_end"] == pytest.approx(T0 + 20) and c["end"] == c["main_end"]


def test_the_private_host_sets_the_turn_time_and_bank_between_games():
    doc, secs = _private(2, bank=0)
    with pytest.raises(ValueError, match="host"):
        T.update_settings(doc, secs[1], turn=45, bank=30, now=T0)
    T.update_settings(doc, secs[0], turn=45, bank=60, now=T0)
    assert doc["settings"]["turn"] == 45 and doc["settings"]["bank"] == 60
    T.update_settings(doc, secs[0], bank=7, now=T0)       # not a choice
    assert doc["settings"]["bank"] == T.BANK_DEFAULT
    T.update_settings(doc, secs[0], bank=60, now=T0)
    T.start(doc, secs[0], now=T0)
    c = doc["clock"]
    assert c["main_end"] == pytest.approx(T0 + 45)
    assert c["end"] == pytest.approx(T0 + 45 + 60)
    with pytest.raises(ValueError):
        T.update_settings(doc, secs[0], turn=10, now=T0), "not mid-game"


# ---------------------------------------------------------------------------
# The deal is stored, so a table survives instances that disagree about keys
# ---------------------------------------------------------------------------
#
# The "kicked out of a private table after a few asks" bug. The deal used to be
# derived from the nonce with FISH_SECRET; with the variable unset every
# serverless instance had its own key, so a poll served by a second instance
# rebuilt a different deal, the stored log stopped replaying, the engine's
# IllegalAction came back as a 400, and the app left the table on any 400.

KEY_A = "a" * 32
KEY_B = "b" * 32


def _hands(doc, seat=0):
    return list(T.session_for(doc, seat).state.hands)     # one bitmask a seat


def test_a_deal_stores_a_random_seed_and_a_rematch_draws_a_new_one():
    doc, secs = _private(1)
    assert "seed" not in doc, "a lobby has no deal yet"
    T.start(doc, secs[0], now=T0)
    seed = doc["seed"]
    assert isinstance(seed, str) and len(seed) == 64
    int(seed, 16)                                       # 256 bits of hex
    assert T.session_for(doc, 0).seed == int(seed, 16)
    # A rematch is a new deal, with its own seed.
    while doc["phase"] == "playing":
        T._engine_move(doc, _turn(doc))
        T.tick(doc, now=T0)
        if T.session_for(doc, 0).over:
            doc["phase"] = "over"
    T.rematch(doc, secs[0], now=T0 + 1)
    assert doc["seed"] != seed


def test_the_stored_seed_is_used_so_a_key_change_does_not_change_the_deal(
        monkeypatch):
    from api import _engine as E
    from api import _room_game as RG
    monkeypatch.setenv("FISH_SECRET", KEY_A)
    doc, secs = _private(1)
    T.start(doc, secs[0], now=T0)
    for _ in range(4):                                  # a few asks in
        T._engine_move(doc, _turn(doc))
    before = _hands(doc)
    assert len(doc["log"]) == 4

    # The instance that serves the next poll holds a different key -- or none.
    for key in (KEY_B, None):
        if key is None:
            monkeypatch.delenv("FISH_SECRET", raising=False)
        else:
            monkeypatch.setenv("FISH_SECRET", key)
        assert _hands(doc) == before, "the deal moved with the key"
        assert T.session_for(doc, 0).state.turn == _turn(doc)
        assert RG.session_for(doc, 0).seed == int(doc["seed"], 16)
        # ...which it would have, had the seed still come from the nonce.
        assert E.seed_from_nonce(doc["nonce"]) != int(doc["seed"], 16)
        T.view(doc, "ABCD", 0, 1, now=T0)              # no ReplayError


def test_a_game_dealt_before_seeds_were_stored_still_uses_its_nonce(
        monkeypatch):
    from api import _engine as E
    monkeypatch.setenv("FISH_SECRET", KEY_A)
    doc, secs = _private(1)
    T.start(doc, secs[0], now=T0)
    del doc["seed"]                                    # an older document
    T._engine_move(doc, _turn(doc))
    s = T.session_for(doc, 0)
    assert s.seed == E.seed_from_nonce(doc["nonce"])
    assert len(s.wire_log) == 1


def test_a_log_that_will_not_replay_raises_a_runtime_error_not_illegal_action():
    from api._engine import ReplayError
    from api import _room_game as RG
    doc, secs = _private(1)
    T.start(doc, secs[0], now=T0)
    turn = _turn(doc)
    # Asking your own teammate is illegal on every deal there is.
    doc["log"] = [{"t": "ask", "target": (turn + 2) % NUM_PLAYERS, "card": 0}]
    for session_for in (T.session_for, RG.session_for):
        with pytest.raises(ReplayError) as info:
            session_for(doc, 0)
        assert isinstance(info.value, RuntimeError)
        assert info.value.ply == 0
        assert str(info.value) == ReplayError.MESSAGE, \
            "the engine's message describes hands; it must not be shown"


def test_no_view_or_list_ever_carries_the_seed():
    doc, secs = _private(3)
    T.start(doc, secs[0], now=T0)
    for _ in range(3):
        T._engine_move(doc, _turn(doc))
    seed = doc["seed"]
    leaks = (seed, str(int(seed, 16)), seed[:16])
    for me in range(NUM_PLAYERS):
        blob = json.dumps(T.view(doc, "ABCD", me, 1, now=T0))
        assert not any(x in blob for x in leaks), f"seat {me} saw the seed"
    pub, _, _ = T.new_table("Bo", public=True, now=T0)
    T._deal(pub, T0)
    blob = json.dumps(T.lobby_summary("WXYZ", pub, T0))
    assert pub["seed"] not in blob and str(int(pub["seed"], 16)) not in blob


def _corrupt(code, entry):
    st = _rooms.store()
    version, doc = st.read(code)
    doc["log"] = [entry]
    st.write(code, version, doc)
    return doc


def test_a_log_that_will_not_replay_is_a_503_the_app_retries(server):
    st, a, _ = _post(server, "t_create", {"name": "Ada", "public": False})
    code, sec = a["code"], a["secret"]
    st, out, _ = _post(server, "t_start", {"code": code, "secret": sec})
    assert st == 200
    turn = out["table"]["game"]["turn"]
    _corrupt(code, {"t": "ask", "target": (turn + 2) % NUM_PLAYERS, "card": 0})
    st, out, _ = _post(server, "t_state", {"code": code, "secret": sec})
    assert st == 503, out
    from api._engine import ReplayError
    assert out["error"] == ReplayError.MESSAGE
    # The seat is still there: "not seated" is the only 400 the app leaves on.
    st, out, _ = _post(server, "t_state", {"code": code, "secret": "forged"})
    assert st == 400 and "not seated" in out["error"]


def test_a_room_log_that_will_not_replay_is_a_503_too(server):
    st, r, _ = _post(server, "room_new", {"humans": 1, "name": "Ada"})
    code, sec = r["code"], r["secret"]
    st, out, _ = _post(server, "room_ready", {"code": code, "secret": sec})
    assert st == 200 and out.get("phase", "playing") == "playing"
    _, doc = _rooms.store().read(code)
    assert len(doc["seed"]) == 64, "a room stores its deal when it starts"
    turn = int(doc["start_seat"])
    _corrupt(code, {"t": "ask", "target": (turn + 2) % NUM_PLAYERS, "card": 0})
    st, out, _ = _post(server, "room_state", {"code": code, "secret": sec})
    assert st == 503, out


def _health(base):
    with urlopen(f"{base}/api/health", timeout=20) as r:
        return json.loads(r.read())


def test_health_says_whether_the_signing_key_is_configured(server, monkeypatch):
    monkeypatch.delenv("FISH_SECRET", raising=False)
    assert _health(server)["signing_key"] == "ephemeral"
    monkeypatch.setenv("FISH_SECRET", "too-short")
    assert _health(server)["signing_key"] == "ephemeral", "under 16 bytes"
    monkeypatch.setenv("FISH_SECRET", KEY_A)
    h = _health(server)
    assert h["signing_key"] == "configured"
    assert KEY_A not in json.dumps(h), "only the state, never the key"


def test_a_serverless_instance_without_the_key_warns(monkeypatch):
    import io
    from api.index import warn_without_signing_key
    monkeypatch.delenv("FISH_SECRET", raising=False)
    out = io.StringIO()
    assert warn_without_signing_key({"VERCEL": "1"}, out)
    assert "FISH_SECRET" in out.getvalue()
    assert not warn_without_signing_key({}, io.StringIO()), "local: no warning"
    monkeypatch.setenv("FISH_SECRET", KEY_A)
    assert not warn_without_signing_key({"VERCEL": "1"}, io.StringIO())
