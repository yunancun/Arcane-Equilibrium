//! MODULE_NOTE
//! 模塊用途：funding rate + open interest 歷史回填的分頁取數 + strict-parse 變體。
//!   產出 ParsedFundingPage / ParsedOiPage（嚴格通過的資料點）+ CoverageVerdict
//!   （覆蓋率判定 + payload sha256），供 funding_oi_writer.rs 落
//!   research.alpha_funding_rates_history / research.alpha_open_interest_history。
//! 主要類/函數：
//!   - strict_parse_funding_list / strict_parse_oi_list（★ C-3 strict-parse 核心，
//!     讀「原始 JSON」而非 client 已塌成 0.0 的 struct）。
//!   - paginate_funding_history / paginate_open_interest（兩者都 walk endTime backward，
//!     統一形狀，抄 daily_kline_backfill::paginate_daily_klines 的 shrinking-end + 三 fail-closed
//!     終止）。
//!   - FundingPoint / OiPoint / CoverageVerdict / CoverageStatus。
//! 依賴：MarketDataClient（直接 get_checked 取原始 JSON）、bybit_rest_client::BybitResponse、
//!   serde_json、sha2::Sha256。
//! 硬邊界：
//!   1. 純讀市場數據 + append-only provenance；不下單、不餵 intent、不碰 auth/lease/cap。
//!   2.【C-3 最關鍵 — 與 kline 的決定性差異】kline 的 strict 用「OHLC > 0.0」，因 OHLC 結構性
//!      恆 > 0、0.0 即 parse-fail 簽名。**funding/OI 不可照抄**：
//!        - `fundingRate` 合法為 0.0（低 premium regime）且合法為負（空付多）；
//!        - `openInterest` 可為任意 finite（不設數值下界）。
//!      故 strict 測試 = 「**原始 JSON 欄位存在 AND parse 為 finite f64**」：用回傳
//!      `Option<f64>` 的 strict variant + `is_finite()`，**絕不用** `parse_str_f64`
//!      （.unwrap_or(0.0) 把 missing 塌成 0.0 = fake-zero 地雷），**絕不用** `> 0.0` floor
//!      （會誤殺真實 0.0 / 負 funding，向正偏污染成本模型）。只 reject missing-field /
//!      non-finite（NaN/Inf/無法 parse）。
//!   3.【cap 紀律】本回填只記「已實現」funding history，禁碰 cap、禁從 max(fundingRate)
//!      反推 cap（cap SSOT = instruments-info upperFundingRate/lowerFundingRate，出本任務範圍）。
//!   4. timestamp string-ms → 由 writer parse TIMESTAMPTZ；parse-fail = reject row（不 epoch
//!      fallback）。本模塊保留原始 ts 字串，strict-parse 只要求 ts 可 parse 為 u64-ms。

use crate::bybit_rest_client::{BybitResponse, BybitResult};
use crate::market_data_client::MarketDataClient;
use serde_json::Value;
use sha2::{Digest, Sha256};

/// 分頁防失控上限：單一 (symbol) 回填最多取的頁數。
/// 為什麼 fail-closed：游標若不推進（Bybit 回同窗）會無限迴圈；超頁數視為異常中止，
/// 不靜默截斷（coverage 會因 observed < expected 自然落 partial）。
/// 取與 daily_kline_backfill::MAX_PAGES_PER_SYMBOL 相同量級的保守上限。
pub const MAX_PAGES_PER_SYMBOL: u32 = 4096;

/// funding history 單頁筆數上限（Bybit /v5/market/funding/history limit max/default = 200/200）。
pub const FUNDING_PAGE_LIMIT: u32 = 200;

/// open interest 單頁筆數上限（Bybit /v5/market/open-interest limit max = 200，default = 50）。
/// 回填固定送 200 以最小化請求數（default 50 會多 4 倍頁數）。
pub const OI_PAGE_LIMIT: u32 = 200;

// ===========================================================================
// 覆蓋率判定（與 daily_kline_backfill::CoverageStatus 同形，但 funding/OI 不推算
// expected「期望 bar 數」——結算事件/OI 點的精確期望數難以離線推算，故 expected 由
// 呼叫端按窗口長度 / 結算間隔粗估，observed 為 strict 通過數）。
// ===========================================================================

/// 覆蓋率判定狀態。對映 V125 alpha_history_ingest_pages.coverage_status CHECK
/// （'pass'/'partial'/'failed'/'skipped'/'not_applicable'）。本回填器只產前三者。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CoverageStatus {
    /// expected > 0 且 observed >= expected：窗口內期望的資料點全部嚴格通過。
    Pass,
    /// 0 < observed < expected：部分點缺失或被 strict-parse 拒（missing-field / 非有限）。
    Partial,
    /// observed == 0：整窗無任何點嚴格通過（全拒或 API 空）。
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
/// 為什麼 rejected 與 observed 分計：審計要能事後核對「strict-parse 拒了幾筆」——
/// rejected > 0 是 fake-zero / 損壞資料的直接信號（與 daily-kline 的 observed<expected 同理，
/// 但這裡額外顯式計數被拒筆數，因 funding/OI 的 expected 是粗估、區分力較弱）。
#[derive(Debug, Clone, PartialEq)]
pub struct CoverageVerdict {
    pub status: CoverageStatus,
    /// 呼叫端按窗口/結算間隔粗估的期望點數（可為 0 = 無法估算時不誤判 partial）。
    pub expected: u64,
    /// 嚴格通過、實際可寫的點數。
    pub observed: u64,
    /// 原始回應中、落在窗口內但被 strict-parse 拒（missing-field / 非有限 / ts 不可 parse）的筆數。
    pub rejected: u64,
    /// 嚴格通過點的規範化 payload SHA-256（hex 小寫）。
    pub payload_sha256: String,
}

/// 由 expected / observed 推算 status（與 daily-kline 同邏輯）。
/// expected==0：無分母 → observed>0 視 pass、observed==0 視 failed（不誤標 partial）。
fn status_from_counts(expected: u64, observed: u64) -> CoverageStatus {
    if observed == 0 {
        CoverageStatus::Failed
    } else if expected == 0 || observed >= expected {
        CoverageStatus::Pass
    } else {
        CoverageStatus::Partial
    }
}

// ===========================================================================
// strict-parse VARIANT（★ 本模塊最 load-bearing；不可照抄 kline 的 >0 filter）
// ===========================================================================

/// strict 解析一個「原始 JSON 物件」的 string-encoded f64 欄位。
///
/// 為什麼回 `Option<f64>` 而非 `parse_str_f64`（.unwrap_or(0.0)）：
///   funding/OI 的合法值域包含 0.0（甚至負），故「值是 0.0」**不可**當解析失敗簽名。
///   唯一的 fail-closed 信號是「欄位缺失 / 非字串 / 字串無法 parse / parse 結果非有限」。
///   本函數對這四種情況回 None（→ 呼叫端 reject 該筆），對「欄位存在且 parse 為 finite f64」
///   回 Some(v)（含 0.0 / 負值，照收）。
///
/// 對比 kline（is_strict_valid_ohlc 用 `> 0.0`）：kline 是事後對「已被 client 塌成 0.0 的
/// struct」做結構性 >0 斷言；本函數是對「原始 JSON」做欄位存在 + 有限性檢查，**從不經過
/// parse_str_f64**，因此能保留真實 0.0 / 負值與 missing-field 的區分。
fn strict_parse_finite_f64(obj: &Value, field: &str) -> Option<f64> {
    let v = obj.get(field)?.as_str()?.parse::<f64>().ok()?;
    if v.is_finite() {
        Some(v)
    } else {
        // NaN / Inf：非法數值，fail-closed 拒（不寫毒值）。
        None
    }
}

/// strict 解析 string-encoded ms 時間戳為 u64。
///
/// 為什麼 ts parse-fail = reject（不 epoch fallback，BB spec §4）：假 1970 epoch 污染 PIT
/// 窗口語義（hypertable time col 是 funding_ts / ts），錯誤時間點使下游分析無法重建。
/// 缺失 / 非字串 / 無法 parse / == 0 皆回 None（→ reject 該筆）。
fn strict_parse_ts_ms(obj: &Value, field: &str) -> Option<u64> {
    let ms = obj.get(field)?.as_str()?.parse::<u64>().ok()?;
    // 0 ms（1970 epoch）不是合法的 funding/OI 時間戳；視為缺值 reject。
    if ms == 0 {
        None
    } else {
        Some(ms)
    }
}

/// 一筆嚴格通過的 funding 點（時間戳 + 費率；費率可為 0.0 / 負）。
#[derive(Debug, Clone, PartialEq)]
pub struct FundingPoint {
    /// fundingRateTimestamp（ms，已驗可 parse）。
    pub funding_ts_ms: u64,
    /// fundingRate（已驗 finite；合法含 0.0 / 負，未經 >0 floor）。
    pub funding_rate: f64,
}

/// 一筆嚴格通過的 OI 點（時間戳 + 持倉量；接受任何 finite，不設下界）。
#[derive(Debug, Clone, PartialEq)]
pub struct OiPoint {
    /// timestamp（ms，已驗可 parse）。
    pub ts_ms: u64,
    /// openInterest（已驗 finite；接受任何 finite，含 0.0，未設數值 floor）。
    pub open_interest: f64,
}

/// funding 一窗的 strict 解析結果。
#[derive(Debug, Clone)]
pub struct ParsedFundingPage {
    pub category: String,
    pub symbol: String,
    pub points: Vec<FundingPoint>,
    pub verdict: CoverageVerdict,
}

/// OI 一窗的 strict 解析結果。
#[derive(Debug, Clone)]
pub struct ParsedOiPage {
    pub category: String,
    pub symbol: String,
    /// Bybit OI intervalTime（回填固定 "1h"）。
    pub interval_time: String,
    pub points: Vec<OiPoint>,
    pub verdict: CoverageVerdict,
}

/// 規範化 payload 指紋：對嚴格通過的 (ts, value) 以 `ts|value` 逐行串接後 SHA-256。
/// 用 {:?}（f64 Debug）保 bit-stable，先按 ts 排序使指紋與輸入順序無關。
fn payload_sha256_pairs(pairs: &[(u64, f64)]) -> String {
    let mut sorted: Vec<&(u64, f64)> = pairs.iter().collect();
    sorted.sort_by_key(|(ts, _)| *ts);
    let mut hasher = Sha256::new();
    for (ts, v) in &sorted {
        hasher.update(format!("{}|{:?}\n", ts, v).as_bytes());
    }
    let digest = hasher.finalize();
    let mut hex = String::with_capacity(digest.len() * 2);
    for byte in digest.iter() {
        hex.push_str(&format!("{:02x}", byte));
    }
    hex
}

/// 從 Bybit 回應的 `result.list` 取出原始 JSON 陣列（缺失/非陣列 → 空）。
fn result_list(resp: &BybitResponse) -> Vec<Value> {
    resp.result
        .get("list")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default()
}

/// 取 `result.nextPageCursor`（OI 用作分頁終止輔助；缺失/空字串 → None）。
fn next_page_cursor(resp: &BybitResponse) -> Option<String> {
    resp.result
        .get("nextPageCursor")
        .and_then(|v| v.as_str())
        .filter(|s| !s.is_empty())
        .map(|s| s.to_string())
}

/// strict-parse 一批 funding 原始 JSON list → 嚴格通過的 FundingPoint。
///
/// 步驟（對每個原始物件）：
///   1. ts = strict_parse_ts_ms("fundingRateTimestamp")：缺失/不可 parse/==0 → reject。
///   2. rate = strict_parse_finite_f64("fundingRate")：缺失/非有限 → reject；**0.0 / 負照收**。
///   3. 窗口夾：只收 [window_start_ms, window_end_ms] 內的點（含端點；防 client 回溢窗的鄰近點）。
///   4. 去重：同 ts 取首見（BTreeMap）。observed = 通過數，rejected = 落窗內但被拒數。
pub fn strict_parse_funding_list(
    category: &str,
    symbol: &str,
    raw_list: &[Value],
    window_start_ms: u64,
    window_end_ms: u64,
    expected: u64,
) -> ParsedFundingPage {
    use std::collections::BTreeMap;

    let mut kept: BTreeMap<u64, f64> = BTreeMap::new();
    let mut rejected: u64 = 0;

    for item in raw_list {
        // ts 先 strict parse（決定是否落在窗內）；不可 parse 直接 reject（不知道窗位置）。
        let Some(ts) = strict_parse_ts_ms(item, "fundingRateTimestamp") else {
            rejected += 1;
            continue;
        };
        // 窗口夾（含端點）：窗外的點不計入 observed/rejected（非本窗職責）。
        if ts < window_start_ms || ts > window_end_ms {
            continue;
        }
        // ★ rate strict：finite 即收（含 0.0 / 負），missing-field / 非有限 → reject。
        match strict_parse_finite_f64(item, "fundingRate") {
            Some(rate) => {
                kept.entry(ts).or_insert(rate);
            }
            None => {
                rejected += 1;
            }
        }
    }

    let points: Vec<FundingPoint> = kept
        .iter()
        .map(|(ts, rate)| FundingPoint {
            funding_ts_ms: *ts,
            funding_rate: *rate,
        })
        .collect();
    let observed = points.len() as u64;
    let pairs: Vec<(u64, f64)> = kept.iter().map(|(ts, r)| (*ts, *r)).collect();
    let payload_sha256 = payload_sha256_pairs(&pairs);

    ParsedFundingPage {
        category: category.to_string(),
        symbol: symbol.to_string(),
        points,
        verdict: CoverageVerdict {
            status: status_from_counts(expected, observed),
            expected,
            observed,
            rejected,
            payload_sha256,
        },
    }
}

/// strict-parse 一批 OI 原始 JSON list → 嚴格通過的 OiPoint。
///
/// 與 funding 同形，差異：欄位是 "timestamp" / "openInterest"，且 open_interest 接受任何
/// finite（不設下界；OI 為非負量但本層只要求有限，0 由上游語意決定，不在此 floor）。
pub fn strict_parse_oi_list(
    category: &str,
    symbol: &str,
    interval_time: &str,
    raw_list: &[Value],
    window_start_ms: u64,
    window_end_ms: u64,
    expected: u64,
) -> ParsedOiPage {
    use std::collections::BTreeMap;

    let mut kept: BTreeMap<u64, f64> = BTreeMap::new();
    let mut rejected: u64 = 0;

    for item in raw_list {
        let Some(ts) = strict_parse_ts_ms(item, "timestamp") else {
            rejected += 1;
            continue;
        };
        if ts < window_start_ms || ts > window_end_ms {
            continue;
        }
        // ★ OI strict：finite 即收（含 0.0），missing-field / 非有限 → reject。不設數值 floor。
        match strict_parse_finite_f64(item, "openInterest") {
            Some(oi) => {
                kept.entry(ts).or_insert(oi);
            }
            None => {
                rejected += 1;
            }
        }
    }

    let points: Vec<OiPoint> = kept
        .iter()
        .map(|(ts, oi)| OiPoint {
            ts_ms: *ts,
            open_interest: *oi,
        })
        .collect();
    let observed = points.len() as u64;
    let pairs: Vec<(u64, f64)> = kept.iter().map(|(ts, oi)| (*ts, *oi)).collect();
    let payload_sha256 = payload_sha256_pairs(&pairs);

    ParsedOiPage {
        category: category.to_string(),
        symbol: symbol.to_string(),
        interval_time: interval_time.to_string(),
        points,
        verdict: CoverageVerdict {
            status: status_from_counts(expected, observed),
            expected,
            observed,
            rejected,
            payload_sha256,
        },
    }
}

// ===========================================================================
// 分頁：兩者都 walk endTime backward（統一形狀，抄 paginate_daily_klines）
// ===========================================================================

/// 一頁分頁的取數摘要（供上層記 per-page provenance）。
#[derive(Debug, Clone)]
pub struct PageMeta {
    pub seq: u32,
    /// 本頁送出的 endTime（cursor_end）。
    pub request_end_ms: u64,
    /// 本頁送出的 startTime。
    pub request_start_ms: u64,
    /// OI 用：本頁送出的 cursor（funding 無 cursor → None）。
    pub cursor_in: Option<String>,
    /// OI 用：回應的 nextPageCursor（funding → None）。
    pub cursor_out: Option<String>,
    /// retCode（get_checked 成功時恆 0）。
    pub ret_code: i64,
    /// 本頁原始 list 筆數（strict 前）。
    pub raw_count: usize,
}

/// 分頁累積結果：合併後的原始 JSON list（去重前由呼叫端 strict）+ 逐頁 meta + cursor 鏈。
#[derive(Debug, Clone, Default)]
pub struct PaginatedRaw {
    pub raw_items: Vec<Value>,
    pub pages: Vec<PageMeta>,
    /// OI 的 nextPageCursor 鏈（依序），落 alpha_open_interest_history.cursor_lineage。
    pub cursor_lineage: Vec<String>,
}

/// 從一筆原始 JSON 物件取 ts（ms）——分頁游標推進用（與 strict ts 同邏輯，但分頁需要
/// 「原始所有筆」的最早 ts，含可能被 strict reject 的筆，故獨立一個寬鬆版只求能讀到 ts）。
/// 缺失/不可 parse → None（該筆不參與游標推進）。
fn raw_ts_ms(obj: &Value, field: &str) -> Option<u64> {
    obj.get(field)?.as_str()?.parse::<u64>().ok()
}

/// funding history 分頁：walk endTime backward。
///
/// 關鍵約束（BB spec §1）：funding/history **只傳 startTime 會 error** → 每頁傳 endTime
///   （cursor_end）。下頁 cursor_end = (本頁最早 fundingRateTimestamp) − 1，往更早回溯。
/// 無 nextPageCursor（time-window only），終止靠三 fail-closed（抄 paginate_daily_klines）：
///   a. 某頁回 0 筆 → 取盡。
///   b. 游標不推進（next_cursor >= cursor_end）→ 防原地打轉，中止。
///   c. 頁數達 MAX_PAGES_PER_SYMBOL → 異常中止（coverage 自然落 partial）。
/// 另加 d. 最早 ts 已抵達/越過 window_start → 無更早可取，停（與 kline 一致）。
pub async fn paginate_funding_history(
    client: &MarketDataClient,
    category: &str,
    symbol: &str,
    start_ms: u64,
    end_ms: u64,
) -> BybitResult<PaginatedRaw> {
    let mut out = PaginatedRaw::default();
    let mut cursor_end = end_ms;
    let mut pages = 0u32;

    loop {
        if pages >= MAX_PAGES_PER_SYMBOL {
            break;
        }
        let seq = pages;
        pages += 1;

        // ★ 只傳 endTime（不傳 startTime；傳 startTime 會 Bybit error）。limit=200。
        let resp = client
            .get_funding_history_raw(category, symbol, None, Some(cursor_end), Some(FUNDING_PAGE_LIMIT))
            .await?;
        let list = result_list(&resp);
        let raw_count = list.len();

        out.pages.push(PageMeta {
            seq,
            request_end_ms: cursor_end,
            request_start_ms: start_ms,
            cursor_in: None,
            cursor_out: None,
            ret_code: resp.ret_code,
            raw_count,
        });

        if list.is_empty() {
            break;
        }

        // 本頁最早 fundingRateTimestamp（用於游標推進 + 窗口起點終止）。
        let mut page_min_ts = u64::MAX;
        for item in &list {
            if let Some(ts) = raw_ts_ms(item, "fundingRateTimestamp") {
                if ts < page_min_ts {
                    page_min_ts = ts;
                }
            }
            out.raw_items.push(item.clone());
        }

        // 終止 d：最早 ts 已抵達/越過窗口起點 → 無更早可取。
        if page_min_ts == u64::MAX {
            // 本頁無任何可 parse 的 ts → 無法推進游標，fail-closed 中止（防原地打轉）。
            break;
        }
        if page_min_ts <= start_ms {
            break;
        }
        // 游標推進：下頁截到本頁最早 ts（不含），往更早回溯。
        let next_cursor = page_min_ts.saturating_sub(1);
        // 終止 b：游標未推進 → 防原地打轉。
        if next_cursor >= cursor_end {
            break;
        }
        cursor_end = next_cursor;
    }

    Ok(out)
}

/// open interest 分頁：walk endTime backward；nextPageCursor 只作終止輔助 + lineage 留痕。
///
/// intervalTime 固定由呼叫端傳（回填用 "1h"）。每頁**只傳 endTime（cursor_end）**，**不**把上頁
///   的 nextPageCursor 回填到 cursor 參數。終止（四 fail-closed + cursor 輔助）：
///   a. 某頁回 0 筆 → 取盡。
///   b. 時間游標不推進（next_cursor >= cursor_end）→ 防原地打轉。
///   c. 頁數達 MAX_PAGES_PER_SYMBOL → 異常中止。
///   d. 最早 ts 已抵達/越過 window_start → 無更早可取。
///   e. nextPageCursor 缺失（None）→ Bybit 表示無更多頁，停（cursor 輔助）。
///
/// 為什麼以 endTime 為唯一游標、cursor 不回填（與初版設計修正）：BB spec §2 要 funding/OI
///   統一 walk endTime backward 形狀（避免兩套分頁路徑）。同時送「shifting endTime」+「上頁
///   position-cursor」會雙重約束、語義在 Bybit 端不確定（哪個優先未保證），是真網行為賭注。
///   故 cursor 只作 (e) 終止信號 + 落 V125 cursor_lineage 留痕（lineage 仍記每頁回應的
///   nextPageCursor），不參與請求位置。client 仍保留 cursor 參數能力（公開 surface），本
///   回填器選擇不用它推進。
pub async fn paginate_open_interest(
    client: &MarketDataClient,
    category: &str,
    symbol: &str,
    interval_time: &str,
    start_ms: u64,
    end_ms: u64,
) -> BybitResult<PaginatedRaw> {
    let mut out = PaginatedRaw::default();
    let mut cursor_end = end_ms;
    let mut pages = 0u32;

    loop {
        if pages >= MAX_PAGES_PER_SYMBOL {
            break;
        }
        let seq = pages;
        pages += 1;

        // 只傳 endTime（cursor=None）；cursor_out 僅留痕 + 終止輔助，不回填請求。
        let resp = client
            .get_open_interest_raw(
                category,
                symbol,
                interval_time,
                Some(OI_PAGE_LIMIT),
                None,
                Some(cursor_end),
                None,
            )
            .await?;
        let list = result_list(&resp);
        let raw_count = list.len();
        let cursor_out = next_page_cursor(&resp);

        out.pages.push(PageMeta {
            seq,
            request_end_ms: cursor_end,
            request_start_ms: start_ms,
            cursor_in: None,
            cursor_out: cursor_out.clone(),
            ret_code: resp.ret_code,
            raw_count,
        });
        if let Some(c) = &cursor_out {
            out.cursor_lineage.push(c.clone());
        }

        if list.is_empty() {
            break;
        }

        let mut page_min_ts = u64::MAX;
        for item in &list {
            if let Some(ts) = raw_ts_ms(item, "timestamp") {
                if ts < page_min_ts {
                    page_min_ts = ts;
                }
            }
            out.raw_items.push(item.clone());
        }

        if page_min_ts == u64::MAX {
            break;
        }
        if page_min_ts <= start_ms {
            break;
        }
        let next_time_cursor = page_min_ts.saturating_sub(1);
        if next_time_cursor >= cursor_end {
            break;
        }
        // 終止 e：Bybit 無 nextPageCursor → 無更多頁（cursor 僅作終止信號，不回填請求）。
        if cursor_out.is_none() {
            break;
        }
        cursor_end = next_time_cursor;
    }

    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    const T0: u64 = 1_700_000_000_000;
    const H8: u64 = 8 * 3_600_000; // 8h funding interval
    const H1: u64 = 3_600_000;

    // ---- strict_parse_finite_f64：核心 fake-zero variant 行為 ----

    #[test]
    fn test_strict_finite_accepts_zero() {
        let obj = json!({"fundingRate": "0.0"});
        assert_eq!(strict_parse_finite_f64(&obj, "fundingRate"), Some(0.0));
    }

    #[test]
    fn test_strict_finite_accepts_negative() {
        let obj = json!({"fundingRate": "-0.0005"});
        assert_eq!(strict_parse_finite_f64(&obj, "fundingRate"), Some(-0.0005));
    }

    #[test]
    fn test_strict_finite_rejects_missing_field() {
        let obj = json!({"other": "0.0001"});
        assert_eq!(strict_parse_finite_f64(&obj, "fundingRate"), None);
    }

    #[test]
    fn test_strict_finite_rejects_non_string_and_unparseable() {
        // 非字串（Bybit 全 string-encoded；數字型視為異常 → reject）。
        assert_eq!(strict_parse_finite_f64(&json!({"fundingRate": 0.0}), "fundingRate"), None);
        // 無法 parse 的字串。
        assert_eq!(strict_parse_finite_f64(&json!({"fundingRate": "abc"}), "fundingRate"), None);
        // 空字串。
        assert_eq!(strict_parse_finite_f64(&json!({"fundingRate": ""}), "fundingRate"), None);
    }

    #[test]
    fn test_strict_finite_rejects_non_finite() {
        // "inf"/"nan" parse 成功但非有限 → reject（不寫毒值）。
        assert_eq!(strict_parse_finite_f64(&json!({"fundingRate": "inf"}), "fundingRate"), None);
        assert_eq!(strict_parse_finite_f64(&json!({"fundingRate": "NaN"}), "fundingRate"), None);
    }

    #[test]
    fn test_strict_ts_rejects_zero_and_missing() {
        assert_eq!(strict_parse_ts_ms(&json!({"timestamp": "0"}), "timestamp"), None);
        assert_eq!(strict_parse_ts_ms(&json!({"other": "1"}), "timestamp"), None);
        assert_eq!(strict_parse_ts_ms(&json!({"timestamp": "abc"}), "timestamp"), None);
        assert_eq!(
            strict_parse_ts_ms(&json!({"timestamp": "1700000000000"}), "timestamp"),
            Some(1_700_000_000_000)
        );
    }

    // ---- funding list strict ----

    /// 【最關鍵】真 0.0 funding → 接受；真 −0.0005（負）→ 接受；missing-field → reject。
    /// 證「不誤殺真 0.0 / 負 funding」+「仍擋 missing-field」。
    #[test]
    fn test_funding_strict_accepts_zero_and_negative_rejects_missing() {
        let raw = vec![
            json!({"fundingRateTimestamp": format!("{}", T0), "fundingRate": "0.0"}),
            json!({"fundingRateTimestamp": format!("{}", T0 + H8), "fundingRate": "-0.0005"}),
            // missing fundingRate → reject（不塌成 0.0）。
            json!({"fundingRateTimestamp": format!("{}", T0 + 2 * H8)}),
            // 正常正值。
            json!({"fundingRateTimestamp": format!("{}", T0 + 3 * H8), "fundingRate": "0.0001"}),
        ];
        let page = strict_parse_funding_list("linear", "BTCUSDT", &raw, T0, T0 + 3 * H8, 4);
        // 4 期望、3 通過（含 0.0 與負）、1 reject（missing）。
        assert_eq!(page.verdict.observed, 3);
        assert_eq!(page.verdict.rejected, 1);
        assert_eq!(page.verdict.status, CoverageStatus::Partial);
        // 真 0.0 確實被收（不是被當 fake-zero 丟掉）。
        assert!(page.points.iter().any(|p| p.funding_rate == 0.0 && p.funding_ts_ms == T0));
        // 真負值被收。
        assert!(page.points.iter().any(|p| p.funding_rate == -0.0005));
        // missing 那筆（T0+2*H8）不在 points。
        assert!(page.points.iter().all(|p| p.funding_ts_ms != T0 + 2 * H8));
    }

    /// 對照：若誤用 kline 的 `> 0.0` floor，真 0.0 / 負 funding 會被丟掉。本測試證明本模塊
    /// strict variant **不**有此行為（保留 0.0 與負）。
    #[test]
    fn test_funding_strict_does_not_apply_positive_floor() {
        let raw = vec![
            json!({"fundingRateTimestamp": format!("{}", T0), "fundingRate": "0.0"}),
            json!({"fundingRateTimestamp": format!("{}", T0 + H8), "fundingRate": "-0.01"}),
        ];
        let page = strict_parse_funding_list("linear", "ETHUSDT", &raw, T0, T0 + H8, 2);
        assert_eq!(page.verdict.observed, 2, "0.0 與負值都必須保留（非 >0 floor）");
        assert_eq!(page.verdict.rejected, 0);
        assert_eq!(page.verdict.status, CoverageStatus::Pass);
    }

    #[test]
    fn test_funding_strict_rejects_non_finite_and_bad_ts() {
        let raw = vec![
            json!({"fundingRateTimestamp": format!("{}", T0), "fundingRate": "inf"}), // 非有限 reject
            json!({"fundingRateTimestamp": "0", "fundingRate": "0.0001"}),            // ts=0 reject
            json!({"fundingRateTimestamp": format!("{}", T0 + 2 * H8), "fundingRate": "0.0002"}),
        ];
        let page = strict_parse_funding_list("linear", "SOLUSDT", &raw, T0, T0 + 2 * H8, 3);
        // ts=0 那筆 strict_parse_ts_ms 回 None → rejected（ts 不可信）。
        // inf 那筆 ts 合法、落窗內，rate 非有限 → rejected。
        assert_eq!(page.verdict.observed, 1);
        assert_eq!(page.verdict.rejected, 2);
    }

    #[test]
    fn test_funding_strict_window_clamp() {
        let raw = vec![
            json!({"fundingRateTimestamp": format!("{}", T0 - H8), "fundingRate": "0.0001"}), // 窗前
            json!({"fundingRateTimestamp": format!("{}", T0), "fundingRate": "0.0002"}),       // 窗內
            json!({"fundingRateTimestamp": format!("{}", T0 + 2 * H8), "fundingRate": "0.0003"}), // 窗後
        ];
        // 窗 [T0, T0+H8]：只 T0 那筆在窗內。
        let page = strict_parse_funding_list("linear", "XRPUSDT", &raw, T0, T0 + H8, 1);
        assert_eq!(page.verdict.observed, 1);
        // 窗外的點不計 rejected（非本窗職責）。
        assert_eq!(page.verdict.rejected, 0);
        assert!(page.points.iter().all(|p| p.funding_ts_ms == T0));
    }

    #[test]
    fn test_funding_strict_empty_failed() {
        let page = strict_parse_funding_list("linear", "BTCUSDT", &[], T0, T0 + 3 * H8, 3);
        assert_eq!(page.verdict.status, CoverageStatus::Failed);
        assert_eq!(page.verdict.observed, 0);
        assert_eq!(page.verdict.expected, 3);
    }

    #[test]
    fn test_funding_strict_dedup_same_ts() {
        let raw = vec![
            json!({"fundingRateTimestamp": format!("{}", T0), "fundingRate": "0.0001"}),
            json!({"fundingRateTimestamp": format!("{}", T0), "fundingRate": "0.0002"}), // 同 ts 取首見
        ];
        let page = strict_parse_funding_list("linear", "BTCUSDT", &raw, T0, T0 + H8, 1);
        assert_eq!(page.verdict.observed, 1);
        assert_eq!(page.points[0].funding_rate, 0.0001);
    }

    // ---- OI list strict ----

    #[test]
    fn test_oi_strict_accepts_any_finite_rejects_missing() {
        let raw = vec![
            json!({"timestamp": format!("{}", T0), "openInterest": "0"}),              // 0 OI 合法
            json!({"timestamp": format!("{}", T0 + H1), "openInterest": "123456.78"}),
            json!({"timestamp": format!("{}", T0 + 2 * H1)}),                          // missing → reject
            json!({"timestamp": format!("{}", T0 + 3 * H1), "openInterest": "inf"}),   // 非有限 → reject
        ];
        let page = strict_parse_oi_list("linear", "BTCUSDT", "1h", &raw, T0, T0 + 3 * H1, 4);
        assert_eq!(page.verdict.observed, 2);
        assert_eq!(page.verdict.rejected, 2);
        // 0 OI 被收（不設下界）。
        assert!(page.points.iter().any(|p| p.open_interest == 0.0 && p.ts_ms == T0));
    }

    #[test]
    fn test_oi_strict_interval_time_recorded() {
        let raw = vec![json!({"timestamp": format!("{}", T0), "openInterest": "100"})];
        let page = strict_parse_oi_list("linear", "ETHUSDT", "1h", &raw, T0, T0, 1);
        assert_eq!(page.interval_time, "1h");
        assert_eq!(page.verdict.status, CoverageStatus::Pass);
    }

    // ---- coverage status ----

    #[test]
    fn test_status_from_counts() {
        assert_eq!(status_from_counts(0, 0), CoverageStatus::Failed);
        assert_eq!(status_from_counts(0, 5), CoverageStatus::Pass); // 無分母 + 有資料 → pass
        assert_eq!(status_from_counts(4, 2), CoverageStatus::Partial);
        assert_eq!(status_from_counts(3, 3), CoverageStatus::Pass);
        assert_eq!(status_from_counts(3, 5), CoverageStatus::Pass); // observed 略超視 pass
    }

    #[test]
    fn test_coverage_status_db_str() {
        assert_eq!(CoverageStatus::Pass.as_db_str(), "pass");
        assert_eq!(CoverageStatus::Partial.as_db_str(), "partial");
        assert_eq!(CoverageStatus::Failed.as_db_str(), "failed");
    }

    // ---- payload sha256 ----

    #[test]
    fn test_payload_sha256_order_independent_and_content_sensitive() {
        let a = (T0, 0.0001_f64);
        let b = (T0 + H8, -0.0002_f64);
        let s1 = payload_sha256_pairs(&[a, b]);
        let s2 = payload_sha256_pairs(&[b, a]);
        assert_eq!(s1, s2, "排序後指紋與輸入順序無關");
        let c = (T0, 0.0009_f64);
        let s3 = payload_sha256_pairs(&[c, b]);
        assert_ne!(s1, s3, "不同內容指紋不同");
    }

    /// 證 0.0 與「缺值（不在集合）」的指紋不同 — 即真 0.0 入庫後可與 missing 區分。
    #[test]
    fn test_payload_sha256_zero_distinct_from_absent() {
        let with_zero = payload_sha256_pairs(&[(T0, 0.0)]);
        let absent = payload_sha256_pairs(&[]);
        assert_ne!(with_zero, absent);
    }

    // ---- next_page_cursor / result_list helpers ----

    #[test]
    fn test_next_page_cursor_empty_is_none() {
        let resp = BybitResponse {
            ret_code: 0,
            ret_msg: String::new(),
            result: json!({"nextPageCursor": ""}),
            time: 0,
        };
        assert_eq!(next_page_cursor(&resp), None);
        let resp2 = BybitResponse {
            ret_code: 0,
            ret_msg: String::new(),
            result: json!({"nextPageCursor": "abc%3D%3D"}),
            time: 0,
        };
        assert_eq!(next_page_cursor(&resp2), Some("abc%3D%3D".to_string()));
    }
}
