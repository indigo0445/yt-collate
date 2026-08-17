"""central app runtime wiring player, queue, music, and persistence"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from models.track import Track
from services.config import ConfigService
from services.discord_rpc import DiscordPresence
from services.download import (
    SONGS_DIR,
    DownloadJobQueue,
    DownloadService,
    existing_download,
)
from services.library_jobs import LibraryJobQueue
from services.music import LibraryTarget, MusicService
from services.player import PlayerService, PlayerSnapshot
from services.queue import QueueService
from services.random_song import pick_random_song
from services.stream import cookies_and_user_agent
from utils import display_user_path

Listener = Callable[[], None]


@dataclass
class AppState:
    config: ConfigService = field(default_factory=ConfigService)
    player: PlayerService = field(init=False)
    music: MusicService = field(init=False)
    queue: QueueService = field(init=False)
    discord: DiscordPresence = field(init=False)
    library_jobs: LibraryJobQueue = field(init=False)
    downloads: DownloadJobQueue = field(init=False)
    status_message: str = ""
    library_mark: LibraryTarget | None = None
    queue_finished: bool = False
    register: list[Track] = field(default_factory=list) # simulates Vim unnamed register
    _listeners: list[Listener] = field(default_factory=list, init=False, repr=False)
    _last_snap: PlayerSnapshot | None = field(default=None, init=False, repr=False)
    _history_pushed_id: str | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        cfg = self.config.config
        self.player = PlayerService(
            volume=cfg.volume,
            cookies_file=cfg.cookies_file,
            cookies_from_browser=cfg.cookies_from_browser,
        )
        auth_path = self.config.auth_headers_path
        # load path only — never network-probe here (blocks TUI startup)
        self.music = MusicService(auth_headers_path=auth_path if auth_path.exists() else None)
        self.queue = QueueService(self.config.player_state_path)
        self.discord = DiscordPresence(enabled=cfg.discord_rpc)
        self.library_jobs = LibraryJobQueue(self.music)
        self.downloads = DownloadJobQueue(
            DownloadService( # default download dir
                cookies=lambda: self.player.cookies_file,
                cookies_from_browser=lambda: self.player.cookies_from_browser,
            )
        )

        self.queue.hydrate()
        self.queue.repeat = cfg.repeat
        self.queue.autoplay = cfg.autoplay

        if self.music.authenticated:
            self.status_message = f"Auth: {auth_path.name}"
        else:
            self.status_message = "Auth: anonymous"

        self.player.on_update(self._on_player_update)
        self.player.on_eof(self._on_eof)
        self.player.on_error(self._on_play_error)
        self._refresh_playback_cookies()
        # Discord connect deferred — can block if Discord isn't running

    def play_restored_current(self) -> None:
        # start the persisted current track from 0 if nothing is loaded yet
        if self.current_track is not None and not self.player.snapshot().url:
            self._start_current()

    def subscribe(self, listener: Listener) -> None:
        self._listeners.append(listener)

    def _emit(self) -> None:
        for listener in list(self._listeners):
            try:
                listener()
            except Exception:  # noqa: BLE001
                pass

    def _on_player_update(self, snap: PlayerSnapshot) -> None:
        prev = self._last_snap
        self._last_snap = snap
        # if the player state has not changed, skip
        if (
            prev is not None
            and prev.paused == snap.paused
            and prev.url == snap.url
            and prev.eof == snap.eof
            and prev.loading == snap.loading
        ):
            return
        track = self.queue.current
        self.discord.update(track, snap)
        self._emit()

    def _on_play_error(self, reason: str) -> None:
        self.status_message = f"Playback failed ({reason})"
        self._emit()

    def _on_eof(self) -> None:
        leaving = self.queue.current
        nxt = self.queue.next_track()
        if nxt is not None:
            self._start_current()
            return
        if self.queue.autoplay and leaving is not None:
            related = self.music.get_related(leaving.video_id, limit=5)
            if related:
                pick = related[0]
                self.queue.add(pick)
                self.queue.index = len(self.queue.queue) - 1
                self.queue.save()
                self._start_current()
                return
        self._finish_queue()

    @property
    def snapshot(self) -> PlayerSnapshot:
        # always read live mpv state — _last_snap is only for change detection
        return self.player.snapshot()

    @property
    def current_track(self) -> Track | None:
        return self.queue.current

    def play_track(self, track: Track, *, clear_queue: bool = True) -> None:
        self.queue.play_track(track, clear=clear_queue)
        self._start_current()

    def play_tracks(self, tracks: list[Track], start_index: int = 0) -> None:
        self.queue.play_all(tracks, start_index=start_index)
        self._start_current()

    def play_upcoming(self, upcoming_index: int) -> None:
        # jump within the current playback order (does not rebuild the queue)
        if self.queue.skip_to_upcoming(upcoming_index) is not None:
            self._start_current()

    def _refresh_playback_cookies(self) -> None:
        # give mpv the same YouTube cookies as the Music API (from browser.json)
        cfg = self.config
        if cfg.config.cookies_file:
            path: str | None = str(Path(cfg.config.cookies_file).expanduser())
        else:
            auth = cfg.auth_headers_path if cfg.auth_headers_path.exists() else None
            cookies, _ua = cookies_and_user_agent(
                auth, cfg.config_dir / "yt-dlp-cookies.txt"
            )
            path = str(cookies) if cookies else None
        if not self.player._started:
            self.player.cookies_file = path or cfg.config.cookies_file
            self.player.cookies_from_browser = cfg.config.cookies_from_browser

    def _finish_queue(self) -> None:
        self.queue_finished = True
        self.player.pause()
        self.status_message = "Playback finished"
        self._emit()

    def _playback_source(self, track: Track) -> str:
        # prioritize local audio file, else YouTube URL
        local = existing_download(SONGS_DIR, track.video_id)
        if local is not None:
            return str(local)
        return track.watch_url

    def _start_current(self) -> None:
        track = self.queue.current
        if track is None:
            return
        self.queue_finished = False
        try:
            self.player.play(self._playback_source(track), music_client=not track.is_video)
        except Exception as exc:  # noqa: BLE001
            self.status_message = f"Playback failed: {exc}"
            self._emit()
            return
        self._push_history(track)
        self.status_message = f"Playing: {track.display}"
        self._emit()

    def _push_history(self, track: Track) -> None:
        # record a started play on the YouTube account. Anonymous: skip entirely
        if not self.music.authenticated:
            return
        if self._history_pushed_id == track.video_id:
            return
        self._history_pushed_id = track.video_id

        def work() -> None:
            try:
                self.music.add_history_item(track)
            except Exception:  # noqa: BLE001
                pass

        threading.Thread(target=work, daemon=True, name="yt-history").start()

    def toggle_pause(self) -> None:
        if self.queue_finished:
            return
        if self.current_track is None:
            return
        if not self.player.snapshot().url:
            # queue restored on launch, but nothing is loaded yet — start from 0
            self._start_current()
            return
        self.player.toggle_pause()
        snap = self.player.snapshot()
        self.status_message = "Paused" if snap.paused else "Playing"
        self._emit()

    def next(self) -> None:
        track = self.queue.next_track()
        if track:
            self._start_current()
        else:
            self.status_message = "End of queue"
            self._emit()

    def previous(self) -> None:
        # restart if >3s into track, else previous
        snap = self.snapshot
        if snap.position > 3 and self.current_track:
            if self.queue_finished or snap.eof:
                self._resume_from(0)
            else:
                self.queue_finished = False
                self.player.seek(0)
                self.player.resume()
                self._emit()
            return
        track = self.queue.previous_track()
        if track:
            self._start_current()

    def _resume_from(self, position: float) -> None:
        # seek back into the current track. keep-open leaves it loaded after EOF
        track = self.queue.current
        if track is None:
            return
        self.queue_finished = False
        if self.player.snapshot().url:
            self.player.seek(max(0.0, position))
            self.player.resume()
            self.status_message = f"Playing: {track.display}"
            self._emit()
            return
        try:
            self.player.play(
                self._playback_source(track),
                start=max(0.0, position),
                music_client=not track.is_video,
            )
        except Exception as exc:  # noqa: BLE001
            self.status_message = f"Playback failed: {exc}"
            self._emit()
            return
        self.status_message = f"Playing: {track.display}"
        self._emit()

    def seek_relative(self, delta: float) -> None:
        # skip by `delta` seconds. Past end with a next track → next; otherwise clamp
        # 30-second jumps are implemented here but currently unbound
        if self.current_track is None or self.player.loading:
            return
        snap = self.snapshot
        duration = snap.duration
        if duration <= 0:
            return
        at_end = self.queue_finished or snap.eof
        pos = duration if at_end else snap.position
        target = pos + delta
        if target < 0:
            target = 0.0
        if at_end:
            if delta >= 0:
                return
            self._resume_from(target)
            return
        if target >= duration - 1:
            if self.queue.has_next():
                self.next()
            else:
                self.player.seek(duration)
                if not self.queue.autoplay:
                    self._finish_queue()
                else:
                    self._emit()
            return
        self.player.seek(target)
        self._emit()

    def seek_tenth(self, tenth: int) -> None:
        # jump to n/10 of the track (YouTube 0–9: 0% … 90%)
        if self.current_track is None or self.player.loading:
            return
        snap = self.snapshot
        duration = snap.duration
        if duration <= 0:
            return
        tenth = max(0, min(9, int(tenth)))
        target = duration * tenth / 10.0
        at_end = self.queue_finished or snap.eof
        if at_end:
            self._resume_from(target)
            return
        self.player.seek(target)
        self._emit()

    def volume_up(self, step: int = 5) -> None:
        self.player.set_volume(self.player.volume + step)
        self.config.update(volume=self.player.volume)
        self.status_message = f"Volume {self.player.volume}%"
        self._emit()

    def volume_down(self, step: int = 5) -> None:
        self.player.set_volume(self.player.volume - step)
        self.config.update(volume=self.player.volume)
        self.status_message = f"Volume {self.player.volume}%"
        self._emit()

    def shuffle_queue(self) -> None:
        if self.queue.shuffle_remaining():
            self.status_message = "Shuffled queue"
        else:
            self.status_message = "Nothing to shuffle"
        self._emit()

    def cycle_repeat(self) -> None:
        mode = self.queue.cycle_repeat()
        self.config.update(repeat=mode)
        self.status_message = f"Repeat: {mode.value}"
        self._emit()

    def queue_play_next(self, tracks: Track | list[Track]) -> None:
        items = [tracks] if isinstance(tracks, Track) else list(tracks)
        if not items:
            return
        start = self.queue.current is None
        self.queue.insert_next(items)
        if start:
            self._start_current()
            return
        if len(items) == 1:
            self.status_message = f"Play next: {items[0].title}"
        else:
            self.status_message = f"Play next: {len(items)} tracks"
        self._emit()

    def queue_append(self, tracks: Track | list[Track]) -> None:
        items = [tracks] if isinstance(tracks, Track) else list(tracks)
        if not items:
            return
        start = self.queue.current is None
        self.queue.append(items)
        if start:
            self._start_current()
            return
        if len(items) == 1:
            self.status_message = f"Queued: {items[0].title}"
        else:
            self.status_message = f"Queued: {len(items)} tracks"
        self._emit()
        
    def replace_register(self, tracks: Track | list[Track]) -> None:
        items = [tracks] if isinstance(tracks, Track) else list(tracks)
        self.register = items

    def play_random(self) -> None:
        try:
            track = pick_random_song(self.music)
        except Exception as exc:  # noqa: BLE001
            self.status_message = f"Search failed: {exc}"
            self._emit()
            return
        if track is None:
            self.status_message = "No random tracks found"
            self._emit()
            return
        self.play_track(track)

    def set_auth_headers(self, path: str | None) -> tuple[bool, str]:
        # load auth from path, or disconnect when empty/missing/invalid
        if path is None or str(path).strip() == "":
            self.config.update(auth_headers_path=None)
            self.music.reload_auth(None)
            self._refresh_playback_cookies()
            self.status_message = "Auth cleared (anonymous)"
            self._emit()
            return False, "Anonymous — auth cleared"

        resolved = Path(str(path).strip()).expanduser()
        self.config.update(auth_headers_path=str(resolved))

        if not resolved.exists():
            self.music.reload_auth(None)
            self._refresh_playback_cookies()
            msg = f"File not found — disconnected ({display_user_path(resolved)})"
            self.status_message = msg
            self._emit()
            return False, msg

        self.music.reload_auth(resolved)
        ok, detail = self.music.verify_auth()
        if not ok:
            self.music.reload_auth(None)
            detail = f"Disconnected — {detail}"
        self._refresh_playback_cookies()
        self.status_message = f"Auth: {detail}"
        self._emit()
        return ok, detail

    def set_discord_enabled(self, enabled: bool) -> None:
        self.config.update(discord_rpc=enabled)
        self.discord.enabled = enabled
        if enabled:
            self.discord.connect()
            track = self.current_track
            snap = self.snapshot
            self.discord.update(track, snap)
        else:
            self.discord.close()
        self.status_message = f"Discord RPC {'on' if enabled else 'off'}"
        self._emit()

    def shutdown(self) -> None:
        self.library_jobs.shutdown()
        self.downloads.shutdown()
        self.discord.close(join=True)
        self.player.shutdown()
        self.config.update(
            volume=self.player.volume,
            shuffle=False,
            repeat=self.queue.repeat,
            autoplay=self.queue.autoplay,
        )
        self.queue.save()
