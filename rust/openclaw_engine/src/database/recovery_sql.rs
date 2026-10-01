//! Shared inserts for the batch writer and atomic execution recovery transactions.
use super::{sanitize_f64, sanitize_f64_or_zero, TradingMsg};
use sqlx::{Postgres, QueryBuilder};

pub(super) fn fills(chunk: &[TradingMsg]) -> QueryBuilder<'_, Postgres> {
    // V094 (2026-05-15): details JSONB plus close-maker audit columns
    // preserve cold defaults while making close-maker attempts queryable.
    // V094（2026-05-15）：新增 details JSONB 與 close-maker audit 欄位；
    // 既有 cold default 不變，同時讓 close-maker 嘗試可查。
    let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
                "INSERT INTO trading.fills (ts, fill_id, order_id, symbol, side, qty, price, fee, fee_rate, reference_price, reference_ts_ms, reference_source, slippage_bps, liquidity_role, fill_latency_ms, realized_pnl, is_paper, strategy_name, context_id, entry_context_id, engine_mode, exit_source, exit_reason, details, close_maker_attempt, close_maker_fallback_reason, maker_markout_bps) "
            );
    qb.push_values(chunk.iter(), |mut b, msg| {
        if let TradingMsg::Fill {
            fill_id,
            ts_ms,
            order_id,
            symbol,
            side,
            qty,
            price,
            fee,
            fee_rate,
            reference_price,
            reference_ts_ms,
            reference_source,
            slippage_bps,
            liquidity_role,
            fill_latency_ms,
            realized_pnl,
            strategy_name,
            context_id,
            entry_context_id,
            engine_mode,
            exit_source,
            exit_reason,
            details,
            close_maker_attempt,
            close_maker_fallback_reason,
            maker_markout_bps,
        } = msg
        {
            b.push_bind(chrono::DateTime::from_timestamp_millis(*ts_ms as i64).unwrap_or_default());
            b.push_bind(fill_id.as_str());
            b.push_bind(order_id.as_str());
            b.push_bind(symbol.as_str());
            b.push_bind(side.as_str());
            b.push_bind(sanitize_f64_or_zero(*qty) as f32);
            b.push_bind(sanitize_f64_or_zero(*price) as f32);
            b.push_bind(sanitize_f64_or_zero(*fee) as f32);
            b.push_bind(sanitize_f64_or_zero(*fee_rate) as f32);
            b.push_bind(reference_price.as_ref().and_then(|v| sanitize_f64(*v)));
            b.push_bind(reference_ts_ms.map(|v| v as i64));
            b.push_bind(reference_source.as_deref());
            b.push_bind(slippage_bps.as_ref().and_then(|v| sanitize_f64(*v)));
            b.push_bind(liquidity_role.as_deref());
            b.push_bind(fill_latency_ms.map(|v| v as i64));
            b.push_bind(sanitize_f64_or_zero(*realized_pnl) as f32);
            // DEPRECATED: is_paper derived from engine_mode (compat with Grafana).
            // 已棄用：is_paper 由 engine_mode 派生（兼容 Grafana）。
            b.push_bind(engine_mode != "live");
            b.push_bind(strategy_name.as_str());
            b.push_bind(context_id.as_str());
            // EDGE-P3-1 R2: entry_context_id — NULL when empty (open fills,
            // pre-V017 restored positions, orphan adopts). Close fills carry
            // the opening entry's context_id for ML training JOIN.
            // EDGE-P3-1 R2：entry_context_id — 空串寫 NULL（開倉、pre-V017 還原、
            // orphan adopt）；平倉 fill 攜帶開倉 entry 的 context_id 供 ML JOIN。
            if entry_context_id.is_empty() {
                b.push_bind(None::<String>);
            } else {
                b.push_bind(Some(entry_context_id.as_str().to_string()));
            }
            b.push_bind(engine_mode.as_str());
            // INFRA-PREBUILD-1 Part A: Combine Layer ExitSource tag
            // (V021 trading.fills.exit_source). None → NULL (open
            // fill or non-Combine exit path like HARD STOP).
            // INFRA-PREBUILD-1 A 部：Combine Layer ExitSource 標籤。
            // None → NULL（開倉 fill 或非 Combine 退場如 HARD STOP）。
            b.push_bind(exit_source.as_deref());
            // V033 (2026-04-29): free-text close reason. Entry fills
            // → None → NULL. Close fills produced via the W1-T2
            // close-tag normalizer bind Some(reason).
            // V033（2026-04-29）：自由文字退場原因。entry fill → None
            // → NULL；close fill 由 W1-T2 close-tag normalizer 產出
            // Some(reason)。
            b.push_bind(exit_reason.as_deref());
            // V094: optional close-maker audit JSONB. None keeps old
            // entry / market-close rows NULL; Some persists audit keys
            // such as close_initial_limit_price and rate_limit_scope.
            // V094：可選 close-maker audit JSONB。None 讓既有 entry /
            // market close row 維持 NULL；Some 寫入 audit key。
            b.push_bind(details.clone());
            // V094 hot columns: false/None is the cold path default.
            // V094 hot 欄位：false/None 為 cold path default。
            b.push_bind(*close_maker_attempt);
            b.push_bind(close_maker_fallback_reason.as_deref());
            // V145: maker adverse-selection markout。只有 maker fill 帶值
            // （loop_exchange.rs 按 liquidity_role 互斥分流）；taker/paper
            // fill 為 None → NULL，與 slippage_bps 對 maker 維持 NULL 對稱。
            b.push_bind(maker_markout_bps.as_ref().and_then(|v| sanitize_f64(*v)));
        }
    });
    qb.push(" ON CONFLICT (fill_id, ts) DO NOTHING");
    qb
}

pub(super) fn funding_settlements(chunk: &[TradingMsg]) -> QueryBuilder<'_, Postgres> {
    let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
        "INSERT INTO trading.funding_settlements \
                 (ts, settlement_id, exec_id, symbol, side, amount, fee_currency, \
                  exec_value, exec_price, exec_qty, strategy_name, engine_mode, raw) ",
    );
    qb.push_values(chunk.iter(), |mut b, msg| {
        if let TradingMsg::FundingSettlement {
            settlement_id,
            ts_ms,
            exec_id,
            symbol,
            side,
            amount,
            fee_currency,
            exec_value,
            exec_price,
            exec_qty,
            strategy_name,
            engine_mode,
            raw,
        } = msg
        {
            b.push_bind(chrono::DateTime::from_timestamp_millis(*ts_ms as i64).unwrap_or_default());
            b.push_bind(settlement_id.as_str());
            b.push_bind(exec_id.as_str());
            b.push_bind(symbol.as_str());
            b.push_bind(side.as_str());
            b.push_bind(sanitize_f64_or_zero(*amount));
            b.push_bind(fee_currency.as_str());
            b.push_bind(sanitize_f64_or_zero(*exec_value));
            b.push_bind(sanitize_f64_or_zero(*exec_price));
            b.push_bind(sanitize_f64_or_zero(*exec_qty));
            b.push_bind(strategy_name.as_str());
            b.push_bind(engine_mode.as_str());
            b.push_bind(raw.clone());
        }
    });
    qb.push(" ON CONFLICT (settlement_id, ts) DO NOTHING");
    qb
}

pub(super) fn orders(chunk: &[TradingMsg]) -> QueryBuilder<'_, Postgres> {
    // ORDER-AUDIT-PROJECTION-1（2026-06-20）：schema 既有
    // price/context_id/details，但 Order writer 漏接，導致 Working
    // PostOnly limit 單不可直接觀測委託價。這裡只補審計投影，不改下單行為。
    let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
        "INSERT INTO trading.orders \
                 (ts, order_id, symbol, side, order_type, time_in_force, qty, strategy_name, \
                  category, is_paper, status, engine_mode, intent_id, price, context_id, details) ",
    );
    qb.push_values(chunk.iter(), |mut b, msg| {
        if let TradingMsg::Order {
            order_id,
            ts_ms,
            symbol,
            side,
            order_type,
            time_in_force,
            qty,
            price,
            context_id,
            strategy_name,
            is_close: _,
            engine_mode,
            details,
            intent_id,
        } = msg
        {
            b.push_bind(chrono::DateTime::from_timestamp_millis(*ts_ms as i64).unwrap_or_default());
            b.push_bind(order_id.as_str());
            b.push_bind(symbol.as_str());
            b.push_bind(side.as_str());
            b.push_bind(order_type.as_str());
            b.push_bind(time_in_force.as_deref());
            b.push_bind(sanitize_f64_or_zero(*qty) as f32);
            b.push_bind(strategy_name.as_str());
            b.push_bind("linear"); // Bybit USDT perp default / USDT 永續默認
                                   // DEPRECATED is_paper derived from engine_mode (Grafana compat)
            b.push_bind(engine_mode != "live");
            // Order 由送出前註冊產生；venue 狀態另記 order_state_changes。
            b.push_bind("PendingSubmit");
            b.push_bind(engine_mode.as_str());
            // P2-ORDERS-INTENT-ID-WRITER-GAP-1：Option<&str> → SQL TEXT NULL
            b.push_bind(intent_id.as_deref());
            b.push_bind(price.and_then(sanitize_f64).map(|v| v as f32));
            b.push_bind(context_id.as_deref());
            b.push_bind(details.clone());
        }
    });
    qb.push(" ON CONFLICT (order_id, ts) DO NOTHING");
    qb
}

pub(super) fn order_state_changes(chunk: &[TradingMsg]) -> QueryBuilder<'_, Postgres> {
    let mut qb: QueryBuilder<Postgres> = QueryBuilder::new(
                "INSERT INTO trading.order_state_changes \
                 (ts, order_id, from_status, to_status, filled_qty, avg_price, reason, engine_mode) ",
            );
    qb.push_values(chunk.iter(), |mut b, msg| {
        if let TradingMsg::OrderStateChange {
            order_id,
            ts_ms,
            from_status,
            to_status,
            filled_qty,
            avg_price,
            reason,
            engine_mode,
        } = msg
        {
            b.push_bind(chrono::DateTime::from_timestamp_millis(*ts_ms as i64).unwrap_or_default());
            b.push_bind(order_id.as_str());
            b.push_bind(from_status.as_deref());
            b.push_bind(to_status.as_str());
            b.push_bind(filled_qty.and_then(sanitize_f64).map(|v| v as f32));
            b.push_bind(avg_price.and_then(sanitize_f64).map(|v| v as f32));
            b.push_bind(reason.as_deref());
            b.push_bind(engine_mode.as_str());
        }
    });
    qb.push(" ON CONFLICT (order_id, ts, to_status) DO NOTHING");
    qb
}

pub(crate) async fn persist(
    conn: &mut sqlx::PgConnection,
    msgs: &[TradingMsg],
) -> Result<(), sqlx::Error> {
    for msg in msgs {
        let one = std::slice::from_ref(msg);
        let mut query = match msg {
            TradingMsg::Fill { .. } => fills(one),
            TradingMsg::FundingSettlement { .. } => funding_settlements(one),
            TradingMsg::Order { .. } => orders(one),
            TradingMsg::OrderStateChange { .. } => order_state_changes(one),
            _ => continue,
        };
        query.build().execute(&mut *conn).await?;
    }
    Ok(())
}
