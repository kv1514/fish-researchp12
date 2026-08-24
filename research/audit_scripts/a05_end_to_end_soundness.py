"""A05: end-to-end belief SOUNDNESS on real game prefixes.

For a seat's live BeliefState we build alternative INITIAL DEALS by permuting
the true initial owners of a random subset S of cards (S never touches the
observer's own initial hand, so the observer's private knowledge still holds).
Counts are preserved by construction. Each alternative is then checked with
``validate_deal_against_history`` -- the module's own INDEPENDENT gold-standard
replay validator. Any alternative that validates is a genuinely possible world
from the observer's viewpoint, so the belief state MUST admit it:

  * candidates[c] must contain deal[c] for every card, and
  * every stored OR constraint must be satisfied by it.

A validating deal that the belief state rejects is a SOUNDNESS bug.
"""
import sys, random, itertools
sys.path.insert(0, r"C:\Users\vel_k\Documents\fish-engine")
from fish.rules import RuleConfig
from fish.engine import GameState
from fish.observation import Observation
from fish.beliefs import BeliefState, validate_deal_against_history
from fish.agents import AGENT_REGISTRY

SUBSET = 8
PERMS_CAP = 40000


def deal_to_hands(deal, n):
    hands = [0] * 6
    for c in range(n):
        hands[deal[c]] |= 1 << c
    return hands


def check_prefix(rules, state, seat, bel, true_initial_deal, rng, n):
    hist = tuple(state.history)
    obs = Observation.from_state(state, seat)
    ownset = (set() if bel.observer is None
              else {c for c in range(n) if true_initial_deal[c] == seat})
    pool = [c for c in range(n) if c not in ownset]
    S = rng.sample(pool, min(SUBSET, len(pool)))
    owners = [true_initial_deal[c] for c in S]
    seen = set()
    checked = valid = 0
    bugs = []
    for perm in itertools.permutations(owners):
        if perm in seen:
            continue
        seen.add(perm)
        if len(seen) > PERMS_CAP:
            break
        deal = list(true_initial_deal)
        for c, o in zip(S, perm):
            deal[c] = o
        checked += 1
        if not validate_deal_against_history(rules, deal_to_hands(deal, n),
                                             hist):
            continue
        valid += 1
        # belief must admit it
        for c in range(n):
            if not bel.candidates[c] & (1 << deal[c]):
                bugs.append(("CANDIDATE EXCLUDES A VALID WORLD", c, deal[c],
                             f"{bel.candidates[c]:06b}", S, perm))
                break
        else:
            for grp, p in bel.ors:
                if not any(deal[c] == p for c in grp):
                    bugs.append(("OR CONSTRAINT REJECTS A VALID WORLD",
                                 grp, p, S, perm))
                    break
    return checked, valid, bugs


def main(n_games=25, agent="memory", plies=(6, 14, 25, 40, 60), seed0=0,
         rule_kwargs=None, spectator=False):
    from fish.cards import deck_size
    rules = RuleConfig(**(rule_kwargs or {}))
    n = deck_size(rules.variant)
    tot_checked = tot_valid = 0
    all_bugs = []
    for g in range(n_games):
        rng = random.Random(9000 + g)
        state = GameState.deal(rules, seed=seed0 + g)
        true_initial = [None] * n
        for p in range(6):
            h = state.hands[p]
            for c in range(n):
                if h & (1 << c):
                    true_initial[c] = p
        agents = [AGENT_REGISTRY[agent]() for _ in range(6)]
        ar = random.Random(seed0 + g)
        for p, a in enumerate(agents):
            a.begin_game(p, rules, ar.getrandbits(64))
        bels = [BeliefState(rules, observer=(None if spectator else p))
                for p in range(6)]
        ply = 0
        while not state.is_terminal and ply <= max(plies):
            for p in range(6):
                bels[p].update(Observation.from_state(state, p))
            if ply in plies:
                for seat in range(6):
                    c, v, b = check_prefix(rules, state, seat, bels[seat],
                                           true_initial, rng, n)
                    tot_checked += c
                    tot_valid += v
                    all_bugs += [(g, ply, seat) + x for x in b]
            p = state.turn
            state.apply(p, agents[p].act(Observation.from_state(state, p)))
            ply += 1
    print(f"agent={agent} rules={rule_kwargs} spectator={spectator}: "
          f"alternative deals tried {tot_checked}, "
          f"history-consistent {tot_valid}, SOUNDNESS VIOLATIONS {len(all_bugs)}")
    for b in all_bugs[:8]:
        print("   ", b)
    return all_bugs


if __name__ == "__main__":
    import json
    ng = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    ag = sys.argv[2] if len(sys.argv) > 2 else "memory"
    rk = json.loads(sys.argv[3]) if len(sys.argv) > 3 else None
    sp = (len(sys.argv) > 4 and sys.argv[4] == "spectator")
    main(n_games=ng, agent=ag, rule_kwargs=rk, spectator=sp)
