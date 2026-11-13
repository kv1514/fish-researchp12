"""Where does each engine spend its asks, by how much of the half-suit it holds?

THE MEASUREMENT THIS FOLLOWS. `assembly_ledger` decomposed the whole deficit:
half-suits won are 4.145 against 4.855, and essentially all of it is REACHING
six rather than converting six -- peak-6 per game 4.098 against 4.860, with both
sides banking a completed half-suit at ~97.4%. The excess shows up as half-suits
stalled at 3, 4 and 5 (+0.690 a game).

And the climb rates say where the stall is, which was not where this line of
work expected:

    holding      our climb rate   their climb rate      gap
       1            0.02930          0.04493         -0.01563
       2            0.04084          0.05568         -0.01484
       3            0.04577          0.05075         -0.00498
       4            0.05775          0.04747         +0.01028
       5            0.06763          0.05581         +0.01182

We are FASTER at finishing and SLOWER at starting, and we spend 38% more plies
holding only one or two of a half-suit. They make 9.5% more upward transitions
overall.

THE HYPOTHESIS. Our ask objective is depth-proportional --
`P(ask in H) ~ depth_H ** gamma`, with `suit` live at 0.06 and `scarce`, a team
share of the half-suit, at 0.2 -- so it prefers half-suits we already hold a lot
of. If that preference is steeper than theirs, we neglect the half-suits we hold
one or two of, they stay low, and the opponents build them instead. That would
produce exactly the climb profile above.

This script tests it directly: for every ask by EITHER engine, how many cards of
that half-suit did the asker hold when it chose, against how many it could have
chosen from. The classifier is the asker's own hand -- the same objective rule
for both engines, no posterior, no model of anyone.

THE SELF-TEST is the rule: Fish forbids asking in a half-suit you hold no card
of, so `P(chosen | k = 0)` must be exactly zero for both engines. A single
counter-example means the harness is misreading the hand it attributes the
choice to.

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
SEED0 = 16_300_000
AGENT0 = 163_000
MAX_ACTIONS = 600
BOOT = 2000
BOOT_SEED = 20_260_923


def _count(mask: int, hs: int) -> int:
    return bin(mask & half_suit_mask(hs)).count("1")


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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--games", type=int, default=400)
    ap.add_argument("--w-suit", type=float, default=None,
                    help="override our w_suit, to check a candidate knob "
                         "actually flattens the curve BEFORE it is dueled")
    ap.add_argument("--w-scarce", type=float, default=None)
    ap.add_argument("--by", choices=("own", "team"), default="own",
                    help="classify a half-suit by the ASKER's own count or by "
                         "the asker's TEAM's count. The two are different "
                         "questions: `suit` weights own depth, but assembly is "
                         "a team quantity, so a half-suit the asker holds one "
                         "of may be one the TEAM holds five of. If the gap "
                         "survives the team conditioning it is a real "
                         "misallocation; if it vanishes, the own-count gap was "
                         "an artifact of which seat happened to hold what.")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    from fish4.registry4 import KRAKEN_V1, make_agent
    from fish4.dylan_v07 import DylanV07

    rules = RuleConfig(**RULES_D)
    t0 = time.time()
    n_hs = 54 // CARDS_PER_HALF_SUIT
    per: list[dict] = []
    impossible: list = []

    for g in range(a.games):
        seed = SEED0 + g
        kv_even = (g % 2 == 0)
        over = {}
        if a.w_suit is not None:
            over["w_suit"] = a.w_suit
        if a.w_scarce is not None:
            over["w_scarce"] = a.w_scarce
        spec = ("fishbot4", dict(KRAKEN_V1[1], **over)) if over else KRAKEN_V1
        agents = [make_agent(spec) if (p % 2 == 0) == kv_even
                  else DylanV07() for p in range(NUM_PLAYERS)]
        ours = {p for p in range(NUM_PLAYERS) if (p % 2 == 0) == kv_even}
        st = GameState.deal(rules, seed=seed)
        for p, ag in enumerate(agents):
            ag.begin_game(p, rules, AGENT0 + seed * 13 + p)

        row = {"game": g}
        for side in ("ours", "theirs"):
            for k in range(7):
                row[f"{side}_seen{k}"] = 0
                row[f"{side}_chosen{k}"] = 0
            row[f"{side}_asks"] = 0

        for _ in range(MAX_ACTIONS):
            if st.is_terminal:
                break
            actor = st.turn
            act = agents[actor].act(Observation.from_state(st, actor))
            if isinstance(act, Ask):
                side = "ours" if actor in ours else "theirs"
                hand = st.hands[actor]          # PRE-ask, the hand that chose
                mates = [p for p in range(NUM_PLAYERS)
                         if team_of(p) == team_of(actor)]
                asked = half_suit_of(act.card)
                row[f"{side}_asks"] += 1
                for h in range(n_hs):
                    if st.set_winner[h] is not None:
                        continue
                    if a.by == "team":
                        k = sum(_count(st.hands[p], h) for p in mates)
                    else:
                        k = _count(hand, h)
                    row[f"{side}_seen{k}"] += 1
                    if h == asked:
                        row[f"{side}_chosen{k}"] += 1
                        if k == 0 and a.by == "own" and len(impossible) < 10:
                            impossible.append({"game": g, "seat": actor,
                                               "half_suit": h, "side": side})
            st.apply(actor, act)
        per.append(row)
        if (g + 1) % 50 == 0 or g + 1 == a.games:
            print(f"  {g+1}/{a.games} games, {(time.time()-t0)/60:.1f} min",
                  flush=True)

    def tot(k):
        return sum(r.get(k, 0) for r in per)

    out = {"script": "scripts4/ask_allocation.py", "descriptive": True,
           "rules": RULES_D, "seed_deal": SEED0, "seed_agent": AGENT0,
           "n_games": a.games,
           "classifier": ("the asker's own PRE-ask count" if a.by == "own"
                          else "the asker's TEAM's PRE-ask count"),
           "by": a.by,
           "our_overrides": {k: v for k, v in (
               ("w_suit", a.w_suit), ("w_scarce", a.w_scarce)) if v is not None},
           "selftest_chose_a_half_suit_held_none_of": len(impossible),
           "selftest_examples": impossible,
           "by_holding": {}, "per_game": per,
           "ours_asks": tot("ours_asks"), "theirs_asks": tot("theirs_asks")}
    for k in range(7):
        o_s, o_c = tot(f"ours_seen{k}"), tot(f"ours_chosen{k}")
        t_s, t_c = tot(f"theirs_seen{k}"), tot(f"theirs_chosen{k}")
        orr = (o_c / o_s) if o_s else None
        trr = (t_c / t_s) if t_s else None
        out["by_holding"][k] = {
            "ours_seen": o_s, "ours_chosen": o_c, "ours_rate": orr,
            "ours_ci": _boot(per, f"ours_chosen{k}", f"ours_seen{k}")
            if o_s else None,
            "theirs_seen": t_s, "theirs_chosen": t_c, "theirs_rate": trr,
            "theirs_ci": _boot(per, f"theirs_chosen{k}", f"theirs_seen{k}")
            if t_s else None,
            "ratio": (orr / trr) if (orr and trr) else None,
            # the SHARE of each engine's asks that went to this holding, which
            # is the allocation itself rather than a per-opportunity rate
            "ours_share": o_c / tot("ours_asks") if tot("ours_asks") else None,
            "theirs_share": (t_c / tot("theirs_asks")
                             if tot("theirs_asks") else None)}

    print("\n" + "=" * 72)
    if a.by == "own":
        print(f"  SELF-TEST: asks in a half-suit the asker held none of: "
              f"{len(impossible)}")
    else:
        print("  SELF-TEST: not applicable under TEAM conditioning -- a seat")
        print("  may legally ask in a half-suit its PARTNER holds all of.")
    if impossible:
        print("  *** MUST BE ZERO -- the rules forbid it, so the harness is")
        print("  *** misreading the hand and NO RATE BELOW MAY BE READ.")
        for x in impossible[:3]:
            print(f"      {x}")
    print("=" * 72)
    print("  WHERE DOES EACH ENGINE SPEND ITS ASKS?")
    print(f"  {a.games} games, ours {out['ours_asks']:,} asks, "
          f"theirs {out['theirs_asks']:,}")
    print("=" * 72)
    print(f"  {'held':>5}  {'P(chosen|k) ours':>17}  {'theirs':>17}"
          f"  {'ratio':>6}   {'share ours':>11}{'share theirs':>13}")
    for k in range(7):
        b = out["by_holding"][k]
        if not b["ours_seen"] and not b["theirs_seen"]:
            continue
        orr = f"{b['ours_rate']:.5f}" if b["ours_rate"] is not None else "   --"
        trr = (f"{b['theirs_rate']:.5f}" if b["theirs_rate"] is not None
               else "   --")
        rat = f"{b['ratio']:.2f}" if b["ratio"] else "  --"
        print(f"  {k:>5}  {orr:>17}  {trr:>17}  {rat:>6}"
              f"   {b['ours_share']:>11.4f}{b['theirs_share']:>13.4f}")
    print("\n  A ratio above 1 means we ask there MORE readily than they do at")
    print("  the same holding. The shares say where each engine's asks")
    print("  actually went, which is the allocation the climb rates react to.")
    dest = a.out or default_path("ask_allocation", SEED0)
    print(f"\n  wrote {write(Path(dest), out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
