"""On-screen key hints. Keep in sync with App.BINDINGS and NavListView.BINDINGS."""

QUEUE = "i play next · a queue"
NAV_BACK = "h Main Selection · Esc/q back"

CATALOG = f"Enter open/play · {QUEUE} · w download · {NAV_BACK}"
LIBRARY = (
    f"Enter open/play · {QUEUE} · w download · m mark · + add · o new · d/x delete · "
    f"{NAV_BACK}"
)
SEARCH = (
    "j/k move · k/#1 → query · Esc/q/↓ query → #1 · Enter play · i/a queue · "
    "w download · \\ query"
)
DISCOVERY = f"Enter play · {QUEUE} · w download · {NAV_BACK}"
SETTINGS = "h Main Selection · Enter edits auth path or toggles · Esc/q cancel · ↓ next"

STATUS_KEYS = (
    "hjkl/arrows move · -/= vol · 0-9 jump · / filter · \\ search · "
    "m mark · + add · o new · w dl · d/x del · Enter play · i/a queue · "
    "Space pause · n/b next/prev · s/r shuffle/repeat · Esc/q back · Ctrl+Q quit"
)

PLAYBACK_CHROME = "▶/⏸ [Space]  |◀ [B]  ▶| [N]  ⇄ [S]  ↺ [R]  [-/=]"
