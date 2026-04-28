//! cost_edge_advisor wire types — status enum + state struct exposed via IPC.
//! cost_edge_advisor wire types — IPC 暴露的 status enum 與 state struct。
//!
//! MODULE_NOTE (EN): Schema mirrors PA RFC `2026-04-26--g3_09_cost_edge_ratio_design.md`
//!   §4.2 / §6.1. Status variants are exhaustively enumerated so downstream
//!   consumers (healthcheck [22], GUI dashboard, audit log) can branch
//!   without wildcard fallthroughs. Forward-compat: variant additions are
//!   minor breaks for serde JSON consumers — Phase B/C may add `Shadow` /
//!   `Gated` variants; downstream callers should treat unknown strings as
//!   `Anomaly`-equivalent (defensive default).
//!
//!   `CostEdgeAdvisorState` is the snapshot DTO returned to IPC; it is
//!   intentionally `Clone` + small (no large vectors / maps) so RwLock
//!   reads are cheap. Audit log + healthcheck format their own strings
//!   from this DTO — we do not push pretty-formatted strings inside the
//!   struct itself (keeps wire size bounded).
//!
//! MODULE_NOTE (中)：Schema 對齊 PA RFC §4.2 / §6.1。Status 列舉完整列出
//!   讓下游 consumer（healthcheck [22] / GUI dashboard / audit log）可
//!   wildcard-free 分支。Forward-compat：新增 variant 對 serde JSON
//!   consumer 屬 minor break — Phase B/C 可能加 `Shadow` / `Gated`，下游
//!   收到未知 string 應 fallback 為 `Anomaly`-equivalent（防禦預設）。
//!
//!   `CostEdgeAdvisorState` 是 IPC 回 DTO，刻意 Clone + 小（無大型 vec/map），
//!   讓 RwLock read 便宜。Audit log + healthcheck 各自從 DTO format 自己的
//!   字串，不在 struct 內塞已格式化字串（控 wire size）。

use serde::{Deserialize, Serialize};

/// G3-09 cost_edge_advisor status — 7-variant state machine.
///
/// EN: Variants are listed in the order an advisor traverses on a healthy
///   startup: Uninitialized → Disabled → WarmUp → OK → Trigger (and
///   sometimes back to OK as ratio recovers). `Stale` and `Anomaly` are
///   off-path failure modes that any state can transition into.
///
/// 中：variants 依健康啟動順序排列：Uninitialized → Disabled → WarmUp → OK
///   → Trigger（ratio 回升可回 OK）。`Stale` 與 `Anomaly` 為任何狀態都可
///   進入的故障模式。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum CostEdgeAdvisorStatus {
    /// Daemon never spawned (env-gate off or daemon spawn failed).
    /// Daemon 未 spawn（env-gate 關或 spawn 失敗）。
    Uninitialized,
    /// Daemon spawned but `RiskConfig.cost_edge.enabled = false`. Evaluation
    /// cycle short-circuits before reading H state — zero overhead beyond
    /// the cycle wake.
    /// Daemon 已 spawn 但 `RiskConfig.cost_edge.enabled=false`。Evaluation
    /// cycle 在讀 H state 前 short-circuit，僅 cycle wake 的最低負擔。
    Disabled,
    /// Advisor enabled but H5 `cost_edge_ratio` is `None` (data_days <
    /// `ADAPTIVE_MIN_DAYS=3` per Python `Layer2CostTracker`). Sample size
    /// insufficient — advisor refuses to opine (fail-closed: never trigger
    /// without data).
    /// Advisor 已啟用但 H5 `cost_edge_ratio=None`（data_days < 3）。樣本不足
    /// → fail-closed：無資料絕不 trigger。
    WarmUp,
    /// Healthy state: `ratio > trigger_threshold` (AI investment paying off
    /// or losses tolerable).
    /// 健康狀態：`ratio > trigger_threshold`（AI 投資回報 OK 或虧損可接受）。
    Ok,
    /// Trigger state: `ratio <= trigger_threshold` (AI burning cash beyond
    /// configured tolerance). Phase A: log + audit only. Phase B/C: shadow
    /// reject count + new-intent gate (deferred).
    /// Trigger 狀態：`ratio <= trigger_threshold`（AI 燒錢超容忍）。Phase A
    /// 僅 log + audit；Phase B/C 加 shadow + 新倉 gate（後續）。
    Trigger,
    /// H state cache stale (Python crash / poller stuck) — advisor refuses
    /// to opine on possibly-old data. Sticks last known `ratio` for
    /// observability but does not re-evaluate.
    /// H state cache 過期（Python crash / poller 卡死）→ advisor 拒絕對可能
    /// 過時資料下判斷；保留上次 `ratio` 供觀測但不重新 evaluate。
    Stale,
    /// `ratio` is NaN or Inf — data corruption / divide-by-zero leakage.
    /// Operator must investigate (healthcheck [22] FAIL on this state).
    /// `ratio` 為 NaN/Inf — 資料損毀或除零洩漏；operator 必查（healthcheck
    /// [22] 此狀態 FAIL）。
    Anomaly,
}

impl CostEdgeAdvisorStatus {
    /// Stable string representation for JSON wire / audit log.
    /// `Debug` derive could change with rustc bumps; this is byte-stable.
    /// 穩定字串表示（給 JSON wire / audit log）。`Debug` derive 可能隨 rustc
    /// 版本變動，本 fn byte-stable。
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Uninitialized => "Uninitialized",
            Self::Disabled => "Disabled",
            Self::WarmUp => "WarmUp",
            Self::Ok => "OK",
            Self::Trigger => "Trigger",
            Self::Stale => "Stale",
            Self::Anomaly => "Anomaly",
        }
    }
}

/// G3-09 cost_edge_advisor state snapshot — DTO returned by IPC handler.
///
/// EN: All fields are populated even in non-Trigger states for diagnostic
///   continuity (healthcheck [22] message printing, GUI display). Optional
///   fields (`ratio`) reflect the upstream H5 schema (None during WarmUp).
///   Timestamps are unix milliseconds for cross-language consistency
///   (Python ms, Rust ms — no nanosecond Rust special).
///
/// 中：所有欄位即使非 Trigger 狀態也填滿，方便 healthcheck / GUI 連續顯示。
///   Optional 欄位（`ratio`）對齊上游 H5 schema（WarmUp 時 None）。時間戳
///   用 unix 毫秒（跨語言一致，Python/Rust 都用 ms）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CostEdgeAdvisorState {
    /// Current advisor status (state machine head).
    /// 當前 advisor 狀態（state machine head）。
    pub status: CostEdgeAdvisorStatus,
    /// Last computed `cost_edge_ratio` if any. `None` during WarmUp /
    /// Uninitialized / Disabled or when h5 reported `None`.
    /// 最後計算的 `cost_edge_ratio`；WarmUp/Uninitialized/Disabled 或 h5
    /// 回 `None` 時為 `None`。
    pub ratio: Option<f64>,
    /// Threshold used for the last evaluation (echoed for audit completeness).
    /// 上次 evaluation 用的 threshold（audit 完整性 echo）。
    pub threshold: f64,
    /// `data_days` from upstream H5 snapshot (samples backing the ratio).
    /// 上游 H5 snapshot 的 `data_days`（支撐 ratio 的樣本量）。
    pub data_days: u32,
    /// 7-day AI spend echoed from H5 (USD).
    /// H5 echo 的 7d AI 花費（USD）。
    pub ai_spend_7d_usd: f64,
    /// 7-day paper PnL echoed from H5 (USD; per CLAUDE.md §二 #10 認知誠實
    /// note: this is paper / LiveDemo simulated, not realised live PnL).
    /// H5 echo 的 7d paper PnL（USD；CLAUDE.md §二 #10 認知誠實 note：是
    /// paper / LiveDemo 模擬而非實際 live PnL）。
    pub paper_pnl_7d_usd: f64,
    /// Unix ms when this state was computed (advisor-side).
    /// 此 state 在 advisor 端計算時的 unix 毫秒。
    pub last_eval_ms: i64,
    /// Unix ms when status first entered the current contiguous `Trigger`
    /// run (sticky across Trigger→Trigger cycles). `0` when status is not
    /// `Trigger`. Daemon enforces stickiness in mod.rs ~L240: pure
    /// `evaluate()` always returns `now_ms`; daemon overwrites with the
    /// previously stored timestamp on Trigger→Trigger cycles, preserves
    /// `now_ms` on the entering transition, and resets to `0` on exit.
    /// 進入當前 contiguous `Trigger` 區段的 unix 毫秒（Trigger→Trigger sticky）；
    /// 非 Trigger 時為 `0`。Daemon 在 mod.rs 約 L240 強制 sticky：pure
    /// `evaluate()` 永遠回 `now_ms`，daemon 於 Trigger→Trigger 覆寫為前次儲存值，
    /// 進入時保留 `now_ms`，退出時清 `0`。
    pub triggered_at_ms: i64,
}

impl CostEdgeAdvisorState {
    /// Default `Uninitialized` state — used at advisor construction before
    /// the first evaluation cycle, and as the env=0 IPC response.
    /// 預設 `Uninitialized` 狀態 — advisor 構造時與 env=0 IPC 回應用。
    pub fn uninitialized() -> Self {
        Self {
            status: CostEdgeAdvisorStatus::Uninitialized,
            ratio: None,
            threshold: 0.0,
            data_days: 0,
            ai_spend_7d_usd: 0.0,
            paper_pnl_7d_usd: 0.0,
            last_eval_ms: 0,
            triggered_at_ms: 0,
        }
    }

    /// Build a `Disabled` state with the configured threshold echoed for
    /// audit (operator may flip `enabled=false` after threshold tuning;
    /// echoing the threshold helps E4 regression).
    /// 建 `Disabled` state，echo 設定 threshold（operator 可能調 threshold 後
    /// 才 flip enabled=false；保留 threshold 助 E4 regression）。
    pub fn disabled(threshold: f64, last_eval_ms: i64) -> Self {
        Self {
            status: CostEdgeAdvisorStatus::Disabled,
            ratio: None,
            threshold,
            data_days: 0,
            ai_spend_7d_usd: 0.0,
            paper_pnl_7d_usd: 0.0,
            last_eval_ms,
            triggered_at_ms: 0,
        }
    }

    /// Build a `WarmUp` state with the current `data_days` (so caller can
    /// see how close we are to ADAPTIVE_MIN_DAYS=3).
    /// 建 `WarmUp` state 帶 `data_days`（讓 caller 看離 ADAPTIVE_MIN_DAYS=3
    /// 還差多少）。
    pub fn warm_up(threshold: f64, data_days: u32, last_eval_ms: i64) -> Self {
        Self {
            status: CostEdgeAdvisorStatus::WarmUp,
            ratio: None,
            threshold,
            data_days,
            ai_spend_7d_usd: 0.0,
            paper_pnl_7d_usd: 0.0,
            last_eval_ms,
            triggered_at_ms: 0,
        }
    }

    /// Build an `OK` state with full H5 echo for diagnostic continuity.
    /// 建 `OK` state 含完整 H5 echo（診斷連續性）。
    pub fn ok(
        ratio: f64,
        threshold: f64,
        data_days: u32,
        ai_spend_7d_usd: f64,
        paper_pnl_7d_usd: f64,
        last_eval_ms: i64,
    ) -> Self {
        Self {
            status: CostEdgeAdvisorStatus::Ok,
            ratio: Some(ratio),
            threshold,
            data_days,
            ai_spend_7d_usd,
            paper_pnl_7d_usd,
            last_eval_ms,
            triggered_at_ms: 0,
        }
    }

    /// Build a `Trigger` state with full H5 echo + transition timestamp.
    /// `triggered_at_ms` is set by the daemon on the OK→Trigger transition;
    /// passed through here so a single eval(...) call site can produce a
    /// fully-formed state.
    /// 建 `Trigger` state 含完整 H5 echo + 轉換時戳。`triggered_at_ms` 由 daemon
    /// 在 OK→Trigger 轉換時設定，這裡接收讓單一 eval(...) 點即可產出完整 state。
    pub fn trigger(
        ratio: f64,
        threshold: f64,
        data_days: u32,
        ai_spend_7d_usd: f64,
        paper_pnl_7d_usd: f64,
        last_eval_ms: i64,
        triggered_at_ms: i64,
    ) -> Self {
        Self {
            status: CostEdgeAdvisorStatus::Trigger,
            ratio: Some(ratio),
            threshold,
            data_days,
            ai_spend_7d_usd,
            paper_pnl_7d_usd,
            last_eval_ms,
            triggered_at_ms,
        }
    }

    /// Build a `Stale` state preserving last known ratio (sticky observability).
    /// 建 `Stale` state，保留上次 ratio（sticky observability）。
    pub fn stale(prev_ratio: Option<f64>, threshold: f64, last_eval_ms: i64) -> Self {
        Self {
            status: CostEdgeAdvisorStatus::Stale,
            ratio: prev_ratio,
            threshold,
            data_days: 0,
            ai_spend_7d_usd: 0.0,
            paper_pnl_7d_usd: 0.0,
            last_eval_ms,
            triggered_at_ms: 0,
        }
    }

    /// Build an `Anomaly` state with the offending ratio echoed for forensics.
    /// 建 `Anomaly` state，echo 觸發 ratio 供取證。
    pub fn anomaly(ratio: f64, threshold: f64, last_eval_ms: i64) -> Self {
        Self {
            status: CostEdgeAdvisorStatus::Anomaly,
            // Echo the offending ratio even though it's NaN/Inf — serde
            // serialises NaN/Inf as `null` by default which is OK for
            // observability. Healthcheck reports the status string +
            // surrounding fields rather than relying on ratio JSON value.
            // 即使 NaN/Inf 也 echo（serde 預設將 NaN/Inf 序列化為 `null`，
            // 觀察用足矣；healthcheck 看 status 字串+鄰近欄位非 ratio）。
            ratio: Some(ratio),
            threshold,
            data_days: 0,
            ai_spend_7d_usd: 0.0,
            paper_pnl_7d_usd: 0.0,
            last_eval_ms,
            triggered_at_ms: 0,
        }
    }
}

impl Default for CostEdgeAdvisorState {
    fn default() -> Self {
        Self::uninitialized()
    }
}
