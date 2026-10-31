# 许可证与合规说明

本页说明 ZC 离线翻译的许可证、第三方依赖和再分发要求。它是工程说明，不是法律意见。

## 本项目

| 项目 | 内容 |
|---|---|
| 许可证 | GNU Affero General Public License v3.0（AGPL-3.0-only） |
| 许可证全文 | 仓库根目录 `LICENSE`（逐字原文，未修改） |
| 版权 | Copyright (C) 2026 ZC Translate contributors |
| 版权与担保声明 | 仓库根目录 `NOTICE` |
| 源代码 | <https://github.com/2vkm2njr2y-droid/ZC-Translate> |

AGPL 第 13 条针对通过网络远程使用修改版程序的场景。本程序只在本机 `127.0.0.1` 上提供界面，正常使用不触发该条；如果把修改版部署成供他人远程访问的服务，就需要向这些用户提供对应源码。

## 依赖许可

完整清单（含版本与用途）见 [`../THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md)。摘要：

| 许可证族 | 代表组件 | 与 AGPL-3.0 组合 |
|---|---|---|
| MIT | fastapi、pydantic、pysbd、sounddevice、onnxruntime、python-docx | 兼容 |
| BSD-3-Clause | uvicorn、pywebview、starlette、protobuf、lxml、torch | 兼容 |
| Apache-2.0 | OpenVINO / OpenVINO GenAI、rapidocr、sherpa-onnx、transformers、nncf | 兼容 |
| MIT-CMU / HPND | Pillow | 兼容 |
| PSF-2.0 | typing_extensions、greenlet（部分） | 兼容 |
| MPL-2.0 | certifi、tqdm | 兼容（文件级弱著佐权） |
| AGPL-3.0 | PyMuPDF、pymupdf_layout、pymupdf4llm | 同族，可直接捆绑 |
| GPL-2.0-or-later + 特例 | PyInstaller（仅构建工具） | 特例允许打包分发，不增加额外义务 |
| Apache-2.0 | Hy-MT2 模型（不随仓库分发） | 与 AGPL 组合无冲突 |

除 PyMuPDF 外，没有第二个著佐权依赖；所有组件都能与 AGPL-3.0 组合。

PyMuPDF 采用 AGPL-3.0 / Artifex 商业许可双授权。本项目整体是 AGPL-3.0，可以直接捆绑；如果要闭源分发，需要购买 Artifex 商业许可，并替换本项目代码。

## 发行包检查清单

发布 ZIP / NSIS 安装包时，确认：

- [ ] 发行包根目录含 `LICENSE`（AGPL-3.0 全文）、`NOTICE`、`THIRD_PARTY_NOTICES.md`。
- [ ] Release 说明给出**同一版本 tag 的源码链接**（GitHub 自动提供 `Source code (zip/tar.gz)`，构建脚本也在仓库内）。
- [ ] 发行包**不含** `models/`（模型是用户单独准备的数据，不属于本程序源码）。
- [ ] 发行包不含 `data/`（本机历史、术语库、翻译记忆属于用户数据）。
- [ ] `licenses/` 目录保留了各依赖的版权与许可证原文；PyMuPDF 的 AGPL 声明不能删。
- [ ] 若修改了源码，在 Release 说明或 `CHANGELOG` 中标注修改点。
- [ ] 不暗示腾讯、Intel、Microsoft 为本项目背书；`ZC 离线翻译` 名称与图标可用于区分来源，但 AGPL 不授予商标许可。

## 模型不是本程序源码

- Hy-MT2 权重为 **Apache-2.0**，由用户从 ModelScope 下载并转换，**不在本仓库、不在发行包**。
- 语音模型（SenseVoice / Silero VAD）同样由用户在应用内下载，许可证以其模型包与上游为准。
- 如果要单独分发转换后的 OpenVINO IR：需附 Apache-2.0 许可与上游 NOTICE（如有），并说明做了 INT4 量化与 IR 转换。模型名称与标识（Hy-MT2、腾讯混元等）归权利人所有。

## 常见问题

**Q：自己改代码给自己用，需要开源吗？**

A：不需要。AGPL 的义务只在分发，以及通过网络向他人提供修改版程序时触发。

**Q：公司内部部署给同事用，要开源吗？**

A：只在公司内部网络、不向公司外部提供时，通常不触发第 13 条；但把安装包发给外部客户仍然属于分发，需要提供源码。具体请咨询法务。

**Q：能把这个项目打包进商业软件卖吗？**

A：可以，但必须整体按 AGPL-3.0 提供源码（含你的修改），并向接收者提供许可证。不想开源的话，需要同时获得本项目版权人许可，并替换 PyMuPDF 或购买其商业许可。

## 免责

本页仅为工程与合规说明，不构成法律意见。涉及商业分发、闭源集成、专利或商标问题时，请咨询专业律师，并以各组件官方许可证原文为准。
