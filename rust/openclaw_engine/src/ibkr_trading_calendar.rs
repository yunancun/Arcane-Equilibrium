//! MODULE_NOTE
//! 模塊用途：**W6-S2 trading calendar 解析器**——消費 W6-S1 identity row 的
//!   `trading_hours`/`liquid_hours`/`time_zone_id` 原字串,產出 typed
//!   `IbkrTradingCalendarV1`(有序 session + 規範化 IANA tz + calendar_hash)。三件事:
//!   ①雙 grammar 解析(TWS ≤969 舊格式收盤側無日期 / 970+ 新格式收盤側帶日期 / `日期:CLOSED`
//!   全休);②legacy timeZoneId → IANA 白名單映射(未知 fail-closed 拒,不默認 America/New_York);
//!   ③DST-aware 絕對時刻(chrono-tz 依 IANA tz 解本地時,禁手寫偏移;跨午夜 session 解成次日
//!   絕對時刻)。calendar_hash 由本模塊鑄(sha256 over 契約 preimage),`compute_calendar_hash`
//!   導出供 W6-S3 provenance 綁定(實際 driver 接線 = S4)。
//! 主要函數：`parse_trading_calendar`(主入口)、`compute_calendar_hash`(provenance 綁定)、
//!   `legacy_tz_to_iana`(映射表)。
//! 依賴：`openclaw_types` 日曆契約、`chrono`/`chrono-tz`(DST)、`sha2`/`hex`(hash)。
//! 硬邊界：純函數、注入無時鐘(全靠 payload 日期字串)、零 socket、零 I/O、零下單、零 wire——
//!   壞格式 / 未知 tz / 亂序 一律 typed `Vec<IbkrTradingCalendarBlocker>` 回 `Err`,不 panic、
//!   不捏值、不默認。fixture 禁硬編當前日期(payload 日期為固定過去日,屬資料非牆鐘)。

use chrono::{NaiveDate, TimeZone};
use chrono_tz::Tz;
use sha2::{Digest, Sha256};

use openclaw_types::{
    IbkrCalendarHoursKindV1, IbkrCalendarSessionKindV1, IbkrInstrumentIdentityRowV1,
    IbkrTradingCalendarBlocker, IbkrTradingCalendarSessionV1, IbkrTradingCalendarV1,
    IBKR_TRADING_CALENDAR_CONTRACT_ID,
};

/// **legacy timeZoneId → 規範化 IANA 白名單映射**(v1 保守集:US 股市相關)。
///
/// 為什麼白名單而非任意 chrono-tz passthrough:IB 的 timeZoneId 值域是 legacy 名(非保證
/// IANA;官方列 `US/Eastern`/`EST`/…,class ref 甚至給 `EST`)——本 lane v1 只承 US 股市時區,
/// 未知一律 fail-closed 拒(不靜默默認 `America/New_York`)。映射目標名(America/New_York·
/// Chicago·Denver·Los_Angeles)亦自映射收進表——本表=**4-entry 有界 IANA 白名單**,非任意
/// chrono-tz passthrough。擴充須 IB 現勘 / EA 校準,禁順手加值。
pub fn legacy_tz_to_iana(raw: &str) -> Option<&'static str> {
    match raw {
        "US/Eastern" | "EST5EDT" | "EST" | "EDT" | "America/New_York" => Some("America/New_York"),
        "US/Central" | "CST6CDT" | "America/Chicago" => Some("America/Chicago"),
        "US/Mountain" | "MST7MDT" | "America/Denver" => Some("America/Denver"),
        "US/Pacific" | "PST8PDT" | "America/Los_Angeles" => Some("America/Los_Angeles"),
        _ => None,
    }
}

/// calendar_hash 鑄造:sha256(preimage) → 64 lowercase hex。preimage 是契約純函數(單一定義
/// 點,PIT 可重建——重放端以同 row 重建必得同 hash);雜湊計算居 engine(types crate 無雜湊依賴,
/// 契約只驗 shape)。**W6-S4 mint 接線**:provenance 的 `calendar_hash` 由本函數供給真值
/// (現行 begin_subscription 仍收上游 String,S4 於 driver 以本函數綁 identity row 解析結果)。
pub fn compute_calendar_hash(calendar: &IbkrTradingCalendarV1) -> String {
    let mut hasher = Sha256::new();
    hasher.update(calendar.calendar_hash_preimage().as_bytes());
    hex::encode(hasher.finalize())
}

/// **W6-S2 主入口**:解析 identity row 的 hours 字串 → typed 日曆。
///
/// `hours_kind` 決定解析 `liquid_hours`(RTH,v1 主目標)或 `trading_hours`(全時段);兩者同
/// grammar,共用解析器。fail-closed:未知 tz / 未識別 grammar / 非法日期 / 亂序 / 非法時刻
/// 一律回 `Err(Vec<blocker>)` 且**不產曆**(不默認、不捏值)。成功時回已通過契約 `validate()`
/// 的日曆(單一 fail-closed 收斂:parser 只在 validate 綠時回 Ok)。
pub fn parse_trading_calendar(
    row: &IbkrInstrumentIdentityRowV1,
    hours_kind: IbkrCalendarHoursKindV1,
) -> Result<IbkrTradingCalendarV1, Vec<IbkrTradingCalendarBlocker>> {
    use IbkrTradingCalendarBlocker as B;

    // ① tz 映射(未知即拒,不默認)。
    let iana = match legacy_tz_to_iana(row.time_zone_id.trim()) {
        Some(v) => v,
        None => return Err(vec![B::TimeZoneUnknownDenied]),
    };
    // 規範化 IANA 名恆可解析為 Tz(白名單目標皆合法);解析失敗屬映射表自身錯,fail-closed。
    let tz: Tz = match iana.parse() {
        Ok(t) => t,
        Err(_) => return Err(vec![B::TimeZoneUnknownDenied]),
    };

    // ② 選 hours 字串。
    let hours = match hours_kind {
        IbkrCalendarHoursKindV1::Rth => row.liquid_hours.as_str(),
        IbkrCalendarHoursKindV1::Trading => row.trading_hours.as_str(),
    };

    // ③ 逐 `;` 日期段解析(累積 blocker;任一壞即整體拒)。
    let mut sessions: Vec<IbkrTradingCalendarSessionV1> = Vec::new();
    let mut blockers: Vec<IbkrTradingCalendarBlocker> = Vec::new();
    let mut saw_segment = false;

    for raw_seg in hours.split(';') {
        let seg = raw_seg.trim();
        if seg.is_empty() {
            // 空段(如尾隨 `;`)寬容跳過;全空由 saw_segment 兜底判 GrammarUnrecognized。
            continue;
        }
        saw_segment = true;
        parse_segment(&tz, seg, &mut sessions, &mut blockers);
    }
    if !saw_segment {
        blockers.push(B::GrammarUnrecognized);
    }
    if !blockers.is_empty() {
        return Err(dedup_blockers(blockers));
    }

    // ④ 建曆 + 鑄 hash。
    let mut calendar = IbkrTradingCalendarV1 {
        contract_id: IBKR_TRADING_CALENDAR_CONTRACT_ID.to_string(),
        source_version: 1,
        asset_lane: openclaw_types::AssetLane::StockEtfCash,
        broker: openclaw_types::Broker::Ibkr,
        con_id: row.con_id,
        symbol: row.symbol.clone(),
        hours_kind,
        time_zone_iana: iana.to_string(),
        sessions,
        calendar_hash: String::new(),
        order_routed: false,
        secret_content_serialized: false,
    };
    calendar.calendar_hash = compute_calendar_hash(&calendar);

    // ⑤ 單一 fail-closed 收斂:只在契約 validate 綠時回 Ok(涵蓋亂序 / 空曆 / 時刻關係)。
    let verdict = calendar.validate();
    if !verdict.accepted {
        return Err(verdict.blockers);
    }
    Ok(calendar)
}

/// 解析單一 `;` 日期段(`YYYYMMDD:...`;`CLOSED` 全休 / 逗號分隔多 session)。
fn parse_segment(
    tz: &Tz,
    seg: &str,
    sessions: &mut Vec<IbkrTradingCalendarSessionV1>,
    blockers: &mut Vec<IbkrTradingCalendarBlocker>,
) {
    use IbkrTradingCalendarBlocker as B;

    // 段首必為 `YYYYMMDD:`;首個 `:` 前為日期。
    let colon = match seg.find(':') {
        Some(i) => i,
        None => {
            blockers.push(B::GrammarUnrecognized);
            return;
        }
    };
    let date_str = &seg[..colon];
    let rest = &seg[colon + 1..];
    let seg_date = match parse_yyyymmdd(date_str) {
        Some(d) => d,
        None => {
            blockers.push(B::DateInvalid);
            return;
        }
    };

    // 全休日:`日期:CLOSED`。
    if rest == "CLOSED" {
        sessions.push(IbkrTradingCalendarSessionV1 {
            date: date_str.to_string(),
            kind: IbkrCalendarSessionKindV1::Closed,
            open_ms: 0,
            close_ms: 0,
        });
        return;
    }

    // 開市:逗號分隔多 session(每段 `START-END`)。
    for sub in rest.split(',') {
        let sub = sub.trim();
        if sub.is_empty() {
            blockers.push(B::GrammarUnrecognized);
            continue;
        }
        parse_open_session(tz, date_str, seg_date, sub, sessions, blockers);
    }
}

/// 解析單一開市 session(`START-END`;`START`=HHMM,`END`=HHMM(舊)或 `YYYYMMDD:HHMM`(新))。
fn parse_open_session(
    tz: &Tz,
    seg_date_str: &str,
    seg_date: NaiveDate,
    sub: &str,
    sessions: &mut Vec<IbkrTradingCalendarSessionV1>,
    blockers: &mut Vec<IbkrTradingCalendarBlocker>,
) {
    use IbkrTradingCalendarBlocker as B;

    // 恰一個 `-` 分隔 START / END(新格式 END 內的 `:` 不含 `-`)。
    let dash: Vec<&str> = sub.split('-').collect();
    if dash.len() != 2 {
        blockers.push(B::GrammarUnrecognized);
        return;
    }
    let (start_raw, end_raw) = (dash[0], dash[1]);

    // START 恆 HHMM(段日期前綴已提供日期)。
    let start_hm = match parse_hhmm(start_raw) {
        Some(v) => v,
        None => {
            blockers.push(B::GrammarUnrecognized);
            return;
        }
    };

    // END:含 `:` = 新格式 `YYYYMMDD:HHMM`;否則 = 舊格式 HHMM(日期=段日期,跨午夜後補)。
    let (mut end_date, end_hm, end_had_date) = if let Some(i) = end_raw.find(':') {
        let ed = match parse_yyyymmdd(&end_raw[..i]) {
            Some(d) => d,
            None => {
                blockers.push(B::DateInvalid);
                return;
            }
        };
        let hm = match parse_hhmm(&end_raw[i + 1..]) {
            Some(v) => v,
            None => {
                blockers.push(B::GrammarUnrecognized);
                return;
            }
        };
        (ed, hm, true)
    } else {
        let hm = match parse_hhmm(end_raw) {
            Some(v) => v,
            None => {
                blockers.push(B::GrammarUnrecognized);
                return;
            }
        };
        (seg_date, hm, false)
    };

    let open_ms = match local_ms(tz, seg_date, start_hm) {
        Some(v) => v,
        None => {
            // DST gap 令該本地時刻不存在,或時刻早於紀元——非法。
            blockers.push(B::SessionTimeInvalid);
            return;
        }
    };
    let mut close_ms = match local_ms(tz, end_date, end_hm) {
        Some(v) => v,
        None => {
            blockers.push(B::SessionTimeInvalid);
            return;
        }
    };

    // 跨午夜:舊格式 END 無日期且 close≤open → 收市在次日,補一天重算。
    if !end_had_date && close_ms <= open_ms {
        if let Some(next) = end_date.succ_opt() {
            end_date = next;
            close_ms = match local_ms(tz, end_date, end_hm) {
                Some(v) => v,
                None => {
                    blockers.push(B::SessionTimeInvalid);
                    return;
                }
            };
        }
    }

    // 收市仍不晚於開市 → 非法時刻(新格式顯式日期倒退亦落此)。
    if close_ms <= open_ms {
        blockers.push(B::SessionTimeInvalid);
        return;
    }

    sessions.push(IbkrTradingCalendarSessionV1 {
        date: seg_date_str.to_string(),
        kind: IbkrCalendarSessionKindV1::Open,
        open_ms,
        close_ms,
    });
}

/// `(date, HHMM)` → epoch ms(DST 由 chrono-tz 依 IANA tz 解本地時,禁手寫偏移)。
/// DST gap(該本地時刻不存在)→ `None`;fold 歧義取較早;紀元前 → `None`。
fn local_ms(tz: &Tz, date: NaiveDate, hm: (u32, u32)) -> Option<u64> {
    let naive = date.and_hms_opt(hm.0, hm.1, 0)?;
    let dt = match tz.from_local_datetime(&naive) {
        chrono::LocalResult::Single(dt) => dt,
        // fold 歧義(秋退重複時刻):取 earliest=DST 側(如 America/New_York 秋退取 EDT)。
        // 本 lane RTH/tradingHours 窗(最早 0400)不觸及 01:00-01:59 fold 窗,實務 unreachable;
        // 此臂僅為確定性選擇避免 panic(對 open 時刻 earliest 非「較保守」,勿如此宣稱)。
        chrono::LocalResult::Ambiguous(a, _) => a,
        // DST gap(春進不存在時刻)。
        chrono::LocalResult::None => return None,
    };
    let ms = dt.timestamp_millis();
    if ms < 0 {
        return None;
    }
    Some(ms as u64)
}

/// `YYYYMMDD` → `NaiveDate`(語義日期驗;非 8 位 / 非數字 / 非法日期 → `None`)。
fn parse_yyyymmdd(raw: &str) -> Option<NaiveDate> {
    if raw.len() != 8 || !raw.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    let y: i32 = raw[..4].parse().ok()?;
    let m: u32 = raw[4..6].parse().ok()?;
    let d: u32 = raw[6..8].parse().ok()?;
    NaiveDate::from_ymd_opt(y, m, d)
}

/// `HHMM` → `(hour, minute)`(4 位數字,`hour<24`/`minute<60`;否則 `None`)。
fn parse_hhmm(raw: &str) -> Option<(u32, u32)> {
    if raw.len() != 4 || !raw.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    let h: u32 = raw[..2].parse().ok()?;
    let m: u32 = raw[2..4].parse().ok()?;
    if h >= 24 || m >= 60 {
        return None;
    }
    Some((h, m))
}

/// blocker 去重(保序;解析累積可能同碼多次,回報收斂單一 taxonomy)。
fn dedup_blockers(blockers: Vec<IbkrTradingCalendarBlocker>) -> Vec<IbkrTradingCalendarBlocker> {
    let mut seen: Vec<IbkrTradingCalendarBlocker> = Vec::new();
    for b in blockers {
        if !seen.contains(&b) {
            seen.push(b);
        }
    }
    seen
}

#[cfg(test)]
#[path = "ibkr_trading_calendar_tests.rs"]
mod tests;
