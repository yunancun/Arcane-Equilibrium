//! `ibkr_trading_calendar` 解析器測試(synthetic;無 gateway、無 socket、無牆鐘)。
//! 覆蓋:雙 grammar(舊/新)、CLOSED 全休、半日短 session、跨午夜、未知 TZ 拒、DST 春進秋退
//! 邊界、亂序 session 拒、空字串拒、grammar 未識別拒、非法日期拒、hash 決定性、tradingHours
//! 複用。**fixture 日期字串為固定過去日,屬 payload 資料非牆鐘依賴**(禁硬編當前日期)。

use super::*;
use openclaw_types::IbkrInstrumentIdentityRowV1;

/// 一天 86_400_000 ms(ms-of-day 斷言用)。
const MS_PER_DAY: u64 = 86_400_000;

/// 以指定 tz / liquid_hours / trading_hours 造 identity row(其餘沿 accepted fixture)。
fn row_with(tz: &str, liquid: &str, trading: &str) -> IbkrInstrumentIdentityRowV1 {
    let mut r = IbkrInstrumentIdentityRowV1::accepted_fixture();
    r.time_zone_id = tz.to_string();
    r.liquid_hours = liquid.to_string();
    r.trading_hours = trading.to_string();
    r
}

fn parse_rth(
    tz: &str,
    liquid: &str,
) -> Result<IbkrTradingCalendarV1, Vec<IbkrTradingCalendarBlocker>> {
    parse_trading_calendar(
        &row_with(tz, liquid, "20260302:0400-20260302:2000"),
        IbkrCalendarHoursKindV1::Rth,
    )
}

// ---------------------------------------------------------------------------
// 雙 grammar 正解
// ---------------------------------------------------------------------------

#[test]
fn new_grammar_parses_two_open_days() {
    // TWS 970+ 新格式(收盤側帶日期)。
    let c = parse_rth(
        "US/Eastern",
        "20260302:0930-20260302:1600;20260303:0930-20260303:1600",
    )
    .expect("new grammar parses");
    assert_eq!(c.sessions.len(), 2);
    assert_eq!(c.time_zone_iana, "America/New_York");
    assert!(c
        .sessions
        .iter()
        .all(|s| s.kind == IbkrCalendarSessionKindV1::Open));
    assert!(c.validate().accepted);
}

#[test]
fn old_grammar_parses_sessions_and_closed() {
    // TWS ≤969 舊格式(收盤側無日期;逗號分隔多 session;`日期:CLOSED` 全休)。
    let c = parse_rth("US/Eastern", "20090507:0700-1830,1830-2330;20090508:CLOSED")
        .expect("old grammar parses");
    assert_eq!(c.sessions.len(), 3);
    assert_eq!(c.sessions[0].kind, IbkrCalendarSessionKindV1::Open);
    assert_eq!(c.sessions[1].kind, IbkrCalendarSessionKindV1::Open);
    assert_eq!(c.sessions[2].kind, IbkrCalendarSessionKindV1::Closed);
    assert_eq!(c.sessions[2].open_ms, 0);
    assert_eq!(c.sessions[2].close_ms, 0);
}

#[test]
fn fully_closed_day() {
    let c = parse_rth("US/Eastern", "20260704:CLOSED").expect("closed day parses");
    assert_eq!(c.sessions.len(), 1);
    assert_eq!(c.sessions[0].kind, IbkrCalendarSessionKindV1::Closed);
}

#[test]
fn half_day_is_just_a_shorter_session() {
    // 半日=較短 session(官方無 half-day 字樣,UNVERIFIED;解析為短 session,不特殊標記)。
    let c = parse_rth("US/Eastern", "20261127:0930-1300").expect("half day parses");
    assert_eq!(c.sessions.len(), 1);
    let s = &c.sessions[0];
    // 3.5 小時盤(EST 內同 offset,差恆 3.5h,不受 DST 影響)。
    assert_eq!(s.close_ms - s.open_ms, 3 * 3_600_000 + 30 * 60_000);
}

// ---------------------------------------------------------------------------
// 跨午夜
// ---------------------------------------------------------------------------

#[test]
fn cross_midnight_old_grammar_rolls_to_next_day() {
    // 舊格式收盤側無日期:22:00-02:00 → 收市在次日。EDT(-4)內 open 22:00、close 次日 02:00 → 4h。
    let c = parse_rth("US/Eastern", "20260316:2200-0200").expect("cross-midnight parses");
    assert_eq!(c.sessions.len(), 1);
    let s = &c.sessions[0];
    assert_eq!(s.date, "20260316");
    assert!(s.close_ms > s.open_ms);
    assert_eq!(s.close_ms - s.open_ms, 4 * 3_600_000);
}

// ---------------------------------------------------------------------------
// DST 春進秋退邊界(America/New_York;ms-of-day == UTC 牆鐘)
// ---------------------------------------------------------------------------

#[test]
fn dst_spring_forward_boundary() {
    // 2026 春進 = 3/8。0306 09:30 EST(-5) → 14:30 UTC;0309 09:30 EDT(-4) → 13:30 UTC。
    let before = parse_rth("US/Eastern", "20260306:0930-1600").expect("pre-DST parses");
    let after = parse_rth("US/Eastern", "20260309:0930-1600").expect("post-DST parses");
    assert_eq!(
        before.sessions[0].open_ms % MS_PER_DAY,
        14 * 3_600_000 + 30 * 60_000
    );
    assert_eq!(
        after.sessions[0].open_ms % MS_PER_DAY,
        13 * 3_600_000 + 30 * 60_000
    );
}

#[test]
fn dst_fall_back_boundary() {
    // 2026 秋退 = 11/1。1030 09:30 EDT(-4) → 13:30 UTC;1102 09:30 EST(-5) → 14:30 UTC。
    let before = parse_rth("US/Eastern", "20261030:0930-1600").expect("pre-fallback parses");
    let after = parse_rth("US/Eastern", "20261102:0930-1600").expect("post-fallback parses");
    assert_eq!(
        before.sessions[0].open_ms % MS_PER_DAY,
        13 * 3_600_000 + 30 * 60_000
    );
    assert_eq!(
        after.sessions[0].open_ms % MS_PER_DAY,
        14 * 3_600_000 + 30 * 60_000
    );
}

#[test]
fn dst_gap_open_time_rejected() {
    // 2026 春進 = 3/8:02:00→03:00,02:00-02:59 本地時刻不存在。開市 02:30 落 DST gap →
    // `local_ms` 回 None → SessionTimeInvalid(鎖死 `LocalResult::None` 臂)。
    let err = parse_rth("US/Eastern", "20260308:0230-1600").unwrap_err();
    assert!(err.contains(&IbkrTradingCalendarBlocker::SessionTimeInvalid));
}

#[test]
fn dst_fold_open_takes_earliest_edt() {
    // 2026 秋退 = 11/1:02:00→01:00,01:00-01:59 重複(ambiguous)。開市 01:30 落 fold →
    // `local_ms` 取 earliest=EDT(-4) → 05:30 UTC(鎖死 `LocalResult::Ambiguous` 臂;
    // 收市 1600 於 EST(-5) 側 → 21:00 UTC,窗有序 → Ok)。
    let c = parse_rth("US/Eastern", "20261101:0130-1600").expect("fold-open parses");
    assert_eq!(c.sessions.len(), 1);
    assert_eq!(
        c.sessions[0].open_ms % MS_PER_DAY,
        5 * 3_600_000 + 30 * 60_000
    );
}

// ---------------------------------------------------------------------------
// fail-closed 拒絕矩陣
// ---------------------------------------------------------------------------

#[test]
fn unknown_timezone_denied() {
    let err = parse_rth("Mars/Phobos", "20260302:0930-1600").unwrap_err();
    assert_eq!(err, vec![IbkrTradingCalendarBlocker::TimeZoneUnknownDenied]);
}

#[test]
fn empty_hours_rejected() {
    let err = parse_rth("US/Eastern", "   ").unwrap_err();
    assert!(err.contains(&IbkrTradingCalendarBlocker::GrammarUnrecognized));
}

#[test]
fn unrecognized_grammar_rejected() {
    // 無日期冒號結構 → grammar 未識別。
    let err = parse_rth("US/Eastern", "not-a-calendar").unwrap_err();
    assert!(err.contains(&IbkrTradingCalendarBlocker::GrammarUnrecognized));
}

#[test]
fn bad_hhmm_rejected() {
    let err = parse_rth("US/Eastern", "20260302:9999-1600").unwrap_err();
    assert!(err.contains(&IbkrTradingCalendarBlocker::GrammarUnrecognized));
}

#[test]
fn invalid_date_rejected() {
    // 月份 13 → 語義非法日期。
    let err = parse_rth("US/Eastern", "20261335:0930-1600").unwrap_err();
    assert!(err.contains(&IbkrTradingCalendarBlocker::DateInvalid));
}

#[test]
fn out_of_order_sessions_rejected() {
    // 日期倒退(晚日在前)→ 亂序拒。
    let err = parse_rth("US/Eastern", "20260303:0930-1600;20260302:0930-1600").unwrap_err();
    assert!(err.contains(&IbkrTradingCalendarBlocker::SessionOutOfOrder));
}

#[test]
fn new_grammar_backwards_end_date_rejected() {
    // 新格式顯式收盤日期早於開市 → 時刻非法(不靜默跨日)。
    let err = parse_rth("US/Eastern", "20260303:0930-20260302:1600").unwrap_err();
    assert!(err.contains(&IbkrTradingCalendarBlocker::SessionTimeInvalid));
}

// ---------------------------------------------------------------------------
// hash 決定性 + legacy 映射 + tradingHours 複用
// ---------------------------------------------------------------------------

#[test]
fn calendar_hash_is_deterministic_sha256() {
    let a = parse_rth("US/Eastern", "20260302:0930-20260302:1600").unwrap();
    let b = parse_rth("US/Eastern", "20260302:0930-20260302:1600").unwrap();
    // 同 hours 字串重解 → 同 hash(PIT 可重建)。
    assert_eq!(a.calendar_hash, b.calendar_hash);
    // hash == compute_calendar_hash(preimage)(provenance 綁定的真值來源)。
    assert_eq!(a.calendar_hash, compute_calendar_hash(&a));
    assert_eq!(a.calendar_hash.len(), 64);
    assert!(a.calendar_hash.bytes().all(|c| c.is_ascii_hexdigit()));
    // 不同 session 時刻 → 不同 hash。
    let c = parse_rth("US/Eastern", "20260302:1000-20260302:1600").unwrap();
    assert_ne!(a.calendar_hash, c.calendar_hash);
}

#[test]
fn legacy_tz_mapping_covers_us_zones() {
    assert_eq!(legacy_tz_to_iana("US/Eastern"), Some("America/New_York"));
    assert_eq!(legacy_tz_to_iana("EST"), Some("America/New_York"));
    assert_eq!(legacy_tz_to_iana("US/Central"), Some("America/Chicago"));
    assert_eq!(legacy_tz_to_iana("US/Pacific"), Some("America/Los_Angeles"));
    assert_eq!(
        legacy_tz_to_iana("America/New_York"),
        Some("America/New_York")
    );
    assert_eq!(legacy_tz_to_iana("Mars/Phobos"), None);
}

#[test]
fn trading_hours_kind_reuses_parser() {
    let row = row_with(
        "US/Eastern",
        "20260302:0930-20260302:1600",
        "20260302:0400-20260302:2000",
    );
    let c = parse_trading_calendar(&row, IbkrCalendarHoursKindV1::Trading)
        .expect("trading hours parses");
    assert_eq!(c.hours_kind, IbkrCalendarHoursKindV1::Trading);
    // 全時段 0400-2000 = 16h。
    assert_eq!(
        c.sessions[0].close_ms - c.sessions[0].open_ms,
        16 * 3_600_000
    );
}
