"""Search view — default catalog search (artists, songs, videos)."""

from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input, Label, LoadingIndicator

from yt_collate.keyhints import SEARCH
from yt_collate.models.music import Track
from yt_collate.screens.base import ContentView
from yt_collate.screens.catalog import CatalogRow
from yt_collate.services.music import CatalogItem
from yt_collate.utils import clip_list_label
from yt_collate.widgets import (
    LeaveInputDown,
    NavListView,
    PanelHeader,
    SearchQueryInput,
    TrackList,
)


class SearchScreen(ContentView):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._rows: list[CatalogRow] = []
        self._drilled = False
        self._opening: str | None = None
        self._result_cursor = 0
        self._committed_query: str | None = None

    def compose(self) -> ComposeResult:
        with Vertical(classes="content-panel"):
            yield PanelHeader("🔍 Search", id="search-title", with_query=True)
            yield LoadingIndicator(id="search-loading")
            yield NavListView(id="search-list", leave_up=True)
            yield TrackList(id="search-tracks")
            yield Label(SEARCH, classes="muted")
            yield Label("", id="search-status", classes="muted")

    def on_mount(self) -> None:
        self.query_one("#search-loading", LoadingIndicator).display = False
        if self._committed_query is None and not self._rows:
            self.query_one("#search-tracks", TrackList).display = False
            self._focus_query()
            return
        self._restore_session()

    def _restore_session(self) -> None:
        inp = self.query_one("#search-input", Input)
        if self._committed_query:
            inp.value = self._committed_query
            self._set_query_results_active(True)
        if self._drilled:
            self.query_one("#search-list", NavListView).display = False
            tv = self.query_one("#search-tracks", TrackList)
            tv.display = True
            tv.focus()
            return
        self.query_one("#search-tracks", TrackList).display = False
        self._show_result_index(focus=True)

    def query_escape_to_results(self) -> bool:
        """Esc/q from the query field returns to result #1 after a search."""
        return self._committed_query is not None

    def _set_query_results_active(self, active: bool) -> None:
        try:
            self.query_one("#search-input", SearchQueryInput).results_active = active
        except Exception:  # noqa: BLE001
            pass

    def handle_back(self) -> bool:
        focused = self.app.focused
        if (
            isinstance(focused, Input)
            and focused.id == "search-input"
            and self._committed_query is not None
        ):
            self._leave_query_to_results()
            return True
        if self._drilled:
            self._show_result_index(focus=True)
            return True
        return False

    def on_leave_input_down(self, event: LeaveInputDown) -> None:
        if not self._rows:
            return
        event.stop()
        self._leave_query_to_results()

    def _leave_query_to_results(self) -> None:
        query = self._committed_query or ""
        inp = self.query_one("#search-input", Input)
        inp.value = query
        self._show_result_index(focus=True, reset_cursor=True)

    def focus_query(self) -> None:
        if self._drilled:
            self._show_result_index(focus=False)
        self._focus_query()

    def _focus_query(self) -> None:
        inp = self.query_one("#search-input", Input)
        inp.focus()
        inp.select_all()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "search-input":
            return
        query = event.value.strip()
        if query:
            self.run_search(query)

    @work(exclusive=True, thread=True)
    def run_search(self, query: str) -> None:
        self.app.call_from_thread(self._set_loading, True)
        try:
            items = self.app.state.music.search_songs_and_artists(query)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001
            self.app.call_from_thread(self._show_error, str(exc))
            return
        self.app.call_from_thread(lambda: self._show_results(items, query))

    def _set_loading(self, loading: bool) -> None:
        self.query_one("#search-loading", LoadingIndicator).display = loading

    def _show_error(self, message: str) -> None:
        self._set_loading(False)
        self.query_one("#search-status", Label).update(f"Error: {message}")

    def _show_results(self, items: list[CatalogItem], query: str | None = None) -> None:
        self._set_loading(False)
        self._drilled = False
        self._set_opening(None)
        if query is not None:
            self._committed_query = query
            self._set_query_results_active(True)
        self._rows = [CatalogRow(kind="item", label=item.label, item=item) for item in items]
        self._result_cursor = 0
        self._show_result_index(focus=bool(items), reset_cursor=True)
        n_art = sum(1 for it in items if it.kind == "artist")
        n_song = sum(1 for it in items if it.kind == "song")
        extra = []
        if n_art:
            extra.append(f"{n_art} artist" + ("s" if n_art != 1 else ""))
        if n_song:
            extra.append(f"{n_song} song" + ("s" if n_song != 1 else ""))
        self.query_one("#search-status", Label).update(
            " · ".join(extra) if extra else "No results"
        )

    def _show_result_index(self, *, focus: bool = False, reset_cursor: bool = False) -> None:
        self._drilled = False
        self.query_one("#search-tracks", TrackList).display = False
        lv = self.query_one("#search-list", NavListView)
        lv.display = True
        self.query_one("#search-title", PanelHeader).set_title("🔍 Search")
        if reset_cursor:
            self._result_cursor = 0
        self._rebuild_list(self._result_cursor)
        if focus:
            lv.focus()

    def _line(self, i: int, row: CatalogRow) -> str:
        prefix = f"{i + 1}. "
        lv = self.query_one("#search-list", NavListView)
        return clip_list_label(lv, prefix, row.label)

    def on_resize(self) -> None:
        if self._rows and not self._drilled:
            lv = self.query_one("#search-list", NavListView)
            self._rebuild_list(lv.index or 0)

    def _rebuild_list(self, index: int = 0) -> None:
        lv = self.query_one("#search-list", NavListView)
        lv.set_rows(
            [self._row_activity(i, self._line(i, row)) for i, row in enumerate(self._rows)]
        )
        if self._rows:
            lv.index = min(max(0, index), len(self._rows) - 1)
            lv.scroll_to_highlight()

    def on_option_list_option_selected(self, event: NavListView.OptionSelected) -> None:
        if event.option_list.id != "search-list" or self._drilled or self._opening:
            return
        lv = event.option_list
        idx = lv.index if isinstance(lv, NavListView) else event.option_index
        if idx is None or idx >= len(self._rows):
            return
        row = self._rows[idx]
        if row.kind != "item" or row.item is None:
            return
        item = row.item
        self._result_cursor = idx
        if item.kind == "song" and item.track:
            self.app.state.play_track(item.track)  # type: ignore[attr-defined]
            return
        if item.kind != "artist" or not item.browse_id:
            return
        self._set_opening(item.browse_id, idx)
        self._apply_row_prompt(idx, "search-list")
        self.open_artist(item, idx)

    @work(thread=True)
    def open_artist(self, item: CatalogItem, row_index: int) -> None:
        try:
            tracks = self.app.state.music.get_artist_tracks(  # type: ignore[attr-defined]
                item.browse_id or "", limit=50
            )
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            self.app.call_from_thread(lambda: self._fetch_failed(row_index, msg))
            return
        self.app.call_from_thread(lambda: self._show_artist_tracks(item, tracks, row_index))

    def _fetch_failed(self, row_index: int, message: str) -> None:
        self._set_opening(None)
        self._apply_row_prompt(row_index, "search-list")
        self.query_one("#search-status", Label).update(f"Error: {message}")

    def _show_artist_tracks(
        self, item: CatalogItem, tracks: list[Track], row_index: int
    ) -> None:
        self._set_opening(None)
        self._apply_row_prompt(row_index, "search-list")
        if not tracks:
            self.query_one("#search-status", Label).update(f"{item.title}: no tracks")
            return
        self._drilled = True
        self.query_one("#search-list", NavListView).display = False
        tv = self.query_one("#search-tracks", TrackList)
        tv.display = True
        tv.set_tracks(tracks)
        tv.focus()
        self.query_one("#search-status", Label).update(
            f"🎤 {item.title} · {len(tracks)} tracks · Esc/q back"
        )

    def on_track_list_play_requested(self, event: TrackList.PlayRequested) -> None:
        if event.list_id != "search-tracks":
            return
        tv = self.query_one("#search-tracks", TrackList)
        self.app.state.play_tracks(tv.tracks, start_index=event.index)  # type: ignore[attr-defined]

    def focused_song(self) -> Track | None:
        if self._drilled:
            return None
        lv = self.query_one("#search-list", NavListView)
        idx = lv.index
        if idx is None or idx >= len(self._rows):
            return None
        row = self._rows[idx]
        if row.kind != "item" or row.item is None:
            return None
        item = row.item
        if item.kind == "song" and item.track:
            return item.track
        return None

    def queue_selection(self, *, play_next: bool) -> None:
        if self._opening:
            return
        if self._drilled:
            tv = self.query_one("#search-tracks", TrackList)
            idx = tv.index
            if idx is None or idx < 0 or idx >= len(tv.tracks):
                return
            track = tv.tracks[idx]
            if play_next:
                self.app.state.queue_play_next(track)  # type: ignore[attr-defined]
            else:
                self.app.state.queue_append(track)  # type: ignore[attr-defined]
            return
        lv = self.query_one("#search-list", NavListView)
        idx = lv.index
        if idx is None or idx >= len(self._rows):
            return
        row = self._rows[idx]
        if row.kind != "item" or row.item is None:
            return
        item = row.item
        self._result_cursor = idx
        if item.kind == "song" and item.track:
            if play_next:
                self.app.state.queue_play_next(item.track)  # type: ignore[attr-defined]
            else:
                self.app.state.queue_append(item.track)  # type: ignore[attr-defined]
            return
        if item.kind != "artist" or not item.browse_id:
            return
        self._set_opening(item.browse_id, idx)
        self._apply_row_prompt(idx, "search-list")
        self.queue_artist(item, idx, play_next=play_next)

    def download_selection(self) -> None:
        if self._opening:
            return
        if self._drilled:
            tv = self.query_one("#search-tracks", TrackList)
            idx = tv.index
            if idx is None or idx < 0 or idx >= len(tv.tracks):
                return
            self.app.download_tracks([tv.tracks[idx]])  # type: ignore[attr-defined]
            return
        lv = self.query_one("#search-list", NavListView)
        idx = lv.index
        if idx is None or idx >= len(self._rows):
            return
        row = self._rows[idx]
        if row.kind != "item" or row.item is None:
            return
        item = row.item
        self._result_cursor = idx
        if item.kind == "song" and item.track:
            self.app.download_tracks([item.track])  # type: ignore[attr-defined]
            return
        if item.kind != "artist" or not item.browse_id:
            return
        self._set_opening(item.browse_id, idx)
        self._apply_row_prompt(idx, "search-list")
        self.download_artist(item, idx)

    @work(thread=True)
    def download_artist(self, item: CatalogItem, row_index: int) -> None:
        try:
            tracks = self.app.state.music.get_artist_tracks(  # type: ignore[attr-defined]
                item.browse_id or "", limit=50
            )
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            self.app.call_from_thread(lambda: self._fetch_failed(row_index, msg))
            return
        self.app.call_from_thread(
            lambda: self._download_artist_ready(item, tracks, row_index)
        )

    def _download_artist_ready(
        self, item: CatalogItem, tracks: list[Track], row_index: int
    ) -> None:
        self._set_opening(None)
        self._apply_row_prompt(row_index, "search-list")
        if not tracks:
            self.query_one("#search-status", Label).update(f"{item.title}: no tracks")
            return
        self._set_download_progress(row_index, 0, len(tracks), "search-list")
        self.app.download_tracks(  # type: ignore[attr-defined]
            tracks,
            collection=item.title,
            on_progress=lambda c, t, i=row_index: self._set_download_progress(
                i, c, t, "search-list"
            ),
            on_finished=lambda i=row_index: self._clear_download_progress(
                i, "search-list"
            ),
        )

    @work(thread=True)
    def queue_artist(self, item: CatalogItem, row_index: int, *, play_next: bool) -> None:
        try:
            tracks = self.app.state.music.get_artist_tracks(  # type: ignore[attr-defined]
                item.browse_id or "", limit=50
            )
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            self.app.call_from_thread(lambda: self._fetch_failed(row_index, msg))
            return
        self.app.call_from_thread(
            lambda: self._queued_artist(item, tracks, row_index, play_next=play_next)
        )

    def _queued_artist(
        self,
        item: CatalogItem,
        tracks: list[Track],
        row_index: int,
        *,
        play_next: bool,
    ) -> None:
        self._set_opening(None)
        self._apply_row_prompt(row_index, "search-list")
        if not tracks:
            self.query_one("#search-status", Label).update(f"{item.title}: no tracks")
            return
        if play_next:
            self.app.state.queue_play_next(tracks)  # type: ignore[attr-defined]
        else:
            self.app.state.queue_append(tracks)  # type: ignore[attr-defined]
