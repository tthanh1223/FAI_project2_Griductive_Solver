"""DPLL SAT solver, written by hand (no SAT library).

Owner: DPLL & Agent.

Required: unit propagation, conflict detection, deterministic variable choice
(smallest unassigned variable), recursive branching + backtracking,
SAT with a complete model or UNSAT, and stats.
Input / output of every function: docs/INTERFACES.md.
"""


def dpll_solve(clauses: list[list[int]], n_vars: int, assumptions: list[int] | None = None):
    """Returns (sat: bool, model: dict[int, bool] | None, stats: dict).

    assumptions: literals added as temporary unit clauses.
    Must not modify `clauses`. On SAT, model assigns every variable 1..n_vars.
    stats = {"decisions", "propagations", "backtracks", "time"}  (time in seconds)
    """
    raise NotImplementedError
