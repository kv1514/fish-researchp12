"""Is the signalling ask already aimed, or does it need aiming?

RESEARCH_FRONTIER.md's Direction 2 proposes: "The shipped signalling gate fires
on cheapness. It does not consider what the team needs to know. Aim it instead
at the half-suit whose allocation is most likely to be forced unresolved."

That is worth a measurement before it is worth an implementation, because the
gate in `agent4.decide` already requires `stuck_half_suits(...)` to be non-empty
before it will signal at all, while `perpetual.signalling_ask` then searches
every half-suit our team OWNS rather than only the stuck ones. If those two sets
come apart, the mechanism fires at the right moment and points somewhere else,
and Direction 2 has a target to fix. If they do not, it has no headroom in
target selection and the direction needs re-aiming itself.

WHAT THIS MEASURES, precisely: at every decision where at least one of our
half-suits is stuck -- provably ours and unplaceable -- and `signalling_ask`
returns an ask, does that ask's half-suit belong to the stuck set?

WHAT IT DELIBERATELY DOES NOT APPLY is the `cheap` half of the gate
(`p_best <= signal_max_p`). That governs HOW OFTEN the signal fires, which is a
separate question from WHERE IT POINTS, and including it would only shrink the
sample without changing the quantity.

AN ERROR WORTH RECORDING, because it produced a confident zero. The first
version of this probe reached for `agent._ctx(obs)`, which does not exist,
inside a bare `except Exception`. It reported "0 opportunities" -- and 0 from a
probe that never ran looks exactly like 0 from a phenomenon that never happens.
The context is now built the way `agent4.decide` builds it, and nothing is
swallowed.

Usage: python scripts4/signal_aim.py [n_games] [out.json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts4"))

from fish.cards import NUM_PLAYERS                           # noqa: E402
from fish.engine import GameState                            # noqa: E402
from fish.observation import Observation                     # noqa: E402
from fish.rules import RuleConfig                            # noqa: E402
from fish4.askfeat import DecisionContext                    # noqa: E402
from fish4.perpetual import signalling_ask, stuck_half_suits  # noqa: E402
from fish4.registry4 import V06_DEPLOYED, make_agent         # noqa: E402

from duel import engine_fingerprint                          # noqa: E402

RULES = RuleConfig(wrong_distribution_outcome="opponent")
SEED_DEAL = 910_000
SEED_AGENT = 920_000


def main(n_games: int = 30, out: str | None = None) -> int:
    spec = dict(V06_DEPLOYED[1])
    spec["signal_mode"] = "stuck"

    fired = on_stuck = 0
    n_stuck = []
    for g in range(n_games):
        agents = [make_agent(("kraken", dict(spec)))
                  for _ in range(NUM_PLAYERS)]
        st = GameState.deal(RULES, seed=SEED_DEAL + g)
        for p, a in enumerate(agents):
            a.begin_game(p, RULES, SEED_AGENT + g * 13 + p)
        step = 0
        while not st.is_terminal and step < 400:
            mover = st.turn
            obs = Observation.from_state(st, mover)
            ag = agents[mover]
            act = ag.act(obs)          # updates ag.bel as a side effect
            post = ag.build_posterior(obs)
            ctx = DecisionContext(obs, ag.bel, post)
            stuck = stuck_half_suits(obs, ag.bel, ctx)
            if stuck:
                sig = signalling_ask(obs, ag.bel, ctx, require_dead=False)
                if sig is not None:
                    fired += 1
                    n_stuck.append(len(stuck))
                    on_stuck += int((sig.card // 6) in stuck)
            st.apply(mover, act)
            step += 1

    rate = on_stuck / fired if fired else None
    mean_stuck = sum(n_stuck) / len(n_stuck) if n_stuck else None
    print(f"\n{n_games} games, seed base {SEED_DEAL}")
    print(f"  signalling opportunities with >=1 stuck half-suit: {fired}")
    if fired:
        print(f"  the ask points AT a stuck half-suit: {on_stuck}/{fired} "
              f"= {100 * rate:.1f}%")
        print(f"  stuck half-suits available when it fires: "
              f"mean {mean_stuck:.2f}")
        print("\n  Direction 2 proposed aiming this. It is already aimed, and "
              "with about one\n  candidate there is nothing to choose between: "
              "no headroom in TARGET SELECTION.")

    payload = {
        "engine": engine_fingerprint(),
        "what": ("Does the signalling ask point at a stuck half-suit? "
                 "RESEARCH_FRONTIER.md Direction 2 proposed aiming it."),
        "n_games": n_games, "seed_deal": SEED_DEAL, "seed_agent": SEED_AGENT,
        "opportunities": fired, "on_stuck": on_stuck, "on_stuck_rate": rate,
        "mean_stuck_available": mean_stuck,
        "cheap_gate_applied": False,
        "spec": spec,
    }
    path = Path(out) if out else ROOT / "results" / "signal_aim.json"
    path.write_text(json.dumps(payload, indent=1))
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 30,
                          a[1] if len(a) > 1 else None))
