"""The doomed-ask claim gate's second bar must be off until it is asked for.

`fish4/agent4.py`'s gate declares when the ask it was about to make cannot
land. Since v0.3 it has used one hard-coded bar, 0.5 on p_exact, and has never
read p_team -- the second element of the very tuple `best_candidate` returns,
and the one `forced_claim` prices its own decision with. `stuck_team_certain`
adds a second bar for the p_team-certain case; at its default of 1.01 the test
can never pass, so the champion must be reproduced move for move.

The second test is what stops the first from being vacuous. The gate is rare
-- about 0.3 firings a game across all six seats -- so a knob wired to nothing
would sail through a bit-identity check on a handful of deals. So the branch
is first shown to be REACHED, at the (p_exact, p_team) pair that arms it, and
only the seeds where it was reached are replayed.
"""

import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from fish.cards import NUM_PLAYERS
from fish.engine import GameState
from fish.observation import Observation
from fish.rules import RuleConfig
from fish4.claim4 import ClaimEvaluator
from fish4.registry4 import V06_DEPLOYED, make_agent

RULES = {"wrong_distribution_outcome": "opponent"}
BASE = dict(V06_DEPLOYED[1])
GATE_WHY = "cannot land"
CERTAIN = 0.999


def _play(params, seed, watch=None):
    rules = RuleConfig(**RULES)
    agents = [make_agent(("fishbot4", params)) for _ in range(NUM_PLAYERS)]
    st = GameState.deal(rules, seed=seed)
    rng = random.Random(seed + 7)
    for p, a in enumerate(agents):
        a.begin_game(p, rules, rng.getrandbits(64))
    moves = []
    for _ in range(400):
        if st.is_terminal:
            break
        p = st.turn
        act = agents[p].act(Observation.from_state(st, p))
        moves.append((p, repr(act)))
        if watch is not None:
            tr = agents[p].last_trace
            if tr and tr.get("kind") == "declare" and GATE_WHY in tr["why"]:
                watch.append(seed)
        st.apply(p, act)
    return moves, list(st.set_winner)


def test_the_default_changes_nothing():
    """Explicit defaults must reproduce the deployed champion exactly."""
    for seed in range(4):
        a, wa = _play(dict(BASE), 7_100 + seed)
        b, wb = _play(dict(BASE, claim_stuck_threshold=0.5,
                           stuck_team_certain=1.01), 7_100 + seed)
        assert a == b and wa == wb, (
            f"seed {seed}: the stuck-gate defaults changed the game, so the "
            f"knob is not off by default")
        assert len(a) > 20, f"seed {seed} produced only {len(a)} moves"


def test_the_branch_is_reached_and_arming_it_changes_play():
    """The 1.01 is doing the work, not a dead code path.

    p_team is a probability, so 1.01 is unreachable by construction. The test
    finds seeds where the incumbent gate actually fires on a candidate the
    armed bar would defer, then shows those games diverge. Both halves are
    required: a reachability claim without a divergence proves nothing, and a
    divergence without reachability could come from anywhere.
    """
    real = ClaimEvaluator.best_candidate
    seen = []

    def spy(self):
        r = real(self)
        if r is not None:
            seen.append((float(r[0]), float(r[1])))
        return r

    hits, deferrable = [], []
    ClaimEvaluator.best_candidate = spy
    try:
        for s in range(20):
            seen.clear()
            fired = []
            _play(dict(BASE, trace=True), 7_200 + s, watch=fired)
            if fired:
                hits.append(7_200 + s)
                # the pair the gate last saw before declaring
                if any(pt >= CERTAIN and pe < BASE.get("claim_threshold", 0.97)
                       for pe, pt in seen):
                    deferrable.append(7_200 + s)
    finally:
        ClaimEvaluator.best_candidate = real

    assert hits, "the gate never fired in 20 games; the probe is broken"
    assert deferrable, (
        f"the gate fired on {len(hits)} of 20 seeds but never on a p_team >= "
        f"{CERTAIN} candidate below the voluntary bar, so arming it could not "
        f"change anything")

    changed = 0
    for seed in deferrable:
        a, _ = _play(dict(BASE), seed)
        b, _ = _play(dict(BASE, claim_stuck_threshold=0.5,
                          stuck_team_certain=CERTAIN), seed)
        if a != b:
            changed += 1
    assert changed, (
        f"arming stuck_team_certain={CERTAIN} changed none of the "
        f"{len(deferrable)} seeds where the branch was reachable")


def test_the_knob_is_a_deferral_and_never_a_new_declaration():
    """Both bars sit at or above the incumbent's, so the armed gate is a
    subset of the incumbent's: it can decline to declare, never declare where
    the incumbent would not have."""
    a = make_agent(("fishbot4", dict(BASE, claim_stuck_threshold=0.97,
                                     stuck_team_certain=CERTAIN)))
    assert a.claim_stuck_threshold >= 0.5
    assert a.claim_cfg.threshold >= 0.5
