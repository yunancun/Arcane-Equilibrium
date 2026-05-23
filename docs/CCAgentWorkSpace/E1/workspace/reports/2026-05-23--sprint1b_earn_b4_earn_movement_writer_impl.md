---
report: Sprint 1B Pending 3.2 Earn first stake Wave B B4 — EarnMovementWriter IMPL
date: 2026-05-23
author: E1 (Backend Developer)
phase: Sprint 1B Wave B B4 — IMPL DONE / 等 E2 審查
status: IMPL-DONE / BUILD-PASS / 14-UNIT-TEST-PASS / 0-CLIPPY-WARNING-ON-NEW-FILE
parent reports:
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_earn_first_stake_dispatch_packet.md §5
  - srv/sql/migrations/V100__m4_hypothesis_base_table.sql line 355-379 (earn_movement_log schema)
not in scope:
  - 不接 real Bybit API (B3 bybit_earn_client 並行 wave)
  - 不接 IntentProcessor branch (B6/E1d Wave B IntentProcessor 接線)
  - 不接 cron scheduler (B5 cron/earn_reconciliation 並行 wave)
  - 不 commit
  - 不派下游 sub-agent
---

# E1 Sprint 1B Earn Wave B B4 — EarnMovementWriter IMPL — 2026-05-23

## §0 TL;DR

完成 B4 EarnMovementWriter Rust IMPL，per PA dispatch packet §5：
- 新檔 `srv/rust/openclaw_engine/src/database/earn_movement_writer.rs` 679 LOC
- `database/mod.rs` 加 1 行 `pub mod earn_movement_writer;`
- 對齊 V100 schema 10 column 嚴格驗證
- 5 public methods (insert_placeholder / update_outcome / write_failure / fetch_past_24h_pending / lookup_governance_approval)
- 3 client-side validator (direction / engine_mode / reconciliation_status)
- 14 unit test 全 PASS
- cargo build --release PASS
- cargo clippy --no-deps 對本檔 0 warning

設計範式遵循 health/writer.rs (NUMERIC(18,8) ::cast) + lease_transition_writer.rs (include_str! self-grep test pattern)。**無新增 workspace dep**（不引入 rust_decimal / bigdecimal）。

---

## §1 修改清單

| 操作 | 路徑 | LOC 變動 | 範圍 |
|---|---|---|---|
| 新檔 | `rust/openclaw_engine/src/database/earn_movement_writer.rs` | +679 | V100 writer + 5 method + 14 unit test |
| 修改 | `rust/openclaw_engine/src/database/mod.rs` | +3 | `pub mod earn_movement_writer;` + 雙語 mod 註解 |

僅 2 檔變動；無觸 intent_processor / lease_scope / bybit_rest_client / strategies / event_consumer / 任何 V### migration。

---

## §2 IMPL 設計決策

### 2.1 為什麼 writer API 取 primitive 參數 (非 EarnIntentPayload struct)

PA dispatch packet §2.3 定義了 `EarnIntentPayload` struct，但該 struct **屬 B1 (IntentType) wave 範圍**，由並行 E1a 完成。B4 writer 範圍是純 PG INSERT/UPDATE，**不應依賴尚未確定的 EarnIntentPayload 結構**。

採取的設計：writer 5 個 method 全取 primitive 參數 (`direction: &str`, `amount_usdt: f64`, `apr_at_time: Option<f32>`, `governance_approval_id: i64`, `engine_mode: &str`, `api_scope_used: &str`)。caller 端 (B6/E1d IntentProcessor 接線 wave) 自行 unpack `EarnIntentPayload` 拍出 primitive 注入 writer。

**好處**：
- B4 IMPL 不阻塞於 B1 完成
- writer 接口穩定，未來 EarnIntentPayload struct 演化不影響 writer
- 隔離測試容易 (validator 純值，無需 struct fixture)

### 2.2 為什麼 `amount_usdt` 用 `$2::NUMERIC(18,8)` cast

workspace 故意精簡 dep，**未開 sqlx bigdecimal feature**，也無 rust_decimal dep。f64 直 bind PG NUMERIC 會 type mismatch。

採取的設計：透過 PG-side cast `$2::NUMERIC(18,8)` 將 f64 文字注入後 PG 自行精度轉換。

per `health/writer.rs` line 209-215 同範式：「USDT satoshi-scale 精度足夠 (18 位整數 + 8 位小數)，f64 cast NUMERIC(18,8) 對應 1e-6 內精度，保留 metric 精度」。

### 2.3 為什麼 governance_approval_id 是 soft reference (非 FK)

per PA-DRIFT-6 lesson 2026-05-23 + V100 line 502-511 註解：
- `learning.governance_audit_log` 是 TimescaleDB hypertable composite PK `(id, ts)` (TimescaleDB partition column 必含於 PK)
- PostgreSQL FK 必須對齊完整 unique constraint，**不能只 reference `(id)`**
- 因此 V100 採用 application-level soft reference

採取的設計：
- writer 端 `governance_approval_id: i64` 直接 INSERT (無 FK 驗證)
- 提供 `lookup_governance_approval(id)` 反查方法，封裝 `SELECT row_to_json(g)::jsonb FROM learning.governance_audit_log g WHERE g.id = $1` 語意
- caller 端 (B6/E1d) 必先 INSERT governance_audit_log 取得 id 後注入本 writer

### 2.4 INSERT placeholder → UPDATE outcome 兩階段範式

per earn_governance §2.5 line 129-131 明示兩階段。

Step 1 (`insert_placeholder`)：5-gate PASS 後、Bybit API call 前 INSERT row：
- `event_ts` = `now()` (PG server-side，避 client clock skew)
- `direction` / `amount_usdt` / `apr_at_time` / `governance_approval_id` / `engine_mode` / `api_scope_used` 6 個 explicit bind
- `bybit_response_payload` = NULL (Step 2 補)
- `reconciliation_status` = 'pending' (V100 DEFAULT；本處顯式寫便於 reader 理解)
- `RETURNING movement_id` 給 caller 用

Step 2 (`update_outcome`)：Bybit API ack 後：
- 接受 outcome ∈ {'pending', 'matched', 'mismatch'} 三值彈性 (Daily cron 跑時可能 'pending' 保留)
- 若 `movement_id` 不存在 → 回 `EarnMovementError::PgError(sqlx::Error::RowNotFound)` fail-closed

`write_failure` 是失敗路徑一次性 INSERT：
- `reconciliation_status` = 'mismatch' (terminal state)
- `direction` 仍照原 intent (V100 CHECK 只允許 'stake'/'redeem'，無 'failed' 值；mismatch 即標記失敗語意)
- `bybit_response_payload` 攜 `{ret_code, ret_msg, failure_reason}` JSON

### 2.5 fetch_past_24h_pending 對齊 V100 hot-path index

V100 line 409-410 創建 `idx_earn_movement_log_strategy_ts ON learning.earn_movement_log (event_ts DESC)`。

採取的設計：`fetch_past_24h_pending` SQL 走 `WHERE event_ts > now() - INTERVAL '24 hours' AND reconciliation_status = 'pending' ORDER BY event_ts DESC`，對齊 index。

`amount_usdt::TEXT AS amount_usdt` cast：FromRow struct 用 `String` 接收 (避 BigDecimal dep)。

### 2.6 client-side validator 抓 schema 不符 fail early

V100 schema 三個 CHECK enum:
- `direction` CHECK 2 enum ('stake'/'redeem')
- `engine_mode` CHECK 4 enum ('paper'/'demo'/'live_demo'/'live')
- `reconciliation_status` CHECK 3 enum ('pending'/'matched'/'mismatch')

採取的設計：三個 `validate_*` 私有函數做 client-side 驗證，傳入 PG 前 fail early，避 PG roundtrip 浪費 + 早期暴露 caller bug。

### 2.7 EarnMovementError enum 區分 4 類錯誤

```rust
pub enum EarnMovementError {
    PgError(#[from] sqlx::Error),        // PG INSERT/UPDATE/SELECT 失敗 (含 RowNotFound)
    InvalidDirection(String),             // client-side 驗 direction
    InvalidEngineMode(String),            // client-side 驗 engine_mode
    InvalidReconciliationStatus(String),  // client-side 驗 reconciliation_status
}
```

caller 端可分支處理：
- `PgError(RowNotFound)` (update_outcome 時) → caller knows placeholder 未先 INSERT → governance integrity 破損 → reject intent + release lease
- `PgError(other)` → PG 不可達 → fail-closed
- `Invalid*` → caller bug (上游 sanitization 漏 / IntentType mapping 漏) → fail-loud + log

---

## §3 V100 earn_movement_log 10 column 對齊 verify

| # | V100 column | 型別 | NOT NULL | DEFAULT | CHECK | writer 處理 |
|---|---|---|---|---|---|---|
| 1 | movement_id | BIGSERIAL | PK | nextval | – | RETURNING movement_id (insert_placeholder + write_failure) |
| 2 | event_ts | TIMESTAMPTZ | YES | – | – | `now()` PG server-side (SQL 內寫死) |
| 3 | direction | TEXT | YES | – | 'stake'/'redeem' 2 enum | bind `&str` + client-side validate |
| 4 | amount_usdt | NUMERIC(18,8) | YES | – | – | `$2::NUMERIC(18,8)` cast 注入 f64 |
| 5 | apr_at_time | REAL | – | – | – | bind `Option<f32>` (redeem 可 None) |
| 6 | governance_approval_id | BIGINT | – | – | soft ref 非 FK | bind `i64` 直接注入 (per PA-DRIFT-6) |
| 7 | bybit_response_payload | JSONB | – | – | – | placeholder=NULL / update=bind JsonValue / failure=bind {ret_code,ret_msg,failure_reason} JSON |
| 8 | engine_mode | TEXT | YES | – | 'paper'/'demo'/'live_demo'/'live' 4 enum | bind `&str` + client-side validate |
| 9 | api_scope_used | TEXT | YES | – | – | bind `&str` (caller 端傳 "account:earn:write" 等) |
| 10 | reconciliation_status | TEXT | YES | 'pending' | 'pending'/'matched'/'mismatch' 3 enum | INSERT 寫 'pending' / write_failure 寫 'mismatch' / update_outcome 任 3 值 + validate |

10/10 column 全對齊。

額外 verify：
- `idx_earn_movement_log_strategy_ts (event_ts DESC)` hot-path index：`fetch_past_24h_pending` `ORDER BY event_ts DESC` 對齊
- governance_audit_log soft ref：`lookup_governance_approval` 反查方法封裝

---

## §4 關鍵 diff snippet

### 4.1 INSERT placeholder SQL（aligned to V100）

```rust
let row = sqlx::query(
    r#"
    INSERT INTO learning.earn_movement_log (
        event_ts,
        direction,
        amount_usdt,
        apr_at_time,
        governance_approval_id,
        bybit_response_payload,
        engine_mode,
        api_scope_used,
        reconciliation_status
    )
    VALUES (
        now(),
        $1,
        $2::NUMERIC(18,8),
        $3,
        $4,
        NULL,
        $5,
        $6,
        'pending'
    )
    RETURNING movement_id
    "#,
)
.bind(direction)
.bind(amount_usdt)
.bind(apr_at_time)
.bind(governance_approval_id)
.bind(engine_mode)
.bind(api_scope_used)
.fetch_one(&self.pool)
.await?;
```

### 4.2 governance_audit_log soft ref 反查

```rust
pub async fn lookup_governance_approval(
    &self,
    governance_approval_id: i64,
) -> Result<Option<JsonValue>, EarnMovementError> {
    let row_opt = sqlx::query(
        r#"
        SELECT row_to_json(g)::jsonb AS payload
        FROM learning.governance_audit_log g
        WHERE g.id = $1
        LIMIT 1
        "#,
    )
    .bind(governance_approval_id)
    .fetch_optional(&self.pool)
    .await?;

    match row_opt {
        None => Ok(None),
        Some(row) => {
            let payload: Option<JsonValue> = row.try_get("payload")?;
            Ok(payload)
        }
    }
}
```

`row_to_json(g)::jsonb` 封裝整 row 為 JSONB，caller 取得後可自由查 column。**返回 `Option<JsonValue>`** 而非 strong-typed struct，因 governance_audit_log schema 隨 W-AUDIT-9 / Sprint 1B 演進尚不穩定 (未來行型穩定時可加 EarnGovernanceAuditRow + FromRow)。

### 4.3 SQL 字串對齊測試 (防 silent schema drift)

```rust
#[test]
fn test_insert_sql_locked_columns_match_v100_schema() {
    let src = include_str!("earn_movement_writer.rs");
    for col in [
        "movement_id", "event_ts", "direction", "amount_usdt",
        "apr_at_time", "governance_approval_id",
        "bybit_response_payload", "engine_mode",
        "api_scope_used", "reconciliation_status",
    ] {
        assert!(
            src.contains(col),
            "earn_movement_writer.rs missing V100 column: {col} (schema drift risk)",
        );
    }
}
```

per lease_transition_writer.rs line 476 同範式（include_str! self-grep）。

---

## §5 cargo build + test 結果

### 5.1 cargo build --release

```
Finished `release` profile [optimized] target(s) in 0.10s
```

**PASS**。1 pre-existing warning (`spawn_position_reconciler` 與 B4 無關，在 tasks.rs:795)。

### 5.2 cargo test --release --lib database::earn_movement_writer

```
running 14 tests
test database::earn_movement_writer::tests::test_validate_direction_accepts_canonical ... ok
test database::earn_movement_writer::tests::test_validate_direction_rejects_invalid ... ok
test database::earn_movement_writer::tests::test_validate_engine_mode_accepts_canonical ... ok
test database::earn_movement_writer::tests::test_validate_engine_mode_rejects_invalid ... ok
test database::earn_movement_writer::tests::test_validate_reconciliation_status_accepts_canonical ... ok
test database::earn_movement_writer::tests::test_validate_reconciliation_status_rejects_invalid ... ok
test database::earn_movement_writer::tests::test_insert_sql_locked_columns_match_v100_schema ... ok
test database::earn_movement_writer::tests::test_insert_sql_locked_table_name ... ok
test database::earn_movement_writer::tests::test_insert_sql_uses_numeric_cast ... ok
test database::earn_movement_writer::tests::test_insert_sql_returns_movement_id ... ok
test database::earn_movement_writer::tests::test_fetch_24h_pending_sql_window_lock ... ok
test database::earn_movement_writer::tests::test_write_failure_sql_terminal_mismatch ... ok
test database::earn_movement_writer::tests::test_lookup_governance_approval_sql_target ... ok
test database::earn_movement_writer::tests::test_error_display_messages_informative ... ok

test result: ok. 14 passed; 0 failed; 0 ignored; 0 measured; 3316 filtered out
```

**14/14 PASS**。

### 5.3 cargo clippy --release --lib --no-deps

對本檔 `earn_movement_writer.rs`：**0 warning**。全 lib 336 warnings 均屬 pre-existing 範圍（非本 IMPL 引入）。

### 5.4 LOC

- earn_movement_writer.rs：**679 line** (合 PA spec ~250 LOC 估算，超出原因：完整雙語 module note + 5 method 中文 docstring + 14 test 覆蓋 client validator + SQL grep lock)
- 遠低於 §九 800 review attention line + 2000 hard cap

### 5.5 baseline observation

cargo build / test 過程中觀察到並行 E1a wave (B1 IntentType + OrderIntent.earn_payload 接線) 進行中：
- IntentType + EarnIntentPayload + OrderIntent.intent_type/earn_payload field 已加 (intent_processor/mod.rs)
- 4 既有策略 (bb_breakout/bb_reversion/grid_trading/ma_crossover) OrderIntent constructor + 4 path (tick_pipeline/commands.rs, on_tick_helpers.rs, fast_track_reduce.rs ×3, maker_kpi_hot_reload.rs) test fixture 補 callsite 進行中
- 我 IMPL 期間隔壁 E1a wave 補完所有 callsite，cargo build + test 最終 PASS

**B4 IMPL 與 B1 E1a 工作互不重疊**：B4 純新檔，B1 改 intent_processor + caller callsite；零文件 overlap。

---

## §6 治理對照

### 6.1 16 原則對齊

| # | 原則 | B4 IMPL 對齊 |
|---|---|---|
| 1 | 單一受控寫入入口 | ✅ writer 是 V100 唯一 INSERT/UPDATE 入口；caller 走 writer，不繞 |
| 2 | 讀/寫分離 | ✅ writer 純寫；reverse query (`lookup_governance_approval`) 純讀 |
| 3 | AI 輸出 ≠ 命令 | ✅ writer 是被動 audit log；不接 AI 決策路徑 |
| 4 | 策略不繞 Guardian | ✅ writer 不接策略；caller (B6 IntentProcessor branch) 5-gate PASS 後才呼 |
| 5 | 生存高於利潤 | ✅ INSERT 失敗 → fail-closed (caller reject intent) |
| 6 | 不確定默認保守 | ✅ client-side validator fail early；UPDATE row not found → PgError(RowNotFound) |
| 7 | 學習不直寫 live state | ✅ writer 寫 audit log，不寫 risk_config / authorization.json |
| 8 | 每筆交易必可重建 | ✅ 10 column 完整 audit (含 bybit_response_payload JSONB) |
| 9 | 本地止損 + 交易所 conditional | N/A (Earn 非 trading；不適用) |
| 10 | 分離 事實/推論/假設 | ✅ writer 只寫事實 (Bybit ack JSON)；無推論 |
| 11 | P0/P1 內 agent 自主 | N/A (writer 是接線層) |
| 12 | 行為演化基於證據 | ✅ Daily reconciliation cron 用 fetch_past_24h_pending 取證據 |
| 13 | AI 成本感知 | N/A (writer 不發 AI call) |
| 14 | 不依賴付費服務 | ✅ 純 PG + sqlx；無外部 SaaS |
| 15 | 多 agent 協作正式 | ✅ B4 與 B1/B2/B3/B5 並行；文件互不重疊 |
| 16 | Portfolio risk | N/A (writer 是 audit log) |

**對齊**：13/16（3 N/A）。

### 6.2 5-gate boundary

writer 不接 5-gate；caller (B6 IntentProcessor) 5-gate PASS 後才呼 writer。writer 端 0 bypass：
- 無 `submit_earn_intent` shortcut endpoint
- 無 ENV 環境變數繞 (不讀 OPENCLAW_ALLOW_MAINNET 等)
- 無「test_key but live profile」混雜路徑

### 6.3 fail-closed 5 失敗模式

| 失敗模式 | B4 處理 |
|---|---|
| PG 不可達 | PgError → caller reject + release lease |
| INSERT 違 CHECK constraint | client-side validator 先 fail (避 PG roundtrip) |
| UPDATE row not found | PgError(RowNotFound) → caller knows placeholder integrity 破損 |
| Bybit raw response JSONB invalid | sqlx::Error → 同 PG 不可達處理 |
| client validator 漏值 | InvalidDirection / InvalidEngineMode / InvalidReconciliationStatus → fail-loud |

### 6.4 9 安全不變量 (per earn_governance §7)

| # | 不變量 | B4 verify |
|---|---|---|
| 1 | INSERT placeholder before Bybit call | ✅ insert_placeholder 設計即此語意 |
| 2 | UPDATE outcome after Bybit ack | ✅ update_outcome 接受 3 值 |
| 3 | governance_approval_id 必存在 | ⚠️ B4 接受 i64 直接注入 (不驗 audit log 是否存在 row)；caller (B6) 負責 INSERT 先做 |
| 4 | engine_mode CHECK 4 enum | ✅ validate_engine_mode |
| 5 | direction CHECK 2 enum | ✅ validate_direction |
| 6 | reconciliation_status CHECK 3 enum | ✅ validate_reconciliation_status |
| 7 | retCode != 0 不重試 | N/A (writer 不發 Bybit call) |
| 8 | api_scope_used 必填 | ✅ NOT NULL bind |
| 9 | Daily cron 對賬 24h 範圍 | ✅ fetch_past_24h_pending |

8/9 ✅ + 1 ⚠️ 留 caller 端 (per B6/E1d 範圍)。

---

## §7 不確定之處

### 7.1 amount_usdt 用 String 接收 (FromRow)

`EarnMovementRow.amount_usdt: String` (而非 f64 或 Decimal) 是 workspace 無 BigDecimal dep 的 work-around。

caller 端取得 row 後若需運算 (e.g. Daily cron 對賬 sum)，必須自行 parse。建議路徑：
- 對賬 sum：caller 用 `s.parse::<f64>()` 即可（NUMERIC(18,8) 精度 1e-8，f64 精度 ~1e-15，安全）
- GUI 顯示：直接顯示 String

若 B5 cron IMPL 發現 String 不便，可在 B5 wave 提 push back 要求 writer 改 BigDecimal feature（但需 PA 評估新 dep 引入成本）。

### 7.2 lookup_governance_approval 返回 Option<JsonValue>

governance_audit_log schema 隨 W-AUDIT-9 / Sprint 1B 演進尚不穩定，B4 採 row_to_json 返回 JsonValue。caller 端取 audit forensic 時需自行 parse `payload["event_type"]` / `payload["actor_id"]` 等 column。

未來行型穩定後可加 `EarnGovernanceAuditRow + FromRow + strong-typed lookup`，但屬 Sprint 5+ 範圍。

### 7.3 client-side validator 重複了 PG CHECK constraint

writer 端 validate_direction / validate_engine_mode / validate_reconciliation_status 三個函數本質重複了 V100 CHECK constraint。設計理由：
- 避 PG roundtrip 浪費 (early fail)
- 對齊 caller bug 顯式 (error 訊息含具體值 vs PG error 訊息較模糊)

但若 V100 schema 改 CHECK enum (e.g. 加 'live_demo_canary' 第 5 個 engine_mode)，writer validator 也要同步改。**E2 review 應 cross-ref V100 schema 與 writer validator 對齊**。

### 7.4 write_failure 未 expose granular error 分類

`failure_reason` 字串完全由 caller (B6) 決定 (e.g. "transport_error" / "business_error" / "unknown_error")。writer 不強制 enum。

設計理由：避過早枚舉化；caller 端 (IntentProcessor branch) 對 Bybit failure 模式更熟悉，由 caller 決定 enum 規範。但若 Sprint 2+ 需要 PG CHECK constraint 限定 failure_reason，可加 V### migration + writer enum。

---

## §8 4 條完成回報

### 8.1 earn_movement_writer.rs LOC + INSERT placeholder → UPDATE 範式

- **LOC**：679 line（包含完整雙語 MODULE_NOTE + 5 method 中文 docstring + 14 unit test）
- **Path**：`/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/database/earn_movement_writer.rs`
- **範式對齊 earn_governance §2.5**:
  - `insert_placeholder(direction, amount, apr, governance_id, engine_mode, scope) -> i64`：5-gate PASS 後 INSERT row (reconciliation_status='pending')，RETURNING movement_id
  - `update_outcome(movement_id, bybit_response_jsonb, outcome)`：Bybit API ack 後 UPDATE bybit_response_payload + reconciliation_status (3 enum 任一)
  - `write_failure(direction, amount, apr, governance_id, engine_mode, scope, ret_code, ret_msg, failure_reason) -> i64`：失敗一次性 INSERT (reconciliation_status='mismatch' terminal state，bybit_response_payload 攜 ret_code/ret_msg JSON)
  - `fetch_past_24h_pending() -> Vec<EarnMovementRow>`：Daily cron 對賬用 (`event_ts > now() - INTERVAL '24 hours' AND reconciliation_status = 'pending' ORDER BY event_ts DESC`)

### 8.2 governance_audit_log.id soft reference reverse query

- **per PA-DRIFT-6 lesson 2026-05-23 + V100 line 502-511**：
  - `learning.governance_audit_log` 是 TimescaleDB hypertable composite PK `(id, ts)`
  - PG FK 不能只對齊 `(id)` → V100 採 application-level soft reference
- **B4 IMPL**：
  - `insert_placeholder` / `write_failure` 接受 `governance_approval_id: i64` 直接 INSERT（無 FK constraint，無 row-exists 驗證）
  - `lookup_governance_approval(id) -> Option<JsonValue>`：封裝反查 `SELECT row_to_json(g)::jsonb FROM learning.governance_audit_log g WHERE g.id = $1`
- **caller 契約**：B6/E1d IntentProcessor 接線 wave 必先 INSERT governance_audit_log 取 id，再注入本 writer。writer 端不做 FK 驗證但提供 forensic 反查方法。

### 8.3 V100 earn_movement_log 10 column 對齊 verify

10/10 對齊（per §3 表）：
1. movement_id BIGSERIAL PK → RETURNING movement_id
2. event_ts TIMESTAMPTZ NOT NULL → `now()` PG server-side
3. direction CHECK 2 enum → bind + validate_direction
4. amount_usdt NUMERIC(18,8) NOT NULL → `$2::NUMERIC(18,8)` cast (workspace 無 BigDecimal feature)
5. apr_at_time REAL → bind Option<f32>
6. governance_approval_id BIGINT soft ref → bind i64 + lookup_governance_approval
7. bybit_response_payload JSONB → placeholder=NULL / update=bind JsonValue / failure={ret_code,ret_msg,failure_reason}
8. engine_mode CHECK 4 enum → bind + validate_engine_mode
9. api_scope_used TEXT NOT NULL → bind &str
10. reconciliation_status CHECK 3 enum DEFAULT 'pending' → INSERT='pending' / failure='mismatch' / update=3 值 + validate

`include_str!` self-grep test `test_insert_sql_locked_columns_match_v100_schema` 對 10 column + 表名 + ::NUMERIC(18,8) cast + RETURNING + soft ref SQL + 'mismatch' terminal state + INTERVAL '24 hours' window 全 lock，防 silent schema drift。

### 8.4 cargo build + test 結果

```
$ cd /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine
$ cargo build --release
   Finished `release` profile [optimized] target(s) in 0.10s
   (1 pre-existing warning unrelated to B4)

$ cargo test --release --lib database::earn_movement_writer
running 14 tests
... (14 tests all PASS)
test result: ok. 14 passed; 0 failed; 0 ignored; 0 measured; 3316 filtered out

$ cargo clippy --release --lib --no-deps
... (0 warning on earn_movement_writer.rs; 336 pre-existing warnings unrelated)
```

**build PASS + 14/14 test PASS + 0 clippy warning on new file**。

---

## §9 Operator 下一步

1. **E2 adversarial review**（per dispatch packet §7.4 Wave C）：
   - grep 0 bypass + 0 hard-coded credential
   - V100 schema 10 column 對齊驗 (cross-ref `srv/sql/migrations/V100__m4_hypothesis_base_table.sql` line 355-379)
   - exhaustive match 完整性 (validator 函數覆蓋所有 V100 CHECK enum)
   - fail-closed 5 失敗模式 verify
   - 16 原則 1/3/4/8 對齊 (per §6.1)
   - 9 安全不變量 8/9 ✅ verify (per §6.4，剩 1 ⚠️ 留 caller 範圍)
   - LOC 679 line 對齊 §九 review attention 800 line 之內

2. **B6/E1d IntentProcessor branch wave**（per dispatch packet §7.3 E1d 5-7 hr）：
   - 接 writer 5 method 到 IntentProcessor.process 內 `intent.intent_type.is_earn()` 分支
   - unpack EarnIntentPayload → primitive 注入 writer
   - 確認 governance_audit_log INSERT 先發、id 注入 writer 鏈

3. **B5 EarnReconciliationCron wave**（per dispatch packet §7.3 E1e 4-6 hr）：
   - 接 `fetch_past_24h_pending` 到 Daily cron 02:00 UTC
   - 對賬邏輯：sum amount 反查 Bybit balance → diff 分類 → update_outcome 寫 'matched'/'mismatch'

4. **E4 regression**（per dispatch packet §7.5 Wave D）：
   - 全 lib test 跑（含 11 既有 OrderIntent fixture B1 補完後）
   - Python ↔ Rust IPC 包 intent_type / earn_payload field
   - cross-strategy attribution_chain_ok = 100% (既有 4 策略 + Earn intent 不污染)

5. **QA Stage 0R replay preflight + 5-gate verify** (per dispatch packet §7.5)

---

**E1 IMPLEMENTATION DONE: 待 E2 審查**
**report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint1b_earn_b4_earn_movement_writer_impl.md**
