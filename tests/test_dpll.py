"""Tests for dpll.dpll_solve, beyond the contract test in test_contracts.py.

- edge cases: empty formula, empty clause, duplicates, tautologies, bad input
- exact stats on tiny formulas, so the meaning of each counter is pinned down
- the variable-choice rule and the restarts
- randomized comparison against brute force: SAT / UNSAT must agree, every
  returned model must satisfy the formula, entailment answers must be right
"""
import copy
import itertools
import random
import sys

import pytest

import dpll
from dpll import dpll_solve


# ---------- helpers ----------

def all_models(clauses, n_vars):
    """Every satisfying assignment, by brute force. Only for small n_vars."""
    for bits in itertools.product([False, True], repeat=n_vars):
        model = dict(zip(range(1, n_vars + 1), bits))
        if satisfies(model, clauses):
            yield model


def satisfies(model, clauses):
    return all(any(model[abs(lit)] == (lit > 0) for lit in c) for c in clauses)


def counters(stats):
    """Stats without the time, for exact comparisons."""
    return {k: stats[k] for k in ("decisions", "propagations", "backtracks")}


def random_cnf(rng, n_vars, n_clauses, max_len=4):
    """Random clauses; may contain duplicate literals and tautologies on purpose."""
    return [[rng.choice([1, -1]) * rng.randint(1, n_vars) for _ in range(rng.randint(1, max_len))]
            for _ in range(n_clauses)]


def pigeonhole(pigeons, holes):
    """Pigeon i is in hole j <=> variable i * holes + j + 1. UNSAT iff pigeons > holes."""
    var = lambda i, j: i * holes + j + 1
    clauses = [[var(i, j) for j in range(holes)] for i in range(pigeons)]
    clauses += [[-var(i, j), -var(k, j)]
                for j in range(holes) for i, k in itertools.combinations(range(pigeons), 2)]
    return clauses, pigeons * holes


def one_empty_column_5x5():
    """KB shaped like the encoder's output for 'Exactly one column has no criminals'
    (COUNT_LINES, CLUES.md 4.4) on a 5x5 grid, plus 'C3 is a criminal'.
    Cells are variables 1..25 (row-major); 26..30 say 'column c has no criminal'.
    Truth-table rows only propagate once a column is almost full, and the
    row-major order fills columns last: without restarts, finding a model took
    270,883 decisions (4.2 s)."""
    clauses = []
    for c in range(5):
        column, r_c = [r * 5 + c + 1 for r in range(5)], 26 + c
        for bits in itertools.product([False, True], repeat=5):
            clauses.append([-x if b else x for x, b in zip(column, bits)]
                           + ([r_c] if not any(bits) else [-r_c]))
    clauses.append([26, 27, 28, 29, 30])
    clauses += [[-a, -b] for a, b in itertools.combinations(range(26, 31), 2)]
    clauses.append([13])
    return clauses, 30


# ---------- examples from the spec ----------

def test_project_example():
    """Project PDF section 3.4: KB = (A or B) and (not A or B). KB |= B, A is unknown."""
    kb = [[1, 2], [-1, 2]]
    assert dpll_solve(kb, 2, [-2])[:2] == (False, None)     # KB and not B: UNSAT
    assert dpll_solve(kb, 2, [1])[0] is True                # A = True possible
    assert dpll_solve(kb, 2, [-1])[0] is True               # A = False possible


def test_return_shape():
    sat, model, stats = dpll_solve([[1, -3]], 3)
    assert sat is True and set(model) == {1, 2, 3}
    assert all(type(b) is bool for b in model.values())
    assert set(stats) == {"decisions", "propagations", "backtracks", "time"}
    assert isinstance(stats["time"], float) and stats["time"] >= 0
    assert dpll_solve([[1], [-1]], 1)[:2] == (False, None)


def test_inputs_not_modified():
    clauses = [[1, 2, 2], [-1, 3], [3, -3], [-2]]
    assumptions = [-3]
    before = copy.deepcopy((clauses, assumptions))
    dpll_solve(clauses, 3, assumptions)
    dpll_solve(clauses, 3)
    assert (clauses, assumptions) == before


# ---------- edge cases ----------

def test_empty_formula_is_sat():
    assert dpll_solve([], 0)[:2] == (True, {})
    assert dpll_solve([], 3)[:2] == (True, {1: False, 2: False, 3: False})


def test_empty_clause_is_unsat():
    assert dpll_solve([[]], 0)[:2] == (False, None)
    assert dpll_solve([[1, 2], []], 2)[0] is False


def test_contradicting_units_and_assumptions():
    assert dpll_solve([[1], [-1]], 1)[0] is False
    assert dpll_solve([], 1, [1, -1])[0] is False
    assert dpll_solve([[1]], 1, [-1])[0] is False
    assert dpll_solve([[1]], 1, [1, 1])[:2] == (True, {1: True})


def test_duplicate_literals_and_tautologies():
    assert dpll_solve([[2, 2]], 2)[:2] == (True, {1: False, 2: True})   # [2, 2] is the unit [2]
    assert dpll_solve([[2, 2], [-2]], 2)[0] is False
    assert dpll_solve([[1, -1]], 1)[:2] == (True, {1: False})          # always true: no constraint


def test_unconstrained_variables_are_false():
    sat, model, stats = dpll_solve([[3]], 5)
    assert sat and model == {1: False, 2: False, 3: True, 4: False, 5: False}
    assert stats["decisions"] == 0


@pytest.mark.parametrize("clauses, n_vars, assumptions", [
    ([[0]], 1, None),
    ([[2]], 1, None),
    ([[-2]], 1, None),
    ([[1]], 1, [2]),
    ([[1]], 1, [0]),
    ([[1]], -1, None),
    ([[1]], 1.0, None),
    ([[True]], 1, None),
    ([[1, 1.0]], 1, None),
    ([[1.0, 1]], 1, None),
    ([[1]], 1, [[1]]),          # a clause passed where a literal is expected
])
def test_bad_input_raises(clauses, n_vars, assumptions):
    with pytest.raises(ValueError):
        dpll_solve(clauses, n_vars, assumptions)


def test_recursion_limit_is_restored():
    old = sys.getrecursionlimit()
    dpll_solve([[1, 2], [-1, 2], [1, -2]], 2000)
    assert sys.getrecursionlimit() == old


# ---------- stats: what each counter means ----------

def test_stats_only_propagation():
    """[1], 1 -> 2, 2 -> 3: three forced literals, no branching."""
    sat, model, stats = dpll_solve([[1], [-1, 2], [-2, 3]], 3)
    assert sat and model == {1: True, 2: True, 3: True}
    assert counters(stats) == {"decisions": 0, "propagations": 3, "backtracks": 0}


def test_stats_one_backtrack():
    """1 -> 2 and 1 -> not 2: the branch 1 = True fails, 1 = False works."""
    sat, model, stats = dpll_solve([[-1, 2], [-1, -2]], 2)
    assert sat and model == {1: False, 2: False}
    assert counters(stats) == {"decisions": 1, "propagations": 1, "backtracks": 1}


def test_stats_both_branches_fail():
    """All four clauses over variables 1, 2: every assignment is blocked."""
    sat, _, stats = dpll_solve([[1, 2], [1, -2], [-1, 2], [-1, -2]], 2)
    assert not sat
    assert counters(stats) == {"decisions": 1, "propagations": 2, "backtracks": 2}


def test_stats_failure_below_counts_as_backtrack():
    """Both values of 1 fail without a conflict of their own: the split on 2 below
    them fails. Those two branches still count as backtracks (6 = 2 * 3 decisions)."""
    sat, _, stats = dpll_solve([[1, 2, 3], [2, 3], [2, -3], [-2, 3], [-2, -3]], 3)
    assert not sat
    assert counters(stats) == {"decisions": 3, "propagations": 4, "backtracks": 6}


# ---------- variable choice and restarts ----------

def test_skips_variables_whose_clauses_are_satisfied():
    """The contradiction only involves 29 and 30. Branching on 1..28 first would
    repeat the failing search below each of them (about 2^28 times)."""
    clauses = [[29, 30], [29, -30], [-29, 30], [-29, -30], [1, 29, -29]]
    sat, _, stats = dpll_solve(clauses, 30)
    assert not sat and stats["decisions"] == 1


def test_restart_escapes_a_bad_order():
    clauses, n = one_empty_column_5x5()
    sat, model, stats = dpll_solve(clauses, n)
    assert sat and satisfies(model, clauses) and model[13]
    empty = [c for c in range(5) if not any(model[r * 5 + c + 1] for r in range(5))]
    assert len(empty) == 1
    assert stats["decisions"] < 1000                 # was 270,883 without restarts


def test_restarts_do_not_change_answers(monkeypatch):
    """Same SAT / UNSAT answer with and without restarts, on instances that restart."""
    rng = random.Random(5)
    restarted = 0
    for _ in range(25):
        n = rng.randint(30, 50)
        clauses = [[rng.choice([1, -1]) * v for v in rng.sample(range(1, n + 1), 3)]
                   for _ in range(int(4.26 * n))]
        sat, model, stats = dpll_solve(clauses, n)
        with monkeypatch.context() as m:
            m.setattr(dpll, "_FIRST_RESTART_BUDGET", 10 ** 9)     # no restart
            assert dpll_solve(clauses, n)[0] == sat
        if sat:
            assert satisfies(model, clauses)
        restarted += stats["backtracks"] >= 16
    assert restarted >= 10


def test_assumptions_behave_like_unit_clauses():
    rng = random.Random(7)
    for _ in range(200):
        n = rng.randint(1, 7)
        clauses = random_cnf(rng, n, rng.randint(0, 20))
        assumptions = [rng.choice([1, -1]) * rng.randint(1, n) for _ in range(rng.randint(0, 3))]
        a = dpll_solve(clauses, n, assumptions)
        b = dpll_solve(clauses + [[lit] for lit in assumptions], n)
        assert a[:2] == b[:2] and counters(a[2]) == counters(b[2])


def test_deterministic():
    rng = random.Random(3)
    clauses = random_cnf(rng, 12, 50, max_len=3)
    first = dpll_solve(clauses, 12)
    for _ in range(3):
        again = dpll_solve(clauses, 12)
        assert again[:2] == first[:2] and counters(again[2]) == counters(first[2])


# ---------- correctness against brute force ----------

@pytest.mark.parametrize("seed", range(4))
def test_random_against_brute_force(seed):
    rng = random.Random(seed)
    outcomes = set()
    for _ in range(120):
        n = rng.randint(1, 8)
        clauses = random_cnf(rng, n, rng.randint(0, 4 * n))
        sat, model, _ = dpll_solve(clauses, n)
        assert sat == any(True for _ in all_models(clauses, n)), clauses
        if sat:
            assert set(model) == set(range(1, n + 1)) and satisfies(model, clauses)
        else:
            assert model is None
        outcomes.add(sat)
    assert outcomes == {True, False}                 # both cases were exercised


def test_entailment_queries_match_brute_force():
    """The agent's use: KB |= lit  <=>  KB and not lit is UNSAT."""
    rng = random.Random(11)
    checked = 0
    for _ in range(150):
        n = rng.randint(2, 7)
        kb = random_cnf(rng, n, rng.randint(1, 2 * n), max_len=3)
        models = list(all_models(kb, n))
        if not models:
            continue
        for v in range(1, n + 1):
            for lit in (v, -v):
                entailed = not dpll_solve(kb, n, [-lit])[0]
                assert entailed == all(m[v] == (lit > 0) for m in models), (kb, lit)
                checked += 1
    assert checked > 500


def test_pigeonhole():
    clauses, n = pigeonhole(5, 4)
    sat, model, stats = dpll_solve(clauses, n)
    assert (sat, model) == (False, None) and stats["backtracks"] > 0
    clauses, n = pigeonhole(4, 4)
    sat, model, _ = dpll_solve(clauses, n)
    assert sat and satisfies(model, clauses)


def test_deep_search_does_not_hit_recursion_limit():
    """The search recurses once per decision. 600 independent clauses need 600
    nested decisions, more than the limit set below: dpll_solve must raise it."""
    clauses = [[v, v + 1] for v in range(1, 1200, 2)]
    old = sys.getrecursionlimit()
    sys.setrecursionlimit(300)
    try:
        sat, model, stats = dpll_solve(clauses, 1200)
        assert sys.getrecursionlimit() == 300        # put back after the call
    finally:
        sys.setrecursionlimit(old)
    assert sat and satisfies(model, clauses) and stats["decisions"] == 600
