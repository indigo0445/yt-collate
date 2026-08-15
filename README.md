# yt-collate

A Terminal User Interface (TUI) music player for YouTube Music.

Built with **Python**, **Textual** (fullscreen alternate screen), **mpv**, and **yt-dlp**. Music metadata via **ytmusicapi**.

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

- Fullscreen TUI using the terminal alternate screen buffer
- Search and play YouTube Music tracks
- Queue, YouTube play history when signed in
- Playlists, liked songs, trending, new releases
- Shuffle / repeat / related-track autoplay
- Browser-header auth for library / liked songs
- Download songs to `~/Music/yt-collate/Songs/`; playlists as `{name}.json` beside it
- Optional Discord Rich Presence (`uv sync --extra discord`)

## Keybindings

| Key | Action |
|-----|--------|
| `h` `j` `k` `l` / arrows | Panels (h/l) and lists (j/k) |
| `/` | Filter the focused list |
| `\` | Jump to Search |
| Enter | Select / play |
| `i` / `a` | Play next / append to queue |
| `w` | Download song to `~/Music/yt-collate/Songs/`; playlists also write `{name}.json` |
| Space | Play / pause |
| `n` / `b` | Next / previous |
| `0`–`9` | Jump to 0% … 90% |
| `-` / `=` | Volume down / up |
| `s` / `r` | Shuffle / cycle repeat |
| `m` / `+` / `o` / `d` `x` | Mark / add / new playlist / delete |
| `H` | Queue & History |
| `,` | Settings |
| `?` | Help |
| `q` / Esc | Back |
| Ctrl+Q | Quit |

## Config

Data lives under `~/.config/yt-collate/` (override with `YT_COLLATE_CONFIG`).

On first run, `~/.config/youtube-music-lite/` is renamed if present. Audio files go to `~/Music/yt-collate/Songs/`; downloaded playlists are `{name}.json` in `~/Music/yt-collate/`.

## Development

```bash
uv sync --group dev
uv run pytest
uv run ruff check .
```
