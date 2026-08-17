"""Discord Rich Presence"""

from __future__ import annotations

import logging
import queue
import threading
import time
from enum import Enum, auto
from typing import Any

from pypresence.presence import Presence
from pypresence.types import ActivityType

from models.track import Track
from services.player import PlayerSnapshot
from utils import display_duration

log = logging.getLogger(__name__)

# public Discord application id
DEFAULT_CLIENT_ID = "1538781593328422942"

class _Job(Enum):
    CONNECT = auto()
    UPDATE = auto()
    DISCONNECT = auto()
    STOP = auto()


class DiscordPresence:
    def __init__(self, client_id: str = DEFAULT_CLIENT_ID, enabled: bool = False) -> None:
        self.client_id = client_id
        self.enabled = enabled
        self._rpc: Presence | None = None
        self._connected = False
        self._queue: queue.Queue[tuple[Any, ...]] = queue.Queue()
        self._thread = threading.Thread(
            target=self._run, name="discord-rpc", daemon=True
        )
        self._thread.start()

    def connect(self) -> None:
        if not self.enabled:
            return
        self._queue.put((_Job.CONNECT,))

    def update(self, track: Track | None, snap: PlayerSnapshot) -> None:
        if not self.enabled:
            return
        self._queue.put((_Job.UPDATE, track, snap))

    def clear(self) -> None:
        self._queue.put((_Job.UPDATE, None, None))

    def close(self, *, join: bool = False) -> None:
        self._queue.put((_Job.DISCONNECT,))
        if join:
            self._queue.put((_Job.STOP,))
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        while True:
            job = self._queue.get()
            kind = job[0]
            try:
                match kind:
                    case _Job.CONNECT:
                        self._connect()
                    case _Job.UPDATE:
                        self._update(job[1], job[2])
                    case _Job.DISCONNECT:
                        self._disconnect()
                    case _Job.STOP:
                        self._disconnect()
                        return
            except Exception as exc:  # noqa: BLE001
                log.debug("Discord RPC worker failed: %s", exc)

    def _connect(self) -> None:
        if not self.enabled:
            return
        self._disconnect()
        try:
            self._rpc = Presence(self.client_id)
            self._rpc.connect()
            self._connected = True
        except Exception as exc:  # noqa: BLE001
            log.info("Discord RPC connect failed: %s", exc)
            self._connected = False
            self._rpc = None

    def _update(self, track: Track | None, snap: PlayerSnapshot | None) -> None:
        if not self.enabled or not self._connected or self._rpc is None:
            return
        if track is None or snap is None or snap.paused:
            self._clear()
            return
        try:
            now = time.time()
            position = max(0.0, snap.position)
            duration = display_duration(
                player=snap.duration,
                catalog=track.duration,
            )
            start = int((now - position) * 1000)
            end = int((now - position + duration) * 1000)
            self._rpc.update(
                activity_type=ActivityType.LISTENING,
                details=track.title[:128],
                state=track.artist_str[:128],
                start=start,
                end=end,
                large_image=track.thumbnail,
                large_url=track.watch_url,
            )
        except Exception as exc:  # noqa: BLE001
            log.debug("Discord RPC update failed: %s", exc)

    def _clear(self) -> None:
        if not self._connected or self._rpc is None:
            return
        try:
            self._rpc.clear()
        except Exception:  # noqa: BLE001
            pass

    def _disconnect(self) -> None:
        self._clear()
        if self._rpc is not None:
            try:
                self._rpc.close()
            except Exception:  # noqa: BLE001
                pass
        self._connected = False
        self._rpc = None
