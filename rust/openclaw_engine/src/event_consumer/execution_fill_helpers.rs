//! Fill attribution helpers for the event consumer exchange-event arm.
//! 事件消費者 exchange-event arm 的成交歸因 helper。
//!
//! MODULE_NOTE (EN): Split from ``loop_handlers.rs`` by
//! STRK-FUP-LOOP-HANDLERS-SPLIT to keep the hot-path handler file below the
//! 1200-line governance threshold.
//! MODULE_NOTE (中): STRK-FUP-LOOP-HANDLERS-SPLIT 從 ``loop_handlers.rs``
//! 拆出，讓 hot-path handler 檔案低於 1200 行治理門檻。

pub(super) fn fill_liquidity_role(
    is_maker: bool,
    tif: Option<crate::order_manager::TimeInForce>,
) -> &'static str {
    if is_maker || matches!(tif, Some(crate::order_manager::TimeInForce::PostOnly)) {
        "maker"
    } else {
        "taker"
    }
}

/// V145：依 liquidity_role 把同一 markout 純函數的結果分流到兩個正交 column。
/// 回傳 `(slippage_bps, maker_markout_bps)`，兩者**互斥**（同一 fill 至多一個非
/// None）：taker→slippage_bps（穿越 spread 的執行劣勢），maker→maker_markout_bps
/// （掛單成交後 mid 朝對我不利方向走的 adverse selection）。
/// 為何拆兩欄：語意正交，混在一欄會讓下游 cost-floor 分析與 market-making edge
/// verdict 雙重歧義（PA §B.2.1 裁決）。zero 新數學，純分流。
pub(super) fn split_markout_by_role(
    liquidity_role: &str,
    is_buy: bool,
    fill_price: f64,
    reference_price: Option<f64>,
) -> (Option<f64>, Option<f64>) {
    match liquidity_role {
        "taker" => (
            adverse_slippage_bps(is_buy, fill_price, reference_price),
            None,
        ),
        "maker" => (
            None,
            adverse_slippage_bps(is_buy, fill_price, reference_price),
        ),
        _ => (None, None),
    }
}

pub(super) fn adverse_slippage_bps(
    is_buy: bool,
    fill_price: f64,
    reference_price: Option<f64>,
) -> Option<f64> {
    let reference_price = reference_price?;
    if reference_price <= 0.0 || !reference_price.is_finite() || !fill_price.is_finite() {
        return None;
    }
    let signed = if is_buy {
        (fill_price - reference_price) / reference_price
    } else {
        (reference_price - fill_price) / reference_price
    };
    Some(signed * 10_000.0)
}

#[cfg(test)]
mod execution_slippage_tests {
    use super::*;

    #[test]
    fn adverse_slippage_is_positive_when_buy_fills_above_reference() {
        let bps = adverse_slippage_bps(true, 100.10, Some(100.0)).unwrap();
        assert!((bps - 10.0).abs() < 1e-9);
    }

    #[test]
    fn adverse_slippage_is_positive_when_sell_fills_below_reference() {
        let bps = adverse_slippage_bps(false, 99.90, Some(100.0)).unwrap();
        assert!((bps - 10.0).abs() < 1e-9);
    }

    #[test]
    fn postonly_fill_is_maker_even_when_exchange_flag_missing() {
        let role = fill_liquidity_role(false, Some(crate::order_manager::TimeInForce::PostOnly));
        assert_eq!(role, "maker");
    }

    /// V145：taker fill → slippage_bps 有值、maker_markout_bps None（互斥）。
    #[test]
    fn split_markout_taker_writes_slippage_only() {
        let (slip, markout) = split_markout_by_role("taker", true, 100.10, Some(100.0));
        assert!(slip.is_some(), "taker must write slippage_bps");
        assert!(markout.is_none(), "taker must NOT write maker_markout_bps");
        assert!((slip.unwrap() - 10.0).abs() < 1e-9);
    }

    /// V145：maker fill → maker_markout_bps 有值、slippage_bps None（互斥）。
    /// 這正是修復 756/756 NULL 的核心：先前 maker 走 None 分支，現在走 markout。
    #[test]
    fn split_markout_maker_writes_markout_only() {
        // maker buy 成交在 reference 之上 → 正 markout（adverse selection）。
        let (slip, markout) = split_markout_by_role("maker", true, 100.10, Some(100.0));
        assert!(slip.is_none(), "maker must NOT write slippage_bps");
        assert!(markout.is_some(), "maker MUST write maker_markout_bps (756/756 NULL fix)");
        assert!((markout.unwrap() - 10.0).abs() < 1e-9);
        // maker sell 成交在 reference 之下 → 正 markout（signed-by-side 正確）。
        let (_, markout_sell) = split_markout_by_role("maker", false, 99.90, Some(100.0));
        assert!((markout_sell.unwrap() - 10.0).abs() < 1e-9);
    }

    /// V145：未知 role / reference 缺值 → 兩欄皆 None（誠實，不誤算）。
    #[test]
    fn split_markout_unknown_role_and_missing_reference_are_none() {
        let (slip, markout) = split_markout_by_role("paper_sim", true, 100.10, Some(100.0));
        assert!(slip.is_none() && markout.is_none(), "unknown role writes neither");
        let (slip2, markout2) = split_markout_by_role("maker", true, 100.10, None);
        assert!(
            slip2.is_none() && markout2.is_none(),
            "missing reference yields None even for maker"
        );
    }
}
