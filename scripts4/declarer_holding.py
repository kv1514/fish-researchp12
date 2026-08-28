"""Who declares matters: does the declarer's own holding predict the split?

WHY THIS QUESTION. `results/margin_decomposition.json` over 10,000 games puts
our wrong declarations at 0.1759 a game, of which 0.1676 are ALLOCATION class
-- our own team held all six and we named the wrong split. That is 95.3% of
everything we get wrong. We essentially never claim a half-suit an opponent
still holds; what we cannot do is say which of our own teammates has what.

That reframes the problem. An allocation error is not an inference failure
against a hidden opponent. Every card is held by someone who knows they hold
it, so the TEAM has the answer and no member of it does. It is a distributed
knowledge problem, and the game provides almost no channel to solve it: once
our team holds all six, `GameState.legal_asks` bars every opponent from asking
there, so no further public event can ever touch the half-suit. The split is
frozen at the moment the last card arrives.

There is one lever that costs nothing in information, and nobody has priced
it. A declaration may be made by any member of the team, on their own turn
(`claims_any_time` is false, so it must be their turn). The teammate holding
FOUR cards of a frozen half-suit has to guess two; the teammate holding one
has to guess five. If the error rate falls steeply with the declarer's own
holding, then "let the best-placed teammate declare" is worth something, and
because the channel is frozen, waiting for their turn costs tempo and no
information at all -- and a turn is measurably free below p_best = 0.50
(paper, sec:tempo).

WHAT THIS MEASURES, AND WHAT IT DOES NOT. This is observational. It reads the
true hands from the game state at the moment of the declaration, which the
agents never see, and reports the error rate by the declarer's own holding.
The "if the best-placed teammate had declared" line is a BOUND obtained by
reading the same curve at a different point, and it is not causal: positions
where somebody holds four cards of a half-suit may be easier for reasons that
have nothing to do with who declares. Nothing ships on it. It exists to decide
whether the intervention is worth pre-registering.

    py scripts4/declarer_holding.py [n_deals] [n_jobs] [--vs v07|self]
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, half_suit_mask, team_of
from fish.engine import ClaimEvent, GameState
from fish.observation import Observation
from fish.rules import RuleConfig

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 9_100_000
AGENT0 = 91_000

PATHS = {"exact": "exact", "voluntary": "voluntary",
         "gate": "cannot land", "forced": "forced"}


def _path_of(why: str) -> str:
    for name, needle in PATHS.items():
        if needle in why:
            return name
    return "other"


def _one(args) -> dict:
    deal_seed, kv_even, vs = args
    from fish4.registry4 import V06_DEPLOYED, make_agent

    params = dict(V06_DEPLOYED[1], trace=True)
    rules = RuleConfig(**RULES_D)
    agents = []
    for p in range(NUM_PLAYERS):
        ours = (p % 2 == 0) == kv_even
        if ours:
            agents.append(make_agent(("fishbot4", params)))
        elif vs == "v07":
            agents.append(make_agent(("dylan_v07", {})))
        else:
            agents.append(make_agent(("fishbot4", dict(V06_DEPLOYED[1]))))
    st = GameState.deal(rules, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
    our_team = 0 if kv_even else 1

    rows = []
    for _ in range(600):
        if st.is_terminal:
            break
        mover = st.turn
        act = agents[mover].act(Observation.from_state(st, mover))
        tr = getattr(agents[mover], "last_trace", None)
        # The hands BEFORE the claim resolves them away. Read from the engine,
        # never handed to an agent: this is the analyst's view, and it is the
        # only way to ask a counterfactual about who should have declared.
        hs = getattr(act, "half_suit", None)
        pre = list(st.hands) if hs is not None else None
        ev = st.apply(mover, act)
        if not isinstance(ev, ClaimEvent) or pre is None:
            continue
        team = team_of(mover)
        mask = half_suit_mask(hs)
        mine = [p for p in range(NUM_PLAYERS) if team_of(p) == team]
        held = {p: (pre[p] & mask).bit_count() for p in mine}
        k_team = sum(held.values())
        k_best = max(held.values())
        kind = (tr or {}).get("kind", "")
        why = "exact" if kind == "exact" else (
            (tr or {}).get("why", "") if kind == "declare" else "")
        rows.append({
            "path": _path_of(why),
            "ours": int(team == our_team),
            "right": int(ev.winner == team),
            "k": held[mover],            # the declarer's own cards of it
            "k_best": k_best,            # the best-placed teammate's
            "k_team": k_team,            # 6 == wholly held, so allocation-only
            "is_best": int(held[mover] == k_best),
            "holders": sum(1 for v in held.values() if v),
            "live": sum(1 for x in st.set_winner if x is None),
        })
    ours_sets = sum(1 for w in st.set_winner if w == our_team)
    return {"deal": deal_seed, "kv_even": kv_even,
            "margin": 2 * ours_sets - 9, "claims": rows}


def _rate(n, wrong):
    return wrong / n if n else 0.0


def report(games, vs) -> dict:
    # In self-play BOTH teams are our engine, so both sides' declarations are
    # evidence about our own declaration machinery and halving the corpus
    # would be throwing away data for a distinction that does not exist there.
    # Against v0.7 only our seats count -- the bridged engine's declarations
    # are not what this is measuring, and its holdings are not ours to reason
    # about.
    claims = [c for g in games for c in g["claims"]
              if vs == "self" or c["ours"]]
    whole = [c for c in claims if c["k_team"] == 6]
    print(f"\n=== who declares, and what it is worth ({len(games):,} games "
          f"vs {vs}) ===")
    print(f"{len(claims):,} declarations by our team, of which {len(whole):,} "
          f"were of half-suits\nour team wholly held -- the only ones where "
          f"the split is the only thing that\ncan go wrong.\n")

    by_k = defaultdict(lambda: [0, 0])
    for c in whole:
        b = by_k[c["k"]]
        b[0] += 1
        b[1] += 1 - c["right"]
    print("  the declarer's own cards of the half-suit they declared")
    print(f"  {'k':>3} {'n':>7} {'wrong':>7} {'err':>8}")
    curve = {}
    for k in sorted(by_k):
        n, w = by_k[k]
        curve[k] = _rate(n, w)
        print(f"  {k:>3} {n:>7} {w:>7} {curve[k]:>8.3f}")

    nb = [c for c in whole if not c["is_best"]]
    print(f"\n  declarations where a teammate held MORE of it than the "
          f"declarer: {len(nb):,}"
          f"  ({_rate(len(whole), len(nb)):.1%} of them)")
    if nb:
        w_nb = sum(1 - c["right"] for c in nb)
        b = [c for c in whole if c["is_best"]]
        w_b = sum(1 - c["right"] for c in b)
        print(f"    declarer was best placed   n={len(b):>6} "
              f"err {_rate(len(b), w_b):.3f}")
        print(f"    a teammate was better      n={len(nb):>6} "
              f"err {_rate(len(nb), w_nb):.3f}")
        # The bound. Read the SAME curve at k_best for the declarations where
        # the declarer was not the best placed. Not causal, and labelled so.
        pred = sum(curve.get(c["k_best"], _rate(len(nb), w_nb)) for c in nb)
        now = w_nb
        print(f"\n  BOUND, not an effect: reading the error curve at k_best "
              f"for those\n  {len(nb):,} declarations predicts {pred:.1f} "
              f"wrong against {now} observed,")
        saved = (now - pred) / len(games)
        print(f"  a difference of {saved:+.4f} wrong declarations per game.")
        print("  At the measured +1.79 sets an avoided error "
              "(results/error_value.json)\n"
              f"  that is worth about {saved * 1.7898:+.3f} sets/game IF the "
              "curve is causal,\n  which is exactly what this run cannot "
              "establish. Positions where a\n  teammate holds four may be "
              "easier for reasons unrelated to who speaks.")
    else:
        saved = 0.0

    by_path = defaultdict(lambda: [0, 0])
    for c in whole:
        b = by_path[c["path"]]
        b[0] += 1
        b[1] += 1 - c["right"]
    print(f"\n  wholly-held declarations by path")
    print(f"  {'path':<11}{'n':>7}{'wrong':>7}{'err':>8}{'mean k':>8}"
          f"{'mean k_best':>13}")
    for p in sorted(by_path):
        n, w = by_path[p]
        ks = [c["k"] for c in whole if c["path"] == p]
        kb = [c["k_best"] for c in whole if c["path"] == p]
        print(f"  {p:<11}{n:>7}{w:>7}{_rate(n, w):>8.3f}"
              f"{sum(ks)/len(ks):>8.2f}{sum(kb)/len(kb):>13.2f}")

    return {"vs": vs, "n_games": len(games),
            "n_claims_ours": len(claims), "n_wholly_held": len(whole),
            "err_by_k": {str(k): {"n": by_k[k][0], "wrong": by_k[k][1],
                                  "err": curve[k]} for k in sorted(by_k)},
            "not_best_placed": len(nb),
            "bound_wrong_per_game_saved": saved,
            "by_path": {p: {"n": by_path[p][0], "wrong": by_path[p][1],
                            "err": _rate(*by_path[p])} for p in by_path}}


def main(n_deals=200, n_jobs=0, vs="v07") -> int:
    n_jobs = n_jobs or max(1, (os.cpu_count() or 2) - 1)
    todo = [(SEED0 + i, ke, vs) for i in range(n_deals) for ke in (True, False)]
    print(f"{len(todo):,} games on {n_jobs} workers", flush=True)
    t0 = time.time()
    games = []
    with Pool(n_jobs) as pool:
        for i, g in enumerate(pool.imap_unordered(_one, todo, chunksize=2)):
            games.append(g)
            if (i + 1) % 50 == 0:
                print(f"  {i+1:,}/{len(todo):,}  "
                      f"{(time.time()-t0)/60:.1f} min", flush=True)
    out = report(games, vs)
    dest = ROOT / "results" / f"declarer_holding_{vs}.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"\nwrote results/{dest.name}")
    return 0


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    vs = "self"
    for x in sys.argv[1:]:
        if x.startswith("--vs"):
            vs = x.split("=", 1)[1] if "=" in x else "v07"
    raise SystemExit(main(int(a[0]) if a else 200,
                          int(a[1]) if len(a) > 1 else 0, vs))
