# 许可证与合规说明

本页说明 ZC 离线翻译为什么选择 **AGPL-3.0-only**、"能不能改成 GPL-3.0"、依赖兼容性，以及再分发时需要做什么。它是工程说明，**不是法律意见**。

## 1. 本项目

| 项目 | 内容 |
|---|---|
| 许可证 | GNU Affero General Public License v3.0（AGPL-3.0-only） |
| 许可证全文 | 仓库根目录 `LICENSE`（逐字原文，未修改） |
| 版权 | Copyright (C) 2026 ZC Translate contributors |
| 源代码 | <https://github.com/2vkm2njr2y-droid/ZC-Translate> |

AGPL-3.0 与 GPL-3.0 的主要差别是**第 13 条**：如果修改后的程序让用户通过网络远程交互，也必须向这些用户提供对应源码。本项目只在 `127.0.0.1` 上提供本地服务，正常使用不触发远程交互，但仍按 AGPL 分发源码与许可证。

## 2. 依赖许可一览

完整清单（含版本与用途）见 [`../THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md)。摘要：

| 许可证族 | 代表组件 | 与 AGPL-3.0 组合 |
|---|---|---|
| MIT | fastapi、pydantic、pysbd、sounddevice、onnxruntime、python-docx | ✅ 兼容 |
| BSD-3-Clause | uvicorn、pywebview、starlette、protobuf、lxml、torch | ✅ 兼容 |
| Apache-2.0 | OpenVINO / OpenVINO GenAI、rapidocr、sherpa-onnx、transformers、nncf | ✅ 兼容（Apache-2.0 与 GPLv2 不兼容，但与 GPLv3/AGPLv3 兼容） |
| MIT-CMU / HPND | Pillow | ✅ 兼容 |
| PSF-2.0 | typing_extensions、greenlet（部分） | ✅ 兼容 |
| MPL-2.0 | certifi、tqdm | ✅ 兼容（文件级弱著佐权，可与 AGPL 共存） |
| zlib | NSIS（仅构建工具） | ✅ 兼容 |
| **AGPL-3.0** | **PyMuPDF、pymupdf_layout、pymupdf4llm** | ✅ 同族，可直接捆绑 |
| GPL-2.0-or-later + 特例 | PyInstaller（构建工具） | ✅ 特例允许打包分发非自由程序，对 AGPL 无额外义务 |
| Apache-2.0 | Hy-MT2 模型（不随仓库分发） | ✅ 与 AGPL 组合无冲突 |

**结论：除 PyMuPDF 外，没有第二个著佐权依赖；所有组件都能与 AGPL-3.0 组合。**

## 3. 能不能改用 GPL-3.0？

能，但当前依赖里有一个硬约束：

- **PyMuPDF（含 `pymupdf_layout`、`pymupdf4llm`）是 AGPL-3.0 / Artifex 商业许可双授权。**
- GPLv3 第 13 条与 AGPLv3 第 13 条允许把两者"链接或组合"成一个作品再分发，但**AGPL 部分仍归 AGPL 管**，组合后的发行包也必须满足 AGPL 的源码提供义务。也就是说：仓库代码可以写 GPL-3.0，但**捆绑 PyMuPDF 的安装包/便携包不能只声明 GPL-3.0**。

三条可选路径：

| 方案 | 做法 | 代价 |
|---|---|---|
| A（本项目采用） | **整体 AGPL-3.0** | 代码零改动；企业/闭源场景可能回避 AGPL |
| B | 代码 GPL-3.0，发行包**不捆绑** PyMuPDF，OCR/PDF 由用户自行 `pip install` | 安装包体积小；PDF/扫描件功能默认不可用，体验下降 |
| C | 代码 GPL-3.0，用 **pypdfium2**（Apache-2.0/BSD-3）等宽松库替换 PyMuPDF | 需要重写 PDF 渲染与译后写字（当前用 `page.get_pixmap` + `page.insert_textbox` 与内置 CJK 字体），并补 PDF 回归测试 |
| D | 购买 **Artifex PyMuPDF 商业许可** | 可闭源分发，但本项目代码若保持 GPL/AGPL 仍需开源自身代码 |

如果你将来把 PyMuPDF 换掉（方案 C），把 `LICENSE` 换成 GPL-3.0 原文、更新本页与 README 即可，其余依赖无需变化。

## 4. 发行包合规检查清单

发布 ZIP / NSIS 安装包时，确认：

- [ ] 发行包根目录含 `LICENSE`（AGPL-3.0 全文）与 `THIRD_PARTY_NOTICES.md`。
- [ ] Release 说明给出**同一版本 tag 的源码链接**（GitHub 自动提供 `Source code (zip/tar.gz)`，本项目构建脚本也在仓库内）。
- [ ] 发行包**不含** `models/`（模型是用户单独准备的数据，不属于本程序源码）。
- [ ] 发行包不含 `data/`（本机历史、术语库、翻译记忆属于用户数据）。
- [ ] PyMuPDF 的 AGPL 声明保留（本仓库 `THIRD_PARTY_NOTICES.md` 已包含，并随包分发）。
- [ ] 若修改了源码，在 Release 说明或 `CHANGELOG` 中标注修改点。
- [ ] 不暗示腾讯、Intel、Microsoft 为本项目背书；`ZC 离线翻译` 名称与图标可用于区分来源，但 AGPL 不授予商标许可。

## 5. 模型不是本程序源码

- Hy-MT2 权重为 **Apache-2.0**，由用户从 ModelScope 下载并转换，**不在本仓库、不在发行包**。
- 语音模型（SenseVoice / Silero VAD）同样由用户在应用内下载，许可证以其模型包与上游为准。
- 如果你要单独分发转换后的 OpenVINO IR：需附 Apache-2.0 许可与上游 NOTICE（如有），并说明做了 INT4 量化与 IR 转换。模型名称与标识（Hy-MT2、腾讯混元等）归权利人所有。

## 6. FAQ

**Q：我自己改代码给自己用，需要开源吗？**
A：不需要。AGPL 的义务只在"分发"以及"通过网络向他人提供修改后的程序"时触发。

**Q：公司内部部署给同事用，要开源吗？**
A：只在公司内部网络、不向公司外部提供时，通常不触发 AGPL 第 13 条；但"分发"（例如把安装包发给外部客户）仍需提供源码。具体请咨询法务。

**Q：能把这个项目打包进商业软件卖吗？**
A：可以，但必须整体按 AGPL-3.0 提供源码（含你的修改），并向接收者提供许可证；如果不想开源，需要同时获得本项目版权人许可，并替换 PyMuPDF 或购买其商业许可。

**Q：PyMuPDF 是 AGPL，会不会"传染"我的整个程序？**
A：PyMuPDF 通过 Python 导入并与本程序组合成一体，按 AGPL 的理解整个组合按 AGPL 分发；本项目已选择 AGPL，因此不存在冲突。若你想用其他许可证发布，就需要方案 B/C/D。

**Q：为什么 README 里还提 Apache-2.0 模型？**
A：模型是独立作品，许可证与程序不同；AGPL 管的是本程序，Apache-2.0 管的是模型权重，两者互不覆盖，但分发时各自的声明都要保留。

## 7. 免责

本页仅为工程与合规说明，不构成法律意见。涉及商业分发、闭源集成、专利或商标问题时，请咨询专业律师，并以各组件官方许可证原文为准。
