"""P(our partner asks in this half-suit | how many of it they hold).

THE ARM'S WEIGHT TABLE, ESTIMATED DIRECTLY. `partner_ask_calibration.py`
established that after the belief has ingested the ask -- legality constraint
and all -- our posterior still under-predicts the partner's holdings in the
half-suit they chose. That is a gap, not a mechanism. This script estimates the
mechanism: the likelihood a partner-side inverter would multiply into the
posterior.

For every decision where our partner asks, and every live half-suit h, record
how many cards of h the partner ACTUALLY held and whether h is the one they
chose. Then

    P(chosen | k) = (pairs with count k that were chosen)
                    / (pairs with count k)

is a nonparametric estimate of exactly the factor a reweighting needs. Nothing
is fitted, no functional form is assumed, and no policy is replayed: the
partner's own policy generated these choices, so the table is its inversion
read off the outcomes.

THE COUNT IS THE PRE-ASK COUNT. The choice was made from the hand they held
when they made it, so a successful ask's gained card must not be in k. Getting
this backwards would put the asked card into the evidence for asking.

THE SELF-TEST IS LOAD-BEARING AND CANNOT BE FUDGED. Fish forbids asking in a
half-suit you hold no card of, so

    P(chosen | k = 0) must be EXACTLY 0.

If a single k=0 pair is recorded as chosen, this harness is misreading either
the hand or the half-suit, and no row of the table may be read. The
`policy_inversion_bite` screen spent four published figures on a defect in my
own instrument before a self-test like this one caught it.

WHAT THIS IS NOT. A per-half-suit factor is an approximation: the real choice
is among the alternatives jointly, so the factors are not independent across h
within a decision. Used as an importance weight the per-decision normalisation
absorbs the leading part of that, but the approximation is real and is not
hidden here. And a likelihood is not a set -- what this buys has to be measured
by a duel against the bar, in both populations, like everything else.

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
                        half_suit_mask, half_suit_of)
from fish.engine import Ask, GameState                             # noqa: E402
from fish.observation import Observation                            # noqa: E402
from fish.rules import RuleConfig                                   # noqa: E402
from scripts4.resultfile import default_path, write                # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 14_800_000
AGENT0 = 148_000
MAX_ACTIONS = 600
BOOT = 2000
BOOT_SEED = 20_260_923


def _count(mask: int, hs: int) -> int:
    return bin(mask & half_suit_mask(hs)).count("1")


def _boot_table(per_game: list[dict], ks: list[int],
                boot: int = BOOT, seed: int = BOOT_SEED) -> dict:
    """Cluster bootstrap over GAMES for each P(chosen | k)."""
    rng = random.Random(seed)
    n = len(per_game)
    keep: dict = {k: [] for k in ks}
    for _ in range(boot):
        pick = [per_game[rng.randrange(n)] for _ in range(n)]
        for k in ks:
            num = sum(r["chosen"].get(k, 0) for r in pick)
            den = sum(r["seen"].get(k, 0) for r in pick)
            if den:
                keep[k].append(num / den)
    out = {}
    for k, v in keep.items():
        v.sort()
        out[k] = ([v[int(0.025 * len(v))],
                   v[min(len(v) - 1, int(0.975 * len(v)))]]
                  if v else [float("nan")] * 2)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--games", type=int, default=200)
    a = ap.parse_args(argv)

    from fish4.registry4 import KRAKEN_V1, make_agent
    from fish4.dylan_v07 import DylanV07

    rules = RuleConfig(**RULES_D)
    t0 = time.time()
    n_hs = 54 // CARDS_PER_HALF_SUIT
    per: dict = {}
    n_asks = 0
    #: pairs where the partner held none of the half-suit and chose it anyway.
    #: The rules forbid it, so this must stay at zero or nothing is readable.
    impossible = 0
    impossible_examples: list = []

    for g in range(a.games):
        seed = SEED0 + g
        kv_even = (g % 2 == 0)
        agents, ours = [], []
        for p in range(NUM_PLAYERS):
            if (p % 2 == 0) == kv_even:
                agents.append(make_agent(KRAKEN_V1))
                ours.append(p)
            else:
                agents.append(DylanV07())
        st = GameState.deal(rules, seed=seed)
        for p, ag in enumerate(agents):
            ag.begin_game(p, rules, AGENT0 + seed * 13 + p)
        row = per.setdefault(g, {"game": g, "chosen": {}, "seen": {},
                                 "asks": 0})

        for _ in range(MAX_ACTIONS):
            if st.is_terminal:
                break
            actor = st.turn
            act = agents[actor].act(Observation.from_state(st, actor))
            # Every KRAKEN ask is a partner ask from the other KRAKEN seat's
            # point of view, and both seats run the same policy, so the table
            # does not depend on which of the two is watching -- there is no
            # watcher in this measurement at all, only the choice and the hand
            # that made it.
            if actor in ours and isinstance(act, Ask):
                hand = st.hands[actor]          # PRE-ask, before any transfer
                asked = half_suit_of(act.card)
                for h in range(n_hs):
                    if st.set_winner[h] is not None:
                        continue
                    k = _count(hand, h)
                    row["seen"][k] = row["seen"].get(k, 0) + 1
                    if h == asked:
                        row["chosen"][k] = row["chosen"].get(k, 0) + 1
                        if k == 0:
                            impossible += 1
                            if len(impossible_examples) < 10:
                                impossible_examples.append(
                                    {"game": g, "seat": actor,
                                     "half_suit": h, "card": act.card})
                row["asks"] += 1
                n_asks += 1
            st.apply(actor, act)
        if (g + 1) % 20 == 0 or g + 1 == a.games:
            print(f"  {g+1}/{a.games} games, {n_asks} partner asks, "
                  f"{(time.time()-t0)/60:.1f} min", flush=True)

    pg = [per[k] for k in sorted(per)]
    ks = sorted({k for r in pg for k in r["seen"]})
    seen = {k: sum(r["seen"].get(k, 0) for r in pg) for k in ks}
    chosen = {k: sum(r["chosen"].get(k, 0) for r in pg) for k in ks}
    rate = {k: (chosen[k] / seen[k]) if seen[k] else float("nan") for k in ks}
    cis = _boot_table(pg, ks)
    # the weight a reweighting would apply, normalised so k=1 is 1.0: the
    # posterior renormalises anyway, so only the SHAPE is meaningful and
    # anchoring it at the smallest count that can ever be chosen makes the
    # shape readable without implying a scale
    anchor = rate.get(1) or float("nan")
    weight = {k: (rate[k] / anchor if anchor else float("nan")) for k in ks}

    out = {"script": "scripts4/partner_choice_likelihood.py",
           "descriptive": True, "rules": RULES_D,
           "seed_deal": SEED0, "seed_agent": AGENT0,
           "n_games": a.games, "n_partner_asks": n_asks,
           "counts_seen": seen, "counts_chosen": chosen,
           "p_chosen_given_k": rate, "ci": cis,
           "weight_shape_anchored_at_k1": weight,
           "selftest_chose_a_half_suit_they_held_none_of": impossible,
           "selftest_examples": impossible_examples,
           "count_is": "PRE-ask, the hand the choice was made from",
           "per_game": pg,
           "note": ("a per-half-suit factor approximates a joint choice; the "
                    "factors are not independent across half-suits within a "
                    "decision. A likelihood is not a set")}

    print("\n" + "=" * 72)
    print(f"  SELF-TEST: chose a half-suit they held none of  {impossible}")
    if impossible:
        print("  *** MUST BE ZERO. Fish forbids asking in a half-suit you hold")
        print("  *** no card of, so this harness is misreading the hand or the")
        print("  *** half-suit and NO ROW BELOW MAY BE READ. First:")
        for e in impossible_examples[:3]:
            print(f"      {e}")
    print("=" * 72)
    print("  P(OUR PARTNER ASKS IN A HALF-SUIT | HOW MANY OF IT THEY HOLD)")
    print(f"  {a.games} games, {n_asks:,} partner asks")
    print("=" * 72)
    print(f"  {'held':>4}  {'pairs':>8}  {'chosen':>7}  {'P(chosen|k)':>11}"
          f"  {'95% CI':>18}  {'weight':>7}")
    for k in ks:
        lo, hi = cis[k]
        print(f"  {k:>4}  {seen[k]:>8,}  {chosen[k]:>7,}  {rate[k]:>11.4f}"
              f"  [{lo:.4f}, {hi:.4f}]  {weight[k]:>7.2f}")
    if not impossible:
        print("\n  P(chosen | k=0) is 0 by the rules and the table reproduces")
        print("  it, so the harness is reading the hand the choice was made")
        print("  from. The weight column is the shape a partner-side")
        print("  reweighting would apply, anchored at k=1.")
    print(f"\n  wrote {write(default_path('partner_choice_likelihood', SEED0), out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
