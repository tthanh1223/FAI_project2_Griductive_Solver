"""clue_to_text (gui/app.py): every clue type and region kind of docs/CLUES.md."""
import json
from pathlib import Path

import pytest

from gui.app import clue_to_text

NAMES = {"A1": "Alice", "B1": "Bob", "C1": "Cara", "A2": "Dan", "B2": "Eve",
         "C2": "Finn", "A3": "Gina", "B3": "Hugo", "C3": "Ivy"}


def R(kind, **kw):
    return {"kind": kind, **kw}


@pytest.mark.parametrize("clue, text", [
    # INTERFACES.md example
    ({"type": "EXACTLY", "k": 1, "region": R("col", col="A")}, "Exactly 1 criminal in column A"),
    # C1-C3
    ({"type": "FACT", "who": "B2", "status": "CRIMINAL"}, "Eve is a criminal"),
    ({"type": "FACT", "who": "B2", "status": "INNOCENT"}, "Eve is innocent"),
    ({"type": "SAME", "a": "B2", "b": "C3"}, "Eve and Ivy have the same status"),
    ({"type": "DIFFERENT", "a": "A3", "b": "C2"}, "Gina and Finn have different statuses"),
    # C4-C6, plural and count: innocent
    ({"type": "EXACTLY", "k": 2, "region": R("row", row=2)}, "Exactly 2 criminals in row 2"),
    ({"type": "AT_LEAST", "k": 1, "count": "innocent", "region": R("row", row=3)},
     "At least 1 innocent in row 3"),
    ({"type": "AT_MOST", "k": 0, "region": R("neighbors", of="A1")}, "At most 0 criminals neighboring Alice"),
    # E2 COMPARE: neighbours of two people, and general regions
    ({"type": "COMPARE", "r1": R("neighbors", of="A1"), "op": "=", "r2": R("neighbors", of="C3")},
     "Alice and Ivy have an equal number of criminal neighbors"),
    ({"type": "COMPARE", "r1": R("neighbors", of="A1"), "op": ">", "r2": R("neighbors", of="A3")},
     "Alice has more criminal neighbors than Gina"),
    ({"type": "COMPARE", "r1": R("neighbors", of="A1"), "op": "<", "r2": R("neighbors", of="A3"),
      "count": "innocent"}, "Alice has fewer innocent neighbors than Gina"),
    ({"type": "COMPARE", "r1": R("row", row=1), "op": ">", "r2": R("row", row=3), "count": "innocent"},
     "There are more innocents in row 1 than in row 3"),
    ({"type": "COMPARE", "r1": R("col", col="A"), "op": "<", "r2": R("col", col="C")},
     "There are fewer criminals in column A than in column C"),
    ({"type": "COMPARE", "r1": R("corners"), "op": "=", "r2": R("edges")},
     "There are as many criminals in the corners as on the edges"),
    # E3 AND (later parts start lower-case, names keep their capital)
    ({"type": "AND", "parts": [{"type": "FACT", "who": "B2", "status": "CRIMINAL"},
                               {"type": "EXACTLY", "k": 2, "region": R("above", of="C3")}]},
     "Eve is a criminal, and exactly 2 criminals above Ivy"),
    ({"type": "AND", "parts": [{"type": "EXACTLY", "k": 2, "count": "innocent", "region": R("row", row=3)},
                               {"type": "CONNECTED", "count": "innocent", "region": R("row", row=3)}]},
     "Exactly 2 innocents in row 3, and all innocents in row 3 are connected"),
    ({"type": "AND", "parts": [{"type": "AT_MOST", "k": 1, "region": R("row", row=1)},
                               {"type": "SAME", "a": "A1", "b": "B1"}]},
     "At most 1 criminal in row 1, and Alice and Bob have the same status"),
    # E5 CONNECTED
    ({"type": "CONNECTED", "region": R("col", col="B")}, "All criminals in column B are connected"),
    ({"type": "CONNECTED", "count": "innocent", "region": R("above", of="A3")},
     "All innocents above Gina are connected"),
    # E6 NONE
    ({"type": "NONE", "text": "I only came in for the lavender candles."},
     "I only came in for the lavender candles."),
    # E8 PARITY
    ({"type": "PARITY", "parity": "odd", "count": "innocent", "region": R("between", a="A1", b="C1")},
     "There's an odd number of innocents in between Alice and Cara"),
    ({"type": "PARITY", "parity": "even", "region": R("all")}, "There's an even number of criminals in total"),
    # E9 COUNT_LINES, with every where type
    ({"type": "COUNT_LINES", "axis": "row", "k": 1, "where": {"type": "EXACTLY", "k": 1}},
     "Only one row has exactly 1 criminal"),
    ({"type": "COUNT_LINES", "axis": "col", "k": 2, "where": {"type": "AT_LEAST", "k": 2, "count": "innocent"}},
     "Exactly 2 columns have at least 2 innocents"),
    ({"type": "COUNT_LINES", "axis": "row", "k": 0, "where": {"type": "AT_MOST", "k": 0}},
     "No row has at most 0 criminals"),
    ({"type": "COUNT_LINES", "axis": "col", "k": 3, "where": {"type": "PARITY", "parity": "odd"}},
     "Exactly 3 columns have an odd number of criminals"),
    ({"type": "COUNT_LINES", "axis": "row", "k": 2, "where": {"type": "CONNECTED", "count": "innocent"}},
     "Exactly 2 rows have all their innocents connected"),
    ({"type": "COUNT_LINES", "axis": "col", "k": 1, "where": {"type": "CONNECTED"}},
     "Only one column has all its criminals connected"),
])
def test_clue_types(clue, text):
    assert clue_to_text(clue, NAMES) == text


@pytest.mark.parametrize("region, phrase", [
    (R("row", row=3), "in row 3"),
    (R("col", col="B"), "in column B"),
    (R("neighbors", of="B2"), "neighboring Eve"),
    (R("cells", cells=["A1"]), "among Alice"),
    (R("cells", cells=["A1", "C3"]), "among Alice and Ivy"),
    (R("cells", cells=["A1", "B1", "C3"]), "among Alice, Bob and Ivy"),
    (R("all"), "in total"),
    (R("edges"), "on the edges"),
    (R("corners"), "in the corners"),
    (R("above", of="B3"), "above Hugo"),
    (R("below", of="B1"), "below Bob"),
    (R("left", of="C2"), "to the left of Finn"),
    (R("right", of="A2"), "to the right of Dan"),
    (R("between", a="A1", b="A3"), "in between Alice and Gina"),
    (R("inter", regions=[R("between", a="B1", b="B3"), R("neighbors", of="A2")]),
     "in between Bob and Hugo and neighboring Dan"),
    (R("inter", regions=[R("row", row=1), R("col", col="C"), R("corners")]),
     "in row 1 and in column C and in the corners"),
])
def test_region_kinds(region, phrase):
    assert clue_to_text({"type": "AT_LEAST", "k": 2, "region": region}, NAMES) == f"At least 2 criminals {phrase}"


def test_and_never_lowers_a_name():
    names = {"A1": "Abel", "B1": "Theresa", "C1": "Allie"}
    clue = {"type": "AND", "parts": [{"type": "FACT", "who": "A1", "status": "CRIMINAL"},
                                     {"type": "SAME", "a": "B1", "b": "A1"},
                                     {"type": "FACT", "who": "C1", "status": "INNOCENT"},
                                     {"type": "COMPARE", "r1": R("row", row=1), "op": ">", "r2": R("row", row=2)}]}
    assert clue_to_text(clue, names) == ("Abel is a criminal, and Theresa and Abel have the same status, "
                                         "and Allie is innocent, and there are more criminals in row 1 than in row 2")


def test_cells_inside_inter_stays_one_region():
    region = R("inter", regions=[R("cells", cells=["A1", "B2"]), R("row", row=1)])
    assert clue_to_text({"type": "EXACTLY", "k": 1, "region": region}, NAMES) == \
        "Exactly 1 criminal among Alice, Eve and in row 1"


def test_unknown_cell_falls_back_to_cell_id():
    assert clue_to_text({"type": "FACT", "who": "D4", "status": "INNOCENT"}, NAMES) == "D4 is innocent"


def test_bad_clue_raises_value_error():
    with pytest.raises(ValueError):
        clue_to_text({"type": "WHATEVER"}, NAMES)
    with pytest.raises(ValueError):
        clue_to_text({"type": "EXACTLY", "k": 1, "region": R("diagonal")}, NAMES)


def test_every_clue_in_every_puzzle_file_has_text():
    """No puzzle in puzzles/ produces an error or a raw dict."""
    for path in sorted(Path(__file__).resolve().parents[1].glob("puzzles/*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        names = {c["cell"]: c["name"] for c in data["cells"]}
        for c in data["cells"]:
            text = clue_to_text(c["clue"], names)
            assert text and "{" not in text and "_" not in text, (path.name, c["cell"], text)
