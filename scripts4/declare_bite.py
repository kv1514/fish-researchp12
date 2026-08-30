"""How big is the declarability term, what does it re-state, and does it bite?

WHY THIS SCRIPT EXISTS BEFORE ANY DUEL DOES
-------------------------------------------
`prereg/locate_term.md` came back null at 3,000 pairs and the only reason that
null was worth anything is that it was DIAGNOSED afterwards: the term was worth
0.013 on a score whose P(success) term alone spans ~1.0, correlated +0.42 with
the objective it was meant to correct, and changed the top-ranked ask in 3.9% of
positions. A term that re-ranks 4% of asks by 1% of the scale cannot move 1.57
sets a game, and no amount of duelling would have said so.

That diagnosis was run after the fact, against a hand-copied fragment of
``FishBot4.act``. This runs the same three measurements through the real
objective, via ``fish4.agent4._SCORE_RECORDER``, and it runs BEFORE the duel so
that a term too small to matter is caught for the price of a few minutes rather
than a few thousand pairs.

It is a screen for FUTILITY, not for value. Passing it means the term is large
enough that a duel can resolve it; it says nothing about the sign.

    py scripts4/declare_bite.py [n_games] [w_declare ...]
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

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 8_300_000


def _corr(a, b) -> float:
    a, b = np.asarray(a, dtype=float), np.asarray(b, dtype=float)
    if a.std() <= 1e-12 or b.std() <= 1e-12:
        return 0.0
    return float(np.corrcoef(a, b)[0, 1])


def main(n_games: int = 60, weights=(0.25, 0.5, 1.0, 2.0)) -> int:
    import fish4.agent4 as A
    from fish4.lookahead import lookahead_bonus
    from fish4.registry4 import V06_DEPLOYED, make_agent

    cfg = dict(V06_DEPLOYED[1])
    w_look = cfg["w_lookahead"]
    depth, beam = cfg["lookahead_depth"], cfg["lookahead_beam"]
    rows = {w: [] for w in weights}

    def recorder(bot, ctx, asks, scores):
        if len(asks) < 2:
            return
        base = np.asarray(scores, dtype=float)
        b0 = lookahead_bonus(ctx, asks, depth=depth, beam=beam)
        top0 = int(np.argmax(base))
        spread = float(base.max() - base.min())
        for w in weights:
            bw = lookahead_bonus(ctx, asks, depth=depth, beam=beam,
                                 w_declare=w)
            # The champion's `scores` already carry w_look * b0, so the
            # counterfactual objective is the champion's plus the DELTA. Adding
            # w_look * bw would double the cards component.
            delta = w_look * (bw - b0)
            alt = base + delta
            r = _corr(base, delta)
            # THE COLLINEARITY QUESTION, and the reason this column exists.
            # `base` already carries w_look * b0, so a correlation against it
            # cannot say WHICH part of the objective the new term restates.
            # This one is against the cards chain alone, and against the score
            # with the chain removed. If declarability along a possession is
            # mostly a restatement of cards banked along it -- which is the
            # obvious worry, since taking cards is what makes half-suits
            # nameable -- it shows up here and nowhere else.
            rows[w].append((float(np.abs(delta).max()), spread, r,
                            int(int(np.argmax(alt)) != top0),
                            _corr(w_look * b0, delta),
                            _corr(base - w_look * b0, delta)))

    rules = RuleConfig(**RULES_D)
    A._SCORE_RECORDER = recorder
    try:
        for g in range(n_games):
            seed = SEED0 + g
            agents = [make_agent(("fishbot4", dict(cfg)))
                      for _ in range(NUM_PLAYERS)]
            st = GameState.deal(rules, seed=seed)
            for p, a in enumerate(agents):
                a.begin_game(p, rules, 83_000 + seed * 13 + p)
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
    print("\n" + "=" * 72)
    print(f"  DECLARABILITY BITE, {n:,} real champion ask decisions")
    print(f"  (w_lookahead = {w_look}, depth {depth}, beam {beam})")
    print("=" * 72)
    print(f"\n  {'w_declare':>10}{'median |delta|':>16}{'p90':>9}"
          f"{'/ spread':>10}{'r score':>9}{'r cards':>9}{'r rest':>8}"
          f"{'bite':>8}")
    out = {"rules": RULES_D, "n_decisions": n, "w_lookahead": w_look,
           "depth": depth, "beam": beam, "arms": {}}
    for w in weights:
        d = np.array([r[0] for r in rows[w]])
        sp = np.array([r[1] for r in rows[w]])
        rr = np.array([r[2] for r in rows[w]])
        bite = float(np.mean([r[3] for r in rows[w]]))
        frac = float(np.median(d[sp > 1e-9] / sp[sp > 1e-9]))
        rc = np.array([r[4] for r in rows[w]])
        ro = np.array([r[5] for r in rows[w]])
        print(f"  {w:>10.2f}{float(np.median(d)):>16.4f}"
              f"{float(np.percentile(d, 90)):>9.4f}{frac:>10.3f}"
              f"{float(np.mean(rr)):>9.3f}{float(np.mean(rc)):>9.3f}"
              f"{float(np.mean(ro)):>8.3f}{bite:>8.1%}")
        out["arms"][str(w)] = {
            "median_abs_delta": float(np.median(d)),
            "p90_abs_delta": float(np.percentile(d, 90)),
            "median_delta_over_spread": frac,
            "mean_corr_with_score": float(np.mean(rr)),
            "mean_corr_with_cards_chain": float(np.mean(rc)),
            "mean_corr_with_score_less_chain": float(np.mean(ro)),
            "bite": bite}
    print("\n  For scale, the `locate` term measured median 0.0444 / p90 0.1136")
    print("  at its shipped-scale weight, correlation +0.42, and bite 3.9% --")
    print("  and came back +0.047 [-0.075, +0.168] over 3,000 pairs. A term")
    print("  that does not clear those by a wide margin is not worth a duel.")
    dest = ROOT / "results" / "declare_bite.json"
    if dest.exists():
        # Arms from an earlier grid are kept only when the run they came from
        # saw the SAME decisions -- same games, same champion, same decision
        # count. Bite is a fraction of a specific position distribution, so
        # merging arms measured on different positions would make a column
        # that is not comparable down its own length.
        prev = json.loads(dest.read_text())
        same = all(prev.get(k) == out[k] for k in
                   ("n_decisions", "w_lookahead", "depth", "beam", "rules"))
        if same:
            merged = dict(prev.get("arms", {}))
            merged.update(out["arms"])
            out["arms"] = merged
            print(f"  merged {len(prev.get('arms', {}))} arm(s) from the "
                  f"earlier grid: same {out['n_decisions']:,} decisions")
        else:
            print("  earlier arms DISCARDED: a different position set")
    dest.write_text(json.dumps(out, indent=1))
    print("\nwrote", dest)
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 60,
                          tuple(float(x) for x in a[1:]) or
                          (0.25, 0.5, 1.0, 2.0)))
