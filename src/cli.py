"""CLI entrypoint"""

from __future__ import annotations

import argparse
import shutil
import sys


def check_dependencies() -> list[str]:
    # return names of missing required binaries
    missing: list[str] = []
    for name in ("mpv", "yt-dlp"):
        if shutil.which(name) is None:
            missing.append(name)
    return missing


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="yt-collate",
        description="yt-collate — Terminal YouTube Music player",
    )
    parser.add_argument(
        "--version",
        action="version",
        version="yt-collate 0.1.0",
    )
    parser.parse_args(argv)

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
