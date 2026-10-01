"""Open the declare dialog early and check what it pre-selects.

The bug this guards was not a crash: the team list is sorted, so seat 0 came
first in every dropdown, every card the human did not hold silently defaulted to
THEM, and declaring without changing all six voided the set. A test that only
checks the dialog opens would have passed.
"""
from playwright.sync_api import sync_playwright

errs = []
with sync_playwright() as pw:
    b = pw.chromium.launch(
        executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    pg = b.new_page(viewport={"width": 1180, "height": 1100})
    pg.on("console", lambda m: errs.append(f"console.error: {m.text}")
          if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append(f"pageerror: {e}"))
    pg.goto("http://127.0.0.1:8455/", wait_until="networkidle")
    pg.click("#s-seat button[data-v='0']")
    pg.click("#s-go")
    pg.wait_for_selector("#table.on", timeout=30000)
    try:
        pg.select_option("#t-pace", index=0)
    except Exception:
        pass

    for _ in range(40):
        t = (pg.query_selector("#t-turn").inner_text() or "").lower()
        if "your" in t:
            break
        n = pg.query_selector("#t-next")
        if n:
            try: n.click()
            except Exception: pass
        pg.wait_for_timeout(400)
    print("turn:", (pg.query_selector("#t-turn").inner_text() or "")[:40])

    d = pg.query_selector("button:has-text('Declare a set')")
    print("declare button present:", bool(d))
    if not d:
        b.close(); raise SystemExit("could not reach a human turn")
    d.click()
    pg.wait_for_timeout(2500)

    rows = pg.query_selector_all(".declrow")
    verdict = pg.query_selector(".declverdict")
    sel = pg.query_selector_all(".declrow select")
    chosen = [s.evaluate("e => e.options[e.selectedIndex]?.text || ''") for s in sel]
    print(f"declare rows: {len(rows)}   selects: {len(sel)}")
    print("verdict line:", (verdict.inner_text().strip()[:90] if verdict else "(none)"))
    for c in chosen:
        print("   pre-selected:", c)
    if chosen:
        me = sum(1 for c in chosen if "you" in c.lower())
        print(f"defaulted to YOU: {me}/{len(chosen)}"
              f"   (all six would be the old guaranteed-void bug)")
        print("options carry probabilities:",
              sum(1 for c in chosen if "%" in c), "/", len(chosen))
        opts = sel[0].evaluate("e => [...e.options].map(o => o.text)")
        print("first dropdown offers:", opts)
    pg.screenshot(path="/tmp/claude-0/-home-user-fish-researchp12/"
                       "993de2cf-d12a-5e1b-8404-c20bdce05164/scratchpad/declare.png",
                  full_page=True)
    b.close()
print("\nJS errors:", errs or "none")
