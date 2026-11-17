"""Contract tests from docs/INTERFACES.md, using puzzles/p3_01.json.

A test is skipped while the function it needs still raises NotImplementedError,
so this file passes on the skeleton and starts checking as each part lands.
"""
import itertools
from pathlib import Path

import pytest

P3 = str(Path(__file__).resolve().parents[1] / "puzzles" / "p3_01.json")
SOLUTION_ORDER = [("A2", "CRIMINAL"), ("A3", "INNOCENT"), ("C2", "INNOCENT"), ("B2", "CRIMINAL"),
                  ("C3", "CRIMINAL"), ("B1", "INNOCENT"), ("C1", "INNOCENT"), ("B3", "INNOCENT")]


def call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except NotImplementedError:
        pytest.skip(f"{fn.__qualname__} not implemented yet")


# ---------- model ----------

def test_load_and_regions():
    from model import load_puzzle, all_cells, region_cells
    p = call(load_puzzle, P3)
    assert (p.rows, p.cols, p.revealed) == (3, 3, ["A1"])
    assert [c.cell for c in p.cells] == call(all_cells, 3, 3)
    assert call(region_cells, {"kind": "row", "row": 2}, 3, 3) == ["A2", "B2", "C2"]
    assert call(region_cells, {"kind": "neighbors", "of": "A1"}, 3, 3) == ["B1", "A2", "B2"]
    assert call(all_cells, 2, 3) == ["A1", "B1", "C1", "A2", "B2", "C2"]


# ---------- dpll ----------

def test_dpll_basic():
    from dpll import dpll_solve
    clauses = [[1, 2], [-1, 2]]
    sat, model, stats = call(dpll_solve, clauses, 2)
    assert sat and model[2] is True and set(model) == {1, 2}
    assert {"decisions", "propagations", "backtracks", "time"} <= stats.keys()
    sat, model, _ = dpll_solve(clauses, 2, [-2])
    assert not sat and model is None
    assert clauses == [[1, 2], [-1, 2]]          # input not modified


# ---------- encoder ----------

def test_encoder_examples():
    from encoder import VarMap, encode_clue
    vm = VarMap(3, 3)
    assert call(vm.var, "A1") == 1 and vm.var("C3") == 9 and vm.cell(9) == "C3"
    assert call(encode_clue, {"type": "FACT", "who": "A2", "status": "CRIMINAL"}, vm) == [[4]]
    diff = encode_clue({"type": "DIFFERENT", "a": "C2", "b": "A2"}, vm)
    assert sorted(map(sorted, diff)) == sorted(map(sorted, [[6, 4], [-6, -4]]))
    assert encode_clue({"type": "NONE", "text": "flavour"}, vm) == []


def test_encoder_matches_evaluator_on_all_3x3_assignments():
    """For every clue of p3_01: CNF satisfiable under an assignment <=> evaluate_clue is True."""
    from model import load_puzzle, all_cells
    from encoder import VarMap, encode_clue, evaluate_clue
    from dpll import dpll_solve
    p = call(load_puzzle, P3)
    cells = all_cells(3, 3)
    for c in p.cells:
        vm = VarMap(3, 3)
        cnf = call(encode_clue, c.clue, vm)
        for bits in itertools.product([False, True], repeat=9):
            a = dict(zip(cells, bits))
            lits = [vm.var(x) if v else -vm.var(x) for x, v in a.items()]
            sat, _, _ = call(dpll_solve, cnf, vm.next_aux - 1, lits)
            assert sat == call(evaluate_clue, c.clue, a, 3, 3), (c.cell, a)


# ---------- engine + agent ----------

def _engine():
    from model import load_puzzle
    from engine import GameEngine
    return call(GameEngine, call(load_puzzle, P3))


def test_public_state_shape():
    s = call(_engine().public_state)
    assert (s["rows"], s["cols"]) == (3, 3)
    assert len(s["cells"]) == 9 and all("status" not in c for c in s["cells"])
    assert s["revealed"] == {"A1": {"type": "FACT", "who": "A2", "status": "CRIMINAL"}}
    assert s["verdicts"] == {"A1": "INNOCENT"}


def test_build_kb_initial():
    from encoder import build_kb
    clauses, vm, stats = call(build_kb, call(_engine().public_state))
    assert sorted(map(sorted, clauses)) == [[-1], [4]]
    assert stats == {"primary": 9, "aux": 0, "clauses": 2}


def test_classify_and_submit():
    e = _engine()
    cls = call(e.agent.classify, e.public_state())
    assert list(cls) == ["B1", "C1", "A2", "B2", "C2", "A3", "B3", "C3"]
    assert cls["A2"] == "CRIMINAL" and all(v == "UNKNOWN" for k, v in cls.items() if k != "A2")
    assert call(e.submit, "B1", "INNOCENT") == "NOT_PROVABLE"
    assert e.submit("A2", "INNOCENT") == "CONTRADICTED"
    assert e.submit("A2", "CRIMINAL") == "ACCEPTED"
    s = e.public_state()
    assert s["verdicts"]["A2"] == "CRIMINAL" and "A2" in s["revealed"]
    assert set(s["revealed"]) == set(s["verdicts"])


def test_hint_and_next_move():
    e = _engine()
    assert call(e.agent.next_move, e.public_state()) == {"cell": "A2", "verdict": "CRIMINAL"}
    assert call(e.agent.hint, e.public_state()) == {"cell": "A2", "verdict": "CRIMINAL", "because": ["A1"]}


def test_solve_whole_puzzle():
    e = _engine()
    r = call(e.agent.solve, e)
    assert r["status"] == "SOLVED" and e.is_solved()
    assert [(s["cell"], s["verdict"]) for s in r["steps"]] == SOLUTION_ORDER
    assert {"primary", "aux", "clauses"} <= r["kb_stats"].keys()
    assert {"sat_calls", "decisions", "propagations", "backtracks", "time"} <= r["stats"].keys()


def test_check_unique():
    from model import load_puzzle
    from agent import check_unique
    assert call(check_unique, call(load_puzzle, P3)) is True
