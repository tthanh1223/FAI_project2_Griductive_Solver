"""Clue tests from docs/CLUES.md section 7.

Skipped while the functions they need still raise NotImplementedError.
The sequential-counter test (CLUES.md 7.3) belongs to the Encoder owner: it needs a private switch.
"""
import itertools
import random

import pytest

from encoder import encode_count



def call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except NotImplementedError:
        pytest.skip(f"{fn.__qualname__} not implemented yet")


def N(x):
    return {"kind": "neighbors", "of": x}


CLUES_3x3 = [
    {"type": "PARITY", "parity": "odd", "region": {"kind": "row", "row": 2}},
    {"type": "PARITY", "parity": "even", "count": "innocent", "region": N("B2")},
    {"type": "COUNT_LINES", "axis": "row", "k": 1, "where": {"type": "EXACTLY", "k": 1}},
    {"type": "COUNT_LINES", "axis": "col", "k": 0, "where": {"type": "AT_LEAST", "k": 2, "count": "innocent"}},
    {"type": "EXACTLY", "k": 1, "region": {"kind": "between", "a": "A2", "b": "C2"}},
    {"type": "CONNECTED", "count": "innocent", "region": {"kind": "col", "col": "B"}},
    {"type": "COMPARE", "r1": {"kind": "row", "row": 1}, "op": ">", "r2": {"kind": "row", "row": 3},
     "count": "innocent"},
    {"type": "AT_LEAST", "k": 2, "count": "innocent", "region": {"kind": "row", "row": 2}},
]

# Candle shop puzzle, 4 cols x 5 rows (CLUES.md 7.1)
CRIMINALS_4x5 = {"A1", "B1", "D2", "C3", "D3", "A5", "B5"}
CLUES_4x5 = {
    "D1": {"type": "COMPARE", "r1": N("A5"), "op": "=", "r2": N("B5")},
    "B2": {"type": "AND", "parts": [
        {"type": "EXACTLY", "k": 2, "count": "innocent", "region": {"kind": "row", "row": 3}},
        {"type": "CONNECTED", "count": "innocent", "region": {"kind": "row", "row": 3}}]},
    "C2": {"type": "AND", "parts": [
        {"type": "EXACTLY", "k": 4, "count": "innocent", "region": N("C5")},
        {"type": "EXACTLY", "k": 1, "count": "innocent",
         "region": {"kind": "inter", "regions": [N("C5"), {"kind": "row", "row": 5}]}}]},
    "C3": {"type": "PARITY", "parity": "odd", "count": "innocent",
           "region": {"kind": "between", "a": "A1", "b": "D1"}},
    "A4": {"type": "COUNT_LINES", "axis": "row", "k": 1, "where": {"type": "EXACTLY", "k": 1}},
    "B4": {"type": "AND", "parts": [
        {"type": "EXACTLY", "k": 2, "count": "innocent", "region": {"kind": "right", "of": "A2"}},
        {"type": "CONNECTED", "count": "innocent", "region": {"kind": "right", "of": "A2"}}]},
    "D4": {"type": "AND", "parts": [
        {"type": "FACT", "who": "D2", "status": "CRIMINAL"},
        {"type": "EXACTLY", "k": 2, "region": {"kind": "above", "of": "D5"}}]},
    "A5": {"type": "EXACTLY", "k": 2, "count": "innocent",
           "region": {"kind": "inter", "regions": [{"kind": "between", "a": "B1", "b": "B5"}, N("A4")]}},
    "B5": {"type": "CONNECTED", "count": "innocent", "region": {"kind": "above", "of": "A5"}},
    "C5": {"type": "COMPARE", "r1": N("A1"), "op": ">", "r2": N("A3")},
}


def _equivalent(clue, rows, cols, assignments):
    from model import all_cells
    from encoder import VarMap, encode_clue, evaluate_clue
    from dpll import dpll_solve
    cells = call(all_cells, rows, cols)
    vm = VarMap(rows, cols)
    cnf = call(encode_clue, clue, vm)
    assert all(c and 0 not in c for c in cnf), "empty clause or literal 0"
    for bits in assignments(len(cells)):
        a = dict(zip(cells, bits))
        lits = [vm.var(x) if a[x] else -vm.var(x) for x in cells]
        sat, _, _ = call(dpll_solve, cnf, vm.next_aux - 1, lits)
        assert sat == call(evaluate_clue, clue, a, rows, cols), (clue, a)


@pytest.mark.parametrize("clue", CLUES_3x3, ids=lambda c: c["type"])
def test_encoder_matches_evaluator_3x3(clue):
    _equivalent(clue, 3, 3, lambda n: itertools.product([False, True], repeat=n))


@pytest.mark.parametrize("cell", list(CLUES_4x5))
def test_encoder_matches_evaluator_4x5(cell):
    rng = random.Random(14003)
    _equivalent(CLUES_4x5[cell], 5, 4,
                lambda n: ([rng.random() < 0.5 for _ in range(n)] for _ in range(400)))


def test_real_puzzle_clues_true_on_solution():
    from model import all_cells
    from encoder import evaluate_clue
    sol = {x: x in CRIMINALS_4x5 for x in call(all_cells, 5, 4)}
    for cell, clue in CLUES_4x5.items():
        assert call(evaluate_clue, clue, sol, 5, 4), cell


@pytest.mark.parametrize("region, expected", [
    ({"kind": "row", "row": 3}, ["A3", "B3", "C3", "D3"]),
    ({"kind": "neighbors", "of": "A4"}, ["A3", "B3", "B4", "A5", "B5"]),
    ({"kind": "corners"}, ["A1", "D1", "A5", "D5"]),
    ({"kind": "above", "of": "D5"}, ["D1", "D2", "D3", "D4"]),
    ({"kind": "below", "of": "B2"}, ["B3", "B4", "B5"]),
    ({"kind": "left", "of": "C1"}, ["A1", "B1"]),
    ({"kind": "right", "of": "A2"}, ["B2", "C2", "D2"]),
    ({"kind": "between", "a": "A1", "b": "D1"}, ["B1", "C1"]),
    ({"kind": "between", "a": "B5", "b": "B1"}, ["B2", "B3", "B4"]),
    ({"kind": "between", "a": "A1", "b": "B1"}, []),
    ({"kind": "above", "of": "C1"}, []),
    ({"kind": "inter", "regions": [{"kind": "between", "a": "B1", "b": "B5"}, N("A4")]}, ["B3", "B4"]),
])
def test_regions_4x5(region, expected):
    from model import region_cells
    assert call(region_cells, region, 5, 4) == expected


def test_edges_count():
    from model import region_cells
    assert len(call(region_cells, {"kind": "edges"}, 5, 4)) == 14


def test_cells_in_clue_includes_anchors():
    from model import cells_in_clue
    assert call(cells_in_clue, CLUES_4x5["A5"], 5, 4) == ["B1", "B3", "A4", "B4", "B5"]


@pytest.mark.parametrize("clue", [
    {"type": "WHATEVER"},
    {"type": "FACT", "who": "Z9", "status": "CRIMINAL"},
    {"type": "EXACTLY", "k": 5, "region": {"kind": "row", "row": 1}},
    {"type": "EXACTLY", "k": 1, "region": {"kind": "between", "a": "A1", "b": "B2"}},
    {"type": "PARITY", "parity": "odd", "region": {"kind": "above", "of": "A1"}},
    {"type": "CONNECTED", "region": N("B2")},
    {"type": "COMPARE", "r1": {"kind": "all"}, "op": ">", "r2": {"kind": "row", "row": 1}},
    {"type": "AND", "parts": []},
    {"type": "COUNT_LINES", "axis": "row", "k": 6, "where": {"type": "EXACTLY", "k": 1}},
    {"type": "COUNT_LINES", "axis": "row", "k": 1,
     "where": {"type": "EXACTLY", "k": 1, "region": {"kind": "row", "row": 1}}},
], ids=lambda c: c["type"])
def test_validate_rejects(clue):
    from encoder import validate_clue
    try:
        validate_clue(clue, 5, 4)
    except NotImplementedError:
        pytest.skip("validate_clue not implemented yet")
    except ValueError:
        return
    pytest.fail(f"accepted invalid clue {clue}")
    
@pytest.mark.parametrize("n", [5, 6])
@pytest.mark.parametrize("kind", ["AT_MOST", "AT_LEAST", "EXACTLY"])
def test_sequential_counter_matches_combinations(n, kind):
    from encoder import VarMap, encode_count
    from dpll import dpll_solve

    for k in range(n + 1):
        direct_vm = VarMap(1, n)
        seq_vm = VarMap(1, n)

        # Mixed signs also exercise counting negated literals.
        lits = [i if i % 2 else -i for i in range(1, n + 1)]
        direct = encode_count(kind, lits, k, direct_vm, limit=2000)
        sequential = encode_count(kind, lits, k, seq_vm, limit=0)

        if 0 < k < n:
            assert seq_vm.next_aux > n + 1

        for bits in itertools.product((False, True), repeat=n):
            fixed = [
                i if value else -i
                for i, value in enumerate(bits, start=1)
            ]
            total = sum(
                bits[abs(lit) - 1] == (lit > 0)
                for lit in lits
            )
            expected = {
                "AT_MOST": total <= k,
                "AT_LEAST": total >= k,
                "EXACTLY": total == k,
            }[kind]

            sat_direct, _, _ = call(
                dpll_solve, direct, direct_vm.next_aux - 1, fixed
            )
            sat_seq, _, _ = call(
                dpll_solve, sequential, seq_vm.next_aux - 1, fixed
            )
            assert sat_direct == sat_seq == expected, (kind, n, k, bits)
            
@pytest.mark.parametrize("kind", ["AT_MOST", "AT_LEAST", "EXACTLY"])
@pytest.mark.parametrize("innocent", [False, True])
def test_basic_counts_on_512_boards(kind, innocent):
    from encoder import VarMap, encode_count

    for k in range(4):
        vm = VarMap(3, 3)
        column = [vm.var(cell) for cell in ("A1", "A2", "A3")]
        lits = [-x for x in column] if innocent else column
        cnf = encode_count(kind, lits, k, vm)

        for bits in itertools.product((False, True), repeat=9):
            total = sum(bits[x - 1] == (not innocent) for x in column)
            expected = {
                "AT_MOST": total <= k,
                "AT_LEAST": total >= k,
                "EXACTLY": total == k,
            }[kind]
            actual = all(
                any(bits[abs(lit) - 1] == (lit > 0) for lit in clause)
                for clause in cnf
            )
            assert actual == expected, (kind, innocent, k, bits)