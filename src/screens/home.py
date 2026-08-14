"""Home — start page: YouTube Music home shelves"""

from screens.catalog import CatalogScreen


class HomeScreen(CatalogScreen):
    PREFIX = "home"
    TITLE = "🏠 Home"
    EMPTY = "No home suggestions"

    def fetch_shelves(self):
        return self.app.state.music.get_home(limit=5)  # type: ignore[attr-defined]
