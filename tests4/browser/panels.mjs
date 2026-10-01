/* Do the end-of-game panels actually paint in a real browser?
 *
 * tests4/js/ drives app.js against a DOM stub, which is fast and covers the
 * logic. What it cannot cover is the real DOM: appendChild ordering, an
 * innerHTML setter that really clears children, CSS that might hide a panel
 * the stub happily "rendered". Two earlier attempts at this played a whole
 * game through the live engine and timed out at 180s under load, which tested
 * the engine's speed rather than the page.
 *
 * So the engine is not in the loop at all. /api/new is intercepted and
 * answered with a finished game, and the page walks its own real code path
 * from the start screen to the three panels.
 */
import { createRequire } from 'module';
// playwright is installed globally here, not in the repo, and NODE_PATH does
// not apply to ESM resolution. createRequire rooted at the global tree finds
// the CJS package without adding a dependency to the project.
const require = createRequire('/opt/node22/lib/node_modules/');
const { chromium } = require('playwright');

const BASE = process.env.BASE || 'http://127.0.0.1:8931';
const CARDS = ['2S', '3S', '4S', '5S', '6S', '7S'];
const hs = (i) => ({
  index: i,
  name: 'half suit ' + i,
  cards: CARDS.map((n, k) => ({ id: i * 6 + k, name: n, red: false, mine: false })),
});
const claim = (claimer, h, winner, klass, declared, revealed) => ({
  t: 'claim', claimer, hs: h, winner, klass, declared, revealed,
  text: `P${claimer} declared ${h}`,
});

const FINISHED = {
  token: 'tok', seat: 0, team: 0, turn: 0, terminal: true, your_turn: false,
  must_pass: false, actions: [],
  score: { you: 5, them: 4, nulled: 0 },
  hand_counts: [0, 0, 0, 0, 0, 0],
  teammates: [2, 4],
  set_winner: ['ours', 'theirs', 'ours', 'ours', 'theirs', 'ours', 'theirs', 'ours', 'theirs'],
  half_suits: Array.from({ length: 9 }, (_, i) => hs(i)),
  hand: [], log: [],
  reveal: [[], [], [], [], [], []],
  ask_tally: [[40, 12], [30, 20], [10, 5], [9, 4], [8, 3], [7, 2]],
  declarations: [
    claim(0, 0, 0, 'right', [0, 0, 2, 2, 4, 4], [0, 0, 2, 2, 4, 4]),
    claim(2, 1, 1, 'split', [0, 0, 2, 2, 4, 4], [0, 0, 2, 4, 2, 4]),
    claim(1, 2, 0, 'ownership', [1, 1, 3, 3, 5, 5], [1, 1, 3, 3, 5, 0]),
  ],
};

const page = await (await chromium.launch()).newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(String(e)));
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });

await page.route('**/api/**', (route) => route.fulfill({
  status: 200, contentType: 'application/json', body: JSON.stringify(FINISHED),
}));

await page.goto(BASE + '/index.html', { waitUntil: 'domcontentloaded' });
await page.click('#s-go');
await page.waitForSelector('#t-action .ledger', { timeout: 20000 });

const text = await page.textContent('#t-action');
const fail = [];
const want = [
  [/Every declaration in this game/, 'the ledger heading'],
  [/half suit 0/, 'the first declaration (the log tail would have dropped it)'],
  [/half suit 1/, 'the second'],
  [/half suit 2/, 'the third'],
  [/wrong split/, 'the allocation-class verdict'],
  [/still held one/, 'the ownership-class verdict'],
  [/Your declaration record/, 'the running record'],
  [/Your asks/, 'the ask record'],
  [/asked 40 times and got 12/, "this game's ask tally at OUR seat"],
  [/Across 1 game: 12 of 40/, 'the cumulative ask line'],
  [/outside your interval/, 'the verdict against the engine rate'],
  [/58%/, 'the sentence saying one game is mostly noise'],
];
for (const [re, what] of want) if (!re.test(text)) fail.push('missing: ' + what);
if (/asked 30 times/.test(text)) fail.push("an opponent's asks were shown as ours");

/* Painted, not merely present: a panel behind display:none is not a panel. */
for (const sel of ['#t-action .ledger', '#t-action h4']) {
  const box = await page.locator(sel).first().boundingBox();
  if (!box || box.width < 40 || box.height < 8) {
    fail.push(`${sel} has no painted box (${JSON.stringify(box)})`);
  }
}
/* And the page must not scroll sideways at a phone width. */
await page.setViewportSize({ width: 390, height: 844 });
await page.waitForTimeout(300);
const over = await page.evaluate(
  () => document.documentElement.scrollWidth - document.documentElement.clientWidth);
if (over > 2) fail.push(`horizontal overflow of ${over}px at 390px wide`);

if (errors.length) fail.push('page errors: ' + errors.join(' | '));
console.log(fail.length ? 'FAIL\n  ' + fail.join('\n  ')
  : 'ok - ledger, declaration record and ask record all paint in Chromium, '
    + 'no page errors, no sideways scroll at 390px');
process.exit(fail.length ? 1 : 0);
