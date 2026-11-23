"""Tests for model.py: puzzle loading and cell ids."""
import copy
import json
from pathlib import Path

import pytest

from model import CRIMINAL, INNOCENT, Cell, _parse_cell, all_cells, load_puzzle

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
