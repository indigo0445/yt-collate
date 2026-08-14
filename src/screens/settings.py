"""Settings — Enter edits the auth path in-place or toggles a yes/no option"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Input, Label

from keyhints import SETTINGS
from screens.base import ContentView
from widgets import NavListView, PanelHeader


def _yn(value: bool) -> str:
    return "yes" if value else "no"


class AuthPathInput(Input):
    # auth path field; Down leaves to the next settings row

    BINDINGS = [
        Binding("down", "leave_down", "Down", show=False, priority=True),
    ]

    def action_leave_down(self) -> None:
        screen = self.query_ancestor(SettingsScreen)
        if screen is not None:
            screen.leave_auth_edit_down()


class SettingsScreen(ContentView):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._editing_auth = False

    def compose(self) -> ComposeResult:
        with Vertical(classes="content-panel"):
            yield PanelHeader("⚙️ Settings")
            with Horizontal(id="auth-edit-row"):
                yield Label("1. Auth file: ", id="auth-edit-prefix")
                yield AuthPathInput(
                    placeholder="~/.config/yt-collate/headers_auth.json",
                    id="auth-path",
                )
            yield NavListView(id="settings-nav")
            yield Label(
                "Setup outside TUI:\n"
                "  uv run ytmusicapi browser --file "
                "~/.config/yt-collate/headers_auth.json\n"
                "Then Enter on Auth file, paste the path, and press Enter. "
                "Empty Enter disconnects.",
                classes="muted",
            )
            yield Label(
                f"Config dir: {self.app.state.config.config_dir}",  # type: ignore[attr-defined]
                classes="muted",
            )
            yield Label(SETTINGS, classes="muted")

    def on_mount(self) -> None:
        self.query_one("#auth-edit-row", Horizontal).display = False
        self._rebuild_nav()
        self.query_one("#settings-nav", NavListView).focus()

    def handle_back(self) -> bool:
        # cancel in-line auth edit first. Returns True if handled locally
        if self._editing_auth:
            self._stop_auth_edit(select_index=0)
            return True
        return False

    def leave_auth_edit_down(self) -> None:
        # revert unsaved path and focus the setting below Auth file
        if self._editing_auth:
            self._stop_auth_edit(select_index=1)

    def _nav_rows(self) -> list[str]:
        state = self.app.state  # type: ignore[attr-defined]
        path = state.config.auth_headers_path
        cfg = state.config.config
        return [
            f"Auth file: {path}",
            f"Discord RPC: {_yn(cfg.discord_rpc)}",
            f"Autoplay: {_yn(cfg.autoplay)}",
            f"Show Episodes for Later: {_yn(cfg.show_episodes_for_later)}",
            f"Show Liked Songs: {_yn(cfg.show_liked_songs)}",
            f"Show Saved Songs: {_yn(cfg.show_saved_songs)}",
            f"Always confirm to delete: {_yn(cfg.confirm_delete)}",
        ]

    def _rebuild_nav(self) -> None:
        lv = self.query_one("#settings-nav", NavListView)
        idx = lv.index or 0
        rows = self._nav_rows()
        self.query_one("#auth-edit-row", Horizontal).display = self._editing_auth
        if self._editing_auth:
            numbered = [f"{i + 2}. {text}" for i, text in enumerate(rows[1:])]
            lv.set_rows(numbered)
        else:
            numbered = [f"{i + 1}. {text}" for i, text in enumerate(rows)]
            lv.set_rows(numbered)
            if numbered:
                lv.index = min(idx, len(numbered) - 1)

    def _start_auth_edit(self) -> None:
        state = self.app.state  # type: ignore[attr-defined]
        stored = state.config.config.auth_headers_path
        inp = self.query_one("#auth-path", Input)
        inp.value = stored if stored else str(state.config.auth_headers_path)
        self._editing_auth = True
        self._rebuild_nav()
        inp.focus()

    def _stop_auth_edit(self, *, select_index: int = 0) -> None:
        self._editing_auth = False
        self._rebuild_nav()
        lv = self.query_one("#settings-nav", NavListView)
        rows = self._nav_rows()
        if rows:
            lv.index = min(max(0, select_index), len(rows) - 1)
            lv.scroll_to_highlight()
        lv.focus()
        self.call_after_refresh(lv.focus)

    def on_option_list_option_selected(self, event: NavListView.OptionSelected) -> None:
        if event.option_list.id != "settings-nav":
            return
        lv = event.option_list
        idx = lv.index if isinstance(lv, NavListView) else event.option_index
        if idx is None:
            return
        if self._editing_auth:
            idx += 1
        if idx == 0:
            self._start_auth_edit()
            return
        state = self.app.state  # type: ignore[attr-defined]
        cfg = state.config.config
        if idx == 1:
            state.set_discord_enabled(not cfg.discord_rpc)
        elif idx == 2:
            new_val = not cfg.autoplay
            state.queue.autoplay = new_val
            state.queue.save()
            state.config.update(autoplay=new_val)
            state.status_message = f"Autoplay {_yn(new_val)}"
        elif idx == 3:
            new_val = not cfg.show_episodes_for_later
            state.config.update(show_episodes_for_later=new_val)
            state.status_message = f"Show Episodes for Later {_yn(new_val)}"
        elif idx == 4:
            new_val = not cfg.show_liked_songs
            state.config.update(show_liked_songs=new_val)
            state.status_message = f"Show Liked Songs {_yn(new_val)}"
        elif idx == 5:
            new_val = not cfg.show_saved_songs
            state.config.update(show_saved_songs=new_val)
            state.status_message = f"Show Saved Songs {_yn(new_val)}"
        elif idx == 6:
            new_val = not cfg.confirm_delete
            state.config.update(confirm_delete=new_val)
            state.status_message = f"Always confirm to delete {_yn(new_val)}"
        self._rebuild_nav()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id != "auth-path":
            return
        raw = event.value.strip()
        state = self.app.state  # type: ignore[attr-defined]
        _ok, detail = state.set_auth_headers(raw if raw else None)
        state.status_message = detail
        self._stop_auth_edit()
