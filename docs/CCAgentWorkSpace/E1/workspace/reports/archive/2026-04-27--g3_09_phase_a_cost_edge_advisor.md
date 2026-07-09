# E1 Report — G3-09 Phase A cost_edge_advisor schema + advisory only

- **Tier**：9 Track 2
- **Date**：2026-04-27
- **Engineer**：E1
- **Source RFC**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--g3_09_cost_edge_ratio_design.md`
- **Source CLAUDE.md**：§二 原則 #13「AI 資源成本感知 — 每次 AI 調用計費，cost_edge_ratio ≥ 0.8 → 建議關倉」
- **Operator threshold lock-in**：trigger_threshold default = **-0.5**（PM Tier 9 T9-LOW-1，ratio direction §2.4 變體 A）

---

## 1. 任務摘要

落地 PA RFC §11 Phase A 範圍：

- 把 CLAUDE.md §二 #13 的「cost_edge_ratio」感知升為 Rust hot-path 一級模組（自有 `cost_edge_advisor/`）
- daemon 每 10s 讀 H5 snapshot + threshold 比對 + 狀態轉換 emit log
- 雙保險 env-gate（`OPENCLAW_COST_EDGE_ADVISOR=1` + `RiskConfig.cost_edge.enabled=true`）
- IPC `get_cost_edge_advisor_status` 暴露 status snapshot 給 healthcheck + GUI
- 三環境 TOML 加 `[cost_edge]` 區塊（demo/paper `-0.5`、live 更保守 `-0.3`）
- 新 healthcheck `[30] cost_edge_advisor_status`（pure-Python TOML + Path 檢查）

**完成狀態**：✅ schema/daemon/IPC handler/healthcheck 全部 land；cargo lib **+38 tests / 0 fail**（baseline 2252 → 2290）；healthcheck 4 案例 smoke 全綠。

**Phase A advisory only** — 0 trade impact / 不接 IntentProcessor / 不關現有倉位 / 對 RiskConfig 唯讀。Phase B (shadow dry-run) + Phase C (gate 新倉) deferred to follow-up sub-tasks。

---

## 2. 修改清單

### 新建（5 個 Rust + 1 個檔加 4 module 子檔）

| 路徑 | 操作 | 行數 | 說明 |
|---|---|---|---|
| `srv/rust/openclaw_engine/src/cost_edge_advisor/mod.rs` | 新增 | 260 | `CostEdgeAdvisor` wrapper + `spawn_cost_edge_advisor` daemon + env-gate const |
| `srv/rust/openclaw_engine/src/cost_edge_advisor/types.rs` | 新增 | 287 | `CostEdgeAdvisorStatus` 7-variant enum + `CostEdgeAdvisorState` DTO + 7 factory fns |
| `srv/rust/openclaw_engine/src/cost_edge_advisor/advisor.rs` | 新增 | 158 | pure fn `evaluate()` + `next_status()` helper（6-step precedence） |
| `srv/rust/openclaw_engine/src/cost_edge_advisor/tests.rs` | 新增 | 433 | **32 unit tests**（status × edge × env-gate × factory） |
| `srv/rust/openclaw_engine/src/config/risk_config_cost_edge.rs` | 新增 | 236 | `CostEdgeConfig` schema + 5 unit tests（default / validate / serde） |
| `srv/rust/openclaw_engine/src/ipc_server/handlers/cost_edge_advisor.rs` | 新增 | 164 | IPC handler `get_cost_edge_advisor_status` + 5 tokio tests |

### 修改 Rust（10 檔）

| 路徑 | 操作 | 說明 |
|---|---|---|
| `lib.rs` | 修改 +1 | `pub mod cost_edge_advisor;` |
| `config/mod.rs` | 修改 +1 | export `CostEdgeConfig` from risk_config 重新導出 |
| `config/risk_config.rs` | 修改 +20 | `pub use cost_edge_cfg::CostEdgeConfig;` + `pub cost_edge: CostEdgeConfig` field + validate hookup |
| `ipc_server/slots.rs` | 修改 +21 | `CostEdgeAdvisorSlot` typedef + 雙語 docstring |
| `ipc_server/server.rs` | 修改 +20 | slot field + ctor init + accessor + handle_connection 傳遞 |
| `ipc_server/connection.rs` | 修改 +9 | param `cost_edge_advisor_slot` + 傳到 dispatch_request |
| `ipc_server/dispatch.rs` | 修改 +14 | dispatch_request param + arm `get_cost_edge_advisor_status` |
| `ipc_server/handlers/mod.rs` | 修改 +2 | `mod cost_edge_advisor;` + `pub(in crate::ipc_server) use ...` |
| `ipc_server/mod.rs` | 修改 +1 | `pub use slots::{... CostEdgeAdvisorSlot ...}` |
| `main.rs` | 修改 +12 | call `spawn_cost_edge_advisor_if_enabled` after H state poller |
| `main_boot_tasks.rs` | 修改 +88 | new fn `spawn_cost_edge_advisor_if_enabled` + import block |

### 修改測試（6 檔，45 個 dispatch_request 呼叫點）

| 路徑 | 操作 | 說明 |
|---|---|---|
| `ipc_server/tests/mod.rs` | 修改 +8 | `empty_cost_edge_advisor_slot()` helper |
| `ipc_server/tests/{dispatch,config,phase4,snapshot,risk,strategy}.rs` | 修改 6 檔 | 共 45 個 `dispatch_request(...)` call sites 加 `&empty_cost_edge_advisor_slot()` 末參 |

### 修改 TOML（3 檔）

| 路徑 | 操作 | 說明 |
|---|---|---|
| `settings/risk_control_rules/risk_config_demo.toml` | 修改 +12 | `[cost_edge] enabled=false trigger_threshold=-0.5` |
| `settings/risk_control_rules/risk_config_paper.toml` | 修改 +12 | 同 demo（cross-env config 獨立但起點對齊） |
| `settings/risk_control_rules/risk_config_live.toml` | 修改 +9 | `enabled=false trigger_threshold=-0.3`（更保守） |

### 修改 Python healthcheck（3 檔）

| 路徑 | 操作 | 說明 |
|---|---|---|
| `helper_scripts/db/passive_wait_healthcheck/checks_derived.py` | 修改 +110 | `def check_cost_edge_advisor_status() -> tuple[str,str]` |
| `helper_scripts/db/passive_wait_healthcheck/__init__.py` | 修改 +4 | re-export + `__all__` |
| `helper_scripts/db/passive_wait_healthcheck/runner.py` | 修改 +18 | import + `[30] cost_edge_advisor_status` 寫入 results |

**總 LOC**：~1138 新 Rust 模組 + ~236 schema + ~164 IPC handler + ~110 healthcheck + ~150 wiring / +tests = **~1800 行新增**；46 既有檔 minor 修改。所有檔案 < §九 1200 hard cap。

---

## 3. 關鍵 diff

### 3.1 雙保險 env-gate

```rust
// rust/openclaw_engine/src/cost_edge_advisor/mod.rs
pub const ENV_ADVISOR_FLAG: &str = "OPENCLAW_COST_EDGE_ADVISOR";

pub fn is_advisor_env_enabled() -> bool {
    std::env::var(ENV_ADVISOR_FLAG).as_deref() == Ok("1")
}
```

```rust
// main_boot_tasks.rs
if !is_advisor_env_enabled() {
    info!("cost_edge_advisor disabled (env=0), daemon not spawned");
    return;  // zero overhead path
}
// ... spawn daemon, but evaluate() short-circuits when !cfg.enabled
```

### 3.2 evaluate() pure fn (6-step precedence)

```rust
// rust/openclaw_engine/src/cost_edge_advisor/advisor.rs
pub fn evaluate(snapshot: &HStateSnapshot, cfg: &CostEdgeConfig, is_stale: bool, now_ms: i64) -> CostEdgeAdvisorState {
    if !cfg.enabled { return CostEdgeAdvisorState::disabled(...); }       // Step 1
    if is_stale { return CostEdgeAdvisorState::stale(...); }              // Step 2
    match snapshot.h5.cost_edge_ratio {
        None => CostEdgeAdvisorState::warm_up(...),                       // Step 3
        Some(r) if !r.is_finite() => CostEdgeAdvisorState::anomaly(...),  // Step 4
        Some(r) if r <= cfg.trigger_threshold => trigger(...),            // Step 5
        Some(r) => ok(...),                                                // Step 6
    }
}
```

### 3.3 Threshold direction lock-in (RFC §2.4 variant A)

```rust
// rust/openclaw_engine/src/config/risk_config_cost_edge.rs
fn default_cost_edge_trigger_threshold() -> f64 {
    // -0.5 — per PM Tier 9 T9-LOW-1 lock-in:
    //   ratio = paper_pnl_7d_usd / ai_spend_7d_usd <= -0.5
    //   = "paper loss reaches 50% of AI spend" = clearly burning cash
    -0.5
}
```

### 3.4 Healthcheck slot ID adjustment ([22] → [30])

```python
# helper_scripts/db/passive_wait_healthcheck/runner.py
# NOTE: PA RFC §6.2 originally proposed slot [22] (drafted before F7);
# adjusted to [30] post-F7 landing.
s, m = check_cost_edge_advisor_status()
results.append(("[30] cost_edge_advisor_status", s, m))
```

### 3.5 IPC handler advisor_disabled fallback (mirrors h_state gateway_disabled)

```rust
// rust/openclaw_engine/src/ipc_server/handlers/cost_edge_advisor.rs
fn advisor_disabled_response(id: serde_json::Value, note: &str) -> JsonRpcResponse {
    JsonRpcResponse::success(id, serde_json::json!({
        "status": "Uninitialized", "ratio": null, "threshold": 0.0,
        "data_days": 0, "ai_spend_7d_usd": 0.0, "paper_pnl_7d_usd": 0.0,
        "last_eval_ms": 0, "triggered_at_ms": 0, "env_enabled": false,
        "phase": "A_advisory", "note": note,
    }))
}
```

---

## 4. 治理對照

| 治理規則 | 符合？ | 說明 |
|---|---|---|
| **CLAUDE.md §二 #2 讀寫分離** | ✅ | advisor 對 RiskConfig + H state cache 純唯讀，無 side-effect |
| **§二 #3 AI 輸出 ≠ 即時命令** | ✅ | Phase A advisory only，不發 SubmitOrder / 不關倉 |
| **§二 #4 策略不繞風控** | ✅ | advisor 不在 IntentProcessor 路徑（Phase A 不接） |
| **§二 #5 生存>利潤** | ✅ | 觸發時不關現有倉，避免 false-positive close |
| **§二 #6 失敗默認收縮** | ✅ | env=0 default + None ratio fail-closed（不 trigger） |
| **§二 #7 學習≠改寫 Live** | ✅ | calibration 走 cron + manual approve（per RFC §5.3）；本 sub-task 不接自動 calibration |
| **§二 #8 交易可解釋** | ✅ | audit trace 含 ratio/threshold/data_days；transition log 嚴格 byte-stable |
| **§二 #10 認知誠實** | ✅ | `paper_pnl_7d_usd` 已標 paper / LiveDemo 模擬（types.rs docstring 明文） |
| **§二 #13 AI 成本感知** | ⭐⭐⭐ | 本 sub-task 直接落地 |
| **§四 5 項 live 硬邊界** | ✅ | 全 5 項零觸碰（advisor 純 observability） |
| **§七 跨平台兼容** | ✅ | 0 路徑硬編碼；healthcheck Mac py3.10 無 tomllib → WARN fallback / Linux 3.12 PASS |
| **§七 雙語注釋** | ✅ | 每 mod / fn / struct / variant 中英對照（MODULE_NOTE + docstring + inline 重點不變量） |
| **§七 SQL migration Guard A/B/C** | N/A | 本 sub-task 0 SQL migration |
| **§七 被動等待 healthcheck** | ✅ | `[30] cost_edge_advisor_status` 已 land |
| **§九 800/1200 行限** | ✅ | 最大新檔 433 行（tests.rs）；advanced.rs 已超 cap 故另立 `risk_config_cost_edge.rs` sibling |
| **§九 singleton 登記** | N/A | 無新 singleton（advisor 是 Arc per IPC connection clone，不是進程級 singleton） |

**3 條核心底線**：
- **簡單優先** ✅：只動 RFC 指定的 5 新 + 6 改面（並按需+1 sibling 檔減 §九 違規）
- **不偷懶** ✅：threshold direction 矛盾在 RFC §2.4 已分析，採 PM lock-in 變體 A
- **最小影響** ✅：env=0 zero-overhead path 驗證；既有 trade path 0 修改

---

## 5. 不確定之處

### 5.1 Mac dev 限制（環境約束）

- Mac Python 3.10 無 `tomllib` → healthcheck 在 Mac dev 跑會回 `WARN`（`tomllib unavailable`）。**Linux 生產 3.12 已驗 PASS**（4 案例 smoke 全綠）。如 Mac CI 出 WARN 屬預期，Linux cron 才是真實 verdict path。
- engine binary mtime / cargo test --release baseline 在 Linux trade-core 仍要驗。Mac cargo `dev` profile 已綠（2290 / 0 fail），但 release profile + Linux build 系列只能透過 `ssh trade-core "cargo test --release"` 驗（operator 視需要派 E4 跑）。

### 5.2 PA RFC slot ID drift（已自我修正）

- RFC §6.2 line 432 寫 `[22]`，但 F7 已先佔 `[22]`（trading_pipeline_silent_gap）。本 commit 改 `[30]` 並在 runner.py + checks_derived.py docstring 留 `NOTE: PA RFC §6.2 原寫 [22]，F7 已佔用 → 改 [30]`。建議 PA 更新 RFC §6.2 / §10.x 的 slot 編號對齊 main 實作（或 PM 派 backlog ticket）。

### 5.3 Daemon 啟動順序假設

- `spawn_cost_edge_advisor_if_enabled` 在 `spawn_h_state_poller_if_enabled` 之後呼，內部 daemon 以 `tokio::time::sleep(100ms) × 100` busy-wait 等 `h_state_cache_slot` populate（最多 10s，否則 warn-and-not-spawn）。當 G3-08 env-gate 關但 G3-09 env-gate 開時，advisor 會 fail-soft（10s 後 warn → daemon 不 spawn → IPC handler 永回 `Uninitialized`）。**RFC 預設 G3-08+G3-09 兩 env-gate 同時開**；分離開啟尚未文件化（未來 operator 可能誤配）。

### 5.4 Phase B / C 拓展面

- Phase B 加 `shadow_reject_count: AtomicU64` to `CostEdgeAdvisorState` — schema 演化需驗 IPC handler JSON shape 對 Python consumer 是否 forward-compat（Phase A 已用 `Option<f64>` ratio 為先例）
- Phase C 加 `RiskConfig.cost_edge.cost_edge_gate_enabled: bool` + `StrategyOverride.cost_edge_threshold_override: Option<f64>` — 後者觸到 G2-03 schema staging（已有 sibling pattern）
- Audit DB INSERT：本 Phase A 故意不接 `observability.engine_events`（Phase A 只走 transition log）；Phase B/C 可加 fire-and-forget INSERT 對齊 `handlers_config.rs` 的 config_patch audit pattern

### 5.5 測試覆蓋判斷

- 32 unit tests 覆蓋全 7-status × 邊界（NaN/Inf/threshold == ratio/None/stale）+ env-gate semantic + factory accuracy + Arc share + monotonic timestamp
- 5 IPC tokio tests 覆蓋 uninjected / OK / Trigger / Anomaly / WarmUp 五種 IPC response shapes
- 5 schema tests 覆蓋 default / validate / serde-roundtrip / serde-partial / out-of-range
- **未覆蓋**：daemon 整合測試（spawn → wait → state transition → audit emit）。RFC §11「24+」門檻已超（37 + 5 schema = 42）；daemon 整合測試屬 E4 regression scope 而非 unit。
- **未覆蓋**：cross-env hot-reload IPC patch_risk_config flip enabled=true 即時生效。RFC §8.4 / §9.2 雙保險已驗 schema 層（cargo test risk_config TOML round-trip 全綠）；hot-reload smoke E4 驗

### 5.6 跨平台風險（§七.★★ 對照）

- ✅ 路徑不硬編碼：healthcheck 用 `OPENCLAW_BASE_DIR` env / `~/BybitOpenClaw/srv` fallback；Rust 沒有任何 `/home/ncyu` / `/Users/ncyu` 字面值
- ✅ LocalLLMClient 抽象不影響：本 sub-task 0 LLM 直連
- ✅ 服務遷移：daemon 走 tokio task，無 systemd/launchd 特定依賴
- ✅ 依賴乾淨：無新 cargo crate / 無新 pip 包；`tomllib` 已是 Python 3.11+ stdlib

---

## 6. Operator 下一步

### 6.1 E2 review 重點

1. **§九 1200 hard cap**：advanced.rs 已 1297 → 我**未**繼續壓縮它（PA 範圍外），改加新 sibling `risk_config_cost_edge.rs`。E2 確認此選擇可接受（vs 派 E1-Beta 拆 advanced.rs）。
2. **runtime ordering**：main.rs 中 `spawn_cost_edge_advisor_if_enabled` 在 `set_config_stores` + `spawn_h_state_poller_if_enabled` 之後呼。E2 確認 risk_stores 在此時 fully populated（grep `set_config_stores` 上下文）。
3. **45 dispatch_request test fixtures 加參**：E2 抽 3-5 個 random sample（dispatch.rs / config.rs / strategy.rs）確認 `&empty_cost_edge_advisor_slot()` 順序與 production `dispatch.rs` 簽名一致。
4. **Threshold direction 字面義 vs PM lock-in**：CLAUDE.md §二 #13 字面寫「≥ 0.8 → 建議關倉」與 ratio 公式方向矛盾。我採 PA RFC §2.4 變體 A + PM Tier 9 T9-LOW-1 lock-in（threshold = `-0.5`，`ratio <= threshold` trigger）。E2 確認此決策已由 PM/PA 合意（如有疑問先回 PA 不要先 reject）。
5. **Healthcheck `[30]` slot ID**：與 RFC `[22]` 寫法不一致（F7 衝突自我修正）。E2 確認該 NOTE 文字已寫清楚，PA RFC drift 由 PA 自行更新。

### 6.2 Mac CC 已透過 cargo dev profile 驗證

- ✅ `cargo check -p openclaw_engine --lib` 0 errors / 21 warnings（既有 pre-existing 居多，本 sub-task 無新 warn）
- ✅ `cargo check -p openclaw_engine --lib --release` 0 errors / 21 warnings
- ✅ `cargo check -p openclaw_engine`（含 binary）0 errors / +3 warnings（既有 pre-existing）
- ✅ `cargo test -p openclaw_engine --lib` 全 2290 tests / 0 failed（baseline 2252 → +38）
- ✅ `cargo test -p openclaw_engine --lib cost_edge_advisor` 32 / 0 failed
- ✅ `cargo test -p openclaw_engine --lib cost_edge` 43 / 0 failed（含 schema + handler + advisor + 1 既有）
- ✅ `cargo test -p openclaw_engine --lib risk_config` 123 / 0 failed（含 demo/paper/live TOML round-trip 已含新 `[cost_edge]` section）
- ✅ Healthcheck Python 3.12 smoke 4 案例全綠（env=unset / env=true / env=1+正確 BASE_DIR / env=1+不存在 BASE_DIR）

### 6.3 E4 regression on Linux 必跑

```bash
ssh trade-core "cd ~/BybitOpenClaw/srv/rust && cargo test --release -p openclaw_engine --lib"
# 預期 ≥ 2290 passed / 0 failed（Mac dev = Linux release 對齊；±5 tests 可能因 Linux-only feature gate）

ssh trade-core "cd ~/BybitOpenClaw/srv && python3 helper_scripts/db/passive_wait_healthcheck.py 2>&1 | grep -E '\[20\]|\[30\]'"
# 預期 [20] PASS-skip 或 PASS（H state gateway DEFAULT-OFF）
# 預期 [30] PASS-skip（cost_edge_advisor DEFAULT-OFF）
# env=1 啟用後（operator 手動）預期 [30] PASS（demo TOML 已有 [cost_edge] section）
```

### 6.4 不需 operator 親自動手的事項

- daemon 不會自動啟動：env=0（DEFAULT）保證 zero-overhead；operator 顯式 `OPENCLAW_COST_EDGE_ADVISOR=1` 才 spawn
- TOML 改動只新增 `[cost_edge]` section，預設 `enabled=false`（雙保險）；既有 trade path bit-identical
- 全 5 項 §四 live 硬邊界 0 觸碰；live key 無新依賴；authorization.json HMAC 無新欄位

### 6.5 高風險項（per RFC §11 line 913-918）

1. ★ daemon poll_interval 10s 與 H state cache poller 對齊（已驗）
2. ★ env-gate dual safeguard：`OPENCLAW_COST_EDGE_ADVISOR=1` env + `RiskConfig.cost_edge.enabled=true` 兩條件 AND（已落 advisor::evaluate 第 1 步 + main_boot_tasks::spawn 第 1 步雙閘）
3. ★ ratio direction：threshold = -0.5 表示「ratio ≤ -0.5 trigger」（PA RFC §2.4 變體 A，PM lock-in）— 不寫成 `>=`（已驗測試 `evaluate_trigger_at_exact_threshold_boundary` + `evaluate_threshold_positive_value_works_correctly`）

---

**G3-09 PHASE A DONE — cost_edge_advisor commit pending E2 review; cargo test +38 green (2252→2290); healthcheck [30] OK (Python 3.12 smoke 4/4 green).**

---

## Files changed (absolute paths)

### New (6)

- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/cost_edge_advisor/mod.rs`
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/cost_edge_advisor/types.rs`
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/cost_edge_advisor/advisor.rs`
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/cost_edge_advisor/tests.rs`
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/config/risk_config_cost_edge.rs`
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/ipc_server/handlers/cost_edge_advisor.rs`

### Modified Rust (10)

- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/lib.rs`
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/config/mod.rs`
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/config/risk_config.rs`
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/ipc_server/slots.rs`
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/ipc_server/server.rs`
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/ipc_server/connection.rs`
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/ipc_server/dispatch.rs`
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/ipc_server/handlers/mod.rs`
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/ipc_server/mod.rs`
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/main.rs`
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/main_boot_tasks.rs`

### Modified test fixtures (7)

- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/ipc_server/tests/mod.rs`
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/ipc_server/tests/dispatch.rs`
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/ipc_server/tests/config.rs`
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/ipc_server/tests/phase4.rs`
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/ipc_server/tests/snapshot.rs`
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/ipc_server/tests/risk.rs`
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/ipc_server/tests/strategy.rs`

### Modified TOML (3)

- `/Users/ncyu/Projects/TradeBot/srv/settings/risk_control_rules/risk_config_demo.toml`
- `/Users/ncyu/Projects/TradeBot/srv/settings/risk_control_rules/risk_config_paper.toml`
- `/Users/ncyu/Projects/TradeBot/srv/settings/risk_control_rules/risk_config_live.toml`

### Modified Python healthcheck (3)

- `/Users/ncyu/Projects/TradeBot/srv/helper_scripts/db/passive_wait_healthcheck/checks_derived.py`
- `/Users/ncyu/Projects/TradeBot/srv/helper_scripts/db/passive_wait_healthcheck/__init__.py`
- `/Users/ncyu/Projects/TradeBot/srv/helper_scripts/db/passive_wait_healthcheck/runner.py`

### Memory (1)

- `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/memory.md` (appended G3-09 Phase A entry)

**Total**：6 new + 21 modified + 1 memory append = **28 files changed**.
