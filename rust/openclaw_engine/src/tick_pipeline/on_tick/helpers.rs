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
    reason.strip_prefix("risk_close:phys_lock_").and_then(|suf| {
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
    let edge_source = if est_net_bps.is_some() { "cell" } else { "fallback" };
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

    let disagreed = phys_only_signal != shadow_signal
        || phys_only_source.as_tag() != shadow_source.as_tag();
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
mod phys_lock_wrapper_tests {
    use super::*;

    // T4-FIX integration test: ensures the T3 emission string actually fires
    // the combine_layer path (prefix + strip + release-build invariant). If
    // someone reverts the prefix back to `PHYS-LOCK` or breaks the strip, this
    // test goes red and 459 LOC of combine_layer stays live.
    // T4-FIX 整合測試：確保 T3 精確輸出字串真的觸發 combine_layer 路徑（prefix +
    // strip + release-build 不變式）。若 prefix 回歸為 `PHYS-LOCK` 或 strip 破壞，
    // 本測試紅，459 LOC combine_layer 保持活躍。

    #[test]
    fn t4_fix_end_to_end_phys_lock_reaches_combine_layer_as_physical_lock() {
        // Arrange — construct the *exact* string T3 emits via
        // risk_checks.rs:242 `format!("risk_close:{}", reason)` for each of the
        // 3 phys_lock gate variants.
        // Arrange — 構造 T3 精確發出的 3 種 phys_lock 字串。
        for expected_bare_tag in [
            "phys_lock_gate1_low_edge",
            "phys_lock_gate4_giveback",
            "phys_lock_gate4_stale_roc_neg",
        ] {
            let reason = format!("risk_close:{expected_bare_tag}");

            // Act #1: strip — must recognise this as a PHYS-LOCK and return
            // the bare tag (without the `risk_close:` envelope) that
            // combine_layer + Python parse_exit_tag both consume.
            // Act #1：strip — 必須識別為 PHYS-LOCK 並回傳 combine_layer 與
            // Python parse_exit_tag 都消費的裸 tag。
            let lock_tag = strip_phys_lock_prefix(&reason)
                .unwrap_or_else(|| panic!("T3 emission must strip: {reason}"));
            assert_eq!(lock_tag, expected_bare_tag);

            // Act #2: feed through combine_layer exactly as the production
            // wrapper does. Must yield (Lock, Physical) in Phase 1a.
            // Act #2：按生產 wrapper 模式走 combine_layer，Phase 1a 必為
            // (Lock, Physical)。
            let physical =
                crate::exit_features::PhysicalDecision::Lock(lock_tag.to_string());
            let (signal, source) = crate::combine_layer::combine_exit_decision(
                physical,
                None,
                &crate::combine_layer::CombineConfig::default(),
            );
            assert_eq!(signal, crate::combine_layer::ExitSignal::Lock);
            assert_eq!(
                source.as_tag(),
                "Physical",
                "Phase 1a P-only: exit_source MUST be Physical, not Disabled/ML/Hybrid"
            );

            // Act #3: execute the logging helper — exercises the promoted
            // `assert_eq!` invariant in release builds (would panic if ever
            // broken, closing the debug_assert_eq! loophole).
            // Act #3：執行 logging helper — release build 也會走 `assert_eq!`
            // invariant（破壞即 panic，封閉 debug_assert_eq! 漏洞）。
            // EDGE-DIAG-1 signature extension: pass placeholder owner + None
            // est_net_bps for unit test (production caller re-queries).
            log_phys_lock_through_combine_layer("BTCUSDT", &reason, lock_tag, "test", None);
        }

        // Guard against partial revert: legacy prefix `PHYS-LOCK` must NOT
        // strip (otherwise prefix mismatch would sneak back in).
        // 防範部分回退：舊 prefix `PHYS-LOCK` 不能匹配。
        assert_eq!(
            strip_phys_lock_prefix("PHYS-LOCK gate1"),
            None,
            "legacy PHYS-LOCK prefix must not match — guards against partial revert"
        );
        // Non-PHYS-LOCK reasons must bypass the combine layer wrapper.
        // 非 PHYS-LOCK 原因必須 bypass。
        assert_eq!(
            strip_phys_lock_prefix("risk_close:HARD STOP at 5.0%"),
            None
        );
    }

    // RUST-DOUBLE-PREFIX-1 (2026-04-23) regression: verify that the outbound
    // close tag emitted from `step_6_risk_checks` carries exactly ONE
    // `risk_close:` prefix regardless of whether `risk_checks.rs` produced the
    // reason bare (HARD STOP / TRAILING / TIME STOP / TP / DRAWDOWN) or
    // pre-prefixed (PHYS-LOCK — `risk_checks.rs:247` wraps before returning).
    // The production bug saw PHYS-LOCK rows land as
    // `"risk_close:risk_close:phys_lock_gate4_giveback"` (double prefix).
    //
    // This test pins the `build_risk_close_tag` contract used at the single
    // outbound emission site in `step_6_risk_checks.rs`.
    //
    // RUST-DOUBLE-PREFIX-1（2026-04-23）回歸：驗證 `step_6_risk_checks` 出口的
    // close tag 永遠只有一層 `risk_close:` 前綴，不論 reason 是裸字串
    // （HARD STOP / TRAILING / TIME STOP / TP / DRAWDOWN）或已 wrap
    // （PHYS-LOCK — risk_checks.rs:247 在回傳前已 wrap）。生產 bug 讓 PHYS-LOCK
    // 進表變成 `"risk_close:risk_close:phys_lock_gate4_giveback"`（雙前綴）。
    // 本測固化 step_6_risk_checks.rs 唯一 emission 點使用的 `build_risk_close_tag`
    // 契約。

    #[test]
    fn phys_lock_reasons_do_not_double_prefix() {
        // Arrange: the exact strings `risk_checks.rs` emits for PHYS-LOCK
        // (already wrapped with `risk_close:` envelope so strip_phys_lock_prefix
        // recognises them).
        // Arrange：risk_checks.rs 對 PHYS-LOCK 實際輸出的字串（已含前綴）。
        for reason in [
            "risk_close:phys_lock_gate4_giveback",
            "risk_close:phys_lock_gate4_stale_roc_neg",
            "risk_close:phys_lock_gate1_low_edge",
        ] {
            // Act — build the outbound tag exactly as step_6 does.
            // Act — 按 step_6 方式構造出口 tag。
            let tag = build_risk_close_tag(reason);

            // Assert #1: single prefix (no `risk_close:risk_close:` drift).
            // Assert #1：單一前綴（無 `risk_close:risk_close:` 漂移）。
            assert!(
                !tag.starts_with("risk_close:risk_close:"),
                "double prefix regression: {tag}"
            );
            // Assert #2: outbound tag is byte-identical to the reason (since it
            // already carries the single prefix).
            // Assert #2：出口 tag 與 reason 位元相同（reason 已帶單前綴）。
            assert_eq!(tag, reason);
            // Assert #3: the healthcheck's post-fix pattern
            // `strategy_name LIKE 'risk_close:phys_lock_%'` matches (single
            // colon, `phys_lock_` starts immediately after).
            // Assert #3：healthcheck 修復後的 pattern
            // `strategy_name LIKE 'risk_close:phys_lock_%'` 必命中（單冒號，
            // `phys_lock_` 緊接其後）。
            let expected_tag_core = reason.strip_prefix("risk_close:").unwrap();
            assert!(
                tag.starts_with("risk_close:") && tag[PREFIX_LEN..].starts_with("phys_lock_"),
                "healthcheck pattern 'risk_close:phys_lock_%' must match, got {tag} (core={expected_tag_core})"
            );
        }
    }

    #[test]
    fn non_phys_lock_reasons_get_single_prefix() {
        // Cost-edge / trailing / hard stop / time stop / take profit / drawdown
        // / daily-loss / consecutive-loss reasons come from risk_checks.rs
        // bare (no `risk_close:` wrap). step_6 must add exactly one prefix.
        // Cost-edge 等 reason 從 risk_checks.rs 裸字串出，step_6 必加且只加一次
        // `risk_close:` 前綴。
        let samples = [
            // (bare_reason, expected_outbound_tag)
            (
                "HARD STOP: pnl -6.00% <= -5.00%",
                "risk_close:HARD STOP: pnl -6.00% <= -5.00%",
            ),
            (
                "TRAILING STOP: peak 3.00% - current 1.00% = 2.00% >= distance 1.50%",
                "risk_close:TRAILING STOP: peak 3.00% - current 1.00% = 2.00% >= distance 1.50%",
            ),
            (
                "TIME STOP: held 24.0h >= limit 24.0h",
                "risk_close:TIME STOP: held 24.0h >= limit 24.0h",
            ),
            (
                "TAKE PROFIT: pnl 5.00% >= 4.50%",
                "risk_close:TAKE PROFIT: pnl 5.00% >= 4.50%",
            ),
            (
                "COST EDGE: ratio 0.85 >= 0.80",
                "risk_close:COST EDGE: ratio 0.85 >= 0.80",
            ),
        ];
        for (reason, expected) in samples {
            let tag = build_risk_close_tag(reason);
            assert_eq!(tag, expected, "bare reason must get exactly one prefix");
            assert!(
                !tag.starts_with("risk_close:risk_close:"),
                "bare reason must NOT double-prefix: {tag}"
            );
        }
    }

    // Local constant mirrors `build_risk_close_tag`'s prefix — kept in the test
    // module so a refactor must touch both sides in lockstep.
    // 本地常數鏡像 `build_risk_close_tag` 的前綴 — 重構必須兩邊同步改。
    const PREFIX_LEN: usize = "risk_close:".len();

    // ─────────────────────────────────────────────────────────────────────
    // INFRA-PREBUILD-1 audit L1-3 (2026-04-23): emit_shadow_exit_observation
    // decision matrix pure-fn tests. Each case pins (est_net_bps, ml_model_id,
    // exit_source, disagreed) tuple for one row of the matrix so regression in
    // `build_ml_inference_shadow` clamp semantics OR `combine_exit_decision`
    // fusion rules turn a single test red instead of silently drifting shadow
    // observation distribution in Phase 2.
    //
    // Scenario: Physical = `Lock(lock_tag)` on PHYS-LOCK path (Phase 1a).
    // Matrix (CombineConfig default: ml_confirm_threshold=0.70, override_high=2.0):
    //
    // | est_net_bps       | shrunk_score           | exit_source | disagreed | ml_model_id          |
    // |-------------------|------------------------|-------------|-----------|----------------------|
    // | None              | None → ml_opt=None     | Physical    | false     | None                 |
    // | Some(-20.0)       | clamp low → 0.0        | Physical    | false     | Some("shadow_...")   |
    // | Some(0.0)         | mid → 0.5 (<0.70)      | Physical    | false     | Some("shadow_...")   |
    // | Some(5.0)         | 0.75 (≥0.70) confirm   | Hybrid      | TRUE      | Some("shadow_...")   |
    // | Some(20.0)        | clamp high → 1.0       | Hybrid      | TRUE      | Some("shadow_...")   |
    // | Some(NaN)         | mock→None              | Physical    | false     | None                 |
    // | Some(INFINITY)    | mock→None              | Physical    | false     | None                 |
    //
    // INFRA-PREBUILD-1 審計 L1-3（2026-04-23）：emit_shadow_exit_observation 的
    // 決策矩陣純函式測試。每 case 固化 (est_net_bps, ml_model_id, exit_source,
    // disagreed) 四元組，令 `build_ml_inference_shadow` clamp 語意或
    // `combine_exit_decision` 融合規則回歸時單測紅，避免 Phase 2 shadow 觀測
    // 分布靜默漂移。Scenario = Physical=`Lock(lock_tag)` 在 PHYS-LOCK 路徑 Phase 1a。
    // ─────────────────────────────────────────────────────────────────────

    /// Helper: drain one ShadowExitMsg out of an mpsc channel created with
    /// capacity ≥ 1. Must be called in a `#[tokio::test]` async context OR
    /// synchronous context using `try_recv` — we pick `try_recv` so the
    /// decision-matrix cases stay plain `#[test]` (no async runtime needed,
    /// matches the pure-fn spirit of the audit finding).
    /// 輔助：從容量 ≥ 1 的 mpsc 通道取一條 ShadowExitMsg；採 `try_recv` 保持
    /// 純 `#[test]`（無需 async runtime），契合審計要求「pure-fn 單測」。
    fn recv_one_shadow(
        rx: &mut tokio::sync::mpsc::Receiver<crate::database::ShadowExitMsg>,
    ) -> crate::database::ShadowExitMsg {
        rx.try_recv().expect("emit_shadow_exit_observation must produce exactly one msg")
    }

    #[test]
    fn test_emit_shadow_none_edge_gives_physical_no_disagreement() {
        // Case: est_net_bps=None → build_ml_inference_shadow returns None →
        // combine falls back to P-only path → (Lock, Physical) source.
        // Case：est_net_bps=None → mock ML=None → combine 走 P-only → Physical。
        let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::ShadowExitMsg>(4);
        emit_shadow_exit_observation(
            "ctx-none", 1_700_000_000_000, "demo", "ma_crossover", "BTCUSDT", 1,
            "phys_lock_gate4_giveback", None, None,
            &tx,
        );
        let msg = recv_one_shadow(&mut rx);
        assert_eq!(msg.exit_source, "Physical");
        assert!(!msg.disagreed);
        assert!(msg.ml_model_id.is_none());
        assert!(msg.ml_score.is_none());
        assert_eq!(msg.physical_action, "Lock");
        assert_eq!(msg.physical_reason.as_deref(), Some("phys_lock_gate4_giveback"));
    }

    #[test]
    fn test_emit_shadow_low_edge_clamps_to_physical() {
        // Case: est_net_bps=-20.0 → shrunk raw (-20+10)/20 = -0.5 → clamp 0.0.
        // score=0.0 < 0.70 confirm → physical Lock + ml (any low) falls to Physical.
        // Case：est_net_bps=-20 → score 0.0（clamp）<0.70 → Physical。
        let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::ShadowExitMsg>(4);
        emit_shadow_exit_observation(
            "ctx-low", 1_700_000_000_000, "demo", "ma_crossover", "BTCUSDT", 1,
            "phys_lock_gate4_giveback", Some(-20.0), None,
            &tx,
        );
        let msg = recv_one_shadow(&mut rx);
        assert_eq!(msg.exit_source, "Physical");
        assert!(!msg.disagreed);
        // Mock ML was built (ml_model_id populated) but score < confirm → Physical.
        // Mock ML 有被建（ml_model_id 有值），但 score < confirm → Physical。
        assert_eq!(msg.ml_model_id.as_deref(), Some("shadow_mock_v1"));
        assert!(msg.ml_score.unwrap().abs() < 1e-6, "score should clamp to 0.0");
    }

    #[test]
    fn test_emit_shadow_neutral_edge_below_confirm_threshold() {
        // Case: est_net_bps=0.0 → score (0+10)/20 = 0.5 < 0.70 → Physical.
        // Case：est_net_bps=0 → score 0.5 < 0.70 → Physical。
        let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::ShadowExitMsg>(4);
        emit_shadow_exit_observation(
            "ctx-neu", 1_700_000_000_000, "demo", "ma_crossover", "BTCUSDT", 1,
            "phys_lock_gate4_giveback", Some(0.0), None,
            &tx,
        );
        let msg = recv_one_shadow(&mut rx);
        assert_eq!(msg.exit_source, "Physical");
        assert!(!msg.disagreed);
        assert_eq!(msg.ml_model_id.as_deref(), Some("shadow_mock_v1"));
        assert!((msg.ml_score.unwrap() - 0.5).abs() < 1e-6);
    }

    #[test]
    fn test_emit_shadow_confirm_threshold_triggers_hybrid_disagreement() {
        // Case: est_net_bps=5.0 → score (5+10)/20 = 0.75 ≥ 0.70 → Hybrid.
        // `phys_only` path (ml=None) → (Lock, Physical). With mock ML → (Lock, Hybrid).
        // Signal identical but source differs → disagreed=true.
        // Case：est_net_bps=5 → score 0.75 ≥ 0.70 → Hybrid；source 與 P-only 不同
        // → disagreed=true。
        let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::ShadowExitMsg>(4);
        emit_shadow_exit_observation(
            "ctx-hit", 1_700_000_000_000, "demo", "ma_crossover", "BTCUSDT", 1,
            "phys_lock_gate4_giveback", Some(5.0), None,
            &tx,
        );
        let msg = recv_one_shadow(&mut rx);
        assert_eq!(msg.exit_source, "Hybrid");
        assert!(msg.disagreed, "score ≥ confirm_threshold must flip exit_source to Hybrid → disagreed");
        assert_eq!(msg.ml_model_id.as_deref(), Some("shadow_mock_v1"));
        assert!((msg.ml_score.unwrap() - 0.75).abs() < 1e-6);
        // disagreement_reason should name the source difference.
        // disagreement_reason 應列出 source 差異。
        let reason = msg.disagreement_reason.as_deref().unwrap_or("");
        assert!(reason.contains("Physical"), "disagreement_reason missing Physical: {reason:?}");
        assert!(reason.contains("Hybrid"), "disagreement_reason missing Hybrid: {reason:?}");
    }

    #[test]
    fn test_emit_shadow_high_edge_clamps_to_hybrid() {
        // Case: est_net_bps=20.0 → score (20+10)/20 = 1.5 → clamp 1.0 ≥ 0.70 → Hybrid.
        // Case：est_net_bps=20 → score clamp 1.0 → Hybrid。
        let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::ShadowExitMsg>(4);
        emit_shadow_exit_observation(
            "ctx-high", 1_700_000_000_000, "demo", "ma_crossover", "BTCUSDT", 1,
            "phys_lock_gate4_giveback", Some(20.0), None,
            &tx,
        );
        let msg = recv_one_shadow(&mut rx);
        assert_eq!(msg.exit_source, "Hybrid");
        assert!(msg.disagreed);
        assert!((msg.ml_score.unwrap() - 1.0).abs() < 1e-6, "score should clamp to 1.0");
    }

    #[test]
    fn test_emit_shadow_nan_edge_degrades_to_physical() {
        // Case: est_net_bps=NaN → build_ml_inference_shadow is_finite() → None
        // → ml_opt=None → (Lock, Physical), disagreed=false, ml_model_id=None.
        // This differs from the combine_layer's safety-net `Disabled` path
        // because the mock producer rejects NaN *before* combine ever sees it
        // (defence-in-depth).
        // Case：est_net_bps=NaN → mock builder is_finite() 拒 → None →
        // ml_opt=None → Physical。mock 層先拒，輪不到 combine 的 Disabled 安全網
        //（雙層防禦）。
        let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::ShadowExitMsg>(4);
        emit_shadow_exit_observation(
            "ctx-nan", 1_700_000_000_000, "demo", "ma_crossover", "BTCUSDT", 1,
            "phys_lock_gate4_giveback", Some(f32::NAN), None,
            &tx,
        );
        let msg = recv_one_shadow(&mut rx);
        assert_eq!(msg.exit_source, "Physical");
        assert!(!msg.disagreed);
        assert!(msg.ml_model_id.is_none(), "NaN edge → mock returns None → no ml_model_id");
        assert!(msg.ml_score.is_none());
    }

    #[test]
    fn test_emit_shadow_inf_edge_degrades_to_physical() {
        // Case: est_net_bps=+Inf → build_ml_inference_shadow is_finite() → None
        // → Physical. Same defence-in-depth as NaN case.
        // Case：est_net_bps=+Inf → mock builder is_finite() 拒 → None → Physical。
        let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::ShadowExitMsg>(4);
        emit_shadow_exit_observation(
            "ctx-inf", 1_700_000_000_000, "demo", "ma_crossover", "BTCUSDT", 1,
            "phys_lock_gate4_giveback", Some(f32::INFINITY), None,
            &tx,
        );
        let msg = recv_one_shadow(&mut rx);
        assert_eq!(msg.exit_source, "Physical");
        assert!(!msg.disagreed);
        assert!(msg.ml_model_id.is_none(), "Inf edge → mock returns None → no ml_model_id");
        assert!(msg.ml_score.is_none());
    }

    // ─────────────────────────────────────────────────────────────────────
    // INFRA-PREBUILD-1 audit L1-1 (2026-04-23): cell-age propagation tests.
    // Two angles: (a) emit wrapper actually sets ml_age_secs on the shadow
    // message from the caller's cell_age_secs param, and (b) a stale age
    // (8 days) flips the shadow row to exit_source=Disabled so Phase 2
    // operators see the fallback path exercised in real traffic.
    //
    // Without these, Part A's `cell_age_secs.unwrap_or(0)` + caller-always-
    // passes-None wiring meant every shadow row landed fresh regardless of
    // writer health, which makes the 7d stale gate dead code. The L2-5
    // healthcheck can now assume fresh-vs-stale rows are real signal.
    //
    // INFRA-PREBUILD-1 審計 L1-1（2026-04-23）：cell 齡期傳遞測試。
    // 兩個角度：(a) emit wrapper 確實把 caller 的 cell_age_secs 寫進
    // `ml_age_secs`；(b) 8 天齡期會讓 shadow 列 exit_source 變 Disabled，
    // Phase 2 operator 能在真流量看到 fallback 路徑 fire。
    // 沒這兩測，Part A 的 `unwrap_or(0)` + caller 永遠傳 None 會讓所有
    // shadow 永遠 fresh、7d stale gate 退化為死碼。
    // ─────────────────────────────────────────────────────────────────────

    #[test]
    fn test_emit_shadow_fresh_age_propagates_to_ml_age_secs() {
        // Case: cell_age_secs=Some(60) → shadow row ml_age_secs=60.
        // Fresh so exit_source stays on normal (Hybrid at score ≥ 0.70).
        // Case：cell_age_secs=Some(60) → shadow 列 ml_age_secs=60；fresh，
        // score 0.75 ≥ 0.70 → Hybrid。
        let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::ShadowExitMsg>(4);
        emit_shadow_exit_observation(
            "ctx-fresh", 1_700_000_000_000, "demo", "ma_crossover", "BTCUSDT", 1,
            "phys_lock_gate4_giveback", Some(5.0), Some(60),
            &tx,
        );
        let msg = recv_one_shadow(&mut rx);
        assert_eq!(
            msg.ml_age_secs,
            Some(60),
            "caller-supplied cell_age_secs must reach ml_age_secs unchanged"
        );
        // Fresh + score 0.75 → Hybrid path.
        // Fresh 且 score 0.75 → Hybrid。
        assert_eq!(msg.exit_source, "Hybrid");
    }

    #[test]
    fn test_emit_shadow_stale_age_triggers_disabled() {
        // Case: cell_age_secs=Some(8 * 86400) > CombineConfig.max_model_age_secs
        // (7d) → build_ml_inference_shadow forwards the age → combine's stale-
        // age guard fires → ExitSource::Disabled. Ensures Phase 2 operators
        // observe real Disabled fallback rows whenever the Python edge writer
        // stalls >7d instead of the L1-1 bug's always-fresh behaviour.
        // Case：cell_age_secs=Some(8d) > max_model_age_secs 7d →
        // build_ml_inference_shadow 傳遞齡期 → combine stale guard fire →
        // ExitSource=Disabled。讓 Phase 2 operator 在 Python writer 停寫
        // >7d 時能看到真實 Disabled fallback 列，而非 L1-1 修前的永遠 fresh。
        let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::ShadowExitMsg>(4);
        let eight_days_secs: u64 = 8 * 24 * 3600;
        emit_shadow_exit_observation(
            "ctx-stale", 1_700_000_000_000, "demo", "ma_crossover", "BTCUSDT", 1,
            "phys_lock_gate4_giveback", Some(5.0), Some(eight_days_secs),
            &tx,
        );
        let msg = recv_one_shadow(&mut rx);
        assert_eq!(
            msg.exit_source, "Disabled",
            "stale cell (>7d) must degrade to Disabled exit_source"
        );
        assert!(
            msg.disagreed,
            "Disabled vs Physical (phys-only) are different as_tag → disagreed"
        );
        assert_eq!(
            msg.ml_age_secs,
            Some(eight_days_secs as i64),
            "stale age must round-trip through to ml_age_secs"
        );
        // ml_model_id still populated (mock was built) — only exit_source
        // reflects the stale-path degradation.
        // ml_model_id 仍有（mock 已建），僅 exit_source 反映 stale 降級。
        assert_eq!(msg.ml_model_id.as_deref(), Some("shadow_mock_v1"));
    }

    // ─────────────────────────────────────────────────────────────────────
    // INFRA-PREBUILD-1 audit L1-1 (2026-04-23): compute_edge_estimates_file_
    // age_secs pure-fn tests. File-system side is intentionally narrow — one
    // happy path (recent tempfile ~0s age), one missing-file path (None),
    // one mode-split check (paper ≠ demo filename). No env mutation, no
    // sleeps, no tracing — pure pressure on the proxy rule.
    //
    // INFRA-PREBUILD-1 審計 L1-1（2026-04-23）：`compute_edge_estimates_file_
    // age_secs` 純 fn 測試。刻意窄範圍 — 一條 happy（新檔 ~0s）、一條
    // missing（回 None）、一條 mode 切檔名驗證。不動 env、不 sleep、不打 log。
    // ─────────────────────────────────────────────────────────────────────

    #[test]
    fn test_compute_edge_estimates_file_age_secs_missing_file_returns_none() {
        // Missing file → None (cold-start before Python writer's first cycle).
        // 檔案不存在 → None（Python writer 首次寫入前的冷啟動）。
        let tmp = std::env::temp_dir()
            .join(format!("openclaw_test_edge_age_missing_{}", std::process::id()));
        // Do NOT create tmp/settings/edge_estimates.json — must return None.
        // 不建立檔案 — 必須回 None。
        let age = compute_edge_estimates_file_age_secs("demo", &tmp);
        assert_eq!(age, None, "missing file must return None, got {age:?}");
    }

    #[test]
    fn test_compute_edge_estimates_file_age_secs_recent_file_under_5s() {
        // Create a fresh file, expect age_secs in [0, 5] (tight bound — no
        // sleeps). Uses `std::env::temp_dir()` so no OPENCLAW_BASE_DIR env
        // mutation. Cleans up after itself.
        // 建立新檔，預期齡期 ∈ [0, 5]（緊邊界，無 sleep）；
        // 用 temp_dir 不動 env，自行清理。
        let tmp = std::env::temp_dir()
            .join(format!("openclaw_test_edge_age_fresh_{}", std::process::id()));
        let settings_dir = tmp.join("settings");
        std::fs::create_dir_all(&settings_dir).expect("mkdir settings");
        let file_path = settings_dir.join("edge_estimates.json");
        std::fs::write(&file_path, b"{}").expect("write stub");

        let age = compute_edge_estimates_file_age_secs("demo", &tmp)
            .expect("recent file must yield Some");
        assert!(
            age <= 5,
            "fresh file age should be ≤5s, got {age}s (clock or FS anomaly)"
        );

        // Clean up / 清理。
        let _ = std::fs::remove_file(&file_path);
        let _ = std::fs::remove_dir(&settings_dir);
        let _ = std::fs::remove_dir(&tmp);
    }

    #[test]
    fn test_compute_edge_estimates_file_age_secs_paper_uses_different_filename() {
        // Paper mode must read edge_estimates_paper.json, not edge_estimates.json.
        // Create ONLY edge_estimates.json → paper mode must still return None
        // (paper file missing) while demo returns Some.
        // Paper 模式讀 edge_estimates_paper.json；只建 edge_estimates.json 時，
        // paper 仍回 None、demo 回 Some — 驗證兩個 mode 看不同檔案。
        let tmp = std::env::temp_dir()
            .join(format!("openclaw_test_edge_age_modes_{}", std::process::id()));
        let settings_dir = tmp.join("settings");
        std::fs::create_dir_all(&settings_dir).expect("mkdir settings");
        let demo_path = settings_dir.join("edge_estimates.json");
        std::fs::write(&demo_path, b"{}").expect("write demo stub");

        // demo → Some
        // demo → Some
        assert!(
            compute_edge_estimates_file_age_secs("demo", &tmp).is_some(),
            "demo must find edge_estimates.json"
        );
        // live also shares demo file
        // live 共用 demo 檔案
        assert!(
            compute_edge_estimates_file_age_secs("live", &tmp).is_some(),
            "live must share edge_estimates.json"
        );
        // paper → None (paper file not created)
        // paper → None（paper 檔案未建）
        assert_eq!(
            compute_edge_estimates_file_age_secs("paper", &tmp),
            None,
            "paper mode must look for edge_estimates_paper.json and return None when absent"
        );

        // Clean up / 清理。
        let _ = std::fs::remove_file(&demo_path);
        let _ = std::fs::remove_dir(&settings_dir);
        let _ = std::fs::remove_dir(&tmp);
    }

    // E4-1 audit FUP (2026-04-23): the two regression tests below close the
    // pipeline-out gap flagged by E4-1 against RUST-DOUBLE-PREFIX-1's
    // `build_risk_close_tag` (see `step_6_risk_checks.rs:306/339/352`). The
    // existing unit tests above pin the helper's output shape for the current
    // call-site; these two add defence-in-depth so the fix cannot silently
    // regress via a new `format!("risk_close:{...}")` literal slipping into the
    // pipeline, nor via a step_6 edit that accidentally applies the helper
    // twice in a row.
    //
    // (A) `no_new_literal_risk_close_format_outside_helpers_rs`:
    //     static file-system scan that asserts the ONLY two files in the engine
    //     crate allowed to contain `format!("risk_close:` are
    //     `on_tick/helpers.rs` (this file — holds both the production helper
    //     impl and this test module's own PHYS-LOCK emission replica) and
    //     `risk_checks.rs` (holds the design-sanctioned single PHYS-LOCK wrap
    //     at line 247 that hands the `risk_close:phys_lock_...` envelope to
    //     downstream `strip_phys_lock_prefix`). Any new call-site — e.g. some
    //     future dev re-adding `format!("risk_close:{reason}")` inside
    //     `step_6_risk_checks.rs` — immediately fails this test.
    //
    // (C) `build_risk_close_tag_is_idempotent`:
    //     contractually pins idempotency. If anyone ever rewires step_6 so the
    //     helper is applied twice in a row (e.g. a bad refactor that calls
    //     `build_risk_close_tag(build_risk_close_tag(reason))`), the second
    //     invocation must be a no-op — no double prefix can sneak back in.
    //
    // E4-1 審計 FUP（2026-04-23）：下方兩個回歸測試補 E4-1 對 RUST-DOUBLE-PREFIX-1
    // 修復提出的「pipeline 出口端 e2e 斷言」缺口（對應 step_6_risk_checks.rs
    // 第 306/339/352 行）。既有單測固化了 helper 當下輸出形狀；這兩個補 defence-
    // in-depth，防止別處新增 `format!("risk_close:{...}")` literal 繞過 helper，
    // 或 step_6 被改成連呼兩次 helper。
    //
    // (A) `no_new_literal_risk_close_format_outside_helpers_rs`：
    //     靜態檔案系統掃描，斷言整個 engine crate 只允許兩個檔案出現
    //     `format!("risk_close:` — `on_tick/helpers.rs`（本檔；production helper
    //     + test module 中的 PHYS-LOCK emission replica）與 `risk_checks.rs`
    //     （line 247 設計上合法的 PHYS-LOCK 單次 wrap，產生
    //     `risk_close:phys_lock_...` envelope 供下游 `strip_phys_lock_prefix`
    //     消費）。任何新增呼叫點（例如在 `step_6_risk_checks.rs` 內重加
    //     `format!("risk_close:{reason}")`）立即 red。
    //
    // (C) `build_risk_close_tag_is_idempotent`：
    //     契約固化 idempotency。若有人改 step_6 連呼兩次 helper（例如錯誤重構
    //     變成 `build_risk_close_tag(build_risk_close_tag(reason))`），第二次
    //     呼叫必為 no-op，雙前綴無法潛回。

    /// E4-1 audit FUP — static regression guard for `format!("risk_close:`
    /// literals. Only `helpers.rs` (this file) and `risk_checks.rs` are
    /// allowed to contain the prefix pattern in this form. Any other file
    /// means a new `format!("risk_close:{...}")` call-site has slipped in,
    /// which is exactly the class of bug RUST-DOUBLE-PREFIX-1 fixed.
    ///
    /// E4-1 審計 FUP — `format!("risk_close:` literal 靜態回歸防線。
    /// 只有 `helpers.rs`（本檔）和 `risk_checks.rs` 允許出現此 pattern。
    /// 其他檔案命中 = 有人新增 `format!("risk_close:{...}")` 呼叫點，正是
    /// RUST-DOUBLE-PREFIX-1 修復的 bug class。
    #[test]
    fn no_new_literal_risk_close_format_outside_helpers_rs() {
        use std::fs;
        use std::path::{Path, PathBuf};

        // Pattern we guard against. Note: matches the `format!("risk_close:`
        // OPENING — both `{reason}` interpolation and `{}` + arg forms trip it.
        // 防禦 pattern：匹配 `format!("risk_close:` 的開頭 —— `{reason}` 與
        // `{}` + arg 兩種形式都會命中。
        const GUARD_PATTERN: &str = "format!(\"risk_close:";

        // Allowlist: files where this literal is legitimately present.
        // - `on_tick/helpers.rs`: production helper impl + this test module's
        //   PHYS-LOCK emission replica (`format!("risk_close:{expected_bare_tag}")`
        //   at line 155) that mirrors `risk_checks.rs:247` for the combine-layer
        //   e2e test.
        // - `risk_checks.rs`: the single design-sanctioned PHYS-LOCK wrap at
        //   line 247 (`RiskAction::ClosePosition(format!("risk_close:{}", reason))`)
        //   that produces the `risk_close:phys_lock_...` envelope downstream.
        // 白名單：合法出現此 literal 的兩個檔案。
        const ALLOWLIST: &[&str] = &[
            "tick_pipeline/on_tick/helpers.rs",
            "risk_checks.rs",
        ];

        // Recursively walk `src/` from CARGO_MANIFEST_DIR, collect all `.rs`
        // files, grep for GUARD_PATTERN, flag any outside ALLOWLIST.
        // 從 CARGO_MANIFEST_DIR 遞歸掃 `src/`，收集所有 `.rs` 檔，抓
        // GUARD_PATTERN，不在白名單的檔案即違規。
        fn walk(dir: &Path, acc: &mut Vec<PathBuf>) {
            let entries = match fs::read_dir(dir) {
                Ok(e) => e,
                Err(_) => return,
            };
            for entry in entries.flatten() {
                let path = entry.path();
                if path.is_dir() {
                    walk(&path, acc);
                } else if path.extension().and_then(|s| s.to_str()) == Some("rs") {
                    acc.push(path);
                }
            }
        }

        let manifest_dir = env!("CARGO_MANIFEST_DIR");
        let src_dir = Path::new(manifest_dir).join("src");
        assert!(
            src_dir.is_dir(),
            "src/ dir not found at {} — test harness broken",
            src_dir.display()
        );

        let mut rs_files: Vec<PathBuf> = Vec::new();
        walk(&src_dir, &mut rs_files);
        assert!(
            !rs_files.is_empty(),
            "walk found 0 .rs files under {} — harness broken",
            src_dir.display()
        );

        let mut violations: Vec<String> = Vec::new();
        for file in &rs_files {
            let rel = file
                .strip_prefix(&src_dir)
                .unwrap()
                .to_string_lossy()
                .replace('\\', "/"); // Windows path sep normalisation
            let allowed = ALLOWLIST.iter().any(|a| rel == *a);
            let contents = match fs::read_to_string(file) {
                Ok(c) => c,
                Err(_) => continue,
            };
            if allowed {
                continue;
            }
            // Only count lines that are not pure comments. Block-doc comments
            // (`///`, `//!`) and line comments (`//`) are informational —
            // RUST-DOUBLE-PREFIX-1's design notes legitimately quote the
            // pattern in several places. A real violation is an executable
            // statement containing the pattern.
            // 僅計入非純註解行。區塊/行註解（`///`、`//!`、`//`）僅為說明，
            // RUST-DOUBLE-PREFIX-1 的設計註解合法引用此 pattern。真正違規是
            // 內含 pattern 的可執行語句。
            let hits: Vec<(usize, &str)> = contents
                .lines()
                .enumerate()
                .filter(|(_, l)| l.contains(GUARD_PATTERN))
                .filter(|(_, l)| {
                    let trimmed = l.trim_start();
                    !(trimmed.starts_with("//") || trimmed.starts_with("/*"))
                })
                .collect();
            if !hits.is_empty() {
                // Capture offending line numbers for actionable diagnostic.
                // 擷取違規行號便於定位。
                let lines: Vec<String> = hits
                    .iter()
                    .map(|(n, l)| format!("  line {}: {}", n + 1, l.trim()))
                    .collect();
                violations.push(format!("{}:\n{}", rel, lines.join("\n")));
            }
        }

        assert!(
            violations.is_empty(),
            "RUST-DOUBLE-PREFIX-1 regression: new `format!(\"risk_close:` literal \
             detected outside the allowlist ({:?}). Use `build_risk_close_tag()` \
             from `on_tick/helpers.rs` instead. Offenders:\n{}\n\n\
             RUST-DOUBLE-PREFIX-1 回歸：白名單外出現 `format!(\"risk_close:` \
             literal。請改呼 `on_tick/helpers.rs::build_risk_close_tag()`。違規檔：\n{}",
            ALLOWLIST,
            violations.join("\n\n"),
            violations.join("\n\n"),
        );
    }

    /// E4-1 FA BLOCKER FUP (2026-04-23 post-commit b0b47b5 review):
    /// Static grep for BARE `"risk_close:phys_lock_` string literals outside
    /// the allowlist. FA audit flagged that the sibling test
    /// `no_new_literal_risk_close_format_outside_helpers_rs` above only
    /// catches `format!("risk_close:{...}")` — it does NOT catch plain
    /// literals such as `"risk_close:phys_lock_new_reason"` that would
    /// bypass `build_risk_close_tag()` and hit the same double-prefix bug
    /// class from the string-constant angle.
    ///
    /// Scope deliberately narrowed to **`risk_close:phys_lock_`** (not all
    /// `risk_close:` literals) because other bare literals in production
    /// (e.g., `"risk_close:halt_session"` in step_6, `"risk_close:fast_track"`
    /// in step_0, `"risk_close:ipc_close_symbol"` in commands.rs) are each
    /// self-contained tags that the helper intentionally forwards through
    /// `build_risk_close_tag()` unchanged — they are not PHYS-LOCK-class
    /// reasons and do NOT participate in the `risk_checks.rs:247` wrap →
    /// `step_6:_close_tag()` double-wrap flow that RUST-DOUBLE-PREFIX-1 fixed.
    ///
    /// E4-1 FA BLOCKER FUP（2026-04-23 post-commit review）：
    /// 掃描白名單外的 BARE `"risk_close:phys_lock_` 字串字面量。FA 審核指出
    /// 上方 `format!` 靜態掃只抓 `format!("risk_close:{...}")` — 不抓
    /// `"risk_close:phys_lock_new_reason"` 這類純字面量，可從另一角度繞過
    /// `build_risk_close_tag()` 重引入雙前綴 bug。
    ///
    /// Scope 縮到 **`risk_close:phys_lock_`**（而非所有 `risk_close:`）因
    /// 其他 bare literal（如 `"risk_close:halt_session"` / `"risk_close:fast_track"`
    /// / `"risk_close:ipc_close_symbol"`）本身就是 self-contained tag，helper
    /// 刻意 forward 不動，非 PHYS-LOCK 類 reason、不參與 double-wrap 流程。
    #[test]
    fn no_new_literal_risk_close_phys_lock_outside_helpers_rs() {
        use std::fs;
        use std::path::{Path, PathBuf};

        // PHYS-LOCK-specific bare literal guard.
        // PHYS-LOCK 類 bare literal 專屬守護。
        const GUARD_PATTERN: &str = "\"risk_close:phys_lock_";

        // Allowlist: files where `risk_close:phys_lock_` literal is legitimate.
        // - `helpers.rs`: this test + `strip_phys_lock_prefix` + idempotency
        //   test reasons that legitimately exercise the full envelope.
        // - `risk_checks.rs`: `#[cfg(test)]` mod tests referencing the tag.
        // - `step_6_risk_checks.rs`: design comments + `#[cfg(test)]` tests.
        // 白名單：`helpers.rs`（本 test + strip_phys_lock_prefix + idempotency
        // test 合法引用）/ `risk_checks.rs`（test mod 引用）/
        // `step_6_risk_checks.rs`（設計註解 + test mod 引用）。
        const ALLOWLIST: &[&str] = &[
            "tick_pipeline/on_tick/helpers.rs",
            "risk_checks.rs",
            "tick_pipeline/on_tick/step_6_risk_checks.rs",
        ];

        fn walk(dir: &Path, acc: &mut Vec<PathBuf>) {
            let entries = match fs::read_dir(dir) {
                Ok(e) => e,
                Err(_) => return,
            };
            for entry in entries.flatten() {
                let path = entry.path();
                if path.is_dir() {
                    walk(&path, acc);
                } else if path.extension().and_then(|s| s.to_str()) == Some("rs") {
                    acc.push(path);
                }
            }
        }

        let manifest_dir = env!("CARGO_MANIFEST_DIR");
        let src_dir = Path::new(manifest_dir).join("src");
        let mut rs_files: Vec<PathBuf> = Vec::new();
        walk(&src_dir, &mut rs_files);

        let mut violations: Vec<String> = Vec::new();
        for file in &rs_files {
            let rel = file
                .strip_prefix(&src_dir)
                .unwrap()
                .to_string_lossy()
                .replace('\\', "/");
            if ALLOWLIST.iter().any(|a| rel == *a) {
                continue;
            }
            let contents = match fs::read_to_string(file) {
                Ok(c) => c,
                Err(_) => continue,
            };
            // Strip pure comment lines (same filter as the sibling test).
            // 排除純註解行（與上方 sibling test 同過濾）。
            let hits: Vec<(usize, &str)> = contents
                .lines()
                .enumerate()
                .filter(|(_, l)| l.contains(GUARD_PATTERN))
                .filter(|(_, l)| {
                    let trimmed = l.trim_start();
                    !(trimmed.starts_with("//") || trimmed.starts_with("/*"))
                })
                .collect();
            if !hits.is_empty() {
                let lines: Vec<String> = hits
                    .iter()
                    .map(|(n, l)| format!("  line {}: {}", n + 1, l.trim()))
                    .collect();
                violations.push(format!("{}:\n{}", rel, lines.join("\n")));
            }
        }

        assert!(
            violations.is_empty(),
            "RUST-DOUBLE-PREFIX-1 regression (bare literal angle): new \
             `\"risk_close:phys_lock_...\"` string literal outside allowlist {:?}. \
             PHYS-LOCK-class reasons MUST go through `build_risk_close_tag()` to \
             avoid the double-prefix bug from the string-constant angle. Offenders:\n{}\n\n\
             RUST-DOUBLE-PREFIX-1 回歸（裸字面量角度）：白名單外出現 \
             `\"risk_close:phys_lock_...\"` literal。PHYS-LOCK 類 reason 必須\
             經 `build_risk_close_tag()` 以防從字串常量角度重引入雙前綴 bug。違規檔：\n{}",
            ALLOWLIST,
            violations.join("\n\n"),
            violations.join("\n\n"),
        );
    }

    /// E4-1 audit FUP — contractual idempotency pin. `build_risk_close_tag`
    /// applied twice in a row must equal applied once, for every reason
    /// variant `risk_checks.rs` can emit. Guards against a future step_6
    /// edit that accidentally wraps the helper output through the helper
    /// again (which would re-introduce the double-prefix bug from a
    /// different angle).
    ///
    /// E4-1 審計 FUP — 契約 idempotency 固化。對 `risk_checks.rs` 能產出的
    /// 每種 reason 變體，連呼 `build_risk_close_tag` 兩次結果必須等同呼一次。
    /// 防止日後 step_6 改動誤將 helper 輸出再餵回 helper（會從另一角度
    /// 重引入雙前綴 bug）。
    #[test]
    fn build_risk_close_tag_is_idempotent() {
        // Representative reason set covers every emission path currently in
        // `risk_checks.rs`: PHYS-LOCK (already-wrapped) + all bare variants
        // (HARD STOP / TRAILING / TIME / TP / COST EDGE / DRAWDOWN /
        // CONSECUTIVE LOSS / DAILY LOSS).
        // 代表性 reason 集合涵蓋 `risk_checks.rs` 當前所有 emission path：
        // PHYS-LOCK（已 wrap）+ 全部裸變體。
        let reasons = [
            // PHYS-LOCK variants (already wrapped by risk_checks.rs:247).
            // PHYS-LOCK 變體（risk_checks.rs:247 已 wrap）。
            "risk_close:phys_lock_gate4_giveback",
            "risk_close:phys_lock_gate4_stale_roc_neg",
            "risk_close:phys_lock_gate1_low_edge",
            // Bare variants (risk_checks.rs emits without wrap).
            // 裸變體（risk_checks.rs 不 wrap 直接 emit）。
            "HARD STOP: pnl -6.00% <= -5.00%",
            "TRAILING STOP: peak 3.00% - current 1.00% = 2.00% >= distance 1.50%",
            "TIME STOP: held 24.0h >= limit 24.0h",
            "TAKE PROFIT: pnl 5.00% >= 4.50%",
            "COST EDGE: ratio 0.85 >= 0.80",
            "DRAWDOWN: session equity -2.50% <= -2.00%",
            "CONSECUTIVE LOSS: 3 in a row",
            "DAILY LOSS: -3.50% <= -3.00%",
            // Defensive edge cases.
            // 防禦性邊界。
            "",
            "risk_close:",
        ];

        for reason in reasons {
            let once = build_risk_close_tag(reason);
            let twice = build_risk_close_tag(&once);

            // Assert #1: exact equality — helper is f(f(x)) == f(x).
            // Assert #1：精確相等 — helper 滿足 f(f(x)) == f(x)。
            assert_eq!(
                once, twice,
                "build_risk_close_tag must be idempotent for reason={reason:?}: \
                 once={once:?} twice={twice:?}"
            );

            // Assert #2: no double-prefix regardless of input (belt + braces).
            // Assert #2：無論輸入為何，結果必無雙前綴（雙保險）。
            assert!(
                !twice.starts_with("risk_close:risk_close:"),
                "double prefix slipped in on second application: reason={reason:?} \
                 once={once:?} twice={twice:?}"
            );
        }
    }
}
