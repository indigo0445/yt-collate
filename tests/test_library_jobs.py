"""library mutation queue runs writes one at a time"""

from __future__ import annotations

import threading
import time

from models.track import Artist, PlaylistSummary, Track
from services.library_jobs import LibraryJobQueue
from services.music import AddResult, LibraryTarget, PlaylistWriteResult


def _song(video_id: str) -> Track:
    return Track(video_id=video_id, title=video_id, artists=[Artist(name="A")])


def test_library_jobs_run_serially() -> None:
    lock = threading.Lock()
    in_flight = 0
    max_in_flight = 0
    order: list[str] = []
    done = threading.Event()

    class FakeMusic:
        def add_song_to_target(self, track: Track, target: LibraryTarget) -> AddResult:
            nonlocal in_flight, max_in_flight
            with lock:
                in_flight += 1
                max_in_flight = max(max_in_flight, in_flight)
            time.sleep(0.05)
            with lock:
                in_flight -= 1
                order.append(track.video_id)
                if len(order) == 3:
                    done.set()
            return AddResult(True, f"Added {track.video_id}")

    jobs = LibraryJobQueue(FakeMusic())  # type: ignore[arg-type]
    target = LibraryTarget("playlist", "PLreal", "Mix")
    finished: list[str] = []
    try:
        for vid in ("a", "b", "c"):
            jobs.add_song(
                _song(vid),
                target,
                on_done=lambda result, vid=vid: finished.append(vid),
            )
        assert done.wait(timeout=2)
        assert order == ["a", "b", "c"]
        assert max_in_flight == 1
        assert finished == ["a", "b", "c"]
    finally:
        jobs.shutdown()


def test_library_jobs_retries_conflict_then_succeeds(monkeypatch) -> None:  # noqa: ANN001
    monkeypatch.setattr("services.library_jobs._CONFLICT_WAIT", 0.01)
    calls = {"n": 0}
    got: list[AddResult] = []
    done = threading.Event()

    class FakeMusic:
        def add_song_to_target(self, track: Track, target: LibraryTarget) -> AddResult:
            calls["n"] += 1
            if calls["n"] < 3:
                return AddResult(False, "Server returned HTTP 409: Conflict.", "error")
            return AddResult(True, f"Added {track.title}")

    jobs = LibraryJobQueue(FakeMusic())  # type: ignore[arg-type]
    try:
        jobs.add_song(
            _song("v1"),
            LibraryTarget("playlist", "PLreal", "Mix"),
            on_done=lambda result: (got.append(result), done.set()),
        )
        assert done.wait(timeout=2)
        assert calls["n"] == 3
        assert got[0].ok
    finally:
        jobs.shutdown()


def test_library_jobs_create_and_delete_playlist() -> None:
    created: list[str] = []
    deleted: list[str] = []
    done = threading.Event()

    class FakeMusic:
        def create_playlist(self, title: str) -> PlaylistWriteResult:
            created.append(title)
            return PlaylistWriteResult(True, f"Created playlist: {title}", playlist_id="PLnew")

        def delete_playlist(self, playlist: PlaylistSummary) -> PlaylistWriteResult:
            deleted.append(playlist.playlist_id)
            return PlaylistWriteResult(True, f'Deleted playlist "{playlist.title}"')

    jobs = LibraryJobQueue(FakeMusic())  # type: ignore[arg-type]
    try:
        jobs.create_playlist("Night", on_done=lambda result: None)
        jobs.delete_playlist(
            PlaylistSummary(playlist_id="PLold", title="Old"),
            on_done=lambda result: done.set(),
        )
        assert done.wait(timeout=2)
        assert created == ["Night"]
        assert deleted == ["PLold"]
    finally:
        jobs.shutdown()


def test_library_jobs_skips_duplicate_remove() -> None:
    calls: list[str] = []
    done = threading.Event()

    class FakeMusic:
        def remove_song_from_target(self, track: Track, target: LibraryTarget) -> AddResult:
            calls.append(track.video_id)
            time.sleep(0.05)
            done.set()
            return AddResult(True, f"Deleted {track.video_id}")

    jobs = LibraryJobQueue(FakeMusic())  # type: ignore[arg-type]
    target = LibraryTarget("playlist", "PLreal", "Mix")
    song = Track(
        video_id="v1", title="Fall", artists=[Artist(name="A")], set_video_id="set1"
    )
    try:
        jobs.remove_song(song, target, on_done=lambda result: None)
        jobs.remove_song(song, target, on_done=lambda result: None)
        jobs.remove_song(song, target, on_done=lambda result: None)
        assert done.wait(timeout=2)
        time.sleep(0.08)
        assert calls == ["v1"]
    finally:
        jobs.shutdown()
