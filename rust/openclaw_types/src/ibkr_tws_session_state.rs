//! IBKR W3 TWS session-state / error-class 契約（最小集，source-only）。
//!
//! 本檔是 W3-S1 交付的**契約層**：TWS wire 錯誤三元組的分類枚舉 + IB 官方現勘
//! error code 常數 + 客戶端 server-version pin 占位 + session state/event 骨架
//! （供 W3-S2 FSM 接線,S1 **不接線**）。不開 socket、不啟 Gateway、不路由訂單、
//! 不讀 secret；純資料/純函數。W4 health IPC 直接消費 `IbkrTwsErrorClassV1` 與
//! state/event 骨架。
//!
//! 出典紀律（loop §2:UNVERIFIED 不得寫成代碼常數）:本檔每個 error code 常數旁註
//! IB 官方 message-codes 文檔 URL + 現勘日期（2026-07-15 裁定的唯一可入碼集）。
//! 未經 IB 帶來源現勘的 code（如 U5「server 拒過低 client 的專屬 code」）**不得鑄造**。

use serde::{Deserialize, Serialize};

// ===========================================================================
// IB 官方現勘 error code 常數（出典=IB TWS API message codes；現勘日 2026-07-15）
// 官方文檔:https://interactivebrokers.github.io/tws-api/message_codes.html
// ===========================================================================

/// **100** — 每秒訊息數達上限（"Max rate of messages per second has been reached"）。
/// 分類 `Pacing`;IB 三次違規即斷 session（設計 §2.4 現勘,故本地 governor 必須讓違規
/// 結構性不可能——S3 事)。出典:官方 message_codes.html「System Message Codes」。
pub const IB_ERR_MAX_MESSAGE_RATE: i64 = 100;

/// **326** — client id 已被占用（"Unable to connect as the client id is already in use.
/// Retry with a unique client id."）。分類 `SessionFatal`;語義=**拒新連線,非踢舊連線**
/// （單 username 單 session 互踢的 R3 現勘中,326 對應「新連線被拒」形態）。出典:官方
/// message_codes.html「Client Errors」;現勘 2026-07-15。
pub const IB_ERR_DUPLICATE_CLIENT_ID: i64 = 326;

/// **354** — 請求的行情未訂閱（"Requested market data is not subscribed."）。分類
/// `Entitlement`;**per-request,不進 session 狀態機**（W6 訂閱表消費）。出典:官方
/// message_codes.html「Warning Message Codes」;現勘 2026-07-15。
pub const IB_ERR_MARKET_DATA_NOT_SUBSCRIBED: i64 = 354;

/// **502** — 無法連上 TWS（"Couldn't connect to TWS."）。分類 `SessionFatal`（未連線）。
/// 出典:官方 message_codes.html「Client Errors」;設計 §2.4 現勘。
pub const IB_ERR_COULD_NOT_CONNECT_TWS: i64 = 502;

/// **503** — TWS/IBG 過舊需升級（"The TWS is out of date and must be upgraded."）。分類
/// `SessionFatal`;語義=**TWS/IBG 過舊,非 client 被拒**（客戶端另走
/// `PINNED_MIN_SERVER_VERSION` 自檢 fail-closed → `ServerVersionTooOld`,不依賴 server 拒
/// 絕行為)。出典:官方 message_codes.html「Client Errors」;現勘 2026-07-15。
pub const IB_ERR_TWS_OUT_OF_DATE: i64 = 503;

/// **504** — 未連線（"Not connected."）。分類 `SessionFatal`。出典:官方
/// message_codes.html「Client Errors」;設計 §2.4 現勘（B1 driver 以 504 作 fatal 樣本)。
pub const IB_ERR_NOT_CONNECTED: i64 = 504;

/// **1100** — IB 與 TWS 間連線中斷（"Connectivity between IB and the TWS has been lost."）。
/// 分類 `Transient`;觸發後續 resubscribe 標記（S6/W6 用)。出典:官方 message_codes.html
/// 「System Message Codes」;現勘 2026-07-15。
pub const IB_ERR_CONNECTIVITY_LOST: i64 = 1100;

/// **1101** — 連線恢復但資料已失（"...has been restored - data lost."）。分類 `Transient`;
/// 語義帶 **data-lost → 必 resubscribe**。出典:官方 message_codes.html;現勘 2026-07-15。
pub const IB_ERR_CONNECTIVITY_RESTORED_DATA_LOST: i64 = 1101;

/// **1102** — 連線恢復且資料保留（"...has been restored - data maintained."）。分類
/// `Transient`（設計描述為 transient/info;採 transient 保守使呼叫端可 resubscribe 決策)。
/// 出典:官方 message_codes.html;現勘 2026-07-15。
pub const IB_ERR_CONNECTIVITY_RESTORED_DATA_KEPT: i64 = 1102;

/// **1300** — socket port 被重置且此連線被丟棄（"TWS socket port has been reset and this
/// connection is being dropped."）。分類 `SessionFatal`;語義=**需向新 port 重連=新活化**
/// （AMD:reconnect=新活化,W3 不自動猜新 port)。出典:官方 message_codes.html;現勘
/// 2026-07-15。
pub const IB_ERR_SOCKET_PORT_RESET: i64 = 1300;

/// **2103** — 行情 farm 連線中斷（"A market data farm connection has been lost."）。分類
/// `Transient`。出典:官方 message_codes.html「Warning Message Codes」;現勘 2026-07-15。
pub const IB_ERR_MKT_DATA_FARM_LOST: i64 = 2103;

/// **2104** — 行情 farm 連線正常（"Market data farm connection is OK"）。分類 `Info`
/// （握手期必然出現的連線 info,非錯誤)。出典:官方 message_codes.html;現勘 2026-07-15。
pub const IB_ERR_MKT_DATA_FARM_OK: i64 = 2104;

/// **2105** — 歷史資料 farm 連線中斷（"A historical data farm connection has been lost."）。
/// 分類 `Transient`。出典:官方 message_codes.html;現勘 2026-07-15。
pub const IB_ERR_HIST_DATA_FARM_LOST: i64 = 2105;

/// **2106** — 歷史資料 farm 已連線（"A historical data farm is connected."）。分類 `Info`。
/// 出典:官方 message_codes.html;現勘 2026-07-15。
pub const IB_ERR_HIST_DATA_FARM_OK: i64 = 2106;

/// **2107** — 歷史資料 farm 連線轉為 inactive 但可按需恢復。分類 `Info`。出典:官方
/// message_codes.html;現勘 2026-07-15。
pub const IB_ERR_HIST_DATA_FARM_INACTIVE: i64 = 2107;

/// **2108** — 行情 farm 連線轉為 inactive 但可按需恢復。分類 `Info`。出典:官方
/// message_codes.html;現勘 2026-07-15。
pub const IB_ERR_MKT_DATA_FARM_INACTIVE: i64 = 2108;

/// **2110** — TWS 與 server 間連線中斷,將自動恢復（"Connectivity between TWS and server is
/// broken. It will be restored automatically."）。分類 `Transient`。出典:官方
/// message_codes.html;現勘 2026-07-15。
pub const IB_ERR_TWS_SERVER_CONNECTIVITY_BROKEN: i64 = 2110;

/// **2158** — sec-def 資料 farm 連線正常（"Sec-def data farm connection is OK"）。分類
/// `Info`。出典:官方 message_codes.html;現勘 2026-07-15。
pub const IB_ERR_SECDEF_FARM_OK: i64 = 2158;

/// IB 連線 info/warning code 地板:**code ≥ 2100** = 純資訊/警告 connectivity 通知
/// （握手期必然出現且非錯誤);**code < 2100** = 真錯誤（如 502/504 未連線)。B1 E2 已實證
/// 此地板為真 IB Gateway 行為。現勘表外 code 的保守裁決以此為界（見 `conservative`)。
pub const IB_INFO_CODE_FLOOR: i64 = 2100;

// ===========================================================================
// 客戶端 server-version pin（占位;出典待 IB 現勘腿核定後才上調)
// ===========================================================================

/// 客戶端接受的**最低** server version;ACK 版本低於此即 `ServerVersionTooOld` session-fatal
/// （客戶端自檢 fail-closed,不依賴 server 拒絕行為,設計 §2.2/§8-U5)。
///
/// **占位初值 = 100**（TWS API v100+ 協議下界,= B1 `CLIENT_MIN_VERSION`)。凡我方實作的
/// 訊息 shape 需要更高 server version,pin 隨之上調並附出典——**由 IB 現勘腿核定後才進代碼**
/// （loop §2:UNVERIFIED 不得寫成代碼常數)。出典:IB TWS API v100+ 協議基線
/// （https://interactivebrokers.github.io/tws-api/）;現勘 2026-07-15。
pub const PINNED_MIN_SERVER_VERSION: i32 = 100;

// ===========================================================================
// error-class 枚舉 + 表驅動分類器（單一 const 表,單處維護)
// ===========================================================================

/// TWS wire 錯誤三元組的分類族。W4 health IPC 直接消費;S2 FSM 依此決定轉移
/// （transient→Backoff、session-fatal→Disconnected、entitlement=per-request 不進 FSM…)。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrTwsErrorClassV1 {
    /// farm/connectivity 斷復類:進 Backoff 可重試（1100/1101/1102/2103/2105/2110)。
    Transient,
    /// session 級致命:未連線 502/504、duplicate client-id 326、port reset 1300、TWS
    /// 過舊 503;不自動重試（reconnect=新活化)。
    SessionFatal,
    /// 行情未訂閱類 354:**per-request,不進 session 狀態機**（W6 消費)。
    Entitlement,
    /// pacing 超限 100:IB 三次違規斷 session;本地 governor 讓違規結構性不可能（S3)。
    Pacing,
    /// 訂單拒絕族（保留;分類表 W7 填,S1 不鑄造任何 order-reject code)。
    OrderReject,
    /// ≥2100 地板的純資訊/警告 connectivity 通知（2104/2106/2158/2107/2108)。
    Info,
    /// 契約 default/未初始化,亦=現勘表外 code 的**原始**分類（`classify` 回此)。actionable
    /// 裁決請用 `conservative`(現勘表外 code<2100→SessionFatal、≥2100→Info,絕不回 Unknown)。
    Unknown,
}

impl Default for IbkrTwsErrorClassV1 {
    fn default() -> Self {
        Self::Unknown
    }
}

impl IbkrTwsErrorClassV1 {
    /// 表驅動**原始**分類:僅現勘 code 回具體分類;現勘表外一律回 `Unknown`
    /// （telemetry 用「這個 code 是否在現勘表」的誠實答案)。單一 const 表,單處維護。
    pub fn classify(code: i64) -> Self {
        match code {
            IB_ERR_MAX_MESSAGE_RATE => Self::Pacing,
            IB_ERR_DUPLICATE_CLIENT_ID => Self::SessionFatal,
            IB_ERR_MARKET_DATA_NOT_SUBSCRIBED => Self::Entitlement,
            IB_ERR_COULD_NOT_CONNECT_TWS => Self::SessionFatal,
            IB_ERR_TWS_OUT_OF_DATE => Self::SessionFatal,
            IB_ERR_NOT_CONNECTED => Self::SessionFatal,
            IB_ERR_CONNECTIVITY_LOST => Self::Transient,
            IB_ERR_CONNECTIVITY_RESTORED_DATA_LOST => Self::Transient,
            IB_ERR_CONNECTIVITY_RESTORED_DATA_KEPT => Self::Transient,
            IB_ERR_SOCKET_PORT_RESET => Self::SessionFatal,
            IB_ERR_MKT_DATA_FARM_LOST => Self::Transient,
            IB_ERR_MKT_DATA_FARM_OK => Self::Info,
            IB_ERR_HIST_DATA_FARM_LOST => Self::Transient,
            IB_ERR_HIST_DATA_FARM_OK => Self::Info,
            IB_ERR_HIST_DATA_FARM_INACTIVE => Self::Info,
            IB_ERR_MKT_DATA_FARM_INACTIVE => Self::Info,
            IB_ERR_TWS_SERVER_CONNECTIVITY_BROKEN => Self::Transient,
            IB_ERR_SECDEF_FARM_OK => Self::Info,
            _ => Self::Unknown,
        }
    }

    /// **保守裁決**（fail-closed,actionable):現勘 code 用其分類;現勘表外 code<2100 →
    /// `SessionFatal`（保守斷線,不猜欄位不半接觸)、≥2100 → `Info`（既有地板,保留)。
    /// **絕不回 Unknown**——S2 FSM/斷線判定用此。
    pub fn conservative(code: i64) -> Self {
        match Self::classify(code) {
            Self::Unknown if code < IB_INFO_CODE_FLOOR => Self::SessionFatal,
            Self::Unknown => Self::Info,
            other => other,
        }
    }
}

// ===========================================================================
// session state/event 骨架（供 W3 session FSM;W4 IPC 消費面)
// S2 接線裁定（2026-07-16）:本枚舉維持 **IPC label 最小集**（unit-variant,snake_case 字串穩定)
//   ——rich payload（halt_reason / server_version / next_valid_id / backoff attempt / 心跳簿記…,
//   設計 §1.1)落 **engine-private** `openclaw_engine::ibkr_tws_session::SessionState`,經其 `label()`
//   投影回本枚舉。動機:types 契約改動最小、Copy/serde 字串穩定不破 S1 測試,rich 態不跨 IPC。
//   轉移表（設計 §1.2)與非法轉移由 engine FSM 實作(`IbkrTwsSessionEventV1` 為其 typed 事件輸出面)。
// ===========================================================================

/// TWS session FSM 狀態骨架（設計 §1.1;S1 unit-variant 骨架,payload 由 S2 補)。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrTwsSessionStateV1 {
    /// 未連線（S2 補 halt_reason)。初始態。
    Disconnected,
    /// transport 建立中。
    Connecting,
    /// 握手 + version pin + paper 實檢中。
    Handshaking,
    /// 就緒（S2 補 server_version/connection_time/paper_confirmed/next_valid_id)。
    Ready,
    /// 心跳連續 miss 標記劣化（socket 未斷)。
    Degraded,
    /// 退避中（S2 補 attempt_n/next_delay)。
    Backoff,
}

impl Default for IbkrTwsSessionStateV1 {
    fn default() -> Self {
        Self::Disconnected
    }
}

/// TWS session typed 事件骨架（設計 §1.2/§7;W4 IPC 消費面;S1 不接線)。
///
/// 注:`DuplicateClientIdRejected` **不叫** `...Kick`——326 語義=拒新連線非踢舊
/// （2026-07-15 裁定;設計舊稿 `DuplicateClientIdKick` 已按裁定改名)。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrTwsSessionEventV1 {
    /// connect permit 授予（單次 token;INV-1)。
    ConnectPermitGranted,
    /// permit 被拒:envelope 前置未滿足（W8 前 production 恆此路)。
    EnvelopeRequired,
    /// 326:client id 已占用→**拒新連線**（非踢舊);session-fatal。
    DuplicateClientIdRejected,
    /// 週日 ~1:00am ET 強制重認證窗:人工事務,永不自動重連。
    SessionExpiredWeeklyReauth,
    /// 重連預算耗盡（>max_reconnect_attempts):不無限重試。
    ReconnectBudgetExhausted,
    /// pacing 有界排隊溢出→拒呼叫端（非 silent drop)。
    PacingBudgetExceeded,
    /// nightly restart 窗內斷線:進 Backoff 但不計入 reconnect budget。
    ScheduledRestartDisconnect,
    /// ACK 版本 < PINNED_MIN_SERVER_VERSION:客戶端自檢 fail-closed。
    ServerVersionTooOld,
    /// managedAccounts 前綴實檢發現非 paper session。
    NonPaperSessionDetected,
    /// 非法轉移（debug_assert + typed 事件;設計 §1.2)。
    IllegalTransition,
    /// kill-switch epoch 變更/operator stop（W8 接真 epoch)。
    Halted,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn classify_maps_every_surveyed_code() {
        // pacing。
        assert_eq!(IbkrTwsErrorClassV1::classify(100), IbkrTwsErrorClassV1::Pacing);
        // session-fatal 家族。
        for c in [326i64, 502, 503, 504, 1300] {
            assert_eq!(
                IbkrTwsErrorClassV1::classify(c),
                IbkrTwsErrorClassV1::SessionFatal,
                "code {c} 應為 SessionFatal"
            );
        }
        // entitlement。
        assert_eq!(
            IbkrTwsErrorClassV1::classify(354),
            IbkrTwsErrorClassV1::Entitlement
        );
        // transient 家族。
        for c in [1100i64, 1101, 1102, 2103, 2105, 2110] {
            assert_eq!(
                IbkrTwsErrorClassV1::classify(c),
                IbkrTwsErrorClassV1::Transient,
                "code {c} 應為 Transient"
            );
        }
        // info 家族。
        for c in [2104i64, 2106, 2107, 2108, 2158] {
            assert_eq!(
                IbkrTwsErrorClassV1::classify(c),
                IbkrTwsErrorClassV1::Info,
                "code {c} 應為 Info"
            );
        }
    }

    #[test]
    fn classify_returns_unknown_for_unsurveyed() {
        // 現勘表外 code → 原始分類 Unknown（誠實:不在表內)。
        assert_eq!(
            IbkrTwsErrorClassV1::classify(9999),
            IbkrTwsErrorClassV1::Unknown
        );
        assert_eq!(
            IbkrTwsErrorClassV1::classify(1500),
            IbkrTwsErrorClassV1::Unknown
        );
    }

    #[test]
    fn conservative_never_returns_unknown_and_is_fail_closed() {
        // 現勘 code:保守裁決 = 其分類（不變)。
        assert_eq!(
            IbkrTwsErrorClassV1::conservative(354),
            IbkrTwsErrorClassV1::Entitlement
        );
        assert_eq!(
            IbkrTwsErrorClassV1::conservative(2104),
            IbkrTwsErrorClassV1::Info
        );
        // 現勘表外 code<2100 → SessionFatal（保守 fail-closed)。
        assert_eq!(
            IbkrTwsErrorClassV1::conservative(1500),
            IbkrTwsErrorClassV1::SessionFatal
        );
        assert_eq!(
            IbkrTwsErrorClassV1::conservative(321),
            IbkrTwsErrorClassV1::SessionFatal
        );
        // 現勘表外 code≥2100 → Info（既有地板)。
        assert_eq!(
            IbkrTwsErrorClassV1::conservative(2200),
            IbkrTwsErrorClassV1::Info
        );
        // 邊界:恰 2100（表外）→ Info;2099（表外）→ SessionFatal。
        assert_eq!(
            IbkrTwsErrorClassV1::conservative(2100),
            IbkrTwsErrorClassV1::Info
        );
        assert_eq!(
            IbkrTwsErrorClassV1::conservative(2099),
            IbkrTwsErrorClassV1::SessionFatal
        );
        // conservative 永不回 Unknown（掃一段 code 域驗證)。
        for c in -10i64..3000 {
            assert_ne!(
                IbkrTwsErrorClassV1::conservative(c),
                IbkrTwsErrorClassV1::Unknown,
                "conservative({c}) 不得為 Unknown"
            );
        }
    }

    #[test]
    fn error_class_default_is_unknown() {
        assert_eq!(
            IbkrTwsErrorClassV1::default(),
            IbkrTwsErrorClassV1::Unknown
        );
    }

    #[test]
    fn pinned_min_server_version_is_v100_placeholder() {
        // 占位初值 = 100（v100+ 協議下界);上調須附 IB 現勘出典。
        assert_eq!(PINNED_MIN_SERVER_VERSION, 100);
    }

    #[test]
    fn state_and_event_skeletons_serde_roundtrip() {
        // 骨架契約可 serialize（W4 IPC 消費面);snake_case 穩定。
        let st = IbkrTwsSessionStateV1::Backoff;
        let j = serde_json::to_string(&st).unwrap();
        assert_eq!(j, "\"backoff\"");
        assert_eq!(
            serde_json::from_str::<IbkrTwsSessionStateV1>(&j).unwrap(),
            st
        );
        assert_eq!(
            IbkrTwsSessionStateV1::default(),
            IbkrTwsSessionStateV1::Disconnected
        );

        let ev = IbkrTwsSessionEventV1::DuplicateClientIdRejected;
        let j = serde_json::to_string(&ev).unwrap();
        assert_eq!(j, "\"duplicate_client_id_rejected\"");
        assert_eq!(
            serde_json::from_str::<IbkrTwsSessionEventV1>(&j).unwrap(),
            ev
        );
    }
}
