"""Which links of the assembly chain does a weight override actually move?

WHY A PANEL AND NOT A DUEL. P52 lost and it took a second instrument, written
afterwards, to discover that its term had never moved the quantity it was aimed
at. A duel reports the margin and nothing upstream of it. This measures every
link of the chain `assembly_ledger` and `ask_allocation` established, for any
set of weight overrides, paired within deal against the champion:

    1. the ALLOCATION   P(ask in a half-suit | the asker holds one of it)
    2. the CLIMB        upward transitions per ply spent holding 1
    3. the ASSEMBLY     half-suits where our team ever held all six
    4. the DECLARATION  D_us, and W_us the ones it got wrong
    5. the MARGIN       sets

The chain says 1 drives 2 drives 3 drives 4 drives 5. An arm that moves 1 and
not 3 has a broken link and the reason is worth more than the margin. An arm
that moves 5 without moving 1 is doing something other than what it was aimed
at, whichever direction the margin went.

Reference values, from the 400-game measurements this is built to follow:

    allocation at holding 1   ours 0.11258   theirs 0.19717
    climb rate from 1         ours 0.02930   theirs 0.04493
    peak 6 a game             ours 4.098     theirs 4.860
    D_us a game               ours 4.100     theirs 4.832   bar needs +0.541

Ground truth is used as a LABEL ONLY, never acted on and never shown.

Descriptive. No arm, no duel, no ship claim.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import (CARDS_PER_HALF_SUIT, NUM_PLAYERS,          # noqa: E402
                        half_suit_mask, half_suit_of, team_of)
from fish.engine import (NULL_TEAM, Ask, ClaimEvent,               # noqa: E402
                         GameState)
from fish.observation import Observation                            # noqa: E402
from fish.rules import RuleConfig                                   # noqa: E402
from scripts4.resultfile import default_path, write                # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 16_700_000
AGENT0 = 167_000
MAX_ACTIONS = 600
BOOT = 2000
BOOT_SEED = 20_260_923

THEIRS = {"alloc1": 0.19717, "climb1": 0.04493, "peak6": 4.860,
          "d_us": 4.832}
NEEDED_D_US = 0.5412


def _count(mask: int, hs: int) -> int:
    return bin(mask & half_suit_mask(hs)).count("1")


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


def _boot_mean(per: list[dict], key: str,
               boot: int = BOOT, seed: int = BOOT_SEED) -> list[float]:
    rng = random.Random(seed)
    n = len(per)
    out = []
    for _ in range(boot):
        pick = [per[rng.randrange(n)] for _ in range(n)]
        out.append(sum(r[key] for r in pick) / n)
    out.sort()
    return [out[int(0.025 * len(out))],
            out[min(len(out) - 1, int(0.975 * len(out)))]]


def play(spec, deal_seed: int, kv_even: bool, rules, agent0: int) -> dict:
    """One deal, with every link of the chain recorded as it happens."""
    from fish4.registry4 import make_agent
    from fish4.dylan_v07 import DylanV07
    agents = [make_agent(spec) if (p % 2 == 0) == kv_even else DylanV07()
              for p in range(NUM_PLAYERS)]
    our_team = 0 if kv_even else 1
    ours = {p for p in range(NUM_PLAYERS) if team_of(p) == our_team}
    st = GameState.deal(rules, seed=deal_seed)
    for p, ag in enumerate(agents):
        ag.begin_game(p, rules, agent0 + deal_seed * 13 + p)

    n_hs = 54 // CARDS_PER_HALF_SUIT
    seen1 = chosen1 = 0                 # link 1
    plies1 = up1 = 0                    # link 2
    peak = [0] * n_hs                   # link 3
    last = [0] * n_hs
    for hs in range(n_hs):
        peak[hs] = last[hs] = _team_count(st.hands, hs, our_team)

    for _ in range(MAX_ACTIONS):
        if st.is_terminal:
            break
        actor = st.turn
        act = agents[actor].act(Observation.from_state(st, actor))
        if actor in ours and isinstance(act, Ask):
            hand = st.hands[actor]
            asked = half_suit_of(act.card)
            for h in range(n_hs):
                if st.set_winner[h] is not None:
                    continue
                if _count(hand, h) == 1:
                    seen1 += 1
                    if h == asked:
                        chosen1 += 1
        st.apply(actor, act)
        for hs in range(n_hs):
            if st.set_winner[hs] is not None:
                continue
            c = _team_count(st.hands, hs, our_team)
            if last[hs] == 1:
                plies1 += 1
                if c > 1:
                    up1 += 1
            last[hs] = c
            if c > peak[hs]:
                peak[hs] = c

    d_us = w_us = 0
    for ev in st.history:
        if isinstance(ev, ClaimEvent) and team_of(ev.claimer) == our_team:
            d_us += 1
            if ev.winner != our_team:
                w_us += 1
    mine = sum(1 for h in st.set_winner if h == our_team)
    return {"seen1": seen1, "chosen1": chosen1,
            "plies1": plies1, "up1": up1,
            "peak6": sum(1 for p in peak if p == 6),
            "d_us": d_us, "w_us": w_us, "margin": 2 * mine - 9}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--deals", type=int, default=150)
    ap.add_argument("--arms", required=True,
                    help='JSON: {"name": {"w_suit": 0.0}, ...}. The champion '
                         'is always included as the baseline.')
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    arms = json.loads(a.arms)

    from fish4.registry4 import KRAKEN_V1

    rules = RuleConfig(**RULES_D)
    t0 = time.time()
    names = ["champion"] + list(arms)
    specs = {"champion": KRAKEN_V1}
    for nm, kw in arms.items():
        specs[nm] = ("fishbot4", dict(KRAKEN_V1[1], **kw))
    per: dict = {nm: [] for nm in names}

    for i in range(a.deals):
        for kv_even in (True, False):
            for nm in names:
                per[nm].append(play(specs[nm], SEED0 + i, kv_even,
                                    rules, AGENT0))
        if (i + 1) % 25 == 0 or i + 1 == a.deals:
            print(f"  {i+1}/{a.deals} deals, {(time.time()-t0)/60:.1f} min",
                  flush=True)

    base = per["champion"]
    out = {"script": "scripts4/chain_mechanism.py", "descriptive": True,
           "rules": RULES_D, "seed_deal": SEED0, "seed_agent": AGENT0,
           "n_deals": a.deals, "arms": arms, "theirs": THEIRS,
           "needed_d_us": NEEDED_D_US, "links": {}}
    for nm in names:
        rows = per[nm]
        n = len(rows)
        paired = [{"d_us": r["d_us"] - b["d_us"],
                   "peak6": r["peak6"] - b["peak6"],
                   "margin": r["margin"] - b["margin"]}
                  for r, b in zip(rows, base)]
        out["links"][nm] = {
            "alloc1": sum(r["chosen1"] for r in rows)
            / max(1, sum(r["seen1"] for r in rows)),
            "alloc1_ci": _boot(rows, "chosen1", "seen1"),
            "climb1": sum(r["up1"] for r in rows)
            / max(1, sum(r["plies1"] for r in rows)),
            "climb1_ci": _boot(rows, "up1", "plies1"),
            "peak6": sum(r["peak6"] for r in rows) / n,
            "peak6_vs": sum(p["peak6"] for p in paired) / n,
            "peak6_vs_ci": _boot_mean(paired, "peak6"),
            "d_us": sum(r["d_us"] for r in rows) / n,
            "d_us_vs": sum(p["d_us"] for p in paired) / n,
            "d_us_vs_ci": _boot_mean(paired, "d_us"),
            "w_us": sum(r["w_us"] for r in rows) / n,
            "margin": sum(r["margin"] for r in rows) / n,
            "margin_vs": sum(p["margin"] for p in paired) / n,
            "margin_vs_ci": _boot_mean(paired, "margin")}

    print("\n" + "=" * 78)
    print("  WHICH LINKS OF THE CHAIN DOES THE OVERRIDE MOVE?")
    print(f"  {a.deals} deals x 2 parities, paired within deal. SESTINA's own "
          f"values in the last row.")
    print("=" * 78)
    print(f"  {'arm':<14}{'alloc@1':>9}{'climb@1':>9}{'peak6':>8}"
          f"{'vs champ':>10}{'D_us':>7}{'vs champ':>10}{'W_us':>7}"
          f"{'margin':>8}")
    for nm in names:
        r = out["links"][nm]
        print(f"  {nm:<14}{r['alloc1']:>9.5f}{r['climb1']:>9.5f}"
              f"{r['peak6']:>8.3f}{r['peak6_vs']:>+10.3f}{r['d_us']:>7.3f}"
              f"{r['d_us_vs']:>+10.3f}{r['w_us']:>7.3f}{r['margin']:>+8.3f}")
    t = THEIRS
    print(f"  {'SESTINA':<14}{t['alloc1']:>9.5f}{t['climb1']:>9.5f}"
          f"{t['peak6']:>8.3f}{'':>10}{t['d_us']:>7.3f}")
    print(f"\n  The bar needs D_us up by {NEEDED_D_US:+.3f}, which is "
          f"{NEEDED_D_US / 0.9732:+.3f} more peak-6s.")
    print("  An arm that moves link 1 and not link 3 has a broken chain, and")
    print("  that is worth more than its margin.")
    dest = a.out or default_path("chain_mechanism", SEED0)
    print(f"\n  wrote {write(Path(dest), out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
