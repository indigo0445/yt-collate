"""Queue state representation - preserves queue on exit"""

from __future__ import annotations

from pydantic import BaseModel, Field

from yt_collate.models.config import RepeatMode
from yt_collate.models.music import Track


class PlayerStateFile(BaseModel):
    queue: list[Track] = Field(default_factory=list)
    index: int = 0