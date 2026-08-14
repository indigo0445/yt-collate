"""help strings must match the live App / list bindings"""

from __future__ import annotations

from pathlib import Path

from app import YtCollateApp
from keyhints import PLAYBACK_CHROME, QUEUE, STATUS_KEYS
from screens.help import HELP_MD

SRC = Path(__file__).resolve().parents[1] / "src"


def _binding_key(action: str) -> str:
    for binding in YtCollateApp.BINDINGS:
        if binding.action == action:
            return binding.key
    raise AssertionError(f"no binding for {action}")


def test_queue_and_download_bindings() -> None:
    assert _binding_key("queue_insert") == "i"
    assert _binding_key("queue_append") == "a"
    assert _binding_key("download") == "w"


def test_help_and_status_match_queue_bindings() -> None:
    assert "- **i** — Insert" in HELP_MD
    assert "- **a** — Append" in HELP_MD
    assert "- **w** — Download" in HELP_MD
    assert "- **A** — Append" not in HELP_MD
    assert QUEUE.startswith("i play next")
    assert "i/a queue" in STATUS_KEYS
    assert "w dl" in STATUS_KEYS
    assert "a/A" not in STATUS_KEYS
    assert "[↑↓]" not in STATUS_KEYS
    assert "[-/=]" in PLAYBACK_CHROME


def test_src_has_no_stale_a_slash_a_queue_hints() -> None:
    stale = (
        "a/A queue",
        "a play next",
        "[↑↓]",
    )
    hits: list[str] = []
    for path in SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for needle in stale:
            if needle in text:
                hits.append(f"{path.relative_to(SRC)}: {needle}")
    assert hits == []
