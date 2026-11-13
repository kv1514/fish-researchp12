"""We acquire as much as they do and assemble less. Where do our cards go?

THE GAP THIS OPENS UP. `completion_ledger` put three numbers side by side that
only make sense together:

    turn acquisitions            +0.0931 [+0.0595, +0.1268]   IN OUR FAVOUR
    half-suits assembled         -0.6525 [-0.786, -0.519]
    hits wasted                  +1.0650 [+0.758, +1.372]
    kept hits per half-suit       4.009 against their 4.090   near-equal

Equal acquisitions, near-equal cost per half-suit won, far fewer won, and the
difference showing up as waste. The cards are going somewhere and not coming
back as half-suits.

WHAT IS MEASURED. For every half-suit in every game, the running count each team
holds, and its PEAK -- the closest that team ever came to owning the whole
thing. Then the conversion: given a team reached peak $k$ in a half-suit, how
often did it end up winning it? Ours against theirs, on the same deals, so the
question is not "who gets more cards" but "who turns the same investment into a
resolved half-suit".

That is the assembly analogue of `contest_ledger`, which conditioned on the
shape of the DEAL. This conditions on what a team actually built, which is the
quantity a policy controls.

THE SELF-TEST IS THE AWARD RULE. `fish/engine.py::_apply_claim` gives the
half-suit to the declaring team only on an exact match, and an exact match
requires that team to hold all six. So every half-suit won by a correct
declaration must show the winner at peak 6. A single counter-example means this
ledger is mis-tracking holdings and no conversion rate below may be read.

History and hands only -- no posterior is sampled, so no stale-belief exposure
and no sampling error of its own.

Descriptive. No arm, no duel, no ship claim.
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import (CARDS_PER_HALF_SUIT, NUM_PLAYERS,          # noqa: E402
                        half_suit_mask, team_of)
from fish.engine import NULL_TEAM, ClaimEvent, GameState           # noqa: E402
from fish.observation import Observation                            # noqa: E402
from fish.rules import RuleConfig                                   # noqa: E402
from scripts4.resultfile import default_path, write                # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 16_100_000
AGENT0 = 161_000
MAX_ACTIONS = 600
BOOT = 2000
BOOT_SEED = 20_260_923


def _team_count(hands, hs: int, team: int) -> int:
    m = half_suit_mask(hs)
    return sum(bin(hands[p] & m).count("1")
               for p in range(NUM_PLAYERS) if team_of(p) == team)


def _boot(per_game: list[dict], num: str, den: str,
          boot: int = BOOT, seed: int = BOOT_SEED) -> list[float]:
    rng = random.Random(seed)
    n = len(per_game)
    out = []
    for _ in range(boot):
        pick = [per_game[rng.randrange(n)] for _ in range(n)]
        a = sum(r.get(num, 0) for r in pick)
        b = sum(r.get(den, 0) for r in pick)
        if b:
            out.append(a / b)
    out.sort()
    if not out:
        return [float("nan")] * 2
    return [out[int(0.025 * len(out))],
            out[min(len(out) - 1, int(0.975 * len(out)))]]


def track(rules, agents, our_team: int, seed: int, agent0: int) -> dict:
    """Peaks and outcomes for every half-suit of one deal."""
    st = GameState.deal(rules, seed=seed)
    for p, ag in enumerate(agents):
        ag.begin_game(p, rules, agent0 + seed * 13 + p)
    n_hs = 54 // CARDS_PER_HALF_SUIT
    peak = [[0, 0] for _ in range(n_hs)]
    #: THE COUNT WHEN THE HALF-SUIT CLOSED, which is what tells "peaked and
    #: then lost ground" apart from "peaked and never found the last card".
    #: They are the same row in a peak table and want opposite remedies: the
    #: first is a retention problem, the second a search problem.
    at_close = [[None, None] for _ in range(n_hs)]
    #: how many plies a half-suit stayed live, so "peaked and lost" can be told
    #: apart from "peaked late and ran out of game"
    opened = [0] * n_hs
    closed: dict = {}
    ply = 0

    #: plies each team spent holding exactly k of a LIVE half-suit, and the
    #: number of times it climbed from k to k+1. The ratio is the rate at which
    #: a side turns a partial holding into a bigger one, which is what
    #: "assembling" means operationally.
    plies_at = [[0] * 7, [0] * 7]
    up_from = [[0] * 7, [0] * 7]
    last_count = [[0, 0] for _ in range(n_hs)]
    for hs in range(n_hs):
        for t in (0, 1):
            peak[hs][t] = _team_count(st.hands, hs, t)
            last_count[hs][t] = peak[hs][t]

    for _ in range(MAX_ACTIONS):
        if st.is_terminal:
            break
        actor = st.turn
        act = agents[actor].act(Observation.from_state(st, actor))
        st.apply(actor, act)
        ply += 1
        for hs in range(n_hs):
            if st.set_winner[hs] is not None:
                if at_close[hs][0] is None:
                    # first ply at which it is resolved: the counts recorded
                    # are the ones from the ply BEFORE the award stripped the
                    # cards, which is the state the outcome was decided in
                    at_close[hs] = list(last_count[hs])
                continue
            for t in (0, 1):
                c = _team_count(st.hands, hs, t)
                prev = last_count[hs][t]
                plies_at[t][prev] += 1
                if c > prev:
                    # one ply can move a count by more than one only via a
                    # claim, and claims resolve the half-suit, so this is a
                    # single-card step in every live case
                    up_from[t][prev] += 1
                last_count[hs][t] = c
                if c > peak[hs][t]:
                    peak[hs][t] = c

    for ev in st.history:
        if isinstance(ev, ClaimEvent):
            closed[ev.half_suit] = ev

    rows = []
    for hs in range(n_hs):
        ev = closed.get(hs)
        w = st.set_winner[hs]
        correct = None
        if ev is not None:
            correct = (ev.winner == team_of(ev.claimer))
        oc = at_close[hs]
        if oc[0] is None:
            oc = list(last_count[hs])
        rows.append({
            "hs": hs,
            "our_peak": peak[hs][our_team],
            "their_peak": peak[hs][1 - our_team],
            "our_close": oc[our_team],
            "their_close": oc[1 - our_team],
            "winner_is_ours": (w == our_team),
            "nulled": (w == NULL_TEAM),
            "resolved": ev is not None,
            "correct_declaration": correct,
            "claimer_ours": (team_of(ev.claimer) == our_team) if ev else None,
        })
    return {"rows": rows, "state": st, "plies": ply, "opened": opened,
            "plies_at": plies_at, "up_from": up_from}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--games", type=int, default=400)
    a = ap.parse_args(argv)

    from fish4.registry4 import KRAKEN_V1, make_agent
    from fish4.dylan_v07 import DylanV07

    rules = RuleConfig(**RULES_D)
    t0 = time.time()
    per: list[dict] = []
    #: a half-suit won by a CORRECT declaration whose winner never reached six
    impossible: list = []

    for g in range(a.games):
        seed = SEED0 + g
        kv_even = (g % 2 == 0)
        agents = [make_agent(KRAKEN_V1) if (p % 2 == 0) == kv_even
                  else DylanV07() for p in range(NUM_PLAYERS)]
        our_team = 0 if kv_even else 1
        w = track(rules, agents, our_team, seed, AGENT0)

        row = {"game": g}
        for side in ("ours", "theirs"):
            for k in range(7):
                row[f"{side}_peak{k}"] = 0
                row[f"{side}_peak{k}_won"] = 0
            row[f"{side}_won"] = 0
            # TIME AT EACH LEVEL AND THE CLIMB OUT OF IT. The first version
            # of this block asked whether a team that peaked at k "regressed or
            # stalled", and that split is DEGENERATE: a half-suit is won by a
            # team holding all six, so the losing side's count at close is 0
            # and "regressed" is true by construction. Plies spent at a level,
            # and upward transitions out of it, are properties of the play.
            for k in range(7):
                row[f"{side}_plies_at{k}"] = 0
                row[f"{side}_up_from{k}"] = 0
        for side, t in (("ours", our_team), ("theirs", 1 - our_team)):
            for k in range(7):
                row[f"{side}_plies_at{k}"] += w["plies_at"][t][k]
                row[f"{side}_up_from{k}"] += w["up_from"][t][k]
        for r in w["rows"]:
            # ours
            ok, tk = r["our_peak"], r["their_peak"]
            we_won = r["winner_is_ours"]
            row[f"ours_peak{ok}"] += 1
            row[f"ours_peak{ok}_won"] += int(we_won)
            row[f"theirs_peak{tk}"] += 1
            row[f"theirs_peak{tk}_won"] += int(not we_won and not r["nulled"])
            row["ours_won"] += int(we_won)
            row["theirs_won"] += int(not we_won and not r["nulled"])

            # THE SELF-TEST. A correct declaration requires the declaring team
            # to hold all six, so its peak must be exactly 6.
            if r["correct_declaration"]:
                claimer_peak = ok if r["claimer_ours"] else tk
                if claimer_peak != 6 and len(impossible) < 10:
                    impossible.append({"game": g, "hs": r["hs"],
                                       "peak": claimer_peak,
                                       "claimer_ours": r["claimer_ours"]})
        per.append(row)
        if (g + 1) % 50 == 0 or g + 1 == a.games:
            print(f"  {g+1}/{a.games} games, {(time.time()-t0)/60:.1f} min",
                  flush=True)

    def tot(k):
        return sum(r.get(k, 0) for r in per)

    out = {"script": "scripts4/assembly_ledger.py", "descriptive": True,
           "rules": RULES_D, "seed_deal": SEED0, "seed_agent": AGENT0,
           "n_games": a.games,
           "selftest_correct_declaration_below_peak_six": len(impossible),
           "selftest_examples": impossible,
           "by_peak": {}, "per_game": per}
    for side in ("ours", "theirs"):
        out[f"{side}_won_per_game"] = tot(f"{side}_won") / a.games
    for k in range(7):
        o_n, o_w = tot(f"ours_peak{k}"), tot(f"ours_peak{k}_won")
        t_n, t_w = tot(f"theirs_peak{k}"), tot(f"theirs_peak{k}_won")
        out["by_peak"][k] = {
            "ours_n": o_n, "ours_won": o_w,
            "ours_rate": (o_w / o_n) if o_n else None,
            "ours_ci": _boot(per, f"ours_peak{k}_won", f"ours_peak{k}")
            if o_n else None,
            "theirs_n": t_n, "theirs_won": t_w,
            "theirs_rate": (t_w / t_n) if t_n else None,
            "gap": ((o_w / o_n) - (t_w / t_n)) if (o_n and t_n) else None,
            "ours_per_game": o_n / a.games, "theirs_per_game": t_n / a.games}

    print("\n" + "=" * 72)
    print(f"  SELF-TEST: correct declarations by a team that never held six: "
          f"{len(impossible)}")
    if impossible:
        print("  *** MUST BE ZERO. _apply_claim awards on an exact match, which")
        print("  *** requires all six, so this ledger is mis-tracking holdings")
        print("  *** and NO CONVERSION RATE BELOW MAY BE READ. First:")
        for x in impossible[:3]:
            print(f"      {x}")
    print("=" * 72)
    print("  HOW CLOSE DID EACH TEAM GET, AND DID IT CONVERT?")
    print(f"  {a.games} games. Peak = the most of a half-suit that team ever")
    print("  held at once. Half-suits won per game: "
          f"ours {out['ours_won_per_game']:.3f}, "
          f"theirs {out['theirs_won_per_game']:.3f}.")
    print("=" * 72)
    print(f"  {'peak':>5}  {'ours/game':>10}  {'our win rate':>13}"
          f"  {'theirs/game':>12}  {'their win rate':>15}  {'gap':>8}")
    for k in range(7):
        b = out["by_peak"][k]
        if not b["ours_n"] and not b["theirs_n"]:
            continue
        orr = f"{b['ours_rate']:.4f}" if b["ours_rate"] is not None else "  --"
        trr = (f"{b['theirs_rate']:.4f}" if b["theirs_rate"] is not None
               else "  --")
        gap = f"{b['gap']:+.4f}" if b["gap"] is not None else ""
        print(f"  {k:>5}  {b['ours_per_game']:>10.3f}  {orr:>13}"
              f"  {b['theirs_per_game']:>12.3f}  {trr:>15}  {gap:>8}")
    print("\n" + "-" * 72)
    print("  THE CLIMB: given a team holds k of a LIVE half-suit, how often")
    print("  does it get to k+1? Plies at the level are the denominator, so")
    print("  this is a rate per opportunity and not a count of opportunities.")
    print(f"  {'holding':>8}  {'our plies':>10}{'our climbs':>11}{'our rate':>10}"
          f"  {'their plies':>12}{'their climbs':>13}{'their rate':>11}"
          f"{'gap':>9}")
    out["climb"] = {}
    for k in range(6):
        op, ou = tot(f"ours_plies_at{k}"), tot(f"ours_up_from{k}")
        tp, tu = tot(f"theirs_plies_at{k}"), tot(f"theirs_up_from{k}")
        orr = (ou / op) if op else None
        trr = (tu / tp) if tp else None
        out["climb"][k] = {
            "ours_plies": op, "ours_climbs": ou, "ours_rate": orr,
            "ours_ci": _boot(per, f"ours_up_from{k}", f"ours_plies_at{k}")
            if op else None,
            "theirs_plies": tp, "theirs_climbs": tu, "theirs_rate": trr,
            "gap": (orr - trr) if (orr is not None and trr is not None)
            else None}
        if not op and not tp:
            continue
        g = f"{orr - trr:+.5f}" if (orr is not None and trr is not None) else ""
        print(f"  {k:>8}  {op:>10,}{ou:>11,}{orr:>10.5f}"
              f"  {tp:>12,}{tu:>13,}{trr:>11.5f}{g:>9}")
    print("\n  The climb out of 5 is the one that becomes a declaration.")
    print("\n  A team that reaches peak 6 and does not win it held the whole")
    print("  half-suit and failed to bank it. A team that never reaches 6")
    print("  spent cards on something it could not finish.")
    print(f"\n  wrote {write(default_path('assembly_ledger', SEED0), out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
