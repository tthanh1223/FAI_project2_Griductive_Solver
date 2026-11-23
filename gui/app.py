"""Tkinter GUI.

Owner: GUI & Video.
Grid of cards, CRIMINAL / INNOCENT buttons, list of revealed clues with highlight,
Load / Restart / Hint / Step / Auto Solve / Theme. Always redraw from
engine.public_state(); never read hidden statuses.
Input / output of every function: docs/INTERFACES.md.

Files:  app.py (this: App + run), clue_text.py (clue_to_text), theme.py (colours,
fonts), widgets.py (drawing pieces). Keys: C criminal, I innocent, H hint,
Space step, Esc clear selection / highlight.
"""
import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

from gui.clue_text import clue_to_text
from gui.theme import THEMES, make_fonts
from gui.widgets import (AvatarCache, Banner, BoardView, ClueList, CrossedTapes, Divider, FlatButton,
                         LevelGrid, RoundPanel, StatsGrid, Tape)
from model import CRIMINAL, INNOCENT

__all__ = ["run", "clue_to_text"]

_PUZZLE_DIR = Path(__file__).resolve().parent.parent / "puzzles"
_AUTO_DELAY_MS = 400
_READY = ("info", "Ready", "Select a face-down card, then choose CRIMINAL or INNOCENT.")
_SIDE_PAD, _SIDE_GAP = 14, 12        # padding inside / gap between the right-hand panels
_LEFT_MIN, _RIGHT_MIN = 360, 440     # the divider cannot squeeze a column below this


def _scan_levels(folder=_PUZZLE_DIR):
    """Puzzles for the level menu, grouped by board size: [(title, [level, ...])].

    Only "id", the size and the generator's "difficulty" are read from each file:
    never a status or a clue, so the menu cannot leak the hidden solution.
    Stars: reveal waves per cell (a long chain of deductions = harder).
    """
    groups = {}
    for path in sorted(Path(folder).glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
            rows = int(data.get("rows", data.get("size")))
            cols = int(data.get("cols", data.get("size")))
        except (OSError, ValueError, TypeError, AttributeError):
            continue                               # unreadable file: not listed (Open file… still works)
        difficulty = data.get("difficulty")
        waves = difficulty.get("waves") if isinstance(difficulty, dict) else None
        if isinstance(waves, int) and waves > 0:
            ratio = waves / (rows * cols)
            stars = 1 if ratio < 0.45 else 2 if ratio < 0.7 else 3
            label = ("Easy", "Medium", "Hard")[stars - 1]
        else:
            stars, label = 0, "Hand-made"
        level = {"id": str(data.get("id", path.stem)), "file": str(path.resolve()),
                 "rows": rows, "cols": cols, "stars": stars, "label": label}
        groups.setdefault((rows, cols), []).append(level)

    def title(size):
        rows, cols = size
        return f"{cols} × {rows}" if rows == cols else f"{cols} × {rows} (special)"

    order = sorted(groups, key=lambda size: (size[0] != size[1], size[0] * size[1]))
    return [(title(size), sorted(groups[size], key=lambda lv: (lv["stars"] != 0, lv["id"]))) for size in order]


def _game_api():
    """Import the other parts lazily: the window still opens (with a clear message)
    if one of them is missing or broken."""
    import agent
    import encoder
    import engine
    import model
    return model, engine, agent, encoder


class App:
    """One window. All game facts come from engine.public_state(); App only keeps
    what the player did in the window (selection, highlighted clue, trace, ...)."""

    def __init__(self, root, puzzle_path=None):
        self.root = root
        self.theme_name = "light"
        self.fonts = make_fonts(root)
        self.avatars = AvatarCache(root)

        self.engine = None           # engine.GameEngine of the current puzzle
        self.agent = None            # the LogicAgent the engine uses (shared with Hint / Step)
        self.puzzle_file = ""
        self.selected = None         # face-down cell chosen for a verdict
        self.clue_focus = []         # face-up cells whose clue is highlighted
        self.feedback = _READY       # (kind, title, body) of the Verdict banner
        self.hint_text = None
        self.trace = []              # one dict per ACCEPTED move
        self.end_status = None       # "STUCK" / "INCONSISTENT" once the agent finds no move
        self._auto_job = None        # id from root.after while Auto Solve runs
        self._current_file = None    # absolute path of the loaded puzzle
        self.solved_files = set()    # puzzles solved in this session (✓ in the level menu)
        self._menu = None            # the level menu overlay while it is open
        self._resize_job = None

        root.title("Griductive Solver")
        root.geometry("1280x900")
        root.minsize(1100, 860)
        self._sash_x = None
        self._bind_keys()
        self._build()
        if puzzle_path:
            self.load(puzzle_path)
        else:
            self.render()
            self.root.after_idle(self._place_sash)
            self.show_levels()

    # ================================================================ layout

    @property
    def t(self):
        return THEMES[self.theme_name]

    def _build(self):
        """Create every widget for the current theme (called again on theme switch)."""
        t, f = self.t, self.fonts
        self.root.configure(bg=t["canvas"])
        self.frame = tk.Frame(self.root, bg=t["canvas"])
        self.frame.pack(fill="both", expand=True)

        # 1. top bar
        top = tk.Frame(self.frame, bg=t["panel"], padx=20, pady=12)
        top.pack(fill="x")
        titles = tk.Frame(top, bg=t["panel"])
        titles.pack(side="left")
        tk.Label(titles, text="Griductive Solver", font=f["title"], bg=t["panel"], fg=t["text"]).pack(anchor="w")
        self.subtitle = tk.Label(titles, text="", font=f["subtitle"], bg=t["panel"], fg=t["muted"])
        self.subtitle.pack(anchor="w")
        buttons = tk.Frame(top, bg=t["panel"])
        buttons.pack(side="right")
        self.btn = {}
        for key, label, command, kind in (
                ("levels", "Levels", self.show_levels, "secondary"),
                ("restart", "Restart", self.restart, "secondary"),
                ("hint", "Hint", self.hint, "secondary"),
                ("step", "Step", self.manual_step, "secondary"),
                ("theme", "Theme", self.toggle_theme, "secondary"),
                ("auto", "Auto Solve", self.toggle_auto, "primary")):
            width = f["button"].measure("Auto Solve") + 30 if key == "auto" else None
            b = FlatButton(buttons, label, command, t, f, kind, bg=t["panel"], width=width)
            b.pack(side="left", padx=(10, 0))
            self.btn[key] = b
        tk.Frame(self.frame, bg=t["border"], height=1).pack(fill="x")

        # 2. KEEP OUT tape
        Tape(self.frame, t, f).pack(fill="x")

        # 4. status bar (packed before the body so it keeps its place at the bottom)
        status = tk.Frame(self.frame, bg=t["panel"])
        status.pack(side="bottom", fill="x")
        tk.Frame(status, bg=t["border"], height=1).pack(fill="x")
        self.status = tk.Label(status, text="", font=f["status"], bg=t["panel"], fg=t["muted"],
                               anchor="w", padx=20, pady=6)
        self.status.pack(fill="x")

        # 3. body: board column | divider (drag it to resize) | side column
        body = tk.Frame(self.frame, bg=t["canvas"], padx=20, pady=20)
        body.pack(fill="both", expand=True)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(2, weight=1)
        self._body = body
        self._left_pane = tk.Frame(body, bg=t["canvas"], width=600)
        self._left_pane.grid(row=0, column=0, sticky="ns")
        self._left_pane.pack_propagate(False)     # its width is set by the divider, not its content
        Divider(body, t, self._drag_divider).grid(row=0, column=1, sticky="ns")
        right_pane = tk.Frame(body, bg=t["canvas"])
        right_pane.grid(row=0, column=2, sticky="nsew")
        body.bind("<Configure>", self._keep_right_room, add="+")

        # left: board panel on top, decorative tapes in the space left below (pack shrinks them first)
        self.left = tk.Frame(self._left_pane, bg=t["canvas"])
        self.left.pack(fill="both", expand=True)
        self.board_panel = RoundPanel(self.left, t)
        self.board_panel.pack(side="top", anchor="nw")
        tk.Label(self.board_panel.body, text="Board", font=f["panel_title"], bg=t["panel"],
                 fg=t["text"]).pack(anchor="w")
        self.board = BoardView(self.board_panel.body, t, f, self.avatars, self.click_card)
        self.board.pack(anchor="w", pady=(6, 0))
        CrossedTapes(self.left, t, f).pack(side="top", fill="both", expand=True, pady=(10, 0))
        self.left.bind("<Configure>", self._on_resize, add="+")
        self._left_size = None

        right = tk.Frame(right_pane, bg=t["canvas"])
        right.pack(fill="both", expand=True)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=3, minsize=96)      # Revealed clues
        right.rowconfigure(4, weight=2, minsize=96)      # Deduction trace

        # 3a. Verdict
        verdict = RoundPanel(right, t, pad=_SIDE_PAD)
        verdict.grid(row=0, column=0, sticky="ew", pady=(0, _SIDE_GAP))
        self._title(verdict.body, "Verdict")
        self.selected_label = tk.Label(verdict.body, text="", font=f["body"], bg=t["panel"], fg=t["text"], anchor="w")
        self.selected_label.pack(fill="x", pady=(2, 8))
        row = tk.Frame(verdict.body, bg=t["panel"])
        row.pack(fill="x")
        row.columnconfigure((0, 1), weight=1, uniform="verdict")
        self.btn["criminal"] = FlatButton(row, CRIMINAL, lambda: self.submit_selected(CRIMINAL), t, f,
                                          "criminal", bg=t["panel"], width=1, height=32)
        self.btn["criminal"].grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.btn["innocent"] = FlatButton(row, INNOCENT, lambda: self.submit_selected(INNOCENT), t, f,
                                          "innocent", bg=t["panel"], width=1, height=32)
        self.btn["innocent"].grid(row=0, column=1, sticky="ew", padx=(5, 0))
        self.banner = Banner(verdict.body, t, f, bg=t["panel"])
        self.banner.pack(fill="x", pady=(10, 0))

        # 3b. Revealed clues
        clues = RoundPanel(right, t, pad=_SIDE_PAD, fit=False)
        clues.grid(row=1, column=0, sticky="nsew", pady=(0, _SIDE_GAP))
        self._title(clues.body, "Revealed clues (click to highlight)")
        self.clue_list = ClueList(clues.body, t, f, self.click_clue)
        self.clue_list.pack(fill="both", expand=True, pady=(8, 0))

        # 3c. Hint
        hint = RoundPanel(right, t, fill=t["hint_bg"], outline=t["hint_border"], pad=_SIDE_PAD)
        hint.grid(row=2, column=0, sticky="ew", pady=(0, _SIDE_GAP))
        tk.Label(hint.body, text="Hint", font=f["panel_title"], bg=t["hint_bg"], fg=t["text"]).pack(anchor="w")
        self.hint_label = tk.Label(hint.body, text="", font=f["body"], bg=t["hint_bg"], fg=t["text"],
                                   justify="left", anchor="w")
        self.hint_label.pack(fill="x", pady=(4, 0))
        hint.body.bind("<Configure>", lambda e: self.hint_label.configure(wraplength=max(100, e.width - 4)), add="+")

        # 3d. Solver stats
        stats = RoundPanel(right, t, pad=_SIDE_PAD)
        stats.grid(row=3, column=0, sticky="ew", pady=(0, _SIDE_GAP))
        self._title(stats.body, "Solver stats")
        self.stats = StatsGrid(stats.body, t, f, bg=t["panel"])
        self.stats.pack(fill="x", pady=(8, 0))

        # 3e. Deduction trace: read-only Text, one wrapped line per accepted move
        trace = RoundPanel(right, t, pad=_SIDE_PAD, fit=False)
        trace.grid(row=4, column=0, sticky="nsew")
        self._title(trace.body, "Deduction trace")
        box = RoundPanel(trace.body, t, fill=t["canvas"], outline=t["canvas"], bg=t["panel"],
                         radius=8, pad=6, fit=False)
        box.pack(fill="both", expand=True, pady=(8, 0))
        self.trace_text = tk.Text(box.body, font=f["mono"], bg=t["canvas"], fg=t["text"], relief="flat",
                                  highlightthickness=0, bd=0, wrap="word", height=3, width=10, padx=6, pady=4,
                                  cursor="arrow")
        self.trace_text.tag_configure("line", lmargin2=28, spacing1=2)
        trace_scroll = tk.Scrollbar(box.body, orient="vertical", command=self.trace_text.yview)
        self.trace_text.configure(yscrollcommand=self._autohide(trace_scroll), state="disabled")
        self.trace_text.pack(side="left", fill="both", expand=True)
        self._trace_drawn = None     # number of trace lines currently in the Text widget

    def _title(self, parent, text):
        tk.Label(parent, text=text, font=self.fonts["panel_title"], bg=self.t["panel"],
                 fg=self.t["text"]).pack(anchor="w")

    @staticmethod
    def _autohide(scroll):
        """yscrollcommand that shows the scrollbar only when the content does not fit."""
        def command(first, last):
            scroll.set(first, last)
            if float(first) > 0 or float(last) < 1:
                if not scroll.winfo_ismapped():
                    scroll.pack(side="right", fill="y")
            elif scroll.winfo_ismapped():
                scroll.pack_forget()
        return command

    def _bind_keys(self):
        for keys, action in ((("c", "C"), lambda: self.submit_selected(CRIMINAL)),
                             (("i", "I"), lambda: self.submit_selected(INNOCENT)),
                             (("h", "H"), self.hint),
                             (("space",), self.manual_step),
                             (("Escape",), self._escape)):
            for key in keys:
                self.root.bind(f"<KeyPress-{key}>", lambda e, a=action: a())

    def _escape(self):
        """Esc closes the level menu, otherwise clears selection and highlight."""
        if self._menu is not None:
            if self.engine is not None:
                self.hide_levels()
        else:
            self.clear_selection()

    # ================================================================ level menu

    def show_levels(self):
        """Cover the body with the level menu (a grid of puzzles grouped by size)."""
        self._stop_auto()
        self.hide_levels()
        t, f = self.t, self.fonts
        overlay = tk.Frame(self._body, bg=t["canvas"])
        overlay.place(x=20, y=20, relwidth=1, width=-40, relheight=1, height=-40)
        overlay.lift()
        panel = RoundPanel(overlay, t, fit=False, pad=24)
        panel.place(relx=0, rely=0, relwidth=1, relheight=1)
        head = tk.Frame(panel.body, bg=t["panel"])
        head.pack(fill="x")
        titles = tk.Frame(head, bg=t["panel"])
        titles.pack(side="left")
        tk.Label(titles, text="Choose a case", font=f["title"], bg=t["panel"], fg=t["text"]).pack(anchor="w")
        tk.Label(titles, text="Click a puzzle to play it. Stars show how long its chain of deductions is.",
                 font=f["subtitle"], bg=t["panel"], fg=t["muted"]).pack(anchor="w")
        if self.engine is not None:
            FlatButton(head, "Back to game", self.hide_levels, t, f, "primary", bg=t["panel"]).pack(side="right")
        FlatButton(head, "Open file…", self.ask_load, t, f, "secondary", bg=t["panel"]).pack(side="right", padx=(0, 10))
        groups = _scan_levels()
        if groups:
            LevelGrid(panel.body, t, f, groups, self._pick_level, self._current_file,
                      self.solved_files).pack(fill="both", expand=True, pady=(18, 0))
        else:
            tk.Label(panel.body, text=f"No puzzle found in {_PUZZLE_DIR}. Use Open file….", font=f["body"],
                     bg=t["panel"], fg=t["muted"]).pack(anchor="w", pady=(18, 0))
        self._menu = overlay
        self._render_buttons(self.state())

    def hide_levels(self):
        if self._menu is not None:
            self._menu.destroy()
            self._menu = None
            self._render_buttons(self.state())

    def _pick_level(self, path):
        self.hide_levels()
        if not self.load(path) and self.engine is None:
            self.show_levels()                    # load failed and there is no game behind the menu

    def _on_resize(self, event):
        """The card size follows the left column (divider position and window height):
        redraw once after its size changes."""
        if (event.width, event.height) != self._left_size:
            self._left_size = (event.width, event.height)
            if self._resize_job is not None:
                self.root.after_cancel(self._resize_job)
            self._resize_job = self.root.after(80, self._after_resize)

    def _after_resize(self):
        self._resize_job = None
        self.render()

    def _place_sash(self, x=None):
        """Set the board column to x px wide, or to the width where cards have their
        normal size (140 px). Kept between the smallest board and the side column's minimum."""
        state = self.state()
        rows, cols = (state["rows"], state["cols"]) if state else (3, 3)
        if x is None:
            x = (self.board.natural_width(rows, cols) if state else 560) + 2 * self.board_panel.pad
        self._body.update_idletasks()
        pad2 = 2 * self.board_panel.pad
        low = max(_LEFT_MIN, self.board.min_width(cols) + pad2)
        inner = self._body.winfo_width() - 40 - Divider.WIDTH       # minus the body padding
        high = max(low, inner - _RIGHT_MIN) if inner > 0 else max(low, int(x))
        if state:                         # never wider than the biggest board: the panel fills the column
            high = max(low, min(high, self.board.max_width(cols) + pad2))
        x = max(low, min(int(x), high))
        if int(self._left_pane["width"]) != x:
            self._left_pane.configure(width=x)
        self._sash_x = x

    def _drag_divider(self, x_root):
        """Divider dragged: the board column ends where the pointer is."""
        self._place_sash(x_root - self._left_pane.winfo_rootx() - Divider.WIDTH // 2)

    def _keep_right_room(self, _event=None):
        """Window resized: keep the divider inside the allowed range."""
        if self._sash_x is not None:
            self._place_sash(self._sash_x)

    # ================================================================ drawing

    def state(self):
        """A fresh engine.public_state(), or None when there is no game (or it cannot be read)."""
        if self.engine is None:
            return None
        try:
            return self.engine.public_state()
        except Exception as e:
            self.feedback = self._error_feedback("public_state failed", e)
            return None

    def render(self):
        """Redraw everything from engine.public_state() (nothing is updated piece by piece)."""
        state = self.state()
        self._render_buttons(state)
        if state is None:
            self._render_empty()
            return

        names = {c["cell"]: c["name"] for c in state["cells"]}
        info = {c["cell"]: c for c in state["cells"]}
        order = [c["cell"] for c in state["cells"]]
        texts = {cell: self._clue_sentence(clue, names) for cell, clue in state["revealed"].items()}

        self.subtitle.configure(text=f"Puzzle: {self.puzzle_file}  ·  {state['cols']} × {state['rows']}"
                                     f"  ·  Step {len(self.trace)}")
        self.board.draw(state["cells"], state["rows"], state["cols"], texts, state["verdicts"],
                        self.selected, self._highlighted(state), self._board_max_width(),
                        self._board_max_height())
        self.board_panel.set_width(self.board.winfo_reqwidth())

        if self.selected in info:
            c = info[self.selected]
            self.selected_label.configure(text=f"Selected: {c['cell']} — {c['name']} ({c['job']})")
        else:
            self.selected_label.configure(text="Selected: — (click a face-down card)")
        self.banner.set(*self.feedback)

        clue_rows = [(cell, texts[cell]) for cell in order if cell in state["revealed"]]
        self.clue_list.set(clue_rows, self.clue_focus)
        self.hint_label.configure(text=self.hint_text or
                                  "Press Hint (H) to see a card that can be proved now and the clues to read.")
        kb = self._kb_stats(state)
        self.stats.set(self._stat_items(kb))
        self._render_trace()

        solved = len(state["verdicts"])
        total = state["rows"] * state["cols"]
        kb_text = f"KB: {kb['primary']} primary · {kb['aux']} aux · {kb['clauses']} clauses" if kb else "KB: —"
        self.status.configure(text=f"Status: {self._status_word()}      Solved {solved} / {total}      {kb_text}")

    def _render_empty(self):
        """No game: empty board and neutral panels."""
        self.subtitle.configure(text="No puzzle loaded")
        self.board.draw_empty("No puzzle loaded", "Press Load and pick a file in puzzles/, e.g. p3_01.json.")
        self.board_panel.set_width(self.board.winfo_reqwidth())
        self.selected_label.configure(text="Selected: —")
        self.banner.set(*(self.feedback if self.engine else ("info", "No puzzle", "Load a puzzle to start playing.")))
        self.clue_list.set([], [])
        self.hint_label.configure(text="Load a puzzle first.")
        self.stats.set(self._stat_items(None))
        self._render_trace()
        self.status.configure(text=f"Status: {self._status_word()}")

    def _render_buttons(self, state):
        auto = self._auto_job is not None
        playable = state is not None and self._safe_is_solved() is False and self._menu is None
        self.btn["restart"].set_enabled(self.engine is not None and not auto and self._menu is None)
        self.btn["hint"].set_enabled(playable and not auto)
        self.btn["step"].set_enabled(playable and not auto)
        self.btn["auto"].set_enabled(playable or auto)
        self.btn["auto"].set_text("Stop" if auto else "Auto Solve")
        can_judge = playable and self.selected is not None and not auto
        self.btn["criminal"].set_enabled(can_judge)
        self.btn["innocent"].set_enabled(can_judge)

    def _board_max_width(self):
        """Pixels the board canvas may use: the left column minus the panel padding."""
        width = self.left.winfo_width()
        if width <= 1:
            return None                       # not laid out yet: normal card size
        return width - 2 * self.board_panel.pad

    def _board_max_height(self):
        """Pixels the board canvas may use: the left column minus the panel padding and title."""
        height = self.left.winfo_height()
        if height <= 1:                       # not laid out yet: estimate from the window size
            height = self.root.winfo_height() if self.root.winfo_height() > 1 else 900
            height -= 170
        return height - 2 * self.board_panel.pad - self.fonts["panel_title"].metrics("linespace") - 8

    def _clue_sentence(self, clue, names):
        try:
            return clue_to_text(clue, names)
        except (KeyError, ValueError, TypeError):
            return str(clue)                     # never crash the window on an odd clue

    def _highlighted(self, state):
        """Cells mentioned by the highlighted clue(s), via model.cells_in_clue."""
        cells = set()
        try:
            model = _game_api()[0]
            for cell in self.clue_focus:
                if cell in state["revealed"]:
                    cells.update(model.cells_in_clue(state["revealed"][cell], state["rows"], state["cols"]))
        except Exception:                        # highlight is decoration: ignore failures
            pass
        return cells

    def _kb_stats(self, state):
        """encoder.build_kb(state)[2] = {"primary", "aux", "clauses"} of the current KB."""
        try:
            return _game_api()[3].build_kb(state)[2]
        except Exception:
            return None

    def _stat_items(self, kb):
        s = self.agent.stats if self.agent else None

        def get(d, key):
            return "—" if not d else str(d.get(key, "—"))

        time_text = f"{s['time']:.3f} s" if s else "—"
        return [(get(kb, "primary"), "Primary vars"), (get(kb, "aux"), "Aux vars"),
                (get(kb, "clauses"), "Clauses"), (get(s, "sat_calls"), "SAT calls"),
                (get(s, "decisions"), "Decisions"), (get(s, "propagations"), "Propagations"),
                (get(s, "backtracks"), "Backtracks"), (time_text, "Time")]

    def _render_trace(self):
        """Rewrite the trace only when it changed, so the reader's scroll position stays."""
        if self._trace_drawn == len(self.trace):
            return
        box = self.trace_text
        box.configure(state="normal")
        box.delete("1.0", "end")
        if not self.trace:
            box.insert("end", "No step yet.")
        for i, s in enumerate(self.trace):
            line = (f"#{s['step']}  {s['cell']} → {s['verdict']}   clues [{', '.join(s['active'])}]"
                    f"   SAT {s['sat']}   revealed: {s['revealed']}")
            box.insert("end", ("\n" if i else "") + line, "line")
        box.configure(state="disabled")
        box.see("end")
        self._trace_drawn = len(self.trace)

    def _status_word(self):
        if self.engine is None:
            return "NO PUZZLE"
        if self._safe_is_solved():
            return "SOLVED"
        return self.end_status or "IN PROGRESS"

    def _safe_is_solved(self):
        """engine.is_solved(), or None if it fails."""
        try:
            return self.engine.is_solved() if self.engine else None
        except Exception:
            return None

    # ================================================================ actions

    def ask_load(self):
        path = filedialog.askopenfilename(parent=self.root, title="Load puzzle",
                                          initialdir=str(_PUZZLE_DIR),
                                          filetypes=[("Puzzle JSON", "*.json"), ("All files", "*.*")])
        if path:
            self.load(path)

    def load(self, path):
        """load_puzzle(path) -> GameEngine(puzzle, agent). On error keep the current game."""
        try:
            model, engine, agent, _ = _game_api()
            puzzle = model.load_puzzle(str(path))
            new_agent = agent.LogicAgent()
            new_engine = engine.GameEngine(puzzle, new_agent)
        except NotImplementedError as e:
            messagebox.showerror("Not implemented yet",
                                 f"A function this window needs is not written yet:\n{e or 'NotImplementedError'}",
                                 parent=self.root)
            return False
        except Exception as e:
            messagebox.showerror("Cannot load puzzle", f"{Path(path).name}\n\n{type(e).__name__}: {e}",
                                 parent=self.root)
            return False
        self._stop_auto()
        self.hide_levels()
        self.engine, self.agent = new_engine, new_agent
        self.puzzle_file = Path(path).name
        self._current_file = str(Path(path).resolve())
        self._reset_play()
        self.render()
        self.root.after_idle(self._place_sash)        # new puzzle: board at its normal size
        return True

    def restart(self):
        if not self.engine or self._menu is not None:
            return
        self._stop_auto()
        try:
            self.engine.restart()
            self.agent.reset_stats()
        except Exception as e:
            self._error("restart failed", e)
            return
        self._reset_play()
        self.render()

    def _reset_play(self):
        self.selected, self.clue_focus, self.trace = None, [], []
        self.feedback, self.hint_text, self.end_status = _READY, None, None

    def toggle_theme(self):
        self.theme_name = "dark" if self.theme_name == "light" else "light"
        sash, menu_open = self._sash_x, self._menu is not None
        self._menu = None                      # destroyed with the old frame
        self.frame.destroy()
        self._build()
        self.render()
        self.root.after_idle(lambda: self._place_sash(sash))
        if menu_open:
            self.show_levels()

    def clear_selection(self):
        self.selected, self.clue_focus = None, []
        self.render()

    def click_card(self, cell):
        state = self.state()
        if state is None:
            return
        if cell in state["revealed"]:                       # face-up: show what its clue talks about
            self.clue_focus = [] if self.clue_focus == [cell] else [cell]
        elif self._auto_job is None:                        # face-down: choose it for a verdict
            self.selected = None if self.selected == cell else cell
        self.render()

    def click_clue(self, cell):
        self.clue_focus = [] if self.clue_focus == [cell] else [cell]
        self.render()

    def submit_selected(self, verdict):
        if (self.engine and self.selected and self._auto_job is None and self._menu is None
                and self._safe_is_solved() is False):
            self._submit(self.selected, verdict)

    def _submit(self, cell, verdict, sat_before=None):
        """engine.submit -> ACCEPTED / NOT_PROVABLE / CONTRADICTED, then redraw.

        The trace's SAT count is agent.stats["sat_calls"] after minus before this move
        (for Step: before next_move, which is where the agent does the work).
        """
        before = self.state()
        if before is None:
            self.render()
            return None
        active = [c["cell"] for c in before["cells"] if c["cell"] in before["revealed"]]
        if sat_before is None:
            sat_before = self.agent.stats["sat_calls"]
        try:
            _, engine, _, _ = _game_api()
            result = self.engine.submit(cell, verdict)
            state = self.engine.public_state()
        except Exception as e:
            self._error("submit failed", e)
            return None
        name = next(c["name"] for c in state["cells"] if c["cell"] == cell)
        if result == engine.ACCEPTED:
            names = {c["cell"]: c["name"] for c in state["cells"]}
            self.trace.append({"step": len(self.trace) + 1, "cell": cell, "verdict": verdict, "active": active,
                               "sat": self.agent.stats["sat_calls"] - sat_before,
                               "revealed": self._clue_sentence(state["revealed"][cell], names)})
            self.selected, self.hint_text, self.end_status = None, None, None
            if self._safe_is_solved():
                self.solved_files.add(self._current_file)
                self.feedback = ("ok", "SOLVED", f"All {len(state['verdicts'])} cards are decided "
                                                 f"in {len(self.trace)} steps, without guessing.")
            else:
                self.feedback = ("ok", "ACCEPTED", f"{cell} ({name}) is {verdict}. The card is turned face-up "
                                                   "and its clue joins the knowledge base.")
        elif result == engine.NOT_PROVABLE:
            self.feedback = ("warn", "NOT_PROVABLE",
                             "Neither verdict is forced by the current clues. Card stays face-down.")
        else:
            other = INNOCENT if verdict == CRIMINAL else CRIMINAL
            self.feedback = ("error", "CONTRADICTED",
                             f"The revealed clues prove {cell} ({name}) is {other}. Card stays face-down.")
        self.render()
        return result

    def hint(self):
        """agent.hint(state) -> {"cell", "verdict", "because"}: explain, select the cell, highlight the clues."""
        state = self.state()
        if (state is None or self._safe_is_solved() is not False or self._auto_job is not None
                or self._menu is not None):
            return
        try:
            h = self.agent.hint(state)
        except Exception as e:
            self._error("hint failed", e)
            return
        if h is None:
            self._no_move(state)
        else:
            names = {c["cell"]: c["name"] for c in state["cells"]}
            first, rest = h["because"][0], h["because"][1:]
            text = f"Look at clue {first} (“{self._clue_sentence(state['revealed'][first], names)}”)"
            if rest:
                text += " together with " + ", ".join(rest)
            self.hint_text = f"{text} → {h['cell']} can be proved {h['verdict']}."
            self.selected, self.clue_focus = h["cell"], list(h["because"])
        self.render()

    def manual_step(self):
        """Step button / Space key: ignored while Auto Solve runs or the level menu is open."""
        if self._auto_job is None and self._menu is None:
            self.step()

    def step(self):
        """One automatic move: agent.next_move(state) -> engine.submit(...). Returns True if a card was turned."""
        state = self.state()
        if state is None or self._safe_is_solved() is not False:
            return False
        sat_before = self.agent.stats["sat_calls"]
        try:
            _, engine, _, _ = _game_api()
            move = self.agent.next_move(state)
        except Exception as e:
            self._error("next_move failed", e)
            return False
        if move is None:
            self._no_move(state)
            self.render()
            return False
        return self._submit(move["cell"], move["verdict"], sat_before) == engine.ACCEPTED

    def _no_move(self, state):
        """No forced cell: the KB is INCONSISTENT, or the game is STUCK."""
        try:
            _, _, agent, _ = _game_api()
            inconsistent = self.agent.classify(state) == agent.INCONSISTENT
        except Exception:
            inconsistent = False
        if inconsistent:
            self.end_status = "INCONSISTENT"
            self.feedback = ("error", "INCONSISTENT", "The revealed clues contradict each other.")
            self.hint_text = "The knowledge base is inconsistent: no card can be judged."
        else:
            self.end_status = "STUCK"
            self.feedback = ("warn", "STUCK", "No face-down card can be proved from the revealed clues.")
            self.hint_text = "No card can be proved right now (STUCK)."

    def toggle_auto(self):
        if self._auto_job is not None:
            self._stop_auto()
            self.render()
        elif self.engine and self._safe_is_solved() is False and self._menu is None:
            self._auto_job = self.root.after(0, self._auto_tick)
            self.render()

    def _auto_tick(self):
        """One Auto Solve move, then schedule the next one with root.after (no while loop:
        the window must keep handling clicks and redraws between moves)."""
        self._auto_job = "running"
        moved = self.step()
        if moved and self._auto_job is not None and self._safe_is_solved() is False:
            self._auto_job = self.root.after(_AUTO_DELAY_MS, self._auto_tick)
        else:
            self._auto_job = None
            self.render()

    def _stop_auto(self):
        if self._auto_job not in (None, "running"):
            self.root.after_cancel(self._auto_job)
        self._auto_job = None

    @staticmethod
    def _error_feedback(what, error):
        if isinstance(error, NotImplementedError):
            return ("error", "Not implemented yet", f"{what}: a function this needs is not written yet.")
        return ("error", "Error", f"{what}: {type(error).__name__}: {error}")

    def _error(self, what, error):
        self.feedback = self._error_feedback(what, error)
        self._stop_auto()
        self.render()


def run(puzzle_path: str | None = None) -> None:
    """Open the window (optionally with a puzzle already loaded) and run the Tk event loop."""
    root = tk.Tk()
    App(root, puzzle_path)
    root.mainloop()
