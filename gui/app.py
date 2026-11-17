"""Tkinter GUI.

Owner: GUI & Video.
Grid of cards, CRIMINAL / INNOCENT buttons, list of revealed clues with highlight,
Load / Restart / Hint / Auto Solve. Always redraw from engine.public_state();
never read hidden statuses.
Input / output of every function: docs/INTERFACES.md.
"""


def clue_to_text(clue: dict, names: dict[str, str]) -> str:
    """JSON clue -> readable sentence, e.g. "Exactly 1 criminal in row 2"."""
    raise NotImplementedError


def run(puzzle_path: str | None = None) -> None:
    raise NotImplementedError
