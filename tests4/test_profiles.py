"""Profiles, ratings and fair play at the table.

What has to hold: a rated game is applied once and only once however many
phones poll it; leaving or idling cannot dodge a loss or farm a win; private
tables are never rated; a profile's secret and fair-play numbers never reach
another player; one profile takes one seat; and the fair-play tests flag a
cheater's record and not an honest one's.
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api import _fairplay as F                                  # noqa: E402
from api import _profiles as P                                  # noqa: E402
from api import _rooms                                          # noqa: E402
from api import _tables as T                                    # noqa: E402

import time                                                     # noqa: E402

#: Real time: the memory store sweeps tables whose clock looks hours stale.
T0 = time.time()


@pytest.fixture(autouse=True)
def _stores(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    monkeypatch.delenv("FISH_ADMIN_KEY", raising=False)
    _rooms.reset_store_for_tests(_rooms.MemoryStore())
    P.reset_for_tests(P.MemoryProfiles())
    yield
    _rooms.reset_store_for_tests(None)
    P.reset_for_tests(None)


def _profile(name, rating=None, games=0):
    pid, sec, doc = P.create(name, now=T0)
    if rating is not None or games:
        def fn(d):
            d["rating"] = float(rating if rating is not None else d["rating"])
            d["games"] = games
            return True
        P._update(pid, fn)
    return pid, sec


def _card(pid, sec):
    return P.seat_card(P.auth(pid, sec))


def _public_table(cards):
    """A public table with the given profiles seated, dealt, in the store."""
    doc, seat, sec = T.new_table("A", public=True, now=T0, card=cards[0])
    secs = [sec]
    for c in cards[1:]:
        secs.append(T.join(doc, "B", now=T0, card=c)["secret"])
    T._deal(doc, T0)
    code = _rooms.store().create(doc)
    return code, doc, secs


def _play_out(code, doc, secs):
    """Play to the end: people move through act(), bots through the engine."""
    by_seat = {T.seat_of(doc, s): s for s in secs}
    for _ in range(600):
        s0 = T.session_for(doc, 0)
        if s0.over:
            break
        turn = int(s0.state.turn)
        if turn in by_seat and doc["seats"][turn]["kind"] == "human":
            mine = T.session_for(doc, turn)
            T.act(doc, by_seat[turn], mine.suggest(), now=T0)
        else:
            T._engine_move(doc, turn)
            T._set_clock(doc, T0)
    T._set_clock(doc, T0)
    st = _rooms.store()
    v, _ = st.read(code)
    v = st.write(code, v, doc)
    return doc, v


# ---------------------------------------------------------------------------
# Elo
# ---------------------------------------------------------------------------

def test_expected_score_is_symmetric_and_even_at_equal_ratings():
    assert P.expected(1500, 1500) == pytest.approx(0.5)
    assert P.expected(1600, 1400) + P.expected(1400, 1600) == pytest.approx(1)
    assert P.expected(1900, 1500) > 0.9


def _rated_doc(ratings, winner, by=None, left=()):
    seats = {str(i): {"pid": f"p{i}", "rating": r, "games": 20}
             for i, r in ratings.items()}
    return {"rated": {"key": "gX", "seats": seats},
            "result": {"winner": winner, "score": [5, 4] if winner == 0 else [4, 5]},
            "by": by or [], "left": list(left)}


def test_winners_gain_losers_lose_and_bots_anchor_at_1500():
    pl = P.plan(_rated_doc({0: 1500.0, 1: 1500.0}, winner=0))
    assert pl[0]["delta"] == pytest.approx(P.K_SETTLED * 0.5)
    assert pl[1]["delta"] == pytest.approx(-P.K_SETTLED * 0.5)
    # A strong player beating a team of bots gains less than an even game
    # pays. Their team is them plus two 1500 bots: a mean of 1700, E = 0.76.
    pl = P.plan(_rated_doc({0: 2100.0}, winner=0))
    assert pl[0]["expected"] == pytest.approx(P.expected(1700, 1500), abs=1e-3)
    assert 0 < pl[0]["delta"] < P.K_SETTLED * 0.5


def test_leaving_a_rated_game_is_a_loss_even_if_your_team_wins():
    pl = P.plan(_rated_doc({0: 1500.0, 1: 1500.0}, winner=0, left=[0]))
    assert pl[0]["abandoned"] and pl[0]["delta"] < 0


def test_letting_the_engine_play_for_you_cannot_win_rating():
    by = [[0, "e"]] * 6 + [[0, "h"]] * 4          # 60% engine-played
    pl = P.plan(_rated_doc({0: 1500.0, 1: 1500.0}, winner=0, by=by))
    assert pl[0]["autopilot"] and pl[0]["delta"] == 0.0
    pl = P.plan(_rated_doc({0: 1500.0, 1: 1500.0}, winner=1, by=by))
    assert pl[0]["delta"] < 0                      # but it can still lose it


def test_new_players_move_faster_than_settled_ones():
    assert P.k_factor(0) == P.K_NEW > P.k_factor(P.PROVISIONAL) == P.K_SETTLED


# ---------------------------------------------------------------------------
# Tables: rated or not, seats, settling
# ---------------------------------------------------------------------------

def test_private_tables_are_never_rated():
    a = _profile("Ada")
    doc, seat, sec = T.new_table("Ada", public=False, now=T0, card=_card(*a))
    T.start(doc, sec, now=T0)
    assert doc["rated"] is None


def test_one_profile_takes_one_seat():
    a = _profile("Ada")
    doc, seat, sec = T.new_table("Ada", public=True, now=T0, card=_card(*a))
    with pytest.raises(ValueError):
        T.join(doc, "Ada again", now=T0, card=_card(*a))


def test_a_public_game_is_rated_settled_once_and_shown_on_the_results():
    a, b = _profile("Ada"), _profile("Bo")
    code, doc, secs = _public_table([_card(*a), _card(*b)])
    assert doc["rated"] and set(doc["rated"]["seats"]) == {"0", "1"}
    doc, v = _play_out(code, doc, secs)
    assert doc["phase"] == "over"
    doc, v2 = T.maybe_settle(code, doc, v)
    assert doc["settled"] == doc["rated"]["key"]
    ratings = doc["result"]["ratings"]
    winner = doc["result"]["winner"]
    for seat, pid in ((0, a[0]), (1, b[0])):
        prof = P.get(pid)
        assert prof["games"] == 1
        assert ratings[str(seat)]["rating"] == prof["rating"]
        gained = ratings[str(seat)]["delta"] > 0
        assert gained == (winner == seat % 2)
    # A second poll, or a second phone, changes nothing.
    again, _ = T.maybe_settle(code, doc, v2)
    assert P.get(a[0])["games"] == 1
    assert P.settle(again) is not None and P.get(b[0])["games"] == 1


def test_fair_play_rows_are_kept_for_people_at_rated_tables_only():
    a = _profile("Ada")
    code, doc, secs = _public_table([_card(*a)])
    me = T.seat_of(doc, secs[0])
    for _ in range(200):
        s0 = T.session_for(doc, 0)
        if s0.over or doc["fair"]:
            break
        turn = int(s0.state.turn)
        if turn == me:
            T.act(doc, secs[0], T.session_for(doc, me).suggest(), now=T0 + 3,
                  focus_lost=True)
        else:
            T._engine_move(doc, turn)
            T._set_clock(doc, T0)
    row = doc["fair"][0]
    assert row["s"] == me and row["k"] in ("a", "c")
    assert 0.0 <= row["p"] <= 1.0 and row["o"] in (0, 1) and row["f"] == 1
    # No rows for anyone on a private table.
    doc2, _, sec2 = T.new_table("Ada", public=False, now=T0, card=_card(*a))
    T.start(doc2, sec2, now=T0)
    s = T.session_for(doc2, 0)
    if s.state.turn == 0:
        T.act(doc2, sec2, s.suggest(), now=T0)
    assert doc2["fair"] == []


def test_the_table_view_shows_ratings_and_never_a_profile_secret():
    a = _profile("Ada", rating=1612)
    code, doc, secs = _public_table([_card(*a)])
    blob = json.dumps(T.view(doc, code, 0, 1, now=T0))
    assert a[1] not in blob
    v = T.view(doc, code, 0, 1, now=T0)
    assert v["seats"][0]["rating"] == 1612 and v["seats"][0]["pid"] == a[0]
    assert v["rated"] is True


# ---------------------------------------------------------------------------
# Profiles
# ---------------------------------------------------------------------------

def test_a_profile_proves_itself_with_its_secret_and_shows_nothing_private():
    pid, sec = _profile("Ada")
    with pytest.raises(ValueError):
        P.auth(pid, "wrong")
    pub = P.get(pid)
    blob = json.dumps(pub)
    for private in ("secret_sha", "fair", "reporters", "applied", sec):
        assert private not in blob


def test_deleting_a_profile_removes_it():
    pid, sec = _profile("Ada")
    P.delete(pid, sec)
    with pytest.raises(_rooms.NotFound):
        P.get(pid)


def test_reports_count_once_per_reporter_and_never_yourself():
    a, b = _profile("Ada"), _profile("Bo")
    P.report(a[0], a[1], b[0], "cheating")
    P.report(a[0], a[1], b[0], "cheating")
    _, d = P.profiles().read(b[0])
    assert d["reports"] == {"cheating": 1}
    with pytest.raises(ValueError):
        P.report(a[0], a[1], a[0], "cheating")


def test_the_leaderboard_lists_established_unflagged_players_by_rating():
    hi = _profile("Hi", rating=1700, games=10)
    lo = _profile("Lo", rating=1550, games=10)
    _profile("New", rating=1900, games=2)          # too few games
    cheat = _profile("Sus", rating=1800, games=10)
    P._update(cheat[0], lambda d: d.update(fair={
        **F.empty(), "asks": 100, "hits": 95, "ask_exp": 50.0,
        "ask_var": 20.0}) or True)
    names = [p["name"] for p in P.leaderboard()]
    assert names == ["Hi", "Lo"]


def test_a_ban_refunds_what_opponents_lost_once():
    a, b = _profile("Ada"), _profile("Bo")
    code, doc, secs = _public_table([_card(*a), _card(*b)])
    doc, v = _play_out(code, doc, secs)
    T.maybe_settle(code, doc, v)
    loser = a if P.get(a[0])["rating"] < 1500 else b
    winner = b if loser is a else a
    lost = 1500 - P.get(loser[0])["rating"]
    assert lost > 0
    P.ban(winner[0])
    assert P.get(loser[0])["rating"] == 1500
    P.ban(winner[0])                               # again: no double refund
    assert P.get(loser[0])["rating"] == 1500
    with pytest.raises(ValueError):
        P.auth(*winner)                            # closed


# ---------------------------------------------------------------------------
# The fair-play rules on synthetic records
# ---------------------------------------------------------------------------

def _record(asks, excess, p=0.6):
    exp = asks * p
    return {**F.empty(), "asks": asks, "hits": round(exp + excess * asks),
            "ask_exp": exp, "ask_var": asks * p * (1 - p)}


def test_an_honest_record_with_the_measured_bias_is_not_flagged_at_any_length():
    for n in (40, 400, 4000, 40000):
        assert F.flags(_record(n, 0.037)) == []


def test_a_peeking_record_is_flagged():
    assert [f["rule"] for f in F.flags(_record(60, 0.31))] == ["asks"]


def test_declarations_beyond_the_evidence_are_flagged_and_honest_ones_not():
    # About ten games of a team reading its hands to each other: every one of
    # 60 declarations right, where the evidence supported half of them.
    t = {**F.empty(), "claims": 60, "right": 60, "claim_exp": 30.0,
         "claim_var": 10.0}
    assert "declarations" in [f["rule"] for f in F.flags(t)]
    # The best honest declarer measured beat the posterior by 0.082 a claim.
    honest = dict(t, right=round(30 + 0.082 * 60))
    assert F.flags(honest) == []


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@pytest.fixture
def server():
    from api.index import handler
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _post(base, op, body):
    req = Request(f"{base}/api/{op}", data=json.dumps(body).encode(),
                  headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req) as r:
            return r.status, json.loads(r.read())
    except HTTPError as e:
        return e.code, json.loads(e.read())


def test_routes_make_a_profile_and_carry_it_to_a_quick_play_seat(server):
    st, out = _post(server, "p_new", {"name": "Ada"})
    assert st == 200 and out["profile"]["rating"] == 1500
    pid, sec = out["id"], out["secret"]
    st, t = _post(server, "t_quick", {"name": "x", "pid": pid, "psecret": sec})
    assert st == 200
    me = t["table"]["me"]
    assert t["table"]["seats"][me]["pid"] == pid
    assert t["table"]["seats"][me]["name"] == "Ada"   # the profile's name
    st, bad = _post(server, "t_quick", {"pid": pid, "psecret": "nope"})
    assert st == 403 and bad["profile_invalid"]
    st, got = _post(server, "p_get", {"id": pid})
    assert st == 200 and got["profile"]["name"] == "Ada"
    st, _ = _post(server, "p_top", {})
    assert st == 200


def test_review_routes_are_a_plain_404_without_the_admin_key(server, monkeypatch):
    st, _ = _post(server, "p_review", {"admin": "x" * 40})
    assert st == 404
    monkeypatch.setenv("FISH_ADMIN_KEY", "k" * 40)
    st, out = _post(server, "p_review", {"admin": "k" * 40})
    assert st == 200 and out["queue"] == []


def test_a_database_without_the_profile_functions_reads_as_ratings_off():
    # Until scripts4/profile_rpc.sql is applied every fish_profile_* call is a
    # 404 from PostgREST; that must surface as "not switched on" (a 503 the
    # app understands and plays unrated through), not as a database error.
    class NotMigrated:
        def _rpc(self, fn, args):
            raise RuntimeError("room store error (404)")
    with pytest.raises(P.ProfilesUnavailable):
        P.RpcProfiles(NotMigrated()).top(5)
    with pytest.raises(P.ProfilesUnavailable):
        P.RpcProfiles(NotMigrated()).create("abcdefgh", {"rating": 1500})


def test_a_rematch_waits_until_the_last_rated_game_is_saved():
    a = _profile("Ada")
    code, doc, secs = _public_table([_card(*a)])
    doc, v = _play_out(code, doc, secs)
    with pytest.raises(ValueError):
        T.rematch(doc, secs[0], now=T0)          # not settled yet
    doc, v = T.maybe_settle(code, doc, v)
    T.rematch(doc, secs[0], now=T0)              # now it may deal again
    assert doc["phase"] == "playing" and P.get(a[0])["games"] == 1
