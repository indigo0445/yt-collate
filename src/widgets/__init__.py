"""reusable widgets"""

from __future__ import annotations

from collections.abc import Sequence

from rich.text import Text
from textual import _widget_navigation, events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.geometry import Region, Spacing
from textual.message import Message
from textual.strip import Strip
from textual.widgets import Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from keyhints import PLAYBACK_CHROME, STATUS_KEYS
from models.track import Track
from utils import clip_list_label, format_bitrate, format_time, progress_bar, truncate

# vim-style lines kept above/below the cursor when the list must scroll
SCROLL_OFF = 5


class NavOption(Option):
    # option w/ filter text and overall source index (for filtering)

    def __init__(
        self,
        prompt: str | Text,
        *,
        id: str | None = None,
        search: str | None = None,  # searchable text - diff than prompt if e.g. song-artist truncated
        source_index: int = 0,
    ) -> None:
        super().__init__(prompt, id=id)
        if search is not None:
            self.search = search
        elif isinstance(prompt, str):
            self.search = prompt
        else:
            self.search = prompt.plain
        self.source_index = source_index


class PanelEdge(Message):
    # emitted when hjkl should leave this list toward another panel

    def __init__(self, direction: str, list_id: str) -> None:
        self.direction = direction  # h/j/k/l
        self.list_id = list_id
        super().__init__()


class ListFilterRequested(Message):
    # focused list wants in-place / filter

    def __init__(self, list_id: str) -> None:
        self.list_id = list_id
        super().__init__()


class ListFilterDismissed(Message):
    # empty / filter: Backspace should close it
    pass


class LeaveInputDown(Message):
    # down-arrow from a field that sits above a list: leave the textbox
    pass


class FilterLeaveDown(Message):
    # down from / filter: focus the first visible row, keep the query
    pass


class FilterInput(Input):
    # inline header filter; Backspace/Ctrl+W on empty query exits

    BINDINGS = [
        Binding("down", "leave_down", "To list", show=False),
    ]

    def action_leave_down(self) -> None:
        self.post_message(FilterLeaveDown())

    def action_delete_left(self) -> None:
        if not self.value:
            self.post_message(ListFilterDismissed())
            return
        super().action_delete_left()

    def action_delete_left_word(self) -> None:
        if not self.value:
            self.post_message(ListFilterDismissed())
            return
        super().action_delete_left_word()


class SearchQueryInput(Input):
    # inline Search "…" field

    BINDINGS = [
        Binding("down", "leave_down", "Results", show=False),
    ]

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("compact", True)
        kwargs.setdefault("select_on_focus", True)
        kwargs.setdefault("placeholder", '"')
        super().__init__(**kwargs)
        self.results_active = False

    def check_consume_key(self, key: str, character: str | None) -> bool:
        if (key == "q" or character == "q") and self.results_active:
            return False
        return character is not None and character.isprintable()

    def action_leave_down(self) -> None:
        if self.results_active:
            self.post_message(LeaveInputDown())

    async def _on_key(self, event: events.Key) -> None:
        # Input stops printable keys before app bindings; intercept q ourselves
        if self.results_active and (event.key == "q" or event.character == "q"):
            event.prevent_default()
            event.stop()
            await self.app.action_go_back()  # type: ignore[misc]
            return
        await super()._on_key(event)

    def on_mount(self) -> None:
        self._fit_width()

    def _watch_value(self, value: str) -> None:
        super()._watch_value(value)
        self._fit_width()

    def _fit_width(self) -> None:
        self.styles.width = len(self.value) + 1

    def render_line(self, y: int) -> Strip:
        if y != 0 or not self.value:
            return super().render_line(y)
        console = self.app.console
        console_options = self.app.console_options
        max_content_width = self.scrollable_content_region.width
        result = self._value.copy()
        result.append('"')
        if self.has_focus:
            if not self.selection.is_empty:
                start, end = sorted(self.selection)
                selection_style = self.get_component_rich_style("input--selection")
                result.stylize_before(selection_style, start, end)
            if self._cursor_visible:
                cursor_style = self.get_component_rich_style("input--cursor")
                cursor = self.cursor_position
                result.stylize(cursor_style, cursor, cursor + 1)
        segments = list(
            console.render(result, console_options.update_width(self.content_width))
        )
        strip = Strip(segments)
        scroll_x, _ = self.scroll_offset
        strip = strip.crop(scroll_x, scroll_x + max_content_width + 1)
        strip = strip.extend_cell_length(max_content_width + 1)
        return strip.apply_style(self.rich_style)


class PanelHeader(Horizontal):
    # panel title with optional Search "…" query, then /filter on the same row

    def __init__(self, title: str, *, with_query: bool = False, **kwargs) -> None:
        super().__init__(**kwargs)
        self._title = title
        self._with_query = with_query
        self._filter_open = False
        self.add_class("panel-header")

    def compose(self) -> ComposeResult:
        yield Label(self._title, classes="panel-title")
        if self._with_query:
            yield Label(' \\"', classes="panel-query-chrome")
            yield SearchQueryInput(id="search-input", classes="panel-query")
        yield Label("/", classes="panel-filter-prefix")
        yield FilterInput(placeholder="", classes="panel-filter")

    def on_mount(self) -> None:
        self.query_one(".panel-filter-prefix", Label).display = False
        self.query_one(".panel-filter", Input).display = False

    def set_title(self, title: str) -> None:
        self.query_one(".panel-title", Label).update(title)

    @property
    def filter_input(self) -> Input:
        return self.query_one(".panel-filter", Input)

    def show_filter(self) -> None:
        self._filter_open = True
        self.query_one(".panel-filter-prefix", Label).display = True
        inp = self.filter_input
        inp.display = True
        inp.focus()

    def set_filter_visible(self, *, focused: bool) -> None:
        inp = self.filter_input
        # keep a bare "/" visible while the filter session is open (OS blur
        # unfocuses the input but must not hide an empty query)
        show = focused or bool(inp.value) or self._filter_open
        inp.display = show
        self.query_one(".panel-filter-prefix", Label).display = show

    def clear_filter(self) -> None:
        self._filter_open = False
        inp = self.filter_input
        inp.value = ""
        inp.display = False
        self.query_one(".panel-filter-prefix", Label).display = False


class NavListView(OptionList):
    # OptionList with custom bindings

    BINDINGS = [
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("h", "nav_left", "Left", show=False),
        Binding("l", "nav_right", "Right", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("left", "nav_left", "Left", show=False),
        Binding("right", "nav_right", "Right", show=False),
        Binding("g", "first", "Top", show=False),
        Binding("G", "last", "Bottom", show=False),
        Binding("z", "center_cursor", "Center", show=False),
        Binding("slash", "start_filter", "Filter", show=False),
    ]

    def __init__(self, **kwargs) -> None:
        self._leave_up = bool(kwargs.pop("leave_up", False))
        kwargs.setdefault("compact", True)
        kwargs.setdefault("markup", False)
        self._rows: list[NavOption] = []
        self._filter_query = ""
        super().__init__(**kwargs)

    @property
    def index(self) -> int | None:
        # source-row index (stable across / filter)
        opt = self.highlighted_option
        if isinstance(opt, NavOption):
            return opt.source_index
        return self.highlighted

    @index.setter
    def index(self, value: int | None) -> None:
        if value is None or not self._options:
            self.highlighted = None
            return
        for i, opt in enumerate(self._options):
            if isinstance(opt, NavOption) and opt.source_index == value:
                self.highlighted = i
                return
        self.highlighted = max(0, min(value, len(self._options) - 1))

    def set_rows(self, rows: Sequence[str | Text | NavOption]) -> None:
        parsed: list[NavOption] = []
        for i, row in enumerate(rows):
            opt = row if isinstance(row, NavOption) else NavOption(row)
            opt.source_index = i
            parsed.append(opt)
        self._rows = parsed
        self._rebuild_visible()

    def clear(self) -> None:
        self._rows = []
        self.clear_options()

    def append(self, item: str | NavOption) -> None:
        opt = item if isinstance(item, NavOption) else NavOption(item)
        opt.source_index = len(self._rows)
        self._rows.append(opt)
        if self._matches(opt):
            self.add_option(opt)

    def _matches(self, opt: NavOption) -> bool:
        q = self._filter_query.strip().lower()
        return (not q) or q in opt.search.lower()

    def _rebuild_visible(self, keep_source: int | None = None) -> None:
        visible = [row for row in self._rows if self._matches(row)]
        self.set_options(visible) # loses track of index; below finds/focuses it again
        if not visible:
            return
        if keep_source is not None:
            for i, opt in enumerate(visible):
                if opt.source_index == keep_source:
                    self.highlighted = i
                    self.scroll_to_highlight()
                    return
        self.highlighted = 0

    def action_start_filter(self) -> None:
        self.post_message(ListFilterRequested(self.id or ""))

    def apply_filter(self, query: str) -> None:
        keep = self.index
        self._filter_query = query
        self._rebuild_visible(keep_source=keep)

    def highlight_first_visible(self) -> bool:
        # move highlight to the first filtered row. False if the list is empty
        if not self._options:
            return False
        self.highlighted = 0
        self.scroll_to_highlight()
        return True

    def action_cursor_down(self) -> None:
        if not self._options:
            return
        nxt = _widget_navigation.find_next_enabled_no_wrap(
            self.options, self.highlighted, 1
        )
        if nxt is None:
            return
        self.highlighted = nxt

    def try_cursor_down(self) -> bool:
        # move down one row if possible. Does not leave the list
        if not self._options:
            return False
        nxt = _widget_navigation.find_next_enabled_no_wrap(
            self.options, self.highlighted, 1
        )
        if nxt is None:
            return False
        self.highlighted = nxt
        return True

    def action_cursor_up(self) -> None:
        if not self._options:
            if self._leave_up:
                self.post_message(PanelEdge("k", self.id or ""))
            return
        prev = _widget_navigation.find_next_enabled_no_wrap(
            self.options, self.highlighted, -1
        )
        if prev is None:
            if self._leave_up:
                self.post_message(PanelEdge("k", self.id or ""))
            return
        self.highlighted = prev

    def action_nav_left(self) -> None:
        self.post_message(PanelEdge("h", self.id or ""))

    def action_nav_right(self) -> None:
        self.post_message(PanelEdge("l", self.id or ""))

    @staticmethod
    def vim_center_row(viewport_h: int) -> int:
        # offset from viewport top for vim's zz; odd height uses the upper middle
        if viewport_h <= 0:
            return 0
        return (viewport_h - 1) // 2

    def action_center_cursor(self) -> None:
        # Vim zz: put the highlighted row at the center of the viewport
        highlighted = self.highlighted
        if highlighted is None or not self.is_mounted:
            return
        self._update_lines()
        try:
            y = self._index_to_line[highlighted]
        except KeyError:
            return
        viewport_h = self.scrollable_content_region.height
        if viewport_h <= 0:
            return
        self.scroll_to(
            y=y - self.vim_center_row(viewport_h),
            animate=False,
            immediate=True,
            force=True,
        )

    def scroll_to_highlight(self, top: bool = False) -> None:
        highlighted = self.highlighted
        if highlighted is None or not self.is_mounted:
            return
        self._update_lines()
        try:
            y = self._index_to_line[highlighted]
        except KeyError:
            return
        height = self._heights[highlighted]
        viewport_h = self.scrollable_content_region.height
        off = min(SCROLL_OFF, max(0, (viewport_h - 1) // 2))
        self.scroll_to_region(
            Region(0, y, self.scrollable_content_region.width, height),
            spacing=Spacing(off, 0, off, 0),
            force=True,
            animate=False,
            top=top,
            immediate=True,
        )


class Sidebar(Static):
    # Main Selection sidebar

    can_focus = False

    class Selected(Message):
        def __init__(self, key: str) -> None:
            self.key = key
            super().__init__()

    LINKS: list[tuple[str, str]] = [
        ("home", "🏠 Home"),
        ("library", "📚 My Library"),
        ("explore", "🧭 Explore"),
        ("search", "🔍 Search"),
        ("trending", "🔥 Trending"),
        ("history", "🕒 Queue & History"),
        ("random", "🎲 Play Random Song"),
        ("local", "📂 Local"),
        ("settings", "⚙️ Settings"),
        ("help", "❓ Help"),
    ]

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._fetching_key: str | None = None

    def compose(self) -> ComposeResult:
        yield PanelHeader("Main Selection")
        yield NavListView(id="sidebar-list")

    def on_mount(self) -> None:
        self._refresh_labels(highlighted=0)

    def _label_for(self, key: str) -> str:
        for link_key, label in self.LINKS:
            if link_key == key:
                return label
        return key

    def set_fetching(self, key: str) -> None:
        self.clear_fetching()
        lv = self.query_one("#sidebar-list", NavListView)
        prompt = Text(self._label_for(key))
        prompt.append(" (Fetching...)", style="italic")
        for i, opt in enumerate(lv.options):
            if getattr(opt, "id", None) == f"nav-{key}":
                lv.replace_option_prompt_at_index(i, prompt)
                self._fetching_key = key
                return

    def clear_fetching(self, key: str | None = None) -> None:
        fetching = self._fetching_key
        if fetching is None:
            return
        if key is not None and key != fetching:
            return
        self._fetching_key = None
        lv = self.query_one("#sidebar-list", NavListView)
        for i, opt in enumerate(lv.options):
            if getattr(opt, "id", None) == f"nav-{fetching}":
                lv.replace_option_prompt_at_index(i, self._label_for(fetching))
                return

    def _refresh_labels(self, highlighted: int | None = None) -> None:
        lv = self.query_one("#sidebar-list", NavListView)
        current = highlighted if highlighted is not None else (lv.index or 0)
        links = self.LINKS
        lv.set_rows([NavOption(label, id=f"nav-{key}") for key, label in links])
        if links:
            lv.index = max(0, min(current, len(links) - 1))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id != "sidebar-list":
            return
        key = (event.option_id or "").removeprefix("nav-")
        self.post_message(self.Selected(key))


class TrackList(NavListView):
    # numbered track list

    class PlayRequested(Message):
        def __init__(self, track: Track, index: int, *, list_id: str | None = None) -> None:
            self.track = track
            self.index = index
            self.list_id = list_id
            super().__init__()

    def __init__(
        self,
        tracks: list[Track] | None = None,
        *,
        mark_playing: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.tracks: list[Track] = list(tracks or [])
        self.mark_playing = mark_playing

    def _line(self, index: int, track: Track) -> str:
        numbered = f"{index + 1}. "
        if self.mark_playing and index == 0:
            prefix = "  >  "
        else:
            prefix = numbered
        return clip_list_label(
            self, prefix, f"{track.title} — {track.artist_str}"
        )

    def _refresh_lines(self) -> None:
        if not self.tracks:
            return
        keep = self.index
        self.set_rows(
            [
                NavOption(
                    self._line(i, track),
                    # allows searching by track number, perhaps inconsistent with vim's line jumping
                    # since / is not supposed to jump to line #s, oh well
                    search=f"{i + 1} {track.title} {track.artist_str}",
                )
                for i, track in enumerate(self.tracks)
            ]
        )
        if keep is not None:
            self.index = keep

    def on_resize(self) -> None:
        self._refresh_lines()

    def set_tracks(self, tracks: list[Track], *, highlight: int | None = None) -> None:
        new_ids = [t.video_id for t in tracks]
        old_ids = [t.video_id for t in self.tracks]
        keep_id = None
        if highlight is None and self.index is not None and 0 <= self.index < len(self.tracks):
            keep_id = self.tracks[self.index].video_id
        if new_ids == old_ids:
            if highlight is not None and self.tracks:
                self.index = min(max(0, highlight), len(self.tracks) - 1)
            return
        self.tracks = list(tracks)
        self.set_rows(
            [
                NavOption(
                    self._line(i, track),
                    search=f"{track.title} {track.artist_str}",
                )
                for i, track in enumerate(self.tracks)
            ]
        )
        if not self.tracks:
            return
        if highlight is not None:
            self.index = min(max(0, highlight), len(self.tracks) - 1)
            return
        if keep_id is not None:
            for i, track in enumerate(self.tracks):
                if track.video_id == keep_id:
                    self.index = i
                    return
        self.index = 0

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list is not self:
            return
        event.stop()
        idx = self.index
        if idx is None or idx < 0 or idx >= len(self.tracks):
            return
        self.post_message(self.PlayRequested(self.tracks[idx], idx, list_id=self.id))


class StatusBar(Static):
    # combined now-playing + key hints

    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal():
                yield Label("▶ Nothing playing", id="np-title")
                yield Label("", id="np-rate")
                yield Label("Vol 100%", id="np-vol")
                yield Label("0:00 / 0:00", id="np-time")
            yield Label("─" * 40, id="np-bar")
            yield Label(STATUS_KEYS, id="status-keys")
            yield Label("", id="status-line")

    def update_display(
        self,
        title: str,
        *,
        playing: bool,
        position: float,
        duration: float,
        status: str = "",
        volume: int = 100,
        audio_bitrate: float | None = None,
        width: int = 40,
        finished: bool = False,
    ) -> None:
        if finished and title and title != "Nothing playing":
            label = f"Finished: {truncate(title, 56)}"
        else:
            # action-style icon: Pause while playing, Play while paused
            icon = "⏸" if playing else "▶"
            state = "Playing" if playing else "Paused"
            if title == "Nothing playing" or not title:
                label = f"{icon} Nothing playing"
            else:
                label = f"{icon} {state}: {truncate(title, 56)}"
        self.query_one("#np-title", Label).update(label)
        self.query_one("#np-time", Label).update(
            f"{format_time(position)} / {format_time(duration)}"
        )
        self.query_one("#np-rate", Label).update(format_bitrate(audio_bitrate))
        self.query_one("#np-vol", Label).update(f"Vol {volume}%")
        bar_width = max(10, width)
        self.query_one("#np-bar", Label).update(progress_bar(position, duration, bar_width))
        extra = f"{status}  " if status else ""
        self.query_one("#status-line", Label).update(f"{extra}{PLAYBACK_CHROME}")
