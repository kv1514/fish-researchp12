"""What is one turn worth, in sets?

This project has one primitive for denominating results: the information
exchange rate of ``results/inference_curve.json``, about **0.45 sets per hidden
card revealed**. It has no second one, and the missing one is tempo. Half the
engine's objective prices turns -- ``turn_risk``, depth, the retained turn a hit
buys -- against features whose weights were fitted, never against a measured
scale.

The doomed-ask diagnostic made that gap concrete. The champion gives the turn
away for certain on 1.5% of decisions when an ask with median success
probability 0.385 was available, and whether that matters depends entirely on
what a turn costs.

THE MEASUREMENT
---------------
Paired on the deal. Both arms play the identical deck with the identical agent
seeds. At one pre-chosen decision of one pre-chosen seat, the treatment arm
substitutes an ask that PROVABLY cannot land -- a card of a half-suit the seat
holds, aimed at an opponent known not to hold it -- which hands the turn to that
opponent. Everything before is identical and everything after is honest play by
both arms. The difference in the donating team's final differential is the price
of exactly one donated turn.

    price = (control differential) - (treatment differential)

WHY THIS IS NOT THE SAME AS THE avoid_doomed_asks DUEL
------------------------------------------------------
That duel changes a policy at every firing, so its result is the sum of a
tempo effect and whatever the doomed asks were signalling. This intervenes once
per deal, at a decision chosen without reference to what the agent wanted to do,
so it isolates the tempo term alone. The two are meant to be read together: if a
turn is worth $x$ and the champion donates 1.53 turns per game of which 0.385
were retainable, the duel's effect should be near $0.59x$ per game. That is a
quantitative prediction linking two independent measurements, and it is the
point of running this.

THE CONTROL
-----------
``--control`` substitutes the agent's OWN action instead of a doomed one, on the
same deals with the same seeds. Every pair must then differ by exactly zero. If
it does not, the arms are not seeing the same game and no measured price means
anything.

    py scripts4/turn_price.py --control-only
    py scripts4/turn_price.py --pairs 200
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import (NUM_PLAYERS, deck_size, half_suit_mask, half_suit_of,
                        mask_to_cards, team_of)
from fish.engine import Ask, GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.registry4 import make_agent

CHAMPION = ("fishbot4", {"opponent_gamma": 0.35})


def doomed_ask(st, me):
    """A legal ask by ``me`` that cannot possibly land, or None.

    Legality needs a card of the half-suit in hand and a target with cards; the
    ask is doomed when the target demonstrably does not hold the card. Chosen
    from the TRUE state rather than from a belief, because the point is to
    donate the turn with certainty, not to model a mistake.
    """
    hand = st.hands[me]
    opps = [q for q in range(NUM_PLAYERS)
            if team_of(q) != team_of(me) and st.hands[q]]
    if not opps:
        return None
    for hs in range(len(st.set_winner)):
        if st.set_winner[hs] is not None:
            continue
        mask = half_suit_mask(hs)
        if not hand & mask:
            continue
        for card in mask_to_cards(mask & ~hand):
            for o in opps:
                if not (st.hands[o] >> card) & 1:
                    return Ask(o, card)
    return None


def one_game(deck, rules, agent_seed, target_seat, at_decision, donate):
    """Play one game; at the ``at_decision``-th decision of ``target_seat``,
    substitute a doomed ask if ``donate``. Returns team-0's differential and
    whether the substitution actually happened."""
    agents = [make_agent(CHAMPION) for _ in range(NUM_PLAYERS)]
    st = GameState.deal(rules, deck_order=deck)
    ar = random.Random(agent_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, ar.getrandbits(64))
    seen = 0
    fired = False
    for _ in range(4000):
        if st.is_terminal:
            break
        p = st.turn
        obs = Observation.from_state(st, p)
        try:
            act = agents[p].act(obs)
        except Exception:
            break
        if p == target_seat:
            if seen == at_decision and donate:
                alt = doomed_ask(st, p)
                if alt is not None:
                    act = alt
                    fired = True
            seen += 1
        try:
            st.apply(p, act)
        except Exception:
            break
    a_, b_, _ = st.scores()
    return float(a_ - b_), fired


def run(n_pairs, base_seed, agent_seed_base, control=False, progress=False,
        at_lo=0, at_hi=5):
    """Donate at the seat's ``at_lo``..``at_hi``-th decision.

    WHY THIS IS A PARAMETER. The first version fixed the donation at decisions
    0-4 and used the resulting price to predict what avoid_doomed_asks should
    score. The two came out disjoint -- [+0.109, +0.531] predicted against
    [-0.024, +0.059] measured -- and one of the three explanations is that the
    bridge assumed a turn is worth the same everywhere. The doomed-ask branch
    fires deep in stuck half-suits, not at move five. If tempo value decays
    through a game, the bridge was wrong before either arm was at fault, and
    that has to be ruled out before the residual can be called signalling.
    """
    rules_dict = RuleConfig().to_dict()
    seed_rng = random.Random(agent_seed_base)
    prices, fired_flags = [], []
    for i in range(n_pairs):
        aseed = seed_rng.getrandbits(64)
        rng = random.Random(base_seed + i)
        base = RuleConfig.from_dict(rules_dict)
        deck = list(range(deck_size(base.variant)))
        rng.shuffle(deck)
        rules = RuleConfig(**{**rules_dict,
                              "starting_player": i % NUM_PLAYERS})
        seat = i % NUM_PLAYERS
        at = at_lo + i % max(1, at_hi - at_lo)
        ref, _ = one_game(deck, rules, aseed, seat, at, donate=False)
        alt, fired = one_game(deck, rules, aseed, seat, at,
                              donate=not control)
        # Price in the DONATING team's frame.
        sign = 1.0 if team_of(seat) == 0 else -1.0
        prices.append(sign * (ref - alt))
        fired_flags.append(bool(fired))
        if progress and (i + 1) % 50 == 0:
            print(f"  ... {i+1}/{n_pairs}", flush=True)
    return prices, fired_flags


def summarise(x):
    n = len(x)
    m = sum(x) / n
    sd = math.sqrt(sum((v - m) ** 2 for v in x) / (n - 1)) if n > 1 else 0.0
    se = sd / math.sqrt(n) if n else 0.0
    return {"n": n, "mean": m, "sd": sd, "se": se,
            "ci95": [m - 1.96 * se, m + 1.96 * se]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", type=int, default=300)
    ap.add_argument("--base-seed", type=int, default=66_000_000)
    ap.add_argument("--agent-seed", type=int, default=66001)
    ap.add_argument("--at-lo", type=int, default=0,
                    help="earliest decision index of the target seat")
    ap.add_argument("--at-hi", type=int, default=5)
    ap.add_argument("--tag", default="",
                    help="suffix for the results filename")
    ap.add_argument("--control-pairs", type=int, default=20)
    ap.add_argument("--control-only", action="store_true")
    ap.add_argument("--skip-control", action="store_true")
    a = ap.parse_args(argv)

    if not a.skip_control:
        c, _ = run(a.control_pairs, 67_000_000, 67001, control=True)
        bad = [i for i, v in enumerate(c) if v != 0.0]
        print(f"control: the agent's own action substituted, "
              f"{a.control_pairs} deals")
        if bad:
            print(f"  FAIL {len(bad)} deals differ; the arms are not seeing "
                  f"the same game: {[(i, c[i]) for i in bad[:5]]}")
            return 1
        print("  ok   every deal differs by exactly 0.000\n")
        if a.control_only:
            return 0

    print(f"donating one turn at decision {a.at_lo}-{a.at_hi-1} of the "
          f"target seat, {a.pairs} paired deals\n")
    prices, flags = run(a.pairs, a.base_seed, a.agent_seed, progress=True,
                        at_lo=a.at_lo, at_hi=a.at_hi)
    nfired = sum(flags)
    fired_prices = [x for x, f in zip(prices, flags) if f]
    s_all = summarise(prices)
    s = summarise(fired_prices) if fired_prices else s_all
    print(f"\nsubstitution fired on {nfired}/{a.pairs} deals; on the rest no "
          f"doomed ask\nwas available, both arms played identically, and the "
          f"pair contributes exactly 0.")
    print(f"\nPRICE OF ONE TURN {s['mean']:+.3f} sets, "
          f"95% CI [{s['ci95'][0]:+.3f}, {s['ci95'][1]:+.3f}]  "
          f"(sd {s['sd']:.2f}, n {s['n']})")
    print(f"  over ALL pairs including the untreated "
          f"{s_all['mean']:+.3f} [{s_all['ci95'][0]:+.3f}, "
          f"{s_all['ci95'][1]:+.3f}]")
    print("  The first is the price of a donation; the second dilutes it with "
          "deals where\n  nothing was donated. Restricting to fired pairs "
          "conditions on the treatment\n  being AVAILABLE, which is fixed "
          "before either arm plays and is identical in\n  both, so it does "
          "not condition on an outcome.")

    RATE = 0.45
    print(f"\nAt the exchange rate of {RATE} sets per hidden card, one turn is "
          f"worth {s['mean']/RATE:+.2f} cards.")
    print(f"The champion donates 1.53 turns per game on the doomed-ask branch, "
          f"of which\n0.385 were retainable, so avoid_doomed_asks should be "
          f"worth about {0.59*s['mean']:+.3f} sets\nper game "
          f"({2*0.59*s['mean']:+.3f} per deal-pair) if tempo is all it "
          f"changes.")

    out = ROOT / "results" / f"turn_price{a.tag}.json"
    out.write_text(json.dumps({"summary": s, "summary_all_pairs": s_all,
                               "prices": prices, "fired": flags,
                               "n_fired": nfired, "base_seed": a.base_seed,
                               "at_lo": a.at_lo, "at_hi": a.at_hi,
                               "rate_sets_per_card": RATE}, indent=1))
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
