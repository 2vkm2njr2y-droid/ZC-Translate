# ZC 离线翻译（ZC Translate）

> 本地运行的**中 · 日 · 英**翻译桌面应用：腾讯混元 **Hy-MT2**（Apache-2.0）经 **OpenVINO GenAI** 在 Intel **NPU / GPU / CPU** 上推理，界面为本地 FastAPI + pywebview。除用户主动下载模型外，运行期不访问网络。

**简体中文** ｜ [English](README.en.md) ｜ [日本語](README.ja.md) ｜ [한국어](README.ko.md) ｜ [Español](README.es.md)

![License](https://img.shields.io/badge/license-AGPL--3.0-blue)
![Platform](https://img.shields.io/badge/platform-Windows%2011%20x64-0078D4)
![Python](https://img.shields.io/badge/python-3.12-3776AB)
![Runtime](https://img.shields.io/badge/runtime-OpenVINO%20GenAI-0B5FFF)
![Offline](https://img.shields.io/badge/runtime-offline-success)

![翻译界面](docs/images/translate.png)

> **重要：本仓库与发行包都不包含翻译模型。** 模型约 2.2–4.6 GB，需要你自己下载并转换（或在别处准备好后拷进来），详见 [「模型：需要自己准备与接入」](#模型仓库不含模型需要自己准备与接入)。

---

## 这是什么

- 一个完全跑在本机的翻译器：文本、截图、图片、扫描 PDF、TXT/MD、DOCX，以及语音输入与划词翻译。
- 推理用 Intel **OpenVINO GenAI** 直接加载 **OpenVINO IR** 模型，可选 **NPU / GPU / CPU**，失败会按策略回退；模型常驻内存，关闭主窗口只是隐藏到托盘。
- 前后端都在本机：FastAPI 只监听 `127.0.0.1`，每次启动生成一次性 token；前端是无构建、无 CDN 的原生 HTML/CSS/ES Modules。
- 默认离线：只有"准备模型"和"下载语音模型"两步需要联网。

## 功能特性

### 翻译

- 中、日、英六方向互译；源语言可选自动检测，也可手动指定。
- 流式输出、取消、复制；输入框支持 `.txt` / `.md` 导入，保留实时字数统计（后端约 10 万字上限）。
- 生成参数默认沿用模型卡推荐值（temperature 0.7 / top_p 0.6 / top_k 20，固定随机种子），可切"稳定贪心"。
- **术语库**：固定译法、双向匹配、大小写选项、CSV 导入导出、译后命中校验。
- **翻译记忆**：相同句子（同方向 / 同模型档位 / 同术语库）直接命中，不重复调用模型；本机 SQLite 保存。
- **历史记录**：可搜索、查看原文与译文、载入继续编辑、单条删除、一键清空。

### 截图、图片与文档

- **截图翻译**：调用 Windows 自带截图（Win+Shift+S），本地 OCR 后按文字位置把译文覆盖在原图上；悬停看原文、整体切换原文/译文、点击查看对照。
- **图片翻译**：同一套画布，支持缩放、拖动、适应窗口。
- **文档翻译**：TXT、MD、扫描 PDF、DOCX；默认在**原文件同目录**生成 `原文件名_翻译`，原文件不改。
- DOCX 在后台逐段翻译，显示"已翻译 X/Y 段"与百分比，可随时取消；取消不生成半成品。
- OCR 完全本地（RapidOCR + ONNX Runtime），图片不落盘、不上传。

### 桌面集成

- 固定约 **620×460** 的圆角悬浮小窗，翻译 / 文档翻译 / 术语库 / 历史 / 设置都在小窗内用顶部标签切换。
- **托盘**：关闭窗口只隐藏，进程、数据库与模型继续运行；托盘菜单可打开主窗口、开关划译、退出。
- **划译**：开启后，在支持 Windows UI Automation 的应用里选中文字，会在选区上方显示悬浮译文卡片，并随流式输出实时增高；不模拟 Ctrl+C、不改写剪贴板。
- **单实例**：重复双击启动器只会唤起已有窗口，不会启动第二份模型。

### 语音（可选）

- **语音对话**：持续录音，约 2.5 秒静音后提交当前一句，但会话继续。
- **语音输入**：录一大段，手动停止后把识别文字填入原文框，再由翻译模型翻译。
- 使用 sherpa-onnx 的 SenseVoice（中/日/英/韩/粤）+ Silero VAD，全部本地。

### 数据与隐私

- 设置、术语库、翻译记忆、历史、OpenVINO 编译缓存都在本机：
  - 源码运行：仓库下 `data/`
  - 便携版：包内 `data/`
  - 安装版：`%LOCALAPPDATA%\ZCTranslate\`
- 日志不记录原文/译文；历史与记忆可一键清空；删除 `data/` 即重置。

## 界面

| 翻译 | 设置 | 历史 |
|---|---|---|
| ![翻译](docs/images/translate.png) | ![设置](docs/images/settings.png) | ![历史](docs/images/history.png) |

界面语言目前为**简体中文**。

## 系统要求

| 项目 | 要求 |
|---|---|
| 操作系统 | Windows 11 x64（Windows 10 未验证） |
| 运行时 | Microsoft Edge WebView2 Runtime（Windows 11 通常已内置） |
| 从源码运行 | Python **3.12**（`py` 启动器或 python.org 安装包） |
| 硬件 | Intel NPU / GPU / CPU 任一即可；NPU 需安装 Intel NPU 驱动 |
| 内存 | 建议 16 GB；7B 档建议 32 GB |
| 磁盘 | 运行环境 ≈1.5 GB；1.8B 模型下载 ≈4.1 GB → 产物 ≈2.2 GB；7B 下载 ≈15 GB → 产物 ≈4.6 GB |
| 网络 | 仅"准备模型 / 下载语音模型"时需要 |

## 快速开始

### 方式一：下载发行包（推荐给最终用户）

到 [Releases](https://github.com/2vkm2njr2y-droid/ZC-Translate/releases) 下载：

| 资产 | 说明 |
|---|---|
| `ZCTranslate-0.1.1-win64-setup.exe` | NSIS 安装包：装到 `%LOCALAPPDATA%\Programs\ZCTranslate`，带开始菜单快捷方式与卸载 |
| `ZCTranslate-0.1.1-win64-portable.zip` | 便携版：解压即用，设置与缓存留在包内 `data\` |
| `SHA256SUMS.txt` | 校验和 |

> **安装包/便携包都不含模型**，首次使用前请按下一节准备模型；未找到模型时应用能启动但不能翻译。安装包未做代码签名，SmartScreen 会提示"更多信息 → 仍要运行"。

### 方式二：从源码运行

```powershell
git clone https://github.com/2vkm2njr2y-droid/ZC-Translate.git
cd ZC-Translate

# 1) 一次性准备两个虚拟环境（运行 + 模型转换），需要 Python 3.12
powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1

# 2) 准备翻译模型（详见下一节，需要联网一次）
.\.venv-convert\Scripts\python.exe scripts\prepare_model.py --profile balanced

# 3) OCR / 扫描 PDF（可选，源码运行时需要单独装）
powershell -ExecutionPolicy Bypass -File scripts\setup_ocr.ps1

# 4) 启动
.\启动翻译器.bat          # 正常启动
.\run_dev.ps1             # 开发模式：控制台日志 + DevTools
```

启动后状态栏出现 `NPU · Hy-MT2 1.8B`（或 GPU/CPU）即可翻译；`Ctrl+Enter` 翻译，`Esc` 取消。

## 模型：仓库不含模型，需要自己准备与接入

### 为什么仓库不带模型

- 体积：转换后 2.2 GB（1.8B）/ 4.6 GB（7B），远超 GitHub 单文件 100 MB 限制。
- 模型是独立作品，有自己的许可证与分发义务（Hy-MT2 为 Apache-2.0）。
- 本仓库只提供**下载、转换、接入**的脚本与格式约定，权重由你自行获取。

`models/` 已在 `.gitignore` 中，永远不会被提交。

### 方式 A：一键脚本（推荐）

```powershell
# 1.8B（默认档，NPU/GPU/CPU，下载约 4.1 GB，产出两个 INT4 变体约 2.2 GB）
.\.venv-convert\Scripts\python.exe scripts\prepare_model.py --profile balanced

# 7B（高精度档，GPU/CPU，下载约 15 GB，产出约 4.6 GB）
.\.venv-convert\Scripts\python.exe scripts\prepare_model.py --profile quality

# 可选参数
#   --delete-source   转换成功后删除 bf16 源模型
#   --skip-download   已有源模型时跳过下载
#   --force           删除已有输出重新转换
```

脚本会：

1. 用 ModelScope 下载 `Tencent-Hunyuan/Hy-MT2-1.8B`（或 `-7B`）到 `models/<id>/source/`；
2. 用 optimum-intel 把权重转成 OpenVINO IR 并做 INT4 量化：
   - `ov-int4`：非对称 INT4、group 128（GPU / CPU）
   - `ov-int4-npu`：**对称** INT4、per-channel（NPU 必须用这个）
3. 复制 `LICENSE.txt` 与 `MODEL_CARD.md`，并写入 `pack.json`。

也可以直接双击 **`准备模型.bat`**（等价于 `--profile balanced`）。

### 方式 B：手动转换

```powershell
# 下载
.\.venv-convert\Scripts\modelscope.exe download --model Tencent-Hunyuan/Hy-MT2-1.8B `
  --local_dir models\hymt2-1.8b\source

# GPU / CPU 变体
.\.venv-convert\Scripts\optimum-cli.exe export openvino `
  --model models\hymt2-1.8b\source --task text-generation-with-past `
  --weight-format int4 --group-size 128 --ratio 0.8 `
  models\hymt2-1.8b\ov-int4

# NPU 变体（必须对称量化，否则 NPU 编译报错）
.\.venv-convert\Scripts\optimum-cli.exe export openvino `
  --model models\hymt2-1.8b\source --task text-generation-with-past `
  --weight-format int4 --sym --group-size -1 --ratio 1.0 `
  models\hymt2-1.8b\ov-int4-npu
```

### 方式 C：接入已有的 OpenVINO IR

在别处转换好（或从同配置机器拷来）后，按下面的结构放置：

```
models/
└── hymt2-1.8b/                 # 目录名必须与 MODEL_PROFILES 里的 model_id 对应
    ├── pack.json               # 必需：声明变体与元数据
    ├── LICENSE.txt             # 建议：模型许可证
    ├── MODEL_CARD.md           # 建议：模型卡
    ├── ov-int4/
    │   ├── openvino_model.xml  # 必须存在 *.xml
    │   ├── openvino_model.bin
    │   └── ...tokenizer 文件
    └── ov-int4-npu/            # 可选：没有则不能选 NPU
        └── ...
```

`pack.json` 示例（脚本生成的就是这个格式）：

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
| `variants.<key>.devices` | 该变体适用设备（`NPU` / `GPU` / `CPU`） |
| `license` / `repo` | 展示用元数据，不影响加载 |
| `prompt_version` | 提示词版本，参与翻译记忆的缓存键 |

启动时只认 `pack.json` 中声明、且目录里存在 `*.xml` 的变体；没有 `pack.json` 时会退而查找 `ov-int4` / `ov-int4-npu` 两个目录。

### 模型目录是怎么找到的

固定顺序（`app/backend/config.py`）：

1. 环境变量 `ZC_MODELS_DIR`
2. 程序目录下的 `models/`（源码仓库或 exe 同级）
3. exe 旁的 `models-path.txt`（第一行有效路径，相对路径以 exe 目录为基准）
4. 数据目录下的 `models/`（`%LOCALAPPDATA%\ZCTranslate\models` 或包内 `data\models`）

便携启动器还会额外找**上一级 / 上两级**目录的 `models`，并把命中的目录设为 `ZC_MODELS_DIR`。三种自定义方式任选：

```powershell
# 1) 环境变量
$env:ZC_MODELS_DIR = "D:\models"

# 2) 编辑 exe / 包目录下的 models-path.txt
#    绝对路径，或以该目录为基准的相对路径（如 ..\models）
# 3) 启动参数
.\启动翻译器.bat --models-dir D:\models
```

### 接入自定义模型的限制（请先读）

- **必须是 OpenVINO GenAI `LLMPipeline` 能加载的 IR**（`--task text-generation-with-past`），且目录内带 tokenizer 与 chat template。
- **NPU 只接受对称 INT4 变体**（`ov-int4-npu`）；非对称 INT4 在 NPU 上会报 online partitioning 错误。
- **提示词固定为 Hy-MT2 官方模板**（`prompt_version=hymt2-v1`，见 `app/backend/pipeline/prompts.py`）。换别的翻译模型时要自行验证提示词与输出后处理是否仍然适用。
- **UI 只有两个档位**：`balanced`（`hymt2-1.8b`）与 `quality`（`hymt2-7b`），定义在 `app/backend/config.py` 的 `MODEL_PROFILES`。自定义模型要么**复用这两个目录名**，要么自己新增档位并同步 `app/backend/api/models.py` 的展示逻辑。
- **本项目没有内置任何在线 / 云端翻译 API**，只做本地推理。如果想接 OpenAI 兼容接口或第三方翻译服务，需要自行实现新的 `Engine`（`app/backend/engine/base.py`）并接入 `EngineManager`——这不在当前版本范围内。

### 语音模型（可选）

应用内点"下载语音模型"会从 `k2-fsa/sherpa-onnx` 的 release 下载到 `models/speech/`（联网一次），之后离线可用：

```
models/speech/
├── sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/
│   ├── model.int8.onnx
│   └── tokens.txt
└── silero_vad.onnx
```

也可以手动拷贝同样的文件结构。

### 发行包用户怎么用模型

ZIP / 安装包都**不含** `models/`：

- **便携版**：把准备好的 `models` 文件夹放到 `ZCTranslate.exe` 同级，或编辑同级 `models-path.txt` 指向它。
- **安装版**：默认找 `%LOCALAPPDATA%\ZCTranslate\models`；把 `models` 放进去，或编辑安装目录下的 `models-path.txt`。
- 也可以在任意位置启动时加 `--models-dir <路径>`。

## 使用指南（摘要）

| 功能 | 入口 | 要点 |
|---|---|---|
| 文本翻译 | 翻译页 | 源语言自动/手动，目标语言不能与源语言相同，中间按钮可交换 |
| 截图翻译 | 底部按钮 / `PrintScreen` | 需在 Windows"截图工具"设置里开启"自动复制到剪贴板" |
| 图片/文档 | 文档翻译页 | 生成 `原文件名_翻译`，原文件不改；长文档建议 1.8B |
| 术语库 | 术语库页 | CSV 列：`source,target,case_sensitive,note` |
| 历史/记忆 | 历史页 / 设置 | 只存本机，可清空 |
| 划译 | 设置页或托盘菜单 | 默认关闭，单次最多 4000 字，依赖 UI Automation |
| 语音 | 翻译页麦克风按钮 | 可选下载模型；识别文字仍交给 Hy-MT2 翻译 |

完整操作与故障排查见 [docs/user-guide.md](docs/user-guide.md)；便携版说明见 [docs/portable-usage.txt](docs/portable-usage.txt)。

## 目录结构

```
app/backend/        FastAPI、OpenVINO 引擎、翻译流水线、SQLite、OCR/语音/文档服务
app/frontend/       原生 HTML/CSS/ES Modules（无 npm、无 CDN）
app/shell/          pywebview 窗口、托盘、全局鼠标钩子、UI Automation 划译
app/desktop.py      桌面启动器（随机端口 + 一次性 token）
scripts/            环境准备、模型下载/转换、诊断、基准、评测、打包、离线检查
tests/              单元与集成测试；fixtures/golden 金标集
docs/               架构、模型准备、评测、基准、用户手册、许可证说明
models/             OpenVINO IR 模型包（gitignore，不随仓库分发）
data/               本机数据库、日志、编译缓存（gitignore）
assets/             图标源文件
```

## 开发

```powershell
# 环境（若还没建）
powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1

# 测试 / 静态检查
.\.venv-runtime\Scripts\python -m pytest tests -q
.\.venv-runtime\Scripts\python -m ruff check app tests

# 真实引擎冒烟（需要已准备模型）
.\.venv-runtime\Scripts\python scripts\smoke.py --device NPU

# 设备基准 / 金标集评测
.\.venv-runtime\Scripts\python scripts\benchmark.py --profiles balanced --devices NPU,GPU,CPU
.\.venv-runtime\Scripts\python scripts\evaluate.py --profile balanced --device NPU

# 断网验证
.\.venv-runtime\Scripts\python scripts\offline_check.py --device NPU

# 环境诊断
.\.venv-runtime\Scripts\python scripts\doctor.py
```

架构与设计取舍见 [docs/architecture.md](docs/architecture.md)，模型细节见 [docs/model-setup.md](docs/model-setup.md)，评测见 [docs/evaluation.md](docs/evaluation.md)，基准见 [docs/benchmark.md](docs/benchmark.md)。

## 打包与发布

```powershell
# 便携目录版（dist\ZCTranslate）
powershell -ExecutionPolicy Bypass -File scripts\build_portable.ps1

# 公开发行：重建 + 去掉本机路径与 data\ + 生成 ZIP 与 NSIS 安装包
powershell -ExecutionPolicy Bypass -File scripts\build_release.ps1 -Version 0.1.1
```

- `build_portable.ps1 -Release` 会把 `models-path.txt` 写成相对路径 `models`、清理 `data\`、加入 `LICENSE` / `THIRD_PARTY_NOTICES.md` / 五种语言 README，并额外生成纯 ASCII 的 `Start-ZCTranslate.bat` 兜底启动器。
- `build_release.ps1` 输出到 `dist\release\v<version>\`：
  - `ZCTranslate-<version>-win64-portable.zip`
  - `ZCTranslate-<version>-win64-setup.exe`（NSIS，按用户安装，免 UAC）
  - `SHA256SUMS.txt`
- 打包后的验收：

```powershell
# 启动打包版（示例端口/令牌），再用验收脚本跑一遍 API
Start-Process dist\ZCTranslate\ZCTranslate.exe -ArgumentList '--no-window --port 18031 --token verify --models-dir E:\models'
.\.venv-runtime\Scripts\python scripts\verify_package.py --base-url http://127.0.0.1:18031 --token verify --ocr
```

## 性能与准确率

参考机：HONOR JGC-N / Intel Core Ultra X7 358H / 32 GB LPDDR5 9600 / Intel Arc B390 / Intel NPU / Windows 11 25H2。

| 模型 | 设备 | 加载时间（含首次编译） | 生成速度（50 / 500 字输入） |
|---|---|---:|---:|
| Hy-MT2-1.8B INT4 | NPU | ≈13.3 s（缓存后 ≈1.4 s） | 66 / 62 tok/s |
| Hy-MT2-1.8B INT4 | GPU（Arc B390） | ≈4.2 s | 74 / 68 tok/s |
| Hy-MT2-1.8B INT4 | CPU | ≈2.8 s | 48 / 43 tok/s |
| Hy-MT2-7B INT4 | GPU（Arc B390） | ≈8 s | 21 / 20 tok/s |
| Hy-MT2-7B INT4 | CPU | ≈6 s | 15 / 14 tok/s |

> 速度随输入长度、驱动与后台负载变化；以 `python scripts/benchmark.py` 的结果为准。

首版金标集 6 方向 × 8 句（48 句），指标为 chrF++（只反映字面相似度，最终以人工复核为准）：

| 方向 | 1.8B chrF++ | 7B chrF++ |
|---|---:|---:|
| zh→ja | 53.22 | 58.75 |
| zh→en | 79.28 | 87.24 |
| ja→zh | 46.46 | 57.51 |
| ja→en | 66.15 | 81.86 |
| en→zh | 52.46 | 55.25 |
| en→ja | 49.67 | 66.06 |
| **平均** | **57.87** | **67.78** |

7B 在六个方向全面优于 1.8B，适合质量优先的场景；1.8B 更适合 NPU / 低功耗，术语密集文本建议配置术语库或切 7B。详见 [docs/evaluation.md](docs/evaluation.md)。

## 隐私与安全

- 只绑定 `127.0.0.1`，每次启动生成随机 token，API 校验 `X-ZC-Token`；页面同样需要 token 才能打开。
- CSP `default-src 'self'`，无内联脚本、无外部 CDN；所有用户文本用 `textContent` 渲染。
- SQLite 参数化查询；日志不记录原文/译文；截图只在内存中处理，不写临时图片。
- 历史、术语库、翻译记忆只存本机，可一键清空。
- 网络请求只发生在：准备翻译模型（ModelScope）、下载语音模型（GitHub release）、安装 Python 依赖。

## 已知限制

- **仓库/发行包不含模型**，必须先自行准备；没有模型时应用能启动但不能翻译。
- 界面目前为**简体中文**，暂未提供多语言 UI。
- Hy-MT2-1.8B 在部分敬语、技术术语和长句上会漏译或措辞不自然；可切换 7B，或配置术语库。
- NPU 首次加载需要编译（参考机约 10–15 秒），之后走 `data/cache`；更换驱动或模型会重新编译。
- 7B 不建议在 NPU 上运行；整本长文档用 7B 可能要数十分钟，建议 1.8B。
- OCR 与文档支持图片型/扫描 PDF、TXT/MD、DOCX；复杂 Word 文本框、PPTX、复杂表格版式暂未覆盖。
- 截图翻译依赖 Windows"截图工具"的"自动复制到剪贴板"设置；浏览器回退模式下截图期间页面不会自动隐藏。
- 划译依赖 Windows UI Automation：部分自绘界面、游戏、管理员权限窗口、密码框读不到选区；不支持键盘 Shift+方向键选择。
- 划译默认关闭，单次最多 4000 字；关闭主窗口后需从托盘恢复或退出。
- 安装包未做代码签名，SmartScreen 会提示；便携版/安装版都可被整体移动。安装版卸载时**保留** `%LOCALAPPDATA%\ZCTranslate`（历史、术语库、模型），需要彻底清理请手动删除。
- 自定义模型需要复用内置档位目录名，或修改 `MODEL_PROFILES`（见上文）。

## 许可证

- **本程序：GNU Affero General Public License v3.0（AGPL-3.0-only）**，全文见 [LICENSE](LICENSE)。
  版权：Copyright (C) 2026 ZC Translate contributors。
- **翻译模型：Hy-MT2-1.8B / 7B，Apache-2.0**（模型不随本仓库分发）。
- **第三方组件**：完整清单见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)；兼容性分析与再分发检查清单见 [docs/licensing.md](docs/licensing.md)。

为什么不是 GPL-3.0？项目里 PDF/扫描件依赖 **PyMuPDF（AGPL-3.0）**。GPLv3 虽然能与 AGPLv3 组合，但捆绑 PyMuPDF 的发行包必须同时满足 AGPL 的源码义务；把整个项目定为 AGPL-3.0 是最一致、也最省事的选择。若将来换成 pypdfium2 等宽松库，可以再改回 GPL。详见 [docs/licensing.md](docs/licensing.md)。

## 致谢

- [腾讯混元 Hy-MT2](https://github.com/Tencent-Hunyuan/Hy-MT2)：翻译模型（Apache-2.0）
- [Intel OpenVINO / OpenVINO GenAI](https://github.com/openvinotoolkit/openvino)：本地推理与模型转换
- [RapidOCR](https://github.com/RapidAI/RapidOCR) + [ONNX Runtime](https://github.com/microsoft/onnxruntime)：本地 OCR
- [sherpa-onnx / k2-fsa](https://github.com/k2-fsa/sherpa-onnx)：语音识别与 VAD
- [pywebview](https://github.com/r0x0r/pywebview)、[FastAPI](https://github.com/fastapi/fastapi)、[Uvicorn](https://github.com/encode/uvicorn)

## 贡献与反馈

- 欢迎提 Issue / PR；请**不要**提交 `models/`、`dist/`、`data/` 或任何大文件。
- 提交代码即表示同意以 AGPL-3.0 授权你的贡献。
- 报告问题请附：Windows 版本、设备（NPU/GPU/CPU）、模型档位、`data/logs/app.log` 相关片段（注意先删个人内容）。

## 免责声明

机器翻译可能产生错误。法律、医疗、金融、文学等高风险或高专业度内容请人工审校。本项目按 AGPL-3.0 "不提供担保"分发。
