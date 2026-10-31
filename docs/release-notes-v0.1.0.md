# ZC 离线翻译 v0.1.0 / ZC Translate v0.1.0

首个公开版本（Windows 11 x64）。本地运行的中·日·英翻译桌面应用：Hy-MT2（Apache-2.0）+ OpenVINO GenAI，支持 Intel NPU / GPU / CPU。

## 简体中文

### 这是

一个完全跑在本机的翻译器：文本、截图、图片、扫描 PDF、TXT/MD、DOCX，加上语音输入与划词翻译。运行期不联网（只有准备模型/下载语音模型时联网），FastAPI 仅监听 `127.0.0.1`。

### 下载

| 资产 | 说明 |
|---|---|
| `ZCTranslate-0.1.0-win64-setup.exe` | NSIS 安装包：装到 `%LOCALAPPDATA%\Programs\ZCTranslate`，含开始菜单快捷方式与卸载程序，按用户安装、免 UAC |
| `ZCTranslate-0.1.0-win64-portable.zip` | 便携版：解压即用，设置与缓存留在包内 `data\` |
| `SHA256SUMS.txt` | 两个包的 SHA-256 校验和 |

校验方式（PowerShell）：

```powershell
Get-FileHash .\ZCTranslate-0.1.0-win64-portable.zip -Algorithm SHA256
# 与 SHA256SUMS.txt 中对应行比对
```

### ⚠️ 两个包都不包含模型

翻译模型约 2.2 GB（1.8B）/ 4.6 GB（7B），不随仓库或发行包分发。使用前请任选一种方式准备：

```powershell
git clone https://github.com/2vkm2njr2y-droid/ZC-Translate.git
cd ZC-Translate
powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1
.\.venv-convert\Scripts\python.exe scripts\prepare_model.py --profile balanced
```

准备好 `models/` 后：

- 便携版：把 `models` 放到 `ZCTranslate.exe` 同级，或编辑同级 `models-path.txt`。
- 安装版：把 `models` 放进 `%LOCALAPPDATA%\ZCTranslate\models`，或编辑安装目录下的 `models-path.txt`。
- 也可以用 `--models-dir <路径>` 启动。

完整说明见仓库 README 的“模型：仓库不含模型，需要自己准备与接入”一节。

### 系统要求

Windows 11 x64、WebView2 Runtime（Win11 通常自带）、Python 3.12（仅源码运行需要）、Intel NPU/GPU/CPU 任一；16 GB 内存建议。

### 主要功能

- 中·日·英六方向互译，流式输出、取消、长文本、术语库、翻译记忆、历史记录。
- 截图 / 图片 / 扫描 PDF / TXT / MD / DOCX 翻译，译后按原位置覆盖，原文件不改。
- 语音对话与语音输入（SenseVoice + Silero VAD，本地）。
- 固定小窗 + 系统托盘 + 划词翻译（UI Automation，不模拟 Ctrl+C）。
- 自动设备选择与回退：NPU → GPU → CPU。

### 已知问题

- 安装包未做代码签名，SmartScreen 会提示“更多信息 → 仍要运行”。
- 界面目前仅简体中文。
- 没有模型时程序能启动，但翻译、截图与文档翻译都会提示模型未安装。
- 7B 不建议在 NPU 上运行；长文档建议 1.8B。

### 许可证

本项目以 **AGPL-3.0-only** 发布，源码即本仓库对应 tag：<https://github.com/2vkm2njr2y-droid/ZC-Translate/tree/v0.1.0>。
翻译模型 Hy-MT2 为 Apache-2.0；第三方组件见仓库 `THIRD_PARTY_NOTICES.md` 与 `docs/licensing.md`。

---

## English

### What this is

A fully local Chinese · Japanese · English translator for Windows 11: text, screenshots, images, scanned PDFs, TXT/MD/DOCX, voice input and select-to-translate. No network at runtime (only model preparation / voice-model download), and FastAPI binds `127.0.0.1` only.

### Downloads

| Asset | Description |
|---|---|
| `ZCTranslate-0.1.0-win64-setup.exe` | NSIS installer; installs per-user to `%LOCALAPPDATA%\Programs\ZCTranslate` with Start Menu shortcuts and an uninstaller (no UAC) |
| `ZCTranslate-0.1.0-win64-portable.zip` | Portable; unzip and run, settings/caches stay in the bundled `data\` |
| `SHA256SUMS.txt` | SHA-256 checksums for both packages |

### ⚠️ No models are bundled

The translation model is ~2.2 GB (1.8B) / ~4.6 GB (7B) and is not distributed with the repo or the release assets. Prepare it first:

```powershell
git clone https://github.com/2vkm2njr2y-droid/ZC-Translate.git
cd ZC-Translate
powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1
.\.venv-convert\Scripts\python.exe scripts\prepare_model.py --profile balanced
```

Then either put `models` next to `ZCTranslate.exe` (portable), into `%LOCALAPPDATA%\ZCTranslate\models` (installed), or start the app with `--models-dir <path>`. See the “Models” section of the README for details.

### Requirements

Windows 11 x64, WebView2 Runtime (usually preinstalled), Python 3.12 only for source runs, any Intel NPU/GPU/CPU; 16 GB RAM recommended.

### Highlights

- Six directions between Chinese, Japanese and English; streaming, cancel, long text, glossary, translation memory, history.
- Screenshot / image / scanned PDF / TXT / MD / DOCX translation with in-place overlay; originals are never modified.
- Local voice conversation and dictation (SenseVoice + Silero VAD).
- Compact window, tray, select-to-translate via Windows UI Automation (never simulates Ctrl+C).
- Automatic device selection with fallback: NPU → GPU → CPU.

### Known issues

- The installer is unsigned; SmartScreen will ask you to click “More info → Run anyway”.
- UI is Simplified Chinese only.
- Without a model the app starts, but translation, screenshots and documents report a missing model.
- 7B is not recommended on NPU; use 1.8B for long documents.

### License

This project is released under **AGPL-3.0-only**; the corresponding source is this tag: <https://github.com/2vkm2njr2y-droid/ZC-Translate/tree/v0.1.0>.
The Hy-MT2 model is Apache-2.0. Third-party notices: `THIRD_PARTY_NOTICES.md` and `docs/licensing.md`.
