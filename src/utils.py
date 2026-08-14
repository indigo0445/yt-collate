"""Formatting helpers."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from rich.text import Text

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YT_HOST_HINTS = ("youtube.com", "youtu.be")


def youtube_video_id(value: str) -> str | None:
    """Extract a video id from a YouTube watch URL, or None if this is not one."""
    raw = value.strip()
    if not raw:
        return None
    lower = raw.casefold()
    if not any(hint in lower for hint in _YT_HOST_HINTS):
        return None
    if "://" not in raw:
        raw = "https://" + raw.lstrip("/")
    parsed = urlparse(raw)
    host = (parsed.hostname or "").casefold()
    if host != "youtu.be" and host != "youtube.com" and not host.endswith(".youtube.com"):
        return None
    v = (parse_qs(parsed.query).get("v") or [None])[0]
    if v and _VIDEO_ID_RE.fullmatch(v):
        return v
    parts = [p for p in parsed.path.split("/") if p]
    if host == "youtu.be" and parts and _VIDEO_ID_RE.fullmatch(parts[0]):
        return parts[0]
    if (
        len(parts) >= 2
        and parts[0].casefold() in {"embed", "shorts", "live", "v"}
        and _VIDEO_ID_RE.fullmatch(parts[1])
    ):
        return parts[1]
    return None


def format_time(seconds: float | int | None) -> str:
    if seconds is None or seconds < 0:
        return "0:00"
    total = int(seconds)
    m, s = divmod(total, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def display_duration(*, player: float, catalog: int | None) -> float:
    """Length shown in the UI.

    Catalog metadata is whole seconds. mpv's float is often just under that
    (e.g. 253.7 vs 254), and truncating it makes the total drop 1s on load.
    """
    if catalog and catalog > 0:
        return float(catalog)
    if player > 0:
        return float(round(player))
    return 0.0


def display_position(
    position: float, duration: float, *, complete: bool = False
) -> float:
    """Position shown in the UI.

    mpv's time-pos is often ~1s behind the catalog/rounded duration when the
    track has actually ended (EOF / next loading). Snap to duration so the
    clock and bar match.
    """
    if duration <= 0:
        return 0.0
    if complete:
        return duration
    pos = max(0.0, min(float(position), duration))
    if duration - pos < 1 and format_time(pos) != format_time(duration):
        return duration
    return pos


def truncate(text: str, width: int) -> str:
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    return text[: width - 1] + "…"


def progress_bar(position: float, duration: float, width: int) -> str:
    width = max(4, width)
    if duration <= 0:
        return "─" * width
    ratio = max(0.0, min(1.0, position / duration))
    filled = int(ratio * width)
    return "█" * filled + "─" * (width - filled)


def clip_list_label(widget: object, prefix: str, text: str, *, suffix: str = "") -> str:
    """Fit a numbered row to the list's current width (no halfway cut on wide panes)."""
    size = getattr(widget, "size", None)
    width = int(getattr(size, "width", 0) or 0)
    if width <= 1:
        return prefix + text + suffix
    body = max(8, width - len(prefix) - len(suffix))
    return prefix + truncate(text, body) + suffix


def row_activity_prompt(
    base: str,
    *,
    downloading: tuple[int, int] | None = None,
    fetching: bool = False,
) -> str | Text:
    """Append italic (Downloading... n/m) then (Fetching...) after the row label."""
    if downloading is None and not fetching:
        return base
    prompt = Text(base)
    if downloading is not None:
        current, total = downloading
        prompt.append(f" (Downloading... {current}/{total})", style="italic")
    if fetching:
        prompt.append(" (Fetching...)", style="italic")
    return prompt
