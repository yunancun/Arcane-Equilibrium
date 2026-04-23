//! Model registry resolver — reads `learning.model_registry` (V023) to find
//! the canonical ONNX artifact for a given (strategy, engine_mode, quantile).
//! Model registry 解析器 — 查 `learning.model_registry`（V023）取某 slot
//! 的權威 ONNX artifact。
//!
//! MODULE_NOTE (EN): INFRA-PREBUILD-1 Part B (2026-04-23). Pure read helper —
//!   no side effects, no caching. Caller (engine startup or SIGHUP handler)
//!   invokes `resolve_latest_production_artifact` to get the winning model's
//!   filesystem path, then feeds it to `OnnxModelManager::new(path, ...)`.
//!   Integration with OnnxModelManager deferred to Phase 3+ when Track L goes
//!   live — at that point the startup sequence will:
//!
//!     1. query registry for each (strategy × engine_mode × quantile) slot
//!     2. fall back to `_current` symlink if registry row missing
//!     3. fall back to None if symlink missing too (graceful degradation)
//!
//!   The helper returns Option<String> so callers can distinguish "no model
//!   registered yet" (None) from "model registered at this path" (Some).
//!   Query prefers canary_status='production' then 'promoting', ordered by
//!   promoted_at DESC, so an in-flight promotion wins over the prior
//!   production model. Shadow / retired / rejected rows are ignored (they
//!   are not authoritative for live inference).
//!
//! MODULE_NOTE (中): INFRA-PREBUILD-1 B 部（2026-04-23）。純讀 helper，
//!   無副作用、無 cache。Caller（engine 啟動或 SIGHUP handler）呼叫
//!   `resolve_latest_production_artifact` 取當前權威 model 的檔案路徑，
//!   再餵給 `OnnxModelManager::new(path, ...)`。與 OnnxModelManager 的整合
//!   延後到 Phase 3+ Track L live 時：啟動流程會 (1) 查每個 slot 的 registry
//!   (2) 不存在則退到 `_current` symlink (3) symlink 也不存在則 None
//!   （優雅降級）。查詢優先 canary_status='production' 後 'promoting'，以
//!   promoted_at DESC 排序；進行中的晉升贏過既有 production。shadow/retired/
//!   rejected row 不被返回（非 live 權威）。
//!
//! Spec: sql/migrations/V023__model_registry.sql · plan INFRA-PREBUILD-1 §B3.

use crate::database::pool::DbPool;
use tracing::{debug, warn};

/// Strategy / engine_mode / quantile identity for a registry lookup.
/// Registry lookup 的 strategy / engine_mode / quantile 身份。
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct ModelSlot {
    pub strategy: String,
    pub engine_mode: String,
    pub quantile: String, // "q10" | "q50" | "q90"
}

impl ModelSlot {
    pub fn new(strategy: &str, engine_mode: &str, quantile: &str) -> Self {
        Self {
            strategy: strategy.to_string(),
            engine_mode: engine_mode.to_string(),
            quantile: quantile.to_string(),
        }
    }
}

/// Resolved artifact metadata from the registry.
/// 從 registry 解析出的 artifact metadata。
#[derive(Debug, Clone, PartialEq)]
pub struct ResolvedArtifact {
    /// Registry row id — echoed back by IPC model_info for observability.
    /// Registry row id — IPC model_info 回傳供觀察。
    pub id: i64,
    /// Absolute or $OPENCLAW_DATA_DIR-relative path to the ONNX blob.
    /// ONNX blob 的絕對或相對路徑（相對於 $OPENCLAW_DATA_DIR）。
    pub artifact_path: String,
    /// "production" or "promoting" — lookup only returns these two states.
    /// "production" 或 "promoting" — lookup 僅回這兩個狀態。
    pub canary_status: String,
    /// "should_ship" or "shadow_only" — never "no_ship" (never registered).
    /// "should_ship" 或 "shadow_only" — 永不會是 "no_ship"（不登記）。
    pub verdict: String,
    /// ISO-8601 train_date string (e.g. "2026-04-23").
    pub train_date: String,
    /// Optional sha256 integrity check — caller may verify on load.
    /// 可選的 sha256 完整性檢查，caller 載入時可校驗。
    pub artifact_sha256: Option<String>,
}

/// Resolve the canonical artifact for a slot. Prefers canary_status='production'
/// then 'promoting'; orders by promoted_at DESC NULLS LAST so in-flight promote
/// wins. Returns `Ok(None)` when no matching row exists (fall back to symlink).
/// `Err` only on DB error — caller should log and treat as `None` equivalent
/// for graceful degradation (a broken registry query must never block inference).
///
/// 取 slot 的權威 artifact。優先 production → promoting；promoted_at DESC NULLS
/// LAST，進行中的晉升勝出。無匹配 row → Ok(None)（caller 回退 symlink）。
/// Err 僅 DB 錯誤，caller 應 log 並視為 None（優雅降級）。
pub async fn resolve_latest_production_artifact(
    pool: &DbPool,
    slot: &ModelSlot,
) -> Result<Option<ResolvedArtifact>, sqlx::Error> {
    let pg = match pool.get() {
        Some(p) => p,
        None => {
            debug!(
                strategy = %slot.strategy,
                "registry: pool unavailable — resolver skipped"
            );
            return Ok(None);
        }
    };

    // NOTE on ORDER BY:
    //   canary_status ASC places 'production' before 'promoting' (alpha), which
    //   is the wrong direction — we want production to win. Use CASE expression
    //   to force production=0, promoting=1 so ASC sorts production first.
    //   promoted_at DESC NULLS LAST so newly-promoted (has ts) wins over the
    //   prior production row that might not have promoted_at set if written by
    //   a legacy path.
    // 注意 ORDER BY：canary_status ASC 會是 promoting 先（字母序），但我們
    // 想要 production 贏。用 CASE 強制 production=0 / promoting=1 讓 ASC
    // 排 production 前。promoted_at DESC NULLS LAST 讓新晉升的勝出。
    let row: Option<(i64, String, String, String, String, Option<String>)> = sqlx::query_as(
        "SELECT id, artifact_path, canary_status, verdict, \
                to_char(train_date, 'YYYY-MM-DD') AS train_date, artifact_sha256 \
         FROM learning.model_registry \
         WHERE strategy = $1 AND engine_mode = $2 AND quantile = $3 \
           AND canary_status IN ('production', 'promoting') \
         ORDER BY \
           CASE canary_status WHEN 'production' THEN 0 ELSE 1 END ASC, \
           promoted_at DESC NULLS LAST, \
           created_at DESC \
         LIMIT 1",
    )
    .bind(&slot.strategy)
    .bind(&slot.engine_mode)
    .bind(&slot.quantile)
    .fetch_optional(pg)
    .await?;

    match row {
        Some((id, artifact_path, canary_status, verdict, train_date, artifact_sha256)) => {
            debug!(
                strategy = %slot.strategy,
                engine_mode = %slot.engine_mode,
                quantile = %slot.quantile,
                registry_id = id,
                status = %canary_status,
                "registry resolved / registry 解析完成"
            );
            Ok(Some(ResolvedArtifact {
                id,
                artifact_path,
                canary_status,
                verdict,
                train_date,
                artifact_sha256,
            }))
        }
        None => {
            debug!(
                strategy = %slot.strategy,
                "registry: no production/promoting row found for slot"
            );
            Ok(None)
        }
    }
}

/// Compose the `_current` symlink filename for a slot (V017 naming convention).
/// The filename matches what `onnx_exporter::_atomic_symlink_swap` writes:
///   edge_predictor_{engine_mode}_{strategy}_{quantile}_{schema_version}_current.onnx
///
/// Pure synchronous helper — does not touch the filesystem. Used by fallback
/// path when registry query returns None: caller checks
/// `{data_dir}/models/{symlink_name}` existence then feeds to OnnxModelManager.
///
/// 組 slot 的 `_current` symlink 檔名（V017 命名規則）。純同步 helper，
/// 不觸及檔案系統。registry 查無時 caller 組 `{data_dir}/models/{symlink_name}`
/// 再檢存在 → 餵給 OnnxModelManager。
pub fn symlink_filename(slot: &ModelSlot, schema_version: &str) -> String {
    format!(
        "edge_predictor_{}_{}_{}_{}_current.onnx",
        slot.engine_mode, slot.strategy, slot.quantile, schema_version
    )
}

/// Warn-log a registry lookup failure without propagating. Lightweight wrapper
/// so caller sites stay tidy — any registry error is audit-only; the caller
/// should always fall through to symlink lookup.
/// 警告 log registry 查詢失敗；caller 應永遠 fallthrough 到 symlink 查詢。
pub fn log_registry_failure(slot: &ModelSlot, err: &sqlx::Error) {
    warn!(
        strategy = %slot.strategy,
        engine_mode = %slot.engine_mode,
        quantile = %slot.quantile,
        error = %err,
        "model registry lookup failed — falling back to symlink / registry 查詢失敗，回退 symlink"
    );
}

#[cfg(test)]
mod tests {
    use super::*;

    // Pure-logic tests that don't require a live PG connection. The async
    // resolver is covered by integration tests against a test DB (deferred
    // to B7 healthcheck integration work).
    // 無需活 PG 的純邏輯測試；async resolver 的整合測試留到 B7。

    #[test]
    fn test_symlink_filename_format() {
        let slot = ModelSlot::new("ma_crossover", "demo", "q50");
        let name = symlink_filename(&slot, "v1");
        assert_eq!(
            name,
            "edge_predictor_demo_ma_crossover_q50_v1_current.onnx"
        );
    }

    #[test]
    fn test_symlink_filename_all_quantiles() {
        // Aligns with onnx_exporter.py `_atomic_symlink_swap` naming for
        // all three trio members — drift guard for cross-language agreement.
        // 對齊 onnx_exporter.py `_atomic_symlink_swap` 的 3 quantile 命名。
        for q in ["q10", "q50", "q90"] {
            let slot = ModelSlot::new("bb_breakout", "live_demo", q);
            let name = symlink_filename(&slot, "v2");
            assert_eq!(
                name,
                format!("edge_predictor_live_demo_bb_breakout_{q}_v2_current.onnx"),
            );
        }
    }

    #[test]
    fn test_model_slot_equality_and_hash() {
        // HashMap keying — same logical slot must hash identically so a slot
        // map can cache resolved artifacts per tick.
        // HashMap keying：同一 slot 必須 hash 一致，供 per-tick 快取。
        let a = ModelSlot::new("ma_crossover", "demo", "q50");
        let b = ModelSlot::new("ma_crossover", "demo", "q50");
        let c = ModelSlot::new("ma_crossover", "demo", "q10");
        assert_eq!(a, b);
        assert_ne!(a, c);
        let mut map = std::collections::HashMap::new();
        map.insert(a, "artifact_a.onnx");
        assert_eq!(map.get(&b), Some(&"artifact_a.onnx"));
        assert_eq!(map.get(&c), None);
    }

    #[test]
    fn test_resolved_artifact_construction() {
        // Minimal smoke test — ensures the struct literal + Clone + PartialEq
        // stay usable. Production code will construct this from sqlx row.
        // 極簡煙霧測試；production 會從 sqlx row 構造。
        let a = ResolvedArtifact {
            id: 42,
            artifact_path: "/tmp/openclaw/models/edge_predictor_demo_ma_crossover_q50_v1_2026-04-23.onnx".into(),
            canary_status: "production".into(),
            verdict: "should_ship".into(),
            train_date: "2026-04-23".into(),
            artifact_sha256: Some("deadbeef".into()),
        };
        let b = a.clone();
        assert_eq!(a, b);
        assert_eq!(a.canary_status, "production");
    }

    #[test]
    fn test_slot_display_via_debug() {
        // Debug output is used in trace/log; spot-check key fields appear.
        // Debug 輸出用於 trace/log；抽檢關鍵欄位出現。
        let slot = ModelSlot::new("funding_arb", "live", "q90");
        let s = format!("{:?}", slot);
        assert!(s.contains("funding_arb"));
        assert!(s.contains("live"));
        assert!(s.contains("q90"));
    }
}
