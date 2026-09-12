"""How long a game on the SHIPPED web path actually runs, and whether it ends.

WHY THIS EXISTS. `RESEARCH_FRONTIER.md` records an open defect: about one web
game in a hundred never terminates. The cycle is individually rational -- every
ask in it succeeds -- so no seat is misplaying; two live half-suits simply pass
back and forth and nobody ever holds all six. A visitor at the public URL can
be dealt one of those and watch forever.

THIS SCRIPT DOES NOT FIX IT. It measures the one number a fix needs: **where a
terminating game's action count actually stops.** An arbiter cap is only honest
if it cannot fire on a game that would have finished, and "cannot" has to be a
measurement rather than a guess. `tests4/test_web_session.py` carries an older
one -- 100 fixtures, median 105, max 191 -- taken as an aside while chasing a
red build. This takes it at power and at both modes.

DESCRIPTIVE. It registers nothing, fixes no threshold and ships nothing. The
cap it informs is a change to the ARBITER, not to any policy: no bot decides
differently because of it, which is what `--verify` in `scripts4/web_cap_check.py`
is for.

WHAT IT PLAYS. `api._engine.Session` exactly as the site builds it: 54-card,
opponent-award, champion gamma, WEB_DRAWS draws. Play mode seats the engine's
own suggestion at the human's chair, so all six seats are KRAKEN -- that is
what a solo visitor faces. Spectate is the 3v3 exhibition, Dylan's v0.7 on the
even seats.

WHY `restore_every` IS AN ARGUMENT AND NOT AN IMPLEMENTATION DETAIL. The site
is stateless: every request rebuilds the Session from the sealed token, which
rebuilds all six agents and re-seeds each one from the deal. A paced client
asks for ONE engine move per request, so on the deployed path every engine move
is decided by a freshly seeded agent. A local loop that keeps one Session alive
does not reproduce that, and `fish4.agent4` draws from `self.rng` twice -- for
the posterior sampler and for the tie-break among equal-scoring asks. So the
two protocols are different experiments, and only one of them is the site.

    py scripts4/web_termination.py [n_per_mode] [restore_every] [n_jobs] [seeding]

`restore_every` 0 keeps one Session for the whole game; 1 reproduces a paced
client; 6 reproduces the loop in tests4/test_web_session.py.
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

#: THE DEAL IS NOT A FUNCTION OF THE NONCE ALONE. `api._engine.seed_from_nonce`
#: is HMAC(FISH_SECRET, nonce), and with FISH_SECRET unset the key is
#: `_EPHEMERAL_SECRET`, freshly random PER PROCESS. So a "pinned" nonce pins
#: nothing across runs: the same fixture measured 115, 129, 202 and 103 actions
#: in four separate processes before this line existed, and two protocols
#: compared without it would have been compared on different deals.
#:
#: Set here rather than left to the caller because forgetting it does not fail,
#: it just quietly unpairs the experiment.
SEED_SECRET = "web-termination-study-2026-09-12"
os.environ["FISH_SECRET"] = SEED_SECRET

from api import _engine                                   # noqa: E402
from api._engine import CHAMPION_GAMMA, MAX_LOG, Session  # noqa: E402

#: THE ARBITER RULES ARE LIFTED FOR THIS STUDY, and that is the whole point of
#: it: this script measures what a web game does WITHOUT them, which is what
#: the rules are then set from. Leaving them in place does not merely bias the
#: answer, it hangs the loop -- `Session.advance` stops producing actions once
#: the session is `stopped`, so `while not terminal and len(log) < CEILING`
#: spins on a game that will never grow another action. That is exactly what it
#: did before this line existed.
_engine.WEB_MAX_ACTIONS = MAX_LOG
_engine.WEB_MAX_IDLE = MAX_LOG
from fish.engine import ClaimEvent, RuleConfig                       # noqa: E402
from scripts4.resultfile import default_path, write      # noqa: E402

#: MAX_LOG, because on the deployed path that IS the ceiling: `Session.restore`
#: refuses a longer log, so a game that gets there does not hang politely, it
#: dies with "action log too long" and takes the player's game with it. It is
#: also about 3.7x the longest game this script has ever seen terminate, so it
#: does not truncate the distribution it is measuring.
CEILING = MAX_LOG

#: Fresh per index and per mode, so the two modes are not scored on the same
#: deals -- they do not play the same game (spectate is 3v3 cross-engine) and
#: pairing them would suggest a comparison that is not being made.
NONCE = "term-{mode}-{i:06d}"


def _rules() -> RuleConfig:
    return RuleConfig(variant="54", starting_player=0,
                      wrong_distribution_outcome="opponent")


def _fresh(mode: str, nonce: str) -> Session:
    return (Session(-1, nonce, _rules(), CHAMPION_GAMMA, mode="spectate")
            if mode == "spectate"
            else Session(0, nonce, _rules(), CHAMPION_GAMMA))


def _one(job):
    mode, i, restore_every, seeding = job
    _engine.SEED_ADVANCES_WITH_PLY = (seeding == "ply")
    nonce = NONCE.format(mode=mode, i=i)
    s = _fresh(mode, nonce)
    t0 = time.time()
    since = 0
    while not s.state.is_terminal and len(s.wire_log) < CEILING:
        before = len(s.wire_log)
        if mode == "play" and s.state.turn == s.seat:
            # suggest() is this engine's own move, and it is legal in every
            # state including the forced declaration where there is no legal
            # ask and no legal pass. A solo visitor who plays the suggestion
            # is therefore playing the shipped policy at all six seats.
            s.play(s.suggest(), max_moves=0)
        else:
            s.advance(1)
        if len(s.wire_log) == before:
            # Belt and braces for the failure above: if a move ever stops
            # arriving for a reason this script did not anticipate, say so
            # instead of spinning.
            raise SystemExit(
                f"{mode} {i}: no action was produced at "
                f"{len(s.wire_log)} actions; an arbiter rule is still live "
                f"and this study cannot measure past it.")
        since += 1
        if restore_every and since >= restore_every:
            # What a request boundary actually is: token out, token in, six
            # agents rebuilt from the deal seed.
            s = Session.restore(s.token(), list(s.wire_log))
            since = 0
    resolved = sum(1 for w in s.state.set_winner if w is not None)
    return {"mode": mode, "i": i, "actions": len(s.wire_log),
            "terminal": bool(s.state.is_terminal), "resolved": resolved,
            "max_idle": _max_idle(s.state.history),
            "secs": round(time.time() - t0, 2)}


def _max_idle(history) -> int:
    """Longest run of actions with no half-suit resolving.

    THE POINT OF MEASURING THIS. A cap on total actions guarantees a game
    ends; it does not guarantee it ends soon. At the table's default pace of
    twelve seconds an engine move, six hundred actions is two hours, so a
    visitor dealt a livelock would still be abandoned -- correctly, eventually.
    A no-progress rule fires as soon as the cycle has run a while instead, and
    what it needs is the longest gap a REAL game leaves between resolutions.

    Every ClaimEvent resolves its half-suit, to the declaring team or (under
    the award rule) to the other one, so a ClaimEvent is exactly progress and
    an AskEvent never is.
    """
    gap = best = 0
    for ev in history:
        if isinstance(ev, ClaimEvent):
            gap = 0
        else:
            gap += 1
            best = max(best, gap)
    return best


def _quantile(xs, q):
    if not xs:
        return None
    ys = sorted(xs)
    k = (len(ys) - 1) * q
    lo, hi = int(k), min(int(k) + 1, len(ys) - 1)
    return ys[lo] + (ys[hi] - ys[lo]) * (k - lo)


def main(argv):
    n = int(argv[1]) if len(argv) > 1 else 1000
    restore_every = int(argv[2]) if len(argv) > 2 else 0
    jobs_n = int(argv[3]) if len(argv) > 3 else 4
    #: "ply" is what ships: the agents' random streams advance with the game.
    #: "frozen" is the defect it replaced -- every request re-seeded the six
    #: agents from the deal, so the engine's answer became a pure function of
    #: the position and a position that recurred produced the move that had
    #: produced it. Both arms are runnable so the before/after is reproducible.
    seeding = argv[4] if len(argv) > 4 else "ply"
    if seeding not in ("ply", "frozen"):
        raise SystemExit(f"seeding must be ply or frozen, not {seeding!r}")
    jobs = [(m, i, restore_every, seeding)
            for m in ("play", "spectate") for i in range(n)]
    t0 = time.time()
    with Pool(jobs_n) as pool:
        rows = []
        for k, r in enumerate(pool.imap_unordered(_one, jobs, chunksize=4), 1):
            rows.append(r)
            if k % 50 == 0:
                print(f"  {k}/{len(jobs)}  {time.time() - t0:.0f}s", flush=True)

    by_mode = {}
    for mode in ("play", "spectate"):
        mine = [r for r in rows if r["mode"] == mode]
        fin = [r["actions"] for r in mine if r["terminal"]]
        idle = [r["max_idle"] for r in mine if r["terminal"]]
        hung = [r for r in mine if not r["terminal"]]
        by_mode[mode] = {
            "n_games": len(mine),
            "n_terminated": len(fin),
            "n_hung": len(hung),
            "median_actions": _quantile(fin, 0.5),
            "p99_actions": _quantile(fin, 0.99),
            "max_actions": max(fin) if fin else None,
            "median_idle": _quantile(idle, 0.5),
            "p99_idle": _quantile(idle, 0.99),
            "max_idle": max(idle) if idle else None,
            # What a capped game would have cost the table: how many of the
            # nine half-suits the livelock had already resolved when it stuck.
            "hung_resolved": sorted(r["resolved"] for r in hung),
        }
        print(f"\n{mode}: {len(fin)}/{len(mine)} terminated, "
              f"median {by_mode[mode]['median_actions']}, "
              f"max {by_mode[mode]['max_actions']}, "
              f"max idle {by_mode[mode]['max_idle']}, "
              f"hung {len(hung)}")

    fin_all = [r["actions"] for r in rows if r["terminal"]]
    idle_all = [r["max_idle"] for r in rows if r["terminal"]]
    payload = {
        "script": "scripts4/web_termination.py",
        "descriptive": True,
        # Without this the nonces below name no particular deal. It is in the
        # payload so a reader can reproduce the exact 2,000 games.
        "fish_secret": SEED_SECRET,
        "ceiling": CEILING,
        # `stride` rather than a new key: scripts4/resultfile.py's IDENTITY
        # already guards it, so a run at one protocol cannot overwrite a run
        # at another even if somebody passes the same filename.
        "stride": restore_every,
        "restore_every": restore_every,
        "seeding": seeding,
        "n_games": len(rows),
        "n_per_mode": n,
        "max_terminating_actions": max(fin_all) if fin_all else None,
        "max_terminating_idle": max(idle_all) if idle_all else None,
        "n_hung": sum(1 for r in rows if not r["terminal"]),
        "by_mode": by_mode,
        "secs": round(time.time() - t0, 1),
    }
    path = write(
        default_path(f"web_termination_r{restore_every}_{seeding}", n), payload)
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
