//! Residual-aware reduce-only close sizing.
//! 殘量感知的 reduce-only 平倉數量規劃。
//!
//! The exchange accepts a special full-position close form for perps/futures:
//! `qty=0`, `reduceOnly=true`, `closeOnTrigger=true`. Use it only for
//! primary exchange full closes; partial reductions still carry an explicit
//! exchange-step quantity.

use super::TickPipeline;

#[derive(Debug, Clone, PartialEq)]
pub(crate) struct DustResidualDecision {
    pub rounded_reduce_qty: f64,
    pub residual_qty: f64,
    pub residual_notional: f64,
    pub min_notional: f64,
}

impl TickPipeline {
    /// Full-position exchange close quantity.
    ///
    /// Primary Demo/Live closes use Bybit's `qty=0 + reduceOnly +
    /// closeOnTrigger` form so the exchange flattens the current position
    /// instead of relying on a possibly stale locally rounded size. Shadow and
    /// paper paths keep the explicit quantity.
    pub(super) fn close_dispatch_qty_for_full_close(
        &self,
        requested_qty: f64,
        is_primary: bool,
    ) -> f64 {
        if is_primary && self.pipeline_kind.is_exchange() {
            0.0
        } else {
            requested_qty
        }
    }

    /// Returns `Some` when a partial reduce should be skipped because the
    /// rounded reduce quantity would leave a below-min-notional residual.
    ///
    /// This is intentionally conservative: it does not full-close from a
    /// partial-reduce trigger. Full closes have their own qty=0 path; partial
    /// reducers should wait for a real close signal instead of manufacturing
    /// untradeable residue.
    pub(super) fn partial_reduce_dust_residual(
        &self,
        symbol: &str,
        position_qty: f64,
        requested_reduce_qty: f64,
        ref_price: f64,
    ) -> Option<DustResidualDecision> {
        if !(position_qty > 0.0 && requested_reduce_qty > 0.0 && ref_price > 0.0) {
            return None;
        }
        let spec = self.instrument_cache.as_ref()?.get(symbol)?;
        if !(spec.min_notional > 0.0 && spec.min_qty > 0.0) {
            return None;
        }

        let rounded_reduce_qty = spec.round_qty(requested_reduce_qty);
        if rounded_reduce_qty < spec.min_qty {
            return Some(DustResidualDecision {
                rounded_reduce_qty,
                residual_qty: position_qty,
                residual_notional: position_qty * ref_price,
                min_notional: spec.min_notional,
            });
        }

        let residual_qty = (position_qty - rounded_reduce_qty).max(0.0);
        if residual_qty <= 0.0 {
            return None;
        }
        let residual_notional = residual_qty * ref_price;
        if residual_notional < spec.min_notional {
            return Some(DustResidualDecision {
                rounded_reduce_qty,
                residual_qty,
                residual_notional,
                min_notional: spec.min_notional,
            });
        }
        None
    }
}
