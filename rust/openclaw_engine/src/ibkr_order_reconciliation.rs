//! MODULE_NOTE
//! 模塊用途：IBKR **W7-S3 三向對賬引擎（P0 核心;Bybit 幻影倉根因防線）**（IBKR_TODO §5-W7;
//!   設計文檔 §3 + 切片表 S3）。承 S1（intent journal + 14-態 lifecycle + **唯一 mutator**
//!   `apply_lifecycle_event`）與 W5-S3（reqOpenOrders/reqExecutions 唯讀 builder=broker 真值源）,
//!   對 **broker 真值 × intent journal × 本地態** 做無序 join tolerant 的三向對賬。
//!   **純函數 / 注入時鐘 / 零 socket / 零 async / 零 send**;不觸 transport seam（INV-ORDER/INV-1
//!   恆 HOLD）,一切 lifecycle 遷移**唯經 S1 單一 mutator**（本模塊不另闢寫入路徑=幻影倉教訓）。
//! 主要區段：
//!   - (a) config / broker 真值視圖（`BrokerTruthView`;由 W5-S3 digest 或測試直建）。
//!   - (b) typed 對賬裁決（`IntentReconOutcome`）+ 告警（`ReconciliationAlert`）+ 報告
//!     （`ReconciliationReport`;含 **凍結 symbol 集**）。
//!   - (c) `reconcile`：三向 join（**idempotency_key 優先**,order-id fallback,歧義/孤兒 fail-closed）
//!     → 逐意圖對賬（經 S1 mutator resync / reduce-only 阻擋 / StateUnknown 漏斗 / ManualReview 凍結）。
//!   - (d) `reconcile_settlement_ledger`：**E2-LOW-2 disjoint 不變量**（已成熟 tranche 滾入 settled
//!     即移出 unsettled,禁同時計數;defense-in-depth 承 S2 carry）。
//! 三向 join 法（設計 §3 P0-C;**禁按 pending 匹配失敗丟棄**）：
//!   1. **idempotency_key（drift-immune 首選）**：broker `orderRef`==本地 `idempotency_key` → 權威 join
//!      （重連後 broker order-id 漂移不影響）。
//!   2. **order-id fallback（drift-prone）**：broker `order_id` ∈ {本地 `order_id`, `broker_order_id`};
//!      唯一命中=暫定 join,**多命中=歧義 fail-closed**（凍結,不樂觀猜）。
//!   3. **孤兒（P0-C）**：broker 事件無對應本地意圖 → **不丟棄** → 記錄 + 凍結 symbol + 告警。
//! 硬邊界：
//!   - **唯一 mutator**：所有本地態遷移經 `OrderLifecycleDriver::apply_lifecycle_event`;本模塊零第二
//!     寫入路徑。遷移合法性以 types `is_transition_allowed`/`is_operation_transition_allowed` 為真源。
//!   - **差異 fail-closed**：不能證明一致的差異一律凍結/ManualReview,不樂觀假設本地對。
//!   - **P0-A reduce-only**：broker fill 經 mutator 應用,reduce-only 違反（幻影再開倉 remaining↑）即拒
//!     + 凍結,態/記帳不變。
//!   - **P0-B unknown-terminal**：StateUnknown 無 terminal-with-evidence → ManualReview + 凍結 symbol +
//!     告警（reconciler/人工裁決前不再對該 symbol 發 order verb）。
//!   - **零效果**：不產 order 出線 bytes、不鑄 effect permit、不開 socket。default build DCE（真接線=
//!     S4 IPC handler）。

// intentional-DCE 姿態繼承 S1/S2:本模塊 default build 零 production caller（真接線=S4 IPC handler
// 的 reconcile 迴路）。allow(dead_code) 必保留至 S4 接線移出。
#![allow(dead_code)]

use std::collections::{BTreeMap, BTreeSet};

use openclaw_types::{
    is_operation_transition_allowed, is_transition_allowed, BrokerOperation,
    IbkrPaperOrderLifecycleState,
};

use crate::ibkr_tws_account_data::SnapshotStaleness;
use crate::ibkr_tws_order_exec_data::IbkrOrderStatusV1;
use crate::ibkr_tws_order_lifecycle::{FillDelta, LifecycleEvent, OrderLifecycleDriver};

// ===========================================================================
// (a) broker 真值視圖（W5-S3 digest 投影;測試可直建）
// ===========================================================================

/// broker 側單筆訂單真值（reqOpenOrders head + orderStatus 併;W5-S3 唯讀 builder 投影）。
/// **join 載體**：`order_ref`==本地 `idempotency_key`（drift-immune 首選）;`order_id`/`perm_id` 為
/// drift-prone fallback 與觀測。`status`/`filled`/`remaining` 缺席以 `None` 誠實承載（非 0 假值）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct BrokerOrderTruth {
    /// broker 回報 order-id（重連可漂移;非權威 join 鍵）。
    pub order_id: i64,
    /// broker 穩定 order-id（perm_id;跨 session 穩定,觀測用）。
    pub perm_id: i64,
    /// 客戶端 order key 載體（`orderRef`;==本地 `idempotency_key` 時為權威 join;空=未載）。
    pub order_ref: String,
    /// 標的代碼（open-order head 承載;凍結 symbol 的真值源）。
    pub symbol: String,
    /// orderStatus 白名單態（`None`=僅 openOrder head 無 status 併入）。
    pub status: Option<IbkrOrderStatusV1>,
    /// 累積成交量（定點字串;`None`=無 status）。
    pub filled_decimal: Option<String>,
    /// 剩餘量（定點字串;`None`=無 status）。
    pub remaining_decimal: Option<String>,
}

/// broker 側單筆成交真值（reqExecutions execDetails+commissionReport join;execId 為去重鍵=P0-C
/// 上游已於 W5-S3 去重）。本引擎用於 **孤兒偵測（禁丟棄）** 與 ledger 佐證。
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct BrokerExecutionTruth {
    /// 成交唯一鍵（P0-C 去重鍵;上游 W5-S3 已去重,本引擎僅消費）。
    pub exec_id: String,
    /// 所屬 broker order-id（join 至本地 order-id）。
    pub order_id: i64,
    pub perm_id: i64,
    pub symbol: String,
    pub shares_decimal: String,
    pub commission_decimal: String,
}

/// broker 真值三向視圖（open-orders 面 + executions 面各帶 staleness;非 `Fresh` → 對賬延後,
/// 不對陳舊 / 毒化快照下結論）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct BrokerTruthView {
    pub open_orders: Vec<BrokerOrderTruth>,
    pub executions: Vec<BrokerExecutionTruth>,
    pub open_orders_staleness: SnapshotStaleness,
    pub executions_staleness: SnapshotStaleness,
}

impl BrokerTruthView {
    /// open-orders 與 executions 兩面皆 `Fresh` 方可對賬（fail-closed:任一面非 Fresh → 延後）。
    fn both_fresh(&self) -> bool {
        matches!(self.open_orders_staleness, SnapshotStaleness::Fresh { .. })
            && matches!(self.executions_staleness, SnapshotStaleness::Fresh { .. })
    }
}

// ===========================================================================
// (b) typed 對賬裁決 + 告警 + 報告
// ===========================================================================

/// 單筆意圖的三向對賬裁決（全 typed;呼叫端據此分流,不 panic/不捏值/不默默跳過）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum IntentReconOutcome {
    /// broker 態與本地態一致（無需遷移）。
    Consistent {
        idempotency_key: String,
        state: IbkrPaperOrderLifecycleState,
    },
    /// 以 broker 真值前推本地未終態成功（resync;經單一 mutator 合法遷移）。
    Resynced {
        idempotency_key: String,
        from: IbkrPaperOrderLifecycleState,
        to: IbkrPaperOrderLifecycleState,
    },
    /// **P0-A**：broker fill 無法證明減倉安全（幻影再開倉 remaining↑ / cancel 後 late-fill）→ mutator
    /// 拒 → 凍結 symbol,態/記帳不變。
    ReduceOnlyBlocked {
        idempotency_key: String,
        symbol: String,
    },
    /// 差異無法以合法遷移對齊（含歧義 join / 本地終態與 broker 衝突）→ 升 ManualReview + 凍結。
    DivergedFrozen {
        idempotency_key: String,
        symbol: String,
        detail: &'static str,
    },
    /// **P0-B**：StateUnknown 無 terminal-with-evidence → 升 ManualReview + 凍結 symbol + 告警。
    UnknownTerminalFrozen {
        idempotency_key: String,
        symbol: String,
    },
}

/// 對賬告警類別（S4 告警 sink 消費;凍結決策的可觀測依據）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum ReconciliationAlertKind {
    /// P0-B unknown-terminal 凍結。
    UnknownTerminalFreeze,
    /// broker/本地態分歧 fail-closed。
    Divergence,
    /// P0-A reduce-only 阻擋（幻影倉防線觸發）。
    ReduceOnlyViolation,
    /// P0-C broker 訂單孤兒（無對應本地意圖;禁丟棄）。
    OrphanBrokerOrder,
    /// P0-C broker 成交孤兒（無對應本地意圖;禁丟棄）。
    OrphanBrokerExecution,
}

/// 單筆對賬告警（symbol + 可選 idempotency_key + 明細）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct ReconciliationAlert {
    pub kind: ReconciliationAlertKind,
    pub symbol: String,
    pub idempotency_key: Option<String>,
    pub detail: &'static str,
}

/// 三向對賬報告（S4 IPC / 告警 sink 唯讀消費）。**凍結 symbol 集**=reconciler/人工裁決前不再對其
/// 發 order verb 的權威集（P0-B）。
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub(crate) struct ReconciliationReport {
    /// 逐意圖裁決（確定序）。
    pub outcomes: Vec<IntentReconOutcome>,
    /// **凍結 symbol 集**（P0-B/P0-C;order-emit 面下單前必查此集）。
    pub frozen_symbols: BTreeSet<String>,
    /// 告警（凍結 / 分歧 / reduce-only / 孤兒）。
    pub alerts: Vec<ReconciliationAlert>,
    /// broker 訂單孤兒（禁丟棄;order_id 觀測）。
    pub orphan_order_ids: Vec<i64>,
    /// broker 成交孤兒（禁丟棄;exec_id 觀測）。
    pub orphan_exec_ids: Vec<String>,
    /// 快照非 `Fresh` → 對賬延後（未動任何態,保守)。
    pub skipped_stale: bool,
}

impl ReconciliationReport {
    /// symbol 是否處於凍結（order-emit 面查詢入口）。
    pub(crate) fn is_symbol_frozen(&self, symbol: &str) -> bool {
        self.frozen_symbols.contains(symbol)
    }

    /// 凍結 symbol + 記錄告警（去重:BTreeSet 天然去重 symbol;告警逐筆保留）。
    fn freeze(
        &mut self,
        symbol: &str,
        kind: ReconciliationAlertKind,
        idempotency_key: Option<String>,
        detail: &'static str,
    ) {
        self.frozen_symbols.insert(symbol.to_string());
        self.alerts.push(ReconciliationAlert {
            kind,
            symbol: symbol.to_string(),
            idempotency_key,
            detail,
        });
    }
}

// ===========================================================================
// (c) 三向對賬主入口
// ===========================================================================

/// 意圖輕量快照（避免對賬迴路中 driver 借用衝突:先快照 public 欄,再經 mutator 遷移）。
struct IntentSnapshot {
    idempotency_key: String,
    state: IbkrPaperOrderLifecycleState,
    order_id: i64,
    broker_order_id: Option<i64>,
    operation: BrokerOperation,
}

/// **三向對賬主入口**：broker 真值 × intent journal（S1 driver）× 本地態。無序 join tolerant;差異
/// fail-closed;一切遷移經 S1 **單一 mutator**。`local_symbols`=idempotency_key→symbol 本地綁定
/// （intent record 無 symbol 欄,由 order-emit 面維護;缺席時以 broker symbol 或 `UNRESOLVED:` 令牌
/// 凍結 + 告警,絕不靜默放行）。回不可變報告（含凍結集）。
pub(crate) fn reconcile(
    driver: &mut OrderLifecycleDriver,
    broker: &BrokerTruthView,
    local_symbols: &BTreeMap<String, String>,
    now_ms: u64,
) -> ReconciliationReport {
    let mut report = ReconciliationReport::default();

    // ── staleness 閘：兩面皆 Fresh 方對賬（非 Fresh=延後,不對陳舊/毒化快照下結論,不誤凍）──
    if !broker.both_fresh() {
        report.skipped_stale = true;
        return report;
    }

    // ── 意圖快照 + order-id 索引（drift-prone fallback 用）──
    let snapshots: Vec<IntentSnapshot> = driver
        .intents()
        .map(|r| IntentSnapshot {
            idempotency_key: r.idempotency_key.clone(),
            state: r.state,
            order_id: r.order_id,
            broker_order_id: r.broker_order_id,
            operation: r.operation,
        })
        .collect();
    let intent_keys: BTreeSet<String> = snapshots
        .iter()
        .map(|s| s.idempotency_key.clone())
        .collect();
    // order-id → 候選 idempotency_key 集（本地 order_id 與 broker_order_id 皆入索引）。
    let mut order_id_to_keys: BTreeMap<i64, BTreeSet<String>> = BTreeMap::new();
    for s in &snapshots {
        order_id_to_keys
            .entry(s.order_id)
            .or_default()
            .insert(s.idempotency_key.clone());
        if let Some(boid) = s.broker_order_id {
            order_id_to_keys
                .entry(boid)
                .or_default()
                .insert(s.idempotency_key.clone());
        }
    }

    // ── broker open-orders 三向 join（idempotency_key 優先 → order-id fallback → 孤兒）──
    let mut matched: BTreeMap<String, &BrokerOrderTruth> = BTreeMap::new();
    let mut forced_diverge: BTreeSet<String> = BTreeSet::new();
    for order in &broker.open_orders {
        match resolve_order_join(order, &intent_keys, &order_id_to_keys) {
            JoinResolution::Matched(key) => {
                use std::collections::btree_map::Entry;
                match matched.entry(key) {
                    Entry::Vacant(v) => {
                        v.insert(order);
                    }
                    Entry::Occupied(e) => {
                        // 同一本地意圖對到 ≥2 個 broker 訂單 → 分歧 fail-closed（不樂觀選一）。
                        let key = e.key().clone();
                        forced_diverge.insert(key.clone());
                        report.freeze(
                            &order.symbol,
                            ReconciliationAlertKind::Divergence,
                            Some(key),
                            "multiple broker orders matched one intent",
                        );
                    }
                }
            }
            JoinResolution::Ambiguous => {
                // order-id fallback 多命中（重連漂移致 order-id 撞號）→ 凍結,不猜。
                report.freeze(
                    &order.symbol,
                    ReconciliationAlertKind::Divergence,
                    None,
                    "broker order-id ambiguous across intents",
                );
            }
            JoinResolution::Orphan => {
                // P0-C:broker 有訂單但無對應本地意圖 → 禁丟棄 → 記錄 + 凍結 + 告警。
                report.orphan_order_ids.push(order.order_id);
                report.freeze(
                    &order.symbol,
                    ReconciliationAlertKind::OrphanBrokerOrder,
                    None,
                    "broker order has no local intent",
                );
            }
        }
    }

    // ── broker executions:孤兒偵測（P0-C 禁丟棄）+ 記錄有成交的本地意圖鍵（幻影 late-fill 用）──
    let mut exec_matched_keys: BTreeSet<String> = BTreeSet::new();
    for exec in &broker.executions {
        match order_id_to_keys.get(&exec.order_id) {
            None => {
                // P0-C:broker 有成交但無對應本地意圖 → 禁丟棄 → 記錄 + 凍結 + 告警。
                report.orphan_exec_ids.push(exec.exec_id.clone());
                report.freeze(
                    &exec.symbol,
                    ReconciliationAlertKind::OrphanBrokerExecution,
                    None,
                    "broker execution has no local intent",
                );
            }
            Some(keys) => {
                for k in keys {
                    exec_matched_keys.insert(k.clone());
                }
            }
        }
    }

    // ── 逐意圖對賬（經 S1 單一 mutator）──
    for snap in &snapshots {
        let matched_order = matched.get(&snap.idempotency_key).copied();
        let symbol = resolve_symbol(&snap.idempotency_key, matched_order, local_symbols);
        if forced_diverge.contains(&snap.idempotency_key) {
            escalate_manual_review(driver, snap, now_ms);
            report.freeze(
                &symbol,
                ReconciliationAlertKind::Divergence,
                Some(snap.idempotency_key.clone()),
                "multiple broker orders matched one intent",
            );
            report.outcomes.push(IntentReconOutcome::DivergedFrozen {
                idempotency_key: snap.idempotency_key.clone(),
                symbol,
                detail: "multiple broker orders matched one intent",
            });
            continue;
        }
        let has_exec = exec_matched_keys.contains(&snap.idempotency_key);
        let outcome = reconcile_intent(
            driver,
            snap,
            matched_order,
            &symbol,
            has_exec,
            now_ms,
            &mut report,
        );
        report.outcomes.push(outcome);
    }

    report
}

/// broker order → 本地意圖 join 裁決（idempotency_key 優先,order-id fallback,孤兒/歧義分流）。
enum JoinResolution {
    Matched(String),
    /// order-id fallback 多命中 → 歧義 fail-closed。
    Ambiguous,
    /// 無對應本地意圖 → 孤兒（P0-C 禁丟棄）。
    Orphan,
}

fn resolve_order_join(
    order: &BrokerOrderTruth,
    intent_keys: &BTreeSet<String>,
    order_id_to_keys: &BTreeMap<i64, BTreeSet<String>>,
) -> JoinResolution {
    // 1) idempotency_key 權威 join（drift-immune;orderRef 載體）。
    if !order.order_ref.is_empty() && intent_keys.contains(&order.order_ref) {
        return JoinResolution::Matched(order.order_ref.clone());
    }
    // 2) order-id fallback（drift-prone;唯一命中=暫定,多命中=歧義 fail-closed）。
    match order_id_to_keys.get(&order.order_id) {
        Some(keys) if keys.len() == 1 => {
            JoinResolution::Matched(keys.iter().next().cloned().unwrap_or_default())
        }
        Some(_) => JoinResolution::Ambiguous,
        None => JoinResolution::Orphan,
    }
}

/// symbol 解析（凍結真值源:broker symbol 優先 → 本地綁定 → `UNRESOLVED:` 令牌保守凍結）。
fn resolve_symbol(
    key: &str,
    matched: Option<&BrokerOrderTruth>,
    local_symbols: &BTreeMap<String, String>,
) -> String {
    matched
        .map(|o| o.symbol.clone())
        .filter(|s| !s.is_empty())
        .or_else(|| local_symbols.get(key).cloned())
        .unwrap_or_else(|| format!("UNRESOLVED:{key}"))
}

/// 單筆意圖對賬（依本地態分流;一切遷移經 mutator）。
fn reconcile_intent(
    driver: &mut OrderLifecycleDriver,
    snap: &IntentSnapshot,
    matched: Option<&BrokerOrderTruth>,
    symbol: &str,
    has_broker_execution: bool,
    now_ms: u64,
    report: &mut ReconciliationReport,
) -> IntentReconOutcome {
    use IbkrPaperOrderLifecycleState as St;

    // ── StateUnknown:P0-B 出口窄——需 terminal-with-evidence 才離開,否則 ManualReview + 凍結 ──
    if snap.state == St::StateUnknown {
        if let Some((target, fill)) = matched.and_then(broker_terminal_target) {
            if apply_transition(driver, &snap.idempotency_key, target, fill, now_ms).is_ok() {
                return IntentReconOutcome::Resynced {
                    idempotency_key: snap.idempotency_key.clone(),
                    from: St::StateUnknown,
                    to: target,
                };
            }
        }
        escalate_manual_review(driver, snap, now_ms);
        report.freeze(
            symbol,
            ReconciliationAlertKind::UnknownTerminalFreeze,
            Some(snap.idempotency_key.clone()),
            "state-unknown without terminal evidence",
        );
        return IntentReconOutcome::UnknownTerminalFrozen {
            idempotency_key: snap.idempotency_key.clone(),
            symbol: symbol.to_string(),
        };
    }

    // ── 本地終態:broker 若顯示衝突（幻影 late-fill / re-open,經 order status 或無序 execution)
    //    → 分歧凍結（P0-A 防線;終態不可再遷,態/記帳恆不變)。本地 Filled 有成交=一致不算衝突。──
    if snap.state.is_terminal() {
        let order_conflict = matched.is_some_and(|o| broker_conflicts_with_terminal(snap.state, o));
        // 非 Filled 終態卻有 broker 成交 = 幻影 late-fill（如 cancel 後成交到達)。
        let exec_conflict = snap.state != St::Filled && has_broker_execution;
        if order_conflict || exec_conflict {
            report.freeze(
                symbol,
                ReconciliationAlertKind::Divergence,
                Some(snap.idempotency_key.clone()),
                "broker shows activity on locally-terminal order",
            );
            return IntentReconOutcome::DivergedFrozen {
                idempotency_key: snap.idempotency_key.clone(),
                symbol: symbol.to_string(),
                detail: "broker shows activity on locally-terminal order",
            };
        }
        return IntentReconOutcome::Consistent {
            idempotency_key: snap.idempotency_key.clone(),
            state: snap.state,
        };
    }

    // ── 本地活躍（非終態、非 StateUnknown）──
    let Some(order) = matched else {
        // broker open-orders 無此單。有終態成交佐證 → resync;否則無法證明 → StateUnknown 漏斗凍結。
        // （open-orders 只列 working 單,filled/cancelled 單本就不在——故缺席非即分歧,經漏斗保守處置。）
        return funnel_via_state_unknown(driver, snap, None, symbol, now_ms, report);
    };

    let Some((target, fill)) = broker_target(order) else {
        // broker status 白名單外 / 缺 status → 無法證明 → 保守漏斗。
        return funnel_via_state_unknown(driver, snap, matched, symbol, now_ms, report);
    };

    // broker 態與本地一致且無新 fill → Consistent。
    if target == snap.state && fill.is_none() {
        return IntentReconOutcome::Consistent {
            idempotency_key: snap.idempotency_key.clone(),
            state: snap.state,
        };
    }

    // 嘗試單步合法前推（含 fill;reduce-only 於 mutator 內把守=P0-A）。
    match apply_transition(driver, &snap.idempotency_key, target, fill.clone(), now_ms) {
        Ok(()) => IntentReconOutcome::Resynced {
            idempotency_key: snap.idempotency_key.clone(),
            from: snap.state,
            to: target,
        },
        Err(true) => {
            // reduce-only 違反（幻影再開倉 remaining↑ / cancel 後 late-fill）→ 凍結,態不變。
            report.freeze(
                symbol,
                ReconciliationAlertKind::ReduceOnlyViolation,
                Some(snap.idempotency_key.clone()),
                "reduce-only violation on broker fill",
            );
            IntentReconOutcome::ReduceOnlyBlocked {
                idempotency_key: snap.idempotency_key.clone(),
                symbol: symbol.to_string(),
            }
        }
        Err(false) => {
            // 非單步可達（如本地 BrokerSubmitRequested、broker 已 Filled）→ StateUnknown 漏斗保守處置。
            funnel_via_state_unknown(driver, snap, matched, symbol, now_ms, report)
        }
    }
}

/// StateUnknown 漏斗（保守）：先經 mutator 遷 StateUnknown,再依 broker terminal-with-evidence 決定
/// resync 至終態 或 升 ManualReview + 凍結（P0-B）。無法遷 StateUnknown（如已終態）→ 分歧凍結。
fn funnel_via_state_unknown(
    driver: &mut OrderLifecycleDriver,
    snap: &IntentSnapshot,
    matched: Option<&BrokerOrderTruth>,
    symbol: &str,
    now_ms: u64,
    report: &mut ReconciliationReport,
) -> IntentReconOutcome {
    use IbkrPaperOrderLifecycleState as St;

    // 先遷 StateUnknown（不續用舊授權,對賬前凍結）。
    if apply_transition(
        driver,
        &snap.idempotency_key,
        St::StateUnknown,
        None,
        now_ms,
    )
    .is_err()
    {
        report.freeze(
            symbol,
            ReconciliationAlertKind::Divergence,
            Some(snap.idempotency_key.clone()),
            "cannot reconcile: no legal path to state-unknown",
        );
        return IntentReconOutcome::DivergedFrozen {
            idempotency_key: snap.idempotency_key.clone(),
            symbol: symbol.to_string(),
            detail: "cannot reconcile: no legal path to state-unknown",
        };
    }

    // 有 terminal-with-evidence → resync 至終態。
    if let Some((target, fill)) = matched.and_then(broker_terminal_target) {
        if apply_transition(driver, &snap.idempotency_key, target, fill, now_ms).is_ok() {
            return IntentReconOutcome::Resynced {
                idempotency_key: snap.idempotency_key.clone(),
                from: St::StateUnknown,
                to: target,
            };
        }
    }

    // 無終態佐證 → ManualReview + 凍結 symbol（P0-B）。
    escalate_manual_review(driver, snap, now_ms);
    report.freeze(
        symbol,
        ReconciliationAlertKind::UnknownTerminalFreeze,
        Some(snap.idempotency_key.clone()),
        "state-unknown without terminal evidence",
    );
    IntentReconOutcome::UnknownTerminalFrozen {
        idempotency_key: snap.idempotency_key.clone(),
        symbol: symbol.to_string(),
    }
}

/// 升 ManualReviewRequired（經 mutator;先試單步,不可達則經 StateUnknown 中轉)。已終態 → no-op。
fn escalate_manual_review(driver: &mut OrderLifecycleDriver, snap: &IntentSnapshot, now_ms: u64) {
    use IbkrPaperOrderLifecycleState as St;
    // 讀當前態（可能已於本迴路被前一步遷移）。
    let from = match driver.intent_by_idempotency_key(&snap.idempotency_key) {
        Some(r) => r.state,
        None => return,
    };
    if from == St::ManualReviewRequired || from.is_terminal() {
        return;
    }
    if apply_transition(
        driver,
        &snap.idempotency_key,
        St::ManualReviewRequired,
        None,
        now_ms,
    )
    .is_ok()
    {
        return;
    }
    // 單步不可達 → 經 StateUnknown 中轉（StateUnknown→ManualReview 恆合法)。
    if apply_transition(
        driver,
        &snap.idempotency_key,
        St::StateUnknown,
        None,
        now_ms,
    )
    .is_ok()
    {
        let _ = apply_transition(
            driver,
            &snap.idempotency_key,
            St::ManualReviewRequired,
            None,
            now_ms,
        );
    }
}

/// 經 S1 **單一 mutator** 應用一步遷移。`op` 由 types 矩陣自動挑選（legal_paper_op_for);回
/// `Ok(())`=成功,`Err(true)`=reduce-only 違反（P0-A),`Err(false)`=遷移非法/其他拒。
fn apply_transition(
    driver: &mut OrderLifecycleDriver,
    key: &str,
    target: IbkrPaperOrderLifecycleState,
    fill: Option<FillDelta>,
    now_ms: u64,
) -> Result<(), bool> {
    let from = driver
        .intent_by_idempotency_key(key)
        .map(|r| r.state)
        .ok_or(false)?;
    let op = legal_paper_op_for(from, target).ok_or(false)?;
    match driver.apply_lifecycle_event(LifecycleEvent::Transition {
        idempotency_key: key.to_string(),
        next_state: target,
        operation: op,
        broker_order_id: None,
        fill,
        now_ms,
    }) {
        Ok(_) => Ok(()),
        Err(e) => Err(matches!(
            e,
            crate::ibkr_tws_order_lifecycle::LifecycleReject::ReduceOnlyViolation { .. }
        )),
    }
}

/// 挑選使 `(from → to)` 合法的 paper operation（types `is_operation_transition_allowed` 為真源;
/// 遍歷 4 個 paper verb,取首個合法者;無 → `None`=遷移本身非法)。fill 承載遷移須落 FillImport
/// （矩陣中唯 FillImport 允帶 fill 的 →PartiallyFilled/Filled),此遍歷順序天然命中。
fn legal_paper_op_for(
    from: IbkrPaperOrderLifecycleState,
    to: IbkrPaperOrderLifecycleState,
) -> Option<BrokerOperation> {
    if !is_transition_allowed(from, to) {
        return None;
    }
    const OPS: [BrokerOperation; 4] = [
        BrokerOperation::PaperOrderFillImport,
        BrokerOperation::PaperOrderCancel,
        BrokerOperation::PaperOrderReplace,
        BrokerOperation::PaperOrderSubmit,
    ];
    OPS.into_iter()
        .find(|op| is_operation_transition_allowed(*op, from, to))
}

/// broker order 的目標本地態 + 可選 fill（活躍前推用;白名單外 / 無 status → `None`=無法證明)。
fn broker_target(
    order: &BrokerOrderTruth,
) -> Option<(IbkrPaperOrderLifecycleState, Option<FillDelta>)> {
    use IbkrOrderStatusV1 as S;
    use IbkrPaperOrderLifecycleState as St;
    let status = order.status?;
    let fill = fill_from(order);
    match status {
        S::Filled => Some((St::Filled, fill)),
        S::Submitted | S::PreSubmitted => {
            // 有部分成交 → PartiallyFilled;否則 broker 已受理 → BrokerAcknowledged。
            match &fill {
                Some(_) if has_positive_fill(order) => Some((St::PartiallyFilled, fill)),
                _ => Some((St::BrokerAcknowledged, None)),
            }
        }
        S::PendingSubmit => Some((St::BrokerSubmitRequested, None)),
        S::PendingCancel => Some((St::CancelRequested, None)),
        S::Cancelled | S::ApiCancelled => Some((St::Cancelled, None)),
        S::Inactive => Some((St::Inactive, None)),
        S::UnknownDenied => None,
    }
}

/// broker terminal-with-evidence 目標（StateUnknown 出口用;僅終態且帶 broker 佐證方回)。
fn broker_terminal_target(
    order: &BrokerOrderTruth,
) -> Option<(IbkrPaperOrderLifecycleState, Option<FillDelta>)> {
    use IbkrOrderStatusV1 as S;
    use IbkrPaperOrderLifecycleState as St;
    match order.status? {
        S::Filled => Some((St::Filled, fill_from(order))),
        S::Cancelled | S::ApiCancelled => Some((St::Cancelled, None)),
        S::Inactive => Some((St::Inactive, None)),
        _ => None,
    }
}

/// broker 是否與本地終態衝突（幻影偵測:本地已 Cancelled/Rejected/Inactive 但 broker 顯示 Filled
/// 或有正成交 → 衝突;本地 Filled 且 broker Filled=一致不衝突)。
fn broker_conflicts_with_terminal(
    local: IbkrPaperOrderLifecycleState,
    order: &BrokerOrderTruth,
) -> bool {
    use IbkrOrderStatusV1 as S;
    use IbkrPaperOrderLifecycleState as St;
    match order.status {
        Some(S::Filled) => local != St::Filled,
        Some(S::Submitted)
        | Some(S::PreSubmitted)
        | Some(S::PendingSubmit)
        | Some(S::PendingCancel) => {
            // broker 仍顯示活躍/工作中,但本地已終態 → 衝突（除非本地 Inactive 且無正成交)。
            has_positive_fill(order) || local != St::Inactive
        }
        _ => false,
    }
}

/// 由 broker order 的 filled/remaining 構 fill delta（缺任一 → `None`,不捏值)。
fn fill_from(order: &BrokerOrderTruth) -> Option<FillDelta> {
    match (&order.filled_decimal, &order.remaining_decimal) {
        (Some(f), Some(r)) => Some(FillDelta {
            cumulative_filled_decimal: f.clone(),
            remaining_decimal: r.clone(),
        }),
        _ => None,
    }
}

/// broker 是否有正累積成交（filled > 0;方向判別,非記帳)。
fn has_positive_fill(order: &BrokerOrderTruth) -> bool {
    order
        .filled_decimal
        .as_deref()
        .and_then(|s| s.parse::<f64>().ok())
        .map(|v| v > 0.0)
        .unwrap_or(false)
}

// (d) E2-LOW-2 結算台帳 disjoint 不變量 + 定點 decimal 輔助：拆分至 _support（檔案行數治理）。
#[path = "ibkr_order_reconciliation_support.rs"]
mod support;
// 結算台帳 API 的 S3 對外面（真消費者=S4 IPC reconcile 迴路;繼承本模塊 intentional-DCE 姿態,
// default build 尚無非測試 caller）。
#[allow(unused_imports)]
pub(crate) use support::{reconcile_settlement_ledger, LedgerReconcileError, SettlementLedger};

#[cfg(test)]
#[path = "ibkr_order_reconciliation_tests.rs"]
mod tests;
