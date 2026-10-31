# 第三方组件、模型与许可证

ZC 离线翻译（ZC Translate）本体以 **GNU Affero General Public License v3.0（AGPL-3.0-only）** 发布，全文见仓库根目录 `LICENSE`。

本文件列出项目使用或打包的第三方组件、模型及其许可证。版本号与 `requirements*.txt` 和发行包 `dist/ZCTranslate/_internal` 中的实际版本一致（2026-10 快照）。

> 本文件不是法律意见。再分发前请自行核对上游许可证原文；各组件许可证以其官方发布为准。

## 1. 模型（不随仓库/发行包分发）

| 组件 | 来源 | 许可证 | 说明 |
|---|---|---|---|
| Hy-MT2-1.8B | Tencent-Hunyuan / ModelScope | Apache-2.0 | 默认档（balanced），转换后 OpenVINO INT4 |
| Hy-MT2-7B | Tencent-Hunyuan / ModelScope | Apache-2.0 | 高精度档（quality），可选 |
| SenseVoice INT8 | FunAudioLLM / sherpa-onnx 模型包 | 见模型包 `LICENSE`（指向 FunASR License 章节） | 可选语音识别，应用内下载 |
| Silero VAD | sherpa-onnx 模型包 | 见上游条款 | 可选停顿检测，应用内下载 |

- 模型卡与许可证原文在 `models/<id>/MODEL_CARD.md`、`models/<id>/LICENSE.txt`，这两个文件由 `scripts/prepare_model.py` 从模型仓库复制。
- 本仓库**不包含**模型权重；用户自行下载与转换。
- 如果你分发转换后的 OpenVINO IR：Apache-2.0 要求保留版权与许可声明、附带 NOTICE（如上游提供），并说明你做了量化/IR 转换等修改；Tencent、Hy-MT2 名称与标识归腾讯所有，AGPL-3.0 不授予商标许可。

## 2. 运行时直接依赖（`requirements.txt`）

| 组件 | 版本 | 用途 | 许可证 |
|---|---|---|---|
| fastapi | 0.162.0 | 本地 HTTP API | MIT |
| uvicorn | 0.54.0 | ASGI 服务 | BSD-3-Clause |
| pywebview | 6.2.1 | 桌面窗口（Edge WebView2） | BSD-3-Clause |
| openvino-genai | 2026.4.1.0 | 本地 LLM 推理 | Apache-2.0 |
| pysbd | 0.3.4 | 分句 | MIT |
| sherpa-onnx | 2.0.1 | 本地语音识别与 VAD | Apache-2.0 |
| sounddevice | 0.5.6 | 麦克风采集 | MIT |

## 3. OCR / 文档扩展（`requirements-ocr.txt`）

| 组件 | 版本 | 用途 | 许可证 |
|---|---|---|---|
| rapidocr | 3.10.0 | 图片/扫描件 OCR | Apache-2.0 |
| onnxruntime | 1.31.1 | OCR 推理运行时 | MIT |
| **PyMuPDF** | **2.0** | **PDF 渲染、扫描件译后覆盖** | **AGPL-3.0（或 Artifex 商业许可）** |
| Pillow | 13.0.0 | 图片读取、屏幕截图 | MIT-CMU（HPND） |
| python-docx | 1.2.0 | DOCX 读写 | MIT |

> **PyMuPDF 声明**：PyMuPDF 采用 AGPL-3.0 / Artifex 商业许可双授权。本项目整体已是 AGPL-3.0，与其兼容；发行包内 `pymupdf` 二进制按 AGPL-3.0 分发，源码见 <https://github.com/pymupdf/PyMuPDF>。若你需要闭源或商业分发，请联系 Artifex 获取商业许可，并替换本项目代码（见 `docs/licensing.md`）。
>
> PyMuPDF 2.0 会安装 `pymupdf_layout` 与 `pymupdf4llm` 两个附加包，二者同为 AGPL-3.0；本项目不直接调用，仅作为传递依赖存在。

## 4. 关键传递依赖

| 组件 | 版本 | 许可证 |
|---|---|---|
| numpy | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| protobuf | 7.36.2 | BSD-3-Clause |
| flatbuffers | 25.12.19 | Apache-2.0 |
| openvino / openvino-tokenizers | 2026.4.1 / 2026.4.1.0 | Apache-2.0 |
| openvino-telemetry | 2025.2.0 | Apache-2.0 |
| starlette | 1.10.0 | BSD-3-Clause |
| pydantic / pydantic-core | 2.14.1 / 2.50.1 | MIT |
| pythonnet / clr-loader | 3.2.1 / 0.3.1 | MIT |
| bottle / proxy_tools | 0.13.4 / 0.1.0 | MIT |
| cffi | 2.1.1 | MIT-0 |
| pycparser | 3.12 | BSD-3-Clause |
| opencv-python-headless | 5.0.0.93 | Apache-2.0 |
| shapely | 2.2.0 | BSD-3-Clause |
| pyclipper | 1.4.0 | MIT |
| lxml | 6.1.3 | BSD-3-Clause |
| PyYAML | 6.0.3 | MIT |
| httpx / httpcore / anyio / h11 | 0.28.1 / 1.0.9 / 4.15.1 / 0.16.0 | BSD-3-Clause / MIT |
| urllib3 / requests | 2.8.0 / 2.34.2 | MIT / Apache-2.0 |
| psutil / portalocker | 7.2.2 / 4.4.2 | BSD-3-Clause |
| greenlet | 3.5.6 | MIT AND PSF-2.0 |
| typing_extensions | 4.16.0 | PSF-2.0 |
| certifi | 2026.10.23 | MPL-2.0 |
| tqdm | 4.70.1 | MPL-2.0 AND MIT |
| pymupdf_layout / pymupdf4llm | 2.0 / 2.0 | AGPL-3.0 |

## 5. 开发与测试依赖（`requirements-dev.txt`）

| 组件 | 版本 | 许可证 |
|---|---|---|
| pytest | 9.2.0 | MIT |
| pytest-asyncio | 1.4.1 | Apache-2.0 |
| httpx | 0.28.1 | BSD-3-Clause |
| ruff | 0.17.3 | MIT |
| sacrebleu | 2.6.0 | Apache-2.0 |
| playwright | 1.64.1 | Apache-2.0 |

## 6. 模型转换环境（`requirements-convert.txt`，仅开发机使用）

| 组件 | 版本 | 许可证 |
|---|---|---|
| torch | 2.15.0 | BSD-3-Clause |
| transformers | 5.6.2 | Apache-2.0 |
| optimum / optimum-intel | 2.3.0 / dev（main 分支） | Apache-2.0 |
| nncf | 3.4.0 | Apache-2.0 |
| openvino / openvino-tokenizers | 2026.4.1 / 2026.4.1.0 | Apache-2.0 |
| modelscope | 1.40.2 | Apache-2.0 |
| huggingface_hub / tokenizers / safetensors | 1.33.0 / 0.22.2 / 0.8.0 | Apache-2.0 |
| jinja2 / scipy / scikit-learn / joblib / sympy | — | BSD-3-Clause |

这些包只在准备模型时安装，**不进入发行包**。

## 7. 构建工具

| 组件 | 版本 | 许可证 | 说明 |
|---|---|---|---|
| PyInstaller | 6.22.3 | GPL-2.0-or-later **附特例** | 官方特例明确允许用它构建并分发非自由程序；本项目为 AGPL，同样兼容 |
| NSIS | 3.11 | zlib/libpng 许可 | 仅用于生成 Windows 安装包，不随程序分发 |
| bsdtar（Windows 自带） | 3.8.9 | BSD-2-Clause | 生成 ZIP |

## 8. 系统组件（不随项目分发）

| 组件 | 提供方 | 说明 |
|---|---|---|
| Microsoft Edge WebView2 Runtime | Microsoft | 专有运行时，Windows 11 通常已内置 |
| Intel NPU / GPU 驱动 | Intel | 专有驱动，需用户自行安装 |
| 界面字体 | Microsoft Windows | 使用系统字体，未打包字体文件 |
| 应用图标 | 本项目 | 内联 SVG 与自制 PNG/ICO，不含第三方图标库 |

## 9. 许可证兼容性摘要

- 除 PyMuPDF 系列外，全部依赖为 MIT / BSD / Apache-2.0 / MIT-CMU / PSF-2.0 / MPL-2.0 / zlib 级别，均可与 AGPL-3.0 组合。
- MPL-2.0（`certifi`、`tqdm`）为文件级弱著佐权，与 AGPL-3.0 兼容。
- PyMuPDF 为 AGPL-3.0，与本项目同族，可直接捆绑分发。
- 完整分析、GPL-3.0 可行性讨论与再分发检查清单见 `docs/licensing.md`。

## 10. 免责

机器翻译可能产生错误。法律、医疗、金融、文学等高风险或高专业度内容请人工审校。本项目按 AGPL-3.0 第 15、16 条"不提供担保"分发。
