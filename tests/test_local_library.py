"""local playlist json next to Songs/"""

from __future__ import annotations

from pathlib import Path

from models.track import Artist, LocalPlaylist, Track
from services.local_library import (
    emoji_for_catalog_kind,
    emoji_for_library_id,
    load_local_playlists,
    playlist_filename,
    save_local_playlist,
)
from services.music import LIKED_PLAYLIST_ID, SAVED_SONGS_PLAYLIST_ID


def _song(video_id: str, title: str = "One") -> Track:
    return Track(video_id=video_id, title=title, artists=[Artist(name="A")])


def test_playlist_filename_sanitizes() -> None:
    assert playlist_filename("Chill Mix") == "Chill Mix.json"
    assert playlist_filename("a/b") == "a_b.json"
    assert playlist_filename("  ") == "Playlist.json"


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    root = tmp_path / "yt-collate"
    (root / "Songs").mkdir(parents=True)
    saved = save_local_playlist(
        LocalPlaylist(
            emoji="❤️",
            title="Liked Songs",
            tracks=[_song("aaaaaaaaaaa", "One"), _song("bbbbbbbbbbb", "Two")],
        ),
        root=root,
    )
    assert saved == root / "Liked Songs.json"
    assert saved.is_file()
    assert not (root / "Songs" / "Liked Songs.json").exists()
    loaded = load_local_playlists(root)
    assert len(loaded) == 1
    pl = loaded[0]
    assert pl.emoji == "❤️"
    assert pl.title == "Liked Songs"
    assert [t.title for t in pl.tracks] == ["One", "Two"]
    assert pl.tracks[0].artist_str == "A"


def test_load_skips_invalid_and_sorts(tmp_path: Path) -> None:
    root = tmp_path / "yt-collate"
    root.mkdir()
    (root / "Songs").mkdir()
    (root / "bad.json").write_text("{not json", encoding="utf-8")
    save_local_playlist(
        LocalPlaylist(emoji="📁", title="Zebra", tracks=[]), root=root
    )
    save_local_playlist(
        LocalPlaylist(emoji="🎵", title="Alpha", tracks=[]), root=root
    )
    titles = [pl.title for pl in load_local_playlists(root)]
    assert titles == ["Alpha", "Zebra"]


def test_library_and_catalog_emoji() -> None:
    assert emoji_for_library_id(LIKED_PLAYLIST_ID) == "❤️"
    assert emoji_for_library_id(SAVED_SONGS_PLAYLIST_ID) == "🎵"
    assert emoji_for_library_id("PLreal") == "📁"
    assert emoji_for_catalog_kind("album") == "💿"
    assert emoji_for_catalog_kind("artist") == "🎤"
    assert emoji_for_catalog_kind("playlist") == "📁"
