"""End-to-end regression test for destructive actions.

The desktop UI is served by the real FastAPI app; this test uses a temporary
data directory so it never touches the user's history.  It exercises the real
confirmation dialog because a regression there makes every delete/clear action
silently do nothing while still closing the modal.  History, glossary terms and
translation-memory clearing are covered because they share that dialog.
"""

from __future__ import annotations

import socket
import threading
import time
import urllib.request

import pytest
import uvicorn

from app.backend.main import create_app

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect
sync_playwright = playwright.sync_playwright


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_health(port: int, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    url = f"http://127.0.0.1:{port}/api/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"测试服务启动超时（端口 {port}）")


@pytest.fixture()
def live_app(tmp_path):
    app = create_app(
        token="test-ui",
        data_dir=str(tmp_path / "data"),
        models_dir=str(tmp_path / "models"),
    )
    port = _free_port()
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="error",
        access_log=False,
        lifespan="on",
        log_config=None,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="test-uvicorn", daemon=True)
    thread.start()
    _wait_health(port)
    try:
        yield app, f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _add_history(app, text: str) -> str:
    return app.state.db.add_history(
        kind="text",
        src_lang="en",
        detected_lang="en",
        tgt_lang="zh",
        profile="balanced",
        device="CPU",
        source_text=text,
        result_text=f"译:{text}",
        status="completed",
        duration_ms=5,
    )


def _seed_glossary(app) -> None:
    glossary = app.state.db.create_glossary("UI Regression Glossary", "en", "zh", False)
    app.state.db.upsert_term(glossary["id"], "cache", "缓存")


def _wait_total(app, expected: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if app.state.db.list_history()["total"] == expected:
            return
        time.sleep(0.05)
    assert app.state.db.list_history()["total"] == expected


def _launch_browser(playwright_context):
    last_error: Exception | None = None
    for launch in (
        lambda: playwright_context.chromium.launch(channel="msedge", headless=True),
        lambda: playwright_context.chromium.launch(headless=True),
    ):
        try:
            return launch()
        except Exception as exc:  # noqa: BLE001 - try the next installed browser
            last_error = exc
    pytest.skip(f"未找到可用的 Chromium / Microsoft Edge：{last_error}")
    raise AssertionError("unreachable")


def test_ui_destructive_actions(live_app):
    app, base = live_app
    for text in ("first", "second", "third"):
        _add_history(app, text)
    _seed_glossary(app)

    with sync_playwright() as playwright_context:
        browser = _launch_browser(playwright_context)
        try:
            page = browser.new_page(viewport={"width": 900, "height": 700})
            page.goto(f"{base}/?token=test-ui", wait_until="domcontentloaded")
            engine = page.locator("#compact-engine")
            expect(engine).not_to_have_text("正在检测设备…", timeout=20000)
            expect(engine).not_to_have_text("无法连接本地服务")

            page.locator('.compact-tab[data-route="history"]').click()
            expect(page.locator(".history-item")).to_have_count(3, timeout=10000)

            detail_delete = page.locator(".history-detail").get_by_role(
                "button", name="删除", exact=True
            )
            expect(detail_delete).to_be_visible(timeout=10000)

            # Cancel must not call the API or remove the row.
            detail_delete.click()
            modal = page.locator(".modal")
            expect(modal).to_be_visible()
            modal.get_by_role("button", name="取消", exact=True).click()
            expect(modal).to_have_count(0)
            expect(page.locator(".history-item")).to_have_count(3)
            assert app.state.db.list_history()["total"] == 3

            # Confirm must actually delete and refresh the current page.
            detail_delete.click()
            expect(modal).to_be_visible()
            modal.get_by_role("button", name="删除", exact=True).click()
            expect(page.locator(".history-item")).to_have_count(2, timeout=10000)
            expect(page.locator(".history-detail .empty-state")).to_be_visible()
            _wait_total(app, 2)

            # Clearing from the history page empties the list in place.
            page.get_by_role("button", name="清空历史", exact=True).click()
            expect(modal).to_be_visible()
            modal.get_by_role("button", name="清空", exact=True).click()
            expect(page.locator(".history-item")).to_have_count(0, timeout=10000)
            expect(page.locator(".history-detail .empty-state")).to_be_visible()
            _wait_total(app, 0)

            # Clearing from settings also works; the history page reloads empty.
            _add_history(app, "fourth")
            page.locator('.compact-tab[data-route="settings"]').click()
            settings_clear = page.get_by_role("button", name="清空历史记录", exact=True)
            expect(settings_clear).to_be_visible(timeout=10000)
            settings_clear.click()
            expect(modal).to_be_visible()
            modal.get_by_role("button", name="清空", exact=True).click()
            _wait_total(app, 0)

            page.locator('.compact-tab[data-route="history"]').click()
            expect(page.locator(".history-item")).to_have_count(0, timeout=10000)
            expect(page.locator(".history-detail .empty-state")).to_be_visible()

            # Deleting a glossary term also uses the shared dialog and must
            # refresh the term count in the left list.
            page.locator('.compact-tab[data-route="glossary"]').click()
            expect(page.locator(".glossary-item")).to_have_count(1, timeout=10000)
            expect(page.locator(".glossary-item .gi-meta")).to_contain_text("1 条")
            term_delete = page.locator(".terms-table tbody tr").get_by_role(
                "button", name="删除", exact=True
            )
            expect(term_delete).to_be_visible(timeout=10000)
            term_delete.click()
            expect(modal).to_be_visible()
            modal.get_by_role("button", name="确定", exact=True).click()
            expect(page.locator(".terms-table tbody tr")).to_have_count(0, timeout=10000)
            expect(page.locator(".glossary-item .gi-meta")).to_contain_text("0 条")

            # Clearing TM must execute and refresh the settings stats line.
            app.state.db.put_tm(
                "en", "zh", "balanced", "hymt2-v1", "", "ui-test-key", "ui-test-value"
            )
            page.locator('.compact-tab[data-route="settings"]').click()
            expect(page.get_by_text("翻译记忆：1 条", exact=False)).to_be_visible(timeout=10000)
            page.get_by_role("button", name="清空翻译记忆", exact=True).click()
            expect(modal).to_be_visible()
            modal.get_by_role("button", name="清空", exact=True).click()
            expect(page.get_by_text("翻译记忆：0 条", exact=False)).to_be_visible(timeout=10000)
            assert app.state.db.tm_stats()["entries"] == 0
        finally:
            browser.close()
