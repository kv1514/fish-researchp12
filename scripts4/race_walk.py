"""Is a contested half-suit a random walk, and does the walk explain the loss?

WHERE THIS SITS. The ask-level accounting of the contested bands is now
complete and every channel is a few percent:

    channel (band 3, the even race)        ours      theirs
    selection ratio                      1.0555      1.1242
    access rate                          0.6965      0.6576   (ours better)
    asks per access ply                  0.24844     0.27496
    hit rate                             0.6059      0.6135
    card skill (within half-suit)        1.1034      1.1495
    target accuracy                      0.7583      0.7730
    take-backs per card taken            0.4102      0.4035
    HALF-SUITS WON                       0.4443      0.5557

A few percent on each side of the ledger, and eleven points of outcome. The
frontier's standing account is that these are "1-8% per-ask quantities
compounding in winner-take-all races to six", and compounding is the one part of
that sentence never checked. It is checkable rather than assertable.

THE STRUCTURE THAT MAKES IT CHECKABLE. Every card of a live half-suit is held by
someone, so our team's count and theirs sum to six at all times, and every
transfer moves one card one way. A band-3 half-suit is therefore a walk on our
count starting at 3, stepping +-1, absorbing at 6 (we assemble it) and 0 (they
do). That is a gambler's ruin with no free parameters once the step
probabilities are measured -- so the chain can be fitted from the OBSERVED
transitions and asked whether it reproduces the OBSERVED win rate. Nothing is
predicted out of sample; this is an internal-consistency test of the walk
description itself.

AND THAT TEST IS VACUOUS, which a smoke test showed before it was run at power
and before anything was written down. The chain CANNOT fail. Across the cut
between counts c and c+1, up-steps from c minus down-steps from c+1 is the net
flow, and a trajectory from the start to 6 crosses every cut above it exactly
once net -- so the transition counts ALGEBRAICALLY determine the absorption
counts. A chain fitted on those transitions reproduces the absorption frequency
by Kirchhoff's identity, not by being right. The band-3 miss of +0.0000 on the
smoke is that identity, not a passing test. It is reported as an identity and
retained only as an arithmetic check on the solver.

Two further things the walk CANNOT say, recorded so they are not reached for
later. There is only ONE transition process in a half-suit, because the two
counts sum to six, so their step profile is a reflection of ours -- their
P(up | their count j) is identically 1 - p_{6-j}. "Is our ladder steeper than
theirs" is therefore not a question about the data; it is one profile read
twice. And the same reflection makes any comparison of the two sides' ladders
degenerate by construction.

WHAT IS WELL POSED, and it is the transition-level form of the observation that
started this line. If the two policies were identical the process would be
invariant under swapping the teams, which requires

    p_c + p_{6-c} = 1    at every count c

exactly as the outcome-level pair 0.2860 + 0.3707 would have summed to 1. It
sums to 0.9153 instead, and that single number is the deficit. The residual
p_c + p_{6-c} - 1 is the same statement LOCALISED BY STATE: it says at which
holdings the two policies differ, and in which direction, with no reflection
degeneracy because it is a statement about one profile against its own
reflection.

THE ASSUMPTION THAT HAS TO BE TESTED FIRST, and it is load-bearing. The walk
framing assumes a half-suit is decided by reaching 0 or 6. It need not be: under
`wrong_distribution_outcome="opponent"` a team can declare with the split wrong
and hand it over at any count, and a game can end with a half-suit unresolved.
If a large share of contested half-suits are absorbed anywhere but 0 and 6, the
walk is the wrong description and THAT is the finding. Measured here before the
chain is solved, not assumed away.

Ground truth is a LABEL ONLY -- counts are read off the hands and never shown to
an agent. The band is our team's count AT THE DEAL, so it is exogenous.

Descriptive. No arm, no duel, no ship claim.
"""
from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import (CARDS_PER_HALF_SUIT, NUM_PLAYERS,          # noqa: E402
                        half_suit_mask, team_of)
from fish.engine import GameState                                  # noqa: E402
from fish.observation import Observation                           # noqa: E402
from fish.rules import RuleConfig                                  # noqa: E402
from scripts4.resultfile import default_path, write                # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}
SEED0 = 18_300_000
AGENT0 = 183_000
MAX_ACTIONS = 600
BOOT = 2000
BOOT_SEED = 20_261_001
BANDS = (2, 3, 4)


def _count(hands, hs: int, team: int) -> int:
    m = half_suit_mask(hs)
    return sum(bin(hands[p] & m).count("1")
               for p in range(NUM_PLAYERS) if team_of(p) == team)


def _solve(up: dict, dn: dict, start: int = 3) -> float | None:
    """P(absorb at 6 | start at ``start``) for the fitted birth-death chain.

    Solved exactly from the measured per-state step probabilities rather than
    assumed constant, so the chain is given every chance to reproduce the
    outcome. With p_c the chance the next step from count c is upward,
    h_c = P(reach 6 before 0 | at c) satisfies h_c = p_c h_{c+1} +
    (1-p_c) h_{c-1}, h_0 = 0, h_6 = 1 -- a tridiagonal system in h_1..h_5.
    """
    p = {}
    for c in range(1, 6):
        n = up.get(c, 0) + dn.get(c, 0)
        if not n:
            return None
        p[c] = up.get(c, 0) / n
    # tridiagonal solve, 5 unknowns
    A = [[0.0] * 5 for _ in range(5)]
    b = [0.0] * 5
    for i, c in enumerate(range(1, 6)):
        A[i][i] = -1.0
        if c - 1 >= 1:
            A[i][i - 1] = 1.0 - p[c]
        if c + 1 <= 5:
            A[i][i + 1] = p[c]
        else:
            b[i] -= p[c]          # h_6 = 1 moves to the right-hand side
    # Gaussian elimination, 5x5
    for i in range(5):
        piv = A[i][i]
        if abs(piv) < 1e-15:
            return None
        for j in range(i, 5):
            A[i][j] /= piv
        b[i] /= piv
        for r in range(5):
            if r != i and A[r][i]:
                f = A[r][i]
                for j in range(i, 5):
                    A[r][j] -= f * A[i][j]
                b[r] -= f * b[i]
    return b[start - 1]            # h_start, for h_1..h_5 indexed from 0


def _boot_ratio(per, num, den, boot=BOOT, seed=BOOT_SEED):
    rng = random.Random(seed)
    n = len(per)
    out = []
    for _ in range(boot):
        pick = [per[rng.randrange(n)] for _ in range(n)]
        a = sum(r.get(num, 0) for r in pick)
        b = sum(r.get(den, 0) for r in pick)
        if b:
            out.append(a / b)
    out.sort()
    if not out:
        return [float("nan")] * 2
    return [out[int(0.025 * len(out))],
            out[min(len(out) - 1, int(0.975 * len(out)))]]


def _boot_chain(per, band, boot=500, seed=BOOT_SEED):
    """Interval for the CHAIN's prediction, resampling games."""
    rng = random.Random(seed)
    n = len(per)
    out = []
    for _ in range(boot):
        pick = [per[rng.randrange(n)] for _ in range(n)]
        up = {c: sum(r.get(f"up_b{band}_c{c}", 0) for r in pick)
              for c in range(1, 6)}
        dn = {c: sum(r.get(f"dn_b{band}_c{c}", 0) for r in pick)
              for c in range(1, 6)}
        v = _solve(up, dn, band)
        if v is not None:
            out.append(v)
    out.sort()
    if not out:
        return [float("nan")] * 2
    return [out[int(0.025 * len(out))],
            out[min(len(out) - 1, int(0.975 * len(out)))]]


def _pool(per, c, bands=BANDS):
    """Transition counts at count ``c`` pooled over the contested bands.

    The band fixes only where a trajectory STARTS; the step probability at a
    given current count is the same process whichever band the half-suit was
    dealt in, so pooling is legitimate and triples the data behind each
    residual. Reported beside the per-band figures, never instead of them.
    """
    u = sum(r.get(f"up_b{b}_c{c}", 0) for r in per for b in bands)
    d = sum(r.get(f"dn_b{b}_c{c}", 0) for r in per for b in bands)
    return u, d


def _boot_resid_pooled(per, c, boot=BOOT, seed=BOOT_SEED):
    rng = random.Random(seed)
    n = len(per)
    out = []
    d_ = 6 - c
    for _ in range(boot):
        pick = [per[rng.randrange(n)] for _ in range(n)]
        u1, d1 = _pool(pick, c)
        u2, d2 = _pool(pick, d_)
        if (u1 + d1) and (u2 + d2):
            out.append(u1 / (u1 + d1) + u2 / (u2 + d2) - 1.0)
    out.sort()
    if not out:
        return [float("nan")] * 2
    return [out[int(0.025 * len(out))],
            out[min(len(out) - 1, int(0.975 * len(out)))]]


def _boot_resid(per, band, c, boot=BOOT, seed=BOOT_SEED):
    """Interval for p_c + p_{6-c} - 1, resampling GAMES.

    At c = 3 the reflection is the state itself, so the quantity is
    2*p_3 - 1 and the same expression with 6-c = c gives it directly.
    """
    rng = random.Random(seed)
    n = len(per)
    out = []
    d = 6 - c
    for _ in range(boot):
        pick = [per[rng.randrange(n)] for _ in range(n)]
        u1 = sum(r.get(f"up_b{band}_c{c}", 0) for r in pick)
        d1 = sum(r.get(f"dn_b{band}_c{c}", 0) for r in pick)
        u2 = sum(r.get(f"up_b{band}_c{d}", 0) for r in pick)
        d2 = sum(r.get(f"dn_b{band}_c{d}", 0) for r in pick)
        if (u1 + d1) and (u2 + d2):
            out.append(u1 / (u1 + d1) + u2 / (u2 + d2) - 1.0)
    out.sort()
    if not out:
        return [float("nan")] * 2
    return [out[int(0.025 * len(out))],
            out[min(len(out) - 1, int(0.975 * len(out)))]]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--games", type=int, default=400)
    ap.add_argument("--seed0", type=int, default=SEED0)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    seed0 = a.seed0

    from fish4.registry4 import KRAKEN_V1, make_agent
    from fish4.dylan_v07 import DylanV07

    rules = RuleConfig(**RULES_D)
    t0 = time.time()
    n_hs = 54 // CARDS_PER_HALF_SUIT
    per: list[dict] = []
    st_jump = 0        # a transition of size other than 1
    st_absorb_live = 0 # a half-suit at 0 or 6 that stayed live to the end
    #: NOT a self-test. Won at a count below six can only be the opponents
    #: declaring with the split wrong, which these rules award to us -- the same
    #: residual access_depletion found 43 of. Counted, because it is exactly the
    #: channel that would break the walk framing.
    n_won_off_six = 0
    n_lost_off_zero = 0

    for g in range(a.games):
        seed = seed0 + g
        kv_even = (g % 2 == 0)
        agents = [make_agent(KRAKEN_V1) if (p % 2 == 0) == kv_even
                  else DylanV07() for p in range(NUM_PLAYERS)]
        our_team = 0 if kv_even else 1
        st = GameState.deal(rules, seed=seed)
        for p, ag in enumerate(agents):
            ag.begin_game(p, rules, AGENT0 + seed * 13 + p)

        band = [_count(st.hands, h, our_team) for h in range(n_hs)]
        row = {"game": g}
        for b in BANDS:
            row[f"n_b{b}"] = sum(1 for h in range(n_hs) if band[h] == b)
            row[f"won_b{b}"] = 0
            for nm in ("end_6", "end_0", "end_other", "end_unresolved"):
                row[f"{nm}_b{b}"] = 0
            for c in range(1, 6):
                row[f"up_b{b}_c{c}"] = 0
                row[f"dn_b{b}_c{c}"] = 0

        cur = list(band)
        for _ in range(MAX_ACTIONS):
            if st.is_terminal:
                break
            actor = st.turn
            act = agents[actor].act(Observation.from_state(st, actor))
            st.apply(actor, act)
            for h in range(n_hs):
                if band[h] not in BANDS or st.set_winner[h] is not None:
                    continue
                new = _count(st.hands, h, our_team)
                if new == cur[h]:
                    continue
                if abs(new - cur[h]) != 1:
                    st_jump += 1
                b = band[h]
                # the step is recorded AT THE STATE IT LEFT, which is what the
                # chain's p_c means
                if 1 <= cur[h] <= 5:
                    key = "up" if new > cur[h] else "dn"
                    row[f"{key}_b{b}_c{cur[h]}"] += 1
                cur[h] = new

        for h in range(n_hs):
            if band[h] not in BANDS:
                continue
            b = band[h]
            # THE COUNT AT RESOLUTION, not at the end of the game. Declaring a
            # half-suit removes its cards from every hand, so reading the hands
            # afterwards returns 0 for a half-suit whoever won it -- which is
            # how the first draft of this reported that all 18 band-3 half-suits
            # "ended at 0" while we won half of them. cur[h] is not updated
            # after a half-suit resolves, so it holds the count immediately
            # before the declaration, which is the absorbing state.
            end = cur[h]
            w = st.set_winner[h]
            if w == our_team:
                row[f"won_b{b}"] += 1
                if end != 6:
                    n_won_off_six += 1
            elif w is not None and end != 0:
                n_lost_off_zero += 1
            if w is None:
                row[f"end_unresolved_b{b}"] += 1
                if end in (0, 6):
                    st_absorb_live += 1
            elif end == 6:
                row[f"end_6_b{b}"] += 1
            elif end == 0:
                row[f"end_0_b{b}"] += 1
            else:
                row[f"end_other_b{b}"] += 1
        per.append(row)
        if (g + 1) % 25 == 0 or g + 1 == a.games:
            print(f"  {g+1}/{a.games} games, {(time.time()-t0)/60:.1f} min",
                  flush=True)

    def tot(k):
        return sum(r.get(k, 0) for r in per)

    out = {"script": "scripts4/race_walk.py", "descriptive": True,
           "rules": RULES_D, "seed_deal": seed0, "seed_agent": AGENT0,
           "n_games": a.games, "bands": list(BANDS),
           "selftest_step_bigger_than_one": st_jump,
           "selftest_at_absorbing_count_but_still_live": st_absorb_live,
           "won_at_a_count_below_six": n_won_off_six,
           "lost_at_a_count_above_zero": n_lost_off_zero,
           "off_absorbing_wins_are": ("a declaration with the split wrong, "
                                      "which these rules award to the "
                                      "opponents; the channel that would "
                                      "break the walk framing"),
           "by_band": {}, "per_game": per}

    print("=" * 80)
    print(f"  THE WALK, {a.games} games, block {seed0:,}")
    print("  A live half-suit's two team counts sum to six, so every transfer")
    print("  is a +-1 step on our count. Absorbing at 6 (we assemble) and 0.")
    print("=" * 80)
    for b in BANDS:
        n = tot(f"n_b{b}")
        up = {c: tot(f"up_b{b}_c{c}") for c in range(1, 6)}
        dn = {c: tot(f"dn_b{b}_c{c}") for c in range(1, 6)}
        pred = _solve(up, dn, b)
        obs = (tot(f"won_b{b}") / n) if n else None
        d = {"n_half_suits": n, "observed_win_rate": obs,
             "observed_ci": _boot_ratio(per, f"won_b{b}", f"n_b{b}"),
             "ended_at_6": tot(f"end_6_b{b}"), "ended_at_0": tot(f"end_0_b{b}"),
             "ended_elsewhere": tot(f"end_other_b{b}"),
             "ended_unresolved": tot(f"end_unresolved_b{b}"),
             "share_absorbed_at_0_or_6":
                 ((tot(f"end_6_b{b}") + tot(f"end_0_b{b}")) / n) if n else None,
             "up": up, "dn": dn,
             "p_up_by_count": {c: (up[c] / (up[c] + dn[c]))
                               if (up[c] + dn[c]) else None
                               for c in range(1, 6)},
             "chain_prediction": pred,
             "chain_prediction_ci": _boot_chain(per, b),
             "miss": (obs - pred) if (obs is not None and pred is not None)
                     else None,
             "miss_is": ("an ARITHMETIC CHECK on the solver, not a test of the "
                         "walk: flow conservation makes the fitted chain "
                         "reproduce the absorption frequency identically"),
             #: THE MEASUREMENT. Symmetric play requires p_c + p_{6-c} = 1.
             "symmetry_residual": {
                 c: ((up[c] / (up[c] + dn[c])
                      + up[6 - c] / (up[6 - c] + dn[6 - c]) - 1.0)
                     if (c != 3 and (up[c] + dn[c]) and (up[6 - c] + dn[6 - c]))
                     else ((2.0 * up[c] / (up[c] + dn[c]) - 1.0)
                           if (c == 3 and (up[c] + dn[c])) else None))
                 for c in range(1, 6)},
             "symmetry_residual_ci": {
                 c: _boot_resid(per, b, c) for c in range(1, 6)}}
        out["by_band"][b] = d
        print()
        print(f"  band {b}   {n:,} half-suits   start count {b}")
        print(f"    where they ENDED: at 6 {d['ended_at_6']:,}   "
              f"at 0 {d['ended_at_0']:,}   elsewhere {d['ended_elsewhere']:,}"
              f"   unresolved {d['ended_unresolved']:,}")
        print(f"    share absorbed at 0 or 6: "
              f"{d['share_absorbed_at_0_or_6']:.4f}   "
              f"<-- the walk framing lives or dies here")
        print(f"    {'count':>7}  {'up':>7}  {'down':>7}  {'P(up)':>7}")
        for c in range(1, 6):
            pu = d["p_up_by_count"][c]
            print(f"    {c:>7}  {up[c]:>7,}  {dn[c]:>7,}  "
                  f"{(f'{pu:.4f}' if pu is not None else '—'):>7}")
        if pred is not None and obs is not None:
            olo, ohi = d["observed_ci"]
            print(f"    chain {pred:.4f} vs observed {obs:.4f} "
                  f"[{olo:.4f}, {ohi:.4f}]   miss {obs - pred:+.6f}")
            print("      (an IDENTITY by flow conservation, not a test --")
            print("       retained as an arithmetic check on the solver)")
        print(f"    SYMMETRY RESIDUAL  p_c + p_(6-c) - 1, which symmetric play")
        print(f"    requires to be 0 at every count:")
        for c in range(1, 4):
            r = d["symmetry_residual"][c]
            if r is None:
                continue
            lo, hi = d["symmetry_residual_ci"][c]
            tag = "  <-- the even state" if c == 3 else ""
            print(f"      c={c} vs {6-c}   {r:+.4f}  [{lo:+.4f}, {hi:+.4f}]{tag}")
    print()
    print("-" * 80)
    print("  SELF-TESTS -- both must be 0")
    print(f"    a step of size other than one        "
          f"{out['selftest_step_bigger_than_one']}")
    print(f"    at count 0 or 6 but still live       "
          f"{out['selftest_at_absorbing_count_but_still_live']}")
    print()
    print("  THE CHANNEL THAT WOULD BREAK THE WALK, counted not assumed:")
    print(f"    half-suits WON at a count below six  "
          f"{out['won_at_a_count_below_six']}")
    print(f"    half-suits LOST at a count above zero "
          f"{out['lost_at_a_count_above_zero']}")
    print("  Both are declarations with the split wrong. A walk cannot")
    print("  describe those, so a large share of them refutes the framing.")

    # -- pooled over the contested bands -----------------------------------
    pooled = {}
    for c in range(1, 6):
        u, dd = _pool(per, c)
        pooled[c] = {"up": u, "down": dd,
                     "p_up": (u / (u + dd)) if (u + dd) else None}
    resid = {}
    for c in range(1, 4):
        u1, d1 = _pool(per, c)
        u2, d2 = _pool(per, 6 - c)
        if (u1 + d1) and (u2 + d2):
            resid[c] = {"residual": (u1 / (u1 + d1) + u2 / (u2 + d2) - 1.0),
                        "ci": _boot_resid_pooled(per, c),
                        "n": (u1 + d1) + (u2 + d2)}
    out["pooled"] = {"p_up_by_count": pooled, "symmetry_residual": resid,
                     "pooling_is": ("the band fixes only where a trajectory "
                                    "starts; the step probability at a given "
                                    "current count is the same process")}
    print()
    print("=" * 80)
    print("  POOLED OVER THE CONTESTED BANDS -- the band fixes only where a")
    print("  trajectory starts, so the step probability at a given count is")
    print("  one process and pooling triples the data behind each residual.")
    print(f"    {'count':>7}  {'up':>8}  {'down':>8}  {'P(up)':>8}")
    for c in range(1, 6):
        q = pooled[c]
        pu = f"{q['p_up']:.4f}" if q["p_up"] is not None else "—"
        print(f"    {c:>7}  {q['up']:>8,}  {q['down']:>8,}  {pu:>8}")
    print()
    print("  SYMMETRY RESIDUAL  p_c + p_(6-c) - 1.  Symmetric play requires 0")
    print("  at every count. This is the transition-level form of the outcome")
    print("  pair that summed to 0.9153 instead of 1, localised by state.")
    for c in range(1, 4):
        if c not in resid:
            continue
        r = resid[c]
        lo, hi = r["ci"]
        clear = "CLEAR OF ZERO" if (lo > 0 or hi < 0) else "covers zero"
        tag = "  (the even state, = 2*p_3 - 1)" if c == 3 else ""
        print(f"    c={c} vs {6-c}   {r['residual']:+.4f}  "
              f"[{lo:+.4f}, {hi:+.4f}]  {clear}   n={r['n']:,}{tag}")

    dest = Path(a.out) if a.out else default_path("race_walk", seed0)
    write(dest, out)
    print(f"\n  wrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
