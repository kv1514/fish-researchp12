"""The action cap changes nothing about how the engine plays. Checked, not argued.

WHY THIS IS NOT A DUEL. `WEB_MAX_ACTIONS` is an ARBITER rule: it decides when
the game is over, and no agent can see it. So the claim is not "the capped arm
scores about the same", which would need thousands of games and a confidence
interval and would still leave a small real effect indistinguishable from zero.
The claim is stronger and cheaper: on every game that finishes below the cap the
two arms play the IDENTICAL sequence of actions. That is an exact statement
about a log, so a single counterexample refutes it and no interval is involved.

WHAT THE ARMS ARE. Same deals, same seats, same protocol; one with the cap at
its shipped value and one with it lifted to `MAX_LOG`, which is the hard
ceiling the client's log length imposes anyway. A game that reaches MAX_LOG in
the lifted arm is a livelock -- the defect this cap exists for -- and is
reported rather than compared, because there is no "same ending" to compare to.

    py scripts4/web_cap_check.py [n_per_mode] [restore_every] [n_jobs]

Exits non-zero if any game diverged, so it can be run as a check rather than
read as a report.
"""
from __future__ import annotations

import json
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

#: THE SAME KEY THE TERMINATION STUDY USED, so this runs on the same deals.
#: `seed_from_nonce` is HMAC(FISH_SECRET, nonce) and the fallback key is random
#: per process, so without this the two arms below would not even share a deal
#: with each other, let alone with results/web_termination_*.
SEED_SECRET = "web-termination-study-2026-09-12"
os.environ["FISH_SECRET"] = SEED_SECRET

from api import _engine                                      # noqa: E402
from api._engine import CHAMPION_GAMMA, MAX_LOG, Session      # noqa: E402
from fish.engine import RuleConfig                            # noqa: E402
from scripts4.resultfile import default_path, write           # noqa: E402

NONCE = "term-{mode}-{i:06d}"

SHIPPED_CAP = _engine.WEB_MAX_ACTIONS
SHIPPED_IDLE = _engine.WEB_MAX_IDLE


def _rules() -> RuleConfig:
    return RuleConfig(variant="54", starting_player=0,
                      wrong_distribution_outcome="opponent")


def _play(mode: str, nonce: str, cap: int, idle: int, restore_every: int):
    """Run one game with both arbiter rules set as given. Returns the log."""
    _engine.WEB_MAX_ACTIONS = cap
    _engine.WEB_MAX_IDLE = idle
    s = (Session(-1, nonce, _rules(), CHAMPION_GAMMA, mode="spectate")
         if mode == "spectate"
         else Session(0, nonce, _rules(), CHAMPION_GAMMA))
    since = 0
    while not s.over and len(s.wire_log) < MAX_LOG:
        if mode == "play" and s.state.turn == s.seat:
            s.play(s.suggest(), max_moves=0)
        else:
            s.advance(1)
        since += 1
        if restore_every and since >= restore_every:
            s = Session.restore(s.token(), list(s.wire_log))
            since = 0
    return (json.dumps(s.wire_log, sort_keys=True),
            bool(s.state.is_terminal), bool(s.stopped), len(s.wire_log))


def _one(job):
    mode, i, restore_every = job
    nonce = NONCE.format(mode=mode, i=i)
    capped = _play(mode, nonce, SHIPPED_CAP, SHIPPED_IDLE, restore_every)
    # Both rules lifted to the hard ceiling the client's log length imposes
    # anyway, which is the closest thing to "no arbiter rule at all" that the
    # session can actually be run under.
    lifted = _play(mode, nonce, MAX_LOG, MAX_LOG, restore_every)
    return {"mode": mode, "i": i,
            "capped_actions": capped[3], "lifted_actions": lifted[3],
            "capped_terminal": capped[1], "lifted_terminal": lifted[1],
            "stopped": capped[2],
            # The lifted arm ran to MAX_LOG without the cards resolving: that
            # is the livelock, and the arms have no shared ending to compare.
            "livelock": not lifted[1] and lifted[3] >= MAX_LOG,
            "same_log": capped[0] == lifted[0]}


def main(argv):
    n = int(argv[1]) if len(argv) > 1 else 200
    restore_every = int(argv[2]) if len(argv) > 2 else 1
    jobs_n = int(argv[3]) if len(argv) > 3 else 4
    jobs = [(m, i, restore_every)
            for m in ("play", "spectate") for i in range(n)]
    t0 = time.time()
    with Pool(jobs_n) as pool:
        rows = []
        for k, r in enumerate(pool.imap_unordered(_one, jobs, chunksize=2), 1):
            rows.append(r)
            if k % 50 == 0:
                print(f"  {k}/{len(jobs)}  {time.time() - t0:.0f}s", flush=True)

    finished = [r for r in rows if not r["livelock"]]
    diverged = [r for r in finished if not r["same_log"]]
    livelocks = [r for r in rows if r["livelock"]]

    print(f"\n  games                  {len(rows)}")
    print(f"  finished under both    {len(finished)}")
    print(f"  IDENTICAL action logs  {len(finished) - len(diverged)}")
    print(f"  diverged               {len(diverged)}")
    print(f"  livelocked without it  {len(livelocks)}")
    for r in diverged[:5]:
        print(f"    DIVERGED {r['mode']} {r['i']}: "
              f"{r['capped_actions']} vs {r['lifted_actions']} actions")

    payload = {
        "script": "scripts4/web_cap_check.py",
        "descriptive": True,
        "fish_secret": SEED_SECRET,
        "cap": SHIPPED_CAP,
        "idle_cap": SHIPPED_IDLE,
        "seeding": "ply" if _engine.SEED_ADVANCES_WITH_PLY else "frozen",
        "lifted_to": MAX_LOG,
        "stride": restore_every,
        "restore_every": restore_every,
        "n_games": len(rows),
        "n_per_mode": n,
        "n_finished_both": len(finished),
        "n_identical": len(finished) - len(diverged),
        "n_diverged": len(diverged),
        "n_livelocked_without_cap": len(livelocks),
        "livelocks": [{"mode": r["mode"], "i": r["i"],
                       "capped_actions": r["capped_actions"]}
                      for r in livelocks],
        "diverged": diverged[:20],
        "secs": round(time.time() - t0, 1),
    }
    path = write(default_path(f"web_cap_check_r{restore_every}", n), payload)
    print(f"\nwrote {path}")
    return 1 if diverged else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
