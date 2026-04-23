//! E4-5 audit FUP: handle_update_risk_config handler-level regression tests.
//! E4-5 審計 FUP：handle_update_risk_config handler 層級回歸測試。
//!
//! EN: Covers the `b5fa443` param_extractor adoption for `handlers/risk.rs`.
//!     One happy path + one error path (empty / wrong-type params) with
//!     byte-for-byte assertions on the returned message so future helper
//!     refactors cannot silently break the Python pytest wire contract.
//! 中：涵蓋 `b5fa443` 在 `handlers/risk.rs` 的 param_extractor 替換。
//!     1 happy + 1 error（空 / 型別錯），對回傳訊息做逐字比對，避免
//!     未來 helper refactor 靜默破壞 Python pytest wire 契約。

use super::super::*;

/// E4-5 test helper: spawn a fake pipeline consumer that **acknowledges**
/// every `UpdateRiskConfig` (drains the channel, does nothing).
/// The handler does not wait for a reply — it only checks that the send
/// succeeded — so the consumer just needs to keep the receiver alive to
/// avoid the send returning `Err(SendError)`. This keeps the test pure
/// handler-level: the response we assert on is built inside
/// `handle_update_risk_config` itself, NOT stubbed.
///
/// E4-5 測試輔助：啟動 fake pipeline consumer，對每個 `UpdateRiskConfig`
/// 只 drain 不處理。handler 不等待回應、僅檢查 send 成功，故 consumer
/// 僅需保持 receiver 存活。這樣 response assertion 來自 handler 內部
/// 真實邏輯，非 stub 回填。
fn setup_risk_update_drain_channel() -> tokio::sync::mpsc::UnboundedSender<PipelineCommand> {
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<PipelineCommand>();
    tokio::spawn(async move {
        while let Some(cmd) = rx.recv().await {
            // drain UpdateRiskConfig (and ignore any other variant) / 只 drain
            if let PipelineCommand::UpdateRiskConfig { .. } = cmd {
                // no-op — fire-and-forget command / 即發即忘，handler 已回 success
            }
        }
    });
    tx
}

// ── E4-5 Happy path: handle_update_risk_config ───────────────────────────
// ── E4-5 Happy 路徑：handle_update_risk_config ───────────────────────────

/// EN: Single risk param (`hard_stop_pct`) suffices to pass the `has_any`
///     gate; the handler sends `UpdateRiskConfig` on the channel and
///     returns `{"updated": true}`. This proves `optional_f64` parses the
///     field, the `has_any` aggregation recognises at least one Some, and
///     the channel send succeeds — all 11 `optional_*` replacements in
///     this handler are exercised through the default-None path plus one
///     Some path.
/// 中：單一 risk 參數（`hard_stop_pct`）即可通過 `has_any` 門；handler
///     經通道送 `UpdateRiskConfig` 並回 `{"updated": true}`。證明
///     `optional_f64` 正確解析、`has_any` 正確識別 ≥1 Some、通道 send
///     成功 — 11 處 `optional_*` 替換走過 default-None 路徑 + 一次 Some。
#[tokio::test]
async fn test_e4_5_handle_update_risk_config_happy_single_param_returns_updated_true() {
    let tx = setup_risk_update_drain_channel();
    let tx_opt = Some(tx);
    let params = serde_json::json!({
        "hard_stop_pct": 0.02
    });
    let resp = handle_update_risk_config(serde_json::json!(10005), &tx_opt, &params).await;
    assert!(
        resp.error.is_none(),
        "happy path must not error: {:?}",
        resp.error
    );
    let result = resp.result.expect("result must be present");
    assert_eq!(
        result,
        serde_json::json!({"updated": true}),
        "response body must match legacy byte-for-byte"
    );
    assert_eq!(resp.id, serde_json::json!(10005));
}

// ── E4-5 Error path: handle_update_risk_config no-param / wrong-type ─────
// ── E4-5 錯誤路徑：handle_update_risk_config 無參 / 型別錯 ───────────────

/// EN: Empty params `{}` (or any payload where every `optional_*` returns
///     None) fails the `has_any` aggregation → ERR_INVALID_REQUEST (-32600)
///     with `"need at least one risk parameter"`. This is the designed
///     error path: every `optional_*` returning None proves the helpers
///     handle absence correctly (no panic, no surprise -32602 from a
///     `require_*` misuse). A wrong-type value (e.g. `hard_stop_pct: "str"`)
///     also collapses to None via `serde_json::Value::as_f64() -> None` and
///     ends up here — we cover both inputs to prove the single `has_any`
///     path handles missing AND coerced-to-None uniformly.
/// 中：空參 `{}`（或所有 `optional_*` 皆 None）走 `has_any` 失敗路徑 →
///     ERR_INVALID_REQUEST (-32600) 訊息 `"need at least one risk parameter"`。
///     此為設計錯誤路徑：每個 `optional_*` 回 None 證 helper 正確處理
///     缺失（不 panic、不誤回 -32602）。型別錯（例 `hard_stop_pct: "str"`）
///     經 `as_f64() -> None` 亦落入此路徑 — 驗兩種輸入統一收斂。
#[tokio::test]
async fn test_e4_5_handle_update_risk_config_error_empty_params_byte_identical_message() {
    let tx = setup_risk_update_drain_channel();
    let tx_opt = Some(tx);
    let params = serde_json::json!({});
    let resp = handle_update_risk_config(serde_json::json!(10006), &tx_opt, &params).await;
    let err = resp
        .error
        .expect("empty params must produce ERR_INVALID_REQUEST");
    assert_eq!(err.code, ERR_INVALID_REQUEST, "expected -32600");
    // Byte-identity: legacy message exactly. "at least one risk parameter"
    // (no trailing period, no "required"). Python pytest depends on this.
    // 逐字比對：legacy 原訊息（無句點、無 "required"）。Python pytest 依賴。
    assert_eq!(
        err.message, "need at least one risk parameter",
        "byte-identity drift: update_risk_config no-param message must match legacy exact text"
    );
    assert_eq!(resp.id, serde_json::json!(10006));

    // Wrong-type input collapses to None via as_f64() and hits the same path.
    // 型別錯 → as_f64() = None → 同路徑。
    let bad_params = serde_json::json!({
        "hard_stop_pct": "not_a_number",
        "max_drawdown_pct": true,
        "boot_cooldown_ms": 3.14
    });
    let resp2 = handle_update_risk_config(serde_json::json!(10007), &tx_opt, &bad_params).await;
    let err2 = resp2
        .error
        .expect("wrong-type params must collapse to None and hit has_any");
    assert_eq!(err2.code, ERR_INVALID_REQUEST);
    assert_eq!(
        err2.message, "need at least one risk parameter",
        "wrong-type inputs must route to the same has_any message (optional_* = None semantics)"
    );
}
