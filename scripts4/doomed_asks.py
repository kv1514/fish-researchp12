"""We spend a ninth of our asks on half-suits our own team already owns.

THE MEASUREMENT THAT FOUND IT. Classifying every ask by the asker's TEAM's
pre-ask count in the chosen half-suit, over 40 games:

    ours     216 of 1,830 asks (11.80%) in a half-suit the team owned ENTIRELY
    theirs   183 of 1,859 asks ( 9.84%)
    of those, hits:  0 and 0

Zero hits is not a coincidence, it is the rule: if your team holds all six, the
target is an opponent and an opponent holds none of them, so the ask CANNOT
succeed. It is a guaranteed failure, and `_apply_ask` hands the turn to the
target on a failure, so each one costs the whole rest of the visit.

THESE ARE NOT SIGNALS. This engine has a signalling protocol whose whole method
is a deliberately doomed ask, and the paper prices it. It is OFF in the
champion: `signal_mode='off'`, `signal_budget=0`, `w_signal=0.0`,
`convention_beta=0.0`. So these are incidental -- the asker did not know its
partner held the rest.

WHAT THIS SCRIPT ASKS. Not whether the asks are doomed, which is already
established, but whether the engine HAD THE INFORMATION and asked anyway. At
each doomed ask it reads the seat's own posterior and computes

    P(our team holds all six of this half-suit)

from the same worlds the policy reasons over. If that probability is usually
near zero, the engine was blind and the fix is inference. If it is often high,
the engine knew and the fix is the decision rule -- and there is a band between
"sure enough to declare" (the gate reads 0.97 on the JOINT assignment) and
"sure enough to know asking is pointless", which needs no split at all.

The belief is brought current with `bel.update(obs)` before it is read, because
`FishBot4.act` calls that inside `act` and a posterior read outside it would
otherwise be stale -- the defect that cost `policy_inversion_bite` four figures.

Ground truth is used as a LABEL ONLY: it selects which asks to examine and is
never shown to an agent.

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

from fish.cards import (CARDS_PER_HALF_SUIT, NUM_PLAYERS,          # noqa: E402
                        half_suit_mask, half_suit_of, team_of)
from fish.engine import Ask, GameState                             # noqa: E402
from fish.observation import Observation                            # noqa: E402
from fish.rules import RuleConfig                                   # noqa: E402
from scripts4.resultfile import default_path, write                # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 17_100_000
AGENT0 = 171_000
MAX_ACTIONS = 600
BOOT = 2000
BOOT_SEED = 20_260_923
BANDS = (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 0.97)


def _team_count(hands, hs: int, team: int) -> int:
    m = half_suit_mask(hs)
    return sum(bin(hands[p] & m).count("1")
               for p in range(NUM_PLAYERS) if team_of(p) == team)


def _boot(per: list[dict], num: str, den: str,
          boot: int = BOOT, seed: int = BOOT_SEED) -> list[float]:
    rng = random.Random(seed)
    n = len(per)
    out = []
    for _ in range(boot):
        pick = [per[rng.randrange(n)] for _ in range(n)]
        a = sum(r.get(num, 0) for r in pick)
        b = sum(r.get(den, 0) for r in pick)
        if b:
            out.append(a / b)
    out.sort()
    if not out:
        return [float("nan")] * 2
    return [out[int(0.025 * len(out))],
            out[min(len(out) - 1, int(0.975 * len(out)))]]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--games", type=int, default=120)
    ap.add_argument("--no-belief", action="store_true",
                    help="skip the posterior read. The doomed-ask RATE varies "
                         "a lot between seed blocks -- 0.118 over 40 games at "
                         "one block against 0.225 over 10 at another, both "
                         "confirmed by a second implementation -- so the rate "
                         "needs hundreds of games and the belief read is the "
                         "expensive part.")
    a = ap.parse_args(argv)

    from fish4.registry4 import KRAKEN_V1, make_agent
    from fish4.dylan_v07 import DylanV07

    rules = RuleConfig(**RULES_D)
    t0 = time.time()
    per: list[dict] = []
    #: a doomed ask that SUCCEEDED would mean the team count is wrong
    impossible = 0

    for g in range(a.games):
        seed = SEED0 + g
        kv_even = (g % 2 == 0)
        agents = [make_agent(KRAKEN_V1) if (p % 2 == 0) == kv_even
                  else DylanV07() for p in range(NUM_PLAYERS)]
        ours = {p for p in range(NUM_PLAYERS) if (p % 2 == 0) == kv_even}
        our_team = 0 if kv_even else 1
        st = GameState.deal(rules, seed=seed)
        for p, ag in enumerate(agents):
            ag.begin_game(p, rules, AGENT0 + seed * 13 + p)

        row = {"game": g, "asks": 0, "doomed": 0, "p_sum": 0.0,
               "their_asks": 0, "their_doomed": 0}
        for b in BANDS:
            row[f"ge{b}"] = 0

        for _ in range(MAX_ACTIONS):
            if st.is_terminal:
                break
            actor = st.turn
            obs = Observation.from_state(st, actor)
            act = agents[actor].act(obs)
            if actor not in ours and isinstance(act, Ask):
                row["their_asks"] += 1
                if _team_count(st.hands, half_suit_of(act.card),
                               1 - our_team) == 6:
                    row["their_doomed"] += 1
            if actor in ours and isinstance(act, Ask):
                row["asks"] += 1
                hs = half_suit_of(act.card)
                if _team_count(st.hands, hs, our_team) == 6:
                    row["doomed"] += 1
                    if st.hands[act.target] >> act.card & 1:
                        impossible += 1
                    # WHAT DID IT KNOW? The belief is already current: act()
                    # ran bel.update(obs) on this same observation a moment ago.
                    #
                    # THE RNG STATE IS SAVED AND RESTORED, and that is not a
                    # nicety. `build_posterior` draws from the agent's OWN rng,
                    # so reading a diagnostic posterior mid-game advances it and
                    # every later decision in the deal differs from the one the
                    # engine would really have made. The first version of this
                    # script did that and reported a doomed-ask share of 0.218
                    # against 0.118 measured on unperturbed play -- it was
                    # measuring games its own instrument had changed.
                    if a.no_belief:
                        st.apply(actor, act)
                        continue
                    _rng = agents[actor].rng.getstate()
                    try:
                        pool = [h for h in agents[actor].build_posterior(
                            obs).worlds() if h is not None]
                    finally:
                        agents[actor].rng.setstate(_rng)
                    if pool:
                        m = half_suit_mask(hs)
                        good = sum(
                            1 for w in pool
                            if sum(bin(w[p] & m).count("1")
                                   for p in range(NUM_PLAYERS)
                                   if team_of(p) == our_team) == 6)
                        p_all = good / len(pool)
                        row["p_sum"] += p_all
                        for b in BANDS:
                            if p_all >= b:
                                row[f"ge{b}"] += 1
            st.apply(actor, act)
        per.append(row)
        if (g + 1) % 20 == 0 or g + 1 == a.games:
            print(f"  {g+1}/{a.games} games, {(time.time()-t0)/60:.1f} min",
                  flush=True)

    def tot(k):
        return sum(r.get(k, 0) for r in per)

    asks, doomed = tot("asks"), tot("doomed")
    out = {"script": "scripts4/doomed_asks.py", "descriptive": True,
           "rules": RULES_D, "seed_deal": SEED0, "seed_agent": AGENT0,
           "n_games": a.games, "asks": asks, "doomed": doomed,
           "doomed_share": (doomed / asks) if asks else float("nan"),
           "doomed_share_ci": _boot(per, "doomed", "asks"),
           "doomed_per_game": doomed / a.games,
           "their_asks": tot("their_asks"), "their_doomed": tot("their_doomed"),
           "their_doomed_share": (tot("their_doomed") / tot("their_asks"))
           if tot("their_asks") else float("nan"),
           "their_doomed_share_ci": _boot(per, "their_doomed", "their_asks"),
           "selftest_doomed_ask_that_hit": impossible,
           "mean_p_team_owns_all_six": (tot("p_sum") / doomed) if doomed
           else float("nan"),
           "signalling": "off in the champion: signal_mode=off, budget=0, "
                         "w_signal=0, convention_beta=0",
           "bands": {}, "per_game": per}
    for b in BANDS:
        out["bands"][str(b)] = {
            "n": tot(f"ge{b}"),
            "share": (tot(f"ge{b}") / doomed) if doomed else None,
            "ci": _boot(per, f"ge{b}", "doomed") if doomed else None}

    print("\n" + "=" * 72)
    print(f"  SELF-TEST: doomed asks that nevertheless hit: {impossible}")
    if impossible:
        print("  *** MUST BE ZERO -- an opponent cannot hold a card of a")
        print("  *** half-suit your team owns entirely, so the team count is")
        print("  *** wrong and NOTHING BELOW MAY BE READ.")
    print("=" * 72)
    print("  ASKS INTO HALF-SUITS OUR OWN TEAM ALREADY OWNS")
    print(f"  {a.games} games, {asks:,} of our asks")
    print("=" * 72)
    lo, hi = out["doomed_share_ci"]
    print(f"  doomed asks      {doomed:,}   "
          f"{out['doomed_share']:.4f} [{lo:.4f}, {hi:.4f}] of our asks, "
          f"{out['doomed_per_game']:.2f} a game")
    tlo, thi = out["their_doomed_share_ci"]
    print(f"  SESTINA          {out['their_doomed']:,}   "
          f"{out['their_doomed_share']:.4f} [{tlo:.4f}, {thi:.4f}] "
          f"of theirs")
    print(f"  each one loses the turn, because a failed ask hands it over")
    print("-" * 72)
    print("  WHAT DID THE BELIEF THINK P(our team holds all six) WAS?")
    print(f"  mean {out['mean_p_team_owns_all_six']:.4f}")
    print(f"  {'threshold':>10}  {'doomed asks at or above it':>28}  {'share':>8}")
    for b in BANDS:
        r = out["bands"][str(b)]
        print(f"  {b:>10.2f}  {r['n']:>28,}  {r['share']:>8.4f}")
    print("\n  Near zero everywhere means the engine was blind and the fix is")
    print("  inference. High means it knew and the fix is the decision rule --")
    print("  the declaration gate reads 0.97 on the JOINT, and knowing an ask")
    print("  is pointless needs no split at all.")
    print(f"\n  wrote {write(default_path('doomed_asks', SEED0), out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
