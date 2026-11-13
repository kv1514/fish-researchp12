"""Calibrate the fair-play detector: honest players, cheaters, and the rules.

Registered in prereg/fairplay_detector.md before the first run; read that for
the players, the quantities and the decision rules. This script plays the
games and writes per-seat-game rows; ``--analyse`` reads them back and applies
the registered rules.

    python scripts4/fairplay_calibration.py --games 300 --procs 4 \
        --out results/fairplay_calibration_rows.jsonl
    python scripts4/fairplay_calibration.py --analyse \
        --out results/fairplay_calibration_rows.jsonl \
        --report results/fairplay_calibration.json

Every policy is its own persistent agent with its own seed. The assessment
helper is built exactly as the server builds it (``api._fairplay.assess``),
from a seed the policy never sees -- so an "engine" player is an independent
engine instance, which is what an engine-assisted human would be running.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, half_suit_cards, team_of      # noqa: E402
from fish.engine import Ask, ClaimEvent, Claim, AskEvent, GameState  # noqa: E402
from fish.observation import Observation                           # noqa: E402
from fish.rules import RuleConfig                                  # noqa: E402

POLICIES = ("engine", "dylan", "peek50", "peek15", "share")
HONEST = ("engine", "dylan")


class _View:
    """What ``assess`` needs from a Session, built from a bare game state."""

    def __init__(self, state, seat, rules, helper_seed):
        from api._engine import CHAMPION_GAMMA, WEB_DRAWS
        self.state, self.seat, self.rules = state, seat, rules
        self.gamma, self.draws = CHAMPION_GAMMA, WEB_DRAWS
        self._helper_seed = helper_seed

    def obs(self):
        return Observation.from_state(self.state, self.seat)


def _engine(seed, seat, rules):
    from api._engine import CHAMPION_GAMMA, WEB_DRAWS, WEB_SPEC, make_agent
    a = make_agent(("fishbot4", dict(WEB_SPEC, opponent_gamma=CHAMPION_GAMMA,
                                     n_draws=WEB_DRAWS)))
    a.begin_game(seat, rules, seed)
    return a


def _dylan(seed, seat, rules):
    from fish4.registry4 import make_agent
    a = make_agent(("dylan_v07", {}))
    a.begin_game(seat, rules, seed)
    return a


def _peek(state, obs, rng):
    """A legal ask for a card the target really holds, or None."""
    sure = [a for a in obs.legal_asks()
            if state.hands[a.target] >> a.card & 1]
    return rng.choice(sure) if sure else None


def _share(state, seat):
    """Declare a half-suit the team wholly holds, with the true split."""
    team = [p for p in range(NUM_PLAYERS) if team_of(p) == team_of(seat)]
    for hs, w in enumerate(state.set_winner):
        if w is not None:
            continue
        owners = []
        for c in half_suit_cards(hs):
            holder = next((p for p in team if state.hands[p] >> c & 1), None)
            if holder is None:
                break
            owners.append(holder)
        else:
            return Claim(hs, tuple(owners))
    return None


def play_game(g: int) -> list:
    from api import _fairplay as F
    rng = random.Random(0xF41C ^ (g * 7919))
    p0 = POLICIES[g % len(POLICIES)]
    p1 = POLICIES[(g // len(POLICIES)) % len(POLICIES)]
    under = {0: p0, 1: p1}
    rules = RuleConfig(variant="54", starting_player=g % NUM_PLAYERS,
                       wrong_distribution_outcome="opponent")
    state = GameState.deal(rules, seed=rng.getrandbits(62))
    agents = {}
    for p in range(NUM_PLAYERS):
        kind = under.get(p, "engine")
        mk = _dylan if kind == "dylan" else _engine
        agents[p] = mk(rng.getrandbits(62), p, rules)
    helper_seed = {p: rng.getrandbits(62) for p in under}
    rows = {p: [] for p in under}
    t0 = time.time()
    for _ply in range(600):
        if state.is_terminal:
            break
        p = state.turn
        obs = Observation.from_state(state, p)
        kind = under.get(p, "engine")
        action = None
        if kind in ("peek50", "peek15") and not obs.must_pass():
            q = 0.5 if kind == "peek50" else 0.15
            if rng.random() < q:
                action = _peek(state, obs, rng)
        if kind == "share" and not obs.must_pass():
            action = _share(state, p)
        engine_action = agents[p].act(obs)      # keeps every agent's belief current
        if action is None:
            action = engine_action
        rec = None
        if p in under:
            rec = F.assess(_View(state, p, rules, helper_seed[p]), action)
        ev = state.apply(p, action)
        if rec is not None:
            if isinstance(ev, AskEvent):
                rec["o"] = int(ev.success)
            elif isinstance(ev, ClaimEvent):
                rec["o"] = int(tuple(ev.declared) == tuple(ev.revealed))
            rows[p].append(rec)
    out = []
    for p, kind in under.items():
        t = F.tally(rows[p])
        out.append({"game": g, "seat": p, "policy": kind,
                    "terminal": bool(state.is_terminal),
                    "secs": round(time.time() - t0, 1), "tally": t})
    return out


def run(args) -> None:
    from multiprocessing import Pool
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out.exists():
        for line in out.read_text().splitlines():
            done.add(json.loads(line)["game"])
    todo = [g for g in range(args.seed_offset, args.seed_offset + args.games)
            if g not in done]
    print(f"{len(todo)} games to play ({len(done)} already in {out})", flush=True)
    with Pool(args.procs) as pool, out.open("a") as fh:
        for i, rows in enumerate(pool.imap_unordered(play_game, todo)):
            for r in rows:
                fh.write(json.dumps(r) + "\n")
            fh.flush()
            if (i + 1) % 20 == 0:
                print(f"{i + 1}/{len(todo)} games", flush=True)


# ---------------------------------------------------------------------------
# Analysis: the registered decision rules
# ---------------------------------------------------------------------------

def _mean_ci(xs):
    n = len(xs)
    m = sum(xs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1)) if n > 1 else 0.0
    h = 1.96 * sd / math.sqrt(n)
    return round(m, 4), [round(m - h, 4), round(m + h, 4)], round(sd, 4)


def analyse(args) -> None:
    from api import _fairplay as F
    rows = [json.loads(l) for l in Path(args.out).read_text().splitlines()]
    by = {k: [r for r in rows if r["policy"] == k] for k in POLICIES}
    rng = random.Random(20261113)
    report = {"seat_games": {k: len(v) for k, v in by.items()},
              "unfinished_games": sum(1 for r in rows if not r["terminal"]),
              "per_game": {}, "careers": {}, "rules": {}}
    for k, rs in by.items():
        ex = [(r["tally"]["hits"] - r["tally"]["ask_exp"]) / r["tally"]["asks"]
              for r in rs if r["tally"]["asks"]]
        z = [F.summary(r["tally"])["ask_z"] for r in rs if r["tally"]["asks"]]
        m_ex, ci_ex, sd_ex = _mean_ci(ex)
        m_z, ci_z, sd_z = _mean_ci(z)
        opn = sum(r["tally"]["open"] for r in rs)
        report["per_game"][k] = {
            "ask_excess_mean": m_ex, "ask_excess_ci95": ci_ex,
            "ask_z_mean": m_z, "ask_z_sd": sd_z,
            "asks_per_game": round(sum(r["tally"]["asks"] for r in rs) / len(rs), 1),
            "claims_per_game": round(sum(r["tally"]["claims"] for r in rs) / len(rs), 2),
            "engine_match_rate": round(sum(r["tally"]["match"] for r in rs) / opn, 3) if opn else None,
        }
    B = 2000
    for K in (5, 10, 25, 50, 100):
        report["careers"][K] = {}
        for k, rs in by.items():
            hit = {"any_ask_or_claim": 0, "asks": 0, "declarations": 0}
            match_rates = []
            for _ in range(B):
                t = F.empty()
                for r in (rng.choice(rs) for _ in range(K)):
                    t = F.merge(t, r["tally"])
                rules = {f["rule"] for f in F.flags(t)}
                for rule in ("asks", "declarations"):
                    hit[rule] += rule in rules
                hit["any_ask_or_claim"] += bool(rules & {"asks", "declarations"})
                if t["open"]:
                    match_rates.append(t["match"] / t["open"])
            match_rates.sort()
            report["careers"][K][k] = {
                **{f"flag_rate_{r}": round(v / B, 4) for r, v in hit.items()},
                "match_rate_p50": round(match_rates[len(match_rates) // 2], 3) if match_rates else None,
                "match_rate_p99": round(match_rates[int(.99 * len(match_rates))], 3) if match_rates else None,
            }
    pg, cr = report["per_game"], report["careers"]
    if args.round == 2:
        Ks = (10, 25, 50, 100)
        fp = {f"K{K}_{k}": cr[K][k]["flag_rate_any_ask_or_claim"]
              for K in Ks for k in HONEST}
        report["rules"] = {
            "round": 2,
            "honest_flag_rates": fp,
            "honest_ok_le_1pct": all(v <= 0.01 for v in fp.values()),
            "peek50_k10": cr[10]["peek50"]["flag_rate_any_ask_or_claim"],
            "share_k25": cr[25]["share"]["flag_rate_any_ask_or_claim"],
            "power_ok": (cr[10]["peek50"]["flag_rate_any_ask_or_claim"] >= 0.90
                         and cr[25]["share"]["flag_rate_any_ask_or_claim"] >= 0.90),
            "k_for_90pct": {k: next((K for K in (5, 10, 25, 50, 100)
                                     if cr[K][k]["flag_rate_any_ask_or_claim"] >= 0.90), None)
                            for k in ("peek50", "peek15", "share")},
            "flag_rate_by_K": {k: {K: cr[K][k]["flag_rate_any_ask_or_claim"]
                                   for K in (5, 10, 25, 50, 100)}
                               for k in POLICIES},
        }
        report["rules"]["ships"] = (report["rules"]["honest_ok_le_1pct"]
                                    and report["rules"]["power_ok"])
        Path(args.report).write_text(json.dumps(report, indent=1))
        print(json.dumps(report["per_game"], indent=1))
        print(json.dumps(report["rules"], indent=1))
        return
    eng_ci = pg["engine"]["ask_excess_ci95"]
    dyl_hi = pg["dylan"]["ask_excess_ci95"][1]
    report["rules"] = {
        "1_calibration_engine_inside_pm003": -0.03 <= eng_ci[0] and eng_ci[1] <= 0.03,
        "1_dylan_upper_ci": dyl_hi,
        "1_raise_ask_excess_to": round(dyl_hi + 0.04, 3) if dyl_hi > 0.04 else None,
        "2_false_positive_ok": all(cr[K][k]["flag_rate_any_ask_or_claim"] <= 0.01
                                   for K in (10, 25, 50) for k in HONEST),
        "2_false_positive_max": max(cr[K][k]["flag_rate_any_ask_or_claim"]
                                    for K in (10, 25, 50) for k in HONEST),
        "3_peek50_power_k10": cr[10]["peek50"]["flag_rate_any_ask_or_claim"],
        "3_peek50_ok": cr[10]["peek50"]["flag_rate_any_ask_or_claim"] >= 0.90,
        "3_k_for_90pct": {k: next((K for K in (5, 10, 25, 50)
                                   if cr[K][k]["flag_rate_any_ask_or_claim"] >= 0.90), None)
                          for k in ("peek50", "peek15", "share")},
        "4_dylan_match_p99_k10": cr[10]["dylan"]["match_rate_p99"],
        "4_keep_match_rate_090": (cr[10]["dylan"]["match_rate_p99"] or 0) < 0.80,
        "4_engine_match_p50_k10": cr[10]["engine"]["match_rate_p50"],
    }
    Path(args.report).write_text(json.dumps(report, indent=1))
    print(json.dumps(report["per_game"], indent=1))
    print(json.dumps(report["rules"], indent=1))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=300)
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--out", default="results/fairplay_calibration_rows.jsonl")
    ap.add_argument("--report", default="results/fairplay_calibration.json")
    ap.add_argument("--seed-offset", type=int, default=0,
                    help="first game index; round 2 confirms on 100000+")
    ap.add_argument("--round", type=int, default=1)
    ap.add_argument("--analyse", action="store_true")
    a = ap.parse_args()
    analyse(a) if a.analyse else run(a)
