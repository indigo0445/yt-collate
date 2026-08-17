"""config dir helpers"""

from __future__ import annotations

from pathlib import Path

from services.config import ConfigService, get_config_dir


def test_config_dir_env_override(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("YT_COLLATE_CONFIG", str(tmp_path / "cfg"))
    path = get_config_dir()
    assert path == tmp_path / "cfg"
    assert path.exists()

    svc = ConfigService()
    svc.update(volume=42)
    assert (path / "config.json").exists()
    assert ConfigService().config.volume == 42


def test_default_config_dir_name(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("YT_COLLATE_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    path = get_config_dir()
    assert path == tmp_path / "yt-collate"
    assert path.exists()


def test_default_auth_file_is_browser_json(tmp_path: Path) -> None:
    svc = ConfigService(config_dir=tmp_path / "cfg")
    assert svc.auth_headers_path == tmp_path / "cfg" / "browser.json"


def test_default_volume_is_100(tmp_path: Path) -> None:
    svc = ConfigService(config_dir=tmp_path / "cfg")
    assert svc.config.volume == 100


def test_library_visibility_defaults() -> None:
    from models.config import AppConfig

    cfg = AppConfig()
    assert cfg.show_episodes_for_later is False
    assert cfg.show_liked_songs is True
    assert cfg.show_saved_songs is True
    assert cfg.confirm_delete is True
