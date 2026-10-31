from __future__ import annotations

import argparse
import json
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.backend.engine.registry import EngineManager  # noqa: E402
from app.backend.pipeline.translator import TranslationService  # noqa: E402
from app.backend.schemas import TranslateRequest  # noqa: E402
from app.backend.storage.db import Database  # noqa: E402

DIRECTIONS = ["zh-ja", "zh-en", "ja-zh", "ja-en", "en-zh", "en-ja"]


def read_jsonl(path: Path) -> list[dict]:
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            items.append(json.loads(line))
    return items


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="ZC 金标集评测")
    parser.add_argument("--profile", default="balanced", choices=["balanced", "quality"])
    parser.add_argument("--device", default="auto", choices=["auto", "NPU", "GPU", "CPU"])
    parser.add_argument("--dataset", default="tests/fixtures/golden")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--json-out", default="")
    parser.add_argument("--md-out", default="")
    args = parser.parse_args()

    engine = EngineManager()
    try:
        resolved = engine.ensure_loaded(args.profile, args.device)
    except Exception as exc:  # noqa: BLE001
        print(f"加载模型失败: {exc}")
        return 2

    try:
        from sacrebleu.metrics import CHRF
        chrf = CHRF(word_order=2)
    except Exception:
        chrf = None
        print("提示：未安装 sacrebleu，跳过 chrF++ 自动指标。")

    results = []
    with tempfile.TemporaryDirectory() as tmp:
        db = Database(Path(tmp) / "eval.db")
        service = TranslationService(engine, db)
        for direction in DIRECTIONS:
            path = Path(args.dataset) / f"{direction}.jsonl"
            if not path.exists():
                print(f"缺少数据集 {path}")
                continue
            rows = read_jsonl(path)
            if args.limit:
                rows = rows[: args.limit]
            src_lang, tgt_lang = direction.split("-")
            hyps, refs, samples = [], [], []
            for row in rows:
                events = []
                request = TranslateRequest(
                    text=row["source"], source_lang=src_lang, target_lang=tgt_lang,
                    profile_id=args.profile, device=args.device,
                )
                service.run(request, lambda event, data=None, events=events: events.append((event, data or {})),
                            threading.Event())
                done = [data for event, data in events if event == "done"]
                error = [data for event, data in events if event == "error"]
                text = done[-1]["text"] if done else ""
                hyps.append(text)
                refs.append(row["reference"])
                samples.append({
                    "source": row["source"],
                    "reference": row["reference"],
                    "hypothesis": text,
                    "error": error[-1]["message"] if error else None,
                })
            score = None
            if chrf is not None:
                score = round(chrf.corpus_score(hyps, [refs]).score, 2)
            results.append({
                "direction": direction,
                "count": len(rows),
                "chrf_pp": score,
                "device": resolved.device,
                "profile": args.profile,
                "samples": samples,
            })
            print(f"{direction}: {len(rows)} 句" + (f"，chrF++ {score}" if score is not None else ""))
        db.close()

    Path("data").mkdir(exist_ok=True)
    json_out = Path(args.json_out or f"data/evaluation-{args.profile}.json")
    md_out = Path(args.md_out or f"docs/evaluation-{args.profile}.md")
    json_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(
        json.dumps({"results": results}, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    lines = [
        "# 准确率评测",
        "",
        f"- 模型档位：{args.profile}",
        f"- 设备：{resolved.device}",
        f"- 数据集：`{args.dataset}`",
        "- 说明：chrF++ 只反映字面/字符相似度，最终以人工复核为准。",
        "",
        "| 方向 | 句数 | chrF++ |",
        "|---|---:|---:|",
    ]
    for item in results:
        lines.append(f"| {item['direction']} | {item['count']} | "
                     f"{item['chrf_pp'] if item['chrf_pp'] is not None else '—'} |")
    lines.append("")
    lines.append("## 抽样")
    lines.append("")
    for item in results:
        lines.append(f"### {item['direction']}")
        for sample in item["samples"][:5]:
            lines.append(f"- 原文：{sample['source']}")
            lines.append(f"  - 参考：{sample['reference']}")
            lines.append(f"  - 译文：{sample['hypothesis']}")
            if sample["error"]:
                lines.append(f"  - 错误：{sample['error']}")
        lines.append("")
    md_out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\n写入 {json_out} 与 {md_out}")
    engine.unload()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
