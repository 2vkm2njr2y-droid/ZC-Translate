# ZC 오프라인 번역 (ZC Translate)

> **중국어 · 일본어 · 영어**를 로컬에서 번역하는 데스크톱 앱입니다. Tencent Hunyuan **Hy-MT2**(Apache-2.0)를 **OpenVINO GenAI**로 Intel **NPU / GPU / CPU**에서 추론하며, UI는 로컬 FastAPI + pywebview입니다. 사용자가 직접 모델을 내려받는 경우를 제외하면 실행 중 네트워크에 접속하지 않습니다.

[简体中文](README.md) ｜ [English](README.en.md) ｜ [日本語](README.ja.md) ｜ **한국어** ｜ [Español](README.es.md)

![License](https://img.shields.io/badge/license-AGPL--3.0-blue)
![Platform](https://img.shields.io/badge/platform-Windows%2011%20x64-0078D4)
![Python](https://img.shields.io/badge/python-3.12-3776AB)
![Runtime](https://img.shields.io/badge/runtime-OpenVINO%20GenAI-0B5FFF)
![Offline](https://img.shields.io/badge/runtime-offline-success)

![번역 화면](docs/images/translate.png)

> **중요: 이 저장소와 릴리스 패키지에는 번역 모델이 포함되어 있지 않습니다.** 모델은 2.2~4.6 GB이며 직접 내려받아 변환하거나(또는 이미 준비된 환경에서 복사해야) 합니다. 자세한 내용은 [「모델은 직접 준비하고 연결해야 합니다」](#모델은-직접-준비하고-연결해야-합니다)를 참고하세요.

---

## 무엇인가

- 완전히 로컬에서 동작하는 번역기: 텍스트, 스크린샷, 이미지, 스캔 PDF, TXT/MD, DOCX, 음성 입력, 선택 영역 번역.
- 추론은 Intel **OpenVINO GenAI**가 **OpenVINO IR** 모델을 로드하며 **NPU / GPU / CPU**를 선택할 수 있습니다. 실패 시 정책에 따라 폴백하고, 모델은 메모리에 상주합니다(창을 닫아도 트레이에 남음).
- 프런트엔드와 백엔드 모두 로컬: FastAPI는 `127.0.0.1`에만 바인딩하고 실행할 때마다 일회용 토큰을 발급합니다. UI는 빌드 단계와 CDN이 없는 순수 HTML/CSS/ES Modules입니다.
- 기본은 오프라인: "모델 준비"와 "음성 모델 다운로드"에서만 네트워크를 사용합니다.

## 기능

### 번역

- 중국어·일본어·영어 6개 방향. 원문 언어는 자동 감지 또는 수동 지정.
- 스트리밍 출력, 취소, 복사, `.txt` / `.md` 가져오기, 실시간 글자 수(백엔드 약 10만 자 제한).
- 생성 파라미터는 모델 카드 권장값(temperature 0.7 / top_p 0.6 / top_k 20, 시드 고정)이며 "안정 그리디" 옵션도 있습니다.
- **용어집**: 고정 번역, 양방향 매칭, 대소문자 구분, CSV 가져오기/내보내기, 번역 후 일치 검증.
- **번역 메모리**: 같은 문장(같은 방향·모델·용어집)은 모델을 호출하지 않고 재사용하며 로컬 SQLite에 저장됩니다.
- **기록**: 검색, 원문/번역 보기, 편집기로 다시 불러오기, 개별 삭제, 전체 삭제.

### 스크린샷·이미지·문서

- **스크린샷 번역**: Windows 기본 캡처(Win+Shift+S)를 호출하고 로컬 OCR 결과를 바탕으로 원문 위치에 번역문을 겹쳐 표시합니다. 마우스를 올리면 원문, 원문/번역 일괄 전환, 클릭 시 대조 보기.
- **이미지 번역**: 같은 캔버스에서 확대, 이동, 창에 맞추기 지원.
- **문서 번역**: TXT, MD, 스캔 PDF, DOCX. **원본과 같은 폴더**에 `원본이름_翻译`를 만들고 원본은 수정하지 않습니다.
- DOCX는 백그라운드에서 문단 단위로 번역하며 "X/Y 문단" 진행률과 취소를 제공합니다. 취소 시 반쯤 만들어진 파일을 남기지 않습니다.
- OCR은 전부 로컬(RapidOCR + ONNX Runtime)이며 이미지는 디스크에 저장하거나 업로드하지 않습니다.

### 데스크톱 통합

- 약 **620×460** 고정 라운드 플로팅 창. 번역/문서 번역/용어집/기록/설정을 상단 탭으로 전환합니다.
- **트레이**: 창을 닫아도 숨겨질 뿐 프로세스·DB·모델은 계속 동작합니다. 트레이 메뉴에서 창 복원, 선택 영역 번역 켜기/끄기, 종료가 가능합니다.
- **선택 영역 번역**: 활성화하면 Windows UI Automation을 지원하는 앱에서 글자를 선택할 때 선택 영역 위에 번역 카드가 뜨고 스트리밍에 따라 높이가 늘어납니다. Ctrl+C를 흉내 내지 않고 클립보드를 변경하지 않습니다.
- **단일 인스턴스**: 다시 실행하면 기존 창을 불러올 뿐 두 번째 모델을 띄우지 않습니다.

### 음성(선택)

- **대화 모드**: 마이크를 계속 사용하며 약 2.5초 무음이면 그 한 문장만 전송하고 세션은 유지합니다.
- **받아쓰기 모드**: 긴 문장을 녹음하고 수동으로 중지하면 인식 결과를 원문 상자에 넣은 뒤 일반 번역 흐름을 탑니다.
- sherpa-onnx의 SenseVoice(중/일/영/한/광둥어) + Silero VAD를 사용하며 모두 로컬입니다.

### 데이터와 개인정보

- 설정, 용어집, 번역 메모리, 기록, OpenVINO 컴파일 캐시는 모두 로컬에 있습니다.
  - 소스 실행: 저장소 아래 `data/`
  - 포터블: 폴더 안 `data/`
  - 설치 버전: `%LOCALAPPDATA%\ZCTranslate\`
- 로그에 원문/번역문을 기록하지 않습니다. 기록과 메모리는 한 번에 지울 수 있고 `data/`를 삭제하면 초기화됩니다.

## 화면

| 번역 | 설정 | 기록 |
|---|---|---|
| ![번역](docs/images/translate.png) | ![설정](docs/images/settings.png) | ![기록](docs/images/history.png) |

UI는 현재 **중국어 간체만** 지원합니다.

## 시스템 요구 사항

| 항목 | 요구 사항 |
|---|---|
| OS | Windows 11 x64(Windows 10 미검증) |
| 런타임 | Microsoft Edge WebView2 Runtime(Windows 11은 보통 기본 포함) |
| 소스 실행 | Python **3.12**(py 런처 또는 python.org 설치 프로그램) |
| 하드웨어 | Intel NPU / GPU / CPU 중 하나. NPU는 Intel NPU 드라이버 필요 |
| 메모리 | 16 GB 권장, 7B는 32 GB 권장 |
| 디스크 | 실행 환경 약 1.5 GB, 1.8B 다운로드 약 4.1 GB → 산출물 약 2.2 GB, 7B 약 15 GB → 약 4.6 GB |
| 네트워크 | "모델 준비" / "음성 모델 다운로드" 때만 |

## 빠른 시작

### 방법 1: 릴리스 패키지(최종 사용자)

[Releases](https://github.com/2vkm2njr2y-droid/ZC-Translate/releases)에서 받으세요.

| 자산 | 설명 |
|---|---|
| `ZCTranslate-0.1.1-win64-setup.exe` | NSIS 설치 프로그램: `%LOCALAPPDATA%\Programs\ZCTranslate`에 설치, 시작 메뉴와 제거 프로그램 포함 |
| `ZCTranslate-0.1.1-win64-portable.zip` | 포터블: 압축을 풀고 실행, 설정과 캐시는 동봉된 `data\`에 저장 |
| `SHA256SUMS.txt` | 체크섬 |

> **설치 프로그램과 포터블 모두 모델을 포함하지 않습니다.** 처음 사용하기 전에 아래 절차로 모델을 준비하세요. 모델이 없으면 앱은 실행되지만 번역할 수 없습니다. 설치 프로그램은 코드 서명이 없어 SmartScreen에서 "추가 정보 → 실행"이 필요합니다.

### 방법 2: 소스에서 실행

```powershell
git clone https://github.com/2vkm2njr2y-droid/ZC-Translate.git
cd ZC-Translate

# 1) 가상 환경 두 개 생성(실행용 + 모델 변환용). Python 3.12 필요
powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1

# 2) 번역 모델 준비(다음 절 참고, 최초 1회 네트워크 필요)
.\.venv-convert\Scripts\python.exe scripts\prepare_model.py --profile balanced

# 3) OCR / 스캔 PDF(선택, 소스 실행 시 별도 설치)
powershell -ExecutionPolicy Bypass -File scripts\setup_ocr.ps1

# 4) 실행
.\启动翻译器.bat          # 일반 실행(파일 이름은 중국어)
.\run_dev.ps1             # 개발 모드: 콘솔 로그 + DevTools
```

상태 표시줄에 `NPU · Hy-MT2 1.8B`(또는 GPU/CPU)가 나오면 번역할 수 있습니다. `Ctrl+Enter` 번역, `Esc` 취소.

## 모델은 직접 준비하고 연결해야 합니다

### 저장소에 모델이 없는 이유

- 크기: 변환 후 2.2 GB(1.8B) / 4.6 GB(7B)로 GitHub의 파일당 100 MB 제한을 크게 넘습니다.
- 모델은 별도 저작물이며 자체 라이선스와 배포 의무가 있습니다(Hy-MT2는 Apache-2.0).
- 이 저장소는 **다운로드·변환·연결** 스크립트와 형식 규약만 제공하며 가중치는 직접 받아야 합니다.

`models/`는 `.gitignore`에 있어 커밋되지 않습니다.

### 방법 A: 원클릭 스크립트(권장)

```powershell
# 1.8B(기본 프로필, NPU/GPU/CPU, 다운로드 약 4.1 GB, INT4 두 종 산출 약 2.2 GB)
.\.venv-convert\Scripts\python.exe scripts\prepare_model.py --profile balanced

# 7B(고정밀 프로필, GPU/CPU, 다운로드 약 15 GB, 산출 약 4.6 GB)
.\.venv-convert\Scripts\python.exe scripts\prepare_model.py --profile quality

# 추가 옵션:
#   --delete-source   변환 후 bf16 원본 삭제
#   --skip-download   기존 원본 재사용
#   --force           기존 출력 삭제 후 재변환
```

스크립트는 다음을 수행합니다.

1. ModelScope에서 `Tencent-Hunyuan/Hy-MT2-1.8B`(또는 `-7B`)를 `models/<id>/source/`로 다운로드
2. optimum-intel로 OpenVINO IR 변환 및 INT4 양자화
   - `ov-int4`: 비대칭 INT4, group 128(GPU / CPU)
   - `ov-int4-npu`: **대칭** INT4, per-channel(NPU는 반드시 이쪽)
3. `LICENSE.txt`와 `MODEL_CARD.md` 복사, `pack.json` 작성

**`准备模型.bat`**(중국어 파일 이름)을 더블클릭해도 같습니다(`--profile balanced`와 동일).

### 방법 B: 수동 변환

```powershell
# 다운로드
.\.venv-convert\Scripts\modelscope.exe download --model Tencent-Hunyuan/Hy-MT2-1.8B `
  --local_dir models\hymt2-1.8b\source

# GPU / CPU용
.\.venv-convert\Scripts\optimum-cli.exe export openvino `
  --model models\hymt2-1.8b\source --task text-generation-with-past `
  --weight-format int4 --group-size 128 --ratio 0.8 `
  models\hymt2-1.8b\ov-int4

# NPU용(대칭 양자화 필수, 비대칭이면 NPU 컴파일 실패)
.\.venv-convert\Scripts\optimum-cli.exe export openvino `
  --model models\hymt2-1.8b\source --task text-generation-with-past `
  --weight-format int4 --sym --group-size -1 --ratio 1.0 `
  models\hymt2-1.8b\ov-int4-npu
```

### 방법 C: 기존 OpenVINO IR 연결

다른 환경에서 변환한 패키지를 다음 구조로 배치합니다.

```
models/
└── hymt2-1.8b/                 # 폴더 이름은 MODEL_PROFILES의 model_id와 일치해야 함
    ├── pack.json               # 필수: 변형과 메타데이터
    ├── LICENSE.txt             # 권장: 모델 라이선스
    ├── MODEL_CARD.md           # 권장: 모델 카드
    ├── ov-int4/
    │   ├── openvino_model.xml  # *.xml 필요
    │   ├── openvino_model.bin
    │   └── ...토크나이저 파일
    └── ov-int4-npu/            # 선택: 없으면 NPU 선택 불가
        └── ...
```

`pack.json` 예시(스크립트가 생성하는 형식과 동일):

```json
{
  "schema": 1,
  "id": "hymt2-1.8b",
  "name": "Hy-MT2 1.8B",
  "repo": "Tencent-Hunyuan/Hy-MT2-1.8B",
  "license": "Apache-2.0",
  "params": "2.0B",
  "description": "기본 프로필: 빠르고 가벼움. NPU / iGPU / CPU에 적합.",
  "prompt_version": "hymt2-v1",
  "openvino_version": "2026.4.1",
  "variants": {
    "default": { "path": "ov-int4", "devices": ["GPU", "CPU"] },
    "npu":     { "path": "ov-int4-npu", "devices": ["NPU"] }
  }
}
```

| 필드 | 의미 |
|---|---|
| `id` | 모델 팩 ID. `hymt2-1.8b` / `hymt2-7b`가 내장 프로필과 대응 |
| `variants.<key>.path` | 팩 기준 상대 경로. `openvino_model.xml` 필요 |
| `variants.<key>.devices` | 해당 변형을 쓸 수 있는 장치(`NPU` / `GPU` / `CPU`) |
| `license` / `repo` | 표시용 메타데이터 |
| `prompt_version` | 프롬프트 버전. 번역 메모리 캐시 키에 포함 |

시작할 때는 `pack.json`에 선언되고 폴더에 `*.xml`이 있는 변형만 로드합니다. `pack.json`이 없으면 `ov-int4` / `ov-int4-npu` 폴더를 찾습니다.

### 모델 폴더 탐색 순서

고정 순서(`app/backend/config.py`):

1. 환경 변수 `ZC_MODELS_DIR`
2. 프로그램 폴더의 `models/`(저장소 루트 또는 exe 옆)
3. exe 옆 `models-path.txt`(첫 유효 줄, 상대 경로는 exe 폴더 기준)
4. 데이터 폴더의 `models/`(`%LOCALAPPDATA%\ZCTranslate\models`, 포터블은 `data\models`)

포터블 런처는 한두 단계 위의 `models`도 찾아 `ZC_MODELS_DIR`로 설정합니다. 덮어쓰는 방법은 세 가지입니다.

```powershell
# 1) 환경 변수
$env:ZC_MODELS_DIR = "D:\models"

# 2) exe 옆 models-path.txt 편집(절대 경로 또는 그 폴더 기준 상대 경로)
# 3) 실행 인자
.\启动翻译器.bat --models-dir D:\models
```

### 사용자 모델을 연결할 때의 제한

- OpenVINO GenAI `LLMPipeline`으로 로드 가능한 IR(`--task text-generation-with-past`)이어야 하며 토크나이저와 chat template이 포함되어야 합니다.
- **NPU는 대칭 INT4만** 허용합니다(`ov-int4-npu`). 비대칭 INT4는 NPU에서 online partitioning 오류가 납니다.
- **프롬프트는 Hy-MT2 공식 템플릿으로 고정**되어 있습니다(`prompt_version=hymt2-v1`, `app/backend/pipeline/prompts.py`). 다른 모델로 바꾸면 프롬프트와 후처리를 직접 검증해야 합니다.
- **UI 프로필은 두 개뿐**: `balanced`(`hymt2-1.8b`)와 `quality`(`hymt2-7b`)이며 `app/backend/config.py`의 `MODEL_PROFILES`에 정의되어 있습니다. 사용자 모델은 이 폴더 이름을 재사용하거나 프로필을 추가하고 `app/backend/api/models.py`의 노출도 수정해야 합니다.
- **온라인/클라우드 번역 API는 내장되어 있지 않습니다.** 번역은 로컬 추론만 수행합니다. OpenAI 호환 API나 외부 번역 서비스를 쓰려면 새 `Engine`(`app/backend/engine/base.py`)을 구현하고 `EngineManager`에 연결해야 하며, 이번 버전 범위 밖입니다.

### 음성 모델(선택)

앱에서 "음성 모델 다운로드"를 누르면 `k2-fsa/sherpa-onnx` 릴리스에서 `models/speech/`로 받습니다(최초 1회 네트워크). 이후에는 오프라인으로 동작합니다.

```
models/speech/
├── sherpa-onnx-sense-voice-zh-en-ja-ko-yue-int8-2024-07-17/
│   ├── model.int8.onnx
│   └── tokens.txt
└── silero_vad.onnx
```

같은 구조로 직접 복사해도 됩니다.

### 릴리스 패키지에서 모델 사용

ZIP과 설치 프로그램 모두 `models/`를 포함하지 않습니다.

- **포터블**: 준비한 `models` 폴더를 `ZCTranslate.exe` 옆에 두거나 같은 위치의 `models-path.txt`를 수정합니다.
- **설치 버전**: 기본적으로 `%LOCALAPPDATA%\ZCTranslate\models`를 찾습니다. 그곳에 두거나 설치 폴더의 `models-path.txt`를 수정하세요.
- 어느 형태든 `--models-dir <경로>`로 지정할 수 있습니다.

## 사용법 요약

| 기능 | 위치 | 요점 |
|---|---|---|
| 텍스트 번역 | 번역 탭 | 원문 언어 자동/수동, 대상 언어는 원문과 같을 수 없음, 가운데 버튼으로 교체 |
| 스크린샷 | 하단 버튼 / `PrintScreen` | Windows "캡처 도구"에서 "클립보드에 자동 복사"를 켜야 함 |
| 이미지/문서 | 문서 번역 탭 | `원본이름_翻译` 생성, 원본은 변경하지 않음, 긴 문서는 1.8B 권장 |
| 용어집 | 용어집 탭 | CSV 열: `source,target,case_sensitive,note` |
| 기록/메모리 | 기록 탭 / 설정 | 로컬 전용, 전체 삭제 가능 |
| 선택 영역 번역 | 설정 또는 트레이 메뉴 | 기본 꺼짐, 1회 4000자, UI Automation 필요 |
| 음성 | 마이크 버튼 | 모델 선택적 다운로드, 인식 결과는 Hy-MT2가 번역 |

자세한 사용법과 문제 해결: [docs/user-guide.md](docs/user-guide.md)(중국어). 포터블 설명: [docs/portable-usage.txt](docs/portable-usage.txt)(중국어).

## 디렉터리 구조

```
app/backend/        FastAPI, OpenVINO 엔진, 번역 파이프라인, SQLite, OCR/음성/문서 서비스
app/frontend/       순수 HTML/CSS/ES Modules(npm 없음, CDN 없음)
app/shell/          pywebview 창, 트레이, 전역 마우스 훅, UI Automation 선택 영역
app/desktop.py      데스크톱 런처(임의 포트 + 일회용 토큰)
scripts/            환경 준비, 모델 다운로드/변환, 진단, 벤치마크, 평가, 패키징, 오프라인 검사
tests/              단위·통합 테스트, fixtures/golden 평가 세트
docs/               아키텍처, 모델 준비, 평가, 벤치마크, 사용자 가이드, 라이선스
models/             OpenVINO IR 모델 팩(gitignore, 배포 대상 아님)
data/               로컬 DB, 로그, 컴파일 캐시(gitignore)
assets/             아이콘 원본
```

## 개발

```powershell
# 환경(아직 없다면)
powershell -ExecutionPolicy Bypass -File scripts\setup_env.ps1

# 테스트 / 정적 검사
.\.venv-runtime\Scripts\python -m pytest tests -q
.\.venv-runtime\Scripts\python -m ruff check app tests

# 실제 엔진 스모크 테스트(모델 준비 필요)
.\.venv-runtime\Scripts\python scripts\smoke.py --device NPU

# 장치 벤치마크 / 골든셋 평가
.\.venv-runtime\Scripts\python scripts\benchmark.py --profiles balanced --devices NPU,GPU,CPU
.\.venv-runtime\Scripts\python scripts\evaluate.py --profile balanced --device NPU

# 오프라인 검증
.\.venv-runtime\Scripts\python scripts\offline_check.py --device NPU

# 환경 진단
.\.venv-runtime\Scripts\python scripts\doctor.py
```

아키텍처: [docs/architecture.md](docs/architecture.md), 모델: [docs/model-setup.md](docs/model-setup.md), 평가: [docs/evaluation.md](docs/evaluation.md), 벤치마크: [docs/benchmark.md](docs/benchmark.md)(문서는 중국어).

## 패키징과 릴리스

```powershell
# 포터블 폴더 빌드(dist\ZCTranslate)
powershell -ExecutionPolicy Bypass -File scripts\build_portable.ps1

# 공개 릴리스: 재빌드 + 로컬 경로와 data\ 제거 + ZIP과 NSIS 설치 프로그램 생성
powershell -ExecutionPolicy Bypass -File scripts\build_release.ps1 -Version 0.1.1
```

- `build_portable.ps1 -Release`는 `models-path.txt`를 상대 경로 `models`로 쓰고, `data\`를 지우고, `LICENSE` / `THIRD_PARTY_NOTICES.md` / 5개 언어 README를 넣으며, ASCII 전용 `Start-ZCTranslate.bat`도 추가합니다.
- `build_release.ps1` 출력: `dist\release\v<version>\`
  - `ZCTranslate-<version>-win64-portable.zip`
  - `ZCTranslate-<version>-win64-setup.exe`(NSIS, 사용자 단위 설치, UAC 없음)
  - `SHA256SUMS.txt`
- 패키지 검증:

```powershell
Start-Process dist\ZCTranslate\ZCTranslate.exe -ArgumentList '--no-window --port 18031 --token verify --models-dir E:\models'
.\.venv-runtime\Scripts\python scripts\verify_package.py --base-url http://127.0.0.1:18031 --token verify --ocr
```

## 성능과 정확도

참고 장비: HONOR JGC-N / Intel Core Ultra X7 358H / 32 GB LPDDR5 9600 / Intel Arc B390 / Intel NPU / Windows 11 25H2.

| 모델 | 장치 | 로드 시간(최초 컴파일 포함) | 생성 속도(50 / 500자 입력) |
|---|---|---:|---:|
| Hy-MT2-1.8B INT4 | NPU | 약 13.3초(캐시 후 약 1.4초) | 66 / 62 tok/s |
| Hy-MT2-1.8B INT4 | GPU(Arc B390) | 약 4.2초 | 74 / 68 tok/s |
| Hy-MT2-1.8B INT4 | CPU | 약 2.8초 | 48 / 43 tok/s |
| Hy-MT2-7B INT4 | GPU(Arc B390) | 약 8초 | 21 / 20 tok/s |
| Hy-MT2-7B INT4 | CPU | 약 6초 | 15 / 14 tok/s |

> 속도는 입력 길이, 드라이버, 백그라운드 부하에 따라 달라집니다. 본인 환경에서는 `python scripts/benchmark.py` 결과를 기준으로 하세요.

초기 골든셋은 6개 방향 × 8문장(48문장), 지표는 chrF++(표면 유사도일 뿐, 최종 판단은 사람 검토):

| 방향 | 1.8B chrF++ | 7B chrF++ |
|---|---:|---:|
| zh→ja | 53.22 | 58.75 |
| zh→en | 79.28 | 87.24 |
| ja→zh | 46.46 | 57.51 |
| ja→en | 66.15 | 81.86 |
| en→zh | 52.46 | 55.25 |
| en→ja | 49.67 | 66.06 |
| **평균** | **57.87** | **67.78** |

7B는 6개 방향 모두에서 1.8B를 앞섭니다. 1.8B는 NPU/저전력에 적합하며, 전문 용어가 많은 글은 용어집이나 7B를 권장합니다. 자세한 내용: [docs/evaluation.md](docs/evaluation.md).

## 개인정보와 보안

- `127.0.0.1`에만 바인딩하고 실행마다 임의 토큰을 발급하며 API는 `X-ZC-Token`을 검증합니다. 페이지 자체도 토큰이 필요합니다.
- CSP는 `default-src 'self'`, 인라인 스크립트와 외부 CDN이 없으며 모든 사용자 텍스트는 `textContent`로 렌더링합니다.
- SQLite는 매개변수화 쿼리, 로그에 원문/번역문을 남기지 않으며 스크린샷은 메모리에서만 처리하고 임시 파일을 만들지 않습니다.
- 기록, 용어집, 번역 메모리는 로컬에만 저장되며 한 번에 지울 수 있습니다.
- 네트워크는 모델 준비(ModelScope), 음성 모델 다운로드(GitHub Releases), Python 의존성 설치에만 사용됩니다.

## 알려진 제한

- **저장소와 릴리스 패키지에 모델이 없습니다.** 준비하기 전에는 앱이 실행되어도 번역할 수 없습니다.
- UI는 현재 **중국어 간체만** 지원합니다.
- Hy-MT2-1.8B는 존댓말, 전문 용어, 긴 문장에서 누락되거나 어색한 표현이 나올 수 있습니다. 7B나 용어집을 사용하세요.
- NPU 최초 로드는 컴파일이 필요합니다(참고 장비 약 10~15초). 이후에는 `data/cache`를 쓰지만 드라이버나 모델을 바꾸면 다시 컴파일합니다.
- 7B는 NPU에 권장하지 않습니다. 긴 문서를 7B로 번역하면 수십 분 걸릴 수 있어 1.8B를 권장합니다.
- OCR과 문서 번역은 이미지/스캔 PDF, TXT/MD, DOCX를 지원합니다. 복잡한 Word 텍스트 상자, PPTX, 복잡한 표 레이아웃은 미지원입니다.
- 스크린샷 번역은 Windows "캡처 도구"의 "클립보드에 자동 복사" 설정에 의존합니다. 브라우저 폴백 모드에서는 캡처 중 창이 숨겨지지 않습니다.
- 선택 영역 번역은 Windows UI Automation에 의존합니다. 자체 렌더링 UI, 게임, 관리자 권한 창, 암호 입력란에서는 선택을 읽지 못하며 키보드 Shift+방향키 선택은 자동 실행되지 않습니다.
- 선택 영역 번역은 기본 꺼짐이고 1회 4000자까지입니다. 메인 창을 닫으면 트레이에서 복원하거나 종료하세요.
- 설치 프로그램은 서명되지 않았습니다(SmartScreen 경고). 제거 시 `%LOCALAPPDATA%\ZCTranslate`는 기본적으로 남습니다.
- 사용자 모델은 내장 프로필 폴더 이름을 재사용하거나 `MODEL_PROFILES`를 확장해야 합니다.

## 라이선스

- **이 프로그램: GNU Affero General Public License v3.0(AGPL-3.0-only)** — [LICENSE](LICENSE) 참고.
  Copyright (C) 2026 ZC Translate contributors.
- **모델: Hy-MT2-1.8B / 7B, Apache-2.0**(이 저장소에 포함되지 않음).
- **서드파티 구성 요소**: 전체 목록은 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md), 호환성 분석과 재배포 체크리스트는 [docs/licensing.md](docs/licensing.md).

왜 GPL-3.0이 아닌가? PDF/스캔 문서 경로가 **PyMuPDF(AGPL-3.0)** 를 사용하기 때문입니다. GPLv3는 AGPLv3와 결합할 수 있지만 PyMuPDF를 번들한 패키지는 AGPL의 소스 제공 의무도 충족해야 합니다. 프로젝트 전체를 AGPL-3.0으로 두는 것이 가장 일관되고 운영이 쉽습니다. 나중에 PyMuPDF를 pypdfium2 같은 관대한 라이브러리로 교체하면 GPL로 바꿀 수 있습니다. 자세한 내용: [docs/licensing.md](docs/licensing.md).

## 감사의 말

- [Tencent Hunyuan Hy-MT2](https://github.com/Tencent-Hunyuan/Hy-MT2) — 번역 모델(Apache-2.0)
- [Intel OpenVINO / OpenVINO GenAI](https://github.com/openvinotoolkit/openvino) — 로컬 추론과 모델 변환
- [RapidOCR](https://github.com/RapidAI/RapidOCR) + [ONNX Runtime](https://github.com/microsoft/onnxruntime) — 로컬 OCR
- [sherpa-onnx / k2-fsa](https://github.com/k2-fsa/sherpa-onnx) — 음성 인식과 VAD
- [pywebview](https://github.com/r0x0r/pywebview), [FastAPI](https://github.com/fastapi/fastapi), [Uvicorn](https://github.com/encode/uvicorn)

## 기여와 피드백

- Issue / PR을 환영합니다. `models/`, `dist/`, `data/` 및 큰 파일은 **커밋하지 마세요**.
- 코드를 제출하면 해당 기여를 AGPL-3.0으로 허여하는 데 동의한 것으로 간주합니다.
- 문제를 보고할 때 Windows 버전, 장치(NPU/GPU/CPU), 모델 프로필, `data/logs/app.log`의 관련 부분(개인 정보 삭제 후)을 포함해 주세요.

## 면책 조항

기계 번역은 오류를 포함할 수 있습니다. 법률, 의료, 금융, 문학 등 고위험·고전문성 콘텐츠는 사람이 검토하세요. 이 프로젝트는 AGPL-3.0의 "보증 없음" 조건으로 배포됩니다.
