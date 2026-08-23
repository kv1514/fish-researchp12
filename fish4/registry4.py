"""Agent registry spanning v0.3 and v0.4 policies.

Evaluation harnesses cross process boundaries, so agents are addressed by
``(name, kwargs)`` specs rather than by object. Importing this module registers
the v0.4 policies alongside the v0.3 ones; any worker process that imports it
can therefore construct either generation, which is what makes head-to-head
duplicate-deal matches between the two possible at all.
"""

from __future__ import annotations

from fish.agents import AGENT_REGISTRY as _V03

from .agent4 import FishBot4

#: The v0.3 champion, as established by 600-pair duplicate-deal experiments.
V03_CHAMPION = ("tuned", {"w_turn": 0.6, "w_scarce": 0.2})
#: The v0.3 baseline the champion was measured against.
V03_BASELINE = ("probabilistic", {})

#: The v0.4 champion: every "vs champion" cell in the paper is against this
#: exact spec, so it is a fixed reference and its defaults must not drift.
V04_CHAMPION = ("fishbot4", {"opponent_gamma": 0.35})

#: The champion plus the belief-space lookahead, which a pre-registered run over
#: 6000 duplicate deal-pairs put at +0.104 sets per deal-pair, 95% CI
#: [+0.020, +0.189] (jobs/PREREGISTRATION_lookahead.md, and the settling blocks
#: of the paper's lookahead table). It is the strongest configuration measured.
#:
#: It is a SEPARATE NAME rather than a change to FishBot4's defaults, and that is
#: not timidity. Every duel in results/v04_duels.jsonl labelled "vs champion"
#: names its opponent as fishbot4 with an explicit opponent_gamma and nothing
#: else; moving the defaults would silently redefine what those runs measured,
#: including the ones still in flight. The reference stays put and the stronger
#: policy gets its own name.
#:
#: The gain is not free: Section "Cost" of the paper measures the search at about
#: 6.7 ms per decision, roughly a quarter again on top of a v0.4 turn, so a
#: caller under a latency budget should choose deliberately rather than inherit.
V04_STRONGEST = ("fishbot4", {"opponent_gamma": 0.35, "w_lookahead": 0.25,
                              "lookahead_depth": 3, "lookahead_beam": 4})

REGISTRY = dict(_V03)
REGISTRY["fishbot4"] = FishBot4

# Register into the v0.3 registry too, so tools that only know about that one
# keep working. Mutating the dict is deliberate: it avoids forking v0.3 code.
_V03.setdefault("fishbot4", FishBot4)


def make_agent(spec):
    name, kwargs = spec
    return REGISTRY[name](**kwargs)
