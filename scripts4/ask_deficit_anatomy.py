"""Where do the 1.95 points of ask hit rate go? A distribution, not a scalar.

THE FACT THIS STARTS FROM. Through the repaired bridge (`BRIDGE_REV 3`) KRAKEN
v1.1 loses to SESTINA v1.0 by -0.5250 [-0.6886, -0.3614] sets/game, we declare
slightly BETTER than they do, and we ask worse: 52.98% hit rate against 54.93%
over about 46 asks a game (`results/mega_match.json`). P43 then failed to move
that with any of three registered ask-channel knobs.

"We ask 1.95 points worse" is a summary statistic and nothing can be aimed at
it. This turns it into a decomposition: every ask by either side, tagged with
the position features that could plausibly separate a good ask from a bad one,
so the gap can be attributed to strata rather than asserted of the whole.

    contribution of stratum s = freq(s) * (their_hit_rate(s) - our_hit_rate(s))

Those contributions sum to the overall gap by construction, so the output is an
exact accounting of where the deficit lives, not a correlation.

THIS IS EXPLORATORY AND ITS OUTPUT IS NOT A RESULT.
It is looked at BEFORE any candidate exists, which is exactly the situation in
which a decomposition invites a story. Anything it suggests is a hypothesis and
must be written into a new registration, with its own bar and its own confirm
block, before a single arm is played against it. The reason this file says so
rather than leaving it understood: P43 exists because sweeping knobs and keeping
the winner is the failure this project spends an appendix arguing against, and
choosing arms from a decomposition one has already stared at is the same failure
with an extra step.

WHAT IS AND IS NOT COMPUTABLE HERE. The strata are built from the ARBITER's
view, which sees every hand. That is deliberate: the question is where the two
policies differ in outcome, not what either could infer. A stratum is therefore
allowed to use hidden information (how many of the named half-suit the target
actually holds); a POLICY built on it would not be, and that distinction is the
first thing any registration coming out of this has to state.
"""

from __future__ import annotations

import argparse
import collections
import json
import statistics
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import CARDS_PER_HALF_SUIT, half_suit_of   # noqa: E402
from fish.engine import AskEvent, GameState                # noqa: E402
from fish.observation import Observation                   # noqa: E402
from fish.rules import RuleConfig                          # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 9_600_000
AGENT0 = 96_000
MAX_ACTIONS = 600


def _features(st, asker, ask):
    """Position features at the moment of an ask, from the arbiter's view."""
    hs = half_suit_of(ask.card)
    base = hs * CARDS_PER_HALF_SUIT
    hand = st.hands[asker]
    depth = sum(1 for i in range(CARDS_PER_HALF_SUIT)
                if hand >> (base + i) & 1)
    # How much of this half-suit the asker's TEAM already holds. "Still in
    # play" was the first version of this and it is vacuous: an unresolved
    # half-suit always has all six cards with somebody, so it had one bucket.
    team_held = sum(1 for i in range(CARDS_PER_HALF_SUIT)
                    for p in range(6) if p % 2 == asker % 2
                    and st.hands[p] >> (base + i) & 1)
    obs = Observation.from_state(st, asker)
    options = obs.legal_asks()
    suits = {half_suit_of(a.card) for a in options}
    resolved = sum(1 for w in st.set_winner if w is not None)
    return {
        "resolved": resolved,
        "n_options": len(options),
        "n_suits": len(suits),
        "depth": depth,
        "team_held_in_hs": team_held,
        "asker_cards": bin(hand).count("1"),
        "target_cards": bin(st.hands[ask.target]).count("1"),
        "forced": len(options) == 1,
    }


def _one(args) -> list[dict]:
    deal_seed, kv_even = args
    from fish4.registry4 import KRAKEN_V1, make_agent

    rules = RuleConfig(**RULES_D)
    agents = [make_agent(KRAKEN_V1) if (p % 2 == 0) == kv_even
              else make_agent(("dylan_v07", {})) for p in range(6)]
    st = GameState.deal(rules, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
    our_team = 0 if kv_even else 1
    rows = []
    for _ in range(MAX_ACTIONS):
        if st.is_terminal:
            break
        mover = st.turn
        act = agents[mover].act(Observation.from_state(st, mover))
        if hasattr(act, "target") and hasattr(act, "card"):
            f = _features(st, mover, act)
            f["ours"] = (mover % 2) == our_team
            n_before = len(st.history)
            st.apply(mover, act)
            ev = st.history[n_before] if len(st.history) > n_before else None
            f["hit"] = bool(getattr(ev, "success", False))
            rows.append(f)
        else:
            st.apply(mover, act)
    return rows


#: Each stratifier maps a row to a bucket label. Chosen BEFORE looking at any
#: output, and kept few, because a decomposition with enough strata will always
#: find one that looks like an explanation.
STRATA = {
    "phase (half-suits resolved)":
        lambda r: f"{min(r['resolved'], 6)}",
    "options available":
        lambda r: "1 (forced)" if r["n_options"] == 1
        else "2-5" if r["n_options"] <= 5
        else "6-15" if r["n_options"] <= 15 else "16+",
    "half-suits to choose from":
        lambda r: "1" if r["n_suits"] <= 1 else "2" if r["n_suits"] == 2
        else "3" if r["n_suits"] == 3 else "4+",
    "our depth in the named half-suit":
        lambda r: f"{min(r['depth'], 5)}",
    "our team's cards in the named half-suit":
        lambda r: f"{min(r['team_held_in_hs'], 6)}",
    "target's hand size":
        lambda r: "0-2" if r["target_cards"] <= 2
        else "3-5" if r["target_cards"] <= 5
        else "6-8" if r["target_cards"] <= 8 else "9+",
}


def report(rows) -> dict:
    """Oaxaca-Blinder: split the gap into execution and selection.

    The first version of this multiplied OUR share by the within-bucket
    difference and called the result a decomposition. It is not one -- the two
    sides do not ask in the same mix of positions, so

        gap = sum_s [ f_t(s) r_t(s) - f_o(s) r_o(s) ]

    does not reduce to sum_s f_o(s) (r_t(s) - r_o(s)) unless the mixes are
    equal. The strata each summed to a different total, which is what a
    decomposition that does not decompose looks like. The identity that does
    hold splits the gap in two:

        EXECUTION  sum_s f_o(s) [ r_t(s) - r_o(s) ]
                   they convert the same kind of ask better

        SELECTION  sum_s [ f_t(s) - f_o(s) ] r_t(s)
                   they ask in better kinds of position in the first place

    and that distinction is the whole point. Selection is what an ask objective
    chooses and is therefore fixable by changing the objective; execution at
    fixed position type is not something the objective controls at all, and a
    deficit there would mean the two engines see different things about the
    same position rather than rank it differently.

    Buckets one side never visits are real and are reported as unmatched rather
    than dropped, because dropping them is how the first version silently
    stopped adding up.
    """
    ours = [r for r in rows if r["ours"]]
    theirs = [r for r in rows if not r["ours"]]

    def rate(rs):
        return sum(r["hit"] for r in rs) / len(rs) if rs else None

    o_all, t_all = rate(ours), rate(theirs)
    gap = t_all - o_all
    print(f"\n=== where the ask deficit lives ===")
    print(f"{len(rows):,} asks   ours {len(ours):,}  theirs {len(theirs):,}")
    print(f"  our hit rate    {o_all:.4%}")
    print(f"  their hit rate  {t_all:.4%}")
    print(f"  gap             {gap:+.4%}  (theirs minus ours)\n")

    out = {"asks": len(rows), "our_hit": o_all, "their_hit": t_all,
           "gap": gap, "strata": {}}
    for name, key in STRATA.items():
        ob, tb = collections.defaultdict(list), collections.defaultdict(list)
        for r in ours:
            ob[key(r)].append(r)
        for r in theirs:
            tb[key(r)].append(r)
        print(f"  {name}")
        print(f"    {'bucket':14s}{'our n':>8s}{'their n':>9s}"
              f"{'our hit':>10s}{'their hit':>11s}"
              f"{'execution':>12s}{'selection':>12s}")
        buckets, exe, sel, unmatched = {}, 0.0, 0.0, 0.0
        for b in sorted(set(ob) | set(tb)):
            o, t = ob.get(b, []), tb.get(b, [])
            f_o, f_t = len(o) / len(ours), len(t) / len(theirs)
            if not o or not t:
                unmatched += max(f_o, f_t)
                buckets[b] = {"our_n": len(o), "their_n": len(t),
                              "unmatched": True,
                              "share_ours": f_o, "share_theirs": f_t}
                print(f"    {b:14s}{len(o):8,d}{len(t):9,d}"
                      f"{'--':>10s}{'--':>11s}{'unmatched':>12s}{'':>12s}")
                continue
            ro, rt = rate(o), rate(t)
            e, sl = f_o * (rt - ro), (f_t - f_o) * rt
            exe += e
            sel += sl
            buckets[b] = {"our_n": len(o), "their_n": len(t),
                          "our_hit": ro, "their_hit": rt,
                          "share_ours": f_o, "share_theirs": f_t,
                          "execution": e, "selection": sl}
            print(f"    {b:14s}{len(o):8,d}{len(t):9,d}{ro:10.2%}{rt:11.2%}"
                  f"{e:+12.4%}{sl:+12.4%}")
        print(f"    {'TOTAL':14s}{'':8s}{'':9s}{'':10s}{'':11s}"
              f"{exe:+12.4%}{sel:+12.4%}   "
              f"sum {exe + sel:+.4%} vs gap {gap:+.4%}"
              + (f"   unmatched share {unmatched:.2%}" if unmatched else ""))
        print()
        out["strata"][name] = {"buckets": buckets, "execution": exe,
                               "selection": sel, "sum": exe + sel,
                               "unmatched_share": unmatched}
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--deals", type=int, default=200)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--out", default=str(ROOT / "results"
                                         / "ask_deficit_anatomy.json"))
    a = ap.parse_args(argv)
    todo = [(SEED0 + i, ke) for i in range(a.deals) for ke in (True, False)]
    print(f"{len(todo):,} games at BRIDGE_REV 3, tagging every ask",
          flush=True)
    rows = []
    t0 = time.time()
    with Pool(a.jobs) as pool:
        for i, rs in enumerate(pool.imap_unordered(_one, todo, chunksize=1)):
            rows.extend(rs)
            if (i + 1) % 50 == 0:
                print(f"  {i + 1}/{len(todo)} games, {len(rows):,} asks, "
                      f"{(time.time() - t0) / 60:.1f} min", flush=True)
    out = report(rows)
    out["seconds"] = round(time.time() - t0, 1)
    out["games"] = len(todo)
    out["exploratory"] = ("hypothesis-generating only; any candidate arising "
                          "from this needs its own registration before a "
                          "single arm is played")
    Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
