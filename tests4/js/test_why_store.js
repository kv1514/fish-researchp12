/* The trace store, and the bug that a screenshot found and no unit test could.
 *
 * The server sends a trace only for moves generated in the CURRENT request --
 * right on the wire, because a replayed move was not decided again. But
 * without a client-side store exactly one row of the log carries an
 * explanation and every earlier one goes bare as it scrolls, which reads like
 * the feature is broken.
 *
 * The store fixes that, and its own first version was broken in a way only a
 * live page showed: absorbWhy() was spliced into an animation callback rather
 * than into render(), so a trace was absorbed a beat late and the NEWEST move
 * -- the one a viewer is actually looking at -- was always the unexplained
 * one. Driving the real page found it; these keep it found.
 */
const assert = require("assert");
const { load } = require("./harness");

const { ctx } = load();
const S = ctx.__S;

const TR = (seat) => ({
  kind: "ask", n_legal: 40, tie_group: 1, seat,
  ranked: [{ rank: 0, target: 0, card: "JS", half_suit: "High Spades",
             score: 0.4, p_hit: 0.5, chosen: true }],
  chosen: { target: 0, card: "JS" },
});

/* --- the wire index addresses the SLICE; the store must key absolutely --- */

S.why = {};
S.actions = new Array(70);                 // 70 actions played
S.snap = { log: new Array(60), why: { "59": TR(1) } };   // only 60 sent
ctx.__absorbWhy();
assert.ok(S.why[69], "a trace on the last sent row is action 69, not 59");
assert.strictEqual(S.why[59], undefined,
  "storing under the slice index would misattribute it by the trim amount");
assert.ok(ctx.__whyAt(59), "and it must read back at the same slice index");

/* --- accumulation across requests: earlier rows keep their reasoning --- */

S.why = {};
S.actions = new Array(3);
S.snap = { log: new Array(3), why: { "1": TR(1) } };
ctx.__absorbWhy();
S.actions = new Array(4);
S.snap = { log: new Array(4), why: { "3": TR(3) } };      // a later request
ctx.__absorbWhy();
assert.ok(ctx.__whyAt(1), "the earlier move lost its explanation");
assert.ok(ctx.__whyAt(3), "the newest move has no explanation");
assert.strictEqual(ctx.__whyAt(0), null, "invented an explanation for a gap");
assert.strictEqual(ctx.__whyAt(2), null, "invented an explanation for a gap");

/* --- absorbing is idempotent, since render() runs many times per move --- */

const before = JSON.stringify(S.why);
ctx.__absorbWhy();
ctx.__absorbWhy();
assert.strictEqual(JSON.stringify(S.why), before, "re-absorbing changed state");

/* --- a snapshot with no why map must not throw or wipe the store --- */

S.snap = { log: new Array(4) };
ctx.__absorbWhy();
assert.ok(ctx.__whyAt(1), "a why-less response wiped earlier traces");

console.log("ok - the trace store keys absolutely and accumulates");
