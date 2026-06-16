//! recorder-v2：有狀態 per-symbol L1 本地簿重建 + BBO 變更事件流。
//!
//! MODULE_NOTE (中): recorder-v2 的核心。v1 的 ObTopSampler 是「無狀態 + 時間
//!   節流取樣」，對 delta 把「第一個*變更*檔」誤當 top-of-book（campaign-8
//!   14.7% crossed/locked/single-side-zero bad ticks 的直接根因）。本模組維護
//!   per-symbol 本地簿（bids/asks 各一個 BTreeMap），逐筆 apply Bybit
//!   orderbook.50 的 snapshot（reset+load 全簿）/ delta（upsert，qty==0 刪除，
//!   亂序容忍）/ u==1 reset，解析出真正的 best-bid（簿中最高買價）與 best-ask
//!   （簿中最低賣價），**僅在解析後 BBO 真的變化時** emit 一筆
//!   `MarketDataMsg::L1Event`。
//!
//!   硬邊界 / 不變量：
//!   - 純 in-memory，O(log 50) per update，無 await、無鎖、不阻塞熱路徑（由
//!     消費執行緒 process_market_events 呼叫，非 WS 讀迴圈）。
//!   - fail-soft：缺 update_id / 非有限值 / 缺 BBO 一律丟整筆（絕不寫 colliding 0
//!     或髒值；對齊 v1 sanitize_f64 慣例）。
//!   - per-symbol 1 秒硬 rate-cap 安全閥（circuit-breaker，非 sampler）：正常市況
//!     永不觸發、保留 full BBO 粒度；病態 flapping feed 下提供「rows ≤ cap × 37
//!     symbol × 86400 s/day」的可證上界，使儲存與 channel 壓力有界。
//!
//! MODULE_NOTE (EN): recorder-v2 stateful per-symbol L1 book reconstruction.
//!   Maintains a BTreeMap bid/ask book per symbol, applies snapshot/delta/reset,
//!   resolves true BBO, emits MarketDataMsg::L1Event only on resolved-BBO change,
//!   bounded by a per-symbol 1s rate-cap circuit breaker. No I/O, no await, no lock.

use crate::database::MarketDataMsg;
use std::cmp::Ordering;
use std::collections::{BTreeMap, HashMap};

/// 默認 per-symbol 每秒最大 L1Event 數（rate-cap 安全閥）。
/// 為什麼是 50：直接綁定 PA 儲存親算的 worst-case 上界——cap=50/s 才推得出已公告的
/// ~8.4 GB/週 compressed 駐留天花板（PA/memory.md）；orderbook.50 的 ~20ms cadence
/// ⇒ 理論 ~50 msg/s 上限，realistic blended ~6-15 BBO 變更/s/sym，故 50 對正常市況
/// 仍有充足 headroom（永不誤截），同時封頂病態 flapping feed 使儲存有界。default 設
/// 80 會讓公告的 ~8.4 GB/週天花板失準（真 worst-case ~13.4 GB/週），故收緊至 50 與
/// 親算同源。可由 OPENCLAW_L1_MAX_EVENTS_PER_SEC_PER_SYMBOL 覆蓋。
pub const L1_DEFAULT_MAX_EVENTS_PER_SEC_PER_SYMBOL: u64 = 50;

/// f64 價格的全序 key（BTreeMap 需 Ord，但 f64 只有 PartialOrd）。
///
/// 為什麼安全：價格在進入 tracker 前已由 parser fail-soft 過濾掉 NaN/Inf
/// （parse_all_levels 的 is_finite 檢查），故此處比較的恆是有限值；
/// total_cmp 對有限值與 partial_cmp 一致。仍以 total_cmp 兜底，杜絕 panic。
#[derive(Debug, Clone, Copy)]
struct OrderedF64(f64);

impl PartialEq for OrderedF64 {
    fn eq(&self, other: &Self) -> bool {
        self.0.total_cmp(&other.0) == Ordering::Equal
    }
}
impl Eq for OrderedF64 {}
impl PartialOrd for OrderedF64 {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}
impl Ord for OrderedF64 {
    fn cmp(&self, other: &Self) -> Ordering {
        self.0.total_cmp(&other.0)
    }
}

/// per-symbol 本地簿：bids/asks 各一個 price→size 的 BTreeMap。
/// best-bid = bids 中最大 key（last_key_value）；best-ask = asks 中最小 key（first_key_value）。
#[derive(Debug, Default)]
struct SymbolBook {
    bids: BTreeMap<OrderedF64, f64>,
    asks: BTreeMap<OrderedF64, f64>,
}

impl SymbolBook {
    /// snapshot / reset：清空後載入全簿。
    fn load_snapshot(&mut self, bids: &[(f64, f64)], asks: &[(f64, f64)]) {
        self.bids.clear();
        self.asks.clear();
        self.apply_levels(bids, asks);
    }

    /// delta：upsert 變更檔；qty==0 刪除該檔。亂序天然由 BTreeMap 吸收。
    fn apply_delta(&mut self, bids: &[(f64, f64)], asks: &[(f64, f64)]) {
        self.apply_levels(bids, asks);
    }

    fn apply_levels(&mut self, bids: &[(f64, f64)], asks: &[(f64, f64)]) {
        for &(price, qty) in bids {
            if qty == 0.0 {
                self.bids.remove(&OrderedF64(price));
            } else {
                self.bids.insert(OrderedF64(price), qty);
            }
        }
        for &(price, qty) in asks {
            if qty == 0.0 {
                self.asks.remove(&OrderedF64(price));
            } else {
                self.asks.insert(OrderedF64(price), qty);
            }
        }
    }

    /// 解析 BBO：(best_bid, bid_size, best_ask, ask_size)。任一側空 → None。
    fn resolve_bbo(&self) -> Option<(f64, f64, f64, f64)> {
        let (bb, bs) = self.bids.last_key_value()?; // 最高買價
        let (ba, as_) = self.asks.first_key_value()?; // 最低賣價
        Some((bb.0, *bs, ba.0, *as_))
    }
}

/// per-symbol 1 秒滑動視窗 rate counter（rate-cap 安全閥）。
#[derive(Debug, Clone, Copy, Default)]
struct RateWindow {
    window_start_ms: u64,
    count: u64,
    /// 本 symbol 因 rate-cap 累計丟棄數（warn 週期性輸出，非逐筆）。
    dropped: u64,
}

/// recorder-v2 有狀態 L1 book tracker。由 TickPipeline 擁有，flag-OFF 時不被呼叫。
#[derive(Debug)]
pub struct L1BookTracker {
    books: HashMap<String, SymbolBook>,
    /// 上次 emit 的 BBO 元組（emit-on-change 去重；f32 鏡像落盤精度）。
    last_emitted: HashMap<String, (f32, f32, f32, f32)>,
    rate: HashMap<String, RateWindow>,
    max_per_sec: u64,
}

impl L1BookTracker {
    pub fn new(max_per_sec: u64) -> Self {
        Self {
            books: HashMap::new(),
            last_emitted: HashMap::new(),
            rate: HashMap::new(),
            max_per_sec,
        }
    }

    /// 從 env 讀 rate-cap（OPENCLAW_L1_MAX_EVENTS_PER_SEC_PER_SYMBOL），
    /// 缺省 L1_DEFAULT_MAX_EVENTS_PER_SEC_PER_SYMBOL（=50，綁 PA ~8.4 GB/週天花板）。
    pub fn from_env() -> Self {
        let cap = std::env::var("OPENCLAW_L1_MAX_EVENTS_PER_SEC_PER_SYMBOL")
            .ok()
            .and_then(|s| s.parse::<u64>().ok())
            .filter(|&v| v > 0)
            .unwrap_or(L1_DEFAULT_MAX_EVENTS_PER_SEC_PER_SYMBOL);
        Self::new(cap)
    }

    /// 接收一筆 orderbook 消息（snapshot 或 delta），apply 後若 BBO 變化則 emit。
    ///
    /// 回傳 `Some(MarketDataMsg::L1Event)` = 應落盤的 BBO 變更；`None` = 無變化 /
    /// 被 rate-cap 丟棄 / fail-soft 丟棄。
    ///
    /// fail-soft：缺 `update_id`（Bybit 漏 u）直接丟整筆——絕不以 0 落盤，否則會
    /// 在 PK (symbol, ts, update_id) 上 colliding（PA risk「PK COLLISION」）。
    #[allow(clippy::too_many_arguments)]
    pub fn record(
        &mut self,
        symbol: &str,
        msg_type: Option<&str>,
        changed_bids: &[(f64, f64)],
        changed_asks: &[(f64, f64)],
        update_id: Option<u64>,
        seq: Option<u64>,
        ts_ms: u64,
    ) -> Option<MarketDataMsg> {
        // fail-soft：缺 update_id 一律丟（防 PK colliding 0）。
        let update_id = update_id?;

        // snapshot 判定：type=="snapshot" 或 u==1（服務重啟）→ reset+load 全簿。
        // 否則視為 delta（upsert / qty==0 刪除）。type 是 load-bearing：缺它時
        // 退而以 u==1 兜底（首見 symbol 亦走 load 分支，見下）。
        let is_snapshot = matches!(msg_type, Some("snapshot")) || update_id == 1;

        let book = self.books.entry(symbol.to_string()).or_default();
        if is_snapshot {
            book.load_snapshot(changed_bids, changed_asks);
        } else if book.bids.is_empty() && book.asks.is_empty() {
            // 首見 symbol 卻收到 delta（尚無 snapshot 基底）：當作初始 load，
            // 避免半截簿；後續 delta 正常 upsert。
            book.load_snapshot(changed_bids, changed_asks);
        } else {
            book.apply_delta(changed_bids, changed_asks);
        }

        // 解析 BBO；任一側空（全被刪光）→ 不 emit（fail-soft）。
        let (best_bid, bid_size, best_ask, ask_size) = book.resolve_bbo()?;
        if !best_bid.is_finite()
            || !bid_size.is_finite()
            || !best_ask.is_finite()
            || !ask_size.is_finite()
        {
            return None;
        }

        // emit-on-change：以 f32（落盤精度）比較，避免 f64 噪音造無謂 emit。
        let tuple = (
            best_bid as f32,
            bid_size as f32,
            best_ask as f32,
            ask_size as f32,
        );
        if self.last_emitted.get(symbol) == Some(&tuple) {
            return None;
        }

        // ── rate-cap 安全閥（circuit breaker）：per-symbol 1s 滑動視窗硬上界 ──
        // 正常市況 emit-on-change 後遠低於 cap，永不觸發；病態 flapping 才封頂。
        let win = self.rate.entry(symbol.to_string()).or_default();
        let sec = ts_ms / 1000;
        if win.window_start_ms != sec {
            win.window_start_ms = sec;
            win.count = 0;
        }
        if win.count >= self.max_per_sec {
            win.dropped = win.dropped.saturating_add(1);
            // 注意：被 cap 丟棄時**不**更新 last_emitted —— 否則視窗滾動後會誤判
            // 「無變化」而漏掉真實 BBO（last_emitted 必須恆等於「真正落盤過」的值）。
            return None;
        }
        win.count += 1;

        self.last_emitted.insert(symbol.to_string(), tuple);

        Some(MarketDataMsg::L1Event {
            ts_ms,
            symbol: symbol.to_string(),
            best_bid,
            bid_size,
            best_ask,
            ask_size,
            update_id,
            seq: seq.unwrap_or(0),
            is_snapshot,
        })
    }

    /// 某 symbol 因 rate-cap 累計丟棄數（供 warn 週期性輸出 / 測試）。
    pub fn dropped_count(&self, symbol: &str) -> u64 {
        self.rate.get(symbol).map(|w| w.dropped).unwrap_or(0)
    }

    pub fn len(&self) -> usize {
        self.books.len()
    }

    pub fn is_empty(&self) -> bool {
        self.books.is_empty()
    }
}

// ═══════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    fn bbo(msg: &MarketDataMsg) -> (f64, f64, f64, f64, u64, u64, bool) {
        match msg {
            MarketDataMsg::L1Event {
                best_bid,
                bid_size,
                best_ask,
                ask_size,
                update_id,
                seq,
                is_snapshot,
                ..
            } => (
                *best_bid,
                *bid_size,
                *best_ask,
                *ask_size,
                *update_id,
                *seq,
                *is_snapshot,
            ),
            _ => panic!("expected L1Event"),
        }
    }

    #[test]
    fn test_snapshot_load_emits_bbo() {
        let mut t = L1BookTracker::new(80);
        let bids = vec![(100.0, 5.0), (99.0, 4.0)];
        let asks = vec![(101.0, 7.0), (102.0, 3.0)];
        let m = t
            .record("BTCUSDT", Some("snapshot"), &bids, &asks, Some(10), Some(1), 1_000)
            .expect("snapshot emits");
        let (bb, bs, ba, as_, u, seq, snap) = bbo(&m);
        assert!((bb - 100.0).abs() < 1e-9);
        assert!((bs - 5.0).abs() < 1e-9);
        assert!((ba - 101.0).abs() < 1e-9);
        assert!((as_ - 7.0).abs() < 1e-9);
        assert_eq!(u, 10);
        assert_eq!(seq, 1);
        assert!(snap);
    }

    #[test]
    fn test_delta_upsert_changes_bbo() {
        let mut t = L1BookTracker::new(80);
        t.record("BTCUSDT", Some("snapshot"), &[(100.0, 5.0)], &[(101.0, 7.0)], Some(10), Some(1), 1_000);
        // delta：新增更高買價 100.5 → BBO 移動。
        let m = t
            .record("BTCUSDT", Some("delta"), &[(100.5, 2.0)], &[], Some(11), Some(2), 1_010)
            .expect("bbo moved emits");
        let (bb, bs, ba, ..) = bbo(&m);
        assert!((bb - 100.5).abs() < 1e-9);
        assert!((bs - 2.0).abs() < 1e-9);
        assert!((ba - 101.0).abs() < 1e-9);
    }

    #[test]
    fn test_delta_qty_zero_deletes_current_best_next_becomes_bbo() {
        // 核心正確性（PA risk「CORRECTNESS highest」）：刪除當前 best，次優成為新 BBO。
        let mut t = L1BookTracker::new(80);
        t.record(
            "BTCUSDT",
            Some("snapshot"),
            &[(100.0, 5.0), (99.0, 4.0), (98.0, 3.0)],
            &[(101.0, 7.0), (102.0, 6.0)],
            Some(10),
            Some(1),
            1_000,
        );
        // 刪除 best-bid 100.0（qty=0）→ 次優 99.0 成為新 best-bid。
        let m = t
            .record("BTCUSDT", Some("delta"), &[(100.0, 0.0)], &[], Some(11), Some(2), 1_010)
            .expect("delete best -> next best emits");
        let (bb, bs, ..) = bbo(&m);
        assert!((bb - 99.0).abs() < 1e-9, "next-best bid becomes BBO after delete");
        assert!((bs - 4.0).abs() < 1e-9);
    }

    #[test]
    fn test_unsorted_delta_resolves_correctly() {
        let mut t = L1BookTracker::new(80);
        // 亂序 snapshot（BTreeMap 吸收排序）。
        let m = t
            .record(
                "BTCUSDT",
                Some("snapshot"),
                &[(98.0, 1.0), (100.0, 5.0), (99.0, 4.0)],
                &[(103.0, 2.0), (101.0, 7.0), (102.0, 3.0)],
                Some(10),
                Some(1),
                1_000,
            )
            .expect("emits");
        let (bb, _, ba, ..) = bbo(&m);
        assert!((bb - 100.0).abs() < 1e-9, "highest bid resolved regardless of input order");
        assert!((ba - 101.0).abs() < 1e-9, "lowest ask resolved regardless of input order");
    }

    #[test]
    fn test_u_eq_1_resets_book() {
        let mut t = L1BookTracker::new(80);
        t.record(
            "BTCUSDT",
            Some("delta"),
            &[(100.0, 5.0), (99.0, 4.0)],
            &[(101.0, 7.0)],
            Some(10),
            Some(1),
            1_000,
        );
        // u==1：服務重啟 → reset+load 全新簿（舊 99.0/100.0 全清，只剩新檔）。
        let m = t
            .record("BTCUSDT", Some("delta"), &[(200.0, 1.0)], &[(201.0, 1.0)], Some(1), Some(2), 2_000)
            .expect("reset emits");
        let (bb, _, ba, _, _, _, snap) = bbo(&m);
        assert!((bb - 200.0).abs() < 1e-9, "old book cleared on u==1 reset");
        assert!((ba - 201.0).abs() < 1e-9);
        assert!(snap, "u==1 treated as snapshot/reset boundary");
    }

    #[test]
    fn test_emit_only_on_bbo_change() {
        let mut t = L1BookTracker::new(80);
        t.record("BTCUSDT", Some("snapshot"), &[(100.0, 5.0)], &[(101.0, 7.0)], Some(10), Some(1), 1_000);
        // delta 只動更深檔（98.0），不改 BBO → 不 emit。
        assert!(t
            .record("BTCUSDT", Some("delta"), &[(98.0, 9.0)], &[], Some(11), Some(2), 1_010)
            .is_none());
        // delta 把同樣的 best-bid 重設成同值 → 仍無變化 → 不 emit。
        assert!(t
            .record("BTCUSDT", Some("delta"), &[(100.0, 5.0)], &[], Some(12), Some(3), 1_020)
            .is_none());
        // best-bid size 變化 → emit。
        assert!(t
            .record("BTCUSDT", Some("delta"), &[(100.0, 8.0)], &[], Some(13), Some(4), 1_030)
            .is_some());
    }

    #[test]
    fn test_missing_update_id_dropped() {
        // fail-soft：缺 u 丟整筆（防 PK colliding 0）。
        let mut t = L1BookTracker::new(80);
        assert!(t
            .record("BTCUSDT", Some("snapshot"), &[(100.0, 5.0)], &[(101.0, 7.0)], None, Some(1), 1_000)
            .is_none());
        assert!(t.is_empty(), "no book created on dropped frame");
    }

    #[test]
    fn test_one_sided_book_no_emit() {
        // 只有一側（ask 全被刪光）→ resolve_bbo None → 不 emit。
        let mut t = L1BookTracker::new(80);
        t.record("BTCUSDT", Some("snapshot"), &[(100.0, 5.0)], &[(101.0, 7.0)], Some(10), Some(1), 1_000);
        // 刪掉唯一 ask → ask 側空。
        assert!(t
            .record("BTCUSDT", Some("delta"), &[], &[(101.0, 0.0)], Some(11), Some(2), 1_010)
            .is_none());
    }

    #[test]
    fn test_rate_cap_drops_overflow_and_counts() {
        // rate-cap 安全閥：1s 視窗內超過 cap 的 BBO 變更被丟棄並計數。
        let mut t = L1BookTracker::new(3); // cap=3/s 便於測
        t.record("BTCUSDT", Some("snapshot"), &[(100.0, 1.0)], &[(101.0, 1.0)], Some(1), Some(1), 5_000);
        let mut emits = 1; // snapshot 已 emit 1 筆（窗 sec=5，count=1）
        // 同一秒（5_000..5_999ms）內製造大量 BBO 變化。
        for i in 0..20u64 {
            let bid = 100.0 + (i as f64 + 1.0) * 0.1; // 每次 best-bid 都變
            if t
                .record("BTCUSDT", Some("delta"), &[(bid, 1.0)], &[], Some(10 + i), Some(10 + i), 5_500)
                .is_some()
            {
                emits += 1;
            }
        }
        assert_eq!(emits, 3, "rate-cap hard upper bound = 3/s");
        assert!(t.dropped_count("BTCUSDT") > 0, "drops are counted");
    }

    #[test]
    fn test_rate_cap_window_rolls_next_second() {
        let mut t = L1BookTracker::new(2);
        t.record("BTCUSDT", Some("snapshot"), &[(100.0, 1.0)], &[(101.0, 1.0)], Some(1), Some(1), 5_000); // count=1 @sec5
        assert!(t
            .record("BTCUSDT", Some("delta"), &[(100.5, 1.0)], &[], Some(2), Some(2), 5_100)
            .is_some()); // count=2 @sec5
        assert!(t
            .record("BTCUSDT", Some("delta"), &[(100.6, 1.0)], &[], Some(3), Some(3), 5_200)
            .is_none()); // 超 cap，drop
        // 下一秒視窗滾動，重新可 emit。
        assert!(t
            .record("BTCUSDT", Some("delta"), &[(100.7, 1.0)], &[], Some(4), Some(4), 6_000)
            .is_some());
    }

    #[test]
    fn test_per_symbol_independent() {
        let mut t = L1BookTracker::new(80);
        assert!(t
            .record("BTCUSDT", Some("snapshot"), &[(100.0, 1.0)], &[(101.0, 1.0)], Some(1), Some(1), 1_000)
            .is_some());
        assert!(t
            .record("ETHUSDT", Some("snapshot"), &[(50.0, 1.0)], &[(51.0, 1.0)], Some(1), Some(1), 1_000)
            .is_some());
        assert_eq!(t.len(), 2);
    }
}
