"""app entry / top-level management / global keys handler"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.notifications import SeverityLevel
from textual.widget import Widget
from textual.widgets import Input, Label, OptionList, Static

from models.track import LocalPlaylist, PlaylistSummary, Track
from screens import (
    DiscoveryScreen,
    HelpScreen,
    HistoryScreen,
    SearchScreen,
    SettingsScreen,
)
from screens.catalog import CatalogScreen
from screens.explore import ExploreScreen
from screens.home import HomeScreen
from screens.library import LibraryScreen
from screens.local import LocalScreen
from services.download import DownloadBatchResult
from services.local_library import save_local_playlist
from services.music import (
    AddResult,
    LibraryTarget,
    PlaylistWriteResult,
    is_user_playlist,
    library_target_for
)
from state import RANDOM_QUERIES, AppState
from utils import display_duration, display_position
from widgets import (
    FilterLeaveDown,
    ListFilterDismissed,
    ListFilterRequested,
    NavListView,
    PanelEdge,
    PanelHeader,
    Sidebar,
    StatusBar,
    TrackList,
)

# horizontal strips only: sidebar | content [| extra]
# history is the one 3-pane page: sidebar | queue | recently played


@dataclass
class _PendingDelete:
    track: Track | None = None
    target: LibraryTarget | None = None
    playlist: PlaylistSummary | None = None


class YtCollateApp(App[None]):
    # shell stays mounted; pages swap in #content. Start page: Home

    TITLE = "yt-collate"
    CSS_PATH = Path(__file__).parent / "themes" / "app.tcss"
    ENABLE_COMMAND_PALETTE = False

    BINDINGS = [
        Binding("escape", "go_back", "Back", show=False),
        Binding("q", "go_back", "Back", show=False),
        Binding("space", "toggle_pause", "Play/Pause", show=True),
        Binding("n", "next_track", "Next", show=False),
        Binding("b", "prev_track", "Prev", show=False),
        Binding("0", "seek_tenth(0)", "Jump 0%", show=False),
        Binding("1", "seek_tenth(1)", "Jump 10%", show=False),
        Binding("2", "seek_tenth(2)", "Jump 20%", show=False),
        Binding("3", "seek_tenth(3)", "Jump 30%", show=False),
        Binding("4", "seek_tenth(4)", "Jump 40%", show=False),
        Binding("5", "seek_tenth(5)", "Jump 50%", show=False),
        Binding("6", "seek_tenth(6)", "Jump 60%", show=False),
        Binding("7", "seek_tenth(7)", "Jump 70%", show=False),
        Binding("8", "seek_tenth(8)", "Jump 80%", show=False),
        Binding("9", "seek_tenth(9)", "Jump 90%", show=False),
        Binding("s", "shuffle_queue", "Shuffle", show=False),
        Binding("i", "queue_insert", "Play next", show=False),
        Binding("a", "queue_append", "Queue", show=False),
        Binding("d", "download", "Download", show=False),
        Binding("r", "cycle_repeat", "Repeat", show=False),
        Binding("comma", "open_settings", "Settings", show=False),
        Binding("question_mark", "open_help", "Help", show=False),
        Binding("H", "open_history", "History", show=False),
        Binding("backslash", "focus_search_query", "Search", show=False, priority=True),
        Binding("m", "mark_library", "Mark", show=False),
        Binding("plus", "add_to_marked", "Add to marked", show=False),
        Binding("o", "compose_playlist", "New playlist", show=False),
        Binding("y", "yank_track", "Yank", show=False),
        Binding("x", "delete_in_library", "Delete", show=False),
        Binding("p", "paste_in_library", "Paste", show=False),
        Binding("enter", "confirm_or_select", "Enter", show=False, priority=True),
        Binding("minus", "vol_down", "Vol-", show=False),
        Binding("=", "vol_up", "Vol+", show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.state = AppState()
        self.view_name = "home"
        self._filter_list: NavListView | None = None
        self._pending_delete: _PendingDelete | None = None
        self._search_screen: SearchScreen | None = None

    def notify(
        self,
        message: str,
        *,
        title: str = "",
        severity: SeverityLevel = "information",
        timeout: float | None = None,
        markup: bool = False,
    ) -> None:
        # toasts are plain text — API payloads and song titles break markup
        super().notify(
            message, title=title, severity=severity, timeout=timeout, markup=markup
        )

    def compose(self) -> ComposeResult:
        yield Static("🎵 ▶ yt-collate ▶ 🎵", id="header")
        with Horizontal(id="body"):
            yield Sidebar(id="sidebar")
            with Vertical(id="content"):
                yield HomeScreen(id="home")
        yield StatusBar(id="status-bar")

    def on_mount(self) -> None:
        self.state.subscribe(self._on_state_change)
        self.set_interval(0.5, self._on_state_change)
        self._on_state_change()
        # always land focus somewhere so hjkl/Enter work immediately
        try:
            self.query_one("#sidebar-list", NavListView).focus()
        except Exception:  # noqa: BLE001
            pass
        if self.state.config.config.discord_rpc:
            self.state.discord.connect()
        self.state.play_restored_current()

    def on_unmount(self) -> None:
        self.state.shutdown()

    async def show_view(self, widget: Widget, name: str) -> None:
        content = self.query_one("#content", Vertical)
        await content.remove_children()
        await content.mount(widget)
        self.view_name = name

    async def show_home(self) -> None:
        await self.show_view(HomeScreen(id="home"), "home")
        self._focus_catalog_content("home")

    async def show_explore(self) -> None:
        await self.show_view(ExploreScreen(id="explore"), "explore")
        self._focus_catalog_content("explore")

    def _focus_catalog_content(self, prefix: str) -> None:
        try:
            self.query_one(f"#{prefix}-list", NavListView).focus()
        except Exception:  # noqa: BLE001
            try:
                self.query_one("#sidebar-list", NavListView).focus()
            except Exception:  # noqa: BLE001
                pass

    async def show_search(self) -> None:
        if self._search_screen is None:
            self._search_screen = SearchScreen(id="search")
        await self.show_view(self._search_screen, "search")

    async def show_library(self) -> None:
        await self.show_view(LibraryScreen(id="library"), "library")
        self._focus_library_content()

    def _focus_library_content(self) -> None:
        try:
            self.query_one("#lib-list", NavListView).focus()
        except Exception:  # noqa: BLE001
            try:
                self.query_one("#sidebar-list", NavListView).focus()
            except Exception:  # noqa: BLE001
                pass

    async def show_local(self) -> None:
        await self.show_view(LocalScreen(id="local"), "local")
        self._focus_local_content()

    def _focus_local_content(self) -> None:
        try:
            self.query_one("#local-list", NavListView).focus()
        except Exception:  # noqa: BLE001
            try:
                self.query_one("#sidebar-list", NavListView).focus()
            except Exception:  # noqa: BLE001
                pass

    async def action_go_back(self) -> None:
        if self._cancel_pending_delete():
            return
        if self._close_list_filter():
            return
        if self.view_name in {"home", "explore"}:
            try:
                if self.query_one(CatalogScreen).handle_back():
                    return
            except Exception:  # noqa: BLE001
                pass
        elif self.view_name == "library":
            try:
                if self.query_one(LibraryScreen).handle_back():
                    return
            except Exception:  # noqa: BLE001
                pass
        elif self.view_name == "local":
            try:
                if self.query_one(LocalScreen).handle_back():
                    return
            except Exception:  # noqa: BLE001
                pass
        elif self.view_name == "settings":
            try:
                if self.query_one(SettingsScreen).handle_back():
                    return
            except Exception:  # noqa: BLE001
                pass
        elif self.view_name == "search":
            try:
                if self.query_one(SearchScreen).handle_back():
                    return
            except Exception:  # noqa: BLE001
                pass
        self._focus_main_selection()

    def _focus_main_selection(self) -> None:
        # focus the sidebar row for the current screen. No-op if already there
        try:
            lv = self.query_one("#sidebar-list", NavListView)
        except Exception:  # noqa: BLE001
            return
        if self.focused is lv:
            return
        nav_id = f"nav-{self.view_name}"
        for i, opt in enumerate(lv.options):
            if getattr(opt, "id", None) == nav_id:
                lv.highlighted = i
                break
        lv.focus()

    def on_list_filter_requested(self, event: ListFilterRequested) -> None:
        event.stop()
        try:
            lv = self.query_one(f"#{event.list_id}", NavListView)
        except Exception:  # noqa: BLE001
            return
        header = self._header_for_list(lv)
        if header is None:
            return
        if self._filter_list is not None and self._filter_list is not lv:
            prev = self._header_for_list(self._filter_list)
            if prev is not None:
                if prev.filter_input.value:
                    prev.set_filter_visible(focused=False)
                else:
                    self._filter_list.apply_filter("")
                    prev.clear_filter()
        self._filter_list = lv
        header.show_filter()

    def on_list_filter_dismissed(self, event: ListFilterDismissed) -> None:
        event.stop()
        self._close_list_filter(clear=True)

    def _header_for_list(self, lv: NavListView) -> PanelHeader | None:
        parent = lv.parent
        if parent is None:
            return None
        try:
            return parent.query_one(PanelHeader)
        except Exception:  # noqa: BLE001
            return None

    def _close_list_filter(self, *, clear: bool = True) -> bool:
        header: PanelHeader | None = None
        target = self._filter_list
        focused = self.focused
        if isinstance(focused, Input) and focused.has_class("panel-filter"):
            if isinstance(focused.parent, PanelHeader):
                header = focused.parent
        if header is None and target is not None:
            header = self._header_for_list(target)
        if header is None:
            return False
        if clear:
            if target is not None:
                target.apply_filter("")
            header.clear_filter()
        else:
            header.set_filter_visible(focused=False)
        self._filter_list = None
        if target is not None:
            target.focus()
        return True

    def on_input_changed(self, event: Input.Changed) -> None:
        if not event.input.has_class("panel-filter") or self._filter_list is None:
            return
        self._filter_list.apply_filter(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if not event.input.has_class("panel-filter"):
            return
        if not event.input.value:
            self._close_list_filter(clear=True)
            return
        # keep the filter, return focus to the list
        target = self._filter_list
        header = event.input.parent
        if isinstance(header, PanelHeader):
            header.set_filter_visible(focused=False)
        if target is not None:
            target.focus()

    def on_filter_leave_down(self, event: FilterLeaveDown) -> None:
        event.stop()
        inp = self.focused
        if not isinstance(inp, Input) or not inp.has_class("panel-filter"):
            return
        if not inp.value:
            self._close_list_filter(clear=True)
            return
        target = self._filter_list
        header = inp.parent
        if isinstance(header, PanelHeader):
            header.set_filter_visible(focused=False)
        if target is not None:
            target.highlight_first_visible()
            target.focus()

    def _on_state_change(self) -> None:
        track = self.state.current_track
        snap = self.state.snapshot
        title = track.display if track else "Nothing playing"
        bar = self.query_one(StatusBar)
        try:
            np_bar = bar.query_one("#np-bar", Label)
            width = max(20, np_bar.size.width)
        except Exception:  # noqa: BLE001
            width = max(20, self.size.width - 4)
        duration = display_duration(
            player=snap.duration,
            catalog=track.duration if track else None,
        )
        finished = self.state.queue_finished or (
            snap.eof
            and not snap.loading
            and not self.state.queue.autoplay
            and not self.state.queue.has_next()
        )
        position = 0.0 if snap.loading and not finished else snap.position
        position = display_position(
            position, duration, complete=finished or snap.eof
        )
        bar.update_display(
            title,
            playing=snap.is_playing,
            position=position,
            duration=duration or 0.0,
            status=self.state.status_message,
            volume=self.state.player.volume,
            audio_bitrate=snap.audio_bitrate,
            width=width,
            finished=finished,
        )
        if self.view_name == "history":
            try:
                self.query_one(HistoryScreen).refresh_lists()
            except Exception:  # noqa: BLE001
                pass

    def _focus_list(self, panel_id: str) -> None:
        try:
            self.query_one(f"#{panel_id}").focus()
        except Exception:  # noqa: BLE001
            pass

    def _primary_content_list_id(self) -> str | None:
        mapping = {
            "home": "home-list",
            "explore": "explore-list",
            "library": "lib-list",
            "local": "local-list",
            "trending": "disc-results",
            "search": "search-list",
            "history": "queue-list",
            "settings": "settings-nav",
            "help": "help-body",
        }
        if self.view_name == "home":
            try:
                tracks = self.query_one("#home-tracks", NavListView)
                if tracks.display:
                    return "home-tracks"
            except Exception:  # noqa: BLE001
                pass
        if self.view_name == "explore":
            try:
                tracks = self.query_one("#explore-tracks", NavListView)
                if tracks.display:
                    return "explore-tracks"
            except Exception:  # noqa: BLE001
                pass
        if self.view_name == "library":
            try:
                tracks = self.query_one("#lib-tracks", NavListView)
                if tracks.display:
                    return "lib-tracks"
            except Exception:  # noqa: BLE001
                pass
        if self.view_name == "local":
            try:
                tracks = self.query_one("#local-tracks", NavListView)
                if tracks.display:
                    return "local-tracks"
            except Exception:  # noqa: BLE001
                pass
        if self.view_name == "search":
            try:
                tracks = self.query_one("#search-tracks", NavListView)
                if tracks.display:
                    return "search-tracks"
            except Exception:  # noqa: BLE001
                pass
        return mapping.get(self.view_name)

    def on_panel_edge(self, event: PanelEdge) -> None:
        direction = event.direction
        list_id = event.list_id

        if direction == "k" and list_id == "search-list":
            try:
                self.query_one(SearchScreen).focus_query()
            except Exception:  # noqa: BLE001
                pass
            return
        if direction in {"j", "k"}:
            return

        if direction == "l":
            if list_id == "sidebar-list":
                target = self._primary_content_list_id()
                if target:
                    self._focus_list(target)
            elif list_id == "queue-list":
                self._focus_list("history-list")
            return

        if direction == "h":
            if list_id == "history-list":
                self._focus_list("queue-list")
            elif list_id != "sidebar-list":
                self._focus_list("sidebar-list")

    async def on_sidebar_selected(self, event: Sidebar.Selected) -> None:
        await self._navigate(event.key)

    def set_sidebar_fetching(self, key: str) -> None:
        try:
            self.query_one(Sidebar).set_fetching(key)
        except Exception:  # noqa: BLE001
            pass

    def clear_sidebar_fetching(self, key: str | None = None) -> None:
        try:
            self.query_one(Sidebar).clear_fetching(key)
        except Exception:  # noqa: BLE001
            pass

    def _sidebar_network_key(self, key: str) -> str | None:
        if key in {"home", "explore", "trending", "random"}:
            return key
        if key in {"library", "history"} and self.state.music.authenticated:
            return key
        return None

    async def _navigate(self, key: str) -> None:
        fetch_key = self._sidebar_network_key(key)
        if fetch_key:
            self.set_sidebar_fetching(fetch_key)
        else:
            self.clear_sidebar_fetching()
        if key == "home":
            await self.show_home()
        elif key == "library":
            await self.show_library()
        elif key == "local":
            await self.show_local()
        elif key == "explore":
            await self.show_explore()
        elif key == "search":
            await self.show_search()
        elif key == "trending":
            await self.show_view(DiscoveryScreen(), "trending")
        elif key == "history":
            await self.show_view(HistoryScreen(), "history")
        elif key == "settings":
            await self.show_view(SettingsScreen(), "settings")
        elif key == "help":
            await self.show_view(HelpScreen(), "help")
        elif key == "random":
            self.run_worker(self._play_random_worker, thread=True)

    def _play_random_worker(self) -> None:
        error: str | None = None
        track = None
        try:
            query = random.choice(RANDOM_QUERIES)
            tracks = self.state.music.search_songs(query, limit=10)
            if tracks:
                track = random.choice(tracks)
        except Exception as exc:  # noqa: BLE001
            error = str(exc)

        def done() -> None:
            self.clear_sidebar_fetching("random")
            if error:
                self.state.status_message = f"Search failed: {error}"
                self._on_state_change()
            elif track is None:
                self.state.status_message = "No random tracks found"
                self._on_state_change()
            else:
                self.state.play_track(track)

        self.call_from_thread(done)

    async def action_focus_search_query(self) -> None:
        if self.view_name != "search":
            await self._navigate("search")
        try:
            self.query_one(SearchScreen).focus_query()
        except Exception:  # noqa: BLE001
            pass

    def action_toggle_pause(self) -> None:
        self.state.toggle_pause()

    def action_next_track(self) -> None:
        self.state.next()

    def action_prev_track(self) -> None:
        self.state.previous()

    def _input_focused(self) -> bool:
        # useful for ignoring most global keybinds when typing in Input
        return isinstance(self.focused, Input)

    def action_vol_up(self) -> None:
        if self._input_focused():
            return
        self.state.volume_up()

    def action_vol_down(self) -> None:
        if self._input_focused():
            return
        self.state.volume_down()

    def action_mark_library(self) -> None:
        if self._input_focused() or self.view_name != "library":
            return
        focused = self.focused
        if focused is None or focused.id != "lib-list":
            return
        try:
            self.query_one(LibraryScreen).mark_focused()
        except Exception:  # noqa: BLE001
            pass

    def action_add_to_marked(self) -> None:
        if self._input_focused():
            return
        track = self._focused_song()
        if track is None:
            return
        target = self.state.library_mark
        if target is None:
            self.notify(
                "Mark (m) a playlist, Saved Songs, or Liked Songs in My Library",
                title="Nothing marked",
                severity="warning",
            )
            return
        self.state.library_jobs.add_song(
            track,
            target,
            on_done=lambda result: self.call_from_thread(lambda: self._notify_add(result)),
        )

    def _notify_add(self, result: AddResult) -> None:
        if result.reason == "success":
            self.notify(result.message, severity="information")
            return
        if result.reason == "duplicate":
            self.notify(result.message, title="Already added", severity="warning")
            return
        self.notify(result.message, title="Could not add", severity="error")

    def action_compose_playlist(self) -> None:
        if self._input_focused() or self.view_name != "library":
            return
        focused = self.focused
        if focused is None or focused.id != "lib-list":
            return
        self._pending_delete = None
        try:
            self.query_one(LibraryScreen).start_compose()
        except Exception:  # noqa: BLE001
            pass

    def action_yank_track(self) -> None:
        if self._input_focused():
            return
        track = self._focused_song()
        if track is not None:
            self.state.replace_register(track)

    def action_delete_in_library(self) -> None:
        if self._input_focused():
            return
        # see if focused on playlist in library to attempt playlist delete
        if self.view_name == "library":
            try:
                screen = self.query_one(LibraryScreen)
            except Exception:  # noqa: BLE001
                screen = None
            if screen is not None:
                playlist = screen.focused_index_playlist()
                if playlist is not None:
                    self._confirm_delete_playlist(playlist)
                    return
        # see if focused on track anywhere and attempt track delete
        track = self._focused_song()
        if track is None:
            return
        target = self._delete_target()
        if target is None:
            self.notify(
                "Mark (m) a playlist, Saved Songs, or Liked Songs, or open one in My Library",
                title="Nothing to delete from",
                severity="warning",
            )
            return
        if self.state.config.config.confirm_delete:
            self._pending_delete = _PendingDelete(track=track, target=target)
            msg = f'Delete "{track.title}" from {target.title}? Enter to confirm'
            self.state.status_message = msg
            self.notify(msg, title="Confirm delete", severity="warning", timeout=12)
            self._on_state_change()
            return
        self._run_delete(track, target)
        # regardless if delete worked or not, update register
        self.state.replace_register(track)

    def _confirm_delete_playlist(self, playlist: PlaylistSummary) -> None:
        if not is_user_playlist(playlist):
            self.notify(
                f"{playlist.title} cannot be deleted",
                title="Cannot delete",
                severity="warning",
            )
            return
        self._pending_delete = _PendingDelete(playlist=playlist)
        msg = f'Delete playlist "{playlist.title}"? Enter to confirm'
        self.state.status_message = msg
        self.notify(msg, title="Confirm delete", severity="warning", timeout=12)
        self._on_state_change()

    def _delete_target(self) -> LibraryTarget | None:
        if self.view_name == "library":
            try:
                opened = self.query_one(LibraryScreen).open_target()
            except Exception:  # noqa: BLE001
                opened = None
            if opened is not None:
                return opened
        return self.state.library_mark

    def _cancel_pending_delete(self) -> bool:
        if self._pending_delete is None:
            return False
        self._pending_delete = None
        self.state.status_message = "Delete cancelled"
        self.notify("Delete cancelled", severity="information")
        self._on_state_change()
        return True

    async def action_confirm_or_select(self) -> None:
        if isinstance(self.focused, Input):
            await self.focused.action_submit()
            return
        if self._pending_delete is not None:
            pending = self._pending_delete
            self._pending_delete = None
            if pending.playlist is not None:
                self._run_delete_playlist(pending.playlist)
                return
            if pending.track is not None and pending.target is not None:
                self._run_delete(pending.track, pending.target)
            return
        focused = self.focused
        if isinstance(focused, OptionList):
            focused.action_select()

    def _run_delete(self, track: Track, target: LibraryTarget) -> None:
        restore_at = self._prepare_delete_ui(track, target)
        self.state.library_jobs.remove_song(
            track,
            target,
            on_done=lambda result: self.call_from_thread(
                lambda: self._after_delete(result, track, target, restore_at)
            ),
        )

    def _prepare_delete_ui(self, track: Track, target: LibraryTarget) -> int | None:
        # drop/advance immediately so spam x hits the next song, not the same one
        if self.view_name == "library":
            try:
                return self.query_one(LibraryScreen).drop_matching(track)
            except Exception:  # noqa: BLE001
                return None
        focused = self.focused
        if isinstance(focused, NavListView):
            focused.try_cursor_down()
        return None

    def _run_delete_playlist(self, playlist: PlaylistSummary) -> None:
        self.state.library_jobs.delete_playlist(
            playlist,
            on_done=lambda result: self.call_from_thread(
                lambda: self._after_delete_playlist(result, playlist)
            ),
        )

    def _after_delete(
        self,
        result: AddResult,
        track: Track,
        target: LibraryTarget,
        restore_at: int | None,
    ) -> None:
        if result.reason == "success":
            self.notify(result.message, severity="information")
        else:
            self.notify(result.message, title="Could not delete", severity="error")
            if restore_at is not None and self.view_name == "library":
                try:
                    screen = self.query_one(LibraryScreen)
                    opened = screen.open_target()
                    if opened is not None and opened.playlist_id == target.playlist_id:
                        screen.restore_track(track, restore_at)
                except Exception:  # noqa: BLE001
                    pass
        self.state.status_message = result.message
        self._on_state_change()

    def _after_delete_playlist(
        self, result: PlaylistWriteResult, playlist: PlaylistSummary
    ) -> None:
        if result.ok:
            self.notify(result.message, severity="information")
        else:
            self.notify(result.message, title="Could not delete", severity="error")
        self.state.status_message = result.message
        self._on_state_change()
        if not result.ok or self.view_name != "library":
            return
        mark = self.state.library_mark
        if mark is not None and mark.playlist_id == playlist.playlist_id:
            self.state.library_mark = None
        try:
            self.query_one(LibraryScreen).drop_playlist(playlist.playlist_id)
        except Exception:  # noqa: BLE001
            pass

    def _focused_song(self) -> Track | None:
        focused = self.focused
        if isinstance(focused, TrackList):
            idx = focused.index
            if idx is None or idx < 0 or idx >= len(focused.tracks):
                return None
            return focused.tracks[idx]
        if not isinstance(focused, NavListView) or focused.id == "sidebar-list":
            return None
        if self.view_name in {"home", "explore"}:
            try:
                return self.query_one(CatalogScreen).focused_song()
            except Exception:  # noqa: BLE001
                return None
        if self.view_name == "search":
            try:
                return self.query_one(SearchScreen).focused_song()
            except Exception:  # noqa: BLE001
                return None
        return None

    def action_paste_in_library(self) -> None:
        if self._input_focused():
            return
        if self.view_name != "library":
            return
        try:
            screen = self.query_one(LibraryScreen)
        except Exception:  # noqa: BLE001
            return
        # see if on top-level, focused on playlist. if so paste in that playlist
        playlist = screen.focused_index_playlist()
        if playlist is not None:
            target = library_target_for(playlist)
            if target is not None:
                self.paste_register(target)
            return
        # drilled. paste in current playlist
        try:
            opened = self.query_one(LibraryScreen).open_target()
        except Exception:  # noqa: BLE001
            opened = None
        if opened is not None:
            self.paste_register(opened)
        
    def paste_register(self, target: LibraryTarget) -> None:
        if not self.state.register:
            return
        for track in self.state.register:
            restore_at = self._prepare_paste_ui(track, target)
            self.state.library_jobs.add_song(
                track,
                target,
                on_done=lambda result, t=track, tgt=target, at=restore_at: (
                    self.call_from_thread(
                        lambda r=result, tr=t, tg=tgt, idx=at: self._after_add(
                            r, tr, tg, idx
                        )
                    )
                ),
            )

    def _prepare_paste_ui(self, track: Track, target: LibraryTarget) -> int | None:
        # visually paste at bottom; this is separate than actually adding to YouTube
        if self.view_name != "library":
            return None
        try:
            screen = self.query_one(LibraryScreen)
            opened = screen.open_target()
            if opened is None or opened.playlist_id != target.playlist_id:
                return None
            return screen.append_track(track)
        except Exception:  # noqa: BLE001
            return None

    def _after_add(
        self,
        result: AddResult,
        track: Track,
        target: LibraryTarget,
        restore_at: int | None,
    ) -> None:
        self._notify_add(result)
        if result.ok or restore_at is None or self.view_name != "library":
            return
        try:
            screen = self.query_one(LibraryScreen)
            opened = screen.open_target()
            if opened is not None and opened.playlist_id == target.playlist_id:
                screen.drop_appended(track, restore_at)
        except Exception:  # noqa: BLE001
            pass

    def action_seek_back(self) -> None:
        # jump back 30s. Unbound; keep for a future keymap
        if self._input_focused():
            return
        self.state.seek_relative(-30)

    def action_seek_forward(self) -> None:
        # jump forward 30s. Unbound; keep for a future keymap
        if self._input_focused():
            return
        self.state.seek_relative(30)

    def action_seek_tenth(self, tenth: int) -> None:
        if self._input_focused():
            return
        self.state.seek_tenth(int(tenth))

    def action_shuffle_queue(self) -> None:
        self.state.shuffle_queue()

    def action_queue_insert(self) -> None:
        self._queue_from_focus(play_next=True)

    def action_queue_append(self) -> None:
        self._queue_from_focus(play_next=False)

    def action_download(self) -> None:
        if self._input_focused():
            return
        self._download_from_focus()

    def download_tracks(
        self,
        tracks: list[Track],
        *,
        collection: str | None = None,
        emoji: str | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        on_finished: Callable[[], None] | None = None,
    ) -> None:
        if not tracks:
            return
        if collection:
            save_local_playlist(
                LocalPlaylist(
                    emoji=emoji or "📁",
                    title=collection,
                    tracks=tracks,
                )
            )

        def progress(current: int, total: int) -> None:
            self.call_from_thread(
                lambda c=current, t=total: self._on_download_progress(
                    c, t, collection, on_progress
                )
            )

        def done(result: DownloadBatchResult) -> None:
            self.call_from_thread(
                lambda r=result: self._on_download_done(r, on_finished)
            )

        self.state.downloads.enqueue(
            tracks,
            collection=collection,
            on_progress=progress,
            on_done=done,
        )

    def _on_download_progress(
        self,
        current: int,
        total: int,
        collection: str | None,
        on_progress: Callable[[int, int], None] | None,
    ) -> None:
        if collection:
            self.state.status_message = f"Downloading {collection}: {current}/{total}"
            self._on_state_change()
        if on_progress is not None:
            try:
                on_progress(current, total)
            except Exception:  # noqa: BLE001
                pass

    def _on_download_done(
        self,
        result: DownloadBatchResult,
        on_finished: Callable[[], None] | None,
    ) -> None:
        if on_finished is not None:
            try:
                on_finished()
            except Exception:  # noqa: BLE001
                pass
        self._notify_download(result)

    def _notify_download(self, result: DownloadBatchResult) -> None:
        if result.collection:
            total = len(result.items)
            if result.failed and result.ok == 0 and result.skipped == 0:
                err = next((i.error for i in result.items if i.error), "Download failed")
                self.notify(
                    f"{result.collection}: {err}",
                    title="Download failed",
                    severity="error",
                )
                return
            parts = [f"Downloaded {result.ok} of {total} from {result.collection}"]
            if result.skipped:
                parts.append(f"{result.skipped} already saved")
            if result.failed:
                parts.append(f"{result.failed} failed")
            severity: SeverityLevel = "warning" if result.failed else "information"
            if result.ok == 0 and result.skipped == total:
                self.notify(
                    f"{total} already saved from {result.collection}",
                    title="Download",
                    severity="information",
                )
                return
            self.notify("; ".join(parts), title="Download", severity=severity)
            return
        if not result.items:
            return
        item = result.items[0]
        if item.status == "ok":
            self.notify(f"Downloaded {item.track.display}", severity="information")
            return
        if item.status == "skipped":
            self.notify(
                f"Already downloaded: {item.track.display}",
                title="Download",
                severity="information",
            )
            return
        self.notify(
            item.error or "Download failed",
            title=f"Could not download {item.track.title}",
            severity="error",
        )

    def _download_from_focus(self) -> None:
        if self.view_name in {"home", "explore"}:
            focused = self.focused
            prefix = self.view_name
            if focused is not None and focused.id in {f"{prefix}-list", f"{prefix}-tracks"}:
                try:
                    self.query_one(CatalogScreen).download_selection()
                except Exception:  # noqa: BLE001
                    pass
            return
        if self.view_name == "library":
            focused = self.focused
            if focused is not None and focused.id in {"lib-list", "lib-tracks"}:
                try:
                    self.query_one(LibraryScreen).download_selection()
                except Exception:  # noqa: BLE001
                    pass
            return
        if self.view_name == "search":
            focused = self.focused
            if focused is not None and focused.id in {"search-list", "search-tracks"}:
                try:
                    self.query_one(SearchScreen).download_selection()
                except Exception:  # noqa: BLE001
                    pass
            return
        tracks = self._focused_queue_tracks(include_queue=True)
        if tracks:
            self.download_tracks(tracks)

    def _queue_from_focus(self, *, play_next: bool) -> None:
        if isinstance(self.focused, Input):
            return
        if self.view_name in {"home", "explore"}:
            focused = self.focused
            prefix = self.view_name
            if focused is not None and focused.id in {f"{prefix}-list", f"{prefix}-tracks"}:
                try:
                    self.query_one(CatalogScreen).queue_selection(play_next=play_next)
                except Exception:  # noqa: BLE001
                    pass
            return
        if self.view_name == "library":
            focused = self.focused
            if focused is not None and focused.id in {"lib-list", "lib-tracks"}:
                try:
                    self.query_one(LibraryScreen).queue_selection(play_next=play_next)
                except Exception:  # noqa: BLE001
                    pass
            return
        if self.view_name == "local":
            focused = self.focused
            if focused is not None and focused.id in {"local-list", "local-tracks"}:
                try:
                    self.query_one(LocalScreen).queue_selection(play_next=play_next)
                except Exception:  # noqa: BLE001
                    pass
            return
        if self.view_name == "search":
            focused = self.focused
            if focused is not None and focused.id in {"search-list", "search-tracks"}:
                try:
                    self.query_one(SearchScreen).queue_selection(play_next=play_next)
                except Exception:  # noqa: BLE001
                    pass
            return
        tracks = self._focused_queue_tracks()
        if not tracks:
            return
        if play_next:
            self.state.queue_play_next(tracks)
        else:
            self.state.queue_append(tracks)

    def _focused_queue_tracks(self, *, include_queue: bool = False) -> list[Track]:
        focused = self.focused
        if isinstance(focused, TrackList):
            if focused.id == "queue-list" and not include_queue:
                return []
            idx = focused.index
            if idx is None or idx < 0 or idx >= len(focused.tracks):
                return []
            return [focused.tracks[idx]]
        return []

    def action_cycle_repeat(self) -> None:
        self.state.cycle_repeat()

    async def action_open_settings(self) -> None:
        await self.show_view(SettingsScreen(), "settings")

    async def action_open_help(self) -> None:
        await self.show_view(HelpScreen(), "help")

    async def action_open_history(self) -> None:
        await self.show_view(HistoryScreen(), "history")
