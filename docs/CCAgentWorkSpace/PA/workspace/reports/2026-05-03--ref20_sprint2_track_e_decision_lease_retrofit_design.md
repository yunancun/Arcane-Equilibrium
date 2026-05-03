# REF-20 Sprint 2 Track E — Decision Lease Retrofit (AMD-2026-05-02-01) PA 設計

**日期：** 2026-05-03
**Owner：** PA
**Sprint scope：** REF-20 Sprint 2 開工 / 解 18 Live Blocker #5（Decision Lease Rust 熱路徑 0 觸發）+ #6（agent 三表 all-time 0 row）
**對應 Amendment：** `docs/governance_dev/amendments/2026-05-02--SM-02_R04_retrofit_path_a.md`
**派發排程：** ~2026-05-15 P0-EDGE-2 後與 LG-2/3 並行；必先於 LG-4 IMPL
**Read-only：** 不寫業務碼，僅派發 / 接口 / 依賴 / 風險

---

## §1. Sprint 起點事實重申

### 1.1 既有資產（已落地，不需改）

| 模組 | 路徑 | 狀態 |
|---|---|---|
| Rust SM `DecisionLeaseSm` 9 狀態 / 20 transitions / 12 forbidden / 5 guards | `srv/rust/openclaw_core/src/sm/lease.rs` | ✅ 完整 + 9 unit test PASS |
| Rust `GovernanceCore { pub lease: DecisionLeaseSm, ... }` | `srv/rust/openclaw_core/src/governance_core.rs` | ✅ 持有 lease，但僅 cascade 路徑用（`revoke_all_live` / `check_expiry` / `lease_backup`） |
| `GovernanceProfile::requires_lease()` Production=true | `governance_core.rs:72` | ✅ 已宣告 |
| Python `governance_hub.acquire_lease()` 740 LOC | `app/governance_hub.py:693` | ✅ 唯一 production caller `executor_agent.py:454` |
| `executor_agent.py shadow_mode_provider` G3-03 Phase B | `executor_agent.py:185` | ⚠️ `lambda: True` fail-close default → per-intent lease 流量近 0（P1-FAKE-1 待修） |
| V050 `replay.simulated_fills.decision_lease_id TEXT nullable` | `sql/migrations/V050__replay_simulated_fills.sql:162` | ✅ Sprint 1 已 land；當前 0 caller，placeholder column 待 retrofit 後啟用 |
| V003 agent 三表（messages / state_changes / ai_invocations）| `sql/migrations/V003__trading_agent_tables.sql:330+` | ✅ schema 在；all-time 0 row 是 writer 接線缺失非 schema 缺失 |
| V053 `governance_audit_log` event_type CHECK 13 值 | `sql/migrations/V053__governance_audit_log_replay_event_types.sql` | ✅ Sprint 1 land；retrofit 將追加 7 個 lease event_type（V054） |

### 1.2 真實 retrofit gap（last-mile）

1. **Rust facade 缺**：`GovernanceCore` 沒有 `acquire_lease(intent_id, scope, ttl_ms)` 一條龍方法封裝 `create_draft → register → activate`（Python 端 `governance_hub.acquire_lease()` 內部就做這件事，Rust 等義 facade 缺）
2. **Rust router gate 缺**：`intent_processor/router.rs::process_with_features()` 與 `process_gates_only_with_features()` 在 Gate 1（is_authorized）通過後 → **直接到 Gate 1.5（duplicate position）**，中間無 lease gate；`profile.requires_lease()` 雖宣告 Production=true 但 0 處 enforce
3. **Python IPC bridge 缺**：`governance_hub.acquire_lease()` 仍是純 Python local SM 實作；retrofit 後改為 IPC 轉呼 Rust（保 backward-compat 簽名）
4. **agent 三表 writer 缺**：`MessageBus._audit_callback` (`multi_agent_framework.py:309`) 接 `agent_audit_bridge.make_agent_audit_callback(...)` 走 `gov_hub._change_audit_log`，但 **這條路徑寫的是 `governance_audit_log`，不是 `agent.messages` / `state_changes` / `ai_invocations`**；三表 writer 從 V003 land（2025）至今 0 接線
5. **lease_transitions 表缺**：amendment §4 AC-1 條件「`learning.lease_transitions` distinct count ≥ 5」目前 0 表 — V054 同 sprint 必須建表

### 1.3 Rust SM impedance mismatch

| 介面 | Python `_lease_sm` | Rust `DecisionLeaseSm` |
|---|---|---|
| `create_draft(intent, ...)` 回傳 | `lease_id: str` 直接 | `idx: usize`（Vec index） |
| `register(handle)` 收 | `lease_id: str` | `idx: usize` |
| `activate(handle)` 收 | `lease_id: str` | `idx: usize` |
| `get(handle)` 收 | `lease_id: str` | `idx: usize` |

→ Rust facade 必須維護 `HashMap<String, usize>` 反查表（內部 hidden）；對外 API 用 `lease_id: String`（與 Python 對等）。**LeaseObject 內已有 `pub lease_id: String`**，所以 Rust 端只需 facade 加 lookup helper，不需動 lease.rs 既有 9 unit test。

---

## §2. Task Partition 表

### 2.1 4-task DAG（依賴 + 並行）

```
                  ┌───────────────────────────────────────────────────────┐
   START ──┬────→ │ Task E1 (Rust facade + Mutex + audit hooks)           │
           │      └───────────────────────────────────────────────────────┘
           │                                  ↓ facade ready
           │      ┌─────────────────────┬────┴───────────────────────────┐
           │      ↓                     ↓                                ↓
           ├──→ Task E2          Task E3                        Task E4 (parallel）
           │   (Rust router      (Python IPC bridge             (V054 schema +
           │    gate enable)      governance_hub.py改寫)         lease_transitions
           │                                                     writer + agent
           │                                                     三表 writer)
           │                                  ↓ all 4 land
           │      ┌──────────────────────────────────────────────────────┐
           └──→   │ E2 review + E4 regression + AC-1~5 driver E2E        │
                  └──────────────────────────────────────────────────────┘
```

**依賴：** Task E1 必先（其餘 3 task 都需要 facade 簽名 lock-in）。E2/E3/E4 一旦 E1 land 即全並行。Task E2 純 Rust 跨 2 file（`router.rs` + `step_4_5_dispatch.rs` 註）；Task E3 純 Python 1 file（`governance_hub.py`）；Task E4 跨 SQL + Rust + Python（檔不重疊 E2/E3）。最大並行 3 E1。

### 2.2 Task 詳表

| Task ID | 路徑 | 範圍 | 並行 | 預估 | 改動風險 |
|---|---|---|---|---|---|
| **E-1: Rust facade** | `srv/rust/openclaw_core/src/governance_core.rs`（+ 新檔 `srv/rust/openclaw_core/src/sm/lease_facade.rs` 或內聯）| 加 `acquire_lease(intent_id, scope, ttl_ms, profile, source_stage) -> Result<LeaseId, GovernanceError>`、`release_lease(lease_id, outcome) -> Result<(), GovernanceError>`、`get_lease_by_id(lease_id) -> Option<&LeaseObject>`；內部維護 `HashMap<String, usize>` lease_id→idx 反查；爆露 `pub fn lease_audit_emit_hook(...)` 供 writer 接 lease_transitions；amendment §3 點 1+2 全條落地；**注意**：interior mutability — `pub lease: DecisionLeaseSm` 改為 `pub lease: parking_lot::Mutex<DecisionLeaseSm>` 讓 `&GovernanceCore` 可透過 `lock()` 修改 SM；既有 cascade（`revoke_all_live` 等 `&mut self`）改寫為 `self.lease.lock()` 內部 borrow；新增 14 個 unit test（每 transition + facade happy path） | A | 0.8 day | **高** — 改 governance_core.rs 既有 5 處 `&mut self` cascade（execute_risk_cascade L175 / evaluate_and_cascade L254 / grant_paper_authorization L331 / check_expiry L347 / 5 sites in tests），全部需用 `lock()` 重寫 |
| **E-2: Rust router gate** | `srv/rust/openclaw_engine/src/intent_processor/router.rs`、`srv/rust/openclaw_engine/src/intent_processor/mod.rs`（IntentResult/ExchangeGateResult 加 `lease_id: Option<String>`）| `process_with_features()` Gate 1（is_authorized）後加 Gate 1.4（lease）：`if profile.requires_lease() { let lease = governance.acquire_lease(...)? else fail-closed }`；`process_gates_only_with_features()` 同步加 Gate 1.4；fill 完成後 `governance.release_lease(lease_id, Consumed)`，被拒則 `Revoked`；IntentResult/ExchangeGateResult 加 `pub lease_id: Option<String>` 由 caller (step_4_5_dispatch.rs) 寫 `replay.simulated_fills.decision_lease_id` | A（依賴 E-1） | 0.6 day | **極高** — 觸發 hot path；router.rs L81 `is_authorized()` Gate 1 後立即添加新 gate 影響所有 paper/demo/live intent；fail-closed 行為若 lease 失敗 → demo intent 也被拒（要靠 profile.requires_lease() Validation=false 短路） |
| **E-3: Python IPC bridge** | `srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub.py`（L693-783 重寫）| `acquire_lease(intent_id, scope, ttl_seconds)` 改為 IPC 轉呼 Rust：用 既有 `ipc_dispatch.py` send `{"method":"governance.acquire_lease", "params":{...}}`；保簽名 backward-compat（仍回 `Optional[str]`）；Rust 端 `dispatch.rs` 加 `governance.acquire_lease/release_lease` two methods（IPC 端口落 `OPENCLAW_DATA_DIR/control.sock`）；fallback 路徑：IPC 失敗 → log warn + return None（fail-closed，executor_agent.py L466 既有的 fail-close 路徑接住）；Dual-write 期間（amendment §5.1 +4 週）lease_id namespace prefix `py_*` Python local fallback / `rs_*` Rust 主路徑；retrofit 完成後 namespace 自動透過 IPC 統一為 `rs_*` | B（依賴 E-1 facade 完成 lock-in IPC schema）| 0.6 day | **高** — IPC failure rate amendment §6 條件 #2 < 0.5%/day 否則回退；Python 平面 fallback 不可移除否則 IPC 死即所有 Python caller 死 |
| **E-4: V054 schema + audit writer** | 新建：`srv/sql/migrations/V054__lease_transitions_and_agent_audit_writer_tables.sql`、新建：`srv/rust/openclaw_engine/src/database/lease_transition_writer.rs`、新檔/改：`srv/program_code/.../app/agent_audit_bridge.py`（追加三表 writer side-effect）| **V054 SQL**：(1) 新表 `learning.lease_transitions` 含 `transition_id PK / lease_id / from_state / to_state / event / initiator / reason_codes / requires_approval / approved_by / profile / engine_mode / context_id / ts_ms / created_at`；(2) `governance_audit_log` event_type CHECK 加 7 個 lease event types（lease_acquired / lease_activated / lease_consumed / lease_revoked / lease_frozen / lease_expired / lease_rejected）；Guard A/B/C 全套 + 雙語；**Rust writer**：`lease_transition_writer.rs` 新 actor 訂閱 GovernanceCore 內 transition emit channel（Mutex 改後加一個 `tokio::sync::mpsc::Sender<LeaseTransitionMsg>`），寫 `learning.lease_transitions`；**Python agent 三表 writer**：`agent_audit_bridge.py` 拓展原有 `record_change()` 路徑，分流 `agent.messages`（每 send 寫一行）/`agent.state_changes`（每 SM transition 寫一行）/`agent.ai_invocations`（每 LLM call 寫一行，從 cost_tracker 觸發）；3 writer 共用 `app/db_pool.py` 寫 PG（`asyncio.to_thread` off event loop） | A（與 E-2 / E-3 並行，純獨立 file，0 衝突）| 1.0 day | **中** — V054 schema retrofit 不影響 hot path；agent 三表 writer 寫吞吐若爆量是 P1 push back 風險點（見 §4 #3） |

**總計：2.5-3 E1 task / 預估 3.0 day E1 work**（amendment 預估 2.5-3 對齊；E1 沒拖延的話 1 sprint 內可閉）。

### 2.3 跨 file 衝突檢測

| 檔案 | E-1 | E-2 | E-3 | E-4 |
|---|---|---|---|---|
| `governance_core.rs` | ✅ 主改 | 唯讀借用 | — | — |
| `sm/lease.rs` | 唯讀（不動既有 9 test） | — | — | — |
| `intent_processor/router.rs` | — | ✅ 主改 | — | — |
| `intent_processor/mod.rs` | — | ✅ struct 加 lease_id | — | — |
| `tick_pipeline/on_tick/step_4_5_dispatch.rs` | — | ✅ caller 同步加 lease_id | — | — |
| `governance_hub.py` | — | — | ✅ 主改 | — |
| `agent_audit_bridge.py` | — | — | — | ✅ 拓展 |
| `multi_agent_framework.py` | — | — | — | 唯讀（confirm callback signature） |
| `executor_agent.py` | — | — | — | 唯讀（caller path 不需改） |
| V054 SQL（新檔）| — | — | — | ✅ 主造 |

**0 file 真實衝突 → E-2/E-3/E-4 可全並行；E-1 必先做 lock facade signature。**

---

## §3. Interface Contract 表

### 3.1 Rust facade signature（amendment §3 點 1+2 落地）

```rust
// governance_core.rs additions / 新增

use parking_lot::Mutex;
use tokio::sync::mpsc;

pub struct GovernanceCore {
    pub auth: AuthorizationSm,
    pub lease: Mutex<DecisionLeaseSm>,            // ← interior mutability 改點
    pub risk: RiskGovernorSm,
    pub oms: OmsStateMachine,
    enabled: bool,
    mode: GovernanceMode,
    lease_id_to_idx: Mutex<HashMap<String, usize>>,  // ← 新增 reverse lookup
    lease_transition_tx: Option<mpsc::Sender<LeaseTransitionMsg>>,  // ← 新增 audit emit
}

#[derive(Debug, Clone)]
pub struct LeaseTransitionMsg {
    pub transition_id: String,    // tx:xxxx
    pub lease_id: String,         // lease:xxxx
    pub from_state: String,
    pub to_state: String,
    pub event: String,
    pub initiator: String,
    pub reason_codes: Vec<String>,
    pub requires_approval: bool,
    pub approved_by: Option<String>,
    pub profile: GovernanceProfile,
    pub engine_mode: String,      // paper / demo / live_demo / live_mainnet
    pub context_id: String,
    pub ts_ms: u64,
}

impl GovernanceCore {
    /// AMD-2026-05-02-01 §3 點 1：Production-only lease facade（一條龍 draft→register→activate）。
    /// AMD-2026-05-02-01 §3 點 1：Production 專用 lease 一條龍 facade。
    ///
    /// Args:
    ///   - intent_id: trade intent unique id（caller-supplied）
    ///   - scope: "TRADE_ENTRY" / "TRADE_EXIT" / "POSITION_ADJUST"
    ///   - ttl_ms: 0.1s-300s（per-intent 短期授權）
    ///   - profile: caller's GovernanceProfile（router 透過 effective_governance_profile 取）
    ///   - source_stage: "router" / "scout" / "strategist"（audit metadata）
    ///
    /// Returns:
    ///   - Ok(LeaseId::Active(s))   = SM 真實走完 Production 路徑
    ///   - Ok(LeaseId::Bypass)      = Exploration / Validation profile（spec §3 點 1 後段）
    ///   - Err(GovernanceError::AuthNotEffective)         = is_authorized() = false
    ///   - Err(GovernanceError::LeaseSmFailure(SmError))  = SM 內部拒
    ///   - Err(GovernanceError::LeaseScopeNotPermitted)   = auth 不允許此 scope
    pub fn acquire_lease(
        &self,                     // ← &self（immutable borrow）relies on Mutex interior mutability
        intent_id: &str,
        scope: &str,
        ttl_ms: u32,               // 100..=300_000
        profile: GovernanceProfile,
        source_stage: &str,
    ) -> Result<LeaseId, GovernanceError> { /* ... */ }

    /// AMD-2026-05-02-01 §3 點 2：lease 釋放。
    pub fn release_lease(
        &self,
        lease_id: &LeaseId,
        outcome: LeaseOutcome,     // Consumed / Failed / Cancelled
    ) -> Result<(), GovernanceError> { /* ... */ }

    /// 反查（Python IPC bridge / replay writer 用）。
    pub fn get_lease_by_id(&self, lease_id: &str) -> Option<LeaseObject> { /* ... */ }

    /// AMD-2026-05-02-01 §3 點 5：注入 audit transition 寫通道。
    pub fn set_lease_transition_tx(&mut self, tx: mpsc::Sender<LeaseTransitionMsg>) { /* ... */ }
}

#[derive(Debug, Clone)]
pub enum LeaseId {
    Active(String),    // 真實 lease:xxxx，需 release
    Bypass,            // Exploration / Validation profile，noop release
}

#[derive(Debug, Clone, Copy)]
pub enum LeaseOutcome {
    Consumed,    // 成功 fill → SM transition Active → Bridged → Consumed
    Failed,      // 失敗 → SM transition Active → Revoked
    Cancelled,   // 主動取消 → SM transition Active → Revoked
}

#[derive(Debug, thiserror::Error)]
pub enum GovernanceError {
    #[error("authorization not effective")]
    AuthNotEffective,
    #[error("lease scope not permitted: {0}")]
    LeaseScopeNotPermitted(String),
    #[error("lease SM failure: {0}")]
    LeaseSmFailure(#[from] SmError),
    #[error("lease id not found: {0}")]
    LeaseNotFound(String),
}
```

### 3.2 Python IPC payload schema（E-3）

```python
# governance_hub.py:693 改寫後接口（backward-compat 簽名）
def acquire_lease(self, intent_id: str, scope: str, ttl_seconds: float = 30.0) -> Optional[str]:
    """AMD-2026-05-02-01: IPC 轉呼 Rust GovernanceCore.acquire_lease()。

    成功 → 回 lease_id (Rust prefix `rs_lease:xxxx`，dual-write period 兼容 `py_*` legacy)
    失敗 → 回 None（fail-closed；IPC connection 死、auth 不效、scope 不允許 都走 None）
    """
    # IPC payload schema:
    #   {
    #     "jsonrpc": "2.0",
    #     "method": "governance.acquire_lease",
    #     "params": {
    #       "intent_id": "<str>",
    #       "scope": "TRADE_ENTRY",
    #       "ttl_ms": 30000,
    #       "profile": "Production" | "Validation" | "Exploration",
    #       "source_stage": "executor_agent_python"
    #     },
    #     "id": <int>
    #   }
    # IPC response:
    #   { "jsonrpc":"2.0", "result": {"lease_id":"rs_lease:abc...","outcome":"Active"|"Bypass"}, "id": ... }
    #   / { "jsonrpc":"2.0", "error": {"code":<i32>,"message":"<str>"}, "id":... }
```

### 3.3 V054 SQL schema additions

```sql
-- learning.lease_transitions（amendment §4 AC-1 觀察點）
CREATE TABLE IF NOT EXISTS learning.lease_transitions (
    transition_id      TEXT        NOT NULL,
    lease_id           TEXT        NOT NULL,
    from_state         TEXT,
    to_state           TEXT        NOT NULL,
    event              TEXT        NOT NULL,
    initiator          TEXT        NOT NULL,
    reason_codes       TEXT[]      DEFAULT ARRAY[]::TEXT[],
    requires_approval  BOOLEAN     DEFAULT FALSE,
    approved_by        TEXT,
    profile            TEXT        NOT NULL,  -- Exploration / Validation / Production
    engine_mode        TEXT        NOT NULL,  -- paper / demo / live_demo / live_mainnet
    context_id         TEXT,
    ts_ms              BIGINT      NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (transition_id, created_at)
);

-- 索引（hot path query）
CREATE INDEX IF NOT EXISTS idx_lease_transitions_lease_id_ts
    ON learning.lease_transitions (lease_id, ts_ms DESC);
CREATE INDEX IF NOT EXISTS idx_lease_transitions_to_state_profile_ts
    ON learning.lease_transitions (to_state, profile, ts_ms DESC);
CREATE INDEX IF NOT EXISTS idx_lease_transitions_engine_mode_ts
    ON learning.lease_transitions (engine_mode, ts_ms DESC);

-- TimescaleDB hypertable
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('learning.lease_transitions', 'created_at',
        chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);
END IF;
END $$;

-- governance.audit_log event_type CHECK 擴 7 lease 值（V053 已 13 → V054 加 7 為 20）
-- 新加：lease_acquired / lease_activated / lease_consumed / lease_revoked / lease_frozen / lease_expired / lease_rejected
ALTER TABLE governance.audit_log DROP CONSTRAINT IF EXISTS chk_audit_log_event_type;
ALTER TABLE governance.audit_log ADD CONSTRAINT chk_audit_log_event_type CHECK (
    event_type IN (
        -- V035 base 5 / V044 +1 / V053 +7 / V054 NEW +7
        ...20 values...
    )
);
```

---

## §4. 5 條 Risk Push Back

### #1（HIGH）Sprint 1 W8 P6 typed-confirm handoff 既有 wiring 衝突

**Push back：** REF-20 W8 P6 Sprint 1 已 land typed-confirm handoff（commit `edf33c0`）+ V044 idempotency + cooldown gate；POST `/api/v1/replay/handoff` 走 atomic transaction 寫 `replay.handoff_requests` + emit `governance.audit_log` row（event_type='replay_handoff_request'）。**該 handoff 是「demo→live」session 級 handoff（T0/T1/T2/T3 EarnedTrust ladder）**，不是 per-intent decision lease — 兩個概念絕不可混為一談（CLAUDE.md §五 註腳明寫「EarnedTrust T0/T1/T2/T3 vs Decision Lease 兩者互補」）。

但 retrofit 後 Rust router gate 對 demo（Validation profile）會 short-circuit `LeaseId::Bypass` —— **若 W8 P6 的 typed-confirm caller 有任何代碼依賴「demo 路徑無 lease 也能走」**，Rust 端絕對不可在 Validation 強制 lease。Spec §3 點 1「Exploration / Validation profile skip（返回 LeaseId::Bypass）」是 contract，retrofit 必嚴守。

**對策：** Task E-2 派發前 PA 強制要 E1 在 router.rs 加 `if !profile.requires_lease() { return early-pass with LeaseId::Bypass; }` 短路；E2 review 必查此短路在 paper/demo 路徑 0 觸發 lease SM transition；E4 regression 加 demo 端 100 intent smoke 必 0 條 `lease_transitions` 對應 row。

**P0 acceptance probe：**
```sql
-- Task E-2 retrofit deploy 後 24h，Validation profile 必 0 lease transition
SELECT COUNT(*) FROM learning.lease_transitions
WHERE profile = 'Validation' AND created_at > NOW() - INTERVAL '24 hours';
-- 期望: 0；> 0 = retrofit bug，立即 rollback feature flag
```

---

### #2（HIGH）Rust router gate fail-closed 對 ExecutorAgent shadow_mode_provider 路徑的影響

**Push back：** `executor_agent.py:185` `_shadow_mode_provider` G3-03 Phase B 既有 hardcoded `lambda: True` fail-close default（CLAUDE.md §三 18 blocker #8 `P1-FAKE-1` 待修）。當 ExecutorAgent shadow_mode=true，submit_order() **就根本不會走 IPC 觸 Rust pipeline**（直接 log + return shadow ExecutionReport）。

但 retrofit 後 Python `governance_hub.acquire_lease()` 改為 IPC 轉呼 Rust — `executor_agent.py:454` `acquire_lease(intent_id, ...)` **無論 shadow_mode 真假都會 IPC 一次 Rust**！
- 真實 caller: shadow mode → executor_agent.py L454 IPC acquire_lease → Rust SM 真做 transition → submit_order shadow log → 沒有對應 release_lease → **lease 卡 ACTIVE 直到 ExpiryGuardian 清掉**
- 副作用 1：amendment §4 AC-1 condition「DRAFT/REGISTERED/ACTIVE 至少 5 state 有 transition」會被 shadow path 滿足 ── **假綠**
- 副作用 2：amendment §6 條件 #2「IPC failure rate < 0.5%」可能因 shadow path 高頻 flush 接近上限 — 但其實是冷代碼

**對策：** Task E-3 在 Python `governance_hub.acquire_lease()` 內加「caller-side shadow short-circuit」：判斷呼叫者是否 shadow mode（透過 `executor_agent._shadow_mode_provider()` 反查），shadow=true → 直接 return `"shadow_lease:no_op_<intent_id>"` 字串 + 不 IPC（fail-fast；不打 Rust SM 也不 fail-close 拒執行）。同時 Task E-4 V054 audit writer 加 `engine_mode='shadow'` 過濾，AC-1 的 query 加 `AND engine_mode != 'shadow'` 條件。

**P0 acceptance probe：**
```sql
-- shadow path 0 lease transition 寫入
SELECT engine_mode, COUNT(*) FROM learning.lease_transitions
WHERE created_at > NOW() - INTERVAL '24 hours' GROUP BY engine_mode;
-- 期望: 無 'shadow' / 'shadow_*' row；live_demo + live_mainnet 為主
```

---

### #3（MEDIUM）MessageBus DB sink 是否打爆 agent.messages 表 throughput

**Push back：** Task E-4 agent 三表 writer 接 `MessageBus._audit_callback` — 但 5 Agent live shadow（CLAUDE.md §三 ~4552 行代碼）每秒可能產生 50-100 message（Scout intel / Strategist directive / Guardian verdict / Analyst summary / Executor report），**24h ≈ 4.3M-8.6M row 寫入 `agent.messages`**。

V003 schema 設了 TimescaleDB hypertable（`chunk_time_interval => INTERVAL '1 day'`），但：
- INSERT throughput：`agent.messages` PRIMARY KEY (message_id, ts) → 每筆 row 全表索引維護成本
- 索引：V005 加了 4 個 index（from_agent / to_agent / message_type / engine_mode）→ 寫入 10× 成本
- DB 容量：每 row payload JSONB 平均 1KB → **每天 4.3-8.6 GB / 月 130-258 GB**
- Linux PG 分配：~4-8GB（memory `project_hardware_constraints.md`）→ shared_buffers 撐不住

**對策：** Task E-4 必加 Sampling rate / aggregation policy：
- Option A（推薦）：`agent.messages` writer 加 sampling — 只寫 LOW priority 樣本 1%、NORMAL 10%、HIGH/CRITICAL 100%；TOML config `agent_audit_writer.sampling_*`
- Option B（降頻）：寫入聚合 `agent.message_count_per_hour` view（PG continuous aggregate）替代逐 row，僅 HIGH/CRITICAL 寫 raw row
- Option C（外部）：寫入 `/tmp/openclaw/agent_messages.jsonl` rolling file，每日批次 `\COPY` 入 PG（非 hot path）

PA 推薦 **Option A**（最小 deploy 成本 + 仍滿足 amendment AC-5「24h ≥10 rows」）；E2 review 必查 sampling logic + 失敗時 fail-soft（drop + log，不阻塞 send）。

**P1 acceptance probe：**
```sql
-- agent.messages 24h 寫入 ≥10 row（AC-5）但 ≤500K row（throughput 健康）
SELECT priority, COUNT(*) FROM agent.messages
WHERE ts > NOW() - INTERVAL '24 hours' GROUP BY priority;
```

---

### #4（MEDIUM）lease.rs facade 對既有 `Profile.requires_lease()` 的 backward compat

**Push back：** `governance_core.rs:72` 的 `requires_lease()` 已宣告 `Production=true` / `Exploration|Validation=false`，但 retrofit 前**完全沒有 caller**。Sprint 1 之前 28 處測試 `GovernanceProfile::Production` 都跑 `process_gates_only(...)` 不檢查 requires_lease，全綠通過。

retrofit 後 router.rs 啟用 `if profile.requires_lease() && lease.is_err() { reject }` — 既有 28 個 Production profile test（intent_processor/tests.rs L547+L576+L776 等）**會集體 fail**，因為 test fixture `gov = GovernanceCore::new()` + `submit_for_approval` + `approve` 但沒 grant lease → router 拒。

**對策：** Task E-1 PA 必派 E1 同步重寫 28 處 Production test fixture：每處構造後加 `gov.acquire_lease("test_intent", "TRADE_ENTRY", 30000, GovernanceProfile::Production, "test")` 預留一個 active lease；fixture 重寫量 ~1.5 day（已含在 E-1 0.8 day 內？— 應加額外 0.3 day 緩衝）。Task E-1 預估**從 0.8 day → 1.1 day**。

**E2 review 必查：** test fixture 不能直接走 `LeaseId::Bypass` 短路（會掩蓋真實 router gate bug）；Production test 必驗 lease 真實 transition。

---

### #5（MEDIUM）AMD-2026-05-02-01 prereq schedule 與 Sprint 2 啟動衝突

**Push back：** AMD-2026-05-02-01 §5.4 明寫「派發排程：~2026-05-15 P0-EDGE-2 後啟動 / 與 LG-2/3 並行 / 必先於 LG-4」。但 REF-20 Sprint 2 是 Sprint 1（2026-05-03 close）的接續 sprint，**理論上 2026-05-04 已可啟動**，比 amendment 預估早 11 天。

兩個情境衝突：
- 情境 A（amendment 排程派）：等到 2026-05-15 P0-EDGE-2 結論再啟動 retrofit；好處 = edge decision 不被技術改動干擾；壞處 = 18 blocker #5 拖到 2026-05-15+3.0 day = **2026-05-18 才 ready**，撞 LG-4 IMPL window
- 情境 B（Sprint 2 直開派）：2026-05-04 直接開工 retrofit；好處 = blocker 提早 11 天解；壞處 = 與 P0-EDGE-2 觀察期重疊，retrofit 後 router gate 改動可能影響 edge accumulation 數據（demo path 雖 Bypass，但 IPC 通道 freeze 0.5s 仍會被 fast-track 觀察到）

PA 立場：**情境 B（Sprint 2 直開）但加 feature flag 灰度**：
- E-1 Rust facade land + E-3 Python IPC bridge land **但 router gate (E-2) 默認 OFF**（feature flag `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0`）
- E-4 audit writer 100% ON（先收 baseline data，writer 不影響 hot path）
- 2026-05-15 P0-EDGE-2 結論後再 flip `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` 灰度啟用

**對策：** Task E-2 必加 env-gated 啟用條件；commit message 說明「灰度 feature flag」；amendment §6 回退條件「IPC failure > 0.5%」變成「flag flip 後觀察 24h 條件達標才 commit second flip」。

---

## §5. Acceptance Probe SQL（5 條 AC 自動驗）

### AC-1: SM-02 transition log 24h 覆蓋率
```sql
-- amendment §4 AC-1：retrofit deploy 後 24h，9 state 至少 5 個 distinct
SELECT COUNT(DISTINCT to_state) AS distinct_states
FROM learning.lease_transitions
WHERE created_at > NOW() - INTERVAL '24 hours'
  AND profile = 'Production'
  AND engine_mode != 'shadow';                -- §4 #2 push back filter
-- PASS：>= 5；FAIL：< 5（router gate 沒真實生效）
```

### AC-2: 6-element auth 元素填充率
```sql
-- amendment §4 AC-2：抽 10 筆 trade_attribution（V050 simulated_fills 為觀察靶）element 4 ≥ 95%
WITH last_10 AS (
    SELECT decision_lease_id
    FROM replay.simulated_fills
    WHERE created_at > NOW() - INTERVAL '7 days'
    ORDER BY created_at DESC LIMIT 10
)
SELECT
    COUNT(*) FILTER (WHERE decision_lease_id IS NOT NULL
                       AND decision_lease_id NOT IN ('PROFILE_FALLBACK','MANUAL','RUST_HOT_PATH_PRE_AMENDMENT_2026-05-02')) * 100.0 / COUNT(*) AS pass_pct
FROM last_10;
-- PASS: >= 95（10 筆 9 筆 PASS）
```

### AC-3: production lease_id 流動驗證
```sql
-- amendment §4 AC-3：每日 lease_id IS NOT NULL count >= 1
SELECT COUNT(*) AS lease_id_emitted_24h
FROM replay.simulated_fills
WHERE decision_lease_id IS NOT NULL
  AND created_at > NOW() - INTERVAL '24 hours';
-- PASS: >= 1（retrofit 第二個 24h 視窗起）
```

### AC-4: SM-02 transition coverage 週審計
```sql
-- amendment §4 AC-4：weekly 9 state 至少 6 個有 ≥1 transition
SELECT to_state, COUNT(*) FROM learning.lease_transitions
WHERE created_at > NOW() - INTERVAL '7 days' AND profile = 'Production'
GROUP BY to_state ORDER BY 2 DESC;
-- PASS: >= 6 distinct to_state；FAIL: 立即 P0 重評
-- helper_scripts/db/passive_wait_healthcheck.py --check sm02_transition_coverage 跑此查詢
```

### AC-5: agent schema 寫入率
```sql
-- amendment §4 AC-5：agent 三表 24h row count > 0
SELECT
    'agent.messages' AS tbl, COUNT(*) AS rows_24h FROM agent.messages WHERE ts > NOW() - INTERVAL '24 hours'
UNION ALL SELECT
    'agent.state_changes', COUNT(*) FROM agent.state_changes WHERE ts > NOW() - INTERVAL '24 hours'
UNION ALL SELECT
    'agent.ai_invocations', COUNT(*) FROM agent.ai_invocations WHERE ts > NOW() - INTERVAL '24 hours';
-- PASS: 3 row 都 >= 10；FAIL: bundled fix #6 落空
```

**自動化整合**：5 條 query 全部加入 `helper_scripts/db/passive_wait_healthcheck.py` 為 5 個新 check function（`check_amd_2026_05_02_01_ac1` 到 `_ac5`）；retrofit deploy commit 同 PR 加；cron 每 6 小時跑；FAIL 觸發 P0 alert。

---

## §6. Deploy 順序 + 灰度策略

### 6.1 推薦 deploy chain（feature flag gradual rollout）

```
Phase 1 (Day 1): E-1 Rust facade land
   ├─ commit: facade.rs + governance_core.rs Mutex 改造 + 14 unit test PASS
   ├─ deploy: --rebuild engine + restart
   ├─ validate: cargo test --workspace 全綠 + lib XXX/0
   └─ feature flag: OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0（默認 OFF）

Phase 2 (Day 1-2 並行): E-3 Python IPC bridge + E-4 schema/writer land
   ├─ commit E-3: governance_hub.py IPC 改寫
   ├─ commit E-4: V054 SQL + lease_transition_writer.rs + agent 三表 writer
   ├─ deploy: --rebuild engine + restart_all + DB migrate (OPENCLAW_AUTO_MIGRATE=1 一次性)
   ├─ validate: AC-5 3 表寫入 >0/24h（24h 後）
   └─ feature flag E-3: OPENCLAW_LEASE_PYTHON_IPC_ENABLED=1（IPC 路徑啟用）

Phase 3 (Day 2-3): E-2 router gate land
   ├─ commit: router.rs + step_4_5_dispatch.rs + 28 test fixture 重寫
   ├─ deploy: --rebuild engine（默認 flag OFF，無 production 影響）
   ├─ validate: cargo test 全綠 + lib XXX/0 + 28 Production fixture PASS
   └─ flag: OPENCLAW_LEASE_ROUTER_GATE_ENABLED=0（仍 OFF）

Phase 4 (Day 3-7): 觀察 baseline
   ├─ AC-5 三表寫入持續 stable
   ├─ Python IPC failure rate < 0.1%/day（amendment §6 條件 #2 baseline）
   └─ governance_hub.py acquire_lease() Python local fallback 仍跑（dual-write Phase 1）

Phase 5 (Day 7+ 或 P0-EDGE-2 結論後): flip router gate
   ├─ flag: OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1
   ├─ canary period: 24h 觀察 AC-1 + AC-3 + IPC failure rate
   ├─ AC-1 PASS → 進入 dual-write Phase 2（4 週兩平面並存）
   └─ AC-1 FAIL → flip back flag=0，調查 P0 root cause

Phase 6 (Day 7+ 4 weeks): dual-write canonical 切換
   ├─ Python lease 標 deprecated；Rust 為唯一 SM truth
   ├─ amendment §5.1 Phase 3 的 4 week boundary
   └─ 觀察期 amendment §6 5 條件全 PASS → 正式 close P0-GOV-1
```

### 6.2 E1 派發順序

| Day | 工作 | E1 數 |
|---|---|---|
| Day 1 AM | E-1 派發（單 E1 串行 0.8-1.1 day）| 1 |
| Day 1 PM (E-1 facade signature land) | E-3 + E-4 並行派發 | 2 |
| Day 2 (E-1 cargo green) | E-2 派發 | 1 |
| Day 3 全部 land | E2 review + E4 regression | 0 |

**最大並行 3 E1**；E-1 為 critical path 阻塞者。

---

## §7. 與 Sprint 1 commits 的 cross-impact

| Sprint 1 commit | 改動範圍 | retrofit 後是否需 follow-up |
|---|---|---|
| V045 `replay.run_state` | spawn argv schema | 0 — `manifest_id`/`run_id` 不含 lease，無 retrofit 衝突 |
| V046 `replay.report_artifacts` | report 元數據 | 0 — 無 lease 欄位 |
| V049 `replay.experiments` 22 col | window timestamps + manifest signature | 0 — 不含 lease |
| **V050 `replay.simulated_fills` 17 col** | 含 `decision_lease_id TEXT nullable` | ✅ **placeholder column 終於有 caller** — Task E-2 router gate consume lease 後，step_4_5_dispatch.rs 寫 fill 時填 `lease_id` 入此 column |
| V051 `mlde_recommendations_replay_columns` | replay_experiment_id + manifest_hash | 0 — 不含 lease |
| V053 `governance_audit_log` event_type 13 值 | replay event types | ✅ Task E-4 V054 在此基礎再加 7 lease event_type 為 20 值 |
| W8 P6 typed-confirm handoff（commit `edf33c0`）| `replay.handoff_requests` + V044 idempotency | ✅ **不衝突但要明示分離** — handoff = session 級 EarnedTrust ladder；lease = per-intent 30s 短期授權；CLAUDE.md §五 註腳已寫互補關係。retrofit 不改 handoff_routes.py |
| W8 P6 cooldown gate | 30s same-actor lockout | 0 — cooldown 是 session level；lease 不互動 |
| **§7 結論：V050 placeholder column + V053 event_type 是 sprint 1 為 sprint 2 預留的接口；retrofit 自然啟用，無需 schema 補造** |

---

## §8. 完成定義

- [x] 設計報告 land：本檔
- [ ] PA memory 追加 Sprint 2 Track E entry（接續 Sprint 1 entry）
- [ ] 摘要 ≤800 字回 PM（含 task partition / risk top 3 / deploy chain summary）
- [x] 不寫業務碼 ✅
- [x] 不 commit ✅

**E2 重點審查 3 點：**

1. **§4 #4 — Production test fixture 28 處重寫**：E2 必查 fixture 改寫**不能用 LeaseId::Bypass 短路**（會掩蓋 router gate bug）；每 fixture 必驗 `gov.acquire_lease()` 真實創 active lease + `gov.lease.lock().get_live().len() > 0`
2. **§4 #2 — Python IPC bridge shadow short-circuit**：E2 必查 `governance_hub.acquire_lease()` 正確檢測 caller shadow_mode；shadow path 不打 IPC + 不寫 lease_transitions（避免 §4 #2 假綠）；測試覆蓋 shadow=true / shadow=false / IPC fail 三 case
3. **§4 #3 — agent.messages sampling**：E2 必查 sampling logic（推薦 Option A）+ fail-soft（writer DB error 不阻塞 send）+ TOML config 設計（不 hardcode）

---

*OpenClaw / Bybit REF-20 Sprint 2 Track E PA Design — AMD-2026-05-02-01 retrofit*
