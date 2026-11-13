"""Play a real game in a real browser: every control, and the declare dialog."""
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

    def turn_text():
        el = pg.query_selector("#t-turn")
        return (el.inner_text() if el else "").lower()

    moves = 0
    for _ in range(60):
        t = turn_text()
        if "your" in t:
            # take a turn via the engine's own suggestion
            btn = pg.query_selector("button:has-text('Let the engine move')")
            if btn:
                btn.click()
                moves += 1
                pg.wait_for_timeout(900)
                continue
        n = pg.query_selector("#t-next")
        if n:
            try:
                n.click()
            except Exception:
                pass
        pg.wait_for_timeout(500)
        if pg.query_selector("#t-us") and moves > 12:
            break

    us = pg.query_selector("#t-us").inner_text()
    them = pg.query_selector("#t-them").inner_text()
    void = (pg.query_selector("#t-void").inner_text() or "").strip()
    print(f"after {moves} engine-assisted turns:  us={us} them={them} "
          f"void={void or '(none)'}")

    log = pg.query_selector_all(".logrow")
    print("move log entries:", len(log))
    last = pg.query_selector(".lastmove")
    print("last-move panel non-empty:", bool(last and last.inner_text().strip()))

    # the declare dialog
    for _ in range(30):
        if "your" in turn_text():
            break
        n = pg.query_selector("#t-next")
        if n:
            try: n.click()
            except Exception: pass
        pg.wait_for_timeout(500)
    d = pg.query_selector("button:has-text('Declare a set')")
    print("declare button present:", bool(d))
    if d:
        d.click()
        pg.wait_for_timeout(1500)
        rows = pg.query_selector_all(".declrow")
        verdict = pg.query_selector(".declverdict")
        sel = pg.query_selector_all(".declrow select")
        chosen = [s.evaluate("e => e.options[e.selectedIndex]?.text || ''")
                  for s in sel]
        print(f"declare rows: {len(rows)} | verdict shown: "
              f"{bool(verdict and verdict.inner_text().strip())}")
        print("pre-selected holders:", chosen[:6])
        allme = all("you" in c.lower() for c in chosen) if chosen else False
        print("every card defaulted to YOU (the old bug):", allme)
        pcts = sum(1 for c in chosen if "%" in c)
        print(f"options carry probabilities: {pcts}/{len(chosen)}")
    pg.screenshot(path="/tmp/claude-0/-home-user-fish-researchp12/"
                       "993de2cf-d12a-5e1b-8404-c20bdce05164/scratchpad/game.png",
                  full_page=True)
    b.close()
print("\nJS errors:", errs or "none")
