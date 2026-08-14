"""Explore — new albums, videos, trending, top songs, moods."""

from yt_collate.screens.catalog import CatalogScreen


class ExploreScreen(CatalogScreen):
    PREFIX = "explore"
    TITLE = "🧭 Explore"
    EMPTY = "No explore suggestions"

    def fetch_shelves(self):
        return self.app.state.music.get_explore()  # type: ignore[attr-defined]
