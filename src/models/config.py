"""App configuration models."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class RepeatMode(StrEnum):
    OFF = "off"
    ALL = "all"
    ONE = "one"


class AppConfig(BaseModel):
    theme: str = "dark"
    volume: int = Field(default=100, ge=0, le=100)
    shuffle: bool = False
    repeat: RepeatMode = RepeatMode.OFF
    autoplay: bool = False
    auth_headers_path: str | None = None
    discord_rpc: bool = False
    show_episodes_for_later: bool = False
    show_liked_songs: bool = True
    show_saved_songs: bool = True
    cookies_file: str | None = None
    cookies_from_browser: str | None = None
    confirm_delete: bool = True