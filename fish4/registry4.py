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

REGISTRY = dict(_V03)
REGISTRY["fishbot4"] = FishBot4

# Register into the v0.3 registry too, so tools that only know about that one
# keep working. Mutating the dict is deliberate: it avoids forking v0.3 code.
_V03.setdefault("fishbot4", FishBot4)


def make_agent(spec):
    name, kwargs = spec
    return REGISTRY[name](**kwargs)
