# PA Sign-off — Decision Lease Three-Way Review (Path A)
# 2026-05-02 · PM × PA × FA · P0-GOV-1

**HEAD**: `a7b93d5`
**Reference agenda**: `docs/CCAgentWorkSpace/PM/2026-05-02--decision_lease_review_agenda.md` (commit `548b145`)
**PA archaeology source**: subagent `a4966c8b96da6fb1b` (2026-05-02), reconfirmed by direct file read in this report.

---

## 1. PA archaeology 結論再確認（含 push back 自查）

**結論不變：路徑 A 仍然強推薦**。重新走過代碼後三條核心事實都成立：

1. `rust/openclaw_core/src/sm/lease.rs` 747 LOC，14 個 public API 全在（`create_draft / register / activate / bridge / consume / freeze / revoke / reject / expire / check_expiry / get / get_live / get_bridgeable / revoke_all_live`），9 個 `LeaseState` enum 完整。
2. `rust/openclaw_core/src/governance_core.rs` 584 LOC，`pub lease: DecisionLeaseSm` 直接持有，`GovernanceProfile::requires_lease()` Production=true 已宣告（line 72-77），但**沒有 `acquire_lease()` / `release_lease()` facade**。
3. `rust/openclaw_engine/src/intent_processor/router.rs:81` 是 `Gate 1: governance.is_authorized()` 唯一一處 governance 觸發；之後 Gate 1.5 / 1.6 / 2 (Guardian) / 3 (cost_gate) 全部不觸 lease。

**1 個 PA archaeology 漏報 — 補上**：

`process_with_features` 接 `governance: &GovernanceCore`（line 72，**immutable reference**）。但 `acquire_lease()` 必走 `lease.create_draft + register + activate` 三步，皆需 `&mut self`。這意味著 **R-04 不只是「加 facade」而已**，還必須選擇 mutability 策略：
- 選項 A：把 `process_with_features(governance: &mut GovernanceCore)` 全鏈改成 `&mut`（call site = `commands.rs:94` + 4 處 tick pipeline），最乾淨但 ripple 大。
- 選項 B：在 `GovernanceCore` 內把 `lease: DecisionLeaseSm` 改 `lease: Mutex<DecisionLeaseSm>` 或 `RwLock<DecisionLeaseSm>` 做 interior mutability，外部簽名不動，加鎖開銷 ~50ns。
- 選項 C：把 `acquire_lease` 做成 `&self` + `&AtomicU64` lease_id counter + 內部 `Mutex<DecisionLeaseSm>` only at SM mutation 點，比 B 更精細。

**PA 推薦選項 B**：lockless hot path 不是必要（lease 只在 Production profile 觸發，profile=Exploration/Validation skip），Mutex 開銷在 hot-path 性能 budget 內，且不破壞現有 `&self.governance` borrow chain（`commands.rs:94` 與 `tick_pipeline/mod.rs:723` 多處 read-only consumer 不需改）。**這是路徑 A 的隱性 +50 LOC + 1 個 unit test，PM 必須知道此細節再派 E1**。

**工作量重估（含 mutability 策略）**：
- 原估：1.5-2 E1（Rust 300-500 行 + Python 50 行 IPC + 70 行 test）
- 修正：**1.7-2.2 E1**，Rust 350-550 行（含 Mutex wrapper + facade + IPC handler + 2 個 router gate insertion + 風險 fail-closed path）+ Python 50-80 行（IPC client + backward-compat shim + 雙寫過渡 metric） + 90 行 test（22 unit + 1 integration + 1 IPC e2e）。

**雙寫過渡期 4 週仍合理**，但 PA push back 一條：**deprecate Python 平面前必須驗證 `agent.messages / state_changes / ai_invocations` all-time 0 row 問題（18 blocker #6）已修**。因為 lease IPC writes 進入 `governance` schema 後，audit reconstruction（DOC01-R07 6-element）會**從 Python 平面挪到 Rust + DB**，若 audit writer 仍 0 row → Rust 平面 acquire_lease 寫無 outcome → 反而把問題藏得更深。**Path A retrofit 必須與 18 blocker #6 audit writer fix 同 sprint 完成或前置**。

---

## 2. R-04 retrofit task spec

### 2.1 Rust facade 接口簽名（`openclaw_core::governance_core`）

```rust
/// Lease ID type — opaque u64 from existing lease SM internal index, prefixed
/// at IPC boundary to avoid Python/Rust namespace collision during dual-write.
pub type LeaseId = usize;

#[derive(Debug, thiserror::Error)]
pub enum LeaseError {
    #[error("governance not authorized")]
    NotAuthorized,
    #[error("profile {0:?} does not require lease")]
    ProfileSkip(GovernanceProfile),  // not an error per se, signal for caller to skip
    #[error("auth scope mismatch: {0}")]
    ScopeMismatch(String),
    #[error("internal SM error: {0}")]
    SmError(#[from] SmError),
    #[error("lease not found: {0}")]
    NotFound(LeaseId),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LeaseOutcome {
    Consumed,  // success path — execution succeeded
    Revoked,   // failure path — execution rejected/failed
}

impl GovernanceCore {
    /// Acquire a per-intent lease. Hot-path call: only triggers when
    /// `profile.requires_lease()` is true (Production only).
    /// 為單筆意圖獲取 lease。Hot-path：僅 Production profile 觸發。
    ///
    /// # Mutability
    /// Internally takes `&self` via `Mutex<DecisionLeaseSm>` interior
    /// mutability. ~50ns lock overhead acceptable per perf budget.
    pub fn acquire_lease(
        &self,
        intent_id: &str,
        scope: &str,           // "TRADE_ENTRY" | "TRADE_EXIT" | future scopes
        ttl_ms: u64,           // recommended 30_000 = 30s, configurable per scope
    ) -> Result<LeaseId, LeaseError>;

    /// Release a lease after execution. `outcome=Consumed` for success,
    /// `Revoked` for failure (matches Python `release_lease(consumed: bool)`).
    pub fn release_lease(
        &self,
        lease_id: LeaseId,
        outcome: LeaseOutcome,
    ) -> Result<(), LeaseError>;
}
```

**Mutability**: `lease: DecisionLeaseSm` field 包 `parking_lot::Mutex<DecisionLeaseSm>`（**非** `std::sync::Mutex`，避免 poisoning + 更快）。`execute_risk_cascade()` 既有 `&mut self` 簽名不動。**內部 `revoke_all_live()` cascade path 改用 `self.lease.lock()`**，single-mutator invariant 保 lock 不爭用。

### 2.2 IPC schema（Python ↔ Rust）

**RPC method**: `governance.acquire_lease` / `governance.release_lease`（namespace 對齊現有 `force_governor_*` 風格，但加一級 dot-namespace 區別 lease vs profile ops）。

**Acquire request**:
```json
{
  "method": "governance.acquire_lease",
  "params": {
    "intent_id": "py_<uuid>",
    "scope": "TRADE_ENTRY",
    "ttl_ms": 30000
  }
}
```

**Acquire response**:
```json
// Success
{ "result": { "lease_id": 42, "expires_at_ms": 1714676000000 } }
// Skip (profile != Production)
{ "result": { "lease_id": null, "skip_reason": "profile_does_not_require_lease" } }
// Error (fail-closed)
{ "error": { "code": -32000, "message": "governance not authorized" } }
```

**Release request**:
```json
{
  "method": "governance.release_lease",
  "params": {
    "lease_id": 42,
    "outcome": "consumed"  // or "revoked"
  }
}
```

**Error case enumeration**:
| Error code | Cause | Fail-closed action |
|---|---|---|
| `-32000` `not_authorized` | governance.is_authorized()=false | 拒絕 intent（caller 不下單） |
| `-32001` `scope_mismatch` | auth 不允許此 scope | 拒絕 intent |
| `-32002` `sm_error` | DecisionLeaseSm transition 拒絕 | 拒絕 intent |
| `-32003` `not_found` | release 階段 lease_id 已不存在 | log warn，仍執行（執行已過 acquire gate） |
| `-32099` `ipc_failure` | 連線/timeout | 拒絕 intent（Python caller fail-closed） |

### 2.3 Router gate 加裝點

**位置**：`rust/openclaw_engine/src/intent_processor/router.rs:81-83` 之後，`reducing_existing_qty` 計算 (line 118) 之前。**新加 Gate 1.7**（Gate 1.6 是 negative balance guard，已存在）。

**插入代碼**（PA 設計，E1 直接抄）：
```rust
// Gate 1.7: Decision Lease (per-intent authorization, Production profile only)
// 1.7：每筆意圖 lease（僅 Production profile）
let lease_handle: Option<LeaseId> = if profile.requires_lease() {
    let intent_id = format!("rs_{}_{}", intent.symbol, openclaw_core::now_ms());
    let scope = if reducing_existing_qty.is_some() { "TRADE_EXIT" } else { "TRADE_ENTRY" };
    match governance.acquire_lease(&intent_id, scope, 30_000) {
        Ok(id) => Some(id),
        Err(e) => {
            // Fail-closed: lease denied → reject intent
            return IntentResult::rejected(RejectionCode::LeaseDenied {
                reason: e.to_string(),
            }.format());
        }
    }
} else {
    None
};
```

**Release 時機**：function epilogue 5 處（IntentResult::approved/modified/rejected 各回傳前）必加：
```rust
if let Some(id) = lease_handle {
    let outcome = if matches!(result.verdict, Verdict::Approved | Verdict::Modified) {
        LeaseOutcome::Consumed
    } else {
        LeaseOutcome::Revoked
    };
    let _ = governance.release_lease(id, outcome);  // log-only on error
}
```

**或**包成 RAII guard（`LeaseGuard` struct + Drop trait）讓 release 自動觸發 — PA 推薦此方案，避免 5 處 epilogue 漏處理。**E1 自決，但 E2 必查 5 個出口都有 release**。

`RejectionCode::LeaseDenied { reason: String }` 變體加進 `intent_processor/rejection_coding.rs`（已 split-out，2026-05 commit `d6f7572`）。

### 2.4 lease_id namespace prefix

確認 OK，但**精確化**：
- **Rust 平面 acquire 的 lease**：internal `LeaseId = usize`（lease.rs SM 內部 index）；IPC 對外時格式為 `"rs_<intent_id>_<usize>"` 字串
- **Python 平面 acquire 的 lease**（過渡期）：`governance_hub.acquire_lease()` 既有 UUID 字串 `"py_<uuid>"` 不變
- **dual-write monitoring**：`agent.messages` 表加 `lease_origin` enum 欄位 (`"rust" | "python"`)，audit 可分平面查
- **過渡期結束後**：Python 改 IPC 轉呼 → 統一 `"rs_*"` namespace

### 2.5 雙寫過渡期 monitoring

**4 週期間 metric**（cron 每 1h sample，存 `monitoring.lease_dual_write_metrics`）：

| Metric | 閾值 | 行動 |
|---|---|---|
| `ipc_failure_rate` (release_lease) | >1% / 1h | 警告 |
| `ipc_failure_rate` (acquire_lease) | >0.5% / 1h | **即時回退** Python local SM |
| `ipc_p99_latency_ms` (acquire) | >5ms | 警告（hot-path budget） |
| `dual_plane_drift_count` (Python lease 寫但 Rust 0 row) | >0 | 即查 dispatch wiring |
| `lease_id_collision_count` | =0（必） | 即查 namespace prefix 漏 |

**回退條件**（即時 trigger，無人介入）：
- `acquire_lease` IPC failure rate ≥0.5% 連續 30 min → ExecutorAgent 切回 Python local SM（保留兩套代碼直到過渡結束）
- 過渡 4 週末 metric 全綠 → PR 刪 Python local SM 真相（保留 IPC client shim），Python 平面 deprecate

**Deprecate Python 平面 criteria**（必全部 PASS 才能刪 Python `_lease_sm`）：
1. ≥21 連續 day acquire_lease IPC 0 failure
2. ≥21 連續 day Python local SM 0 fallback
3. `agent.messages.lease_origin='rust'` row count ≥ Python 平面 baseline ×0.95
4. **18 blocker #6（agent.messages / state_changes / ai_invocations 0 row）已 GREEN**
5. PA + FA 雙簽 deprecate PR

---

## 3. 與其他 P0 work 的依賴關係

| Work item | 關係 | 排程建議 |
|---|---|---|
| **P0-EDGE-2 / P0-3 edge decision (~05-15)** | **無代碼依賴**，但有資源依賴：edge decision 期間 PM/PA 注意力都在 strategy edge，retrofit 同期派發會排擠 review 帶寬 | **05-15 後啟動**（並行於 LG-2/3/4 IMPL） |
| **18 blocker #6（audit writer 0 row）** | **強依賴**：retrofit 後 lease audit 落 DB，若 writer 0 row → audit reconstruction 反而退化 | **必須前置**或同 sprint 完成 |
| **LG-2 H0 blocking IMPL** | 弱依賴：LG-2 走 H0 gate，retrofit 後 H0 也可走 lease 路徑（spec 一致） | **可並行**，無阻塞 |
| **LG-3 provider pricing binding** | 0 依賴 | **可並行** |
| **LG-4 supervised live IMPL** | 中度依賴：LG-4 SM 涉及 lease state，retrofit 完成後 LG-4 IMPL 接口較乾淨 | **建議 retrofit 前 1 sprint 不啟動 LG-4 IMPL**（讓 retrofit 先穩） |
| **LG-5 W3 FUP-1 reviewer（sibling CC `463890d`）** | **單向依賴**：LG-5 reviewer 走 lease 路徑寫 audit row（B-finding, FUP-1 的 attribution 需要 lease ID 6-element auth）；retrofit 後 LG-5 reviewer 會自動 pickup Rust lease | **無需阻塞**：FUP-1 已 land 待 deploy；retrofit 完成後 W3 自動補強，FUP-1 寫的 review row 會自帶 Rust lease_id（取代 Python `py_*` 為 `rs_*`） |

**最終排程建議**：retrofit task 派發時間 = **2026-05-15 後**（P0-EDGE-2 結 + 18 blocker #6 audit writer 同 sprint 啟動），與 LG-2/3 IMPL 並行，比 LG-4 IMPL 早 1 sprint。

---

## 4. 風險預估 + 緩解（5 條）

| # | 風險 | 機率 | 影響 | 緩解 |
|---|---|---|---|---|
| **R1** | **Hot-path latency regression**（Production profile +10µs SM activate ＋ Mutex lock ~50ns＝~10.05µs） | 中 | 中（hot-path SLA <1ms 仍遠在內，但 grid_trading 12 sym × 200 tick/s × +10µs = +24ms/s CPU 增量，需 profile 驗） | E1 task spec 含 `cargo bench --bench intent_processor_lease` 對比 baseline；E4 跑 1h smoke 驗 P99 不漂；超 P99 +5% 就回退 mutability 策略至選項 C（內 Atomic counter） |
| **R2** | **IPC failure 對交易影響**（Python ExecutorAgent acquire_lease 切 IPC 後若 socket down → 0 intent 通過） | 低（unix socket 99.99% uptime，過去 30d 0 故障） | 高（fail-closed 拒絕 = 整 ExecutorAgent 路徑停擺） | dual-write 過渡 4 週期 Python local SM 保留作 fallback；IPC failure ≥0.5%/30min 自動切回 Python local SM；wave 結束前不切硬模式 |
| **R3** | **Schema migration / lease_id collision** | 低 | 中（dual-plane 期 audit 雙計） | namespace prefix `rs_` / `py_` + `agent.messages.lease_origin` enum；CI invariant test：「同 intent_id 不可有兩條不同 lease_id 寫入」 |
| **R4** | **過渡期 audit 雙計 / 對應錯亂**（同一筆 intent Python 寫 lease A、Rust 也寫 lease B，6-element auth 取哪個？） | 中（過渡期內 ExecutorAgent 路徑唯一活躍 caller，IntentProcessor 走 Production profile 才觸發 → 兩平面同時 fire = 真實情境） | 中 | 過渡期 ExecutorAgent acquire_lease 改為 IPC-only（**不雙寫**），保 Python local SM 僅作 IPC failure fallback；audit 6-element auth 取 IPC 結果為主、Python local SM 為 secondary trace；amendment 文件明寫此優先級 |
| **R5** | **Mutex poisoning / lock 爭用 deadlock**（cascade revoke 走 `&mut self`，acquire_lease 走 `&self + Mutex` → 若同一 thread 同時 hold cascade lock 又 try acquire_lease 死鎖） | 低 | 極高（engine hang） | 用 `parking_lot::Mutex`（非 poisoning）+ static 分析：cascade 與 acquire 在 call graph 上無 nested call（cascade 僅由 risk_governor SM 升級 broadcaster 觸發，不在 router hot path）；E2 必查 lock acquisition order；E4 加一個 deadlock detection test（兩 thread 同時 cascade + acquire） |

---

## 5. PA Sign-off Statement

```
PA sign-off (2026-05-02): Path A approved. R-04 retrofit task spec attached
at docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--decision_lease_review_signoff.md.

Estimated 1.7-2.2 E1 task (Rust 350-550 LOC + Python 50-80 LOC IPC + 90 LOC test).
Hot-path overhead acceptable per `parking_lot::Mutex` interior mutability strategy
(~50ns lock + ~10µs SM activate, Production profile only, well under 1ms SLA).

Recommend dispatch after 2026-05-15 P0-EDGE-2 edge decision, parallel with LG-2/3
IMPL, 1 sprint before LG-4 IMPL. Hard prerequisite: 18 blocker #6 (agent.messages
0-row) audit writer fix must land same sprint or before, otherwise retrofit hides
audit reconstruction failure.

Risk mitigations: (1) cargo bench gate on hot-path P99 regression ≤+5%;
(2) dual-write 4-week with Python local SM fallback on IPC failure ≥0.5%/30min;
(3) lease_id namespace prefix rs_/py_ + agent.messages.lease_origin enum;
(4) ExecutorAgent IPC-only during transition (no double-write); (5) parking_lot
Mutex + lock acquisition order static check + deadlock detection test.

Co-signed pending: FA spec amendment, PM E1 dispatch.
```

---

## 6. 關鍵 push back（給 PM 主會話）

**唯一 blocker-style push back**：

> **Path A retrofit 必須與 18 blocker #6（`agent.messages / state_changes / ai_invocations` all-time 0 row）audit writer fix 綁同 sprint 完成或前置。**
>
> 理由：retrofit 後 Rust 平面 lease audit row 會落 `agent.messages`/`governance.lease_events` 表，若 writer 仍 0 row → 等於把 Python 平面的可審計性挪到 Rust 平面再次失防，DOC01-R07 6-element auth reconstruction 退化更深。**單獨派 R-04 而 #6 還在 0 row 狀態 = 治理債放大，不是修復**。

PM 決策時若選擇先做 R-04 不等 #6，PA 立場改為「Conditional approval」需 amendment 文件補一段「Phase 1 retrofit 不寫 audit row，Phase 2 補 audit writer 後一次性 backfill」，但這條路 FA 大機率擋（spec amendment scope 擴大）。

---

**PA 簽核完成**。下游：FA spec archaeology sign-off → PM 三方 commit。
