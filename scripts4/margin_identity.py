"""The margin is an identity, not a model. Three channels, and only three.

Under `wrong_distribution_outcome="opponent"` the NULL_TEAM branch in
`engine._apply_claim` is unreachable, so each of the nine half-suits is awarded
to exactly one team by exactly one ClaimEvent, and no half-suit is awarded any
other way. Write D for declarations a side makes and W for the ones it loses:

    ours   = (D_us   - W_us)   + W_them
    theirs = (D_them - W_them) + W_us
    D_us + D_them = 9

    margin = ours - theirs = 2 * (D_us - W_us + W_them) - 9

So a change in the margin is exactly a change in three counters, each worth two
sets a head:

    RACE    how many of the nine we get to declare at all      +2 each
    OURS    how many of the ones we declare we get wrong       -2 each
    THEIRS  how many of the ones they declare they get wrong   +2 each

IT IS AN ACCOUNTING, NOT A CAUSAL DECOMPOSITION. Each channel is exactly what
happened to that counter, and the three sum to the effect exactly. They are not
independent: a half-suit we stop declaring is one THEY declare, so it leaves
RACE and arrives in THEIRS carrying their error rate with it. No single channel
may be read as "what this arm would gain if only that counter moved", and
`rates` below exists to separate the part of THEIRS that is merely that
handover from the part that is a change in how well the opponents declare.

WHY THIS FILE EXISTS. Every instrument in the signalling line reported the
second channel and neither of the others, and the line then spent a week asking
where a margin went that its own ledger could not hold. The identity closes:
given a run's margins and its ledger of OUR declarations, the opponent's wrong
count is not unknown, it is determined -- and a run that also measures it
directly (`both_sides`) has to agree, which is the check `verify` performs.

    py scripts4/margin_identity.py [results/a.json ...] [--sweep]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

#: The identity holds only under the award rule that makes NULL_TEAM
#: unreachable. Under "null" a wrong distribution retires a half-suit to
#: neither side, `ours + theirs < 9`, and the residual below stops being zero.
REQUIRED_RULE = {"wrong_distribution_outcome": "opponent"}
N_HALF_SUITS = 9

#: A run's stated margin and its ledger are computed from the same games, so
#: the residual is float noise on a few tens of thousands of integer counts.
#: Anything above this is a real disagreement: a dropped declaration path, a
#: game that never finished, or the wrong award rule.
TOL = 1e-9


def _boot_mean(xs, reps: int = 4000, seed: int = 20_250_920):
    """A percentile bootstrap of a mean over GAMES.

    Deliberately not a normal-approximation standard error. These per-game
    channel values are small integers on a bounded support -- RACE takes nine
    values, OURS and THEIRS are counts that are zero most of the time -- and
    the normal interval on a zero-inflated count is the one this project has
    already had to widen once.
    """
    import numpy as np
    a = np.asarray(xs, dtype=float)
    rng = np.random.default_rng(seed)
    m = a[rng.integers(0, len(a), (reps, len(a)))].mean(1)
    lo, hi = np.percentile(m, [2.5, 97.5])
    return float(lo), float(hi)


def our_counts(ledger: dict, games: int) -> tuple[float, float]:
    """(declarations, wrong declarations) a game, from the raw integers.

    Not from `per_game` and `_wrong_per_game`: those are rounded to four
    places, and four places times nine half-suits is inside the effects this
    line is trying to resolve.
    """
    d = w = 0
    for path, v in ledger.items():
        if path.startswith("_"):
            continue
        d += v["n"]
        w += v["wrong"]
    return d / games, w / games


def their_wrong(margin: float, d_us: float, w_us: float) -> float:
    """The opponent's wrong declarations a game, from the identity.

    This is a residual, not a measurement: it absorbs any error in the other
    three numbers. It is worth reading only where the run cannot measure it,
    and worth checking against `both_sides` wherever the run can.
    """
    return (margin + N_HALF_SUITS) / 2 - d_us + w_us


def channels(payload: dict, arm: str) -> dict:
    games = payload["n_games"]
    margin = payload["margins"][arm]["mean"]
    d_us, w_us = our_counts(payload["ledger"][arm], games)
    solved = their_wrong(margin, d_us, w_us)
    out = {"margin": margin, "d_us": d_us, "w_us": w_us,
           "w_them": solved, "w_them_source": "solved from the identity"}
    meas = (payload.get("both_sides") or {}).get(arm)
    if meas is not None:
        m = meas["their_wrong"] / games
        out["w_them_measured"] = m
        out["w_them_residual"] = solved - m
        out["w_them_source"] = "measured, and it agrees with the identity"
        out["d_them"] = meas["their_declares"] / games
    return out


def verify(payload: dict) -> list[str]:
    """Every way this payload can contradict the identity. Empty means clean."""
    bad = []
    if payload.get("rules") != REQUIRED_RULE:
        bad.append(f"award rule is {payload.get('rules')!r}, not "
                   f"{REQUIRED_RULE!r}: NULL_TEAM is reachable and the "
                   f"identity does not hold")
    if payload.get("unfinished"):
        bad.append(f"{payload['unfinished']} games never finished, so their "
                   f"nine half-suits were not all awarded")
    for arm, fails in (payload.get("integrality_failures") or {}).items():
        i, deal, du, wt, m, wu = fails[0]
        bad.append(f"{arm}: {len(fails)} of {payload['n_games']} games solve "
                   f"to a non-integral or out-of-range count of OUR wrong "
                   f"declarations; first is row {i} (deal {deal}) with "
                   f"d_us={du}, w_them={wt}, margin={m} giving w_us={wu:.4f}")
    games = payload["n_games"]
    for arm in payload["margins"]:
        c = channels(payload, arm)
        if "w_them_measured" not in c:
            continue
        if abs(c["w_them_residual"]) > TOL:
            bad.append(f"{arm}: the identity wants {c['w_them']:.6f} wrong "
                       f"opponent declarations a game and the run counted "
                       f"{c['w_them_measured']:.6f}")
        d_them = c["d_them"]
        if abs(c["d_us"] + d_them - N_HALF_SUITS) > TOL:
            bad.append(f"{arm}: {c['d_us']:.4f} + {d_them:.4f} declarations a "
                       f"game is not {N_HALF_SUITS}")
    return bad


def headroom(payload: dict, arm: str) -> dict:
    """The most each channel could ever give, from this arm's own counters.

    Bounds, not targets, and not simultaneously reachable -- a half-suit moved
    into RACE leaves THEIRS. They are worth computing for one reason: the
    OURS bound is small, fixed and nearly spent, and it is the only channel
    this project has ever optimised.

      OURS    declare perfectly:            2 * w_us
      RACE    declare all nine at our own
              current accuracy:             2*(9 - w_us*9/d_us) - 9 - margin
      THEIRS  they are wrong on every one
              they declare:                 2 * (d_them - w_them)
    """
    games = payload["n_games"]
    m = payload["margins"][arm]["mean"]
    d_us, w_us = our_counts(payload["ledger"][arm], games)
    w_them = their_wrong(m, d_us, w_us)
    d_them = N_HALF_SUITS - d_us
    e_us = w_us / d_us if d_us else 0.0
    return {"ours": 2 * w_us,
            "race": (2 * (N_HALF_SUITS * (1 - e_us)) - N_HALF_SUITS) - m,
            "theirs": 2 * (d_them - w_them)}


def rates(payload: dict, base: str, arm: str) -> dict:
    """Split the THEIRS channel into volume and rate.

    Handing the opponents a half-suit adds wrong opponent declarations even if
    nothing about their play changed, because they are wrong about a fifth of
    the time either way. That part is arithmetic and says nothing. The part
    that is a change in their per-declaration ERROR RATE is the part that is a
    claim about the opponents.

        w_them = d_them * e_them
        d(w_them) = e_base * dd  +  d_base * de  +  dd * de

    reported x2, in margin units, so the three sum to the THEIRS channel.
    """
    b, a = channels(payload, base), channels(payload, arm)
    d_b, d_a = N_HALF_SUITS - b["d_us"], N_HALF_SUITS - a["d_us"]
    e_b = b["w_them"] / d_b if d_b else 0.0
    e_a = a["w_them"] / d_a if d_a else 0.0
    dd, de = d_a - d_b, e_a - e_b
    return {"their_err_base": e_b, "their_err_arm": e_a,
            "our_err_base": b["w_us"] / b["d_us"] if b["d_us"] else 0.0,
            "our_err_arm": a["w_us"] / a["d_us"] if a["d_us"] else 0.0,
            "volume": 2 * e_b * dd, "rate": 2 * d_b * de,
            "interaction": 2 * dd * de}


def decompose(payload: dict, base: str, arm: str) -> dict:
    """The arm's effect, split into the three channels it can come from.

    Each channel is reported in MARGIN units -- two sets a declaration -- so
    they sum to the effect rather than to something proportional to it.
    """
    b, a = channels(payload, base), channels(payload, arm)
    race = 2 * (a["d_us"] - b["d_us"])
    ours = -2 * (a["w_us"] - b["w_us"])
    theirs = 2 * (a["w_them"] - b["w_them"])
    total = a["margin"] - b["margin"]
    return {"base": base, "arm": arm, "effect": total,
            "race": race, "ours": ours, "theirs": theirs,
            "residual": total - (race + ours + theirs),
            **rates(payload, base, arm)}


def absolute(payload: dict, arm: str) -> dict:
    """The three channels of the MARGIN ITSELF, against a parity reference.

    `decompose` splits the DIFFERENCE between two arms. That is the right
    object when asking what an arm changed, and the wrong one when asking
    where a standing deficit lives -- which is the question a retraction
    leaves behind, because after a retraction there is no base arm to
    difference against. The reference here is parity: nine half-suits split
    4.5/4.5 with nobody ever wrong, which scores 0.

        margin = 2*(d_us - w_us + w_them) - 9
               = 2*(d_us - 4.5)  +  (-2*w_us)  +  (2*w_them)
               =      RACE       +     OURS    +   THEIRS

    exactly, with no residual, because it is the identity rearranged. The
    same warning applies as everywhere else in this file: the channels are an
    accounting and they co-move. A half-suit we do not declare is one they
    do, so it leaves RACE and arrives in THEIRS carrying their error rate.
    """
    c = channels(payload, arm)
    race = 2 * (c["d_us"] - N_HALF_SUITS / 2)
    ours = -2 * c["w_us"]
    theirs = 2 * c["w_them"]
    return {"arm": arm, "margin": c["margin"], "race": race, "ours": ours,
            "theirs": theirs, "residual": c["margin"] - (race + ours + theirs),
            "d_us": c["d_us"], "w_us": c["w_us"], "w_them": c["w_them"]}


def _bridge_arm(rows: list[dict], arm: str) -> dict:
    """One bridge arm's per-game counters, solved and checked per game.

    The bridge instruments record the OPPONENT's side -- how many half-suits
    they declared and how many of those were wrong -- and the margin. Our own
    wrong count is then not free: the identity determines it,

        w_us = d_us + w_them - (margin + 9)/2

    game by game. In the canonical ledger shape it is the other way round and
    `verify` cross-checks a measured opponent count against a solved one.
    Here that cross-check would be vacuous, because the only opponent numbers
    available are the ones the solve already used. The check that is NOT
    vacuous is integrality: `w_us` counts declarations, so per game it must
    come out a non-negative whole number no larger than `d_us`. A transport
    that drops a declaration, a game that did not finish, or the wrong award
    rule all break that, and nothing else in this shape would catch them.
    """
    d_us, w_us, w_them, margin, bad = [], [], [], [], []
    for i, r in enumerate(rows):
        a = r[arm]
        du = N_HALF_SUITS - a["their_declarations"]
        wt = a["their_ownership_errors"] + a["their_allocation_errors"]
        wu = du + wt - (a["margin"] + N_HALF_SUITS) / 2
        if abs(wu - round(wu)) > 1e-9 or wu < -1e-9 or wu > du + 1e-9:
            bad.append((i, r.get("deal"), du, wt, a["margin"], wu))
        d_us.append(du)
        w_us.append(wu)
        w_them.append(wt)
        margin.append(a["margin"])
    return {"d_us": d_us, "w_us": w_us, "w_them": w_them, "margin": margin,
            "integrality_failures": bad}


def from_bridge(payload: dict) -> dict | None:
    """Normalise a `bridge_*_price` run into the canonical margins+ledger shape.

    These runs predate this file's shape and carry `per_pair`, one row per
    (deal, seating) with each arm's counters on it. They are the only record
    of how the corrected transport actually plays, so the identity has to
    reach them or the post-retraction picture stays a hand calculation across
    two files -- which is exactly how it was being read.
    """
    rows = payload.get("per_pair")
    arms = payload.get("margins")
    if not isinstance(rows, list) or not isinstance(arms, dict) or not rows:
        return None
    if not all(isinstance(r, dict) and "margin" in r
               for r in rows[0].values() if isinstance(r, dict)):
        return None
    n = len(rows)
    ledger, both, margins, per_game, failures = {}, {}, {}, {}, {}
    for arm in arms:
        if not all(arm in r for r in rows):
            return None
        c = _bridge_arm(rows, arm)
        if c["integrality_failures"]:
            failures[arm] = c["integrality_failures"]
        ledger[arm] = {"identity": {"n": sum(c["d_us"]),
                                    "wrong": sum(c["w_us"])}}
        both[arm] = {"their_wrong": sum(c["w_them"]),
                     "their_declares": sum(N_HALF_SUITS - d
                                           for d in c["d_us"])}
        margins[arm] = {"mean": sum(c["margin"]) / n}
        per_game[arm] = c
    return dict(payload, n_games=n, rules=REQUIRED_RULE, ledger=ledger,
                margins=margins, both_sides=both, per_game=per_game,
                integrality_failures=failures, vs="dylan_v07",
                _w_us_is_solved=True)


def adapt(payload: dict) -> dict | None:
    """Normalise the shapes this project has stored margins-plus-ledger in.

    The identity is older than any of these files -- it has been true of every
    game the project has played -- so a run is worth decomposing whichever
    instrument wrote it. Three shapes exist. `None` means the payload is not a
    run of this kind at all.

      * canonical, from `signal_vs_defer` and `signal_no_repeat`:
        `margins[arm]["mean"]` and `ledger[arm]`.
      * the `*_confirm` shape, from the arm-vs-champion instruments:
        `margin_A` for the base and `arms[arm]["margin"]` for the rest.
      * `path_ledger_self`, ONE arm played against itself with no `margins`
        block: refused, because a symmetric self-play margin is zero by
        construction and the identity says nothing about it.

    `vs: "self"` is not itself disqualifying. A run that seats the champion
    opposite itself but puts the arm on only one side is asymmetric, carries a
    `margins` block, and decomposes like any other -- which is the whole point
    of asking whether an effect measured in the opponent's counters survives a
    change of opponent.
    """
    if not isinstance(payload, dict):
        return None
    if "ledger" not in payload:
        return from_bridge(payload)
    if "margins" in payload:
        return payload
    if payload.get("vs") == "self":
        return None
    if "margin_A" not in payload or "arms" not in payload:
        return None
    margins = {"A_shipped": {"mean": payload["margin_A"]}}
    for name, v in payload["arms"].items():
        if isinstance(v, dict) and "margin" in v:
            margins[name] = {"mean": v["margin"]}
    if set(margins) != set(payload["ledger"]):
        return None
    return dict(payload, margins=margins)


def report(path: Path, base: str | None = None) -> int:
    payload = adapt(json.loads(path.read_text()))
    if payload is None:
        print(f"{path.name}: not a margins-plus-ledger run, skipping")
        return 0
    print(f"\n=== {path.name}   ({payload['n_games']:,} games, "
          f"{payload.get('prereg', 'no registration')})")
    bad = verify(payload)
    for line in bad:
        print(f"  IDENTITY BROKEN  {line}")
    print(f"  {'arm':<14}{'margin':>9}{'decl/game':>11}{'ours wrong':>12}"
          f"{'theirs wrong':>14}  source")
    for arm in payload["margins"]:
        c = channels(payload, arm)
        print(f"  {arm:<14}{c['margin']:>+9.4f}{c['d_us']:>11.4f}"
              f"{c['w_us']:>12.4f}{c['w_them']:>14.4f}  {c['w_them_source']}")
    print(f"\n  --- where each arm's MARGIN lives, against parity ---")
    print(f"  (RACE = 2*(d_us - 4.5), OURS = -2*w_us, THEIRS = +2*w_them;")
    print(f"   they sum to the margin exactly, and they co-move)")
    pg = payload.get("per_game")
    ci = "  [95% over games]" if pg else ""
    print(f"  {'arm':<14}{'margin':>9}{'race':>9}{'ours':>9}{'theirs':>9}"
          f"{'resid':>8}{ci}")
    for arm in payload["margins"]:
        ab = absolute(payload, arm)
        tail = ""
        if pg:
            c = pg[arm]
            per = [2 * (d - N_HALF_SUITS / 2) - 2 * wu + 2 * wt
                   for d, wu, wt in zip(c["d_us"], c["w_us"], c["w_them"])]
            lo, hi = _boot_mean(per)
            tail = f"  [{lo:+.3f}, {hi:+.3f}]"
        print(f"  {arm:<14}{ab['margin']:>+9.4f}{ab['race']:>+9.4f}"
              f"{ab['ours']:>+9.4f}{ab['theirs']:>+9.4f}"
              f"{ab['residual']:>+8.4f}{tail}")
    if payload.get("_w_us_is_solved"):
        print("  w_us is SOLVED from the identity here, not counted: these")
        print("  runs record the opponent's declarations and not ours. The")
        print("  check that bites in this shape is per-game integrality, and")
        print("  it is run above.")

    # WHICH ARM IS THE BASE MATTERS, and defaulting to the first one is how
    # a retracted transport came to anchor a headroom table. `published` in
    # the bridge runs is the withdrawn stateless bridge; reading headroom off
    # it describes a game this project no longer claims to have played.
    if base is not None and base not in payload["margins"]:
        print(f"  no arm named {base!r}; have "
              f"{', '.join(payload['margins'])}")
        return 1
    base = base or next(iter(payload["margins"]))
    print(f"\n  --- where each arm's effect lives, in margin units, "
          f"vs {base} ---")
    print(f"  (an accounting, not a causal split: the channels co-move)")
    print(f"  {'arm':<14}{'effect':>9}{'race':>9}{'ours':>9}{'theirs':>9}"
          f"{'resid':>9}")
    for arm in payload["margins"]:
        if arm == base:
            continue
        d = decompose(payload, base, arm)
        print(f"  {arm:<14}{d['effect']:>+9.4f}{d['race']:>+9.4f}"
              f"{d['ours']:>+9.4f}{d['theirs']:>+9.4f}{d['residual']:>+9.4f}")
    h = headroom(payload, base)
    print(f"\n  --- the most each channel could ever give, from {base} ---")
    print(f"      (bounds, not targets, and not simultaneously reachable)")
    print(f"      ours   declare perfectly            {h['ours']:>+8.3f}")
    print(f"      race   declare all nine             {h['race']:>+8.3f}")
    print(f"      theirs they never get one right     {h['theirs']:>+8.3f}")
    print(f"\n  --- per-declaration error rates, and the THEIRS channel split "
          f"into\n      the half-suits handed over and the rate they are "
          f"declared at ---")
    print(f"  {'arm':<14}{'ours':>8}{'theirs':>9}{'volume':>10}{'rate':>9}"
          f"{'cross':>9}")
    print(f"  {base + ' (base)':<14}"
          f"{decompose(payload, base, base)['our_err_base']:>8.4f}"
          f"{decompose(payload, base, base)['their_err_base']:>9.4f}")
    for arm in payload["margins"]:
        if arm == base:
            continue
        d = decompose(payload, base, arm)
        print(f"  {arm:<14}{d['our_err_arm']:>8.4f}{d['their_err_arm']:>9.4f}"
              f"{d['volume']:>+10.4f}{d['rate']:>+9.4f}"
              f"{d['interaction']:>+9.4f}")
    return 1 if bad else 0


def sweep(paths: list[Path]) -> list[dict]:
    """One row per (run, arm): the effect and its three channels, in one table.

    A single run's decomposition is a reading. The same decomposition holding
    across runs at different seeds, sample sizes and engine revisions is the
    thing worth believing, and it is only visible side by side.
    """
    rows, skipped = [], []
    for path in paths:
        try:
            payload = adapt(json.loads(path.read_text()))
        except (ValueError, OSError) as e:
            skipped.append((path.stem, f"unreadable: {type(e).__name__}"))
            continue
        if payload is None:
            continue                      # not a run of this shape at all
        bad = verify(payload)
        if bad:
            #: NOT silently. A run excluded without saying so is how a table
            #: comes to describe only the data that agreed with it, and it is
            #: the exact failure this instrument was written to catch.
            skipped.append((path.stem, bad[0]))
            continue
        base = next(iter(payload["margins"]))
        for arm in payload["margins"]:
            if arm == base:
                continue
            d = decompose(payload, base, arm)
            #: The opponent belongs in the row. Every arm here was measured
            #: against `dylan_v07` until signal_generality, and a table that
            #: cannot show the opponent invites reading two opponents as a
            #: replication of one. It already did: the sweep's own signalling
            #: rows now disagree, and the disagreement IS the opponent.
            rows.append(dict(d, run=path.stem, games=payload["n_games"],
                             vs=payload.get("vs", "dylan_v07"),
                             params=(payload.get("arms") or {}).get(arm)))
    rows.sort(key=lambda r: -r["effect"])
    print(f"\n=== every arm this project has measured, by channel "
          f"({len(rows)} arms)")
    print(f"  {'run':<30}{'arm':<13}{'vs':<11}{'games':>7}{'effect':>9}"
          f"{'race':>9}{'ours':>9}{'theirs':>9}")
    for r in rows:
        print(f"  {r['run'][:29]:<30}{r['arm'][:12]:<13}{r['vs'][:10]:<11}"
              f"{r['games']:>7}{r['effect']:>+9.4f}{r['race']:>+9.4f}"
              f"{r['ours']:>+9.4f}{r['theirs']:>+9.4f}")
    if skipped:
        print(f"\n  --- EXCLUDED, and why ({len(skipped)}) ---")
        for name, why in skipped:
            print(f"  {name[:33]:<34}{why}")
    return rows


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    base = next((a.split("=", 1)[1] for a in argv
                 if a.startswith("--base=")), None)
    paths = [Path(a) for a in args] or sorted(
        (ROOT / "results").glob("*.json"))
    if "--sweep" in argv:
        sweep(paths)
        return 0
    return max([report(p, base) for p in paths] or [0])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
