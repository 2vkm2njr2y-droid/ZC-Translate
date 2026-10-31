from __future__ import annotations

import io
import tarfile
from pathlib import Path

import pytest

from app.backend.services.speech import SpeechService, SpeechSession


def test_speech_status_reports_missing_model(tmp_path: Path):
    service = SpeechService(tmp_path / "models")
    status = service.model_status()
    assert status["installed"] is False
    assert status["pause_seconds"] == 2.5
    with pytest.raises(RuntimeError, match="下载语音识别模型"):
        service.start_session("conversation")


def test_safe_extract_rejects_path_escape(tmp_path: Path):
    archive = tmp_path / "bad.tar.bz2"
    with tarfile.open(archive, "w:bz2") as bundle:
        data = io.BytesIO(b"unsafe")
        info = tarfile.TarInfo("../outside.txt")
        info.size = len(data.getvalue())
        bundle.addfile(info, data)

    with pytest.raises(RuntimeError, match="非法路径"):
        SpeechService._safe_extract(archive, tmp_path / "dest")


def test_input_segments_update_live_transcript(tmp_path: Path):
    service = SpeechService(tmp_path / "models")
    session = SpeechSession(id="live", mode="input")

    service._add_segment(session, "第一句", "zh", 0.1)
    service._add_segment(session, "第二句", "zh", 0.1)

    assert session.transcript == "第一句\n第二句"
    assert [item["text"] for item in session.segments] == ["第一句", "第二句"]
