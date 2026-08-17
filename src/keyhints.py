"""on-screen key hints. Should match App.BINDINGS and NavListView.BINDINGS"""

CATALOG = " · ".join(["y yank", "+ add"])
LIBRARY = " · ".join(["o new", "x delete", "y yank", "p paste", "m mark", "+ add"])
SEARCH = " · ".join(["y yank", "+ add"])
DISCOVERY = " · ".join(["y yank", "+ add"])
LOCAL = ""
SETTINGS = "Enter to edit paths or toggle flags"

# STATUS_KEYS = " · ".join(
#    ["hjkl/arrows move", "Enter open/play", "Esc/q back", "/ filter", 
#    "\\ search", "a queue", "d download", "Ctrl+Q quit"]
#)

PLAYBACK_KEYS = " · ".join(
    ["Space play/pause", "n next", "b prev", "0-9 jump", "s shuffle", "r repeat", "-/= vol"]
)
