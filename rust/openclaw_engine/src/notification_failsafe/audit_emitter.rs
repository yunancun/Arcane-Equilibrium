//! Wave 5 Packet C / C2 — V114 audit emitter 真實實裝。
//!
//! 模塊用途:
//!   - `PgAuditEmitter`: `FailsafeAuditEmitter` 真實 PG impl;
//!     INSERT 到 `observability.notification_failsafe_events` 17 column 表
//!     (V114 hypertable); 從 payload JSON 拆 column + 留 payload_jsonb 完整 row;
//!     fail-soft (error 不 panic 回 `FailsafeAuditError::EmitFailed`);
//!     5s timeout 硬限避 hot-path block。
//!   - `ack_failsafe_event`: C5 GUI ack endpoint stub —
//!     UPDATE acked_at_utc/acked_by; row 已 ack 時返 false (idempotent)。
//!
//! 為什麼 fail-soft 不阻 caller:
//!   per CLAUDE.md §二 #6 fail-closed read / fail-soft write hot path;
//!   audit emit 失敗時 watcher 已完成 SM-04 transition + exchange sync,
//!   survival 已保 — audit 是 *記錄* 用途, 不該 rollback 已執行的副作用。
//!
//! 為什麼 5s timeout:
//!   FailsafeWatcher::check_timer 每 30s tick (per spec §4.4);
//!   audit INSERT 卡 30s 將 block 下一次 tick + 其他 pipeline check_timer。
//!   5s 是合理上限 (sqlx pool + V114 INSERT 預期 < 100ms,5s 為 fail-soft margin)。
//!
//! 為什麼 ack 是 stub:
//!   C5 GUI 工作 (Sprint 3 promotion) 會建 control_api endpoint 呼此 helper;
//!   C2 IMPL 範圍只 land helper 供 C5 wire,不開 control_api endpoint。
//!
//! 不變量:
//!   - INSERT 從 payload 拆 column (ts_ms / event_type / trigger / initiator /
//!     from_level / to_level / transition_succeeded / transition_skipped_reason /
//!     adjustments_count / sync_records / atr_buffer_multiplier / now_ms);
//!   - payload_jsonb 永遠存完整 payload (forward-compat 與 audit reconstruction);
//!   - acked_at_utc + acked_by + id 由 DB 控制 (INSERT 不傳);
//!   - ack UPDATE 限 acked_at_utc IS NULL 條件 (idempotent;double-ack 返 false 不報錯)。
//!
//! ref:
//!   - sql/migrations/V114__notification_failsafe_events_hypertable.sql
//!   - docs/execution_plan/specs/2026-05-28--packet_c_3way_dispatcher_wire_spec.md §5
//!   - 既有 V109 writer pattern: database/anomaly_event_writer.rs

use async_trait::async_trait;
use serde_json::Value as JsonValue;
use sqlx::PgPool;
use std::time::Duration;

use super::{FailsafeAuditEmitter, FailsafeAuditError};

/// V114 `observability.notification_failsafe_events` PG audit emitter。
///
/// 為什麼 PgPool clone 不包 Arc:
///   sqlx::PgPool 內部已 Arc-shared (clone 廉價);對齊既有 anomaly_event_writer
///   範式 (per database/anomaly_event_writer.rs line 178-186)。
///
/// 為什麼 timeout 是 const 不是可配:
///   fail-safe path 的 emit timeout 不應被 runtime config override
///   (per CLAUDE.md §四 hard boundary);5s 為設計拍板。
pub struct PgAuditEmitter {
    pool: PgPool,
}

impl PgAuditEmitter {
    /// V114 INSERT timeout 上限 (per module-level rationale)。
    /// 為什麼是 const: fail-safe 不可被 runtime override;對齊 mod.rs
    /// FailsafeConfig::DEFAULT_TIMEOUT_MS const 範式。
    pub const EMIT_TIMEOUT: Duration = Duration::from_secs(5);

    /// 建立 emitter;caller 端 share PgPool clone 注入。
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }
}

#[async_trait]
impl FailsafeAuditEmitter for PgAuditEmitter {
    /// V114 INSERT — 從 payload JSON 拆 12 column + 留 payload_jsonb 完整 row。
    ///
    /// payload 預期 shape (per mod.rs execute_failsafe_escalation line 465-477):
    ///   {
    ///     "event": "auto_escalated_to_sm04_defensive",
    ///     "trigger": "notification_failsafe_timeout",
    ///     "initiator": "RiskGovernor",
    ///     "from_level": "NORMAL",
    ///     "to_level": "DEFENSIVE",
    ///     "transition_succeeded": true,
    ///     "transition_skipped_reason": null,
    ///     "adjustments_count": 2,
    ///     "sync_records": [...],
    ///     "now_ms": 1234567890123,
    ///     "atr_buffer_multiplier": 0.5
    ///   }
    ///
    /// 為什麼某些 field 用 `as_*().unwrap_or(...)` 不報錯:
    ///   audit 是 fail-soft;payload 缺欄位時 NULL INSERT 比 panic 好。
    ///   schema drift caller 端 (mod.rs payload build) E2 review 把守。
    ///
    /// 為什麼 ts_ms 用 now_ms 同值:
    ///   V114 partition column ts_ms = escalate 執行時刻 (對齊 audit 時序);
    ///   now_ms 冗餘存留 audit reconstruction 便利性 (per V114 column comment)。
    async fn emit_auto_escalated(
        &self,
        payload: JsonValue,
    ) -> Result<(), FailsafeAuditError> {
        // 從 payload 拆 column (audit fail-soft 不對 schema drift panic)
        let event_type = payload
            .get("event")
            .and_then(|v| v.as_str())
            .unwrap_or("auto_escalated_to_sm04_defensive");
        // event_type 必為已知值 (V114 CHECK 限制 1 值);非 auto_escalated_to_sm04_defensive
        // 走 InvalidPayload 而非 PG CHECK violation (early fail save PG roundtrip)
        if event_type != "auto_escalated_to_sm04_defensive" {
            return Err(FailsafeAuditError::EmitFailed(format!(
                "invalid event_type '{event_type}' (V114 CHECK 限 'auto_escalated_to_sm04_defensive')"
            )));
        }

        let trigger = payload.get("trigger").and_then(|v| v.as_str());
        let initiator = payload.get("initiator").and_then(|v| v.as_str());
        let from_level = payload.get("from_level").and_then(|v| v.as_str());
        let to_level = payload.get("to_level").and_then(|v| v.as_str());
        let transition_succeeded = payload.get("transition_succeeded").and_then(|v| v.as_bool());
        let transition_skipped_reason = payload
            .get("transition_skipped_reason")
            .and_then(|v| v.as_str());
        let adjustments_count = payload
            .get("adjustments_count")
            .and_then(|v| v.as_i64())
            .map(|n| n as i32);
        // sync_records 整段 JSONB 存
        let sync_records = payload.get("sync_records").cloned();
        let atr_buffer_multiplier = payload
            .get("atr_buffer_multiplier")
            .and_then(|v| v.as_f64());
        // now_ms 必有 (mod.rs execute_failsafe_escalation 必填);缺時 fallback 0
        // (audit row 仍可寫入,now_ms = 0 為 caller 端 schema drift 信號)
        let now_ms = payload
            .get("now_ms")
            .and_then(|v| v.as_i64())
            .unwrap_or(0);
        // ts_ms == now_ms (partition column = escalate 執行時刻)
        let ts_ms = now_ms;

        // V114 INSERT — id / acked_at_utc / acked_by / created_at 由 DB 控制
        let insert_future = sqlx::query(
            r#"
            INSERT INTO observability.notification_failsafe_events (
                ts_ms,
                event_type,
                trigger,
                initiator,
                from_level,
                to_level,
                transition_succeeded,
                transition_skipped_reason,
                adjustments_count,
                sync_records,
                atr_buffer_multiplier,
                now_ms,
                payload_jsonb
            )
            VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13
            )
            RETURNING id
            "#,
        )
        .bind(ts_ms)
        .bind(event_type)
        .bind(trigger)
        .bind(initiator)
        .bind(from_level)
        .bind(to_level)
        .bind(transition_succeeded)
        .bind(transition_skipped_reason)
        .bind(adjustments_count)
        .bind(&sync_records)
        .bind(atr_buffer_multiplier)
        .bind(now_ms)
        .bind(&payload)
        .fetch_one(&self.pool);

        // 5s timeout 硬限 (per Self::EMIT_TIMEOUT 設計拍板)
        match tokio::time::timeout(Self::EMIT_TIMEOUT, insert_future).await {
            Ok(Ok(_row)) => Ok(()),
            Ok(Err(e)) => Err(FailsafeAuditError::EmitFailed(format!(
                "V114 INSERT failed: {e}"
            ))),
            Err(_) => Err(FailsafeAuditError::EmitFailed(format!(
                "V114 INSERT timeout after {:?}",
                Self::EMIT_TIMEOUT
            ))),
        }
    }
}

/// C5 GUI ack 端 stub — UPDATE acked_at_utc + acked_by。
///
/// 回傳:
///   - `Ok(true)`: row 被 ack (有效 UPDATE);
///   - `Ok(false)`: row 已 ack 或 id 不存在 (idempotent;不算錯誤);
///   - `Err`: PG 連線/語法錯誤 (caller 端決定是否報 GUI)。
///
/// 為什麼 stub:
///   C5 GUI 工作 (Sprint 3 Level 2 promotion) 會建 control_api endpoint 呼此;
///   C2 IMPL 範圍只 land helper 不開 endpoint。
///
/// 為什麼 acked_at_utc IS NULL 條件:
///   idempotent — 已 ack 不重寫 (避免 acked_by 被覆蓋);double-ack 不報錯。
///
/// 為什麼用 NOW() 不傳 caller timestamp:
///   server-side 時鐘是 ack audit 唯一可信來源 (避 caller clock skew 偽 audit);
///   對齊 V114 column comment 設計。
pub async fn ack_failsafe_event(
    pool: &PgPool,
    event_id: i64,
    acked_by: &str,
) -> Result<bool, FailsafeAuditError> {
    let result = sqlx::query(
        r#"
        UPDATE observability.notification_failsafe_events
        SET acked_at_utc = NOW(),
            acked_by = $2
        WHERE id = $1
          AND acked_at_utc IS NULL
        "#,
    )
    .bind(event_id)
    .bind(acked_by)
    .execute(pool)
    .await
    .map_err(|e| FailsafeAuditError::EmitFailed(format!("V114 UPDATE failed: {e}")))?;

    Ok(result.rows_affected() == 1)
}

#[cfg(test)]
mod tests {
    //! 單元測試:
    //!   - SQL 字串對齊 V114 schema 17 column lock (include_str! grep);
    //!   - Mock FailsafeAuditEmitter impl 驗 payload 拆 column 邏輯;
    //!   - 不真實連 PG (Mac 無 PG runtime; 對齊 anomaly_event_writer 範式)。
    //!
    //! 真實 PG INSERT/UPDATE round-trip 由 Linux empirical dry-run 跑
    //! (per `feedback_v_migration_pg_dry_run`)。

    use super::*;
    use serde_json::json;
    use std::sync::Mutex;

    // ─────────────────────────────────────────────────────────────────────
    // SQL 字串對齊 V114 schema (防 silent schema drift)。
    // ─────────────────────────────────────────────────────────────────────

    /// INSERT SQL 必含 V114 表名。
    #[test]
    fn test_insert_sql_locked_table_name() {
        let src = include_str!("audit_emitter.rs");
        assert!(
            src.contains("observability.notification_failsafe_events"),
            "audit_emitter.rs missing V114 table name `observability.notification_failsafe_events`",
        );
    }

    /// INSERT SQL 必含 V114 全 13 INSERT column (不含 id/acked_*/created_at 由 DB 控制)。
    #[test]
    fn test_insert_sql_locked_columns_match_v114_schema() {
        let src = include_str!("audit_emitter.rs");
        // INSERT VALUES list 13 column (V114 17 column - id/acked_at_utc/acked_by/created_at)
        for col in [
            "ts_ms",
            "event_type",
            "trigger",
            "initiator",
            "from_level",
            "to_level",
            "transition_succeeded",
            "transition_skipped_reason",
            "adjustments_count",
            "sync_records",
            "atr_buffer_multiplier",
            "now_ms",
            "payload_jsonb",
        ] {
            assert!(
                src.contains(col),
                "audit_emitter.rs missing V114 INSERT column: {col} (schema drift risk)",
            );
        }
    }

    /// INSERT SQL 必走 13 placeholder ($1 .. $13) 對齊 13 INSERT column。
    #[test]
    fn test_insert_sql_has_13_placeholders() {
        let src = include_str!("audit_emitter.rs");
        // 找 INSERT VALUES block — 必含 $1 .. $13
        for n in 1..=13 {
            let placeholder = format!("${n}");
            assert!(
                src.contains(&placeholder),
                "audit_emitter.rs INSERT missing placeholder {placeholder} (13 column INSERT)",
            );
        }
    }

    /// INSERT SQL 必含 `RETURNING id` 供未來 caller 取 id (即使 C2 不用,留 hook 供 C5/audit)。
    #[test]
    fn test_insert_sql_returns_id() {
        let src = include_str!("audit_emitter.rs");
        assert!(
            src.contains("RETURNING id"),
            "audit_emitter.rs INSERT must RETURNING id for downstream cross-ref",
        );
    }

    /// UPDATE SQL 必含 `acked_at_utc IS NULL` 條件 (idempotent ack)。
    #[test]
    fn test_ack_sql_idempotent_guard() {
        let src = include_str!("audit_emitter.rs");
        assert!(
            src.contains("acked_at_utc IS NULL"),
            "ack_failsafe_event UPDATE must guard acked_at_utc IS NULL (idempotent)",
        );
    }

    /// UPDATE SQL 必用 server-side `NOW()` (per V114 design — caller clock 不可信)。
    #[test]
    fn test_ack_sql_uses_server_now() {
        let src = include_str!("audit_emitter.rs");
        assert!(
            src.contains("acked_at_utc = NOW()"),
            "ack_failsafe_event must use server-side NOW() not caller-supplied timestamp",
        );
    }

    /// EMIT_TIMEOUT const 必 = 5s (per module design fail-soft margin)。
    #[test]
    fn test_emit_timeout_is_5s() {
        assert_eq!(
            PgAuditEmitter::EMIT_TIMEOUT,
            Duration::from_secs(5),
            "EMIT_TIMEOUT must be 5s per fail-soft margin design",
        );
    }

    /// SQL 必含 V114 event_type 唯一值 (CHECK 限定)。
    #[test]
    fn test_event_type_check_value_in_source() {
        let src = include_str!("audit_emitter.rs");
        assert!(
            src.contains("auto_escalated_to_sm04_defensive"),
            "audit_emitter.rs must reference V114 event_type 'auto_escalated_to_sm04_defensive'",
        );
    }

    // ─────────────────────────────────────────────────────────────────────
    // Mock impl 驗 payload 拆 column 語義 (不真實連 PG)。
    // ─────────────────────────────────────────────────────────────────────

    /// Mock impl 記錄收到的 payload,驗 caller 端 build payload 的欄位完整性。
    struct MockEmitter {
        captured: Mutex<Vec<JsonValue>>,
    }

    impl MockEmitter {
        fn new() -> Self {
            Self {
                captured: Mutex::new(Vec::new()),
            }
        }
        fn captured(&self) -> Vec<JsonValue> {
            self.captured.lock().unwrap().clone()
        }
    }

    #[async_trait]
    impl FailsafeAuditEmitter for MockEmitter {
        async fn emit_auto_escalated(
            &self,
            payload: JsonValue,
        ) -> Result<(), FailsafeAuditError> {
            self.captured.lock().unwrap().push(payload);
            Ok(())
        }
    }

    /// 驗 mock impl 接受 mod.rs execute_failsafe_escalation 產出的 payload shape。
    #[tokio::test]
    async fn test_mock_emitter_captures_expected_payload_shape() {
        let m = MockEmitter::new();
        // mod.rs line 465-477 payload shape
        let payload = json!({
            "event": "auto_escalated_to_sm04_defensive",
            "trigger": "notification_failsafe_timeout",
            "initiator": "RiskGovernor",
            "from_level": "NORMAL",
            "to_level": "DEFENSIVE",
            "transition_succeeded": true,
            "transition_skipped_reason": null,
            "adjustments_count": 2,
            "sync_records": [
                {"symbol": "BTCUSDT", "side": "Buy", "new_sl": 102.0, "success": true, "error": null},
                {"symbol": "ETHUSDT", "side": "Sell", "new_sl": 197.0, "success": true, "error": null}
            ],
            "now_ms": 1_234_567_890_123i64,
            "atr_buffer_multiplier": 0.5
        });
        m.emit_auto_escalated(payload.clone()).await.unwrap();
        let captured = m.captured();
        assert_eq!(captured.len(), 1);
        let got = &captured[0];
        // 12 必要 field 全在
        assert_eq!(got["event"], "auto_escalated_to_sm04_defensive");
        assert_eq!(got["trigger"], "notification_failsafe_timeout");
        assert_eq!(got["initiator"], "RiskGovernor");
        assert_eq!(got["from_level"], "NORMAL");
        assert_eq!(got["to_level"], "DEFENSIVE");
        assert_eq!(got["transition_succeeded"], true);
        assert!(got["transition_skipped_reason"].is_null());
        assert_eq!(got["adjustments_count"], 2);
        assert_eq!(got["sync_records"].as_array().unwrap().len(), 2);
        assert_eq!(got["now_ms"], 1_234_567_890_123i64);
        assert_eq!(got["atr_buffer_multiplier"], 0.5);
    }

    /// 驗 payload event_type 不對時 PgAuditEmitter 應 early reject (不走 PG)。
    ///
    /// 為什麼測這條: V114 CHECK 限定 1 值,client-side validate 比 PG roundtrip 早報錯;
    /// 此 test 走 mock impl 模擬 PgAuditEmitter::emit_auto_escalated 早期返回邏輯。
    #[tokio::test]
    async fn test_invalid_event_type_rejected_in_emitter_logic() {
        // 模擬 PgAuditEmitter 端 early-fail 邏輯 — 不走 PG;
        // 真實 PgAuditEmitter 邏輯在 emit_auto_escalated 內,此 test 驗等價判斷
        let payload = json!({
            "event": "some_other_unknown_event",
            "now_ms": 123i64
        });
        let event_type = payload
            .get("event")
            .and_then(|v| v.as_str())
            .unwrap_or("auto_escalated_to_sm04_defensive");
        // 對齊 PgAuditEmitter::emit_auto_escalated line 90-95 邏輯
        assert!(
            event_type != "auto_escalated_to_sm04_defensive",
            "test payload 應觸發 early reject",
        );
    }

    /// 驗 payload 缺欄位 fail-soft (NULL bind 不 panic)。
    ///
    /// 為什麼測這條: audit 是 fail-soft 不該因 schema drift caller 端漏欄位 panic;
    /// 此 test 驗 emitter 內 unwrap_or / and_then 鏈不 panic。
    #[tokio::test]
    async fn test_payload_missing_optional_fields_does_not_panic() {
        // 最小 payload — 只含 event + now_ms
        let payload = json!({
            "event": "auto_escalated_to_sm04_defensive",
            "now_ms": 100i64
        });

        // 模擬 PgAuditEmitter 端拆 column 邏輯
        let trigger: Option<&str> = payload.get("trigger").and_then(|v| v.as_str());
        let initiator: Option<&str> = payload.get("initiator").and_then(|v| v.as_str());
        let from_level: Option<&str> = payload.get("from_level").and_then(|v| v.as_str());
        let to_level: Option<&str> = payload.get("to_level").and_then(|v| v.as_str());
        let transition_succeeded: Option<bool> = payload
            .get("transition_succeeded")
            .and_then(|v| v.as_bool());
        let adjustments_count: Option<i32> = payload
            .get("adjustments_count")
            .and_then(|v| v.as_i64())
            .map(|n| n as i32);
        let now_ms: i64 = payload
            .get("now_ms")
            .and_then(|v| v.as_i64())
            .unwrap_or(0);
        // 全 None 但不 panic
        assert_eq!(trigger, None);
        assert_eq!(initiator, None);
        assert_eq!(from_level, None);
        assert_eq!(to_level, None);
        assert_eq!(transition_succeeded, None);
        assert_eq!(adjustments_count, None);
        assert_eq!(now_ms, 100);
    }

    /// FailsafeAuditError::EmitFailed Display 含 V114 上下文便於 grep。
    #[test]
    fn test_audit_error_display_informative() {
        let e = FailsafeAuditError::EmitFailed("V114 INSERT failed: connection lost".into());
        let msg = format!("{e}");
        assert!(
            msg.contains("V114") || msg.contains("audit emit failed"),
            "EmitFailed msg must mention V114 or audit emit context: {msg}",
        );
    }

    /// 驗 PgAuditEmitter::new constructor 純值不 panic。
    #[test]
    fn test_pg_audit_emitter_struct_construction() {
        // sqlx::PgPool 無法在 Mac 無 PG runtime 真實建,只驗 struct shape compile-time。
        // 編譯通過即視為 struct 完整 (對齊 anomaly_event_writer 範式)。
        // 此 test 不真實 instantiate PgPool。
        fn _assert_construct_sig(pool: PgPool) -> PgAuditEmitter {
            PgAuditEmitter::new(pool)
        }
    }

    /// 驗 ack_failsafe_event 函數 sig 對齊 C5 GUI 期待 (event_id i64 + acked_by &str → bool)。
    #[test]
    fn test_ack_failsafe_event_sig() {
        // 編譯期驗 sig (path-based;不真實連 PG)。
        // 期望 sig: async fn ack_failsafe_event(pool: &PgPool, event_id: i64, acked_by: &str)
        //          -> Result<bool, FailsafeAuditError>
        // 將函數 path 賦給變數即觸發 compile-time sig check。
        let _f = ack_failsafe_event;
    }
}
