"""How good is the posterior, measured against the truth it is guessing at?

Every belief metric in v0.3 was indirect: sampler cost, agreement with an exact
endgame solver, or downstream win rate. None of them asked the direct question,
which in simulation we can simply answer, because the hidden hands are sitting
right there in the engine:

    given the public record, how much probability does the agent put on where
    the cards ACTUALLY are?

This script scores several inference configurations on exactly that, over real
positions from real games. The true state is used only to SCORE, never to act -
the same line the v0.3 value network was trained on.

Scores, computed over cards that are still genuinely uncertain (a card the
propagator has already pinned is scored perfectly by everything and would only
dilute the comparison):

* **NLL** - mean of -log P(true holder). The proper score; lower is better.
* **Brier** - mean squared error of the six-way distribution. Bounded, so it is
  robust to a single confident mistake, which NLL is not.
* **top-1** - how often the most likely holder is the real one.
* **calibration** - reliability of the stated probabilities in deciles.

Configurations compared:
  v03-N        v0.3's heuristic sampler with N draws (the incumbent)
  exact-free   the exact DP, ignoring the OR clauses
  sis-N        v0.4's unbiased importance sampler with N draws
  sis-N-gG     the same, with the opponent choice model at gamma = G
"""

from __future__ import annotations

import json
import math
import random
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.beliefs import RESOLVED, BeliefState
from fish.cards import NUM_PLAYERS
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.posterior import Posterior
from fish4.registry4 import make_agent

EPS = 1e-9


def v03_marginals(bel, rng, n_samples):
    """Marginals as v0.3 computes them: empirical over its own sampler."""
    M = np.zeros((bel.n, NUM_PLAYERS))
    for _ in range(n_samples):
        hands = bel.sample_current_hands(rng)
        for p in range(NUM_PLAYERS):
            h = hands[p]
            while h:
                low = h & -h
                M[low.bit_length() - 1, p] += 1
                h ^= low
    return M / max(1, n_samples)


def _sis(n, gamma=0.0, depth_mode="initial", count_mode="linear"):
    return lambda bel, rng, obs: Posterior(
        bel, rng, n_draws=n, mode="sample", obs=obs, gamma=gamma,
        depth_mode=depth_mode, count_mode=count_mode).marginals()


CONFIGS = [
    ("v03-512", lambda bel, rng, obs: v03_marginals(bel, rng, 512)),
    ("sis-160", _sis(160)),
    ("sis-160-g0.35", _sis(160, 0.35)),
    ("sis-160-g0.35-attime", _sis(160, 0.35, depth_mode="attime")),
    ("sis-160-g0.70-attime", _sis(160, 0.70, depth_mode="attime")),
    ("sis-160-g1.20-attime", _sis(160, 1.20, depth_mode="attime")),
    ("sis-160-g0.70-attime-sqrt", _sis(160, 0.70, depth_mode="attime",
                                       count_mode="sqrt")),
    ("sis-320-g0.70-attime", _sis(320, 0.70, depth_mode="attime")),
    ("sis-320-g0.45", _sis(320, 0.45)),
]


class Score:
    __slots__ = ("nll", "brier", "top1", "n", "seconds", "calib")

    def __init__(self):
        self.nll = 0.0
        self.brier = 0.0
        self.top1 = 0
        self.n = 0
        self.seconds = 0.0
        self.calib = defaultdict(lambda: [0.0, 0.0, 0])   # bin -> [p_sum, hits, n]

    def add(self, M, truth, cards):
        for c in cards:
            t = truth[c]
            row = M[c]
            p = float(row[t])
            self.nll += -math.log(max(p, EPS))
            self.brier += float(((row - np.eye(NUM_PLAYERS)[t]) ** 2).sum())
            self.top1 += int(int(np.argmax(row)) == t)
            self.n += 1

    def add_calibration(self, M, truth, cards):
        """Reliability must bin the probability assigned to a FIXED outcome.

        Binning by the probability given to the true holder would make every
        entry a hit by construction and report perfect calibration for any
        model at all.
        """
        for c in cards:
            t = truth[c]
            for p in range(NUM_PLAYERS):
                pr = float(M[c, p])
                b = min(9, int(pr * 10))
                e = self.calib[b]
                e[0] += pr
                e[1] += 1.0 if p == t else 0.0
                e[2] += 1

    def to_dict(self):
        if not self.n:
            return {}
        calib = {str(b): {"mean_p": v[0] / v[2], "freq": v[1] / v[2], "n": v[2]}
                 for b, v in sorted(self.calib.items()) if v[2] > 0}
        return {"nll": self.nll / self.n, "brier": self.brier / self.n,
                "top1": self.top1 / self.n, "n_cards": self.n,
                "seconds": self.seconds,
                "ms_per_decision": None, "calibration": calib}


def true_holder_map(state: GameState):
    truth = {}
    for p in range(NUM_PLAYERS):
        h = state.hands[p]
        while h:
            low = h & -h
            truth[low.bit_length() - 1] = p
            h ^= low
    return truth


def main(n_games: int = 12, stride: int = 3, out: str = None):
    rules = RuleConfig()
    scores = {name: Score() for name, _ in CONFIGS}
    calib = {name: Score() for name, _ in CONFIGS}
    decisions = 0
    ref = ("tuned", {"w_turn": 0.6, "w_scarce": 0.2})
    for g in range(n_games):
        agents = [make_agent(ref) for _ in range(6)]
        ar = random.Random(31_000 + g)
        st = GameState.deal(rules, seed=41_000 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        bels = [BeliefState(rules, observer=p) for p in range(6)]
        step = 0
        while not st.is_terminal and step < 400:
            p = st.turn
            for q in range(NUM_PLAYERS):
                bels[q].update(Observation.from_state(st, q))
            if step % stride == 0:
                obs = Observation.from_state(st, p)
                bel = bels[p]
                truth = true_holder_map(st)
                # score only cards that are still genuinely uncertain for this
                # seat: a pinned card is free marks for every configuration
                cards = [c for c in range(bel.n)
                         if bel.public_loc[c] is None
                         and bel.candidates[c].bit_count() > 1]
                if cards:
                    decisions += 1
                    for name, fn in CONFIGS:
                        rng = random.Random(9_000_000 + 977 * decisions)
                        t0 = time.perf_counter()
                        M = fn(bel, rng, obs)
                        dt = time.perf_counter() - t0
                        scores[name].seconds += dt
                        scores[name].add(M, truth, cards)
                        calib[name].add_calibration(M, truth, cards)
            st.apply(p, agents[p].act(Observation.from_state(st, p)))
            step += 1
        print(f"  game {g+1}/{n_games}: {decisions} scored decisions",
              file=sys.stderr, flush=True)

    rows = []
    for name, _ in CONFIGS:
        d = scores[name].to_dict()
        if not d:
            continue
        d["name"] = name
        d["ms_per_decision"] = 1000.0 * scores[name].seconds / max(1, decisions)
        d["calibration"] = calib[name].to_dict().get("calibration", {})
        rows.append(d)
    rows.sort(key=lambda r: r["nll"])
    print(f"\n{decisions} decisions, {rows[0]['n_cards']} uncertain-card "
          f"predictions each\n")
    print(f"{'config':16s} {'NLL':>8s} {'Brier':>8s} {'top-1':>8s} "
          f"{'ms/dec':>9s}")
    for r in rows:
        print(f"{r['name']:16s} {r['nll']:8.4f} {r['brier']:8.4f} "
              f"{r['top1']:8.4f} {r['ms_per_decision']:9.2f}")
    path = Path(out) if out else ROOT / "results" / "posterior_accuracy3.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(
        {"n_games": n_games, "stride": stride, "decisions": decisions,
         "rows": rows}, indent=2))
    print(f"\nSaved {path}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 12,
         int(sys.argv[2]) if len(sys.argv) > 2 else 3)
