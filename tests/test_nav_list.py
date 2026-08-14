"""NavListView OptionList filter keeps original row indices."""

from __future__ import annotations

from widgets import NavListView, make_row, vim_center_row


def test_vim_center_row() -> None:
    assert vim_center_row(1) == 0
    assert vim_center_row(2) == 0  # even: upper of the two middles
    assert vim_center_row(10) == 4
    assert vim_center_row(11) == 5


def test_filter_preserves_source_index() -> None:
    lv = NavListView()
    lv.set_rows(["Alpha", "Beta", "Alpine"])
    assert lv.option_count == 3
    assert lv.index == 0

    lv.apply_filter("alp")
    assert lv.option_count == 2
    assert lv.index == 0
    lv.highlighted = 1
    assert lv.index == 2


def test_make_row_ids_survive_filter() -> None:
    lv = NavListView()
    lv.set_rows(
        [
            make_row("Library", id="nav-library"),
            make_row("Search", id="nav-search"),
            make_row("Settings", id="nav-settings"),
        ]
    )
    lv.apply_filter("se")
    assert lv.option_count == 2
    assert lv.highlighted_option is not None
    assert lv.highlighted_option.id == "nav-search"
    lv.highlighted = 1
    assert lv.highlighted_option is not None
    assert lv.highlighted_option.id == "nav-settings"
    assert lv.index == 2


def test_highlight_first_visible_jumps_to_top_match() -> None:
    lv = NavListView()
    lv.set_rows(
        [
            make_row("Search", id="nav-search"),
            make_row("Settings", id="nav-settings"),
        ]
    )
    lv.index = 1
    lv.apply_filter("s")
    assert lv.highlighted_option is not None
    assert lv.highlighted_option.id == "nav-settings"
    assert lv.highlight_first_visible() is True
    assert lv.highlighted_option is not None
    assert lv.highlighted_option.id == "nav-search"


def test_clear_filter_keeps_highlighted_row() -> None:
    lv = NavListView()
    lv.set_rows(["Alpha", "Beta", "Alpine", "Gamma"])
    lv.apply_filter("alp")
    lv.highlighted = 1
    assert lv.index == 2  # Alpine
    lv.apply_filter("")
    assert lv.option_count == 4
    assert lv.index == 2
