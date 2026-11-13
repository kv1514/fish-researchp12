"""Accounts: sign up, sign in on several devices, log out, delete, and guests.

Supabase Auth is replaced by a small fake that speaks the same routes
(/settings, /signup, /token, /user, /otp, /verify), so every path the app
takes is exercised here without a network or a real project.
"""

from __future__ import annotations

import json
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api import _auth as A                                      # noqa: E402
from api import _profiles as P                                  # noqa: E402
from api import _rooms                                          # noqa: E402


class FakeGoTrue:
    """Just enough of Supabase Auth for the app's sign-in paths."""

    def __init__(self):
        self.settings = {"external": {"email": True, "google": False,
                                      "phone": True},
                         "disable_signup": False, "mailer_autoconfirm": True}
        self.users = {}           # email/phone -> user
        self.passwords = {}
        self.tokens = {}          # access token -> user
        self.codes = {}           # phone -> code
        self.calls = []

    def session(self, user):
        tok = "tok-" + uuid.uuid4().hex
        self.tokens[tok] = user
        return {"access_token": tok, "refresh_token": "r", "user": user}

    def handle(self, method, path, query, body, bearer):
        self.calls.append((method, path))
        if path == "/settings":
            return 200, self.settings
        if path == "/signup":
            email = body["email"]
            if email in self.users:
                return 422, {"msg": "User already registered"}
            user = {"id": str(uuid.uuid4()), "email": email,
                    "user_metadata": {}}
            self.users[email], self.passwords[email] = user, body["password"]
            if self.settings["mailer_autoconfirm"]:
                return 200, self.session(user)
            return 200, dict(user, confirmation_sent_at="now")
        if path == "/token" and query.get("grant_type") == ["password"]:
            email = body["email"]
            if self.passwords.get(email) != body["password"]:
                return 400, {"error": "invalid_grant",
                             "error_description": "Invalid login credentials"}
            return 200, self.session(self.users[email])
        if path == "/user":
            user = self.tokens.get(bearer)
            return (200, user) if user else (401, {"msg": "invalid JWT"})
        if path == "/otp":
            self.codes[body["phone"]] = "123456"
            return 200, {}
        if path == "/verify":
            phone = body["phone"]
            if self.codes.get(phone) != body["token"]:
                return 403, {"msg": "Token has expired or is invalid"}
            user = self.users.setdefault(phone, {"id": str(uuid.uuid4()),
                                                 "phone": phone,
                                                 "user_metadata": {}})
            return 200, self.session(user)
        return 404, {"msg": "not found"}


@pytest.fixture
def gotrue(monkeypatch):
    fake = FakeGoTrue()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _go(self, method):
            u = urlparse(self.path)
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}") if n else {}
            auth = self.headers.get("Authorization", "")
            bearer = auth[7:] if auth.startswith("Bearer ") else None
            code, out = fake.handle(method, u.path, parse_qs(u.query), body,
                                    bearer)
            raw = json.dumps(out).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            self._go("GET")

        def do_POST(self):
            self._go("POST")

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    A.configure_for_tests(f"http://127.0.0.1:{srv.server_address[1]}")
    yield fake
    A.configure_for_tests(None)
    srv.shutdown()


@pytest.fixture(autouse=True)
def _stores(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    _rooms.reset_store_for_tests(_rooms.MemoryStore())
    P.reset_for_tests(P.MemoryProfiles())
    yield
    _rooms.reset_store_for_tests(None)
    P.reset_for_tests(None)


@pytest.fixture
def server():
    from api.index import handler
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _post(base, op, body=None):
    req = Request(f"{base}/api/{op}", data=json.dumps(body or {}).encode(),
                  headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req) as r:
            return r.status, json.loads(r.read())
    except HTTPError as e:
        return e.code, json.loads(e.read())


def test_the_app_is_told_which_ways_to_sign_in_are_on(server, gotrue):
    st, out = _post(server, "a_config")
    assert st == 200
    assert out["accounts"]["email"] and out["accounts"]["phone"]
    assert not out["accounts"]["google"]


def test_sign_up_makes_a_named_account_and_signs_this_device_in(server, gotrue):
    st, out = _post(server, "a_signup", {"name": "Ada", "email": "Ada@Gmail.com",
                                         "password": "correct horse"})
    assert st == 200, out
    assert out["profile"]["name"] == "Ada" and out["profile"]["rating"] == 1500
    assert out["profile"]["login"] == "a•••@gmail.com"
    st, me = _post(server, "p_me", {"id": out["id"], "secret": out["secret"]})
    assert st == 200 and me["profile"]["login"] == "a•••@gmail.com"
    # nothing about how they sign in is public
    st, pub = _post(server, "p_get", {"id": out["id"]})
    assert "login" not in pub["profile"] and "devices" not in json.dumps(pub)


def test_sign_up_needs_a_name_before_any_account_is_made(server, gotrue):
    st, out = _post(server, "a_signup", {"name": " ", "email": "a@b.co",
                                         "password": "correct horse"})
    assert st == 400 and "name" in out["error"]
    assert ("POST", "/signup") not in gotrue.calls


def test_wrong_passwords_and_taken_emails_say_so(server, gotrue):
    body = {"name": "Ada", "email": "ada@x.io", "password": "correct horse"}
    _post(server, "a_signup", body)
    st, out = _post(server, "a_signup", body)
    assert st == 400 and out["error"] == "User already registered"
    st, out = _post(server, "a_login", {"email": "ada@x.io", "password": "nope-nope"})
    assert st == 400 and out["error"] == "Invalid login credentials"
    st, out = _post(server, "a_signup", dict(body, email="not-an-email"))
    assert st == 400


def test_one_account_many_devices_and_logging_out_forgets_only_that_one(
        server, gotrue):
    _, a = _post(server, "a_signup", {"name": "Ada", "email": "ada@x.io",
                                      "password": "correct horse"})
    st, b = _post(server, "a_login", {"email": "ada@x.io",
                                      "password": "correct horse"})
    assert st == 200 and b["id"] == a["id"] and b["secret"] != a["secret"]
    assert b["profile"]["name"] == "Ada"          # a later sign-in keeps it
    _post(server, "p_logout", {"id": a["id"], "secret": a["secret"]})
    st, _ = _post(server, "p_me", {"id": a["id"], "secret": a["secret"]})
    assert st == 400
    st, _ = _post(server, "p_me", {"id": b["id"], "secret": b["secret"]})
    assert st == 200


def test_email_confirmation_on_means_check_your_email_then_log_in(
        server, gotrue):
    gotrue.settings["mailer_autoconfirm"] = False
    st, out = _post(server, "a_signup", {"name": "Ada", "email": "ada@x.io",
                                         "password": "correct horse"})
    assert st == 200 and out == {"confirm": True}
    # (they click the link; the fake lets them straight in)
    st, out = _post(server, "a_login", {"email": "ada@x.io",
                                        "password": "correct horse",
                                        "name": "Ada"})
    assert st == 200 and out["profile"]["name"] == "Ada"


def test_a_phone_code_signs_in(server, gotrue):
    st, _ = _post(server, "a_phone_start", {"phone": "+1 (555) 123-4567"})
    assert st == 200 and "+15551234567" in gotrue.codes
    st, out = _post(server, "a_phone_verify", {"phone": "+15551234567",
                                               "code": "000000", "name": "Bo"})
    assert st == 400
    st, out = _post(server, "a_phone_verify", {"phone": "+15551234567",
                                               "code": "123456", "name": "Bo"})
    assert st == 200 and out["profile"]["name"] == "Bo"
    assert out["profile"]["login"] == "•••4567"


def test_a_google_return_signs_in_with_the_name_google_gave(server, gotrue):
    user = {"id": str(uuid.uuid4()), "email": "cy@gmail.com",
            "user_metadata": {"full_name": "Cy Young"}}
    tok = gotrue.session(user)["access_token"]
    st, out = _post(server, "a_token", {"access_token": tok})
    assert st == 200 and out["profile"]["name"] == "Cy Young"
    st, _ = _post(server, "a_token", {"access_token": "forged"})
    assert st == 400


def test_sign_in_links_only_go_where_the_app_lives(server, gotrue):
    gotrue.settings["external"]["google"] = True
    A.configure_for_tests(A._BASE)              # drop the cached settings
    st, out = _post(server, "a_oauth", {"provider": "google",
                                        "redirect_to": "fish://auth"})
    assert st == 200 and "provider=google" in out["url"]
    st, _ = _post(server, "a_oauth", {"provider": "google",
                                      "redirect_to": "https://evil.example/"})
    assert st == 400


def test_deleting_an_account_removes_the_sign_in_too(server, gotrue):
    _, a = _post(server, "a_signup", {"name": "Ada", "email": "ada@x.io",
                                      "password": "correct horse"})
    uid = gotrue.users["ada@x.io"]["id"]
    st, _ = _post(server, "p_delete", {"id": a["id"], "secret": a["secret"]})
    assert st == 200
    assert P.profiles().deleted_accounts == [uid]
    st, _ = _post(server, "p_get", {"id": a["id"]})
    assert st == 404


def test_a_closed_account_cannot_sign_back_in(server, gotrue):
    _, a = _post(server, "a_signup", {"name": "Ada", "email": "ada@x.io",
                                      "password": "correct horse"})
    P.ban(a["id"])
    st, out = _post(server, "a_login", {"email": "ada@x.io",
                                        "password": "correct horse"})
    assert st == 400 and "fair-play" in out["error"]


def test_accounts_carry_to_quick_play_and_guests_play_unrated(server, gotrue):
    _, a = _post(server, "a_signup", {"name": "Ada", "email": "ada@x.io",
                                      "password": "correct horse"})
    st, t = _post(server, "t_quick", {"name": "ignored", "pid": a["id"],
                                      "psecret": a["secret"]})
    assert st == 200
    me = t["table"]["seats"][t["table"]["me"]]
    assert me["pid"] == a["id"] and me["name"] == "Ada" and me["rating"] == 1500
    st, g = _post(server, "t_quick", {"name": "Guesty"})
    assert st == 200
    gs = g["table"]["seats"][g["table"]["me"]]
    assert gs["pid"] is None and gs["rating"] is None and gs["name"] == "Guesty"


def test_without_supabase_configured_accounts_say_they_are_off(server):
    A.configure_for_tests(None)
    st, out = _post(server, "a_config")
    assert st == 503 and "switched on" in out["error"]


def test_there_is_no_route_that_makes_an_anonymous_profile(server):
    st, _ = _post(server, "p_new", {"name": "x"})
    assert st == 404
