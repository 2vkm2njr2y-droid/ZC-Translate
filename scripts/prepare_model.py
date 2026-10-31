"""Download Hy-MT2 from ModelScope and convert it to OpenVINO INT4.

Run this with the conversion virtual environment, which needs optimum-intel
(including Hy-MT2 support), nncf, torch and modelscope.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.backend.config import MODEL_PROFILES, resolve_models_dir  # noqa: E402


def run(command: list[str]) -> None:
    print("\n$ " + " ".join(command), flush=True)
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["TERM"] = "dumb"
    subprocess.run(command, check=True, env=env, cwd=str(ROOT))


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="准备 Hy-MT2 OpenVINO 模型")
    parser.add_argument("--profile", default="balanced", choices=list(MODEL_PROFILES))
    parser.add_argument("--skip-download", action="store_true")
    parser.add_argument("--skip-convert", action="store_true")
    parser.add_argument("--force", action="store_true", help="删除已有输出后重转")
    parser.add_argument("--delete-source", action="store_true", help="转换成功后删除 bf16 源模型")
    args = parser.parse_args()

    profile = MODEL_PROFILES[args.profile]
    model_id = str(profile["model_id"])
    repo = str(profile["repo"])
    models_dir = resolve_models_dir()
    pack_dir = models_dir / model_id
    source_dir = pack_dir / "source"
    pack_dir.mkdir(parents=True, exist_ok=True)

    variants: dict[str, dict[str, object]] = {}
    outputs: list[tuple[str, str, list[str]]] = []
    if args.profile == "balanced":
        outputs = [
            ("default", "ov-int4", [
                "--weight-format", "int4", "--group-size", "128", "--ratio", "0.8",
            ]),
            ("npu", "ov-int4-npu", [
                "--weight-format", "int4", "--sym", "--group-size", "-1", "--ratio", "1.0",
            ]),
        ]
    else:
        outputs = [
            ("default", "ov-int4", [
                "--weight-format", "int4", "--group-size", "128", "--ratio", "0.8",
            ]),
        ]

    if not args.force and (pack_dir / "pack.json").exists():
        ready = all((pack_dir / dirname / "openvino_model.xml").exists()
                    for _, dirname, _ in outputs)
        if ready:
            print(f"{profile['name']} 已准备完成：{pack_dir}")
            return 0

    if not args.skip_download and not source_dir.exists():
        from modelscope import snapshot_download
        print(f"下载 {repo} ...")
        snapshot_download(repo, local_dir=str(source_dir))

    if not args.skip_convert:
        optimum_cli = Path(sys.executable).with_name("optimum-cli.exe")
        if not optimum_cli.exists():
            optimum_cli = Path(sys.executable).with_name("optimum-cli")
        for key, dirname, extra in outputs:
            out_dir = pack_dir / dirname
            if out_dir.exists():
                if not args.force:
                    print(f"跳过已存在的 {out_dir}")
                    variants[key] = {
                        "path": dirname,
                        "devices": ["NPU"] if key == "npu" else ["GPU", "CPU"],
                    }
                    continue
                shutil.rmtree(out_dir)
            run([
                str(optimum_cli), "export", "openvino",
                "--model", str(source_dir),
                "--task", "text-generation-with-past",
                *extra,
                str(out_dir),
            ])
            if not list(out_dir.glob("*.xml")):
                raise RuntimeError(f"{out_dir} 没有生成 OpenVINO IR")
            variants[key] = {
                "path": dirname,
                "devices": ["NPU"] if key == "npu" else ["GPU", "CPU"],
            }

    license_src = source_dir / "LICENSE.txt"
    if license_src.exists():
        shutil.copy2(license_src, pack_dir / "LICENSE.txt")
    readme_src = source_dir / "README.md"
    if readme_src.exists():
        shutil.copy2(readme_src, pack_dir / "MODEL_CARD.md")

    pack = {
        "schema": 1,
        "id": model_id,
        "name": str(profile["name"]),
        "repo": repo,
        "license": str(profile["license"]),
        "params": str(profile["params"]),
        "description": str(profile["description"]),
        "prompt_version": "hymt2-v1",
        "openvino_version": "2026.4.1",
        "variants": variants,
    }
    (pack_dir / "pack.json").write_text(
        json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n完成：{pack_dir}")
    print(json.dumps(pack, ensure_ascii=False, indent=2))
    if args.delete_source and source_dir.exists():
        shutil.rmtree(source_dir)
        print("已删除 bf16 源模型目录")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
