"""Optional Discord Rich Presence."""

from __future__ import annotations

import logging
import time
from typing import Any

from models.track import Track

log = logging.getLogger(__name__)

# Public Discord application id placeholder — users can override.
DEFAULT_CLIENT_ID = "1400000000000000000"


class DiscordPresence:
    def __init__(self, client_id: str = DEFAULT_CLIENT_ID, enabled: bool = False) -> None:
        self.client_id = client_id
        self.enabled = enabled
        self._rpc: Any = None
        self._connected = False
        self._started_at: float | None = None

    def connect(self) -> bool:
        if not self.enabled:
            return False
        try:
            from pypresence import Presence
        except ImportError:
            log.info("pypresence not installed; Discord RPC disabled")
            return False
        try:
            self._rpc = Presence(self.client_id)
            self._rpc.connect()
            self._connected = True
            return True
        except Exception as exc:  # noqa: BLE001
            log.info("Discord RPC connect failed: %s", exc)
            self._connected = False
            return False

    def update(self, track: Track | None, *, paused: bool, position: float = 0.0) -> None:
        if not self.enabled or not self._connected or self._rpc is None:
            return
        if track is None or paused:
            self.clear()
            return
        try:
            now = time.time()
            start = int(now - max(0.0, position))
            payload: dict[str, Any] = {
                "details": track.title[:128],
                "state": track.artist_str[:128],
                "start": start,
            }
            self._rpc.update(**payload)
            self._started_at = start
        except Exception as exc:  # noqa: BLE001
            log.debug("Discord RPC update failed: %s", exc)

    def clear(self) -> None:
        if not self._connected or self._rpc is None:
            return
        try:
            self._rpc.clear()
        except Exception:  # noqa: BLE001
            pass

    def close(self) -> None:
        self.clear()
        if self._rpc is not None:
            try:
                self._rpc.close()
            except Exception:  # noqa: BLE001
                pass
        self._connected = False
        self._rpc = None
