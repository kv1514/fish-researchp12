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
    for c in range(54):
        for p in range(6):
            if st.hands[p] >> c & 1:
                dealt[c // 6][team_of(p)] += 1
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
        rows.append({
            "hs": hs,
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


def report(games: list[dict]) -> dict:
    n = len(games)
    flat = [(g["deal"], r) for g in games for r in g["half_suits"]]
    out = {"script": "scripts4/contest_ledger.py", "descriptive": True,
           "rules": RULES_D, "seed_deal": SEED0, "seed_agent": AGENT0,
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

    # 2. SELECTION vs CONVERSION. Win rate by investment, and by dealt share.
    #    A half-suit won because the OTHER side misdeclared is excluded from
    #    both, because nobody's asking produced it.
    def table(keyfn, title, head):
        print(f"\n  --- {title} ---")
        print(f"  {head:<16}{'n (ours)':>10}{'we win':>9}"
              f"{'n (theirs)':>12}{'they win':>10}{'diff':>9}")
        cells = {}
        for s, other in (("kv", "dy"), ("dy", "kv")):
            for _deal, r in flat:
                if r["winner"] is None or r[f"hits_{s}"] == 0:
                    continue
                k = keyfn(r, s)
                cells.setdefault(k, {}).setdefault(s, []).append(
                    1.0 if r["winner"] == s else 0.0)
        rows = {}
        for k in sorted(cells):
            a = cells[k].get("kv", [])
            b = cells[k].get("dy", [])
            ma = sum(a) / len(a) if a else float("nan")
            mb = sum(b) / len(b) if b else float("nan")
            print(f"  {str(k):<16}{len(a):>10}{ma:>9.3f}"
                  f"{len(b):>12}{mb:>10.3f}{ma - mb:>+9.3f}")
            rows[str(k)] = {"n_kv": len(a), "win_kv": ma,
                            "n_dy": len(b), "win_dy": mb, "diff": ma - mb}
        return rows

    out["win_by_investment"] = table(
        lambda r, s: min(r[f"hits_{s}"], 5), "win rate by hits invested",
        "hits invested")
    out["win_by_dealt"] = table(
        lambda r, s: r[f"dealt_{s}"], "win rate by cards DEALT to that side",
        "cards dealt")

    # 3. Where the asks go relative to the deal. Selection shows here.
    print(f"\n  --- hits invested, by how many of the six you were dealt ---")
    print(f"  {'cards dealt':<16}{'ours':>10}{'theirs':>10}{'diff':>10}"
          f"{'n (ours)':>11}{'n (theirs)':>12}")
    by_dealt = {}
    for s in SIDES:
        for _deal, r in flat:
            by_dealt.setdefault(r[f"dealt_{s}"], {}).setdefault(s, []).append(
                r[f"hits_{s}"])
    rows = {}
    for k in sorted(by_dealt):
        a, b = by_dealt[k].get("kv", []), by_dealt[k].get("dy", [])
        ma = sum(a) / len(a) if a else float("nan")
        mb = sum(b) / len(b) if b else float("nan")
        print(f"  {k:<16}{ma:>10.3f}{mb:>10.3f}{ma - mb:>+10.3f}"
              f"{len(a):>11}{len(b):>12}")
        rows[str(k)] = {"hits_kv": ma, "hits_dy": mb, "diff": ma - mb,
                        "n_kv": len(a), "n_dy": len(b)}
    out["hits_by_dealt"] = rows

    print("\n  SELECTION reads as a level win rate at matched hits AND matched")
    print("  deal, with the investment going to different half-suits.")
    print("  CONVERSION reads as a lower win rate for us at matched both.")
    print("  SPREAD reads as more half-suits asked into, at fewer hits each.")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--deals", type=int, default=400)
    ap.add_argument("--seed", type=int, default=SEED0)
    ap.add_argument("--jobs", type=int, default=3)
    a = ap.parse_args(argv)
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
    out = report(games)
    out["seconds"] = round(time.time() - t0, 1)
    out["per_game"] = games
    print("\n  wrote", write(default_path("contest_ledger", SEED0), out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
