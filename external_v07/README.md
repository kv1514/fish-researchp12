# Dylan's engine, bridged: FishBot v0.7, released as SESTINA v1.0

The exhibition opponent on the website: the frozen v0.7 configuration from
<https://github.com/dylann4500/fishbot>, running its own C++ engine code,
playing our game through a one-shot decision binary.

**The upstream project renamed this agent.** It was developed and evaluated as
FishBot v0.7 and released as **SESTINA v1.0** (`docs/RELEASE-v1.0.md` upstream).
Their release notes say "the name changed at release; nothing measured did",
and every sealed identifier on their side still carries a `v07` form — the
freeze artifact, the spec string, the deal banks. This directory keeps the
`v07` names for the same reason they did: they are what the objects are called.
Where the two names both appear in this repository, *SESTINA v1.0* names the
released agent and *v0.7* names the configuration.

- `UPSTREAM.txt` — the upstream commit this build is pinned to.
- `v07_spec.txt` — their frozen `allparamsSpec` (from `engine/fishbot_v07.json`),
  the exact parameter vector plus det=12 test-time search their repo names as
  v0.7. Also embedded in `fish4/dylan_v07.py` for the deployed function.
- `shim_decide.cpp` — the shim `main`: feed it seat, hand, rules and the public
  event stream; it answers one decision (ask, declaration, or pass choice)
  through their `factory.hpp` agent and exits. Compiles against their headers
  only; none of their networking/server code (`httpd`, `serve`, `tunnel`,
  `lobby`) is included in the build.
- `build.sh` — local build. The deployed copy at `api/bin/fish_v07_decide` is
  built with `-static` and no `-march=native` so it runs on the Vercel runtime.

The Python side is `fish4/dylan_v07.py`, registered as `dylan_v07`. The two
projects agree on misdeclaration scoring — a wrong declaration awards the set to
the opponents in both engines (this repo's baseline since the rule correction;
theirs always) — so the one remaining rule difference is their out-of-turn
declaration channel versus our declarations-on-turn, documented there. Our
engine arbitrates, their policy is told the rules it is actually playing under,
and every proposed action is legality-checked with a counted fallback.
Verification: full games with zero fallbacks across 20 mixed 3v3 games before
anything shipped.

## Moving the pin, and why that did not move a number

The pin was `d017fbcb` for the whole of the v0.7 exhibition and the published
head-to-head. Upstream then added five commits: the SESTINA release, an
external-bot protocol (`extbot.hpp`, `botpkg.hpp`, `docs/BOT_PACKAGE.md`), a
port of *our* v0.1 search policy into their engine (`kv.hpp`), a bridge to our
v0.6 package (`kv6.hpp`), and **124 new lines in `factory.hpp`** — the function
this shim calls to construct their agent.

A published margin against "their v0.7" is a claim about a policy, so a change
under it is a threat to the claim rather than a housekeeping matter, and their
release notes asserting that nothing moved is their assertion, not our
measurement. `scripts4/v07_upstream_parity.py` settles it directly instead of
by rerunning a noisy head-to-head: it captures the exact stdin script the bridge
sends for every decision of real games and replays each one through a binary
built from the old pin and one built from the release, diffing stdout. The shim
is a pure function of that script, so a behavioural change cannot hide.

    6,329 decisions (5,817 asks, 472 declarations) over 60 deals x 2 seatings
    mismatches: 0                                          VERDICT: IDENTICAL

`results/v07_upstream_parity.json`. Two things follow and a third does not.
The pin moves to `f9b4743` with the published margin intact; the freeze
artifact `engine/fishbot_v07.json` is byte-identical across the same range, so
the configuration is unchanged as well as the play. What it does **not**
establish is equivalence everywhere: it exercises the decision distribution our
games actually reach, which is the one our claim is about, and nothing else.

## What their repository now contains about us

Extracted here because it changes what our own comparison means, not as a
courtesy. Upstream now carries two reciprocal bridges, and **both point at
superseded versions of this project**:

- `engine/src/kv.hpp` is a port of "KV's sampled-world search policy", and its
  own header names the source: `fish-researchp12 @ 0676737`, `fish/agents.py`
  `SearchAgent`. That commit is this project's **v0.1** — the pre-v0.3 engine
  that was rebuilt from scratch after a filesystem loss and shares no history
  with the current tree. It is not KRAKEN, and it is four development cycles
  behind it.
- `engine/src/kv6.hpp` bridges our deployed package over our own JSON dialect,
  and looks for it at `fishbot_v06/`. That directory is now `fishlab/`, so the
  path no longer resolves.

Neither of those appears in their technical report, which mentions neither
KRAKEN nor this project, so nothing published upstream currently rests on them.
The consequence for us is only this: if a KV-versus-SESTINA number ever appears
from their side, it is a number about our v0.1 unless it says otherwise. The
comparison this repository reports runs their *current released* engine against
our *current champion*, in both arbiters.

Their repository was previously present here as a single squashed commit, which
is why `fish4/dylan_ladder.py` recorded that the compiled-in v0.4/v0.5/v0.6
vectors could not be checked against the history that produced them. The full
history (89 commits) is now published, and that limitation is lifted.

## Provenance

Their repository carries no licence file; the code is used here to run their
bot as-published for a head-to-head exhibition, with attribution, and none of
it is redistributed in this repository beyond the compiled decide binary.
