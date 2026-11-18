"""Tkinter GUI (dark board, colour-coded clues).

Always redraw from engine.public_state(); never read hidden statuses.
Input / output of every function: docs/INTERFACES.md.

Mouse: click a face-down card to select it, click a face-up card to highlight what its clue
talks about, right-click a face-down card to cycle a pencil mark.
Keys: C = criminal, I = innocent, H = hint, Space = one auto step, Esc = clear.
"""
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font, messagebox

from agent import INCONSISTENT, LogicAgent
from engine import ACCEPTED, CONTRADICTED, NOT_PROVABLE, GameEngine
from model import CRIMINAL, INNOCENT, cells_in_clue, load_puzzle, region_cells

PUZZLE_DIR = Path(__file__).resolve().parents[1] / "puzzles"
AUTO_DELAY_MS = 450
CARD_W, CARD_H, GAP = 118, 116, 8

# ---------------------------------------------------------------- palette
BG = "#1d1918"
PANEL_TEXT = "#e9e3dc"
MUTED = "#8c847c"
FAINT = "#5c5550"
CARD_BG = "#2a2523"
CARD_EDGE = "#3e3734"
CARD_DIM_TEXT = "#9a928a"
INNO_BG, INNO_EDGE = "#26362b", "#5fae78"
CRIM_BG, CRIM_EDGE = "#4a2422", "#d0645a"
SELECT = "#f2c14e"
HINT = "#7b6cf0"
BUTTON_BG, BUTTON_ACTIVE = "#2e2826", "#3a3330"
ACCENT = "#ef8a7a"
DLG_BG = "#2b2523"
# colours for the parts of a clue (region, person, second region, ...)
SEG_COLOURS = ["#6aa9e9", "#f2c14e", "#c08ae8", "#5cc8b8", "#e88aa8"]
MARK_COLOURS = [None, "#5fae78", "#d0645a", "#f2c14e", "#6aa9e9", "#c08ae8"]
AVATAR_COLOURS = ["#c9844f", "#7fa86a", "#6c8ec9", "#c47aa0", "#c9b14f", "#5fb3a6", "#a77fc9", "#c96a5f"]
RESULT_COLOURS = {ACCEPTED: INNO_EDGE, NOT_PROVABLE: SELECT, CONTRADICTED: CRIM_EDGE}


# ---------------------------------------------------------------- clue -> coloured segments
# A segment is (text, cells or None). Segments with cells are drawn in colour and their
# cells are outlined in the same colour when the clue is selected.

def _person(cell, names):
    return (names.get(cell, cell), [cell])


def _region_segments(region, names, rows, cols):
    kind = region.get("kind")
    cells = lambda: region_cells(region, rows, cols)  # noqa: E731
    if kind == "row":
        return [(f"row {region['row']}", cells())]
    if kind == "col":
        return [(f"column {region['col']}", cells())]
    if kind == "neighbors":
        return [("neighboring", cells()), _person(region["of"], names)]
    if kind == "cells":
        return [(", ".join(names.get(c, c) for c in region["cells"]), list(region["cells"]))]
    if kind == "all":
        return [("in total", None)]
    if kind in ("edges", "corners"):
        return [(f"on the {kind}", cells())]
    if kind in ("above", "below"):
        return [(kind, cells()), _person(region["of"], names)]
    if kind in ("left", "right"):
        return [(f"to the {kind} of", cells()), _person(region["of"], names)]
    if kind == "inter":
        out = []
        for i, r in enumerate(region["regions"]):
            if i:
                out.append(("and", None))
            out += _region_segments(r, names, rows, cols)
        return out
    return [(str(region), None)]


def _plural(k, word):
    return f"{k} {word}" if k == 1 else f"{k} {word}s"


def clue_segments(clue: dict, names: dict[str, str], rows: int = 0, cols: int = 0) -> list[tuple]:
    """Clue -> [(text, cells | None), ...]. rows/cols are needed to colour regions."""
    t = clue.get("type")
    word = "innocent" if clue.get("count") == "innocent" else "criminal"

    def region(r):
        if rows and cols:
            return _region_segments(r, names, rows, cols)
        return [(seg, None) for seg, _ in _region_segments_text(r, names)]

    if t == "NONE":
        return [(clue.get("text", "(no information)"), None)]
    if t == "FACT":
        return [_person(clue["who"], names), (f"is {clue['status'].lower()}", None)]
    if t == "SAME":
        return [_person(clue["a"], names), ("and", None), _person(clue["b"], names),
                ("are on the same side", None)]
    if t == "DIFFERENT":
        return [_person(clue["a"], names), ("and", None), _person(clue["b"], names),
                ("are on different sides", None)]
    if t in ("EXACTLY", "AT_LEAST", "AT_MOST"):
        k = clue["k"]
        lead = {"EXACTLY": "Exactly", "AT_LEAST": "At least", "AT_MOST": "At most"}[t]
        head = f"There are no {word}s" if t == "EXACTLY" and k == 0 else f"{lead} {_plural(k, word)}"
        return [(head, None)] + region(clue["region"])
    if t == "COMPARE":
        op = {">": f"more {word}s than", "<": f"fewer {word}s than", "=": f"as many {word}s as"}[clue["op"]]
        return region(clue["r1"]) + [(f"has {op}", None)] + region(clue["r2"])
    if t == "CONNECTED":
        return [(f"All {word}s", None)] + region(clue["region"]) + [("are connected", None)]
    if t == "AND":
        out = []
        for i, part in enumerate(clue["parts"]):
            if i:
                out.append(("; and", None))
            out += clue_segments(part, names, rows, cols)
        return out
    return [(str(clue), None)]


def _region_segments_text(region, names):
    """Region text without needing the board size (used by clue_to_text)."""
    kind = region.get("kind")
    simple = {
        "row": lambda: f"row {region['row']}",
        "col": lambda: f"column {region['col']}",
        "cells": lambda: ", ".join(names.get(c, c) for c in region["cells"]),
        "all": lambda: "in total",
        "edges": lambda: "on the edges",
        "corners": lambda: "on the corners",
    }
    if kind in simple:
        return [(simple[kind](), None)]
    if kind == "neighbors":
        return [("neighboring", None), (names.get(region["of"], region["of"]), None)]
    if kind in ("above", "below"):
        return [(kind, None), (names.get(region["of"], region["of"]), None)]
    if kind in ("left", "right"):
        return [(f"to the {kind} of", None), (names.get(region["of"], region["of"]), None)]
    if kind == "inter":
        out = []
        for i, r in enumerate(region["regions"]):
            if i:
                out.append(("and", None))
            out += _region_segments_text(r, names)
        return out
    return [(str(region), None)]


def clue_to_text(clue: dict, names: dict[str, str]) -> str:
    """JSON clue -> readable sentence, e.g. 'Exactly 1 criminal row 2.'"""
    return " ".join(text for text, _ in clue_segments(clue, names)) + "."


# ---------------------------------------------------------------- canvas helpers

def round_rect(cv, x0, y0, x1, y1, r=10, **kw):
    pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
           x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
    return cv.create_polygon(pts, smooth=True, **kw)


def wrap_segments(words, fnt, width, bold=None):
    """words: [(word, colour)] -> lines of [(word, colour, width_px)].
    Coloured words are measured with `bold` (the font they are drawn with)."""
    space = fnt.measure(" ")
    lines, line, used = [], [], 0
    for word, colour in words:
        w = (bold if colour and bold else fnt).measure(word)
        if line and used + space + w > width:
            lines.append(line)
            line, used = [], 0
        used += (space if line else 0) + w
        line.append((word, colour, w))
    if line:
        lines.append(line)
    return lines


class FlatButton(tk.Label):
    def __init__(self, master, text, command, accent=False, **kw):
        bg = ACCENT if accent else BUTTON_BG
        super().__init__(master, text=text, bg=bg, fg="#1d1918" if accent else PANEL_TEXT,
                         padx=14, pady=6, cursor="hand2", **kw)
        self.base_bg = bg
        self.command = command
        self.bind("<Button-1>", lambda _e: self.command())
        self.bind("<Enter>", lambda _e: self.configure(bg=BUTTON_ACTIVE if not accent else "#f39d8f"))
        self.bind("<Leave>", lambda _e: self.configure(bg=self.base_bg))

    def set_accent(self, on: bool):
        self.base_bg = ACCENT if on else BUTTON_BG
        self.configure(bg=self.base_bg, fg="#1d1918" if on else PANEL_TEXT)


# ---------------------------------------------------------------- app

class App:
    def __init__(self, root: tk.Tk, puzzle_path: str | None = None):
        self.root = root
        self.agent = LogicAgent()
        self.engine: GameEngine | None = None
        self.selected: str | None = None        # face-down card chosen for a verdict
        self.focus_clue: str | None = None      # face-up card whose clue is highlighted
        self.hint_state: dict | None = None     # {"cell", "verdict", "because", "revealed": bool}
        self.marks: dict[str, int] = {}
        self.mark_mode = False
        self.last_accepted: str | None = None
        self.dialog = None
        self.auto_job = None
        self.step_no = 0

        self.k = max(1.0, root.winfo_fpixels("1i") / 96)   # HiDPI: scale card geometry
        root.title("Griductive Solver")
        root.configure(bg=BG)
        self.f = {
            "title": font.Font(family="Georgia", size=20, weight="bold"),
            "coord": font.Font(family="Consolas", size=7, weight="bold"),
            "job": font.Font(family="Consolas", size=7),
            "name": font.Font(family="Segoe UI", size=10, weight="bold"),
            "name_s": font.Font(family="Segoe UI", size=8, weight="bold"),
            "clue": font.Font(family="Segoe UI", size=8),
            "clue_b": font.Font(family="Segoe UI", size=8, weight="bold"),
            "clue_x": font.Font(family="Segoe UI", size=8, overstrike=1),
            "init": font.Font(family="Segoe UI", size=12, weight="bold"),
            "init_s": font.Font(family="Segoe UI", size=7, weight="bold"),
            "ui": font.Font(family="Segoe UI", size=9),
            "ui_b": font.Font(family="Segoe UI", size=10, weight="bold"),
            "dlg_title": font.Font(family="Georgia", size=13, weight="bold"),
            "small": font.Font(family="Consolas", size=8),
        }
        self._build_layout()
        root.bind("<Key-c>", lambda _e: self.submit(CRIMINAL))
        root.bind("<Key-i>", lambda _e: self.submit(INNOCENT))
        root.bind("<Key-h>", lambda _e: self.hint())
        root.bind("<space>", lambda _e: self.auto_step(single=True))
        root.bind("<Escape>", lambda _e: (self.close_dialog(), self.clear_focus()))
        if puzzle_path:
            self.load(puzzle_path)
        else:
            self.set_message("Load a puzzle to start.", MUTED)

    # ----- layout

    def _build_layout(self):
        outer = tk.Frame(self.root, bg=BG)
        outer.pack(fill="both", expand=True, padx=28, pady=22)

        left = tk.Frame(outer, bg=BG, width=300)
        left.pack(side="left", fill="y", padx=(0, 28))
        left.pack_propagate(False)
        tk.Label(left, text="Griductive Solver", font=self.f["title"], bg=BG, fg=PANEL_TEXT).pack(anchor="w")
        self.info = tk.Label(left, text="", font=self.f["small"], bg=BG, fg=MUTED)
        self.info.pack(anchor="w", pady=(2, 14))
        rules = ("Every person is criminal or innocent, and every clue is true.\n"
                 "• Click a face-down card and choose Innocent or Criminal.\n"
                 "• A proved call flips the card and reveals its clue.\n"
                 "• Only call what the clues prove. No guessing.\n"
                 "• Click a clue to see who it talks about.\n"
                 "• Hint shows which clue to read; Reveal shows who it proves.\n"
                 "• Mark (or right-click) adds pencil colours to cards.")
        tk.Label(left, text="HOW TO PLAY", font=self.f["coord"], bg=BG, fg=MUTED).pack(anchor="w")
        tk.Label(left, text=rules, font=self.f["ui"], bg=BG, fg=CARD_DIM_TEXT, justify="left",
                 wraplength=290).pack(anchor="w", pady=(4, 16))
        self.message = tk.Label(left, text="", font=self.f["ui_b"], bg=BG, fg=PANEL_TEXT,
                                justify="left", wraplength=290, anchor="w")
        self.message.pack(fill="x", pady=(0, 12))
        tk.Label(left, text="TRACE", font=self.f["coord"], bg=BG, fg=MUTED).pack(anchor="w")
        self.trace = tk.Text(left, height=12, bg="#231e1d", fg=CARD_DIM_TEXT, relief="flat",
                             font=self.f["small"], wrap="word", state="disabled",
                             highlightthickness=0, padx=6, pady=4)
        self.trace.pack(fill="both", expand=True, pady=(4, 0))

        right = tk.Frame(outer, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        self.canvas = tk.Canvas(right, bg=BG, highlightthickness=0, width=self.p(4 * (CARD_W + GAP)),
                                height=self.p(3 * (CARD_H + GAP)))
        self.canvas.pack(pady=(0, 10))
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<Button-3>", self.on_right_click)

        bar = tk.Frame(right, bg=BG)
        bar.pack()
        self.btn_mark = FlatButton(bar, "Mark", self.toggle_mark, font=self.f["ui"])
        self.btn_mark.pack(side="left", padx=4)
        self.btn_hint = FlatButton(bar, "Hint", self.hint, font=self.f["ui"])
        self.btn_auto = FlatButton(bar, "Auto Solve", self.toggle_auto, font=self.f["ui"])
        for b in (self.btn_hint, self.btn_auto,
                  FlatButton(bar, "Restart", self.restart, font=self.f["ui"]),
                  FlatButton(bar, "Load", self.ask_load, font=self.f["ui"])):
            b.pack(side="left", padx=4)

    # ----- geometry

    def p(self, n):
        return n * self.k

    def card_box(self, i):
        cols = self.engine.public_state()["cols"] if self.engine else 4
        r, c = divmod(i, cols)
        w, h, g = self.p(CARD_W), self.p(CARD_H), self.p(GAP)
        x0, y0 = c * (w + g) + 4, r * (h + g) + 4
        return x0, y0, x0 + w, y0 + h

    def cell_at(self, x, y):
        if not self.engine:
            return None
        for i, info in enumerate(self.state["cells"]):
            x0, y0, x1, y1 = self.card_box(i)
            if x0 <= x <= x1 and y0 <= y <= y1:
                return info["cell"]
        return None

    # ----- drawing

    @property
    def state(self):
        return self.engine.public_state()

    def names(self, state=None):
        state = state or self.state
        return {c["cell"]: c["name"] for c in state["cells"]}

    def _segments(self, clue, state):
        return clue_segments(clue, self.names(state), state["rows"], state["cols"])

    def _outlines(self, state):
        """cell -> list of colours to outline it with (selected clue + hint)."""
        out: dict[str, list[str]] = {}
        if self.focus_clue and self.focus_clue in state["revealed"]:
            colour_i = 0
            for _text, cells in self._segments(state["revealed"][self.focus_clue], state):
                if cells:
                    col = SEG_COLOURS[colour_i % len(SEG_COLOURS)]
                    colour_i += 1
                    for c in cells:
                        out.setdefault(c, []).append(col)
        return out

    def _clue_used_up(self, owner, clue, state):
        """Cross a clue out once it can no longer help.

        - A clue about people: every cell it talks about is already proved.
        - A flavour clue (no cells): once the whole board is solved.
        The card flipped last stays readable.
        """
        if owner == self.last_accepted:
            return False
        try:
            cells = cells_in_clue(clue, state["rows"], state["cols"])
        except NotImplementedError:
            return False
        if not cells:
            return len(state["verdicts"]) == len(state["cells"])
        return all(c in state["verdicts"] for c in cells)

    def redraw(self):
        cv = self.canvas
        cv.delete("all")
        if not self.engine:
            return
        state = self.state
        rows, cols = state["rows"], state["cols"]
        cv.configure(width=cols * self.p(CARD_W + GAP) + 8, height=rows * self.p(CARD_H + GAP) + 8)
        outlines = self._outlines(state)
        dimmed = bool(self.focus_clue) or bool(self.hint_state) or self.dialog is not None
        hint_clues = set(self.hint_state["because"]) if self.hint_state else set()
        hint_target = self.hint_state["cell"] if self.hint_state and self.hint_state["revealed"] else None

        for i, info in enumerate(state["cells"]):
            cell = info["cell"]
            x0, y0, x1, y1 = self.card_box(i)
            verdict = state["verdicts"].get(cell)
            clue = state["revealed"].get(cell)
            bg, edge, width = CARD_BG, CARD_EDGE, 1
            if verdict == INNOCENT:
                bg, edge = INNO_BG, INNO_EDGE
            elif verdict == CRIMINAL:
                bg, edge = CRIM_BG, CRIM_EDGE
            ring = outlines.get(cell)
            faded = self.dialog is not None or dimmed and not ring and cell != self.focus_clue                 and cell not in hint_clues and cell != hint_target
            if cell == hint_target:
                edge, width = HINT, 3
            elif cell == self.selected:
                edge, width = SELECT, 3
            elif ring:
                edge, width = ring[0], 3
            round_rect(cv, x0, y0, x1, y1, fill=bg, outline=edge, width=width)
            if ring and len(ring) > 1:   # second colour as a bottom stripe
                cv.create_line(x0 + self.p(10), y1 - 1, x1 - self.p(10), y1 - 1, fill=ring[1], width=3)
            if cell in hint_clues:
                cv.create_rectangle(x0 - 3, y0 - 3, x1 + 3, y1 + 3, outline=HINT, width=3, dash=(6, 4))
            text_col = PANEL_TEXT if not faded else FAINT
            dim_col = CARD_DIM_TEXT if not faded else FAINT
            cv.create_text(x0 + self.p(6), y0 + self.p(4), text=cell, anchor="nw", font=self.f["coord"], fill=dim_col)
            mark = MARK_COLOURS[self.marks.get(cell, 0)]
            if mark and verdict is None:
                round_rect(cv, x1 - self.p(18), y0 + self.p(6), x1 - self.p(6), y0 + self.p(18), r=3, fill=mark, outline=mark)
            colour = AVATAR_COLOURS[sum(map(ord, info["name"])) % len(AVATAR_COLOURS)]
            initials = info["name"][:2]
            if clue is None:
                cx, cy = (x0 + x1) / 2, y0 + self.p(40)
                cv.create_oval(cx - self.p(20), cy - self.p(20), cx + self.p(20), cy + self.p(20), fill=colour if not faded else FAINT, outline="")
                cv.create_text(cx, cy, text=initials, font=self.f["init"], fill="#1d1918")
                name_col = HINT if cell == hint_target else SELECT if cell == self.selected else text_col
                cv.create_text(cx, y0 + self.p(76), text=info["name"], font=self.f["name"], fill=name_col)
                cv.create_text(cx, y0 + self.p(94), text=info["job"], font=self.f["job"], fill=dim_col)
            else:
                ax, ay = x0 + self.p(18), y0 + self.p(30)
                cv.create_oval(ax - self.p(9), ay - self.p(9), ax + self.p(9), ay + self.p(9), fill=colour if not faded else FAINT, outline="")
                cv.create_text(ax, ay, text=initials, font=self.f["init_s"], fill="#1d1918")
                cv.create_text(ax + self.p(14), ay - self.p(6), text=info["name"], anchor="w", font=self.f["name_s"],
                               fill=HINT if cell in hint_clues else text_col)
                cv.create_text(ax + self.p(14), ay + self.p(6), text=info["job"], anchor="w", font=self.f["job"], fill=dim_col)
                self._draw_clue(cv, cell, clue, state, x0, y0 + self.p(44), x1, y1, faded, cell == self.focus_clue)

        if self.engine.is_solved():
            self.set_message("Solved! Every verdict was proved.", INNO_EDGE)

    def _draw_clue(self, cv, owner, clue, state, x0, y0, x1, y1, faded, focused):
        used = self._clue_used_up(owner, clue, state) and not focused
        words, colour_i = [], 0
        for text, cells in self._segments(clue, state):
            col = None
            if cells and focused:
                col = SEG_COLOURS[colour_i % len(SEG_COLOURS)]
            if cells:
                colour_i += 1
            for w in text.split():
                words.append((w, col))
        fnt = self.f["clue_x"] if used else self.f["clue"]
        lines = wrap_segments(words, fnt, (x1 - x0) - self.p(14), self.f["clue_b"])
        line_h = fnt.metrics("linespace")
        top = y0 + max(0, ((y1 - y0 - 6) - line_h * len(lines)) / 2)
        base = FAINT if faded or used else PANEL_TEXT
        space = fnt.measure(" ")
        for li, line in enumerate(lines):
            width = sum(w for _, _, w in line) + space * (len(line) - 1)
            x = (x0 + x1 - width) / 2
            for word, col, w in line:
                f = self.f["clue_b"] if col else fnt
                cv.create_text(x, top + li * line_h, text=word, anchor="nw", font=f, fill=col or base)
                x += w + space

    def set_message(self, text: str, colour: str = PANEL_TEXT):
        self.message.configure(text=text, fg=colour)

    def log(self, line: str):
        self.trace.configure(state="normal")
        self.trace.insert("end", line + "\n")
        self.trace.see("end")
        self.trace.configure(state="disabled")

    # ----- input

    def on_click(self, event):
        cell = self.cell_at(event.x, event.y)
        if cell is None:
            self.clear_focus()
            return
        if self.mark_mode and cell not in self.state["verdicts"]:
            self.marks[cell] = (self.marks.get(cell, 0) + 1) % len(MARK_COLOURS)
            self.redraw()
            return
        if cell in self.state["revealed"]:
            self.focus_clue = None if self.focus_clue == cell else cell
            self.selected = None
        elif cell not in self.state["verdicts"]:
            self.focus_clue = None
            self.open_dialog(cell)
            return
        self.redraw()

    def on_right_click(self, event):
        cell = self.cell_at(event.x, event.y)
        if cell and cell not in self.state["verdicts"]:
            self.marks[cell] = (self.marks.get(cell, 0) + 1) % len(MARK_COLOURS)
            self.redraw()

    # ----- dialogs (verdict choice, rejected verdict)

    def _dialog_frame(self):
        self.close_dialog()
        k = self.k
        d = tk.Frame(self.canvas, bg=DLG_BG, highlightthickness=1, highlightbackground="#4a423e",
                     padx=int(24 * k), pady=int(16 * k))
        self.dialog = d
        return d

    def _dialog_label(self, d, text, fnt, fg, **kw):
        lab = tk.Label(d, text=text, font=fnt, bg=DLG_BG, fg=fg, **kw)
        lab.pack()
        return lab

    def _dialog_button(self, row, text, command, bg, fg, edge):
        k = self.k
        b = tk.Label(row, text=text, font=self.f["ui_b"], bg=bg, fg=fg, width=11, pady=int(7 * k),
                     cursor="hand2", highlightthickness=2, highlightbackground=edge)
        b.pack(side="left", padx=int(5 * k))
        b.bind("<Button-1>", lambda _e: command())
        return b

    def open_dialog(self, cell: str):
        """Ask Innocent or Criminal for a face-down card."""
        d = self._dialog_frame()
        self.selected = cell
        self.redraw()
        info = next(c for c in self.state["cells"] if c["cell"] == cell)
        k = self.k
        avatar = tk.Canvas(d, width=int(56 * k), height=int(56 * k), bg=DLG_BG, highlightthickness=0)
        colour = AVATAR_COLOURS[sum(map(ord, info["name"])) % len(AVATAR_COLOURS)]
        avatar.create_oval(2, 2, 56 * k - 2, 56 * k - 2, fill=colour, outline="#f4efe8", width=2)
        avatar.create_text(28 * k, 28 * k, text=info["name"][:2], font=self.f["init"], fill="#1d1918")
        avatar.pack()
        self._dialog_label(d, info["name"], self.f["ui_b"], PANEL_TEXT)
        self._dialog_label(d, f"{cell} · {info['job']}", self.f["job"], MUTED)
        self._dialog_label(d, "Innocent or criminal?", self.f["dlg_title"], PANEL_TEXT,
                           pady=int(6 * k))
        self._dialog_label(d, "You can only lock a verdict the clues actually prove. "
                              "A correct call flips the card and reveals its clue.",
                           self.f["ui"], CARD_DIM_TEXT, wraplength=int(250 * k), justify="center")
        row = tk.Frame(d, bg=DLG_BG)
        row.pack(pady=(int(12 * k), int(6 * k)))
        self._dialog_button(row, "Innocent", lambda: self.submit(INNOCENT), INNO_BG, INNO_EDGE, INNO_EDGE)
        self._dialog_button(row, "Criminal", lambda: self.submit(CRIMINAL), CRIM_BG, CRIM_EDGE, CRIM_EDGE)
        cancel = self._dialog_label(d, "Cancel", self.f["ui"], MUTED, cursor="hand2")
        cancel.bind("<Button-1>", lambda _e: self.close_dialog(redraw=True))
        d.place(relx=0.5, rely=0.5, anchor="center")

    def open_rejected(self, cell: str, verdict: str, result: str):
        """Explain a NOT_PROVABLE / CONTRADICTED verdict."""
        d = self._dialog_frame()
        k = self.k
        name = self.names()[cell]
        other = INNOCENT if verdict == CRIMINAL else CRIMINAL
        icon = tk.Canvas(d, width=int(44 * k), height=int(44 * k), bg=DLG_BG, highlightthickness=0)
        icon_col = SELECT if result == NOT_PROVABLE else CRIM_EDGE
        icon.create_oval(2, 2, 44 * k - 2, 44 * k - 2, outline=icon_col, width=2, fill="#3a3122")
        icon.create_text(22 * k, 22 * k, text="!", font=self.f["dlg_title"], fill=icon_col)
        icon.pack()
        if result == NOT_PROVABLE:
            title = "Conclusion not possible"
            body = (f"You can't prove {name} is {verdict.lower()} from the clues you've unlocked yet: "
                    f"there's still a consistent case where {name} is {other.lower()}. "
                    "Unlock more clues first, or lean on a hint.")
        else:
            title = "Contradicted"
            body = (f"The clues you've unlocked prove {name} is {other.lower()}, "
                    f"so {name} can't be {verdict.lower()}.")
        self._dialog_label(d, title, self.f["dlg_title"], PANEL_TEXT, pady=int(6 * k))
        self._dialog_label(d, body, self.f["ui"], CARD_DIM_TEXT, wraplength=int(270 * k), justify="center")
        row = tk.Frame(d, bg=DLG_BG)
        row.pack(pady=(int(14 * k), 0))
        self._dialog_button(row, "Hint", lambda: (self.close_dialog(), self.hint()),
                            DLG_BG, PANEL_TEXT, "#5c5550")
        self._dialog_button(row, "Keep looking", lambda: self.close_dialog(redraw=True),
                            ACCENT, "#1d1918", ACCENT)
        d.place(relx=0.5, rely=0.5, anchor="center")
        self.redraw()

    def close_dialog(self, redraw: bool = False):
        if self.dialog is not None:
            self.dialog.destroy()
            self.dialog = None
            self.selected = None
            if redraw:
                self.redraw()

    def toggle_mark(self):
        self.mark_mode = not self.mark_mode
        self.btn_mark.set_accent(self.mark_mode)
        self.set_message("Mark mode: click a card to cycle a pencil colour." if self.mark_mode
                         else "Mark mode off.", MUTED)

    def clear_focus(self):
        self.selected = self.focus_clue = self.hint_state = None
        self.btn_hint.configure(text="Hint")
        self.btn_hint.set_accent(False)
        self.redraw()

    # ----- actions

    def ask_load(self):
        path = filedialog.askopenfilename(initialdir=PUZZLE_DIR, title="Load puzzle",
                                          filetypes=[("Puzzle JSON", "*.json")])
        if path:
            self.load(path)

    def load(self, path: str):
        self.stop_auto()
        try:
            puzzle = load_puzzle(path)
            self.engine = GameEngine(puzzle, self.agent)
        except Exception as e:  # show any loading error instead of crashing the window
            messagebox.showerror("Load failed", f"{path}\n\n{e}")
            return
        self.info.configure(text=f"PUZZLE {puzzle.id} · {puzzle.rows}×{puzzle.cols}")
        self.restart()

    def restart(self):
        if not self.engine:
            return
        self.stop_auto()
        self.close_dialog()
        self.engine.restart()
        self.agent.reset_stats()
        self.marks, self.step_no, self.last_accepted = {}, 0, None
        self.trace.configure(state="normal")
        self.trace.delete("1.0", "end")
        self.trace.configure(state="disabled")
        self.set_message("Click a face-down card to call it.", MUTED)
        self.clear_focus()

    def submit(self, verdict: str, cell: str | None = None, source: str = "you"):
        if not self.engine:
            return None
        cell = cell or self.selected
        if not cell:
            self.set_message("Click a face-down card first.", MUTED)
            return None
        state = self.state
        if cell in state["verdicts"]:
            return None
        self.close_dialog()
        try:
            result = self.engine.submit(cell, verdict)
        except NotImplementedError as e:
            self.set_message(f"Not implemented yet: {e}", CRIM_EDGE)
            return None
        name = self.names(state)[cell]
        self.set_message({
            ACCEPTED: f"Correct: {name} is {verdict.lower()}.",
            NOT_PROVABLE: f"Not provable yet: nothing forces {name} to be {verdict.lower()}.",
            CONTRADICTED: f"Contradicted: the clues prove {name} is not {verdict.lower()}.",
        }[result], RESULT_COLOURS[result])
        self.step_no += 1
        self.log(f"{self.step_no:>3}. {source:<5} {cell} {verdict:<9} {result}")
        if result == ACCEPTED:
            self.marks.pop(cell, None)
            self.last_accepted = cell
            self.selected = self.focus_clue = self.hint_state = None
            self.btn_hint.configure(text="Hint")
            self.btn_hint.set_accent(False)
        self.redraw()
        if result != ACCEPTED and source == "you":
            self.open_rejected(cell, verdict, result)
        return result

    def hint(self):
        """Hint: outline the clues to read. Reveal: also outline the card they prove. Clear."""
        if not self.engine or self.engine.is_solved():
            return
        if self.hint_state and self.hint_state["revealed"]:
            self.clear_focus()
            return
        if self.hint_state:
            self.hint_state["revealed"] = True
            name = self.names()[self.hint_state["cell"]]
            self.set_message(f"Reveal: {name} ({self.hint_state['cell']}) can be proved now.", HINT)
            self.btn_hint.configure(text="Clear")
            self.redraw()
            return
        state = self.state
        try:
            h = self.agent.hint(state)
        except NotImplementedError as e:
            self.set_message(f"Not implemented yet: {e}", CRIM_EDGE)
            return
        if h is None:
            stuck = self.agent.classify(state) == INCONSISTENT
            self.set_message("The clues contradict each other." if stuck else
                             "Nothing can be proved from the visible clues.", CRIM_EDGE)
            return
        self.hint_state = {**h, "revealed": False}
        self.focus_clue = self.selected = None
        names = self.names(state)
        clues = ", ".join(names[c] for c in h["because"]) or "the known verdicts"
        self.set_message(f"Hint: read the clue of {clues}.", HINT)
        self.btn_hint.configure(text="Reveal")
        self.btn_hint.set_accent(True)
        self.redraw()

    # ----- auto solve

    def toggle_auto(self):
        if self.auto_job:
            self.stop_auto()
        else:
            self.btn_auto.configure(text="Stop")
            self.btn_auto.set_accent(True)
            self.auto_step()

    def stop_auto(self):
        if self.auto_job:
            self.root.after_cancel(self.auto_job)
        self.auto_job = None
        if hasattr(self, "btn_auto"):
            self.btn_auto.configure(text="Auto Solve")
            self.btn_auto.set_accent(False)

    def auto_step(self, single: bool = False):
        self.auto_job = None
        if not self.engine or self.engine.is_solved():
            self.stop_auto()
            return
        try:
            move = self.agent.next_move(self.state)
        except NotImplementedError as e:
            self.set_message(f"Not implemented yet: {e}", CRIM_EDGE)
            self.stop_auto()
            return
        if move is None:
            self.set_message("Stuck: nothing can be proved. The agent does not guess.", CRIM_EDGE)
            self.stop_auto()
            return
        self.submit(move["verdict"], move["cell"], source="agent")
        if not single and not self.engine.is_solved():
            self.auto_job = self.root.after(AUTO_DELAY_MS, self.auto_step)
            self.btn_auto.configure(text="Stop")
            self.btn_auto.set_accent(True)
        elif not single:
            s = self.agent.stats
            self.log(f"SAT calls {s['sat_calls']} · decisions {s['decisions']} · "
                     f"propagations {s['propagations']} · backtracks {s['backtracks']} · "
                     f"{s['time']:.3f}s")
            self.stop_auto()


def run(puzzle_path: str | None = None) -> None:
    try:  # crisp text on Windows HiDPI screens
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = tk.Tk()
    root.minsize(int(root.winfo_fpixels("1i") / 96 * 980), int(root.winfo_fpixels("1i") / 96 * 640))
    App(root, puzzle_path)
    root.mainloop()
