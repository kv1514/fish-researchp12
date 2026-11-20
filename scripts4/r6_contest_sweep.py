"""R6 of prereg/rules_award_baseline.md: contestation and silence vs Dylan.

Stage 1 screen: every arm (baseline, five contest doses, two silence doses)
plays 3 copies against 3x dylan_v07 on identical deals and rotations,
journalled per (deal, rotation, arm). Analysis pairs each arm against the
baseline arm per (deal, rotation).

    py scripts4/r6_contest_sweep.py [n_deals] [stage]

stage "screen" (default) uses seeds 333000+; stage "confirm:<arm>" uses
fresh seeds 334000+ with only that arm and the baseline.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.registry4 import make_agent

BASE = {"opponent_gamma": 0.35, "n_draws": 480, "w_lookahead": 0.25,
        "lookahead_depth": 3, "lookahead_beam": 4, "endgame_m": 0}
ARMS = {
    "base": dict(BASE),
    "c-1.0": dict(BASE, w_contest=-1.0),
    "c-0.3": dict(BASE, w_contest=-0.3),
    "c+0.3": dict(BASE, w_contest=0.3),
    "c+1.0": dict(BASE, w_contest=1.0),
    "c+3.0": dict(BASE, w_contest=3.0),
    "d0.7": dict(BASE, silence_delta=0.7),
    "d0.9": dict(BASE, silence_delta=0.9),
}
RULES = RuleConfig(wrong_distribution_outcome="opponent")


def play(deal_seed: int, kv_even: bool, arm: str, agent0: int) -> dict:
    agents = []
    for p in range(6):
        kv = (p % 2 == 0) == kv_even
        agents.append(make_agent(("fishbot4", dict(ARMS[arm]))) if kv
                      else make_agent(("dylan_v07", {})))
    st = GameState.deal(RULES, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, RULES, agent0 + deal_seed * 13 + p)
    for _ in range(600):
        if st.is_terminal:
            break
        st.apply(st.turn,
                 agents[st.turn].act(Observation.from_state(st, st.turn)))
    fb = sum(getattr(a, "fallbacks", 0) for a in agents)
    kv_team = 0 if kv_even else 1
    kv = sum(1 for w in st.set_winner if w == kv_team)
    dy = sum(1 for w in st.set_winner if w == 1 - kv_team)
    return {"deal": deal_seed, "kv_even": kv_even, "arm": arm,
            "kv": kv, "dylan": dy, "margin": kv - dy,
            "terminal": st.is_terminal, "fallbacks": fb}


def _claim_lock(journal: Path):
    """One writer per journal, or none.

    Two drivers of this script raced into one journal during the R6 screen:
    a background runner and the foreground chunks that replaced it when the
    background one turned out to stall whenever the container idled. It cost
    2,888 redundant games and, worse, could have gone unnoticed. It did no
    damage -- every duplicated (deal, rotation, arm) came back bit-identical,
    which is a fact worth having checked rather than assumed -- but a
    measurement harness that can be run twice into the same file is one
    nondeterminism away from silently mixing two populations.

    O_EXCL is the whole mechanism: it is atomic, and a stale lock from a
    killed run is removed by hand, deliberately, after checking nothing else
    is running.
    """
    import os
    lock = journal.with_suffix(journal.suffix + ".lock")
    try:
        fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise SystemExit(
            f"{lock} exists: another run of this sweep is writing "
            f"{journal.name}. If you are sure none is (check `ps`), remove "
            f"the lock and rerun.")
    os.write(fd, f"pid {os.getpid()}\n".encode())
    os.close(fd)
    import atexit
    atexit.register(lambda: lock.unlink(missing_ok=True))


def run(n_deals: int, seed0: int, agent0: int, arms: list[str],
        journal: Path, out_name: str) -> int:
    _claim_lock(journal)
    done = set()
    rows = []
    if journal.exists():
        for line in journal.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                done.add((r["deal"], r["kv_even"], r["arm"]))
                rows.append(r)
    print(f"{len(done)} games already journalled", flush=True)
    for i in range(n_deals):
        seed = seed0 + i
        for kv_even in (True, False):
            for arm in arms:
                if (seed, kv_even, arm) in done:
                    continue
                t0 = time.time()
                r = play(seed, kv_even, arm, agent0)
                r["seconds"] = round(time.time() - t0, 1)
                rows.append(r)
                with journal.open("a") as fh:
                    fh.write(json.dumps(r) + "\n")
        if (i + 1) % 10 == 0:
            print(f"  deal {i + 1}/{n_deals}", flush=True)

    by = {}
    for r in rows:
        by[(r["deal"], r["kv_even"], r["arm"])] = r
    fbs = sum(r["fallbacks"] for r in by.values())
    print(f"\npaired vs base, {fbs} bridge fallbacks over {len(by)} games:")
    result = {"rules": RULES.to_dict(), "arms": {}, "bridge_fallbacks": fbs}
    for arm in arms:
        if arm == "base":
            continue
        diffs = []
        for (deal, ke, a), r in by.items():
            if a != arm:
                continue
            b = by.get((deal, ke, "base"))
            if b is not None:
                diffs.append(r["margin"] - b["margin"])
        n = len(diffs)
        if n < 20:
            print(f"  {arm:6s}: {n} pairs, too few")
            continue
        m = sum(diffs) / n
        var = sum((x - m) ** 2 for x in diffs) / (n - 1)
        se = (var / n) ** 0.5
        lo, hi = m - 1.96 * se, m + 1.96 * se
        base_margin = sum(r["margin"] for r in by.values()
                          if r["arm"] == "base") / max(
            1, sum(1 for r in by.values() if r["arm"] == "base"))
        arm_margin = sum(r["margin"] for r in by.values()
                         if r["arm"] == arm) / max(
            1, sum(1 for r in by.values() if r["arm"] == arm))
        print(f"  {arm:6s}: {m:+.4f} [{lo:+.4f}, {hi:+.4f}]  n={n}  "
              f"(margin {arm_margin:+.3f} vs base {base_margin:+.3f})")
        # Dot-free key: the paper's number manifest addresses nested values
        # by a dot-separated path, so an arm named "c+3.0" would be read as
        # two levels. The journal keeps the human names; only this index is
        # sanitised, so nothing already recorded is orphaned.
        result["arms"][arm.replace(".", "")] = {
            "arm": arm, "n_pairs": n, "effect": m, "ci95": [lo, hi],
            "margin": arm_margin, "base_margin": base_margin}
    (ROOT / "results" / out_name).write_text(json.dumps(result, indent=1))
    print(f"wrote results/{out_name}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    n = int(a[0]) if a else 250
    stage = a[1] if len(a) > 1 else "screen"
    if stage == "screen":
        raise SystemExit(run(
            n, 333_000, 3330, list(ARMS),
            ROOT / "results" / "r6_screen_journal.jsonl",
            "r6_screen.json"))
    if stage.startswith("confirm:"):
        arm = stage.split(":", 1)[1]
        assert arm in ARMS and arm != "base", f"unknown arm {arm!r}"
        raise SystemExit(run(
            n, 334_000, 3340, ["base", arm],
            ROOT / "results" / "r6_confirm_journal.jsonl",
            "r6_confirm.json"))
    raise SystemExit(f"unknown stage {stage!r}")
