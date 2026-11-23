"""Tests for puzzles/validate.py, and every puzzle file in puzzles/ must be valid."""
import copy
from pathlib import Path

import pytest

from model import CRIMINAL, INNOCENT, Cell, Puzzle, all_cells, load_puzzle
from puzzles.validate import main, puzzle_problems

PUZZLES = Path(__file__).resolve().parents[1] / "puzzles"
FILES = sorted(PUZZLES.glob("*.json"))


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_every_puzzle_file_is_valid(path):
    assert puzzle_problems(load_puzzle(path)) == []


def test_hand_written_puzzles_are_present():
    assert {"p3_01", "p3_02", "p3_03", "p4x5_candle"} <= {p.stem for p in FILES}


def test_core_clue_types_are_all_used():
    used = {c.clue["type"] for p in FILES for c in load_puzzle(p).cells}
    assert {"FACT", "SAME", "DIFFERENT", "EXACTLY", "AT_LEAST", "AT_MOST"} <= used
    assert len(used & {"COMPARE", "CONNECTED", "PARITY", "AND", "COUNT_LINES"}) >= 2


def test_puzzle_set_for_experiments():
    sizes = [(p.rows, p.cols) for p in map(load_puzzle, FILES)]
    assert sizes.count((3, 3)) >= 6 and sizes.count((4, 4)) >= 6 and sizes.count((5, 5)) >= 1


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_id_matches_file_name(path):
    assert load_puzzle(path).id == path.stem


def test_no_two_puzzles_are_the_same():
    def content(p):
        return (p.rows, p.cols, tuple((c.status, repr(c.clue)) for c in p.cells))
    contents = [content(load_puzzle(p)) for p in FILES]
    assert len(set(contents)) == len(contents)


def test_puzzle_is_not_modified():
    p = load_puzzle(PUZZLES / "p3_02.json")
    before = copy.deepcopy(p)
    puzzle_problems(p)
    assert p == before


# ---------- every broken puzzle is reported ----------

def _p(name="p3_02"):
    return load_puzzle(PUZZLES / f"{name}.json")


def _set_clue(puzzle, cell, clue):
    next(c for c in puzzle.cells if c.cell == cell).clue = clue
    return puzzle


def test_clue_false_on_solution():
    p = _set_clue(_p(), "B1", {"type": "EXACTLY", "k": 2, "region": {"kind": "row", "row": 1}})   # really 1
    assert any("false on the hidden solution" in x for x in puzzle_problems(p))


def test_invalid_clue():
    p = _set_clue(_p(), "B1", {"type": "EXACTLY", "k": 4, "region": {"kind": "row", "row": 1}})
    assert any("rejected by GameEngine" in x for x in puzzle_problems(p))


def test_needed_face_up_card_missing():
    p = _p("p4x5_candle")
    p.revealed = ["A1"]                     # A5 is the only start that works (checked when the file was made)
    problems = puzzle_problems(p)
    assert any("cannot finish without guessing" in x for x in problems)


def test_not_unique_and_stuck():
    p = _p()
    for c in p.cells:
        if c.cell != "B2":
            c.clue = {"type": "NONE", "text": "-"}
    problems = puzzle_problems(p)
    assert any("more than one solution" in x for x in problems)
    assert any("cannot finish without guessing" in x for x in problems)


def test_unique_but_needs_guessing():
    # 2x2, start A1 (innocent). Only the face-down card B2 holds the clue that decides
    # everything, so check_unique passes but the agent cannot start.
    cells = [Cell("A1", "Ann", "Cook", INNOCENT, {"type": "NONE", "text": "-"}),
             Cell("B1", "Bob", "Cook", CRIMINAL, {"type": "NONE", "text": "-"}),
             Cell("A2", "Cid", "Cook", INNOCENT, {"type": "NONE", "text": "-"}),
             Cell("B2", "Dee", "Cook", INNOCENT,
                  {"type": "AND", "parts": [{"type": "FACT", "who": "B1", "status": CRIMINAL},
                                            {"type": "EXACTLY", "k": 1, "region": {"kind": "all"}}]})]
    problems = puzzle_problems(Puzzle("guess", 2, 2, cells, ["A1"]))
    assert len(problems) == 1 and "cannot finish without guessing" in problems[0]


@pytest.mark.parametrize("names", [
    ["Amy", "Ben", "Cole", "Dina", "Ezra", "Faye", "Gus", "Igor", "Hana"],      # swapped
    ["Amy", "Ben", "Cole", "Dina", "Ezra", "Faye", "Gus", "Hana", "hana"],      # duplicate, any case
])
def test_names_not_alphabetical(names):
    p = _p()
    for c, name in zip(p.cells, names):
        c.name = name
    assert any("alphabetical" in x for x in puzzle_problems(p))


def test_names_order_uses_row_major_even_if_cells_are_shuffled():
    p = _p()
    p.cells.reverse()
    assert puzzle_problems(p) == []


# ---------- command line ----------

def test_main_reports_valid_invalid_and_unreadable(tmp_path, capsys):
    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    assert main([str(PUZZLES / "p3_01.json")]) == 0
    assert main([str(PUZZLES / "p3_01.json"), str(broken)]) == 1
    out = capsys.readouterr().out
    assert "OK      " in out and "INVALID" in out and "broken.json" in out
    assert main([]) == 2
