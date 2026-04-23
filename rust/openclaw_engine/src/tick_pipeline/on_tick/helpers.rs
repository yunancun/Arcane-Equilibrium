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
}
