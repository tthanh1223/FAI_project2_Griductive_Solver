"""Game Engine: owns the full puzzle, hidden statuses and face-down clues.

Owner: Engine & Puzzle.
Only this module may read Cell.status of unsolved cells and clues of face-down cards.
Input / output of every function: docs/INTERFACES.md.
"""
import copy

from agent import INCONSISTENT, UNKNOWN, LogicAgent
from encoder import evaluate_clue, validate_clue
from model import CRIMINAL, INNOCENT, Puzzle, all_cells

ACCEPTED = "ACCEPTED"
NOT_PROVABLE = "NOT_PROVABLE"
CONTRADICTED = "CONTRADICTED"


class GameEngine:
    """Referee of one game. Everything hidden lives in "_" attributes; the agent and
    the GUI only ever see public_state()."""

    def __init__(self, puzzle: Puzzle, agent: LogicAgent | None = None):
        """Check the puzzle and start a game.

        The puzzle is deep-copied, so later changes to the caller's object do not
        affect the engine. Raises ValueError if the cells are not exactly the grid
        cells, a status is not CRIMINAL / INNOCENT, a revealed cell does not exist,
        a clue is invalid (encoder.validate_clue) or a clue is false on the hidden
        solution. The last check guarantees that the public knowledge base is
        always consistent.
        """
        self._puzzle = copy.deepcopy(puzzle)
        self.agent = agent or LogicAgent()
        rows, cols = self._puzzle.rows, self._puzzle.cols
        grid = all_cells(rows, cols)

        by_cell = {c.cell: c for c in self._puzzle.cells}
        if len(self._puzzle.cells) != len(grid) or set(by_cell) != set(grid):
            raise ValueError(f"Puzzle {self._puzzle.id}: cells must be exactly the {rows}x{cols} grid cells")
        self._cells = [by_cell[cell] for cell in grid]              # row-major
        for c in self._cells:
            if c.status not in (CRIMINAL, INNOCENT):
                raise ValueError(f"Cell {c.cell}: invalid status {c.status!r}")
        unknown = [cell for cell in self._puzzle.revealed if cell not in by_cell]
        if unknown:
            raise ValueError(f"Revealed cells not in the grid: {unknown}")

        self._status = {c.cell: c.status for c in self._cells}
        self._clues = {c.cell: c.clue for c in self._cells}
        solution = {cell: status == CRIMINAL for cell, status in self._status.items()}
        for cell, clue in self._clues.items():
            try:
                validate_clue(clue, rows, cols)
            except ValueError as e:
                raise ValueError(f"Clue of {cell}: {e}") from None
            if not evaluate_clue(clue, solution, rows, cols):
                raise ValueError(f"Clue of {cell} is false on the hidden solution")
        self.restart()

    def restart(self) -> None:
        """Back to the initial state: only puzzle.revealed cards are face-up.

        A face-up card's status is known, so it is also a verdict: revealed and
        verdicts always have the same cells.
        """
        start = set(self._puzzle.revealed)
        self._revealed = {c.cell: copy.deepcopy(c.clue) for c in self._cells if c.cell in start}
        self._verdicts = {c.cell: c.status for c in self._cells if c.cell in start}

    def public_state(self) -> dict:
        """Everything the agent / GUI may see (a deep copy, safe to modify).

        {
          "rows": int, "cols": int,
          "cells": [{"cell", "name", "job"}],          # every cell, row-major, no status
          "revealed": {cell: clue},                     # face-up clues only
          "verdicts": {cell: "CRIMINAL" | "INNOCENT"},  # proved statuses only
        }
        """
        return {
            "rows": self._puzzle.rows,
            "cols": self._puzzle.cols,
            "cells": [{"cell": c.cell, "name": c.name, "job": c.job} for c in self._cells],
            "revealed": copy.deepcopy(self._revealed),
            "verdicts": dict(self._verdicts),
        }

    def submit(self, cell: str, verdict: str) -> str:
        """A verdict from the player or the agent: ACCEPTED | NOT_PROVABLE | CONTRADICTED.

        Decided with LogicAgent.classify(public_state), never with the hidden
        solution. ACCEPTED: the verdict is forced; it is recorded and the card is
        flipped (its clue joins "revealed"). NOT_PROVABLE: neither status is
        forced. CONTRADICTED: the opposite status is forced. A rejection changes
        nothing.

        Raises ValueError for an unknown cell, an already decided cell or a
        verdict other than CRIMINAL / INNOCENT. Raises AssertionError if a forced
        verdict differs from the hidden status, and RuntimeError if the agent
        returns INCONSISTENT or no result for the cell; both mean a bug in the
        encoder / agent, and the state is left unchanged.
        """
        if cell not in self._status:
            raise ValueError(f"Unknown cell: {cell!r}")
        if verdict not in (CRIMINAL, INNOCENT):
            raise ValueError(f"Verdict must be {CRIMINAL} or {INNOCENT}, got {verdict!r}")
        if cell in self._verdicts:
            raise ValueError(f"Cell {cell} is already decided")

        result = self.agent.classify(self.public_state())
        if result == INCONSISTENT:
            raise RuntimeError("Agent found the public knowledge base inconsistent, "
                               "but every clue is true on the solution")
        forced = result.get(cell) if isinstance(result, dict) else None
        if forced == UNKNOWN:
            return NOT_PROVABLE
        if forced not in (CRIMINAL, INNOCENT):
            raise RuntimeError(f"Agent gave no valid result for {cell}: {forced!r}")
        if forced != verdict:
            return CONTRADICTED
        if verdict != self._status[cell]:
            raise AssertionError(f"Agent proved {verdict} for {cell}, but the hidden status differs")

        self._verdicts[cell] = verdict
        self._revealed[cell] = copy.deepcopy(self._clues[cell])
        return ACCEPTED

    def is_solved(self) -> bool:
        """True when every cell has a verdict."""
        return len(self._verdicts) == len(self._cells)
