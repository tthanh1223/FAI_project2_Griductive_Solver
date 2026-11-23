"""Puzzle validity check, shared by the tests, the puzzle generator and hand-copied puzzles.

Owner: Engine & Puzzle.

A puzzle is valid when:
  1. GameEngine accepts it: the structure is right, every clue passes
     encoder.validate_clue and every clue is true on the hidden solution;
  2. check_unique: all clues together allow exactly one grid;
  3. the agent solves it from the face-up cards without guessing (unique is not
     enough: clues are revealed one at a time, so the agent can still get stuck);
  4. names increase alphabetically in row-major order (game rules, section 2.1).

Usage (from the project root):  python -m puzzles.validate puzzles/*.json
"""
import sys

from agent import LogicAgent, check_unique
from engine import GameEngine
from model import Puzzle, load_puzzle


def puzzle_problems(puzzle: Puzzle) -> list[str]:
    """Every reason why `puzzle` is not valid; [] means valid. `puzzle` is not modified."""
    try:
        engine = GameEngine(puzzle, LogicAgent())
    except ValueError as e:
        return [f"rejected by GameEngine: {e}"]

    problems = []
    if not check_unique(puzzle):
        problems.append("all clues together allow more than one solution")
    result = engine.agent.solve(engine)
    if result["status"] != "SOLVED":
        decided = len(engine.public_state()["verdicts"])
        problems.append(f"agent is {result['status']} after {decided}/{puzzle.rows * puzzle.cols} cells: "
                        "it cannot finish without guessing")
    names = [c.name for c in sorted(puzzle.cells, key=lambda c: (int(c.cell[1:]), c.cell[0]))]
    keys = [name.casefold() for name in names]
    if any(a >= b for a, b in zip(keys, keys[1:])):
        problems.append(f"names are not strictly alphabetical in row-major order: {names}")
    return problems


def main(paths: list[str]) -> int:
    """Check each file and print the problems; exit code 1 if any file is invalid."""
    if not paths:
        print("usage: python -m puzzles.validate FILE.json [FILE.json ...]")
        return 2
    invalid = 0
    for path in paths:
        try:
            problems = puzzle_problems(load_puzzle(path))
        except (OSError, ValueError) as e:
            problems = [str(e)]
        invalid += bool(problems)
        print(f"{'OK     ' if not problems else 'INVALID'} {path}")
        for problem in problems:
            print(f"        - {problem}")
    return 1 if invalid else 0


if __name__ == "__main__":
    # A redirected stdout uses the Windows code page (e.g. cp1252), which cannot encode
    # every character of a path such as "TỐT NGHIỆP": escape those instead of crashing.
    sys.stdout.reconfigure(errors="backslashreplace")
    sys.exit(main(sys.argv[1:]))
