"""Dylan's RELEASED LADDER, extracted properly rather than one version deep.

`fish4/dylan_v07.py` bridges one policy: the frozen v0.7. That was never a
limitation of the bridge. `external_v07/shim_decide.cpp` reads a `SPEC` line
and hands it straight to their `makeAgent()`, and their factory dispatches a
whole ladder off the base prefix -- so every released FishBot was one string
away the entire time, and nothing but the absence of this file stopped us
measuring against all of them.

WHAT THEIR FACTORY ACCEPTS (engine/src/factory.hpp at the pinned commit):

  v02 v03            scripted baselines, Baseline::FishV02 / FishV03
  v04 v05 v06        V04Agent / V05Agent / V06Agent, fitted vectors compiled in
  v07 v07r           V07Responder -- the one already bridged
  v07c               V07AdaptAgent: an ONLINE model of the target's policy that
                     updates within a match (their threat-model class C6)
  v07l               V07LAgent: the leaf-evaluator interface, whose default is
                     bit-for-bit v0.6's leafValue -- an identity control
  v07i               V07InvertAgent: white-box transcript inversion (C5), which
                     needs the opponent's policy source to invert
  v07x               A CHEAT HARNESS. See below.
  random hunter diversifier detective lockout bluffer
  silent feint withholder                       scripted styles

WHAT THIS MODULE EXPORTS, AND WHY IT IS A SHORTER LIST.

Only the six RELEASES: v0.2 through v0.7. A version ladder is a claim about
how a project's strength moved release over release, and v07c, v07l and v07i
are research instruments rather than releases -- one adapts to its opponent
within the match, one needs the opponent's source to work at all, and one is
an identity control. Putting any of them on a rung would answer a question
nobody asked with a number that looks like a release.

THE CHEATS ARE REFUSED, by base name and by substring.

`v07x` is a deliberate cheat harness -- their own header calls the three
policies "deliberately-cheating", built as positive controls for a
side-channel gate:

    cheat=seed    inverts its reset seed to the DEAL seed, re-deals the pack
                  and plays clairvoyantly
    cheat=shared  writes to a process-global board shared by the three team
                  seats and conditions its ask on what a teammate wrote
    cheat=conv    reads the arbitrary tie-break label of a teammate's ask

This is the same rule `arena/roster.py` applies to our own `oracle` and
`oracle_gated`, and for the same reason: a cheating agent in a strength ladder
produces a number that looks exactly like an honest one. Note that `v07x`
with NO `cheat=` option falls through to a plain V06Agent in their factory, so
barring the substring "cheat" alone would let `v07x` through and then let
`v07x:cheat=seed` through on a later edit that dropped the marker. The BASE is
refused outright.

PROVENANCE, AND WHAT IT DOES NOT ESTABLISH.

THE CAVEAT THIS SECTION USED TO CARRY IS DISCHARGED. Their repository was
present here as a single squashed commit, so there was no history against which
to check whether the compiled-in v0.4, v0.5 and v0.6 vectors were the ones
their published results were generated from, and this module said so. Their
full history (89 commits) is now published, including the release commits, so
the question is answered rather than flagged.

`scripts4/dylan_ladder_provenance.py` runs their own reproduction protocol:
build THEIR engine at the release commit and at our pin, run the identical
`fish match` on both, compare every field. Over five rungs x three seeds at 240
games a cell:

    v02  bb3bc8a   v03  bb3bc8a   v04  bb3bc8a   v05  bd812fe   v06  60fee17
    play differences: 0 at every rung        PLAYS IDENTICALLY

Win rate, mean sets, ask accuracy, declaration counts and events per game agree
exactly at every cell. What moved is their bootstrap interval, in the last
place at 5 of 15 cells, and nine JSON fields their older builds did not emit --
reporting, not play. `results/dylan_ladder_provenance.json`.

Two limits on what that licenses. A differing field would have localised a
change to the policy-and-arbiter pair rather than to the policy, since both
live in one binary; the pass is clean, so the distinction did not have to be
made. And it does not verify their PUBLISHED numbers for a rung, which came
from their harness on their deal banks -- their own manifests point at commits
absent even from the full history and record `working_tree_dirty = True`.
Nothing in this repository can check those.

One thing the manifests do pin: v0.4's `policy_spec` is `v04:mgate=0.008`,
not a bare `v04`, and that is the string used here -- their published spec,
not one we chose.

IT IS ALSO INERT, WHICH IS WORTH KNOWING RATHER THAN ASSUMING. Measured on a
250-deal probe (`scripts4/dylan_ladder_sweep.py mgate`), `v04` and
`v04:mgate=0.008` are bit-identical: same margin, same interval, same error
rates to four decimals. Two independent reasons, both in their source at the
pinned commit:

  * `v04.hpp:130` sets `marginalGate = .008` as v0.4's DEFAULT, so the option
    assigns the value it already had; and
  * the `v04` branch of `makeAgent` parses only `belief`. `mgate` is applied
    in the v05/v06 option helpers (factory.hpp:80, :398) and never on the v04
    path at all, so the key is read into the option map and dropped.

Harmless here because the two agree. It would not be harmless to someone who
set `v04:mgate=0.05` expecting a different gate and silently got the default.
"""
from __future__ import annotations

from fish4.dylan_v07 import DylanV07, _load_spec

#: our name -> (their spec, what the spec is and where it came from)
RELEASES: dict[str, tuple[str, str]] = {
    "dylan_v02": ("v02", "Baseline::FishV02, scripted"),
    "dylan_v03": ("v03", "Baseline::FishV03, scripted"),
    "dylan_v04": ("v04:mgate=0.008",
                  "V04Agent; spec from research/v04/results/MANIFEST.json"),
    "dylan_v05": ("v05",
                  "V05Agent; spec from research/v05/results/MANIFEST.json"),
    "dylan_v06": ("v06", "V06Agent, the fitted vector compiled in at d017fbcb"),
    "dylan_v07": (None, "V07Responder; the frozen allparamsSpec, loaded from "
                        "external_v07/v07_spec.txt"),
}

#: Bases refused outright. v07x is their cheat harness; with no cheat= option
#: it silently degrades to a V06Agent, which is why the BASE is barred rather
#: than only the marker.
BARRED_BASES = frozenset({"v07x"})

#: Substrings that also trip the guard, so a renamed cheat cannot slip in.
#: Mirrors arena/roster.py's _CHEAT_MARKERS and adds their side-channel names.
CHEAT_MARKERS = ("cheat", "oracle", "godmode", "perfect_info", "v07x",
                 "clairvoyant")


def refuse_if_cheating(spec: str) -> None:
    """Raise unless `spec` names a policy that reads only what it is dealt.

    Checked on the WHOLE spec string, not just the base, because their options
    carry the cheat: `v07x:cheat=seed` differs from an honest agent by one
    key=value pair.
    """
    low = (spec or "").lower()
    base = low.split(":", 1)[0].strip()
    if base in BARRED_BASES:
        raise SystemExit(
            f"{spec!r} names {base!r}, their cheat harness. Its policies read "
            f"the deal seed, share state across team seats, or decode a "
            f"teammate's tie-break label. Nothing it produces is a strength "
            f"figure and it may never sit opposite an honest arm.")
    for marker in CHEAT_MARKERS:
        if marker in low:
            raise SystemExit(
                f"{spec!r} contains {marker!r}. Cheating agents never enter a "
                f"strength ladder; price a ceiling with one and label it a "
                f"ceiling.")


def spec_for(name: str) -> str:
    """The frozen spec string for one released version."""
    if name not in RELEASES:
        raise KeyError(
            f"{name!r} is not one of Dylan's releases: {sorted(RELEASES)}")
    spec, _why = RELEASES[name]
    spec = spec if spec is not None else _load_spec()
    refuse_if_cheating(spec)
    return spec


def make(name: str, timeout: float = 60.0) -> DylanV07:
    """One of their released policies, playing our game through their binary.

    Returns a DylanV07 whose `name` is the RELEASE, not "dylan_v07". The
    override hatch on DylanV07 exists so a variant can be measured against the
    frozen spec; using it without renaming would file a different policy's
    numbers under v0.7, which is the exact hazard that docstring warns about.
    """
    agent = DylanV07(timeout=timeout, spec=spec_for(name))
    agent.name = name
    return agent


#: The ladder in release order, for a strength sweep.
LADDER = tuple(RELEASES)
