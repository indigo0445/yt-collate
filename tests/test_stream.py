"""yt-dlp stream helpers."""

from __future__ import annotations

from pathlib import Path

from services.stream import cookies_and_user_agent, write_netscape_cookies


def test_write_netscape_cookies(tmp_path: Path) -> None:
    dest = tmp_path / "cookies.txt"
    write_netscape_cookies("SID=abc; __Secure-1PSID=xyz; skipme", dest)
    text = dest.read_text(encoding="utf-8")
    assert "SID\tabc" in text
    assert "__Secure-1PSID\txyz" in text
    assert ".youtube.com" in text
    assert ".google.com" in text
    assert "TRUE\t0\t__Secure-1PSID" in text


def test_cookies_from_headers_auth(tmp_path: Path) -> None:
    auth = tmp_path / "headers_auth.json"
    auth.write_text(
        '{"Cookie": "SID=s1; HSID=h1", "User-Agent": "TestUA/1.0"}',
        encoding="utf-8",
    )
    cookies, ua = cookies_and_user_agent(auth, tmp_path / "out.txt")
    assert ua == "TestUA/1.0"
    assert cookies is not None and cookies.exists()
    assert "SID\ts1" in cookies.read_text(encoding="utf-8")
