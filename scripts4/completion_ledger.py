"""Why does SESTINA complete 4.80 half-suits a game where KRAKEN completes 3.96?

THE QUESTION, AND WHY IT IS THE ONE THAT MATTERS

`scripts4/margin_identity.py --base=persistent results/bridge_dealt_hand_price.json`
decomposes our BRIDGE_REV 3 deficit exactly:

    margin -0.8733  =  RACE -0.8000  +  OURS -0.2767  +  THEIRS +0.2033

and `fish/engine.py:327` says what RACE can and cannot be. `_apply_claim`
awards a half-suit to the declaring team only on an exact match, and to the
OPPONENTS whenever any revealed holder is on the other team. A team that does
not hold all six cannot take a half-suit by declaring it. The counters agree:
8.7600 of the nine half-suits a game are collected outright and declared
correctly, only 0.2400 declarations involve any error at all, and their
ownership errors -- the only genuinely contested case -- run at 0.0233.

So RACE is not a declaration-timing channel. It is a CARD COLLECTION channel:
they complete 4.7983 half-suits a game and we complete 3.9617, and the
declaration that follows is a formality. That is the ask channel, which is
where `prereg/kraken_v12_vs_sestina.md` aimed, and this file does not dispute
the aim. It disputes the METRIC.

That programme scored the ask channel by ASK HIT RATE -- 52.5% against 54.9%
in its own table -- and the record already shows hit rate and completion
coming apart. Three arms raised the hit rate by about a point: P44's D1 and
P45's F1 each lost about a third of a set, and P46's G was the first not to
lose. A point of hit rate has never once bought a set, and no arm in this
study has ever been scored on half-suits COMPLETED, which is the quantity the
margin is actually made of.

WHAT THIS SEPARATES, fixed before the run

  tempo          they complete more because they act more, at a similar
                 asks-per-completion. The lever is turn retention, the hit
                 rate was the right proxy, and it was measured against the
                 wrong margin.
  concentration  they complete more per ask, at similar action counts. The
                 lever is WHICH half-suit an ask is spent on; the hit rate is
                 then actively misleading, because a hit in a half-suit the
                 team never completes is a wasted hit that scores as a
                 success.

`wasted` is the column that decides it, and it is a fact about the finished
game rather than a model: a successful ask in half-suit h by team t is wasted
if t never went on to win h by a correct declaration. Every card it gathered
ended up somewhere else.

PREDICTION, RECORDED BEFORE THE RUN: concentration. Three arms raised the hit
rate without buying a set, which is hard to reconcile with tempo binding.

SHIPS NOTHING. This is a diagnostic, it plays the champion unchanged, and its
only output is a description of two engines' finished games.

    py scripts4/completion_ledger.py [--deals N] [--jobs J]
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
#: A fresh block. 8,600,000 is bridge_dealt_hand_price's and re-using it would
#: describe the same games the decomposition was read off.
SEED0 = 12_500_000
AGENT0 = 125_000
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
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
    kv_team = 0 if kv_even else 1
    side_of = {kv_team: "kv", 1 - kv_team: "dy"}
    # Plies spent holding a completed half-suit without declaring it. The
    # paper's acquisition table carries this column, and it is the only one
    # here that is about TIMING rather than collection -- so it is where a
    # declaration-side effect would show if there were one to show.
    unspoken = {0: 0, 1: 0}
    for _ in range(MAX_ACTIONS):
        if st.is_terminal:
            break
        st.apply(st.turn, agents[st.turn].act(
            Observation.from_state(st, st.turn)))
        for hs in range(9):
            if st.set_winner[hs] is not None:
                continue
            m = 0
            for c in range(hs * 6, hs * 6 + 6):
                for pl in range(6):
                    if st.hands[pl] >> c & 1:
                        m |= 1 << pl
                        break
            # wholly held by ONE team: some seats set, none on the other side
            if m and not ((m & 0b010101) and (m & 0b101010)):
                unspoken[0 if m & 0b010101 else 1] += 1
    row = {"deal": deal_seed, "kv_even": kv_even,
           "terminal": st.is_terminal,
           "fallbacks": sum(getattr(a, "fallbacks", 0) for a in agents)}
    for s in SIDES:
        row[s] = {"acts": 0, "turns": 0, "asks": 0, "hits": 0,
                  "completed": 0, "hits_kept": 0, "hits_wasted": 0,
                  "unspoken": 0}
    for _t, _v in unspoken.items():
        row[side_of[_t]]["unspoken"] = _v

    # Who eventually won each half-suit, and by whose declaration. A team
    # "completed" a half-suit when its own declaration was correct; a half-suit
    # won because the OTHER team declared it wrongly is a gift, not a
    # completion, and is counted separately so the two are never conflated.
    won_by_own_claim = {}
    for e in st.history:
        if isinstance(e, ClaimEvent) and e.winner == team_of(e.claimer):
            won_by_own_claim[e.half_suit] = e.winner

    prev = None
    for e in st.history:
        actor = e.claimer if isinstance(e, ClaimEvent) else (
            e.asker if isinstance(e, AskEvent) else e.player)
        t = team_of(actor)
        s = side_of[t]
        row[s]["acts"] += 1
        # A turn ACQUISITION: this team acting when the last actor was not on
        # it. Counting actions alone would score a long successful run as many
        # turns, and counting turn changes alone would miss that a run is what
        # a turn is FOR.
        if prev is None or team_of(prev) != t:
            row[s]["turns"] += 1
        prev = actor
        if isinstance(e, AskEvent):
            row[s]["asks"] += 1
            if e.success:
                row[s]["hits"] += 1
                hs = e.card // 6
                if won_by_own_claim.get(hs) == t:
                    row[s]["hits_kept"] += 1
                else:
                    row[s]["hits_wasted"] += 1
        elif isinstance(e, ClaimEvent) and e.winner == t:
            row[s]["completed"] += 1
    return row


def _mean_ci(xs):
    m = sum(xs) / len(xs)
    se = (statistics.stdev(xs) / len(xs) ** 0.5) if len(xs) > 1 else 0.0
    return m, m - 1.96 * se, m + 1.96 * se


def report(rows: list[dict]) -> dict:
    n = len(rows)
    out = {"script": "scripts4/completion_ledger.py", "descriptive": True,
           "rules": RULES_D, "seed_deal": SEED0, "seed_agent": AGENT0,
           "n_games": n, "bridge_rev": 3, "transport": "persistent",
           "fallbacks": sum(r["fallbacks"] for r in rows),
           "unfinished": sum(1 for r in rows if not r["terminal"]),
           "sides": {}}
    keys = ("acts", "turns", "asks", "hits", "completed",
            "hits_kept", "hits_wasted", "unspoken")
    for s in SIDES:
        d = {k: sum(r[s][k] for r in rows) / n for k in keys}
        d["hit_rate"] = d["hits"] / d["asks"] if d["asks"] else 0.0
        d["asks_per_completion"] = (d["asks"] / d["completed"]
                                    if d["completed"] else float("nan"))
        d["hits_per_completion"] = (d["hits"] / d["completed"]
                                    if d["completed"] else float("nan"))
        d["wasted_share"] = d["hits_wasted"] / d["hits"] if d["hits"] else 0.0
        out["sides"][s] = d
    # Paired within the deal, because the two sides played the same cards.
    out["paired"] = {}
    for k in keys + ("hit_rate", "asks_per_completion", "wasted_share"):
        def val(r, s, k=k):
            v = r[s]
            if k == "hit_rate":
                return v["hits"] / v["asks"] if v["asks"] else 0.0
            if k == "asks_per_completion":
                return v["asks"] / v["completed"] if v["completed"] else None
            if k == "wasted_share":
                return v["hits_wasted"] / v["hits"] if v["hits"] else 0.0
            return v[k]
        d = [a - b for a, b in
             ((val(r, "kv"), val(r, "dy")) for r in rows)
             if a is not None and b is not None]
        m, lo, hi = _mean_ci(d)
        out["paired"][k] = {"mean": m, "ci95": [lo, hi], "n": len(d)}

    kv, dy = out["sides"]["kv"], out["sides"]["dy"]
    print("\n" + "=" * 74)
    print("  WHERE THE COLLECTION DEFICIT COMES FROM")
    print(f"  {n:,} games, BRIDGE_REV 3 persistent, "
          f"{out['fallbacks']} fallbacks, {out['unfinished']} unfinished")
    print("=" * 74)
    print(f"\n  {'':<22}{'KRAKEN':>10}{'SESTINA':>10}{'ours - theirs':>24}")
    for k, label in (("completed", "half-suits completed"),
                     ("turns", "turn acquisitions"),
                     ("acts", "actions"),
                     ("asks", "asks"),
                     ("hits", "asks that hit"),
                     ("hit_rate", "hit rate"),
                     ("hits_kept", "hits it kept"),
                     ("hits_wasted", "hits WASTED"),
                     ("wasted_share", "wasted share of hits"),
                     ("asks_per_completion", "asks per completion"),
                     ("unspoken", "plies sitting on a set")):
        p = out["paired"].get(k)
        tail = (f"{p['mean']:+.4f} [{p['ci95'][0]:+.4f}, {p['ci95'][1]:+.4f}]"
                if p else "")
        print(f"  {label:<22}{kv[k]:>10.4f}{dy[k]:>10.4f}{tail:>24}")

    print("\n  TEMPO would show as a turn/action deficit at a similar")
    print("  asks-per-completion. CONCENTRATION shows as a similar action")
    print("  count with more of our hits wasted -- cards gathered into")
    print("  half-suits we never finish, each of which scores as a")
    print("  successful ask and as nothing else.")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--deals", type=int, default=150)
    ap.add_argument("--seed", type=int, default=SEED0)
    ap.add_argument("--jobs", type=int, default=3)
    a = ap.parse_args(argv)
    todo = [(a.seed + i, ke) for i in range(a.deals) for ke in (True, False)]
    print(f"{len(todo):,} games on {a.jobs} workers", flush=True)
    rows, t0 = [], time.time()
    with Pool(a.jobs) as pool:
        for i, r in enumerate(pool.imap_unordered(_one, todo, chunksize=1)):
            rows.append(r)
            if (i + 1) % 40 == 0:
                print(f"  {i + 1}/{len(todo)}, "
                      f"{(time.time() - t0) / 60:.1f} min", flush=True)
    if len(rows) < 30:
        print("too few games", file=sys.stderr)
        return 1
    out = report(rows)
    out["seconds"] = round(time.time() - t0, 1)
    out["per_game"] = rows
    print("\n  wrote", write(default_path("completion_ledger", SEED0), out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
