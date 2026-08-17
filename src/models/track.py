"""music entity representations"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Artist(BaseModel):
    name: str
    id: str | None = None


class Track(BaseModel):
    video_id: str
    title: str
    artists: list[Artist] = Field(default_factory=list)
    duration: int | None = None  # seconds
    thumbnail: str | None = None
    album: str | None = None
    album_id: str | None = None
    library_add_token: str | None = None
    library_remove_token: str | None = None
    like_status: str | None = None
    in_library: bool | None = None
    set_video_id: str | None = None
    is_video: bool = False

    @property
    def artist_str(self) -> str:
        if not self.artists:
            return "Unknown"
        return ", ".join(a.name for a in self.artists)

    @property
    def watch_url(self) -> str:
        # fetching from www.youtube.com probably gives same audio
        return f"https://music.youtube.com/watch?v={self.video_id}"

    @property
    def display(self) -> str:
        return f"{self.title} - {self.artist_str}"

    def same_listen(self, other: Track) -> bool:
        if self.video_id and other.video_id and self.video_id == other.video_id:
            return True
        return self.title == other.title and self.artist_str == other.artist_str


class PlaylistSummary(BaseModel):
    playlist_id: str
    title: str
    author: str | None = None
    track_count: int | None = None
    thumbnail: str | None = None


class LocalPlaylist(BaseModel):
    emoji: str = "📁"
    title: str
    tracks: list[Track] = Field(default_factory=list)