"""Premise C, tested against opponents that are trying to win.

``scripts4/closed_form_proof.py`` establishes V = 2f - m by three premises, and
premise C is the constructive one: *the team on move takes every half-suit it
has a foothold in, without ever surrendering the turn.* It is checked there by
playing a greedy strategy out against ITSELF, which proves the strategy works
but leaves an obvious objection -- both sides were the same simple rule.

The premise is stronger than that. Look at what it needs: the mover drains
each half-suit with asks that cannot miss and never gives up the turn, so the
opponents never act at all until the mover's team is cardless. Their policy
therefore cannot matter. The premise should hold against ANY opponent, and it
needs only the MOVER's team to know the deal -- not both sides.

That experiment already exists. ``scripts4/inference_ceiling.py`` played a
whole team of ``OracleBot`` (which sees the true deal) against the champion,
and its per-deal differentials are 18, 18, 18, 18, 18, 18, 18, 16, 16, 15 --
suspiciously quantised for a game whose honest differentials have sd 3.5.

THE PREDICTION, IN ITS SHARP FORM
---------------------------------
For every game in which an ORACLE seat moves first:

    the oracle team's realised set count == the number of half-suits it has a
    foothold in at the deal.

Not approximately, and not on average: exactly, every game. If a single game
comes in below, premise C is false as stated and the closed-form proof needs
the qualification it currently does not have.

Where a CHAMPION moves first the prediction is only an upper bound -- the
champion team can claim a half-suit before it loses the turn -- so those games
are reported separately and are not evidence either way.

    py scripts4/oracle_foothold_check.py [n_deals]
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, deck_size, half_suit_mask, team_of
from fish.engine import GameState
from fish.rules import RuleConfig
from fish4.match import play_capped
from fish4.oracle import OracleBot, initial_owners
from fish4.registry4 import make_agent

CHAMPION = ("fishbot4", {"opponent_gamma": 0.35})


def footholds_at_deal(hands, team) -> int:
    n = 0
    for hs in range(9):
        mask = half_suit_mask(hs)
        if any(hands[p] & mask for p in range(NUM_PLAYERS)
               if team_of(p) == team):
            n += 1
    return n


def main(n_deals: int = 40) -> int:
    rules_dict = RuleConfig().to_dict()
    rows = []
    for i in range(n_deals):
        rng = random.Random(63_000_000 + i)
        base = RuleConfig.from_dict(rules_dict)
        deck = list(range(deck_size(base.variant)))
        rng.shuffle(deck)
        owners = initial_owners(deck, base.variant)
        start = i % NUM_PLAYERS
        rules = RuleConfig(**{**rules_dict, "starting_player": start})
        for swap in (0, 1):
            agents = []
            for seat in range(NUM_PLAYERS):
                on_x = (seat % 2 == 0) if swap == 0 else (seat % 2 == 1)
                a = OracleBot(opponent_gamma=0.35) if on_x \
                    else make_agent(CHAMPION)
                if isinstance(a, OracleBot):
                    a.see_deal(owners)
                agents.append(a)
            oracle_team = 0 if swap == 0 else 1
            deal = GameState.deal(rules, deck_order=deck)
            f = footholds_at_deal(deal.hands, oracle_team)
            st, timed_out = play_capped(agents, rules, deck, 63_500_000 + i)
            a_, b_, nulls = st.scores()
            got = a_ if oracle_team == 0 else b_
            rows.append({
                "deal": i, "swap": swap,
                "oracle_moves_first": team_of(start) == oracle_team,
                "footholds": f, "oracle_sets": got, "nulls": nulls,
                "timed_out": bool(timed_out)})
        print(f"  {i+1}/{n_deals} deals", flush=True)

    first = [r for r in rows if r["oracle_moves_first"]]
    other = [r for r in rows if not r["oracle_moves_first"]]
    exact = [r for r in first if r["oracle_sets"] == r["footholds"]]
    under = [r for r in first if r["oracle_sets"] < r["footholds"]]
    over = [r for r in first if r["oracle_sets"] > r["footholds"]]

    print(f"\n{len(rows)} games from {n_deals} deals\n")
    print(f"ORACLE MOVES FIRST  {len(first)} games")
    print(f"  sets == footholds   {len(exact)}/{len(first)}")
    print(f"  sets <  footholds   {len(under)}   <- refutes premise C")
    print(f"  sets >  footholds   {len(over)}   <- refutes premise A")
    for r in under[:5]:
        print(f"      deal {r['deal']} swap {r['swap']}: "
              f"f={r['footholds']} got {r['oracle_sets']}")
    for r in over[:5]:
        print(f"      deal {r['deal']} swap {r['swap']}: "
              f"f={r['footholds']} got {r['oracle_sets']}")

    if other:
        le = sum(1 for r in other if r["oracle_sets"] <= r["footholds"])
        print(f"\nCHAMPION MOVES FIRST  {len(other)} games "
              f"(upper bound only)")
        print(f"  sets <= footholds   {le}/{len(other)}")
        print(f"  mean sets {sum(r['oracle_sets'] for r in other)/len(other):.2f}"
              f" against mean footholds "
              f"{sum(r['footholds'] for r in other)/len(other):.2f}")

    fs = [r["footholds"] for r in rows]
    print(f"\nfootholds at the deal: mean {sum(fs)/len(fs):.3f} of 9 "
          f"(closed form predicts 9 - 9*C(27,6)/C(54,6) = 8.897)")

    ok = not under and not over and len(first) > 0
    print()
    if ok:
        print(f"Premise C holds in {len(exact)}/{len(first)} real games against "
              f"champions that are\ntrying to win. The team on move with the "
              f"deal takes exactly its footholds and\nnothing else -- the "
              f"opponents never get to act, so their policy cannot matter.")
        print("\nThis also explains the inference ceiling's +17.3: it is not a "
              "measurement of\nhow much card-reading is worth so much as the "
              "closed form being played out.")
    else:
        print("Premise C does NOT hold as stated. The proof in "
              "scripts4/closed_form_proof.py\nneeds the qualification these "
              "games imply, and the failures above are the\nthing to read.")

    out = ROOT / "results" / "oracle_foothold_check.json"
    out.write_text(json.dumps({
        "n_deals": n_deals, "n_games": len(rows),
        "oracle_first": len(first), "exact": len(exact),
        "under": len(under), "over": len(over),
        "mean_footholds": sum(fs) / len(fs),
        "closed_form_mean_footholds": 8.8968,
        "premise_c_holds": ok, "rows": rows}, indent=1))
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0 if ok else 1


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 40))
