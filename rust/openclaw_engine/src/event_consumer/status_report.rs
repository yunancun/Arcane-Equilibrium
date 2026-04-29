//! Status-interval work for the event consumer tick arm.
//! 事件消費者 tick arm 的 status-interval 週期工作。
//!
//! MODULE_NOTE (EN): Split from ``loop_handlers.rs`` by
//! STRK-FUP-LOOP-HANDLERS-SPLIT. Owns the 30s-ish status cadence: H0Gate risk
//! snapshot refresh, state/checkpoint writes, scanner D2 diff + D3 bootstrap,
//! and the EVICT-ON-DUST T4 reaper.
//! MODULE_NOTE (中): STRK-FUP-LOOP-HANDLERS-SPLIT 從 ``loop_handlers.rs``
//! 拆出；負責約 30s 狀態節奏：H0 風控快照、state/checkpoint 寫入、scanner
//! D2 diff + D3 bootstrap，以及 EVICT-ON-DUST T4 reaper。

use std::sync::Arc;
use std::time::{Duration, Instant};

use super::loop_handlers::LoopState;
use crate::persistence::{DualStateWriter, StateWriter};
use crate::tick_pipeline::TickPipeline;

/// Build the periodic H0 risk refresh snapshot while preserving independently
/// owned cooldown / kill-switch fields from the previous snapshot.
/// 生成週期性 H0 風控刷新快照，同時保留前一版中由其他路徑擁有的
/// cooldown / kill-switch 欄位。
fn build_status_risk_snapshot(
    prev: &openclaw_types::H0GateRiskSnapshot,
    open_position_count: u32,
    total_exposure_pct: f64,
    now_ms: u64,
) -> openclaw_types::H0GateRiskSnapshot {
    openclaw_types::H0GateRiskSnapshot {
        open_position_count,
        total_exposure_pct,
        cooldown_until_ts_ms: if prev.cooldown_until_ts_ms > now_ms {
            prev.cooldown_until_ts_ms
        } else {
            0
        },
        kill_switch_active: prev.kill_switch_active,
        snapshot_ts_ms: now_ms,
    }
}

#[allow(clippy::too_many_arguments)]
pub(super) fn handle_status_interval(
    pipeline: &mut TickPipeline,
    state_writer: &mut StateWriter,
    snapshot_writer: &mut DualStateWriter,
    state: &mut LoopState,
    start_time: Instant,
    status_interval: Duration,
    audit_pool: Option<&sqlx::PgPool>,
    symbol_registry: Option<&Arc<crate::scanner::registry::SymbolRegistry>>,
    cfg_snapshot: &Arc<crate::config::EngineBootstrap>,
    bootstrap_client: Option<&Arc<crate::bybit_rest_client::BybitRestClient>>,
    kline_seed_tx: &tokio::sync::mpsc::Sender<(String, Vec<openclaw_core::klines::KlineBar>)>,
) {
    // RRC-1-A2: Periodic H0Gate risk snapshot update (every status interval).
    // RRC-1-A2：定期更新 H0 門控風控快照（每狀態報告間隔）。
    if state.last_status.elapsed() >= status_interval {
        let positions = pipeline.paper_state.positions();
        let position_count = positions.len() as u32;
        let balance = pipeline.paper_state.export_state().balance;
        let total_exposure_pct = if balance > 0.0 {
            let total_notional: f64 = positions
                .iter()
                .map(|p| {
                    let price = pipeline
                        .latest_prices()
                        .get(&p.symbol)
                        .copied()
                        .unwrap_or(p.entry_price);
                    p.qty * price
                })
                .sum();
            (total_notional / balance * 100.0).min(999.0)
        } else {
            0.0
        };
        let now_ms = openclaw_core::now_ms();
        let prev_h0_risk = pipeline.h0_gate.risk_snapshot();
        pipeline.h0_gate.update_risk(build_status_risk_snapshot(
            &prev_h0_risk,
            position_count,
            total_exposure_pct,
            now_ms,
        ));

        let status = pipeline.status();
        let uptime = start_time.elapsed().as_secs();
        let h0_stats = pipeline.h0_gate.get_stats();
        // PNL-2: invariant — every tick must run H0Gate.check.
        // PNL-2：不變量 — 每個 tick 必須走過 H0Gate.check。
        // If ticks > 0 but checks == 0 → stale binary or wiring regression.
        // 若 ticks > 0 而 checks == 0 → stale binary 或接線退化。
        if status.stats.total_ticks > 0 && h0_stats.total_checks == 0 {
            tracing::warn!(
                ticks = status.stats.total_ticks,
                "PNL-2 invariant violated: ticks>0 but H0Gate checks==0 — stale binary? / H0 門控未執行"
            );
        }
        tracing::info!(
            ticks = status.stats.total_ticks,
            fills = status.stats.total_fills,
            intents = status.stats.total_intents,
            stops = status.stats.total_stops,
            balance = format!("{:.2}", status.balance),
            positions = status.positions,
            symbols = status.symbols_tracked,
            uptime_secs = uptime,
            h0_checks = h0_stats.total_checks,
            h0_blocked = h0_stats.total_blocked(),
            h0_shadow_would_block = h0_stats.shadow_would_block,
            "status report / 狀態報告"
        );
        let snap = pipeline.paper_state.export_state();
        state_writer.maybe_write(&snap);
        let full_snap = pipeline.snapshot();
        snapshot_writer.maybe_write(&full_snap);

        // P1-5 A2: piggy-back checkpoint UPSERT on the state-writer
        // cadence (~30s per engine). Detached spawn so the event loop
        // isn't blocked on the DB round-trip. `audit_pool.clone()` is
        // cheap (Arc<Inner>). Fail-soft: warn logs live inside
        // `write_checkpoint`, next tick will retry.
        // P1-5 A2：在狀態寫入週期（每引擎 ~30s）順手 UPSERT checkpoint。
        // 分離 spawn 避免阻塞事件迴圈；pool clone 為 Arc 廉價。
        // fail-soft：write_checkpoint 內部 warn log，下週期重試。
        if let Some(pool) = audit_pool {
            let pool_clone = pool.clone();
            let em = pipeline.effective_engine_mode().to_string();
            let peak = pipeline.paper_state.peak_balance();
            let session_start_ts_ms = pipeline.paper_state.session_start_ts_ms();
            tokio::spawn(async move {
                if let Err(e) = crate::paper_state::checkpoint::write_checkpoint(
                    &pool_clone,
                    &em,
                    peak,
                    session_start_ts_ms,
                )
                .await
                {
                    tracing::warn!(
                        engine_mode = %em,
                        error = %e,
                        "P1-5 A2: checkpoint UPSERT failed (will retry next cycle) \
                         / checkpoint 寫入失敗，下週期重試"
                    );
                }
            });
        }

        // D2: Diff registry vs known_symbols → add/remove from pipeline.
        // Runs every status interval (30s); scanner cycle is 30 min,
        // so changes are reflected within one interval.
        // D2：差分注冊表與 known_symbols → 從管線增減交易對。
        // 每狀態報告間隔（30s）執行；掃描器週期 30 分鐘，
        // 變更在一個間隔內反映。
        if let Some(reg) = symbol_registry {
            let current: std::collections::HashSet<String> = reg.snapshot().into_iter().collect();
            let to_add: Vec<String> = current.difference(&state.known_symbols).cloned().collect();
            let to_remove: Vec<String> =
                state.known_symbols.difference(&current).cloned().collect();

            for sym in &to_remove {
                pipeline.remove_symbol(sym);
                state.known_symbols.remove(sym);
                tracing::info!(symbol = %sym,
                      "D2: scanner removed symbol from pipeline \
                       / 掃描器從管線移除交易對");
            }

            for sym in &to_add {
                pipeline.add_symbol(sym);
                state.known_symbols.insert(sym.clone());
                tracing::info!(symbol = %sym,
                      "D2: scanner added symbol to pipeline \
                       / 掃描器向管線添加交易對");

                // D3: Spawn async kline bootstrap for new symbol.
                // D3：為新交易對生成異步 K 線引導。
                if cfg_snapshot.kline_bootstrap {
                    if let Some(client_arc) = bootstrap_client {
                        let sym_owned = sym.clone();
                        let client_clone = Arc::clone(client_arc);
                        let seed_tx = kline_seed_tx.clone();
                        tokio::spawn(async move {
                            let mdc =
                                crate::market_data_client::MarketDataClient::new(client_clone);
                            match mdc
                                .get_klines("linear", &sym_owned, "1", None, None, Some(200))
                                .await
                            {
                                Ok(bars) => {
                                    let now_ms = openclaw_core::now_ms();
                                    let mut core_bars: Vec<openclaw_core::klines::KlineBar> = bars
                                        .iter()
                                        .filter(|b| b.start_time + 60_000 <= now_ms)
                                        .map(|b| openclaw_core::klines::KlineBar {
                                            open_time_ms: b.start_time,
                                            close_time_ms: b.start_time + 60_000,
                                            open: b.open,
                                            high: b.high,
                                            low: b.low,
                                            close: b.close,
                                            volume: b.volume,
                                            turnover: b.turnover,
                                            tick_count: 1,
                                            is_closed: true,
                                        })
                                        .collect();
                                    core_bars.sort_by_key(|b| b.open_time_ms);
                                    let _ = seed_tx.send((sym_owned, core_bars)).await;
                                }
                                Err(e) => {
                                    tracing::warn!(
                                        symbol = %sym_owned,
                                        error = %e,
                                        "D3: dynamic kline bootstrap failed \
                                         / 動態 K 線引導失敗"
                                    );
                                }
                            }
                        });
                    }
                }
            }
        }

        // EVICT-ON-DUST T4 (PA §1.2.1): status interval reaper.
        // Runs every status_interval (~30 s) — coalesces with the existing
        // status report so we don't spawn a new tokio interval. Catches
        // residue accumulated between hot-path T1/T2 firings: cross-restart
        // dust, funding-payment accruals that didn't go through apply_fill,
        // upsert_position_from_exchange WS reductions, and any code path
        // that mutates `paper_state.positions` without calling evict_if_dust.
        // Performance: O(N=positions). Status interval is 30 s by default →
        // 0.033 calls/s. Safe well below per-tick limit (PA §1.5 review #2).
        // Effect-free when dust_floor_usd <= 0 (gate disabled, pre-set_risk_store).
        // EVICT-ON-DUST T4：status arm 30 s reaper，與 status report 同步觸發
        // 不額外 spawn timer。專責守底跨重啟、funding 累計、WS upsert 等不走
        // hot-path 的殘餘。性能 O(N)，~0.033 次/秒，遠低於 per-tick 限制。
        // dust_floor<=0 時自動 no-op。
        let t4_evicted = pipeline.paper_state.evict_all_dust("status_arm_reaper");
        if t4_evicted > 0 {
            tracing::info!(
                evicted = t4_evicted,
                dust_evictions_total = pipeline.paper_state.dust_evictions_total(),
                dust_floor_usd = pipeline.paper_state.dust_floor_usd(),
                "EVICT-ON-DUST T4 status reaper: phantom dust positions evicted \
                 / status arm reaper：殭屍 dust 倉位已驅逐"
            );
        }

        state.last_status = Instant::now();
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn status_risk_snapshot_preserves_active_cooldown_and_kill_switch() {
        let now_ms = 1_000;
        let prev = openclaw_types::H0GateRiskSnapshot {
            open_position_count: 9,
            total_exposure_pct: 88.8,
            cooldown_until_ts_ms: now_ms + 15_000,
            kill_switch_active: true,
            snapshot_ts_ms: now_ms - 100,
        };

        let merged = build_status_risk_snapshot(&prev, 2, 25.0, now_ms);
        assert_eq!(merged.open_position_count, 2);
        assert_eq!(merged.total_exposure_pct, 25.0);
        assert_eq!(merged.cooldown_until_ts_ms, now_ms + 15_000);
        assert!(merged.kill_switch_active);
        assert_eq!(merged.snapshot_ts_ms, now_ms);
    }

    #[test]
    fn status_risk_snapshot_clears_expired_cooldown_but_keeps_kill_switch() {
        let now_ms = 20_000;
        let prev = openclaw_types::H0GateRiskSnapshot {
            open_position_count: 1,
            total_exposure_pct: 10.0,
            cooldown_until_ts_ms: now_ms - 1,
            kill_switch_active: false,
            snapshot_ts_ms: now_ms - 500,
        };

        let merged = build_status_risk_snapshot(&prev, 3, 55.0, now_ms);
        assert_eq!(merged.cooldown_until_ts_ms, 0);
        assert!(!merged.kill_switch_active);
    }
}
