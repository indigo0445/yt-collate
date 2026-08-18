"""auth helper unit tests"""

from __future__ import annotations

import json
from pathlib import Path

from services.auth import (
    build_browser_headers,
    header_error,
    run_auth,
    strip_header_value,
    write_browser_json,
)
from services.music import MusicService, track_from_song


def test_verify_auth_without_file(tmp_path: Path) -> None:
    missing = tmp_path / "nope.json"
    svc = MusicService(auth_headers_path=missing)
    ok, msg = svc.verify_auth()
    assert ok is False
    assert "No auth file" in msg


def test_track_from_song_still_works() -> None:
    t = track_from_song({"videoId": "x", "title": "T", "artists": [{"name": "A"}]})
    assert t is not None and t.video_id == "x"


def test_strip_header_prefix() -> None:
    assert (
        strip_header_value("Authorization: SAPISIDHASH 1_abc", "authorization")
        == "SAPISIDHASH 1_abc"
    )
    assert strip_header_value('Cookie: "SID=x"', "cookie") == "SID=x"
    assert strip_header_value("SAPISIDHASH 1_abc", "authorization") == "SAPISIDHASH 1_abc"


def test_build_browser_headers_uses_defaults() -> None:
    headers = build_browser_headers(
        "Authorization: SAPISIDHASH 1_abc",
        "SID=x; __Secure-3PAPISID=y",
    )
    assert headers["Accept"] == "*/*"
    assert headers["Content-Type"] == "application/json"
    assert headers["X-Goog-AuthUser"] == "0"
    assert headers["x-origin"] == "https://music.youtube.com"
    assert headers["Authorization"] == "SAPISIDHASH 1_abc"
    assert headers["Cookie"] == "SID=x; __Secure-3PAPISID=y"
    assert header_error(headers) is None


def test_header_error_requires_sapisid() -> None:
    headers = build_browser_headers("Bearer nope", "SID=x")
    assert header_error(headers) is not None
    headers = build_browser_headers("SAPISIDHASH 1_abc", "SID=x")
    assert "__Secure-3PAPISID" in (header_error(headers) or "")


def test_write_browser_json(tmp_path: Path) -> None:
    dest = tmp_path / "browser.json"
    headers = build_browser_headers("SAPISIDHASH 1_abc", "SID=x; __Secure-3PAPISID=y")
    write_browser_json(dest, headers)
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["Authorization"] == "SAPISIDHASH 1_abc"
    assert data["Cookie"] == "SID=x; __Secure-3PAPISID=y"
    assert data["X-Goog-AuthUser"] == "0"


def test_run_auth_writes_default_file(tmp_path: Path, monkeypatch, capsys) -> None:
    dest = tmp_path / "cfg" / "browser.json"
    answers = iter(["SAPISIDHASH 1_abc", "SID=x; __Secure-3PAPISID=y"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    code = run_auth(dest)
    assert code == 0
    assert dest.exists()
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["Authorization"] == "SAPISIDHASH 1_abc"
    assert "Wrote" in capsys.readouterr().out


def test_run_auth_cancel_overwrite(tmp_path: Path, monkeypatch) -> None:
    dest = tmp_path / "browser.json"
    dest.write_text("{}", encoding="utf-8")
    answers = iter(["n"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    monkeypatch.setattr("builtins.print", lambda *_args, **_kwargs: None)
    code = run_auth(dest)
    assert code == 1
    assert dest.read_text(encoding="utf-8") == "{}"


def test_run_auth_retries_invalid_then_writes(tmp_path: Path, monkeypatch) -> None:
    dest = tmp_path / "browser.json"
    answers = iter(
        [
            "not-auth",
            "SID=x",
            "SAPISIDHASH 1_abc",
            "SID=x; __Secure-3PAPISID=y",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    monkeypatch.setattr("builtins.print", lambda *_args, **_kwargs: None)
    code = run_auth(dest)
    assert code == 0
    data = json.loads(dest.read_text(encoding="utf-8"))
    assert data["Authorization"] == "SAPISIDHASH 1_abc"
