"""Sign-in: accounts through the project's Supabase Auth, proxied by our server.

WHY SUPABASE AUTH, AND WHY THROUGH THE SERVER
---------------------------------------------
Passwords, Google sign-in, phone codes, rate limiting and reset emails are all
things to get from a system built for them, not to write here. The fish-rooms
Supabase project already has one (GoTrue), reachable with the PUBLISHABLE key
the server already holds -- the key that is public by design.

The app talks only to our server, and the server talks to Supabase Auth. That
keeps one origin for the app (the same CORS allowlist the tables use), and it
means a successful sign-in is turned into the thing the rest of the app already
uses -- a profile id and a per-device secret -- at exactly one place. The
Supabase session itself is not kept: we only need to know, once, that this
person proved who they are.

WHAT IS ON, AND HOW THE APP KNOWS
---------------------------------
Supabase reports which providers are switched on at /auth/v1/settings, a public
endpoint. ``config()`` reads it, so the app shows a Google button only when
Google is configured and a phone option only when an SMS provider is -- turning
one on in the Supabase dashboard is enough, with no new release.

Every message from Supabase Auth that reaches a player is one of its own
user-facing errors ("Invalid login credentials", "User already registered");
they describe the request, never the system, and are shortened before use.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request


class AuthUnavailable(Exception):
    """Sign-in is not configured on this server; the message is safe to show."""


class AuthError(ValueError):
    """Supabase Auth refused the request; the message is safe to show."""


_BASE = None            # tests point this at a fake
_KEY = None
_CFG = {"at": 0.0, "value": None}
_LOCK = threading.Lock()

EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,24}$")
PHONE_RE = re.compile(r"^\+[1-9][0-9]{6,14}$")


def configure_for_tests(base: str | None, key: str | None = "test-key") -> None:
    global _BASE, _KEY
    with _LOCK:
        _BASE, _KEY = base, key
        _CFG.update(at=0.0, value=None)


def _endpoint() -> tuple[str, str]:
    if _BASE:
        return _BASE.rstrip("/"), _KEY or ""
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = (os.environ.get("SUPABASE_PUBLISHABLE_KEY")
           or os.environ.get("SUPABASE_ANON_KEY") or "").strip()
    if not url or not key:
        raise AuthUnavailable("Accounts aren't switched on for this server yet.")
    return url.rstrip("/") + "/auth/v1", key


def _message(raw: bytes, code: int) -> str:
    try:
        d = json.loads(raw or b"{}")
    except ValueError:
        d = {}
    msg = (d.get("msg") or d.get("error_description") or d.get("message")
           or d.get("error") or f"sign-in failed ({code})")
    msg = re.sub(r"\s+", " ", str(msg)).strip()
    return msg[:160]


def _call(method: str, path: str, body=None, bearer: str | None = None) -> dict:
    base, key = _endpoint()
    headers = {"apikey": key, "Content-Type": "application/json",
               "Accept": "application/json"}
    if bearer:
        headers["Authorization"] = f"Bearer {bearer}"
    elif key.startswith("eyJ"):
        headers["Authorization"] = f"Bearer {key}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, headers=headers,
                                 method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        if e.code >= 500:
            raise RuntimeError("sign-in service unavailable; try again") from None
        raise AuthError(_message(e.read(), e.code)) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise RuntimeError("sign-in service unreachable; try again") from None


def config() -> dict:
    """Which ways to sign in are switched on. Cached for a minute."""
    with _LOCK:
        if _CFG["value"] is not None and time.time() - _CFG["at"] < 60:
            return dict(_CFG["value"])
    s = _call("GET", "/settings")
    ext = s.get("external") or {}
    value = {
        "email": bool(ext.get("email", True)),
        "google": bool(ext.get("google")),
        "apple": bool(ext.get("apple")),
        "phone": bool(ext.get("phone")),
        "signup": not bool(s.get("disable_signup")),
        # False means a new email account must click a link before signing
        # in -- which needs working email, so the app says so up front.
        "email_autoconfirm": bool(s.get("mailer_autoconfirm")),
    }
    with _LOCK:
        _CFG.update(at=time.time(), value=value)
    return dict(value)


def _clean_email(email) -> str:
    e = str(email or "").strip().lower()
    if not EMAIL_RE.match(e):
        raise AuthError("that doesn't look like an email address")
    return e


def _clean_phone(phone) -> str:
    p = re.sub(r"[\s()\-.]", "", str(phone or ""))
    if not PHONE_RE.match(p):
        raise AuthError("enter the number with its country code, like +1 555 123 4567")
    return p


def _user_of(resp: dict) -> dict | None:
    """The signed-in user from a session response, or None if none yet."""
    if resp.get("access_token") and isinstance(resp.get("user"), dict):
        return resp["user"]
    return None


def signup_email(email, password) -> dict | None:
    """Create an email account. Returns the user, or None if it must confirm."""
    e = _clean_email(email)
    if len(str(password or "")) < 8:
        raise AuthError("use a password of at least 8 characters")
    resp = _call("POST", "/signup", {"email": e, "password": str(password)})
    return _user_of(resp)


def login_email(email, password) -> dict:
    resp = _call("POST", "/token?grant_type=password",
                 {"email": _clean_email(email), "password": str(password or "")})
    user = _user_of(resp)
    if not user:
        raise AuthError("Invalid login credentials")
    return user


def phone_start(phone) -> None:
    _call("POST", "/otp", {"phone": _clean_phone(phone)})


def phone_verify(phone, code) -> dict:
    code = re.sub(r"\D", "", str(code or ""))
    if not 4 <= len(code) <= 10:
        raise AuthError("enter the code from the text message")
    resp = _call("POST", "/verify",
                 {"type": "sms", "phone": _clean_phone(phone), "token": code})
    user = _user_of(resp)
    if not user:
        raise AuthError("that code didn't work; ask for a new one")
    return user


def from_token(access_token) -> dict:
    """The user an access token belongs to (the Google / OAuth return path)."""
    tok = str(access_token or "").strip()
    if not tok or len(tok) > 4096:
        raise AuthError("sign-in expired; try again")
    user = _call("GET", "/user", bearer=tok)
    if not user.get("id"):
        raise AuthError("sign-in expired; try again")
    return user


def oauth_url(provider: str, redirect_to: str) -> str:
    """Where to send the player to sign in with ``provider``."""
    if provider not in ("google", "apple"):
        raise AuthError("unknown sign-in provider")
    if not config().get(provider):
        raise AuthError(f"{provider.title()} sign-in isn't switched on yet")
    base, _ = _endpoint()
    from urllib.parse import urlencode
    return f"{base}/authorize?" + urlencode(
        {"provider": provider, "redirect_to": redirect_to})


def login_label(user: dict) -> str:
    """How the account signs in, masked for display: k•••@gmail.com."""
    if user.get("email"):
        local, _, dom = user["email"].partition("@")
        return f"{local[:1]}•••@{dom}"
    if user.get("phone"):
        p = str(user["phone"])
        return f"•••{p[-4:]}"
    return "account"


def suggested_name(user: dict) -> str:
    meta = user.get("user_metadata") or {}
    return str(meta.get("full_name") or meta.get("name") or "").strip()
