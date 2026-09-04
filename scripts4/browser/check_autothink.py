"""The auto toggle must actually save the click, not just exist.

The two worst UI bugs in this project were both a control that was present and
did nothing, so the assertion here is behavioural: with `auto` on and WITHOUT
touching Think, the posterior panel appears on our turn. Then it must survive a
reload, because the toggle claims to be remembered.
"""
from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8433/"
errors = []


def to_our_turn(pg, tries=40):
    for _ in range(tries):
        turn = (pg.query_selector("#t-turn").inner_text() or "").lower()
        if "your" in turn:
            return True
        n = pg.query_selector("#t-next")
        if n:
            try:
                n.click()
            except Exception:
                pass
        pg.wait_for_timeout(700)
    return False


with sync_playwright() as pw:
    b = pw.chromium.launch(
        executable_path="/opt/pw-browsers/chromium-1194/chrome-linux/chrome")
    pg = b.new_page(viewport={"width": 1100, "height": 1000})
    pg.on("console", lambda m: errors.append(f"console.error: {m.text}")
          if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    pg.goto(URL, wait_until="networkidle")

    box = pg.query_selector("#t-auto")
    print("toggle present on the start screen's table bar:", bool(box))

    pg.click("#s-seat button[data-v='0']")
    pg.click("#s-go")
    pg.wait_for_selector("#table.on", timeout=30000)
    try:
        pg.select_option("#t-pace", index=0)
    except Exception:
        pass

    print("default state (should be unchecked):",
          pg.is_checked("#t-auto"))

    ok = to_our_turn(pg)
    print("reached our turn:", ok)
    print("posterior panel hidden before the toggle:",
          pg.query_selector("#t-postpanel").get_attribute("hidden") is not None)

    pg.check("#t-auto")
    pg.wait_for_timeout(9000)
    hidden = pg.query_selector("#t-postpanel").get_attribute("hidden")
    print("posterior panel visible after toggling, WITHOUT clicking Think:",
          hidden is None)
    rows = pg.query_selector_all("#t-post .postrow")
    print("  per-card rows rendered:", len(rows))

    # it must not fire again and again on the same position
    before = len(pg.query_selector_all("#t-post .postrow"))
    pg.wait_for_timeout(4000)
    after = len(pg.query_selector_all("#t-post .postrow"))
    print("stable across 4s (no refetch loop):", before == after)

    pg.reload(wait_until="networkidle")
    print("remembered after reload:", pg.is_checked("#t-auto"))

    print("console/page errors:", errors or "none")
    b.close()
