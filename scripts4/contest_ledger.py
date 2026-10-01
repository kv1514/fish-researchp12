"""Do we lose the half-suits we fight for, or fight for the wrong ones?

THE GAP THIS FILLS

`results/completion_ledger_12500000.json` found the revision-3 deficit is not
tempo -- turn acquisitions are level to a tenth of a turn in 23, and the tenth
is ours -- but WASTED HITS: 31.6% of our successful asks land in half-suits we
never go on to win, against 25.2% of theirs, at kept-hits-per-half-suit of
4.009 against 4.090. The two engines are indistinguishable in what they do
with a card once it is on the winning side of the ledger; the whole gap is
which side it lands on.

That measurement says WHERE the loss is and nothing about why. Two mechanisms
fit it and they call for opposite fixes:

  SELECTION   we invest in half-suits we were never going to win. Then the
              win rate at matched investment is level between the engines,
              and the difference is which half-suits get the asks. The lever
              is choosing, and the deal itself predicts it.
  CONVERSION  we invest in the same half-suits and lose them anyway. Then
              our win rate is lower at every investment level, and the lever
              is holding on to what we gather rather than picking targets.

A third possibility has to be named so it can be excluded rather than
assumed: SPREAD, where we invest a little in many half-suits and they invest
a lot in few. Spread is a form of selection but it is visible separately, in
the count of half-suits invested in and in asks per invested half-suit.

WHAT IS RECORDED. For every half-suit of every game: how many successful asks
each team made into it, how many of its six cards each team was DEALT, and who
won it. The dealt share is the part no instrument here has ever carried, and
it is what separates "picked a fight it could win" from "won a fair fight" --
a half-suit dealt 4-2 in your favour is not evidence of skill when you take
it.

A NOTE ON WHAT A GIVE-BACK IS, because the obvious framing collapses. Every
card a team loses, it loses to an opponent's successful ask, and declarations
remove the rest from play -- so "cards we won and then lost" is very nearly
the opponent's hit count, which is already measured and says nothing new. The
quantity with content is the HALF-SUIT the contested cards belonged to, which
is what this file counts.

PREDICTION, RECORDED BEFORE THE RUN: selection with a spread component. We
invest in more half-suits at fewer asks each, and our win rate conditional on
both investment and dealt share is level with theirs. If instead the win rate
is lower at matched investment and matched deal, the reading is conversion and
the `expose` axis -- priced at zero in the shipped objective and never dueled
alone -- becomes the first named knob behind this gap.

SHIPS NOTHING. The champion plays unchanged; this describes finished games.

    py scripts4/contest_ledger.py [--deals 400] [--jobs 3]
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

from fish.cards import team_of                              # noqa: E402
from fish.engine import AskEvent, ClaimEvent, GameState     # noqa: E402
from fish.observation import Observation                    # noqa: E402
from fish.rules import RuleConfig                           # noqa: E402
from scripts4.resultfile import default_path, write         # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}
#: Fresh block again. 12,500,000 is the completion ledger's.
SEED0 = 12_700_000
#: the shape columns were added after the first block, so the run that
#: carries them uses its own seeds rather than re-reporting a file without them
SEED_SHAPE = 13_100_000
AGENT0 = 127_000
MAX_ACTIONS = 600
SIDES = ("kv", "dy")


def _one(args) -> dict:
    deal_seed, kv_even = args
    from fish4.registry4 import KRAKEN_V1, make_agent
    from fish4.dylan_v07_persistent import DylanV07Persistent

    rules = RuleConfig(**RULES_D)
    agents = []
    for p in range(6):
        kv = (p % 2 == 0) == kv_even
        agents.append(make_agent(KRAKEN_V1) if kv else DylanV07Persistent())
    st = GameState.deal(rules, seed=deal_seed)
    kv_team = 0 if kv_even else 1
    side_of = {kv_team: "kv", 1 - kv_team: "dy"}

    # The DEALT share, taken before a card moves. It is the covariate the
    # whole question turns on and it is unrecoverable after the first ask.
    dealt = [[0, 0] for _ in range(9)]
    #: per-seat dealt counts, so each team's holding of a half-suit has a
    #: SHAPE as well as a size. Which of our seats may ask in a half-suit is
    #: fixed by the deal -- the rules require the asker to hold a card of it
    #: -- so the shape is exogenous in exactly the way the split is, and it is
    #: the only covariate available that separates "three seats each holding
    #: one card and none able to lead" from "one seat holding three".
    per_seat = [[0] * 6 for _ in range(9)]
    for c in range(54):
        for p in range(6):
            if st.hands[p] >> c & 1:
                dealt[c // 6][team_of(p)] += 1
                per_seat[c // 6][p] += 1
                break

    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
    for _ in range(MAX_ACTIONS):
        if st.is_terminal:
            break
        st.apply(st.turn, agents[st.turn].act(
            Observation.from_state(st, st.turn)))

    hits = [[0, 0] for _ in range(9)]
    won_by_own = {}
    for e in st.history:
        if isinstance(e, AskEvent) and e.success:
            hits[e.card // 6][team_of(e.asker)] += 1
        elif isinstance(e, ClaimEvent) and e.winner == team_of(e.claimer):
            won_by_own[e.half_suit] = e.winner

    rows = []
    for hs in range(9):
        w = won_by_own.get(hs)
        shape = {}
        for side, t in (("kv", kv_team), ("dy", 1 - kv_team)):
            counts = sorted((per_seat[hs][p] for p in range(6)
                             if team_of(p) == t), reverse=True)
            shape[side] = "-".join(str(x) for x in counts)
        rows.append({
            "hs": hs,
            "shape_kv": shape["kv"], "shape_dy": shape["dy"],
            "dealt_kv": dealt[hs][kv_team], "dealt_dy": dealt[hs][1 - kv_team],
            "hits_kv": hits[hs][kv_team], "hits_dy": hits[hs][1 - kv_team],
            # None when neither side won it by its own correct declaration,
            # i.e. it was a gift from a misdeclaration. Counted for nobody.
            "winner": None if w is None else side_of[w],
        })
    return {"deal": deal_seed, "kv_even": kv_even, "terminal": st.is_terminal,
            "fallbacks": sum(getattr(a, "fallbacks", 0) for a in agents),
            "half_suits": rows}


def _ci(xs):
    if not xs:
        return float("nan"), float("nan"), float("nan")
    m = sum(xs) / len(xs)
    se = (statistics.stdev(xs) / len(xs) ** 0.5) if len(xs) > 1 else 0.0
    return m, m - 1.96 * se, m + 1.96 * se


def report(games: list[dict], seed: int | None = None) -> dict:
    n = len(games)
    #: The seed ACTUALLY played, read off the games when not passed. It used to
    #: be the module constant, so `--seed` changed the deals and neither the
    #: filename nor the recorded identity -- and a run on a fresh block
    #: overwrote an earlier one under an identity the clobber guard could not
    #: distinguish. Derived rather than trusted, so the file cannot disagree
    #: with its own rows.
    played = min(g["deal"] for g in games)
    if seed is not None and seed != played:
        raise SystemExit(f"--seed {seed} but the games start at {played}")
    seed = played
    flat = [(g["deal"], r) for g in games for r in g["half_suits"]]
    out = {"script": "scripts4/contest_ledger.py", "descriptive": True,
           "rules": RULES_D, "seed_deal": seed, "seed_agent": AGENT0,
           "n_games": n, "n_half_suits": len(flat), "bridge_rev": 3,
           "fallbacks": sum(g["fallbacks"] for g in games),
           "unfinished": sum(1 for g in games if not g["terminal"])}

    print("\n" + "=" * 76)
    print("  DO WE LOSE THE FIGHTS, OR PICK THE WRONG ONES?")
    print(f"  {n:,} games, {len(flat):,} half-suits, BRIDGE_REV 3, "
          f"{out['fallbacks']} fallbacks, {out['unfinished']} unfinished")
    print("=" * 76)

    # 1. SPREAD. How many half-suits does each side put asks into at all.
    print(f"\n  --- spread: where the asks go ---")
    print(f"  {'':<34}{'KRAKEN':>10}{'SESTINA':>10}{'ours - theirs':>26}")
    inv, per = {}, {}
    for s in SIDES:
        inv[s] = [sum(1 for r in g["half_suits"] if r[f"hits_{s}"] > 0)
                  for g in games]
        per[s] = [sum(r[f"hits_{s}"] for r in g["half_suits"])
                  / max(1, sum(1 for r in g["half_suits"] if r[f"hits_{s}"] > 0))
                  for g in games]
    for label, d in (("half-suits asked into", inv),
                     ("hits per half-suit asked into", per)):
        a, b = d["kv"], d["dy"]
        m, lo, hi = _ci([x - y for x, y in zip(a, b)])
        print(f"  {label:<34}{sum(a)/n:>10.3f}{sum(b)/n:>10.3f}"
              f"{f'{m:+.4f} [{lo:+.4f}, {hi:+.4f}]':>26}")
        out[label.replace(" ", "_")] = {
            "kv": sum(a) / n, "dy": sum(b) / n,
            "paired": {"mean": m, "ci95": [lo, hi]}}

    # 2. THE MATCHED COMPARISON. Dealt splits are complementary, so "we were
    #    dealt k" and "they were dealt 6-k" name the SAME half-suits scored
    #    from opposite sides: one set, scored twice, no subset confound. The
    #    deal is also the only covariate here that is exogenous -- it is fixed
    #    before a card moves and neither policy can influence it.
    #
    #    A TABLE THIS FILE USED TO PRINT IS GONE, and why matters more than
    #    what it said. It reported the win rate conditional on HITS INVESTED,
    #    as if investment were a choice priced against an outcome. It is not:
    #    winning a 3-3 half-suit requires taking the opponent's three cards,
    #    so three successful asks into it are a CONSEQUENCE of winning it, not
    #    a bet placed on it. Scored on the 800-game block the cell structure
    #    was degenerate -- hit difference -3 gave a 0.000/0.996 split and +3
    #    gave 0.990/0.000, with nine half-suits anywhere between. A covariate
    #    downstream of the outcome cannot separate selection from conversion,
    #    and reading one that does looks exactly like a finding.
    print(f"\n  --- conversion at a matched deal: the same half-suits, "
          f"scored both ways ---")
    print(f"  {'deal (ours)':<13}{'n':>7}{'we convert':>12}"
          f"{'they convert':>14}{'edge':>9}{'gift':>8}")
    matched, cost = {}, 0.0
    for k in range(6, -1, -1):
        ours = [r for _d, r in flat if r["dealt_kv"] == k]
        mirror = [r for _d, r in flat if r["dealt_kv"] == 6 - k]
        if not ours or not mirror:
            continue
        a = sum(1 for r in ours if r["winner"] == "kv") / len(ours)
        b = sum(1 for r in mirror if r["winner"] == "dy") / len(mirror)
        gift = sum(1 for r in ours if r["winner"] is None) / len(ours)
        cost += len(ours) * (b - a)
        print(f"  {f'{k}-{6-k}':<13}{len(ours):>7}{a:>12.3f}{b:>14.3f}"
              f"{a - b:>+9.3f}{gift:>8.3f}")
        matched[f"{k}-{6-k}"] = {"n": len(ours), "we_convert": a,
                                 "they_convert": b, "edge": a - b,
                                 "gift_share": gift}
    out["matched_by_deal"] = matched

    # 3. What the gap is worth, stated as arithmetic and labelled as such.
    mid = ("4-2", "3-3", "2-4")
    ext = ("6-0", "5-1", "1-5", "0-6")
    def block(keys):
        return sum(matched[k]["n"] * -matched[k]["edge"]
                   for k in keys if k in matched) / n
    out["cost_per_game"] = cost / n
    #: two sets a half-suit, per the margin identity. Quoted in the paper, so
    #: it is stored rather than multiplied out in LaTeX -- computing a figure
    #: in the manuscript is how Table tab:exact came to disagree with its own
    #: pipeline.
    out["margin_swing"] = 2 * cost / n
    out["cost_middle"] = block(mid)
    out["cost_extremes"] = block(ext)
    out["middle_share"] = sum(matched[k]["n"] for k in mid if k in matched) \
        / len(flat)
    print(f"\n  half-suits a game if we converted at their rate everywhere: "
          f"{cost / n:+.4f}")
    print(f"    the contested middle (4-2, 3-3, 2-4), "
          f"{out['middle_share']:.1%} of all half-suits: "
          f"{out['cost_middle']:+.4f}")
    print(f"    the extremes (6-0, 5-1, 1-5, 0-6), where we are AHEAD: "
          f"{out['cost_extremes']:+.4f}")
    print("  Arithmetic on finished games, not a counterfactual margin: a")
    print("  half-suit that changed hands changes every ply after it.")

    # 4. THE COORDINATION SPLIT. Within an even 3-3 deal, how the three cards
    #    sit across a team's three seats is fixed by the deal and is the one
    #    remaining exogenous covariate. If our disadvantage concentrates in
    #    1-1-1 -- three seats each holding one card, none able to lead the
    #    fight -- that is a coordination failure and not a play failure, and
    #    it is the only family in the opponent's basis with no analogue in
    #    ours. If it is flat across shapes, coordination is not the story.
    # Blocks written before the shape columns existed have no shape_kv, and a
    # reporter that crashes on its own older files is a reporter nobody will
    # re-run. Skipped with a line saying so, rather than silently omitted.
    if not all("shape_kv" in r for _d, r in flat):
        print("\n  --- seat-shape split: SKIPPED, this block predates the "
              "shape columns ---")
        out["coordination_shape_3_3"] = None
        print("\n  SELECTION would read as a level conversion at a matched "
              "deal,")
        print("  with the asks going to different half-suits. CONVERSION "
              "reads as")
        print("  a lower conversion for us at the SAME deal. SPREAD reads as "
              "more")
        print("  half-suits asked into, at fewer hits each.")
        return out
    print(f"\n  --- even 3-3 deals only, by how the three sit across seats ---")
    print(f"  {'shape':<10}{'n':>7}{'we convert':>12}{'they convert':>14}"
          f"{'edge':>9}")
    coord = {}
    seen = sorted({r["shape_kv"] for _d, r in flat if r["dealt_kv"] == 3})
    for sh in seen:
        ours = [r for _d, r in flat
                if r["dealt_kv"] == 3 and r["winner"] is not None
                and r["shape_kv"] == sh]
        theirs = [r for _d, r in flat
                  if r["dealt_dy"] == 3 and r["winner"] is not None
                  and r["shape_dy"] == sh]
        if not ours or not theirs:
            continue
        a = sum(1 for r in ours if r["winner"] == "kv") / len(ours)
        b = sum(1 for r in theirs if r["winner"] == "dy") / len(theirs)
        print(f"  {sh:<10}{len(ours):>7}{a:>12.3f}{b:>14.3f}{a - b:>+9.3f}")
        coord[sh] = {"n_ours": len(ours), "we_convert": a,
                     "n_theirs": len(theirs), "they_convert": b,
                     "edge": a - b}
    out["coordination_shape_3_3"] = coord

    print("\n  SELECTION would read as a level conversion at a matched deal,")
    print("  with the asks going to different half-suits. CONVERSION reads as")
    print("  a lower conversion for us at the SAME deal. SPREAD reads as more")
    print("  half-suits asked into, at fewer hits each.")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--deals", type=int, default=400)
    ap.add_argument("--seed", type=int, default=SEED0)
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--rescore", action="store_true",
                    help="re-report from the stored run instead of replaying "
                         "it; the games do not change when a table is fixed")
    a = ap.parse_args(argv)
    if a.rescore:
        dest = default_path("contest_ledger", a.seed)
        old = json.loads(dest.read_text())
        out = report(old["per_game"], a.seed)
        out["seconds"] = old.get("seconds")
        out["rescored"] = True
        out["per_game"] = old["per_game"]
        print("\n  wrote", write(dest, out, force=True))
        return 0
    todo = [(a.seed + i, ke) for i in range(a.deals) for ke in (True, False)]
    print(f"{len(todo):,} games on {a.jobs} workers", flush=True)
    games, t0 = [], time.time()
    with Pool(a.jobs) as pool:
        for i, r in enumerate(pool.imap_unordered(_one, todo, chunksize=1)):
            games.append(r)
            if (i + 1) % 100 == 0:
                print(f"  {i + 1}/{len(todo)}, "
                      f"{(time.time() - t0) / 60:.1f} min", flush=True)
    if len(games) < 30:
        print("too few games", file=sys.stderr)
        return 1
    out = report(games, a.seed)
    out["seconds"] = round(time.time() - t0, 1)
    out["per_game"] = games
    print("\n  wrote", write(default_path("contest_ledger", a.seed), out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
