"""Desktop launcher: local FastAPI server + pywebview (Edge WebView2)."""

from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import socket
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# PyInstaller's --windowed mode sets stdout/stderr to None.  Uvicorn's logging
# configuration expects real streams, so provide a harmless sink.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

import uvicorn  # noqa: E402

from app.backend.logging_setup import setup_logging  # noqa: E402
from app.backend.main import create_app  # noqa: E402
from app.backend.services.settings import load_settings  # noqa: E402
from app.shell.shell import DesktopShell  # noqa: E402
from app.shell.single_instance import SingleInstance  # noqa: E402


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_for_health(port: int, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    url = f"http://127.0.0.1:{port}/api/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.15)
    return False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ZC 离线翻译桌面启动器")
    parser.add_argument("--port", type=int, default=0, help="0 = 自动选择端口")
    parser.add_argument("--token", default="", help="调试用固定令牌")
    parser.add_argument("--data-dir", default="", help="覆盖数据目录")
    parser.add_argument("--models-dir", default="", help="覆盖模型目录")
    parser.add_argument("--dev", action="store_true", help="开发者模式（控制台日志/DevTools）")
    parser.add_argument("--no-window", action="store_true", help="不打开窗口，只启动本地服务")
    return parser.parse_args()


def log_line(message: str, error: bool = False) -> None:
    stream = sys.stderr if error else sys.stdout
    if stream is not None:
        print(message, file=stream, flush=True)


def log_startup_failure(exc: BaseException) -> None:
    """Keep packaged-window errors visible when console=False is enabled."""
    try:
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "ZCTranslate" / "logs"
        base.mkdir(parents=True, exist_ok=True)
        with (base / "desktop-startup.log").open("a", encoding="utf-8") as stream:
            stream.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            stream.write(traceback.format_exc())
            stream.write("\n")
    except Exception:
        pass


# Keep these values in sync with --bg in app/frontend/assets/styles.css.
WINDOW_BACKGROUND = {"light": "#f4f6fb", "dark": "#0b1220"}


def _system_theme_is_dark() -> bool:
    """Read the Windows app-theme setting for the pre-page-load background."""
    if os.name != "nt":
        return False
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            use_light, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        return int(use_light) == 0
    except Exception:
        return False


def window_background_color(app) -> str:
    """Choose the opaque WebView2 surface color before the page paints."""
    theme = "system"
    try:
        theme = str(load_settings(app.state.db).get("theme") or "system")
    except Exception:
        pass
    if theme == "system":
        theme = "dark" if _system_theme_is_dark() else "light"
    return WINDOW_BACKGROUND["dark" if theme == "dark" else "light"]


class DesktopApi:
    """Small bridge used by the borderless window controls."""

    def __init__(self) -> None:
        self._shell: DesktopShell | None = None

    def attach(self, shell: DesktopShell) -> None:
        self._shell = shell

    def _window(self):
        if self._shell is not None:
            return self._shell.main_window
        import webview  # type: ignore
        return webview.windows[0] if webview.windows else None

    def capture_for_screenshot(self):
        """Hide the window, run the native snipping flow, then restore.

        This runs entirely in Python while the page is hidden, so the result
        does not depend on timers or network requests continuing in a hidden
        WebView2 page.
        """
        from app.backend.services.screenshot import (
            CaptureBusy,
            CaptureCancelled,
            CaptureError,
            CaptureTimeout,
            CaptureUnavailable,
            capture_native_region,
        )

        window = self._window()
        hidden = False
        try:
            if window:
                try:
                    window.hide()
                    hidden = True
                except Exception:
                    log_line("隐藏窗口失败，继续截图流程。", error=True)
            return capture_native_region()
        except CaptureCancelled as exc:
            return {"ok": False, "cancelled": True,
                    "code": "SCREENSHOT_CANCELLED", "message": str(exc)}
        except CaptureTimeout as exc:
            return {"ok": False, "code": "SCREENSHOT_TIMEOUT", "message": str(exc)}
        except CaptureUnavailable as exc:
            return {"ok": False, "code": "SCREENSHOT_UNAVAILABLE", "message": str(exc)}
        except CaptureBusy as exc:
            return {"ok": False, "code": "SCREENSHOT_BUSY", "message": str(exc)}
        except CaptureError as exc:
            return {"ok": False, "code": "SCREENSHOT_FAILED", "message": str(exc)}
        except Exception as exc:  # noqa: BLE001
            log_startup_failure(exc)
            return {"ok": False, "code": "SCREENSHOT_FAILED", "message": f"截图失败：{exc}"}
        finally:
            if hidden and window:
                try:
                    window.show()
                except Exception:
                    log_line("恢复窗口失败。", error=True)
                if self._shell is not None:
                    try:
                        self._shell.restore_main_size()
                    except Exception:
                        log_line("恢复窗口尺寸失败。", error=True)

    def minimize(self):
        window = self._window()
        if window:
            window.minimize()
        return True

    def set_frame_color(self, color):
        if self._shell is None:
            return False
        return self._shell.set_frame_color(color)

    def close(self):
        if self._shell is not None:
            return self._shell.close_main()
        window = self._window()
        if window:
            window.destroy()
        return True

    # ----------------------------------------------------------- overlay bridge
    def overlay_resize(self, width, height):
        if self._shell is None:
            return False
        return self._shell.overlay_resize(width, height)

    def overlay_hide(self):
        if self._shell is None:
            return False
        return self._shell.overlay_hide()

    def copy_text(self, text):
        if self._shell is None:
            return False
        return self._shell.copy_text(text)

    def selection_status(self):
        if self._shell is None:
            return {"available": False, "detail": "桌面壳尚未启动"}
        return self._shell.selection_status()

    def choose_document(self):
        """Use the native picker so translated files can be saved beside the source."""
        import webview  # type: ignore
        window = self._window()
        if not window:
            return None
        selected = window.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=False,
            file_types=(
                "Supported files (*.pdf;*.docx;*.txt;*.md;*.png;*.jpg;*.jpeg;*.bmp;*.webp;*.gif)",
            ),
        )
        if not selected:
            return None
        path = Path(selected[0])
        return {
            "path": str(path),
            "name": path.name,
            "content_base64": base64.b64encode(path.read_bytes()).decode("ascii"),
        }


def register_printscreen(window) -> None:
    """Dispatch a browser event when PrintScreen is pressed anywhere in Windows."""
    if os.name != "nt":
        return

    def worker():
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hotkey_id = 0x5A43
        # VK_SNAPSHOT = PrintScreen; no modifier means it is global.
        if not user32.RegisterHotKey(None, hotkey_id, 0, 0x2C):
            log_line("PrintScreen 快捷键注册失败，将只保留界面内截图入口。", error=True)
            return
        msg = wintypes.MSG()
        try:
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0312 and msg.wParam == hotkey_id:
                    try:
                        window.evaluate_js("window.dispatchEvent(new Event('zc-screenshot'))")
                    except Exception:
                        break
        finally:
            user32.UnregisterHotKey(None, hotkey_id)

    threading.Thread(target=worker, name="printscreen-hotkey", daemon=True).start()


def main() -> int:
    args = parse_args()
    setup_logging(dev=args.dev)
    single_instance = None
    if not args.no_window and not args.dev:
        single_instance = SingleInstance()
        if not single_instance.acquire():
            log_line("已有实例在运行，已请求其显示主窗口。")
            return 0

    port = args.port or find_free_port()
    token = args.token or secrets.token_urlsafe(24)
    app = create_app(
        token=token,
        data_dir=args.data_dir or None,
        models_dir=args.models_dir or None,
        dev=args.dev,
    )
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
        lifespan="on",
        log_config=None,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="uvicorn", daemon=True)
    thread.start()

    if not wait_for_health(port):
        log_line("本地服务启动失败，请查看 data/logs/app.log", error=True)
        server.should_exit = True
        return 1

    base_url = f"http://127.0.0.1:{port}"
    url = f"{base_url}/?token={token}"
    overlay_url = f"{base_url}/overlay?token={token}"
    if args.dev or args.no_window:
        log_line(f"ZC 离线翻译已启动：{url}")
        log_line("提示：这是本地一次性链接，地址中的 token 用于防止其他网页调用本地服务。")
    if args.no_window:
        # Machine-readable handshake for local clients such as Comic-Player.
        # The token never leaves the local process and is required on every API
        # request except /api/health.
        log_line("ZC_READY " + json.dumps({"port": port, "token": token}, ensure_ascii=False))

    if args.no_window:
        try:
            thread.join()
        except KeyboardInterrupt:
            pass
        finally:
            server.should_exit = True
            thread.join(timeout=5)
        return 0

    shell: DesktopShell | None = None
    try:
        import webview  # type: ignore

        desktop_api = DesktopApi()
        window_background = window_background_color(app)
        window = webview.create_window(
            "ZC 离线翻译",
            url,
            width=620,
            height=460,
            min_size=(560, 420),
            # DWM clips the composed window to the native rounded silhouette.
            # The page stays opaque so no backing surface can leak through.
            background_color=window_background,
            text_select=True,
            frameless=True,
            # Only the topbar drag handle (pywebview-drag-region) moves the
            # window.  easy_drag would make the whole client area draggable and
            # block text selection in the input and result panes.
            easy_drag=False,
            # Sizes are controlled by the explicit compact/expand actions.
            resizable=False,
            # DWM needs non-client rendering enabled to round a frameless window.
            shadow=True,
            js_api=desktop_api,
        )
        overlay_window = webview.create_window(
            "ZC 划译",
            overlay_url,
            width=420,
            height=120,
            min_size=(200, 48),
            hidden=True,
            frameless=True,
            easy_drag=False,
            resizable=False,
            on_top=True,
            focus=False,
            shadow=False,
            text_select=True,
            background_color=window_background,
            js_api=desktop_api,
        )
        shell = DesktopShell(
            window,
            overlay_window,
            app,
            single_instance=single_instance,
            frame_color=window_background,
        )
        desktop_api.attach(shell)
        register_printscreen(window)
        webview.start(shell.start, debug=args.dev)
        return 0
    except Exception as exc:  # noqa: BLE001
        log_startup_failure(exc)
        log_line(f"桌面窗口启动失败，改用默认浏览器：{exc}", error=True)
        if shell is not None:
            shell.stop()
        webbrowser.open(url)
        try:
            thread.join()
        except KeyboardInterrupt:
            pass
        finally:
            server.should_exit = True
            thread.join(timeout=5)
        return 0
    finally:
        if shell is not None:
            shell.stop()
        server.should_exit = True
        thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
