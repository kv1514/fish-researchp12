# Which stored journals came through which bridge

Every game this project has played against Dylan's FishBot v0.7 went through
`fish4/dylan_v07.py`, our bridge into his C++ engine. On 2026-08-28 an
adversarial read of his source found a defect in that bridge — not in either
engine — and it ran in **our** favour. This file says which stored results
were taken before the repair and which after, because a number is only as
good as the apparatus that produced it, and the apparatus changed.

The revision constant lives in `fish4/dylan_v07.py` as `BRIDGE_REV`.

## What changed between rev 1 and rev 2

Forced to declare, his own driver picks the first live half-suit the mover
**holds a card in** (`engine/src/game.hpp:535`):

```cpp
for (int st = 0; st < NSET; st++)
  if (g.pub.setActive[st] && (g.hand[g.turn] & setMask(st)))
    { chosen = st; break; }
```

Rev 1 of our bridge passed the first live half-suit, full stop. His
`bestGuess` was therefore periodically asked to name all six owners of a
half-suit it held nothing of — a question with no anchor in its own hand,
which his driver never puts him in a position to be asked, and which under
the opponent-award rule hands the set to us. Rev 2 mirrors his rule
(`DylanV07._forced_half_suit`, pinned by `tests4/test_dylan_bridge.py`).

## What it was worth

Priced paired, on 4,000 deals replayed under both revisions with identical
deals and identical seating (`scripts4/bridge_bug_price.py` →
`results/bridge_bug_price.json`): **−0.0915 sets/game against us**, 95% CI
[−0.1076, −0.0754]. Real, and about 4% of the margin — and an order of
magnitude smaller than the 0.30 sets/game first estimated off 40 games,
which is what the paired instrument is for.

Two supporting figures, both from the same paired set. His declaration
accuracy rises under the repair (76.04% → 78.85%); ours barely moves (96.88%
→ 96.69%), which is the control — the repair touches only his side of the
bridge, and if our number had moved much, something else would be wrong.

Note the shape of the error. The anchorless forced declarations were
**ownership**-class mistakes: half-suits the opposing team still held a card
of. They are *not* the allocation-class misdeclarations the paper's
160-to-306 split counts, and that split is flat across the repair (1,078 →
1,070 against v0.7 over the same 4,000 paired deals). So the finding that we
misdeclare roughly half as often survives; the explanation that credited it
to his forced declarations does not.

The repaired head-to-head, which is what the paper and the package README now
quote: **+2.3750** [+2.2896, +2.4604] sets/game over 4,000 games, 63.19% of
decided sets, 80.70% of games won, zero substituted moves.

## The ledger

| journal | rev | status |
|---|---|---|
| `mega_match_journal.jsonl` | **2** | current; every row carries `"rev": 2` |
| `mega_match_journal_prefix_bridgebug.jsonl` | 1 | retained, retracted. The 10,000-game run that reported +2.4250 sets/game (+2.4665 on the 4,000 deals the rev-2 run also covers). Kept rather than deleted so the retracted numbers stay readable, and used as the paired baseline that prices the defect. |
| `foreign_award_journal.jsonl` | 1 | R2 of `prereg/rules_award_baseline.md`. Its **pre-registered verdict is unaffected** — the defect is common-mode across the correction-on and correction-off arms, and a paired difference cannot see an error identical in both halves of the pair. The *context* figures it reports beside that verdict (margin +2.544, set share 64.3%) are rev-1 absolutes and are superseded by the rev-2 head-to-head. |
| `r6_screen_journal.jsonl` | 1 | R6, the contestation and silence screens. Same reasoning: every arm ran through the same bridge, so the arm-vs-baseline contrasts that carry the rejection stand. The baseline's absolute margin is a rev-1 number. |
| `foreign_m2_journal.jsonl` | 1 | Same common-mode argument as R2. |
| `dialect_gap_journal.jsonl` | 1 | The three off-turn-declaration arms. Common-mode again; the arm *gaps* are what the finding rests on. |

## The rule this file exists to enforce

An absolute measured through a bridge is a statement about the bridge as
well as the engines. A paired contrast whose arms share the bridge is not.
When in doubt about a rev-1 number, ask which of those two it is — and if it
is the first, re-measure rather than reprice.
