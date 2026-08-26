"""Exact best response at m = 1, under imperfect information.

Everything this project calls exact is a statement about the
PERFECT-information game. ``scripts4/closed_form_proof.py`` solves that game at
every m, and the answer is degenerate: the team on move takes every half-suit it
can touch. The v0.3 benchmark's headline -- belief agents choosing a provably
optimal move in 100% of information-resolved positions -- was scored against
that same perfect-information optimum, and every one of those positions had a
single live half-suit.

So the one thing nobody has measured is whether the champion plays the m = 1
endgame well when it does NOT know where the cards are. That is a different
game with a different value, and this solves it exactly for one deviating seat.

WHAT IS EXACT AND WHAT IS ASSUMED
---------------------------------
Exact: the enumeration of deals, the deviator's optimisation over its own
information sets, and the backward induction. No sampling anywhere.

Assumed, and both stated rather than buried:

* **The prior is uniform over consistent deals.** A deal is consistent when
  every unseen card sits with a player the deviator's belief still allows and
  the public hand counts are met. Uniform is the maximum-entropy choice given
  those constraints and is what the constraint system alone licenses; the
  champion's own posterior tilts this by an opponent model, and using that
  instead would make the answer a statement about the model rather than about
  the position.
* **The opponents are a deterministic realisation of the champion.** The
  champion samples, so "the champion" is a distribution over policies. Seeding
  it from a hash of the observation makes it a pure strategy -- a well-defined
  object to best-respond to -- and one that a fresh agent reproduces exactly,
  checked: over 629 real decisions a freshly constructed agent given the same
  observation computes a bit-identical belief to one attached from the deal.

THE CONTROL THAT MAKES IT CHECKABLE
-----------------------------------
When the deviator's belief pins every card the support collapses to one deal,
imperfect information is gone, and the exact value MUST equal the closed form
``2f - m``. 43% of real m = 1 decisions are of that kind, so the solver is
checked against an independently proved answer on nearly half its input. A
solver that cannot reproduce ``+/-1`` there is wrong, whatever it says
elsewhere.
"""

from __future__ import annotations

import copy
import hashlib
import time
from itertools import product
from typing import Optional

from fish.cards import (CARDS_PER_HALF_SUIT, NUM_PLAYERS, half_suit_cards,
                        team_of)
from fish.engine import Ask, Claim, GameState, NULL_TEAM, Pass
from fish.observation import Observation
from fish.rules import RuleConfig

#: Depth cap. A cycle of mutual misses can run forever; the harness scores an
#: unresolved half-suit for nobody (fish4/match.play_capped), so this does too.
MAX_PLIES = 24

#: Seconds a single position may take before the solver gives up on it.
#:
#: This exists because "solvable" and "solvable in the time available" were
#: conflated once already. A probe capped at support 8 solved every m = 2
#: position in under a second, which read as "m = 2 is reachable"; the study
#: allowed support up to 24 and ground on ONE position for six and a half
#: hours, writing nothing. An exact solver with no deadline does not fail
#: loudly, it fails silently and forever, and a layer that is out of reach
#: should say so rather than hang.
DEFAULT_DEADLINE = 60.0


class SolveTimeout(Exception):
    """The position exceeded its budget. It is unsolved, not zero."""


def consistent_deals_multi(obs: Observation, bel, live) -> list:
    """The same enumeration over SEVERAL live half-suits at once.

    m = 1 is the only layer where one half-suit's cards are all the live cards,
    so the single-half-suit version below silently assumes it. Above m = 1 the
    hand counts cover every live card and the enumeration has to as well.
    """
    me = obs.player
    cards = [c for h in live for c in half_suit_cards(h)]
    mine = [c for c in cards if (obs.hand >> c) & 1]
    unseen = [c for c in cards if not (obs.hand >> c) & 1]
    opts = []
    for c in unseen:
        mask = bel.current_holder_mask(c)
        allowed = [q for q in range(NUM_PLAYERS)
                   if q != me and (mask >> q) & 1]
        if not allowed:
            return []
        opts.append(allowed)
    prod = 1
    for o in opts:
        prod *= len(o)
    if prod > 2_000_000:
        return []                    # refuse rather than grind
    counts = list(obs.hand_counts)
    out = []
    for combo in (product(*opts) if opts else [()]):
        need = [0] * NUM_PLAYERS
        for q in combo:
            need[q] += 1
        if any(need[q] != counts[q] for q in range(NUM_PLAYERS) if q != me):
            continue
        hands = [0] * NUM_PLAYERS
        for c in mine:
            hands[me] |= 1 << c
        for c, q in zip(unseen, combo):
            hands[q] |= 1 << c
        out.append(tuple(hands))
    return out


def consistent_deals(obs: Observation, bel, hs: int) -> list:
    """Every assignment of the unseen cards of ``hs`` the public record allows.

    Constrained by the belief's per-card holder masks and by the public hand
    counts, both of which every seat can see.
    """
    me = obs.player
    cards = list(half_suit_cards(hs))
    mine = [c for c in cards if (obs.hand >> c) & 1]
    unseen = [c for c in cards if not (obs.hand >> c) & 1]
    opts = []
    for c in unseen:
        mask = bel.current_holder_mask(c)
        allowed = [q for q in range(NUM_PLAYERS)
                   if q != me and (mask >> q) & 1]
        if not allowed:
            return []
        opts.append(allowed)
    counts = list(obs.hand_counts)
    out = []
    for combo in (product(*opts) if opts else [()]):
        need = [0] * NUM_PLAYERS
        for q in combo:
            need[q] += 1
        if any(need[q] != counts[q] for q in range(NUM_PLAYERS) if q != me):
            continue
        hands = [0] * NUM_PLAYERS
        for c in mine:
            hands[me] |= 1 << c
        for c, q in zip(unseen, combo):
            hands[q] |= 1 << c
        out.append(tuple(hands))
    return out


#: Memo for the champion oracle. It is a PURE FUNCTION of the information set
#: -- that is the whole point of seeding it from the observation hash -- so
#: caching it changes no value, only the time to get one. Without it the solver
#: rebuilt an agent and replayed a hundred-event history at every node of every
#: branch, and twenty games took over two hours to reach four.
_CHAMP_CACHE: dict = {}


def _info_key(seat, obs) -> bytes:
    return hashlib.sha256(repr((seat, obs.hand, tuple(obs.hand_counts),
                                tuple(obs.set_winner),
                                tuple(repr(e) for e in obs.history)))
                          .encode()).digest()


def _champion_action(spec, rules, seat, st):
    """The champion's move, as a pure function of its information set."""
    from fish4.registry4 import make_agent
    obs = Observation.from_state(st, seat)
    key = _info_key(seat, obs)
    hit = _CHAMP_CACHE.get(key)
    if hit is not None:
        return hit[0]
    a = make_agent(spec)
    a.begin_game(seat, rules, int.from_bytes(key[:8], "big"))
    try:
        act = a.act(obs)
    except Exception:
        act = None
    _CHAMP_CACHE[key] = (act,)
    return act


class ExactII:
    """Best response for one seat at m = 1, against champion opponents."""

    def __init__(self, rules: RuleConfig, hs, deviator: int, spec):
        self.rules = rules
        #: one half-suit or several. Kept as a tuple internally so the m = 1
        #: path and the general path are the same code; ``self.hs`` stays an
        #: int there so nothing that reads it has to change.
        self.live = (hs,) if isinstance(hs, int) else tuple(hs)
        self.hs = self.live[0]
        self.me = deviator
        self.spec = spec
        self.nodes = 0
        self._memo: dict = {}
        #: the optimal action AT THE ROOT, once solve() has run. The value
        #: alone says the champion leaves something on the table; this says
        #: what it should have done instead, which is what a policy change has
        #: to be built from.
        self.best_action = None
        self.action_values: dict = {}
        self.deadline = None          # set by the caller; None = no limit

    # -- terminal value ------------------------------------------------------

    def _value(self, st: GameState) -> Optional[float]:
        total = 0.0
        for h in self.live:
            w = st.set_winner[h]
            if w is None:
                return None
            if w == NULL_TEAM:
                continue
            total += 1.0 if w == team_of(self.me) else -1.0
        return total

    # -- what the champion itself gets ---------------------------------------

    def champion_value(self, states, weights, max_plies=MAX_PLIES) -> float:
        """The same expectation with the CHAMPION in the deviator's seat.

        The best response is only interesting beside this. Their difference is
        the exact gain from deviating at m = 1 -- exploitability restricted to
        the endgame, computed rather than sampled, which is what
        scripts4/exploitability.py could not do.
        """
        tot = 0.0
        for st, w in zip(states, weights):
            t = copy.deepcopy(st)
            for _ in range(max_plies):
                v = self._value(t)
                if v is not None:
                    break
                a = _champion_action(self.spec, self.rules, t.turn, t)
                if a is None:
                    break
                try:
                    t.apply(t.turn, a)
                except Exception:
                    break
            v = self._value(t)
            tot += w * (0.0 if v is None else v)
        return tot

    # -- the search ----------------------------------------------------------

    def solve(self, states: list, weights: list, depth: int = 0) -> float:
        """Expected value to the deviator's team over a weighted belief set.

        ``states`` all share the deviator's information: same public history,
        same own hand. Its action must therefore be the same in all of them,
        which is what makes this a best response over INFORMATION SETS rather
        than a per-deal cheat.
        """
        self.nodes += 1
        if self.deadline is not None and time.monotonic() > self.deadline:
            raise SolveTimeout(f"exceeded budget after {self.nodes} nodes")
        # Memo on the node itself: two branches reaching the same weighted
        # belief set at the same depth have the same value by construction.
        key = (depth, tuple(sorted(
            (tuple(s.hands), s.turn, tuple(s.set_winner), round(w, 12))
            for s, w in zip(states, weights))))
        hit = self._memo.get(key)
        if hit is not None:
            return hit
        done = [self._value(s) for s in states]
        if all(v is not None for v in done):
            r = sum(w * v for w, v in zip(weights, done))
            self._memo[key] = r
            return r
        if depth >= MAX_PLIES:
            self._memo[key] = 0.0   # unresolved scores for nobody, as the
            return 0.0              # harness does

        turn = states[0].turn
        if any(s.turn != turn for s in states):
            # The deviator can see whose turn it is, so this cannot happen.
            raise AssertionError("information set spans different movers")

        r = (self._deviator(states, weights, depth) if turn == self.me
             else self._opponent(states, weights, depth, turn))
        self._memo[key] = r
        return r

    def _legal(self, st: GameState):
        p = st.turn
        if st.hands[p] == 0:
            return list(st.legal_passes(p))
        acts = list(st.legal_asks(p))
        team = team_of(p)
        for h in self.live:
            if st.set_winner[h] is not None:
                continue
            base = h * CARDS_PER_HALF_SUIT
            holders = [st.holder_of(base + i)
                       for i in range(CARDS_PER_HALF_SUIT)]
            if all(x is not None and team_of(x) == team for x in holders):
                acts.append(Claim(h, tuple(holders)))
        return acts

    def _deviator(self, states, weights, depth):
        # Legality is information-set measurable: an ask needs a card of the
        # half-suit in hand (own), a target holding cards (public counts), and
        # a card not held (own). So the action set is the same in every state.
        acts = self._legal(states[0])
        # Claims are the exception: which assignment is TRUE differs by state,
        # so the deviator may only offer assignments over its own team, and is
        # scored on whether each happens to be right.
        acts = [a for a in acts if not isinstance(a, Claim)]
        acts += self._claim_candidates(states)
        if not acts:
            return 0.0
        best = None
        root = depth == 0
        for a in acts:
            buckets = {}
            for s, w in zip(states, weights):
                t = copy.deepcopy(s)
                try:
                    ev = t.apply(self.me, a)
                except Exception:
                    return -1.0 if best is None else best
                sig = repr(ev)
                buckets.setdefault(sig, ([], []))
                buckets[sig][0].append(t)
                buckets[sig][1].append(w)
            v = 0.0
            for ss, ws in buckets.values():
                tot = sum(ws)
                v += tot * self.solve(ss, [x / tot for x in ws], depth + 1)
            if root:
                self.action_values[repr(a)] = v
            if best is None or v > best:
                best = v
                if root:
                    self.best_action = a
        return best if best is not None else 0.0

    def _claim_candidates(self, states):
        """The declarations worth considering: those TRUE in some candidate.

        All 3^6 = 729 assignments over the team are legal, but a declaration
        true in no candidate deal scores at most 0 in every one of them, while
        one true in some candidate scores +1 there and no worse elsewhere. So
        the rest are weakly dominated and enumerating them only costs tree.
        """
        team = team_of(self.me)
        seen = set()
        out = []
        for h in self.live:
            base = h * CARDS_PER_HALF_SUIT
            for st in states:
                if st.set_winner[h] is not None:
                    continue
                holders = tuple(st.holder_of(base + i)
                                for i in range(CARDS_PER_HALF_SUIT))
                if any(x is None or team_of(x) != team for x in holders):
                    continue        # not ours in this deal; cannot be true
                if (h, holders) not in seen:
                    seen.add((h, holders))
                    out.append(Claim(h, holders))
        return out

    def _opponent(self, states, weights, depth, seat):
        buckets = {}
        for s, w in zip(states, weights):
            a = _champion_action(self.spec, self.rules, seat, s)
            t = copy.deepcopy(s)
            if a is None:
                continue
            try:
                ev = t.apply(seat, a)
            except Exception:
                continue
            sig = repr(ev)
            buckets.setdefault(sig, ([], []))
            buckets[sig][0].append(t)
            buckets[sig][1].append(w)
        if not buckets:
            return 0.0
        v = 0.0
        norm = sum(sum(ws) for _, ws in buckets.values())
        for ss, ws in buckets.values():
            tot = sum(ws)
            v += (tot / norm) * self.solve(ss, [x / tot for x in ws], depth + 1)
        return v
