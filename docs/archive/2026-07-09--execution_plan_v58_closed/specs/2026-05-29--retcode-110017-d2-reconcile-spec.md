> ⚠️ 归档历史文档 — 非当前权威。active 状态见 repo 根 `TODO.md`；本文件仅供历史/审计参考。（2026-07-18 审计批量补入）

# P2-110017-D2-RECONCILE-QTY-GT-ZERO-DRIFT — PA design spec

- 日期：2026-05-29
- 作者：PA（design only；未 IMPL，未 ssh 寫）
- 風險等級：**高**（跨「本地倉 truth ↔ exchange truth」收斂；誤刪真倉 = 災難。Root Principle 5/9）
- chain：PA spec（本檔）→ E1 IMPL → BB review（exchange truth 信任邊界）→ E2 → E4 → PM
- 前置 ref：
  - PA RCA `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-29--phys_lock_zero_position_close_loop_rca.md` §5 D2
  - BB `docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-29--retcode_110017_convergence_semantics.md`（G-1..G-5 / one-way 前提 / C-1/C-2/C-3）
  - D1 已 land：commit `caf008b6`（dispatch 110017→NoOp + qty==0 guard + `converge_exchange_zero_close`）

---

## 0. 為什麼 D1 不夠 / D2 解什麼（gap 一句話）

D1 收斂只在 `qty==0 全平 form` 觸發（BB G-4 路徑 a）。但 demo `risk_config_demo.toml:229 use_maker_close=true` → close-maker PostOnly 走 **explicit qty>0**（`commands.rs:975` `dispatch_qty = if full_close && !is_close_maker_limit { 0.0 } else { qty }`）。qty>0 partial/maker close 撞 drift 倉撞 110017 時 D1 guard **故意不收斂**（因 qty>0 可能是 C-1「qty>size 倉仍在」，裸刪會誤刪真倉）。結果：close-maker 路徑的 drift 倉會「安靜迴圈」——NoOp 無 log spam，但仍 ~1.4/sec 重發、drift 永不清、污染 demo edge 樣本。

**D2 = 補足 qty>0 路徑的收斂**，但因為 qty>0 無法靠 form 推斷零倉（D1 的安全來源），D2 **必須改用 Bybit position query 顯式確認 size==0** 才能本地 remove。

> **live 影響面（先講結論）**：live `use_maker_close=false`（`risk_config_live.toml:212`），primary 全平走 qty==0 form → D1 已覆蓋 live 正常路徑。D2 對 live 的價值僅在「liquidation / 手動平倉 / DCP 後本地殘倉」這類非 qty==0-form 觸發的 drift（罕見但存在）。live 不依賴 D2 止迴圈，D2 對 live 是 defense-in-depth。

---

## 1. 觸發（選擇 + 理由）

**選擇：週期性 reconcile（復用既有 `position_reconciler` 30s cycle），不採「連發 ≥N 次 110017」。**

理由：
1. **不需新增可變狀態**。`position_reconciler/mod.rs` 已存在、已每 30s polls `/v5/position/list`（Bybit truth）、已有 `engine_positions_mirror`（`symbol→is_long`，引擎本地倉鏡像，由 `paper_state.set_positions_mirror` 寫入）。「連發計數」需在 dispatch 熱路徑加 per-symbol counter + 過期清理（BB G-5 自己也把連發 DEFER 為非 mandatory，理由是複雜度不值）。
2. **reconciler 本就是「感知 exchange 真相 vs 本地基線」的權威層**（module doc line 1-2）。D2 的本質就是 reconciler 的本職，不該在 dispatch 出口另造一套。
3. **drift 偵測不依賴「有沒有人在撞 110017」**。連發計數只在「正好有 close 決策每 tick 重發」時才觸發；週期 reconcile 對「靜止的 drift 倉（暫時沒 close 決策命中）」也能清，覆蓋更全。
4. **30s 收斂時延可接受**。D2 場景無真錢損失（reject 不成交），30s 內最多 ~42 次無效下單，比 D1（即時）慢但完全在容忍範圍；換來零新熱路徑狀態。

**不採連發計數的代價說明**：D2 不會「即時」斷迴圈（最壞 30s）。若未來發現有「30s 內高頻 + 真錢路徑」的 drift，再評估在 dispatch 層加 D3 熔斷（RCA §5 D3，本 spec 不含）。

---

## 2. 安全 gate（BB mandatory）：position query → confirm size==0 → remove

**核心安全論證：reconciler 的 `Ghost` 偵測天生就是「position query confirm」。** 不需新發 REST，因 reconcile cycle 每輪都已 `pos_mgr.get_positions(Linear, None)` 抓全 Bybit 真相（`mod.rs:420`）。

### 2.1 收斂判定條件（全 AND，缺一不收斂）

D2 收斂一個 symbol 的本地倉，當且僅當：

- **S-1 引擎本地確實有倉**：`engine_positions_mirror` 含該 symbol（`oh_cfg.engine_positions_mirror`，已快照於 `process_orphans` cycle）。**這是 D1 沒有的維度** — D1 靠 110017 事件被動觸發；D2 主動比對「本地有 vs Bybit 無」。
- **S-2 Bybit 本輪 fetch 成功且該 symbol size==0**：該 symbol 不在本輪 `current` view map（`build_view_map` 已過濾 `size<=0 || side=="None"` → `position_info_to_view` line 207）。**即 Bybit 權威回報「此 symbol 無 open 倉」**。這正是 BB 要求的 "position query 確認 size==0 才 remove"，由 reconciler 既有 `Ghost` verdict（`classify`：baseline=Some, current=None）表達。
- **S-3 fetch 未失敗**：本輪 `raw_fetch` 為 `Ok`（`mod.rs:449` arm）。REST 失敗（`Err`）→ 整個 cycle fail-open（`mod.rs:423`，baseline 保留、不分類）→ **天然 fail-closed for D2：查不到就不刪**。BB 的「query 失敗/timeout 不確定就不刪」由既有 fail-open 結構直接滿足，**無需新增 timeout 處理**（get_positions 走 `get_checked`，REST client 自帶 timeout → `Err`）。
- **S-4 dust filter 後仍判 Ghost**：`filter_dust` 已先跑（`mod.rs:455`）。dust 倉不誤觸（保守）。
- **S-5 非引擎剛開倉 race（C-3 防護）**：復用既有 orphan FUP 的反向邏輯——若 mirror 顯示引擎剛開該倉但 Bybit baseline 尚未收錄，那是 Orphan 方向（Bybit 有/本地剛開）不是 Ghost；D2 只處理 Ghost（本地有/Bybit 無），與 fresh-fill race 方向相反，**結構性不衝突**。額外保護見 2.3 streak。

### 2.2 為什麼不需要「額外」position query

BB spec 提供兩條路徑：路徑 a（qty==0 form 推斷，= D1）/路徑 b（發一次 `GET /v5/position/list?symbol=X` 確認）。**D2 = 路徑 b 的免費版**：reconciler 每 30s 已對全 symbol 做等價 query，D2 只是消費既有結果而非新發 REST。這比「在 dispatch 熱路徑同步發 position query」更安全（不阻塞、不加 race window、不增 rate budget）。

### 2.3 C-3 race 二次防護（建議，低成本）

reconciler baseline 是「上一 cycle 的 Bybit 真相」。理論 race：cycle N Bybit 有倉 → 引擎本地也有 → cycle N+1 Bybit「剛好」短暫不回該倉（結算延遲）→ 誤判 Ghost。防護：**要求連續 ≥2 cycle 都判 Ghost 才收斂**（即 `last_ghost_cycle[symbol]` 命中 + 本輪再命中）。這需在 `ReconcilerState` 加一個小 `HashSet<String>`（per-engine，非熱路徑），成本遠低於 dispatch 層 per-tick counter。**60s 確認窗對「倉早已不存在」的真 drift 無實質延遲，但擋住單 cycle 結算 race**。E1 可先實作單 cycle（最小），E2 評估是否升 2-cycle；BB review 拍板。

---

## 3. 落點 + 復用

### 3.1 落點：`position_reconciler` 的 Ghost 處理分支（新增）

現狀：`Ghost` verdict 目前**只寫 V014 audit，無 action**（`mod.rs:504` spawn_reconcile_audit，drift push 入 `drifts` 後交 `evaluate_actions` 做 governor 升級，但**不刪本地倉**）。

新增：在 `process_orphans` 之後、`evaluate_actions` 之前，加一個 `process_ghosts`（對稱於既有 `process_orphans`），攔截 `DriftVerdict::Ghost` 且滿足 S-1..S-5 的 symbol，dispatch 收斂命令。攔截後從 `drifts` 移除該 Ghost（避免 `evaluate_actions` 對「已收斂的 Ghost」重複 governor 升級——對齊 `process_orphans` 的 `kept` 模式 `mod.rs:613`）。

### 3.2 收斂如何回到 pipeline：**新 `PipelineCommand::ConvergeExchangeZero`，不可用 `CloseSymbol`**

**關鍵反模式警告**：既有 orphan close 走 `PipelineCommand::CloseSymbol` → `handle_close_symbol` → `ipc_close_symbol` → **同一條 reduce-only dispatch**（`lifecycle.rs:96`）。若 D2 對 Ghost 發 `CloseSymbol`，會**再撞 110017 → 重入迴圈**（RCA §3a 已證 ipc_close 對 110017 清不掉）。**D2 必須繞過 close dispatch，直接調 D1 已 land 的 `converge_exchange_zero_close`。**

復用清單：
- **`PipelineCommand::ConvergeExchangeZero { symbol, is_long, ts_ms }`**（新 variant，types/handlers）。語意=「reconciler 確認 Bybit 端該倉已 zero，請本地收斂」。
- handler（`handlers/lifecycle.rs` 新 `handle_converge_exchange_zero`）→ 直接調 `pipeline.converge_exchange_zero_close(&symbol, is_long, ts_ms)`（**commands.rs:1267，D1 已 land，0 改動**）→ `upsert_position_from_exchange(size=0)` → `positions_remove` + `pending_close_symbols.remove` + mirror 同步，**0 record_trade / 0 realized PnL / 0 Kelly 污染**（D1 已驗）。
- `is_long`：取自 `engine_positions_mirror[symbol]`（引擎本地方向，非 Bybit——Bybit 已無倉故無方向）。
- dispatch helper（`orphan_handler.rs` 旁新 `dispatch_ghost_converge`，對稱 `dispatch_orphan_close`）+ V014 audit（對稱 `spawn_orphan_audit`）。

### 3.3 為什麼新 variant 而非復用 ExchangeZeroClose 事件

D1 的 `PendingOrderEvent::ExchangeZeroClose` 走 dispatch task → event consumer 的 `pending_reg_tx`。D2 的觸發源是 reconciler task，走 `cmd_tx`（`PipelineCommand` 通道）。兩條通道不同、源不同，但**匯流到同一收斂函數** `converge_exchange_zero_close`。新 `PipelineCommand` variant 是 reconciler→pipeline 的對齊管道，不混用事件通道。

---

## 4. engine_mode 行為 + live 真倉安全論證

| mode | reconciler 是否跑 | D2 是否生效 | 安全論證 |
|---|---|---|---|
| paper | **否** | noop | reconciler spawn gate 在 `shared_client.is_some()`（exchange client）；paper 無 exchange client → reconciler 不啟 → D2 不存在。額外，`converge_exchange_zero_close` 本身 `if !pipeline_kind.is_exchange() { return false }`（commands.rs:1274）二重保護。 |
| demo | 是 | **主要受益者** | demo `use_maker_close=true` → qty>0 close-maker drift 的唯一治本路徑。無真錢。 |
| live_demo | 是 | 生效 | live-grade 控制流走 demo endpoint；按 live 標準收斂（不降級）。 |
| live | 是 | defense-in-depth | 見下。 |

**live 真倉安全論證（最高約束）**：
1. **收斂前提是 Bybit 權威 fetch 回報 size==0**（S-2）。若 live 真有倉，Bybit `/v5/position/list` 必回該倉 size>0 → 不判 Ghost → **不收斂**。D2 只在 Bybit 自己說「此 symbol 無倉」時才動本地倉 = 跟隨真相，不是猜測。
2. **這正是 D1 比 D2 更需謹慎之處的反面**：D1 靠 110017 + qty==0 form 推斷；D2 靠**直接 query 確認**——對 live 而言 D2 的安全來源（顯式 query）比 D1（form 推斷）更強。BB 的 C-1（qty>size 倉仍在）對 D2 結構性不適用：D2 不看 reject 的 qty，只看 query 結果。
3. **fail-open = fail-closed for delete**：REST 失敗 → 不分類 → 不刪（§2.1 S-3）。「查不到就不刪」是 Root Principle 6（不確定默認保守）。
4. **C-2（hedge）前提守衛繼承**：`converge_exchange_zero_close` 已帶 G-3 hedge-mode re-review 註解（commands.rs:1259）。D2 復用同函數 → 同前提（one-way mode）。reconciler `PositionView.key()` 用 `symbol|side`（mod.rs:101，已 hedge-aware），故 D2 的 Ghost 判定本就分 side；one-way 下每 symbol 單 side，無誤判。**E1 須在 D2 收斂處重申 G-3：hedge 啟用 = mandatory re-review。**
5. **liquidation / 手動平倉 drift**：live 被強平 / operator 手動平倉後本地殘倉 → Bybit query size==0 → D2 收斂 = 對齊真相（正確期望行為，非誤刪）。這是 D2 對 live 的真正價值。

---

## 5. audit / log（別重蹈 D1 的 observability 坑）

**D1 audit 已知問題（follow-up `P3-110017-CONVERGE-AUDIT-OBSERVABILITY`）**：D1 把收斂 audit 寫 `OrderStateChange(Cancelled, exchange_zero_close_converge:110017)` 到 `trading.order_state_changes`，但部署後**查無該 row**——因 position-convergence 無真實 order_id 對應該表（用 order_link_id 當 order_id 寫，但該表可能不收這類合成 id）。

**D2 audit 設計（避坑）**：
- **不寫 `order_state_changes`**（D2 無 close order_id 概念，純 position drift 收斂）。
- **寫 `observability.engine_events`**（reconciler 既有 audit 通道，`spawn_reconcile_audit` / `spawn_action_audit` 已用，已驗可落地）。新 `event_type = "reconcile_ghost_converge"`，`source = "position_reconciler"`，payload `{ symbol, side, baseline_qty, engine, removed_position: bool }`。對齊 `mod.rs:231 spawn_reconcile_audit` 結構，0 新表。
- **log**：偵測 `info!("ghost drift → exchange-zero converge candidate")` + 收斂 `warn!("ghost converged: removed drifted local position")`（對稱 `converge_exchange_zero_close` 既有 warn）。removed_position bool 入 audit + log 供歸因。
- **E1 acceptance**：deploy 後須在 `observability.engine_events WHERE event_type='reconcile_ghost_converge'` 查得 row（不重蹈 D1「audit 寫了但查無」）。MIT 核 audit 落地。

---

## 6. 與 D1 關係：**補充（complement），非 superset；不會雙刪**

- **D1（dispatch 即時）**：qty==0 全平 form + 110017 即時觸發。覆蓋 primary 全平 drift（live 正常路徑 + demo 全平路徑）。
- **D2（reconcile 週期）**：任何 form 的本地倉（含 qty>0 close-maker）+ Bybit query 確認 size==0。覆蓋 D1 漏掉的 qty>0 路徑 + 靜止 drift 倉。
- **交集處理**：兩者最終都調**同一函數** `converge_exchange_zero_close`，該函數**冪等**——`upsert_position_from_exchange(size=0)` 對已 remove 的倉回 false（no-op，commands.rs:1281+1293 已處理「倉不存在」分支），`pending_close_symbols.remove` 對已清的 flag 也 no-op。**故 D1 先收斂後 D2 再撞同 symbol = 安全 no-op，無雙刪、無 double realized（本就 0 realized）**。
- **時序**：D1 即時（若 qty==0 path 命中）先清；D2 30s 後若仍見 drift（D1 沒覆蓋的 qty>0 path）才清。兩者不互斥、不需協調鎖——冪等收斂是天然防雙刪設計。
- **結論**：D2 **不取代 D1**。D1 留作 qty==0 path 的即時止血；D2 補 qty>0 path + 週期兜底。

---

## 7. V### migration？**不需要。**

- D2 audit 復用既有 `observability.engine_events` 表（reconciler 既有 `spawn_reconcile_audit` 已 INSERT，schema 不變）。
- 無新 drift log table、無新 column、無 schema 變更。
- 新 `event_type='reconcile_ghost_converge'` 是 payload 值，非 schema。
- **故無 V### migration → 無 Linux PG dry-run gate**。（若 E1/BB review 後堅持要獨立 drift log table，則升級為需 V### + Linux PG empirical dry-run mandatory，並標 idempotency double-apply gate；但本 spec 評估 engine_events 足夠，不建議新表。）

---

## E1 派發計劃（單 E1，文件不重疊，無並行需求）

範圍小（~120-160 LOC，全 Rust，集中在 reconciler + 1 command variant），單 E1 串行即可：

| 檔 | 改動 | LOC |
|---|---|---|
| `position_reconciler/mod.rs` | 新 `process_ghosts`（對稱 process_orphans）+ cycle loop 接線（process_orphans 後、evaluate_actions 前）+ Ghost 從 drifts kept 移除 | ~50 |
| `position_reconciler/orphan_handler.rs`（或同層新檔） | `dispatch_ghost_converge` + V014 audit helper | ~30 |
| `tick_pipeline/mod.rs`（PipelineCommand enum）| 新 `ConvergeExchangeZero { symbol, is_long, ts_ms }` variant | ~6 |
| `event_consumer/handlers/mod.rs` + `handlers/lifecycle.rs` | 新 arm → `handle_converge_exchange_zero` → 調既有 `converge_exchange_zero_close` | ~25 |
| `position_reconciler/tests.rs` + `handlers` test | Ghost-converge 正/負 case（含 fetch-fail 不刪 / 真倉不刪 / 冪等 double-converge） | ~50 |
| `ReconcilerState`（escalation.rs）| （若採 2-cycle streak）加 `last_ghost_symbols: HashSet<String>` | ~10 |

**0 改動既有 `converge_exchange_zero_close` / `upsert_position_from_exchange` / dispatch.rs**（D1 路徑完全不碰，零回歸風險）。

NO-OP exit：若 E1 fetch 發現 reconciler 已有人加 Ghost action（重複派發），exit 並回報。

---

## E2 重點審查 3 點（高風險）

1. **誤刪真倉對抗驗證**：構造 cycle N Bybit 有倉 + 本地有倉 → cycle N+1 Bybit fetch **失敗（Err）** → 必須**不收斂**（fail-open 保倉）。再構造 Bybit fetch 成功但回 size>0 → 必須**不收斂**。這兩個 negative case 是 live 安全的命脈，必須有測試。
2. **不重入 close 迴圈**：確認 D2 走 `ConvergeExchangeZero`→`converge_exchange_zero_close`，**絕不**經 `CloseSymbol`/`ipc_close_symbol`（否則 qty>0 close 再撞 110017 = 新迴圈）。grep 確認 D2 路徑無 `execute_position_close` 調用。
3. **冪等 + 不雙刪 + evaluate_actions 不重複升級**：D1 已清的 symbol 被 D2 再收斂 = no-op（測試覆蓋）；Ghost 被 process_ghosts 攔截後必須從 `drifts` 移除，否則 `evaluate_actions` 對「已收斂 Ghost」仍 governor 升級（false escalation）——對齊 process_orphans 的 kept 模式。

---

## BB review 重點（exchange-facing，mandatory）

1. 背書「reconciler Ghost（Bybit fetch 確認 symbol 不在 position list）= 可靠的 size==0 信號」——對比 D1 的 form 推斷，D2 是顯式 query，BB 應確認 `/v5/position/list` 對「無倉 symbol」的回報語意（不回該 symbol vs 回 size=0/side=None；`position_info_to_view` 兩者都過濾）。
2. 確認 one-way mode 前提守衛（G-3）對 D2 同樣成立 + hedge 啟用須重審 D2 路徑。
3. 拍板 §2.3：單 cycle 收斂 vs 2-cycle streak（C-3 結算 race 防護是否 mandatory）。
