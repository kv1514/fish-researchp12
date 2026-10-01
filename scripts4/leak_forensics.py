"""Per-move forensics on the deployed head-to-head, replayed from journal seeds.

Reconstructs games exactly as scripts4/mega_match.py::_one does (same deals,
same seating, same agent seeds), then walks the transcript with SIX shadow
BeliefStates -- one per seat, fed only that seat's Observation, so nothing here
sees GameState.

For every half-suit it records, per seat:
  t_split : first ply at which that seat can PIN all six cards, all to its own
            team  -> it could have declared with certainty, had it been on move
  t_own   : first ply at which that seat can prove all six sit on its own team
            without pinning the split -> the "stuck" state
and per game it records every claim with the ply, the mover, the live-half-suit
count, the number of misplaced cards, and how many of the declaring team's own
turns went by after certainty was available.

    py scripts4/leak_forensics.py [n_deals] [n_jobs] [out.jsonl]
"""
from __future__ import annotations

import json, os, sys, time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.beliefs import BeliefState
from fish.cards import CARDS_PER_HALF_SUIT, half_suit_cards, team_of
from fish.engine import AskEvent, ClaimEvent, GameState, PassEvent
from fish.observation import Observation
from fish.rules import RuleConfig

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 900_000
AGENT0 = 9000
NHS = 9


def _hs_status(bel, hs, seat):
    """(pinned_all_own_team, own_team_ownership_provable) for one seat."""
    my = team_of(seat)
    pinned = True
    owned = True
    for c in half_suit_cards(hs):
        m = bel.current_holder_mask(c)
        if m == 0:
            return False, False          # resolved: half-suit already gone
        # every candidate holder on my team?
        for p in range(6):
            if m >> p & 1 and team_of(p) != my:
                owned = False
                break
        if m & (m - 1):
            pinned = False
    return (pinned and owned), owned


def _one(args) -> dict:
    deal_seed, kv_even = args
    from fish4.registry4 import V06_DEPLOYED, make_agent
    rules = RuleConfig(**RULES_D)
    agents = []
    for p in range(6):
        kv = (p % 2 == 0) == kv_even
        agents.append(make_agent(V06_DEPLOYED) if kv
                      else make_agent(("dylan_v07", {})))
    st = GameState.deal(rules, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
    shadow = [BeliefState(rules, observer=p) for p in range(6)]
    kv_team = 0 if kv_even else 1

    t_split = [[None] * 6 for _ in range(NHS)]   # [hs][seat] -> ply
    t_own = [[None] * 6 for _ in range(NHS)]
    turns_after_split = [[0] * 6 for _ in range(NHS)]  # own turns while certain
    turns_after_own = [[0] * 6 for _ in range(NHS)]
    #: true-state bookkeeping, forensics only -- never read by any policy
    first_full = [None] * NHS          # (ply, team) the hs first sits in one team
    full_plies = [[0, 0] for _ in range(NHS)]   # plies each team fully owned it
    claims = []
    ply = 0
    for _ in range(600):
        if st.is_terminal:
            break
        mover = st.turn
        # refresh every seat's shadow belief BEFORE the move is chosen
        for p in range(6):
            shadow[p].update(Observation.from_state(st, p))
        for hs in range(NHS):
            if st.set_winner[hs] is not None:
                continue
            for p in range(6):
                sp, ow = _hs_status(shadow[p], hs, p)
                if sp and t_split[hs][p] is None:
                    t_split[hs][p] = ply
                if ow and t_own[hs][p] is None:
                    t_own[hs][p] = ply
                if p == mover and t_split[hs][p] is not None \
                        and t_split[hs][p] < ply:
                    turns_after_split[hs][p] += 1
                if p == mover and t_own[hs][p] is not None \
                        and t_own[hs][p] < ply:
                    turns_after_own[hs][p] += 1
        for hs in range(NHS):
            if st.set_winner[hs] is not None:
                continue
            owners = {next(t for t in range(6) if st.hands[t] >> c & 1)
                      for c in half_suit_cards(hs)}
            teams = {team_of(o) for o in owners}
            if len(teams) == 1:
                t = teams.pop()
                full_plies[hs][t] += 1
                if first_full[hs] is None:
                    first_full[hs] = [ply, t]
        act = agents[mover].act(Observation.from_state(st, mover))
        ev = st.apply(mover, act)
        if isinstance(ev, ClaimEvent):
            hs = ev.half_suit
            wrong = sum(1 for a, b in zip(ev.declared, ev.revealed) if a != b)
            side = "kv" if team_of(ev.claimer) == kv_team else "dy"
            live = sum(1 for x in st.set_winner if x is None)  # AFTER the claim
            # what the claiming team knew, and what the OTHER team knew
            def team_seats(t):
                return [p for p in range(6) if team_of(p) == t]
            ct = team_of(ev.claimer)
            claims.append({
                "hs": hs, "ply": ply, "side": side, "claimer": ev.claimer,
                "ok": int(ev.winner == ct),
                "own_class": int(all(team_of(h) == ct for h in ev.revealed)),
                "wrong_cards": wrong, "live_after": live,
                "declarer_split": t_split[hs][ev.claimer],
                "team_split": min([t_split[hs][p] for p in team_seats(ct)
                                   if t_split[hs][p] is not None], default=None),
                "opp_split": min([t_split[hs][p] for p in team_seats(1 - ct)
                                  if t_split[hs][p] is not None], default=None),
                "declarer_own": t_own[hs][ev.claimer],
                "team_own": min([t_own[hs][p] for p in team_seats(ct)
                                 if t_own[hs][p] is not None], default=None),
                "opp_own": min([t_own[hs][p] for p in team_seats(1 - ct)
                                if t_own[hs][p] is not None], default=None),
                "turns_wasted": max(turns_after_split[hs][p]
                                    for p in team_seats(ct)),
                "turns_stuck": max(turns_after_own[hs][p]
                                   for p in team_seats(ct)),
                "rev_kv": sum(1 for h in ev.revealed if team_of(h) == kv_team),
                "first_full": first_full[hs],
                "full_plies_kv": full_plies[hs][kv_team],
                "full_plies_dy": full_plies[hs][1 - kv_team],
            })
        ply += 1
    kv = sum(1 for w in st.set_winner if w == kv_team)
    return {"deal": deal_seed, "kv_even": kv_even, "plies": ply,
            "kv": kv, "margin": 2 * kv - NHS, "claims": claims}


def main(n_deals=100, n_jobs=0, out="results/leak_forensics.jsonl"):
    n_jobs = n_jobs or max(1, (os.cpu_count() or 2))
    todo = [(SEED0 + i, ke) for i in range(n_deals) for ke in (True, False)]
    outp = Path(out)
    t0 = time.time()
    with Pool(n_jobs) as pool, outp.open("w") as fh:
        for i, r in enumerate(pool.imap_unordered(_one, todo, chunksize=2)):
            fh.write(json.dumps(r) + "\n")
            if (i + 1) % 25 == 0:
                print(f"  {i+1}/{len(todo)}  {(time.time()-t0)/60:.1f} min",
                      flush=True)
    print("wrote", outp)
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 100,
                          int(a[1]) if len(a) > 1 else 0,
                          a[2] if len(a) > 2 else "results/leak_forensics.jsonl"))
