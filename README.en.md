# ZC Translate

ZC Translate is a Windows desktop app for translating between Chinese, Japanese and English. It runs Tencent Hunyuan's Hy-MT2 model locally on Intel NPU, GPU or CPU through OpenVINO. The interface is a small pywebview window, with FastAPI behind it. Apart from preparing the translation model and downloading the optional voice model, it does not need a network connection; source text and translations stay on your machine.

[简体中文](README.md) ｜ **English** ｜ [日本語](README.ja.md) ｜ [한국어](README.ko.md) ｜ [Español](README.es.md)

![Translation UI](docs/images/translate.png)

## Features

- Six directions between Chinese, Japanese and English. The source language can be detected automatically or set by hand, and output streams in so you can cancel at any time.
- Screenshot translation calls the built-in Windows snipping tool, runs OCR locally, and paints the translation over the original text. Image translation uses the same canvas, with zoom and pan.
- Document translation covers TXT, Markdown, scanned PDF and DOCX. The result is written next to the original as `originalname_翻译`, and the original file is never modified.
- Select-to-translate works in apps that expose Windows UI Automation. Select some text and a translation card appears above the selection. It does not simulate Ctrl+C or touch the clipboard.
- Voice input supports conversation and dictation modes, using SenseVoice and Silero VAD from sherpa-onnx. Recognition and translation both run locally; the voice model is a separate download.
- Glossaries, translation memory and history live in a local SQLite database. Glossaries support CSV import/export and search, history is searchable, and translation memory is matched automatically and can be cleared in Settings.

## Requirements

- Windows 11 x64. Windows 10 has not been tested.
- Microsoft Edge WebView2 Runtime, usually already installed on Windows 11.
- An Intel NPU, GPU or CPU. Using the NPU requires the Intel NPU driver.
- 16 GB of RAM recommended; 32 GB for the 7B profile.
- Disk: about 1.5 GB for the runtime. The 1.8B model downloads about 4.1 GB and converts to about 2.2 GB; the 7B model downloads about 15 GB and converts to about 4.6 GB.
- Python 3.12 to run from source.

## Download

Get a build from [Releases](https://github.com/2vkm2njr2y-droid/ZC-Translate/releases):

- `ZCTranslate-0.1.2-win64-setup.exe`: NSIS installer for the current user; no administrator rights needed.
- `ZCTranslate-0.1.2-win64-portable.zip`: portable build; unzip and run, with settings and caches kept inside the folder.
- `SHA256SUMS.txt`: checksums for both packages.

Neither package includes a model. The installer is unsigned, so SmartScreen will ask you to click "More info → Run anyway". Portable usage notes are in [docs/portable-usage.txt](docs/portable-usage.txt) (Chinese).

## Preparing a model

The converted model is too large for GitHub, so the repository and release packages contain the download and conversion scripts but not the weights. You need to prepare a model once before the first run; this step needs a network connection.

Conversion uses the `.venv-convert` environment from the repository. If it does not exist yet, run `scripts\setup_env.ps1` from the next section first (you do not need a model for that step), then come back:

```powershell
# 1.8B, default profile, works on NPU / GPU / CPU
.\.venv-convert\Scripts\python.exe scripts\prepare_model.py --profile balanced

# 7B, quality profile, GPU or CPU recommended
.\.venv-convert\Scripts\python.exe scripts\prepare_model.py --profile quality
```

You can also double-click `准备模型.bat`, which is the same as `--profile balanced`.

The script downloads Hy-MT2 from ModelScope, converts it to OpenVINO IR, applies INT4 quantization, and produces a folder like this under `models/`:

```
models/
└── hymt2-1.8b/
    ├── pack.json
    ├── LICENSE.txt
    ├── MODEL_CARD.md
    ├── ov-int4/          # GPU / CPU
    └── ov-int4-npu/      # NPU; must be symmetric quantization
```

`ov-int4-npu` is the symmetric INT4 variant required by the NPU; asymmetric quantization fails to compile there. The first NPU load compiles the model (about 10–15 seconds on the reference machine), after which it is loaded from `data/cache`.

The app looks for models in this order: the `ZC_MODELS_DIR` environment variable, `models/` next to the program, `models-path.txt` next to the executable, and `models/` in the data directory. The portable launcher also checks one or two directories above. You can always pass `--models-dir <path>`.

For the portable build, put `models` next to `ZCTranslate.exe`; for the installed build, put it in `%LOCALAPPDATA%\ZCTranslate\models`. Both accept `--models-dir` as an override.

Manual conversion, plugging in an existing OpenVINO IR, and the limits of custom models are covered in [docs/model-setup.md](docs/model-setup.md) (Chinese).

## Running from source

```powershell
git clone https://github.com/2vkm2njr2y-droid/ZC-Translate.git
cd ZC-Translate

# Runtime and model-conversion environments; requires Python 3.12
powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1

# Prepare a model; see the previous section
.\.venv-convert\Scripts\python.exe scripts\prepare_model.py --profile balanced

# OCR and scanned PDF support, optional
powershell -ExecutionPolicy Bypass -File scripts\setup_ocr.ps1

# Launch
.\启动翻译器.bat
```

`run_dev.ps1` is the development mode; it shows console logs and opens DevTools.

Tests and static checks:

```powershell
.\.venv-runtime\Scripts\python -m pytest tests -q
.\.venv-runtime\Scripts\python -m ruff check app tests
```

Release builds use `scripts\build_release.ps1`; architecture notes are in [docs/architecture.md](docs/architecture.md) (Chinese).

## Usage

Once the app is open, the status bar shows the current device and model. `Ctrl+Enter` translates and `Esc` cancels.

- Screenshot translation: click "截图翻译" at the bottom, or press `PrintScreen`. You need to enable "automatically copy to clipboard" in the Windows Snipping Tool settings.
- Document translation: pick a file on the "文档翻译" tab. For long documents, 1.8B is the better choice; 7B is more accurate but much slower.
- Select-to-translate: enable it in Settings. It is off by default and capped at 4000 characters per selection.
- Glossary: CSV columns are `source,target,case_sensitive,note`.

The full guide and troubleshooting notes are in [docs/user-guide.md](docs/user-guide.md) (Chinese).

## Performance

Reference machine: HONOR JGC-N, Core Ultra X7 358H, 32 GB LPDDR5, Arc B390, Windows 11 25H2.

| Model | Device | Load time | Throughput (50 / 500 characters) |
|---|---|---:|---:|
| Hy-MT2 1.8B INT4 | NPU | about 13.3 s (about 1.4 s cached) | 66 / 62 tok/s |
| Hy-MT2 1.8B INT4 | GPU | about 4.2 s | 74 / 68 tok/s |
| Hy-MT2 1.8B INT4 | CPU | about 2.8 s | 48 / 43 tok/s |
| Hy-MT2 7B INT4 | GPU | about 8 s | 21 / 20 tok/s |
| Hy-MT2 7B INT4 | CPU | about 6 s | 15 / 14 tok/s |

Speed varies with input length, driver and background load. Full data and the evaluation method are in [docs/benchmark.md](docs/benchmark.md) and [docs/evaluation.md](docs/evaluation.md) (Chinese).

## Known limitations

- The interface is Simplified Chinese only.
- 1.8B occasionally misses honorifics, technical terms or long clauses, or produces awkward phrasing; switch to 7B or add glossary entries.
- 7B is not recommended on NPU. A long document can take tens of minutes with 7B.
- The first NPU load compiles the model; changing the driver or the model triggers a recompile.
- Select-to-translate relies on UI Automation. Custom-drawn UIs, games, elevated windows and password fields are not supported.
- The installer is unsigned. Uninstalling the installed build keeps settings, history and models in `%LOCALAPPDATA%\ZCTranslate`.
- Machine translation can be wrong. Have legal, medical, financial or literary content reviewed by a person.

## Privacy

FastAPI binds only to `127.0.0.1` and creates a one-time token on each launch. Logs do not contain source text or translations, and screenshots are processed in memory without temporary files. History, glossaries and translation memory can be cleared in one go.

## License

ZC Translate is released under the GNU Affero General Public License v3.0 (AGPL-3.0-only). Copyright (C) 2026 ZC Translate contributors. The full text is in [LICENSE](LICENSE), the copyright and warranty notice is in [NOTICE](NOTICE), and third-party components are listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

Hy-MT2 is Apache-2.0 and is not distributed with this repository. The voice models are downloaded by the user inside the app and carry their own licenses.

## Acknowledgements

- [Tencent Hunyuan Hy-MT2](https://github.com/Tencent-Hunyuan/Hy-MT2): translation model
- [Intel OpenVINO / OpenVINO GenAI](https://github.com/openvinotoolkit/openvino): inference and model conversion
- [RapidOCR](https://github.com/RapidAI/RapidOCR) + [ONNX Runtime](https://github.com/microsoft/onnxruntime): local OCR
- [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx): speech recognition and VAD
- [pywebview](https://github.com/r0x0r/pywebview), [FastAPI](https://github.com/fastapi/fastapi), [Uvicorn](https://github.com/encode/uvicorn)

Issues and pull requests are welcome. Please do not commit `models/`, `dist/`, `data/` or personal content from logs.
