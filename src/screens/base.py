"""shared in-line activity indicators - fetching, downloading, - but not marked"""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from utils import row_activity_prompt
from widgets import NavListView


class ContentView(Static):
    # a page shown in #content; Esc/q is handled by the app (show_home)

    DEFAULT_CSS = """
    ContentView {
        height: 1fr;
        width: 1fr;
        background: transparent;
    }
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._opening: str | None = None
        self._opening_row: int | None = None
        self._download_counts_by_row: dict[int, tuple[int, int]] = {}

    def _set_opening(self, key: str | None, row: int | None = None) -> None:
        self._opening = key
        self._opening_row = row if key is not None else None

    def _row_activity(self, index: int, base: str) -> str | Text:
        fetching = self._opening is not None and self._opening_row == index
        return row_activity_prompt(
            base,
            downloading=self._download_counts_by_row.get(index),
            fetching=fetching,
        )

    def _apply_row_prompt(self, source_index: int, list_id: str) -> None:
        rows = getattr(self, "_rows", None)
        if not isinstance(rows, list) or source_index < 0 or source_index >= len(rows):
            return
        try:
            lv = self.query_one(f"#{list_id}", NavListView)
            line = self._line(source_index, rows[source_index])  # type: ignore[attr-defined]
            prompt = self._row_activity(source_index, line)
            for i, opt in enumerate(lv.options):
                if getattr(opt, "source_index", i) == source_index:
                    lv.replace_option_prompt_at_index(i, prompt)
                    return
        except Exception:  # noqa: BLE001
            pass

    def _set_download_progress(
        self, row_index: int, current: int, total: int, list_id: str
    ) -> None:
        self._download_counts_by_row[row_index] = (current, total)
        self._apply_row_prompt(row_index, list_id)

    def _clear_download_progress(self, row_index: int, list_id: str) -> None:
        self._download_counts_by_row.pop(row_index, None)
        self._apply_row_prompt(row_index, list_id)
