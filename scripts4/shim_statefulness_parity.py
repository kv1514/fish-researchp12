"""Is our stateless replay the same thing as their arbiter's incremental play?

THE QUESTION THIS ANSWERS, AND WHY IT IS THE ONE WORTH ASKING.
`results/ladder_shape_comparison.json` found that their released ladder runs
BACKWARDS through our bridge: their declaration error climbs monotonically with
their own version number here (4.71% at v0.3 to 20.71% at v0.7) and does not
there. Improving strength does not produce that shape, so something about the
bridge is doing it, and the thing to look for is a mechanism that (a) exists
only on our side and (b) bites later versions harder than earlier ones.

There is an obvious candidate and it has been sitting in `shim_decide.cpp`'s
own docstring the whole time: **the shim is stateless**. It spawns a fresh
process for every decision and replays the entire public log into a
freshly-`reset()` agent. Their arbiter constructs one agent per seat per deal
and feeds it events as they happen. Those two agree only if their agent is a
pure function of (reset state, event sequence). Two reasons it might not be,
both introduced by their v0.4 and leaned on harder by every version after:

  * their belief is an iterative Sinkhorn/IPF fit, and an iterative fit warm-
    started from the previous position need not land where a from-scratch fit
    lands;
  * their test-time search is determinized (det=12) off the agent's RNG, and a
    fresh process re-seeds that stream every decision -- so through our bridge
    their search may draw the SAME determinizations at every turn of the game,
    where in their arbiter the stream advances.

Either would cost them strength here and nothing at home, and would cost the
later versions more. v0.2 and v0.3 are scripted baselines with no fitted belief
and no search, which is exactly where the two ladders agree.

HOW IT IS MEASURED. One game, played once by our engine. At every decision our
bridge makes, the exact stdin script is captured (that is the STATELESS answer,
the one every published number rests on). The same game's events are also fed
to a PERSISTENT shim -- one process for the whole game, each event seen once,
in order, decisions answered inline -- which is what their arbiter does. Then
the two answer streams are diffed, decision by decision.

WHAT EACH OUTCOME MEANS.

  * Identical -> their agent really is a pure function of the event stream, the
    statelessness is free, and this mechanism is dead. The ladder inversion
    needs another explanation and this script has excluded the best candidate.
  * Divergent -> our bridge is not asking their engine the same question their
    arbiter asks it, and every cross-engine absolute in the paper is measured
    through that difference. The rate and the shape of the divergence say how
    much.

WHAT IT CANNOT DO. It cannot say which answer is *better*, only that they
differ; a divergence is not by itself proof that we handicapped them, though it
removes the ground for assuming we did not. And it holds our own side fixed by
construction -- both modes see the identical game -- so it says nothing about
which engine is stronger.

USAGE

    python3 scripts4/shim_statefulness_parity.py --games 6
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.engine import GameState                      # noqa: E402
from fish.observation import Observation               # noqa: E402
from fish.rules import RuleConfig                      # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 7_400_000
AGENT0 = 74_000
MAX_ACTIONS = 600

ONESHOT = ROOT / "external_v07" / "fish_v07_decide"
PERSIST = ROOT / "external_v07" / "fish_v07_persist"


def capture_game(deal_seed: int, kv_even: bool, spec_name: str
                 ) -> list[list[str]]:
    """Every stdin script our bridge sends during one game, in order.

    Each is the FULL header plus the whole replayed history plus one DECIDE, so
    the list is a complete record of what the stateless path asked and in what
    order it asked it.
    """
    from fish4.registry4 import KRAKEN_V1, make_agent
    from fish4.dylan_v07 import DylanV07
    from fish4.dylan_ladder import spec_for

    scripts: list[list[str]] = []
    original = DylanV07._run

    def recording(self, lines):
        scripts.append(list(lines))
        return original(self, lines)

    DylanV07._run = recording
    try:
        rules = RuleConfig(**RULES_D)
        agents = []
        for p in range(6):
            kv = (p % 2 == 0) == kv_even
            agents.append(make_agent(KRAKEN_V1) if kv else make_agent(
                ("dylan_v07", {"spec": spec_for(spec_name)})))
        st = GameState.deal(rules, seed=deal_seed)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
        for _ in range(MAX_ACTIONS):
            if st.is_terminal:
                break
            st.apply(st.turn, agents[st.turn].act(
                Observation.from_state(st, st.turn)))
    finally:
        DylanV07._run = original
    return scripts


def oneshot_answer(lines: list[str]) -> str:
    r = subprocess.run([str(ONESHOT)], input="\n".join(lines) + "\n",
                       capture_output=True, text=True, timeout=180)
    if r.returncode != 0:
        return f"<rc={r.returncode}> {r.stderr.strip()[:120]}"
    return r.stdout.strip()


def _header(lines: list[str]) -> tuple[list[str], list[str], str]:
    """Split a captured script into (header, events, decide line)."""
    head, evs = [], []
    for ln in lines[:-1]:
        (evs if ln.startswith("EV ") else head).append(ln)
    return head, evs, lines[-1]


def persistent_answers(scripts: list[str]) -> list[str]:
    """Replay one seat's decisions through ONE long-lived process.

    Grouped by seat: each seat in their arbiter has its own agent for the whole
    deal, so the persistent side must too. Within a seat the scripts arrive in
    game order and their event lists are prefixes of one another, so the events
    NEW since that seat's last decision are exactly the tail.
    """
    out: list[str] = []
    by_seat: dict[str, list[int]] = {}
    for i, s in enumerate(scripts):
        seat = [l for l in s if l.startswith("SEAT ")][0]
        by_seat.setdefault(seat, []).append(i)

    answers: dict[int, str] = {}
    for seat, idxs in by_seat.items():
        head, _, _ = _header(scripts[idxs[0]])
        proc = subprocess.Popen([str(PERSIST)], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, text=True, bufsize=1)
        try:
            for ln in head:
                proc.stdin.write(ln + "\n")
            shown: list[str] = []
            for i in idxs:
                _, evs, decide = _header(scripts[i])
                # The tail is what this seat has not been shown yet. The
                # persistent stream is only equivalent if each decision's event
                # list EXTENDS the last one; if it ever does not, the run is
                # abandoned rather than patched, because a persistent agent fed
                # the wrong events is not measuring anything.
                if evs[:len(shown)] != shown:
                    raise SystemExit(
                        f"event list at decision {i} is not an extension of "
                        f"the previous one ({len(shown)} shown, "
                        f"{len(evs)} now); abandoning rather than guessing")
                for ln in evs[len(shown):]:
                    proc.stdin.write(ln + "\n")
                shown = evs
                turn = [l for l in scripts[i] if l.startswith("TURN ")]
                for ln in turn:
                    proc.stdin.write(ln + "\n")
                proc.stdin.write(decide + "\n")
                proc.stdin.flush()
                line = proc.stdout.readline()
                answers[i] = line.strip()
            proc.stdin.write("QUIT\n")
            proc.stdin.flush()
        finally:
            try:
                proc.stdin.close()
            except Exception:
                pass
            proc.wait(timeout=60)
    return [answers[i] for i in range(len(scripts))]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--games", type=int, default=6)
    ap.add_argument("--seed", type=int, default=SEED0)
    ap.add_argument("--spec", default="dylan_v07")
    ap.add_argument("--out", default=str(ROOT / "results"
                                         / "shim_statefulness_parity.json"))
    a = ap.parse_args(argv)

    for p in (ONESHOT, PERSIST):
        if not p.exists():
            print(f"missing binary: {p}", file=sys.stderr)
            return 2

    t0 = time.time()
    rows, total, diff = [], 0, 0
    kinds: Counter = Counter()
    examples = []
    for i in range(a.games):
        for kv_even in (True, False):
            scripts = capture_game(a.seed + i, kv_even, a.spec)
            if not scripts:
                continue
            one = [oneshot_answer(s) for s in scripts]
            per = persistent_answers(scripts)
            d = [j for j in range(len(one)) if one[j] != per[j]]
            for j in d:
                kinds[(one[j].split()[0], per[j].split()[0])] += 1
                if len(examples) < 15:
                    examples.append({"deal": a.seed + i, "kv_even": kv_even,
                                     "decision": j,
                                     "stateless": one[j], "persistent": per[j],
                                     "decide": scripts[j][-1]})
            rows.append({"deal": a.seed + i, "kv_even": kv_even,
                         "decisions": len(scripts), "divergent": len(d),
                         "first_divergence": d[0] if d else None})
            total += len(scripts)
            diff += len(d)
            print(f"  deal {a.seed + i} kv_even={kv_even}: "
                  f"{len(d)}/{len(scripts)} decisions differ"
                  + (f", first at #{d[0]}" if d else ""), flush=True)

    out = {
        "question": "does our stateless replay ask their engine the same "
                    "question their arbiter asks it",
        "spec": a.spec,
        "games": len(rows),
        "decisions": total,
        "divergent": diff,
        "divergence_rate": diff / total if total else None,
        "verdict": ("PURE -- statelessness is free" if not diff else
                    "STATEFUL -- the two paths are not the same agent"),
        "kind_changes": {f"{k[0]}->{k[1]}": v for k, v in kinds.items()},
        "per_game": rows,
        "examples": examples,
        "seconds": round(time.time() - t0, 1),
    }
    Path(a.out).write_text(json.dumps(out, indent=1) + "\n")

    print("\n=== stateless replay vs persistent play, their v0.7 ===")
    print(f"  decisions compared   {total:,}")
    print(f"  divergent            {diff:,} "
          f"({100 * diff / total:.2f}%)" if total else "")
    print(f"  VERDICT              {out['verdict']}")
    if kinds:
        print("\n  what changed (stateless -> persistent):")
        for k, v in kinds.most_common():
            print(f"    {k[0]:5} -> {k[1]:5}  {v}")
    print(f"\nwrote {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
