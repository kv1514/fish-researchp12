"""Which policies may enter the arena, and which may never.

THE EXCLUSION IS THE IMPORTANT PART. This repository contains agents that see
the true deal -- ``oracle`` and ``oracle_gated``. They exist to price a
*ceiling*: how much a perfect card-reader would gain, which bounds what any
honest inference could ever be worth. They are not players.

A cheating agent placed in a strength ladder produces a number that looks
exactly like the honest ones beside it and means something entirely different,
and once such a number is copied into a table nothing about its appearance
reveals the difference. So the arena refuses them by name and by substring,
loudly, rather than trusting whoever writes the roster on the command line.
"""

from __future__ import annotations

#: Agents that see hidden state. Never admissible as a duelling policy.
CHEATERS = frozenset({"oracle", "oracle_gated"})

#: Substrings that also trip the guard, so a future ``oracle_v2`` cannot slip
#: past a name-only denylist.
_CHEAT_MARKERS = ("oracle", "cheat", "godmode", "perfect_info")


class CheatingAgentRefused(ValueError):
    """Raised when a roster entry would put a hidden-state agent in a ladder."""


#: The arena's named policies. Each maps to a registry spec understood by
#: ``fish4.registry4.make_agent``. Descriptions are what the report prints.
ROSTER: dict[str, dict] = {
    "kraken": {
        "spec": ("__registry__", "KRAKEN_V1"),
        "blurb": "KRAKEN v1.0, the deployed configuration: exact inference, "
                 "opponent model, belief-space lookahead, exhaustive forced "
                 "declarations.",
    },
    "kraken-nolookahead": {
        "spec": ("fishbot4", {"opponent_gamma": 0.35}),
        "blurb": "The ask objective in isolation -- same inference, no "
                 "lookahead, fewer posterior draws.",
    },
    "tuned": {
        "spec": ("tuned", {"w_turn": 0.6, "w_scarce": 0.2}),
        "blurb": "The v0.3 champion: hand-tuned ask weights, no exact "
                 "inference.",
    },
    "probabilistic": {
        "spec": ("probabilistic", {}),
        "blurb": "Picks by success probability alone.",
    },
    "heuristic": {
        "spec": ("heuristic", {}),
        "blurb": "Public-information heuristic. No belief state.",
    },
    "random": {
        "spec": ("random", {}),
        "blurb": "Uniform over legal actions. The floor.",
    },
}


def _refuse_if_cheating(name: str, spec) -> None:
    head = spec[0] if isinstance(spec, tuple) else str(spec)
    for probe in (name.lower(), str(head).lower()):
        if probe in CHEATERS or any(m in probe for m in _CHEAT_MARKERS):
            raise CheatingAgentRefused(
                f"{name!r} resolves to {head!r}, which sees hidden state. "
                "Agents that see the deal price a CEILING and are not "
                "players; putting one in a ladder produces a number "
                "indistinguishable from an honest one. Refused.")


def resolve(name: str):
    """Registry spec for an arena policy name, with the cheat guard applied."""
    if name not in ROSTER:
        raise KeyError(f"unknown policy {name!r}; known: "
                       + ", ".join(sorted(ROSTER)))
    spec = ROSTER[name]["spec"]
    if spec[0] == "__registry__":
        from fish4 import registry4
        spec = getattr(registry4, spec[1])
    _refuse_if_cheating(name, spec)
    return spec


def default_field() -> list[str]:
    """The roster in a fixed, strongest-first order, so reports are stable."""
    return ["kraken", "kraken-nolookahead", "tuned", "probabilistic",
            "heuristic", "random"]
