"""Tests for agent.py (DPLL & Agent owner).

_MiniEngine below follows the engine contract in docs/INTERFACES.md, so the
agent is also tested without the real GameEngine.
"""
import copy
import itertools
import json
import random
from pathlib import Path

import pytest

from agent import INCONSISTENT, UNKNOWN, LogicAgent, check_unique
from model import CRIMINAL, INNOCENT, Cell, Puzzle

P3 = Path(__file__).resolve().parents[1] / "puzzles" / "p3_01.json"
SOLUTION_ORDER = [("A2", "CRIMINAL"), ("A3", "INNOCENT"), ("C2", "INNOCENT"), ("B2", "CRIMINAL"),
                  ("C3", "CRIMINAL"), ("B1", "INNOCENT"), ("C1", "INNOCENT"), ("B3", "INNOCENT")]


def names(rows, cols):
    return [f"{chr(65 + c)}{r + 1}" for r in range(rows) for c in range(cols)]


def p3_puzzle() -> Puzzle:
    """p3_01 read with json directly, so these tests do not wait for model.load_puzzle."""
    d = json.loads(P3.read_text())
    cells = [Cell(c["cell"], c["name"], c["job"], c["status"], c["clue"]) for c in d["cells"]]
    return Puzzle(d["id"], d["size"], d["size"], cells, list(d.get("revealed", [])))


class _MiniEngine:
    """GameEngine as described in docs/INTERFACES.md (only what the agent needs)."""

    def __init__(self, puzzle: Puzzle, agent: LogicAgent | None = None):
        self.puzzle = puzzle
        self.agent = agent or LogicAgent()
        self.by = {c.cell: c for c in puzzle.cells}
        self.revealed = {c: self.by[c].clue for c in puzzle.revealed}
        self.verdicts = {c: self.by[c].status for c in puzzle.revealed}

    def public_state(self):
        return copy.deepcopy({
            "rows": self.puzzle.rows, "cols": self.puzzle.cols,
            "cells": [{"cell": c.cell, "name": c.name, "job": c.job} for c in self.puzzle.cells],
            "revealed": self.revealed, "verdicts": self.verdicts})

    def submit(self, cell, verdict):
        got = self.agent.classify(self.public_state())[cell]
        if got == verdict:
            assert verdict == self.by[cell].status, f"agent proved a wrong verdict for {cell}"
            self.verdicts[cell] = verdict
            self.revealed[cell] = self.by[cell].clue
            return "ACCEPTED"
        return "NOT_PROVABLE" if got == UNKNOWN else "CONTRADICTED"

    def is_solved(self):
        return len(self.verdicts) == self.puzzle.rows * self.puzzle.cols


def state(rows, cols, revealed, verdicts):
    return {"rows": rows, "cols": cols,
            "cells": [{"cell": c, "name": c, "job": "-"} for c in names(rows, cols)],
            "revealed": revealed, "verdicts": verdicts}


def brute_force_classify(st):
    """Reference: enumerate every grid that agrees with the verdicts, keep those
    satisfying the face-up clues."""
    from encoder import evaluate_clue
    rows, cols = st["rows"], st["cols"]
    cells = names(rows, cols)
    free = [c for c in cells if c not in st["verdicts"]]
    fixed = {c: s == CRIMINAL for c, s in st["verdicts"].items() if c in cells}
    models = []
    for bits in itertools.product((False, True), repeat=len(free)):
        a = dict(fixed)
        a.update(zip(free, bits))
        if all(evaluate_clue(clue, a, rows, cols) for clue in st["revealed"].values()):
            models.append(a)
    if not models:
        return INCONSISTENT
    out = {}
    for c in free:
        values = {m[c] for m in models}
        out[c] = UNKNOWN if len(values) == 2 else (CRIMINAL if values == {True} else INNOCENT)
    return out


# ---------- random puzzles (clues true on a hidden solution) ----------

def random_region(rng, rows, cols):
    cells = names(rows, cols)
    x = rng.choice(cells)
    kind = rng.choice(["row", "col", "neighbors", "cells", "above", "below", "left", "right", "all"])
    if kind == "row":
        return {"kind": "row", "row": rng.randint(1, rows)}
    if kind == "col":
        return {"kind": "col", "col": chr(65 + rng.randrange(cols))}
    if kind == "cells":
        return {"kind": "cells", "cells": sorted(rng.sample(cells, rng.randint(1, 3)), key=cells.index)}
    if kind == "all":
        return {"kind": "all"}
    return {"kind": kind, "of": x}


ALL_TYPES = ["FACT", "SAME", "DIFFERENT", "EXACTLY", "AT_LEAST", "AT_MOST", "PARITY", "COMPARE", "NONE"]
# Mostly informative clues, so that many random puzzles can be solved to the end.
STRONG_TYPES = ["EXACTLY"] * 4 + ["SAME", "DIFFERENT", "PARITY", "COMPARE", "AT_MOST"]


def random_true_clue(rng, rows, cols, solution, types=ALL_TYPES):
    """A random clue that is true on `solution` (cell -> bool)."""
    from encoder import evaluate_clue, validate_clue
    cells = names(rows, cols)
    while True:
        t = rng.choice(types)
        count = rng.choice(["criminal", "innocent"])
        if t == "FACT":
            who = rng.choice(cells)
            clue = {"type": t, "who": who, "status": CRIMINAL if solution[who] else INNOCENT}
        elif t in ("SAME", "DIFFERENT"):
            a, b = rng.sample(cells, 2)
            clue = {"type": "SAME" if solution[a] == solution[b] else "DIFFERENT", "a": a, "b": b}
        elif t == "NONE":
            clue = {"type": "NONE", "text": "flavour"}
        elif t == "PARITY":
            clue = {"type": t, "parity": rng.choice(["odd", "even"]), "count": count,
                    "region": random_region(rng, rows, cols)}
        elif t == "COMPARE":
            clue = {"type": t, "r1": random_region(rng, rows, cols), "op": rng.choice("<>="),
                    "r2": random_region(rng, rows, cols), "count": count}
        else:
            region = random_region(rng, rows, cols)
            n = sum(1 for c in _region(region, rows, cols) if solution[c] == (count == "criminal"))
            clue = {"type": t, "region": region, "count": count, "k": n}
            if t == "AT_LEAST":
                clue["k"] = rng.randint(0, n)
            elif t == "AT_MOST":
                clue["k"] = rng.randint(n, len(_region(region, rows, cols)))
        try:
            validate_clue(clue, rows, cols)
        except ValueError:
            continue
        if evaluate_clue(clue, solution, rows, cols):
            return clue


def _region(region, rows, cols):
    from model import region_cells
    return region_cells(region, rows, cols)


def random_puzzle(seed, rows=3, cols=3, n_revealed=1, types=ALL_TYPES):
    rng = random.Random(seed)
    cells = names(rows, cols)
    solution = {c: rng.random() < 0.4 for c in cells}
    puzzle_cells = [Cell(c, c, "-", CRIMINAL if solution[c] else INNOCENT,
                         random_true_clue(rng, rows, cols, solution, types)) for c in cells]
    revealed = sorted(rng.sample(cells, n_revealed), key=cells.index)
    return Puzzle(f"rand{seed}", rows, cols, puzzle_cells, revealed), solution


def random_state(seed):
    """A mid-game public state: some face-up clues and their verdicts (all true)."""
    rng = random.Random(seed)
    rows, cols = rng.choice([(2, 2), (2, 3), (3, 3), (3, 4)])
    puzzle, _ = random_puzzle(seed, rows, cols, rng.randint(1, min(4, rows * cols)))
    by = {c.cell: c for c in puzzle.cells}
    revealed = {c: by[c].clue for c in puzzle.revealed}
    verdicts = {c: by[c].status for c in puzzle.revealed}
    return state(rows, cols, revealed, verdicts)


# ---------- p3_01 ----------

def test_p3_initial_classify_next_move_hint():
    e = _MiniEngine(p3_puzzle())
    a = e.agent
    cls = a.classify(e.public_state())
    assert list(cls) == ["B1", "C1", "A2", "B2", "C2", "A3", "B3", "C3"]
    assert cls == {c: (CRIMINAL if c == "A2" else UNKNOWN) for c in cls}
    assert a.next_move(e.public_state()) == {"cell": "A2", "verdict": "CRIMINAL"}
    assert a.hint(e.public_state()) == {"cell": "A2", "verdict": "CRIMINAL", "because": ["A1"]}


def test_p3_solve_trace():
    e = _MiniEngine(p3_puzzle())
    r = e.agent.solve(e)
    assert r["status"] == "SOLVED" and e.is_solved()
    assert [(s["cell"], s["verdict"]) for s in r["steps"]] == SOLUTION_ORDER
    assert [s["step"] for s in r["steps"]] == list(range(1, 9))
    assert all(s["result"] == "ACCEPTED" for s in r["steps"])
    assert r["steps"][0]["active_clues"] == ["A1"]
    assert r["steps"][1]["active_clues"] == ["A1", "A2"]
    by = {c.cell: c.clue for c in p3_puzzle().cells}
    assert all(s["revealed_clue"] == by[s["cell"]] for s in r["steps"])
    assert r["kb_stats"]["primary"] == 9
    assert r["stats"]["sat_calls"] == sum(s["sat_calls"] for s in r["steps"])
    assert set(r["stats"]) == {"sat_calls", "decisions", "propagations", "backtracks", "time"}


def test_p3_sat_calls_per_step():
    """Optimized: at most 1 + unsolved per step. Plain: exactly 1 + 2 * unsolved."""
    for optimized in (True, False):
        e = _MiniEngine(p3_puzzle(), LogicAgent(optimized=optimized))
        r = e.agent.solve(e)
        for s in r["steps"]:
            unsolved = 9 - s["step"]                   # A1 is face-up, one more verdict per step
            if optimized:
                assert 1 <= s["sat_calls"] <= 1 + unsolved
            else:
                assert s["sat_calls"] == 1 + 2 * unsolved


def test_p3_check_unique():
    assert check_unique(p3_puzzle()) is True


# ---------- agent against brute force ----------

@pytest.mark.parametrize("seed", range(60))
def test_classify_matches_brute_force(seed):
    st = random_state(seed)
    expected = brute_force_classify(st)
    for optimized in (True, False):
        got = LogicAgent(optimized=optimized).classify(copy.deepcopy(st))
        assert got == expected, (optimized, st)
        if isinstance(got, dict):
            assert list(got) == [c for c in names(st["rows"], st["cols"]) if c not in st["verdicts"]]


@pytest.mark.parametrize("seed", range(40))
def test_hint_because_is_minimal_and_sufficient(seed):
    st = random_state(seed)
    a = LogicAgent()
    h = a.hint(st)
    if h is None:
        assert a.next_move(st) is None
        return
    assert {"cell": h["cell"], "verdict": h["verdict"]} == a.next_move(st)
    assert h["because"] == [c for c in names(st["rows"], st["cols"]) if c in h["because"]]
    assert set(h["because"]) <= set(st["revealed"])

    def forced_with(cells):
        sub = dict(st, revealed={c: st["revealed"][c] for c in cells})
        return brute_force_classify(sub)[h["cell"]] == h["verdict"]

    assert forced_with(h["because"])                                      # sufficient
    for c in h["because"]:
        assert not forced_with([d for d in h["because"] if d != c])       # each one needed


def brute_force_play(puzzle):
    """Play the game with brute_force_classify instead of the agent: list of (cell, verdict)."""
    e = _MiniEngine(puzzle)
    moves = []
    while not e.is_solved():
        ref = brute_force_classify(e.public_state())
        forced = [(c, v) for c, v in ref.items() if v != UNKNOWN]
        if not forced:
            break
        cell, verdict = forced[0]
        e.verdicts[cell] = verdict
        e.revealed[cell] = e.by[cell].clue
        moves.append((cell, verdict))
    return moves, e.is_solved()


def solvable_puzzle(seed):
    """First random 3x3 puzzle (from this seed) that brute force can play to the end."""
    for i in range(500):
        puzzle, _ = random_puzzle(seed * 1000 + i, 3, 3, 2, STRONG_TYPES)
        if brute_force_play(puzzle)[1]:
            return puzzle
    raise AssertionError("no solvable puzzle found")


def check_solve_against_brute_force(puzzle):
    e = _MiniEngine(puzzle)                            # asserts every accepted verdict is right
    r = e.agent.solve(e)
    moves, solved = brute_force_play(puzzle)
    assert [(s["cell"], s["verdict"]) for s in r["steps"]] == moves
    assert all(s["result"] == "ACCEPTED" for s in r["steps"])
    assert r["status"] == ("SOLVED" if solved else "STUCK")
    assert e.is_solved() == solved
    return r


@pytest.mark.parametrize("seed", range(30))
def test_solve_plays_solvable_puzzles_to_the_end(seed):
    puzzle = solvable_puzzle(seed)
    r = check_solve_against_brute_force(puzzle)
    assert r["status"] == "SOLVED" and len(r["steps"]) == 7      # 9 cells, 2 face-up


@pytest.mark.parametrize("seed", range(30))
def test_solve_stops_exactly_where_brute_force_gets_stuck(seed):
    rows, cols = [(3, 3), (2, 4), (3, 4)][seed % 3]
    puzzle, _ = random_puzzle(1000 + seed, rows, cols, 1 + seed % 2, STRONG_TYPES)
    check_solve_against_brute_force(puzzle)


# ---------- special cases ----------

def test_inconsistent_kb():
    st = state(2, 2, {"A1": {"type": "FACT", "who": "B1", "status": CRIMINAL},
                      "A2": {"type": "FACT", "who": "B1", "status": INNOCENT}},
               {"A1": INNOCENT, "A2": INNOCENT})
    a = LogicAgent()
    assert a.classify(st) == INCONSISTENT
    assert a.next_move(st) is None and a.hint(st) is None


def test_inconsistent_solve_status():
    cells = [Cell("A1", "a", "-", INNOCENT, {"type": "FACT", "who": "A1", "status": CRIMINAL}),
             Cell("B1", "b", "-", INNOCENT, {"type": "NONE", "text": "x"})]
    e = _MiniEngine(Puzzle("bad", 1, 2, cells, ["A1"]))
    r = e.agent.solve(e)
    assert r["status"] == INCONSISTENT and r["steps"] == []


def test_stuck_when_nothing_forced():
    cells = [Cell("A1", "a", "-", INNOCENT, {"type": "NONE", "text": "x"}),
             Cell("B1", "b", "-", CRIMINAL, {"type": "NONE", "text": "y"})]
    e = _MiniEngine(Puzzle("stuck", 1, 2, cells, ["A1"]))
    r = e.agent.solve(e)
    assert r["status"] == "STUCK" and r["steps"] == []
    assert e.agent.next_move(e.public_state()) is None and e.agent.hint(e.public_state()) is None


def test_all_cells_decided_gives_empty_dict():
    st = state(1, 2, {"A1": {"type": "NONE", "text": "x"}, "B1": {"type": "NONE", "text": "y"}},
               {"A1": INNOCENT, "B1": CRIMINAL})
    assert LogicAgent().classify(st) == {}


def test_hint_leaves_out_unneeded_clues():
    # A1 says exactly 1 criminal among B1, C1; B1 is innocent (verdict); C1's clue says C1 = C2.
    # C1 (first forced) needs only A1's clue; A2's clue is face-up but not needed for C1.
    st = state(2, 3, {"A1": {"type": "EXACTLY", "k": 1, "region": {"kind": "cells", "cells": ["B1", "C1"]}},
                      "B1": {"type": "NONE", "text": "x"},
                      "A2": {"type": "SAME", "a": "C1", "b": "C2"}},
               {"A1": INNOCENT, "B1": INNOCENT, "A2": INNOCENT})
    a = LogicAgent()
    assert a.classify(st) == {"C1": CRIMINAL, "B2": UNKNOWN, "C2": CRIMINAL}
    assert a.hint(st) == {"cell": "C1", "verdict": CRIMINAL, "because": ["A1"]}


def test_hint_prefers_one_clue_that_explains_alone():
    # A1 alone forces A2. B1 + C1 together also force it; the hint must say A1.
    st = state(3, 3, {"A1": {"type": "FACT", "who": "A2", "status": CRIMINAL},
                      "B1": {"type": "AT_LEAST", "k": 1, "region": {"kind": "cells", "cells": ["A2", "C3"]}},
                      "C1": {"type": "FACT", "who": "C3", "status": INNOCENT}},
               {"A1": INNOCENT, "B1": INNOCENT, "C1": INNOCENT})
    assert LogicAgent().hint(st) == {"cell": "A2", "verdict": CRIMINAL, "because": ["A1"]}


def test_cache_repeats_cost_nothing_and_results_are_copies():
    st = random_state(3)
    a = LogicAgent()
    first = a.classify(st)
    calls = a.stats["sat_calls"]
    second = a.classify(copy.deepcopy(st))
    assert second == first and a.stats["sat_calls"] == calls
    if isinstance(second, dict):
        second.clear()                                 # caller damage must not reach the cache
        assert a.classify(st) == first


def test_state_not_modified_and_reset_stats():
    st = random_state(5)
    before = copy.deepcopy(st)
    a = LogicAgent()
    a.classify(st)
    a.hint(st)
    assert st == before
    assert a.stats["sat_calls"] > 0
    a.reset_stats()
    assert a.stats == {"sat_calls": 0, "decisions": 0, "propagations": 0, "backtracks": 0, "time": 0.0}


def test_check_unique_false_cases():
    none = {"type": "NONE", "text": "x"}
    # No information: 2 grids.
    two = Puzzle("two", 1, 2, [Cell("A1", "a", "-", INNOCENT, none), Cell("B1", "b", "-", CRIMINAL, none)], ["A1"])
    assert check_unique(two) is False
    # Contradiction: 0 grids.
    zero = Puzzle("zero", 1, 2, [Cell("A1", "a", "-", INNOCENT, {"type": "FACT", "who": "A1", "status": CRIMINAL}),
                                 Cell("B1", "b", "-", CRIMINAL, none)], ["A1"])
    assert check_unique(zero) is False
    # Face-down clue decides B1: unique.
    fact_b1 = {"type": "FACT", "who": "B1", "status": CRIMINAL}
    one = Puzzle("one", 1, 2, [Cell("A1", "a", "-", INNOCENT, none),
                               Cell("B1", "b", "-", CRIMINAL, fact_b1)], ["A1"])
    assert check_unique(one) is True


def test_check_unique_blocks_only_primary_variables():
    # AT_MOST 7 of 16 uses the sequential counter: its aux variables have slack,
    # so the one grid has many models. Blocking every variable would say "not unique".
    cells = names(4, 4)
    puzzle_cells = [Cell("A1", "a", "-", CRIMINAL, {"type": "AND", "parts": [
        {"type": "FACT", "who": "A1", "status": CRIMINAL},
        {"type": "AT_MOST", "k": 7, "region": {"kind": "all"}}]})]
    puzzle_cells += [Cell(c, c, "-", INNOCENT, {"type": "FACT", "who": c, "status": INNOCENT}) for c in cells[1:]]
    assert check_unique(Puzzle("slack", 4, 4, puzzle_cells, ["A1"])) is True


def test_check_unique_ignores_aux_variables():
    # COUNT_LINES adds auxiliary variables; the grid is still unique.
    none = {"type": "NONE", "text": "x"}
    cells = [Cell("A1", "a", "-", CRIMINAL, {"type": "COUNT_LINES", "axis": "row", "k": 2,
                                              "where": {"type": "EXACTLY", "k": 1}}),
             Cell("A2", "b", "-", CRIMINAL, none)]
    assert check_unique(Puzzle("aux", 2, 1, cells, ["A1"])) is True


@pytest.mark.parametrize("seed", range(40))
def test_check_unique_matches_brute_force(seed):
    from encoder import evaluate_clue
    puzzle, _ = random_puzzle(2000 + seed, 2, 3, 1)
    cells = names(2, 3)
    by = {c.cell: c for c in puzzle.cells}
    count = 0
    for bits in itertools.product((False, True), repeat=6):
        a = dict(zip(cells, bits))
        if all(a[c] == (by[c].status == CRIMINAL) for c in puzzle.revealed) and \
           all(evaluate_clue(c.clue, a, 2, 3) for c in puzzle.cells):
            count += 1
    assert check_unique(puzzle) is (count == 1)


# ---------- reuse between calls ----------

def game_states(puzzle):
    """Every public state of a game played with brute force, in order."""
    e = _MiniEngine(puzzle)
    states = [e.public_state()]
    for cell, verdict in brute_force_play(puzzle)[0]:
        e.verdicts[cell] = verdict
        e.revealed[cell] = e.by[cell].clue
        states.append(e.public_state())
    return states


@pytest.mark.parametrize("seed", range(15))
def test_reuse_along_a_game_and_in_random_order(seed):
    """One agent fed the states of a game, then the same states shuffled (so most
    calls do not extend the previous one): every answer equals brute force."""
    states = game_states(solvable_puzzle(100 + seed))
    a = LogicAgent()
    for st in states:
        assert a.classify(st) == brute_force_classify(st)
    shuffled = states[:]
    random.Random(seed).shuffle(shuffled)
    for st in shuffled + states[::-1]:
        assert a.classify(st) == brute_force_classify(st)


def test_reuse_saves_sat_calls_and_reset_stats_starts_cold():
    puzzle = solvable_puzzle(7)
    runs = []
    for optimized in (True, False):
        e = _MiniEngine(puzzle, LogicAgent(optimized=optimized))
        runs.append(e.agent.solve(e))
    fast, plain = runs
    assert [s["cell"] for s in fast["steps"]] == [s["cell"] for s in plain["steps"]]
    assert fast["stats"]["sat_calls"] < plain["stats"]["sat_calls"]

    a = LogicAgent()
    e1 = _MiniEngine(puzzle, a)
    first = a.solve(e1)["stats"]
    a.reset_stats()
    e2 = _MiniEngine(puzzle, a)
    second = a.solve(e2)["stats"]
    assert {k: v for k, v in first.items() if k != "time"} == \
           {k: v for k, v in second.items() if k != "time"}


def test_cache_depends_on_optimized():
    st = random_state(11)
    a = LogicAgent()
    a.classify(st)
    a.optimized = False
    before = a.stats["sat_calls"]
    a.classify(st)
    assert a.stats["sat_calls"] > before


def test_inconsistent_extension_is_still_caught():
    # Step 1: A1 says B1 is criminal -> B1 forced. Step 2 (extends step 1): a
    # verdict that says B1 innocent. The reused forced value must not hide the conflict.
    first = state(1, 3, {"A1": {"type": "FACT", "who": "B1", "status": CRIMINAL}}, {"A1": INNOCENT})
    a = LogicAgent()
    assert a.classify(first) == {"B1": CRIMINAL, "C1": UNKNOWN}
    second = state(1, 3, {"A1": first["revealed"]["A1"], "C1": {"type": "NONE", "text": "x"}},
                   {"A1": INNOCENT, "C1": INNOCENT, "B1": INNOCENT})
    second["revealed"]["B1"] = {"type": "NONE", "text": "y"}
    assert a.classify(second) == INCONSISTENT


# ---------- auxiliary variables ----------

AUX_CLUES = [
    {"type": "COUNT_LINES", "axis": "row", "k": 1, "where": {"type": "EXACTLY", "k": 2}},
    {"type": "COUNT_LINES", "axis": "col", "k": 2, "where": {"type": "AT_MOST", "k": 1, "count": "innocent"}},
    {"type": "COUNT_LINES", "axis": "row", "k": 2, "where": {"type": "PARITY", "parity": "odd"}},
    {"type": "COUNT_LINES", "axis": "col", "k": 1, "where": {"type": "CONNECTED"}},
    {"type": "AND", "parts": [{"type": "EXACTLY", "k": 7, "region": {"kind": "all"}},
                              {"type": "CONNECTED", "count": "innocent", "region": {"kind": "row", "row": 1}}]},
]


@pytest.mark.parametrize("seed", range(20))
def test_classify_with_auxiliary_variables_matches_brute_force(seed):
    """4x4 boards: COUNT_LINES (Tseitin aux) and EXACTLY 7 of 16 (sequential counter aux)."""
    from encoder import evaluate_clue
    rng = random.Random(seed)
    cells = names(4, 4)
    while True:
        solution = {c: rng.random() < 0.45 for c in cells}
        true_clues = [c for c in AUX_CLUES if evaluate_clue(c, solution, 4, 4)]
        if len(true_clues) >= 2:
            break
    holders = rng.sample(cells, len(true_clues) + rng.randint(0, 3))
    revealed = {h: clue for h, clue in zip(holders, true_clues)}
    for h in holders[len(true_clues):]:
        revealed[h] = random_true_clue(rng, 4, 4, solution, STRONG_TYPES)
    st = state(4, 4, revealed, {h: CRIMINAL if solution[h] else INNOCENT for h in holders})
    expected = brute_force_classify(st)
    for optimized in (True, False):
        assert LogicAgent(optimized=optimized).classify(st) == expected
