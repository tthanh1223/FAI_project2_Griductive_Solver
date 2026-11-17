"""Deductive Logic Agent: never guesses.

Owner: DPLL & Agent.
Receives only GameEngine.public_state(), never the hidden solution.
Input / output of every function: docs/INTERFACES.md.

For an unsolved cell i:  KB |= C_i  <=>  KB AND (not C_i) is UNSAT.
"""

UNKNOWN = "UNKNOWN"
INCONSISTENT = "INCONSISTENT"

SOLVED = "SOLVED"
STUCK = "STUCK"


class LogicAgent:
    def __init__(self):
        self.reset_stats()

    def reset_stats(self) -> None:
        """Cumulative counters over every SAT call made by this agent."""
        self.stats = {"sat_calls": 0, "decisions": 0, "propagations": 0,
                      "backtracks": 0, "time": 0.0}

    def classify(self, public_state: dict) -> dict[str, str] | str:
        """{cell: CRIMINAL | INNOCENT | UNKNOWN} for every cell not in verdicts
        (row-major order), or INCONSISTENT if the KB itself is UNSAT."""
        raise NotImplementedError

    def next_move(self, public_state: dict) -> dict | None:
        """{"cell", "verdict"} of the first forced cell in row-major order, or None."""
        raise NotImplementedError

    def hint(self, public_state: dict) -> dict | None:
        """{"cell", "verdict", "because": [cells whose revealed clue is needed]}, or None."""
        raise NotImplementedError

    def solve(self, engine) -> dict:
        """Deduction loop: classify, submit the first forced cell, repeat.

        Returns {"status": SOLVED | STUCK | INCONSISTENT, "steps": [...],
                 "kb_stats": {...}, "stats": {...}}; see docs/INTERFACES.md.
        """
        raise NotImplementedError


def check_unique(puzzle) -> bool:
    """With ALL clues (face-down ones too): exactly one model?
    Find a model, block it with one clause, solve again: UNSAT => unique."""
    raise NotImplementedError
