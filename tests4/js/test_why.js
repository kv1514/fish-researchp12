/* The engine's reasoning, rendered honestly.
 *
 * The failure this pins is not a crash. A panel that says "the engine picked
 * 5C because it scored highest" when four candidates tied and the pick was
 * random is a page telling a confident lie about its own engine, and it looks
 * completely fine. So the tie case is tested first and hardest.
 *
 * The payload shapes here are copied from real traces produced by
 * fish4/trace.py, not invented.
 */
const assert = require("assert");
const { load } = require("./harness");

const { ctx } = load();

const S = ctx.__S;

/* This suite is about the WORDING, so it calls the formatter directly. Where
   the trace comes from -- the wire, or the client-side store that keeps it as
   the row scrolls -- is test_why_store.js's job. */
const whyText = ctx.__whyText;

/* ------------------------------------------------------------------ ties */

const TIED = {
  kind: "ask", n_legal: 81, tie_group: 4, seat: 1,
  margin: 0,
  ranked: [
    { rank: 0, target: 1, card: "8H", half_suit: "Specials (8s+Jokers)",
      score: 0.4723, p_hit: 0.2, chosen: false },
    { rank: 1, target: 3, card: "8H", half_suit: "Specials (8s+Jokers)",
      score: 0.4723, p_hit: 0.2, chosen: false },
    { rank: 2, target: 1, card: "RJ", half_suit: "Specials (8s+Jokers)",
      score: 0.4723, p_hit: 0.2, chosen: true },
    { rank: 3, target: 3, card: "RJ", half_suit: "Specials (8s+Jokers)",
      score: 0.4723, p_hit: 0.2, chosen: false },
  ],
  chosen: { target: 1, card: "RJ" },
};

const CLEAR = {
  kind: "ask", n_legal: 117, tie_group: 1, seat: 1, margin: 0.0038,
  ranked: [
    { rank: 0, target: 0, card: "JS", half_suit: "High Spades",
      score: 0.4677, p_hit: 0.3813, chosen: true },
    { rank: 1, target: 0, card: "9S", half_suit: "High Spades",
      score: 0.4639, p_hit: 0.2281, chosen: false },
  ],
  chosen: { target: 0, card: "JS" },
};

const t = whyText(TIED);

assert.ok(/picked at random/.test(t),
  "a tie must be reported as a tie, not dressed up as a preference: " + t);
assert.ok(/tied with 3 others/.test(t), "wrong tie count: " + t);
assert.ok(/20%/.test(t), "the chosen ask's own odds should be shown: " + t);
assert.ok(!/next best/.test(t),
  "there is no 'next best' inside a tie group: " + t);

/* The number quoted must belong to the ask that HAPPENED (rank 2 here), not
   to rank 0. Both are 20% in this fixture, so re-check with them differing. */
const TIED_DIFF = JSON.parse(JSON.stringify(TIED));
TIED_DIFF.ranked[0].p_hit = 0.91;
assert.ok(/20%/.test(whyText(TIED_DIFF)),
  "quoted the top row's odds instead of the chosen row's: "
  + whyText(TIED_DIFF));

/* ------------------------------------------------------------- no tie */

const c = whyText(CLEAR);
assert.ok(/38%/.test(c), "chosen ask's odds missing: " + c);
assert.ok(/next best/.test(c), "the runner-up is the comparison people want: " + c);
assert.ok(/9S/.test(c), "runner-up card missing: " + c);
assert.ok(/23%/.test(c), "runner-up odds missing: " + c);
assert.ok(!/at random/.test(c), "a clear winner is not a coin flip: " + c);
assert.ok(/117 legal asks/.test(c), "breadth of choice missing: " + c);

/* -------------------------------------------------------- other kinds */

const decl = whyText({ kind: "declare", why: "voluntary", confidence: 0.9642,
  seat: 1, half_suit: "Low Clubs", split: [] });
assert.ok(/chose to declare/.test(decl), decl);
assert.ok(/96%/.test(decl), "declaration confidence missing: " + decl);

const forced = whyText({ kind: "declare", why: "forced: no legal ask",
  confidence: 0.41, seat: 1, half_suit: "Low Clubs", split: [] });
assert.ok(/forced to declare/.test(forced), forced);
assert.ok(/41%/.test(forced),
  "a forced declaration's low confidence is the whole point: " + forced);

assert.ok(/solved exactly/.test(whyText({ kind: "exact", seat: 1 })));
assert.ok(/deliberately dead/.test(whyText({ kind: "signal", seat: 1 })));

/* ------------------------------------------------------------- absence */

assert.strictEqual(whyText(null), null, "an absent trace must render nothing");
assert.strictEqual(
  whyText({ kind: "ask", n_legal: 5, tie_group: 1, ranked: [] }), null,
  "an empty ranking must render nothing");

/* And the lookup path: no store, no reasoning -- never an invented one. */
S.why = {};
S.actions = new Array(3);
S.snap = { log: new Array(3) };
assert.strictEqual(ctx.__whyAt(0), null, "an untraced move must render nothing");

console.log("ok - engine reasoning renders honestly");
