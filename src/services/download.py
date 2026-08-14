"""download audio into a flat ~/Music/yt-collate dump, named by video id"""

from __future__ import annotations

import queue
import re
import subprocess
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from models.track import Track

_YTDL_MUSIC_CLIENT = "youtube:player_client=web_music"

DOWNLOAD_SUBDIR = Path("Music") / "yt-collate"
LEGACY_DOWNLOAD_SUBDIR = Path("Music") / "ymlite"
_SAFE_ID = re.compile(r"[A-Za-z0-9_-]+")
_SKIP_SUFFIXES = {".part", ".ytdl", ".temp", ".tmp"}
_AUDIO_SUFFIXES = {".mp3", ".opus", ".ogg", ".m4a", ".aac", ".flac", ".wav"}
_VIDEO_LEFTOVERS = {".mp4", ".mkv", ".webm"}
_TRACK_TIMEOUT = 300

DownloadStatus = Literal["ok", "skipped", "error"]
RunFn = Callable[..., subprocess.CompletedProcess[str]]
CookiesFn = Callable[[], str | None]
BrowserFn = Callable[[], str | None]


def default_download_dir() -> Path:
    dest = Path.home() / DOWNLOAD_SUBDIR
    legacy = Path.home() / LEGACY_DOWNLOAD_SUBDIR
    if not dest.exists() and legacy.is_dir():
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            legacy.rename(dest)
        except OSError:
            return legacy
    return dest


def safe_video_id(video_id: str) -> str | None:
    if not video_id or "/" in video_id or "\\" in video_id or ".." in video_id:
        return None
    if _SAFE_ID.fullmatch(video_id):
        return video_id
    return None


def existing_download(dest: Path, video_id: str) -> Path | None:
    ident = safe_video_id(video_id)
    if ident is None or not dest.is_dir():
        return None
    matches = [
        path
        for path in dest.glob(f"{ident}.*")
        if path.is_file()
        and path.suffix.casefold() not in _SKIP_SUFFIXES
        and path.suffix.casefold() in _AUDIO_SUFFIXES
    ]
    if not matches:
        return None
    return min(matches, key=lambda p: p.name)


@dataclass
class TrackDownloadResult:
    track: Track
    status: DownloadStatus
    path: Path | None = None
    error: str | None = None


@dataclass
class DownloadBatchResult:
    items: list[TrackDownloadResult] = field(default_factory=list)
    collection: str | None = None

    @property
    def ok(self) -> int:
        return sum(1 for item in self.items if item.status == "ok")

    @property
    def skipped(self) -> int:
        return sum(1 for item in self.items if item.status == "skipped")

    @property
    def failed(self) -> int:
        return sum(1 for item in self.items if item.status == "error")


class DownloadService:
    def __init__(
        self,
        dest: Path | None = None,
        *,
        cookies: CookiesFn | None = None,
        cookies_from_browser: BrowserFn | None = None,
        run: RunFn | None = None,
    ) -> None:
        self.dest = dest or default_download_dir()
        self._cookies = cookies or (lambda: None)
        self._cookies_from_browser = cookies_from_browser or (lambda: None)
        self._run = run or subprocess.run

    def download_track(self, track: Track) -> TrackDownloadResult:
        ident = safe_video_id(track.video_id)
        if ident is None:
            return TrackDownloadResult(track, "error", error="Missing video id")
        self.dest.mkdir(parents=True, exist_ok=True)
        already = existing_download(self.dest, ident)
        if already is not None:
            return TrackDownloadResult(track, "skipped", path=already)
        cmd = self._command(track, ident)
        try:
            proc = self._run(
                cmd,
                capture_output=True,
                text=True,
                timeout=_TRACK_TIMEOUT,
                check=False,
            )
        except FileNotFoundError:
            return TrackDownloadResult(track, "error", error="yt-dlp is not installed")
        except subprocess.TimeoutExpired:
            return TrackDownloadResult(track, "error", error="Download timed out")
        except Exception as exc:  # noqa: BLE001
            return TrackDownloadResult(track, "error", error=str(exc))
        saved = existing_download(self.dest, ident)
        if proc.returncode == 0 and saved is not None:
            _remove_video_leftovers(self.dest, ident, keep=saved)
            return TrackDownloadResult(track, "ok", path=saved)
        detail = (proc.stderr or proc.stdout or "yt-dlp failed").strip()
        error = detail.splitlines()[-1] if detail else "yt-dlp failed"
        if "ffmpeg" in detail.casefold():
            error = "ffmpeg is required to extract audio"
        return TrackDownloadResult(track, "error", error=error)

    def _command(self, track: Track, ident: str) -> list[str]:
        out = str(self.dest / f"{ident}.%(ext)s")
        cmd = [
            "yt-dlp",
            "--no-playlist",
            "--no-progress",
            "--no-overwrites",
            "-x",
            "--audio-format",
            "opus",
            "--audio-quality",
            "0",
            "-f",
            "bestaudio/best",
            "-o",
            out,
        ]
        if not track.is_video:
            cmd.extend(["--extractor-args", _YTDL_MUSIC_CLIENT])
            cookies = self._cookies()
            browser = self._cookies_from_browser()
            if cookies:
                cmd.extend(["--cookies", cookies])
            elif browser:
                cmd.extend(["--cookies-from-browser", browser])
        cmd.append(track.watch_url)
        return cmd


def _remove_video_leftovers(dest: Path, ident: str, *, keep: Path) -> None:
    for path in dest.glob(f"{ident}.*"):
        if path == keep:
            continue
        if path.suffix.casefold() in _VIDEO_LEFTOVERS:
            path.unlink(missing_ok=True)


@dataclass
class _DownloadJob:
    tracks: list[Track]
    collection: str | None
    on_progress: Callable[[int, int], None] | None
    on_done: Callable[[DownloadBatchResult], None]


class DownloadJobQueue:
    # one background thread; playlist batches stay a single job

    def __init__(self, service: DownloadService) -> None:
        self._service = service
        self._jobs: queue.Queue[_DownloadJob | None] = queue.Queue()
        self._thread = threading.Thread(
            target=self._run, name="ytc-downloads", daemon=True
        )
        self._thread.start()

    def enqueue(
        self,
        tracks: Sequence[Track],
        *,
        collection: str | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        on_done: Callable[[DownloadBatchResult], None],
    ) -> None:
        packed = [t for t in tracks if t.video_id]
        if not packed:
            on_done(DownloadBatchResult(collection=collection))
            return
        self._jobs.put(
            _DownloadJob(
                tracks=packed,
                collection=collection,
                on_progress=on_progress,
                on_done=on_done,
            )
        )

    def shutdown(self) -> None:
        self._jobs.put(None)
        self._thread.join(timeout=3)

    def _run(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            try:
                result = self._execute(job)
                job.on_done(result)
            except Exception:  # noqa: BLE001
                pass

    def _execute(self, job: _DownloadJob) -> DownloadBatchResult:
        items: list[TrackDownloadResult] = []
        total = len(job.tracks)
        for i, track in enumerate(job.tracks, start=1):
            if job.on_progress is not None:
                job.on_progress(i, total)
            item = self._service.download_track(track)
            items.append(item)
            if item.error == "yt-dlp is not installed":
                break
        return DownloadBatchResult(items=items, collection=job.collection)
