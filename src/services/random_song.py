"""pick a somewhat-random catalog song via a generated search query"""

from __future__ import annotations

import random

from models.track import Track
from services.music import MusicService

GENRES = [
    "pop",
    "rock",
    "metal",
    "hip hop",
    "electronic",
    "country",
    "classical",
    "jazz",
    "soul",
    "folk",
    "acoustic",
    "psytrance",
    "breakcore",
    "dreamcore",
    "tech",
    "vaporwave",
    "hardcore",
]

EXTENSIONS = [
    "songs",
    "vibes",
    "bangers",
    "hits",
    "classics",
    "indie",
    "mixes",
    "remixes",
    "covers",
    "live",
]

YEARS = [str(year) for year in range(1980, 2026)]


def random_query() -> str:
    return f"{random.choice(GENRES)} {random.choice(EXTENSIONS)} {random.choice(YEARS)}"


def pick_random_song(music: MusicService, *, limit: int = 20) -> Track | None:
    tracks = music.search_songs(random_query(), limit=limit)
    if not tracks:
        return None
    return random.choice(tracks)
