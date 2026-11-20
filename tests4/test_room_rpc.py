"""The key-gated store: same semantics as the service-key store, smaller key.

``RpcStore`` reaches fish_rooms only through the four functions in
scripts4/room_rpc.sql. These tests stand up a fake PostgREST that implements
those functions the way the SQL does -- including refusing a wrong key -- and
drive real table play through it, so the request shapes and the
compare-and-set behaviour are pinned without a database.

The live database is checked separately, once, when the migration is applied.
"""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api import _rooms                                          # noqa: E402
from api import _tables as T                                    # noqa: E402

KEY = "k" * 48
PUBLIC = "sb_publishable_test"


class FakeRpc(BaseHTTPRequestHandler):
    rows: dict = {}
    seen: list = []
    lock = threading.Lock()

    def do_POST(self):
        fn = self.path.rsplit("/", 1)[-1]
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeRpc.seen.append((fn, {k.lower(): v for k, v in self.headers.items()}, body))
        if self.headers.get("apikey") != PUBLIC:
            return self._out(401, {"message": "no api key"})
        if body.get("p_key") != KEY:
            return self._out(403, {"message": "denied"})
        with FakeRpc.lock:
            rows = FakeRpc.rows
            if fn == "fish_store_create":
                if body["p_code"] in rows:
                    return self._out(200, False)
                rows[body["p_code"]] = [1, body["p_touched"], body["p_doc"]]
                return self._out(200, True)
            if fn == "fish_store_read":
                r = rows.get(body["p_code"])
                return self._out(200, [] if r is None else
                                 [{"version": r[0], "touched": r[1], "doc": r[2]}])
            if fn == "fish_store_write":
                r = rows.get(body["p_code"])
                if r is None or r[0] != body["p_version"]:
                    return self._out(200, False)
                rows[body["p_code"]] = [r[0] + 1, body["p_touched"], body["p_doc"]]
                return self._out(200, True)
            if fn == "fish_store_lobbies":
                out = [{"code": c, "version": v, "doc": d}
                       for c, (v, t, d) in rows.items()
                       if d.get("kind") == "table" and d.get("public")
                       and d.get("phase") == "lobby" and t > body["p_since"]]
                return self._out(200, out[: body["p_limit"]])
        return self._out(404, {"message": "no such function"})

    def _out(self, code, obj):
        raw = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a):
        pass


@pytest.fixture
def rpc_url():
    FakeRpc.rows, FakeRpc.seen = {}, []
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeRpc)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.fixture
def rpc_store(rpc_url):
    st = _rooms.RpcStore(rpc_url, PUBLIC, KEY)
    _rooms.reset_store_for_tests(st)
    yield st
    _rooms.reset_store_for_tests(None)


def test_a_whole_quick_play_table_runs_through_the_rpc_store(rpc_store):
    a = T.quick_play("Ada")
    b = T.quick_play("Bo")
    assert a[0] == b[0], "the second player should land at the first table"
    code, secret = a[0], a[2]
    T.mutate(code, lambda d: (T.start(d, secret), True))
    version, doc = rpc_store.read(code)
    assert doc["phase"] == "playing" and version >= 3
    s = T.session_for(doc, a[1])
    T.mutate(code, lambda d: (T.act(d, secret, s.suggest()), True))
    assert len(rpc_store.read(code)[1]["log"]) == 1


def test_compare_and_set_refuses_a_stale_version(rpc_store):
    code = rpc_store.create({"touched": 1e12, "kind": "table"})
    v, doc = rpc_store.read(code)
    rpc_store.write(code, v, doc)
    with pytest.raises(_rooms.Conflict):
        rpc_store.write(code, v, doc)          # v is stale now


def test_every_call_carries_the_key_and_only_the_public_key_as_apikey(rpc_store):
    rpc_store.create({"touched": 1e12})
    fn, headers, body = FakeRpc.seen[-1]
    assert body["p_key"] == KEY
    assert headers.get("apikey") == PUBLIC
    assert "authorization" not in headers, (
        "an sb_publishable_ key is not a JWT and must not be sent as a Bearer")


def test_a_wrong_key_is_an_error_that_does_not_echo_the_database(rpc_url):
    st = _rooms.RpcStore(rpc_url, PUBLIC, "wrong" * 10)
    with pytest.raises(RuntimeError) as e:
        st.read("ABCD")
    assert str(e.value) == "room store error (403)"


def test_the_environment_picks_the_rpc_store_and_rooms_are_allowed(monkeypatch):
    for k in ("SUPABASE_SERVICE_KEY", "SUPABASE_SERVICE_ROLE_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", PUBLIC)
    monkeypatch.setenv("FISH_DB_KEY", KEY)
    monkeypatch.setenv("VERCEL", "1")
    _rooms.reset_store_for_tests(None)
    try:
        assert isinstance(_rooms.store(), _rooms.RpcStore)
        assert _rooms.backend_name() == "postgres-rpc"
        _rooms.require_shared_store()          # must not raise
    finally:
        _rooms.reset_store_for_tests(None)


def test_half_configured_is_still_refused(monkeypatch):
    """A URL and a public key without FISH_DB_KEY must not look shared."""
    for k in ("SUPABASE_SERVICE_KEY", "SUPABASE_SERVICE_ROLE_KEY", "FISH_DB_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", PUBLIC)
    monkeypatch.setenv("VERCEL", "1")
    _rooms.reset_store_for_tests(None)
    try:
        with pytest.raises(_rooms.RoomsUnavailable):
            _rooms.require_shared_store()
    finally:
        _rooms.reset_store_for_tests(None)
