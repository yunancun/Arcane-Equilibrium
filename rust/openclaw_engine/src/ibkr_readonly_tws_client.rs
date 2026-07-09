//! MODULE_NOTE
//! 模塊用途：IBKR **B1 只讀 TWS 連接器**（ADR-0048 / AMD-2026-07-08-01，G4 首次接觸）。
//!   只做 connect handshake + `reqCurrentTime`（=server-time / health 最小首接觸），零
//!   新治理契約。**build now / run=G4**（惰性；default build 不 auto-run、無 production
//!   caller、不接 socket）。B2/B3（account / positions / market-data）不在本 phase。
//! 主要區段（單檔 4 段）：
//!   - (a) 純 codec：`encode_frame` / `try_decode_frame` / `encode_fields` /
//!     `decode_fields` / `encode_handshake_prefix` / `encode_start_api` /
//!     `encode_req_current_time` / `decode_server_handshake_ack` /
//!     `decode_current_time`（無 I/O，synthetic fixture 可測）。
//!   - (b) generic driver：`drive_handshake_and_current_time<S>`（pub(crate)，泛型於
//!     `AsyncRead + AsyncWrite + Unpin`，不自持 socket；由 duplex / TcpStream 注入）。
//!   - (c) structural guards：`assert_loopback_paper_endpoint`（literal `127.0.0.1` +
//!     paper port 4002 only；4001 / 7496 硬拒），無 config 拓寬面。
//!   - (d) gated G4 entry：`g4_operator_triggered_first_contact`
//!     （`#[cfg(feature="ibkr_g4_contact")]`，唯一具體 `TcpStream::connect`）。
//! 依賴：`tokio`（io traits + net + time）、`openclaw_types`（port / AMD / ADR 常量）、
//!   `boot_observability::BUILD_GIT_SHA`（G4 approval anti-replay）、`sha2` 不需要（帳號
//!   採 drop 策略）、`toml` / `serde`（G4 approval 讀取）。
//! 硬邊界（絕不鬆動）：
//!   - **只讀**：源級不存在任何下單 / 撤單 / 改單方法（single write entry §1）；
//!     不接 IPC / dispatch / normalizer（P4）；不 auto-run；無 production caller。
//!   - **loopback + paper-port only**：connect 目標硬編 literal `127.0.0.1:4002`；live
//!     port（4001 / 7496）與非 loopback host 結構性拒，無 config 拓寬。
//!   - **不洩帳號**：握手中 gateway push `managedAccounts`（msgId 15，含 paper `DU…`）——
//!     payload 全欄 tokenize（僅為取 msgId）後**整體丟棄**，明文帳號從不 bind 具名變量、
//!     從不 log / serialize（「hash-or-drop」中最保守的 drop 側）。
//!   - **untrusted-wire fail-closed**：length 讀 u32 BE（無負）；任何分配前比
//!     `<= MAX_FRAME_LEN`；欄位 tokenizer 嚴限 frame slice 內，越界 / 非數字 / 非 ASCII /
//!     缺終止 → typed `CodecError`，零 unwrap / expect / panic / 裸索引 on parsed data，
//!     無捏造值（禁 `unwrap_or(0)`）；msgId 處理（ack + 49 done + 15/9 ignored + 4 ERR_MSG
//!     按 code 分流 / 其餘 UnexpectedMsgId）。
//!   - **惰性 G4 gate（任何 socket syscall 之前）**：env `OPENCLAW_IBKR_G4_CONTACT_APPLY==
//!     "1"` literal → `phase2_immutable_pass_artifact_present()`（真磁盤 re-verify，直接調
//!     producer）→ G4 approval 6 綁定 valid → structural host/port → 才 connect。
//!   - Bybit crypto_perp 不變；無 DB migration；不動 Python no-write / no-SDK 守衛。
//!
//! 字段映射（FA 裁：無新契約）：driver 回 engine-private `TwsHealthProbeResult`
//!   （非治理契約、無 validate、不跨 IPC / DB）。B1 **不** seal / persist / IPC 它（那是
//!   P4 / P5）；僅 G4 bin 打印供 QA 捕獲。它投影到既有 `IbkrApiSessionTopologyV1` /
//!   `IbkrSessionAttestationV1` 的子集（host / port / api_server_version / connection
//!   time），真 attestation land 於 P5。

#![allow(dead_code)]

use std::path::{Path, PathBuf};
use std::time::Duration;

use serde::Deserialize;
use tokio::io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt};

use openclaw_types::{
    IBKR_LIVE_GATEWAY_PORT, IBKR_LIVE_TWS_PORT, IBKR_PAPER_GATEWAY_DEFAULT_PORT, IBKR_PHASE2_ADR,
    IBKR_PHASE2_CONTACT_AMD,
};

use crate::boot_observability::BUILD_GIT_SHA;

// ---------------------------------------------------------------------------
// 常量
// ---------------------------------------------------------------------------

/// 任何分配前的 frame 上界（≤64KB）。untrusted wire 的 length 欄先比此界，再分配。
const MAX_FRAME_LEN: usize = 64 * 1024;

/// TWS v100+ 握手前綴（4-byte，unframed；之後才是 4-byte BE length + payload 的 frame）。
const HANDSHAKE_PREFIX: &[u8] = b"API\0";

/// 客戶端支援的 API 版本區間（handshake payload `v{min}..{max}`）。
const CLIENT_MIN_VERSION: i32 = 100;
const CLIENT_MAX_VERSION: i32 = 176;

/// TWS msgId（wire 協議常量）。
const START_API_MSG_ID: &str = "71";
const START_API_VERSION: &str = "2";
const REQ_CURRENT_TIME_MSG_ID: &str = "49";
const REQ_CURRENT_TIME_VERSION: &str = "1";
const CURRENT_TIME_MSG_ID: i64 = 49;
const MANAGED_ACCOUNTS_MSG_ID: i64 = 15;
const NEXT_VALID_ID_MSG_ID: i64 = 9;
/// ERR_MSG（server 於 START_API 後必推的連線狀態通知）。
const ERR_MSG_MSG_ID: i64 = 4;
/// IB 連線狀態 info/warning code 下界：**code ≥ 2100** = 純資訊/警告 connectivity 通知
/// （2104 market-data farm OK / 2106 HMDS farm OK / 2158 sec-def farm OK / 2107 / 2103…），
/// 握手期必然出現且非錯誤 → drain 續讀；**code < 2100** = 真錯誤（如 502/504 未連線）→
/// fail-closed。真實 IB Gateway 在 CURRENT_TIME(49) 之前推這些通知，故 drain 迴圈必須容忍，
/// 否則嚴格 allowlist 會令真 G4 握手必失敗（E2 RETURN #1）。
const IB_INFO_CODE_FLOOR: i64 = 2100;

/// G4 只讀探針的固定 client_id（read-only；不下單，故 master-client 語義無關）。
const G4_READONLY_CLIENT_ID: i32 = 0;

/// structural guard 常量：literal loopback IP（**非 "localhost"**——connect 目標硬編 IP，
/// 不走 hostname 解析，杜絕 DNS / hosts 覆寫繞過）+ paper-port only + live-port 硬拒。
const ALLOWED_HOST: &str = "127.0.0.1";
const PAPER_PORT: u16 = IBKR_PAPER_GATEWAY_DEFAULT_PORT;
const DENIED_PORTS: [u16; 2] = [IBKR_LIVE_GATEWAY_PORT, IBKR_LIVE_TWS_PORT];

/// G4 approval owner-only 檔名（**獨立**於 P2 seal approval，獨立 token；絕不接受 seal
/// approval 檔）。落於同 P2 治理目錄 `<OPENCLAW_DATA_DIR>/governance/ibkr_phase2`。
const G4_APPROVAL_FILENAME: &str = "phase2_g4_first_contact_approval.toml";

/// G4 approval issue→now 上界（bounded freshness，30 天）；超齡即視為過期（fail-closed）。
const G4_MAX_APPROVAL_AGE_MS: u64 = 30 * 24 * 60 * 60 * 1000;

/// 一次探針的 read/write 超時（loopback 掛死 gateway 不得掛死 engine）。
const PROBE_IO_TIMEOUT: Duration = Duration::from_secs(10);
/// connect 超時（僅 gated G4 路徑用）。
const CONNECT_TIMEOUT: Duration = Duration::from_secs(5);
/// read budget：G4 為 one-shot（handshake→1×currentTime→close），握手 push 有限，
/// 32 frame / 256KB 綽綽有餘且足以擋惡意 gateway 無限灌流。
const MAX_READ_FRAMES: usize = 32;
const MAX_TOTAL_READ_BYTES: usize = 256 * 1024;

// ===========================================================================
// (a) 純 codec（無 I/O）
// ===========================================================================

/// codec 錯誤（全 typed；解析 untrusted wire 一律回此，絕不 panic / 捏值）。
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
    /// length 欄為 0（合法 TWS 訊息至少含 msgId 欄，故 0 長 = 損壞）。
    #[error("empty frame (zero length prefix)")]
    EmptyFrame,
    /// length 欄超過 `MAX_FRAME_LEN`（分配前即拒，杜絕 OOM）。
    #[error("frame too large (length prefix exceeds MAX_FRAME_LEN)")]
    FrameTooLarge,
}

/// server 首個握手回應（serverVersion + connectionTime，兩個 `\0`-終止欄）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct HandshakeAck {
    pub server_version: i32,
    pub connection_time: String,
}

/// encode 一個 framed 訊息：4-byte **big-endian u32** length + payload。
fn encode_frame(payload: &[u8]) -> Vec<u8> {
    let len = payload.len() as u32;
    let mut out = Vec::with_capacity(4 + payload.len());
    out.extend_from_slice(&len.to_be_bytes());
    out.extend_from_slice(payload);
    out
}

/// try-decode 一個 framed 訊息。`Ok(None)`=需更多位元組（尚未成 frame）；
/// `Ok(Some((consumed, payload)))`=成功（consumed = 4 + len）。
///
/// 硬化：length 讀 **u32 BE**（無負值可能）；`len==0` → `EmptyFrame`；
/// `len > MAX_FRAME_LEN` → `FrameTooLarge`（**任何分配前**即拒）；`with_capacity` 亦
/// clamp 至 `MAX_FRAME_LEN`。
fn try_decode_frame(buf: &[u8]) -> Result<Option<(usize, Vec<u8>)>, CodecError> {
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
    // 分配前 len 已 <= MAX_FRAME_LEN；capacity 再 clamp 一次作縱深防禦。
    let mut payload = Vec::with_capacity(len.min(MAX_FRAME_LEN));
    payload.extend_from_slice(&buf[4..total]);
    Ok(Some((total, payload)))
}

/// encode `\0`-終止欄位序列（每欄尾附一個 `\0`；TWS wire 為 null-terminated 欄，非分隔）。
fn encode_fields(fields: &[&str]) -> Vec<u8> {
    let mut out = Vec::new();
    for f in fields {
        out.extend_from_slice(f.as_bytes());
        out.push(0);
    }
    out
}

/// decode `\0`-終止欄位。**嚴限 frame slice 內**：掃描 `\0` 切欄，任一欄非 ASCII → `Malformed`；
/// 末欄缺終止（尾有殘位元）→ `Truncated`。無越界索引、無 panic。
fn decode_fields(payload: &[u8]) -> Result<Vec<String>, CodecError> {
    let mut fields = Vec::new();
    let mut start = 0usize;
    for (i, &b) in payload.iter().enumerate() {
        if b == 0 {
            let raw = &payload[start..i];
            if !raw.is_ascii() {
                return Err(CodecError::Malformed("non-ascii field"));
            }
            let s = std::str::from_utf8(raw).map_err(|_| CodecError::Malformed("non-utf8 field"))?;
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

/// encode v100+ 握手前綴：`b"API\0"` + framed `v{min}..{max}`（**版本字串為 raw payload，
/// 不 null-terminate**——與一般 msgId 訊息的 null-terminated 欄不同）。
fn encode_handshake_prefix(min: i32, max: i32) -> Vec<u8> {
    let version = format!("v{min}..{max}");
    let mut out = Vec::with_capacity(HANDSHAKE_PREFIX.len() + 4 + version.len());
    out.extend_from_slice(HANDSHAKE_PREFIX);
    out.extend_from_slice(&encode_frame(version.as_bytes()));
    out
}

/// encode START_API：framed `["71","2",client_id,""]`（末欄 optionalCapabilities="" ）。
fn encode_start_api(client_id: i32) -> Vec<u8> {
    let cid = client_id.to_string();
    encode_frame(&encode_fields(&[
        START_API_MSG_ID,
        START_API_VERSION,
        &cid,
        "",
    ]))
}

/// encode reqCurrentTime：framed `["49","1"]`。
fn encode_req_current_time() -> Vec<u8> {
    encode_frame(&encode_fields(&[
        REQ_CURRENT_TIME_MSG_ID,
        REQ_CURRENT_TIME_VERSION,
    ]))
}

/// 取一個已 decode frame 的 msgId（fields[0]）；空欄列 / 非數字 → typed err。
fn frame_msg_id(payload: &[u8]) -> Result<i64, CodecError> {
    let fields = decode_fields(payload)?;
    let first = fields
        .first()
        .ok_or(CodecError::Malformed("empty field list"))?;
    first
        .parse::<i64>()
        .map_err(|_| CodecError::NonNumericField("msg_id"))
}

/// decode server 握手 ACK：需 ≥2 欄；server_version 非數字 → `NonNumericField`（不捏 0）。
fn decode_server_handshake_ack(payload: &[u8]) -> Result<HandshakeAck, CodecError> {
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

/// decode CURRENT_TIME（`["49","1",epoch]`）→ epoch 秒（i64）。msgId≠49 → `UnexpectedMsgId`；
/// epoch 非數字 → `NonNumericField`（不捏 0）。
fn decode_current_time(payload: &[u8]) -> Result<i64, CodecError> {
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
/// `[msgId, version, reqId, errorCode, errorMsg, ...]`——errorCode 在 index 3。需 ≥4 欄；
/// 少於 4 欄或 code 非數字 → typed err（不捏值、不 panic）。
///
/// 為什麼只取 code：連線通知的 errorMsg 是通用 farm 名稱（非帳號），但驅動判定只需 code；
/// 只回 numeric code 令 fail-closed 判據與 telemetry 皆零明文逃逸。
fn decode_error_code(payload: &[u8]) -> Result<i64, CodecError> {
    let fields = decode_fields(payload)?;
    if fields.len() < 4 {
        return Err(CodecError::Malformed("err_msg needs >=4 fields"));
    }
    fields[3]
        .parse::<i64>()
        .map_err(|_| CodecError::NonNumericField("error_code"))
}

// ===========================================================================
// (b) generic driver（pub(crate)，不自持 socket）
// ===========================================================================

/// driver 錯誤（含 codec + I/O + gate）。
#[derive(Debug, thiserror::Error)]
pub enum TwsClientError {
    #[error("codec error: {0}")]
    Codec(#[from] CodecError),
    #[error("io error: {0}")]
    Io(String),
    #[error("read/write timed out")]
    Timeout,
    #[error("read budget exceeded (frames or bytes)")]
    ReadBudgetExceeded,
    #[error("connection closed before current_time received")]
    ConnectionClosed,
    /// IB Gateway 於握手推送的真錯誤（ERR_MSG code < 2100，如 502/504 未連線）。只帶
    /// numeric code（非明文 errorMsg），零明文逃逸。
    #[error("ib gateway error during handshake (code {code})")]
    GatewayError { code: i64 },
    #[error("endpoint denied: {0}")]
    EndpointDenied(String),
    /// env `OPENCLAW_IBKR_G4_CONTACT_APPLY` 非 literal "1"（dry-run 預設）。
    #[error("g4 contact not applied (OPENCLAW_IBKR_G4_CONTACT_APPLY != \"1\")")]
    ContactNotApplied,
    /// sealed pass artifact 或 G4 approval 缺席 / 無效（fail-closed）。
    #[error("g4 first-contact gate blocked (sealed artifact or contact approval missing/invalid)")]
    GateBlocked,
}

/// 探針結果（engine-private；**非治理契約**，無 validate、不跨 IPC / DB）。僅 G4 bin
/// 打印供 QA 捕獲。投影到 `IbkrApiSessionTopologyV1` / `IbkrSessionAttestationV1` 子集
/// （P5 才 land 真 attestation）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TwsHealthProbeResult {
    pub server_version: i32,
    pub connection_time_raw: String,
    pub server_epoch_seconds: i64,
    pub endpoint_host: String,
    pub endpoint_port: u16,
    pub client_id: i32,
}

/// 探針配置（driver 不 connect，故 host/port 僅供結果記錄 + connect 端結構性斷言）。
pub(crate) struct TwsProbeConfig {
    pub client_id: i32,
    pub endpoint_host: String,
    pub endpoint_port: u16,
    pub min_version: i32,
    pub max_version: i32,
    pub io_timeout: Duration,
    pub max_read_frames: usize,
    pub max_total_read_bytes: usize,
}

impl TwsProbeConfig {
    /// G4 只讀探針的預設配置（loopback paper endpoint）。
    fn g4_default() -> Self {
        Self {
            client_id: G4_READONLY_CLIENT_ID,
            endpoint_host: ALLOWED_HOST.to_string(),
            endpoint_port: PAPER_PORT,
            min_version: CLIENT_MIN_VERSION,
            max_version: CLIENT_MAX_VERSION,
            io_timeout: PROBE_IO_TIMEOUT,
            max_read_frames: MAX_READ_FRAMES,
            max_total_read_bytes: MAX_TOTAL_READ_BYTES,
        }
    }
}

/// read/frame budget（loopback 掛死或惡意灌流時 fail-closed）。
struct ReadBudget {
    frames_read: usize,
    bytes_read: usize,
    max_frames: usize,
    max_bytes: usize,
}

impl ReadBudget {
    fn new(cfg: &TwsProbeConfig) -> Self {
        Self {
            frames_read: 0,
            bytes_read: 0,
            max_frames: cfg.max_read_frames,
            max_bytes: cfg.max_total_read_bytes,
        }
    }

    fn record_frame(&mut self) -> Result<(), TwsClientError> {
        self.frames_read = self.frames_read.saturating_add(1);
        if self.frames_read > self.max_frames {
            return Err(TwsClientError::ReadBudgetExceeded);
        }
        Ok(())
    }

    fn record_bytes(&mut self, n: usize) -> Result<(), TwsClientError> {
        self.bytes_read = self.bytes_read.saturating_add(n);
        if self.bytes_read > self.max_bytes {
            return Err(TwsClientError::ReadBudgetExceeded);
        }
        Ok(())
    }
}

async fn read_with_timeout<S: AsyncRead + Unpin>(
    stream: &mut S,
    buf: &mut [u8],
    io_timeout: Duration,
) -> Result<usize, TwsClientError> {
    match tokio::time::timeout(io_timeout, stream.read(buf)).await {
        Ok(Ok(n)) => Ok(n),
        Ok(Err(e)) => Err(TwsClientError::Io(e.to_string())),
        Err(_) => Err(TwsClientError::Timeout),
    }
}

async fn write_all_with_timeout<S: AsyncWrite + Unpin>(
    stream: &mut S,
    buf: &[u8],
    io_timeout: Duration,
) -> Result<(), TwsClientError> {
    match tokio::time::timeout(io_timeout, stream.write_all(buf)).await {
        Ok(Ok(())) => Ok(()),
        Ok(Err(e)) => Err(TwsClientError::Io(e.to_string())),
        Err(_) => Err(TwsClientError::Timeout),
    }
}

/// 從 stream 讀出下一個完整 frame payload（先試 decode 既有 buffer，不足才讀）。
async fn read_one_frame<S: AsyncRead + Unpin>(
    stream: &mut S,
    buf: &mut Vec<u8>,
    io_timeout: Duration,
    budget: &mut ReadBudget,
) -> Result<Vec<u8>, TwsClientError> {
    loop {
        match try_decode_frame(buf) {
            Ok(Some((consumed, payload))) => {
                buf.drain(0..consumed);
                budget.record_frame()?;
                return Ok(payload);
            }
            Ok(None) => {}
            Err(e) => return Err(TwsClientError::Codec(e)),
        }
        let mut tmp = [0u8; 4096];
        let n = read_with_timeout(stream, &mut tmp, io_timeout).await?;
        if n == 0 {
            // EOF 前未成完整 frame → 連線於握手中被關（fail-closed，不半解析）。
            return Err(TwsClientError::ConnectionClosed);
        }
        budget.record_bytes(n)?;
        buf.extend_from_slice(&tmp[..n]);
    }
}

/// 驅動一次 handshake + reqCurrentTime。序：寫 handshake prefix → 讀 framed ACK →
/// 寫 START_API → 寫 reqCurrentTime → 讀到 CURRENT_TIME(49)。**pub(crate) 不 pub**。
///
/// msgId 處理（讀 currentTime 迴圈內）：49（done）/ 15（managedAccounts，全欄 tokenize 取
/// msgId 後整體丟棄，明文帳號從不 bind/log/serialize）/ 9（nextValidId，ignored）/ 4
/// （ERR_MSG：code≥2100 = 連線 info/warning → 續讀；code<2100 = 真錯誤 → fail-closed
/// `GatewayError`）；其餘 → `UnexpectedMsgId`。真 IB Gateway 必在 49 之前推 id-4 通知，
/// 故必須容忍（E2 RETURN #1）；read-budget/timeout 仍為終止上界。
pub(crate) async fn drive_handshake_and_current_time<S: AsyncRead + AsyncWrite + Unpin>(
    mut stream: S,
    cfg: &TwsProbeConfig,
) -> Result<TwsHealthProbeResult, TwsClientError> {
    // 1) 寫 handshake prefix。
    let prefix = encode_handshake_prefix(cfg.min_version, cfg.max_version);
    write_all_with_timeout(&mut stream, &prefix, cfg.io_timeout).await?;

    // 2) 讀 framed ACK。
    let mut buf: Vec<u8> = Vec::new();
    let mut budget = ReadBudget::new(cfg);
    let ack_payload = read_one_frame(&mut stream, &mut buf, cfg.io_timeout, &mut budget).await?;
    let ack = decode_server_handshake_ack(&ack_payload)?;

    // 3) 寫 START_API + reqCurrentTime。
    let start_api = encode_start_api(cfg.client_id);
    write_all_with_timeout(&mut stream, &start_api, cfg.io_timeout).await?;
    let req_time = encode_req_current_time();
    write_all_with_timeout(&mut stream, &req_time, cfg.io_timeout).await?;

    // 4) 讀到 CURRENT_TIME(49)；握手 push 的 15 / 9 ignored，4（ERR_MSG）按 code 分流。
    let server_epoch_seconds = loop {
        let payload = read_one_frame(&mut stream, &mut buf, cfg.io_timeout, &mut budget).await?;
        let msg_id = frame_msg_id(&payload)?;
        match msg_id {
            CURRENT_TIME_MSG_ID => break decode_current_time(&payload)?,
            ERR_MSG_MSG_ID => {
                // ERR_MSG：typed 解析 error code（無 panic / 無裸索引）。真 IB Gateway 在 49
                // 之前必推 code≥2100 的連線 info/warning（2104/2106/2158/2107/2103…）→ 續讀；
                // code<2100 = 真錯誤 → fail-closed（不半接觸）。只帶 numeric code，零明文。
                let code = decode_error_code(&payload)?;
                if code >= IB_INFO_CODE_FLOOR {
                    continue;
                }
                return Err(TwsClientError::GatewayError { code });
            }
            MANAGED_ACCOUNTS_MSG_ID => {
                // managedAccounts：payload 全欄 tokenize（`frame_msg_id`→`decode_fields`）僅為
                // 取 msgId，取畢即整體丟棄——明文 `DU…` 帳號從不 bind 具名變量 / log / serialize
                // （hash-or-drop 中最保守的一側）。
                continue;
            }
            NEXT_VALID_ID_MSG_ID => continue,
            other => return Err(TwsClientError::Codec(CodecError::UnexpectedMsgId { got: other })),
        }
    };

    Ok(TwsHealthProbeResult {
        server_version: ack.server_version,
        connection_time_raw: ack.connection_time,
        server_epoch_seconds,
        endpoint_host: cfg.endpoint_host.clone(),
        endpoint_port: cfg.endpoint_port,
        client_id: cfg.client_id,
    })
}

// ===========================================================================
// (c) structural guards（無 config 拓寬面）
// ===========================================================================

/// 結構性 endpoint 斷言：非 `127.0.0.1` 拒、port∈{4001,7496} 拒、port≠4002 拒。
///
/// 為什麼 literal IP：connect host 硬編 `127.0.0.1`，不走 hostname / is_loopback helper，
/// 杜絕 `localhost` 經 DNS / hosts 覆寫指向非本機的繞過。
fn assert_loopback_paper_endpoint(host: &str, port: u16) -> Result<(), TwsClientError> {
    if host != ALLOWED_HOST {
        return Err(TwsClientError::EndpointDenied(format!(
            "host must be literal {ALLOWED_HOST}"
        )));
    }
    if DENIED_PORTS.contains(&port) {
        return Err(TwsClientError::EndpointDenied(format!(
            "live port {port} denied"
        )));
    }
    if port != PAPER_PORT {
        return Err(TwsClientError::EndpointDenied(format!(
            "port must be paper gateway {PAPER_PORT}"
        )));
    }
    Ok(())
}

// ===========================================================================
// G4 approval reader（owner-only；鏡像 P2 seal-approval 的 6 綁定，獨立檔 + 獨立 token）
// ===========================================================================

/// G4 首次接觸授權（TOML deser）。**獨立**於 P2 seal approval：獨立檔名 + 獨立型別，
/// 絕不接受 seal approval 檔（防以 shape 授權冒充 contact 授權）。
#[derive(Debug, Clone, PartialEq, Eq, Deserialize)]
pub(crate) struct G4ContactApproval {
    pub adr: String,
    pub amd: String,
    pub reviewer_roles: Vec<String>,
    pub approved_source_commit: String,
    pub issued_at_ms: u64,
    pub expires_at_ms: u64,
}

/// source_commit 必須是真世代——拒空 / 拒 build.rs 的 "unknown" fallback（anti-replay）。
fn source_commit_is_known(sha: &str) -> bool {
    !sha.trim().is_empty() && sha != "unknown"
}

/// G4 approval 6 綁定（缺一即 false → fail-closed，不放行接觸）：
/// 1) adr==ADR-0048；2) amd==contact-AMD 07-08-01（非 shape-AMD）；
/// 3) approved_source_commit==BUILD_GIT_SHA 且非 "unknown"（anti-replay）；
/// 4) reviewer_roles **含 PM 且 Operator**（忠實鏡像 P2 `approval_is_valid`，PM 裁決採更
///    fail-closed 的雙角色要求，E2 RETURN #2）；5) 時窗有效：issued>0、issued<=now、
///    expires>now、expires>issued；6) bounded freshness：now-issued<=30d；future-dated
///    （issued>now）判無效不 fail-open，clock 異常一律 fail-closed。
fn g4_approval_is_valid(a: &G4ContactApproval, now_ms: u64, build_sha: &str) -> bool {
    a.adr == IBKR_PHASE2_ADR
        && a.amd == IBKR_PHASE2_CONTACT_AMD
        && source_commit_is_known(build_sha)
        && a.approved_source_commit == build_sha
        && a.reviewer_roles.iter().any(|r| r == "PM")
        && a.reviewer_roles.iter().any(|r| r == "Operator")
        && a.issued_at_ms > 0
        && a.issued_at_ms <= now_ms
        && a.expires_at_ms > now_ms
        && a.expires_at_ms > a.issued_at_ms
        && now_ms.saturating_sub(a.issued_at_ms) <= G4_MAX_APPROVAL_AGE_MS
}

/// gov_dir 與其父 `governance/` 皆須 mode==0o700 且 owner==euid（鏡像 P2
/// `check_dir_pair_owner_only`）。lstat：symlink 祖先的 mode 不會是 0o700 → 自然 fail-closed。
#[cfg(unix)]
fn g4_check_dir_pair_owner_only(gov_dir: &Path) -> Result<(), String> {
    use std::os::unix::fs::{MetadataExt, PermissionsExt};

    let euid = unsafe { libc::geteuid() } as u32;
    for dir in [Some(gov_dir), gov_dir.parent()] {
        let path = dir.ok_or_else(|| "gov_dir has no parent (governance) dir".to_string())?;
        let meta = std::fs::symlink_metadata(path)
            .map_err(|e| format!("gov ancestor stat {} failed: {e}", path.display()))?;
        if (meta.permissions().mode() & 0o777) != 0o700 {
            return Err(format!(
                "gov ancestor not 0o700: {} mode={:#o}",
                path.display(),
                meta.permissions().mode() & 0o777
            ));
        }
        if meta.uid() as u32 != euid {
            return Err(format!("gov ancestor not owned by euid: {}", path.display()));
        }
    }
    Ok(())
}

/// G4 approval 讀取器（owner-only；鏡像 P2 `load_phase2_seal_approval_from_dir`）。
/// 缺檔 → `Ok(None)`（absent → 呼叫端不放行）；symlink / 非 0o600 / 非本人所有 /
/// 祖先鏈非 0o700 → `Err`（fail-closed）；存在且合法 → `Ok(Some)`。6 綁定內容由
/// `g4_approval_is_valid` 判定。
#[cfg(unix)]
fn load_g4_contact_approval_from_dir(gov_dir: &Path) -> Result<Option<G4ContactApproval>, String> {
    use std::os::unix::fs::{MetadataExt, PermissionsExt};

    let path = gov_dir.join(G4_APPROVAL_FILENAME);
    let meta = match std::fs::symlink_metadata(&path) {
        Ok(m) => m,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(e) => return Err(format!("g4 approval stat {} failed: {e}", path.display())),
    };
    // 綁定：檔本身不得為 symlink（lstat 不跟隨）。
    if meta.file_type().is_symlink() {
        return Err(format!("g4 approval file is symlink (denied): {}", path.display()));
    }
    if !meta.is_file() {
        return Err(format!("g4 approval path is not a regular file: {}", path.display()));
    }
    let euid = unsafe { libc::geteuid() } as u32;
    if (meta.permissions().mode() & 0o777) != 0o600 {
        return Err(format!("g4 approval file not 0o600: {}", path.display()));
    }
    if meta.uid() as u32 != euid {
        return Err(format!("g4 approval file not owned by euid: {}", path.display()));
    }
    // 綁定：0o700 祖先鏈。
    g4_check_dir_pair_owner_only(gov_dir)?;

    let raw = std::fs::read_to_string(&path)
        .map_err(|e| format!("read g4 approval {} failed: {e}", path.display()))?;
    let approval: G4ContactApproval = toml::from_str(&raw)
        .map_err(|e| format!("parse g4 approval {} failed: {e}", path.display()))?;
    Ok(Some(approval))
}

/// 非 unix：無法驗權限 / owner → 結構性 fail-closed 視為無 approval（部署目標皆 unix）。
#[cfg(not(unix))]
fn load_g4_contact_approval_from_dir(gov_dir: &Path) -> Result<Option<G4ContactApproval>, String> {
    let _ = gov_dir;
    Ok(None)
}

fn now_ms() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

/// 解析 G4 治理目錄 `<OPENCLAW_DATA_DIR>/governance/ibkr_phase2`（與 P2 同）。未設 / 空
/// → None（呼叫端 fail-closed）。ephemeral 拒由 AND-composed 的
/// `phase2_immutable_pass_artifact_present()`（本身 refuse-ephemeral）保障，此處不重複。
fn resolve_g4_governance_dir() -> Option<PathBuf> {
    match std::env::var("OPENCLAW_DATA_DIR") {
        Ok(raw) if !raw.trim().is_empty() => {
            Some(PathBuf::from(raw).join("governance").join("ibkr_phase2"))
        }
        _ => None,
    }
}

/// G4 approval 存在且 6 綁定 valid（absent / Err / 無效 → false，fail-closed）。
fn g4_contact_approval_present() -> bool {
    let gov_dir = match resolve_g4_governance_dir() {
        Some(d) => d,
        None => return false,
    };
    match load_g4_contact_approval_from_dir(&gov_dir) {
        Ok(Some(a)) => g4_approval_is_valid(&a, now_ms(), BUILD_GIT_SHA),
        _ => false,
    }
}

/// 首次接觸閘：sealed pass artifact 真磁盤 re-verify（**直接調 producer**，不自寫
/// file-exists）**且** G4 approval valid。
fn phase2_first_contact_gate_ok() -> bool {
    crate::ibkr_phase2_gate_producer::phase2_immutable_pass_artifact_present()
        && g4_contact_approval_present()
}

// ===========================================================================
// (d) gated G4 entry（唯一具體 TcpStream::connect）
// ===========================================================================

/// G4 gate posture（read-only；供 G4 bin dry-run 打印，無 socket）。
#[cfg(feature = "ibkr_g4_contact")]
#[derive(Debug, Clone)]
pub struct G4GateStatus {
    pub apply_env_set: bool,
    pub sealed_artifact_present: bool,
    pub contact_approval_valid: bool,
    pub gate_ok: bool,
}

/// 讀取 G4 gate 狀態（不接觸 socket）。供 bin dry-run 用。
#[cfg(feature = "ibkr_g4_contact")]
pub fn g4_first_contact_gate_status() -> G4GateStatus {
    let apply_env_set =
        std::env::var("OPENCLAW_IBKR_G4_CONTACT_APPLY").ok().as_deref() == Some("1");
    let sealed_artifact_present =
        crate::ibkr_phase2_gate_producer::phase2_immutable_pass_artifact_present();
    let contact_approval_valid = g4_contact_approval_present();
    G4GateStatus {
        apply_env_set,
        sealed_artifact_present,
        contact_approval_valid,
        gate_ok: sealed_artifact_present && contact_approval_valid,
    }
}

/// **唯一** 具體 `tokio::net::TcpStream::connect`。runtime-gate 順序（全在任何 socket
/// syscall 之前）：env `OPENCLAW_IBKR_G4_CONTACT_APPLY=="1"` literal（unset → dry-run 不
/// 接觸）→ `phase2_immutable_pass_artifact_present()`（真磁盤 re-verify）→ G4 approval 6
/// 綁定 valid → structural host/port const → 才 connect。
///
/// G4 為 one-shot：connect → handshake → 1×currentTime → close（stream drop）。無
/// production caller（僅 G4 bin 於 operator 顯式 `--contact` + env 觸發）。
#[cfg(feature = "ibkr_g4_contact")]
pub async fn g4_operator_triggered_first_contact() -> Result<TwsHealthProbeResult, TwsClientError> {
    // Gate 1：env APPLY literal "1"——在任何 socket syscall 之前。
    if std::env::var("OPENCLAW_IBKR_G4_CONTACT_APPLY").ok().as_deref() != Some("1") {
        return Err(TwsClientError::ContactNotApplied);
    }
    // Gate 2+3：sealed pass artifact re-verify + G4 approval 6 綁定 valid。
    if !phase2_first_contact_gate_ok() {
        return Err(TwsClientError::GateBlocked);
    }
    // Gate 4：structural host/port const（literal 127.0.0.1:4002；live port 硬拒）。
    assert_loopback_paper_endpoint(ALLOWED_HOST, PAPER_PORT)?;

    // 才 connect（唯一具體 TcpStream::connect）。
    let addr = format!("{ALLOWED_HOST}:{PAPER_PORT}");
    let stream = match tokio::time::timeout(
        CONNECT_TIMEOUT,
        tokio::net::TcpStream::connect(&addr),
    )
    .await
    {
        Ok(Ok(s)) => s,
        Ok(Err(e)) => return Err(TwsClientError::Io(e.to_string())),
        Err(_) => return Err(TwsClientError::Timeout),
    };

    let cfg = TwsProbeConfig::g4_default();
    drive_handshake_and_current_time(stream, &cfg).await
}

// ===========================================================================
// 測試（synthetic，無 gateway；權限 / approval 測試 #[cfg(unix)]；env 測試共用鎖）
// ===========================================================================

#[cfg(test)]
mod tests {
    use super::*;
    // trait method（write_all / read_to_end）需 Ext trait 於 scope；glob `use super::*`
    // 不保證帶入父模塊的私有 `use` 導入，故顯式導入。
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

    // ---- (a) codec ----

    #[test]
    fn frame_roundtrip_and_partial() {
        let framed = encode_frame(b"hello");
        // 4-byte BE length header = 5。
        assert_eq!(framed[0], 0u8);
        assert_eq!(framed[1], 0u8);
        assert_eq!(framed[2], 0u8);
        assert_eq!(framed[3], 5u8);
        // 完整 frame → Ok(Some)。
        let (consumed, payload) = try_decode_frame(&framed).unwrap().unwrap();
        assert_eq!(consumed, 9);
        assert_eq!(payload, b"hello".to_vec());
        // 不足 4-byte header → Ok(None)。
        assert_eq!(try_decode_frame(&framed[0..3]).unwrap(), None);
        // header 齊但 payload 不足 → Ok(None)。
        assert_eq!(try_decode_frame(&framed[0..7]).unwrap(), None);
    }

    #[test]
    fn frame_zero_length_and_too_large() {
        assert_eq!(try_decode_frame(&[0, 0, 0, 0]), Err(CodecError::EmptyFrame));
        // 0xFFFFFFFF length → FrameTooLarge（分配前即拒）。
        assert_eq!(
            try_decode_frame(&[0xFF, 0xFF, 0xFF, 0xFF]),
            Err(CodecError::FrameTooLarge)
        );
    }

    #[test]
    fn handshake_prefix_byte_exact() {
        // v100..176 payload 正好 9 bytes。
        let got = encode_handshake_prefix(100, 176);
        let mut expect: Vec<u8> = Vec::new();
        expect.extend_from_slice(b"API\0");
        expect.extend_from_slice(&[0u8, 0, 0, 9]); // BE length of "v100..176" (9 bytes)
        expect.extend_from_slice(b"v100..176");
        assert_eq!(got, expect);
    }

    #[test]
    fn start_api_and_req_current_time_byte_exact() {
        // START_API client_id=0 → framed "71\0 2\0 0\0 \0"（8 bytes）。
        let got = encode_start_api(0);
        let body = b"71\x002\x000\x00\x00";
        let mut expect = vec![0, 0, 0, body.len() as u8];
        expect.extend_from_slice(body);
        assert_eq!(got, expect);

        // reqCurrentTime → framed "49\0 1\0"（5 bytes）。
        let got2 = encode_req_current_time();
        let body2 = b"49\x001\x00";
        let mut expect2 = vec![0, 0, 0, body2.len() as u8];
        expect2.extend_from_slice(body2);
        assert_eq!(got2, expect2);
    }

    #[test]
    fn decode_ack_and_current_time() {
        let ack = decode_server_handshake_ack(b"176\x0020240101 09:30:00 EST\x00").unwrap();
        assert_eq!(ack.server_version, 176);
        assert_eq!(ack.connection_time, "20240101 09:30:00 EST");

        let epoch = decode_current_time(b"49\x001\x001700000000\x00").unwrap();
        assert_eq!(epoch, 1_700_000_000);
    }

    #[test]
    fn decode_current_time_rejects_wrong_id_and_nonnumeric() {
        // msgId 9 送進 current_time decoder → UnexpectedMsgId。
        assert_eq!(
            decode_current_time(b"9\x001\x00123\x00"),
            Err(CodecError::UnexpectedMsgId { got: 9 })
        );
        // epoch 非數字 → NonNumericField（不捏 0）。
        assert_eq!(
            decode_current_time(b"49\x001\x00abc\x00"),
            Err(CodecError::NonNumericField("current_time_epoch"))
        );
    }

    #[test]
    fn decode_fields_truncated_and_nonascii() {
        // 末欄缺終止 → Truncated。
        assert_eq!(decode_fields(b"49\x001"), Err(CodecError::Truncated));
        // 非 ASCII 欄 → Malformed。
        assert_eq!(
            decode_fields(b"\x80\x00"),
            Err(CodecError::Malformed("non-ascii field"))
        );
        // handshake ack server_version 非數字 → NonNumericField。
        assert_eq!(
            decode_server_handshake_ack(b"vX\x00time\x00"),
            Err(CodecError::NonNumericField("server_version"))
        );
    }

    // ---- (a) property / fuzz：任意位元組永不 panic ----

    fn lcg_next(state: &mut u64) -> u64 {
        *state = state
            .wrapping_mul(6364136223846793005)
            .wrapping_add(1442695040888963407);
        *state
    }

    #[test]
    fn fuzz_codec_never_panics() {
        let mut state: u64 = 0x1234_5678_9abc_def0;
        for _ in 0..20_000 {
            let len = (lcg_next(&mut state) % 300) as usize;
            let mut bytes = Vec::with_capacity(len);
            for _ in 0..len {
                bytes.push((lcg_next(&mut state) & 0xFF) as u8);
            }
            // 四個解析入口全部餵；任何 panic 都會令測試失敗。
            let _ = try_decode_frame(&bytes);
            let _ = decode_fields(&bytes);
            let _ = decode_server_handshake_ack(&bytes);
            let _ = decode_current_time(&bytes);
            let _ = frame_msg_id(&bytes);
        }
        // 顯式對抗案例。
        assert!(matches!(try_decode_frame(&[0xFF, 0xFF, 0xFF, 0xFF]), Err(CodecError::FrameTooLarge)));
        assert!(matches!(try_decode_frame(&[0, 0, 0, 0]), Err(CodecError::EmptyFrame)));
        assert!(matches!(try_decode_frame(&[0, 0, 0, 5, 1, 2, 3]), Ok(None)));
    }

    // ---- (b) full driver via tokio::io::duplex ----

    #[tokio::test]
    async fn driver_full_handshake_no_account_leak() {
        // 預載 synthetic server frames：ACK + managedAccounts(15, 含 DU 帳號) +
        // nextValidId(9) + CURRENT_TIME(49)。
        let ack = encode_frame(b"176\x0020240101 09:30:00 EST\x00");
        let accounts = encode_frame(b"15\x001\x00DU1234567\x00");
        let next_valid = encode_frame(b"9\x001\x0042\x00");
        let current_time = encode_frame(b"49\x001\x001700000000\x00");

        let (client, mut server) = tokio::io::duplex(64 * 1024);
        // 全部預載進 server→client 緩衝（容量足，不會阻塞）。
        let mut preload = Vec::new();
        preload.extend_from_slice(&ack);
        preload.extend_from_slice(&accounts);
        preload.extend_from_slice(&next_valid);
        preload.extend_from_slice(&current_time);
        server.write_all(&preload).await.unwrap();

        let cfg = TwsProbeConfig::g4_default();
        let probe = drive_handshake_and_current_time(client, &cfg).await.unwrap();

        // probe 正確。
        assert_eq!(probe.server_version, 176);
        assert_eq!(probe.connection_time_raw, "20240101 09:30:00 EST");
        assert_eq!(probe.server_epoch_seconds, 1_700_000_000);
        assert_eq!(probe.endpoint_host, "127.0.0.1");
        assert_eq!(probe.endpoint_port, 4002);
        assert_eq!(probe.client_id, 0);

        // 帳號 DU1234567 絕不洩漏到 probe 的 Debug 表示（drop 策略：明文帳號從未進入變量）。
        let dbg = format!("{probe:?}");
        assert!(!dbg.contains("DU1234567"), "account leaked into probe: {dbg}");
        // client 寫出的位元組正確性由 `driver_writes_exact_client_bytes` 單獨覆蓋。
        drop(server);
    }

    #[tokio::test]
    async fn driver_writes_exact_client_bytes() {
        let ack = encode_frame(b"176\x00t\x00");
        let current_time = encode_frame(b"49\x001\x001\x00");

        let (client, mut server) = tokio::io::duplex(64 * 1024);
        let mut preload = Vec::new();
        preload.extend_from_slice(&ack);
        preload.extend_from_slice(&current_time);
        server.write_all(&preload).await.unwrap();

        let cfg = TwsProbeConfig::g4_default();
        let probe = drive_handshake_and_current_time(client, &cfg).await.unwrap();
        assert_eq!(probe.server_epoch_seconds, 1);

        // driver 已完成並 drop client（by-value 消費）；讀 server 端收到的位元組。
        let mut got = Vec::new();
        server.read_to_end(&mut got).await.unwrap();
        let mut expect = Vec::new();
        expect.extend_from_slice(&encode_handshake_prefix(100, 176));
        expect.extend_from_slice(&encode_start_api(0));
        expect.extend_from_slice(&encode_req_current_time());
        assert_eq!(got, expect);
    }

    #[tokio::test]
    async fn driver_rejects_unexpected_msg_id() {
        let ack = encode_frame(b"176\x00t\x00");
        // msgId 8（不在 {49,4,15,9} allowlist）→ UnexpectedMsgId（msgId 4 現已改為 ERR_MSG
        // 分流處理，故用 8 作真正的非預期訊息）。
        let unexpected = encode_frame(b"8\x001\x000\x00");
        let (client, mut server) = tokio::io::duplex(64 * 1024);
        let mut preload = Vec::new();
        preload.extend_from_slice(&ack);
        preload.extend_from_slice(&unexpected);
        server.write_all(&preload).await.unwrap();
        // 亦餵一個 currentTime 使緩衝非空（driver 應在 msgId 8 即 fail）。
        server.write_all(&encode_frame(b"49\x001\x001\x00")).await.unwrap();

        let cfg = TwsProbeConfig::g4_default();
        let err = drive_handshake_and_current_time(client, &cfg).await.unwrap_err();
        assert!(matches!(
            err,
            TwsClientError::Codec(CodecError::UnexpectedMsgId { got: 8 })
        ));
    }

    #[tokio::test]
    async fn driver_tolerates_info_err_msgs() {
        // 真 IB Gateway 序列：ACK → id4(2104 farm OK) → id4(2106 HMDS OK) → CURRENT_TIME。
        // code≥2100 = 連線 info → drain 續讀，最終仍取到 epoch。
        let ack = encode_frame(b"176\x00t\x00");
        let info1 = encode_frame(b"4\x002\x00-1\x002104\x00Market data farm connection is OK:usfarm\x00");
        let info2 = encode_frame(b"4\x002\x00-1\x002106\x00HMDS data farm connection is OK:ushmds\x00");
        let current_time = encode_frame(b"49\x001\x001700000000\x00");

        let (client, mut server) = tokio::io::duplex(64 * 1024);
        let mut preload = Vec::new();
        preload.extend_from_slice(&ack);
        preload.extend_from_slice(&info1);
        preload.extend_from_slice(&info2);
        preload.extend_from_slice(&current_time);
        server.write_all(&preload).await.unwrap();

        let cfg = TwsProbeConfig::g4_default();
        let probe = drive_handshake_and_current_time(client, &cfg).await.unwrap();
        assert_eq!(probe.server_epoch_seconds, 1_700_000_000);
    }

    #[tokio::test]
    async fn driver_fails_on_fatal_err_msg() {
        // code<2100（504 = Not connected）= 真錯誤 → fail-closed GatewayError，不半接觸。
        let ack = encode_frame(b"176\x00t\x00");
        let fatal = encode_frame(b"4\x002\x00-1\x00504\x00Not connected\x00");
        let (client, mut server) = tokio::io::duplex(64 * 1024);
        let mut preload = Vec::new();
        preload.extend_from_slice(&ack);
        preload.extend_from_slice(&fatal);
        server.write_all(&preload).await.unwrap();

        let cfg = TwsProbeConfig::g4_default();
        let err = drive_handshake_and_current_time(client, &cfg).await.unwrap_err();
        assert!(matches!(err, TwsClientError::GatewayError { code: 504 }));
    }

    #[test]
    fn decode_error_code_extracts_index3() {
        assert_eq!(
            decode_error_code(b"4\x002\x00-1\x002104\x00msg\x00").unwrap(),
            2104
        );
        // 欄數不足 → Malformed（不裸索引）。
        assert!(matches!(
            decode_error_code(b"4\x002\x00-1\x00"),
            Err(CodecError::Malformed(_))
        ));
        // code 非數字 → NonNumericField（不捏值）。
        assert_eq!(
            decode_error_code(b"4\x002\x00-1\x00xx\x00msg\x00"),
            Err(CodecError::NonNumericField("error_code"))
        );
    }

    // ---- (c) structural guards ----

    #[test]
    fn endpoint_guard_allows_paper_denies_live_and_nonloopback() {
        assert!(assert_loopback_paper_endpoint("127.0.0.1", 4002).is_ok());
        assert!(assert_loopback_paper_endpoint("127.0.0.1", 4001).is_err()); // live gateway
        assert!(assert_loopback_paper_endpoint("127.0.0.1", 7496).is_err()); // live TWS
        assert!(assert_loopback_paper_endpoint("127.0.0.1", 4003).is_err()); // 非 paper port
        assert!(assert_loopback_paper_endpoint("10.0.0.1", 4002).is_err()); // 非 loopback
        assert!(assert_loopback_paper_endpoint("localhost", 4002).is_err()); // literal IP only
    }

    // ---- G4 approval validity ----

    fn valid_approval(commit: &str, now: u64) -> G4ContactApproval {
        G4ContactApproval {
            adr: IBKR_PHASE2_ADR.to_string(),
            amd: IBKR_PHASE2_CONTACT_AMD.to_string(),
            reviewer_roles: vec!["PM".to_string(), "Operator".to_string()],
            approved_source_commit: commit.to_string(),
            issued_at_ms: now - 1000,
            expires_at_ms: now + 3_600_000,
        }
    }

    #[test]
    fn g4_approval_validity_matrix() {
        let now = 1_800_000_000_000u64;
        let sha = "a".repeat(40);

        assert!(g4_approval_is_valid(&valid_approval(&sha, now), now, &sha));

        // adr 錯。
        let mut a = valid_approval(&sha, now);
        a.adr = "ADR-9999".to_string();
        assert!(!g4_approval_is_valid(&a, now, &sha));

        // amd 錯（用 shape-AMD 冒充 contact-AMD）。
        let mut a = valid_approval(&sha, now);
        a.amd = "AMD-2026-06-29-01".to_string();
        assert!(!g4_approval_is_valid(&a, now, &sha));

        // commit 不符。
        let a = valid_approval(&"b".repeat(40), now);
        assert!(!g4_approval_is_valid(&a, now, &sha));

        // commit == "unknown" → anti-replay 拒。
        let a = valid_approval("unknown", now);
        assert!(!g4_approval_is_valid(&a, now, "unknown"));

        // 缺 Operator。
        let mut a = valid_approval(&sha, now);
        a.reviewer_roles = vec!["PM".to_string()];
        assert!(!g4_approval_is_valid(&a, now, &sha));

        // 缺 PM（忠實鏡像 P2 要求 PM 且 Operator，E2 RETURN #2）。
        let mut a = valid_approval(&sha, now);
        a.reviewer_roles = vec!["Operator".to_string()];
        assert!(!g4_approval_is_valid(&a, now, &sha));

        // 已過期。
        let mut a = valid_approval(&sha, now);
        a.expires_at_ms = now - 1;
        assert!(!g4_approval_is_valid(&a, now, &sha));

        // 超齡（issued 早於 now-30d）。
        let mut a = valid_approval(&sha, now);
        a.issued_at_ms = now - G4_MAX_APPROVAL_AGE_MS - 1;
        a.expires_at_ms = now + 3_600_000;
        assert!(!g4_approval_is_valid(&a, now, &sha));

        // future-dated（issued>now）→ 判無效不 fail-open。
        let mut a = valid_approval(&sha, now);
        a.issued_at_ms = now + 1000;
        assert!(!g4_approval_is_valid(&a, now, &sha));
    }

    // ---- G4 approval reader（owner-only；#[cfg(unix)]）----

    #[cfg(unix)]
    fn make_gov_chain(root: &Path) -> PathBuf {
        use std::os::unix::fs::PermissionsExt;
        let gov = root.join("governance");
        let ibkr = gov.join("ibkr_phase2");
        std::fs::create_dir_all(&ibkr).unwrap();
        std::fs::set_permissions(&gov, std::fs::Permissions::from_mode(0o700)).unwrap();
        std::fs::set_permissions(&ibkr, std::fs::Permissions::from_mode(0o700)).unwrap();
        ibkr
    }

    #[cfg(unix)]
    fn write_approval_file(dir: &Path, mode: u32) -> PathBuf {
        use std::os::unix::fs::PermissionsExt;
        let path = dir.join(G4_APPROVAL_FILENAME);
        let toml = r#"
adr = "ADR-0048"
amd = "AMD-2026-07-08-01"
reviewer_roles = ["PM", "Operator"]
approved_source_commit = "abc123"
issued_at_ms = 1800000000000
expires_at_ms = 1800003600000
"#;
        std::fs::write(&path, toml).unwrap();
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(mode)).unwrap();
        path
    }

    #[cfg(unix)]
    #[test]
    fn g4_reader_absent_returns_none() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        assert_eq!(load_g4_contact_approval_from_dir(&gov).unwrap(), None);
    }

    #[cfg(unix)]
    #[test]
    fn g4_reader_valid_roundtrip() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        write_approval_file(&gov, 0o600);
        let got = load_g4_contact_approval_from_dir(&gov).unwrap().unwrap();
        assert_eq!(got.adr, "ADR-0048");
        assert_eq!(got.amd, "AMD-2026-07-08-01");
        assert!(got.reviewer_roles.iter().any(|r| r == "Operator"));
        assert_eq!(got.approved_source_commit, "abc123");
    }

    #[cfg(unix)]
    #[test]
    fn g4_reader_rejects_wide_perms() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        write_approval_file(&gov, 0o644); // 過寬 → Err。
        assert!(load_g4_contact_approval_from_dir(&gov).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn g4_reader_rejects_symlink() {
        use std::os::unix::fs::PermissionsExt;
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        // 真檔在別處，gov 內放一個指向它的 symlink。
        let target = tmp.path().join("real_approval.toml");
        std::fs::write(&target, "adr = \"ADR-0048\"\n").unwrap();
        std::fs::set_permissions(&target, std::fs::Permissions::from_mode(0o600)).unwrap();
        std::os::unix::fs::symlink(&target, gov.join(G4_APPROVAL_FILENAME)).unwrap();
        assert!(load_g4_contact_approval_from_dir(&gov).is_err());
    }

    // ---- 惰性 gate（env-mutating；共用 crate 測試鎖）----

    #[cfg(unix)]
    #[test]
    fn gate_false_when_env_unset_or_sealed_absent() {
        let _guard = crate::test_env_lock::guard();

        // env 未設 → g4_contact_approval_present false。
        std::env::remove_var("OPENCLAW_DATA_DIR");
        assert!(!g4_contact_approval_present());

        // env 設 tempdir + 合法 approval，但無 sealed pass artifact →
        // phase2_first_contact_gate_ok 仍 false（sealed 這一半不成立）。
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        write_approval_file(&gov, 0o600);
        std::env::set_var("OPENCLAW_DATA_DIR", tmp.path());
        // approval 檔存在且權限合法（reader 不報 Err），但世代 commit=abc123 未必 ==
        // BUILD_GIT_SHA，故 approval valid 與否不確定；無論如何 sealed absent →
        // 整閘必 false。
        assert!(!phase2_first_contact_gate_ok());

        std::env::remove_var("OPENCLAW_DATA_DIR");
    }

    // ---- 源級守衛：本檔絕不含下單 / HTTP / Bybit 符號 ----
    // needle 以 concat! 於編譯期組裝，令 verbatim token 不出現在本檔源碼，避免 include_str!
    // 自我命中。

    #[test]
    fn source_has_no_forbidden_symbols() {
        let src = include_str!("ibkr_readonly_tws_client.rs");
        let forbidden = [
            concat!("place", "_order"),
            concat!("cancel", "_order"),
            concat!("submit", "_order"),
            concat!("amend", "_order"),
            concat!("req", "west"),
            concat!("by", "bit"),
        ];
        for needle in forbidden {
            assert!(!src.contains(needle), "forbidden source token present: {needle}");
        }
    }
}
