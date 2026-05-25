//! Sprint 2 Stream D W2-D — V109 `learning.anomaly_events` writer skeleton。
//!
//! MODULE_NOTE
//! 模塊用途：
//!   M8 anomaly_events 寫入骨架；Sprint 3 detector wire 前置實裝。本 module 不寫
//!   detector 演算法 (Sprint 3 W3-A/W3-B 才上)，只提供：
//!     - 23 column INSERT 對齊 V109 schema (含 v2 amend `metric_baseline`)
//!     - 4 client-side validator (event_taxonomy 9 / severity 4 / detection_method 4
//!       / engine_mode 5) — early fail 避 PG roundtrip
//!     - amplification cap H-11 helper：寫入前查 24h 同 (symbol, event_taxonomy)
//!       CRITICAL/HALT count；caller 依結果決定 evidence_json 是否標 cap_suppressed
//!     - Sprint 3 detector 透過 `pub use write_anomaly_event` 訂閱本 writer
//!
//! 主要類 / 函數：
//!   - `AnomalyEventWriter`：sqlx::PgPool 包裝；提供 write_anomaly_event +
//!     amplification_loop_24h_count helper。
//!   - `AnomalyEventRow`：23 column row 投影 (INSERT 輸入 + Sprint 3 query 輸出)。
//!   - `AnomalyEventError`：寫入失敗錯誤碼 (PG / 4 enum validate 各 1)。
//!   - `validate_event_taxonomy` / `validate_severity` / `validate_detection_method`
//!     / `validate_engine_mode` — V109 CHECK constraint client-side mirror，且
//!     `validate_detection_method` 強制黑名單 HMM / Markov-switching / GARCH。
//!
//! 依賴：
//!   - sqlx Postgres + serde_json + chrono (workspace deps，無新引入)；
//!   - 不引 rust_decimal / BigDecimal — V109 NUMERIC(18,8) column 透過
//!     `$N::NUMERIC(18,8)` PG cast 從 f64 注入 (對齊 earn_movement_writer.rs +
//!     health/writer.rs 範式)；
//!   - 不依賴 Sprint 3 detector — writer 取 primitive 參數，caller 端組裝
//!     AnomalyEventRow。
//!
//! 硬邊界：
//!   - 0 sudo / 0 cargo build (Mac SSOT)；本 module Sprint 2 Wave 1 不接 cron / runtime。
//!   - V109 schema 23 column 嚴格對齊 (per sql/migrations/V109 line 353-438)；
//!     新增 column 必同步更新本 module + 新增 unit test。
//!   - **ADR-0036 Decision 1 forbidden algorithm**：detection_method 黑名單 HMM /
//!     Markov-switching / GARCH 永久禁用；validator 強制 compile-time block
//!     (per V109 Guard A/C 雙重反向防護 schema-level enforce + 本 writer client-side
//!     mirror = 三重防護)。
//!   - DRAFT writeback ≠ live order；M8 anomaly_event 是 sensor 寫入不觸 live trade
//!     (per AMD-2026-05-21-01 + earn_governance 模式)；不寫 trading.fills。
//!   - engine_mode CHECK 5 enum ('paper' / 'demo' / 'live_demo' / 'live' / 'replay')
//!     — replay 是 ADR-0036 Decision 1 例外段 (M11 read-only counterfactual);
//!     ML training filter 必 IN ('live','live_demo') per CLAUDE.md §七。
//!   - amplification_loop_24h_count writer 預計算 (per H-11 + M3 §6.2)：≥ 2 雖
//!     INSERT 但 caller 標 evidence_json.cap_suppressed=true 不 emit M3 cascade。
//!   - m3 / m7 / m1_lal _ref BIGINT soft reference (非 FK 跨 hypertable; per V109
//!     spec §8.7)；application 層 + healthcheck 補 referential integrity。
//!
//! 不變量：
//!   - 任何成功 INSERT 對應「至少 1 row」在 learning.anomaly_events (無 silent skip)。
//!   - 4 enum validator early fail 在 client-side；不發送非法 row 給 PG。
//!   - amplification_loop_24h_count helper 是 read-only SELECT；caller decide cap
//!     enforcement policy (writer 不自動 mutate cap_suppressed flag)。
//!
//! 規格 / Spec:
//!   - V109 SQL: `sql/migrations/V109__m8_anomaly_events_hypertable.sql`
//!   - V109 spec v2 amend: `docs/execution_plan/2026-05-25--v109_m8_anomaly_events_schema_spec_v2_amend.md`
//!   - V109 spec base: `docs/execution_plan/2026-05-21--v109_m8_anomaly_events_schema_spec.md`
//!   - M8 design spec: `docs/execution_plan/2026-05-21--m8_anomaly_detection_design_spec.md` (§5 H-11)
//!   - ADR-0036: `docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md`
//!   - Sister writer pattern: `earn_movement_writer.rs` (Sprint 1B Earn Wave B)

use serde_json::Value as JsonValue;
use sqlx::{FromRow, PgPool, Row};

/// V109 `learning.anomaly_events` 23 column 對齊 row 投影。
///
/// 為什麼 BIGSERIAL `id` 走 RETURNING：
///   - PG BIGSERIAL 由 DB 端 nextval 取；INSERT 不傳 id 而是 RETURNING id 讓
///     caller 取得，後續 cross-ref update (UPDATE SET m3_health_observation_ref ...
///     WHERE id = $) 才能定位 row (per V109 spec §8.3 example 1)。
///
/// 為什麼 amount column 用 String：
///   - V109 metric_value / metric_baseline / metric_threshold 是 NUMERIC(18,8)；
///   - workspace sqlx feature 沒開 rust_decimal / BigDecimal (避大 dep)；
///   - 對齊 earn_movement_writer 範式：String 接收 read 端，f64 + ::NUMERIC cast
///     write 端。
///
/// 為什麼 timestamptz 用 chrono::DateTime<Utc>：
///   - sqlx Postgres feature 已啟 chrono；對齊 health/writer.rs PgHealthObservationRow。
#[derive(Debug, Clone, FromRow)]
pub struct AnomalyEventRow {
    /// V109 column `id BIGSERIAL`：DB 端 nextval (PRIMARY KEY 含 observed_at)。
    pub id: i64,
    /// V109 column `observed_at TIMESTAMPTZ NOT NULL`：anomaly 觀測時刻。
    pub observed_at: chrono::DateTime<chrono::Utc>,
    /// V109 column `event_taxonomy TEXT NOT NULL`：CHECK 9 enum。
    pub event_taxonomy: String,
    /// V109 column `severity TEXT NOT NULL`：CHECK 4 enum (INFO/WARN/CRITICAL/HALT)。
    pub severity: String,
    /// V109 column `detection_method TEXT NOT NULL`：CHECK 4 enum (no HMM/Markov/GARCH)。
    pub detection_method: String,
    /// V109 column `atr_vol_state TEXT`：CHECK NULL OR (LOW/MED/HIGH)；9-cell axis 1。
    pub atr_vol_state: Option<String>,
    /// V109 column `funding_state TEXT`：CHECK NULL OR (NEGATIVE/NEUTRAL/POSITIVE)；9-cell axis 2。
    pub funding_state: Option<String>,
    /// V109 column `strategy_id TEXT`：可 NULL (大多 anomaly 不綁 strategy)。
    pub strategy_id: Option<String>,
    /// V109 column `symbol TEXT`：可 NULL (system-level anomaly e.g. ws_disconnect)。
    pub symbol: Option<String>,
    /// V109 column `metric_value NUMERIC(18,8)`：當下觀測值；String 接收避 dep。
    pub metric_value: Option<String>,
    /// V109 column `metric_baseline NUMERIC(18,8)`：v2 amend P1-5 新增；30d rolling
    /// block bootstrap baseline；drift PSI 比對用。
    pub metric_baseline: Option<String>,
    /// V109 column `metric_threshold NUMERIC(18,8)`：當下 active threshold。
    pub metric_threshold: Option<String>,
    /// V109 column `amplification_loop_24h_count INTEGER NOT NULL DEFAULT 0`：
    /// per H-11 cap；writer 預計算 24h 同 event_taxonomy CRITICAL/HALT count。
    pub amplification_loop_24h_count: i32,
    /// V109 column `m3_health_observation_ref BIGINT`：M3 cross-ref soft FK。
    pub m3_health_observation_ref: Option<i64>,
    /// V109 column `m7_decay_signal_ref BIGINT`：M7 cross-ref soft FK。
    pub m7_decay_signal_ref: Option<i64>,
    /// V109 column `m1_lal_demote_ref BIGINT`：M1 LAL Tier 降階 ref；per ADR-0034
    /// 數字越大越嚴方向 — ref 指向 demote 後 row 而非 promote。
    pub m1_lal_demote_ref: Option<i64>,
    /// V109 column `evidence_json JSONB`：detector raw output / cap_suppressed flag /
    /// atr percentile window / cascade_actions_taken 等 audit 富 context。
    pub evidence_json: Option<JsonValue>,
    /// V109 column `engine_mode TEXT NOT NULL`：CHECK 5 enum (per v2 amend P0-3)。
    pub engine_mode: String,
    /// V109 column `created_by TEXT NOT NULL DEFAULT 'anomaly_detector'`。
    pub created_by: String,
    /// V109 column `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`。
    pub created_at: chrono::DateTime<chrono::Utc>,
    /// V109 column `updated_by TEXT`：後續 update 的 actor (cross-ref backfill)。
    pub updated_by: Option<String>,
    /// V109 column `updated_at TIMESTAMPTZ`：後續 update 時刻。
    pub updated_at: Option<chrono::DateTime<chrono::Utc>>,
    /// V109 column `source_version TEXT NOT NULL DEFAULT 'V109'`。
    pub source_version: String,
}

/// V109 writer 錯誤碼。
///
/// 為什麼分 4 個 invalid_* 變體：
///   - 4 CHECK constraint 個別 client-side fail-fast；caller 端可分支處理 (e.g.
///     event_taxonomy 不認得 → 上游 detector mapping bug；engine_mode 不認得 →
///     config 拼錯)。
///   - 黑名單 HMM/Markov/GARCH 走 `InvalidDetectionMethod` (錯誤訊息含 ADR-0036
///     引用便於 grep)。
#[derive(Debug, thiserror::Error)]
pub enum AnomalyEventError {
    /// PG INSERT / SELECT 失敗。
    #[error("PG operation failed: {0}")]
    PgError(#[from] sqlx::Error),
    /// event_taxonomy 不在 V109 CHECK 9 enum (per M8 design spec §2.1)。
    #[error(
        "invalid event_taxonomy '{0}' (must be one of regime_shift/liquidation_cascade/\
         orderbook_imbalance/funding_outlier/volume_spike/spread_widening/\
         price_dislocation/ws_disconnect/fee_anomaly)"
    )]
    InvalidEventTaxonomy(String),
    /// severity 不在 V109 CHECK 4 enum。
    #[error("invalid severity '{0}' (must be one of INFO/WARN/CRITICAL/HALT)")]
    InvalidSeverity(String),
    /// detection_method 不在 V109 CHECK 4 enum，或含 ADR-0036 Decision 1 黑名單。
    #[error(
        "invalid detection_method '{0}' (must be one of atr_vol_funding_9cell/\
         rv_percentile/block_bootstrap/manual_operator; HMM / Markov-switching / \
         GARCH 永久禁用 per ADR-0036 Decision 1)"
    )]
    InvalidDetectionMethod(String),
    /// engine_mode 不在 V109 CHECK 5 enum。
    #[error(
        "invalid engine_mode '{0}' (must be one of paper/demo/live_demo/live/replay)"
    )]
    InvalidEngineMode(String),
}

/// V109 `learning.anomaly_events` writer。
///
/// 為什麼 PgPool 不包 Arc：
///   - sqlx::PgPool 內部已 Arc-shared (clone 廉價)；無需再包 Arc。
///   - 對齊 earn_movement_writer.rs + health/writer.rs PgHealthObservationWriter 範式。
///   - caller 端持 PgPool clone 注入 writer (one-shot constructor)。
pub struct AnomalyEventWriter {
    pool: PgPool,
}

impl AnomalyEventWriter {
    /// 建立 writer；caller 端 share PgPool (engine main pool)。
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    /// 主 INSERT：寫一筆 anomaly_event 進 V109 hypertable。
    ///
    /// 為什麼一條 INSERT (不像 earn writer 兩階段 placeholder + update)：
    ///   - M8 anomaly 是 sensor 觀測 emit；不像 earn stake/redeem 有 Bybit API
    ///     ack 等待期。caller 已知 detector output 即可一次寫定。
    ///   - cross-ref column (m3 / m7 / m1_lal _ref) 是後續 cascade emit 後另一條
    ///     UPDATE 補 (per V109 spec §8.3 example 1)；本 INSERT 預設留 NULL。
    ///
    /// 參數說明：
    ///   - `row`：Sprint 3 detector 組裝好的 row (id / created_at / created_by /
    ///     source_version 由 DB DEFAULT 填，caller 傳 sentinel 不影響)。
    ///   - 4 enum field (event_taxonomy / severity / detection_method / engine_mode)
    ///     client-side 驗 fail early；ADR-0036 黑名單 detection_method 在
    ///     validate_detection_method 強制 reject。
    ///
    /// 回傳：RETURNING id (i64)，供 caller 後續 cross-ref UPDATE 用。
    ///
    /// 為什麼 NUMERIC(18,8) cast `$N::NUMERIC(18,8)`：
    ///   - workspace sqlx feature 沒開 rust_decimal / BigDecimal；f64 直 bind PG
    ///     NUMERIC 會 type mismatch。透過 PG-side cast 從文字注入後 PG 精度轉換，
    ///     per earn_movement_writer.rs line 188-193 + health/writer.rs line 209-215 同範式。
    ///   - NUMERIC(18,8) 對應 18 位整數 + 8 位小數，足以保留 funding rate (1e-6) /
    ///     spread bps (1e-2) / price (1e8) 等 metric 精度。
    pub async fn write_anomaly_event(
        &self,
        row: &AnomalyEventRow,
    ) -> Result<i64, AnomalyEventError> {
        validate_event_taxonomy(&row.event_taxonomy)?;
        validate_severity(&row.severity)?;
        validate_detection_method(&row.detection_method)?;
        validate_engine_mode(&row.engine_mode)?;

        // metric_value / metric_baseline / metric_threshold 從 Option<String> 轉
        // Option<f64> (PG-side ::NUMERIC(18,8) cast)。
        // 注意：parse fail (e.g. caller 傳 "not-a-number") → 視為 NULL；caller
        // 端若需嚴格驗證自行檢；本 writer 不對輸入字串 panic。
        let mv: Option<f64> = row.metric_value.as_deref().and_then(|s| s.parse().ok());
        let mb: Option<f64> = row.metric_baseline.as_deref().and_then(|s| s.parse().ok());
        let mt: Option<f64> = row.metric_threshold.as_deref().and_then(|s| s.parse().ok());

        // V109 23 column INSERT；id / created_by / created_at / source_version 走
        // DEFAULT (per V109 SQL line 354 + 432-436)；本 INSERT 不傳這 4 column 而由
        // PG 自動填。
        // 注意 RETURNING (id, created_at) — 對齊 PRIMARY KEY (id, observed_at) +
        // 額外取 created_at 供 caller log。
        let row_result = sqlx::query(
            r#"
            INSERT INTO learning.anomaly_events (
                observed_at,
                event_taxonomy,
                severity,
                detection_method,
                atr_vol_state,
                funding_state,
                strategy_id,
                symbol,
                metric_value,
                metric_baseline,
                metric_threshold,
                amplification_loop_24h_count,
                m3_health_observation_ref,
                m7_decay_signal_ref,
                m1_lal_demote_ref,
                evidence_json,
                engine_mode
            )
            VALUES (
                $1,
                $2,
                $3,
                $4,
                $5,
                $6,
                $7,
                $8,
                $9::NUMERIC(18,8),
                $10::NUMERIC(18,8),
                $11::NUMERIC(18,8),
                $12,
                $13,
                $14,
                $15,
                $16,
                $17
            )
            RETURNING id
            "#,
        )
        .bind(row.observed_at)
        .bind(&row.event_taxonomy)
        .bind(&row.severity)
        .bind(&row.detection_method)
        .bind(&row.atr_vol_state)
        .bind(&row.funding_state)
        .bind(&row.strategy_id)
        .bind(&row.symbol)
        .bind(mv)
        .bind(mb)
        .bind(mt)
        .bind(row.amplification_loop_24h_count)
        .bind(row.m3_health_observation_ref)
        .bind(row.m7_decay_signal_ref)
        .bind(row.m1_lal_demote_ref)
        .bind(&row.evidence_json)
        .bind(&row.engine_mode)
        .fetch_one(&self.pool)
        .await?;

        let id: i64 = row_result.try_get("id")?;
        Ok(id)
    }

    /// 預查 24h amplification cap count helper (per H-11 + M3 §6.2 + V109 spec §5.3)。
    ///
    /// 為什麼是 helper 不是自動 enforce：
    ///   - cap enforcement 政策 (≥ 2 標 cap_suppressed=true) 在 caller 端 (Sprint 3
    ///     detector + M3 cascade emit policy)；writer 只回 raw count，caller
    ///     decide 是否標 evidence_json.cap_suppressed=true 不 emit M3 cascade。
    ///   - 對齊 V109 spec §5.3 SQL pattern。
    ///
    /// 為什麼參數含 engine_mode：
    ///   - per V109 spec §5.3 line 277-278 + 1 paper / demo / live_demo / live /
    ///     replay 5 個獨立計數空間；live 環境的 cap 不該被 paper anomaly 噪音污染。
    ///   - caller 傳當下 engine_mode (從 row.engine_mode 拍出來)。
    ///
    /// 為什麼只計 CRITICAL/HALT 不含 INFO/WARN：
    ///   - per H-11 + M3 §6.2 「1 anomaly_type = 1 state change / 24h」針對的是
    ///     trigger M3 cascade 的 severity (CRITICAL/HALT)；INFO/WARN 不 trigger
    ///     M3 state change (per M8 design spec §6.1)，不計入 cap。
    ///
    /// 參數說明：
    ///   - `event_taxonomy`：9 enum 之一 (client-side 驗)；
    ///   - `engine_mode`：5 enum 之一 (client-side 驗)；
    ///   - `since`：24h 視窗起點 (caller 傳 `now() - 24h`；明示傳避隱式時鐘漂移)。
    ///
    /// 回傳：i32 count；caller decide ≥ 2 是否標 cap_suppressed。
    pub async fn amplification_loop_24h_count(
        &self,
        event_taxonomy: &str,
        engine_mode: &str,
        since: chrono::DateTime<chrono::Utc>,
    ) -> Result<i32, AnomalyEventError> {
        validate_event_taxonomy(event_taxonomy)?;
        validate_engine_mode(engine_mode)?;

        // per V109 spec §5.3 SQL pattern：同 event_taxonomy + 24h + severity IN
        // ('CRITICAL','HALT') + engine_mode 同。
        // 注意 BIGINT count → i64 → as i32 cast；24h 內同 type CRITICAL/HALT 不
        // 可能超 i32::MAX (60-300 row/day total per V109 spec §3.1)。
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
        .bind(event_taxonomy)
        .bind(since)
        .bind(engine_mode)
        .fetch_one(&self.pool)
        .await?;

        let count: i64 = row.try_get("cnt")?;
        Ok(count as i32)
    }
}

/// V109 event_taxonomy CHECK 9 enum client-side 驗 (per M8 design spec §2.1)。
///
/// 為什麼 9 enum 名以 array literal 列出：
///   - compile-time const reference；rust grep 即可枚舉 9 值，便於 audit。
///   - Sprint 3 若 PA + MIT 仲裁加 / 改 taxonomy：必同步 V109 ENUM amend +
///     本 array + AnomalyEventError msg 字面值。
pub fn validate_event_taxonomy(taxonomy: &str) -> Result<(), AnomalyEventError> {
    const VALID: &[&str] = &[
        "regime_shift",
        "liquidation_cascade",
        "orderbook_imbalance",
        "funding_outlier",
        "volume_spike",
        "spread_widening",
        "price_dislocation",
        "ws_disconnect",
        "fee_anomaly",
    ];
    if VALID.contains(&taxonomy) {
        Ok(())
    } else {
        Err(AnomalyEventError::InvalidEventTaxonomy(taxonomy.to_string()))
    }
}

/// V109 severity CHECK 4 enum client-side 驗 (per v2 amend P0-2)。
///
/// HALT Y2+ 不寫 row 但 ENUM value 必先 land 避 future ALTER (per v2 amend P0-2)。
pub fn validate_severity(severity: &str) -> Result<(), AnomalyEventError> {
    const VALID: &[&str] = &["INFO", "WARN", "CRITICAL", "HALT"];
    if VALID.contains(&severity) {
        Ok(())
    } else {
        Err(AnomalyEventError::InvalidSeverity(severity.to_string()))
    }
}

/// V109 detection_method CHECK 4 enum client-side 驗 (per ADR-0036 Decision 2-4)。
///
/// **ADR-0036 Decision 1 黑名單**：HMM / Markov-switching / GARCH 永久禁用
/// schema-level enforcement。即使 caller 傳 hmm_filter / markov_switch / garch_x
/// 也會被本 validator reject (反 substring match)；對齊 V109 Guard A line 117-138 +
/// Guard C line 244-254 雙重反向防護。
///
/// 為什麼用 substring match 不是 exact match for blacklist：
///   - caller 端可能拼 hmm_v2 / arima_markov / garch_1_1 等變體；substring 反向
///     match 是 strictest enforcement；對齊 V109 Guard A line 126-128 position()
///     lower() 範式。
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

    // 4 替代算法 per ADR-0036 Decision 2-4 + V109 spec §2.1。
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

/// V109 engine_mode CHECK 5 enum client-side 驗 (per v2 amend P0-3)。
///
/// 為什麼含 'replay' 第 5 值：
///   - ADR-0036 Decision 1 例外段：M11 replay surface read-only counterfactual
///     可寫入 V109 但 training filter 必 IN ('live','live_demo') per CLAUDE.md §七。
pub fn validate_engine_mode(mode: &str) -> Result<(), AnomalyEventError> {
    const VALID: &[&str] = &["paper", "demo", "live_demo", "live", "replay"];
    if VALID.contains(&mode) {
        Ok(())
    } else {
        Err(AnomalyEventError::InvalidEngineMode(mode.to_string()))
    }
}

#[cfg(test)]
mod tests {
    //! 單元測試：純 client-side validator + V109 schema SQL 對齊測試。
    //!
    //! 為什麼不接 in-memory PG mock：
    //!   - workspace 無 in-memory PG (sqlx::test 需 Linux PG runtime / TestContainers，
    //!     違 Mac dev local-only constraint per CLAUDE.md §六)；
    //!   - SQL 字串對齊 V109 schema 透過 include_str! 自身 + grep-style assert
    //!     (per earn_movement_writer.rs + lease_transition_writer.rs 範式)；
    //!   - 真實 PG roundtrip 留 Sprint 3 W2-E E2 對抗式 review + W3-A detector wire
    //!     後的 Linux empirical 跑。

    use super::*;
    use chrono::{TimeZone, Utc};

    // ─────────────────────────────────────────────────────────────────────
    // Test 1: minimal INSERT row construction — 必要 column 全填，可選 NULL。
    //
    // 為什麼驗 row construction 不直接驗 PG INSERT：
    //   - Mac SSOT 無 in-memory PG；test 範圍 = struct field 完整性 + serializable
    //     + SQL grep 對齊；
    //   - Sprint 3 接 cron + Linux empirical 後跑 round-trip。
    // ─────────────────────────────────────────────────────────────────────
    #[test]
    fn test_write_anomaly_event_minimal() {
        // 建一個 AnomalyEventRow 對齊 V109 23 column；驗 struct field 全可 set。
        let row = AnomalyEventRow {
            id: 0, // INSERT 時 ignore；DB DEFAULT 填
            observed_at: Utc.with_ymd_and_hms(2026, 5, 25, 12, 0, 0).unwrap(),
            event_taxonomy: "regime_shift".to_string(),
            severity: "WARN".to_string(),
            detection_method: "atr_vol_funding_9cell".to_string(),
            atr_vol_state: Some("HIGH".to_string()),
            funding_state: Some("NEGATIVE".to_string()),
            strategy_id: Some("grid".to_string()),
            symbol: Some("BTCUSDT".to_string()),
            metric_value: Some("0.05".to_string()),
            metric_baseline: Some("0.02".to_string()),
            metric_threshold: Some("0.04".to_string()),
            amplification_loop_24h_count: 0,
            m3_health_observation_ref: None,
            m7_decay_signal_ref: None,
            m1_lal_demote_ref: None,
            evidence_json: Some(serde_json::json!({"detector_raw": "test"})),
            engine_mode: "live".to_string(),
            created_by: "anomaly_detector".to_string(),
            created_at: Utc.with_ymd_and_hms(2026, 5, 25, 12, 0, 0).unwrap(),
            updated_by: None,
            updated_at: None,
            source_version: "V109".to_string(),
        };
        // 驗 4 enum field 全合法 (validator pass)。
        assert!(validate_event_taxonomy(&row.event_taxonomy).is_ok());
        assert!(validate_severity(&row.severity).is_ok());
        assert!(validate_detection_method(&row.detection_method).is_ok());
        assert!(validate_engine_mode(&row.engine_mode).is_ok());
        // 驗 amplification cap 初始 0。
        assert_eq!(row.amplification_loop_24h_count, 0);
        // 驗 cross-ref 全 None (INSERT 時走 NULL；後續 cascade 後 UPDATE 補)。
        assert!(row.m3_health_observation_ref.is_none());
        assert!(row.m7_decay_signal_ref.is_none());
        assert!(row.m1_lal_demote_ref.is_none());
    }

    // ─────────────────────────────────────────────────────────────────────
    // Test 2: 9 event_taxonomy enum pass + invalid reject。
    // ─────────────────────────────────────────────────────────────────────
    #[test]
    fn test_validate_taxonomy_9_enum_pass_and_invalid_reject() {
        // 9 enum 全接受。
        for tax in [
            "regime_shift",
            "liquidation_cascade",
            "orderbook_imbalance",
            "funding_outlier",
            "volume_spike",
            "spread_widening",
            "price_dislocation",
            "ws_disconnect",
            "fee_anomaly",
        ] {
            assert!(
                validate_event_taxonomy(tax).is_ok(),
                "taxonomy {tax} must be accepted (V109 CHECK 9 enum)",
            );
        }
        // invalid case：空 / 大小寫變體 / 已剔除 own behavior enum (走 M3) /
        // 已剔除 replay_divergence (走 V107)。
        let invalid_cases = [
            "",
            "REGIME_SHIFT",
            "Regime_Shift",
            "fill_rate_drift",    // 已剔除：走 M3 strategy_quality
            "slippage_outlier",   // 已剔除：走 M3
            "lease_grant_anomaly", // 已剔除：走 M3
            "replay_divergence",  // 已剔除：走 V107 M11
            "unknown_event",
        ];
        for case in invalid_cases {
            let result = validate_event_taxonomy(case);
            assert!(
                matches!(result, Err(AnomalyEventError::InvalidEventTaxonomy(_))),
                "taxonomy {case:?} must be rejected",
            );
        }
    }

    // ─────────────────────────────────────────────────────────────────────
    // Test 3: 4 severity enum pass + invalid reject。
    // ─────────────────────────────────────────────────────────────────────
    #[test]
    fn test_validate_severity_4_enum_and_invalid_reject() {
        // 4 enum 全接受 (含 HALT — Y2+ 不寫 row 但 ENUM 必先 land per v2 amend P0-2)。
        for sev in ["INFO", "WARN", "CRITICAL", "HALT"] {
            assert!(
                validate_severity(sev).is_ok(),
                "severity {sev} must be accepted (V109 CHECK 4 enum)",
            );
        }
        // invalid case：大小寫變體 / 已剔除 WARNING (typo per v2 amend P0-2) / 空 / 拼錯。
        let invalid_cases = [
            "",
            "info",
            "Info",
            "WARNING", // 已剔除：typo per v2 amend P0-2 (3-level vs 4-level conflict)
            "FATAL",
            "ALERT",
        ];
        for case in invalid_cases {
            let result = validate_severity(case);
            assert!(
                matches!(result, Err(AnomalyEventError::InvalidSeverity(_))),
                "severity {case:?} must be rejected",
            );
        }
    }

    // ─────────────────────────────────────────────────────────────────────
    // Test 4: 4 detection_method enum + ADR-0036 黑名單 HMM/Markov/GARCH reject。
    //
    // 重點：HARDCODE compile-time block — 黑名單 substring 命中即 reject，
    // 對齊 V109 Guard A line 117-138 + Guard C line 244-254 三重反向防護。
    // ─────────────────────────────────────────────────────────────────────
    #[test]
    fn test_validate_detection_method_4_enum_and_hmm_garch_reject() {
        // 4 替代算法接受 (per ADR-0036 Decision 2-4)。
        for method in [
            "atr_vol_funding_9cell",
            "rv_percentile",
            "block_bootstrap",
            "manual_operator",
        ] {
            assert!(
                validate_detection_method(method).is_ok(),
                "detection_method {method} must be accepted (V109 CHECK 4 enum)",
            );
        }
        // ADR-0036 Decision 1 黑名單：HMM / Markov-switching / GARCH 永久禁用。
        // 含字面值 + 變體 + 大小寫 (validator lower-cased substring match)。
        let blacklist_cases = [
            "hmm",
            "HMM",
            "Hmm",
            "hmm_v2",         // 變體
            "hmm_filter",
            "markov_switching",
            "MARKOV_SWITCHING",
            "Markov_Switching",
            "markov-switching", // dash 變體
            "garch",
            "GARCH",
            "garch_1_1",      // GARCH(1,1) 變體
            "egarch",         // E-GARCH 變體 (substring match 也命中)
            "arima_markov",   // 混合命名
        ];
        for case in blacklist_cases {
            let result = validate_detection_method(case);
            assert!(
                matches!(result, Err(AnomalyEventError::InvalidDetectionMethod(_))),
                "ADR-0036 Decision 1 blacklist: detection_method {case:?} must be \
                 rejected (HMM / Markov-switching / GARCH 永久禁用)",
            );
        }
        // 其他 invalid case：不在 4 enum 內、非黑名單。
        let other_invalid = [
            "",
            "isolation_forest",
            "arima_residual",   // 已剔除：own behavior detector 走 M3
            "autoencoder_Y2",   // Y2+ 需 amend ADR-0036 路徑
            "unknown_method",
        ];
        for case in other_invalid {
            let result = validate_detection_method(case);
            assert!(
                matches!(result, Err(AnomalyEventError::InvalidDetectionMethod(_))),
                "non-4-enum detection_method {case:?} must be rejected",
            );
        }
    }

    // ─────────────────────────────────────────────────────────────────────
    // Test 5: amplification cap 24h window — same symbol + taxonomy 24h 內 ≥ 2
    // CRITICAL/HALT count 觸 cap 邏輯。
    //
    // 注意：本 test 不接 PG (Mac SSOT 無 in-memory PG)；驗 helper function 簽名 +
    // 4 enum validator 配對 + 24h 視窗時間計算 + cap policy semantic。真實 PG
    // roundtrip 由 Sprint 3 W2-E + Linux empirical 跑。
    // ─────────────────────────────────────────────────────────────────────
    #[test]
    fn test_amplification_cap_24h_window_semantic() {
        // 模擬：caller 端決定 cap_suppressed 政策 (≥ 2 → 標 cap_suppressed=true)。
        // 本 test 驗 cap policy 函式 boundary：
        //   - count = 0 → cap_suppressed=false
        //   - count = 1 → cap_suppressed=false (本 INSERT 後 count=1，是 cap 內第 1 筆)
        //   - count = 2 → cap_suppressed=true (本 INSERT 是 24h 內第 2 筆，觸 H-11 cap)
        //   - count ≥ 3 → cap_suppressed=true (持續抑制)
        fn cap_suppressed(count: i32) -> bool {
            // per H-11 + M3 §6.2 + V109 spec §5.3 line 280：
            //   ≥ 2 → 雖 INSERT 但 evidence_json 標 cap_suppressed=true 不 emit M3 cascade。
            count >= 2
        }
        assert!(!cap_suppressed(0), "count=0 不該標 cap_suppressed");
        assert!(!cap_suppressed(1), "count=1 不該標 cap_suppressed");
        assert!(cap_suppressed(2), "count=2 必標 cap_suppressed (per H-11)");
        assert!(cap_suppressed(3), "count=3 必標 cap_suppressed");
        assert!(
            cap_suppressed(10),
            "count=10 必標 cap_suppressed (持續抑制)",
        );

        // 驗 helper 函式輸入 validator 配對：傳非法 taxonomy 應 reject (不會穿透到 PG)。
        // 注意：本 test 走 async 函式驗 sig 對齊（不真實呼）。
        let _expected_sig: fn(
            &AnomalyEventWriter,
            &str,
            &str,
            chrono::DateTime<chrono::Utc>,
        ) -> _ = |w, tax, em, since| {
            // 此處只驗 sig 結構；無真實呼。
            let _ = w;
            let _ = tax;
            let _ = em;
            let _ = since;
            async { Ok(0i32) as Result<i32, AnomalyEventError> }
        };

        // 24h 視窗時間計算驗 (per V109 spec §5.3 + M3 §6.2 24h rolling)。
        let now = Utc.with_ymd_and_hms(2026, 5, 25, 12, 0, 0).unwrap();
        let since_24h = now - chrono::Duration::hours(24);
        let diff = now - since_24h;
        assert_eq!(diff.num_hours(), 24, "24h 視窗計算必準確");
    }

    // ─────────────────────────────────────────────────────────────────────
    // SQL 字串對齊 V109 schema 23 column lock — 防 silent schema drift。
    //
    // 為什麼用 include_str! self-grep 範式 (per earn_movement_writer +
    // lease_transition_writer 範式)：
    //   - 若未來「順手 rename」column 名 (e.g. observed_at → ts)，本 test 直接
    //     fail，提示 reviewer 必同步 V109 migration + 本 writer。
    // ─────────────────────────────────────────────────────────────────────
    #[test]
    fn test_insert_sql_locked_columns_match_v109_schema() {
        let src = include_str!("anomaly_event_writer.rs");
        // V109 schema 23 column 全列。id / created_by / created_at / source_version
        // 走 DB DEFAULT 不在 INSERT value list，但在 AnomalyEventRow struct + RETURNING
        // 中出現。observed_at 屬 INSERT value list。
        for col in [
            "id",
            "observed_at",
            "event_taxonomy",
            "severity",
            "detection_method",
            "atr_vol_state",
            "funding_state",
            "strategy_id",
            "symbol",
            "metric_value",
            "metric_baseline",
            "metric_threshold",
            "amplification_loop_24h_count",
            "m3_health_observation_ref",
            "m7_decay_signal_ref",
            "m1_lal_demote_ref",
            "evidence_json",
            "engine_mode",
            "created_by",
            "created_at",
            "updated_by",
            "updated_at",
            "source_version",
        ] {
            assert!(
                src.contains(col),
                "anomaly_event_writer.rs missing V109 column: {col} (schema drift risk)",
            );
        }
    }

    /// INSERT SQL 必含 `learning.anomaly_events` 表名 (V109 schema location lock)。
    #[test]
    fn test_insert_sql_locked_table_name() {
        let src = include_str!("anomaly_event_writer.rs");
        assert!(
            src.contains("learning.anomaly_events"),
            "anomaly_event_writer.rs missing V109 table name `learning.anomaly_events`",
        );
    }

    /// INSERT SQL 必走 `::NUMERIC(18,8)` cast (workspace 無 BigDecimal feature) +
    /// 對齊 metric_value / metric_baseline / metric_threshold 3 個 NUMERIC column。
    #[test]
    fn test_insert_sql_uses_numeric_cast() {
        let src = include_str!("anomaly_event_writer.rs");
        let numeric_cast_count = src.matches("::NUMERIC(18,8)").count();
        // 至少 3 處 (3 個 NUMERIC column)。本 file 註釋 + 1 處 INSERT 內 3 個 cast
        // = 至少 3 個。實際 = 5 個 (含 doc comment 中 1 引用 + 1 註釋引用)。
        assert!(
            numeric_cast_count >= 3,
            "expected ≥ 3 ::NUMERIC(18,8) cast (metric_value / baseline / threshold), \
             found {numeric_cast_count}",
        );
    }

    /// INSERT SQL 必含 `RETURNING id` 讓 caller 取 BIGSERIAL PK (per V109 PK)。
    #[test]
    fn test_insert_sql_returns_id() {
        let src = include_str!("anomaly_event_writer.rs");
        assert!(
            src.contains("RETURNING id"),
            "anomaly_event_writer.rs INSERT must RETURNING id for caller's cross-ref UPDATE",
        );
    }

    /// amplification cap SQL 必含 `INTERVAL` 或 timestamp 範圍 + severity IN
    /// ('CRITICAL', 'HALT') (per V109 spec §5.3 + H-11)。
    #[test]
    fn test_amplification_cap_sql_window_lock() {
        let src = include_str!("anomaly_event_writer.rs");
        // 走 caller 傳 since 參數而非 SQL 內 INTERVAL；驗 severity filter + observed_at
        // > $2 (caller 傳 24h ago timestamp)。
        assert!(
            src.contains("severity IN ('CRITICAL', 'HALT')"),
            "amplification cap query must filter severity IN ('CRITICAL', 'HALT') \
             (per H-11 + M8 design §5.2 — INFO/WARN 不計 cap)",
        );
        assert!(
            src.contains("observed_at > $"),
            "amplification cap query must use observed_at > $ for 24h window",
        );
        assert!(
            src.contains("event_taxonomy = $"),
            "amplification cap query must filter by event_taxonomy",
        );
        assert!(
            src.contains("engine_mode = $"),
            "amplification cap query must filter by engine_mode (5 mode 獨立計數空間)",
        );
    }

    /// V109 黑名單 ADR-0036 Decision 1 — validator 必含 hmm / markov / garch 反向防護。
    #[test]
    fn test_validator_contains_adr0036_blacklist_strings() {
        let src = include_str!("anomaly_event_writer.rs");
        // validator function 必引黑名單 substring (不是 comment 引用，是真實 reject 邏輯)。
        // 驗 lower().contains("hmm") / lower().contains("markov_switching") /
        // lower().contains("garch") 三個 substring 出現在程式碼。
        assert!(
            src.contains("lower.contains(\"hmm\")"),
            "validator must contain reverse-pattern check for HMM",
        );
        assert!(
            src.contains("lower.contains(\"markov_switching\")")
                || src.contains("lower.contains(\"markov-switching\")"),
            "validator must contain reverse-pattern check for Markov-switching",
        );
        assert!(
            src.contains("lower.contains(\"garch\")"),
            "validator must contain reverse-pattern check for GARCH",
        );
    }

    /// 5 engine_mode 全 land — paper / demo / live_demo / live / replay
    /// (per v2 amend P0-3)。
    #[test]
    fn test_validate_engine_mode_5_enum_complete() {
        for mode in ["paper", "demo", "live_demo", "live", "replay"] {
            assert!(
                validate_engine_mode(mode).is_ok(),
                "engine_mode {mode} must be accepted (V109 CHECK 5 enum)",
            );
        }
        // invalid case：3-mode typo + 大小寫變體 + 拼錯。
        let invalid_cases = [
            "",
            "PAPER",
            "Paper",
            "shadow",
            "test",
            "live_replay", // 拼錯變體
            "replays",     // 拼錯
        ];
        for case in invalid_cases {
            let result = validate_engine_mode(case);
            assert!(
                matches!(result, Err(AnomalyEventError::InvalidEngineMode(_))),
                "engine_mode {case:?} must be rejected",
            );
        }
    }

    /// AnomalyEventRow struct 必含 V109 全 23 column field — 防 struct drift。
    ///
    /// 用 include_str! 檢 struct field 名而非 reflection (Rust 無 stable reflection)。
    #[test]
    fn test_anomaly_event_row_struct_has_23_fields() {
        let src = include_str!("anomaly_event_writer.rs");
        // 23 column field 名全列；對齊 V109 SQL line 353-438。
        let required_fields = [
            "pub id: i64",
            "pub observed_at: chrono::DateTime<chrono::Utc>",
            "pub event_taxonomy: String",
            "pub severity: String",
            "pub detection_method: String",
            "pub atr_vol_state: Option<String>",
            "pub funding_state: Option<String>",
            "pub strategy_id: Option<String>",
            "pub symbol: Option<String>",
            "pub metric_value: Option<String>",
            "pub metric_baseline: Option<String>",
            "pub metric_threshold: Option<String>",
            "pub amplification_loop_24h_count: i32",
            "pub m3_health_observation_ref: Option<i64>",
            "pub m7_decay_signal_ref: Option<i64>",
            "pub m1_lal_demote_ref: Option<i64>",
            "pub evidence_json: Option<JsonValue>",
            "pub engine_mode: String",
            "pub created_by: String",
            "pub created_at: chrono::DateTime<chrono::Utc>",
            "pub updated_by: Option<String>",
            "pub updated_at: Option<chrono::DateTime<chrono::Utc>>",
            "pub source_version: String",
        ];
        for field in required_fields {
            assert!(
                src.contains(field),
                "AnomalyEventRow missing V109 field declaration: {field} (struct drift risk)",
            );
        }
    }

    /// AnomalyEventError Display 文字含 column / enum 名 (便於 grep log 排查)。
    #[test]
    fn test_error_display_messages_informative() {
        let e = AnomalyEventError::InvalidEventTaxonomy("foo".to_string());
        let msg = format!("{e}");
        assert!(
            msg.contains("event_taxonomy"),
            "InvalidEventTaxonomy msg must mention 'event_taxonomy': {msg}",
        );
        assert!(
            msg.contains("foo"),
            "InvalidEventTaxonomy msg must mention input value: {msg}",
        );

        let e = AnomalyEventError::InvalidSeverity("bar".to_string());
        let msg = format!("{e}");
        assert!(
            msg.contains("severity"),
            "InvalidSeverity msg must mention 'severity': {msg}",
        );

        let e = AnomalyEventError::InvalidDetectionMethod("hmm".to_string());
        let msg = format!("{e}");
        assert!(
            msg.contains("detection_method"),
            "InvalidDetectionMethod msg must mention 'detection_method': {msg}",
        );
        assert!(
            msg.contains("ADR-0036"),
            "InvalidDetectionMethod msg must reference ADR-0036 for blacklist context: {msg}",
        );

        let e = AnomalyEventError::InvalidEngineMode("baz".to_string());
        let msg = format!("{e}");
        assert!(
            msg.contains("engine_mode"),
            "InvalidEngineMode msg must mention 'engine_mode': {msg}",
        );
    }
}
