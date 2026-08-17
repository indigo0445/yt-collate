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
- Authentication to access your Library and personalized recommendations
- Includes YouTube Music Home, Explore, Search, and Trending pages
- Download to local / Play from local
- Smooth playback experience, with a simple dynamic queue
- Vast set of intuitive keybinds (e.g. `/` for local filter, `0-9` to jump around track, etc.)
- Easy management of Library (e.g. o to create playlist, x/p to cut/paste tracks, etc.)
- "Marking" playlists to easily add to collection from anywhere
- YouTube Music subscribers benefit from enhanced audio bitrate (both streams and downloads)
- Discord Rich Presence (`uv sync --extra discord`)
- Extremeley lightweight; consistently under 100MB RAM

## Usage

Collate uses browser headers to authenticate since OAuth2 currently fails (link sigma67 thing). Follow the steps HERE to create your auth headers file (any POST request should work); do it from a private/incognito window or your cookie might only last a few hours. Supply this file in Settings.

Navigating with keys should be intuitive (hjkl supported); mouse is supported as well. 

Press `?` to view list of all keybinds.

## Config

Data lives under `~/.config/yt-collate/` (override with `YT_COLLATE_CONFIG`). Downloads appear in `~/Music/yt-collate`.

## Development

Contributions are welcome! 

```bash
uv sync --group dev
uv run pytest
uv run ruff check .
```
