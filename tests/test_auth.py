"""Auth helper unit tests."""

from __future__ import annotations

from pathlib import Path

from services.music import MusicService, track_from_song


def test_verify_auth_without_file(tmp_path: Path) -> None:
    missing = tmp_path / "nope.json"
    svc = MusicService(auth_headers_path=missing)
    ok, msg = svc.verify_auth()
    assert ok is False
    assert "No auth file" in msg


def test_track_from_song_still_works() -> None:
    t = track_from_song({"videoId": "x", "title": "T", "artists": [{"name": "A"}]})
    assert t is not None and t.video_id == "x"
