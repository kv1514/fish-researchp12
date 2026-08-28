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
from fish.engine import AskEvent, ClaimEvent, GameState
from fish.observation import Observation
from fish.rules import RuleConfig

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 9_100_000
AGENT0 = 91_000
#: Below this, the run prints its report and writes no file. See main().
MIN_GAMES_TO_WRITE = 400

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
            # trace=True on BOTH sides in self-play. Without it the opposing
            # seats carry no trace, `why` is empty, and _path_of drops every
            # one of their declarations into "other" -- which is exactly what
            # the first 1,800-game run did: 8,078 declarations in "other"
            # against 8,078 across the four real paths, the two halves equal
            # to the card. A path ledger whose largest bucket is "unattributed"
            # is not a ledger, and it looked like a finding about self-play
            # rather than a missing keyword argument.
            agents.append(make_agent(("fishbot4",
                                      dict(V06_DEPLOYED[1], trace=True))))
    st = GameState.deal(rules, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
    our_team = 0 if kv_even else 1

    # The probability the engine ASSIGNED to the split it named, captured where
    # it is computed and thrown away.
    #
    # `forced_claim` already maximises p_exact across live half-suits, so the
    # lever there is not which suit it picks -- it is whether p_exact is
    # CALIBRATED. results/forced_ceiling_self.json found it overconfident in
    # the middle band: 94 declarations claiming 0.528 were right 0.362 of the
    # time. If that miscalibration is a function of how much of the half-suit
    # the declarer holds, the argmax systematically over-picks suits it knows
    # least about, and that is a defect with a direct fix.
    from fish4.claim4 import ClaimEvaluator
    real_bfh = ClaimEvaluator.best_for_half_suit
    priced = {}

    def spy(self, hs):
        r = real_bfh(self, hs)
        if r is not None:
            priced[(int(self.me), int(hs))] = (float(r[0]), float(r[1]))
        return r
    ClaimEvaluator.best_for_half_suit = spy

    # Cards the public record has actually touched.
    #
    # This is the variable the k-curve pointed at. The error rate RISES with
    # the declarer's own holding, which is selection: holding one card you only
    # declare when the other five are pinned, while holding five leaves exactly
    # one card that may never have moved and is then a coin flip between two
    # teammates. If that story is right, "how many of these six have never been
    # publicly located" should predict the error better than k does, and the
    # k-effect should largely vanish once it is held fixed.
    #
    # `taken` is the strong notion: a successful ask publicly LOCATES a card in
    # the asker's hand. `asked` is the weak one: a failed ask proves only that
    # the target does not hold it, which constrains without locating.
    taken, asked = set(), set()
    # Who a successful ask last put each card with. After a half-suit freezes
    # nothing in it moves (you cannot ask a teammate), so for any card ever
    # taken this IS its public current location.
    last_taken = {}

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
        if isinstance(ev, AskEvent):
            asked.add(ev.card)
            if ev.success:
                taken.add(ev.card)
                last_taken[ev.card] = ev.asker
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
            "p_exact": (priced.get((mover, hs)) or (None, None))[0],
            "p_team": (priced.get((mover, hs)) or (None, None))[1],
            "n_unmoved": sum(1 for c in range(hs * 6, hs * 6 + 6)
                             if c not in taken),
            "n_unasked": sum(1 for c in range(hs * 6, hs * 6 + 6)
                             if c not in asked),
            # WHAT THE PROPAGATOR DERIVED, over and above the declarer's own
            # hand and the cards a successful ask publicly located.
            #
            # This is the quantity behind a claim I got wrong: that once a team
            # holds all six "nothing further can inform the split". No further
            # ask can NAME one of those cards, true -- but fish/beliefs.py
            # keeps propagating. Public hand counts exclude a player whose
            # quota hits zero from every unresolved card and pin cards to a
            # player whose quota equals what they could still hold, and failed
            # asks exclude too. All of that accrues while a set sits.
            #
            # `derived` counts the cards pinned to a specific player that were
            # neither in the declarer's hand nor publicly located by an ask. It
            # is what waiting actually bought, per declaration.
            **_derived(agents[mover], hs, pre[mover], last_taken),
        })
    ClaimEvaluator.best_for_half_suit = real_bfh
    ours_sets = sum(1 for w in st.set_winner if w == our_team)
    return {"deal": deal_seed, "kv_even": kv_even,
            "margin": 2 * ours_sets - 9, "claims": rows}


def _derived(agent, hs, own_mask, last_taken) -> dict:
    """Cards the propagator pinned beyond the hand and the public record."""
    bel = getattr(agent, "bel", None)
    if bel is None:
        return {"n_pinned": None, "n_derived": None}
    pinned = free_known = 0
    for c in range(hs * 6, hs * 6 + 6):
        try:
            m = bel.current_holder_mask(c)
        except Exception:
            return {"n_pinned": None, "n_derived": None}
        if m and not (m & (m - 1)):
            pinned += 1
            if not (own_mask >> c & 1) and c not in last_taken:
                free_known += 1
    return {"n_pinned": pinned, "n_derived": free_known}


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

    med = [c for c in whole if c.get("n_unmoved") is not None]
    if med:
        print(f"\n  the mediator: how many of the six have never been "
              f"publicly LOCATED\n  (never taken by a successful ask)")
        print(f"  {'unmoved':>8} {'n':>7} {'wrong':>7} {'err':>8}")
        for u in sorted({c["n_unmoved"] for c in med}):
            g = [c for c in med if c["n_unmoved"] == u]
            w = sum(1 - c["right"] for c in g)
            print(f"  {u:>8} {len(g):>7} {w:>7} {_rate(len(g), w):>8.3f}")
        print(f"\n  and the k-effect HELD AT FIXED unmoved. If the k-curve is"
              f"\n  selection on this variable, the rows should flatten.")
        print(f"  {'unmoved':>8} " + " ".join(f"{'k=' + str(k):>9}"
                                              for k in range(7)))
        strat = {}
        for u in sorted({c["n_unmoved"] for c in med}):
            cells, row = [], {}
            for k in range(7):
                g = [c for c in med if c["n_unmoved"] == u and c["k"] == k]
                if len(g) < 25:
                    cells.append(f"{'-':>9}")
                    continue
                w = sum(1 - c["right"] for c in g)
                cells.append(f"{_rate(len(g), w):>9.3f}")
                row[str(k)] = {"n": len(g), "wrong": w,
                               "err": _rate(len(g), w)}
            print(f"  {u:>8} " + " ".join(cells))
            if row:
                strat[str(u)] = row
        print("  (cells with fewer than 25 declarations are left blank rather"
              "\n  than printed as a rate over a handful)")
    else:
        strat = {}

    dv = [c for c in whole if c.get("n_derived") is not None]
    if dv:
        tot = len(dv)
        any_d = sum(1 for c in dv if c["n_derived"] > 0)
        print(f"\n  what waiting actually bought: cards pinned beyond the "
              f"declarer's\n  own hand and the public record "
              f"({tot:,} wholly-held declarations)")
        print(f"  {'derived':>8} {'n':>7} {'share':>8} {'wrong':>7} {'err':>8}")
        for d in sorted({c["n_derived"] for c in dv}):
            g = [c for c in dv if c["n_derived"] == d]
            w = sum(1 - c["right"] for c in g)
            print(f"  {d:>8} {len(g):>7} {len(g)/tot:>8.1%} {w:>7} "
                  f"{_rate(len(g), w):>8.3f}")
        print(f"\n  at least one card derived: {any_d:,} of {tot:,} "
              f"({any_d/tot:.1%})")
        print("  A claim I made and had to retract was that once a team holds")
        print("  all six, nothing further can inform the split. No further ASK")
        print("  can name those cards; the propagator keeps working. This row")
        print("  is how often that mattered.")
    else:
        any_d = 0

    cal = [c for c in whole if c["p_exact"] is not None]
    if cal:
        print(f"\n  is p_exact calibrated, and does that depend on how much "
              f"the\n  declarer holds? ({len(cal):,} wholly-held "
              f"declarations that were priced)")
        print(f"  {'k':>3} {'n':>7} {'claimed':>9} {'observed':>9} {'gap':>8}")
        cal_out = {}
        for k in sorted({c["k"] for c in cal}):
            g = [c for c in cal if c["k"] == k]
            claimed = sum(c["p_exact"] for c in g) / len(g)
            obs = sum(c["right"] for c in g) / len(g)
            print(f"  {k:>3} {len(g):>7} {claimed:>9.3f} {obs:>9.3f} "
                  f"{obs - claimed:>+8.3f}")
            cal_out[str(k)] = {"n": len(g), "claimed": claimed,
                               "observed": obs, "gap": obs - claimed}
        print("  A negative gap is overconfidence. forced_claim takes the "
              "argmax of\n  p_exact, so a gap that VARIES with k means the "
              "argmax is biased toward\n  the half-suits the declarer knows "
              "least about.")
    else:
        cal_out = {}

    return {"vs": vs, "n_games": len(games), "calibration_by_k": cal_out,
            "declarations_with_a_derived_card": any_d,
            "err_by_unmoved": {
                str(u): {"n": len([c for c in med if c["n_unmoved"] == u]),
                         "wrong": sum(1 - c["right"] for c in med
                                      if c["n_unmoved"] == u)}
                for u in sorted({c["n_unmoved"] for c in med})} if med else {},
            "err_by_unmoved_and_k": strat,
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
    # A smoke run must not overwrite a real one. This script writes to a fixed
    # path, and an 8-game check of the instrumentation duly replaced an
    # 1,800-game result with eight games of noise -- the same failure the
    # confirm runners had when a scratch journal wrote into results/, arriving
    # by a different route. The report is still printed; only the file is
    # withheld, so a small run stays useful for what small runs are for.
    dest = ROOT / "results" / f"declarer_holding_{vs}.json"
    if len(games) < MIN_GAMES_TO_WRITE:
        print(f"\n{len(games)} games is below the {MIN_GAMES_TO_WRITE}-game "
              f"floor for writing {dest.name}.\nReport above is complete; the "
              f"file is left alone.")
        return 0
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
