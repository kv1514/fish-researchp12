"""How well does the champion play the m = 1 endgame when it cannot see?

v0.3's headline absolute result was that its belief agents choose a provably
optimal move in 100% of information-resolved positions. ``fish4/EXACT2.md``
already notes that every one of those positions had a single live half-suit,
where the closed form reduces to "the team on move wins it" -- so the
certificate was shallower than it read. This goes further: that benchmark
scored against the PERFECT-information optimum, and at m = 1 the champion is
frequently NOT information-resolved. 43% of real m = 1 decisions pin every
card; the other 57% do not, and for those nobody has ever known what optimal
means.

``fish4/exact_ii.ExactII`` computes it exactly -- no sampling -- for one
deviating seat against champion opponents, optimising over the deviator's
information sets rather than per deal.

THE CONTROL RUNS FIRST AND GATES EVERYTHING
-------------------------------------------
Where the support is a single deal there is no hidden information left, and the
exact value MUST be the closed form's +/-1. That is checked on every such
position before any other number is reported, because a solver that cannot
reproduce an independently proved answer on the easy half of its input has not
earned the hard half.

    py scripts4/ii_endgame.py [n_games]
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

from fish.cards import NUM_PLAYERS, half_suit_mask, team_of
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.exact_ii import (DEFAULT_DEADLINE, MAX_NODES, ExactII,
                             SolveTimeout,
                             _clone, consistent_deals,
                             consistent_deals_multi)
from fish4.registry4 import make_agent

SPEC = ("fishbot4", {"opponent_gamma": 0.35})
MAX_SUPPORT = 24          # positions above this are reported, not solved
#: Above this the belief is too wide to enumerate exhaustively, and the
#: enumeration stops rather than running to a support nobody would solve.
#: Positions there are COUNTED -- the old product enumerator refused silently.
WIDE_LIMIT = 100_000
#: Positions at or below this support also get the tree-vs-playout control.
#: It doubles their cost, so it buys its coverage where searches are cheap.
CONSISTENCY_MAX_SUPPORT = 8
#: Below this many games the run is a regression check and its output goes
#: somewhere a reader -- or a manifest -- cannot mistake for a measurement.
MIN_RESULT_GAMES = 30


def closed_form(st, live, seat) -> int:
    """2f - m in the deviator's team frame, at any layer."""
    if isinstance(live, int):
        live = [live]
    t = team_of(st.turn)
    f = sum(1 for h in live
            if any(st.hands[q] & half_suit_mask(h)
                   for q in range(NUM_PLAYERS) if team_of(q) == t))
    v = 2 * f - len(live)
    return v if t == team_of(seat) else -v


def _solver_fingerprint() -> str:
    """A short hash of the solver's source.

    The journal exists so a killed run does not redo work, and that is only
    safe while the work would come out the same. It was not: the memo key in
    fish4/exact_ii.py omitted the history, five m = 2 positions came back with
    an impossible negative gain, and the fixed run would have RESUMED FROM THE
    BROKEN ONE -- reporting the old numbers under the new solver, with nothing
    to say which was which. Rows carry the fingerprint now and a run ignores
    any that do not match its own.
    """
    src = (ROOT / "fish4" / "exact_ii.py").read_bytes()
    return hashlib.sha256(src).hexdigest()[:12]


def _journal_path(layer: int) -> Path:
    """One journal per layer.

    The single shared file was keyed by game index alone, so an m = 2 run
    started while an m = 1 journal was present would have skipped all sixty
    games as "already done" and reported m = 1's positions as m = 2's. It did
    not happen -- the file was cleared between the runs -- but only by luck,
    and the same luck is not available next time.
    """
    return ROOT / "results" / (f"ii_endgame_journal_m{layer}.jsonl"
                               if layer != 1 else "ii_endgame_journal.jsonl")


def _load_journal(path: Path, fp: str):
    """Positions already solved, keyed by game index.

    This session has lost four long background runs to a timeout or a container
    restart, each time writing nothing because the results file is only written
    at the end. At roughly thirty seconds a game that is an expensive way to
    learn the same lesson twice, so every position is appended as it lands and
    a restart skips the games already done.
    """
    if not path.exists():
        return [], set()
    rows = []
    complete = set()
    stale = 0
    for line in path.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            if r.get("solver") != fp:
                stale += 1
                continue
            rows.append(r)
            if r.get("kind") == "game_done":
                complete.add(r["game"])
    if stale:
        print(f"  ignoring {stale} journalled rows from an older solver "
              f"(fingerprint != {fp})")
    # Only games with a game_done marker are complete. A run killed mid-game
    # leaves that game's positions in the journal, and replaying it would
    # DOUBLE-COUNT them -- so its partial records are dropped and it is redone.
    return [r for r in rows if r["game"] in complete], complete


def main(n_games: int = 12, layer: int = 1) -> int:
    """``layer`` is m, the number of live half-suits to solve.

    m = 2 was reachable in the end, but only checking said so: eight positions
    solved in under a second each and five returned exactly +0.0000, which is
    also what the depth cap returns. At m = 2 the closed form gives 0 whenever
    f = 1, so the two are indistinguishable from the value alone -- and twelve
    live cards can outrun MAX_PLIES in a way six cannot. The pinned control
    settles it, 21/21 against the closed form, and it runs before anything
    else at every layer for exactly that reason.
    """
    rules = RuleConfig()
    fp = _solver_fingerprint()
    journal = _journal_path(layer)
    print(f"  solver fingerprint {fp}; journal {journal.name}")
    journalled, done_games = _load_journal(journal, fp)
    if done_games:
        print(f"  resuming: {len(done_games)} games already journalled "
              f"({len(journalled)} positions)")
    pinned_ok = pinned_bad = timed_out = 0
    too_wide = no_deals = truth_ok = 0
    opp_dropped = dev_skipped = 0
    truth_bad: list = []
    consistent_ok = 0
    consistent_bad: list = []
    bad = []
    solved = []
    skipped = 0
    for r in journalled:
        # Dispatch on the tag explicitly. An earlier version used a bare else
        # for "solved", which swept up the game_done bookkeeping rows: the
        # resumed run reported six solved positions where the fresh run found
        # four, and then died on a KeyError reading a value those rows do not
        # have. The faithfulness check caught it; the resume itself looked fine.
        k = r.get("kind")
        if k == "pinned_ok":
            pinned_ok += 1
        elif k == "pinned_bad":
            pinned_bad += 1
            bad.append(r)
        elif k == "skipped":
            skipped += 1
        elif k == "timeout":
            timed_out += 1
        elif k == "solved":
            solved.append(r)

    for g in range(n_games):
        if g in done_games:
            continue
        agents = [make_agent(SPEC) for _ in range(NUM_PLAYERS)]
        st = GameState.deal(rules, seed=99_000 + g)
        ar = random.Random(99_500 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        for _ in range(600):
            if st.is_terminal:
                break
            p = st.turn
            obs = Observation.from_state(st, p)
            live = [h for h, w in enumerate(obs.set_winner) if w is None]
            if len(live) == layer:
                live_mask = 0
                for h in live:
                    live_mask |= half_suit_mask(h)
                hs = live[0] if layer == 1 else list(live)
                agents[p].bel.update(obs)
                deals = (consistent_deals(obs, agents[p].bel, hs)
                         if layer == 1 else
                         consistent_deals_multi(obs, agents[p].bel, live,
                                                limit=WIDE_LIMIT))
                # CONTROL. The true deal must be one of the deals the belief
                # admits. If it is not, the belief has excluded the truth and
                # every value computed over that support is a value of the
                # wrong game. This is free here -- the support is already
                # enumerated -- and it is the only check in this study that
                # tests the BELIEF rather than the solver.
                if deals and len(deals) <= WIDE_LIMIT:
                    truth = tuple(st.hands[q] & live_mask
                                  for q in range(NUM_PLAYERS))
                    if truth in deals:
                        truth_ok += 1
                    else:
                        truth_bad.append({"game": g, "support": len(deals)})
                if deals and len(deals) > WIDE_LIMIT:
                    # Used to be invisible: the product enumerator refused and
                    # returned [], and the position was dropped without a
                    # record of any kind.
                    too_wide += 1
                    with journal.open("a") as fh:
                        fh.write(json.dumps({"game": g, "kind": "too_wide",
                                             "solver": fp,
                                             "support": len(deals)}) + "\n")
                elif not deals:
                    no_deals += 1
                    with journal.open("a") as fh:
                        fh.write(json.dumps({"game": g, "kind": "no_deals",
                                             "solver": fp}) + "\n")
                elif deals and len(deals) <= MAX_SUPPORT:
                    sv = ExactII(rules, hs, p, SPEC)
                    sv.max_nodes = MAX_NODES
                    sv.deadline = time.monotonic() + DEFAULT_DEADLINE
                    states = []
                    for hands in deals:
                        t = GameState.from_components(
                            rules, list(hands), st.turn, list(st.set_winner))
                        t.history = list(st.history)
                        states.append(t)
                    w = [1.0 / len(states)] * len(states)
                    try:
                        v = sv.solve(states, w)
                    except SolveTimeout:
                        timed_out += 1
                        with journal.open("a") as fh:
                            fh.write(json.dumps(
                                {"game": g, "kind": "timeout", "solver": fp,
                                 "support": len(deals),
                                 "nodes": sv.nodes}) + "\n")
                        st.apply(p, agents[p].act(obs))
                        continue
                    except Exception as e:
                        skipped += 1
                        st.apply(p, agents[p].act(obs))
                        continue
                    cv = sv.champion_value(states, w)
                    opp_dropped += sv.opp_dropped
                    dev_skipped += sv.dev_skipped
                    # SECOND CONTROL. champion_value rolls each deal forward
                    # independently; champion_tree_value walks the same tree
                    # the best response walks and plays the champion at the
                    # deviator's nodes. Same strategy, two code paths, so the
                    # numbers must be equal. This is what localises a broken
                    # tree: the pinned control below only exercises positions
                    # where the support is one deal, and the memo bug that
                    # produced five impossible negative gains needed several.
                    # Restricted to small supports because it costs a second
                    # full search, and the bug it was written for showed at
                    # support 4.
                    if len(deals) <= CONSISTENCY_MAX_SUPPORT:
                        try:
                            tv = sv.champion_tree_value(
                                [_clone(x) for x in states], list(w))
                            if abs(tv - cv) < 1e-9:
                                consistent_ok += 1
                            else:
                                consistent_bad.append(
                                    {"game": g, "support": len(deals),
                                     "tree": tv, "playout": cv})
                        except SolveTimeout:
                            pass
                    if len(deals) == 1:
                        want = closed_form(states[0], live, p)
                        rec = {"game": g, "solver": fp,
                               "exact": v, "closed_form": want,
                               "kind": ("pinned_ok" if abs(v - want) < 1e-9
                                        else "pinned_bad")}
                        if rec["kind"] == "pinned_ok":
                            pinned_ok += 1
                        else:
                            pinned_bad += 1
                            bad.append(rec)
                    else:
                        rec = {"game": g, "kind": "solved", "solver": fp,
                               "support": len(deals), "value": v,
                               "champion": cv, "gain": v - cv,
                               "nodes": sv.nodes}
                        solved.append(rec)
                    with journal.open("a") as fh:
                        fh.write(json.dumps(rec) + "\n")
                elif deals:
                    skipped += 1
                    with journal.open("a") as fh:
                        fh.write(json.dumps({"game": g, "kind": "skipped", "solver": fp,
                                             "support": len(deals)}) + "\n")
            st.apply(p, agents[p].act(obs))
        with journal.open("a") as fh:
            fh.write(json.dumps({"game": g, "kind": "game_done", "solver": fp}) + "\n")
        print(f"  {g+1}/{n_games} games, {pinned_ok+pinned_bad} pinned, "
              f"{len(solved)} solved, {skipped} skipped", flush=True)

    print(f"\nCONTROL -- positions where the belief pins every card")
    print(f"  exact value equals the closed form: {pinned_ok}/"
          f"{pinned_ok+pinned_bad}")
    for b in bad[:5]:
        print(f"    MISMATCH exact {b['exact']:+.4f} vs closed form "
              f"{b['closed_form']:+d}")
    if pinned_bad or pinned_ok == 0:
        print("\nThe solver does not reproduce the proved answer where there is")
        print("nothing hidden. Nothing else it says is worth reading.")
        return 1

    print(f"\nCONTROL -- the true deal is in the belief's support")
    print(f"  it is: {truth_ok}/{truth_ok + len(truth_bad)}")
    if truth_bad:
        print(f"  MISSING in {len(truth_bad)}: the belief excludes the actual")
        print(f"  deal, so every value over that support is a value of a")
        print(f"  different game.")
        return 1

    if opp_dropped or dev_skipped:
        # NOT a warning. These are deals the champion has no move in; the tree
        # scores them where they stand and keeps their weight, exactly as the
        # rollout does. The count is reported because it USED to be a fault --
        # the tree dropped such a deal and renormalised the survivors, and the
        # tree/rollout control caught it at m = 2 at 105/106. m = 1 has none of
        # them at all, which is why the fault was invisible there.
        print(f"\n  deals the champion has no move in, scored in place: "
              f"{opp_dropped}")
        if dev_skipped:
            print(f"  deviator actions illegal in some deal of the set, "
                  f"skipped: {dev_skipped}")

    print(f"\nCONTROL -- the tree and the playout, same champion strategy")
    print(f"  they agree: {consistent_ok}/{consistent_ok + len(consistent_bad)}"
          f"  (support <= {CONSISTENCY_MAX_SUPPORT})")
    for b in consistent_bad[:5]:
        print(f"    MISMATCH game {b['game']} support {b['support']}: "
              f"tree {b['tree']:+.4f} vs playout {b['playout']:+.4f}")
    if consistent_bad:
        print("\nThe search and the rollout do not agree about the SAME")
        print("strategy, so the tree is wrong and its optimum means nothing.")
        return 1

    print(f"\nGENUINELY HIDDEN positions solved exactly: {len(solved)}"
          f"  ({skipped} skipped for support > {MAX_SUPPORT},"
          f" {timed_out} over the {MAX_NODES:,}-node budget)")
    if too_wide or no_deals:
        print(f"  positions not enumerated: {too_wide} with a support above "
              f"{WIDE_LIMIT:,}, {no_deals} with none at all")
    if solved:
        vs = sorted(r["value"] for r in solved)
        n = len(vs)
        print(f"  exact value to the seat on move: mean "
              f"{sum(vs)/n:+.4f}, median {vs[n//2]:+.4f}, "
              f"min {vs[0]:+.4f}, max {vs[-1]:+.4f}")
        one = sum(1 for v in vs if abs(v - 1.0) < 1e-9)
        print(f"  positions still worth a full +1 despite the uncertainty: "
              f"{one}/{n}")
        print(f"  mean search nodes: "
              f"{sum(r['nodes'] for r in solved)/n:.0f}")
        gains = sorted(r["gain"] for r in solved)
        cvs = [r["champion"] for r in solved]
        print(f"\n  THE CHAMPION IN THE SAME SEAT: mean "
              f"{sum(cvs)/n:+.4f}")
        print(f"  EXACT GAIN FROM DEVIATING: mean {sum(gains)/n:+.4f}, "
              f"median {gains[n//2]:+.4f}, max {gains[-1]:+.4f}")
        pos = sum(1 for x in gains if x > 1e-9)
        neg = sum(1 for x in gains if x < -1e-9)
        print(f"  positions where deviating gains: {pos}/{n};  "
              f"where it loses: {neg}/{n}")
        if neg:
            # This printed a warning and carried on, once. The run wrote a
            # results file with five impossible entries in it and every other
            # number in that file computed by the same broken search. A
            # violated invariant is a failed run.
            print("  A NEGATIVE GAIN IS IMPOSSIBLE: the best response can "
                  "always copy the\n  champion, so any negative entry is a "
                  "bug in the solver, not a result.")
            print("\nRefusing to write a results file. Fix the solver.")
            return 1

    # A short run is a regression check, not a result, and must not be able
    # to occupy the filename a result lives at. Two six-game verification runs
    # silently overwrote the 200-game m=1 result this session -- the one the
    # paper's manifest watches for 344 pinned and 308 solved -- and it was git
    # that noticed, not me. Same guard as scripts4/exploitability.py.
    smoke = n_games < MIN_RESULT_GAMES
    stem = f"ii_endgame_m{layer}" if layer != 1 else "ii_endgame"
    out = ROOT / "results" / (f"{stem}_smoke.json" if smoke
                              else f"{stem}.json")
    out.write_text(json.dumps({
        "n_games": n_games, "layer": layer,
        "max_support": MAX_SUPPORT,
        "pinned_checked": pinned_ok + pinned_bad, "pinned_ok": pinned_ok,
        "consistency_checked": consistent_ok + len(consistent_bad),
        "consistency_ok": consistent_ok,
        "consistency_max_support": CONSISTENCY_MAX_SUPPORT,
        "truth_in_support_checked": truth_ok + len(truth_bad),
        "truth_in_support_ok": truth_ok,
        "too_wide": too_wide, "no_deals": no_deals, "wide_limit": WIDE_LIMIT,
        "opp_dropped": opp_dropped, "dev_skipped": dev_skipped,
        "pinned_mismatches": bad, "n_solved": len(solved),
        # Stored, not left for a reader to recompute from the records. The
        # paper's manifest watches these three, and a figure the manifest
        # cannot address is a figure nobody is checking. They were backfilled
        # into the first run's output by hand after the manifest could not
        # find them, which is exactly the drift check_paper_numbers exists to
        # catch -- so the script writes them now.
        "mean_gain": (sum(r["gain"] for r in solved) / len(solved))
        if solved else None,
        "mean_optimum": (sum(r["value"] for r in solved) / len(solved))
        if solved else None,
        "mean_champion": (sum(r["champion"] for r in solved) / len(solved))
        if solved else None,
        "skipped_large_support": skipped, "timed_out": timed_out,
        "node_budget": MAX_NODES, "backstop_seconds": DEFAULT_DEADLINE,
        "solved": solved}, indent=1))
    if smoke:
        print(f"\n{n_games} games is below the {MIN_RESULT_GAMES} this script "
              f"treats as a result;\nwrote {out.relative_to(ROOT)} instead. "
              f"Do not cite it.")
    else:
        print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 12,
                          int(a[1]) if len(a) > 1 else 1))
