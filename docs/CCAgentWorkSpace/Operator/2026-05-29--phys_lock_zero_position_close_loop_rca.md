# PA RCA — PHYS-LOCK zero-position reduce-only close loop (TRXUSDT demo)

- 日期：2026-05-29
- 模式：read-only RCA（無改碼/無重啟/無 IPC；ssh 僅 cat/grep/python SELECT-equivalent）
- 範圍：demo engine（PID 27582，13:57 CEST cold-audit --rebuild 後）TRXUSDT 1.4/sec reduce-only close → Bybit 110017 迴圈
- 證據分類遵 Root Principle 10（FACT / INFERENCE / ASSUMPTION 標記）

---

## 0. 重大前提修正（推翻 PM 採集的「positions: {}」）

[FACT] `/tmp/openclaw/demo_state.json`（mtime 2026-05-29 16:46，engine 仍在寫）`positions` 欄位是 **JSON list 不是 dict**，內含**一個** TRXUSDT 倉：

```
symbol=TRXUSDT  is_long=true  qty=2907.0  entry_price=0.34204
owner_strategy="strategy_close:grid_close_short"
entry_context_id="ctx-demo-TRXUSDT-1780054703495"
entry_ts_ms=1780055910428  (2026-05-29 11:58:30 UTC = 13:58 CEST)
peak_reached_ts_ms=1780062784505 (13:53:04 UTC = 15:53 CEST)
```

[FACT] live_state.json 唯一倉是 AVAXUSDT（grid_trading，無關）。live_demo_state.json absent。
[INFERENCE] PM 報「positions: {} 空」是把 list 當 dict 解析、或讀到 reboot 瞬間 pre-restore 快照的誤判。**這不是 in-memory phantom，是 persisted 真倉。**

---

## 1. 根因（一句話 + code path）

[FACT/INFERENCE] **TRXUSDT 在 engine 本地/persisted state 中是一個真實殘倉（grid short 平倉後未被清除），但 Bybit demo 端實際無此倉；exchange-mode 平倉只 dispatch 不本地刪倉、要靠 confirmed fill 才刪，而 Bybit 對「無倉」回 110017 永不成交 → 倉永不刪 → 每 tick PHYS-LOCK gate4_giveback 重評重發，自持迴圈。**

精確 path：
1. `tick_pipeline/on_tick/step_6_risk_checks.rs:84-134` 從 `paper_state.positions()`（含 TRXUSDT）建 `position_rows`。
2. `position_risk_evaluator::evaluate_positions` → TRXUSDT 命中 PHYS-LOCK Priority 6 → `RiskAction::ClosePosition("risk_close:phys_lock_gate4_giveback")`。
3. step_6_risk_checks.rs:381-410（exchange-mode arm）：`pending_close_symbols.contains` 檢查（382）後 `execute_position_close(..., is_primary=true)`（399）。
4. `tick_pipeline/commands.rs:920-1057 execute_position_close`：build reduce-only `OrderDispatchRequest`，`tx.send` 成功才 `pending_close_symbols.insert`（1031）。**此函數不呼 positions_remove**（exchange path 設計上靠 fill 確認才刪倉）。
5. Bybit 回 `ret_code=110017`「current position is zero」。`event_consumer/dispatch.rs:223 classify_business_retcode` → 110017 落 `_ => DispatchOutcome::Structural`（304-306）→ no retry、無 fill。
6. 無 confirmed close fill → `commands.rs:617 apply_confirmed_fill`（→ fill_engine `positions_remove`）永不執行 → TRXUSDT 留在 `positions()`。
7. `commands.rs:1219 reconcile_pending_exchange_orders`（R-02）只 `retain(|s| open_symbols.contains(s))` — TRXUSDT 仍在 `positions()`（open_symbols 來自同一 `positions()`）→ **不清**。pending flag 與 local 倉互相佐證、形成自洽假象。
8. 下一 tick 回到步驟 1，多執行緒（log 見 ThreadId 17/25/26/29 同毫秒）各跑一遍 → ~1.4/sec。

**缺陷不是缺 `position qty>0` guard**（倉的 qty=2907>0，gate 正常 fire）。缺陷是**本地 position truth 與 exchange position truth 不一致時，沒有收斂機制**：110017（exchange-zero）既不被當 NoOp 清倉、reconcile 又只信任本地 positions()。

---

## 2. qty=0.0 來源（非 bug，是設計形態）

[FACT] `tick_pipeline/close_sizing.rs:26-36 close_dispatch_qty_for_full_close`：primary + exchange-mode full close 回 `0.0`。這是 Bybit perp 全平特殊形態 `qty=0 + reduceOnly=true + closeOnTrigger=true`，讓交易所 flatten 當前倉而非依賴本地可能 stale 的 rounded size（2026-04-30 dust-residual fix 引入，archive 2026-04-30）。
- order_link_id `oc_risk_dm_<ts>_<ctr>`：`oc_risk`=primary risk close 前綴（commands.rs:931），`dm`=`order_link_mode_tag()` 的 demo 標籤（pipeline_ctor.rs:319 `"demo" => "dm"`）。**`dm` ≠ decision_manager**，與 risk drawdown 無關。
- 對「有倉」symbol：qty=0 form 正確全平。對「無倉」symbol：Bybit 無倉可平 → 110017。所以 qty=0 本身不錯，錯在它被送往一個 exchange 端不存在的倉。

---

## 3. restart 能否清掉 — 明確結論

[FACT/INFERENCE] **不能。** TRXUSDT 是 `demo_state.json` 的 **persisted** 倉（非 in-memory only）。`restart_all --keep-auth` 後 engine startup 從 demo_state.json restore 該倉（或被 Bybit sync / reconciler 處理）→ 重啟即重載 → 迴圈會在重啟後繼續。

依據：demo_state.json mtime 16:46 仍含 TRXUSDT；entry_ts 11:58 UTC 早於 13:57 重啟仍存活 = 已驗它能跨重啟存活。

可清的途徑：
- (a) [INFERENCE] IPC `ipc_close_symbol(TRXUSDT)` — 但同走 reduce-only dispatch，Bybit 仍回 110017，**清不掉**（除非該 path 對 110017 做本地 flatten，需查；目前看不會）。
- (b) [FACT-derived] engine stop 後手動從 demo_state.json 移除 TRXUSDT 條目再啟 — 可清，但繞過正規路徑、屬一次性止血、不治本。
- (c) 修 code（見 §5）讓 110017/exchange-zero 觸發本地 positions_remove —— 治本。

---

## 4. 為何 13:57 後 / 為何 TRXUSDT / 擴散風險

[FACT] entry_ts=11:58 UTC（13:58 CEST），owner=`strategy_close:grid_close_short`。即此倉是 grid SHORT 開倉後被 grid_close 觸發平倉、owner 已轉為 close-tag 的**殘倉**，在 13:57 重啟同窗形成。
[INFERENCE] 13:57 cold-audit --rebuild 重啟期間（downtime）grid_close 的 exchange 平倉未確認 / 在 Bybit 端已平但本地未收到 fill → 重啟 restore 把這個「本地以為還在、exchange 已無」的不一致倉撈回。13:57 後才爆 = 重啟 reload 了這個 drift 倉 + PHYS-LOCK T4（2026-04-21 後 active）每 tick 對它重評。
[INFERENCE] 只 TRXUSDT = 目前 demo 只有這一個 exchange-local drift 倉（其他 demo 倉已正常平掉，state 只剩它）。
[ASSESSMENT 擴散風險] **中**：任何「本地殘倉 + exchange 端已平 + 該倉每 tick 命中某 close 決策（PHYS-LOCK / hard stop / grid_close）」的組合都會複現同迴圈。觸發不限 PHYS-LOCK；110017 misclassification + exchange-mode 不本地刪倉 是通用缺陷。每次 cold restart / downtime 平倉競態都可能再造一個。**這是結構性而非 TRXUSDT 專屬。**

---

## 5. 修法設計（未 impl；layer + guard）

### 主修（治本）— dispatch classifier 把 exchange-zero 當已平並收斂本地倉
- **Layer**：`event_consumer/dispatch.rs classify_business_retcode` + 其結果消費端（成交/收斂處理）。
- **改法**：110017（及語意等同「無倉可 reduce」族）由 `Structural` 改為 **NoOp / 等效已平**，對齊既有 110001/110009「Order/position not found on a close → NoOp」語意（dispatch.rs:286-288）；並在 NoOp-close 結果消費端觸發 **本地 positions_remove + pending_close_symbols.remove**（即把「exchange 確認無倉」當成一次成功平倉收斂）。
- **理由**：110017 的 retMsg「current position is zero」就是「交易所確認此倉已不存在」，與 110001/110009 同義，理應同樣讓本地收斂。WP-10（2026-05-16 ef6ea79f）只加了 `ReduceOnlyReject=110017` enum variant + 字典 row，**未改分類也未接收斂** — 這是缺口。
- **硬邊界檢查**：110017 是 CLOSE（reduce-only）方向；把它從 fail-closed(Structural) 改 NoOp 不違反「Bybit nonzero retCode fails closed」原則的 **開倉** 語意 — close 的 fail-closed 目的是「不要讓倉沒平掉」，而 110017 恰恰證明倉已不在，NoOp 收斂才是 survival-correct（Root Principle 5）。**但此判定須 BB review 對 Bybit 110017 語意背書**（不可只憑 PA 推斷）。

### Defense-in-depth（任一獨立成立即斷迴圈）
- **D1 — execute_position_close 前 assert exchange-relevant 倉存在**：`tick_pipeline/commands.rs:920 execute_position_close` 在 build request 前，對 exchange-mode primary close 檢查（若可得）近期 Bybit position view / 連續 110017 計數；qty=0-form 全平前確認本地倉 qty>0（已成立）**且** 非「已知 exchange-zero」。放 commands 層。
- **D2 — R-02 reconcile 納入 exchange truth**：`commands.rs:1219 reconcile_pending_exchange_orders` 或 `position_reconciler` 對「Bybit 回報 zero / 連續 110017」的 symbol，即使本地 positions() 仍有，也 **remove 本地倉 + 記 reconcile drift 審計**。目前 R-02 只信本地 positions()，是迴圈得以自洽的關鍵盲點。
- **D3 — dispatch 層 N 連發同 symbol 同 110017 熔斷**：同 symbol reduce-only 在短窗內連續 110017 達閾值 → 強制本地 flatten + 暫停對該 symbol 的 close re-dispatch（fail-safe 收斂，Root Principle 6）。

### 「dispatch 層收到 qty=0 reduce-only 應否直接 reject」評估
[ASSESSMENT] **不應**對 qty=0 reduce-only 一律 reject — qty=0 是 Bybit 全平 form 的**合法且必要**形態（close_sizing.rs 設計），盲 reject 會打掉正常全平。正確 defense 是 **D1（emit 前確認倉真實存在）** 而非在 dispatch 出口按 qty=0 reject。dispatch 出口的 defense 應是 **D3（同 symbol 110017 連發熔斷）**，針對「結果」而非「形態」。

### 建議優先序
主修（classifier→NoOp→本地收斂，需 BB sign-off）為治本；D2（reconcile 納 exchange truth）為最高價值 defense（堵住自洽盲點）；D1/D3 為快速止血層。止血（清現有 TRXUSDT 殘倉）建議走 §3(b/c)，不要靠 restart（§3 結論：清不掉）。

---

## 6. 是否新 bug

[FACT] **同族已知，此觸發實例為新。**
- prior art：BUSDT / funding_arb V2 的 110017 reject loop（`docs/CCAgentWorkSpace/BB/memory.md:200-202`：「short perp leg 反覆被 Bybit 110017/110007 reject」；archive `2026-04-30` dust residual RCA；archive readme `[40] BUSDT 110017 reject loop`）。
- 已落地但不夠：WP-10（2026-05-16 commit ef6ea79f）加 110017 enum variant + 字典 §4.2 row；funding_arb 三端 active=false + fee_filter 110017 過濾。**這些都沒修 classifier 分類、沒接本地收斂、沒處理 exchange-mode 不本地刪倉的根因。**
- 新處：本次是 **grid_close 殘倉 + PHYS-LOCK gate4_giveback 每 tick 重評** 觸發同一 110017 結構缺陷，證明問題不限 funding_arb，是通用 exchange-local drift 收斂缺失。
- TODO/active：grep TODO.md 無對應 active ticket（無「110017 loop / phys_lock loop / exchange drift converge」條目）→ 應新開 ticket（建議掛 P1：active resource-burn loop，7411+ reject，無真錢但污染 demo edge 樣本 + 27116 110017 噪音 + log 5.7GB 膨脹）。

---

## 派 E1 前置（供 PM）
- 主修需 **BB review** 背書 Bybit 110017 語意（is it safe to treat as position-flat NoOp）→ 走 §八 `BB if exchange-facing` 鏈。
- 改 `dispatch.rs classify_business_retcode` 屬「高」風險（dispatch 主路徑 + 5 classifier 既有 7 assertion test，bybit_rest_client_tests.rs）；E2 重點審 3 點：(1) 110017→NoOp 不誤吞真正該 fail-closed 的 close 失敗；(2) 本地 positions_remove 收斂不破壞 fill 歸因 / Kelly stats（commands.rs:724 record_trade 路徑）；(3) reconcile D2 不誤刪正常 in-flight close 的本地倉（需 exchange truth 來源可靠性確認）。
- 止血與治本分兩 wave：wave 0 清 TRXUSDT 殘倉（operator/E3 手動，engine stop 編 demo_state.json），wave 1 code fix。
