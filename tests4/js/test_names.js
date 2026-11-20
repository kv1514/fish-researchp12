/* Seat names, and the two ways a name can be worse than no name at all.
 *
 * The table used to read "P0 … P5". Names make it readable, and they introduce
 * a problem a number does not have: two seats can be made to LOOK like each
 * other. A player identifies who asked them for a card by the label on the
 * seat, so a name that can impersonate another name is a gameplay problem and
 * not a cosmetic one.
 *
 * Every invisible character below is written as an escape rather than pasted,
 * so the test source says what it is testing. A file containing the literal
 * characters would be a file nobody can review.
 */
const assert = require("assert");
const { load } = require("./harness");

const { ctx } = load();
const FN = ctx.window.FishNames;

const ZWSP = "​";        // zero-width space
const RLO = "‮";         // right-to-left override
const ZWJ = "‍";         // zero-width joiner
const BOM = "﻿";         // zero-width no-break space

/* ------------------------------------------------------------------ clean */

// Invisible characters are stripped, not merely trimmed. A zero-width space
// between two letters renders as nothing, so "Ma<ZWSP>rlin" and "Marlin" are
// the same label to a reader and different strings to everything else -- which
// is how you sit down at a table as somebody who is already at it.
assert.strictEqual(FN.clean("Ma" + ZWSP + "rlin"), "Marlin",
  "zero-width space survived");
assert.strictEqual(FN.clean("Nori" + RLO), "Nori", "bidi override survived");
assert.strictEqual(FN.clean("Co" + ZWJ + "ral"), "Coral", "ZWJ survived");
assert.strictEqual(FN.clean(BOM + "Tide"), "Tide", "BOM survived");
assert.strictEqual(FN.clean("ab"), "ab", "control character survived");

// Whitespace collapses, so padding cannot be used to make two names align
// differently while reading identically.
assert.strictEqual(FN.clean("  Coral   Reef  "), "Coral Reef");
assert.strictEqual(FN.clean("   "), "", "all-space name must come back empty");
assert.strictEqual(FN.clean(null), "");
assert.strictEqual(FN.clean(undefined), "");

// Length is capped, and the cap is applied AFTER cleaning -- otherwise a name
// padded past the cap with zero-width characters would be truncated to
// something shorter than the visible limit, and two different names could cap
// to the same visible string.
const long = FN.clean("x".repeat(200));
assert.strictEqual(long.length, FN.MAX, `cap is ${FN.MAX}`);
const padded = FN.clean(ZWSP.repeat(50) + "y".repeat(200));
assert.strictEqual(padded.length, FN.MAX,
  "cleaning must precede the length cap");

/* ---------------------------------------------------------------- display */

// An unnamed seat never renders empty: it falls back to a default, and the
// viewer's own seat falls back to "You".
assert.strictEqual(FN.display([], 2, 0, 2), FN.BOTS[2 % FN.BOTS.length]);
assert.strictEqual(FN.display([], 0, 0, 0), "You");
assert.strictEqual(FN.display(["  "], 0, 0, 0), "You",
  "a whitespace name must fall back, not render blank");
assert.strictEqual(FN.display(["Ada"], 0, 0, 0), "Ada");

// A name that cleans to nothing must fall back too, not render the raw value.
assert.strictEqual(FN.display([ZWSP + ZWSP], 0, 0, 0), "You");

// A seat past the end of the defaults still gets a label rather than
// undefined -- six seats against five bot defaults is the real case.
const far = FN.display([], 5, 0, 99);
assert.ok(far && far.length, "no label for a seat past the defaults");

/* ----------------------------------------------------------- soloDefaults */

const d = FN.soloDefaults(3, "Kavin");
assert.strictEqual(d.length, 6);
assert.strictEqual(d[3], "Kavin", "the human's seat takes the human's name");
// The other five are distinct, which is the property that makes the table
// readable. Five identical names would be worse than P0..P5.
const bots = d.filter((_, i) => i !== 3);
assert.strictEqual(new Set(bots).size, 5, "bot names must be distinct");
// And distinct at EVERY seat, not just seat 3 -- the defaults are laid out
// relative to where the human sits.
for (let seat = 0; seat < 6; seat++) {
  const row = FN.soloDefaults(seat, "Me");
  const others = row.filter((_, i) => i !== seat);
  assert.strictEqual(new Set(others).size, 5,
    `duplicate bot name with the human at seat ${seat}`);
}

// An empty human name still yields a usable label.
assert.strictEqual(FN.soloDefaults(0, "")[0], "You");
assert.strictEqual(FN.soloDefaults(0, "   ")[0], "You");

/* -------------------------------------------------------------- initials */

assert.strictEqual(FN.initials("Marlin"), "Ma");
assert.strictEqual(FN.initials("Coral Reef"), "CR");
assert.strictEqual(FN.initials(""), "?", "initials must never come back empty");
assert.strictEqual(FN.initials("   "), "?");
assert.strictEqual(FN.initials(ZWSP), "?");
// Two characters at most: three does not fit the puck and one is ambiguous
// across six seats.
assert.ok(FN.initials("Alexandria Ocasio").length <= 2);

console.log("ok - names");
