"""What the margin is made of once the declarations are netted out.

`scripts4/margin_decomposition.py` splits the head-to-head margin into
declaration accounting (61%) and a residual of +0.963 sets per game. The
residual is what asking, inference and search produce between them, and it has
never been broken down either.

It has a natural shape. Every set is won by declaring a half-suit your team
holds, so once misdeclarations are netted out what remains is the race to
ASSEMBLE half-suits. That race has exactly two factors and they multiply:

    volume      how many asks a team gets to make, which is turns
    conversion  how many of them land, which is inference

A team that asks twice as often at the same hit rate gains twice the cards; a
team that hits twice as often on the same turns does too. The published
head-to-head reports conversion (51.75% against 48.14%) and has never reported
volume, which is the half nobody looks at because it is not a skill anybody
names. This measures both, per game, paired.

Also recorded, because it is the thing the two factors are FOR: how many
half-suits each team came to hold outright, and how long it held them before
declaring. A team that assembles a set and sits on it has converted volume
into nothing.

    py scripts4/acquisition.py [n_deals] [n_jobs] [--vs v07|self]
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, half_suit_cards, team_of
from fish.engine import AskEvent, ClaimEvent, GameState, PassEvent
from fish.observation import Observation
from fish.rules import RuleConfig

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 9_900_000
AGENT0 = 99_000
NHS = 9


def _one(args) -> dict:
    deal_seed, kv_even, vs = args
    from fish4.registry4 import V06_DEPLOYED, make_agent
    rules = RuleConfig(**RULES_D)
    agents = []
    for p in range(NUM_PLAYERS):
        ours = (p % 2 == 0) == kv_even
        if ours or vs == "self":
            agents.append(make_agent(V06_DEPLOYED))
        else:
            agents.append(make_agent(("dylan_v07", {})))
    st_ = GameState.deal(rules, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
    us = 0 if kv_even else 1

    # [ours, theirs] for each counter
    asks = [0, 0]
    hits = [0, 0]
    turns = [0, 0]
    passes = [0, 0]
    #: plies a team held all six of a live half-suit without declaring it
    sat = [0, 0]
    #: half-suits a team ever held outright
    assembled = [set(), set()]
    #: per half-suit: plies OUR team sat on it fully assembled, and the ply we
    #: first assembled it. After that moment nothing can teach us its split
    #: except a deliberately failed ask -- an opponent cannot ask in a
    #: half-suit they hold no card of, so the only remaining channel costs a
    #: turn. Whether the eventual declaration was right is recorded beside it.
    hs_sat = [0] * NHS
    hs_first = [None] * NHS
    hs_out = {}
    ply = 0
    #: (ply, whose turn, how many cards the opponents still hold). The
    #: DEADLINE is the first ply at which they hold none: after it we have no
    #: legal ask, so the last chance to spend a turn on a signal has gone.
    #: `GameState.legal_asks` needs an opponent with cards, so this is not an
    #: interpretation of the rules, it is the rule.
    timeline = []
    for _ in range(600):
        if st_.is_terminal:
            break
        mover = st_.turn
        side = 0 if team_of(mover) == us else 1
        turns[side] += 1
        timeline.append((side, sum(bin(st_.hands[q]).count("1")
                                   for q in range(NUM_PLAYERS)
                                   if team_of(q) != us)))
        # who owns what, before the move
        for hs in range(NHS):
            if st_.set_winner[hs] is not None:
                continue
            owner = None
            for c in half_suit_cards(hs):
                h = next(q for q in range(NUM_PLAYERS) if st_.hands[q] >> c & 1)
                t = 0 if team_of(h) == us else 1
                if owner is None:
                    owner = t
                elif owner != t:
                    owner = -1
                    break
            if owner is not None and owner >= 0:
                assembled[owner].add(hs)
                sat[owner] += 1
                if owner == 0:
                    hs_sat[hs] += 1
                    if hs_first[hs] is None:
                        hs_first[hs] = ply
        ev = st_.apply(mover, agents[mover].act(
            Observation.from_state(st_, mover)))
        if isinstance(ev, AskEvent):
            asks[side] += 1
            hits[side] += int(ev.success)
        elif isinstance(ev, PassEvent):
            passes[side] += 1
        elif isinstance(ev, ClaimEvent) and team_of(ev.claimer) == us:
            hs_out[ev.half_suit] = {
                "sat": hs_sat[ev.half_suit],
                "first": hs_first[ev.half_suit],
                "ply": ply,
                "right": int(ev.winner == team_of(ev.claimer))}
        ply += 1
    ours_sets = sum(1 for w in st_.set_winner if w == us)
    theirs = sum(1 for w in st_.set_winner if w == 1 - us)
    # Where the deadline fell, and how many of OUR turns each half-suit had
    # between the moment we assembled it and that deadline. This is the
    # feasibility question for signalling: a set assembled two plies before
    # the deadline cannot be signalled by any policy, and one assembled with
    # ten of our turns left and still misdeclared is a policy failure.
    dead = next((i for i, (_, opp) in enumerate(timeline) if opp == 0),
                len(timeline))
    for v in hs_out.values():
        f = v["first"]
        v["turns_left"] = (0 if f is None else
                           sum(1 for i in range(f, dead)
                               if timeline[i][0] == 0))
        v["deadline"] = dead
    return {"deal": deal_seed, "kv_even": kv_even,
            "margin": ours_sets - theirs,
            "asks": asks, "hits": hits, "turns": turns, "passes": passes,
            "sat": sat, "assembled": [len(assembled[0]), len(assembled[1])],
            "deadline": dead, "plies": len(timeline),
            "hs": [dict(v, hs=k) for k, v in sorted(hs_out.items())]}


def report(rows) -> dict:
    g = len(rows)

    def per(key, i):
        return [r[key][i] for r in rows]

    def line(label, key):
        a, b = per(key, 0), per(key, 1)
        d = [x - y for x, y in zip(a, b)]
        m = sum(d) / g
        se = st.pstdev(d) / g ** 0.5
        print(f"  {label:<26}{sum(a)/g:>9.3f}{sum(b)/g:>9.3f}"
              f"{m:>+10.3f}   [{m-1.96*se:+.3f}, {m+1.96*se:+.3f}]")
        return {"ours": sum(a) / g, "theirs": sum(b) / g, "diff": m,
                "ci95": [m - 1.96 * se, m + 1.96 * se]}

    mar = [r["margin"] for r in rows]
    mm = sum(mar) / g
    mse = st.pstdev(mar) / g ** 0.5
    print(f"\n=== the acquisition race ({g:,} games) ===")
    print(f"  margin {mm:+.4f} [{mm-1.96*mse:+.4f}, {mm+1.96*mse:+.4f}] "
          f"sets/game\n")
    print(f"  {'per game':<26}{'ours':>9}{'theirs':>9}{'diff':>10}   95% CI")
    out = {"n_games": g, "margin": mm}
    for label, key in (("turns (VOLUME)", "turns"),
                       ("asks", "asks"),
                       ("asks that landed", "hits"),
                       ("passes", "passes"),
                       ("half-suits assembled", "assembled"),
                       ("plies sat on a full set", "sat")):
        out[key] = line(label, key)

    ha = sum(per("hits", 0)) / max(1, sum(per("asks", 0)))
    hb = sum(per("hits", 1)) / max(1, sum(per("asks", 1)))
    print(f"\n  CONVERSION: {ha:.4f} against {hb:.4f}  "
          f"({ha-hb:+.4f})")
    out["hit_rate"] = {"ours": ha, "theirs": hb, "diff": ha - hb}
    # Which factor carries the cards? Cards gained = asks * hit rate, so the
    # difference splits into a volume term and a conversion term at the mean.
    aa = sum(per("asks", 0)) / g
    ab = sum(per("asks", 1)) / g
    vol = (aa - ab) * ((ha + hb) / 2)
    conv = ((aa + ab) / 2) * (ha - hb)
    print(f"  cards gained per game: {aa*ha:.3f} against {ab*hb:.3f}")
    print(f"    attributable to VOLUME     (more asks)  {vol:+.3f}")
    print(f"    attributable to CONVERSION (better ask) {conv:+.3f}")
    out["decomposition"] = {"volume": vol, "conversion": conv,
                            "cards_ours": aa * ha, "cards_theirs": ab * hb}

    # Does sitting on a set predict getting it wrong? The channel argument
    # says it should: once our team holds all six, no opponent can ask in that
    # half-suit (they hold no card of it), so the only way its split can still
    # be learned is a deliberately failed ask that costs a turn. A set we
    # assembled early and never signalled in is one we are guessing at.
    hs = [c for r in rows for c in r["hs"]]
    if hs:
        print(f"\n  --- our declarations by how long we sat on the set ---")
        print(f"  {'plies assembled':<20}{'n':>7}{'wrong':>8}{'err':>9}")
        bands = [(0, 1), (1, 10), (10, 30), (30, 80), (80, 10 ** 9)]
        out["by_sat"] = {}
        for lo, hi in bands:
            sub = [c for c in hs if lo <= c["sat"] < hi]
            if not sub:
                continue
            w = sum(1 - c["right"] for c in sub)
            lab = f"{lo}" if hi - lo == 1 else f"{lo}-{hi-1}" if hi < 10 ** 9 \
                else f"{lo}+"
            print(f"  {lab:<20}{len(sub):>7}{w:>8}{w/len(sub):>9.4f}")
            out["by_sat"][lab] = {"n": len(sub), "wrong": w,
                                 "err": round(w / len(sub), 4)}
        wrong = [c for c in hs if not c["right"]]
        if wrong:
            tl = sorted(c["turns_left"] for c in wrong)
            print(f"\n  --- WAS THERE TIME? our turns between assembling a "
                  f"set and the deadline ---")
            print(f"  over the {len(wrong)} half-suits we declared WRONGLY: "
                  f"median {st.median(tl)}, "
                  f"min {tl[0]}, max {tl[-1]}")
            none = sum(1 for x in tl if x == 0)
            print(f"    assembled at or after the deadline (no turn to "
                  f"spend): {none}/{len(wrong)}")
            out["wrong_turns_left"] = {
                "n": len(wrong), "median": st.median(tl),
                "min": tl[0], "max": tl[-1], "no_turn": none}
        sat_w = [c["sat"] for c in hs if not c["right"]]
        sat_r = [c["sat"] for c in hs if c["right"]]
        if sat_w and sat_r:
            print(f"\n  median plies assembled: wrong {st.median(sat_w):.1f}, "
                  f"right {st.median(sat_r):.1f}")
            out["sat_median"] = {"wrong": st.median(sat_w),
                                 "right": st.median(sat_r)}
    return out


def main(n_deals=250, n_jobs=0, vs="v07") -> int:
    n_jobs = n_jobs or max(1, (os.cpu_count() or 2))
    todo = [(SEED0 + i, ke, vs) for i in range(n_deals) for ke in (True, False)]
    t0 = time.time()
    rows = []
    with Pool(n_jobs) as pool:
        for i, r in enumerate(pool.imap_unordered(_one, todo, chunksize=2)):
            rows.append(r)
            if (i + 1) % 50 == 0:
                print(f"  {i+1}/{len(todo)} {(time.time()-t0)/60:.1f} min",
                      flush=True)
    out = {"rules": RULES_D, "vs": vs, **report(rows)}
    dest = ROOT / "results" / f"acquisition_{vs}.json"
    dest.write_text(json.dumps(out, indent=1))
    print("\nwrote", dest.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    a = [x for x in argv if not x.startswith("--")]
    kw = {}
    for f in (x for x in argv if x.startswith("--")):
        k, _, v = f[2:].partition("=")
        if k != "vs":
            raise SystemExit(f"unknown flag --{k}")
        kw["vs"] = v
    raise SystemExit(main(int(a[0]) if a else 250,
                          int(a[1]) if len(a) > 1 else 0, **kw))
