"""Where the champion and the EXACT m=1 optimum disagree, and about what.

``scripts4/ii_endgame.py`` establishes that a single seat can gain by deviating
at m = 1, exactly and without sampling. A gain is a fact about the value; it
says nothing about what to change. This says what the optimum does differently,
in terms a knob could be built from.

WHY THIS IS DIFFERENT FROM EVERY EARLIER DIAGNOSTIC HERE
--------------------------------------------------------
``scripts4/value_objective_diag.py`` compared two hand-designed objectives to
each other, and ``fish4/bestresponse.py`` compared the champion to a rollout
responder whose own strategy fusion makes a loss uninterpretable. Both compare
a policy to another policy. This compares a policy to the OPTIMUM, computed by
backward induction over information sets, so a disagreement is an error rather
than a difference of opinion.

WHAT IT RECORDS AT EACH DISAGREEMENT
------------------------------------
* the kind of each action -- ask or claim -- because "claims too early" and
  "asks the wrong player" are different repairs
* how much the disagreement costs, from ``action_values``: the exact value of
  the champion's own move against the optimum's. A disagreement worth 0.0 is
  not an error at all, merely a tie the champion broke differently, and
  counting those as mistakes would inflate the rate.
* for ask-vs-ask, whether they differ in the TARGET, the CARD, or both
* the success probability of each, since a systematic gap there points at the
  posterior rather than at the objective

THIS COST IS NOT THE EXPLOITABILITY GAIN, AND THE TWO MUST NOT BE ADDED
-----------------------------------------------------------------------
``ii_endgame.py`` reports the gain from deviating for the WHOLE continuation --
the best response plays optimally at every decision it reaches, so its gain
compounds. This reports the cost of ONE root decision, with the champion
resuming immediately afterwards. The root cost is therefore smaller than the
continuation gain by construction, and quoting either as the other would be
wrong in a way that looks like arithmetic.

    py scripts4/ii_action_diff.py [n_games]
"""

from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, half_suit_of
from fish.engine import Ask, Claim, GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.exact_ii import (DEFAULT_DEADLINE, ExactII, SolveTimeout,
                            _champion_action, consistent_deals)
from fish4.registry4 import make_agent

SPEC = ("fishbot4", {"opponent_gamma": 0.35})
MAX_SUPPORT = 24


def kind(a) -> str:
    if isinstance(a, Ask):
        return "ask"
    if isinstance(a, Claim):
        return "claim"
    return "pass"


def main(n_games: int = 60) -> int:
    rules = RuleConfig()
    rows = []
    agree = 0
    timed_out = 0
    for g in range(n_games):
        agents = [make_agent(SPEC) for _ in range(NUM_PLAYERS)]
        st = GameState.deal(rules, seed=76_000_000 + g)
        ar = random.Random(76_500_000 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        for _ in range(600):
            if st.is_terminal:
                break
            p = st.turn
            obs = Observation.from_state(st, p)
            live = [h for h, w in enumerate(obs.set_winner) if w is None]
            if len(live) == 1:
                hs = live[0]
                agents[p].bel.update(obs)
                deals = consistent_deals(obs, agents[p].bel, hs)
                if len(deals) > 1 and len(deals) <= MAX_SUPPORT:
                    sv = ExactII(rules, hs, p, SPEC)
                    # A budget, because the fixed solver searches roughly two
                    # orders of magnitude more nodes than the one that wrote
                    # the first version of this result and an unbounded exact
                    # search does not fail loudly, it fails forever.
                    sv.deadline = time.monotonic() + DEFAULT_DEADLINE
                    states = []
                    for hands in deals:
                        t = GameState.from_components(
                            rules, list(hands), st.turn, list(st.set_winner))
                        t.history = list(st.history)
                        states.append(t)
                    w = [1.0 / len(states)] * len(states)
                    try:
                        best_v = sv.solve(states, w)
                    except SolveTimeout:
                        timed_out += 1
                        st.apply(p, agents[p].act(obs))
                        continue
                    except Exception:
                        st.apply(p, agents[p].act(obs))
                        continue
                    champ = _champion_action(SPEC, rules, p, states[0])
                    opt = sv.best_action
                    if champ is None or opt is None:
                        st.apply(p, agents[p].act(obs))
                        continue
                    cv = sv.action_values.get(repr(champ))
                    if repr(champ) == repr(opt):
                        agree += 1
                    else:
                        rec = {"support": len(deals),
                               "champ_kind": kind(champ),
                               "opt_kind": kind(opt),
                               "opt_value": best_v,
                               "champ_value": cv,
                               "cost": (best_v - cv) if cv is not None else None}
                        if isinstance(champ, Ask) and isinstance(opt, Ask):
                            rec["same_target"] = champ.target == opt.target
                            rec["same_card"] = champ.card == opt.card
                        rows.append(rec)
            st.apply(p, agents[p].act(obs))
        print(f"  {g+1}/{n_games} games, {agree} agree, {len(rows)} differ",
              flush=True)

    impossible = [r for r in rows
                  if r["cost"] is not None and r["cost"] < -1e-9]
    if impossible:
        # best_v is the MAXIMUM over the deviator's actions and the champion's
        # action is one of them, so a negative cost is arithmetically
        # impossible. It was not, for five m = 2 positions in ii_endgame.py,
        # because the memo merged nodes with different histories -- the max
        # read a stale value and came out below one of its own options. That
        # run printed a warning and wrote its results anyway; this one does
        # not.
        print(f"\n{len(impossible)} decisions where the champion's own move "
              f"scores ABOVE the maximum")
        for r in impossible[:5]:
            print(f"    support {r['support']}: optimum {r['opt_value']:+.4f} "
                  f"vs champion {r['champ_value']:+.4f}")
        print("That cannot happen. The search is wrong; nothing here is a "
              "result.")
        return 1

    n = len(rows)
    tot = agree + n
    print(f"\n{tot} hidden m=1 decisions solved exactly"
          f"  ({timed_out} timed out at {DEFAULT_DEADLINE:.0f}s)")
    if not tot:
        print("None reached. Nothing to report.")
        return 1
    print(f"  champion plays the exact optimum: {agree}/{tot} "
          f"= {agree/tot*100:.0f}%")

    priced = [r for r in rows if r["cost"] is not None]
    free = [r for r in priced if r["cost"] < 1e-9]
    costly = [r for r in priced if r["cost"] >= 1e-9]
    print(f"  of the {n} disagreements, {len(free)} cost exactly 0 -- ties "
          f"broken differently,\n  not errors -- and {len(costly)} cost "
          f"something")
    if costly:
        cs = sorted(r["cost"] for r in costly)
        print(f"  cost when it is an error: mean "
              f"{sum(cs)/len(cs):+.4f}, median {cs[len(cs)//2]:+.4f}, "
              f"max {cs[-1]:+.4f}")
        print(f"  per hidden m=1 decision overall: "
              f"{sum(cs)/tot:+.4f}")

    print("\n  what the disagreement IS:")
    kinds = {}
    for r in costly:
        k = f"champion {r['champ_kind']} -> optimum {r['opt_kind']}"
        kinds[k] = kinds.get(k, 0) + 1
    for k in sorted(kinds, key=lambda x: -kinds[x]):
        print(f"    {k:<34}{kinds[k]:>4}")
    aa = [r for r in costly if r["champ_kind"] == "ask" == r["opt_kind"]]
    if aa:
        st_ = sum(1 for r in aa if r.get("same_target"))
        sc = sum(1 for r in aa if r.get("same_card"))
        print(f"    of {len(aa)} ask-vs-ask: same target {st_}, "
              f"same card {sc}")

    out = ROOT / "results" / "ii_action_diff.json"
    out.write_text(json.dumps({
        "n_games": n_games, "n_decisions": tot, "n_agree": agree,
        "timed_out": timed_out, "deadline_seconds": DEFAULT_DEADLINE,
        "n_differ": n, "n_free_ties": len(free), "n_costly": len(costly),
        "mean_cost_when_error": (sum(r["cost"] for r in costly) / len(costly))
        if costly else None,
        "cost_per_decision": (sum(r["cost"] for r in costly) / tot)
        if costly else 0.0,
        "by_kind": kinds, "rows": rows}, indent=1))
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 60))
