"""Does the opponent model have the right SIGN against a FOREIGN policy?

The opponent model is the largest single effect in this engine, and it rests on
one assumed sentence: a player asks in a half-suit in proportion to how many
cards of it they hold, with exponent gamma = +0.35. scripts4/choice_curve.py
measured that propensity and found it positive -- but it measured this project's
own champion AGAINST A COPY OF ITSELF, which is the one population where the
assumption is guaranteed to be self-consistent.

That script's own docstring already flagged why the sign is not obvious:

    "holding five of six leaves exactly one card to ask for, holding one of six
    leaves five. Those pull opposite ways, so linear-in-depth is not obviously
    right even in sign"

Dylan's v0.7 is a foreign policy dominated by P(success) (w[0] = 11.266 on p,
his largest coefficient by a wide margin). A policy that maximises the chance a
single named card lands has more candidate cards to choose from in a half-suit
it holds FEW of. If that dominates, his asks are evidence of shallowness, and
our sampler is re-weighting worlds in exactly the wrong direction on every one
of his moves -- three of the six seats at the table.

THIS SCRIPT DOES NOT CHANGE THE BOT. It reuses the conditional-logit design
already written and validated in choice_curve.py -- same alternatives, same
depth definition, same estimator -- and only changes WHOSE asks are recorded
and WHO is playing. A difference in the fitted alpha between the two
populations is then attributable to the policy rather than to the method.

WHAT WOULD MAKE THIS ACTIONABLE, AND WHAT WOULD NOT. A negative alpha for his
seats is a measurement about HIS engine, not a licence to ship anything: this
project has already withdrawn one feature that turned out to be exploiting a
sibling's opponent model rather than playing better. So the output here is a
number and a sign, and any use of it has to be pre-registered separately and
justified against a foreign opponent that is not the one it was fitted on.

    py scripts4/choice_curve_foreign.py [n_games]
"""

from __future__ import annotations

import json
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import (NUM_PLAYERS, deck_size, half_suit_cards, half_suit_of,
                        num_half_suits, team_of)
from fish.engine import Ask, GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.registry4 import V06_DEPLOYED, make_agent

# The same estimator the self-play study used, imported rather than re-derived
# so the two numbers are comparable by construction.
from scripts4.choice_curve import (_report, bootstrap_alpha, design,
                                   fit_design, propensity)

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 1_700_000
AGENT0 = 17_000
JOURNAL = Path(os.environ.get(
    "FOREIGN_CHOICE_JOURNAL",
    ROOT / "results" / "choice_curve_foreign_records.json"))


def collect(n_games: int):
    """One record per ask BY A DYLAN SEAT, in a real cross-engine game.

    Their seats are the even ones, matching the exhibition. Our seats play the
    deployed spec, so the games are the same population every head-to-head
    number in this project is measured on -- not a contrived probe.
    """
    rules = RuleConfig(**RULES_D)
    n_hs = num_half_suits(rules.variant)
    n_cards = deck_size(rules.variant)
    records = []
    for g in range(n_games):
        seed = SEED0 + 977 * g
        st = GameState.deal(rules, seed=seed)
        initial = list(st.hands)
        agents = [make_agent(("dylan_v07", {})) if p % 2 == 0
                  else make_agent(V06_DEPLOYED) for p in range(NUM_PLAYERS)]
        ar = random.Random(AGENT0 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        depth0 = [[0] * n_hs for _ in range(NUM_PLAYERS)]
        for p in range(NUM_PLAYERS):
            for c in range(n_cards):
                if initial[p] >> c & 1:
                    depth0[p][half_suit_of(c)] += 1
        step = 0
        while not st.is_terminal and step < 300:
            p = st.turn
            act = agents[p].act(Observation.from_state(st, p))
            # Only THEIR asks. Ours are the population choice_curve.py already
            # measured, and mixing them would average two policies into one
            # meaningless exponent.
            if isinstance(act, Ask) and p % 2 == 0:
                live = []
                for hs in range(n_hs):
                    if st.set_winner[hs] is not None:
                        continue
                    held = sum(1 for c in half_suit_cards(hs)
                               if st.hands[p] >> c & 1)
                    if held == 0:
                        continue
                    missing = sum(1 for c in half_suit_cards(hs)
                                  if not (st.hands[p] >> c & 1))
                    live.append({"hs": hs, "depth0": depth0[p][hs],
                                 "held_now": held, "missing_now": missing})
                if len(live) >= 2:
                    records.append({
                        "alts": live,
                        "picked": half_suit_of(act.card),
                        "resolved": sum(1 for w in st.set_winner
                                        if w is not None),
                        "n_hs": n_hs,
                        "game": g,
                        "seat": p,
                    })
            st.apply(p, act)
            step += 1
        if (g + 1) % 10 == 0:
            print(f"  {g + 1}/{n_games} games, {len(records)} of their asks",
                  flush=True)
    return records


def main(n_games: int = 60) -> int:
    if JOURNAL.exists():
        records = json.loads(JOURNAL.read_text())
        print(f"{len(records)} records loaded from {JOURNAL.name}")
    else:
        records = collect(n_games)
        JOURNAL.write_text(json.dumps(records))
        print(f"collected {len(records)} of their asks over {n_games} games")

    if len(records) < 200:
        print("too few records to fit")
        return 1

    curve = propensity(records, key="depth0")
    print("\n=== their propensity to ask by depth on the initial deal ===")
    _report("dylan v0.7 (foreign)", curve)

    des = design(records)
    fit = fit_design(des)
    alpha = fit["alpha"]
    # Clustered over GAMES, not decisions: asks inside one deal share a layout
    # and six hands, so the likelihood's own curvature understates the spread.
    boot = bootstrap_alpha(records, reps=200)
    se = boot["se_clustered"] if boot else fit["se"]
    lo, hi = alpha - 1.96 * se, alpha + 1.96 * se
    print(f"\n  fitted alpha = {alpha:+.4f}   95% CI [{lo:+.4f}, {hi:+.4f}]"
          f"   (n = {fit['n']:,} asks, se clustered over games"
          f"{'' if boot else ' UNAVAILABLE -- curvature se, understated'})")
    print(f"  our sampler assumes gamma = +0.35 for every seat")

    if hi < 0:
        verdict = "OPPOSITE SIGN -- our model re-weights his worlds backwards"
    elif lo > 0:
        verdict = "same sign as assumed"
    else:
        verdict = "INCONCLUSIVE -- the interval straddles zero"
    print(f"  VERDICT: {verdict}")

    out = {"rules": RULES_D, "n_games": n_games, "n_records": len(records),
           "alpha": alpha, "ci95": [lo, hi], "se_clustered": se,
           "nll": fit["nll"], "clustered": bool(boot),
           "assumed_gamma": 0.35, "verdict": verdict,
           "curve": {str(k): v for k, v in curve.items()}}
    (ROOT / "results" / "choice_curve_foreign.json").write_text(
        json.dumps(out, indent=1))
    print("wrote results/choice_curve_foreign.json")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 60))
