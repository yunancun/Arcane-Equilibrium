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
}
