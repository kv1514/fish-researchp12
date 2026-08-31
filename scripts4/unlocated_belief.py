"""Does `unlocated_now` make the BELIEF better, or only the fit?

Registered in full at ``prereg/unlocated_belief.md`` before this file existed.
Read that first: the grid, the clamp and the decision rule are fixed there, and
nothing here is free to choose them.

The short version. ``prereg/choice_basis.md`` put the covariate at +3,143
held-out nats on a conditional logit over the half-suits a teammate chose, and
licensed a build behind an inert default on that evidence and no more. A logit
is scored on predicting the ASK. The engine does not want to predict asks; it
wants a posterior over WHERE THE CARDS ARE. The last attempt on this frontier,
``gamma_team``, had a better NLL and a worse top-1 and was refuted, which is
why the pre-registration demands both.

WHAT THIS INHERITS FROM ``scripts4/gamma_split.py``, deliberately:

  * games are generated ONCE at the incumbent and every cell is scored on the
    SAME positions, so no cell is graded on the positions its own play reached;
  * the truth is used only to SCORE, never to act;
  * cards are scored in two disjoint pools by where the card ACTUALLY is, and
    only cards the propagator has not pinned -- a pinned card is scored
    perfectly by every cell and dilutes the contrast;
  * the same RNG seed in every cell at every decision, so a difference between
    cells is the model and not the draw.

AND THE ONE THING IT DOES NOT INHERIT. ``gamma_split.paired`` clusters by
DECISION and pairs it with 1.96. Decisions inside one game share a deal, a seed
and a policy realisation, so that interval is computed over far more units than
there are independent ones -- #83 one level in, and its own output file cannot
be restated because it kept means and dropped the per-decision rows. This
clusters by GAME through ``fish4.clustered.cluster_ci``, which does the
grouping and the t at k-1 df together so neither can be fixed without the
other, AND writes every per-decision row with its game id, so a future reader
who disagrees with the unit can recompute rather than re-run.

Usage: python scripts4/unlocated_belief.py [n_games] [stride] [out.json]
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

from fish.beliefs import BeliefState                       # noqa: E402
from fish.cards import NUM_PLAYERS                         # noqa: E402
from fish.engine import GameState                          # noqa: E402
from fish.observation import Observation                   # noqa: E402
from fish.rules import RuleConfig                          # noqa: E402
from fish4.clustered import cluster_ci                     # noqa: E402
from fish4.posterior import Posterior                      # noqa: E402
from fish4.registry4 import V06_DEPLOYED, make_agent       # noqa: E402

EPS = 1e-12
RULES = RuleConfig(wrong_distribution_outcome="opponent")
N_DRAWS = 480

#: Fixed by prereg/unlocated_belief.md. 0.0 is the incumbent and the baseline
#: every cell is paired against; -4.0 is about the fitted exponent (-3.9568).
#: Positive values are not swept: the sign is not in doubt at 3,143 nats.
GRID = (0.0, -0.5, -1.0, -2.0, -4.0)
BASE = 0.0

#: prereg/unlocated_belief.md refuses an interval below this many
#: clusters. Reported as a withheld interval, never as a number.
MIN_CLUSTERS = 8


def true_holder_map(state: GameState) -> dict[int, int]:
    """Card -> the player who actually holds it. Verbatim from gamma_split.py.

    Copied rather than reinvented: my first attempt indexed `state.n_cards`,
    which does not exist. Hands are bitmasks and this walks the set bits.
    """
    truth = {}
    for p in range(NUM_PLAYERS):
        h = state.hands[p]
        while h:
            low = h & -h
            truth[low.bit_length() - 1] = p
            h ^= low
    return truth


class Pool:
    """Per-decision scores, each tagged with the GAME it came from.

    The game id is the part gamma_split.py did not keep. Without it the only
    unit available after the fact is the decision, which is not independent.
    """

    __slots__ = ("rows",)

    def __init__(self) -> None:
        #: (game, decision, mean_nll, mean_top1, n_cards)
        self.rows: list[tuple[int, int, float, float, int]] = []

    def add(self, M, truth, cards, game: int, decision: int) -> None:
        if not cards:
            return
        nll = 0.0
        hits = 0
        for c in cards:
            row = M[c]
            t = truth[c]
            nll += -math.log(max(row[t], EPS))
            hits += int(max(range(NUM_PLAYERS), key=lambda q: row[q]) == t)
        self.rows.append((game, decision, nll / len(cards),
                          hits / len(cards), len(cards)))

    def mean(self, i: int) -> float | None:
        return (sum(r[i] for r in self.rows) / len(self.rows)
                if self.rows else None)


def paired_by_game(cell: Pool, base: Pool) -> dict | None:
    """(cell - base) per decision, then clustered on the GAME.

    Positive NLL means the cell is WORSE (a loss); positive top-1 means BETTER
    (a hit rate). The caller labels the direction; this only reports it.
    """
    b = {(g, d): (nll, t1) for g, d, nll, t1, _ in base.rows}
    games, dn, dt = [], [], []
    for g, d, nll, t1, _ in cell.rows:
        if (g, d) in b:
            games.append(g)
            dn.append(nll - b[(g, d)][0])
            dt.append(t1 - b[(g, d)][1])
    if len(dn) < 2:
        return None
    out = {}
    for name, xs in (("nll", dn), ("top1", dt)):
        mu, half, k = cluster_ci(xs, games)
        # prereg/unlocated_belief.md: "If fewer than 8 games survive to give
        # clusters, the interval is not reported: k < 8 is too few for t on
        # k-1 df to mean much." A smoke run at two games printed four intervals
        # before this was here -- a rule stated in the registration and not
        # implemented in the instrument is the shape of defect this whole
        # branch has been fixing, and it does not get an exception for being
        # mine. The MEAN is still reported; it is the interval that is refused.
        withheld = k < MIN_CLUSTERS
        out[name] = {"mean": mu,
                     "lo": None if (half is None or withheld) else mu - half,
                     "hi": None if (half is None or withheld) else mu + half,
                     "n_clusters": k,
                     "interval_withheld": withheld or half is None}
    out["n_decisions"] = len(dn)
    return out


def main(n_games: int = 40, stride: int = 4, out: str | None = None) -> int:
    team = {w: Pool() for w in GRID}
    opp = {w: Pool() for w in GRID}
    decisions = 0
    t0 = time.perf_counter()

    for g in range(n_games):
        # Play is ALWAYS the incumbent, exactly as in gamma_split.py.
        agents = [make_agent(("kraken", dict(V06_DEPLOYED[1])))
                  for _ in range(NUM_PLAYERS)]
        st = GameState.deal(RULES, seed=720_000 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, RULES, 730_000 + g * 13 + p)
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
                t_cards = [c for c in unpinned
                           if truth[c] % 2 == mover % 2 and truth[c] != mover]
                o_cards = [c for c in unpinned if truth[c] % 2 != mover % 2]
                if t_cards or o_cards:
                    decisions += 1
                    for w in GRID:
                        rng = random.Random(7_100_000 + 977 * decisions)
                        M = Posterior(bel, rng, n_draws=N_DRAWS, obs=obs,
                                      gamma=0.35, w_unlocated=w).marginals()
                        team[w].add(M, truth, t_cards, g, decisions)
                        opp[w].add(M, truth, o_cards, g, decisions)
            st.apply(mover, agents[mover].act(
                Observation.from_state(st, mover)))
            step += 1
        print(f"  game {g + 1}/{n_games}: {decisions} decisions, "
              f"{time.perf_counter() - t0:.0f}s", file=sys.stderr, flush=True)

    rows = []
    for w in GRID:
        rows.append({
            "w_unlocated": w,
            "team_nll": team[w].mean(2), "team_top1": team[w].mean(3),
            "opp_nll": opp[w].mean(2), "opp_top1": opp[w].mean(3),
            "team_decisions": len(team[w].rows),
            "opp_decisions": len(opp[w].rows),
            "paired_team": None if w == BASE else paired_by_game(team[w], team[BASE]),
            "paired_opp": None if w == BASE else paired_by_game(opp[w], opp[BASE]),
        })

    doc = {
        "prereg": "prereg/unlocated_belief.md",
        "grid": list(GRID), "base": BASE,
        "n_games": n_games, "stride": stride, "n_draws": N_DRAWS,
        "decisions": decisions,
        "spec": ["kraken", dict(V06_DEPLOYED[1])],
        "cluster_unit": "game",
        "rows": rows,
        # The rows gamma_split.py dropped. Kept so the unit can be argued with
        # after the fact instead of re-run.
        "per_decision": {
            "team": {str(w): team[w].rows for w in GRID},
            "opp": {str(w): opp[w].rows for w in GRID},
        },
        "seconds": time.perf_counter() - t0,
    }

    print(f"\n{'w':>6}  {'team NLL':>9} {'team top1':>10}  "
          f"{'opp NLL':>9} {'opp top1':>9}")
    for r in rows:
        print(f"{r['w_unlocated']:>6}  {r['team_nll']:>9.5f} "
              f"{r['team_top1']:>10.5f}  {r['opp_nll']:>9.5f} "
              f"{r['opp_top1']:>9.5f}")
    print(f"\nSCORED AT n_draws = {N_DRAWS}"
          f"   (gamma_split.py and the convention instruments score at 720; "
          f"effects measured at different n_draws are not directly "
          f"comparable -- results/channel_precision.json)")
    print("\npaired against w=0.0, clustered by GAME (t at k-1 df):")
    for r in rows:
        pt = r["paired_team"]
        if not pt:
            continue
        n, t1 = pt["nll"], pt["top1"]

        def show(d):
            if d["interval_withheld"]:
                return f"{d['mean']:+.5f} [interval withheld, k={d['n_clusters']}]"
            return f"{d['mean']:+.5f} [{d['lo']:+.5f}, {d['hi']:+.5f}]"

        print(f"  w={r['w_unlocated']:<5} team NLL {show(n)}   "
              f"top1 {show(t1)}")
    if any((r["paired_team"] or {}).get("nll", {}).get("interval_withheld")
           for r in rows if r["paired_team"]):
        print(f"\n  Intervals withheld: fewer than {MIN_CLUSTERS} game "
              f"clusters. Means are shown; nothing here is a measurement.")
    print("\nNLL: negative is BETTER (a loss). top-1: positive is BETTER.")
    print("prereg/unlocated_belief.md requires BOTH, each excluding zero.")

    dest = Path(out) if out else ROOT / "results" / "unlocated_belief.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(doc, indent=1))
    print(f"\nWrote {dest} ({doc['seconds']:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(
        int(sys.argv[1]) if len(sys.argv) > 1 else 40,
        int(sys.argv[2]) if len(sys.argv) > 2 else 4,
        sys.argv[3] if len(sys.argv) > 3 else None))
