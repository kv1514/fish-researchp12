"""How long a team sits on a half-suit it already owns, and what that costs.

WHERE THIS COMES FROM. `results/ask_deadness_signal.json` decomposed our
dead-ask rate against SESTINA's into the menu we choose from and the choice we
make from it. The choice is ours by 3.19 points; the MENU is theirs by 7.00.
So the deficit is not in the ask objective, and the next question is what makes
a menu deadder.

Under the no-bluff rule that question has a structural answer rather than an
empirical one. An ask is legal only for a card of a half-suit the asker holds
another of, so a half-suit is dead for us exactly when NO OPPONENT HOLDS ANY
CARD OF IT -- which, since an unclaimed half-suit's six cards are all in
someone's hand, means OUR OWN TEAM HOLDS ALL SIX. A dead ask is not a badly
chosen ask into a contested half-suit. It is an ask into a half-suit the asking
team has already won and not yet declared.

That equivalence is asserted at every decision below rather than argued, so a
rules variant that breaks it (bluff asks, a claim rule that leaves cards live)
fails loudly instead of quietly changing what the numbers mean.

AND COMPLETION IS ABSORBING. Once a team holds all six, no opponent holds a
card of that half-suit, so no opponent can legally ask into it, so no card can
leave. The state persists until the owning team declares. That makes the
interval from completion to declaration a well-defined latency rather than a
window that can close on its own, and makes "asks made into it meanwhile" a
clean price for the delay.

WHAT THIS MEASURES, PER SIDE. Completions per game; the latency in plies from
completion to declaration; the share of completions still undeclared at the end
of the game; and the asks the owning team spent into its own completed
half-suits while it sat there. The last is the dead-ask count, arrived at from
the other direction.

STILL EXPLORATORY, and now doubly so: this prices a mechanism, and the thing it
prices is a consequence of the declaration channel. It licenses no arm.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import CARDS_PER_HALF_SUIT, half_suit_of, half_suit_mask  # noqa: E402
from fish.engine import GameState                          # noqa: E402
from fish.observation import Observation                   # noqa: E402
from fish.rules import RuleConfig                          # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 9_900_000
AGENT0 = 99_000
MAX_ACTIONS = 600


def _one(args) -> tuple[tuple, dict]:
    deal_seed, kv_even = args
    from fish4.registry4 import KRAKEN_V1, make_agent

    rules = RuleConfig(**RULES_D)
    ours = {p for p in range(6) if (p % 2 == 0) == kv_even}
    agents = [make_agent(KRAKEN_V1) if p in ours
              else make_agent(("dylan_v07", {})) for p in range(6)]
    st = GameState.deal(rules, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
    nhs = 54 // CARDS_PER_HALF_SUIT
    # Per-game totals as well as pooled ones: the two sides play the SAME
    # deal, so their dead-ask counts are paired, and an unpaired interval on
    # the difference would price between-deal variation the contrast never
    # sees.
    done = [None] * nhs        # ply at which a team came to hold all six
    owner = [None] * nhs       # which team that was
    spent = [0] * nhs          # asks the owner made into it while sitting
    out = {"completions": [], "asks": {True: 0, False: 0},
           "dead": {True: 0, False: 0}}

    def team_mask(t):
        m = 0
        for p in range(6):
            if p % 2 == t:
                m |= st.hands[p]
        return m

    def scan(ply):
        for hs in range(nhs):
            if done[hs] is None and st.set_winner[hs] is None:
                for t in (0, 1):
                    if team_mask(t) & half_suit_mask(hs) == half_suit_mask(hs):
                        done[hs], owner[hs] = ply, t
                        break

    # A half-suit can arrive complete in the deal. Scanned at -1 so that such a
    # one is not silently dropped, and so its latency is on the same footing as
    # every other: a claim is its own action, so the floor is one ply either
    # way. Completion itself can only happen on a successful ask -- a claim
    # removes six cards and cannot complete anything -- so no completion is
    # ever invisible between the scans.
    scan(-1)
    for ply in range(MAX_ACTIONS):
        if st.is_terminal:
            break
        mover = st.turn
        obs = Observation.from_state(st, mover)
        act = agents[mover].act(obs)
        if hasattr(act, "target") and hasattr(act, "card"):
            hs = half_suit_of(act.card)
            side = mover in ours
            out["asks"][side] += 1
            # The equivalence, checked rather than assumed: every legal ask in
            # this half-suit missing is the same event as the mover's own team
            # holding all six of it.
            legal = [a for a in obs.legal_asks() if half_suit_of(a.card) == hs]
            dead = not any(st.hands[a.target] >> a.card & 1 for a in legal)
            complete = (team_mask(mover % 2) & half_suit_mask(hs)
                        == half_suit_mask(hs))
            if dead != complete:
                raise RuntimeError(
                    f"dead-ask equivalence broken at half-suit {hs}: "
                    f"dead={dead} team-complete={complete}; the no-bluff rule "
                    "this analysis rests on does not hold for these rules")
            if dead:
                spent[hs] += 1
                out["dead"][side] += 1
        st.apply(mover, act)
        # Completion is absorbing, so this only ever fires once per half-suit.
        scan(ply)
        for hs in range(nhs):
            if done[hs] is not None and st.set_winner[hs] is not None:
                if not any(c["hs"] == hs for c in out["completions"]):
                    out["completions"].append(
                        {"hs": hs, "ours": (owner[hs] == (0 if kv_even else 1)),
                         "latency": ply - done[hs], "spent": spent[hs],
                         "declared": True})
    for hs in range(nhs):
        if done[hs] is not None and st.set_winner[hs] is None:
            out["completions"].append(
                {"hs": hs, "ours": (owner[hs] == (0 if kv_even else 1)),
                 "latency": None, "spent": spent[hs], "declared": False})
    return args, out


def report(games) -> dict:
    comps = [c for g in games for c in g["completions"]]
    asks = {True: sum(g["asks"][True] for g in games),
            False: sum(g["asks"][False] for g in games)}
    out = {"games": len(games), "completions": len(comps)}
    print(f"\n=== sitting on a half-suit you already own ===")
    print(f"{len(games):,} games, {len(comps):,} completions\n")
    print(f"  {'':34s}{'KRAKEN v1.1':>14s}{'SESTINA v1.0':>15s}")
    rows = []
    for side in (True, False):
        cs = [c for c in comps if c["ours"] is side]
        lat = [c["latency"] for c in cs if c["declared"]]
        rows.append({
            "completions_per_game": len(cs) / len(games),
            "undeclared_share": sum(not c["declared"] for c in cs) / len(cs),
            "mean_latency_plies": statistics.fmean(lat) if lat else None,
            "median_latency_plies": statistics.median(lat) if lat else None,
            "dead_asks_per_completion": sum(c["spent"] for c in cs) / len(cs),
            "dead_asks": sum(c["spent"] for c in cs),
            "asks": asks[side],
            "dead_ask_share_of_asks": sum(c["spent"] for c in cs) / asks[side],
        })
        # The mean and the median disagree by an order of magnitude, so the
        # shape matters more than either: most completions are declared at
        # once and a minority sit. Both the size of that tail and the share of
        # the dead asks it accounts for are reported, because "we are slow to
        # declare" and "we occasionally get stuck" are different problems with
        # different fixes.
        stuck = [c for c in cs if not c["declared"] or c["latency"] >= 10]
        rows[-1]["stuck_share"] = len(stuck) / len(cs)
        rows[-1]["dead_asks_from_stuck"] = (
            sum(c["spent"] for c in stuck) / max(1, sum(c["spent"] for c in cs)))
    for key, label, fmt in (
            ("completions_per_game", "half-suits completed per game", "{:.3f}"),
            ("mean_latency_plies", "mean plies to declare it", "{:.2f}"),
            ("median_latency_plies", "median plies to declare it", "{:.1f}"),
            ("undeclared_share", "never declared", "{:.2%}"),
            ("dead_asks_per_completion", "asks spent into it meanwhile", "{:.3f}"),
            ("dead_ask_share_of_asks", "those, as a share of all asks", "{:.2%}"),
            ("stuck_share", "completions sat on 10+ plies", "{:.2%}"),
            ("dead_asks_from_stuck", "share of dead asks from those", "{:.2%}")):
        a = fmt.format(rows[0][key]) if rows[0][key] is not None else "--"
        b = fmt.format(rows[1][key]) if rows[1][key] is not None else "--"
        print(f"  {label:34s}{a:>14s}{b:>15s}")
    # Keyed without a dot: the figure-pinning manifest splits a dotted path.
    rows[0]["label"], rows[1]["label"] = "KRAKEN v1.1", "SESTINA v1.0"
    out["kraken_v11"], out["sestina_v10"] = rows

    # Is this channel the right SIZE to matter? The excess is denominated in
    # dead asks; this project has a measured price for exactly one thing of
    # that kind -- results/turn_price.json, the value of one donated turn,
    # +0.2713 [+0.0922, +0.4505] sets over 1,500 paired deals. Both
    # uncertainties are propagated: the per-game difference by a paired
    # bootstrap, the price by its own standard error.
    #
    # This is an accounting of a DIFFERENCE, not a counterfactual. Removing a
    # dead ask changes every ply after it; SESTINA's own 4.7 a game are not
    # zero and nothing here says ours could be; and the price was measured
    # with our engine on both sides at a decision chosen without reference to
    # what the agent wanted. It answers "is this channel big enough to be the
    # story", which is a smaller question than "is it the cause", and the
    # smaller question is the one the numbers can carry.
    import random as _r
    price = json.loads((ROOT / "results" / "turn_price.json").read_text())
    mu, se = price["summary"]["mean"], price["summary"]["se"]
    diffs = [g["dead"][True] - g["dead"][False] for g in games]
    rng = _r.Random(20260908)
    reps = []
    for _ in range(4000):
        d = statistics.fmean(rng.choices(diffs, k=len(diffs)))
        reps.append(d * rng.gauss(mu, se))
    reps.sort()
    lo, hi = reps[100], reps[3899]
    dm = statistics.fmean(diffs)
    print(f"\n  our excess dead asks per game                {dm:+.3f}")
    print(f"  at the measured price of a donated turn      "
          f"{dm * mu:+.3f} sets/game  [{lo:+.3f}, {hi:+.3f}]")
    print(f"  the deficit this would have to account for   -0.5250 "
          "[-0.6886, -0.3614]")
    out["excess_dead_asks_per_game"] = dm
    out["turn_price_used"] = {"mean": mu, "se": se,
                              "source": "results/turn_price.json"}
    out["excess_priced_sets_per_game"] = {"point": dm * mu, "ci95": [lo, hi]}
    out["not_a_counterfactual"] = (
        "difference accounting only; removing a dead ask changes every "
        "subsequent ply and the price was not measured against SESTINA")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--deals", type=int, default=400)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--out", default=str(ROOT / "results"
                                         / "completion_latency.json"))
    a = ap.parse_args(argv)
    todo = [(SEED0 + i, ke) for i in range(a.deals) for ke in (True, False)]
    print(f"{len(todo):,} games", flush=True)
    # Re-assembled in the order of `todo` rather than of completion: the size
    # check bootstraps per-game differences, so an artifact whose game order
    # depends on pool scheduling is not reproducible from its own seeds.
    got, t0 = {}, time.time()
    with Pool(a.jobs) as pool:
        for i, (key, g) in enumerate(pool.imap_unordered(_one, todo,
                                                         chunksize=1)):
            got[key] = g
            if (i + 1) % 100 == 0:
                print(f"  {i+1}/{len(todo)} games, "
                      f"{(time.time()-t0)/60:.1f} min", flush=True)
    games = [got[k] for k in todo]
    out = report(games)
    out["seconds"] = round(time.time() - t0, 1)
    out["exploratory"] = "prices a mechanism; licenses no arm"
    Path(a.out).write_text(json.dumps(out, indent=1) + "\n")
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
