"""stub views for radio / live / mood"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label

from screens.base import ContentView


class StubScreen(ContentView):
    def __init__(self, title: str, body: str) -> None:
        super().__init__()
        self._title = title
        self._body = body

    def compose(self) -> ComposeResult:
        with Vertical(classes="content-panel"):
            yield Label(self._title, classes="panel-title")
            yield Label(self._body, classes="muted")
            yield Label("Press Esc or q to go back.", classes="muted")
