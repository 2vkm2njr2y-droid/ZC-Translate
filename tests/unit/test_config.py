from __future__ import annotations

from pathlib import Path

from app.backend import config


def _freeze_app(monkeypatch, tmp_path: Path, exe_dir: Path) -> None:
    exe_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.delenv("ZC_MODELS_DIR", raising=False)
    monkeypatch.setenv("ZC_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(config, "is_frozen", lambda: True)
    monkeypatch.setattr(config, "repo_root", lambda: exe_dir)


def test_absolute_models_pointer(monkeypatch, tmp_path: Path) -> None:
    exe_dir = tmp_path / "app"
    models = tmp_path / "shared-models"
    models.mkdir()
    _freeze_app(monkeypatch, tmp_path, exe_dir)
    (exe_dir / "models-path.txt").write_text(
        f"# models location\n{models}\n", encoding="utf-8"
    )
    assert config.resolve_models_dir() == models.resolve()


def test_relative_models_pointer(monkeypatch, tmp_path: Path) -> None:
    exe_dir = tmp_path / "app"
    models = tmp_path / "shared-models"
    models.mkdir()
    _freeze_app(monkeypatch, tmp_path, exe_dir)
    relative = str(Path("..") / "shared-models")
    (exe_dir / "models-path.txt").write_text(relative + "\n", encoding="utf-8")
    assert config.resolve_models_dir() == models.resolve()


def test_exe_side_models_win_over_pointer(monkeypatch, tmp_path: Path) -> None:
    exe_dir = tmp_path / "app"
    exe_models = exe_dir / "models"
    exe_models.mkdir(parents=True)
    shared = tmp_path / "shared-models"
    shared.mkdir()
    _freeze_app(monkeypatch, tmp_path, exe_dir)
    (exe_dir / "models-path.txt").write_text(str(shared) + "\n", encoding="utf-8")
    assert config.resolve_models_dir() == exe_models.resolve()


def test_env_var_wins_over_pointer(monkeypatch, tmp_path: Path) -> None:
    exe_dir = tmp_path / "app"
    env_models = tmp_path / "env-models"
    env_models.mkdir()
    pointer_models = tmp_path / "pointer-models"
    pointer_models.mkdir()
    _freeze_app(monkeypatch, tmp_path, exe_dir)
    monkeypatch.setenv("ZC_MODELS_DIR", str(env_models))
    (exe_dir / "models-path.txt").write_text(
        str(pointer_models) + "\n", encoding="utf-8"
    )
    assert config.resolve_models_dir() == env_models.resolve()


def test_missing_pointer_falls_back_to_data_models(monkeypatch, tmp_path: Path) -> None:
    exe_dir = tmp_path / "app"
    _freeze_app(monkeypatch, tmp_path, exe_dir)
    expected = (tmp_path / "data" / "models").resolve()
    assert config.resolve_models_dir() == expected
