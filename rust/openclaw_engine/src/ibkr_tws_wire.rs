//! MODULE_NOTE
//! 模塊用途：IBKR **W3 TWS wire 層**（W3-S1;設計 §2.1/2.4/2.5/2.6）。純 codec + 分類 +
//!   framing + timeout,**無 I/O、無 socket、無狀態機**。B1（`ibkr_readonly_tws_client`)
//!   的純 codec §(a) 抽此;codec 自此有兩個消費者（B1 G4 探針 + W3 session manager),
//!   deletion test 過。
//! 主要區段：
//!   - (a) 純 codec（自 B1 §(a) 抽,語義**零變**):`encode_frame` / `try_decode_frame` /
//!     `encode_fields` / `decode_fields` / `encode_handshake_prefix` / `encode_start_api` /
//!     `encode_req_current_time` / `frame_msg_id` / `decode_server_handshake_ack` /
//!     `decode_current_time` / `decode_error_code` / `managed_accounts_all_paper`。
//!   - (b) `FrameReader`:streaming length-prefixed framing + **滾動窗預算**
//!     （`max_frames_per_window`/`max_bytes_per_window`,注入時鐘;長連線防惡意灌流。B1
//!     one-shot `ReadBudget` 是 G4 探針語義,此為 S2 長連線用)。
//!   - (c) 錯誤分類橋:`classify_error_frame`（decode_error_code + types
//!     `IbkrTwsErrorClassV1::conservative`);未知 msgId fail-closed（`classify_msg_id`)。
//!   - (d) timeout 正規化:`TimeoutPolicy` + `with_timeout`（每個 await 必包 timeout →
//!     typed `WireTimeout{op}`,禁裸 await 掛死;B1 PROBE_IO_TIMEOUT 範式推廣)。
//! 依賴：`tokio`（time,for `with_timeout`)、`openclaw_types`（error-class 契約 + 現勘 code
//!   常數 + IB_INFO_CODE_FLOOR)、`thiserror`。
//! 硬邊界：
//!   - **無 socket**:本檔零 `TcpStream::connect`（S1 CC 約束;TCP factory 是 S2+ 的
//!     `ibkr_transport_tcp` feature 事)。`with_timeout` 只包既有 future,不自建 I/O。
//!   - **DCE 姿態（W4 起更新;W5-S0 comment-only 修正）**:W3 時代「整面零 production
//!     caller → 全面 DCE」已過時——W4 health emitter
//!     （`ipc_server/handlers/stock_etf/health_summary.rs`）是 `TwsSessionManager` 的首個
//!     production caller,session/pacing 面已移出 DCE;本 wire 面經 manager 消費的部分可
//!     隨之鏈入。現行安全屬性=**真 I/O 消費者缺席**:`ibkr_tws_driver`
//!     （driver/factory/send_framed）在 default build 仍零 production caller → 被 DCE
//!     （`helper_scripts/ci/ibkr_driver_absence_audit.sh` nm 雙斷言:session 符號 present +
//!     driver 符號 absent;`ibkr_g4_symbol_audit.sh` 續驗 B1 G4 接觸面缺席）。本模塊
//!     `#![allow(dead_code)]` 保留——非「藏 orphan」:codec 有 B1 driver + 26 測試真消費,
//!     `FrameReader`/`TimeoutPolicy`/分類器有本檔測試消費;僅測試消費的面在 default build
//!     dead 是設計使然。
//!   - Bybit crypto_perp 不變;無 DB migration;無新契約入 IPC/DB。

// intentional-DCE 姿態(見 MODULE_NOTE;W4 起僅指真 I/O 面):W4 health emitter 已把
// session/pacing 接進 production,wire 面部分符號可經 manager 鏈入;driver(真 I/O
// 消費者)仍零 production caller,由 driver-absence audit nm 驗證。與 B1 line 49 對稱。
#![allow(dead_code)]

use std::collections::VecDeque;
use std::future::Future;
use std::time::Duration;

use openclaw_types::IbkrTwsErrorClassV1;

// ---------------------------------------------------------------------------
// 常量（自 B1 §(a) 遷入;codec 域)
// ---------------------------------------------------------------------------

/// 任何分配前的 frame 上界（≤64KB）。untrusted wire 的 length 欄先比此界,再分配。
pub(crate) const MAX_FRAME_LEN: usize = 64 * 1024;

/// TWS v100+ 握手前綴（4-byte,unframed;之後才是 4-byte BE length + payload 的 frame）。
pub(crate) const HANDSHAKE_PREFIX: &[u8] = b"API\0";

/// 客戶端支援的 API 版本區間（handshake payload `v{min}..{max}`）。min 對齊 types
/// `PINNED_MIN_SERVER_VERSION` 占位（100 = v100+ 協議下界)。
pub(crate) const CLIENT_MIN_VERSION: i32 = 100;
pub(crate) const CLIENT_MAX_VERSION: i32 = 176;

/// TWS msgId（wire 協議常量）。
pub(crate) const START_API_MSG_ID: &str = "71";
pub(crate) const START_API_VERSION: &str = "2";
pub(crate) const REQ_CURRENT_TIME_MSG_ID: &str = "49";
pub(crate) const REQ_CURRENT_TIME_VERSION: &str = "1";
pub(crate) const CURRENT_TIME_MSG_ID: i64 = 49;
pub(crate) const MANAGED_ACCOUNTS_MSG_ID: i64 = 15;
pub(crate) const NEXT_VALID_ID_MSG_ID: i64 = 9;
/// ERR_MSG（server 於 START_API 後必推的連線狀態通知）。
pub(crate) const ERR_MSG_MSG_ID: i64 = 4;
// W5-S2 account/positions **入站（IN）空間** msg ID。IB 現勘（2026-07-17,官方 ibapi
// 9.81.1.post1）:out/in 是兩個獨立編號空間,61-64 撞號——OUT 空間的 reqPositions=61 /
// reqAccountSummary=62 / cancelAccountSummary=63 / cancelPositions=64 常數居
// `ibkr_tws_account_data`;命名顯式帶 `IN_`/`OUT_` 方向以免撞號誤用。
/// IN 61:position 資料行。
pub(crate) const IN_POSITION_DATA_MSG_ID: i64 = 61;
/// IN 62:positionEnd（全量快照完成標記）。
pub(crate) const IN_POSITION_END_MSG_ID: i64 = 62;
/// IN 63:accountSummary 資料行。
pub(crate) const IN_ACCOUNT_SUMMARY_MSG_ID: i64 = 63;
/// IN 64:accountSummaryEnd（全量快照完成標記）。
pub(crate) const IN_ACCOUNT_SUMMARY_END_MSG_ID: i64 = 64;

// 注:`IB_INFO_CODE_FLOOR`（≥2100 info 地板)單處維護於 openclaw_types crate;B1 driver
// 直接自 openclaw_types import（避免兩份 2100 常數漂移)。本 wire 檔的錯誤分類走 types
// `IbkrTwsErrorClassV1::conservative`,不直接引用地板常數。

// ===========================================================================
// (a) 純 codec（無 I/O;自 B1 §(a) 抽,語義零變)
// ===========================================================================

/// codec 錯誤（全 typed;解析 untrusted wire 一律回此,絕不 panic / 捏值）。
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum CodecError {
    /// 欄位缺終止 `\0`（frame slice 尾有殘位元）——非「需更多位元組」（那是 `Ok(None)`）。
    #[error("frame field truncated (unterminated field in frame slice)")]
    Truncated,
    #[error("malformed frame: {0}")]
    Malformed(&'static str),
    /// msgId 不在 allowlist（handshake ack + 49 + 15 + 9）。
    #[error("unexpected msg id: {got}")]
    UnexpectedMsgId { got: i64 },
    /// 應為數字的欄位非數字（禁 `unwrap_or(0)` 捏造）。
    #[error("non-numeric field: {0}")]
    NonNumericField(&'static str),
    /// length 欄為 0（合法 TWS 訊息至少含 msgId 欄,故 0 長 = 損壞）。
    #[error("empty frame (zero length prefix)")]
    EmptyFrame,
    /// length 欄超過 `MAX_FRAME_LEN`（分配前即拒,杜絕 OOM）。
    #[error("frame too large (length prefix exceeds MAX_FRAME_LEN)")]
    FrameTooLarge,
}

/// server 首個握手回應（serverVersion + connectionTime,兩個 `\0`-終止欄）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct HandshakeAck {
    pub server_version: i32,
    pub connection_time: String,
}

/// encode 一個 framed 訊息：4-byte **big-endian u32** length + payload。
pub(crate) fn encode_frame(payload: &[u8]) -> Vec<u8> {
    let len = payload.len() as u32;
    let mut out = Vec::with_capacity(4 + payload.len());
    out.extend_from_slice(&len.to_be_bytes());
    out.extend_from_slice(payload);
    out
}

/// try-decode 一個 framed 訊息。`Ok(None)`=需更多位元組（尚未成 frame）;
/// `Ok(Some((consumed, payload)))`=成功（consumed = 4 + len）。
///
/// 硬化：length 讀 **u32 BE**（無負值可能）;`len==0` → `EmptyFrame`;
/// `len > MAX_FRAME_LEN` → `FrameTooLarge`（**任何分配前**即拒）;`with_capacity` 亦
/// clamp 至 `MAX_FRAME_LEN`。
pub(crate) fn try_decode_frame(buf: &[u8]) -> Result<Option<(usize, Vec<u8>)>, CodecError> {
    if buf.len() < 4 {
        return Ok(None);
    }
    let len = u32::from_be_bytes([buf[0], buf[1], buf[2], buf[3]]) as usize;
    if len == 0 {
        return Err(CodecError::EmptyFrame);
    }
    if len > MAX_FRAME_LEN {
        return Err(CodecError::FrameTooLarge);
    }
    let total = 4 + len;
    if buf.len() < total {
        return Ok(None);
    }
    // 分配前 len 已 <= MAX_FRAME_LEN;capacity 再 clamp 一次作縱深防禦。
    let mut payload = Vec::with_capacity(len.min(MAX_FRAME_LEN));
    payload.extend_from_slice(&buf[4..total]);
    Ok(Some((total, payload)))
}

/// encode `\0`-終止欄位序列（每欄尾附一個 `\0`;TWS wire 為 null-terminated 欄,非分隔）。
pub(crate) fn encode_fields(fields: &[&str]) -> Vec<u8> {
    let mut out = Vec::new();
    for f in fields {
        out.extend_from_slice(f.as_bytes());
        out.push(0);
    }
    out
}

/// decode `\0`-終止欄位。**嚴限 frame slice 內**：掃描 `\0` 切欄,任一欄非 ASCII → `Malformed`;
/// 末欄缺終止（尾有殘位元）→ `Truncated`。無越界索引、無 panic。
pub(crate) fn decode_fields(payload: &[u8]) -> Result<Vec<String>, CodecError> {
    let mut fields = Vec::new();
    let mut start = 0usize;
    for (i, &b) in payload.iter().enumerate() {
        if b == 0 {
            let raw = &payload[start..i];
            if !raw.is_ascii() {
                return Err(CodecError::Malformed("non-ascii field"));
            }
            let s =
                std::str::from_utf8(raw).map_err(|_| CodecError::Malformed("non-utf8 field"))?;
            fields.push(s.to_string());
            start = i + 1;
        }
    }
    // 末位元後仍有殘位元 = 有欄未被 `\0` 終止 → fail-closed（不吞、不猜）。
    if start != payload.len() {
        return Err(CodecError::Truncated);
    }
    Ok(fields)
}

/// encode v100+ 握手前綴：`b"API\0"` + framed `v{min}..{max}`（**版本字串為 raw payload,
/// 不 null-terminate**——與一般 msgId 訊息的 null-terminated 欄不同）。
pub(crate) fn encode_handshake_prefix(min: i32, max: i32) -> Vec<u8> {
    let version = format!("v{min}..{max}");
    let mut out = Vec::with_capacity(HANDSHAKE_PREFIX.len() + 4 + version.len());
    out.extend_from_slice(HANDSHAKE_PREFIX);
    out.extend_from_slice(&encode_frame(version.as_bytes()));
    out
}

/// encode START_API：framed `["71","2",client_id,""]`（末欄 optionalCapabilities="" ）。
pub(crate) fn encode_start_api(client_id: i32) -> Vec<u8> {
    let cid = client_id.to_string();
    encode_frame(&encode_fields(&[
        START_API_MSG_ID,
        START_API_VERSION,
        &cid,
        "",
    ]))
}

/// encode reqCurrentTime：framed `["49","1"]`。
pub(crate) fn encode_req_current_time() -> Vec<u8> {
    encode_frame(&encode_fields(&[
        REQ_CURRENT_TIME_MSG_ID,
        REQ_CURRENT_TIME_VERSION,
    ]))
}

/// 取一個已 decode frame 的 msgId（fields[0]）;空欄列 / 非數字 → typed err。
pub(crate) fn frame_msg_id(payload: &[u8]) -> Result<i64, CodecError> {
    let fields = decode_fields(payload)?;
    let first = fields
        .first()
        .ok_or(CodecError::Malformed("empty field list"))?;
    first
        .parse::<i64>()
        .map_err(|_| CodecError::NonNumericField("msg_id"))
}

/// decode server 握手 ACK：需 ≥2 欄;server_version 非數字 → `NonNumericField`（不捏 0）。
pub(crate) fn decode_server_handshake_ack(payload: &[u8]) -> Result<HandshakeAck, CodecError> {
    let fields = decode_fields(payload)?;
    if fields.len() < 2 {
        return Err(CodecError::Malformed("handshake ack needs >=2 fields"));
    }
    let server_version = fields[0]
        .parse::<i32>()
        .map_err(|_| CodecError::NonNumericField("server_version"))?;
    Ok(HandshakeAck {
        server_version,
        connection_time: fields[1].clone(),
    })
}

/// decode CURRENT_TIME（`["49","1",epoch]`）→ epoch 秒（i64）。msgId≠49 → `UnexpectedMsgId`;
/// epoch 非數字 → `NonNumericField`（不捏 0）。
pub(crate) fn decode_current_time(payload: &[u8]) -> Result<i64, CodecError> {
    let fields = decode_fields(payload)?;
    if fields.len() < 3 {
        return Err(CodecError::Malformed("current_time needs >=3 fields"));
    }
    let msg_id = fields[0]
        .parse::<i64>()
        .map_err(|_| CodecError::NonNumericField("msg_id"))?;
    if msg_id != CURRENT_TIME_MSG_ID {
        return Err(CodecError::UnexpectedMsgId { got: msg_id });
    }
    fields[2]
        .parse::<i64>()
        .map_err(|_| CodecError::NonNumericField("current_time_epoch"))
}

/// decode ERR_MSG（msgId 4）的 error code。IB v100+ ERR_MSG 欄序：
/// `[msgId, version, reqId, errorCode, errorMsg, ...]`——errorCode 在 index 3。需 ≥4 欄;
/// 少於 4 欄或 code 非數字 → typed err（不捏值、不 panic）。
///
/// 為什麼只取 code：連線通知的 errorMsg 是通用 farm 名稱（非帳號）,但驅動判定只需 code;
/// 只回 numeric code 令 fail-closed 判據與 telemetry 皆零明文逃逸。
pub(crate) fn decode_error_code(payload: &[u8]) -> Result<i64, CodecError> {
    let fields = decode_fields(payload)?;
    if fields.len() < 4 {
        return Err(CodecError::Malformed("err_msg needs >=4 fields"));
    }
    fields[3]
        .parse::<i64>()
        .map_err(|_| CodecError::NonNumericField("error_code"))
}

/// decode MANAGED_ACCOUNTS（msgId 15）並做 **paper 前綴實檢**。IB 欄序：
/// `[msgId, version, accountsCsv]`——fields[2] 為單欄逗號分隔帳號列表（與 fixture
/// `"15\0 1\0 DU1234567\0"` 一致）。按逗號切 token,每個 token 必須 `DU` 開頭
/// （IB paper 帳號固定前綴）;空列表 → `Malformed`（gateway 必回至少一個帳號,
/// 空 = 損壞或偽造,fail-closed）。
///
/// 為什麼只回 boolean（prefix-only inspect then drop）：實檢只需「是否全 DU」,
/// 明文帳號不 bind 具名變量、不 log、不 serialize、不進錯誤訊息——`fields` 於
/// fn 結束即整體 drop,維持 drop 側保守性。
pub(crate) fn managed_accounts_all_paper(payload: &[u8]) -> Result<bool, CodecError> {
    let fields = decode_fields(payload)?;
    let msg_id = fields
        .first()
        .ok_or(CodecError::Malformed("empty field list"))?
        .parse::<i64>()
        .map_err(|_| CodecError::NonNumericField("msg_id"))?;
    if msg_id != MANAGED_ACCOUNTS_MSG_ID {
        return Err(CodecError::UnexpectedMsgId { got: msg_id });
    }
    if fields.len() < 3 {
        return Err(CodecError::Malformed("managed_accounts needs >=3 fields"));
    }
    // 空帳號欄 = 空列表 → Malformed（不以空欄當「已驗證」）。
    if fields[2].is_empty() {
        return Err(CodecError::Malformed("managed_accounts empty account list"));
    }
    // 逐 token 前綴實檢：任一空 token 或非 `DU` 開頭 → false（呼叫端 fail-closed）。
    Ok(fields[2].split(',').all(|t| t.starts_with("DU")))
}

// ===========================================================================
// (b) FrameReader — streaming length-prefixed framing + 滾動窗預算
// TODO(S2):production 消費者 = W3-S2 session driver（長連線讀迴圈)。S1 僅立 + 測試。
// ===========================================================================

/// 滾動窗計數器：在 `window_ms` 內累計事件數,超過 `max_in_window` 即回 false。
/// **注入時鐘（now_ms)**,無 wall-clock 依賴（fixture 禁硬編日期 time-bomb)。
struct RollingWindow {
    window_ms: u64,
    max_in_window: u64,
    /// (ts_ms, count) 佇列;evict 逾窗者後 `sum` 為窗內總量。
    events: VecDeque<(u64, u64)>,
    sum: u64,
}

impl RollingWindow {
    fn new(window_ms: u64, max_in_window: u64) -> Self {
        Self {
            window_ms,
            max_in_window,
            events: VecDeque::new(),
            sum: 0,
        }
    }

    /// 記一筆 `count` 事件於 `now_ms`;先 evict 逾窗,再判「記入後窗內總量是否 ≤ max」。
    /// **超限即不 commit**（fail-closed:被拒的量代表未接受的 push,不得污染後續窗
    /// ——否則被拒嘗試會累積毒化滾動窗)。evict 條件:事件 ts + window_ms ≤ now_ms
    /// （即已滿一窗)。now_ms 單調不倒退由呼叫端保證。
    fn record(&mut self, now_ms: u64, count: u64) -> bool {
        while let Some(&(ts, c)) = self.events.front() {
            if ts.saturating_add(self.window_ms) <= now_ms {
                self.sum = self.sum.saturating_sub(c);
                self.events.pop_front();
            } else {
                break;
            }
        }
        if self.sum.saturating_add(count) > self.max_in_window {
            return false;
        }
        self.sum = self.sum.saturating_add(count);
        self.events.push_back((now_ms, count));
        true
    }
}

/// FrameReader 滾動窗上限（config;S3 pacing 之外,這是 wire 層防惡意灌流的底線)。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct FrameReaderLimits {
    pub window_ms: u64,
    pub max_frames_per_window: u64,
    pub max_bytes_per_window: u64,
}

/// FrameReader 錯誤：codec 錯誤（斷線）或滾動窗預算超限（fail-closed 斷線)。
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub(crate) enum FrameReaderError {
    #[error("codec error: {0}")]
    Codec(#[from] CodecError),
    /// 滾動窗內 frame 數超限（惡意灌流 / farm 風暴)→ fail-closed 斷線。
    #[error("frame rate exceeded (>{max} frames in {window_ms}ms)")]
    FrameRateExceeded { window_ms: u64, max: u64 },
    /// 滾動窗內 byte 數超限 → fail-closed 斷線。
    #[error("byte rate exceeded (>{max} bytes in {window_ms}ms)")]
    ByteRateExceeded { window_ms: u64, max: u64 },
}

/// streaming frame reader:餵位元組（`push_bytes`)→ 取 frame（`next_frame`)。B1 one-shot
/// `ReadBudget`（32 frame/256KB,G4 探針語義)之外,此為 S2 長連線用的**滾動窗**預算——
/// 長連線不能用一次性上界,改用「每窗 N frame / N byte」防惡意灌流。純狀態機,無 I/O。
pub(crate) struct FrameReader {
    buf: Vec<u8>,
    limits: FrameReaderLimits,
    frames: RollingWindow,
    bytes: RollingWindow,
}

impl FrameReader {
    pub(crate) fn new(limits: FrameReaderLimits) -> Self {
        Self {
            buf: Vec::new(),
            limits,
            frames: RollingWindow::new(limits.window_ms, limits.max_frames_per_window),
            bytes: RollingWindow::new(limits.window_ms, limits.max_bytes_per_window),
        }
    }

    /// 餵入新讀到的位元組（注入 now_ms 作滾動窗時鐘)。超 byte 率 → fail-closed。
    /// 空輸入不記帳（避免 0-byte read 蝕預算)。
    pub(crate) fn push_bytes(&mut self, bytes: &[u8], now_ms: u64) -> Result<(), FrameReaderError> {
        if bytes.is_empty() {
            return Ok(());
        }
        if !self.bytes.record(now_ms, bytes.len() as u64) {
            return Err(FrameReaderError::ByteRateExceeded {
                window_ms: self.limits.window_ms,
                max: self.limits.max_bytes_per_window,
            });
        }
        self.buf.extend_from_slice(bytes);
        Ok(())
    }

    /// 嘗試取下一個完整 frame payload;不足回 `Ok(None)`;損壞 → `Codec`;超 frame 率 →
    /// fail-closed（**在 drain 前檢預算**,超限即不消費 buffer,呼叫端斷線)。
    pub(crate) fn next_frame(&mut self, now_ms: u64) -> Result<Option<Vec<u8>>, FrameReaderError> {
        match try_decode_frame(&self.buf)? {
            Some((consumed, payload)) => {
                if !self.frames.record(now_ms, 1) {
                    return Err(FrameReaderError::FrameRateExceeded {
                        window_ms: self.limits.window_ms,
                        max: self.limits.max_frames_per_window,
                    });
                }
                self.buf.drain(0..consumed);
                Ok(Some(payload))
            }
            None => Ok(None),
        }
    }
}

// ===========================================================================
// (c) 錯誤分類橋 + 未知 msgId fail-closed（codec 層判定,不接 FSM)
// TODO(S2):production 消費者 = W3-S2 session driver。S1 僅立 + 測試。
// ===========================================================================

/// 已知 msgId 白名單分類（ACK 為握手首 frame 無 msgId,不在此列;W5-S2 擴入站 61-64)。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum KnownMsgId {
    /// 4:ERR_MSG（連線狀態通知,按 code 分類)。
    ErrMsg,
    /// 9:nextValidId。
    NextValidId,
    /// 15:managedAccounts。
    ManagedAccounts,
    /// 49:currentTime。
    CurrentTime,
    /// IN 61:position 資料行（W5-S2;OUT 空間 61=reqPositions,兩空間撞號,見常數注釋)。
    PositionData,
    /// IN 62:positionEnd。
    PositionEnd,
    /// IN 63:accountSummary 資料行。
    AccountSummary,
    /// IN 64:accountSummaryEnd。
    AccountSummaryEnd,
}

/// codec 層 msgId 白名單判定（**入站空間**）:已知 → `Some`;**未知 → `None`（fail-closed,
/// 呼叫端斷線,不猜欄位、不跳過)**。W6-W7 擴白名單時逐 msgId 加分支 + 測試,禁「默認略過」。
pub(crate) fn classify_msg_id(id: i64) -> Option<KnownMsgId> {
    match id {
        ERR_MSG_MSG_ID => Some(KnownMsgId::ErrMsg),
        NEXT_VALID_ID_MSG_ID => Some(KnownMsgId::NextValidId),
        MANAGED_ACCOUNTS_MSG_ID => Some(KnownMsgId::ManagedAccounts),
        CURRENT_TIME_MSG_ID => Some(KnownMsgId::CurrentTime),
        IN_POSITION_DATA_MSG_ID => Some(KnownMsgId::PositionData),
        IN_POSITION_END_MSG_ID => Some(KnownMsgId::PositionEnd),
        IN_ACCOUNT_SUMMARY_MSG_ID => Some(KnownMsgId::AccountSummary),
        IN_ACCOUNT_SUMMARY_END_MSG_ID => Some(KnownMsgId::AccountSummaryEnd),
        _ => None,
    }
}

/// 從 ERR_MSG(4) frame decode error code 並做**保守分類**（types
/// `IbkrTwsErrorClassV1::conservative`:現勘 code 用其分類,表外 code<2100→SessionFatal、
/// ≥2100→Info,絕不回 Unknown)。回 `(code, class)`:code 供 telemetry,class 供 S2 FSM 轉移。
/// 只帶 numeric code,零明文逃逸（沿 B1 `decode_error_code` 紀律)。
pub(crate) fn classify_error_frame(
    payload: &[u8],
) -> Result<(i64, IbkrTwsErrorClassV1), CodecError> {
    let code = decode_error_code(payload)?;
    Ok((code, IbkrTwsErrorClassV1::conservative(code)))
}

// ===========================================================================
// (d) timeout 正規化（每個 await 必包 timeout → typed;禁裸 await 掛死)
// TODO(S2):production 消費者 = W3-S2 session driver 的各 await 站點。S1 僅立 + 測試。
// ===========================================================================

/// timeout 作用的操作標籤（typed;telemetry / 錯誤區辨用,不含明文)。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum TimeoutOp {
    Connect,
    Io,
    HandshakeTotal,
    HeartbeatReply,
    GracefulClose,
}

/// 單一 timeout policy（config;設計 §2.5)。每個 await 站點取對應時限包裹。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct TimeoutPolicy {
    pub connect: Duration,
    pub io: Duration,
    pub handshake_total: Duration,
    pub heartbeat_reply: Duration,
    pub graceful_close: Duration,
}

impl Default for TimeoutPolicy {
    /// 設計 §2.5 默認:connect=5s / io=10s / handshake_total=15s / heartbeat_reply=10s /
    /// graceful_close=2s（B1 CONNECT_TIMEOUT=5s、PROBE_IO_TIMEOUT=10s 對齊)。
    fn default() -> Self {
        Self {
            connect: Duration::from_secs(5),
            io: Duration::from_secs(10),
            handshake_total: Duration::from_secs(15),
            heartbeat_reply: Duration::from_secs(10),
            graceful_close: Duration::from_secs(2),
        }
    }
}

/// timeout 逾期錯誤（typed,帶 op 標籤)。
#[derive(Debug, Clone, Copy, PartialEq, Eq, thiserror::Error)]
#[error("operation timed out: {op:?}")]
pub(crate) struct WireTimeout {
    pub op: TimeoutOp,
}

/// 把任一 future 包上 timeout:逾期 → `Err(WireTimeout{op})`,否則透傳 `Ok(output)`。
/// 禁裸 await（B1 PROBE_IO_TIMEOUT 範式推廣);本身不建 I/O,只包既有 future。
pub(crate) async fn with_timeout<F>(
    op: TimeoutOp,
    dur: Duration,
    fut: F,
) -> Result<F::Output, WireTimeout>
where
    F: Future,
{
    match tokio::time::timeout(dur, fut).await {
        Ok(output) => Ok(output),
        Err(_) => Err(WireTimeout { op }),
    }
}

// ===========================================================================
// 測試（synthetic,無 gateway、無 socket）
// ===========================================================================

#[cfg(test)]
mod tests {
    use super::*;

    // ---- (b) FrameReader ----

    fn limits(window_ms: u64, max_frames: u64, max_bytes: u64) -> FrameReaderLimits {
        FrameReaderLimits {
            window_ms,
            max_frames_per_window: max_frames,
            max_bytes_per_window: max_bytes,
        }
    }

    #[test]
    fn frame_reader_yields_frames_in_order() {
        let mut r = FrameReader::new(limits(1000, 100, 1_000_000));
        let mut wire = Vec::new();
        wire.extend_from_slice(&encode_frame(b"one"));
        wire.extend_from_slice(&encode_frame(b"two"));
        r.push_bytes(&wire, 0).unwrap();
        assert_eq!(r.next_frame(0).unwrap(), Some(b"one".to_vec()));
        assert_eq!(r.next_frame(0).unwrap(), Some(b"two".to_vec()));
        // 無更多 frame → None。
        assert_eq!(r.next_frame(0).unwrap(), None);
    }

    #[test]
    fn frame_reader_reassembles_split_frame() {
        let mut r = FrameReader::new(limits(1000, 100, 1_000_000));
        let framed = encode_frame(b"hello");
        // 先餵半個 frame（header 全 + payload 缺）→ None。
        r.push_bytes(&framed[0..6], 0).unwrap();
        assert_eq!(r.next_frame(0).unwrap(), None);
        // 餵剩餘 → 成 frame。
        r.push_bytes(&framed[6..], 1).unwrap();
        assert_eq!(r.next_frame(1).unwrap(), Some(b"hello".to_vec()));
    }

    #[test]
    fn frame_reader_byte_rate_exceeded_fail_closed() {
        // max_bytes=8/窗。餵 9 bytes → 超限。
        let mut r = FrameReader::new(limits(1000, 100, 8));
        let err = r.push_bytes(&[0u8; 9], 0).unwrap_err();
        assert!(matches!(err, FrameReaderError::ByteRateExceeded { .. }));
    }

    #[test]
    fn frame_reader_frame_rate_exceeded_fail_closed() {
        // max_frames=2/窗。同一 now 餵 3 個 1-byte frame → 第 3 個 next_frame 超限。
        let mut r = FrameReader::new(limits(1000, 2, 1_000_000));
        let mut wire = Vec::new();
        for _ in 0..3 {
            wire.extend_from_slice(&encode_frame(b"x"));
        }
        r.push_bytes(&wire, 0).unwrap();
        assert_eq!(r.next_frame(0).unwrap(), Some(b"x".to_vec()));
        assert_eq!(r.next_frame(0).unwrap(), Some(b"x".to_vec()));
        let err = r.next_frame(0).unwrap_err();
        assert!(matches!(err, FrameReaderError::FrameRateExceeded { .. }));
    }

    #[test]
    fn frame_reader_rolling_window_resets_after_window() {
        // max_bytes=8/1000ms。now=0 餵 8 bytes(剛好);now=1001 再餵 8 bytes → 舊事件已
        // evict,不超限（證明滾動窗真的滾,非累計上界)。
        let mut r = FrameReader::new(limits(1000, 100, 8));
        r.push_bytes(&[0u8; 8], 0).unwrap();
        // 同窗再餵 1 byte → 超限。
        assert!(matches!(
            r.push_bytes(&[0u8; 1], 500).unwrap_err(),
            FrameReaderError::ByteRateExceeded { .. }
        ));
        // 推進超過一窗 → 舊 8 bytes evict,再餵 8 bytes OK。
        r.push_bytes(&[0u8; 8], 1001).unwrap();
    }

    #[test]
    fn frame_reader_propagates_codec_error() {
        // 0-length frame → EmptyFrame(codec 斷線語義透傳)。
        let mut r = FrameReader::new(limits(1000, 100, 1_000_000));
        r.push_bytes(&[0, 0, 0, 0], 0).unwrap();
        let err = r.next_frame(0).unwrap_err();
        assert!(matches!(
            err,
            FrameReaderError::Codec(CodecError::EmptyFrame)
        ));
    }

    // ---- (c) msgId 白名單 + 錯誤分類橋 ----

    #[test]
    fn classify_msg_id_whitelist_and_unknown_fail_closed() {
        assert_eq!(classify_msg_id(4), Some(KnownMsgId::ErrMsg));
        assert_eq!(classify_msg_id(9), Some(KnownMsgId::NextValidId));
        assert_eq!(classify_msg_id(15), Some(KnownMsgId::ManagedAccounts));
        assert_eq!(classify_msg_id(49), Some(KnownMsgId::CurrentTime));
        // W5-S2:入站 account/positions 四 msgId（IN 空間;與 OUT 空間 61-64 撞號不混用）。
        assert_eq!(classify_msg_id(61), Some(KnownMsgId::PositionData));
        assert_eq!(classify_msg_id(62), Some(KnownMsgId::PositionEnd));
        assert_eq!(classify_msg_id(63), Some(KnownMsgId::AccountSummary));
        assert_eq!(classify_msg_id(64), Some(KnownMsgId::AccountSummaryEnd));
        // 未知 msgId → None（fail-closed,呼叫端斷線)。
        assert_eq!(classify_msg_id(8), None);
        assert_eq!(classify_msg_id(60), None);
        assert_eq!(classify_msg_id(65), None);
        assert_eq!(classify_msg_id(71), None);
    }

    #[test]
    fn classify_error_frame_bridges_codec_and_contract() {
        // 2104 info。
        let f = encode_fields(&["4", "2", "-1", "2104", "farm ok"]);
        assert_eq!(
            classify_error_frame(&f).unwrap(),
            (2104, IbkrTwsErrorClassV1::Info)
        );
        // 504 未連線 → SessionFatal。
        let f = encode_fields(&["4", "2", "-1", "504", "Not connected"]);
        assert_eq!(
            classify_error_frame(&f).unwrap(),
            (504, IbkrTwsErrorClassV1::SessionFatal)
        );
        // 100 pacing。
        let f = encode_fields(&["4", "2", "-1", "100", "max rate"]);
        assert_eq!(
            classify_error_frame(&f).unwrap(),
            (100, IbkrTwsErrorClassV1::Pacing)
        );
        // 326 duplicate client id → SessionFatal。
        let f = encode_fields(&["4", "2", "-1", "326", "client id in use"]);
        assert_eq!(
            classify_error_frame(&f).unwrap(),
            (326, IbkrTwsErrorClassV1::SessionFatal)
        );
        // 354 未訂閱 → Entitlement。
        let f = encode_fields(&["4", "2", "-1", "354", "not subscribed"]);
        assert_eq!(
            classify_error_frame(&f).unwrap(),
            (354, IbkrTwsErrorClassV1::Entitlement)
        );
        // 表外 code<2100 → 保守 SessionFatal。
        let f = encode_fields(&["4", "2", "-1", "1500", "mystery"]);
        assert_eq!(
            classify_error_frame(&f).unwrap(),
            (1500, IbkrTwsErrorClassV1::SessionFatal)
        );
        // 欄數不足 → Codec err（不裸索引)。
        let f = encode_fields(&["4", "2", "-1"]);
        assert!(matches!(
            classify_error_frame(&f),
            Err(CodecError::Malformed(_))
        ));
    }

    // ---- (d) timeout 正規化 ----

    #[test]
    fn timeout_policy_default_matches_design() {
        let p = TimeoutPolicy::default();
        assert_eq!(p.connect, Duration::from_secs(5));
        assert_eq!(p.io, Duration::from_secs(10));
        assert_eq!(p.handshake_total, Duration::from_secs(15));
        assert_eq!(p.heartbeat_reply, Duration::from_secs(10));
        assert_eq!(p.graceful_close, Duration::from_secs(2));
    }

    #[tokio::test]
    async fn with_timeout_passes_through_ready_future() {
        let out = with_timeout(TimeoutOp::Io, Duration::from_secs(10), async { 42 })
            .await
            .unwrap();
        assert_eq!(out, 42);
    }

    #[tokio::test]
    async fn with_timeout_elapses_to_typed_error() {
        // pending future + 極短時限 → typed WireTimeout,帶 op 標籤。
        let err = with_timeout(
            TimeoutOp::HandshakeTotal,
            Duration::from_millis(5),
            std::future::pending::<()>(),
        )
        .await
        .unwrap_err();
        assert_eq!(err.op, TimeoutOp::HandshakeTotal);
    }
}
