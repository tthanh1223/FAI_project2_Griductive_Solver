"""Clue -> CNF encoder and direct clue evaluator.

Owner: Encoder.

Variables: cell index in row-major order + 1 (A1 = 1, B1 = 2, ...); True = CRIMINAL.
Auxiliary variables start at rows * cols + 1.
CNF: list[list[int]] (DIMACS style, negative literal = negation).
Input / output of every function: docs/INTERFACES.md.
Meaning, CNF encoding and validation of every clue type: docs/CLUES.md.
"""
from itertools import combinations, product
from math import comb

from model import CRIMINAL, INNOCENT, region_cells

class VarMap:
    def __init__(self, rows: int, cols: int):
        self.rows = rows
        self.cols = cols
        self.cells = [
            f"{chr(ord('A') + col)}{row}"
            for row in range(1, rows + 1)
            for col in range(cols)
        ]
        self._ids = {
            cell: index
            for index, cell in enumerate(self.cells, start=1)
        }
        self.next_aux = rows * cols + 1

    def var(self, cell: str) -> int:
        if not isinstance(cell, str) or cell not in self._ids:
            raise ValueError(f"Invalid cell: {cell!r}")
        return self._ids[cell]

    def cell(self, var: int) -> str:
        if type(var) is not int or not 1 <= var <= len(self.cells):
            raise ValueError(f"Invalid cell variable: {var!r}")
        return self.cells[var - 1]

    def new_aux(self) -> int:
        var = self.next_aux
        self.next_aux += 1
        return var
    

_COUNT_TYPES = {"EXACTLY", "AT_LEAST", "AT_MOST"}
_WHERE_TYPES = _COUNT_TYPES | {"PARITY", "CONNECTED"}
_WITH_COUNT = _WHERE_TYPES | {"COMPARE"}

_REQUIRED = {
    "NONE": {"text"},
    "FACT": {"who", "status"},
    "SAME": {"a", "b"},
    "DIFFERENT": {"a", "b"},
    "EXACTLY": {"region", "k"},
    "AT_LEAST": {"region", "k"},
    "AT_MOST": {"region", "k"},
    "CONNECTED": {"region"},
    "PARITY": {"region", "parity"},
    "COMPARE": {"r1", "r2", "op"},
    "AND": {"parts"},
    "COUNT_LINES": {"axis", "k", "where"},
}


def check_k(k, maximum):
    if type(k) is not int or not 0 <= k <= maximum:
        raise ValueError(f"k must be in [0, {maximum}]")


def is_line(cells, vm):
    if len(cells) <= 1:
        return True

    coords = [divmod(vm.var(cell) - 1, vm.cols) for cell in cells]
    rows = [r for r, c in coords]
    cols = [c for r, c in coords]
    if len(set(rows)) == 1:
        return max(cols) - min(cols) + 1 == len(cells)
    if len(set(cols)) == 1:
        return max(rows) - min(rows) + 1 == len(cells)
    return False


def validate_clue(clue: dict, rows: int, cols: int) -> None:
    if not isinstance(clue, dict):
        raise ValueError("A clue must be a dictionary")

    kind = clue.get("type")
    if not isinstance(kind, str) or kind not in _REQUIRED:
        raise ValueError(f"Unknown clue type: {kind!r}")

    required = _REQUIRED[kind] | {"type"}
    allowed = required | ({"count"} if kind in _WITH_COUNT else set())
    if not required <= clue.keys() or not clue.keys() <= allowed:
        raise ValueError(f"Invalid fields for {kind}")
    if clue.get("count", "criminal") not in ("criminal", "innocent"):
        raise ValueError("Invalid count target")

    vm = VarMap(rows, cols)

    def region(key):
        value = clue[key]
        if not isinstance(value, dict):
            raise ValueError(f"Invalid region in {key}")
        return region_cells(value, rows, cols)

    if kind == "NONE":
        if not isinstance(clue["text"], str):
            raise ValueError("NONE requires text")
    elif kind == "FACT":
        vm.var(clue["who"])
        if clue["status"] not in (CRIMINAL, INNOCENT):
            raise ValueError("Invalid status")
    elif kind in ("SAME", "DIFFERENT"):
        vm.var(clue["a"])
        vm.var(clue["b"])
    elif kind == "AND":
        parts = clue["parts"]
        if not isinstance(parts, list) or not parts:
            raise ValueError("AND requires at least one part")
        for part in parts:
            validate_clue(part, rows, cols)
    elif kind in _COUNT_TYPES:
        check_k(clue["k"], len(region("region")))
    elif kind == "CONNECTED":
        if not is_line(region("region"), vm):
            raise ValueError("CONNECTED requires a contiguous line")
    elif kind == "PARITY":
        if clue["parity"] not in ("odd", "even"):
            raise ValueError("Invalid parity")
        if not 1 <= len(region("region")) <= 16:
            raise ValueError("PARITY requires 1 to 16 cells")
    elif kind == "COMPARE":
        if clue["op"] not in ("<", ">", "="):
            raise ValueError("Invalid comparison")
        if len(set(region("r1")) | set(region("r2"))) > 16:
            raise ValueError("COMPARE exceeds 16 cells")
    elif kind == "COUNT_LINES":
        axis = clue["axis"]
        if axis not in ("row", "col"):
            raise ValueError("Invalid axis")
        lines = line_regions(axis, rows, cols)
        length = cols if axis == "row" else rows
        check_k(clue["k"], len(lines))
        if length > 8:
            raise ValueError("COUNT_LINES exceeds 8 cells per line")

        where = clue["where"]
        if not isinstance(where, dict) or "region" in where:
            raise ValueError("Invalid where clause")
        inner_kind = where.get("type")
        if not isinstance(inner_kind, str) or inner_kind not in _WHERE_TYPES:
            raise ValueError("Invalid where type")
        for line in lines:
            validate_clue({**where, "region": line}, rows, cols)


def encode_clue(clue: dict, vm: VarMap) -> list[list[int]]:
    kind = clue["type"]

    if kind == "NONE":
        return []

    if kind == "FACT":
        x = vm.var(clue["who"])
        return [[x if clue["status"] == CRIMINAL else -x]]

    if kind in ("SAME", "DIFFERENT"):
        a = vm.var(clue["a"])
        b = vm.var(clue["b"])
        if kind == "SAME":
            return [[-a, b], [a, -b]]
        return [[a, b], [-a, -b]]
    
    if kind == "AND":
        clauses = []
        for part in clue["parts"]:
            clauses.extend(encode_clue(part, vm))
        return clauses

    if kind in ("PARITY", "COMPARE"):
        return encode_truth_table(clue, vm)

    if kind == "COUNT_LINES":
        return encode_count_lines(clue, vm)

    if kind in ("EXACTLY", "AT_LEAST", "AT_MOST", "CONNECTED"):
        cells = region_cells(clue["region"], vm.rows, vm.cols)
        sign = -1 if clue.get("count", "criminal") == "innocent" else 1
        lits = [sign * vm.var(cell) for cell in cells]

        if kind == "CONNECTED":
            return [
                [-left, middle, -right]
                for left, middle, right in combinations(lits, 3)
            ]
        return encode_count(kind, lits, clue["k"], vm)

    raise ValueError(f"Unknown clue type: {kind!r}")

def line_regions(axis, rows, cols):
    if axis == "row":
        return [{"kind": "row", "row": r} for r in range(1, rows + 1)]
    return [
        {"kind": "col", "col": chr(ord("A") + c)}
        for c in range(cols)
    ]

def evaluate_clue(clue: dict, assignment: dict[str, bool], rows: int, cols: int) -> bool: 
    kind = clue["type"]
    if kind == "NONE":
        return True
    if kind == "FACT":
        return assignment[clue["who"]] == (clue["status"] == CRIMINAL)
    if kind in ("SAME", "DIFFERENT"):
        same = assignment[clue["a"]] == assignment[clue["b"]]
        return same if kind == "SAME" else not same
    if kind == "AND":
        return all(
            evaluate_clue(part, assignment, rows, cols)
            for part in clue["parts"]
        )
    if kind == "COUNT_LINES":
        matches = 0
        for line in line_regions(clue["axis"], rows, cols):
            inner = {**clue["where"], "region": line}
            if evaluate_clue(inner, assignment, rows, cols):
                matches += 1
        return matches == clue["k"]

    target = clue.get("count", "criminal") == "criminal"

    def selected(region):
        cells = region_cells(region, rows, cols)
        return [assignment[cell] == target for cell in cells]

    if kind == "COMPARE":
        left = sum(selected(clue["r1"]))
        right = sum(selected(clue["r2"]))
        if clue["op"] == "=":
            return left == right
        if clue["op"] == ">":
            return left > right
        return left < right

    flags = selected(clue["region"])
    total = sum(flags)

    if kind == "EXACTLY":
        return total == clue["k"]
    if kind == "AT_LEAST":
        return total >= clue["k"]
    if kind == "AT_MOST":
        return total <= clue["k"]
    if kind == "PARITY":
        return total % 2 == (1 if clue["parity"] == "odd" else 0)
    if kind == "CONNECTED":
        indices = [i for i, value in enumerate(flags) if value]
        return not indices or indices[-1] - indices[0] + 1 == total

    raise ValueError(f"Unknown clue type: {kind!r}")


def build_kb(public_state: dict) -> tuple[list[list[int]], VarMap, dict]:
    rows = public_state["rows"]
    cols = public_state["cols"]
    vm = VarMap(rows, cols)
    clauses = []

    for clue in public_state["revealed"].values():
        clauses.extend(encode_clue(clue, vm))

    for cell, status in public_state["verdicts"].items():
        if status not in (CRIMINAL, INNOCENT):
            raise ValueError(f"Invalid verdict: {status!r}")
        x = vm.var(cell)
        clauses.append([x if status == CRIMINAL else -x])

    primary = rows * cols
    stats = {
        "primary": primary,
        "aux": vm.next_aux - 1 - primary,
        "clauses": len(clauses),
    }
    return clauses, vm, stats

def sequential_at_most(lits, k, vm):
    # Caller handles the boundaries k == 0 and k == len(lits).
    n = len(lits)
    s = [[vm.new_aux() for _ in range(k)] for _ in range(n - 1)]

    clauses = [[-lits[0], s[0][0]]]
    for j in range(1, k):
        clauses.append([-s[0][j]])

    for i in range(1, n - 1):
        x = lits[i]
        clauses.append([-x, s[i][0]])
        clauses.append([-s[i - 1][0], s[i][0]])

        for j in range(1, k):
            clauses.append([-x, -s[i - 1][j - 1], s[i][j]])
            clauses.append([-s[i - 1][j], s[i][j]])

        clauses.append([-x, -s[i - 1][k - 1]])

    clauses.append([-lits[-1], -s[-1][k - 1]])
    return clauses


def at_most(lits, k, vm, limit):
    n = len(lits)
    if k == n:
        return []
    if k == 0:
        return [[-lit] for lit in lits]

    if comb(n, k + 1) > limit:
        return sequential_at_most(lits, k, vm)

    return [
        [-lit for lit in group]
        for group in combinations(lits, k + 1)
    ]


def encode_count(kind, lits, k, vm, *, limit=2000):
    if type(k) is not int or not 0 <= k <= len(lits):
        raise ValueError(f"Invalid k: {k!r}")

    clauses = []
    if kind in ("AT_MOST", "EXACTLY"):
        clauses.extend(at_most(lits, k, vm, limit))
    if kind in ("AT_LEAST", "EXACTLY"):
        opposite = [-lit for lit in lits]
        clauses.extend(at_most(opposite, len(lits) - k, vm, limit))
    return clauses

def assignments_for(cells, vm):
    for bits in product((False, True), repeat=len(cells)):
        assignment = dict.fromkeys(vm.cells, False)
        assignment.update(zip(cells, bits))
        block = [
            -vm.var(cell) if bit else vm.var(cell)
            for cell, bit in zip(cells, bits)
        ]
        yield assignment, block


def encode_truth_table(clue, vm):
    if clue["type"] == "PARITY":
        cells = region_cells(clue["region"], vm.rows, vm.cols)
    else:
        left = region_cells(clue["r1"], vm.rows, vm.cols)
        right = region_cells(clue["r2"], vm.rows, vm.cols)
        cells = sorted(set(left) | set(right), key=vm.var)

    clauses = []
    for assignment, block in assignments_for(cells, vm):
        if not evaluate_clue(clue, assignment, vm.rows, vm.cols):
            if not block:
                # A false comparison of two empty regions is unsatisfiable.
                x = vm.new_aux()
                return [[x], [-x]]
            clauses.append(block)
    return clauses

def encode_count_lines(clue, vm):
    clauses = []
    line_vars = []

    for line in line_regions(clue["axis"], vm.rows, vm.cols):
        r = vm.new_aux()
        line_vars.append(r)
        inner = {**clue["where"], "region": line}
        cells = region_cells(line, vm.rows, vm.cols)

        for assignment, block in assignments_for(cells, vm):
            matches = evaluate_clue(inner, assignment, vm.rows, vm.cols)
            clauses.append(block + [r if matches else -r])

    clauses.extend(encode_count("EXACTLY", line_vars, clue["k"], vm))
    return clauses