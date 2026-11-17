"""Deductive Logic Agent: never guesses.

Owner: DPLL & Agent.
Receives only GameEngine.public_state(), never the hidden solution.

For an unsolved cell i:  KB |= C_i  <=>  KB AND (not C_i) is UNSAT.
"""

CRIMINAL = "CRIMINAL"
INNOCENT = "INNOCENT"
UNKNOWN = "UNKNOWN"
INCONSISTENT = "INCONSISTENT"


class LogicAgent:
    def classify(self, public_state: dict) -> dict[str, str] | str:
        """{cell: CRIMINAL | INNOCENT | UNKNOWN} for every unsolved cell,
        or INCONSISTENT if the KB itself is UNSAT."""
        raise NotImplementedError

    def solve(self, engine) -> list[dict]:
        """Deduction loop until solved or stuck; forced cells are taken in row-major order.

        Returns the trace, one dict per step:
        {"step", "active_clues", "sat_calls", "cell", "verdict", "revealed_clue"}.
        """
        raise NotImplementedError

    def hint(self, public_state: dict):
        """(cell, verdict, [cells whose clues are needed]) for the next forced cell, or None."""
        raise NotImplementedError


def check_unique(puzzle) -> bool:
    """With ALL clues (face-down ones too): exactly one model?
    Find a model, block it with one clause, solve again: UNSAT => unique."""
    raise NotImplementedError
