from __future__ import annotations

import argparse
import json
import statistics
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.backend.config import MODEL_PROFILES  # noqa: E402
from app.backend.engine.base import GenerationOptions  # noqa: E402
from app.backend.engine.openvino_engine import OpenVINOEngine  # noqa: E402
from app.backend.engine.registry import scan_models  # noqa: E402
from app.backend.pipeline.prompts import build_prompt  # noqa: E402


def make_text(length: int) -> str:
    sample = "系统会在缓存目录缺失时自动重建索引，并记录一条警告日志。"
    return (sample * (length // len(sample) + 1))[:length]


def run_case(engine: OpenVINOEngine, length: int) -> dict:
    text = make_text(length)
    prompt = build_prompt(text=text, src_lang="zh", tgt_lang="en").messages()
    prompt = engine.apply_chat_template(prompt)
    options = GenerationOptions(
        max_new_tokens=min(1024, max(128, length * 2)),
        temperature=0.7, top_p=0.6, top_k=20,
        repetition_penalty=1.05, do_sample=True, rng_seed=42,
    )
    chunks: list[str] = []
    started = time.perf_counter()
    result = engine.generate(prompt, options, lambda piece: chunks.append(piece),
                             threading.Event())
    return {
        "length": length,
        "ttft_ms": round(result.ttft_ms, 1),
        "total_ms": round(result.total_ms, 1),
        "tokens": result.gen_tokens,
        "tok_s": round(result.tok_s, 1),
        "text": "".join(chunks)[:160],
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="ZC 设备基准测试")
    parser.add_argument("--profiles", default="balanced")
    parser.add_argument("--devices", default="NPU,GPU,CPU")
    parser.add_argument("--lengths", default="50,200,500")
    parser.add_argument("--out", default="docs/benchmark.md")
    args = parser.parse_args()

    profiles = [item for item in args.profiles.split(",") if item]
    devices = [item.strip() for item in args.devices.split(",") if item.strip()]
    lengths = [int(item) for item in args.lengths.split(",") if item.strip()]
    packs = scan_models()
    report = {"generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "results": []}

    for profile_id in profiles:
        profile = MODEL_PROFILES.get(profile_id)
        if not profile:
            continue
        pack = packs.get(str(profile["model_id"]))
        if not pack:
            print(f"跳过 {profile_id}: 未安装模型")
            continue
        for device in devices:
            key = "npu" if device == "NPU" else "default"
            variant = pack.variants.get(key)
            if not variant:
                print(f"跳过 {profile_id}/{device}: 缺少变体")
                continue
            print(f"\n== {profile['name']} / {device} ==")
            engine = OpenVINOEngine()
            try:
                load_ms = engine.load(str(variant), device, str(ROOT / "data" / "cache" / "bench"))
            except Exception as exc:  # noqa: BLE001
                print(f"加载失败: {exc}")
                continue
            warm = run_case(engine, 20)
            rows = []
            for length in lengths:
                values = [run_case(engine, length) for _ in range(2)]
                best = max(values, key=lambda item: item["tok_s"])
                samples = [item["tok_s"] for item in values]
                rows.append({
                    "profile": profile_id,
                    "device": device,
                    "length": length,
                    "ttft_ms": best["ttft_ms"],
                    "tok_s_median": round(statistics.median(samples), 1),
                    "total_ms": best["total_ms"],
                    "tokens": best["tokens"],
                    "sample": best["text"],
                })
                print(f"{length:4} 字: ttft {best['ttft_ms']:7.0f} ms  "
                      f"{statistics.median(samples):6.1f} tok/s  total {best['total_ms']:7.0f} ms")
            report["results"].append({
                "profile": profile_id,
                "model": pack.name,
                "device": device,
                "load_ms": round(load_ms, 1),
                "warmup": warm,
                "rows": rows,
            })
            engine.unload()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    Path("data").mkdir(exist_ok=True)
    Path("data/benchmark.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = ["# 基准测试", "", f"生成时间：{report['generated_at']}", "",
             "| 模型 | 设备 | 加载 ms | 输入字数 | 首 token ms | tok/s | 总耗时 ms |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for group in report["results"]:
        for row in group["rows"]:
            lines.append(
                f"| {group['model']} | {group['device']} | {group['load_ms']} | "
                f"{row['length']} | {row['ttft_ms']} | {row['tok_s_median']} | {row['total_ms']} |"
            )
    lines.append("")
    lines.append("说明：每个长度运行两次取 tok/s 中位数；加载时间包含首次 OpenVINO/NPU 编译。")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n写入 {out} 与 data/benchmark.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
