//! MODULE_NOTE
//! 模塊用途：IBKR **W7-S1 訂單生命週期 runtime driver + append-only intent journal（不送出）**
//!   （IBKR_TODO §5-W7;設計文檔 §2.2）。承 S0 transport-gating 恆拒地基,在 14-態型別基座
//!   （`openclaw_types::ibkr_paper_lifecycle`,source-ready 純消費不重造）之上落地 runtime 狀態機:
//!   單一狀態 mutator、hash-chain 意圖日誌、nextValidId 管理 + order-id drift recovery、ApiPending
//!   transient-pending 態分流、重啟 recovery。**純同步、注入時鐘、零 socket / 零 async / 零下單出線**
//!   （place/cancel encoder 在 `ibkr_tws_order_transport`,S1 產 `OrderFrame` 但無 production send）。
//! 主要區段：
//!   - (a) config / typed 裁決 `LifecycleReject`（全 typed;禁 panic/捏值/silent drop）。
//!   - (b) `IntentRecord`：單筆意圖 runtime 態（**冪等真源=`idempotency_key`**;本地 `order_id` 由
//!     nextValidId 遞增分配,重連後 broker 回的 order-id 可能漂移 → 以 idempotency_key join 日誌）。
//!   - (c) `IntentJournalEntry` + hash chain（append-only;`event_hash = sha256(prev_hash || 正規化)`,
//!     genesis prev="";可 `verify_chain` 驗竄改）。
//!   - (d) `OrderLifecycleDriver`：**唯一狀態 mutator `apply_lifecycle_event`**（Bybit 幻影倉教訓:
//!     單一狀態寫入路徑,fill 應用與 cancel 應用共用此 mutator,reduce-only fail-closed=無法證明
//!     減倉安全即拒）+ nextValidId + ApiPending 有界 timeout + restart recovery。
//! 依賴：`openclaw_types`（`IbkrPaperOrderLifecycleState` 14 態 / `is_transition_allowed` /
//!   `is_operation_transition_allowed` / `classify_ibkr_paper_restart_recovery` +
//!   `IbkrPaperRestartRecoveryInputV1/Action`）、`sha2`/`hex`（journal hash chain）、`BTreeMap`。
//! 硬邊界：
//!   - **唯一 mutator（絕無第二狀態寫入路徑）**：所有 lifecycle STATE 遷移經 `apply_lifecycle_event`;
//!     遷移合法性以 types `is_transition_allowed` + `is_operation_transition_allowed` 為單一真源
//!     （engine 不重寫遷移矩陣）。ApiPending 計時器是**非狀態注記**（不改 lifecycle state）,逾時升級
//!     才經單一 mutator 遷 `Rejected`。
//!   - **reduce-only fail-closed**：fill 應用要求 cumulative 非遞減、remaining 非遞增（減倉方向;
//!     f64 僅作方向判別,記帳承載仍 decimal 字串）——無法證明即拒（`ReduceOnlyViolation`）。
//!   - **INV-ORDER 不受影響**：本模塊不產 order 出線 bytes（encoder 在 transport,產 OrderFrame 但
//!     S1 零 production send;effect permit 恆零鑄造）。零真 socket、零 async。
//!   - **default build DCE（W3-W7 B′ 姿態）**：0 production caller（真接線=S4 IPC handler）→ default
//!     artifact DCE。Bybit crypto_perp 不變;無 DB migration;不擴 IPC（IPC 接線=S4）。

// intentional-DCE 姿態繼承 transport/exec_data:本模塊 default build 零 production caller（真接線=S4
// IPC handler 的 preview/submit/cancel/replace）。allow(dead_code) 必保留至 S4 接線移出。
#![allow(dead_code)]

use std::collections::BTreeMap;
use std::time::Duration;

use sha2::{Digest, Sha256};

use openclaw_types::{
    classify_ibkr_paper_restart_recovery, is_operation_transition_allowed, is_transition_allowed,
    BrokerOperation, IbkrPaperOrderLifecycleState, IbkrPaperRestartRecoveryAction,
    IbkrPaperRestartRecoveryInputV1,
};

// ===========================================================================
// (a) config + typed 裁決
// ===========================================================================

/// 生命週期 driver 配置。default = 保守值（參數禁假功能,每項真生效、可觀測）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) struct OrderLifecycleConfig {
    /// **ApiPending 有界 timeout**：訂單於 `BrokerSubmitRequested` 觀測到 IB `ApiPending`（合法暫態,
    /// 訂單未送達 server）後,逾此窗仍未 ack → 升級 `Rejected`（denied;與真 unknown=`StateUnknown`
    /// 分流,§2.2.6）。default 30s（保守;真值待 EA 現勘校準）。
    pub api_pending_timeout: Duration,
}

impl Default for OrderLifecycleConfig {
    fn default() -> Self {
        Self {
            api_pending_timeout: Duration::from_secs(30),
        }
    }
}

/// 生命週期 typed 拒絕（全 typed;呼叫端據此分流,不 panic、不捏值、不默默跳過）。
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub(crate) enum LifecycleReject {
    /// `Create` 的 idempotency_key 已存在（冪等:重複建意圖 = 協議意外,拒併入）。
    #[error("duplicate idempotency key")]
    DuplicateIdempotencyKey,
    /// `Transition`/注記的 idempotency_key 查無意圖（未建先遷 = 協議意外）。
    #[error("unknown idempotency key")]
    UnknownIdempotencyKey,
    /// 遷移非法（types `is_transition_allowed` 拒;含終態不可再遷、StateUnknown 出口窄）。
    #[error("invalid lifecycle transition {from:?} -> {to:?}")]
    InvalidTransition {
        from: IbkrPaperOrderLifecycleState,
        to: IbkrPaperOrderLifecycleState,
    },
    /// operation-scoped 遷移非法（types `is_operation_transition_allowed` 拒;verb 與遷移不符）。
    #[error("operation {operation:?} cannot drive {from:?} -> {to:?}")]
    OperationTransitionMismatch {
        operation: BrokerOperation,
        from: IbkrPaperOrderLifecycleState,
        to: IbkrPaperOrderLifecycleState,
    },
    /// **reduce-only fail-closed**：fill 無法證明減倉安全（cumulative 遞減 / remaining 遞增 / 負值）。
    #[error("reduce-only violation on field {field}")]
    ReduceOnlyViolation { field: &'static str },
    /// fill 欄位 decimal 形狀損壞（非數字）。
    #[error("fill field invalid: {field}")]
    FillFieldInvalid { field: &'static str },
    /// ApiPending 注記於非法起態（僅 `BrokerSubmitRequested` 為合法暫態窗）。
    #[error("api-pending annotation only valid at BrokerSubmitRequested (state={state:?})")]
    ApiPendingInvalidState { state: IbkrPaperOrderLifecycleState },
}

/// fill 增量（cumulative/remaining decimal 字串承載;reduce-only 方向守衛用 f64 判別非記帳）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct FillDelta {
    pub cumulative_filled_decimal: String,
    pub remaining_decimal: String,
}

/// 單一狀態 mutator 的輸入事件（**所有 lifecycle STATE 遷移唯一入口**;Bybit 幻影倉教訓）。
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum LifecycleEvent {
    /// 建立本地意圖（genesis;`LocalIntentCreated`）。冪等真源=`idempotency_key`;`order_id`=nextValidId
    /// 本地分配（replace 復用同一 orderId 覆蓋,見 transport encoder）。
    Create {
        idempotency_key: String,
        order_local_id: String,
        operation: BrokerOperation,
        order_id: i64,
        now_ms: u64,
    },
    /// 遷移現有意圖至 `next_state`（ack/fill/cancel/replace/reject/StateUnknown/ManualReview…）。
    /// `fill` 存在 → 過 reduce-only 守衛;`broker_order_id` 存在 → 掛載（重連可漂移,以 idem key join）。
    Transition {
        idempotency_key: String,
        next_state: IbkrPaperOrderLifecycleState,
        operation: BrokerOperation,
        broker_order_id: Option<i64>,
        fill: Option<FillDelta>,
        now_ms: u64,
    },
}

// ===========================================================================
// (b) IntentRecord（單筆意圖 runtime 態;冪等真源=idempotency_key）
// ===========================================================================

/// reduce-only 單調守衛 epsilon（f64 僅作方向判別容差,非記帳精度）。
const REDUCE_ONLY_EPS: f64 = 1.0e-9;

/// 單筆訂單意圖的 runtime 態。**冪等真源=`idempotency_key`**（client order key）:重連後 broker 回的
/// `broker_order_id` 可能漂移,以 idempotency_key join 意圖與日誌,不以本地 `order_id` 為鍵。
/// （含 f64 方向快取欄 → 不派生 `Eq`;比較用 `PartialEq`。）
#[derive(Debug, Clone, PartialEq)]
pub(crate) struct IntentRecord {
    pub order_local_id: String,
    pub idempotency_key: String,
    /// nextValidId 本地分配的 order-id（可因重連漂移;非冪等鍵）。
    pub order_id: i64,
    /// broker 回報的 order-id（重連可與本地漂移;以 idempotency_key join 掛載）。
    pub broker_order_id: Option<i64>,
    pub operation: BrokerOperation,
    pub state: IbkrPaperOrderLifecycleState,
    /// 累積成交量（記帳定點字串;`None`=尚無 fill）。
    pub cumulative_filled_decimal: Option<String>,
    /// 剩餘量（記帳定點字串）。
    pub remaining_decimal: Option<String>,
    /// reduce-only 方向守衛快取（f64;方向判別非記帳）。
    cumulative_filled_dir: Option<f64>,
    remaining_dir: Option<f64>,
    /// **ApiPending 計時器**（非狀態注記;`Some(ts)`=已觀測 ApiPending,逾 timeout 升級 Rejected）。
    pub api_pending_since_ms: Option<u64>,
    pub created_at_ms: u64,
    pub updated_at_ms: u64,
}

// ===========================================================================
// (c) IntentJournalEntry + hash chain（append-only;竄改可驗）
// ===========================================================================

/// append-only 意圖日誌條目（hash chain:`event_hash = sha256(prev_hash || 正規化欄位)`,genesis
/// prev=""）。runtime 日誌面;durable 驗證投影（`BrokerLifecycleEventLogV1`）+ 三向對賬歸 S3。
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct IntentJournalEntry {
    pub event_sequence: u64,
    pub previous_event_hash: String,
    pub event_hash: String,
    pub event_time_ms: u64,
    pub idempotency_key: String,
    pub order_local_id: String,
    pub broker_order_id: Option<i64>,
    pub previous_state: IbkrPaperOrderLifecycleState,
    pub next_state: IbkrPaperOrderLifecycleState,
    pub operation: BrokerOperation,
}

impl IntentJournalEntry {
    /// 正規化字串（pipe-separated;參與 event_hash 計算,承 live_authorization canonical 紀律）。
    fn canonical(&self) -> String {
        format!(
            "{}|{}|{}|{}|{}|{}|{:?}|{:?}|{:?}",
            self.event_sequence,
            self.previous_event_hash,
            self.event_time_ms,
            self.idempotency_key,
            self.order_local_id,
            self.broker_order_id
                .map(|v| v.to_string())
                .unwrap_or_default(),
            self.previous_state,
            self.next_state,
            self.operation,
        )
    }
}

/// sha256 hex（承 session_attestation `raw_artifact_hash` 慣例）。
fn sha256_hex(input: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(input.as_bytes());
    hex::encode(hasher.finalize())
}

// ===========================================================================
// (d) OrderLifecycleDriver（唯一狀態 mutator + nextValidId + ApiPending + restart recovery）
// ===========================================================================

/// typed 觀測面（單調計數;S4 IPC 投影唯讀消費）。
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub(crate) struct OrderLifecycleAudit {
    /// ApiPending 觀測次數（合法暫態,非錯誤）。
    pub api_pending_observed: u64,
    /// ApiPending 逾 timeout 升級 Rejected 次數（denied;與真 unknown 分流）。
    pub api_pending_timeout_escalations: u64,
    /// reduce-only 守衛拒次數。
    pub reduce_only_violations: u64,
    /// 重啟 recovery 標 StateUnknown 次數。
    pub restart_marked_unknown: u64,
    /// broker order-id drift join 次數（idempotency_key join 掛載漂移 order-id）。
    pub broker_order_id_drift_joins: u64,
}

/// 訂單生命週期 runtime driver。純同步、注入時鐘;**所有狀態遷移經 `apply_lifecycle_event`**。
pub(crate) struct OrderLifecycleDriver {
    config: OrderLifecycleConfig,
    /// nextValidId（取自 session `Ready(...)` 的 `NEXT_VALID_ID=9`;`None`=尚未就緒,不可分配）。
    next_valid_id: Option<i64>,
    /// 本地已分配 order-id 數（下一分配 = next_valid_id + alloc_offset）。
    alloc_offset: i64,
    /// idempotency_key → 意圖（冪等真源;BTreeMap=確定序）。
    intents: BTreeMap<String, IntentRecord>,
    /// append-only 意圖日誌（hash chain）。
    journal: Vec<IntentJournalEntry>,
    last_event_hash: String,
    audit: OrderLifecycleAudit,
}

impl OrderLifecycleDriver {
    pub(crate) fn new(config: OrderLifecycleConfig) -> Self {
        Self {
            config,
            next_valid_id: None,
            alloc_offset: 0,
            intents: BTreeMap::new(),
            journal: Vec::new(),
            last_event_hash: String::new(),
            audit: OrderLifecycleAudit::default(),
        }
    }

    // ---- nextValidId 管理 + order-id 分配 ----

    /// 由 session `Ready(...)` 設 nextValidId（`REQ_IDS=8` 請求 → `NEXT_VALID_ID=9` 回）。重連後
    /// broker 可回新的 nextValidId → 重設基準（本地已分配 offset 不回捲,避免與在途重號）。
    pub(crate) fn set_next_valid_id(&mut self, next_valid_id: i64) {
        self.next_valid_id = Some(next_valid_id);
    }

    /// 本地遞增分配 order-id（`next_valid_id + alloc_offset`;未就緒 → `None`,fail-closed 不猜號）。
    pub(crate) fn allocate_order_id(&mut self) -> Option<i64> {
        let base = self.next_valid_id?;
        let id = base + self.alloc_offset;
        self.alloc_offset += 1;
        Some(id)
    }

    // ---- 唯一狀態 mutator ----

    /// **唯一狀態 mutator**（Bybit 幻影倉教訓:絕無第二狀態寫入路徑;fill/cancel 應用共用此 mutator,
    /// reduce-only fail-closed）。遷移合法性以 types `is_transition_allowed` +
    /// `is_operation_transition_allowed` 為單一真源。任一步 `Err` → 意圖態不變（原子:先驗後寫）。
    pub(crate) fn apply_lifecycle_event(
        &mut self,
        event: LifecycleEvent,
    ) -> Result<IbkrPaperOrderLifecycleState, LifecycleReject> {
        match event {
            LifecycleEvent::Create {
                idempotency_key,
                order_local_id,
                operation,
                order_id,
                now_ms,
            } => {
                if self.intents.contains_key(&idempotency_key) {
                    return Err(LifecycleReject::DuplicateIdempotencyKey);
                }
                let genesis = IbkrPaperOrderLifecycleState::LocalIntentCreated;
                let record = IntentRecord {
                    order_local_id: order_local_id.clone(),
                    idempotency_key: idempotency_key.clone(),
                    order_id,
                    broker_order_id: None,
                    operation,
                    state: genesis,
                    cumulative_filled_decimal: None,
                    remaining_decimal: None,
                    cumulative_filled_dir: None,
                    remaining_dir: None,
                    api_pending_since_ms: None,
                    created_at_ms: now_ms,
                    updated_at_ms: now_ms,
                };
                self.intents.insert(idempotency_key.clone(), record);
                // genesis 日誌條目（prev==next==LocalIntentCreated;建意圖事件）。
                self.append_journal(
                    &idempotency_key,
                    &order_local_id,
                    None,
                    genesis,
                    genesis,
                    operation,
                    now_ms,
                );
                Ok(genesis)
            }
            LifecycleEvent::Transition {
                idempotency_key,
                next_state,
                operation,
                broker_order_id,
                fill,
                now_ms,
            } => {
                // ── phase 1:驗證（不可變借用;先驗後寫,原子——失敗態不變）──
                let (from, prev_cum_dir, prev_rem_dir) = {
                    let r = self
                        .intents
                        .get(&idempotency_key)
                        .ok_or(LifecycleReject::UnknownIdempotencyKey)?;
                    (r.state, r.cumulative_filled_dir, r.remaining_dir)
                };
                // 遷移矩陣（types 單一真源）。
                if !is_transition_allowed(from, next_state) {
                    return Err(LifecycleReject::InvalidTransition {
                        from,
                        to: next_state,
                    });
                }
                if !is_operation_transition_allowed(operation, from, next_state) {
                    return Err(LifecycleReject::OperationTransitionMismatch {
                        operation,
                        from,
                        to: next_state,
                    });
                }
                // reduce-only fail-closed（fill 應用;無法證明減倉安全即拒;純驗證,審計計數於此無 record 借用）。
                let fill_dir = match &fill {
                    Some(fd) => match validate_reduce_only(prev_cum_dir, prev_rem_dir, fd) {
                        Ok(dirs) => Some(dirs),
                        Err(e) => {
                            if matches!(e, LifecycleReject::ReduceOnlyViolation { .. }) {
                                self.audit.reduce_only_violations += 1;
                            }
                            return Err(e);
                        }
                    },
                    None => None,
                };
                // ── phase 2:提交（可變借用;此後不再 Err）──
                let record = self
                    .intents
                    .get_mut(&idempotency_key)
                    .expect("intent present (validated in phase 1)");
                let mut drift_join = false;
                if let Some(boid) = broker_order_id {
                    if record.broker_order_id != Some(boid) {
                        // 以 idempotency_key join 掛載可能漂移的 broker order-id（重連後可變）。
                        drift_join = record.broker_order_id.is_some();
                    }
                    record.broker_order_id = Some(boid);
                }
                if let (Some((cum, rem)), Some(fd)) = (fill_dir, &fill) {
                    record.cumulative_filled_dir = Some(cum);
                    record.remaining_dir = Some(rem);
                    record.cumulative_filled_decimal = Some(fd.cumulative_filled_decimal.clone());
                    record.remaining_decimal = Some(fd.remaining_decimal.clone());
                }
                record.state = next_state;
                record.updated_at_ms = now_ms;
                // 進入非 BrokerSubmitRequested 態 → 清 ApiPending 計時器（暫態窗結束）。
                if next_state != IbkrPaperOrderLifecycleState::BrokerSubmitRequested {
                    record.api_pending_since_ms = None;
                }
                let order_local_id = record.order_local_id.clone();
                let boid = record.broker_order_id;
                if drift_join {
                    self.audit.broker_order_id_drift_joins += 1;
                }
                self.append_journal(
                    &idempotency_key,
                    &order_local_id,
                    boid,
                    from,
                    next_state,
                    operation,
                    now_ms,
                );
                Ok(next_state)
            }
        }
    }

    // ---- ApiPending transient-pending 態分流（§2.2.6）----

    /// 觀測到 IB `ApiPending`（**合法暫態**:訂單未送達 server,非錯誤、非終態）。僅 `BrokerSubmitRequested`
    /// 為合法暫態窗;它**不改 lifecycle state**（非狀態注記,故不經狀態 mutator),只設計時器供逾時升級。
    /// 與 W5-S3 現行「ApiPending 當 UnknownDenied 毒化」對比:此處分流為 transient-pending,不誤毒。
    pub(crate) fn observe_api_pending(
        &mut self,
        idempotency_key: &str,
        now_ms: u64,
    ) -> Result<(), LifecycleReject> {
        let record = self
            .intents
            .get_mut(idempotency_key)
            .ok_or(LifecycleReject::UnknownIdempotencyKey)?;
        if record.state != IbkrPaperOrderLifecycleState::BrokerSubmitRequested {
            return Err(LifecycleReject::ApiPendingInvalidState {
                state: record.state,
            });
        }
        if record.api_pending_since_ms.is_none() {
            record.api_pending_since_ms = Some(now_ms);
        }
        self.audit.api_pending_observed += 1;
        Ok(())
    }

    /// 巡檢 ApiPending 逾時:`BrokerSubmitRequested` 且 ApiPending 計時器逾 `api_pending_timeout`
    /// 仍未 ack → 經**單一 mutator** 升級 `Rejected`（denied;與真 unknown=StateUnknown 分流）。
    /// 回升級的 idempotency_key 列表（觀測用）。
    pub(crate) fn poll_api_pending_timeouts(&mut self, now_ms: u64) -> Vec<String> {
        let timeout_ms = self.config.api_pending_timeout.as_millis() as u64;
        let due: Vec<String> = self
            .intents
            .iter()
            .filter_map(|(key, r)| match r.api_pending_since_ms {
                Some(since)
                    if r.state == IbkrPaperOrderLifecycleState::BrokerSubmitRequested
                        && now_ms.saturating_sub(since) > timeout_ms =>
                {
                    Some(key.clone())
                }
                _ => None,
            })
            .collect();
        let mut escalated = Vec::new();
        for key in due {
            let op = self
                .intents
                .get(&key)
                .map(|r| r.operation)
                .unwrap_or(BrokerOperation::PaperOrderSubmit);
            // 升級 Rejected 經單一 mutator（BrokerSubmitRequested → Rejected 合法遷移）。
            if self
                .apply_lifecycle_event(LifecycleEvent::Transition {
                    idempotency_key: key.clone(),
                    next_state: IbkrPaperOrderLifecycleState::Rejected,
                    operation: op,
                    broker_order_id: None,
                    fill: None,
                    now_ms,
                })
                .is_ok()
            {
                self.audit.api_pending_timeout_escalations += 1;
                escalated.push(key);
            }
        }
        escalated
    }

    // ---- 重啟 recovery（未終態 → MarkStateUnknown;不續用舊授權,對賬前凍結）----

    /// 重連/重啟後對每筆意圖分類 recovery（types `classify_ibkr_paper_restart_recovery` 單一真源）:
    /// terminal+evidence → 保留;broker 態知 → 待 S3 三向對賬;否則 **MarkStateUnknown**（未終態 →
    /// 經單一 mutator 遷 `StateUnknown`,對賬前凍結,不續用舊授權;nonce 一次性）。回 (key, action)。
    /// 註:pre-submit 態（LocalIntentCreated/RustAuthorityAccepted）無 broker 接觸 → `StateUnknown`
    /// 非合法遷移（types 矩陣）→ 該筆本地安全,留原態不強遷（凍結由不再分配新 send 承載,S3 對賬）。
    pub(crate) fn mark_restart_recovery(
        &mut self,
        now_ms: u64,
    ) -> Vec<(String, IbkrPaperRestartRecoveryAction)> {
        let keys: Vec<String> = self.intents.keys().cloned().collect();
        let mut out = Vec::new();
        for key in keys {
            let (action, from, op) = {
                let r = match self.intents.get(&key) {
                    Some(r) => r,
                    None => continue,
                };
                let input = IbkrPaperRestartRecoveryInputV1 {
                    last_local_state: r.state,
                    broker_state_known: false,
                    broker_order_id: r.broker_order_id.map(|v| v.to_string()).unwrap_or_default(),
                    idempotency_key: r.idempotency_key.clone(),
                    terminal_evidence_hash: String::new(),
                };
                (
                    classify_ibkr_paper_restart_recovery(&input),
                    r.state,
                    r.operation,
                )
            };
            // recovery MarkStateUnknown 是系統事件（非原始 broker verb）→ 以 from-態選 types 矩陣
            // 允許 `from → StateUnknown` 的 operation（op-scoped 檢仍是單一真源,不放寬）。`op` 綁定
            // 原意圖 operation,僅用於矩陣不覆蓋時的保守回退（實際恆由 recovery_op 命中）。
            let _ = op;
            if action == IbkrPaperRestartRecoveryAction::MarkStateUnknown
                && is_transition_allowed(from, IbkrPaperOrderLifecycleState::StateUnknown)
            {
                if let Some(recovery_op) = state_unknown_recovery_op(from) {
                    if self
                        .apply_lifecycle_event(LifecycleEvent::Transition {
                            idempotency_key: key.clone(),
                            next_state: IbkrPaperOrderLifecycleState::StateUnknown,
                            operation: recovery_op,
                            broker_order_id: None,
                            fill: None,
                            now_ms,
                        })
                        .is_ok()
                    {
                        self.audit.restart_marked_unknown += 1;
                    }
                }
            }
            out.push((key, action));
        }
        out
    }

    // ---- 日誌 append + 觀測 ----

    /// append hash-chain 日誌條目（`event_hash = sha256(prev_hash || 正規化)`;genesis prev=""）。
    #[allow(clippy::too_many_arguments)]
    fn append_journal(
        &mut self,
        idempotency_key: &str,
        order_local_id: &str,
        broker_order_id: Option<i64>,
        previous_state: IbkrPaperOrderLifecycleState,
        next_state: IbkrPaperOrderLifecycleState,
        operation: BrokerOperation,
        now_ms: u64,
    ) {
        let mut entry = IntentJournalEntry {
            event_sequence: self.journal.len() as u64 + 1,
            previous_event_hash: self.last_event_hash.clone(),
            event_hash: String::new(),
            event_time_ms: now_ms,
            idempotency_key: idempotency_key.to_string(),
            order_local_id: order_local_id.to_string(),
            broker_order_id,
            previous_state,
            next_state,
            operation,
        };
        entry.event_hash = sha256_hex(&entry.canonical());
        self.last_event_hash = entry.event_hash.clone();
        self.journal.push(entry);
    }

    /// idempotency_key join（冪等真源查詢;非以本地/broker order-id 為鍵——後者重連可漂移）。
    pub(crate) fn intent_by_idempotency_key(&self, key: &str) -> Option<&IntentRecord> {
        self.intents.get(key)
    }

    /// 意圖唯讀迭代（確定序）。
    pub(crate) fn intents(&self) -> impl Iterator<Item = &IntentRecord> {
        self.intents.values()
    }

    /// append-only 日誌唯讀檢視。
    pub(crate) fn journal(&self) -> &[IntentJournalEntry] {
        &self.journal
    }

    /// hash chain 完整性驗證（逐條重算 + prev 鏈接;竄改可測）。
    pub(crate) fn verify_chain(&self) -> bool {
        let mut prev = String::new();
        for entry in &self.journal {
            if entry.previous_event_hash != prev {
                return false;
            }
            if entry.event_hash != sha256_hex(&entry.canonical()) {
                return false;
            }
            prev = entry.event_hash.clone();
        }
        true
    }

    /// 觀測面唯讀檢視。
    pub(crate) fn audit(&self) -> &OrderLifecycleAudit {
        &self.audit
    }
}

/// restart-recovery 標 StateUnknown 的 operation 選擇（系統事件;回 types 矩陣允許
/// `from → StateUnknown` 的 verb;不放寬 op-scoped 檢——僅選命中該遷移的 verb）。pre-submit 態
/// （LocalIntentCreated/RustAuthorityAccepted）無 →StateUnknown 遷移 → `None`（本地安全,不強遷）。
fn state_unknown_recovery_op(from: IbkrPaperOrderLifecycleState) -> Option<BrokerOperation> {
    use IbkrPaperOrderLifecycleState as State;
    match from {
        State::BrokerSubmitRequested => Some(BrokerOperation::PaperOrderSubmit),
        State::BrokerAcknowledged | State::PartiallyFilled | State::Replaced => {
            Some(BrokerOperation::PaperOrderFillImport)
        }
        State::CancelRequested => Some(BrokerOperation::PaperOrderCancel),
        State::ReplaceRequested => Some(BrokerOperation::PaperOrderReplace),
        _ => None,
    }
}

/// decimal 字串 → f64（**僅** reduce-only 方向判別用,非記帳;非數字 → `None`,fail-closed）。
fn parse_dir(raw: &str) -> Option<f64> {
    raw.parse::<f64>().ok()
}

/// reduce-only 純守衛（無 record 借用;f64 僅方向判別,記帳承載 decimal 字串於 commit 階段）。
/// cumulative 非遞減、remaining 非遞增、皆非負;違反 → `ReduceOnlyViolation`（無法證明減倉安全即拒）。
/// 回 `(cum, rem)` f64 供 commit 階段快取方向。
fn validate_reduce_only(
    prev_cum: Option<f64>,
    prev_rem: Option<f64>,
    fd: &FillDelta,
) -> Result<(f64, f64), LifecycleReject> {
    let cum =
        parse_dir(&fd.cumulative_filled_decimal).ok_or(LifecycleReject::FillFieldInvalid {
            field: "cumulative_filled",
        })?;
    let rem = parse_dir(&fd.remaining_decimal)
        .ok_or(LifecycleReject::FillFieldInvalid { field: "remaining" })?;
    if cum < 0.0 {
        return Err(LifecycleReject::ReduceOnlyViolation {
            field: "cumulative_filled_negative",
        });
    }
    if rem < 0.0 {
        return Err(LifecycleReject::ReduceOnlyViolation {
            field: "remaining_negative",
        });
    }
    if let Some(prev) = prev_cum {
        if cum + REDUCE_ONLY_EPS < prev {
            return Err(LifecycleReject::ReduceOnlyViolation {
                field: "cumulative_filled_decreased",
            });
        }
    }
    if let Some(prev) = prev_rem {
        if rem > prev + REDUCE_ONLY_EPS {
            return Err(LifecycleReject::ReduceOnlyViolation {
                field: "remaining_increased",
            });
        }
    }
    Ok((cum, rem))
}

#[cfg(test)]
#[path = "ibkr_tws_order_lifecycle_tests.rs"]
mod tests;
