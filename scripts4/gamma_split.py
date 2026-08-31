"""Is one gamma right for both sides of the table?

The opponent choice model weights every other seat's asks by the same exponent
`gamma = 0.35`. That single number does two different jobs:

  * on the OPPONENTS' side it sharpens the read that picks our next ask;
  * on OUR OWN side it sharpens the read that places an allocation --- which of
    our seats holds which card of a half-suit our team already owns outright.

Two results from v1.0 say those jobs should not be priced the same. 95.3% of
this engine's residual errors are allocation errors (0.1676 a game against
0.0083 ownership errors), and handing a seat the true deal one side at a time
values teammates' cards at +3.41 sets against opponents' +1.31 --- 2.6x
(prereg/information_ceiling_split.md). A single gamma forces one compromise
between two jobs with very different returns.

This is the CHEAP instrument, run before any play experiment. It asks only
whether the posterior gets *more accurate* when the two sides are priced
separately, which is a question about the belief and needs no games to be
replayed. If the optimum sits on the diagonal gamma_team == gamma_opp, the idea
is dead and it cost an hour instead of a duel.

DESIGN. Games are generated ONCE at the incumbent and every (gamma_opp,
gamma_team) cell is scored on the SAME positions. That is what makes the grid a
paired comparison: a cell that changed play would be scored on its own
positions and the differences would be confounded with which positions each
arm reached. The truth is used only to SCORE, never to act.

Cards are scored in two disjoint pools, by where the card ACTUALLY is:

  team   the true holder is a teammate of the observing seat (not the observer;
         our own cards are never uncertain to us)
  opp    the true holder is an opponent

Both pools are restricted to cards the propagator has NOT pinned, since a
pinned card is scored perfectly by every cell and would only dilute the
contrast.

Reported per cell: mean NLL on each pool, and the pooled mean. NLL is the
proper score. Brier is carried too because NLL is unbounded and one confident
mistake can move it a long way.

Usage: python scripts4/gamma_split.py [n_games] [stride] [out.json]
"""

from __future__ import annotations

import json
import math
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.beliefs import BeliefState                      # noqa: E402
from fish.cards import NUM_PLAYERS                        # noqa: E402
from fish.engine import GameState                         # noqa: E402
from fish.observation import Observation                  # noqa: E402
from fish.rules import RuleConfig                         # noqa: E402
from fish4.posterior import Posterior                     # noqa: E402
from fish4.registry4 import V06_DEPLOYED, make_agent      # noqa: E402

EPS = 1e-12

#: The incumbent's single value, and the grid around it. gamma_opp is swept too
#: rather than pinned: a cell that improves only because BOTH sides moved is a
#: different finding from one that improves because they moved APART, and
#: pinning gamma_opp would make the two indistinguishable.
GAMMA_OPP = [0.0, 0.35, 0.7, 1.0]
GAMMA_TEAM = [0.0, 0.35, 0.7, 1.0, 1.5, 2.0, 3.0]

#: Draws for the scored posterior. Higher than the shipped 480 on purpose: this
#: is a measurement of the TARGET distribution, and sampling noise common to
#: every cell still inflates every cell's NLL. It is not a play setting.
N_DRAWS = 720

RULES = RuleConfig(wrong_distribution_outcome="opponent")

#: A smoke run must not overwrite a real one. On 2026-08-28 an eight-game
#: check replaced an 1,800-game result with eight games of noise, and
#: nothing downstream could tell. This script takes no journal, so the
#: journal-derived naming rule in scripts4/journal.py does not apply --
#: the size guard is what applies instead.
MIN_GAMES_TO_WRITE = 20


def true_holder_map(state: GameState) -> dict[int, int]:
    truth = {}
    for p in range(NUM_PLAYERS):
        h = state.hands[p]
        while h:
            low = h & -h
            truth[low.bit_length() - 1] = p
            h ^= low
    return truth


class Pool:
    """Running NLL/Brier/top-1 over one pool of cards.

    ``per_decision`` keeps each decision's mean NLL and top-1 separately. Cells
    are scored on the SAME decisions, so the comparison between two cells is
    paired and its standard error is the SD of the per-decision DIFFERENCE, not
    the SD of either level. Cards inside one decision share a belief and are
    strongly correlated, so the decision is the independent unit; treating
    16,342 cards as 16,342 observations would understate the interval several
    times over and turn noise into a finding.
    """

    __slots__ = ("nll", "brier", "top1", "n", "per_decision")

    def __init__(self) -> None:
        self.nll = 0.0
        self.brier = 0.0
        self.top1 = 0
        self.n = 0
        #: (decision_index, mean_nll, mean_top1) for every decision scored
        self.per_decision: list[tuple[int, float, float]] = []

    def add(self, M, truth, cards, decision: int | None = None) -> None:
        d_nll = 0.0
        d_top1 = 0
        for c in cards:
            row = M[c]
            t = truth[c]
            p = row[t]
            nll = -math.log(max(p, EPS))
            self.nll += nll
            d_nll += nll
            self.brier += sum((row[q] - (1.0 if q == t else 0.0)) ** 2
                              for q in range(NUM_PLAYERS))
            best = max(range(NUM_PLAYERS), key=lambda q: row[q])
            hit = int(best == t)
            self.top1 += hit
            d_top1 += hit
            self.n += 1
        if decision is not None and cards:
            self.per_decision.append(
                (decision, d_nll / len(cards), d_top1 / len(cards)))

    def to_dict(self):
        if not self.n:
            return None
        return {"nll": self.nll / self.n, "brier": self.brier / self.n,
                "top1": self.top1 / self.n, "n": self.n}



def paired(cell_pool, base_pool):
    """Paired mean difference (cell - base) over decisions both scored.

    Returns (mean, lo, hi, n_decisions). Positive means the cell is WORSE on a
    loss (NLL) and BETTER on a hit rate (top-1); callers label the direction.

    THE UNIT HERE IS THE DECISION, AND THAT IS NOT THE WHOLE STORY.

    Cards inside one decision are strongly correlated, which is why the
    decision and not the card is the unit -- see the Pool docstring above. But
    decisions inside one GAME are correlated too: they share a deal, a seed and
    a policy realisation. This run scored 1,557 decisions drawn from 60 games,
    so the 1.96 interval below is computed over roughly twenty-six times more
    units than there are independent ones, and is understated by a factor this
    function cannot know -- the design effect depends on the intra-game
    correlation, not on the counts alone.

    That is #83's finding one level in, and it was not re-clustered with the
    rest: results/cluster_audit.json covers declare_regret only. Nor can it be
    from the file, because to_dict() keeps means and intervals and drops
    per_decision -- exactly the case the paper names as the argument for
    storing per-pair data.

    What it does NOT touch is the conclusion. gamma_team was refuted because
    top-1 moved the WRONG WAY (0.39279 -> 0.38178 at gamma_team=0.7 while NLL
    improved), and a direction is a sign, not a significance. A wider interval
    makes that refutation harder to dispute, not easier. What is overstated is
    only the confidence attached to each number, and a re-run at game level is
    the way to restate them if anyone ever needs them restated.

    New work on this instrument should use ``fish4.clustered.cluster_ci``,
    which does the grouping and the t at k-1 df together so neither can be
    fixed without the other. ``scripts4/unlocated_belief.py`` does.
    """
    b = {d: (nll, t1) for d, nll, t1 in base_pool.per_decision}
    dn, dt = [], []
    for d, nll, t1 in cell_pool.per_decision:
        if d in b:
            dn.append(nll - b[d][0])
            dt.append(t1 - b[d][1])
    n = len(dn)
    if n < 2:
        return None
    out = []
    for xs in (dn, dt):
        m = sum(xs) / n
        var = sum((x - m) ** 2 for x in xs) / (n - 1)
        se = (var / n) ** 0.5
        out.append((m, m - 1.96 * se, m + 1.96 * se))
    return {"nll": out[0], "top1": out[1], "n_decisions": n}


def main(n_games: int = 40, stride: int = 4, out: str | None = None) -> int:
    cells = [(go, gt) for go in GAMMA_OPP for gt in GAMMA_TEAM]
    team = {c: Pool() for c in cells}
    opp = {c: Pool() for c in cells}
    decisions = 0
    t0 = time.perf_counter()

    for g in range(n_games):
        # Play is ALWAYS the incumbent. The grid scores beliefs at positions
        # the shipped engine actually reaches; no cell gets to steer the game
        # towards positions it happens to read well.
        agents = [make_agent(("kraken", dict(V06_DEPLOYED[1])))
                  for _ in range(NUM_PLAYERS)]
        st = GameState.deal(RULES, seed=520_000 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, RULES, 530_000 + g * 13 + p)
        bels = [BeliefState(RULES, observer=p) for p in range(NUM_PLAYERS)]
        step = 0
        while not st.is_terminal and step < 400:
            mover = st.turn
            for q in range(NUM_PLAYERS):
                bels[q].update(Observation.from_state(st, q))
            if step % stride == 0:
                obs = Observation.from_state(st, mover)
                bel = bels[mover]
                truth = true_holder_map(st)
                unpinned = [c for c in range(bel.n)
                            if bel.public_loc[c] is None
                            and bel.candidates[c].bit_count() > 1]
                # Split by where the card TRULY is. A card held by the observer
                # is never uncertain to the observer, so the two pools cover
                # every scored card between them.
                t_cards = [c for c in unpinned
                           if truth[c] % 2 == mover % 2 and truth[c] != mover]
                o_cards = [c for c in unpinned if truth[c] % 2 != mover % 2]
                if not t_cards and not o_cards:
                    step += 1
                    st.apply(mover, agents[mover].act(
                        Observation.from_state(st, mover)))
                    continue
                decisions += 1
                for (go, gt) in cells:
                    # Same RNG seed in every cell at every decision, so a
                    # difference between cells is the model and not the draw.
                    rng = random.Random(6_100_000 + 977 * decisions)
                    M = Posterior(bel, rng, n_draws=N_DRAWS, obs=obs,
                                  gamma=go, gamma_team=gt).marginals()
                    if t_cards:
                        team[(go, gt)].add(M, truth, t_cards, decision=decisions)
                    if o_cards:
                        opp[(go, gt)].add(M, truth, o_cards, decision=decisions)
            st.apply(mover, agents[mover].act(
                Observation.from_state(st, mover)))
            step += 1
        print(f"  game {g + 1}/{n_games}: {decisions} scored decisions, "
              f"{time.perf_counter() - t0:.0f}s",
              file=sys.stderr, flush=True)

    rows = []
    for (go, gt) in cells:
        td, od = team[(go, gt)].to_dict(), opp[(go, gt)].to_dict()
        if td is None or od is None:
            continue
        n = td["n"] + od["n"]
        rows.append({
            "gamma_opp": go, "gamma_team": gt,
            "team_nll": td["nll"], "team_brier": td["brier"],
            "team_top1": td["top1"], "team_n": td["n"],
            "opp_nll": od["nll"], "opp_brier": od["brier"],
            "opp_top1": od["top1"], "opp_n": od["n"],
            "pooled_nll": (td["nll"] * td["n"] + od["nll"] * od["n"]) / n,
            "n": n,
        })

    bt, bo = team[(0.35, 0.35)], opp[(0.35, 0.35)]
    for r in rows:
        c = (r["gamma_opp"], r["gamma_team"])
        r["paired_team"] = paired(team[c], bt)
        r["paired_opp"] = paired(opp[c], bo)

    base = next((r for r in rows
                 if r["gamma_opp"] == 0.35 and r["gamma_team"] == 0.35), None)
    print(f"\n=== posterior accuracy by side, {decisions} decisions, "
          f"{n_games} games ===")
    print("play is the incumbent throughout; truth scores only, never acts")
    # The scoring precision belongs BESIDE the table, not only in the payload.
    # It was a module constant in three instruments set to two different values
    # -- 720 here, 480 in unlocated_belief.py -- and nothing printed it, so two
    # runs could be read side by side without either saying they were not
    # scored at the same precision. results/channel_precision.json measures how
    # much that is worth: a paired belief effect grows with n_draws.
    print(f"SCORED AT n_draws = {N_DRAWS}"
          f"   (the engine plays at {V06_DEPLOYED[1]['n_draws']}; effects "
          f"measured at different n_draws are not directly comparable)\n")
    print(f"{'g_opp':>6} {'g_team':>7} | {'team NLL':>9} {'opp NLL':>9} "
          f"{'pooled':>9} | {'team top1':>10} {'opp top1':>9}")
    print("-" * 74)
    for r in sorted(rows, key=lambda r: (r["gamma_opp"], r["gamma_team"])):
        mark = "  <- incumbent" if r is base else ""
        print(f"{r['gamma_opp']:6.2f} {r['gamma_team']:7.2f} | "
              f"{r['team_nll']:9.4f} {r['opp_nll']:9.4f} "
              f"{r['pooled_nll']:9.4f} | "
              f"{r['team_top1']:10.4f} {r['opp_top1']:9.4f}{mark}")

    if base is not None:
        best_t = min(rows, key=lambda r: r["team_nll"])
        best_p = min(rows, key=lambda r: r["pooled_nll"])
        print(f"\nincumbent (0.35, 0.35): team NLL {base['team_nll']:.4f}, "
              f"pooled {base['pooled_nll']:.4f}")
        print(f"best team NLL:   g_opp={best_t['gamma_opp']:.2f} "
              f"g_team={best_t['gamma_team']:.2f}  "
              f"{best_t['team_nll']:.4f}  "
              f"({best_t['team_nll'] - base['team_nll']:+.4f} vs incumbent)")
        print(f"best pooled NLL: g_opp={best_p['gamma_opp']:.2f} "
              f"g_team={best_p['gamma_team']:.2f}  "
              f"{best_p['pooled_nll']:.4f}  "
              f"({best_p['pooled_nll'] - base['pooled_nll']:+.4f} vs incumbent)")
        print("\n=== paired against the incumbent, by decision "
              "(the independent unit) ===")
        print(f"{'g_opp':>6} {'g_team':>7} | {'dNLL (team)':>22} "
              f"| {'dtop1 (team)':>22}")
        print("-" * 64)
        for r in sorted(rows, key=lambda r: (r["gamma_opp"], r["gamma_team"])):
            pt = r["paired_team"]
            if not pt:
                continue
            m, lo, hi = pt["nll"]
            tm, tlo, thi = pt["top1"]
            print(f"{r['gamma_opp']:6.2f} {r['gamma_team']:7.2f} | "
                  f"{m:+8.4f} [{lo:+.4f},{hi:+.4f}] | "
                  f"{tm:+8.4f} [{tlo:+.4f},{thi:+.4f}]")

        # A cell only counts as an improvement if it moves BOTH scores the
        # right way with an interval clear of zero. NLL alone is not enough:
        # a model can win on NLL purely by spreading mass while getting the
        # holder right LESS often, which is a worse belief for a policy that
        # has to name a split.
        wins = []
        for r in rows:
            pt = r["paired_team"]
            if not pt or (r["gamma_opp"], r["gamma_team"]) == (0.35, 0.35):
                continue
            nll_better = pt["nll"][2] < 0.0          # CI entirely below zero
            top1_not_worse = pt["top1"][2] > 0.0     # CI not entirely below
            if nll_better and top1_not_worse:
                wins.append(r)
        print("\nVERDICT")
        if wins:
            # The question is not "does some cell beat the incumbent" -- a
            # uniform gamma raise can do that, and the posterior sweep in
            # tab:posterior already showed gamma 0.45-0.60 beating 0.35 on NLL
            # years before this. The question is whether pricing the two sides
            # APART beats pricing them together, so an off-diagonal cell has to
            # beat the best DIAGONAL cell, not merely the incumbent.
            diag = [r for r in wins if r["gamma_opp"] == r["gamma_team"]]
            off = [r for r in wins if r["gamma_opp"] != r["gamma_team"]]
            best = min(wins, key=lambda r: r["paired_team"]["nll"][0])
            print(f"  {len(wins)} cell(s) pass both pre-registered conditions "
                  f"({len(off)} off-diagonal, {len(diag)} diagonal).")
            if diag and off:
                bd = min(diag, key=lambda r: r["paired_team"]["nll"][0])
                bo = min(off, key=lambda r: r["paired_team"]["nll"][0])
                print(f"  best diagonal     "
                      f"({bd['gamma_opp']:.2f}, {bd['gamma_team']:.2f}): "
                      f"dNLL {bd['paired_team']['nll'][0]:+.4f}")
                print(f"  best off-diagonal "
                      f"({bo['gamma_opp']:.2f}, {bo['gamma_team']:.2f}): "
                      f"dNLL {bo['paired_team']['nll'][0]:+.4f}")
            if best["gamma_opp"] == best["gamma_team"]:
                print(f"  The best passing cell is DIAGONAL "
                      f"(gamma={best['gamma_opp']:.2f} on both sides), so what "
                      f"this run found is that the incumbent gamma is too LOW, "
                      f"not that the sides deserve different numbers.")
                print("  THE SPLIT IS REFUTED. No play experiment on it.")
            else:
                print(f"  Best passing cell is OFF-DIAGONAL: "
                      f"g_opp={best['gamma_opp']:.2f}, "
                      f"g_team={best['gamma_team']:.2f}. The split beats every "
                      f"uniform gamma in the grid; a play experiment is "
                      f"licensed. Pre-register it before running.")
        else:
            print("  NO cell improves teammate-side NLL on a paired interval "
                  "clear of zero while also not worsening top-1.")
            print("  Every NLL gain here is bought by getting the holder "
                  "right LESS often, which is calibration moving rather than "
                  "the read improving. The split is NOT licensed by this "
                  "instrument and no play experiment should be run on it.")

    payload = {"rows": rows, "decisions": decisions, "n_games": n_games,
               "stride": stride, "n_draws": N_DRAWS,
               "gamma_opp_grid": GAMMA_OPP, "gamma_team_grid": GAMMA_TEAM,
               "spec": V06_DEPLOYED[1], "rules": RULES.to_dict(),
               "seconds": time.perf_counter() - t0}
    if out:
        path = Path(out)
    elif n_games < MIN_GAMES_TO_WRITE:
        print(f"\nNOT WRITING: {n_games} games is below "
              f"MIN_GAMES_TO_WRITE={MIN_GAMES_TO_WRITE}. This looks like a "
              f"smoke run; pass an explicit output path to keep it.",
              file=sys.stderr)
        return 0
    else:
        path = ROOT / "results" / "gamma_split.json"
    path.write_text(json.dumps(payload, indent=2))
    print(f"\nwrote {path}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 40,
                          int(a[1]) if len(a) > 1 else 4,
                          a[2] if len(a) > 2 else None))
