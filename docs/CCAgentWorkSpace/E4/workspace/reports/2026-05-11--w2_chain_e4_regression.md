# E4 Regression — W2 IMPL Chain 4 Sub-agent（A4-C BTC→Alt Lead-Lag）

**Date**: 2026-05-11 (post Mac noon)
**Reviewer**: E4
**Trigger**: Operator dispatch `regression-testing-protocol` skill + PA `2026-05-11--w2_impl_v12_dispatch_plan.md` §3.4/§3.5/§5 E4 必跑項
**HEAD**: `1f0354cf` (W2 IMPL chain 4 sub-agent land + sibling V083 E2 review)
**Scope**: 4 W2 sub-task（IMPL-1 orderbook 接線 / IMPL-2 Layer 2 fence amendment / IMPL-3 healthcheck [57] / IMPL-4 paper edge report 工具鏈）+ sibling W2-IMPL-5 排程待 rebase

---

## 0. Verdict

**NEEDS_FIX**（**3 個 HIGH BLOCKER in IMPL-4 SQL** + 5 個其他 sub-task ALL PASS）

| 維度 | 結論 |
|---|---|
| Rust lib test (release, 跑兩遍) | ✅ **2797 / 0 / 0** non-flaky · 與 IMPL-1 sub-agent self-claim 2789→2797 (+8) 對齊 |
| W2 btc_lead_lag specific (35 test) | ✅ 35 / 0 / 0（含 ingest task / cohort cap / strict shift(N) / NaN propagation） |
| W2 healthcheck Mac fixture (10 test) | ✅ 10 / 0 / 0（fixture 真實 cover PASS / WARN / FAIL 三段） |
| Python pytest tests/ baseline | ⚠️ 253 / 1 / 2 skipped · 1 failed = **pre-existing docs/README.md drift（非 W2 引入）** |
| **IMPL-4 SQL Linux PG dry-run** | ❌ **3 HIGH BLOCKER**（trading.klines / klines.interval / SQL 注釋 `%(window_days)s` 字面字串） |
| IMPL-3 healthcheck Linux PG real check | ✅ runtime status `WARN` by design（book_imb=0 placeholder，IMPL-1 binary 待 engine restart load） |
| Cross-language consistency (panel schema + cohort + regime) | ✅ Rust write → V088 PG read → Python check 三方對齊 7-symbol cohort + regime enum |
| Mock 不掩蓋業務邏輯 (4 sub-task each) | ✅ 4/4 sub-task 全真驗 production behavior |
| 3 端 git sync | ✅ Mac/Linux/origin 同 HEAD `1f0354cf` |

**結論**：IMPL-1/2/3 + cargo test 全 GREEN，**IMPL-4 SQL 因 3 個 schema/syntax BLOCKER 在 Linux PG empirical caller path 100% fail**。建議：W2-IMPL-1/2/3 + cargo test land 可保留 commit；**IMPL-4 SQL 退回 E1 修 3 BLOCKER → E2 re-review → E4 重 dry-run**；W2-IMPL-5 派發前必先收 IMPL-4 fix。

---

## A. Rust lib test full regression

### A.1 `cargo test --release -p openclaw_engine --lib`

**第一遍** (從 srv root via /Users/ncyu/Projects/TradeBot/srv/rust):
```
test result: ok. 2797 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.57s
```

**第二遍** (non-flaky 驗):
```
test result: ok. 2797 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.56s
```

**結論**: ✅ **2797 / 0 / 0** 同綠兩遍 non-flaky

**Baseline 對比**:
| Phase | passed | failed | ignored | source |
|---|---|---|---|---|
| Pre-W2（Sprint N+0 5/10 snapshot） | 2789 | 0 | 0 | E4 R7 baseline |
| Post-IMPL-1 self-claim | 2797 | 0 | 0 | W2-IMPL-1 sub-agent report |
| **Post W2 全 4 sub-task（本次）** | **2797** | **0** | **0** | **E4 實測** |
| Delta | +8 | 0 | 0 | W2-IMPL-1 8 個 new test，IMPL-2/3/4 不加 cargo test |

### A.2 W2 btc_lead_lag specific tests

`cargo test --release -p openclaw_engine --lib btc_lead_lag`:
```
test result: ok. 35 passed; 0 failed; 0 ignored; 0 measured; 2762 filtered out; finished in 0.06s
```

**35 個 test 涵蓋**:

| 測試類型 | 數量 | 範圍 |
|---|---|---|
| W2-IMPL-1 orderbook ingest path | 7 | `compute_book_imbalance_*` (positive/negative/balanced/top_n/nan_empty) + `on_tick_writes_real_book_imbalance_or_nan` + `ingest_task_drops_non_btc_or_non_orderbook_event` + `ingest_task_to_producer_5_tick_integration`（真實 spawn task + 5 tick fixture）+ `run_loop_responds_to_cancel`（cancel-safe） |
| Producer 核心（pre-W2-IMPL-1） | 13 | strict shift(N) lookahead-free / regime_tag / xcorr / expected_dir truth table / latest lifecycle / buffer capacity / arrays_aligned invariant |
| V088 INSERT writer | 4 | `arrays_aligned_invariant_fails_when_lengths_mismatch` / `nan_to_null_f32_handles_nan_and_finite` / `insert_sql_has_12_placeholders` |
| PSR / DSR / R²(N) helper | 5 | `pearson_perfect_positive/negative/zero` / `psr_zero_sanity_skew_kurt_formula` / `psr_zero_nan_on_*` |
| panel snapshot trait propagation | 4 | `snapshot_to_trait_panel_preserves_nan` / `snapshot_to_trait_panel_propagates_main_signal_fields` |
| Slot factory | 2 | `create_btc_lead_lag_panel_slot_returns_empty` / `factories_match_pattern` |

**結論**: ✅ 真實覆蓋 ingest path（非 stub return），integration test 真 spawn `spawn_btc_orderbook_ingest_task` 跑 cancel-safe + 5-tick imbalance 真實計算 + 非 BTC/非 Orderbook 過濾 silent drop assertion；無業務邏輯 mock。

---

## B. Python Tests

### B.1 IMPL-3 healthcheck Mac fixture (10 test)

`OPENCLAW_BASE_DIR="$PWD" PYTHONPATH="$PWD" python3 -m pytest helper_scripts/db/test_btc_lead_lag_panel_healthcheck.py -v`:
```
============================== 10 passed in 0.02s ==============================
```

**Fixture 覆蓋 3 段 verdict**:
| Test | 對應 verdict | 真實 cover |
|---|---|---|
| `test_fixture_1_all_four_conditions_pass` | PASS（4/4 全綠）| ✅ 真實 cur.fetchone 回 6-tuple |
| `test_fixture_2_two_warn_conditions` | WARN（2 warn sub-check）| ✅ 真實 |
| `test_fixture_3_silent_dead_three_failures` | FAIL（3 fail sub-check）| ✅ 真實 |
| `test_book_placeholder_warn_without_required_env` | WARN by design | ✅ |
| `test_book_placeholder_fail_with_book_required` | FAIL when required env set | ✅ |
| `test_required_env_escalates_warn_to_fail` | WARN→FAIL escalation | ✅ |
| `test_v088_table_absent_pass_skip` | PASS_SKIP pre-deploy | ✅ |
| `test_v088_zero_rows_pass_skip_post_deploy` | PASS_SKIP early window | ✅ |
| `test_default_off_pass_skip_without_query` | env opt-in 默認 off | ✅ |
| `test_sql_contract_is_read_only` | grep DDL/DML 0 hit | ✅ |

**結論**: ✅ Mock cursor 真實傳遞 6-tuple aggregate result，verdict logic 真跑（age/cohort/extreme/book_imb 4 sub-verdict + overall 整合）。不 mock check_57 內部 verdict 函數。

### B.2 Python full regression `tests/`

`python3 -m pytest tests/ -q --tb=short`:
```
1 failed, 253 passed, 2 skipped in 0.84s
```

**FAIL test 歸屬**:
- `tests/structure/test_docs_readme_index_static.py::test_archive_top_level_files_are_all_indexed`
- 失敗原因：`docs/archive/2026-05-09--claude_md_section5_pre_alpha_surface.md` 未登錄 `docs/README.md` 索引
- Pre-existing：archive file 由 commit `c13c811e` (2026-05-09 W-AUDIT-8a) 引入；W2 commit `1f0354cf` 不動該 file
- **非 W2 引入** → 對 W2 deploy 0 影響 → 已記入 P2 followup（CLAUDE.md §三 衛生規則需後續同 commit 補索引）

---

## C. Linux PG empirical dry-run（per `feedback_v_migration_pg_dry_run.md` 必跑）

### C.1 IMPL-3 healthcheck [57] re-verify

**setup**: ssh trade-core + psql 連 trading_ai DB + 設 `OPENCLAW_W2_HEALTHCHECK_ENABLED=1`

**結果**:
```
STATUS: WARN
DETAIL: [57] W2 btc_lead_lag panel degraded (0 FAIL / 1 WARN sub-checks) — window=60m total_n=60 age=56.0s/PASS cohort=7/7/PASS extreme=0(0.0%)/PASS book=placeholder_zero/WARN
```

**逐項驗**:
| 條件 | 實測 | 預期 | 結論 |
|---|---|---|---|
| age | 56.0s | < 120s PASS | ✅ producer 1m grain 寫入即時 |
| cohort | 7/7 | = 7 | ✅ 7-symbol cohort 全 land |
| extreme | 0(0.0%) | < 5% PASS | ✅ BTC 1h return normal range |
| book_imb | placeholder_zero | WARN by default | ⚠️ W2-IMPL-1 binary 已 land 但 engine 載入舊 binary（待 deploy --rebuild） |
| **overall** | **WARN** | **WARN by design** | ✅ |

**hot-path index 命中分析**:

`EXPLAIN ANALYZE` 對 panel_window CTE:
```
Custom Scan (ChunkAppend) on btc_lead_lag_panel p  (cost=0.00..73.32 rows=557 width=0)
        Chunks excluded during startup: 0
        ->  Seq Scan on _hyper_75_486_chunk p_1  (cost=0.00..73.32 rows=557 width=0)
              Filter: ((lead_window_secs = 120) AND (snapshot_ts_ms >= ...))
Planning Time: 2.347 ms
Execution Time: 0.497 ms
```

| 觀察 | 解讀 |
|---|---|
| Seq Scan 而非 Index Scan | PG cost-based optimizer 正確選擇 — 565 row 全在 7d window 內，全表掃描比 index lookup 便宜 |
| Hot-path index `idx_btc_lead_lag_panel_ts_window` 存在 | ✅ V088 migration 已 land |
| Hypertable chunk = `_hyper_75_486_chunk` | ✅ TimescaleDB 自動 chunk 對應 IMPL-3 sub-agent report 對齊 |
| Execution Time 0.497ms | ✅ Healthcheck SLA < 1s 大幅滿足 |

**結論**: ✅ Hot-path index land + execution time well within SLA；Seq Scan 在當前 row count 是 PG 正確決策（resilience：row count 達 1m × 24h × 7d = 10080 後 PG 會自動切 Index Scan）。

### C.2 IMPL-4 counterfactual SQL — **3 HIGH BLOCKER**

#### BLOCKER 1: `trading.klines` 表不存在

**證據**:
```sql
-- /Users/ncyu/Projects/TradeBot/srv/sql/queries/w2_btc_alt_lead_lag_counterfactual.sql:182
FROM trading.klines k, params
```

Linux PG empirical query:
```
SELECT table_schema, table_name FROM information_schema.tables
WHERE table_name ILIKE '%kline%';

 table_schema | table_name
--------------+------------
 market       | klines
```

**修復**: `trading.klines` → `market.klines`

#### BLOCKER 2: `klines.interval` column 不存在

**證據**:
```sql
-- line 185
AND k.interval = '1m'
```

Linux PG empirical schema:
```
column_name |        data_type
-------------+--------------------------
 ts          | timestamp with time zone
 open_ts_ms  | bigint
 close_ts_ms | bigint
 symbol      | text
 timeframe   | text  <-- 不是 'interval'
 ...
```

**修復**: `k.interval` → `k.timeframe`

#### BLOCKER 3: SQL 注釋字面字串 `%(window_days)s` 被 psycopg2 當 placeholder

**證據**:
```sql
-- line 42 (注釋)
--   :window_days        — paper engine 7d edge collection window（int, default 7）
-- line 87 (注釋)
    -- 參數標準化：caller 注入 %(window_days)s（default 7）+ %(cohort_symbols)s
```

注釋裡的 `%(window_days)s` / `%(cohort_symbols)s` 字面字串被 psycopg2 解析成 placeholder（psycopg2 不跳過 `--` SQL 注釋），所以即使 caller 傳了 `{"window_days": 7, "cohort_symbols": [...]}` 字典，仍會 `KeyError`（重複 placeholder 仍視 fail）：

Mac empirical caller test:
```
FAIL: KeyError: 'param'
```

**修復**: 把 line 42 + line 87 注釋裡的 `%(...)s` 字面替換為「無 placeholder 的字串」，例如「caller 注入 window_days / cohort_symbols 兩個變數」純文字描述。

#### Fixed-SQL 驗證

把 3 BLOCKER fix 後（`trading.klines → market.klines`, `k.interval → k.timeframe`, 注釋字面字串移除）跑 Linux PG empirical：

```
final_row_count = 3948
```

**結論**: ✅ Fixed-SQL 真實返 3948 row（panel 565 × 7 cohort sym = ~3955 panel_expanded row LEFT JOIN klines + fills）→ 三表 JOIN 邏輯正確；fix 後 SQL 結構性 OK；確認 BLOCKER 是 schema/comment 失誤而非設計缺陷。

---

## D. Cross-language Consistency (1e-4 tolerance)

### D.1 Schema 對齊

| 欄位 | Rust 寫 | PG 列型 | Python check_57 讀 | 結論 |
|---|---|---|---|---|
| `snapshot_ts_ms` | `i64` | `BIGINT` | `int` | ✅ 整數無精度差 |
| `alt_symbols` | `Vec<String>` | `text[]` | `list[str]` | ✅ 字串無精度差 |
| `alt_xcorr` | `Vec<f32>` | `real[]` | `list[float]` (Python f64) | ✅ f32 寫 → f64 讀 是擴展，精度差 ≈ 1e-7 < 1e-4 |
| `btc_lead_return_pct` | `f32` | `real` | `float` | ✅ 同上 |
| `regime_tag` | `String` enum {"normal","extreme"} | `text` | `str` enum compare | ✅ |
| `lead_window_secs` | `u32` (120) | `integer` | `int` | ✅ |

### D.2 Empirical real-row sample

Linux PG `SELECT alt_symbols, regime_tag, btc_book_imbalance, snapshot_ts_ms FROM panel.btc_lead_lag_panel ORDER BY snapshot_ts_ms DESC LIMIT 3`:

```
                     alt_symbols                         | regime_tag | btc_book_imbalance | snapshot_ts_ms
---------------------------------------------------------+------------+--------------------+----------------
 {ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT,ADAUSDT,AVAXUSDT,DOTUSDT} | normal | 0 | 1778491848918
 {ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT,ADAUSDT,AVAXUSDT,DOTUSDT} | normal | 0 | 1778491788918
 {ETHUSDT,SOLUSDT,XRPUSDT,DOGEUSDT,ADAUSDT,AVAXUSDT,DOTUSDT} | normal | 0 | 1778491728918
```

- `alt_symbols` 7-cohort 對齊 spec §2.2 ✅
- `regime_tag = 'normal'` 對齊 Rust enum ✅
- `btc_book_imbalance = 0`：IMPL-1 binary 已 land 但 engine 載入舊 binary（待 `restart_all --rebuild` deploy 後翻 non-0）— **預期 deploy gating 行為**
- `snapshot_ts_ms` diff = 60000ms = 60s = 1m grain 對齊 ✅

**結論**: ✅ 跨語言 schema + cohort enumeration + regime enum + 1m grain bucketing 全對齊；浮點欄位（f32 寫 / f64 讀）擴展 cast 精度差 < 1e-7 遠優於 1e-4 容差。

---

## E. Mock 不掩蓋邏輯（4 Sub-task Each）

### E.1 IMPL-1（Orderbook 接線）

| 驗證項 | 結論 |
|---|---|
| `compute_btc_book_imbalance` 純函數 6 test | ✅ 真實計算公式 `(bid_top_n - ask_top_n) / (bid_all + ask_all)` 走進去；NaN / 空 bid / 空 ask / overflow clamp 全有真實 fixture |
| `spawn_btc_orderbook_ingest_task` integration test | ✅ 真實 `tokio::spawn` + `mpsc::channel(32)` + 餵 5 個 Bybit V5 PriceEvent fixture（不同 imbalance pattern）+ assert imbalance ∈ {0.333, -0.500, 0.0, 0.714, -0.818} 真實計算結果 |
| `ingest_task_drops_non_btc_or_non_orderbook_event` | ✅ 真實送 ETHUSDT Orderbook + BTCUSDT Ticker → slot.read() 仍 None → 真實過濾 logic |
| `run_loop_responds_to_cancel` | ✅ 真實 `CancellationToken::cancel()` → ingest task 真退出 |

**結論**: ✅ **0 業務邏輯 mock**，外部 IO（PriceEvent stream）走 tokio mpsc fixture 是合法 IO boundary mock；imbalance 計算 / 過濾 / cancel-safe 全 production fn 真實跑

### E.2 IMPL-2（Layer 2 fence amendment）

| 驗證項 | 結論 |
|---|---|
| spec v1.2 → v1.3 inline edit | ✅ spec 文檔更新（非 code path，無 test 需求） |
| main.rs env-gate 三狀態 wrap | ⚠️ 無對應 unit test（IMPL-2 sub-agent 自承「env-gate logic 等 W2-IMPL-5 integration test cover」） |
| cross_asset/mod.rs MODULE_NOTE | ✅ 純文檔更新（無 logic 變動） |

**結論**: ⚠️ IMPL-2 邏輯依賴 W2-IMPL-5（pending）的 integration test；當前 cargo test 不 cover env-gate fence — **此為 PA dispatch plan §3.2 設計**（IMPL-5 rebase IMPL-1+2 後跑 fence integration test）。E4 不視為 BLOCKER 但 IMPL-5 派發前必補。

### E.3 IMPL-3（Healthcheck [57]）

| 驗證項 | 結論 |
|---|---|
| Mac fixture 10 test | ✅ 真實 cur.fetchone 6-tuple → verdict 整合 logic 真跑（age/cohort/extreme/book_imb 4 子 verdict + overall PASS/WARN/FAIL）|
| Linux PG real check | ✅ 連真實 PG 跑 → `WARN by design (book=placeholder_zero)` 對齊預期 |
| SQL `read_only` contract test | ✅ grep INSERT/UPDATE/DELETE/DDL 0 hit |

**結論**: ✅ **0 業務邏輯 mock**，DB cursor 是合法 IO boundary mock；verdict logic + SQL aggregate 真實 cover

### E.4 IMPL-4（Paper edge report 工具鏈）

| 驗證項 | 結論 |
|---|---|
| Mock case 1 (plus15)：n=150, avg_net=19.87, t=86.45 → verdict=plus15 | ✅ 真實跑 step_gate_verdict (n, avg_net, t-stat) → plus15 |
| Mock case 2 (plus5_15)：n=150, avg_net=7.91, t=34.44 → verdict=plus5_15 | ✅ 同上 |
| Mock case 3 (minus5)：n=150, avg_net=-2.99, t=-12.93 → verdict=minus5 | ✅ 同上 |
| PSR(0) Bailey-LdP 2012 | ✅ 真實 `Φ((SR - 0) × √(n-1) / √(1 - skew·SR + (kurt-1)/4·SR²))` 跑（含 math.erf cross-platform Φ）|
| DSR K=95 | ✅ `mu_0 = √(2 ln 95) = 3.0179` 真實計算 |
| Block-bootstrap 95% CI | ✅ deterministic seed=20260512, block_size=60, 1000 iter Künsch 1989 moving-block 真實跑 |
| Alpha decay R²(60/120/300) | ✅ OLS `β₁ = Cov(x,y)/Var(x); R² = 1 - SS_res/SS_tot` 真實計算 |

**結論**: ✅ **0 業務邏輯 mock**，公式全真實跑；唯一 mock = `_make_mock_row` 為 SQL row 構造器，但下游公式跑進去後是 production helper（PSR / DSR / CI / R²）真實計算

---

## F. SLA Pressure

| 項目 | 實測 | SLA 目標 | 結論 |
|---|---|---|---|
| `compute_btc_book_imbalance` 純函數 | 不到 1μs | < 50μs hot-path | ✅ |
| `spawn_btc_orderbook_ingest_task` 1 tick e2e | ~10ms（含 tokio sleep）| 觀察用，非 hot-path | ✅ |
| check_57 PG query (1h window) | 0.497ms | < 1s | ✅ 充裕 |
| Rust lib full test | 0.57s （2797 test 跑）| - | ✅ |

---

## G. 退回 E1 修復清單（NEEDS_FIX）

### G.1 BLOCKER 3 個（IMPL-4 only，W2-IMPL-5 派發前必修）

| # | 位置 | 修復 |
|---|---|---|
| **B1** | `sql/queries/w2_btc_alt_lead_lag_counterfactual.sql:182` | `FROM trading.klines k` → `FROM market.klines k` |
| **B2** | 同檔 line 185 | `AND k.interval = '1m'` → `AND k.timeframe = '1m'` |
| **B3** | 同檔 line 42 + line 87 | 注釋裡的 `%(window_days)s` / `%(cohort_symbols)s` 字面字串需轉純文字描述，避免 psycopg2 把注釋當 placeholder（建議：用單反引號或全角字符或寫成 `\%(window_days)s` 但 SQL 不支援 escape，最簡 = 改寫「caller 注入 window_days 與 cohort_symbols 兩變數」純文字） |

附帶補丁：line 6 + 31 + 32 + 98 + 160 + 6 (w2_paper_edge_report.py 開頭注釋) 中 `trading.klines` 引用也需同步改 `market.klines`（這些是注釋無 runtime 影響，但 documentation hygiene 應一併修）

### G.2 NEEDS_FIX 不 BLOCKER 1 個（IMPL-2 邏輯覆蓋）

| # | 位置 | 修復 |
|---|---|---|
| **N1** | W2-IMPL-2 main.rs env-gate fence wrap | 等 W2-IMPL-5 派發時必加 unit test 對三狀態（OPENCLAW_ENABLE_PAPER=1 / unset+paper-only / unset+demo|live-active）assert producer.spawn 行為 — per PA dispatch §3.5 acceptance criteria 2 |

### G.3 P2 followup（非本 wave，不阻 W2-IMPL-5）

| # | 位置 | 修復 |
|---|---|---|
| **P1** | `docs/README.md` 索引 | 補登 `2026-05-09--claude_md_section5_pre_alpha_surface.md`（pre-existing W-AUDIT-8a drift，非 W2 引入）|
| **P2** | `helper_scripts/reports/w2_paper_edge_report.py` 1257 LOC > 800 警告線 | E2 拍板拆 module 或 single-file accept（per IMPL-4 sub-agent §8.1）|
| **P3** | `rust/openclaw_engine/src/panel_aggregator/btc_lead_lag.rs` 1771 LOC pre-existing baseline exception | per §九 exception clause 接受 + 開 P2 ticket（per IMPL-1 sub-agent 自承）|

---

## H. 三端 git 同步驗

```
Mac:    1f0354cf W2 IMPL chain 4 sub-agent land + sibling V083 E2 review [skip ci]
Linux:  1f0354cf W2 IMPL chain 4 sub-agent land + sibling V083 E2 review [skip ci]
origin: 1f0354cf
```

✅ 三端同步在 HEAD `1f0354cf`，Linux trade-core working tree clean

---

## I. Test 表

| 引擎 | passed | failed | ignored | baseline | delta | non-flaky |
|---|---|---|---|---|---|---|
| Rust lib (release) | **2797** | **0** | **0** | 2789 (pre-W2) | +8 | ✅ 跑兩遍同綠 |
| Rust W2 btc_lead_lag specific | **35** | **0** | **0** | n/a (new) | +8 (IMPL-1) | ✅ |
| W2 healthcheck Python fixture | **10** | **0** | **0** | n/a (new) | +10 (IMPL-3) | ✅ |
| Python tests/ | 253 | **1** | 2 skipped | n/a | **0 W2 regression**（1 fail 是 pre-existing docs/README.md drift）| ✅ |
| IMPL-4 SQL Linux PG dry-run | **0** | **3 BLOCKER** | - | n/a | -3 | ❌ |

---

## J. Sub-task 級別 Verdict

| Sub-task | 狀態 | E4 結論 |
|---|---|---|
| W2-IMPL-1 (Orderbook 接線) | ✅ PASS | 35 test 真實 cover ingest path + cohort/cap/strict-shift；no business-logic mock |
| W2-IMPL-2 (Layer 2 fence amendment) | ⚠️ PASS-with-note | spec edit + main.rs env-gate land；env-gate unit test 由 IMPL-5 cover（per PA dispatch） |
| W2-IMPL-3 (Healthcheck [57]) | ✅ PASS | Mac fixture 10/10 + Linux PG real check WARN by design + hot-path index 命中 |
| W2-IMPL-4 (Paper edge report 工具鏈) | ❌ **NEEDS_FIX** | smoke-test mock 3/3 PASS + PSR/DSR/CI/R²(N) 公式 verified；**Linux PG empirical caller path 3 HIGH BLOCKER**（SQL schema 錯 + 注釋 placeholder 字面）；IMPL-4 sub-agent 自承 PG dry-run 屬 E4 範圍但未自跑 |
| W2-IMPL-5 (E2 fence + E4 regression test + sign-off) | ⏸ NOT STARTED | PA dispatch 設計需 rebase IMPL-1+2 head 後派發；E4 建議：IMPL-4 BLOCKER fix 後再派 IMPL-5 |

---

## K. 重要架構觀察

1. **Engine binary 待 deploy**：Linux engine 已啟動但 `btc_book_imbalance=0` 全部為 0 → 表示 engine 載入的是 **pre-W2-IMPL-1** binary（即仍是 placeholder）。`restart_all --rebuild --keep-auth` 後 W2-IMPL-1 orderbook 真實值才會寫入 panel。E4 不在 deploy gate（per CLAUDE.md PM 收尾範圍）但記錄此 deploy gating。
2. **Hot-path index 在 60-row 級別走 Seq Scan 正常**：PG cost-based optimizer 看 565 row + cardinality 估算選 Seq Scan 比 Index Lookup 便宜 → 等 panel 累積 ≥10k row 後 PG 自動切 Index Scan，這是 PG **正確決策**不是 bug。
3. **跨語言 1e-4 容差自然滿足**：Rust `f32` → PG `real` → Python `float (f64)` 鏈路只有 f32→f64 擴展（無精度損失，diff < 1e-7），W2 scope 內無新浮點計算 hot path（panel field 大多是 input pass-through）。
4. **W2-IMPL-5 rebase 排程**：PA dispatch 設計 IMPL-5 等 IMPL-1+2 land 後 rebase 寫 fence integration test。E4 建議：先 **派 E1 修 3 BLOCKER → E2 re-review → E4 重 dry-run** → 通過後再派 IMPL-5。

---

E4 REGRESSION DONE: NEEDS_FIX · report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-11--w2_chain_e4_regression.md`
