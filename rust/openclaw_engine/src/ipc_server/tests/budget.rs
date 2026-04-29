//! Phase 4 (4-15) + E4-5 audit FUP: AI budget IPC handler tests.
//! Phase 4 (4-15) + E4-5 審計 FUP：AI 預算 IPC handler 測試。

use super::super::*;
use super::empty_budget_slot;

/// Slot empty → get_ai_budget_status fail-soft returns "uninitialized".
/// 槽位為空 → get_ai_budget_status fail-soft 回傳 "uninitialized"。
#[tokio::test]
async fn test_handle_get_ai_budget_status_uninitialized() {
    let slot = empty_budget_slot();
    let resp = handle_get_ai_budget_status(serde_json::json!(4150), &slot).await;
    assert!(resp.error.is_none(), "should fail-soft, not error");
    let result = resp.result.expect("result should be present");
    assert_eq!(result["status"], "uninitialized");
    assert_eq!(resp.id, serde_json::json!(4150));
}

/// Slot empty → update_ai_budget_config -32603 (fail-closed for writes).
/// 槽位為空 → update_ai_budget_config 回 -32603（寫入路徑 fail-closed）。
#[tokio::test]
async fn test_handle_update_ai_budget_config_uninitialized() {
    let slot = empty_budget_slot();
    let params = serde_json::json!({
        "scope": "teacher",
        "monthly_usd": 60.0,
        "updated_by": "operator"
    });
    let resp = handle_update_ai_budget_config(serde_json::json!(4151), &params, &slot).await;
    assert!(resp.error.is_some(), "must fail-closed when uninitialized");
    assert_eq!(resp.error.unwrap().code, ERR_INTERNAL);
}

/// Missing 'scope' / invalid 'monthly_usd' → -32602 invalid params.
/// 缺 'scope' 或 'monthly_usd' 不合法 → 回 -32602。
#[tokio::test]
async fn test_handle_update_ai_budget_config_invalid_params() {
    let slot = empty_budget_slot();
    // Missing scope / 缺 scope
    let p1 = serde_json::json!({ "monthly_usd": 60.0 });
    let r1 = handle_update_ai_budget_config(serde_json::json!(1), &p1, &slot).await;
    assert_eq!(r1.error.expect("err").code, -32602);

    // Negative monthly_usd / monthly_usd 為負
    let p2 = serde_json::json!({ "scope": "teacher", "monthly_usd": -1.0 });
    let r2 = handle_update_ai_budget_config(serde_json::json!(2), &p2, &slot).await;
    assert_eq!(r2.error.expect("err").code, -32602);

    // Empty scope / scope 空字串
    let p3 = serde_json::json!({ "scope": "", "monthly_usd": 10.0 });
    let r3 = handle_update_ai_budget_config(serde_json::json!(3), &p3, &slot).await;
    assert_eq!(r3.error.expect("err").code, -32602);
}

// ───────────────────────────────────────────────────────────────────────────
// E4-5 audit FUP: handler-level end-to-end JSON-RPC response regression tests
// for the `b5fa443` param_extractor adoption (handlers/budget.rs parts).
// E4-5 審計 FUP：`b5fa443` param_extractor 替換的 handler 端到端
// JSON-RPC response 回歸測試（handlers/budget.rs 部份）。
//
// EN: The adopter commit claims "error messages remain byte-for-byte
//     identical" but ships without handler-level happy / error regression
//     coverage. These tests close that gap: one happy path + one error path
//     per migrated handler with exact-string assertions on the error message
//     so future param renaming / helper refactors cannot silently change the
//     wire contract consumed by the Python pytest suite.
// 中：adopter commit 聲稱「錯誤訊息逐位元組保留」但未附 handler 層級的
//     happy / error 回歸測試。本節補齊：每個遷移 handler 1 happy + 1 error，
//     對錯誤訊息做逐字比對，避免未來改名 / helper refactor 靜默改變
//     Python pytest 依賴的 wire 契約。
// ───────────────────────────────────────────────────────────────────────────

// ── E4-5 Happy path: handle_update_ai_budget_config ───────────────────────
// ── E4-5 Happy 路徑：handle_update_ai_budget_config ──────────────────────

/// EN: With all params valid but slot uninitialized, the **parse step
///     succeeds** (param_extractor returns Ok for scope / monthly_usd /
///     optional updated_by) and we reach the slot check, which fails-closed
///     with ERR_INTERNAL. This proves the `require_str` + `require_non_negative_f64`
///     + `optional_str_or` happy path wiring actually flows through — if
///     one of those helpers were broken, we'd surface -32602 instead and
///     never reach the slot guard.
/// 中：所有參數合法但槽位未初始化時，param_extractor **解析成功**
///     （scope / monthly_usd 必填 + updated_by 可選），接著進入槽位檢查
///     fail-closed 回 ERR_INTERNAL。此測試證明 `require_str` +
///     `require_non_negative_f64` + `optional_str_or` 三個 helper 的
///     happy 路徑真的串通 — 任一 helper 壞會回 -32602 而非 -32603。
#[tokio::test]
async fn test_e4_5_handle_update_ai_budget_config_happy_parse_reaches_slot() {
    let slot = empty_budget_slot();
    let params = serde_json::json!({
        "scope": "layer2_scout",
        "monthly_usd": 42.5,
        "updated_by": "e4_5_regression"
    });
    let resp = handle_update_ai_budget_config(serde_json::json!(10001), &params, &slot).await;
    // Parse succeeded → progressed past param_extractor → hit slot guard.
    // 解析通過 → 走完 param_extractor → 命中槽位守衛。
    let err = resp
        .error
        .as_ref()
        .expect("uninitialized slot must fail-closed with ERR_INTERNAL, not -32602");
    assert_eq!(
        err.code, ERR_INTERNAL,
        "expected ERR_INTERNAL ({ERR_INTERNAL}) proving params parsed OK, got code={} msg={:?}",
        err.code, err.message
    );
    // Verify it's the specific slot-guard message, not a random ERR_INTERNAL.
    // 驗證是特定槽位守衛訊息而非隨意 -32603。
    assert_eq!(
        err.message, "budget tracker not initialized (DB pool unavailable?)",
        "ERR_INTERNAL message drifted — expected slot-guard exact text"
    );
    assert_eq!(resp.id, serde_json::json!(10001));
}

// ── E4-5 Error path: handle_update_ai_budget_config missing 'scope' ──────
// ── E4-5 錯誤路徑：handle_update_ai_budget_config 缺 'scope' ─────────────

/// EN: Missing `scope` → `require_str` short-circuits with the canonical
///     `"missing or empty 'scope' (string)"` (with the `(string)` suffix —
///     `update_ai_budget_config` uses `require_str`, NOT `require_str_with_msg`).
///     Byte-for-byte assertion catches any future drift in the helper
///     format string or the handler's choice of helper variant.
/// 中：缺 `scope` → `require_str` 短路回傳預設訊息
///     `"missing or empty 'scope' (string)"`（帶 `(string)` 尾綴 —
///     此 handler 用 `require_str`，不是 `require_str_with_msg`）。
///     逐字比對抓未來 helper format / 選擇變體的任何漂移。
#[tokio::test]
async fn test_e4_5_handle_update_ai_budget_config_error_missing_scope_exact_message() {
    let slot = empty_budget_slot();
    let params = serde_json::json!({
        // scope intentionally absent / 故意不傳 scope
        "monthly_usd": 10.0
    });
    let resp = handle_update_ai_budget_config(serde_json::json!(10002), &params, &slot).await;
    let err = resp
        .error
        .expect("missing 'scope' must produce an error response");
    assert_eq!(
        err.code, -32602,
        "expected ERR_INVALID_PARAMS, got {}",
        err.code
    );
    // Byte-for-byte — THIS is the load-bearing assertion per the audit finding.
    // If this message changes to e.g. "'scope' is missing" or drops the
    // "(string)" suffix, Python pytest breaks on the wire contract.
    // 逐字比對 — audit finding 的關鍵斷言。訊息若改成
    // "'scope' is missing" 或掉 "(string)" 尾綴，Python pytest wire 契約就壞。
    assert_eq!(
        err.message, "missing or empty 'scope' (string)",
        "byte-identity drift: error message must exactly match legacy handler contract"
    );
    assert_eq!(resp.id, serde_json::json!(10002));
    assert!(resp.result.is_none());
}

// ── E4-5 Happy path: handle_record_ai_usage ──────────────────────────────
// ── E4-5 Happy 路徑：handle_record_ai_usage ──────────────────────────────

/// EN: All required string params (scope / provider / model) present;
///     tokens_in/out omitted (optional, defaults to 0 via `optional_u64 →
///     unwrap_or(0)`); purpose omitted (defaults to `"layer2_external"` via
///     `optional_str_or`). Parse must reach the slot guard which fails-
///     closed with ERR_INTERNAL (same pattern as budget happy test).
///     This proves the 3 × `require_str_with_msg` + `optional_u64` + two
///     `optional_str_or` wiring is intact.
/// 中：必填 scope / provider / model 齊備，tokens_in/out 省略（走
///     `optional_u64.unwrap_or(0)`），purpose 省略（走 `optional_str_or`
///     預設 `"layer2_external"`）。解析成功後觸槽位守衛 ERR_INTERNAL。
///     證明 3 × `require_str_with_msg` + `optional_u64` + 兩個
///     `optional_str_or` 全部接線無損。
#[tokio::test]
async fn test_e4_5_handle_record_ai_usage_happy_parse_reaches_slot() {
    let slot = empty_budget_slot();
    let params = serde_json::json!({
        "scope": "layer2_scout",
        "provider": "anthropic",
        "model": "claude-4-5-sonnet",
        // tokens_in/tokens_out/purpose intentionally omitted to exercise
        // the optional_* defaults / 故意省略 optional_* 欄位驗預設接線
    });
    let resp = handle_record_ai_usage(serde_json::json!(10003), &params, &slot).await;
    let err = resp
        .error
        .as_ref()
        .expect("uninitialized slot must fail-closed, proving parse succeeded");
    assert_eq!(
        err.code, ERR_INTERNAL,
        "expected ERR_INTERNAL (proves all require_str_with_msg parsed OK), \
         got code={} msg={:?}",
        err.code, err.message
    );
    assert_eq!(
        err.message, "budget tracker not initialized (DB pool unavailable?)",
        "slot-guard message drifted"
    );
    assert_eq!(resp.id, serde_json::json!(10003));
}

// ── E4-5 Error path: handle_record_ai_usage missing 'scope' ──────────────
// ── E4-5 錯誤路徑：handle_record_ai_usage 缺 'scope' ─────────────────────

/// EN: Missing `scope` → `require_str_with_msg(..., "missing 'scope'")`
///     short-circuits with the **short-form** message — NO `(string)`
///     suffix. This is the exact byte-for-byte form the legacy
///     `handlers.rs` hand-written path produced before `b5fa443`.
///     Python pytest asserts on this short form; drift would silently
///     break the external contract.
/// 中：缺 `scope` → `require_str_with_msg(..., "missing 'scope'")` 短路
///     回傳 **短訊息** — 無 `(string)` 尾綴。此為 `b5fa443` 前 legacy
///     hand-written 路徑的精確 byte-for-byte 格式，Python pytest 對此
///     斷言；漂移會靜默破壞外部契約。
#[tokio::test]
async fn test_e4_5_handle_record_ai_usage_error_missing_scope_short_form_message() {
    let slot = empty_budget_slot();
    let params = serde_json::json!({
        // scope intentionally absent / 故意不傳
        "provider": "anthropic",
        "model": "claude-4-5-sonnet"
    });
    let resp = handle_record_ai_usage(serde_json::json!(10004), &params, &slot).await;
    let err = resp
        .error
        .expect("missing 'scope' must produce an error response");
    assert_eq!(err.code, -32602, "expected ERR_INVALID_PARAMS");
    // CRITICAL BYTE-IDENTITY: short form, no "(string)" suffix, single quotes
    // around scope. Any reformatting (e.g. "missing scope" / "scope: missing"
    // / adding "(string)") breaks the Python wire contract.
    // 關鍵逐字比對：短形式，無 "(string)" 尾綴，scope 帶單引號。任何
    // 重排（"missing scope" / "scope: missing" / 加 "(string)"）都壞 Python 契約。
    assert_eq!(
        err.message, "missing 'scope'",
        "byte-identity drift: require_str_with_msg short-form must match legacy exact text"
    );
    assert_eq!(resp.id, serde_json::json!(10004));
    assert!(resp.result.is_none());
}
