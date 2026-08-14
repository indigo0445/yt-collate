"""AppState snapshot should always reflect live mpv position."""

from __future__ import annotations

from pathlib import Path

from models.track import Artist, Track
from services.config import ConfigService
from services.player import FakeMpvTransport, PlayerService
from state import AppState


def _t(i: int) -> Track:
    return Track(video_id=f"v{i}", title=f"T{i}", artists=[Artist(name="A")])


def _state(tmp_path: Path) -> AppState:
    state = AppState(config=ConfigService(config_dir=tmp_path / "cfg"))
    transport = FakeMpvTransport()
    player = PlayerService()
    player._transport = transport
    player.on_update(state._on_player_update)
    state.player = player
    return state


def test_snapshot_reads_live_position_not_cached_snap(tmp_path: Path) -> None:
    state = AppState(config=ConfigService(config_dir=tmp_path / "cfg"))
    transport = FakeMpvTransport()
    player = PlayerService()
    player._transport = transport
    player.on_update(state._on_player_update)
    state.player = player

    player.play("https://www.youtube.com/watch?v=1")
    assert state.snapshot.position == 0.0
    assert state._last_snap is not None
    assert state._last_snap.position == 0.0

    player._handle_message(
        {"event": "property-change", "name": "duration", "data": 180.0}
    )
    player._handle_message(
        {"event": "property-change", "name": "time-pos", "data": 0.4}
    )
    player._handle_message(
        {"event": "property-change", "name": "time-pos", "data": 42.5}
    )
    # time-pos does not notify, so _last_snap stays at 0 — UI must still see 42.5
    assert state._last_snap.position == 0.0
    assert state.snapshot.position == 42.5


def test_eof_advances_to_next_track(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state.player.on_eof(state._on_eof)
    state.play_tracks([_t(1), _t(2), _t(3)], start_index=0)
    state.player._handle_message({"event": "end-file", "reason": "eof"})
    assert state.current_track is not None and state.current_track.video_id == "v2"
    assert state.queue_finished is False


def test_eof_last_track_is_finished_and_space_is_noop(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state.player.on_eof(state._on_eof)
    state.play_tracks([_t(1)])
    state.player._duration = 137.0
    state.player._position = 136.4
    state.player._handle_message({"event": "end-file", "reason": "eof"})
    assert state.queue_finished is True
    assert state.snapshot.position == 137.0
    assert state.snapshot.paused is True
    state.toggle_pause()
    assert state.queue_finished is True
    assert state.snapshot.paused is True
    assert state.status_message == "Playback finished"


def test_seek_back_from_finished_resumes(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state.player.on_eof(state._on_eof)
    state.play_tracks([_t(1)])
    transport = state.player._transport
    assert transport is not None
    loads = transport.loadfile_count()
    state.player._duration = 180.0
    state.player._position = 179.0
    state.player._handle_message({"event": "end-file", "reason": "eof"})
    assert state.queue_finished is True
    state.seek_relative(-30)
    assert state.queue_finished is False
    assert state.snapshot.eof is False
    assert state.snapshot.position == 150.0
    assert state.snapshot.paused is False
    assert transport.loadfile_count() == loads


def test_autoplay_defaults_off(tmp_path: Path) -> None:
    state = _state(tmp_path)
    assert state.config.config.autoplay is False
    assert state.queue.autoplay is False


def test_queue_insert_does_not_replace_current(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state.play_tracks([_t(1), _t(2)], start_index=0)
    state.queue_play_next([_t(8), _t(9)])
    assert [t.video_id for t in state.queue.queue] == ["v1", "v8", "v9", "v2"]
    assert state.current_track is not None and state.current_track.video_id == "v1"
    state.queue_append([_t(7)])
    assert [t.video_id for t in state.queue.queue] == ["v1", "v8", "v9", "v2", "v7"]
    assert state.current_track.video_id == "v1"


def test_seek_relative_jumps_thirty_seconds(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state.play_tracks([_t(1), _t(2)], start_index=0)
    state.player._position = 10.0
    state.player._duration = 180.0
    state.seek_relative(30)
    assert state.snapshot.position == 40.0
    assert state.current_track is not None and state.current_track.video_id == "v1"


def test_seek_tenth_matches_youtube(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state.play_tracks([_t(1)])
    state.player._loading = False
    state.player._duration = 180.0
    state.player._position = 40.0
    state.seek_tenth(0)
    assert state.snapshot.position == 0.0
    state.seek_tenth(5)
    assert state.snapshot.position == 90.0
    state.seek_tenth(9)
    assert state.snapshot.position == 162.0
    assert state.snapshot.paused is False


def test_seek_tenth_from_finished_resumes_without_reload(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state.player.on_eof(state._on_eof)
    state.play_tracks([_t(1)])
    transport = state.player._transport
    assert transport is not None
    loads = transport.loadfile_count()
    state.player._duration = 180.0
    state.player._position = 179.0
    state.player._handle_message({"event": "end-file", "reason": "eof"})
    assert state.queue_finished is True
    state.seek_tenth(3)
    assert state.queue_finished is False
    assert state.snapshot.position == 54.0
    assert state.snapshot.paused is False
    assert transport.loadfile_count() == loads


def test_seek_relative_clamps_before_start(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state.play_tracks([_t(1), _t(2)], start_index=0)
    state.player._position = 10.0
    state.player._duration = 180.0
    state.seek_relative(-30)
    assert state.snapshot.position == 0.0
    assert state.current_track is not None and state.current_track.video_id == "v1"


def test_seek_relative_near_start_stays_on_current(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state.play_tracks([_t(1), _t(2), _t(3)], start_index=0)
    state.next()
    state.player._position = 0.4
    state.player._duration = 180.0
    state.seek_relative(-30)
    assert state.current_track is not None and state.current_track.video_id == "v2"
    assert state.snapshot.position == 0.0


def test_seek_relative_past_end_goes_next(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state.play_tracks([_t(1), _t(2)], start_index=0)
    state.player._position = 170.0
    state.player._duration = 180.0
    state.seek_relative(30)
    assert state.current_track is not None and state.current_track.video_id == "v2"


def test_seek_relative_past_end_on_last_clamps_to_duration(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state.play_tracks([_t(1)])
    state.player._position = 170.0
    state.player._duration = 180.0
    state.seek_relative(30)
    assert state.current_track is not None and state.current_track.video_id == "v1"
    assert state.snapshot.position == 180.0
    assert state.queue_finished is True


def test_seek_relative_last_second_goes_next(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state.play_tracks([_t(1), _t(2)], start_index=0)
    state.player._loading = False
    state.player._position = 136.4
    state.player._duration = 137.0
    state.seek_relative(30)
    assert state.current_track is not None and state.current_track.video_id == "v2"


def test_seek_relative_ignored_while_loading(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state.play_tracks([_t(1), _t(2)], start_index=0)
    state.player._loading = True
    state.player._position = 0.0
    state.player._duration = 0.0
    state.seek_relative(30)
    assert state.snapshot.position == 0.0
    assert state.current_track is not None and state.current_track.video_id == "v1"


def test_seek_relative_does_not_pass_duration(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state.play_tracks([_t(1), _t(2)], start_index=0)
    state.player._loading = False
    state.player._position = 250.0
    state.player._duration = 277.0
    state.seek_relative(30)
    assert state.current_track is not None and state.current_track.video_id == "v2"
    assert state.snapshot.position == 0.0


def test_volume_change_is_saved(tmp_path: Path) -> None:
    state = _state(tmp_path)
    assert state.player.volume == 100
    state.volume_down()
    assert state.player.volume == 95
    assert state.config.config.volume == 95


def test_space_starts_unloaded_queue_from_beginning(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state.queue.play_all([_t(1), _t(2)], start_index=0)
    assert state.current_track is not None
    assert state.player.snapshot().url is None
    transport = state.player._transport
    assert transport is not None
    state.toggle_pause()
    assert transport.loadfile_count() == 1
    assert state.player.snapshot().url is not None
    assert state.player.snapshot().paused is False


def test_space_toggles_pause_without_reload_once_loaded(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state.play_tracks([_t(1)])
    transport = state.player._transport
    assert transport is not None
    n = transport.loadfile_count()
    state.toggle_pause()
    assert state.player.snapshot().paused is True
    assert transport.loadfile_count() == n
    state.toggle_pause()
    assert state.player.snapshot().paused is False
    assert transport.loadfile_count() == n


def test_previous_at_queue_head_does_not_restore_playlist_prefix(
    tmp_path: Path,
) -> None:
    state = _state(tmp_path)
    state.play_tracks([_t(1), _t(2), _t(3)], start_index=1)
    assert [t.video_id for t in state.queue.queue] == ["v2", "v3"]
    state.player._position = 0.4
    state.previous()
    assert state.current_track is not None and state.current_track.video_id == "v2"
    assert [t.video_id for t in state.queue.upcoming()] == ["v2", "v3"]


def test_play_restored_current_starts_unloaded_queue(tmp_path: Path) -> None:
    state = _state(tmp_path)
    state.queue.play_all([_t(1), _t(2)], start_index=0)
    transport = state.player._transport
    assert transport is not None
    state.play_restored_current()
    assert transport.loadfile_count() == 1
    assert state.player.snapshot().url is not None
    state.play_restored_current()
    assert transport.loadfile_count() == 1
