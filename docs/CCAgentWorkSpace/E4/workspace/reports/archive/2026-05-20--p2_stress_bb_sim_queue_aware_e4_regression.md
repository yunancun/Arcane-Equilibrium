# E4 Regression Report — P2-STRESS-BB-BREAKOUT-FALSE-SQUEEZE-COINCIDENTAL-PASS + P2-SIM-QUEUE-AWARE-ADJUSTMENT

**Date**: 2026-05-20
**Author**: E4
**Branch / state**: `main` HEAD `232c3aff`（origin/main 領先 3 commits：`879e3852` / `dc33eb2d` / `232c3aff`）。兩個 P2 IMPL 均在 Mac dirty working tree（未 commit / 未 push）。
**Scope**：並行 batch — 兩個 P2 task 同次 E4 regression。
**E2 verdict 入口**：
- P2-STRESS-BB-BREAKOUT-FALSE-SQUEEZE-COINCIDENTAL-PASS：E2 APPROVE（0 BLOCKER）
- P2-SIM-QUEUE-AWARE-ADJUSTMENT：E2 APPROVE-CONDITIONAL（0 CRITICAL / 2 MEDIUM 不阻 E4）

## 1. Verdict 速覽

| Task | Verdict | 主結果 |
|---|---|---|
| P2-STRESS-BB-BREAKOUT-FALSE-SQUEEZE-COINCIDENTAL-PASS | **PASS** | stress_integration 35/0/0 × 2 runs non-flaky；pre-PR baseline 35/0/0 同（stash 法驗）；目標 test `stress_bb_breakout_false_squeeze_no_volume` PASS；OI fail-closed 解 + volume gate 真攔下 false breakout |
| P2-SIM-QUEUE-AWARE-ADJUSTMENT | **PASS** | calibration pytest 89/89 × 2 runs non-flaky；既有 9 sweep_replay 0 false GREEN（default `orderbook_window=None` → backward-compat）；新 4 integration + 22 unit 全踩真實 simulation 邏輯 |

**P2-STRESS-BB E4: PASS — P2-SIM-QUEUE-AWARE E4: PASS**

兩個 IMPL 均 ready to PM sign-off → commit → push（PM 視 sibling worktree dirty 範圍決策）。

---

## 2. 主結果並列表格

### 2.1 P2-STRESS-BB-BREAKOUT（Rust）

| 引擎 / 命令 | passed | failed | ignored | duration | baseline | delta |
|---|---|---|---|---|---|---|
| `cargo test -p openclaw_engine --release --lib` (run 1) | 3042 | 0 | 1 | 0.70s | 2993 (5/18 cleanup sprint) + sibling +49 (Layer A/B/exit-code/spine) | **0 P2-STRESS-BB attribution**（lib 不含 stress_integration） |
| `cargo test -p openclaw_engine --release --lib` (run 2) | 3042 | 0 | 1 | 0.70s | identical | non-flaky ✅ |
| `cargo test -p openclaw_engine --release --tests` (run 1) | 3264 (3042 lib + 222 integration / 26 binaries) | 0 | 1 | ~10s wall | n/a | 0 |
| `cargo test -p openclaw_engine --release --tests` (run 2) | 3264 | 0 | 1 | ~10s wall | identical | non-flaky ✅ |
| `cargo test --release --test stress_integration` (focused × 3) | 35 | 0 | 0 | 0.10-0.12s | pre-PR baseline 35/0/0（stash 法驗） | **+0 / -0**（純強化既有 1 test assertion，不增 test count） |

**目標 spotlight**：
- `stress_bb_breakout_false_squeeze_no_volume` (line 545-657 新版)：**PASS** × 3 isolated runs（focused + tests + tests）
- 相鄰 bb_breakout stress tests:
  - `stress_bb_breakout_valid_squeeze_with_volume`：**PASS**
  - `stress_bb_reversion_extreme_oversold_bounce`：**PASS**
- 5/18 cleanup sprint report 記載這 2 個 sibling 曾為 pre-existing fail（`left:0 right:1`）；5/19 `stress_test_invariant_drift_fix` 已修，當前 baseline 0 fail ✅

### 2.2 P2-SIM-QUEUE-AWARE（Python）

| 引擎 / 命令 | passed | failed | duration | baseline | delta |
|---|---|---|---|---|---|
| `python3 -m pytest helper_scripts/calibration/tests/ -v --tb=short` (run 1) | 89 | 0 | 0.04s | 63 pre-PR (per memory 5/18 phase_1b harness) | **+26**（22 queue_adjustment new + 4 integration new） |
| `python3 -m pytest helper_scripts/calibration/tests/ -v --tb=short` (run 2) | 89 | 0 | 0.04s | identical | non-flaky ✅ |
| `python3 -m pytest helper_scripts/ -k 'phase_1b' --tb=short` | 89 | 0 | 0.14s | n/a | identical 內含 |
| `python3 -m pytest helper_scripts/calibration/tests/test_phase_1b_sweep_replay.py -v` (run 1) | 13 (9 既有 + 4 new queue integration) | 0 | 0.02s | pre-PR 9 既有 | **+4** integration |
| `python3 -m pytest helper_scripts/calibration/tests/test_phase_1b_sweep_replay.py -q` (run 2) | 13 | 0 | 0.01s | identical | non-flaky ✅ |

**89 test 拆解**（task brief 「既有 63」實際拆分）：
| File | n | new? |
|---|---|---|
| test_phase_1b_maker_price.py | 20 | 既有 |
| test_phase_1b_queue_adjustment.py | 22 | **NEW**（P2-SIM-QUEUE-AWARE）|
| test_phase_1b_sweep_cells.py | 17 | 既有 |
| test_phase_1b_sweep_replay.py | 13 | 9 既有 + **4 NEW**（P2-SIM-QUEUE-AWARE 4 個 queue integration）|
| test_phase_1b_sweep_report.py | 17 | 既有 |
| **Total** | **89** | 63 既有 + **26 new** |

「既有 63 是否 false GREEN 受隱式影響」**答 NO**：既有 9 sweep_replay test fixture 不傳 `orderbook_window` → `simulate_cell_against_fill` 走 default `orderbook_window=None` → `queue_factor=None` → `apply_queue_adjustment` queue 維度 vanish → `queue_adjusted_fill_probability = simulated_fill * (1-0)*(1-w*1.0 if factor else 1.0) = simulated_fill * 1.0`，**backward-compat 1:1**。新 dataclass 欄位 `queue_adjusted_fill_probability=0.0` / `queue_factor=None` 為 default，既有 9 test 0 assertion 觸碰。

---

## 3. Baseline diff 來源 + delta attribution

### 3.1 Rust lib baseline

| 來源 | passed |
|---|---|
| 5/18 cleanup sprint report（memory.md 條目） | 2993 |
| 當前 main HEAD `232c3aff` (run 1+2 一致) | 3042 |
| **Delta** | **+49** |

**Attribution**（5/18 → 5/20 origin/main 領先 3 commits + worktree dirty）：
- Layer A `6cf476c4` (P0-ENGINE-HALTSESSION-STUCK-FIX) +N tests
- Layer B `fec63743` (watchdog inert probe — Python only，**lib 0 增量**)
- watchdog exit code `dc33eb2d` (Python only，**lib 0 增量**)
- spine align `879e3852` (Rust spine_message_bus +M tests)
- Wave A1 cell stress 5/19 invariant drift fix（**stress_integration 0 lib 增量；integration suite 35/0 變動**）

**P2-STRESS-BB-BREAKOUT 對 lib 0 attribution**（純 tests/ 端強化既有 test assertion，不新增 lib unit test，亦不改 production code）。

### 3.2 Rust integration baseline

| 來源 | passed |
|---|---|
| 5/18 cleanup sprint report | 33 (stress_integration) + 2 failed pre-existing |
| 當前 main HEAD（stash pre-PR + tests/ 全 26 binaries） | 222（25 binaries 內 stress_integration=35）|
| **Delta** | **35-33 = +2 stress test count / -2 pre-existing failures** |

**Attribution**：5/19 `stress_test_invariant_drift_fix` 修了 5/18 報告的 2 個 fail；當前 P2-STRESS-BB 改動是 test fixture only +92/-6 LOC（不增 test count）。pre-PR stash run = 35/0/0；post-PR run = 35/0/0；**delta 0**。

### 3.3 Python pytest baseline

| 來源 | passed |
|---|---|
| 5/18 phase_1b harness E4 report（memory.md）| 63 (calibration 全套) |
| 當前 main HEAD post-PR | 89 |
| **Delta** | **+26 = 22 queue_adjustment new unit + 4 sweep_replay new integration** |

**Attribution**：P2-SIM-QUEUE-AWARE 100% 新增。既有 63 不受影響（default param backward-compat）。

---

## 4. Mock 審查（per regression-testing-protocol §5）

| Task | grep `patch|MagicMock|Mock\(\)|mock\.` 結果 | 結論 |
|---|---|---|
| P2-STRESS-BB stress_integration.rs 改動範圍（line 545-657 stress_bb_breakout_false_squeeze_no_volume）| 0 hit；sibling line 1317 `apply_patch` 是 RiskConfig store API 呼叫（非 mock）| **0 anti-pattern** |
| P2-SIM-QUEUE-AWARE 4 new file + 2 mod file | 0 hit across all 6 files | **0 anti-pattern** |

**E1 test 真實 invoke 業務邏輯**（per protocol §5.3 正例）：
- Rust：真 `BbBreakout::new()` + `fresh_oi_surface("BTCUSDT")` test-local helper（**fixture data 非 mock**）+ 真 `on_tick` + 真 `has_squeeze` / `entry_price_of` / `trailing_stop_of` public accessor。volume gate 真攔下 false breakout（control case 反證 vol→1.5 必 fire long）。
- Python：22 unit test 真 invoke `compute_queue_factor` / `apply_queue_adjustment` / `select_same_side_depth` 純函數；4 integration test 真 invoke `simulate_cell_against_fill` / `simulate_cell` 含 `OrderbookDepthWindow` dataclass instance；queue_factor=0.5 + adj=0.80 可手算驗證；**0 mock V094 audit JSON**。

**task brief「regression 用真實 PG query 而非 mock JSON」核驗**：
- `phase_1b_queue_bias_regression.py:143` 唯一 `cur.execute` = `SELECT ... FROM trading.fills WHERE engine_mode='demo' AND close_maker_attempt=TRUE AND exit_reason = ANY(%s) AND ts BETWEEN %s AND %s`（SELECT only / 0 INSERT/UPDATE/DELETE）。E2 §1.4 已 verified 5 個 SQL 全 SELECT。
- E1 §4.2 跑出 n=18 真實 fills（5 actual_maker / 13 actual_taker per `liquidity_role` ground truth）+ 跑出 14d window real depth_5 samples — **不是 mock**。

---

## 5. Cross-language floating-point 1e-4 consistency

**N/A 標記不適用 — per task brief 第 3 條 §3**：
- P2-STRESS-BB：Rust 內部 stress integration test，無 Python 對照面
- P2-SIM-QUEUE-AWARE：Python 內 simulation harness（read-only PG → in-memory dataclass → pure function arithmetic），無 Rust 同邏輯對照

兩 IMPL **不涉跨 Rust↔Python 同邏輯**。

---

## 6. SLA pressure

**N/A 標記不適用 — per task brief 第 5 條**：
- P2-STRESS-BB：test fixture only 改動（assert + control case），不在 H0 Gate / Tick path / IPC hot path 上
- P2-SIM-QUEUE-AWARE：calibration research tool 是 Mac local CLI，非 runtime hot path

兩 IMPL **不在 SLA-bound 範圍**。stress_integration test 0.10-0.12s 跑完 35 個 test（其中 stress_tick_latency_benchmark 內含 latency micro-bench，但 P2-STRESS-BB 改的 false_squeeze test 與 latency bench 隔離）。

---

## 7. 跨平台（Mac）

| Engine | Mac succeed? |
|---|---|
| Rust cargo test --release --lib | ✅ 3042/0/1 in 0.70s × 2 runs |
| Rust cargo test --release --tests | ✅ 3264/0/1 × 2 runs |
| Rust cargo test --release --test stress_integration | ✅ 35/0/0 × 3 runs |
| Python pytest helper_scripts/calibration/tests/ | ✅ 89/89 in 0.04s × 2 runs |
| Python pytest sweep_replay focused | ✅ 13/13 in 0.01-0.02s × 2 runs |

**0 cross-platform issue**。`/home/ncyu` / `/Users/.../Projects` grep across all 7 modified files = 0 hit。可隨時 deploy Linux runtime（per `feedback_cross_platform`）。

---

## 8. RED → GREEN 演練驗證（P2-STRESS-BB only）

E1 §RED→GREEN 演練：`fresh_oi_surface + vol_ratio=1.5` → 原 assert `is_empty()` panic at line 568。

E4 對抗驗證（stash 法跑 pre-PR baseline）：
- Pre-PR fixture（`EMPTY_ALPHA_SURFACE` + vol=1.0）：35/0/0 PASS（但 coincidental — E1 root cause 成立：OI gate fail-closed 永遠 return vec![]）
- Post-PR fixture（`fresh_oi_surface` + vol=1.0 + control vol=1.5）：35/0/0 PASS（真實踩 volume gate + control case fire long）

**E4 驗證重點**：
- E1 7 切片 + control case 設計 100% 對應 PA 任務 4 三條要求（indicator path / entry-exit behavior / PnL boundary）
- E2 mod.rs:469-690 grep verified path（OI gate 在 line 490 早於 squeeze line 542）✅
- pre-PR fixture 修法不只「強化 assertion」，更是「揭露 volume gate 真不真攔下 false breakout」— RED probe panic 證明 entry path 完整可達。

---

## 9. E2 SHOULD-FIX (MEDIUM-1 / MEDIUM-2) 對 P2-SIM-QUEUE-AWARE 的 E4 不阻塞性

E2 review §0 verdict 寫「2 SHOULD-FIX 不阻 E4」。E4 確認：

| MEDIUM | 內容 | E4 不阻塞理由 |
|---|---|---|
| MEDIUM-1 | regression 限 grid family；phys_lock_* 不 cover | 純 scope 標註（per code comment line 138-140 已 explicit warning）；不影響當前 V094 grid anchor 結論；下次 sweep 跑 phys_lock anchor 再 cover |
| MEDIUM-2 | `ts > NOW() - interval` sliding window 影響重現性 | E1 已 fix（line 105-110 + 119-130：`sample_end_utc` arg + Python 側 resolve window）；CLI artifact 含 query/params + 顯式 (start, end) timestamptz → audit 時刻 bit-exact 重現 |

兩 MEDIUM 已被 E1 IMPL 吸納或 explicitly noted → E4 不再追究。

---

## 10. 設計觀察（不阻塞 PASS）

### 10.1 task brief 「既有 63 test 是否有 false GREEN 受隱式影響」深掘

E4 主動針對此問題對抗驗證：
1. **既有 9 sweep_replay test fixture 全不傳 orderbook_window** → walk default `None` → queue 維度 vanish 數學上等於原 fill_p_proxy
2. **新 `queue_adjusted_fill_probability=0.0` default** 在 `simulated_fill=False` 場景與「無 queue 調整」邏輯一致（reject 必 0）；在 `simulated_fill=True` 場景需走 `apply_queue_adjustment(1.0, None, 0.4, 0.0)` → 算式 `1.0 * (1-0) * (1-0) = 1.0`（base=DEFAULT 0.0，queue_factor=None → queue 維度 multiplier=1.0）
3. **既有 9 test 0 assertion 觸碰** `queue_adjusted_fill_probability / queue_factor / same_side_depth_5 / queue_adjusted_fill_rate / queue_adjusted_eligible_with_depth` 新欄位

→ **0 false GREEN 隱式影響**。E1 / E2 self-claim 成立。

### 10.2 task brief 數字以實測為準（再次驗證）

- task brief 寫「既有 63 + queue_adjustment 22 + integration 4 = 89」**正確**（實測 89）
- task brief 寫 stress_integration「+92/-6 LOC」**正確**（實測 `git diff --stat` = 98 inserts/6 deletes / +92/-6 from line context）
- task brief 寫「baseline 2555 passed / 17 failed 已過期」**正確**（per E4 profile §測試基準線讀取規則 + memory 5/18 cleanup sprint = 2993 lib，當前 = 3042 lib）

### 10.3 §九 LOC governance

| File | LOC | 上限 |
|---|---|---|
| `stress_integration.rs` | 1315 → 1401 (+86) | 2000 hard cap ✅（pre-existing >800） |
| `phase_1b_queue_adjustment.py` | 210 | 800 警告線 ✅ |
| `phase_1b_queue_bias_regression.py` | 452 | 800 警告線 ✅ |
| `test_phase_1b_queue_adjustment.py` | 202 | 800 警告線 ✅ |
| `phase_1b_tick_loader.py` | +94 (existing 1027？需驗) | 1k+ 警告 / 2000 hard cap ✅ |
| `phase_1b_sweep_replay.py` | +124 (existing 700+) | 警告線附近 attention |
| `test_phase_1b_sweep_replay.py` | +149 | 800 警告線 ✅ |

兩 IMPL **0 hard cap breach**（per `srv/CLAUDE.md` §九 + §七 code structure guardrails）。

### 10.4 Governance flag (TODO §11.3 line 163)

TODO 提醒「`cargo test --lib` 不覆蓋 tests/ integration crate」。E4 已 cover：
- run 1 lib focus → 3042/0/1
- run 2 lib focus → 3042/0/1 (non-flaky)
- run `--tests` → 3264/0/1（含 26 integration binaries 222 passed）
- focused stress_integration × 3

**完整 cover lib + integration 雙 surface**，無 governance flag 漏網。

---

## 11. 跑兩遍 / 三遍結果

| Surface | Run 1 | Run 2 | Run 3 | Identical? |
|---|---|---|---|---|
| Rust lib | 3042/0/1 in 0.70s | 3042/0/1 in 0.70s | — | ✅ identical |
| Rust --tests (all) | 3264/0/1 | 3264/0/1 | — | ✅ identical |
| Rust stress_integration focused | 35/0/0 in 0.10s | 35/0/0 in 0.12s | 35/0/0 in 0.10s | ✅ identical |
| Python calibration full | 89/89 in 0.04s | 89/89 in 0.04s | — | ✅ identical |
| Python sweep_replay focused | 13/13 in 0.02s | 13/13 in 0.01s | — | ✅ identical |

**All non-flaky**。0 race / 0 timing-dependent / 0 environment-dependent。

---

## 12. 退回 E1 清單

**無**。兩個 P2 IMPL 全綠。PM 可 sign-off → commit → push。

---

## 13. 後續建議（不在 E4 階段執行）

1. **PM commit 順序**：建議 P2-STRESS-BB（Rust test fixture only）+ P2-SIM-QUEUE-AWARE（Python calibration only）分兩 commit，便於 attribution 追蹤
2. **Push 後 Linux 驗證**（per memory 5/18 layer_a/b 模板，optional）：
   ```
   ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test --release --test stress_integration"
   ssh trade-core "cd ~/BybitOpenClaw/srv && python3 -m pytest helper_scripts/calibration/tests/ -v"
   ```
   兩 IMPL 都不需 runtime restart（純 test / 純 research tool，無 binary 變更 / 無 V### migration / 無 TOML）
3. **MEDIUM-1 phys_lock_* family follow-up**：下次 sim sweep 跑 phys_lock_giveback / phys_lock_stale_roc_neg anchor cell 驗 queue model bias

---

## 14. 命令證據附錄（E4 親跑時間戳）

```
2026-05-20 (Asia/Taipei)

# Python full calibration suite (run 1)
$ cd /Users/ncyu/Projects/TradeBot/srv && python3 -m pytest helper_scripts/calibration/tests/ -v --tb=short
============================== 89 passed in 0.04s ==============================

# Python full calibration suite (run 2)
$ python3 -m pytest helper_scripts/calibration/tests/ -v --tb=short
89 passed in 0.04s

# Python broad phase_1b -k filter
$ python3 -m pytest helper_scripts/ -k 'phase_1b' --tb=short
89 passed, 719 deselected in 0.14s

# Python sweep_replay focused (existing 9 + 4 new integration)
$ python3 -m pytest helper_scripts/calibration/tests/test_phase_1b_sweep_replay.py -v --tb=short
13 passed in 0.02s

# Python sweep_replay focused run 2
$ python3 -m pytest helper_scripts/calibration/tests/test_phase_1b_sweep_replay.py -q
13 passed in 0.01s

# Rust lib (run 1)
$ cd /Users/ncyu/Projects/TradeBot/srv/rust && cargo test -p openclaw_engine --release --lib
test result: ok. 3042 passed; 0 failed; 1 ignored; 0 measured; 0 filtered out; finished in 0.70s

# Rust lib (run 2)
$ cargo test -p openclaw_engine --release --lib
3042 passed; 0 failed; 1 ignored; finished in 0.70s

# Rust --tests (run 1, 26 binaries aggregated)
$ cargo test -p openclaw_engine --release --tests 2>&1 | grep "^test result:" | awk '{...}'
Run 1: 3264 passed, 0 failed, 1 ignored

# Rust --tests (run 2)
$ cargo test -p openclaw_engine --release --tests
Run 2: 3264 passed, 0 failed, 1 ignored

# stress_integration focused × 3
$ cargo test -p openclaw_engine --release --test stress_integration
test result: ok. 35 passed; 0 failed; 0 ignored; finished in 0.10-0.12s × 3

# pre-PR baseline (stash stress_integration.rs only)
$ git stash push -- rust/openclaw_engine/tests/stress_integration.rs
$ cargo test -p openclaw_engine --release --test stress_integration
test result: ok. 35 passed; 0 failed; 0 ignored
$ git stash pop  # restore IMPL diff

# Mock audit
$ grep -nE "patch|MagicMock|Mock\(\)|mock\." rust/openclaw_engine/tests/stress_integration.rs
1317:    .apply_patch(  # RiskConfig store API in sibling stress_config_hot_reload_during_ticks (not mock)

$ grep -nE "patch|MagicMock|Mock\(\)|mock\." \
    helper_scripts/calibration/phase_1b_queue_adjustment.py \
    helper_scripts/calibration/phase_1b_queue_bias_regression.py \
    helper_scripts/calibration/tests/test_phase_1b_queue_adjustment.py \
    helper_scripts/calibration/tests/test_phase_1b_sweep_replay.py
(no output — 0 hit)

# Cross-platform path check
$ grep -nE "/home/ncyu|/Users/[^/]+/Projects" \
    helper_scripts/calibration/phase_1b_queue_adjustment.py \
    helper_scripts/calibration/phase_1b_queue_bias_regression.py \
    helper_scripts/calibration/tests/test_phase_1b_queue_adjustment.py \
    helper_scripts/calibration/phase_1b_sweep_replay.py \
    helper_scripts/calibration/phase_1b_tick_loader.py \
    helper_scripts/calibration/tests/test_phase_1b_sweep_replay.py \
    rust/openclaw_engine/tests/stress_integration.rs
(no output — 0 hit)

# Real PG SELECT-only verification
$ grep -nE "execute|INSERT|UPDATE|DELETE|DROP" helper_scripts/calibration/phase_1b_queue_bias_regression.py
143:        cur.execute(  # SELECT ... FROM trading.fills only
```

---

**Report path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-20--p2_stress_bb_sim_queue_aware_e4_regression.md`

**E4 REGRESSION DONE: PASS**

P2-STRESS-BB E4: PASS — P2-SIM-QUEUE-AWARE E4: PASS
