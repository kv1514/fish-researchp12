"""What a spectator sees, classified: game win rates, futile asks, ask-backs.

Two viewer-reported patterns from the exhibition are checked against replayed
games, attributed per engine:

* "Why would it ask for a card a bot just had?" -- an opponent asking the
  player who just publicly RECEIVED a card for that same card is a certain
  steal (the transfer was face up), i.e. strong play that looks odd. Counted
  as ``askback`` with its success rate, per side.
* A PROVABLY FUTILE ask -- asking a player for a card the public record
  already proves they cannot hold (they were in a failed ask involving that
  card and have not received it since). Under the no-bluff rule a failed ask
  proves the card is with neither party. Futile asks surrender the turn for
  certain; counted per side. (Deliberate signalling is off in the deployed
  spec, so for this engine any futile ask would be the doomed-ask branch:
  no ask anywhere can land.)

    py scripts4/watch_forensics.py [n_games]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import team_of
from fish.engine import AskEvent, ClaimEvent, GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.registry4 import make_agent

BASE = {"opponent_gamma": 0.35, "n_draws": 480, "w_lookahead": 0.25,
        "lookahead_depth": 3, "lookahead_beam": 4,
        "endgame_m": 2, "endgame_d_info": 2.0}
RULES = RuleConfig(wrong_distribution_outcome="opponent")


def play(deal_seed: int):
    agents = []
    for p in range(6):
        agents.append(make_agent(("dylan_v07", {})) if p % 2 == 0
                      else make_agent(("fishbot4", dict(BASE))))
    st = GameState.deal(RULES, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, RULES, 991_000 + deal_seed * 13 + p)
    for _ in range(600):
        if st.is_terminal:
            break
        st.apply(st.turn,
                 agents[st.turn].act(Observation.from_state(st, st.turn)))
    return st


def main(n_games: int = 20) -> int:
    tallies = {
        "dylan": {"futile": 0, "askback": 0, "askback_hit": 0, "asks": 0},
        "kv": {"futile": 0, "askback": 0, "askback_hit": 0, "asks": 0},
    }
    wins = {"dylan": 0, "kv": 0, "tie": 0}
    margins = []
    for i in range(n_games):
        st = play(600_000 + i)
        d = sum(1 for w in st.set_winner if w == 0)
        k = sum(1 for w in st.set_winner if w == 1)
        margins.append(k - d)
        wins["kv" if k > d else "dylan" if d > k else "tie"] += 1
        # Public tracking: proven_absent[(player, card)] active until the card
        # publicly moves TO that player; last_taker[card] = who received it.
        absent = set()
        last_taker = {}
        for ev in st.history:
            if isinstance(ev, ClaimEvent):
                continue
            if not isinstance(ev, AskEvent):
                continue
            side = "dylan" if ev.asker % 2 == 0 else "kv"
            tallies[side]["asks"] += 1
            if (ev.target, ev.card) in absent:
                tallies[side]["futile"] += 1
            if last_taker.get(ev.card) == ev.target:
                tallies[side]["askback"] += 1
                if ev.success:
                    tallies[side]["askback_hit"] += 1
            # update public record
            absent.add((ev.asker, ev.card))       # no-bluff: asker lacks it
            if ev.success:
                absent.discard((ev.asker, ev.card))
                absent.add((ev.target, ev.card))
                last_taker[ev.card] = ev.asker
            else:
                absent.add((ev.target, ev.card))
    n = len(margins)
    print(f"{n} games, KV margin mean {sum(margins)/n:+.2f} sets/game")
    print(f"game wins: KV {wins['kv']}, Dylan {wins['dylan']}, "
          f"ties {wins['tie']}")
    for side in ("kv", "dylan"):
        t = tallies[side]
        hit = (100 * t["askback_hit"] / t["askback"]) if t["askback"] else 0
        print(f"  {side:5s}: {t['asks']} asks, {t['futile']} provably futile, "
              f"{t['askback']} ask-backs of a just-taken card "
              f"({hit:.0f}% of those hit)")
    out = {"n_games": n, "kv_margin_mean": sum(margins) / n, "wins": wins,
           "tallies": tallies}
    (ROOT / "results" / "watch_forensics.json").write_text(
        json.dumps(out, indent=1))
    print("wrote results/watch_forensics.json")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 20))
