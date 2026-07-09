# P1-5 A2 — Cross-Restart Drawdown Continuity · Implementation Worklog

**日期 / Date:** 2026-04-20
**範圍 / Scope:** TODO §P1-5 (DEMO-REBOOT-PNL-RESET-1 方案 A2)
**狀態 / Status:** 實作完成、測試綠 — 待 `--rebuild` 部署
**里程碑 / Milestone:** P1-5 A2 · Python↔Rust 全鏈路
**相關文件 / Related:**
`project_p06_rca_and_fix_plan.md`、`feedback_env_config_independence.md`（三環境風控獨立原則）

---

## 一、問題陳述 / Problem Statement

**Root bug (TODO §P1-5 DEMO-REBOOT-PNL-RESET-1):**
Rust `PaperState.peak_balance` 只活在記憶體，引擎每次重啟後回退到 `balance`
（通過 `apply_restored_counters` 從 `trading.fills` 回放）。
結果 — **operator 觸發的重啟可繞過 25% drawdown 斷路器**：當 session 已跌破
baseline 時，只要重啟一次引擎，`peak_balance = balance` 立即歸一，
`drawdown_pct = 0`，Guardian 的 `drawdown_breach` 檢查形同虛設。

**Root Principles 觸犯（pre-fix）：**
- #5 生存 > 利潤 — 斷路器可被重啟洗掉
- #6 失敗默認收縮 — 重啟本應 fail-closed，實際 fail-open
- #8 交易可解釋 — 無審計記錄、無法重建 drawdown 歷史

---

## 二、方案決策 / Design Decision

### 選項回顧
| 選項 | 描述 | 拒絕理由 |
|---|---|---|
| A — 不修 | 繼續用記憶體 | 觸犯根原則 #5/#6/#8 |
| B — 改存 Python PAPER_STORE | DEDUP-PY-RUST 後 Python 已非權威 | 反架構 |
| **A+A2 ✅** | 持久化 peak_balance 到 DB；**僅 operator IPC 手動重置** | 符合根原則 fail-closed |
| A+A1 | 持久化 + 重啟自動重置 | 仍可被重啟洗 drawdown，等於沒修 |

**Operator decision sequence:** `A` → `A2`
- `A`：peak_balance 上 DB（跨重啟不丟）
- `A2`：重置語義僅 operator IPC + FastAPI 手動觸發，**永不自動**

### A2 語義要點
1. 重啟 → 讀 checkpoint（若有）→ `peak = max(stored, current)` 保留較高者
2. 重啟 → **永不降** peak_balance（fail-closed）
3. Operator 通過 IPC/REST 手動觸發 → `peak = balance` 且 DELETE DB row
4. 所有 reset 事件寫 `change_audit_log` STATE_CHANGE（根原則 #8）

---

## 三、實作細節 / Implementation

### A. DB Schema — `V018__paper_state_checkpoint.sql`

```sql
CREATE TABLE IF NOT EXISTS trading.paper_state_checkpoint (
    engine_mode      TEXT PRIMARY KEY,            -- paper|demo|live|live_demo
    peak_balance     DOUBLE PRECISION NOT NULL,
    session_start_ts TIMESTAMPTZ NOT NULL,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT ... CHECK (engine_mode IN ('paper','demo','live','live_demo')),
    CONSTRAINT ... CHECK (peak_balance >= 0)
);
```

設計選擇：
- PK = engine_mode，最多 4 rows（paper/demo/live/live_demo）
- **非 hypertable**（無時間維度）→ 無 TimescaleDB UNIQUE index 限制
- `DOUBLE PRECISION` 對齊 `PaperState.balance` f64
- Idempotent — 可重跑

### B. Rust 層

**1. `paper_state/checkpoint.rs`（新檔，~110 行）**
```rust
pub(crate) async fn load_checkpoint(pool, em)  -> Option<(f64, u64)>
pub(crate) async fn write_checkpoint(pool, em, peak, ts_ms) -> Result<()>
pub(crate) async fn delete_checkpoint(pool, em) -> Result<()>
```
- `load` 用 `EXTRACT(EPOCH FROM ...) * 1000` 保留亞秒精度
- `write` `INSERT ... ON CONFLICT (engine_mode) DO UPDATE` UPSERT
- 全部 `pub(crate)` + 雙語 docstring

**2. `paper_state/accessor.rs`（新增 4 方法）**
```rust
pub fn peak_balance(&self) -> f64
pub fn session_start_ts_ms(&self) -> u64
pub(crate) fn restore_checkpoint(&mut self, peak, ts_ms)   // NaN/inf reject
pub fn reset_drawdown_baseline(&mut self)                  // peak=balance, forced_drawdown=0
```

**關鍵 invariant — `restore_checkpoint` clamp direction：**
```rust
self.peak_balance = peak.max(self.peak_balance);
// ^ 取 (stored, current_replayed) 較高者
//   A. checkpoint peak > replayed balance → 保留歷史高水位（不降 peak）
//   B. checkpoint peak < replayed balance（post-checkpoint fills）→ 用 replay 值
```

**3. `event_consumer/paper_state_restore.rs`（restore path 新增）**
- `apply_restored_counters` 之後追加 `load_checkpoint` → `restore_checkpoint`
- cold start (Ok(None)) + 讀失敗 (Err) 均 fail-soft

**4. `event_consumer/mod.rs`（寫入路徑 + IPC 攔截）**
- StateWriter cadence 內 `tokio::spawn` detached UPSERT（hot path，fire-and-forget）
- IPC `ResetDrawdownBaseline` 在 dispatch loop 中攔截：
  - 先執行記憶體 `reset_drawdown_baseline`
  - 再 `await delete_checkpoint`（確保 DB DELETE 完成再回應）
  - 回應 oneshot 成功後強制 snapshot
  - 任何環節失敗 → 回應 Err，操作未完成

**5. `tick_pipeline/mod.rs`（PipelineCommand 新變體）**
```rust
ResetDrawdownBaseline {
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
}
```

**6. `ipc_server/handlers/risk.rs` + `ipc_server/mod.rs`**
- `handle_reset_drawdown_baseline` — 5s timeout，傳 PipelineCommand，轉發結果
- IPC method `"reset_drawdown_baseline"` 通過 `extract_engine_tx` 路由

### C. Python 層

**1. `risk_view_client.py` — 新 method：**
```python
async def reset_drawdown_baseline(self, engine: str) -> dict[str, Any]:
    # 呼叫 Rust IPC reset_drawdown_baseline 並傳 engine param
    resp = await self._ipc.call("reset_drawdown_baseline", {"engine": engine})
    await self.refresh_runtime_status()
    return resp
```

**2. `risk_routes.py` — 新 route `POST /api/v1/paper/risk/reset-drawdown-baseline`：**
- Pydantic `ResetDrawdownBaselineRequest` — engine + reason 均 required
- Operator role gate（duck-typed，同 governance_routes 模式）
- Engine whitelist（`paper|demo|live`，防 IPC 注入）
- **`_record_reset_drawdown_audit` helper：**
  - Lazy import `_get_governance_hub`（避免循環）
  - hub / `_change_audit_log` 缺席 → WARN（fail-soft，Rust DB DELETE 已完成）
  - `record_change(ChangeType.STATE_CHANGE, who=actor.actor_id, what=..., reason=..., affected_components=["paper_state:{engine}", "trading.paper_state_checkpoint"], auto_approve=True)`
  - `record_change` 本身拋錯 → WARN，不影響 route 回應
- IPC 失敗 → HTTP 500（`rust_engine_unavailable`，絕不假成功）

---

## 四、測試 / Tests

### Rust（engine lib：**1640 passed / 0 failed**，+11 vs baseline 1629）
`rust/openclaw_engine/src/paper_state/tests.rs` 新增 **9 個 P1-5 測試**：

| 測試 | 驗證內容 |
|---|---|
| `p1_5_peak_balance_and_session_start_accessors_return_new_defaults` | 新欄位默認值 |
| `p1_5_restore_checkpoint_raises_peak_above_current` | 高 checkpoint 被採納 |
| `p1_5_restore_checkpoint_does_not_lower_current_peak` | clamp 絕不降 peak |
| `p1_5_restore_checkpoint_rejects_nan_and_inf` | NaN/±inf 被拒 |
| `p1_5_restore_checkpoint_absorbs_negative_peak` | 負值被 clamp guard 吸收 |
| `p1_5_reset_drawdown_baseline_equalises_peak_to_balance` | peak=balance, drawdown=0 |
| `p1_5_reset_drawdown_baseline_clears_forced_drawdown` | forced_drawdown 歸零 |
| `p1_5_reset_drawdown_baseline_does_not_touch_positions_or_pnl` | scope guard（vs PipelineCommand::Reset） |
| `p1_5_drawdown_breach_persists_across_apply_restored_counters_plus_checkpoint` | E2E：drawdown breach 跨重啟不被洗 |

### Python client（`test_risk_view_client.py`：**21 passed**，+4）
- `test_reset_drawdown_baseline_sends_engine_param` — engine 參數必須傳到 Rust
- `test_reset_drawdown_baseline_distinct_engines_route_independently` — paper/demo/live 各自路由
- `test_reset_drawdown_baseline_no_ipc_returns_empty` — 無 IPC fail-soft
- `test_reset_drawdown_baseline_ipc_error_propagates` — IPC 錯誤必須拋回

### Python route（`test_reset_drawdown_route.py`：**8 passed**，新檔）
- `test_invalid_engine_returns_400` — 非白名單 engine 在觸達 IPC 前 400
- `test_non_operator_returns_403` — viewer role 403
- `test_unauthenticated_actor_returns_401` — 缺 roles/actor_id 401
- `test_happy_path_writes_state_change_audit` — 成功 reset 寫 STATE_CHANGE 審計
- `test_audit_helper_no_hub_is_soft` — hub 缺席 WARN + 不拋錯
- `test_audit_helper_hub_without_log_is_soft` — change_audit_log=None WARN + 不拋錯
- `test_audit_helper_record_change_raising_is_soft` — record_change 拋錯 WARN + route 仍成功
- `test_ipc_error_surfaces_as_500` — IPC 失敗 HTTP 500 且**無審計行**（未發生的重置絕不留記錄）

### 全量回歸
- Engine lib：1640 passed / 0 failed（+11）
- control_api_v1 pytest：2511 passed / 2 pre-existing DYNAMIC-RISK fail / 20 skipped
- 無新增 regression

---

## 五、部署 / Deployment

### 步驟
```bash
# 1. 部署 V018 migration（idempotent，可重跑）
source settings/environment_files/basic_system_services.env
bash helper_scripts/db/deploy_V018.sh

# 2. 重啟引擎 + API（加載 Rust checkpoint writer/reader 與新 IPC handler）
bash helper_scripts/restart_all.sh --rebuild
```

### 部署驗證
- Migration audit log 位於 `trading_services/logs/v018_deploy_*.log`
- Engine log grep `restored peak_balance` 確認 restore path 走通（有 checkpoint 時）
- GUI / curl 觸發 `POST /api/v1/paper/risk/reset-drawdown-baseline` 測 happy path
- `trading.change_audit_log` 應看到對應 STATE_CHANGE 條目
- `trading.paper_state_checkpoint` 應有 ≤4 rows

### Rollback（緊急，**僅在尚無寫入時**）
```sql
DROP TABLE IF EXISTS trading.paper_state_checkpoint;
```
Rust 端 load_checkpoint 對 Err 是 fail-soft（WARN），故 DROP 後引擎不會 crash，
只會回退到「memory-only peak_balance」（即 pre-P1-5 行為）。

---

## 六、根原則對照 / Root Principles

| 原則 | 實作映射 |
|---|---|
| **#5 生存 > 利潤** | peak_balance 持久化 + 重啟不降 → drawdown 斷路器不可被重啟洗掉 |
| **#6 失敗默認收縮** | Restore fail-soft（WARN 不 crash）+ `restore_checkpoint` clamp 絕不降 peak |
| **#8 交易可解釋** | 每次 operator 重置均寫 `change_audit_log` STATE_CHANGE；route 先寫審計再返回 |
| **#11 Agent 最大自主權（P0/P1 硬邊界內）** | Agent 永遠無權重置 drawdown；**僅 operator role + IPC + REST** |

---

## 七、後續事項 / Follow-ups

1. **21d demo 觀察（TODO §P0-2 LG-1）** — V018 部署後 session_start_ts 重新起算，
   但現行 PID 1364222 已啟動數小時，重啟後時鐘歸零屬預期。
2. **GUI Wiring** — 目前只有 REST endpoint，GUI 側尚未接按鈕。操作員可通過 curl/postman 觸發。
3. **Live 路徑驗證** — `live` engine channel 在 live_demo endpoint 下也命中；
   IPC `engine=live` 即可覆蓋 LiveDemo（見 `feedback_live_no_degradation_by_endpoint.md`）。
4. **Checkpoint write 失敗監控** — `tokio::spawn` detached 後，WARN log 是唯一
   可觀察信號；下一步可加 counter metric（P2）。

---

## 八、Commit Plan

```
fix(engine): P1-5 A2 cross-restart drawdown continuity + operator reset endpoint

- Rust: new paper_state::checkpoint (load/write/delete); PaperState.restore_checkpoint + reset_drawdown_baseline; event_consumer hot-path UPSERT + IPC ResetDrawdownBaseline with DB DELETE; ipc_server reset_drawdown_baseline method
- DB: V018 trading.paper_state_checkpoint (PK=engine_mode, ≤4 rows, non-hypertable)
- Python: RiskViewClient.reset_drawdown_baseline; POST /api/v1/paper/risk/reset-drawdown-baseline (operator-only, engine whitelist, change_audit_log STATE_CHANGE, fail-soft audit + fail-closed IPC)
- Tests: +9 Rust (1629→1640) / +4 client / +8 route
- Deploy: helper_scripts/db/deploy_V018.sh (idempotent)

Root Principles: #5 生存>利潤 · #6 失敗默認收縮 · #8 交易可解釋
```
