"""Tests for puzzles/generate.py: validity, determinism, clue quality, command line."""
import random

import pytest

from encoder import VarMap, encode_clue, evaluate_clue
from model import all_cells, load_puzzle
from puzzles.generate import (_to_puzzle, generate, is_useful_clue, main, puzzle_id,
                              random_clue, to_json)
from puzzles.validate import puzzle_problems

SEED = 0
N3 = 50


@pytest.fixture(scope="module")
def puzzles_3x3():
    return [generate(3, 3, SEED, i) for i in range(1, N3 + 1)]


def test_generated_3x3_are_valid(puzzles_3x3):
    for data in puzzles_3x3:
        assert puzzle_problems(_to_puzzle(data["id"], data)) == [], data["id"]


def test_generated_clues_are_useful_and_one_flavour_card(puzzles_3x3):
    for data in puzzles_3x3:
        answer = {c["cell"]: c["status"] == "CRIMINAL" for c in data["cells"]}
        flavour = [c for c in data["cells"] if c["clue"]["type"] == "NONE"]
        assert len(flavour) == 1, data["id"]                 # only the last flipped card
        assert flavour[0]["cell"] not in data["revealed"]
        for c in data["cells"]:
            if c["clue"]["type"] != "NONE":
                assert is_useful_clue(c["clue"], answer, 3, 3), (data["id"], c)


def test_generated_set_is_varied(puzzles_3x3):
    types = {c["clue"]["type"] for d in puzzles_3x3 for c in d["cells"]}
    assert {"FACT", "SAME", "DIFFERENT", "EXACTLY", "AT_LEAST", "AT_MOST"} <= types
    assert len(types & {"COMPARE", "CONNECTED", "PARITY", "AND"}) >= 2
    answers = {tuple(c["status"] for c in d["cells"]) for d in puzzles_3x3}
    assert len(answers) > N3 // 2
    fact = sum(c["clue"]["type"] == "FACT" for d in puzzles_3x3 for c in d["cells"])
    assert fact <= 0.1 * 9 * N3


@pytest.mark.parametrize("rows, cols", [(4, 4), (4, 5), (2, 3)])
def test_other_sizes_are_valid(rows, cols):
    data = generate(rows, cols, SEED, 1)
    p = _to_puzzle(data["id"], data)
    assert (p.rows, p.cols) == (rows, cols) and [c.cell for c in p.cells] == all_cells(rows, cols)
    assert puzzle_problems(p) == []
    assert set(data["difficulty"]) == {"waves", "sat_calls"}


def test_same_arguments_same_bytes():
    assert to_json(generate(3, 3, 7, 2)) == to_json(generate(3, 3, 7, 2))
    assert generate(3, 3, 7, 2) != generate(3, 3, 7, 3)
    assert generate(3, 3, 7, 2) != generate(3, 3, 8, 2)


def test_puzzle_ids():
    assert puzzle_id(3, 3, 1) == "g3_01"
    assert puzzle_id(4, 5, 12) == "g4x5_12"


@pytest.mark.parametrize("rows, cols", [(1, 3), (3, 1), (7, 7), (2, 27)])
def test_unsupported_sizes(rows, cols):
    with pytest.raises(ValueError):
        generate(rows, cols, SEED, 1)


# ---------- clue drawing ----------

def test_random_clue_is_always_useful_and_true():
    rng = random.Random(1)
    for rows, cols in [(3, 3), (4, 4), (4, 5)]:
        cells = all_cells(rows, cols)
        for _ in range(150):
            answer = {c: rng.random() < 0.4 for c in cells}
            cell = rng.choice(cells)
            clue = random_clue(answer, cell, rows, cols, rng)
            assert evaluate_clue(clue, answer, rows, cols)
            assert encode_clue(clue, VarMap(rows, cols)), clue


ANSWER = {c: c in {"A1", "B2"} for c in all_cells(3, 3)}       # criminals A1, B2
ROW1 = {"kind": "row", "row": 1}


@pytest.mark.parametrize("clue, useful", [
    ({"type": "EXACTLY", "k": 1, "region": ROW1}, True),
    ({"type": "AT_LEAST", "k": 0, "region": ROW1}, False),                   # always true
    ({"type": "AT_MOST", "k": 3, "region": ROW1}, False),                    # always true
    ({"type": "EXACTLY", "k": 0, "region": {"kind": "above", "of": "A1"}}, False),   # empty region
    ({"type": "COMPARE", "r1": ROW1, "op": "=", "r2": ROW1}, False),          # region with itself
    ({"type": "CONNECTED", "region": {"kind": "between", "a": "A1", "b": "A3"}}, False),  # 1 cell
    ({"type": "NONE", "text": "hi"}, False),
    ({"type": "EXACTLY", "k": 2, "region": ROW1}, False),                    # false on the answer
    ({"type": "EXACTLY", "k": 5, "region": ROW1}, False),                    # invalid
    ({"type": "SAME", "a": "A1", "b": "B2"}, True),
])
def test_is_useful_clue(clue, useful):
    assert is_useful_clue(clue, ANSWER, 3, 3) is useful


# ---------- command line ----------

def test_main_writes_skips_and_overwrites(tmp_path, capsys):
    args = ["--rows", "3", "--cols", "3", "--count", "2", "--seed", "5", "--out", str(tmp_path)]
    assert main(args) == 0
    files = sorted(tmp_path.glob("*.json"))
    assert [f.name for f in files] == ["g3_01.json", "g3_02.json"]
    raw = files[0].read_bytes()
    assert b"\r\n" not in raw and raw.endswith(b"}\n")
    assert raw.decode("utf-8") == to_json(generate(3, 3, 5, 1))
    assert puzzle_problems(load_puzzle(files[0])) == []

    files[0].write_text("keep me", encoding="utf-8")
    main(args)
    assert files[0].read_text(encoding="utf-8") == "keep me"          # not overwritten
    assert "skip g3_01.json" in capsys.readouterr().out
    main(args + ["--force"])
    assert load_puzzle(files[0]).id == "g3_01"
