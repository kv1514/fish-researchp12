"""Does Literature have a stalemate? Measuring dead positions and repetition.

Four questions, four measurements. Ground truth (the real hands) is used here
for ANALYSIS only; nothing measured here is fed to an acting policy.

1. **Do positions repeat?** Hash (hands, turn, resolved) at every ply and look
   for a state occurring twice. A repeat proves the state graph is cyclic in
   actual play, not merely in principle.

2. **How often is the board dead?** A live half-suit is *dead* when all six of
   its cards sit with one team: no member of the other team may legally ask in
   it, and members of the holding team can only ask opponents who hold none of
   it, so no ask in it can ever succeed. A *dead position* is one where every
   live half-suit is dead - the material is frozen for the rest of the game and
   only declarations remain.

3. **Is anyone stuck?** In a dead position, a team that holds a half-suit but
   cannot place the split among its own members has, naively, no way forward:
   no card will move again. We measure how often that happens.

4. **Do games terminate without the agents' progress rule?** Our policies carry
   a stalling rule (gamble a declaration if nothing has resolved in a while).
   Turning it off and counting how many games hit the action cap measures how
   much of "Fish games end" is the rules and how much is the convention.

Usage:  py scripts4/perpetual_study.py [n_games] [n_jobs]
"""

from __future__ import annotations

import json
import random
import sys
import time
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, half_suit_cards, team_of
from fish.engine import NULL_TEAM, GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.registry4 import make_agent

CHAMPION = ("fishbot4", {"opponent_gamma": 0.35})


# ---------------------------------------------------------------------------
# ground-truth structure of a position
# ---------------------------------------------------------------------------

def true_dead_half_suits(state: GameState) -> list:
    """Live half-suits held entirely by one team, from the real hands."""
    out = []
    for hs, w in enumerate(state.set_winner):
        if w is not None:
            continue
        team = None
        ok = True
        for c in half_suit_cards(hs):
            h = state.holder_of(c)
            if h is None:
                ok = False
                break
            t = team_of(h)
            if team is None:
                team = t
            elif team != t:
                ok = False
                break
        if ok and team is not None:
            out.append((hs, team))
    return out


def is_dead(state: GameState) -> bool:
    live = [hs for hs, w in enumerate(state.set_winner) if w is None]
    if not live:
        return False
    dead = {hs for hs, _ in true_dead_half_suits(state)}
    return all(hs in dead for hs in live)


def any_ask_can_succeed(state: GameState) -> bool:
    """The operational definition: does a landing ask exist anywhere?"""
    for p in range(NUM_PLAYERS):
        if not state.hands[p]:
            continue
        for hs, w in enumerate(state.set_winner):
            if w is not None:
                continue
            mine = [c for c in half_suit_cards(hs) if state.hands[p] >> c & 1]
            if not mine:
                continue
            for c in half_suit_cards(hs):
                if state.hands[p] >> c & 1:
                    continue
                h = state.holder_of(c)
                if h is not None and team_of(h) != team_of(p):
                    return True
    return False


def unplaceable_from_seat(state, bel, seat, hs) -> bool:
    """Seat's team provably holds hs, but the seat cannot place every card.

    "Provably holds" means every possible holder of every card is a teammate -
    which does NOT require knowing which teammate. That distinction is the
    whole phenomenon: the set is safe and still undeclarable.
    """
    from fish4.perpetual import half_suit_owner_team
    if half_suit_owner_team(bel, hs) != team_of(seat):
        return False
    return any(bel.current_holder_mask(c) & (bel.current_holder_mask(c) - 1)
               for c in half_suit_cards(hs))


# ---------------------------------------------------------------------------
# one game
# ---------------------------------------------------------------------------

def one_game(args) -> dict:
    seed, agent_seed, stall_window, cap, use_signalling = args
    from fish.beliefs import BeliefState
    rules = RuleConfig()
    kw = dict(CHAMPION[1])
    kw["stall_window"] = stall_window
    kw["signal_mode"] = "stuck" if use_signalling else "off"
    bots = [make_agent((CHAMPION[0], dict(kw))) for _ in range(NUM_PLAYERS)]
    st = GameState.deal(rules, seed=seed)
    ar = random.Random(agent_seed)
    for p, b in enumerate(bots):
        b.begin_game(p, rules, ar.getrandbits(64))
    bels = [BeliefState(rules, observer=p) for p in range(NUM_PLAYERS)]

    seen = Counter()
    rec = {"seed": seed, "plies": 0, "timeout": False,
           "dead_plies": 0, "frozen_plies": 0, "ever_dead": False,
           "first_dead_ply": None, "dead_tail": 0,
           "stuck_team_plies": 0, "ever_stuck": False,
           # WHICH half-suits a team got stuck on, not just how many plies were
           # spent stuck. The paper quotes a null rate for stuck half-suits
           # against unstuck ones (17.5% vs 2.8%, 27% of all nulls, 11% of
           # half-suits) and none of those four numbers was ever computed: this
           # script tracked stuck_team_plies and never summarised it. Record the
           # identities so the comparison is possible.
           "stuck_hs": set(),
           "repeat_states": 0, "max_repeat": 0,
           "dead_hs_seen": 0, "nulls": 0, "diff": 0}
    n = 0
    while not st.is_terminal and n < cap:
        key = (tuple(st.hands), st.turn, tuple(st.set_winner))
        seen[key] += 1
        if seen[key] > 1:
            rec["repeat_states"] += 1
            rec["max_repeat"] = max(rec["max_repeat"], seen[key])
        dead = true_dead_half_suits(st)
        if dead:
            rec["dead_hs_seen"] = max(rec["dead_hs_seen"], len(dead))
        frozen = not any_ask_can_succeed(st)
        if frozen:
            rec["frozen_plies"] += 1
        if is_dead(st):
            rec["dead_plies"] += 1
            if not rec["ever_dead"]:
                rec["ever_dead"] = True
                rec["first_dead_ply"] = n
            # is anyone stuck: holds a half-suit, cannot place it
            for q in range(NUM_PLAYERS):
                try:
                    bels[q].update(Observation.from_state(st, q))
                except Exception:
                    continue
            for hs, t in dead:
                for q in range(NUM_PLAYERS):
                    if team_of(q) != t:
                        continue
                    if unplaceable_from_seat(st, bels[q], q, hs):
                        rec["stuck_team_plies"] += 1
                        rec["ever_stuck"] = True
                        rec["stuck_hs"].add(hs)
                        break
        p = st.turn
        try:
            st.apply(p, bots[p].act(Observation.from_state(st, p)))
        except Exception:
            break
        n += 1
    rec["plies"] = n
    rec["timeout"] = n >= cap
    if rec["first_dead_ply"] is not None:
        rec["dead_tail"] = n - rec["first_dead_ply"]
    a, b, nulls = st.scores()
    rec["nulls"] = nulls
    rec["diff"] = a - b
    # Which half-suits actually nulled, so the rate can be split by whether the
    # holding team was ever stuck on that half-suit.
    nulled = {h for h, w in enumerate(st.set_winner) if w == NULL_TEAM}
    stuck = rec.pop("stuck_hs")
    rec["n_half_suits"] = len(st.set_winner)
    rec["n_stuck_hs"] = len(stuck)
    rec["n_nulled"] = len(nulled)
    rec["n_stuck_and_nulled"] = len(stuck & nulled)
    rec["n_unstuck_and_nulled"] = len(nulled - stuck)
    return rec


def _run(n_games, n_jobs, stall_window, cap, signalling, base=700_000):
    jobs = [(base + i, 800_000 + i, stall_window, cap, signalling)
            for i in range(n_games)]
    if n_jobs > 1:
        with Pool(n_jobs) as pool:
            return list(pool.imap_unordered(one_game, jobs, chunksize=2))
    return [one_game(j) for j in jobs]


# ---------------------------------------------------------------------------

def main(n_games: int = 200, n_jobs: int = 4) -> int:
    t0 = time.time()
    out = {}

    print(f"\n[1/3] {n_games} games with the normal progress rule ...",
          file=sys.stderr, flush=True)
    normal = _run(n_games, n_jobs, 80, 4000, False)

    print(f"[2/3] {n_games} games with the progress rule DISABLED ...",
          file=sys.stderr, flush=True)
    nostall = _run(n_games, n_jobs, 10 ** 9, 4000, False)

    print(f"[3/3] {n_games} games with the signalling protocol ON ...",
          file=sys.stderr, flush=True)
    signal = _run(n_games, n_jobs, 80, 4000, True)

    def summarise(rows, label):
        g = len(rows)
        plies = sum(r["plies"] for r in rows)
        d = {
            "games": g,
            "mean_plies": plies / g,
            "timeouts": sum(1 for r in rows if r["timeout"]),
            "games_reaching_a_dead_position": sum(1 for r in rows if r["ever_dead"]),
            "games_with_a_stuck_team": sum(1 for r in rows if r["ever_stuck"]),
            "games_with_a_repeated_state": sum(1 for r in rows
                                               if r["repeat_states"]),
            "max_times_one_state_repeated": max(r["max_repeat"] for r in rows),
            "share_of_plies_in_a_dead_position": sum(r["dead_plies"]
                                                     for r in rows) / plies,
            "share_of_plies_with_no_landing_ask": sum(r["frozen_plies"]
                                                      for r in rows) / plies,
            "mean_actions_after_first_dead_position": (
                sum(r["dead_tail"] for r in rows if r["ever_dead"])
                / max(1, sum(1 for r in rows if r["ever_dead"]))),
            "mean_dead_half_suits_at_peak": sum(r["dead_hs_seen"]
                                                for r in rows) / g,
            "nulls_per_game": sum(r["nulls"] for r in rows) / g,
        }
        # The deadlock quartet, computed rather than asserted. The paper quotes
        # a null rate for stuck half-suits against unstuck ones, their share of
        # all nulls, and their share of half-suits; none of the four was ever
        # produced by this script, which tracked stuck plies and summarised
        # none of them.
        hs_tot = sum(r["n_half_suits"] for r in rows)
        stuck_tot = sum(r["n_stuck_hs"] for r in rows)
        sn = sum(r["n_stuck_and_nulled"] for r in rows)
        un = sum(r["n_unstuck_and_nulled"] for r in rows)
        d["half_suits"] = hs_tot
        d["stuck_half_suits"] = stuck_tot
        d["share_of_half_suits_stuck"] = stuck_tot / max(1, hs_tot)
        d["null_rate_when_stuck"] = sn / max(1, stuck_tot)
        d["null_rate_when_not_stuck"] = un / max(1, hs_tot - stuck_tot)
        d["stuck_share_of_all_nulls"] = sn / max(1, sn + un)
        d["null_rate_ratio"] = (
            d["null_rate_when_stuck"] / d["null_rate_when_not_stuck"]
            if d["null_rate_when_not_stuck"] else None)
        out[label] = d
        return d

    a = summarise(normal, "normal")
    b = summarise(nostall, "no_progress_rule")
    c = summarise(signal, "signalling")

    print(f"\n{'':44s}{'normal':>12s}{'no stall rule':>15s}{'signalling':>13s}")
    keys = [
        ("mean_plies", "actions per game", "{:.1f}"),
        ("timeouts", "games hitting the 4000-action cap", "{:d}"),
        ("games_with_a_repeated_state", "games where a position repeated", "{:d}"),
        ("max_times_one_state_repeated", "most repeats of one position", "{:d}"),
        ("games_reaching_a_dead_position", "games reaching a DEAD position", "{:d}"),
        ("share_of_plies_in_a_dead_position", "share of plies fully dead", "{:.4f}"),
        ("share_of_plies_with_no_landing_ask", "share of plies with no landing ask", "{:.4f}"),
        ("mean_actions_after_first_dead_position", "actions after going dead", "{:.1f}"),
        ("games_with_a_stuck_team", "games where a team held an unplaceable set", "{:d}"),
        ("mean_dead_half_suits_at_peak", "dead half-suits at peak", "{:.2f}"),
        ("nulls_per_game", "nulls per game", "{:.3f}"),
    ]
    for k, label, fmt in keys:
        print(f"  {label:42s}" + "".join(
            fmt.format(d[k]).rjust(12 if i == 0 else (15 if i == 1 else 13))
            for i, d in enumerate((a, b, c))))

    path = ROOT / "results" / "perpetual_study.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2))
    print(f"\n({time.time()-t0:.0f}s)  Saved {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(int(sys.argv[1]) if len(sys.argv) > 1 else 200,
                          int(sys.argv[2]) if len(sys.argv) > 2 else 4))
