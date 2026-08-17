"""formatting helpers"""

from __future__ import annotations

from pathlib import Path

from rich.text import Text

from utils import (
    clip_list_label,
    display_duration,
    display_position,
    display_user_path,
    format_bitrate,
    format_time,
    row_activity_prompt,
    youtube_video_id,
)


class _Wide:
    size = type("S", (), {"width": 40})()


class _Unknown:
    size = type("S", (), {"width": 0})()


def test_format_time() -> None:
    assert format_time(0) == "0:00"
    assert format_time(254) == "4:14"
    assert format_time(253.7) == "4:13"


def test_display_user_path(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr("utils.Path.home", lambda *args: home)
    nested = home / ".config" / "yt-collate" / "browser.json"
    nested.parent.mkdir(parents=True)
    nested.write_text("{}\n")
    assert display_user_path(nested) == "~/.config/yt-collate/browser.json"
    assert display_user_path(home) == "~"
    outside = tmp_path / "other" / "browser.json"
    outside.parent.mkdir()
    outside.write_text("{}\n")
    assert display_user_path(outside) == str(outside.resolve())


def test_format_bitrate() -> None:
    assert format_bitrate(None) == ""
    assert format_bitrate(0) == ""
    assert format_bitrate(129632) == "130k"
    assert format_bitrate(251000) == "251k"


def test_clip_list_label_uses_widget_width() -> None:
    line = clip_list_label(_Wide(), "1. ", "A" * 80)
    assert line.startswith("1. ")
    assert len(line) == 40
    assert line.endswith("…")
    assert clip_list_label(_Unknown(), "1. ", "hello") == "1. hello"
    marked = clip_list_label(_Wide(), "1* ", "A" * 80, suffix=" — marked")
    assert marked.startswith("1* ")
    assert marked.endswith(" — marked")
    assert len(marked) == 40
    prompt = Text(marked)
    prompt.append(" (Fetching...)", style="italic")
    shown = str(prompt)
    assert "— marked (Fetching...)" in shown
    assert shown.index("— marked") < shown.index("(Fetching...)")


def test_row_activity_prompt_download_then_fetching() -> None:
    plain = row_activity_prompt("1. Mix")
    assert plain == "1. Mix"
    shown = str(row_activity_prompt("1. Mix", downloading=(134, 282), fetching=True))
    assert shown == "1. Mix (Downloading... 134/282) (Fetching...)"
    assert shown.index("(Downloading...") < shown.index("(Fetching...)")


def test_display_duration_keeps_catalog_when_player_is_slightly_short() -> None:
    # loading uses catalog 4:14; mpv often reports 253.7s which used to show 4:13
    assert display_duration(player=0.0, catalog=254) == 254.0
    assert display_duration(player=253.7, catalog=254) == 254.0
    assert format_time(display_duration(player=253.7, catalog=254)) == "4:14"


def test_display_duration_rounds_player_when_no_catalog() -> None:
    assert display_duration(player=253.7, catalog=None) == 254.0
    assert display_duration(player=0.0, catalog=None) == 0.0
    assert display_duration(player=180.0, catalog=0) == 180.0


def test_display_position_snaps_last_second_to_duration() -> None:
    assert display_position(136.4, 137.0) == 137.0
    assert format_time(display_position(136.4, 137.0)) == "2:17"
    assert display_position(120.0, 137.0) == 120.0
    assert display_position(136.4, 137.0, complete=True) == 137.0
    assert display_position(0.0, 180.0, complete=True) == 180.0


def test_youtube_video_id_from_watch_url() -> None:
    vid = "DF9Ydu4wxjQ"
    assert (
        youtube_video_id(f"https://www.youtube.com/watch?v={vid}&t=39s ") == vid
    )
    assert youtube_video_id(f"https://music.youtube.com/watch?v={vid}") == vid
    assert youtube_video_id(f"https://youtu.be/{vid}?t=39") == vid
    assert youtube_video_id(f"www.youtube.com/watch?v={vid}") == vid
    assert youtube_video_id(f"https://www.youtube.com/shorts/{vid}") == vid
    assert youtube_video_id("imagine dragons") is None
    assert youtube_video_id(vid) is None
    assert youtube_video_id("https://www.youtube.com/playlist?list=PLmix") is None
