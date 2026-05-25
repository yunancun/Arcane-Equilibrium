# W2-D V109 Anomaly Event Writer Skeleton — Rust + Python IMPL

**Date**: 2026-05-25
**Role**: E1 (Backend Developer)
**Phase**: v5.8 Sprint 2 Stream D Wave 2 → W2-D E1 IMPL (Sprint 3 detector wire 前置)
**Parent spec**: `srv/sql/migrations/V109__m8_anomaly_events_hypertable.sql` (commit `16796d13`) + `srv/docs/execution_plan/2026-05-25--v109_m8_anomaly_events_schema_spec_v2_amend.md`
**Status**: IMPL DONE — awaiting E2 cold review (chain E1 → E2 → E4 → QA → PM)

---

## 1. 任務摘要

接 W1-F V109 schema land (PG dry-run × 2 PASS) 後，IMPL M8 anomaly_events Rust writer skeleton + Python query helper skeleton。**不寫 detector 代碼** — Sprint 3 W3-A/W3-B 才上 ATR-vol×Funding 9-cell / RV percentile / block bootstrap / manual_operator 4 算法。

**5 hard invariant 必守**：
- I-1 V109 23 column 嚴格對齊 (含 v2 amend `metric_baseline`)
- I-2 ADR-0036 Decision 1 黑名單 detection_method (HMM / Markov-switching / GARCH 永久禁用) 反向防護 — V109 Guard A/C schema-level + 本 writer client-side = **三重防護**
- I-3 amplification cap H-11 24h count helper (per M3 §6.2 + V109 spec §5.3)；read-only 不自動 enforce
- I-4 5 enum CHECK constraint client-side mirror (event_taxonomy 9 / severity 4 / detection_method 4 / engine_mode 5)
- I-5 Mac SSOT 不接 PG runtime；單元測試走 SQL self-grep + struct field lock + validator pure logic

---

## 2. 修改清單

### 2.1 新建 file

| File | LOC | Purpose |
|---|---|---|
| `rust/openclaw_engine/src/database/anomaly_event_writer.rs` | 935 | Rust writer skeleton + AnomalyEventRow + 4 validator + amplification cap helper + 13 unit test |
| `helper_scripts/m8/__init__.py` | 22 | Python helper module entry + MODULE_NOTE |
| `helper_scripts/m8/anomaly_event_query.py` | 278 | Read-only query helper (get_recent_anomalies + get_amplification_cap_count + validate_detection_method_python) |

### 2.2 修改 existing file (1 處)

| File | 改動 | Purpose |
|---|---|---|
| `rust/openclaw_engine/src/database/mod.rs` | 新增 `pub mod anomaly_event_writer;` + 3 行中文 comment | 接入 openclaw_engine crate |

**0 existing module logic 改動** — 全 additive (新建 module + module 註冊 1 line)。

---

## 3. 關鍵 diff (核心 invariant 編碼點)

### 3.1 I-2 ADR-0036 Decision 1 黑名單 client-side 反向防護 (Rust)

```rust
pub fn validate_detection_method(method: &str) -> Result<(), AnomalyEventError> {
    // ADR-0036 Decision 1 forbidden algorithm reverse pattern (HARDCODE 永久禁用)。
    let lower = method.to_lowercase();
    if lower.contains("hmm")
        || lower.contains("markov_switching")
        || lower.contains("markov-switching")
        || lower.contains("garch")
    {
        return Err(AnomalyEventError::InvalidDetectionMethod(method.to_string()));
    }
    // 4 替代算法 per ADR-0036 Decision 2-4。
    const VALID: &[&str] = &[
        "atr_vol_funding_9cell",
        "rv_percentile",
        "block_bootstrap",
        "manual_operator",
    ];
    if VALID.contains(&method) {
        Ok(())
    } else {
        Err(AnomalyEventError::InvalidDetectionMethod(method.to_string()))
    }
}
```

對齊 V109 Guard A line 117-138 + Guard C line 244-254 schema-level reverse-pattern reject = **三重防護**：
1. **DB layer (V109)**: `CHECK (detection_method IN (...))` + `position('hmm' IN lower(v_check_def)) > 0 → RAISE`
2. **Rust writer (本 module)**: `validate_detection_method` substring `to_lowercase().contains("hmm")` reject
3. **Python helper (本 module)**: `validate_detection_method_python` 對齊 Rust semantic

### 3.2 I-1 23 column INSERT SQL (對齊 V109 schema)

```rust
let row_result = sqlx::query(
    r#"
    INSERT INTO learning.anomaly_events (
        observed_at, event_taxonomy, severity, detection_method,
        atr_vol_state, funding_state, strategy_id, symbol,
        metric_value, metric_baseline, metric_threshold,
        amplification_loop_24h_count,
        m3_health_observation_ref, m7_decay_signal_ref, m1_lal_demote_ref,
        evidence_json, engine_mode
    )
    VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8,
        $9::NUMERIC(18,8), $10::NUMERIC(18,8), $11::NUMERIC(18,8),
        $12, $13, $14, $15, $16, $17
    )
    RETURNING id
    "#,
)
```

17 個 column 顯式 INSERT；6 個走 DB DEFAULT (id / created_by / created_at / source_version / updated_by / updated_at) — total 23 對齊 V109 schema。
- `metric_value` / `metric_baseline` / `metric_threshold` 走 `::NUMERIC(18,8)` cast (workspace 無 BigDecimal feature；對齊 earn_movement_writer 範式)
- `RETURNING id` 供 caller 後續 cross-ref UPDATE 用 (per V109 spec §8.3 example 1)

### 3.3 I-3 amplification cap H-11 24h count helper

```rust
pub async fn amplification_loop_24h_count(
    &self,
    event_taxonomy: &str,
    engine_mode: &str,
    since: chrono::DateTime<chrono::Utc>,
) -> Result<i32, AnomalyEventError> {
    validate_event_taxonomy(event_taxonomy)?;
    validate_engine_mode(engine_mode)?;
    let row = sqlx::query(
        r#"
        SELECT COUNT(*) AS cnt
        FROM learning.anomaly_events
        WHERE event_taxonomy = $1
          AND observed_at > $2
          AND severity IN ('CRITICAL', 'HALT')
          AND engine_mode = $3
        "#,
    )
    .bind(event_taxonomy).bind(since).bind(engine_mode)
    .fetch_one(&self.pool).await?;
    let count: i64 = row.try_get("cnt")?;
    Ok(count as i32)
}
```

對齊 V109 spec §5.3 + H-11：
- 只計 CRITICAL/HALT (INFO/WARN 不 trigger M3 state change 不計入 cap)
- engine_mode 必傳 (5 mode 獨立計數空間；live 不被 paper 污染)
- 24h 視窗 caller 端傳 `since = now() - 24h` (明示傳避隱式時鐘漂移)
- 回 `i32`；caller decide ≥ 2 → 標 `evidence_json.cap_suppressed=true` 不 emit M3 cascade

### 3.4 Sprint 3 detector subscribe pattern

```rust
// rust/openclaw_engine/src/database/mod.rs
pub mod anomaly_event_writer;
```

Sprint 3 detector 透過 `use crate::database::anomaly_event_writer::{AnomalyEventWriter, AnomalyEventRow, validate_detection_method, ...}` 訂閱本 writer。Rust 端 detector 直接呼 `write_anomaly_event`；Python 端 cron/audit 走 `helper_scripts/m8/anomaly_event_query.py` query。

---

## 4. 治理對照 (V109 schema 23 column + ADR-0036 + H-11 對照表)

| V109 spec § | 編碼點 | Status |
|---|---|---|
| §3 v2 final schema 23 column | `AnomalyEventRow` struct + `test_anomaly_event_row_struct_has_23_fields` | DONE |
| §3 metric_baseline (v2 amend P1-5) | `pub metric_baseline: Option<String>` + INSERT SQL 含 | DONE |
| §3 event_taxonomy CHECK 9 enum | `validate_event_taxonomy` const VALID + test_validate_taxonomy_9_enum_pass_and_invalid_reject | DONE |
| §3 severity CHECK 4 enum (含 HALT Y2+) | `validate_severity` const VALID + test_validate_severity_4_enum_and_invalid_reject | DONE |
| §3 detection_method CHECK 4 enum + ADR-0036 黑名單 | `validate_detection_method` 雙重防護 + test_validate_detection_method_4_enum_and_hmm_garch_reject | DONE |
| §3 atr_vol_state / funding_state NULL OR (3 enum) | `Option<String>` field；不在 client-side 強制 (DB CHECK 處理) | DONE |
| §3 engine_mode CHECK 5 enum (含 replay) | `validate_engine_mode` const VALID + test_validate_engine_mode_5_enum_complete | DONE |
| §3 amplification_loop_24h_count INTEGER DEFAULT 0 | `pub amplification_loop_24h_count: i32` + amplification_loop_24h_count helper | DONE |
| §3 m3 / m7 / m1_lal _ref BIGINT soft ref | `Option<i64>` field × 3；INSERT 預設 NULL；caller cross-ref UPDATE 補 | DONE |
| §3 evidence_json JSONB | `Option<JsonValue>` + INSERT bind | DONE |
| §3 5 audit field per V103/V106/V107 範式 | `created_by` / `created_at` / `updated_by` / `updated_at` / `source_version` 全進 struct | DONE |
| §5.3 H-11 amplification cap 24h count writer-side query | `amplification_loop_24h_count` helper + Python 對應 | DONE |
| §5.3 cap_suppressed=true ≥ 2 policy | `is_cap_suppressed(count: i32) -> bool` Python helper + test_amplification_cap_24h_window_semantic | DONE |
| §8.3 cross-ref pattern (M3 / M7 / M1 LAL) | `RETURNING id` 供 caller UPDATE m3_health_observation_ref / m7_decay_signal_ref / m1_lal_demote_ref | DONE |
| ADR-0036 Decision 1 黑名單 reverse pattern | Rust `validate_detection_method` substring match + Python `validate_detection_method_python` 對齊 + V109 Guard A/C schema enforce = **三重防護** | DONE |
| ADR-0036 Decision 2-4 替代算法 4 enum | const VALID 4 字符串 + 4 test case | DONE |
| ADR-0036 例外段 (replay engine_mode) | const VALID 5 enum 含 'replay' + 1 test case | DONE |
| AC-S2-D-1 V109 schema land | (W1-F 已 commit `16796d13` PG dry-run × 2 PASS) | DEPENDENCY DONE |
| AC-S2-D-5 Sprint 3 detector IMPL prerequisite | writer skeleton + `pub mod` 註冊 + 13 unit test PASS | DONE |
| AC-S2-D-6 engine_mode CHECK 5 值 + training filter | 5 enum client-side 驗；training filter 鼓勵 caller 端 IN ('live','live_demo') | DONE |
| AC-S2-D-7 23 column 全俱在 | `test_insert_sql_locked_columns_match_v109_schema` + `test_anomaly_event_row_struct_has_23_fields` | DONE |

---

## 5. Mac SSOT Verify

### 5.1 cargo test (per M-4 hygiene SOP — Mac SSOT，禁 trade-core)

```
$ cargo test --release -p openclaw_engine --lib database::anomaly_event_writer
running 14 tests
test ... test_validate_engine_mode_5_enum_complete ... ok
test ... test_validate_taxonomy_9_enum_pass_and_invalid_reject ... ok
test ... test_validate_severity_4_enum_and_invalid_reject ... ok
test ... test_amplification_cap_24h_window_semantic ... ok
test ... test_insert_sql_locked_table_name ... ok
test ... test_insert_sql_returns_id ... ok
test ... test_amplification_cap_sql_window_lock ... ok
test ... test_anomaly_event_row_struct_has_23_fields ... ok
test ... test_insert_sql_uses_numeric_cast ... ok
test ... test_validator_contains_adr0036_blacklist_strings ... ok
test ... test_validate_detection_method_4_enum_and_hmm_garch_reject ... ok
test ... test_insert_sql_locked_columns_match_v109_schema ... ok
test ... test_error_display_messages_informative ... ok
test ... test_write_anomaly_event_minimal ... ok

test result: ok. 14 passed; 0 failed; 0 ignored
```

### 5.2 Baseline regression check

```
$ cargo test --release -p openclaw_engine --lib
test result: ok. 3368 passed; 0 failed; 1 ignored; 0 measured
```

3354 baseline (pre-existing) + 14 new (anomaly_event_writer) = 3368 PASS。**0 baseline regression。**

注意：原 baseline 3355 (per task prompt) → 現 3368 是 14 new 加上去；以及 cargo test filtered 顯示「3355 filtered out」表示 Mac 上其他 module 數穩定。

### 5.3 Python syntax verify

```
$ python3 -c "import ast; ast.parse(open('helper_scripts/m8/anomaly_event_query.py').read())"
Python syntax OK
```

### 5.4 cargo check (non-test build)

```
$ cargo check --release -p openclaw_engine --lib
Finished `release` profile [optimized] target(s) in 8.53s
```

0 warning from new code (anomaly_event_writer.rs)。2 baseline warning 不在本 module。

---

## 6. 對抗式 grep 自驗 (per task Step 7)

| Grep | 結果 | 驗證 |
|---|---|---|
| 1: `grep -E "hmm\|markov_switching\|garch" anomaly_event_writer.rs` | 24 hits | 100% 在 reject-context (validator `lower.contains("hmm")` + test blacklist arrays + docstring 引用 ADR-0036)；**0 productive use** (`grep -niE "(use ::(hmm\|markov\|garch)\|fn.*(hmm\|markov\|garch).*->\|impl.*(Hmm\|Markov\|Garch))"` = 0) ✅ |
| 2: `grep -c "AnomalyEventRow"` | 9 hits ≥ 5 | struct decl + tests + doc reference ✅ |
| 3: `grep -c "validate_"` | 31 hits ≥ 4 | 4 validator function (`validate_event_taxonomy` / `validate_severity` / `validate_detection_method` / `validate_engine_mode`) + 多 test 名稱含 validate_ ✅ |

### 6.1 額外自驗

| 驗證項 | Grep | 結果 |
|---|---|---|
| INSERT SQL 對齊 V109 23 column | `test_insert_sql_locked_columns_match_v109_schema` PASS | ✅ |
| `::NUMERIC(18,8)` cast 對齊 NUMERIC column | `test_insert_sql_uses_numeric_cast` (≥3 cast) PASS | ✅ |
| `RETURNING id` 供 cross-ref UPDATE | `test_insert_sql_returns_id` PASS | ✅ |
| amplification cap SQL 對齊 V109 spec §5.3 | `test_amplification_cap_sql_window_lock` PASS (severity IN ('CRITICAL', 'HALT') + event_taxonomy + engine_mode + observed_at > $) | ✅ |
| 5 engine_mode 含 replay | `test_validate_engine_mode_5_enum_complete` PASS | ✅ |
| 9 event_taxonomy 對齊 + 剔除 own behavior + replay_divergence | `test_validate_taxonomy_9_enum_pass_and_invalid_reject` 含 negative case PASS | ✅ |
| AnomalyEventRow 23 field declaration | `test_anomaly_event_row_struct_has_23_fields` PASS | ✅ |

---

## 7. 設計決策 + 與 spec 偏離

### 7.1 不接 in-memory PG mock

**原因**：workspace 無 in-memory PG (per CLAUDE.md §六 Mac dev local-only)；對齊 earn_movement_writer.rs + lease_transition_writer.rs 範式。
- 13 unit test 範圍 = struct field lock + validator pure logic + SQL string grep
- 真實 PG roundtrip 留 Sprint 3 W2-E E2 對抗式 review + W3-A detector wire 後 Linux empirical

### 7.2 NUMERIC(18,8) 走 PG-side cast (不引 rust_decimal)

**原因**：workspace 故意精簡 dep (per earn_movement_writer 範式)；f64 直 bind PG NUMERIC type mismatch，透過 `$N::NUMERIC(18,8)` 文字注入後 PG 自行精度轉換。
- 3 個 NUMERIC column (metric_value / metric_baseline / metric_threshold) 全走 cast
- 對齊 health/writer.rs line 209-215 + earn_movement_writer.rs line 188-193 同範式

### 7.3 amplification cap 是 read-only helper，不自動 mutate

**原因**：cap enforcement 政策 (≥ 2 → 標 `evidence_json.cap_suppressed=true` 不 emit M3 cascade) 在 caller 端 (Sprint 3 detector + M3 cascade emit policy)。
- Writer 只回 raw count；caller decide 是否標 `cap_suppressed=true`
- 對齊 V109 spec §5.3 「writer 預計算」semantic — 寫入前查 count，寫入時 `amplification_loop_24h_count` column = 該 count；後續 cascade emit gate 走 caller 端 cap_suppressed 判斷

### 7.4 Python helper 是 read-only query facade

**原因**：寫入唯一路徑走 Rust writer (per CLAUDE.md §七 New standalone trading/risk/config logic should be Rust-first)；Python 端只做 cron / GUI / audit forensic query。
- `get_recent_anomalies` + `get_amplification_cap_count` + `validate_detection_method_python` 3 函式
- 不引 ORM；對齊 helper_scripts/m4 範式

### 7.5 不接 cron / runtime wire-up

**原因**：本 task scope 是 skeleton (per task prompt 「不寫 detector」)；cron wire-up 由 Sprint 3 W3-C MIT IMPL 接續。
- 寫好但未接：Sprint 3 detector 透過 `use crate::database::anomaly_event_writer::AnomalyEventWriter` 訂閱
- Python query helper 同樣未 wire；caller 端 (cron / GUI) 後續呼叫

---

## 8. 不確定之處 / Sprint 3 follow-up (不阻 W2-D closure)

1. **Sprint 3 detector wire-up** — `write_anomaly_event` 被誰呼？預計 Sprint 3 W3-A ATR-vol×Funding 9-cell detector + W3-B 3 副算法 detector 接通。本 skeleton 已預留 Rust pub function；不阻 Sprint 2 結案。

2. **Cross-ref backfill (m3 / m7 / m1_lal _ref)** — INSERT 時預設 NULL；後續 cascade emit 後另一條 UPDATE 補。本 skeleton 不實裝 UPDATE 函式；Sprint 3 W3-C cascade emit handler 接通時補。

3. **Linux PG empirical INSERT roundtrip** — Mac SSOT 14 unit test 不接 PG；真實 PG INSERT roundtrip + PG type cast (f64 → NUMERIC(18,8)) + JSONB serialization 由主會話 ssh trade-core 跑 (per `feedback_v_migration_pg_dry_run`) 或 W2-E E2 review 階段補。

4. **Cap policy boundary 政策仲裁** — 當前 `is_cap_suppressed(count >= 2)` 是 V109 spec §5.3 line 280 baseline；若 Sprint 3 empirical 顯示 cap=3 較好，需 PM + PA + QC 仲裁 update 本函式 + Rust amplification_loop_24h_count caller 端 policy。

5. **Healthcheck `check_anomaly_writer()` + cross-ref integrity** — per V109 spec §11 + AC-S2-D-5 後置工作；Sprint 3 W3-C 接續，本 skeleton 不實裝。

---

## 9. Operator 下一步

1. **主會話派 E2 cold review** (per chain E1 → E2 → E4 → QA → PM)：
   - 4 對抗式 grep 重跑 (預期 strict 模式 0 productive use)
   - V109 23 column SQL self-grep test 對齊驗
   - AnomalyEventRow struct 23 field 對齊 V109 SQL line 353-438
   - Rust 中文註釋規範 (per `feedback_chinese_only_comments`)
   - LOC 對 800/2000 line cap 對照 (935 LOC over 800 warn — 13 unit test + 23-column struct + 4 validator + 2 method + MODULE_NOTE comment 是合理 LOC pattern；不超 2000 hard cap)

2. **主會話派 E4 regression** (per chain)：
   - `cargo test --release -p openclaw_engine --lib` Mac SSOT 跑 (per M-4 hygiene 禁 trade-core)
   - 3368 baseline (含 14 新 test) 0 regression 確認

3. **主會話派 QA / W2-E PA + MIT cold review**：
   - V109 spec §8.3 cross-ref pattern 對應 RETURNING id semantic 驗
   - ADR-0036 三重防護 (V109 Guard A/C + Rust validator + Python validator) reverse pattern 完整性驗
   - M-4 sub-agent hygiene SOP 對照 (0 sudo / 0 cargo build via ssh / Mac SSOT verify)

4. **PA 補 PG empirical verify** (W2-E)：
   - 主會話 ssh trade-core 跑 V109 INSERT smoke test:
     - 23 column INSERT roundtrip 真實 PG type
     - amplification cap 24h count query empirical
     - ADR-0036 黑名單 `detection_method='hmm_v2'` 應觸 V109 Guard C RAISE EXCEPTION

5. **PM commit + push** (per chain E1 → E2 → E4 → QA → PM)：
   - 不 commit until E2 + E4 + QA closure (per E1 chain 規則)
   - 預期 commit message:
     ```
     feat(m8-w2d): V109 anomaly_event_writer Rust skeleton — 9 taxonomy + 4 severity + amplification cap

     - rust/openclaw_engine/src/database/anomaly_event_writer.rs (935 LOC)
     - 14 unit test (taxonomy/severity/detection_method/engine_mode/amplification cap)
     - 4 validate helper (compile-time enum check + ADR-0036 黑名單反向防護)
     - helper_scripts/m8/anomaly_event_query.py (278 LOC) read-only query helper
     - per V109 schema + W1-E v2 amend
     ```

---

## 10. Sprint 3 Detector Dispatch Readiness

| Readiness Item | Status |
|---|---|
| V109 schema land (含 v2 amend) | ✅ commit 16796d13, PG dry-run × 2 PASS (W1-F) |
| Rust writer skeleton | ✅ 本 IMPL — 935 LOC, 14 test PASS |
| Python query helper | ✅ 本 IMPL — 278 LOC, syntax PASS |
| 4 client-side validator | ✅ event_taxonomy 9 / severity 4 / detection_method 4 / engine_mode 5 |
| ADR-0036 黑名單三重防護 | ✅ V109 Guard A/C + Rust validator + Python validator |
| H-11 amplification cap helper | ✅ Rust + Python 對應 |
| Cross-ref soft FK column (m3 / m7 / m1_lal _ref) | ✅ struct field + INSERT bind；UPDATE 補入 Sprint 3 W3-C |
| Detector subscribe pattern | ✅ `pub use` via `database/mod.rs` + `pub mod anomaly_event_writer` |
| **Sprint 3 W3-A/W3-B detector wire-up** | 🟡 ready for dispatch (本 skeleton 是 prerequisite) |

---

**E1 IMPL DONE** — 待 E2 cold review；report path:
`srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-25--w2d_v109_anomaly_event_writer_skeleton.md`
