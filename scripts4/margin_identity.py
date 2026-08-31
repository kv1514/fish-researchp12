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

WHY THIS FILE EXISTS. Every instrument in the signalling line reported the
second channel and neither of the others, and the line then spent a week asking
where a margin went that its own ledger could not hold. The identity closes:
given a run's margins and its ledger of OUR declarations, the opponent's wrong
count is not unknown, it is determined -- and a run that also measures it
directly (`both_sides`) has to agree, which is the check `verify` performs.

    py scripts4/margin_identity.py results/a.json [results/b.json ...]
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
            "residual": total - (race + ours + theirs)}


def report(path: Path) -> int:
    payload = json.loads(path.read_text())
    if "margins" not in payload or "ledger" not in payload:
        print(f"{path.name}: no margins/ledger, skipping")
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
    base = next(iter(payload["margins"]))
    print(f"\n  --- where each arm's effect lives, in margin units ---")
    print(f"  {'arm':<14}{'effect':>9}{'race':>9}{'ours':>9}{'theirs':>9}"
          f"{'resid':>9}")
    for arm in payload["margins"]:
        if arm == base:
            continue
        d = decompose(payload, base, arm)
        print(f"  {arm:<14}{d['effect']:>+9.4f}{d['race']:>+9.4f}"
              f"{d['ours']:>+9.4f}{d['theirs']:>+9.4f}{d['residual']:>+9.4f}")
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv] or sorted(
        (ROOT / "results").glob("signal_*.json"))
    return max([report(p) for p in paths] or [0])


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
