"""serialize library writes. YouTube rejects overlapping playlist edits with HTTP 409"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from models.track import PlaylistSummary, Track
from services.music import (
    AddResult,
    LibraryTarget,
    MusicService,
    PlaylistWriteResult,
)

JobKind = Literal["add", "remove_song", "delete_playlist", "create_playlist"]

_CONFLICT_TRIES = 3
_CONFLICT_WAIT = 0.35


def _is_conflict(message: str) -> bool:
    text = message.casefold()
    return "409" in text or "conflict" in text


@dataclass(frozen=True)
class _Job:
    kind: JobKind
    track: Track | None = None
    target: LibraryTarget | None = None
    playlist: PlaylistSummary | None = None
    title: str | None = None
    on_add: Callable[[AddResult], None] | None = None
    on_playlist: Callable[[PlaylistWriteResult], None] | None = None


class LibraryJobQueue:
    # one background thread that runs add/delete/create in order

    def __init__(self, music: MusicService) -> None:
        self._music = music
        self._jobs: queue.Queue[_Job | None] = queue.Queue()
        self._lock = threading.Lock()
        self._inflight: set[tuple[object, ...]] = set()
        self._thread = threading.Thread(
            target=self._run, name="ytc-library-jobs", daemon=True
        )
        self._thread.start()

    def add_song(
        self,
        track: Track,
        target: LibraryTarget,
        on_done: Callable[[AddResult], None],
    ) -> None:
        self._jobs.put(_Job("add", track=track, target=target, on_add=on_done))

    def remove_song(
        self,
        track: Track,
        target: LibraryTarget,
        on_done: Callable[[AddResult], None],
    ) -> None:
        job = _Job("remove_song", track=track, target=target, on_add=on_done)
        if not self._claim(job):
            return
        self._jobs.put(job)

    def delete_playlist(
        self,
        playlist: PlaylistSummary,
        on_done: Callable[[PlaylistWriteResult], None],
    ) -> None:
        self._jobs.put(_Job("delete_playlist", playlist=playlist, on_playlist=on_done))

    def create_playlist(
        self, title: str, on_done: Callable[[PlaylistWriteResult], None]
    ) -> None:
        self._jobs.put(_Job("create_playlist", title=title, on_playlist=on_done))

    def shutdown(self) -> None:
        self._jobs.put(None)
        self._thread.join(timeout=3)

    def _run(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            try:
                self._execute(job)
            except Exception:  # noqa: BLE001
                pass
            finally:
                self._release(job)

    def _job_key(self, job: _Job) -> tuple[object, ...] | None:
        if job.kind != "remove_song" or job.track is None or job.target is None:
            return None
        ident = job.track.set_video_id or job.track.video_id
        return ("remove_song", job.target.playlist_id, ident)

    def _claim(self, job: _Job) -> bool:
        key = self._job_key(job)
        if key is None:
            return True
        with self._lock:
            if key in self._inflight:
                return False
            self._inflight.add(key)
            return True

    def _release(self, job: _Job | None) -> None:
        if job is None:
            return
        key = self._job_key(job)
        if key is None:
            return
        with self._lock:
            self._inflight.discard(key)

    def _execute(self, job: _Job) -> None:
        delay = _CONFLICT_WAIT
        add_result: AddResult | None = None
        playlist_result: PlaylistWriteResult | None = None
        for attempt in range(_CONFLICT_TRIES):
            add_result, playlist_result = self._run_job(job)
            conflict = False
            if add_result is not None:
                conflict = add_result.reason == "error" and _is_conflict(add_result.message)
            elif playlist_result is not None:
                conflict = (not playlist_result.ok) and _is_conflict(playlist_result.message)
            if not conflict or attempt == _CONFLICT_TRIES - 1:
                break
            time.sleep(delay)
            delay *= 1.5
        if add_result is not None and job.on_add is not None:
            job.on_add(add_result)
        if playlist_result is not None and job.on_playlist is not None:
            job.on_playlist(playlist_result)

    def _run_job(
        self, job: _Job
    ) -> tuple[AddResult | None, PlaylistWriteResult | None]:
        if job.kind == "add" and job.track is not None and job.target is not None:
            return self._music.add_song_to_target(job.track, job.target), None
        if job.kind == "remove_song" and job.track is not None and job.target is not None:
            return self._music.remove_song_from_target(job.track, job.target), None
        if job.kind == "delete_playlist" and job.playlist is not None:
            return None, self._music.delete_playlist(job.playlist)
        if job.kind == "create_playlist" and job.title is not None:
            return None, self._music.create_playlist(job.title)
        return None, None
