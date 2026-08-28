/* The declare dialog must not open on the answer.
 *
 * This dialog has now been wrong twice in opposite directions. First it
 * defaulted every unheld card to the lowest team seat -- for seat 0, to YOU --
 * so declaring without touching all six threw the set away. The fix opened it
 * on the engine's posterior MAP with the engine's marginal printed beside
 * every option, which cured that and replaced it with a dialog that plays for
 * you: you can score a set having reasoned about nothing.
 *
 * So there are two properties to pin, and they pull against each other:
 *   - nothing is pre-filled except cards you can SEE in your own hand, and no
 *     probability appears anywhere before you ask for one;
 *   - you cannot declare a half-built split.
 *
 * The harness's querySelectorAll walks the real child list, which matters
 * here: a stub returning [] would make "every card is assigned" vacuously
 * true and this file would pass on a broken dialog.
 */
const assert = require("assert");
const { load } = require("./harness");

/* app.js's el() writes labels through innerHTML, not textContent. */
const txt = (n) => String((n && (n.innerHTML || n.textContent)) || "");
const deep = (n) => JSON.stringify(n, (k, v) => (k === "_l" ? undefined : v));

const { ctx, replies, calls, get } = load();
const S = ctx.__S;

const CARDS = ["2S", "3S", "4S", "5S", "6S", "7S"];
S.snap = {
  seat: 0,
  teammates: [2, 4],
  set_winner: [null, null, null, null, null, null, null, null, null],
  half_suits: Array.from({ length: 9 }, (_, i) => ({
    name: "half suit " + i,
    cards: CARDS.map((n, k) => ({ id: i * 6 + k, name: n, mine: false })),
  })),
};
S.names = {};

/* openModal builds into #t-modalbox, so that node IS the dialog. */
async function open() {
  await ctx.__openDeclare();
  return get("t-modalbox");
}

(async () => {
  const b = await open();
  assert.ok(b, "openDeclare did not build a dialog");

  const selects = b.querySelectorAll("select");
  // one half-suit picker + six card assignments
  assert.strictEqual(selects.length, 7,
    `expected 7 selects (1 picker + 6 cards), got ${selects.length}`);

  const picker = selects[0];
  const cardSels = selects.slice(1);

  /* --- 1. nothing is pre-filled --- */
  for (const s of cardSels) {
    assert.strictEqual(s.value, "",
      "a card assignment was pre-filled; the dialog is answering for the "
      + "player again");
  }

  /* --- 2. no probability is on screen before the player asks --- */
  const text = deep(b);
  assert.ok(!/%/.test(text),
    "a percentage appeared in the dialog before any check was requested");

  /* --- 3. the half-suit picker no longer leaks the engine's confidence --- */
  for (const o of picker.children) {
    const t = txt(o);
    assert.ok(!/engine|%/i.test(t),
      `the set picker still shows the engine's answer: ${t}`);
  }

  /* --- 4. the check asks the server about the SPLIT THAT WAS BUILT --- */
  cardSels.forEach((s, k) => { s.value = String([0, 2, 4][k % 3]); });
  const want = cardSels.map((s) => +s.value);
  replies.push({ half_suit: 0, assignment: want, p_exact: 0.12,
                 p_team: 0.83,
                 engine: { p_exact: 0.44, assignment: [0, 0, 2, 2, 4, 4],
                           same: false } });
  const buttons = b.querySelectorAll("button");
  const check = buttons.find((x) => /check/i.test(txt(x)));
  assert.ok(check, "no check button");
  await check.onclick();

  const sent = calls[calls.length - 1];
  assert.deepStrictEqual(sent.body.assignment, want,
    "the check sent something other than the player's own split");
  assert.strictEqual(sent.body.half_suit, 0);

  /* --- 5. and only now does the engine's split appear --- */
  const after = deep(b);
  assert.ok(/83%/.test(after), "p_team was not shown after the check");
  assert.ok(/12%/.test(after), "the player's own split was not priced");
  assert.ok(/44%/.test(after), "the engine's figure was not revealed");

  console.log("ok - declare dialog asks before it answers");
})().catch((e) => { console.error(e); process.exit(1); });
