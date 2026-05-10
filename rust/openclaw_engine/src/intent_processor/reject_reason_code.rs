//! W6-3c (V086): reject reason code mapping — producer-side string→enum mapping.
//! W6-3c (V086)：reject reason code 映射 — producer 端 string→enum 對應。
//!
//! MODULE_NOTE (中):
//!   producer 端把 free-form `reject_reason: &str`（已被 `RejectionCode::format()`
//!   或 caller 自行構造的拒絕字串）映射到 V086 §4.1 規範的 12 enum 之一，
//!   寫進 `learning.decision_features.reject_reason_code`。
//!
//!   evaluation order **必須與 V086 SQL backfill CASE WHEN 鏡像**：
//!   - ATR unavailable 必先於 JS-demo / cost_gate_other（前者是 SEC-11 fail-closed
//!     特殊 signal，與 legacy cost_gate 語義不同，per W6-3b A3 拍板）
//!   - JS-demo 必先於 generic cost_gate_other（避免被 prefix-only "cost_gate" 誤判）
//!   - symbol_blocklist 必先於 risk_gate_other（嵌入在 risk_gate 字串內，per V086 line 329）
//!   - 任何不匹配的 reason → 'reject_other' catch-all
//!
//!   Source spec：
//!     - PA W6-3b enum spec final
//!       docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_3b_enum_spec_final_pa_decision.md
//!     - V086 SQL CASE WHEN line 316-333（reject path）
//!       sql/migrations/V086__governance_reject_close_reason_code.sql
//!
//!   不變式 / Invariants:
//!     - 此函式必為純函式（&str → &'static str），無 IO，無 panic
//!     - 12 enum 為 hardcoded slice；新增 enum 必同步改 V086 + 此函式 + 對應單測
//!     - 此函式 byte-identical SQL backfill 行為（同樣輸入產同樣 enum 輸出）

use std::borrow::Cow;

/// W6-3c V086 12 enum reject reason codes（11 + 1 catch-all）。
///
/// 對齊 V086 SQL line 251-263 chk_reject_reason_code_enum 12 字面值，順序鎖死。
/// 任何修改必同步：(1) 此 slice (2) V086 SQL CHECK constraint (3) `map_reject_reason_to_code()`。
pub const REJECT_REASON_CODE_ENUM: &[&str] = &[
    "cost_gate_js_demo_negative_edge",
    "cost_gate_atr_unavailable",
    "cost_gate_other",
    "duplicate_position",
    "direction_conflict",
    "position_count_limit",
    "scanner_market_gate",
    "scanner_opportunity_canary",
    "drawdown_breach",
    "symbol_blocklist",
    "risk_gate_other",
    "reject_other",
];

/// 把 producer 端 free-form `reject_reason: &str` 映射到 V086 §4.1 12 enum 之一。
///
/// evaluation order 與 V086 SQL `UPDATE ... SET reject_reason_code = CASE WHEN ...`
/// 鏡像（line 316-333）。任何修改必同步 V086 SQL；E2 review 必比對。
///
/// # Arguments
/// - `reason`: producer 端的 reject 字串（通常為 `RejectionCode::format()` 輸出，
///   或 caller 直接構造的字面字串如 "scanner_market_gate: ..." / "drawdown_breach"）
///
/// # Returns
/// - `&'static str`：12 enum 之一；不匹配走 `reject_other` catch-all
pub fn map_reject_reason_to_code(reason: &str) -> &'static str {
    // ── 鏡像 V086 SQL line 316-333 evaluation order ──
    //
    // 注意：Rust regex / glob 不在 hot path 用。SQL 用的是 `LIKE 'pattern%'` (prefix)
    // 與 `~ 'regex'`；此函式對應 Rust `starts_with()` 與 `contains()`，語義相同。

    // (1) ATR unavailable 必先於 JS-demo / cost_gate_other
    // V086 SQL: rv.reason ~ 'cost_gate.*ATR unavailable'
    // RejectionCode: "cost_gate: ATR unavailable (fail-closed, SEC-11)"
    if reason.contains("cost_gate") && reason.contains("ATR unavailable") {
        return "cost_gate_atr_unavailable";
    }

    // (2) cost_gate(JS-demo) 必先於 generic cost_gate_other
    // V086 SQL: rv.reason LIKE 'cost_gate(JS-demo)%'
    // RejectionCode: "cost_gate(JS-demo): edge=... < threshold=..." 等
    if reason.starts_with("cost_gate(JS-demo)") {
        return "cost_gate_js_demo_negative_edge";
    }

    // (3) 其他 cost_gate*（含 JS / JS-live 等變體 + generic cost_gate）
    // V086 SQL: rv.reason LIKE 'cost_gate%'
    if reason.starts_with("cost_gate") {
        return "cost_gate_other";
    }

    // (4) duplicate_position
    // V086 SQL: rv.reason LIKE 'duplicate_position%'
    // RejectionCode: "duplicate_position: SYMBOL already LONG/SHORT QTY"
    if reason.starts_with("duplicate_position") {
        return "duplicate_position";
    }

    // (5) direction_conflict
    // V086 SQL: rv.reason LIKE 'direction_conflict%'
    if reason.starts_with("direction_conflict") {
        return "direction_conflict";
    }

    // (6) position_count_limit
    // V086 SQL: rv.reason LIKE 'position_count%'
    if reason.starts_with("position_count") {
        return "position_count_limit";
    }

    // (7) scanner_market_gate
    // V086 SQL: rv.reason LIKE 'scanner_market_gate%'
    if reason.starts_with("scanner_market_gate") {
        return "scanner_market_gate";
    }

    // (8) scanner_opportunity_canary
    // V086 SQL: rv.reason LIKE 'scanner_opportunity_canary%'
    if reason.starts_with("scanner_opportunity_canary") {
        return "scanner_opportunity_canary";
    }

    // (9) drawdown_breach
    // V086 SQL: rv.reason LIKE 'drawdown_breach%'
    if reason.starts_with("drawdown_breach") {
        return "drawdown_breach";
    }

    // (10) symbol_blocklist 必先於 risk_gate_other（嵌入在 risk_gate 字串內）
    // V086 SQL: rv.reason ~ 'blocked by per_strategy\.\w+\.blocked_symbols'
    // 例：risk_gate: blocked by per_strategy.grid_trading.blocked_symbols
    if is_symbol_blocklist_reason(reason) {
        return "symbol_blocklist";
    }

    // (11) risk_gate_other
    // V086 SQL: rv.reason LIKE 'risk_gate%'
    // RejectionCode: "risk_gate: ..."
    if reason.starts_with("risk_gate") {
        return "risk_gate_other";
    }

    // (12) catch-all
    // V086 SQL: ELSE 'reject_other'
    "reject_other"
}

/// `is_symbol_blocklist_reason`：偵測 reason 是否為 per_strategy.<strategy>.blocked_symbols
/// 結構（嵌在 risk_gate 字串內）。對齊 V086 SQL regex
/// `'blocked by per_strategy\.\w+\.blocked_symbols'`。
///
/// 用簡單 substring + 結構檢查取代正則（hot path 友好；正則庫依賴避免）。
fn is_symbol_blocklist_reason(reason: &str) -> bool {
    // 必含「blocked by per_strategy.」開頭片段
    let needle = "blocked by per_strategy.";
    let Some(start) = reason.find(needle) else {
        return false;
    };
    let tail = &reason[start + needle.len()..];
    // tail 應為 "<strategy_name>.blocked_symbols..." 格式
    // 找到第一個 '.'，檢查 '.' 後是否為 "blocked_symbols"
    let Some(dot_pos) = tail.find('.') else {
        return false;
    };
    let strategy_name = &tail[..dot_pos];
    let after_dot = &tail[dot_pos + 1..];
    // strategy_name 必非空且只含 word char（\w 在 PG = [A-Za-z0-9_]）
    if strategy_name.is_empty()
        || !strategy_name
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '_')
    {
        return false;
    }
    after_dot.starts_with("blocked_symbols")
}

/// `validate_reject_reason_code`：驗證 enum 值是否在 12 enum 列表中（D+2 ALTER VALIDATE
/// 收緊前的 producer 端防線；CHECK constraint 是 NOT VALID 階段不會強制新 INSERT，
/// 但 producer 寫之前自我驗證可避免下游 D+2 收緊時 fails）。
///
/// 不在列表 → 返回 `Cow::Borrowed("reject_other")` 並 log warning。
/// 在列表 → 返回 `Cow::Borrowed(原值的 'static slice 對應)`。
///
/// 注意：返回 `Cow<'static, str>` 而非 `&'static str` 是為了 caller 收到後可
/// 直接 own / clone，與 `DecisionFeatureMsg.reject_reason_code: Option<String>`
/// 對接更乾淨。
#[allow(dead_code)]
pub fn validate_reject_reason_code(value: &str) -> Cow<'static, str> {
    for &enum_val in REJECT_REASON_CODE_ENUM {
        if enum_val == value {
            return Cow::Borrowed(enum_val);
        }
    }
    tracing::warn!(
        invalid_value = %value,
        "validate_reject_reason_code: value not in V086 12 enum, falling back to reject_other"
    );
    Cow::Borrowed("reject_other")
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 鏡像 V086 SQL CASE WHEN evaluation order 的 12 enum 全覆蓋測試。
    /// 任何測試 fail = producer 與 V086 SQL backfill 行為發生語意漂移。
    #[test]
    fn test_v086_12_reject_enum_mapping_byte_identical() {
        // (1) ATR unavailable
        assert_eq!(
            map_reject_reason_to_code("cost_gate: ATR unavailable (fail-closed, SEC-11)"),
            "cost_gate_atr_unavailable"
        );

        // (2) cost_gate JS-demo
        assert_eq!(
            map_reject_reason_to_code(
                "cost_gate(JS-demo): edge=2.00bps < threshold=6.50bps (fee=5.00bps, wr=0.50)"
            ),
            "cost_gate_js_demo_negative_edge"
        );
        assert_eq!(
            map_reject_reason_to_code(
                "cost_gate(JS-demo): estimated=-12.50bps < 0 — blocked / 負估計阻擋"
            ),
            "cost_gate_js_demo_negative_edge"
        );

        // (3) cost_gate other 變體
        assert_eq!(
            map_reject_reason_to_code("cost_gate: confidence 0.42 < min 0.50"),
            "cost_gate_other"
        );
        assert_eq!(
            map_reject_reason_to_code(
                "cost_gate(JS): edge=5.00bps < threshold=10.50bps (fee=11.00bps, wr=0.55, slip=5.0bps)"
            ),
            "cost_gate_other"
        );
        assert_eq!(
            map_reject_reason_to_code(
                "cost_gate(JS-live): edge=1.00bps < threshold=9.99bps (fee=7.70bps, wr=0.60)"
            ),
            "cost_gate_other"
        );

        // (4) duplicate_position
        assert_eq!(
            map_reject_reason_to_code("duplicate_position: BTCUSDT already LONG 0.5"),
            "duplicate_position"
        );

        // (5) direction_conflict（caller-constructed string）
        assert_eq!(
            map_reject_reason_to_code("direction_conflict: existing LONG vs new SHORT"),
            "direction_conflict"
        );

        // (6) position_count_limit
        assert_eq!(
            map_reject_reason_to_code("position_count: 5 >= max_open 5"),
            "position_count_limit"
        );

        // (7) scanner_market_gate
        assert_eq!(
            map_reject_reason_to_code("scanner_market_gate: market_phase=high_vol blocked"),
            "scanner_market_gate"
        );

        // (8) scanner_opportunity_canary
        assert_eq!(
            map_reject_reason_to_code("scanner_opportunity_canary: ratio 0.30 < min 0.50"),
            "scanner_opportunity_canary"
        );

        // (9) drawdown_breach
        assert_eq!(
            map_reject_reason_to_code("drawdown_breach: 6.5% > 5.0% cap"),
            "drawdown_breach"
        );

        // (10) symbol_blocklist
        assert_eq!(
            map_reject_reason_to_code(
                "risk_gate: blocked by per_strategy.grid_trading.blocked_symbols"
            ),
            "symbol_blocklist"
        );
        assert_eq!(
            map_reject_reason_to_code(
                "risk_gate: blocked by per_strategy.ma_crossover.blocked_symbols [BTCUSDT]"
            ),
            "symbol_blocklist"
        );

        // (11) risk_gate_other（不嵌 blocked_symbols 的 risk_gate）
        assert_eq!(
            map_reject_reason_to_code("risk_gate: daily_loss_pct 3.00 > 2.00"),
            "risk_gate_other"
        );

        // (12) catch-all
        assert_eq!(
            map_reject_reason_to_code("guardian_rejected: [\"some_unknown_reason\"]"),
            "reject_other"
        );
        assert_eq!(map_reject_reason_to_code(""), "reject_other");
        assert_eq!(map_reject_reason_to_code("unknown_format_string"), "reject_other");
    }

    /// evaluation order 關鍵測試：ATR unavailable 必先於 cost_gate_other（V086 SQL §6 #1
    /// 高風險點）。如果順序錯，"cost_gate: ATR unavailable ..." 會被誤判為 cost_gate_other。
    #[test]
    fn test_evaluation_order_atr_unavailable_precedes_cost_gate_other() {
        let reason = "cost_gate: ATR unavailable (fail-closed, SEC-11)";
        // 必須返回 atr_unavailable，不是 cost_gate_other
        assert_eq!(map_reject_reason_to_code(reason), "cost_gate_atr_unavailable");
    }

    /// evaluation order 關鍵測試：JS-demo 必先於 cost_gate_other。
    #[test]
    fn test_evaluation_order_js_demo_precedes_cost_gate_other() {
        let reason = "cost_gate(JS-demo): estimated=-3.5bps < 0";
        assert_eq!(
            map_reject_reason_to_code(reason),
            "cost_gate_js_demo_negative_edge"
        );
    }

    /// evaluation order 關鍵測試：symbol_blocklist 必先於 risk_gate_other（嵌套字串）。
    #[test]
    fn test_evaluation_order_symbol_blocklist_precedes_risk_gate_other() {
        let reason = "risk_gate: blocked by per_strategy.bb_breakout.blocked_symbols";
        // 必須返回 symbol_blocklist，不是 risk_gate_other
        assert_eq!(map_reject_reason_to_code(reason), "symbol_blocklist");
    }

    /// 12 enum 全在 REJECT_REASON_CODE_ENUM slice。
    #[test]
    fn test_all_12_enum_in_constant() {
        assert_eq!(REJECT_REASON_CODE_ENUM.len(), 12);
        let expected = [
            "cost_gate_js_demo_negative_edge",
            "cost_gate_atr_unavailable",
            "cost_gate_other",
            "duplicate_position",
            "direction_conflict",
            "position_count_limit",
            "scanner_market_gate",
            "scanner_opportunity_canary",
            "drawdown_breach",
            "symbol_blocklist",
            "risk_gate_other",
            "reject_other",
        ];
        for v in expected {
            assert!(
                REJECT_REASON_CODE_ENUM.contains(&v),
                "missing enum value in constant: {v}"
            );
        }
    }

    /// `is_symbol_blocklist_reason` 結構驗證。
    #[test]
    fn test_is_symbol_blocklist_reason_structure() {
        // PASS: 標準格式
        assert!(is_symbol_blocklist_reason(
            "risk_gate: blocked by per_strategy.grid_trading.blocked_symbols"
        ));
        assert!(is_symbol_blocklist_reason(
            "blocked by per_strategy.ma_crossover.blocked_symbols [BTCUSDT,ETHUSDT]"
        ));
        // PASS: 嵌入長字串
        assert!(is_symbol_blocklist_reason(
            "some prefix; blocked by per_strategy.bb_breakout.blocked_symbols and other text"
        ));

        // FAIL: 缺 needle
        assert!(!is_symbol_blocklist_reason("risk_gate: daily_loss_pct exceeded"));
        // FAIL: 結構不對（無 .blocked_symbols 後綴）
        assert!(!is_symbol_blocklist_reason(
            "blocked by per_strategy.grid_trading.other_field"
        ));
        // FAIL: 缺 strategy_name
        assert!(!is_symbol_blocklist_reason(
            "blocked by per_strategy..blocked_symbols"
        ));
    }

    /// `validate_reject_reason_code` 防線測試。
    #[test]
    fn test_validate_reject_reason_code_falls_back_on_unknown() {
        assert_eq!(
            validate_reject_reason_code("cost_gate_other").as_ref(),
            "cost_gate_other"
        );
        assert_eq!(
            validate_reject_reason_code("reject_other").as_ref(),
            "reject_other"
        );
        // 不在列表 → catch-all
        assert_eq!(
            validate_reject_reason_code("invalid_enum_value").as_ref(),
            "reject_other"
        );
        assert_eq!(validate_reject_reason_code("").as_ref(), "reject_other");
    }
}
