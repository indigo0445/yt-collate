"""Queue service tests."""

from __future__ import annotations

from pathlib import Path

from yt_collate.models.config import RepeatMode
from yt_collate.models.music import Artist, Track
from yt_collate.services.queue import QueueService


def _t(i: int) -> Track:
    return Track(video_id=f"v{i}", title=f"T{i}", artists=[Artist(name="A")])


def test_play_next_and_advance(tmp_path: Path) -> None:
    q = QueueService(tmp_path / "player-state.json")
    q.hydrate()
    q.play_track(_t(1))
    q.add(_t(2))
    q.play_next(_t(3))
    # queue: [1, 3, 2], index 0
    assert [t.video_id for t in q.queue] == ["v1", "v3", "v2"]
    assert q.next_track() is not None
    assert q.current is not None and q.current.video_id == "v3"


def test_repeat_one(tmp_path: Path) -> None:
    q = QueueService(tmp_path / "ps.json")
    q.hydrate()
    q.play_track(_t(1))
    q.repeat = RepeatMode.ONE
    nxt = q.next_track()
    assert nxt is not None and nxt.video_id == "v1"


def test_persist(tmp_path: Path) -> None:
    path = tmp_path / "ps.json"
    q = QueueService(path)
    q.hydrate()
    q.play_all([_t(1), _t(2)], start_index=1)
    q.save()

    q2 = QueueService(path)
    q2.hydrate()
    assert [t.video_id for t in q2.queue] == ["v2"]
    assert q2.index == 0


def test_play_all_starts_at_selected_head(tmp_path: Path) -> None:
    q = QueueService(tmp_path / "ps.json")
    q.hydrate()
    q.play_all([_t(1), _t(2), _t(3), _t(4)], start_index=2)
    assert [t.video_id for t in q.queue] == ["v3", "v4"]
    assert q.index == 0
    assert q.previous_track() is None
    assert [t.video_id for t in q.queue] == ["v3", "v4"]
    assert q.current is not None and q.current.video_id == "v3"


def test_upcoming_linear_starts_at_current(tmp_path: Path) -> None:
    q = QueueService(tmp_path / "ps.json")
    q.hydrate()
    q.play_all([_t(1), _t(2), _t(3), _t(4)], start_index=1)
    assert [t.video_id for t in q.upcoming()] == ["v2", "v3", "v4"]
    q.next_track()
    assert [t.video_id for t in q.upcoming()] == ["v3", "v4"]


def test_insert_next_playlist_keeps_current(tmp_path: Path) -> None:
    q = QueueService(tmp_path / "ps.json")
    q.hydrate()
    q.play_all([_t(1), _t(2), _t(3)], start_index=0)
    q.insert_next([_t(8), _t(9)])
    assert [t.video_id for t in q.queue] == ["v1", "v8", "v9", "v2", "v3"]
    assert q.current is not None and q.current.video_id == "v1"
    assert [t.video_id for t in q.upcoming()] == ["v1", "v8", "v9", "v2", "v3"]


def test_append_playlist_to_end(tmp_path: Path) -> None:
    q = QueueService(tmp_path / "ps.json")
    q.hydrate()
    q.play_all([_t(1), _t(2)], start_index=0)
    q.append([_t(8), _t(9)])
    assert [t.video_id for t in q.queue] == ["v1", "v2", "v8", "v9"]
    assert q.current is not None and q.current.video_id == "v1"


def test_shuffle_remaining_keeps_current_first(tmp_path: Path) -> None:
    q = QueueService(tmp_path / "ps.json")
    q.hydrate()
    q.play_all([_t(1), _t(2), _t(3), _t(4)], start_index=1)
    assert q.shuffle_remaining()
    assert q.current is not None and q.current.video_id == "v2"
    rest = {t.video_id for t in q.upcoming()[1:]}
    assert rest == {"v3", "v4"}
    q.play_all([_t(1)], start_index=0)
    assert q.shuffle_remaining() is False
