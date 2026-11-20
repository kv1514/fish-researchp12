"""Line protocol: their harness asks, KRAKEN answers.

One JSON object per line in, one per line out. Their Node harness owns the
game loop and their reducer arbitrates; this process only turns a SeatView into
a GameAction.

    in   {"game": "<id>", "seed": <int>, "view": <SeatView>}
    out  {"action": <GameAction>}                    or {"error": "..."}

AGENTS ARE STATEFUL AND THAT IS THE POINT. `FishBot4` keeps an incremental
belief and calls `bel.update(obs)` inside `act()`, so one instance per (game,
seat) is kept and reused. It is only called on its own turns, which is exactly
how it runs in our own engine; the Observation carries the whole public log
each time, so a belief that has missed intervening events catches up on the
next update. (That mechanism is why this project's inversion screen was wrong
for four figures until the update was made explicit -- here it is the normal
path and needs nothing special.)

A new `game` id drops every agent, so no state crosses a deal.
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from external_mp.bridge import (RULES, designate,                     # noqa: E402
                                endgame_claim, to_action, to_observation)

AGENTS: dict = {}
CUR_GAME: list = [None]


def agent_for(spec, game: str, seat: int, seed: int):
    from fish4.registry4 import make_agent
    if CUR_GAME[0] != game:
        AGENTS.clear()
        CUR_GAME[0] = game
    key = seat
    if key not in AGENTS:
        ag = make_agent(spec)
        ag.begin_game(seat, RULES, seed)
        AGENTS[key] = ag
    return AGENTS[key]


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--spec", default="KRAKEN_V1",
                    help="a registry name, or JSON overrides on top of it, "
                         "e.g. '{\"claim_stuck_threshold\": 0.3}'")
    a = ap.parse_args()

    from fish4 import registry4
    base = getattr(registry4, "KRAKEN_V1")
    if a.spec.startswith("{"):
        spec = ("fishbot4", dict(base[1], **json.loads(a.spec)))
    elif a.spec == "KRAKEN_V1":
        spec = base
    else:
        spec = getattr(registry4, a.spec)

    sys.stderr.write(f"kraken serve: spec={a.spec} rules={RULES}\n")
    sys.stderr.flush()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            view = req["view"]
            phase = view.get("phase")
            if phase == "awaitDesignate":
                # bridge logic, not our policy -- see bridge.designate
                out = {"action": designate(view)}
            else:
                ag = agent_for(spec, req["game"], view["seat"],
                               int(req.get("seed", 0)))
                obs = to_observation(view)
                if phase == "endgame":
                    # their endgame admits ONLY a claim; see
                    # bridge.endgame_claim for why this is a rule translation
                    # and not a policy of the bridge's own
                    act = endgame_claim(ag, obs)
                    if act is None:
                        raise RuntimeError(
                            "no claim available in their endgame phase")
                else:
                    act = ag.act(obs)
                out = {"action": to_action(act, view["seat"], view)}
        except Exception as e:                      # never die mid-tournament
            out = {"error": f"{type(e).__name__}: {e}",
                   "trace": traceback.format_exc()[-800:]}
        sys.stdout.write(json.dumps(out) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
