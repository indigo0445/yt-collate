"""CLI dependency check"""

from __future__ import annotations

from cli import build_parser, check_dependencies, main


def test_check_dependencies_finds_mpv_ytdlp() -> None:
    missing = check_dependencies()
    # both should be present in this environment
    assert "mpv" not in missing
    assert "yt-dlp" not in missing


def test_parser_auth_subcommand() -> None:
    args = build_parser().parse_args(["auth"])
    assert args.command == "auth"
    assert build_parser().parse_args([]).command is None


def test_main_auth_skips_app(monkeypatch) -> None:
    called: list[int] = []

    def fake_run_auth() -> int:
        called.append(1)
        return 0

    monkeypatch.setattr("services.auth.run_auth", fake_run_auth)
    assert main(["auth"]) == 0
    assert called == [1]
