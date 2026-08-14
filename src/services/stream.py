"""turn browser auth headers into a Netscape cookie file for mpv/yt-dlp"""

from __future__ import annotations

import json
from pathlib import Path


def _header(data: dict[str, object], name: str) -> str | None:
    lower = name.casefold()
    for key, value in data.items():
        if str(key).casefold() == lower and value is not None:
            text = str(value).strip()
            return text or None
    return None


def headers_from_auth_file(path: Path) -> dict[str, object] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    return raw if isinstance(raw, dict) else None


def write_netscape_cookies(cookie_header: str, dest: Path) -> Path:
    # write a Cookie request header as a Netscape cookie file for yt-dlp
    lines = [
        "# Netscape HTTP Cookie File",
        "# Generated from YouTube Music browser headers",
    ]
    for part in cookie_header.split(";"):
        part = part.strip()
        if not part or "=" not in part:
            continue
        name, value = part.split("=", 1)
        name, value = name.strip(), value.strip()
        if not name:
            continue
        secure = "TRUE" if name.startswith("__Secure-") or name.startswith("__Host-") else "FALSE"
        for domain in (".youtube.com", ".google.com"):
            lines.append(f"{domain}\tTRUE\t/\t{secure}\t0\t{name}\t{value}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dest


def cookies_and_user_agent(
    auth_headers_path: Path | None,
    dest: Path,
) -> tuple[Path | None, str | None]:
    # build yt-dlp cookies + User-Agent from headers_auth.json if present
    if auth_headers_path is None:
        return None, None
    headers = headers_from_auth_file(auth_headers_path)
    if not headers:
        return None, None
    ua = _header(headers, "user-agent")
    cookie = _header(headers, "cookie")
    cookies_path = write_netscape_cookies(cookie, dest) if cookie else None
    return cookies_path, ua
