"""Tests for model.py: puzzle loading, cell ids and regions."""
import copy
import itertools
import json
from pathlib import Path

import pytest

from model import CRIMINAL, INNOCENT, Cell, _parse_cell, all_cells, load_puzzle, region_cells

P3 = Path(__file__).resolve().parents[1] / "puzzles" / "p3_01.json"


def _puzzle_dict(rows=2, cols=3):
    """A structurally valid puzzle (flavour clues only) with rows x cols cells."""
    cells = [{"cell": cell, "name": f"Name{i}", "job": "Cook",
              "status": CRIMINAL if i % 2 else INNOCENT,
              "clue": {"type": "NONE", "text": "hello"}}
             for i, cell in enumerate(all_cells(rows, cols))]
    return {"id": "t", "rows": rows, "cols": cols, "cells": cells, "revealed": ["A1"]}


def _write(tmp_path, data, name="p.json", encoding="utf-8"):
    path = tmp_path / name
    text = data if isinstance(data, str) else json.dumps(data)
    path.write_text(text, encoding=encoding)
    return path


# ---------- all_cells ----------

def test_all_cells_row_major():
    assert all_cells(2, 3) == ["A1", "B1", "C1", "A2", "B2", "C2"]
    assert all_cells(1, 1) == ["A1"]
    assert all_cells(3, 1) == ["A1", "A2", "A3"]
    assert all_cells(10, 2)[-1] == "B10"


@pytest.mark.parametrize("rows, cols", [(0, 3), (3, 0), (-1, 2), (True, 2), (2, 2.0), (1, 27)])
def test_all_cells_rejects_bad_size(rows, cols):
    with pytest.raises(ValueError):
        all_cells(rows, cols)


# ---------- _parse_cell ----------

def test_parse_cell():
    assert _parse_cell("A1", 3, 3) == (0, 0)
    assert _parse_cell("B3", 3, 3) == (2, 1)
    assert _parse_cell("A10", 10, 1) == (9, 0)


@pytest.mark.parametrize("cell", ["a1", "A0", "AA1", "A01", "1A", "A", "", " A1", "A1 ", None, 11, "D1", "A4"])
def test_parse_cell_rejects(cell):
    with pytest.raises(ValueError):
        _parse_cell(cell, 3, 3)


# ---------- load_puzzle: valid input ----------

def test_load_p3_01():
    p = load_puzzle(str(P3))
    assert (p.id, p.rows, p.cols, p.revealed) == ("p3_01", 3, 3, ["A1"])
    assert [c.cell for c in p.cells] == all_cells(3, 3)
    assert p.cells[0] == Cell("A1", "Alice", "Cook", INNOCENT,
                              {"type": "FACT", "who": "A2", "status": "CRIMINAL"})


def test_load_accepts_path_object_and_rectangular_grid(tmp_path):
    p = load_puzzle(_write(tmp_path, _puzzle_dict(rows=2, cols=3)))
    assert (p.rows, p.cols) == (2, 3) and len(p.cells) == 6


def test_size_with_matching_rows_cols(tmp_path):
    data = _puzzle_dict(rows=2, cols=2)
    data["size"] = 2
    assert load_puzzle(_write(tmp_path, data)).rows == 2


def test_utf8_bom_and_unicode_names(tmp_path):
    data = _puzzle_dict()
    data["cells"][0]["name"] = "Ánh"
    p = load_puzzle(_write(tmp_path, json.dumps(data, ensure_ascii=False), encoding="utf-8-sig"))
    assert p.cells[0].name == "Ánh"


def test_unknown_top_level_keys_are_ignored(tmp_path):
    data = _puzzle_dict()
    data["difficulty"] = {"steps": 5, "sat_calls": 40}
    assert load_puzzle(_write(tmp_path, data)).id == "t"


def test_cells_are_sorted_row_major(tmp_path):
    data = _puzzle_dict()
    data["cells"].reverse()
    p = load_puzzle(_write(tmp_path, data))
    assert [c.cell for c in p.cells] == all_cells(2, 3)
    assert p.cells[0].name == "Name0"          # each cell keeps its own data


# ---------- load_puzzle: errors ----------

def _drop(key):
    def edit(d):
        del d[key]
    return edit


def _set(key, value):
    def edit(d):
        d[key] = value
    return edit


def _set_cell(index, key, value):
    def edit(d):
        d["cells"][index][key] = value
    return edit


def _drop_cell_field(index, key):
    def edit(d):
        del d["cells"][index][key]
    return edit


BAD = {
    "missing id": _drop("id"),
    "empty id": _set("id", " "),
    "missing size": lambda d: (d.pop("rows"), d.pop("cols")),
    "only rows": _drop("cols"),
    "size conflicts": _set("size", 3),
    "zero rows": _set("rows", 0),
    "bool cols": _set("cols", True),
    "string rows": _set("rows", "2"),
    "too many cols": lambda d: d.update(cols=27),
    "cells not list": _set("cells", {}),
    "too few cells": lambda d: d["cells"].pop(),
    "cell not object": lambda d: d["cells"].__setitem__(0, "A1"),
    "missing clue": _drop_cell_field(0, "clue"),
    "missing status": _drop_cell_field(1, "status"),
    "duplicate cell": _set_cell(1, "cell", "A1"),
    "cell off grid": _set_cell(1, "cell", "D1"),
    "bad cell id": _set_cell(1, "cell", "b1"),
    "bad status": _set_cell(0, "status", "criminal"),
    "empty name": _set_cell(0, "name", ""),
    "job not string": _set_cell(0, "job", 3),
    "clue not object": _set_cell(0, "clue", "NONE"),
    "missing revealed": _drop("revealed"),
    "empty revealed": _set("revealed", []),
    "revealed not list": _set("revealed", "A1"),
    "revealed off grid": _set("revealed", ["A9"]),
    "revealed duplicate": _set("revealed", ["A1", "A1"]),
}


@pytest.mark.parametrize("case", BAD)
def test_structural_errors(tmp_path, case):
    data = copy.deepcopy(_puzzle_dict())
    BAD[case](data)
    with pytest.raises(ValueError, match=r"^bad\.json: "):
        load_puzzle(_write(tmp_path, data, name="bad.json"))


@pytest.mark.parametrize("text", ["{", "", "[1, 2]", "null"])
def test_invalid_json_or_not_object(tmp_path, text):
    with pytest.raises(ValueError, match=r"^bad\.json: "):
        load_puzzle(_write(tmp_path, text, name="bad.json"))


def test_missing_file_is_os_error(tmp_path):
    with pytest.raises(OSError):
        load_puzzle(tmp_path / "nope.json")


# ---------- region_cells: examples (3x3 unless stated) ----------

def N(cell):
    return {"kind": "neighbors", "of": cell}


@pytest.mark.parametrize("region, expected", [
    ({"kind": "row", "row": 1}, ["A1", "B1", "C1"]),
    ({"kind": "col", "col": "C"}, ["C1", "C2", "C3"]),
    (N("A1"), ["B1", "A2", "B2"]),                                   # corner: 3
    (N("B1"), ["A1", "C1", "A2", "B2", "C2"]),                       # edge: 5
    (N("B2"), ["A1", "B1", "C1", "A2", "C2", "A3", "B3", "C3"]),     # centre: 8
    ({"kind": "cells", "cells": ["C3", "A1", "B2"]}, ["A1", "B2", "C3"]),   # any order in
    ({"kind": "cells", "cells": []}, []),
    ({"kind": "all"}, all_cells(3, 3)),
    ({"kind": "edges"}, ["A1", "B1", "C1", "A2", "C2", "A3", "B3", "C3"]),
    ({"kind": "corners"}, ["A1", "C1", "A3", "C3"]),
    ({"kind": "above", "of": "B3"}, ["B1", "B2"]),
    ({"kind": "above", "of": "B1"}, []),
    ({"kind": "below", "of": "A1"}, ["A2", "A3"]),
    ({"kind": "left", "of": "C2"}, ["A2", "B2"]),
    ({"kind": "right", "of": "C2"}, []),
    ({"kind": "between", "a": "C1", "b": "A1"}, ["B1"]),
    ({"kind": "between", "a": "B1", "b": "B3"}, ["B2"]),
    ({"kind": "between", "a": "A1", "b": "A2"}, []),
    ({"kind": "inter", "regions": [N("A1"), N("C1")]}, ["B1", "B2"]),
    ({"kind": "inter", "regions": [N("A1"), N("C3")]}, ["B2"]),
    ({"kind": "inter", "regions": [{"kind": "row", "row": 1}, {"kind": "row", "row": 2}]}, []),
    ({"kind": "inter", "regions": [{"kind": "all"}, N("B2"),
                                   {"kind": "inter", "regions": [{"kind": "edges"}, {"kind": "col", "col": "A"}]}]},
     ["A1", "A2", "A3"]),                                            # nested
])
def test_regions_3x3(region, expected):
    assert region_cells(region, 3, 3) == expected


def test_degenerate_grids():
    assert region_cells({"kind": "corners"}, 1, 3) == ["A1", "C1"]
    assert region_cells({"kind": "corners"}, 1, 1) == ["A1"]
    assert region_cells({"kind": "edges"}, 1, 3) == ["A1", "B1", "C1"]
    assert region_cells({"kind": "edges"}, 2, 2) == all_cells(2, 2)
    assert region_cells(N("A1"), 1, 1) == []


def test_region_on_large_grid():
    assert region_cells({"kind": "above", "of": "A10"}, 10, 1)[-1] == "A9"


def test_region_input_not_modified():
    region = {"kind": "inter", "regions": [N("A1"), {"kind": "cells", "cells": ["B2", "A2"]}]}
    before = copy.deepcopy(region)
    region_cells(region, 3, 3)
    assert region == before


# ---------- region_cells: errors ----------

@pytest.mark.parametrize("region", [
    "row 1", None, {}, {"kind": "diagonal"}, {"kind": "ROW", "row": 1},
    {"kind": "row"}, {"kind": "row", "row": 1, "col": "A"}, {"kind": "all", "of": "A1"},
    {"kind": "row", "row": 0}, {"kind": "row", "row": 4}, {"kind": "row", "row": True},
    {"kind": "row", "row": "1"}, {"kind": "row", "row": 1.0},
    {"kind": "col", "col": "D"}, {"kind": "col", "col": "a"}, {"kind": "col", "col": "AB"}, {"kind": "col", "col": 1},
    {"kind": "neighbors", "of": "D1"}, {"kind": "above", "of": "a1"}, {"kind": "right", "of": None},
    {"kind": "cells", "cells": "A1"}, {"kind": "cells", "cells": ["A1", "A1"]}, {"kind": "cells", "cells": ["A9"]},
    {"kind": "between", "a": "A1", "b": "B2"}, {"kind": "between", "a": "B2", "b": "B2"},
    {"kind": "between", "a": "A1"},
    {"kind": "inter", "regions": [N("A1")]}, {"kind": "inter", "regions": N("A1")},
    {"kind": "inter", "regions": [N("A1"), {"kind": "nope"}]},
])
def test_region_errors(region):
    with pytest.raises(ValueError):
        region_cells(region, 3, 3)


# ---------- region_cells: properties on every grid 1x1 .. 5x5 ----------

GRIDS = list(itertools.product(range(1, 6), repeat=2))


def _all_regions(rows, cols):
    """Every region of every kind on this grid (all anchors, all pairs)."""
    cells = all_cells(rows, cols)
    yield from ({"kind": "row", "row": r} for r in range(1, rows + 1))
    yield from ({"kind": "col", "col": chr(ord("A") + c)} for c in range(cols))
    yield from ({"kind": k} for k in ("all", "edges", "corners"))
    for cell in cells:
        yield from ({"kind": k, "of": cell} for k in ("neighbors", "above", "below", "left", "right"))
    for a, b in itertools.permutations(cells, 2):
        if a[0] == b[0] or a[1:] == b[1:]:
            yield {"kind": "between", "a": a, "b": b}
    yield {"kind": "cells", "cells": cells[::-1]}
    yield {"kind": "inter", "regions": [N(cells[0]), N(cells[-1])]}


@pytest.mark.parametrize("rows, cols", GRIDS)
def test_every_region_is_row_major_unique_and_in_grid(rows, cols):
    order = {cell: i for i, cell in enumerate(all_cells(rows, cols))}
    for region in _all_regions(rows, cols):
        out = region_cells(region, rows, cols)
        assert all(cell in order for cell in out), region
        assert [order[c] for c in out] == sorted(set(order[c] for c in out)), region


@pytest.mark.parametrize("rows, cols", GRIDS)
def test_neighbors_are_symmetric_and_exclude_self(rows, cols):
    cells = all_cells(rows, cols)
    nb = {x: set(region_cells(N(x), rows, cols)) for x in cells}
    for a in cells:
        assert a not in nb[a]
        for b in cells:
            assert (b in nb[a]) == (a in nb[b])


@pytest.mark.parametrize("rows, cols", GRIDS)
def test_directions_cover_row_and_column(rows, cols):
    for cell in all_cells(rows, cols):
        parts = set().union(*(region_cells({"kind": k, "of": cell}, rows, cols)
                              for k in ("above", "below", "left", "right")))
        line = (set(region_cells({"kind": "row", "row": int(cell[1:])}, rows, cols))
                | set(region_cells({"kind": "col", "col": cell[0]}, rows, cols)))
        assert parts | {cell} == line
        assert cell not in parts


@pytest.mark.parametrize("rows, cols", GRIDS)
def test_between_is_symmetric_and_strict(rows, cols):
    cells = all_cells(rows, cols)
    for a, b in itertools.permutations(cells, 2):
        if a[0] == b[0] or a[1:] == b[1:]:
            ab = region_cells({"kind": "between", "a": a, "b": b}, rows, cols)
            assert ab == region_cells({"kind": "between", "a": b, "b": a}, rows, cols)
            distance = abs(int(a[1:]) - int(b[1:])) + abs(ord(a[0]) - ord(b[0]))
            assert len(ab) == distance - 1 and a not in ab and b not in ab


@pytest.mark.parametrize("rows, cols", [g for g in GRIDS if min(g) >= 2])
def test_edges_and_corners_counts(rows, cols):
    assert len(region_cells({"kind": "edges"}, rows, cols)) == 2 * (rows + cols) - 4
    assert len(region_cells({"kind": "corners"}, rows, cols)) == 4
