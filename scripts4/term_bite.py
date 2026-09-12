"""Size, overlap and bite for any ask-basis term, before any duel is run.

WHY THIS IS A STANDING INSTRUMENT AND NOT A ONE-OFF
---------------------------------------------------
`prereg/locate_term.md` spent 3,000 duplicate-deal pairs to learn that a term
adding at most 0.013 to a score whose P(success) part spans ~1.0, and changing
the top-ranked ask in 3.9% of positions, cannot move 1.57 sets a game. That
diagnosis was worth more than the duel, and it was run afterwards.

`scripts4/declare_bite.py` then did the same measurement BEFORE the duel for a
weight inside the lookahead, and the pre-registered 15% floor stopped a
3,000-pair run for the price of seven minutes. This is that instrument for the
twelve-plus-term ask basis, so the next term gets screened for free.

It is a screen for FUTILITY, not for value: passing means a duel can resolve
the term, and says nothing about the sign.

    py scripts4/term_bite.py <term> [n_games] [w ...]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.askfeat import TERM_NAMES, ask_feature_matrix

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 10_400_000


def main(term: str, n_games: int = 40, weights=(0.15, 0.3, 0.6, 1.2)) -> int:
    import fish4.agent4 as A
    from fish4.registry4 import V06_DEPLOYED, make_agent

    if term not in TERM_NAMES:
        raise SystemExit(f"{term!r} is not a basis term: {TERM_NAMES}")
    idx = TERM_NAMES.index(term)
    rows = {w: [] for w in weights}

    def recorder(bot, ctx, asks, scores):
        if len(asks) < 2:
            return
        base = np.asarray(scores, dtype=float)
        _, F = ask_feature_matrix(ctx, asks)
        f = F[:, idx]
        if not f.any():
            # A term that is identically zero here still counts as a position
            # where it does not bite; dropping such rows would inflate every
            # figure below by conditioning on the term having fired.
            rows_append(rows, weights, 0.0, float(base.max() - base.min()),
                        0.0, 0)
            return
        top0 = int(np.argmax(base))
        spread = float(base.max() - base.min())
        for w in weights:
            d = w * f
            r = 0.0
            if base.std() > 1e-12 and d.std() > 1e-12:
                r = float(np.corrcoef(base, d)[0, 1])
            rows[w].append((float(np.abs(d).max()), spread, r,
                            int(int(np.argmax(base + d)) != top0)))

    def rows_append(rows, weights, a, b, c, d):
        for w in weights:
            rows[w].append((a, b, c, d))

    rules = RuleConfig(**RULES_D)
    A._SCORE_RECORDER = recorder
    try:
        for g in range(n_games):
            seed = SEED0 + g
            agents = [make_agent(("fishbot4", dict(V06_DEPLOYED[1])))
                      for _ in range(NUM_PLAYERS)]
            st = GameState.deal(rules, seed=seed)
            for p, a in enumerate(agents):
                a.begin_game(p, rules, 104_000 + seed * 13 + p)
            for _ in range(600):
                if st.is_terminal:
                    break
                st.apply(st.turn,
                         agents[st.turn].act(Observation.from_state(st, st.turn)))
            if (g + 1) % 10 == 0:
                print(f"  {g+1}/{n_games} games", flush=True)
    finally:
        A._SCORE_RECORDER = None

    n = len(rows[weights[0]])
    print("\n" + "=" * 74)
    print(f"  BITE OF `{term}`, {n:,} real champion ask decisions")
    print("=" * 74)
    print(f"\n  {'w':>8}{'median |delta|':>16}{'p90':>9}{'/ spread':>11}"
          f"{'corr':>8}{'fires':>8}{'bite':>8}")
    out = {"rules": RULES_D, "term": term, "n_decisions": n, "arms": {}}
    for w in weights:
        d = np.array([r[0] for r in rows[w]])
        sp = np.array([r[1] for r in rows[w]])
        rr = np.array([r[2] for r in rows[w]])
        bite = float(np.mean([r[3] for r in rows[w]]))
        ok = sp > 1e-9
        frac = float(np.median(d[ok] / sp[ok])) if ok.any() else 0.0
        fires = float((d > 1e-12).mean())
        print(f"  {w:>8.2f}{float(np.median(d)):>16.4f}"
              f"{float(np.percentile(d, 90)):>9.4f}{frac:>11.3f}"
              f"{float(np.mean(rr)):>8.3f}{fires:>8.1%}{bite:>8.1%}")
        out["arms"][str(w)] = {
            "median_abs_delta": float(np.median(d)),
            "p90_abs_delta": float(np.percentile(d, 90)),
            "median_delta_over_spread": frac,
            "mean_corr_with_score": float(np.mean(rr)),
            "fires": fires, "bite": bite}
    print("\n  For scale: `locate` measured median 0.0444, correlation +0.42")
    print("  and bite 3.9% at its shipped-scale weight, and came back")
    print("  +0.047 [-0.075, +0.168] over 3,000 pairs. A term that does not")
    print("  clear that by a wide margin is not worth a duel.")
    dest = ROOT / "results" / f"term_bite_{term}.json"
    dest.write_text(json.dumps(out, indent=1))
    print("\nwrote", dest)
    return 0


if __name__ == "__main__":
    v = sys.argv[1:]
    if not v:
        raise SystemExit(f"usage: term_bite.py <term> [n_games] [w ...]\n"
                         f"terms: {', '.join(TERM_NAMES)}")
    raise SystemExit(main(v[0], int(v[1]) if len(v) > 1 else 40,
                          tuple(float(x) for x in v[2:]) or
                          (0.15, 0.3, 0.6, 1.2)))
