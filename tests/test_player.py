"""PlayerService pause contract tests."""

from __future__ import annotations

from yt_collate.services.player import (
    FakeMpvTransport,
    PlayerService,
    build_mpv_args,
    ytdl_raw_options,
)


def test_mpv_args_request_bestaudio_and_cookies() -> None:
    args = build_mpv_args(ipc_path="/tmp/ytc.sock", volume=80, cookies_file="/tmp/c.txt")
    assert "--ytdl-format=bestaudio/best" in args
    assert not any("player_client=web_music" in a for a in args)
    assert "--ytdl-raw-options-append=format-sort=abr" in args
    assert "--ytdl-raw-options-append=cookies=/tmp/c.txt" in args
    assert "--keep-open=always" in args


def test_ytdl_raw_options_switch_client() -> None:
    music = ytdl_raw_options(music_client=True, cookies_file="/tmp/c.txt")
    assert music["extractor-args"] == "youtube:player_client=web_music"
    assert music["cookies"] == "/tmp/c.txt"
    web = ytdl_raw_options(music_client=False, cookies_file="/tmp/c.txt")
    assert "extractor-args" not in web
    assert "cookies" not in web
    assert web["format-sort"] == "abr"


def test_play_sets_web_client_before_loadfile() -> None:
    transport = FakeMpvTransport()
    player = PlayerService(cookies_file="/tmp/c.txt")
    player._transport = transport
    player.play("https://www.youtube.com/watch?v=1", music_client=False)
    opts = next(
        c[2]
        for c in transport.commands
        if c[:2] == ["set_property", "ytdl-raw-options"]
    )
    assert "extractor-args" not in opts
    assert "cookies" not in opts
    load_at = next(i for i, c in enumerate(transport.commands) if c and c[0] == "loadfile")
    set_at = next(
        i
        for i, c in enumerate(transport.commands)
        if c[:2] == ["set_property", "ytdl-raw-options"]
    )
    assert set_at < load_at


def test_play_keeps_cookies_for_music_client() -> None:
    transport = FakeMpvTransport()
    player = PlayerService(cookies_file="/tmp/c.txt")
    player._transport = transport
    player.play("https://music.youtube.com/watch?v=1", music_client=True)
    opts = next(
        c[2]
        for c in transport.commands
        if c[:2] == ["set_property", "ytdl-raw-options"]
    )
    assert opts["extractor-args"] == "youtube:player_client=web_music"
    assert opts["cookies"] == "/tmp/c.txt"


def test_toggle_pause_does_not_reload() -> None:
    transport = FakeMpvTransport()
    player = PlayerService(volume=50)
    player._transport = transport

    player.play("https://www.youtube.com/watch?v=abc123")
    assert transport.loadfile_count() == 1
    assert player.snapshot().is_playing is True

    player.toggle_pause()
    assert player.snapshot().paused is True
    assert player.snapshot().is_playing is False
    assert transport.loadfile_count() == 1  # no second loadfile

    player.toggle_pause()
    assert player.snapshot().paused is False
    assert player.snapshot().is_playing is True
    assert transport.loadfile_count() == 1  # still only one loadfile


def test_resume_does_not_loadfile() -> None:
    transport = FakeMpvTransport()
    player = PlayerService()
    player._transport = transport

    player.play("https://www.youtube.com/watch?v=xyz")
    player.pause()
    assert transport.loadfile_count() == 1
    player.resume()
    assert transport.loadfile_count() == 1
    assert any(c[:2] == ["set_property", "pause"] for c in transport.commands)


def test_play_increments_generation() -> None:
    transport = FakeMpvTransport()
    player = PlayerService()
    player._transport = transport

    g1 = player.play("https://www.youtube.com/watch?v=1")
    g2 = player.play("https://www.youtube.com/watch?v=2")
    assert g2 == g1 + 1
    assert player.is_generation_current(g2)
    assert not player.is_generation_current(g1)


def test_stop_clears_current() -> None:
    transport = FakeMpvTransport()
    player = PlayerService()
    player._transport = transport
    player.play("https://www.youtube.com/watch?v=1")
    player.stop()
    assert player.snapshot().url is None
    assert player.snapshot().is_playing is False


def test_end_file_eof_fires_once() -> None:
    transport = FakeMpvTransport()
    player = PlayerService()
    player._transport = transport
    fired: list[int] = []
    player.on_eof(lambda: fired.append(1))
    player.play("https://www.youtube.com/watch?v=1")
    player._handle_message({"event": "end-file", "reason": "eof"})
    player._handle_message({"event": "end-file", "reason": "eof"})
    assert fired == [1]
    assert player.snapshot().eof is True


def test_eof_reached_property_fires_eof_once() -> None:
    transport = FakeMpvTransport()
    player = PlayerService()
    player._transport = transport
    fired: list[int] = []
    player.on_eof(lambda: fired.append(1))
    player.play("https://www.youtube.com/watch?v=1")
    player._handle_message(
        {"event": "property-change", "name": "eof-reached", "data": True}
    )
    player._handle_message(
        {"event": "property-change", "name": "eof-reached", "data": True}
    )
    assert fired == [1]
    assert player.snapshot().eof is True
    player._handle_message(
        {"event": "property-change", "name": "eof-reached", "data": False}
    )
    assert player.snapshot().eof is False


def test_eof_pins_position_to_duration() -> None:
    transport = FakeMpvTransport()
    player = PlayerService()
    player._transport = transport
    player.play("https://www.youtube.com/watch?v=1")
    player._duration = 137.0
    player._position = 136.4
    player._handle_message({"event": "end-file", "reason": "eof"})
    assert player.snapshot().position == 137.0
    assert player.snapshot().eof is True


def test_time_pos_updates_snapshot_without_notifying() -> None:
    transport = FakeMpvTransport()
    player = PlayerService()
    player._transport = transport
    notified: list[float] = []
    player.on_update(lambda snap: notified.append(snap.position))
    player.play("https://www.youtube.com/watch?v=1")
    notified.clear()

    player._handle_message(
        {"event": "property-change", "name": "duration", "data": 180.0}
    )
    player._handle_message(
        {"event": "property-change", "name": "time-pos", "data": 0.4}
    )
    player._handle_message(
        {"event": "property-change", "name": "time-pos", "data": 42.5}
    )
    assert player.snapshot().position == 42.5
    assert notified == []


def test_seek_updates_position_immediately() -> None:
    transport = FakeMpvTransport()
    player = PlayerService()
    player._transport = transport
    player.play("https://www.youtube.com/watch?v=1")
    player._duration = 200.0
    player.seek(45)
    assert player.snapshot().position == 45.0
    assert any(c[:2] == ["seek", 45.0] for c in transport.commands)


def test_seek_clamps_to_duration() -> None:
    transport = FakeMpvTransport()
    player = PlayerService()
    player._transport = transport
    player.play("https://www.youtube.com/watch?v=1")
    player._duration = 277.0
    player.seek(400)
    assert player.snapshot().position == 277.0


def test_seek_ignored_while_loading() -> None:
    transport = FakeMpvTransport()
    player = PlayerService()
    player._transport = transport
    player.play("https://www.youtube.com/watch?v=1")
    player._loading = True
    player._duration = 0.0
    player._position = 0.0
    player.seek(90)
    assert player.snapshot().position == 0.0
    assert not any(c and c[0] == "seek" for c in transport.commands)


def test_snapshot_clamps_stale_position() -> None:
    transport = FakeMpvTransport()
    player = PlayerService()
    player._transport = transport
    player.play("https://www.youtube.com/watch?v=1")
    player._duration = 277.0
    player._position = 400.0
    assert player.snapshot().position == 277.0


def test_play_seeks_to_start_after_load() -> None:
    transport = FakeMpvTransport()
    player = PlayerService()
    player._transport = transport
    player.play("https://www.youtube.com/watch?v=1", start=90)
    assert player.snapshot().loading is False
    assert player.snapshot().position == 90.0
    assert player.snapshot().eof is False


def test_end_file_error_clears_loading() -> None:
    transport = FakeMpvTransport()
    player = PlayerService()
    player._transport = transport
    errors: list[str] = []
    player.on_error(errors.append)
    player.play("https://www.youtube.com/watch?v=1")
    player._loading = True
    player._handle_message({"event": "end-file", "reason": "error"})
    assert player.loading is False
    assert player.snapshot().paused is True
    assert errors == ["error"]
