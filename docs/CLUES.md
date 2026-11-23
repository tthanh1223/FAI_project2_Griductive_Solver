# Clue spec: định nghĩa, JSON, CNF, kiểm tra

File này là **nguồn chuẩn duy nhất** cho mọi thứ liên quan tới clue: vùng (region) gồm ô nào, clue nghĩa là gì, JSON viết sao, mã hoá CNF ra sao, validate gì, GUI hiển thị chữ gì.
Hàm và kiểu dữ liệu: [INTERFACES.md](INTERFACES.md). Có chỗ nào hai file nói khác nhau thì báo nhóm, sửa cho khớp trước khi code tiếp.

| Ai | Dùng phần nào |
|---|---|
| Engine & Puzzle (`model.py`) | §2 Vùng, §5 `cells_in_clue`, §7 viết puzzle |
| Encoder (`encoder.py`) | toàn bộ, nhất là §3 nghĩa, §4 CNF, §6 validate |
| DPLL & Agent | §4.4 biến phụ (để hiểu `kb_stats`) |
| Lead / GUI | §5, §8 chữ hiển thị |

---

## 1. Quy ước chung

- **Ô:** `"A1"` = cột A, hàng 1, **hàng 1 ở trên cùng**. Lưới `rows × cols`, cột A…, hàng 1…
- **Biến:** ô thứ i theo row-major (A1, B1, …, A2, …) là biến `i+1`. `True` = **tội phạm**. Biến phụ cấp từ `rows*cols + 1` qua `vm.new_aux()`.
- **Mọi danh sách ô** (kết quả vùng, `cells_in_clue`) theo **row-major**, không trùng.
- **`count`:** mọi clue đếm đều có trường tuỳ chọn `"count": "criminal"` (mặc định) hoặc `"innocent"`. Đếm vô tội = đếm literal `¬x` thay cho `x`.
- **Nguồn chuẩn của nghĩa là `evaluate_clue`** (§3). CNF (§4) phải cho đúng cùng kết quả trên **mọi** cách gán. Test §7 kiểm đúng điều này.

---

## 2. Vùng (region)

`region_cells(region, rows, cols)` trả về list ô theo row-major. `X` là một ô, `(r, c)` là hàng/cột của X (đếm từ 0).

| `kind` | JSON | Gồm ô nào | Ví dụ (lưới 4 cột × 5 hàng) |
|---|---|---|---|
| `row` | `{"kind":"row","row":3}` | cả hàng 3 | A3 B3 C3 D3 |
| `col` | `{"kind":"col","col":"B"}` | cả cột B | B1 … B5 |
| `neighbors` | `{"kind":"neighbors","of":"A4"}` | tối đa **8** ô quanh X (kể cả chéo), **không** gồm X | A3 B3 B4 A5 B5 |
| `cells` | `{"kind":"cells","cells":["A1","C3"]}` | đúng các ô liệt kê | A1 C3 |
| `all` | `{"kind":"all"}` | cả bảng | 20 ô |
| `edges` | `{"kind":"edges"}` | ô ở hàng đầu/cuối hoặc cột đầu/cuối | 14 ô |
| `corners` | `{"kind":"corners"}` | 4 góc | A1 D1 A5 D5 |
| `above` | `{"kind":"above","of":"D5"}` | cùng cột, hàng **nhỏ hơn** X (không gồm X) | D1 D2 D3 D4 |
| `below` | `{"kind":"below","of":"B2"}` | cùng cột, hàng lớn hơn | B3 B4 B5 |
| `left` | `{"kind":"left","of":"C1"}` | cùng hàng, cột nhỏ hơn | A1 B1 |
| `right` | `{"kind":"right","of":"A2"}` | cùng hàng, cột lớn hơn | B2 C2 D2 |
| `between` **(mới)** | `{"kind":"between","a":"A1","b":"D1"}` | các ô **nằm giữa** a và b trên cùng một hàng hoặc cột, **không** gồm a, b. a, b không cùng hàng/cột → lỗi | B1 C1 |
| `inter` | `{"kind":"inter","regions":[R1,R2,…]}` | giao của các vùng con (≥ 2 vùng, lồng nhau được) | between(B1,B5) ∩ neighbors(A4) = B3 B4 |

- Vùng **được phép rỗng** (vd `above` của ô hàng 1, `between` hai ô kề nhau). Clue đếm trên vùng rỗng chỉ đúng khi k = 0.
- "Hàng xóm của tôi" trong game = `neighbors` của **chính ô có clue đó**. JSON luôn ghi ô cụ thể, không có từ khoá "me".

---

## 3. Các loại clue và nghĩa

`a` là cách gán đầy đủ `{ô: bool}`, `n(R)` là số tội phạm (hoặc vô tội nếu `count: innocent`) trong vùng R.

| # | `type` | Trường | Đúng khi |
|---|---|---|---|
| C1 | `FACT` | `who`, `status` | `a[who] == (status == "CRIMINAL")` |
| C2 | `SAME` | `a`, `b` | `a[a] == a[b]` |
| C3 | `DIFFERENT` | `a`, `b` | `a[a] != a[b]` |
| C4 | `EXACTLY` | `k`, `region`, `count?` | `n(region) == k` |
| C5 | `AT_LEAST` | như trên | `n(region) >= k` |
| C6 | `AT_MOST` | như trên | `n(region) <= k` |
| E2 | `COMPARE` | `r1`, `op` (`>` `<` `=`), `r2`, `count?` | `n(r1) op n(r2)` |
| E3 | `AND` | `parts` (list clue, ≥ 1) | mọi clue con đúng |
| E5 | `CONNECTED` | `region`, `count?` | các ô được đếm trong vùng nằm **liền một dải** (0 hoặc 1 ô cũng tính là liền) |
| E6 | `NONE` | `text` | luôn đúng (clue trang trí) |
| E8 | `PARITY` **(mới)** | `parity` (`odd` / `even`), `region`, `count?` | `n(region) % 2 == 1` (odd) hoặc `== 0` (even) |
| E9 | `COUNT_LINES` **(mới)** | `axis` (`row` / `col`), `k`, `where` | đúng **k** hàng (hoặc cột) L thoả `where` khi gắn `region = L` |

Các mở rộng còn lại: E1 = các vùng ngoài `row/col/neighbors/cells` (§2), E4 = `count: innocent`, E7 = bộ đếm tuần tự (§4.4).

**`where` của `COUNT_LINES`** là một clue **không có `region`**, thuộc một trong các type `EXACTLY`, `AT_LEAST`, `AT_MOST`, `PARITY`, `CONNECTED` (có `count?` riêng). Ví dụ "Only one row has exactly one criminal":
```json
{"type": "COUNT_LINES", "axis": "row", "k": 1, "where": {"type": "EXACTLY", "k": 1}}
```

**Lưu ý COMPARE vô tội:** hai vùng khác cỡ thì "nhiều vô tội hơn" **không** bằng "ít tội phạm hơn". Phải đếm vô tội thật.

**Câu game → clue:** nhiều câu thật là ghép (AND) của 2 điều. Dịch theo bảng:

| Kiểu câu | JSON |
|---|---|
| "X is one of Y's 2 criminal neighbors" | AND(FACT X criminal, EXACTLY 2 neighbors(Y)) |
| "Both innocents in row 3 are connected" | AND(EXACTLY 2 innocent row 3, CONNECTED innocent row 3) |
| "All criminals above X are connected" | CONNECTED above(X) (không biết trước số lượng, **không** thêm EXACTLY) |
| "Only 1 of the 4 innocents neighboring X is in row 5" | AND(EXACTLY 4 innocent N(X), EXACTLY 1 innocent N(X) ∩ row 5) |
| "Exactly 2 innocents in between X and Y are neighboring Z" | EXACTLY 2 innocent (between(X,Y) ∩ N(Z)) |
| "Neither of the 2 innocents neighboring X are Y's neighbors" | AND(EXACTLY 2 innocent N(X), EXACTLY 0 innocent N(X) ∩ N(Y)) |
| "Row 1 has more criminals than any other row" | AND(COMPARE row1 > row2, row1 > row3, …) |
| "There's an odd number of innocents in between X and Y" | PARITY odd innocent between(X,Y) |
| "X and Y have an equal number of criminal neighbors" | COMPARE N(X) = N(Y) |

---

## 4. Mã hoá CNF

Ký hiệu: `x` = biến của ô; nếu `count: innocent` thì dùng `-x` ở mọi chỗ (gọi chung là literal đếm `ℓ`). `L = [ℓ1..ℓn]` là literal đếm của vùng theo row-major.

### 4.1 Clue cơ bản

| Clue | CNF |
|---|---|
| FACT | `[x]` (tội phạm) / `[-x]` (vô tội) |
| SAME | `[-a, b], [a, -b]` |
| DIFFERENT | `[a, b], [-a, -b]` |
| AT_MOST k | mọi tập con S ⊆ L cỡ k+1: `[-ℓ for ℓ in S]` |
| AT_LEAST k | k = 0: không sinh gì; ngược lại mọi tập con S cỡ n−k+1: `[ℓ for ℓ in S]` |
| EXACTLY k | AT_MOST k + AT_LEAST k |
| AND | nối CNF các clue con |
| NONE | `[]` |

Biên: k = 0 → mỗi ô một mệnh đề `[-ℓ]`; k = n → mỗi ô `[ℓ]`. Vùng rỗng, k = 0 → `[]`.

### 4.2 Bảng chân trị (COMPARE, PARITY)

Gọi U là các ô clue dùng tới (COMPARE: hợp r1 ∪ r2, row-major; PARITY: vùng). Với **mỗi** cách gán của U làm `evaluate_clue` **sai**, thêm một mệnh đề cấm đúng cách gán đó: `[-lit(u) for u in U]` với `lit(u) = x_u` nếu u đang là tội phạm, `-x_u` nếu vô tội.

- Ví dụ PARITY odd trên A1 B1 C1 (biến 1, 2, 3) cấm 4 cách gán chẵn: `[1,2,3], [1,-2,-3], [-1,2,-3], [-1,-2,3]`.
- Số mệnh đề ≤ 2^|U|. Giới hạn: **|U| ≤ 16** (validate báo lỗi nếu lớn hơn). Clue "hàng 1 nhiều hơn mọi hàng khác" phải tách thành AND các COMPARE 2 hàng.
- PARITY trên vùng rỗng: odd luôn sai, even luôn đúng. Validate **cấm** PARITY vùng rỗng, để không sinh mệnh đề rỗng.
- **Clue lớn (2^|U| > 2 000, tức |U| ≥ 11) không dùng bảng chân trị** (tới 65 536 mệnh đề, DPLL rất chậm) mà dùng biến phụ:
  - PARITY: chuỗi XOR trên các literal được đếm ℓ1..ℓn. t1 = ℓ1; với i = 2..n cấp `ti = vm.new_aux()`, ti ⇔ t(i−1) ⊕ ℓi: `[-ti, t, ℓ], [-ti, -t, -ℓ], [ti, -t, ℓ], [ti, t, -ℓ]` (t = t(i−1), ℓ = ℓi). Cuối cùng `[tn]` nếu odd, `[-tn]` nếu even.
  - COMPARE: ô nằm trong cả r1 lẫn r2 cộng như nhau vào hai vế nên bỏ đi. Với A = r1 \ r2, B = r2 \ r1 thì `n1 op n2` ⇔ `count(lit(A) + ¬lit(B)) op |B|`, tức `=` → EXACTLY |B|, `>` → AT_LEAST |B|+1, `<` → AT_MOST |B|−1 (§4.1, bộ đếm tuần tự §4.4 khi lớn). k ngoài [0, |A|+|B|] thì clue luôn sai: `[[x], [-x]]` với x là biến phụ mới.
  - Mọi ví dụ và số mệnh đề tham khảo ở §7.1 có |U| ≤ 10 nên vẫn dùng bảng chân trị, không đổi.

### 4.3 CONNECTED

Vùng phải là **một đoạn liền** của một hàng hoặc một cột (row, col, above/below/left/right, between, hoặc `cells`/`inter` mà kết quả là đoạn liền). Với mọi bộ ba vị trí `i < j < k` theo thứ tự trên đoạn: cấm "i có, j không, k có":
```
[-ℓi, ℓj, -ℓk]
```
Ví dụ CONNECTED innocent trên above(A5) = A1 A2 A3 A4: 4 mệnh đề, như `[x_A1, -x_A2, x_A3]`.

### 4.4 Biến phụ

**COUNT_LINES (E9), Tseitin.** Với mỗi hàng (cột) L, cấp biến phụ `r_L = vm.new_aux()` với ý nghĩa `r_L ⇔ where(L)`. Ràng buộc này mã hoá bằng bảng chân trị có điều kiện: với **mọi** cách gán β của các ô trong L
```
[-lit(u) for u in L] + ([r_L] nếu where(L) đúng dưới β, ngược lại [-r_L])
```
Sau đó thêm `EXACTLY k` (§4.1) trên các `r_L`. Số mệnh đề = Σ 2^|L| + phần EXACTLY. Bảng 4 cột × 5 hàng, `axis: row`: 5·16 + 11 = **91 mệnh đề, 5 biến phụ**. Giới hạn: mỗi đường ≤ 8 ô.

**Bộ đếm tuần tự (E7, Sinz 2005)** cho AT_MOST/AT_LEAST/EXACTLY khi **số tập con phải duyệt > 2 000** (vd "9 innocents in total" trên 20 ô). AT_MOST k trên ℓ1..ℓn (1 ≤ k < n), biến phụ `s[i][j]` = "trong ℓ1..ℓi đã có ≥ j cái đúng", i = 1..n−1, j = 1..k:
```
[-ℓ1, s[1][1]];   [-s[1][j]]  với j = 2..k
với i = 2..n-1:
  [-ℓi, s[i][1]];   [-s[i-1][1], s[i][1]]
  với j = 2..k: [-ℓi, -s[i-1][j-1], s[i][j]];   [-s[i-1][j], s[i][j]]
  [-ℓi, -s[i-1][k]]
[-ℓn, -s[n-1][k]]
```
AT_LEAST k trên L = AT_MOST (n−k) trên các literal phủ định. k = 0 hoặc k ≥ n thì dùng luật biên §4.1, không cấp biến phụ. Encoder phải cho **cùng** kết quả SAT/UNSAT với cách tổ hợp (test §7).

`build_kb` báo `aux = vm.next_aux - 1 - rows*cols`. Biến phụ **không** được dùng để quyết định ô: agent chỉ hỏi về biến chính.

---

## 5. `cells_in_clue` (cho GUI tô sáng, gạch clue, Hint)

= các ô **được nhắc tên** ∪ các ô **được đếm**, row-major, không trùng.

| Clue | Ô |
|---|---|
| FACT | `who` |
| SAME / DIFFERENT | `a`, `b` |
| EXACTLY / AT_LEAST / AT_MOST / PARITY / CONNECTED | các ô của vùng + ô mốc của vùng (`of`, `a`, `b`, kể cả trong `inter`) |
| COMPARE | như trên cho cả `r1`, `r2` |
| AND | hợp của các clue con |
| COUNT_LINES | cả bảng |
| NONE | `[]` |

Ví dụ: EXACTLY 2 innocent `inter(between(B1,B5), neighbors(A4))` → `B1, B3, A4, B4, B5` (mốc B1, B5, A4 + ô đếm B3, B4).

---

## 6. Validate (`validate_clue`, lỗi → `ValueError`)

Engine gọi cho mọi clue lúc tải puzzle, kể cả clue con trong AND và `where`.

- `type` nằm trong danh sách §3; đủ trường bắt buộc; không có trường lạ ngoài `count` (và `text` cho NONE).
- Mọi ô (`who`, `a`, `b`, `of`, `cells`) nằm trong lưới; `status` ∈ {CRIMINAL, INNOCENT}; `count` ∈ {criminal, innocent}.
- `kind` nằm trong §2; `inter` có ≥ 2 vùng; `between` thì a, b cùng hàng hoặc cùng cột và a ≠ b.
- Clue đếm: `0 ≤ k ≤ |vùng|`. COMPARE: `op` ∈ {`>`, `<`, `=`} và |r1 ∪ r2| ≤ 16.
- PARITY: `parity` ∈ {odd, even}, vùng **không rỗng**, |vùng| ≤ 16.
- CONNECTED: vùng là một đoạn liền của một hàng/cột (§4.3).
- AND: `parts` không rỗng.
- COUNT_LINES: `axis` ∈ {row, col}; `0 ≤ k ≤ số đường`; `where` không có `region`, type thuộc {EXACTLY, AT_LEAST, AT_MOST, PARITY, CONNECTED}; với `where` đếm thì `k_where` ≤ độ dài đường.

---

## 7. Test bắt buộc (`tests/test_clues.py`)

1. **Encoder ≡ evaluator, vét cạn 3×3:** với mỗi clue mẫu dưới đây và **mọi** 512 cách gán, `dpll_solve(encode_clue(clue), n_vars, lits(gán)) SAT` ⇔ `evaluate_clue(clue, gán) == True`.
   ```json
   {"type": "PARITY", "parity": "odd", "region": {"kind": "row", "row": 2}}
   {"type": "PARITY", "parity": "even", "count": "innocent", "region": {"kind": "neighbors", "of": "B2"}}
   {"type": "COUNT_LINES", "axis": "row", "k": 1, "where": {"type": "EXACTLY", "k": 1}}
   {"type": "COUNT_LINES", "axis": "col", "k": 0, "where": {"type": "AT_LEAST", "k": 2, "count": "innocent"}}
   {"type": "EXACTLY", "k": 1, "region": {"kind": "between", "a": "A2", "b": "C2"}}
   {"type": "CONNECTED", "count": "innocent", "region": {"kind": "col", "col": "B"}}
   {"type": "COMPARE", "r1": {"kind": "row", "row": 1}, "op": ">", "r2": {"kind": "row", "row": 3}, "count": "innocent"}
   ```
   cộng mọi clue trong `puzzles/p3_01.json`.
2. **Lưới 4×5:** mọi clue ở §7.1 bên dưới, 400 cách gán ngẫu nhiên (seed cố định), cùng điều kiện như trên.
3. **Bộ đếm tuần tự ≡ tổ hợp:** EXACTLY/AT_MOST/AT_LEAST trên vùng 5–6 ô, mọi k, ép dùng bộ đếm tuần tự rồi so với cách tổ hợp.
4. **Vùng:** từng dòng bảng §2 (cột "Ví dụ") là một assert.
5. **Validate:** mỗi gạch đầu dòng §6 có ít nhất một clue sai bị bắt.
6. **Mã hoá gọn ≡ evaluator:** PARITY và COMPARE ép dùng chuỗi XOR / bộ đếm (bỏ qua giới hạn 2 000), so với `evaluate_clue` trên mọi 512 cách gán 3×3; clue 16 ô trên 4×4 phải sinh ít mệnh đề và vẫn đúng.

### 7.1 Puzzle thật dùng làm test (cửa hàng nến, 4 cột × 5 hàng)

Đáp án: tội phạm = **A1 B1 D2 C3 D3 A5 B5**, còn lại vô tội. 10 clue logic dưới đây đều **đúng** trên đáp án này (đã kiểm). Các ô còn lại là clue trang trí (`NONE`).

| Ô | Câu | JSON |
|---|---|---|
| D1 | Quilla and Roy have an equal number of criminal neighbors | `{"type":"COMPARE","r1":{"kind":"neighbors","of":"A5"},"op":"=","r2":{"kind":"neighbors","of":"B5"}}` |
| B2 | Both innocents in row 3 are connected | `{"type":"AND","parts":[{"type":"EXACTLY","k":2,"count":"innocent","region":{"kind":"row","row":3}},{"type":"CONNECTED","count":"innocent","region":{"kind":"row","row":3}}]}` |
| C2 | Only 1 of the 4 innocents neighboring Senna is in row 5 | `{"type":"AND","parts":[{"type":"EXACTLY","k":4,"count":"innocent","region":{"kind":"neighbors","of":"C5"}},{"type":"EXACTLY","k":1,"count":"innocent","region":{"kind":"inter","regions":[{"kind":"neighbors","of":"C5"},{"kind":"row","row":5}]}}]}` |
| C3 | There's an odd number of innocents in between Abel and Dora | `{"type":"PARITY","parity":"odd","count":"innocent","region":{"kind":"between","a":"A1","b":"D1"}}` |
| A4 | Only one row has exactly one criminal | `{"type":"COUNT_LINES","axis":"row","k":1,"where":{"type":"EXACTLY","k":1}}` |
| B4 | Both innocents to the right of Enzo are connected | `{"type":"AND","parts":[{"type":"EXACTLY","k":2,"count":"innocent","region":{"kind":"right","of":"A2"}},{"type":"CONNECTED","count":"innocent","region":{"kind":"right","of":"A2"}}]}` |
| D4 | Hazel is one of 2 criminals above Theo | `{"type":"AND","parts":[{"type":"FACT","who":"D2","status":"CRIMINAL"},{"type":"EXACTLY","k":2,"region":{"kind":"above","of":"D5"}}]}` |
| A5 | Exactly 2 innocents in between Bella and Roy are neighboring Mona | `{"type":"EXACTLY","k":2,"count":"innocent","region":{"kind":"inter","regions":[{"kind":"between","a":"B1","b":"B5"},{"kind":"neighbors","of":"A4"}]}}` |
| B5 | All innocents above Quilla are connected | `{"type":"CONNECTED","count":"innocent","region":{"kind":"above","of":"A5"}}` |
| C5 | Abel has more criminal neighbors than Ivy | `{"type":"COMPARE","r1":{"kind":"neighbors","of":"A1"},"op":">","r2":{"kind":"neighbors","of":"A3"}}` |

Tên: A1 Abel, B1 Bella, C1 Clara, D1 Dora, A2 Enzo, B2 Fern, C2 Grant, D2 Hazel, A3 Ivy, B3 Jonas, C3 Karl, D3 Lucy, A4 Mona, B4 Noah, C4 Otis, D4 Piper, A5 Quilla, B5 Roy, C5 Senna, D5 Theo.
Chỉ riêng 10 clue logic thì còn 4 lời giải. Puzzle gốc còn có thẻ lật sẵn (chưa biết là thẻ nào), nên khi làm thành `puzzles/*.json` phải chọn `revealed` sao cho `check_unique` trả về `True`.

Số mệnh đề tham khảo (để so khi debug): D1 48 · B2 12 · C2 13 · C3 2 · A4 91 (+5 biến phụ) · B4 5 · D4 9 · A5 2 · B5 4 · C5 60.

---

## 8. Chữ hiển thị (`clue_to_text`, GUI)

Viết theo giọng game, tiếng Anh. `{X}` = tên người ở ô X; `{who}` = "criminal(s)" hoặc "innocent(s)" theo `count` và số ít/nhiều; `{R}` = mô tả vùng.

| Clue | Mẫu |
|---|---|
| FACT | `{who} is {criminal/innocent}` |
| SAME / DIFFERENT | `{a} and {b} are on the same side` / `{a} and {b} are on different sides` |
| EXACTLY / AT_LEAST / AT_MOST | `Exactly / At least / At most {k} {who} {R}` |
| COMPARE | `{R1} has more / fewer / the same number of {who} as {R2}` (N(X) = N(Y) → `{X} and {Y} have an equal number of {who} neighbors`) |
| CONNECTED | `All {who} {R} are connected` |
| PARITY | `There's an odd / even number of {who} {R}` |
| COUNT_LINES | `Exactly {k} rows / columns have {where viết không có vùng}`; k = 1 → `Only one row has …` |
| AND | các phần nối bằng `, and ` |
| NONE | `text` nguyên văn |

| Vùng | `{R}` |
|---|---|
| row / col | `in row 3` / `in column B` |
| neighbors | `neighboring {X}` |
| all / edges / corners | `in total` / `on the edges` / `in the corners` |
| above / below / left / right | `above {X}` / `below {X}` / `to the left of {X}` / `to the right of {X}` |
| between | `in between {a} and {b}` |
| cells | `among {X}, {Y} and {Z}` |
| inter | các vùng con nối bằng ` and ` (vd `in between Bella and Roy and neighboring Mona`) |

Câu không cần khớp từng chữ với game. Yêu cầu chỉ là **đọc lên đúng nghĩa của JSON**.
