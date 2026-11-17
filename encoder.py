"""Clue -> CNF encoder and direct clue evaluator.

Owner: Encoder.

Variables: cell index in row-major order + 1 (A1 = 1, B1 = 2, ...); True = CRIMINAL.
Auxiliary variables start at rows * cols + 1.
CNF: list[list[int]] (DIMACS style, negative literal = negation).
Input / output of every function: docs/INTERFACES.md.
"""


class VarMap:
    """Deterministic cell <-> variable mapping plus a counter for auxiliary variables."""

    def __init__(self, rows: int, cols: int):
        self.rows, self.cols = rows, cols
        self.next_aux = rows * cols + 1

    def var(self, cell: str) -> int:
        raise NotImplementedError

    def cell(self, var: int) -> str:
        raise NotImplementedError

    def new_aux(self) -> int:
        v = self.next_aux
        self.next_aux += 1
        return v


def validate_clue(clue: dict, rows: int, cols: int) -> None:
    """Raise ValueError on unknown type, unknown cell, or k outside [0, |R|]."""
    raise NotImplementedError


def encode_clue(clue: dict, vm: VarMap) -> list[list[int]]:
    """CNF of one clue (6 core types + extensions)."""
    raise NotImplementedError


def evaluate_clue(clue: dict, assignment: dict[str, bool], rows: int, cols: int) -> bool:
    """Is the clue true under a complete assignment? Must NOT call the CNF encoder."""
    raise NotImplementedError


def build_kb(public_state: dict) -> tuple[list[list[int]], VarMap, dict]:
    """KB_t = CNF(revealed clues) + unit clauses for proved verdicts.

    Returns (clauses, varmap, stats), stats = {"primary", "aux", "clauses"}.
    """
    raise NotImplementedError
