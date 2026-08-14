"""playback queue management with persistence"""

from __future__ import annotations

import random
from collections.abc import Sequence
from pathlib import Path

from models.config import RepeatMode
from models.player_state import PlayerStateFile
from models.track import Track
from services.config import _read_model, _write_model


class QueueService:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.queue: list[Track] = []
        self.index: int = 0
        self.repeat: RepeatMode = RepeatMode.OFF
        self.autoplay: bool = False
        self._hydrated = False

    def hydrate(self) -> None:
        # restores saved queue file once, on startup
        if self._hydrated:
            return
        state = _read_model(self.path, PlayerStateFile, PlayerStateFile())
        self.queue = list(state.queue)
        self.index = max(0, min(state.index, max(0, len(self.queue) - 1)))
        self._hydrated = True

    def save(self) -> None:
        # refuse to overwrite saved queue file if not hydrated
        if not self._hydrated:
            return
        _write_model(
            self.path,
            PlayerStateFile(
                queue=self.queue,
                index=self.index,
            ),
        )

    @property
    def current(self) -> Track | None:
        if not self.queue or self.index < 0 or self.index >= len(self.queue):
            return None
        return self.queue[self.index]

    def upcoming(self) -> list[Track]:
        # now playing, then the rest of the queue
        self.hydrate()
        if not self.queue:
            return []
        return list(self.queue[self.index :])

    def skip_to_upcoming(self, upcoming_index: int) -> Track | None:
        # jump to the Nth upcoming track (0 = current)
        self.hydrate()
        target = self.index + upcoming_index
        if upcoming_index < 0 or target >= len(self.queue):
            return None
        self.index = target
        self.save()
        return self.current

    def play_track(self, track: Track, *, clear: bool = True) -> Track:
        self.hydrate()
        if clear:
            self.queue = [track]
            self.index = 0
        else:
            self.queue.append(track)
            self.index = len(self.queue) - 1
        self.save()
        return track

    def play_all(self, tracks: list[Track], start_index: int = 0) -> Track | None:
        self.hydrate()
        if not tracks:
            return None
        start = max(0, min(start_index, len(tracks) - 1))
        self.queue = list(tracks[start:])
        self.index = 0
        self.save()
        return self.current

    def insert_next(self, tracks: Sequence[Track]) -> None:
        # insert tracks immediately after the current song (play-next)
        self.hydrate()
        items = list(tracks)
        if not items:
            return
        if not self.queue:
            self.queue = items
            self.index = 0
        else:
            at = self.index + 1
            self.queue[at:at] = items
        self.save()

    def append(self, tracks: Sequence[Track]) -> None:
        # append tracks to the end of the queue
        self.hydrate()
        items = list(tracks)
        if not items:
            return
        empty = not self.queue
        self.queue.extend(items)
        if empty:
            self.index = 0
        self.save()

    def add(self, track: Track) -> None:
        self.append([track])

    def play_next(self, track: Track) -> None:
        self.insert_next([track])

    def shuffle_remaining(self) -> bool:
        # keep the current track; shuffle everything after it. True if changed
        self.hydrate()
        rest = self.queue[self.index + 1 :]
        if len(rest) < 2:
            return False
        random.shuffle(rest)
        self.queue = self.queue[: self.index + 1] + rest
        self.save()
        return True

    def cycle_repeat(self) -> RepeatMode:
        self.hydrate()
        order = [RepeatMode.OFF, RepeatMode.ALL, RepeatMode.ONE]
        self.repeat = order[(order.index(self.repeat) + 1) % len(order)]
        self.save()
        return self.repeat

    def has_next(self) -> bool:
        # true if next_track() would return a song (including repeat wrap/loop)
        self.hydrate()
        if not self.queue:
            return False
        if self.repeat == RepeatMode.ONE:
            return True
        if self.index + 1 < len(self.queue):
            return True
        return self.repeat == RepeatMode.ALL

    def next_track(self) -> Track | None:
        self.hydrate()
        if not self.queue:
            return None
        if self.repeat == RepeatMode.ONE:
            return self.current
        if self.index + 1 < len(self.queue):
            self.index += 1
            self.save()
            return self.current
        if self.repeat == RepeatMode.ALL:
            self.index = 0
            self.save()
            return self.current
        return None

    def previous_track(self) -> Track | None:
        self.hydrate()
        if not self.queue or self.index <= 0:
            return None
        self.index -= 1
        self.save()
        return self.current
