"""mpv IPC playback service"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# player info for external access
@dataclass
class PlayerSnapshot:
    url: str | None = None
    paused: bool = True
    position: float = 0.0
    duration: float = 0.0
    volume: int = 100
    eof: bool = False
    loading: bool = False
    audio_bitrate: float | None = None

    @property
    def is_playing(self) -> bool:
        return bool(self.url) and not self.paused


Observer = Callable[[PlayerSnapshot], None]
EofHandler = Callable[[], None]

# YouTube InnerTube "player clients" are which app yt-dlp pretends to be
# `web_music` is YouTube Music (catalog songs). Plain YouTube videos are
# "Video unavailable" on that client. Cookies must stay off those videos
# too: signed-in TV/web clients return googlevideo URLs that ffmpeg/mpv
# fetches as HTTP 403. Commas are avoided because mpv splits
# --ytdl-raw-options on commas
_YTDL_MUSIC_CLIENT = "youtube:player_client=web_music" # official yt catalog songs
_YTDL_VIDEO_CLIENT = "youtube:player_client=visionos" # so it reliably plays non-song videos


def detect_ytdlp_js_runtime() -> str | None:
    # catalog `web_music` streams need n/signature solving. Deno is yt-dlp's
    # default; node and quickjs have to supplied as flags. Without any runtime,
    # yt-dlp returns only storyboards and mpv never starts the song.
    if shutil.which("deno"):
        return None
    if shutil.which("node"):
        return "node"
    if shutil.which("qjs"):
        return "quickjs"
    return None


# yt-dlp is NOT directly called, these are passed to mpv on every play
def ytdl_raw_options(
    *,
    music_client: bool,
    cookies_file: str | None = None,
    cookies_from_browser: str | None = None,
) -> dict[str, str]:
    opts: dict[str, str] = {
        "format-sort": "abr",
    }
    runtime = detect_ytdlp_js_runtime()
    if runtime:
        opts["js-runtimes"] = runtime
    if music_client:
        # ';formats=missing_pot' is needed to get enhanced bitrate for yt subscribers
        # spent hours figuring that out omg
        opts["extractor-args"] = f"{_YTDL_MUSIC_CLIENT};formats=missing_pot"
        if cookies_file:
            opts["cookies"] = cookies_file
        elif cookies_from_browser:
            opts["cookies-from-browser"] = cookies_from_browser
    else:
        opts["extractor-args"] = _YTDL_VIDEO_CLIENT
    return opts


# args for building permanent mpv process once
def build_mpv_args(
    *,
    ipc_path: str,
    volume: int,
    cookies_file: str | None = None,
    cookies_from_browser: str | None = None,
) -> list[str]:
    args = [
        "mpv",
        "--no-video",
        "--no-terminal",
        f"--volume={volume}",
        "--no-audio-display",
        "--really-quiet",
        "--msg-level=all=error",
        f"--input-ipc-server={ipc_path}",
        "--idle=yes",
        "--keep-open=always",
        "--cache=yes",
        "--cache-secs=30",
        "--network-timeout=20",
        "--gapless-audio=no",
        "--ytdl-format=bestaudio/best",
        "--ytdl-raw-options-append=format-sort=abr",
    ]
    runtime = detect_ytdlp_js_runtime()
    if runtime:
        args.append(f"--ytdl-raw-options-append=js-runtimes={runtime}")
    if cookies_file:
        args.append(f"--ytdl-raw-options-append=cookies={cookies_file}")
    elif cookies_from_browser:
        args.append(
            f"--ytdl-raw-options-append=cookies-from-browser={cookies_from_browser}",
        )
    return args


@dataclass
class PlayerService:
    # controls an idle mpv process over a JSON IPC unix socket

    volume: int = 100
    cookies_file: str | None = None
    cookies_from_browser: str | None = None
    _process: subprocess.Popen[str] | None = field(default=None, init=False, repr=False)
    _socket_path: str | None = field(default=None, init=False, repr=False)
    _sock: socket.socket | None = field(default=None, init=False, repr=False)
    _request_id: int = field(default=0, init=False, repr=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)
    _current_url: str | None = field(default=None, init=False, repr=False)
    _paused: bool = field(default=True, init=False, repr=False)
    _position: float = field(default=0.0, init=False, repr=False)
    _duration: float = field(default=0.0, init=False, repr=False)
    _eof: bool = field(default=False, init=False, repr=False)
    _observers: list[Observer] = field(default_factory=list, init=False, repr=False)
    _eof_handlers: list[EofHandler] = field(default_factory=list, init=False, repr=False)
    _error_handlers: list[Callable[[str], None]] = field(
        default_factory=list, init=False, repr=False
    )
    _reader_thread: threading.Thread | None = field(default=None, init=False, repr=False)
    _stop_reader: threading.Event = field(default_factory=threading.Event, init=False, repr=False)
    _pending: dict[int, dict[str, Any]] = field(default_factory=dict, init=False, repr=False)
    _started: bool = field(default=False, init=False, repr=False)
    _loading: bool = field(default=False, init=False, repr=False)
    _pending_seek: float | None = field(default=None, init=False, repr=False)
    _audio_bitrate: float | None = field(default=None, init=False, repr=False)
    _stderr_tail: list[str] = field(default_factory=list, init=False, repr=False)
    # for tests: inject a fake transport instead of real mpv
    _transport: Any | None = field(default=None, init=False, repr=False)

    @property
    def loading(self) -> bool:
        return self._loading

    def on_update(self, observer: Observer) -> None:
        self._observers.append(observer)

    def on_eof(self, handler: EofHandler) -> None:
        self._eof_handlers.append(handler)

    def on_error(self, handler: Callable[[str], None]) -> None:
        self._error_handlers.append(handler)

    def snapshot(self) -> PlayerSnapshot:
        # other classes can fetch at will
        duration = self._duration
        position = 0.0 if self._loading else self._position
        if duration > 0:
            position = min(position, duration)
        return PlayerSnapshot(
            url=self._current_url,
            paused=self._paused,
            position=position,
            duration=duration,
            volume=self.volume,
            eof=self._eof,
            loading=self._loading,
            audio_bitrate=None if self._loading else self._audio_bitrate,
        )

    def _notify(self) -> None:
        # sends observers an updated snapshot. currently only 1 observer: AppState._on_player_update
        snap = self.snapshot()
        for obs in list(self._observers):
            try:
                obs(snap)
            except Exception:  # noqa: BLE001
                pass

    def start(self) -> None:
        # only runs once. 
        if self._started:
            return
        # for tests: use a fake transport instead of real mpv
        if self._transport is not None:
            self._started = True
            self._transport.start(self)
            return
        self._socket_path = os.path.join(
            tempfile.gettempdir(),
            f"ytc-mpv-{os.getpid()}-{int(time.time() * 1000)}.sock",
        )
        if Path(self._socket_path).exists():
            Path(self._socket_path).unlink(missing_ok=True)

        args = build_mpv_args(
            ipc_path=self._socket_path,
            volume=self.volume,
            cookies_file=self.cookies_file,
            cookies_from_browser=self.cookies_from_browser,
        )

        self._process = subprocess.Popen[str](
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._stderr_tail.clear()
        self._connect_ipc(timeout=5.0)
        self._stop_reader.clear()
        self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
        self._reader_thread.start()
        err_thread = threading.Thread(target=self._read_stderr, daemon=True)
        err_thread.start()
        self._observe_properties()
        self._started = True

    def _connect_ipc(self, timeout: float) -> None:
        assert self._socket_path is not None
        deadline = time.time() + timeout
        last_err: Exception | None = None
        while time.time() < deadline:
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.connect(self._socket_path)
                sock.settimeout(0.5)
                self._sock = sock
                return
            except OSError as exc:
                last_err = exc
                time.sleep(0.05)
        raise RuntimeError(f"Failed to connect to mpv IPC: {last_err}")

    def _observe_properties(self) -> None:
        for i, prop in enumerate(
            ("time-pos", "duration", "pause", "eof-reached", "audio-bitrate"),
            start=1,
        ):
            self._send({"command": ["observe_property", i, prop]})

    def _send(self, payload: dict[str, Any], wait: bool = False) -> Any:
        if self._transport is not None:
            return self._transport.send(payload, wait=wait)
        with self._lock:
            if self._sock is None:
                raise RuntimeError("mpv IPC not connected")
            self._request_id += 1
            req_id = self._request_id
            payload = {**payload, "request_id": req_id}
            data = (json.dumps(payload) + "\n").encode("utf-8")
            if wait:
                self._pending[req_id] = {}
            self._sock.sendall(data)
            if not wait:
                return None
            deadline = time.time() + 2.0
            while time.time() < deadline:
                if "error" in self._pending.get(req_id, {}):
                    result = self._pending.pop(req_id)
                    if result.get("error") != "success":
                        return None
                    return result.get("data")
                time.sleep(0.01)
            self._pending.pop(req_id, None)
            return None

    def _read_loop(self) -> None:
        assert self._sock is not None
        buf = b""
        while not self._stop_reader.is_set():
            try:
                chunk = self._sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    try:
                        msg = json.loads(line.decode("utf-8"))
                    except json.JSONDecodeError:
                        continue
                    self._handle_message(msg)
            except TimeoutError:
                continue
            except OSError:
                break

    def _read_stderr(self) -> None:
        proc = self._process
        if proc is None or proc.stderr is None:
            return
        try:
            for line in proc.stderr:
                text = line.strip()
                if not text:
                    continue
                self._stderr_tail.append(text)
                if len(self._stderr_tail) > 30:
                    del self._stderr_tail[:-20]
        except (OSError, ValueError):
            return

    def _stderr_hint(self) -> str:
        if not self._stderr_tail:
            return ""
        return self._stderr_tail[-1]

    def _mark_loaded(self) -> None:
        # disambiguity: not the same as 'marking' a playlist
        if not self._loading:
            return
        self._loading = False
        start = self._pending_seek
        self._pending_seek = None
        if start is not None and start > 0:
            self.seek(start)
        else:
            self._position = 0.0
        self._notify()

    def _hit_eof(self) -> None:
        if self._loading or self._eof:
            return
        self._eof = True
        self._paused = True
        if self._duration > 0:
            self._position = self._duration
        self._notify()
        for handler in list(self._eof_handlers):
            try:
                handler()
            except Exception:  # noqa: BLE001
                pass

    def _handle_message(self, msg: dict[str, Any]) -> None:
        req_id = msg.get("request_id")
        if req_id is not None and req_id in self._pending:
            self._pending[req_id] = msg
            return

        event = msg.get("event")
        if event == "file-loaded" or (event == "playback-restart" and self._loading):
            self._mark_loaded()
            return
        if event == "end-file":
            reason = str(msg.get("reason") or "")
            if reason == "error":
                self._loading = False
                self._paused = True
                self._notify()
                detail = self._stderr_hint() or reason
                for handler in list(self._error_handlers):
                    try:
                        handler(detail)
                    except Exception:  # noqa: BLE001
                        pass
            elif reason == "eof":
                self._hit_eof()
            return

        if event == "property-change":
            name = msg.get("name")
            data = msg.get("data")
            if name == "time-pos" and isinstance(data, (int, float)):
                if self._loading:
                    return
                pos = float(data)
                if self._duration <= 0 and pos > 3.0:
                    return
                if self._duration > 0:
                    pos = min(pos, self._duration)
                self._position = pos
            elif name == "duration" and isinstance(data, (int, float)):
                dur = float(data)
                if dur > 0 and self._loading:
                    self._mark_loaded()
                if self._loading:
                    return
                self._duration = dur
                if self._duration > 0:
                    self._position = min(self._position, self._duration)
            elif name == "pause" and isinstance(data, bool):
                self._paused = data
                self._notify()
            elif name == "eof-reached":
                if data is True:
                    self._hit_eof()
                elif data is False:
                    self._eof = False
            elif name == "audio-bitrate":
                if self._loading:
                    return
                if isinstance(data, (int, float)) and data > 0:
                    self._audio_bitrate = float(data)
                else:
                    self._audio_bitrate = None

    def play(
        self, url: str, *, start: float | None = None, music_client: bool = True
    ) -> None:
        # load either a local file or a YouTube URL
        # if local file, music_client param is ignored
        # only called from _start_current and _resume_from in AppState
        self.start()

        with self._lock:
            self._current_url = url
            self._paused = False
            self._position = 0.0
            self._duration = 0.0
            self._eof = False
            self._loading = True
            self._pending_seek = start
            self._audio_bitrate = None
            self._stderr_tail.clear()
        self._notify()
        if url.startswith("http://") or url.startswith("https://"):
            self._send(
                {
                    "command": [
                        "set_property",
                        "ytdl-raw-options",
                        ytdl_raw_options(
                            music_client=music_client,
                            cookies_file=self.cookies_file,
                            cookies_from_browser=self.cookies_from_browser,
                        ),
                    ]
                }
            )
        # loadfile replace already aborts the previous item. An extra stop can
        # race and cancel the new ytdl load (song appears to never start)
        # actually that was not the problem (?) still dont really know
        self._send({"command": ["loadfile", url, "replace"]})
        self._send({"command": ["set_property", "pause", False]})
        self._send({"command": ["set_property", "volume", self.volume]})

    def toggle_pause(self) -> None:
        # toggle pause only — never reload the file
        if not self._current_url:
            return
        self.start()
        new_paused = not self._paused
        self._send({"command": ["set_property", "pause", new_paused]})
        self._paused = new_paused
        self._notify()

    def pause(self) -> None:
        if not self._current_url:
            return
        self.start()
        self._send({"command": ["set_property", "pause", True]})
        self._paused = True
        self._notify()

    def resume(self) -> None:
        if not self._current_url:
            return
        self.start()
        self._send({"command": ["set_property", "pause", False]})
        self._paused = False
        self._notify()

    def stop(self) -> None:
        with self._lock:
            self._current_url = None
            self._paused = True
            self._position = 0.0
            self._duration = 0.0
            self._eof = False
            self._loading = False
            self._pending_seek = None
            self._audio_bitrate = None
        if self._started:
            self._send({"command": ["stop"]})
        self._notify()

    def set_volume(self, volume: int) -> None:
        self.volume = max(0, min(100, int(volume)))
        if self._started:
            self._send({"command": ["set_property", "volume", self.volume]})
        self._notify()

    def seek(self, seconds: float) -> None:
        if not self._current_url or self._loading:
            return
        pos = max(0.0, float(seconds))
        if self._duration > 0:
            pos = min(pos, self._duration)
        self._position = pos
        if self._duration <= 0 or pos < self._duration - 0.25:
            self._eof = False
        self._send({"command": ["seek", pos, "absolute"]})

    def shutdown(self) -> None:
        self._stop_reader.set()
        if self._transport is not None:
            self._transport.shutdown()
            self._started = False
            return
        try:
            if self._sock is not None:
                try:
                    self._send({"command": ["quit"]})
                except Exception:  # noqa: BLE001
                    pass
                self._sock.close()
        finally:
            self._sock = None
        if self._process is not None:
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
        if self._socket_path:
            Path(self._socket_path).unlink(missing_ok=True)
            self._socket_path = None
        self._started = False


class _IpcTransport:
    # test double interface

    def start(self, player: PlayerService) -> None:  # noqa: ARG002
        raise NotImplementedError

    def send(self, payload: dict[str, Any], wait: bool = False) -> Any:  # noqa: ARG002
        raise NotImplementedError

    def shutdown(self) -> None:
        raise NotImplementedError


class FakeMpvTransport(_IpcTransport):
    # in-memory mpv stand-in for unit tests

    def __init__(self) -> None:
        self.commands: list[list[Any]] = []
        self.player: PlayerService | None = None
        self.paused = True
        self.volume = 100
        self.loaded_url: str | None = None

    def start(self, player: PlayerService) -> None:
        self.player = player

    def send(self, payload: dict[str, Any], wait: bool = False) -> Any:
        cmd = payload.get("command", [])
        self.commands.append(list(cmd))
        if not cmd:
            return None
        op = cmd[0]
        if op == "loadfile":
            self.loaded_url = cmd[1]
            self.paused = False
            if self.player:
                self.player._paused = False
                self.player._current_url = self.loaded_url
                self.player._handle_message({"event": "file-loaded"})
        elif op == "set_property":
            prop, value = cmd[1], cmd[2]
            if prop == "pause":
                self.paused = bool(value)
                if self.player:
                    self.player._paused = self.paused
            elif prop == "volume":
                self.volume = int(value)
                if self.player:
                    self.player.volume = self.volume
        elif op == "seek":
            seconds = float(cmd[1])
            if self.player:
                self.player._position = seconds
        elif op == "stop":
            self.loaded_url = None
            self.paused = True
        if wait:
            return None
        return None

    def shutdown(self) -> None:
        return None

    def loadfile_count(self) -> int:
        return sum(1 for c in self.commands if c and c[0] == "loadfile")
