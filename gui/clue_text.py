"""clue_to_text: JSON clue -> English sentence shown in the GUI (docs/CLUES.md section 8).

Owner: GUI & Video.
People are named by their character name ("Ivy") instead of their cell id ("C3")
whenever `names` knows the cell. The sentence only has to carry the exact meaning
of the JSON; it does not need to match the game word for word.
"""
from model import CRIMINAL

_QUANTIFIER = {"EXACTLY": "Exactly", "AT_LEAST": "At least", "AT_MOST": "At most"}
_OP_WORD = {">": "more", "<": "fewer"}

# Clue types whose sentence starts with one of our own words ("Exactly", "There's", "All", ...),
# never with a character name: their first letter is lowered inside an AND.
_OWN_FIRST_WORD = {"EXACTLY", "AT_LEAST", "AT_MOST", "PARITY", "CONNECTED", "COUNT_LINES"}


def clue_to_text(clue: dict, names: dict[str, str]) -> str:
    """JSON clue -> readable sentence, e.g. "Exactly 1 criminal in column A".

    names = {cell: character name} from public_state["cells"].
    Supports every clue type and region kind of docs/CLUES.md.
    """
    kind = clue.get("type")

    if kind == "NONE":
        return str(clue.get("text", ""))

    if kind == "FACT":
        who = _name(clue["who"], names)
        return f"{who} is a criminal" if clue["status"] == CRIMINAL else f"{who} is innocent"

    if kind == "SAME":
        return f"{_name(clue['a'], names)} and {_name(clue['b'], names)} have the same status"

    if kind == "DIFFERENT":
        return f"{_name(clue['a'], names)} and {_name(clue['b'], names)} have different statuses"

    if kind in _QUANTIFIER:
        noun = _noun(clue, clue["k"])
        return f"{_QUANTIFIER[kind]} {clue['k']} {noun} {_region_text(clue['region'], names)}"

    if kind == "PARITY":
        return (f"There's an {clue['parity']} number of {_noun(clue, 2)} "
                f"{_region_text(clue['region'], names)}")

    if kind == "CONNECTED":
        return f"All {_noun(clue, 2)} {_region_text(clue['region'], names)} are connected"

    if kind == "COMPARE":
        return _compare_text(clue, names)

    if kind == "COUNT_LINES":
        return _count_lines_text(clue)

    if kind == "AND":
        parts = [clue_to_text(part, names) for part in clue["parts"]]
        for i in range(1, len(parts)):
            if _starts_with_own_word(clue["parts"][i]):
                parts[i] = parts[i][0].lower() + parts[i][1:]
        return ", and ".join(parts)

    raise ValueError(f"Unknown clue type: {kind!r}")


# ---------------------------------------------------------------- helpers

def _name(cell: str, names: dict[str, str]) -> str:
    return names.get(cell, cell)


def _noun(clue: dict, k: int) -> str:
    """'criminal' / 'criminals' / 'innocent' / 'innocents' for count target and number k."""
    word = "innocent" if clue.get("count", "criminal") == "innocent" else "criminal"
    return word if k == 1 else word + "s"


def _join(words: list[str]) -> str:
    """['A'] -> 'A'; ['A', 'B'] -> 'A and B'; ['A', 'B', 'C'] -> 'A, B and C'."""
    if len(words) <= 1:
        return "".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]


def _region_text(region: dict, names: dict[str, str], inside_inter: bool = False) -> str:
    """Phrase that follows a count: 'in row 3', 'neighboring Ivy', 'in between A and B', ...

    Inside an inter the sub-regions are joined with 'and', so a cells list there is
    written with commas only ('among Alice, Eve') to keep it one sub-region.
    """
    kind = region.get("kind")
    if kind == "row":
        return f"in row {region['row']}"
    if kind == "col":
        return f"in column {region['col']}"
    if kind == "neighbors":
        return f"neighboring {_name(region['of'], names)}"
    if kind == "cells":
        people = [_name(c, names) for c in region["cells"]]
        return "among " + (", ".join(people) if inside_inter else _join(people))
    if kind == "all":
        return "in total"
    if kind == "edges":
        return "on the edges"
    if kind == "corners":
        return "in the corners"
    if kind in ("above", "below"):
        return f"{kind} {_name(region['of'], names)}"
    if kind in ("left", "right"):
        return f"to the {kind} of {_name(region['of'], names)}"
    if kind == "between":
        return f"in between {_name(region['a'], names)} and {_name(region['b'], names)}"
    if kind == "inter":
        return " and ".join(_region_text(r, names, inside_inter=True) for r in region["regions"])
    raise ValueError(f"Unknown region kind: {kind!r}")


def _compare_text(clue: dict, names: dict[str, str]) -> str:
    r1, r2, op = clue["r1"], clue["r2"], clue["op"]
    word = "innocent" if clue.get("count", "criminal") == "innocent" else "criminal"

    # Two people's neighbourhoods read best as a sentence about the people.
    if r1.get("kind") == "neighbors" and r2.get("kind") == "neighbors":
        x, y = _name(r1["of"], names), _name(r2["of"], names)
        if op == "=":
            return f"{x} and {y} have an equal number of {word} neighbors"
        return f"{x} has {_OP_WORD[op]} {word} neighbors than {y}"

    left, right = _region_text(r1, names), _region_text(r2, names)
    if op == "=":
        return f"There are as many {word}s {left} as {right}"
    return f"There are {_OP_WORD[op]} {word}s {left} than {right}"


def _count_lines_text(clue: dict) -> str:
    """'Exactly 2 rows have exactly 1 criminal', 'Only one column has ...', 'No row has ...'."""
    line = "row" if clue["axis"] == "row" else "column"
    k = clue["k"]
    where = _where_text(clue["where"], plural=k > 1)
    if k == 0:
        return f"No {line} has {where}"
    if k == 1:
        return f"Only one {line} has {where}"
    return f"Exactly {k} {line}s have {where}"


def _where_text(where: dict, plural: bool) -> str:
    """The condition of COUNT_LINES, written without a region."""
    kind = where["type"]
    if kind in _QUANTIFIER:
        return f"{_QUANTIFIER[kind].lower()} {where['k']} {_noun(where, where['k'])}"
    if kind == "PARITY":
        return f"an {where['parity']} number of {_noun(where, 2)}"
    if kind == "CONNECTED":
        return f"all {'their' if plural else 'its'} {_noun(where, 2)} connected"
    raise ValueError(f"Invalid where type: {kind!r}")


def _starts_with_own_word(clue: dict) -> bool:
    """Does clue_to_text(clue) start with our own word rather than a character name?"""
    kind = clue.get("type")
    if kind == "AND":
        return bool(clue["parts"]) and _starts_with_own_word(clue["parts"][0])
    if kind == "COMPARE":                   # "There are ..." unless it is about two people's neighbours
        return not (clue["r1"].get("kind") == "neighbors" and clue["r2"].get("kind") == "neighbors")
    return kind in _OWN_FIRST_WORD
