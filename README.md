# yt-collate

A Terminal User Interface client for YouTube Music, with a focus on **efficiency** and **easy-of-use** while also offering a **comprehensive feature list**.

Originally planned to only focus on gathering/arranging tracks in playlists (hence name), Collate has become a full-fledged music client that is reliable and "just works". Developed for **Linux** (likely compatible with Mac; untested yet).

Built with **Textual**, **ytmusicapi**, **mpv**, and **yt-dlp**. Keybinds are a mix of Vim binds and general binds for efficient keyboard navigation (mouse is supported as well). Collate is inspired by [youtube-music-cli](https://github.com/involvex/youtube-music-cli) and [yazi](https://github.com/sxyazi/yazi); check them out!

<p align="center">
  <img src="https://raw.githubusercontent.com/indigo0445/yt-collate/refs/heads/main/assets/home.png" alt="Home page">
  <br>
  <em>Home page, with personalized recommendations once authenticated</em>
</p>

## Features

- Clean, minimalistic, modern TUI client for YouTube Music
- Extremeley fast, lightweight, and responsive
- Authentication to access your Library and personalized recommendations
- Includes YouTube Music Home, Explore, Search, and Trending pages
- Smooth playback experience, with a simple dynamic queue
- Download songs/playlists to local / Automatic audio retrieval from local
- Vast set of intuitive keybinds (e.g. `n` for next track, `d` to download, etc.)
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
- No concept of "unshuffle", `s` reshuffles queue everytime; I have no use "unshuffling" my queue

## Prerequisites

- Python 3.12+
- [mpv](https://mpv.io/)
- [yt-dlp (nightly build)](https://github.com/yt-dlp/yt-dlp-nightly-builds) (Certain non-music videos will not play on stable build. Can run `yt-dlp --update-to nightly`)
- [Deno](https://deno.com/) or [Node](https://nodejs.org/) or [QuickJS](https://bellard.org/quickjs/) (A JS runtime is needed for yt-dlp to [reliably fetch](https://github.com/yt-dlp/yt-dlp/wiki/ejs))

## Install / Update

```bash
pipx install yt-collate
```
Make sure `~/.local/bin` is in your `PATH`.
When a new version is released, update with:
```bash
pipx upgrade yt-collate
```

<p align="center">
  <img src="https://raw.githubusercontent.com/indigo0445/yt-collate/refs/heads/main/assets/playlist.png" alt="Library playlist">
  <br>
  <em>Library playlist, with a local filter (<code>/</code>) and download notification</em>
</p>

## Usage

To set up authentication, run:

```bash
yt-collate auth
```

and follow the prompts. The file is written to `~/.config/yt-collate/browser.json`, and this will likely last a few years. Run Collate with:

```bash
yt-collate
```

Press `?` in-app to view list of all keybinds.

## Config

Data lives under `~/.config/yt-collate/`. Downloads appear in `~/Music/yt-collate`.

## Development

Contributions are welcome! As a start, consider adding your favorite genre to `GENRES` in `src/services/random_song.py`.

```bash
uv sync --group dev # install dev packages
uv run pytest # for testing
uv run ruff check . # for linting/formatting
```
