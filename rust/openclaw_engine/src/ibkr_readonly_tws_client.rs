//! MODULE_NOTE
//! 模塊用途：IBKR **B1 只讀 TWS 連接器**（ADR-0048 / AMD-2026-07-08-01，G4 首次接觸）。
//!   只做 connect handshake + `reqCurrentTime`（=server-time / health 最小首接觸），零
//!   新治理契約。**build now / run=G4**（惰性；default build 不 auto-run、無 production
//!   caller、不接 socket）。B2/B3（account / positions / market-data）不在本 phase。
//! 主要區段（單檔 4 段）：
//!   - (a) 純 codec：`encode_frame` / `try_decode_frame` / `encode_fields` /
//!     `decode_fields` / `encode_handshake_prefix` / `encode_start_api` /
//!     `encode_req_current_time` / `decode_server_handshake_ack` /
//!     `decode_current_time` / `managed_accounts_all_paper`（無 I/O，synthetic
//!     fixture 可測）。
//!   - (b) generic driver：`drive_handshake_and_current_time<S>`（pub(crate)，泛型於
//!     `AsyncRead + AsyncWrite + Unpin`，不自持 socket；由 duplex / TcpStream 注入）。
//!   - (c) structural guards：`assert_loopback_paper_endpoint`（literal `127.0.0.1` +
//!     paper port 4002 only；4001 / 7496 硬拒），無 config 拓寬面。
//!   - (d) gated G4 entry：`g4_operator_triggered_first_contact`
//!     （`#[cfg(feature="ibkr_g4_contact")]`，唯一具體 `TcpStream::connect`）。
//!   - (e) EA3 envelope 活化閘：`ea3_envelope_activation_gate`（R16 mini-wiring;
//!     IB-NOTE-1）——G4 entry 於全部既有 gate 之後、唯一 socket 接觸之前消費 W8a
//!     驗證器 `check_readonly_contact`（nonce 原子消費）;envelope + 當前兩 epoch 均為
//!     owner-only 治理 artifact（非 0o400/0o600 拒,沿 seal 慣例）。
//! 依賴：`tokio`（io traits + net + time）、`openclaw_types`（port / AMD / ADR 常量 +
//!   `IbkrActivationEnvelopeV1` / `BrokerOperation`）、`boot_observability::BUILD_GIT_SHA`
//!   （G4 approval anti-replay + envelope build 綁定）、`sha2` 不需要（帳號採 drop 策略）、
//!   `toml` / `serde`（G4 approval / epoch 現值讀取）、`serde_json`（envelope artifact）、
//!   `ibkr_activation_envelope_check`（W8a 活化裁決唯一入口）。
//! 硬邊界（絕不鬆動）：
//!   - **只讀**：源級不存在任何下單 / 撤單 / 改單方法（single write entry §1）；
//!     不接 IPC / dispatch / normalizer（P4）；不 auto-run；無 production caller。
//!   - **loopback + paper-port only**：connect 目標硬編 literal `127.0.0.1:4002`；live
//!     port（4001 / 7496）與非 loopback host 結構性拒，無 config 拓寬。
//!   - **不洩帳號（prefix-only inspect then drop）**：握手中 gateway push
//!     `managedAccounts`（msgId 15，含 paper `DU…`）——payload tokenize 後僅做
//!     **前綴實檢**（每個帳號 token 必須 `DU` 開頭 = paper session），實檢只導出
//!     boolean，明文帳號從不 bind 具名變量、從不 log / serialize / 進錯誤訊息，
//!     檢畢即整體丟棄（保持「hash-or-drop」drop 側的保守性）。任一非 `DU` 帳號 →
//!     `NonPaperSessionDetected`；直到 49 都未見 15 → `PaperSessionUnverified`
//!     （fail-closed，不以「沒看到」當「已驗證」）。
//!   - **untrusted-wire fail-closed**：length 讀 u32 BE（無負）；任何分配前比
//!     `<= MAX_FRAME_LEN`；欄位 tokenizer 嚴限 frame slice 內，越界 / 非數字 / 非 ASCII /
//!     缺終止 → typed `CodecError`，零 unwrap / expect / panic / 裸索引 on parsed data，
//!     無捏造值（禁 `unwrap_or(0)`）；msgId 處理（ack + 49 done + 15 paper 前綴實檢 +
//!     9 ignored + 4 ERR_MSG 按 code 分流 / 其餘 UnexpectedMsgId）。
//!   - **惰性 G4 gate（任何 socket syscall 之前）**：env `OPENCLAW_IBKR_G4_CONTACT_APPLY==
//!     "1"` literal → `phase2_immutable_pass_artifact_present()`（真磁盤 re-verify，直接調
//!     producer）→ G4 approval 6 綁定 valid → structural host/port → **EA3 activation
//!     envelope 閘（R16;活化鐵律 §2）**：owner-only 載入 envelope + 當前兩 epoch →
//!     `check_readonly_contact`（build SHA/epoch 綁定比對 + nonce 原子消費;非 accepted
//!     = typed reject）→ 才 connect。**加閘只收緊,任何既有 gate 全保留**;envelope 閘放
//!     最後一道=任何前置 gate 失敗都不燒 nonce（拒絕不燒授權）。
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
    BrokerOperation, IbkrActivationEnvelopeV1, IBKR_LIVE_GATEWAY_PORT, IBKR_LIVE_TWS_PORT,
    IBKR_PAPER_GATEWAY_DEFAULT_PORT, IBKR_PHASE2_ADR, IBKR_PHASE2_CONTACT_AMD, IB_INFO_CODE_FLOOR,
};

use crate::boot_observability::BUILD_GIT_SHA;
// R16 EA3 mini-wiring:W8a 活化裁決唯一入口 + 姿態/帳本型別（IB-NOTE-1;本檔為其
// 首個 production 消費面,feature-gated——default build 仍零 caller/DCE）。
use crate::ibkr_activation_envelope_check::{
    check_readonly_contact, ActivationCheckPosture, ActivationNonceLedger,
};
// W3-S1:純 codec §(a) 已抽至 `ibkr_tws_wire`（本檔改就地消費,語義零變;codec 自此有兩個
// 消費者=B1 driver + W3 session manager)。glob 匯入 codec 原語 / CodecError / HandshakeAck /
// 版本 + msgId 常量,令 driver 與既有 26 測試（`use super::*`)零改仍解析。
use crate::ibkr_tws_wire::*;

// ---------------------------------------------------------------------------
// 常量（W3-S1 後:codec 域常量=MAX_FRAME_LEN / HANDSHAKE_PREFIX / CLIENT_{MIN,MAX}_VERSION /
// msgId 常量已遷至 `ibkr_tws_wire`;`IB_INFO_CODE_FLOOR`（≥2100 地板)遷至 openclaw_types
// 單處維護。本檔僅留 driver / gate / guard 域常量)
// ---------------------------------------------------------------------------

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
// (a) 純 codec — **已抽至 `crate::ibkr_tws_wire`**（W3-S1;語義零變）
// ---------------------------------------------------------------------------
// `CodecError` / `HandshakeAck` / `encode_frame` / `try_decode_frame` /
// `encode_fields` / `decode_fields` / `encode_handshake_prefix` /
// `encode_start_api` / `encode_req_current_time` / `frame_msg_id` /
// `decode_server_handshake_ack` / `decode_current_time` / `decode_error_code` /
// `managed_accounts_all_paper` 及 codec 域常量現由檔首 `use crate::ibkr_tws_wire::*`
// 就地匯入。動機:B1 檔逼近 2000 行拆檔守衛,且 codec 自此有兩個消費者（B1 G4 探針 +
// W3 session manager),deletion test 過。下方 driver / guards / G4 gate 原樣凍結。
// ===========================================================================

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
    /// managedAccounts(15) 前綴實檢發現任一非 `DU` 帳號 = 非 paper session →
    /// 立即 fail-closed（錯誤訊息刻意不含任何帳號明文）。
    #[error("non-paper session detected (managedAccounts contains non-DU account)")]
    NonPaperSessionDetected,
    /// 直到 CURRENT_TIME(49) 都未收到 managedAccounts(15)，paper session 無從實檢 →
    /// fail-closed（真 IB Gateway 於 startApi 後、49 前必推 15/9；異序只 false-fail
    /// 可重試，不 fail-open）。
    #[error("paper session unverified (no managedAccounts before current_time)")]
    PaperSessionUnverified,
    #[error("endpoint denied: {0}")]
    EndpointDenied(String),
    /// env `OPENCLAW_IBKR_G4_CONTACT_APPLY` 非 literal "1"（dry-run 預設）。
    #[error("g4 contact not applied (OPENCLAW_IBKR_G4_CONTACT_APPLY != \"1\")")]
    ContactNotApplied,
    /// sealed pass artifact 或 G4 approval 缺席 / 無效（fail-closed）。
    #[error("g4 first-contact gate blocked (sealed artifact or contact approval missing/invalid)")]
    GateBlocked,
    /// EA3 activation artifact 載入失敗（壞 JSON/TOML、symlink、權限過寬、非本人所有、
    /// envelope 在位而 epoch 現值缺席等）。為什麼 typed 不 panic:授權面任何不可證狀態
    /// 都必須是可觀測的拒絕,而非進程崩潰。envelope **檔缺席**不走此變體——交由驗證器
    /// 產 `EnvelopeAbsent`（保住 seal≠活化機器證明路徑）。
    #[error("ea3 activation artifact unavailable: {0}")]
    EnvelopeUnavailable(String),
    /// EA3 活化裁決非 accepted（blocker 全列於 Debug 投影;deny path 不燒 nonce）。
    #[error("ea3 activation rejected: {blockers}")]
    ActivationRejected { blockers: String },
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
/// msgId 處理（讀 currentTime 迴圈內）：49（done，但須已 paper_confirmed）/ 15
/// （managedAccounts，**paper 前綴實檢**：全 `DU` → paper_confirmed=true 續讀；任一非
/// `DU` → 立即 `NonPaperSessionDetected`；明文帳號 prefix-only inspect then drop，從不
/// bind/log/serialize）/ 9（nextValidId，ignored）/ 4（ERR_MSG：code≥2100 = 連線
/// info/warning → 續讀；code<2100 = 真錯誤 → fail-closed `GatewayError`）；其餘 →
/// `UnexpectedMsgId`。真 IB Gateway 必在 49 之前推 id-4 通知，故必須容忍（E2 RETURN
/// #1）；同時序記錄證明 startApi 後、49 前必推 15/9 → 49 時若仍未見 15 →
/// `PaperSessionUnverified`（異序只 false-fail 可重試，不 fail-open）。
/// read-budget/timeout 仍為終止上界。
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

    // 4) 讀到 CURRENT_TIME(49)；握手 push 的 15 做 paper 前綴實檢，9 ignored，
    //    4（ERR_MSG）按 code 分流。
    let mut paper_confirmed = false;
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
                // managedAccounts：由盲 drop 改為強制實檢（prefix-only inspect then drop）——
                // 全帳號 `DU` 前綴 = paper session → 記 paper_confirmed 續讀；任一非 `DU` →
                // 立即 fail-closed，絕不對 live session 繼續任何讀取。明文帳號僅在
                // `managed_accounts_all_paper` 內短暫 tokenize，只導出 boolean，從不
                // bind 具名變量 / log / serialize（維持 drop 側保守性）。
                if !managed_accounts_all_paper(&payload)? {
                    return Err(TwsClientError::NonPaperSessionDetected);
                }
                paper_confirmed = true;
                continue;
            }
            NEXT_VALID_ID_MSG_ID => continue,
            other => return Err(TwsClientError::Codec(CodecError::UnexpectedMsgId { got: other })),
        }
    };

    // 真 IB Gateway 於 startApi 後、CURRENT_TIME(49) 前必推 15/9（同檔 E2 RETURN #1 的
    // 時序記錄同構）——若直到 49 都未見 15，paper session 無從實檢 → fail-closed。
    // 異序（先 49 後 15）只會 false-fail，可重試；絕不 fail-open。
    if !paper_confirmed {
        return Err(TwsClientError::PaperSessionUnverified);
    }

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
/// 綁定 valid → structural host/port const → **EA3 activation envelope 閘**
/// （`ea3_envelope_activation_gate`,nonce 原子消費——R16 起真接觸必經 Rust 驗證的
/// envelope,活化鐵律 §2）→ 才 connect。
///
/// G4 為 one-shot：connect → handshake → 1×currentTime → close（stream drop）。無
/// production caller（僅 G4 bin 於 operator 顯式 `--contact` + env 觸發）。**單次入口
/// 呼叫=活化時刻**（驗證器移交契約）:同進程二次呼叫必 `NonceAlreadyConsumed`;
/// reconnect/scope 變更=換新 envelope（新 nonce）。
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

    // Gate 5（R16 EA3 mini-wiring;IB-NOTE-1）：activation envelope 消費。刻意放在全部
    // 既有 gate 之後、connect 之前:任何前置 gate 失敗都不燒 nonce,通過本閘即為
    // 「活化時刻」,緊接唯一 socket 接觸。G4 首讀嚴格對齊 health/serverTime 讀集 →
    // operation verb 固定 `HealthRead`;seal 在位事實直取唯一 production seal 消費點
    // （驗證器 MODULE_NOTE 移交契約,禁第二套 seal 讀取語義）。
    let gov_dir = resolve_g4_governance_dir().ok_or_else(|| {
        TwsClientError::EnvelopeUnavailable("OPENCLAW_DATA_DIR unset/empty".to_string())
    })?;
    ea3_envelope_activation_gate(
        &gov_dir,
        BrokerOperation::HealthRead,
        BUILD_GIT_SHA,
        crate::ibkr_phase2_gate_producer::phase2_immutable_pass_artifact_present(),
        now_ms(),
        g4_activation_nonce_ledger(),
    )?;

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
// (e) EA3 envelope 活化閘（R16 mini-wiring;IB-NOTE-1;活化鐵律 §2 的 G4 消費面）
// ===========================================================================

/// envelope artifact 檔名（owner-only;與 G4 approval 同治理目錄
/// `<OPENCLAW_DATA_DIR>/governance/ibkr_phase2`——**config/固定路徑,非 env-var 憑證
/// fallback 語義**:envelope 非憑證但同紀律,路徑來源與 G4 approval 完全同級,由 EA3
/// authenticated Operator 活化紀錄提供本檔）。
const ACTIVATION_ENVELOPE_FILENAME: &str = "ibkr_activation_envelope_v1.json";

/// 當前兩 epoch（revocation/kill-switch）現值檔名。engine 目前無 runtime epoch 來源
/// （W8 前）→ 過渡採 G4 approval 同級 config 注入;EA3 活化紀錄與 envelope 同批提供
/// 本檔,operator 撤銷/kill = bump 檔內 epoch 使既發 envelope 綁定失配即拒。
const ACTIVATION_CURRENT_EPOCHS_FILENAME: &str = "ibkr_activation_current_epochs.toml";

/// 當前 epoch 現值（TOML deser）。**只承載現值**,絕不從 envelope 自帶值推導——
/// 「envelope 綁定值 vs 現值」比對若同源即恆等,撤銷機制形同虛設。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
pub(crate) struct ActivationCurrentEpochs {
    pub revocation_epoch: u64,
    pub kill_switch_epoch: u64,
}

/// owner-only 治理 artifact 讀取（EA3 面共用;沿 seal/approval 慣例）。
/// 缺檔 → `Ok(None)`;symlink / 非 regular file / 模式非 {0o400,0o600} / 非本人所有 /
/// 祖先鏈非 0o700 → `Err`（fail-closed）。為什麼收 0o400:sealed artifact 慣例為
/// write-once 0o400,EA3 活化紀錄歸檔後可比照鎖唯讀。
#[cfg(unix)]
fn load_owner_only_artifact_text(gov_dir: &Path, filename: &str) -> Result<Option<String>, String> {
    use std::os::unix::fs::{MetadataExt, PermissionsExt};

    let path = gov_dir.join(filename);
    let meta = match std::fs::symlink_metadata(&path) {
        Ok(m) => m,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(e) => return Err(format!("ea3 artifact stat {} failed: {e}", path.display())),
    };
    // 綁定：檔本身不得為 symlink（lstat 不跟隨）。
    if meta.file_type().is_symlink() {
        return Err(format!(
            "ea3 artifact is symlink (denied): {}",
            path.display()
        ));
    }
    if !meta.is_file() {
        return Err(format!(
            "ea3 artifact is not a regular file: {}",
            path.display()
        ));
    }
    let mode = meta.permissions().mode() & 0o777;
    if mode != 0o600 && mode != 0o400 {
        return Err(format!(
            "ea3 artifact not owner-only 0o400/0o600: {} mode={mode:#o}",
            path.display()
        ));
    }
    let euid = unsafe { libc::geteuid() } as u32;
    if meta.uid() as u32 != euid {
        return Err(format!(
            "ea3 artifact not owned by euid: {}",
            path.display()
        ));
    }
    // 綁定：0o700 祖先鏈（與 G4 approval 共用同一檢查）。
    g4_check_dir_pair_owner_only(gov_dir)?;

    std::fs::read_to_string(&path)
        .map(Some)
        .map_err(|e| format!("read ea3 artifact {} failed: {e}", path.display()))
}

/// 非 unix：無法驗權限 / owner → 結構性 fail-closed 視為缺檔（部署目標皆 unix）。
#[cfg(not(unix))]
fn load_owner_only_artifact_text(gov_dir: &Path, filename: &str) -> Result<Option<String>, String> {
    let _ = (gov_dir, filename);
    Ok(None)
}

/// envelope artifact 載入（serde_json → `IbkrActivationEnvelopeV1`）。缺檔 → `Ok(None)`
/// （交由驗證器產 `EnvelopeAbsent`）;壞 JSON / 權限違規 → `Err`。
fn load_activation_envelope_from_dir(
    gov_dir: &Path,
) -> Result<Option<IbkrActivationEnvelopeV1>, String> {
    let raw = match load_owner_only_artifact_text(gov_dir, ACTIVATION_ENVELOPE_FILENAME)? {
        Some(raw) => raw,
        None => return Ok(None),
    };
    serde_json::from_str::<IbkrActivationEnvelopeV1>(&raw)
        .map(Some)
        .map_err(|e| format!("parse ea3 envelope {ACTIVATION_ENVELOPE_FILENAME} failed: {e}"))
}

/// 當前兩 epoch 現值載入（toml）。缺檔 → `Ok(None)`（是否致拒由 gate 依 envelope 在位
/// 與否決定）;壞 TOML / 權限違規 → `Err`。
fn load_activation_current_epochs_from_dir(
    gov_dir: &Path,
) -> Result<Option<ActivationCurrentEpochs>, String> {
    let raw = match load_owner_only_artifact_text(gov_dir, ACTIVATION_CURRENT_EPOCHS_FILENAME)? {
        Some(raw) => raw,
        None => return Ok(None),
    };
    toml::from_str::<ActivationCurrentEpochs>(&raw)
        .map(Some)
        .map_err(|e| format!("parse ea3 epochs {ACTIVATION_CURRENT_EPOCHS_FILENAME} failed: {e}"))
}

/// **EA3 envelope 活化閘**:G4 entry 在既有 gate 鏈之後、任何 socket 接觸之前的最後
/// 一道授權裁決（活化鐵律 §2:真接觸必經 Rust 驗證 envelope + 原子燒 nonce）。
///
/// 流程（先寫拒絕路徑）:
/// 1. owner-only 載 envelope（權限/壞 JSON → `EnvelopeUnavailable`;**缺檔=None 續走**,
///    交由驗證器產 `EnvelopeAbsent`——保住「seal 在位而 envelope 缺席 →
///    `SealIsNotActivationAuthority`」機器證明路徑）。
/// 2. owner-only 載當前兩 epoch 現值;envelope 在位而現值缺 → 無從比對 = fail-closed
///    `EnvelopeUnavailable`（絕不以 envelope 自帶綁定值充當現值）。兩者皆缺時取 0 佔位
///    ——驗證器 envelope-absent 分支提前拒,佔位值不參與任何放行判定。
/// 3. 構造 `ActivationCheckPosture` → `check_readonly_contact`（shape/綁定/時窗/verb
///    白名單全過才原子消費 nonce）;非 accepted → `ActivationRejected`（deny 不燒 nonce）。
///
/// `phase2_seal_present` 由呼叫端供給且**只能**取自
/// `phase2_immutable_pass_artifact_present()`（驗證器 MODULE_NOTE 移交契約——本函數
/// 不自讀 seal,禁第二套 seal 讀取語義;參數化同時使測試無需 env/seal fixture）。
fn ea3_envelope_activation_gate(
    gov_dir: &Path,
    operation: BrokerOperation,
    current_build_git_sha: &str,
    phase2_seal_present: bool,
    now_ms_value: u64,
    ledger: &ActivationNonceLedger,
) -> Result<(), TwsClientError> {
    let envelope =
        load_activation_envelope_from_dir(gov_dir).map_err(TwsClientError::EnvelopeUnavailable)?;
    let epochs = load_activation_current_epochs_from_dir(gov_dir)
        .map_err(TwsClientError::EnvelopeUnavailable)?;

    let (current_revocation_epoch, current_kill_switch_epoch) = match (&envelope, &epochs) {
        (_, Some(e)) => (e.revocation_epoch, e.kill_switch_epoch),
        // envelope 在位而 epoch 現值缺席:無從證明未被撤銷/kill → fail-closed 拒。
        (Some(_), None) => {
            return Err(TwsClientError::EnvelopeUnavailable(format!(
                "current epochs artifact absent ({ACTIVATION_CURRENT_EPOCHS_FILENAME}); \
                 cannot prove envelope not revoked/killed"
            )));
        }
        // 兩者皆缺:0 佔位——驗證器於 envelope-absent 分支提前拒,佔位值不被讀取比對。
        (None, None) => (0, 0),
    };

    let posture = ActivationCheckPosture {
        now_ms: now_ms_value,
        current_build_git_sha: current_build_git_sha.to_string(),
        current_revocation_epoch,
        current_kill_switch_epoch,
        phase2_seal_present,
    };
    let verdict = check_readonly_contact(envelope.as_ref(), operation, &posture, ledger);
    if !verdict.activation_accepted {
        return Err(TwsClientError::ActivationRejected {
            blockers: format!("{:?}", verdict.blockers),
        });
    }
    Ok(())
}

/// process-global activation nonce 帳本（僅 gated G4 entry 消費;default build 不編譯）。
///
/// 為什麼 process-global:驗證器移交契約規定「單次入口呼叫=活化時刻」——若每次呼叫
/// 建新帳本,同進程二次呼叫將繞過 `NonceAlreadyConsumed`,replay 防護即失效。in-memory
/// 易失（CC-NOTE-1）:進程重啟遺忘已消費 nonce（重啟=重新活化語義,舊 envelope 仍受
/// expiry/epoch 綁定約束）;durable 消費紀錄歸 W8 吸收。
#[cfg(feature = "ibkr_g4_contact")]
fn g4_activation_nonce_ledger() -> &'static ActivationNonceLedger {
    static LEDGER: std::sync::OnceLock<ActivationNonceLedger> = std::sync::OnceLock::new();
    LEDGER.get_or_init(ActivationNonceLedger::new)
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
            // 全部解析入口全部餵；任何 panic 都會令測試失敗。
            let _ = try_decode_frame(&bytes);
            let _ = decode_fields(&bytes);
            let _ = decode_server_handshake_ack(&bytes);
            let _ = decode_current_time(&bytes);
            let _ = frame_msg_id(&bytes);
            let _ = managed_accounts_all_paper(&bytes);
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
        // paper 實檢後 49 前必須有 15（否則 PaperSessionUnverified）。
        let accounts = encode_frame(b"15\x001\x00DU1\x00");
        let current_time = encode_frame(b"49\x001\x001\x00");

        let (client, mut server) = tokio::io::duplex(64 * 1024);
        let mut preload = Vec::new();
        preload.extend_from_slice(&ack);
        preload.extend_from_slice(&accounts);
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
        // 真 IB Gateway 序列：ACK → 15(managedAccounts) → id4(2104 farm OK) →
        // id4(2106 HMDS OK) → CURRENT_TIME。code≥2100 = 連線 info → drain 續讀，
        // 最終仍取到 epoch（15 為 paper 實檢所需）。
        let ack = encode_frame(b"176\x00t\x00");
        let accounts = encode_frame(b"15\x001\x00DU1234567\x00");
        let info1 = encode_frame(b"4\x002\x00-1\x002104\x00Market data farm connection is OK:usfarm\x00");
        let info2 = encode_frame(b"4\x002\x00-1\x002106\x00HMDS data farm connection is OK:ushmds\x00");
        let current_time = encode_frame(b"49\x001\x001700000000\x00");

        let (client, mut server) = tokio::io::duplex(64 * 1024);
        let mut preload = Vec::new();
        preload.extend_from_slice(&ack);
        preload.extend_from_slice(&accounts);
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

    #[tokio::test]
    async fn driver_rejects_non_paper_account() {
        // 非 DU 帳號（live 前綴 U…）→ 立即 NonPaperSessionDetected，不讀到 49。
        let ack = encode_frame(b"176\x00t\x00");
        let accounts = encode_frame(b"15\x001\x00U1234567\x00");
        let current_time = encode_frame(b"49\x001\x001\x00");
        let (client, mut server) = tokio::io::duplex(64 * 1024);
        let mut preload = Vec::new();
        preload.extend_from_slice(&ack);
        preload.extend_from_slice(&accounts);
        preload.extend_from_slice(&current_time);
        server.write_all(&preload).await.unwrap();

        let cfg = TwsProbeConfig::g4_default();
        let err = drive_handshake_and_current_time(client, &cfg)
            .await
            .unwrap_err();
        assert!(matches!(err, TwsClientError::NonPaperSessionDetected));
        // 錯誤的 Debug/Display 表示絕不含帳號明文。
        let s = format!("{err:?} {err}");
        assert!(!s.contains("U1234567"), "account leaked into error: {s}");
    }

    #[tokio::test]
    async fn driver_rejects_mixed_paper_and_live_accounts() {
        // 混合 DU1,U2 → 同拒（任一非 DU 即非 paper session）。
        let ack = encode_frame(b"176\x00t\x00");
        let accounts = encode_frame(b"15\x001\x00DU1,U2\x00");
        let (client, mut server) = tokio::io::duplex(64 * 1024);
        let mut preload = Vec::new();
        preload.extend_from_slice(&ack);
        preload.extend_from_slice(&accounts);
        server.write_all(&preload).await.unwrap();

        let cfg = TwsProbeConfig::g4_default();
        let err = drive_handshake_and_current_time(client, &cfg)
            .await
            .unwrap_err();
        assert!(matches!(err, TwsClientError::NonPaperSessionDetected));
    }

    #[tokio::test]
    async fn driver_requires_managed_accounts_before_current_time() {
        // 缺 15 直達 49 → PaperSessionUnverified（fail-closed；異序只 false-fail 可重試）。
        let ack = encode_frame(b"176\x00t\x00");
        let current_time = encode_frame(b"49\x001\x001700000000\x00");
        let (client, mut server) = tokio::io::duplex(64 * 1024);
        let mut preload = Vec::new();
        preload.extend_from_slice(&ack);
        preload.extend_from_slice(&current_time);
        server.write_all(&preload).await.unwrap();

        let cfg = TwsProbeConfig::g4_default();
        let err = drive_handshake_and_current_time(client, &cfg)
            .await
            .unwrap_err();
        assert!(matches!(err, TwsClientError::PaperSessionUnverified));
    }

    #[test]
    fn managed_accounts_paper_prefix_check() {
        // 全 DU（單帳號 / 多帳號 CSV）→ true。
        assert_eq!(
            managed_accounts_all_paper(b"15\x001\x00DU1234567\x00"),
            Ok(true)
        );
        assert_eq!(
            managed_accounts_all_paper(b"15\x001\x00DU1,DU2,DU3\x00"),
            Ok(true)
        );
        // 任一非 DU → false（live 帳號前綴 U…）。
        assert_eq!(
            managed_accounts_all_paper(b"15\x001\x00U1234567\x00"),
            Ok(false)
        );
        assert_eq!(
            managed_accounts_all_paper(b"15\x001\x00DU1,U2\x00"),
            Ok(false)
        );
        // 空帳號欄 = 空列表 → Malformed（不以空欄當已驗證）。
        assert!(matches!(
            managed_accounts_all_paper(b"15\x001\x00\x00"),
            Err(CodecError::Malformed(_))
        ));
        // 欄數不足 → Malformed（不裸索引）。
        assert!(matches!(
            managed_accounts_all_paper(b"15\x001\x00"),
            Err(CodecError::Malformed(_))
        ));
        // msgId 非 15 → UnexpectedMsgId（純 codec 層自帶 msgId 防呆）。
        assert_eq!(
            managed_accounts_all_paper(b"9\x001\x00DU1\x00"),
            Err(CodecError::UnexpectedMsgId { got: 9 })
        );
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

    // ---- (e) EA3 envelope 活化閘（gov_dir 注入,零 env 依賴;權限面 #[cfg(unix)]）----

    /// fixture 有效窗內的注入時刻（issued + 10min;同驗證器測試——固定 epoch ms 常量
    /// 相對取值,非牆鐘/非 time-bomb）。
    const EA3_NOW_IN_WINDOW_MS: u64 = 1_772_232_600_000;

    /// 與 `readonly_fixture` build 綁定相符的注入 build SHA（fixture 域,非真 SHA）。
    fn ea3_fixture_sha() -> String {
        "f".repeat(40)
    }

    #[cfg(unix)]
    fn write_ea3_envelope_file(dir: &Path, envelope: &IbkrActivationEnvelopeV1, mode: u32) {
        use std::os::unix::fs::PermissionsExt;
        let path = dir.join(ACTIVATION_ENVELOPE_FILENAME);
        std::fs::write(&path, serde_json::to_string(envelope).unwrap()).unwrap();
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(mode)).unwrap();
    }

    #[cfg(unix)]
    fn write_ea3_epochs_file(dir: &Path, revocation: u64, kill: u64, mode: u32) {
        use std::os::unix::fs::PermissionsExt;
        let path = dir.join(ACTIVATION_CURRENT_EPOCHS_FILENAME);
        let toml = format!("revocation_epoch = {revocation}\nkill_switch_epoch = {kill}\n");
        std::fs::write(&path, toml).unwrap();
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(mode)).unwrap();
    }

    /// 全鏈 accept + 同 ledger 二次消費必拒（replay;移交契約:單次入口=活化時刻）。
    #[cfg(unix)]
    #[test]
    fn ea3_gate_accepts_fixture_envelope_then_denies_replay() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        write_ea3_envelope_file(&gov, &IbkrActivationEnvelopeV1::readonly_fixture(), 0o600);
        write_ea3_epochs_file(&gov, 1, 1, 0o600);
        let ledger = ActivationNonceLedger::new();

        let first = ea3_envelope_activation_gate(
            &gov,
            BrokerOperation::HealthRead,
            &ea3_fixture_sha(),
            false,
            EA3_NOW_IN_WINDOW_MS,
            &ledger,
        );
        assert!(first.is_ok(), "expected accept, got {first:?}");

        // 同進程二次呼叫 = replay → NonceAlreadyConsumed。
        let replay = ea3_envelope_activation_gate(
            &gov,
            BrokerOperation::HealthRead,
            &ea3_fixture_sha(),
            false,
            EA3_NOW_IN_WINDOW_MS,
            &ledger,
        )
        .unwrap_err();
        match replay {
            TwsClientError::ActivationRejected { blockers } => {
                assert!(blockers.contains("NonceAlreadyConsumed"), "{blockers}");
            }
            other => panic!("expected ActivationRejected, got {other:?}"),
        }
    }

    /// sealed artifact 慣例的 0o400 唯讀模式同為合法 owner-only。
    #[cfg(unix)]
    #[test]
    fn ea3_gate_accepts_readonly_0400_artifacts() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        write_ea3_envelope_file(&gov, &IbkrActivationEnvelopeV1::readonly_fixture(), 0o400);
        write_ea3_epochs_file(&gov, 1, 1, 0o400);
        let ledger = ActivationNonceLedger::new();

        let verdict = ea3_envelope_activation_gate(
            &gov,
            BrokerOperation::HealthRead,
            &ea3_fixture_sha(),
            false,
            EA3_NOW_IN_WINDOW_MS,
            &ledger,
        );
        assert!(verdict.is_ok(), "expected accept, got {verdict:?}");
    }

    /// envelope 缺席 → 驗證器 `EnvelopeAbsent` 路徑（seal 缺席時單一拒因;typed 不 panic）。
    #[cfg(unix)]
    #[test]
    fn ea3_gate_denies_absent_envelope() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let ledger = ActivationNonceLedger::new();

        let err = ea3_envelope_activation_gate(
            &gov,
            BrokerOperation::HealthRead,
            &ea3_fixture_sha(),
            false,
            EA3_NOW_IN_WINDOW_MS,
            &ledger,
        )
        .unwrap_err();
        match err {
            TwsClientError::ActivationRejected { blockers } => {
                assert!(blockers.contains("EnvelopeAbsent"), "{blockers}");
            }
            other => panic!("expected ActivationRejected, got {other:?}"),
        }
    }

    /// seal 在位而 envelope 缺席 → `SealIsNotActivationAuthority`（seal≠活化機器證明
    /// 全鏈保真;seal 在位事實為注入參數,來源紀律由 entry 呼叫端持有）。
    #[cfg(unix)]
    #[test]
    fn ea3_gate_denies_seal_without_envelope() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let ledger = ActivationNonceLedger::new();

        let err = ea3_envelope_activation_gate(
            &gov,
            BrokerOperation::HealthRead,
            &ea3_fixture_sha(),
            true,
            EA3_NOW_IN_WINDOW_MS,
            &ledger,
        )
        .unwrap_err();
        match err {
            TwsClientError::ActivationRejected { blockers } => {
                assert!(blockers.contains("EnvelopeAbsent"), "{blockers}");
                assert!(
                    blockers.contains("SealIsNotActivationAuthority"),
                    "{blockers}"
                );
            }
            other => panic!("expected ActivationRejected, got {other:?}"),
        }
    }

    /// 壞 JSON → `EnvelopeUnavailable`（typed,不 panic,不 fall-through 到 absent 語義）。
    #[cfg(unix)]
    #[test]
    fn ea3_gate_denies_malformed_envelope_json() {
        use std::os::unix::fs::PermissionsExt;
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let path = gov.join(ACTIVATION_ENVELOPE_FILENAME);
        std::fs::write(&path, "{ not json").unwrap();
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600)).unwrap();
        write_ea3_epochs_file(&gov, 1, 1, 0o600);
        let ledger = ActivationNonceLedger::new();

        let err = ea3_envelope_activation_gate(
            &gov,
            BrokerOperation::HealthRead,
            &ea3_fixture_sha(),
            false,
            EA3_NOW_IN_WINDOW_MS,
            &ledger,
        )
        .unwrap_err();
        assert!(
            matches!(err, TwsClientError::EnvelopeUnavailable(_)),
            "{err:?}"
        );
        // 壞 artifact 絕不燒 nonce。
        let fixture = IbkrActivationEnvelopeV1::readonly_fixture();
        assert!(!ledger.is_consumed(&fixture.activation_nonce));
    }

    /// 權限過寬（0o644）→ `EnvelopeUnavailable`（owner-only 紀律,沿 seal 慣例）。
    #[cfg(unix)]
    #[test]
    fn ea3_gate_denies_wide_permission_envelope() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        write_ea3_envelope_file(&gov, &IbkrActivationEnvelopeV1::readonly_fixture(), 0o644);
        write_ea3_epochs_file(&gov, 1, 1, 0o600);
        let ledger = ActivationNonceLedger::new();

        let err = ea3_envelope_activation_gate(
            &gov,
            BrokerOperation::HealthRead,
            &ea3_fixture_sha(),
            false,
            EA3_NOW_IN_WINDOW_MS,
            &ledger,
        )
        .unwrap_err();
        assert!(
            matches!(err, TwsClientError::EnvelopeUnavailable(_)),
            "{err:?}"
        );
    }

    /// envelope symlink → `EnvelopeUnavailable`（lstat 不跟隨）。
    #[cfg(unix)]
    #[test]
    fn ea3_gate_denies_symlink_envelope() {
        use std::os::unix::fs::PermissionsExt;
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let target = tmp.path().join("real_envelope.json");
        std::fs::write(
            &target,
            serde_json::to_string(&IbkrActivationEnvelopeV1::readonly_fixture()).unwrap(),
        )
        .unwrap();
        std::fs::set_permissions(&target, std::fs::Permissions::from_mode(0o600)).unwrap();
        std::os::unix::fs::symlink(&target, gov.join(ACTIVATION_ENVELOPE_FILENAME)).unwrap();
        write_ea3_epochs_file(&gov, 1, 1, 0o600);
        let ledger = ActivationNonceLedger::new();

        let err = ea3_envelope_activation_gate(
            &gov,
            BrokerOperation::HealthRead,
            &ea3_fixture_sha(),
            false,
            EA3_NOW_IN_WINDOW_MS,
            &ledger,
        )
        .unwrap_err();
        assert!(
            matches!(err, TwsClientError::EnvelopeUnavailable(_)),
            "{err:?}"
        );
    }

    /// envelope 在位而 epoch 現值缺席 → fail-closed 拒（無從證明未被撤銷/kill）。
    #[cfg(unix)]
    #[test]
    fn ea3_gate_denies_missing_epochs_when_envelope_present() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        write_ea3_envelope_file(&gov, &IbkrActivationEnvelopeV1::readonly_fixture(), 0o600);
        let ledger = ActivationNonceLedger::new();

        let err = ea3_envelope_activation_gate(
            &gov,
            BrokerOperation::HealthRead,
            &ea3_fixture_sha(),
            false,
            EA3_NOW_IN_WINDOW_MS,
            &ledger,
        )
        .unwrap_err();
        assert!(
            matches!(err, TwsClientError::EnvelopeUnavailable(_)),
            "{err:?}"
        );
        let fixture = IbkrActivationEnvelopeV1::readonly_fixture();
        assert!(!ledger.is_consumed(&fixture.activation_nonce));
    }

    /// 現值 epoch 被 bump（撤銷語義）→ 綁定失配拒且不燒 nonce。
    #[cfg(unix)]
    #[test]
    fn ea3_gate_denies_epoch_mismatch_without_burning_nonce() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let fixture = IbkrActivationEnvelopeV1::readonly_fixture();
        write_ea3_envelope_file(&gov, &fixture, 0o600);
        write_ea3_epochs_file(&gov, 2, 1, 0o600); // revocation 已 bump（envelope 綁 1）。
        let ledger = ActivationNonceLedger::new();

        let err = ea3_envelope_activation_gate(
            &gov,
            BrokerOperation::HealthRead,
            &ea3_fixture_sha(),
            false,
            EA3_NOW_IN_WINDOW_MS,
            &ledger,
        )
        .unwrap_err();
        match err {
            TwsClientError::ActivationRejected { blockers } => {
                assert!(blockers.contains("RevocationEpochMismatch"), "{blockers}");
            }
            other => panic!("expected ActivationRejected, got {other:?}"),
        }
        assert!(!ledger.is_consumed(&fixture.activation_nonce));
    }

    /// 現 binary build SHA 與 envelope 綁定不符 → 拒（envelope 綁死精確 build）。
    #[cfg(unix)]
    #[test]
    fn ea3_gate_denies_build_sha_mismatch() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        write_ea3_envelope_file(&gov, &IbkrActivationEnvelopeV1::readonly_fixture(), 0o600);
        write_ea3_epochs_file(&gov, 1, 1, 0o600);
        let ledger = ActivationNonceLedger::new();

        let err = ea3_envelope_activation_gate(
            &gov,
            BrokerOperation::HealthRead,
            &"0".repeat(40),
            false,
            EA3_NOW_IN_WINDOW_MS,
            &ledger,
        )
        .unwrap_err();
        match err {
            TwsClientError::ActivationRejected { blockers } => {
                assert!(blockers.contains("BuildGitShaMismatch"), "{blockers}");
            }
            other => panic!("expected ActivationRejected, got {other:?}"),
        }
    }

    /// readonly envelope + order verb → 結構性拒全鏈保真（G4 entry 固定 HealthRead,
    /// 本測試證明閘本身對 verb 白名單忠實轉發驗證器裁決）。
    #[cfg(unix)]
    #[test]
    fn ea3_gate_denies_order_verb_structurally() {
        let tmp = tempfile::tempdir().unwrap();
        let gov = make_gov_chain(tmp.path());
        let fixture = IbkrActivationEnvelopeV1::readonly_fixture();
        write_ea3_envelope_file(&gov, &fixture, 0o600);
        write_ea3_epochs_file(&gov, 1, 1, 0o600);
        let ledger = ActivationNonceLedger::new();

        let err = ea3_envelope_activation_gate(
            &gov,
            BrokerOperation::PaperOrderSubmit,
            &ea3_fixture_sha(),
            false,
            EA3_NOW_IN_WINDOW_MS,
            &ledger,
        )
        .unwrap_err();
        match err {
            TwsClientError::ActivationRejected { blockers } => {
                assert!(
                    blockers.contains("OrderVerbStructurallyDenied"),
                    "{blockers}"
                );
            }
            other => panic!("expected ActivationRejected, got {other:?}"),
        }
        assert!(!ledger.is_consumed(&fixture.activation_nonce));
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
