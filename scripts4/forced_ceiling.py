"""Is the forced declaration a coin flip because the information is gone, or
because we are not using what is left?

The declaration path ledger says all of our loss lives in two branches, and
the larger is `forced`: no legal ask exists, so a half-suit must be named.
Measured in self-play it fires 0.392 times a game and is wrong 51% of the
time, against 0.000 for the two paths that carry 92% of all declarations.

Two very different diagnoses fit that number and they call for opposite work.

  A. THE INFORMATION IS GONE. This is the reading that says a forced claim
     fires when every opponent is cardless: our team then holds every
     remaining card, no ask can carry a message, and the split among three
     teammates is whatever the record already implies. If the posterior's own
     best split carries 1/6 of the mass, being wrong five times in six is the
     correct price of a position lost earlier, and the lever is upstream --
     spend a turn signalling while someone still holds a card.

     That reading rests on a premise this file checks rather than assumes,
     because the premise is FALSE as usually stated. `GameState.legal_asks`
     returns nothing under a disjunction, not a single condition: our own hand
     is empty, OR every opponent is cardless, OR we hold no card of any live
     half-suit. A cardless player has no legal ask at ANY point in the game,
     so the forced bucket is not purely an endgame phenomenon and the
     "information is gone" argument does not cover all of it. Each row records
     which condition held.

  B. WE ARE NOT MAXIMISING OUR OWN POSTERIOR. If the best split carries most
     of the mass and we are still wrong half the time, the failure is in the
     policy or the posterior, and it is fixable where it happens.

The two are told apart by one number nobody has looked at: the posterior mass
on the split the engine NAMES, beside the mass on the split that was actually
TRUE. Both are computable at the moment of the declaration, and the true one
is available here because the runner can see the deal even though the seat
cannot.

    py scripts4/forced_ceiling.py [n_deals] [n_jobs] [--vs self|v07]
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
from fish.engine import ClaimEvent, GameState
from fish.observation import Observation
from fish.rules import RuleConfig

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 7_700_000
AGENT0 = 77_000


def _one(args) -> dict:
    deal_seed, kv_even, vs = args
    from fish4.registry4 import V06_DEPLOYED, make_agent
    from fish4.claim4 import ClaimConfig, ClaimEvaluator
    rules = RuleConfig(**RULES_D)
    agents = []
    for p in range(NUM_PLAYERS):
        ours = (p % 2 == 0) == kv_even
        if ours:
            agents.append(make_agent(("fishbot4",
                                      dict(V06_DEPLOYED[1], trace=True))))
        elif vs == "v07":
            agents.append(make_agent(("dylan_v07", {})))
        else:
            agents.append(make_agent(("fishbot4",
                                      dict(V06_DEPLOYED[1], trace=True))))
    st_ = GameState.deal(rules, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)

    # The evaluator is built per decision and thrown away, so the posterior it
    # used is only reachable from inside. Keep the last one each seat built.
    real = ClaimEvaluator.best_for_half_suit
    live = {}

    def spy(self, hs):
        r = real(self, hs)
        live[int(self.me)] = (self, hs, r)
        return r
    ClaimEvaluator.best_for_half_suit = spy

    rows = []
    try:
        for _ in range(600):
            if st_.is_terminal:
                break
            mover = st_.turn
            live.pop(mover, None)
            # the true holders, read before the claim resolves the set
            truth = {}
            for q in range(NUM_PLAYERS):
                h = st_.hands[q]
                while h:
                    b = h & -h
                    truth[b.bit_length() - 1] = q
                    h ^= b
            opp_cards = sum(bin(st_.hands[q]).count("1")
                            for q in range(NUM_PLAYERS)
                            if team_of(q) != team_of(mover))
            my_cards = bin(st_.hands[mover]).count("1")
            n_live = sum(1 for x in st_.set_winner if x is None)
            act = agents[mover].act(Observation.from_state(st_, mover))
            tr = getattr(agents[mover], "last_trace", None)
            ev = st_.apply(mover, act)
            if not isinstance(ev, ClaimEvent):
                continue
            why = (tr or {}).get("why", "") if (tr or {}).get(
                "kind") == "declare" else ""
            if "forced" not in why:
                continue
            got = live.get(mover)
            if not got:
                continue
            evaluator = got[0]
            cards = list(half_suit_cards(ev.half_suit))
            named = list(ev.declared)
            actual = [truth[c] for c in cards]
            try:
                p_named = float(evaluator.post.prob_assignment(cards, named))
                p_true = float(evaluator.post.prob_assignment(cards, actual))
            except Exception:
                continue
            # The question the two masses above only gesture at: was OUR pick
            # the best one available? At one live half-suit the team space is
            # 3^6 = 729 assignments, small enough to settle by enumeration
            # rather than by inference about the shortlist. Above that it is
            # left None rather than guessed.
            p_best, best_is_true, best_beats_ours = None, None, None
            if n_live == 1:
                team = [q for q in range(NUM_PLAYERS)
                        if team_of(q) == team_of(mover)]
                import itertools
                bp, ba = -1.0, None
                for cand in itertools.product(team, repeat=len(cards)):
                    v = float(evaluator.post.prob_assignment(cards,
                                                             list(cand)))
                    if v > bp:
                        bp, ba = v, list(cand)
                p_best = round(bp, 6)
                best_is_true = int(ba == actual)
                best_beats_ours = int(bp > p_named + 1e-9)
            rows.append({
                "hs": ev.half_suit, "live": n_live, "opp_cards": opp_cards,
                "my_cards": my_cards,
                # which arm of the disjunction closed the ask list
                "why_forced": ("hand empty" if my_cards == 0 else
                               "opponents cardless" if opp_cards == 0 else
                               "no card in any live half-suit"),
                "right": int(ev.winner == team_of(mover)),
                "p_named": round(p_named, 6), "p_true": round(p_true, 6),
                # a declaration that names the true split but is scored wrong
                # would be an engine bug; recorded so it cannot hide
                "named_is_true": int(named == actual),
                "p_best": p_best, "best_is_true": best_is_true,
                "best_beats_ours": best_beats_ours,
            })
    finally:
        ClaimEvaluator.best_for_half_suit = real
    return {"deal": deal_seed, "kv_even": kv_even, "forced": rows}


def report(rows: list[dict]) -> dict:
    flat = [c for r in rows for c in r["forced"]]
    g = len(rows)
    if not flat:
        print("no forced declarations in this block")
        return {"n_games": g, "n_forced": 0}
    right = [c for c in flat if c["right"]]
    wrong = [c for c in flat if not c["right"]]
    pn = [c["p_named"] for c in flat]
    pt = [c["p_true"] for c in flat]
    print(f"\n=== the forced declaration: is the information gone? ===")
    print(f"{g} games, {len(flat)} forced declarations "
          f"({len(flat)/g:.3f}/game), {len(wrong)} wrong "
          f"({len(wrong)/len(flat):.3f})")
    print(f"\n  posterior mass on the split we NAMED   "
          f"median {st.median(pn):.4f}  mean {sum(pn)/len(pn):.4f}")
    print(f"  posterior mass on the split that was TRUE "
          f"median {st.median(pt):.4f}  mean {sum(pt)/len(pt):.4f}")
    # If the truth routinely carries MORE mass than what we named, we are not
    # taking our own argmax and the loss is a policy bug, not an information
    # limit.
    beat = sum(1 for c in flat if c["p_true"] > c["p_named"] + 1e-9)
    print(f"\n  declarations where the TRUE split had more posterior mass "
          f"than ours: {beat}/{len(flat)} ({beat/len(flat):.3f})")
    if wrong:
        w = [c["p_named"] for c in wrong]
        print(f"  among the wrong ones, mass on what we named: "
              f"median {st.median(w):.4f}")
        wt = [c["p_true"] for c in wrong]
        print(f"  among the wrong ones, mass on the truth:     "
              f"median {st.median(wt):.4f}")
    by_live = {}
    for c in flat:
        b = by_live.setdefault(c["live"], [0, 0])
        b[0] += 1
        b[1] += 1 - c["right"]
    print(f"\n  by live half-suits at the moment of the claim:")
    for k in sorted(by_live):
        n, bad = by_live[k]
        print(f"    live={k}  n={n:<5} wrong {bad:<5} ({bad/n:.3f})")
    zero_opp = sum(1 for c in flat if c["opp_cards"] == 0)
    by_why = {}
    for c in flat:
        b = by_why.setdefault(c["why_forced"], [0, 0])
        b[0] += 1
        b[1] += 1 - c["right"]
    print(f"\n  why no ask was legal:")
    for k in sorted(by_why):
        n, bad = by_why[k]
        print(f"    {k:<32} n={n:<5} wrong {bad:<5} ({bad/n:.3f})")
    print(f"  forced with every opponent cardless: {zero_opp}/{len(flat)}")
    bug = sum(1 for c in flat if c["named_is_true"] and not c["right"])
    if bug:
        print(f"  *** {bug} declaration(s) named the true split and were "
              f"scored wrong; that is an engine bug, not a measurement")
    return {
        "n_games": g, "n_forced": len(flat),
        "per_game": round(len(flat) / g, 4),
        "err": round(len(wrong) / len(flat), 4),
        "p_named": {"median": round(st.median(pn), 6),
                    "mean": round(sum(pn) / len(pn), 6)},
        "p_true": {"median": round(st.median(pt), 6),
                   "mean": round(sum(pt) / len(pt), 6)},
        "truth_beats_ours": beat,
        "by_live": {str(k): {"n": v[0], "wrong": v[1]}
                    for k, v in sorted(by_live.items())},
        "all_opponents_cardless": zero_opp,
        "by_why_forced": {k: {"n": v[0], "wrong": v[1]}
                          for k, v in sorted(by_why.items())},
        "named_true_but_scored_wrong": bug,
    }


def main(n_deals=120, n_jobs=0, vs="self") -> int:
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
    jl = ROOT / "results" / f"forced_ceiling_{vs}.jsonl"
    with jl.open("w") as fh:
        for r in rows:
            for c in r["forced"]:
                fh.write(json.dumps(dict(c, deal=r["deal"],
                                         kv_even=r["kv_even"])) + "\n")
    print("wrote", jl.relative_to(ROOT))
    out = {"rules": RULES_D, "vs": vs, **report(rows)}
    dest = ROOT / "results" / f"forced_ceiling_{vs}.json"
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
    raise SystemExit(main(int(a[0]) if a else 120,
                          int(a[1]) if len(a) > 1 else 0, **kw))
