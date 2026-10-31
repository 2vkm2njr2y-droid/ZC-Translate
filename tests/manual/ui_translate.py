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
    page.wait_for_timeout(1200)
    page.fill("#source-text", "今天天气真好。我们下午去公园散步吧。")
    page.select_option("select[aria-label='目标语言']", "ja")
    page.locator("button.primary").click()
    status = ""
    for _ in range(180):
        status = page.locator("#status-text").inner_text()
        if "完成" in status or "失败" in status or "取消" in status:
            break
        page.wait_for_timeout(500)
    page.wait_for_timeout(400)
    target = page.locator("#target-content").inner_text()
    statusbar = page.locator("#statusbar").inner_text()
    page.screenshot(path="data/ui-translate.png", full_page=True)
    print("TARGET:", target)
    print("STATUS:", status)
    print("STATUSBAR:", statusbar)
    print("ERRORS:", json.dumps(errors, ensure_ascii=False))
    browser.close()
