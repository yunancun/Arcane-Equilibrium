# ADR — PIPELINE-SLOT-1：Authorization-Fail Scoping 與 Live Hot-Respawn

**Date**: 2026-04-19
**Status**: Accepted
**Supersedes**: 2026-04-14 Fix 3 crash-only parity（scope 已收斂）
**Related commits**: `3005fc0`（Phase 1）· `e28f3d8`（Phase 2）· `d92f25d`（Phase 3）
**Phase 4 scope**: Threaded-offload FUP + Python pytest + 本 ADR + CLAUDE.md/TODO.md 同步

---

## 情境（Context）

PIPELINE-SLOT-1 Phase 2 改變了 authorization.json 在會話中途失效時引擎的
行為：

- **Before**：`authorization.rs::verify_*()` 失敗觸發 engine-wide `auth_cancel`
  → 整個 engine（paper + demo + live）一起 shutdown；operator 必須執行
  `restart_all.sh` 才能恢復，且 demo + paper 的中場狀態（已開倉、KlineManager
  歷史、Orchestrator 信號計數器）全部重來。

- **After**：僅 live slot 被 teardown；demo + paper 照常交易。Operator 透過
  GUI 重新 renew 後，live 在 ≤5 秒內自動 respawn（Phase 3 `LiveAuthWatcher`
  5 秒輪詢 + Phase 3 IPC `trigger_live_auth_recheck` fast path + Phase 4
  daemon-thread offload 讓 HTTP 回應不被 IPC 拖累）。

此 ADR 記錄這個範圍收斂（scope narrowing）+ hot-respawn 設計的四個決策
（D1-D4），以及明確拒絕的四條替代路徑。

---

## 決策（Decisions）

### D1：Auth-fail scope 從 engine-wide 收斂到 live-only

**決策**：authorization.json 失效（missing / expired / signature mismatch /
env_allowed mismatch）只 teardown live pipeline slot；demo 與 paper slot 保持
運行。

**理由**：

1. **Root Principle #5「生存 > 利潤」** 是關於「避免螺旋崩潰」，而非「出錯
   就把所有活動一起殺掉」。Live auth 過期不代表 demo 風控壞了 — demo/paper
   根本不讀 authorization.json，兩者與 live 的關連是共用 engine binary 進程，
   不是 logical 依賴。把 demo/paper 一起拉下來屬於 unnecessary 破壞。

2. **Operator 負擔** — engine-wide shutdown 後 operator 必須重跑
   `restart_all.sh`，這在 live 階段每日 renew 流程中會重複發生；
   一勞永逸（Phase 2 Plan A 的明確目標）。

3. **事實上的物理層隔離** — Phase 1 `PipelineSlot` 抽象已讓 slot 之間互不
   持有共享 mutable 狀態（`KlineManager` / `Orchestrator` / `StopManager`
   per-slot），teardown 一個 slot 不會污染其他 slot 的 working set。

**實作**：`pipeline_slot.rs::try_spawn` / `teardown` 1-slot-at-a-time；
`live_auth_watcher.rs` 只對 `SlotKind::Live` 下 teardown 命令。

### D2：Crash-only parity（2026-04-14 Fix 3）PARTIALLY preserved

**決策**：
- **Live OS thread panic** → engine-wide cancel（2026-04-14 Fix 3 原設計保留）。
- **Auth expiry / file missing / sig mismatch** → 只 teardown live，不觸發
  engine-wide cancel（D1）。

**理由**：這是兩種本質不同的失敗：
- **Panic** 表示 Rust 已進入未知狀態腐蝕（unknown state corruption），無法區
  分腐蝕範圍是否跨 slot；fail-closed 殺整個進程是 2026-04-14 Fix 3 的保守
  正解。
- **Auth expiry** 是 recoverable via operator action 的計畫內事件（operator
  點 renew 即可），它表達的是「授權狀態變化」而非「程序腐蝕」，範圍自然只到
  live。

D2 是 D1 的小字條款：「範圍收斂，但危險 failure mode 的全殺語義不動」。

### D3：Restart-kind 區分 manual vs unattended

**決策**：引入 `restart_kind.rs` sentinel 機制：
- `restart_all.sh` atomic write `/tmp/openclaw/restart_kind.manual` →
  engine 讀一次即刪 → treats next boot as **manual**（operator 有意介入，
  應 reset 中場狀態）。
- 無 sentinel → 視為 **unattended**（crash / auto-reboot / watchdog 拉
  回來），應 **persist** 中場狀態（不重置 drawdown 計數、不重置 KlineManager
  冷起時間、不重置 Orchestrator cooldown）。

**理由**：operator intent 語義區分：
- **Manual restart** ≈ operator 主動想乾淨開始（換 config、部署新 binary、
  clear 狀態）→ reset 是正確的。
- **Unattended restart** ≈ 機器抖了一下 → 中場狀態（例如已經進入縮倉模式、
  已經暫停某策略）應保留，否則 watchdog 拉回來就無限循環進入/退出同一個
  安全狀態。

**實作**：Phase 1 commit `3005fc0`；`restart_all.sh` atomic rename → sentinel
read+delete 於 `main.rs` 啟動序列頭部。

### D4：NO Rust-side governance state persistence

**決策**：**拒絕** 在 Rust 側寫 governance / circuit-breaker / freeze-state
snapshot file。

**替代理由**：
1. **Python earned_trust_state.json 已 persist** live auth ladder（MW-RELOAD-1，
   2026-04-19 commit `e0e68fc`）— authorization tier 與 TTL 已落地。
2. **ConfigStore TOML persist** 所有 trading / risk / learning / budget
   config — 參數層已持久化。
3. **Postgres persist** positions / verdicts / fills / decision_features —
   歷史與當前持倉已持久化。
4. **In-memory freeze state 刻意 ephemeral** — 如果 crash 發生在「已凍結」
   狀態（例如 GovernanceHub 自動凍結），auto-resume 為凍結狀態 **可能 compound
   the issue**（例如 freeze 是因為一個已經修復的 transient，卻因為 snapshot
   把系統鎖死）。Fresh boot defaults 是 safer。
5. **Phase 4 ADR 留門**：若未來某個 specific requirement 出現（例如「要跨
   crash 保留某個 circuit-breaker trip 狀態」），則針對那個 specific state
   加 targeted serialization，不做 general governance hub snapshot。

---

## 後果（Consequences）

### Positive

- **Auth expiry 不再干擾 demo/paper**：operator renew 流程不再附帶「副作用：
  把 demo/paper 中場狀態重置」的代價。
- **Live respawn ≤5 秒**：renew 點擊到 live pipeline 重新接 WS + 接 order
  router 的時間從「手動 restart_all.sh 全程」（~60-120s）降到 ≤5 秒（Phase 3
  watcher 5s poll），或 <100ms（Phase 3 IPC fast path）。
- **Exponential backoff**：Phase 2 `spawn_backoff.rs` (1s → 60s) 防止 live
  spawn 一直失敗（例如 Bybit API 持續 5xx）時對 exchange 發射 spawn-failure
  storm。
- **HTTP UX**：Phase 4 threaded offload 讓 operator 的 renew/revoke HTTP
  回應不再被 IPC 同步調用拖累（最差 1.5s）。

### Negative / open

- **Live slot teardown mid-trade 可能留下 in-flight orders**。此風險由既有
  `position_reconciler` 在下次 spawn 時的對帳 cycle 覆蓋（EX-04 邊界已設計
  處理此 case）。非 Phase 2 新增風險，只是現在觸發頻率上升。
- **Live respawn 狀態開新**：respawn 後沒有 pre-teardown 策略決策記憶
  （例如 orchestrator 的 last-signal-at 計數器）。Acceptable，因為 (a) 策略
  是 stateless function（ConfigStore 持有參數），(b) in-memory 計數器
  （cooldown / last-signal）短時間重建即可（一個 tick 就補齊）。

---

## Code references

- `rust/openclaw_engine/src/pipeline_slot.rs` — `SlotKind` / `PipelineSlot` /
  `try_spawn` / `teardown`（Phase 1 `3005fc0`）
- `rust/openclaw_engine/src/live_auth_watcher.rs` — 4-branch state machine
  （NotRunning / ShouldRun / AuthChanged / ShouldTeardown）、`SpawnOp` trait、
  5s poll loop（Phase 3 `d92f25d`）
- `rust/openclaw_engine/src/spawn_backoff.rs` — 1s → 60s exponential backoff
  （Phase 2 `e28f3d8`）
- `rust/openclaw_engine/src/main.rs` — watcher spawn、shutdown teardown
  sequence、Fix 3 preservation（panic → engine-wide cancel）
- `rust/openclaw_engine/src/restart_kind.rs` — sentinel read+delete + manual/
  unattended 分類（Phase 1 `3005fc0`）
- `helper_scripts/restart_all.sh` — atomic sentinel write（Phase 1 `3005fc0`）
- `program_code/.../app/live_trust_routes.py::_trigger_live_auth_recheck_fire_and_forget()`
  — Python daemon-thread offload（Phase 3 加入；Phase 4 threaded-offload 收尾）
- `program_code/.../tests/test_live_auth_recheck_trigger.py` — Phase 4 pytest
  （8 tests：4 contract + 3 call-site integration + 1 HTTP failure isolation）

---

## 考慮過的替代路徑（Alternatives considered）

- **Route B：engine auto-restart on auth fail**。Rejected：heavy-handed，為了
  重新拉 live 把 demo/paper 一起殺，違反 D1 motivation。
- **Route C：operator 手動跑 restart_all.sh post-renew**。Rejected：每次
  renewal 都要手動一次，非「一勞永逸」，且新部署後每日 renew 都要介入。
- **保留 engine-wide auth_cancel 不變**。Rejected：違反 D1 motivation
  （demo/paper 無辜受罰）。
- **Rust snapshot governance state across crashes**。Rejected：見 D4 五點。
