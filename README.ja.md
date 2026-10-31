# ZC オフライン翻訳

ZC オフライン翻訳は、Windows 上でローカルに動く中国語・日本語・英語の翻訳アプリです。Tencent Hunyuan の Hy-MT2 を OpenVINO で変換し、Intel NPU / GPU / CPU で推論します。画面は pywebview の小さなウィンドウで、バックエンドは FastAPI です。翻訳モデルの準備と音声モデルのダウンロードを除けば実行時にネットワークを使わず、原文と訳文はすべて手元に残ります。

[简体中文](README.md) ｜ [English](README.en.md) ｜ **日本語** ｜ [한국어](README.ko.md) ｜ [Español](README.es.md)

![翻訳画面](docs/images/translate.png)

## 機能

- 中国語・日本語・英語の 6 方向。原文言語は自動判定または手動指定ができ、訳文はストリーミングで表示されるためいつでもキャンセルできます。
- スクリーンショット翻訳は Windows 標準の切り取りツールを呼び出し、ローカル OCR の結果を原文の位置に重ねます。画像翻訳も同じキャンバスを使い、拡大と移動ができます。
- 文書翻訳は TXT、Markdown、スキャン PDF、DOCX に対応します。訳文は元ファイルの隣に `元ファイル名_翻译` として保存され、元ファイルは変更しません。
- 選択範囲翻訳は Windows UI Automation に対応したアプリで使えます。文字を選ぶと選択範囲の上に訳文カードが出ます。Ctrl+C の模擬やクリップボードの書き換えは行いません。
- 音声入力は会話モードとディクテーションモードに対応し、sherpa-onnx の SenseVoice と Silero VAD を使います。認識も翻訳もローカルで完結し、音声モデルだけは別途ダウンロードします。
- 用語集、翻訳メモリ、履歴はローカルの SQLite に保存されます。用語集は CSV の入出力と検索に対応し、履歴は検索でき、翻訳メモリは自動的に照合され、設定から消去できます。

## 動作環境

- Windows 11 x64。Windows 10 は未検証です。
- Microsoft Edge WebView2 Runtime（Windows 11 には通常同梱されています）。
- Intel NPU / GPU / CPU のいずれか。NPU を使うには Intel NPU ドライバーが必要です。
- メモリは 16 GB 推奨。7B を使うなら 32 GB 推奨です。
- ディスク：実行環境は約 1.5 GB、1.8B はダウンロード約 4.1 GB・変換後約 2.2 GB、7B はダウンロード約 15 GB・変換後約 4.6 GB。
- ソースから実行する場合は Python 3.12。

## ダウンロード

[Releases](https://github.com/2vkm2njr2y-droid/ZC-Translate/releases) から次のいずれかを取得します。

- `ZCTranslate-0.1.2-win64-setup.exe`：NSIS インストーラー。現在のユーザーにインストールし、管理者権限は不要です。
- `ZCTranslate-0.1.2-win64-portable.zip`：ポータブル版。解凍してそのまま実行でき、設定とキャッシュはフォルダ内に残ります。
- `SHA256SUMS.txt`：2 つのパッケージのチェックサム。

どちらのパッケージにもモデルは含まれません。インストーラーはコード署名がないため、SmartScreen で「詳細情報 → 実行」を選ぶ必要があります。ポータブル版の使い方は [docs/portable-usage.txt](docs/portable-usage.txt)（中国語）にあります。

## モデルの準備

変換後のモデルは大きすぎて GitHub に置けないため、リポジトリにもリリースパッケージにも重みは含まれていません。初回利用前に一度だけ準備が必要で、この工程ではネットワークを使います。

変換にはリポジトリの `.venv-convert` 環境を使います。まだない場合は、次の「ソースから実行」にある `scripts\setup_env.ps1` を先に実行し（この時点ではモデルは不要です）、戻ってきてください。

```powershell
# 1.8B（既定プロファイル、NPU / GPU / CPU）
.\.venv-convert\Scripts\python.exe scripts\prepare_model.py --profile balanced

# 7B（高精度プロファイル、GPU / CPU 推奨）
.\.venv-convert\Scripts\python.exe scripts\prepare_model.py --profile quality
```

`准备模型.bat` をダブルクリックしても同じです（`--profile balanced` 相当）。

スクリプトは ModelScope から Hy-MT2 をダウンロードし、OpenVINO IR に変換して INT4 量子化を行い、`models/` の下に次のようなフォルダを作ります。

```
models/
└── hymt2-1.8b/
    ├── pack.json
    ├── LICENSE.txt
    ├── MODEL_CARD.md
    ├── ov-int4/          # GPU / CPU
    └── ov-int4-npu/      # NPU 用。対称量子化が必須
```

`ov-int4-npu` は NPU 用の対称 INT4 バリアントです。非対称量子化は NPU ではコンパイルに失敗します。NPU の初回読み込みではモデルをコンパイルするため、検証機で 10〜15 秒ほどかかります。2 回目以降は `data/cache` から読み込みます。

モデルフォルダは次の順に探します：環境変数 `ZC_MODELS_DIR`、プログラム直下の `models/`、実行ファイル横の `models-path.txt`、データフォルダ内の `models/`。ポータブル版はさらに 1〜2 階層上も探します。起動時に `--models-dir <パス>` を渡すこともできます。

ポータブル版は `models` を `ZCTranslate.exe` の隣に、インストール版は `%LOCALAPPDATA%\ZCTranslate\models` に置きます。どちらも `--models-dir` で上書きできます。

手動変換、既存の OpenVINO IR の接続、独自モデルの制限は [docs/model-setup.md](docs/model-setup.md)（中国語）にまとめています。

## ソースから実行

```powershell
git clone https://github.com/2vkm2njr2y-droid/ZC-Translate.git
cd ZC-Translate

# 実行環境とモデル変換環境。Python 3.12 が必要
powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1

# モデルを準備（前の節を参照）
.\.venv-convert\Scripts\python.exe scripts\prepare_model.py --profile balanced

# OCR とスキャン PDF（任意）
powershell -ExecutionPolicy Bypass -File scripts\setup_ocr.ps1

# 起動
.\启动翻译器.bat
```

`run_dev.ps1` は開発モードで、コンソールログと DevTools を表示します。

テストと静的チェック：

```powershell
.\.venv-runtime\Scripts\python -m pytest tests -q
.\.venv-runtime\Scripts\python -m ruff check app tests
```

リリースビルドは `scripts\build_release.ps1`、アーキテクチャの説明は [docs/architecture.md](docs/architecture.md)（中国語）にあります。

## 使い方

起動後、ステータスバーに現在のデバイスとモデルが表示されます。`Ctrl+Enter` で翻訳、`Esc` でキャンセルです。

- スクリーンショット翻訳：下部の「截图翻译」ボタン、または `PrintScreen`。Windows の「切り取りツール」で「クリップボードに自動コピー」を有効にする必要があります。
- 文書翻訳：「文档翻译」タブでファイルを選びます。長い文書は 1.8B がおすすめです。7B はより正確ですが、かなり遅くなります。
- 選択範囲翻訳：設定で有効にします。既定はオフで、1 回 4000 文字までです。
- 用語集：CSV の列は `source,target,case_sensitive,note` です。

詳しい操作とよくある問題は [docs/user-guide.md](docs/user-guide.md)（中国語）にあります。

## 性能

検証機：HONOR JGC-N、Core Ultra X7 358H、32 GB LPDDR5、Arc B390、Windows 11 25H2。

| モデル | デバイス | 読み込み時間 | 生成速度（50 / 500 文字） |
|---|---|---:|---:|
| Hy-MT2 1.8B INT4 | NPU | 約 13.3 秒（キャッシュ後 約 1.4 秒） | 66 / 62 tok/s |
| Hy-MT2 1.8B INT4 | GPU | 約 4.2 秒 | 74 / 68 tok/s |
| Hy-MT2 1.8B INT4 | CPU | 約 2.8 秒 | 48 / 43 tok/s |
| Hy-MT2 7B INT4 | GPU | 約 8 秒 | 21 / 20 tok/s |
| Hy-MT2 7B INT4 | CPU | 約 6 秒 | 15 / 14 tok/s |

速度は入力長、ドライバー、バックグラウンド負荷で変わります。詳細は [docs/benchmark.md](docs/benchmark.md) と [docs/evaluation.md](docs/evaluation.md)（中国語）にあります。

## 既知の制限

- 画面は現在、簡体字中国語のみです。
- 1.8B は敬語、専門用語、長文で訳抜けや不自然な表現が起きることがあります。7B に切り替えるか、用語集を使ってください。
- 7B は NPU には向きません。長い文書を 7B で翻訳すると数十分かかることがあります。
- NPU の初回読み込みではコンパイルが走ります。ドライバーやモデルを変えると再コンパイルされます。
- 選択範囲翻訳は UI Automation に依存します。自作描画の UI、ゲーム、管理者権限のウィンドウ、パスワード欄では選択を読めません。
- インストーラーはコード署名がありません。インストール版をアンインストールしても、`%LOCALAPPDATA%\ZCTranslate` の設定・履歴・モデルは残ります。
- 機械翻訳には誤りがあります。法律、医療、金融、文学などの内容は人が確認してください。

## プライバシー

FastAPI は `127.0.0.1` にだけバインドし、起動ごとに一度きりのトークンを発行します。ログには原文も訳文も記録せず、スクリーンショットはメモリ上だけで処理して一時ファイルを作りません。履歴、用語集、翻訳メモリは一括で消去できます。

## ライセンス

本プロジェクトは GNU Affero General Public License v3.0（AGPL-3.0-only）で公開されています。Copyright (C) 2026 ZC Translate contributors。ライセンス全文は [LICENSE](LICENSE)、著作権と保証の表示は [NOTICE](NOTICE)、第三者コンポーネントは [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) を参照してください。

翻訳モデルの Hy-MT2 は Apache-2.0 で、このリポジトリには含まれません。音声モデルはアプリ内でユーザーがダウンロードするもので、ライセンスは各モデルパッケージに従います。

## 謝辞

- [Tencent Hunyuan Hy-MT2](https://github.com/Tencent-Hunyuan/Hy-MT2)：翻訳モデル
- [Intel OpenVINO / OpenVINO GenAI](https://github.com/openvinotoolkit/openvino)：推論とモデル変換
- [RapidOCR](https://github.com/RapidAI/RapidOCR) + [ONNX Runtime](https://github.com/microsoft/onnxruntime)：ローカル OCR
- [sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx)：音声認識と VAD
- [pywebview](https://github.com/r0x0r/pywebview)、[FastAPI](https://github.com/fastapi/fastapi)、[Uvicorn](https://github.com/encode/uvicorn)

Issue や PR は歓迎します。`models/`、`dist/`、`data/`、ログに含まれる個人情報はコミットしないでください。
