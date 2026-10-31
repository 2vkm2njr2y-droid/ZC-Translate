"""Manual end-to-end UI test. Run while the local server is running.

The server must be started with a known token, for example:
  .venv-runtime\\Scripts\\python.exe app\\desktop.py --no-window --port 8011 --token test-ui
Then:
  .venv-runtime\\Scripts\\python.exe tests\\manual\\ui_full.py
"""

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
        page.wait_for_timeout(800)

        # Settings defaults: official sampling.
        page.locator("#nav button", has_text="设置").click()
        page.wait_for_selector(".model-card", timeout=15000)
        temperature = page.locator(".field", has_text="temperature").locator("input").input_value()
        top_p = page.locator(".field", has_text="top_p").locator("input").input_value()
        top_k = page.locator(".field", has_text="top_k").locator("input").input_value()
        print("SAMPLING", temperature, top_p, top_k)

        # Dark theme.
        page.locator("#theme-toggle").click()
        page.wait_for_timeout(400)
        theme = page.locator("html").get_attribute("data-theme")
        print("THEME", theme)
        page.screenshot(path="data/ui-dark-real.png", full_page=True)
        page.locator("#theme-toggle").click()
        page.wait_for_timeout(300)
        page.locator("#theme-toggle").click()
        page.wait_for_timeout(300)

        # Japanese -> Chinese hard sentence.
        page.locator("#nav button", has_text="翻译").click()
        page.wait_for_selector("#source-text", timeout=10000)
        page.fill("#source-text", "会議の資料は昨日のうちに全員に送っておきました。")
        page.select_option("select[aria-label='源语言']", "ja")
        page.select_option("select[aria-label='目标语言']", "zh")
        page.locator("button.primary").click()
        for _ in range(120):
            status = page.locator("#status-text").inner_text()
            if "完成" in status or "失败" in status:
                break
            page.wait_for_timeout(500)
        ja_zh = page.locator("#target-content").inner_text()
        print("JA_ZH", ja_zh.replace("\n", " | "))
        page.screenshot(path="data/ui-translate-ja-zh.png", full_page=True)

        # Glossary UI: create a glossary and add one term.
        page.locator("#nav button", has_text="术语库").click()
        page.wait_for_timeout(600)
        page.get_by_role("button", name="新建术语库").click()
        page.wait_for_selector(".modal", timeout=5000)
        page.locator(".modal input[type=text]").fill("UI术语测试")
        page.locator(".modal select").nth(0).select_option("en")
        page.locator(".modal select").nth(1).select_option("ja")
        page.locator(".modal").get_by_role("button", name="创建").click()
        page.wait_for_timeout(900)
        source_input = page.locator(".term-form input[type=text]").nth(0)
        target_input = page.locator(".term-form input[type=text]").nth(1)
        if source_input.count():
            source_input.fill("cache directory")
            target_input.fill("キャッシュディレクトリ")
            page.locator(".term-form").get_by_role("button", name="添加").click()
            page.wait_for_timeout(900)
        page.screenshot(path="data/ui-glossary-real.png", full_page=True)

        # Translate with the glossary.
        page.locator("#nav button", has_text="翻译").click()
        page.wait_for_selector("#source-text", timeout=10000)
        page.fill("#source-text", "The cache directory is missing.")
        page.select_option("select[aria-label='源语言']", "en")
        page.select_option("select[aria-label='目标语言']", "ja")
        options = page.locator("select[aria-label='术语库'] option").all_text_contents()
        selected = next((text for text in options if "UI术语测试" in text), "")
        if selected:
            page.select_option("select[aria-label='术语库']", label=selected)
        page.locator("button.primary").click()
        for _ in range(120):
            status = page.locator("#status-text").inner_text()
            if "完成" in status or "失败" in status:
                break
            page.wait_for_timeout(500)
        glossary_out = page.locator("#target-content").inner_text()
        print("GLOSSARY_OUT", glossary_out.replace("\n", " | "))

        # History contains the runs.
        page.locator("#nav button", has_text="历史记录").click()
        page.wait_for_timeout(1000)
        print("HISTORY_COUNT", page.locator(".history-item").count())

        print("ERRORS", json.dumps(errors, ensure_ascii=False))
        browser.close()
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
