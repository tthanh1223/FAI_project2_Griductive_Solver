"""DPLL SAT solver, written by hand (no SAT library).

Owner: DPLL & Agent.

Required: unit propagation, conflict detection, deterministic variable choice,
recursive branching + backtracking, SAT with a complete model or UNSAT, and stats.
Input / output of every function: docs/INTERFACES.md.

How the search works
--------------------
Every variable is True, False or unassigned. The trail lists the assigned
literals in the order they were set, so backtracking = popping the trail.

1. Setup. Copy the clauses (the caller's lists are never modified), drop
   repeated literals and always-true clauses such as [3, -3], and add every
   assumption as a unit clause. An empty clause means UNSAT at once. Unit
   clauses are assigned before the search; [x] together with [-x] is UNSAT.
2. Unit propagation. A clause can only become unit or empty when one of its
   literals turns False, so after assigning a literal we visit only the clauses
   that contain its negation (occurrence lists). A clause with no True literal
   and one unassigned literal forces that literal. A clause with no True literal
   and no unassigned literal is a conflict.
3. Branching (recursive). Pick the smallest unassigned variable that still
   occurs in a clause with no True literal. Try one value, propagate, recurse;
   on failure undo and try the other value. If both fail, report failure to the
   caller, which undoes its own branch. If no variable is left to pick, every
   clause is satisfied: SAT. Variables still unassigned then get False.
4. Restarts. A fixed order can spend a very long time in a hopeless part of the
   tree (e.g. a clue about a column while the order fills the grid row by row).
   After 16 backtracks the search starts again from step 3 with the two values
   tried in the opposite order (False first instead of True first), and with
   twice the budget each time (16, 32, 64, ...). Everything stays deterministic.

Why the answer is right
-----------------------
- Propagation only sets literals that every model extending the current
  assignment must contain, so it never loses a model.
- A split tries x = True and x = False, which together cover every extension,
  so UNSAT is returned only when no assignment satisfies the clauses.
- After a successful propagation, a clause with no True literal still has at
  least two unassigned literals (zero would be a conflict, one a unit). So when
  no variable is left to pick, every clause already has a True literal, and
  any values for the remaining variables keep it that way.
- Termination: each recursion level assigns one more variable, so a run is at
  most n_vars levels deep and finite; the budget doubles, so some run is
  eventually allowed to finish.
Not implemented (optional in the assignment): pure-literal elimination, clause learning.

Stats (all work is counted, including work undone by backtracking or a restart):
- decisions:    splits in step 3; a variable tried both ways counts once.
- propagations: literals forced by a unit clause: input units, assumptions and
                units found while propagating. Decision values are not counted.
- backtracks:   values tried for a decision variable that failed and were undone,
                because their own propagation hit a conflict or because both
                branches below them failed. With no restart, an UNSAT answer has
                backtracks == 2 * decisions; UNSAT with 0 decisions means
                propagation alone found the contradiction.
- time:         wall-clock seconds for the whole call, setup included.
"""
import sys
import time

# A run is at most n_vars recursion levels deep. Python stops at 1000 levels by
# default; this many levels are left for the callers (GUI, agent, pytest).
_RECURSION_HEADROOM = 1000

# Backtracks allowed before the first restart; doubled after every restart.
_FIRST_RESTART_BUDGET = 16


def dpll_solve(clauses: list[list[int]], n_vars: int, assumptions: list[int] | None = None):
    """Returns (sat: bool, model: dict[int, bool] | None, stats: dict).

    assumptions: literals added as temporary unit clauses.
    Must not modify `clauses`. On SAT, model assigns every variable 1..n_vars.
    stats = {"decisions", "propagations", "backtracks", "time"}  (time in seconds)
    Raises ValueError if n_vars is not an int >= 0, or a literal is not an int,
    is 0, or has abs(literal) > n_vars.
    """
    start = time.perf_counter()
    solver = _Solver(clauses, n_vars, [] if assumptions is None else assumptions)
    sat = solver.solve()
    model = solver.model() if sat else None
    stats = {"decisions": solver.decisions, "propagations": solver.propagations,
             "backtracks": solver.backtracks, "time": time.perf_counter() - start}
    return sat, model, stats


class _Restart(Exception):
    """Raised inside the search when the current run has used up its backtrack budget."""


class _Solver:
    """State of one dpll_solve call."""

    def __init__(self, clauses, n_vars, assumptions):
        if type(n_vars) is not int or n_vars < 0:
            raise ValueError(f"n_vars must be an int >= 0, got {n_vars!r}")
        self.n_vars = n_vars

        self.clauses: list[list[int]] = []
        for clause in list(clauses) + [[lit] for lit in assumptions]:
            for lit in clause:
                # type(...) is int also rejects True / False and 1.0
                if type(lit) is not int or lit == 0 or abs(lit) > n_vars:
                    raise ValueError(f"bad literal {lit!r} (n_vars = {n_vars})")
            # New list without repeated literals (a dict keeps their order). Needed so
            # that [1, 2, 2] is seen as a unit clause once 1 is False.
            lits = list(dict.fromkeys(clause))
            if len({abs(lit) for lit in lits}) < len(lits):
                continue                    # some variable occurs as x and -x: always true
            self.clauses.append(lits)

        # occ[lit] = indices of the clauses that contain lit
        self.occ: dict[int, list[int]] = {lit: [] for lit in range(-n_vars, n_vars + 1) if lit != 0}
        for i, clause in enumerate(self.clauses):
            for lit in clause:
                self.occ[lit].append(i)

        self.value: list[bool | None] = [None] * (n_vars + 1)   # value[var], index 0 unused
        # n_true[i] = number of True literals in clause i right now (kept exact by
        # _assign / _undo). n_true[i] > 0 means "clause i is satisfied", without a scan.
        self.n_true = [0] * len(self.clauses)
        self.trail: list[int] = []      # assigned literals, in assignment order
        self.head = 0                   # trail[:head] is propagated, trail[head:] still to do
        self.true_first = True          # value tried first at a split; flipped by each restart
        self.budget_end = 0             # restart when self.backtracks reaches this
        self.decisions = self.propagations = self.backtracks = 0

    # ---------- top level ----------

    def solve(self) -> bool:
        """Step 1 (empty and unit clauses), propagation, then the search with restarts."""
        for clause in self.clauses:
            if not clause:
                return False                        # empty clause: nothing satisfies it
            if len(clause) == 1:
                current = self._lit_value(clause[0])
                if current is False:
                    return False                    # both [x] and [-x]
                if current is None:
                    self._assign(clause[0])
                    self.propagations += 1
        if not self._propagate():
            return False

        base = len(self.trail)                      # forced by the input: never undone
        budget = _FIRST_RESTART_BUDGET
        old_limit = sys.getrecursionlimit()
        sys.setrecursionlimit(max(old_limit, self.n_vars + _RECURSION_HEADROOM))
        try:
            while True:
                self.budget_end = self.backtracks + budget
                try:
                    return self._search()
                except _Restart:
                    self._undo(base)                # forget every decision of this run
                    self.true_first = not self.true_first
                    budget *= 2
        finally:
            sys.setrecursionlimit(old_limit)

    def model(self) -> dict[int, bool]:
        """Complete assignment of 1..n_vars; variables still unassigned get False."""
        return {v: self.value[v] is True for v in range(1, self.n_vars + 1)}

    # ---------- search ----------

    def _search(self) -> bool:
        """Step 3: branch on one variable, recurse, backtrack on failure."""
        var = self._choose_var()
        if var is None:
            return True                             # every clause is satisfied
        self.decisions += 1
        # The order is fixed for the whole run, so results are reproducible.
        for lit in ((var, -var) if self.true_first else (-var, var)):
            mark = len(self.trail)                  # the trail is fully propagated here
            self._assign(lit)
            if self._propagate() and self._search():
                return True                         # keep the assignment: it is the model
            self._undo(mark)
            self.backtracks += 1
            if self.backtracks >= self.budget_end:
                raise _Restart
        return False

    def _choose_var(self) -> int | None:
        """Smallest unassigned variable that occurs in a clause with no True literal.

        None means every clause is satisfied. A variable whose clauses are all
        satisfied is skipped: its value cannot change any clause, so both of its
        branches would give the same answer, and every failing search below it
        would be done twice. (Early in the game most cells are in no revealed clue.)
        """
        for v in range(1, self.n_vars + 1):
            if self.value[v] is None and (any(self.n_true[i] == 0 for i in self.occ[v]) or
                                          any(self.n_true[i] == 0 for i in self.occ[-v])):
                return v
        return None

    def _propagate(self) -> bool:
        """Step 2: unit propagation until nothing more is forced. False on conflict."""
        while self.head < len(self.trail):
            lit = self.trail[self.head]
            self.head += 1
            for i in self.occ[-lit]:                # clauses where -lit just became False
                if self.n_true[i]:
                    continue                        # already satisfied
                free = [x for x in self.clauses[i] if self.value[abs(x)] is None]
                if not free:
                    return False                    # conflict: every literal is False
                if len(free) == 1:
                    self._assign(free[0])           # unit: the last literal is forced
                    self.propagations += 1
        return True

    # ---------- assignment ----------

    def _lit_value(self, lit: int) -> bool | None:
        """True / False under the current assignment, None if unassigned."""
        value = self.value[abs(lit)]
        return None if value is None else value == (lit > 0)

    def _assign(self, lit: int) -> None:
        """Make lit True and put it on the trail. The caller ensures its variable is unassigned."""
        self.value[abs(lit)] = lit > 0
        self.trail.append(lit)
        for i in self.occ[lit]:
            self.n_true[i] += 1

    def _undo(self, mark: int) -> None:
        """Unassign trail[mark:], i.e. a decision and everything propagated from it.

        mark was taken when the trail was fully propagated, so head goes back to mark.
        """
        while len(self.trail) > mark:
            lit = self.trail.pop()
            self.value[abs(lit)] = None
            for i in self.occ[lit]:
                self.n_true[i] -= 1
        self.head = mark
