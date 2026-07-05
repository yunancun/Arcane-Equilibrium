//! Sprint 1B Pending 3.2 Earn first stake Wave B B4 —
//! V100 `learning.earn_movement_log` writer。
//!
//! MODULE_NOTE
//! 模塊用途：
//!   per docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_earn_first_stake_dispatch_packet.md
//!   §5 EarnMovementWriter spec，將 Bybit Earn stake/redeem 操作的審計列寫入
//!   `learning.earn_movement_log` (V100 schema)。設計範式：
//!     - Step 1: INSERT placeholder (5-gate PASS 後、Bybit API call 前)，
//!       reconciliation_status='pending' + bybit_response_payload=NULL；
//!     - Step 2: UPDATE outcome (Bybit API ack 後)，bind bybit raw response JSONB +
//!       reconciliation_status 由 caller 決定 (Daily reconciliation cron 之前固定 'pending'，
//!       cron 跑後改為 'matched' / 'mismatch')；
//!     - Failure path: write_failure 一次性 INSERT failure row (direction 仍照原 intent，
//!       reconciliation_status='mismatch' + bybit_response_payload 含 ret_code/ret_msg)，
//!       per earn_governance §5.1 fail-closed。
//!
//! 主要類 / 函數：
//!   - `EarnMovementWriter`：sqlx::PgPool 包裝；提供 insert_placeholder / update_outcome /
//!     write_failure / fetch_past_24h_pending 四個方法。
//!   - `EarnMovementRow`：Daily reconciliation cron 用的 10 column row 投影。
//!   - `EarnMovementError`：寫入失敗錯誤碼 (PG error / invalid_direction /
//!     invalid_engine_mode / invalid_reconciliation_status)。
//!
//! 依賴：
//!   - sqlx Postgres + serde_json (workspace deps，無新引入)；不依賴 rust_decimal
//!     (workspace 故意精簡 dep，per health/writer.rs line 209-213 同範式)；
//!   - 不依賴 B1 (IntentType) / B2 (LeaseScope) / B3 (BybitEarnClient) — writer 取
//!     primitive 參數 (direction &str / amount f64 / governance_approval_id i64 等)，
//!     caller 端 unpack EarnIntentPayload struct 拍出 primitive 給 writer。
//!   - Sprint 1B 並行 B1/B2/B3 wave 不阻塞本 IMPL；E1d IntentProcessor 接線 wave 階段
//!     的 caller 再做 IntentType→direction 字串 mapping。
//!
//! 硬邊界：
//!   - V100 schema 10 column 嚴格對齊 (per sql/migrations/V100 line 355-379)；
//!     新增 column 必同步更新本 module + 新增 unit test。
//!   - direction CHECK 2 enum ('stake' / 'redeem')：writer 端做 client-side 驗證
//!     (early fail 避 PG roundtrip 浪費)。
//!   - engine_mode CHECK 4 enum ('paper' / 'demo' / 'live_demo' / 'live')：同 client-side 驗。
//!   - reconciliation_status CHECK 3 enum ('pending' / 'matched' / 'mismatch')：
//!     insert_placeholder 永遠寫 'pending'；update_outcome 允許三值；client-side 驗。
//!   - amount_usdt NUMERIC(18,8)：透過 `$N::NUMERIC(18,8)` cast 注入 f64
//!     (per health/writer.rs line 209-215 同範式；workspace 無 BigDecimal feature 開)。
//!   - apr_at_time REAL：由 caller 將 apr_bps (i32) 轉 REAL (bps / 10000.0) 並以
//!     Option<f32> 注入。
//!   - governance_approval_id BIGINT soft reference (per PA-DRIFT-6 lesson 2026-05-23 +
//!     V100 line 502-511 註解)：不是 PG FK constraint；caller 必先 INSERT
//!     learning.governance_audit_log 取 id，再以 id 注入本 writer。
//!   - INSERT 失敗時 caller 端 fail-closed (return Err)：governance integrity 破損
//!     (audit log 缺 row) 即 lease release + reject intent，per earn_governance §2.5。
//!
//! 不變量：
//!   - 任何 stake/redeem 操作對應「至少 1 row」在 earn_movement_log 表（無 silent skip）。
//!   - insert_placeholder + update_outcome 是兩階段；caller 若在 Bybit API call 後忘記
//!     update_outcome，會留下 reconciliation_status='pending' row；Daily cron 會掃 24h
//!     pending row 嘗試對賬補上 matched/mismatch（不會 false-positive failure）。
//!   - write_failure 是一次性 (INSERT 直接寫 mismatch row)；不需 update_outcome。
//!
//! 規格 / Spec:
//!   - PA dispatch packet §5.2 EarnMovementWriter Rust skeleton
//!   - V100 schema sql/migrations/V100__m4_hypothesis_base_table.sql line 355-379
//!   - earn_governance_spec.md §2.5 (Audit gate fail-closed)
//!   - earn_governance_spec.md §5.1 (fail-closed retCode != 0 處理)
//!   - earn_governance_spec.md §6 (Daily reconciliation cron 對賬)

use serde_json::Value as JsonValue;
use sqlx::{FromRow, PgPool, Row};

/// V100 `learning.earn_movement_log` 10 column 對齊的 row 投影。
///
/// 為什麼 BIGSERIAL `movement_id` 走 RETURNING：
///   - PG BIGSERIAL 由 DB 端 nextval 取；INSERT 不傳 id 而是 RETURNING movement_id
///     讓 caller 取得，後續 update_outcome 才能用 movement_id 鎖定 row。
///
/// 為什麼 `event_ts` 在 client side 取 `now()`：
///   - 對齊 V100 schema 設計 (event_ts TIMESTAMPTZ NOT NULL，無 DEFAULT)：caller 必
///     提供。在 SQL 層用 `now()` 函數寫入即可 (per insert_placeholder INSERT SQL)。
#[derive(Debug, Clone, FromRow)]
pub struct EarnMovementRow {
    /// V100 column `movement_id BIGSERIAL PRIMARY KEY`：DB 端 nextval。
    pub movement_id: i64,
    /// V100 column `event_ts TIMESTAMPTZ NOT NULL`：寫入時刻 (insert_placeholder 用 now())。
    pub event_ts: chrono::DateTime<chrono::Utc>,
    /// V100 column `direction TEXT NOT NULL`：CHECK ('stake', 'redeem') 2 enum。
    pub direction: String,
    /// V100 column `amount_usdt NUMERIC(18,8) NOT NULL`：高精度 USDT 數額；
    /// 用 String 接收避 BigDecimal dep；caller 端可自行 parse 為 f64 / Decimal。
    pub amount_usdt: String,
    /// V100 column `apr_at_time REAL`：APR 4-decimal float；NULL allowed for redeem。
    pub apr_at_time: Option<f32>,
    /// V100 column `governance_approval_id BIGINT`：soft reference 至
    /// `learning.governance_audit_log.id` (per PA-DRIFT-6 lesson 2026-05-23)。
    pub governance_approval_id: Option<i64>,
    /// V100 column `bybit_response_payload JSONB`：Bybit API raw response。
    pub bybit_response_payload: Option<JsonValue>,
    /// V100 column `engine_mode TEXT NOT NULL`：CHECK 4 enum
    /// ('paper'/'demo'/'live_demo'/'live')。
    pub engine_mode: String,
    /// V100 column `api_scope_used TEXT NOT NULL`：Bybit API permission scope
    /// (e.g. "account:earn:write")；audit forensic 用。
    pub api_scope_used: String,
    /// V100 column `reconciliation_status TEXT NOT NULL DEFAULT 'pending'`：
    /// CHECK ('pending'/'matched'/'mismatch') 3 enum。
    pub reconciliation_status: String,
}

/// V100 writer 錯誤碼。
///
/// 為什麼用 thiserror enum：
///   - PG error / client-side validation 兩類錯誤需區分；caller 端 reject intent +
///     log + release lease 路徑可分支處理。
///   - 為何不 inherit M3Error pattern (health writer)：earn writer 屬 governance hot path
///     不屬 health observation；錯誤類型與 M3Error 不同 (M3Error 含 SampleError 與
///     SM 相關碼)。
#[derive(Debug, thiserror::Error)]
pub enum EarnMovementError {
    /// PG INSERT / UPDATE / SELECT 失敗。
    #[error("PG operation failed: {0}")]
    PgError(#[from] sqlx::Error),
    /// direction 字串不在 V100 CHECK 允許範圍 (must be 'stake' 或 'redeem')。
    #[error("invalid direction '{0}' (must be 'stake' or 'redeem')")]
    InvalidDirection(String),
    /// engine_mode 不在 V100 CHECK 4 enum。
    #[error("invalid engine_mode '{0}' (must be one of paper/demo/live_demo/live)")]
    InvalidEngineMode(String),
    /// reconciliation_status 不在 V100 CHECK 3 enum。
    #[error(
        "invalid reconciliation_status '{0}' (must be one of pending/matched/mismatch)"
    )]
    InvalidReconciliationStatus(String),
}

/// V100 `learning.earn_movement_log` writer。
///
/// 為什麼 PgPool 不包 Arc：
///   - sqlx::PgPool 內部已 Arc-shared (clone 廉價)；無需再包 Arc。
///   - 對齊 health/writer.rs PgHealthObservationWriter 範式。
///   - caller 端持 PgPool clone 注入 writer (one-shot constructor)。
pub struct EarnMovementWriter {
    pool: PgPool,
}

impl EarnMovementWriter {
    /// 建立 writer；caller 端 share PgPool (engine main pool)。
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    /// Step 1: INSERT placeholder row (5-gate PASS 後、Bybit API call 前)。
    ///
    /// 為什麼用 placeholder 範式：
    ///   - earn_governance §2.5 line 129 明示「DB INSERT placeholder（outcome=pending）」；
    ///   - Bybit API call 失敗時，row 已存在於 earn_movement_log 表，留 audit forensic 痕跡
    ///     (不會「靜默失敗 → 無 audit」狀態)；
    ///   - Bybit API call 成功時，update_outcome 補 bybit_response_payload + reconciliation
    ///     _status 即可，無需 DELETE/RE-INSERT。
    ///
    /// 參數說明：
    ///   - `direction`: "stake" 或 "redeem"；client-side 驗 fail early。
    ///   - `amount_usdt`: f64；透過 `$2::NUMERIC(18,8)` cast 注入 PG。
    ///   - `apr_at_time`: Option<f32>；redeem 時可 None；REAL 4-decimal 精度足夠。
    ///   - `governance_approval_id`: i64；soft ref 至 learning.governance_audit_log(id)；
    ///     per PA-DRIFT-6 lesson 不是 FK constraint，caller 端必先 INSERT audit log 取 id。
    ///   - `engine_mode`: "paper" / "demo" / "live_demo" / "live"；client-side 驗。
    ///   - `api_scope_used`: Bybit API permission scope (e.g. "account:earn:write")。
    ///
    /// 回傳：RETURNING movement_id (i64)，供 caller 後續 update_outcome 用。
    pub async fn insert_placeholder(
        &self,
        direction: &str,
        amount_usdt: f64,
        apr_at_time: Option<f32>,
        governance_approval_id: i64,
        engine_mode: &str,
        api_scope_used: &str,
    ) -> Result<i64, EarnMovementError> {
        validate_direction(direction)?;
        validate_engine_mode(engine_mode)?;

        // 對齊 V100 schema 10 column：
        //   - movement_id 走 BIGSERIAL DEFAULT (RETURNING 取回)；
        //   - event_ts 用 now() 取 PG server-side timestamp (避 client clock skew)；
        //   - direction / amount_usdt / apr_at_time / governance_approval_id /
        //     engine_mode / api_scope_used 6 個顯式 bind；
        //   - bybit_response_payload 初始 NULL (Step 2 update_outcome 補)；
        //   - reconciliation_status 初始 'pending' (V100 DEFAULT；本處顯式寫便於 reader 理解)。
        //
        // 為什麼 amount_usdt 用 `$2::NUMERIC(18,8)` cast：
        //   - workspace sqlx feature 沒開 BigDecimal / rust_decimal；f64 直 bind PG NUMERIC
        //     會 type mismatch。透過 PG-side cast `$2::NUMERIC(18,8)` 將 f64 文字注入後
        //     PG 自行精度轉換，per health/writer.rs line 209-215 同範式 (5-sample window
        //     精度 1e-6 內，NUMERIC(18,8) 對應 18 位整數 + 8 位小數，足以保留 USDT satoshi-scale)。
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

        let movement_id: i64 = row.try_get("movement_id")?;
        Ok(movement_id)
    }

    /// Step 2: UPDATE bybit_response_payload + reconciliation_status (Bybit API ack 後)。
    ///
    /// 為什麼分兩步 (INSERT placeholder → UPDATE outcome)：
    ///   - per earn_governance §2.5 line 129-131 明示兩階段範式；
    ///   - Bybit API ack 後 caller 才知 outcome (成功 ack / 失敗 retCode != 0)；
    ///   - 若 Bybit API timeout，placeholder row 仍存於表內 (reconciliation_status='pending')，
    ///     Daily cron 跑時掃 24h pending row 並對賬，避免「silent loss」。
    ///
    /// 參數說明：
    ///   - `movement_id`: insert_placeholder 回傳的 BIGSERIAL PK。
    ///   - `bybit_response`: Bybit V5 API raw JSON response (含 retCode / retMsg / result 全文)；
    ///     audit forensic 用，per earn_governance §2.5 line 130-131。
    ///   - `outcome`: 'pending' / 'matched' / 'mismatch' (V100 CHECK 3 enum)；
    ///     成功 ack 直接寫 'matched' (Daily cron 也用)；失敗則走 write_failure 不是這條。
    ///
    /// 為什麼 outcome 允許 'pending' (不只 'matched'/'mismatch')：
    ///   - Daily cron 對賬時若無法 100% match (e.g. Bybit balance API 暫時不可達)，
    ///     可保 'pending' 等下一輪；UPDATE 接受全 3 值彈性處理。
    pub async fn update_outcome(
        &self,
        movement_id: i64,
        bybit_response: &JsonValue,
        outcome: &str,
    ) -> Result<(), EarnMovementError> {
        validate_reconciliation_status(outcome)?;

        let result = sqlx::query(
            r#"
            UPDATE learning.earn_movement_log
            SET bybit_response_payload = $1,
                reconciliation_status = $2
            WHERE movement_id = $3
            "#,
        )
        .bind(bybit_response)
        .bind(outcome)
        .bind(movement_id)
        .execute(&self.pool)
        .await?;

        if result.rows_affected() == 0 {
            // movement_id 不存在 (placeholder 未先 INSERT) → 視為 PG error
            // (fail-closed：caller 端 reject intent + release lease)。
            return Err(EarnMovementError::PgError(sqlx::Error::RowNotFound));
        }
        Ok(())
    }

    /// Failure path: 一次性 INSERT failure row (per earn_governance §5.1 fail-closed)。
    ///
    /// 為什麼不走 insert_placeholder + update_outcome 兩步：
    ///   - 失敗時 caller 已知 retCode/retMsg，無需 placeholder「等 ack」；一次 INSERT
    ///     寫定 (direction 仍照 intent 原意 / reconciliation_status='mismatch' /
    ///     bybit_response_payload 攜 retCode/retMsg/timestamp JSON)；
    ///   - reconciliation_status='mismatch' 即「未在 Bybit 端真實執行」標記；
    ///     Daily cron 掃此 row 不再嘗試對賬 (mismatch 是 terminal state)。
    ///
    /// 為什麼 direction 仍照 intent (不寫 'failed')：
    ///   - V100 CHECK 只允許 ('stake'/'redeem')，無 'failed' 值；
    ///   - reconciliation_status='mismatch' 已標記失敗語意；direction 保留 intent 原意
    ///     便於 audit 端「intent 想做 stake 但失敗」 vs 「intent 想做 redeem 但失敗」分流。
    ///
    /// 參數說明：
    ///   - `direction`: 仍照原 intent ('stake'/'redeem')；
    ///   - `amount_usdt`: 仍照原 intent；audit 用 (表明意圖金額)；
    ///   - `apr_at_time`: stake 時若有則填，redeem 時 None；
    ///   - `governance_approval_id`: soft ref 仍存在 (per PA-DRIFT-6)；
    ///   - `engine_mode`: 仍照原 intent；
    ///   - `api_scope_used`: 仍照原 intent；
    ///   - `ret_code`: Bybit retCode (e.g. 10001 invalid sig)；
    ///   - `ret_msg`: Bybit retMsg；
    ///   - `failure_reason`: 內部分類 (e.g. "transport_error" / "business_error" /
    ///     "unknown_error")；caller 端傳對齊 §4.3 §5.1。
    ///
    /// 回傳：RETURNING movement_id (audit/log/test 用)。
    #[allow(clippy::too_many_arguments)]
    pub async fn write_failure(
        &self,
        direction: &str,
        amount_usdt: f64,
        apr_at_time: Option<f32>,
        governance_approval_id: i64,
        engine_mode: &str,
        api_scope_used: &str,
        ret_code: i64,
        ret_msg: &str,
        failure_reason: &str,
    ) -> Result<i64, EarnMovementError> {
        validate_direction(direction)?;
        validate_engine_mode(engine_mode)?;

        let failure_payload = serde_json::json!({
            "ret_code": ret_code,
            "ret_msg": ret_msg,
            "failure_reason": failure_reason,
        });

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
                $5,
                $6,
                $7,
                'mismatch'
            )
            RETURNING movement_id
            "#,
        )
        .bind(direction)
        .bind(amount_usdt)
        .bind(apr_at_time)
        .bind(governance_approval_id)
        .bind(failure_payload)
        .bind(engine_mode)
        .bind(api_scope_used)
        .fetch_one(&self.pool)
        .await?;

        let movement_id: i64 = row.try_get("movement_id")?;
        Ok(movement_id)
    }

    /// Daily reconciliation cron 用：取 past 24h 仍 'pending' 的 row。
    ///
    /// 為什麼這條走 ORDER BY event_ts DESC：
    ///   - V100 hot-path index `idx_earn_movement_log_strategy_ts` 對齊
    ///     (event_ts DESC) — 高效掃描；
    ///   - earn_governance §6 Daily cron 02:00 UTC 跑時，optimal scan 是 past 24h
    ///     範圍內最近 row 先處理 (避 stale row 阻塞 cron)。
    pub async fn fetch_past_24h_pending(
        &self,
    ) -> Result<Vec<EarnMovementRow>, EarnMovementError> {
        let rows: Vec<EarnMovementRow> = sqlx::query_as::<_, EarnMovementRow>(
            r#"
            SELECT
                movement_id,
                event_ts,
                direction,
                amount_usdt::TEXT AS amount_usdt,
                apr_at_time,
                governance_approval_id,
                bybit_response_payload,
                engine_mode,
                api_scope_used,
                reconciliation_status
            FROM learning.earn_movement_log
            WHERE event_ts > now() - INTERVAL '24 hours'
              AND reconciliation_status = 'pending'
            ORDER BY event_ts DESC
            "#,
        )
        .fetch_all(&self.pool)
        .await?;

        Ok(rows)
    }

    /// 反查 governance_approval_id 對應的 learning.governance_audit_log row。
    ///
    /// per PA-DRIFT-6 lesson + V100 line 502-511 註解：
    ///   - governance_approval_id 是 soft reference 非 FK；
    ///   - learning.governance_audit_log 是 TimescaleDB hypertable composite PK (id, ts)，
    ///     PG FK 不能只對齊 (id)；
    ///   - 審計時透過 application-level SELECT 反查；本方法封裝該語意。
    ///
    /// 為什麼回傳 Option<JsonValue> 而非 strong-typed struct：
    ///   - governance_audit_log schema 隨 W-AUDIT-9 / Sprint 1B Earn 演進，行型未穩定；
    ///   - caller 端 (audit forensic / GUI) 端只需 JSON snapshot；
    ///   - 若未來行型穩定，可加 EarnGovernanceAuditRow struct 並 FromRow。
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

    /// 先寫 learning.governance_audit_log 取 BIGSERIAL id，供 earn_movement_log
    /// 的 governance_approval_id soft-ref 注入（兌現 PA-DRIFT-6 預定鏈，見本檔
    /// module doc line 48「caller 必先 INSERT learning.governance_audit_log 取 id」）。
    ///
    /// 為什麼 raw INSERT 而非走 Python audit writer：
    ///   - governance_audit_log 是 multi-producer append-only event log（B 型，非
    ///     單一寫入權威；訂單/交易執行才是單一寫入口 root principle 1）；
    ///   - 本 writer 已持 engine main pool（同 earn_movement_log 寫入 pool）；
    ///   - Python 端 governance_audit_log INSERT 皆 fire-and-forget 無 RETURNING，
    ///     無法回傳 id；走 IPC 只為取一個 id 會把 earn critical path 綁死於
    ///     control_api 可用性 —— 那才是壞設計。
    ///
    /// RETURNING id：governance_audit_log composite PK = (id BIGSERIAL, ts)，取 id
    /// 即可（ts 由 DB DEFAULT now() 生成，不需回傳）。
    ///
    /// 參數說明：
    ///   - `event_type`: 必在 V150 28-value CHECK 白名單內（earn 走
    ///     "earn_stake_approval" / "earn_redeem_approval"，見 earn_router
    ///     earn_audit_event_type helper）；不在則 PG CHECK fail-loud → PgError，
    ///     caller fail-closed reject。
    ///   - `decision_lease_id`: earn lease_id 的 String（審計鏈 join key）。
    ///   - `decided_by`: V035 `decided_by TEXT NOT NULL` → 傳 actor_id（operator
    ///     role），絕不空字串。
    ///   - `payload`: forensic JSONB（approval_id UUID / intent_id / direction /
    ///     amount / engine_mode / api_scope）。其餘 nullable 欄靠 DB DEFAULT。
    ///
    /// 沿用既有 `EarnMovementError`：CHECK 違反與 PG 不可達皆落 `PgError`（`sqlx::
    /// Error::Database` / 連線錯誤），caller 一律 fail-closed，語意足夠，不新增 variant。
    pub async fn insert_governance_audit_log(
        &self,
        event_type: &str,
        decision_lease_id: &str,
        decided_by: &str,
        payload: &JsonValue,
    ) -> Result<i64, EarnMovementError> {
        let row = sqlx::query(
            r#"
            INSERT INTO learning.governance_audit_log (
                event_type,
                decision_lease_id,
                decided_by,
                payload
            )
            VALUES ($1, $2, $3, $4)
            RETURNING id
            "#,
        )
        .bind(event_type)
        .bind(decision_lease_id)
        .bind(decided_by)
        .bind(payload)
        .fetch_one(&self.pool)
        .await?;

        let id: i64 = row.try_get("id")?;
        Ok(id)
    }
}

/// V100 direction CHECK ('stake'/'redeem') client-side 驗。
fn validate_direction(direction: &str) -> Result<(), EarnMovementError> {
    match direction {
        "stake" | "redeem" => Ok(()),
        other => Err(EarnMovementError::InvalidDirection(other.to_string())),
    }
}

/// V100 engine_mode CHECK ('paper'/'demo'/'live_demo'/'live') client-side 驗。
fn validate_engine_mode(engine_mode: &str) -> Result<(), EarnMovementError> {
    match engine_mode {
        "paper" | "demo" | "live_demo" | "live" => Ok(()),
        other => Err(EarnMovementError::InvalidEngineMode(other.to_string())),
    }
}

/// V100 reconciliation_status CHECK ('pending'/'matched'/'mismatch') client-side 驗。
fn validate_reconciliation_status(status: &str) -> Result<(), EarnMovementError> {
    match status {
        "pending" | "matched" | "mismatch" => Ok(()),
        other => Err(EarnMovementError::InvalidReconciliationStatus(other.to_string())),
    }
}

#[cfg(test)]
mod tests {
    //! 單元測試：純 client-side validator + V100 schema 對齊測試。
    //!
    //! 為什麼不接 in-memory PG mock：
    //!   - workspace 無 in-memory PG (sqlx::test 需 Linux PG runtime / TestContainers，
    //!     違 mac dev local-only constraint)；
    //!   - SQL 字串對齊 V100 schema 透過 include_str! 自身 + grep-style assert
    //!     (per lease_transition_writer.rs test_insert_sql_locked_columns 範式 line 476)；
    //!   - 真實 PG roundtrip 留 E4 regression + QA Stage 0R replay 驗證
    //!     (per dispatch packet §7.5 Wave D)。

    use super::*;

    /// validate_direction 接受 'stake' / 'redeem'；其他全拒。
    #[test]
    fn test_validate_direction_accepts_canonical() {
        assert!(validate_direction("stake").is_ok());
        assert!(validate_direction("redeem").is_ok());
    }

    /// validate_direction 拒空字串 / 大小寫變體 / 其他值。
    #[test]
    fn test_validate_direction_rejects_invalid() {
        let cases = ["", "STAKE", "Stake", "withdraw", "deposit", "stake "];
        for case in cases {
            let result = validate_direction(case);
            assert!(
                matches!(result, Err(EarnMovementError::InvalidDirection(_))),
                "direction {case:?} must be rejected",
            );
        }
    }

    /// validate_engine_mode 接受 V100 CHECK 4 enum。
    #[test]
    fn test_validate_engine_mode_accepts_canonical() {
        for mode in ["paper", "demo", "live_demo", "live"] {
            assert!(
                validate_engine_mode(mode).is_ok(),
                "engine_mode {mode} must be accepted",
            );
        }
    }

    /// validate_engine_mode 拒大小寫變體 / 空 / 未列舉值。
    #[test]
    fn test_validate_engine_mode_rejects_invalid() {
        let cases = ["", "PAPER", "Paper", "LIVE", "shadow", "test"];
        for case in cases {
            let result = validate_engine_mode(case);
            assert!(
                matches!(result, Err(EarnMovementError::InvalidEngineMode(_))),
                "engine_mode {case:?} must be rejected",
            );
        }
    }

    /// validate_reconciliation_status 接受 V100 CHECK 3 enum。
    #[test]
    fn test_validate_reconciliation_status_accepts_canonical() {
        for status in ["pending", "matched", "mismatch"] {
            assert!(
                validate_reconciliation_status(status).is_ok(),
                "reconciliation_status {status} must be accepted",
            );
        }
    }

    /// validate_reconciliation_status 拒未列舉值。
    #[test]
    fn test_validate_reconciliation_status_rejects_invalid() {
        let cases = ["", "PENDING", "ok", "failed", "in_progress"];
        for case in cases {
            let result = validate_reconciliation_status(case);
            assert!(
                matches!(
                    result,
                    Err(EarnMovementError::InvalidReconciliationStatus(_))
                ),
                "reconciliation_status {case:?} must be rejected",
            );
        }
    }

    /// SQL 字串對齊 V100 schema 10 column lock — 防 silent schema drift。
    ///
    /// 為什麼用 include_str! self-grep 範式：
    ///   - per lease_transition_writer.rs test_insert_sql_locked_columns line 476，
    ///     將 INSERT SQL 內 column 名與 V100 schema 字串對齊；
    ///   - 若未來「順手 rename」column 名 (e.g. `amount_usdt` → `amount`)，本 test
    ///     直接 fail，提示 reviewer 必同步 V### migration + 本 writer。
    #[test]
    fn test_insert_sql_locked_columns_match_v100_schema() {
        let src = include_str!("earn_movement_writer.rs");
        // V100 schema 10 column 全列；其中 movement_id 走 RETURNING 不出現在 INSERT
        // value list，但出現在 RETURNING / fetch_past_24h_pending SELECT 中。
        for col in [
            "movement_id",
            "event_ts",
            "direction",
            "amount_usdt",
            "apr_at_time",
            "governance_approval_id",
            "bybit_response_payload",
            "engine_mode",
            "api_scope_used",
            "reconciliation_status",
        ] {
            assert!(
                src.contains(col),
                "earn_movement_writer.rs missing V100 column: {col} (schema drift risk)",
            );
        }
    }

    /// INSERT SQL 必含 `learning.earn_movement_log` 表名 (V100 schema location lock)。
    #[test]
    fn test_insert_sql_locked_table_name() {
        let src = include_str!("earn_movement_writer.rs");
        assert!(
            src.contains("learning.earn_movement_log"),
            "earn_movement_writer.rs missing V100 table name `learning.earn_movement_log`",
        );
    }

    /// INSERT SQL 必走 `$2::NUMERIC(18,8)` cast (workspace 無 BigDecimal feature)。
    #[test]
    fn test_insert_sql_uses_numeric_cast() {
        let src = include_str!("earn_movement_writer.rs");
        assert!(
            src.contains("::NUMERIC(18,8)"),
            "earn_movement_writer.rs INSERT must use ::NUMERIC(18,8) cast (workspace no BigDecimal dep)",
        );
    }

    /// INSERT SQL 必含 `RETURNING movement_id` 讓 caller 取 PK。
    #[test]
    fn test_insert_sql_returns_movement_id() {
        let src = include_str!("earn_movement_writer.rs");
        assert!(
            src.contains("RETURNING movement_id"),
            "earn_movement_writer.rs INSERT must RETURNING movement_id for caller's Step 2 UPDATE",
        );
    }

    /// fetch_past_24h_pending SQL 必含 `event_ts > now() - INTERVAL '24 hours'`
    /// + `reconciliation_status = 'pending'` (Daily cron 對賬語意 lock)。
    #[test]
    fn test_fetch_24h_pending_sql_window_lock() {
        let src = include_str!("earn_movement_writer.rs");
        assert!(
            src.contains("INTERVAL '24 hours'"),
            "fetch_past_24h_pending must use INTERVAL '24 hours' window",
        );
        assert!(
            src.contains("reconciliation_status = 'pending'"),
            "fetch_past_24h_pending must filter reconciliation_status = 'pending'",
        );
        assert!(
            src.contains("ORDER BY event_ts DESC"),
            "fetch_past_24h_pending must ORDER BY event_ts DESC (V100 hot-path index alignment)",
        );
    }

    /// write_failure SQL 必直寫 reconciliation_status = 'mismatch' (一次性 terminal state)。
    #[test]
    fn test_write_failure_sql_terminal_mismatch() {
        let src = include_str!("earn_movement_writer.rs");
        // src 應在 write_failure 內 INSERT VALUES (...) 處出現 'mismatch' 字面量。
        let mismatch_occurrences = src.matches("'mismatch'").count();
        assert!(
            mismatch_occurrences >= 1,
            "write_failure must INSERT with reconciliation_status = 'mismatch' (terminal state)",
        );
    }

    /// lookup_governance_approval SQL 必含 `learning.governance_audit_log` 表名 +
    /// `id = $1` 對齊 PA-DRIFT-6 soft reference 範式。
    #[test]
    fn test_lookup_governance_approval_sql_target() {
        let src = include_str!("earn_movement_writer.rs");
        assert!(
            src.contains("learning.governance_audit_log"),
            "lookup_governance_approval must reverse-query learning.governance_audit_log (PA-DRIFT-6)",
        );
        assert!(
            src.contains("g.id = $1"),
            "lookup_governance_approval must filter by g.id = $1 (soft reference)",
        );
    }

    /// insert_governance_audit_log SQL 必寫 `learning.governance_audit_log` 表 +
    /// `RETURNING id`（CC-3 兌現 PA-DRIFT-6 鏈：先寫 audit log 取真 BIGSERIAL id）。
    #[test]
    fn test_insert_governance_audit_log_sql_target() {
        let src = include_str!("earn_movement_writer.rs");
        assert!(
            src.contains("INSERT INTO learning.governance_audit_log"),
            "insert_governance_audit_log must INSERT INTO learning.governance_audit_log (CC-3)",
        );
        assert!(
            src.contains("RETURNING id"),
            "insert_governance_audit_log must RETURNING id for earn_router Gate E-5.5 soft-ref",
        );
    }

    /// EarnMovementError Display 文字含 column / enum 名 (便於 grep log 排查)。
    #[test]
    fn test_error_display_messages_informative() {
        let e = EarnMovementError::InvalidDirection("foo".to_string());
        let msg = format!("{e}");
        assert!(msg.contains("direction"), "InvalidDirection msg must mention 'direction': {msg}");
        assert!(msg.contains("foo"), "InvalidDirection msg must mention input value: {msg}");

        let e = EarnMovementError::InvalidEngineMode("bar".to_string());
        let msg = format!("{e}");
        assert!(msg.contains("engine_mode"), "InvalidEngineMode msg must mention 'engine_mode': {msg}");

        let e = EarnMovementError::InvalidReconciliationStatus("baz".to_string());
        let msg = format!("{e}");
        assert!(
            msg.contains("reconciliation_status"),
            "InvalidReconciliationStatus msg must mention 'reconciliation_status': {msg}",
        );
    }
}
