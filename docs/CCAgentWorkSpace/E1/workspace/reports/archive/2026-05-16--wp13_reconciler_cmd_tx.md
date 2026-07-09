# E1 IMPL -- WP-13 Demo Reconciler Stale cmd_tx Fix (FA-P1-11)

**日期**：2026-05-16
**Agent**：E1 (Backend Developer)
**任務來源**：PA WP-13 派發（FA-P1-11 LIVE-RECONCILER-STALE-CMD-TX P1）
**對應檔案**：4 個 Rust 源檔

---

## 1. 任務摘要

Demo position reconciler 持有 `cmd_tx` by-value clone，若 demo pipeline
restart/rotate 後 reconciler 仍向舊 channel 發送命令。Live reconciler 已用
`ReconcilerCommandTxProvider` 閉包 + `LiveCmdSenderSlot` 間接讀取解決。本次
將同樣 pattern 套用到 demo，新增 `DemoCmdSenderSlot` type alias + slot 接線。

---

## 2. 修改清單

| 檔案 | LOC delta | 內容 |
|---|---|---|
| `ipc_server/engine_routing.rs` | +6 | 新增 `DemoCmdSenderSlot` type alias |
| `ipc_server/mod.rs` | +2 | re-export `DemoCmdSenderSlot` |
| `main.rs` | -6 (net) | 建立 `demo_cmd_slot` + mirror + 傳遞至 reconciler + 更新 TODO 注釋 |
| `main_boot_tasks.rs` | +2 (net) | 函數簽名改收 `&DemoCmdSenderSlot`；demo reconciler 改用 `spawn_position_reconciler_with_cmd_provider` |

---

## 3. 關鍵 diff

### engine_routing.rs -- 新 type alias
```rust
pub type DemoCmdSenderSlot =
    Arc<RwLock<Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>>>;
```

### main.rs -- slot 建立 + mirror
```rust
let demo_cmd_slot: DemoCmdSenderSlot = Arc::new(ParkingRwLock::new(None));
if let Some(ref tx) = demo_cmd_tx {
    *demo_cmd_slot.write() = Some(tx.clone());
}
```

### main_boot_tasks.rs -- demo reconciler 改用 provider 閉包
```rust
// 舊：
if let Some(ref tx) = demo_cmd_tx {
    tasks::spawn_position_reconciler(..., tx.clone(), ...);
}

// 新：
if let Some(ref demo_b) = demo_bindings {
    let slot = Arc::clone(demo_cmd_slot);
    let cmd_tx_provider: ReconcilerCommandTxProvider =
        Arc::new(move || slot.read().as_ref().cloned());
    tasks::spawn_position_reconciler_with_cmd_provider(..., cmd_tx_provider, ...);
}
```

---

## 4. 治理對照

| 規則 | 狀態 |
|---|---|
| 注釋默認中文 | PASS（新注釋全中文） |
| 不改 live reconciler | PASS（live 區塊零修改） |
| 不改 position_reconciler/mod.rs 業務邏輯 | PASS |
| cargo check 通過 | PASS（唯一新 warning: `spawn_position_reconciler` unused，因 demo 是其最後 call site） |
| 硬邊界（max_retries=0 等） | N/A（無涉） |
| 800 行警告 | main_boot_tasks.rs 858 行（改前 856，pre-existing > 800） |
| 2000 行硬上限 | main.rs 1439 / main_boot_tasks.rs 858（皆 PASS） |
| 跨平台兼容 | PASS（無路徑硬編碼） |

---

## 5. 不確定之處

- `spawn_position_reconciler`（by-value wrapper）現無 call site，產生 dead_code
  warning。Paper 預設關閉（OPENCLAW_ENABLE_PAPER=0）且無 reconciler，若未來
  需要可復用此 wrapper 或將其標 `#[allow(dead_code)]` / 移除。屬 P2 清理。
- `spawn_edge_estimates_reloader_if_enabled` 和 `spawn_strategist_scheduler`
  也接收 `demo_cmd_tx` by-value，同樣有 stale 風險但不在本 PA scope。
- Demo pipeline 目前 boot-time 固定不 respawn（無 DemoAuthWatcher），所以
  stale 問題實務上只在手動 restart 時觸發。Slot pattern 是預防性修正。

---

## 6. Operator 下一步

- 等 E2 審查 + E4 回歸通過
- PM 決定是否統一 commit + push
- 若部署到 Linux，需 `--rebuild` 重建 engine binary
