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
//!   Startup flow:
//!   - query registry for each (strategy × engine_mode × quantile) slot
//!   - fall back to `_current` symlink if registry row missing
//!   - fall back to None if symlink missing too (graceful degradation)
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
    /// Hash of the feature schema (feature names + dtypes) used at training
    /// time. Must match the engine's runtime `FEATURE_NAMES_V1_HASH` before
    /// the artifact is loaded — mismatch means feature dim / ordering drift
    /// which would crash `session.run` at inference. `None` for legacy rows
    /// that were registered before the column was populated — caller should
    /// treat `None` as OK (warn-log) to preserve backward compat.
    ///
    /// 訓練時使用的 feature schema（feature names + dtypes）hash。載入前
    /// 必須與 engine 運行時的 `FEATURE_NAMES_V1_HASH` 比對；mismatch 表示
    /// feature dim / 排序漂移，`session.run` 會 panic。legacy row 未填寫時
    /// `None`，caller 應視為 OK（warn-log）以保相容。
    pub feature_schema_hash: Option<String>,
}

/// Feature-schema hash mismatch between registry row and engine runtime.
/// Returned by `validate_schema_hash` when the registered artifact was
/// trained against a different feature schema than the engine is currently
/// built with. Caller should treat this as "disable this slot" — loading
/// the ONNX would likely panic on the first `session.run` call due to
/// feature dim / ordering drift.
///
/// Registry row 與 engine 運行時之間的 feature schema hash 不匹配。
/// `validate_schema_hash` 在註冊 artifact 與當前 engine 的 feature schema
/// 不同時回此錯；caller 應 disable 該 slot（直接 load ONNX 會在第一次
/// `session.run` 因 feature dim/排序漂移 panic）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SchemaHashMismatch {
    /// The hash stored in `learning.model_registry.feature_schema_hash`.
    /// 存於 `learning.model_registry.feature_schema_hash` 的值。
    pub registry: String,
    /// The hash compiled into the engine (typically `FEATURE_NAMES_V1_HASH`).
    /// 編譯進 engine 的 hash（通常為 `FEATURE_NAMES_V1_HASH`）。
    pub engine: String,
}

impl std::fmt::Display for SchemaHashMismatch {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "feature schema hash mismatch: registry={} engine={} \
             (feature dim/ordering drift — load disabled)",
            self.registry, self.engine,
        )
    }
}

impl std::error::Error for SchemaHashMismatch {}

/// Validate that a resolved artifact's `feature_schema_hash` matches the
/// engine's compiled-in feature schema. Pure function — no side effects.
///
/// Semantics:
/// * `None` on the resolved artifact → `Ok(())` + warn log. Registered
///   before the column was populated; treat as best-effort legacy OK so
///   early adopters aren't locked out at Phase 3 cut-over.
/// * Hash matches → `Ok(())`.
/// * Hash differs → `Err(SchemaHashMismatch)`. Caller should skip loading
///   this slot and fall back to the Disabled path (not panic).
///
/// Phase 3+ integration: the startup sequence / SIGHUP handler in
/// `OnnxModelManager` will call this before every `new(path, ...)` attempt
/// with the engine's `FEATURE_NAMES_V1_HASH` constant. Failure → log +
/// Disabled fallback, never panic.
///
/// 驗 resolved artifact 的 feature_schema_hash 是否匹配 engine 編譯的 schema。
/// 純函式，無副作用。語意：None → Ok + warn（legacy row 當 OK 向後相容）；
/// 相符 → Ok；不符 → Err，caller 應跳過 load 走 Disabled fallback（不 panic）。
/// Phase 3+ 整合時由 `OnnxModelManager::new(...)` 前呼，失敗 → log + Disabled。
pub fn validate_schema_hash(
    resolved: &ResolvedArtifact,
    engine_schema_hash: &str,
) -> Result<(), SchemaHashMismatch> {
    match &resolved.feature_schema_hash {
        None => {
            warn!(
                registry_id = resolved.id,
                engine_hash = %engine_schema_hash,
                "registry row has no feature_schema_hash — legacy row, treating as OK / \
                 legacy row 無 feature_schema_hash，視為 OK"
            );
            Ok(())
        }
        Some(reg_hash) if reg_hash == engine_schema_hash => Ok(()),
        Some(reg_hash) => Err(SchemaHashMismatch {
            registry: reg_hash.clone(),
            engine: engine_schema_hash.to_string(),
        }),
    }
}

/// Resolve the canonical artifact for a slot. Prefers canary_status='production'
/// then 'promoting'; orders by promoted_at DESC NULLS LAST so in-flight promote
/// wins. Returns `Ok(None)` when no matching row exists (fall back to symlink).
/// `Err` only on DB error — caller should log and treat as `None` equivalent
/// for graceful degradation (a broken registry query must never block inference).
///
/// **Phase 3+ integration contract**: before feeding the returned
/// `ResolvedArtifact.artifact_path` to `OnnxModelManager::new(...)`, the caller
/// MUST invoke `validate_schema_hash(resolved, FEATURE_NAMES_V1_HASH)` to
/// detect feature-schema drift between training time and engine runtime. A
/// mismatch means `session.run` would panic on feature dim / ordering mismatch
/// — on `Err(SchemaHashMismatch)` caller should log + route the slot through
/// the Disabled fallback path, not surface the error or retry.
///
/// 取 slot 的權威 artifact。優先 production → promoting；promoted_at DESC NULLS
/// LAST，進行中的晉升勝出。無匹配 row → Ok(None)（caller 回退 symlink）。
/// Err 僅 DB 錯誤，caller 應 log 並視為 None（優雅降級）。
/// **Phase 3+ 整合契約**：把 `artifact_path` 餵給 `OnnxModelManager::new(...)`
/// 前必須呼 `validate_schema_hash(resolved, FEATURE_NAMES_V1_HASH)` 檢 schema
/// 漂移；mismatch → `session.run` 會 panic，caller 應 log + 走 Disabled fallback。
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
    let row: Option<(
        i64,
        String,
        String,
        String,
        String,
        Option<String>,
        Option<String>,
    )> = sqlx::query_as(
        "SELECT id, artifact_path, canary_status, verdict, \
                to_char(train_date, 'YYYY-MM-DD') AS train_date, \
                artifact_sha256, feature_schema_hash \
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
        Some((
            id,
            artifact_path,
            canary_status,
            verdict,
            train_date,
            artifact_sha256,
            feature_schema_hash,
        )) => {
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
                feature_schema_hash,
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
        assert_eq!(name, "edge_predictor_demo_ma_crossover_q50_v1_current.onnx");
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
            artifact_path:
                "/tmp/openclaw/models/edge_predictor_demo_ma_crossover_q50_v1_2026-04-23.onnx"
                    .into(),
            canary_status: "production".into(),
            verdict: "should_ship".into(),
            train_date: "2026-04-23".into(),
            artifact_sha256: Some("deadbeef".into()),
            feature_schema_hash: Some("abc123".into()),
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

    // ───── L2-9: feature_schema_hash validation ─────────────────────
    // INFRA-PREBUILD-1 audit L2-9 (2026-04-23): ResolvedArtifact must carry
    // feature_schema_hash so Phase 3+ callers can detect feature-schema drift
    // between training and runtime before loading the ONNX. Missing → panic
    // in session.run at inference time.
    // L2-9 審計：ResolvedArtifact 必須帶 feature_schema_hash，Phase 3+ caller
    // 載入 ONNX 前偵測 schema 漂移；無此驗證 → runtime session.run panic。

    fn _make_resolved(feature_schema_hash: Option<String>) -> ResolvedArtifact {
        // Helper: build ResolvedArtifact with only feature_schema_hash varying.
        // 測試 helper：固定其他欄位、只變動 feature_schema_hash。
        ResolvedArtifact {
            id: 7,
            artifact_path: "/tmp/x.onnx".into(),
            canary_status: "production".into(),
            verdict: "should_ship".into(),
            train_date: "2026-04-23".into(),
            artifact_sha256: Some("sha".into()),
            feature_schema_hash,
        }
    }

    #[test]
    fn test_resolved_artifact_has_schema_hash_field() {
        // Field existence + struct literal compile — drift guard against
        // accidental field removal that would silently disable L2-9.
        // 欄位存在 + struct literal 可編譯；守意外移除欄位後 L2-9 失效。
        let a = _make_resolved(Some("hash_v1".into()));
        assert_eq!(a.feature_schema_hash.as_deref(), Some("hash_v1"));
        let b = _make_resolved(None);
        assert_eq!(b.feature_schema_hash, None);
    }

    #[test]
    fn test_validate_schema_hash_match_ok() {
        // Happy path: registry hash == engine hash → Ok(()).
        // 快樂路徑：registry hash 等於 engine hash → Ok(())。
        let resolved = _make_resolved(Some("feat_hash_v1".into()));
        assert!(validate_schema_hash(&resolved, "feat_hash_v1").is_ok());
    }

    #[test]
    fn test_validate_schema_hash_none_ok_with_warn() {
        // Legacy row (feature_schema_hash NULL pre-backfill) → Ok(()) with
        // warn log. Preserves backward compat so early rows don't lock out
        // the Phase 3+ cut-over.
        // Legacy row（feature_schema_hash NULL）→ Ok + warn；保向後相容。
        let resolved = _make_resolved(None);
        assert!(validate_schema_hash(&resolved, "feat_hash_v1").is_ok());
    }

    #[test]
    fn test_validate_schema_hash_mismatch_err() {
        // Mismatch → Err with both hashes populated for logging.
        // 不匹配 → Err，兩邊 hash 都帶回供 log。
        let resolved = _make_resolved(Some("registry_hash_old".into()));
        let result = validate_schema_hash(&resolved, "engine_hash_new");
        assert!(result.is_err());
        let err = result.unwrap_err();
        assert_eq!(err.registry, "registry_hash_old");
        assert_eq!(err.engine, "engine_hash_new");
    }

    #[test]
    fn test_schema_hash_mismatch_display() {
        // Display trait must include both hashes so log output is actionable
        // — operator needs to see which hash rolled forward / rolled back.
        // Display 必含兩邊 hash；operator log 才能診斷哪邊動了。
        let err = SchemaHashMismatch {
            registry: "abc123".into(),
            engine: "def456".into(),
        };
        let s = format!("{}", err);
        assert!(s.contains("abc123"), "display missing registry hash: {s}");
        assert!(s.contains("def456"), "display missing engine hash: {s}");
        // std::error::Error trait implementation must compile.
        // std::error::Error trait 需能編譯。
        let _: &dyn std::error::Error = &err;
    }
}
