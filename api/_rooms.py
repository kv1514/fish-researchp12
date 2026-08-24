"""Rooms for the serverless build: shared state, and where it is allowed to live.

WHY THIS IS NOT THE LOBBY IN fish4/web/lobby.py
-----------------------------------------------
That one is correct and unusable here. It holds rooms in a dict guarded by a
lock, and drives bot moves from a daemon thread. Both assume a process that
outlives a request. Vercel gives every request a fresh handler on a possibly
fresh instance, so an in-process dict is a room exactly one player can see and
a daemon thread is a thread that stops existing between moves.

Solo play needs none of this: the position is a signed token plus the public
log, both held by the one client, so the server can be stateless. A room breaks
that, and for one reason -- when Ada acts, Bo has to find out. Two clients
cannot learn about each other through a server that remembers nothing.

WHAT MUST NOT BE STORED WHERE THE CLIENT CAN REACH IT
-----------------------------------------------------
The obvious cheap design is to let browsers talk to the database directly with
a public key and skip the server. It cannot work here, and the reason is the
whole game: a room's row holds the deal nonce, and the nonce derives the deal.
A client that can read the row can derive all six hands. The same applies to
storing the hands themselves.

So the store is reached only from the server, with a secret the browser never
sees, and each player is handed the per-seat view that
``Session.snapshot`` already builds. The information boundary is the same one
the solo build enforces; only the transport moved.

CONCURRENCY
-----------
Two players can act in the same instant. Each write therefore carries the
version it read, and the store rejects a write whose version has moved --
compare-and-set, so a lost update is an error the caller can retry rather than
a move that silently vanished. The alternative, last-write-wins, would drop a
move that a player watched be accepted.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
from typing import Optional

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # no I/O/0/1
CODE_LEN = 4

#: Rooms are ephemeral. A table nobody has touched for this long is gone, which
#: keeps an abandoned room from holding a code forever and bounds the store.
ROOM_TTL = 6 * 3600.0

#: Cap on how many rooms one store will hold. A public site with an open create
#: endpoint needs a ceiling that is not "whatever the database will take".
MAX_ROOMS = 500

#: Longest a name may be. Applied SERVER-SIDE, independently of the client's
#: own copy in public/names.js -- that one is for display, and a check that
#: runs in the browser is not a boundary.
MAX_NAME = 18

#: Characters that render as nothing or reorder what follows. A seat label is
#: how a player identifies who asked them for a card, so a name that can be
#: made to look like another name is a gameplay problem. Kept as explicit
#: ranges rather than a regex literal so the source is reviewable.
_INVISIBLE = (
    tuple(range(0x00, 0x20)) + (0x7F,)
    + tuple(range(0x200B, 0x2010))      # ZWSP..RLM
    + tuple(range(0x202A, 0x202F))      # bidi embedding/override
    + tuple(range(0x2060, 0x2065))      # word joiner, invisible operators
    + (0xFEFF,)
)
_STRIP = {c: None for c in _INVISIBLE}


def clean_name(raw, fallback: str = "") -> str:
    """Sanitise a display name. Mirrors ``FishNames.clean`` in the client.

    Deliberately duplicated rather than shared. The client's copy keeps the
    display tidy; this one is the boundary, and it has to hold for a request
    that never went near the client.
    """
    if raw is None:
        return fallback
    s = str(raw).translate(_STRIP)
    s = " ".join(s.split())
    return s[:MAX_NAME] or fallback


def new_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LEN))


class Conflict(Exception):
    """A write lost a race. The caller re-reads and retries."""


class NotFound(Exception):
    """No such room, or it expired."""


# ---------------------------------------------------------------------------
# Stores
# ---------------------------------------------------------------------------

class MemoryStore:
    """Rooms in this process.

    Correct for the local dev server and for tests, and correct for exactly one
    serverless instance -- which is why it is not the default in production. It
    is here so the room logic can be tested without a database, and so a local
    run exercises the same code path the deployed one does.
    """

    def __init__(self) -> None:
        self._rooms: dict[str, tuple[int, dict]] = {}
        self._lock = threading.Lock()

    def create(self, doc: dict) -> str:
        with self._lock:
            self._sweep()
            if len(self._rooms) >= MAX_ROOMS:
                raise RuntimeError("too many rooms open; try again later")
            for _ in range(40):
                code = new_code()
                if code not in self._rooms:
                    self._rooms[code] = (1, doc)
                    return code
            raise RuntimeError("could not allocate a room code")

    def read(self, code: str) -> tuple[int, dict]:
        with self._lock:
            self._sweep()
            got = self._rooms.get(code)
            if got is None:
                raise NotFound(code)
            return got[0], json.loads(json.dumps(got[1]))

    def write(self, code: str, version: int, doc: dict) -> int:
        with self._lock:
            got = self._rooms.get(code)
            if got is None:
                raise NotFound(code)
            if got[0] != version:
                raise Conflict(code)
            self._rooms[code] = (version + 1, doc)
            return version + 1

    def _sweep(self) -> None:
        now = time.time()
        for code in [c for c, (_, d) in self._rooms.items()
                     if now - float(d.get("touched", 0)) > ROOM_TTL]:
            self._rooms.pop(code, None)


class PostgrestStore:
    """Rooms in Postgres, reached over Supabase's REST interface.

    No new dependency: ``urllib`` is in the standard library and the whole
    surface is four requests. Adding a client library would mean a bigger cold
    start on a function whose cold start is already dominated by importing the
    engine.

    Schema (see scripts4/room_schema.sql)::

        create table fish_rooms (
          code       text primary key,
          version    integer not null default 1,
          touched    double precision not null,
          doc        jsonb not null
        );

    Row-level security stays ON with no policies, which denies every anonymous
    request. This store authenticates with the service key, which bypasses RLS
    and lives only in the function's environment. That combination is the point:
    the table is unreachable from a browser even though the project's anon key
    is public by design.
    """

    def __init__(self, url: str, key: str) -> None:
        self.base = url.rstrip("/") + "/rest/v1/fish_rooms"
        self.key = key

    def _req(self, method: str, path: str = "", body=None, prefer=None):
        import urllib.error
        import urllib.request
        headers = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if prefer:
            headers["Prefer"] = prefer
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data,
                                     headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=8) as r:
                raw = r.read()
                return json.loads(raw) if raw else []
        except urllib.error.HTTPError as e:
            # Never surface the database's message: it can name columns and
            # constraints, and on a conflict it would describe the row.
            raise RuntimeError(f"room store error ({e.code})") from None
        except Exception:
            raise RuntimeError("room store unreachable") from None

    def create(self, doc: dict) -> str:
        for _ in range(40):
            code = new_code()
            try:
                self._req("POST", "", [{"code": code, "version": 1,
                                        "touched": doc.get("touched", 0),
                                        "doc": doc}],
                          prefer="return=minimal")
                return code
            except RuntimeError:
                continue          # almost certainly a code collision; try again
        raise RuntimeError("could not allocate a room code")

    def read(self, code: str) -> tuple[int, dict]:
        rows = self._req("GET", f"?code=eq.{code}&select=version,touched,doc")
        if not rows:
            raise NotFound(code)
        row = rows[0]
        if time.time() - float(row.get("touched") or 0) > ROOM_TTL:
            raise NotFound(code)
        return int(row["version"]), row["doc"]

    def write(self, code: str, version: int, doc: dict) -> int:
        # The version predicate is what makes this compare-and-set: PATCH with
        # `version=eq.<read>` updates nothing if another writer already moved
        # it, and `return=representation` is how we find out which happened.
        rows = self._req(
            "PATCH", f"?code=eq.{code}&version=eq.{version}",
            {"version": version + 1, "touched": doc.get("touched", 0),
             "doc": doc},
            prefer="return=representation")
        if not rows:
            raise Conflict(code)
        return version + 1


_STORE = None
_STORE_LOCK = threading.Lock()


def store():
    """The configured store, or the in-process one.

    Chosen from the environment rather than from a flag, so a deployment that
    forgot to configure Postgres gets the memory store and a room that works
    for one player -- which is visibly broken -- rather than a crash on the
    first join. ``room_backend`` in the health response says which is live, so
    the difference is reportable instead of mysterious.
    """
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            url = os.environ.get("SUPABASE_URL", "").strip()
            key = (os.environ.get("SUPABASE_SERVICE_KEY")
                   or os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
            _STORE = PostgrestStore(url, key) if url and key else MemoryStore()
        return _STORE


def backend_name() -> str:
    return "postgres" if isinstance(store(), PostgrestStore) else "memory"


def serverless() -> bool:
    """Are we running where each request may get a different process?"""
    return bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))


def require_shared_store() -> None:
    """Refuse rooms when the store cannot actually be shared.

    The memory store is correct for the local dev server, which is one
    process, and correct for exactly one serverless instance -- which is the
    problem. Deployed without SUPABASE_URL and SUPABASE_SERVICE_KEY, a room
    created and joined in quick succession OFTEN WORKS, because both requests
    happen to land on the same warm instance. Then a third request lands
    somewhere else and the table has never existed.

    That was measured, not predicted: a create-then-join against the deployed
    build with no store configured returned a perfectly good seat. An
    intermittent room is worse than no room, because it looks like a game bug
    rather than a missing environment variable -- so this refuses up front,
    and says which two variables are missing.
    """
    if serverless() and not isinstance(store(), PostgrestStore):
        raise RuntimeError(
            "Rooms need a shared store, and this deployment has none. Set "
            "SUPABASE_URL and SUPABASE_SERVICE_KEY (see "
            "scripts4/room_schema.sql), or play the bots -- solo games need "
            "no setup and are unaffected.")


def reset_store_for_tests(s=None) -> None:
    global _STORE
    with _STORE_LOCK:
        _STORE = s
