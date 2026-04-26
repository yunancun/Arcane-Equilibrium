//! H State Cache wire types — H1-H5 + 5-Agent state snapshot structs that
//! Rust端 serde 解析 Python 透過 `query_h_state_full` IPC 推送的 payload。
//! 對應 PA design plan §5.2 schema（commit `7564d07`）。
//!
//! MODULE_NOTE (EN): These structs mirror the JSON dict Python's
//!   `build_h_state_full_response()` (in `app/h_state_query_handler.py`,
//!   to be authored by Sub-task B in parallel) emits. Phase 1 only wires
//!   the empty-shell shape — Phase 2-4 backfill real stats. All fields use
//!   `#[serde(default)]` so unknown / missing keys don't break parsing
//!   (forward-compat per PA §2 G7). The `AgentState.stats` deliberately
//!   uses `HashMap<String, i64>` so Phase 4 can extend without lock-step
//!   Rust deploy.
//!
//!   IMPORTANT — observability only:
//!   * Rust never WRITES H state. Python is SSOT.
//!   * Rust query path is purely advisory — it must NOT influence trading
//!     decisions (CLAUDE.md §二 原則 #3 / #4 / G5). Hot-path consumers
//!     (intent_processor / risk_gate) are NOT wired in Phase 1.
//!
//! MODULE_NOTE (中)：這些結構鏡射 Python `build_h_state_full_response()`
//!   （由並行的 Sub-task B 撰寫）emit 的 JSON dict。Phase 1 只接空殼，
//!   Phase 2-4 才回填真實 stats。所有欄位採 `#[serde(default)]`，未知 /
//!   缺失的鍵不會破壞 parsing（forward-compat 對應 PA §2 G7）。
//!   `AgentState.stats` 故意用 `HashMap<String, i64>`，Phase 4 可動態
//!   擴增不需 lock-step Rust 部署。
//!
//!   重要 — 純 observability：
//!   * Rust 永不 WRITE H 狀態。Python 為 SSOT。
//!   * Rust 查詢純 advisory — 不可影響交易決策（CLAUDE.md §二 原則 #3 /
//!     #4 / G5）。hot-path consumer（intent_processor / risk_gate）
//!     在 Phase 1 不接線。

use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// H1 ThoughtGate stats / H1 思考閘 stats。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct H1Stats {
    /// Number of times H1 rejected an intel due to budget exhaustion.
    /// H1 因預算耗盡而拒絕 intel 的次數。
    #[serde(default)]
    pub budget_skip: u64,
    /// Number of times H1 rejected due to complexity score below threshold.
    /// H1 因複雜度分數低於門檻而拒絕的次數。
    #[serde(default)]
    pub complexity_skip: u64,
    /// Number of times H1 rejected due to per-symbol cooldown.
    /// H1 因 per-symbol 冷卻而拒絕的次數。
    #[serde(default)]
    pub cooldown_skip: u64,
    /// Current size of the cooldown dict (diagnostic).
    /// 當前 cooldown dict 大小（診斷用）。
    #[serde(default)]
    pub cooldown_dict_size: u64,
}

/// H2 budget gate state / H2 預算閘狀態。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct H2BudgetState {
    /// USD amount remaining in the day's AI cost budget.
    /// 當日 AI 成本預算剩餘 USD。
    #[serde(default)]
    pub daily_remaining_usd: f64,
    /// Hard cap on daily spend (governance constant).
    /// 當日預算硬上限（治理常數）。
    #[serde(default)]
    pub hard_cap_usd: f64,
    /// Adaptive multiplier (≤ 1.0 means tightening).
    /// 自適應倍率（≤ 1.0 = 收縮）。
    #[serde(default)]
    pub adaptive_multiplier: f64,
}

/// H3 ModelRouter route distribution / H3 路由分佈。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct H3RouteStats {
    #[serde(default)]
    pub l1_9b: u64,
    #[serde(default)]
    pub l1_27b: u64,
    #[serde(default)]
    pub l1_5: u64,
    #[serde(default)]
    pub l2: u64,
    #[serde(default)]
    pub cache_size: u64,
    #[serde(default)]
    pub cache_hit: u64,
    #[serde(default)]
    pub cache_expired: u64,
}

/// H4 validator stats / H4 驗證器 stats。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct H4ValidationStats {
    #[serde(default)]
    pub validation_fail: u64,
    #[serde(default)]
    pub validation_pass: u64,
}

/// H5 cost_logging stats / H5 成本日誌 stats。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct H5CostStats {
    #[serde(default)]
    pub ai_spend_7d_usd: f64,
    #[serde(default)]
    pub paper_pnl_7d_usd: f64,
    /// `None` when data_days < ADAPTIVE_MIN_DAYS (insufficient sample).
    /// 樣本不足（data_days < ADAPTIVE_MIN_DAYS）時為 `None`。
    #[serde(default)]
    pub cost_edge_ratio: Option<f64>,
    #[serde(default)]
    pub data_days: u32,
}

/// 5-Agent state for one agent (Strategist / Guardian / Analyst / Executor / Scout).
/// 5-Agent 中單一 agent 的狀態（策略師 / 守衛 / 分析師 / 執行者 / 偵察）。
///
/// MODULE_NOTE (EN): `stats` uses HashMap<String, i64> for forward-compat
///   schema evolution (PA §2 G7). When Phase 4 adds new metric keys,
///   Python pushes them in the dict and Rust automatically picks them
///   up — no Rust deploy required.
/// MODULE_NOTE (中)：`stats` 用 HashMap<String, i64> 支援 forward-compat
///   schema 演化（PA §2 G7）。Phase 4 加新指標 key 時，Python 推 dict 即可，
///   Rust 自動接收 — 無需重部署。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct AgentState {
    #[serde(default)]
    pub agent_name: String,
    #[serde(default)]
    pub stats: HashMap<String, i64>,
}

/// Aggregate H state snapshot — what `query_h_state_full` IPC returns.
/// H 狀態聚合快照 — `query_h_state_full` IPC 的回傳。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct HStateSnapshot {
    /// Monotonic version counter from Python state_store. Bumped on each
    /// successful poll. `0` = uninitialized (Phase 1 default-off path).
    /// Python state_store 單調遞增的版本號。每次 poll 成功時 bump。
    /// `0` = 未初始化（Phase 1 default-off 路徑）。
    #[serde(default)]
    pub version: u64,
    /// Unix ms timestamp when Python built this snapshot.
    /// Python 建構此 snapshot 的 unix ms 時間戳。
    #[serde(default)]
    pub fetched_at_ms: i64,
    #[serde(default)]
    pub h1: H1Stats,
    #[serde(default)]
    pub h2: H2BudgetState,
    #[serde(default)]
    pub h3: H3RouteStats,
    #[serde(default)]
    pub h4: H4ValidationStats,
    #[serde(default)]
    pub h5: H5CostStats,
    /// 5-Agent state keyed by agent name (`strategist` / `guardian` /
    /// `analyst` / `executor` / `scout`). Phase 1 receives empty map.
    /// 5-Agent 狀態，key = agent 名稱。Phase 1 收到空 map。
    #[serde(default)]
    pub agents: HashMap<String, AgentState>,
}

/// Light status payload for `get_h_state_status` IPC — health probe view.
/// `get_h_state_status` IPC 的輕量狀態 payload — 健檢視角。
///
/// MODULE_NOTE (EN): Used by `passive_wait_healthcheck.py [20]` to detect
///   silent staleness (poll daemon stuck) without pulling the full snapshot.
/// MODULE_NOTE (中)：`passive_wait_healthcheck.py [20]` 用此判 poll 失能，
///   不必拉完整 snapshot。
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct HStateStatus {
    pub version: u64,
    pub staleness_ms: i64,
    pub is_stale: bool,
    pub poll_attempts: u64,
    pub poll_successes: u64,
    pub poll_failures: u64,
    /// `true` when env-gate `OPENCLAW_H_STATE_GATEWAY=1` and poller spawned.
    /// `OPENCLAW_H_STATE_GATEWAY=1` 且 poller 已 spawn 時為 `true`。
    pub gateway_enabled: bool,
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Forward-compat: parsing JSON with extra unknown fields must succeed
    /// (serde default + #[serde(default)] on every field).
    /// Forward-compat：含未知欄位的 JSON 必須能 parse。
    #[test]
    fn snapshot_deserializes_with_unknown_fields() {
        let json = serde_json::json!({
            "version": 7,
            "fetched_at_ms": 1714000000000_i64,
            "h1": {"budget_skip": 5, "unknown_future_field": 999},
            "agents": {
                "strategist": {
                    "agent_name": "strategist",
                    "stats": {"intel_evaluated": 412, "intents_produced": 38, "future_metric_x": 1}
                }
            },
            "totally_new_top_level_field": [1,2,3]
        });
        let snap: HStateSnapshot =
            serde_json::from_value(json).expect("forward-compat parse should succeed");
        assert_eq!(snap.version, 7);
        assert_eq!(snap.h1.budget_skip, 5);
        assert_eq!(
            snap.agents
                .get("strategist")
                .and_then(|a| a.stats.get("intel_evaluated")),
            Some(&412)
        );
        assert_eq!(
            snap.agents
                .get("strategist")
                .and_then(|a| a.stats.get("future_metric_x")),
            Some(&1)
        );
    }

    /// Backward-compat: missing fields default to zero — Phase 1 empty payload.
    /// Backward-compat：缺欄位 default 為 0 — Phase 1 空 payload。
    #[test]
    fn snapshot_deserializes_empty_dict() {
        let snap: HStateSnapshot =
            serde_json::from_value(serde_json::json!({})).expect("empty dict parse");
        assert_eq!(snap.version, 0);
        assert_eq!(snap.fetched_at_ms, 0);
        assert_eq!(snap.h1.budget_skip, 0);
        assert!(snap.agents.is_empty());
    }

    /// Cost ratio Option<f64> survives null vs number round-trip.
    /// cost_edge_ratio Option<f64> 處理 null vs 數字。
    #[test]
    fn h5_cost_ratio_null_vs_number() {
        let with_ratio: H5CostStats = serde_json::from_value(serde_json::json!({
            "cost_edge_ratio": -0.508
        }))
        .unwrap();
        assert_eq!(with_ratio.cost_edge_ratio, Some(-0.508));

        let without: H5CostStats =
            serde_json::from_value(serde_json::json!({"cost_edge_ratio": null})).unwrap();
        assert_eq!(without.cost_edge_ratio, None);

        let absent: H5CostStats = serde_json::from_value(serde_json::json!({})).unwrap();
        assert_eq!(absent.cost_edge_ratio, None);
    }
}
