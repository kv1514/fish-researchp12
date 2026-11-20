// Store screenshots, taken from the real app against a local server. From the
// repo root run
//   python3 scripts4/devserve.py 8420
// and then, from app/:
//   node store/make-screenshots.js               Google Play, 1080x1920
//   FISH_SHOT_OS=ios node store/make-screenshots.js
//                                                App Store, iPhone 6.9" 1320x2868
// FISH_SHOT_W/H change the phone size in CSS pixels; FISH_SHOT_DIR the folder.
const path = require('path');
const fs = require('fs');
const { chromium } = require('playwright');

const BASE = process.env.FISH_URL || 'http://127.0.0.1:8420/play/';
const IOS = process.env.FISH_SHOT_OS === 'ios';
const OUT = process.env.FISH_SHOT_DIR || path.join(__dirname, IOS ? 'ios/screenshots' : 'play/screenshots');
// iPhone 16 Pro Max is 440x956 points at 3x; the Android shots are 9:16.
const W = +(process.env.FISH_SHOT_W || (IOS ? 440 : 432));
const H = +(process.env.FISH_SHOT_H || (IOS ? 956 : 768));
const PX = IOS ? 1320 : 1080;          // width of the saved image
fs.mkdirSync(OUT, { recursive: true });

// Android draws in Roboto, iPhone in SF Pro; Inter is the closest font to
// either that this machine has.
const FONT = `html,body,button,input{font-family:${IOS ? '' : 'Roboto,'}Inter,sans-serif!important}`;

async function phone(browser, name, turn = 90) {
  const ctx = await browser.newContext({
    viewport: { width: W, height: H }, deviceScaleFactor: PX / W, isMobile: true, hasTouch: true,
  });
  await ctx.addInitScript(([n, t]) => {
    localStorage.setItem('fish.guest', 'true');
    localStorage.setItem('fish.name', JSON.stringify(n));
    localStorage.setItem('fish.sound', 'false');
    localStorage.setItem('fish.solo_turn', String(t));
  }, [name, turn]);
  const page = await ctx.newPage();
  page.on('pageerror', (e) => console.log('PAGEERROR', e.message));
  await page.goto(BASE);
  await page.addStyleTag({ content: FONT });
  return page;
}
const shot = (page, file) => page.screenshot({ path: path.join(OUT, file) });
const quiet = (page) => page.evaluate(() => document.querySelectorAll('.toast').forEach((t) => t.remove()));

// One legal ask, the way a person makes it: the first opponent, the first card.
async function ask(page) {
  await page.click('#ask-btn');
  await page.waitForSelector('.sheet .pick[data-seat]');
  await page.click('.sheet .pick[data-seat]');
  await page.click('.sheet .card-grid .card');
  await page.click('#ask-go');
}

(async () => {
  const browser = await chromium.launch();

  // 1. Home
  const p = await phone(browser, 'Kai');
  await p.waitForSelector('#bots-btn');
  await p.waitForTimeout(800);
  await shot(p, '1-home.png');

  // 2-3. A game against the bots, part-way through: Kai asks whenever it is
  // Kai's turn until the table has some history and a set or two is won.
  await p.click('#bots-btn');
  const t0 = Date.now();
  for (let i = 0; i < 40 && Date.now() - t0 < 150000; i++) {
    await p.waitForSelector('#ask-btn, #pass-btn, .result-score', { timeout: 60000 });
    if (await p.$('.result-score')) break;
    const sets = await p.$$eval('.set.us, .set.them', (e) => e.length).catch(() => 0);
    if (i >= 6 && sets >= 2) break;
    if (await p.$('#pass-btn')) { await p.click('#pass-btn'); await p.click('.sheet .pick'); continue; }
    await ask(p);
    await p.waitForTimeout(1500);
  }
  await p.waitForSelector('#ask-btn', { timeout: 60000 });
  await p.waitForTimeout(3500);           // let the last move's animation settle
  await quiet(p);
  await shot(p, '2-table.png');
  await p.click('#ask-btn');
  await p.waitForSelector('.sheet .pick[data-seat]');
  await p.click('.sheet .pick[data-seat]');
  await p.click('.sheet .card-grid .card');
  await p.waitForTimeout(500);
  await quiet(p);
  await shot(p, '3-ask.png');

  // 4. A private table, friends seated, host's timer on show
  const host = await phone(browser, 'Kai');
  await host.waitForSelector('#private-btn');
  await host.click('#private-btn');
  await host.waitForSelector('#cr-go');
  await host.click('#cr-go');
  await host.waitForSelector('.big-code');
  const code = (await host.textContent('.big-code')).trim();
  for (const n of ['Maya', 'Jonah', 'Priya']) {
    const f = await phone(browser, n);
    await f.goto(`${BASE}?join=${code}`);
    await f.waitForTimeout(2500);
  }
  await host.waitForTimeout(3000);
  await quiet(host);
  await shot(host, '4-private-table.png');
  await host.click('#tbl-settings');
  await host.waitForSelector('#ts-bank');
  await host.waitForTimeout(500);
  await shot(host, '5-timer.png');

  // 6. How to play
  const r = await phone(browser, 'Kai');
  await r.waitForSelector('#rules-btn');
  await r.click('#rules-btn');
  await r.waitForTimeout(700);
  await shot(r, '6-rules.png');

  await browser.close();
  console.log('screenshots in', OUT, 'after', Math.round((Date.now() - t0) / 1000), 's');
})().catch((e) => { console.error(e); process.exit(1); });
