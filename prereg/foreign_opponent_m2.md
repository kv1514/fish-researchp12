# Pre-registration: does the m=2 correction survive a foreign opponent?

Written before any pair of this run.

## Why this exists

The endgame-m ladder above m=2 was withdrawn when cross-play showed its
growing rungs were **poisoning the sibling's opponent model**, not strength:
every rung was measured only against copies of this project's own engine, and
the m=9 config that scored +4.28 against the sibling LOSES by 2.14 to v0.3.
Dylan's own repository documents the same trap independently ("the advantage
is a self-play advantage ... it does not transfer").

The m=2 rung kept its place because it has non-sibling evidence — the exact
solver's diagnosis, a game-held-out fit, an exploitability check. But its
IN-PLAY number (+0.1220) was still measured against siblings. The exhibition
bridge now provides what no earlier test had: a genuinely foreign opponent,
**Dylan's FishBot v0.7**, a different codebase, a different belief, a
different policy class.

## The design

Identical deals, both rotations, two arms:

- **X**  = the deployed config (endgame_m=2, endgame_d_info=+2.0) vs Dylan v0.7
- **X0** = the same config with the correction OFF (endgame_m=0) vs Dylan v0.7

Statistic: per (deal, rotation), (X's set margin over Dylan) minus (X0's set
margin over Dylan) — a paired difference against the same foreign opponent on
the same cards. 250 deals × 2 rotations = 500 paired games per arm, seeds
331000..331249, agent seed base 3310.

## What this can and cannot resolve, fixed now

The sibling-measured effect is +0.12 sets. The expected paired sd here is
roughly 2–3 sets, so the 95% interval will span about ±0.2–0.3: this run is
**underpowered to confirm** an effect of sibling size, and a null here does
NOT retire the correction (its other evidence stands).

What it IS powered for is a **reversal of deception scale**: the withdrawn
rungs flipped by 1–6 sets when the opponent changed. Outcomes:

1. **CI entirely below 0** — the correction's in-play gain was also a sibling
   artefact. Withdraw it from the deployed config; the offline evidence then
   stands alone and says so in the paper.
2. **CI straddles 0** — no reversal detected. The correction stays, and the
   paper's claim gains the sentence "and does not reverse against a foreign
   opponent (n=500 paired games)".
3. **CI entirely above 0** — it transfers, which is more than anyone claimed.

No second run to chase a straddle.

## Amendments

None yet.
