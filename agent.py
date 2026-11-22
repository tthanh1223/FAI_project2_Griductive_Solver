"""Deductive Logic Agent: never guesses.

Owner: DPLL & Agent.
Receives only GameEngine.public_state(), never the hidden solution.
Input / output of every function: docs/INTERFACES.md.

For an unsolved cell i:  KB |= C_i  <=>  KB AND (not C_i) is UNSAT.

How classify works
------------------
KB = encoder.build_kb(public_state): CNF of every face-up clue + a unit clause
for every verdict. One SAT call checks the KB itself (UNSAT -> INCONSISTENT)
and gives a model M. A cell can only be forced to the value it has in M, so
for each unsolved cell x (row-major) one query is enough:
  KB AND (x != M[x])  UNSAT -> x is forced to M[x]
                      SAT   -> x is UNKNOWN, and the new model is remembered.
Every model found is a real solution of the KB, so a cell that already has
both values in remembered models is UNKNOWN without any query.

Two more savings, both keeping the answer exactly the same:
- A literal proved in this call is entailed by the KB, so it is added as a
  unit clause to the next queries: the models do not change, but DPLL gets
  it for free by propagation instead of searching for it again.
- The KB only grows during a game (cards get flipped, verdicts get added). So
  if the new state extends the last one classified, a cell forced then is
  still forced now, with the same value: it is copied without a query, and
  its literal is a unit clause from the start. Otherwise (GUI restart, a test
  calling classify on any state) everything is computed from scratch.
Together: at most 1 + (unsolved cells) SAT calls per classify instead of
1 + 2 * (unsolved cells). LogicAgent(optimized=False) runs the plain version
(two queries per cell, nothing reused), as the baseline for experiments.

Auxiliary variables (encoder, CLUES.md 4.4) are never asked about: only
primary variables 1..rows*cols decide cells.

The agent may be called several times on the same state (solve -> classify,
then engine.submit -> classify again, GUI hint -> submit). The last result is
kept, so a repeat costs no SAT call and adds nothing to stats.

stats (cumulative until reset_stats): sat_calls, decisions, propagations and
backtracks summed over every dpll_solve call; time = seconds spent by the
agent, i.e. building the KB (encoder) + every dpll_solve call.
"""
import copy
import json
import time

from dpll import dpll_solve
from encoder import VarMap, build_kb, encode_clue
from model import CRIMINAL, INNOCENT

UNKNOWN = "UNKNOWN"
INCONSISTENT = "INCONSISTENT"

SOLVED = "SOLVED"
STUCK = "STUCK"


class LogicAgent:
    def __init__(self, optimized: bool = True):
        """optimized=False: always 2 queries per unsolved cell, nothing reused (baseline)."""
        self.optimized = optimized
        self.reset_stats()

    def reset_stats(self) -> None:
        """Cumulative counters over every SAT call made by this agent.

        Also forgets the last classified state, so a new measurement starts
        cold and counts all of its own work.
        """
        self.stats = {"sat_calls": 0, "decisions": 0, "propagations": 0,
                      "backtracks": 0, "time": 0.0}
        self._last_key = None          # _state_key of the last classified state
        self._last_result = None       # its classify result
        self._last_state = None        # (revealed, verdicts) of the last consistent state
        self._last_forced = {}         # forced cells of that state: {cell: verdict}

    # ---------- contract ----------

    def classify(self, public_state: dict) -> dict[str, str] | str:
        """{cell: CRIMINAL | INNOCENT | UNKNOWN} for every cell not in verdicts
        (row-major order), or INCONSISTENT if the KB itself is UNSAT."""
        key = _state_key(public_state, self.optimized)
        if key != self._last_key:
            self._last_result = self._classify(public_state)
            self._last_key = key
        result = self._last_result
        return dict(result) if isinstance(result, dict) else result

    def next_move(self, public_state: dict) -> dict | None:
        """{"cell", "verdict"} of the first forced cell in row-major order, or None."""
        forced = self._first_forced(public_state)
        return None if forced is None else {"cell": forced[0], "verdict": forced[1]}

    def hint(self, public_state: dict) -> dict | None:
        """{"cell", "verdict", "because": [cells whose revealed clue is needed]}, or None.

        cell / verdict = next_move. because = a set of face-up clues that, with
        the verdicts, forces the cell, and from which no clue can be removed
        (removing any one makes the cell UNKNOWN). Row-major order.
        1. If one clue alone forces the cell, the hint is that clue (the first
           such clue in row-major order): the simplest explanation.
        2. Otherwise start from every face-up clue and drop each one, in
           row-major order, if the cell stays forced without it.
        Verdict unit clauses always stay in the KB: the player knows them.
        """
        forced = self._first_forced(public_state)
        if forced is None:
            return None
        cell, verdict = forced

        start = time.perf_counter()
        rows, cols = public_state["rows"], public_state["cols"]
        vm = VarMap(rows, cols)
        order = {vm.cell(v): v for v in range(1, rows * cols + 1)}
        units = [[vm.var(c) if s == CRIMINAL else -vm.var(c)]
                 for c, s in public_state["verdicts"].items()]
        groups = {c: encode_clue(clue, vm)
                  for c, clue in sorted(public_state["revealed"].items(),
                                        key=lambda item: order[item[0]])}
        n_vars = vm.next_aux - 1
        self.stats["time"] += time.perf_counter() - start
        x = vm.var(cell)
        wrong = -x if verdict == CRIMINAL else x     # the value the clues must rule out

        def forces(cells):
            clauses = [clause for c in cells for clause in groups[c]]
            sat, _, _ = self._sat(clauses + units, n_vars, [wrong])
            return not sat

        kept = [c for c, cnf in groups.items() if cnf]   # an empty CNF (NONE) is never needed
        for c in kept:
            if forces([c]):
                return {"cell": cell, "verdict": verdict, "because": [c]}
        for c in list(kept):
            if forces([k for k in kept if k != c]):
                kept.remove(c)                        # still forced without clue c
        return {"cell": cell, "verdict": verdict, "because": kept}

    def solve(self, engine) -> dict:
        """Deduction loop: classify, submit the first forced cell, repeat.

        Returns {"status": SOLVED | STUCK | INCONSISTENT, "steps": [...],
                 "kb_stats": {...}, "stats": {...}}; see docs/INTERFACES.md.
        SOLVED: every cell has a verdict. STUCK: no cell is forced (or the engine
        rejected a forced verdict, which only an engine / encoder bug can cause).
        INCONSISTENT: the face-up clues contradict each other.
        A step's sat_calls are the SAT calls made by classify in that step. The
        last classify of a STUCK / INCONSISTENT game belongs to no step, so then
        stats["sat_calls"] is larger than the sum over the steps.
        Use the engine's own agent (engine.agent.solve(engine)): engine.submit
        then reuses this step's classify instead of computing it again.
        """
        steps = []
        while True:
            state = engine.public_state()
            total = state["rows"] * state["cols"]
            if len(state["verdicts"]) == total:
                status = SOLVED
                break
            calls_before = self.stats["sat_calls"]
            result = self.classify(state)
            if result == INCONSISTENT:
                status = INCONSISTENT
                break
            forced = _first_forced_of(result)
            if forced is None:
                status = STUCK
                break
            cell, verdict = forced
            sat_calls = self.stats["sat_calls"] - calls_before
            outcome = engine.submit(cell, verdict)
            after = engine.public_state()
            steps.append({
                "step": len(steps) + 1,
                "active_clues": _row_major(state["revealed"], state),
                "sat_calls": sat_calls,
                "cell": cell,
                "verdict": verdict,
                "result": outcome,
                "revealed_clue": after["revealed"].get(cell),
            })
            if cell not in after["verdicts"]:
                status = STUCK                        # engine disagreed with a proof
                break

        _, _, kb_stats = build_kb(engine.public_state())
        return {"status": status, "steps": steps, "kb_stats": kb_stats,
                "stats": dict(self.stats)}

    # ---------- helpers ----------

    def _classify(self, public_state: dict) -> dict[str, str] | str:
        start = time.perf_counter()
        clauses, vm, _ = build_kb(public_state)
        self.stats["time"] += time.perf_counter() - start
        n_vars = vm.next_aux - 1
        verdicts = public_state["verdicts"]
        primary = public_state["rows"] * public_state["cols"]
        cells = [(v, vm.cell(v)) for v in range(1, primary + 1)]
        unsolved = [(v, c) for v, c in cells if c not in verdicts]

        if not self.optimized:
            sat, _, _ = self._sat(clauses, n_vars)
            if not sat:
                return INCONSISTENT
            result = {}
            for v, cell in unsolved:
                can_criminal, _, _ = self._sat(clauses, n_vars, [v])
                can_innocent, _, _ = self._sat(clauses, n_vars, [-v])
                if can_criminal and can_innocent:
                    result[cell] = UNKNOWN
                else:
                    result[cell] = CRIMINAL if can_criminal else INNOCENT
            return result

        # Cells forced in the last state stay forced if this state extends it.
        known = {}
        if self._extends_last(public_state):
            known = {c: s for c, s in self._last_forced.items() if c not in verdicts}
        proved = [vm.var(c) if s == CRIMINAL else -vm.var(c) for c, s in known.items()]

        sat, model, _ = self._sat(clauses, n_vars, proved)
        if not sat:
            return INCONSISTENT
        # seen[v] = set of values v takes in the models found so far
        seen = {v: {model[v]} for v, _ in unsolved}
        result = {}
        for v, cell in unsolved:
            if cell in known:
                result[cell] = known[cell]
                continue
            if len(seen[v]) == 2:
                result[cell] = UNKNOWN                # two real solutions disagree on v
                continue
            value = next(iter(seen[v]))
            other_sat, other, _ = self._sat(clauses, n_vars, proved + [-v if value else v])
            if other_sat:
                for u, _ in unsolved:
                    seen[u].add(other[u])
                result[cell] = UNKNOWN
            else:
                result[cell] = CRIMINAL if value else INNOCENT
                proved.append(v if value else -v)     # entailed: a free unit from now on

        self._last_state = (copy.deepcopy(public_state["revealed"]), dict(verdicts),
                            public_state["rows"], public_state["cols"])
        self._last_forced = {c: s for c, s in result.items() if s != UNKNOWN}
        return result

    def _extends_last(self, public_state: dict) -> bool:
        """Every clue and verdict of the last consistent state is still here, unchanged."""
        if self._last_state is None:
            return False
        revealed, verdicts, rows, cols = self._last_state
        if (rows, cols) != (public_state["rows"], public_state["cols"]):
            return False
        new_revealed, new_verdicts = public_state["revealed"], public_state["verdicts"]
        return (all(c in new_revealed and new_revealed[c] == clue for c, clue in revealed.items())
                and all(new_verdicts.get(c) == s for c, s in verdicts.items()))

    def _first_forced(self, public_state: dict):
        result = self.classify(public_state)
        return None if result == INCONSISTENT else _first_forced_of(result)

    def _sat(self, clauses, n_vars, assumptions=None):
        """dpll_solve + add its stats to self.stats."""
        sat, model, stats = dpll_solve(clauses, n_vars, assumptions)
        self.stats["sat_calls"] += 1
        for key in ("decisions", "propagations", "backtracks", "time"):
            self.stats[key] += stats[key]
        return sat, model, stats


def _first_forced_of(result: dict[str, str]):
    """(cell, verdict) of the first forced cell; result is already row-major."""
    for cell, verdict in result.items():
        if verdict != UNKNOWN:
            return cell, verdict
    return None


def _row_major(cells, public_state) -> list[str]:
    order = {c["cell"]: i for i, c in enumerate(public_state["cells"])}
    return sorted(cells, key=order.__getitem__)


def _state_key(public_state: dict, optimized: bool) -> str:
    """Everything classify depends on, as one comparable string."""
    return json.dumps([optimized, public_state["rows"], public_state["cols"],
                       public_state["revealed"], public_state["verdicts"]], sort_keys=True)


def check_unique(puzzle) -> bool:
    """With ALL clues (face-down ones too): exactly one model?
    Find a model, block it with one clause, solve again: UNSAT => unique.

    The statuses of the cards face-up at the start are known to the player, so
    they are unit clauses (CLUES.md 7.1: choose `revealed` so that this is True).
    Only primary variables count: two models that differ only in auxiliary
    variables are the same grid. The stored statuses of face-down cards are
    not compared with the model (the engine checks verdicts against them).
    """
    vm = VarMap(puzzle.rows, puzzle.cols)
    clauses = []
    for cell in puzzle.cells:
        clauses.extend(encode_clue(cell.clue, vm))
    for cell in puzzle.cells:
        if cell.cell in puzzle.revealed:
            x = vm.var(cell.cell)
            clauses.append([x if cell.status == CRIMINAL else -x])
    n_vars = vm.next_aux - 1

    sat, model, _ = dpll_solve(clauses, n_vars)
    if not sat:
        return False
    primary = puzzle.rows * puzzle.cols
    block = [-v if model[v] else v for v in range(1, primary + 1)]
    sat_again, _, _ = dpll_solve(clauses + [block], n_vars)
    return not sat_again
