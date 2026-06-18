# E1 IMPL — flash_dip_buy Demo Pilot PHASE-1（待 E2 審查）

> 日期：2026-06-18 · 角色：E1 · 狀態：IMPL DONE，Linux build+test 綠，無 commit
> 方案：`docs/CCAgentWorkSpace/Operator/2026-06-18--PA--flash-crash-dipbuy-demo-pilot-design.md`
> baseline：main（srv git root）· Linux build 機：trade-core `~/BybitOpenClaw/srv`

## 任務摘要

建 PHASE-1 flash_dip_buy demo pilot：獨立 Strategy sibling 模組 + band-external nf cap +
kind-aware demo-gate + config TOML + env flag + boot 1d REST seed。全 flag-OFF 預設、
demo-only、所有單經既有單一寫入口 gate stack（emit `StrategyAction::Open(OrderIntent)`
PostOnly；N=3 `StrategyAction::Close`）。E1-C（CUSUM hot-path）DEFER 未建。6 must-fix 全折入。

## 修改清單

**新建（E1-A 純函式 + E1-D 策略本體）**
- `rust/openclaw_engine/src/strategies/flash_dip_buy/params.rs` — FlashDipBuyParams + StrategyParams + 4 純函式（compute_dip_level / is_first_tick_of_utc_day / hold_expired / fixed_notional_qty）+ 15 純函式單測
- `rust/openclaw_engine/src/strategies/flash_dip_buy/mod.rs` — FlashDipBuy impl Strategy（on_tick 三分支 / import_positions / on_fill / on_close_confirmed / seed_prior_close override / entry_ts sidecar 讀寫）
- `rust/openclaw_engine/src/strategies/flash_dip_buy/tests.rs` — 15 on_tick/lifecycle 整合測試

**修改**
- `strategies/mod.rs` — `pub mod flash_dip_buy;` + Strategy trait 加 default-no-op `seed_prior_close`
- `strategies/params.rs` — re-export FlashDipBuyParams + StrategyParamsConfig.flash_dip_buy + fail_closed_inactive_config
- `strategies/registry.rs` — `create_for_engine` kind-aware demo-gate（三合一）+ FLASH_DIP_PILOT_ENABLED_ENV const + 4 負測（在 strategies/tests.rs）
- `config/risk_config.rs` — GlobalLimits 加 `flash_dip_buy_max_notional_pct_equity` 欄 + default fn + Default + validate() 拒 >0.03/<=0
- `claude_teacher/applier_riskconfig.rs` — denylist 加 `limits.flash_dip_buy_max_notional_pct_equity` + 3 RiskConfig AC proof 測試
- `intent_processor/mod.rs` — `check_flash_dip_notional_cap` helper（band-external hard reject，kill-switch 1）
- `intent_processor/router.rs` — 兩條 Gate 2.7 path（process_with_features + process_gates_only_with_features）各 wire 1 行呼叫
- `event_consumer/bootstrap.rs` — boot 1d REST seed（"D" → seed_bars "1d" → get_buffer 最後收盤 + 2日 freshness → seed_prior_close）gate 在 Demo+flag+registered
- `settings/strategy_params_demo.toml` — `[flash_dip_buy]` block（active=false，26 symbols，K15/N3/C3/nf0.02）
- `settings/risk_control_rules/risk_config_demo.toml` — `[limits].flash_dip_buy_max_notional_pct_equity=0.03` + `[per_strategy.flash_dip_buy]`（enabled=false，max_concurrent_positions=3，26 symbols）+ max_order_notional_usdt 注記

## 治理對照（6 must-fix）

| # | must-fix | 落地 |
|---|---|---|
| 1 | 並發 C=3 band-external | `per_strategy.flash_dip_buy.max_concurrent_positions=3`（denylist `per_strategy` 前綴下，agent 不可放寬）；on_tick producer-side count 為軟層 fail-fast |
| 2 | survival floor 歸通用 cap | 宣稱記 P1 per_trade_risk_pct(2%) + position_size_max_pct + max_order_notional_usdt（label-independent，已 denylist）；新 cap key 在 intent.strategy 為 ADDITIVE。max_order_notional_usdt 維持 0（cross-cutting，留 risk-owner 決策，已 TOML 注記） |
| 3 | 新欄 3 AC proof | (a) validate 拒 >0.03/<=0 ✅ (b) denylist→`riskconfig_decide_leaf` HardBoundary ✅ (c) 漏列仍 DefaultDeny（用 hypothetical unlisted leaf 證 fail-closed by construction）✅ — 3 測全綠 |
| 4 | kind-aware demo-gate | 落 `create_for_engine`（Demo+env flag+active 三合一）；**禁** create_with_params。grep-proof：FlashDipBuy push 0 次在 create_with_params body；4 負測證 Paper=0/Live=0/create_all=0/flag-OFF=0 |
| 5 | 誠實 confidence | entry confidence=0.55*conf_scale（反映 day-clustered boot_t≈1.4 含 0 的不確定），不硬設高過 cost_gate min_confidence |
| 6 | wall-clock cadence | UTC 日判定 + hold + entry_ts 全用 `openclaw_core::now_ms()`（SystemTime epoch）；**禁** ctx.timestamp_ms（=event.ts_ms=WS payload-ts，Fix-4 教訓） |

## Open Questions 解法

- **Q1**（1d seed）：bootstrap 加 Demo+flag-gated 1d REST seed（`get_klines("D")` → `seed_bars(sym,"1d")` → 讀 get_buffer 最後已收盤 close + last_open ≤2日 freshness 檢查 → `seed_prior_close`）。stale/缺則該 symbol 當日 inert（fail-safe）。
- **Q2**（entry_ts 保真）：**empirically 不可靠** — startup/mod.rs:654 種倉用 `pos.updated_time`（非 createdTime）+owner="bybit_sync"，重啟+同向加倉後 entry_ts 與歸屬皆重置。`trading.positions` 表**不存在**（PG 直查 NULL，migration head=V145）→ 不走 migration。robust 選項=策略 fill 後持久化真 entry_ts 到 `OPENCLAW_DATA_DIR/flash_dip_buy_entry_ts.json` sidecar（atomic write-tmp+rename，fail-soft），import_positions 還原覆寫（first-write-wins 防加倉刷新；缺 sidecar 退回 paper_state ts）。
- **Q4**（26 universe）：extend_full.json `universe_composition.symbols`（n=26，n_possibly_delisted=0，與 overlap_validation 全 730-bar 0-mismatch 吻合）。入場硬篩=allowed_symbols fence + 既有 h0 gate + cross-strategy skip；scanner hard_filters（turnover/spread/status）由既有 gate stack 與 scanner 注入的 is_pinned 上下游覆蓋（pilot 不自建第二套篩，避免重複）。
- **Q3/Q5/Q7**：採 PA 默認（in-memory CUSUM 屬 deferred E1-C；exit day-clustered UTC 日首 tick；單 tranche K15/N3/C3）。

## 關鍵 diff（load-bearing）

cadence wall-clock（must-fix #6，mod.rs on_tick）：
```
// ctx.timestamp_ms = event.ts_ms = WS payload-ts；禁用。
let now_wall_ms = openclaw_core::now_ms();
```

band-external hard cap（kill-switch 1，intent_processor/mod.rs）：
```
if is_reducing || strategy != "flash_dip_buy" { return None; }
let pct = self.risk_config.limits.flash_dip_buy_max_notional_pct_equity;
if final_qty * price > balance * pct { Some(reason) } else { None }
```

## Linux build / test

- `cargo build --release -p openclaw_engine`：**rc=0**（2m29s）。3 warning 全 pre-existing（btc_lead_lag unused import / single_watcher dead fields / ma_crossover make_intent），**0 新 warning**。
- `cargo test --release -p openclaw_engine --lib`：**4077 passed / 0 failed / 1 ignored**（含 37 新測，無回歸）。
- 37 新測：15 純函式（params）+ 15 lifecycle（strategy on_tick/import/fill/restart）+ 3 RiskConfig AC proof + 4 demo-gate 負測。
- TOML parse 驗證（Linux tomllib）：兩 demo TOML OK，值正確（active=false / K0.15 / N3 / C3 / nf0.02 / 26 symbols / cap0.03 / per_strategy C=3）。

## 不確定之處 / Operator 下一步

1. **max_order_notional_usdt 仍 0（disabled）**：must-fix #2 要求「set/verify 為真 backstop」，但三環境皆 0 且改為非零會約束其餘 5 策略（cross-cutting risk policy）→ 我未 silently 變更，已 TOML 注記為 risk-owner（E3/operator）決策。pilot per-trade floor 已由 P1+position_size+新 cap 三層守。**請 E3/operator 裁示是否啟用通用上限**。
2. **entry_ts sidecar 而非 trading.positions migration**：因表不存在 + 無既有策略持久化先例，採 JSON sidecar（最小、無 DB 風險、跨重啟確定性）。若 E2/QC 偏好 migration 路徑，需先建整張 trading.positions 表（scope 擴大）。
3. **prior_close 每 boot 刷新**：on_tick 無 KlineManager 存取，prior_close 由 boot 一次性 seed（daily pilot 可接受）；跨日新 prior_close 依賴重啟或 daily backfill cron。Phase-1 demo 可接受；若要日內自動刷新需後續加 daily refresh hook。
4. **E1-C DEFER 確認**：未碰 step_4_5_dispatch.rs / orchestrator.rs / risk_cusum.rs（git status CLEAN）。death-rate metric 定義 + monitoring cron 屬 Phase-2 / QC（Q6 未定）。
5. **未部署 / 未 commit**：等 E2 審查 → E4 回歸 → PM 統一 commit+push。

E1 IMPLEMENTATION DONE: 待 E2 審查
