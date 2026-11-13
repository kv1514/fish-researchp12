"""Their repository moved. Does the agent we published a margin against still play the same?

WHAT HAPPENED UPSTREAM. `external_v07/UPSTREAM.txt` pinned
github.com/dylann4500/fishbot at d017fbcb. Five commits later the project
released the same agent under a new name -- SESTINA v1.0, `docs/RELEASE-v1.0.md`
-- and in the same window added an external-bot protocol (`extbot.hpp`,
`botpkg.hpp`, `docs/BOT_PACKAGE.md`), a port of OUR v0.1 search policy into
their engine (`kv.hpp`), a bridge to our v0.6 package (`kv6.hpp`), and 124 new
lines in `factory.hpp` -- the very function our shim calls to construct their
agent.

WHY THAT IS A THREAT TO A PUBLISHED NUMBER. This paper reports a head-to-head
against "their v0.7". If their released binary now plays even slightly
differently from the one we measured, that sentence is about a policy nobody
can run any more. The release notes say "the name changed at release; nothing
measured did" -- but a claim in someone else's release notes is a claim, and
the whole point of bridging their engine rather than reimplementing it was to
stop taking their word for their bot's behaviour.

WHAT THIS SETTLES, AND HOW. Not by rerunning the head-to-head -- that would
answer a noisy question at enormous cost, and a null result there would be
consistent with a real behavioural change too small for 10,000 games to see.
Instead it compares the two builds DECISION BY DECISION on identical inputs.

  1. Play games in our engine against the bridge, capturing the exact stdin
     script -- spec, rules, seat, hand, seed, the whole replayed event stream,
     the DECIDE line -- that the bridge sends for every single decision.
  2. Replay every captured script through a binary built from the OLD pinned
     headers and through one built from the CURRENT release, and diff stdout.

Their shim is a pure function of that script (`shim_decide.cpp` boots, replays,
answers one decision and exits), so identical scripts must produce identical
answers unless their code changed what the policy does. This is a stronger test
than any number of games: it is exact, it needs no statistics, and one
differing decision refutes it.

WHAT A PASS DOES AND DOES NOT LICENCE. A pass says the released SESTINA v1.0
answers every decision our published run actually asked exactly as the pinned
v0.7 did, so the margin we report describes the released agent and the pin can
move. It does NOT say the two builds are equivalent everywhere: this exercises
the decision distribution our games reach, which is the one our claim is about,
and nothing else. Positions our bot never puts them in are untested here.

USAGE

    python3 scripts4/v07_upstream_parity.py --games 40 \\
        --old /tmp/fish_v07_decide_pinned \\
        --new external_v07/fish_v07_decide

Build the two binaries with `external_v07/build.sh <path-to-their-engine/src>`
against a worktree of each commit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.engine import GameState                      # noqa: E402
from fish.observation import Observation               # noqa: E402
from fish.rules import RuleConfig                      # noqa: E402

#: The rule dialect every head-to-head in this paper is played under.
RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 3_100_000
AGENT0 = 31_000

#: Cap per game, matching the head-to-head harness.
MAX_ACTIONS = 600


def _capture(games: int, seed0: int, progress: bool) -> list[list[str]]:
    """Play games against the bridge, returning every stdin script it sent.

    Both seatings are played for each deal, because the seat a policy sits in
    changes which decisions it is asked for, and a parity check that only ever
    saw one seating would be testing half the decision space.
    """
    from fish4.registry4 import KRAKEN_V1, make_agent
    from fish4.dylan_v07 import DylanV07

    scripts: list[list[str]] = []
    original = DylanV07._run

    def recording(self, lines):
        scripts.append(list(lines))
        return original(self, lines)

    DylanV07._run = recording
    try:
        rules = RuleConfig(**RULES_D)
        for i in range(games):
            for kv_even in (True, False):
                deal_seed = seed0 + i
                agents = []
                for p in range(6):
                    kv = (p % 2 == 0) == kv_even
                    agents.append(make_agent(KRAKEN_V1) if kv
                                  else make_agent(("dylan_v07", {})))
                st = GameState.deal(rules, seed=deal_seed)
                for p, a in enumerate(agents):
                    a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
                for _ in range(MAX_ACTIONS):
                    if st.is_terminal:
                        break
                    st.apply(st.turn, agents[st.turn].act(
                        Observation.from_state(st, st.turn)))
                fb = sum(getattr(a, "fallbacks", 0) for a in agents)
                if fb:
                    # A fallback means our engine rejected their move, so the
                    # captured script is from a game the bridge was not
                    # faithfully driving. Refuse rather than average it in.
                    raise SystemExit(
                        f"bridge fell back {fb} times on deal {deal_seed}; "
                        "fix the bridge before trusting a parity result")
            if progress and (i + 1) % 5 == 0:
                print(f"  captured {len(scripts):,} decisions "
                      f"over {i + 1}/{games} deals", flush=True)
    finally:
        DylanV07._run = original
    return scripts


def _answer(binary: str, lines: list[str], timeout: float = 120.0) -> str:
    r = subprocess.run([binary], input="\n".join(lines) + "\n",
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        return f"<rc={r.returncode}> {r.stderr.strip()[:200]}"
    return r.stdout.strip()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--games", type=int, default=40,
                    help="deals to capture from (each played both seatings)")
    ap.add_argument("--seed", type=int, default=SEED0)
    ap.add_argument("--old", required=True, help="binary from the OLD pin")
    ap.add_argument("--new", required=True, help="binary from the NEW release")
    ap.add_argument("--out", default=str(ROOT / "results"
                                         / "v07_upstream_parity.json"))
    a = ap.parse_args(argv)

    for p in (a.old, a.new):
        if not Path(p).exists():
            print(f"missing binary: {p}", file=sys.stderr)
            return 2

    t0 = time.time()
    print(f"capturing decisions over {a.games} deals x 2 seatings ...",
          flush=True)
    scripts = _capture(a.games, a.seed, progress=True)
    print(f"{len(scripts):,} decisions captured in "
          f"{(time.time() - t0) / 60:.1f} min", flush=True)

    if not scripts:
        print("no decisions captured", file=sys.stderr)
        return 1

    mismatches = []
    decls_old = asks_old = 0
    for i, lines in enumerate(scripts):
        old = _answer(a.old, lines)
        new = _answer(a.new, lines)
        if old.startswith("DECL"):
            decls_old += 1
        elif old.startswith("ASK"):
            asks_old += 1
        if old != new:
            mismatches.append({
                "index": i,
                "old": old,
                "new": new,
                # The script itself can run to hundreds of lines; a digest
                # identifies it, and --games with the same seed reproduces it.
                "script_sha256_16": hashlib.sha256(
                    "\n".join(lines).encode()).hexdigest()[:16],
                "decide_line": lines[-1],
            })
        if (i + 1) % 500 == 0:
            print(f"  replayed {i + 1:,}/{len(scripts):,}, "
                  f"{len(mismatches)} mismatch(es)", flush=True)

    out = {
        "question": "does SESTINA v1.0 answer our decisions as pinned v0.7 did",
        "rules": RULES_D,
        "deals": a.games,
        "seed0": a.seed,
        "decisions_compared": len(scripts),
        "asks": asks_old,
        "declarations": decls_old,
        "mismatches": len(mismatches),
        "mismatch_rate": len(mismatches) / len(scripts),
        "verdict": "IDENTICAL" if not mismatches else "DIVERGENT",
        "old_binary": a.old,
        "new_binary": a.new,
        "examples": mismatches[:20],
        "seconds": round(time.time() - t0, 1),
    }
    Path(a.out).write_text(json.dumps(out, indent=1) + "\n")

    print(f"\n=== decision parity: pinned v0.7 vs released SESTINA v1.0 ===")
    print(f"  decisions compared   {len(scripts):,} "
          f"({asks_old:,} asks, {decls_old:,} declarations)")
    print(f"  mismatches           {len(mismatches)}")
    print(f"  VERDICT              {out['verdict']}")
    if mismatches:
        print("\n  first differing decisions:")
        for m in mismatches[:5]:
            print(f"    #{m['index']}  old={m['old']!r}  new={m['new']!r}")
    print(f"\nwrote {a.out}")
    return 0 if not mismatches else 1


if __name__ == "__main__":
    raise SystemExit(main())
