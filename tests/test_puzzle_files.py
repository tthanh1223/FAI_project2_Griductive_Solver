import json
from pathlib import Path

PUZZLES = sorted((Path(__file__).resolve().parents[1] / "puzzles").glob("*.json"))


def test_puzzle_files_have_required_fields():
    assert PUZZLES
    for path in PUZZLES:
        p = json.loads(path.read_text(encoding="utf-8"))
        rows = p.get("rows", p.get("size"))
        cols = p.get("cols", p.get("size"))
        assert len(p["cells"]) == rows * cols, path.name
        assert p["revealed"], path.name
        for c in p["cells"]:
            assert {"cell", "name", "job", "status", "clue"} <= c.keys(), path.name
