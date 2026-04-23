//! Bybit instrument info cache — symbol lot sizes, tick sizes, min notional (R-05).
//! Bybit 合約信息緩存 — 交易對步長、tick 精度、最小名義值。
//!
//! MODULE_NOTE (EN): Fetches GET /v5/market/instruments-info and caches symbol
//!   specifications. Provides rounding helpers for qty and price to comply with
//!   exchange precision requirements. Cache can be refreshed periodically.
//! MODULE_NOTE (中): 獲取 GET /v5/market/instruments-info 並緩存交易對規格。
//!   提供 qty 和 price 取整輔助函數以符合交易所精度要求。緩存可定期刷新。

use crate::bybit_rest_client::{BybitApiError, BybitRestClient, BybitResult};
use async_trait::async_trait;
use parking_lot::{Mutex, RwLock};
use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::{Notify, Semaphore};
use tracing::{info, warn};

// ---------------------------------------------------------------------------
// SymbolSpec — per-symbol trading spec / 單交易對交易規格
// ---------------------------------------------------------------------------

/// Trading specification for a single symbol.
/// 單個交易對的交易規格。
#[derive(Debug, Clone, serde::Serialize)]
pub struct SymbolSpec {
    /// Symbol name, e.g. "BTCUSDT" / 交易對名稱
    pub symbol: String,
    /// Base currency, e.g. "BTC" / 基礎貨幣
    pub base_currency: String,
    /// Quote currency, e.g. "USDT" / 計價貨幣
    pub quote_currency: String,
    /// Contract type: "LinearPerpetual", "InversePerpetual", etc.
    /// 合約類型
    pub contract_type: String,
    /// Lot size step (qty precision), e.g. 0.001 for BTC / 步長精度
    pub qty_step: f64,
    /// Minimum order quantity / 最小下單數量
    pub min_qty: f64,
    /// Maximum order quantity / 最大下單數量
    pub max_qty: f64,
    /// Tick size (price precision), e.g. 0.10 for BTCUSDT / Tick 精度
    pub tick_size: f64,
    /// Minimum price / 最小價格
    pub min_price: f64,
    /// Maximum price / 最大價格
    pub max_price: f64,
    /// Minimum notional value (qty * price), 0 if not available / 最小名義值
    pub min_notional: f64,
    /// Number of decimal places for qty (derived from qty_step) / qty 小數位數
    pub qty_decimals: u32,
    /// Number of decimal places for price (derived from tick_size) / price 小數位數
    pub price_decimals: u32,
}

impl SymbolSpec {
    /// Round quantity down to the nearest qty_step (floor).
    /// 將數量向下取整到最近的 qty_step（地板除法）。
    ///
    /// Floor is used to avoid exceeding available balance.
    /// 使用 floor 避免超過可用餘額。
    pub fn round_qty(&self, qty: f64) -> f64 {
        if self.qty_step <= 0.0 || qty <= 0.0 {
            return 0.0;
        }
        let floored = (qty / self.qty_step).floor() * self.qty_step;
        round_to_decimals(floored, self.qty_decimals)
    }

    /// Round price to the nearest tick_size.
    /// 將價格取整到最近的 tick_size。
    pub fn round_price(&self, price: f64) -> f64 {
        if self.tick_size <= 0.0 || price <= 0.0 {
            return 0.0;
        }
        let rounded = (price / self.tick_size).round() * self.tick_size;
        round_to_decimals(rounded, self.price_decimals)
    }

    /// Round price down (floor) — conservative for long stop-loss.
    /// 價格向下取整（floor）— 適用於多頭止損。
    pub fn floor_price(&self, price: f64) -> f64 {
        if self.tick_size <= 0.0 || price <= 0.0 {
            return 0.0;
        }
        let floored = (price / self.tick_size).floor() * self.tick_size;
        round_to_decimals(floored, self.price_decimals)
    }

    /// Round price up (ceil) — conservative for short stop-loss.
    /// 價格向上取整（ceil）— 適用於空頭止損。
    pub fn ceil_price(&self, price: f64) -> f64 {
        if self.tick_size <= 0.0 || price <= 0.0 {
            return 0.0;
        }
        let ceiled = (price / self.tick_size).ceil() * self.tick_size;
        round_to_decimals(ceiled, self.price_decimals)
    }

    /// Validate an order's qty and price against exchange limits.
    /// 驗證訂單的 qty 和 price 是否符合交易所限制。
    ///
    /// Returns (valid, reason). If valid is false, reason explains why.
    /// 返回 (valid, reason)。若 valid 為 false，reason 說明原因。
    pub fn validate_order(&self, qty: f64, price: f64) -> (bool, String) {
        if qty < self.min_qty {
            return (false, format!("qty {qty} < min_qty {}", self.min_qty));
        }
        if qty > self.max_qty {
            return (false, format!("qty {qty} > max_qty {}", self.max_qty));
        }
        if price > 0.0 {
            if price < self.min_price {
                return (
                    false,
                    format!("price {price} < min_price {}", self.min_price),
                );
            }
            if self.max_price > 0.0 && price > self.max_price {
                return (
                    false,
                    format!("price {price} > max_price {}", self.max_price),
                );
            }
            if self.min_notional > 0.0 && qty * price < self.min_notional {
                return (
                    false,
                    format!(
                        "notional {:.4} < min_notional {}",
                        qty * price,
                        self.min_notional
                    ),
                );
            }
        }
        (true, String::new())
    }
}

// ---------------------------------------------------------------------------
// InstrumentInfoCache / 合約信息緩存
// ---------------------------------------------------------------------------

// ---------------------------------------------------------------------------
// INSTR-ENSURE-1 — lazy single-symbol fetch trait (2026-04-23)
// INSTR-ENSURE-1 — 單 symbol 按需拉取抽象（2026-04-23）
// ---------------------------------------------------------------------------

/// Abstraction over Bybit's single-symbol instruments-info endpoint.
/// Exists purely so `ensure_symbol` can be unit-tested without a live REST
/// client: tests implement this trait with an in-memory mock + call counter.
///
/// 單 symbol instruments-info 抽象。只為了 `ensure_symbol` 可以用 mock +
/// 計數器做單測（不打網）。
///
/// Contract:
///   * `Ok(Some(serde_json::Value))` — Bybit responded 200 with a non-empty
///     `result.list[0]` item (exchange confirmed symbol exists).
///   * `Ok(None)` — Bybit responded 200 with an empty `result.list` (Bybit
///     denies the symbol). Caller enters neg cache.
///   * `Err(..)` — transport / timeout / 5xx / business error. Caller must NOT
///     enter neg cache (prevents cache poisoning on transient failures).
///
/// 契約：
///   * `Ok(Some(..))` — Bybit 回 200 + list 非空（交易所確認存在）。
///   * `Ok(None)` — Bybit 回 200 + list 空（Bybit 否認）→ 入 neg cache。
///   * `Err(..)` — 網路/timeout/5xx/業務錯 → **不入** neg cache（防 poisoning）。
#[async_trait]
pub trait SingleSymbolFetcher: Send + Sync {
    async fn fetch_single_symbol(
        &self,
        category: &str,
        symbol: &str,
    ) -> BybitResult<Option<serde_json::Value>>;
}

/// Live adapter: `BybitRestClient` fetches from Bybit with a 2s hard timeout
/// (fail-fast on hot path — dispatch can't wait on a stuck connect).
///
/// Live 適配器：BybitRestClient 2s 硬超時（熱路徑失敗快速，不等 hang）。
#[async_trait]
impl SingleSymbolFetcher for BybitRestClient {
    async fn fetch_single_symbol(
        &self,
        category: &str,
        symbol: &str,
    ) -> BybitResult<Option<serde_json::Value>> {
        // 2s hard timeout on the hot order path — if Bybit stalls, fail closed
        // and let dispatch's fail-closed path reject this order instead of
        // blocking on a dead socket.
        // 熱路徑 2s 硬超時：Bybit 卡住 → 讓下單 fail-closed 拒單，不阻塞。
        let params = [("category", category), ("symbol", symbol)];
        let fut = self.get("/v5/market/instruments-info", &params);
        let resp = match tokio::time::timeout(Duration::from_secs(2), fut).await {
            Ok(r) => r?,
            Err(_) => {
                return Err(BybitApiError::Business {
                    ret_code: -1,
                    ret_msg: format!(
                        "ensure_symbol timeout after 2s for {symbol} / 2s 超時"
                    ),
                    response: serde_json::json!({"timeout_ms": 2000, "symbol": symbol}),
                });
            }
        };

        if resp.ret_code != 0 {
            // Business error from exchange → treat as transient; do not poison neg cache.
            // 業務錯（例如 10001 參數錯）→ 視為瞬時，**不入** neg cache，保守拒單。
            return Err(BybitApiError::Business {
                ret_code: resp.ret_code,
                ret_msg: resp.ret_msg.clone(),
                response: serde_json::to_value(&resp).unwrap_or_default(),
            });
        }

        let list = resp.result.get("list").and_then(|v| v.as_array());
        let first = list.and_then(|arr| arr.first()).cloned();
        Ok(first)
    }
}

/// Thread-safe instrument info cache.
/// 線程安全的合約信息緩存。
pub struct InstrumentInfoCache {
    /// Map of symbol -> SymbolSpec / 交易對 -> 規格 映射
    /// pub(crate) for test access from sibling modules / pub(crate) 供兄弟模組測試存取
    pub(crate) cache: RwLock<HashMap<String, SymbolSpec>>,

    /// INSTR-ENSURE-1: negative cache — symbols Bybit explicitly denied.
    /// Entry value = insertion `Instant`; TTL = `NEG_CACHE_TTL`.
    /// INSTR-ENSURE-1：否定快取 — Bybit 明確否認的 symbol。TTL 60s。
    negative_cache: RwLock<HashMap<String, Instant>>,

    /// INSTR-ENSURE-1: singleflight by symbol — concurrent ensures for the same
    /// symbol only issue one REST call; others subscribe to the `InflightEntry`.
    /// INSTR-ENSURE-1：symbol 維度 singleflight — 同 symbol 併發只打 1 次。
    ///
    /// INSTR-ENSURE-FIX-1 (2026-04-23, B-1): upgraded value type from
    /// `Arc<Notify>` → `Arc<InflightEntry>` so followers can observe a
    /// `done` flag in addition to subscribing to the Notify. The precise
    /// race this closes is a snapshot-counter ordering window: a `Notified`
    /// future captures the Notify's internal `notify_waiters_calls` counter
    /// at **construction time** (before the first `.poll()`). If the leader
    /// calls `notify_waiters()` AFTER the follower `.notified()` call has
    /// snapshotted the counter but BEFORE the follower polls the future
    /// (or enables its waker slot), the counter bump happens during the
    /// "pre-enable" window — but if the leader bumps the counter BEFORE
    /// the follower constructs `.notified()`, the follower's snapshot
    /// equals the current counter value, the first poll sees no mismatch,
    /// and it simply registers a waker and sleeps. No pending permit
    /// remains, and no future `notify_waiters()` is issued, so the waker
    /// is never fired → follower sleeps forever. With the `done`
    /// AtomicBool we publish the "leader finished" fact BEFORE bumping
    /// the counter. Followers enable the waker first (to catch any
    /// POST-enable counter bump) THEN Acquire-load `done`; if `done==true`
    /// we short-circuit the `.await` entirely, bypassing the snapshot
    /// window. required for correctness.
    /// INSTR-ENSURE-FIX-1：inflight 值升級為 InflightEntry，含 done 旗標 +
    /// Notify。race 本質：`Notified` 在 construction 時 snapshot
    /// `notify_waiters_calls` counter；若 leader 在 follower 呼
    /// `.notified()` 之前已 bump counter，follower 的 snapshot 等於
    /// 當前值，poll 時無 mismatch，只登記 waker 睡死。
    /// 修復：`done` 在 counter bump 前先 Release-store；follower 先
    /// enable waker 再 Acquire-load done，true 則跳 await 繞過 snapshot
    /// 窗。required for correctness。
    inflight: Mutex<HashMap<String, Arc<InflightEntry>>>,

    /// INSTR-ENSURE-1: global semaphore to cap concurrent ensure_symbol REST
    /// calls (prevents scanner-storm from multi-miss burst).
    /// INSTR-ENSURE-1：全域併發上限，防 scanner 多 miss 風暴。
    ensure_semaphore: Arc<Semaphore>,
}

/// Negative-cache TTL (60s). A symbol Bybit denied once is silently rejected
/// for this long before we retry.
/// 負緩存 TTL（60s）。Bybit 一旦否認，60s 內直接拒單不重試。
const NEG_CACHE_TTL: Duration = Duration::from_secs(60);

/// Max concurrent single-symbol ensure calls — prevents a multi-symbol scanner
/// sweep from fan-outing REST calls faster than Bybit's rate limit window.
/// 最大併發 ensure 呼叫數 — 防 scanner 多 symbol 同時 fan-out 爆 rate limit。
const ENSURE_CONCURRENCY: usize = 4;

impl InstrumentInfoCache {
    /// Create an empty cache.
    /// 創建空緩存。
    pub fn new() -> Self {
        Self {
            cache: RwLock::new(HashMap::new()),
            negative_cache: RwLock::new(HashMap::new()),
            inflight: Mutex::new(HashMap::new()),
            ensure_semaphore: Arc::new(Semaphore::new(ENSURE_CONCURRENCY)),
        }
    }

    /// Refresh cache by fetching instrument info from Bybit.
    /// 通過從 Bybit 獲取合約信息刷新緩存。
    ///
    /// INSTR-PAGINATE-1 (2026-04-23): cursor loop + limit=1000 + max_pages=10.
    /// Bybit `/v5/market/instruments-info` linear has > 500 symbols; single-page
    /// fetch (the pre-fix behaviour) silently dropped every symbol alphabetically
    /// after ~"SOONUSDT" (XRP/ZEC/SUI/STRK/SPK/UB...), causing OrderManager
    /// M-1 fail-closed to reject every scanner-routed order for those names.
    /// Today's `fills=0` root cause.
    ///
    /// INSTR-PAGINATE-1（2026-04-23）：cursor 迴圈 + limit=1000 + max_pages=10 護欄。
    /// Bybit linear 超過 500 symbol；單頁拉取會讓字母序 > "SOONUSDT" 的 symbol
    /// 全部從 cache 缺席，導致 M-1 fail-closed 全面拒單，今日 fills=0 根因。
    pub async fn refresh(&self, client: &BybitRestClient, category: &str) -> BybitResult<usize> {
        const MAX_PAGES: usize = 10;
        const PAGE_LIMIT: &str = "1000";

        let mut cursor = String::new();
        let mut total = 0usize;
        let mut pages = 0usize;

        loop {
            pages += 1;
            if pages > MAX_PAGES {
                // PAGINATE-METRIC-1 (2026-04-23, P1-5): hard cap hit. This is
                // a soft signal — Bybit's linear universe has grown past our
                // expected ceiling (10_000 symbols @ 1000/page). Promote to
                // warn! so operators can spot it in log tailing; on a healthy
                // exchange universe this line should never emit. If it does,
                // raise MAX_PAGES or page_limit and redeploy.
                // PAGINATE-METRIC-1（2026-04-23，P1-5）：硬上限觸發。若出現此
                // log 代表 Bybit linear 宇宙已超越預期，operator 應調大 MAX_PAGES。
                tracing::error!(
                    category = category,
                    max_pages = MAX_PAGES,
                    total_so_far = total,
                    "instrument info pagination hit max_pages guard — aborting loop / 分頁達硬上限，強制停止"
                );
                warn!(
                    category = category,
                    pages = MAX_PAGES,
                    "refresh hit MAX_PAGES cap — possible Bybit linear universe growth beyond cache expectation, add metric/alert / 達頂可能代表 Bybit 宇宙擴張，建議加 metric/alert"
                );
                break;
            }

            // Build params — always include category + limit; cursor only if non-empty.
            // 構建 params — category + limit 必帶；cursor 非空才帶。
            let mut params: Vec<(&str, &str)> =
                vec![("category", category), ("limit", PAGE_LIMIT)];
            if !cursor.is_empty() {
                params.push(("cursor", cursor.as_str()));
            }

            let resp = client.get("/v5/market/instruments-info", &params).await?;

            if resp.ret_code != 0 {
                let ret_msg = resp.ret_msg.clone();
                return Err(BybitApiError::Business {
                    ret_code: resp.ret_code,
                    ret_msg,
                    response: serde_json::to_value(&resp).unwrap_or_default(),
                });
            }

            // Parse this page into the cache + get next cursor.
            // 解析本頁到 cache 並讀下一頁 cursor。
            let (page_count, next_cursor) = {
                let mut cache = self.cache.write();
                parse_page(&resp.result, &mut cache)
            };
            total += page_count;

            match next_cursor {
                Some(next) if !next.is_empty() => {
                    cursor = next;
                }
                _ => break,
            }
        }

        info!(
            category = category,
            symbols = total,
            pages = pages,
            "instrument info refreshed / 合約信息已刷新"
        );

        // PAGINATE-METRIC-1: pages-utilisation signal. `pages > MAX_PAGES`
        // means the loop broke via the guard (already warn!-logged above).
        // `pages == MAX_PAGES` (exactly) = used the full envelope; warn so
        // operator sees it trending. `pages < MAX_PAGES` = healthy, debug-only.
        // PAGINATE-METRIC-1：分頁使用率訊號。達頂 warn，未達頂 debug。
        if pages == MAX_PAGES {
            warn!(
                category = category,
                pages = pages,
                max_pages = MAX_PAGES,
                "refresh used full pagination envelope — close to MAX_PAGES cap, consider raising limit / 分頁接近上限"
            );
        } else if pages < MAX_PAGES {
            tracing::debug!(
                category = category,
                pages = pages,
                max_pages = MAX_PAGES,
                "refresh pagination within envelope / 分頁在上限內"
            );
        }

        Ok(total)
    }

    /// Get the SymbolSpec for a given symbol.
    /// 取得指定交易對的 SymbolSpec。
    pub fn get(&self, symbol: &str) -> Option<SymbolSpec> {
        self.cache.read().get(symbol).cloned()
    }

    // -----------------------------------------------------------------------
    // INSTR-ENSURE-1 — lazy single-symbol fetch with neg cache + singleflight
    // INSTR-ENSURE-1 — 按需拉取 + 負緩存 + singleflight
    // -----------------------------------------------------------------------

    /// Ensure a symbol's spec is cached, fetching on demand if absent.
    /// See `ensure_symbol_with_fetcher` for the full protocol.
    ///
    /// 確保 symbol 的規格已緩存，缺失時按需向 Bybit 拉取。
    /// 詳細協議見 `ensure_symbol_with_fetcher`。
    pub async fn ensure_symbol(
        &self,
        client: &BybitRestClient,
        category: &str,
        symbol: &str,
    ) -> BybitResult<Option<SymbolSpec>> {
        self.ensure_symbol_with_fetcher(client, category, symbol)
            .await
    }

    /// Core ensure_symbol implementation, generic over `SingleSymbolFetcher`.
    ///
    /// Protocol / 協議：
    ///   1. Positive cache hit → return Some immediately (no network).
    ///   2. Negative cache hit (not TTL-expired) → return None immediately.
    ///   3. Singleflight: if another task is already fetching this symbol,
    ///      await its Notify, then re-check positive cache and return.
    ///   4. Otherwise acquire the global semaphore + install inflight slot,
    ///      call the fetcher, and:
    ///        - `Ok(Some(item))` → parse + insert positive cache → return Some.
    ///        - `Ok(None)` → insert fresh neg-cache entry → return None.
    ///        - `Err(_)` → do NOT poison neg cache (prevents transient-fail
    ///          cache poisoning) → propagate the error.
    ///   5. Always drain the inflight slot + notify waiters in a guard drop.
    ///
    /// 協議：
    ///   1. 正緩存 hit → 立即 Some（不打網）。
    ///   2. 負緩存 hit（TTL 內）→ 立即 None。
    ///   3. Singleflight：同 symbol 有 inflight → await Notify → 重查正緩存。
    ///   4. 否則 acquire semaphore + 裝 inflight → fetcher：
    ///        - Ok(Some) → 解析插正緩存 → Some。
    ///        - Ok(None) → 插新鮮負緩存 → None。
    ///        - Err → **不**入負緩存（防 poisoning）→ 傳錯。
    ///   5. Drop 時固定清 inflight + notify 等待者。
    pub async fn ensure_symbol_with_fetcher<F: SingleSymbolFetcher + ?Sized>(
        &self,
        fetcher: &F,
        category: &str,
        symbol: &str,
    ) -> BybitResult<Option<SymbolSpec>> {
        // Step 1: positive cache fast path / 正緩存快路徑
        if let Some(spec) = self.get(symbol) {
            return Ok(Some(spec));
        }

        // Step 2: negative cache check (TTL-gated) / 負緩存查驗（TTL 內拒）
        if self.neg_cache_hit(symbol) {
            return Ok(None);
        }

        // Step 3: singleflight — install or subscribe to inflight slot.
        //          Step 3：singleflight — 裝 / 訂閱 inflight 槽位。
        //
        // INSTR-ENSURE-FIX-1 (2026-04-23, B-1): lost-wakeup race fix.
        // See `InflightEntry` docs for the full ordering argument. Summary:
        //   * Leader on drop: Release-store `done=true`, then notify_waiters.
        //   * Follower here: enable() waker FIRST (registers in intrusive
        //     list), then Acquire-load `done`. If done==true, skip await.
        //     If done==false, it MUST have been false before the leader's
        //     Release store, therefore our enable() also happened before
        //     the leader's notify_waiters, therefore our waker will fire.
        //
        // INSTR-ENSURE-FIX-1（2026-04-23，B-1）：lost-wakeup 修復。
        // 詳見 InflightEntry 註解。要點：leader drop 時先 Release 寫 done
        // 再 notify_waiters；follower 先 enable waker 再 Acquire 讀 done。
        let (entry, is_leader) = {
            let mut inflight = self.inflight.lock();
            match inflight.get(symbol) {
                Some(existing) => (Arc::clone(existing), false),
                None => {
                    let entry = Arc::new(InflightEntry::new());
                    inflight.insert(symbol.to_string(), Arc::clone(&entry));
                    (entry, true)
                }
            }
        };

        if !is_leader {
            // Follower path — see InflightEntry / INSTR-ENSURE-FIX-1.
            // 跟隨者路徑 — 見 InflightEntry / INSTR-ENSURE-FIX-1。
            let notified_fut = entry.notify.notified();
            tokio::pin!(notified_fut);
            // (1) Register waker slot FIRST. Any leader notify_waiters()
            //     issued after this line will wake us.
            // (1) 先登記 waker。此後 leader 的 notify_waiters() 都會喚醒我們。
            notified_fut.as_mut().enable();
            // (2) Acquire-load done. Pairs with leader's Release-store in
            //     InflightGuard::drop. If we see true here, leader has
            //     finished and published all its cache writes — skip await.
            //     If we see false, leader has NOT yet executed its Release
            //     store, therefore has NOT yet called notify_waiters (since
            //     the guard drop does store-then-notify), so our enable()
            //     above necessarily precedes leader's notify and we will
            //     be woken when it fires.
            // (2) Acquire 讀 done，與 leader InflightGuard::drop 的 Release 配對。
            //     true 表示 leader 已完成，可跳 await；false 表示 leader 尚未
            //     notify，我們的 enable 必定早於 leader notify，會被喚醒。
            if !entry.done.load(Ordering::Acquire) {
                notified_fut.await;
            }

            if let Some(spec) = self.get(symbol) {
                return Ok(Some(spec));
            }
            if self.neg_cache_hit(symbol) {
                return Ok(None);
            }
            // Leader failed with Err and did not populate either cache — follower
            // returns the same "missing" signal (None). Caller's M-1 fail-closed
            // will reject this order; next call will trigger a fresh fetch.
            // 領導者錯誤未填 cache → 跟隨者回 None（M-1 會拒單）；下次觸發新 fetch。
            return Ok(None);
        }

        // Leader path: acquire semaphore + perform fetch.
        // 領導者路徑：acquire semaphore + 執行 fetch。
        let inflight_guard = InflightGuard {
            cache: self,
            symbol: symbol.to_string(),
            entry: Arc::clone(&entry),
        };

        let _permit = self
            .ensure_semaphore
            .clone()
            .acquire_owned()
            .await
            .map_err(|e| BybitApiError::Business {
                ret_code: -1,
                ret_msg: format!("ensure_symbol semaphore closed: {e}"),
                response: serde_json::json!(null),
            })?;

        let fetch_result = fetcher.fetch_single_symbol(category, symbol).await;

        match fetch_result {
            Ok(Some(item)) => {
                let parsed = parse_instrument_item(&item);
                match parsed {
                    Some(spec) => {
                        {
                            let mut cache = self.cache.write();
                            cache.insert(spec.symbol.clone(), spec.clone());
                        }
                        drop(inflight_guard); // explicit drop to notify waiters
                        Ok(Some(spec))
                    }
                    None => {
                        // INSTR-ENSURE-FIX-1 (2026-04-23, P1-1): parse failure
                        // is NOT neg-cached. Previously we inserted the symbol
                        // into the neg cache for 60s on parse failure, which
                        // is a schema-drift poisoning vector: if Bybit renames
                        // a required field (e.g. `lotSizeFilter` → something
                        // else), EVERY symbol's first post-rename fetch would
                        // fail to parse, poisoning the neg cache for 60s and
                        // causing OrderManager M-1 to fail-closed reject every
                        // order engine-wide for a full minute.
                        //
                        // Fix: return a transient Err instead. Caller's M-1
                        // still fail-closed rejects this specific order, but
                        // the neg cache stays clean so the next call issues a
                        // fresh fetch. The moment Bybit returns a parseable
                        // schema again (or we ship a parser update), the
                        // engine self-heals.
                        //
                        // INSTR-ENSURE-FIX-1（2026-04-23，P1-1）：解析失敗**不**入
                        // neg cache。舊實作若 Bybit 改 field name 會讓全部 symbol
                        // 首次拉取都 parse fail → 60s 全引擎拒單。修法：回傳
                        // 瞬時 Err，由 M-1 保守拒當前單，但 neg cache 保持乾淨，
                        // 下次會再打 API 自癒。
                        warn!(
                            symbol = symbol,
                            "ensure_symbol: Bybit returned item but parse failed — treated as transient Err, NOT neg-cached / 解析失敗視為瞬時錯誤，不入負緩存"
                        );
                        drop(inflight_guard);
                        Err(BybitApiError::Business {
                            ret_code: -1,
                            ret_msg: format!(
                                "parse failed for {symbol} — treated as transient, not neg-cached (possible Bybit schema drift) / 解析失敗視為瞬時錯誤（疑 Bybit schema 漂移）"
                            ),
                            response: serde_json::json!({
                                "symbol": symbol,
                                "reason": "parse_failed",
                            }),
                        })
                    }
                }
            }
            Ok(None) => {
                // Bybit confirms symbol does not exist → neg cache.
                // Bybit 確認不存在 → 負緩存。
                self.neg_cache_insert(symbol);
                drop(inflight_guard);
                Ok(None)
            }
            Err(e) => {
                // Transport / timeout / 5xx / business error — do NOT neg-cache.
                // 網路/超時/5xx/業務錯 — **不**入負緩存。
                drop(inflight_guard);
                Err(e)
            }
        }
    }

    fn neg_cache_hit(&self, symbol: &str) -> bool {
        let guard = self.negative_cache.read();
        match guard.get(symbol) {
            Some(ts) if ts.elapsed() < NEG_CACHE_TTL => true,
            _ => false,
        }
    }

    fn neg_cache_insert(&self, symbol: &str) {
        self.negative_cache
            .write()
            .insert(symbol.to_string(), Instant::now());
    }

    /// Get lot size (qty_step) for a symbol. Returns None if not cached.
    /// 取得交易對的步長。未緩存時返回 None。
    pub fn get_lot_size(&self, symbol: &str) -> Option<f64> {
        self.cache.read().get(symbol).map(|s| s.qty_step)
    }

    /// Get tick size for a symbol. Returns None if not cached.
    /// 取得交易對的 tick 精度。未緩存時返回 None。
    pub fn get_tick_size(&self, symbol: &str) -> Option<f64> {
        self.cache.read().get(symbol).map(|s| s.tick_size)
    }

    /// Round qty for a symbol using cached spec.
    /// 使用緩存的規格為交易對取整 qty。
    pub fn round_qty(&self, symbol: &str, qty: f64) -> Option<f64> {
        self.cache
            .read()
            .get(symbol)
            .map(|s: &SymbolSpec| s.round_qty(qty))
    }

    /// Round price for a symbol using cached spec.
    /// 使用緩存的規格為交易對取整 price。
    pub fn round_price(&self, symbol: &str, price: f64) -> Option<f64> {
        self.cache
            .read()
            .get(symbol)
            .map(|s: &SymbolSpec| s.round_price(price))
    }

    /// Get all cached symbols.
    /// 取得所有已緩存的交易對。
    pub fn symbols(&self) -> Vec<String> {
        self.cache.read().keys().cloned().collect()
    }

    /// Get number of cached symbols.
    /// 取得已緩存的交易對數量。
    pub fn len(&self) -> usize {
        self.cache.read().len()
    }

    /// Check if cache is empty.
    /// 檢查緩存是否為空。
    pub fn is_empty(&self) -> bool {
        self.cache.read().is_empty()
    }
}

impl Default for InstrumentInfoCache {
    fn default() -> Self {
        Self::new()
    }
}

// ---------------------------------------------------------------------------
// InflightEntry — per-symbol singleflight slot (done flag + Notify).
// InflightEntry — 單 symbol 的 singleflight 槽位（done 旗標 + Notify）。
// ---------------------------------------------------------------------------

/// Singleflight entry stored in `InstrumentInfoCache::inflight`.
///
/// Why we need `done` alongside `notify`:
///
/// The real (subtle) race is NOT just "notify_waiters() stores no permit".
/// `tokio::sync::Notify::Notified` captures an internal counter
/// (`notify_waiters_calls`) at **construction time**, before the first
/// `.poll()` call. Roughly:
///
/// ```text
///   let fut = notify.notified();       // <-- snapshots counter = K
///   // ... leader does notify_waiters() which bumps counter to K+1 ...
///   fut.poll();                        // sees current != snapshot → consume
/// ```
///
/// The common understanding "notify_waiters stores no permit so if follower
/// hasn't polled yet the notify is lost" is *directionally* correct but
/// imprecise. The precise failure mode for our singleflight is:
///
/// 1. Leader calls `notify_waiters()`, bumping the counter (before the
///    follower even constructs `.notified()`).
/// 2. Follower, scheduled later, constructs `notify.notified()`. The
///    `Notified` future snapshots the counter at its now-current value —
///    **equal** to the current counter because the bump already happened.
/// 3. Follower calls `enable()` / `.poll()`. Seeing `snapshot == current`,
///    the future finds no mismatch to consume, registers its waker in the
///    intrusive list, and suspends.
/// 4. No further `notify_waiters()` is ever issued (leader is done,
///    inflight slot already removed). Waker never fires → hang forever.
///
/// Fix: the leader publishes a separate `done` flag in the `InflightEntry`
/// BEFORE bumping the Notify counter, with Release ordering. The follower
/// enables its waker slot first (so any post-enable counter bump will wake
/// it), THEN Acquire-loads `done`. If `done == true`, the follower skips
/// `.await` entirely and re-reads the cache — this bypasses the snapshot
/// window completely. If `done == false`, the Acquire-load synchronises
/// with a future Release store that must occur before its paired
/// `notify_waiters()`, and since `enable()` has already installed the
/// waker, the follower is guaranteed to be woken. required for correctness.
///
/// Memory ordering:
///   * Leader: `done.store(true, Release)` → `notify_waiters()`.
///   * Follower: `enable()` → `done.load(Acquire)` → `.await` if false.
///   The Acquire load synchronises-with the Release store, so any observed
///   `done == true` guarantees the follower sees all cache writes the
///   leader performed BEFORE the store.
///
/// 真正的 race 不是「notify_waiters 無 permit」這麼簡單。`Notified` 在
/// construction 時 snapshot counter；若 leader 在 follower 建 `.notified()`
/// **之前**已 bump counter，follower snapshot 等於當前值，poll 時無
/// mismatch，直接登記 waker 睡死。修復機制：`done` 在 counter bump
/// 前先 Release-store；follower 先 enable 再 Acquire-load done，true
/// 則短路 `.await`，false 則由 Release/Acquire 配對保證後續 notify 會
/// 喚醒 follower。required for correctness。
struct InflightEntry {
    /// Set to `true` by the leader once its fetch + cache writes are complete.
    /// Load with Acquire ordering to synchronise-with the leader's Release store.
    /// Leader 完成後以 Release 寫 true；Follower 以 Acquire 讀，可見所有 cache 寫入。
    done: AtomicBool,
    /// Waiter list — leader calls `notify_waiters()` AFTER `done.store(true, Release)`.
    /// 等待者列表；Leader 在 store done 之後才呼叫 notify_waiters。
    notify: Notify,
}

impl InflightEntry {
    fn new() -> Self {
        Self {
            done: AtomicBool::new(false),
            notify: Notify::new(),
        }
    }
}

// ---------------------------------------------------------------------------
// InflightGuard — singleflight slot cleanup on drop (success or panic).
// InflightGuard — 無論 ensure 成功或 panic 都保證清 inflight + notify。
// ---------------------------------------------------------------------------

struct InflightGuard<'a> {
    cache: &'a InstrumentInfoCache,
    symbol: String,
    entry: Arc<InflightEntry>,
}

impl<'a> Drop for InflightGuard<'a> {
    fn drop(&mut self) {
        {
            let mut inflight = self.cache.inflight.lock();
            inflight.remove(&self.symbol);
        }
        // Order matters for the lost-wakeup fix (see InflightEntry docs):
        //   1. Mark done with Release ordering (publishes cache writes).
        //   2. Wake every follower awaiting this symbol's fetch.
        // A follower that observes done==true via Acquire load is
        // guaranteed to see the leader's prior cache writes; a follower
        // that observed done==false MUST have registered its waker via
        // enable() before this Release store, so notify_waiters() below
        // wakes it.
        // 順序關鍵（lost-wakeup 修復）：先 Release 寫 done，再 notify_waiters()。
        self.entry.done.store(true, Ordering::Release);
        self.entry.notify.notify_waiters();
    }
}

// ---------------------------------------------------------------------------
// Parsing helpers / 解析輔助函數
// ---------------------------------------------------------------------------

/// Parse a single page of Bybit `/v5/market/instruments-info` into the cache,
/// returning `(parsed_count, next_cursor)`.
///
/// 解析 Bybit `/v5/market/instruments-info` 單頁並寫入 cache，
/// 回傳 `(本頁新增計數, 下一頁 cursor)`。
///
/// `next_cursor` semantics:
///   * `Some(s)` when `result.nextPageCursor` is a non-empty string.
///   * `None` when missing, not a string, or empty (Bybit's end-of-pages signal).
///
/// `next_cursor` 語意：
///   * `result.nextPageCursor` 是非空字串時回 `Some(s)`。
///   * 缺失 / 非字串 / 空字串 → `None`（Bybit 末頁約定）。
///
/// Kept as a pure function so pagination logic is unit-testable without a live
/// HTTP client (INSTR-PAGINATE-1).
/// 保留為純函數，方便在無 HTTP 客戶端情況下單測分頁邏輯（INSTR-PAGINATE-1）。
pub(crate) fn parse_page(
    result: &serde_json::Value,
    cache: &mut HashMap<String, SymbolSpec>,
) -> (usize, Option<String>) {
    let list = result.get("list").and_then(|v| v.as_array());

    let mut count = 0usize;
    if let Some(items) = list {
        for item in items {
            if let Some(spec) = parse_instrument_item(item) {
                cache.insert(spec.symbol.clone(), spec);
                count += 1;
            }
        }
    }

    let next_cursor = result
        .get("nextPageCursor")
        .and_then(|v| v.as_str())
        .filter(|s| !s.is_empty())
        .map(|s| s.to_string());

    (count, next_cursor)
}

/// Parse a single instrument item from Bybit API response.
/// 從 Bybit API 回應中解析單個合約信息。
///
/// Bybit V5 instruments-info response structure:
///   { "symbol": "BTCUSDT", "baseCoin": "BTC", "quoteCoin": "USDT",
///     "contractType": "LinearPerpetual",
///     "lotSizeFilter": { "qtyStep": "0.001", "minOrderQty": "0.001", "maxOrderQty": "100" },
///     "priceFilter": { "tickSize": "0.10", "minPrice": "0.10", "maxPrice": "999999" },
///     "lotSizeFilter": { ... "minNotionalValue": "5" } }
fn parse_instrument_item(item: &serde_json::Value) -> Option<SymbolSpec> {
    let symbol = item.get("symbol")?.as_str()?.to_string();
    let base_currency = item
        .get("baseCoin")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let quote_currency = item
        .get("quoteCoin")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let contract_type = item
        .get("contractType")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();

    let lot_filter = item.get("lotSizeFilter")?;
    let price_filter = item.get("priceFilter")?;

    let qty_step = parse_f64_field(lot_filter, "qtyStep").unwrap_or(0.001);
    let min_qty = parse_f64_field(lot_filter, "minOrderQty").unwrap_or(0.001);
    let max_qty = parse_f64_field(lot_filter, "maxOrderQty").unwrap_or(100.0);
    let tick_size = parse_f64_field(price_filter, "tickSize").unwrap_or(0.01);
    let min_price = parse_f64_field(price_filter, "minPrice").unwrap_or(0.01);
    let max_price = parse_f64_field(price_filter, "maxPrice").unwrap_or(0.0);

    // minNotionalValue can be in lotSizeFilter or at root level / 最小名義值位置不固定
    let min_notional = parse_f64_field(lot_filter, "minNotionalValue")
        .or_else(|| parse_f64_field(item, "minNotionalValue"))
        .unwrap_or(0.0);

    let qty_decimals = decimal_places_from_step(qty_step);
    let price_decimals = decimal_places_from_step(tick_size);

    Some(SymbolSpec {
        symbol,
        base_currency,
        quote_currency,
        contract_type,
        qty_step,
        min_qty,
        max_qty,
        tick_size,
        min_price,
        max_price,
        min_notional,
        qty_decimals,
        price_decimals,
    })
}

/// Parse a string field as f64 from a JSON object.
/// 從 JSON 對象中將字串欄位解析為 f64。
fn parse_f64_field(obj: &serde_json::Value, field: &str) -> Option<f64> {
    obj.get(field)?.as_str().and_then(|s| s.parse::<f64>().ok())
}

/// Derive number of decimal places from a step value.
/// 從步長值推導小數位數。
///
/// e.g. 0.001 → 3, 0.10 → 1, 1.0 → 0
fn decimal_places_from_step(step: f64) -> u32 {
    if step <= 0.0 || step >= 1.0 {
        return 0;
    }
    let s = format!("{:.10}", step);
    let trimmed = s.trim_end_matches('0');
    if let Some(dot_pos) = trimmed.find('.') {
        (trimmed.len() - dot_pos - 1) as u32
    } else {
        0
    }
}

/// Round a float to N decimal places.
/// 將浮點數取整到 N 位小數。
fn round_to_decimals(value: f64, decimals: u32) -> f64 {
    let factor = 10_f64.powi(decimals as i32);
    (value * factor).round() / factor
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_btc_spec() -> SymbolSpec {
        SymbolSpec {
            symbol: "BTCUSDT".to_string(),
            base_currency: "BTC".to_string(),
            quote_currency: "USDT".to_string(),
            contract_type: "LinearPerpetual".to_string(),
            qty_step: 0.001,
            min_qty: 0.001,
            max_qty: 100.0,
            tick_size: 0.10,
            min_price: 0.10,
            max_price: 999999.0,
            min_notional: 5.0,
            qty_decimals: 3,
            price_decimals: 1,
        }
    }

    #[test]
    fn test_round_qty() {
        let spec = sample_btc_spec();
        assert!((spec.round_qty(0.0056) - 0.005).abs() < 1e-10);
        assert!((spec.round_qty(0.0019) - 0.001).abs() < 1e-10);
        assert!((spec.round_qty(1.9999) - 1.999).abs() < 1e-10);
        assert!((spec.round_qty(0.0001) - 0.0).abs() < 1e-10); // below step
    }

    #[test]
    fn test_round_qty_zero_negative() {
        let spec = sample_btc_spec();
        assert_eq!(spec.round_qty(0.0), 0.0);
        assert_eq!(spec.round_qty(-1.0), 0.0);
    }

    #[test]
    fn test_round_price() {
        let spec = sample_btc_spec();
        // tick_size = 0.10, so 65000.55 → 65000.6
        assert!((spec.round_price(65000.55) - 65000.6).abs() < 1e-10);
        // 65000.04 → 65000.0
        assert!((spec.round_price(65000.04) - 65000.0).abs() < 1e-10);
    }

    #[test]
    fn test_floor_price() {
        let spec = sample_btc_spec();
        assert!((spec.floor_price(65000.99) - 65000.9).abs() < 1e-10);
        assert!((spec.floor_price(65000.01) - 65000.0).abs() < 1e-10);
    }

    #[test]
    fn test_ceil_price() {
        let spec = sample_btc_spec();
        assert!((spec.ceil_price(65000.01) - 65000.1).abs() < 1e-10);
        assert!((spec.ceil_price(65000.0) - 65000.0).abs() < 1e-10);
    }

    #[test]
    fn test_validate_order_ok() {
        let spec = sample_btc_spec();
        let (ok, reason) = spec.validate_order(0.01, 65000.0);
        assert!(ok, "should be valid: {reason}");
    }

    #[test]
    fn test_validate_order_qty_too_small() {
        let spec = sample_btc_spec();
        let (ok, reason) = spec.validate_order(0.0001, 65000.0);
        assert!(!ok);
        assert!(reason.contains("min_qty"));
    }

    #[test]
    fn test_validate_order_qty_too_large() {
        let spec = sample_btc_spec();
        let (ok, reason) = spec.validate_order(200.0, 65000.0);
        assert!(!ok);
        assert!(reason.contains("max_qty"));
    }

    #[test]
    fn test_validate_order_notional_too_small() {
        let spec = sample_btc_spec();
        // 0.001 * 1.0 = 0.001 < min_notional 5
        let (ok, reason) = spec.validate_order(0.001, 1.0);
        assert!(!ok);
        assert!(reason.contains("min_notional"));
    }

    #[test]
    fn test_decimal_places_from_step() {
        assert_eq!(decimal_places_from_step(0.001), 3);
        assert_eq!(decimal_places_from_step(0.10), 1);
        assert_eq!(decimal_places_from_step(0.01), 2);
        assert_eq!(decimal_places_from_step(1.0), 0);
        assert_eq!(decimal_places_from_step(0.0), 0);
    }

    #[test]
    fn test_round_to_decimals() {
        assert!((round_to_decimals(1.23456, 3) - 1.235).abs() < 1e-10);
        assert!((round_to_decimals(1.23456, 0) - 1.0).abs() < 1e-10);
        assert!((round_to_decimals(1.5, 0) - 2.0).abs() < 1e-10);
    }

    #[test]
    fn test_parse_instrument_item() {
        let item = serde_json::json!({
            "symbol": "BTCUSDT",
            "baseCoin": "BTC",
            "quoteCoin": "USDT",
            "contractType": "LinearPerpetual",
            "lotSizeFilter": {
                "qtyStep": "0.001",
                "minOrderQty": "0.001",
                "maxOrderQty": "100",
                "minNotionalValue": "5"
            },
            "priceFilter": {
                "tickSize": "0.10",
                "minPrice": "0.10",
                "maxPrice": "999999.00"
            }
        });

        let spec = parse_instrument_item(&item).unwrap();
        assert_eq!(spec.symbol, "BTCUSDT");
        assert_eq!(spec.base_currency, "BTC");
        assert!((spec.qty_step - 0.001).abs() < 1e-10);
        assert!((spec.tick_size - 0.10).abs() < 1e-10);
        assert!((spec.min_notional - 5.0).abs() < 1e-10);
        assert_eq!(spec.qty_decimals, 3);
        assert_eq!(spec.price_decimals, 1);
    }

    #[test]
    fn test_parse_instrument_item_missing_symbol() {
        let item = serde_json::json!({
            "baseCoin": "BTC",
            "lotSizeFilter": {"qtyStep": "0.001"},
            "priceFilter": {"tickSize": "0.10"}
        });
        assert!(parse_instrument_item(&item).is_none());
    }

    #[test]
    fn test_cache_basic_operations() {
        let cache = InstrumentInfoCache::new();
        assert!(cache.is_empty());
        assert_eq!(cache.len(), 0);
        assert!(cache.get("BTCUSDT").is_none());
        assert!(cache.get_lot_size("BTCUSDT").is_none());
        assert!(cache.get_tick_size("BTCUSDT").is_none());
        assert!(cache.round_qty("BTCUSDT", 1.0).is_none());
        assert!(cache.round_price("BTCUSDT", 65000.0).is_none());
    }

    #[test]
    fn test_cache_manual_insert_and_query() {
        let cache = InstrumentInfoCache::new();
        {
            let mut map = cache.cache.write();
            map.insert("BTCUSDT".to_string(), sample_btc_spec());
        }

        assert!(!cache.is_empty());
        assert_eq!(cache.len(), 1);
        assert!(cache.get("BTCUSDT").is_some());
        assert!((cache.get_lot_size("BTCUSDT").unwrap() - 0.001).abs() < 1e-10);
        assert!((cache.get_tick_size("BTCUSDT").unwrap() - 0.10).abs() < 1e-10);
        assert!((cache.round_qty("BTCUSDT", 0.0056).unwrap() - 0.005).abs() < 1e-10);
        assert!((cache.round_price("BTCUSDT", 65000.55).unwrap() - 65000.6).abs() < 1e-10);
        assert!(cache.symbols().contains(&"BTCUSDT".to_string()));
    }

    // -----------------------------------------------------------------------
    // INSTR-PAGINATE-1 — pagination unit tests (pure parse_page)
    // INSTR-PAGINATE-1 — 分頁單元測試（純 parse_page）
    // -----------------------------------------------------------------------

    fn sample_item(symbol: &str) -> serde_json::Value {
        serde_json::json!({
            "symbol": symbol,
            "baseCoin": "FOO",
            "quoteCoin": "USDT",
            "contractType": "LinearPerpetual",
            "lotSizeFilter": {
                "qtyStep": "0.001",
                "minOrderQty": "0.001",
                "maxOrderQty": "100",
                "minNotionalValue": "5"
            },
            "priceFilter": {
                "tickSize": "0.10",
                "minPrice": "0.10",
                "maxPrice": "999999.00"
            }
        })
    }

    #[test]
    fn test_parse_page_single_page_empty_cursor_absent() {
        // result has no nextPageCursor field → next = None
        let result = serde_json::json!({
            "list": [sample_item("AAAUSDT"), sample_item("BBBUSDT")],
        });
        let mut cache: HashMap<String, SymbolSpec> = HashMap::new();
        let (count, next) = parse_page(&result, &mut cache);
        assert_eq!(count, 2);
        assert_eq!(next, None);
        assert!(cache.contains_key("AAAUSDT"));
        assert!(cache.contains_key("BBBUSDT"));
    }

    #[test]
    fn test_parse_page_empty_string_cursor_is_none() {
        // Bybit end-of-pages: nextPageCursor = "" → next = None
        let result = serde_json::json!({
            "list": [sample_item("ZZZUSDT")],
            "nextPageCursor": "",
        });
        let mut cache: HashMap<String, SymbolSpec> = HashMap::new();
        let (count, next) = parse_page(&result, &mut cache);
        assert_eq!(count, 1);
        assert_eq!(next, None);
    }

    #[test]
    fn test_parse_page_non_empty_cursor_propagates() {
        let result = serde_json::json!({
            "list": [sample_item("AAAUSDT")],
            "nextPageCursor": "page2_cursor",
        });
        let mut cache: HashMap<String, SymbolSpec> = HashMap::new();
        let (count, next) = parse_page(&result, &mut cache);
        assert_eq!(count, 1);
        assert_eq!(next, Some("page2_cursor".to_string()));
    }

    #[test]
    fn test_parse_page_missing_list_returns_zero() {
        let result = serde_json::json!({"nextPageCursor": "c1"});
        let mut cache: HashMap<String, SymbolSpec> = HashMap::new();
        let (count, next) = parse_page(&result, &mut cache);
        assert_eq!(count, 0);
        assert_eq!(next, Some("c1".to_string()));
    }

    #[test]
    fn test_parse_page_three_page_concatenation() {
        // Simulate the three-page loop the refresh() cursor loop would drive.
        // Pages cursor chain: "" → "c1" → "c2" → "" (terminal).
        // 模擬 refresh() cursor 迴圈跑三頁：空 → c1 → c2 → 空。
        let page1 = serde_json::json!({
            "list": [sample_item("AAAUSDT"), sample_item("BBBUSDT")],
            "nextPageCursor": "c1",
        });
        let page2 = serde_json::json!({
            "list": [sample_item("CCCUSDT"), sample_item("DDDUSDT"), sample_item("EEEUSDT")],
            "nextPageCursor": "c2",
        });
        let page3 = serde_json::json!({
            "list": [sample_item("FFFUSDT")],
            "nextPageCursor": "",
        });

        let mut cache: HashMap<String, SymbolSpec> = HashMap::new();
        let mut total = 0usize;
        let mut pages_iter = 0usize;
        let mut cursor: Option<String> = None;
        for page in [&page1, &page2, &page3] {
            pages_iter += 1;
            let (c, next) = parse_page(page, &mut cache);
            total += c;
            cursor = next;
            if cursor.is_none() {
                break;
            }
        }

        assert_eq!(total, 6);
        assert_eq!(pages_iter, 3);
        assert_eq!(cursor, None);
        assert_eq!(cache.len(), 6);
        for s in ["AAAUSDT", "BBBUSDT", "CCCUSDT", "DDDUSDT", "EEEUSDT", "FFFUSDT"] {
            assert!(cache.contains_key(s), "missing {s}");
        }
    }

    #[test]
    fn test_parse_page_cursor_chain_terminates() {
        // Page with `nextPageCursor` field absent entirely should also terminate.
        let result = serde_json::json!({
            "list": [sample_item("ONLYUSDT")],
        });
        let mut cache: HashMap<String, SymbolSpec> = HashMap::new();
        let (_c, next) = parse_page(&result, &mut cache);
        assert!(next.is_none(), "absent nextPageCursor must terminate");
    }

    // -----------------------------------------------------------------------
    // INSTR-ENSURE-1 — ensure_symbol unit tests (mock SingleSymbolFetcher)
    // INSTR-ENSURE-1 — ensure_symbol 單元測試（mock SingleSymbolFetcher）
    // -----------------------------------------------------------------------

    use std::sync::atomic::{AtomicU64, AtomicU8, Ordering};

    /// Mock fetcher — programmable response + REST call counter.
    /// Mock fetcher — 可編程回應 + REST 呼叫計數器。
    struct MockFetcher {
        /// 0 = Ok(Some(item)), 1 = Ok(None), 2 = Err transient, 3 = Err 5xx
        mode: AtomicU8,
        /// Counts every call to fetch_single_symbol
        calls: Arc<AtomicU64>,
        /// Optional per-call delay to force concurrency overlap
        delay_ms: u64,
    }

    impl MockFetcher {
        fn new(mode: u8) -> Self {
            Self {
                mode: AtomicU8::new(mode),
                calls: Arc::new(AtomicU64::new(0)),
                delay_ms: 0,
            }
        }
        fn with_delay(mode: u8, delay_ms: u64) -> Self {
            Self {
                mode: AtomicU8::new(mode),
                calls: Arc::new(AtomicU64::new(0)),
                delay_ms,
            }
        }
        fn set_mode(&self, m: u8) {
            self.mode.store(m, Ordering::SeqCst);
        }
        fn call_count(&self) -> u64 {
            self.calls.load(Ordering::SeqCst)
        }
    }

    #[async_trait]
    impl SingleSymbolFetcher for MockFetcher {
        async fn fetch_single_symbol(
            &self,
            _category: &str,
            symbol: &str,
        ) -> BybitResult<Option<serde_json::Value>> {
            self.calls.fetch_add(1, Ordering::SeqCst);
            if self.delay_ms > 0 {
                tokio::time::sleep(Duration::from_millis(self.delay_ms)).await;
            }
            match self.mode.load(Ordering::SeqCst) {
                0 => Ok(Some(sample_item(symbol))),
                1 => Ok(None),
                2 => Err(BybitApiError::Business {
                    ret_code: -1,
                    ret_msg: "simulated transient error".into(),
                    response: serde_json::json!(null),
                }),
                _ => Err(BybitApiError::Business {
                    ret_code: 10002,
                    ret_msg: "simulated 5xx".into(),
                    response: serde_json::json!(null),
                }),
            }
        }
    }

    #[tokio::test]
    async fn test_ensure_symbol_positive_cache_hit_no_fetch() {
        let cache = InstrumentInfoCache::new();
        {
            let mut map = cache.cache.write();
            map.insert("BTCUSDT".to_string(), sample_btc_spec());
        }
        let fetcher = MockFetcher::new(0);

        let got = cache
            .ensure_symbol_with_fetcher(&fetcher, "linear", "BTCUSDT")
            .await
            .unwrap();
        assert!(got.is_some());
        assert_eq!(fetcher.call_count(), 0, "positive cache hit must not fetch");
    }

    #[tokio::test]
    async fn test_ensure_symbol_fetch_inserts_positive_cache() {
        let cache = InstrumentInfoCache::new();
        let fetcher = MockFetcher::new(0);

        let got = cache
            .ensure_symbol_with_fetcher(&fetcher, "linear", "AAAUSDT")
            .await
            .unwrap();
        assert!(got.is_some());
        assert_eq!(fetcher.call_count(), 1);
        assert!(cache.get("AAAUSDT").is_some(), "spec must be cached");

        // Second call — positive cache served, no new fetch
        let _ = cache
            .ensure_symbol_with_fetcher(&fetcher, "linear", "AAAUSDT")
            .await
            .unwrap();
        assert_eq!(fetcher.call_count(), 1, "second call must hit positive cache");
    }

    #[tokio::test]
    async fn test_ensure_symbol_neg_cache_blocks_refetch() {
        let cache = InstrumentInfoCache::new();
        let fetcher = MockFetcher::new(1); // Bybit says "not found"

        let got = cache
            .ensure_symbol_with_fetcher(&fetcher, "linear", "FAKE__USDT")
            .await
            .unwrap();
        assert!(got.is_none());
        assert_eq!(fetcher.call_count(), 1);

        // Second call within TTL — neg cache hit, no new fetch
        let got2 = cache
            .ensure_symbol_with_fetcher(&fetcher, "linear", "FAKE__USDT")
            .await
            .unwrap();
        assert!(got2.is_none());
        assert_eq!(
            fetcher.call_count(),
            1,
            "neg cache hit must not trigger fetch"
        );
    }

    #[tokio::test]
    async fn test_ensure_symbol_transient_error_not_neg_cached() {
        let cache = InstrumentInfoCache::new();
        let fetcher = MockFetcher::new(3); // simulated 5xx-like

        let r1 = cache
            .ensure_symbol_with_fetcher(&fetcher, "linear", "FOOBAR")
            .await;
        assert!(r1.is_err(), "transient error must propagate");
        assert_eq!(fetcher.call_count(), 1);

        // Neg cache must NOT contain FOOBAR
        assert!(
            !cache.neg_cache_hit("FOOBAR"),
            "transient errors must not poison neg cache"
        );

        // Second call — fetcher is called again (retry allowed because
        // no neg cache poisoning + not in positive cache)
        let _ = cache
            .ensure_symbol_with_fetcher(&fetcher, "linear", "FOOBAR")
            .await;
        assert_eq!(
            fetcher.call_count(),
            2,
            "transient error must permit retry on next call"
        );
    }

    #[tokio::test]
    async fn test_ensure_symbol_singleflight_dedup() {
        // 10 concurrent tasks request the same symbol — only 1 REST call should issue.
        let cache = Arc::new(InstrumentInfoCache::new());
        // Use a per-call delay so tasks overlap in the inflight slot.
        let fetcher = Arc::new(MockFetcher::with_delay(0, 50));

        let mut handles = Vec::new();
        for _ in 0..10 {
            let c = Arc::clone(&cache);
            let f = Arc::clone(&fetcher);
            handles.push(tokio::spawn(async move {
                c.ensure_symbol_with_fetcher(&*f, "linear", "RACEUSDT")
                    .await
                    .map(|o| o.is_some())
            }));
        }

        let results: Vec<_> = futures_util::future::join_all(handles).await;
        for r in results {
            assert!(r.unwrap().unwrap(), "every task must see a positive result");
        }

        assert_eq!(
            fetcher.call_count(),
            1,
            "singleflight must dedup concurrent fetches to 1 REST call"
        );
        assert!(cache.get("RACEUSDT").is_some());
    }

    #[tokio::test]
    async fn test_ensure_symbol_neg_cache_ttl_expiry_then_refetch() {
        // Same flow as test_ensure_symbol_neg_cache_blocks_refetch, but we
        // manually expire the neg cache entry to prove the TTL gate works.
        let cache = InstrumentInfoCache::new();
        let fetcher = MockFetcher::new(1);

        let _ = cache
            .ensure_symbol_with_fetcher(&fetcher, "linear", "EXPIREUSDT")
            .await
            .unwrap();
        assert_eq!(fetcher.call_count(), 1);

        // Force-expire: rewrite entry with an Instant well beyond TTL.
        {
            let mut guard = cache.negative_cache.write();
            guard.insert(
                "EXPIREUSDT".to_string(),
                Instant::now()
                    .checked_sub(NEG_CACHE_TTL + Duration::from_secs(1))
                    .expect("test clock subtraction"),
            );
        }

        // Bybit flips to "found"
        fetcher.set_mode(0);
        let got = cache
            .ensure_symbol_with_fetcher(&fetcher, "linear", "EXPIREUSDT")
            .await
            .unwrap();
        assert!(got.is_some());
        assert_eq!(
            fetcher.call_count(),
            2,
            "TTL-expired neg entry must allow refetch"
        );
    }

    /// Test ETH-style spec with different precision.
    /// 測試 ETH 風格的規格（不同精度）。
    #[test]
    fn test_eth_spec_rounding() {
        let spec = SymbolSpec {
            symbol: "ETHUSDT".to_string(),
            base_currency: "ETH".to_string(),
            quote_currency: "USDT".to_string(),
            contract_type: "LinearPerpetual".to_string(),
            qty_step: 0.01,
            min_qty: 0.01,
            max_qty: 1000.0,
            tick_size: 0.01,
            min_price: 0.01,
            max_price: 99999.0,
            min_notional: 5.0,
            qty_decimals: 2,
            price_decimals: 2,
        };
        assert!((spec.round_qty(1.234) - 1.23).abs() < 1e-10);
        assert!((spec.round_price(3500.555) - 3500.56).abs() < 1e-10);
    }

    // -----------------------------------------------------------------------
    // INSTR-ENSURE-FIX-1 — regression tests for E2 review findings
    // INSTR-ENSURE-FIX-1 — E2 review 回歸測試
    // -----------------------------------------------------------------------

    /// B-1 race regression — direct white-box test for the lost-wakeup fix.
    ///
    /// Background — on the old code the follower registers its `.notified()`
    /// waker AFTER releasing the inflight mutex:
    ///
    /// ```text
    ///   // OLD (buggy):
    ///   drop(inflight_mutex);
    ///   notify.notified().await;    // <-- only registers HERE
    /// ```
    ///
    /// If the leader completes between the two steps and calls
    /// `notify_waiters()`, the follower's waker isn't yet in the intrusive
    /// list. Because `Notify::notify_waiters()` does NOT store a permit
    /// for future subscribers, the notification is lost → follower hangs
    /// on `.await` indefinitely.
    ///
    /// This test constructs the exact race by **hand-placing** a stale
    /// InflightEntry with `done=true` into the inflight map (simulating
    /// "leader already finished + notified before follower started"),
    /// then calls ensure_symbol and asserts it does NOT hang. The
    /// production follower path must observe `done` via Acquire and skip
    /// the `.await`; on the old code (plain `.notified().await`) this
    /// exact shape is a guaranteed hang — no race randomness required.
    ///
    /// We also run a looser end-to-end stress scenario with many
    /// contenders colliding under a shared start-barrier to catch any
    /// other ordering regressions.
    ///
    /// B-1 lost-wakeup 回歸（白盒）：手動放「已完成」的 InflightEntry，
    /// 直接驗證 follower 觀察 done=true 跳 await；再做多 contender 壓測覆蓋。
    #[tokio::test(flavor = "multi_thread", worker_threads = 4)]
    async fn test_ensure_symbol_race_regression_leader_fast() {
        use tokio::sync::Barrier;

        // -------------------------------------------------------------------
        // Part 1 — white-box: stale-done entry must not hang the follower.
        // Part 1 — 白盒：已完成的 entry 必須讓 follower 不 hang。
        // -------------------------------------------------------------------
        {
            let cache = Arc::new(InstrumentInfoCache::new());

            // Step 1: pre-populate the positive cache (simulate leader's
            // cache insert).
            {
                let mut map = cache.cache.write();
                map.insert("STALEUSDT".to_string(), sample_btc_spec());
            }

            // Step 2: hand-place a stale InflightEntry with done=true into
            // the inflight map. This is the exact state that would exist
            // if the leader had (a) installed the entry, (b) set done=true,
            // (c) called notify_waiters(), (d) released the inflight mutex
            // to remove the slot — but where some "follower" observer had
            // cloned the Arc<InflightEntry> before the leader removed the
            // slot from the map. The follower holds a ref to the stale
            // entry. On old code, it would call `.notified().await` on a
            // Notify whose notification has already been flushed → hang.
            //
            // We avoid the "slot is removed" cleanup path by leaving the
            // entry in place so that a new ensure_symbol call finds it as
            // a follower.
            // 手動放入一個已 done=true 的 InflightEntry。對舊 code 是必 hang 的
            // 情境（notify_waiters 已發過、當前 Notify 無 permit）。新 code 先
            // enable 再 Acquire 讀 done → true → 跳 await。
            let stale_entry = Arc::new(InflightEntry::new());
            stale_entry.done.store(true, Ordering::Release);
            // Emit a notify_waiters() to simulate the permit being "flushed"
            // — with no current waiters, notify_waiters is a no-op-ish
            // state bump that does NOT leave a permit for future subscribers.
            // This is exactly the scenario that breaks old-code followers.
            // 發 notify_waiters()：無 waiter 等於無效，不留 permit，正是破壞舊
            // code follower 的情境。
            stale_entry.notify.notify_waiters();
            {
                let mut inflight = cache.inflight.lock();
                inflight.insert("STALEUSDT".to_string(), Arc::clone(&stale_entry));
            }

            // Dummy fetcher that must never be called (positive cache hit
            // path in follower flow — done=true triggers re-check of caches
            // which finds the pre-populated positive entry).
            struct NeverCalledFetcher;
            #[async_trait]
            impl SingleSymbolFetcher for NeverCalledFetcher {
                async fn fetch_single_symbol(
                    &self,
                    _category: &str,
                    _symbol: &str,
                ) -> BybitResult<Option<serde_json::Value>> {
                    panic!("fetcher must not be called: positive cache already seeded");
                }
            }

            // ensure_symbol with the stale done-entry must return quickly.
            // On old code (plain `.notified().await`) this hangs forever
            // because no permit is waiting and no new notify will arrive.
            // 1s timeout surfaces old-code hang as a test failure.
            // 舊 code 會 hang（無 permit、無後續 notify）；新 code 立即返回。
            //
            // Note: Step 1 seeded the positive cache, so ensure_symbol's
            // very first check (positive cache fast path) should return
            // BEFORE we even hit the follower path. To actually force the
            // follower path, we need to clear the positive cache check —
            // but that check is unconditional. So instead we verify a
            // DIFFERENT arrangement: remove the positive cache entry, keep
            // the stale done-entry, and assert ensure_symbol returns None
            // (follower wakes via done=true, re-checks both caches, neither
            // has an entry, returns None — no hang).
            // 註：positive cache 會先被檢查導致捷徑返回。為強迫走 follower
            // 路徑，我們移除正 cache、保留 done entry，驗證 ensure 回 None
            // 且不 hang。
            {
                let mut map = cache.cache.write();
                map.remove("STALEUSDT");
            }

            let fetcher = NeverCalledFetcher;
            let result = tokio::time::timeout(
                Duration::from_secs(1),
                cache.ensure_symbol_with_fetcher(&fetcher, "linear", "STALEUSDT"),
            )
            .await;
            match result {
                Ok(Ok(opt)) => assert!(
                    opt.is_none(),
                    "follower observing done=true with empty caches must return None"
                ),
                Ok(Err(e)) => panic!("unexpected Err: {e:?}"),
                Err(_) => panic!(
                    "B-1 REGRESSION: follower hung on .notified().await — done=true flag was not observed before await"
                ),
            }
        }

        // -------------------------------------------------------------------
        // Part 2 — end-to-end stress: many contenders collide, none may hang.
        // Part 2 — 端到端壓測：多 contender 同時衝擊，零 hang。
        // -------------------------------------------------------------------
        const ROUNDS: usize = 100;
        const CONTENDERS: usize = 8;

        /// Micro-delay fetcher — just enough `.await` (yield_now) to force
        /// the runtime to re-schedule, creating interleaving opportunities.
        /// Micro-delay fetcher：一次 yield_now，製造執行緒重排機會。
        struct YieldFetcher {
            calls: Arc<AtomicU64>,
        }
        #[async_trait]
        impl SingleSymbolFetcher for YieldFetcher {
            async fn fetch_single_symbol(
                &self,
                _category: &str,
                symbol: &str,
            ) -> BybitResult<Option<serde_json::Value>> {
                self.calls.fetch_add(1, Ordering::SeqCst);
                tokio::task::yield_now().await;
                Ok(Some(sample_item(symbol)))
            }
        }

        for round in 0..ROUNDS {
            let cache = Arc::new(InstrumentInfoCache::new());
            let calls = Arc::new(AtomicU64::new(0));
            let fetcher = Arc::new(YieldFetcher {
                calls: Arc::clone(&calls),
            });
            let start_barrier = Arc::new(Barrier::new(CONTENDERS + 1));

            let mut handles = Vec::with_capacity(CONTENDERS);
            for idx in 0..CONTENDERS {
                let c = Arc::clone(&cache);
                let f = Arc::clone(&fetcher);
                let bar = Arc::clone(&start_barrier);
                handles.push(tokio::spawn(async move {
                    bar.wait().await;
                    let r = tokio::time::timeout(
                        Duration::from_secs(1),
                        c.ensure_symbol_with_fetcher(&*f, "linear", "RACEUSDT"),
                    )
                    .await;
                    (idx, r)
                }));
            }

            start_barrier.wait().await;

            for h in handles {
                let (idx, joined) = h.await.expect("task join");
                match joined {
                    Ok(Ok(opt)) => assert!(
                        opt.is_some(),
                        "round {round} task {idx}: must observe positive cache"
                    ),
                    Ok(Err(e)) => panic!(
                        "round {round} task {idx}: ensure returned Err {e:?}"
                    ),
                    Err(_elapsed) => panic!(
                        "round {round} task {idx}: TIMEOUT — B-1 lost-wakeup regression"
                    ),
                }
            }

            assert!(
                cache.get("RACEUSDT").is_some(),
                "round {round}: positive cache must be populated"
            );
        }
    }

    /// P1-1 regression — parse failure must NOT populate neg cache.
    ///
    /// Old behaviour: Bybit returns 200 + item whose schema doesn't match
    /// our parser → we insert the symbol into the neg cache for 60s. If a
    /// Bybit field rename causes parse failure for EVERY symbol, the whole
    /// engine is blacked out for 60s (M-1 fail-closed rejects all orders).
    ///
    /// New behaviour: parse failure returns a transient Err (still
    /// fail-closes the current order via M-1) but leaves the neg cache
    /// clean, so the next call issues a fresh fetch. If Bybit fixes the
    /// schema, the engine self-heals within one tick.
    ///
    /// P1-1 回歸：parse 失敗**不**入 neg cache，避免 Bybit schema 漂移 60s
    /// 全引擎拒單。
    #[tokio::test]
    async fn test_ensure_symbol_parse_fail_not_neg_cached() {
        /// Mock fetcher: first call returns 200 + item missing
        /// `lotSizeFilter` (schema drift simulation). Subsequent calls
        /// return a valid item (Bybit "recovered").
        /// 第一次回 200 但少欄位（模擬 schema 漂移）；後續恢復正常 schema。
        struct FlipSchemaFetcher {
            calls: Arc<AtomicU64>,
        }
        #[async_trait]
        impl SingleSymbolFetcher for FlipSchemaFetcher {
            async fn fetch_single_symbol(
                &self,
                _category: &str,
                symbol: &str,
            ) -> BybitResult<Option<serde_json::Value>> {
                let n = self.calls.fetch_add(1, Ordering::SeqCst);
                if n == 0 {
                    // Missing `lotSizeFilter` — parse_instrument_item will
                    // short-circuit with None on the `item.get("lotSizeFilter")?`.
                    // 缺 lotSizeFilter → parse_instrument_item 早退 None。
                    Ok(Some(serde_json::json!({
                        "symbol": symbol,
                        "baseCoin": "FOO",
                        "quoteCoin": "USDT",
                        "contractType": "LinearPerpetual",
                        "priceFilter": {
                            "tickSize": "0.10",
                            "minPrice": "0.10",
                            "maxPrice": "999999.00"
                        }
                    })))
                } else {
                    Ok(Some(sample_item(symbol)))
                }
            }
        }

        let cache = InstrumentInfoCache::new();
        let fetcher = FlipSchemaFetcher {
            calls: Arc::new(AtomicU64::new(0)),
        };
        let calls = Arc::clone(&fetcher.calls);

        // First call — schema is broken, parser rejects, must surface Err.
        // 首呼：schema 壞，parser 拒，必須回 Err。
        let r1 = cache
            .ensure_symbol_with_fetcher(&fetcher, "linear", "DRIFTUSDT")
            .await;
        assert!(
            r1.is_err(),
            "parse failure must surface as Err, not Ok(None) (otherwise neg cache poisoning)"
        );
        if let Err(BybitApiError::Business { ret_msg, .. }) = &r1 {
            assert!(
                ret_msg.contains("parse"),
                "error message should mention parse failure: {ret_msg}"
            );
        }

        // Neg cache must be clean — this is the core P1-1 assertion.
        // 負緩存必須乾淨 — P1-1 的核心 assertion。
        assert!(
            !cache.neg_cache_hit("DRIFTUSDT"),
            "parse failure must NOT poison neg cache"
        );
        assert_eq!(calls.load(Ordering::SeqCst), 1);

        // Second call — schema is good, must hit API again and succeed.
        // 次呼：schema 恢復，必須再打 API 並成功。
        let r2 = cache
            .ensure_symbol_with_fetcher(&fetcher, "linear", "DRIFTUSDT")
            .await
            .expect("second call must succeed");
        assert!(r2.is_some(), "self-heal: second call must cache the spec");
        assert_eq!(
            calls.load(Ordering::SeqCst),
            2,
            "neg cache must not have blocked the retry"
        );
        assert!(
            cache.get("DRIFTUSDT").is_some(),
            "positive cache must now hold the symbol"
        );
    }
}
