"""P45 futility screen: does the free-message gate reach the code path?

Registered in `prereg/kraken_v12_free_message.md`, which fixes the arm, the
bar and the seeds. This file only measures the firing rate; it plays no duel
and reports no margin.

TWO NUMBERS, both fixed in advance by the registration:

  * **carry gain over the champion on the SAME deals** -- must be at least
    +2 percentage points. NOT "share of decisions changed": a free-message gate
    swaps only when the agreed card TIES the objective's pick, and on a tie the
    champion picks uniformly from the tied pool, so the gate changes no score
    and a replay comparison counts RNG tie-breaking as firing. A probe on 10
    games reported 16.45% by that route against a true carry gain of 0.7
    points. See the registration's futility section for the correction.

  * **realised carry rate** -- the share of our asks naming the agreed card.
    `prereg/convention_duel.md`'s corrected table puts the no-encoder baseline
    at **35.3%** and this gate at **40.1%**. Below the baseline the encoder is
    not reaching the code path and the arm is void; more than 10 points off
    40.1% and the duel population is not the one that table describes.

The champion is measured on the SAME deals, not assumed, so the baseline is
this block's rather than a number carried across from another one.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import half_suit_of                        # noqa: E402
from fish.engine import GameState                          # noqa: E402
from fish.observation import Observation                   # noqa: E402
from fish.rules import RuleConfig                          # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 10_150_000
AGENT0 = 101_500
MAX_ACTIONS = 600

#: Fixed by the registration. The label carries no "." for the same reason
#: P44's did: the paper's pin manifest splits dotted paths.
ARM = {"convention_q": 0.5, "convention_book": "locate",
       "convention_max_cost": 1e-9}

#: Carry gain over the champion, in percentage points. A little under half the
#: +4.8 the corrected table in `prereg/convention_duel.md` advertises.
CARRY_GAIN_BAR = 0.02
#: `prereg/convention_duel.md`'s corrected carry table.
NO_ENCODER_CARRY = 0.353
EXPECTED_CARRY = 0.401


def _agreed_card(ag, obs, asks):
    """The card the locating book would have us name, or None.

    Lifted from the encoder in `fish4/agent4.py` rather than re-derived: a
    screen that re-implements the book measures a different book, and this
    project has lost two results to a script that re-listed what a module
    already owned.
    """
    from fish.cards import half_suit_of
    from fish4.convention import (half_suit_cards, legal_cards,
                                  locate_payload)
    if not asks:
        return None
    hs = half_suit_of(asks[0].card)
    best_u, g_hs = -1, 0
    for h in range(len(obs.set_winner)):
        u = sum(1 for c in half_suit_cards(h)
                if ag.bel.public_loc[c] is None)
        if u > best_u:
            best_u, g_hs = u, h
    cards = legal_cards(obs.hand, hs)
    if not cards:
        return None
    tg = [c for c in half_suit_cards(g_hs)
          if ag.bel.public_loc[c] is None][:len(cards)]
    return cards[locate_payload(obs.hand, tg) % len(cards)]


def _one(args) -> dict:
    deal_seed, kv_even = args
    from fish4.registry4 import KRAKEN_V1, make_agent

    rules = RuleConfig(**RULES_D)
    ours = {p for p in range(6) if (p % 2 == 0) == kv_even}
    out = {"games": 1}
    for tag, extra in (("arm", ARM), ("champ", {})):
        params = dict(KRAKEN_V1[1], **extra)
        agents = [make_agent(("fishbot4", params)) if p in ours
                  else make_agent(("dylan_v07", {})) for p in range(6)]
        st = GameState.deal(rules, seed=deal_seed)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
        asks = carry = 0
        for _ in range(MAX_ACTIONS):
            if st.is_terminal:
                break
            mover = st.turn
            obs = Observation.from_state(st, mover)
            act = agents[mover].act(obs)
            if mover in ours and hasattr(act, "target") \
                    and hasattr(act, "card"):
                asks += 1
                ag = agents[mover]
                legal = obs.legal_asks()
                same_hs = [a for a in legal
                           if half_suit_of(a.card) == half_suit_of(act.card)]
                agreed = _agreed_card(ag, obs, same_hs)
                if agreed is not None and agreed == act.card:
                    carry += 1
            st.apply(mover, act)
        out[f"{tag}_asks"] = asks
        out[f"{tag}_carry"] = carry
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--deals", type=int, default=200)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--out", default="results/p45_futility.json")
    a = ap.parse_args(argv)

    todo = [(SEED0 + i, ke) for i in range(a.deals) for ke in (True, False)]
    print(f"P45 futility: {len(todo)} games, seed base {SEED0:,}", flush=True)
    t0 = time.time()
    tot = {"games": 0, "arm_asks": 0, "arm_carry": 0,
           "champ_asks": 0, "champ_carry": 0}
    with Pool(a.jobs) as pool:
        for i, r in enumerate(pool.imap_unordered(_one, todo, chunksize=1)):
            for k in tot:
                tot[k] += r.get(k, 0)
            if (i + 1) % 50 == 0:
                print(f"  {i + 1}/{len(todo)}, "
                      f"{(time.time() - t0) / 60:.1f} min", flush=True)

    arm_carry = tot["arm_carry"] / max(1, tot["arm_asks"])
    champ_carry = tot["champ_carry"] / max(1, tot["champ_asks"])
    gain = arm_carry - champ_carry
    res = {
        "prereg": "prereg/kraken_v12_free_message.md",
        "seed0": SEED0, "arm": ARM, "totals": tot,
        "arm_carry_rate": arm_carry,
        "champion_carry_rate": champ_carry,
        "carry_gain": gain,
        "carry_gain_bar": CARRY_GAIN_BAR,
        "passes_carry_gain_bar": gain >= CARRY_GAIN_BAR,
        "carry_above_baseline": arm_carry > champ_carry,
        "carry_within_10pts_of_expected":
            abs(arm_carry - EXPECTED_CARRY) <= 0.10,
        "seconds": round(time.time() - t0, 1),
    }
    Path(ROOT / a.out).write_text(json.dumps(res, indent=1) + "\n")
    print(f"\n  carry gain over champion  {gain:+.2%}   "
          f"bar +{CARRY_GAIN_BAR:.0%}   "
          f"{'pass' if res['passes_carry_gain_bar'] else 'STOP'}")
    print(f"  carry, arm             {arm_carry:.1%}   "
          f"(this block's champion {champ_carry:.1%}, "
          f"document's 35.3% / expected 40.1%)")
    print(f"  carry above baseline   "
          f"{'yes' if res['carry_above_baseline'] else 'NO -- arm is VOID'}")
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
