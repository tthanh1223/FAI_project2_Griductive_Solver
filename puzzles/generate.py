"""Puzzle generator: no-guess puzzles with exactly one solution.

Owner: Engine & Puzzle.

Idea: choose the hidden answer first, so every clue written from it is true.
A card gets its clue only when it is flipped, while the LogicAgent plays the
puzzle: for each flipped card several random candidate clues are drawn and the
one forcing the fewest new cells (at least one) is kept, so the deduction chain
is long. If no candidate makes progress the attempt is dropped and another one
starts. The agent only ever sees the public state; the answer is used to write
clues, never to decide a cell. The last flipped card gets a flavour clue.

Every cell is forced at some step, so the puzzle is solvable without guessing
and has exactly one solution; puzzles.validate.puzzle_problems re-checks it.

Deterministic: one random.Random per puzzle, seeded from (seed, size, index).

Usage (from the project root):
    python -m puzzles.generate --rows 3 --cols 3 --count 6 --seed 0
"""
import argparse
import json
import random
import sys
from pathlib import Path

from agent import INCONSISTENT, UNKNOWN, LogicAgent
from encoder import VarMap, encode_clue, evaluate_clue, validate_clue
from engine import GameEngine
from model import CRIMINAL, INNOCENT, Cell, Puzzle, all_cells, region_cells
from puzzles.validate import puzzle_problems

NAMES = ["Abel", "Bea", "Clara", "Derek", "Eliza", "Franz", "Grant", "Hannah", "Ivy", "Jonas",
         "Karl", "Leo", "Mara", "Noah", "Owen", "Priya", "Quilla", "Roy", "Sophia", "Tom",
         "Uma", "Victor", "Wendy", "Xavier", "Yara", "Zane", "Alma", "Boris", "Celia", "Dmitri",
         "Elsa", "Felix", "Greta", "Hector", "Iris", "Jade", "Kira", "Liam", "Mona", "Nina"]
JOBS = ["Astronaut", "Baker", "Clerk", "Cook", "Detective", "Doctor", "Farmer", "Guard",
        "Judge", "Painter", "Pilot", "Singer", "Teacher"]
FLAVOUR = ["I was just here for the coffee.", "Nice weather today, isn't it?",
           "I have nothing to add.", "Has anyone seen my umbrella?"]

CRIMINAL_RATIO = 0.4
CANDIDATES = 8          # candidate clues drawn per flipped card
ROUNDS = 4              # extra draws of CANDIDATES before an attempt is dropped
ATTEMPTS = 200          # attempts per puzzle before giving up

# Clue templates and their weights. FACT is rare: it makes puzzles easy.
TEMPLATES = ["FACT", "PAIR", "COUNT", "COMPARE", "CONNECTED", "PARITY"]
TEMPLATE_WEIGHTS = [5, 16, 50, 11, 10, 8]
REGION_KINDS = ["row", "col", "neighbors", "cells", "above", "below", "left", "right",
                "between", "edges", "corners", "all", "inter"]
REGION_WEIGHTS = [14, 14, 24, 7, 4, 4, 4, 4, 7, 3, 2, 3, 10]
LINE_KINDS = ["row", "col", "above", "below", "left", "right", "between"]


def _status(is_criminal: bool) -> str:
    return CRIMINAL if is_criminal else INNOCENT


# ---------------------------------------------------------------- clues

def _random_region(cell: str, cells: list[str], rows: int, cols: int, rng: random.Random,
                   kinds=REGION_KINDS, weights=REGION_WEIGHTS) -> dict:
    """A random region; may be empty or invalid, callers check the clue."""
    kind = rng.choices(kinds, weights)[0]
    if kind == "row":
        return {"kind": "row", "row": rng.randint(1, rows)}
    if kind == "col":
        return {"kind": "col", "col": chr(ord("A") + rng.randrange(cols))}
    if kind == "neighbors":                      # often "my neighbors"
        return {"kind": "neighbors", "of": cell if rng.random() < 0.4 else rng.choice(cells)}
    if kind == "cells":
        picked = rng.sample(range(len(cells)), rng.randint(2, min(4, len(cells))))
        return {"kind": "cells", "cells": [cells[i] for i in sorted(picked)]}
    if kind in ("above", "below", "left", "right"):
        return {"kind": kind, "of": rng.choice(cells)}
    if kind == "between":
        a = rng.choice(cells)
        line = [x for x in cells if x != a and (x[0] == a[0] or x[1:] == a[1:])]
        return {"kind": "between", "a": a, "b": rng.choice(line)}
    if kind == "inter":
        second = rng.choice([{"kind": "row", "row": rng.randint(1, rows)},
                             {"kind": "col", "col": chr(ord("A") + rng.randrange(cols))},
                             {"kind": "neighbors", "of": rng.choice(cells)}])
        return {"kind": "inter", "regions": [{"kind": "neighbors", "of": rng.choice(cells)}, second]}
    return {"kind": kind}                         # edges, corners, all


def _counted(answer: dict, members: list[str], innocent: bool) -> list[str]:
    return [x for x in members if answer[x] != innocent]


def _draw_clue(answer: dict, cell: str, rows: int, cols: int, rng: random.Random) -> dict:
    """One random clue that is true on `answer` (not yet checked for usefulness)."""
    cells = all_cells(rows, cols)
    template = rng.choices(TEMPLATES, TEMPLATE_WEIGHTS)[0]
    innocent = rng.random() < 0.3
    count = {"count": "innocent"} if innocent else {}

    if template == "FACT":
        who = rng.choice(cells)
        return {"type": "FACT", "who": who, "status": _status(answer[who])}
    if template == "PAIR":
        a, b = rng.sample(cells, 2)
        return {"type": "SAME" if answer[a] == answer[b] else "DIFFERENT", "a": a, "b": b}
    if template == "COMPARE":
        kinds, weights = ["row", "col", "neighbors"], [1, 1, 2]
        r1 = _random_region(cell, cells, rows, cols, rng, kinds, weights)
        r2 = _random_region(cell, cells, rows, cols, rng, kinds, weights)
        n1 = len(_counted(answer, region_cells(r1, rows, cols), innocent))
        n2 = len(_counted(answer, region_cells(r2, rows, cols), innocent))
        op = ">" if n1 > n2 else "<" if n1 < n2 else "="
        return {"type": "COMPARE", "r1": r1, "op": op, "r2": r2, **count}

    region = _random_region(cell, cells, rows, cols, rng,
                            *((LINE_KINDS, [1] * len(LINE_KINDS)) if template == "CONNECTED" else ()))
    members = region_cells(region, rows, cols)
    hits = _counted(answer, members, innocent)
    n = len(hits)
    if template == "PARITY":
        return {"type": "PARITY", "parity": "odd" if n % 2 else "even", "region": region, **count}
    if template == "CONNECTED":
        positions = [members.index(x) for x in hits]
        if n < 2 or positions[-1] - positions[0] + 1 != n:
            return {"type": "NONE", "text": ""}      # not connected: rejected as uninformative
        connected = {"type": "CONNECTED", "region": region, **count}
        if rng.random() < 0.5:                       # "Both criminals in row 2 are connected"
            return {"type": "AND", "parts": [{"type": "EXACTLY", "k": n, "region": region, **count}, connected]}
        return connected
    kind = rng.choices(["EXACTLY", "AT_LEAST", "AT_MOST"], [2, 1, 1])[0]
    k = n - rng.randint(0, 1) if kind == "AT_LEAST" else n + rng.randint(0, 1) if kind == "AT_MOST" else n
    return {"type": kind, "k": k, "region": region, **count}


def is_useful_clue(clue: dict, answer: dict, rows: int, cols: int) -> bool:
    """Valid, true on the answer, and not always true (its CNF is not empty).

    The last test rejects every clue without information: empty regions,
    AT_LEAST 0, AT_MOST |R|, COMPARE of a region with itself, CONNECTED on
    fewer than 3 cells, flavour clues.
    """
    try:
        validate_clue(clue, rows, cols)
    except ValueError:
        return False
    return evaluate_clue(clue, answer, rows, cols) and bool(encode_clue(clue, VarMap(rows, cols)))


def random_clue(answer: dict, cell: str, rows: int, cols: int, rng: random.Random) -> dict:
    """A random useful clue for the card at `cell`, true on `answer`."""
    while True:
        clue = _draw_clue(answer, cell, rows, cols, rng)
        if is_useful_clue(clue, answer, rows, cols):
            return clue


# ---------------------------------------------------------------- generation

def _forced(agent: LogicAgent, state: dict) -> list[str]:
    result = agent.classify(state)
    if result == INCONSISTENT:                       # impossible: every clue is true on the answer
        raise RuntimeError("generator produced an inconsistent knowledge base")
    return [cell for cell, verdict in result.items() if verdict != UNKNOWN]


def _pick_clue(answer, cell, state, agent, rng) -> dict | None:
    """The candidate clue for `cell` that forces the fewest new cells (at least one).

    FACT always forces exactly one cell, so it would win that contest and make
    puzzles easy: it is only taken when no other candidate forces something new.
    If cells are already forced without the new clue, any useful clue keeps the
    game going, so the first candidate is taken when none forces something new.
    None if no candidate in all rounds lets the game go on.
    """
    rows, cols = state["rows"], state["cols"]
    before = set(_forced(agent, state))
    for _ in range(1 + ROUNDS):
        best, best_key = None, None
        candidates = [random_clue(answer, cell, rows, cols, rng) for _ in range(CANDIDATES)]
        for clue in candidates:
            trial = {**state, "revealed": {**state["revealed"], cell: clue}}
            new = len(set(_forced(agent, trial)) - before)
            key = (clue["type"] == "FACT", new)
            if new and (best_key is None or key < best_key):
                best, best_key = clue, key
        if best is not None:
            return best
        if before:
            return candidates[0]
    return None


def _attempt(rows: int, cols: int, rng: random.Random, agent: LogicAgent) -> dict | None:
    """One generation attempt: the puzzle as a JSON-ready dict, or None if it got stuck."""
    cells = all_cells(rows, cols)
    while True:
        answer = {cell: rng.random() < CRIMINAL_RATIO for cell in cells}
        if 0 < sum(answer.values()) < len(cells):
            break
    names = sorted(rng.sample(NAMES, len(cells)), key=str.casefold)
    jobs = [rng.choice(JOBS) for _ in cells]
    start = rng.choice(cells)

    state = {"rows": rows, "cols": cols,
             "cells": [{"cell": c, "name": n, "job": j} for c, n, j in zip(cells, names, jobs)],
             "revealed": {}, "verdicts": {start: _status(answer[start])}}
    current = start
    while len(state["verdicts"]) < len(cells):
        clue = _pick_clue(answer, current, state, agent, rng)
        if clue is None:
            return None
        state["revealed"][current] = clue
        current = _forced(agent, state)[0]           # first forced cell, row-major
        state["verdicts"][current] = _status(answer[current])
    state["revealed"][current] = {"type": "NONE", "text": rng.choice(FLAVOUR)}

    head = {"size": rows} if rows == cols else {"rows": rows, "cols": cols}
    return {**head,
            "cells": [{"cell": c["cell"], "name": c["name"], "job": c["job"],
                       "status": _status(answer[c["cell"]]), "clue": state["revealed"][c["cell"]]}
                      for c in state["cells"]],
            "revealed": [start]}


def _to_puzzle(puzzle_id: str, data: dict) -> Puzzle:
    rows = data.get("rows", data.get("size"))
    cols = data.get("cols", data.get("size"))
    cells = [Cell(c["cell"], c["name"], c["job"], c["status"], c["clue"]) for c in data["cells"]]
    return Puzzle(puzzle_id, rows, cols, cells, list(data["revealed"]))


def difficulty(puzzle: Puzzle) -> dict:
    """{"waves", "sat_calls"}: reveal waves (flip every forced card at once, repeat)
    and SAT calls of a standard LogicAgent.solve. Fewer cells per wave = harder.

    Raises ValueError if the puzzle cannot be solved without guessing.
    """
    engine = GameEngine(puzzle, LogicAgent())
    result = engine.agent.solve(engine)
    if result["status"] != "SOLVED":
        raise ValueError(f"Puzzle {puzzle.id} cannot be solved without guessing ({result['status']})")
    engine.restart()
    waves = 0
    while not engine.is_solved():
        forced = {cell: verdict for cell, verdict in engine.agent.classify(engine.public_state()).items()
                  if verdict != UNKNOWN}
        for cell, verdict in forced.items():
            engine.submit(cell, verdict)
        waves += 1
    return {"waves": waves, "sat_calls": result["stats"]["sat_calls"]}


def puzzle_id(rows: int, cols: int, index: int) -> str:
    """g3_01 for 3x3; g5x4_01 for 5 cols x 4 rows (width x height, as in p4x5_candle)."""
    size = f"{rows}" if rows == cols else f"{cols}x{rows}"
    return f"g{size}_{index:02d}"


def check_size(rows: int, cols: int) -> None:
    """Raises ValueError unless 2 <= rows, 2 <= cols <= 26 and there are enough names."""
    if not (2 <= rows and 2 <= cols <= 26 and rows * cols <= len(NAMES)):
        raise ValueError(f"Unsupported size: {rows} rows x {cols} cols "
                         f"(need rows, cols >= 2, cols <= 26, rows * cols <= {len(NAMES)})")


def generate(rows: int, cols: int, seed: int, index: int) -> dict:
    """Puzzle number `index` for this size and seed, as a JSON-ready dict.

    Same arguments -> same puzzle. Raises ValueError for an unsupported size and
    RuntimeError after ATTEMPTS failed attempts.
    """
    check_size(rows, cols)
    rng = random.Random(f"{seed}:{rows}x{cols}:{index}")
    agent = LogicAgent()
    pid = puzzle_id(rows, cols, index)
    for _ in range(ATTEMPTS):
        data = _attempt(rows, cols, rng, agent)
        if data is None:
            continue
        puzzle = _to_puzzle(pid, data)
        problems = puzzle_problems(puzzle)
        if problems:                                  # cannot happen if the generator is right
            raise RuntimeError(f"generated {pid} is invalid: {problems}")
        return {"id": pid, **data, "difficulty": difficulty(puzzle)}
    raise RuntimeError(f"no puzzle {pid} after {ATTEMPTS} attempts")


def to_json(data: dict) -> str:
    """Stable text: same puzzle -> same bytes on every OS."""
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate no-guess Griductive puzzles.")
    parser.add_argument("--rows", type=int, required=True)
    parser.add_argument("--cols", type=int, required=True)
    parser.add_argument("--count", type=int, default=1)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--start", type=int, default=1, help="index of the first puzzle")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--force", action="store_true", help="overwrite existing files")
    args = parser.parse_args(argv)
    try:
        check_size(args.rows, args.cols)
    except ValueError as e:
        parser.error(str(e))
    if args.count < 1 or args.start < 1:
        parser.error("--count and --start must be at least 1")
    if not args.out.is_dir():
        parser.error(f"--out: not a directory: {args.out}")

    for index in range(args.start, args.start + args.count):
        path = args.out / f"{puzzle_id(args.rows, args.cols, index)}.json"
        if path.exists() and not args.force:
            print(f"skip {path.name}: exists (use --force to overwrite)")
            continue
        data = generate(args.rows, args.cols, args.seed, index)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(to_json(data))
        print(f"wrote {path.name}  difficulty={data['difficulty']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
