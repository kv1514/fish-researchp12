"""P48: the signalling protocol through the repaired bridge, under the dual bar.

Registered in `prereg/kraken_v12_signalling_rev3.md`, which fixes the arms,
the seeds, the bar, the registered secondary and the predicted outcome
before any game; this file only executes it.

Every margin the signalling line reported against an opponent was measured at
BRIDGE_REV 2, through the bridge this project later found to be corrupting
that opponent's posterior, and the line's own ledger put most of the gain in
the opponent's extra wrong declarations -- the counter the defect inflated.
The self-play control was a null. This is the same two arms played through
BRIDGE_REV 3 in both populations, with the margin identity's three counters
read off every game so that the effect can be placed, not just measured.

DESIGN. `p46_screen`'s dual-population design, imported: champion and
candidate each against SESTINA on the same deal on both parities, plus
candidate-versus-champion self-play on the same deal. The scorer here adds,
per game, the identity's counters (declarations made and lost, by team,
from the ClaimEvents) and the candidate seats' own signal counters, and the
report splits every arm's effect into race / ours / theirs, paired within
deal, with the residual asserted zero on every pairing.

Usage:
  python scripts4/p48_screen.py [--deals 300] [--arms S1,S2] [--jobs 3]
         [--out results/p48_screen.json]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.engine import AskEvent, ClaimEvent, GameState        # noqa: E402
from fish.rules import RuleConfig                               # noqa: E402
from scripts4.p46_screen import (_by_deal, _play, _self_play,   # noqa: E402
                                 SHIP_BAR)
from scripts4.v12_screen import _paired                         # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 11_400_000
AGENT0 = 114_000
PREREG = "prereg/kraken_v12_signalling_rev3.md"
#: The two arms, fixed by the registration. S1 is arm C of the signalling
#: line verbatim; S2 is the dose at which the rev-2 opponent channel vanished.
ARMS = {
    "S1_signal_stuck_05": {"signal_mode": "stuck", "signal_max_p": 0.5},
    "S2_signal_budget6": {"signal_mode": "stuck", "signal_max_p": 0.5,
                          "signal_budget": 6},
}
DEFAULT_ARMS = tuple(ARMS)
#: The rev-2 value of S1's theirs channel against dylan_v07, in margin units
#: (2 x their extra wrong declarations a game, +0.1363 [+0.1135, +0.1590]).
REV2_THEIRS = {"mean": 0.2725, "ci95": [0.2270, 0.3180]}


def score(st, our_team, agents) -> dict:
    """Margin, ask hit rate, and the identity's four counters for one game."""
    ours = sum(1 for w in st.set_winner if w == our_team)
    theirs = sum(1 for w in st.set_winner if w == 1 - our_team)
    hits = asks = 0
    d = {0: 0, 1: 0}
    w = {0: 0, 1: 0}
    for e in st.history:
        if isinstance(e, AskEvent) and (e.asker % 2) == our_team:
            asks += 1
            hits += int(e.success)
        elif isinstance(e, ClaimEvent):
            t = e.claimer % 2
            d[t] += 1
            if e.winner != t:
                w[t] += 1
    out = {"margin": ours - theirs, "terminal": st.is_terminal,
           "ask_hit": hits / asks if asks else None, "asks": asks,
           "d_us": d[our_team], "w_us": w[our_team],
           "d_them": d[1 - our_team], "w_them": w[1 - our_team],
           "fallbacks": sum(getattr(a, "fallbacks", 0) for a in agents),
           "signals": sum(getattr(a, "_signals", 0) for p, a in
                          enumerate(agents) if p % 2 == our_team)}
    # The identity: nine half-suits, each awarded once, so the margin is a
    # function of three counters. Asserted, not assumed.
    if st.is_terminal:
        out["identity_ok"] = (
            out["margin"] == 2 * (out["d_us"] - out["w_us"] + out["w_them"]) - 9)
    else:
        out["identity_ok"] = None
    return out


def _one(job) -> dict:
    deal_seed, kv_even, label, agent0 = job
    from fish4.registry4 import KRAKEN_V1, make_agent

    rules = RuleConfig(**RULES_D)
    cand = ("fishbot4", dict(KRAKEN_V1[1], **ARMS[label]))
    our_team = 0 if kv_even else 1
    out = {"deal": deal_seed, "kv_even": kv_even, "arm": label,
           "agent0": agent0}

    def seat(spec_ours, spec_theirs):
        return [make_agent(spec_ours) if (p % 2 == 0) == kv_even
                else make_agent(spec_theirs) for p in range(6)]

    for who, spec in (("champ", KRAKEN_V1), ("cand", cand)):
        agents = seat(spec, ("dylan_v07", {}))
        st = _play(agents, deal_seed, rules, agent0)
        out[f"sestina_{who}"] = score(st, our_team, agents)
    agents = seat(cand, KRAKEN_V1)
    st = _play(agents, deal_seed, rules, agent0)
    out["self"] = score(st, our_team, agents)
    return out


def _mean_ci(values) -> dict:
    n = len(values)
    m = sum(values) / n
    se = (statistics.stdev(values) / n ** 0.5) if n > 1 else 0.0
    return {"mean": m, "ci95": [m - 1.96 * se, m + 1.96 * se], "n": n}


def channels(rows, cand_key, champ_key) -> dict:
    """The arm's effect split into the identity's channels, paired within deal.

    Against SESTINA the candidate's game and the champion's are two games on
    the same deal, and the split is the identity's: race = 2 dD_us,
    ours = -2 dW_us, theirs = +2 dW_them, summing to the effect exactly.

    In self-play (`champ_key` None) the candidate's team and the champion's
    are the two sides of ONE game, and the identity reads differently:
    with D_us + D_them = 9, margin = (D_us - D_them) - 2 W_us + 2 W_them, so
    race = D_us - D_them and the two error counters collapse into ONE
    channel, errors = 2 (W_them - W_us). A symmetric game cannot separate
    "we declared better" from "they declared worse" -- both are the same
    difference -- so no ours/theirs split is reported there. The first
    version of this function applied the two-game coefficients to the one-
    game counters and double-counted every channel, which the residual
    exposed (9, not 0); the residual is asserted zero for both cases now.
    """
    eff, race, ours, theirs, errors, resid = [], [], [], [], [], []
    for r in rows:
        a = r[cand_key]
        if champ_key is None:
            e = a["margin"]
            rc = a["d_us"] - a["d_them"]
            er = 2 * (a["w_them"] - a["w_us"])
            eff.append(e); race.append(rc); errors.append(er)
            resid.append(e - (rc + er))
        else:
            b = r[champ_key]
            e = a["margin"] - b["margin"]
            rc = 2 * (a["d_us"] - b["d_us"])
            ou = -2 * (a["w_us"] - b["w_us"])
            th = 2 * (a["w_them"] - b["w_them"])
            eff.append(e); race.append(rc); ours.append(ou); theirs.append(th)
            resid.append(e - (rc + ou + th))
    out = {"effect": _mean_ci(eff), "race": _mean_ci(race),
           "max_abs_residual": max(abs(x) for x in resid) if resid else None}
    if champ_key is None:
        out["errors"] = _mean_ci(errors)
        out["note"] = ("one game, two sides: race = D_us - D_them, errors = "
                       "2 (W_them - W_us); ours/theirs are not separable")
    else:
        out["ours"] = _mean_ci(ours)
        out["theirs"] = _mean_ci(theirs)
    return out


def _fmt(x) -> str:
    return f"{x['mean']:+8.4f} [{x['ci95'][0]:+.3f},{x['ci95'][1]:+.3f}]"


def report(rows_by_arm, stage) -> dict:
    out = {"stage": stage, "ship_bar": SHIP_BAR, "prereg": PREREG,
           "rev2_theirs_s1_vs_dylan": REV2_THEIRS, "arms": {}}
    print(f"\n=== P48 {stage}: candidate minus champion, paired on the deal ===")
    print(f"  {'arm':22s}{'vs SESTINA':>26s}{'self-play':>26s}  verdict")
    for label, rows in rows_by_arm.items():
        if not rows:
            continue
        joined = [{"deal": r["deal"], "kv_even": r["kv_even"],
                   "cand": r["sestina_cand"], "champ": r["sestina_champ"]}
                  for r in rows]
        vs = _paired(joined, "cand", "champ")
        vs["by_deal"] = _by_deal(
            joined, [j["cand"]["margin"] - j["champ"]["margin"] for j in joined])
        sp = _self_play(rows)
        sp["by_deal"] = _by_deal(rows, [r["self"]["margin"] for r in rows])

        def clears(x):
            return x["mean"] >= SHIP_BAR and x["ci95"][0] > 0
        verdict = ("CLEARS BOTH" if clears(vs) and clears(sp) else
                   "clears vs SESTINA only" if clears(vs) else
                   "clears self-play only" if clears(sp) else "no")

        def hit(key):
            v = [r[key]["ask_hit"] for r in rows if r[key]["ask_hit"] is not None]
            return sum(v) / len(v) if v else None

        def per_game(key, field):
            return sum(r[key][field] for r in rows) / len(rows)

        def err(key, d, w):
            D = sum(r[key][d] for r in rows)
            return (sum(r[key][w] for r in rows) / D) if D else None

        arm = {
            "spec": ARMS[label], "vs_sestina": vs, "self_play": sp,
            "verdict": verdict,
            "channels": {"vs_sestina": channels(rows, "sestina_cand", "sestina_champ"),
                         "self_play": channels(rows, "self", None)},
            "signals_per_game": {"vs_sestina": per_game("sestina_cand", "signals"),
                                 "self_play": per_game("self", "signals"),
                                 "champion_vs_sestina": per_game("sestina_champ", "signals")},
            "error_rates": {
                "vs_sestina": {"ours_cand": err("sestina_cand", "d_us", "w_us"),
                               "ours_champ": err("sestina_champ", "d_us", "w_us"),
                               "theirs_with_cand": err("sestina_cand", "d_them", "w_them"),
                               "theirs_with_champ": err("sestina_champ", "d_them", "w_them")},
                "self_play": {"cand_side": err("self", "d_us", "w_us"),
                              "champ_side": err("self", "d_them", "w_them")}},
            "fallbacks": sum(r[k]["fallbacks"] for r in rows
                             for k in ("sestina_champ", "sestina_cand", "self")),
            "unfinished": sum(1 for r in rows for k in
                              ("sestina_champ", "sestina_cand", "self")
                              if not r[k]["terminal"]),
            "identity_failures": sum(1 for r in rows for k in
                                     ("sestina_champ", "sestina_cand", "self")
                                     if r[k]["identity_ok"] is False),
            "cand_ask_hit": hit("sestina_cand"), "champ_ask_hit": hit("sestina_champ"),
        }
        out["arms"][label] = arm
        print(f"  {label:22s}{_fmt(vs)}{_fmt(sp):>27s}  {verdict}")
        ch = arm["channels"]["vs_sestina"]
        print(f"    vs SESTINA channels  race {_fmt(ch['race'])}  ours "
              f"{_fmt(ch['ours'])}  theirs {_fmt(ch['theirs'])}  "
              f"max|resid| {ch['max_abs_residual']}")
        chs = arm["channels"]["self_play"]
        print(f"    self-play channels   race {_fmt(chs['race'])}  errors "
              f"{_fmt(chs['errors'])}  max|resid| {chs['max_abs_residual']}")
        sg = arm["signals_per_game"]
        er = arm["error_rates"]["vs_sestina"]
        print(f"    signals/game vs SESTINA {sg['vs_sestina']:.3f}  self-play "
              f"{sg['self_play']:.3f}; their error rate with cand "
              f"{er['theirs_with_cand']:.4f} vs champ {er['theirs_with_champ']:.4f}; "
              f"ask hit cand {arm['cand_ask_hit']:.4f} champ {arm['champ_ask_hit']:.4f}; "
              f"fallbacks {arm['fallbacks']} unfinished {arm['unfinished']} "
              f"identity failures {arm['identity_failures']}")
    return out


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--deals", type=int, default=300)
    ap.add_argument("--arms", default=",".join(DEFAULT_ARMS))
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--out", default=None)
    ap.add_argument("--rescore", default=None, metavar="RESULTS",
                    help="rebuild the report from an existing results file's "
                         "per-pairing rows without replaying a game; the "
                         "rows are the data, the report is a summary of them")
    return ap


def rescore(path: str) -> int:
    d = json.loads(Path(path).read_text())
    rows_by_arm = {l: rows for l, rows in d["per_pair"].items()}
    out = report(rows_by_arm, d.get("stage", "screen"))
    for k in ("seconds", "seed_base", "agent0", "deals", "per_pair"):
        out[k] = d[k]
    out["rescored"] = True
    Path(path).write_text(json.dumps(out, indent=1) + "\n")
    print(f"\nrescored {path}")
    return 0


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    if a.rescore:
        return rescore(a.rescore)
    labels = [x for x in a.arms.split(",") if x]
    for l in labels:
        if l not in ARMS:
            print(f"{l} is not a registered arm", file=sys.stderr)
            return 2
    todo = [(SEED0 + i, ke, l, AGENT0) for l in labels
            for i in range(a.deals) for ke in (True, False)]
    print(f"P48 screen: {len(labels)} arms x {a.deals} deals x 2 parities = "
          f"{len(todo):,} pairings, {3 * len(todo):,} games, seed base "
          f"{SEED0:,}, agent base {AGENT0:,}", flush=True)
    rows_by_arm = {l: [] for l in labels}
    t0 = time.time()
    with Pool(a.jobs) as pool:
        for i, r in enumerate(pool.imap_unordered(_one, todo, chunksize=1)):
            rows_by_arm[r["arm"]].append(r)
            if (i + 1) % 50 == 0:
                print(f"  {i + 1}/{len(todo)} pairings, "
                      f"{(time.time() - t0) / 60:.1f} min", flush=True)
    for l in labels:
        rows_by_arm[l].sort(key=lambda r: (r["deal"], not r["kv_even"]))
    out = report(rows_by_arm, "screen")
    out["seconds"] = round(time.time() - t0, 1)
    out["seed_base"] = SEED0
    out["agent0"] = AGENT0
    out["deals"] = a.deals
    out["per_pair"] = {l: rows_by_arm[l] for l in labels}
    dest = a.out or str(ROOT / "results" / "p48_screen.json")
    Path(dest).write_text(json.dumps(out, indent=1) + "\n")
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
