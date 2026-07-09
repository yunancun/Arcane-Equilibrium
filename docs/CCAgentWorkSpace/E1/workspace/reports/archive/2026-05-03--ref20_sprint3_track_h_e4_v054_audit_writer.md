# REF-20 Sprint 3 Track H E-4 — V054 SQL + lease_transition_writer + agent 三表 sampling config（IMPLEMENTATION DONE）

**日期：** 2026-05-03
**Owner：** E1（E-4 task）
**Sprint：** REF-20 Sprint 3 Track H
**Amendment：** AMD-2026-05-02-01 §3 點 5（audit writer trail）+ §4 AC-1 backbone（learning.lease_transitions distinct count >= 5）
**派發來源：** PA partition `2026-05-03--ref20_sprint2_track_e_decision_lease_retrofit_design.md` Track E E-4
**E-1 contract：** `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--ref20_sprint3_track_h_e1_rust_facade.md` §6 + §7.3 emit 策略
**狀態：** IMPLEMENTATION DONE — 待 E2 review / E4 regression / PM 統一 commit

---

## §1. 任務摘要

E-4：在 PA partition `2026-05-03--ref20_sprint2_track_e_decision_lease_retrofit_design.md` 的 Sprint 3 Track H 切片下，落地 Decision Lease retrofit 的 audit-trail 物理層：

1. **V054 SQL** — 新表 `learning.lease_transitions`（14 col + 4 CHECK + 3 hot-path index + TimescaleDB hypertable）+ `governance.audit_log` event_type CHECK enum 由 V053 14 值擴 V054 21 值（新增 7 lease lifecycle event_type）
2. **`lease_transition_writer.rs`** Rust async actor — 接收 E-1 預留的 `LeaseTransitionMsg` channel，batched flush 至 V054 表（fail-soft）
3. **emit hook** 在 `governance_core.rs::acquire_lease/release_lease` inline 加入（Option A — facade 自動 emit，caller 0 改動）
4. **agent 三表 sampling config schema** — `risk_config_{demo,paper,live}.toml` 加 `[messagebus_db_sink]` 段（三環境獨立 sampling 比，Phase A config-only）

E-2 router gate / E-3 Python IPC bridge 由 PM 後續派發；本 task 不涉入。**agent 三表 PG wiring 拆 Phase B 標 P1-AGENT-DB-SINK follow-up ticket**（push back §7.2）。

---

## §2. 修改清單（7 檔）

| 檔案 | 改動 | LOC |
|---|---|---|
| `srv/sql/migrations/V054__lease_transitions_audit_writer.sql` | NEW — 14 col table + 4 CHECK + 3 index + hypertable + V053→V054 event_type enum 擴展 + race-free DROP+ADD ACCESS EXCLUSIVE LOCK | 535 |
| `srv/rust/openclaw_engine/src/database/lease_transition_writer.rs` | NEW — `spawn_lease_transition_pipeline()` + `run_bridge_thread()` + `run_lease_transition_writer()` + `flush_lease_transitions()` + 6 unit test | 492 |
| `srv/rust/openclaw_core/src/governance_core.rs` | acquire_lease/release_lease 加 inline emit + `build_msg_from_last_transition()` helper + `resolve_engine_mode_tag()` env reader + `LeaseTransitionMsg.profile` enum→String | 1251→1498（+247） |
| `srv/rust/openclaw_engine/src/database/mod.rs` | `pub mod lease_transition_writer` | +1 |
| `srv/settings/risk_control_rules/risk_config_demo.toml` | 加 `[messagebus_db_sink]` schema（Phase A） | 381→403（+22） |
| `srv/settings/risk_control_rules/risk_config_paper.toml` | 加 `[messagebus_db_sink]` schema | 342→362（+20） |
| `srv/settings/risk_control_rules/risk_config_live.toml` | 加 `[messagebus_db_sink]` schema（live 收緊 sampling） | 345→366（+21） |
| `srv/sql/migrations/REF-20_RESERVATION.md` | v1.9→v1.10：V054 row + Sprint 3 Track H Decision Lease Retrofit Note | +6 |

---

## §3. 關鍵 diff 摘要

### 3.1 V054 SQL — `learning.lease_transitions` table + 21-value enum extension

```sql
-- learning.lease_transitions (14 col)
CREATE TABLE IF NOT EXISTS learning.lease_transitions (
    transition_id      TEXT        NOT NULL,
    lease_id           TEXT        NOT NULL,
    from_state         TEXT,                              -- nullable for initial draft
    to_state           TEXT        NOT NULL,
    event              TEXT        NOT NULL,
    initiator          TEXT        NOT NULL,
    reason_codes       TEXT[]      NOT NULL DEFAULT ARRAY[]::TEXT[],
    requires_approval  BOOLEAN     NOT NULL DEFAULT FALSE,
    approved_by        TEXT,
    profile            TEXT        NOT NULL,              -- "Production"/"Validation"/"Exploration"
    engine_mode        TEXT        NOT NULL,              -- 5-value (paper/demo/live_demo/live_mainnet/shadow)
    context_id         TEXT,
    ts_ms              BIGINT      NOT NULL,              -- ms since epoch
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (transition_id, created_at)
);

-- 4 CHECK constraints (idempotent, conditional ADD)
-- chk_lease_transitions_profile: 3-value GovernanceProfile enum
-- chk_lease_transitions_to_state: 9-value LeaseState enum (UPPERCASE)
-- chk_lease_transitions_engine_mode: 5-value engine_mode enum
-- chk_lease_transitions_ts_ms_positive: ts_ms > 0 (epoch reject)

-- 3 hot-path index (CREATE INDEX IF NOT EXISTS):
-- idx_lease_transitions_lease_id_ts (per-lease query)
-- idx_lease_transitions_to_state_profile_ts (AC-1 distinct count weekly)
-- idx_lease_transitions_engine_mode_ts (PA §4 #2 shadow filter)

-- TimescaleDB hypertable: 1-day chunk (extension probe + plain table fallback)
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('learning.lease_transitions', 'created_at',
        chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);
END IF;
END $$;

-- governance_audit_log event_type CHECK enum V053 14 → V054 21:
-- race-free DROP+ADD via ACCESS EXCLUSIVE LOCK (V053 retrofit F2 模板)
BEGIN;
DO $$ ...
    LOCK TABLE learning.governance_audit_log IN ACCESS EXCLUSIVE MODE;
    -- DROP existing CHECK + ADD canonical 21-value list:
    --   V035 base 5 + V044 1 + V053 8 + V054 NEW 7
    --     14. lease_acquire_request    15. lease_acquire_success
    --     16. lease_acquire_fail       17. lease_release_consumed
    --     18. lease_release_failed     19. lease_release_cancelled
    --     20. lease_sm_transition
END $$;
COMMIT;
```

### 3.2 `lease_transition_writer.rs` 三層架構

```rust
// 公開 spawn helper — operator 從 main.rs 啟動時呼叫一次。
pub fn spawn_lease_transition_pipeline(
    pool: Arc<DbPool>,
    config: Arc<crate::config::ConfigManager>,
    cancel: CancellationToken,
) -> LeaseTransitionSender { ... }

// 架構：
//   GovernanceCore (openclaw_core, no tokio)
//       │ std::sync::mpsc::Sender::send(msg) — sync, lock-free
//       ▼
//   std::sync::mpsc::Receiver — polled in spawn_blocking thread
//       │ tokio::sync::mpsc::Sender::try_send(msg) — async, bounded
//       ▼
//   tokio::sync::mpsc::Receiver — polled in async writer task
//       │ INSERT INTO learning.lease_transitions
//       ▼
//   PG (sqlx pool)
//
// 1024 capacity bounded tokio mpsc; 100ms recv_timeout cancellation responsive.
// Writer batched flush: 100 row OR config.batch_flush_interval_ms whichever first.
```

### 3.3 governance_core.rs acquire_lease emit hook（Option A facade auto-emit）

```rust
// 持鎖期間蒐集 3 筆 transition record snapshot；釋鎖後 emit 至 channel（fail-soft）。
let (lease_id_str, idx, emit_msgs) = {
    let mut sm = self.lease.lock();
    let idx = sm.create_draft(intent_meta, &created_by, expires_at_ms);
    let draft_obj = sm.get(idx).ok_or(...)?.clone();        // snapshot Draft
    sm.register(idx)?;
    let registered_obj = sm.get(idx).ok_or(...)?.clone();   // snapshot Registered
    sm.activate(idx)?;
    let active_obj = sm.get(idx).ok_or(...)?.clone();       // snapshot Active

    let id = active_obj.lease_id.clone();
    let mut msgs = Vec::with_capacity(3);
    for obj in [&draft_obj, &registered_obj, &active_obj] {
        if let Some(msg) = Self::build_msg_from_last_transition(
            &id, obj, &profile_str, &engine_mode_tag, &context_id,
        ) { msgs.push(msg); }
    }
    (id, idx, msgs)
};

// Lock 已釋；安全 emit。
for msg in emit_msgs {
    self.emit_transition_safe(msg);  // std::sync::mpsc::Sender::send fail-soft
}
```

`release_lease` 同模式（持鎖蒐集 1-2 筆 → 釋鎖 emit）。release 路徑 profile 從 `lease.intent` JSONB 反推（acquire_lease 寫入時塞 profile metadata）。

### 3.4 三環境 TOML sampling schema（Phase A config-only）

```toml
# Demo / Paper（learning data source 寬鬆）
[messagebus_db_sink]
enabled = false                 # Phase A dormant
sampling = "severity"            # Option A
sampling_low_pct = 1            # LOW 1%
sampling_normal_pct = 10        # NORMAL 10%
sampling_high_pct = 50          # HIGH 50%
sampling_critical_pct = 100     # CRITICAL 100%（audit 完整性硬底線）
fail_soft_on_db_error = true

# Live（生產審計收緊）
[messagebus_db_sink]
enabled = false
sampling = "severity"
sampling_low_pct = 0            # Live drops all LOW (audit completeness via HIGH+)
sampling_normal_pct = 5         # Live tightened from demo 10% → 5%
sampling_high_pct = 50
sampling_critical_pct = 100
fail_soft_on_db_error = true
```

三環境獨立 per `feedback_env_config_independence`；live 收緊 per `feedback_demo_loose_live_strict_policy`。

### 3.5 emit 策略決策說明（push back §7.1）

E-1 §7.3 留 emit 策略 A/B/C 三選項給 E-4。**選 Option A facade 內 inline emit**：

| 選項 | 描述 | 我的判斷 |
|---|---|---|
| A（推薦）| facade 內 inline emit（acquire/release method body 內持鎖 collect snapshot + 釋鎖 emit）| **選用** — 100% coverage 不依賴 caller |
| B | caller-side 顯式 emit（router gate / IPC handler 自呼）| 拒 — caller 漏 emit 風險 → AC-1 distinct count >= 5 假綠 |
| C | DecisionLeaseSm 內 transition emit hook（pass to constructor）| 拒 — 改 SM constructor 簽名破 sm/lease.rs 9 unit test backward compat |

選 A **強制** 修改 `governance_core.rs`（task 描述絕對路徑沒列），這是 PA design / E-1 §7.3 留給 E-4 的決策權。詳 §7.3 push back。

### 3.6 task spec vs PA design 7 event_type 衝突決策（push back §7.4）

| 來源 | 7 event_type 命名 |
|---|---|
| **task spec（採用）** | lease_acquire_request / lease_acquire_success / lease_acquire_fail / lease_release_consumed / lease_release_failed / lease_release_cancelled / lease_sm_transition |
| PA design §3.3 | lease_acquired / lease_activated / lease_consumed / lease_revoked / lease_frozen / lease_expired / lease_rejected |

**選 task spec**：與 facade emit 語意對齊（acquire/release outcome → 1 event_type 1 row）；audit 重建單筆 row 對一個 outcome 直接定位，不必 JOIN SM transition 表。PA design 是 SM-state-name 偏向架構意圖。

---

## §4. 治理對照（CLAUDE.md §七 強制檢查）

| 檢查項 | 結果 |
|---|---|
| 雙語 SQL comment（V054 Purpose / 目的）| ✅ V054 §header + §每段 comment 中英對照 |
| 雙語 Rust /// doc + 中文 inline | ✅ lease_transition_writer.rs MODULE_NOTE 中英 + 函數 doc + inline 雙語 |
| 雙語 governance_core.rs 改動 | ✅ acquire/release emit hook + helper + module note 全雙語 |
| `grep -E '/home/ncyu\|/Users/[^/]+'` diff 0 hit | ✅ |
| V054 idempotent + Guard A/B/C | ✅ Mac dev real-PG dry-run × 2 → 0 RAISE EXCEPTION + 全 NOTICE skip |
| V054 LOCK TABLE race-free（同 V053 pattern）| ✅ BEGIN + LOCK TABLE ACCESS EXCLUSIVE + DROP+ADD CHECK + COMMIT |
| 0 trading.* mutate / 0 live_* mutate | ✅ E-4 diff 0 hit（既有 mod.rs 內引用都是 doc comment） |
| `max_retries` / `live_execution_allowed` / `execution_authority` / `system_mode` / `OPENCLAW_ALLOW_MAINNET` / `authorization.json` | ✅ E-4 diff 0 觸碰 |
| TOML config 三環境獨立（不合併）| ✅ paper/demo/live 各自 commit 自己的 sampling 比 |
| 文件 ≤800 警告 / ≤1500 hard | governance_core.rs 1498（過警告 800，未過 hard 1500）；lease_transition_writer.rs 492（OK）；V054 535（OK）；§九 pre-existing 不適用（baseline 1251 已超 800）但本次未推 hard cap。**push back §7.4：1 LOC 緩衝接近 hard cap，下次擴張前先抽 helper（候選 lease_facade.rs / governance_emit.rs）**。 |
| 新 singleton 登記 §九 表 | 無新 singleton（lease_transition_writer 是 actor task spawn pattern，不是 singleton；GovernanceCore 既有，欄位內加 emit channel） |

---

## §5. 測試結果

| 測試套件 | 結果 |
|---|---|
| `cargo test --release -p openclaw_core --lib`（含既有 401 + 8 facade unit test）| **401 PASS / 0 fail** |
| `cargo test --release -p openclaw_engine --lib database::lease_transition_writer`（新 6 unit test）| **6 PASS / 0 fail** |
| `cargo test --release -p openclaw_engine --lib`（含 E-1 後 2454 + E-4 加 6 + 7 cross-bridge tests 啟動）| **2467 PASS / 0 fail** |
| `cargo test --release --tests --workspace` | **全綠 0 failed**（openclaw_core 19 integration / openclaw_engine 58 integration / 多套件） |
| `cargo build -p openclaw_core --lib` | **0 error / 0 warning** |
| `cargo build -p openclaw_engine --lib` | **0 error / 21 pre-existing dead_code warning（與 E-4 無關）** |
| nm scan release lib | **0 forbidden symbol**（panic_unwind / forgery / mock_ 0 hit；只有 std::process::abort handle 是合法 std 引用） |

### 5.1 V054 Mac dev real-PG dry-run

| Step | 結果 |
|---|---|
| 第 1 次 apply（CREATE 全 PASS）| `INSERT 0 7` lease event_type / `INSERT 0 1` lease_transitions row |
| 第 2 次 apply（idempotent check）| **0 RAISE EXCEPTION**；全 NOTICE skip（profile/to_state/engine_mode/ts_ms CHECK + index + table + V054 enum 全 already-present）|
| 7 V054 NEW event_type INSERT PASS | `INSERT 0 7` lease_acquire_request/success/fail + lease_release_consumed/failed/cancelled + lease_sm_transition |
| Unknown event_type 'not_a_real_event' REJECT | `ERROR: violates check constraint "governance_audit_log_event_type_check"` |
| ts_ms=0 epoch reject | `ERROR: violates check constraint "chk_lease_transitions_ts_ms_positive"` |
| 'NotAProfile' invalid profile reject | `ERROR: violates check constraint "chk_lease_transitions_profile"` |
| 'active' lowercase to_state reject | `ERROR: violates check constraint "chk_lease_transitions_to_state"` |

### 5.2 新 6 unit test in lease_transition_writer.rs

| Test name | 覆蓋 |
|---|---|
| `test_msg_fields_roundtrip` | LeaseTransitionMsg fields 透過 Clone 守恆（lease_id / to_state / profile / engine_mode / ts_ms / from_state / reason_codes）|
| `test_bridge_channel_clean_drop` | std mpsc + tokio mpsc 對；3 msgs queued；tokio_rx drop 後 try_send Err；std_rx 仍 drain 3 msgs（bridge clean shutdown） |
| `test_facade_send_fail_soft_on_disconnect` | std_rx drop 後 facade 模式 `let _ = tx.send(msg)` 不 panic；模擬 emit_transition_safe fail-soft |
| `test_epoch_zero_ts_ms_detected` | bad msg ts_ms=0 / good msg ts_ms>0；驗 V054 chk_lease_transitions_ts_ms_positive carrier 層 invariant |
| `test_bridge_channel_capacity_does_not_block_facade` | tokio mpsc 灌滿 BRIDGE_CHANNEL_CAPACITY=1024；第 1025 條 try_send 必 Err（fail-soft 路徑）|
| `test_insert_sql_locked_columns` | INSERT SQL 14 col + ON CONFLICT clause schema 鎖定，防止與 V054 schema 漂移 |

### 5.3 既有 cargo test 對 governance_core.rs emit hook 改動的回歸驗證

| 風險點 | 結果 |
|---|---|
| acquire_lease 持鎖期間蒐集 3 筆 transition record snapshot | 既有 8 facade unit test + 17 既有 governance test 全綠 |
| release_lease 持鎖蒐集 1-2 筆 + profile 反推 from intent JSONB | 既有 cascade test + 8 Production fixture（intent_processor::tests）全綠 |
| `LeaseTransitionMsg.profile` enum→String 微調 | 0 caller 調用此欄位（E-1 留 `lease_transition_tx: None`）；E-4 自身使用 String 路徑 |
| Mutex contention 在 hot path | E-2 `test_facade_no_mutex_deadlock_in_sequence` 5 次 acquire+status+release 序列 PASS；新 inline emit 仍持鎖最短時間 + 釋鎖後 emit |

---

## §6. Interface Contract（為 E-2/E-3 + Linux deploy 準備）

### 6.1 `spawn_lease_transition_pipeline()` Contract — 給 main.rs / Linux deploy

```rust
pub fn spawn_lease_transition_pipeline(
    pool: Arc<DbPool>,
    config: Arc<crate::config::ConfigManager>,
    cancel: CancellationToken,
) -> LeaseTransitionSender;  // std::sync::mpsc::Sender<LeaseTransitionMsg>

// main.rs / startup wiring 順序：
//   1. let pool = Arc::new(DbPool::new(...).await?);
//   2. let cancel = CancellationToken::new();
//   3. let lease_tx = spawn_lease_transition_pipeline(pool, config, cancel.clone());
//   4. governance_core.set_lease_transition_tx(lease_tx);  // 注入 facade
//   5. (continue normal engine startup)
//
// 副作用：
//   - 啟動 dedicated bridge thread "lease_tx_bridge"（std mpsc → tokio mpsc）
//   - 啟動 async writer task（tokio mpsc → PG INSERT）
//   - cancel.cancel() 時兩者 graceful shutdown
```

### 6.2 V054 Schema Contract — 給 E-2 `step_4_5_dispatch.rs` + E-3 IPC bridge

```sql
-- E-2 router gate flip (OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1) 後：
--   每筆 acquire_lease 自動 emit 3 筆 row（DRAFT / REGISTERED / ACTIVE）
--   每筆 release_lease(Consumed) emit 2 筆（BRIDGED / CONSUMED）
--   每筆 release_lease(Failed/Cancelled) emit 1 筆（REVOKED）
--
-- 24h 期望 row count（5 strategy × 50 fills/day × ~5 transition/intent）：
--   ~1250 row/day Production；shadow path 經 PA design §4 #2 push back filter
--   AND engine_mode != 'shadow' 排除（amendment §4 AC-1 query 過濾）
--
-- AC-1 query：
SELECT COUNT(DISTINCT to_state) AS distinct_states
FROM learning.lease_transitions
WHERE created_at > NOW() - INTERVAL '24 hours'
  AND profile = 'Production'
  AND engine_mode != 'shadow';
-- PASS：>= 5；FAIL：router gate 沒真實生效 / SM transition 漏 emit
```

### 6.3 governance_audit_log 21-value enum Contract — 給未來 caller-side emit

V054 加的 7 lease event_type 是給**未來** caller-side emit（例如 handoff_routes 的 lease accept/reject）使用的 governance_audit_log 入口；**E-4 task 自身不 wire** 此 7 值（lease_transition_writer 寫 `learning.lease_transitions`，不寫 `governance_audit_log`）。

```python
# 未來 caller (in handoff_routes.py / strategy_routes.py 等):
audit_payload = {
    "event_type": "lease_acquire_fail",  # V054 NEW enum
    "audit_data": {"intent_id": "...", "reason": "AuthNotEffective"},
    "context_id": "...",
}
gov_hub._change_audit_log.record_change(...)  # 走 V035 governance_audit_log
```

### 6.4 三環境 TOML messagebus_db_sink Contract — 給 Phase B（P1-AGENT-DB-SINK）

```python
# Phase B caller (in agent_audit_bridge.py 拓展 — P1 follow-up):
def _audit_callback(event_type: str, data: Any, priority: str = "NORMAL") -> None:
    # 1. Read [messagebus_db_sink] from runtime config
    # 2. If enabled=false → existing record_change() path (no change)
    # 3. If enabled=true:
    #    sample_pct = sampling_{priority.lower()}_pct  (LOW=1 / NORMAL=10 / HIGH=50 / CRITICAL=100)
    #    If random.uniform(0,100) > sample_pct → drop (sampled out)
    #    Else: route to agent.messages / agent.state_changes / agent.ai_invocations
    #          per event classification (existing _classify_event() logic)
    # 4. Fail-soft: PG outage → log warn + drop, never block MessageBus.send
```

---

## §7. 不確定之處 / Open issues

### 7.1 Task 描述路徑 `srv/rust/openclaw_engine/src/messagebus/db_sink.rs` 錯（push back）

task description §1 列：「`srv/rust/openclaw_engine/src/messagebus/db_sink.rs`（如不存在則新建；agent 三表 writer）」。但：
- MessageBus 在 Python 端 `program_code/exchange_connectors/bybit_connector/control_api_v1/app/multi_agent_framework.py`
- agent.messages / state_changes / ai_invocations 三表是 V003/V005 schema，由 Python 端 5-Agent 系統消費
- PA partition design §2 #4 明寫「Python `agent_audit_bridge.py` 拓展原有 `record_change()` 路徑分流三表」

**我跟 PA partition design 不跟 task description**。task description 路徑錯是 PM 派發時的 paste error；PM 確認後修正 task description。

### 7.2 agent 三表 PG wiring 拆 Phase A vs Phase B（push back）

1.0 day E-4 task **塞不下**「V054 SQL + lease_transition_writer + 三表 PG sink wiring」三項。三表 PG sink 需：
- db_pool conn 注入跨 4-5 module（multi_agent_framework / agent_audit_bridge / strategy_wiring / db_pool）
- 三表 INSERT 各自 payload mapping（agent.messages 7 col / agent.state_changes 5 col / agent.ai_invocations 12 col）
- sampling logic（按 priority enum 動態取 sample_pct）
- TOML hot-reload 對齊 ConfigStore（Python 側 config 是 RuntimeRiskConfig 對齊 Rust）

**我做 Phase A：TOML config schema 三環境獨立**（demo/paper/live 各自 sampling 比，per `feedback_env_config_independence`）。**Phase B：標 P1-AGENT-DB-SINK follow-up ticket**（真實 PG INSERT + sampling logic + db_pool 注入）。

E2 review 是否同意切割。如 E2 認為 1.0 day 應吃下 Phase A+B，請重派並指出時間預算來源。

### 7.3 emit Option A 改了 `governance_core.rs`（task 描述沒列 path）

選 Option A 強制需要修改 `srv/rust/openclaw_core/src/governance_core.rs` 加 inline emit hook。task description 絕對路徑只列：
- `srv/sql/migrations/V054__...`
- `srv/sql/migrations/REF-20_RESERVATION.md`
- `srv/rust/openclaw_engine/src/governance/lease_transition_writer.rs`
- `srv/rust/openclaw_engine/src/messagebus/db_sink.rs`
- `srv/settings/risk_config*.toml`

但 task description §3 明寫「E-1 push back §7.3 提的『emit 策略 A/B/C』由 E-4 自選」— 選 Option A 即必改 facade method body。我列入修改清單並雙語注釋說明。E2 review 是否同意「選 A → 必改 governance_core.rs」邊界擴張。

### 7.4 `governance_core.rs` 1498 LOC 接近 1500 hard cap

E-1 baseline 1251 → E-4 +247 = 1498 LOC。**未過** 1500 hard cap 但已**超** 800 警告線（既有狀態，amendment 0 強制要求） + 接近 hard cap 1 LOC 緩衝。

§九 pre-existing baseline exception clause **不嚴格適用**（baseline 1251 不是 1500+ 違反）。但本次新增 +247 LOC 屬必要 emit 接線：
- 19 LOC：`emit_transition_safe()` + `build_msg_from_last_transition()` + `resolve_engine_mode_tag()` 三 helper
- ~80 LOC：acquire_lease 加 inline emit 重寫（持鎖蒐集 3 筆 + 釋鎖 emit）
- ~80 LOC：release_lease 加 inline emit + profile 反推（持鎖蒐集 1-2 筆 + 釋鎖 emit）
- ~30 LOC：LeaseTransitionMsg.profile enum→String + comment + module note
- ~38 LOC：雙語 doc / Track H emit 策略說明

E2 review 必查：「能否抽 helper module（candidate `lease_facade.rs` / `governance_emit.rs`）」。我的判斷是不能在 E-4 task 範圍內抽（amendment 0 強制要求 + 抽會破 既有 8 facade unit test + 17 governance test backward compat）。**E5 P2 ticket 提早規劃**：下次 retrofit 前必抽。

### 7.5 V054 retention 0 設

V054 不設 `drop_chunks()` retention policy，依 CLAUDE.md §三 P2 ticket P2-WAVE-9-V047-V048-RETENTION 模式延至 follow-up P2 ticket。理由：
1. AC-1 baseline 累積需 7-30d window，不可 truncate
2. operator 硬體預算需逐表 retention review（PG ~4-8GB per memory `project_hardware_constraints.md`）
3. retention 參數是觀察性政策決策，非 schema-必要

開 P2 ticket：30d baseline 累積後 review；預期 default 90d retention with weekly chunk drop。

### 7.6 TimescaleDB extension 缺失 fallback

Mac dev PG 沒 TimescaleDB（我用 ad-hoc test DB `trading_ai_v054_test` dry-run）。V054 用：
```sql
DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable(...);
ELSE
    RAISE NOTICE 'V054: TimescaleDB extension not present; skipping hypertable promotion (table works as plain PG table)';
END IF;
END $$;
```

Mac dev → NOTICE skip + plain PG table 運作。Linux trade-core deploy 自動 hypertable 轉換（`if_not_exists => TRUE`）。

**E4 regression 必跑 Linux real PG 確認 hypertable promotion 正常**；本 task Mac dev 階段只能驗證 plain table 路徑。

### 7.7 V053 vs PA design 數字不對齊

PA design §3.3 line 277 寫 `V053 +7` (應是 13 值) 但 V053 實際 land 是 14 值（5 V035 + 1 V044 + 8 V053）。PA design partition 寫於 V053 land 之前。

**我寫 V054 用 14 + 7 = 21 而非 PA 寫的 20**，並在 V054 comment 內顯式列出 V053 14 enum 全列 + V054 NEW 7。schema drift 防衛 = 列出每個 enum 的 V### 來源 commit。

### 7.8 task spec 7 event_type vs PA design 7 衝突

task spec 7 個是 acquire/release-semantic（lease_acquire_request/success/fail + lease_release_consumed/failed/cancelled + lease_sm_transition）；PA design §3.3 7 個是 SM-state-name（lease_acquired/lease_activated/...）。

**我選 task spec 7 個** — 與 facade emit 語意對齊（一筆 row 對一個 acquire 或 release outcome 直接定位，不必 JOIN SM transition 表）。V054 governance_audit_log 21 值是 7 task spec 命名；`learning.lease_transitions.to_state` 是 9-value LeaseState UPPERCASE（aligned with sm/lease.rs::LeaseState::as_str()）。兩者皆可從 row 觀察 SM 級狀態演進。

PA design partition 偏向架構意圖；task description 通常更貼近實作意圖；衝突時 task 為主，design comment 註明分歧。

### 7.9 `LeaseTransitionMsg.profile` 從 GovernanceProfile enum 改 String 是 backward-compat 微調

E-1 §6.5 報告留的 `LeaseTransitionMsg` struct 中 `profile: GovernanceProfile`。我改為 `profile: String` 對齊 V054 chk_lease_transitions_profile 3-value CHECK enum + writer 不必 import `openclaw_core::GovernanceProfile`。

這是 **E-4 對 E-1 預留 struct 的微調**（E-1 §6.5 明寫「LeaseTransitionMsg Contract — 給 E-4 audit writer」，E-4 可微調 fields）。**不破 facade contract**（caller 看到 LeaseId 不變；emit 在 facade 內部用 `format!("{:?}", profile)` 轉 String）。

E2 review 是否同意 E-1 預留 struct 內部欄位 type 微調權給 E-4。

---

## §8. Operator 下一步

1. **E2 代碼審查**（重點區域）：
   - §6 4 條 contract 是否 lock-in 可給 E-2/E-3 直接 import
   - §7.1 task 描述路徑錯是否需要 PM 修正 task description
   - §7.2 agent 三表 PG wiring 拆 Phase B 是否同意（P1-AGENT-DB-SINK ticket）
   - §7.3 emit Option A 改 governance_core.rs 邊界擴張是否同意
   - §7.4 governance_core.rs 1498 LOC 接近 hard cap 是否需 P2 ticket 抽 helper
   - 6 unit test 是否覆蓋 V054 schema drift / fail-soft / 持鎖蒐集 + 釋鎖 emit pattern
   - V054 race-free pattern（V053 retrofit F2 模板）正確套用
   - 三環境 TOML 獨立 sampling 比合理（live 收緊 vs paper/demo 寬鬆）

2. **E4 regression**：
   - 跑 cargo test --workspace --tests --release 全綠驗證
   - **Linux trade-core real PG 跑 V054 hypertable promotion 驗證**（Mac dev 跑 plain table 路徑，hypertable 路徑只有 Linux 可驗）
   - Linux real PG 跑 24h baseline 累積觀察 AC-1 distinct count（amendment §4 AC-1）
   - MIT 看 E-4 對 E-1 預留 LeaseTransitionMsg struct 的微調（profile enum→String）是否破壞既有測試語意

3. **PM 後續派發排程**（依 PA design §6.2 + AMD-2026-05-02-01 Phase 1-6 灰度策略）：
   - **Day 1 PM** E-1 facade green + E-4 V054/writer green → PM 統一 commit Track H（E-1 + E-4 一次）
   - **Day 2** 派 E-3（Python IPC bridge）+ E-2（Rust router gate flag OFF）並行（V054 schema land 後 IPC + router 可同步開發）
   - **Day 3** 全部 land → E2 review + E4 regression + 5 AC probe + Linux deploy
   - **Day 7+ / P0-EDGE-2 結論後** flip `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` Phase 5 灰度

4. **不要 commit / push** — 等 E2/E4 + E-2/E-3 全 done 後 PM 統一 commit Track H 完整 patch

5. **不要 ssh trade-core deploy** — Linux deploy 在 Sprint 4 P0-EDGE-2 結論後（~2026-05-15）+ E-2 router gate flip 前

6. **P1-AGENT-DB-SINK follow-up ticket**（push back §7.2 切割的 Phase B）：
   - agent_audit_bridge.py 拓展 record_change() 路徑分流三表
   - sampling logic（按 priority dynamic sample_pct）
   - db_pool conn 注入跨 multi_agent_framework / agent_audit_bridge / strategy_wiring
   - 三表各自 payload mapping
   - 預估 0.8-1.0 day 獨立 E1 task

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--ref20_sprint3_track_h_e4_v054_audit_writer.md`）

---

## §9. Retrofit Log — Round 2 (E2 verdict HIGH-1 fix · 2026-05-03)

### §9.1 任務摘要 (round 2)

E2 round 1 verdict 退回 1 條 HIGH（`OPENCLAW_ENGINE_MODE` env var 沒 setter，emit 永遠 'demo'，AC-1 query `WHERE engine_mode != 'shadow'` partition 失效）。E1 自選實作策略 + push back task description 提出的「Option A 讀 system_mode.json」路徑（**system_mode.json 在本 repo 不存在 — 全 Mac/Linux/Python/Rust grep 0 hit**），改用 instance-injected pattern 對齊既有 `pipeline.effective_engine_mode()` 架構（mode_state.rs:38）。

**最終設計**：
1. `GovernanceCore` 新增 `engine_mode_tag: Option<String>` 欄位 + `set_engine_mode_tag()` setter
2. `resolve_engine_mode_tag()` 改 instance method：優先 self-injected → fallback OPENCLAW_ENGINE_MODE env var → fallback `'unknown'` sentinel
3. `tick_pipeline/pipeline_ctor.rs::set_endpoint_env()` 加一行 `self.governance.set_engine_mode_tag(self.effective_engine_mode().to_string())` — pipeline-aware tag wiring（每個 pipeline boot 時透過既有 effective_engine_mode resolver 自動 wire）
4. **抽 `governance_emit.rs` 模組**（同 crate）— LeaseTransitionMsg / LeaseTransitionSender / LeaseId / LeaseOutcome / GovernanceError + 3 helper（build_msg / emit_fail_soft / EngineModeTagResolver），governance_core.rs 從 round 1 的 1498 縮回 **1491 LOC**（緩衝 9 LOC 給 E-1 retrofit 並行）
5. governance_core.rs `pub use crate::governance_emit::{...}` re-export 保持 caller path 不變（router.rs / lease_transition_writer 等 0 改動）

### §9.2 修改清單 (round 2，4 檔)

| 檔案 | 改動 | LOC 變化 |
|---|---|---|
| `srv/rust/openclaw_core/src/governance_emit.rs` | NEW — LeaseTransitionMsg + Sender + LeaseId + LeaseOutcome + GovernanceError + EngineModeTagResolver + 3 helper + 12 unit test（含 process-wide ENV_LOCK Mutex 解 cargo parallel race） | 622 |
| `srv/rust/openclaw_core/src/governance_core.rs` | 移除 emit-side types + 3 helper（搬 governance_emit）；加 `engine_mode_tag` 欄位 + `set_engine_mode_tag()` setter；改 `resolve_engine_mode_tag()` 為 instance method；caller 改呼 module-level helper | 1498 → **1491**（淨 -7） |
| `srv/rust/openclaw_core/src/lib.rs` | `pub mod governance_emit` | +8（含註解） |
| `srv/rust/openclaw_engine/src/tick_pipeline/pipeline_ctor.rs` | `set_endpoint_env()` 加 `self.governance.set_engine_mode_tag(self.effective_engine_mode().to_string())` 注入 | +14 |
| `srv/rust/openclaw_core/tests/engine_mode_tag_e2e.rs` | NEW — 6 e2e integration test（4 trading_mode + shadow + unknown fail-soft）；驗 set_engine_mode_tag 注入 → acquire_lease/release_lease emit msg.engine_mode 對應 | 211 |

### §9.3 push back（已 PM 隱含同意 / 已 in-line 處理）

#### §9.3.1 task description 「Option A 讀 system_mode.json」是錯路徑（**未採用，push back 並改 Option C-improved**）

task description 提出兩個 option：(A) 讀 `OPENCLAW_DATA_DIR/system_mode.json` + cache + 取 trading_mode 字段；(B) 改 helper_scripts/restart_all.sh export env var。

**經 grep 證實 system_mode.json 在本 repo 0 hit**：
```bash
grep -rn "system_mode.json" srv/rust/ srv/program_code/ srv/helper_scripts/  # 0 hit
ls $HOME/.openclaw_runtime/                                                    # 無 system_mode.json
ssh trade-core "ls -la /tmp/openclaw/*.json"                                  # 無 system_mode.json
```

實際 trading_mode 持久化是 `pipeline_snapshot_{paper,demo,live}.json`（每 pipeline 一份，含 trading_mode 字段）— 但這是 IPC snapshot 用，非 governance 真實 source。**真實 source-of-truth** 是 `crate::mode_state::effective_engine_mode(PipelineKind, Option<BybitEnvironment>)`（mode_state.rs:38），透過 `pipeline.effective_engine_mode()` instance method（pipeline_ctor.rs:189）取得 — pipeline 構造時即知 endpoint。

**選 Option C-improved（instance-injected）**：
- 不撞 hot path（無 fs::read 在 acquire_lease 內）
- 不依賴不存在的 system_mode.json
- 不依賴 helper_scripts/restart_all.sh（Mac dev 沒此啟動路徑）
- 對齊既有 pipeline.effective_engine_mode() 架構，0 新概念
- pipeline boot 時 set_endpoint_env() 自動 chain wire（既有 setter pattern，0 新呼叫點）

E2 round 2 review 必查：是否同意 Option C-improved 取代 task description 提的 Option A/B。我的判斷：Option C-improved 是 strict superset，無 downside。

#### §9.3.2 governance_core.rs 1491 LOC vs hard cap 1500（**自行抽 governance_emit.rs 緩衝**）

task description 預警：「governance_core.rs 1498 LOC 距 hard cap 2 LOC — HIGH-1 修加 ~30 LOC 必撞 1500；提早做 P2-GOV-CORE-EMIT-EXTRACT 抽 helper（governance_emit.rs）並把 resolve_engine_mode_tag 一起搬過去」。

**已照 task 指令做**：抽出 governance_emit.rs（622 LOC），governance_core.rs 縮回 1491 LOC（緩衝 9 LOC for E-1 retrofit 並行）。涵蓋的搬遷項：
- LeaseTransitionMsg + LeaseTransitionSender（round 1 已在 governance_core.rs 內）
- LeaseId + LeaseOutcome + GovernanceError（round 1 facade types section）
- emit_transition_safe → emit_transition_fail_soft（module-level free fn）
- build_msg_from_last_transition（module-level）
- resolve_engine_mode_tag → EngineModeTagResolver::resolve（instance-aware fallback chain）

`pub use crate::governance_emit::{...}` re-export 保持 caller path 不變 — router.rs / lease_transition_writer / intent_processor 等 0 改動。

#### §9.3.3 6 e2e test 放 integration test 檔（不放 governance_core::tests）

加 6 個 end-to-end test 驗證 set_engine_mode_tag 注入 → acquire_lease/release_lease emit msg.engine_mode 對應。如果放 governance_core::tests，會把 governance_core.rs 推到 1669 LOC（嚴重超 hard cap 169 LOC）。

決策：放獨立 `tests/engine_mode_tag_e2e.rs`（211 LOC），governance_core.rs 維持 1491 LOC。e2e test 用 `pub use` 路徑 import GovernanceCore + facade types，0 額外 binding。

E2 review 必查：是否同意「e2e test 放 integration test 檔」是 LOC budget 友好的合理選擇。

#### §9.3.4 lib test parallel race + ENV_LOCK Mutex 修法

`governance_emit::tests` 內 4 個 env-var-dependent test（fallback / invalid / override / no-injection）會撞 cargo test default parallel runner（`set_var` cross-thread race）。第一次跑 `cargo test -p openclaw_core --release --lib governance_emit` → 2 fail。

修法：`with_env_var` helper 加 `static ENV_LOCK: Mutex<()>`，序列化所有觸 env var 的 test。**5 連續 stability run 全 PASS**。

無依賴 `serial_test` crate（保持 0 新依賴 per CLAUDE.md §七 依賴管理乾淨原則）。

### §9.4 治理對照（round 2 強制檢查）

| 檢查項 | 結果 |
|---|---|
| 雙語 MODULE_NOTE EN/中（governance_emit.rs 頂部）| ✅ |
| 雙語 docstring（4 新公開介面：set_engine_mode_tag / resolve_engine_mode_tag instance / EngineModeTagResolver / VALID_TAGS const）| ✅ |
| `grep -E '/home/ncyu\|/Users/[^/]+'` 5 改動檔 | 0 hit ✅ |
| `max_retries` / `live_execution_allowed` / `execution_authority` / `system_mode` / `OPENCLAW_ALLOW_MAINNET` / `authorization.json` | 0 觸碰 ✅ |
| 0 SQL（V054 schema 不變 / 0 INSERT/UPDATE/DELETE）| ✅（grep INSERT 命中全為 doc comment）|
| 0 trading.* mutate / 0 live_* mutate | ✅ |
| 文件 ≤800 警告 / ≤1500 hard | governance_core.rs **1491** ✅（< 1500 hard，緩衝 9 LOC for E-1 retrofit）；governance_emit.rs **622** ✅（< 800 警告）；engine_mode_tag_e2e.rs **211** ✅；pipeline_ctor.rs **464** ✅ |
| 新 singleton 登記 §九 表 | 無新 singleton（GovernanceCore.engine_mode_tag 是 per-instance Option<String> 欄位，非 singleton）|
| Stability 跑 cargo test ≥3 次 | ✅ 5 連續 governance_emit lib test + 3 連續 full workspace test 全 PASS |

### §9.5 測試結果 (round 2)

| 測試套件 | 結果 |
|---|---|
| `cargo test -p openclaw_core --release --lib`（含新 12 governance_emit::tests）| **415 PASS / 0 fail**（baseline 401 + 12 新 + 既有 2 整理）|
| `cargo test -p openclaw_core --release --test engine_mode_tag_e2e`（6 e2e 整合 test）| **6 PASS / 0 fail** |
| `cargo test --release --tests --workspace`（全套件）| **3132 PASS / 0 fail / 26 test bin**（cumulative round 1 → round 2 +12 lib tests + 6 e2e tests）|
| `cargo build --workspace --release` | **0 error**（21 pre-existing dead_code warning 與 round 2 無關）|
| 5 連續 `cargo test -p openclaw_core --release --lib governance_emit` | **5/5 stable**（ENV_LOCK Mutex 修 cargo parallel race）|
| 3 連續 `cargo test --release --tests --workspace` | **3/3 stable** 3132 PASS |

### §9.6 Coverage check vs task description 必測 case

| Task case | Coverage |
|---|---|
| 1. trading_mode=paper 驗 tag | ✅ `governance_emit::tests::test_resolve_engine_mode_tag_paper_injected` + `engine_mode_tag_e2e::test_engine_mode_tag_paper_emit_via_acquire_lease` |
| 2. trading_mode=live_demo（task 標 "live_demo" 對齊 V054 enum）| ✅ `..._live_demo_injected` + `..._live_demo_emit_via_acquire_and_release`（含 release path 驗 5 msg）|
| 3. trading_mode=live | ✅ 改名 `live_mainnet`（V054 enum 命名）`..._live_mainnet_injected` + `..._live_mainnet_emit_via_acquire_lease` |
| 4. trading_mode=shadow | ✅ `..._shadow_injected` + `..._shadow_emit_via_acquire_lease`（含 AC-1 filter context comment）|
| 5. file 不存在 → 'unknown' fail-soft | ✅ `..._no_injection_no_env_fallback_unknown` + `engine_mode_tag_e2e::test_engine_mode_tag_no_injection_falls_back_to_unknown`（acquire_lease 觸發 → emit msg.engine_mode='unknown'）|

額外 4 個 robustness case：
- `..._env_var_fallback_when_no_injection`（env 補位無注入）
- `..._invalid_injection_falls_through_to_env`（不合法注入 fallback env）
- `..._invalid_env_falls_through_to_unknown`（不合法 env fallback unknown）
- `..._injection_overrides_env`（注入 vs env 優先序）

加 2 個 emit fail-soft case：
- `test_emit_transition_fail_soft_no_sender_no_panic`
- `test_emit_transition_fail_soft_dropped_receiver_swallows_error`

**Total: 6（必測）+ 6（額外）+ 2（emit）= 14 test 覆蓋；task 要求 ≥5 unit test，達成 280%。**

### §9.7 Operator 下一步 (round 2)

1. **E2 round 2 代碼審查**（重點區域）：
   - §9.3.1 task description 提出 Option A/B 路徑被 push back（system_mode.json 0 hit），改用 Option C-improved instance-injected 是否同意
   - §9.3.2 抽 governance_emit.rs 622 LOC 是否獲准（task description 預警 P2-GOV-CORE-EMIT-EXTRACT 提早做）
   - §9.3.3 6 e2e test 放 integration test 檔不放 governance_core::tests 是否同意
   - §9.3.4 ENV_LOCK Mutex 修 cargo parallel race 是否同意（無新依賴）
   - 12 lib unit test + 6 e2e integration test 是否覆蓋 task description 必測 5 case + 額外 9 case
   - governance_core.rs 1491 LOC 緩衝 9 LOC 給 E-1 retrofit 是否足夠
   - pipeline_ctor.rs::set_endpoint_env 注入 14 LOC 是否撞既有 set_endpoint_env signature 或 caller chain（已驗 0 撞 — full workspace test 3132/3132 PASS）

2. **E4 round 2 regression**：跑 `cargo test --release --tests --workspace` 全綠驗證；檢查 round 2 是否破壞 round 1 既有 lease_transition_writer 6 unit test + intent_processor 8 fixture / 7 router_gate test 等。

3. **PM 後續派發排程**（不變）：
   - **Day 1（今天）** E1 round 2 retrofit done → 待 E2 round 2 review + E4 round 2 regression
   - **Day 2-3** E-3（Python IPC bridge）+ E-2（Rust router gate flag OFF）已 land → 全部 done 後 PM 統一 commit Track H
   - **Sprint 4 P0-EDGE-2 後 ~2026-05-15** operator flip `OPENCLAW_LEASE_ROUTER_GATE_ENABLED=1` 24h canary

4. **不要 commit / push** — round 2 仍待 E2 round 2 review；PM 一次 commit Track H 完整 retrofit patch（round 1 + round 2）

5. **不要呼 E2 / E4** — 等 PM 派發

---

E1 IMPLEMENTATION DONE (Round 2): 待 E2 round 2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--ref20_sprint3_track_h_e4_v054_audit_writer.md` §9）
