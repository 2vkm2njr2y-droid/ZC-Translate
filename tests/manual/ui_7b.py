import json

from playwright.sync_api import sync_playwright

URL = "http://127.0.0.1:8011/?token=test-ui"


def main() -> int:
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.on("console", lambda msg: errors.append(f"console:{msg.type}:{msg.text}")
                if msg.type == "error" else None)
        page.on("pageerror", lambda exc: errors.append(f"pageerror:{exc}"))
        page.goto(URL, wait_until="networkidle")
        page.wait_for_selector(".translate-page", timeout=15000)
        page.wait_for_timeout(700)

        # Both model cards should be installed now.
        page.locator("#nav button", has_text="设置").click()
        page.wait_for_selector(".model-card", timeout=15000)
        page.wait_for_timeout(500)
        installed = page.locator(".model-card .badge", has_text="已安装").count()
        print("INSTALLED_BADGES", installed)
        page.screenshot(path="data/ui-settings-7b.png", full_page=True)

        # Switch to 7B and translate a hard technical sentence.
        page.locator("#nav button", has_text="翻译").click()
        page.wait_for_selector("#source-text", timeout=10000)
        page.select_option("select[aria-label='模型档位']", "quality")
        page.wait_for_timeout(500)
        page.fill("#source-text", "The update fixes a crash when the cache directory is missing.")
        page.select_option("select[aria-label='源语言']", "en")
        page.select_option("select[aria-label='目标语言']", "ja")
        page.locator("button.primary").click()
        status = ""
        for _ in range(240):
            status = page.locator("#status-text").inner_text()
            if "完成" in status or "失败" in status:
                break
            page.wait_for_timeout(500)
        target = page.locator("#target-content").inner_text()
        statusbar = page.locator("#statusbar").inner_text()
        print("STATUS", status)
        print("TARGET", target.replace("\n", " | "))
        print("STATUSBAR", statusbar.replace("\n", " | "))
        page.screenshot(path="data/ui-translate-7b.png", full_page=True)
        print("ERRORS", json.dumps(errors, ensure_ascii=False))
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
