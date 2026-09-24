"""P46 screen (Stage 1) and confirm (Stage 2): the two halves of C1b, two populations.

Registered in `prereg/kraken_v12_belief_grid.md`; that document fixes the arms,
the seeds, the bar, the order and the predicted outcome, and this file only
executes it. It is `scripts4/p45_screen.py` with its own ARMS and constants,
which in turn is the dual-population design of `scripts4/v12_screen.py`:
champion and candidate each play the SAME deal against SESTINA v1.0 through
BRIDGE_REV 3 on both parities, plus candidate-versus-champion self-play on the
same deal, so every reported difference is within a deal.

WHAT THE FOUR ARMS SEPARATE. P43's C1b (`opponent_gamma = 0.0`) switched the
opponent model off on SESTINA's three seats AND on our two teammates, because
`gamma_team` defaults to `opponent_gamma`. Its -0.59 / -1.07 is therefore a
two-knob number, and the paper's sentence "being wrong about an opponent's
propensity beats having no opinion" rests on it. The arms take it apart:

  E0  opponent_gamma = 0.0                    C1b replicated on THIS seed block,
                                              so E1 - E0 and E2 - E0 are within deal
  E1  opponent_gamma = 0.0, gamma_team = 0.35 model off on SESTINA's seats only;
                                              teammates keep the champion's
  E2  opponent_gamma = 0.35, gamma_team = 0.0 model off on our teammates only;
                                              SESTINA's seats keep the champion's
  G   opponent_gamma = 0.7                    the upward cell of the Stage 0 grid

WHY E0-E2 HAVE NO FUTILITY SCREEN. A belief-level screen on them cannot fail:
they are the arms whose belief the Stage 0 grid already scores, and their
purpose is the within-deal decomposition of C1b, not a ship. Their only gates
are the void conditions (any fallback, any unfinished game, any zero-width
interval, any IllegalAction). No equivalence claim is made at any margin.

WHY G IS CONDITIONAL. G is played only if Stage 0's licensing rule licenses
cell (0.7, 0.7) in both blocks at both budgets; otherwise it is recorded as
"not licensed" and no game is played. That decision is read off
`results/p46_belief_grid.json` by the operator, and this script enforces the
two mechanical halves of it: it refuses to run at all until that file is on
disk (`--require-stage0`, the registration's "runs only after Stage 0 has been
written"), and G is never in the default `--arms`; it runs only when named.

WHAT DIFFERS FROM P45'S FILE, BESIDES THE CONSTANTS AND THE ARMS.
* `_play` is re-typed here rather than imported, because `v12_screen._play`
  reads its module-level `AGENT0` at call time and the registration gives the
  two stages different agent-seed bases (107,000 screen, 108,000 confirm).
  The base travels inside each job tuple so it reaches every pool worker
  regardless of the start method. `_paired` and `_score` are still imported.
* The report adds the paired contrasts E1 - E0 and E2 - E0 (each arm's
  candidate margin against SESTINA, joined on (deal, parity)), and next to
  every 1.96-SE interval a second interval clustered by deal with
  `fish4.clustered.cluster_ci`, because the two parities of one deal share the
  hands and are not two independent pairings.
* Every per-pairing row is written to the output (`per_pair`), as
  `v12_screen.py` does and `p45_screen.py` did not.
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

from fish.engine import GameState                            # noqa: E402
from fish.observation import Observation                     # noqa: E402
from fish.rules import RuleConfig                            # noqa: E402
from fish4.clustered import cluster_ci                       # noqa: E402
from scripts4.v12_screen import MAX_ACTIONS, _paired, _score  # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}
SCREEN_SEED = 10_700_000
CONFIRM_SEED = 10_800_000
#: Agent-seed base per stage: seat p in deal d seeds at base + d*13 + p.
AGENT0 = {"screen": 107_000, "confirm": 108_000}
SHIP_BAR = 0.15
PREREG = "prereg/kraken_v12_belief_grid.md"
#: Stage 0's output. Stage 1 does not start until it exists.
STAGE0_RESULT = Path("results") / "p46_belief_grid.json"

#: label -> the change from V06_DEPLOYED. Fixed by the registration.
#: The labels carry no "." on purpose: the paper's figure-pinning manifest
#: addresses nested values by splitting a dotted path, so "0.7" would split.
ARMS = {
    "E0_gamma_off": {"opponent_gamma": 0.0},
    "E1_off_on_sestina": {"opponent_gamma": 0.0, "gamma_team": 0.35},
    "E2_off_on_teammates": {"opponent_gamma": 0.35, "gamma_team": 0.0},
    "G_gamma_07": {"opponent_gamma": 0.7},
}
#: The registered order for the one Stage 1 job. G is not here: it runs only
#: when named explicitly, after Stage 0 has licensed it.
DEFAULT_ARMS = ("E0_gamma_off", "E1_off_on_sestina", "E2_off_on_teammates")
#: (label, minuend, subtrahend) for the within-deal contrasts the registration
#: reports. Computed only when both arms are present in the run.
CONTRASTS = (("E1_minus_E0", "E1_off_on_sestina", "E0_gamma_off"),
             ("E2_minus_E0", "E2_off_on_teammates", "E0_gamma_off"))


def agent0_for(stage: str) -> int:
    return AGENT0[stage]


def _play(agents, deal_seed, rules, agent0):
    """`v12_screen._play` with the agent-seed base as an argument."""
    st = GameState.deal(rules, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, agent0 + deal_seed * 13 + p)
    for _ in range(MAX_ACTIONS):
        if st.is_terminal:
            break
        st.apply(st.turn, agents[st.turn].act(
            Observation.from_state(st, st.turn)))
    return st


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

    # Population 1: against SESTINA through BRIDGE_REV 3, champion and
    # candidate on the SAME deal, so the difference is within a deal.
    for who, spec in (("champ", KRAKEN_V1), ("cand", cand)):
        agents = seat(spec, ("dylan_v07", {}))
        st = _play(agents, deal_seed, rules, agent0)
        out[f"sestina_{who}"] = _score(st, our_team)
        out[f"sestina_{who}"]["fallbacks"] = sum(
            getattr(a, "fallbacks", 0) for a in agents)

    # Population 2: self-play, candidate's team against the champion's.
    st = _play(seat(cand, KRAKEN_V1), deal_seed, rules, agent0)
    out["self"] = _score(st, our_team)
    return out


def _by_deal(rows, values):
    """A second interval on the same numbers, clustered on the deal, since the
    two parities of one deal are not two independent pairings."""
    mu, hw, k = cluster_ci(values, [r["deal"] for r in rows])
    return {"mean": mu, "ci95": None if hw is None else [mu - hw, mu + hw],
            "clusters": k}


def _self_play(rows) -> dict:
    d = [r["self"]["margin"] for r in rows]
    se = (statistics.stdev(d) / len(d) ** 0.5) if len(d) > 1 else 0.0
    m = sum(d) / len(d)
    return {"mean": m, "ci95": [m - 1.96 * se, m + 1.96 * se], "n": len(d)}


def _contrast(rows_a, rows_b, key) -> dict | None:
    """Arm A minus arm B on `key`'s margin, joined on (deal, parity)."""
    b = {(r["deal"], r["kv_even"]): r for r in rows_b}
    joined = [{"deal": r["deal"], "kv_even": r["kv_even"],
               "a": r[key], "b": b[(r["deal"], r["kv_even"])][key]}
              for r in rows_a if (r["deal"], r["kv_even"]) in b]
    if not joined:
        return None
    out = _paired(joined, "a", "b")
    out["by_deal"] = _by_deal(
        joined, [j["a"]["margin"] - j["b"]["margin"] for j in joined])
    return out


def _fmt(x) -> str:
    return f"{x['mean']:+8.4f} [{x['ci95'][0]:+.3f},{x['ci95'][1]:+.3f}]"


def report(rows_by_arm, stage) -> dict:
    out = {"stage": stage, "ship_bar": SHIP_BAR, "prereg": PREREG,
           "arms": {}, "contrasts": {}}
    print(f"\n=== P46 {stage}: candidate minus champion, paired on the deal ===")
    print(f"  {'arm':20s}{'vs SESTINA':>26s}{'self-play':>26s}  verdict")
    for label, rows in rows_by_arm.items():
        if not rows:
            out["arms"][label] = {"n": 0}
            print(f"  {label:20s}  no rows")
            continue
        vs = _paired(rows, "sestina_cand", "sestina_champ")
        vs["by_deal"] = _by_deal(
            rows, [r["sestina_cand"]["margin"] - r["sestina_champ"]["margin"]
                   for r in rows])
        sp = _self_play(rows)
        sp["by_deal"] = _by_deal(rows, [r["self"]["margin"] for r in rows])

        def clears(x):
            return x["mean"] >= SHIP_BAR and x["ci95"][0] > 0

        verdict = ("CLEARS BOTH" if clears(vs) and clears(sp) else
                   "OPPONENT-SPECIFIC" if clears(vs) else "no")
        fb = sum(r["sestina_cand"]["fallbacks"] + r["sestina_champ"]["fallbacks"]
                 for r in rows)
        unf = sum(1 for r in rows for k in
                  ("sestina_cand", "sestina_champ", "self")
                  if not r[k]["terminal"])
        out["arms"][label] = {
            "vs_sestina": vs, "self_play": sp, "verdict": verdict,
            "fallbacks": fb, "unfinished": unf,
            "cand_ask_hit": sum(r["sestina_cand"]["ask_hit"] or 0
                                for r in rows) / len(rows),
            "champ_ask_hit": sum(r["sestina_champ"]["ask_hit"] or 0
                                 for r in rows) / len(rows),
        }
        print(f"  {label:20s}{_fmt(vs)}{_fmt(sp):>27s}  {verdict}")
        print(f"    ask hit rate  candidate {out['arms'][label]['cand_ask_hit']:.4f}"
              f"   champion {out['arms'][label]['champ_ask_hit']:.4f}")
        if fb or unf:
            print(f"    VOID: fallbacks {fb} unfinished {unf}")

    # The registration's within-deal contrasts, only when both arms ran.
    for name, a, b in CONTRASTS:
        if not (rows_by_arm.get(a) and rows_by_arm.get(b)):
            continue
        c = {"vs_sestina": _contrast(rows_by_arm[a], rows_by_arm[b],
                                     "sestina_cand"),
             "self_play": _contrast(rows_by_arm[a], rows_by_arm[b], "self")}
        if c["vs_sestina"] is None:
            continue
        out["contrasts"][name] = c
        print(f"  {name:20s}{_fmt(c['vs_sestina'])}"
              f"{_fmt(c['self_play']):>27s}  "
              f"(n = {c['vs_sestina']['n']}, {a} - {b})")
    return out


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--deals", type=int, default=300)
    ap.add_argument("--stage", choices=("screen", "confirm"), default="screen")
    ap.add_argument("--arms", default=",".join(DEFAULT_ARMS),
                    help="comma-separated labels; G_gamma_07 only if named")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--out", default=None)
    ap.add_argument("--require-stage0", action=argparse.BooleanOptionalAction,
                    default=True,
                    help=f"refuse to run unless {STAGE0_RESULT} exists "
                         "(--no-require-stage0 is for tests only)")
    return ap


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)

    stage0 = ROOT / STAGE0_RESULT
    if a.require_stage0 and not stage0.exists():
        print(f"refusing to run: Stage 0 has not been written to disk "
              f"({stage0} is absent). The registration runs Stage 1 only "
              f"after it; --no-require-stage0 is for tests only.",
              file=sys.stderr)
        return 2

    seed0 = SCREEN_SEED if a.stage == "screen" else CONFIRM_SEED
    agent0 = agent0_for(a.stage)
    labels = [x for x in a.arms.split(",") if x]
    for l in labels:
        if l not in ARMS:
            print(f"{l} is not a registered arm", file=sys.stderr)
            return 2
    todo = [(seed0 + i, ke, l, agent0) for l in labels
            for i in range(a.deals) for ke in (True, False)]
    print(f"P46 {a.stage}: {len(labels)} arms x {a.deals} deals x 2 parities "
          f"= {len(todo):,} pairings, {3 * len(todo):,} games, "
          f"seed base {seed0:,}, agent base {agent0:,}", flush=True)

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
    out = report(rows_by_arm, a.stage)
    out["seconds"] = round(time.time() - t0, 1)
    out["seed_base"] = seed0
    out["agent0"] = agent0
    out["deals"] = a.deals
    out["stage0_present"] = stage0.exists()
    out["per_pair"] = {l: rows_by_arm[l] for l in labels}
    dest = a.out or str(ROOT / "results" / f"p46_{a.stage}.json")
    Path(dest).write_text(json.dumps(out, indent=1) + "\n")
    print(f"\nwrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
