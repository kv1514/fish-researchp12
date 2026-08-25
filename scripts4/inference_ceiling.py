"""What is perfect card-reading worth? The ceiling on every inference gain.

The largest demonstrated gain in this project is posterior precision: +0.340
sets per duplicate deal-pair for 160 -> 480 draws. The next rung, 480 -> 1440,
came back +0.094 with an interval touching zero over 6000 pairs. So more
sampling has stopped paying -- which does not tell us whether *inference* has
stopped paying. A sampler can converge on a correct posterior and still leave
value on the table, or be wrong in a way more draws never fixes.

This measures the ceiling. One team keeps the champion's objective, weights,
claim rule and tablebase, and has its BELIEFS replaced by the truth
(``fish4.oracle``). The other team is the champion. Everything else is the
project's standard duplicate-deal design, so the margin is directly comparable
to every "vs champion" number already recorded:

    +0.340   480 draws vs 160          demonstrated
    +0.104   depth-3 belief lookahead  demonstrated
    +0.094   1440 draws vs 480         not demonstrated
    ?        PERFECT card-reading      <- this

Every future inference improvement is bounded by the number this prints. If it
is small, better inference is not where the remaining strength is and the
search should go elsewhere. If it is large, the sampler is leaving real sets on
the table.

WHY THIS SCRIPT HAS ITS OWN GAME LOOP, AND WHY THAT IS A RISK IT ADDRESSES
--------------------------------------------------------------------------
``play_matchup`` builds its agents inside worker processes from ``(name,
kwargs)`` specs, so there is no handle on which to install a deal. The
alternative -- a truth channel through the shared harness -- would put a leak
path in the code every honest run uses, to serve one cheating experiment. So
the pairing loop is duplicated here instead.

A duplicated harness that has silently drifted from the real one produces
numbers that look comparable and are not. ``--control`` therefore runs this
loop and ``play_matchup`` over the same seeds with the same two honest specs
and requires that they agree EXACTLY, pair for pair. The control runs by
default before any measurement.

Note that the game itself is still played by the real ``play_capped``: the
capped-game scoring semantics, which an earlier audit showed to be
bias-critical, are the harness's own and are not reimplemented.

    py scripts4/inference_ceiling.py --control-only
    py scripts4/inference_ceiling.py --pairs 200
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, deck_size
from fish.rules import RuleConfig
from fish4.match import play_capped, play_matchup
from fish4.oracle import OracleBot, initial_owners
from fish4.registry4 import make_agent

CHAMPION = ("fishbot4", {"opponent_gamma": 0.35})


def _agents_for(swap: int, x_factory, y_factory, owners, rules):
    """Six agents, X on even seats in swap 0 and odd seats in swap 1.

    Mirrors ``fish4.match._one_deal`` exactly; the swap is what makes the
    design paired.
    """
    out = []
    for seat in range(NUM_PLAYERS):
        on_x = (seat % 2 == 0) if swap == 0 else (seat % 2 == 1)
        a = (x_factory if on_x else y_factory)()
        if isinstance(a, OracleBot):
            a.see_deal(owners)
        out.append(a)
    return out


def one_pair(deal_seed, start_seat, agent_seed, x_factory, y_factory,
             rules_dict):
    """One duplicate deal-pair. Returns the X-minus-Y differential."""
    rng = random.Random(deal_seed)
    base = RuleConfig.from_dict(rules_dict)
    deck = list(range(deck_size(base.variant)))
    rng.shuffle(deck)
    owners = initial_owners(deck, base.variant)
    rules = RuleConfig(**{**rules_dict, "starting_player": start_seat})

    diff = 0
    for swap in (0, 1):
        agents = _agents_for(swap, x_factory, y_factory, owners, rules)
        st, _ = play_capped(agents, rules, deck, agent_seed)
        a, b, _ = st.scores()
        xs, ys = (a, b) if swap == 0 else (b, a)
        diff += xs - ys
    return diff


def run(n_pairs, x_factory, y_factory, base_seed, agent_seed_base,
        rules_dict, progress=False):
    seed_rng = random.Random(agent_seed_base)
    diffs = []
    t0 = time.time()
    for i in range(n_pairs):
        diffs.append(one_pair(base_seed + i, i % NUM_PLAYERS,
                              seed_rng.getrandbits(64),
                              x_factory, y_factory, rules_dict))
        if progress and (i + 1) % 25 == 0:
            print(f"  ... {i+1}/{n_pairs} pairs ({time.time()-t0:.0f}s)",
                  flush=True)
    return diffs


def summarise(diffs):
    n = len(diffs)
    m = sum(diffs) / n
    sd = math.sqrt(sum((d - m) ** 2 for d in diffs) / (n - 1)) if n > 1 else 0.0
    se = sd / math.sqrt(n) if n else 0.0
    return {"n_pairs": n, "mean": m, "sd": sd, "se": se,
            "ci95": [m - 1.96 * se, m + 1.96 * se]}


def control(n_pairs, base_seed, agent_seed_base, rules_dict) -> bool:
    """Does this loop reproduce ``play_matchup`` exactly, pair for pair?

    Two honest specs that genuinely differ, so an agreement is informative:
    an A/A would be identically zero on both sides under seat seeding and
    would agree for reasons that have nothing to do with this loop.
    """
    x = ("fishbot4", {"opponent_gamma": 0.35, "n_draws": 480})
    y = CHAMPION
    mine = run(n_pairs, lambda: make_agent(x), lambda: make_agent(y),
               base_seed, agent_seed_base, rules_dict)
    res = play_matchup(x, y, n_deals=n_pairs, n_jobs=1,
                       rules=RuleConfig.from_dict(rules_dict),
                       base_seed=base_seed, agent_seed_base=agent_seed_base)
    theirs = list(res.diffs)
    same = mine == theirs
    print(f"control: {n_pairs} pairs, this loop vs play_matchup")
    print(f"  mine   mean {sum(mine)/len(mine):+.4f}")
    print(f"  theirs mean {sum(theirs)/len(theirs):+.4f}")
    if same:
        print("  ok   identical pair for pair")
    else:
        bad = [(i, a, b) for i, (a, b) in enumerate(zip(mine, theirs)) if a != b]
        print(f"  FAIL {len(bad)} of {n_pairs} pairs differ; first few: {bad[:5]}")
    return same


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", type=int, default=200)
    ap.add_argument("--base-seed", type=int, default=40_000_000)
    ap.add_argument("--agent-seed", type=int, default=40001)
    ap.add_argument("--control-pairs", type=int, default=12)
    ap.add_argument("--control-seed", type=int, default=41_000_000)
    ap.add_argument("--control-only", action="store_true")
    ap.add_argument("--skip-control", action="store_true")
    a = ap.parse_args(argv)

    rules_dict = RuleConfig().to_dict()

    if not a.skip_control:
        if not control(a.control_pairs, a.control_seed, 41001, rules_dict):
            print("\nRefusing to measure: this loop is not the harness's.")
            return 1
        print()
    if a.control_only:
        return 0

    print(f"oracle team vs champion team, {a.pairs} pairs")
    diffs = run(a.pairs,
                lambda: OracleBot(opponent_gamma=0.35),
                lambda: make_agent(CHAMPION),
                a.base_seed, a.agent_seed, rules_dict, progress=True)
    s = summarise(diffs)
    print(f"\nPERFECT CARD-READING is worth "
          f"{s['mean']:+.3f} sets per deal-pair, "
          f"95% CI [{s['ci95'][0]:+.3f}, {s['ci95'][1]:+.3f}]  "
          f"(sd {s['sd']:.2f}, {s['n_pairs']} pairs)")
    print("\nfor scale, against the same champion:")
    print("   +0.340  480 draws vs 160        demonstrated")
    print("   +0.104  depth-3 lookahead       demonstrated")
    print("   +0.094  1440 draws vs 480       not demonstrated")
    out = ROOT / "results" / "inference_ceiling.json"
    out.write_text(json.dumps({
        "summary": s, "diffs": diffs,
        "x": "OracleBot(opponent_gamma=0.35) -- CHEATS, sees the true deal",
        "y": list(CHAMPION), "base_seed": a.base_seed,
        "agent_seed_base": a.agent_seed}, indent=1))
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
