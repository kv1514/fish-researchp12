"""Does the endgame ask defect extend to m = 3, where exact solving cannot go?

v0.5 found, using the EXACT one-ply value, that the engine's ask is beaten by
another ask on 51% of unpinned m = 1 positions and 61% at m = 2, that the better
move is an ASK, and that it is systematically riskier. The correction that
followed ships and is worth +0.1220 sets.

That method reaches under a tenth of the game. ``oneply_sampled_check.py``
established that a SAMPLED one-ply target, drawn from the agent's own
posterior, makes the same decisions as the exact one at a cost of +0.0033 in
the exact target's units -- so the target itself travels. This asks whether the
DEFECT travels with it.

WHY m = 3 AND NOT FURTHER
-------------------------
Timed on real positions, one sampled target at 128 worlds costs about 19 s of
rollout at m = 3, 162 s at m = 4, 422 s at m = 5 and 1955 s at m = 9. The
rollout has to play until the half-suit resolves however the target is scoped,
and computing the engine's move at every ply is what costs. m = 3 is 7.8% of
decisions and affordable; m >= 5 is not, at any sample size worth having. That
is a limit of this method and it is reported as one rather than worked around.

WHAT WOULD SHOW THE DEFECT DOES NOT EXTEND
------------------------------------------
If the engine's ask is beaten about as rarely at m = 3 as chance would give, or
if the better ask is no riskier than the engine's, then what the solver found in
the endgame is a property of the endgame and not of the ask objective, and
raising the correction's m threshold has no reason to help. That is a real
possible outcome: with seven half-suits still to come, an ask that gambles is
paid for out of a much longer remaining game.

    py scripts4/oneply_m3_defect.py [n_positions] [n_worlds] [layer] [first_game]
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
from fish4.askfeat import TERM_NAMES, DecisionContext, ask_feature_matrix
from fish4.exact_ii import ExactII, _champion_action, _info_key
from fish4.posterior import Posterior
from fish4.registry4 import make_agent

SPEC = ("fishbot4", {"opponent_gamma": 0.35})
JOURNAL = ROOT / "results" / "oneply_m3_targets.jsonl"


def _fp() -> str:
    h = hashlib.sha256()
    for f in ("fish4/exact_ii.py", "fish4/askfeat.py", "fish4/posterior.py"):
        h.update((ROOT / f).read_bytes())
    h.update(Path(__file__).resolve().read_bytes())
    # The rules are part of what the stored numbers MEAN: a row
    # computed under one misdeclaration rule must never be resumed
    # into a run playing the other, so the rule set is in the hash.
    h.update(repr(RuleConfig()).encode())
    return h.hexdigest()[:12]


def _ctx_and_worlds(rules, seat, st, n_worlds):
    """The agent's own view and its own posterior draws, seeded as it seeds."""
    obs = Observation.from_state(st, seat)
    key = _info_key(seat, obs)
    a = make_agent(SPEC)
    a.begin_game(seat, rules, int.from_bytes(key[:8], "big"))
    a.bel.update(obs)
    post = Posterior(a.bel, a.rng, n_draws=a.n_draws, n_worlds=n_worlds,
                     mode=a.infer_mode, obs=obs, gamma=a.opponent_gamma,
                     depth_mode=a.depth_mode, count_mode=a.count_mode,
                     opp_lambda=a.opp_lambda,
                     gamma_schedule=a.gamma_schedule, sis_tilt=a.sis_tilt)
    return obs, DecisionContext(obs, a.bel, post), post.worlds()


def main(n_positions: int = 60, n_worlds: int = 64, layer: int = 3,
         first_game: int = 0) -> int:
    rules = RuleConfig()
    fp = _fp()
    done, rows = set(), []
    if JOURNAL.exists():
        for line in JOURNAL.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                if r.get("solver") == fp and r.get("worlds") == n_worlds:
                    done.add((r["layer"], r["game"], r["index"]))
                    rows.append(r)
    print(f"  fingerprint {fp}; {len(done)} positions already collected "
          f"at {n_worlds} worlds")

    new = 0
    for g in range(first_game, 400):
        if len(rows) >= n_positions:
            break
        agents = [make_agent(SPEC) for _ in range(NUM_PLAYERS)]
        st = GameState.deal(rules, seed=99_000 + g)
        ar = random.Random(99_500 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        idx = 0
        for _ in range(600):
            if st.is_terminal or len(rows) >= n_positions:
                break
            p = st.turn
            obs0 = Observation.from_state(st, p)
            live = [h for h, w in enumerate(obs0.set_winner) if w is None]
            if len(live) == layer:
                idx += 1
                if (layer, g, idx) not in done:
                    t0 = time.time()
                    obs, ctx, worlds = _ctx_and_worlds(rules, p, st, n_worlds)
                    asks = obs.legal_asks()
                    if len(asks) >= 2:
                        pr, F = ask_feature_matrix(ctx, asks)
                        probe = ExactII(rules, list(live), p, SPEC)
                        vals = []
                        for a in asks:
                            tot, ok = 0.0, True
                            for hands in worlds:
                                t = GameState.from_components(
                                    rules, list(hands), st.turn,
                                    list(st.set_winner))
                                t.history = list(st.history)
                                try:
                                    t.apply(p, a)
                                except Exception:
                                    ok = False
                                    break
                                tot += probe.champion_value([t], [1.0])
                            vals.append(tot / len(worlds) if ok else None)
                        champ = _champion_action(SPEC, rules, p, st)
                        rec = {"layer": layer, "game": g, "index": idx,
                               "solver": fp, "worlds": n_worlds,
                               "asks": [repr(a) for a in asks],
                               "champion_action": repr(champ),
                               "p": [float(x) for x in pr],
                               "features": [[float(x) for x in row]
                                            for row in F],
                               "values": vals,
                               "seconds": time.time() - t0}
                        rows.append(rec)
                        new += 1
                        with JOURNAL.open("a") as fh:
                            fh.write(json.dumps(rec) + "\n")
                        if new % 5 == 0:
                            print(f"    {len(rows)} positions "
                                  f"(game {g}, {len(asks)} asks, "
                                  f"{time.time()-t0:.0f}s)", flush=True)
            st.apply(p, agents[p].act(obs0))

    if len(rows) < 15:
        print(f"only {len(rows)} positions; too few to report")
        return 1
    beaten = riskier = safer = same = 0
    gains, dp = [], []
    for r in rows:
        vals, pr = r["values"], r["p"]
        idxs = [i for i, v in enumerate(vals) if v is not None]
        if len(idxs) < 2:
            continue
        try:
            ci = r["asks"].index(r["champion_action"])
        except ValueError:
            continue
        if vals[ci] is None:
            continue
        bi = max(idxs, key=lambda i: vals[i])
        if vals[bi] > vals[ci] + 1e-9:
            beaten += 1
            gains.append(vals[bi] - vals[ci])
            d = pr[bi] - pr[ci]
            dp.append(d)
            if d < -1e-9:
                riskier += 1
            elif d > 1e-9:
                safer += 1
            else:
                same += 1
    n = sum(1 for r in rows if r["champion_action"] in r["asks"])
    print(f"\nm = {layer}: {len(rows)} positions, {n} with the engine's ask "
          f"among the candidates")
    print(f"  the engine's ask is beaten by another on {beaten}/{n} "
          f"({100.0*beaten/max(n,1):.0f}%)")
    if beaten:
        mg = sum(gains) / len(gains)
        md = sum(dp) / len(dp)
        var = sum((x - md) ** 2 for x in dp) / (len(dp) - 1) if len(dp) > 1 else 0.0
        se = (var / len(dp)) ** 0.5
        print(f"  mean gain from the better ask: {mg:+.4f}")
        print(f"  the better ask's hit rate minus the engine's: {md:+.4f}"
              + (f", t = {md/se:+.2f}" if se > 0 else ""))
        print(f"  riskier on {riskier}, safer on {safer}, equal on {same}")
        if md < 0 and se > 0 and md / se < -2:
            print(f"\n  The defect extends: at m = {layer} the better ask is "
                  f"RISKIER too, on the\n  same sign and a comparable size to "
                  f"m = 1 and m = 2. Raising the\n  correction's threshold has "
                  f"a reason to help.")
        else:
            print(f"\n  The defect does NOT extend in the same form. What the "
                  f"solver found in\n  the endgame looks like a property of "
                  f"the endgame, and raising the\n  threshold has no "
                  f"mechanism behind it.")
    dest = ROOT / "results" / f"oneply_m{layer}_defect.json"
    dest.write_text(json.dumps({
        "layer": layer, "worlds": n_worlds, "n": len(rows),
        "n_with_champion": n, "beaten": beaten,
        "mean_gain": (sum(gains) / len(gains)) if gains else None,
        "mean_dp": (sum(dp) / len(dp)) if dp else None,
        "riskier": riskier, "safer": safer, "equal": same}, indent=1))
    print(f"\nwrote {dest.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 60,
                          int(a[1]) if len(a) > 1 else 64,
                          int(a[2]) if len(a) > 2 else 3,
                          int(a[3]) if len(a) > 3 else 0))
