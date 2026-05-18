//! W-AUDIT-8a C1-LIQ-WRITER (2026-05-18) — Liquidation pulse panel aggregator。
//!
//! MODULE_NOTE：
//!   模塊用途：消費 Bybit `allLiquidation.{symbol}` 事件流（已由 ws_client
//!     parser 轉成 `PriceEventKind::Liquidation` PriceEvent），維護 cohort
//!     per-symbol 5m rolling cluster pulse，flush 時把 snapshot 寫入
//!     `LiquidationPulsePanelSlot` 供 step_4_5_dispatch 賽進 AlphaSurface。
//!   主類函數：`LiquidationPulseAggregator::on_liquidation`（事件 ingest）、
//!     `snapshot_panel`（生成 panel snapshot）。
//!   依賴：openclaw_core::alpha_surface::{LiquidationPulse,
//!     LiquidationPulsePanel, LiquidationSide}、openclaw_types::PriceEvent、
//!     tokio::sync::RwLock（slot late-inject）。
//!   硬邊界：
//!     - **無 PG 寫入** — market.liquidations 已存原始 row-level data
//!       (V095 + market_writer 路徑既有)，本 aggregator 純 in-memory IPC
//!       provider，不重複寫資料庫；
//!     - **BB cor-side 映射死契約**：`metadata["side"]="Buy"` ⇒
//!       `LongLiquidated`（多頭被強平）；`metadata["side"]="Sell"` ⇒
//!       `ShortLiquidated`（空頭被強平）；寫反 = alpha 反向 = trade loss；
//!     - **non-cohort symbol silent ignored** — 與 funding_curve / oi_delta
//!       pattern 一致，不污染 panel；
//!     - **window 視窗硬上限**：每 symbol 內最大 1024 events，超出 LRU 拋舊；
//!       避免高頻強平 burst 撐爆記憶體。
//!
//! 設計約束（per PA decomposition §6.3 + Phase C infrastructure spec §6 C1）：
//!   - 5m sliding window per symbol；事件 push_back 後 trim 舊於
//!     `current_ts - WINDOW_5M_MS - 60s margin` 的 entry；
//!   - flush 是 sliding-window snapshot（不 drain history，避免 60s flush
//!     boundary 把 5m 視窗截斷）；snapshot_ts_ms 取 caller 給的 flush 時戳；
//!   - dominant_side 判定：long/short notional 任一佔比 ≥ 60% 即為 dominant，
//!     否則 `Mixed`（避免 50/50 邊界毛刺）；
//!   - notional = qty × price（USD-equivalent）；qty/price 為 f32（V095 schema），
//!     計算用 f64 避免累加精度漂移。
//!
//! Spec：
//!   - PA decomposition: docs/CCAgentWorkSpace/PA/workspace/reports/
//!     2026-05-18--w_audit_8a_phase_b_c_d_worktree_decomposition.md §6.3
//!   - Infrastructure spec: docs/execution_plan/
//!     2026-05-16--w_audit_8a_phase_b_c_d_infrastructure_spec.md §6 C1
//!   - Downstream consumer spec: docs/execution_plan/
//!     2026-05-16--w_audit_8c_liquidation_cluster_strategy_spec.md
//!   - V095 SQL：sql/migrations/V095__market_liquidations_identity.sql
//!   - C1 v2 proof（BB cor-side 認定）：commit 82ab71eb
//!   - Production WS revival：commit 0e8a8ae8
//!
//! Sister pattern：panel_aggregator/oi_delta.rs (W1 sub-task 2)。

use std::collections::{HashMap, HashSet, VecDeque};

use openclaw_core::alpha_surface::{
    LiquidationEvent, LiquidationPulse, LiquidationPulsePanel, LiquidationSide,
};
use openclaw_types::{PriceEvent, PriceEventKind};
use tracing::{debug, trace};

/// 5 分鐘 rolling window 毫秒（per spec §6 C1 + W-AUDIT-8c reaction window）。
pub const WINDOW_5M_MS: i64 = 5 * 60 * 1000;
/// 額外保留邊際；確保 60s flush boundary 不截斷 5m 視窗。
pub const WINDOW_RETAIN_MARGIN_MS: i64 = 60_000;
/// Per-symbol 視窗事件硬上限；高頻 burst 防護（理論 5m × 高頻不應 > 1024）。
pub const MAX_EVENTS_PER_SYMBOL: usize = 1024;
/// Dominant side 佔比閾值；任一 side notional ≥ 60% 視為 dominant，否則 Mixed。
pub const DOMINANT_SIDE_RATIO: f64 = 0.6;
/// Source tier 字串；對齊既有 panel 命名風格（per spec §6 C1）。
pub const SOURCE_TIER: &str = "bybit_v5_ws_all_liquidation";

/// LiquidationPulseAggregator — cohort per-symbol 強平 5m rolling cluster。
///
/// 不變式：
///   - cohort 為建構時 hardcoded HashSet（與 funding_curve / oi_delta 一致）；
///   - non-cohort symbol 的 `on_liquidation` 呼叫 silent ignored；
///   - history key 為 symbol，value 為 VecDeque<LiquidationEvent>（按 ts 升序）；
///   - trim 在每次 on_liquidation 內執行；snapshot_panel 不修改 history；
///   - snapshot_panel 是 borrow-only 計算（在 caller 給定 snapshot_ts_ms 上
///     重新計算 5m 視窗 cluster，避免依賴最近一次 on_liquidation 的瞬時值）。
pub struct LiquidationPulseAggregator {
    /// Cohort symbol set；O(1) lookup。
    cohort: HashSet<String>,
    /// Per-symbol sliding window VecDeque<LiquidationEvent>。
    history: HashMap<String, VecDeque<LiquidationEvent>>,
}

impl LiquidationPulseAggregator {
    /// 建構 aggregator。
    ///
    /// `cohort_symbols` 是與 funding_curve / oi_delta 共享的 hardcoded cohort
    /// （W1 IMPL 階段固定）；重複項自動 dedupe（HashSet）。
    pub fn new(cohort_symbols: Vec<String>) -> Self {
        Self {
            cohort: cohort_symbols.into_iter().collect(),
            history: HashMap::new(),
        }
    }

    /// 處理單筆 PriceEvent（Liquidation variant）。
    ///
    /// 為什麼接 PriceEvent 而非 LiquidationEvent：上游 ws_client/dispatch.rs
    /// 廣播統一型別，aggregator caller (panel run loop) 一律拿到 PriceEvent；
    /// 本函數內負責解構並映射 BB side。non-Liquidation variant silent return。
    ///
    /// 行為：
    ///   - event_kind ≠ Liquidation → silent skip；
    ///   - non-cohort symbol → silent skip（cohort filter）；
    ///   - metadata 缺 side / qty / 解析失敗 → silent skip（parser 層已過濾，
    ///     此處 defensive）；
    ///   - 通過後 push_back 入 history + trim 舊於 cutoff entry；
    ///   - 超過 MAX_EVENTS_PER_SYMBOL → LRU pop_front 拋舊（最老事件）。
    pub fn on_liquidation(&mut self, event: &PriceEvent) {
        if event.event_kind != Some(PriceEventKind::Liquidation) {
            return;
        }
        if !self.cohort.contains(&event.symbol) {
            return;
        }
        let side_str = match event.metadata.get("side") {
            Some(s) => s,
            None => {
                trace!(
                    target: "panel_aggregator",
                    symbol = %event.symbol,
                    "liquidation event missing side metadata; defensive skip"
                );
                return;
            }
        };
        // BB cor-side 映射不變式：Buy=long_liquidation, Sell=short_liquidation
        let side = match side_str.as_str() {
            "Buy" => LiquidationSide::LongLiquidated,
            "Sell" => LiquidationSide::ShortLiquidated,
            other => {
                trace!(
                    target: "panel_aggregator",
                    symbol = %event.symbol,
                    side = %other,
                    "liquidation event side not Buy/Sell; defensive skip"
                );
                return;
            }
        };
        let qty: f64 = match event.metadata.get("qty").and_then(|s| s.parse::<f64>().ok()) {
            Some(q) if q > 0.0 && q.is_finite() => q,
            _ => {
                trace!(
                    target: "panel_aggregator",
                    symbol = %event.symbol,
                    "liquidation event qty unparseable; defensive skip"
                );
                return;
            }
        };
        let price = event.last_price;
        if !(price.is_finite() && price > 0.0) {
            return;
        }
        let ts_ms = event.ts_ms as i64;
        if ts_ms <= 0 {
            return;
        }

        let liq_event = LiquidationEvent {
            symbol: event.symbol.clone(),
            side,
            qty,
            price,
            ts_ms,
        };

        let window = self
            .history
            .entry(event.symbol.clone())
            .or_default();
        window.push_back(liq_event);

        // Trim：刪除舊於 (current_ts - WINDOW_5M_MS - margin) 的 entry。
        // 為什麼用 ts_ms 而非 caller now：trim 與事件流時間軸對齊，避免
        // 系統時鐘漂移影響視窗 boundary。
        let cutoff = ts_ms - WINDOW_5M_MS - WINDOW_RETAIN_MARGIN_MS;
        while window
            .front()
            .map(|e| e.ts_ms < cutoff)
            .unwrap_or(false)
        {
            window.pop_front();
        }

        // 視窗事件硬上限：burst 防護，LRU 拋舊
        while window.len() > MAX_EVENTS_PER_SYMBOL {
            window.pop_front();
        }

        debug!(
            target: "panel_aggregator",
            symbol = %event.symbol,
            side = ?side,
            qty = qty,
            price = price,
            ts_ms = ts_ms,
            window_len = window.len(),
            "liquidation pulse event buffered"
        );
    }

    /// 取當前 history size（test + observability 用）。
    pub fn symbol_history_count(&self) -> usize {
        self.history.len()
    }

    /// 取 cohort 大小（test + observability 用）。
    pub fn cohort_size(&self) -> usize {
        self.cohort.len()
    }

    /// 取單一 symbol 的 history deque 長度（test 用）。
    #[cfg(test)]
    pub fn history_len_for(&self, symbol: &str) -> usize {
        self.history.get(symbol).map(|d| d.len()).unwrap_or(0)
    }

    /// 從當前 history 構造 LiquidationPulsePanel snapshot。
    ///
    /// 為什麼 borrow-only：snapshot_panel 在 flush boundary 由 panel run loop
    /// 呼叫，history 不能被 drain（5m 視窗連續性）；此函數在 `snapshot_ts_ms`
    /// 上重新計算每 symbol 的 5m cluster pulse，回傳 Option<panel>。
    ///
    /// 行為：
    ///   - history 全空 → None（caller 不更新 slot；既有 slot value 保留）；
    ///   - 對每 symbol 計算 5m 視窗（snapshot_ts_ms - WINDOW_5M_MS .. snapshot_ts_ms）
    ///     內事件的 long_notional / short_notional / event_count；
    ///   - 視窗內無事件的 symbol 不放入 panel.pulses（避免空 pulse 雜訊）；
    ///   - 結果 HashMap 為 empty → 回 None（與 caller 「nothing to publish」對齊）；
    ///   - source_tier = `SOURCE_TIER`。
    pub fn snapshot_panel(&self, snapshot_ts_ms: i64) -> Option<LiquidationPulsePanel> {
        if self.history.is_empty() {
            return None;
        }
        let window_lower = snapshot_ts_ms - WINDOW_5M_MS;
        let mut pulses: HashMap<String, LiquidationPulse> = HashMap::new();

        for (sym, deque) in &self.history {
            let mut recent_events: Vec<LiquidationEvent> = Vec::new();
            let mut long_notional = 0.0_f64;
            let mut short_notional = 0.0_f64;
            let mut event_count: u32 = 0;
            for ev in deque.iter() {
                if ev.ts_ms < window_lower || ev.ts_ms > snapshot_ts_ms {
                    continue;
                }
                let notional = ev.qty * ev.price;
                if !notional.is_finite() {
                    continue;
                }
                match ev.side {
                    LiquidationSide::LongLiquidated => long_notional += notional,
                    LiquidationSide::ShortLiquidated => short_notional += notional,
                    LiquidationSide::Mixed => {
                        // 不該由 parser 產生 Mixed，但 defensive 計入 both 半量
                        long_notional += notional * 0.5;
                        short_notional += notional * 0.5;
                    }
                }
                event_count = event_count.saturating_add(1);
                recent_events.push(ev.clone());
            }

            if event_count == 0 {
                continue;
            }
            let cluster_notional = long_notional + short_notional;
            let dominant_side = if cluster_notional > 0.0 {
                let long_ratio = long_notional / cluster_notional;
                let short_ratio = short_notional / cluster_notional;
                if long_ratio >= DOMINANT_SIDE_RATIO {
                    LiquidationSide::LongLiquidated
                } else if short_ratio >= DOMINANT_SIDE_RATIO {
                    LiquidationSide::ShortLiquidated
                } else {
                    LiquidationSide::Mixed
                }
            } else {
                LiquidationSide::Mixed
            };

            pulses.insert(
                sym.clone(),
                LiquidationPulse {
                    recent_events,
                    cluster_notional_5m: cluster_notional,
                    long_notional_5m: long_notional,
                    short_notional_5m: short_notional,
                    event_count_5m: event_count,
                    dominant_side,
                    snapshot_ts_ms,
                },
            );
        }

        if pulses.is_empty() {
            return None;
        }

        Some(LiquidationPulsePanel {
            pulses,
            snapshot_ts_ms,
            source_tier: SOURCE_TIER.to_string(),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap as StdHashMap;

    fn make_liquidation_event(
        symbol: &str,
        side: &str,
        qty: f64,
        price: f64,
        ts_ms: u64,
    ) -> PriceEvent {
        let mut ev = PriceEvent::new(symbol.to_string(), price, ts_ms);
        ev.event_kind = Some(PriceEventKind::Liquidation);
        let mut meta = StdHashMap::new();
        meta.insert("type".into(), "liquidation".into());
        meta.insert("side".into(), side.into());
        meta.insert("qty".into(), qty.to_string());
        ev.metadata = meta;
        ev
    }

    fn make_aggregator() -> LiquidationPulseAggregator {
        LiquidationPulseAggregator::new(vec![
            "BTCUSDT".to_string(),
            "ETHUSDT".to_string(),
            "SOLUSDT".to_string(),
        ])
    }

    /// 為什麼測 BB cor-side：side 映射寫反 = alpha 反向 = trade loss。
    /// 本 test 是 aggregator 層的契約 lock — parser 改了也不能改這個語義。
    #[test]
    fn test_bb_corside_buy_maps_to_long_liquidated() {
        let mut agg = make_aggregator();
        let ev = make_liquidation_event("BTCUSDT", "Buy", 0.5, 60_000.0, 1_700_000_000_000);
        agg.on_liquidation(&ev);
        let snap = agg
            .snapshot_panel(1_700_000_001_000)
            .expect("snapshot must be Some after Buy event");
        let btc = snap.pulse_for("BTCUSDT").expect("BTCUSDT pulse present");
        assert_eq!(btc.dominant_side, LiquidationSide::LongLiquidated);
        assert!((btc.long_notional_5m - 30_000.0).abs() < 1e-6);
        assert!((btc.short_notional_5m).abs() < 1e-9);
        assert_eq!(btc.event_count_5m, 1);
    }

    #[test]
    fn test_bb_corside_sell_maps_to_short_liquidated() {
        let mut agg = make_aggregator();
        let ev = make_liquidation_event("ETHUSDT", "Sell", 2.0, 3_000.0, 1_700_000_000_000);
        agg.on_liquidation(&ev);
        let snap = agg
            .snapshot_panel(1_700_000_001_000)
            .expect("snapshot must be Some after Sell event");
        let eth = snap.pulse_for("ETHUSDT").expect("ETHUSDT pulse present");
        assert_eq!(eth.dominant_side, LiquidationSide::ShortLiquidated);
        assert!((eth.short_notional_5m - 6_000.0).abs() < 1e-6);
        assert!((eth.long_notional_5m).abs() < 1e-9);
    }

    /// 為什麼測 mixed dominant：50/50 邊界毛刺；佔比 < 60% 即 Mixed，
    /// 避免「微弱多空均衡」被誤標為單向 alpha。
    #[test]
    fn test_dominant_side_mixed_when_below_threshold() {
        let mut agg = make_aggregator();
        // 50/50 → Mixed
        agg.on_liquidation(&make_liquidation_event(
            "BTCUSDT",
            "Buy",
            0.5,
            60_000.0,
            1_700_000_000_000,
        ));
        agg.on_liquidation(&make_liquidation_event(
            "BTCUSDT",
            "Sell",
            0.5,
            60_000.0,
            1_700_000_000_500,
        ));
        let snap = agg
            .snapshot_panel(1_700_000_001_000)
            .expect("snapshot must be Some");
        let btc = snap.pulse_for("BTCUSDT").expect("BTCUSDT present");
        assert_eq!(btc.dominant_side, LiquidationSide::Mixed);
        assert_eq!(btc.event_count_5m, 2);
        assert!((btc.cluster_notional_5m - 60_000.0).abs() < 1e-6);
    }

    /// 為什麼測 per-symbol 隔離：清算是局部現象；BTC cluster 不該污染 ETH pulse。
    #[test]
    fn test_per_symbol_isolation() {
        let mut agg = make_aggregator();
        agg.on_liquidation(&make_liquidation_event(
            "BTCUSDT",
            "Buy",
            1.0,
            60_000.0,
            1_700_000_000_000,
        ));
        agg.on_liquidation(&make_liquidation_event(
            "ETHUSDT",
            "Sell",
            10.0,
            3_000.0,
            1_700_000_000_100,
        ));
        let snap = agg
            .snapshot_panel(1_700_000_001_000)
            .expect("snapshot must be Some");
        assert_eq!(snap.symbol_count(), 2);
        let btc = snap.pulse_for("BTCUSDT").unwrap();
        let eth = snap.pulse_for("ETHUSDT").unwrap();
        assert_eq!(btc.dominant_side, LiquidationSide::LongLiquidated);
        assert_eq!(eth.dominant_side, LiquidationSide::ShortLiquidated);
        // BTC + ETH 各算各的，不交叉污染
        assert!((btc.cluster_notional_5m - 60_000.0).abs() < 1e-6);
        assert!((eth.cluster_notional_5m - 30_000.0).abs() < 1e-6);
    }

    /// 為什麼測 non-cohort silent skip：non-cohort symbol 大量強平不應撐爆
    /// panel 也不該被策略消費（fail-closed 契約由 cohort 邊界執行）。
    #[test]
    fn test_non_cohort_silent_skip() {
        let mut agg = make_aggregator();
        agg.on_liquidation(&make_liquidation_event(
            "DOGEUSDT", // 非 cohort
            "Buy",
            10000.0,
            0.5,
            1_700_000_000_000,
        ));
        assert_eq!(agg.symbol_history_count(), 0);
        assert!(agg.snapshot_panel(1_700_000_001_000).is_none());
    }

    /// 為什麼測 5m 視窗 boundary：舊於 5m 的事件必被排除；策略只看 5m
    /// reaction window，不能讓 1h 前的 outlier 污染當前 pulse。
    #[test]
    fn test_5m_window_excludes_old_events() {
        let mut agg = make_aggregator();
        // 6 分鐘前的事件
        agg.on_liquidation(&make_liquidation_event(
            "BTCUSDT",
            "Buy",
            1.0,
            60_000.0,
            1_699_999_640_000, // snapshot_ts - 360s = 6 分鐘前
        ));
        // 1 分鐘前的事件
        agg.on_liquidation(&make_liquidation_event(
            "BTCUSDT",
            "Sell",
            0.5,
            60_000.0,
            1_699_999_940_000, // snapshot_ts - 60s
        ));
        let snap = agg
            .snapshot_panel(1_700_000_000_000)
            .expect("snapshot must be Some");
        let btc = snap.pulse_for("BTCUSDT").expect("BTCUSDT present");
        // 只有 1 分鐘前的 Sell event 在 5m 視窗內
        assert_eq!(btc.event_count_5m, 1);
        assert_eq!(btc.dominant_side, LiquidationSide::ShortLiquidated);
        assert!((btc.short_notional_5m - 30_000.0).abs() < 1e-6);
    }

    /// 為什麼測 history retention margin：trim cutoff 帶 60s margin 確保 60s
    /// flush boundary 不誤刪 5m 視窗邊緣事件。
    #[test]
    fn test_trim_retains_margin_for_window_boundary() {
        let mut agg = make_aggregator();
        // 5m 視窗邊緣 + 1s 的 entry：不該被 trim
        let edge_ts = 1_700_000_000_000 - WINDOW_5M_MS - 1_000;
        agg.on_liquidation(&make_liquidation_event(
            "BTCUSDT",
            "Buy",
            1.0,
            60_000.0,
            edge_ts as u64,
        ));
        agg.on_liquidation(&make_liquidation_event(
            "BTCUSDT",
            "Sell",
            1.0,
            60_000.0,
            1_700_000_000_000,
        ));
        // history 應有 2 entries（edge_ts 在 retention margin 內保留）
        assert_eq!(agg.history_len_for("BTCUSDT"), 2);
    }

    /// 為什麼測 non-Liquidation variant silent skip：上游 ws_client/dispatch
    /// 雖按 topic 路由，aggregator 仍應只認 Liquidation event_kind，避免
    /// 上游配線錯誤誤入。
    #[test]
    fn test_non_liquidation_event_kind_silent_skip() {
        let mut agg = make_aggregator();
        let mut ev = PriceEvent::new("BTCUSDT".to_string(), 60_000.0, 1_700_000_000_000);
        ev.event_kind = Some(PriceEventKind::Trade); // 非 Liquidation
        agg.on_liquidation(&ev);
        assert_eq!(agg.symbol_history_count(), 0);
    }

    /// 為什麼測 invalid side metadata silent skip：parser 雖過濾 Buy/Sell，
    /// 此處 defensive 確保 aggregator 不會被未預期 metadata 污染。
    #[test]
    fn test_invalid_side_metadata_silent_skip() {
        let mut agg = make_aggregator();
        agg.on_liquidation(&make_liquidation_event(
            "BTCUSDT",
            "Unknown",
            1.0,
            60_000.0,
            1_700_000_000_000,
        ));
        assert_eq!(agg.symbol_history_count(), 0);
    }

    /// 為什麼測 missing qty / unparseable price：parser 已 filter 但
    /// aggregator 端 defensive guard 應拒絕 NaN / 0 / negative 進 history。
    #[test]
    fn test_invalid_qty_or_price_silent_skip() {
        let mut agg = make_aggregator();
        // qty=0
        agg.on_liquidation(&make_liquidation_event(
            "BTCUSDT",
            "Buy",
            0.0,
            60_000.0,
            1_700_000_000_000,
        ));
        // price=0
        let mut ev_bad_price = make_liquidation_event(
            "BTCUSDT",
            "Buy",
            1.0,
            60_000.0,
            1_700_000_000_100,
        );
        ev_bad_price.last_price = 0.0;
        agg.on_liquidation(&ev_bad_price);
        assert_eq!(agg.symbol_history_count(), 0);
    }

    /// 為什麼測 empty history → None：avoid 寫空 panel 進 IPC slot；
    /// 與 oi_delta_aggregator.snapshot_panel 行為對齊。
    #[test]
    fn test_empty_history_snapshot_returns_none() {
        let agg = make_aggregator();
        assert!(agg.snapshot_panel(1_700_000_000_000).is_none());
    }

    /// 為什麼測 5m 視窗外全空 → None：history 有資料但都過期 → panel 不該 publish
    /// （避免「全 zero pulse」誤導下游策略以為「有 panel 但無 cluster」）。
    #[test]
    fn test_all_events_outside_window_returns_none() {
        let mut agg = make_aggregator();
        // 10 分鐘前的事件
        agg.on_liquidation(&make_liquidation_event(
            "BTCUSDT",
            "Buy",
            1.0,
            60_000.0,
            1_699_999_400_000,
        ));
        // snapshot_ts_ms 10 分鐘後 → 視窗 5m 內無事件
        assert!(agg.snapshot_panel(1_700_000_000_000).is_none());
    }

    /// 為什麼測 max events cap：高頻 burst 防護；視窗內事件超出 cap 應 LRU 拋舊。
    #[test]
    fn test_max_events_per_symbol_cap() {
        let mut agg = make_aggregator();
        // 灌 MAX + 50 events，所有時戳同 5m 視窗內
        let base_ts = 1_700_000_000_000_u64;
        for i in 0..(MAX_EVENTS_PER_SYMBOL + 50) {
            agg.on_liquidation(&make_liquidation_event(
                "BTCUSDT",
                "Buy",
                0.01,
                60_000.0,
                base_ts + i as u64,
            ));
        }
        // history 應限於 MAX_EVENTS_PER_SYMBOL
        assert_eq!(agg.history_len_for("BTCUSDT"), MAX_EVENTS_PER_SYMBOL);
    }

    /// 為什麼測 source_tier 不變式：下游 B-REM-5 SourceAvailability 接線會用
    /// 此字串對齊 AvailabilitySource enum；錯字會破壞 healthcheck 分類。
    #[test]
    fn test_snapshot_source_tier_stable() {
        let mut agg = make_aggregator();
        agg.on_liquidation(&make_liquidation_event(
            "BTCUSDT",
            "Buy",
            1.0,
            60_000.0,
            1_700_000_000_000,
        ));
        let snap = agg.snapshot_panel(1_700_000_001_000).expect("snapshot");
        assert_eq!(snap.source_tier, "bybit_v5_ws_all_liquidation");
        assert_eq!(snap.snapshot_ts_ms, 1_700_000_001_000);
    }
}
