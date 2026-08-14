"""Queue & history view."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical

from yt_collate.models.music import Track
from yt_collate.screens.base import ContentView
from yt_collate.widgets import PanelHeader, TrackList

_HISTORY_LIMIT = 50


class HistoryScreen(ContentView):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._last_current: Track | None = None

    def compose(self) -> ComposeResult:
        with Horizontal():
            with Vertical(classes="content-panel"):
                yield PanelHeader("📋 Queue", id="queue-title")
                yield TrackList(id="queue-list", mark_playing=True)
            with Vertical(classes="content-panel"):
                yield PanelHeader("🕒 Recently Played", id="history-title")
                yield TrackList(id="history-list")

    def on_mount(self) -> None:
        self.refresh_lists()
        self.query_one("#queue-list", TrackList).focus()
        state = self.app.state  # type: ignore[attr-defined]
        if not state.music.authenticated:
            self.query_one("#history-list", TrackList).set_tracks([])
            return
        self.load_history()

    def on_unmount(self) -> None:
        self.workers.cancel_all()

    def refresh_lists(self) -> None:
        """Queue always; recently played is optimistic while this page stays mounted."""
        state = self.app.state  # type: ignore[attr-defined]
        self.query_one("#queue-title", PanelHeader).set_title("📋 Queue")
        self.query_one("#queue-list", TrackList).set_tracks(state.queue.upcoming())
        self._sync_recently_played(state.queue.current)

    def _sync_recently_played(self, current: Track | None) -> None:
        state = self.app.state  # type: ignore[attr-defined]
        prev = self._last_current
        self._last_current = current
        if not state.music.authenticated or current is None:
            return
        if prev is None or current.same_listen(prev):
            return
        self._show_recent([current, *self.query_one("#history-list", TrackList).tracks])

    @work(thread=True)
    def load_history(self) -> None:
        try:
            tracks = self.app.state.music.get_history(limit=_HISTORY_LIMIT)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            tracks = []
        self.app.call_from_thread(lambda: self._set_history(tracks))

    def _set_history(self, tracks: list[Track]) -> None:
        if not self.is_attached:
            return
        self._show_recent(tracks)
        self.app.clear_sidebar_fetching("history")  # type: ignore[attr-defined]

    def _show_recent(self, tracks: list[Track]) -> None:
        current = self.app.state.queue.current  # type: ignore[attr-defined]
        shown: list[Track] = []
        for track in tracks:
            if shown and shown[-1].same_listen(track):
                continue
            shown.append(track)
        if current is not None:
            shown = [t for t in shown if not t.same_listen(current)]
            shown.insert(0, current)
        self.query_one("#history-list", TrackList).set_tracks(shown[:_HISTORY_LIMIT])

    def on_track_list_play_requested(self, event: TrackList.PlayRequested) -> None:
        state = self.app.state  # type: ignore[attr-defined]
        if event.list_id == "queue-list":
            state.play_upcoming(event.index)
        else:
            state.play_track(event.track)
        self.refresh_lists()
