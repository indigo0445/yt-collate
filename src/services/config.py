"""Config directory and JSON persistence helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel

from yt_collate.models.config import AppConfig

APP_DIR_NAME = "yt-collate"
LEGACY_DIR_NAME = "youtube-music-lite"
ENV_CONFIG = "YT_COLLATE_CONFIG"
LEGACY_ENV_CONFIG = "YOUTUBE_MUSIC_LITE_CONFIG"


def _config_home() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)
    return Path.home() / ".config"


def get_config_dir() -> Path:
    override = os.environ.get(ENV_CONFIG) or os.environ.get(LEGACY_ENV_CONFIG)
    if override:
        path = Path(override).expanduser()
    else:
        home = _config_home()
        path = home / APP_DIR_NAME
        legacy = home / LEGACY_DIR_NAME
        if not path.exists() and legacy.exists():
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                legacy.rename(path)
            except OSError:
                path = legacy
    path.mkdir(parents=True, exist_ok=True)
    return path


def _read_model[T: BaseModel](path: Path, model: type[T], default: T) -> T:
    if not path.exists():
        return default
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return model.model_validate(data)
    except (OSError, json.JSONDecodeError, ValueError):
        return default


def _write_model(path: Path, model: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        model.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )


class ConfigService:
    def __init__(self, config_dir: Path | None = None) -> None:
        self.config_dir = config_dir or get_config_dir()
        self._path = self.config_dir / "config.json"
        self.config = _read_model(self._path, AppConfig, AppConfig())

    def save(self) -> None:
        _write_model(self._path, self.config)

    def update(self, **kwargs: object) -> AppConfig:
        self.config = self.config.model_copy(update=kwargs)
        self.save()
        return self.config

    @property
    def player_state_path(self) -> Path:
        return self.config_dir / "player-state.json"

    @property
    def auth_headers_path(self) -> Path:
        if self.config.auth_headers_path:
            return Path(self.config.auth_headers_path).expanduser()
        return self.config_dir / "headers_auth.json"
