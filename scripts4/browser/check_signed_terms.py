"""The negative-term branch, which real openings never reach."""
from playwright.sync_api import sync_playwright

errs = []
with sync_playwright() as pw:
    b = pw.chromium.launch(
        executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    pg = b.new_page(viewport={"width": 900, "height": 700})
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:8421/", wait_until="networkidle")
    out = pg.evaluate("""() => {
      const box = document.createElement('div');
      document.body.appendChild(box);
      renderWhy(box, {target: 3, card_name: 'KH', score: 0.41,
                      p_success: 0.62,
                      terms: {turn: -0.31, suit: 0.12, scarce: -0.02}});
      const rows = [...box.querySelectorAll('.whyrow')].map(r =>
        [...r.querySelectorAll('span')].map(s => s.innerText.trim()).join(' | '));
      const track = box.querySelector('.whytrack');
      const bars = [...box.querySelectorAll('.whybar')].map(x => {
        const t = x.parentElement.getBoundingClientRect();
        const r = x.getBoundingClientRect();
        return {cls: x.className, w: Math.round(r.width),
                leftOfCentre: Math.round(r.left + r.width) <= Math.round(t.left + t.width/2) + 1,
                rightOfCentre: Math.round(r.left) >= Math.round(t.left + t.width/2) - 1};
      });
      const cs = getComputedStyle(track, '::before');
      return {rows, bars, signed: track.classList.contains('signed'),
              centreLine: cs.content !== 'none'};
    }""")
    for r in out["rows"]:
        print("  ", r)
    print("signed layout:", out["signed"], "| centre line drawn:", out["centreLine"])
    for bar in out["bars"]:
        print("  ", bar)
    pos = [x for x in out["bars"] if "pos" in x["cls"]]
    neg = [x for x in out["bars"] if "neg" in x["cls"]]
    print("positives all right of centre:", all(x["rightOfCentre"] for x in pos))
    print("negatives all left of centre :", all(x["leftOfCentre"] for x in neg))
    print("ordered by magnitude         :",
          out["rows"][0].startswith("lands"))
    b.close()
print("JS errors:", errs or "none")
