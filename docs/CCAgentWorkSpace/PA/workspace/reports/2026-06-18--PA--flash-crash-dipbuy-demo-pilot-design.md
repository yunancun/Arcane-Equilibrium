# PA 技術設計（build-ready）— Flash-Crash Dip-Buy Demo Pilot

> 日期：2026-06-18 · 作者：PA · 狀態：BUILD-READY（已折入 CC + E3 審查 must-fix）
> 審查結論：CC `APPROVE_WITH_CONDITIONS`（B 級，14/16，0 CRITICAL，0 硬邊界觸碰）· E3 `APPROVE_WITH_CONDITIONS`（0 CRITICAL / 0 HIGH / 3 MED / 3 LOW）
> baseline：main（CC 引 3bb56904+ / E3 引 3bb56904+）· 所有 file:line 已 PA 親讀復驗（見 §0 復驗）

---

## 0. PA 親讀復驗（CC/E3 兩條 callsite drift 親證）

兩位審查者各自獨立抓到同一組 callsite 漂移，PA 親 grep 全部證實——原 PA design prose 在這兩點是錯的，本最終版已更正：

| 漂移點 | 原 design prose（錯） | 親讀真相（證據） | 結論 |
|---|---|---|---|
| CUSUM 接線位置 | wire 進 `orchestrator.rs:106 dispatch_tick_with_cusum_filter` | orchestrator.rs:67 + :104 doc comment 明示「自 RC-04 起生產不再調用」「目前生產 hot path 尚未調用此方法」；`dispatch_tick_with_cusum_filter` **0 個 production caller**（grep 除 orchestrator.rs:106 定義 + :513 test 外無命中）。真 production loop = `step_4_5_dispatch.rs:357 split_borrow_for_dispatch()` + `:411 strategy.on_tick()` | **更正**：kill-switch (2)/(4-granular) 接線目標 = step_4_5_dispatch.rs hot-loop，非 orchestrator.rs:106 |
| demo-gate 落點 | gate 加在 `create_with_params (registry.rs:54)` | registry.rs:47 `create_for_engine(kind)` 立即委派 kind-blind 的 `create_with_params(registry.rs:54)`；後者亦被 `create_all()(registry.rs:41)` 呼叫（無 kind） | **更正**：gate 必落 kind-aware site（`create_for_engine` 本體 OR `bootstrap.rs:830` register loop），**禁** 落 `create_with_params` |

另親證（支撐 must-fix）：
- `per_strategy.max_concurrent_positions: Option<u32>`（risk_config_per_strategy.rs:67）存在；整個 `"per_strategy"` 前綴在 `RISKCONFIG_SURVIVAL_DENYLIST`（applier_riskconfig.rs:109）→ agent 不可放寬。**CC 條件 1 的硬層真實存在**。
- `limits.max_order_notional_usdt` 已在 denylist（applier_riskconfig.rs:146）→ label-independent 通用 notional 上限存在。**E3 MED-2 backstop 真實存在**。
- allowlist-default-deny catch-all：未列葉 → `VetoedByDefaultDeny`（applier_riskconfig.rs:63/80）。**CC 條件 2(c) / E3 #4 的 fail-closed-by-construction 成立**。
- `position_size_max_pct` 跨欄受 `limits.position_size_max_pct` 約束（risk_config_per_strategy.rs:181-190）。

---

## 1. 修正後的整合方案（corrected integration approach）

**DECISION（不變）**：新建獨立 Strategy-trait 模組 `strategies/flash_dip_buy/`，作為既有 5 參考策略的 sibling，經引擎正常 tick-driven `on_tick` 調用。**不是** daily bin、**不是** out-of-band 迴圈。

**Rust-first 合規**：整體在 Rust openclaw_engine 內以 `dyn Strategy`（strategies/mod.rs:90 trait）實作，經 `StrategyFactory`（registry.rs）註冊。無 Python 交易真相。

**單一寫入口合規（Root Principle 1）**：策略只回 `Vec<StrategyAction>`，持有 0 個 OrderManager/REST handle（E3 #1 grep-proof：strategies/ 內 0 個 `place_order`/`OrderManager`/`reqwest`/`v5/order`）。daily bin 會開第二寫入口=違憲，已拒。

**daily 視野** 純由策略「內部 cadence state」達成（只在 UTC 日首 tick 動作），非獨立 scheduler——既有 infra（gate / sizing / position tracking / resting-order sweep / maker close）原樣復用。

修正後的整合邊界（兩處 callsite 對齊真相）：
- demo-gate：落 `create_for_engine`（registry.rs:47，kind-aware）或 `bootstrap.rs:830` register loop。**禁** `create_with_params`。
- 線上熔斷 wire：落 production hot-loop `step_4_5_dispatch.rs:357/411`。**禁** `orchestrator.rs:106`（非生產路徑）。

---

## 2. 單一寫入口路由（single-write-entry routing，唯一受控寫入口）

Maker limit BUY 與 N=3 Close 兩條腿全程同一路由，順序：

1. 策略 emit `StrategyAction::Open(OrderIntent)`（strategies/mod.rs:74）/ `Close`（mod.rs:80），經 `OrderIntent::new_trade(...)`（intent_processor/mod.rs:265）構建，帶 `order_type="limit"` / `limit_price=Some(prior_close*(1-K))` / `time_in_force=Some(PostOnly)` / `maker_timeout_ms=Some(ms_to_utc_day_end)`（四欄存在於 OrderIntent struct，mod.rs:199/200/216/226）。
2. production per-strategy loop 收集：`step_4_5_dispatch.rs:357 split_borrow_for_dispatch()` → `:411 strategy.on_tick()`（**真 production loop**，非 orchestrator.rs:74 的 test/batch 變體）。
3. gate stack `IntentProcessor::process`（router.rs:171）依序：Gate1 auth(216) → Gate1.4 lease(235) → Gate1.5 dup(247) → Gate1.6 neg-bal(269) → Gate2 Guardian(336) → Gate2.5 Kelly(398) → Gate2.6 P1 cap(412，`kelly_qty.min(p1_max_qty)` :420) → qty=0 reject(437) → Gate2.7 check_order_allowed(476) + global_notional_cap(500) → Gate3 cost_gate(509)。新的 band-external notional reject 加在此 stack 內（見 §6 kill-switch 1）。
4. 核准 → `OrderDispatchRequest`（tick_pipeline/mod.rs:748，帶 maker_timeout_ms :796）→ `order_dispatch_tx`（mod.rs:978，emit at step_4_5_dispatch.rs:846）。
5. event_consumer order-dispatch task（bootstrap.rs:821 `spawn_order_dispatch`）→ `OrderManager::place_order`（order_manager.rs:354）→ Bybit V5 `/v5/order/create` PostOnly。

**無獨立下單路徑**。N=3 Close 腿亦走此鏈（經 close dispatch 尊重 `use_maker_close`，tick_pipeline/mod.rs:975 → commands.rs:109 → maker-first/toward-touch reprice pending_sweep.rs:94 → 強制 taker fallback）。maker timeout cancel 復用 `pending_sweep::cancel_resting_maker_order`（pending_sweep.rs:232）。

**誠實 confidence（E3 #5 折入）**：cost_gate 的 `min_confidence` 是 live gate；策略**必須** emit 真實 confidence 進 Open intent，**禁** 為過 cost_gate 硬設高 confidence。AC 納入（見 §7 E1-D）。

---

## 3. daily cadence 機制

UTC 日首 tick 檢測，用 tick clock，無排程 hook、無第二執行緒：
- 策略持 `last_acted_utc_day: HashMap<String,i64>`。`on_tick` 內 `today = (ctx.timestamp_ms / 86_400_000) as i64`；若 `today > last_acted_utc_day[symbol]` → 武裝當日入場（掛 prior_close*(1-K) maker limit），再 set。當日後續 tick 對入場 no-op。
- **wall-clock 來源（折入 memory 2026-06-15 Fix-4 教訓 / CC LOW-1）**：`ctx.timestamp_ms` 須用與 Fix-4 repoint 相同的 wall-clock atomic source，**禁** 用 payload-ts（`shared_last_tick_ms` 曾誤存 payload ts 致 cadence 污染）。AC 納入。
- miss-a-day（無 tick 到達）= no-trade = fail-safe。

---

## 4. prior_close 來源（CRITICAL，乾淨 1d，leak-free）

WS 只訂 intraday（1m/5m/15m/60m/240m），1d buffer **不由** live WS 聚合器填充。乾淨 prior_close 來源：
- **primary**：boot-time REST seed `MarketDataClient::get_klines(interval="D")`（market_data_client/mod.rs:87）→ `KlineManager::seed_bars(symbol,"1d",bars)`（klines.rs:634）→ 讀 `get_buffer(symbol,"1d")`（klines.rs:547）取「最後一根已收盤 1d bar」（`last_closed_open_time_ms(symbol,"1d")` klines.rs:559，**非** building bar）。
- **fallback**：DB `market.klines WHERE timeframe='1d'`（daily_kline_backfill cron 寫，與 intraday disjoint）。
- **leak-free**：用前一完整 UTC 日收盤價，於次日使用。

**E3 LOW-1 / Q1 確證**：bootstrap kline seed（bootstrap.rs:889）目前只 fetch 1m+5m，1d buffer 由 daily backfill cron 填，**boot 時無 1d 來源** → pilot 在首次 daily backfill 前 inert（fail-safe 但 silent）。**必須** 在 E1-D 前解決：加 26 pilot symbols 的 boot 1d REST seed + 1d-freshness healthcheck。(Q1，E1 blocker)

---

## 5. maker limit 掛單 / hold-exit / 重啟存活（不變，摘要）

- **掛單**：PostOnly LIMIT BUY 靜態深價 `prior_close*(1-K)`（K=0.15；alt K=0.20）。**禁用** `compute_post_only_price`（maker_price.rs:256，那是 inside-quote at-touch 用）；直接 set `limit_price`。同-tick crash 致 PostOnly 被拒 → `on_post_only_rejected`（mod.rs:226）武裝 cooldown。
- **fill 檢測**（復用 0 新碼）：demo sim 經 `RestingLimitOrder`（resting_orders.rs:262）+ `sweep_resting_limit_orders_for_symbol`（:510）；真交易所經 private fill WS；`on_fill`（mod.rs:150）eager sync；PostOnly maker fill recog at step_4_5_dispatch.rs:1592。
- **日終撤單**：`maker_timeout_ms` → `RestingLimitOrder.deadline_ms` → 既有 timeout sweep（pending_sweep.rs:232 / resting_orders.rs:83 Timeout）。靜態價不 reprice（reprice 只用於 close 腿）。
- **hold-exit**：N=3 日，從 `PaperPosition.entry_ts_ms`（containers.rs:25）算，`owner_strategy=="flash_dip_buy"`（containers.rs:47）。`ctx.timestamp_ms - entry_ts_ms >= 3*86_400_000` → emit `Close{reason:"flash_dip_hold_3d_expiry"}`。「exit at close」**預設 gate 到 UTC 日首 tick**（保持 day-clustered，對齊研究面板；除非 operator 另指——見 Q5）。
- **重啟存活**：positions 從 Bybit demo snapshot 還原（seed_positions → `import_positions` bootstrap.rs:367，帶真 entry_ts_ms）→ triage 重新歸屬（bootstrap.rs:420）→ 策略 `import_positions` override（mod.rs:169，W7-5 pattern）filter `owner_strategy==self.name()` 重建內部集。N=3 倒數活在 position record，跨重啟確定性重建。**Q2 caveat**：Bybit demo snapshot 是否跨 accumulation/restart 保真原始 entry time（createdTime）須確認；若重置則 persist entry_ts_ms 進 trading.positions checkpoint（小 migration，Guard B + double-apply + Linux PG dry-run）。**E3 LOW-2**：triage（bootstrap.rs:420）按 scanner-universe 重新歸屬 bybit_sync 倉，universe 重疊時 flash_dip 倉可能誤歸屬，污染 hold clock + 並發計數 → Q2 緩解。

---

## 6. Kill-switches 實作（折入 must-fix）

**(1) nf≤3% band-external HARD limit**：新 `RiskConfig.limits.flash_dip_buy_max_notional_pct_equity`（risk_config.rs:382 GlobalLimits；validate() 拒 >0.03 或 ≤0）。在 gate stack（router.rs Gate2.7 region，final_qty 已知後）做 **hard reject**（非 soft scale）。
  - **E3 MED-2 折入（label-conditional 弱點 + backstop）**：此 cap key 在 `intent.strategy=="flash_dip_buy"`（self-asserted String），故 (a) 只約束自標 flash_dip_buy 的單；(b) 策略 bug 誤標/清空 strategy 字串會**繞過自己的 cap**。**真通用 survival floor = P1 `per_trade_risk_pct`(2%) + `check_order_allowed.position_size_max_pct`**（兩者 label-independent + 已 denylist）。→ **必須同時** 設 label-independent `limits.max_order_notional_usdt`（已 denylist，applier_riskconfig.rs:146）作真 backstop；survival-floor 宣稱改記在 P1/position_size，**不**記在 label-conditional cap。
  - **survival denylist（CC 條件 2 / E3 #4）**：顯式加新欄入 `RISKCONFIG_SURVIVAL_DENYLIST`（applier_riskconfig.rs:90 limits.* 段）= defense-in-depth；即使漏列，default-deny catch-all 仍 `VetoedByDefaultDeny`（fail-closed by construction）。`limits.*` 從不在 allowlist candidates。

**(2) 已實現-條件-死亡率線上熔斷**：復用 dormant CUSUM（risk_cusum.rs:56 `evaluate_downside_cusum`，`CusumConfig.enabled=false` :35）。**接線目標 = production hot-loop `step_4_5_dispatch.rs:357/411`（已更正，非 orchestrator.rs:106）**。餵料 = `trading.fills` realized_pnl per strategy（DB 可信聚合，非 attacker-injectable，E3 #5）。online metric = 已平 deep-K slots 中 realize ≥X% loss 的比例；> 3% → auto-shrink nf 或 pause。MVP：in-memory CUSUM window，boot 時從 trading.fills aggregate 重建（無 migration，Q3）。
  - **Q6（QC，E1-C blocker）**：死亡率指標精確定義（X 閾值 + 觸發前 min sample n，防低樣本自觸發）須在 E1-C 前由 QC 定清。

**(3) 並發上限 C=3 HARD（CC 條件 1 折入）**：**band-external 強制層 = `per_strategy.flash_dip_buy.max_concurrent_positions`**（risk_config_per_strategy.rs:67，在 denylist `per_strategy` 前綴下，agent 不可放寬）。producer-side count（on_tick 內 filter `owner_strategy=="flash_dip_buy"` ≥3 則 skip）保留為 fail-fast 軟層。**策略 bug 時硬上限仍由風控層守**。

**(4) daily portfolio-loss + GRANULAR per-strategy breaker**：portfolio 部分已存（step_6 priority 9 daily-loss halt，risk_checks.rs:156 + session_drawdown :435）。granular per-strategy（2026-06-15 RCA 已知缺口）= **同 (2) 的 CUSUM down-edge alarm 接進 hot-loop** → block 該策略 dispatch。引擎級閉缺口，但 default 只對 flash_dip_buy enabled 保持 surgical。

**(5) 9 安全不變量 + 16 根原則**：demo engine_mode 硬鎖（PipelineKind::Demo），策略結構性缺席 Live factory 路徑（見 §8）；pre-trade audit/replay、lease-before-execute、fills 寫表、fail-closed degrade、authorization 過期 shutdown 全繼承不變。無任何不變量放寬。

---

## 7. E1 任務拆分（ordered + 並行旗標 + 驗收）

**並行群組**：`{E1-A, E1-B}` 立即啟動（file-disjoint）。`E1-C ∥ E1-D` 皆依賴 E1-A 完成，且彼此 file-disjoint（orchestrator/risk_cusum/step_4_5_dispatch vs flash_dip_buy/），並行跑。`E1-E` 最後整合。

### E1-A — 純函數核心（FIRST，parallel-safe）
檔：`flash_dip_buy/params.rs` + helpers（`compute_dip_level(prior_close,k)` / `is_first_tick_of_utc_day(ts,last)` / `hold_expired(now,entry_ts,3d)` / `fixed_notional_qty(equity,nf,price)`）。
**AC**：level 數學單測；day-boundary edge（UTC 午夜、重啟日、整數日嚴格大於）；nf qty 單測；全獨立可測無 engine 依賴。

### E1-B — band-external cap（∥ E1-A）
檔：`config/risk_config.rs:382`（加 `flash_dip_buy_max_notional_pct_equity` serde default 0.03 + validate() bound）+ `applier_riskconfig.rs:90`（denylist 入列）。
**AC（CC 條件 2 三項缺一不可 sign-off）**：(a) validate() 拒 >0.03 或 ≤0；(b) 新欄入 `RISKCONFIG_SURVIVAL_DENYLIST` 且 `riskconfig_decide_leaf` 對完整路徑回 HardBoundary（單測 assert）；(c) 退一步漏列 denylist 仍回 `DefaultDeny`（單測 assert，證 fail-closed by construction）。double-apply/hot-reload 保持 default。**E3 MED-2**：同時設 `limits.max_order_notional_usdt` backstop（已 denylist）。File-disjoint。

### E1-C — CUSUM hot-path wire + per-strategy realized breaker（依賴 E1-A；HIGH RISK）
檔：`step_4_5_dispatch.rs`（hot-loop，**更正後真 callsite**）+ `risk_cusum.rs` + realized-net 餵料。把 per-strategy realized-net CUSUM filter 接進 production dispatch（兩案擇一，E1-C prompt 須釘明）：(方案A) production loop 改路由經 `Orchestrator::dispatch_tick_with_cusum_filter`；(方案B) step_4_5_dispatch hot-loop 直接加 blocked 檢查。gate scope 限 flash_dip_buy。
**AC**：>3% death-rate 餵料 → 策略被 block；健康餵料 → dispatch 不變；`cusum.enabled=false` → **其他 5 策略 dispatch 路徑 byte-identical**。**前置**：Q6（死亡率指標 + min sample n）須 QC 先定。**E2 focus 重點**（見 §9）。

### E1-D — 策略模組本體（依賴 E1-A）
檔：`flash_dip_buy/mod.rs` impl Strategy（on_tick：day-arm 入場 / hold-expiry close / 並發 cap producer-side soft / fixed-notional emit via `OrderIntent::new_trade` PostOnly）+ import_positions/on_fill/on_close_confirmed overrides + prior_close 讀 KlineManager 1d / DB fallback。
**AC**：日首 tick emit PostOnly limit @ prior_close*(1-K)；C=3 producer-side soft 生效 **AND** per_strategy 層硬拒 >3 開倉（CC 條件 1，非僅策略內 skip）；3d expiry emit Close；重啟重建 set；**cadence 用 wall-clock atomic source 非 payload-ts**（memory Fix-4）；**emit 真實 confidence 非硬設高值**（E3 #5）。依賴 E1-A。

### E1-E — wiring + config + flag（LAST，依賴 E1-B/D）
檔：`registry.rs:47 create_for_engine`（**kind-aware** demo+flag gate，**禁** create_with_params）/ `bootstrap.rs:830` / `strategy_params_demo.toml [flash_dip_buy]` block（active=false，allowed_symbols=26 survivors）/ env flag / boot 1d REST seed（Q1）。
**AC（grep-proof）**：flag OFF → 註冊 0 次（grep-proof 負測）；Demo+flag+active → 註冊；**Paper/Live → 永不註冊**（負測 assert 策略在 Paper/Live pipeline 註冊 0 次，僅 Demo 出現）。

---

## 8. demo-gating + Live 5-gate（不觸碰）

註冊條件三合一：(a) env `OPENCLAW_FLASH_DIP_PILOT_ENABLED` set AND (b) TOML `active=true` AND (c) `PipelineKind::Demo`。**落點：kind-aware `create_for_engine`（registry.rs:47）push 前 OR bootstrap.rs:830 register loop——禁 create_with_params（kind-blind，亦被 create_all/replay_runner 用，E3 MED-1）**。

fail-closed：flag OFF 預設 + active=false 預設（對齊 funding_harvest/funding_short_v2/liquidation_cascade_fade）+ 非-Demo kind 不建構。

Live/mainnet 5-gate **零修改**：策略 kind!=Demo 不建構 → 結構性排除 Live factory 分支 → Live pipeline 的 strategy vector 不含它 → IPC `set_strategy_active("flash_dip_buy")` 在 Live 回 `Err("strategy not found")`（orchestrator.rs:258）。無新 live-write IPC、無 token path 改、無 `execution_state/authority/live_execution_allowed/max_retries` 觸碰（指紋掃 0 命中）。**不繼承** 2026-06-17 Phase-3 RiskConfigDirectiveSink 的 AUTH-1 IPC-chokepoint-bypass concern（本策略走 IntentProcessor，非 in-process ConfigStore sink，E3 #6）。LiveDemo 不降級（Demo pipeline 繼承同 auth/TTL/risk/audit）。

---

## 9. E2 重點審查 3 點

1. **CUSUM hot-path wire 對其他 5 策略零行為差**：`cusum.enabled=false` 時 step_4_5_dispatch.rs:357/411 dispatch 路徑對其他 5 策略 byte-identical（HIGH RISK hot path 回歸）。
2. **notional 不可超 3%**：cap 是 hard reject 非 scale，且在 Kelly/P1 交互下 effective qty = min(target, Kelly, P1) 永遠保守；驗無任何路徑令 flash_dip_buy notional 超 3%；驗 label-conditional cap 弱點由 P1(2%)/position_size + `limits.max_order_notional_usdt` backstop 覆蓋。
3. **demo-only gating 結構性 grep-proof**：Live factory 分支永不建構此策略；負測證 Paper/Live 註冊 0 次、僅 Demo 出現；gate 落 kind-aware site 非 create_with_params。

---

## 10. 派發摘要（main session 用於 E1→E2→E4→QA build chain）

> **建構期合規已綠**（CC B 級 14/16 + E3 0 CRITICAL/0 HIGH），3 條 MED 全為 sign-off/AC 閘非代碼阻斷，可啟動 E1。**runtime 證據（maker fill 真實率 / death-rate 先驗 falsification）歸 QA**，非建構期。

**啟動順序**：
- 即刻並行：**E1-A**（純函數+params）∥ **E1-B**（band-external cap + denylist + max_order_notional backstop）。
- E1-A 綠後並行：**E1-C**（CUSUM→step_4_5_dispatch hot-loop，HIGH RISK，前置 Q6）∥ **E1-D**（策略本體）。
- 最後：**E1-E**（kind-aware gate + TOML + flag + 1d boot seed）。
- → **E2**（×對抗，重點 §9 三點，HIGH RISK 項回歸）→ **E4**（scratch-DB E2E：日首 tick emit→gate→dispatch→sim fill→3d close；重啟重建 hold clock；flag-OFF 不註冊 grep-proof）→ **QA**（runtime falsification：sim fill rate vs Bybit demo 真 fill 對照；death-rate 先驗驗證；per-strategy CUSUM 觸發實證）。

**E1 dispatch prompt 必釘的 4 條更正/條件**（否則會誤導 E1）：
1. CUSUM wire 落 `step_4_5_dispatch.rs:357/411`，**非** orchestrator.rs:106（後者 RC-04 起非生產）。
2. demo-gate 落 kind-aware `create_for_engine`(registry.rs:47) / bootstrap.rs:830，**非** kind-blind create_with_params(registry.rs:54)。
3. 並發 C=3 硬層用 `per_strategy.max_concurrent_positions`（risk_config_per_strategy.rs:67，denylist 下），producer-side 僅軟層。
4. survival-floor 真backstop = P1(2%)/position_size + `limits.max_order_notional_usdt`（label-independent，已 denylist）；新 label-conditional cap 僅 additive；E1-B AC 三項（validate/denylist-HardBoundary/漏列仍 DefaultDeny）缺一不可 sign-off。

---

## 11. 待解 operator / QC open questions

| # | 歸屬 | 阻塞點 | 問題 | PA 建議 |
|---|---|---|---|---|
| Q1 | operator/QC | **E1-D blocker** | demo pipeline boot 是否已 REST seed 1d（"D"）klines？親證 bootstrap.rs:889 只 fetch 1m+5m → 1d 無 boot 來源，pilot 在首次 daily backfill 前 silent inert | 加 26 symbols boot 1d REST seed + 1d-freshness healthcheck |
| Q2 | operator | **E1-D blocker** | Bybit DEMO position snapshot 是否跨 restart + 同向 accumulation 保真原始 entry time（createdTime）？N=3 hold clock 依賴 entry_ts_ms 存活 | 若 Bybit 重置 → persist entry_ts_ms 進 trading.positions checkpoint（小 migration，Guard B + double-apply + Linux PG dry-run） |
| Q3 | operator | E1-C decision | per-strategy realized-death-rate 線上狀態：in-memory CUSUM window（boot 從 trading.fills 重建，無 migration）vs 持久 `learning.flash_dip_realized_death` 審計表（需 migration）？ | **MVP：in-memory + boot rebuild，無 migration** |
| Q4 | QC | **E1-E blocker** | 26 survivor large-cap universe 確切 symbol list（研究面板 ≥2yr 連續上市的 26）。scanner_config.toml 現 pin 25（不同用途），pilot 需自己的 allowed_symbols。+ 入場硬 delisting/illiquidity 篩：復用 scanner hard_filters（min_turnover_24h/max_spread_bps/status!=Closed）或更嚴 pilot-specific gate？閾值？ | 提供 canonical 26 + 確認篩選閾值 |
| Q5 | operator/QC | E1-D 默認可定 | 「exit at close」：day-N+3 首 tick AT/AFTER（tick-driven，可能 N+3 intraday-open）vs 嚴格 gate 到 UTC 日首 tick（day-clustered，對齊面板）？ | **預設後者**（day-clustered）除非另指 |
| Q6 | QC | **E1-C blocker** | kill-switch(2) 已實現-條件-死亡率精確定義：已平 deep-K slots 中 realize ≥X% loss 的比例（X=？，breaker 觸發前 min sample n=？防低樣本自觸發），使 3% 閾值 well-defined | 須 E1-C 前定清 |
| Q7 | operator | E1-E 默認可定 | pilot 單 tranche K=0.15/C=3，或並行 alt K=0.20/C=5 第二 tranche？並發 cap + config 不同 | **建議單 config（K15/N3/C3）先跑，保持測量乾淨** |

**E1 blocker 小結**：Q1（1d seed）、Q2（entry_ts 保真）、Q4（26 symbol list + 篩選閾值）、Q6（death-rate 指標）須在對應子任務啟動前由 operator/QC 回。Q3/Q5/Q7 有 PA 默認可逕行。

---

## 12. 降級 / rollback 路徑

- **flag rollback**：`OPENCLAW_FLASH_DIP_PILOT_ENABLED` unset / `active=false` → 策略不建構不註冊不 emit。**單一 env flag 即可全停**，無需 rebuild（active=false 走 hot-reload TOML）。
- **CUSUM rollback**：`cusum.enabled=false`（既有預設）→ hot-loop filter 對全策略 no-op，byte-identical 既有行為。E1-C 接線必須保證此性質（E2 回歸驗）。
- **cap rollback**：新 GlobalLimits 欄 serde default 0.03，移除/缺失 → 退回 P1(2%) + position_size 通用上限（更保守）。
- **整模組 rollback**：策略 file-disjoint（自有 dir）+ config 加欄 additive；移除策略 dir + 還原 registry/bootstrap gate 兩行 + risk_config 一欄即完整回退，不影響其他 5 策略。
- **fail-safe 缺省**：cold-start no-trade（flag OFF + active=false + 缺 1d seed → inert）。worst case = demo 測量誤差，非資本損失（demo-only，零真錢）。
