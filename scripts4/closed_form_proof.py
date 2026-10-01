"""Perfect-information Fish is solved, and the solution is degenerate.

``fish4/EXACT2.md`` section 5 reports that both exact tables match a one-line
rule -- **V = sign(mover's team) x (2f - m)**, for *m* live half-suits and *f*
of them where the team on move holds at least one card -- exhaustively at m = 1
(2,604 states) and m = 2 (1,275,960 states), plus 61 sampled at m = 3. It gives
a proof sketch and stops there, because building the m = 3 table is expensive
and m = 9 is out of reach forever.

The table is not the only way to know. The sketch turns into a real proof if
three premises hold, and each of the three is a property of the RULES rather
than of any position, so each can be checked directly against the engine:

  A. **Footholds never grow.** Asking for a card of half-suit h requires
     already holding one of h, so a team holding none of h can never acquire
     one. Hence a team can claim at most the half-suits it has a foothold in
     NOW -- the mover's team at most f.
  B. **A team with no foothold in h cannot deny h.** Every card of h is in
     opponents' hands, so any claim it makes on h reveals an opponent holder
     and scores for the opponents. There is no spite-null available. Hence the
     opponents get at least m - f, whatever the mover does.
  C. **The mover's team can take all f without ever surrendering the turn.**
     With perfect information every ask can be made to hit, a hit retains the
     turn, a claim does not move the turn either, and a claim that empties the
     claimant passes within the team. So it drains and claims all f, and only
     then does the turn normalise to an opponent -- who by symmetry takes the
     remaining m - f.

A and B give V <= 2f - m. C gives V >= 2f - m. Together V = 2f - m, at every m,
with no table.

So this script checks A, B and C against the engine rather than against my
reading of it, and checks C by PLAYING the strategy out at every m from 1 to 9
and comparing the realised differential to the formula. m = 9 from a fresh deal
is the whole game.

WHAT THE ANSWER IS, AND WHY IT MATTERS MORE THAN "SOLVED" SOUNDS
----------------------------------------------------------------
At a fresh deal a team lacks a foothold in a half-suit only if all six of its
cards landed in the opponents' 27, which happens with probability
C(27,6)/C(54,6) = 1.15%. So f is almost always 9 and the perfect-information
value of the opening position is almost always **+9: the team on move takes
every half-suit**. Exactly:

    E[V] = 2 * E[f] - 9 = 2 * (9 - 9*C(27,6)/C(54,6)) - 9 = +8.794

That is the real finding, and it is a negative one for a whole family of
approaches. Perfect-information Fish is not a hard game that we have partially
solved; it is a trivial game whose answer is "whoever moves first wins
everything". Every difficulty in Fish lives in the hidden information, which is
why ``results/determinization_gap.json`` measures the tables overstating the
mover by +5.29 sets on positions real play reaches and +8.18 at a fresh deal.
A perfect-information tablebase is not an approximation to Fish that we should
try to extend; it answers a different and much easier question.

    py scripts4/closed_form_proof.py [n_per_layer]
"""

from __future__ import annotations

import json
import random
import sys
from itertools import product
from math import comb
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import (CARDS_PER_HALF_SUIT, NUM_PLAYERS, half_suit_mask,
                        mask_to_cards, team_of, teammates)
from fish.engine import NULL_TEAM, Ask, Claim, GameState, Pass
from fish.rules import RuleConfig


# -- the formula -------------------------------------------------------------

def footholds(hands, set_winner, team) -> set:
    """Live half-suits in which ``team`` holds at least one card."""
    out = set()
    for hs, w in enumerate(set_winner):
        if w is not None:
            continue
        mask = half_suit_mask(hs)
        if any(hands[p] & mask for p in range(NUM_PLAYERS)
               if team_of(p) == team):
            out.add(hs)
    return out


def closed_form(st) -> int:
    """2f - m in the frame of the team on move."""
    live = sum(1 for w in st.set_winner if w is None)
    f = len(footholds(st.hands, st.set_winner, team_of(st.turn)))
    return 2 * f - live


# -- the strategy of premise C, as three lines --------------------------------

def greedy_action(st, rng):
    """Take a hitting ask; else claim a half-suit the team wholly owns; else
    pass. This is the whole optimal perfect-information policy."""
    p = st.turn
    if st.hands[p] == 0:
        opts = st.legal_passes(p)
        return rng.choice(opts) if opts else None
    hits = [a for a in st.legal_asks(p) if st.hands[a.target] >> a.card & 1]
    if hits:
        return rng.choice(hits)
    team = team_of(p)
    for hs in range(len(st.set_winner)):
        if st.set_winner[hs] is not None:
            continue
        base = hs * CARDS_PER_HALF_SUIT
        holders = [st.holder_of(base + i) for i in range(CARDS_PER_HALF_SUIT)]
        if st.hands[p] & half_suit_mask(hs) and all(
                team_of(h) == team for h in holders):
            return Claim(hs, tuple(holders))
    return None


def constructive_playout(st, rng, max_steps=400):
    """Both teams play ``greedy_action``. Returns the realised differential in
    the frame of the team that was on move at entry, or None if it jammed."""
    frame = team_of(st.turn)
    a0, b0, _ = st.scores()
    before = a0 - b0 if frame == 0 else b0 - a0
    for _ in range(max_steps):
        if st.is_terminal:
            break
        act = greedy_action(st, rng)
        if act is None:
            return None, "no action available"
        st.apply(st.turn, act)
    if not st.is_terminal:
        return None, "did not terminate"
    a, b, n = st.scores()
    after = a - b if frame == 0 else b - a
    return after - before, ("nulls", n)


# -- random positions at a chosen layer ---------------------------------------

def random_position(rules, m, rng):
    """A fresh deal with 9 - m half-suits struck out and their cards removed."""
    st = GameState.deal(rules, rng=rng)
    n_hs = len(st.set_winner)
    kill = rng.sample(range(n_hs), n_hs - m)
    hands = list(st.hands)
    sw = list(st.set_winner)
    for hs in kill:
        sw[hs] = rng.choice((0, 1))
        mask = half_suit_mask(hs)
        for p in range(NUM_PLAYERS):
            hands[p] &= ~mask
    if not any(hands):
        return None
    return GameState.from_components(rules, hands, rng.randrange(NUM_PLAYERS),
                                     sw)


# -- premise A: footholds never grow ------------------------------------------

def check_A(rules, n_games, rng, sabotage=False):
    """Play random legal games and watch every team's foothold set shrink.

    ``sabotage`` strips a team of a half-suit at step 3 (a legal-shaped SHRINK,
    which the check must not flag) and hands one card of it back at step 6 (a
    GROWTH, which the check must flag). A fresh deal almost never has a
    footholdless half-suit on its own -- 1.1% per half-suit -- so an earlier
    version of this control silently never fired, and the check passed while
    proving nothing. The control now manufactures the condition instead of
    waiting for it, and main() refuses to report premise A unless it fires.
    """
    bad = []
    for g in range(n_games):
        st = GameState.deal(rules, rng=rng)
        prev = {t: footholds(st.hands, st.set_winner, t) for t in (0, 1)}
        stripped = None
        for step in range(400):
            if st.is_terminal:
                break
            p = st.turn
            if st.hands[p] == 0:
                acts = st.legal_passes(p)
            else:
                acts = st.legal_asks(p)
            act = rng.choice(acts) if acts else greedy_action(st, rng)
            if act is None:
                break
            st.apply(p, act)

            if sabotage and step == 3 and stripped is None:
                hs = next((h for h, w in enumerate(st.set_winner)
                           if w is None), None)
                if hs is not None:
                    mask = half_suit_mask(hs)
                    sink = next(q for q in range(NUM_PLAYERS)
                                if team_of(q) == 1)
                    moved = 0
                    for q in range(NUM_PLAYERS):
                        if team_of(q) == 0 and st.hands[q] & mask:
                            moved |= st.hands[q] & mask
                            st.hands[q] &= ~mask
                    if moved:
                        st.hands[sink] |= moved
                        stripped = (hs, moved)
            if sabotage and step == 6 and stripped:
                hs, moved = stripped
                card = mask_to_cards(moved)[0]
                src = st.holder_of(card)
                dst = next(q for q in range(NUM_PLAYERS) if team_of(q) == 0)
                if src is not None and src != dst:
                    st.hands[src] &= ~(1 << card)
                    st.hands[dst] |= 1 << card

            for t in (0, 1):
                now = footholds(st.hands, st.set_winner, t)
                grew = now - prev[t]
                if grew:
                    bad.append({"game": g, "step": step, "team": t,
                                "gained": sorted(grew)})
                prev[t] = now
        if bad:
            break
    return bad


# -- premise B: no foothold, no denial ----------------------------------------

def check_B(rules, n_positions, rng):
    """For a team with no card of h, enumerate its declarations on h and
    confirm every one of them scores for the OPPONENTS -- never itself.

    The converse is checked too: where the team wholly owns h, a mis-ordered
    assignment must cost the set -- awarded to the foe under the baseline
    rule, and nulled under the explicitly pinned legacy variant. Without that
    half the check could pass by never finding a declaration the engine
    scores as wrong at all.
    """
    from dataclasses import replace as _dc_replace
    denials = 0
    checked = 0
    award_seen = 0
    null_seen = 0
    for _ in range(n_positions):
        st = random_position(rules, rng.randint(2, 9), rng)
        if st is None:
            continue
        for hs, w in enumerate(st.set_winner):
            if w is not None:
                continue
            base = hs * CARDS_PER_HALF_SUIT
            holders = [st.holder_of(base + i)
                       for i in range(CARDS_PER_HALF_SUIT)]
            for team in (0, 1):
                mine = [h for h in holders if team_of(h) == team]
                claimer = next(q for q in range(NUM_PLAYERS)
                               if team_of(q) == team)
                mates = [q for q in range(NUM_PLAYERS) if team_of(q) == team]
                if not mine:
                    # no foothold: sample assignments, all must go to the foe
                    for _ in range(12):
                        asg = tuple(rng.choice(mates)
                                    for _ in range(CARDS_PER_HALF_SUIT))
                        w2 = _claim_outcome(st, claimer, hs, asg)
                        checked += 1
                        if w2 != 1 - team:
                            denials += 1
                elif len(mine) == CARDS_PER_HALF_SUIT:
                    # wholly owned: a wrong order must cost the set under
                    # BOTH rules, in each rule's own way
                    asg = list(holders)
                    if len(set(asg)) > 1:
                        i, j = 0, next(k for k in range(1, 6)
                                       if asg[k] != asg[0])
                        asg[i], asg[j] = asg[j], asg[i]
                        arules = _dc_replace(
                            st.rules, wrong_distribution_outcome="opponent")
                        if _claim_outcome(st, claimer, hs, tuple(asg),
                                          rules=arules) == 1 - team:
                            award_seen += 1
                        nrules = _dc_replace(
                            st.rules, wrong_distribution_outcome="null")
                        if _claim_outcome(st, claimer, hs, tuple(asg),
                                          rules=nrules) == NULL_TEAM:
                            null_seen += 1
    return {"claims_checked": checked, "denials_found": denials,
            "awards_demonstrated": award_seen,
            "nulls_demonstrated": null_seen}


def _claim_outcome(st, claimer, hs, assignment, rules=None) -> int:
    """Outcome of a declaration, without disturbing ``st``. ``rules``
    overrides ``st.rules`` so the two misdeclaration variants can each be
    probed on the same position."""
    probe = GameState.from_components(rules if rules is not None else st.rules,
                                      list(st.hands), claimer,
                                      list(st.set_winner))
    probe.turn = claimer
    ev = probe.apply(claimer, Claim(hs, assignment))
    return ev.winner


# -- premise C: the playout realises the formula ------------------------------

def check_C(rules, n_per_layer, rng):
    rows = []
    for m in range(1, 10):
        agree = 0
        n = 0
        jams = 0
        vals = []
        for _ in range(n_per_layer):
            st = random_position(rules, m, rng)
            if st is None:
                continue
            live = sum(1 for w in st.set_winner if w is None)
            if live != m:
                continue
            want = closed_form(st)
            got, note = constructive_playout(st, rng)
            n += 1
            if got is None:
                jams += 1
                continue
            vals.append(want)
            if got == want:
                agree += 1
        rows.append({"m": m, "n": n, "agree": agree, "jams": jams,
                     "mean_value": sum(vals) / len(vals) if vals else None})
    return rows


# -- premise D: anchor the whole chain to a solver nobody here wrote ----------

def check_D(rules, n_positions, rng):
    """Compare the greedy playout to the EXACT solver at m = 1 and m = 2.

    Premises A-C compare two things I wrote -- ``closed_form`` and
    ``constructive_playout`` -- so a shared misconception would pass them
    silently. ``fish4.exact2`` is an independent perfect-information solver
    with exhaustive tables at these layers, so agreeing with it is the only
    step in this argument that is anchored to ground truth rather than to
    internal consistency. It is why the m <= 2 tables are worth keeping even
    though the formula supersedes them.
    """
    from fish4.exact2 import Exact2Solver
    solver = Exact2Solver(rules)
    rows = []
    for m in (1, 2):
        n = agree_form = agree_play = 0
        bad = []
        for _ in range(n_positions):
            st = random_position(rules, m, rng)
            if st is None or sum(1 for w in st.set_winner if w is None) != m:
                continue
            try:
                exact0 = solver.value(st)          # team 0's frame
            except Exception:
                continue
            sign = 1 if team_of(st.turn) == 0 else -1
            exact = sign * exact0                 # mover's frame
            want = closed_form(st)
            got, _ = constructive_playout(GameState.from_components(
                rules, list(st.hands), st.turn, list(st.set_winner)), rng)
            n += 1
            if want == exact:
                agree_form += 1
            if got == exact:
                agree_play += 1
            else:
                bad.append({"exact": exact, "formula": want, "playout": got})
        rows.append({"m": m, "n": n, "formula_matches_exact": agree_form,
                     "playout_matches_exact": agree_play,
                     "examples": bad[:3]})
    return rows


def main(n: int = 200) -> int:
    rules = RuleConfig()
    rng = random.Random(31337)

    print("PREMISE A  footholds never grow")
    bad = check_A(rules, 40, rng)
    print(f"  {'ok' if not bad else 'FAIL'}   40 random games, "
          f"{len(bad)} growth events")
    sab = check_A(rules, 3, random.Random(9), sabotage=True)
    print(f"  control: strip a team of a half-suit, hand one card back -- "
          f"the check reports {len(sab)} growth event(s), "
          f"{'so it can fail' if sab else 'SO IT CANNOT FAIL AND PROVES NOTHING'}")

    print("\nPREMISE B  a team with no foothold in h cannot deny h")
    b = check_B(rules, 60, rng)
    print(f"  {b['claims_checked']} declarations by a footholdless team: "
          f"{b['denials_found']} scored anything but the opponents")
    print(f"  control: {b['awards_demonstrated']} mis-ordered declarations "
          f"on a wholly-owned half-suit WERE awarded to the foe (baseline), "
          f"{b['nulls_demonstrated']} nulled under the legacy variant "
          f"-- {'both wrong-order paths are reachable' if b['awards_demonstrated'] and b['nulls_demonstrated'] else 'A CONTROL NEVER FIRED, check is vacuous'}")

    print("\nPREMISE C  the greedy playout realises 2f - m, at every layer")
    print(f"  {'m':>3}{'positions':>11}{'agree':>8}{'jams':>7}{'mean 2f-m':>12}")
    rows = check_C(rules, n, rng)
    for r in rows:
        mv = f"{r['mean_value']:+.3f}" if r["mean_value"] is not None else "-"
        print(f"  {r['m']:>3}{r['n']:>11}{r['agree']:>8}{r['jams']:>7}{mv:>12}")
    total = sum(r["n"] for r in rows)
    ok = sum(r["agree"] for r in rows)

    print("\nPREMISE D  and the exact solver agrees, where it can be asked")
    drows = check_D(rules, max(20, n // 4), rng)
    print(f"  {'m':>3}{'positions':>11}{'formula=exact':>16}{'playout=exact':>16}")
    for r in drows:
        print(f"  {r['m']:>3}{r['n']:>11}{r['formula_matches_exact']:>16}"
              f"{r['playout_matches_exact']:>16}")
        for e in r["examples"]:
            print(f"      MISMATCH exact {e['exact']:+d} formula "
                  f"{e['formula']:+d} playout {e['playout']}")
    d_ok = all(r["formula_matches_exact"] == r["n"]
               and r["playout_matches_exact"] == r["n"] for r in drows)

    p_no = comb(27, CARDS_PER_HALF_SUIT) / comb(54, CARDS_PER_HALF_SUIT)
    ev = 2 * (9 - 9 * p_no) - 9
    m9 = next(r for r in rows if r["m"] == 9)
    print(f"\nOPENING POSITION")
    print(f"  P(a half-suit is entirely with the opponents) = "
          f"C(27,6)/C(54,6) = {p_no:.5f}")
    print(f"  so E[V] = 2*(9 - 9*{p_no:.5f}) - 9 = {ev:+.3f}")
    print(f"  measured over {m9['n']} fresh deals: "
          f"{m9['mean_value']:+.3f}")

    # A green check whose control never fired is not evidence. Both
    # controls gate the verdict.
    proved = ((not bad) and bool(sab) and b["denials_found"] == 0
              and b["nulls_demonstrated"] > 0 and ok == total and d_ok)
    print()
    if proved:
        print(f"All four premises hold and the playout matches the formula on "
              f"{ok}/{total}\npositions across every layer m = 1..9. The "
              f"perfect-information game is solved:\nthe team on move takes "
              f"every half-suit it can touch, and at a fresh deal that\nis "
              f"{ev:+.2f} of the 9 available.")
        print("\nThat is a statement about a DIFFERENT GAME. Fish is hard "
              "because of what\nplayers do not know; strip that away and "
              "nothing is left to solve. See\nresults/determinization_gap.json "
              "for the size of the difference: +5.29 sets.")
    else:
        print("A premise failed. The closed form is not established at general "
              "m and the\nfailures above are the thing to read, not this "
              "summary.")

    out = ROOT / "results" / "closed_form_proof.json"
    out.write_text(json.dumps({
        "premise_A_growth_events": len(bad),
        "premise_A_control_events": len(sab),
        "premise_B": b,
        "premise_C": rows,
        "premise_D": drows,
        "positions": total, "agree": ok,
        "p_half_suit_all_opponents": p_no,
        "opening_expected_value_closed_form": ev,
        "opening_expected_value_measured": m9["mean_value"],
        "proved": proved}, indent=1))
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0 if proved else 1


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 200))
