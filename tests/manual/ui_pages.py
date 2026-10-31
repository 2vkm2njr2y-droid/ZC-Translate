import json
from playwright.sync_api import sync_playwright

url = "http://127.0.0.1:8011/?token=test-ui"
errors = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.on("console", lambda msg: errors.append(f"console:{msg.type}:{msg.text}") if msg.type == "error" else None)
    page.on("pageerror", lambda exc: errors.append(f"pageerror:{exc}"))
    page.goto(url, wait_until="networkidle")
    page.wait_for_selector(".translate-page", timeout=15000)
    page.locator("#nav button", has_text="设置").click()
    page.wait_for_selector(".model-card", timeout=15000)
    page.wait_for_timeout(500)
    page.screenshot(path="data/ui-settings.png", full_page=True)
    page.get_by_role("button", name="运行诊断").click()
    page.wait_for_selector(".check-row", timeout=30000)
    page.wait_for_timeout(300)
    page.screenshot(path="data/ui-doctor.png", full_page=True)
    page.locator("#theme-toggle").click()
    page.wait_for_timeout(700)
    page.screenshot(path="data/ui-dark.png", full_page=True)
    page.locator("#nav button", has_text="历史记录").click()
    page.wait_for_timeout(1200)
    page.screenshot(path="data/ui-history.png", full_page=True)
    page.locator("#nav button", has_text="术语库").click()
    page.wait_for_timeout(1000)
    page.screenshot(path="data/ui-glossary.png", full_page=True)
    print("HISTORY_ITEMS", page.locator(".history-item").count())
    print("ERRORS", json.dumps(errors, ensure_ascii=False))
    browser.close()
