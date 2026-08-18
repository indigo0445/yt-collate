"""CLI entrypoint"""

from __future__ import annotations

import argparse
import shutil
import sys
from importlib.metadata import PackageNotFoundError, version


def _package_version() -> str:
    try:
        return version("yt-collate")
    except PackageNotFoundError:
        return "dev"


def check_dependencies() -> list[str]:
    # return names of missing required binaries
    missing: list[str] = []
    for name in ("mpv", "yt-dlp"):
        if shutil.which(name) is None:
            missing.append(name)
    return missing


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yt-collate",
        description="yt-collate — Terminal YouTube Music player",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"yt-collate {_package_version()}",
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser(
        "auth",
        help="create browser.json from YouTube Music request headers",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "auth":
        from services.auth import run_auth

        try:
            return run_auth()
        except (EOFError, KeyboardInterrupt):
            print()
            return 1

    missing = check_dependencies()
    if missing:
        print(
            "Missing required dependencies: "
            + ", ".join(missing)
            + "\nInstall mpv and yt-dlp, then try again.",
            file=sys.stderr,
        )
        return 1

    from app import YtCollateApp

    app = YtCollateApp()
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
