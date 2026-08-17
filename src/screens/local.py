"""Local — downloaded playlists from ~/Music/yt-collate/*.json"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label

from keyhints import LOCAL
from models.track import LocalPlaylist
from screens.base import ContentView
from screens.library import library_num_prefix
from services.local_library import load_local_playlists
from utils import clip_list_label
from widgets import NavListView, PanelHeader, TrackList


@dataclass
class LocalRow:
    kind: Literal["section", "playlist"]
    label: str
    playlist: LocalPlaylist | None = None


class LocalScreen(ContentView):
    # on-disk playlists. Esc/q undrills via app. No network.

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._rows: list[LocalRow] = []
        self._drilled = False
        self._index_cursor = 0
        self._open_playlist: LocalPlaylist | None = None

    def compose(self) -> ComposeResult:
        with Vertical(classes="content-panel"):
            yield PanelHeader("📂 Local", id="local-title")
            yield NavListView(id="local-list")
            yield TrackList(id="local-tracks")
            yield Label(LOCAL, id="local-hint", classes="muted")
            yield Label("", id="local-status", classes="muted")

    async def on_mount(self) -> None:
        self.query_one("#local-tracks", TrackList).display = False
        self.reload()

    def handle_back(self) -> bool:
        if self._drilled:
            self._show_index()
            self.query_one("#local-list", NavListView).focus()
            return True
        return False

    def reload(self) -> None:
        playlists = load_local_playlists()
        rows: list[LocalRow] = []
        if not playlists:
            rows.append(LocalRow(kind="section", label="(no playlists)"))
        for pl in playlists:
            emoji = pl.emoji.strip() or "📁"
            rows.append(
                LocalRow(
                    kind="playlist",
                    label=f"{emoji} {pl.title}",
                    playlist=pl,
                )
            )
        self._rows = rows
        self._show_index()
        if playlists:
            self.query_one("#local-status", Label).update(
                f"{len(playlists)} playlist" + ("" if len(playlists) == 1 else "s")
            )
        else:
            self.query_one("#local-status", Label).update(
                "Download a playlist to save it here"
            )

    def _show_index(self) -> None:
        self._drilled = False
        self._open_playlist = None
        self.query_one("#local-tracks", TrackList).display = False
        lv = self.query_one("#local-list", NavListView)
        lv.display = True
        self.query_one("#local-title", PanelHeader).set_title("📂 Local")
        self._rebuild_list(self._index_cursor)

    def _line(self, i: int, row: LocalRow) -> str:
        if row.kind == "section":
            return row.label
        num = sum(1 for r in self._rows[: i + 1] if r.kind != "section")
        prefix = library_num_prefix(num, marked=False)
        lv = self.query_one("#local-list", NavListView)
        return clip_list_label(lv, prefix, row.label)

    def on_resize(self) -> None:
        if self._rows:
            lv = self.query_one("#local-list", NavListView)
            self._rebuild_list(lv.index or 0)

    def _rebuild_list(self, index: int = 0) -> None:
        lv = self.query_one("#local-list", NavListView)
        lv.set_rows([self._line(i, row) for i, row in enumerate(self._rows)])
        if self._rows:
            lv.index = min(max(0, index), len(self._rows) - 1)
            lv.scroll_to_highlight()

    def on_option_list_option_selected(self, event: NavListView.OptionSelected) -> None:
        if event.option_list.id != "local-list" or self._drilled:
            return
        lv = event.option_list
        idx = lv.index if isinstance(lv, NavListView) else event.option_index
        if idx is None or idx >= len(self._rows):
            return
        row = self._rows[idx]
        if row.kind == "playlist" and row.playlist:
            self._index_cursor = idx
            self._show_playlist(row.playlist)

    def _show_playlist(self, pl: LocalPlaylist) -> None:
        self._drilled = True
        self._open_playlist = pl
        self.query_one("#local-list", NavListView).display = False
        tv = self.query_one("#local-tracks", TrackList)
        tv.display = True
        tv.set_tracks(pl.tracks)
        tv.focus()
        emoji = pl.emoji.strip() or "📁"
        self.query_one("#local-title", PanelHeader).set_title(f"{emoji} {pl.title}")
        self.query_one("#local-status", Label).update(
            f"{len(pl.tracks)} tracks · Esc/q back"
        )

    def on_track_list_play_requested(self, event: TrackList.PlayRequested) -> None:
        tv = self.query_one("#local-tracks", TrackList)
        self.app.state.play_tracks(tv.tracks, start_index=event.index)  # type: ignore[attr-defined]

    def queue_selection(self, *, play_next: bool) -> None:
        if self._drilled:
            tv = self.query_one("#local-tracks", TrackList)
            idx = tv.index
            if idx is None or idx < 0 or idx >= len(tv.tracks):
                return
            track = tv.tracks[idx]
            if play_next:
                self.app.state.queue_play_next(track)  # type: ignore[attr-defined]
            else:
                self.app.state.queue_append(track)  # type: ignore[attr-defined]
            return
        lv = self.query_one("#local-list", NavListView)
        idx = lv.index
        if idx is None or idx >= len(self._rows):
            return
        row = self._rows[idx]
        if row.kind != "playlist" or row.playlist is None:
            return
        tracks = row.playlist.tracks
        if not tracks:
            self.query_one("#local-status", Label).update(
                f"{row.playlist.title}: no tracks"
            )
            return
        if play_next:
            self.app.state.queue_play_next(tracks)  # type: ignore[attr-defined]
        else:
            self.app.state.queue_append(tracks)  # type: ignore[attr-defined]
