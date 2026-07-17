//! MODULE_NOTE
//! 模塊用途：IBKR **W3 TWS session driver（端到端讀迴圈）**（W3-S4;設計 §4 整合 S1+S2+S3）。
//!   承 B1 driver 範式（duplex synthetic-frame 讀迴圈）,把 S1（wire codec / FrameReader）+
//!   S2（session FSM / manager）+ S3（pacing governor 單一出口）用**注入 transport factory**
//!   串成可跑的長連線讀迴圈:冷啟 → permit check → connect → 握手 → Ready → 心跳（過 governor）
//!   → 故障注入 → 斷線/重連對賬。**fake 測試域**以 tokio duplex + granting provider 走通;
//!   **production** 恆撞 `EnvelopeRequiredStub` 停 `Disconnected(EnvelopeRequired)`（INV-1）。
//! 主要區段：
//!   - (a) transport 抽象：`TransportFactory`（注入 stream 來源;fake=duplex,W8=TCP）+ `TransportError`。
//!   - (b) **F4 單一出口牙齒**：`send_framed(grant: OutboundGrant, frame)` **by-value 消費 grant**——
//!     出站 framed 訊息**編譯期強制**過 governor（無 grant 無法呼叫 send;grant 唯 governor 鑄）。
//!   - (c) 注入時鐘：`DriverClock`（心跳/故障時序;fixture 禁硬編日期,注入 now_ms）。
//!   - (d) `SessionDriver<P, F>`：driver 本體。持 S2 `TwsSessionManager`（fsm+governor+F3）+ **注入
//!     permit `P`**（production=`EnvelopeRequiredStub` / test=granting provider）+ transport factory `F`。
//!     `run_connect_cycle` = permit → connect → 握手 → serve loop → 斷線判定 → 回 `CycleOutcome`。
//! 依賴：`tokio`（io traits;duplex 由測試/dev-crate 提供,本檔零 socket）、`ibkr_tws_wire`（codec /
//!   FrameReader / timeout）、`ibkr_tws_session`（FSM / manager / permit / F3）、`ibkr_tws_pacing`
//!   （OutboundGrant）、`openclaw_types`（pin / info floor / 現勘 code）。
//! 硬邊界：
//!   - **零真 socket**：本檔零 `TcpStream::connect`、零真實網路型別;stream 由 `TransportFactory`
//!     注入（fake 域=tokio in-process duplex,零 socket;TCP factory 是 W8 `ibkr_transport_tcp` 事）。
//!   - **INV-1（連接 permit）**：driver 的 connect 決策用**注入 permit `P`**。production 的唯一
//!     `ConnectPermitProvider` 實作 = `EnvelopeRequiredStub`（恆拒）→ production `SessionDriver<P,F>` 只
//!     能是 `SessionDriver<EnvelopeRequiredStub, _>` → 恆停 `Disconnected(EnvelopeRequired)`,factory
//!     從不呼叫。granting provider **僅存在於測試域**（本檔 `#[cfg(test)]`）→ production 零放行。
//!     `TwsSessionManager` 自身的具體 `permit: EnvelopeRequiredStub` 欄仍是 S2 靜態守衛的 INV-1 錨點
//!     + W8 TCP 組合的 permit（二者 production 皆 stub,冗餘為刻意;設計 §10）。
//!   - **F4 單一出口**：driver 一切出站 API 訊息（START_API / reqCurrentTime / 心跳）全走
//!     `send_framed(grant, ..)`;grant 唯 governor 放行時鑄（`OutboundGrant::mint` 模塊私有於 pacing）
//!     → 無 grant 無法送 → 編譯期必經 governor。`API\0` 為**連線 preamble**（含版本協商 frame`v{min}..{max}`）,
//!     pre-session 單次寫、非 pacing-subject 的 API 訊息,故不經 governor（IB 不對 preamble 限速）。
//!   - **DCE 姿態繼承 B1/wire/session/pacing**：整個 TWS 連接器面在 default build **零 production
//!     caller → 被 linker DCE**（g4 nm 審計 + fake 缺席審計驗證）。故本模塊 `#![allow(dead_code)]`
//!     ——**非「藏 orphan」**:driver / send_framed / transport 抽象全有本檔 `#[cfg(test)]` 測試 caller;
//!     **真 production caller = W4 IPC 接線**（明標 `TODO(W4)`;W8 落 TCP factory 進 default build）。
//!   - Bybit crypto_perp 不變;無 DB migration;不擴 types 契約。

// 繼承 B1/wire/session/pacing 的 intentional-DCE 姿態（見 MODULE_NOTE）：整個 TWS 連接器面在
// default build 無 production caller,由 linker DCE（g4 symbol audit + fake 缺席審計驗證）。
#![allow(dead_code)]

use std::future::Future;
use std::time::Duration;

use tokio::io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt};

use openclaw_types::ibkr_tws_session_state::IB_ERR_DUPLICATE_CLIENT_ID;
use openclaw_types::{IB_INFO_CODE_FLOOR, PINNED_MIN_SERVER_VERSION};

use crate::ibkr_tws_account_data::{
    AccountDataConfig, AccountDataDigest, AccountDataReject, SnapshotStaleness,
};
use crate::ibkr_tws_pacing::{OutboundGrant, PacingConfig};
use crate::ibkr_tws_session::{
    ConnectPermitProvider, FatalCause, HandshakeOutcome, HeartbeatOutbound, PacingDispatch,
    SessionState, TwsSessionConfig, TwsSessionManager,
};
use crate::ibkr_tws_wire::{
    classify_error_frame, classify_msg_id, decode_current_time, decode_error_code, decode_fields,
    decode_server_handshake_ack, encode_handshake_prefix, encode_req_current_time,
    encode_start_api, frame_msg_id, managed_accounts_all_paper, with_timeout, FrameReader,
    FrameReaderLimits, KnownMsgId, TimeoutOp, TimeoutPolicy,
};

/// G4 只讀 / W3 session 探針的固定 client_id（read-only;不下單,master-client 語義無關;同 B1）。
const HANDSHAKE_CLIENT_ID: i32 = 0;

/// serve loop 迭代上界（安全網:正常 session 隨 server EOF / fatal / 心跳 drop 自然結束;此界防
/// 測試/異常無限迴圈）。
const SERVE_BUDGET: u32 = 100_000;

/// serve 期讀取的 poll 間隔（**靜默 tick**:每 poll 逾時回 `Idle` 令迴圈重評心跳時序,liveness 靠
/// 心跳 miss 非讀逾時,設計 §1.2）。production 用短間隔即可（成本低;每間隔喚醒一次查心跳）;測試以
/// `tokio::time::pause`(start_paused) 令 poll 即時推進。
const DEFAULT_SERVE_POLL: Duration = Duration::from_secs(1);

/// W5-S2 account summary 訂閱的固定 reqId（request-id 分配器歸 W5-S3+ 請求路由;summary 為
/// 全域單訂閱（G3 自限 1 份）,固定 id 無碰撞面——fake 場景以此值對齊）。
pub(crate) const ACCOUNT_SUMMARY_REQ_ID: i64 = 9001;

// ===========================================================================
// (a) transport 抽象（注入 stream 來源;fake=duplex,W8=TCP factory）
// ===========================================================================

/// transport 建立錯誤（connect timeout / refused → driver 進 transient Backoff）。
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub(crate) enum TransportError {
    #[error("transport connect timed out")]
    Timeout,
    #[error("transport connect refused: {0}")]
    Refused(String),
}

/// **注入 transport factory**:每次 connect 產一條已連線的雙工 stream。fake 域=tokio in-process
/// duplex（零 socket;dev-crate `openclaw_fake_tws` 場景 spawn）;W8=真 `TcpStream::connect`（留
/// `ibkr_transport_tcp` feature 後,持具體 `EnvelopeRequiredStub`,測試域無從注入放行者;設計 §5/§10）。
/// **注**:async fn 以 `-> impl Future` 表達,避免 `async_fn_in_trait` lint 且維持靜態分派（非 dyn）。
pub(crate) trait TransportFactory {
    type Stream: AsyncRead + AsyncWrite + Unpin;
    fn connect(&mut self) -> impl Future<Output = Result<Self::Stream, TransportError>>;
}

// ===========================================================================
// (b) F4 單一出口牙齒:send_framed by-value 消費 OutboundGrant
// ===========================================================================

/// **F4 單一出口牙齒咬合**:送出一個 framed 出站訊息。**by-value 消費 `grant: OutboundGrant`**——
/// `OutboundGrant` 唯 governor 放行時鑄（`mint` 模塊私有於 `ibkr_tws_pacing`）,故**任何**呼叫
/// `send_framed` 者**編譯期**必先持有 governor 鑄的 grant → 出站 framed 訊息結構上無法旁路 governor。
/// driver 一切出站（START_API / reqCurrentTime / 心跳）全走此函數。
async fn send_framed<S: AsyncWrite + Unpin>(
    stream: &mut S,
    grant: OutboundGrant,
    frame: &[u8],
    timeout: Duration,
) -> Result<(), DriverError> {
    // grant by-value 消費（drop）:單次出站憑證,不可復用（非 Clone/非 Copy;與送出動作綁定）。
    drop(grant);
    write_all_timed(stream, frame, timeout).await
}

/// driver I/O 錯誤（read/write/codec/timeout;皆 fail-closed 導向斷線判定,不半接觸）。
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub(crate) enum DriverError {
    #[error("io error: {0}")]
    Io(String),
    #[error("operation timed out: {0:?}")]
    Timeout(TimeoutOp),
    #[error("frame reader error")]
    FrameReader,
    #[error("connection closed before frame completed")]
    Eof,
}

async fn write_all_timed<S: AsyncWrite + Unpin>(
    stream: &mut S,
    buf: &[u8],
    timeout: Duration,
) -> Result<(), DriverError> {
    match with_timeout(TimeoutOp::Io, timeout, stream.write_all(buf)).await {
        Ok(Ok(())) => Ok(()),
        Ok(Err(e)) => Err(DriverError::Io(e.to_string())),
        Err(_) => Err(DriverError::Timeout(TimeoutOp::Io)),
    }
}

/// 從 stream 讀出下一個完整 frame payload（先試既有 buffer,不足才讀;經 S1 `FrameReader` 滾動窗預算
/// → 惡意灌流 fail-closed）。`Ok(None)`=EOF;`Err`=codec/rate/io/timeout（呼叫端 fail-closed 斷線）。
async fn read_next_frame<S: AsyncRead + Unpin>(
    stream: &mut S,
    reader: &mut FrameReader,
    now_ms: u64,
    timeout: Duration,
) -> Result<Option<Vec<u8>>, DriverError> {
    loop {
        match reader.next_frame(now_ms) {
            Ok(Some(payload)) => return Ok(Some(payload)),
            Ok(None) => {}
            Err(_) => return Err(DriverError::FrameReader),
        }
        let mut tmp = [0u8; 4096];
        match with_timeout(TimeoutOp::Io, timeout, stream.read(&mut tmp)).await {
            Ok(Ok(0)) => return Ok(None), // EOF
            Ok(Ok(n)) => {
                if reader.push_bytes(&tmp[..n], now_ms).is_err() {
                    return Err(DriverError::FrameReader);
                }
            }
            Ok(Err(e)) => return Err(DriverError::Io(e.to_string())),
            Err(_) => return Err(DriverError::Timeout(TimeoutOp::Io)),
        }
    }
}

/// serve 期一次讀取的結果（**區分 Idle poll tick vs 斷線**;與握手期 `read_next_frame` 不同語義）。
enum ServeRead {
    /// 取到一個完整 frame。
    Frame(Vec<u8>),
    /// server EOF（write 半關）→ 斷線。
    Eof,
    /// poll 逾時（靜默:server 開著但暫無資料）或收到不足一 frame 的部分位元組 → **非斷線**,續迴圈
    /// （頂部重評心跳時序;liveness 靠心跳 miss 非讀逾時,設計 §1.2）。
    Idle,
    /// 讀錯 / codec 超限（滾動窗）→ fail-closed 斷線。
    Failed,
}

/// serve 期讀取一步:先看 buffer 有無完整 frame（免讀）,否則 poll 一次（bounded `poll_timeout`）。
/// **靜默期正常**——server 開著但無資料時回 `Idle`（非斷線）,令 serve 迴圈重評心跳並最終以心跳 miss
/// 判 liveness（silent server → Degraded → HeartbeatDropped;設計 §1.2）,唯 EOF / 讀錯 / codec 超限
/// 才斷線。
async fn serve_read_step<S: AsyncRead + Unpin>(
    stream: &mut S,
    reader: &mut FrameReader,
    now_ms: u64,
    poll_timeout: Duration,
) -> ServeRead {
    // 先看 buffer 有無完整 frame（免讀;跨迭代殘留 + 握手殘餘）。
    match reader.next_frame(now_ms) {
        Ok(Some(payload)) => return ServeRead::Frame(payload),
        Ok(None) => {}
        Err(_) => return ServeRead::Failed,
    }
    let mut tmp = [0u8; 4096];
    match with_timeout(TimeoutOp::Io, poll_timeout, stream.read(&mut tmp)).await {
        Ok(Ok(0)) => ServeRead::Eof, // server write 半關 → 斷線
        Ok(Ok(n)) => {
            if reader.push_bytes(&tmp[..n], now_ms).is_err() {
                return ServeRead::Failed; // 滾動窗超限 → fail-closed
            }
            match reader.next_frame(now_ms) {
                Ok(Some(payload)) => ServeRead::Frame(payload),
                Ok(None) => ServeRead::Idle, // 不足一 frame,續 poll
                Err(_) => ServeRead::Failed,
            }
        }
        Ok(Err(_)) => ServeRead::Failed,
        Err(_) => ServeRead::Idle, // poll 逾時:靜默 tick（非斷線;liveness 靠心跳）
    }
}

// ===========================================================================
// (c) 注入時鐘（心跳/故障時序;fixture 禁硬編日期,注入 now_ms）
// ===========================================================================

/// driver 注入時鐘:回當前 ms（單調不倒退由實作保證;serve loop 每迭代取一次）。production 用真
/// 單調時鐘（W8）;測試用確定性序列（`SeqClock`）。
pub(crate) trait DriverClock {
    fn now_ms(&mut self) -> u64;
}

// ===========================================================================
// (d) SessionDriver — 端到端讀迴圈
// ===========================================================================

/// 一次 connect-cycle（握手段）的裁決。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum ConnectStep {
    /// permit 拒（production stub）→ `Disconnected(EnvelopeRequired)`,factory 未呼叫。
    Denied,
    /// factory.connect 失敗（timeout/refused）→ Backoff。
    ConnectFailed,
    /// 握手致命（版本過舊 / 非 paper / gateway error<2100 / 326 踢線）→ `Disconnected(SessionFatal)`。
    HandshakeFatal,
    /// 握手 transient（IO/EOF/timeout/codec/亂序未實檢 paper）→ Backoff。
    HandshakeTransient,
    /// 到 Ready（stream 保留於 driver 供 serve）。
    Ready,
}

/// serve loop 結束原因。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum ServeEnd {
    /// server EOF / IO 斷 / codec fail-closed / 未知 msgId → Backoff。
    IoDropped,
    /// session-fatal error frame（326 / 502 / pacing 三振…）→ `Disconnected(SessionFatal)`。
    SessionFatal,
    /// 心跳連續 miss 達 drop 門檻 → Backoff。
    HeartbeatDropped,
    /// serve budget 用盡（安全網;正常 session 不觸）。
    BudgetExhausted,
}

/// 一次 `run_connect_cycle` 的整體裁決。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum CycleOutcome {
    /// 結構性終態（SessionFatal/WeeklyReauth/Exhausted/Halted）→ 永不自動重連,cycle no-op。
    Terminal,
    /// Backoff 延遲未到期 → 尚不重連（退避等待中）。
    BackingOff,
    /// permit 拒（production 恆此路;INV-1）。
    Denied,
    ConnectFailed,
    HandshakeFatal,
    HandshakeTransient,
    /// 到 Ready 後 serve 結束（帶結束原因）。
    Served(ServeEnd),
}

/// 端到端 TWS session driver（設計 §4）。持 S2 manager（fsm+governor+F3）+ 注入 permit + transport
/// factory。泛型於 `P: ConnectPermitProvider`（**注**:泛型 permit 面在本 driver 檔,非 session 檔——
/// INV-1 靜態守衛錨定 session 檔的具體 stub;此處注入面 production 唯一實作=stub,test-only=granting）
/// 與 `F: TransportFactory`（stream 來源;fake duplex / W8 TCP）。
pub(crate) struct SessionDriver<P: ConnectPermitProvider, F: TransportFactory> {
    manager: TwsSessionManager,
    /// **注入 connect permit**:production=`EnvelopeRequiredStub`（恆拒）/ test=granting provider。
    permit: P,
    factory: F,
    timeouts: TimeoutPolicy,
    reader_limits: FrameReaderLimits,
    /// serve 期靜默 poll 間隔（見 `DEFAULT_SERVE_POLL`;每 poll 逾時回 Idle 重評心跳時序）。
    serve_poll: Duration,
    /// **觀測**:serve 期是否曾抵達 Degraded（心跳劣化;測試斷言心跳 miss 路徑真經 Degraded,非直接
    /// drop）。跨 serve 呼叫累積,重連不重置（telemetry 語義）。
    observed_degraded: bool,
    /// 當前連線 stream + reader（connect_and_handshake 到 Ready 時填,serve 取用後 drop;重連取新）。
    stream: Option<F::Stream>,
    reader: Option<FrameReader>,
    /// **W5-S2**:account/positions 消化器（入站 IN 61-64 分派至此;斷線由 serve 收尾標記）。
    account_data: AccountDataDigest,
    /// W5-S2 訂閱 pump 開關（默認 **off**;`enable_account_data_subscriptions` 開啟後 serve
    /// 期自動經 governor `AccountData` 類送 reqAccountSummary/reqPositions。真消費者=driver
    /// 測試域;TODO(W6) IPC 投影面接真開關）。
    subscribe_account_data: bool,
    /// G1 session 級 blocker 記憶:serverVersion 低於 positions 下界 → 本 session 不再重試
    /// reqPositions（重連/reset 後新 driver 世代重評;避免每 tick 空耗 governor token）。
    positions_floor_blocked: bool,
}

impl<P: ConnectPermitProvider, F: TransportFactory> SessionDriver<P, F> {
    pub(crate) fn new(
        permit: P,
        factory: F,
        config: TwsSessionConfig,
        timeouts: TimeoutPolicy,
        reader_limits: FrameReaderLimits,
    ) -> Self {
        Self::new_with_pacing(
            permit,
            factory,
            config,
            PacingConfig::default(),
            timeouts,
            reader_limits,
        )
    }

    /// 顯式注入 pacing config（供心跳可被 Queued 的 F3 driver 端測試;W4 engine config plumbing 後成
    /// 真接線口）。
    pub(crate) fn new_with_pacing(
        permit: P,
        factory: F,
        config: TwsSessionConfig,
        pacing: PacingConfig,
        timeouts: TimeoutPolicy,
        reader_limits: FrameReaderLimits,
    ) -> Self {
        Self {
            manager: TwsSessionManager::new_with_pacing(config, pacing),
            permit,
            factory,
            timeouts,
            reader_limits,
            serve_poll: DEFAULT_SERVE_POLL,
            observed_degraded: false,
            stream: None,
            reader: None,
            account_data: AccountDataDigest::new(AccountDataConfig::default()),
            subscribe_account_data: false,
            positions_floor_blocked: false,
        }
    }

    pub(crate) fn state(&self) -> &SessionState {
        self.manager.state()
    }

    pub(crate) fn manager(&self) -> &TwsSessionManager {
        &self.manager
    }

    /// serve 期是否曾抵達 Degraded（見欄位）。
    pub(crate) fn observed_degraded(&self) -> bool {
        self.observed_degraded
    }

    /// **W5-S2** account/positions 消化器唯讀檢視（typed staleness + 最新行）。
    pub(crate) fn account_data(&self) -> &AccountDataDigest {
        &self.account_data
    }

    /// **W5-S2** 開啟訂閱 pump（默認 off;serve 期經 governor `AccountData` 類自動訂閱。
    /// 真消費者=driver 測試域;TODO(W6) IPC 投影面接真開關）。
    pub(crate) fn enable_account_data_subscriptions(&mut self) {
        self.subscribe_account_data = true;
    }

    /// **測試專用**:可變存取內部 manager（令測試預先耗盡 governor token 逼心跳 Queued,驗 driver
    /// serve loop 的 `resolve_pacing → HeartbeatReady → send_framed` 分派）。
    #[cfg(test)]
    pub(crate) fn manager_mut(&mut self) -> &mut TwsSessionManager {
        &mut self.manager
    }

    /// **測試專用**:縮短 serve 靜默 poll 間隔（令 silent-server 心跳劣化測試以極短真 poll 逾時快速
    /// 推進迭代,免依賴 tokio `test-util`/`start_paused`;注入時鐘仍獨立驅動心跳時序）。
    #[cfg(test)]
    pub(crate) fn set_serve_poll(&mut self, d: Duration) {
        self.serve_poll = d;
    }

    /// 端到端一次 connect-cycle:冷啟/退避 → permit → connect → 握手 → serve → 斷線判定。
    /// **production**:permit（stub）恆拒 → 立即回 `Denied`,factory 從不呼叫（INV-1）。
    /// **fake test**:granting provider 放行 → 走通全鏈,serve loop 讀 fake duplex 直到 EOF/fatal。
    pub(crate) async fn run_connect_cycle(&mut self, clock: &mut impl DriverClock) -> CycleOutcome {
        // 結構性終態前置閘（永不自動重連）。
        if self.manager.is_terminal() {
            return CycleOutcome::Terminal;
        }
        let now = clock.now_ms();
        // Backoff 延遲未到期 → 尚不重連（退避等待;delay 為 full-jitter,測試推進 now 過 ceiling 即到期）。
        if matches!(self.manager.state(), SessionState::Backoff { .. }) {
            if !self.manager.fsm_mut().backoff_elapsed(now) {
                return CycleOutcome::BackingOff;
            }
        }
        match self.connect_and_handshake(now).await {
            ConnectStep::Denied => CycleOutcome::Denied,
            ConnectStep::ConnectFailed => CycleOutcome::ConnectFailed,
            ConnectStep::HandshakeFatal => CycleOutcome::HandshakeFatal,
            ConnectStep::HandshakeTransient => CycleOutcome::HandshakeTransient,
            ConnectStep::Ready => CycleOutcome::Served(self.serve(clock).await),
        }
    }

    /// permit → connect → 握手 → Ready（或 Denied/ConnectFailed/Fatal/Transient）。假設非終態
    /// （`run_connect_cycle` 已前置閘）。
    async fn connect_and_handshake(&mut self, now: u64) -> ConnectStep {
        // INV-1:注入 permit 決策。production stub 恆拒 → Disconnected(EnvelopeRequired),factory 不呼叫。
        let token = match self.permit.check() {
            Ok(t) => t,
            Err(_) => {
                let _ = self.manager.fsm_mut().on_permit_denied();
                return ConnectStep::Denied;
            }
        };
        let _ = self.manager.fsm_mut().on_permit_granted(token, now); // → Connecting
        let mut stream = match self.factory.connect().await {
            Ok(s) => s,
            Err(_) => {
                let delay = self.manager.next_transient_backoff_delay();
                let _ = self.manager.fsm_mut().on_connect_failed(now, delay); // → Backoff
                return ConnectStep::ConnectFailed;
            }
        };
        let _ = self.manager.fsm_mut().on_transport_established(now); // → Handshaking
        let mut reader = FrameReader::new(self.reader_limits);
        // 握手全程包 handshake_total 總預算（設計 §2.5;逾時 → transient）。
        let hs = match with_timeout(
            TimeoutOp::HandshakeTotal,
            self.timeouts.handshake_total,
            run_handshake_inner(
                &mut self.manager,
                &mut stream,
                &mut reader,
                now,
                &self.timeouts,
            ),
        )
        .await
        {
            Ok(inner) => inner,
            Err(_) => Err(HandshakeErr::Transient),
        };
        match hs {
            Ok(()) => {
                // 到 Ready:stream+reader 交棒給 serve。
                self.stream = Some(stream);
                self.reader = Some(reader);
                ConnectStep::Ready
            }
            Err(HandshakeErr::Fatal) => ConnectStep::HandshakeFatal, // fsm 已 fatal
            Err(HandshakeErr::Transient) => {
                let delay = self.manager.next_transient_backoff_delay();
                let _ = self.manager.fsm_mut().on_handshake_transient(now, delay); // → Backoff
                ConnectStep::HandshakeTransient
            }
        }
    }

    /// Ready 後的 serve loop（讀 server frames + 排心跳 + 故障判定;注入時鐘）。
    async fn serve(&mut self, clock: &mut impl DriverClock) -> ServeEnd {
        let mut stream = match self.stream.take() {
            Some(s) => s,
            None => return ServeEnd::IoDropped,
        };
        let mut reader = match self.reader.take() {
            Some(r) => r,
            None => return ServeEnd::IoDropped,
        };
        let mut budget = 0u32;
        let end = loop {
            budget += 1;
            if budget > SERVE_BUDGET {
                break ServeEnd::BudgetExhausted;
            }
            let now = clock.now_ms();
            // 前輪 error frame 可能已驅 FSM 離開 Ready/Degraded → 判結束。
            if !self.in_serve_state() {
                break self.classify_serve_end();
            }
            // 1. 心跳到期 → 經 governor 送（單一出口:send_framed 消費 grant）。
            match self.manager.heartbeat_outbound(now) {
                HeartbeatOutbound::Sent { grant, frame } => {
                    if send_framed(&mut stream, grant, &frame, self.timeouts.io)
                        .await
                        .is_err()
                    {
                        break self.drop_io(now);
                    }
                }
                HeartbeatOutbound::Queued(_)
                | HeartbeatOutbound::Rejected(_)
                | HeartbeatOutbound::NotDue => {}
            }
            // 2. F3:排空 governor 佇列;在途心跳放行 → send_framed（簿記已於 resolve_pacing 回填）。
            let mut io_broke = false;
            for d in self.manager.resolve_pacing(now) {
                if let PacingDispatch::HeartbeatReady { grant, frame } = d {
                    if send_framed(&mut stream, grant, &frame, self.timeouts.io)
                        .await
                        .is_err()
                    {
                        io_broke = true;
                        break;
                    }
                }
            }
            if io_broke {
                break self.drop_io(now);
            }
            // 2b. W5-S2:account/positions 訂閱 pump（默認 off;開啟後未訂閱/失效即經
            // governor `AccountData` 類取 grant → send_framed 送訂閱,單一出口不變量）。
            if self.subscribe_account_data
                && self.pump_account_data(&mut stream, now).await.is_err()
            {
                break self.drop_io(now);
            }
            // 3. 心跳回覆逾時 → miss（達 degraded 門檻 → Degraded;達 drop 門檻 → Backoff）。
            if self.manager.fsm_mut().heartbeat_reply_overdue(now) {
                let would_drop = self.manager.fsm_mut().heartbeat_miss_would_drop();
                let delay = if would_drop {
                    self.manager.next_transient_backoff_delay()
                } else {
                    Duration::ZERO
                };
                let _ = self.manager.fsm_mut().on_heartbeat_miss(now, delay);
                if matches!(self.manager.state(), SessionState::Degraded(_)) {
                    self.observed_degraded = true; // 心跳劣化路徑真經 Degraded（測試斷言用）
                }
                if matches!(self.manager.state(), SessionState::Backoff { .. }) {
                    break ServeEnd::HeartbeatDropped;
                }
                continue;
            }
            // 4. 讀下一 server frame（靜默 poll tick 非斷線;liveness 靠上方心跳 miss,設計 §1.2）。
            match serve_read_step(&mut stream, &mut reader, now, self.serve_poll).await {
                ServeRead::Frame(payload) => self.process_serve_frame(&payload, now),
                ServeRead::Eof => break self.drop_io(now), // server 關 → 斷線
                ServeRead::Failed => break self.drop_io(now), // 讀錯 / codec 超限 → fail-closed
                ServeRead::Idle => {} // 靜默 tick,續迴圈（心跳 liveness 於頂部）
            }
        };
        // W5-S2:serve 任何結束路徑（EOF/IO/fatal/心跳 drop/budget）= 連線失效 → 快照標
        // `DisconnectedStale`（訂閱不跨連線存活,重連需重訂閱;fail-closed 明示不可信）。
        self.account_data.on_disconnect();
        drop(stream);
        drop(reader);
        end
    }

    /// W5-S2 訂閱 pump:未訂閱/斷線失效的資料面 → 取 governor grant（`AccountData` 類,
    /// 單一出口）→ digest 轉移訂閱狀態 → `send_framed` 送出。grant 先於 begin:begin 成功
    /// 即送出,無「已標訂閱但未送」的簿記謊言;grant 不足本 tick 跳過（無副作用,下 tick 重試）。
    /// `Err(())` = IO 斷,呼叫端 fail-closed。
    async fn pump_account_data<S: AsyncWrite + Unpin>(
        &mut self,
        stream: &mut S,
        now: u64,
    ) -> Result<(), ()> {
        // summary(G3 單訂閱:staleness 閘保證 begin 不撞 AlreadyActive)。
        if matches!(
            self.account_data.summary_staleness(now),
            SnapshotStaleness::NotSubscribed | SnapshotStaleness::DisconnectedStale
        ) {
            if let Some(grant) = self.manager.account_data_grant(now) {
                match self
                    .account_data
                    .begin_account_summary(ACCOUNT_SUMMARY_REQ_ID)
                {
                    Ok(frame) => {
                        if send_framed(stream, grant, &frame, self.timeouts.io)
                            .await
                            .is_err()
                        {
                            return Err(());
                        }
                    }
                    // staleness 閘下不可達;防禦性 no-op（grant 隨 scope drop）。
                    Err(_) => {}
                }
            }
        }
        // positions(G1:serverVersion 低於下界 → session 級 blocker,本 session 不再重試)。
        if !self.positions_floor_blocked
            && matches!(
                self.account_data.positions_staleness(now),
                SnapshotStaleness::NotSubscribed | SnapshotStaleness::DisconnectedStale
            )
        {
            let server_version = match self.manager.state() {
                SessionState::Ready(rs) | SessionState::Degraded(rs) => rs.server_version,
                _ => return Ok(()),
            };
            if let Some(grant) = self.manager.account_data_grant(now) {
                match self.account_data.begin_positions(server_version) {
                    Ok(frame) => {
                        if send_framed(stream, grant, &frame, self.timeouts.io)
                            .await
                            .is_err()
                        {
                            return Err(());
                        }
                    }
                    Err(AccountDataReject::ServerVersionBelowPositionsFloor { .. }) => {
                        // G1 session 級 blocker:記憶後不再空耗 token 重試（新連線世代重評）。
                        self.positions_floor_blocked = true;
                    }
                    Err(_) => {}
                }
            }
        }
        Ok(())
    }

    fn in_serve_state(&self) -> bool {
        matches!(
            self.manager.state(),
            SessionState::Ready(_) | SessionState::Degraded(_)
        )
    }

    /// serve 期 FSM 已離開 Ready/Degraded 時判結束原因（error frame → SessionFatal / io → Backoff）。
    fn classify_serve_end(&self) -> ServeEnd {
        match self.manager.state() {
            SessionState::Disconnected { .. } => ServeEnd::SessionFatal,
            _ => ServeEnd::IoDropped,
        }
    }

    /// IO 斷（EOF / 送失敗 / codec fail-closed）→ transient Backoff。
    fn drop_io(&mut self, now: u64) -> ServeEnd {
        let delay = self.manager.next_transient_backoff_delay();
        let _ = self.manager.fsm_mut().on_io_drop(now, delay);
        ServeEnd::IoDropped
    }

    /// 處理一個 serve 期 server frame（§2.3/2.4;未知 msgId / malformed → fail-closed 斷線）。
    fn process_serve_frame(&mut self, payload: &[u8], now: u64) {
        let msg_id = match frame_msg_id(payload) {
            Ok(id) => id,
            Err(_) => {
                self.fail_closed(now);
                return;
            }
        };
        match classify_msg_id(msg_id) {
            // 49:serve 期 currentTime = 心跳回覆（Degraded→Ready 恢復;miss 歸零）。
            Some(KnownMsgId::CurrentTime) => {
                let _ = self.manager.fsm_mut().on_heartbeat_reply(now);
            }
            // 4:ERR_MSG → 分類 → manager（pacing 三振 / N2 farm-blip transient / session-fatal）。
            Some(KnownMsgId::ErrMsg) => match classify_error_frame(payload) {
                Ok((code, class)) => {
                    let _ = self.manager.on_error_frame(code, class, now);
                }
                Err(_) => self.fail_closed(now), // malformed err frame → fail-closed
            },
            // 15/9:serve 期重現（罕見）→ 容忍忽略（已知 msgId,非未知）。
            Some(KnownMsgId::ManagedAccounts) | Some(KnownMsgId::NextValidId) => {}
            // W5-S2:IN 61-64 account/positions → 消化器（wire 損壞才斷線,資料層 reject 續 serve）。
            Some(KnownMsgId::AccountSummary) => {
                let r = self.account_data.on_account_summary_frame(payload, now);
                self.handle_account_data_result(r, now);
            }
            Some(KnownMsgId::AccountSummaryEnd) => {
                let r = self.account_data.on_account_summary_end_frame(payload, now);
                self.handle_account_data_result(r, now);
            }
            Some(KnownMsgId::PositionData) => {
                let r = self.account_data.on_position_frame(payload, now);
                self.handle_account_data_result(r, now);
            }
            Some(KnownMsgId::PositionEnd) => {
                let r = self.account_data.on_position_end_frame(payload, now);
                self.handle_account_data_result(r, now);
            }
            // 未知 msgId → fail-closed 斷線（§2.3:不猜欄位、不跳過）。
            None => self.fail_closed(now),
        }
    }

    /// W5-S2 消化結果分流:`WireMalformed`（欄位缺/非數字/錯位）= wire 損壞 → 既有紀律
    /// fail-closed 斷線;其餘 typed reject（契約 blocker/哨兵/reqId 錯配/未訂而收）= 資料層
    /// fail-closed——快照已由 digest 標 `Invalidated`/拒併入,session 續 serve（不 panic）。
    fn handle_account_data_result(&mut self, r: Result<(), AccountDataReject>, now: u64) {
        match r {
            Ok(()) => {}
            Err(AccountDataReject::WireMalformed(_)) => self.fail_closed(now),
            Err(_) => {}
        }
    }

    /// serve 期 fail-closed 斷線（未知 msgId / malformed）:Ready/Degraded → Backoff。
    fn fail_closed(&mut self, now: u64) {
        if self.in_serve_state() {
            let delay = self.manager.next_transient_backoff_delay();
            let _ = self.manager.fsm_mut().on_io_drop(now, delay);
        }
    }
}

/// 握手內層錯誤:致命（FSM 已驅 fatal）vs transient（呼叫端進 Backoff）。
enum HandshakeErr {
    Fatal,
    Transient,
}

/// 握手讀迴圈（承 B1 `drive_handshake_and_current_time` 範式,但驅動 S2 FSM + 過 S3 governor）。
/// 序:寫連線 preamble（`API\0`+版本協商 frame,pre-session 直寫,非 pacing-subject）→ 讀 ACK →
/// version pin 自檢 → 送 START_API+reqCurrentTime
/// （control,過 governor → send_framed）→ 讀直到 currentTime(49):15 paper 前綴實檢 / 9 記
/// next_valid_id / 4 按 code 分流(≥2100 續讀,<2100 fatal) / 49 done。未 paper_confirmed 到 49（亂序）
/// → transient。**自由函數**（非方法）以避開 driver 泛型 borrow;僅碰 manager fsm/control_grant。
async fn run_handshake_inner<S: AsyncRead + AsyncWrite + Unpin>(
    manager: &mut TwsSessionManager,
    stream: &mut S,
    reader: &mut FrameReader,
    now: u64,
    timeouts: &TimeoutPolicy,
) -> Result<(), HandshakeErr> {
    // 1. 寫連線 preamble（`API\0` + 版本協商 frame `v{min}..{max}`;pre-session 單次寫,非
    //    pacing-subject 的 API 訊息 → 直寫,不過 governor;IB 不對 preamble 限速）。
    let prefix = encode_handshake_prefix(
        crate::ibkr_tws_wire::CLIENT_MIN_VERSION,
        crate::ibkr_tws_wire::CLIENT_MAX_VERSION,
    );
    if write_all_timed(stream, &prefix, timeouts.io).await.is_err() {
        return Err(HandshakeErr::Transient);
    }
    // 2. 讀 ACK frame。
    let ack_payload = match read_next_frame(stream, reader, now, timeouts.io).await {
        Ok(Some(p)) => p,
        _ => return Err(HandshakeErr::Transient), // EOF/codec/timeout
    };
    let ack = match decode_server_handshake_ack(&ack_payload) {
        Ok(a) => a,
        Err(_) => return Err(HandshakeErr::Transient),
    };
    // 3. version pin 自檢 fail-closed（不依賴 server 拒絕行為;§2.2）。
    if ack.server_version < PINNED_MIN_SERVER_VERSION {
        let _ = manager
            .fsm_mut()
            .on_handshake_fatal(FatalCause::ServerVersionTooOld, now);
        return Err(HandshakeErr::Fatal);
    }
    // 4. 送 START_API + reqCurrentTime（control 訊息,過 governor → grant → send_framed;單一出口）。
    let start_api = encode_start_api(HANDSHAKE_CLIENT_ID);
    match manager.control_grant(now) {
        Some(g) => {
            if send_framed(stream, g, &start_api, timeouts.io)
                .await
                .is_err()
            {
                return Err(HandshakeErr::Transient);
            }
        }
        None => return Err(HandshakeErr::Transient),
    }
    let req_time = encode_req_current_time();
    match manager.control_grant(now) {
        Some(g) => {
            if send_framed(stream, g, &req_time, timeouts.io)
                .await
                .is_err()
            {
                return Err(HandshakeErr::Transient);
            }
        }
        None => return Err(HandshakeErr::Transient),
    }
    // 5. 讀直到 currentTime(49)。
    let mut paper_confirmed = false;
    let mut next_valid_id: i64 = 0;
    // server_epoch:握手取到的 server-time（證健康首接觸;W3 driver 不 seal/persist,僅消費為到達
    // Ready 的必要條件——decode 失敗即 transient,見下 CurrentTime 分支）。
    let _server_epoch = loop {
        let payload = match read_next_frame(stream, reader, now, timeouts.io).await {
            Ok(Some(p)) => p,
            Ok(None) => return Err(HandshakeErr::Transient), // EOF before Ready
            Err(_) => return Err(HandshakeErr::Transient),   // codec/rate/timeout
        };
        let msg_id = match frame_msg_id(&payload) {
            Ok(id) => id,
            Err(_) => return Err(HandshakeErr::Transient),
        };
        match classify_msg_id(msg_id) {
            Some(KnownMsgId::CurrentTime) => match decode_current_time(&payload) {
                Ok(epoch) => break epoch,
                Err(_) => return Err(HandshakeErr::Transient),
            },
            Some(KnownMsgId::ManagedAccounts) => match managed_accounts_all_paper(&payload) {
                Ok(true) => paper_confirmed = true,
                Ok(false) => {
                    // 非 paper session → 立即 fatal（絕不對 live session 續讀;B1 紀律）。
                    let _ = manager
                        .fsm_mut()
                        .on_handshake_fatal(FatalCause::NonPaperSession, now);
                    return Err(HandshakeErr::Fatal);
                }
                Err(_) => return Err(HandshakeErr::Transient),
            },
            Some(KnownMsgId::NextValidId) => {
                // nextValidId = ["9","1",id];decode 失敗容忍（沿用既有 next_valid_id）。
                if let Ok(fields) = decode_fields(&payload) {
                    if let Some(idstr) = fields.get(2) {
                        if let Ok(id) = idstr.parse::<i64>() {
                            next_valid_id = id;
                        }
                    }
                }
            }
            Some(KnownMsgId::ErrMsg) => match decode_error_code(&payload) {
                // ≥2100 連線 info/warning（握手期必然出現）→ 續讀。
                Ok(code) if code >= IB_INFO_CODE_FLOOR => {}
                // <2100 真錯誤 → fatal（326=duplicate 拒新連;其餘 GatewayError）。
                Ok(code) => {
                    let cause = if code == IB_ERR_DUPLICATE_CLIENT_ID {
                        FatalCause::DuplicateClientIdRejected
                    } else {
                        FatalCause::GatewayError(code)
                    };
                    let _ = manager.fsm_mut().on_handshake_fatal(cause, now);
                    return Err(HandshakeErr::Fatal);
                }
                Err(_) => return Err(HandshakeErr::Transient),
            },
            // W5-S2:握手期不預期 account/positions 資料（未訂而收=亂序/協議意外）→
            // fail-closed transient（不猜、不 fail-open;可重試）。
            Some(KnownMsgId::AccountSummary)
            | Some(KnownMsgId::AccountSummaryEnd)
            | Some(KnownMsgId::PositionData)
            | Some(KnownMsgId::PositionEnd) => return Err(HandshakeErr::Transient),
            // 未知 msgId 於握手 → fail-closed transient（不猜欄位;可重試,不 fail-open）。
            None => return Err(HandshakeErr::Transient),
        }
    };
    // 到 49 但未見 paper 前綴實檢（亂序）→ fail-closed transient（不以「沒看到」當「已驗證」）。
    if !paper_confirmed {
        return Err(HandshakeErr::Transient);
    }
    let outcome = HandshakeOutcome {
        server_version: ack.server_version,
        connection_time_raw: ack.connection_time,
        paper_confirmed: true,
        next_valid_id,
    };
    let _ = manager.fsm_mut().on_handshake_result(outcome, now); // → Ready（budget 歸零）
    Ok(())
}

#[cfg(test)]
#[path = "ibkr_tws_driver_tests.rs"]
mod tests;
