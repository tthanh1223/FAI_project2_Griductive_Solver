"""Puzzle data model: cells, clues, regions, JSON loading.

Owner: Engine & Puzzle.

Cell ids: column letter + row number, e.g. "A1" (column A, row 1, rows counted top-down).
A puzzle JSON uses "size": N (square) or "rows" + "cols" (rectangular).
Clue / region JSON format: see README.md; exact region definitions: docs/CLUES.md section 2.
Input / output of every function: docs/INTERFACES.md.
"""
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

CRIMINAL = "CRIMINAL"
INNOCENT = "INNOCENT"

_MAX_COLS = 26                                   # columns are single letters A..Z
_CELL_RE = re.compile(r"([A-Z])([1-9][0-9]*)")   # "A1", "C12"; not "a1", "A0", "AA1"
_CELL_FIELDS = ("cell", "name", "job", "status", "clue")


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
    """Read a puzzle JSON file and check its structure.

    "size": N means rows = cols = N; otherwise both "rows" and "cols" are required.
    Unknown top-level keys (e.g. "difficulty") are ignored. Cells are returned in
    row-major order whatever their order in the file. A UTF-8 BOM is accepted.

    Only the structure is checked here; clue semantics are checked by GameEngine
    (encoder.validate_clue), since encoder imports this module.

    Raises ValueError (message starts with the file name) on invalid JSON, a missing
    or ill-typed field, a cell count other than rows * cols, a duplicate or
    off-grid cell id, an unknown status, or an empty / invalid "revealed" list.
    A missing file raises OSError as usual.
    """
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"{path.name}: invalid JSON ({e})") from None
    try:
        return _build_puzzle(data)
    except ValueError as e:
        raise ValueError(f"{path.name}: {e}") from None


def all_cells(rows: int, cols: int) -> list[str]:
    """Cell ids in row-major order: A1, B1, C1, A2, ...

    all_cells(2, 3) -> ["A1", "B1", "C1", "A2", "B2", "C2"].
    Raises ValueError if rows / cols is not a positive int or cols > 26.
    """
    _check_size(rows, cols)
    return [_cell_id(r, c) for r in range(rows) for c in range(cols)]


def region_cells(region: dict, rows: int, cols: int) -> list[str]:
    """Cells of a region, in row-major order.

    Core kinds: row, col, neighbors (up to 8 around, excluding the cell itself), cells.
    Extension kinds: all, edges, corners, above / below / left / right, between, inter.
    """
    raise NotImplementedError


def cells_in_clue(clue: dict, rows: int, cols: int) -> list[str]:
    """Every cell a clue refers to or counts (used by GUI highlight and Hint)."""
    raise NotImplementedError


# ---------------------------------------------------------------- helpers

def _is_int(value) -> bool:
    """A real int: bool is a subclass of int but is rejected."""
    return isinstance(value, int) and not isinstance(value, bool)


def _check_size(rows, cols) -> None:
    if not (_is_int(rows) and rows >= 1 and _is_int(cols) and cols >= 1):
        raise ValueError(f"Grid size must be positive integers, got rows={rows!r}, cols={cols!r}")
    if cols > _MAX_COLS:
        raise ValueError(f"At most {_MAX_COLS} columns are supported, got {cols}")


def _cell_id(r: int, c: int) -> str:
    """(row, col), both 0-based -> cell id: (0, 0) -> "A1", (2, 1) -> "B3"."""
    return f"{chr(ord('A') + c)}{r + 1}"


def _parse_cell(cell, rows: int, cols: int) -> tuple[int, int]:
    """Cell id -> (row, col), both 0-based: "B3" -> (2, 1).

    Raises ValueError if `cell` is not a well-formed id or lies outside the grid.
    """
    match = _CELL_RE.fullmatch(cell) if isinstance(cell, str) else None
    if match is None:
        raise ValueError(f"Invalid cell id: {cell!r}")
    r, c = int(match.group(2)) - 1, ord(match.group(1)) - ord("A")
    if not (r < rows and c < cols):
        raise ValueError(f"Cell {cell} is outside the {rows}x{cols} grid")
    return r, c


def _grid_size(data: dict) -> tuple[int, int]:
    """(rows, cols) from "size", or from "rows" + "cols". Both forms must agree."""
    if "size" in data:
        size = data["size"]
        rows, cols = data.get("rows", size), data.get("cols", size)
        if (rows, cols) != (size, size):
            raise ValueError(f'"size" {size!r} conflicts with "rows"/"cols" {rows!r}/{cols!r}')
    elif "rows" in data and "cols" in data:
        rows, cols = data["rows"], data["cols"]
    else:
        raise ValueError('Missing grid size: give "size", or both "rows" and "cols"')
    _check_size(rows, cols)
    return rows, cols


def _build_cell(raw, index: int, rows: int, cols: int) -> Cell:
    if not isinstance(raw, dict):
        raise ValueError(f"cells[{index}] must be an object")
    missing = [key for key in _CELL_FIELDS if key not in raw]
    if missing:
        raise ValueError(f"cells[{index}] is missing {', '.join(missing)}")
    cell = raw["cell"]
    _parse_cell(cell, rows, cols)
    for key in ("name", "job"):
        if not isinstance(raw[key], str) or not raw[key].strip():
            raise ValueError(f"Cell {cell}: {key!r} must be a non-empty string")
    if raw["status"] not in (CRIMINAL, INNOCENT):
        raise ValueError(f"Cell {cell}: status must be {CRIMINAL} or {INNOCENT}, got {raw['status']!r}")
    if not isinstance(raw["clue"], dict):
        raise ValueError(f"Cell {cell}: clue must be an object")
    return Cell(cell=cell, name=raw["name"], job=raw["job"], status=raw["status"], clue=raw["clue"])


def _build_puzzle(data) -> Puzzle:
    """Check the structure of a parsed puzzle JSON and build the Puzzle."""
    if not isinstance(data, dict):
        raise ValueError("The puzzle must be a JSON object")
    puzzle_id = data.get("id")
    if not isinstance(puzzle_id, str) or not puzzle_id.strip():
        raise ValueError('"id" must be a non-empty string')
    rows, cols = _grid_size(data)

    raw_cells = data.get("cells")
    if not isinstance(raw_cells, list):
        raise ValueError('"cells" must be a list')
    if len(raw_cells) != rows * cols:
        raise ValueError(f"Expected {rows * cols} cells for a {rows}x{cols} grid, got {len(raw_cells)}")
    cells = [_build_cell(raw, i, rows, cols) for i, raw in enumerate(raw_cells)]
    ids = [c.cell for c in cells]
    duplicates = sorted({x for x in ids if ids.count(x) > 1})
    if duplicates:
        raise ValueError(f"Duplicate cell ids: {', '.join(duplicates)}")
    order = {cell: i for i, cell in enumerate(all_cells(rows, cols))}
    cells.sort(key=lambda c: order[c.cell])

    revealed = data.get("revealed")
    if not isinstance(revealed, list) or not revealed:
        raise ValueError('"revealed" must be a non-empty list of cell ids')
    for cell in revealed:
        _parse_cell(cell, rows, cols)
    if len(set(revealed)) != len(revealed):
        raise ValueError('"revealed" contains duplicate cell ids')

    return Puzzle(id=puzzle_id, rows=rows, cols=cols, cells=cells, revealed=list(revealed))
