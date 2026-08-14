"""Help view."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Label, Markdown

from yt_collate.screens.base import ContentView
from yt_collate.widgets import PanelEdge

HELP_MD = """
# yt-collate help

## Navigation
- **h / l** / **← / →** — Move between side-by-side panels (Main Selection, content, and Queue | Recently Played)
- **j / k** / **↓ / ↑** — Move within the focused list (stay at the first/last row)
- **g / G** — First / last row
- Start page is **Home** (YouTube Music shelves: songs, albums, playlists, artists)
- **My Library** — playlists, then Saved Songs, Liked Songs, and Episodes for Later (visibility is in Settings)
- **Explore** — new albums, new videos, trending, top songs, moods & genres
- **Enter** — Select / play
- **/** — Filter the focused list (Esc clears; **↓** keeps it and focuses the list)
- **Search** — `🔍 Search \\"query"` (artists, songs, videos). Watch URL → one result.
  **k** / **↑** on #1 returns to the query.
  **Esc** / **q** / **↓** from the query restores it and focuses #1
- **\\** — Jump to Search and focus/select the quoted query (from anywhere)
- **z** — Center the highlighted row in the list (vim zz)
- **Esc** / **q** — Close filter, leave a folder, or focus that page’s row in Main Selection.
  **q** types in text fields except the Search query after results.
  **↓** leaves Search query, `/` filter, and Settings auth
- **Ctrl+Q** — Quit
- **Ctrl+C** — Quit (with confirmation)

## Playback
- **Space** — Play / pause
- **n** — Next · **b** — Previous
- **0–9** — Jump to 0%, 10%, … 90% of the current track (same as YouTube)
- **- / =** — Volume down / up (in-app, 0–100; saved in config)
- **s** — Shuffle the remaining queue (keeps the current track first)
- **r** — Cycle repeat
- **i** — Insert as play-next (song, or album/playlist/artist from Home/Explore/Search, or playlist from My Library)
- **a** — Append to the end of the queue (song, or album/playlist/artist from Home/Explore/Search, or playlist from My Library)
- **w** — Download to `~/Music/yt-collate` (filename is the video id).
  A playlist/album/artist row bulk-downloads every song into that same folder

## Library
- **m** — Mark a playlist, Saved Songs, or Liked Songs (My Library index). Marked row uses `*` instead of `.` (`12* `) and ends with `— marked`
- **+** — Add the focused song to the marked collection
- **o** — New playlist (My Library index): dimmed row at the bottom of the list; type a name and Enter. Private, empty description. Esc cancels
- **d** / **x** — Delete the focused song from the open My Library folder, or from the marked collection (Enter confirms when Settings: Always confirm to delete). On the My Library index, delete a normal playlist (always confirms; not Liked/Saved/Episodes)
- **Shift+H** — Queue & History
- **,** — Settings
- **?** — This help

Auth: `uv run ytmusicapi browser --file ~/.config/yt-collate/headers_auth.json`
then Settings → paste path → **Enter**. Empty Enter disconnects. Startup autoloads the saved path.
Use **My Library** for playlists, Saved Songs (YouTube library, not likes), and Liked Songs.
"""


class HelpBody(VerticalScroll):
    """Focus target for the Help panel (pink border); h returns to Main Selection."""

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
