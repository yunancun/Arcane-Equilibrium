# BB — C4 fail-safe wire · set_trading_stop 交易所信任邊界審查

- 日期：2026-05-29
- Worktree：`/Users/ncyu/Projects/TradeBot/wt-c4` · branch `fix/packet-c-c4-wire`
- Scope：C4（`P2-PACKET-C-C4-PIPELINE-WIRE`）把自主 fail-safe 接進 runtime 的**交易所面**（`set_trading_stop`）信任邊界。read-only 靜態審計，不打真實 API，不改碼。
- 上游 E2 verdict：APPROVE-WITH-CONDITIONS（set_trading_stop 交易所面深審交 BB）。

## Verdict：**APPROVE-WITH-GUARD**

C4 交易所面安全。既有單一寫入口復用正確、retCode fail-closed 繼承既有路徑、paper 雙層 noop、rate-limit 0 風險、半 wire 故 deploy 後交易所面 0 實際影響。1 個 **非阻 advisory（G-1）**：lock-profit SL 設在 entry 上方（Buy）/ 下方（Sell），對「尚未足夠獲利」的倉 Bybit 會**拒單**（非誤平），是安全的，但應在字典 + spec 明記此語義避免未來 drift。

---

## 1. 既有路徑非新 client（Root Principle 1）— PASS [FACT]

C4 owner handler `InBandStopSync::sync_stop`（risk.rs:660-675）**只**做 `stop_tx.send(StopRequest{symbol,stop_loss,is_long})`，不持 PositionManager、不構造第二個 Bybit client。

復用鏈（grep 驗，三方一致）：
- `handle_notification_failsafe_escalate`（risk.rs:761）`pipeline.stop_channel().cloned()` 取既有 `stop_request_tx`。
- `set_stop_channel` / `stop_channel`（pipeline_helpers.rs:629-646）= C4 之前既有 server-side stop 雙軌 channel。
- consumer = `bootstrap.rs:752` 既有 `while let Some(req) = stop_rx.recv()` task，line 778 `mgr.set_trading_stop(stop_req)`。
- 該 consumer 與既有 tick-pipeline 開倉 SL 路徑（`step_4_5_dispatch.rs:1298-1313` 也 `tx.send(StopRequest{..})`）**共用同一 channel 同一 consumer 同一 `set_trading_stop`**。

C4 新增 StopRequest 生產者，但 `StopRequest` struct（tick_pipeline/mod.rs:662）未改、consumer 未改、`set_trading_stop`（position_manager.rs:237）未改。owner pipeline 不持 PositionManager（私有在 consumer task 內），新構 client 會違反單一寫入口——handler doc-comment（risk.rs:637-644）+ pipeline_helpers.rs:636-645 明寫此設計理由。**0 第二 client / 0 繞過。**

## 2. conditional SL 語義 / 方向 / 誤平風險 — PASS（含 G-1 advisory）

### (a) SL price 方向 [FACT]
`active_lock_profit_per_position`（risk_gov.rs:327-382，buffer default 0.5）：
- Buy 倉 `new_sl = entry + atr×0.5` → **entry 上方**
- Sell 倉 `new_sl = entry - atr×0.5` → **entry 下方**
- 「不放鬆既有保護方向」守衛正確：Buy `existing >= candidate → 保留 existing`；Sell `existing <= candidate → 保留 existing`。
- 無效輸入（NaN / atr<=0 / entry<=0 / qty≈0 / 未知 side）逐倉跳過 fail-closed，不 panic。

★ 關鍵：這是 **lock-profit（鎖利）** 而非 entry-time stop-loss，方向與 entry 的相對關係**故意相反**於既有開倉 SL：
- 既有開倉路徑（step_4_5_dispatch.rs:1303-1307）：Buy SL = `entry×(1-pct)` 在 entry **下方**（虧損保護）。
- C4 lock-profit：Buy SL = `entry + atr×buffer` 在 entry **上方**（鎖住 unrealized 獲利）。
兩者方向不同是**設計正確**，不是 bug。SM-04 Defensive 收緊 = 把 SL 從「虧損保護位」上移到「entry+鎖利位」，符合「survival 優先」。

### (b) 誤平風險 — 安全（Bybit 拒單而非誤平）[FACT + 官方驗證]
Bybit V5 long SL 是 sell-to-close trigger，要求 stopLoss < current market price。C4 lock-profit SL 在 entry 上方，對 current price 有兩種情況：
1. **倉已足夠獲利**（market > new_sl，例 price 51000 / new_sl 50250）→ SL 在 market 下方 → 合法，鎖利生效。**無誤平。**
2. **倉未足夠獲利**（market <= new_sl，例 price 50100 / new_sl 50250）→ SL 在 market 上方/等於 → Bybit **拒單**（"expect Rising/Falling but trigger vs current" / 34040 / 10001 family），**不會立即市價平倉**。Bybit 的 validation 是「拒絕錯側 SL」而非「立即觸發」。

→ 誤平結構路徑為空：Bybit 把錯側 SL fail 掉，position 不被誤平，consumer 端 set_trading_stop 回 Err → fail-closed（見 §3）。代價僅是「未獲利倉的鎖利 SL 靜默設不上」——可接受（該倉仍有開倉期 SL + 本地 StopManager 雙軌）。

**G-1 advisory（非阻）**：lock-profit 計算只用 `entry_price` + `current_sl`，**不讀 current market price**，故無「SL 設在 market 錯側即跳過」的本地預檢。當前依賴 Bybit 拒單兜底是安全的（fail-closed），但：
- 字典 §set_trading_stop（line 559+）應補「long SL 必 < lastPrice、short SL 必 > lastPrice，否則 Bybit 拒單（34040/10001 family）；lock-profit SL 在 entry 上/下方時，未獲利倉會被拒，屬預期 fail-closed 非錯誤」。
- spec / handler doc 應記此語義，避免未來有人把「set_trading_stop 回 Err」誤判為 bug 而加 retry（會違 CLAUDE §四）。
- 未來若 buffer 調大或 ATR 極端，被拒比例升高僅降鎖利覆蓋率，不增誤平風險。

### (c) tpslMode / positionIdx — PASS [FACT]
- `positionIdx: Some(0)`（bootstrap.rs:774）= one-way mode，正確。與 memory 4 指紋一致（系統 one-way；`switch_position_mode` 0 production caller）。
- `slTriggerBy: Some("LastPrice")`（bootstrap.rs:771）合法。
- `tpslMode`：body 未送（position_manager.rs:238-339 不含 tpslMode）。Bybit V5 預設 Full（整倉 SL），對「整倉收緊保命」語義正確；C4 是逐倉設整倉 SL，符合預期。**非新增，繼承既有 set_trading_stop**，C4 未改。
- SL price 經 `normalize_trading_stop_price`（instrument_info.rs:766）方向保守 tick 取整（long floor / short ceil），缺 spec → None → 跳過交易所 SL + warn（本地 StopManager 兜底）。C4 繼承此 P1-06 行為，未改。

## 3. retCode fail-closed — PASS [FACT]
C4 **0 新增 retry**。fail-closed 全繼承既有：
- consumer（bootstrap.rs:778-794）：`set_trading_stop` 回 Err → `warn!` "exchange stop-loss failed (local stop active)"，**不重試、不假成功**，本地 StopManager 維持（Root Principle 9）。
- `set_trading_stop`（position_manager.rs:346）走 `post_checked` → nonzero retCode / timeout 回 Err（CLAUDE §四 fail-closed）。
- `InBandStopSync::sync_stop` 是 fire-and-forget：`UnboundedSender::send` 只入 channel 不等交易所回應；channel 已關回 `Transport` Err，escalation 記入 sync_record **不 rollback transition**（survival 優先，core mod.rs:398 不變量）。
- C4 grep 全程無新增 retry loop / 無 sleep-then-resend / 無 success 假冒。owner handler `atr_missing` warn 是誠實標記不是重試。

## 4. paper 不誤觸 — PASS（雙層）[FACT]
交易所面 cross-check E2：
- 第一層（結構性）：watcher escalate loop（tasks.rs:932）**只迭代 `[("demo",..),("live",..)]`，根本不含 paper**。paper `paper_enabled=false` 無 TickPipeline，cmd channel 被 drain。
- 第二層（防禦）：`InBandStopSync::sync_stop`（risk.rs:665-667）`engine_mode=="paper"` → 直接 `Ok(())` 不 send StopRequest。
- 第三層（最終）：即便 StopRequest 到達 consumer，paper pipeline 無 exchange client → log-only（bootstrap.rs paper 無 PositionManager）。
- test `e2e_c4_paper_skips_exchange_sync`（c4_failsafe_wire_tests.rs:164-192）斷言 paper 模式 0 StopRequest。
→ paper 不可能打任何 Bybit write endpoint。

## 5. rate-limit / ToS — 0 風險 — PASS [FACT/INFERENCE]
- set-trading-stop 屬 Position group 20 req/s（字典 line 1254，與 confirm-pending-mmr/set-leverage 共用）。
- fail-safe escalation 觸發頻率：watcher 30s tick + claim-before-await（同一武裝只發一次）+ per-engine（demo/live 各一）。最壞單次 incident = N 倉逐倉 set_trading_stop，N≤universe（demo ≤40），瞬發 ≪ 20 req/s × 5s burst budget。
- 觸發本身極罕見（通知三路全 fail + 1h timeout 才升），且 incident-trigger 尚未接（§6）→ 當前實際頻率 = 0。
- 非 wash / 非 spoof / 非 multi-account；收緊自己倉 SL 是合規行為（同既有 server-side stop）。**0 ToS、0 rate-limit 風險。**

## 6. 半 wire → deploy 交易所面 0 影響 — CONFIRMED [FACT]
C4 是半 wire：**timer 永不武裝 → escalate 永不發 → set_trading_stop 永不被 C4 呼**。鏈條斷點：
- 武裝 timer 唯一入口 = `observe_dispatch(AllFail)`（→ `evaluate_dispatch` set `timer_armed_at_ms`）。
- C4 把 `observe_dispatch` 的 outcome 來源放在 `outcome_rx`（tasks.rs:923），其 `outcome_tx` 註冊進 `FAILSAFE_FEED_SENDERS` OnceLock **供 Sprint 3 `P2-INCIDENT-POLICY-DISPATCH-TRIGGER` 取用**——C4 **自身 0 producer**（single_watcher.rs:68-90 + tasks.rs doc §5.1 誠實標記）。
- 故 `outcome_rx` 永遠空 → timer 永不武裝 → `timer_armed_at_ms == None` → `timer_expired`（mod.rs:345-348）`None => false` → `timer_expired_and_claim()` 永回 false → escalate command 永不發 → owner handler 永不跑 → `InBandStopSync` 永不 send StopRequest → `set_trading_stop` 永不被 C4 觸及。

→ **C4 deploy 後交易所面 0 實際影響**，直到 Sprint 3 incident-trigger 接上。deploy 安全。watcher task 本身只是 30s 空轉 select!（cancel/timer/outcome/ack），0 副作用。

機制側（非交易所面）已 live：SM-04 transition 邏輯、lock-profit 計算、雙軌 sync 通道、paper noop、claim-before-await idempotent 全 land 且有 e2e test 覆蓋（demo escalate / paper skip / watcher arm-then-claim-once）。Sprint 3 只需接 outcome producer 即全功能 live——屆時 set_trading_stop 才真實被觸發，**須 BB re-review**（incident-trigger 頻率 + 屆時 buffer/ATR 對被拒比例的影響）。

---

## 交易所面 overall
- 技術合規度：維持 ~97%（C4 0 新 endpoint、0 字典 endpoint drift、復用既有 set_trading_stop）。
- 0 ship-stop blocker；0 hard boundary 違反；Root Principle 1/5/6/9 全對齊。
- 30d Bybit V5 changelog 0 breaking change（繼承 2026-05-29 v80 audit）。

## follow-up（下次啟動查驗）
1. **G-1 字典補錄**：§set_trading_stop（line 559+）補 long/short SL 對 current price 的方向約束 + lock-profit SL 在未獲利倉被拒屬預期 fail-closed（防未來誤加 retry）。非阻，併入既有 BB1 字典 backlog。
2. **Sprint 3 incident-trigger 接上時 BB mandatory re-review**：屆時 set_trading_stop 真實觸發；驗 incident 頻率對 Position group rate budget、被拒比例（market 錯側 SL）對鎖利覆蓋率、live slot respawn 時 cmd_tx 不 stale（LIVE-AUTH-WATCHER 教訓）。
3. live 真錢首次 escalate 前確認 one-way 前提仍成立（hedge 啟用會復活 positionIdx corner case，須重審）。

BB AUDIT DONE: srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-29--c4_set_trading_stop_trust.md
