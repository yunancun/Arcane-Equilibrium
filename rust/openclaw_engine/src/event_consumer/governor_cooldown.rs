//! Governor de-escalation cooldown PG persistence helpers (ARCH-RC1 1C-4 B1).
//! Governor 降級冷卻 PG 持久化輔助函數。
//!
//! MODULE_NOTE (EN): Extracted from event_consumer/mod.rs (FIX-08 file size).
//!   Pure decision function + async PG loader for governor de-escalation cooldown.
//! MODULE_NOTE (中): 從 event_consumer/mod.rs 提取（FIX-08 文件大小）。
//!   純決策函數 + 非同步 PG 載入器，用於 governor 降級冷卻。

use crate::tick_pipeline::TickPipeline;
use tracing::warn;

/// EN: Pure decision function — given a stored ts (from V014) and the current
///     wall clock, decide whether the cooldown is still active. Extracted as a
///     standalone fn so it is unit-testable without a PG fixture.
///     Returns Some(stored_ts) when the cooldown is still active; None when
///     the cooldown has expired or the stored ts is in the future
///     (clock-skew → ignore the row, treat as expired so we don't pin a
///     bogus future cooldown forever).
/// 中文: 純決策函數 — 給定 V014 存的 ts 與當前時間，判斷冷卻是否仍生效。
///       抽成獨立函數以便不依賴 PG fixture 做單測。冷卻仍活躍回 Some，
///       過期或時鐘倒退（stored_ts > now）回 None（避免錯誤地永久 pin 未來冷卻）。
pub(crate) fn cooldown_ts_if_active(stored_ts_ms: i64, now_ms: u64, cooldown_ms: u64) -> Option<u64> {
    if stored_ts_ms < 0 {
        return None;
    }
    let ts = stored_ts_ms as u64;
    if ts > now_ms {
        // Clock skew — V014 row claims a timestamp in the future. Refuse to
        // honour it; let cooldown start fresh and let the next legitimate
        // de-escalation overwrite the row.
        // 時鐘倒退 — V014 row 聲稱未來時間戳，拒絕沿用，讓下次合法降級覆蓋。
        return None;
    }
    let elapsed = now_ms.saturating_sub(ts);
    if elapsed < cooldown_ms {
        Some(ts)
    } else {
        None
    }
}

/// EN: Query V014 for the most recent successful operator de-escalation and
///     return its ts_ms iff the 24h cooldown is still active. Fail-soft: any
///     SQL error logs a warn and returns None — the engine still starts but
///     the cooldown begins from zero. Other guards (whitelist, step rule,
///     5-min hold, CB/MR lockout) remain active so this is defence-in-depth.
/// 中文: 查 V014 取最近一筆 operator 成功降級記錄，僅當 24h 冷卻仍活躍時返回
///       ts_ms。fail-soft：SQL 失敗記 warn 並回 None，引擎照常啟動但冷卻從零
///       開始；其他守衛（白名單/步進/5min hold/CB+MR 鎖死）持續生效，
///       這只是 defence-in-depth 層。
pub(crate) async fn load_governor_cooldown_from_audit(
    pool: &sqlx::PgPool,
    now_ms: u64,
) -> Option<u64> {
    let row: Result<Option<(i64,)>, sqlx::Error> = sqlx::query_as(
        "SELECT ts_ms FROM observability.engine_events \
         WHERE event_type = 'governor_de_escalate' \
           AND payload->>'result' = 'applied' \
         ORDER BY ts_ms DESC LIMIT 1",
    )
    .fetch_optional(pool)
    .await;
    match row {
        Ok(Some((ts,))) => cooldown_ts_if_active(
            ts,
            now_ms,
            TickPipeline::GOVERNOR_DE_ESCALATION_COOLDOWN_MS,
        ),
        Ok(None) => None,
        Err(e) => {
            warn!(error = %e, "ARCH-RC1 1C-4 B1: V014 governor cooldown query failed (fail-soft) / V014 governor 冷卻查詢失敗（fail-soft）");
            None
        }
    }
}

#[cfg(test)]
mod cooldown_tests {
    use super::cooldown_ts_if_active;

    const COOLDOWN_MS: u64 = 24 * 60 * 60 * 1000;

    #[test]
    fn fresh_cooldown_within_window_returns_some() {
        // 1h ago — well inside the 24h window.
        let now = 1_000_000_000_000u64;
        let stored = (now - 3_600_000) as i64;
        assert_eq!(cooldown_ts_if_active(stored, now, COOLDOWN_MS), Some(stored as u64));
    }

    #[test]
    fn expired_cooldown_returns_none() {
        // 25h ago — past the window.
        let now = 1_000_000_000_000u64;
        let stored = (now - 25 * 3_600_000) as i64;
        assert_eq!(cooldown_ts_if_active(stored, now, COOLDOWN_MS), None);
    }

    #[test]
    fn boundary_at_exactly_cooldown_treated_as_expired() {
        let now = 1_000_000_000_000u64;
        let stored = (now - COOLDOWN_MS) as i64;
        // elapsed == cooldown → not <, so None.
        assert_eq!(cooldown_ts_if_active(stored, now, COOLDOWN_MS), None);
    }

    #[test]
    fn future_timestamp_clock_skew_returns_none() {
        // V014 row claims a timestamp 1h in the future — refuse to honour.
        let now = 1_000_000_000_000u64;
        let stored = (now + 3_600_000) as i64;
        assert_eq!(cooldown_ts_if_active(stored, now, COOLDOWN_MS), None);
    }

    #[test]
    fn negative_stored_ts_returns_none() {
        // Defensive: V014 column is BIGINT so a corrupt row could be negative.
        let now = 1_000_000_000_000u64;
        assert_eq!(cooldown_ts_if_active(-1, now, COOLDOWN_MS), None);
    }
}
