//! Tests for `on_tick::helpers` PHYS-LOCK / shadow-exit wrappers.
//! `on_tick::helpers` PHYS-LOCK / shadow-exit wrapper 測試。

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
        let physical = crate::exit_features::PhysicalDecision::Lock(lock_tag.to_string());
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
    assert_eq!(strip_phys_lock_prefix("risk_close:HARD STOP at 5.0%"), None);
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
    rx.try_recv()
        .expect("emit_shadow_exit_observation must produce exactly one msg")
}

#[test]
fn test_emit_shadow_none_edge_gives_physical_no_disagreement() {
    // Case: est_net_bps=None → build_ml_inference_shadow returns None →
    // combine falls back to P-only path → (Lock, Physical) source.
    // Case：est_net_bps=None → mock ML=None → combine 走 P-only → Physical。
    let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::ShadowExitMsg>(4);
    emit_shadow_exit_observation(
        "ctx-none",
        1_700_000_000_000,
        "demo",
        "ma_crossover",
        "BTCUSDT",
        1,
        "phys_lock_gate4_giveback",
        None,
        None,
        &tx,
    );
    let msg = recv_one_shadow(&mut rx);
    assert_eq!(msg.exit_source, "Physical");
    assert!(!msg.disagreed);
    assert!(msg.ml_model_id.is_none());
    assert!(msg.ml_score.is_none());
    assert_eq!(msg.physical_action, "Lock");
    assert_eq!(
        msg.physical_reason.as_deref(),
        Some("phys_lock_gate4_giveback")
    );
}

#[test]
fn test_emit_shadow_low_edge_clamps_to_physical() {
    // Case: est_net_bps=-20.0 → shrunk raw (-20+10)/20 = -0.5 → clamp 0.0.
    // score=0.0 < 0.70 confirm → physical Lock + ml (any low) falls to Physical.
    // Case：est_net_bps=-20 → score 0.0（clamp）<0.70 → Physical。
    let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::ShadowExitMsg>(4);
    emit_shadow_exit_observation(
        "ctx-low",
        1_700_000_000_000,
        "demo",
        "ma_crossover",
        "BTCUSDT",
        1,
        "phys_lock_gate4_giveback",
        Some(-20.0),
        None,
        &tx,
    );
    let msg = recv_one_shadow(&mut rx);
    assert_eq!(msg.exit_source, "Physical");
    assert!(!msg.disagreed);
    // Mock ML was built (ml_model_id populated) but score < confirm → Physical.
    // Mock ML 有被建（ml_model_id 有值），但 score < confirm → Physical。
    assert_eq!(msg.ml_model_id.as_deref(), Some("shadow_mock_v1"));
    assert!(
        msg.ml_score.unwrap().abs() < 1e-6,
        "score should clamp to 0.0"
    );
}

#[test]
fn test_emit_shadow_neutral_edge_below_confirm_threshold() {
    // Case: est_net_bps=0.0 → score (0+10)/20 = 0.5 < 0.70 → Physical.
    // Case：est_net_bps=0 → score 0.5 < 0.70 → Physical。
    let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::ShadowExitMsg>(4);
    emit_shadow_exit_observation(
        "ctx-neu",
        1_700_000_000_000,
        "demo",
        "ma_crossover",
        "BTCUSDT",
        1,
        "phys_lock_gate4_giveback",
        Some(0.0),
        None,
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
        "ctx-hit",
        1_700_000_000_000,
        "demo",
        "ma_crossover",
        "BTCUSDT",
        1,
        "phys_lock_gate4_giveback",
        Some(5.0),
        None,
        &tx,
    );
    let msg = recv_one_shadow(&mut rx);
    assert_eq!(msg.exit_source, "Hybrid");
    assert!(
        msg.disagreed,
        "score ≥ confirm_threshold must flip exit_source to Hybrid → disagreed"
    );
    assert_eq!(msg.ml_model_id.as_deref(), Some("shadow_mock_v1"));
    assert!((msg.ml_score.unwrap() - 0.75).abs() < 1e-6);
    // disagreement_reason should name the source difference.
    // disagreement_reason 應列出 source 差異。
    let reason = msg.disagreement_reason.as_deref().unwrap_or("");
    assert!(
        reason.contains("Physical"),
        "disagreement_reason missing Physical: {reason:?}"
    );
    assert!(
        reason.contains("Hybrid"),
        "disagreement_reason missing Hybrid: {reason:?}"
    );
}

#[test]
fn test_emit_shadow_high_edge_clamps_to_hybrid() {
    // Case: est_net_bps=20.0 → score (20+10)/20 = 1.5 → clamp 1.0 ≥ 0.70 → Hybrid.
    // Case：est_net_bps=20 → score clamp 1.0 → Hybrid。
    let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::ShadowExitMsg>(4);
    emit_shadow_exit_observation(
        "ctx-high",
        1_700_000_000_000,
        "demo",
        "ma_crossover",
        "BTCUSDT",
        1,
        "phys_lock_gate4_giveback",
        Some(20.0),
        None,
        &tx,
    );
    let msg = recv_one_shadow(&mut rx);
    assert_eq!(msg.exit_source, "Hybrid");
    assert!(msg.disagreed);
    assert!(
        (msg.ml_score.unwrap() - 1.0).abs() < 1e-6,
        "score should clamp to 1.0"
    );
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
        "ctx-nan",
        1_700_000_000_000,
        "demo",
        "ma_crossover",
        "BTCUSDT",
        1,
        "phys_lock_gate4_giveback",
        Some(f32::NAN),
        None,
        &tx,
    );
    let msg = recv_one_shadow(&mut rx);
    assert_eq!(msg.exit_source, "Physical");
    assert!(!msg.disagreed);
    assert!(
        msg.ml_model_id.is_none(),
        "NaN edge → mock returns None → no ml_model_id"
    );
    assert!(msg.ml_score.is_none());
}

#[test]
fn test_emit_shadow_inf_edge_degrades_to_physical() {
    // Case: est_net_bps=+Inf → build_ml_inference_shadow is_finite() → None
    // → Physical. Same defence-in-depth as NaN case.
    // Case：est_net_bps=+Inf → mock builder is_finite() 拒 → None → Physical。
    let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::ShadowExitMsg>(4);
    emit_shadow_exit_observation(
        "ctx-inf",
        1_700_000_000_000,
        "demo",
        "ma_crossover",
        "BTCUSDT",
        1,
        "phys_lock_gate4_giveback",
        Some(f32::INFINITY),
        None,
        &tx,
    );
    let msg = recv_one_shadow(&mut rx);
    assert_eq!(msg.exit_source, "Physical");
    assert!(!msg.disagreed);
    assert!(
        msg.ml_model_id.is_none(),
        "Inf edge → mock returns None → no ml_model_id"
    );
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
        "ctx-fresh",
        1_700_000_000_000,
        "demo",
        "ma_crossover",
        "BTCUSDT",
        1,
        "phys_lock_gate4_giveback",
        Some(5.0),
        Some(60),
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
        "ctx-stale",
        1_700_000_000_000,
        "demo",
        "ma_crossover",
        "BTCUSDT",
        1,
        "phys_lock_gate4_giveback",
        Some(5.0),
        Some(eight_days_secs),
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
    let tmp = std::env::temp_dir().join(format!(
        "openclaw_test_edge_age_missing_{}",
        std::process::id()
    ));
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
    let tmp = std::env::temp_dir().join(format!(
        "openclaw_test_edge_age_fresh_{}",
        std::process::id()
    ));
    let settings_dir = tmp.join("settings");
    std::fs::create_dir_all(&settings_dir).expect("mkdir settings");
    let file_path = settings_dir.join("edge_estimates.json");
    std::fs::write(&file_path, b"{}").expect("write stub");

    let age =
        compute_edge_estimates_file_age_secs("demo", &tmp).expect("recent file must yield Some");
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
    let tmp = std::env::temp_dir().join(format!(
        "openclaw_test_edge_age_modes_{}",
        std::process::id()
    ));
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
    // - `on_tick/helpers.rs`: production helper impl.
    // - `on_tick/helpers/phys_lock_wrapper_tests.rs`: this test module's
    //   PHYS-LOCK emission replica (`format!("risk_close:{expected_bare_tag}")`
    //   near the top) that mirrors `risk_checks.rs:247` for the combine-layer
    //   e2e test.
    // - `risk_checks.rs`: the single design-sanctioned PHYS-LOCK wrap at
    //   line 247 (`RiskAction::ClosePosition(format!("risk_close:{}", reason))`)
    //   that produces the `risk_close:phys_lock_...` envelope downstream.
    // 白名單：合法出現此 literal 的檔案。
    const ALLOWLIST: &[&str] = &[
        "tick_pipeline/on_tick/helpers.rs",
        "tick_pipeline/on_tick/helpers/phys_lock_wrapper_tests.rs",
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
    // - `helpers.rs`: `strip_phys_lock_prefix`.
    // - `helpers/phys_lock_wrapper_tests.rs`: this test + idempotency test
    //   reasons that legitimately exercise the full envelope.
    // - `risk_checks.rs`: `#[cfg(test)]` mod tests referencing the tag.
    // - `step_6_risk_checks.rs`: design comments + `#[cfg(test)]` tests.
    // 白名單：`helpers.rs`（strip_phys_lock_prefix）/
    // `helpers/phys_lock_wrapper_tests.rs`（本 test + idempotency test 合法引用）/
    // `risk_checks.rs`（test mod 引用）/
    // `step_6_risk_checks.rs`（設計註解 + test mod 引用）。
    const ALLOWLIST: &[&str] = &[
        "tick_pipeline/on_tick/helpers.rs",
        "tick_pipeline/on_tick/helpers/phys_lock_wrapper_tests.rs",
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

// ─────────────────────────────────────────────────────────────────────
// EXIT-FEATURES-WRITER-BUG-1-FIX (2026-04-26): is_partial_reduce_tag
// taxonomy tests. Pin the contract that ONLY fast_track ReduceToHalf is
// recognised as partial-reduce; every other close path (PHYS-LOCK / hard
// stop / trailing / time / TP / drawdown / strategy exits / etc.) must
// pass through as a full close so the EF writer continues to emit. MIT
// audit `2026-04-26--exit_features_writer_bug_audit.md` §4 RCA-B
// mitigation. If a future partial-reduce path is added (e.g. ladder
// partial close), expand `is_partial_reduce_tag` and add a new test row
// here.
// EXIT-FEATURES-WRITER-BUG-1-FIX：is_partial_reduce_tag 分類測試 — 固化
// 唯有 fast_track ReduceToHalf 視為 partial reduce 的契約；其他全 full
// close 路徑必通過（EF 繼續寫）。新增 partial reduce 路徑時須擴 helper
// + 加新測試 row。
// ─────────────────────────────────────────────────────────────────────

#[test]
fn fast_track_reduce_half_is_recognised_as_partial_reduce() {
    // The exact tag emit_close_fill receives from
    // step_0_fast_track.rs:386 ReduceToHalf path.
    // step_0_fast_track.rs:386 ReduceToHalf 路徑傳入的精確 tag。
    assert!(
        is_partial_reduce_tag("risk_close:fast_track_reduce_half"),
        "fast_track ReduceToHalf MUST be recognised as partial reduce \
         — otherwise dust spiral 37 EF noise rows resurrect"
    );
}

#[test]
fn phys_lock_full_close_is_not_partial_reduce() {
    // PHYS-LOCK fires close_position_at_market (full close, position
    // removed). EF row must continue to be emitted.
    // PHYS-LOCK 走 close_position_at_market（全平 → 移除倉位），EF 必寫。
    for tag in [
        "risk_close:phys_lock_gate4_giveback",
        "risk_close:phys_lock_gate1_low_edge",
        "risk_close:phys_lock_gate4_stale_roc_neg",
    ] {
        assert!(
            !is_partial_reduce_tag(tag),
            "PHYS-LOCK full close must NOT be classified as partial: {tag}"
        );
    }
}

#[test]
fn legacy_full_close_paths_are_not_partial_reduce() {
    // Hard / trailing / time / TP / drawdown / consecutive-loss / daily-
    // loss / strategy exits all reach emit_close_fill via close_position*
    // helpers (full close). EF must continue to land for these.
    // 硬止損 / 跟蹤 / 時間 / TP / 回撤 / 連虧 / 日損 / 策略退場全走
    // close_position*（全平），EF 必須繼續落表。
    for tag in [
        "risk_close:HARD STOP: pnl -6.00% <= -5.00%",
        "risk_close:TRAILING STOP: peak 3.00% - current 1.00% = 2.00% >= distance 1.50%",
        "risk_close:TIME STOP: held 24.0h >= limit 24.0h",
        "risk_close:TAKE PROFIT: pnl 5.00% >= 4.50%",
        "risk_close:DRAWDOWN: session equity -2.50% <= -2.00%",
        "risk_close:CONSECUTIVE LOSS: 3 in a row",
        "risk_close:DAILY LOSS: -3.50% <= -3.00%",
        "risk_close:fast_track", // CloseAll path (full close)
        "risk_close:fast_track_close_all",
        "stop_trigger:hard_stop",
        "strategy_close:ma_crossover_exit",
        "",
    ] {
        assert!(
            !is_partial_reduce_tag(tag),
            "full-close path must NOT be classified as partial: {tag:?}"
        );
    }
}

#[test]
fn partial_reduce_match_is_byte_exact() {
    // Defensive: similar-but-not-equal strings must NOT match. Prevents
    // a future "looks-like-partial" false positive from silencing legit
    // full-close EF emissions (which would re-introduce the exact bug
    // RCA-B was meant to fix from the opposite direction).
    // 防禦性：類似但不相等的字串不可命中 — 避免未來「看起來像 partial」的
    // false positive 反向打殘 full-close EF emission，反向重現 RCA-B。
    assert!(
        !is_partial_reduce_tag("fast_track_reduce_half"),
        "missing prefix"
    );
    assert!(
        !is_partial_reduce_tag("risk_close:fast_track_reduce_half "),
        "trailing space must not match"
    );
    assert!(
        !is_partial_reduce_tag("RISK_CLOSE:FAST_TRACK_REDUCE_HALF"),
        "case-sensitive — uppercase must not match"
    );
    assert!(
        !is_partial_reduce_tag("risk_close:fast_track_reduce_half_extra"),
        "suffix must not match (substring guard)"
    );
    assert!(
        !is_partial_reduce_tag("risk_close:fast_track"),
        "fast_track CloseAll (full close) must not match"
    );
}
