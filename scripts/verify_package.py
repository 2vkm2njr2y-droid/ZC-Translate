"""Packaged-build acceptance checks over the local HTTP API.

The script never imports ``app``; it talks to a running ZCTranslate build the
same way the desktop window does, so it can validate any packaged folder.
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import sys
import time
from pathlib import Path

import httpx


def _same_path(left: str, right: str) -> bool:
    try:
        return Path(left).resolve() == Path(right).resolve()
    except OSError:
        return left.rstrip("\\/").casefold() == right.rstrip("\\/").casefold()


def _ocr_png() -> bytes:
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (420, 140), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 56)
    except OSError:
        font = ImageFont.load_default(size=56)
    draw.text((24, 36), "HELLO 2026", fill="black", font=font)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _wait_ready(client: httpx.Client, timeout: float) -> dict:
    started = time.monotonic()
    triggered = False
    last_state = ""
    while True:
        response = client.get("/api/models")
        response.raise_for_status()
        data = response.json()
        engine = data.get("engine", {})
        last_state = str(engine.get("state", ""))
        if last_state == "ready":
            return data
        if last_state == "error":
            raise RuntimeError(f"模型加载失败：{engine.get('last_error') or '未知错误'}")
        if last_state == "idle" and not triggered and time.monotonic() - started > 10:
            client.post("/api/system/preload")
            triggered = True
        if time.monotonic() - started >= timeout:
            raise TimeoutError(f"等待模型加载超时（state={last_state}）")
        time.sleep(2)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="验证 ZC 打包版本地 API")
    parser.add_argument("--base-url", default="http://127.0.0.1:18031")
    parser.add_argument("--token", required=True)
    parser.add_argument("--expect-models-dir", default="")
    parser.add_argument(
        "--expect-device", default="", choices=["", "NPU", "GPU", "CPU"]
    )
    parser.add_argument("--timeout", type=float, default=240.0)
    parser.add_argument("--ocr", action="store_true")
    parser.add_argument("--text", default="今天天气真好。我们下午去公园散步吧。")
    parser.add_argument("--target", default="ja", choices=["zh", "ja", "en"])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    problems: list[str] = []
    summary: dict[str, object] = {"base_url": base}

    def check(condition: bool, message: str) -> None:
        if not condition:
            problems.append(message)

    client = httpx.Client(
        base_url=base,
        headers={"x-zc-token": args.token},
        timeout=httpx.Timeout(30.0, read=max(60.0, args.timeout)),
    )
    try:
        health = client.get("/api/health")
        check(health.status_code == 200, f"/api/health 返回 {health.status_code}")
        check(health.json().get("status") == "ok", "/api/health 状态不是 ok")

        home = client.get("/", params={"token": args.token})
        check(home.status_code == 200, f"首页返回 {home.status_code}")
        check("__ZC_TOKEN__" not in home.text, "首页未注入一次性 token")
        check('id="app"' in home.text, "首页缺少 #app 根节点")

        overlay = client.get("/overlay", params={"token": args.token})
        check(overlay.status_code == 200, f"/overlay 返回 {overlay.status_code}")
        check("__ZC_TOKEN__" not in overlay.text, "/overlay 未注入一次性 token")
        check("/js/overlay.js" in overlay.text, "/overlay 缺少划译前端脚本")

        styles = client.get("/assets/styles.css")
        check(styles.status_code == 200, f"styles.css 返回 {styles.status_code}")
        check("--radius-window" in styles.text, "styles.css 缺少新圆角令牌")
        check(".zc-overlay" in styles.text, "styles.css 缺少划译浮层样式")
        icon = client.get("/assets/zc-translate-icon.png")
        check(icon.status_code == 200, f"图标返回 {icon.status_code}")
        check(
            icon.headers.get("content-type", "").startswith("image/"),
            "图标 Content-Type 不是图片",
        )

        model_data = _wait_ready(client, args.timeout)
        models_dir = str(model_data.get("models_dir", ""))
        engine = model_data.get("engine", {})
        summary["models_dir"] = models_dir
        summary["engine"] = {
            "state": engine.get("state"),
            "device": engine.get("device"),
            "model_name": engine.get("model_name"),
            "load_ms": engine.get("load_ms"),
        }
        if args.expect_models_dir:
            check(
                _same_path(models_dir, args.expect_models_dir),
                f"模型目录为 {models_dir}，期望 {args.expect_models_dir}",
            )
        installed = {
            str(item.get("profile_id")): bool(item.get("installed"))
            for item in model_data.get("models", [])
        }
        summary["models"] = installed
        check(installed.get("balanced") is True, "1.8B（balanced）未安装")
        check(installed.get("quality") is True, "7B（quality）未安装")

        payload = {
            "text": args.text,
            "source_lang": "zh",
            "target_lang": args.target,
            "device": "auto",
            "use_tm": False,
        }
        translated = client.post("/api/translate", json=payload)
        if translated.status_code != 200:
            check(False, f"翻译返回 {translated.status_code}：{translated.text[:200]}")
            result: dict = {}
        else:
            result = translated.json()
            text = str(result.get("text", "")).strip()
            check(bool(text), "翻译结果为空")
            summary["translate"] = {
                "device": result.get("device"),
                "model": result.get("model"),
                "tok_s": result.get("tok_s"),
                "elapsed_ms": result.get("elapsed_ms"),
                "chars": len(text),
                "preview": text[:60],
            }
            if args.expect_device:
                check(
                    result.get("device") == args.expect_device,
                    f"实际设备 {result.get('device')}，期望 {args.expect_device}",
                )

        capabilities = client.get("/api/ocr/capabilities")
        check(capabilities.status_code == 200, "OCR capabilities 请求失败")
        capability_data = capabilities.json() if capabilities.status_code == 200 else {}
        summary["ocr_available"] = capability_data.get("available")
        check(capability_data.get("available") is True, "OCR 组件不可用")

        if args.ocr:
            image = _ocr_png()
            ocr_response = client.post(
                "/api/ocr/image",
                json={
                    "file_name": "verify.png",
                    "content_base64": base64.b64encode(image).decode("ascii"),
                },
            )
            if ocr_response.status_code != 200:
                check(False, f"OCR 返回 {ocr_response.status_code}：{ocr_response.text[:200]}")
            else:
                ocr_data = ocr_response.json()
                ocr_text = str(ocr_data.get("text", "")).strip()
                summary["ocr"] = {"chars": len(ocr_text), "preview": ocr_text[:60]}
                check(bool(ocr_text), "OCR 识别结果为空")
    except (httpx.HTTPError, RuntimeError, TimeoutError) as exc:
        print(f"FAIL: {exc}")
        return 2
    finally:
        client.close()

    summary["problems"] = problems
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"base_url: {base}")
        print(f"models_dir: {summary.get('models_dir')}")
        print(f"engine: {summary.get('engine')}")
        print(f"models: {summary.get('models')}")
        print(f"translate: {summary.get('translate')}")
        print(f"ocr_available: {summary.get('ocr_available')}")
        if args.ocr:
            print(f"ocr: {summary.get('ocr')}")
        if problems:
            print("problems:")
            for item in problems:
                print(f"  - {item}")
        else:
            print("PASS: 打包版 API 验收通过")
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
