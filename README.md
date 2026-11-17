# Griductive Solver

CSC14003 – Introduction to Artificial Intelligence, Project 2.
A no-guess solver for the Griductive grid-deduction game: clues → CNF → DPLL SAT solver → deductive logic agent, with a Tkinter GUI.

## Run

```bash
pip install -r requirements.txt
python main.py puzzles/p3_01.json     # GUI
python experiments/run.py             # experiments → experiments/results/
python -m pytest                      # tests
```

Python 3.10+. Tkinter ships with Python.

## Layout

| File | What | Owner |
|---|---|---|
| `model.py` | Puzzle / Cell, JSON loading, regions | Engine & Puzzle |
| `engine.py` | GameEngine: hidden solution, verdict check, card flip | Engine & Puzzle |
| `encoder.py` | Clue → CNF, direct clue evaluator, KB builder | Encoder |
| `dpll.py` | DPLL SAT solver + stats | DPLL & Agent |
| `agent.py` | LogicAgent: classify, deduction loop, trace, hint, uniqueness | DPLL & Agent |
| `gui/app.py` | Tkinter GUI | GUI & Video |
| `experiments/run.py` | Benchmark over all puzzles | Lead |
| `puzzles/*.json` | Puzzle set (+ generator) | Engine & Puzzle |
| `tests/` | pytest | everyone |

**Rule:** only `GameEngine` reads hidden statuses and face-down clues. Agent, Hint and GUI use `engine.public_state()` only.

## Puzzle format

```json
{
  "id": "p3_01",
  "size": 3,
  "cells": [
    {"cell": "A1", "name": "Alice", "job": "Cook", "status": "INNOCENT",
     "clue": {"type": "EXACTLY", "k": 1, "region": {"kind": "row", "row": 2}}}
  ],
  "revealed": ["B2"]
}
```

- Cell id = column letter + row number (`A1` top-left). `"size": N` or `"rows": R, "cols": C`.
- `cells` in row-major order. `revealed` = cards face-up at the start (their status is known).

### Clues

| Type | Fields | Meaning |
|---|---|---|
| `FACT` | `who`, `status` | `who` is CRIMINAL / INNOCENT |
| `SAME` | `a`, `b` | same status |
| `DIFFERENT` | `a`, `b` | different status |
| `EXACTLY` / `AT_LEAST` / `AT_MOST` | `k`, `region`, optional `count` | number of criminals (or innocents if `"count": "innocent"`) in region |
| `COMPARE` | `r1`, `op` (`>` `<` `=`), `r2`, optional `count` | compare counts of two regions |
| `CONNECTED` | `region`, optional `count` | criminals (or innocents) in a line region are contiguous |
| `AND` | `parts` | all sub-clues hold |
| `NONE` | `text` | flavour text, no information |

### Regions

`{"kind": "row", "row": 2}` · `{"kind": "col", "col": "B"}` · `{"kind": "neighbors", "of": "B2"}` (8 around, not itself) · `{"kind": "cells", "cells": ["A1", "C3"]}` · `{"kind": "all"}` · `{"kind": "edges"}` · `{"kind": "corners"}` · `{"kind": "above", "of": "B4"}` (also `below`, `left`, `right`) · `{"kind": "inter", "regions": [R1, R2]}`

## Workflow

- One branch per person: `<name>/<topic>`, e.g. `an/dpll`. Open a PR into `main`; someone else reviews.
- `python -m pytest` must pass before merging.
- Do not change the function signatures in the stubs without telling the group.
- Write down what you did (for the contribution % in the report).
