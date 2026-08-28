"""G1 of prereg/gamma_policy_specific.md: what does the mis-signed opponent
model actually cost us against v0.7?

Our sampler re-weights sampled deals by depth^gamma with gamma = +0.35 for
every seat that is not itself. scripts4/choice_curve_foreign.py measured
Dylan's true propensity exponent at -1.0041 [-1.1434, -0.8648] against our own
self-play +1.2071 -- opposite signs. This asks the only question that decides
whether that matters: does it cost sets?

THREE ARMS, all playing OUR deployed spec except for one scalar:

    A  gamma = +0.35   the shipped value
    B  gamma =  0.0    no opponent model at all
    C  gamma = -1.00   his measured exponent

Paired duplicate deals, seats rotated, so every arm sees the identical deal
from the identical seat. The statistic is the paired difference in set margin
against arm A.

WHAT IS FIXED IN ADVANCE, and why it is written in the pre-registration rather
than here: the minimum interesting effect is 0.15 sets/game, and the outcome
we EXPECT is that neither B nor C clears it -- gamma enters as one scalar
re-weighting of a 480-draw sample that is already dominated by hard
constraints. If arm B beats A, our opponent model is a liability against a
foreign policy rather than an asset, which would be the most important result
here and the one we are least expecting.

NOTHING SHIPS ON THIS RUN. Arm C is fitted on v0.7 and measured against v0.7,
which is the exact shape of the error this project already made once with the
endgame ladder. G2 -- the same arms against the v0.3 champion, with no
refitting -- is what would license anything, and it only runs if C clears here.

    py scripts4/g1_gamma_cost.py [n_deals] [n_jobs]
"""

from __future__ import annotations

import json
import os
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import team_of
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.dylan_v07 import BRIDGE_REV

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 1_800_000
AGENT0 = 18_000
MIN_INTERESTING = 0.15
ARMS = {"A_shipped": 0.35, "B_none": 0.0, "C_measured": -1.00}
JOURNAL = Path(os.environ.get(
    "G1_JOURNAL", ROOT / "results" / "g1_gamma_cost_journal.jsonl"))


def _one(args) -> dict:
    deal_seed, kv_even = args
    from fish4.registry4 import V06_DEPLOYED, make_agent
    rules = RuleConfig(**RULES_D)
    out = {"deal": deal_seed, "kv_even": kv_even, "rev": BRIDGE_REV}
    for arm, gamma in ARMS.items():
        agents = []
        for p in range(6):
            if (p % 2 == 0) == kv_even:
                spec = (V06_DEPLOYED[0],
                        dict(V06_DEPLOYED[1], opponent_gamma=gamma))
                agents.append(make_agent(spec))
            else:
                agents.append(make_agent(("dylan_v07", {})))
        st = GameState.deal(rules, seed=deal_seed)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
        for _ in range(600):
            if st.is_terminal:
                break
            st.apply(st.turn,
                     agents[st.turn].act(Observation.from_state(st, st.turn)))
        kv_team = 0 if kv_even else 1
        kv = sum(1 for w in st.set_winner if w == kv_team)
        dy = sum(1 for w in st.set_winner if w == 1 - kv_team)
        out[arm] = {"margin": kv - dy, "terminal": st.is_terminal,
                    "fallbacks": sum(getattr(a, "fallbacks", 0)
                                     for a in agents)}
    return out


def _assert_arms_are_distinct(rows) -> None:
    """Two arms that produce identical play are not two arms.

    G1's first run reported arm B (gamma 0.0) and arm C (gamma -1.00) at
    bit-identical margins over 800 deals, with identical intervals. That was
    not a finding, it was fish4/posterior.py gating the opponent model on
    `gamma > 0.0`, so a negative gamma silently became zero and arm C
    collapsed into arm B. The result LOOKED like a clean measurement, which is
    the dangerous kind of broken.

    A duplicated arm is detectable without knowing the cause: if two arms agree
    on every deal, either the knob does nothing or it was never applied, and
    both mean the run cannot be reported.
    """
    names = list(ARMS)
    for i, a in enumerate(names):
        for bname in names[i + 1:]:
            if all(r[a]["margin"] == r[bname]["margin"] for r in rows):
                raise SystemExit(
                    f"arms {a!r} (gamma {ARMS[a]}) and {bname!r} (gamma "
                    f"{ARMS[bname]}) produced IDENTICAL margins on all "
                    f"{len(rows)} deals. Either the parameter does nothing or "
                    f"it never reached the engine. Refusing to report.")


def report(rows) -> dict:
    _assert_arms_are_distinct(rows)
    n = len(rows)
    base = [r["A_shipped"]["margin"] for r in rows]
    print(f"\n=== G1: what the opponent model's sign costs against v0.7 ===")
    print(f"{n:,} deals, each played once per arm on the identical deal\n")
    print(f"  arm A (gamma +0.35, shipped)   "
          f"{sum(base)/n:+.4f} sets/game")
    out = {"rules": RULES_D, "bridge_rev": BRIDGE_REV, "n_deals": n,
           "min_interesting": MIN_INTERESTING,
           "margin_A": sum(base) / n, "arms": {}}
    for arm in ("B_none", "C_measured"):
        d = [r[arm]["margin"] - r["A_shipped"]["margin"] for r in rows]
        m = sum(d) / n
        var = sum((x - m) ** 2 for x in d) / (n - 1)
        se = (var / n) ** 0.5
        lo, hi = m - 1.96 * se, m + 1.96 * se
        clears = lo > MIN_INTERESTING
        worse = hi < -MIN_INTERESTING
        verdict = ("BEATS the shipped arm" if clears else
                   "WORSE than shipped" if worse else
                   "inside the bar -- no detectable difference that matters")
        print(f"  arm {arm:12s} gamma {ARMS[arm]:+.2f}   "
              f"{sum(r[arm]['margin'] for r in rows)/n:+.4f} sets/game")
        print(f"       vs shipped: {m:+.4f}  [{lo:+.4f}, {hi:+.4f}]   {verdict}")
        out["arms"][arm] = {"gamma": ARMS[arm], "effect": m, "ci95": [lo, hi],
                            "margin": sum(r[arm]["margin"] for r in rows) / n,
                            "verdict": verdict}
    fb = sum(r[a]["fallbacks"] for r in rows for a in ARMS)
    unf = sum(1 for r in rows for a in ARMS if not r[a]["terminal"])
    print(f"\n  bridge fallbacks {fb}   unfinished {unf}")
    print("  NOTHING SHIPS ON THIS RUN: arm C is fitted on v0.7 and measured\n"
          "  against v0.7. G2 against the v0.3 champion is what would license\n"
          "  anything, and only if C clears here.")
    out["bridge_fallbacks"] = fb
    out["unfinished"] = unf
    return out


G1_KEYS = {"deal", "kv_even", "rev"}


def _load_journal():
    """Read the journal, and refuse to read one that is not ours.

    A row missing the G1 shape is not an old revision to skip past: it
    means something else wrote to this path.  G1's first journal was
    lost exactly that way -- a sibling process overwrote the file, the
    `rev` filter skipped all 478 foreign rows without a word, and a
    clobbered journal read as an empty one.  The silence was the bug.
    A resumable runner that cannot tell "nothing here yet" from "this
    is somebody else's file" will happily replay 17 minutes of work
    and call the result reproducible.
    """
    done, rows = set(), []
    if not JOURNAL.exists():
        return done, rows
    for n, line in enumerate(JOURNAL.read_text().splitlines(), 1):
        if not line.strip():
            continue
        r = json.loads(line)
        if not G1_KEYS <= r.keys():
            raise SystemExit(
                f"{JOURNAL}:{n} is not a G1 row (keys present: "
                f"{sorted(r)}).  Something else wrote to this journal. "
                f"Move it aside; do not append to it.")
        if r["rev"] != BRIDGE_REV:
            continue
        key = (r["deal"], r["kv_even"])
        if key in done:
            continue
        done.add(key)
        rows.append(r)
    return done, rows


def main(n_deals: int = 400, n_jobs: int = 0) -> int:
    n_jobs = n_jobs or max(1, (os.cpu_count() or 2))
    done, rows = _load_journal()
    todo = [(SEED0 + i, ke) for i in range(n_deals) for ke in (True, False)
            if (SEED0 + i, ke) not in done]
    print(f"{len(done):,} journalled, {len(todo):,} to play on {n_jobs} workers",
          flush=True)
    t0 = time.time()
    if todo:
        with Pool(n_jobs) as pool, JOURNAL.open("a") as fh:
            for i, r in enumerate(pool.imap_unordered(_one, todo, chunksize=2)):
                rows.append(r)
                fh.write(json.dumps(r) + "\n")
                if (i + 1) % 40 == 0:
                    print(f"  {i+1:,}/{len(todo):,}  "
                          f"{(time.time()-t0)/60:.1f} min", flush=True)
                    fh.flush()
    if len(rows) < 80:
        print(f"{len(rows)} deals; too few to report")
        return 1
    out = report(rows)
    (ROOT / "results" / "g1_gamma_cost.json").write_text(json.dumps(out, indent=1))
    print("wrote results/g1_gamma_cost.json")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 400,
                          int(a[1]) if len(a) > 1 else 0))
