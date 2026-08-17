"""local playlists under ~/Music/yt-collate"""

from __future__ import annotations

import json
import re
from pathlib import Path

from models.track import LocalPlaylist
from services import download as download_mod
from services.music import LIKED_PLAYLIST_ID, SAVED_SONGS_PLAYLIST_ID

PLAYLIST_SUFFIX = ".json"
_UNSAFE_NAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_CATALOG_EMOJI = {
    "album": "💿",
    "playlist": "📁",
    "artist": "🎤",
}


def library_root(root: Path | None = None) -> Path:
    return root if root is not None else download_mod.DOWNLOAD_DIR


def emoji_for_library_id(playlist_id: str) -> str:
    if playlist_id == LIKED_PLAYLIST_ID:
        return "❤️"
    if playlist_id == SAVED_SONGS_PLAYLIST_ID:
        return "🎵"
    return "📁"


def emoji_for_catalog_kind(kind: str) -> str:
    return _CATALOG_EMOJI.get(kind, "📁")


def playlist_filename(title: str) -> str:
    name = _UNSAFE_NAME.sub("_", title).strip(" .")
    return f"{name or 'Playlist'}{PLAYLIST_SUFFIX}"


def save_local_playlist(
    playlist: LocalPlaylist, *, root: Path | None = None
) -> Path:
    dest = library_root(root)
    dest.mkdir(parents=True, exist_ok=True)
    path = dest / playlist_filename(playlist.title)
    payload = playlist.model_dump(mode="json")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)
    return path


def load_local_playlists(root: Path | None = None) -> list[LocalPlaylist]:
    dest = library_root(root)
    if not dest.is_dir():
        return []
    found: list[LocalPlaylist] = []
    for path in sorted(dest.glob(f"*{PLAYLIST_SUFFIX}")):
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            found.append(LocalPlaylist.model_validate(data))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
    found.sort(key=lambda pl: pl.title.casefold())
    return found
