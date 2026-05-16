# E1 IMPL -- WP-13 Leftover P1 Fix (FA-P1-11 補修)

**日期**：2026-05-16
**Agent**：E1 (Backend Developer)
**任務來源**：PM E2 retroactive review Round 4 RETURN (WP-13 partial fix marked complete = governance transparency 違反)
**對應檔案**：5 個 Rust 源檔
**Prior context**：`2026-05-16--wp13_reconciler_cmd_tx.md`（WP-13 demo reconciler slot 接線）

---

## 1. 任務摘要

WP-13 commit body 暗示 FA-P1-11 全完，但實際 2 個 callsite 仍 by-value 接 demo `cmd_tx`，有 pipeline restart 後 stale 風險：

| Callsite | 函數 | 原語意 |
|---|---|---|
| `main.rs:822` | `spawn_strategist_scheduler` | 接 `&Option<UnboundedSender>`，傳 by-value 給 `StrategistScheduler::new` 儲存在 `tune_cmd_tx` field |
| `main.rs:1372` | `spawn_edge_estimates_reloader_if_enabled` | 接 `Option<UnboundedSender>` by-value，loop 內持有並 dispatch |

擴 `DemoCmdSenderSlot` pattern 至兩處，與 WP-13 demo reconciler 共用既有 `demo_cmd_slot`（main.rs:429 已建）。Pipeline restart 後兩個 daemon 自動拿到新 cmd_tx，不需 respawn。

---

## 2. 修改清單

| 檔案 | LOC delta | 內容 |
|---|---|---|
| `rust/openclaw_engine/src/main.rs` | +14 | 兩 callsite 加 `&demo_cmd_slot` / `Some(Arc::clone(&demo_cmd_slot))` + 雙語注釋 |
| `rust/openclaw_engine/src/main_boot_tasks.rs` | +104 (含新測 3 個 + 雙語注釋) | `spawn_strategist_scheduler` 簽名 +1 arg；`spawn_edge_estimates_reloader_if_enabled` 簽名改 demo arg 為 slot；helper `try_send_reload_from_demo_slot` 新；3 新測 (`manual_trigger_reads_demo_slot_dynamically` + 2 unit) |
| `rust/openclaw_engine/src/strategist_scheduler/mod.rs` | +35 | `tune_cmd_slot` field 新；`with_tune_cmd_slot` builder 新；`tune_cmd_snapshot()` pub(crate) helper 新；對齊 `promote_cmd_*` pattern |
| `rust/openclaw_engine/src/strategist_scheduler/evaluate.rs` | +9 -3 | 3 處 `self.tune_cmd_tx.send(...)` → `self.tune_cmd_snapshot().send(...)` + 雙語注釋 |
| `rust/openclaw_engine/src/strategist_scheduler/tests.rs` | +71 | 2 新 regression tests（slot 動態切換 + slot 缺 fallback）|

**未動**（按 PA restriction）：
- demo reconciler（WP-13 已修）
- live reconciler（屬 LIVE-RECONCILER-STALE-CMD-TX 範圍）
- main.rs:1211 demo pipeline spawn 本身（cmd_tx 屬該 pipeline 擁有，非 stale 源）
- main.rs:430/450 demo_cmd_tx 與 engine_cmd_channels.demo（基礎構造）
- paper 路徑（PA 明文不擴 scope；paper 預設關 + 無 paper slot 基礎設施）

---

## 3. 關鍵 diff

### strategist_scheduler/mod.rs — 新 slot field + builder + snapshot helper

```rust
// 新 imports
use crate::ipc_server::{DemoCmdSenderSlot, LiveCmdSenderSlot};

// 新 field
pub struct StrategistScheduler {
    // ...
    promote_cmd_slot: Option<LiveCmdSenderSlot>,
    /// WP-13-LEFTOVER-1：tune-target 管線 sender slot。生產注入 demo_cmd_slot。
    tune_cmd_slot: Option<DemoCmdSenderSlot>,
    // ...
}

// 新 builder（對齊 with_promote_cmd_slot）
pub fn with_tune_cmd_slot(mut self, tune_cmd_slot: DemoCmdSenderSlot) -> Self {
    self.tune_cmd_slot = Some(tune_cmd_slot);
    self
}

// 新 helper（對齊 promote_cmd_snapshot）
pub(crate) fn tune_cmd_snapshot(&self) -> UnboundedSender<PipelineCommand> {
    if let Some(slot) = &self.tune_cmd_slot {
        if let Some(guard) = slot.try_read() {
            if let Some(tx) = guard.as_ref() {
                return tx.clone();
            }
        } else {
            debug!("StrategistScheduler::tune_cmd_snapshot: demo slot read contention ...");
        }
    }
    self.tune_cmd_tx.clone()  // fallback：owned boot-time sender 永遠存在
}
```

### strategist_scheduler/evaluate.rs — 3 處改 snapshot

```rust
// 舊
self.tune_cmd_tx.send(PipelineCommand::GetStrategyParams { ... })?;
// 新
self.tune_cmd_snapshot().send(PipelineCommand::GetStrategyParams { ... })?;
```

### main_boot_tasks.rs — `spawn_strategist_scheduler` 簽名 + 接線

```rust
pub(crate) async fn spawn_strategist_scheduler(
    db_pool: &Arc<DbPool>,
    cancel: &CancellationToken,
    demo_cmd_tx: &Option<UnboundedSender<PipelineCommand>>,
    demo_cmd_slot: &DemoCmdSenderSlot,   // ← 新 arg
    live_cmd_slot: &LiveCmdSenderSlot,
    risk_stores: &PerEngineRiskStores,
) -> Option<...> {
    // ...
    let scheduler = Arc::new(
        StrategistScheduler::new(ai_client, demo_tx.clone(), Demo, None, db_pool, cancel)
            .with_promote_cmd_slot(Arc::clone(live_cmd_slot))
            .with_tune_cmd_slot(Arc::clone(demo_cmd_slot))   // ← 新接線
            .with_risk_store(Arc::clone(&risk_stores.demo)),
    );
}
```

### main_boot_tasks.rs — `spawn_edge_estimates_reloader_if_enabled` 簽名

```rust
pub(crate) fn spawn_edge_estimates_reloader_if_enabled(
    paper_cmd_tx: Option<UnboundedSender<PipelineCommand>>,
    demo_cmd_slot: Option<DemoCmdSenderSlot>,         // ← 由 by-value 改 slot
    live_cmd_slot: Option<LiveCmdSenderSlot>,
    cancel: &CancellationToken,
) -> Option<Sender<()>> { ... }

// 新 dispatch helper
fn try_send_reload_from_demo_slot(demo_cmd_slot: &Option<DemoCmdSenderSlot>) -> bool {
    let Some(slot) = demo_cmd_slot.as_ref() else { return false; };
    let tx = slot.read().clone();
    try_send_reload(&tx, "demo")
}
```

### main.rs — 兩 callsite 接 slot

```rust
// callsite 822 (strategist)
let strategist_counters = main_boot_tasks::spawn_strategist_scheduler(
    &db_pool, &cancel,
    &demo_cmd_tx,
    &demo_cmd_slot,           // ← 新 arg（reuse WP-13 既有 slot）
    &live_cmd_slot,
    &risk_stores,
).await;

// callsite 1372 (edge reloader)
let edge_reload_signal_tx = main_boot_tasks::spawn_edge_estimates_reloader_if_enabled(
    Some(paper_cmd_tx.clone()),
    Some(Arc::clone(&demo_cmd_slot)),    // ← 由 demo_cmd_tx.clone() 改 slot
    Some(Arc::clone(&live_cmd_slot)),
    &cancel,
);
```

---

## 4. 治理對照

| 規則 | 狀態 |
|---|---|
| 注釋默認中文（2026-05-05 規） | PASS（新注釋全中文，inline 雙語僅 doc-block 上方延續既有風格） |
| 不擴 PA scope | PASS（不動 live reconciler / paper 路徑 / WP-13 已修檔的非相關 block） |
| 硬邊界（max_retries / live_execution_allowed / execution_authority / system_mode） | PASS（grep 0 hit） |
| 跨平台兼容 | PASS（無 `/home/ncyu` `/Users/<name>` 硬編碼，grep 0 hit） |
| SQL migration | N/A（無 schema 改動） |
| Singleton 表登記 §九 | 不增新 singleton；`DemoCmdSenderSlot` 已於 WP-13 登記，本 fix 純擴用 |
| 被動等待 healthcheck | N/A（純結構修正，無新被動等待） |
| 800 行警告 / 2000 行硬上限 | main.rs 1448 / main_boot_tasks.rs 962 / tests.rs 937（皆超 800 警告 pre-existing，遠未達 2000 硬上限） |
| `cargo check --release` | PASS（3 個 warning 全 pre-existing：LEAD_WINDOW_SECS_MAIN / ma_crossover::make_intent / spawn_position_reconciler dead — 後者為 WP-13 ack 過的 P2 清理項） |
| `cargo test --release --lib` | PASS 2908 / 0 FAIL（含新增 2 strategist regression test） |
| `cargo test --release --bin openclaw-engine` | PASS 62 / 0 FAIL（含新增 3 edge_reload regression test）|
| `rustfmt --check` 改的 5 個檔 | PASS（tests.rs apply 過一次後 clean；其他 4 檔本來 clean；startup/mod.rs pre-existing rustfmt drift 不在本次 scope）|

### 新測試清單（5 個）

1. `main_boot_tasks::edge_reload_tests::manual_trigger_reads_demo_slot_dynamically` — 證明 daemon 啟動時 demo slot 為 None，之後注入新 sender，trigger 後新 sender 收到 ReloadEdgeEstimates（非 boot 值捕獲）
2. `main_boot_tasks::edge_reload_tests::try_send_reload_from_demo_slot_returns_false_when_unbound` — slot=None fail-safe
3. `main_boot_tasks::edge_reload_tests::try_send_reload_from_demo_slot_returns_false_when_inner_none` — slot=Some 但內層 None fail-safe
4. `strategist_scheduler::tests::test_tune_cmd_snapshot_reads_latest_demo_slot` — 證明 slot rotation 後 snapshot 回新 sender，舊 channel 不收命令
5. `strategist_scheduler::tests::test_tune_cmd_snapshot_fallbacks_to_owned_when_slot_absent` — 缺 slot 時 fallback 到 owned tune_cmd_tx

---

## 5. 不確定之處

- Demo pipeline 目前 boot-time 固定不 respawn（無 DemoAuthWatcher），所以 stale 問題只在手動 restart / 未來加 DemoAuthWatcher 時觸發。本次修正是 **預防性 + governance transparency 對齊**：避免 commit body 暗示「全完」實則 partial 的治理失真。
- `tune_cmd_snapshot()` 的 fallback 邏輯與 `promote_cmd_snapshot()` 細微不同：promote 是 `Option<UnboundedSender>`（live 可能完全未綁，需 None 表達），tune 是 `UnboundedSender`（demo 必綁，故 owned `tune_cmd_tx` 永遠存在作為 unwrap-safe fallback）。這與 ctor 契約一致（demo 未綁則 scheduler 整個不 spawn）。
- Paper 路徑保留 by-value：(a) PA 明文不擴 scope；(b) paper 預設關 (`OPENCLAW_ENABLE_PAPER=0`)；(c) 無 paper slot 基礎設施。若未來啟 paper 並加 watcher，需另開 ticket。
- Edge reloader 中 `tx.send()` 若 channel 已關回 false log warn 後繼續跑（fail-soft），對齊既有 pattern。

---

## 6. Operator 下一步

- 等 E2 代碼審查
- E4 回歸測試（重點：strategist 5 min cycle 真實跑、demo restart 後 edge reload trigger）
- PM 統一 commit + push（不單獨 commit，遵 CLAUDE.md §七 強制鏈 E1→E2→E4→QA→PM）
- 部署到 Linux 需 `--rebuild` 重建 engine binary（CLAUDE.md §六）
- WP-13 dead code warning `spawn_position_reconciler`（pre-existing P2）仍存在，本次未清；若 PM 要在同 commit 處理可加 `#[allow(dead_code)]` 或移除（非本任務 scope）
