# yt-collate

A Terminal User Interface (TUI) music player for YouTube Music.

Originally planned to only focus on gathering/arranging tracks in playlists, Collate has become a full-fledged music client rivaling the ease-of-use of GUI clients while requiring only a fraction of their resources usage.

Built with **Textual**, **ytmusicapi**, **mpv**, and **yt-dlp**. Keybinds are a mix of Vim binds and general binds. Collate is inspired by youtube-music-cli and yazi; check them out!

## Prerequisites

- Python 3.12+
- [mpv](https://mpv.io/)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) (nightly; yt-dlp --update-to nightly)

## Install

```bash
uv sync
uv run yt-collate
```

Short alias: `uv run ytc`.

## Features

- Clean, minimalistic, fullscreen TUI client for YouTube Music
- Extremeley fast, lightweight, and responsive
- Authentication to access your Library and personalized recommendations
- Includes YouTube Music Home, Explore, Search, and Trending pages
- Download songs/playlists to local / Automatic audio retrieval from local
- Smooth playback experience, with a simple dynamic queue
- Vast set of intuitive keybinds (e.g. `n` for next track, `s` to shuffle, etc.)
- Easy management of Library (e.g. `o` to create playlist, `x` to delete song/playlist, etc.)
- "Marking" playlists to easily add to collection from anywhere
- YouTube Music subscribers benefit from enhanced audio bitrate (both streams and downloads)
- Discord Rich Presence integration

## Distinct Touches

- Has Vim's "unnamed register" for `x` (cut), `y` (yank), and `p` (put/paste) for songs
- `0-9` keys jump around current track, imitating YouTube's playback keybinds
- Audio bitrate indicator, originally added to verify enhanced premium bitrate
- Local filter `/` can jump to line numbers, allowing fast gotos
- Search screen accepts YouTube URLs, useful if you prefer exploring YouTube on a browser (me)
- Option to hide "Episodes for Later" in Library, I'm sure many find this annoying (me)
- Global queue; queue is never tied to a specific playlist; `i/a` adds to 

## Usage

Collate uses browser headers to authenticate since OAuth2 currently fails (link sigma67 thing). Follow the steps HERE to create your auth headers file (any POST request should work); do it from a private/incognito window or your cookie might only last a few hours. Supply this file in Settings.

Navigating with keys should be intuitive (hjkl supported); mouse is supported as well. 

Press `?` to view list of all keybinds.

## Config

Data lives under `~/.config/yt-collate/` (override with `YT_COLLATE_CONFIG`). Downloads appear in `~/Music/yt-collate`.

## Development

Contributions are welcome! As a start, consider adding your favorite genre to `GENRES` in `src/services/random_song.py`

```bash
uv sync --group dev
uv run pytest
uv run ruff check .
```
