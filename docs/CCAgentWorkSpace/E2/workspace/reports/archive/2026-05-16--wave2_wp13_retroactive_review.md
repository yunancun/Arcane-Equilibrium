# E2 Retroactive Adversarial Review — Wave 3 WP-13 Demo Reconciler DemoCmdSenderSlot

**對象**：commit `f31b6e8f` 內 `rust/openclaw_engine/src/main.rs` + `main_boot_tasks.rs` + `ipc_server/mod.rs` + `ipc_server/engine_routing.rs`
**Scope**：FA-P1-11 LIVE-RECONCILER-STALE-CMD-TX P1 — Demo reconciler 改用 `DemoCmdSenderSlot` 透過 provider 間接讀取 cmd_tx，避免 stale by-value 捕獲
**Review 模式**：retroactive — commit body self-claim 「E2 PASS」0 真實 dispatch
**Verdict**：**RETURN to E1 → leftover P1 補修後 PASS to E4** · 0 BLOCKER / 0 HIGH / 1 HIGH / 1 MEDIUM / 1 LOW

---

## 一、改動範圍 vs PA 方案核對

### Scope claim
1. 新增 `DemoCmdSenderSlot = Arc<RwLock<Option<UnboundedSender<PipelineCommand>>>>` type alias
2. main.rs 構造 `demo_cmd_slot` 並寫入 boot-time `demo_cmd_tx`
3. `spawn_position_reconcilers` 簽名改 `demo_cmd_tx` → `demo_cmd_slot`
4. demo reconciler 用 `spawn_position_reconciler_with_cmd_provider` 而非 `spawn_position_reconciler`（對齊 live pattern）

### Diff 實測
- `engine_routing.rs:55-60` 新 `DemoCmdSenderSlot` type alias ✅
- `ipc_server/mod.rs:73-75` re-export ✅
- `main_boot_tasks.rs:24-25` import `DemoCmdSenderSlot` ✅
- `main_boot_tasks.rs:83-84` 簽名改 `demo_cmd_tx: &Option<...>` → `demo_cmd_slot: &DemoCmdSenderSlot` ✅
- `main_boot_tasks.rs:120-137` reconciler closure 改用 `Arc::clone(demo_cmd_slot)` + cmd_tx_provider ✅
- `main.rs:427-432` 新增 `demo_cmd_slot` 構造 + 寫入 boot tx ✅
- `main.rs:801` `spawn_position_reconcilers` call 改傳 `&demo_cmd_slot` ✅

✅ Claim 與 diff 一致；對齊 live reconciler pattern（同 `LiveCmdSenderSlot`）。

---

## 二、Root cause 分析（對抗視角）

**Root cause**：reconciler tokio task spawn 時用 closure capture `tx.clone()` by-value；若 demo pipeline 重啟產生新 cmd channel，reconciler 仍持舊 sender → 發 SetEdgePredictorShadow / RestartPipeline cmd 走 dead channel → silent dropped。Demo pipeline 目前 boot-time 固定不 respawn，但**FA-P1-11 ticket 預期未來 demo 也支援動態重啟**。

✅ 改用 slot + provider pattern 是正確 root-cause fix（不寫死 tx，每次需要 sender 時透過 slot read 取最新）。

---

## 三、**HIGH** — Leftover P1 by-value cmd_tx 路徑未修

### 對抗 grep 結果

```bash
# main.rs by-value demo_cmd_tx callsite
grep -n 'demo_cmd_tx' rust/openclaw_engine/src/main.rs
```

實測 leftover：
- **main.rs:822** `spawn_strategist_scheduler(&db_pool, &cancel, &demo_cmd_tx, &live_cmd_slot, &risk_stores)` — 仍傳 `&demo_cmd_tx`（by-reference to original Option<UnboundedSender>）
- **main.rs:1372** `spawn_edge_estimates_reloader_if_enabled(Some(paper_cmd_tx.clone()), demo_cmd_tx.clone(), Some(Arc::clone(&live_cmd_slot)), &cancel)` — 仍 `demo_cmd_tx.clone()` by-value

### 問題分析

WP-13 commit message body 自承「Live / Demo reconciler 已透過 slot 間接讀取 cmd_tx（WP-13 FA-P1-11 修正）」但**只修了 reconciler**；同 ticket scope 的另外兩個 by-value caller：
1. `strategist_scheduler` (main.rs:822) — 每 strategist evaluation cycle 必發 SetParam 等 cmd 到 demo
2. `edge_estimates_reloader` (main.rs:1372) — F6 PH5-WIRE-1 RELOAD daemon 接 IPC `reload_edge_estimates` 發 cmd 到 demo

若未來 demo pipeline 動態 respawn（FA-P1-11 ticket 預期場景），這兩個 daemon 仍持舊 tx → silent dead。

### 對抗反問
1. 「FA-P1-11 ticket 原 scope 範圍：grep `LIVE-RECONCILER-STALE-CMD-TX` 在 main.rs 文檔出現幾次？」
   - 答：main.rs 兩處註釋（line 824 之上 + line 1288 之上）顯示 ticket 預期 scope 涵蓋 **all by-value cmd_tx captures**，不只 reconciler
2. 「WP-13 修了 reconciler 但 commit body 把 ticket marked done — 這跟 LG-1 T3 PA mitigation 假設不成立 同型反模式（部分修了當全修）」
3. 「strategist_scheduler + edge_estimates_reloader 兩 daemon 是否 demo respawn 路徑會觸？memory 提示 demo respawn 是 P2 / future scope — 即 WP-13 scope cut acceptable，但 commit body 必明標『FA-P1-11 部分修；strategist_scheduler + edge_estimates_reloader 留 P2』」

### 嚴重性 = HIGH

治理 partial fix marked as complete：
- WP-13 commit message body line "Live / Demo reconciler 已透過 slot 間接讀取 cmd_tx（WP-13 FA-P1-11 修正）" 暗示 FA-P1-11 已修
- 但 leftover main.rs:822 + main.rs:1372 仍 by-value，與 FA-P1-11 ticket 原 scope 矛盾
- chain breach + partial-fix-marked-complete = 雙重治理破裂

### 建議修法

**選 A（治理乾淨）**：
1. 修改 commit `f31b6e8f` body 的 WP-13 自陳述為「FA-P1-11 reconciler 子任務完成；strategist_scheduler (main.rs:822) + edge_estimates_reloader (main.rs:1372) 留 follow-up P1-WP13-LEFTOVER-1」
2. 同 Wave 開新 ticket P1-WP13-LEFTOVER-1：spawn_strategist_scheduler + spawn_edge_estimates_reloader_if_enabled 簽名都改接 `DemoCmdSenderSlot`；對齊本 wave 模式

**選 B（一次性收口）**：本 wave 補修 strategist_scheduler + edge_estimates_reloader 兩處 — 但這超出原 WP-13 commit scope，需新 commit

E2 建議 = **選 A**（不擴 wave scope，但治理 transparency 必補正）

---

## 四、其他 finding

### MEDIUM — DemoCmdSenderSlot 構造後 demo_cmd_tx **同時被** Mirror 與 by-value capture（雙路活躍）

**位置**：main.rs:425-432

**內容**：
```rust
let demo_cmd_slot: DemoCmdSenderSlot = Arc::new(ParkingRwLock::new(None));
if let Some(ref tx) = demo_cmd_tx {
    *demo_cmd_slot.write() = Some(tx.clone());
}
```

**問題**：`demo_cmd_tx` 仍是原 `Option<UnboundedSender>`，後續 strategist_scheduler / edge_estimates_reloader 仍引用它（line 822 / 1372）；slot 是 mirror 副本。

**風險**：未來若 demo pipeline 動態 respawn，**slot 會被更新但原 demo_cmd_tx by-value 副本仍舊** → 兩條路徑 diverge → 不一致

**對抗反問**：「Slot pattern 的意義是『所有 caller 透過 slot 取最新 tx』；保留 by-value capture 等於 partial migration —**未來 respawn 時 reconciler 看新 sender，scheduler 看舊 sender，行為不一致**」

**建議**：與 HIGH 一起修 — strategist_scheduler + edge_estimates_reloader 全改 slot；本 wave 不修則 commit body 必明標「partial migration」

**嚴重性**：MEDIUM — 真實 demo respawn 路徑目前不存在（demo boot-time 固定），但設計上的 partial-state 是治理 risk。

### LOW — `Arc<ParkingRwLock<Option<...>>>` 對齊 live pattern 但 demo 永不寫入（demo 不 rotate）→ 純 boilerplate

**位置**：main.rs:427-432 + main_boot_tasks.rs:103
**內容**：demo slot 構造 + boot-time 寫入後**永不再寫**（因 demo 不像 live 有 LiveAuthWatcher 動態替換 cmd_tx）；slot 純結構對齊。
**對抗反問**：「為什麼 demo 也用 slot pattern 如果不會 rotate？」
**答**：FA-P1-11 ticket 預期未來 demo 動態重啟；提前準備 infra。Acceptable 為「forward-prep boilerplate」。
**建議**：commit body 或註釋明標「demo slot 是 forward-prep；當前 boot-time fixed」。
**嚴重性**：LOW — 不阻 deploy；setup cost vs future benefit trade-off acceptable。

---

## 五、對抗 7 checklist

| Item | Verdict |
|---|---|
| 1. Root cause vs 表面 patch | ⚠️ 部分修了 root cause（reconciler）；另 2 by-value caller 未修 — partial fix |
| 2. Lexical scope shadow | ✅ `demo_cmd_slot` / `demo_cmd_tx` 命名分明，無 shadow |
| 3. Race condition | ✅ `ParkingRwLock` read 是 lock-free fast path；reconciler closure 每 reconcile cycle 重讀 slot 是 safe pattern |
| 4. Backward compat | ✅ 簽名改動是 internal helper，無外部 caller 用 `spawn_position_reconcilers` raw |
| 5. Perf regression | ✅ 每 reconcile cycle 多 1 RwLock read（ns 級）；可忽略 |
| 6. Test 強度 | ⚠️ 無 unit test 驗 slot pattern 與 by-value 對比（reconciler 在 respawn 場景拿正確 tx）— 但這需 integration test framework，超出 scope |
| 7. Comment / citation accuracy | ⚠️ commit body 自陳述「Live / Demo reconciler 已透過 slot 間接讀取 cmd_tx（WP-13 FA-P1-11 修正）」隱晦暗示 FA-P1-11 已完成 — 是 HIGH issue |
| 8. §九 singleton 表 | ⚠️ **DemoCmdSenderSlot 新增 type alias，§九 singleton 表是否需登記**？grep §九 表確認 LiveCmdSenderSlot 已登記為「Live command sender slot」；DemoCmdSenderSlot 同型應補登記 |
| 9. 跨檔影響面 | ⚠️ 詳「Leftover P1」HIGH |
| 10. 新引入 issue | HIGH 1 / MEDIUM 1 / LOW 1 + §九 singleton 補登記 |

---

## 六、Findings 補充

### §九 Singleton 表補登記
**位置**：CLAUDE.md §九 Singleton 表（line ~830 區附近）
**內容**：應加 row：
```
| `DemoCmdSenderSlot` | rust/openclaw_engine/src/ipc_server/engine_routing.rs | Wave 3 WP-13 FA-P1-11：對齊 LiveCmdSenderSlot pattern；demo 目前 boot-time 固定，slot 是 forward-prep；reconciler 透過 provider closure 間接讀取 |
```
**建議**：meta-doc commit 加 row（與 P2 ticket 一起處理，per E2 Wave 2.2 lesson 6 同型）

---

## 七、結論

**RETURN to E1 → leftover P1 補修 + commit body amend** · 0 BLOCKER / 1 HIGH / 1 MEDIUM / 1 LOW

WP-13 reconciler 修正本身正確（slot + provider pattern 對齊 live），但**partial fix marked as complete** 是 chain breach 延伸治理問題。

### Pushback（必修）
1. **HIGH** — commit body amend 明標「WP-13 修 reconciler 子任務；strategist_scheduler (main.rs:822) + edge_estimates_reloader (main.rs:1372) 仍 by-value capture」+ 開 follow-up ticket `P1-WP13-LEFTOVER-1`
2. **MEDIUM** — 與 HIGH 一起：mod_boot_tasks 對 strategist_scheduler / edge_estimates_reloader 補 slot pattern 或同 ticket scope 留

### Follow-up
- **LOW** — demo slot 註釋明標「forward-prep boilerplate」
- **§九 singleton 表** — DemoCmdSenderSlot 補登記（meta-doc commit）

### Retroactive caveat
commit `f31b6e8f` 自承「E2 PASS」0 真實 E2 dispatch。本 retroactive verdict RETURN，理由：
- HIGH partial fix mark complete 是治理透明度問題（chain breach 衍生）
- 必修才能 PASS to E4（防止 E4 在以為「FA-P1-11 全修完」狀態下做 regression）
