"""Config dir helpers."""

from __future__ import annotations

from pathlib import Path

from yt_collate.services.config import ConfigService, get_config_dir


def test_config_dir_env_override(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("YT_COLLATE_CONFIG", str(tmp_path / "cfg"))
    path = get_config_dir()
    assert path == tmp_path / "cfg"
    assert path.exists()

    svc = ConfigService()
    svc.update(volume=42)
    assert (path / "config.json").exists()
    assert ConfigService().config.volume == 42


def test_legacy_env_override(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("YT_COLLATE_CONFIG", raising=False)
    monkeypatch.setenv("YOUTUBE_MUSIC_LITE_CONFIG", str(tmp_path / "old"))
    path = get_config_dir()
    assert path == tmp_path / "old"
    assert path.exists()


def test_default_config_dir_name(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("YT_COLLATE_CONFIG", raising=False)
    monkeypatch.delenv("YOUTUBE_MUSIC_LITE_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = get_config_dir()
    assert path == tmp_path / "yt-collate"
    assert path.exists()


def test_migrates_legacy_config_dir(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("YT_COLLATE_CONFIG", raising=False)
    monkeypatch.delenv("YOUTUBE_MUSIC_LITE_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    legacy = tmp_path / "youtube-music-lite"
    legacy.mkdir()
    (legacy / "headers_auth.json").write_text("{}\n")
    path = get_config_dir()
    assert path == tmp_path / "yt-collate"
    assert (path / "headers_auth.json").exists()
    assert not legacy.exists()


def test_default_volume_is_100(tmp_path: Path) -> None:
    svc = ConfigService(config_dir=tmp_path / "cfg")
    assert svc.config.volume == 100


def test_library_visibility_defaults() -> None:
    from yt_collate.models.config import AppConfig

    cfg = AppConfig()
    assert cfg.show_episodes_for_later is False
    assert cfg.show_liked_songs is True
    assert cfg.show_saved_songs is True
    assert cfg.confirm_delete is True
