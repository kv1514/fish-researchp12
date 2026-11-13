"""Player profiles: an identity that outlives a table, a rating, and a record.

IDENTITY WITHOUT AN ACCOUNT
---------------------------
A profile is made the first time the app opens: a public id (shown to other
players, used in links) and a secret (kept on the device, never shown to
anyone). There is no email and no password, so there is nothing to leak and
nothing to recover -- lose the device and the profile is gone, which is the
honest trade for collecting nothing. The database stores a SHA-256 of the
secret, not the secret.

Apple requires an app that creates an account to let the person delete it
(App Review Guideline 5.1.1(v)); ``delete`` does, completely.

RATING
------
Elo, for teams: a team's rating is the mean of its three seats, a bot seat
counts as ``BOT_RATING``, and every rated person on a team moves by
``K * (score - expected)`` where expected comes from the two team means. So
beating a stronger table pays more than beating a weaker one, and a team that
was expected to win gains little for doing it.

Only PUBLIC tables are rated. A private table is friends who chose each other,
and a rating that friends can trade between themselves measures nothing.

The bot anchors the scale: a bot is 1500 by definition and new players start
there, so "1600" means "beats a table of bots about 64% of the time" and keeps
meaning it as the population changes.

Leaving does not dodge a loss. The rated seats are written down when the cards
are dealt, and a seat that left counts as a loss whatever its team then did.
A seat the engine played for more than a third of the time (timeouts, away)
can lose rating but not gain it, so going idle and letting the engine win is
not a way up.

Every rated game has a key, and a profile records the keys it has applied, so
two phones polling the same finished table at the same moment cannot apply a
result twice.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import secrets
import threading
import time

from api import _fairplay as F
from api._rooms import Conflict, NotFound, RpcStore, clean_name, store

START_RATING = 1500.0
BOT_RATING = 1500.0
K_NEW = 40.0           # for a player's first PROVISIONAL games
K_SETTLED = 24.0
PROVISIONAL = 10
LISTED_AFTER = 5       # games before a profile appears on the leaderboard
RECENT_KEEP = 30
APPLIED_KEEP = 80
REPORTERS_KEEP = 200
AUTOPILOT_LIMIT = 1 / 3
ID_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
ID_LEN = 10


class ProfilesUnavailable(Exception):
    """No profile store here; the message is safe to show."""


def _sha(secret: str) -> str:
    return hashlib.sha256(str(secret).encode()).hexdigest()


def _new_id() -> str:
    return "".join(secrets.choice(ID_ALPHABET) for _ in range(ID_LEN))


def k_factor(games: int) -> float:
    return K_NEW if int(games) < PROVISIONAL else K_SETTLED


def expected(r_a: float, r_b: float) -> float:
    """Chance team A beats team B, from their mean ratings."""
    return 1.0 / (1.0 + 10 ** ((float(r_b) - float(r_a)) / 400.0))


# ---------------------------------------------------------------------------
# The columns a store indexes, derived from the document
# ---------------------------------------------------------------------------

#: Which summary number each flag rule is judged on.
ZKEY = {"asks": "ask_z_margin", "declarations": "claim_z_margin",
        "focus": "focus_lost_z_margin"}


def _active_flags(doc: dict) -> list:
    """Flags not already reviewed and cleared at their current strength."""
    cleared = doc.get("cleared") or {}
    out = []
    s = F.summary(doc.get("fair"))
    for f in F.flags(doc.get("fair")):
        rule = f["rule"]
        if rule in cleared:
            # Re-raised only by materially stronger evidence than a person
            # already looked at and let go.
            now_z = s.get(ZKEY[rule], 0) or 0
            if now_z < float(cleared[rule]) + 1.0:
                continue
        out.append(f)
    return out


def columns(doc: dict) -> dict:
    ok = doc.get("status", "ok") == "ok"
    flagged = bool(_active_flags(doc))
    reports = sum((doc.get("reports") or {}).values())
    return {
        "rating": float(doc.get("rating", START_RATING)),
        "games": int(doc.get("games", 0)),
        "listed": ok and not flagged and int(doc.get("games", 0)) >= LISTED_AFTER,
        "review": ok and (flagged or reports >= 3),
        "touched": float(doc.get("seen") or 0),
    }


# ---------------------------------------------------------------------------
# Stores
# ---------------------------------------------------------------------------

class MemoryProfiles:
    def __init__(self) -> None:
        self._d: dict[str, tuple[int, dict]] = {}
        self._lock = threading.Lock()

    def create(self, pid: str, doc: dict) -> bool:
        with self._lock:
            if pid in self._d:
                return False
            self._d[pid] = (1, json.loads(json.dumps(doc)))
            return True

    def read(self, pid: str) -> tuple[int, dict]:
        with self._lock:
            if pid not in self._d:
                raise NotFound(pid)
            v, d = self._d[pid]
            return v, json.loads(json.dumps(d))

    def write(self, pid: str, version: int, doc: dict) -> int:
        with self._lock:
            if pid not in self._d:
                raise NotFound(pid)
            v, _ = self._d[pid]
            if v != version:
                raise Conflict(pid)
            self._d[pid] = (v + 1, json.loads(json.dumps(doc)))
            return v + 1

    def delete(self, pid: str) -> bool:
        with self._lock:
            return self._d.pop(pid, None) is not None

    def _where(self, col: str) -> list:
        with self._lock:
            return [json.loads(json.dumps(d)) for _, d in self._d.values()
                    if columns(d)[col]]

    def top(self, limit: int = 50) -> list:
        rows = sorted(self._where("listed"), key=lambda d: -d["rating"])
        return rows[:limit]

    def review(self, limit: int = 50) -> list:
        rows = sorted(self._where("review"), key=lambda d: -(d.get("seen") or 0))
        return rows[:limit]

    def rank(self, rating: float) -> int:
        return 1 + sum(1 for d in self._where("listed") if d["rating"] > rating)


class RpcProfiles:
    """Profiles in Postgres through key-gated functions; scripts4/profile_rpc.sql."""

    def __init__(self, rpc: RpcStore) -> None:
        self._raw = rpc._rpc

    def _rpc(self, fn: str, args: dict):
        """The room store's RPC call, with "not migrated yet" made readable.

        Until scripts4/profile_rpc.sql has been applied, every fish_profile_*
        function is a 404 from PostgREST. That must read as "ratings are not
        on yet" -- the app then plays unrated -- rather than as a database
        error on the leaderboard.
        """
        try:
            return self._raw(fn, args)
        except RuntimeError as e:
            if "(404)" in str(e):
                raise ProfilesUnavailable(
                    "Ratings aren't switched on for this server yet.") from None
            raise

    def _cols(self, doc: dict) -> dict:
        c = columns(doc)
        return {"p_rating": c["rating"], "p_games": c["games"],
                "p_listed": c["listed"], "p_review": c["review"],
                "p_touched": c["touched"]}

    def create(self, pid: str, doc: dict) -> bool:
        return bool(self._rpc("fish_profile_create",
                              dict(self._cols(doc), p_id=pid, p_doc=doc)))

    def read(self, pid: str) -> tuple[int, dict]:
        rows = self._rpc("fish_profile_read", {"p_id": pid}) or []
        if not rows:
            raise NotFound(pid)
        return int(rows[0]["version"]), rows[0]["doc"]

    def write(self, pid: str, version: int, doc: dict) -> int:
        if not self._rpc("fish_profile_write",
                         dict(self._cols(doc), p_id=pid,
                              p_version=int(version), p_doc=doc)):
            raise Conflict(pid)
        return version + 1

    def delete(self, pid: str) -> bool:
        return bool(self._rpc("fish_profile_delete", {"p_id": pid}))

    def top(self, limit: int = 50) -> list:
        return [r["doc"] for r in
                self._rpc("fish_profile_top", {"p_limit": int(limit)}) or []]

    def review(self, limit: int = 50) -> list:
        return [r["doc"] for r in
                self._rpc("fish_profile_review", {"p_limit": int(limit)}) or []]

    def rank(self, rating: float) -> int:
        return int(self._rpc("fish_profile_rank",
                             {"p_rating": float(rating)}) or 0) + 1


_PROFILES = None
_LOCK = threading.Lock()


def profiles():
    """The profile store that matches the room store, or None if there is none.

    Profiles ride on the key-gated RPC store in production and on memory in
    tests and the local dev server. A deployment on the service-key store has
    no profile functions, and gets None rather than a half-working rating.
    """
    global _PROFILES
    with _LOCK:
        if _PROFILES is None:
            st = store()
            if isinstance(st, RpcStore):
                _PROFILES = RpcProfiles(st)
            elif type(st).__name__ == "MemoryStore":
                _PROFILES = MemoryProfiles()
            else:
                _PROFILES = False
        return _PROFILES or None


def reset_for_tests(p=None) -> None:
    global _PROFILES
    with _LOCK:
        _PROFILES = p


def _need():
    p = profiles()
    if p is None:
        raise ProfilesUnavailable("Profiles are not switched on for this server.")
    return p


def _update(pid: str, fn, retries: int = 6):
    """Read, apply ``fn(doc)`` (returns changed?), compare-and-set."""
    p = _need()
    for _ in range(retries):
        v, doc = p.read(pid)
        if not fn(doc):
            return doc
        try:
            p.write(pid, v, doc)
            return doc
        except Conflict:
            continue
    raise RuntimeError("that profile is busy; try again")


# ---------------------------------------------------------------------------
# Profile lifecycle
# ---------------------------------------------------------------------------

def create(name: str, now: float = None) -> tuple[str, str, dict]:
    now = time.time() if now is None else now
    p = _need()
    secret = secrets.token_urlsafe(24)
    doc = {"v": 1, "name": clean_name(name, "") or "Player",
           "secret_sha": _sha(secret), "created": now, "seen": now,
           "rating": START_RATING, "peak": START_RATING, "games": 0,
           "wins": 0, "losses": 0, "draws": 0, "recent": [], "applied": [],
           "fair": F.empty(), "status": "ok", "reports": {},
           "reporters": [], "cleared": {}}
    for _ in range(20):
        pid = _new_id()
        doc["id"] = pid
        if p.create(pid, doc):
            return pid, secret, doc
    raise RuntimeError("could not allocate a profile id")


def auth(pid, secret) -> dict:
    """The profile, if ``secret`` is its secret. Raises ValueError otherwise."""
    if not pid or not secret:
        raise ValueError("no profile")
    try:
        _, doc = _need().read(str(pid))
    except NotFound:
        raise ValueError("profile not recognised") from None
    if not secrets.compare_digest(doc.get("secret_sha", ""), _sha(secret)):
        raise ValueError("profile not recognised")
    if doc.get("status") == "banned":
        raise ValueError("this profile was closed for a fair-play violation")
    return doc


def public(doc: dict, rank: bool = False) -> dict:
    """What anyone may see. No secret hash, no fair-play numbers, no reporters."""
    games = int(doc.get("games", 0))
    out = {
        "id": doc["id"], "name": doc.get("name", "Player"),
        "rating": round(float(doc.get("rating", START_RATING))),
        "peak": round(float(doc.get("peak", START_RATING))),
        "provisional": games < PROVISIONAL,
        "games": games, "wins": int(doc.get("wins", 0)),
        "losses": int(doc.get("losses", 0)), "draws": int(doc.get("draws", 0)),
        "win_rate": round(doc.get("wins", 0) / games, 3) if games else None,
        "created": doc.get("created"),
        "closed": doc.get("status") == "banned",
        "recent": [{k: r.get(k) for k in ("t", "won", "delta", "rating",
                                          "score", "abandoned")}
                   for r in (doc.get("recent") or [])[:15]],
    }
    if rank and columns(doc)["listed"]:
        try:
            out["rank"] = _need().rank(float(doc["rating"]))
        except Exception:
            out["rank"] = None
    return out


def get(pid: str) -> dict:
    try:
        _, doc = _need().read(str(pid))
    except NotFound:
        raise NotFound(pid) from None
    return public(doc, rank=True)


def rename(pid, secret, name, now: float = None) -> dict:
    now = time.time() if now is None else now
    auth(pid, secret)
    new = clean_name(name, "")
    if not new:
        raise ValueError("pick a name")

    def fn(d):
        d["name"], d["seen"] = new, now
        return True
    return public(_update(pid, fn))


def delete(pid, secret) -> None:
    auth(pid, secret)
    _need().delete(str(pid))


def report(pid, secret, target, reason, now: float = None) -> None:
    """One report per person per target per reason, kept for review."""
    now = time.time() if now is None else now
    if reason not in ("cheating", "name"):
        raise ValueError("unknown reason")
    if str(target) == str(pid):
        raise ValueError("you can't report yourself")
    auth(pid, secret)
    tag = f"{reason}:{_sha(pid)[:16]}"

    def fn(d):
        rs = d.setdefault("reporters", [])
        if tag in rs:
            return False
        rs.append(tag)
        del rs[:-REPORTERS_KEEP]
        rep = d.setdefault("reports", {})
        rep[reason] = int(rep.get(reason, 0)) + 1
        return True
    try:
        _update(str(target), fn)
    except NotFound:
        raise ValueError("no such player") from None


def leaderboard(limit: int = 50) -> list:
    rows = _need().top(limit)
    return [dict(public(d), rank=i + 1) for i, d in enumerate(rows)]


# ---------------------------------------------------------------------------
# Settling a rated game
# ---------------------------------------------------------------------------

def plan(doc: dict) -> dict:
    """Every rated seat's result and rating change, from the table alone.

    Pure: reads the table document and nothing else, so it can be tested
    without a store and gives the same answer however many times it is asked.
    Uses the ratings written down at the deal, as chess servers use the rating
    at the start of a game.
    """
    rated = doc.get("rated") or {}
    seats = rated.get("seats") or {}
    res = doc.get("result") or {}
    if not seats or res.get("winner", "x") == "x":
        return {}
    winner = res.get("winner")

    def seat_rating(i: int) -> float:
        r = seats.get(str(i))
        return float(r["rating"]) if r else BOT_RATING

    team_mean = [sum(seat_rating(i) for i in range(6) if i % 2 == t) / 3
                 for t in (0, 1)]
    moves = {}
    for seat, by in doc.get("by") or []:
        own, tot = moves.get(int(seat), (0, 0))
        moves[int(seat)] = (own + (by == "h"), tot + 1)
    left = {int(x) for x in doc.get("left") or []}
    out = {}
    for key, r in seats.items():
        i = int(key)
        team = i % 2
        e = expected(team_mean[team], team_mean[1 - team])
        s = 0.5 if winner is None else 1.0 if winner == team else 0.0
        own, tot = moves.get(i, (0, 0))
        autopilot = tot > 0 and (tot - own) / tot > AUTOPILOT_LIMIT
        abandoned = i in left
        if abandoned:
            s = 0.0
        delta = k_factor(r.get("games", 0)) * (s - e)
        if autopilot and not abandoned and delta > 0:
            delta = 0.0
        out[i] = {"pid": r["pid"], "score": s, "expected": round(e, 3),
                  "delta": round(delta, 1), "abandoned": abandoned,
                  "autopilot": autopilot,
                  "won": None if winner is None else int(winner == team)}
    return out


def settle(doc: dict, now: float = None) -> dict:
    """Apply a finished rated game to its players. Idempotent per game.

    Returns ``{seat: {"delta", "rating"}}`` for the results screen. A profile
    that cannot be reached is skipped and retried by the next poll -- the
    table is not marked settled until every profile took it.
    """
    now = time.time() if now is None else now
    rated = doc.get("rated") or {}
    key = rated.get("key")
    pl = plan(doc)
    if not key or not pl:
        return {}
    fair_rows = {}
    for row in doc.get("fair") or []:
        fair_rows.setdefault(int(row["s"]), []).append(row)
    score = (doc.get("result") or {}).get("score") or [0, 0]
    out = {}
    for seat, r in pl.items():
        team = seat % 2
        others = [v["pid"] for s2, v in pl.items() if s2 % 2 != team]
        game_tally = F.tally(fair_rows.get(seat, []))

        def fn(d, r=r, seat=seat, team=team, others=others,
               game_tally=game_tally):
            if key in (d.get("applied") or []):
                return False
            d["rating"] = round(float(d.get("rating", START_RATING))
                                + r["delta"], 1)
            d["peak"] = max(float(d.get("peak", START_RATING)), d["rating"])
            d["games"] = int(d.get("games", 0)) + 1
            if r["won"] is None:
                d["draws"] = int(d.get("draws", 0)) + 1
            elif r["won"] and not r["abandoned"]:
                d["wins"] = int(d.get("wins", 0)) + 1
            else:
                d["losses"] = int(d.get("losses", 0)) + 1
            d.setdefault("recent", []).insert(0, {
                "key": key, "t": now, "won": r["won"] if not r["abandoned"] else 0,
                "delta": r["delta"], "rating": d["rating"],
                "score": [score[team], score[1 - team]],
                "abandoned": r["abandoned"], "opp": others,
                "opp_delta": {v["pid"]: v["delta"] for s2, v in pl.items()
                              if s2 % 2 != team}})
            del d["recent"][RECENT_KEEP:]
            d.setdefault("applied", []).append(key)
            del d["applied"][:-APPLIED_KEEP]
            d["fair"] = F.merge(d.get("fair"), game_tally)
            d["seen"] = now
            return True
        try:
            d = _update(r["pid"], fn)
            out[seat] = {"delta": r["delta"], "rating": round(d["rating"])}
        except NotFound:
            out[seat] = {"delta": 0.0, "rating": None}     # profile deleted
    return out


# ---------------------------------------------------------------------------
# Review: for whoever holds FISH_ADMIN_KEY
# ---------------------------------------------------------------------------

def admin_ok(key) -> bool:
    want = os.environ.get("FISH_ADMIN_KEY", "").strip()
    return bool(want) and len(want) >= 32 and bool(key) and \
        secrets.compare_digest(_sha(want), _sha(str(key)))


def review_queue(limit: int = 50) -> list:
    out = []
    for d in _need().review(limit):
        out.append({"profile": public(d), "reports": d.get("reports") or {},
                    "fair_play": F.summary(d.get("fair")),
                    "flags": _active_flags(d),
                    "cleared": d.get("cleared") or {}})
    return out


def clear(pid: str) -> None:
    """Reviewed, and let go: the flag stays down unless the evidence grows."""
    def fn(d):
        s = F.summary(d.get("fair"))
        d["cleared"] = {f["rule"]: s[ZKEY[f["rule"]]]
                        for f in F.flags(d.get("fair"))}
        d["reports"] = {}
        return True
    _update(pid, fn)


def ban(pid: str, now: float = None) -> dict:
    """Close a profile for a fair-play violation and refund its opponents.

    As on Chess.com: the rating each opponent lost to this player in their
    recent rated games is given back. Idempotent per game per opponent.
    """
    now = time.time() if now is None else now
    _, doc = _need().read(pid)
    refunded = 0
    for g in doc.get("recent") or []:
        for opp, delta in (g.get("opp_delta") or {}).items():
            if delta >= 0 or opp == pid:
                continue
            tag = f"refund:{g['key']}"

            def fn(d, delta=delta, tag=tag):
                if tag in (d.get("applied") or []):
                    return False
                d["rating"] = round(float(d["rating"]) - float(delta), 1)
                d["peak"] = max(float(d.get("peak", START_RATING)), d["rating"])
                d.setdefault("applied", []).append(tag)
                del d["applied"][:-APPLIED_KEEP]
                d.setdefault("refunds", []).insert(0, {
                    "t": now, "points": -float(delta)})
                return True
            try:
                _update(opp, fn)
                refunded += 1
            except NotFound:
                pass

    def close(d):
        d["status"] = "banned"
        d["closed_at"] = now
        return True
    _update(pid, close)
    return {"refunded": refunded}


def seat_card(doc: dict) -> dict:
    """What a table seat carries about its profile: enough to show and rate."""
    return {"pid": doc["id"], "rating": round(float(doc.get("rating",
                                                            START_RATING)), 1),
            "games": int(doc.get("games", 0))}
