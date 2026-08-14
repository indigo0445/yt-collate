"""MusicService normalization tests."""

from __future__ import annotations

from yt_collate.services.music import track_from_song


def test_track_from_song_basic() -> None:
    track = track_from_song(
        {
            "videoId": "abc",
            "title": "Indigo Night",
            "artists": [{"name": "Tamino", "id": "x"}],
            "duration": "4:14",
            "thumbnails": [{"url": "http://img"}],
            "album": {"name": "Amir", "id": "MPREb_amir"},
            "feedbackTokens": {"add": "tok_add", "remove": "tok_rm"},
            "setVideoId": "set_abc",
            "likeStatus": "INDIFFERENT",
            "inLibrary": False,
        }
    )
    assert track is not None
    assert track.video_id == "abc"
    assert track.title == "Indigo Night"
    assert track.artist_str == "Tamino"
    assert track.duration == 254
    assert track.watch_url == "https://music.youtube.com/watch?v=abc"
    assert track.album == "Amir"
    assert track.album_id == "MPREb_amir"
    assert track.library_add_token == "tok_add"
    assert track.library_remove_token == "tok_rm"
    assert track.set_video_id == "set_abc"
    assert track.like_status == "INDIFFERENT"
    assert track.in_library is False
    assert track.is_video is False


def test_track_from_song_missing_id() -> None:
    assert track_from_song({"title": "Nope"}) is None


def test_track_from_song_rejects_non_dict() -> None:
    assert track_from_song("not-a-track") is None
    assert track_from_song(None) is None


class _FakeExploreClient:
    def __init__(self, explore: dict) -> None:
        self.explore = explore

    def get_explore(self) -> dict:
        return self.explore


def test_get_explore_builds_shelves() -> None:
    from yt_collate.services.music import MusicService

    music = MusicService()
    music._yt = _FakeExploreClient(
        {
            "new_releases": [
                {"title": "Hangang", "browseId": "MPREb_album", "type": "Album"},
            ],
            "new_videos": [
                {"videoId": "nv1", "title": "New Vid", "artists": [{"name": "DJ"}]},
            ],
            "trending": {
                "playlist": "VLOLxxx",
                "items": [
                    {
                        "title": "Permission to Dance",
                        "videoId": "CuklIb9d3fI",
                        "artists": [{"name": "BTS"}],
                    }
                ],
            },
            "moods_and_genres": [
                {"title": "Chill", "params": "ggMPOg1uXzVuc0dnZlhpV3Ba"},
            ],
        }
    )
    shelves = music.get_explore()
    titles = [s.title for s in shelves]
    assert titles == ["New albums", "New music videos", "Trending", "Moods & genres"]
    assert shelves[0].items[0].kind == "album"
    assert shelves[0].items[0].browse_id == "MPREb_album"
    assert shelves[1].items[0].kind == "song"
    assert shelves[1].items[0].track is not None
    assert shelves[1].items[0].track.video_id == "nv1"
    assert shelves[3].items[0].kind == "mood"
    assert shelves[3].items[0].params == "ggMPOg1uXzVuc0dnZlhpV3Ba"


def test_catalog_item_classifies_mixed_row() -> None:
    from yt_collate.services.music import catalog_item_from_content

    song = catalog_item_from_content(
        {
            "title": "Gravity",
            "videoId": "EludZd6lfts",
            "artists": [{"name": "yetep", "id": "x"}],
        }
    )
    assert song is not None and song.kind == "song" and song.track is not None
    assert song.track.video_id == "EludZd6lfts"

    album = catalog_item_from_content(
        {"title": "Sentiment", "browseId": "MPREb_QtqXtd2xZMR"}
    )
    assert album is not None and album.kind == "album"
    assert album.browse_id == "MPREb_QtqXtd2xZMR"

    playlist = catalog_item_from_content(
        {
            "title": "r/EDM",
            "playlistId": "PLz7-xrYmULdSLRZGk-6GKUtaBZcgQNwel",
            "description": "redditEDM • 161 songs",
        }
    )
    assert playlist is not None and playlist.kind == "playlist"
    assert playlist.playlist_id.startswith("PL")

    artist = catalog_item_from_content(
        {
            "title": "Chill Satellite",
            "browseId": "UCrPLFBWdOroD57bkqPbZJog",
            "subscribers": "374",
        }
    )
    assert artist is not None and artist.kind == "artist"
    assert artist.subtitle == "374"

    mood = catalog_item_from_content(
        {"title": "Chill", "params": "ggMPOg1uXzVuc0dnZlhpV3Ba"}
    )
    assert mood is not None and mood.kind == "mood"
    assert mood.params == "ggMPOg1uXzVuc0dnZlhpV3Ba"

    from_search = catalog_item_from_content(
        {
            "artist": "Imagine Dragons",
            "browseId": "UCT9zcQNlyZm7ZKsI1b6yLzA",
            "resultType": "artist",
            "subscribers": "41.8M",
        }
    )
    assert from_search is not None and from_search.kind == "artist"
    assert from_search.title == "Imagine Dragons"


def test_get_home_and_home_tracks() -> None:
    from yt_collate.services.music import MusicService

    class FakeHome:
        def get_home(self, limit: int = 5) -> list:
            assert limit == 5
            return [
                {
                    "title": "Your morning music",
                    "contents": [
                        {"title": "Sentiment", "browseId": "MPREb_QtqXtd2xZMR"},
                        {
                            "title": "r/EDM",
                            "playlistId": "PLz7-xrYmULdSLRZGk-6GKUtaBZcgQNwel",
                        },
                    ],
                },
                {
                    "title": "Quick picks",
                    "contents": [
                        {
                            "title": "Gravity",
                            "videoId": "EludZd6lfts",
                            "artists": [{"name": "yetep"}],
                        }
                    ],
                },
            ]

    music = MusicService()
    music._yt = FakeHome()
    shelves = music.get_home(limit=5)
    assert [s.title for s in shelves] == ["Your morning music", "Quick picks"]
    assert [i.kind for i in shelves[0].items] == ["album", "playlist"]
    assert [t.video_id for t in music.get_home_tracks(limit=5)] == ["EludZd6lfts"]


def test_anonymous_skips_history_api() -> None:
    from yt_collate.models.music import Artist, Track
    from yt_collate.services.music import MusicService

    class Forbidden:
        def get_history(self) -> list:
            raise AssertionError("get_history must not be called when anonymous")

        def get_song(self, video_id: str) -> dict:
            raise AssertionError("get_song must not be called when anonymous")

        def add_history_item(self, song: dict) -> None:
            raise AssertionError("add_history_item must not be called when anonymous")

    music = MusicService()
    music._authenticated = False
    music._yt = Forbidden()
    assert music.get_history() == []
    music.add_history_item(
        Track(video_id="abc", title="T", artists=[Artist(name="A")])
    )


def test_get_history_collapses_consecutive_and_add_uses_same_client() -> None:
    from yt_collate.models.music import Artist, Track
    from yt_collate.services.music import MusicService

    class FakeHistory:
        def __init__(self) -> None:
            self.songs: list[str] = []
            self.added: list[object] = []

        def get_history(self) -> list:
            return [
                {"videoId": "a", "title": "A", "artists": [{"name": "X"}]},
                {"videoId": "a", "title": "A", "artists": [{"name": "X"}]},
                {"videoId": "b", "title": "B", "artists": [{"name": "Y"}]},
            ]

        def get_song(self, video_id: str) -> dict:
            self.songs.append(video_id)
            return {"videoId": video_id}

        def add_history_item(self, song: dict) -> None:
            self.added.append(song)

    music = MusicService()
    music._authenticated = True
    client = FakeHistory()
    music._yt = client
    tracks = music.get_history(limit=10)
    assert [t.video_id for t in tracks] == ["a", "b"]
    music.add_history_item(Track(video_id="a", title="A", artists=[Artist(name="X")]))
    assert client.songs == ["a"]
    assert client.added == [{"videoId": "a"}]


def test_get_library_playlists_skips_liked_music_row() -> None:
    from yt_collate.services.music import (
        LIKED_PLAYLIST_ID,
        SAVED_SONGS_PLAYLIST_ID,
        MusicService,
    )

    class FakeLib:
        def get_library_playlists(self, limit: int = 50) -> list:
            return [
                {"playlistId": "LM", "title": "Liked Music"},
                {"playlistId": "PLreal", "title": "Real Mix", "count": 3},
            ]

        def get_liked_songs(self, limit: int = 100) -> dict:
            return {
                "tracks": [
                    {"videoId": "like1", "title": "Heart", "artists": [{"name": "A"}]}
                ]
            }

        def get_library_songs(self, limit: int = 50) -> list:
            return [{"videoId": "saved1", "title": "Kept", "artists": [{"name": "C"}]}]

        def get_playlist(self, playlist_id: str, limit: int = 100) -> dict:
            return {"tracks": [{"videoId": "p1", "title": "P", "artists": [{"name": "B"}]}]}

    music = MusicService()
    music._authenticated = True
    music._yt = FakeLib()
    playlists = music.get_library_playlists()
    assert [p.playlist_id for p in playlists] == ["PLreal"]
    liked = music.get_collection_tracks(LIKED_PLAYLIST_ID)
    assert [t.video_id for t in liked] == ["like1"]
    saved = music.get_collection_tracks(SAVED_SONGS_PLAYLIST_ID)
    assert [t.video_id for t in saved] == ["saved1"]
    normal = music.get_collection_tracks("PLreal")
    assert [t.video_id for t in normal] == ["p1"]


def test_get_library_playlists_hides_episodes_for_later() -> None:
    from yt_collate.services.music import MusicService

    class FakeLib:
        def get_library_playlists(self, limit: int = 50) -> list:
            return [
                {"playlistId": "PLep", "title": "Episodes for Later"},
                {"playlistId": "PLreal", "title": "Real Mix"},
            ]

    music = MusicService()
    music._authenticated = True
    music._yt = FakeLib()
    hidden = music.get_library_playlists(show_episodes_for_later=False)
    assert [p.playlist_id for p in hidden] == ["PLreal"]
    shown = music.get_library_playlists(show_episodes_for_later=True)
    assert [p.playlist_id for p in shown] == ["PLep", "PLreal"]


def test_library_target_for_kinds() -> None:
    from yt_collate.models.music import PlaylistSummary
    from yt_collate.services.music import (
        LIKED_PLAYLIST_ID,
        SAVED_SONGS_PLAYLIST_ID,
        is_user_playlist,
        library_target_for,
    )

    pl = library_target_for(PlaylistSummary(playlist_id="PLreal", title="Mix"))
    assert pl is not None and pl.kind == "playlist"
    saved = library_target_for(
        PlaylistSummary(playlist_id=SAVED_SONGS_PLAYLIST_ID, title="Saved Songs")
    )
    assert saved is not None and saved.kind == "saved"
    liked = library_target_for(
        PlaylistSummary(playlist_id=LIKED_PLAYLIST_ID, title="Liked Songs")
    )
    assert liked is not None and liked.kind == "liked"
    assert (
        library_target_for(
            PlaylistSummary(playlist_id="PLep", title="Episodes for Later")
        )
        is None
    )
    assert is_user_playlist(PlaylistSummary(playlist_id="PLreal", title="Mix"))
    assert not is_user_playlist(
        PlaylistSummary(playlist_id=SAVED_SONGS_PLAYLIST_ID, title="Saved Songs")
    )
    assert not is_user_playlist(
        PlaylistSummary(playlist_id=LIKED_PLAYLIST_ID, title="Liked Songs")
    )
    assert not is_user_playlist(
        PlaylistSummary(playlist_id="PLep", title="Episodes for Later")
    )


def test_add_song_to_target_routes() -> None:
    from yt_collate.models.music import Artist, Track
    from yt_collate.services.music import (
        LIKED_PLAYLIST_ID,
        SAVED_SONGS_PLAYLIST_ID,
        LibraryTarget,
        MusicService,
    )
    from ytmusicapi.models.content.enums import LikeStatus

    class FakeAdd:
        def __init__(self) -> None:
            self.saved: list[list[str]] = []
            self.liked: list[tuple[str, object]] = []
            self.playlists: list[tuple[str, list[str], bool]] = []
            self.watch_calls = 0

        def edit_song_library_status(self, tokens: list[str]) -> dict:
            self.saved.append(tokens)
            return {}

        def rate_song(self, video_id: str, rating: object) -> dict:
            self.liked.append((video_id, rating))
            return {}

        def add_playlist_items(
            self,
            playlist_id: str,
            videoIds: list[str] | None = None,
            duplicates: bool = False,
        ) -> str:
            self.playlists.append((playlist_id, list(videoIds or []), duplicates))
            return "STATUS_SUCCEEDED"

        def get_watch_playlist(self, videoId: str, limit: int = 5) -> dict:
            self.watch_calls += 1
            return {
                "tracks": [
                    {
                        "videoId": videoId,
                        "feedbackTokens": {"add": "from_watch"},
                    }
                ]
            }

    music = MusicService()
    music._authenticated = True
    client = FakeAdd()
    music._yt = client
    song = Track(
        video_id="vid1",
        title="Song",
        artists=[Artist(name="A")],
        library_add_token="tok_add",
        in_library=False,
        like_status="INDIFFERENT",
    )
    assert (
        music.add_song_to_target(
            song, LibraryTarget("saved", SAVED_SONGS_PLAYLIST_ID, "Saved Songs")
        ).message
        == "Saved: Song"
    )
    assert client.saved == [["tok_add"]]
    assert client.watch_calls == 0

    no_token = Track(video_id="vid2", title="Need Token", artists=[Artist(name="A")])
    music.add_song_to_target(
        no_token, LibraryTarget("saved", SAVED_SONGS_PLAYLIST_ID, "Saved Songs")
    )
    assert client.saved[-1] == ["from_watch"]
    assert client.watch_calls == 1

    liked = music.add_song_to_target(
        song, LibraryTarget("liked", LIKED_PLAYLIST_ID, "Liked Songs")
    )
    assert liked.ok and liked.message == "Liked: Song"
    assert client.liked == [("vid1", LikeStatus.LIKE)]

    added = music.add_song_to_target(
        song, LibraryTarget("playlist", "PLreal", "Real Mix")
    )
    assert added.ok and added.message == "Added to Real Mix: Song"
    assert client.playlists == [("PLreal", ["vid1"], False)]


def test_add_song_to_target_requires_auth() -> None:
    from yt_collate.models.music import Artist, Track
    from yt_collate.services.music import LibraryTarget, MusicService

    music = MusicService()
    music._authenticated = False
    result = music.add_song_to_target(
        Track(video_id="v", title="T", artists=[Artist(name="A")]),
        LibraryTarget("liked", "__liked__", "Liked Songs"),
    )
    assert not result.ok
    assert result.reason == "error"
    assert "Sign in" in result.message


def test_add_to_playlist_duplicate_and_other_error() -> None:
    from yt_collate.models.music import Artist, Track
    from yt_collate.services.music import LibraryTarget, MusicService

    song = Track(video_id="vid1", title="Song", artists=[Artist(name="A")])
    target = LibraryTarget("playlist", "PLreal", "Real Mix")

    class DupClient:
        def add_playlist_items(self, playlist_id: str, videoIds=None, duplicates=False):
            assert duplicates is False
            return {"status": "FAILED", "error": "DUPLICATE_ITEM"}

    music = MusicService()
    music._authenticated = True
    music._yt = DupClient()
    dup = music.add_song_to_target(song, target)
    assert not dup.ok
    assert dup.reason == "duplicate"
    assert "Already in Real Mix" in dup.message

    class BoomClient:
        def add_playlist_items(self, playlist_id: str, videoIds=None, duplicates=False):
            raise RuntimeError("Server returned HTTP 400: Bad Request")

    music._yt = BoomClient()
    err = music.add_song_to_target(song, target)
    assert not err.ok
    assert err.reason == "error"
    assert "HTTP 400" in err.message


def test_liked_and_saved_duplicate() -> None:
    from yt_collate.models.music import Artist, Track
    from yt_collate.services.music import (
        LIKED_PLAYLIST_ID,
        SAVED_SONGS_PLAYLIST_ID,
        LibraryTarget,
        MusicService,
    )

    class Forbidden:
        def rate_song(self, *a, **k):
            raise AssertionError("should not like again")

        def edit_song_library_status(self, *a, **k):
            raise AssertionError("should not save again")

        def get_watch_playlist(self, videoId: str, limit: int = 5) -> dict:
            return {
                "tracks": [
                    {
                        "videoId": videoId,
                        "likeStatus": "LIKE",
                        "inLibrary": True,
                        "feedbackTokens": {"add": "tok", "remove": "rm"},
                    }
                ]
            }

    music = MusicService()
    music._authenticated = True
    music._yt = Forbidden()
    liked = music.add_song_to_target(
        Track(video_id="v1", title="Song", artists=[Artist(name="A")], like_status="LIKE"),
        LibraryTarget("liked", LIKED_PLAYLIST_ID, "Liked Songs"),
    )
    assert liked.reason == "duplicate"
    assert "Already in Liked Songs" in liked.message

    saved = music.add_song_to_target(
        Track(video_id="v1", title="Song", artists=[Artist(name="A")], in_library=True),
        LibraryTarget("saved", SAVED_SONGS_PLAYLIST_ID, "Saved Songs"),
    )
    assert saved.reason == "duplicate"
    assert "Already in Saved Songs" in saved.message

    from_watch = music.add_song_to_target(
        Track(video_id="v2", title="Other", artists=[Artist(name="A")]),
        LibraryTarget("liked", LIKED_PLAYLIST_ID, "Liked Songs"),
    )
    assert from_watch.reason == "duplicate"


def test_remove_song_from_target_routes() -> None:
    from yt_collate.models.music import Artist, Track
    from yt_collate.services.music import (
        LIKED_PLAYLIST_ID,
        SAVED_SONGS_PLAYLIST_ID,
        LibraryTarget,
        MusicService,
    )
    from ytmusicapi.models.content.enums import LikeStatus

    class FakeRemove:
        def __init__(self) -> None:
            self.removed: list[object] = []
            self.rated: list[tuple[str, object]] = []
            self.saved: list[list[str]] = []

        def remove_playlist_items(self, playlist_id: str, videos: list) -> str:
            self.removed.append((playlist_id, videos))
            return "STATUS_SUCCEEDED"

        def rate_song(self, video_id: str, rating: object) -> dict:
            self.rated.append((video_id, rating))
            return {}

        def edit_song_library_status(self, tokens: list[str]) -> dict:
            self.saved.append(tokens)
            return {}

    music = MusicService()
    music._authenticated = True
    client = FakeRemove()
    music._yt = client
    song = Track(
        video_id="vid1",
        title="Song",
        artists=[Artist(name="A")],
        set_video_id="set1",
        like_status="LIKE",
        in_library=True,
        library_remove_token="tok_rm",
    )
    pl = music.remove_song_from_target(
        song, LibraryTarget("playlist", "PLreal", "Real Mix")
    )
    assert pl.ok and "Deleted from Real Mix" in pl.message
    assert client.removed == [("PLreal", [{"videoId": "vid1", "setVideoId": "set1"}])]

    liked = music.remove_song_from_target(
        song, LibraryTarget("liked", LIKED_PLAYLIST_ID, "Liked Songs")
    )
    assert liked.ok and liked.message == "Unliked: Song"
    assert client.rated == [("vid1", LikeStatus.INDIFFERENT)]

    saved = music.remove_song_from_target(
        song, LibraryTarget("saved", SAVED_SONGS_PLAYLIST_ID, "Saved Songs")
    )
    assert saved.ok and "Removed from Saved Songs" in saved.message
    assert client.saved == [["tok_rm"]]

    missing = music.remove_song_from_target(
        Track(video_id="vid1", title="Song", artists=[Artist(name="A")]),
        LibraryTarget("playlist", "PLreal", "Real Mix"),
    )
    assert not missing.ok
    assert "Open this playlist" in missing.message

    class FakeGone:
        def remove_playlist_items(self, playlist_id: str, videos: list) -> None:
            raise Exception("Server returned HTTP 400: Bad Request.\nPrecondition check failed.")

    music._yt = FakeGone()
    gone = music.remove_song_from_target(
        song, LibraryTarget("playlist", "PLreal", "Real Mix")
    )
    assert gone.ok
    assert "Deleted from Real Mix" in gone.message


def test_create_and_delete_playlist() -> None:
    from yt_collate.models.music import PlaylistSummary
    from yt_collate.services.music import (
        LIKED_PLAYLIST_ID,
        SAVED_SONGS_PLAYLIST_ID,
        MusicService,
    )

    class FakePlaylists:
        def __init__(self) -> None:
            self.created: list[tuple[str, str, str]] = []
            self.deleted: list[str] = []

        def create_playlist(
            self,
            title: str,
            description: str,
            privacy_status: str = "PRIVATE",
        ) -> str:
            self.created.append((title, description, privacy_status))
            return "PLnew"

        def delete_playlist(self, playlistId: str) -> str:
            self.deleted.append(playlistId)
            return "STATUS_SUCCEEDED"

    music = MusicService()
    music._authenticated = True
    client = FakePlaylists()
    music._yt = client

    created = music.create_playlist("  Night Drive  ")
    assert created.ok and created.playlist_id == "PLnew"
    assert created.message == "Created playlist: Night Drive"
    assert client.created == [("Night Drive", "", "PRIVATE")]

    empty = music.create_playlist("   ")
    assert not empty.ok
    assert "name required" in empty.message.casefold()
    assert client.created == [("Night Drive", "", "PRIVATE")]

    deleted = music.delete_playlist(PlaylistSummary(playlist_id="PLreal", title="Mix"))
    assert deleted.ok and deleted.playlist_id == "PLreal"
    assert "Deleted playlist" in deleted.message
    assert client.deleted == ["PLreal"]

    saved = music.delete_playlist(
        PlaylistSummary(playlist_id=SAVED_SONGS_PLAYLIST_ID, title="Saved Songs")
    )
    assert not saved.ok
    assert "cannot be deleted" in saved.message
    liked = music.delete_playlist(
        PlaylistSummary(playlist_id=LIKED_PLAYLIST_ID, title="Liked Songs")
    )
    assert not liked.ok
    episodes = music.delete_playlist(
        PlaylistSummary(playlist_id="PLep", title="Episodes for Later")
    )
    assert not episodes.ok
    assert client.deleted == ["PLreal"]


def test_delete_playlist_innertube_payload_is_success() -> None:
    from yt_collate.models.music import PlaylistSummary
    from yt_collate.services.music import MusicService

    payload = {
        "responseContext": {"serviceTrackingParams": []},
        "actions": [
            {"handlePlaylistDeletionCommand": {"playlistId": "PLreal"}},
            {
                "removeFromGuideSectionAction": {
                    "handlerData": "GUIDE_ACTION_REMOVE_FROM_PLAYLISTS",
                    "guideEntryId": "PLreal",
                }
            },
        ],
    }

    class FakeDelete:
        def delete_playlist(self, playlistId: str) -> dict:
            return payload

    music = MusicService()
    music._authenticated = True
    music._yt = FakeDelete()
    result = music.delete_playlist(PlaylistSummary(playlist_id="PLreal", title="test list"))
    assert result.ok
    assert result.message == 'Deleted playlist "test list"'
    assert "responseContext" not in result.message


def test_delete_playlist_unknown_blob_is_short_error() -> None:
    from yt_collate.models.music import PlaylistSummary
    from yt_collate.services.music import MusicService

    class FakeDelete:
        def delete_playlist(self, playlistId: str) -> dict:
            return {"responseContext": {"visitorData": "x"}, "error": "nope"}

    music = MusicService()
    music._authenticated = True
    music._yt = FakeDelete()
    result = music.delete_playlist(PlaylistSummary(playlist_id="PLreal", title="test list"))
    assert not result.ok
    assert "responseContext" not in result.message
    assert "{" not in result.message
