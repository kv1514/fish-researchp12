"""Review flagged and reported players. For whoever holds FISH_ADMIN_KEY.

    FISH_ADMIN_KEY=... python scripts4/fairplay_review.py              # the queue
    FISH_ADMIN_KEY=... python scripts4/fairplay_review.py clear ID     # let go
    FISH_ADMIN_KEY=... python scripts4/fairplay_review.py ban ID       # close + refund

``--site`` defaults to the live deployment. The server only answers these
routes when its own FISH_ADMIN_KEY (32+ characters, set in Vercel) matches;
otherwise they are a plain 404.

How to read a record (see api/_fairplay.py for the reasoning):

* ask_hit_rate vs ask_expected_rate: how often their asks landed, against how
  often the cards they could see made that likely. Honest players run a few
  points above (the posterior is slightly cautious); a flag needs z >= 4 even
  after allowing 5 points.
* claim_right_rate vs claim_expected_rate: the same for declarations, with a
  25-point allowance.
* focus_lost_*: the ask test repeated on moves made after the app left the
  screen during that turn.
* think_ratio: seconds on hard decisions over seconds on easy ones. People sit
  well above 1; a relay that takes the same time every move sits near 1.
  Context, never a verdict.
* engine_match_rate: context only. The engine samples, so it agrees with
  itself on under half of open decisions; this cannot identify an engine user.

A flag is evidence for a person, not a verdict. Clear anyone the numbers do
not convince you about; a cleared flag comes back only if the evidence grows
by a further z of 1.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request


def call(site: str, op: str, body: dict) -> dict:
    req = urllib.request.Request(
        f"{site.rstrip('/')}/api/{op}",
        data=json.dumps(dict(body, admin=os.environ.get("FISH_ADMIN_KEY", ""))).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("action", nargs="?", default="queue",
                    choices=("queue", "clear", "ban"))
    ap.add_argument("id", nargs="?")
    ap.add_argument("--site", default="https://fish-engine.vercel.app")
    a = ap.parse_args()
    if not os.environ.get("FISH_ADMIN_KEY"):
        sys.exit("set FISH_ADMIN_KEY")
    if a.action == "queue":
        q = call(a.site, "p_review", {})["queue"]
        if not q:
            print("Nothing to review.")
        for item in q:
            p = item["profile"]
            print(f"\n{p['name']} ({p['id']}) rating {p['rating']}, "
                  f"{p['games']} games")
            for f in item["flags"]:
                print(f"  FLAG {f['rule']}: {f['why']}")
            if item["reports"]:
                print(f"  reports: {item['reports']}")
            print("  " + json.dumps(item["fair_play"]))
        return
    if not a.id:
        sys.exit("give the profile id")
    print(call(a.site, "p_clear" if a.action == "clear" else "p_ban", {"id": a.id}))


if __name__ == "__main__":
    main()
