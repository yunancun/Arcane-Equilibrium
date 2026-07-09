# G3-08 H1-H5 → Rust IPC Gateway 技術設計（PA Plan Only）

- **作者**：PA（Project Architect）
- **日期**：2026-04-26
- **狀態**：Plan only — 不寫實作代碼
- **觸發**：TODO.md Wave 2 G3-08（P3）
- **前置 ✅**：G3-03 ExecutorConfigCache + ExecutorAgent rewire（commit `51608fe`，2026-04-25）
- **解阻 後續**：G3-09 cost_edge_ratio 演算法（P3）+ G8-01 認知自適應 e2e 測試（W3 deferred 待此 ticket）

---

## §1 現狀

### 1.1 H1-H5 + 5-Agent 架構（Python-only）

OpenClaw 5-Agent + H1-H5 AI 治理層當前**全 Python 進程**：

| 模組 | 檔案 | LOC | 狀態 |
|---|---|---|---|
| H1 ThoughtGate | `app/h1_thought_gate.py` | 185 | live（2026-04-23 audit 已驗，shadow=False） |
| H2 budget gate | `app/layer2_cost_tracker.check_daily_budget()` | 共用 | live |
| H3 ModelRouter | `app/model_router.py` | 292 | live（4-tier l1_9b/l1_27b/l1_5/l2 + L2 cache） |
| H4 validator | `app/h4_validator.py` | 103 | live |
| H5 cost_logging | `app/layer2_cost_tracker.py` | 727 | live |
| Strategist | `app/strategist_agent.py` | 1170 | shadow=False（Sprint 5a live） |
| Guardian | `app/guardian_agent.py` | 587 | live（subscribe MessageBus） |
| Analyst | `app/analyst_agent.py` | 834 | live |
| Executor | `app/executor_agent.py` | 630 | shadow_mode=True（G3-03 IPC 控制） |
| Scout | `app/scout_worker.py` | 194 | daemon 30min |
| MultiAgent fwk | `app/multi_agent_framework.py` | 1137 | MessageBus + 5 subscribe |

合計 **~4552 行** Python AI/governance 在 main process 內運行。

### 1.2 現有 IPC 結構（單向）

當前 Python ↔ Rust IPC 是**單向 Python push to Rust** + **Rust 偶爾 push status 給 Python**：

- **Forward path（Python → Rust）**：
  - `update_strategy_params` / `patch_risk_config` / `patch_learning_config` / `patch_budget_config` — 寫 Rust ConfigStore
  - `record_ai_usage` — H5 cost 同步給 Rust BudgetTracker（fire-and-forget，已有，見 `layer2_cost_tracker.py:264 _sync_to_rust_budget`）
  - `set_strategy_active` / `set_dynamic_risk_enabled` 等 control flips
- **Reverse path（Rust → Python）**：
  - `get_paper_state` / `get_mode_snapshot` / `get_active_modes` / `get_latest_prices` / `get_tick_stats`
  - `get_strategy_params` / `get_risk_config` / `get_learning_config` / `get_budget_config`
  - `get_ai_budget_status` / `get_strategist_cycle_metrics`
- **Pull 模型已驗證 pattern**：G3-03 ExecutorConfigCache（commit `51608fe`，788 LOC）將 Rust `RiskConfig.executor` 子切片以**10s daemon poll** + **fail-closed 預設** + **graceful degrade**（首次成功後保留 last good snapshot）方式包裝給 Python ExecutorAgent。

### 1.3 痛點 — Rust 看不到 H1-H5 + 5-Agent 狀態

**5 個具體場景無法支援**（按優先級）：

| # | 場景 | 當前 workaround | 缺口 |
|---|---|---|---|
| 1 | Rust `intent_processor.rs` 風控 gate 階段檢視 H1-H4 是否拒絕 | 只能事後查 audit_log（async） | hot-path 無 H state |
| 2 | Rust 即時 cost-aware 縮倉（H5 hard_cap 觸頂時） | Python 自己縮，Rust 無感 | 跨進程 hysteresis |
| 3 | GUI 健檢需 H 級觀測（H1 budget_skip 24h 統計、H3 tier 分布） | 寫 GUI endpoint 從 state_store 讀 | 無 Rust 端 healthcheck 可達 |
| 4 | G3-09 cost_edge_ratio 演算法需要 Rust 端讀 H5 paper_pnl_7d / ai_spend_7d | 走 sync IPC pull（每 tick）= breach SLA | 必需 cached snapshot |
| 5 | G8-01 認知自適應 e2e 測試 — 5-Agent state events → Rust 觀測 | Python state_store + Mac 拉 GUI | 集成測試需 Rust 端 fixture |

**G3-03 已示範的 pattern**：Python 端 cache + 10s poll + fail-closed default + graceful degrade。**G3-08 是這個 pattern 的反向擴展**（Rust 端 cache，從 Python pull）+ **新增的 push** invalidation 通道。

### 1.4 為什麼**不能**直接重用 G3-03 模板

| 維度 | G3-03 ExecutorConfigCache | G3-08 H State Gateway |
|---|---|---|
| 流向 | Rust 是 SSOT，Python pull | Python 是 SSOT，Rust pull |
| 字段量 | 3 個（shadow_mode / max_pos / per_symbol_cap） | 5 H 模組各 5-15 個（合計 ~50+） |
| 更新頻率 | 低（Operator IPC patch） | 高（H1 每 intel 30s 內、H5 每 AI call、5-Agent 每 emit） |
| Hot-path 消費者 | Python ExecutorAgent（非 hot-path） | Rust intent_processor / risk_gate（**1ms hot-path SLA**） |
| Crash 行為 | Rust crash 整個 engine 死，Python 端 fail-closed | Python crash 不能讓 Rust 卡，須**graceful 沿用 last good** |

**結論**：G3-08 需要**反向 pattern + 新增 push 路徑**。

---

## §2 設計目標

| # | 目標 | 量化指標 |
|---|---|---|
| G1 | 雙向通道：Python H/Agent state → Rust + Rust hot-path query | forward push + reverse pull 都 ≤ 5ms |
| G2 | Hot-path SLA 保護 | Rust hot-path query (`query_h_state`) ≤ 1ms p99（DashMap lookup，無 IPC roundtrip） |
| G3 | DEFAULT-OFF env-gate | `OPENCLAW_H_STATE_GATEWAY=1` 才啟動，否則 zero overhead |
| G4 | Python crash → Rust 不死 | Rust 沿用 last good snapshot，timestamp 標記 stale |
| G5 | H state**永不影響交易決策** | Rust 端只**讀**用於 observability + cost_edge_ratio computation；**不**做 risk gate（純 advisory） |
| G6 | 漸進可逆 | Phase 1-4 各 phase 完成後即可獨立 rollback（env flip） |
| G7 | Schema 演化兼容 | 新增 H 字段不需 lock-step Rust deploy（forward-compat parsing） |

### 2.1 非目標（明確排除）

- ❌ **不**取代 H state JSON file persistence（`runtime/layer2_cost_state.json` 仍是 H5 SSOT，IPC 是即時鏡像）
- ❌ **不**讓 Rust 寫 H state（Python 是 SSOT，唯一寫入口）
- ❌ **不**與 G3-03 ExecutorConfigCache 合併（流向相反，混合 pattern 會增加複雜度）
- ❌ **不**動 H1-H5 / 5-Agent 業務邏輯（純 observability extension）

---

## §3 三選項對比

### Option A：Python push 模型（aggressive push）

**機制**：
- Python H1-H5 + 5-Agent 各加 hook → 每次 state 變化推 IPC `emit_h_state_event` 到 Rust
- Rust 維護 in-memory snapshot（DashMap），按 H module 分桶
- Rust 提供 `query_h_state(h_module)` IPC handler 給 Python GUI / healthcheck（非 hot-path）
- Rust hot-path 直接讀 DashMap snapshot

**ASCII 流程圖**：
```
Python H1 budget_skip ─push event──▶  Rust IPC handler ──update──▶ DashMap[H1] ──read──▶ hot-path
                                                                       ▲
                                       Rust GUI healthcheck ──query────┘
```

**優點**：
- Push timing 精準（state 變化即推）
- Rust 端 0ms cache latency（永遠 fresh）

**缺點**：
- IPC 量爆炸：H1 每 intel 觸發、H5 每 AI call、Strategist 每 evaluate cycle、Scout 每 30min
- 估算 ~1000-5000 events/min（650 symbols × 各 H × 評估頻率）
- Python crash → Rust 端 state 立刻過時（無心跳機制 → hot-path 拿到 stale data）
- 每個 H 模組需各自加 hook（5 H + 5 Agent = 10 個改動點），擴 schema 痛苦

### Option B：Rust pull 模型（pure pull）

**機制**：
- Rust 需要 H 狀態時走 IPC `query_h_state(h_module)` → Python state_store
- Python 維護 H 狀態 dict（已有 state_store + Layer2CostTracker 等）
- 無新 push 通道

**ASCII 流程圖**：
```
Rust hot-path ──IPC roundtrip──▶ Python state_store ──response──▶ Rust（每 query）
                  (1-5ms!)
```

**優點**：
- Python 為唯一真理源，無 dual-state
- 實作極簡（只加 1 個 reverse IPC handler）

**缺點**：
- **致命：每 hot-path query 一條 IPC = breach 1ms SLA**（IPC roundtrip 通常 1-3ms）
- Tick-rate query (650 symbols × N ticks/sec) → IPC 隊列爆炸
- 違反 G2

### Option C：混合模型（cache + invalidation push）★ 推薦

**機制**：
- 鏡射 G3-03 ExecutorConfigCache pattern，但**反向**：
  - Rust 端 cache（**新建** sibling `h_state_cache.rs`，DashMap 背景 daemon 每 10s poll Python `query_h_state_full`）
  - Python 端 emit 「**state changed**」event（**只推一條 invalidation hint**，不推完整 state）
  - Rust 收到 invalidation → 立刻 trigger 一次 ad-hoc poll（不等 10s）
- **Hot-path 永遠讀 DashMap**（lookup ≤ 1ms）
- Rust 端 staleness check：snapshot age ≤ 30s 視為 fresh，> 30s 標記 stale 但仍可讀（fail-soft）

**ASCII 流程圖**：
```
Python H1 budget_skip ──invalidate(h1)──▶ Rust ad-hoc poll trigger
                                                  ▼
Rust 10s daemon ──IPC pull──────────────▶ Python query_h_state_full ──response──▶ Rust DashMap[H1..H5+5Agent]
                                                                                       ▲
                                                                                       │ ≤1ms lookup
                                                            Rust hot-path ─────────────┘
                                                            Rust GUI/healthcheck ───query──┘
```

**優點**：
- 鏡射已驗證 G3-03 pattern（Phase B commit 51608fe 過 17 tests / 286 LOC test suite）
- IPC 量可控（10s base poll + 偶發 invalidation，估 ~50 events/min vs Option A 5000+）
- Hot-path SLA 達標（DashMap lookup ≤ 1ms）
- Python crash → Rust 沿用 last good snapshot（標 staleness flag）
- Schema 演化容易：Python 一次推 full snapshot，Rust 一次解一個 dict
- DEFAULT-OFF 易做（poll daemon spawn 條件加 env check）

**缺點**：
- 複雜度高（需 push + pull 雙通道）
- 10s poll + invalidation 偶有 race（< 10s 內兩次變化可能合併推送，但對 observability 可接受）

### 3.1 推薦 Option C 的決策矩陣

| 評分維度 | A push | B pull | C 混合 |
|---|---|---|---|
| Hot-path SLA | ✅ 0ms | ❌ 1-3ms breach | ✅ ≤1ms |
| IPC 量 | ❌ 5000/min | ✅ 0 (no daemon) | ✅ 50/min |
| 實作複雜度 | 中（10 個 hook） | ✅ 低（1 handler） | 中（1 daemon + 1 invalidation hook） |
| Python crash 韌性 | ❌ 立刻 stale | ❌ Rust hot-path 死 | ✅ last good 沿用 |
| Schema 演化 | ❌ 10 個 hook 跟改 | ✅ 1 handler 改 | ✅ 1 schema 改 |
| 與 G3-03 一致性 | ❌ 反 pattern | 中 | ✅ 鏡射 |
| **總分** | 2/6 | 2/6 | **6/6** |

**結論：選 Option C**。

---

## §4 推薦方案：Option C 混合模型詳細設計

### 4.1 Rust 端結構（新建 sibling `h_state_cache.rs`）

```rust
// rust/openclaw_engine/src/h_state_cache/mod.rs (~250 LOC)
// rust/openclaw_engine/src/h_state_cache/types.rs (~150 LOC)
// rust/openclaw_engine/src/h_state_cache/poller.rs (~200 LOC)

pub struct HStateCache {
    // DashMap 線程安全 + lock-free read
    h1: DashMap<&'static str, H1Stats>,         // budget_skip / complexity_skip / cooldown_skip 等
    h2: DashMap<&'static str, H2BudgetState>,   // daily_remaining_usd / hard_cap_usd
    h3: DashMap<&'static str, H3RouteStats>,    // route counts by tier
    h4: DashMap<&'static str, H4ValidationStats>, // validation_fail count
    h5: DashMap<&'static str, H5CostStats>,     // ai_spend_7d / paper_pnl_7d / cost_edge_ratio
    agents: DashMap<&'static str, AgentState>,  // 5-Agent stats（intel_evaluated / intents_produced 等）
    fetched_at_ms: AtomicI64,                   // last successful poll timestamp
    config_version: AtomicU64,                  // Python state_store version (monotonic)
}

impl HStateCache {
    pub fn query(&self, h_module: &str, key: &str) -> Option<HStateValue> {
        // ≤ 1ms DashMap lookup
    }
    pub fn staleness_ms(&self) -> i64 {
        let now = unix_ms();
        now - self.fetched_at_ms.load(Ordering::Acquire)
    }
    pub fn is_stale(&self) -> bool {
        self.staleness_ms() > 30_000  // 30s threshold
    }
}

pub fn spawn_h_state_poller(
    cache: Arc<HStateCache>,
    poll_interval: Duration,
    cancel: CancellationToken,
) -> JoinHandle<()> {
    // tokio::spawn with cancel guard
    // 每 N 秒 + 收 invalidation hint 後立刻一次 poll
}
```

**新增 sibling**：`rust/openclaw_engine/src/h_state_cache/{mod.rs, types.rs, poller.rs}`（不改既有檔，pattern 對齊 G5-FUP-IPC-MOD-SPLIT）。

### 4.2 IPC schema（5 條 message types）

#### 4.2.1 `query_h_state_full`（Rust → Python，新）

```json
{
  "jsonrpc": "2.0",
  "method": "query_h_state_full",
  "params": {"engine": "demo", "include": ["h1", "h2", "h3", "h4", "h5", "agents"]},
  "id": 1
}
```

Response:
```json
{
  "jsonrpc": "2.0",
  "result": {
    "version": 1234,
    "fetched_at_ms": 1714123456789,
    "h1": {"budget_skip": 12, "complexity_skip": 5, "cooldown_skip": 8, "cooldown_dict_size": 47},
    "h2": {"daily_remaining_usd": 1.42, "hard_cap_usd": 2.00, "adaptive_multiplier": 0.8},
    "h3": {"l1_9b": 234, "l1_27b": 56, "l1_5": 12, "l2": 3, "cache_size": 18, "cache_hit": 89, "cache_expired": 4},
    "h4": {"validation_fail": 2, "validation_pass": 304},
    "h5": {"ai_spend_7d_usd": 4.23, "paper_pnl_7d_usd": -2.15, "cost_edge_ratio": -0.508, "data_days": 4},
    "agents": {
      "strategist": {"intel_evaluated": 412, "intents_shadow_logged": 0, "intents_produced": 38, "ai_evaluations": 89},
      "guardian":   {"intents_received": 38, "intents_approved": 24, "intents_rejected": 14},
      "analyst":    {"opportunities_tracked": 7},
      "executor":   {"shadow_logs": 24, "real_submits": 0},
      "scout":      {"intel_produced_24h": 56}
    }
  },
  "id": 1
}
```

#### 4.2.2 `invalidate_h_state`（Python → Rust，新）

```json
{
  "jsonrpc": "2.0",
  "method": "invalidate_h_state",
  "params": {"h_module": "h5", "reason": "claude_call_recorded"},
  "id": null
}
```

**Fire-and-forget**（Python 不等 response），純提示 Rust 立刻觸發一次 ad-hoc poll。

#### 4.2.3 `query_h_state`（Rust 內部，**不上 IPC**）

純 Rust API，hot-path 用：
```rust
pub fn query_h_state(cache: &HStateCache, h_module: &str, key: &str) -> Option<HStateValue> {
    cache.query(h_module, key)  // ≤ 1ms DashMap
}
```

#### 4.2.4 `get_h_state_status`（GUI 用，**新 IPC**）

```json
{"method": "get_h_state_status", "params": {}}
```

Response: `{"version": 1234, "staleness_ms": 5234, "is_stale": false, "poll_attempts": 89, "poll_successes": 87, "poll_failures": 2}`

供 healthcheck 監看 cache 健康。

#### 4.2.5 (Reserved) `set_h_state_gateway_enabled`

Phase 4+ 動態 toggle 用，留 schema slot 但 Phase 1 不實作。

### 4.3 Python 端 hook 設計（Phased）

每個 H 模組加 1 個 hook：state 變化後 fire-and-forget `invalidate_h_state` IPC（不阻塞）。

**抽象基底**（pattern 對齊既有 `_sync_to_rust_budget`）：

```python
# app/h_state_invalidator.py (~80 LOC，新建)
import threading
def invalidate_async(h_module: str, reason: str = "") -> None:
    if not _IS_GATEWAY_ENABLED:  # env-gate check
        return
    def _do():
        try:
            from .ipc_client import EngineIPCClient
            import asyncio
            async def _call():
                client = EngineIPCClient()
                await client.connect()
                try:
                    await client.notify("invalidate_h_state",
                                        params={"h_module": h_module, "reason": reason},
                                        timeout=2.0)
                finally:
                    await client.disconnect()
            asyncio.run(_call())
        except Exception:
            logger.debug("invalidate_h_state failed (non-fatal)")
    threading.Thread(target=_do, daemon=True).start()
```

**5 H + 5 Agent = 10 個 callsite 加一行**：
```python
# h1_thought_gate.py:check() return False 處
stats["h1_budget_skip"] += 1
invalidate_async("h1", "budget_skip")  # ← 新增 1 行
```

### 4.4 Rust query_h_state_full handler 實作位置

新建 `rust/openclaw_engine/src/ipc_server/handlers/h_state.rs`（~150 LOC）：

```rust
pub(super) async fn handle_query_h_state_full(
    id: serde_json::Value,
    params: &serde_json::Value,
    cache: &Option<Arc<HStateCache>>,
) -> JsonRpcResponse { ... }
```

dispatch.rs 加 1 個 arm：
```rust
"query_h_state_full" => handle_query_h_state_full(id, &req.params, h_state_cache).await,
"get_h_state_status" => handle_get_h_state_status(id, h_state_cache),
"invalidate_h_state" => handle_invalidate_h_state(id, &req.params, h_state_cache),
```

### 4.5 Slot pattern（對齊 BudgetTrackerSlot / TeacherLoopSlot）

`slots.rs` 加：
```rust
pub type HStateCacheSlot = Arc<RwLock<Option<Arc<HStateCache>>>>;
```

`main_boot_tasks.rs` env-gate spawn:
```rust
if std::env::var("OPENCLAW_H_STATE_GATEWAY").as_deref() == Ok("1") {
    let cache = Arc::new(HStateCache::new());
    let poller = spawn_h_state_poller(Arc::clone(&cache), Duration::from_secs(10), cancel);
    ipc_server.set_h_state_cache_slot(cache);
}
// 否則 slot stays None，handler return uninitialized
```

---

## §5 IPC 完整 schema（含 type definitions）

### 5.1 Python 端 `query_h_state_full` route handler 預期 in `governance_routes.py` 或新檔 `h_state_routes.py`

```python
# control_api_v1/app/h_state_query_handler.py（新建，純查詢函式，無 route）
def build_h_state_full_response(include: list[str]) -> dict:
    """聚合 H1-H5 + 5-Agent state 為單一 dict。"""
    out = {"version": _state_version_counter(), "fetched_at_ms": int(time.time()*1000)}
    if "h1" in include:
        out["h1"] = STRATEGIST_AGENT.get_h1_stats_snapshot()
    if "h2" in include:
        out["h2"] = COST_TRACKER.get_h2_budget_snapshot()
    if "h3" in include:
        out["h3"] = STRATEGIST_AGENT.get_h3_route_stats_snapshot()
    if "h4" in include:
        out["h4"] = STRATEGIST_AGENT.get_h4_validation_stats_snapshot()
    if "h5" in include:
        out["h5"] = COST_TRACKER.get_h5_cost_snapshot()
    if "agents" in include:
        out["agents"] = {
            "strategist": STRATEGIST_AGENT.get_stats_snapshot(),
            "guardian": GUARDIAN_AGENT.get_stats_snapshot(),
            "analyst": ANALYST_AGENT.get_stats_snapshot(),
            "executor": EXECUTOR_AGENT.get_stats_snapshot(),
            "scout": SCOUT_AGENT.get_stats_snapshot(),
        }
    return out
```

**Note**：`get_*_snapshot()` 多數是新 method（H1ThoughtGate / Layer2CostTracker / 5 Agent 各加一個），但**讀已有的 self._stats / self._h1_cooldown / self._adaptive 等**，0 業務邏輯改動。

### 5.2 Rust H1Stats / H2BudgetState / ... 結構

`rust/openclaw_engine/src/h_state_cache/types.rs`：

```rust
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct H1Stats {
    pub budget_skip: u64,
    pub complexity_skip: u64,
    pub cooldown_skip: u64,
    pub cooldown_dict_size: u64,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct H2BudgetState {
    pub daily_remaining_usd: f64,
    pub hard_cap_usd: f64,
    pub adaptive_multiplier: f64,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct H3RouteStats {
    pub l1_9b: u64,
    pub l1_27b: u64,
    pub l1_5: u64,
    pub l2: u64,
    pub cache_size: u64,
    pub cache_hit: u64,
    pub cache_expired: u64,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct H4ValidationStats {
    pub validation_fail: u64,
    pub validation_pass: u64,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct H5CostStats {
    pub ai_spend_7d_usd: f64,
    pub paper_pnl_7d_usd: f64,
    pub cost_edge_ratio: Option<f64>,  // None when data_days < ADAPTIVE_MIN_DAYS
    pub data_days: u32,
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct AgentState {
    pub agent_name: String,
    pub stats: HashMap<String, i64>,  // forward-compat 鬆綁
}
```

**Forward-compat 設計**：未知字段 Rust serde 用 `#[serde(default)]`、AgentState `stats` 用 HashMap，新增字段 Python 推送即可，Rust 不需 lock-step deploy。

---

## §6 Rust 端結構詳細

### 6.1 新建檔案清單

| 檔案 | LOC 估 | 職責 |
|---|---|---|
| `rust/openclaw_engine/src/h_state_cache/mod.rs` | ~150 | HStateCache struct + DashMap + atomic timestamps |
| `rust/openclaw_engine/src/h_state_cache/types.rs` | ~200 | H1Stats / H2/H3/H4/H5 / AgentState struct |
| `rust/openclaw_engine/src/h_state_cache/poller.rs` | ~250 | tokio daemon poll loop + invalidation channel |
| `rust/openclaw_engine/src/h_state_cache/tests.rs` | ~250 | 12+ unit tests（cache lookup / staleness / poller smoke / invalidation race） |
| `rust/openclaw_engine/src/ipc_server/handlers/h_state.rs` | ~200 | 3 handler（query_full / get_status / invalidate） |

合計 **~1050 LOC** Rust 新增。

### 6.2 既有檔修改

| 檔案 | 改動 |
|---|---|
| `rust/openclaw_engine/src/lib.rs` | 加 `pub mod h_state_cache;` |
| `rust/openclaw_engine/src/ipc_server/mod.rs` | 加 `HStateCacheSlot` field + setter |
| `rust/openclaw_engine/src/ipc_server/slots.rs` | 加 `HStateCacheSlot` type alias |
| `rust/openclaw_engine/src/ipc_server/dispatch.rs` | 加 3 個 method arm（query_full / get_status / invalidate） |
| `rust/openclaw_engine/src/ipc_server/handlers/mod.rs` | 加 `pub(super) mod h_state;` + re-export |
| `rust/openclaw_engine/src/main_boot_tasks.rs` | env-gate 條件 spawn poller + late-inject slot |

### 6.3 Cache lookup 性能驗證

**SLA 證明**：
- DashMap lookup amortized O(1)，p99 < 100ns（tokio docs benchmark）
- HashMap 單字段 read（u64 / f64）< 50ns
- 整條 `query_h_state(h, key)` 走 DashMap shard lookup + Clone HashMap value，**估 < 1μs**

✅ G2 達標（≤ 1ms hot-path）。

---

## §7 Python 端 hook 詳細

### 7.1 H1 ThoughtGate（`app/h1_thought_gate.py`）

```python
# 既有 check() function L98 - L98 加 invalidation hook
def check(self, intel: Any, stats: Dict[str, int]) -> bool:
    if not self._check_budget():
        stats["h1_budget_skip"] = stats.get("h1_budget_skip", 0) + 1
        invalidate_async("h1", "budget_skip")  # ← 新增
        return False
    if self.complexity_score(intel) < self._COMPLEXITY_THRESHOLD:
        stats["h1_complexity_skip"] = stats.get("h1_complexity_skip", 0) + 1
        invalidate_async("h1", "complexity_skip")  # ← 新增
        return False
    if not self._check_cooldown(intel):
        stats["h1_cooldown_skip"] = stats.get("h1_cooldown_skip", 0) + 1
        invalidate_async("h1", "cooldown_skip")  # ← 新增
        return False
    return True

# 新增 method（純讀，無業務邏輯）
def get_h1_stats_snapshot(self) -> Dict[str, int]:
    return {
        "cooldown_dict_size": len(self._h1_cooldown),
        # 其他 stats 由 caller 從 self._stats 補
    }
```

### 7.2 H2 / H5 Layer2CostTracker（`app/layer2_cost_tracker.py`）

```python
# record_claude_cost L227 後 _sync_to_rust_budget 旁邊 + 1 行
def record_claude_cost(self, ...) -> float:
    ...
    self._sync_to_rust_budget(...)  # 既有
    invalidate_async("h5", "claude_call")  # ← 新增
    invalidate_async("h2", "budget_consumed")  # ← 新增（H2 = same tracker）
    return cost

# 新增 snapshot method
def get_h2_budget_snapshot(self) -> dict:
    allowed, remaining = self.check_daily_budget()
    return {
        "daily_remaining_usd": remaining,
        "hard_cap_usd": self._config.daily_hard_cap_usd,
        "adaptive_multiplier": self._adaptive.multiplier,
    }

def get_h5_cost_snapshot(self) -> dict:
    return self.get_cost_edge_ratio()  # 既有 method 回傳完整 dict
```

### 7.3 H3 ModelRouter / H4 validator / 5-Agent

每個加 1-3 個 invalidation 點 + 1 個 `get_*_stats_snapshot()` 方法。Phase 計劃見 §9。

### 7.4 strategy_wiring.py 接線

```python
# strategy_wiring.py 末尾加（對齊 ExecutorConfigCache pattern）
if os.environ.get("OPENCLAW_H_STATE_GATEWAY") == "1":
    from .h_state_invalidator import init_invalidator_singleton
    init_invalidator_singleton()
    logger.info("H State Gateway enabled / H 狀態橋接器啟用")
```

---

## §8 安全 + 風險

### 8.1 硬邊界守護（CLAUDE.md §四）

| 邊界 | 影響 | 守護 |
|---|---|---|
| `live_execution_allowed` | 不觸碰 | H state 純 observability |
| `max_retries=0` | 不觸碰 | invalidate_async fire-and-forget，無 retry |
| `system_mode` | 不觸碰 | 無寫入路徑 |
| `OPENCLAW_ALLOW_MAINNET` | 不觸碰 | 不影響 Rust mainnet gate |
| `authorization.json` | 不觸碰 | 不影響 5min re-verify |

### 8.2 16 根原則對照（CLAUDE.md §二）

| # | 原則 | 影響 | 措施 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | H state 純讀，無 order 路徑 |
| 2 | 讀寫分離 | ✅ | Rust 只讀，Python 寫 |
| 3 | AI 輸出 ≠ 命令 | ✅ | H state 不繞過 lease |
| 4 | 策略不繞風控 | ✅ | hot-path query 純 advisory |
| 5 | 生存 > 利潤 | ✅ | Python crash → Rust last good，trade path 不死 |
| 6 | 失敗默認收縮 | ✅ | DEFAULT-OFF + fail-closed default |
| 7 | 學習 ≠ 改寫 Live | ✅ | observability 不寫 RiskConfig |
| 8 | 交易可解釋 | ✅ | invalidate_async log 留痕 |
| 9 | 災難保護 | ✅ | Rust 不依賴 Python alive |
| 10 | 認知誠實 | ✅ | staleness flag 標記 |
| 11 | Agent 最大自主權 | 中性 | H state 不限制能力 |
| 12 | 持續進化 | ✅ | 學習平面不受影響 |
| 13 | AI 成本感知 | ⭐ | **G3-08 解阻 G3-09 cost_edge_ratio** |
| 14 | 零外部成本可運行 | ✅ | DEFAULT-OFF，L0/L1 不需 |
| 15 | 多 Agent 協作 | ⭐ | **5-Agent → Rust 觀測通道** |
| 16 | 組合級風險 | ✅ | observability extension only |

### 8.3 Top 3 風險

#### 風險 1：IPC poll 競態（10s daemon 與 invalidation hint 重疊）
**機制**：daemon 正 poll 中 Python 推 invalidate → Rust 收到時 daemon 還在跑 → 結果 backlog 兩次 poll
**影響**：低（只是多一次 poll，無正確性問題）
**緩解**：poller 用 `tokio::sync::watch` channel + dedup logic（30s 內兩次 invalidation 合併為一次 poll）

#### 風險 2：Python state_store 鎖競爭（多 worker uvicorn）
**機制**：4 worker 各自 STRATEGIST_AGENT 等 singleton 是 worker-local，不同 worker 數據不一致
**影響**：中（query_h_state_full 看到的是隨機某 worker 的 view）
**緩解**：Phase 1 接受不一致（純 advisory observability），Phase 4+ 評估「leader worker only」schema 變更（沿襲 EDGE-SCHEDULER-LEADER-1 flock pattern，commit `f32629c`）

#### 風險 3：Schema drift（Python 加新字段 Rust 沒解）
**機制**：Python 推送新字段 Rust serde 解到舊 struct 丟失
**影響**：低（observability 字段，丟失非致命）
**緩解**：AgentState `stats: HashMap<String, i64>` 動態 schema；H1-H5 用 `#[serde(default)]` 對未知字段；Rust release notes 記載 schema migration

### 8.4 Crash 韌性矩陣

| 場景 | Rust 行為 | Python 行為 |
|---|---|---|
| Rust 啟動時 cache 未 init | hot-path query return None，handler return uninitialized | invalidate_async 失敗 silent |
| Python crash | poll fail → log warn → 沿用 last good snapshot + staleness flag | n/a |
| IPC server 暫時不可用 | poll timeout 2s → 沿用 last good | invalidate_async fire-and-forget OK |
| schema 解碼失敗 | 跳過該 H module，其他正常 | n/a |
| `OPENCLAW_H_STATE_GATEWAY != 1` | poller 不啟動，slot None，所有 query return uninitialized | invalidator 不啟，所有 invalidate noop |

---

## §9 Phased Rollout（4 phase）

### Phase 1：IPC schema + Rust h_state_cache.rs sibling（基礎設施）

**範圍**：
- 新建 `rust/openclaw_engine/src/h_state_cache/{mod.rs, types.rs, poller.rs, tests.rs}`
- 新建 `rust/openclaw_engine/src/ipc_server/handlers/h_state.rs`
- 修改 `slots.rs` / `dispatch.rs` / `main_boot_tasks.rs`（新 slot + 3 IPC arms + env-gated spawn）
- 新建 `app/h_state_invalidator.py`（abstract invalidator + singleton）
- 新建 `app/h_state_query_handler.py`（聚合函式 stub）
- 新建 IPC reverse handler `query_h_state_full` 在 Python 端（FastAPI route + IPC server reverse channel）

**完成標準**：
- env=1 + `query_h_state_full` IPC 回傳空 dict（version=0）
- env=0 全 dormant（cargo test + pytest 綠）
- 12+ Rust unit tests（cache lookup / staleness / poller smoke）+ 17+ Python tests（invalidator threadsafe / IPC fire-and-forget / fail-closed default）

**工時**：3.5d（E1 一個並行做 Rust，另一個做 Python）+ E2 0.5d + E4 0.5d = **4.5d 全鏈**

**Rollback**：env=0 即關（無 schema migration、無業務影響）

### Phase 2：H1 ThoughtGate + H3 ModelRouter（最高量 query）

**範圍**：
- H1: `h1_thought_gate.py` 加 3 個 `invalidate_async("h1", ...)` + `get_h1_stats_snapshot()`
- H3: `model_router.py` 加 4 個 invalidation（每 tier 一個）+ `get_h3_route_stats_snapshot()`
- 修改 `h_state_query_handler.build_h_state_full_response` 加 H1/H3 聚合

**完成標準**：
- query_h_state_full 回傳 H1+H3 真實數據
- 24h dogfood：對比 Python state_store 與 Rust DashMap 數值一致（< 1% drift）
- staleness < 30s p99（healthcheck check）

**工時**：2d + E2/E4 0.5d 各 = **3d 全鏈**

**Rollback**：unset env，poll daemon 停 + 既有 strategist_agent.py invalidate 點變成 noop（已 wrapped in env check）

### Phase 3：H2 + H4 + H5 cost_logging（解阻 G3-09 cost_edge_ratio）

**範圍**：
- H2/H5: `layer2_cost_tracker.py` 加 invalidate at `record_claude_cost` / `record_search_cost` + 2 snapshot methods
- H4: `strategist_agent._ai_evaluate` line 944 invalidate at validate_ai_output 失敗點 + h4 stats snapshot
- 修改 `build_h_state_full_response` 加 H2/H4/H5

**完成標準**：
- `cost_edge_ratio` 透過 IPC `query_h_state_full` Rust 端可讀
- G3-09 unblocked（Rust 端 paper_pnl_7d / ai_spend_7d 可即時讀）

**工時**：2.5d + E2/E4 各 0.5d = **3.5d 全鏈**

**Rollback**：unset env

### Phase 4：5-Agent state events（Strategist / Guardian / Analyst / Executor / Scout）

**範圍**：
- 5 Agent 各加 1 個 `get_stats_snapshot()` method（純讀 self._stats）
- 加 invalidate at intel_received / intent_produced / order_submitted（Strategist + Guardian + Executor 高頻變化點各 1）
- 修改 `build_h_state_full_response` 加 agents

**完成標準**：
- query_h_state_full 回傳 5-Agent 完整 stats
- G8-01 認知自適應 e2e 測試 unblocked（Rust fixture 可讀 5-Agent observability）
- 24h dogfood：strategist intel_evaluated count drift < 1%

**工時**：3d + E2/E4 各 0.5d = **4d 全鏈**

**Rollback**：unset env

### 9.1 Phased 工時總計

| Phase | E1 | E2 | E4 | 全鏈 |
|---|---|---|---|---|
| Phase 1 | 3.5d | 0.5d | 0.5d | **4.5d** |
| Phase 2 | 2d | 0.5d | 0.5d | **3d** |
| Phase 3 | 2.5d | 0.5d | 0.5d | **3.5d** |
| Phase 4 | 3d | 0.5d | 0.5d | **4d** |
| **合計** | 11d | 2d | 2d | **15d** |

並行折扣：Phase 1 Rust + Python 兩 E1 同步可省 1.5d → **實際 13.5d wall-clock**。

---

## §10 E1 工作 prompt template

### 10.1 Phase 1 prompt（給 PM 派發 E1 用）

```
## 任務：G3-08 Phase 1 — H State Gateway 基礎設施

### Sub-task A（Rust E1，可獨立並行）：
1. 新建 rust/openclaw_engine/src/h_state_cache/{mod.rs, types.rs, poller.rs, tests.rs}
2. 新建 rust/openclaw_engine/src/ipc_server/handlers/h_state.rs（3 handler）
3. 修改 ipc_server/{slots.rs, dispatch.rs} 加 HStateCacheSlot + 3 method arms
4. 修改 main_boot_tasks.rs env-gate 條件 spawn poller
5. 12+ unit tests（cache lookup / staleness > 30s / poller smoke / invalidation channel）
6. cargo test --release -p openclaw_engine --lib 必綠

### Sub-task B（Python E1，可獨立並行 A）：
1. 新建 app/h_state_invalidator.py（threadsafe + env-gated + fire-and-forget）
2. 新建 app/h_state_query_handler.py（聚合函式 stub，Phase 1 只回空 dict）
3. 新增 reverse IPC route `query_h_state_full`（路由層 + handler）
4. 17+ pytest（singleton dedup / env-gate / fail-closed / IPC mock）

### Sub-task C（接線，串行 A + B 完成後）：
1. strategy_wiring.py 加 init_invalidator_singleton() 條件 spawn
2. CLAUDE.md §九 singleton table 加 _H_STATE_INVALIDATOR + HStateCacheSlot
3. 新 healthcheck check_h_state_gateway_freshness（passive_wait_healthcheck.py）

### 完成標準：
- OPENCLAW_H_STATE_GATEWAY=1 + query_h_state_full IPC return version=0 空 dict
- OPENCLAW_H_STATE_GATEWAY=0 zero overhead（grep poll daemon spawn 條件、無 invalidate ）
- cargo test 綠 + pytest 綠 + healthcheck 加新 check（[20] check_h_state_gateway_freshness）

### 不要做：
- 不接 H1-H5 + 5-Agent（留 Phase 2-4）
- 不寫實際 stats snapshot 內容（Phase 2-4 個別接）
- 不影響既有 ExecutorConfigCache（pattern 鏡射但物理隔離）

### 副作用警示：
- main_boot_tasks.rs 改動 = startup sequence 改動，必須 cargo test integration tests 重跑
- ipc_server/dispatch.rs 接近 §九 1200 line cap（當前 572，加 3 arm + 1 import 預估 +30，仍安全）
```

### 10.2 Phase 2/3/4 prompt template（簡化版，PA 派發時填參數）

```
## 任務：G3-08 Phase {N} — {H_modules}

### 範圍：
- 修改：{file_list}
- 新增 invalidate_async hook：{count} 個
- 新增 get_*_snapshot() method：{count} 個
- 修改 build_h_state_full_response 加 {modules}

### 完成標準：
- query_h_state_full 回傳 {modules} 真實數據
- 24h dogfood：Python stats vs Rust DashMap 數值一致（drift < 1%）
- staleness check [20]: < 30s p99

### 不要做：
- 不改業務邏輯（純讀 self._stats / self._cooldown 等）
- 不影響 H 模組原有 advisory-only 行為
```

---

## §11 工時估算

### 11.1 Phase-by-Phase 全鏈工時

| Phase | Rust E1 | Python E1 | 串行接線 | E2 | E4 | 全鏈 wall-clock | 備註 |
|---|---|---|---|---|---|---|---|
| Phase 1 | 3d | 2.5d | 0.5d | 0.5d | 0.5d | **4.5d**（Rust+Py 並行） | 基礎設施 |
| Phase 2 | n/a | 2d | n/a | 0.5d | 0.5d | **3d** | H1+H3 接 |
| Phase 3 | n/a | 2.5d | n/a | 0.5d | 0.5d | **3.5d** | H2+H4+H5 接 |
| Phase 4 | n/a | 3d | n/a | 0.5d | 0.5d | **4d** | 5-Agent 接 |

**合計 wall-clock**：~15d（並行折扣後 ~13.5d）

### 11.2 LOC 估

| 範疇 | LOC |
|---|---|
| Rust 新檔 | ~1050 |
| Rust 既有改 | ~80 |
| Python 新檔 | ~250 |
| Python hook + snapshot 5 H + 5 Agent | ~150 |
| Python tests | ~400 |
| Rust tests | ~250 |
| **合計** | **~2180** |

---

## §12 Unblock 路徑

| Ticket | 阻塞點 | G3-08 解法 |
|---|---|---|
| G3-09 cost_edge_ratio 演算法（P3） | Rust 端無 ai_spend_7d / paper_pnl_7d 即時讀 | Phase 3 完成後 Rust hot-path 可 query H5 |
| G8-01 認知自適應 e2e 測試（W3 deferred） | Rust fixture 看不到 Strategist intel_evaluated count | Phase 4 完成後 5-Agent stats 可從 Rust 讀 |
| 未來 GUI 統一健檢 dashboard | 跨進程 H 狀態聚合靠 GUI scrape | Phase 1 後 healthcheck 可單一 IPC 拉全部 |
| 未來 Layer 2 自主推理觀測（memory `project_layer2_agent_design`） | Rust 端無 Strategist L2 cache hit 統計 | Phase 2 H3 cache stats 可達 |

---

## §13 派發架構建議

### 13.1 Phase 1 並行 E1 派發

| 子任務 | E1 instance | isolation | 文件 | 工時 |
|---|---|---|---|---|
| Phase 1A Rust（新建 5 檔 + 改 5 檔） | E1-Alpha worktree A | 必須 isolation（多檔 + main_boot_tasks 接近 hot path） | rust/openclaw_engine/src/h_state_cache/* + ipc_server/* | 3d |
| Phase 1B Python（新建 2 檔 + 加 reverse IPC） | E1-Beta 主樹 | 主樹（純新檔） | app/h_state_invalidator.py + app/h_state_query_handler.py + IPC route | 2.5d |
| Phase 1C 接線（串行 A+B 完成後） | 主 agent 串行 | 主樹 | strategy_wiring.py + CLAUDE.md §九 + healthcheck | 0.5d |

並行折扣：A + B 同時跑 → wall-clock 3d；C 串行 0.5d → 全 implementation 3.5d；E2 0.5d + E4 0.5d = **4.5d 全鏈**

### 13.2 Phase 2-4 派發（順序）

每 Phase 一個 E1（Python only），主樹開工，**串行**避免聚合函式撞檔。E2/E4 跟跑。

### 13.3 撞檔風險矩陣

| 任務 | Isolation | 衝突風險 |
|---|---|---|
| Phase 1A Rust h_state_cache | **必 isolation** | 與 G5-FUP-IPC-MOD-SPLIT（已完）+ 任何 ipc_server 重構撞區 |
| Phase 1B Python | 主樹 | 純新檔，0 衝突 |
| Phase 2 H1+H3 | 主樹 | strategist_agent.py callsite 改動，與 G3-09 cost_edge_ratio 可能撞區 |
| Phase 3 H2+H4+H5 | 主樹 | layer2_cost_tracker.py 加 invalidate hook |
| Phase 4 5-Agent | 主樹 | 5 個 Agent 檔各加 1 method，0 業務邏輯衝突 |

---

## §14 E2 重點審查 Top 3

### 14.1 Phase 1 Rust H State Cache poller 競態

**審查點**：
- 10s daemon poll + invalidation hint 雙路徑是否會 race（DashMap 同時被讀+寫 不死鎖）
- `tokio::sync::watch` channel dedup logic 是否正確（30s 內 N 次 invalidate 是否合併）
- cancel token 終止時 daemon graceful shutdown 不 leak handle

**驗證**：cargo test loom-style concurrent stress test（multi-thread 1000 query + 100 push 不 panic）

### 14.2 Python invalidate_async 不阻塞 H 模組 hot-path

**審查點**：
- threading.Thread fire-and-forget 是否真不阻塞（vs asyncio.run 在某些情境會 block）
- IPC client connect timeout 設 2s 而非 default（非阻塞 daemon）
- 1000 invalidate/sec stress 不導致 thread leak

**驗證**：pytest stress test（thread count 監控 + invalidate 100k 次 < 30s 完成）

### 14.3 fail-closed default + DEFAULT-OFF env-gate

**審查點**：
- `OPENCLAW_H_STATE_GATEWAY=0` 時 `invalidate_async` 是 noop（不 spawn thread）
- `OPENCLAW_H_STATE_GATEWAY=0` 時 Rust poller 不 spawn（main_boot_tasks 不 set slot）
- env=1 但 IPC 暫時失敗時 Rust 沿用 last good snapshot（staleness flag 標）+ Python invalidate_async log warn 不 raise
- 16 根原則 #6 fail-closed 各路徑均覆蓋（grep `_DEFAULT_*` + `noop` + `silent`）

**驗證**：5 個 e2e 測試 = env on/off × IPC up/down × snapshot init/uninit 矩陣

---

## §15 PA 結論

### 15.1 推薦

**Option C 混合模型（cache + invalidation push）**，4 phase rollout，全鏈 wall-clock **~13.5 day**（Phase 1 Rust+Python 並行）。

### 15.2 立即行動

PM 看完此 design 後 **下次 session** 派發 Phase 1：
- E1-Alpha：Phase 1A Rust h_state_cache（worktree isolation） — 3d
- E1-Beta：Phase 1B Python invalidator + query_handler（主樹） — 2.5d
- 主 agent：Phase 1C 接線 + healthcheck（串行收尾） — 0.5d

### 15.3 待後續輪迴

- Phase 2 H1+H3 — wave 2 第二批
- Phase 3 H2+H4+H5 — wave 2 第三批（解阻 G3-09）
- Phase 4 5-Agent — wave 3 wave 啟動前（解阻 G8-01）

### 15.4 未動的事（E1/E2 領域）

- 不寫 Rust 任何實作代碼（h_state_cache 全留 E1 Phase 1A）
- 不寫 Python invalidator 實作（純 spec + prompt template）
- 不改 H1-H5 / 5-Agent 業務代碼（Phase 2-4 個別小改）
- 不 spawn sub-agent（純 PA design，主 agent 串行讀 + 寫）
- 不擴範圍到 G3-09 / G3-10 / G8-01（隔壁 ticket）

### 15.5 教訓備忘（為未來 PA 留）

- **「鏡射 G3-03 ExecutorConfigCache pattern」是反 pattern 命名**：流向相反（Python SSOT vs Rust SSOT），但 cache + poll + fail-closed default 三件套通用 — 未來 IPC bridge design 第一句先確定 SSOT 在哪邊
- **DashMap u64 atomic stats 是 Rust hot-path 觀測的標配**（已驗 G3-11 CycleCounters pattern），新增 H state cache 應沿用而非引新 lock-based concurrent struct
- **Phased rollout 必含 env-gate + DEFAULT-OFF**：G3-08 範圍大（~2180 LOC）若無 phase 切割易堵 Wave 2 主軸；env-gate 確保 wave 2 阻塞時可立即 unset 不影響其他工作流

---

## 附錄 A：Healthcheck 接線

新增 `helper_scripts/db/passive_wait_healthcheck.py` 中：

```python
def check_h_state_gateway_freshness() -> tuple[str, str]:
    """[20] H State Gateway 新鮮度（DEFAULT-OFF 時 PASS skip）"""
    if os.environ.get("OPENCLAW_H_STATE_GATEWAY") != "1":
        return "PASS", "H State Gateway disabled (env=0), skipping"
    # IPC: get_h_state_status
    status = ipc_call("get_h_state_status", {})
    if status.get("staleness_ms", 99999) > 30000:
        return "FAIL", f"staleness {status.get('staleness_ms')}ms > 30s threshold"
    poll_attempts = status.get("poll_attempts", 0)
    poll_failures = status.get("poll_failures", 0)
    fail_rate = poll_failures / max(poll_attempts, 1)
    if fail_rate > 0.10:
        return "WARN", f"poll fail rate {fail_rate:.2%} > 10%"
    return "PASS", f"version={status.get('version')} staleness={status.get('staleness_ms')}ms"
```

---

## 附錄 B：Schema 演化策略

未來 5-Agent 加新 stats 字段：
1. Python 端 `get_*_stats_snapshot()` 加 key
2. Rust 端 `AgentState.stats: HashMap<String, i64>` 自動接（無需 deploy）
3. 若加非 i64（例如 f64 或 Vec），需：
   - Rust 端加 `serde(default)` 新 field
   - phased deploy（先 Rust 後 Python，反之 fallback default）
   - 14 day grace period 後 require new field

---

**全文完。 next: PM dispatches E1 per Phase 1 prompt template (§10.1) — likely next session given 13.5d total estimate.**
