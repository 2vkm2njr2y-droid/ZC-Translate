# 模型准备

## 模型

| Profile | ModelScope | 参数 | 原始 BF16 | OpenVINO INT4 | 设备 |
|---|---|---|---:|---:|---|
| balanced | `Tencent-Hunyuan/Hy-MT2-1.8B` | 2.0B | ≈4.1GB | 约 2.2GB（两个变体） | NPU / GPU / CPU |
| quality | `Tencent-Hunyuan/Hy-MT2-7B` | 8.0B | ≈15GB | ≈4.6GB | GPU / CPU |

许可证均为 Apache-2.0。模型卡与提示词模板随包放在 `models/<id>/MODEL_CARD.md`。本工作区已准备好两档模型（`models/hymt2-1.8b`、`models/hymt2-7b`）。

## 一键准备

```powershell
# 首次会创建 .venv-convert 并安装 optimum-intel / torch / nncf / modelscope
powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1
.\.venv-convert\Scripts\python.exe scripts\prepare_model.py --profile balanced
```

或双击 `准备模型.bat`。

## 手动转换

```powershell
# 下载
.\.venv-convert\Scripts\modelscope.exe download --model Tencent-Hunyuan/Hy-MT2-1.8B `
  --local_dir models\hymt2-1.8b\source

# GPU/CPU 变体
.\.venv-convert\Scripts\optimum-cli.exe export openvino `
  --model models\hymt2-1.8b\source `
  --task text-generation-with-past `
  --weight-format int4 --group-size 128 --ratio 0.8 `
  models\hymt2-1.8b\ov-int4

# NPU 变体（必须对称量化）
.\.venv-convert\Scripts\optimum-cli.exe export openvino `
  --model models\hymt2-1.8b\source `
  --task text-generation-with-past `
  --weight-format int4 --sym --group-size -1 --ratio 1.0 `
  models\hymt2-1.8b\ov-int4-npu
```

转换完成后 `pack.json` 由脚本写入；也可以手工创建。启动时只认 `pack.json` 中声明且存在 `*.xml` 的变体。

## NPU 说明

- 本机实测：对称 INT4 变体可编译；非对称 INT4 在 NPU 上会报 online partitioning 错误。
- 首次编译约 10–15 秒（本机）；编译缓存位于 `data/cache/ov/`。
- NPU 只启用 1.8B；7B 权重 + KV 较大，建议 GPU/CPU。
- 驱动：Intel NPU Driver（Windows）。`scripts/doctor.py` 会读取 `NPU_DRIVER_VERSION`。

## 7B

```powershell
.\.venv-convert\Scripts\python.exe scripts\prepare_model.py --profile quality
```

7B 的下载与转换约 15GB + 4.3GB；准备好后，在设置页把它设为当前，并选择 GPU/CPU。首次加载可能 10–30 秒。

## 清理

- `models/<id>/source` 是 BF16 原始模型，转换成功后可删除（`--delete-source`）。
- 不要删除 `pack.json`、`LICENSE.txt`、变体目录中的 `openvino_model.xml/bin`、tokenizer 文件。
