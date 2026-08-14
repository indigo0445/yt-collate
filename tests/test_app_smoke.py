"""Textual app smoke test with pilot."""

from __future__ import annotations

import threading
from pathlib import Path

import pytest
from textual.containers import Horizontal
from textual.widgets import Input

from app import YtCollateApp
from models.track import Artist, Track
from screens.explore import ExploreScreen
from screens.help import HelpScreen
from screens.history import HistoryScreen
from screens.home import HomeScreen
from screens.library import LibraryScreen
from screens.search import SearchScreen
from screens.settings import SettingsScreen
from services.music import CatalogItem, CatalogShelf
from widgets import NavListView, Sidebar, TrackList


@pytest.fixture
def stub_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.music.MusicService.get_home",
        lambda self, limit=5: [],
    )


@pytest.mark.asyncio
async def test_app_opens_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_home: None
) -> None:
    monkeypatch.setenv("YT_COLLATE_CONFIG", str(tmp_path / "cfg"))
    app = YtCollateApp()
    async with app.run_test(size=(120, 40)) as pilot:
        assert app.state is not None
        assert app.view_name == "home"
        assert app.query_one(HomeScreen)
        await pilot.pause()
        assert app.focused is not None
        assert app.focused.id == "sidebar-list"

        await pilot.press("slash")
        await pilot.pause()
        assert app.view_name == "home"
        filt = app.query_one("#sidebar Input.panel-filter", Input)
        assert filt.display is True
        assert app.focused is filt

        await pilot.press("backspace")
        await pilot.pause()
        assert filt.display is False
        assert app.focused is not None
        assert app.focused.id == "sidebar-list"

        await pilot.press("slash")
        await pilot.pause()
        assert filt.display is True
        await pilot.press("ctrl+w")
        await pilot.pause()
        assert filt.display is False
        assert app.focused is not None
        assert app.focused.id == "sidebar-list"

        # Bare "/" stays visible after the input loses focus (OS window switch).
        await pilot.press("slash")
        await pilot.pause()
        assert filt.display is True
        app.query_one("#sidebar-list").focus()
        await pilot.pause()
        prefix = app.query_one("#sidebar .panel-filter-prefix")
        assert filt.display is True
        assert prefix.display is True


@pytest.mark.asyncio
async def test_history_mount(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_home: None
) -> None:
    monkeypatch.setenv("YT_COLLATE_CONFIG", str(tmp_path / "cfg"))
    app = YtCollateApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await app.show_view(HistoryScreen(), "history")
        await pilot.pause()
        assert app.query_one(HistoryScreen)


@pytest.mark.asyncio
async def test_history_queue_follows_shuffle_and_advance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_home: None
) -> None:
    monkeypatch.setenv("YT_COLLATE_CONFIG", str(tmp_path / "cfg"))
    app = YtCollateApp()

    def track(i: int) -> Track:
        return Track(video_id=f"v{i}", title=f"T{i}", artists=[Artist(name="A")])

    async with app.run_test(size=(120, 40)) as pilot:
        app.state.queue.play_all([track(1), track(2), track(3), track(4)], start_index=0)
        await app.show_view(HistoryScreen(), "history")
        await pilot.pause()
        qlist = app.query_one("#queue-list", TrackList)
        assert [t.video_id for t in qlist.tracks] == ["v1", "v2", "v3", "v4"]
        q0 = str(qlist.get_option_at_index(0).prompt)
        q1 = str(qlist.get_option_at_index(1).prompt)
        assert q0.startswith("  >")
        assert q1.startswith("2. ")
        assert q0.index("T1") == q1.index("T2") + 2
        hlist = app.query_one("#history-list", TrackList)
        assert [t.video_id for t in hlist.tracks] == []

        app.state.queue.next_track()
        app._on_state_change()
        await pilot.pause()
        assert [t.video_id for t in qlist.tracks] == ["v2", "v3", "v4"]
        assert [t.video_id for t in hlist.tracks] == []

        app.query_one("#queue-list", TrackList).focus()
        await pilot.press("l")
        await pilot.pause()
        assert app.focused is not None and app.focused.id == "history-list"
        await pilot.press("h")
        await pilot.pause()
        assert app.focused is not None and app.focused.id == "queue-list"
        await pilot.press("h")
        await pilot.pause()
        assert app.focused is not None and app.focused.id == "sidebar-list"

        app.query_one("#history-list", TrackList).post_message(
            TrackList.PlayRequested(track(1), 0, list_id="history-list")
        )
        await pilot.pause()
        assert app.state.current_track is not None
        assert app.state.current_track.video_id == "v1"


@pytest.mark.asyncio
async def test_history_live_prepends_without_refetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_home: None
) -> None:
    monkeypatch.setenv("YT_COLLATE_CONFIG", str(tmp_path / "cfg"))
    app = YtCollateApp()
    fetches = {"n": 0}

    def track(i: int) -> Track:
        return Track(video_id=f"v{i}", title=f"T{i}", artists=[Artist(name="A")])

    def fake_load(self: HistoryScreen) -> None:
        fetches["n"] += 1
        self._set_history([track(9)])

    monkeypatch.setattr(HistoryScreen, "load_history", fake_load)

    async with app.run_test(size=(120, 40)) as pilot:
        app.state.music._authenticated = True
        monkeypatch.setattr(app.state.music, "add_history_item", lambda t: None)
        app.state.queue.play_all([track(1), track(2)], start_index=0)
        await app.show_view(HistoryScreen(), "history")
        await pilot.pause()
        hlist = app.query_one("#history-list", TrackList)
        assert [t.video_id for t in hlist.tracks][:2] == ["v1", "v9"]
        assert fetches["n"] == 1

        app.state.queue.next_track()
        app._on_state_change()
        await pilot.pause()
        assert [t.video_id for t in hlist.tracks][:3] == ["v2", "v1", "v9"]
        assert fetches["n"] == 1


@pytest.mark.asyncio
async def test_catalog_restores_focus_on_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_home: None
) -> None:
    moods = [
        CatalogItem(kind="mood", title="Chill", params="chill"),
        CatalogItem(kind="mood", title="Rock", params="rock"),
        CatalogItem(kind="mood", title="Jazz", params="jazz"),
    ]
    playlists = [
        CatalogItem(kind="playlist", title=f"Mix {i}", playlist_id=f"pl{i}")
        for i in range(8)
    ]
    monkeypatch.setattr(
        "services.music.MusicService.get_explore",
        lambda self: [CatalogShelf(title="Moods & genres", items=moods)],
    )
    monkeypatch.setenv("YT_COLLATE_CONFIG", str(tmp_path / "cfg"))
    app = YtCollateApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await app.show_explore()
        await pilot.pause()
        screen = app.query_one(ExploreScreen)
        for _ in range(30):
            if screen._loaded:
                break
            await pilot.pause()
        assert screen._loaded

        lv = app.query_one("#explore-list", NavListView)
        rock_idx = next(
            i for i, row in enumerate(screen._rows) if row.item and row.item.title == "Rock"
        )
        lv.index = rock_idx
        screen._index_cursor = rock_idx
        rock = screen._rows[rock_idx].item
        assert rock is not None
        screen._show_mood_playlists(rock, playlists)
        await pilot.pause()
        assert screen._drill == "playlists"

        lv.index = 7
        screen.handle_back()
        await pilot.pause()
        assert screen._drill == "index"
        assert lv.index == rock_idx

        screen._index_cursor = rock_idx
        screen._show_mood_playlists(rock, playlists)
        lv.index = 4
        screen._playlist_cursor = 4
        screen._show_tracks(
            playlists[4],
            [Track(video_id="v1", title="Song", artists=[Artist(name="A")])],
        )
        await pilot.pause()
        assert screen._drill == "tracks"
        screen.handle_back()
        await pilot.pause()
        assert screen._drill == "playlists"
        assert lv.index == 4


@pytest.mark.asyncio
async def test_q_goes_back_except_in_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_home: None
) -> None:
    monkeypatch.setenv("YT_COLLATE_CONFIG", str(tmp_path / "cfg"))
    app = YtCollateApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await app.show_view(HelpScreen(), "help")
        await pilot.pause()
        await pilot.press("q")
        await pilot.pause()
        assert app.view_name == "help"
        assert app.focused is not None and app.focused.id == "sidebar-list"

        await app.show_view(LibraryScreen(), "library")
        await pilot.pause()
        app.query_one("#lib-list", NavListView).focus()
        await pilot.press("q")
        await pilot.pause()
        assert app.view_name == "library"
        assert app.focused is not None and app.focused.id == "sidebar-list"
        opt = app.query_one("#sidebar-list", NavListView).highlighted_option
        assert opt is not None and opt.id == "nav-library"
        await pilot.press("q")
        await pilot.pause()
        assert app.view_name == "library"
        assert app.focused is not None and app.focused.id == "sidebar-list"

        await app.show_view(SearchScreen(), "search")
        await pilot.pause()
        inp = app.query_one("#search-input", Input)
        assert app.focused is inp
        await pilot.press("q")
        await pilot.pause()
        assert inp.value == "q"
        assert app.view_name == "search"

        inp.value = "imagine dragons"
        app.query_one(SearchScreen)._show_results(
            [
                CatalogItem(
                    kind="song",
                    title="Believer",
                    track=Track(
                        video_id="v1",
                        title="Believer",
                        artists=[Artist(name="Imagine Dragons")],
                    ),
                )
            ]
        )
        await pilot.pause()
        assert app.focused is not None and app.focused.id == "search-list"
        await pilot.press("escape")
        await pilot.pause()
        assert app.view_name == "search"
        assert app.focused is not None and app.focused.id == "sidebar-list"

        await app.show_home()
        await pilot.pause()
        app.query_one("#sidebar-list").focus()
        await pilot.press("backslash")
        await pilot.pause()
        assert app.view_name == "search"
        search_inp = app.query_one("#search-input", Input)
        assert app.focused is search_inp

        await app.show_home()
        await pilot.pause()
        app.query_one("#sidebar-list").focus()
        await pilot.press("slash")
        await pilot.pause()
        filt = app.query_one("#sidebar Input.panel-filter", Input)
        assert app.focused is filt
        await pilot.press("q")
        await pilot.pause()
        assert filt.value == "q"
        assert app.view_name == "home"


@pytest.mark.asyncio
async def test_help_takes_content_focus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_home: None
) -> None:
    monkeypatch.setenv("YT_COLLATE_CONFIG", str(tmp_path / "cfg"))
    app = YtCollateApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await app.action_open_help()
        await pilot.pause()
        assert app.view_name == "help"
        assert app.focused is not None and app.focused.id == "help-body"
        await pilot.press("h")
        await pilot.pause()
        assert app.focused is not None and app.focused.id == "sidebar-list"
        await pilot.press("l")
        await pilot.pause()
        assert app.focused is not None and app.focused.id == "help-body"
        await pilot.press("left")
        await pilot.pause()
        assert app.focused is not None and app.focused.id == "sidebar-list"
        await pilot.press("right")
        await pilot.pause()
        assert app.focused is not None and app.focused.id == "help-body"


@pytest.mark.asyncio
async def test_search_k_on_first_result_focuses_query(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_home: None
) -> None:
    monkeypatch.setenv("YT_COLLATE_CONFIG", str(tmp_path / "cfg"))
    app = YtCollateApp()

    def song(i: int) -> CatalogItem:
        return CatalogItem(
            kind="song",
            title=f"S{i}",
            track=Track(
                video_id=f"v{i}",
                title=f"S{i}",
                artists=[Artist(name="A")],
            ),
        )

    async with app.run_test(size=(120, 40)) as pilot:
        await app.show_view(SearchScreen(), "search")
        await pilot.pause()
        app.query_one(SearchScreen)._show_results([song(1), song(2)])
        await pilot.pause()
        lv = app.query_one("#search-list", NavListView)
        lv.focus()
        lv.index = 1
        await pilot.press("k")
        await pilot.pause()
        assert app.focused is lv
        assert lv.index == 0
        await pilot.press("k")
        await pilot.pause()
        assert app.focused is not None and app.focused.id == "search-input"
        lv.focus()
        lv.index = 1
        await pilot.press("j")
        await pilot.pause()
        assert app.focused is lv
        assert lv.index == 1
        lv.index = 0
        await pilot.press("up")
        await pilot.pause()
        assert app.focused is not None and app.focused.id == "search-input"


@pytest.mark.asyncio
async def test_search_esc_from_query_restores_committed_and_focuses_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_home: None
) -> None:
    monkeypatch.setenv("YT_COLLATE_CONFIG", str(tmp_path / "cfg"))
    app = YtCollateApp()
    song = CatalogItem(
        kind="song",
        title="S1",
        track=Track(video_id="v1", title="S1", artists=[Artist(name="A")]),
    )
    async with app.run_test(size=(120, 40)) as pilot:
        await app.show_view(SearchScreen(), "search")
        await pilot.pause()
        inp = app.query_one("#search-input", Input)
        inp.value = "original"
        app.query_one(SearchScreen)._show_results([song, song], query="original")
        await pilot.pause()
        inp.focus()
        inp.value = "edited but not entered"
        await pilot.press("escape")
        await pilot.pause()
        assert inp.value == "original"
        lv = app.query_one("#search-list", NavListView)
        assert app.focused is lv
        assert lv.index == 0

        inp.focus()
        inp.value = "another edit"
        await pilot.press("q")
        await pilot.pause()
        assert inp.value == "original"
        assert app.focused is lv
        assert lv.index == 0

        inp.focus()
        inp.value = "down edit"
        await pilot.press("down")
        await pilot.pause()
        assert inp.value == "original"
        assert app.focused is lv
        assert lv.index == 0


@pytest.mark.asyncio
async def test_search_keeps_results_after_leaving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_home: None
) -> None:
    monkeypatch.setenv("YT_COLLATE_CONFIG", str(tmp_path / "cfg"))
    app = YtCollateApp()
    song = CatalogItem(
        kind="song",
        title="Believer",
        track=Track(video_id="v1", title="Believer", artists=[Artist(name="Imagine Dragons")]),
    )
    async with app.run_test(size=(120, 40)) as pilot:
        await app.show_search()
        await pilot.pause()
        screen = app.query_one(SearchScreen)
        screen._show_results([song], query="believer")
        await pilot.pause()
        await app.show_library()
        await pilot.pause()
        await app.show_search()
        await pilot.pause()
        restored = app.query_one(SearchScreen)
        assert restored is screen
        inp = app.query_one("#search-input", Input)
        assert inp.value == "believer"
        assert restored._committed_query == "believer"
        lv = app.query_one("#search-list", NavListView)
        assert lv.display is True
        assert lv.option_count == 1
        assert app.focused is lv


@pytest.mark.asyncio
async def test_filter_down_keeps_query_and_focuses_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_home: None
) -> None:
    monkeypatch.setenv("YT_COLLATE_CONFIG", str(tmp_path / "cfg"))
    app = YtCollateApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        sidebar = app.query_one("#sidebar-list", NavListView)
        sidebar.focus()
        settings_idx = next(
            i for i, o in enumerate(sidebar.options) if o.id == "nav-settings"
        )
        sidebar.index = settings_idx
        await pilot.press("slash")
        await pilot.pause()
        filt = app.query_one("#sidebar Input.panel-filter", Input)
        assert app.focused is filt
        await pilot.press("s")
        await pilot.pause()
        await pilot.press("down")
        await pilot.pause()
        assert app.focused is sidebar
        assert filt.value == "s"
        assert filt.display is True
        opt = sidebar.highlighted_option
        assert opt is not None and opt.id == "nav-search"


@pytest.mark.asyncio
async def test_filter_down_on_empty_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_home: None
) -> None:
    monkeypatch.setenv("YT_COLLATE_CONFIG", str(tmp_path / "cfg"))
    app = YtCollateApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        sidebar = app.query_one("#sidebar-list", NavListView)
        sidebar.focus()
        await pilot.press("slash")
        await pilot.pause()
        filt = app.query_one("#sidebar Input.panel-filter", Input)
        await pilot.press("down")
        await pilot.pause()
        assert app.focused is sidebar
        assert filt.display is False


@pytest.mark.asyncio
async def test_settings_auth_down_focuses_next_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_home: None
) -> None:
    monkeypatch.setenv("YT_COLLATE_CONFIG", str(tmp_path / "cfg"))
    app = YtCollateApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await app.show_view(SettingsScreen(), "settings")
        await pilot.pause()
        screen = app.query_one(SettingsScreen)
        screen._start_auth_edit()
        await pilot.pause()
        inp = app.query_one("#auth-path", Input)
        assert app.focused is inp
        inp.value = "/tmp/not-saved.json"
        await pilot.press("down")
        await pilot.pause()
        assert screen._editing_auth is False
        lv = app.query_one("#settings-nav", NavListView)
        await pilot.pause()
        assert app.focused is lv
        assert lv.index == 1
        assert "Discord" in str(lv.highlighted_option.prompt)


@pytest.mark.asyncio
async def test_sidebar_fetching_while_explore_loads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_home: None
) -> None:
    release = threading.Event()

    def slow_explore(_self: object) -> list:
        release.wait(timeout=3)
        return []

    monkeypatch.setattr(
        "services.music.MusicService.get_explore",
        slow_explore,
    )
    monkeypatch.setenv("YT_COLLATE_CONFIG", str(tmp_path / "cfg"))
    app = YtCollateApp()
    async with app.run_test(size=(120, 40)) as pilot:
        sidebar = app.query_one(Sidebar)
        lv = app.query_one("#sidebar-list", NavListView)
        sidebar.set_fetching("explore")
        opt = next(o for o in lv.options if o.id == "nav-explore")
        assert "Fetching" in str(opt.prompt)
        sidebar.clear_fetching("explore")
        opt = next(o for o in lv.options if o.id == "nav-explore")
        assert "Fetching" not in str(opt.prompt)

        await app._navigate("explore")
        await pilot.pause()
        assert sidebar._fetching_key == "explore"
        opt = next(o for o in lv.options if o.id == "nav-explore")
        assert "Fetching" in str(opt.prompt)
        release.set()
        for _ in range(40):
            if sidebar._fetching_key is None:
                break
            await pilot.pause()
        assert sidebar._fetching_key is None
        opt = next(o for o in lv.options if o.id == "nav-explore")
        assert "Fetching" not in str(opt.prompt)


@pytest.mark.asyncio
async def test_home_fetching_on_startup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = threading.Event()

    def slow_home(_self: object, limit: int = 5) -> list:
        release.wait(timeout=3)
        return []

    monkeypatch.setattr(
        "services.music.MusicService.get_home",
        slow_home,
    )
    monkeypatch.setenv("YT_COLLATE_CONFIG", str(tmp_path / "cfg"))
    app = YtCollateApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        sidebar = app.query_one(Sidebar)
        lv = app.query_one("#sidebar-list", NavListView)
        assert sidebar._fetching_key == "home"
        opt = next(o for o in lv.options if o.id == "nav-home")
        assert "Fetching" in str(opt.prompt)
        release.set()
        for _ in range(40):
            if sidebar._fetching_key is None:
                break
            await pilot.pause()
        assert sidebar._fetching_key is None
        opt = next(o for o in lv.options if o.id == "nav-home")
        assert "Fetching" not in str(opt.prompt)


@pytest.mark.asyncio
async def test_trending_focuses_list_before_load(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_home: None
) -> None:
    release = threading.Event()

    def slow_charts(_self: object) -> list:
        release.wait(timeout=3)
        return []

    monkeypatch.setattr(
        "services.music.MusicService.get_charts_tracks",
        slow_charts,
    )
    monkeypatch.setattr(
        "services.music.MusicService.search_songs",
        lambda self, *a, **k: [],
    )
    monkeypatch.setenv("YT_COLLATE_CONFIG", str(tmp_path / "cfg"))
    app = YtCollateApp()
    async with app.run_test(size=(120, 40)) as pilot:
        await app._navigate("trending")
        await pilot.pause()
        assert app.focused is not None
        assert app.focused.id == "disc-results"
        release.set()


@pytest.mark.asyncio
async def test_library_mark_prefix_and_plus_not_volume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_home: None
) -> None:
    from models.track import PlaylistSummary
    from screens.library import library_num_prefix

    assert library_num_prefix(12, marked=True) == "12* "
    assert library_num_prefix(12, marked=False) == "12. "

    monkeypatch.setattr(
        "services.music.MusicService.get_library_playlists",
        lambda self, limit=100, show_episodes_for_later=True: [
            PlaylistSummary(playlist_id="PLreal", title="Real Mix", track_count=3)
        ],
    )
    monkeypatch.setenv("YT_COLLATE_CONFIG", str(tmp_path / "cfg"))
    app = YtCollateApp()
    async with app.run_test(size=(120, 40)) as pilot:
        vol = app.state.player.volume
        await pilot.press("plus")
        await pilot.pause()
        assert app.state.player.volume == vol

        app.state.music._authenticated = True
        await app.show_library()
        screen = app.query_one(LibraryScreen)
        for _ in range(40):
            if screen._loaded:
                break
            await pilot.pause()
        assert screen._loaded
        lv = app.query_one("#lib-list", NavListView)
        lv.focus()
        await pilot.pause()
        await pilot.press("m")
        await pilot.pause()
        assert app.state.library_mark is not None
        assert app.state.library_mark.playlist_id == "PLreal"
        prompt = str(lv.highlighted_option.prompt)
        assert prompt.startswith("1* ")
        assert "— marked" in prompt
        assert " · " not in prompt.split("— marked")[0]
        assert "(Fetching...)" not in prompt

        await pilot.press("m")
        await pilot.pause()
        assert app.state.library_mark is None
        prompt = str(lv.highlighted_option.prompt)
        assert prompt.startswith("1. ")
        assert "— marked" not in prompt

        await pilot.press("j")
        await pilot.pause()
        await pilot.press("m")
        await pilot.pause()
        assert app.state.library_mark is not None
        assert app.state.library_mark.kind == "saved"
        prompt = str(lv.highlighted_option.prompt)
        assert prompt.startswith("2* ")
        assert prompt.rstrip().endswith("— marked")

        song = Track(video_id="v1", title="Believer", artists=[Artist(name="A")])
        next_song = Track(video_id="v2", title="Next", artists=[Artist(name="B")])
        added: list[tuple[str, str]] = []
        toasts: list[tuple[str, str | None, str]] = []

        def fake_add(self, track, target):  # noqa: ANN001
            added.append((track.video_id, target.kind))
            from services.music import AddResult

            return AddResult(True, f"Added to {target.title}: {track.title}")

        def capture_notify(
            self, message: str, *, title: str = "", severity: str = "information", **kwargs
        ) -> None:
            toasts.append((message, severity, title))

        monkeypatch.setattr(
            "services.music.MusicService.add_song_to_target",
            fake_add,
        )
        monkeypatch.setattr(type(app), "notify", capture_notify)
        await app.show_view(HistoryScreen(), "history")
        await pilot.pause()
        app.state.queue.play_all([song, next_song], start_index=0)
        app._on_state_change()
        await pilot.pause()
        qlist = app.query_one("#queue-list", TrackList)
        qlist.focus()
        qlist.index = 0
        await pilot.pause()
        saved_mark = app.state.library_mark
        app.state.library_mark = None
        await pilot.press("plus")
        await pilot.pause()
        assert added == []
        assert toasts[-1][1] == "warning"
        assert "Mark (m)" in toasts[-1][0]
        assert qlist.index == 0
        app.state.library_mark = saved_mark
        vol = app.state.player.volume
        await pilot.press("plus")
        assert qlist.index == 1
        for _ in range(20):
            if added:
                break
            await pilot.pause()
        assert added == [("v1", "saved")]
        assert any(t[1] == "information" and "Added to" in t[0] for t in toasts)
        assert app.state.player.volume == vol
        assert qlist.index == 1


@pytest.mark.asyncio
async def test_library_marked_before_fetching(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_home: None
) -> None:
    from models.track import PlaylistSummary

    release = threading.Event()

    def slow_tracks(_self: object, playlist_id: str, limit: int = 200) -> list[Track]:
        release.wait(timeout=3)
        return []

    monkeypatch.setattr(
        "services.music.MusicService.get_library_playlists",
        lambda self, limit=100, show_episodes_for_later=True: [
            PlaylistSummary(playlist_id="PLreal", title="Real Mix", track_count=3)
        ],
    )
    monkeypatch.setattr(
        "services.music.MusicService.get_collection_tracks",
        slow_tracks,
    )
    monkeypatch.setenv("YT_COLLATE_CONFIG", str(tmp_path / "cfg"))
    app = YtCollateApp()
    async with app.run_test(size=(120, 40)) as pilot:
        app.state.music._authenticated = True
        await app.show_library()
        screen = app.query_one(LibraryScreen)
        for _ in range(40):
            if screen._loaded:
                break
            await pilot.pause()
        lv = app.query_one("#lib-list", NavListView)
        lv.focus()
        await pilot.pause()
        await pilot.press("m")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        prompt = str(lv.highlighted_option.prompt)
        assert "— marked (Fetching...)" in prompt
        release.set()
        for _ in range(40):
            if not screen._opening:
                break
            await pilot.pause()


@pytest.mark.asyncio
async def test_library_delete_keeps_focus_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_home: None
) -> None:
    from models.track import PlaylistSummary

    songs = [
        Track(video_id="a", title="One", artists=[Artist(name="A")]),
        Track(video_id="b", title="Two", artists=[Artist(name="A")]),
        Track(video_id="c", title="Three", artists=[Artist(name="A")]),
    ]
    monkeypatch.setattr(
        "services.music.MusicService.get_library_playlists",
        lambda self, limit=100, show_episodes_for_later=True: [
            PlaylistSummary(playlist_id="PLreal", title="Real Mix", track_count=3)
        ],
    )
    monkeypatch.setattr(
        "services.music.MusicService.get_collection_tracks",
        lambda self, playlist_id, limit=200: list(songs),
    )
    monkeypatch.setenv("YT_COLLATE_CONFIG", str(tmp_path / "cfg"))
    app = YtCollateApp()
    async with app.run_test(size=(120, 40)) as pilot:
        app.state.music._authenticated = True
        await app.show_library()
        screen = app.query_one(LibraryScreen)
        for _ in range(40):
            if screen._loaded:
                break
            await pilot.pause()
        lv = app.query_one("#lib-list", NavListView)
        lv.focus()
        await pilot.pause()
        await pilot.press("enter")
        for _ in range(40):
            if screen._drilled:
                break
            await pilot.pause()
        tv = app.query_one("#lib-tracks", TrackList)
        assert [t.video_id for t in tv.tracks] == ["a", "b", "c"]

        tv.index = 1
        screen.drop_track("b")
        assert [t.video_id for t in tv.tracks] == ["a", "c"]
        assert tv.index == 1

        screen.restore_track(songs[1], 1)
        assert [t.video_id for t in tv.tracks] == ["a", "b", "c"]
        assert tv.index == 2

        tv.index = 1
        screen.drop_track("b")
        screen.drop_track("c")
        assert [t.video_id for t in tv.tracks] == ["a"]
        assert tv.index == 0


@pytest.mark.asyncio
async def test_library_compose_playlist_and_refetch_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_home: None
) -> None:
    from models.track import PlaylistSummary
    from services.music import PlaylistWriteResult

    library = [PlaylistSummary(playlist_id="PLold", title="Old Mix", track_count=1)]

    def fake_get(self, limit=100, show_episodes_for_later=True):  # noqa: ANN001
        return list(library)

    def fake_create(self, title: str) -> PlaylistWriteResult:  # noqa: ANN001
        library.insert(
            0, PlaylistSummary(playlist_id="PLnew", title=title, track_count=0)
        )
        return PlaylistWriteResult(True, f"Created playlist: {title}", playlist_id="PLnew")

    monkeypatch.setattr(
        "services.music.MusicService.get_library_playlists",
        fake_get,
    )
    monkeypatch.setattr(
        "services.music.MusicService.create_playlist",
        fake_create,
    )
    monkeypatch.setenv("YT_COLLATE_CONFIG", str(tmp_path / "cfg"))
    app = YtCollateApp()
    async with app.run_test(size=(120, 40)) as pilot:
        app.state.music._authenticated = True
        await app.show_library()
        screen = app.query_one(LibraryScreen)
        for _ in range(40):
            if screen._loaded:
                break
            await pilot.pause()
        lv = app.query_one("#lib-list", NavListView)
        lv.focus()
        await pilot.pause()
        await pilot.press("o")
        await pilot.pause()
        assert screen._composing
        assert app.query_one("#lib-compose", Horizontal).display is True
        numbered = sum(1 for row in screen._rows if row.kind != "section")
        assert numbered == 3
        inp = app.query_one("#lib-compose-name", Input)
        assert app.focused is inp
        await pilot.press("n", "e", "w")
        await pilot.pause()
        assert inp.value == "new"
        await pilot.press("enter")
        for _ in range(40):
            if not screen._composing and any(
                row.playlist and row.playlist.playlist_id == "PLnew" for row in screen._rows
            ):
                break
            await pilot.pause()
        assert not screen._composing
        ids = [
            row.playlist.playlist_id
            for row in screen._rows
            if row.playlist is not None
        ]
        assert ids[:2] == ["PLnew", "PLold"]
        assert lv.index == 0


@pytest.mark.asyncio
async def test_library_delete_playlist_always_confirms(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stub_home: None
) -> None:
    from models.track import PlaylistSummary
    from services.music import PlaylistWriteResult

    monkeypatch.setattr(
        "services.music.MusicService.get_library_playlists",
        lambda self, limit=100, show_episodes_for_later=True: [
            PlaylistSummary(playlist_id="PLreal", title="Real Mix", track_count=3),
            PlaylistSummary(playlist_id="PLtwo", title="Second", track_count=1),
        ],
    )
    deleted: list[str] = []

    def fake_delete(self, playlist):  # noqa: ANN001
        deleted.append(playlist.playlist_id)
        return PlaylistWriteResult(
            True, f'Deleted playlist "{playlist.title}"', playlist_id=playlist.playlist_id
        )

    monkeypatch.setattr(
        "services.music.MusicService.delete_playlist",
        fake_delete,
    )
    monkeypatch.setenv("YT_COLLATE_CONFIG", str(tmp_path / "cfg"))
    app = YtCollateApp()
    async with app.run_test(size=(120, 40)) as pilot:
        app.state.config.update(confirm_delete=False)
        app.state.music._authenticated = True
        await app.show_library()
        screen = app.query_one(LibraryScreen)
        for _ in range(40):
            if screen._loaded:
                break
            await pilot.pause()
        lv = app.query_one("#lib-list", NavListView)
        lv.focus()
        await pilot.pause()
        toasts: list[str] = []

        def capture_notify(
            self, message: str, *, title: str = "", severity: str = "information", **kwargs
        ) -> None:
            toasts.append(message)

        monkeypatch.setattr(type(app), "notify", capture_notify)
        await pilot.press("d")
        await pilot.pause()
        assert deleted == []
        assert app._pending_delete is not None
        assert app._pending_delete.playlist is not None
        assert any("Delete playlist" in msg for msg in toasts)

        await pilot.press("enter")
        for _ in range(40):
            if deleted:
                break
            await pilot.pause()
        assert deleted == ["PLreal"]
        ids = [
            row.playlist.playlist_id
            for row in screen._rows
            if row.playlist is not None
        ]
        assert ids[0] == "PLtwo"
        assert lv.index == 0

        lv.index = next(
            i
            for i, row in enumerate(screen._rows)
            if row.playlist and row.playlist.title == "Saved Songs"
        )
        lv.focus()
        await pilot.pause()
        toasts.clear()
        await pilot.press("d")
        await pilot.pause()
        assert deleted == ["PLreal"]
        assert any("cannot be deleted" in msg for msg in toasts)
