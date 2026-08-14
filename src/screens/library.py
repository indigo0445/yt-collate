"""My Library — playlists, Saved Songs, Liked Songs, Episodes for Later"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, Label

from keyhints import LIBRARY
from models.track import PlaylistSummary, Track
from screens.base import ContentView
from services.music import (
    LIKED_PLAYLIST_ID,
    SAVED_SONGS_PLAYLIST_ID,
    LibraryTarget,
    PlaylistWriteResult,
    is_episodes_for_later,
    is_user_playlist,
    library_target_for,
)
from utils import clip_list_label
from widgets import NavListView, PanelHeader, TrackList

SAVED_SONGS_ICON = "🎵"


def library_num_prefix(num: int, *, marked: bool) -> str:
    return f"{num}* " if marked else f"{num}. "


def _folder_icon(playlist_id: str) -> str:
    if playlist_id == LIKED_PLAYLIST_ID:
        return "❤️"
    if playlist_id == SAVED_SONGS_PLAYLIST_ID:
        return SAVED_SONGS_ICON
    return "📁"


def _same_library_row(item: Track, track: Track) -> bool:
    if track.set_video_id and item.set_video_id:
        return item.set_video_id == track.set_video_id
    return bool(track.video_id) and item.video_id == track.video_id


@dataclass
class LibRow:
    kind: Literal["section", "playlist", "track"]
    label: str
    playlist: PlaylistSummary | None = None
    track: Track | None = None


class LibraryScreen(ContentView):
    # account library: playlists and songs. Esc/q undrills playlist via app

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._rows: list[LibRow] = []
        self._drilled = False
        self._loaded = False
        self._opening: str | None = None
        self._index_cursor = 0
        self._open_playlist: PlaylistSummary | None = None
        self._composing = False
        self._pending_focus_id: str | None = None
        self._pending_focus_title: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(classes="content-panel"):
            yield PanelHeader("📚 My Library", id="lib-title")
            yield NavListView(id="lib-list") # top-level playlists
            with Horizontal(id="lib-compose"): # new playlist row; initially hidden
                yield Label("", id="lib-compose-prefix", classes="muted")
                yield Input(id="lib-compose-name", classes="lib-compose-input")
            yield Vertical(id="lib-compose-fill")
            yield TrackList(id="lib-tracks") # track listing of playlist; initially hidden
            yield Label(LIBRARY, id="lib-hint", classes="muted")
            yield Label("Loading…", id="lib-status", classes="muted") # is this visible?

    async def on_mount(self) -> None:
        self.query_one("#lib-tracks", TrackList).display = False
        self._set_compose_visible(False)
        if self._loaded:
            return
        self._start_reload()

    def on_unmount(self) -> None:
        self.workers.cancel_all()

    def _start_reload(self) -> None:
        state = self.app.state  # type: ignore[attr-defined]
        if not state.music.authenticated:
            self._show_anon()
            return
        self.reload()

    def handle_back(self) -> bool:
        # cancel compose or undrill playlist. Returns True if handled
        if self.cancel_compose():
            return True
        if self._drilled:
            self._show_index()
            self.query_one("#lib-list", NavListView).focus()
            return True
        return False

    @work(thread=True)
    def reload(self) -> None:
        state = self.app.state  # type: ignore[attr-defined]
        if not state.music.authenticated:
            self.app.call_from_thread(self._show_anon)
            return
        try:
            playlists = state.music.get_library_playlists(
                limit=100,
                show_episodes_for_later=True,
            )
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            self.app.call_from_thread(lambda: self._show_error(msg))
            return
        self.app.call_from_thread(lambda: self._build_index(playlists))

    def _show_anon(self) -> None:
        self._drilled = False
        self._loaded = True
        self._rows = [
            LibRow(
                kind="section",
                label="Not authenticated — Settings: set headers path and press Enter",
            )
        ]
        self._rebuild_list()
        self.query_one("#lib-status", Label).update(
            "Anonymous — connect in Settings to see playlists and library folders"
        )
        self._sidebar_fetch_done()

    def _show_error(self, message: str) -> None:
        self._loaded = True
        self.query_one("#lib-status", Label).update(f"Error: {message}")
        self._sidebar_fetch_done()

    def _build_index(
        self, playlists: list[PlaylistSummary], *, focus_playlist_id: str | None = None
    ) -> None:
        self._drilled = False
        self._loaded = True
        if self._composing:
            self._composing = False
            self._set_compose_visible(False)
        cfg = self.app.state.config.config  # type: ignore[attr-defined]
        episodes = [p for p in playlists if is_episodes_for_later(p.title)]
        playlists = [p for p in playlists if not is_episodes_for_later(p.title)]
        if not cfg.show_episodes_for_later:
            episodes = []
        focus_id = focus_playlist_id or self._pending_focus_id
        focus_title = self._pending_focus_title
        self._pending_focus_id = None
        self._pending_focus_title = None
        if focus_id and all(p.playlist_id != focus_id for p in playlists):
            playlists = [
                PlaylistSummary(
                    playlist_id=focus_id,
                    title=focus_title or "Playlist",
                    track_count=0,
                ),
                *playlists,
            ]

        rows: list[LibRow] = []
        if not playlists:
            rows.append(LibRow(kind="section", label="(no playlists)"))
        for pl in playlists:
            rows.append(
                LibRow(
                    kind="playlist",
                    label=f"📁 {pl.title}",
                    playlist=pl,
                )
            )
        if cfg.show_saved_songs:
            saved = PlaylistSummary(
                playlist_id=SAVED_SONGS_PLAYLIST_ID, title="Saved Songs"
            )
            rows.append(
                LibRow(
                    kind="playlist",
                    label=f"{SAVED_SONGS_ICON} Saved Songs",
                    playlist=saved,
                )
            )
        if cfg.show_liked_songs:
            liked = PlaylistSummary(
                playlist_id=LIKED_PLAYLIST_ID, title="Liked Songs"
            )
            rows.append(
                LibRow(kind="playlist", label="❤️ Liked Songs", playlist=liked)
            )
        for pl in episodes:
            rows.append(
                LibRow(
                    kind="playlist",
                    label=f"📁 {pl.title}",
                    playlist=pl,
                )
            )
        self._rows = rows
        if focus_id:
            for i, row in enumerate(rows):
                if row.playlist and row.playlist.playlist_id == focus_id:
                    self._index_cursor = i
                    break
        self._show_index()
        if focus_id:
            self.query_one("#lib-list", NavListView).focus()
        extras: list[str] = []
        if cfg.show_saved_songs:
            extras.append("Saved Songs")
        if cfg.show_liked_songs:
            extras.append("Liked Songs")
        if episodes:
            extras.append("Episodes for Later")
        extra = f" · {' · '.join(extras)}" if extras else ""
        if not playlists and not extras:
            self.query_one("#lib-status", Label).update(
                "0 playlists — warning: if you expect a library, re-copy browser headers"
            )
        else:
            self.query_one("#lib-status", Label).update(
                f"{len(playlists)} playlists{extra}"
            )
        self._sidebar_fetch_done()

    def _sidebar_fetch_done(self) -> None:
        self.app.clear_sidebar_fetching("library")  # type: ignore[attr-defined]

    def _show_index(self) -> None:
        self._drilled = False
        self._set_opening(None)
        self._open_playlist = None
        self.query_one("#lib-tracks", TrackList).display = False
        lv = self.query_one("#lib-list", NavListView)
        lv.display = True
        self.query_one("#lib-title", PanelHeader).set_title("📚 My Library")
        self._rebuild_list(self._index_cursor)

    def _line(self, i: int, row: LibRow) -> str:
        if row.kind == "section":
            return row.label
        num = sum(1 for r in self._rows[: i + 1] if r.kind != "section")
        marked_id = None
        mark = self.app.state.library_mark  # type: ignore[attr-defined]
        if mark is not None:
            marked_id = mark.playlist_id
        pid = row.playlist.playlist_id if row.playlist else None
        marked = bool(pid and pid == marked_id)
        prefix = library_num_prefix(num, marked=marked)
        lv = self.query_one("#lib-list", NavListView)
        return clip_list_label(
            lv, prefix, row.label, suffix=" — marked" if marked else ""
        )

    def mark_focused(self) -> None:
        # toggle mark on a playlist / Saved Songs / Liked Songs row
        if self._drilled or self._opening:
            return
        lv = self.query_one("#lib-list", NavListView)
        idx = lv.index
        if idx is None or idx >= len(self._rows):
            return
        row = self._rows[idx]
        if row.kind != "playlist" or row.playlist is None:
            return
        target = library_target_for(row.playlist)
        if target is None:
            return
        state = self.app.state  # type: ignore[attr-defined]
        current = state.library_mark
        if current is not None and current.playlist_id == target.playlist_id:
            state.library_mark = None
            state.status_message = "Unmarked"
        else:
            state.library_mark = target
            state.status_message = f"Marked: {target.title}"
        self._rebuild_list(idx)
        self.app._on_state_change()  # type: ignore[attr-defined]

    def on_resize(self) -> None:
        if self._rows:
            lv = self.query_one("#lib-list", NavListView)
            self._rebuild_list(lv.index or 0)

    def _rebuild_list(self, index: int = 0) -> None:
        lv = self.query_one("#lib-list", NavListView)
        lv.set_rows(
            [self._row_activity(i, self._line(i, row)) for i, row in enumerate(self._rows)]
        )
        if self._rows:
            lv.index = min(max(0, index), len(self._rows) - 1)
            lv.scroll_to_highlight()

    def on_option_list_option_selected(self, event: NavListView.OptionSelected) -> None:
        if event.option_list.id != "lib-list" or self._drilled or self._opening:
            return
        lv = event.option_list
        idx = lv.index if isinstance(lv, NavListView) else event.option_index
        if idx is None or idx >= len(self._rows):
            return
        row = self._rows[idx]
        if row.kind == "section":
            return
        if row.kind == "track" and row.track:
            self.app.state.play_track(row.track)  # type: ignore[attr-defined]
        elif row.kind == "playlist" and row.playlist:
            self._index_cursor = idx
            self._set_opening(row.playlist.playlist_id, idx)
            self._apply_row_prompt(idx, "lib-list")
            self.open_playlist(row.playlist, idx)

    @work(thread=True)
    def open_playlist(self, pl: PlaylistSummary, row_index: int) -> None:
        try:
            tracks = self.app.state.music.get_collection_tracks(  # type: ignore[attr-defined]
                pl.playlist_id, limit=200
            )
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            self.app.call_from_thread(lambda m=msg, i=row_index: self._fetch_failed(i, m))
            return
        self.app.call_from_thread(lambda: self._show_playlist(pl, tracks))

    def _fetch_failed(self, row_index: int, message: str) -> None:
        self._set_opening(None)
        self._apply_row_prompt(row_index, "lib-list")
        self.query_one("#lib-status", Label).update(f"Error: {message}")

    def _show_playlist(self, pl: PlaylistSummary, tracks: list[Track]) -> None:
        self._set_opening(None)
        self._drilled = True
        self._open_playlist = pl
        self.query_one("#lib-list", NavListView).display = False
        tv = self.query_one("#lib-tracks", TrackList)
        tv.display = True
        tv.set_tracks(tracks)
        tv.focus()
        icon = _folder_icon(pl.playlist_id)
        self.query_one("#lib-title", PanelHeader).set_title(f"{icon} {pl.title}")
        self.query_one("#lib-status", Label).update(f"{len(tracks)} tracks · Esc/q back")

    def open_target(self) -> LibraryTarget | None:
        # collection currently drilled into, if markable (or a normal playlist)
        if not self._drilled or self._open_playlist is None:
            return None
        return library_target_for(self._open_playlist) or LibraryTarget(
            "playlist",
            self._open_playlist.playlist_id,
            self._open_playlist.title,
        )

    def drop_track(self, video_id: str) -> None:
        self.drop_matching(Track(video_id=video_id, title=""))

    def drop_matching(self, track: Track) -> int | None:
        # remove one matching row. Returns the index it left, or None
        if not self._drilled:
            return None
        tv = self.query_one("#lib-tracks", TrackList)
        if not tv.tracks:
            return None
        idx = tv.index if tv.index is not None else 0
        remove_at: int | None = None
        if 0 <= idx < len(tv.tracks) and _same_library_row(tv.tracks[idx], track):
            remove_at = idx
        else:
            for i, item in enumerate(tv.tracks):
                if _same_library_row(item, track):
                    remove_at = i
                    break
        if remove_at is None:
            return None
        remaining = [item for i, item in enumerate(tv.tracks) if i != remove_at]
        highlight = min(remove_at, len(remaining) - 1) if remaining else 0
        tv.set_tracks(remaining, highlight=highlight)
        return remove_at

    def restore_track(self, track: Track, index: int) -> None:
        # put a failed delete back where it was, without stealing focus
        if not self._drilled:
            return
        tv = self.query_one("#lib-tracks", TrackList)
        if any(_same_library_row(item, track) for item in tv.tracks):
            return
        at = min(max(0, index), len(tv.tracks))
        keep = tv.index if tv.index is not None else 0
        tracks = [*tv.tracks[:at], track, *tv.tracks[at:]]
        if keep >= at:
            keep += 1
        tv.set_tracks(tracks, highlight=min(keep, len(tracks) - 1))

    def focused_index_playlist(self) -> PlaylistSummary | None:
        # playlist row on the library index, if any
        if self._drilled or self._opening or self._composing:
            return None
        lv = self.query_one("#lib-list", NavListView)
        idx = lv.index
        if idx is None or idx >= len(self._rows):
            return None
        row = self._rows[idx]
        if row.kind != "playlist" or row.playlist is None:
            return None
        return row.playlist

    def drop_playlist(self, playlist_id: str) -> None:
        if self._drilled:
            return
        lv = self.query_one("#lib-list", NavListView)
        idx = lv.index if lv.index is not None else 0
        self._rows = [
            row
            for row in self._rows
            if not (row.playlist and row.playlist.playlist_id == playlist_id)
        ]
        has_user = any(
            row.playlist is not None and is_user_playlist(row.playlist)
            for row in self._rows
        )
        has_empty = any(row.kind == "section" and row.label == "(no playlists)" for row in self._rows)
        if not has_user and not has_empty:
            self._rows.insert(0, LibRow(kind="section", label="(no playlists)"))
        if not self._rows:
            return
        highlight = min(idx, len(self._rows) - 1)
        self._index_cursor = highlight
        self._rebuild_list(highlight)

    def start_compose(self) -> bool:
        # show the dimmed new-playlist row. Returns False if not on the index
        if self._drilled or self._opening or self._composing:
            return False
        state = self.app.state  # type: ignore[attr-defined]
        if not state.music.authenticated:
            self.app.notify(  # type: ignore[attr-defined]
                "Sign in (Settings) to create a playlist",
                title="Not signed in",
                severity="warning",
            )
            return False
        self._rows = [
            row for row in self._rows if not (row.kind == "section" and row.label == "(no playlists)")
        ]
        keep = self.query_one("#lib-list", NavListView).index or 0
        self._rebuild_list(keep)
        num = sum(1 for row in self._rows if row.kind != "section") + 1
        self.query_one("#lib-compose-prefix", Label).update(f"{num}. ")
        inp = self.query_one("#lib-compose-name", Input)
        inp.value = ""
        self._set_compose_visible(True)
        self._composing = True
        inp.focus()
        return True

    def cancel_compose(self) -> bool:
        if not self._composing:
            return False
        self._stop_compose(restore_focus=True)
        return True

    def _stop_compose(self, *, restore_focus: bool) -> None:
        self._composing = False
        self._set_compose_visible(False)
        self.query_one("#lib-compose-name", Input).value = ""
        has_user = any(
            row.playlist is not None and is_user_playlist(row.playlist)
            for row in self._rows
        )
        has_empty = any(row.kind == "section" and row.label == "(no playlists)" for row in self._rows)
        if not has_user and not has_empty:
            self._rows.insert(0, LibRow(kind="section", label="(no playlists)"))
            self._rebuild_list(0)
        if restore_focus:
            lv = self.query_one("#lib-list", NavListView)
            lv.focus()
            if self._rows:
                lv.index = min(self._index_cursor, len(self._rows) - 1)

    def _set_compose_visible(self, visible: bool) -> None:
        self.query_one("#lib-compose", Horizontal).display = visible
        self.query_one("#lib-compose-fill", Vertical).display = visible
        lv = self.query_one("#lib-list", NavListView)
        lv.set_class(visible, "composing")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "lib-compose-name" or not self._composing:
            return
        name = event.value.strip()
        if not name:
            return
        self.query_one("#lib-status", Label).update("Creating playlist…")
        self.create_playlist(name)

    def create_playlist(self, name: str) -> None:
        app = self.app

        def done(result: PlaylistWriteResult) -> None:
            app.call_from_thread(lambda: self._after_create(result, name))

        app.state.library_jobs.create_playlist(name, on_done=done)  # type: ignore[attr-defined]

    def _after_create(self, result: PlaylistWriteResult, name: str) -> None:
        if not result.ok:
            msg = result.message
            self.app.notify(msg, title="Could not create", severity="error")  # type: ignore[attr-defined]
            self.query_one("#lib-status", Label).update(msg)
            self.query_one("#lib-compose-name", Input).focus()
            return
        self.app.notify(result.message, severity="information")  # type: ignore[attr-defined]
        self._pending_focus_id = result.playlist_id
        self._pending_focus_title = name
        self._stop_compose(restore_focus=False)
        self.reload()

    def on_track_list_play_requested(self, event: TrackList.PlayRequested) -> None:
        tv = self.query_one("#lib-tracks", TrackList)
        self.app.state.play_tracks(tv.tracks, start_index=event.index)  # type: ignore[attr-defined]

    def queue_selection(self, *, play_next: bool) -> None:
        # i / a from the library index or an open playlist
        if self._opening:
            return
        if self._drilled:
            tv = self.query_one("#lib-tracks", TrackList)
            idx = tv.index
            if idx is None or idx < 0 or idx >= len(tv.tracks):
                return
            track = tv.tracks[idx]
            if play_next:
                self.app.state.queue_play_next(track)  # type: ignore[attr-defined]
            else:
                self.app.state.queue_append(track)  # type: ignore[attr-defined]
            return
        lv = self.query_one("#lib-list", NavListView)
        idx = lv.index
        if idx is None or idx >= len(self._rows):
            return
        row = self._rows[idx]
        if row.kind == "track" and row.track:
            if play_next:
                self.app.state.queue_play_next(row.track)  # type: ignore[attr-defined]
            else:
                self.app.state.queue_append(row.track)  # type: ignore[attr-defined]
            return
        if row.kind == "playlist" and row.playlist:
            self._set_opening(row.playlist.playlist_id, idx)
            self._apply_row_prompt(idx, "lib-list")
            self.queue_playlist(row.playlist, idx, play_next=play_next)

    def download_selection(self) -> None:
        if self._opening:
            return
        if self._drilled:
            tv = self.query_one("#lib-tracks", TrackList)
            idx = tv.index
            if idx is None or idx < 0 or idx >= len(tv.tracks):
                return
            self.app.download_tracks([tv.tracks[idx]])  # type: ignore[attr-defined]
            return
        lv = self.query_one("#lib-list", NavListView)
        idx = lv.index
        if idx is None or idx >= len(self._rows):
            return
        row = self._rows[idx]
        if row.kind == "track" and row.track:
            self.app.download_tracks([row.track])  # type: ignore[attr-defined]
            return
        if row.kind == "playlist" and row.playlist:
            self._set_opening(row.playlist.playlist_id, idx)
            self._apply_row_prompt(idx, "lib-list")
            self.download_playlist(row.playlist, idx)

    @work(thread=True)
    def download_playlist(self, pl: PlaylistSummary, row_index: int) -> None:
        try:
            tracks = self.app.state.music.get_collection_tracks(  # type: ignore[attr-defined]
                pl.playlist_id, limit=200
            )
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            self.app.call_from_thread(lambda m=msg, i=row_index: self._fetch_failed(i, m))
            return
        self.app.call_from_thread(
            lambda: self._download_playlist_ready(pl, tracks, row_index)
        )

    def _download_playlist_ready(
        self, pl: PlaylistSummary, tracks: list[Track], row_index: int
    ) -> None:
        self._set_opening(None)
        self._apply_row_prompt(row_index, "lib-list")
        if not tracks:
            self.query_one("#lib-status", Label).update(f"{pl.title}: no tracks")
            return
        self._set_download_progress(row_index, 0, len(tracks), "lib-list")
        self.app.download_tracks(  # type: ignore[attr-defined]
            tracks,
            collection=pl.title,
            on_progress=lambda c, t, i=row_index: self._set_download_progress(
                i, c, t, "lib-list"
            ),
            on_finished=lambda i=row_index: self._clear_download_progress(i, "lib-list"),
        )

    @work(thread=True)
    def queue_playlist(
        self, pl: PlaylistSummary, row_index: int, *, play_next: bool
    ) -> None:
        try:
            tracks = self.app.state.music.get_collection_tracks(  # type: ignore[attr-defined]
                pl.playlist_id, limit=200
            )
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            self.app.call_from_thread(lambda m=msg, i=row_index: self._fetch_failed(i, m))
            return
        self.app.call_from_thread(
            lambda: self._queued_playlist(pl, tracks, row_index, play_next=play_next)
        )

    def _queued_playlist(
        self,
        pl: PlaylistSummary,
        tracks: list[Track],
        row_index: int,
        *,
        play_next: bool,
    ) -> None:
        self._set_opening(None)
        self._apply_row_prompt(row_index, "lib-list")
        if not tracks:
            self.query_one("#lib-status", Label).update(f"{pl.title}: no tracks")
            return
        if play_next:
            self.app.state.queue_play_next(tracks)  # type: ignore[attr-defined]
        else:
            self.app.state.queue_append(tracks)  # type: ignore[attr-defined]
