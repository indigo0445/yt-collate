# yt-collate

A Terminal User Interface music player for YouTube Music, developed for Linux (likely compatible with Mac; untested yet, don't have Mac).

Originally planned to only focus on gathering/arranging tracks in playlists (hence name), Collate has become a full-fledged music client rivaling the ease-of-use of GUI clients while requiring only a fraction of their resources usage.

Built with **Textual**, **ytmusicapi**, **mpv**, and **yt-dlp**. Keybinds are a mix of Vim binds and general binds for efficient keyboard-only navigation. Collate is inspired by [youtube-music-cli](https://github.com/involvex/youtube-music-cli) and [yazi](https://github.com/sxyazi/yazi); check them out!

![Home](https://raw.githubusercontent.com/indigo0445/yt-collate/refs/heads/main/assets/home.png)

## Prerequisites

- Python 3.12+
- [mpv](https://mpv.io/)
- [yt-dlp (nightly build)](https://github.com/yt-dlp/yt-dlp-nightly-builds) (Certain non-music videos will not play on stable build. Can run `yt-dlp --update-to nightly`)
- [Deno](https://deno.com/) or [Node](https://nodejs.org/) or [QuickJS](https://bellard.org/quickjs/) (A JS runtime is needed for yt-dlp to [reliably fetch](https://github.com/yt-dlp/yt-dlp/wiki/ejs))

## Install

```bash
uv sync
uv run yt-collate
```

## Features

- Clean, minimalistic, fullscreen TUI client for YouTube Music
- Authentication to access your Library and personalized recommendations
- Includes YouTube Music Home, Explore, Search, and Trending pages
- Smooth playback experience, with a simple dynamic queue
- Download songs/playlists to local / Automatic audio retrieval from local
- Vast set of intuitive keybinds (e.g. `n` for next track, `d` to download, etc.)
- Easy management of Library (e.g. `o` to create playlist, `x` to delete song/playlist, etc.)
- "Marking" playlists to easily add to collection from anywhere
- YouTube Music subscribers benefit from enhanced audio bitrate (both streams and downloads)
- Discord Rich Presence integration
- Extremeley fast, lightweight, and responsive

![Library playlist](https://raw.githubusercontent.com/indigo0445/yt-collate/refs/heads/main/assets/playlist.png)

## Distinct Touches

- Has Vim's "unnamed register" for `x` (cut), `y` (yank), and `p` (put/paste) for songs
- `0-9` keys jump around current track, imitating YouTube's playback keybinds
- Audio bitrate indicator, originally added to verify enhanced premium bitrate
- Local filter `/` can jump to line numbers, allowing fast gotos
- Search screen accepts YouTube URLs, useful if you prefer exploring YouTube on a browser (me)
- Option to hide "Episodes for Later" in Library, I'm sure many find this annoying (me)
- No concept of "unshuffle", `s` reshuffles everytime; I have no use "unshuffling" my queue

## Usage

Collate uses browser headers to authenticate since OAuth2 [currently fails](https://github.com/sigma67/ytmusicapi/issues/813). Follow the steps [here](https://ytmusicapi.readthedocs.io/en/stable/setup/browser.html) to create your auth headers file (any POST request should work); do it from a private/incognito window so your cookie might last a few years. Supply this file in Settings.

Collage is designed for efficient keyboard navigation, but mouse is supported as well. 

Press `?` in-app to view list of all keybinds.

## Config

Data lives under `~/.config/yt-collate/` (override with `YT_COLLATE_CONFIG`). Downloads appear in `~/Music/yt-collate`.

## Development

Contributions are welcome! As a start, consider adding your favorite genre to `GENRES` in `src/services/random_song.py`

```bash
uv sync --group dev # install dev packages
uv run pytest # for testing
uv run ruff check . # for linting/formatting
```
