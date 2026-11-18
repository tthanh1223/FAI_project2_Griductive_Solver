"""Tkinter GUI.

Grid of cards, CRIMINAL / INNOCENT buttons, list of revealed clues with highlight,
Load / Restart / Hint / Auto Solve. Always redraw from engine.public_state();
never read hidden statuses.
Input / output of every function: docs/INTERFACES.md.

Keys: click a card to select it, C = criminal, I = innocent, H = hint, Space = one auto step.
"""
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font, messagebox

from agent import INCONSISTENT, LogicAgent
from engine import ACCEPTED, CONTRADICTED, NOT_PROVABLE, GameEngine
from model import CRIMINAL, INNOCENT, cells_in_clue, load_puzzle

PUZZLE_DIR = Path(__file__).resolve().parents[1] / "puzzles"
AUTO_DELAY_MS = 400
CARD_W, CARD_H = 150, 120

# Colours: plain, readable, one accent per meaning.
BG = "#f4f1ea"
CARD_DOWN = "#d9d4c7"
CARD_UP = "#fffdf8"
CRIM_BG, CRIM_EDGE = "#f6d5d1", "#c0392b"
INNO_BG, INNO_EDGE = "#d6eedb", "#2e8b57"
EDGE = "#8a8578"
SELECT_EDGE = "#1f3a93"
HIGHLIGHT = "#f7e27a"
HINT_EDGE = "#e67e22"
TEXT, MUTED = "#222222", "#6b665c"
RESULT_COLOURS = {ACCEPTED: "#2e8b57", NOT_PROVABLE: "#b9770e", CONTRADICTED: "#c0392b"}


# ---------------------------------------------------------------- clue text

def _who(cell: str, names: dict[str, str]) -> str:
    return names.get(cell, cell)


def _region_text(region: dict, names: dict[str, str]) -> str:
    kind = region.get("kind")
    if kind == "row":
        return f"row {region['row']}"
    if kind == "col":
        return f"column {region['col']}"
    if kind == "neighbors":
        return f"{_who(region['of'], names)}'s neighbors"
    if kind == "cells":
        return ", ".join(_who(c, names) for c in region["cells"])
    if kind == "all":
        return "the whole board"
    if kind == "edges":
        return "the edges"
    if kind == "corners":
        return "the corners"
    if kind in ("above", "below"):
        return f"the cells {kind} {_who(region['of'], names)}"
    if kind in ("left", "right"):
        return f"the cells to the {kind} of {_who(region['of'], names)}"
    if kind == "inter":
        return " and also in ".join(_region_text(r, names) for r in region["regions"])
    return str(region)


def _plural(k: int, word: str) -> str:
    return f"{k} {word}" if k == 1 else f"{k} {word}s"


def clue_to_text(clue: dict, names: dict[str, str]) -> str:
    """JSON clue -> readable sentence, e.g. "Exactly 1 criminal in row 2"."""
    t = clue.get("type")
    word = "innocent" if clue.get("count") == "innocent" else "criminal"
    if t == "NONE":
        return clue.get("text", "(no information)")
    if t == "FACT":
        return f"{_who(clue['who'], names)} is {clue['status'].lower()}."
    if t == "SAME":
        return f"{_who(clue['a'], names)} and {_who(clue['b'], names)} are on the same side."
    if t == "DIFFERENT":
        return f"{_who(clue['a'], names)} and {_who(clue['b'], names)} are on different sides."
    if t in ("EXACTLY", "AT_LEAST", "AT_MOST"):
        k = clue["k"]
        where = _region_text(clue["region"], names)
        if t == "EXACTLY" and k == 0:
            return f"There are no {word}s in {where}."
        lead = {"EXACTLY": "Exactly", "AT_LEAST": "At least", "AT_MOST": "At most"}[t]
        return f"{lead} {_plural(k, word)} in {where}."
    if t == "COMPARE":
        op = {">": "more", "<": "fewer", "=": "the same number of"}[clue["op"]]
        r1 = _region_text(clue["r1"], names)
        r2 = _region_text(clue["r2"], names)
        if clue["op"] == "=":
            return f"{r1.capitalize()} has the same number of {word}s as {r2}."
        return f"{r1.capitalize()} has {op} {word}s than {r2}."
    if t == "CONNECTED":
        return f"All {word}s in {_region_text(clue['region'], names)} are connected."
    if t == "AND":
        parts = [clue_to_text(p, names).rstrip(".") for p in clue["parts"]]
        return "; ".join(parts) + "."
    return str(clue)


# ---------------------------------------------------------------- card widget

class Card(tk.Frame):
    """One cell: coordinate, name, job, clue (if face-up). Click to select."""

    def __init__(self, master, cell: str, name: str, job: str, on_click, fonts):
        super().__init__(master, width=CARD_W, height=CARD_H, highlightthickness=3,
                         highlightbackground=EDGE, bg=CARD_DOWN, cursor="hand2")
        self.cell = cell
        self.pack_propagate(False)
        self.coord = tk.Label(self, text=cell, font=fonts["small"], fg=MUTED, anchor="w")
        self.name = tk.Label(self, text=name, font=fonts["bold"], fg=TEXT)
        self.job = tk.Label(self, text=job, font=fonts["small"], fg=MUTED)
        self.clue = tk.Label(self, text="?", font=fonts["clue"], fg=TEXT,
                             wraplength=CARD_W - 16, justify="center")
        self.coord.pack(fill="x", padx=6, pady=(2, 0))
        self.name.pack()
        self.job.pack()
        self.clue.pack(expand=True, fill="both", padx=4, pady=(0, 4))
        for w in (self, self.coord, self.name, self.job, self.clue):
            w.bind("<Button-1>", lambda _e: on_click(cell))

    def show(self, status: str | None, clue_text: str | None, edge: str, highlighted: bool):
        if status == CRIMINAL:
            bg = CRIM_BG
        elif status == INNOCENT:
            bg = INNO_BG
        else:
            bg = CARD_DOWN
        if highlighted:
            bg = HIGHLIGHT
        self.configure(bg=bg, highlightbackground=edge)
        for w in (self.coord, self.name, self.job, self.clue):
            w.configure(bg=bg)
        self.clue.configure(text=clue_text if clue_text is not None else "?")


# ---------------------------------------------------------------- app

class App:
    def __init__(self, root: tk.Tk, puzzle_path: str | None = None):
        self.root = root
        self.agent = LogicAgent()
        self.engine: GameEngine | None = None
        self.cards: dict[str, Card] = {}
        self.selected: str | None = None
        self.highlight: set[str] = set()
        self.hint_cell: str | None = None
        self.auto_job = None
        self.step_no = 0

        root.title("Griductive Solver")
        root.configure(bg=BG)
        self.fonts = {
            "small": font.Font(family="Segoe UI", size=8),
            "bold": font.Font(family="Segoe UI", size=10, weight="bold"),
            "clue": font.Font(family="Segoe UI", size=9),
            "big": font.Font(family="Segoe UI", size=11, weight="bold"),
        }
        self._build_layout()
        root.bind("<Key-c>", lambda _e: self.submit(CRIMINAL))
        root.bind("<Key-i>", lambda _e: self.submit(INNOCENT))
        root.bind("<Key-h>", lambda _e: self.hint())
        root.bind("<space>", lambda _e: self.auto_step(single=True))
        if puzzle_path:
            self.load(puzzle_path)
        else:
            self.set_message("Load a puzzle to start.", MUTED)

    # ----- layout

    def _build_layout(self):
        bar = tk.Frame(self.root, bg=BG)
        bar.pack(fill="x", padx=12, pady=(10, 4))
        for text, cmd in (("Load", self.ask_load), ("Restart", self.restart),
                          ("Hint", self.hint), ("Auto Solve", self.toggle_auto)):
            b = tk.Button(bar, text=text, command=cmd, width=10, relief="groove")
            b.pack(side="left", padx=(0, 6))
            if text == "Auto Solve":
                self.auto_button = b
        self.title_label = tk.Label(bar, text="", bg=BG, fg=MUTED, font=self.fonts["small"])
        self.title_label.pack(side="right")

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=12, pady=4)
        self.board = tk.Frame(body, bg=BG)
        self.board.pack(side="left", anchor="n")

        side = tk.Frame(body, bg=BG, width=320)
        side.pack(side="left", fill="both", expand=True, padx=(14, 0))

        tk.Label(side, text="Selected", bg=BG, fg=MUTED, font=self.fonts["small"]).pack(anchor="w")
        self.selected_label = tk.Label(side, text="-", bg=BG, fg=TEXT, font=self.fonts["big"])
        self.selected_label.pack(anchor="w")
        buttons = tk.Frame(side, bg=BG)
        buttons.pack(anchor="w", pady=4)
        tk.Button(buttons, text="CRIMINAL (C)", width=13, fg=CRIM_EDGE,
                  command=lambda: self.submit(CRIMINAL)).pack(side="left", padx=(0, 6))
        tk.Button(buttons, text="INNOCENT (I)", width=13, fg=INNO_EDGE,
                  command=lambda: self.submit(INNOCENT)).pack(side="left")
        self.message = tk.Label(side, text="", bg=BG, font=self.fonts["bold"],
                                wraplength=290, justify="left", anchor="w")
        self.message.pack(fill="x", pady=(6, 10))

        tk.Label(side, text="Revealed clues (click to highlight)", bg=BG, fg=MUTED,
                 font=self.fonts["small"]).pack(anchor="w")
        self.clue_list = tk.Listbox(side, height=9, activestyle="none", exportselection=False,
                                    font=self.fonts["clue"])
        self.clue_list.pack(fill="x")
        self.clue_list.bind("<<ListboxSelect>>", self.on_clue_select)
        self.clue_cells: list[str] = []

        tk.Label(side, text="Trace", bg=BG, fg=MUTED, font=self.fonts["small"]).pack(anchor="w", pady=(10, 0))
        self.trace = tk.Text(side, height=10, width=44, font=self.fonts["small"], state="disabled")
        self.trace.pack(fill="both", expand=True)

    def _build_board(self):
        for w in self.board.winfo_children():
            w.destroy()
        state = self.engine.public_state()
        rows, cols = state["rows"], state["cols"]
        for c in range(cols):
            tk.Label(self.board, text=chr(65 + c), bg=BG, fg=MUTED,
                     font=self.fonts["bold"]).grid(row=0, column=c + 1)
        for r in range(rows):
            tk.Label(self.board, text=str(r + 1), bg=BG, fg=MUTED,
                     font=self.fonts["bold"]).grid(row=r + 1, column=0, padx=(0, 4))
        self.cards = {}
        for i, info in enumerate(state["cells"]):
            r, c = divmod(i, cols)
            card = Card(self.board, info["cell"], info["name"], info["job"], self.select, self.fonts)
            card.grid(row=r + 1, column=c + 1, padx=3, pady=3)
            self.cards[info["cell"]] = card

    # ----- drawing

    def names(self, state) -> dict[str, str]:
        return {c["cell"]: c["name"] for c in state["cells"]}

    def redraw(self):
        if not self.engine:
            return
        state = self.engine.public_state()
        names = self.names(state)
        for cell, card in self.cards.items():
            clue = state["revealed"].get(cell)
            if cell == self.selected:
                edge = SELECT_EDGE
            elif cell == self.hint_cell:
                edge = HINT_EDGE
            else:
                edge = {CRIMINAL: CRIM_EDGE, INNOCENT: INNO_EDGE}.get(state["verdicts"].get(cell), EDGE)
            card.show(state["verdicts"].get(cell),
                      clue_to_text(clue, names) if clue is not None else None,
                      edge, cell in self.highlight)
        self.selected_label.configure(
            text=f"{self.selected} - {names[self.selected]}" if self.selected else "-")

        self.clue_list.delete(0, "end")
        self.clue_cells = list(state["revealed"])
        for cell in self.clue_cells:
            self.clue_list.insert("end", f"{cell} {names[cell]}: {clue_to_text(state['revealed'][cell], names)}")
        if self.engine.is_solved():
            self.set_message("Solved! Every verdict was proved.", RESULT_COLOURS[ACCEPTED])

    def set_message(self, text: str, colour: str = TEXT):
        self.message.configure(text=text, fg=colour)

    def log(self, line: str):
        self.trace.configure(state="normal")
        self.trace.insert("end", line + "\n")
        self.trace.see("end")
        self.trace.configure(state="disabled")

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
        self.title_label.configure(text=f"Puzzle {puzzle.id} ({puzzle.rows}x{puzzle.cols})")
        self._build_board()
        self.restart()

    def restart(self):
        if not self.engine:
            return
        self.stop_auto()
        self.engine.restart()
        self.agent.reset_stats()
        self.selected, self.hint_cell, self.highlight, self.step_no = None, None, set(), 0
        self.trace.configure(state="normal")
        self.trace.delete("1.0", "end")
        self.trace.configure(state="disabled")
        self.set_message("Pick a card, then CRIMINAL or INNOCENT.", MUTED)
        self.redraw()

    def select(self, cell: str):
        if not self.engine:
            return
        self.selected = None if self.selected == cell else cell
        self.redraw()

    def submit(self, verdict: str, cell: str | None = None, source: str = "you"):
        if not self.engine:
            return None
        cell = cell or self.selected
        if not cell:
            self.set_message("Select a card first.", MUTED)
            return None
        state = self.engine.public_state()
        if cell in state["verdicts"]:
            self.set_message(f"{cell} is already {state['verdicts'][cell].lower()}.", MUTED)
            return None
        try:
            result = self.engine.submit(cell, verdict)
        except NotImplementedError as e:
            self.set_message(f"Not implemented yet: {e}", CRIM_EDGE)
            return None
        names = self.names(state)
        explain = {
            ACCEPTED: f"{names[cell]} is {verdict.lower()}. Card flipped.",
            NOT_PROVABLE: f"NOT_PROVABLE: {names[cell]} cannot be proved {verdict.lower()} yet.",
            CONTRADICTED: f"CONTRADICTED: the clues prove {names[cell]} is NOT {verdict.lower()}.",
        }[result]
        self.set_message(explain, RESULT_COLOURS[result])
        self.step_no += 1
        self.log(f"{self.step_no:>3}. [{source}] {cell} {verdict} -> {result}")
        if result == ACCEPTED:
            self.selected = None
            self.hint_cell, self.highlight = None, set()
        self.redraw()
        return result

    def hint(self):
        if not self.engine or self.engine.is_solved():
            return
        state = self.engine.public_state()
        try:
            h = self.agent.hint(state)
        except NotImplementedError as e:
            self.set_message(f"Not implemented yet: {e}", CRIM_EDGE)
            return
        if h is None:
            kind = self.agent.classify(state)
            msg = "The clues contradict each other." if kind == INCONSISTENT else \
                "No verdict can be proved from the visible clues."
            self.set_message(msg, CRIM_EDGE)
            return
        names = self.names(state)
        self.hint_cell = h["cell"]
        self.highlight = set(h["because"])
        because = ", ".join(f"{c} {names[c]}" for c in h["because"]) or "the known verdicts"
        self.set_message(f"Hint: look at {h['cell']} {names[h['cell']]}. Use the clues of: {because}.",
                         HINT_EDGE)
        self.redraw()

    def on_clue_select(self, _event=None):
        sel = self.clue_list.curselection()
        if not sel or not self.engine:
            return
        state = self.engine.public_state()
        owner = self.clue_cells[sel[0]]
        try:
            self.highlight = set(cells_in_clue(state["revealed"][owner], state["rows"], state["cols"]))
        except NotImplementedError as e:
            self.set_message(f"Not implemented yet: {e}", CRIM_EDGE)
            return
        self.redraw()
        self.clue_list.selection_set(sel[0])

    # ----- auto solve

    def toggle_auto(self):
        if self.auto_job:
            self.stop_auto()
        else:
            self.auto_button.configure(text="Stop")
            self.auto_step()

    def stop_auto(self):
        if self.auto_job:
            self.root.after_cancel(self.auto_job)
        self.auto_job = None
        if hasattr(self, "auto_button"):
            self.auto_button.configure(text="Auto Solve")

    def auto_step(self, single: bool = False):
        self.auto_job = None
        if not self.engine or self.engine.is_solved():
            self.stop_auto()
            return
        try:
            move = self.agent.next_move(self.engine.public_state())
        except NotImplementedError as e:
            self.set_message(f"Not implemented yet: {e}", CRIM_EDGE)
            self.stop_auto()
            return
        if move is None:
            self.set_message("Stuck: no verdict can be proved. The agent does not guess.", CRIM_EDGE)
            self.stop_auto()
            return
        self.selected = None
        self.submit(move["verdict"], move["cell"], source="agent")
        if not single and not self.engine.is_solved():
            self.auto_job = self.root.after(AUTO_DELAY_MS, self.auto_step)
        elif not single:
            s = self.agent.stats
            self.log(f"SAT calls {s['sat_calls']}, decisions {s['decisions']}, "
                     f"propagations {s['propagations']}, backtracks {s['backtracks']}, "
                     f"time {s['time']:.3f}s")
            self.stop_auto()


def run(puzzle_path: str | None = None) -> None:
    root = tk.Tk()
    root.minsize(900, 560)
    App(root, puzzle_path)
    root.mainloop()
