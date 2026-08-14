"""YouTube Music API façade via ytmusicapi."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from models.track import Artist, PlaylistSummary, Track
from utils import youtube_video_id


def _parse_duration(raw: Any) -> int | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return int(raw)
    if isinstance(raw, str):
        parts = raw.split(":")
        try:
            nums = [int(p) for p in parts]
        except ValueError:
            return None
        if len(nums) == 3:
            return nums[0] * 3600 + nums[1] * 60 + nums[2]
        if len(nums) == 2:
            return nums[0] * 60 + nums[1]
        if len(nums) == 1:
            return nums[0]
    return None


def _artists_from_item(item: dict[str, Any]) -> list[Artist]:
    artists: list[Artist] = []
    for a in item.get("artists") or []:
        if isinstance(a, dict) and a.get("name"):
            artists.append(Artist(name=a["name"], id=a.get("id")))
    if not artists and item.get("artist"):
        artists.append(Artist(name=str(item["artist"])))
    return artists


_ATV = "MUSIC_VIDEO_TYPE_ATV"


def _item_is_video(item: dict[str, Any], *, default: bool = False) -> bool:
    """True for YouTube videos that are not YouTube Music catalog songs."""
    result_type = str(item.get("resultType") or "").casefold()
    if result_type == "video":
        return True
    if result_type == "song":
        return False
    mvt = str(item.get("videoType") or item.get("musicVideoType") or "")
    if mvt:
        return mvt != _ATV
    return default


def track_from_song(item: Any) -> Track | None:
    if not isinstance(item, dict):
        return None
    video_id = item.get("videoId") or item.get("video_id")
    title = item.get("title")
    if not video_id or not title:
        return None
    thumbs = item.get("thumbnails") or []
    thumb = thumbs[-1]["url"] if thumbs else None
    album = None
    album_id = None
    if isinstance(item.get("album"), dict):
        album = item["album"].get("name")
        album_id = item["album"].get("id")
    elif isinstance(item.get("album"), str):
        album = item["album"]
    tokens = item.get("feedbackTokens")
    library_add_token = None
    library_remove_token = None
    if isinstance(tokens, dict):
        if tokens.get("add"):
            library_add_token = str(tokens["add"])
        if tokens.get("remove"):
            library_remove_token = str(tokens["remove"])
    raw_like = item.get("likeStatus")
    like_status = None
    if raw_like is not None:
        like_status = str(getattr(raw_like, "value", raw_like))
    in_library = item.get("inLibrary")
    if not isinstance(in_library, bool):
        in_library = None
        if library_remove_token and not library_add_token:
            in_library = True
    set_video_id = item.get("setVideoId") or item.get("set_video_id")
    if set_video_id is not None:
        set_video_id = str(set_video_id)
    return Track(
        video_id=video_id,
        title=title,
        artists=_artists_from_item(item),
        duration=_parse_duration(item.get("duration_seconds") or item.get("duration")),
        thumbnail=thumb,
        album=album,
        album_id=album_id,
        library_add_token=library_add_token,
        library_remove_token=library_remove_token,
        like_status=like_status,
        in_library=in_library,
        set_video_id=set_video_id,
        is_video=_item_is_video(item),
    )


def track_from_player(payload: Any) -> Track | None:
    """Normalize ytmusicapi ``get_song`` (player) metadata into a Track."""
    if not isinstance(payload, dict):
        return None
    details = payload.get("videoDetails")
    if not isinstance(details, dict):
        return None
    video_id = details.get("videoId") or details.get("video_id")
    title = details.get("title")
    if not video_id or not title:
        return None
    author = details.get("author")
    artists = [Artist(name=str(author))] if author else []
    thumbs: list[Any] = []
    thumb_block = details.get("thumbnail")
    if isinstance(thumb_block, dict):
        thumbs = thumb_block.get("thumbnails") or []
    elif isinstance(details.get("thumbnails"), list):
        thumbs = details["thumbnails"]
    thumb = thumbs[-1]["url"] if thumbs and isinstance(thumbs[-1], dict) else None
    return Track(
        video_id=str(video_id),
        title=str(title),
        artists=artists,
        duration=_parse_duration(details.get("lengthSeconds") or details.get("length_seconds")),
        thumbnail=thumb if isinstance(thumb, str) else None,
        is_video=_item_is_video(details, default=True),
    )


LIKED_PLAYLIST_ID = "__liked__"
SAVED_SONGS_PLAYLIST_ID = "__saved__"
EPISODES_FOR_LATER = "episodes for later"

LibraryTargetKind = Literal["playlist", "saved", "liked"]
AddReason = Literal["success", "duplicate", "error"]


@dataclass(frozen=True)
class LibraryTarget:
    """Playlist / Saved Songs / Liked Songs chosen with m in My Library."""

    kind: LibraryTargetKind
    playlist_id: str
    title: str


@dataclass(frozen=True)
class AddResult:
    ok: bool
    message: str
    reason: AddReason = "success"


@dataclass(frozen=True)
class PlaylistWriteResult:
    ok: bool
    message: str
    playlist_id: str | None = None


def is_episodes_for_later(title: str) -> bool:
    return title.strip().casefold() == EPISODES_FOR_LATER


def _playlist_add_succeeded(result: object) -> bool:
    if isinstance(result, str):
        return "SUCCEEDED" in result
    if isinstance(result, dict):
        return "SUCCEEDED" in str(result.get("status") or "")
    return False


def _playlist_delete_succeeded(result: object) -> bool:
    """ytmusicapi often returns the full Innertube payload (no status string)."""
    if _playlist_add_succeeded(result):
        return True
    text = str(result)
    return (
        "handlePlaylistDeletionCommand" in text
        or "GUIDE_ACTION_REMOVE_FROM_PLAYLISTS" in text
    )


def _is_api_blob(result: object) -> bool:
    if isinstance(result, dict) and (
        "responseContext" in result or "frameworkUpdates" in result or "actions" in result
    ):
        return True
    text = str(result)
    return "responseContext" in text or "handlePlaylistDeletionCommand" in text


def _short_failure(result: object, fallback: str) -> str:
    """User-facing error; never dump Innertube JSON (breaks toast markup)."""
    if isinstance(result, dict):
        for key in ("status", "error", "message"):
            value = result.get(key)
            if isinstance(value, str) and value and not _is_api_blob(value):
                return f"{fallback}: {value}"
        return fallback
    text = str(result).strip()
    if not text or text in {"None", "{}"} or _is_api_blob(text):
        return fallback
    if len(text) > 160:
        text = text[:159] + "…"
    return f"{fallback}: {text}"


def _is_liked(status: str | None) -> bool:
    if not status:
        return False
    return status.upper().split(".")[-1] == "LIKE"


def _looks_like_duplicate(result: object) -> bool:
    text = str(result).casefold()
    return "duplicate" in text or "already exists" in text or "already in" in text


def _looks_like_already_gone(result: object) -> bool:
    """Stale playlist edit: item already removed (HTTP 400 precondition)."""
    text = str(result).casefold()
    return "precondition" in text or "not found" in text


def _playlist_error_message(result: object, title: str) -> str:
    return _short_failure(result, f"Could not add to {title}")


def library_target_for(playlist: PlaylistSummary) -> LibraryTarget | None:
    """Markable library folders only: user playlists, Saved Songs, Liked Songs."""
    if is_episodes_for_later(playlist.title):
        return None
    if playlist.playlist_id == SAVED_SONGS_PLAYLIST_ID:
        return LibraryTarget("saved", playlist.playlist_id, playlist.title)
    if playlist.playlist_id == LIKED_PLAYLIST_ID:
        return LibraryTarget("liked", playlist.playlist_id, playlist.title)
    return LibraryTarget("playlist", playlist.playlist_id, playlist.title)


def is_user_playlist(playlist: PlaylistSummary) -> bool:
    """Normal account playlist — not Liked, Saved, or Episodes for Later."""
    target = library_target_for(playlist)
    return target is not None and target.kind == "playlist"


@dataclass
class LibraryState:
    like_status: str | None = None
    in_library: bool | None = None
    add_token: str | None = None
    remove_token: str | None = None


def _state_from_item(item: Any) -> LibraryState:
    if not isinstance(item, dict):
        return LibraryState()
    raw_like = item.get("likeStatus")
    like_status = None
    if raw_like is not None:
        like_status = str(getattr(raw_like, "value", raw_like))
    in_library = item.get("inLibrary")
    if not isinstance(in_library, bool):
        in_library = None
    tokens = item.get("feedbackTokens")
    add_token = None
    remove_token = None
    if isinstance(tokens, dict):
        if tokens.get("add"):
            add_token = str(tokens["add"])
        if tokens.get("remove"):
            remove_token = str(tokens["remove"])
        if in_library is None and remove_token and not add_token:
            in_library = True
    return LibraryState(
        like_status=like_status,
        in_library=in_library,
        add_token=add_token,
        remove_token=remove_token,
    )


def _merge_library_state(state: LibraryState, extra: LibraryState) -> None:
    if extra.like_status and not state.like_status:
        state.like_status = extra.like_status
    if extra.in_library is not None and state.in_library is None:
        state.in_library = extra.in_library
    if extra.add_token and not state.add_token:
        state.add_token = extra.add_token
    if extra.remove_token and not state.remove_token:
        state.remove_token = extra.remove_token


def _apply_matching_track(state: LibraryState, payload: Any, video_id: str) -> None:
    if not isinstance(payload, dict):
        return
    for item in payload.get("tracks") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("videoId") or "") != video_id:
            continue
        _merge_library_state(state, _state_from_item(item))
        return


CatalogKind = Literal["song", "album", "playlist", "artist", "mood"]


@dataclass
class CatalogItem:
    kind: CatalogKind
    title: str
    track: Track | None = None
    browse_id: str | None = None
    playlist_id: str | None = None
    params: str | None = None
    subtitle: str | None = None

    @property
    def label(self) -> str:
        if self.kind == "song" and self.track is not None:
            return f"{self.track.title} — {self.track.artist_str}"
        prefix = {
            "album": "💿",
            "playlist": "📁",
            "artist": "🎤",
            "mood": "🎭",
        }.get(self.kind, "")
        extra = f" · {self.subtitle}" if self.subtitle else ""
        return f"{prefix} {self.title}{extra}".strip()

    @property
    def open_key(self) -> str | None:
        return self.playlist_id or self.browse_id or self.params


@dataclass
class CatalogShelf:
    title: str
    items: list[CatalogItem]


def _catalog_subtitle(item: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)):
            return str(value)
    artists = _artists_from_item(item)
    if artists:
        return ", ".join(a.name for a in artists)
    author = item.get("author")
    if isinstance(author, str) and author.strip():
        return author.strip()
    if isinstance(author, list) and author:
        first = author[0]
        if isinstance(first, dict) and first.get("name"):
            return str(first["name"])
        if isinstance(first, str):
            return first
    return None


def _search_row_item(raw: Any) -> CatalogItem | None:
    """Keep artists / songs / videos from a default search row; drop other types."""
    if not isinstance(raw, dict):
        return None
    result_type = str(raw.get("resultType") or "").casefold()
    if result_type in {"song", "video"}:
        track = track_from_song(raw)
        if track is None:
            return None
        return CatalogItem(kind="song", title=track.title, track=track)
    if result_type == "artist":
        item = catalog_item_from_content(raw)
        if item is None or item.kind != "artist":
            return None
        return item
    if result_type:
        return None
    item = catalog_item_from_content(raw)
    if item is not None and item.kind in {"song", "artist"}:
        return item
    return None


def catalog_item_from_content(item: Any) -> CatalogItem | None:
    """Classify a mixed catalog entry (song, album, playlist, artist, or mood)."""
    if not isinstance(item, dict):
        return None
    title = item.get("title") or item.get("artist") or item.get("name")
    if not title:
        return None
    track = track_from_song(item)
    if track is not None:
        return CatalogItem(kind="song", title=title, track=track)
    browse_id = str(item.get("browseId") or "")
    playlist_id = item.get("playlistId")
    if playlist_id:
        return CatalogItem(
            kind="playlist",
            title=title,
            playlist_id=str(playlist_id),
            subtitle=_catalog_subtitle(item, "description", "count"),
        )
    if browse_id.startswith("MPRE"):
        return CatalogItem(
            kind="album",
            title=title,
            browse_id=browse_id,
            subtitle=_catalog_subtitle(item, "year"),
        )
    if browse_id.startswith(("VL", "PL", "RD")):
        return CatalogItem(
            kind="playlist",
            title=title,
            playlist_id=browse_id,
            subtitle=_catalog_subtitle(item, "description", "count"),
        )
    if (
        item.get("resultType") == "artist"
        or browse_id.startswith("UC")
        or item.get("subscribers") is not None
    ):
        return CatalogItem(
            kind="artist",
            title=title,
            browse_id=browse_id or None,
            subtitle=_catalog_subtitle(item, "subscribers"),
        )
    if item.get("params"):
        return CatalogItem(kind="mood", title=title, params=str(item["params"]))
    return None


def _items_from_contents(contents: Any) -> list[CatalogItem]:
    items: list[CatalogItem] = []
    for raw in contents or []:
        item = catalog_item_from_content(raw)
        if item is not None:
            items.append(item)
    return items


class MusicService:
    def __init__(self, auth_headers_path: Path | None = None) -> None:
        self._auth_headers_path = auth_headers_path
        self._yt = None
        # Optimistic: file present ⇒ treat as authed; first API call validates.
        self._authenticated = (
            auth_headers_path is not None and auth_headers_path.exists()
        )

    @property
    def authenticated(self) -> bool:
        return self._authenticated

    def _client(self):
        if self._yt is not None:
            return self._yt
        from ytmusicapi import YTMusic

        path = self._auth_headers_path
        if path is not None and path.exists():
            self._yt = YTMusic(str(path))
            self._authenticated = True
        else:
            self._yt = YTMusic()
            self._authenticated = False
        return self._yt

    def reload_auth(self, auth_headers_path: Path | None) -> None:
        self._auth_headers_path = auth_headers_path
        self._yt = None
        self._authenticated = (
            auth_headers_path is not None and auth_headers_path.exists()
        )

    def search_songs(self, query: str, limit: int = 25) -> list[Track]:
        if not query.strip():
            return []
        results = self._client().search(query, filter="songs", limit=limit)
        tracks: list[Track] = []
        for item in results:
            track = track_from_song(item)
            if track:
                tracks.append(track)
        return tracks

    def search_songs_and_artists(self, query: str, *, limit: int = 30) -> list[CatalogItem]:
        """Default (unfiltered) search. Artists, songs, and videos in API order.

        Songs and videos are both playable `song` rows. A YouTube watch URL
        resolves to a single result via ``get_song``.
        """
        query = query.strip()
        if not query:
            return []
        video_id = youtube_video_id(query)
        if video_id:
            item = self._catalog_item_from_video_id(video_id)
            return [item] if item else []
        results = self._client().search(query, limit=limit)
        items: list[CatalogItem] = []
        for raw in results or []:
            item = _search_row_item(raw)
            if item is not None:
                items.append(item)
        return items

    def _catalog_item_from_video_id(self, video_id: str) -> CatalogItem | None:
        track = track_from_player(self._client().get_song(video_id))
        if track is None:
            return None
        return CatalogItem(kind="song", title=track.title, track=track)

    def search(self, query: str, limit: int = 25) -> list[Track]:
        return self.search_songs(query, limit=limit)

    def get_playlist_tracks(self, playlist_id: str, limit: int = 100) -> list[Track]:
        data = self._client().get_playlist(playlist_id, limit=limit)
        tracks: list[Track] = []
        for item in data.get("tracks") or []:
            track = track_from_song(item)
            if track:
                tracks.append(track)
        return tracks

    def get_playlist_summary(self, playlist_id: str) -> PlaylistSummary | None:
        data = self._client().get_playlist(playlist_id, limit=1)
        return PlaylistSummary(
            playlist_id=playlist_id,
            title=data.get("title") or "Playlist",
            author=(data.get("author") or {}).get("name")
            if isinstance(data.get("author"), dict)
            else data.get("author"),
            track_count=data.get("trackCount"),
            thumbnail=(data.get("thumbnails") or [{}])[-1].get("url"),
        )

    def search_playlists(self, query: str, limit: int = 20) -> list[PlaylistSummary]:
        results = self._client().search(query, filter="playlists", limit=limit)
        out: list[PlaylistSummary] = []
        for item in results:
            pid = item.get("browseId") or item.get("playlistId")
            title = item.get("title")
            if not pid or not title:
                continue
            out.append(
                PlaylistSummary(
                    playlist_id=pid,
                    title=title,
                    author=item.get("author"),
                    track_count=item.get("itemCount"),
                    thumbnail=(item.get("thumbnails") or [{}])[-1].get("url")
                    if item.get("thumbnails")
                    else None,
                )
            )
        return out

    def get_charts_tracks(self, country: str = "US") -> list[Track]:
        try:
            charts = self._client().get_charts(country=country)
        except Exception:  # noqa: BLE001
            return []
        tracks: list[Track] = []
        for section_key in ("songs", "videos", "trending"):
            section = charts.get(section_key)
            if not section:
                continue
            items = section.get("items") if isinstance(section, dict) else section
            if not isinstance(items, list):
                continue
            for item in items:
                track = track_from_song(item)
                if track:
                    tracks.append(track)
        return tracks

    def get_home(self, limit: int = 5) -> list[CatalogShelf]:
        """Titled home rows (songs, albums, playlists, artists mixed)."""
        try:
            rows = self._client().get_home(limit=limit)
        except Exception:  # noqa: BLE001
            return []
        shelves: list[CatalogShelf] = []
        for row in rows or []:
            if not isinstance(row, dict):
                continue
            title = str(row.get("title") or "").strip() or "Home"
            items = _items_from_contents(row.get("contents"))
            if items:
                shelves.append(CatalogShelf(title=title, items=items))
        return shelves

    def get_home_tracks(self, limit: int = 5) -> list[Track]:
        """Playable songs from the first `limit` home rows."""
        tracks: list[Track] = []
        for shelf in self.get_home(limit=limit):
            for item in shelf.items:
                if item.track is not None:
                    tracks.append(item.track)
        return tracks

    def get_album_tracks(self, browse_id: str) -> list[Track]:
        data = self._client().get_album(browse_id)
        if not isinstance(data, dict):
            return []
        album_name = data.get("title")
        tracks: list[Track] = []
        for item in data.get("tracks") or []:
            if isinstance(item, dict) and album_name and not item.get("album"):
                item = {**item, "album": album_name}
            track = track_from_song(item)
            if track:
                tracks.append(track)
        return tracks

    def get_artist_tracks(self, channel_id: str, limit: int = 50) -> list[Track]:
        data = self._client().get_artist(channel_id)
        if not isinstance(data, dict):
            return []
        songs = data.get("songs") if isinstance(data.get("songs"), dict) else {}
        browse_id = songs.get("browseId") if isinstance(songs, dict) else None
        if browse_id:
            try:
                tracks = self.get_playlist_tracks(str(browse_id), limit=limit)
                if tracks:
                    return tracks
            except Exception:  # noqa: BLE001
                pass
        tracks: list[Track] = []
        for item in (songs.get("results") if isinstance(songs, dict) else None) or []:
            track = track_from_song(item)
            if track:
                tracks.append(track)
            if len(tracks) >= limit:
                break
        return tracks

    def get_explore(self) -> list[CatalogShelf]:
        """Explore shelves: new albums, new videos, trending, top songs, moods."""
        try:
            data = self._client().get_explore()
        except Exception:  # noqa: BLE001
            return []
        if not isinstance(data, dict):
            return []
        sections: list[tuple[str, str]] = [
            ("new_releases", "New albums"),
            ("new_videos", "New music videos"),
            ("trending", "Trending"),
            ("top_songs", "Top songs"),
            ("moods_and_genres", "Moods & genres"),
        ]
        shelves: list[CatalogShelf] = []
        for key, title in sections:
            raw = data.get(key)
            if isinstance(raw, dict):
                contents = raw.get("items")
            else:
                contents = raw
            items = _items_from_contents(contents)
            if items:
                shelves.append(CatalogShelf(title=title, items=items))
        return shelves

    def get_mood_playlists(self, params: str) -> list[CatalogItem]:
        try:
            rows = self._client().get_mood_playlists(params)
        except Exception:  # noqa: BLE001
            return []
        return _items_from_contents(rows)

    def get_related(self, video_id: str, limit: int = 10) -> list[Track]:
        try:
            watch = self._client().get_watch_playlist(videoId=video_id)
        except Exception:  # noqa: BLE001
            return []
        tracks: list[Track] = []
        for item in watch.get("tracks") or []:
            track = track_from_song(item)
            if track and track.video_id != video_id:
                tracks.append(track)
            if len(tracks) >= limit:
                break
        return tracks

    def get_history(self, limit: int = 50) -> list[Track]:
        """Account play history. No-op (empty) when anonymous — never calls the API."""
        if not self.authenticated:
            return []
        items = self._client().get_history()
        tracks: list[Track] = []
        for item in items:
            track = track_from_song(item)
            if track is None:
                continue
            if tracks and tracks[-1].same_listen(track):
                continue
            tracks.append(track)
            if len(tracks) >= limit:
                break
        return tracks

    def add_history_item(self, track: Track) -> None:
        """Tell YouTube this track was played. No-op when anonymous — never calls the API."""
        if not self.authenticated or not track.video_id:
            return
        client = self._client()
        song = client.get_song(track.video_id)
        client.add_history_item(song)

    def get_library_songs(self, limit: int = 50) -> list[Track]:
        if not self.authenticated:
            return []
        items = self._client().get_library_songs(limit=limit)
        tracks: list[Track] = []
        for item in items:
            track = track_from_song(item)
            if track:
                tracks.append(track)
        return tracks

    def get_liked_songs(self, limit: int = 100) -> list[Track]:
        if not self.authenticated:
            return []
        data = self._client().get_liked_songs(limit=limit)
        tracks: list[Track] = []
        for item in data.get("tracks") or []:
            track = track_from_song(item)
            if track:
                tracks.append(track)
        return tracks

    def get_collection_tracks(self, playlist_id: str, limit: int = 200) -> list[Track]:
        if playlist_id == LIKED_PLAYLIST_ID:
            return self.get_liked_songs(limit=100)
        if playlist_id == SAVED_SONGS_PLAYLIST_ID:
            return self.get_library_songs(limit=limit)
        return self.get_playlist_tracks(playlist_id, limit=limit)

    def add_song_to_target(self, track: Track, target: LibraryTarget) -> AddResult:
        """Add a song to the marked library collection."""
        if not self.authenticated:
            return AddResult(False, "Sign in (Settings) to add to library", "error")
        if not track.video_id:
            return AddResult(False, "Song has no video id", "error")
        try:
            if target.kind == "saved":
                state = self._resolve_library_state(track, kind="saved")
                if state.in_library:
                    return AddResult(
                        False, f"Already in {target.title}: {track.title}", "duplicate"
                    )
                if not state.add_token:
                    return AddResult(
                        False,
                        "No library token for this song (try opening its album)",
                        "error",
                    )
                self._client().edit_song_library_status([state.add_token])
                return AddResult(True, f"Saved: {track.title}")
            if target.kind == "liked":
                from ytmusicapi.models.content.enums import LikeStatus

                state = self._resolve_library_state(track, kind="liked")
                if _is_liked(state.like_status):
                    return AddResult(
                        False, f"Already in {target.title}: {track.title}", "duplicate"
                    )
                self._client().rate_song(track.video_id, LikeStatus.LIKE)
                return AddResult(True, f"Liked: {track.title}")
            return self._add_to_playlist(track, target)
        except Exception as exc:  # noqa: BLE001
            if target.kind == "playlist" and _looks_like_duplicate(exc):
                return AddResult(
                    False, f"Already in {target.title}: {track.title}", "duplicate"
                )
            return AddResult(False, str(exc) or f"Could not add to {target.title}", "error")

    def _add_to_playlist(self, track: Track, target: LibraryTarget) -> AddResult:
        result = self._client().add_playlist_items(
            target.playlist_id, videoIds=[track.video_id], duplicates=False
        )
        if _playlist_add_succeeded(result):
            return AddResult(True, f"Added to {target.title}: {track.title}")
        if _looks_like_duplicate(result):
            return AddResult(
                False, f"Already in {target.title}: {track.title}", "duplicate"
            )
        return AddResult(False, _playlist_error_message(result, target.title), "error")

    def remove_song_from_target(self, track: Track, target: LibraryTarget) -> AddResult:
        """Remove a song from the marked or open library collection."""
        if not self.authenticated:
            return AddResult(False, "Sign in (Settings) to remove from library", "error")
        if not track.video_id:
            return AddResult(False, "Song has no video id", "error")
        try:
            if target.kind == "saved":
                state = self._resolve_library_state(track, kind="saved")
                if state.in_library is False:
                    return AddResult(
                        False, f"Not in {target.title}: {track.title}", "error"
                    )
                token = state.remove_token
                if not token:
                    return AddResult(
                        False,
                        "No library token for this song (try opening its album)",
                        "error",
                    )
                self._client().edit_song_library_status([token])
                return AddResult(True, f"Removed from {target.title}: {track.title}")
            if target.kind == "liked":
                from ytmusicapi.models.content.enums import LikeStatus

                state = self._resolve_library_state(track, kind="liked")
                if state.like_status and not _is_liked(state.like_status):
                    return AddResult(
                        False, f"Not in {target.title}: {track.title}", "error"
                    )
                self._client().rate_song(track.video_id, LikeStatus.INDIFFERENT)
                return AddResult(True, f"Unliked: {track.title}")
            if not track.set_video_id:
                return AddResult(
                    False,
                    "Open this playlist in My Library to delete from it",
                    "error",
                )
            result = self._client().remove_playlist_items(
                target.playlist_id,
                [{"videoId": track.video_id, "setVideoId": track.set_video_id}],
            )
            if _playlist_add_succeeded(result):
                return AddResult(True, f"Deleted from {target.title}: {track.title}")
            if _looks_like_already_gone(result):
                return AddResult(True, f"Deleted from {target.title}: {track.title}")
            return AddResult(
                False, _playlist_error_message(result, target.title), "error"
            )
        except Exception as exc:  # noqa: BLE001
            if _looks_like_already_gone(exc):
                return AddResult(True, f"Deleted from {target.title}: {track.title}")
            return AddResult(False, str(exc) or f"Could not delete from {target.title}", "error")

    def create_playlist(self, title: str) -> PlaylistWriteResult:
        """Create an empty private playlist. Description is left blank."""
        if not self.authenticated:
            return PlaylistWriteResult(False, "Sign in (Settings) to create a playlist")
        name = title.strip()
        if not name:
            return PlaylistWriteResult(False, "Playlist name required")
        try:
            result = self._client().create_playlist(
                name, description="", privacy_status="PRIVATE"
            )
        except Exception as exc:  # noqa: BLE001
            return PlaylistWriteResult(False, str(exc) or "Could not create playlist")
        if isinstance(result, str) and result:
            return PlaylistWriteResult(True, f"Created playlist: {name}", playlist_id=result)
        return PlaylistWriteResult(False, _short_failure(result, "Could not create playlist"))

    def delete_playlist(self, playlist: PlaylistSummary) -> PlaylistWriteResult:
        """Delete a normal user playlist (not Liked / Saved / Episodes for Later)."""
        if not self.authenticated:
            return PlaylistWriteResult(False, "Sign in (Settings) to delete a playlist")
        if not is_user_playlist(playlist):
            return PlaylistWriteResult(False, f"{playlist.title} cannot be deleted")
        try:
            result = self._client().delete_playlist(playlist.playlist_id)
        except Exception as exc:  # noqa: BLE001
            return PlaylistWriteResult(
                False, _short_failure(exc, f'Could not delete playlist "{playlist.title}"')
            )
        if _playlist_delete_succeeded(result):
            return PlaylistWriteResult(
                True, f'Deleted playlist "{playlist.title}"', playlist_id=playlist.playlist_id
            )
        return PlaylistWriteResult(
            False, _short_failure(result, f'Could not delete playlist "{playlist.title}"')
        )

    def _resolve_library_state(
        self, track: Track, *, kind: Literal["saved", "liked"]
    ) -> LibraryState:
        state = LibraryState(
            like_status=track.like_status,
            in_library=track.in_library,
            add_token=track.library_add_token,
            remove_token=track.library_remove_token,
        )
        if kind == "liked" and state.like_status:
            return state
        if kind == "saved" and state.in_library is True and state.remove_token:
            return state
        if kind == "saved" and state.in_library is False and state.add_token:
            return state
        client = self._client()
        try:
            watch = client.get_watch_playlist(videoId=track.video_id, limit=5)
        except Exception:  # noqa: BLE001
            watch = None
        _apply_matching_track(state, watch, track.video_id)
        if kind == "liked" and state.like_status:
            return state
        if kind == "saved" and state.in_library is True and state.remove_token:
            return state
        if kind == "saved" and state.in_library is False and state.add_token:
            return state
        if kind == "saved" and track.album_id:
            try:
                album = client.get_album(track.album_id)
            except Exception:  # noqa: BLE001
                album = None
            _apply_matching_track(state, album, track.video_id)
        return state

    def get_library_playlists(
        self, limit: int = 50, *, show_episodes_for_later: bool = False
    ) -> list[PlaylistSummary]:
        """User library playlists (includes private) when authenticated."""
        if not self.authenticated:
            return []
        items = self._client().get_library_playlists(limit=limit)
        out: list[PlaylistSummary] = []
        for item in items:
            pid = item.get("playlistId")
            title = item.get("title")
            if not pid or not title:
                continue
            if pid == "LM" or pid.startswith("LM"):
                continue
            if not show_episodes_for_later and is_episodes_for_later(title):
                continue
            count = item.get("count")
            try:
                track_count = int(count) if count is not None else None
            except (TypeError, ValueError):
                track_count = None
            out.append(
                PlaylistSummary(
                    playlist_id=pid,
                    title=title,
                    author=item.get("author")
                    if isinstance(item.get("author"), str)
                    else None,
                    track_count=track_count,
                    thumbnail=(item.get("thumbnails") or [{}])[-1].get("url")
                    if item.get("thumbnails")
                    else None,
                )
            )
        return out

    def verify_auth(self) -> tuple[bool, str]:
        """Probe the authenticated client. Returns (ok, message)."""
        if self._auth_headers_path is None or not self._auth_headers_path.exists():
            return False, "No auth file — set path in Settings"
        try:
            # Force rebuild client from file
            self._yt = None
            self._authenticated = False
            client = self._client()
            if not self.authenticated:
                return False, "Auth file present but client is anonymous"
            # Stale cookies often 200 with an empty library instead of 401.
            playlists = client.get_library_playlists(limit=5) or []
            songs = client.get_library_songs(limit=5) or []
        except Exception as exc:  # noqa: BLE001
            self._authenticated = False
            self._yt = None
            return False, f"Auth failed: {exc}"

        n_pl, n_songs = len(playlists), len(songs)
        if n_pl == 0 and n_songs == 0:
            return (
                True,
                "OK — logged in, but 0 playlists and 0 songs. "
                "If you expect a library, re-copy browser headers (session may be stale).",
            )
        return True, f"OK — library reachable ({n_pl} playlists, {n_songs} songs in sample)"
