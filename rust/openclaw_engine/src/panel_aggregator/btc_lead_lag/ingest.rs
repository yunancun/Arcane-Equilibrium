use std::sync::Arc;

use openclaw_types::{PriceEvent, PriceEventKind};
use tokio::sync::{mpsc, RwLock};
use tokio_util::sync::CancellationToken;
use tracing::{debug, info};

use super::{BTC_BOOK_IMBALANCE_TOP_N, BTC_ORDERBOOK_SYMBOL};

/// W2-IMPL-1 — `BtcOrderbookSlot`：BTC top-N book imbalance 最新值的 RwLock slot。
///
/// 設計（per dispatch §3.1 acceptance criteria 1-6 + E2 重點 1-4 + spec §3.1.3）：
/// - **WS-first**：值來自 ingest task 消費 `mpsc::Receiver<Arc<PriceEvent>>` 過濾
///   `event_kind == PriceEventKind::Orderbook && symbol == "BTCUSDT"` 的 push event
///   （既有 fan-out 既存 ws subscription，**不**新增 connection / 不 polling）。
/// - **NaN sentinel**：尚無 snapshot / snapshot 缺 bid+ask → `None`；caller 寫
///   V088 `btc_book_imbalance` 時 cast 為 `f32::NAN`，PG 接 NaN literal；下游
///   evaluator `WHERE NOT btc_book_imbalance = 'NaN'::REAL` 過濾。
/// - **NaN propagation safety**：`compute_btc_book_imbalance` 對 `bids/asks` 空、
///   sum=0、NaN qty 全 fail-soft → return `None`；snapshot.btc_book_imbalance 不
///   寫 0.0 假值，避免 lost evidence。
/// - **lookahead-free**：60s timer tick 時讀 slot snapshot ≈ 「current 1m bucket
///   完成時最新 orderbook 狀態」；orderbook event ts ≤ snapshot_ts_ms（current
///   timer tick）— natural shift(1)，無 future leak。
/// - **Rate budget**：0 req/s（純 WS push，既有 connection 數不變）。
///
/// `Arc<RwLock<Option<f64>>>` 而非 `f64` atomic 是為了：
/// - `None` 哨值表「尚無 fresh data」
/// - 與 `BtcLeadLagPanelSlot` 一致命名約定（panel_aggregator 內慣例）
/// - write 頻率 ~100 Hz（BTCUSDT orderbook update rate）但 read 頻率 1/60s，
///   RwLock contention 可忽略
pub type BtcOrderbookSlot = Arc<RwLock<Option<f64>>>;

/// W2-IMPL-1 — 工廠：建立空 `BtcOrderbookSlot`（None = 尚無 snapshot）。
pub fn create_btc_orderbook_slot() -> BtcOrderbookSlot {
    Arc::new(RwLock::new(None))
}

/// W2-IMPL-1 — 純函數：計算 top-N book imbalance ∈ [-1, +1]。
///
/// 公式（per spec §3.1.3）：
/// `imbalance = (sum(bid_qty[0..N]) - sum(ask_qty[0..N])) / (sum(bid_qty) + sum(ask_qty))`
///
/// **不變量 / Invariants**：
/// - `bids` / `asks` 為 `(price, qty)` tuple slice，price/qty 預期 > 0（parsers
///   已過濾無效字串）。NaN qty 在 sum 階段傳染 → `denom.is_nan()` → return None。
/// - top-N truncation：取最多前 N 檔（不足 N 時 fail-soft 仍算，per Cont &
///   Kukanov 2017 sparse-book 容忍）。
/// - 空 `bids` 或空 `asks` → 不對稱 → return None（不可信 imbalance 信號）。
/// - `denom <= 0` → return None（避免除零或負分母）。
/// - 結果 NaN（如 numerator NaN）→ return None（fail-closed，下游 NULL 寫入）。
///
/// Return：
/// - `Some(f64)`：有效 imbalance，clamp 到 [-1, +1]（防 numerical precision drift）
/// - `None`：資料不足或計算失敗（caller 寫 NaN 進 panel）
pub fn compute_btc_book_imbalance(
    bids: &[(f64, f64)],
    asks: &[(f64, f64)],
    top_n: usize,
) -> Option<f64> {
    if bids.is_empty() || asks.is_empty() {
        return None;
    }
    let bid_qty: f64 = bids.iter().take(top_n).map(|&(_, q)| q).sum();
    let ask_qty: f64 = asks.iter().take(top_n).map(|&(_, q)| q).sum();
    if !bid_qty.is_finite() || !ask_qty.is_finite() {
        return None;
    }
    let denom = bid_qty + ask_qty;
    if denom <= 0.0 || !denom.is_finite() {
        return None;
    }
    let imbalance = (bid_qty - ask_qty) / denom;
    if !imbalance.is_finite() {
        return None;
    }
    // Clamp [-1, +1]：numerical precision drift（如 sum overflow）防護。
    Some(imbalance.clamp(-1.0, 1.0))
}

/// W2-IMPL-1 — Ingest task：從 fan-out arm 收 `PriceEvent`，過濾 BTCUSDT Orderbook
/// event，計算 top-N imbalance，寫入 slot。
///
/// 設計：
/// - **單 task / 單 BTC symbol**：本 task 只關心 BTCUSDT；其他 symbol 的 Orderbook
///   variant silent drop（per spec §3.1.3 只計算 BTC book imbalance）。
/// - **非 Orderbook variant skip**：Ticker / Trade / Kline 全 skip（不報錯，per
///   fan-out 設計：所有 PriceEvent variant 都過 panel arm，本 task 自選感興趣
///   的 subset）。
/// - **cancel-safe**：tokio::select! cancel.cancelled() 即 break；mpsc::recv 回
///   `None` 也 break（上游 fan-out 關閉）。
/// - **lookahead-free**：寫 slot 時不關心當前 60s timer phase；自然對齊到
///   producer.on_tick 時 latest snapshot ≤ tick ts（WS push 必早於 60s timer
///   tick 因 orderbook update rate ~100 Hz）。
/// - **無 PG / 無 lock contention 風險**：write lock ~1 µs（一個 f64 replace），
///   read lock 1/60s rate < 1 µs read。
pub async fn spawn_btc_orderbook_ingest_task(
    mut event_rx: mpsc::Receiver<Arc<PriceEvent>>,
    slot: BtcOrderbookSlot,
    cancel: CancellationToken,
) {
    info!(
        target: "panel_aggregator",
        symbol = BTC_ORDERBOOK_SYMBOL,
        top_n = BTC_BOOK_IMBALANCE_TOP_N,
        "BtcOrderbookIngest task start (W2-IMPL-1 wired)"
    );
    let mut total_events: u64 = 0;
    let mut btc_book_updates: u64 = 0;
    let mut drop_events: u64 = 0;

    loop {
        tokio::select! {
            _ = cancel.cancelled() => {
                info!(
                    target: "panel_aggregator",
                    total_events = total_events,
                    btc_book_updates = btc_book_updates,
                    drop_events = drop_events,
                    "BtcOrderbookIngest cancelled, shutting down"
                );
                return;
            }
            evt = event_rx.recv() => {
                match evt {
                    Some(price_event) => {
                        total_events = total_events.saturating_add(1);
                        // 過濾 1：必為 BTCUSDT
                        if price_event.symbol != BTC_ORDERBOOK_SYMBOL {
                            continue;
                        }
                        // 過濾 2：必為 Orderbook variant（其他 variant skip）
                        if price_event.event_kind != Some(PriceEventKind::Orderbook) {
                            continue;
                        }
                        // 過濾 3：必有 bids5 / asks5（parsers 應已填充；
                        // 缺失 = parser 故障或 legacy event，silent drop）
                        let bids = match price_event.bids5.as_ref() {
                            Some(b) if !b.is_empty() => b,
                            _ => {
                                drop_events = drop_events.saturating_add(1);
                                continue;
                            }
                        };
                        let asks = match price_event.asks5.as_ref() {
                            Some(a) if !a.is_empty() => a,
                            _ => {
                                drop_events = drop_events.saturating_add(1);
                                continue;
                            }
                        };
                        // 計算 top-N book imbalance
                        let imbalance = compute_btc_book_imbalance(
                            bids,
                            asks,
                            BTC_BOOK_IMBALANCE_TOP_N,
                        );
                        match imbalance {
                            Some(imb) => {
                                *slot.write().await = Some(imb);
                                btc_book_updates = btc_book_updates.saturating_add(1);
                                if btc_book_updates.is_multiple_of(1000) {
                                    debug!(
                                        target: "panel_aggregator",
                                        btc_book_updates = btc_book_updates,
                                        latest_imbalance = imb,
                                        "btc_orderbook ingest progress"
                                    );
                                }
                            }
                            None => {
                                drop_events = drop_events.saturating_add(1);
                            }
                        }
                    }
                    None => {
                        info!(
                            target: "panel_aggregator",
                            total_events = total_events,
                            "BtcOrderbookIngest upstream channel closed, exiting"
                        );
                        return;
                    }
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::panel_aggregator::btc_lead_lag::BtcLeadLagProducer;
    use std::collections::HashMap;

    fn make_cohort() -> Vec<String> {
        vec![
            "ETHUSDT".to_string(),
            "SOLUSDT".to_string(),
            "XRPUSDT".to_string(),
            "DOGEUSDT".to_string(),
            "ADAUSDT".to_string(),
            "AVAXUSDT".to_string(),
            "DOTUSDT".to_string(),
        ]
    }

    /// W2-IMPL-1 unit test 1：正 imbalance（bid > ask）→ (+0, +1]。
    /// 對齊 dispatch §3.1 E4 regression 重點 1 第一 fixture。
    #[test]
    fn compute_book_imbalance_positive_when_bid_heavy() {
        // bid top-5：5 × 2.0 = 10.0；ask top-5：5 × 1.0 = 5.0
        let bids: Vec<(f64, f64)> = (0..5).map(|i| (100.0 - i as f64, 2.0)).collect();
        let asks: Vec<(f64, f64)> = (0..5).map(|i| (101.0 + i as f64, 1.0)).collect();
        let imb = compute_btc_book_imbalance(&bids, &asks, BTC_BOOK_IMBALANCE_TOP_N)
            .expect("正 imbalance must return Some");
        // (10 - 5) / (10 + 5) = 0.333...
        assert!(
            (imb - (5.0 / 15.0)).abs() < 1e-9,
            "imb = {} expected 0.333...",
            imb
        );
        assert!(imb > 0.0 && imb <= 1.0, "imb must be in (0, +1]");
    }

    /// W2-IMPL-1 unit test 2：負 imbalance（ask > bid）→ [-1, -0)。
    #[test]
    fn compute_book_imbalance_negative_when_ask_heavy() {
        let bids: Vec<(f64, f64)> = (0..5).map(|i| (100.0 - i as f64, 0.5)).collect();
        let asks: Vec<(f64, f64)> = (0..5).map(|i| (101.0 + i as f64, 3.0)).collect();
        let imb = compute_btc_book_imbalance(&bids, &asks, BTC_BOOK_IMBALANCE_TOP_N)
            .expect("負 imbalance must return Some");
        // (2.5 - 15) / (2.5 + 15) = -12.5/17.5 ≈ -0.714
        assert!(
            (imb - (-12.5 / 17.5)).abs() < 1e-9,
            "imb = {} expected -0.714...",
            imb
        );
        assert!(imb >= -1.0 && imb < 0.0, "imb must be in [-1, 0)");
    }

    /// W2-IMPL-1 unit test 3：完全平衡（bid == ask）→ 0.0。
    #[test]
    fn compute_book_imbalance_zero_when_balanced() {
        let bids: Vec<(f64, f64)> = (0..5).map(|i| (100.0 - i as f64, 1.0)).collect();
        let asks: Vec<(f64, f64)> = (0..5).map(|i| (101.0 + i as f64, 1.0)).collect();
        let imb = compute_btc_book_imbalance(&bids, &asks, BTC_BOOK_IMBALANCE_TOP_N)
            .expect("平衡 case must return Some(0.0)");
        assert!(
            imb.abs() < 1e-12,
            "balanced book imbalance = {} expected 0",
            imb
        );
    }

    /// W2-IMPL-1 unit test 4：NaN edge case + 空 levels → None（fail-soft，不寫 0.0 假值）。
    /// 對齊 dispatch §3.1 acceptance criteria 4 + E2 重點 3。
    #[test]
    fn compute_book_imbalance_none_on_nan_or_empty() {
        // 空 bids
        let asks_only: Vec<(f64, f64)> = vec![(101.0, 1.0)];
        assert!(
            compute_btc_book_imbalance(&[], &asks_only, 5).is_none(),
            "empty bids must return None"
        );
        // 空 asks
        let bids_only: Vec<(f64, f64)> = vec![(100.0, 1.0)];
        assert!(
            compute_btc_book_imbalance(&bids_only, &[], 5).is_none(),
            "empty asks must return None"
        );
        // 兩端皆空
        assert!(
            compute_btc_book_imbalance(&[], &[], 5).is_none(),
            "both empty must return None"
        );
        // NaN qty
        let bids_nan: Vec<(f64, f64)> = vec![(100.0, f64::NAN), (99.0, 1.0)];
        let asks_ok: Vec<(f64, f64)> = vec![(101.0, 1.0)];
        assert!(
            compute_btc_book_imbalance(&bids_nan, &asks_ok, 5).is_none(),
            "NaN qty must propagate to None"
        );
        // sum = 0（所有 qty 0）
        let zero_bids: Vec<(f64, f64)> = vec![(100.0, 0.0)];
        let zero_asks: Vec<(f64, f64)> = vec![(101.0, 0.0)];
        assert!(
            compute_btc_book_imbalance(&zero_bids, &zero_asks, 5).is_none(),
            "denom=0 must return None"
        );
    }

    /// W2-IMPL-1 unit test 5：top-N truncation — 超過 N 檔的尾段不算進 numerator。
    /// 驗 spec §3.1.3 「top-N」語義（不是全 book）。
    #[test]
    fn compute_book_imbalance_top_n_truncation() {
        // 6 檔 bids（top-5 = 5x1.0=5.0；第 6 檔 100.0 不算）
        let mut bids: Vec<(f64, f64)> = (0..5).map(|i| (100.0 - i as f64, 1.0)).collect();
        bids.push((94.0, 100.0)); // 第 6 檔，不應被計入
        let asks: Vec<(f64, f64)> = (0..5).map(|i| (101.0 + i as f64, 1.0)).collect();
        let imb = compute_btc_book_imbalance(&bids, &asks, 5).expect("top-5 must succeed");
        // 5/10 = 0.5? no — top-5 only：5.0 vs 5.0 → 0.0
        assert!(
            imb.abs() < 1e-12,
            "top-5 truncated balanced imb = {} expected 0",
            imb
        );
    }

    /// W2-IMPL-1 unit test 6：on_tick 收 Some(imbalance) → snapshot 寫真實值；
    /// 收 None → snapshot 寫 NaN（不寫 0.0 假值）。
    /// 對齊 dispatch §3.1 acceptance criteria 1 + 4。
    #[test]
    fn on_tick_writes_real_book_imbalance_or_nan() {
        let mut p = BtcLeadLagProducer::new(make_cohort());
        let alt_closes = HashMap::new();

        // case 1：Some(0.42) → snapshot 寫 0.42
        let snap1 = p.on_tick(60_000, 50_000.0, 100.0, &alt_closes, Some(0.42));
        assert!(
            (snap1.btc_book_imbalance - 0.42).abs() < 1e-9,
            "btc_book_imbalance = {} expected 0.42",
            snap1.btc_book_imbalance
        );
        assert!(
            !snap1.btc_book_imbalance.is_nan(),
            "Some(value) must not write NaN"
        );

        // case 2：None → snapshot 寫 NaN
        let snap2 = p.on_tick(120_000, 50_100.0, 100.0, &alt_closes, None);
        assert!(
            snap2.btc_book_imbalance.is_nan(),
            "None must write NaN (NOT 0.0 fake), got {}",
            snap2.btc_book_imbalance
        );
    }

    /// W2-IMPL-1 integration test：5-tick mock WS Orderbook event → ingest task →
    /// slot 寫入 → on_tick 讀 → 5 個 snapshot 全非 0.0 / 非 NaN。
    /// 對齊 dispatch §3.1 E4 regression 重點 2「5-tick integration test」+
    /// acceptance criteria 1 (非 0.0 placeholder) + 5 (7d ≥ 90% non-null 驗證雛形)。
    #[tokio::test]
    async fn ingest_task_to_producer_5_tick_integration() {
        let slot = create_btc_orderbook_slot();
        let cancel = CancellationToken::new();
        let (tx, rx) = mpsc::channel::<Arc<PriceEvent>>(32);

        // spawn ingest task
        let ingest_slot = Arc::clone(&slot);
        let ingest_cancel = cancel.clone();
        let ingest_handle = tokio::spawn(async move {
            spawn_btc_orderbook_ingest_task(rx, ingest_slot, ingest_cancel).await;
        });

        // 餵 5 個 BTCUSDT Orderbook event（不同 imbalance pattern）
        let event_specs: [(Vec<(f64, f64)>, Vec<(f64, f64)>); 5] = [
            // tick 1：正 (bid 2.0 vs ask 1.0)
            (vec![(100.0, 2.0); 5], vec![(101.0, 1.0); 5]),
            // tick 2：負 (bid 0.5 vs ask 1.5)
            (vec![(100.0, 0.5); 5], vec![(101.0, 1.5); 5]),
            // tick 3：平衡
            (vec![(100.0, 1.0); 5], vec![(101.0, 1.0); 5]),
            // tick 4：強正
            (vec![(100.0, 3.0); 5], vec![(101.0, 0.5); 5]),
            // tick 5：強負
            (vec![(100.0, 0.2); 5], vec![(101.0, 2.0); 5]),
        ];

        // 收集每 tick 後 producer.on_tick 看到的 imbalance
        let mut producer = BtcLeadLagProducer::new(make_cohort());
        let alt_closes = HashMap::new();
        let mut observed_imbalances: Vec<f64> = Vec::new();

        for (i, (bids, asks)) in event_specs.iter().enumerate() {
            let mut ev = PriceEvent::new(
                BTC_ORDERBOOK_SYMBOL.to_string(),
                100.5,
                60_000 + i as u64 * 60_000,
            );
            ev.event_kind = Some(PriceEventKind::Orderbook);
            ev.bids5 = Some(bids.clone());
            ev.asks5 = Some(asks.clone());
            tx.send(Arc::new(ev)).await.expect("send tick");

            // 等 ingest task 處理（lock contention 極短，10ms 足夠）
            tokio::time::sleep(std::time::Duration::from_millis(10)).await;

            // 讀 slot snapshot
            let imb_opt = *slot.read().await;
            let imb = imb_opt.expect("slot must have value after 10ms");
            observed_imbalances.push(imb);

            // 餵 producer on_tick 模擬 60s timer
            let snap = producer.on_tick(
                60_000 + i as i64 * 60_000,
                50_000.0 + i as f64,
                100.0,
                &alt_closes,
                imb_opt,
            );

            // dispatch §3.1 acceptance criteria 1：非 0.0 placeholder（除非 tick 3 是真平衡 0.0）
            // dispatch §3.1 acceptance criteria 4：非 NaN（5 tick 都 mock 有 fresh event）
            assert!(
                !snap.btc_book_imbalance.is_nan(),
                "tick {}：btc_book_imbalance must be real, not NaN",
                i
            );
        }

        // 驗 5 tick 全收到（dispatch §3.1 acceptance criteria 5 雛形）。
        // imbalance 期望值（per fixture）：
        //   tick 1: (10-5)/(15) = +0.333 (bid 2.0 × 5 vs ask 1.0 × 5)
        //   tick 2: (2.5-7.5)/(10) = -0.500 (bid 0.5 × 5 vs ask 1.5 × 5)
        //   tick 3: (5-5)/(10) = 0.0 (平衡)
        //   tick 4: (15-2.5)/(17.5) = +0.714 (bid 3.0 × 5 vs ask 0.5 × 5)
        //   tick 5: (1-10)/(11) = -0.818 (bid 0.2 × 5 vs ask 2.0 × 5)
        assert_eq!(observed_imbalances.len(), 5);
        assert!(
            observed_imbalances[0] > 0.2 && observed_imbalances[0] < 0.5,
            "tick 1 mid-positive expected ~0.333, got {}",
            observed_imbalances[0]
        );
        assert!(
            observed_imbalances[1] < -0.4,
            "tick 2 strong negative < -0.4 expected ~-0.500, got {}",
            observed_imbalances[1]
        );
        assert!(observed_imbalances[2].abs() < 1e-9, "tick 3 balanced ≈ 0");
        assert!(
            observed_imbalances[3] > 0.6,
            "tick 4 strong positive > 0.6 expected ~0.714, got {}",
            observed_imbalances[3]
        );
        assert!(
            observed_imbalances[4] < -0.7,
            "tick 5 strong negative < -0.7 expected ~-0.818, got {}",
            observed_imbalances[4]
        );

        // shutdown ingest task
        cancel.cancel();
        let _ = tokio::time::timeout(std::time::Duration::from_millis(500), ingest_handle).await;
    }

    /// W2-IMPL-1 unit test：ingest task 對 non-BTCUSDT / non-Orderbook event silent drop。
    /// 確保不污染 slot 也不 panic。
    #[tokio::test]
    async fn ingest_task_drops_non_btc_or_non_orderbook_event() {
        let slot = create_btc_orderbook_slot();
        let cancel = CancellationToken::new();
        let (tx, rx) = mpsc::channel::<Arc<PriceEvent>>(8);

        let ingest_slot = Arc::clone(&slot);
        let ingest_cancel = cancel.clone();
        let handle = tokio::spawn(async move {
            spawn_btc_orderbook_ingest_task(rx, ingest_slot, ingest_cancel).await;
        });

        // event 1：ETHUSDT Orderbook（symbol 過濾）— drop
        let mut eth_ob = PriceEvent::new("ETHUSDT".to_string(), 2500.0, 60_000);
        eth_ob.event_kind = Some(PriceEventKind::Orderbook);
        eth_ob.bids5 = Some(vec![(2499.0, 1.0); 5]);
        eth_ob.asks5 = Some(vec![(2501.0, 1.0); 5]);
        tx.send(Arc::new(eth_ob)).await.unwrap();

        // event 2：BTCUSDT Ticker（variant 過濾）— drop
        let mut btc_ticker = PriceEvent::new(BTC_ORDERBOOK_SYMBOL.to_string(), 50_000.0, 60_000);
        btc_ticker.event_kind = Some(PriceEventKind::Ticker);
        tx.send(Arc::new(btc_ticker)).await.unwrap();

        tokio::time::sleep(std::time::Duration::from_millis(20)).await;

        // slot 應仍為 None（無 valid event 寫入）
        let slot_val = *slot.read().await;
        assert!(
            slot_val.is_none(),
            "slot should remain None after filtered-out events, got {:?}",
            slot_val
        );

        cancel.cancel();
        let _ = tokio::time::timeout(std::time::Duration::from_millis(500), handle).await;
    }
}
