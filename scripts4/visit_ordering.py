"""When a free card is on the table, do we take it before we gamble?

THE LEAD THIS CHASES. `results/disclosure_cost_15300000.json` refuted the
hypothesis it was built for and left one fact behind that points the other way:
on essentially the same number of visits, SESTINA extracts **1.7581** cards
against our **1.6063**, with 1,278 runs of three or more against our 939. The
retained-turn compounding is real and they are the ones exploiting it.

`fish/engine.py::_apply_ask` says "asker retains the turn" on success, so a visit
is a run of asks that ends at the first failure. That makes ORDERING WITHIN A
VISIT worth something on its own: a card whose location the public record already
fixes is a free continuation, and spending the turn on a gamble first forfeits
every certain steal still standing behind it. A policy that gambles early pays
for it with the whole rest of the run.

THE CLASSIFIER IS OBJECTIVE AND SHARED. `BeliefState.public_loc[c]` is None,
a player, or RESOLVED, and it is written only from public events -- so it is the
same for every observer and the same for both engines. An ask is a CERTAIN steal
when `public_loc[card]` is the target. No posterior, no threshold, no model of
anyone: both sides are scored by the identical rule, which is what makes the
comparison mean anything.

THE SELF-TEST CANNOT BE FUDGED. If the public record says a player holds a card,
the true hand must agree. Every certain steal is checked against the real state,
and a single disagreement means this script is misreading the record and no rate
below may be read.

Ground truth is used as a LABEL ONLY, never acted on and never shown to an agent.

Descriptive. No arm, no duel, no ship claim.
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.beliefs import BeliefState                               # noqa: E402
from fish.cards import NUM_PLAYERS, team_of                        # noqa: E402
from fish.engine import Ask, GameState                             # noqa: E402
from fish.observation import Observation                            # noqa: E402
from fish.rules import RuleConfig                                   # noqa: E402
from scripts4.resultfile import default_path, write                # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 15_500_000
AGENT0 = 155_000
MAX_ACTIONS = 600
BOOT = 2000
BOOT_SEED = 20_260_923
RESOLVED = -1


def _boot(per_game: list[dict], num: str, den: str,
          boot: int = BOOT, seed: int = BOOT_SEED) -> list[float]:
    rng = random.Random(seed)
    n = len(per_game)
    out = []
    for _ in range(boot):
        pick = [per_game[rng.randrange(n)] for _ in range(n)]
        a = sum(r.get(num, 0) for r in pick)
        b = sum(r.get(den, 0) for r in pick)
        if b:
            out.append(a / b)
    out.sort()
    if not out:
        return [float("nan")] * 2
    return [out[int(0.025 * len(out))],
            out[min(len(out) - 1, int(0.975 * len(out)))]]


def certain_steals(bel, st, actor: int) -> list[Ask]:
    """Legal asks whose card the PUBLIC RECORD already places with the target."""
    out = []
    for ask in st.legal_asks(actor):
        loc = bel.public_loc[ask.card]
        if loc is not None and loc != RESOLVED and loc == ask.target:
            out.append(ask)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--games", type=int, default=400)
    a = ap.parse_args(argv)

    from fish4.registry4 import KRAKEN_V1, make_agent
    from fish4.dylan_v07 import DylanV07

    rules = RuleConfig(**RULES_D)
    t0 = time.time()
    per: list[dict] = []
    #: a "certain" steal the true hands contradict: the record was misread
    liars: list = []

    for g in range(a.games):
        seed = SEED0 + g
        kv_even = (g % 2 == 0)
        agents = []
        for p in range(NUM_PLAYERS):
            agents.append(make_agent(KRAKEN_V1) if (p % 2 == 0) == kv_even
                          else DylanV07())
        our_team = 0 if kv_even else 1
        st = GameState.deal(rules, seed=seed)
        for p, ag in enumerate(agents):
            ag.begin_game(p, rules, AGENT0 + seed * 13 + p)
        # ONE shared belief, read only for public_loc, which is written from
        # public events alone and is therefore the same for every observer.
        shared = BeliefState(rules, observer=0)

        row = {"game": g}
        for side in ("ours", "theirs"):
            for k in ("decisions", "had_certain", "took_certain",
                      "gambled_with_certain_up", "gamble_failed_with_certain_up",
                      "n_certain_available"):
                row[f"{side}_{k}"] = 0

        for _ in range(MAX_ACTIONS):
            if st.is_terminal:
                break
            actor = st.turn
            shared.update(Observation.from_state(st, 0))
            free = certain_steals(shared, st, actor)
            # THE SELF-TEST. The public record cannot be wrong about a location.
            for ask in free:
                if not (st.hands[ask.target] >> ask.card & 1):
                    if len(liars) < 10:
                        liars.append({"game": g, "card": ask.card,
                                      "target": ask.target})
            act = agents[actor].act(Observation.from_state(st, actor))
            side = "ours" if team_of(actor) == our_team else "theirs"
            row[f"{side}_decisions"] += 1
            if free:
                row[f"{side}_had_certain"] += 1
                row[f"{side}_n_certain_available"] += len(free)
                chose_free = isinstance(act, Ask) and any(
                    act.card == f.card and act.target == f.target for f in free)
                if chose_free:
                    row[f"{side}_took_certain"] += 1
                else:
                    row[f"{side}_gambled_with_certain_up"] += 1
                    # did the gamble cost the visit? a failed ask hands the
                    # turn over with the free cards still standing
                    if isinstance(act, Ask) and not (
                            st.hands[act.target] >> act.card & 1):
                        row[f"{side}_gamble_failed_with_certain_up"] += 1
            st.apply(actor, act)
        per.append(row)
        if (g + 1) % 50 == 0 or g + 1 == a.games:
            print(f"  {g+1}/{a.games} games, {(time.time()-t0)/60:.1f} min",
                  flush=True)

    def tot(k):
        return sum(r.get(k, 0) for r in per)

    out = {"script": "scripts4/visit_ordering.py", "descriptive": True,
           "rules": RULES_D, "seed_deal": SEED0, "seed_agent": AGENT0,
           "n_games": a.games,
           "classifier": "BeliefState.public_loc[card] == ask.target",
           "selftest_public_loc_contradicted_by_the_hands": len(liars),
           "selftest_examples": liars, "per_game": per,
           "ground_truth_use": "label only, never acted on, never shown"}
    for side in ("ours", "theirs"):
        had = tot(f"{side}_had_certain")
        out[f"{side}_decisions"] = tot(f"{side}_decisions")
        out[f"{side}_had_certain"] = had
        out[f"{side}_took_certain"] = tot(f"{side}_took_certain")
        out[f"{side}_take_rate"] = (tot(f"{side}_took_certain") / had) if had \
            else float("nan")
        out[f"{side}_take_rate_ci"] = _boot(per, f"{side}_took_certain",
                                           f"{side}_had_certain")
        out[f"{side}_gambled"] = tot(f"{side}_gambled_with_certain_up")
        out[f"{side}_gamble_failed"] = tot(
            f"{side}_gamble_failed_with_certain_up")
        out[f"{side}_gamble_fail_rate"] = (
            tot(f"{side}_gamble_failed_with_certain_up") /
            tot(f"{side}_gambled_with_certain_up")
            if tot(f"{side}_gambled_with_certain_up") else float("nan"))
        out[f"{side}_mean_certain_available"] = (
            tot(f"{side}_n_certain_available") / had) if had else float("nan")

    print("\n" + "=" * 72)
    print(f"  SELF-TEST: 'certain' steals the true hands contradict: "
          f"{len(liars)}")
    if liars:
        print("  *** MUST BE ZERO. The public record cannot be wrong about a")
        print("  *** location, so this script is misreading it and NO RATE")
        print("  *** BELOW MAY BE READ. First:")
        for x in liars[:3]:
            print(f"      {x}")
    print("=" * 72)
    print("  WHEN A FREE CARD IS ON THE TABLE, WHO TAKES IT?")
    print(f"  {a.games} games. A certain steal is one the PUBLIC RECORD already")
    print("  places with the target -- same rule for both engines.")
    print("=" * 72)
    for side, label in (("ours", "KRAKEN"), ("theirs", "SESTINA")):
        lo, hi = out[f"{side}_take_rate_ci"]
        print(f"  {label:<8} {out[f'{side}_had_certain']:>6,} decisions with one"
              f" up,  took it {out[f'{side}_take_rate']:.4f}"
              f"  [{lo:.4f}, {hi:.4f}]")
    print("-" * 72)
    print("  and when they gambled instead, how often did it cost the visit?")
    for side, label in (("ours", "KRAKEN"), ("theirs", "SESTINA")):
        print(f"  {label:<8} gambled {out[f'{side}_gambled']:>6,} times,"
              f"  failed {out[f'{side}_gamble_failed']:>6,}"
              f"  ({out[f'{side}_gamble_fail_rate']:.4f})"
              f"   mean free cards up "
              f"{out[f'{side}_mean_certain_available']:.2f}")
    print("\n  A failed ask hands the turn over with every free card still")
    print("  standing, so a gamble taken ahead of a certain steal is paid for")
    print("  with the rest of the run.")
    print(f"\n  wrote {write(default_path('visit_ordering', SEED0), out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
