//! MODULE_NOTE
//! 模塊用途：IBKR **W3 TWS session FSM**（W3-S2;設計 §1 全部）。六態可恢復狀態機 +
//!   指數退避（full jitter）+ reqCurrentTime 心跳 + 排程感知（nightly restart / 週日重認證）
//!   + **INV-1 connect-permit 掛點**（envelope 前置,W8 前恆拒）。消費 S1 的 wire 層
//!   （`ibkr_tws_wire`）與 types 契約骨架（`IbkrTwsSessionStateV1`/`IbkrTwsSessionEventV1`）。
//! 主要區段：
//!   - (a) config：`TwsSessionConfig`（退避/心跳/miss 門檻/排程窗;參數禁假功能——每項真讀取生效）。
//!   - (b) INV-1 permit：`PermitToken`（**非 Clone/非 Copy**,構造子 crate-private,單次消費）+
//!     `ConnectPermitProvider` trait + production 唯一實作 `EnvelopeRequiredStub`（**恆拒,零
//!     env/config/cfg**）。守衛區塊以 `PERMIT-STUB-GUARD-BEGIN/END` 標界（CI 靜態守衛掃描邊界）。
//!   - (c) 退避：`full_jitter_delay`（注入 RNG;base 1s/cap 60s/max 8）+ `FullJitterRng` trait +
//!     production `EntropyJitterRng`（rand StdRng from_entropy）。
//!   - (d) 排程感知：`classify_disconnect_context`（注入 UTC 時鐘 → America/New_York,DST 由
//!     chrono-tz 解;窗未配置=無感知不猜默認時刻,設計 §1.4/§8-U4）。
//!   - (e) FSM：`SessionState`（rich payload）+ `HaltReason` + `SessionFsm`（§1.2 轉移表;
//!     未列組合=`IllegalTransition` typed + debug_assert）+ 心跳 miss/恢復簿記。
//!   - (f) manager：`TwsSessionManager`（**持具體 `EnvelopeRequiredStub`**=INV-1 守衛錨點;
//!     每次 attempt 重新 check() 取新 token,禁緩存;production 恆撞 EnvelopeRequired 停 Disconnected）。
//! 依賴：`std::time::Duration`、`chrono`+`chrono-tz`（僅排程判定）、`rand`（僅 entropy jitter）、
//!   `openclaw_types`（state/event/error-class 契約 + pin 常數 + 現勘 code）、`thiserror`。
//! 硬邊界：
//!   - **無 socket / 無 I/O**：本檔零 `TcpStream::connect`、零 async runtime（純同步狀態機,注入
//!     時鐘/RNG）。真 transport（fake duplex / TCP factory）是 S4 / `ibkr_transport_tcp` feature 事。
//!   - **INV-1（本包最高不變量）**：connect 前必經 `ConnectPermitProvider::check`;`PermitToken`
//!     move 進 connect 單次消費（不可 Clone/緩存）;production 唯一 provider = `EnvelopeRequiredStub`
//!     恆 `Err(EnvelopeRequired)`,**無任何 env/config/cfg 開關可翻放行**。FSM 自動重連全路徑只在
//!     fake 測試域走通;production 每次 Backoff→Connecting 都撞 EnvelopeRequired 停在 Disconnected。
//!   - **DCE 姿態繼承 B1/wire**：整個 IBKR TWS 連接器面在 default build **零 production caller →
//!     被 linker DCE**（W4 IPC 接線後才有真消費者;S3 pacing / S4 fake-TWS 為後續切片）。故本模塊如
//!     `ibkr_tws_wire`（line 32）一律 `#![allow(dead_code)]`——**非「藏 orphan」**:FSM/permit/退避/
//!     排程/manager 全有本檔測試 caller,S3/S4 才接的面（transport factory 注入、pacing 出口）明標
//!     `TODO(S3)`/`TODO(S4)`;module 在 default build dead 是設計使然。
//!   - Bybit crypto_perp 不變;無 DB migration;不擴 types 契約（IPC label 維持 S1 最小集,rich
//!     payload 落本檔 engine-private `SessionState`,經 `label()` 投影回 `IbkrTwsSessionStateV1`）。

// 繼承 B1/wire 的 intentional-DCE 姿態（見 MODULE_NOTE）：整個 TWS 連接器面在 default build
// 無 production caller,由 linker DCE。與 `ibkr_tws_wire` line 32 對稱。
#![allow(dead_code)]

use std::time::Duration;

use chrono::{DateTime, Datelike, Timelike, Utc, Weekday};

use openclaw_types::ibkr_tws_session_state::IB_ERR_DUPLICATE_CLIENT_ID;
use openclaw_types::{
    IbkrTwsErrorClassV1, IbkrTwsSessionEventV1, IbkrTwsSessionStateV1, PINNED_MIN_SERVER_VERSION,
};

// ===========================================================================
// (a) config（全 config 化;設計 §1.3;參數禁假功能——每項必真實被讀取、生效、可觀測）
// ===========================================================================

/// nightly restart 窗（America/New_York 本地時刻;設計 §1.4）。**窗未配置 → 無感知**
/// （`TwsSessionConfig::restart_window == None`,不猜默認時刻,§8-U4）。窗為單日內不跨午夜區間。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct RestartWindow {
    /// 窗起始 ET 本地時（0..=23）。
    pub start_hour: u32,
    /// 窗起始 ET 本地分（0..=59）。
    pub start_minute: u32,
    /// 窗時長（分鐘;現勘 restart 窗為分鐘量級,不跨午夜）。
    pub duration_min: u32,
}

impl RestartWindow {
    /// 若 ET 本地 (hour,minute,second) 落在 `[start, start+duration)` 內,回「到窗尾殘餘 + grace」;
    /// 否則 `None`。以秒粒度計（不丟當前分內秒數,令重連確實推過窗尾）。
    fn remaining_within(
        &self,
        hour: u32,
        minute: u32,
        second: u32,
        grace: Duration,
    ) -> Option<Duration> {
        let now_s = hour * 3600 + minute * 60 + second;
        let start_s = self.start_hour * 3600 + self.start_minute * 60;
        let end_s = start_s + self.duration_min * 60;
        if now_s >= start_s && now_s < end_s {
            Some(Duration::from_secs((end_s - now_s) as u64) + grace)
        } else {
            None
        }
    }
}

/// 週日 ~1:00am ET 強制重認證窗（auto-restart 只覆蓋 Mon-Sat;IB 現勘事實,設計 §1.4）。
/// 窗內斷線 → `Disconnected(WeeklyReauth)`,FSM 永不自動重連（人工+活化事務）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct WeeklyReauthWindow {
    /// 窗起始 ET 本地時（默認 1 = 1am ET）。
    pub start_hour: u32,
    /// 窗起始 ET 本地分（默認 0）。
    pub start_minute: u32,
    /// 窗時長（分鐘;默認 60,~1:00am 的保守寬窗——寧可多停不自動重連,不可誤在重認證窗自動重連）。
    pub duration_min: u32,
}

impl WeeklyReauthWindow {
    fn contains(&self, hour: u32, minute: u32) -> bool {
        let now_m = hour * 60 + minute;
        let start_m = self.start_hour * 60 + self.start_minute;
        let end_m = start_m + self.duration_min;
        now_m >= start_m && now_m < end_m
    }
}

/// session 配置（退避/心跳/miss 門檻/排程窗;設計 §1.3/§1.4）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct TwsSessionConfig {
    /// 指數退避基數（默認 1s）。
    pub backoff_base: Duration,
    /// 退避上限（默認 60s）。
    pub backoff_cap: Duration,
    /// 最大重連嘗試數（默認 8;超過 → `ReconnectBudgetExhausted`,不無限重試,IBKR_TODO §5-W3-1）。
    pub max_reconnect_attempts: u32,
    /// 心跳週期（reqCurrentTime;默認 30s）。
    pub heartbeat_interval: Duration,
    /// 心跳回覆超時（默認 10s;逾時=一次 miss）。
    pub heartbeat_timeout: Duration,
    /// 連續 miss ≥ 此值 → Degraded（socket 未斷,標劣化;默認 2）。
    pub degraded_after_misses: u32,
    /// 連續 miss ≥ 此值 → Backoff（transport 視為斷;默認 4）。
    pub drop_after_misses: u32,
    /// nightly restart 窗（`None` = 無感知,不猜默認時刻;設計 §1.4/§8-U4）。
    pub restart_window: Option<RestartWindow>,
    /// 排程重啟後的 grace（首個延遲 = 窗殘餘 + grace;默認 60s）。
    pub scheduled_grace: Duration,
    /// 週日 ~1:00am ET 重認證窗（IB 現勘事實;默認啟用）。
    pub weekly_reauth: WeeklyReauthWindow,
}

impl Default for TwsSessionConfig {
    fn default() -> Self {
        Self {
            backoff_base: Duration::from_secs(1),
            backoff_cap: Duration::from_secs(60),
            max_reconnect_attempts: 8,
            heartbeat_interval: Duration::from_secs(30),
            heartbeat_timeout: Duration::from_secs(10),
            degraded_after_misses: 2,
            drop_after_misses: 4,
            // U4:Gateway 默認重啟時刻官方通篇無載 → **不猜**,默認無感知。operator 配置後才啟用。
            restart_window: None,
            scheduled_grace: Duration::from_secs(60),
            weekly_reauth: WeeklyReauthWindow {
                start_hour: 1,
                start_minute: 0,
                duration_min: 60,
            },
        }
    }
}

// ===========================================================================
// (b) INV-1 connect-permit（本包最高不變量;設計 §1.5）
// ---------------------------------------------------------------------------
// PERMIT-STUB-GUARD-BEGIN
// 【CI 靜態守衛掃描邊界】本區塊（BEGIN..END）內:
//   - production permit provider = 具體型別 `EnvelopeRequiredStub`（禁 dyn/泛型 permit 參數）;
//   - `EnvelopeRequiredStub::check` 恆 `Err(EnvelopeRequired)`,**零 env / config / cfg 讀取**
//     （無任何開關可翻放行——W8 才以真 envelope 驗證器替換同一 trait 位）;
//   - `PermitToken` 非 Clone / 非 Copy,構造子 `mint` 為 crate-private（唯一鑄造點=provider check
//     回 Ok;production stub 恆不回 Ok → production 永無 token）。
// ---------------------------------------------------------------------------

/// INV-1 permit token:connect 授權的**單次消費證明**。**非 Clone / 非 Copy**——move 進 connect
/// 轉移後即消費,結構上禁止「舊 envelope 靜默復用」（設計 §1.5;AMD §Activation-authenticity）。
/// 構造只能經 `mint`（crate-private）,外部無法以 struct literal 偽造（私有零大小欄位封裝）。
pub(crate) struct PermitToken {
    /// 私有零大小封印:令 `PermitToken { .. }` literal 在 crate 外不可構造。
    _seal: (),
}

impl PermitToken {
    /// **crate-private** 構造子（唯一鑄造點）。只應由 `ConnectPermitProvider::check` 回 `Ok` 時
    /// 呼叫;production 的 `EnvelopeRequiredStub` 恆 `Err` → 從不鑄造 → production 永無 token。
    pub(crate) fn mint() -> Self {
        Self { _seal: () }
    }
}

/// permit 被拒原因（W3 production 恆 `EnvelopeRequired`;W8 真驗證器擴充此枚舉）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, thiserror::Error)]
pub(crate) enum ConnectDenied {
    /// 活化 envelope 前置未滿足（production W8 前恆此路;INV-1）。
    #[error("connect denied: activation envelope required")]
    EnvelopeRequired,
}

/// INV-1 掛點:每次 connect **之前**必經 `check`;回 `Ok(token)` 才可 connect,回 `Err` 不放行。
/// 每次 Backoff→Connecting 重新 `check()` 取新 token（禁緩存 permit;設計 §1.2 轉移表）。
pub(crate) trait ConnectPermitProvider {
    fn check(&mut self) -> Result<PermitToken, ConnectDenied>;
}

/// W3 production **唯一** permit provider:**恆拒**。**零 env / config / cfg 讀取**——本 struct 與其
/// `check` 實作內不存在任何可翻放行的開關;W8 以真 `ibkr_activation_envelope_v1` 驗證器替換同一 trait
/// 位。TCP transport factory（§5,`ibkr_transport_tcp` feature）持此**具體型別**（非 trait object /
/// 非泛型）——測試域無法向 production connect 路徑注入放行者。
pub(crate) struct EnvelopeRequiredStub;

impl ConnectPermitProvider for EnvelopeRequiredStub {
    fn check(&mut self) -> Result<PermitToken, ConnectDenied> {
        // 恆拒。不讀 env、不讀 config、不 cfg!——production 無任何放行路徑。
        Err(ConnectDenied::EnvelopeRequired)
    }
}
// PERMIT-STUB-GUARD-END

// ===========================================================================
// (c) 退避:full jitter 指數退避（注入 RNG;設計 §1.3）
// ===========================================================================

/// 注入式 full-jitter RNG 抽象:回 `[0, upper]` 閉區間一個值。測試以確定性序列注入;
/// production 用 `EntropyJitterRng`（rand StdRng）。**注**:permit 才禁泛型/dyn（INV-1）,RNG
/// 抽象不在該約束內。
pub(crate) trait FullJitterRng {
    /// 回 `[0, upper_inclusive]` 內一個值（full jitter 的均勻取樣）。
    fn jitter_upto(&mut self, upper_inclusive: u64) -> u64;
}

/// production RNG:rand `StdRng`（`from_entropy`;非確定性,只用於真 backoff 抖動）。
pub(crate) struct EntropyJitterRng {
    inner: rand::rngs::StdRng,
}

impl EntropyJitterRng {
    pub(crate) fn new() -> Self {
        use rand::SeedableRng;
        Self {
            inner: rand::rngs::StdRng::from_entropy(),
        }
    }
}

impl FullJitterRng for EntropyJitterRng {
    fn jitter_upto(&mut self, upper_inclusive: u64) -> u64 {
        use rand::Rng;
        if upper_inclusive == 0 {
            0
        } else {
            self.inner.gen_range(0..=upper_inclusive)
        }
    }
}

/// full-jitter 指數退避延遲（設計 §1.3）:`delay = rand(0, min(cap, base × 2^attempt))`。
/// `attempt` 為本次退避的嘗試序（1-based;第 1 次退避 attempt=1）。溢位飽和（不 panic/不 wrap）。
pub(crate) fn full_jitter_delay(
    cfg: &TwsSessionConfig,
    attempt: u32,
    rng: &mut impl FullJitterRng,
) -> Duration {
    let base_ms = cfg.backoff_base.as_millis() as u64;
    let cap_ms = cfg.backoff_cap.as_millis() as u64;
    // 2^attempt 溢位 → 飽和 u64;base×factor 溢位 → 飽和 u64;再 min cap。
    let factor = 2u64.checked_pow(attempt).unwrap_or(u64::MAX);
    let ceiling = base_ms.saturating_mul(factor).min(cap_ms);
    Duration::from_millis(rng.jitter_upto(ceiling))
}

// ===========================================================================
// (d) 排程感知（設計 §1.4;注入 UTC 時鐘 → America/New_York,DST 由 chrono-tz 解,禁手寫偏移）
// ===========================================================================

/// 斷線發生時的排程脈絡（決定退避 vs 永久停機）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum DisconnectContext {
    /// 週日 ~1:00am ET 重認證窗:→ `Disconnected(WeeklyReauth)`,永不自動重連。
    WeeklyReauth,
    /// nightly restart 窗（Mon-Sat）:→ Backoff 但不計入 reconnect budget;首延遲=窗殘餘+grace。
    ScheduledRestart { first_delay: Duration },
    /// 一般斷線:走 transient 退避（消耗 budget）。
    Normal,
}

/// 以**注入 UTC 時鐘**判定斷線脈絡（America/New_York 本地時,DST 由 chrono-tz 解;fixture 全相對/
/// 凍結時鐘,禁硬編日期 time-bomb,設計 §1.4）。週日重認證優先於 nightly restart（週日不套 restart 窗）。
pub(crate) fn classify_disconnect_context(
    now_utc: DateTime<Utc>,
    cfg: &TwsSessionConfig,
) -> DisconnectContext {
    // UTC → America/New_York 本地時（DST 由 IANA tz 庫解,絕不手寫偏移）。
    let et = now_utc.with_timezone(&chrono_tz::America::New_York);
    let (hour, minute, second) = (et.hour(), et.minute(), et.second());

    // 週日重認證窗優先（永不自動重連;此判定壓過任何 restart 窗）。
    if et.weekday() == Weekday::Sun && cfg.weekly_reauth.contains(hour, minute) {
        return DisconnectContext::WeeklyReauth;
    }

    // nightly restart 窗:auto-restart 只覆蓋 Mon-Sat;窗未配置 → 無感知（不猜默認時刻,§8-U4）。
    if et.weekday() != Weekday::Sun {
        if let Some(w) = cfg.restart_window {
            if let Some(first_delay) = w.remaining_within(hour, minute, second, cfg.scheduled_grace)
            {
                return DisconnectContext::ScheduledRestart { first_delay };
            }
        }
    }

    DisconnectContext::Normal
}

// ===========================================================================
// (e) FSM（設計 §1.1 六態 + §1.2 轉移表;未列組合=IllegalTransition typed + debug_assert）
// ===========================================================================

/// `Disconnected` 態的停機原因（設計 §1.1 `Disconnected(halt_reason)`）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum HaltReason {
    /// 初始未連線。
    Initial,
    /// permit 被拒（envelope 前置未滿足;production 恆此路）。
    EnvelopeRequired,
    /// session 級致命（見 `FatalCause`）;不自動重試（reconnect=新活化）。
    SessionFatal(FatalCause),
    /// 週日 ~1:00am ET 重認證窗:人工事務,永不自動重連。
    WeeklyReauth,
    /// 重連預算耗盡（> max_reconnect_attempts）:不無限重試。
    ReconnectBudgetExhausted,
    /// kill-switch epoch 變更 / operator stop（W8 接真 epoch）。
    Halted,
}

impl HaltReason {
    /// 是否可（在取得新 permit 後）自動重連。`SessionFatal`/`WeeklyReauth`/
    /// `ReconnectBudgetExhausted`/`Halted` = **結構性終態**（永不自動重連,除非 operator
    /// `reset_for_reactivation` 顯式重置=新活化事務）。
    fn is_reconnectable(self) -> bool {
        matches!(self, HaltReason::Initial | HaltReason::EnvelopeRequired)
    }
}

/// session 級致命的細因（`Disconnected(SessionFatal(_))` payload）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum FatalCause {
    /// ACK server_version < `PINNED_MIN_SERVER_VERSION`（客戶端自檢 fail-closed）。
    ServerVersionTooOld,
    /// managedAccounts 前綴實檢發現非 paper session。
    NonPaperSession,
    /// 326:client id 已占用→拒新連線（非踢舊;設計 §2.4 現勘）。
    DuplicateClientIdRejected,
    /// 握手 / 活 session 收到真錯誤 ERR_MSG（code < 2100,如 502/504/1300）。
    GatewayError(i64),
}

/// 就緒態 payload（Ready / Degraded 共用;設計 §1.1 + 心跳簿記）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct ReadyState {
    pub server_version: i32,
    pub connection_time_raw: String,
    pub paper_confirmed: bool,
    pub next_valid_id: i64,
    /// 最後收到任何 frame / 心跳回覆的注入 ms（telemetry / liveness）。
    pub last_activity_ms: u64,
    /// 已送 reqCurrentTime 等回覆的起始 ms（`Some` = 等回覆中;`None` = 無在途心跳）。
    pub awaiting_reply_since: Option<u64>,
    /// 連續心跳 miss 計數（回覆到達歸零）。
    pub consecutive_misses: u32,
    /// 下次心跳到期的注入 ms。
    pub next_heartbeat_due_ms: u64,
}

/// FSM 六態（設計 §1.1;rich payload——engine-private,經 `label()` 投影回 types IPC 契約）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum SessionState {
    /// 未連線（帶 halt_reason）。初始態。
    Disconnected { reason: HaltReason },
    /// transport 建立中。
    Connecting,
    /// 握手 + version pin + paper 實檢中。
    Handshaking,
    /// 就緒。
    Ready(ReadyState),
    /// 心跳連續 miss 標記劣化（socket 未斷）。
    Degraded(ReadyState),
    /// 退避中。`scheduled` = 排程重啟窗斷線（不計 budget）。
    Backoff {
        attempt_n: u32,
        next_delay: Duration,
        scheduled: bool,
        entered_at_ms: u64,
    },
}

impl SessionState {
    /// 投影回 types IPC label 契約（W4 IPC 消費面;rich payload 不跨 IPC,只送 label）。
    pub(crate) fn label(&self) -> IbkrTwsSessionStateV1 {
        match self {
            SessionState::Disconnected { .. } => IbkrTwsSessionStateV1::Disconnected,
            SessionState::Connecting => IbkrTwsSessionStateV1::Connecting,
            SessionState::Handshaking => IbkrTwsSessionStateV1::Handshaking,
            SessionState::Ready(_) => IbkrTwsSessionStateV1::Ready,
            SessionState::Degraded(_) => IbkrTwsSessionStateV1::Degraded,
            SessionState::Backoff { .. } => IbkrTwsSessionStateV1::Backoff,
        }
    }
}

/// 握手完成的產物（S4 fake-TWS / TCP driver 讀完 ACK+15+9 後餵入;S2 由測試/manager 注入）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct HandshakeOutcome {
    pub server_version: i32,
    pub connection_time_raw: String,
    pub paper_confirmed: bool,
    pub next_valid_id: i64,
}

/// 六態可恢復 session 狀態機（設計 §1;純同步,注入時鐘/RNG;無 socket/無 async）。
pub(crate) struct SessionFsm {
    state: SessionState,
    config: TwsSessionConfig,
    /// 連續重連嘗試計數（Ready 成功歸零;每入 transient Backoff +1;scheduled Backoff 不 +1）。
    reconnect_attempt: u32,
}

impl SessionFsm {
    /// 新 FSM,起於 `Disconnected(Initial)`。
    pub(crate) fn new(config: TwsSessionConfig) -> Self {
        Self {
            state: SessionState::Disconnected {
                reason: HaltReason::Initial,
            },
            config,
            reconnect_attempt: 0,
        }
    }

    pub(crate) fn state(&self) -> &SessionState {
        &self.state
    }

    pub(crate) fn ipc_state(&self) -> IbkrTwsSessionStateV1 {
        self.state.label()
    }

    pub(crate) fn reconnect_attempt(&self) -> u32 {
        self.reconnect_attempt
    }

    /// 是否為**結構性終態**（`Disconnected` 且 halt_reason 不可自動重連:SessionFatal / WeeklyReauth /
    /// ReconnectBudgetExhausted / Halted）。manager **必須**先查此再決定是否 `attempt_connect`——終態
    /// 不得自動重連（唯一離開途徑=`reset_for_reactivation`=新活化事務）。
    pub(crate) fn is_terminal(&self) -> bool {
        matches!(
            &self.state,
            SessionState::Disconnected { reason } if !reason.is_reconnectable()
        )
    }

    /// 非法轉移:debug_assert + typed `IllegalTransition` 事件,**狀態不變**（設計 §1.2）。
    fn illegal(&self) -> Vec<IbkrTwsSessionEventV1> {
        debug_assert!(false, "illegal transition from {:?}", self.state);
        vec![IbkrTwsSessionEventV1::IllegalTransition]
    }

    // ---- connect 邊界（INV-1）----

    /// permit 授予（token 單次消費:move 入本 fn 即 drop,不 Clone/不緩存）。合法起態=
    /// `Disconnected(可重連)` 或 `Backoff`（設計 §1.2 row 1 / row「Backoff→Connecting」）。
    pub(crate) fn on_permit_granted(
        &mut self,
        token: PermitToken,
        _now_ms: u64,
    ) -> Vec<IbkrTwsSessionEventV1> {
        // token move 入,函數結束即 drop——結構上單次消費（PermitToken 非 Clone）。
        let PermitToken { _seal: () } = token;
        let ok = match &self.state {
            SessionState::Disconnected { reason } => reason.is_reconnectable(),
            SessionState::Backoff { .. } => true,
            _ => false,
        };
        if !ok {
            return self.illegal();
        }
        self.state = SessionState::Connecting;
        vec![IbkrTwsSessionEventV1::ConnectPermitGranted]
    }

    /// permit 被拒（production 恆此路）:合法起態=`Disconnected(可重連)` 或 `Backoff` →
    /// `Disconnected(EnvelopeRequired)`,不重試（設計 §1.2 row 2）。
    pub(crate) fn on_permit_denied(&mut self) -> Vec<IbkrTwsSessionEventV1> {
        let ok = match &self.state {
            SessionState::Disconnected { reason } => reason.is_reconnectable(),
            SessionState::Backoff { .. } => true,
            _ => false,
        };
        if !ok {
            return self.illegal();
        }
        self.state = SessionState::Disconnected {
            reason: HaltReason::EnvelopeRequired,
        };
        vec![IbkrTwsSessionEventV1::EnvelopeRequired]
    }

    // ---- Connecting / Handshaking ----

    /// transport 建立 → Handshaking（fake 域=duplex 注入;TCP 域=S8）。合法起態=`Connecting`。
    pub(crate) fn on_transport_established(&mut self, _now_ms: u64) -> Vec<IbkrTwsSessionEventV1> {
        if !matches!(self.state, SessionState::Connecting) {
            return self.illegal();
        }
        self.state = SessionState::Handshaking;
        vec![]
    }

    /// connect timeout / refused → Backoff（transient）。合法起態=`Connecting`。
    pub(crate) fn on_connect_failed(
        &mut self,
        now_ms: u64,
        next_delay: Duration,
    ) -> Vec<IbkrTwsSessionEventV1> {
        if !matches!(self.state, SessionState::Connecting) {
            return self.illegal();
        }
        self.enter_backoff_transient(now_ms, next_delay)
    }

    /// 握手完成 → Ready（缺 version pin / 非 paper → session-fatal,fail-closed;設計 §1.2）。
    /// 合法起態=`Handshaking`。
    pub(crate) fn on_handshake_result(
        &mut self,
        outcome: HandshakeOutcome,
        now_ms: u64,
    ) -> Vec<IbkrTwsSessionEventV1> {
        if !matches!(self.state, SessionState::Handshaking) {
            return self.illegal();
        }
        // 客戶端自檢 fail-closed:version < pin → session-fatal（不依賴 server 拒絕行為,§2.2）。
        if outcome.server_version < PINNED_MIN_SERVER_VERSION {
            self.state = SessionState::Disconnected {
                reason: HaltReason::SessionFatal(FatalCause::ServerVersionTooOld),
            };
            return vec![IbkrTwsSessionEventV1::ServerVersionTooOld];
        }
        // paper 前綴實檢未過 → session-fatal（絕不對 live session 續讀;B1 紀律）。
        if !outcome.paper_confirmed {
            self.state = SessionState::Disconnected {
                reason: HaltReason::SessionFatal(FatalCause::NonPaperSession),
            };
            return vec![IbkrTwsSessionEventV1::NonPaperSessionDetected];
        }
        // 成功 → reconnect budget 歸零。
        self.reconnect_attempt = 0;
        self.state = SessionState::Ready(ReadyState {
            server_version: outcome.server_version,
            connection_time_raw: outcome.connection_time_raw,
            paper_confirmed: true,
            next_valid_id: outcome.next_valid_id,
            last_activity_ms: now_ms,
            awaiting_reply_since: None,
            consecutive_misses: 0,
            next_heartbeat_due_ms: now_ms + self.config.heartbeat_interval.as_millis() as u64,
        });
        vec![]
    }

    /// 握手期 IO err / timeout / EOF → Backoff（transient）。合法起態=`Handshaking`。
    pub(crate) fn on_handshake_transient(
        &mut self,
        now_ms: u64,
        next_delay: Duration,
    ) -> Vec<IbkrTwsSessionEventV1> {
        if !matches!(self.state, SessionState::Handshaking) {
            return self.illegal();
        }
        self.enter_backoff_transient(now_ms, next_delay)
    }

    /// 握手期致命（NonPaper / ServerVersionTooOld / fatal ERR<2100）→ `Disconnected(SessionFatal)`,
    /// 不自動重試。合法起態=`Handshaking`。
    pub(crate) fn on_handshake_fatal(
        &mut self,
        cause: FatalCause,
        _now_ms: u64,
    ) -> Vec<IbkrTwsSessionEventV1> {
        if !matches!(self.state, SessionState::Handshaking) {
            return self.illegal();
        }
        let events = fatal_events(cause);
        self.state = SessionState::Disconnected {
            reason: HaltReason::SessionFatal(cause),
        };
        events
    }

    // ---- 活 session：錯誤 frame / IO 斷 / 心跳 ----

    /// 活 session（Ready/Degraded）收到 ERR_MSG frame 的分類裁決（設計 §2.4 + **N2**）。
    /// class 由呼叫端以 `IbkrTwsErrorClassV1::conservative(code)` 供給。
    ///
    /// **N2**（farm-blip 2103/2105/2110/1100/1101/1102 = `Transient`）:在活 session 為**資訊性**
    /// （通常隨即被 2104/2106 恢復）——**不觸發過早 reconnect/Backoff**,狀態不變;需真 IO 斷 /
    /// 心跳 miss 才轉 Backoff。`SessionFatal` → Disconnected;`Pacing` 留 S3 governor;`Info`/
    /// `Entitlement` no-op。
    pub(crate) fn on_error_frame(
        &mut self,
        code: i64,
        class: IbkrTwsErrorClassV1,
        _now_ms: u64,
    ) -> Vec<IbkrTwsSessionEventV1> {
        if !matches!(
            self.state,
            SessionState::Ready(_) | SessionState::Degraded(_)
        ) {
            return self.illegal();
        }
        match class {
            // N2:farm-blip = 資訊性,不轉移（防過早 reconnect）。
            IbkrTwsErrorClassV1::Transient => vec![],
            // per-request（W6 訂閱表消費）/ ≥2100 info 地板:不進 FSM。
            IbkrTwsErrorClassV1::Entitlement | IbkrTwsErrorClassV1::Info => vec![],
            // TODO(S3):pacing governor（error 100 三次違規斷 session）;S2 governor 未接,不轉移。
            IbkrTwsErrorClassV1::Pacing => vec![],
            // session 級致命:326=拒新連線 typed;其餘 code<2100 → GatewayError。
            IbkrTwsErrorClassV1::SessionFatal
            | IbkrTwsErrorClassV1::OrderReject
            | IbkrTwsErrorClassV1::Unknown => {
                let cause = if code == IB_ERR_DUPLICATE_CLIENT_ID {
                    FatalCause::DuplicateClientIdRejected
                } else {
                    FatalCause::GatewayError(code)
                };
                let events = fatal_events(cause);
                self.state = SessionState::Disconnected {
                    reason: HaltReason::SessionFatal(cause),
                };
                events
            }
        }
    }

    /// IO err / EOF / timeout（真傳輸斷）→ Backoff（transient）。合法起態=`Ready`/`Degraded`。
    pub(crate) fn on_io_drop(
        &mut self,
        now_ms: u64,
        next_delay: Duration,
    ) -> Vec<IbkrTwsSessionEventV1> {
        if !matches!(
            self.state,
            SessionState::Ready(_) | SessionState::Degraded(_)
        ) {
            return self.illegal();
        }
        self.enter_backoff_transient(now_ms, next_delay)
    }

    /// `DuplicateClientIdKick`（§2.4 現勘後的踢線形態,若未來現勘定案）→ session-fatal。合法起態=
    /// `Ready`/`Degraded`。W3 主路徑走 `on_error_frame(326,..)`;此為顯式踢線入口。
    pub(crate) fn on_duplicate_client_id(&mut self, _now_ms: u64) -> Vec<IbkrTwsSessionEventV1> {
        if !matches!(
            self.state,
            SessionState::Ready(_) | SessionState::Degraded(_)
        ) {
            return self.illegal();
        }
        self.state = SessionState::Disconnected {
            reason: HaltReason::SessionFatal(FatalCause::DuplicateClientIdRejected),
        };
        vec![IbkrTwsSessionEventV1::DuplicateClientIdRejected]
    }

    // ---- 心跳簿記 ----

    /// 心跳是否到期需送（在途無等待 且 now ≥ 下次到期）。合法起態=`Ready`/`Degraded`。
    pub(crate) fn heartbeat_send_due(&self, now_ms: u64) -> bool {
        match &self.state {
            SessionState::Ready(rs) | SessionState::Degraded(rs) => {
                rs.awaiting_reply_since.is_none() && now_ms >= rs.next_heartbeat_due_ms
            }
            _ => false,
        }
    }

    /// 記錄已送出 reqCurrentTime（起等回覆;下次到期推後一個 interval）。
    pub(crate) fn mark_heartbeat_sent(&mut self, now_ms: u64) {
        if let SessionState::Ready(rs) | SessionState::Degraded(rs) = &mut self.state {
            rs.awaiting_reply_since = Some(now_ms);
            rs.next_heartbeat_due_ms = now_ms + self.config.heartbeat_interval.as_millis() as u64;
        }
    }

    /// 心跳回覆是否已逾時（在途等待 且 now-since ≥ heartbeat_timeout）。
    pub(crate) fn heartbeat_reply_overdue(&self, now_ms: u64) -> bool {
        match &self.state {
            SessionState::Ready(rs) | SessionState::Degraded(rs) => match rs.awaiting_reply_since {
                Some(since) => {
                    now_ms.saturating_sub(since) >= self.config.heartbeat_timeout.as_millis() as u64
                }
                None => false,
            },
            _ => false,
        }
    }

    /// 下一次 miss 是否會觸發 drop（→ Backoff）。manager 用此決定是否需算 backoff delay（耗 RNG）。
    pub(crate) fn heartbeat_miss_would_drop(&self) -> bool {
        match &self.state {
            SessionState::Ready(rs) | SessionState::Degraded(rs) => {
                rs.consecutive_misses + 1 >= self.config.drop_after_misses
            }
            _ => false,
        }
    }

    /// 心跳回覆到達 → Degraded 恢復為 Ready;miss 歸零。合法起態=`Ready`/`Degraded`。
    pub(crate) fn on_heartbeat_reply(&mut self, now_ms: u64) -> Vec<IbkrTwsSessionEventV1> {
        let mut rs = match &self.state {
            SessionState::Ready(rs) | SessionState::Degraded(rs) => rs.clone(),
            _ => return self.illegal(),
        };
        rs.awaiting_reply_since = None;
        rs.consecutive_misses = 0;
        rs.last_activity_ms = now_ms;
        rs.next_heartbeat_due_ms = now_ms + self.config.heartbeat_interval.as_millis() as u64;
        self.state = SessionState::Ready(rs); // Degraded→Ready 恢復
        vec![]
    }

    /// 心跳 miss（回覆逾時）:miss+1 → 達 degraded 門檻 → Degraded;達 drop 門檻 → Backoff。
    /// `next_delay` 只在 drop 時被消費（manager 於 `heartbeat_miss_would_drop()` 為真才算真 RNG delay,
    /// 否則傳 `Duration::ZERO`,避免非 drop miss 空耗 RNG）。合法起態=`Ready`/`Degraded`。
    pub(crate) fn on_heartbeat_miss(
        &mut self,
        now_ms: u64,
        next_delay: Duration,
    ) -> Vec<IbkrTwsSessionEventV1> {
        let mut rs = match &self.state {
            SessionState::Ready(rs) | SessionState::Degraded(rs) => rs.clone(),
            _ => return self.illegal(),
        };
        rs.awaiting_reply_since = None; // 清在途,令下次心跳可再送
        rs.next_heartbeat_due_ms = now_ms + self.config.heartbeat_interval.as_millis() as u64;
        rs.consecutive_misses += 1;
        if rs.consecutive_misses >= self.config.drop_after_misses {
            // transport 視為斷 → transient Backoff（消耗 budget）。
            return self.enter_backoff_transient(now_ms, next_delay);
        }
        if rs.consecutive_misses >= self.config.degraded_after_misses {
            self.state = SessionState::Degraded(rs);
        } else {
            self.state = SessionState::Ready(rs);
        }
        vec![]
    }

    // ---- 排程感知 ----

    /// 排程重啟窗內斷線 → Backoff **但不計 reconnect budget**;首延遲=窗殘餘+grace（設計 §1.4）。
    /// 合法起態=`Ready`/`Degraded`。
    pub(crate) fn on_scheduled_restart_disconnect(
        &mut self,
        now_ms: u64,
        first_delay: Duration,
    ) -> Vec<IbkrTwsSessionEventV1> {
        if !matches!(
            self.state,
            SessionState::Ready(_) | SessionState::Degraded(_)
        ) {
            return self.illegal();
        }
        self.state = SessionState::Backoff {
            attempt_n: self.reconnect_attempt, // 不 +1:排程斷線不吃 budget
            next_delay: first_delay,
            scheduled: true,
            entered_at_ms: now_ms,
        };
        vec![IbkrTwsSessionEventV1::ScheduledRestartDisconnect]
    }

    /// 週日重認證窗判定 → `Disconnected(WeeklyReauth)`,永不自動重連（設計 §1.4）。合法起態=
    /// `Ready`/`Degraded`。
    pub(crate) fn on_weekly_reauth(&mut self) -> Vec<IbkrTwsSessionEventV1> {
        if !matches!(
            self.state,
            SessionState::Ready(_) | SessionState::Degraded(_)
        ) {
            return self.illegal();
        }
        self.state = SessionState::Disconnected {
            reason: HaltReason::WeeklyReauth,
        };
        vec![IbkrTwsSessionEventV1::SessionExpiredWeeklyReauth]
    }

    // ---- 停機 / 重置 ----

    /// kill-switch epoch 變更 / operator stop → `Disconnected(Halted)`。合法起態=**任意**
    /// （設計 §1.2 「任意 | kill-switch | Disconnected(Halted)」）。
    pub(crate) fn on_halt(&mut self) -> Vec<IbkrTwsSessionEventV1> {
        self.state = SessionState::Disconnected {
            reason: HaltReason::Halted,
        };
        vec![IbkrTwsSessionEventV1::Halted]
    }

    /// operator 顯式重置為 `Disconnected(Initial)`（=新活化事務;WeeklyReauth/Fatal/Exhausted/Halted
    /// 等終態後,唯一離開途徑）。清 reconnect budget。**非自動**——由 operator/W8 活化流程呼叫。
    pub(crate) fn reset_for_reactivation(&mut self) {
        self.state = SessionState::Disconnected {
            reason: HaltReason::Initial,
        };
        self.reconnect_attempt = 0;
    }

    // ---- backoff 到期查詢 ----

    /// Backoff 延遲是否已到期（now ≥ entered_at + next_delay）。非 Backoff 態回 false。
    pub(crate) fn backoff_elapsed(&self, now_ms: u64) -> bool {
        match &self.state {
            SessionState::Backoff {
                next_delay,
                entered_at_ms,
                ..
            } => now_ms.saturating_sub(*entered_at_ms) >= next_delay.as_millis() as u64,
            _ => false,
        }
    }

    // ---- 內部：進 transient Backoff（消耗 budget;超上限 → Exhausted）----

    fn enter_backoff_transient(
        &mut self,
        now_ms: u64,
        next_delay: Duration,
    ) -> Vec<IbkrTwsSessionEventV1> {
        self.reconnect_attempt += 1;
        if self.reconnect_attempt > self.config.max_reconnect_attempts {
            self.state = SessionState::Disconnected {
                reason: HaltReason::ReconnectBudgetExhausted,
            };
            return vec![IbkrTwsSessionEventV1::ReconnectBudgetExhausted];
        }
        self.state = SessionState::Backoff {
            attempt_n: self.reconnect_attempt,
            next_delay,
            scheduled: false,
            entered_at_ms: now_ms,
        };
        vec![]
    }
}

/// session-fatal cause → typed 事件（無對應 contract 事件者回空;GatewayError 無 IPC 事件,以 state
/// halt_reason 承載）。
fn fatal_events(cause: FatalCause) -> Vec<IbkrTwsSessionEventV1> {
    match cause {
        FatalCause::ServerVersionTooOld => vec![IbkrTwsSessionEventV1::ServerVersionTooOld],
        FatalCause::NonPaperSession => vec![IbkrTwsSessionEventV1::NonPaperSessionDetected],
        FatalCause::DuplicateClientIdRejected => {
            vec![IbkrTwsSessionEventV1::DuplicateClientIdRejected]
        }
        FatalCause::GatewayError(_) => vec![],
    }
}

// ===========================================================================
// (f) manager（**INV-1 守衛錨點**:持具體 `EnvelopeRequiredStub`;每次 attempt 重新 check()）
// ===========================================================================

/// session manager:驅動 FSM 的 connect 邊界。**持具體型別 `EnvelopeRequiredStub`**（非 dyn / 非
/// 泛型 permit 參數;INV-1 守衛錨點,設計 §1.5/§10）。每次嘗試離開 Disconnected/Backoff 都重新
/// `permit.check()` 取新 token（禁緩存 permit）;production stub 恆拒 → 恆撞 EnvelopeRequired 停在
/// Disconnected。TODO(S4):真 transport factory（fake duplex）注入後,自動重連在測試域走通。
pub(crate) struct TwsSessionManager {
    fsm: SessionFsm,
    /// **具體型別**（INV-1）:production 唯一 permit provider,恆拒。
    permit: EnvelopeRequiredStub,
    rng: EntropyJitterRng,
    config: TwsSessionConfig,
}

impl TwsSessionManager {
    pub(crate) fn new(config: TwsSessionConfig) -> Self {
        Self {
            fsm: SessionFsm::new(config.clone()),
            permit: EnvelopeRequiredStub,
            rng: EntropyJitterRng::new(),
            config,
        }
    }

    pub(crate) fn state(&self) -> &SessionState {
        self.fsm.state()
    }

    pub(crate) fn ipc_state(&self) -> IbkrTwsSessionStateV1 {
        self.fsm.ipc_state()
    }

    /// 嘗試連線:**每次都重新 `permit.check()`**（禁緩存;INV-1 轉移表「Backoff→Connecting 每次重驗」）。
    /// production 恆 `Err(EnvelopeRequired)` → FSM 停 `Disconnected(EnvelopeRequired)`。
    pub(crate) fn attempt_connect(&mut self, now_ms: u64) -> Vec<IbkrTwsSessionEventV1> {
        // 硬化 terminal 前置（E2-F1）:結構性終態（SessionFatal/WeeklyReauth/Exhausted/Halted）永不
        // 自動重連——自我強制此不變量,避免 S4 driver 於終態誤呼叫觸 FSM 非法轉移 debug_assert。
        if self.fsm.is_terminal() {
            return vec![];
        }
        match self.permit.check() {
            Ok(token) => self.fsm.on_permit_granted(token, now_ms),
            Err(ConnectDenied::EnvelopeRequired) => self.fsm.on_permit_denied(),
        }
    }

    /// kill-switch / operator stop → `Disconnected(Halted)`（終態）。供 W8 kill-switch 接線;S2 亦供
    /// 測試驅動 manager 至終態以驗 `attempt_connect` 的 terminal 前置。
    pub(crate) fn halt(&mut self) -> Vec<IbkrTwsSessionEventV1> {
        self.fsm.on_halt()
    }

    /// 計算下次 transient backoff 延遲（full jitter + 注入 RNG;attempt=下一次嘗試序）。
    /// TODO(S4):driver 迴圈在真斷線點呼叫此並餵 FSM。
    pub(crate) fn next_transient_backoff_delay(&mut self) -> Duration {
        full_jitter_delay(
            &self.config,
            self.fsm.reconnect_attempt() + 1,
            &mut self.rng,
        )
    }
}

#[cfg(test)]
#[path = "ibkr_tws_session_tests.rs"]
mod tests;
