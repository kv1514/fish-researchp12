"""How much of our misdeclaration bill is a TEAM-COORDINATION loss?

Combines the two instruments:
  * the trace ``why`` (which gate in ``fish4/agent4.py::act`` produced the
    declaration), and
  * six shadow BeliefStates, one per seat, fed only that seat's Observation,
    so "seat t could pin this split" is a deduction any player could make.

For every declaration OUR side makes it records whether the declarer had the
split pinned, whether any TEAMMATE did, and -- the part that decides whether a
deferral is even available -- whether that teammate is ever on move again
before the game ends.

    py scripts4/defer_bound.py [n_deals] [n_jobs] [out.jsonl]
"""
from __future__ import annotations

import json, os, sys, time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.beliefs import BeliefState
from fish.cards import half_suit_cards, team_of
from fish.engine import ClaimEvent, GameState
from fish.observation import Observation
from fish.rules import RuleConfig

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 900_000
AGENT0 = 9000
NHS = 9


def _pins(bel, hs, seat) -> bool:
    my = team_of(seat)
    for c in half_suit_cards(hs):
        m = bel.current_holder_mask(c)
        if m == 0 or (m & (m - 1)):
            return False
        if team_of(m.bit_length() - 1) != my:
            return False
    return True


def _one(args) -> dict:
    deal_seed, kv_even = args
    from fish4.registry4 import V06_DEPLOYED, make_agent
    rules = RuleConfig(**RULES_D)
    name, kw = V06_DEPLOYED
    agents = []
    for p in range(6):
        kv = (p % 2 == 0) == kv_even
        agents.append(make_agent((name, dict(kw, trace=True))) if kv
                      else make_agent(("dylan_v07", {})))
    st = GameState.deal(rules, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
    shadow = [BeliefState(rules, observer=p) for p in range(6)]
    kv_team = 0 if kv_even else 1
    pinned_by = [[None] * 6 for _ in range(NHS)]   # first ply seat pinned hs
    movers, decls = [], []
    ply = 0
    for _ in range(600):
        if st.is_terminal:
            break
        mover = st.turn
        movers.append(mover)
        kv_side = team_of(mover) == kv_team
        for p in range(6):
            shadow[p].update(Observation.from_state(st, p))
        for hs in range(NHS):
            if st.set_winner[hs] is not None:
                continue
            for p in range(6):
                if pinned_by[hs][p] is None and _pins(shadow[p], hs, p):
                    pinned_by[hs][p] = ply
        counts = list(st.hand_counts())
        hand_before = st.hands[mover]
        act = agents[mover].act(Observation.from_state(st, mover))
        tr = getattr(agents[mover], "last_trace", None) if kv_side else None
        ev = st.apply(mover, act)
        if isinstance(ev, ClaimEvent) and kv_side:
            ct = team_of(ev.claimer)
            #: cards of the declared half-suit the DECLARER holds that are not
            #: publicly located. If this is zero, every card of the half-suit
            #: is either public or in a teammate's hand, so exactly one seat --
            #: whichever teammate holds all the non-public ones -- can pin the
            #: split, and the declarer can compute the probability of that from
            #: its own posterior. If it is nonzero, no teammate can pin it and
            #: the declarer is by construction the best-informed seat.
            hidden_mine = 0
            for c in half_suit_cards(ev.half_suit):
                loc = shadow[ev.claimer].public_loc[c]
                if (loc is None or loc == -1) and (hand_before >> c & 1):
                    hidden_mine += 1
            mates = [p for p in range(6)
                     if team_of(p) == ct and p != ev.claimer]
            decls.append({
                "ply": ply, "hs": ev.half_suit, "claimer": ev.claimer,
                "ok": int(ev.winner == ct),
                "own_class": int(all(team_of(h) == ct for h in ev.revealed)),
                "why": (tr or {}).get("why"), "kind": (tr or {}).get("kind"),
                "conf": (tr or {}).get("confidence"),
                "declarer_pinned": pinned_by[ev.half_suit][ev.claimer],
                "mates_pinned": [pinned_by[ev.half_suit][m] for m in mates],
                "mates": mates,
                "opp_cards": sum(counts[o] for o in range(6)
                                 if team_of(o) != ct),
                "my_cards": counts[ev.claimer],
                "hidden_mine": hidden_mine,
                #: Cards of the declared half-suit in the declarer's OWN hand
                #: at the moment of declaring. Zero is an ANCHORLESS
                #: declaration: the declarer names six owners in a half-suit it
                #: holds nothing of, purely from deduction.
                #:
                #: (A subagent's version of this comment added "so the declarer
                #: stays on move and declares again rather than passing". That
                #: is true but not distinctive: fish/engine.py:_apply_claim
                #: never touches self.turn, so the declarer keeps the move after
                #: ANY declaration. What is actually particular to the
                #: anchorless case is narrower -- it removes none of the
                #: declarer's own cards, so it can never be the declaration
                #: that empties a hand and forces a pass.)
                "my_in_hs": sum(1 for c in half_suit_cards(ev.half_suit)
                                if hand_before >> c & 1),
                "mate_cards": [counts[m] for m in mates],
                "live": sum(1 for x in st.set_winner if x is None) + 1,
                #: how many claimable half-suits the declarer had to choose
                #: between at this decision
                "n_live_options": sum(1 for x in st.set_winner if x is None) + 1,
            })
        ply += 1
    kv = sum(1 for w in st.set_winner if w == kv_team)
    return {"deal": deal_seed, "kv_even": kv_even, "margin": 2 * kv - NHS,
            "plies": ply, "decls": decls, "movers": movers}


def main(n_deals=250, n_jobs=0, out="results/defer_bound.jsonl"):
    n_jobs = n_jobs or max(1, (os.cpu_count() or 2))
    todo = [(SEED0 + i, ke) for i in range(n_deals) for ke in (True, False)]
    t0 = time.time()
    with Pool(n_jobs) as pool, Path(out).open("w") as fh:
        for i, r in enumerate(pool.imap_unordered(_one, todo, chunksize=2)):
            fh.write(json.dumps(r) + "\n")
            if (i + 1) % 50 == 0:
                print(f"  {i+1}/{len(todo)} {(time.time()-t0)/60:.1f} min",
                      flush=True)
    print("wrote", out)
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 250,
                          int(a[1]) if len(a) > 1 else 0,
                          a[2] if len(a) > 2 else "results/defer_bound.jsonl"))
