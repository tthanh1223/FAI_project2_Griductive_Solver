"""Clue -> CNF encoder and direct clue evaluator.

Owner: Encoder.

Variables: cell index in row-major order + 1 (A1 = 1, B1 = 2, ...); True = CRIMINAL.
Auxiliary variables start at rows * cols + 1.
CNF: list[list[int]] (DIMACS style, negative literal = negation).
Input / output of every function: docs/INTERFACES.md.
Meaning, CNF encoding and validation of every clue type: docs/CLUES.md.
"""
from itertools import combinations
from math import comb

from model import CRIMINAL, INNOCENT, region_cells

_LIMIT = 2000  # max subsets before the sequential counter (CLUES.md 4.4)

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


class VarMap:
    """Deterministic cell <-> variable mapping plus a counter for auxiliary variables."""

    def __init__(self, rows: int, cols: int):
        self.rows = rows
        self.cols = cols
        self.cells = [
            f"{chr(ord('A') + col)}{row}"
            for row in range(1, rows + 1)
            for col in range(cols)
        ]
        self._ids = {cell: index for index, cell in enumerate(self.cells, start=1)}
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


# ---------------------------------------------------------------- validate

def validate_clue(clue: dict, rows: int, cols: int) -> None:
    """Raise ValueError on unknown type, unknown cell, or k outside [0, |R|].

    Full rule list: docs/CLUES.md section 6.
    """
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
        _check_k(clue["k"], len(region("region")))
    elif kind == "CONNECTED":
        if not _is_line(region("region"), vm):
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
        lines = _line_regions(axis, rows, cols)
        length = cols if axis == "row" else rows
        _check_k(clue["k"], len(lines))
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


def _check_k(k, maximum):
    if type(k) is not int or not 0 <= k <= maximum:
        raise ValueError(f"k must be in [0, {maximum}]")


def _is_line(cells, vm):
    """Is `cells` one contiguous segment of a single row or column?"""
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


def _line_regions(axis, rows, cols):
    """Regions of every row (axis "row") or every column (axis "col")."""
    if axis == "row":
        return [{"kind": "row", "row": r} for r in range(1, rows + 1)]
    return [{"kind": "col", "col": chr(ord("A") + c)} for c in range(cols)]


# ---------------------------------------------------------------- encode

def encode_clue(clue: dict, vm: VarMap) -> list[list[int]]:
    """CNF of one clue. Encoding per type: docs/CLUES.md section 4."""
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

    if kind == "PARITY":
        return _encode_parity(clue, vm)

    if kind == "COMPARE":
        return _encode_compare(clue, vm)

    if kind == "COUNT_LINES":
        return _encode_count_lines(clue, vm)

    if kind in ("EXACTLY", "AT_LEAST", "AT_MOST", "CONNECTED"):
        cells = region_cells(clue["region"], vm.rows, vm.cols)
        lits = _counted_lits(cells, clue, vm)

        if kind == "CONNECTED":
            return [
                [-left, middle, -right]
                for left, middle, right in combinations(lits, 3)
            ]
        return _encode_count(kind, lits, clue["k"], vm)

    raise ValueError(f"Unknown clue type: {kind!r}")


def _counted_lits(cells, clue, vm):
    """Literal that is true when a cell is counted (criminal, or innocent if count = innocent)."""
    sign = -1 if clue.get("count", "criminal") == "innocent" else 1
    return [sign * vm.var(cell) for cell in cells]


def _false(vm):
    """An always-false CNF without an empty clause."""
    x = vm.new_aux()
    return [[x], [-x]]


# Truth tables (CLUES.md 4.2, 4.4). A row of the table is a bit mask over the cells U:
# bit set = CRIMINAL, U[0] is the most significant bit, so rows come in the same order
# as itertools.product((False, True), repeat=len(U)).

def _rows(cells, vm):
    """Yield (mask, block) for every assignment of `cells`; block is the clause forbidding it."""
    xs = [vm.var(cell) for cell in cells]
    n = len(xs)
    for mask in range(1 << n):
        yield mask, [-x if mask >> (n - 1 - i) & 1 else x for i, x in enumerate(xs)]


def _holds(clue, cells, vm):
    """Return holds(mask), equal to evaluate_clue(clue) for a clue that reads only `cells`.

    Handles PARITY, COMPARE, EXACTLY, AT_LEAST, AT_MOST and CONNECTED. For CONNECTED
    the region must be `cells` itself (the COUNT_LINES case), so its cells sit on
    consecutive bits.
    """
    kind = clue["type"]
    n = len(cells)
    bit = {cell: 1 << (n - 1 - i) for i, cell in enumerate(cells)}
    innocent = clue.get("count", "criminal") == "innocent"

    def mask_of(region):
        return sum(bit[cell] for cell in region_cells(region, vm.rows, vm.cols))

    def counted(mask, region_mask):
        return (~mask if innocent else mask) & region_mask

    if kind == "COMPARE":
        m1, m2 = mask_of(clue["r1"]), mask_of(clue["r2"])
        op = clue["op"]

        def holds(mask):
            left = counted(mask, m1).bit_count()
            right = counted(mask, m2).bit_count()
            return left == right if op == "=" else left > right if op == ">" else left < right
        return holds

    region = mask_of(clue["region"])
    if kind == "PARITY":
        want = 1 if clue["parity"] == "odd" else 0
        return lambda mask: counted(mask, region).bit_count() % 2 == want
    if kind == "EXACTLY":
        return lambda mask: counted(mask, region).bit_count() == clue["k"]
    if kind == "AT_LEAST":
        return lambda mask: counted(mask, region).bit_count() >= clue["k"]
    if kind == "AT_MOST":
        return lambda mask: counted(mask, region).bit_count() <= clue["k"]
    if kind == "CONNECTED":
        def holds(mask):
            s = counted(mask, region)
            if not s:
                return True
            s //= s & -s           # drop trailing zeros
            return not s & (s + 1)  # remaining bits are one block of ones
        return holds
    raise ValueError(f"No truth table for clue type: {kind!r}")


def _truth_table(clue, cells, vm):
    """Forbid every assignment of `cells` that makes the clue false."""
    holds = _holds(clue, cells, vm)
    clauses = [block for mask, block in _rows(cells, vm) if not holds(mask)]
    if clauses == [[]]:
        # No cells and the clue is false (e.g. COMPARE ">" on two empty regions).
        return _false(vm)
    return clauses


def _encode_parity(clue, vm):
    cells = region_cells(clue["region"], vm.rows, vm.cols)
    return _truth_table(clue, cells, vm)


def _encode_compare(clue, vm):
    left = region_cells(clue["r1"], vm.rows, vm.cols)
    right = region_cells(clue["r2"], vm.rows, vm.cols)
    cells = sorted(set(left) | set(right), key=vm.var)
    return _truth_table(clue, cells, vm)


def _encode_count_lines(clue, vm):
    """Tseitin: r_L <-> where(L) for every line L (truth table, <= 8 cells), then EXACTLY k of r_L."""
    clauses = []
    line_vars = []

    for line in _line_regions(clue["axis"], vm.rows, vm.cols):
        r = vm.new_aux()
        line_vars.append(r)
        cells = region_cells(line, vm.rows, vm.cols)
        holds = _holds({**clue["where"], "region": line}, cells, vm)
        for mask, block in _rows(cells, vm):
            clauses.append(block + [r if holds(mask) else -r])

    clauses.extend(_encode_count("EXACTLY", line_vars, clue["k"], vm))
    return clauses


# Counting (CLUES.md 4.1, 4.4).

def _encode_count(kind, lits, k, vm, *, limit=_LIMIT):
    """EXACTLY / AT_LEAST / AT_MOST k of `lits`; switches to the sequential counter above `limit` subsets."""
    if type(k) is not int or not 0 <= k <= len(lits):
        raise ValueError(f"Invalid k: {k!r}")

    clauses = []
    if kind in ("AT_MOST", "EXACTLY"):
        clauses.extend(_at_most(lits, k, vm, limit))
    if kind in ("AT_LEAST", "EXACTLY"):
        opposite = [-lit for lit in lits]
        clauses.extend(_at_most(opposite, len(lits) - k, vm, limit))
    return clauses


def _at_most(lits, k, vm, limit):
    n = len(lits)
    if k == n:
        return []
    if k == 0:
        return [[-lit] for lit in lits]

    if comb(n, k + 1) > limit:
        return _sequential_at_most(lits, k, vm)

    return [[-lit for lit in group] for group in combinations(lits, k + 1)]


def _sequential_at_most(lits, k, vm):
    """Sinz 2005, 1 <= k < len(lits). s[i][j] = "at least j+1 of lits[0..i] are true"."""
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


# ---------------------------------------------------------------- evaluate

def evaluate_clue(clue: dict, assignment: dict[str, bool], rows: int, cols: int) -> bool:
    """Is the clue true under a complete assignment? Must NOT call the CNF encoder."""
    kind = clue["type"]
    if kind == "NONE":
        return True
    if kind == "FACT":
        return assignment[clue["who"]] == (clue["status"] == CRIMINAL)
    if kind in ("SAME", "DIFFERENT"):
        same = assignment[clue["a"]] == assignment[clue["b"]]
        return same if kind == "SAME" else not same
    if kind == "AND":
        return all(evaluate_clue(part, assignment, rows, cols) for part in clue["parts"])
    if kind == "COUNT_LINES":
        matches = 0
        for line in _line_regions(clue["axis"], rows, cols):
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


# ---------------------------------------------------------------- KB

def build_kb(public_state: dict) -> tuple[list[list[int]], VarMap, dict]:
    """KB_t = CNF(revealed clues) + unit clauses for proved verdicts.

    Returns (clauses, varmap, stats), stats = {"primary", "aux", "clauses"}.
    """
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
