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

# Region kind -> required fields besides "kind" (no other field is allowed).
_REGION_FIELDS = {
    "row": {"row"}, "col": {"col"}, "neighbors": {"of"}, "cells": {"cells"},
    "all": set(), "edges": set(), "corners": set(),
    "above": {"of"}, "below": {"of"}, "left": {"of"}, "right": {"of"},
    "between": {"a", "b"}, "inter": {"regions"},
}


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

    Raises ValueError (message starts with the file name) on a file that is not
    UTF-8, invalid JSON, a missing or ill-typed field, a cell count other than
    rows * cols, a duplicate or off-grid cell id, an unknown status, or an
    empty / invalid "revealed" list. A missing file raises OSError as usual.
    """
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except UnicodeDecodeError as e:
        raise ValueError(f"{path.name}: not a UTF-8 file ({e})") from None
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
    """Cells of a region, in row-major order, without duplicates.

    Core kinds: row, col, neighbors (up to 8 around, excluding the cell itself), cells.
    Extension kinds: all, edges, corners, above / below / left / right, between, inter.
    Exact definitions: docs/CLUES.md section 2. Examples on a 3x3 grid:
        {"kind": "row", "row": 2}             -> ["A2", "B2", "C2"]
        {"kind": "neighbors", "of": "A1"}     -> ["B1", "A2", "B2"]
        {"kind": "above", "of": "B3"}         -> ["B1", "B2"]
        {"kind": "between", "a": "A1", "b": "C1"} -> ["B1"]

    Empty regions are valid (above a row-1 cell, between two adjacent cells, an
    empty intersection). On degenerate grids "corners" is the set of corner
    positions without repeats (1x3 -> A1, C1; 1x1 -> A1) and "edges" is the
    whole grid when rows or cols < 3.

    Raises ValueError on an unknown kind, a missing / extra / ill-typed field, a
    cell outside the grid, a duplicate in "cells", "between" cells that are equal
    or not on one row / column, or "inter" with fewer than 2 regions.
    """
    _check_size(rows, cols)
    return [_cell_id(r, c) for r, c in sorted(_region_positions(region, rows, cols))]


def cells_in_clue(clue: dict, rows: int, cols: int) -> list[str]:
    """Every cell a clue refers to or counts (used by GUI highlight and Hint).

    = cells named by the clue + cells counted by it + anchor cells of its regions
    ("of", and "a" / "b" of "between", also inside "inter"); row-major, no
    duplicates. AND is the union of its parts, COUNT_LINES the whole grid, NONE [].
    Definition: docs/CLUES.md section 5. Examples on a 3x3 grid:
        {"type": "SAME", "a": "B2", "b": "C3"}                         -> ["B2", "C3"]
        {"type": "EXACTLY", "k": 1, "region": {"kind": "above", "of": "B3"}} -> ["B1", "B2", "B3"]

    Only what is needed to list the cells is checked: raises ValueError on an
    unknown clue type, a missing field or an invalid cell / region. Full clue
    validation is encoder.validate_clue.
    """
    _check_size(rows, cols)
    return [_cell_id(r, c) for r, c in sorted(_clue_positions(clue, rows, cols))]


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


def _region_positions(region, rows: int, cols: int) -> set[tuple[int, int]]:
    """(row, col) positions (0-based) of a region; see region_cells."""
    if not isinstance(region, dict):
        raise ValueError(f"A region must be an object, got {region!r}")
    kind = region.get("kind")
    if not isinstance(kind, str) or kind not in _REGION_FIELDS:
        raise ValueError(f"Unknown region kind: {kind!r}")
    if region.keys() != _REGION_FIELDS[kind] | {"kind"}:
        raise ValueError(f"Region {kind!r} needs exactly the fields {sorted(_REGION_FIELDS[kind])}, "
                         f"got {sorted(region.keys() - {'kind'})}")
    grid = {(r, c) for r in range(rows) for c in range(cols)}

    if kind == "row":
        row = region["row"]
        if not (_is_int(row) and 1 <= row <= rows):
            raise ValueError(f"Row must be an int in [1, {rows}], got {row!r}")
        return {(row - 1, c) for c in range(cols)}
    if kind == "col":
        col = region["col"]
        if not (isinstance(col, str) and len(col) == 1 and "A" <= col < chr(ord("A") + cols)):
            raise ValueError(f"Column must be a letter in A..{chr(ord('A') + cols - 1)}, got {col!r}")
        return {(r, ord(col) - ord("A")) for r in range(rows)}
    if kind == "cells":
        cells = region["cells"]
        if not isinstance(cells, list):
            raise ValueError('"cells" must be a list of cell ids')
        positions = [_parse_cell(cell, rows, cols) for cell in cells]
        if len(set(positions)) != len(positions):
            raise ValueError(f"Duplicate cell ids in {cells}")
        return set(positions)
    if kind == "all":
        return grid
    if kind == "edges":
        return {(r, c) for r, c in grid if r in (0, rows - 1) or c in (0, cols - 1)}
    if kind == "corners":
        return {(r, c) for r in (0, rows - 1) for c in (0, cols - 1)}
    if kind == "inter":
        parts = region["regions"]
        if not isinstance(parts, list) or len(parts) < 2:
            raise ValueError('"inter" needs a list of at least 2 regions')
        return set.intersection(*(_region_positions(part, rows, cols) for part in parts))

    if kind == "between":
        (ra, ca), (rb, cb) = _parse_cell(region["a"], rows, cols), _parse_cell(region["b"], rows, cols)
        if (ra, ca) == (rb, cb):
            raise ValueError(f"'between' needs two different cells, got {region['a']} twice")
        if ra == rb:
            return {(ra, c) for c in range(min(ca, cb) + 1, max(ca, cb))}
        if ca == cb:
            return {(r, ca) for r in range(min(ra, rb) + 1, max(ra, rb))}
        raise ValueError(f"'between' cells {region['a']} and {region['b']} are not on one row or column")

    r, c = _parse_cell(region["of"], rows, cols)      # neighbors, above, below, left, right
    if kind == "neighbors":
        return {(r + dr, c + dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1)
                if (dr, dc) != (0, 0) and (r + dr, c + dc) in grid}
    if kind == "above":
        return {(i, c) for i in range(r)}
    if kind == "below":
        return {(i, c) for i in range(r + 1, rows)}
    if kind == "left":
        return {(r, j) for j in range(c)}
    return {(r, j) for j in range(c + 1, cols)}      # right


def _region_anchors(region: dict, rows: int, cols: int) -> set[tuple[int, int]]:
    """Positions of the cells a (valid) region is defined from: "of", "a" / "b", recursively in "inter"."""
    kind = region["kind"]
    if "of" in _REGION_FIELDS[kind]:
        return {_parse_cell(region["of"], rows, cols)}
    if kind == "between":
        return {_parse_cell(region["a"], rows, cols), _parse_cell(region["b"], rows, cols)}
    if kind == "inter":
        return set().union(*(_region_anchors(part, rows, cols) for part in region["regions"]))
    return set()


def _region_and_anchors(region, rows: int, cols: int) -> set[tuple[int, int]]:
    counted = _region_positions(region, rows, cols)        # validates the region first
    return counted | _region_anchors(region, rows, cols)


def _clue_positions(clue, rows: int, cols: int) -> set[tuple[int, int]]:
    """(row, col) positions of cells_in_clue."""
    if not isinstance(clue, dict):
        raise ValueError(f"A clue must be an object, got {clue!r}")
    kind = clue.get("type")
    try:
        if kind == "NONE":
            return set()
        if kind == "FACT":
            return {_parse_cell(clue["who"], rows, cols)}
        if kind in ("SAME", "DIFFERENT"):
            return {_parse_cell(clue["a"], rows, cols), _parse_cell(clue["b"], rows, cols)}
        if kind in ("EXACTLY", "AT_LEAST", "AT_MOST", "PARITY", "CONNECTED"):
            return _region_and_anchors(clue["region"], rows, cols)
        if kind == "COMPARE":
            return _region_and_anchors(clue["r1"], rows, cols) | _region_and_anchors(clue["r2"], rows, cols)
        if kind == "AND":
            parts = clue["parts"]
            if not isinstance(parts, list):
                raise ValueError('"parts" of an AND clue must be a list')
            return set().union(*(_clue_positions(part, rows, cols) for part in parts))
        if kind == "COUNT_LINES":
            return {(r, c) for r in range(rows) for c in range(cols)}
    except KeyError as e:
        raise ValueError(f"{kind} clue is missing the field {e}") from None
    raise ValueError(f"Unknown clue type: {kind!r}")


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
