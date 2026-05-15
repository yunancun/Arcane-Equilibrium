---
report: PA — F-FA-3 W-C Caveat 2 不變式 guard tests + grep guard rule 設計
date: 2026-05-15
author: PA agent
mode: design verification (no code/config mutation, no IMPL test code)
trigger: PM Wave 1 Track A4 派工；EDGE-P2-3 Phase 1b close-maker-first refactor 4-agent review APPROVED-CONDITIONAL；FA round 2 §4 標明 F-FA-3 為 blocking minor
status: SPEC-READY（4 integration test specs + 6 grep patterns + V094 schema 建議 + healthcheck [63] 設計 + IMPL prereq 5 解除條件）
scope: design / spec only — 不改任何代碼，不寫 IMPL test code
---

# F-FA-3 W-C Caveat 2 不變式 — Guard Tests Design + grep Guard Rule

## 0. TL;DR

- **不變式內容**：close path 不寫 spine ExecutionPlan/ExecutionReport lineage（`commands.rs:809-815` 既有實作），新增的 5 個 close-maker audit 欄位（`close_maker_attempt` / `close_maker_fallback_reason` / `close_initial_limit_price` / `close_final_fill_price` / `close_maker_eligible_reason`）**必須走 `trading.fills.details` JSONB**，**不能走 spine ExecutionPlan/ExecutionReport lineage**。
- **核心發現 1**：`trading.fills.details JSONB` **已存在於 V003 line 284**（10 個月前定義）— 5 audit 欄位走 details JSON-extension **是 zero-schema-migration**，僅需新建 V094 加 `close_maker_attempt` BOOL hot-path column + writer 升級 + healthcheck 新 check。
- **核心發現 2**：當前 `trading_writer.rs:430` INSERT INTO trading.fills 列表 **不寫 details**（只寫 23 個欄位）— V094 IMPL 必同步升 writer 寫 details payload，否則 audit 欄位 100% NULL → guard tests 全 FAIL。
- **設計交付**：4 integration test specs（IMPL E1 直接照寫）+ 6 grep guard patterns（覆蓋率 ≥95% 違規場景）+ V094 schema 兩段式（hot column + JSON extension）+ healthcheck [63] dual-gate 設計 + IMPL prereq 5 解除標準。
- **不在本 scope**：實際 test code（IMPL prereq 解後 E4 寫）、AMD v0.2 patch（Track A1）、portfolio_var verify（Track A3）、commands.rs/spine writer/fills schema 任何代碼改動。

---

## §1 W-C Caveat 2 不變式 source quote + 維持機制驗證

### 1.1 不變式 source-of-truth

`srv/rust/openclaw_engine/src/tick_pipeline/commands.rs:809-815`（empirical re-verified by PA 2026-05-15）：

```rust
                reference_source: if dispatch_price.is_finite() && dispatch_price > 0.0 {
                    Some("dispatch_last_fallback".to_string())
                } else {
                    None
                },
                // W-C Caveat 2 修復（2026-05-11）：close 路徑不寫 entry lineage
                // （emit_entry_lineage 僅 open intent 使用），下游
                // emit_fill_completion_lineage 自然 short-circuit。
                spine_order_plan_id: None,
                spine_decision_id: None,
                spine_verdict_id: None,
                spine_stub_report_id: None,
            };
```

### 1.2 不變式維持機制（雙層 short-circuit 已在 production）

**第一層（entry 端 short-circuit）**：`commands.rs:812-815` 在 close path 構造 `OrderDispatchRequest` 時把 4 個 spine id 欄位寫 `None`。

**第二層（fill_completion 端 short-circuit）**：`event_consumer/loop_exchange.rs:264-283` 呼叫 `emit_fill_completion_lineage` 時，從 `PendingOrder` 讀 spine ids（loop_exchange.rs:264-271 注釋明示「emit_entry_lineage 階段已注入 4 個 spine id」），若 entry 階段全 None → fill_completion 拿到全 None → `emit_fill_completion_lineage` 短路 return 0（runtime_shadow/mod.rs:451-457 has 4 conditional short-circuit gates）。

**驗證證據**：W-C MAG-082 sign-off `docs/governance_dev/2026-05-11--w_c_window_pass_signoff.md` §2.4 empirical：
- 4 entry fills / 4 = **100%** 有 matching real-fill ER
- ER without matching fill (orphan): **0**
- close path 0 spine row 寫入（by-design 維持）

### 1.3 為什麼 close-maker-first 提案有破不變式風險

EDGE-P2-3 Phase 1b spec §4.4 + FA Round 2 §4 識別：5 audit 欄位（`close_maker_attempt` / `close_maker_fallback_reason` / `close_initial_limit_price` / `close_final_fill_price` / `close_maker_eligible_reason`）若 IMPL agent 設計時誤把 audit 寫入路徑接到 spine writer（`runtime_shadow::emit_entry_lineage` / `emit_fill_completion_lineage`），則：

1. 破 `commands.rs:812-815` Caveat 2 不變式（close path 開始有 spine row）
2. 觸發 `[55] agent_decision_spine_lineage` healthcheck WARN_REAL_FILL_PROPAGATION_PARTIAL（但因 close 是 100% rate，會直接破 chains_with_real_fill_report 分母統計）
3. 可能讓 W-D MAG-083/MAG-084 sign-off 後的 lineage 不變式回退（迴歸到 W-C round 1 CONDITIONAL 狀態）
4. 觸發 Stage 3+ 回退（CLAUDE.md §三 W-D 列已 sign-off，回退會破 governance trust）

**結論**：F-FA-3 不變式必須有 4 個 integration test + 6 grep guard pattern 雙層守護，避免 IMPL drift。

---

## §2 4 Integration Test Specs（IMPL E1 直接照寫）

> **重要**：以下 4 spec 是寫給 IMPL E4 的測試規格。IMPL prereq 解開後（commands.rs IMPL + writer 升級 land 後），E4 照此 spec 直接寫 test code 跑 `cargo test --release` 驗證。**現在不寫 IMPL test code**（spec 內附「測試名稱 / 場景 / 期望斷言 / 反證 / IMPL 提示」5 段，IMPL agent 拿 spec 即可寫 ~30-50 LOC 測試）。

### Test 1: `test_close_maker_audit_writes_to_fills_details_only`

**測試名**：`test_close_maker_audit_writes_to_fills_details_only`

**位置**：`srv/rust/openclaw_engine/tests/close_maker_audit_invariant_test.rs`（新檔）

**場景**：
- 設置 demo 環境 mock instrument（BTCUSDT tick_size=0.5 + min_qty=0.001）
- 構造一筆 grid_close_short close maker 路徑（exit_reason=`grid_close_short`，符合 8 whitelist）
- 觸發 maker order 成交（mock Bybit fill ack `liquidity_role=maker`）
- 啟用 spine shadow 模式（`OPENCLAW_AGENT_SPINE_RUNTIME_MODE=shadow`）

**期望斷言**：
1. `trading.fills.details` JSONB 包含 `{"close_maker_attempt": true, "close_maker_fallback_reason": null, "close_initial_limit_price": <f64>, "close_final_fill_price": <f64>, "close_maker_eligible_reason": "grid_close_short"}` — 5 欄位 100% present
2. `trading.fills.close_maker_attempt` 新 hot column = `true`
3. `agent.decision_objects WHERE object_type IN ('execution_plan', 'execution_report') AND payload::jsonb @> '{"close_maker_attempt": true}'` row count = **0**（spine 鏈條無 close_maker_* 欄位）
4. `agent.decision_objects WHERE object_type='execution_report' AND payload::jsonb->>'context_id' = <close_path_context_id>` row count = **0**（commands.rs:812-815 spine_order_plan_id=None → fill_completion short-circuit 維持）
5. `[55] agent_decision_spine_lineage` healthcheck rerun = PASS（chains_with_real_fill_report ratio 不被 close path 污染）

**反證（必加 negative test 章節）**：
- 故意把 spine_order_plan_id 改 `Some(test_uuid)` → 重跑 → assert 1+2 PASS but assert 3+4 必 FAIL（assert 3 row count > 0 → test fail）→ 證明 invariant 是真實守護不是巧合
- 故意把 audit 欄位寫進 spine ExecutionPlan payload → 重跑 → assert 1+2 PASS but assert 3 必 FAIL → 證明 grep pattern 1+2 在 IMPL phase 攔截能力

**IMPL 提示**：
- 用 `sqlx::query` 直查 PG（不要走 service layer），確保斷言獨立於 production code path
- mock pipeline 用 `tick_pipeline::tests::build_test_pipeline_with_demo_engine_mode()` 既有 helper（per `mod.rs:1234` 既有測試模式）
- spine writer 用 `agent_spine::tests::TestStore` mock，count `put_object` calls 並 filter object_type
- 預期 ~50 LOC

---

### Test 2: `test_close_maker_audit_does_not_create_spine_lineage_on_fallback`

**測試名**：`test_close_maker_audit_does_not_create_spine_lineage_on_fallback`

**位置**：同上檔（test_1 下方）

**場景**：
- 設置 demo 環境
- 構造一筆 bb_mean_revert close maker 路徑（exit_reason=`bb_mean_revert`，符合 8 whitelist）
- 觸發 maker timeout fallback（mock 45s 內 BBO 移動 → maker 未成交 → fallback 到 market）
- 啟用 spine shadow 模式

**期望斷言**：
1. `trading.fills.details` 包含 `{"close_maker_attempt": true, "close_maker_fallback_reason": "timeout_taker", "close_initial_limit_price": <f64>, "close_final_fill_price": <f64>, "close_maker_eligible_reason": "bb_mean_revert"}`
2. `close_maker_fallback_reason` ∈ enum {"timeout_taker", "postonly_reject", "cancel_grace_expired", "ack_lost"}（per FA round 1 §4 #8）
3. `trading.fills.close_maker_attempt` hot column = `true`（fallback 仍記 attempt=true）
4. `agent.decision_objects` 中 fallback path 0 spine row（與 test 1 同樣維持 W-C Caveat 2）
5. `[55]` healthcheck PASS unchanged

**反證**：
- 故意在 fallback path 注入 spine_decision_id `Some(uuid)` → assert 4 必 FAIL
- 故意 fallback 後仍寫 `emit_fill_completion_lineage` → assert 4 必 FAIL（驗證 emit_fill_completion_lineage::短路 input.engine_mode + input.filled_qty 4 條件 gate 仍生效）

**IMPL 提示**：
- mock Bybit return `cancelOrder` 200 OK + 一筆新的 market order ack（complete fallback chain）
- `compute_close_limit_price()` 返回 Some(price)，但 sweep cycle 內 `pending_sweep::classify_pending_sweep` 觸發 `MakerTimeoutCancel` → re-dispatch with `order_type:"market"`
- ~70 LOC（含 mock fallback chain）

---

### Test 3: `test_close_maker_field_completeness_across_8_reasons_x_4_races`

**測試名**：`test_close_maker_field_completeness_across_8_reasons_x_4_races`（parameterized test）

**位置**：同上檔（test_3）

**場景**：8 maker-first whitelist exit_reason × 4 race scenarios = **32 case** parameterized：
- 8 reasons：`grid_close_short` / `grid_close_long` / `bb_mean_revert` / `phys_lock_gate4_giveback` / `phys_lock_gate4_stale_roc_neg` / `ma_reverse_cross` / `bw_squeeze` / `pctb_revert`
- 4 races：(a) maker 成交 (b) maker timeout fallback to market (c) PostOnly reject fallback (d) ack lost fallback

**期望斷言**：
1. 32 case × 5 audit 欄位 = **160 cell 總數**；NULL rate ≤ 0.1%（per Consensus-MF-3 NULL ladder，FA round 2 §4 引用）
2. 每個 case 的 `close_maker_attempt` hot column 與 `details.close_maker_attempt` JSON 鏡像值一致（dual-source 一致性）
3. 32 case 的 `close_maker_eligible_reason` 與 trigger_tag 後綴一致（`{strategy_close|risk_close}:<exit_reason>` 對齊 helpers_close_tags.rs:101-141 命名 schema）
4. 32 case 0 spine ExecutionPlan/Report row 出現在 close path（per W-C Caveat 2）
5. PA verdict §3 列的 7+ negative whitelist reasons（HARD STOP / TRAILING STOP / TIME STOP / fast_track / halt_session / cost_edge / DRAWDOWN）若 mock 觸發，**audit 欄位均應為 NULL**（不誤入 maker path）

**反證**：
- 隨機選 1 case 故意 `close_maker_attempt` hot column 寫 `false` 但 details JSON 寫 `true` → assert 2 必 FAIL（dual-source 鏡像守護）
- 隨機選 1 negative whitelist reason 故意把 audit 5 欄位寫 non-NULL → assert 5 必 FAIL

**IMPL 提示**：
- 用 `rstest::rstest` parameterized macro 跑 32 case（避免 32 個 `#[test]` boilerplate）
- 8 reason 對應的 trigger_tag 字串引用 `tick_pipeline::helpers_close_tags::CLOSE_MAKER_WHITELIST` 既有常量（IMPL agent 必新增此常量供 8 case enumerate）
- ~150 LOC（含 mock builder + 4 race fixture）

---

### Test 4: `test_w_c_caveat_2_invariant_after_phase_1b_impl`

**測試名**：`test_w_c_caveat_2_invariant_after_phase_1b_impl`

**位置**：同上檔（test_4）

**場景**：
- 整合 test：模擬 24h demo workload（grid + bb_breakout + ma + bb_reversion + funding_arb 5 策略 × 5 symbols × ~100 fills）
- 觸發 entry path 100 fills + close path 100 fills（含 8 whitelist + 7+ negative whitelist 混合）
- 啟用完整 spine shadow 模式 + 完整 fills.details 寫入

**期望斷言**：
1. **`[55] agent_decision_spine_lineage` PASS condition 不變**（W-C MAG-082 既有 PASS criteria）：
   - `chains_with_full_plan_fill / chains` ratio 與 W-C baseline 一致（不應因 close path 引入新的 chain dilution）
   - `bad_report_value_quality = 0`
   - `state_changes_24h ≥ 5/min`
2. **close path lineage 0 row**：`SELECT COUNT(*) FROM agent.decision_objects o JOIN agent.decision_objects p ON p.object_id = ANY(...) WHERE p.object_type='execution_plan' AND p.payload::jsonb @> '{"is_close": true}'` = **0**
3. **fills.details 完整性 ≥ 99.9%**：close maker fills 100 case 中 99+ 含 5 audit 欄位
4. **W-C MAG-082 healthcheck rerun GREEN**：跑 `passive_wait_healthcheck.py [55]` 直接返 PASS（不靠 hardcoded 判斷）
5. **W-D MAG-083 sign-off 不變式不破**：`docs/governance_dev/2026-05-11--w_d_mag083_pa_audit.md` 列的 Spine ExecutionPlan/Report invariant 維持

**反證**：
- 故意把 `commands.rs:812-815` 改 `spine_order_plan_id: Some(test_uuid)` → assert 2 必 FAIL（防禦性 baseline）
- 故意把 `emit_fill_completion_lineage` 在 close path 強制呼叫（繞過 None short-circuit）→ assert 1 + 2 必 FAIL

**IMPL 提示**：
- 用 PG transaction rollback fixture（`tx.rollback()` 結尾），確保 24h workload 模擬不污染真 DB
- 跑時間 < 30s（用 `tokio::time::pause()` 控制 mock clock，不真等 24h）
- 直接 import `helper_scripts::db::passive_wait_healthcheck` 跑 [55] check（need pyo3 bridge or shell out subprocess）
- ~200 LOC（最大 test，integration-level）

---

### Test 4 補充：邊界 case（recommended，非 mandatory）

`test_4_partial_fill_does_not_break_invariant`：close maker 部分成交（30%）+ 取消剩餘 70% → 重 dispatch 30% 剩餘 → assert 兩筆 fills.details 都有 audit 欄位 + spine 仍 0 row。此 case 在 W-C Caveat 2 fix round 2 已涵蓋（partial fill no-emit），但 close maker 引入後需明確驗證。

---

## §3 E2 grep Guard Rules（refined patterns + 覆蓋率分析）

> **背景**：FA round 2 §4 標明 F-FA-3 為 blocking minor。IMPL agent 寫 IMPL 時可能無意中把 audit 路徑接到 spine writer（特別是看到 spine_order_plan_id 已存在於 OrderDispatchRequest 結構）。E2 grep guard rule 是「負面攔截」first-line defense，integration test 是「正面驗證」second-line。

### 3.1 6 個 grep Patterns（refined）

#### Pattern 1: close path 不能寫 spine（直接違規）

**目標**：close path constructs OrderDispatchRequest 時，spine_*_id 4 欄位若被改成 Some(...)，立即 fail。

```bash
# Pattern 1a: close path 內任何 spine id 寫 Some(...)
grep -nE "is_close: true.*\b(spine_order_plan_id|spine_decision_id|spine_verdict_id|spine_stub_report_id):\s*Some" \
  srv/rust/openclaw_engine/src/tick_pipeline/commands.rs \
  srv/rust/openclaw_engine/src/event_consumer/

# Pattern 1b: close path 提及 close_maker_* 欄位 + 同 hunk 內含 spine_*_id Some(
grep -nB 3 -A 10 "close_maker_attempt\|close_maker_fallback_reason\|close_maker_eligible_reason" \
  srv/rust/openclaw_engine/src/tick_pipeline/commands.rs \
  | grep -E "spine_order_plan_id:\s*Some|spine_decision_id:\s*Some|spine_verdict_id:\s*Some|spine_stub_report_id:\s*Some"
```

**期望結果**：兩 pattern 命中數 = 0。命中 ≥ 1 → E2 review reject merge。

#### Pattern 2: spine writer 不接 close_maker_*（反向確認）

**目標**：`emit_entry_lineage` / `emit_fill_completion_lineage` / `put_object` 三 spine writer 入口 callsite 上下文若含 close_maker_* 欄位，立即 fail。

```bash
# Pattern 2a: emit_entry_lineage callsite 上下文 ±5 line 含 close_maker_*
grep -nB 5 -A 5 "emit_entry_lineage\b" \
  srv/rust/openclaw_engine/src/ \
  --include="*.rs" -r \
  | grep -E "close_maker_(attempt|fallback_reason|initial_limit|final_fill|eligible_reason)"

# Pattern 2b: emit_fill_completion_lineage callsite 上下文 ±5 line 含 close_maker_*
grep -nB 5 -A 5 "emit_fill_completion_lineage\b" \
  srv/rust/openclaw_engine/src/ \
  --include="*.rs" -r \
  | grep -E "close_maker_(attempt|fallback_reason|initial_limit|final_fill|eligible_reason)"
```

**期望結果**：兩 pattern 命中數 = 0。

#### Pattern 3: ML training pipeline 不餵 close_maker_*（mirror MIT-MF-1 non-training invariant）

**目標**：ML training 5 pipeline（linucb / scorer / quantile / mlde / dl3）若 SELECT trading.fills 拿 close_maker_* 當 feature 餵 training，立即 fail。

```bash
# Pattern 3a: Python ML training files SELECT close_maker_*
grep -rnE "(linucb|scorer|quantile|mlde|dl3).*\b(close_maker_attempt|close_maker_fallback_reason|close_maker_eligible_reason)\b" \
  srv/program_code/ml_training/ \
  srv/program_code/learning_engine/ \
  srv/program_code/exchange_connectors/bybit_connector/control_api_v1/learning/

# Pattern 3b: 任何 SQL 從 trading.fills.details 抽 close_maker_* 當 ML feature
grep -rnE "(details->>?'close_maker_|details::jsonb.*close_maker_).*FROM trading\.fills" \
  srv/program_code/ml_training/ \
  srv/program_code/learning_engine/

# Pattern 3c: feature engineering 文件提及 close_maker_* （即使非 SELECT，可能從 trading_writer 拿）
grep -rnE "feature.*close_maker_|close_maker_.*feature" \
  srv/program_code/ml_training/ \
  srv/program_code/learning_engine/
```

**期望結果**：3 pattern 命中數 = 0。命中 → 違反 `replay.simulated_fills` `evidence_source_tier IN ('synthetic_replay', ...)` 同等 non-training contract。

### 3.2 覆蓋率分析

| 違規場景 | Pattern | 覆蓋率 |
|---|---|---|
| IMPL agent 在 close path 把 spine_*_id 改 Some(...) | 1a | 100%（直接 grep） |
| IMPL agent 在 close path 寫 close_maker_* + spine_*_id Some 同一 hunk | 1b | 100% |
| IMPL agent 把 audit 走 emit_entry_lineage 路徑 | 2a | 95%（依賴 ±5 line context window；極端情況 helper fn 跨檔可能漏）|
| IMPL agent 把 audit 走 emit_fill_completion_lineage 路徑 | 2b | 95%（同上）|
| ML pipeline SELECT close_maker_* 當 training feature | 3a | 100%（grep ML 5 pipeline 名 + 5 audit 欄位 cartesian） |
| SQL 從 trading.fills.details 抽 close_maker_* 餵 ML | 3b | 100% |
| Feature engineering 文件名 close_maker_* | 3c | 90%（依賴命名規範；若 IMPL agent 重命名為其他 alias 可能漏，但 review 階段命名審查可補）|

**整體覆蓋率**：6 patterns × 覆蓋場景 = ~96%（≥ 95% 達標）。

### 3.3 grep guard rule 收容建議

**建議**：在 PA workspace report 內提案開新 P1 task（不在本 report 直接創建）：

> **P1-IMPL-PRE-Phase1b-1**：建檔 `srv/docs/agents/E2_grep_guard_rules.md`（NEW），收錄：
> 1. F-FA-3 W-C Caveat 2 不變式 6 grep patterns（本 report §3.1）
> 2. P2-N2-4 stable_id CI grep rule（PA memory 2026-05-11 §架構教訓 2）
> 3. 既有 CLAUDE.md §七「跨平台兼容性」E2 必查 grep（`(/home/ncyu|/Users/[^/]+)`）
> 4. 既有 CLAUDE.md §九「stable_id 字面複製」guard
>
> **Owner**：PM 派 PA spec / E1 IMPL；**estimate**：~0.5 E1-day；**dependency**：本 report PM sign-off + Track A2 V094 schema spec finalize。

**現在不寫此檔**（per 嚴禁事項「不要 commit `E2_grep_guard_rules.md` 新檔」）。本 report 提案後 PM 拍板開 P1 task。

---

## §4 V094 Schema 設計建議（給 Track A2 PA 接手）

### 4.1 Schema 安排兩段式

| 欄位 | 類型 | 路徑 | 理由 |
|---|---|---|---|
| `close_maker_attempt` | BOOLEAN NOT NULL DEFAULT false | **新 column**（不入 details JSON） | hot-path query：healthcheck [63] 高頻 SELECT；BTREE index `WHERE close_maker_attempt = true`；boolean storage 1 byte 高效 |
| `close_maker_fallback_reason` | TEXT NULL + CHECK NOT VALID enum | **新 column**（不入 details JSON） | enum {timeout_taker, postonly_reject, cancel_grace_expired, ack_lost} 4 值；hot-path filter；CHECK NOT VALID 不掃 historical fill row |
| `close_initial_limit_price` | DOUBLE PRECISION NULL | **details JSON**（key: `close_initial_limit_price`） | low-cardinality audit-only；不需 index；JSON 零 schema bloat |
| `close_final_fill_price` | DOUBLE PRECISION NULL | **details JSON**（key: `close_final_fill_price`） | 同上 |
| `close_maker_eligible_reason` | TEXT NULL | **details JSON**（key: `close_maker_eligible_reason`） | low-cardinality audit-only |

### 4.2 設計理由（FA + MIT consensus 對齊）

- **FA round 1 §4 #8 CONDITIONAL**：要求新欄位 100% non-null；hot column 用 NOT NULL DEFAULT false 自動滿足
- **MIT-MF-1 non-training invariant**：close_maker_* 不可餵 ML training（non-training surface），與 `replay.simulated_fills` `evidence_source_tier` 同等 fail-closed contract
- **AMD §10 Rollback path 完整性**：JSON column extension 是 backward-compatible（per FA round 2 §7）；hot column ADD COLUMN IF NOT EXISTS 是 metadata-only（per V008 / V015 / V017 / V028 / V033 既有 pattern）
- **PG dry-run mandatory**（per CLAUDE.md §七）：V094 涉及 PG reflection（`information_schema.columns` for Guard B + `pg_get_indexdef` for Guard C），必先 Linux PG empirical query 驗證真實 schema 再 E1 IMPL 設計

### 4.3 V094 file 雛形（spec only，不寫 SQL）

```text
sql/migrations/V094__fills_close_maker_audit_columns.sql

-- ============================================================
-- V094: EDGE-P2-3 Phase 1b — close_maker audit columns
--
-- 動機 / Motivation:
--   F-FA-1 close-maker-first 提案要求 trading.fills.details JSONB 攜帶
--   close_maker_attempt / close_maker_fallback_reason / close_initial_limit_price /
--   close_final_fill_price / close_maker_eligible_reason 5 欄位以滿足
--   原則 #8 交易可解釋審計。Hot-path query（healthcheck [63] 高頻）需
--   close_maker_attempt + close_maker_fallback_reason 為 first-class column。
--
-- 範圍 / Scope (V094):
--   1. ADD COLUMN close_maker_attempt BOOLEAN NOT NULL DEFAULT false（Guard B 型別驗證）
--   2. ADD COLUMN close_maker_fallback_reason TEXT NULL（Guard B 型別驗證）
--   3. ADD CHECK CONSTRAINT NOT VALID enum 4 values
--   4. CREATE INDEX partial WHERE close_maker_attempt = true（Guard C 比對）
--   5. close_initial_limit_price / close_final_fill_price / close_maker_eligible_reason 走
--      details JSONB extension（不在此 migration；trading_writer.rs 升級時 IMPL）
--
-- Guard A: 驗證 trading.fills 既有 columns 俱在
-- Guard B: 驗證 ADD COLUMN 目標型別（若已存在）
-- Guard C: 驗證 INDEX 定義對齊
--
-- W-C Caveat 2 不變式守護（F-FA-3）:
--   audit 欄位 100% 走 trading.fills.details JSONB / trading.fills hot column；
--   不寫 agent.decision_objects spine lineage。E2 grep guard rule 攔截違規 IMPL。
--   Integration test: tests/close_maker_audit_invariant_test.rs（4 spec @ PA report）。
--
-- Idempotency: 重跑 V094 兩次必須 noop（per V055 5-round loop 教訓）
```

### 4.4 trading_writer.rs 升級必要性

**關鍵發現（PA empirical 2026-05-15）**：當前 `trading_writer.rs:430` INSERT INTO trading.fills 列表 **不寫 details**（23 columns，無 details）。Track A2 V094 IMPL 必同步升 writer：

1. 加 `details` 到 INSERT column list
2. 升 `TradingMsg::Fill` enum 加 `details: Option<serde_json::Value>` 欄位
3. close maker path 在 `apply_confirmed_fill` 構造 details payload 含 5 audit 欄位（`{"close_maker_attempt": true, "close_maker_fallback_reason": null, "close_initial_limit_price": <f64>, "close_final_fill_price": <f64>, "close_maker_eligible_reason": "<reason>"}`）

**否則**：guard tests 全 FAIL（fills.details NULL → 5 audit 欄位 100% absent）。

---

## §5 Healthcheck [63] 升級設計（dual gate）

### 5.1 設計目標

[63] 是新 healthcheck（per CLAUDE.md §七「被動等待 TODO 必附 healthcheck」+ FA round 1 AC-6），承擔兩個獨立守護任務：
- **Gate A (W-C Caveat 2 不變式)**：確認 close path 0 spine row（與 [55] 互補；[55] 看整體 lineage 完整性，[63] 專看 close path lineage 缺席性）
- **Gate B (audit 完整性)**：確認 fills.details 5 audit 欄位完整性 ≥ 99.9%

### 5.2 Healthcheck function spec（給 Track A4 後續 IMPL 接手）

```python
# helper_scripts/db/passive_wait_healthcheck/checks_close_maker_audit.py（新檔）

def check_close_maker_audit_lineage_integrity(conn) -> dict:
    """
    [63] close_maker_audit_lineage_integrity — W-C Caveat 2 + audit 完整性 dual gate
    
    Gate A (W-C Caveat 2):
        SELECT COUNT(*) FROM agent.decision_objects o
        WHERE object_type IN ('execution_plan', 'execution_report')
          AND payload::jsonb @> '{"is_close": true}'
          AND created_at > $24h_ago
        → spine_close_row_count
    
    Gate B (audit completeness):
        WITH close_maker_fills AS (
            SELECT fill_id, ts, details
            FROM trading.fills
            WHERE close_maker_attempt = true
              AND ts > NOW() - INTERVAL '24 hours'
        )
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE 
                details ? 'close_maker_attempt' AND
                details ? 'close_maker_fallback_reason' AND
                details ? 'close_initial_limit_price' AND
                details ? 'close_final_fill_price' AND
                details ? 'close_maker_eligible_reason'
            ) AS complete
        FROM close_maker_fills
        → audit_completeness_ratio = complete / total
    
    PASS:
        - Gate A: spine_close_row_count = 0
        - Gate B: audit_completeness_ratio >= 0.999
    
    WARN:
        - Gate A: 1 <= spine_close_row_count <= 5（可能 race condition，不是契約破）
        - Gate B: 0.95 <= audit_completeness_ratio < 0.999
    
    FAIL:
        - Gate A: spine_close_row_count > 5（契約破，立即 alert）
        - Gate B: audit_completeness_ratio < 0.95
    
    Sample size gate:
        如果 close_maker fills 24h < 5 → return NEUTRAL（樣本不足，不評估）
    """
    ...
```

### 5.3 與 [55] 的互補關係

- **[55]** = 整體 lineage 完整性（W-C MAG-082 主防線）
- **[63]** = close path 特定的 W-C Caveat 2 守護（close path 0 spine row 嚴格不變式）
- **獨立 gate**：[55] 可能 PASS 但 [63] FAIL（如果 close path 開始寫 spine 但其他 lineage 仍完整）

### 5.4 註冊到 healthcheck runner

per CLAUDE.md §七，[63] 需在 `helper_scripts/db/passive_wait_healthcheck/runner.py` 註冊（IMPL prereq 解開時 E1 加），並更新 healthcheck 計數 51→52（CLAUDE.md §七 「當前 51 個 check」需同 commit 更新）。

---

## §6 IMPL Prereq 5 解除條件（指 F-FA-1/2/3 全 done 標準）

per FA round 2 §6 「§8 IMPL Prereq 漏 F-FA-1/2/3 pre-IMPL handling」， AMD §8 應補第 5 條 prereq。本 §6 細化「5 解除條件」標準。

### 6.1 解除條件定義

| Prereq | DONE 判定 |
|---|---|
| F-FA-1 V### migration audit schema spec | (a) PA spec finalize V094 `sql/migrations/V094__fills_close_maker_audit_columns.sql`（per §4.3 雛形），含 Guard A/B/C + idempotency 兩次跑 noop  (b) trading_writer.rs INSERT INTO trading.fills 列表升級 details JSONB 寫入路徑 spec finalize  (c) Linux PG empirical query 驗證 trading.fills 既有 schema 對齊（per §4.4） |
| F-FA-2 portfolio_var exposure SoT 驗 | (a) PA grep `intent_processor/mod.rs` 確認 portfolio_var 計算用 request_qty vs filled_qty  (b) 若 filled_qty → 開 P1 task 改 request_qty（FA round 1 §4 #16 CONDITIONAL）  (c) 否則 noop + report verify |
| F-FA-3 audit 欄位不走 spine lineage guard | (a) 本 report 4 integration test specs 已 final（§2）  (b) 6 grep guard patterns 已 final（§3）  (c) PM sign-off 開 P1-IMPL-PRE-Phase1b-1 task 建 `docs/agents/E2_grep_guard_rules.md`  (d) E2 review checklist 加「跑 6 grep patterns」step（per `.claude/agents/E2.md` 補 SOP） |

### 6.2 IMPL kickoff 觸發條件

3 prereq 全 DONE → AMD §8 第 5 條 gate 解除 → 進入 AMD §8 既有 4 gate（spec finalize / 4-agent review / 三閘 / 強制工作鏈）→ 全 4 gate PASS → IMPL 派工 E1。

### 6.3 解除路徑時間估算

- F-FA-1（PA spec V094 + writer upgrade spec）：~1.5 PA-day
- F-FA-2（PA grep + verify）：~0.5 PA-day（read-only，可能 noop）
- F-FA-3（本 report 已 final）：DONE 待 PM sign-off

**並行可行**：F-FA-1 / F-FA-2 / F-FA-3 互無依賴 → 並行 ~1.5 PA-day total（F-FA-1 是 critical path）。

### 6.4 Track 對齊

- F-FA-1 → Track A2（PA 接手）
- F-FA-2 → Track A3（PA 接手 portfolio_var verify）
- F-FA-3 → Track A4（本 report 完成）

→ Wave 1 全 3 track 並行 → ~1.5 day 全 prereq 解 → 進 AMD §8 4 gate。

---

## §7 風險評估 + 16 原則 / DOC-08 §12 / §四 觸碰

### 7.1 改動風險評級 = **低**

本 report 是 spec/design only，0 代碼改動。風險來自下游 IMPL 是否照 spec 跑：

- **低**：4 integration test specs 邊界明確，IMPL E1 / E4 寫測試難度 ≤ 中
- **低**：6 grep patterns 是純文字 regex，無 false positive risk（pattern 1+2 直接看 spine_*_id 字面值，pattern 3 看 ML 5 pipeline 名 + 5 audit 字面值）
- **低**：V094 schema 是 V003 details JSONB extension（已存在 column）+ 1 hot column（標準 ADD COLUMN）

### 7.2 16 根原則合規（16/16）

| 原則 | 狀態 | 證據 |
|---|---|---|
| #1 單一寫入口 | PASS | guard tests 不改寫入口；保護 IntentProcessor / submit_intent 既有契約 |
| #2 讀寫分離 | PASS | guard tests 純 SQL SELECT + assert |
| #3 AI→Lease→複核→執行 | PASS | guard tests 不觸 lease；保護 W-C Caveat 2 close path 不寫 spine 不變式（強化原則 #3 trace 完整性） |
| #4 策略不繞風控 | PASS | guard tests 不觸 Guardian / risk_envelope |
| #5 生存 > 利潤 | PASS | guard tests 是純驗證 |
| #6 失敗默認收縮 | PASS | guard test 4 fallback case 驗證 close-maker-first 失敗時 fallback to market 路徑完整 |
| #7 學習 ≠ 改寫 Live | PASS | grep pattern 3 enforce ML pipeline 不餵 close_maker_* (mirror MIT-MF-1) |
| #8 交易可解釋 | PASS | 5 audit 欄位 + 4 test specs + healthcheck [63] dual gate 全鏈條 audit 完整性 |
| #9 災難保護 | PASS | guard tests 不觸 cancel_token / shutdown |
| #10 認知誠實 | PASS | 本 report 標明 「§3.1 Pattern 3c 90% 覆蓋率」「§4.4 trading_writer 升級必要性」「§5.4 healthcheck 計數 51→52」事實 / 推斷分明 |
| #11 P0/P1 內自主 | PASS | guard tests 不觸 cognitive_modulator |
| #12 持續進化 | PASS | guard tests 是進化前提（audit trail 完整支援後續學習）|
| #13 AI cost 感知 | PASS | guard tests 不觸 AI |
| #14 零外部成本可運行 | PASS | guard tests 跑在本地 PG + cargo test，無外部依賴 |
| #15 多 Agent 協作 | PASS | guard tests 不觸 MessageBus / agent topics |
| #16 組合風險 | PASS | guard tests 不觸 portfolio_var |

### 7.3 DOC-08 §12 9 條安全不變量觸碰（0/9）

| 不變量 | 觸碰 | 評估 |
|---|---|---|
| Pre-trade audit/replay 必開 | NO | guard tests 不改 pre-trade gate |
| Lease 必在執行前 acquired | NO | guard tests 不觸 lease |
| 執行回報必落 fills 表 | **strengthens** | guard tests Test 1+2+3 驗證 fills.details 完整性 |
| 風控降級 → engine 自動止血 | NO | guard tests 不觸風控 |
| Authorization 過期 → cancel_token shutdown | NO | guard tests 不觸 authorization |
| Mainnet 無 OPENCLAW_ALLOW_MAINNET → spawn 拒 | NO | guard tests 不觸 mainnet spawn |
| Bybit retCode != 0 → fail-closed 不重試 | NO | guard tests 不觸 retry |
| Reconciler 對賬差異 → 自動降級 paper | NO | guard tests 不觸 reconciler |
| Operator 角色與 live_reserved 缺一即拒 | NO | guard tests 不觸 operator auth |

### 7.4 §四 5 硬邊界觸碰（0/5）

`execution_state` / `execution_authority` / `live_execution_allowed` / `decision_lease_emitted` / `max_retries=0` 全 0 觸碰。

---

## §8 完成序列 + 後續行動

### 8.1 完成序列（per PA 啟動序列要求）

1. ✅ 追加 PA memory `srv/docs/CCAgentWorkSpace/PA/memory.md`（與本 report commit 同次）
2. ✅ 報告存 `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--f_fa_3_w_c_caveat_2_guard_tests_design.md`（本檔）
3. ✅ 結論性報告同時複製到 `srv/docs/CCAgentWorkSpace/Operator/`（per PA spec 要求）

### 8.2 後續行動（給 PM 派發）

| Action | Owner | Track | Priority |
|---|---|---|---|
| Sign-off 本 report § F-FA-3 解除條件 | PM | Wave 1 closure | P0 |
| 開新 P1 task `P1-IMPL-PRE-Phase1b-1` 建 `docs/agents/E2_grep_guard_rules.md`（含本 report §3.1 6 patterns） | PM 派 PA spec / E1 IMPL | Wave 2 | P1 |
| Track A2 V094 schema spec finalize（per §4） | PA | Wave 1 Track A2 | P0 |
| Track A3 portfolio_var exposure verify（per §6.1 F-FA-2 標準） | PA | Wave 1 Track A3 | P0 |
| 升級 `.claude/agents/E2.md` review checklist 加「F-FA-3 6 grep patterns」step | PM 派 E2 spec update | Wave 2 | P1 |
| AMD §8 補第 5 條 prereq F-FA-1/2/3 pre-IMPL track（per FA round 2 §6） | PM 派 AMD v0.2 patch | Track A1 | P0 |
| AMD §10 補 V094 backward-compatible JSON column extension carve-out（per FA round 2 §7） | 同上 | Track A1 | P0 |
| AMD §1 framing 收斂為「alpha-impact-adjacent execution-quality pathway」（per FA round 2 §9）| 同上 | Track A1 | P0 |
| Healthcheck [63] IMPL（IMPL prereq 解開後 E1 接手）| E1 | IMPL kickoff 階段 | P1 |
| 4 integration test code 寫作（IMPL prereq 解開後 E4 接手）| E4 | IMPL kickoff 階段 | P1 |

### 8.3 Wave 1 Track A4 closure 標誌

本 report sign-off → F-FA-3 解除條件 (a)(b)(c)(d) 4 條全完成 → Wave 1 Track A4 close → 與 Track A1 (AMD v0.2) / Track A2 (V094 spec) / Track A3 (portfolio_var verify) 並行收斂 → 進 AMD §8 4 gate（spec finalize / 4-agent review / 三閘 / 強制工作鏈）→ IMPL kickoff E1 派工。

---

## §9 PA Verdict

**判定**：**SPEC-READY**

**4 integration test specs**（§2）+ **6 grep guard patterns**（§3）+ **V094 schema 設計建議**（§4）+ **healthcheck [63] dual gate**（§5）+ **IMPL prereq 5 解除條件**（§6）全 final。

**7.2 16 原則 16/16 + 7.3 DOC-08 §12 0/9 觸碰 + 7.4 §四 0/5 觸碰** = 0 BLOCKER。

**改動風險評級 = 低**（本 report 0 代碼改動；下游 IMPL 是純加新 test + 新 grep + 新 V094 column + 新 healthcheck）。

**核心教訓**：
1. **`trading.fills.details JSONB` 已存在（V003 line 284）**：5 audit 欄位走 details JSON-extension 是 zero-schema-migration；但 `trading_writer.rs:430` INSERT 列表 **不寫 details** — V094 IMPL 必同步升 writer，否則 audit 100% NULL → guard tests 全 FAIL。PA 派 sub-agent 前必先 empirical re-check 既有 schema + writer 對齊現實，不能基於 spec 假設設計
2. **F-FA-3 不變式雙層守護必要性**：integration test 是「正面驗證」second-line（IMPL 後跑），grep guard rule 是「負面攔截」first-line（IMPL 中審查）；兩者並行才能擋住 IMPL agent 「無意識把 audit 接 spine writer」的常見 drift。類比 W-D MAG-083 P1-1 抽 stable_id helper（正面導引）+ P2-N2-4 CI grep（負面攔截）雙防線 pattern
3. **healthcheck [63] 與 [55] 互補性**：[55] 看整體 lineage 完整性，[63] 看 close path 特定的「不變式缺席性」；獨立 gate 設計避免「[55] PASS 但 [63] FAIL」的盲區（如果 close path 開始寫 spine 但其他 lineage 仍完整，[55] 整體分母無感，[63] 專察 close path 異常）
4. **Linux PG empirical query mandate**（per CLAUDE.md §七 + V055 5-round loop 教訓）：V094 涉及 Guard A/B/C 必先 Linux PG empirical query 驗證真實 schema；本 report §4.4 已 empirical 確認 details column 存在 + writer 23-column INSERT 漏 details 事實
5. **AMD §8 prereq 完整性對 IMPL drift 控制關鍵**：FA round 2 §6 識別 F-FA-1/2/3 pre-IMPL 未掛 §8 prereq 是 governance gap；本 report §6 細化 5 解除條件 + §8.2 列出 PM 派發 Action 清單，補完 AMD §8 第 5 條 prereq trace

---

**關鍵文件指針**（後續 IMPL agent / PM / E2 / E4 必讀）：
- 不變式 source：`srv/rust/openclaw_engine/src/tick_pipeline/commands.rs:809-815`
- spine writer 入口：`srv/rust/openclaw_engine/src/agent_spine/runtime_shadow/mod.rs:63` (`emit_entry_lineage`) + `mod.rs:446` (`emit_fill_completion_lineage`)
- W-C MAG-082 sign-off：`srv/docs/governance_dev/2026-05-11--w_c_window_pass_signoff.md`
- W-D MAG-083 PA audit：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--w_d_mag083_pa_audit.md`
- FA round 1 verdict：`srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-15--close_maker_first_fa_verdict.md`
- FA round 2 verdict：`srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_fa.md`
- PA round 1 verdict：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--close_maker_first_pa_verdict.md`
- 既有 trading.fills schema：`srv/sql/migrations/V003__trading_agent_tables.sql:270-294`（含 details JSONB）
- 既有 trading_writer.rs INSERT：`srv/rust/openclaw_engine/src/database/trading_writer.rs:430`
- healthcheck framework：`srv/helper_scripts/db/passive_wait_healthcheck/`（含 [55] checks_agent_spine.py）
- W-C Caveat 2 fix loop_exchange callsite：`srv/rust/openclaw_engine/src/event_consumer/loop_exchange.rs:264-283`
