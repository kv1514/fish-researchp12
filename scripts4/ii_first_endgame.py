"""One exact deviation per game, so the number is comparable to exploitability.

``scripts4/ii_endgame.py`` averages the gain over POSITIONS, and a game can
contain several. That is the right unit for "how well does the champion play
the endgame" and the wrong one for "how exploitable is the champion", because
summing gains across positions in one game double-counts a continuation the
deviator only gets to play once.

So this takes exactly ONE position per game -- the first m = 1 decision with
genuinely hidden cards -- and reports the exact gain there. The deviator plays
champion-identically up to that point and optimally from it, so the number is a
LOWER BOUND on what a single seat gains by deviating from the all-champion
profile over the whole game, in the same units ``scripts4/exploitability.py``
uses: a team differential, where a half-suit changing hands moves it by 2.

WHAT IT IS A LOWER BOUND ON, EXACTLY
------------------------------------
Not on exploitability against the champion as it plays. The opponents here are
a DETERMINISTIC REALISATION of the champion, seeded from a hash of the
observation, and best-responding to a realisation one can predict is easier
than beating the mixture it came from. The champion mixes at most of these
decisions -- over 41 hidden m = 1 information sets at 12 seeds each it repeats
its move every time in only 32% of them. So this bounds the deterministic
realisation, and the honest comparison to the sampled interval has to say so.

    py scripts4/ii_first_endgame.py [n_games]
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.exact_ii import (DEFAULT_DEADLINE, MAX_NODES, ExactII, SolveTimeout,
                            _clone, consistent_deals)
from fish4.registry4 import make_agent

SPEC = ("fishbot4", {"opponent_gamma": 0.35})
MAX_SUPPORT = 24
MIN_RESULT_GAMES = 30
JOURNAL = ROOT / "results" / "ii_first_endgame_journal.jsonl"


def _solver_fingerprint() -> str:
    """Same guard as scripts4/ii_endgame.py, for the same reason: a journal
    written by a different solver is not a shortcut, it is last week's answer
    reported under this week's name."""
    return hashlib.sha256(
        (ROOT / "fish4" / "exact_ii.py").read_bytes()).hexdigest()[:12]


def main(n_games: int = 60) -> int:
    rules = RuleConfig()
    fp = _solver_fingerprint()
    print(f"  solver fingerprint {fp}")
    done = {}
    stale = undetailed = 0
    if JOURNAL.exists():
        for line in JOURNAL.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("solver") != fp:
                    stale += 1
                    continue
                if r.get("kind") == "none" and "reason" not in r:
                    # Not a solver mismatch. Counting it as one printed
                    # "ignoring 36 journalled games from an older solver" for
                    # rows the current solver wrote, which is the same lumping
                    # of distinct causes under one label that the breakdown
                    # below exists to undo.
                    undetailed += 1
                    continue
                done[r["game"]] = r
    if stale:
        print(f"  ignoring {stale} journalled games from an older solver")
    if undetailed:
        print(f"  redoing {undetailed} journalled games recorded before the "
              f"'why nothing here' breakdown existed")
    rows = list(done.values())
    for g in range(n_games):
        if g in done:
            continue
        agents = [make_agent(SPEC) for _ in range(NUM_PLAYERS)]
        st = GameState.deal(rules, seed=61_000 + g)
        ar = random.Random(61_500 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        # "none" covers three different things and used to hide all of them
        # behind one word. 36 of 60 games landed here, which is most of the
        # denominator of the headline, so what it MEANS is not a detail:
        #   pinned  -- an m = 1 decision arose but the belief pinned every
        #              card, so there was nothing hidden to solve. The closed
        #              form already answers those and the deviator gains 0.
        #   wide    -- the support exceeded MAX_SUPPORT. Not solved, and NOT
        #              the same as gaining nothing.
        #   absent  -- no m = 1 decision arose at all before the game ended.
        rec = {"game": g, "kind": "none", "reason": "absent", "solver": fp}
        seen_pinned = seen_wide = False
        for _ in range(600):
            if st.is_terminal:
                break
            p = st.turn
            obs = Observation.from_state(st, p)
            live = [h for h, w in enumerate(obs.set_winner) if w is None]
            if len(live) == 1:
                agents[p].bel.update(obs)
                deals = consistent_deals(obs, agents[p].bel, live[0])
                if len(deals) == 1:
                    seen_pinned = True
                elif len(deals) > MAX_SUPPORT:
                    seen_wide = True
                if 1 < len(deals) <= MAX_SUPPORT:
                    states = []
                    for hands in deals:
                        t = GameState.from_components(
                            rules, list(hands), st.turn, list(st.set_winner))
                        t.history = list(st.history)
                        states.append(t)
                    w = [1.0 / len(states)] * len(states)
                    sv = ExactII(rules, live[0], p, SPEC)
                    sv.max_nodes = MAX_NODES
                    sv.deadline = time.monotonic() + DEFAULT_DEADLINE
                    try:
                        v = sv.solve([_clone(s) for s in states], list(w))
                    except SolveTimeout:
                        rec = {"game": g, "kind": "timeout", "solver": fp,
                               "support": len(deals)}
                        break
                    cv = sv.champion_value([_clone(s) for s in states],
                                           list(w))
                    rec = {"game": g, "kind": "solved", "solver": fp, "seat": p,
                           "support": len(deals), "value": v, "champion": cv,
                           "gain": v - cv, "nodes": sv.nodes}
                    break              # ONE position per game, deliberately
            st.apply(p, agents[p].act(obs))
        if rec["kind"] == "none":
            rec["reason"] = ("pinned" if seen_pinned else
                             "wide" if seen_wide else "absent")
        rows.append(rec)
        with JOURNAL.open("a") as fh:
            fh.write(json.dumps(rec) + "\n")
        print(f"  {g+1}/{n_games} games, "
              f"{sum(1 for r in rows if r['kind'] == 'solved')} with a "
              f"solvable first endgame", flush=True)

    solved = [r for r in rows if r["kind"] == "solved"]
    none_ = sum(1 for r in rows if r["kind"] == "none")
    to = sum(1 for r in rows if r["kind"] == "timeout")
    why = {"pinned": 0, "wide": 0, "absent": 0}
    for r in rows:
        if r["kind"] == "none":
            why[r.get("reason", "absent")] += 1
    print(f"\n{len(rows)} games: {len(solved)} with a solvable first hidden "
          f"m = 1 decision,\n  {none_} with none -- {why['pinned']} where the "
          f"belief pinned every card,\n  {why['wide']} where the support "
          f"exceeded {MAX_SUPPORT}, {why['absent']} where no m = 1 decision "
          f"arose --\n  and {to} over the {MAX_NODES:,}-node budget")
    if not solved:
        print("Nothing to report.")
        return 1

    gains = sorted(r["gain"] for r in solved)
    n = len(gains)
    mean = sum(gains) / n
    var = sum((x - mean) ** 2 for x in gains) / (n - 1) if n > 1 else 0.0
    se = (var / n) ** 0.5
    lo, hi = mean - 1.96 * se, mean + 1.96 * se
    print(f"\n  exact gain from deviating at the FIRST hidden m = 1 decision")
    print(f"    mean {mean:+.4f}  95% CI [{lo:+.4f}, {hi:+.4f}]")
    # A gain of zero is computed as a difference of two equal numbers reached
    # by different code paths, so it lands at -5.6e-17 as often as at 0.0 and
    # prints as "-0.0000" -- which reads exactly like a violation of the
    # invariant checked immediately below. Clamped for display only; the
    # invariant still tests the raw value against -1e-9.
    def z(x):
        return 0.0 if abs(x) < 1e-12 else x
    print(f"    median {z(gains[n//2]):+.4f}, min {z(gains[0]):+.4f}, "
          f"max {gains[-1]:+.4f}")
    neg = sum(1 for x in gains if x < -1e-9)
    if neg:
        print(f"\n  {neg} NEGATIVE gains, which cannot happen: the best "
              f"response may copy\n  the champion. Refusing to write a "
              f"result.")
        return 1
    print(f"    positions where deviating gains nothing: "
          f"{sum(1 for x in gains if abs(x) < 1e-9)}/{n}")

    # READ the sampled bound, do not retype it. A hardcoded comparison figure
    # is a number nobody is checking: exploitability.py can be rerun with more
    # pairs and this line would go on quoting the old interval while looking
    # like it had been recomputed. That is the drift
    # scripts4/check_paper_numbers.py exists to catch, and it does not watch
    # print statements.
    expl = ROOT / "results" / "exploitability.json"
    sampled = None
    if expl.exists():
        sm = json.loads(expl.read_text()).get("summary", {})
        if "mean" in sm and "ci95" in sm:
            sampled = (sm["mean"], sm["ci95"][0], sm["ci95"][1])
    # THE COMPARISON HAS TO BE PER GAME, NOT PER SOLVED POSITION.
    # exploitability.py averages over EVERY game it plays. Most games here have
    # no hidden m = 1 decision at all -- the belief pins every card, or the
    # position never arises -- and in those the restricted deviator never
    # deviates and gains exactly nothing. Quoting the conditional mean beside a
    # whole-game figure compares a mean over a favourable subset against a mean
    # over everything, and inflates the bound by the reciprocal of how often the
    # subset occurs. Games over the node budget are EXCLUDED from the
    # denominator rather than scored 0: they are unsolved, not worth nothing.
    known = n + none_
    uncond = sum(gains) / known if known else float("nan")
    uvar = (sum((x - uncond) ** 2 for x in gains)
            + none_ * uncond ** 2) / (known - 1) if known > 1 else 0.0
    use = (uvar / known) ** 0.5
    ulo, uhi = uncond - 1.96 * use, uncond + 1.96 * use
    print(f"\n  PER GAME, counting the {none_} games with no hidden m = 1 "
          f"decision as a gain of zero\n  ({to} over budget excluded -- "
          f"unsolved is not zero):")
    print(f"    mean {uncond:+.4f}  95% CI [{ulo:+.4f}, {uhi:+.4f}]")

    print(f"\n  beside scripts4/exploitability.py, same units (team "
          f"differential), per game:")
    if sampled is None:
        print(f"    results/exploitability.json not found; no comparison")
    else:
        print(f"    sampled rollout best response, whole game:  "
              f"{sampled[0]:+.4f}  [{sampled[1]:+.4f}, {sampled[2]:+.4f}]")
    print(f"    exact, one endgame decision only:           "
          f"{uncond:+.4f}  [{ulo:+.4f}, {uhi:+.4f}]")
    if sampled is not None and ulo > sampled[2]:
        print(f"\n  The exact bound from ONE endgame decision exceeds the")
        print(f"  sampled interval's upper end. The rollout responder was not")
        print(f"  finding what is there -- as fish4/bestresponse.py warned it")
        print(f"  might not, and against a deterministic realisation only.")

    smoke = n_games < MIN_RESULT_GAMES
    out = ROOT / "results" / ("ii_first_endgame_smoke.json" if smoke
                              else "ii_first_endgame.json")
    out.write_text(json.dumps({
        "n_games": len(rows), "n_solved": n, "n_none": none_,
        "none_pinned": why["pinned"], "none_wide": why["wide"],
        "none_absent": why["absent"],
        "n_timeout": to, "node_budget": MAX_NODES,
        "mean_gain": mean, "ci95": [lo, hi],
        "mean_gain_per_game": uncond, "ci95_per_game": [ulo, uhi],
        "median_gain": gains[n // 2], "max_gain": gains[-1],
        # stored so the comparison is a figure a manifest can address, not a
        # sentence in a log
        "sampled_exploitability": sampled,
        "beats_sampled_upper": bool(sampled is not None and lo > sampled[2]),
        "rows": solved}, indent=1))
    if smoke:
        print(f"\n{n_games} games is below {MIN_RESULT_GAMES}; wrote "
              f"{out.name}. Do not cite it.")
    else:
        print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 60))
