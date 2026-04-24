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
    /// Thin wrapper over `ensure_symbol_force(client, category, symbol, false)`.
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
        self.ensure_symbol_with_fetcher_opts(client, category, symbol, false)
            .await
    }

    /// INSTR-ENSURE-FORCE-1 (2026-04-23): force-refresh a symbol's spec even
    /// if a positive cache entry already exists. Intended for mid-window
    /// recovery on `PriceTickInvalid` / `PriceOutOfRange` retcodes where a
    /// cached tick_size / qty_step has gone stale (Bybit listed a symbol on
    /// a new precision since our last refresh).
    ///
    /// Semantics:
    ///   * `force_refresh = true`: skip Step 1 (positive cache fast path);
    ///     still respects singleflight dedup (same-symbol concurrent force
    ///     calls collapse to a single REST) + global semaphore + neg-cache
    ///     poisoning rules (Bybit denies → insert neg cache; transient Err
    ///     → NO neg cache).
    ///   * `force_refresh = false`: equivalent to `ensure_symbol`.
    ///
    /// Note: this does NOT clear an existing positive cache entry before
    /// fetching — if the fetch returns Err, the stale entry remains usable
    /// as a fallback. Only on successful parse does the new spec overwrite
    /// the cache (same write semantics as leader path).
    ///
    /// INSTR-ENSURE-FORCE-1：強制重拉 symbol 規格（繞正 cache 快路徑）。
    /// 用於 PriceTickInvalid 等 retcode 觸發的中窗 spec 漂移自癒。
    /// singleflight + semaphore + neg cache 防 poisoning 規則全部保留。
    pub async fn ensure_symbol_force(
        &self,
        client: &BybitRestClient,
        category: &str,
        symbol: &str,
        force_refresh: bool,
    ) -> BybitResult<Option<SymbolSpec>> {
        self.ensure_symbol_with_fetcher_opts(client, category, symbol, force_refresh)
            .await
    }

    /// Convenience wrapper that preserves the pre-FORCE-1 API surface for tests
    /// that inject mock fetchers. Calls the full `_opts` form with
    /// `force_refresh=false`.
    /// 舊測試相容 wrapper（force_refresh=false）。
    pub async fn ensure_symbol_with_fetcher<F: SingleSymbolFetcher + ?Sized>(
        &self,
        fetcher: &F,
        category: &str,
        symbol: &str,
    ) -> BybitResult<Option<SymbolSpec>> {
        self.ensure_symbol_with_fetcher_opts(fetcher, category, symbol, false)
            .await
    }

    /// Core ensure_symbol implementation, generic over `SingleSymbolFetcher`.
    ///
    /// Protocol / 協議：
    ///   1. Positive cache fast path (SKIPPED if `force_refresh=true`).
    ///   2. Negative cache hit (not TTL-expired) → return None immediately.
    ///      Applies regardless of `force_refresh` — if Bybit has denied this
    ///      symbol in the last 60s, force-refreshing won't help and would
    ///      burn rate limit. Operator clears neg cache explicitly via TTL.
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
    ///   1. 正緩存 hit → 立即 Some（不打網）。`force_refresh=true` 時跳過。
    ///   2. 負緩存 hit（TTL 內）→ 立即 None。force_refresh 不影響負緩存門。
    ///   3. Singleflight：同 symbol 有 inflight → await Notify → 重查正緩存。
    ///   4. 否則 acquire semaphore + 裝 inflight → fetcher：
    ///        - Ok(Some) → 解析插正緩存 → Some。
    ///        - Ok(None) → 插新鮮負緩存 → None。
    ///        - Err → **不**入負緩存（防 poisoning）→ 傳錯。
    ///   5. Drop 時固定清 inflight + notify 等待者。
    pub async fn ensure_symbol_with_fetcher_opts<F: SingleSymbolFetcher + ?Sized>(
        &self,
        fetcher: &F,
        category: &str,
        symbol: &str,
        force_refresh: bool,
    ) -> BybitResult<Option<SymbolSpec>> {
        // Step 1: positive cache fast path / 正緩存快路徑
        // INSTR-ENSURE-FORCE-1: skip when force_refresh=true so the caller
        // can recover from a stale tick_size / qty_step spec.
        if !force_refresh {
            if let Some(spec) = self.get(symbol) {
                return Ok(Some(spec));
            }
        }

        // Step 2: negative cache check (TTL-gated) / 負緩存查驗（TTL 內拒）
        // Kept under force_refresh path too: Bybit denied → no force-refresh
        // can find it before TTL. Skipping this would burn rate limit.
        // 負緩存門對 force_refresh 也生效：Bybit 已否認的 symbol 強拉也找不到。
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
#[path = "instrument_info_tests.rs"]
mod tests;
