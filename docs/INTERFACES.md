# Interfaces: input / output của từng hàm

File này là **hợp đồng ghép code**. Mỗi người code phần mình sao cho đúng input/output ở đây thì ghép là chạy.
Muốn đổi gì thì báo cả nhóm và sửa file này trước.

Ví dụ trong file dùng `puzzles/p3_01.json` (3×3, A1 lật sẵn).

## Luồng gọi

```
main.py ─► gui/app.py
             │ load_puzzle(path) ─────────────► Puzzle
             │ GameEngine(puzzle)
             │ engine.public_state() ─────────► PublicState
             │ engine.submit(cell, verdict) ──► "ACCEPTED" | "NOT_PROVABLE" | "CONTRADICTED"
             │ agent.hint(state) / agent.next_move(state)
             ▼
GameEngine.submit ─► LogicAgent.classify(state) ─► encoder.build_kb(state) ─► dpll.dpll_solve(...)
experiments/run.py ─► LogicAgent.solve(engine) ─► SolveResult
```

Không file nào ngoài `engine.py` được đọc `Cell.status` của ô chưa chốt hay clue của thẻ chưa lật.

## Hằng số (dùng chung, không gõ chuỗi tay)

| Hằng | Giá trị | Ở đâu |
|---|---|---|
| `CRIMINAL`, `INNOCENT` | `"CRIMINAL"`, `"INNOCENT"` | `model.py` |
| `UNKNOWN`, `INCONSISTENT` | `"UNKNOWN"`, `"INCONSISTENT"` | `agent.py` |
| `ACCEPTED`, `NOT_PROVABLE`, `CONTRADICTED` | cùng tên | `engine.py` |

Cell id luôn là chuỗi `"A1"` (cột chữ hoa + hàng số, hàng 1 ở trên cùng). Mọi danh sách ô đều theo **row-major**: A1, B1, C1, A2, …

## model.py (Engine & Puzzle)

### `load_puzzle(path: str) -> Puzzle`
- Input: đường dẫn file JSON (format trong README).
- Output: `Puzzle(id, rows, cols, cells, revealed)`; `cells` là `list[Cell]` theo row-major, `Cell(cell, name, job, status, clue)`. `"size": 3` → `rows = cols = 3`.
- Lỗi: thiếu trường, số ô ≠ rows × cols, cell id trùng → `ValueError`.

### `all_cells(rows, cols) -> list[str]`
`all_cells(2, 3)` → `["A1", "B1", "C1", "A2", "B2", "C2"]`.

### `region_cells(region: dict, rows, cols) -> list[str]`
- Output: danh sách ô, row-major, không trùng.
- `{"kind":"row","row":2}` → `["A2","B2","C2"]` · `{"kind":"neighbors","of":"A1"}` → `["B1","A2","B2"]` · `{"kind":"above","of":"B3"}` → `["B1","B2"]`.
- Region sai (kind lạ, ô ngoài lưới) → `ValueError`.

### `cells_in_clue(clue: dict, rows, cols) -> list[str]`
Mọi ô clue nhắc tới hoặc đếm, để GUI tô sáng. `{"type":"SAME","a":"B2","b":"C3"}` → `["B2","C3"]`. `NONE` → `[]`.

## engine.py (Engine & Puzzle)

### `GameEngine(puzzle: Puzzle, agent: LogicAgent | None = None)`
`agent` mặc định là `LogicAgent()`. Engine dùng agent để quyết verdict có được chấp nhận không.

### `public_state() -> PublicState`
```python
{
  "rows": 3, "cols": 3,
  "cells": [{"cell": "A1", "name": "Alice", "job": "Cook"}, ...],      # đủ 9 ô, KHÔNG có status
  "revealed": {"A1": {"type": "FACT", "who": "A2", "status": "CRIMINAL"}},
  "verdicts": {"A1": "INNOCENT"},
}
```
- `revealed` và `verdicts` luôn có **cùng tập key** (thẻ lật đúng lúc verdict được chấp nhận; thẻ lật sẵn thì status cũng đã biết).
- Trả về **bản sao**: người gọi sửa dict này không làm hỏng engine.

### `submit(cell: str, verdict: str) -> str`
- Input: ô chưa chốt, `verdict` là `CRIMINAL` hoặc `INNOCENT`.
- Gọi `agent.classify(public_state())`:
  - `classify[cell] == verdict` → **`ACCEPTED`**: thêm `verdicts[cell]`, lật `revealed[cell] = clue của ô đó`.
  - `classify[cell]` là phía ngược → **`CONTRADICTED`**, không đổi gì.
  - `UNKNOWN` → **`NOT_PROVABLE`**, không đổi gì.
- Ví dụ lúc đầu: `submit("A2","CRIMINAL")` → `"ACCEPTED"`; `submit("A2","INNOCENT")` → `"CONTRADICTED"`; `submit("B1","INNOCENT")` → `"NOT_PROVABLE"`.
- Ô đã chốt / ô không tồn tại / verdict lạ → `ValueError`.
- Sau `ACCEPTED`, engine `assert` verdict trùng đáp án ẩn (bắt lỗi encoder/agent sớm).

### `restart() -> None` · `is_solved() -> bool`
`restart` về đúng trạng thái lúc đầu. `is_solved` = mọi ô đã có verdict.

## encoder.py (Encoder)

### `VarMap(rows, cols)`
- `var("A1") == 1`, `var("B1") == 2`, … `var("C3") == 9`; `cell(9) == "C3"`.
- `new_aux()` cấp biến phụ từ `rows*cols + 1` trở lên. `n_vars = vm.next_aux - 1` (tổng số biến, kể cả phụ).

### `encode_clue(clue: dict, vm: VarMap) -> list[list[int]]`
- Output: CNF, mỗi mệnh đề là `list[int]` khác 0 (âm = phủ định), không mệnh đề rỗng.
- Ví dụ: `{"type":"FACT","who":"A2","status":"CRIMINAL"}` → `[[4]]` · `{"type":"DIFFERENT","a":"C2","b":"A2"}` → `[[6, 4], [-6, -4]]` · `NONE` → `[]`.

### `evaluate_clue(clue: dict, assignment: dict[str, bool], rows, cols) -> bool`
- `assignment` đủ mọi ô, `True` = tội phạm. Không được gọi `encode_clue`.

### `validate_clue(clue: dict, rows, cols) -> None`
Clue sai (type lạ, thiếu trường, ô ngoài lưới, k ngoài `[0, |R|]`) → `ValueError`. Engine gọi cho mọi clue lúc khởi tạo.

### `build_kb(public_state) -> (clauses, vm, stats)`
- `clauses` = CNF mọi clue trong `revealed` + `[var]` / `[-var]` cho mỗi ô trong `verdicts`.
- `stats = {"primary": rows*cols, "aux": số biến phụ, "clauses": len(clauses)}`.
- Lúc đầu p3_01: clauses `[[4], [-1]]` (thứ tự không quan trọng), stats `{"primary": 9, "aux": 0, "clauses": 2}`.

## dpll.py (DPLL & Agent)

### `dpll_solve(clauses, n_vars, assumptions=None) -> (sat, model, stats)`
- Input: CNF, `n_vars` = số biến lớn nhất, `assumptions` = list literal coi như mệnh đề đơn tạm thời.
- **Không được sửa** list `clauses` truyền vào.
- Output:
  - `sat: bool`
  - `model: dict[int, bool]` gán **đủ** biến 1..n_vars nếu SAT, `None` nếu UNSAT.
  - `stats = {"decisions": int, "propagations": int, "backtracks": int, "time": float giây}`.
- Ví dụ: `dpll_solve([[1, 2], [-1, 2]], 2, [-2])` → `(False, None, {...})`.

## agent.py (DPLL & Agent)

### `LogicAgent.classify(public_state) -> dict[str, str] | "INCONSISTENT"`
- Output: chỉ các ô **chưa** có trong `verdicts`, key theo row-major, value `CRIMINAL` / `INNOCENT` / `UNKNOWN`. Nếu KB tự mâu thuẫn → chuỗi `"INCONSISTENT"`.
- Lúc đầu p3_01: `{"B1": "UNKNOWN", "C1": "UNKNOWN", "A2": "CRIMINAL", "B2": "UNKNOWN", ...}` (chỉ A2 bị ép).
- Cộng dồn số liệu vào `self.stats = {"sat_calls", "decisions", "propagations", "backtracks", "time"}`; `reset_stats()` đưa về 0.

### `LogicAgent.next_move(public_state) -> {"cell", "verdict"} | None`
Ô bị ép đầu tiên theo row-major, `None` nếu không còn ô nào bị ép. GUI dùng cho Auto Solve từng bước.

### `LogicAgent.hint(public_state) -> {"cell", "verdict", "because"} | None`
`because` = list ô có clue cần để suy ra (bỏ clue đó đi thì ô hết bị ép). Lúc đầu p3_01: `{"cell": "A2", "verdict": "CRIMINAL", "because": ["A1"]}`.

### `LogicAgent.solve(engine) -> SolveResult`
```python
{
  "status": "SOLVED" | "STUCK" | "INCONSISTENT",
  "steps": [
    {"step": 1, "active_clues": ["A1"], "sat_calls": 17,
     "cell": "A2", "verdict": "CRIMINAL", "result": "ACCEPTED",
     "revealed_clue": {"type": "EXACTLY", "k": 1, "region": {"kind": "col", "col": "A"}}},
    ...
  ],
  "kb_stats": {"primary": 9, "aux": 0, "clauses": ...},   # KB cuối cùng
  "stats": {"sat_calls", "decisions", "propagations", "backtracks", "time"},
}
```
- Mỗi bước: classify một lần, submit ô bị ép **đầu tiên** theo row-major (đúng như `next_move`). `sat_calls` của bước = 1 lần kiểm KB + 2 lần cho mỗi ô chưa chốt (bản tối ưu thì ít hơn).
- p3_01 giải theo thứ tự: A2 C, A3 I, C2 I, B2 C, C3 C, B1 I, C1 I, B3 I (8 bước), `status = "SOLVED"`.

### `check_unique(puzzle: Puzzle) -> bool`
Dùng mọi clue (kể cả thẻ chưa lật). `True` nếu đúng 1 model trên các biến chính. Chỉ dùng để kiểm puzzle, không dùng lúc chơi.

## gui/app.py (GUI & Video)

- `run(puzzle_path: str | None) -> None`: mở cửa sổ.
- `clue_to_text(clue, names: dict[str, str]) -> str`: `names` = `{cell: name}` lấy từ `public_state["cells"]`. Ví dụ `{"type":"EXACTLY","k":1,"region":{"kind":"col","col":"A"}}` → `"Exactly 1 criminal in column A"`.
- Highlight: `cells_in_clue(clue, rows, cols)`. Hint: `agent.hint(state)`. Auto Solve: lặp `agent.next_move(state)` → `engine.submit(...)` → vẽ lại → `root.after(400, ...)`.

## experiments/run.py (Lead)

Với mỗi `puzzles/*.json`: `load_puzzle` → `GameEngine` → `agent.reset_stats()` → `agent.solve(engine)` (có timeout) → một dòng CSV từ `SolveResult`:
`id, rows, cols, primary_vars, aux_vars, clauses, sat_calls, decisions, propagations, backtracks, steps, time, status`.
