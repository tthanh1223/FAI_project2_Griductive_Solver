"""Puzzle data model: cells, clues, regions, JSON loading.

Owner: Engine & Puzzle.

Cell ids: column letter + row number, e.g. "A1" (column A, row 1, rows counted top-down).
A puzzle JSON uses "size": N (square) or "rows" + "cols" (rectangular).
Clue / region JSON format: see README.md; exact region definitions: docs/CLUES.md section 2.
Input / output of every function: docs/INTERFACES.md.
"""
from dataclasses import dataclass, field

CRIMINAL = "CRIMINAL"
INNOCENT = "INNOCENT"


@dataclass
class Cell:
    cell: str            # "A1"
    name: str
    job: str
    status: str          # "CRIMINAL" | "INNOCENT" (hidden: only GameEngine may read it)
    clue: dict


@dataclass
class Puzzle:
    id: str
    rows: int
    cols: int
    cells: list[Cell]
    revealed: list[str] = field(default_factory=list)   # face-up at the start


def load_puzzle(path: str) -> Puzzle:
    """Read a puzzle JSON file. "size": N means rows = cols = N."""
    raise NotImplementedError


def all_cells(rows: int, cols: int) -> list[str]:
    """Cell ids in row-major order: A1, B1, C1, A2, ..."""
    raise NotImplementedError


def region_cells(region: dict, rows: int, cols: int) -> list[str]:
    """Cells of a region, in row-major order.

    Core kinds: row, col, neighbors (up to 8 around, excluding the cell itself), cells.
    Extension kinds: all, edges, corners, above / below / left / right, between, inter.
    """
    raise NotImplementedError


def cells_in_clue(clue: dict, rows: int, cols: int) -> list[str]:
    """Every cell a clue refers to or counts (used by GUI highlight and Hint)."""
    raise NotImplementedError
