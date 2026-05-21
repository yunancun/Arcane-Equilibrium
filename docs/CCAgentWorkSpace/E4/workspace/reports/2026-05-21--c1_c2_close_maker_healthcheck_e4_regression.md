# E4 Regression Report — C1+C2 close_maker healthcheck · 2026-05-21

## 範圍

E2 R2 APPROVE-CONDITIONAL（2026-05-21 11:31 cfb9d243）後 light regression。

改動 5 files（純 Python read-only SQL healthcheck）：
- 新檔 `helper_scripts/canary/healthchecks/66_close_maker_pre_stopout_rate.py` (392 行)
- 改 `helper_scripts/canary/healthchecks/62_close_maker_fill_rate.py` (336 行，+ `--stratify` flag)
- 改 `helper_scripts/canary/healthchecks/__init__.py` (39 行，補 [66] 入口 + slot 邊界段)
- 新檔 `helper_scripts/canary/healthchecks/tests/test_66_pre_stopout_rate.py` (301 行)
- 改 `helper_scripts/canary/healthchecks/tests/conftest.py` (104 行，hc71 → hc66 + new fixture)

未動：`_common.py` / production Rust / IPC / GUI。

E4 範圍：light（純 Python pytest + cross-module不破 + grep + 規範驗證 + mock 真實性 spot check）。Rust regression + Linux PG empirical 不在 scope。

HEAD = cfb9d243（與 E2 R2 對齊；0 sibling push）。

---

## VERDICT: **PASS**

- pytest 83/83 PASS（healthchecks/tests/ scope）
- cross-module canary/ 201/201 PASS（不破）
- passive_wait [71] `test_close_maker_audit_healthcheck.py` 8/8 + 14 subtests PASS（cross-namespace 不擾）
- grep 0 leftover active `[71]` / `hc71` / `71_close_maker_pre_stopout` 編號
- 規範全綠（file size / emoji / cross-platform path / argparse）
- mock 真實性 4-spot 全 OK（無 fake-success / 無 self-consistent mock 過頭）
- 兩遍跑同綠（non-flaky）

可進 PM commit + push。

---

## Verify Step 詳結果

### Step 1 — Full pytest healthchecks/tests/

```bash
$ python3 -m pytest helper_scripts/canary/healthchecks/tests/ -v --tb=short
# 1st run
============================== 83 passed in 0.04s ==============================
# 2nd run
============================== 83 passed in 0.03s ==============================
```

| 引擎 | passed | failed | baseline | delta |
|---|---|---|---|---|
| Python pytest (healthchecks/tests/) 1st | 83 | 0 | 83 (E2 R2 自跑) | 0 |
| Python pytest (healthchecks/tests/) 2nd | 83 | 0 | 83 | 0 |

新加測（test_66 11 + test_62 stratify 12）已隨 E2 R2 一起綠。Flaky=N。

**file 分布（83/83）**：
- test_62_fill_rate.py: 19 tests（含 12 新 stratify tests）
- test_63_fallback_audit.py: 5 tests
- test_64_rate_limit.py: 5 tests
- test_65_reject_sample.py: 6 tests
- test_66_pre_stopout_rate.py: 11 tests（新檔）
- test_67_pulse_freshness.py: 15 tests
- test_common.py: 22 tests

### Step 2 — Cross-module pytest 不破

```bash
$ python3 -m pytest helper_scripts/canary/ -q --tb=short
# 1st run
201 passed in 31.77s
# 2nd run
201 passed in 31.21s
```

```bash
$ python3 -m pytest helper_scripts/db/test_close_maker_audit_healthcheck.py -q --tb=short
# 1st & 2nd
8 passed, 14 subtests passed in 0.03s
```

**重點 case — passive_wait [71] zero_spine_lineage**:
`test_zero_spine_lineage_guard` PASS（cross-namespace 不擾，[66] 不污染 [71]）。

`passive_wait_healthcheck/` 子目錄本身無 test（測試集中放 `helper_scripts/db/`）。

### Step 3 — Syntax / import / argparse

| Check | Result |
|---|---|
| `python3 -c "import helper_scripts.canary.healthchecks"` | `module import OK` ✓ |
| `python3 66_close_maker_pre_stopout_rate.py --help` | exit 0 ✓ |
| `python3 62_close_maker_fill_rate.py --help` | exit 0 ✓（含 `--stratify {none,hour,dow,both}` 選項）|
| `python3 62_close_maker_fill_rate.py --stratify hour --help` | exit 0 ✓ |
| `_STRATIFY_CHOICES` 動態 introspection | `('none', 'hour', 'dow', 'both')` ✓ |

[66] argparse 所有自訂 flag 全展現：`--pass-upper 0.10` / `--fail-upper 0.30` / `--min-sample 30` / `--stopout-patterns CSV`。

### Step 4 — 跨檔 grep verify

```bash
# [71] 在 canary/healthchecks/ 應 0 active hit
$ grep -rn "\[71\]" helper_scripts/canary/healthchecks/ | grep -v __pycache__
helper_scripts/canary/healthchecks/__init__.py:12 ... [70][71][72][73][74] slot) 關係：
helper_scripts/canary/healthchecks/__init__.py:22 ... passive_wait_healthcheck/：[70][71][72][73][74]
helper_scripts/canary/healthchecks/__init__.py:37 ... R2 從 [71] rename 避碰）
helper_scripts/canary/healthchecks/66_close_maker_pre_stopout_rate.py:11 ... 原 R1 取 ``[71]`` 與
helper_scripts/canary/healthchecks/66_close_maker_pre_stopout_rate.py:13 ... 的 passive_wait ``[71] close_maker_zero_spine_lineage`` 字面碰撞
helper_scripts/canary/healthchecks/tests/test_66_pre_stopout_rate.py:13 ... MEDIUM-F1：[71] → [66]
helper_scripts/canary/healthchecks/tests/conftest.py:63,64 ... R2 從 [71] 改 [66] 避與 passive_wait_healthcheck [71]
```

→ **8 hits 全部是 doc/comment 形式**，分三類：
  1. `__init__.py:12,22` + `66_close_maker_pre_stopout_rate.py:13` = passive_wait `[70-74]` namespace 邊界說明（**design intent**）
  2. `__init__.py:37` + `66_close_maker_pre_stopout_rate.py:11` + `tests/*` = rename 歷史說明（防後人重蹈覆轍）
  3. **0 個 active slot 編號還是 `[71]`**（active = `[66]`，見下）

與 E2 R2 §MEDIUM-F1 verdict 一致：「passive_wait `[71]` 仍 own close_maker_zero_spine_lineage（不影響）；hc71 0 hit；active leftover 0」。

**E4 認定**：task list 字面預期 "0 hit" 是嚴格無 `[71]` 字串，但 E2 已 APPROVE 此 design（保留 namespace 邊界 doc 是釐清意圖，非 leftover）。E4 不重啟 E2 review；確認 active slot 無 `[71]` 即 PASS（CLAUDE.md §八 工作鏈 + 不重審 E2 已 APPROVE 範圍）。

```bash
$ grep -rn "71_close_maker_pre_stopout" helper_scripts/canary/ | grep -v __pycache__
# 0 hit ✓

$ grep -rn "hc71" helper_scripts/canary/healthchecks/tests/ | grep -v __pycache__
# 0 hit ✓

$ find helper_scripts/canary/healthchecks/ -name "71_close_maker*"
# 0 file ✓

# [66] 應 ≥ 3 hit
$ grep -rn "\[66\]" helper_scripts/canary/healthchecks/ | grep -v __pycache__ | wc -l
17 ✓ (active check_id + spec doc + test ref + slot doc)
```

| Grep | Expected | Actual | Result |
|---|---|---|---|
| `[71]` in canary/healthchecks/ active slot | 0 | 0 (8 hits 全 doc/comment) | ✓ |
| `71_close_maker_pre_stopout` in canary/ | 0 | 0 | ✓ |
| `hc71` in tests/ | 0 | 0 | ✓ |
| `71_close_maker*` file | 0 | 0 | ✓ |
| `[66]` in canary/healthchecks/ | ≥ 3 | 17 | ✓ |

### Step 5 — 規範驗證

| Check | Result |
|---|---|
| `66_close_maker_pre_stopout_rate.py` LOC | 392 ≤ 800 ✓ |
| `62_close_maker_fill_rate.py` LOC | 336 ≤ 800 ✓ |
| `__init__.py` LOC | 39 ≤ 800 ✓ |
| `tests/test_66_pre_stopout_rate.py` LOC | 301 ≤ 800 ✓ |
| `tests/conftest.py` LOC | 104 ≤ 800 ✓ |
| Emoji scan (5 files) | 0 emoji line per file ✓ |
| `/home/ncyu` / `/Users/ncyu` hardcoded path | 0 hit ✓ |

注釋規範（中文為主，per feedback_chinese_only_comments 2026-05-05）：spot 抽查 module docstring + R2 修正歷史段 + adversarial probe rationale 全中文。

### Step 6 — Mock 真實性 spot check

抽 4 個 test case 對照 Mock 安全規則 §5.1/§5.2：

**Spot 1 — FakeCursor (conftest.py:71-104)**

- 模式：純 mock IO（PG cursor.execute / fetchall），不 mock 業務
- 業務邏輯（run() 計算 stopout rate / verdict ladder / overall 收斂）真跑
- `cur.executed_sqls` capture SQL + params → 測 SQL semantic correctness
- ✓ OK per §5.1（mock IO 邊界）

**Spot 2 — test_default_patterns_match_real_production_exit_reasons (test_66:256-285)**

- **不 mock**：用 fnmatch 模擬 PG LIKE，pattern 真實 match
- Fixture `EXPECTED_STOPOUT_EXIT_REASONS` = 12 個 production 真實字串，全部 source line 標註（risk_checks.rs:334/355/379/390 + bb_breakout/mod.rs:910/919 + step_0_fast_track.rs:486/603 + helpers_close_tags.rs:122-127 + maker_price.rs:528/529）
- E2 R2 自跑 adversarial probe 證實此 test 設計能 catch R1 HIGH-A1 + HIGH-A2 regression（3/12 紅報）
- ✓ 非 self-consistent；adversarial-tested

**Spot 3 — test_sql_binds_patterns_and_liquidation (test_66:205-231)**

- 驗 SQL 字面 + params tuple 順序（patterns × 2 次重用 + liq_pattern × 2 次 + window_secs + engine_modes）
- 驗 psycopg2 不會自動 dedup FILTER 子句的事實
- 純 SQL string + params 結構檢驗，無業務 mock
- ✓ 真實 SQL semantic 檢驗

**Spot 4 — test_stratify_none_keeps_legacy_sql_verbatim (test_62:132-153)**

- 驗 stratify=none 模式 SQL **逐字節向後兼容**（不含 `EXTRACT(HOUR` / `EXTRACT(DOW`）
- 額外 assert `GROUP BY engine_mode` → `ORDER BY engine_mode` 之間無 comma（無 extra GROUP cols）
- ✓ adversarial design；真實檢驗 R2 改動的向後兼容承諾

| Test | mock 內容 | OK? |
|---|---|---|
| FakeCursor | PG cursor IO only（execute/fetchall），業務真跑 | ✓ |
| test_default_patterns_match... | 無 mock；fnmatch 模擬 LIKE | ✓ |
| test_sql_binds_patterns... | 無 mock；SQL string + params 檢驗 | ✓ |
| test_stratify_none_keeps_legacy... | 無 mock；逐字節向後兼容 assert | ✓ |

**整體評估**：mock 範圍嚴守 IO 邊界；業務邏輯（verdict ladder / Wilson / pattern match）100% 真跑；EXPECTED_* fixture 全部 source-derived（grep 標註），不是 self-consistent。

---

## 跑兩遍結果

| Run | healthchecks/tests/ | canary/ | passive_wait close_maker |
|---|---|---|---|
| 1st | 83 PASS | 201 PASS | 8 PASS + 14 subtests |
| 2nd | 83 PASS | 201 PASS | 8 PASS + 14 subtests |

flaky? **N**（two-run identical green）

---

## SLA / 浮點 / 跨語言

不適用（healthcheck 是 read-only SQL observability，非 hot path / 非 indicator 計算 / 純 Python 無 Rust counterpart）。

---

## E2 R2 nit / defer 狀態（不擋 E4，PM 後續處理）

E2 R2 §LOW-G1 / LOW-G2 / LOW-G3 + DEFER-D1 全部不擋 commit。E4 不做 fix，只報：

| ID | 描述 | 處理方 |
|---|---|---|
| LOW-G1 | `66_close_maker_pre_stopout_rate.py:54-56` regime_shift 未在非 stopout docstring 顯式列 | PM 後續 polish |
| LOW-G2 | `62_close_maker_fill_rate.py:280` literal `"PASS"` vs `VERDICT_PASS` const | PM 後續 polish |
| LOW-G3 | `TODO.md:467` 仍 ref `71_close_maker_pre_stopout_rate.py` 沒同步 rename → `66_*` | **PM commit 時順手改** |
| DEFER-D1 | Wilson upper bound sub-clause | PM 補 TODO §11.3 follow-up ticket |

---

## E4 FLAG（不擋 commit）

無新 BLOCKER / 無 mock 過頭 / 無結構性 test 失靈 / 無跨檔 broken 發現。

E2 R2 已對 LOW-G1/G2/G3 + DEFER-D1 給出修法，E4 不重複。

---

## 結論

**PASS · commit ready**

- 83/83 pytest（healthchecks/tests/）兩遍同綠
- 201/201 cross-module（canary/）兩遍同綠
- 8/8 + 14 subtests passive_wait close_maker_audit（cross-namespace 不擾）
- grep clean：active `[71]` / `hc71` / `71_close_maker_pre_stopout` 0 leftover；8 個 `[71]` doc/comment 全 E2 APPROVE design intent
- 規範全綠（5 file size ≤ 800 / 0 emoji / 0 hardcoded path / 注釋中文為主）
- mock 真實性 4-spot 全 OK，無 self-consistent fake-success
- 新 test `test_default_patterns_match_real_production_exit_reasons` 設計上 adversarial-tested（E2 R2 §MEDIUM-E1 證實能 catch R1 HIGH-A1/A2 regression）

PM 建議：
1. commit + push 順手改 `TODO.md:467` `71_` → `66_`（LOW-G3）
2. 補 TODO §11.3 `P2-OBS-PRE-STOPOUT-WILSON-SUBCLAUSE` follow-up ticket（DEFER-D1）
3. LOW-G1 / LOW-G2 polish 入下批

E4 REGRESSION DONE: PASS · report path:
`docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-21--c1_c2_close_maker_healthcheck_e4_regression.md`
