"""A06: exact-solver probes (fast version; each 1-half-suit layer costs
3-20 s to solve, so the sample sizes are deliberately small).

(1) ExactSolver._layer_done cache poisoning -> KeyError on solver reuse.
(2) Does the value-iteration fixpoint depend on the sweep ORDER?
(3) Is pruning claims to TRUE claims only safe (within the tractable budget)?
(4) optimal_actions / ties.
(5) Is the "unbroken cycle scores 0" branch reachable at all?
"""
import sys
import random
import traceback

sys.path.insert(0, r"C:\Users\vel_k\Documents\fish-engine")
from fish.rules import RuleConfig
from fish.engine import Claim
from fish.exact import (ExactSolver, SubgameTooLarge, make_endgame,
                        position_key, _delta, solve_position)
from fish.cards import team_of

RULES = RuleConfig()


def hdr(t):
    print()
    print("=" * 72)
    print(t)
    print("=" * 72)
    sys.stdout.flush()


LAYERS = [
    ([0b110000, 0b001100, 0, 0b000011, 0, 0], 0),
    ([0b100000, 0b010000, 0b001000, 0b000100, 0b000010, 0b000001], 0),
    ([0b111000, 0b000111, 0, 0, 0, 0], 1),
    ([0b110100, 0, 0b001000, 0b000011, 0, 0], 2),
]

# --------------------------------------------------------------------- 1
hdr("1. ExactSolver reuse across two roots of the SAME layer")
print("_solve_layer marks `config` done, but only enumerates states REACHABLE")
print("from the root it was given. In a 1-half-suit layer a player holding 0")
print("cards can never receive one (you may only be asked for a card of a")
print("half-suit the ASKER already holds), so different card placements are")
print("mutually unreachable. Reusing one solver therefore KeyErrors.")
solver = ExactSolver(RULES)
a = make_endgame(RULES, [0], [0b111111, 0, 0, 0, 0, 0], turn=0)
b = make_endgame(RULES, [0], [0, 0b111111, 0, 0, 0, 0], turn=1)
print("  first  solve ->", solver.solve(a))
try:
    print("  second solve ->", solver.solve(b))
except Exception as e:
    print("  second solve RAISED", type(e).__name__, ":", repr(e)[:120])
    traceback.print_exc(limit=2)
print("  (a fresh solver gives:", ExactSolver(RULES).solve(b), ")")
sys.stdout.flush()


# --------------------------------------------------------------------- 2
class ShuffledSolver(ExactSolver):
    """Same algorithm, different value-iteration sweep ORDER."""

    def __init__(self, *a, order_seed=0, **kw):
        super().__init__(*a, **kw)
        self.order_seed = order_seed

    def _solve_layer(self, root):
        config = tuple(root.set_winner)
        if config in self._layer_done:
            return
        states = {}
        stack = [root]
        while stack:
            st = stack.pop()
            k = position_key(st)
            if k in states or st.is_terminal:
                continue
            states[k] = st
            self.nodes += 1
            if self.nodes > self.max_nodes:
                raise SubgameTooLarge("too large")
            p = st.turn
            for act in self.actions(st):
                if isinstance(act, Claim):
                    continue
                stack.append(self._child(st, p, act))
        exits = {}
        for k, st in states.items():
            p = st.turn
            out = []
            for act in self.actions(st):
                if not isinstance(act, Claim):
                    continue
                child = self._child(st, p, act)
                gained = _delta(st, child)
                if child.is_terminal:
                    out.append((act, gained))
                else:
                    sub, _ = self.solve(child)
                    out.append((act, gained + sub))
            exits[k] = out
        order = list(states)
        random.Random(self.order_seed).shuffle(order)
        V = {k: 0.0 for k in states}
        best = {}
        for _ in range(self.max_iterations):
            delta = 0.0
            for k in order:
                st = states[k]
                p = st.turn
                maximizing = team_of(p) == 0
                cur = float("-inf") if maximizing else float("inf")
                arg = None
                for act, val in exits[k]:
                    if (val > cur) if maximizing else (val < cur):
                        cur, arg = val, act
                for act in self.actions(st):
                    if isinstance(act, Claim):
                        continue
                    ck = position_key(self._child(st, p, act))
                    val = V.get(ck, 0.0)
                    if (val > cur) if maximizing else (val < cur):
                        cur, arg = val, act
                if arg is None:
                    cur = 0.0
                if abs(cur - V[k]) > 1e-12:
                    delta = max(delta, abs(cur - V[k]))
                    V[k] = cur
                best[k] = arg
            if delta < 1e-12:
                break
        else:
            raise SubgameTooLarge("no convergence")
        self.cache.update(V)
        self.best.update(best)
        self._layer_done.add(config)


class FullClaimSolver(ExactSolver):
    """Claim generation NOT pruned to true claims: adds one representative of
    each non-true outcome class (wrong split -> null, gift -> opponents)."""

    def actions(self, state):
        p = state.turn
        if state.hands[p] == 0:
            return list(state.legal_passes(p))
        acts = list(state.legal_asks(p))
        team = team_of(p)
        mates = [q for q in range(6) if team_of(q) == team]
        for hs in state.claimable_half_suits(p):
            holders = [state.holder_of(hs * 6 + i) for i in range(6)]
            if all(h is not None and team_of(h) == team for h in holders):
                acts.append(Claim(hs, tuple(holders)))
                wrong = list(holders)
                for i in range(6):
                    alt = [q for q in mates if q != holders[i]]
                    if alt:
                        wrong[i] = alt[0]
                        break
                if tuple(wrong) != tuple(holders):
                    acts.append(Claim(hs, tuple(wrong)))
            else:
                acts.append(Claim(hs, tuple(mates[0] for _ in range(6))))
        return acts


hdr("2. Value-iteration ORDER dependence")
for hands, turn in LAYERS:
    base = ExactSolver(RULES).solve(make_endgame(RULES, [0], hands, turn=turn))[0]
    vs = []
    for os_ in (1, 2, 3):
        vs.append(ShuffledSolver(RULES, order_seed=os_).solve(
            make_endgame(RULES, [0], hands, turn=turn))[0])
    flag = "OK" if all(abs(v - base) < 1e-9 for v in vs) else "ORDER-DEPENDENT"
    print("  hands=%s turn=%d base=%+.1f shuffled=%s  %s"
          % ([bin(h) for h in hands], turn, base, vs, flag))
    sys.stdout.flush()

hdr("3. Effect of pruning claims to TRUE claims only")
for hands, turn in LAYERS:
    v1 = ExactSolver(RULES).solve(make_endgame(RULES, [0], hands, turn=turn))[0]
    v2 = FullClaimSolver(RULES).solve(
        make_endgame(RULES, [0], hands, turn=turn))[0]
    print("  hands=%s turn=%d pruned=%+.1f full=%+.1f  %s"
          % ([bin(h) for h in hands], turn, v1, v2,
             "SAME" if abs(v1 - v2) < 1e-9 else "DIFFERENT"))
    sys.stdout.flush()

hdr("4. optimal_actions")
for hands, turn in LAYERS:
    st = make_endgame(RULES, [0], hands, turn=turn)
    s = ExactSolver(RULES)
    val, act = s.solve(st)
    opts = s.optimal_actions(st)
    bad = [a for a in opts if abs(s.action_value(st, a) - val) > 1e-9]
    print("  turn=%d value=%+.1f  best=%s  n_optimal=%d  best_in_optimal=%s"
          " mis-valued=%d" % (turn, val, type(act).__name__, len(opts),
                              act in opts, len(bad)))
    sys.stdout.flush()

hdr("5. Reachability of the 'unbroken cycle => 0' semantics")
print("  A layer needs >= 2 unresolved half-suits to be able to stall, because")
print("  in a 1-half-suit layer the player on move can always drain every")
print("  opponent (perfect information => every ask can be made to succeed)")
print("  and then claim. Check the values found above: all +/-1, never 0.")
hands = [0] * 6
for c in range(12):
    hands[c % 6] |= 1 << c
try:
    st = make_endgame(RULES, [0, 1], hands, turn=0)
    ExactSolver(RULES).solve(st)
    print("  2-half-suit layer SOLVED")
except Exception as e:
    print("  2-half-suit layer:", type(e).__name__, "-", str(e)[:100])
try:
    solve_position(st)
except Exception as e:
    print("  solve_position:", type(e).__name__, "-", str(e)[:100])
