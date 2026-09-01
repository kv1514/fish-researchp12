"""prereg/signal_matched_dose.md: compare opponents at EQUAL signal dose.

Two stages, on two banks, in this order and no other.

  calibrate   seed 13,900,000. Sweeps `signal_max_p` per opponent to find the
              largest dose every opponent in the grid can reach, then measures
              the REFERENCE opponent's own error channel at that dose. Its
              only outputs are a parameter per opponent and a feasibility
              verdict; no effect from this bank is evidence for anything.

  score       seed 14,300,000. Only runs if the feasibility gate passed. Two
              arms per opponent on the identical deal, primary is the
              OPPONENT's extra wrong declarations a game.

WHY A SWEEP AND NOT A CAP. `signal_budget` only lowers a dose, and the dose
every opponent can reach by capping is one where the reference opponent's own
channel already covers zero. `signal_max_p` is the cheapness gate and raising
it raises the dose, without touching what a signal proves.

ONE RULE THE REGISTRATION LEFT OPEN, and this is flagged rather than hidden:
the document says the stronger opponent is "brought down to D with
signal_budget" and does not say how the integer is chosen, because a per-game
cap does not map to a dose in closed form. This implements the minimal
completion consistent with the document -- sweep integer budgets and take the
one whose realised dose is nearest D -- and records that the rule was fixed at
implementation time rather than in the registration.

    py scripts4/matched_dose.py calibrate [n_deals] [n_jobs]
    py scripts4/matched_dose.py score     [n_deals] [n_jobs]
"""
from __future__ import annotations

import json
import math
import sys
import time
from collections import defaultdict
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, team_of                       # noqa: E402
from fish.engine import ClaimEvent, GameState                     # noqa: E402
from fish.observation import Observation                          # noqa: E402
from fish.rules import RuleConfig                                 # noqa: E402
from fish4.clustered import cluster_ci                            # noqa: E402
from scripts4 import signal_vs_defer as run                       # noqa: E402
from scripts4.resultfile import write as write_result             # noqa: E402

GRID = ("dylan_v07", "ev_claim")
REFERENCE = "dylan_v07"

CAL_SEED, CAL_AGENT, CAL_DEALS = 13_900_000, 139_000, 200
SCORE_SEED, SCORE_AGENT, SCORE_DEALS = 14_300_000, 143_000, 800

SWEEP = (0.50, 0.70, 0.85, 1.00)
BUDGET_SWEEP = (2, 3, 4, 6, 8, 10, 12, 16)
#: withdrawal condition 3: the scored run's dose must land within this of D
DOSE_TOLERANCE = 0.15


def _agents(kv_even: bool, vs: str, arm: dict):
    from fish4.registry4 import V06_DEPLOYED, make_agent
    kind, opp = ("fishbot4", dict(V06_DEPLOYED[1])) if vs == "self" \
        else (vs, {})
    ours = dict(V06_DEPLOYED[1], trace=True, **arm)
    return [make_agent(("fishbot4", ours)) if (p % 2 == 0) == kv_even
            else make_agent((kind, opp)) for p in range(NUM_PLAYERS)]


def _play(deal_seed: int, kv_even: bool, vs: str, arm: dict,
          agent0: int) -> dict:
    rules = RuleConfig(**run.RULES_D)
    agents = _agents(kv_even, vs, arm)
    st = GameState.deal(rules, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, agent0 + deal_seed * 13 + p)
    our_team = 0 if kv_even else 1
    fires = 0
    opp_declares = opp_wrong = 0
    for _ in range(600):
        if st.is_terminal:
            break
        mover = st.turn
        ours = team_of(mover) == our_team
        act = agents[mover].act(Observation.from_state(st, mover))
        if ours and (getattr(agents[mover], "last_trace", None)
                     or {}).get("kind") == "signal":
            fires += 1
        ev = st.apply(mover, act)
        if isinstance(ev, ClaimEvent) and not ours:
            opp_declares += 1
            opp_wrong += int(ev.winner != team_of(mover))
    ours_sets = sum(1 for w in st.set_winner if w == our_team)
    theirs = sum(1 for w in st.set_winner if w == 1 - our_team)
    return {"margin": ours_sets - theirs, "fires": fires, "opp_declares": opp_declares,
            "opp_wrong": opp_wrong, "terminal": int(st.is_terminal),
            "fallbacks": sum(getattr(a, "fallbacks", 0) for a in agents)}


def _sweep_job(a):
    seed, kv, vs, max_p, budget, agent0 = a
    arm = {"signal_mode": "stuck", "signal_max_p": max_p}
    if budget:
        arm["signal_budget"] = budget
    r = _play(seed, kv, vs, arm, agent0)
    r.update(deal=seed, vs=vs, max_p=max_p, budget=budget or 0)
    return r


def _mean(rows, key):
    return sum(r[key] for r in rows) / max(1, len(rows))


def calibrate(n_deals=None, n_jobs=None, out=None) -> int:
    t0 = time.time()
    n_deals = CAL_DEALS if n_deals is None else n_deals
    jobs = [(CAL_SEED + i, kv, vs, p, 0, CAL_AGENT)
            for i in range(n_deals) for kv in (True, False)
            for vs in GRID for p in SWEEP]
    with Pool(n_jobs or 4) as pool:
        rows = pool.map(_sweep_job, jobs, chunksize=1)

    dose: dict = defaultdict(dict)
    for r in rows:
        dose[r["vs"]].setdefault(r["max_p"], []).append(r)
    table = {vs: {p: round(_mean(rs, "fires"), 3) for p, rs in d.items()}
             for vs, d in dose.items()}

    print("\n=== calibration, seed %d, %d deals x 2 parities" % (CAL_SEED,
                                                                 n_deals))
    print("\n  fires a game by cheapness gate\n")
    print("  %-11s %s" % ("opponent", "  ".join("p=%.2f" % p for p in SWEEP)))
    for vs in GRID:
        print("  %-11s %s" % (vs, "  ".join("%6.3f" % table[vs][p]
                                            for p in SWEEP)))

    #: D is the largest dose EVERY opponent reaches, floored to one decimal.
    ceiling = min(table[vs][1.00] for vs in GRID)
    D = math.floor(ceiling * 10) / 10
    print("\n  every opponent reaches at most %.3f at p=1.00, so D = %.1f"
          % (ceiling, D))

    params: dict = {}
    for vs in GRID:
        ok = [p for p in SWEEP if table[vs][p] >= D]
        p_star = min(ok) if ok else 1.00
        params[vs] = {"signal_mode": "stuck", "signal_max_p": p_star}
        got = table[vs][p_star]
        if got > D * (1 + DOSE_TOLERANCE):
            bjobs = [(CAL_SEED + i, kv, vs, p_star, b, CAL_AGENT)
                     for i in range(n_deals) for kv in (True, False)
                     for b in BUDGET_SWEEP]
            with Pool(n_jobs or 4) as pool:
                brows = pool.map(_sweep_job, bjobs, chunksize=1)
            by_b: dict = defaultdict(list)
            for r in brows:
                by_b[r["budget"]].append(r)
            cand = {b: round(_mean(rs, "fires"), 3) for b, rs in by_b.items()}
            best = min(cand, key=lambda b: abs(cand[b] - D))
            params[vs]["signal_budget"] = best
            got = cand[best]
            print("  %-11s p=%.2f gave %.3f, capped at budget %d -> %.3f"
                  % (vs, p_star, table[vs][p_star], best, got))
        else:
            print("  %-11s p=%.2f -> %.3f" % (vs, p_star, got))
        params[vs]["_dose"] = got

    print("\n  FEASIBILITY GATE: does %s still show the effect at D?"
          % REFERENCE)
    arm = {k: v for k, v in params[REFERENCE].items() if not k.startswith("_")}
    gate = _gate(n_deals, n_jobs, arm)
    passes = gate["ci95"][0] > 0
    print("    their extra wrong declarations at D: %+0.4f [%+0.4f, %+0.4f]"
          % (gate["mean"], *gate["ci95"]))
    print("    -> %s" % ("PASS, the scored run may proceed"
                         if passes else "FAIL, the study is ABANDONED"))

    payload = {"what": "calibration for prereg/signal_matched_dose.md",
               "calibration_only": True, "prereg": "signal_matched_dose",
               "seed_deal": CAL_SEED, "seed_agent": CAL_AGENT,
               "n_deals": n_deals, "n_games": len(rows), "vs": "|".join(GRID),
               "sweep": list(SWEEP), "dose_table": table,
               "common_dose_D": D, "params": params,
               "gate": gate, "gate_passes": passes,
               "budget_rule": "nearest realised dose to D; fixed at "
                              "implementation time, not in the registration",
               #: A short run is a SMOKE and says so in the payload, because a
               #: calibration at three deals that reached the real filename
               #: would be indistinguishable from the registered one.
               "smoke": n_deals != CAL_DEALS,
               "minutes": round((time.time() - t0) / 60, 1)}
    if n_deals != CAL_DEALS and out is None:
        raise SystemExit(
            f"{n_deals} deals is not the registered {CAL_DEALS}. Pass an "
            f"explicit output path for a smoke; the registered filename is "
            f"reserved for the registered size.")
    path = write_result(
        Path(out) if out else ROOT / "results" / "matched_dose_calibration.json",
        payload)
    print("\nwrote %s  (%s min)" % (path, payload["minutes"]))
    return 0 if passes else 2


def _gate(n_deals, n_jobs, arm) -> dict:
    """The reference opponent's own channel at the common dose."""
    jobs = [(CAL_SEED + 500_000 + i, kv, REFERENCE, arm, CAL_AGENT + 7)
            for i in range(n_deals) for kv in (True, False)]
    base = [(s, kv, vs, {}, a) for (s, kv, vs, _, a) in jobs]
    with Pool(n_jobs or 4) as pool:
        b_rows = pool.map(_pair_job, jobs)
        a_rows = pool.map(_pair_job, base)
    deals = [j[0] for j in jobs]
    diff = [b["opp_wrong"] - a["opp_wrong"] for a, b in zip(a_rows, b_rows)]
    m, h, k = cluster_ci(diff, deals)
    return {"mean": round(m, 4), "half_width": round(h or 0.0, 4),
            "ci95": [round(m - (h or 0), 4), round(m + (h or 0), 4)],
            "n_clusters": k,
            "fires_per_game": round(_mean(b_rows, "fires"), 3)}


def _pair_job(a):
    seed, kv, vs, arm, agent0 = a
    return _play(seed, kv, vs, arm, agent0)


SCORE_DEALS_AMENDED = 2_500          # prereg amendment 1, 2026-09-01


def score(n_deals=None, n_jobs=None, out=None) -> int:
    """Stage two. Refuses to run unless calibration passed its gate."""
    t0 = time.time()
    cal_path = ROOT / "results" / "matched_dose_calibration.json"
    if not cal_path.exists():
        raise SystemExit("calibration has not run; stage two is not licensed.")
    cal = json.loads(cal_path.read_text())
    if cal.get("smoke"):
        raise SystemExit("the calibration on disk is a SMOKE, not the "
                         "registered bank.")
    if not cal.get("gate_passes"):
        raise SystemExit(
            "the feasibility gate FAILED: %s. prereg/signal_matched_dose.md "
            "abandons the study on that outcome, and re-picking D after "
            "seeing it is barred." % cal["gate"])
    D = cal["common_dose_D"]
    params = {vs: {k: v for k, v in p.items() if not k.startswith("_")}
              for vs, p in cal["params"].items()}
    n_deals = SCORE_DEALS_AMENDED if n_deals is None else n_deals

    jobs = [(SCORE_SEED + i, kv, vs, arm, SCORE_AGENT)
            for i in range(n_deals) for kv in (True, False)
            for vs in GRID for arm in ({}, params[vs])]
    with Pool(n_jobs or 4) as pool:
        rows = pool.map(_pair_job, jobs)

    out_p = {"opponents": {}}
    print("\n=== matched dose, seed %d, %d deals x 2 parities, D = %.1f"
          % (SCORE_SEED, n_deals, D))
    withdrawn = []
    for vs in GRID:
        idx = [i for i, j in enumerate(jobs) if j[2] == vs]
        a = [rows[i] for i in idx[0::2]]
        b = [rows[i] for i in idx[1::2]]
        deals = [jobs[i][0] for i in idx[0::2]]
        m, h, k = cluster_ci([x["opp_wrong"] - y["opp_wrong"]
                              for y, x in zip(a, b)], deals)
        md, mh, _ = cluster_ci([x["margin"] - y["margin"]
                                for y, x in zip(a, b)], deals)
        dose = round(_mean(b, "fires"), 3)
        off = abs(dose - D) / D
        out_p["opponents"][vs] = {
            "params": params[vs], "dose": dose, "dose_off_by": round(off, 4),
            "their_wrong_effect": {
                "mean": round(m, 4), "half_width": round(h or 0.0, 4),
                "ci95": [round(m - (h or 0), 4), round(m + (h or 0), 4)],
                "n_clusters": k},
            "margin_effect": {"mean": round(md, 4),
                              "half_width": round(mh or 0.0, 4)},
            "unfinished": sum(1 for r in a + b if not r["terminal"]),
            "fallbacks": sum(r["fallbacks"] for r in a + b)}
        d = out_p["opponents"][vs]
        print("\n  %-11s dose %.3f (%.1f%% off D)   params %s"
              % (vs, dose, 100 * off, params[vs]))
        print("    their extra wrong declarations  %+0.4f [%+0.4f, %+0.4f]"
              % (m, d["their_wrong_effect"]["ci95"][0],
                 d["their_wrong_effect"]["ci95"][1]))
        print("    margin (NOT the primary)        %+0.4f +-%0.4f"
              % (md, mh or 0.0))
        if off > DOSE_TOLERANCE:
            withdrawn.append("%s dose %.3f is %.1f%% from D=%.1f"
                             % (vs, dose, 100 * off, D))
        if d["unfinished"] or d["fallbacks"]:
            withdrawn.append("%s had unfinished games or bridge fallbacks" % vs)

    out_p["withdrawn"] = withdrawn
    if withdrawn:
        print("\n  WITHDRAWN: %s" % "; ".join(withdrawn))
    out_p.update(prereg="signal_matched_dose", seed_deal=SCORE_SEED,
                 seed_agent=SCORE_AGENT, n_deals=n_deals,
                 n_games=len(rows), vs="|".join(GRID), common_dose_D=D,
                 amendment="n raised 800 -> 2500 after calibration",
                 smoke=n_deals != SCORE_DEALS_AMENDED,
                 minutes=round((time.time() - t0) / 60, 1))
    if out_p["smoke"] and out is None:
        raise SystemExit("%d is not the amended %d; pass an explicit path "
                         "for a smoke." % (n_deals, SCORE_DEALS_AMENDED))
    path = write_result(
        Path(out) if out else ROOT / "results" / "matched_dose_scored.json",
        out_p)
    print("\nwrote %s  (%s min)" % (path, out_p["minutes"]))
    return 0


def main(argv) -> int:
    what = argv[0] if argv else "calibrate"
    rest = [x for x in argv[1:]]
    n_deals = int(rest[0]) if rest else None
    n_jobs = int(rest[1]) if len(rest) > 1 else None
    out = rest[2] if len(rest) > 2 else None
    if what == "calibrate":
        return calibrate(n_deals, n_jobs, out)
    if what == "score":
        return score(n_deals, n_jobs, out)
    raise SystemExit("stages are 'calibrate' and 'score'; got %r" % what)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
