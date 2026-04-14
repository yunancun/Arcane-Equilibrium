# 已完成歸檔：2026-04-14 Phantom-Heal + Engine Self-Healing + Edge Strategy Fixes
# Completed Archive: Phantom-Heal + Engine Self-Healing + Edge Strategy Fixes (2026-04-14)

> 來源：TODO.md「🔴 FA-PHANTOM-1」「ENGINE-HEAL」「🔧 EDGE 策略修復」「WP-F GUI」等章節
> 歸檔日期：2026-04-14（TODO 清理同日）
> 工程日誌：`docs/worklogs/2026-04-14--engine_self_healing.md`
> Known Issues：`docs/known_issues/2026-04-14--ws_stale_detector.md`

---

## 🛠️ ENGINE-HEAL — 引擎自癒 4 Fix ✅（commit `ba1ad21`）

2026-04-14 靜默死亡事故驅動（引擎死 18 min 無重啟無死前日誌 · WS 死前 14+ min 已斷但進程仍「存活」）。

- [x] **Fix 1** `main.rs` L55-108 panic hook — `std::panic::set_hook` 捕 thread id/location/payload/`Backtrace::force_capture()` + flush → `tracing::error!`，覆蓋所有 tokio worker & std thread
- [x] **Fix 2** watchdog 4 道保險（`engine_watchdog.py` + `stop_all.sh` + `restart_all.sh`）：
  - (1) `fcntl.flock` 單例
  - (2) `engine_maintenance.flag` operator 意圖守則
  - (3) SIGTERM-first + 5s graceful + SIGKILL fallback（原 `pkill -f` 會在 `paper_state.json` atomic rename 中途殺死留損毀 tmp → 虛假重啟循環）
  - (4) 退避 [60,120,300,600,3600]s + 連續失敗 ≥5 熔斷寫 `canary_events.jsonl` 告警
- [x] **Fix 3** crash-only — `run_pipeline_crash_only<F>()` 包 paper/demo spawn + Live thread catch_unwind 後補 `live_cancel.cancel()`，任一 panic → `EngineEvent::Crashed(kind)` + 全局 cancel → ordered shutdown → exit（**不 isolate**，避免三引擎共享 `RiskConfigStore`/`SymbolRegistry`/`EdgeEstimates` 污染帶病繼續）
- [x] **Fix 4** WS tick stale 自救（`main.rs` L1108-1155）— 30s 週期檢 `shared_last_tick_ms: Arc<AtomicU64>`，age > **120_000ms** 且 last!=0 → `cancel.cancel()`，業務層存活斷言防殭屍
- [x] **Bonus** `rotate_engine_log()` 保留 10 份 `/tmp/openclaw/engine_logs/engine-<epoch>.log`（原 `>` truncate 是事故放大器 — 沒它任何事故都沒死因）

**決策**：D1 全部 crash-only 含 Live / D2 WS stale 120s（60s 誤報太多，worst case ~3min zombie 可接受）/ D3 Phase 0 medium。
**驗證**：engine lib 1144 + core 366 + e2e 33 = **1543** 0 fail · watchdog 8/8 unit · shell `bash -n` clean。
**部署待辦**：運行中引擎仍 pre-fix binary — operator `bash helper_scripts/restart_all.sh --rebuild` 一次性替換（追蹤於新版 TODO 頂部）。

---

## 🔴 FA-PHANTOM-1 — fast_track margin_utilization 忽略 leverage ✅（commit `7eef87f` + `6c8b1a1`）

**Root Cause**：`on_tick.rs` L108-120 計算 `margin_utilization_pct = total_notional / balance × 100`（**無 leverage 除法**）。`fast_track.rs` L40 閾值 90% 同時 `total_exposure_max_pct` 設計上限 100% — 閾值低於設計上限，必然觸發。

**衝擊範圍**：**全策略**（ma_crossover / grid_trading / bb_breakout / bb_reversion / funding_arb）— FA-PHANTOM-1 只是最顯眼症狀。DB 驗證非 funding_arb 策略也有同樣 entry→risk_close:fast_track 對。窗口 17:00-20:30+02 共 769 fills (paper 468 + demo 301) 受污染。

**FIX**：`on_tick.rs` L108 改 leverage-aware：
```rust
let leverage = self.risk_config.load().limits.leverage_max.max(1.0);
let margin_used = total_notional / leverage;
let margin_utilization_pct = (margin_used / balance * 100.0).min(999.0);
```
Default leverage=20 → 5×$124 notional / 20 = $31 margin / $620 = 5% → 正常放行。

### 三方審查 Follow-Ups（E2+QC+FA）

- [x] **FUP-1** 補真正的 on_tick 整合測試 ✅ commit `6c8b1a1` — `stress_integration.rs` 新增兩個 on_tick 整合測試（20x leverage no-CloseAll + cash-mode 1x closes-all）。bite-check 驗證：移除 `/leverage` 使 20x 測試從 pass→fail（positions 5→0），cash-mode 仍正確。engine lib 1146 + core 372 + stress_integration 35。
- [x] **FUP-3** ~~引擎未運行~~ 誤警 — QC 用 `grep openclaw_engine`（underscore），實際 binary 是 `openclaw-engine`（dash）。PID 208182 從 19:01 就在跑 pre-fix binary；engine_results.jsonl 71GB 是獨立輪轉議題。
- [x] **FUP-4** 10 個未提交文件 ✅ 大部分已在 session 期間提交到 `51f6744` trailing-stop fix；session 內另行提交 `c7815da` (G-2 TOML revert) + `0ef5adf` (snapshot refresh) + `6c8b1a1` (FUP-1 tests)。`git status` clean。
- [x] **FUP-5** 污染清理 SQL ✅ 執行。scope 擴大為 paper+demo（demo 也有 58 fast_track closes in window → bug 對稱擊中兩引擎）。窗口 2026-04-14 17:00-20:30+02 全部 769 fills (paper 468 + demo 301) 標記 `details.contaminated=true` + `details.contamination_reason='fa_phantom_1'`。edge_estimates.json 本身 3 bytes 空，無須重算。
- [x] **FUP-2** Commit message 數字校正 ✅ memory `project_fa_phantom_bug.md` 已更新實際運行配置（leverage_max=100 / total_exposure_max_pct=200 / position_size_max_pct=50），post-fix 數學修正為 1.0% margin（100x）而非 5%（20x）；引用 balance=$615 paper 實測。
- [x] **FUP-6** Phase 5 歸因量化 ✅ memory `project_phase5_promotion_edge_crisis.md` 已加新 section「FA-PHANTOM-1 re-framing (2026-04-14)」含 QC 量化表（strategy_open=263 / fast_track_close=105 / strategy_close=94 / other_risk_close=63 → fast_track = 20% 總 fills/40% closes）+ 「don't assume fix 單獨 unpause Phase 5」/「do rerun per-strategy edge after 2w clean paper」兩條 applicability 規則。
- [x] **FUP-8** `intents.details` NULL 獨立 bug ✅ code ready（等 deploy）— 根因：`TradingMsg::Intent` variant 根本沒有 details 欄位 + `flush_intents` INSERT 沒列 details → 100% NULL 是 by-design 漏寫。修復：
  - `database/mod.rs`：TradingMsg::Intent 加 `details: Option<serde_json::Value>`
  - `database/trading_writer.rs`：INSERT 列表 + push_bind 加 details
  - `tick_pipeline/on_tick_helpers.rs persist_intent`：填 `{strategy, confidence, submitted_qty, is_long}`
  - `tick_pipeline/commands.rs`：同樣 pattern，details 加 `source: "command"` 區分
  - 測試基準線：engine lib 1145/1146（1 pre-existing env-race flake，isolation 下通過）+ stress_integration 35 全通過
  - **Phase 2**：OrderIntent 加 edge/funding_rate/basis/regime 欄位 — 留 G-1 Strategist 串線時一併做（W25+）

**留尾（轉入新版 TODO）**：FUP-7（90% 閾值可能 dead code — 等 operator 決策，brief 在 `docs/references/2026-04-14--fa_phantom_fup7_margin_threshold_decision.md`）· ENGINE-HEAL-DEPLOY（operator 執行 `restart_all.sh --rebuild` 一次性部署 Fix 1/3/4 + FA-PHANTOM-1 + FUP-8）。

---

## 🔧 EDGE 策略修復 P0+P1 ✅（2026-04-13）

診斷：隔離後 ~9h 乾淨數據確認所有 4 策略 gross edge ≈ 0，fee（5.5 bps/side = 11 bps RT）為主要虧損源；fast_track ReduceToHalf 佔 demo 75% fills。

- [x] **EDGE-P0-1** fast_track ReduceToHalf one-shot guard — `ft_reduced_symbols: HashSet<String>` in TickPipeline，per-symbol flag reset when risk < Defensive
- [x] **EDGE-P0-2** min_persistence_ms 120s → 180s — MA/BBR/Grid cooldown 提高（BBB 仍 60s，triple gate 已嚴）
- [x] **EDGE-P1-1** Grid 趨勢硬停 — `grid_trading.rs on_tick()`: ADX > 30 || hurst regime == "trending" → return vec![]
- [x] **EDGE-P1-2** Funding Rate 信號源 — PriceEvent + TickContext 加 `funding_rate: Option<f64>`；bb_reversion 極端費率方向對齊加成；+5 tests
- [x] **EDGE-P1-3** Confluence threshold 收緊 — 35/45/55 → 45/52/58
- [x] **EDGE-P1-4** bb_breakout 參數放寬 — `squeeze_bw` 0.02→0.03；`volume_threshold` 1.5→1.2；`squeeze_expiry_ms` 30→45 min
- [x] **EDGE-P2-1** risk_check 出場頻率審查 — close fill labeling bug 修復：`emit_close_fill()` 對所有平倉都寫 `risk_close:{reason}`，導致 327/435 看似風控強平；close_tag 直接寫入 DB `strategy_name`，三類標籤（`strategy_close:*` / `risk_close:*` / `stop_trigger:*`）明確區分；`realized_edge_stats.py` 更新 + `close_fill_analysis.sql` 診斷腳本

---

## 🛠️ QoL 修復（2026-04-14）

- [x] **QoL-1** Engine 重啟後 `paper_state` 計數器歸零 ✅ commits `22a0b36`+`ea25844`(merge) — `PaperState::restore_from_db()` + `event_consumer/paper_state_restore.rs` fail-soft glue，啟動時按 `engine_mode` 從 `trading.fills` 還原 `total_realized_pnl`/`total_fees`/`trade_count`。重啟驗證 PASS：demo=-3.49/29.11/254 · paper=-14.40/58.21/333 · live=0/0/0。
- [x] **QoL-3** PyO3 `.so` 部署不統一 ✅ commits `c510388`+`dc2eec3`(merge) — `helper_scripts/build_pyo3.sh` 統一雙寫（`~/.venv` + `control_api_v1/.venv`）；`restart_all.sh --rebuild` 旗標集成；build → pip install --force-reinstall → size 比對驗證。
- [x] **QoL-4** Paper PnL 異常大 ✅ commit `2a422fa` PNL-FIX-1（歸檔至 `2026-04-12--completed_todo_full_program_audit.md`）

---

## 🧟 ZOMBIE-API-SVC ✅（2026-04-14）

殭屍 `openclaw-trading-api.service` 1074+ restart 循環。`systemctl --user disable --now openclaw-trading-api.service` 執行完畢，service 現為 `inactive (dead) / disabled`。

三個並發根因：
1. port :8000 衝突（被 `restart_all.sh` 手啟的 uvicorn workers 28040/28078/28079 持有）
2. systemd cwd 錯致 `No module named 'program_code'`
3. `Restart=always` 政策

API 服務不受影響（手啟 workers 持續 serving）。`openclaw-gateway.service` 單元健康運行不受影響。需要時恢復 `systemctl --user enable --now openclaw-trading-api.service`（先解決 cwd + port 衝突）。

---

## 🛡️ ORPHAN-ADOPT-1 Phase 1 ✅（2026-04-14）

Reconciler 對 orphan 倉「偵測但不動作」的行為修復。

**交付**：`position_reconciler/orphan_handler.rs`（~350 行 + 11 unit tests）+ `run_position_reconciler` process_orphans 接線 + dedup（`ReconcilerState.pending_orphan_closes` 2 min TTL）+ V014 audit `orphan_handled`。

- **Stage A 硬安全**：A1 距強平 < 10% · A2 已 CB · A3 名義 > `max_order_notional_usdt` · A4 不在 active universe
- **Stage B 軟評估**：B1 五策略 shrunk_bps 全非正 且 unrealised_pnl > 0 → SoftLockProfit；default: SoftConservative
- **Stage C 降級**：Phase 1 所有 decision 都走 Close（`PipelineCommand::CloseSymbol` with `hint_is_long`/`hint_qty`）；dispatch 失敗 → 回退 drift 讓 Phase 6 升級階梯兜底

**測試基準**：58 reconciler tests pass（47 + 11 新）· 1136 lib + 366 core + 33 e2e = 1535 Rust pass。

**Phase 2**（真正 Adopt 路徑）轉入新版 TODO，等 G-1 R-02 Strategist Agent + StopManager adopt 接口 + 合成 StrategyId 規約。Phase 1 已預留 `OrphanDecision::Adopt` enum variant + `OrphanStage::SoftAdoptEligible` 分支，Phase 2 改 dispatch 即可。

---

## 🎨 WP-F GUI ✅ 部分完成

- [x] **WP-F/UX-07~10** 術語全域統一 ✅ 2026-04-14 commit `19a84da` — 規範字典 `Paper 模拟 / Demo 演示 / Live 实盘`；console.html BUILD_TS bump `20260414.ux07-unify-v1`；15 文件（11 tab HTML + console + 2 js + index.html legacy）；Session 語境消歧（AI 推理 / 交易暂停 / 授权租约 Lease）；tab-live.html L178-188 Pass-4 雙態資訊區塊 + tab-settings.html L773 Live-Demo ⚠ 同 Live 待遇標示。零後端改動。
- [x] **WP-F/margin-position-mode** `preferred_margin_mode` / `preferred_position_mode` GUI 入口 ✅ 2026-04-14 — tab-risk.html 新增 2 select inputs（isolated/cross, one_way/hedge）+ 2 display metrics (s-margin-mode/s-position-mode)；risk-tab.js 3 site 接線；console.html BUILD_TS `20260414.margin-position-mode-v1`。後端已有契約（RiskUpdatePayload + risk_view_client + Rust validate），零後端改動。
- [x] **WP-F/D-01** applyAIAdvice() → clipboard copy（2026-04-13）
- [x] **WP-F/UX-06** Submit loading 狀態：saveProviderKey + saveAIConfig（2026-04-13）
- [x] **WP-F/AH-05** btn-apply-ai 元素補齊 + 標籤改「Copy Advice」（2026-04-13）

**留尾（轉入新版 TODO backlog）**：WP-F/O-xx / AH-08~11 其他 GUI 小項；詳見 `docs/audits/2026-04-06--consolidated_remediation_report.md` §10.1。

---

## 🔍 PNL 調查留尾 ✅ 閉案（2026-04-12）

- [x] **PNL-5** bb_breakout 近乎 dead ✅ 調查完成 — 3 天僅 2 fills / 2 intents，零 round-trip。對比 grid_trading 3418 / ma_crossover 766 / bb_reversion 422。根因：三重入場門檻（squeeze→expansion 序列 + volume_ratio≥1.5 + Donchian 突破）+ 30min 窗口過嚴。**結論：非完全 dead 但參數過嚴致觸發率 ~0**。等 G-SR-1 策略研究一起重新評估參數（EDGE-P1-4 已部分放寬）。
- [x] **PNL-6** fast_track 已真實接線 ✅ 調查完成 — FIX-03/04 已將 `price_drop_pct`（PriceTracker.max_drop_pct()）和 `margin_utilization_pct`（positions notional/balance×100）真實接線。三條路徑（CloseAll/ReduceToHalf/PauseNewEntries）全有真實邏輯 + exchange dispatch + PNL-4 forensic logging。**TODO 描述已過時，不再是死碼**。注：margin_utilization_pct 本身是 FA-PHANTOM-1 的 bug，已由該修復解決。

---

## ⭐ OC-5 FundingArb on_tick() 完整實現 ✅（2026-04-13，解鎖 G-2）

FundingArb `on_tick()` 從 stub 升級為完整實現（~280 行）。

**數據管線**：`index_price: Option<f64>` 加入 PriceEvent → WS tickers `indexPrice` 提取 → `TickPipeline.index_prices` HashMap 緩存 → `TickContext.index_price`

**策略邏輯**：entry（funding_threshold + edge 計算 + basis 風險 `|perp/index-1|` + H0/cooldown/position guards）→ direction（positive→short, negative→long）→ confidence scaling（capped 0.6）→ RC-04 rejection rollback。Exit on rate flip / basis breach / max hold。

**驗證**：22 新測試。TOML: paper/demo `active=true`，live `active=false`。

**留尾（轉入新版 TODO）**：G-2 驗證本身 BLOCKED by FA-PHANTOM-1（驗證窗口全 PHANTOM fills），待 ENGINE-HEAL 部署後重啟驗證流程。

---

## 📊 驗收摘要

| 項目 | 狀態 | 測試基準線 |
|------|------|----------|
| ENGINE-HEAL 4 Fix | ✅ commit | 1543（engine lib 1144 + core 366 + e2e 33）· watchdog 8/8 |
| FA-PHANTOM-1 + FUP-1/3/4/5 | ✅ commit | 1146 lib + 372 core + stress 35 |
| EDGE-P0/P1/P2-1 | ✅ commit | 含於 G-SR-1 baseline |
| QoL-1/3/4 | ✅ commit | 重啟驗證 PASS |
| ORPHAN-ADOPT-1 Phase 1 | ✅ commit | 58 reconciler + 1535 total |
| WP-F GUI 部分 | ✅ commit | 零後端改動 |
| ZOMBIE-API-SVC | ✅ | systemd disabled + dead |
| OC-5 FundingArb | ✅ commit | 22 new tests |
| PNL-5/6 調查 | ✅ 閉案 | - |
