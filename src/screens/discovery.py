"""Trending charts view."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label, LoadingIndicator

from yt_collate.keyhints import DISCOVERY
from yt_collate.screens.base import ContentView
from yt_collate.widgets import PanelHeader, TrackList


class DiscoveryScreen(ContentView):
    def compose(self) -> ComposeResult:
        with Vertical(classes="content-panel"):
            yield PanelHeader("🔥 Trending")
            yield LoadingIndicator(id="disc-loading")
            yield TrackList(id="disc-results")
            yield Label(DISCOVERY, id="disc-hint", classes="muted")
            yield Label("", id="disc-status", classes="muted")

    def on_mount(self) -> None:
        self.query_one("#disc-results", TrackList).focus()
        self.load_data()

    @work(exclusive=True, thread=True)
    def load_data(self) -> None:
        self.app.call_from_thread(
            lambda: setattr(self.query_one("#disc-loading", LoadingIndicator), "display", True)
        )
        music = self.app.state.music  # type: ignore[attr-defined]
        try:
            tracks = music.get_charts_tracks() or music.search_songs("trending music")
        except Exception as exc:  # noqa: BLE001
            self.app.call_from_thread(self._fail, str(exc))
            return
        self.app.call_from_thread(self._ok, tracks)

    def _fail(self, message: str) -> None:
        self.query_one("#disc-loading", LoadingIndicator).display = False
        self.query_one("#disc-status", Label).update(f"Error: {message}")
        self._sidebar_fetch_done()

    def _ok(self, tracks) -> None:
        self.query_one("#disc-loading", LoadingIndicator).display = False
        results = self.query_one("#disc-results", TrackList)
        results.set_tracks(tracks)
        self.query_one("#disc-status", Label).update(f"{len(tracks)} tracks")
        self._sidebar_fetch_done()

    def _sidebar_fetch_done(self) -> None:
        self.app.clear_sidebar_fetching("trending")  # type: ignore[attr-defined]

    def on_track_list_play_requested(self, event: TrackList.PlayRequested) -> None:
        tv = self.query_one("#disc-results", TrackList)
        self.app.state.play_tracks(tv.tracks, start_index=event.index)  # type: ignore[attr-defined]
