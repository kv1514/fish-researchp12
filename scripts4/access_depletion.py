"""Does the contested band turn on ACCESS -- the seats that can still ask there?

WHERE THIS SITS. `contested_race` put the entire measured margin in the
contested bands (bands 2-4 are short by -0.718 sets against a measured margin of
-0.710) and found no single per-ask edge inside them large enough to be the
cause: they send 8% more asks per ply into the even race and hit 1.3% better,
neither remotely the size of the outcome gap. Its one sharp asymmetry was that
we lose the behind positions (0.2860 holding two) by more than we win the ahead
ones (0.6293 holding four) -- a pair that would sum to exactly 1.0 under
symmetric play and instead sums to 0.9153. Read the other way, that single
number IS the deficit: from behind they convert 0.3707 where we convert 0.2860,
**8.47 points**, and the same 8.47 comes back at band four.

Three dose sweeps over 19,200 duel games then established that the ask
objective's half-suit-level preferences are at a joint optimum, so this cannot
be an asks-per-ply quantity: investing more when behind is exactly what P53, P54
and P55 tested, on both signs of both knobs, and every downward step lost.

THE QUANTITY NO ARM COULD HAVE MOVED. An ask is legal only if the ACTING SEAT
holds a card of the half-suit. So a team's ability to contest a half-suit is not
"how many cards does the team hold" but "does the seat with the turn hold one",
and those come apart: two cards in one seat gives access on a third of the
team's plies, two cards in two seats on two thirds.

And that resource is STRICTLY DEPLETING. A seat can only come to hold a card of
a half-suit by asking for one, which requires it to already hold one -- so the
set of seats with access to a half-suit is fixed at the deal and can only ever
SHRINK, never grow. There is no recovering access once a seat's last card of a
half-suit is taken. Asserted on every event here, not assumed.

A WARNING ABOUT THE OBVIOUS VERSION OF THIS, which a smoke test refuted before
this instrument was run at power. "Did the team reach zero cards in the
half-suit" is NOT a mechanism: reaching zero means the opponents hold all six,
and under these rules every half-suit is eventually declared by whoever
assembles it, so lockout is losing the half-suit RESTATED. The smoke test shows
it: P(win | retained access) came out 1.0000 in every band for both sides, and
the lockout rate summed with the win rate to 1. A decomposition whose second
factor is pinned at one by the rules of the game has no content, and it is
reported below only as the near-tautology it is, with the one genuine residual
broken out -- a locked-out team can still take a half-suit when the opponents
declare it with the split wrong, which these rules award to the opponents.

WHAT IS NOT PINNED, and is the reason this instrument exists. `contested_race`
measured asks sent into a half-suit per ply it was LIVE, and found they send 8%
more than we do into the even race. But an ask into a half-suit is impossible
from a seat that holds none of it, so asks per live ply conflates WILLINGNESS to
contest with ABILITY to. Asks per ACCESS ply -- per ply on which the seat holding
the turn could legally ask there -- is the same quantity with the ability divided
out, and the two answer different questions:

    same under both denominators    the gap is preference, and three dose
                                    sweeps say preference is at its optimum
    gap closes or inverts under     the gap is ACCESS, which no weight on the
    the access denominator          ask objective can move, and which would
                                    explain five consecutive null arms

Access is also symmetric at the deal and strictly depleting thereafter, so any
asymmetry in it is entirely the work of play. Both halves of that are asserted
below rather than assumed.

WHY NOTHING CHARGES FOR IT, from the shipping weights rather than from the
basis. Ten of the thirteen ask terms ship at 0.0. The champion's entire live
objective is three numbers -- `suit` 0.06 on own depth, `turn` 0.6 on handing the
turn to a full hand, `scarce` 0.2 on team share of the half-suit -- and not one
of them is a SEAT-level quantity. `suit` and `scarce` are both satisfied by the
same seat getting deeper, which is what a successful ask does: the card goes to
the asker, who by the legality rule already had access there, so a success can
never widen the team's access and the two live terms that drive accumulation are
one-sided with respect to it.

Two terms that might have priced it do not. `concent`, which rewards
concentrating the team's holding because concentration makes a half-suit safer
to declare, ships at 0.0, so the obvious story -- that the engine is paid to
concentrate -- is NOT what is happening here and is not claimed. `expose`, which
charges for handing the turn to an opponent who can rob us, also ships at 0.0,
and even at weight it counts robbable cards without distinguishing one that
costs a card from one that costs the half-suit permanently. `_exposure` does
compute P(player holds >= 1 of a half-suit), but only for OPPONENTS, as a threat
estimate. Our own team's access is computed nowhere, at any weight.

This is also the complement of a refuted hypothesis rather than a repeat of it.
The disclosure instrument established that we are NOT taken back more often than
they are -- the asymmetry ran the other way. So if our access dies faster it
cannot be because we are robbed more; it has to be that our robberies land more
often on a seat's LAST card of a half-suit. That conditional -- access deaths per
card taken -- is measured here and is the sharp form of the question.

The band is our team's count AT THE DEAL, so it is exogenous: nothing a policy
did can move which band a half-suit started in. Ground truth is a LABEL ONLY and
is never shown to an agent. History and hands only -- no posterior is sampled,
so there is no sampling error of its own and no stale-belief exposure.

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
                        half_suit_mask, half_suit_of, team_of)
from fish.engine import Ask, GameState                             # noqa: E402
from fish.observation import Observation                            # noqa: E402
from fish.rules import RuleConfig                                   # noqa: E402
from scripts4.resultfile import default_path, write                # noqa: E402

RULES_D = {"wrong_distribution_outcome": "opponent"}
#: deliberately the SAME deal and agent seeds as scripts4/contested_race.py, so
#: every figure here is on the identical games as the 0.2860 / 0.6293 it is
#: decomposing and no part of a difference can be a seed block.
SEED0 = 18_300_000
AGENT0 = 183_000
MAX_ACTIONS = 600
BOOT = 2000
BOOT_SEED = 20_261_001
BANDS = (2, 3, 4)
SIDES = ("ours", "theirs")


def _seats(hands, hs: int, team: int) -> list[int]:
    """Seats of ``team`` holding at least one card of ``hs``.

    This is the ACCESS SET whose monotonicity is asserted below. It is not
    quite the set of seats an ask is legal from -- see :func:`_askable`.
    """
    m = half_suit_mask(hs)
    return [p for p in range(NUM_PLAYERS)
            if team_of(p) == team and (hands[p] & m)]


def _askable(hands, hs: int, p: int) -> bool:
    """Would the engine accept an ask in ``hs`` from seat ``p``?

    Holding a card of the half-suit is the rule, but it is not sufficient, and
    the two exceptions were found by cross-checking this predicate against
    ``Observation.legal_asks`` rather than reasoned about: 47 disagreements in
    6,087 checks, every one of them either

      * ``p`` holds ALL SIX cards, so there is nothing left to ask for (34), or
      * no opponent has a card in hand at all, so there is no legal target (13).

    Both are positions where the race is already over, so including them would
    be a small bias -- but NOT a neutral one. A side that assembles more
    half-suits accrues more of the first kind, and SESTINA assembles 4.832 a
    game against our 4.100, so leaving them in would inflate THEIR access
    denominator and deflate their asks per access ply: it would bias the
    comparison toward the hypothesis under test. Hence the exact predicate.
    """
    m = half_suit_mask(hs)
    held = hands[p] & m
    if not held or held == m:
        return False
    return any(hands[q] for q in range(NUM_PLAYERS) if team_of(q) != team_of(p))


def _boot(per: list[dict], num: str, den: str,
          boot: int = BOOT, seed: int = BOOT_SEED) -> list[float]:
    """Bootstrap over GAMES. The unit of resampling is the game because every
    half-suit, ply and take event within one game shares its deal and its two
    policies; resampling half-suits would understate the interval."""
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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--games", type=int, default=400)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)

    from fish4.registry4 import KRAKEN_V1, make_agent
    from fish4.dylan_v07 import DylanV07

    rules = RuleConfig(**RULES_D)
    t0 = time.time()
    n_hs = 54 // CARDS_PER_HALF_SUIT
    per: list[dict] = []
    # -- self-tests, each counting a thing that must be impossible -----------
    st_illegal_seat = 0     # an ask from a seat holding none of the half-suit
    st_same_team = 0        # an ask at one's own teammate
    st_access_grew = 0      # the access set grew: refutes the monotonicity
    st_asked_unaskable = 0  # the engine accepted an ask _askable calls illegal
    #: NOT a self-test. Under wrong_distribution_outcome="opponent" a team
    #: holding none of a half-suit still takes it when the opponents declare it
    #: with the split wrong, so this is the one real residual in an otherwise
    #: tautological decomposition and is measured rather than asserted away.
    n_won_after_lockout = 0
    st_identity = 0         # won != won_retained + won_after_lockout
    st_band_range = 0

    for g in range(a.games):
        seed = SEED0 + g
        kv_even = (g % 2 == 0)
        agents = [make_agent(KRAKEN_V1) if (p % 2 == 0) == kv_even
                  else DylanV07() for p in range(NUM_PLAYERS)]
        ours = {p for p in range(NUM_PLAYERS) if (p % 2 == 0) == kv_even}
        our_team = 0 if kv_even else 1
        team_side = {our_team: "ours", 1 - our_team: "theirs"}
        st = GameState.deal(rules, seed=seed)
        for p, ag in enumerate(agents):
            ag.begin_game(p, rules, AGENT0 + seed * 13 + p)

        band = [sum(bin(st.hands[p] & half_suit_mask(h)).count("1")
                    for p in range(NUM_PLAYERS) if team_of(p) == our_team)
                for h in range(n_hs)]
        for b in band:
            if not 0 <= b <= 6:
                st_band_range += 1

        row = {"game": g}
        for b in BANDS:
            row[f"n_b{b}"] = sum(1 for h in range(n_hs) if band[h] == b)
            for s in SIDES:
                for k in ("s0", "took_from", "access_death", "lockout",
                          "won", "retained", "won_retained", "won_locked",
                          "seatsum", "liveplies", "accessplies", "turnplies",
                          "asks", "hits", "asks_acc", "hits_acc"):
                    row[f"{s}_{k}_b{b}"] = 0

        #: access seats per (half-suit, team) at the deal. Monotone from here.
        acc = {(h, t): set(_seats(st.hands, h, t))
               for h in range(n_hs) for t in (0, 1)}
        locked = {(h, t): False for h in range(n_hs) for t in (0, 1)}
        for h in range(n_hs):
            if band[h] in BANDS:
                for t in (0, 1):
                    row[f"{team_side[t]}_s0_b{band[h]}"] += len(acc[(h, t)])

        for _ in range(MAX_ACTIONS):
            if st.is_terminal:
                break
            actor = st.turn
            act = agents[actor].act(Observation.from_state(st, actor))
            a_side = team_side[team_of(actor)]

            # -- the exposure denominators, before anything moves -----------
            # Counted for the ACTING side only, because access is a property of
            # the seat that has the turn: a ply on which the opponents cannot
            # reach a half-suit is not an opportunity they declined.
            for h in range(n_hs):
                if st.set_winner[h] is not None or band[h] not in BANDS:
                    continue
                b = band[h]
                row[f"{a_side}_liveplies_b{b}"] += 1
                seats = acc[(h, team_of(actor))]
                row[f"{a_side}_seatsum_b{b}"] += len(seats)
                # Both denominators use the engine's exact legality, so a ply
                # on which NO seat of the team could have asked here counts as
                # an opportunity for neither side.
                if any(_askable(st.hands, h, q) for q in seats):
                    row[f"{a_side}_turnplies_b{b}"] += 1
                    if _askable(st.hands, h, actor):
                        row[f"{a_side}_accessplies_b{b}"] += 1

            if isinstance(act, Ask):
                h = half_suit_of(act.card)
                if not (st.hands[actor] & half_suit_mask(h)):
                    st_illegal_seat += 1
                if not _askable(st.hands, h, actor):
                    st_asked_unaskable += 1
                if team_of(act.target) == team_of(actor):
                    st_same_team += 1
                hit = bool(st.hands[act.target] >> act.card & 1)
                if band[h] in BANDS:
                    b = band[h]
                    row[f"{a_side}_asks_b{b}"] += 1
                    row[f"{a_side}_hits_b{b}"] += int(hit)
                    if hit:
                        v_side = team_side[team_of(act.target)]
                        row[f"{v_side}_took_from_b{b}"] += 1

            st.apply(actor, act)

            # -- recompute access and assert it only ever shrinks ------------
            for h in range(n_hs):
                if st.set_winner[h] is not None:
                    continue
                for t in (0, 1):
                    now = set(_seats(st.hands, h, t))
                    was = acc[(h, t)]
                    if now - was:
                        st_access_grew += 1
                    died = was - now
                    if died and band[h] in BANDS:
                        row[f"{team_side[t]}_access_death_b{band[h]}"] += len(died)
                    acc[(h, t)] = now
                    if not now and not locked[(h, t)]:
                        locked[(h, t)] = True
                        if band[h] in BANDS:
                            row[f"{team_side[t]}_lockout_b{band[h]}"] += 1

        for h in range(n_hs):
            if band[h] not in BANDS:
                continue
            b = band[h]
            for t in (0, 1):
                s = team_side[t]
                won = st.set_winner[h] == t
                if won:
                    row[f"{s}_won_b{b}"] += 1
                if locked[(h, t)]:
                    if won:
                        n_won_after_lockout += 1
                        row[f"{s}_won_locked_b{b}"] += 1
                else:
                    row[f"{s}_retained_b{b}"] += 1
                    if won:
                        row[f"{s}_won_retained_b{b}"] += 1
                if won and not (row[f"{s}_won_retained_b{b}"]
                                + row[f"{s}_won_locked_b{b}"]
                                == row[f"{s}_won_b{b}"]):
                    st_identity += 1
        per.append(row)
        if (g + 1) % 25 == 0 or g + 1 == a.games:
            print(f"  {g+1}/{a.games} games, {(time.time()-t0)/60:.1f} min",
                  flush=True)

    def tot(k):
        return sum(r.get(k, 0) for r in per)

    out = {"script": "scripts4/access_depletion.py", "descriptive": True,
           "rules": RULES_D, "seed_deal": SEED0, "seed_agent": AGENT0,
           "n_games": a.games, "bands": list(BANDS),
           "band_is": "our team's count of the half-suit AT THE DEAL",
           "selftest_ask_from_seat_without_access": st_illegal_seat,
           "selftest_ask_at_teammate": st_same_team,
           "selftest_access_set_grew": st_access_grew,
           "selftest_engine_accepted_an_unaskable_ask": st_asked_unaskable,
           "selftest_win_decomposition_identity": st_identity,
           "won_after_lockout": n_won_after_lockout,
           "won_after_lockout_is": ("the opponents declared it with the split "
                                    "wrong; the only way a team holding none "
                                    "of a half-suit still takes it"),
           "selftest_band_out_of_range": st_band_range,
           "by_side_band": {}, "matched": {}, "per_game": per}

    for s in SIDES:
        for b in BANDS:
            n = tot(f"n_b{b}")
            d = {
                "n_half_suits": n,
                "seats_at_deal": (tot(f"{s}_s0_b{b}") / n) if n else None,
                "mean_access_seats": ((tot(f"{s}_seatsum_b{b}")
                                       / tot(f"{s}_liveplies_b{b}"))
                                      if tot(f"{s}_liveplies_b{b}") else None),
                # the headline access rate: of this side's plies on which its
                # team could still reach the half-suit, the share on which the
                # seat holding the turn was one that could
                "access_rate": ((tot(f"{s}_accessplies_b{b}")
                                 / tot(f"{s}_turnplies_b{b}"))
                                if tot(f"{s}_turnplies_b{b}") else None),
                "access_rate_ci": _boot(per, f"{s}_accessplies_b{b}",
                                        f"{s}_turnplies_b{b}"),
                # the SAME quantity contested_race reports, under its own
                # denominator and then under the one that divides out ability
                "asks": tot(f"{s}_asks_b{b}"),
                "hit_rate": ((tot(f"{s}_hits_b{b}") / tot(f"{s}_asks_b{b}"))
                             if tot(f"{s}_asks_b{b}") else None),
                "asks_per_live_ply": ((tot(f"{s}_asks_b{b}")
                                       / tot(f"{s}_liveplies_b{b}"))
                                      if tot(f"{s}_liveplies_b{b}") else None),
                "asks_per_live_ply_ci": _boot(per, f"{s}_asks_b{b}",
                                              f"{s}_liveplies_b{b}"),
                "asks_per_access_ply": ((tot(f"{s}_asks_b{b}")
                                         / tot(f"{s}_accessplies_b{b}"))
                                        if tot(f"{s}_accessplies_b{b}") else None),
                "asks_per_access_ply_ci": _boot(per, f"{s}_asks_b{b}",
                                                f"{s}_accessplies_b{b}"),
                "cards_taken_from": tot(f"{s}_took_from_b{b}"),
                "access_deaths": tot(f"{s}_access_death_b{b}"),
                # the conditional the disclosure refutation leaves open: given a
                # card IS taken from this side, how often is it a seat's last
                "death_per_card_taken": ((tot(f"{s}_access_death_b{b}")
                                          / tot(f"{s}_took_from_b{b}"))
                                         if tot(f"{s}_took_from_b{b}") else None),
                "death_per_card_ci": _boot(per, f"{s}_access_death_b{b}",
                                           f"{s}_took_from_b{b}"),
                "lockouts": tot(f"{s}_lockout_b{b}"),
                "lockout_rate": (tot(f"{s}_lockout_b{b}") / n) if n else None,
                "lockout_rate_ci": _boot(per, f"{s}_lockout_b{b}", f"n_b{b}"),
                "win_rate": (tot(f"{s}_won_b{b}") / n) if n else None,
                "win_rate_ci": _boot(per, f"{s}_won_b{b}", f"n_b{b}"),
                "retained": tot(f"{s}_retained_b{b}"),
                "win_rate_given_retained":
                    ((tot(f"{s}_won_retained_b{b}") / tot(f"{s}_retained_b{b}"))
                     if tot(f"{s}_retained_b{b}") else None),
                "win_rate_given_retained_ci":
                    _boot(per, f"{s}_won_retained_b{b}", f"{s}_retained_b{b}"),
                "won_after_lockout": tot(f"{s}_won_locked_b{b}"),
            }
            out["by_side_band"][f"{s}_b{b}"] = d

    # -- the matched comparison ---------------------------------------------
    # our band k is their band 6-k in the same half-suit, so "both sides holding
    # k" is ours at band k against theirs at band 6-k. This is the same matching
    # scripts4/contested_race.py uses for its asks-per-ply table.
    print("=" * 78)
    print(f"  ACCESS DEPLETION in the contested bands, {a.games} games")
    print("  our band k is their band 6-k, so a row compares both sides at the")
    print("  SAME holding. seats@deal is a DEAL property and must come out")
    print("  symmetric -- it is the instrument's symmetry check, not a finding.")
    print("  asks/live is the denominator contested_race used; asks/access")
    print("  divides out the plies on which the ask was not available at all.")
    print("=" * 78)
    hdr = (f"  {'holding':>7}  {'side':>6}  {'seats@deal':>10}  "
           f"{'access':>7}  {'asks/live':>9}  {'asks/access':>11}  "
           f"{'hit':>6}  {'death/take':>10}  {'P(win)':>7}")
    for k in (2, 3, 4):
        ob, tb = k, 6 - k
        if ob not in BANDS or tb not in BANDS:
            continue
        o = out["by_side_band"][f"ours_b{ob}"]
        t = out["by_side_band"][f"theirs_b{tb}"]
        out["matched"][f"holding_{k}"] = {
            "ours_band": ob, "theirs_band": tb,
            "seats_at_deal": [o["seats_at_deal"], t["seats_at_deal"]],
            "access_rate": [o["access_rate"], t["access_rate"]],
            "asks_per_live_ply": [o["asks_per_live_ply"],
                                  t["asks_per_live_ply"]],
            "asks_per_access_ply": [o["asks_per_access_ply"],
                                    t["asks_per_access_ply"]],
            "hit_rate": [o["hit_rate"], t["hit_rate"]],
            "death_per_card_taken": [o["death_per_card_taken"],
                                     t["death_per_card_taken"]],
            "lockout_rate": [o["lockout_rate"], t["lockout_rate"]],
            "win_rate": [o["win_rate"], t["win_rate"]],
            "win_rate_given_retained": [o["win_rate_given_retained"],
                                        t["win_rate_given_retained"]],
        }
        print()
        print(hdr)
        for label, d in (("ours", o), ("theirs", t)):
            def f(x, w=7, p=4):
                return f"{x:>{w}.{p}f}" if x is not None else " " * w
            print(f"  {k:>7}  {label:>6}  {f(d['seats_at_deal'],10,4)}  "
                  f"{f(d['access_rate'])}  {f(d['asks_per_live_ply'],9,5)}  "
                  f"{f(d['asks_per_access_ply'],11,5)}  {f(d['hit_rate'],6)}  "
                  f"{f(d['death_per_card_taken'],10)}  {f(d['win_rate'])}")
    print()
    print("  THE NEAR-TAUTOLOGY, reported as one. Losing the last access seat")
    print("  means the opponents hold all six, and every half-suit is")
    print("  eventually declared by whoever assembles it, so the lockout rate")
    print("  is the loss rate restated. Its only genuine residual is a team")
    print("  taking a half-suit it holds none of, when the opponents declare")
    print("  with the split wrong:")
    for k in (2, 3, 4):
        ob, tb = k, 6 - k
        o = out["by_side_band"][f"ours_b{ob}"]
        t = out["by_side_band"][f"theirs_b{tb}"]
        print(f"    holding {k}:  lockout {o['lockout_rate']:.4f} / "
              f"{t['lockout_rate']:.4f}   P(win) {o['win_rate']:.4f} / "
              f"{t['win_rate']:.4f}   won-after-lockout "
              f"{o['won_after_lockout']} / {t['won_after_lockout']}")
    print(f"  total won after lockout: {out['won_after_lockout']}")
    print()
    print("-" * 78)
    print("  SELF-TESTS -- every one of these must be 0")
    for key in ("selftest_ask_from_seat_without_access",
                "selftest_ask_at_teammate", "selftest_access_set_grew",
                "selftest_engine_accepted_an_unaskable_ask",
                "selftest_win_decomposition_identity",
                "selftest_band_out_of_range"):
        print(f"    {key:<46} {out[key]}")
    print("  The access-set-grew counter is the monotonicity claim under test,")
    print("  not an assumption: a seat can only gain a card of a half-suit by")
    print("  asking for one, which requires it to hold one already.")

    dest = Path(a.out) if a.out else default_path("access_depletion", SEED0)
    write(dest, out)
    print(f"\n  wrote {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
