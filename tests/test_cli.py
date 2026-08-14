"""CLI dependency check."""

from __future__ import annotations

from cli import check_dependencies


def test_check_dependencies_finds_mpv_ytdlp() -> None:
    missing = check_dependencies()
    # Both should be present in this environment
    assert "mpv" not in missing
    assert "yt-dlp" not in missing
