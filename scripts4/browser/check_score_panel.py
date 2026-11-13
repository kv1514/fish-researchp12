"""Actually click the thing. A rendering bug is not visible from the source."""
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8421/"
errors = []

with sync_playwright() as pw:
    b = pw.chromium.launch(
        executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    pg = b.new_page(viewport={"width": 1100, "height": 1000})
    pg.on("console", lambda m: errors.append(f"console.error: {m.text}")
          if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    pg.goto(URL, wait_until="networkidle")

    pg.click("#s-seat button[data-v='0']")
    pg.click("#s-go")
    pg.wait_for_selector("#table.on", timeout=30000)
    # fastest pace so the table does not sit waiting
    try:
        pg.select_option("#t-pace", index=0)
    except Exception:
        pass

    # drive to our turn
    for _ in range(40):
        turn = (pg.query_selector("#t-turn").inner_text() or "").lower()
        if "your" in turn or "you " in turn:
            break
        n = pg.query_selector("#t-next")
        if n:
            try:
                n.click()
            except Exception:
                pass
        pg.wait_for_timeout(700)
    print("turn line:", (pg.query_selector("#t-turn").inner_text() or "")[:80])

    pg.click("#t-think")
    pg.wait_for_timeout(6000)

    ht = pg.query_selector(".hinttable")
    why = pg.query_selector(".why")
    print("hint table present:", bool(ht), "| why panel present:", bool(why))
    if why:
        rows = pg.query_selector_all(".whyrow")
        print(f"why rows: {len(rows)}")
        for r in rows[:9]:
            spans = [x.inner_text().strip()
                     for x in r.query_selector_all("span")]
            print("   ", " | ".join(x for x in spans if x))
        bars = pg.query_selector_all(".whybar")
        w = [round(x.evaluate("e => e.getBoundingClientRect().width"), 1)
             for x in bars]
        print("bar widths:", w)
        print("all bars visible:", all(x > 0 for x in w))
        body = [t for t in pg.query_selector_all(".hinttable tr")
                if t.query_selector("td")]
        print("clickable ask rows:", len(body))
        if len(body) > 1:
            before = pg.query_selector(".why").inner_text()
            body[1].click()
            pg.wait_for_timeout(400)
            after = pg.query_selector(".why").inner_text()
            print("clicking a second ask changed the panel:", before != after)
            sel = pg.query_selector_all(".hinttable tr.sel")
            print("exactly one row highlighted:", len(sel) == 1)
    pg.screenshot(path="/tmp/claude-0/-home-user-fish-researchp12/"
                       "993de2cf-d12a-5e1b-8404-c20bdce05164/scratchpad/table.png",
                  full_page=True)
    b.close()

print("\nJS errors:", errors or "none")
