# 模型准备

## 模型档位

| 档位 | ModelScope | 参数量 | 原始 BF16 | OpenVINO INT4 | 设备 |
|---|---|---|---:|---:|---|
| balanced | `Tencent-Hunyuan/Hy-MT2-1.8B` | 2.0B | 约 4.1 GB | 约 2.2 GB（两个变体） | NPU / GPU / CPU |
| quality | `Tencent-Hunyuan/Hy-MT2-7B` | 8.0B | 约 15 GB | 约 4.6 GB | GPU / CPU |

两个模型的许可证都是 Apache-2.0。模型权重不随仓库分发，需要自己下载和转换。

## 一键准备

```powershell
# 首次会创建 .venv-convert，并安装 optimum-intel、torch、nncf、modelscope
powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1
.\.venv-convert\Scripts\python.exe scripts\prepare_model.py --profile balanced
```

也可以双击 `准备模型.bat`。

## 手动转换

```powershell
# 下载
.\.venv-convert\Scripts\modelscope.exe download --model Tencent-Hunyuan/Hy-MT2-1.8B `
  --local_dir models\hymt2-1.8b\source

# GPU / CPU 变体
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

转换完成后 `pack.json` 由脚本写入，也可以手工创建。启动时只认 `pack.json` 中声明、并且目录里存在 `*.xml` 的变体。

## 模型包结构

目录名要和 `app/backend/config.py` 里 `MODEL_PROFILES` 的 `model_id` 对应（`hymt2-1.8b`、`hymt2-7b`）。

```
models/
└── hymt2-1.8b/
    ├── pack.json               # 必需：变体和元数据
    ├── LICENSE.txt             # 建议：模型许可证
    ├── MODEL_CARD.md           # 建议：模型卡
    ├── ov-int4/
    │   ├── openvino_model.xml  # 必须存在 *.xml
    │   ├── openvino_model.bin
    │   └── ...tokenizer 文件
    └── ov-int4-npu/            # 可选：没有它就不能选 NPU
        └── ...
```

`pack.json` 示例：

```json
{
  "schema": 1,
  "id": "hymt2-1.8b",
  "name": "Hy-MT2 1.8B",
  "repo": "Tencent-Hunyuan/Hy-MT2-1.8B",
  "license": "Apache-2.0",
  "params": "2.0B",
  "description": "默认档：速度快、占用低，适合 NPU / iGPU / CPU。",
  "prompt_version": "hymt2-v1",
  "openvino_version": "2026.4.1",
  "variants": {
    "default": { "path": "ov-int4", "devices": ["GPU", "CPU"] },
    "npu":     { "path": "ov-int4-npu", "devices": ["NPU"] }
  }
}
```

| 字段 | 说明 |
|---|---|
| `id` | 模型包 ID；`hymt2-1.8b` / `hymt2-7b` 与内置档位对应 |
| `variants.<key>.path` | 相对模型包目录的变体子目录，必须含 `openvino_model.xml` |
| `variants.<key>.devices` | 该变体适用的设备（`NPU` / `GPU` / `CPU`） |
| `license` / `repo` | 展示用元数据，不影响加载 |
| `prompt_version` | 提示词版本，参与翻译记忆的缓存键 |

## 程序怎么找模型

固定顺序（`app/backend/config.py`）：

1. 环境变量 `ZC_MODELS_DIR`
2. 程序目录下的 `models/`（源码仓库或 exe 同级）
3. exe 旁的 `models-path.txt`（第一行有效路径，相对路径以 exe 目录为基准）
4. 数据目录下的 `models/`（`%LOCALAPPDATA%\ZCTranslate\models` 或包内 `data\models`）

便携启动器还会额外找上一级、上两级目录的 `models`，并把命中的目录设为 `ZC_MODELS_DIR`。三种自定义方式任选：

```powershell
# 1) 环境变量
$env:ZC_MODELS_DIR = "D:\models"

# 2) 编辑 exe 或包目录下的 models-path.txt
#    绝对路径，或以该目录为基准的相对路径（如 ..\models）

# 3) 启动参数
.\启动翻译器.bat --models-dir D:\models
```

## 在发行包里使用模型

ZIP 和安装包都不含 `models/`：

- 便携版：把准备好的 `models` 文件夹放到 `ZCTranslate.exe` 同级，或编辑同级 `models-path.txt` 指向它。
- 安装版：默认找 `%LOCALAPPDATA%\ZCTranslate\models`；把 `models` 放进去，或编辑安装目录下的 `models-path.txt`。
- 也可以在任意位置启动时加 `--models-dir <路径>`。

## 自定义模型的限制

- 必须是 OpenVINO GenAI `LLMPipeline` 能加载的 IR（`--task text-generation-with-past`），并且目录内带 tokenizer 与 chat template。
- NPU 只接受对称 INT4 变体（`ov-int4-npu`）；非对称 INT4 在 NPU 上会报 online partitioning 错误。
- 提示词固定为 Hy-MT2 官方模板（`prompt_version=hymt2-v1`，见 `app/backend/pipeline/prompts.py`）。换别的翻译模型时，要自行验证提示词和输出后处理是否仍然适用。
- UI 只有两个档位：`balanced`（`hymt2-1.8b`）和 `quality`（`hymt2-7b`），定义在 `app/backend/config.py` 的 `MODEL_PROFILES`。自定义模型要么复用这两个目录名，要么新增档位并同步 `app/backend/api/models.py` 的展示逻辑。
- 本项目没有内置在线或云端翻译 API，只做本地推理。要接 OpenAI 兼容接口或第三方翻译服务，需要实现新的 `Engine`（`app/backend/engine/base.py`）并接入 `EngineManager`，这不在当前版本范围内。

## NPU 说明

- 参考机实测：对称 INT4 变体可以编译；非对称 INT4 在 NPU 上会报 online partitioning 错误。
- 首次编译约 10–15 秒（参考机）；编译缓存位于 `data/cache/ov/`。
- NPU 只建议跑 1.8B；7B 的权重和 KV 缓存较大，建议用 GPU 或 CPU。
- 驱动：Intel NPU Driver（Windows）。`scripts/doctor.py` 会读取 `NPU_DRIVER_VERSION`。

## 7B

```powershell
.\.venv-convert\Scripts\python.exe scripts\prepare_model.py --profile quality
```

7B 的下载与转换约 15 GB + 4.3 GB；准备好后，在设置页把它设为当前，并选择 GPU 或 CPU。首次加载可能 10–30 秒。

## 清理

- `models/<id>/source` 是 BF16 原始模型，转换成功后可删除（`--delete-source`）。
- 不要删除 `pack.json`、`LICENSE.txt`、变体目录中的 `openvino_model.xml` / `.bin` 和 tokenizer 文件。
