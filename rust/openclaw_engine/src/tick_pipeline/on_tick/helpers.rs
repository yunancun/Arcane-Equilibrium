//! DUAL-TRACK-EXIT-1 Track P T4 audit-side wrapper helpers + end-to-end test.
//! DUAL-TRACK-EXIT-1 Track P T4 審計層包裝 helpers 與端到端測試。
//!
//! Extracted as `pub(crate)` free functions (+ `#[cfg(test)]` module) so the
//! prefix alignment can be unit-tested directly without spinning up the whole
//! tick pipeline. The wrapper is pure audit / info-log side; business close
//! path is unchanged. Split out of the monolithic `on_tick.rs` during
//! ON-TICK-SPLIT-1 (2026-04-21) to honour §七 1200-line hard cap; callers
//! reach these via the `pub use` re-export in the parent `mod.rs` so the
//! external surface is bit-identical.
//!
//! 抽為 `pub(crate)` 自由函式（+ `#[cfg(test)]` 模組）以便 prefix 對齊可直接
//! 單測，無需啟動整個 tick pipeline。包裝純屬審計 / info log 層，業務平倉
//! 路徑不變。ON-TICK-SPLIT-1（2026-04-21）從原單檔 `on_tick.rs` 抽出以遵守
//! §七 1200 行硬上限；外部透過父模組 `mod.rs` 的 `pub use` 訪問，行為 bit-
//! identical。

use tracing::info;

/// RUST-DOUBLE-PREFIX-1 (2026-04-23): build the outbound `risk_close:*` close
/// tag from a `RiskAction::ClosePosition(reason)` payload, normalising exactly
/// **one** `risk_close:` prefix regardless of whether the caller (risk_checks /
/// position_risk_evaluator) emitted the reason bare or pre-prefixed.
///
/// Historical context: `risk_checks.rs:247` wraps PHYS-LOCK reasons as
/// `"risk_close:{reason}"` so downstream `strip_phys_lock_prefix` can recognise
/// them; other reasons (HARD STOP / TRAILING / TIME / TP / DRAWDOWN) stay bare.
/// Previously the `step_6` emission site unconditionally re-wrapped again,
/// producing `"risk_close:risk_close:phys_lock_gate4_giveback"` (double
/// prefix) in `trading.fills.strategy_name`. This helper is the single point
/// of truth for how the outbound tag is constructed — use it at every close
/// emission.
///
/// RUST-DOUBLE-PREFIX-1（2026-04-23）：從 `RiskAction::ClosePosition(reason)`
/// 建立單一 `risk_close:` 前綴的出口 close tag，不論 reason 已含前綴（PHYS-LOCK
/// 路徑：risk_checks.rs:247 已 wrap）或裸字串（HARD STOP / TRAILING 等），
/// 對外只會有一層前綴。此 helper 為所有平倉 emit 點的唯一構造規則。
pub(crate) fn build_risk_close_tag(reason: &str) -> String {
    const PREFIX: &str = "risk_close:";
    if reason.starts_with(PREFIX) {
        reason.to_string()
    } else {
        format!("{PREFIX}{reason}")
    }
}

/// EXIT-FEATURES-WRITER-BUG-1-FIX (2026-04-26): identify a close_tag whose
/// underlying close action is a partial reduce (NOT a full position exit).
/// Returns `true` for close_tags emitted by paths that call
/// `paper_state.reduce_position` instead of removing the position outright.
///
/// Currently the sole partial-reduce path is fast-track ReduceToHalf
/// (`risk_close:fast_track_reduce_half`). PHYS-LOCK / hard stop / trailing
/// stop / time stop / take profit / drawdown / daily loss / consecutive loss
/// / strategy exits all call `close_position*` (full close → position
/// removed). When the taxonomy expands (e.g. ladder partial close), add
/// the new tag here to keep the EF writer 1:1 invariant intact.
///
/// Why this exists: `learning.exit_features` is designed as a **post-close**
/// label for ML training on round-trip outcomes. Writing an EF row when the
/// position remains open (partial reduce) pollutes the training set with
/// labels whose `realized_net_bps` reflects only the closed portion's PnL,
/// not the full round-trip. MIT audit
/// `2026-04-26--exit_features_writer_bug_audit.md` §4 RCA-B verified this
/// produced 37 noise rows in the STRKUSDT dust spiral (close_fills 1:1
/// invariant violated by Δ37 in the 24h healthcheck window).
///
/// EXIT-FEATURES-WRITER-BUG-1-FIX（2026-04-26）：辨識 close_tag 是否為 partial
/// reduce（部分減倉、倉位仍 open），用以決定是否寫 EF row。EF 設計為「post-close
/// 標籤」（ML training 用），partial reduce 寫入污染 training set；MIT audit
/// §4 RCA-B 驗證 STRKUSDT dust spiral 37 條 noise label。當前唯一 partial reduce
/// 路徑為 fast_track ReduceToHalf；新增 partial 路徑（如 ladder partial close）
/// 須同步擴此 helper 以維持 close_fills 1:1 不變量。
pub(crate) fn is_partial_reduce_tag(close_tag: &str) -> bool {
    // 只認確切 tag — 避免誤判 PHYS-LOCK / strategy exit 等 full-close 路徑。
    // Match exact tag — avoid false positives on PHYS-LOCK / strategy exits.
    close_tag == "risk_close:fast_track_reduce_half"
}

/// T3 (`physical_micro_profit_lock`) 產生 `PhysicalDecision::Lock("phys_lock_xxx")`，
/// `risk_checks.rs:242` 再用 `format!("risk_close:{}", reason)` 包成
/// `RiskAction::ClosePosition("risk_close:phys_lock_xxx")`。此 helper 檢查
/// `risk_close:phys_lock_` 前綴並回傳裸 tag（`"phys_lock_xxx"`）；不匹配回 None。
///
/// T3 produces `Lock("phys_lock_xxx")`; risk_checks.rs:242 wraps as
/// `ClosePosition("risk_close:phys_lock_xxx")`. This helper checks the
/// `risk_close:phys_lock_` prefix and returns the stripped tag; returns None
/// if the reason is not a PHYS-LOCK (HARD STOP / TAKE PROFIT / TRAILING / TIME
/// STOP / DRAWDOWN / CONSECUTIVE LOSS / DAILY LOSS bypass the combine layer).
pub(crate) fn strip_phys_lock_prefix(reason: &str) -> Option<&str> {
    // 前綴必須完整（`risk_close:phys_lock_`），後綴至少 1 char（gateN_*）。
    // Prefix must be exact; suffix (gateN_*) must be non-empty.
    reason
        .strip_prefix("risk_close:phys_lock_")
        .and_then(|suf| {
            if suf.is_empty() {
                None
            } else {
                // 取完整的 `phys_lock_<suf>` 裸 tag — combine_layer 與下游
                // parse_exit_tag 依賴 `phys_lock_` 開頭的穩定形式。
                // Return the full `phys_lock_<suf>` stripped tag — combine_layer
                // and downstream parse_exit_tag depend on the `phys_lock_` prefix.
                Some(&reason["risk_close:".len()..])
            }
        })
}

/// 以剝離過的 lock_tag 走一次 combine_layer、確認 invariant 並記 info log。
/// 不改變下游平倉行為（純審計側）。
///
/// **EDGE-DIAG-1（2026-04-23）參數擴充**：新增 `owner_strategy` 與 `est_net_bps`
/// 兩個診斷欄位，讓每次 PHYS-LOCK fire 的 INFO log 自帶「Gate 1 是經 cell 還是
/// 經 fallback 路徑通過」的證據。Caller 在 lock 觸發時應重查 paper_state 與
/// edge_estimates 以取得 fire 時點的 owner_strategy / cell shrunk_bps（pre-close
/// snapshot 仍存在於 paper_state，因為 close 動作排在 log 之後）。
///
/// `est_net_bps = None` → fallback path 觸發（v2 ExitConfig.missing_edge_fallback_bps）；
/// `Some(v)` → cell hit，`v` 為 shrunk_bps。
///
/// Run the stripped lock_tag through combine_layer, enforce the invariant and
/// emit an info log. Does not alter downstream close behaviour (pure audit).
///
/// **EDGE-DIAG-1 (2026-04-23) signature extension**: `owner_strategy` and
/// `est_net_bps` are appended so every PHYS-LOCK fire log records *why* it
/// cleared Gate 1 — via cell hit or via fallback. Caller re-queries paper_state
/// and edge_estimates at fire time (pre-close snapshot is still live).
///
/// `est_net_bps = None` → fallback path triggered;
/// `Some(v)` → cell hit, `v` is shrunk_bps.
pub(crate) fn log_phys_lock_through_combine_layer(
    symbol: &str,
    reason: &str,
    lock_tag: &str,
    owner_strategy: &str,
    est_net_bps: Option<f32>,
) {
    let physical = crate::exit_features::PhysicalDecision::Lock(lock_tag.to_string());
    let combine_cfg = crate::combine_layer::CombineConfig::default();
    let (signal, source) = crate::combine_layer::combine_exit_decision(
        physical,
        None, // Phase 1a: P-only (ml_opt forced None at call-site)
        &combine_cfg,
    );
    // T4-FIX：promoted from debug_assert_eq! so the invariant is enforced in
    // release builds too — if combine_layer ever breaks this, we want a loud
    // runtime panic not silent drift.
    // T4-FIX：從 debug_assert_eq! 升為 assert_eq!，release build 也保留 runtime
    // 防線；若 combine_layer 破壞此不變式，寧要顯式 panic 也不要靜默漂移。
    assert_eq!(
        signal,
        crate::combine_layer::ExitSignal::Lock,
        "invariant: PHYS-LOCK physical decision must yield ExitSignal::Lock"
    );
    let edge_source = if est_net_bps.is_some() {
        "cell"
    } else {
        "fallback"
    };
    info!(
        symbol = %symbol,
        owner_strategy = %owner_strategy,
        est_net_bps = ?est_net_bps,
        edge_source = %edge_source,
        exit_source = %source.as_tag(),
        reason = %reason,
        lock_tag = %lock_tag,
        "combine layer: PHYS-LOCK → Lock / Combine 層：PHYS-LOCK → Lock"
    );
}

/// INFRA-PREBUILD-1 L1-1 (2026-04-23) — caller-side cell-age proxy.
///
/// Computes `age_secs = now - mtime(edge_estimates*.json)` as a conservative
/// proxy for per-cell freshness. The Python writer (`james_stein_estimator`)
/// atomically rewrites the whole file once per cycle (~hourly), so the whole-
/// file mtime is a valid lower bound on each cell's staleness. Used by
/// `step_6_risk_checks.rs` to feed `emit_shadow_exit_observation` with real
/// freshness so Phase 2's `max_model_age_secs=7d` stale gate can actually
/// fire (was `None` in Part A, making every shadow eternally fresh).
///
/// Pure fn — no tracing, no panic, no I/O beyond a single `fs::metadata` call.
/// Returns `None` when:
/// - the file does not exist (cold-start before first Python cycle),
/// - `fs::metadata` fails (permission / FS error),
/// - the system clock reports a time earlier than the file mtime
///   (clock skew; we clamp to None so callers don't feed negative ages).
///
/// `engine_mode` switches between `edge_estimates.json` (demo/live, shared
/// production file) and `edge_estimates_paper.json` (paper isolation, see
/// `edge_estimates::load_for_mode`). `base_dir` is normally
/// `OPENCLAW_BASE_DIR` but accepted as an injected param so tests can point
/// at a temp dir without touching env.
///
/// INFRA-PREBUILD-1 L1-1（2026-04-23）— caller 側 cell 齡期 proxy。
///
/// 以 `now - mtime(edge_estimates*.json)` 作為 per-cell freshness 的保守
/// proxy（Python writer 每小時原子重寫整檔，整檔 mtime 是每個 cell 齡期的
/// 下界）。由 `step_6_risk_checks.rs` 呼叫，餵給 `emit_shadow_exit_observation`
/// 真實齡期，使 Phase 2 的 `max_model_age_secs=7d` stale gate 能真正 fire。
///
/// 純函式 — 僅一次 `fs::metadata` I/O，無 tracing / panic。以下回 `None`：
/// 檔案不存在（冷啟動）、metadata 失敗、系統時鐘早於檔案 mtime（clock skew）。
///
/// `engine_mode` 切換 paper/demo/live 檔名；`base_dir` 通常為
/// `OPENCLAW_BASE_DIR`，以 param 注入方便單測用 tempdir 不動 env。
pub(crate) fn compute_edge_estimates_file_age_secs(
    engine_mode: &str,
    base_dir: &std::path::Path,
) -> Option<u64> {
    let filename = match engine_mode {
        "paper" => "edge_estimates_paper.json",
        _ => "edge_estimates.json", // demo + live share production file
    };
    let path = base_dir.join("settings").join(filename);

    let metadata = std::fs::metadata(&path).ok()?;
    let mtime = metadata.modified().ok()?;
    let now = std::time::SystemTime::now();

    // duration_since returns Err if `now` < `mtime` (clock skew). Return None
    // so callers don't feed negative ages to the downstream guard.
    // 時鐘早於 mtime 時回 None，避免下游餵負值。
    let elapsed = now.duration_since(mtime).ok()?;
    Some(elapsed.as_secs())
}

/// INFRA-PREBUILD-1 Part A (2026-04-23) — Combine Layer shadow-mode emit.
///
/// Fired alongside `log_phys_lock_through_combine_layer` when
/// `ExitConfig.shadow_enabled=true`. Builds a mock `MLInference` from the
/// edge_estimates cell, runs `combine_exit_decision` with it, and emits one
/// `ShadowExitMsg` to the shadow-exit writer so `learning.decision_shadow_exits`
/// captures what Combine Layer would have output if a real ML model were
/// available. **Pure audit** — does not alter the downstream close path.
///
/// The `disagreed` field is populated by comparing:
/// - `physical_only` = `combine_exit_decision(physical, None, cfg)` — pure Track P
/// - `shadow_combined` = `combine_exit_decision(physical, Some(mock_ml), cfg)`
/// When the signal differs (or source differs on Hybrid/ML), `disagreed=true`.
/// Phase 1a invariant: `ml_override_high=2.0` sentinel prevents ML from
/// escalating Hold→Lock, so disagreement is only possible via Hybrid on Lock
/// (Physical→Hybrid source change with identical signal=Lock).
///
/// # Fail-soft semantics
/// - `tx` is `&Sender`, not `Option`: caller already checked `shadow_enabled`
///   and `tx.is_some()` before calling. Channel full → silent drop (`try_send`).
///
/// INFRA-PREBUILD-1 A 部（2026-04-23）— Combine Layer shadow 模式發射。
/// 與 `log_phys_lock_through_combine_layer` 並行觸發（當 ExitConfig.shadow_enabled=true）。
/// 從 edge_estimates cell 建 mock MLInference，走 combine_exit_decision，
/// 發一條 ShadowExitMsg 到 writer，寫入 `learning.decision_shadow_exits`。
/// 純審計 — 不改變下游平倉路徑。
#[allow(clippy::too_many_arguments)]
pub(crate) fn emit_shadow_exit_observation(
    context_id: &str,
    ts_ms: i64,
    engine_mode: &str,
    strategy_name: &str,
    symbol: &str,
    side: i16,
    lock_tag: &str,
    est_net_bps: Option<f32>,
    cell_age_secs: Option<u64>,
    tx: &tokio::sync::mpsc::Sender<crate::database::ShadowExitMsg>,
) {
    let physical = crate::exit_features::PhysicalDecision::Lock(lock_tag.to_string());
    let combine_cfg = crate::combine_layer::CombineConfig::default();

    // Build mock MLInference from edge_estimates (score = clamp((shrunk+10)/20))
    // None shrunk_bps → None MLInference → Combine falls back to Physical path
    // (disagreed=false). See combine_layer::build_ml_inference_shadow docstring.
    // 用 edge_estimates 建 mock MLInference（score = clamp((shrunk+10)/20)）；
    // 無 shrunk_bps → MLInference=None → Combine 走 Physical 路徑（disagreed=false）。
    let mock_ml = crate::combine_layer::build_ml_inference_shadow(
        est_net_bps.map(|v| v as f64),
        cell_age_secs,
    );

    // Run Combine twice: once P-only, once with mock ML. Compare for disagreement.
    // Combine 兩次：一次純 Physical，一次帶 mock ML。比對是否分歧。
    let (phys_only_signal, phys_only_source) =
        crate::combine_layer::combine_exit_decision(physical.clone(), None, &combine_cfg);
    let (shadow_signal, shadow_source) =
        crate::combine_layer::combine_exit_decision(physical, mock_ml.clone(), &combine_cfg);

    let disagreed =
        phys_only_signal != shadow_signal || phys_only_source.as_tag() != shadow_source.as_tag();
    let disagreement_reason = if disagreed {
        Some(format!(
            "phys_only={}:{} shadow={}:{}",
            match phys_only_signal {
                crate::combine_layer::ExitSignal::Lock => "Lock",
                crate::combine_layer::ExitSignal::Hold => "Hold",
            },
            phys_only_source.as_tag(),
            match shadow_signal {
                crate::combine_layer::ExitSignal::Lock => "Lock",
                crate::combine_layer::ExitSignal::Hold => "Hold",
            },
            shadow_source.as_tag(),
        ))
    } else {
        None
    };

    let msg = crate::database::ShadowExitMsg {
        context_id: context_id.to_string(),
        ts_ms,
        engine_mode: engine_mode.to_string(),
        strategy_name: strategy_name.to_string(),
        symbol: symbol.to_string(),
        side,
        physical_action: "Lock".to_string(), // PHYS-LOCK path → always Lock
        physical_reason: Some(lock_tag.to_string()),
        ml_model_id: mock_ml.as_ref().map(|m| m.id.clone()),
        ml_score: mock_ml.as_ref().map(|m| m.score as f64),
        ml_age_secs: mock_ml.as_ref().map(|m| m.age_secs as i64),
        ml_confidence: mock_ml.as_ref().map(|m| m.confidence as f64),
        exit_source: shadow_source.as_tag().to_string(),
        disagreed,
        disagreement_reason,
        ml_confirm_threshold: Some(combine_cfg.ml_confirm_threshold as f64),
        ml_override_high: Some(combine_cfg.ml_override_high as f64),
        ml_veto_low: Some(combine_cfg.ml_veto_low as f64),
    };

    // try_send: channel full → silent drop (fail-soft). Shadow is pure audit —
    // losing a row is strictly preferable to backpressuring the tick pipeline.
    // try_send：通道滿 → 靜默丟棄（fail-soft）。shadow 純審計，
    // 丟列絕對優於讓 tick pipeline backpressure。
    let _ = tx.try_send(msg);
}

#[cfg(test)]
#[path = "helpers/phys_lock_wrapper_tests.rs"]
mod phys_lock_wrapper_tests;
