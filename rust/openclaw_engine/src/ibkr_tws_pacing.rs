//! MODULE_NOTE
//! 模塊用途：IBKR **W3 TWS pacing governor**（W3-S3;設計 §3 全部）。所有出站 framed 訊息的
//!   **單一出口**——主 msg-rate token bucket（`rate = market_data_lines ÷ 2` msg/s）+ 獨立
//!   historical bucket（IB 現勘四規則）+ subscription lines 併發配額 + **有界排隊裁決**
//!   （bounded FIFO,溢出/逾時即拒,禁無界排隊=OOM 教訓、禁 silent drop）+ IB error-100
//!   三次違規斷 session 的 strike 計數。消費 S2 的心跳出站（`TwsSessionManager` 接線）。
//! 主要區段：
//!   - (a) config：`PacingConfig`（lines / queue_timeout / historical 四規則閾值 / strike limit;
//!     參數禁假功能——每項真讀取生效,有對應測試證明改參數→行為變化）。IB 現勘常數為 default。
//!   - (b) 單一出口證明：`OutboundGrant`（**非 Clone/非 Copy**,構造子 `mint` **模塊私有**——
//!     唯 governor 放行時鑄造。S4 transport `send_framed(grant, ..)` by-value 消費 → 任何出站
//!     framed 訊息**編譯期**必經 governor,無 grant 無法送。與 S2 `PermitToken` 同構）。
//!   - (c) 主 token bucket：`TokenBucket`（milli-token 定點整數,注入時鐘 refill;burst=1 秒額度）。
//!   - (d) historical limiter：`HistoricalLimiter`（60req/600s + BID_ASK×2 + 15s identical-dedup
//!     + same-(contract,exchange,ticktype) 2s<6;皆滑窗,由 rule-a 60/600 天然有界=OOM-safe）。
//!   - (e) lines 配額：`acquire_line/release_line` 計數器（併發非速率;上限=market_data_lines;
//!     **TODO(W6)** 真消費者=訂閱表,S3 只立計數器+測試）。
//!   - (f) governor：`PacingGovernor`（submit/poll 有界排隊裁決 + strike 計數 + 觀測 getter）。
//! 依賴：`std::collections::VecDeque`、`std::time::Duration`、`thiserror`。**零 openclaw_types**
//!   （strike 門檻為 config;fatal-cause code 100 由 manager 側 `IB_ERR_MAX_MESSAGE_RATE` 承載）。
//! 硬邊界：
//!   - **無 socket / 無 I/O / 無 async**：純同步狀態機,注入時鐘（`now_ms`）。真 transport 送出
//!     （消費 `OutboundGrant`）是 S4 事。
//!   - **有界排隊不變量（OOM 教訓）**：佇列 cap=1 秒額度×2 結構性有界;逾時 500ms → 拒（非 drop）;
//!     order-verb 超限**直拒不排隊**（訂單延遲=語義謊言,重試權還呼叫端）。禁無界排隊、禁 silent drop。
//!   - **單一出口不變量**：`OutboundGrant::mint` 模塊私有 → ibkr_tws_pacing 外無法構造 grant →
//!     出站送出編譯期必經 governor。
//!   - **DCE 姿態（W4 起更新;W5-S0 comment-only 修正）**：W3 時代「整面零 production caller →
//!     被 linker DCE」已過時——W4 health emitter 經 `TwsSessionManager::pacing_observation()`
//!     消費本模塊,pacing 面**已隨 session 移出 DCE**（`ibkr_driver_absence_audit.sh` Part A
//!     正向斷言 session 符號 present;真 transport 面 `ibkr_tws_driver` 仍 production-DCE,
//!     同 audit Part B）。`#![allow(dead_code)]` 保留——非「藏 orphan」:W6 訂閱表 / S4
//!     transport 才接的面明標 `TODO(W6)`/`TODO(S4)`,僅測試消費的 item 在 default build
//!     dead 是設計使然。
//!   - Bybit crypto_perp 不變;無 DB migration;不擴 types 契約。

// intentional-DCE 姿態已於 W4 更新（見 MODULE_NOTE）：pacing 面經 health emitter →
// TwsSessionManager 有 production caller、隨 session 移出 DCE;allow 僅為 W6/S4 才接的
// 測試專屬 item 保留。與 session 檔頭對稱。
#![allow(dead_code)]

use std::collections::VecDeque;
use std::time::Duration;

// ===========================================================================
// (a) config（全 config 化;設計 §3;參數禁假功能——每項必真實被讀取、生效、可觀測）
// IB 現勘常數（2026-07-15,IBKR_TODO §8 U2/U6 已解入碼）為 default。
// 官方出典:https://interactivebrokers.github.io/tws-api/message_codes.html（pacing 章）。
// ===========================================================================

/// pacing 配置（設計 §3）。default = IB 2026-07-15 現勘常數;每欄真實驅動行為（見對應測試）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct PacingConfig {
    /// 帳戶 market data lines（IB 現勘 U6:無查詢 API,default 100,EA4 實測校準）。
    /// 主 msg-rate `rate = market_data_lines ÷ 2` msg/s;亦為 subscription lines 併發上限。
    pub market_data_lines: u32,
    /// 有界佇列排隊逾時（default 500ms;逾時 → `PacingBudgetExceeded` 拒呼叫端,非 silent drop）。
    pub queue_timeout: Duration,
    /// 歷史請求滑窗（IB 現勘 U2:60 req / 600s）。
    pub historical_window: Duration,
    /// 歷史滑窗成本上限（default 60;BID_ASK 請求成本×`historical_bid_ask_cost`）。
    pub historical_max_cost: u64,
    /// BID_ASK 歷史請求的成本倍數（IB 現勘 U2:×2）。
    pub historical_bid_ask_cost: u64,
    /// identical-request 去重窗（IB 現勘 U2:15s 內相同請求 → 拒）。
    pub historical_identical_dedup: Duration,
    /// same-(contract,exchange,ticktype) 突發窗（IB 現勘 U2:2s）。
    pub historical_same_key_window: Duration,
    /// same-key 突發門檻（IB 現勘 U2:2s 內「6 或更多」=違規 → 允許 ≤5,第 6 拒;default 6）。
    pub historical_same_key_limit: u64,
    /// IB error-100 斷 session 門檻（IB 現勘:三次違規斷 session;default 3）。
    pub ib_pacing_strike_limit: u32,
}

impl Default for PacingConfig {
    fn default() -> Self {
        Self {
            market_data_lines: 100,
            queue_timeout: Duration::from_millis(500),
            historical_window: Duration::from_secs(600),
            historical_max_cost: 60,
            historical_bid_ask_cost: 2,
            historical_identical_dedup: Duration::from_secs(15),
            historical_same_key_window: Duration::from_secs(2),
            historical_same_key_limit: 6,
            ib_pacing_strike_limit: 3,
        }
    }
}

impl PacingConfig {
    /// 主 msg-rate（msg/s）:`market_data_lines ÷ 2`,下限 1（避免 lines 過小致零速率 footgun;
    /// 整數截斷向下=更保守=pacing 安全）。IB 現勘語義:lines=100 → 50 msg/s。
    fn main_rate_per_sec(&self) -> u64 {
        ((self.market_data_lines as u64) / 2).max(1)
    }

    /// 有界佇列容量:1 秒額度×2（設計 §3;結構性有界=OOM-safe,禁無界排隊）。
    fn queue_cap(&self) -> usize {
        (self.main_rate_per_sec() * 2) as usize
    }
}

// ===========================================================================
// (b) 單一出口證明 OutboundGrant（設計 §3「所有出站 framed 訊息單一出口過 governor,無旁路」）
// ===========================================================================

/// **單一出口證明**:唯 `PacingGovernor` 放行（Admitted / poll-Admitted）時鑄造。**非 Clone /
/// 非 Copy**——S4 transport 的 `send_framed(grant: OutboundGrant, ..)` by-value 消費此 grant,故
/// 任何出站 framed 訊息**編譯期**必經 governor（無 grant 無法呼叫 send）。與 S2 `PermitToken`
/// 同構的結構性不變量。
///
/// `mint` **模塊私有**（非 `pub(crate)`）:ibkr_tws_pacing **模塊外**無法構造 grant——比 S2
/// `PermitToken`（`pub(crate) mint`）更嚴,因單一出口要求 grant 構造為 governor 獨佔。
/// **TODO(S4)**:consumer = transport `send_framed`;S3 只鑄造 + 回呼叫端（測試斷言其存在）。
pub(crate) struct OutboundGrant {
    /// 私有零大小封印:令 `OutboundGrant { .. }` literal 在模塊外不可構造。
    _seal: (),
}

impl OutboundGrant {
    /// **模塊私有**構造子（唯一鑄造點=governor 放行）。
    fn mint() -> Self {
        Self { _seal: () }
    }
}

// ===========================================================================
// (c) 主 token bucket（milli-token 定點整數;注入時鐘 refill;設計 §3 burst=1 秒額度）
// ===========================================================================

/// 1 token = `MILLI` milli-token（定點整數避免浮點;rate=50/s → 每 ms 補 50 milli-token,
/// 20ms 補 1 token,整數精確無小數漂移）。
const MILLI: u64 = 1000;

/// 主 msg-rate token bucket:注入時鐘 refill,扣 1 token/訊息。**注入 now_ms 單調不倒退由呼叫端
/// 保證**（同 wire `RollingWindow` 紀律）。
struct TokenBucket {
    /// burst 容量（milli-token;= rate_per_sec × MILLI = 1 秒額度）。
    capacity_milli: u64,
    /// 每 ms 補充量（milli-token;= rate_per_sec,因 MILLI/1000=1）。
    refill_milli_per_ms: u64,
    /// 當前 token（milli-token）。
    tokens_milli: u64,
    /// 上次 refill 的注入 ms。
    last_ms: u64,
}

impl TokenBucket {
    fn new(rate_per_sec: u64, now_ms: u64) -> Self {
        let capacity_milli = rate_per_sec.saturating_mul(MILLI);
        Self {
            capacity_milli,
            refill_milli_per_ms: rate_per_sec,
            tokens_milli: capacity_milli, // 起始滿桶（可立即 burst 1 秒額度）
            last_ms: now_ms,
        }
    }

    /// 依注入時鐘補充（elapsed×rate;封頂 capacity;elapsed=0 不動 last_ms 以保子 ms 精度）。
    fn refill(&mut self, now_ms: u64) {
        let elapsed = now_ms.saturating_sub(self.last_ms);
        if elapsed > 0 {
            let add = elapsed.saturating_mul(self.refill_milli_per_ms);
            self.tokens_milli = self
                .tokens_milli
                .saturating_add(add)
                .min(self.capacity_milli);
            self.last_ms = now_ms;
        }
    }

    /// 試扣一個 token（先 refill）。回是否扣得。
    fn try_take(&mut self, now_ms: u64) -> bool {
        self.refill(now_ms);
        if self.tokens_milli >= MILLI {
            self.tokens_milli -= MILLI;
            true
        } else {
            false
        }
    }

    /// 當前可用整數 token（觀測用;反映**上次 refill 後**狀態,不主動推進時鐘）。
    fn available(&self) -> u64 {
        self.tokens_milli / MILLI
    }
}

// ===========================================================================
// (d) historical limiter（IB 現勘 U2 四規則;滑窗由 rule-a 60/600 天然有界=OOM-safe）
// ===========================================================================

/// 歷史資料請求指紋（W6 訂閱/歷史請求路徑計算;S3 以 u64 指紋表示,零明文）。
/// **TODO(W6)**:真指紋由歷史請求編碼側計算（contract/exchange/tickType 雜湊）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct HistoricalRequest {
    /// BID_ASK 請求 → 60/600 窗成本×2（IB 現勘 U2）。
    pub bid_ask: bool,
    /// 完整請求指紋（15s identical-dedup 用）。
    pub identical_key: u64,
    /// (contract,exchange,tickType) 三元指紋（2s<6 突發規則用）。
    pub contract_exchange_ticktype: u64,
}

/// 歷史請求限速器（四規則,滑窗;注入時鐘)。**OOM-safe**:三個 deque 皆為 600s 窗活動子集,
/// 而 rule-a 天然封頂 60/600s → 總量 ≤ ~60 筆,無界增長不可能（禁無界結構,OOM 教訓）。
struct HistoricalLimiter {
    window_ms: u64,
    max_cost: u64,
    bid_ask_cost: u64,
    dedup_ms: u64,
    same_key_window_ms: u64,
    same_key_limit: u64,
    /// 60/600s 窗:(ts, cost)。
    window: VecDeque<(u64, u64)>,
    /// identical-dedup 窗:(ts, identical_key)。
    dedup: VecDeque<(u64, u64)>,
    /// same-key 突發窗:(ts, triple_key)。
    same_key: VecDeque<(u64, u64)>,
}

impl HistoricalLimiter {
    fn new(cfg: &PacingConfig) -> Self {
        Self {
            window_ms: cfg.historical_window.as_millis() as u64,
            max_cost: cfg.historical_max_cost,
            bid_ask_cost: cfg.historical_bid_ask_cost,
            dedup_ms: cfg.historical_identical_dedup.as_millis() as u64,
            same_key_window_ms: cfg.historical_same_key_window.as_millis() as u64,
            same_key_limit: cfg.historical_same_key_limit,
            window: VecDeque::new(),
            dedup: VecDeque::new(),
            same_key: VecDeque::new(),
        }
    }

    /// 逐出逾窗前端（ts + win ≤ now = 已滿一窗）。
    fn prune(deque: &mut VecDeque<(u64, u64)>, win_ms: u64, now_ms: u64) {
        while let Some(&(ts, _)) = deque.front() {
            if ts.saturating_add(win_ms) <= now_ms {
                deque.pop_front();
            } else {
                break;
            }
        }
    }

    /// 四規則裁決（通過即 commit,失敗不 commit）。檢查序:identical-dedup(c) → same-key(d) →
    /// 60/600 窗(a,含 BID_ASK×2 的 b);多規則同時違反時前者先報。
    fn try_admit(&mut self, req: &HistoricalRequest, now_ms: u64) -> Result<(), PacingReject> {
        Self::prune(&mut self.window, self.window_ms, now_ms);
        Self::prune(&mut self.dedup, self.dedup_ms, now_ms);
        Self::prune(&mut self.same_key, self.same_key_window_ms, now_ms);

        // rule c:15s 內相同 identical_key → 拒（identical-request dedup）。
        if self.dedup.iter().any(|&(_, k)| k == req.identical_key) {
            return Err(PacingReject::HistoricalDuplicate);
        }
        // rule d:2s 內 same-(contract,exchange,ticktype)「6 或更多」=違規 → 允許 ≤ limit-1。
        let same_count = self
            .same_key
            .iter()
            .filter(|&&(_, k)| k == req.contract_exchange_ticktype)
            .count() as u64;
        if same_count + 1 >= self.same_key_limit {
            return Err(PacingReject::HistoricalSameKeyBurst);
        }
        // rule a+b:60/600s 窗,BID_ASK 成本×2。
        let cost = if req.bid_ask { self.bid_ask_cost } else { 1 };
        let sum: u64 = self.window.iter().map(|&(_, c)| c).sum();
        if sum + cost > self.max_cost {
            return Err(PacingReject::HistoricalWindowExceeded);
        }

        // 全通過 → commit（三窗同記）。
        self.window.push_back((now_ms, cost));
        self.dedup.push_back((now_ms, req.identical_key));
        self.same_key
            .push_back((now_ms, req.contract_exchange_ticktype));
        Ok(())
    }
}

// ===========================================================================
// (f) governor 對外裁決型別 + strike 計數
// ===========================================================================

/// pacing 拒絕原因（typed;禁 silent drop——每次拒皆回具體原因給呼叫端）。W4 telemetry 消費。
#[derive(Debug, Clone, Copy, PartialEq, Eq, thiserror::Error)]
pub(crate) enum PacingReject {
    /// order-verb 主 bucket 超限:**直拒不排隊**（訂單延遲=語義謊言,重試權還呼叫端;設計 §3）。
    #[error("pacing reject: order verb over budget (no queue)")]
    OrderVerbNoBudget,
    /// 有界佇列已滿（cap=1 秒額度×2）:拒（禁無界排隊,OOM 教訓）。
    #[error("pacing reject: bounded queue full")]
    QueueFull,
    /// 排隊逾時被逐（poll 時 now-enqueued ≥ queue_timeout）→ 拒呼叫端。
    #[error("pacing reject: queue timeout exceeded")]
    QueueTimeout,
    /// 歷史 60req/600s 窗超限（BID_ASK 計成本×2）。
    #[error("pacing reject: historical 60/600s window exceeded")]
    HistoricalWindowExceeded,
    /// 歷史 identical-request 15s 去重命中。
    #[error("pacing reject: historical identical request within dedup window")]
    HistoricalDuplicate,
    /// 歷史 same-(contract,exchange,ticktype) 2s 內達 6+。
    #[error("pacing reject: historical same-key burst (6+ within 2s)")]
    HistoricalSameKeyBurst,
    /// subscription lines 併發配額耗盡（= market_data_lines）。
    #[error("pacing reject: subscription lines exhausted")]
    LinesExhausted,
}

/// IB error-100 strike 裁決（設計 §3:三次違規斷 session）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum StrikeVerdict {
    /// 已記一次違規,未達門檻（count = 已累計次數）。
    Recorded { count: u32 },
    /// 達門檻 → session 必須斷（manager 驅 FSM 至 SessionFatal）。
    SessionMustDrop,
}

/// submit 的即時裁決。
pub(crate) enum SubmitOutcome {
    /// 立即放行:token 已扣,`grant` 為單一出口證明。
    Admitted(OutboundGrant),
    /// 入有界佇列（driver 後續 `poll(now)` 取解決;non-order-verb 且主 bucket 空且佇列有位）。
    Queued(QueueTicket),
    /// 直接拒（見 `PacingReject`)。
    Rejected(PacingReject),
}

/// 佇列票(driver 用以關聯 `poll` 解決結果;單調遞增 id)。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct QueueTicket(u64);

impl QueueTicket {
    pub(crate) fn id(self) -> u64 {
        self.0
    }
}

/// `poll` 對佇列項的解決(driver 迴圈推進時鐘後取)。
pub(crate) enum QueueResolution {
    /// token 補足 → 放行(grant 為單一出口證明)。
    Admitted {
        ticket: QueueTicket,
        grant: OutboundGrant,
    },
    /// 排隊逾時 → 拒呼叫端(`PacingBudgetExceeded` 語義,非 silent drop)。
    TimedOut { ticket: QueueTicket },
}

/// governor 觀測快照(tokens / queue depth / reject 計數 / strike;設計 §3「export 給 W4 health
/// IPC」)。**TODO(W4)**:IPC 接線於 W4;S3 立 getter,tests + 未來 IPC 為消費者。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub(crate) struct PacingObservation {
    /// 累計放行(即時 + poll)。
    pub admitted: u64,
    /// 當前佇列深度。
    pub queue_depth: usize,
    /// 主 bucket 當前可用 token(上次 refill 後)。
    pub main_tokens_available: u64,
    /// 當前佔用的 subscription lines。
    pub lines_in_use: u32,
    /// IB error-100 已累計 strike。
    pub ib_pacing_strikes: u32,
    pub rejected_order_verb: u64,
    pub rejected_queue_full: u64,
    pub rejected_timeout: u64,
    pub rejected_historical: u64,
    pub rejected_lines: u64,
}

// ---------------------------------------------------------------------------
// 內部:佇列項 + strike 計數
// ---------------------------------------------------------------------------

struct QueuedItem {
    ticket: u64,
    enqueued_ms: u64,
}

struct StrikeCounter {
    count: u32,
    limit: u32,
}

impl StrikeCounter {
    fn record(&mut self) -> StrikeVerdict {
        self.count = self.count.saturating_add(1);
        if self.count >= self.limit {
            StrikeVerdict::SessionMustDrop
        } else {
            StrikeVerdict::Recorded { count: self.count }
        }
    }
}

// ===========================================================================
// (f) PacingGovernor(單一出口:主 bucket + historical + lines + 有界排隊 + strike + 觀測)
// ===========================================================================

/// pacing governor:所有出站 framed 訊息的單一出口(設計 §3)。純同步,注入時鐘。
pub(crate) struct PacingGovernor {
    config: PacingConfig,
    main_bucket: TokenBucket,
    hist: HistoricalLimiter,
    queue: VecDeque<QueuedItem>,
    queue_cap: usize,
    queue_timeout_ms: u64,
    next_ticket: u64,
    lines_in_use: u32,
    strikes: StrikeCounter,
    // 累計計數（觀測;live 欄 tokens/queue/lines/strikes 於 `observe()` 即時計算,不快取以免
    // 建構/閒置後讀到陳舊零值）。
    obs_admitted: u64,
    obs_rejected_order_verb: u64,
    obs_rejected_queue_full: u64,
    obs_rejected_timeout: u64,
    obs_rejected_historical: u64,
    obs_rejected_lines: u64,
}

impl PacingGovernor {
    pub(crate) fn new(config: PacingConfig, now_ms: u64) -> Self {
        let main_bucket = TokenBucket::new(config.main_rate_per_sec(), now_ms);
        Self {
            main_bucket,
            hist: HistoricalLimiter::new(&config),
            queue: VecDeque::new(),
            queue_cap: config.queue_cap(),
            queue_timeout_ms: config.queue_timeout.as_millis() as u64,
            next_ticket: 0,
            lines_in_use: 0,
            strikes: StrikeCounter {
                count: 0,
                limit: config.ib_pacing_strike_limit,
            },
            config,
            obs_admitted: 0,
            obs_rejected_order_verb: 0,
            obs_rejected_queue_full: 0,
            obs_rejected_timeout: 0,
            obs_rejected_historical: 0,
            obs_rejected_lines: 0,
        }
    }

    // ---- 出站裁決(單一出口)----

    /// 提交一則出站訊息求裁決。**不解決既有佇列項**（那是 `poll` 的職責;避免遺失他者的 ticket
    /// 解決）。FIFO 公平:佇列非空時新項一律入佇列(不搶排在前之項)。
    pub(crate) fn submit(&mut self, class: OutboundClass, now_ms: u64) -> SubmitOutcome {
        match class {
            OutboundClass::Heartbeat | OutboundClass::MarketData | OutboundClass::Control => {
                self.admit_or_queue(now_ms, false)
            }
            // order-verb:超限直拒不排隊(訂單延遲=語義謊言)。
            OutboundClass::OrderVerb => self.admit_or_queue(now_ms, true),
            OutboundClass::Historical(req) => {
                // 先過 historical 四規則(hard reject,不可排隊繞過);通過再走主 bucket。
                if let Err(r) = self.hist.try_admit(&req, now_ms) {
                    self.obs_rejected_historical += 1;
                    return SubmitOutcome::Rejected(r);
                }
                self.admit_or_queue(now_ms, false)
            }
        }
    }

    /// 主 bucket 放行 / 入有界佇列 / 拒。FIFO:僅「佇列空 ∧ 有 token」才即時放行。
    fn admit_or_queue(&mut self, now_ms: u64, is_order_verb: bool) -> SubmitOutcome {
        if self.queue.is_empty() && self.main_bucket.try_take(now_ms) {
            self.obs_admitted += 1;
            return SubmitOutcome::Admitted(OutboundGrant::mint());
        }
        if is_order_verb {
            self.obs_rejected_order_verb += 1;
            return SubmitOutcome::Rejected(PacingReject::OrderVerbNoBudget);
        }
        if self.queue.len() < self.queue_cap {
            let ticket = self.next_ticket;
            self.next_ticket += 1;
            self.queue.push_back(QueuedItem {
                ticket,
                enqueued_ms: now_ms,
            });
            return SubmitOutcome::Queued(QueueTicket(ticket));
        }
        // 有界佇列滿:拒(禁無界排隊,OOM 教訓)。
        self.obs_rejected_queue_full += 1;
        SubmitOutcome::Rejected(PacingReject::QueueFull)
    }

    /// driver 迴圈推進時鐘後呼叫:先逐出逾時前端(→ TimedOut 拒),再 FIFO 放行(token 足)。
    /// **逾時優先於放行**(排隊逾時=請求已陳舊,即使此刻 token 足也拒;設計 §3)。
    /// **TODO(S4)**:driver 迴圈每 tick 呼叫,對每個解決分派(Admitted→送、TimedOut→回拒)。
    pub(crate) fn poll(&mut self, now_ms: u64) -> Vec<QueueResolution> {
        let mut out = Vec::new();
        // 1) 逐出逾時前端(FIFO:前端最早入隊,前端未逾時則後續更不逾時)。
        while let Some(front) = self.queue.front() {
            if now_ms.saturating_sub(front.enqueued_ms) >= self.queue_timeout_ms {
                let item = self.queue.pop_front().expect("front just checked");
                self.obs_rejected_timeout += 1;
                out.push(QueueResolution::TimedOut {
                    ticket: QueueTicket(item.ticket),
                });
            } else {
                break;
            }
        }
        // 2) FIFO 放行(token 足則扣並鑄 grant)。
        while !self.queue.is_empty() {
            if self.main_bucket.try_take(now_ms) {
                let item = self.queue.pop_front().expect("non-empty just checked");
                self.obs_admitted += 1;
                out.push(QueueResolution::Admitted {
                    ticket: QueueTicket(item.ticket),
                    grant: OutboundGrant::mint(),
                });
            } else {
                break;
            }
        }
        out
    }

    // ---- subscription lines 併發配額(非速率;設計 §3)----

    /// 佔用一條 subscription line(上限=market_data_lines)。**TODO(W6)**:真呼叫端=訂閱表。
    pub(crate) fn acquire_line(&mut self) -> Result<(), PacingReject> {
        if self.lines_in_use >= self.config.market_data_lines {
            self.obs_rejected_lines += 1;
            return Err(PacingReject::LinesExhausted);
        }
        self.lines_in_use += 1;
        Ok(())
    }

    /// 釋放一條 subscription line(飽和減,不下溢)。**TODO(W6)**:真呼叫端=訂閱表。
    pub(crate) fn release_line(&mut self) {
        self.lines_in_use = self.lines_in_use.saturating_sub(1);
    }

    pub(crate) fn lines_in_use(&self) -> u32 {
        self.lines_in_use
    }

    // ---- IB error-100 strike(設計 §3:三次違規斷 session)----

    /// 記一次 IB error-100 pacing 違規;回是否須斷 session。manager 於收到 error 100 呼叫,
    /// `SessionMustDrop` 時驅 FSM 至 SessionFatal(GatewayError(100))。
    pub(crate) fn record_ib_pacing_violation(&mut self) -> StrikeVerdict {
        self.strikes.record()
    }

    // ---- 觀測(設計 §3「tokens/queue depth/reject 計數 export 給 W4 health IPC」)----

    /// 觀測快照。live 欄(tokens/queue depth/lines/strikes)即時計算(不快取→建構/閒置後不讀陳舊
    /// 零值);累計計數為 governor 生命週期內單調總量。**TODO(W4)**:IPC 接線於 W4;S3 立 getter。
    /// 注:`main_tokens_available` 反映**上次 refill 後**桶量(未主動推進時鐘;telemetry 語義)。
    pub(crate) fn observe(&self) -> PacingObservation {
        PacingObservation {
            admitted: self.obs_admitted,
            queue_depth: self.queue.len(),
            main_tokens_available: self.main_bucket.available(),
            lines_in_use: self.lines_in_use,
            ib_pacing_strikes: self.strikes.count,
            rejected_order_verb: self.obs_rejected_order_verb,
            rejected_queue_full: self.obs_rejected_queue_full,
            rejected_timeout: self.obs_rejected_timeout,
            rejected_historical: self.obs_rejected_historical,
            rejected_lines: self.obs_rejected_lines,
        }
    }
}

/// 出站訊息類別（單一出口分類;決定 bucket 消費 + 超限裁決）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum OutboundClass {
    /// 心跳 reqCurrentTime（1/30s;不豁免但幾乎不觸限;主 bucket,可排隊）。S2 心跳出站消費。
    Heartbeat,
    /// 握手控制訊息（START_API / 初次 reqCurrentTime;主 bucket,可排隊）。S4 driver 握手出站消費——
    /// **單一出口不變量**要求所有 API 訊息（含握手 control）過 governor（`API\0`+版本協商為連線
    /// preamble,pre-session 直寫、非 pacing-subject,不在此列;見 driver `send_framed` 咬合證明）。
    Control,
    /// 一般 msg-rate 出站（market data 訂閱請求等;主 bucket,可排隊）。**TODO(W6)** 真消費者。
    MarketData,
    /// 歷史資料請求（主 bucket + 獨立 historical 四規則;可排隊）。**TODO(W6)** 真消費者。
    Historical(HistoricalRequest),
    /// order-verb（W7;主 bucket,超限直拒不排隊）。**TODO(W7)** 真消費者。
    OrderVerb,
}

#[cfg(test)]
#[path = "ibkr_tws_pacing_tests.rs"]
mod tests;
