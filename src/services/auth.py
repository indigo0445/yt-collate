"""interactive CLI browser.json setup for YouTube Music headers"""

from __future__ import annotations

import json
from pathlib import Path

from services.config import ConfigService
from utils import display_user_path

_DEFAULT_HEADERS = {
    "Accept": "*/*",
    "Content-Type": "application/json",
    "X-Goog-AuthUser": "0", # incognito anyway
    "x-origin": "https://music.youtube.com",
}

_INSTRUCTIONS = """\
Create YouTube Music auth file (browser.json)

1. Open a new private/incognito browser window
3. Open https://music.youtube.com and sign in
2. Open DevTools (F12 / Right-click > Inspect) and go to the Network tab
4. Reload the page
5. Find a POST request. Open it and look at Request Headers
6. Paste "Authorization" and "Cookie" below

"""


def default_browser_json_path() -> Path:
    return ConfigService().auth_headers_path


def strip_header_value(raw: str, *names: str) -> str:
    text = raw.strip().strip('"').strip("'")
    for name in names:
        prefix = f"{name}:"
        if text.casefold().startswith(prefix.casefold()):
            return text[len(prefix) :].strip().strip('"').strip("'")
    return text


def build_browser_headers(authorization: str, cookie: str) -> dict[str, str]:
    auth = strip_header_value(authorization, "authorization")
    cookie_value = strip_header_value(cookie, "cookie")
    return {
        "Accept": _DEFAULT_HEADERS["Accept"],
        "Authorization": auth,
        "Content-Type": _DEFAULT_HEADERS["Content-Type"],
        "X-Goog-AuthUser": _DEFAULT_HEADERS["X-Goog-AuthUser"],
        "x-origin": _DEFAULT_HEADERS["x-origin"],
        "Cookie": cookie_value,
    }


def header_error(headers: dict[str, str]) -> str | None:
    auth = headers.get("Authorization", "")
    cookie = headers.get("Cookie", "")
    if not auth:
        return "Authorization is empty"
    if "SAPISIDHASH" not in auth:
        return "Authorization should be the SAPISIDHASH value from Request Headers"
    if not cookie:
        return "Cookie is empty"
    if "__Secure-3PAPISID" not in cookie:
        return "Cookie is missing __Secure-3PAPISID (use a logged-in POST request)"
    return None


def write_browser_json(path: Path, headers: dict[str, str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(headers, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return path


def run_auth(dest: Path | None = None) -> int:
    path = dest if dest is not None else default_browser_json_path()
    print(_INSTRUCTIONS.rstrip())
    print(f"File: {display_user_path(path)}")
    print()

    if path.exists():
        answer = input(f"{display_user_path(path)} already exists. Overwrite? [y/N] ").strip()
        if answer.casefold() not in {"y", "yes"}:
            print("Cancelled.")
            return 1

    while True:
        authorization = input("Authorization: ").strip()
        cookie = input("Cookie: ").strip()
        headers = build_browser_headers(authorization, cookie)
        error = header_error(headers)
        if error is None:
            break
        print(f"\n{error}. Try again.\n")

    write_browser_json(path, headers)
    print(f"\nWrote {display_user_path(path)}")
    print(
        "You're all set! Run yt-collate to confirm your authentication.\n"
        "If you have a Premium account, you probably want to allow premium bitrates in Settings."
    )
    return 0
