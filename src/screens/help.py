"""Help view"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Label, Markdown

from screens.base import ContentView
from widgets import PanelEdge

HELP_MD = """

## General
- **hjkl / arrows** — Directional navigation
- **Enter** — Open, select, or play. When on a song, overrides queue with every song under currently focused.
- **Esc** / **q** — Back
- **/** — Filter the focused list (can also jump to a line number)
- **g / G** — Top / bottom row in any list
- **z** — Center the highlighted row (Vim zz)
- **&#92;** — Jump to Search screen from anywhere
- **H** — Queue & History
- **,** — Settings
- **?** — This help
- **Ctrl+Q** — Quit

## Playback
- **Space** — Play / pause
- **n** — Next track
- **b** — Previous track
- **0–9** — Jump to 0%, 10%, … 90% of the current track (same as YouTube)
- **- / =** — Volume down / up (separate from system volume)
- **s** — Shuffle the remaining queue
- **r** — Cycle repeat
- **a** — Append to queue (song, playlist, etc.)
- **i** — Insert as play-next (song, playlist, etc.)
- **d** — Download to `~/Music/yt-collate/` (song, playlist, etc.)

## Library
- **y** — Yank the focused song into register
- **x** — Delete song/playlist from Library; if song, also yanks into register. If not in Library, deletes song from marked collection
- **p** — Paste register into currently focused/opened playlist in Library
- **m** — Mark a playlist, Saved Songs, or Liked Songs in Library
- **+** — Add the focused song to the marked collection
- **o** — New private playlist in Library; type name and Enter

## Authentication
See GitHub README: https://github.com/indigo0445/yt-collate
"""


class HelpBody(VerticalScroll):
    # focus target for the Help panel (pink border); h returns to Main Selection

    BINDINGS = [
        Binding("h", "nav_left", "Left", show=False),
        Binding("l", "nav_right", "Right", show=False),
        Binding("left", "nav_left", "Left", show=False),
        Binding("right", "nav_right", "Right", show=False),
        Binding("j", "scroll_down", "Down", show=False),
        Binding("k", "scroll_up", "Up", show=False),
        Binding("down", "scroll_down", "Down", show=False),
        Binding("up", "scroll_up", "Up", show=False),
    ]

    def action_nav_left(self) -> None:
        self.post_message(PanelEdge("h", self.id or "help-body"))

    def action_nav_right(self) -> None:
        self.post_message(PanelEdge("l", self.id or "help-body"))


class HelpScreen(ContentView):
    def compose(self) -> ComposeResult:
        with Vertical(classes="content-panel"):
            yield Label("❓ Help", classes="panel-title")
            yield HelpBody(Markdown(HELP_MD), id="help-body")

    def on_mount(self) -> None:
        self.query_one("#help-body").focus()

    async def on_key(self, event) -> None:
        if event.key == "question_mark":
            await self.app.action_go_back()  # type: ignore[attr-defined]
            event.stop()
