# G3-08 Phase 4 — 5-Agent State Events Design RFC（PA Plan Only）

- **作者**：PA（Project Architect）
- **日期**：2026-04-27 CEST
- **Tier**：G3-08 Phase 4
- **狀態**：Plan only — 不寫實作代碼，純設計 + 5 self-contained E1 prompt template
- **依賴前置**（硬阻塞）：
  - G3-08 Phase 1A Rust h_state_cache（commit `aa287c4`）✅
  - G3-08 Phase 1B Python invalidator + query_handler（commit `1c7b20e`）✅
  - G3-08 Phase 1C strategy_wiring + healthcheck [20]（commit `5943337`）✅
  - G3-08 Phase 2 H1+H3 integration（commits `9120948` + `f2ed286`）✅
  - G3-08 Phase 3 Sub-task 3-1/3-2/3-3（commits `8cd257e` + `71faf4c` + `1c7b20e`）✅
  - **Sub-task 4-1 hard pre-condition**：G3-08-PHASE-4-STRATEGIST-SPLIT 落地（commit 待，並行進行中，per Phase 4 split RFC §9）
  - 其他 4 sub-task 無 split 依賴（Guardian 587 / Analyst 834 / Executor 669 / Scout 在 multi_agent_framework.py 1137 裡的 ScoutAgent class（L379-561 ~183 LOC））
- **解阻 後續**：
  - G8-01 認知自適應 e2e 測試（Rust fixture 看 5-Agent observability 為主，弱依賴 H2/H5）
  - G3-09 cost_edge_advisor 跨 Agent 訂閱（cost_edge_ratio 與 5-Agent stats 相關性分析）
  - 未來 GUI 統一 6-pane dashboard（H1-H5 + 5-Agent 同 IPC pull）

---

## §1 背景：為何 hot-path 需要 5-Agent state + Phase 1-3 關係

### 1.1 5-Agent 狀態的 Rust 消費者

OpenClaw 5-Agent（Strategist / Guardian / Analyst / Executor / Scout）皆為 Python 進程內 BaseAgent 子類，stats 全在 `self._stats: dict[str, int]` + `self._lock` 保護。當前 Rust hot-path（governance / risk_gate / executor IPC dispatch / cost_edge_advisor 設計中）**完全看不到** 5-Agent 即時 stats，造成 4 個 hot-path 缺口：

| # | Rust 模組 | 需要 5-Agent stats 的場景 | 當前 fallback |
|---|---|---|---|
| 1 | **governor** (governance_hub.rs) | Strategist `intents_produced` / `evaluations_rejected` 比率異常時降頻 | 無，純 Python observability |
| 2 | **executor IPC** (ipc_server/handlers/submit_order.rs) | Executor `executions_failed / executions_attempted` > 0.5 → 拒收新 intent（Reconciler 兜底前的快速防線） | 無 |
| 3 | **cost_edge_advisor**（G3-09 設計中） | Analyst `l2_analyses` 高頻 + Strategist `ai_evaluations` 高頻 + cost_edge_ratio ≥ 0.8 三條件複合判定 | G3-09 設計目前只能取 H5 一個 lens |
| 4 | **scout dormancy detector**（未來） | Scout `intel_produced` 0/30min + `scans_completed` > 0 → 訊號 silent dead | 當前需 Python healthcheck cron 補 |

**關鍵設計判斷**：5-Agent stats 與 H1-H5 屬**同類觀測訊號**（counter / gauge / latency hint），共用 `h_state_cache` DashMap 機制最低成本最大複用。Phase 4 = Phase 1-3 pattern 鏡射延伸到 agent 維度。

### 1.2 與 Phase 1-3 的 H state cache 關係

| Slot 類型 | Phase | DashMap key | SSOT | snapshot accessor | invalidate hint |
|---|---|---|---|---|---|
| H middleware × 5 | Phase 2/3 | `h1` / `h2` / `h3` / `h4` / `h5` | 對應 H 模組（h1_thought_gate / cost_tracker / model_router / strategist_caller-side / cost_tracker） | `get_h<N>_snapshot()` | `invalidate_async("h<N>.<event>")` |
| **Agent × 5 (Phase 4)** | **Phase 4** | `strategist` / `guardian` / `analyst` / `executor` / `scout` | 對應 BaseAgent 子類 `self._stats` | **新增 `get_<agent>_snapshot()`** | **新增 `invalidate_async("agent.<role>.<event>")`** |

**核心 invariant**：Phase 4 不變更 schema version（保持 `_PHASE2_VERSION = 1`），新增 `agent_states` bucket 為**加性 forward-compat**（per `h_state_query_handler.py` MODULE_NOTE L54-58 + Phase 1A Rust `AgentState.stats: HashMap<String, i64>` 已備）。

### 1.3 Phase 1-3 證明的 4 條 pattern law

- **Law 1（accessor 在 SSOT 自身或最近 caller）**：H4 caller-side stats 在 strategist；Phase 4 各 agent 的 `_stats` 即在自身，**無 caller-side 例外**，比 H4 更乾淨。
- **Law 2（snapshot 純讀 + 自身鎖）**：每個 agent 已有 `self._lock`（threading.Lock），與 H1/H3 對等模式。
- **Law 3（invalidate hint 逐 event 推，非定時推）**：H5 高頻 case 已驗 100k call < 30s（`h_state_invalidator` daemon thread 模型）。Phase 4 各 agent emit 頻率（Strategist intel handle ~5/min、Executor execute ~1/min、Scout scan ~2/min）皆遠低於 H5。
- **Law 4（query_handler bucket 加入是 additive，無 schema bump）**：Phase 3 已驗 — `agent_states: {}` Phase 1 已備 buckets，Phase 4 填入 5 key。

### 1.4 為何 Phase 4 拆 5 sub-task

PA design plan §11.1 估 Phase 4 全鏈 **4d wall-clock**（Python E1 3d + E2 0.5d + E4 0.5d）。Phase 3 的 Pattern B（per-H 模組整鏈）證明「1 模組 = 1 sub-task」是收斂值。Phase 4 自然延伸為 **5 sub-task = per-agent 整鏈**，理由：

1. **5 個 agent 主檔**獨立，**不共享熱寫檔**（不同於 Phase 3 layer2_cost_tracker 同檔雙修衝突）→ **4 sub-task 可並行**（4-1 等 split）
2. **Roll-back 粒度 per-agent**（任一 sub-task fail 不影響其他 4 個）
3. **context 壓力可控**（Phase 1+2+3 經驗：1 agent / 1 模組 ~80 LOC + ~30 tests = 1 session 舒適）

---

## §2 每 agent snapshot schema 設計

### 2.1 Strategist snapshot schema

**SSOT**：`StrategistAgent._stats` (`strategist_agent.py:189-216`)。Phase 3 Sub-task 3-2 已加 `h4_validation_pass`；Phase 4 不再動 H4 stats，只新增 agent-level snapshot。

| Snapshot key | Source `_stats` key | 對應 hot-path 用例 |
|---|---|---|
| `intel_received` | `intel_received` | Scout→Strategist 流量觀測 |
| `intel_evaluated` | `intel_evaluated` | dispatch 是否暢通 |
| `intents_produced` | `intents_produced` | live intent 產出率 |
| `intents_shadow_logged` | `intents_shadow_logged` | shadow_mode=True 時 strategist 路徑驗證 |
| `evaluations_rejected` | `evaluations_rejected` | rejection 比率（governor 用） |
| `ai_evaluations` | `ai_evaluations` | Layer 2 自主推理使用率（cost_edge_advisor 用） |
| `heuristic_evaluations` | `heuristic_evaluations` | L0/L1 fallback 比率 |
| `errors` | `errors` | 錯誤累積（healthcheck FAIL 觸發） |
| `pending_intents` | `len(self._pending_intents)` | gauge：當前隊列 |
| `emergency_mode_active` | `self._emergency_mode.is_set()` | bool（V2 雙軌 fast channel 狀態） |
| `cognitive_modulator_connected` | `self._cognitive_modulator is not None` | bool（G8-01 認知接入指示） |

**Schema 注意事項**：
- 全為 `int` 或 `bool`（hot-path 友善，無 float / string）
- `pending_intents` 是 gauge 不是 counter；Phase 4 settle 為純讀，未來如需 percentile 化在 G8-01 處理
- 11 fields > Phase 3 H1/H3 的 4-7 fields，但仍可控（Rust `AgentState.stats: HashMap<String, i64>` 動態 schema）

**LOC 預估**：method ~30 LOC（含雙語 docstring + schema 註解 + with self._lock）。

### 2.2 Guardian snapshot schema

**SSOT**：`GuardianAgent._stats` (`guardian_agent.py:135-142`)。

| Snapshot key | Source | 用例 |
|---|---|---|
| `intents_reviewed` | `_stats["intents_reviewed"]` | risk_gate 流量 |
| `verdicts_approved` | `_stats["verdicts_approved"]` | approve 比率（risk_gate 健康度） |
| `verdicts_rejected` | `_stats["verdicts_rejected"]` | reject 比率（governor 用） |
| `verdicts_modified` | `_stats["verdicts_modified"]` | 風控降倉次數 |
| `events_assessed` | `_stats["events_assessed"]` | Scout 事件流量 |
| `errors` | `_stats["errors"]` | 錯誤累積 |
| `active_event_risks` | `len(self._active_event_risks)` | gauge：當前事件風險數 |
| `verdict_log_size` | `len(self._verdict_log)` | gauge：log buffer 充滿度 |

**LOC 預估**：method ~25 LOC（8 fields，比 Strategist 少 → 更短）。

### 2.3 Analyst snapshot schema

**SSOT**：`AnalystAgent._stats` (`analyst_agent.py:228-234`)。

| Snapshot key | Source | 用例 |
|---|---|---|
| `trades_analyzed` | `_stats["trades_analyzed"]` | l1 update 流量 |
| `l1_updates` | `_stats["l1_updates"]` | EarnedTrust 寫入次數 |
| `l2_analyses` | `_stats["l2_analyses"]` | L2 推理次數（cost_edge_advisor 用） |
| `errors` | `_stats["errors"]` | 錯誤累積 |
| `experiment_ledger_connected` | `self._experiment_ledger is not None` | bool（學習平面接入） |

**LOC 預估**：method ~20 LOC（5 fields）。

### 2.4 Executor snapshot schema

**SSOT**：`ExecutorAgent._stats` (`executor_agent.py:198-207`) + `_shadow_mode_provider()`。

| Snapshot key | Source | 用例 |
|---|---|---|
| `intents_received` | `_stats["intents_received"]` | dispatch 流量 |
| `intents_deduped` | `_stats["intents_deduped"]` | ARCH-1 去重觸發次數 |
| `executions_attempted` | `_stats["executions_attempted"]` | submit_order IPC 嘗試 |
| `executions_success` | `_stats["executions_success"]` | submit_order 成功 |
| `executions_failed` | `_stats["executions_failed"]` | **執行失敗（hot-path 預警觸發點）** |
| `total_slippage_bps` | `int(_stats["total_slippage_bps"])` | 累積滑點 bps（cast 為 int） |
| `errors` | `_stats["errors"]` | 錯誤累積 |
| `recent_intent_id_size` | `len(self._recent_intent_ids)` | gauge：去重 buffer |
| `shadow_mode` | `bool(self._shadow_mode_provider())` | bool（G3-03 ConfigStore 提供，shadow→live 切換指示） |

**Schema 注意事項**：
- `total_slippage_bps` 在 `_stats` 是 `float`（line 205 `0.0`），snapshot **必 cast 為 int**（per Phase 3 H5 對 cost_edge_ratio 的處理 — `Optional[float]` 例外才保 float；其他全 int）
- `shadow_mode` 是**最重要的單一 hot-path 訊號**：Rust executor IPC handler 可即時驗證 Python 端 shadow flag 與 Rust ConfigStore 是否同步（G3-03 Phase B 已 wire ExecutorConfigCache，但目前 Rust 看不到 Python provider 的實時值）

**LOC 預估**：method ~28 LOC（9 fields）。

### 2.5 Scout snapshot schema

**SSOT**：`ScoutAgent._stats`（`multi_agent_framework.py:431` — 整 class L379-561）。

| Snapshot key | Source | 用例 |
|---|---|---|
| `intel_produced` | `_stats["intel_produced"]` | Scout→Strategist 流量 |
| `alerts_produced` | `_stats["alerts_produced"]` | Scout→Guardian 流量 |
| `scans_completed` | `_stats["scans_completed"]` | scan loop 健康度 |
| `intel_log_size` | `len(self._intel_log)` | gauge：buffer |
| `alert_log_size` | `len(self._alert_log)` | gauge：buffer |

**LOC 預估**：method ~18 LOC（5 fields，最簡）。

### 2.6 Schema versioning 策略（與 Phase 1-3 對齊）

**Forward-compat 機制**（per Phase 1A Rust `AgentState.stats: HashMap<String, i64>` + `#[serde(default)]`，per `h_state_query_handler.py` MODULE_NOTE）：

| 變更類型 | Phase 4 處理 | Schema version |
|---|---|---|
| 新增 stats key | Python 加 → Rust 自動接（HashMap 容忍） | 維持 1 |
| 移除 stats key | Python 砍 → Rust serde 視為缺失（`#[serde(default)]` 補 0） | 維持 1 |
| 改 key type（int → string） | **breaking** — bump version → 2 + Phase 4-FUP migration | bump |
| 加新 agent（如未來 Conductor） | 加新 bucket key → handler 加 include flag | 維持 1（additive） |

**Phase 4 預期不 bump version**：5 agent 全 int / bool 字段，與既有 H state shape 一致。

### 2.7 跨 Phase summary（H + 5-Agent 全圖）

完成 Phase 4 後 `query_h_state_full` 回傳：

```json
{
  "version": 1,
  "fetched_at_ms": 1745923200000,
  "h_states": {
    "h1": {...4 fields},
    "h2": {...3 fields},
    "h3": {...7 fields},
    "h4": {...2 fields},
    "h5": {...4 fields}
  },
  "agent_states": {
    "strategist": {...11 fields},
    "guardian":   {...8 fields},
    "analyst":    {...5 fields},
    "executor":   {...9 fields},
    "scout":      {...5 fields}
  }
}
```

合計 5 H bucket + 5 agent bucket = **10 bucket / ~58 fields**。

---

## §3 h_state_query_handler.py extension 設計

### 3.1 query_h_state_full schema v1 → v1（不升 version）

Phase 4 維持 `_PHASE2_VERSION = 1`（per §2.6）。

**API 不變**：
- 公開函式 `build_h_state_full_response(include=None)` 簽名不變
- `include` filter 擴展支援 5 個新 bucket name：`["strategist", "guardian", "analyst", "executor", "scout"]`
- Phase 1 fallback shape 不變（`version=0` + 空 dict）

### 3.2 _collect_h_snapshots 升級設計

**當前簽名（Phase 3 完成後）**：

```python
def _collect_h_snapshots(
    include_h1: bool,
    include_h3: bool,
    include_h2: bool = False,
    include_h4: bool = False,
    include_h5: bool = False,
) -> tuple[Optional[dict], Optional[dict], Optional[dict], Optional[dict], Optional[dict]]:
```

**Phase 4 升級兩個選項**：

#### Option A — 同函式擴展（10 參數 / 10-tuple 返回）

```python
def _collect_h_snapshots(
    include_h1, include_h3, include_h2=False, include_h4=False, include_h5=False,
    include_strategist=False, include_guardian=False, include_analyst=False,
    include_executor=False, include_scout=False,
) -> tuple[Optional[dict], ...]  # 10-tuple
```

- ✅ 沿襲 Phase 3 pattern 簡單
- ❌ 10-tuple 返回值難讀；參數列過長
- ❌ Phase 5（如 Conductor）擴展 = 12-tuple，繼續惡化

#### Option B — 拆兩個 collector（推薦）

```python
def _collect_h_snapshots(  # H1-H5 only, Phase 3 簽名不變
    include_h1, include_h3, include_h2=False, include_h4=False, include_h5=False,
) -> tuple[Optional[dict], Optional[dict], Optional[dict], Optional[dict], Optional[dict]]:
    # ...

def _collect_agent_snapshots(  # 新增 Phase 4
    include_strategist=False, include_guardian=False, include_analyst=False,
    include_executor=False, include_scout=False,
) -> dict[str, Optional[dict[str, Any]]]:  # 直接返回 dict 而非 tuple
    """
    Returns:
        {
          "strategist": Optional[dict],
          "guardian":   Optional[dict],
          ...
        }
    """
```

- ✅ 職責分離（H middleware vs agent observation）
- ✅ Phase 3 caller 完全不動（_collect_h_snapshots 簽名不變）
- ✅ 返回 dict 而非 tuple → Phase 5 加 agent 不破壞 caller
- ✅ Phase 4 Sub-task 4-1~5 可漸進填充（先 4-1 commit Strategist，dict 含 `"strategist": dict + 其他 None`，逐步 Sub-task 補齊）

**推薦 Option B**。

### 3.3 build_h_state_full_response 升級

```python
def build_h_state_full_response(include: Optional[list[str]] = None) -> dict[str, Any]:
    fetched_at_ms = int(time.time() * 1000)

    if include is not None and not isinstance(include, list):
        include = None

    # H bucket flags（不變）
    if include is None:
        include_h1 = include_h3 = include_h2 = include_h4 = include_h5 = True
        # Phase 4 新增
        include_strategist = include_guardian = include_analyst = True
        include_executor = include_scout = True
    else:
        include_h1 = "h1" in include
        # ...
        include_strategist = "strategist" in include
        include_guardian = "guardian" in include
        include_analyst = "analyst" in include
        include_executor = "executor" in include
        include_scout = "scout" in include

    if not _is_gateway_enabled():
        return { "version": 0, "fetched_at_ms": fetched_at_ms,
                 "h_states": {}, "agent_states": {} }

    # H state 聚合（Phase 3 既有）
    h1_dict, h3_dict, h2_dict, h4_dict, h5_dict = _collect_h_snapshots(
        include_h1, include_h3, include_h2, include_h4, include_h5,
    )
    h_states = {}
    if h1_dict is not None: h_states["h1"] = h1_dict
    # ... 5 個

    # Agent state 聚合（Phase 4 新增）
    agent_dict_map = _collect_agent_snapshots(
        include_strategist, include_guardian, include_analyst,
        include_executor, include_scout,
    )
    agent_states = {k: v for k, v in agent_dict_map.items() if v is not None}

    # version: 至少一桶為真實時升 version；空殼維持 fallback
    if h_states or agent_states:
        version = 1
    else:
        version = 0

    return {
        "version": version,
        "fetched_at_ms": fetched_at_ms,
        "h_states": h_states,
        "agent_states": agent_states,  # Phase 4 填入
    }
```

**LOC 預估**：總 handler 從 636 → ~720（+84 LOC：`_collect_agent_snapshots` ~50 + flag handling ~20 + 雙語 docstring ~14）。**遠低 §七 警告線 800**。

### 3.4 各 agent 注入點（agent SSOT 來源）

| Agent | strategy_wiring 中的 module-level singleton | 取值路徑 |
|---|---|---|
| Strategist | `STRATEGIST_AGENT` | `_sw.STRATEGIST_AGENT.get_strategist_snapshot()` |
| Guardian | `GUARDIAN_AGENT` | `_sw.GUARDIAN_AGENT.get_guardian_snapshot()` |
| Analyst | `ANALYST_AGENT` | `_sw.ANALYST_AGENT.get_analyst_snapshot()` |
| Executor | `EXECUTOR_AGENT` | `_sw.EXECUTOR_AGENT.get_executor_snapshot()` |
| Scout | `SCOUT_AGENT` | `_sw.SCOUT_AGENT.get_scout_snapshot()` |

**注入驗證**：grep `strategy_wiring.py` 確認 5 singleton 全 module-level（已驗 STRATEGIST_AGENT 是；其他 4 個由 E1 sub-task 驗證並在 prompt template `必讀` 步驟之 grep 確認）。如某 agent singleton 不存在 module-level（例：ScoutWorker 在 `scout_worker.py` 而 ScoutAgent 在 `multi_agent_framework.py`），sub-task 4-5 prompt 內含 grep 步驟讓 E1 找到正確 singleton 名稱（例如 `_SCOUT_AGENT_FOR_STRATEGIST` 之類）。

### 3.5 invalidator hook 接線點（每 agent _handle_<msg> hot-path）

| Agent | 必加 hook 位置 | reason 字串 |
|---|---|---|
| Strategist | `_handle_intel` 結尾 + `_produce_intents` 結尾（Sub-task 4-1）| `"agent.strategist.intel_handled"` / `"agent.strategist.intent_produced"` |
| Guardian | `_handle_trade_intent` 結尾 + `_handle_event_alert` 結尾 | `"agent.guardian.intent_reviewed"` / `"agent.guardian.event_assessed"` |
| Analyst | `_handle_round_trip` 結尾 | `"agent.analyst.round_trip_analyzed"` |
| Executor | `_handle_approved_intent` 結尾（success / failed 分支末加） | `"agent.executor.execution_complete"` / `"agent.executor.execution_failed"` |
| Scout | `produce_intel()` 結尾 + `produce_alert()` 結尾 + `_complete_scan()` 結尾 | `"agent.scout.intel_produced"` / `"agent.scout.alert_produced"` / `"agent.scout.scan_completed"` |

**Reason 命名 convention**：`agent.<role>.<event>` 兩層 namespace + 動詞過去式（與 Phase 1-3 `h<N>.<event>` pattern 對齊）。

**hook 數量上限**：每 agent ≤3 hook（per Phase 1 Risk 8.2 建議 < 50/sec spawn rate；5 agent × 3 hook × 真實流量 ≤10/agent/min = ~150/min = 2.5/sec，遠低警戒）。

---

## §4 Rust DashMap shard 擴展

### 4.1 AgentState slot：5 個新 sibling key

Phase 1A Rust `h_state_cache::types` 已備（per design `2026-04-26--g3_08_h1_h5_ipc_gateway_design.md` §5.2 + L468「pub struct AgentState」）：

```rust
// rust/openclaw_engine/src/h_state_cache/types.rs（Phase 1A 已備，Phase 4 不改）
#[derive(Clone, Debug, Default, serde::Deserialize, serde::Serialize)]
pub struct AgentState {
    #[serde(default)]
    pub stats: std::collections::HashMap<String, i64>,
    #[serde(default)]
    pub last_updated_ms: u64,
}
```

### 4.2 Cache slot 擴展（Phase 4 唯一 Rust 改動，集中於 mod.rs poller）

**當前 Rust hot-path query**（per Phase 1A `h_state_cache/mod.rs` `query_h_state` fn）：

```rust
// 假設既有 h hash key 已支援 "h1".."h5"
pub fn query_h_state(cache: &HStateCache, bucket: &str, field: &str) -> Option<i64>
```

**Phase 4 擴展**：

```rust
// 新增 agent state query（Sub-task 4-N 任一 land 後 hot-path 可即用）
pub fn query_agent_state(cache: &HStateCache, agent: &str, field: &str) -> Option<i64>
```

兩個 fn 共用同 DashMap（per design `g3_08_h1_h5_ipc_gateway_design.md` L211 「agents: DashMap<&'static str, AgentState>」槽位 Phase 1A 已備）。

**LOC 預估**：~30 LOC（新 fn + 5 unit test）。

**注意**：Phase 1A 已備 agents DashMap slot，但 poller 解析 Python JSON 時是否已 populate `agent_states` bucket 的解析路徑需 grep 確認。如 Phase 1A poller stub 不解 agent_states → Phase 4 必先 land 該解析（建議先放 sub-task 4-0 或併入 4-1，由 E1 grep poller code 後決定）。

### 4.3 Shard hash 分布驗證

DashMap 預設 shard count = `cpus * 4`；5 H + 5 agent = 10 key 分布到 ≥16 shard 上。**碰撞風險可忽略**（per Phase 1A 文檔同 reasoning）。

### 4.4 Staleness threshold per-agent

**建議延用 30s 統一 threshold**（per Phase 1A healthcheck [20] 設計）。

理由：
- 5 agent 真實 emit 頻率最低為 Scout（`scans_completed` 每 30 min 一次）— 但 invalidate hint 在 emit 時推，不依賴頻率
- 30s pull cycle + 即時 invalidate hint = 偶發 ≤30s 延遲可接受
- 統一 threshold 簡化 healthcheck logic（10 bucket 同公式）

**未來細化空間**：Phase 5+ 如某 agent 觀察到誤報，可加 per-agent override（YAGNI 暫不做）。

---

## §5 Sub-task split pattern (per-agent)

### 5.1 5 sub-task 拆分（per Phase 3 Pattern B 鏡射）

| Sub-task | Agent | 主檔 | 主檔 LOC（split 後）| 預估增量 LOC | 依賴 | 並行性 |
|---|---|---|---|---|---|---|
| **4-1** | Strategist | `strategist_agent.py` (split 後) | ~710 → ~770 | +30 (snapshot) +30 (2 hooks + import) = **+60** | **STRATEGIST-SPLIT 必先 land** | 與 4-2/4-3/4-4/4-5 並行（不同檔） |
| **4-2** | Guardian | `guardian_agent.py` | 587 → ~620 | +25 (snapshot) +10 (2 hooks + import) = **+35** | Phase 3 ✅ | 與 4-1/4-3/4-4/4-5 並行 |
| **4-3** | Analyst | `analyst_agent.py` | 834 → ~860 | +20 (snapshot) +6 (1 hook + import) = **+26** | Phase 3 ✅ | 與 4-1/4-2/4-4/4-5 並行 |
| **4-4** | Executor | `executor_agent.py` | 669 → ~705 | +28 (snapshot) +8 (2 hooks + import) = **+36** | Phase 3 ✅ + G3-03 ConfigStore（已 land） | 與 4-1/4-2/4-3/4-5 並行 |
| **4-5** | Scout | `multi_agent_framework.py` | 1137 → ~1165 | +18 (snapshot) +9 (3 hooks + import) = **+27** | Phase 3 ✅ | 與 4-1/4-2/4-3/4-4 並行 |

**主檔 LOC 安全性檢查**：
- Strategist split 後 ~710 LOC + 60 = **~770 < §七 800 警告線** ✅（pre-Phase-4 split RFC §4.2 已預留 ~90 LOC headroom for Phase 4）
- Guardian 587 + 35 = **622 < 800** ✅
- Analyst 834 + 26 = **860 ⚠️ 已過 800**（pre-Phase-4 即 834 = 已過警告線）
- Executor 669 + 36 = **705 < 800** ✅
- multi_agent_framework.py 1137 + 27 = **1164 < §九 1200** ✅（接近，Phase 5 注意）

**Analyst 已過警告線警告**：834 LOC 已過 §七 800，Phase 4 Sub-task 4-3 land 後達 ~860。**不阻塞 Phase 4 進行**（§七 警告線 800 不是 hard cap），但**新增 Backlog 項 G3-08-FUP-ANALYST-SPLIT**（建議下一輪 Wave 完成 Analyst 拆檔，per Phase 4 split RFC §1.4 同模式 — 目標主檔 ~480 LOC）。

**multi_agent_framework.py 1164 警告**：距 §九 1200 hard cap 僅 36 LOC headroom。Phase 5 加任何字段 = 觸 §九。**Backlog 項 G3-08-FUP-MAF-SPLIT**：把 ScoutAgent (~183 LOC) 拆出獨立 `scout_agent.py` 檔（沿襲 Strategist sibling pattern）。可同 Sub-task 4-5 順道拆，或獨立 Backlog（推薦獨立 Backlog 避擴大 4-5 範圍）。

### 5.2 撞檔風險矩陣（5 sub-task vs h_state_query_handler.py 共用）

| Sub-task pair | 共享文件 | 並行可行 | 緩解 |
|---|---|---|---|
| 4-1 ↔ 4-2/3/4/5 | `h_state_query_handler.py`（每 sub-task 加 1 bucket key） | ✅ Yes | 加 `"<agent>"` key 為加性 dict 操作；後 commit `git pull --rebase` 自動 merge |
| 4-1 主檔 vs 其他 4-N | 不同檔（strategist_agent.py vs guardian_agent.py / analyst_agent.py / executor_agent.py / multi_agent_framework.py） | ✅ Yes | 完全獨立 |
| 4-1 ↔ STRATEGIST-SPLIT | strategist_agent.py | ❌ Hard pre-condition | 4-1 必等 SPLIT commit hash land 後 dispatch |
| 4-5 ↔ G3-08-FUP-MAF-SPLIT | multi_agent_framework.py | ❌ Hard pre-condition（如 SPLIT 也排在 Phase 4 wave）| 推薦 G3-08-FUP-MAF-SPLIT 排 backlog **下一 wave** 而非 Phase 4 wave，避 4-5 阻塞 |
| `_collect_agent_snapshots` 新增 | h_state_query_handler.py | ⚠️ 多 sub-task 同改 | **約定**：每 sub-task 都加自己的 dispatch arm（加 `if include_<agent>:` 區塊），後 commit `git pull --rebase` 自動合併 dict 加項 |

**派發 multi-track absorb pattern（per Phase 3 Sub-task 3-1 commit `8cd257e` 經驗）**：Sub-task 4-1 落主樹 → 主 PM commit 後 push → Sub-task 4-2/3/4/5 同步 fetch → 4 個 E1 並行 worktree（**isolation**）— 然後 PM 序貫 merge 4 個 sub-task commit。

**4 sub-task 並行 isolation 需求**：
- 4-2 / 4-3 / 4-4：**主樹 OK**（不同主檔，h_state_query_handler.py 共改但加性 dict 不衝突）
- 4-5：**主樹 OK**（multi_agent_framework.py 改動局限 ScoutAgent class）
- 4-1：**worktree isolation**（主檔 Strategist split 剛 land，high-churn 時段，避免 race）

### 5.3 Multi-track absorb pattern（Phase 3 commit 8cd257e 經驗）

per Phase 3 Sub-task 3-1 commit `8cd257e` 觀察：當主 PM session 同 wave 派 2+ E1 並行改 h_state_query_handler.py 時，**absorb pattern** = PM 序貫 merge：

1. E1-Alpha (4-1) 完成 → push → PM merge
2. E1-Beta (4-2) 完成 → fetch → rebase → push → PM merge
3. E1-Gamma (4-3) 同上
4. E1-Delta (4-4) 同上
5. E1-Epsilon (4-5) 同上

合併衝突風險低（每 sub-task 加自己的 if 區塊到 `_collect_agent_snapshots` 不同位置；dict literal 後 commit 自動合）。

### 5.4 工時預估（Phase 4 全鏈）

| Phase | E1 wall-clock | E2 review | E4 regression | 全鏈 |
|---|---|---|---|---|
| **Sub-task 4-1 Strategist** | 1d（含 split commit 等待）| 0.5d | 0.5d | 2d 順序 |
| **Sub-task 4-2/3/4/5 並行** | 0.75d × 4 並行 = 0.75d | 0.5d（4 commit 集中 review） | 0.5d（合 regression） | 1.75d |
| Total Phase 4 | — | — | — | **~3.75d ≤ PA design §11.1 估 4d** ✅ |

**比較串行**：5 × 1.5d = 7.5d。並行省 ~3.75d。

---

## §6 Self-contained E1 prompt template × 5

每個 prompt PM 下次 wave 0 額外 context 即可派發（per PM Tier 8 sign-off `e5f1b2d` 約定）。

### 6.1 Sub-task 4-1 Strategist E1 prompt template

````markdown
═══════════════════════════════════════════════════════════════════════════════
@E1 G3-08-PHASE-4-1-STRATEGIST — Strategist agent_state event integration
═══════════════════════════════════════════════════════════════════════════════

## 背景
G3-08 Phase 4 拆 5 sub-task（每 agent 1 個）。本 sub-task = Strategist agent state
接線到 Rust h_state_cache gateway。Pattern 鏡 Phase 3 commit `8cd257e`（H2 Sub-task 3-1）。

## 前置驗證（開工前必跑，缺一即 STOP）

```bash
# (a) STRATEGIST-SPLIT 必先 land
git log --oneline -10 | grep -iE "G3-08-PHASE-4-STRATEGIST-SPLIT" || \
  echo "STOP: Strategist split not landed - this sub-task hard depends on it"

# (b) Phase 3 H 5-bucket 仍綠
ssh trade-core "cd ~/BybitOpenClaw/srv && python3 helper_scripts/db/passive_wait_healthcheck.py 2>&1 | grep -i '\[20\]'"

# (c) cargo test agent slot ready
ssh trade-core "cd ~/BybitOpenClaw/srv/rust && grep -A 6 'pub struct AgentState' \
  rust/openclaw_engine/src/h_state_cache/types.rs"
```

三條全綠 → 開工。

## 必讀
1. PA design RFC: docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g3_08_phase4_5agent_design_rfc.md
   - §2.1 Strategist snapshot schema（11 fields）
   - §3.5 Hook 接線點
   - §6.1 本 prompt
2. Phase 3 reference commit `8cd257e`（H2 Sub-task 3-1）— pattern 模板
3. Phase 4 split RFC §4.2: docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--g3_08_phase4_split_plan.md
   - 確認 strategist_agent.py 主檔 ~710 LOC（split 後）+ 預留 90 LOC headroom

## 改動文件
1. `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategist_agent.py`
   - 新增 method `get_strategist_snapshot()` (~30 LOC)
   - `_handle_intel()` 結尾加 `_invalidate_h_state_async("agent.strategist.intel_handled")`
   - `_produce_intents()` 結尾加 `_invalidate_h_state_async("agent.strategist.intent_produced")`
   - 確認 import 已有 `from .h_state_invalidator import invalidate_async as _invalidate_h_state_async`（Phase 3 Sub-task 3-2 已加，本 sub-task 不重加）

2. `program_code/exchange_connectors/bybit_connector/control_api_v1/app/h_state_query_handler.py`
   - 新增 fn `_collect_agent_snapshots(...)` （per RFC §3.2 Option B）
   - `build_h_state_full_response` 加 5 個 include flag + `agent_states` bucket population
   - 本 sub-task **只填 strategist key**，其他 4 agent 留 `None`，4-2~5 sub-task 接續填

3. Tests:
   - `tests/test_strategist_agent.py` 加 H4-pattern Strategist snapshot test
   - `tests/test_h_state_query_handler.py` 加 strategist agent_state round-trip test

## 具體實作

### strategist_agent.py 加 method

```python
# G3-08 Phase 4 Sub-task 4-1: Strategist agent state snapshot accessor
# G3-08 Phase 4 Sub-task 4-1：Strategist agent 狀態 snapshot 存取器

def get_strategist_snapshot(self) -> Dict[str, Any]:
    """Return a thread-safe agent-state snapshot for h_state_cache exposure.
    回傳 Strategist agent 狀態的線程安全 snapshot，供 h_state_cache 暴露使用。

    Schema (PA RFC §2.1, 11 fields, Rust AgentState.stats parity):
      - intel_received / intel_evaluated / intents_produced / intents_shadow_logged
      - evaluations_rejected / ai_evaluations / heuristic_evaluations / errors
      - pending_intents (gauge) / emergency_mode_active (bool→int 0/1)
      - cognitive_modulator_connected (bool→int 0/1)

    Pure-read, only acquires self._lock. Phase 4 invariant: all fields are
    int or bool→int (no float / string). cognitive/emergency bool cast to
    int for Rust HashMap<String, i64> 容忍.
    純讀取，只取 self._lock。Phase 4 不變式：所有欄位皆 int 或 bool→int
    （無 float / string）。bool 轉 int 以對齊 Rust HashMap<String, i64>。
    """
    with self._lock:
        return {
            "intel_received": int(self._stats.get("intel_received", 0)),
            "intel_evaluated": int(self._stats.get("intel_evaluated", 0)),
            "intents_produced": int(self._stats.get("intents_produced", 0)),
            "intents_shadow_logged": int(self._stats.get("intents_shadow_logged", 0)),
            "evaluations_rejected": int(self._stats.get("evaluations_rejected", 0)),
            "ai_evaluations": int(self._stats.get("ai_evaluations", 0)),
            "heuristic_evaluations": int(self._stats.get("heuristic_evaluations", 0)),
            "errors": int(self._stats.get("errors", 0)),
            "pending_intents": int(len(self._pending_intents)),
            "emergency_mode_active": int(bool(self._emergency_mode.is_set())),
            "cognitive_modulator_connected": int(self._cognitive_modulator is not None),
        }
```

### invalidate hook 接線

```python
# In _handle_intel(), 末尾（既有 line ~430 self._stats["intel_evaluated"] += 1 之後）:
_invalidate_h_state_async("agent.strategist.intel_handled")

# In _produce_intents(), 末尾（既有 line ~534 self._stats["intents_produced"] += 1 之後）:
_invalidate_h_state_async("agent.strategist.intent_produced")
```

### h_state_query_handler.py 升級

加新 fn `_collect_agent_snapshots`（per RFC §3.2 Option B）；本 sub-task 只填 strategist：

```python
def _collect_agent_snapshots(
    include_strategist: bool = False,
    include_guardian: bool = False,
    include_analyst: bool = False,
    include_executor: bool = False,
    include_scout: bool = False,
) -> dict[str, Optional[dict[str, Any]]]:
    """Lazy-import strategy_wiring and pull 5-Agent state snapshots.
    延遲 import strategy_wiring 並拉取 5-Agent 狀態 snapshot。

    Phase 4 Sub-task 4-1 lands strategist; 4-2/3/4/5 land subsequent
    agent buckets. Pattern: per-agent grow returns dict (not tuple) so
    later sub-tasks add keys without breaking caller.
    """
    result: dict[str, Optional[dict[str, Any]]] = {
        "strategist": None,
        "guardian": None,
        "analyst": None,
        "executor": None,
        "scout": None,
    }

    if not (include_strategist or include_guardian or include_analyst
            or include_executor or include_scout):
        return result

    try:
        from . import strategy_wiring as _sw
    except Exception:
        return result

    if include_strategist:
        result["strategist"] = _safe_snapshot_self(
            getattr(_sw, "STRATEGIST_AGENT", None),
            "get_strategist_snapshot",
        ) if getattr(_sw, "STRATEGIST_AGENT", None) is not None else None

    # (Sub-task 4-2/3/4/5 future: include_guardian / include_analyst / ...)
    return result
```

並升級 `build_h_state_full_response` 加 5 個 include flag + agent_states 填充（per RFC §3.3）。

## 完成標準

- ✅ pytest +N（Strategist snapshot test + agent_states round-trip test）
- ✅ env=1 + IPC `query_h_state_full` 回 `agent_states["strategist"]` 含 11 fields
- ✅ env=0 zero overhead（grep `_invalidate_h_state_async("agent.strategist.…")` 全 env-gated）
- ✅ healthcheck [20] 仍綠（staleness < 30s）
- ✅ ssh trade-core cargo test 仍綠（無 Rust 改動）
- ✅ STRATEGIST-SPLIT 預留 90 LOC headroom 已用 ~60，餘 ~30 給未來 Phase 5（如 Conductor snapshot）

## Commit message

```
feat(strategist): G3-08 Phase 4 Sub-task 4-1 — Strategist agent_state events

- strategist_agent.py:
  - new method get_strategist_snapshot() returns 11-field dict per PA RFC §2.1
  - _handle_intel() now invokes _invalidate_h_state_async("agent.strategist.intel_handled")
  - _produce_intents() now invokes _invalidate_h_state_async("agent.strategist.intent_produced")
  - bool fields cast to int for Rust HashMap<String, i64> parity

- h_state_query_handler.py: aggregate Strategist agent_state alongside Phase 3 H bucket
  - new _collect_agent_snapshots() per RFC §3.2 Option B (returns dict)
  - build_h_state_full_response gains 5 include flags + agent_states population
  - Sub-task 4-1 fills "strategist" key; "guardian"/"analyst"/"executor"/"scout"
    remain None until 4-2/3/4/5 land

- tests: +N Strategist snapshot test + agent_states round-trip test

Phase 4 Sub-task 4-1 of 5; 4-2/3/4/5 follow in parallel. Per PA RFC
docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g3_08_phase4_5agent_design_rfc.md
- Pattern B (per-agent module) chosen, mirrors Phase 3 Pattern B (per-H module)
- Strategist split (G3-08-PHASE-4-STRATEGIST-SPLIT commit <hash>) hard pre-cond verified

Verified: cargo test pass; pytest pass; env=1 IPC agent_states.strategist populated;
env=0 zero overhead; healthcheck [20] green.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Estimated time
- 樂觀 0.75d / 中位 1d / 悲觀 1.5d
- 與 4-2/3/4/5 並行（不同 agent 主檔）
- **Hard pre-condition**：STRATEGIST-SPLIT commit 必先 land（PM 在 Phase 4 wave 開工前 grep 驗證）

## High-risk warnings
1. Hook 加在 `_handle_intel`/`_produce_intents` 結尾不是中段（中段加會 race condition with `with self._lock` block）
2. STRATEGIST-SPLIT 後 method 可能在 sibling 不在主類別 — 必驗 `get_strategist_snapshot` 落主檔 `StrategistAgent` class（不在 strategist_edge_eval / weights / cognitive sibling）
3. 11 fields 是 hot-path 觀測 ceiling — 加新字段必先 RFC + Rust HashMap parity check

## 一行回報
```
SUB-TASK 4-1 DONE — Strategist agent_state commit <hash> pushed; pytest +N green; IPC strategist 11 fields OK
```
````

### 6.2 Sub-task 4-2 Guardian E1 prompt template

````markdown
═══════════════════════════════════════════════════════════════════════════════
@E1 G3-08-PHASE-4-2-GUARDIAN — Guardian agent_state event integration
═══════════════════════════════════════════════════════════════════════════════

## 背景
Phase 4 Sub-task 2 of 5。鏡 Sub-task 4-1 pattern but 對 GuardianAgent。可與 4-1/3/4/5 並行
（不同主檔 guardian_agent.py，h_state_query_handler.py 共改但加性 dict）。

## 前置驗證（開工前必跑）

```bash
# (a) Sub-task 4-1 已 land（避 _collect_agent_snapshots dict shape 衝突）
git log --oneline -10 | grep -iE "G3-08-PHASE-4-1-STRATEGIST" || \
  echo "STOP: Sub-task 4-1 not landed - this sub-task depends on _collect_agent_snapshots dict skeleton"

# (b) Phase 3 H 5-bucket 仍綠
ssh trade-core "cd ~/BybitOpenClaw/srv && python3 helper_scripts/db/passive_wait_healthcheck.py 2>&1 | grep -i '\[20\]'"
```

## 必讀
1. PA RFC `2026-04-27--g3_08_phase4_5agent_design_rfc.md` §2.2 Guardian schema + §3.5 + §6.2

## 改動文件
1. `app/guardian_agent.py`
   - 加 method `get_guardian_snapshot()` (~25 LOC，8 fields per RFC §2.2)
   - `_handle_trade_intent` 結尾加 `_invalidate_h_state_async("agent.guardian.intent_reviewed")`
   - `_handle_event_alert` 結尾加 `_invalidate_h_state_async("agent.guardian.event_assessed")`
   - 新 import：`from .h_state_invalidator import invalidate_async as _invalidate_h_state_async`

2. `app/h_state_query_handler.py`
   - `_collect_agent_snapshots` 加 `include_guardian` arm：
     ```python
     if include_guardian:
         result["guardian"] = _safe_snapshot_self(
             getattr(_sw, "GUARDIAN_AGENT", None),
             "get_guardian_snapshot",
         ) if getattr(_sw, "GUARDIAN_AGENT", None) is not None else None
     ```

3. Tests: +N Guardian snapshot test + agent_states.guardian round-trip

## 具體實作（snapshot method）

```python
def get_guardian_snapshot(self) -> Dict[str, Any]:
    """Guardian agent-state snapshot for h_state_cache.
    Schema (PA RFC §2.2, 8 fields):
      intents_reviewed / verdicts_approved / verdicts_rejected / verdicts_modified
      events_assessed / errors / active_event_risks / verdict_log_size
    """
    with self._lock:
        return {
            "intents_reviewed": int(self._stats.get("intents_reviewed", 0)),
            "verdicts_approved": int(self._stats.get("verdicts_approved", 0)),
            "verdicts_rejected": int(self._stats.get("verdicts_rejected", 0)),
            "verdicts_modified": int(self._stats.get("verdicts_modified", 0)),
            "events_assessed": int(self._stats.get("events_assessed", 0)),
            "errors": int(self._stats.get("errors", 0)),
            "active_event_risks": int(len(self._active_event_risks)),
            "verdict_log_size": int(len(self._verdict_log)),
        }
```

## 完成標準
- pytest +N
- env=1 IPC `agent_states["guardian"]` 含 8 fields
- env=0 zero overhead
- healthcheck [20] 仍綠

## Commit message
```
feat(guardian): G3-08 Phase 4 Sub-task 4-2 — Guardian agent_state events

- guardian_agent.py: new get_guardian_snapshot() + 2 invalidate hooks
- h_state_query_handler.py: include_guardian arm in _collect_agent_snapshots
- tests: +N Guardian round-trip

Phase 4 Sub-task 4-2 of 5. Per PA RFC §2.2.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Estimated time
- 樂觀 0.5d / 中位 0.75d / 悲觀 1d

## High-risk warnings
1. Guardian 主檔 587 LOC + ~35 = ~622，仍 < §七 800 ✅
2. `verdict_log_size` 是 gauge（list len），int cast 必加（Phase 4 invariant）
3. 確認 `strategy_wiring.GUARDIAN_AGENT` 存在（grep 驗證；如無，回報 PM 改為延遲 lazy lookup）

## 一行回報
```
SUB-TASK 4-2 DONE — Guardian agent_state commit <hash> pushed; pytest +N green
```
````

### 6.3 Sub-task 4-3 Analyst E1 prompt template

````markdown
═══════════════════════════════════════════════════════════════════════════════
@E1 G3-08-PHASE-4-3-ANALYST — Analyst agent_state event integration
═══════════════════════════════════════════════════════════════════════════════

## 背景
Phase 4 Sub-task 3 of 5。鏡 Sub-task 4-1 pattern。**警告**：Analyst 主檔 834 LOC（pre-Phase-4
即超 §七 800 警告線）；本 sub-task land 後 ~860。**不阻塞** Phase 4，但 Backlog 項
G3-08-FUP-ANALYST-SPLIT 必排（per RFC §5.1）。

## 前置驗證（開工前必跑）

```bash
# (a) Sub-task 4-1 已 land
git log --oneline -10 | grep -iE "G3-08-PHASE-4-1-STRATEGIST" || \
  echo "STOP: Sub-task 4-1 not landed"

# (b) Analyst 主檔 LOC 採集
wc -l srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/analyst_agent.py
# 預期 834；±10 接受，>=850 必告 PM

# (c) Phase 3 healthcheck [20] 仍綠
ssh trade-core "cd ~/BybitOpenClaw/srv && python3 helper_scripts/db/passive_wait_healthcheck.py 2>&1 | grep -i '\[20\]'"
```

## 必讀
1. PA RFC `2026-04-27--g3_08_phase4_5agent_design_rfc.md` §2.3 Analyst schema + §6.3

## 改動文件
1. `app/analyst_agent.py`
   - 加 method `get_analyst_snapshot()` (~20 LOC，5 fields)
   - `_handle_round_trip` 結尾加 `_invalidate_h_state_async("agent.analyst.round_trip_analyzed")`
   - 新 import：`from .h_state_invalidator import invalidate_async as _invalidate_h_state_async`

2. `app/h_state_query_handler.py`
   - `_collect_agent_snapshots` 加 `include_analyst` arm

3. Tests: +N Analyst snapshot test + agent_states.analyst round-trip

## 具體實作（snapshot method）

```python
def get_analyst_snapshot(self) -> Dict[str, Any]:
    """Analyst agent-state snapshot for h_state_cache.
    Schema (PA RFC §2.3, 5 fields):
      trades_analyzed / l1_updates / l2_analyses / errors
      experiment_ledger_connected (bool→int)
    """
    with self._lock:
        return {
            "trades_analyzed": int(self._stats.get("trades_analyzed", 0)),
            "l1_updates": int(self._stats.get("l1_updates", 0)),
            "l2_analyses": int(self._stats.get("l2_analyses", 0)),
            "errors": int(self._stats.get("errors", 0)),
            "experiment_ledger_connected": int(self._experiment_ledger is not None),
        }
```

## 完成標準
- pytest +N
- env=1 IPC `agent_states["analyst"]` 含 5 fields
- env=0 zero overhead
- healthcheck [20] 仍綠
- 提報 G3-08-FUP-ANALYST-SPLIT Backlog 條目給 PM（per RFC §5.1）

## Commit message
```
feat(analyst): G3-08 Phase 4 Sub-task 4-3 — Analyst agent_state events

- analyst_agent.py: new get_analyst_snapshot() + 1 invalidate hook
- h_state_query_handler.py: include_analyst arm in _collect_agent_snapshots
- tests: +N Analyst round-trip

NOTE: analyst_agent.py post-this-commit ~860 LOC (pre-Phase-4 already 834,
exceeded §七 800 warn line). Backlog item G3-08-FUP-ANALYST-SPLIT to be
filed for next-wave refactor (per PA RFC §5.1).

Phase 4 Sub-task 4-3 of 5. Per PA RFC §2.3.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Estimated time
- 樂觀 0.5d / 中位 0.75d / 悲觀 1d

## High-risk warnings
1. **§七 警告線溢出**：land 後主檔 ~860，超 800 警告線（pre-Phase-4 即 834 已超）。FA must file Backlog G3-08-FUP-ANALYST-SPLIT.
2. AnalystAgent.experiment_ledger 是 Optional 注入；snapshot bool 為「是否注入」非「是否健康」（避免誤導）
3. 確認 `strategy_wiring.ANALYST_AGENT` 存在（grep 驗）

## 一行回報
```
SUB-TASK 4-3 DONE — Analyst agent_state commit <hash> pushed; pytest +N green; FUP-ANALYST-SPLIT filed
```
````

### 6.4 Sub-task 4-4 Executor E1 prompt template

````markdown
═══════════════════════════════════════════════════════════════════════════════
@E1 G3-08-PHASE-4-4-EXECUTOR — Executor agent_state event integration
═══════════════════════════════════════════════════════════════════════════════

## 背景
Phase 4 Sub-task 4 of 5。鏡 Sub-task 4-1 pattern。**特別注意**：Executor 已有
G3-03 ConfigStore (`shadow_mode_provider()` lambda) 接 Rust ConfigStore.executor 的
shadow_mode。本 sub-task 把 `_shadow_mode_provider()` 的當前值納入 snapshot
（**snapshot vs ConfigStore cache 區分** — RFC §2.4 special note）。

## 前置驗證（開工前必跑）

```bash
# (a) Sub-task 4-1 已 land
git log --oneline -10 | grep -iE "G3-08-PHASE-4-1-STRATEGIST" || \
  echo "STOP: Sub-task 4-1 not landed"

# (b) G3-03 ExecutorConfigCache live
ssh trade-core "cd ~/BybitOpenClaw/srv && grep -n '_shadow_mode_provider' \
  program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_agent.py"
# 預期 line 180 有 self._shadow_mode_provider 設置；line 543 _shadow_mode_provider() call

# (c) Phase 3 healthcheck [20] 仍綠
ssh trade-core "cd ~/BybitOpenClaw/srv && python3 helper_scripts/db/passive_wait_healthcheck.py 2>&1 | grep -i '\[20\]'"
```

## 必讀
1. PA RFC `2026-04-27--g3_08_phase4_5agent_design_rfc.md` §2.4 Executor schema + §6.4
2. G3-03 Phase B ExecutorConfigCache: `app/executor_config_cache.py` + `executor_agent.py:140-181`

## 改動文件
1. `app/executor_agent.py`
   - 加 method `get_executor_snapshot()` (~28 LOC，9 fields per RFC §2.4)
   - `_handle_approved_intent` 兩個結束分支（success / failed）各加：
     - success path: `_invalidate_h_state_async("agent.executor.execution_complete")`
     - failed path: `_invalidate_h_state_async("agent.executor.execution_failed")`
   - 新 import：`from .h_state_invalidator import invalidate_async as _invalidate_h_state_async`

2. `app/h_state_query_handler.py`
   - `_collect_agent_snapshots` 加 `include_executor` arm

3. Tests: +N Executor snapshot test（覆蓋 shadow_mode True/False 兩條 case）+ agent_states.executor round-trip

## 具體實作（snapshot method）

```python
def get_executor_snapshot(self) -> Dict[str, Any]:
    """Executor agent-state snapshot for h_state_cache.
    Schema (PA RFC §2.4, 9 fields):
      intents_received / intents_deduped / executions_attempted / executions_success
      executions_failed / total_slippage_bps (cast int) / errors
      recent_intent_id_size / shadow_mode (bool→int via _shadow_mode_provider)

    NOTE: shadow_mode pulled via self._shadow_mode_provider() (G3-03 ConfigStore
    lambda), distinct from snapshot itself. Snapshot reflects RUNTIME shadow
    decision; ConfigStore is the SOURCE of TRUTH. Same cycle reads ensure
    synchronization (no skew within snapshot).
    註：shadow_mode 透過 self._shadow_mode_provider()（G3-03 ConfigStore lambda）
    取，與 snapshot 本身分離。Snapshot 反映 RUNTIME shadow 決定；ConfigStore 為
    SSOT。同一 snapshot cycle 讀取確保不會 skew。
    """
    with self._lock:
        snapshot = {
            "intents_received": int(self._stats.get("intents_received", 0)),
            "intents_deduped": int(self._stats.get("intents_deduped", 0)),
            "executions_attempted": int(self._stats.get("executions_attempted", 0)),
            "executions_success": int(self._stats.get("executions_success", 0)),
            "executions_failed": int(self._stats.get("executions_failed", 0)),
            "total_slippage_bps": int(self._stats.get("total_slippage_bps", 0.0)),
            "errors": int(self._stats.get("errors", 0)),
            "recent_intent_id_size": int(len(self._recent_intent_ids)),
        }
    # shadow_mode_provider call OUTSIDE self._lock to avoid deadlock with
    # ExecutorConfigCache singleton lock (defensive — provider 應為 lock-free
    # snapshot 但避同 lock 風險)
    try:
        snapshot["shadow_mode"] = int(bool(self._shadow_mode_provider()))
    except Exception:
        snapshot["shadow_mode"] = 1  # fail-closed: assume shadow on provider error
    return snapshot
```

## 完成標準
- pytest +N（含 shadow_mode True/False 兩條 case + provider raises 例外回 1 fail-closed test）
- env=1 IPC `agent_states["executor"]` 含 9 fields
- env=0 zero overhead
- healthcheck [20] 仍綠

## Commit message
```
feat(executor): G3-08 Phase 4 Sub-task 4-4 — Executor agent_state events

- executor_agent.py: new get_executor_snapshot() + 2 invalidate hooks
  (success / failed branches)
- shadow_mode pulled via _shadow_mode_provider() (G3-03 ConfigStore lambda),
  fail-closed default 1 on provider error (CLAUDE.md §二 原則 #6)
- h_state_query_handler.py: include_executor arm
- tests: +N Executor round-trip including shadow_mode True/False/provider-raises

Phase 4 Sub-task 4-4 of 5. Per PA RFC §2.4.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Estimated time
- 樂觀 0.5d / 中位 0.75d / 悲觀 1d

## High-risk warnings
1. `_shadow_mode_provider()` call **必在 self._lock 之外**（避 G3-03 ExecutorConfigCache 內部 lock + self._lock 死鎖）
2. provider raise 必 fail-closed 為 1（shadow 開啟 = 安全姿態，CLAUDE.md §二 原則 #6）
3. `total_slippage_bps` 在 `_stats` 是 float（line 205）；snapshot int cast 必加（Phase 4 invariant）
4. snapshot vs ConfigStore SSOT 區分必寫進 docstring（避免未來開發混淆 cache vs state）

## 一行回報
```
SUB-TASK 4-4 DONE — Executor agent_state commit <hash> pushed; pytest +N green; shadow_mode wire validated
```
````

### 6.5 Sub-task 4-5 Scout E1 prompt template

````markdown
═══════════════════════════════════════════════════════════════════════════════
@E1 G3-08-PHASE-4-5-SCOUT — Scout agent_state event integration
═══════════════════════════════════════════════════════════════════════════════

## 背景
Phase 4 Sub-task 5 of 5（最後一個）。鏡 Sub-task 4-1 pattern but **特別**：ScoutAgent class
不在獨立 `scout_agent.py` 而在 `multi_agent_framework.py`（L379-561 ~183 LOC）。
multi_agent_framework.py 1137 LOC + ~27 = ~1164 距 §九 1200 hard cap 36 LOC headroom。

## 前置驗證（開工前必跑）

```bash
# (a) Sub-task 4-1 已 land
git log --oneline -10 | grep -iE "G3-08-PHASE-4-1-STRATEGIST" || \
  echo "STOP: Sub-task 4-1 not landed"

# (b) ScoutAgent 位置確認
grep -n "class ScoutAgent" srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/multi_agent_framework.py
# 預期 line 379 命中

# (c) multi_agent_framework.py LOC headroom
wc -l srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/multi_agent_framework.py
# 預期 1137；>=1170 必告 PM（接近 §九 1200）

# (d) strategy_wiring SCOUT_AGENT 確認
grep -n "SCOUT_AGENT\|_SCOUT_AGENT" srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_wiring.py
# 必驗 module-level singleton 名稱（如非 SCOUT_AGENT，回報 PM 調整 prompt）

# (e) Phase 3 healthcheck [20] 仍綠
ssh trade-core "cd ~/BybitOpenClaw/srv && python3 helper_scripts/db/passive_wait_healthcheck.py 2>&1 | grep -i '\[20\]'"
```

## 必讀
1. PA RFC `2026-04-27--g3_08_phase4_5agent_design_rfc.md` §2.5 Scout schema + §6.5

## 改動文件
1. `app/multi_agent_framework.py`（ScoutAgent class L379-561 內部）
   - 加 method `get_scout_snapshot()` (~18 LOC，5 fields per RFC §2.5)
   - `produce_intel()` 結尾加 `_invalidate_h_state_async("agent.scout.intel_produced")`
   - `produce_alert()` 結尾加 `_invalidate_h_state_async("agent.scout.alert_produced")`
   - `_complete_scan()` 結尾加 `_invalidate_h_state_async("agent.scout.scan_completed")`
   - 文件頂部加 import：`from .h_state_invalidator import invalidate_async as _invalidate_h_state_async`（如已有 4-2/3/4 同檔不重加；此檔只 ScoutAgent 用）

2. `app/h_state_query_handler.py`
   - `_collect_agent_snapshots` 加 `include_scout` arm
   - **此 sub-task 完成 = `_collect_agent_snapshots` 5 個 agent 全 wired**

3. Tests: +N Scout snapshot test + agent_states.scout round-trip + **5-bucket regression test**（agent_states 全 5 個 + h_states 全 5 個 = 10 bucket 同框）

## 具體實作（snapshot method）

```python
def get_scout_snapshot(self) -> Dict[str, Any]:
    """Scout agent-state snapshot for h_state_cache.
    Schema (PA RFC §2.5, 5 fields):
      intel_produced / alerts_produced / scans_completed
      intel_log_size / alert_log_size (gauges)
    """
    with self._lock:
        return {
            "intel_produced": int(self._stats.get("intel_produced", 0)),
            "alerts_produced": int(self._stats.get("alerts_produced", 0)),
            "scans_completed": int(self._stats.get("scans_completed", 0)),
            "intel_log_size": int(len(self._intel_log)),
            "alert_log_size": int(len(self._alert_log)),
        }
```

## 完成標準
- pytest +N（Scout snapshot test + 10-bucket round-trip regression test）
- env=1 IPC 回 5 H bucket + 5 agent bucket 同框（10/10 fields populated）
- env=0 zero overhead
- healthcheck [20] 仍綠
- **Phase 4 完成標誌**：env=1 + IPC `query_h_state_full` 含 `h_states` (5) + `agent_states` (5)
- 提報 G3-08-FUP-MAF-SPLIT Backlog（建議 ScoutAgent 拆出獨立 scout_agent.py，per RFC §5.1）

## Commit message
```
feat(scout): G3-08 Phase 4 Sub-task 4-5 — Scout agent_state events (Phase 4 complete)

- multi_agent_framework.py (ScoutAgent class):
  - new get_scout_snapshot() returns 5-field dict
  - 3 invalidate hooks (produce_intel / produce_alert / _complete_scan)
- h_state_query_handler.py: include_scout arm — 5-bucket agent_states complete
  - env=1 IPC query_h_state_full now returns full 10-bucket envelope
    (5 H bucket + 5 agent bucket)
- tests: +N Scout round-trip + 10-bucket regression test

Phase 4 final sub-task. Per PA RFC §2.5.

NOTE: multi_agent_framework.py post-this-commit ~1164 LOC (pre-Phase-4
1137; Sub-task 4-5 +27). Backlog G3-08-FUP-MAF-SPLIT proposes splitting
ScoutAgent (~183 LOC) into standalone scout_agent.py for §九 1200 hard
cap headroom.

Phase 4 unblock paths NOW LIVE:
- G8-01 認知自適應 e2e 測試: Rust fixture can read 5-Agent observability
- G3-09 cost_edge_advisor: cross-agent stats correlation (Strategist
  ai_evaluations + Analyst l2_analyses + cost_edge_ratio)

Verified: pytest pass; env=1 IPC 10-bucket envelope; env=0 zero overhead;
healthcheck [20] green.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Estimated time
- 樂觀 0.5d / 中位 0.75d / 悲觀 1d

## High-risk warnings
1. **§九 1200 hard cap 接近**：multi_agent_framework.py post 1164/1200 = 36 LOC headroom；任何 Phase 5 加 LOC 即觸 §九 violation。Backlog G3-08-FUP-MAF-SPLIT 必排
2. ScoutAgent class 是 multi_agent_framework.py 內 class（不是獨立檔）；snapshot method 必加在 class 內部（line 379-561 範圍內）
3. **`_complete_scan` 函式名 grep 確認**：可能其他內部 helper 名稱；如 `_complete_scan` 不存在則用 `complete_scan` 或對應名稱，回報 PM 調 prompt

## 一行回報
```
SUB-TASK 4-5 DONE — Scout agent_state commit <hash> pushed; Phase 4 10-bucket envelope live; G8-01/G3-09 unblocked
```
````

---

## §7 healthcheck [20] h_state_gateway_freshness 升級

### 7.1 expected set 升級

`passive_wait_healthcheck.py` `[20]` Phase 1C 已加（基於 `get_h_state_status` IPC）。Phase 4 完成後升級判斷：

```python
def check_h_state_5bucket_parity() -> tuple[str, str]:
    """[Xa] H State Gateway 10-bucket parity (Phase 4 complete)"""
    if os.environ.get("OPENCLAW_H_STATE_GATEWAY") != "1":
        return "PASS", "gateway disabled"
    snap = ipc_call("query_h_state_full", {})
    h_states = snap.get("h_states", {})
    agent_states = snap.get("agent_states", {})

    expected_h = {"h1", "h2", "h3", "h4", "h5"}
    expected_agents = {"strategist", "guardian", "analyst", "executor", "scout"}

    missing_h = expected_h - set(h_states.keys())
    missing_agents = expected_agents - set(agent_states.keys())

    if missing_h or missing_agents:
        return "FAIL", (
            f"missing H buckets: {sorted(missing_h)} "
            f"missing agent buckets: {sorted(missing_agents)}"
        )
    return "PASS", (
        f"10/10 buckets present "
        f"(H={len(h_states)}/5, agents={len(agent_states)}/5, "
        f"version={snap.get('version')})"
    )
```

### 7.2 漸進式 rollout（每 sub-task 落地後 expected set 補一 agent slot）

```
Phase 3 結束（baseline）  : expected = {h1,h2,h3,h4,h5}
Sub-task 4-1 land 後      : expected = {h1,h2,h3,h4,h5} + {strategist}
Sub-task 4-2 land 後      : expected += {guardian}
Sub-task 4-3 land 後      : expected += {analyst}
Sub-task 4-4 land 後      : expected += {executor}
Sub-task 4-5 land 後      : expected += {scout}  ← Phase 4 complete (10/10)
```

**WARN 邏輯**：set diff 結果非空但**並非全空** → WARN（部署半途容忍 missing agent slot）；set diff 全空 → PASS；H bucket 任一缺 → FAIL（Phase 3 已 live，缺 H bucket 是 regression）。

每 sub-task 都需在 prompt 中**強制 E1 同 commit 升級 healthcheck expected set**（避免 sub-task 落地後 healthcheck 持續 FAIL；rollback 時也 reverse 對應 expected set）。

---

## §8 風險矩陣 + multi-session race 防護

### 8.1 Phase 4 5 sub-task vs G3-09 schema parallel

PM Tier 9 sign-off 已派 G3-09 cost_edge_ratio design RFC（per memory 2026-04-26 Tier 9 Track 2）。G3-09 schema 與 Phase 4 schema 隔離：

| 範疇 | G3-09（cost_edge_advisor 模組） | Phase 4（5-Agent state events） |
|---|---|---|
| 主檔 | 新建 `cost_edge_advisor.py`（暫定） + Rust hot-path 模組 | 5 個 agent .py + h_state_query_handler.py |
| Schema 動 | 純消費 H5 cost_edge_ratio + 新增 advisory rule schema | 純新增 agent_states bucket（non-breaking） |
| 衝突點 | 無 — 兩者 SSOT 不同 | 無 |

**結論**：G3-09 與 Phase 4 可同 wave 並行派發（PM 編排 6 sub-task 並行：4-1 worktree + 4-2/3/4/5 主樹 + G3-09 主樹/worktree 視 G3-09 拆分結果）。

### 8.2 AgentState schema vs ExecutorConfigCache 雙資料流分離

**易混淆點**：Sub-task 4-4 Executor 同時動到：
- `_shadow_mode_provider()` lambda（G3-03 ConfigStore SSOT, Rust → Python read）
- `agent_states["executor"]["shadow_mode"]` snapshot（Phase 4 SSOT, Python → Rust observe）

**物理層次區分**（per RFC §2.4 special note）：
- ConfigStore = **CONFIG**（writeable via Operator IPC patch_executor_config）
- agent_state snapshot = **OBSERVATION**（read-only mirror of runtime decision）

**錯誤模式**：未來開發者誤以為「snapshot 寫入會改 ConfigStore」 → 雙向錯誤。**Sub-task 4-4 prompt template `具體實作 docstring` 章節必明確強調分離**（per §6.4 已寫）。

### 8.3 同 wave commit `--only` pattern（multi-session race 防護）

per memory `feedback_git_commit_only_for_metadoc`：本 RFC commit 用：

```bash
cd /Users/ncyu/Projects/TradeBot/srv
git add docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g3_08_phase4_5agent_design_rfc.md
git commit --only docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g3_08_phase4_5agent_design_rfc.md
git push origin main
```

memory.md 追加另起一個 `git commit --only` 提交（避免合併 commit 中 memory 與 RFC 雙改）。

### 8.4 隔壁 session WIP 不動

當前 git status（per task 環境章節說明）有 unstaged WIP：
- `TODO.md` / `memory/MEMORY.md` / E1a memory — **不動**（PM 接手）
- 不在 worktree 內（PA read-only design 工作即可）

本 RFC 寫到 `docs/CCAgentWorkSpace/PA/workspace/reports/`，與 unstaged WIP 不重疊。

### 8.5 Risk 矩陣

| # | 風險 | 機率 | 影響 | 緩解 |
|---|---|---|---|---|
| R1 | 4 並行 sub-task 同改 h_state_query_handler.py 衝突 | 中 | 中 | absorb pattern（PM 序貫 merge），加性 dict 操作不衝突 |
| R2 | Sub-task 4-1 等 STRATEGIST-SPLIT，SPLIT 卡住即全 Phase 4 阻塞 | 低（SPLIT 已並行進行） | 高 | PM 編排：先派 4-2/3/4/5 並行（不依賴 SPLIT），4-1 等 SPLIT 完成 |
| R3 | Analyst / multi_agent_framework.py 過 §七 警告線 | **高**（已超） | 低（警告不阻塞） | Backlog FUP-ANALYST-SPLIT + FUP-MAF-SPLIT，下 wave 拆檔 |
| R4 | Executor `_shadow_mode_provider()` 與 self._lock 死鎖 | 低 | 高 | 4-4 prompt §高風險警告明確：provider call **必在 self._lock 之外** + fail-closed default = 1 |
| R5 | invalidate_async daemon thread 高頻 spawn（5 agent × 3 hook） | 低 | 低 | per Phase 1 stress test 100k call < 30s；Phase 4 真實 ≤2.5/sec |
| R6 | strategy_wiring SCOUT_AGENT singleton 名稱不對 | 中（待 4-5 grep 驗） | 中 | 4-5 prompt 前置 grep 步驟強制 |
| R7 | 4-1 land 後 4-2/3/4/5 同時改同一 fn `_collect_agent_snapshots` git conflict | 中 | 中 | absorb pattern + per-arm if 區塊隔離（4-2 加 include_guardian arm，4-3 加 include_analyst arm，互不重疊） |
| R8 | bool 字段未 cast int 導致 Rust HashMap parse fail | 中 | 中 | Phase 4 invariant 強制 int / bool→int；E2 review 必查每個 snapshot return dict |
| R9 | snapshot 字段名 typo（如 `intel_produced` 寫成 `intl_produced`）silent regression | 中 | 中 | E2 review 必對 schema RFC §2.X 逐字段比對；agent_states.<agent> Rust 端用 HashMap 容忍 typo（不 raise）但會 silent miss |
| R10 | env=0 invalidator no-op 在某 hook callsite 漏判 | 低 | 低 | invalidate_async 內部已 env-gate（per `h_state_invalidator.py:130 is_gateway_enabled`）；callsite 不需重判 |

---

## §9 工時預估

### 9.1 Total wall-clock：≤ 4d（與 PA design §11.1 估值對齊）

| Phase | E1 wall-clock | E2 review | E4 regression | E5 refactor | 全鏈 |
|---|---|---|---|---|---|
| **Sub-task 4-1 Strategist** | 1d（含 SPLIT 等待） | 0.5d | 0.5d | 0.5d | 2.5d 順序 |
| **Sub-task 4-2/3/4/5 並行** | 0.75d × 4 並行 = 0.75d | 0.5d（4 commit 集中） | 0.5d（合 regression） | 0.5d（合 refactor） | 2.25d |
| **Total Phase 4 順序** | — | — | — | — | **5d** |
| **Total Phase 4 並行** | — | — | — | — | **3.75d** ✅ |

對比 PA design §11.1 估 **4d**：3.75d 並行版略快於估值，預留 0.25d buffer 應急。

### 9.2 per sub-task 工時細節

| Sub-task | E1 樂觀/中位/悲觀 | E2 | E4 | 註 |
|---|---|---|---|---|
| 4-1 Strategist | 0.75d / 1d / 1.5d | 0.5d | 0.5d | hard pre-condition SPLIT |
| 4-2 Guardian | 0.5d / 0.75d / 1d | 共 4-3/4/5 集中 0.5d | 共 4-3/4/5 集中 0.5d | 並行 |
| 4-3 Analyst | 0.5d / 0.75d / 1d | 同上 | 同上 | 並行；§七 警告 |
| 4-4 Executor | 0.5d / 0.75d / 1d | 同上 | 同上 | 並行；shadow_mode wire |
| 4-5 Scout | 0.5d / 0.75d / 1d | 同上 | 同上 | 並行；§九 接近 |

### 9.3 E5 refactor pass after Phase 4 完成（per CLAUDE.md §八 強制工作鏈）

per CLAUDE.md §八：「`@E5` 優化（每 Phase / Wave / ≥3 E1 任務強制）」。Phase 4 = 5 sub-task ≥ 3 → E5 強制觸發。

E5 範圍建議：
- 5 個 `get_<agent>_snapshot()` 共用 helper 提取（如 `_int_stats(stats_dict, keys: list)` 純 utils）
- `_collect_agent_snapshots` 5 個 if 區塊重複 pattern → loop / dispatcher dict
- 雙語 docstring 跨 5 method 重複 → shared base docstring fragment

**E5 工時**：0.5d。

---

## §10 unblock 下游路徑

### 10.1 G8-01 認知自適應 e2e 測試

**G8-01 描述**（per TODO.md Wave 3）：CognitiveModulator ≥85% line cov + StrategistAgent integration test 整合（含 Conductor stub fallback）。

**強依賴 Phase 4 Sub-task 4-1**：
- StrategistAgent integration test 需驗 `cognitive_modulator_connected` 狀態通過 IPC 看見（per RFC §2.1 第 11 field）
- Rust fixture（`cargo test` 端）讀 `agent_states["strategist"]["cognitive_modulator_connected"]` ≤1ms p99 即時驗證 wire 接通

**強依賴 Phase 4 Sub-task 4-3** （Analyst experiment_ledger）：
- 學習平面接入指示（Analyst snapshot `experiment_ledger_connected`）= G8-01 e2e 測試的 dimension

**派發前置**：Phase 4 Sub-task 4-5 commit 後 24h dogfood 觀察 10-bucket parity + healthcheck [20] 升級版確認後可派 G8-01。

### 10.2 G3-09 cost_edge_advisor 跨 Agent 訂閱

**G3-09 設計 RFC**（per memory 2026-04-26 Tier 9 Track 2）：cost_edge_advisor 模組 4.5d Phase A schema+advisory + 1.5d Phase B shadow + 2.5d Phase C live triggered gate = 8.5d 全鏈。

**Phase 4 解阻 G3-09 Phase A**：
- Rust hot-path `query_agent_state(cache, "strategist", "ai_evaluations")` + `query_agent_state(cache, "analyst", "l2_analyses")` + `query_h_state(cache, "h5", "cost_edge_ratio")` 三條 ≤1ms p99 即時讀
- cost_edge_advisor 規則 = `if cost_edge_ratio >= 0.8 AND ai_evaluations_per_min > 5 AND l2_analyses_per_min > 1: advise(REDUCE_POSITION_SIZING)`
- Phase 4 提供 ai_evaluations + l2_analyses 兩個 cross-agent dimension（單純 H5 看不到 agent breakdown）

### 10.3 完整 unblock graph

```
Phase 1 ✅ (commits aa287c4 / 1c7b20e / 5943337)
  ↓
Phase 2 ✅ (commits 9120948 + f2ed286 — H1+H3)
  ↓
Phase 3 ✅ (commits 8cd257e + 71faf4c + 1c7b20e — H2/H4/H5)
  ↓
G3-08-PHASE-4-STRATEGIST-SPLIT (next session, hard pre-cond for 4-1)
  ↓
Sub-task 4-1 Strategist
  ↓
  ┌─────────────┬─────────────┬─────────────┐
  ▼             ▼             ▼             ▼
Sub-task 4-2  Sub-task 4-3  Sub-task 4-4  Sub-task 4-5
(Guardian)    (Analyst)     (Executor)    (Scout)
  │             │             │             │
  └──────┬──────┴──────┬──────┴──────┬──────┘
         │             │             │
         ▼             ▼             ▼
        Phase 4 完成（10-bucket envelope live）
                      │
         ┌────────────┼────────────┐
         ▼            ▼            ▼
       G8-01        G3-09        Future
       認知 e2e     cost_edge    GUI 6-pane
                    advisor      dashboard
```

---

## §11 治理對照（CLAUDE.md §二 16 根原則 + §四 硬邊界）

### 11.1 16 根原則

| # | 原則 | 狀態 |
|---|---|---|
| #1-#10 | 同 PA design plan §8.2（observability extension only） | ✅ 全綠 |
| #6 失敗默認收縮 | env=0 default + invalidator/poller 雙端 fail-closed default + 4-4 shadow_mode provider raise → 1 (shadow on) | ✅ |
| #11 Agent 最大自主權 | snapshot 純讀，不限制 agent 任何決策能力 | ✅ |
| #13 AI 成本感知 | Phase 4 4-3 (Analyst l2_analyses) + 4-1 (Strategist ai_evaluations) → G3-09 cost_edge_advisor 跨維度判斷 | ⭐ |
| #15 多 Agent 協作 | Phase 4 直接強化（5-Agent → Rust 觀測通道全 wired） | ⭐⭐ |

### 11.2 §四 5 項 live 硬邊界

| 邊界 | 觸碰 | 說明 |
|---|---|---|
| live_reserved | ❌ | 純 observability |
| Operator 角色 auth | ❌ | 純 observability |
| OPENCLAW_ALLOW_MAINNET | ❌ | 不影響 Mainnet gate |
| API key/secret slot | ❌ | 不影響 secret resolution |
| authorization.json HMAC | ❌ | 不影響 5min re-verify |

**全 5 項零觸碰** ✅

### 11.3 §九 Singleton table 維護

Phase 4 不新增 singleton（重用 Phase 1C `_H_STATE_INVALIDATOR` + 既有 5 agent module-level singleton via strategy_wiring）。**§九 不需更新**。

### 11.4 §七 文件大小

| 檔 | Phase 4 後預計 LOC | 警告線 800 / 硬上限 1200 | 行動 |
|---|---|---|---|
| `strategist_agent.py`（split 後） | 710 + 60 = ~770 | < 800 ✅ | 無 |
| `guardian_agent.py` | 587 + 35 = ~622 | < 800 ✅ | 無 |
| `analyst_agent.py` | 834 + 26 = ~860 | **> 800 ⚠️** | Backlog FUP-ANALYST-SPLIT |
| `executor_agent.py` | 669 + 36 = ~705 | < 800 ✅ | 無 |
| `multi_agent_framework.py` | 1137 + 27 = ~1164 | < 1200 ✅（接近）| Backlog FUP-MAF-SPLIT |
| `h_state_query_handler.py` | 636 + 84 = ~720 | < 800 ✅ | 無 |

**2 條 Backlog 必排**：
- **G3-08-FUP-ANALYST-SPLIT**：Analyst 主檔已超 §七 警告線（pre-Phase-4 即超），下 wave 拆檔（建議目標 ~480 LOC，per Phase 4 split RFC §6.4 Method A）
- **G3-08-FUP-MAF-SPLIT**：multi_agent_framework.py 距 §九 1200 hard cap 36 LOC，下 wave 拆 ScoutAgent (~183 LOC) 出獨立 `scout_agent.py`

---

## §12 沒做的事（E1/E2 領域）

- 沒寫 5 sub-task 任何實作代碼（純 design + 5 prompt template）
- 沒派 sub-agent（純 PA 主 agent 串行讀+寫）
- 沒跑 cargo test / pytest（E1/E4 任務）
- 沒驗 STRATEGIST-SPLIT 是否已 land（next session PM 啟動前驗）
- 沒擴範圍到 G3-09 cost_edge_advisor 演算法（屬 G3-09 ticket）
- 沒擴範圍到 G8-01 認知 e2e 測試（屬 Wave 3 ticket）
- 沒實際拆 Analyst / multi_agent_framework.py（屬 Backlog FUP，本 RFC §11.4 已 file）
- 沒擴範圍到 GUI 統一 H+Agent dashboard（屬未來 ticket）

---

## §13 教訓備忘（給未來 PA / PM）

1. **Phase 1+2+3 commit pattern 收斂後，Phase 4 sub-task 拆分應鏡 Phase 3**（Pattern B 1-agent-1-sub-task），不需重新發明拆法。pattern 法則：1 SSOT 1 sub-task。
2. **Phase 4 比 Phase 3 並行性更高**（5 不同主檔 vs Phase 3 共享 layer2_cost_tracker.py）。但仍需 absorb pattern（PM 序貫 merge `_collect_agent_snapshots` h_state_query_handler.py 共改）。
3. **Phase 4 split RFC 預留 ~90 LOC headroom 是 plan-ahead 投資**：Sub-task 4-1 land ~60 LOC + Phase 5 預留 ~30 LOC 仍 < §七 800（per RFC §11.4）。**未來大型 cross-cutting 工作前必先評估各影響檔的 §七/§九 headroom**，提前 split 是最便宜的解法。
4. **snapshot vs config cache 物理層次**（Sub-task 4-4 Executor 案例）：未來凡是 Rust ConfigStore + Python observation 兩條資料流共存的場景，prompt template 必明確標記方向（read vs write、SSOT vs mirror、cache vs state），避免後續開發者誤改方向破壞 G3-03 ConfigStore 契約。
5. **bool→int cast 規則**（Phase 4 invariant）：所有 snapshot 字段必為 int 或 bool→int（不准 float / string），對齊 Rust `AgentState.stats: HashMap<String, i64>`。Phase 5+ 若需 float 字段（如延遲 ms） → 新增 `AgentState.gauges: HashMap<String, f64>` 兄弟字段（不混入 stats）。
6. **multi_agent_framework.py 1137 LOC 是 Phase 1+2+3 合計擴展副作用**（5 個 agent class 集中在一檔的歷史包袱）。Phase 4 揭發 §九 距離只剩 36 LOC headroom。**ScoutAgent 拆檔（FUP-MAF-SPLIT）優先級提升至 P1**（避 Phase 5 觸 §九 hard cap 阻塞 wave）。
7. **healthcheck expected set 漸進式 rollout 是 5 sub-task 並行的關鍵**：每 sub-task 必同 commit 升級 healthcheck，避免半途部署 healthcheck 持續 FAIL；rollback 時 expected set 也 reverse。E2 review 必查 healthcheck 升級。
8. **5 sub-task 命名 convention `agent.<role>.<event>` 是 future-proof key**：Phase 5 加 Conductor → `agent.conductor.<event>`，前綴 namespace 確保 Rust DashMap shard 分布、Python invalidator log filter 都一致 query。

---

## §14 報告索引追加

| 日期 | 報告類型 | 文件位置 |
|---|---|---|
| 2026-04-27 | G3-08 Phase 4 5-Agent state events design RFC（推 Pattern B 5 sub-task / ETA 3.75d 並行） | workspace/reports/2026-04-27--g3_08_phase4_5agent_design_rfc.md |

---

**全文完。next: PM 啟動 Phase 4 wave 先驗 STRATEGIST-SPLIT 是否已 land + Phase 3 healthcheck [20] 仍綠 → 派 Sub-task 4-1（待 SPLIT）→ 4-2/3/4/5 並行（不依賴 SPLIT）→ 4-1 commit 後 PM merge → 全 5 sub-task 完成後 G8-01 + G3-09 unblock → E5 refactor pass 收尾。Backlog FUP-ANALYST-SPLIT + FUP-MAF-SPLIT 排下 wave。**
