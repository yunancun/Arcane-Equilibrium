# 2026-04-17 Daily Summary

P0-10 SCANNER-GATE 死循環收線 + 自適應出場/fast-track 範圍化 + MICRO-PROFIT-FIX-1 全生命週期（RCA→設計→部署→核實）+ P1-8 DUST-EVICTION-GAP-1 E1/E4 + FUP tick-level retriage + P0-6 LiveDemo cost-gate profile 破 cold-start 死鎖。Engine lib 測試從 1342 → **1415 (default) / 1420 (ort)** 全綠 0 fail。

## 完成項目 / Completed

### P0-10 SCANNER-GATE 死循環修復（commit `7131250`）
**問題**：策略在 scanner 輪替出的 symbol 上反復「開倉 → orphan_handler A4 強平 → 策略再開」。BASEDUSDT 為首例，影響 20+ symbols（ENJUSDT 45 筆、CLUSDT 28 筆、AAVEUSDT 23 筆），共 **228 筆 `ipc_close_symbol` fills** / 24h。

**三部分修復**：
- **Fix 1 SCANNER-GATE**：`tick_pipeline/mod.rs` 新增 `symbol_registry: Option<Arc<SymbolRegistry>>` + setter + bootstrap wiring；`on_tick.rs` 在 strategy Open dispatch 前加 `reg.is_active(symbol)` 檢查，非活躍 symbol `continue`
- **Fix 2 FUP-RACE**：`paper_state.rs` 新增 `proactive_mirror_insert(symbol, is_long)`；OrderDispatchRequest 發送後立即呼叫，彌合 REST 下單 → WS Fill 空窗期 reconciler 誤判 orphan 的 race
- **Fix 3 A4 移除**：`orphan_handler.rs` Stage A4 邏輯刪除（enum 變體 `HardSafetyNotInUniverse` 保留 DB backward compat），orphan 定義回歸正確語義 —「僅指重啟/故障後遺留的舊倉位」，非 scanner 輪替
- **測試**：engine lib 1342 → **1351** passed；orphan_handler 17/17（含 2 個更新的 A4 測試）；core 380
- **部署**：`restart_all.sh --rebuild`

### Adaptive Exit Persistence + Fast-Track Scoping（commit `baa75a2`，proposal `68cfcb2`）
Proposal 見 `docs/references/2026-04-17--adaptive_exit_fasttrack_proposal.md`（A1/A2/B1/B2 四變更）。

- **A1 ER-scaled exit persistence**（`strategies/ma_crossover.rs`）：新增 `exit_persistence: PersistenceTracker`（與入場獨立）；`compute_exit_persistence_ms(er) = min_persistence_ms × (1 − ER).clamp(0)`；`on_external_close` 同步 clear；choppy 市場不再首 tick 誤平
- **A2 Trend-adaptive cooldown**：新增 `max_cooldown_boost: f64`（default 3.0，`[0, 10]`，agent_adjustable / db_persisted）；`trend_score = 0.6 × adx_factor + 0.4 × hurst_factor`；`multiplier = 1 + trend_score × max_cooldown_boost`（default 最大 4×）
- **B1 Symbol-scoped ReduceToHalf**（`fast_track.rs`）：新增 `is_drop_scoped_reduce` classifier；on_tick ReduceToHalf positions filter 加 `!drop_scoped || p.symbol == held_drop_symbol`。Normal/Cautious/Reduced + 5% + 3σ → 僅減半觸發 symbol；Defensive+/margin crisis/≥15% → 全倉減半不變
- **B2 Sigma-proportional cooldown**（`tick_pipeline/on_tick_helpers.rs`）：`FtReduceStamp = (halving_ts, effective_cooldown_ms)`；`ft_reduced_symbols: HashMap<String, FtReduceStamp>`；冷卻**觸發當時**鎖定不受後續 σ 衰減影響；`sigma_scaled_reduce_cooldown_ms(σ) = base × max(1, σ/3)` clamp 到 `FT_REDUCE_COOLDOWN_MAX_MS = 600_000`（10× base 硬上限）
- **測試**：+25 測試（A1:5 / A2:8 / B1:7 / B2:5）+ 4 既有 P0-5 測試遷移到 tuple stamp；engine lib 1351 → **1380** / 0 failed
- **部署**：20:55 local / PID 1364222 → **1771173**；`strings` 驗證新符號烘焙

### MICRO-PROFIT-FIX-1（RCA → 設計 → 部署 → 核實，commits `2170432` → `d9e2560`）

#### RCA（worklog `2170432`）
**觸發**：Operator 觀察「全部交易都是微利」。48h demo fills（PID 1364222+1771173）：3210 fills / 924 勝 / 875 負 / **1411 零盈虧** / net +$17.15。87.5% PnL 落在 ±$0.20。

**兩大獨立微利源**：

1. **`risk_close:COST EDGE ratio ≥100x`** × 162 fills — 公式 `cost_ratio = 2 × fee_rate × 100 / pnl_pct`（`position_risk_evaluator.rs:76-82`）；配置 `cost_edge_max_ratio = 100.0`（default 0.8 被改到 100 意圖「放寬」方向錯）。Bybit taker 0.055% → `0.11 / pnl_pct ≥ 100` → **pnl_pct ≤ 0.0011% 就觸發**（breakeven 區）。實測 `ratio 128.69 pnl 0.00%` / 極端 `ratio 5619309260446`（pnl ≈ 2×10⁻¹⁴%）。**澄清**：分母是實時浮盈 %，與 `edge_estimates.json` **無關**（原假設錯，空集屬 P1-7 獨立問題）

2. **`risk_close:fast_track_reduce_half`** × **989 fills (31%)**，avg |PnL| $0.068，小計 −$10.33 — 正常入場 notional ≈ $70；實測 15:00 hr 96 fills avg **$5.29**（halve 4 次）、11:00 hr avg **$1.90**（halve 5-6 次）。根因：60s 冷卻 + risk_level 長時間卡 Cautious/Defensive（HashMap clear 只在 Normal）→ 每 60s 一批再半倉 → dust 化。**90% margin_utilization gate 非觸發源**（leverage_max=100 + total_exposure_max_pct=200% 下 max margin_util = 2%），intentional cash-mode fail-safe 不動

**設計（凍結）**：
- **方案 A 相對名義底線**（勝過 halve_count 方案 B，因 grid/strategy_close/IPC 手動削倉 B 看不到）— `PaperPosition.entry_notional: f64`；filter `(qty × price) / entry_notional ≥ 0.25`；accumulate 語義（開倉 set、同方向加倉 `+=`、reduce 不動、direction flip 重設）
- **Config 方案 ② 窄帶激活** — `cost_edge_max_ratio = 0.2`（上界 pnl_pct ≤ 0.55%）+ `min_profit_to_close_pct = 0.3%`（下界）→ **激活帶 `[0.3%, 0.55%]`**（taker）；語義「利潤在縮但還抓得住」lock-in

**PM 核實補強（compact 後）**：
- validator 縮窄 `[0, 100]` → `[0, 10]` 需配套 `sanitize_legacy_budget_config` legacy migration 防舊 snapshot (`100.0`) 反序列 fail-close
- `entry_notional` 於同方向加倉明確採**累加語義**（拒絕「首次凍結」偏小早停、「重設」filter 恆 1.0 失效）

#### 部署（commit `d9e2560`，16 檔 +886 / −66）
**核心改動**：
- `config/budget_config.rs` — `cost_edge_max_ratio` 0.8→0.2；新增 `min_profit_to_close_pct` 0.3；validate `[0,10]`/`[0,5]`；+3 單測
- `config/legacy_migration.rs` — `sanitize_legacy_budget_config` 原地 clamp + warn；+2 單測
- `config/risk_config.rs` + `risk_config_tests.rs` — `ft_min_notional_ratio_of_entry` 0.25，`[0,1]`；default/range/serialization 三件套
- `risk_checks.rs` + `position_risk_evaluator.rs` + `tick_pipeline/mod.rs` — dual-gate `ratio ≥ max AND pnl ≥ min_profit` 參數穿透；訊息加 `min_profit=X%`
- `paper_state.rs` — `PaperPosition.entry_notional` + accumulate 語義 + direction flip reset + `migrate_legacy_entry_notional()`；+4 單測
- `tick_pipeline/on_tick.rs` — fast_track filter；物化 `(sym, is_long, qty, entry_notional)` 避開 borrow 衝突；0.0/零 fail-open
- `settings/risk_control_rules/budget_config.toml` — `cost_edge_max_ratio = 0.2` + `min_profit_to_close_pct = 0.3`
- `tests/micro_profit_fix_integration.rs` — **新檔，7 整合測試**（僅用公開 API）
- `startup.rs` — BudgetConfig 兩段載入：parse-no-validate → sanitize → validate

**E2 Adversarial Audit**：APPROVED_WITH_NITS（3 非阻塞 nit：`migrate_legacy_entry_notional` 未 wire 進 startup、`export_state` doc、`ratio=0.0` 顯式 fail-open test）。

**測試回歸**：engine lib 1351 → **1415** (default) / 1348 → 1420 (ort) +64/+72；core 380、e2e 35、reconciler_e2e 19 不變；`micro_profit_fix_integration` +7（新檔）；Python 2898 / 5 skipped 不變。

**部署時間線**（CEST local）：
- 22:02:29 首次 `restart_all.sh --rebuild` / PID **1814952**
- 22:13:50 commit `d9e2560` 落地
- 22:20:57 二次 rebuild 後 PID **1827304**（當前活躍，帶入 P1-8 + P0-6 WIP）

**Runtime 核實**（PID 1814952 log 18min 窗口）：
- 新格式樣本：`COST EDGE: ratio 0.36 >= 0.20, pnl 0.30% >= min_profit 0.30% (suggest close while profitable)` × 11
- pnl 觸發值 0.30%-0.31% 正好落在設計窄帶 `[0.3%, 0.55%]` 下限
- `strings` 驗證 binary 含 `min_profit_to_close_pct` / `ft_min_notional_ratio_of_entry` / `MICRO-PROFIT-FIX-1 BudgetConfig legacy fields clamped` / `MICRO-PROFIT-FIX-1: skip ReduceToHalf` 等標記
- 舊 PID 1771173 log 對照：`ratio 290.18 >= 100.00, pnl 0.00%`（舊 breakeven dust trigger）→ 新格式 22:02 後零出現，對比鮮明

### P1-8 DUST-EVICTION-GAP-1 E1/E4 + FUP retriage_synthetic_owner（commit `51183ca`）
*此工作流與 MICRO-PROFIT-FIX-1 同日部署但獨立 commit，無獨立 worklog — 以下整理自 commit message + `CLAUDE_CHANGELOG.md` + CLAUDE.md §十一。*

**P1-8 E1/E4 Dust-aware bybit_sync triage**：
- 新增 `DUST_FROZEN_STRATEGY` 常量 + `TriageOutcome.dust_frozen` 分支
- `triage_bybit_sync` 加入 `dust_check` 閉包參數：名義值 < 交易所 `min_notional` 時**不驅逐**、**不派 CloseSymbol**（dispatch pre-flight 會拒 + Bybit 會 retCode=170124），改凍結為 `DUST_FROZEN_STRATEGY` owner，避免引擎/交易所無聲偏差
- `event_consumer` 組裝 `ref_prices` + `shared_instruments` 接線，啟動 triage 用 `dust_check`
- +5 triage 測試（dust frozen / evict / adopt 邊界）

**P1-8 FUP Tick-level retriage_synthetic_owner**：
- 新增 `SYNTHETIC_OWNER_LABELS` 常量（`bybit_sync` / `orphan_adopted` / `orphan_frozen`）
- `paper_state.retriage_synthetic_owner` 返回 `RetriageOutcome` 四分支（`NoOp` / `FrozenAsDust` / `Promoted` / `NeedsEviction`）
- `tick_pipeline.retriage_synthetic_owner_for_symbol` 在 `on_tick` 熱路徑調用；熱路徑短路：非 synthetic label 為 O(1)；`NeedsEviction` 走 `ipc_close_symbol`
- 新增 `retriage_last_evict_ms` + `ORPHAN_CLOSE_DEDUP_MS = 2min` 去重
- **Agent 自主接管**：無需重啟或 operator 介入即可從啟動時阻擋升級的條件恢復（§原則 #11 Agent 最大自主權）
- +10 retriage 測試
- engine lib 1413 (default) 全綠（+62 vs 1351 baseline）

### P0-6 LiveDemo cost-gate profile（commit `e6aa467`，晚間續作）
**問題**：`edge_estimates.json = {}` → `cost_gate(JS-live)` fail-closed → 0 fills → 0 edge → 永遠 fail-closed 冷啟動死循環。LiveDemo 是假錢 demo-endpoint 流量，不應套 Production strict gate。

**修復**：`mode_state::effective_governance_profile(kind, env)` endpoint-aware 映射：
- Paper → Exploration · Demo → Validation
- Live + Mainnet → Production（真錢 strict）
- Live + LiveDemo/Testnet/Demo/None → **Validation**（moderate cost gate 允許 cold-start）

`on_tick.rs` 兩處 callsite 改走新函式（inline 自由函式避開 orchestrator `strategies_mut()` 可變迭代期間 immutable borrow E0502）；`GovernanceCore::new_with_profile()` 構造時 profile 不動，Live 管線 Auth/Lease 語義不變（Python Operator auth 仍必須）。

**Post-deploy 6min 驗證（PID 1827304）**：
- `cost_gate(JS-live): fail-closed` = 0（之前 85+/hr）
- `cost_gate(demo-cold-start): allow` = 30（Validation moderate 放行）
- Live_Demo 0 → 4 positions / 0 → 6 trades / +$0.59 realized PnL
- 測試：engine lib 1415 (+2 new) / core 380 / reconciler_e2e 19 / stress 35 全綠

## 測試基準線 / Test Baseline
- Rust engine lib: 1342 → 1351 → 1380 → **1413 → 1415 (default) / 1420 (ort)** passed / 0 failed
- Rust core: **380** / e2e 35 / reconciler_e2e 19
- 新增整合測試套件：`micro_profit_fix_integration` 7 passed
- Python: **2898 passed** / 5 skipped / 0 fail
- ml_training: 182 passed / 10 skipped

## 關鍵決策 / Decisions
1. **orphan = 重啟/故障遺留，非 scanner 輪替** — A4 邏輯刪除；scanner 輪替歸 SCANNER-GATE 責任
2. **fast_track 90% margin_utilization gate 為 intentional cash-mode fail-safe，不動** — 當前參數下永不觸發為設計本意
3. **MICRO-PROFIT-FIX-1 方案 A 勝過方案 B**：相對名義（current/entry）路徑無關，grid/strategy_close/IPC 削倉同樣計入；halve_count 只數自己的次數會漏
4. **`entry_notional` accumulate 語義（非首次凍結、非重設）**：反映累計入場總 notional，符合「halve 到 25% 殘餘」直觀；與 `entry_price` weighted-avg 天然對齊
5. **窄帶 `[0.3%, 0.55%]` 取代「≥100」**：threshold 100 在 breakeven 觸發的設計錯誤修正；hot-reload 運行時 agent 可收窄/放寬
6. **3 參數全走 ConfigStore/ArcSwap，TOML 僅 cold-start default**（CLAUDE.md §三 根原則）；validate 縮窄必配 legacy migration 防 fail-close
7. **LiveDemo ≠ Production strict**：endpoint-aware profile 映射破除「假錢 demo 流量套真錢 gate → 永遠無法累積 edge」死循環
8. **P1-8 FUP tick-level retriage 體現 §原則 #11**：Agent 自主接管啟動時被阻擋升級的條件，無需 operator 介入
9. **自適應出場/fast-track 範圍化為「加過濾層」非「改攻擊面」**：不擴大寫入口、不動 RiskConfig 權威、hot-reloadable
10. **P0-2 LG-1 21d demo 時鐘**：MICRO-PROFIT-FIX-1 為 code fix intentional restart，時鐘從 22:20 local 重新起算（CLAUDE.md §三 規則計為一次觀察期重置）

## 遺留項 / Remaining
1. **MICRO-PROFIT-FIX-1 24-48h 觀察期**：目標 `fast_track_reduce_half` fills 989/48h → < 200；`COST EDGE` fills 162/48h → < 50；avg |PnL| $0.068 → ≥ $0.15；pnl_pct 帶位置從 breakeven 移到 [0.3%, 0.55%]。早期 17min 樣本方向一致（11 新格式 COST EDGE，pnl 落窄帶下限 0.30%）
2. **E2 nit 收斂**：`migrate_legacy_entry_notional` wire 進 startup（低優先，整合測試已覆蓋正邏輯）
3. **A1 exit_persistence_max_ms 硬上限**：若觀察到 choppy 市場 exit 拖延造成小幅超額回撤，考慮加硬上限（當前上限 = `min_persistence_ms` = 180s default）
4. **A2 `max_cooldown_boost` 納入 EDGE-P2 參數搜尋空間**：當前 default 3.0 為保守先驗，待 paper/demo 真實數據決定最優
5. **B1 `drop_scoped` / `effective_cooldown_ms` 欄位 live/demo 觀察**：`tracing::warn!` 已加欄位，需驗證真實被觸發過 scoped 分支（非僅單測綠）
6. **P1-8 部署觀察一週**：dust frozen / retriage 分支在真實 bybit_sync/orphan label 上的覆蓋率
7. **P1-7 LEARNING-PIPELINE-DORMANT-1**：`edge_estimates.json = {}` 屬獨立問題（非 COST EDGE 觸發源）；不阻 live 但阻 Phase 5 edge 收斂
8. **P0-2 LG-1 21d demo 時鐘**：PID 1827304 於 22:20 CEST 起算

## Commits
- `7131250` SCANNER-GATE — kill orphan_handler death loop + P0-6 triage
- `68cfcb2` docs(qa): adaptive exit persistence + fast-track scoping proposal
- `baa75a2` adaptive exit persistence + fast-track symbol scoping
- `2170432` docs(worklog): micro-profit RCA + fix plan (PM-verified, pre-E1)
- `d9e2560` MICRO-PROFIT-FIX-1 — 窄帶 cost-edge + fast_track 名義底線
- `51183ca` P1-8 DUST-EVICTION-GAP-1 E1/E4 + FUP tick-level retriage
- `e6aa467` P0-6 方案 A — LiveDemo → Validation cost-gate profile
- `2098a34` docs(todo): archive 4 completed P0s (scanner-gate / phantom-2-fup / live-guard-1 / stability-1)
- `49d4dc0` docs(todo): +P1-8 DUST-EVICTION-GAP-1 · +G-11 gap index
- `648bda5` fix(gui): strategy column + Total Equity on demo/live tabs
- `da56e4b` fix(gui): propagate realized_pnl through fills display for demo/live/paper

**日終成績**：P0-10 ✅ · MICRO-PROFIT-FIX-1 ✅（RCA + 部署 + 核實全鏈）· P1-8 E1/E4 + FUP ✅ · P0-6 方案 A ✅ · 自適應出場 + fast-track scoping ✅ · engine lib 1342 → 1415/1420（+73 測試）/ 0 fail。
