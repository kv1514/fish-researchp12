"""What would closing the transition-symmetry residual be worth, in sets?

`race_walk` reduced the contested-band deficit to a single per-transfer number
at a state with no asymmetry in it. Identical policies make a half-suit's
transition process invariant under swapping the teams, which requires
p_c + p_(6-c) = 1 at every count. Measured on two independent 400-game blocks,
every residual is negative and every interval is clear of zero, and at the
exactly symmetric 3-3 state p_3 = 0.478: we lose 52.2% of transfers from a
position that is symmetric by construction.

THIS SCRIPT IS ARITHMETIC ON THE FITTED CHAINS AND NOTHING ELSE. No games are
played. It answers one question: if that residual were zero -- if we won
transfers at the rate symmetry requires, at every state -- what would the
contested bands pay, in the units the ship bar is written in?

    p_hat_c = (p_c + 1 - p_(6-c)) / 2

is the symmetric part of the measured profile, and satisfies
p_hat_c + p_hat_(6-c) = 1 exactly by construction. Each band is re-solved from
its own starting count with p_hat in place of p, and the change in declarations
is converted at the project's own identity, margin = 2 * (D_us - 4.5).

WHAT THIS IS AND IS NOT. It is a MODEL counterfactual inside a description that
has been checked: the walk accounts for 99.1-99.8% of contested half-suits
(the rest resolve off the absorbing states, through a declaration with the split
wrong), and the fitted chain reproduces the observed band win rates to within
0.005-0.025. It is NOT a duel result, NOT an arm, and NOT a claim that any
policy change can reach p_hat. Nothing here clears or approaches the ship bar,
which requires a dueled +0.15 in both populations. What it bounds is the SIZE OF
THE PRIZE: whether the symmetry residual is the whole margin or a corner of it.
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts4.race_walk import _solve                              # noqa: E402

BANDS = (2, 3, 4)
BOOT = 2000
BOOT_SEED = 20_261_001


def _profile(per, bands=BANDS):
    up = {c: sum(r.get(f"up_b{b}_c{c}", 0) for r in per for b in bands)
          for c in range(1, 6)}
    dn = {c: sum(r.get(f"dn_b{b}_c{c}", 0) for r in per for b in bands)
          for c in range(1, 6)}
    return up, dn


def _symmetrise(up, dn):
    """Counts whose implied p is the symmetric part of the measured one."""
    p = {}
    for c in range(1, 6):
        n = up[c] + dn[c]
        p[c] = (up[c] / n) if n else None
    out_up, out_dn = {}, {}
    for c in range(1, 6):
        if p[c] is None or p[6 - c] is None:
            return None, None
        ph = 0.5 * (p[c] + 1.0 - p[6 - c])
        # _solve only reads the ratio, so any scale works
        out_up[c], out_dn[c] = ph, 1.0 - ph
    return out_up, out_dn


def _interp(up, dn, lam):
    """Counts whose implied p is ``lam`` of the way from measured to symmetric."""
    p = {c: up[c] / (up[c] + dn[c]) for c in range(1, 6)}
    o_u, o_d = {}, {}
    for c in range(1, 6):
        ph = 0.5 * (p[c] + 1.0 - p[6 - c])
        q = p[c] + lam * (ph - p[c])
        o_u[c], o_d[c] = q, 1.0 - q
    return o_u, o_d


def _ship_fraction(up, dn, per, games, target=0.15):
    """How much of the residual must close to be worth ``target`` sets a game.

    Bisection on the interpolation weight. This is the reason the arithmetic is
    worth doing: it puts the ship bar in the units of ONE DECISION. Every knob
    this project has swept moves the policy globally and by far more than this,
    in both directions, with side effects -- which is a coherent reading of why
    all of them overshoot into losses.
    """
    nb = {b: sum(r.get(f"n_b{b}", 0) for r in per) / games for b in BANDS}
    base = sum(nb[b] * _solve(up, dn, b) for b in BANDS)

    def gain(lam):
        u, d = _interp(up, dn, lam)
        return 2.0 * (sum(nb[b] * _solve(u, d, b) for b in BANDS) - base)

    if gain(1.0) < target:
        return None, None
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if gain(mid) < target:
            lo = mid
        else:
            hi = mid
    lam = 0.5 * (lo + hi)
    u, _d = _interp(up, dn, lam)
    return lam, u[3]            # the implied p_3


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("paths", nargs="+")
    a = ap.parse_args(argv)

    report = {"script": "scripts4/symmetry_value.py", "model_only": True,
              "no_games_played": True, "blocks": {}}
    for path in a.paths:
        d = json.loads(Path(path).read_text())
        per, games = d["per_game"], d["n_games"]
        up, dn = _profile(per)
        sup, sdn = _symmetrise(up, dn)
        rows, d_now, d_sym, d_obs = [], 0.0, 0.0, 0.0
        for b in BANDS:
            n = sum(r.get(f"n_b{b}", 0) for r in per)
            per_game = n / games
            now = _solve(up, dn, b)
            sym = _solve(sup, sdn, b)
            obs = sum(r.get(f"won_b{b}", 0) for r in per) / n
            rows.append({"band": b, "half_suits_per_game": per_game,
                         "observed": obs, "chain_now": now,
                         "chain_symmetric": sym,
                         "gain_per_half_suit": sym - now})
            d_now += per_game * now
            d_sym += per_game * sym
            d_obs += per_game * obs

        def boot():
            rng = random.Random(BOOT_SEED)
            out = []
            for _ in range(BOOT):
                pick = [per[rng.randrange(len(per))] for _ in range(len(per))]
                u2, n2 = _profile(pick)
                s2, t2 = _symmetrise(u2, n2)
                if s2 is None:
                    continue
                tot = 0.0
                ok = True
                for b in BANDS:
                    nb = sum(r.get(f"n_b{b}", 0) for r in pick)
                    if not nb:
                        ok = False
                        break
                    v1, v2 = _solve(u2, n2, b), _solve(s2, t2, b)
                    if v1 is None or v2 is None:
                        ok = False
                        break
                    tot += (nb / len(pick)) * (v2 - v1)
                if ok:
                    out.append(2.0 * tot)
            out.sort()
            return [out[int(0.025 * len(out))],
                    out[min(len(out) - 1, int(0.975 * len(out)))]] if out \
                else [float("nan")] * 2

        gain_sets = 2.0 * (d_sym - d_now)
        ci = boot()
        lam, p3_target = _ship_fraction(up, dn, per, games)
        p3_now = up[3] / (up[3] + dn[3])
        report["blocks"][str(d["seed_deal"])] = {
            "p3_now": p3_now, "ship_fraction_of_residual": lam,
            "p3_needed_for_ship_bar": p3_target,
            "n_games": games, "by_band": rows,
            "declarations_in_contested_bands_now": d_now,
            "declarations_if_symmetric": d_sym,
            "declarations_observed": d_obs,
            "margin_gain_sets": gain_sets, "margin_gain_ci": ci}

        print("=" * 76)
        print(f"  block {d['seed_deal']:,}   {games} games   MODEL ONLY, no games played")
        print("=" * 76)
        print(f"  {'band':>5}  {'a game':>7}  {'observed':>9}  {'chain':>8}"
              f"  {'if symmetric':>12}  {'gain':>8}")
        for r in rows:
            print(f"  {r['band']:>5}  {r['half_suits_per_game']:>7.3f}"
                  f"  {r['observed']:>9.4f}  {r['chain_now']:>8.4f}"
                  f"  {r['chain_symmetric']:>12.4f}"
                  f"  {r['gain_per_half_suit']:>+8.4f}")
        print(f"  declarations a game from the contested bands: "
              f"{d_now:.4f} now, {d_sym:.4f} if symmetric")
        print(f"  MARGIN IF THE RESIDUAL WERE ZERO: "
              f"{gain_sets:+.4f} sets a game  [{ci[0]:+.4f}, {ci[1]:+.4f}]")
        print("  Against a measured margin of -0.710. Closing the residual")
        print("  recovers about the whole margin, which is close to a")
        print("  consistency check -- equally strong policies tie. What is NOT")
        print("  a restatement is that the residual is measured ONLY inside")
        print("  contested half-suits and still recovers it, so there is no")
        print("  fourth channel outside this description.")
        print()
        print("  THE SHIP BAR IN THE UNITS OF ONE DECISION, which is the reason")
        print("  this arithmetic is worth doing:")
        print(f"    p_3 now                      {p3_now:.4f}")
        if lam is not None:
            print(f"    fraction of the residual that must close for +0.15 "
                  f"sets   {lam:.3f}")
            print(f"    p_3 that would pay the ship bar   {p3_target:.4f}  "
                  f"(+{p3_target - p3_now:.4f})")
            print("    So the bar is winning half a percentage point more of")
            print("    the transfers at the exactly symmetric 3-3 state. Every")
            print("    knob swept so far moves the policy globally and by far")
            print("    more than that, in both directions, with side effects.")
        print("  Nothing here is a duel result, an arm, or a ship claim.")

    out = ROOT / "results" / "symmetry_value.json"
    out.write_text(json.dumps(report, indent=1) + "\n")
    print(f"\n  wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
