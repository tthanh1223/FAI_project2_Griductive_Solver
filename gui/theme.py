"""Colours and fonts of the GUI (Figma design: light and dark theme).

Owner: GUI & Video.
LIGHT and DARK have the same keys (the Figma table plus tag_text), so every widget reads colours as theme["key"]
and switching theme = rebuild the window with the other dict.
"""
import tkinter.font as tkfont

LIGHT = {
    "canvas": "#EFE0C4",            # window background
    "panel": "#FAF1DE",
    "border": "#D8C6A4",
    "text": "#2A1F21",
    "muted": "#7A6650",
    "on_accent": "#FFFFFF",         # text on coloured buttons / badges
    "selected": "#7E3DB5",          # selected cell, primary button, selected clue
    "selected_subtle": "#F1E7FA",
    "criminal": "#C8302C",
    "criminal_subtle": "#FBE5E2",   # background of a criminal card
    "innocent": "#2F8F9B",
    "innocent_subtle": "#E2F2F4",   # background of an innocent card
    "facedown": "#E6D6B6",          # background of a face-down card
    "facedown_border": "#CDB892",
    "highlight": "#E8823F",         # cell mentioned by the selected clue
    "warning": "#B0601C",           # NOT_PROVABLE
    "warning_subtle": "#FFF1E4",
    "hint_bg": "#FFF8D6",
    "hint_border": "#E9D34A",
    "tape": "#F2D43C",
    "tape_ink": "#2A1F21",
    "tag_text": "#2A1F21",          # cell tag in the Revealed clues list
}

DARK = {
    "canvas": "#1A1416",
    "panel": "#281F22",
    "border": "#3E3337",
    "text": "#F1ECE4",
    "muted": "#A49A9E",
    "on_accent": "#FFFFFF",
    "selected": "#7B70B8",
    "selected_subtle": "#2E2945",
    "criminal": "#E5533A",
    "criminal_subtle": "#3D1F1C",
    "innocent": "#4A6BB5",
    "innocent_subtle": "#1D2540",
    "facedown": "#332A2D",
    "facedown_border": "#4A3F43",
    "highlight": "#D4B232",
    "warning": "#D4B232",
    "warning_subtle": "#332C14",
    "hint_bg": "#2E2814",
    "hint_border": "#6B5A22",
    "tape": "#D4B232",
    "tape_ink": "#281F22",
    "tag_text": "#7B70B8",
}

THEMES = {"light": LIGHT, "dark": DARK}

_UI_FAMILIES = ("Inter", "Helvetica Neue", "Segoe UI", "Arial")
_MONO_FAMILIES = ("Menlo", "Consolas", "Courier")

# name -> (size, bold?)
_SIZES = {
    "title": (18, True),        # "Griductive Solver"
    "subtitle": (12, False),    # "Puzzle: p3_01.json · 3 × 3 · Step 5"
    "button": (13, True),
    "panel_title": (14, True),  # "Board", "Verdict", ...
    "body": (12, False),
    "body_bold": (12, True),
    "card_name": (14, True),
    "card_small": (11, False),  # job
    "card_coord": (11, True),
    "badge": (10, True),
    "clue": (10, False),
    "axis": (13, True),         # A B C / 1 2 3 around the board
    "legend": (11, False),
    "stat_value": (15, True),
    "stat_label": (10, False),
    "status": (11, False),
    "tape": (12, True),
    "tape_big": (13, True),
}


def _first_available(root, families):
    available = set(tkfont.families(root))
    for family in families:
        if family in available:
            return family
    return families[-1]


def make_fonts(root) -> dict:
    """{name: tkinter Font}. Fonts must be created after the Tk root exists."""
    ui = _first_available(root, _UI_FAMILIES)
    mono = _first_available(root, _MONO_FAMILIES)
    fonts = {
        name: tkfont.Font(root=root, family=ui, size=size, weight="bold" if bold else "normal")
        for name, (size, bold) in _SIZES.items()
    }
    fonts["mono"] = tkfont.Font(root=root, family=mono, size=11)
    return fonts
