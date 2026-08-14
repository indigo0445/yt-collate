"""Shared shelf UI for Home and Explore (sectioned catalog rows)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from textual import work
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label

from keyhints import CATALOG
from models.track import Track
from screens.base import ContentView
from services.music import CatalogItem, CatalogShelf
from utils import clip_list_label
from widgets import NavListView, PanelHeader, TrackList


@dataclass
class CatalogRow:
    kind: Literal["section", "item"]
    label: str
    item: CatalogItem | None = None


class CatalogScreen(ContentView):
    """Sectioned catalog: songs play; albums/playlists/artists/moods drill in."""

    PREFIX = "catalog"
    TITLE = "Catalog"
    EMPTY = "No suggestions"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._rows: list[CatalogRow] = []
        self._index_rows: list[CatalogRow] = []
        self._playlist_rows: list[CatalogRow] = []
        self._drill: Literal["index", "playlists", "tracks"] = "index"
        self._loaded = False
        self._opening: str | None = None
        self._collection_title = self.TITLE
        self._index_cursor = 0
        self._playlist_cursor = 0

    @property
    def _title_id(self) -> str:
        return f"{self.PREFIX}-title"

    @property
    def _list_id(self) -> str:
        return f"{self.PREFIX}-list"

    @property
    def _tracks_id(self) -> str:
        return f"{self.PREFIX}-tracks"

    @property
    def _status_id(self) -> str:
        return f"{self.PREFIX}-status"

    def fetch_shelves(self) -> list[CatalogShelf]:
        raise NotImplementedError

    def compose(self) -> ComposeResult:
        with Vertical(classes="content-panel"):
            yield PanelHeader(self.TITLE, id=self._title_id)
            yield NavListView(id=self._list_id)
            yield TrackList(id=self._tracks_id)
            yield Label(CATALOG, classes="muted")
            yield Label("Loading…", id=self._status_id, classes="muted")

    async def on_mount(self) -> None:
        self.query_one(f"#{self._tracks_id}", TrackList).display = False
        if self._loaded:
            return
        self._sidebar_fetch_start()
        self.reload()

    def on_unmount(self) -> None:
        self.workers.cancel_all()

    def handle_back(self) -> bool:
        if self._drill == "tracks":
            if self._playlist_rows:
                self._show_playlist_index(focus=True)
            else:
                self._show_index(focus=True)
            return True
        if self._drill == "playlists":
            self._show_index(focus=True)
            return True
        return False

    @work(thread=True)
    def reload(self) -> None:
        try:
            shelves = self.fetch_shelves()
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            self.app.call_from_thread(lambda: self._show_error(msg))
            return
        self.app.call_from_thread(lambda: self._build_index(shelves))

    def _show_error(self, message: str) -> None:
        self._loaded = True
        self.query_one(f"#{self._status_id}", Label).update(f"Error: {message}")
        self._sidebar_fetch_done()

    def _rows_from_shelves(self, shelves: list[CatalogShelf]) -> list[CatalogRow]:
        rows: list[CatalogRow] = []
        for shelf in shelves:
            rows.append(CatalogRow(kind="section", label=f"— {shelf.title} —"))
            if not shelf.items:
                rows.append(CatalogRow(kind="section", label="  (empty)"))
            for item in shelf.items:
                rows.append(CatalogRow(kind="item", label=item.label, item=item))
        if not rows:
            rows.append(CatalogRow(kind="section", label=self.EMPTY))
        return rows

    def _build_index(self, shelves: list[CatalogShelf]) -> None:
        self._loaded = True
        self._index_rows = self._rows_from_shelves(shelves)
        n_items = sum(1 for r in self._index_rows if r.kind == "item")
        self._show_index()
        self.query_one(f"#{self._status_id}", Label).update(
            f"{len(shelves)} rows · {n_items} items"
        )
        self._sidebar_fetch_done()

    def _sidebar_fetch_start(self) -> None:
        self.app.set_sidebar_fetching(self.PREFIX)  # type: ignore[attr-defined]

    def _sidebar_fetch_done(self) -> None:
        self.app.clear_sidebar_fetching(self.PREFIX)  # type: ignore[attr-defined]

    def _show_index(self, *, focus: bool = False) -> None:
        self._drill = "index"
        self._set_opening(None)
        self._playlist_rows = []
        self._rows = self._index_rows
        self.query_one(f"#{self._tracks_id}", TrackList).display = False
        lv = self.query_one(f"#{self._list_id}", NavListView)
        lv.display = True
        self.query_one(f"#{self._title_id}", PanelHeader).set_title(self.TITLE)
        self._rebuild_list(self._index_cursor)
        if focus:
            lv.focus()

    def _show_playlist_index(self, *, reset_cursor: bool = False, focus: bool = True) -> None:
        self._drill = "playlists"
        self._set_opening(None)
        self._rows = self._playlist_rows
        self.query_one(f"#{self._tracks_id}", TrackList).display = False
        lv = self.query_one(f"#{self._list_id}", NavListView)
        lv.display = True
        self.query_one(f"#{self._title_id}", PanelHeader).set_title(self._collection_title)
        if reset_cursor:
            self._playlist_cursor = 0
        self._rebuild_list(self._playlist_cursor)
        if focus:
            lv.focus()
        n = sum(1 for r in self._rows if r.kind == "item")
        self.query_one(f"#{self._status_id}", Label).update(f"{n} playlists · Esc/q back")

    def _line(self, i: int, row: CatalogRow) -> str:
        if row.kind == "section":
            return row.label
        num = sum(1 for r in self._rows[: i + 1] if r.kind != "section")
        prefix = f"{num}. "
        lv = self.query_one(f"#{self._list_id}", NavListView)
        return clip_list_label(lv, prefix, row.label)

    def on_resize(self) -> None:
        if self._rows:
            lv = self.query_one(f"#{self._list_id}", NavListView)
            self._rebuild_list(lv.index or 0)

    def _rebuild_list(self, index: int = 0) -> None:
        lv = self.query_one(f"#{self._list_id}", NavListView)
        lv.set_rows(
            [self._row_activity(i, self._line(i, row)) for i, row in enumerate(self._rows)]
        )
        if self._rows:
            lv.index = min(max(0, index), len(self._rows) - 1)
            lv.scroll_to_highlight()

    def on_option_list_option_selected(self, event: NavListView.OptionSelected) -> None:
        if event.option_list.id != self._list_id or self._drill == "tracks" or self._opening:
            return
        lv = event.option_list
        idx = lv.index if isinstance(lv, NavListView) else event.option_index
        if idx is None or idx >= len(self._rows):
            return
        row = self._rows[idx]
        if row.kind != "item" or row.item is None:
            return
        item = row.item
        if self._drill == "index":
            self._index_cursor = idx
        elif self._drill == "playlists":
            self._playlist_cursor = idx
        if item.kind == "song" and item.track:
            self.app.state.play_track(item.track)  # type: ignore[attr-defined]
            return
        key = item.open_key
        if not key:
            return
        self._set_opening(key, idx)
        self._apply_row_prompt(idx, self._list_id)
        self.open_item(item, idx)

    @work(thread=True)
    def open_item(self, item: CatalogItem, row_index: int) -> None:
        try:
            if item.kind == "mood" and item.params:
                playlists = self.app.state.music.get_mood_playlists(item.params)  # type: ignore[attr-defined]
                self.app.call_from_thread(
                    lambda: self._show_mood_playlists(item, playlists)
                )
                return
            tracks = self._fetch_item_tracks(item)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            self.app.call_from_thread(lambda m=msg, i=row_index: self._fetch_failed(i, m))
            return
        self.app.call_from_thread(lambda: self._show_tracks(item, tracks))

    def _fetch_item_tracks(self, item: CatalogItem) -> list[Track]:
        music = self.app.state.music  # type: ignore[attr-defined]
        if item.kind == "album" and item.browse_id:
            return music.get_album_tracks(item.browse_id)
        if item.kind == "playlist" and item.playlist_id:
            return music.get_playlist_tracks(item.playlist_id, limit=200)
        if item.kind == "artist" and item.browse_id:
            return music.get_artist_tracks(item.browse_id, limit=50)
        return []

    def _fetch_failed(self, row_index: int, message: str) -> None:
        self._set_opening(None)
        self._apply_row_prompt(row_index, self._list_id)
        self.query_one(f"#{self._status_id}", Label).update(f"Error: {message}")

    def _show_mood_playlists(self, item: CatalogItem, playlists: list[CatalogItem]) -> None:
        self._set_opening(None)
        icon = "🎭"
        self._collection_title = f"{icon} {item.title}".strip()
        rows = [
            CatalogRow(kind="item", label=pl.label, item=pl) for pl in playlists
        ]
        if not rows:
            rows = [CatalogRow(kind="section", label="  (no playlists)")]
        self._playlist_rows = rows
        self._show_playlist_index(reset_cursor=True)

    def _show_tracks(self, item: CatalogItem, tracks: list[Track]) -> None:
        self._set_opening(None)
        self._drill = "tracks"
        self.query_one(f"#{self._list_id}", NavListView).display = False
        tv = self.query_one(f"#{self._tracks_id}", TrackList)
        tv.display = True
        tv.set_tracks(tracks)
        tv.focus()
        icon = {"album": "💿", "playlist": "📁", "artist": "🎤", "mood": "🎭"}.get(
            item.kind, ""
        )
        title = f"{icon} {item.title}".strip()
        self.query_one(f"#{self._title_id}", PanelHeader).set_title(title)
        self.query_one(f"#{self._status_id}", Label).update(
            f"{len(tracks)} tracks · Esc/q back"
        )

    def on_track_list_play_requested(self, event: TrackList.PlayRequested) -> None:
        tv = self.query_one(f"#{self._tracks_id}", TrackList)
        self.app.state.play_tracks(tv.tracks, start_index=event.index)  # type: ignore[attr-defined]

    def focused_song(self) -> Track | None:
        if self._drill == "tracks":
            return None
        lv = self.query_one(f"#{self._list_id}", NavListView)
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
        if self._drill == "tracks":
            tv = self.query_one(f"#{self._tracks_id}", TrackList)
            idx = tv.index
            if idx is None or idx < 0 or idx >= len(tv.tracks):
                return
            track = tv.tracks[idx]
            if play_next:
                self.app.state.queue_play_next(track)  # type: ignore[attr-defined]
            else:
                self.app.state.queue_append(track)  # type: ignore[attr-defined]
            return
        lv = self.query_one(f"#{self._list_id}", NavListView)
        idx = lv.index
        if idx is None or idx >= len(self._rows):
            return
        row = self._rows[idx]
        if row.kind != "item" or row.item is None:
            return
        item = row.item
        if self._drill == "index":
            self._index_cursor = idx
        elif self._drill == "playlists":
            self._playlist_cursor = idx
        if item.kind == "song" and item.track:
            if play_next:
                self.app.state.queue_play_next(item.track)  # type: ignore[attr-defined]
            else:
                self.app.state.queue_append(item.track)  # type: ignore[attr-defined]
            return
        if item.kind == "mood":
            self.open_item(item, idx)
            return
        key = item.open_key
        if not key:
            return
        self._set_opening(key, idx)
        self._apply_row_prompt(idx, self._list_id)
        self.queue_item(item, idx, play_next=play_next)

    def download_selection(self) -> None:
        if self._opening:
            return
        if self._drill == "tracks":
            tv = self.query_one(f"#{self._tracks_id}", TrackList)
            idx = tv.index
            if idx is None or idx < 0 or idx >= len(tv.tracks):
                return
            self.app.download_tracks([tv.tracks[idx]])  # type: ignore[attr-defined]
            return
        lv = self.query_one(f"#{self._list_id}", NavListView)
        idx = lv.index
        if idx is None or idx >= len(self._rows):
            return
        row = self._rows[idx]
        if row.kind != "item" or row.item is None:
            return
        item = row.item
        if self._drill == "index":
            self._index_cursor = idx
        elif self._drill == "playlists":
            self._playlist_cursor = idx
        if item.kind == "song" and item.track:
            self.app.download_tracks([item.track])  # type: ignore[attr-defined]
            return
        if item.kind == "mood":
            self.app.notify(  # type: ignore[attr-defined]
                "Open a playlist in this mood to download it",
                title="Download",
                severity="warning",
            )
            return
        key = item.open_key
        if not key:
            return
        self._set_opening(key, idx)
        self._apply_row_prompt(idx, self._list_id)
        self.download_item(item, idx)

    @work(thread=True)
    def download_item(self, item: CatalogItem, row_index: int) -> None:
        try:
            tracks = self._fetch_item_tracks(item)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            self.app.call_from_thread(lambda m=msg, i=row_index: self._fetch_failed(i, m))
            return
        self.app.call_from_thread(
            lambda: self._download_item_ready(item, tracks, row_index)
        )

    def _download_item_ready(
        self, item: CatalogItem, tracks: list[Track], row_index: int
    ) -> None:
        self._set_opening(None)
        self._apply_row_prompt(row_index, self._list_id)
        if not tracks:
            self.query_one(f"#{self._status_id}", Label).update(f"{item.title}: no tracks")
            return
        list_id = self._list_id
        self._set_download_progress(row_index, 0, len(tracks), list_id)
        self.app.download_tracks(  # type: ignore[attr-defined]
            tracks,
            collection=item.title,
            on_progress=lambda c, t, i=row_index: self._set_download_progress(
                i, c, t, list_id
            ),
            on_finished=lambda i=row_index: self._clear_download_progress(i, list_id),
        )

    @work(thread=True)
    def queue_item(self, item: CatalogItem, row_index: int, *, play_next: bool) -> None:
        try:
            tracks = self._fetch_item_tracks(item)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            self.app.call_from_thread(lambda m=msg, i=row_index: self._fetch_failed(i, m))
            return
        self.app.call_from_thread(
            lambda: self._queued_item(item, tracks, row_index, play_next=play_next)
        )

    def _queued_item(
        self,
        item: CatalogItem,
        tracks: list[Track],
        row_index: int,
        *,
        play_next: bool,
    ) -> None:
        self._set_opening(None)
        self._apply_row_prompt(row_index, self._list_id)
        if not tracks:
            self.query_one(f"#{self._status_id}", Label).update(f"{item.title}: no tracks")
            return
        if play_next:
            self.app.state.queue_play_next(tracks)  # type: ignore[attr-defined]
        else:
            self.app.state.queue_append(tracks)  # type: ignore[attr-defined]
