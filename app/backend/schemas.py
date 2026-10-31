"""Pydantic request/response models for the local HTTP API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

LanguageCode = Literal["auto", "zh", "ja", "en"]
TargetLanguage = Literal["zh", "ja", "en"]
DeviceCode = Literal["auto", "NPU", "GPU", "CPU"]
StyleCode = Literal["default", "formal", "casual", "technical", "literary"]
SplitMode = Literal["auto", "paragraph", "line"]
SpeechMode = Literal["conversation", "input"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TranslateRequest(StrictModel):
    text: str = Field(min_length=1, max_length=100_000)
    source_lang: LanguageCode = "auto"
    target_lang: TargetLanguage = "zh"
    profile_id: str | None = None
    device: DeviceCode = "auto"
    glossary_id: str | None = None
    style: StyleCode = "default"
    use_tm: bool = True
    use_context: bool = False
    refine: bool = False
    split_mode: SplitMode = "auto"


class GlossaryCreate(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    src_lang: Literal["zh", "ja", "en"]
    tgt_lang: Literal["zh", "ja", "en"]
    bidirectional: bool = False


class GlossaryUpdate(StrictModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    bidirectional: bool | None = None


class TermCreate(StrictModel):
    source: str = Field(min_length=1, max_length=500)
    target: str = Field(min_length=1, max_length=500)
    case_sensitive: bool = False
    note: str = Field(default="", max_length=500)


class TermUpdate(StrictModel):
    source: str | None = Field(default=None, min_length=1, max_length=500)
    target: str | None = Field(default=None, min_length=1, max_length=500)
    case_sensitive: bool | None = None
    note: str | None = Field(default=None, max_length=500)


class SettingsUpdate(StrictModel):
    theme: Literal["system", "light", "dark"] | None = None
    target_lang: TargetLanguage | None = None
    source_lang: LanguageCode | None = None
    profile_id: str | None = None
    device: DeviceCode | None = None
    style: StyleCode | None = None
    glossary_id: str | None = None
    use_tm: bool | None = None
    use_context: bool | None = None
    refine: bool | None = None
    split_mode: SplitMode | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    top_p: float | None = Field(default=None, gt=0.0, le=1.0)
    top_k: int | None = Field(default=None, ge=0)
    repetition_penalty: float | None = Field(default=None, ge=0.5, le=2.0)
    max_new_tokens: int | None = Field(default=None, ge=64, le=4096)
    preload_model: bool | None = None
    offline_mode: bool | None = None
    selection_translate: bool | None = None


class BenchmarkRequest(StrictModel):
    profile_id: str | None = None
    devices: list[DeviceCode] | None = None
    lengths: list[int] | None = None


class CancelRequest(StrictModel):
    job_id: str


class SpeechSessionStartRequest(StrictModel):
    mode: SpeechMode = "conversation"


class SpeechSessionRequest(StrictModel):
    session_id: str = Field(min_length=1, max_length=64)


class ImportTermsRequest(StrictModel):
    csv_text: str = Field(max_length=2_000_000)
    replace: bool = False


class OCRImageRequest(StrictModel):
    file_name: str = Field(default="image.png", max_length=260)
    content_base64: str = Field(min_length=1, max_length=80_000_000)


class ScreenshotTranslateRequest(StrictModel):
    lines: list[str] = Field(min_length=1, max_length=200)
    source_lang: LanguageCode = "auto"
    target_lang: TargetLanguage = "zh"
    profile_id: str | None = None
    device: DeviceCode = "auto"
    glossary_id: str | None = None
    style: StyleCode = "default"
    use_tm: bool = True

    @field_validator("lines")
    @classmethod
    def validate_lines(cls, value: list[str]) -> list[str]:
        cleaned = [line.strip() for line in value]
        if any(not line for line in cleaned):
            raise ValueError("截图 OCR 行不能为空。")
        if any(len(line) > 1500 for line in cleaned):
            raise ValueError("单行文字过长，请缩小截图区域后重试。")
        if sum(len(line) for line in cleaned) > 20_000:
            raise ValueError("截图文字过多，请缩小截图区域后重试。")
        return cleaned


class DocumentTranslateRequest(StrictModel):
    file_name: str = Field(min_length=1, max_length=260)
    source_path: str = Field(default="", max_length=2000)
    content_base64: str = Field(min_length=1, max_length=120_000_000)
    source_lang: LanguageCode = "auto"
    target_lang: TargetLanguage = "zh"
    profile_id: str | None = None
    device: DeviceCode = "auto"
    glossary_id: str | None = None
    style: StyleCode = "default"
    use_tm: bool = True


class ComicTranslateRequest(StrictModel):
    """A local batch of manga page images for Comic-Player integration."""

    image_paths: list[str] = Field(min_length=1, max_length=2000)
    output_dir: str = Field(min_length=1, max_length=2000)
    source_lang: LanguageCode = "auto"
    target_lang: TargetLanguage = "zh"
    quality: Literal["speed", "quality"] = "speed"
    profile_id: str | None = None
    device: DeviceCode = "auto"
    glossary_id: str | None = None
    style: StyleCode = "default"
    use_tm: bool = True
    force: bool = False

    @field_validator("image_paths")
    @classmethod
    def validate_image_paths(cls, value: list[str]) -> list[str]:
        cleaned = [str(item).strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("漫画图片路径不能为空。")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("漫画图片路径不能重复。")
        return cleaned


class ModelImportRequest(StrictModel):
    path: str = Field(min_length=1, max_length=1000)
