"""Does our posterior sample worlds that no deal plus this history could produce?

THE QUESTION, AND WHY IT IS NOT THE ONE THE LAST SCREEN COULD ANSWER

`results/policy_inversion_bite_14100000.json` found that only **26.0%** of the
worlds the champion's posterior resamples survive the v0.7 bridge's own
consistency checks -- the rest rejected either because the dealt-hand
reconstruction does not come to nine cards or because a forward replay ends on
a different hand than the arbiter holds. Two readings fit that and the screen
could not separate them:

  1. our posterior puts mass on worlds that are UNREACHABLE -- no assignment
     of the deal is consistent with both the sampled current hands and the
     public transfer history. That would be a defect in the belief, and it
     would affect every quantity the posterior produces, not just an inverter.
  2. `Observation.initial_hand()` is not valid for counterfactual use. It
     restores resolved half-suits from `ev.revealed`, the TRUE holder at
     resolution, so a counterfactual current hand is reconciled against a real
     historical fact and can fail the count for that reason alone.

THE DISCRIMINATOR NEEDS NO ENGINE. Reachability is arithmetic. Every card's
holder is determined backwards from the public record:

  * a card of an UNRESOLVED half-suit is held, now, by whoever the world says;
  * a card of a RESOLVED half-suit was held, at resolution, by
    `ev.revealed[i]` -- a public fact the counterfactual cannot change;
  * every successful ask moves one named card from target to asker, so walking
    the history backwards from either starting point names its dealt owner.

A world is reachable exactly when that walk gives all six seats nine cards.
This file runs that test on the posterior's own draws and on the true world.
The true world MUST come out reachable; it is the self-test, and if it fails
the test is wrong rather than the belief.

WHAT EACH OUTCOME MEANS, fixed before the run:

  reachable share near 1.00   the belief is sound and the bridge's rejections
                              are reading 2 -- a harness limit. The inversion
                              screen's 1.24 bits then rests on a subset
                              selected by an artefact, and has to be redone.
  reachable share near 0.26   reading 1. Our posterior spends three quarters
                              of its draws on worlds that cannot exist, which
                              is a defect in the belief and is far larger than
                              the inversion question that turned it up.
  anything between            both are live and the gap is the artefact's
                              share.

PREDICTION, RECORDED BEFORE THE RUN: near 1.00, reading 2. The constraint
store is built from the same public events this walk uses, and a sampler that
respected current locations but not reachability would have shown up in the
SIS feasibility counters long ago.

    py scripts4/world_reachability.py [--games 20] [--cap 40]
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS                              # noqa: E402
from fish.engine import AskEvent, ClaimEvent, GameState         # noqa: E402
from fish.observation import Observation                        # noqa: E402
from fish.rules import RuleConfig                              # noqa: E402
from scripts4.resultfile import default_path, write             # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 14_300_000
AGENT0 = 143_000
MAX_ACTIONS = 600
DECK = 54
PER_SEAT = 9


def dealt_owners(hands, history, set_winner):
    """The dealt owner of every card, or None where the record cannot say.

    `hands` is a candidate assignment of CURRENT hands. Cards of resolved
    half-suits are in nobody's hand, so their holder at resolution is taken
    from the ClaimEvent that resolved them -- a public fact, and the one place
    a counterfactual world has no freedom.
    """
    holder = [None] * DECK
    for p in range(NUM_PLAYERS):
        h = hands[p]
        for c in range(DECK):
            if h >> c & 1:
                holder[c] = p
    for ev in history:
        if isinstance(ev, ClaimEvent) and ev.revealed_known:
            for i, who in enumerate(ev.revealed):
                holder[ev.half_suit * 6 + i] = who
    # Walk backwards: before a successful ask, the card sat with the target.
    for ev in reversed(history):
        if isinstance(ev, AskEvent) and ev.success:
            if holder[ev.card] == ev.asker:
                holder[ev.card] = ev.target
            else:
                #: The world says someone else holds it at this point, which
                #: the public record forbids. Unreachable, and named so rather
                #: than silently producing a wrong count.
                return None
    return holder


def reachable(hands, history, set_winner):
    own = dealt_owners(hands, history, set_winner)
    if own is None or any(o is None for o in own):
        return False
    counts = [0] * NUM_PLAYERS
    for o in own:
        counts[o] += 1
    return all(n == PER_SEAT for n in counts)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--games", type=int, default=20)
    ap.add_argument("--cap", type=int, default=40)
    a = ap.parse_args(argv)

    from fish4.registry4 import KRAKEN_V1, make_agent
    from fish4.dylan_v07 import DylanV07

    rules = RuleConfig(**RULES_D)
    rng = random.Random(20_260_923)
    n_w = n_ok = n_dec = 0
    truth_n = truth_ok = 0
    t0 = time.time()

    for g in range(a.games):
        seed = SEED0 + g
        kv_even = (g % 2 == 0)
        agents = [make_agent(KRAKEN_V1) if (p % 2 == 0) == kv_even
                  else DylanV07() for p in range(NUM_PLAYERS)]
        ours = [p for p in range(NUM_PLAYERS) if (p % 2 == 0) == kv_even]
        st = GameState.deal(rules, seed=seed)
        for p, ag in enumerate(agents):
            ag.begin_game(p, rules, AGENT0 + seed * 13 + p)
        picked = 0
        for _ in range(MAX_ACTIONS):
            if st.is_terminal:
                break
            actor = st.turn
            act = agents[actor].act(Observation.from_state(st, actor))
            if actor in ours and picked < a.cap and rng.random() < 0.5:
                picked += 1
                n_dec += 1
                # The self-test: the world that actually happened.
                truth_n += 1
                truth_ok += int(reachable(list(st.hands), st.history,
                                          st.set_winner))
                obs = Observation.from_state(st, actor)
                for w in agents[actor].build_posterior(obs).worlds():
                    n_w += 1
                    n_ok += int(reachable(list(w), st.history, st.set_winner))
            st.apply(actor, act)
        print(f"  {g+1}/{a.games} games, {n_dec} decisions, {n_w:,} worlds, "
              f"{(time.time()-t0)/60:.1f} min", flush=True)

    if not n_w:
        print("no worlds drawn", file=sys.stderr)
        return 1
    share = n_ok / n_w
    trate = truth_ok / truth_n if truth_n else 0.0
    out = {"script": "scripts4/world_reachability.py", "descriptive": True,
           "rules": RULES_D, "seed_deal": SEED0, "seed_agent": AGENT0,
           "n_games": a.games, "n_decisions": n_dec, "n_worlds": n_w,
           "reachable_worlds": n_ok, "reachable_share": share,
           "truth_n": truth_n, "truth_reachable": truth_ok,
           "truth_share": trate,
           "bridge_survival_for_comparison": 0.26,
           "world_source": "FishBot4.build_posterior(...).worlds()"}
    print("\n" + "=" * 72)
    print(f"  SELF-TEST: the TRUE world is reachable {truth_ok}/{truth_n} "
          f"({trate:.4f})")
    if trate < 0.999:
        print("  *** BELOW 1.000. The world that actually happened must be")
        print("  *** reachable by definition, so the TEST is wrong, not the")
        print("  *** belief, and the share below may not be read.")
    print("=" * 72)
    print(f"  DOES OUR POSTERIOR SAMPLE UNREACHABLE WORLDS?")
    print(f"  {n_dec:,} decisions, {n_w:,} sampled worlds")
    print(f"\n  reachable share  {share:.4f}   "
          f"(the bridge accepted 0.26 of the same kind of draw)")
    print("\n  Near 1.00 means the belief is sound and the bridge's")
    print("  rejections are a counterfactual-reconstruction artefact.")
    print("  Near 0.26 means the posterior spends three quarters of its")
    print("  draws on worlds that cannot exist.")
    print(f"\n  wrote {write(default_path('world_reachability', SEED0), out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
