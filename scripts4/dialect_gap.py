"""Why do we lose on HIS host when we win on ours? Measure the dialect gap.

A user watching our bot imported into dylann4500's local server reported the
opposite of every number this project has measured: our bot losing, not
winning. The engines are the same ones; the arbiter is not, and his differs
in a rule we do not implement on our side of the bridge.

His `Rules` defaults (engine/src/fish.hpp:108-109) are
``outOfTurnDeclare = true`` and ``cardlessMayDeclare = true``: any seat may
declare a half-suit the moment it knows it, on anyone's turn, holding cards
or not. Ours declares only on its own turn -- and the integration package
we shipped him says, in as many words, not to poll us off-turn. So in his
arbiter his three seats race to declare and our three wait their turn.
Whoever declares first takes the set; our card-reading advantage cannot
pay if we are structurally last to speak.

Three arms, identical deals and rotations:

  own-turn    both sides declare on their own turn only (our dialect --
              this is the +2.5 sets/game we have been reporting)
  both-any    both sides may declare off-turn (his dialect, played fairly)
  us-handicap only THEIR side declares off-turn -- what his host actually
              runs today, given our integration answers only when polled

If the handicap arm is the loss the user saw, the fix is an integration
one, not a strength one.

    py scripts4/dialect_gap.py [n_deals]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fish.cards import NUM_PLAYERS, team_of
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.match import _deduced_claim
from fish4.registry4 import V06_DEPLOYED, make_agent

SEED0 = 560_000
AGENT0 = 5600
JOURNAL = ROOT / "results" / "dialect_gap_journal.jsonl"
ARMS = ("own-turn", "both-any", "us-handicap")


def play(deal_seed: int, kv_even: bool, arm: str) -> dict:
    """One game. ``arm`` decides who may declare off-turn."""
    rules = RuleConfig(
        wrong_distribution_outcome="opponent",
        claims_any_time=(arm != "own-turn"))
    agents = []
    for p in range(6):
        kv = (p % 2 == 0) == kv_even
        agents.append(make_agent(V06_DEPLOYED) if kv
                      else make_agent(("dylan_v07", {})))
    st = GameState.deal(rules, seed=deal_seed)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, AGENT0 + deal_seed * 13 + p)
    kv_team = 0 if kv_even else 1

    def may_declare_offturn(seat: int) -> bool:
        if arm == "own-turn":
            return False
        if arm == "both-any":
            return True
        return team_of(seat) != kv_team      # us-handicap: only their side

    # Off-turn declaration is a property of the RULES, not of either engine's
    # internals, so both sides get the same deducer: an independent belief
    # per seat, fed only public events. Using each agent's own belief would
    # be unfair here -- the bridged v0.7 does not expose one, and giving our
    # side its posterior while his side got nothing would measure the
    # engines rather than the rule. This deduces only what is CERTAIN from
    # the public record, which is the weakest possible version of the
    # capability and therefore a lower bound on what his engine gets.
    from fish.beliefs import BeliefState

    class _Deducer:
        def __init__(self, seat):
            self.bel = BeliefState(rules, observer=seat)

    shadow = [_Deducer(p) for p in range(NUM_PLAYERS)]
    offturn = {"kv": 0, "dy": 0}
    for _ in range(700):
        if st.is_terminal:
            break
        # Off-turn declarations resolve before the turn-holder moves, which
        # is what "at any moment" means: a seat that already knows the set
        # does not wait for anyone.
        fired = True
        while fired and not st.is_terminal:
            fired = False
            for q in range(NUM_PLAYERS):
                if st.is_terminal or q == st.turn:
                    continue
                if not may_declare_offturn(q):
                    continue
                obs_q = Observation.from_state(st, q)
                shadow[q].bel.update(obs_q)
                claim = _deduced_claim(shadow[q], q, obs_q)
                if claim is None:
                    continue
                try:
                    st.apply(q, claim)
                except Exception:
                    continue
                offturn["kv" if team_of(q) == kv_team else "dy"] += 1
                fired = True
        if st.is_terminal:
            break
        st.apply(st.turn,
                 agents[st.turn].act(Observation.from_state(st, st.turn)))

    kv = sum(1 for w in st.set_winner if w == kv_team)
    dy = sum(1 for w in st.set_winner if w == 1 - kv_team)
    return {"deal": deal_seed, "kv_even": kv_even, "arm": arm,
            "kv": kv, "dylan": dy, "margin": kv - dy,
            "offturn_kv": offturn["kv"], "offturn_dylan": offturn["dy"],
            "terminal": st.is_terminal,
            "fallbacks": sum(getattr(a, "fallbacks", 0) for a in agents)}


def main(n_deals: int = 120) -> int:
    done, rows = set(), []
    if JOURNAL.exists():
        for line in JOURNAL.read_text().splitlines():
            if line.strip():
                r = json.loads(line)
                done.add((r["deal"], r["kv_even"], r["arm"]))
                rows.append(r)
    print(f"{len(done)} games already journalled", flush=True)
    for i in range(n_deals):
        seed = SEED0 + i
        for kv_even in (True, False):
            for arm in ARMS:
                if (seed, kv_even, arm) in done:
                    continue
                t0 = time.time()
                r = play(seed, kv_even, arm)
                r["seconds"] = round(time.time() - t0, 1)
                rows.append(r)
                with JOURNAL.open("a") as fh:
                    fh.write(json.dumps(r) + "\n")
        if (i + 1) % 10 == 0:
            print(f"  deal {i + 1}/{n_deals}", flush=True)

    by = {(r["deal"], r["kv_even"], r["arm"]): r for r in rows}
    out = {"arms": {}}
    print("\n=== the dialect gap: v0.6 vs v0.7, same deals, three arbiters ===")
    for arm in ARMS:
        g = [r for r in by.values() if r["arm"] == arm]
        if len(g) < 20:
            print(f"  {arm:12s} {len(g)} games, too few")
            continue
        m = [x["margin"] for x in g]
        n = len(m)
        mean = sum(m) / n
        var = sum((x - mean) ** 2 for x in m) / (n - 1)
        se = (var / n) ** 0.5
        wins = sum(1 for x in m if x > 0)
        ok = sum(x["offturn_kv"] for x in g)
        od = sum(x["offturn_dylan"] for x in g)
        print(f"  {arm:12s} {mean:+.3f} sets/game "
              f"[{mean-1.96*se:+.3f}, {mean+1.96*se:+.3f}]  "
              f"{100*wins/n:.0f}% games won  "
              f"(off-turn declares: ours {ok}, theirs {od})")
        out["arms"][arm] = {"n_games": n, "margin": mean,
                            "ci95": [mean - 1.96 * se, mean + 1.96 * se],
                            "win_rate": wins / n,
                            "offturn_kv": ok, "offturn_dylan": od}
    (ROOT / "results" / "dialect_gap.json").write_text(json.dumps(out, indent=1))
    print("wrote results/dialect_gap.json")
    return 0


if __name__ == "__main__":
    a = sys.argv[1:]
    raise SystemExit(main(int(a[0]) if a else 120))
