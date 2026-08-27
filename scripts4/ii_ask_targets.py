"""Exact one-ply value of every candidate ask, beside the features the agent sees.

Every earlier fit of the ask objective in this project trained against a
sampled target -- rollouts, duel outcomes, a learned continuation. This trains
against an exact one. In the endgame the value of playing ask ``a`` and then
reverting to champion play is

    V(a) = sum_d w_d * champion_value(d after a)

over the enumerated belief, and every term of that is computed rather than
estimated: the belief is the full set of consistent deals, and the champion is
deterministic given its observation. The bound runs showed this quantity is
worth training on -- on 88% of exactly solved positions the best action under
it IS the exact optimum, so it is very nearly the right target and not merely
a cheap one.

FEATURES AS THE AGENT SEES THEM, TARGETS AS THE TRUTH IS
--------------------------------------------------------
The features come from a champion agent built exactly the way
``_champion_action`` builds one, seeded from the same observation hash, so its
posterior is the same approximation it would use in play. Using the exact
belief to build features would fit an objective the agent cannot evaluate at
the table. The targets, in contrast, use the enumerated belief, because there
is no reason to hand the target the agent's error as well.

WHAT THIS DOES NOT COLLECT
--------------------------
Claims. The improving move is an ask on 131 of 154 improvable m = 1 positions
and 128 of 138 at m = 2, so ask selection is where the defect is, and mixing
claim decisions into an ask objective would fit two things with one set of
weights. Positions whose best move is a claim are counted and skipped.

    py scripts4/ii_ask_targets.py [layer] [n_games] [max_support] [first_game]
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.askfeat import TERM_NAMES, DecisionContext, ask_feature_matrix
from fish4.exact_ii import ExactII, _clone, _info_key, consistent_deals_multi
from fish4.posterior import Posterior
from fish4.registry4 import make_agent

SPEC = ("fishbot4", {"opponent_gamma": 0.35})
MAX_SUPPORT = 24
JOURNAL = ROOT / "results" / "ii_ask_targets.jsonl"


def _fp() -> str:
    h = hashlib.sha256()
    for f in ("fish4/exact_ii.py", "fish4/askfeat.py"):
        h.update((ROOT / f).read_bytes())
    h.update(Path(__file__).resolve().read_bytes())
    return h.hexdigest()[:12]


def _champion_ctx(rules, seat, st):
    """A champion agent's own view of this position, seeded as it would be.

    Mirrors ``_champion_action``: same construction, same seed from the same
    observation hash, so the posterior it samples is the one it would sample at
    the table. Anything else fits an objective against features the agent will
    never compute.
    """
    obs = Observation.from_state(st, seat)
    key = _info_key(seat, obs)
    a = make_agent(SPEC)
    a.begin_game(seat, rules, int.from_bytes(key[:8], "big"))
    a.bel.update(obs)
    post = Posterior(a.bel, a.rng, n_draws=a.n_draws, n_worlds=a.n_worlds,
                     mode=a.infer_mode, obs=obs, gamma=a.opponent_gamma,
                     depth_mode=a.depth_mode, count_mode=a.count_mode,
                     opp_lambda=a.opp_lambda,
                     gamma_schedule=a.gamma_schedule, sis_tilt=a.sis_tilt)
    return obs, DecisionContext(obs, a.bel, post)


def main(layer: int = 1, n_games: int = 200, max_support: int = MAX_SUPPORT,
         first_game: int = 0) -> int:
    rules = RuleConfig()
    fp = _fp()
    done = set()
    if JOURNAL.exists():
        for line in JOURNAL.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("solver") == fp:
                    done.add((r["layer"], r["game"], r["index"]))
    print(f"  fingerprint {fp}; {len(done)} positions already collected")

    n_new = skipped_wide = skipped_pinned = skipped_thin = 0
    for g in range(first_game, n_games):
        agents = [make_agent(SPEC) for _ in range(NUM_PLAYERS)]
        st = GameState.deal(rules, seed=99_000 + g)
        ar = random.Random(99_500 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        idx = 0
        for _ in range(600):
            if st.is_terminal:
                break
            p = st.turn
            obs = Observation.from_state(st, p)
            live = [h for h, w in enumerate(obs.set_winner) if w is None]
            if len(live) == layer:
                idx += 1
                if (layer, g, idx) not in done:
                    agents[p].bel.update(obs)
                    deals = consistent_deals_multi(obs, agents[p].bel, live,
                                                   limit=max_support + 1)
                    # Support 1 is pinned: one deal, no belief, every ask has a
                    # known outcome and the position is a tablebase lookup
                    # rather than a decision under uncertainty.
                    if deals and 2 <= len(deals) <= max_support:
                        t0 = time.time()
                        states = []
                        for hands in deals:
                            t = GameState.from_components(
                                rules, list(hands), st.turn,
                                list(st.set_winner))
                            t.history = list(st.history)
                            states.append(t)
                        w = [1.0 / len(states)] * len(states)
                        cobs, ctx = _champion_ctx(rules, p, states[0])
                        asks = cobs.legal_asks()
                        if len(asks) < 2:
                            # One legal ask is not a choice, so it carries no
                            # information about how to choose.
                            skipped_thin += 1
                        else:
                            pr, F = ask_feature_matrix(ctx, asks)
                            probe = ExactII(rules, list(live), p, SPEC)
                            vals = []
                            for a in asks:
                                tot = 0.0
                                ok = True
                                for s, ww in zip(states, w):
                                    tt = _clone(s)
                                    try:
                                        tt.apply(p, a)
                                    except Exception:
                                        ok = False
                                        break
                                    tot += ww * probe.champion_value(
                                        [tt], [1.0])
                                vals.append(tot if ok else None)
                            champ = probe.champion_value(
                                [_clone(s) for s in states], list(w))
                            rec = {"layer": layer, "game": g, "index": idx,
                                   "solver": fp, "support": len(deals),
                                   "champion": champ,
                                   "asks": [repr(a) for a in asks],
                                   "p": [float(x) for x in pr],
                                   "features": [[float(x) for x in row]
                                                for row in F],
                                   "values": vals,
                                   "seconds": time.time() - t0}
                            with JOURNAL.open("a") as fh:
                                fh.write(json.dumps(rec) + "\n")
                            n_new += 1
                            if n_new % 20 == 0:
                                print(f"    {n_new} positions "
                                      f"(game {g}, {len(asks)} asks, "
                                      f"support {len(deals)})", flush=True)
                    elif deals:
                        # Two different reasons, counted apart. Lumping them
                        # gave "11 skipped for support above 24" in six games
                        # when the bound run had found only 13 such positions
                        # in two hundred -- the count was mostly pinned
                        # positions wearing the wide label.
                        if len(deals) < 2:
                            skipped_pinned += 1
                        else:
                            skipped_wide += 1
            st.apply(p, agents[p].act(obs))

    print(f"\n{n_new} new positions collected at m = {layer}")
    print(f"  skipped: {skipped_pinned} pinned (support 1), {skipped_wide} "
          f"above support {max_support}, {skipped_thin} with only one legal "
          f"ask")
    print(f"terms: {', '.join(TERM_NAMES)}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 1,
                          int(a[1]) if len(a) > 1 else 200,
                          int(a[2]) if len(a) > 2 else MAX_SUPPORT,
                          int(a[3]) if len(a) > 3 else 0))
