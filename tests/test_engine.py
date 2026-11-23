"""Tests for engine.py: GameEngine contract, independent oracle, fuzzing, atomicity."""
import copy
import itertools
import json
import random
from pathlib import Path

import pytest

from agent import INCONSISTENT, LogicAgent
from encoder import evaluate_clue
from engine import ACCEPTED, CONTRADICTED, NOT_PROVABLE, GameEngine
from model import CRIMINAL, INNOCENT, Cell, Puzzle, all_cells, load_puzzle

PUZZLES = Path(__file__).resolve().parents[1] / "puzzles"
P3 = PUZZLES / "p3_01.json"
P3_ORDER = ["A2", "A3", "C2", "B2", "C3", "B1", "C1", "B3"]
# Puzzles small enough for the brute-force oracle (2^cells assignments per state).
SMALL = [p for p in sorted(PUZZLES.glob("*.json")) if len(json.loads(p.read_text(encoding="utf-8-sig"))["cells"]) <= 9]


def _p3() -> Puzzle:
    return load_puzzle(P3)


def _statuses(puzzle: Puzzle) -> dict:
    return {c.cell: c.status for c in puzzle.cells}


# ---------- initial state, copies, restart ----------

def test_initial_public_state():
    e = GameEngine(_p3())
    s = e.public_state()
    assert (s["rows"], s["cols"]) == (3, 3)
    assert [c["cell"] for c in s["cells"]] == all_cells(3, 3)
    assert all(c.keys() == {"cell", "name", "job"} for c in s["cells"])
    assert s["cells"][0] == {"cell": "A1", "name": "Alice", "job": "Cook"}
    assert s["revealed"] == {"A1": {"type": "FACT", "who": "A2", "status": "CRIMINAL"}}
    assert s["verdicts"] == {"A1": INNOCENT}
    assert not e.is_solved()


def test_public_state_is_a_copy():
    e = GameEngine(_p3())
    before = e.public_state()
    s = e.public_state()
    s["revealed"]["A1"]["who"] = "B1"
    s["verdicts"]["B1"] = CRIMINAL
    s["cells"][0]["name"] = "X"
    s["cells"].pop()
    assert e.public_state() == before


def test_engine_copies_the_puzzle():
    p = _p3()
    e = GameEngine(p)
    before = e.public_state()
    p.cells[0].status = CRIMINAL
    p.cells[0].clue["who"] = "B1"
    p.cells[1].clue = {"type": "NONE", "text": "changed"}
    p.revealed.append("B1")
    assert e.public_state() == before
    e.restart()
    assert e.public_state() == before
    assert e.agent.solve(e)["status"] == "SOLVED"


def test_restart_returns_to_initial_state():
    e = GameEngine(_p3())
    initial = e.public_state()
    assert e.submit("A2", CRIMINAL) == ACCEPTED
    assert e.submit("A3", INNOCENT) == ACCEPTED
    assert e.public_state() != initial
    e.restart()
    s = e.public_state()
    assert s == initial and set(s["revealed"]) == set(s["verdicts"])


def test_cells_given_out_of_order_are_served_row_major():
    p = _p3()
    p.cells.reverse()
    s = GameEngine(p).public_state()
    assert [c["cell"] for c in s["cells"]] == all_cells(3, 3)


# ---------- submit ----------

def test_three_results_and_flip():
    e = GameEngine(_p3())
    before = e.public_state()
    assert e.submit("B1", INNOCENT) == NOT_PROVABLE
    assert e.submit("A2", INNOCENT) == CONTRADICTED
    assert e.public_state() == before                      # rejections change nothing
    assert e.submit("A2", CRIMINAL) == ACCEPTED
    s = e.public_state()
    assert s["verdicts"] == {"A1": INNOCENT, "A2": CRIMINAL}
    assert s["revealed"]["A2"] == {"type": "EXACTLY", "k": 1, "region": {"kind": "col", "col": "A"}}


@pytest.mark.parametrize("cell, verdict", [
    ("D1", CRIMINAL), ("a2", CRIMINAL), (None, CRIMINAL),      # unknown cell
    ("A2", "criminal"), ("A2", "UNKNOWN"), ("A2", None),      # bad verdict
    ("A1", INNOCENT), ("A1", CRIMINAL),                       # face-up at the start
])
def test_submit_value_errors(cell, verdict):
    e = GameEngine(_p3())
    before = e.public_state()
    with pytest.raises(ValueError):
        e.submit(cell, verdict)
    assert e.public_state() == before


def test_submit_on_decided_cell():
    e = GameEngine(_p3())
    e.submit("A2", CRIMINAL)
    with pytest.raises(ValueError):
        e.submit("A2", CRIMINAL)


def test_full_solve_matches_hidden_solution():
    p = _p3()
    e = GameEngine(p)
    result = e.agent.solve(e)
    assert result["status"] == "SOLVED" and e.is_solved()
    assert [s["cell"] for s in result["steps"]] == P3_ORDER
    s = e.public_state()
    assert s["verdicts"] == _statuses(p)
    assert s["revealed"] == {c.cell: c.clue for c in p.cells}


def test_default_agent_and_injected_agent():
    assert isinstance(GameEngine(_p3()).agent, LogicAgent)
    agent = LogicAgent(optimized=False)
    assert GameEngine(_p3(), agent).agent is agent


# ---------- puzzle checks at construction ----------

def _with(edit):
    p = _p3()
    edit(p)
    return p


@pytest.mark.parametrize("edit, message", [
    (lambda p: setattr(p.cells[0], "clue", {"type": "FACT", "who": "A2", "status": INNOCENT}), "false"),
    (lambda p: setattr(p.cells[7], "clue", {"type": "AT_MOST", "k": 0, "region": {"kind": "row", "row": 3}}),
     "false"),
    (lambda p: setattr(p.cells[0], "clue", {"type": "EXACTLY", "k": 4, "region": {"kind": "row", "row": 1}}),
     "Clue of A1"),
    (lambda p: setattr(p.cells[0], "clue", {"type": "MAYBE"}), "Clue of A1"),
    (lambda p: setattr(p.cells[0], "clue", {"type": "FACT", "who": "Z9", "status": CRIMINAL}), "Clue of A1"),
    (lambda p: setattr(p.cells[0], "status", "GUILTY"), "status"),
    (lambda p: p.cells.pop(), "grid"),
    (lambda p: setattr(p.cells[1], "cell", "A1"), "grid"),
    (lambda p: setattr(p.cells[8], "cell", "D4"), "grid"),
    (lambda p: p.revealed.append("Z1"), "Revealed"),
])
def test_bad_puzzles_are_rejected(edit, message):
    with pytest.raises(ValueError, match=message):
        GameEngine(_with(edit))


# ---------- independent oracle: brute force with evaluate_clue (no CNF, no DPLL) ----------

def _oracle(state):
    """{cell: forced status or None} for every undecided cell, by enumerating all grids."""
    rows, cols = state["rows"], state["cols"]
    cells = all_cells(rows, cols)
    models = []
    for bits in itertools.product((False, True), repeat=len(cells)):
        a = dict(zip(cells, bits))
        if (all(a[c] == (v == CRIMINAL) for c, v in state["verdicts"].items())
                and all(evaluate_clue(clue, a, rows, cols) for clue in state["revealed"].values())):
            models.append(a)
    assert models, "public knowledge must stay consistent"
    out = {}
    for c in cells:
        if c not in state["verdicts"]:
            values = {m[c] for m in models}
            out[c] = None if len(values) == 2 else (CRIMINAL if values == {True} else INNOCENT)
    return out


def _expected(forced, verdict):
    if forced is None:
        return NOT_PROVABLE
    return ACCEPTED if forced == verdict else CONTRADICTED


@pytest.mark.parametrize("path", SMALL, ids=lambda p: p.stem)
def test_submit_matches_brute_force_at_every_step(path):
    e = GameEngine(load_puzzle(path))
    while not e.is_solved():
        oracle = _oracle(e.public_state())
        for cell, forced in oracle.items():
            for verdict in (CRIMINAL, INNOCENT):
                trial = copy.deepcopy(e)
                assert trial.submit(cell, verdict) == _expected(forced, verdict), (cell, verdict)
        cell = next(c for c, f in oracle.items() if f is not None)      # puzzle is no-guess solvable
        assert e.submit(cell, oracle[cell]) == ACCEPTED


# ---------- fuzzing: random verdicts until solved ----------

@pytest.mark.parametrize("seed", range(20))
def test_random_play_keeps_invariants(seed):
    rng = random.Random(seed)
    p = _p3()
    hidden_status, hidden_clue = _statuses(p), {c.cell: c.clue for c in p.cells}
    e = GameEngine(p)
    for _ in range(5000):
        if e.is_solved():
            break
        before = e.public_state()
        cell = rng.choice(sorted(set(all_cells(3, 3)) - set(before["verdicts"])))
        result = e.submit(cell, rng.choice((CRIMINAL, INNOCENT)))
        s = e.public_state()
        if result != ACCEPTED:
            assert s == before
        assert set(s["revealed"]) == set(s["verdicts"])
        assert all(hidden_status[c] == v for c, v in s["verdicts"].items())
        assert all(hidden_clue[c] == clue for c, clue in s["revealed"].items())
        dumped = json.loads(json.dumps(s))
        assert all("status" not in c for c in dumped["cells"])
    assert e.is_solved()


# ---------- atomicity: agent bugs leave the state unchanged ----------

class _FakeAgent:
    def __init__(self, result):
        self.result = result

    def classify(self, state):
        return copy.deepcopy(self.result)


@pytest.mark.parametrize("result, error", [
    ({"B1": CRIMINAL}, AssertionError),       # B1 is innocent: a wrong "proof"
    (INCONSISTENT, RuntimeError),
    ({}, RuntimeError),                        # no result for the cell
    ({"B1": "MAYBE"}, RuntimeError),
])
def test_agent_bugs_do_not_change_state(result, error):
    e = GameEngine(_p3(), _FakeAgent(result))
    before = e.public_state()
    with pytest.raises(error):
        e.submit("B1", CRIMINAL)
    assert e.public_state() == before


def test_puzzle_built_in_code_without_load_puzzle():
    cells = [Cell(cell, f"N{i}", "Job", INNOCENT, {"type": "NONE", "text": "-"})
             for i, cell in enumerate(all_cells(2, 2))]
    cells[0].clue = {"type": "EXACTLY", "k": 0, "region": {"kind": "all"}}
    e = GameEngine(Puzzle("tiny", 2, 2, cells, ["A1"]))
    assert e.agent.solve(e)["status"] == "SOLVED"
    assert e.public_state()["verdicts"] == {c: INNOCENT for c in all_cells(2, 2)}
