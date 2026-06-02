//! MODULE_NOTE
//! 模塊用途：日線（timeframe='1d'）K 線歷史回填的分頁取數 + strict-parse 變體。
//!   產出 ParsedKlinePage（嚴格通過的 bar）與 CoverageVerdict（覆蓋率判定 +
//!   payload sha256），供 writer.rs 落 market.klines + research.alpha_klines_provenance。
//! 主要類/函數：daily_window_ms / paginate_daily_klines（游標分頁 limit=1000）/
//!   strict_filter_closed_bars（C-3 strict-parse 核心）/ CoverageVerdict / ParsedKlinePage。
//! 依賴：MarketDataClient::get_klines（既有 client，不重寫）、openclaw_core::klines::KlineBar、
//!   sha2::Sha256。
//! 硬邊界：
//!   1. 純讀市場數據 + append-only provenance，不下單、不餵 intent、不碰 auth/lease。
//!   2.【C-3 最關鍵】絕不用 .unwrap_or(0.0) / sanitize_f64_or_zero（parsers.rs:38-77 與
//!      market_writer.rs:259-262 的 fake-zero 地雷）。任何 OHLC 缺失/非有限/= 0.0 的 bar
//!      → 該 bar 不寫，coverage 降為 partial/failed。理由：流動 perp 的日線 OHLC 價格
//!      恆 > 0，0.0 是上游 parse_kline_list 失敗 default 的唯一簽名，不可與真實值混淆，
//!      入庫即 silent fake-zero 污染 PIT alpha 證據。fail-closed：寧可標 partial 也不寫假值。

use openclaw_core::klines::KlineBar as CoreKlineBar;
use sha2::{Digest, Sha256};

/// 日線一根 bar 的毫秒週期（86_400_000 ms = 24h）。
/// 用於 closed-bar filter 與 expected-rows 推算（抄 bootstrap.rs:884 的 period_ms 範式）。
pub const DAILY_PERIOD_MS: u64 = 86_400_000;

/// Bybit 單頁 kline 最大筆數（per Bybit V5 /v5/market/kline limit 上限）。
/// 分頁 wrapper 固定用 1000，使每頁取滿、最小化請求數。
pub const KLINE_PAGE_LIMIT: u32 = 1000;

/// 分頁防失控上限：單一 (symbol) 回填最多取的頁數。
/// 為什麼 fail-closed：游標若不推進（Bybit 回同窗）會無限迴圈；超頁數視為異常中止，
/// 不靜默截斷（coverage 會因 observed < expected 自然落 partial）。
pub const MAX_PAGES_PER_SYMBOL: u32 = 4096;

/// 覆蓋率判定狀態。與 V125 research.alpha_klines_provenance.coverage_status CHECK
/// 約束一致（'pass'/'partial'/'failed'/'skipped'/'not_applicable'）。
/// 本回填器只產出前三者；skipped/not_applicable 由更上層流程語意決定。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CoverageStatus {
    /// observed == expected 且 expected > 0：窗口內期望的 closed bar 全部嚴格通過。
    Pass,
    /// 0 < observed < expected：部分 bar 缺失或被 strict-parse 拒（fake-zero / 非有限）。
    Partial,
    /// observed == 0 且 expected > 0：整窗無任何 bar 嚴格通過（全拒或 API 空）。
    Failed,
}

impl CoverageStatus {
    /// 對映 V125 coverage_status CHECK 的字串值（落 provenance 帳本用）。
    pub fn as_db_str(self) -> &'static str {
        match self {
            CoverageStatus::Pass => "pass",
            CoverageStatus::Partial => "partial",
            CoverageStatus::Failed => "failed",
        }
    }
}

/// 一個回填窗口的覆蓋率判定 + payload 指紋。
///
/// 為什麼需要 expected/observed 雙計數：provenance 帳本要能事後核對「該抓多少、實得多少」，
/// 任何 strict-parse 拒絕都會使 observed < expected → status 自動降級，審計可追。
#[derive(Debug, Clone, PartialEq)]
pub struct CoverageVerdict {
    pub status: CoverageStatus,
    /// 窗口內期望的 closed daily bar 數（由 [window_start, window_end) 與 DAILY_PERIOD_MS 推算）。
    pub expected: u64,
    /// 嚴格通過、實際可寫的 bar 數。
    pub observed: u64,
    /// 嚴格通過 bar 的規範化 payload SHA-256（hex 小寫）。用於 provenance 防篡改 / 去重核對。
    pub payload_sha256: String,
}

/// 一個窗口嚴格解析後的結果：可寫 bar + 覆蓋率判定。
///
/// 不變量：`bars` 內每根的 open/high/low/close 皆為有限且 > 0（已過 strict_filter_closed_bars），
/// 故 writer 可直接綁定，無需任何 sanitize_f64_or_zero。
#[derive(Debug, Clone)]
pub struct ParsedKlinePage {
    pub symbol: String,
    /// 固定 "1d"（與 live 1m-1h 完全 disjoint，永不 ON CONFLICT 衝突）。
    pub timeframe: String,
    pub bars: Vec<CoreKlineBar>,
    pub verdict: CoverageVerdict,
}

/// 推算 [window_start_ms, window_end_ms) 區間內期望的 closed daily bar 數。
///
/// 為什麼 floor 而非 ceil：只有 `bar_open + DAILY_PERIOD_MS <= now_ms` 的 bar 才算 closed
/// （見 strict_filter_closed_bars）。expected 以窗口長度整除週期估算可寫上界；末尾未滿一天
/// 的殘段不計入期望，避免 observed < expected 的假性 partial。
pub fn expected_daily_bars(window_start_ms: u64, window_end_ms: u64) -> u64 {
    if window_end_ms <= window_start_ms {
        return 0;
    }
    (window_end_ms - window_start_ms) / DAILY_PERIOD_MS
}

/// 規範化 payload 指紋：對嚴格通過的 bar 以 `open_time|open|high|low|close|volume|turnover`
/// 逐行串接後 SHA-256。
///
/// 為什麼用 {:?}（Rust f64 Debug）而非格式化捨入：要 bit-stable 還原性（root principle #8
/// 每筆可重建），任何捨入都可能讓兩個不同真實值碰撞同一指紋。bar 先按 open_time 排序確保
/// 指紋與輸入順序無關。
pub fn compute_payload_sha256(bars: &[CoreKlineBar]) -> String {
    let mut sorted: Vec<&CoreKlineBar> = bars.iter().collect();
    sorted.sort_by_key(|b| b.open_time_ms);
    let mut hasher = Sha256::new();
    for b in &sorted {
        // 逐欄位串接；分隔符 '|' 與行尾 '\n' 防欄位邊界歧義。
        let line = format!(
            "{}|{:?}|{:?}|{:?}|{:?}|{:?}|{:?}\n",
            b.open_time_ms, b.open, b.high, b.low, b.close, b.volume, b.turnover
        );
        hasher.update(line.as_bytes());
    }
    let digest = hasher.finalize();
    let mut hex = String::with_capacity(digest.len() * 2);
    for byte in digest.iter() {
        hex.push_str(&format!("{:02x}", byte));
    }
    hex
}

/// 判定單根 bar 的 OHLC 是否嚴格有效（C-3 核心斷言）。
///
/// 為什麼這四個條件都 fail-closed（任一不滿足即拒該 bar）：
///   1. is_finite：NaN/Inf 是非法價格，入庫無意義且會毒化下游統計。
///   2. > 0.0：流動 perp 日線 OHLC 價格恆 > 0；0.0 是上游 parse_kline_list `.unwrap_or(0.0)`
///      解析失敗的唯一簽名（parsers.rs:53-68），不可與真實值區分 → 視為解析失敗。
///   3. high >= low：違反即資料損壞。
///   4. high >= open/close 且 low <= open/close：OHLC 內部一致性，違反即損壞。
/// volume/turnover 不納入此斷言：可合法為 0（無成交日），且為 nullable 欄位由 writer 走
/// sanitize_f64（保 None 語意），不影響「bar 是否可寫」的判定。
fn is_strict_valid_ohlc(b: &CoreKlineBar) -> bool {
    let ohlc = [b.open, b.high, b.low, b.close];
    if !ohlc.iter().all(|v| v.is_finite() && *v > 0.0) {
        return false;
    }
    if b.high < b.low {
        return false;
    }
    if b.high < b.open || b.high < b.close {
        return false;
    }
    if b.low > b.open || b.low > b.close {
        return false;
    }
    true
}

/// strict-parse 核心：把 client 回傳的 KlineBar（已被 parse_kline_list fake-zero 污染）
/// 過濾成「closed + 嚴格有效」的可寫 bar，並產出 CoverageVerdict。
///
/// 步驟：
///   1. closed-bar filter：`bar_open + DAILY_PERIOD_MS <= now_ms`（抄 bootstrap.rs:894，
///      未收盤 bar 不寫，避免寫入會變動的當日未完成 bar）。
///   2. strict OHLC：對每根跑 is_strict_valid_ohlc，任一失敗即丟棄該 bar（不寫 0.0）。
///   3. 轉 openclaw_core::klines::KlineBar（is_closed=true / tick_count=1，對齊 bootstrap 範式）。
///   4. 按 open_time 排序、去重（同 open_time 取首見），計 observed vs expected → status。
///
/// 為什麼 observed/expected 決定 status 而非「有無錯誤」：本函數從不 panic、從不靜默補值；
/// 任何缺失（API 沒回 / closed filter 濾掉 / strict 拒掉）都只反映成 observed 下降，由
/// provenance 帳本誠實記錄，下游可據 coverage_status 決定是否信任該窗口。
pub fn strict_filter_closed_bars(
    symbol: &str,
    raw_bars: &[KlineBar],
    window_start_ms: u64,
    window_end_ms: u64,
    now_ms: u64,
) -> ParsedKlinePage {
    use std::collections::BTreeMap;

    // open_time -> bar，BTreeMap 天然按 open_time 排序 + 去重（同 open_time 取首見）。
    let mut kept: BTreeMap<u64, CoreKlineBar> = BTreeMap::new();
    for raw in raw_bars {
        // 只收窗口內的 bar（[window_start, window_end)），防 client 回溢出窗的鄰近 bar。
        if raw.start_time < window_start_ms || raw.start_time >= window_end_ms {
            continue;
        }
        // closed-bar filter：未滿一天的當前 bar 不寫。
        if raw.start_time + DAILY_PERIOD_MS > now_ms {
            continue;
        }
        let core = CoreKlineBar {
            open_time_ms: raw.start_time,
            close_time_ms: raw.start_time + DAILY_PERIOD_MS,
            open: raw.open,
            high: raw.high,
            low: raw.low,
            close: raw.close,
            volume: raw.volume,
            turnover: raw.turnover,
            tick_count: 1,
            is_closed: true,
        };
        // C-3：strict OHLC，fake-zero / 非有限 / 損壞 bar 直接不收。
        if !is_strict_valid_ohlc(&core) {
            continue;
        }
        kept.entry(core.open_time_ms).or_insert(core);
    }

    let bars: Vec<CoreKlineBar> = kept.into_values().collect();
    let observed = bars.len() as u64;
    let expected = expected_daily_bars(window_start_ms, window_end_ms);
    let payload_sha256 = compute_payload_sha256(&bars);

    let status = if expected == 0 {
        // 窗口無期望 bar（退化窗）：observed 必為 0，視為 failed（無可寫且無期望，
        // 由上層決定是否當 not_applicable；本層保守標 failed 不掩蓋空窗）。
        CoverageStatus::Failed
    } else if observed == 0 {
        CoverageStatus::Failed
    } else if observed >= expected {
        // observed 可能因 client 多回（已被窗口/去重夾住）略超，視同 pass。
        CoverageStatus::Pass
    } else {
        CoverageStatus::Partial
    };

    ParsedKlinePage {
        symbol: symbol.to_string(),
        timeframe: "1d".to_string(),
        bars,
        verdict: CoverageVerdict {
            status,
            expected,
            observed,
            payload_sha256,
        },
    }
}

// 重新導出 client 的 KlineBar 型別供本模塊簽名使用（不重寫 client，只引用）。
use crate::market_data_client::KlineBar;

/// 對單一 symbol 的 [start_ms, end_ms) 窗口分頁取數，回傳合併後的原始 KlineBar。
///
/// 分頁策略（游標 = 已取得最大 open_time + 1 ms 往前推進）：
///   - 每頁 get_klines(category, sym, "D", Some(cursor), Some(end_ms), Some(1000))。
///   - Bybit kline 回傳通常為 open_time 降序；本函數只負責「取齊原始 bar」，排序/去重/strict
///     交給 strict_filter_closed_bars。
///   - 終止條件（三重 fail-closed，任一觸發即停，不靜默無限迴圈）：
///       a. 某頁回 0 筆 → 視為取盡。
///       b. 游標不推進（本頁最大/最小 open_time 未突破上輪邊界）→ 防原地打轉，中止。
///       c. 頁數達 MAX_PAGES_PER_SYMBOL → 異常中止（coverage 會因 observed < expected 落 partial）。
///   - sequential（呼叫端負責 per-symbol 串行）：本函數一次只跑一個 symbol 的迴圈，與
///     get_open_interest_batch（mod.rs:227）相同「不製造 burst 驚動共享 rate-limit group」的範式。
///
/// 為什麼回原始 bar 而非直接 strict：分頁終止判定需要原始 open_time（含未收盤 bar），strict
/// 過濾在 client 翻頁完成後一次做，避免「closed filter 濾掉邊界 bar 導致游標誤判取盡」。
pub async fn paginate_daily_klines(
    client: &crate::market_data_client::MarketDataClient,
    category: &str,
    symbol: &str,
    start_ms: u64,
    end_ms: u64,
) -> crate::bybit_rest_client::BybitResult<Vec<KlineBar>> {
    use std::collections::BTreeMap;

    let mut acc: BTreeMap<u64, KlineBar> = BTreeMap::new();
    // 游標上界：每輪以「已取得的最早 open_time」往前收斂（Bybit 用 end 截斷窗口）。
    let mut cursor_end = end_ms;
    let mut pages = 0u32;

    loop {
        if pages >= MAX_PAGES_PER_SYMBOL {
            // 達頁數上限：fail-closed 中止；已取得的 bar 仍回傳，coverage 由 strict 層判定。
            break;
        }
        pages += 1;

        let page = client
            .get_klines(
                category,
                symbol,
                "D",
                Some(start_ms),
                Some(cursor_end),
                Some(KLINE_PAGE_LIMIT),
            )
            .await?;

        if page.is_empty() {
            break;
        }

        // 記錄本頁最早 open_time，用於游標推進判定。
        let mut page_min_open = u64::MAX;
        let before = acc.len();
        for bar in page {
            if bar.start_time < page_min_open {
                page_min_open = bar.start_time;
            }
            acc.entry(bar.start_time).or_insert(bar);
        }
        let after = acc.len();

        // 終止：本頁無新增（全是已見過的 open_time）→ 取盡，停。
        if after == before {
            break;
        }
        // 終止：最早 open_time 已抵達/越過窗口起點 → 無更早可取，停。
        if page_min_open <= start_ms {
            break;
        }
        // 游標推進：下一輪截到本頁最早 open_time（不含），繼續向更早回溯。
        let next_cursor = page_min_open.saturating_sub(1);
        if next_cursor >= cursor_end {
            // 游標未推進（防原地打轉）→ fail-closed 中止。
            break;
        }
        cursor_end = next_cursor;
    }

    Ok(acc.into_values().collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    /// 構造一根原始 KlineBar（client 型別）。
    fn raw_bar(open_time: u64, o: f64, h: f64, l: f64, c: f64, v: f64, t: f64) -> KlineBar {
        KlineBar {
            start_time: open_time,
            open: o,
            high: h,
            low: l,
            close: c,
            volume: v,
            turnover: t,
        }
    }

    // 一個固定 now：窗口 [day0, day0+3d) 三根 bar 全已收盤。
    const DAY0: u64 = 1_700_000_000_000; // 任意對齊毫秒
    fn now_after(days: u64) -> u64 {
        DAY0 + days * DAILY_PERIOD_MS + 1
    }

    #[test]
    fn test_expected_daily_bars_floor() {
        assert_eq!(expected_daily_bars(DAY0, DAY0 + 3 * DAILY_PERIOD_MS), 3);
        // 末尾殘段（半天）不計入期望。
        assert_eq!(
            expected_daily_bars(DAY0, DAY0 + 3 * DAILY_PERIOD_MS + DAILY_PERIOD_MS / 2),
            3
        );
        assert_eq!(expected_daily_bars(DAY0, DAY0), 0);
        assert_eq!(expected_daily_bars(DAY0 + 10, DAY0), 0);
    }

    #[test]
    fn test_strict_all_valid_pass() {
        let raw = vec![
            raw_bar(DAY0, 100.0, 110.0, 95.0, 105.0, 10.0, 1000.0),
            raw_bar(DAY0 + DAILY_PERIOD_MS, 105.0, 120.0, 104.0, 118.0, 11.0, 1200.0),
            raw_bar(DAY0 + 2 * DAILY_PERIOD_MS, 118.0, 119.0, 100.0, 101.0, 9.0, 900.0),
        ];
        let page = strict_filter_closed_bars(
            "BTCUSDT",
            &raw,
            DAY0,
            DAY0 + 3 * DAILY_PERIOD_MS,
            now_after(3),
        );
        assert_eq!(page.verdict.status, CoverageStatus::Pass);
        assert_eq!(page.verdict.expected, 3);
        assert_eq!(page.verdict.observed, 3);
        assert_eq!(page.bars.len(), 3);
        assert_eq!(page.timeframe, "1d");
        assert!(!page.verdict.payload_sha256.is_empty());
    }

    /// 【C-3 反例 — 最關鍵測試】fake-zero bar（open=0.0，模擬上游 parse_kline_list
    /// `.unwrap_or(0.0)` 解析失敗）必須被拒、不寫，coverage 降 partial，且 0.0 不入 bars。
    #[test]
    fn test_strict_fake_zero_open_rejected_not_written() {
        let raw = vec![
            raw_bar(DAY0, 100.0, 110.0, 95.0, 105.0, 10.0, 1000.0),
            // 第二根 open=0.0（fake-zero 簽名）→ 必被拒。
            raw_bar(DAY0 + DAILY_PERIOD_MS, 0.0, 120.0, 104.0, 118.0, 11.0, 1200.0),
            raw_bar(DAY0 + 2 * DAILY_PERIOD_MS, 118.0, 119.0, 100.0, 101.0, 9.0, 900.0),
        ];
        let page = strict_filter_closed_bars(
            "ETHUSDT",
            &raw,
            DAY0,
            DAY0 + 3 * DAILY_PERIOD_MS,
            now_after(3),
        );
        // 3 期望，僅 2 嚴格通過 → partial。
        assert_eq!(page.verdict.status, CoverageStatus::Partial);
        assert_eq!(page.verdict.expected, 3);
        assert_eq!(page.verdict.observed, 2);
        assert_eq!(page.bars.len(), 2);
        // 證明 fake-zero bar 確實沒被寫入（無 open==0.0 的 bar）。
        assert!(page.bars.iter().all(|b| b.open > 0.0));
        // 證明被拒的正是 DAY0+1d 那根（open_time 不在 bars 內）。
        assert!(page
            .bars
            .iter()
            .all(|b| b.open_time_ms != DAY0 + DAILY_PERIOD_MS));
    }

    /// fake-zero 出現在 high/low/close 任一欄同樣必拒（不只 open）。
    #[test]
    fn test_strict_fake_zero_any_ohlc_field_rejected() {
        for field in 0..4 {
            let mut vals = [100.0_f64, 110.0, 95.0, 105.0]; // o,h,l,c
            vals[field] = 0.0;
            let raw = vec![raw_bar(DAY0, vals[0], vals[1], vals[2], vals[3], 10.0, 1000.0)];
            let page = strict_filter_closed_bars(
                "SOLUSDT",
                &raw,
                DAY0,
                DAY0 + DAILY_PERIOD_MS,
                now_after(1),
            );
            assert_eq!(
                page.verdict.status,
                CoverageStatus::Failed,
                "field {} = 0.0 應使整窗 failed（唯一 bar 被拒）",
                field
            );
            assert_eq!(page.verdict.observed, 0);
            assert!(page.bars.is_empty());
        }
    }

    /// 非有限值（NaN / Inf）必拒。
    #[test]
    fn test_strict_non_finite_rejected() {
        let raw = vec![
            raw_bar(DAY0, f64::NAN, 110.0, 95.0, 105.0, 10.0, 1000.0),
            raw_bar(DAY0 + DAILY_PERIOD_MS, 100.0, f64::INFINITY, 95.0, 105.0, 10.0, 1000.0),
        ];
        let page = strict_filter_closed_bars(
            "BNBUSDT",
            &raw,
            DAY0,
            DAY0 + 2 * DAILY_PERIOD_MS,
            now_after(2),
        );
        assert_eq!(page.verdict.status, CoverageStatus::Failed);
        assert_eq!(page.verdict.observed, 0);
        assert!(page.bars.is_empty());
    }

    /// OHLC 內部不一致（high < low / high < open 等）必拒。
    #[test]
    fn test_strict_inconsistent_ohlc_rejected() {
        // high(90) < low(95)：損壞。
        let bad_hl = vec![raw_bar(DAY0, 100.0, 90.0, 95.0, 92.0, 10.0, 1000.0)];
        let p1 = strict_filter_closed_bars("XRPUSDT", &bad_hl, DAY0, DAY0 + DAILY_PERIOD_MS, now_after(1));
        assert_eq!(p1.verdict.observed, 0);

        // high(108) < close(115)：損壞。
        let bad_hc = vec![raw_bar(DAY0, 100.0, 108.0, 95.0, 115.0, 10.0, 1000.0)];
        let p2 = strict_filter_closed_bars("XRPUSDT", &bad_hc, DAY0, DAY0 + DAILY_PERIOD_MS, now_after(1));
        assert_eq!(p2.verdict.observed, 0);
    }

    /// 未收盤 bar（bar_open + 86_400_000 > now）不寫（closed-bar filter）。
    #[test]
    fn test_closed_bar_filter_excludes_current_unclosed() {
        let raw = vec![
            raw_bar(DAY0, 100.0, 110.0, 95.0, 105.0, 10.0, 1000.0),
            // 第二根 open_time = now 對齊當天 → 未滿一天 → 不寫。
            raw_bar(DAY0 + DAILY_PERIOD_MS, 105.0, 115.0, 104.0, 110.0, 11.0, 1200.0),
        ];
        // now 落在第二根 bar 中途（僅第一根收盤）。
        let now = DAY0 + DAILY_PERIOD_MS + DAILY_PERIOD_MS / 2;
        let page = strict_filter_closed_bars("BTCUSDT", &raw, DAY0, DAY0 + 2 * DAILY_PERIOD_MS, now);
        // 窗口期望 2，但僅 1 根收盤 → partial。
        assert_eq!(page.verdict.expected, 2);
        assert_eq!(page.verdict.observed, 1);
        assert_eq!(page.verdict.status, CoverageStatus::Partial);
        assert!(page.bars.iter().all(|b| b.open_time_ms == DAY0));
    }

    /// 【FIX-1 回歸】window_end 對齊 UTC 日界後，non-aligned now 下「資料完整 → pass（gap=0）」，
    /// 並證明對照組（未對齊 window_end = now）會結構性誤標 partial（區分力喪失）。
    ///
    /// 為什麼這個測試守得住 FIX-1：bin 的 run() 把 window_end floor 到
    /// (now / DAILY_PERIOD_MS) * DAILY_PERIOD_MS（最後完整收盤 UTC 日界）。本測試在
    /// 模塊層複刻該對齊式（run() 不可單元呼叫），對「現實的 non-aligned now」分別跑
    /// 對齊 / 未對齊兩種 window_end，斷言只有對齊版能讓完整資料落 pass。
    #[test]
    fn test_fix1_utc_aligned_window_end_yields_pass_when_complete() {
        // 與 bin run() 相同的對齊式：floor 到最後一個完整收盤的 UTC 日界（今日 00:00 UTC）。
        fn align_window_end(now_ms: u64) -> u64 {
            (now_ms / DAILY_PERIOD_MS) * DAILY_PERIOD_MS
        }

        // 真正對齊週期的日界基準（DAY0 常量本身未必是 period 的整數倍，這裡 floor 一次取真日界）。
        let base = align_window_end(DAY0);
        assert_eq!(base % DAILY_PERIOD_MS, 0, "base 必須對齊 DAILY_PERIOD_MS");
        // 模擬 non-UTC-aligned now：base+3d（今日 00:00 UTC）再過 13h47m（不滿一天的殘段）。
        let now = base + 3 * DAILY_PERIOD_MS + 13 * 3_600_000 + 47 * 60_000;
        assert_ne!(now % DAILY_PERIOD_MS, 0, "now 必須是 non-aligned 才有意義");

        // 對齊後窗口 = [base, base+3d)，lookback=3 天，三根全收盤的完整資料。
        let window_end = align_window_end(now);
        assert_eq!(window_end, base + 3 * DAILY_PERIOD_MS);
        let window_start = window_end - 3 * DAILY_PERIOD_MS;
        assert_eq!(window_start, base);
        let raw = vec![
            raw_bar(base, 100.0, 110.0, 95.0, 105.0, 10.0, 1000.0),
            raw_bar(base + DAILY_PERIOD_MS, 105.0, 120.0, 104.0, 118.0, 11.0, 1200.0),
            raw_bar(base + 2 * DAILY_PERIOD_MS, 118.0, 119.0, 100.0, 101.0, 9.0, 900.0),
        ];
        // closed filter 仍以真實 now 為準（window_end <= now，三根 open_time+period <= now）。
        let aligned = strict_filter_closed_bars("BTCUSDT", &raw, window_start, window_end, now);
        assert_eq!(aligned.verdict.expected, 3, "對齊後 expected = 3 天");
        assert_eq!(aligned.verdict.observed, 3, "完整資料 observed = 3");
        assert_eq!(aligned.verdict.expected, aligned.verdict.observed, "gap = 0");
        assert_eq!(
            aligned.verdict.status,
            CoverageStatus::Pass,
            "資料完整時必須 pass（FIX-1 恢復區分力）"
        );

        // 對照組（修復前行為）：window_end = now（未對齊），窗寬仍固定 3 天。
        // 未對齊使整個窗口向後平移 13h47m → window_start = base+13h47m，把對齊版本來收進的
        // base 那根擠出窗外（start_time < window_start）→ expected=3 但 observed=2 → 假性 partial。
        // 這正是 FIX-1 前「資料完整卻每次標 partial」的結構性 bug 形態。
        let unaligned_end = now;
        let unaligned_start = unaligned_end - 3 * DAILY_PERIOD_MS;
        let unaligned =
            strict_filter_closed_bars("BTCUSDT", &raw, unaligned_start, unaligned_end, now);
        assert_eq!(unaligned.verdict.expected, 3);
        assert_eq!(unaligned.verdict.observed, 2);
        assert_eq!(
            unaligned.verdict.status,
            CoverageStatus::Partial,
            "未對齊 window_end 會結構性誤標 partial（FIX-1 修復前的 bug）"
        );
        assert!(
            unaligned.verdict.expected > unaligned.verdict.observed,
            "未對齊時 expected > observed = 假性 gap"
        );
    }

    /// volume/turnover = 0（無成交日，合法）不影響 bar 可寫性。
    #[test]
    fn test_zero_volume_is_legal_bar_still_written() {
        let raw = vec![raw_bar(DAY0, 100.0, 110.0, 95.0, 105.0, 0.0, 0.0)];
        let page = strict_filter_closed_bars("BTCUSDT", &raw, DAY0, DAY0 + DAILY_PERIOD_MS, now_after(1));
        assert_eq!(page.verdict.status, CoverageStatus::Pass);
        assert_eq!(page.verdict.observed, 1);
        assert_eq!(page.bars.len(), 1);
    }

    /// 窗口外 bar 被夾掉（client 多回鄰近 bar 不污染本窗）。
    #[test]
    fn test_out_of_window_bars_dropped() {
        let raw = vec![
            raw_bar(DAY0 - DAILY_PERIOD_MS, 50.0, 55.0, 49.0, 52.0, 5.0, 500.0), // 窗前
            raw_bar(DAY0, 100.0, 110.0, 95.0, 105.0, 10.0, 1000.0),             // 窗內
            raw_bar(DAY0 + 2 * DAILY_PERIOD_MS, 200.0, 210.0, 190.0, 205.0, 20.0, 2000.0), // 窗後（>= end）
        ];
        let page = strict_filter_closed_bars(
            "BTCUSDT",
            &raw,
            DAY0,
            DAY0 + DAILY_PERIOD_MS,
            now_after(5),
        );
        assert_eq!(page.verdict.expected, 1);
        assert_eq!(page.verdict.observed, 1);
        assert!(page.bars.iter().all(|b| b.open_time_ms == DAY0));
    }

    /// 整窗全空（API 無回）→ failed，payload sha256 為空 bar 集合的確定性指紋。
    #[test]
    fn test_empty_window_failed() {
        let page = strict_filter_closed_bars("BTCUSDT", &[], DAY0, DAY0 + 3 * DAILY_PERIOD_MS, now_after(3));
        assert_eq!(page.verdict.status, CoverageStatus::Failed);
        assert_eq!(page.verdict.observed, 0);
        assert_eq!(page.verdict.expected, 3);
    }

    /// payload sha256 對相同 bar 集合（不同輸入順序）穩定一致（排序後計）。
    #[test]
    fn test_payload_sha256_order_independent() {
        let a = raw_bar(DAY0, 100.0, 110.0, 95.0, 105.0, 10.0, 1000.0);
        let b = raw_bar(DAY0 + DAILY_PERIOD_MS, 105.0, 120.0, 104.0, 118.0, 11.0, 1200.0);
        let p1 = strict_filter_closed_bars("BTCUSDT", &[a.clone(), b.clone()], DAY0, DAY0 + 2 * DAILY_PERIOD_MS, now_after(2));
        let p2 = strict_filter_closed_bars("BTCUSDT", &[b, a], DAY0, DAY0 + 2 * DAILY_PERIOD_MS, now_after(2));
        assert_eq!(p1.verdict.payload_sha256, p2.verdict.payload_sha256);
        // 不同內容指紋不同。
        let c = raw_bar(DAY0, 100.0, 110.0, 95.0, 999.0, 10.0, 1000.0);
        let p3 = strict_filter_closed_bars("BTCUSDT", &[c], DAY0, DAY0 + DAILY_PERIOD_MS, now_after(1));
        assert_ne!(p1.verdict.payload_sha256, p3.verdict.payload_sha256);
    }

    /// coverage_status 字串對映 V125 CHECK 約束。
    #[test]
    fn test_coverage_status_db_str() {
        assert_eq!(CoverageStatus::Pass.as_db_str(), "pass");
        assert_eq!(CoverageStatus::Partial.as_db_str(), "partial");
        assert_eq!(CoverageStatus::Failed.as_db_str(), "failed");
    }
}
