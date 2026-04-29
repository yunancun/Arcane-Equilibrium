//! JSON-RPC params extraction & validation helpers (E5-P1-5 orphan §九).
//! JSON-RPC 參數提取與驗證輔助（E5-P1-5，§九 孤兒抽取）。
//!
//! MODULE_NOTE (EN):
//!   ``handlers.rs`` contains 30+ near-identical snippets of the form:
//!
//!   ```ignore
//!   let scope = match params.get("scope").and_then(|v| v.as_str()) {
//!       Some(s) if !s.is_empty() => s.to_string(),
//!       _ => return JsonRpcResponse::error(id, ERR_INVALID_PARAMS,
//!                "missing or empty 'scope' (string)"),
//!   };
//!   ```
//!
//!   This module extracts those into typed helpers returning
//!   ``Result<T, JsonRpcResponse>`` so a handler can write:
//!
//!   ```ignore
//!   let scope = require_str(params, "scope", id.clone())?;
//!   let monthly_usd = require_non_negative_f64(params, "monthly_usd", id.clone())?;
//!   let updated_by = optional_str(params, "updated_by").unwrap_or("ipc");
//!   ```
//!
//!   with the ``?`` operator short-circuiting to the same ``JsonRpcResponse``
//!   error payloads as the hand-written path.  Error messages are preserved
//!   **byte-for-byte** to keep the external contract stable (python side tests
//!   assert on exact text).
//!
//!   Cross-wave coordination: this file is brand-new and nothing in
//!   ``handlers.rs`` currently calls it.  We intentionally leave
//!   ``handlers.rs`` untouched to avoid conflicting with the parallel
//!   E5-P1-3 handlers split.  Re-exports at the bottom of this file plus
//!   ``pub(super) use`` in ``ipc_server/mod.rs`` make the helpers available
//!   to future handler migrations without any further scaffolding.
//!
//! MODULE_NOTE (中):
//!   ``handlers.rs`` 裡有 30+ 段幾乎完全相同的片段如上 EN 範例所示。本模組
//!   將它們抽成回傳 ``Result<T, JsonRpcResponse>`` 的型別化輔助函數，讓
//!   handler 可以透過 ``?`` 短路，與舊寫法產生**逐位元組一致**的
//!   ``JsonRpcResponse`` 錯誤。錯誤訊息故意保持完全相同，Python 測試會
//!   對字串精確比對。
//!
//!   跨波次協調：本檔案全新，``handlers.rs`` 目前尚未呼叫，亦不修改
//!   ``handlers.rs`` 內容，以避免與並行進行的 E5-P1-3 handlers 拆分衝突。
//!   檔尾 re-export + ``ipc_server/mod.rs`` 的 ``pub(super) use`` 讓後續
//!   handler 遷移可直接採用，無需再加任何連線。
//!
//! Safety guarantees / 安全保證:
//!   - Fail-closed: missing/invalid params always produce an error response;
//!     no silent defaults unless caller explicitly opts into ``optional_*``.
//!   - Byte-for-byte message compatibility with legacy handlers.rs code.
//!   - No I/O, no async — pure ``serde_json::Value`` inspection.

// E5-P1-5-FUP: file-level `#![allow(dead_code)]` removed now that the first
//         adopters (`handlers/budget.rs` + `handlers/risk.rs`) consume the
//         canonical `require_*` / `optional_*` helpers.  The three helpers
//         that no handler consumes yet (`require_f64`, `require_bool`,
//         `optional_str`, `internal_error`) carry individual
//         `#[allow(dead_code)]` + TODO markers so new call sites can adopt
//         them drop-in without re-enabling the module-level suppression.
// E5-P1-5-FUP：首批採用點（`handlers/budget.rs` + `handlers/risk.rs`）
//         落地後移除檔案級 `#![allow(dead_code)]`；尚未被消費的
//         `require_f64` / `require_bool` / `optional_str` / `internal_error`
//         改加函數級 `#[allow(dead_code)]` + TODO，新 call site 採用時可
//         即刻移除，避免再次打開檔案級壓制。

use super::{JsonRpcResponse, ERR_INTERNAL};
use serde_json::Value;

/// JSON-RPC 2.0 "Invalid params" error code (mirrored from handlers.rs).
/// JSON-RPC 2.0「參數無效」錯誤碼（與 handlers.rs 一致）。
pub(crate) const ERR_INVALID_PARAMS: i64 = -32602;

// ── Required string / 必填字串 ────────────────────────────────────────────

/// Require a non-empty string param, or return an error response.
/// 要求必填非空字串參數；缺失則回錯誤回應。
///
/// Produces the canonical message ``"missing or empty '<key>' (string)"`` —
/// identical to hand-written sites in ``handlers.rs``.
/// 錯誤訊息固定為 ``"missing or empty '<key>' (string)"``，與 handlers.rs
/// 手寫點完全一致。
pub(crate) fn require_str(
    params: &Value,
    key: &str,
    id: Value,
) -> Result<String, JsonRpcResponse> {
    match params.get(key).and_then(|v| v.as_str()) {
        Some(s) if !s.is_empty() => Ok(s.to_string()),
        _ => Err(JsonRpcResponse::error(
            id,
            ERR_INVALID_PARAMS,
            format!("missing or empty '{key}' (string)"),
        )),
    }
}

/// Require a string param with a caller-supplied error message.
/// 要求必填字串參數（呼叫方指定錯誤訊息）。
///
/// Used when legacy handler has a non-default message (e.g. simply
/// ``"missing 'scope'"`` without the ``(string)`` suffix).
/// 對應舊 handler 自訂訊息（例如只寫 ``"missing 'scope'"`` 不加 ``(string)``）。
pub(crate) fn require_str_with_msg(
    params: &Value,
    key: &str,
    id: Value,
    missing_msg: &str,
) -> Result<String, JsonRpcResponse> {
    match params.get(key).and_then(|v| v.as_str()) {
        Some(s) if !s.is_empty() => Ok(s.to_string()),
        _ => Err(JsonRpcResponse::error(
            id,
            ERR_INVALID_PARAMS,
            missing_msg.to_string(),
        )),
    }
}

/// Fetch an optional string param, returning ``None`` if absent / empty.
/// 取可選字串參數；缺失或空字串回 ``None``。
// TODO(E5-P1-5-FUP-2): no handler currently distinguishes between "absent" and
//     "present but empty" for optional strings (all call sites either use a
//     default via `optional_str_or` or short-circuit via `require_str`).
//     Remove the attribute once a handler adopts this two-state variant.
// TODO(E5-P1-5-FUP-2)：目前 handlers 對可選字串都用 `optional_str_or`（帶預設）
//     或 `require_str`（必填），沒有 call site 需要區分「缺失」vs「空字串」。
//     待有 handler 採用此二態版本後即可移除本屬性。
#[allow(dead_code)]
pub(crate) fn optional_str<'a>(params: &'a Value, key: &str) -> Option<&'a str> {
    params.get(key).and_then(|v| v.as_str()).filter(|s| !s.is_empty())
}

/// Fetch an optional string with a default fallback.
/// 取可選字串，缺失時回退到預設值。
pub(crate) fn optional_str_or<'a>(
    params: &'a Value,
    key: &str,
    default: &'a str,
) -> &'a str {
    optional_str(params, key).unwrap_or(default)
}

// ── Numeric params / 數值參數 ─────────────────────────────────────────────

/// Require a finite ``f64`` param; error if missing or not finite.
/// 要求必填有限 ``f64`` 參數；缺失或非有限值即回錯誤。
// TODO(E5-P1-5-FUP-2): no handler currently needs an unconstrained required
//     f64 (existing risk/budget sites use either `require_non_negative_f64`
//     or two-state `optional_f64`).  Drop the attribute when adopted.
// TODO(E5-P1-5-FUP-2)：目前 handlers 僅用 `require_non_negative_f64` 或
//     二態 `optional_f64`；首個 unconstrained 必填 f64 call site 落地後移除。
#[allow(dead_code)]
pub(crate) fn require_f64(
    params: &Value,
    key: &str,
    id: Value,
) -> Result<f64, JsonRpcResponse> {
    match params.get(key).and_then(|v| v.as_f64()) {
        Some(v) if v.is_finite() => Ok(v),
        _ => Err(JsonRpcResponse::error(
            id,
            ERR_INVALID_PARAMS,
            format!("missing or invalid '{key}' (must be finite f64)"),
        )),
    }
}

/// Require a finite ``f64 >= 0.0`` param; mirrors the ``monthly_usd`` handler.
/// 要求必填有限非負 ``f64`` 參數；對應 ``monthly_usd`` 處理器的契約。
pub(crate) fn require_non_negative_f64(
    params: &Value,
    key: &str,
    id: Value,
) -> Result<f64, JsonRpcResponse> {
    match params.get(key).and_then(|v| v.as_f64()) {
        Some(v) if v.is_finite() && v >= 0.0 => Ok(v),
        _ => Err(JsonRpcResponse::error(
            id,
            ERR_INVALID_PARAMS,
            format!("missing or invalid '{key}' (must be finite f64 >= 0)"),
        )),
    }
}

/// Fetch an optional ``f64`` with an ``and_then(as_f64)`` one-liner.
/// 以 ``and_then(as_f64)`` 取可選 ``f64``。
pub(crate) fn optional_f64(params: &Value, key: &str) -> Option<f64> {
    params.get(key).and_then(|v| v.as_f64())
}

/// Fetch an optional ``u64``; legacy code uses this for millisecond-scale
/// timestamps and cooldown values.
/// 以 ``and_then(as_u64)`` 取可選 ``u64``（舊程式碼多用於毫秒級時間戳）。
pub(crate) fn optional_u64(params: &Value, key: &str) -> Option<u64> {
    params.get(key).and_then(|v| v.as_u64())
}

// ── Booleans / 布林值 ─────────────────────────────────────────────────────

/// Require a boolean param; error if missing or wrong type.
/// 要求必填布林值；缺失或型別錯誤回錯誤回應。
// TODO(E5-P1-5-FUP-2): risk.rs uses `optional_bool` (h0_shadow_mode is an
//     optional toggle).  Wire this once a handler requires a non-optional
//     bool (e.g. a dry-run flag that must be explicit).
// TODO(E5-P1-5-FUP-2)：risk.rs 用 `optional_bool`（如 h0_shadow_mode 可選）。
//     未來需要強制指定的布林（例如 dry-run flag）時再採用此必填版本。
#[allow(dead_code)]
pub(crate) fn require_bool(
    params: &Value,
    key: &str,
    id: Value,
) -> Result<bool, JsonRpcResponse> {
    match params.get(key).and_then(|v| v.as_bool()) {
        Some(v) => Ok(v),
        None => Err(JsonRpcResponse::error(
            id,
            ERR_INVALID_PARAMS,
            format!("missing or invalid '{key}' (bool)"),
        )),
    }
}

/// Fetch an optional boolean with ``as_bool``.
/// 以 ``and_then(as_bool)`` 取可選布林值。
pub(crate) fn optional_bool(params: &Value, key: &str) -> Option<bool> {
    params.get(key).and_then(|v| v.as_bool())
}

// ── Internal errors / 內部錯誤便捷建構子 ──────────────────────────────────

/// Build an ``ERR_INTERNAL`` response — common shorthand when a DB write or
/// channel send fails inside a handler.
/// 建構 ``ERR_INTERNAL`` 錯誤回應 — handler 內 DB 寫入或 channel 失敗常用。
// TODO(E5-P1-5-FUP-2): budget.rs keeps its inline `JsonRpcResponse::error(id,
//     ERR_INTERNAL, ...)` calls because the `format!(...)` message paths
//     differ per-call.  Adopt `internal_error` when a handler has a static
//     error string to keep the helper exercised.
// TODO(E5-P1-5-FUP-2)：budget.rs 各 `ERR_INTERNAL` 訊息為動態 `format!`，保留
//     內嵌調用；未來有靜態錯誤訊息的 handler 可用此便捷建構子取代。
#[allow(dead_code)]
pub(crate) fn internal_error(id: Value, message: impl Into<String>) -> JsonRpcResponse {
    JsonRpcResponse::error(id, ERR_INTERNAL, message.into())
}

// ── Tests / 測試 ──────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn rid() -> Value {
        json!(42)
    }

    #[test]
    fn require_str_accepts_non_empty() {
        let p = json!({"scope": "teacher"});
        assert_eq!(require_str(&p, "scope", rid()).unwrap(), "teacher");
    }

    #[test]
    fn require_str_rejects_missing() {
        let p = json!({});
        let err = require_str(&p, "scope", rid()).unwrap_err();
        let code = err.error.as_ref().unwrap().code;
        assert_eq!(code, ERR_INVALID_PARAMS);
        assert_eq!(
            err.error.as_ref().unwrap().message,
            "missing or empty 'scope' (string)"
        );
    }

    #[test]
    fn require_str_rejects_empty() {
        let p = json!({"scope": ""});
        let err = require_str(&p, "scope", rid()).unwrap_err();
        assert_eq!(err.error.as_ref().unwrap().code, ERR_INVALID_PARAMS);
    }

    #[test]
    fn require_str_rejects_non_string() {
        let p = json!({"scope": 123});
        let err = require_str(&p, "scope", rid()).unwrap_err();
        assert_eq!(
            err.error.as_ref().unwrap().message,
            "missing or empty 'scope' (string)"
        );
    }

    #[test]
    fn require_str_with_msg_uses_custom_text() {
        let p = json!({});
        let err = require_str_with_msg(&p, "scope", rid(), "missing 'scope'").unwrap_err();
        assert_eq!(err.error.as_ref().unwrap().message, "missing 'scope'");
    }

    #[test]
    fn optional_str_returns_none_for_empty_or_missing() {
        let p = json!({"a": "", "b": "x"});
        assert_eq!(optional_str(&p, "a"), None);
        assert_eq!(optional_str(&p, "missing"), None);
        assert_eq!(optional_str(&p, "b"), Some("x"));
    }

    #[test]
    fn optional_str_or_falls_back() {
        let p = json!({});
        assert_eq!(optional_str_or(&p, "updated_by", "ipc"), "ipc");
        let p2 = json!({"updated_by": "operator"});
        assert_eq!(optional_str_or(&p2, "updated_by", "ipc"), "operator");
    }

    #[test]
    fn require_non_negative_f64_accepts_zero_and_positive() {
        let p = json!({"x": 0.0, "y": 12.5});
        assert_eq!(require_non_negative_f64(&p, "x", rid()).unwrap(), 0.0);
        assert_eq!(require_non_negative_f64(&p, "y", rid()).unwrap(), 12.5);
    }

    #[test]
    fn require_non_negative_f64_rejects_negative() {
        let p = json!({"x": -1.0});
        let err = require_non_negative_f64(&p, "x", rid()).unwrap_err();
        assert_eq!(
            err.error.as_ref().unwrap().message,
            "missing or invalid 'x' (must be finite f64 >= 0)"
        );
    }

    #[test]
    fn require_non_negative_f64_rejects_nan() {
        // f64 NaN serialised as null by serde — still covered by as_f64() None.
        // NaN 經 serde 會序列化為 null；as_f64() 回 None，會進入 err 路徑。
        let p: Value = serde_json::from_str(r#"{"x": null}"#).unwrap();
        assert!(require_non_negative_f64(&p, "x", rid()).is_err());
    }

    #[test]
    fn require_f64_rejects_missing() {
        let p = json!({});
        let err = require_f64(&p, "ratio", rid()).unwrap_err();
        assert_eq!(
            err.error.as_ref().unwrap().message,
            "missing or invalid 'ratio' (must be finite f64)"
        );
    }

    #[test]
    fn require_bool_accepts_true_false() {
        let p = json!({"enabled": true, "active": false});
        assert!(require_bool(&p, "enabled", rid()).unwrap());
        assert!(!require_bool(&p, "active", rid()).unwrap());
    }

    #[test]
    fn require_bool_rejects_non_bool() {
        let p = json!({"enabled": "yes"});
        let err = require_bool(&p, "enabled", rid()).unwrap_err();
        assert_eq!(
            err.error.as_ref().unwrap().message,
            "missing or invalid 'enabled' (bool)"
        );
    }

    #[test]
    fn optional_bool_and_optional_u64_return_none_for_missing() {
        let p = json!({});
        assert_eq!(optional_bool(&p, "x"), None);
        assert_eq!(optional_u64(&p, "y"), None);
    }

    #[test]
    fn internal_error_has_correct_code_and_message() {
        let resp = internal_error(rid(), "boom");
        let err = resp.error.as_ref().unwrap();
        assert_eq!(err.code, ERR_INTERNAL);
        assert_eq!(err.message, "boom");
    }

    // ── E5-P1-5-FUP: adopter-level tests ─────────────────────────────────
    // ── E5-P1-5-FUP：採用點層級單測 ─────────────────────────────────────
    //
    // EN: the helpers below back the newly-migrated `handlers/budget.rs` and
    //     `handlers/risk.rs` call sites.  Adding explicit happy / error path
    //     tests here makes the contract with those handlers self-evident and
    //     guards against future edits that would silently change the JSON-RPC
    //     error payload.
    // 中：以下輔助函式承載剛遷移的 `handlers/budget.rs` 與 `handlers/risk.rs`
    //     call site。補上 happy / error 雙路徑單測使其對 handler 的契約清晰，
    //     並避免未來改動靜默改變 JSON-RPC error payload。

    #[test]
    fn require_str_adopter_happy_budget_scope() {
        // Mirrors `handle_update_ai_budget_config` happy path.
        // 對應 `handle_update_ai_budget_config` 的 happy 路徑。
        let p = json!({"scope": "layer2_scout", "monthly_usd": 10.0});
        assert_eq!(require_str(&p, "scope", rid()).unwrap(), "layer2_scout");
    }

    #[test]
    fn require_str_adopter_error_preserves_canonical_message() {
        // Byte-identity on the error message is load-bearing for the Python
        // test suite (asserts on exact text).
        // 錯誤訊息的逐位元組一致對 Python 測試是關鍵契約（對字串精確比對）。
        let p = json!({"monthly_usd": 5.0});
        let err = require_str(&p, "scope", rid()).unwrap_err();
        let body = err.error.as_ref().unwrap();
        assert_eq!(body.code, ERR_INVALID_PARAMS);
        assert_eq!(body.message, "missing or empty 'scope' (string)");
    }

    #[test]
    fn optional_u64_adopter_happy_tokens_in() {
        // Mirrors `handle_record_ai_usage` token-count extraction.
        // 對應 `handle_record_ai_usage` 的 token 數抽取。
        let p = json!({"tokens_in": 12_345u64});
        assert_eq!(optional_u64(&p, "tokens_in"), Some(12_345));
    }

    #[test]
    fn optional_u64_adopter_missing_falls_to_none_for_unwrap_or_zero() {
        // Legacy handlers.rs did `.and_then(as_u64).unwrap_or(0)`; the migrated
        // call site does `optional_u64(...).unwrap_or(0)` — verify the
        // `None`-on-missing branch so the fallback is identical.
        // 舊 handlers.rs 寫 `.and_then(as_u64).unwrap_or(0)`；遷移後為
        // `optional_u64(...).unwrap_or(0)`。驗證缺失時回 `None`，fallback 等義。
        let p = json!({});
        assert_eq!(optional_u64(&p, "tokens_in"), None);
        assert_eq!(optional_u64(&p, "tokens_in").unwrap_or(0) as u32, 0u32);
    }

    #[test]
    fn optional_u64_adopter_rejects_negative_and_float() {
        // serde_json `as_u64()` is `None` for negatives and non-integers; this
        // matches the legacy `.and_then(|v| v.as_u64())` behaviour so the
        // downstream `unwrap_or(0)` collapses suspicious inputs to zero.
        // serde_json `as_u64()` 對負數與非整數回 `None`，與舊 `.and_then(as_u64)`
        // 一致；下游 `unwrap_or(0)` 將可疑輸入歸零。
        let p = json!({"a": -1, "b": 3.14});
        assert_eq!(optional_u64(&p, "a"), None);
        assert_eq!(optional_u64(&p, "b"), None);
    }
}
