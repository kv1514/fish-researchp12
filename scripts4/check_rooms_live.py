"""Does a deployment actually serve rooms? Play one and find out.

``GET /api/health`` reports ``room_backend``, and that is worth checking but it
is not the same question. It says which store the process CHOSE at import time;
it does not say the credentials work, that the table exists, that RLS lets the
service key through, or that two different browsers reach the same room. Every
one of those can be wrong while health says ``postgres``.

So this drives the real thing: create a table as one player, join it as a
second, rename a bot, ready both, and confirm the deal lands with each seat
seeing nine cards and only its own. Two independent HTTP clients, no shared
state beyond the room code -- which is exactly the shape a real pair of players
has.

It is also the only end-to-end check that can catch the failure this whole
design is about. With no shared store, a create and a join a second apart
usually land on the same warm serverless instance and LOOK fine; the test that
notices is one that also does something afterwards.

    py scripts4/check_rooms_live.py                      # the deployed site
    py scripts4/check_rooms_live.py http://127.0.0.1:8420

Exit status is 0 only if a room dealt and both seats got a private hand.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

DEFAULT = ("https://fish-engine-git-claude-fishnbot-work-access-g7ciey"
           "-side-space.vercel.app")

TIMEOUT = 45


def call(base: str, op: str, body: dict):
    """POST one API op. Returns (json, http_status)."""
    req = urllib.request.Request(
        f"{base}/api/{op}",
        data=json.dumps(body).encode(),
        headers={"content-type": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return json.loads(r.read() or b"{}"), r.status
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read() or b"{}"), e.code
        except Exception:
            return {"error": f"HTTP {e.code}"}, e.code


def get(base: str, path: str):
    with urllib.request.urlopen(f"{base}{path}", timeout=TIMEOUT) as r:
        return json.loads(r.read() or b"{}")


def main(argv) -> int:
    base = (argv[0] if argv else DEFAULT).rstrip("/")
    print(f"checking {base}\n")

    ok = True

    def check(cond, msg):
        nonlocal ok
        print(("  ok   " if cond else "  FAIL ") + msg)
        if not cond:
            ok = False
        return cond

    # ---- what the process thinks -------------------------------------------
    health = get(base, "/api/health")
    backend = health.get("room_backend")
    print(f"health: {json.dumps(health)}")
    if backend != "postgres":
        print(
            f"\nroom_backend is {backend!r}, so this deployment has no shared\n"
            f"store and rooms are refused by design. Set SUPABASE_URL and\n"
            f"SUPABASE_SERVICE_KEY (see scripts4/room_schema.sql), redeploy,\n"
            f"and run this again.\n\n"
            f"Locally that is fine and expected: one process, one memory\n"
            f"store, rooms work. Deployed it is the thing to fix.")
        # Not a failure when running against a local dev server.
        if "127.0.0.1" in base or "localhost" in base:
            print("\n(local run: continuing anyway)")
        else:
            return 1

    # ---- one player creates ------------------------------------------------
    print("\ncreating a table as Ada")
    a, code_status = call(base, "room_new",
                          {"humans": 2, "name": "Ada", "pace": 0})
    if not check("code" in a, f"created ({a.get('error') or code_status})"):
        return 1
    code = a["code"]
    print(f"  room {code}, seat {a['seat']}")

    # ---- a second, independent client joins --------------------------------
    b, _ = call(base, "room_join", {"code": code, "name": "Bo"})
    if not check("secret" in b,
                 f"a second client joined ({b.get('error')})"):
        return 1
    check(b["seat"] != a["seat"], "the joiner got a different seat")

    # ---- renaming, and who is allowed to --------------------------------
    seats = b.get("room", {}).get("seats", [])
    bot = next((s["seat"] for s in seats if s["kind"] == "bot"), None)
    if bot is not None:
        r, _ = call(base, "room_rename",
                    {"code": code, "secret": b["secret"], "seat": bot,
                     "name": "Sharky"})
        check("Sharky" in (r.get("room", {}).get("names") or []),
              "any player may rename a bot")
    r, st = call(base, "room_rename",
                 {"code": code, "secret": b["secret"], "seat": a["seat"],
                  "name": "Hacked"})
    check(st >= 400, "one player may NOT rename another")

    # ---- the ready gate ----------------------------------------------------
    r1, _ = call(base, "room_ready",
                 {"code": code, "secret": a["secret"], "ready": True})
    phase1 = r1.get("phase") or r1.get("room", {}).get("phase")
    check(phase1 == "seating", "one player ready does NOT deal")

    r2, _ = call(base, "room_ready",
                 {"code": code, "secret": b["secret"], "ready": True})
    phase2 = r2.get("phase") or r2.get("room", {}).get("phase")
    check(phase2 == "playing" or "hand" in r2, "both ready deals")

    # ---- the boundary ------------------------------------------------------
    va, _ = call(base, "room_state", {"code": code, "secret": a["secret"]})
    vb, _ = call(base, "room_state", {"code": code, "secret": b["secret"]})
    ha = {c["id"] for c in va.get("hand", [])}
    hb = {c["id"] for c in vb.get("hand", [])}
    check(len(ha) == 9 and len(hb) == 9,
          f"each seat holds nine cards ({len(ha)}, {len(hb)})")
    check(ha.isdisjoint(hb), "the two hands share no card")
    blob = json.dumps(va) + json.dumps(vb)
    check("nonce" not in blob, "the deal nonce is not in any view")
    check("secret" not in blob, "no seat secret is in any view")

    # ---- and a stranger gets nothing --------------------------------------
    s, st = call(base, "room_state", {"code": code, "secret": "not-a-secret"})
    check(st >= 400, "a wrong secret is refused")
    s, st = call(base, "room_join", {"code": code, "name": "Late"})
    check(st >= 400, "nobody joins a game in progress")

    print()
    if ok:
        print(f"Rooms work on {base}.\nTwo independent clients sat at table "
              f"{code}, it dealt only when both were ready,\nand neither can "
              f"see the other's cards.")
    else:
        print("Something above failed. Rooms are not working here.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
