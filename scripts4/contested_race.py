"""In a contested half-suit, who wins the race to six, and is it choice or execution?

WHERE THIS SITS. `assembly_ledger` put the whole deficit in reaching six rather
than converting it (peak-6 a game 4.098 against 4.860, conversion 0.9732 against
0.9748), and `contest_ledger` put it in the CONTESTED band -- at a matched deal
we convert worse at 4-2, 3-3 and 2-4 and better at 6-0, 5-1 and 1-5. Three dose
sweeps over 19,200 duel games then established that the ask objective's
half-suit-level preferences are at a joint optimum, so the deficit cannot be
re-tuned away by choosing DIFFERENT half-suits.

Everything measured so far has been at the half-suit level. **Which card, and
which target, inside a half-suit has not been measured at all.**

A half-suit dealt 3-3 is a race: whoever assembles all six first takes it. This
splits that race into two factors that want different remedies:

    CHOICE      asks each team sends INTO that half-suit, per ply it is live
    EXECUTION   the hit rate of those asks, WITHIN that half-suit

If we send as many and hit less, the gap is target and card selection -- an
untouched dimension. If we send fewer, it is allocation again, and three sweeps
say allocation is already where it should be, which would make the contested
band a consequence rather than a cause.

The band is taken from the DEAL, before any play, so it is exogenous: nothing a
policy did can move which band a half-suit started in. Ground truth is used as a
LABEL ONLY -- it selects the band and is never shown to an agent.

History and hands only: no posterior is sampled, so no stale-belief exposure and
no sampling error of its own.

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
SEED0 = 18_300_000
AGENT0 = 183_000
MAX_ACTIONS = 600
BOOT = 2000
BOOT_SEED = 20_260_923
#: our team's count of the half-suit AT THE DEAL. 3 is the even race; 4 and 2 are
#: the shoulders. Together with 3 they are the band the deficit lives in.
BANDS = (2, 3, 4)


def _tc(hands, hs: int, team: int) -> int:
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
    ap.add_argument("--games", type=int, default=400)
    a = ap.parse_args(argv)

    from fish4.registry4 import KRAKEN_V1, make_agent
    from fish4.dylan_v07 import DylanV07

    rules = RuleConfig(**RULES_D)
    t0 = time.time()
    n_hs = 54 // CARDS_PER_HALF_SUIT
    per: list[dict] = []
    #: a half-suit whose band is outside 0..6 would mean the count is wrong
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

        # THE BAND IS FIXED AT THE DEAL and never revisited: it is exogenous,
        # so conditioning on it cannot be contaminated by what the policies did.
        band = [_tc(st.hands, h, our_team) for h in range(n_hs)]
        for b in band:
            if not 0 <= b <= 6:
                impossible += 1

        row = {"game": g}
        for b in BANDS:
            for side in ("ours", "theirs"):
                row[f"{side}_asks_b{b}"] = 0
                row[f"{side}_hits_b{b}"] = 0
                row[f"{side}_plies_b{b}"] = 0
            row[f"won_b{b}"] = 0
            row[f"n_b{b}"] = sum(1 for h in range(n_hs) if band[h] == b)

        for _ in range(MAX_ACTIONS):
            if st.is_terminal:
                break
            actor = st.turn
            act = agents[actor].act(Observation.from_state(st, actor))
            side = "ours" if actor in ours else "theirs"
            if isinstance(act, Ask):
                b = band[half_suit_of(act.card)]
                if b in BANDS:
                    row[f"{side}_asks_b{b}"] += 1
                    if st.hands[act.target] >> act.card & 1:
                        row[f"{side}_hits_b{b}"] += 1
            # plies each band's live half-suits are exposed to, so "asks sent"
            # can be a RATE and not a count of opportunities
            for h in range(n_hs):
                if st.set_winner[h] is None and band[h] in BANDS:
                    row[f"ours_plies_b{band[h]}"] += 1
                    row[f"theirs_plies_b{band[h]}"] += 1
            st.apply(actor, act)

        for h in range(n_hs):
            if band[h] in BANDS and st.set_winner[h] == our_team:
                row[f"won_b{band[h]}"] += 1
        per.append(row)
        if (g + 1) % 50 == 0 or g + 1 == a.games:
            print(f"  {g+1}/{a.games} games, {(time.time()-t0)/60:.1f} min",
                  flush=True)

    def tot(k):
        return sum(r.get(k, 0) for r in per)

    out = {"script": "scripts4/contested_race.py", "descriptive": True,
           "rules": RULES_D, "seed_deal": SEED0, "seed_agent": AGENT0,
           "n_games": a.games, "bands": list(BANDS),
           "band_is": "our team's count of the half-suit AT THE DEAL",
           "selftest_band_out_of_range": impossible, "by_band": {},
           "per_game": per}
    for b in BANDS:
        n = tot(f"n_b{b}")
        d = {"n_half_suits": n, "per_game": n / a.games,
             "we_won": tot(f"won_b{b}"),
             "win_rate": (tot(f"won_b{b}") / n) if n else None,
             "win_rate_ci": _boot(per, f"won_b{b}", f"n_b{b}") if n else None}
        for side in ("ours", "theirs"):
            asks, hits = tot(f"{side}_asks_b{b}"), tot(f"{side}_hits_b{b}")
            plies = tot(f"{side}_plies_b{b}")
            d[f"{side}_asks"] = asks
            d[f"{side}_asks_per_ply"] = (asks / plies) if plies else None
            d[f"{side}_asks_per_ply_ci"] = _boot(
                per, f"{side}_asks_b{b}", f"{side}_plies_b{b}") if plies else None
            d[f"{side}_hit_rate"] = (hits / asks) if asks else None
            d[f"{side}_hit_rate_ci"] = _boot(
                per, f"{side}_hits_b{b}", f"{side}_asks_b{b}") if asks else None
        out["by_band"][b] = d

    print("\n" + "=" * 78)
    print(f"  SELF-TEST: half-suits with a band outside 0..6: {impossible}")
    if impossible:
        print("  *** MUST BE ZERO. NOTHING BELOW MAY BE READ.")
    print("=" * 78)
    print("  THE RACE IN A CONTESTED HALF-SUIT: CHOICE, OR EXECUTION?")
    print(f"  {a.games} games. Band = our team's count AT THE DEAL, so it is")
    print("  exogenous and conditioning on it cannot be contaminated by play.")
    print("=" * 78)
    print(f"  {'band':>5}{'n/game':>8}{'we won':>8}   "
          f"{'CHOICE: asks per ply':>24}   {'EXECUTION: hit rate':>22}")
    print(f"  {'':>5}{'':>8}{'':>8}   {'ours':>11}{'theirs':>12}   "
          f"{'ours':>10}{'theirs':>11}")
    for b in BANDS:
        d = out["by_band"][b]
        print(f"  {b:>5}{d['per_game']:>8.2f}{d['win_rate']:>8.4f}   "
              f"{d['ours_asks_per_ply']:>11.5f}{d['theirs_asks_per_ply']:>12.5f}"
              f"   {d['ours_hit_rate']:>10.4f}{d['theirs_hit_rate']:>11.4f}")
    print("\n  Same asks and a lower hit rate means the gap is target and card")
    print("  selection, which nothing in this project has touched. Fewer asks")
    print("  means allocation, and three sweeps say allocation is already right")
    print("  -- which would make the contested band a consequence, not a cause.")
    print(f"\n  wrote {write(default_path('contested_race', SEED0), out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
