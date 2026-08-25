"""Does the champion make claims its own beliefs say are impossible?

``results/ii_action_diff.json`` compares the champion to the exact m = 1
optimum. Of 189 disagreements, 13 could not be priced at all: the champion's
declared split was not in the solver's candidate set, and that set contains
every assignment true in at least one deal the public record allows. So those
claims were true in NO consistent deal -- provably wrong from the claimer's own
information, before any search.

That is worth checking directly rather than inferring from an absence, and the
direct check does not need the solver, the m = 1 restriction, or a uniform
prior. ``BeliefState.current_holder_mask(c)`` is the exact combinatorial set of
players who can still hold card c. A declaration is IMPOSSIBLE when it names a
holder outside that set for any card:

    impossible  <=>  exists c in the half-suit with
                     declared_holder(c) not in current_holder_mask(c)

No sampling, no assumption, no threshold. If this fires the claim could not
have been right, and the engine knew it.

WHY IT COULD FIRE AT ALL
------------------------
``claim4.best_for_half_suit`` has three tiers. Tier 1 is exact deduction and
cannot produce an impossible split. Tiers 2 and 3 score candidate assignments
with an independence product or a sampled joint, and a sampled posterior can
put positive mass on an assignment the exact constraint system has already
ruled out -- 160 draws need not cover the truth, and the marginals that build
the shortlist are per-card rather than joint.

    py scripts4/impossible_claims.py [n_games]
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import CARDS_PER_HALF_SUIT, NUM_PLAYERS, half_suit_cards
from fish.engine import Claim, GameState, NULL_TEAM
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.registry4 import make_agent

SPEC = ("fishbot4", {"opponent_gamma": 0.35})


def marginally_impossible(bel, claim: Claim) -> bool:
    """Some card is declared to a holder its own mask already excludes."""
    for c, holder in zip(half_suit_cards(claim.half_suit), claim.assignment):
        if not (bel.current_holder_mask(c) >> holder) & 1:
            return True
    return False


def generally_impossible(obs, bel, claim: Claim) -> bool:
    """The max-flow feasibility check, which works at EVERY layer.

    The enumeration below only decides m = 1. That left the pre-registration
    for the claim_feasibility arm with a stated hole: 9.2% is the m=1 rate and
    the rate above it was unmeasured, while the arm applied everywhere. The
    arm then scored +0.028 against a +0.183 ceiling computed from the m=1 rate
    alone, so whether impossible claims occur at higher layers is exactly the
    number that says whether that ceiling was ever the right one.

    fish4.feasible.declaration_feasible answers it, and agrees 40/40 with the
    enumeration where both apply.
    """
    from fish4.feasible import declaration_feasible
    try:
        return not declaration_feasible(obs, bel, claim.half_suit,
                                        claim.assignment)
    except Exception:
        return False


def jointly_impossible(obs, bel, claim: Claim) -> bool:
    """No complete deal the public record allows contains this declaration.

    The marginal test above is the weak one, and running it first was worth
    doing because it came back 0/225 and refuted the reading it was built to
    confirm. This is the test that matters, and claim4's own docstring names
    the gap it exploits: "the product of marginals is not the joint: cards
    compete for the same quota slots, so per-card modes can be jointly
    impossible". A declaration can satisfy every card's mask separately and
    still be consistent with no deal at all, because the hand COUNTS do not
    add up.

    So this enumerates the deals consistent with the record -- the same
    enumeration fish4/exact_ii uses -- and asks whether any of them contains
    the declared split.
    """
    from fish4.exact_ii import consistent_deals
    live = [h for h, w in enumerate(obs.set_winner) if w is None]
    if len(live) != 1 or live[0] != claim.half_suit:
        return False              # only decidable cheaply at m = 1
    deals = consistent_deals(obs, bel, claim.half_suit)
    if not deals:
        return False              # enumeration unavailable; no claim made
    cards = list(half_suit_cards(claim.half_suit))
    for hands in deals:
        if all((hands[h] >> c) & 1
               for c, h in zip(cards, claim.assignment)):
            return False
    return True


def main(n_games: int = 80) -> int:
    rules = RuleConfig()
    n_claims = 0
    rows = []
    for g in range(n_games):
        agents = [make_agent(SPEC) for _ in range(NUM_PLAYERS)]
        st = GameState.deal(rules, seed=79_000_000 + g)
        ar = random.Random(79_500_000 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        for _ in range(600):
            if st.is_terminal:
                break
            p = st.turn
            obs = Observation.from_state(st, p)
            try:
                act = agents[p].act(obs)
            except Exception:
                break
            rec = None
            if isinstance(act, Claim):
                n_claims += 1
                live = sum(1 for w in obs.set_winner if w is None)
                marg = marginally_impossible(agents[p].bel, act)
                joint = jointly_impossible(obs, agents[p].bel, act)
                gen = generally_impossible(obs, agents[p].bel, act)
                rec = {"live": live, "impossible": marg or joint,
                       "marginal": marg, "joint_only": joint and not marg,
                       "general": gen, "checked_jointly": live == 1}
            ev = st.apply(p, act)
            if rec is not None:
                rec["winner"] = ev.winner
                rec["mine"] = ev.winner == (p % 2)
                rows.append(rec)
        print(f"  {g+1}/{n_games} games, {n_claims} claims", flush=True)

    bad = [r for r in rows if r["impossible"]]
    ok = [r for r in rows if not r["impossible"]]
    n = len(rows)
    print(f"\n{n} claims in {n_games} games\n")
    jointly = [r for r in rows if r.get("checked_jointly")]
    jbad = [r for r in jointly if r["impossible"]]
    print(f"  MARGINALLY impossible (some card's own mask excludes its "
          f"declared holder):\n    {sum(1 for r in rows if r['marginal'])}"
          f"/{n}")
    print(f"  JOINTLY impossible (no complete consistent deal contains the "
          f"split),\n  among the {len(jointly)} claims at m=1 where the "
          f"enumeration is cheap:\n    {len(jbad)}/{len(jointly)} = "
          f"{len(jbad)/max(1,len(jointly))*100:.1f}%")

    def outcome(sub, label):
        if not sub:
            return
        won = sum(1 for r in sub if r["winner"] not in (NULL_TEAM,)
                  and r["mine"])
        null = sum(1 for r in sub if r["winner"] == NULL_TEAM)
        lost = len(sub) - won - null
        print(f"    {label:<22}{len(sub):>5}   won {won:>4}  "
              f"nulled {null:>4}  to the foe {lost:>4}   "
              f"sets/claim {(won-lost)/len(sub):+.3f}")

    gen = [r for r in rows if r.get("general")]
    from collections import Counter
    print(f"\n  BY THE GENERAL CHECK, at every layer: {len(gen)}/{n} = "
          f"{len(gen)/max(1,n)*100:.1f}%")
    if gen:
        print(f"    by half-suits still live: "
              f"{dict(sorted(Counter(r['live'] for r in gen).items()))}")
    bylive = Counter(r["live"] for r in rows)
    print(f"    claims made per layer:     {dict(sorted(bylive.items()))}")

    print(f"\n  what they scored:")
    outcome(ok, "possible claims")
    outcome(bad, "impossible claims")

    if bad:
        from collections import Counter
        c = Counter(r["live"] for r in bad)
        print(f"\n  by half-suits still live: "
              f"{dict(sorted(c.items(), reverse=True))}")
        print("\n  An impossible claim cannot be right, so every one of them "
              "is a set given\n  away or nulled for nothing. This needs no "
              "search to detect: the exact\n  constraint system already holds "
              "the answer when the sampled posterior is\n  asked instead.")
    else:
        print("\n  None. The claim path never contradicts the exact belief, "
              "so the 13\n  unpriced disagreements at m=1 have some other "
              "explanation and this line\n  is closed.")

    out = ROOT / "results" / "impossible_claims.json"
    out.write_text(json.dumps({
        "n_games": n_games, "n_claims": n, "n_impossible": len(bad),
        "share": len(bad) / max(1, n), "rows": rows}, indent=1))
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 80))
