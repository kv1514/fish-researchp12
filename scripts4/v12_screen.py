"""P43 screen: three candidates, two populations each, paired on identical deals.

Registered in `prereg/kraken_v12_vs_sestina.md` before any arm here was played.
Read that first; this file only executes it.

WHAT IT MEASURES. For each candidate, two paired contrasts:

  vs SESTINA   candidate and champion each play the SAME deal against their
               engine through BRIDGE_REV 3. The statistic is the per-deal
               difference in our set margin.
  self-play    candidate's team against champion's team on the same deal.

BOTH must clear +0.15 with an interval clear of zero for a candidate to ship.
The second is not ceremony: a change that beats one opponent and nothing else
is an exploit of that opponent, and this project has already withdrawn a
feature -- the endgame ladder above m=2 -- for exactly that shape. A candidate
that clears against SESTINA and fails self-play is reported as opponent-
specific and left out of v1.2.

WHY THE CHAMPION ARM IS PLAYED HERE RATHER THAN READ FROM THE BASELINE.
`results/mega_match.json` has the champion against SESTINA at -0.5250 over its
own seed block. Differencing a candidate on THIS block against a champion on
THAT one is an unpaired comparison wearing a paired label, and at this block
size the deal variation is larger than the effect being looked for. So the
champion plays every deal here too, and every reported difference is within a
deal.

THE ARMS ARE FIXED IN THE REGISTRATION. Nothing is added to this list without
a new registration, because choosing arms after seeing a screen is the
forking-paths failure the appendix of the paper argues against at length.
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

from fish.engine import AskEvent, ClaimEvent, GameState   # noqa: E402
from fish.observation import Observation                  # noqa: E402
from fish.rules import RuleConfig                         # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}
SCREEN_SEED = 9_300_000
CONFIRM_SEED = 9_400_000
AGENT0 = 93_000
MAX_ACTIONS = 600
SHIP_BAR = 0.15

#: Their fitted choice exponent at BRIDGE_REV 3
#: (`results/choice_curve_foreign.json`, alpha = -1.1055). Arm C of C1 applies
#: it to THEIR seats and leaves teammates at the shipped value, which is what
#: `gamma_team` is for.
ALPHA_HAT = -1.1055

#: label -> the single change from V06_DEPLOYED. Fixed by the registration.
ARMS = {
    "C1b_gamma_off": {"opponent_gamma": 0.0},
    "C1c_gamma_fitted": {"opponent_gamma": ALPHA_HAT, "gamma_team": 0.35},
    "C2_avoid_doomed": {"avoid_doomed_asks": True},
    "C3_depth_atask": {"depth_mode": "atask"},
}


def _play(agents, deal_seed, rules):
    st = GameState.deal(rules, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
    for _ in range(MAX_ACTIONS):
        if st.is_terminal:
            break
        st.apply(st.turn, agents[st.turn].act(
            Observation.from_state(st, st.turn)))
    return st


def _score(st, our_team):
    ours = sum(1 for w in st.set_winner if w == our_team)
    theirs = sum(1 for w in st.set_winner if w == 1 - our_team)
    hits = asks = 0
    for e in st.history:
        if isinstance(e, AskEvent) and (e.asker % 2) == our_team:
            asks += 1
            hits += int(e.success)
    return {"margin": ours - theirs, "terminal": st.is_terminal,
            "ask_hit": hits / asks if asks else None, "asks": asks}


def _one(job) -> dict:
    deal_seed, kv_even, label = job
    from fish4.registry4 import KRAKEN_V1, make_agent

    rules = RuleConfig(**RULES_D)
    cand = ("fishbot4", dict(KRAKEN_V1[1], **ARMS[label]))
    our_team = 0 if kv_even else 1
    out = {"deal": deal_seed, "kv_even": kv_even, "arm": label}

    # -- population 1: against their engine, champion and candidate paired ----
    for who, spec in (("champ", KRAKEN_V1), ("cand", cand)):
        agents = [make_agent(spec) if (p % 2 == 0) == kv_even
                  else make_agent(("dylan_v07", {})) for p in range(6)]
        st = _play(agents, deal_seed, rules)
        out[f"sestina_{who}"] = _score(st, our_team)
        out[f"sestina_{who}"]["fallbacks"] = sum(
            getattr(a, "fallbacks", 0) for a in agents)

    # -- population 2: self-play, candidate against the champion -------------
    agents = [make_agent(cand) if (p % 2 == 0) == kv_even
              else make_agent(KRAKEN_V1) for p in range(6)]
    st = _play(agents, deal_seed, rules)
    out["self"] = _score(st, our_team)
    return out


def _paired(rows, a, b):
    d = [r[a]["margin"] - r[b]["margin"] for r in rows]
    n = len(d)
    m = sum(d) / n
    se = (statistics.stdev(d) / n ** 0.5) if n > 1 else 0.0
    return {"mean": m, "ci95": [m - 1.96 * se, m + 1.96 * se], "n": n}


def report(rows_by_arm, stage) -> dict:
    out = {"stage": stage, "ship_bar": SHIP_BAR, "arms": {}}
    print(f"\n=== P43 {stage}: candidate minus champion, paired ===")
    print(f"  {'arm':20s}{'vs SESTINA':>26s}{'self-play':>26s}  verdict")
    for label, rows in rows_by_arm.items():
        vs = _paired(rows, "sestina_cand", "sestina_champ")
        sp = {"mean": sum(r["self"]["margin"] for r in rows) / len(rows)}
        d = [r["self"]["margin"] for r in rows]
        se = (statistics.stdev(d) / len(d) ** 0.5) if len(d) > 1 else 0.0
        sp["ci95"] = [sp["mean"] - 1.96 * se, sp["mean"] + 1.96 * se]
        sp["n"] = len(d)

        def clears(x):
            return x["mean"] >= SHIP_BAR and x["ci95"][0] > 0

        verdict = ("CLEARS BOTH" if clears(vs) and clears(sp) else
                   "OPPONENT-SPECIFIC" if clears(vs) else
                   "no")
        out["arms"][label] = {
            "vs_sestina": vs, "self_play": sp, "verdict": verdict,
            "fallbacks": sum(r["sestina_cand"]["fallbacks"]
                             + r["sestina_champ"]["fallbacks"] for r in rows),
            "unfinished": sum(1 for r in rows for k in
                              ("sestina_cand", "sestina_champ", "self")
                              if not r[k]["terminal"]),
            "cand_ask_hit": sum(r["sestina_cand"]["ask_hit"] or 0
                                for r in rows) / len(rows),
            "champ_ask_hit": sum(r["sestina_champ"]["ask_hit"] or 0
                                 for r in rows) / len(rows),
        }
        f = out["arms"][label]
        print(f"  {label:20s}"
              f"{vs['mean']:+8.4f} [{vs['ci95'][0]:+.3f},{vs['ci95'][1]:+.3f}]"
              f"{sp['mean']:+9.4f} [{sp['ci95'][0]:+.3f},{sp['ci95'][1]:+.3f}]"
              f"  {verdict}")
        if f["fallbacks"] or f["unfinished"]:
            print(f"    VOID: fallbacks {f['fallbacks']} "
                  f"unfinished {f['unfinished']}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--deals", type=int, default=300)
    ap.add_argument("--stage", choices=("screen", "confirm"), default="screen")
    ap.add_argument("--arms", default=",".join(ARMS))
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    seed0 = SCREEN_SEED if a.stage == "screen" else CONFIRM_SEED
    labels = [x for x in a.arms.split(",") if x]
    for l in labels:
        if l not in ARMS:
            print(f"{l} is not a registered arm", file=sys.stderr)
            return 2
    todo = [(seed0 + i, ke, l) for l in labels
            for i in range(a.deals) for ke in (True, False)]
    print(f"P43 {a.stage}: {len(labels)} arms x {a.deals} deals x 2 parities "
          f"= {len(todo):,} pairings, {3 * len(todo):,} games, "
          f"seed base {seed0:,}", flush=True)

    rows_by_arm = {l: [] for l in labels}
    t0 = time.time()
    with Pool(a.jobs) as pool:
        for i, r in enumerate(pool.imap_unordered(_one, todo, chunksize=1)):
            rows_by_arm[r["arm"]].append(r)
            if (i + 1) % 50 == 0:
                print(f"  {i + 1}/{len(todo)} pairings, "
                      f"{(time.time() - t0) / 60:.1f} min", flush=True)

    out = report(rows_by_arm, a.stage)
    out["seconds"] = round(time.time() - t0, 1)
    out["seed_base"] = seed0
    out["deals"] = a.deals
    out["per_pair"] = {l: rows_by_arm[l] for l in labels}
    dest = a.out or str(ROOT / "results" / f"v12_{a.stage}.json")
    Path(dest).write_text(json.dumps(out, indent=1) + "\n")
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
