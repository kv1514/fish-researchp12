// Draws every Android icon, the launch-screen emblem and the Google Play
// graphics from one source: public/play/icon-square.svg. Run from app/:
//   node store/make-assets.js
// Needs Playwright's Chromium (the CI image and dev containers have it).
const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const APP = path.join(__dirname, '..');
const RES = path.join(APP, 'android/app/src/main/res');
const OUT = path.join(__dirname, 'play');
const src = fs.readFileSync(path.join(APP, '../public/play/icon-square.svg'), 'utf8');

// The parts of the icon: its gradients, its square background, and the
// emblem (felt circle and cards) drawn on top of it.
const defs = src.match(/<defs>[\s\S]*?<\/defs>/)[0];
const body = src.replace(/^[\s\S]*?<\/defs>/, '').replace(/<\/svg>\s*$/, '');
const bgRect = '<rect width="512" height="512" fill="url(#bg)"/>';
const emblem = body.replace(bgRect, '');
if (emblem === body) throw new Error('icon-square.svg changed shape: no background rect');

const svg = (inner, extra = '') =>
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" ${extra}>${defs}${inner}</svg>`;
// The emblem alone, centred, at `scale` of its drawn size (the felt circle is
// centred at 256,262 in the source).
const emblemAt = (scale) =>
  `<g transform="translate(256 256) scale(${scale}) translate(-256 -262)">${emblem}</g>`;

const DENSITIES = { mdpi: 1, hdpi: 1.5, xhdpi: 2, xxhdpi: 3, xxxhdpi: 4 };

async function render(page, markup, w, h, file, transparent = true) {
  await page.setViewportSize({ width: w, height: h });
  await page.setContent(`<html><body style="margin:0;background:transparent">${markup}</body></html>`);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  await page.screenshot({ path: file, omitBackground: transparent, clip: { x: 0, y: 0, width: w, height: h } });
}
const sized = (s, w, h) => s.replace('<svg ', `<svg width="${w}" height="${h}" style="display:block" `);

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  for (const [d, k] of Object.entries(DENSITIES)) {
    // Android 8+ adaptive icon: the emblem inside the 66dp safe circle of a
    // 108dp layer, so no launcher mask can clip the felt.
    const fg = Math.round(108 * k);
    await render(page, sized(svg(emblemAt(0.79)), fg, fg), fg, fg,
      path.join(RES, `mipmap-${d}/ic_launcher_foreground.png`));
    // Older launchers: the whole square icon, rounded, and a round one.
    const n = Math.round(48 * k);
    await render(page, `<div style="width:${n}px;height:${n}px;border-radius:${n * 0.18}px;overflow:hidden">${sized(src, n, n)}</div>`,
      n, n, path.join(RES, `mipmap-${d}/ic_launcher.png`));
    await render(page, `<div style="width:${n}px;height:${n}px;border-radius:50%;overflow:hidden">${sized(src, n, n)}</div>`,
      n, n, path.join(RES, `mipmap-${d}/ic_launcher_round.png`));
  }
  // The launch screen's emblem (older Android; 12+ shows the app icon).
  await render(page, sized(svg(emblemAt(1.0)), 480, 480), 480, 480,
    path.join(RES, 'drawable-nodpi/fish_emblem.png'));

  // Google Play: the 512px store icon (Play rounds the corners itself) ...
  await render(page, sized(src, 512, 512), 512, 512, path.join(OUT, 'icon-512.png'), false);
  // ... and the 1024x500 feature graphic.
  const feature = `
    <div style="width:1024px;height:500px;position:relative;overflow:hidden;
      background:radial-gradient(120% 140% at 30% 40%, #13305a 0%, #0a1426 55%, #060a14 100%);
      font-family:Inter, system-ui, sans-serif;color:#fff">
      <div style="position:absolute;left:60px;top:50px">${sized(svg(emblemAt(1.0)), 400, 400)}</div>
      <div style="position:absolute;left:500px;top:120px;width:480px">
        <div style="font-weight:900;font-size:148px;letter-spacing:22px;line-height:1">FISH</div>
        <div style="margin-top:22px;font-size:34px;font-weight:600;color:#9fb3d1">The team card game · 3 vs 3</div>
        <div style="margin-top:26px;font-size:26px;font-weight:500;color:#38bdf8">Ask. Remember. Declare.</div>
      </div>
    </div>`;
  await render(page, feature, 1024, 500, path.join(OUT, 'feature-graphic.png'), false);
  await browser.close();
  console.log('assets written');
})().catch((e) => { console.error(e); process.exit(1); });
