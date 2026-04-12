# OpenClaw TODO — 工作計劃清單

最後更新：2026-04-12（全程序鏈審計 58 發現 · 8 P0 · PM APPROVED 修復計劃）
測試基準線：**Rust engine lib 961 + core 366 + e2e 29 + promotion 32 = 1388 · Python program_code 2852 passed (5 skipped · 0 fail) · ml_training 135 passed (6 skipped)**

> compact 後從此文件恢復工作狀態。第一個 `[ ]` 即為下一步起點。
> 歷史歸檔索引在文件末尾。詳細完成度視角見 README.md。

---

## 🏗️ 3E-ARCH — 三引擎並行架構 ✅ 完成（2026-04-11 歸檔）

歸檔：`docs/archive/2026-04-11--completed_todo_3e_arch.md`（S0-S13 + Fix Rounds A-G，9/9 角色重審 PASS）。

**殘留非阻塞**（文件大小監控）：
- [ ] **M-1** `rust/openclaw_engine/src/ipc_server/handlers.rs` 1195 行
- [ ] **M-2** `rust/openclaw_engine/src/tick_pipeline/on_tick.rs` 1170 行

---

## 🔴 2026-04-11 晚間 Audit BLOCKERs ✅ 全部完成（2026-04-12 歸檔）

歸檔：`docs/archive/2026-04-11--completed_todo_w19_w20_phase6.md`（B-1/B-2 BLOCKER + M-1~M-4 MAJOR 全修）。

---

## 🗓️ 排期總覽（2026-04-12 更新）

| 週次 | 日期 | 主要焦點 | 狀態 |
|------|------|---------|------|
| W19 | 04-14~18 | G-3 IPC 認證 · G-5 Rate Limit · OC-3 / 6-RC-6 告警 | ✅ |
| W20 | 04-21~25 | SEC E3 審查 · 6-01~03 漸進放權 | ✅ |
| W21 | 04-28~05-02 | 6-04~13 Phase 6 驗收 · 3E-ARCH · Audit BLOCKERs | ✅ |
| W22 | 05-05~09 | **G-1 R-02** AI Agent（Strategist/Guardian）· G-2/OC-5 FundingArb · LG-2/3 | ⬜ |
| W23 | 05-12~16 | **G-1 R-06** 全 5 agent · **G-7** Teacher · **G-10** Calibration · LG-4/5 | ⬜ |
| W24+ | 05-19+ | Phase 5 補強 · Backlog | ⬜ |

**關鍵路徑**：`~~G-3 → OC-3 → 6-RC-6 → 6-01~13 → 3E-ARCH~~ ✅ → LG-1(05-01) → LG-2 → LG-4 → Live`
**最早 Live 日期**：W23 末（～2026-05-16）

---

## 🔴 2026-04-12 全程序鏈審計（12 報告 · 58 發現 · 8 P0）

來源：`2026-04-12--full_audit_fix_plan_pm_confirmed.md`（PM APPROVED）
PA 原始報告：`docs/CCAgentWorkSpace/PA/2026-04-12--consolidated_fix_plan.md`

### P0 — Live 阻塞（W22 Mon-Tue 必須完成）

- [x] **FIX-10** ← E3: SEC-D01 [CRITICAL] — IPC HMAC 認證 Live 模式下應強制 ✅ main.rs panic guard
- [x] **FIX-03** ← FA: #2 [BLOCKER] · E3: SEC-A01 [LOW] · E5: D-01 [Medium] — FastTrack ReduceToHalf/PauseNewEntries 已處理 ✅ on_tick.rs 半倉+暫停開倉
- [x] **FIX-04** ← FA: #2 [BLOCKER] · E3: SEC-A01 [LOW] — fast_track 真實 price_drop_pct + margin_utilization_pct ✅ PriceHistoryTracker.max_drop_pct() + paper_state notional
- [x] **FIX-19** ← BB: BB-A4 [P1] [PARSE-ERROR] — execution.fast execFee 缺失時用 taker_fee_rate 估算 ✅ event_consumer/mod.rs
- [x] **FIX-13** ← E4: P0-#1 [P0-CRITICAL] — edge_estimates.rs +14 tests ✅ JSON 解析/空值/邊界/clamp
- [x] **FIX-14** ← E4: P0-#2 [P0-CRITICAL] — REST fail-closed +7 tests ✅ NoCredentials/Transport/retCode/timeout
- [x] **FIX-15** ← E4: P0-#3 [P0-CRITICAL] — 三管線並發寫入 +1 integration test ✅ 3 thread×50 writes 無損壞
- [x] **FIX-09** ← E3: SEC-E01 [HIGH] + SEC-B03 [MEDIUM] — ocEsc() 加單引號 `&#39;` 轉義 ✅ common.js

### P1 — 架構缺陷（W22 Wed 完成核心項）

- [ ] **FIX-05** ← QC: RG-1 [P1] — correlated_exposure_pct 永遠 0.0 — `router.rs:179,420`，組合級風險（原則 #16）實質失效
- [ ] **FIX-06** ← QC: RG-3 [P1] + H5 [P1] — GridTrading grid_levels TOML 配置存儲但不應用 — `grid_trading.rs`，dead param 違反規則
- [ ] **FIX-07** ← QC: RG-4 [P1] — OU theta clamp 0.001 在非 OU 序列產生巨大間距 — `grid_trading.rs` compute_ou_step
- [ ] **FIX-11** ← E3: SEC-D02 [HIGH] — Cookie secure=False — `legacy_routes.py:322`，1 行修改
- [ ] **FIX-16** ← E4: P1-#4 [P1-HIGH] — startup.rs 零測試（856 行）— 啟動邏輯關鍵
- [ ] **FIX-17** ← E4: P1-#9 [P1-HIGH] — Config hot-reload + tick 並發無測試 — ArcSwap 語義正確性未驗證
- [ ] **FIX-18** ← E4: §四.2 [P1-HIGH] — Price=0.0 tick 行為未測試 — 除零風險
- [ ] **FIX-20** ← BB: BB-A5 [P1] [RISK] — pre_check_order() 使用真正下單端點 — 意外下單風險，Live 模式需禁用
- [ ] **FIX-22** ← FA: #8 [MAJOR] + #6 [MAJOR] — 4 個 MlSwitches config 欄位未運行時讀取 — `learning_config.rs:86-106`，假功能
- [ ] **FIX-29** ← E5: R-02 [High] — on_tick() 1187 行需拆分為 7 子方法 — 超 1200 硬上限
- [ ] **FIX-30** ← E5: P-01 [High] — on_tick() symbol.clone() 重複 9 次 — 熱路徑堆分配
- [ ] **FIX-32** ← E5: P-04 [Medium] — risk_config().clone() 每 tick 深拷貝 — 不必要開銷
- [ ] **FIX-39** ← A3: §5.1 [CRITICAL] — Danger Zone 操作使用原生 confirm() — 需自定義 modal
- [ ] **FIX-40** ← A3: §5.1 [CRITICAL] — 策略刪除使用原生 confirm() — 不可逆操作需二次確認
- [ ] **FIX-47** ← TW: §4.1 [STALE] — CLAUDE_REFERENCE.md 過時 6 天
- [ ] **FIX-48** ← TW: §4.1 [STALE] — KNOWN_ISSUES.md 過時 7 天
- [ ] **FIX-52** ← R4: §四 P1-#5 [P1] — SCRIPT_INDEX.md 覆蓋率 ~11%
- [ ] **FIX-55** ← BB: BB-A1+A2+A3 [P1] [API-MISMATCH] — 3 個 API 路徑 MISMATCH（dead code）— `position_manager.rs`, `account_manager.rs`

P2/P3 共 25 項（文件拆分、策略參數化、ML backfill、文檔清理等）見完整報告。

---

## 🎯 當前焦點（W19 開始，按執行順序）

### 1. 🟢 觀察期 — 等數據（無開發動作，只需維運）

Phase 5 cost_gate 改造已全部上線。現在唯一阻擋正式 Live 的是**時間**：乾淨 paper 數據累積。

- [ ] **PH5-VERIFY-1** 7d paper observation — 看 fills / realized pnl 分布是否改善
  - **重新起算**：2026-04-10 DB fresh-start reset（71.3M 開發噪音清除），乾淨數據從今天開始
- [ ] **JS 滾動重跑排程**（2026-04-10 = Day 1）
  - 2026-04-11（Day 2）：`python3 -m program_code.ml_training.james_stein_estimator --days 2`
  - 2026-04-12（Day 3）：`--days 3`
  - 2026-04-17（Day 7）：`--days 7`
  - 之後每週拉長窗口（14d → 30d）直到估計穩定
  - 若某 cell 轉正 → 重啟引擎後 mode-aware gate 自動對該 pair 生效
  - `settings/edge_estimates.json` 更新後需重啟引擎才生效（無 hot-reload）
  - ↳ **G-6**（ML edge 重訓）：JS 重跑本身即為修復路徑，W19-W20 維運覆蓋
  - ↳ **G-8**（cost_gate 可信度）：G-6 完成後 W21 評估是否需人工干預
- [ ] **LG-1** Paper Trading 穩定運行 21 天（Live Gate 前置）— 最早 2026-05-01 完成

---

## 🛡️ W19 安全 + 告警 ✅ 全部完成

歸檔：`docs/archive/2026-04-11--completed_todo_w19_w20_phase6.md`（SEC-05/17, G-3/5, OC-3, 6-RC-6 等全部）。

## 🛡️ W20 深度安全審查 ✅ 大部分完成

歸檔：同上（SEC-04/06/13, G-9, WP-CC FS-1/BI-1/P9/SM-1）。剩餘：

- [ ] **SEC-21** Cookie `secure=True`（HTTPS 上線後，W22 依賴 HTTPS 部署）

---

## 📈 Phase 6 — 漸進放權 + Reconciler 自動收縮 ✅ 全部完成（2026-04-12 歸檔）

歸檔：`docs/archive/2026-04-11--completed_todo_w19_w20_phase6.md`（6-RC-1~10 + 6-01~08 + 6-09~13 PM 驗收 PASS）。

---

## 🤖 AI 治理層補強（W22-W23）

> 背景：`ai_service.py` 5 個 handler 全為 stub（返回保守固定值），H1-H5 AI 判決輸入為空值。系統目前完全靠 H0 + Rust 規則驅動。
> R-02 = Strategist + Guardian 接線；R-06 = Analyst + Conductor + Scout + FundingArb IPC。

- [ ] **G-1 / R-02** Strategist + Guardian 真實接線（ai_service.py → multi_agent_framework，優先這兩個關鍵角色，W22）
  - 前置：G-3 IPC 認證完成
- [ ] **G-SR-1** 真正策略研究（W22）— Strategist Agent 主導，在現有 4 策略參數空間外探索新策略邏輯
  - 現況：Rust 引擎固定 4 策略（MaCrossover/BbReversion/BbBreakout/GridTrading），參數由 JumpStart/LinUCB 調優但種類不增加；Python AUTO_DEPLOYER.on_scan_results() 已於 2026-04-10 廢棄（死代碼），GUI "Auto-Deployed" 區塊改為顯示 Rust ScannerRunner 的活躍 symbol universe
  - 目標：Strategist Agent 能提出新策略邏輯（訊號組合/出入場規則/止損方式），通過 Paper 驗證後由開發者實作為 Rust Strategy trait，進入正式 4+ 策略池
  - 實施方向：(a) Strategist 定期（每週）分析 fills/PnL/regime 數據，生成「策略改進提案」寫入 DB；(b) 提案包含：新策略描述、預期 Sharpe、測試週期、所需指標；(c) 人類 operator 審閱後批准進入 Rust 實作 backlog；(d) 長期：自動 backtesting 管線驗證提案（依賴 Phase 7+ backtest 基礎設施）
  - 前置：G-1/R-02 Strategist Agent 接線 + 足夠 fills 數據積累（LG-1 21d 後）
- [ ] **G-1 / R-06** Analyst + Conductor + Scout 接線（完整 5 agent，W23）
- [ ] **G-2** FundingArb.on_tick() 資金費率 IPC 接線（依賴 OC-5 REST 輪詢，W22）
  - 現況：funding_arb.rs on_tick() 永遠返回 vec![]（TODO R-06 註解）
- [ ] **G-7** ClaudeTeacher 正式啟用（SEC-04/06/13 E3 審查 PASS 後 flip enabled AtomicBool，學習閉環接通，W23）
  - 現況：consumer_loop.rs `enabled = false`（啟動時 fail-closed）+ learning_store "currently has no consumer"
  - 前置：E3 審查 PASS + G-3 IPC 認證 + 21d paper 穩定
- [ ] **G-10** Calibration.py 整合（calibrate_isotonic → run_training_pipeline.py，加入 ECE < 0.05 門檻，W23）
  - 現況：ml_training/calibration.py 骨架，apply_calibration 缺整合入口
  - 前置：fills 累積 + 2-11 actual training

---

## 🚦 Live Gate（W22-W23）

前置條件（全部必須）：
- G-3 IPC 認證 ✅（W19）
- G-5 Rate Limiting ✅（W19）
- Phase 6 完整驗收 ✅（W21）
- LG-1 Paper Trading 21 天 ✅（05-01）

- [ ] **LG-1** Paper Trading 穩定運行 21 天（同觀察期，05-01 完成）
- [ ] **LG-2** H0 Gate blocking 驗證（shadow → blocking，W22）
- [ ] **LG-3** provider pricing table 正式綁定（W22）
- [ ] **G-4 / SEC-21** Cookie `secure=True`（HTTPS 就緒後，W22）
- [ ] **LG-4** M 章 Supervised Live Gate（W23）
- [ ] **LG-5** N 章 Constrained Autonomous Live（W23）

**完成後**：換入 mainnet API key，系統即進入真實 Live（零代碼改動）。

---

## 📊 ML Edge Gap（觀察期後自動改善）

- [ ] **G-6** Edge estimates 重訓（JS 重跑使用重置後乾淨數據，W19-W20 滾動排程已覆蓋）
  - 現況：edge_estimates.json 8 個 cells 基於 71M 開發噪音數據
  - 修復路徑：JS 滾動重跑（14d/30d 窗口後估計穩定）
- [ ] **G-8** cost_gate 可信度評估（G-6 JS 重跑自然改善；W21 評估是否需要人工干預）
  - 現況：cost_gate 依賴不可靠的 edge_estimates，決策精度有限

---

## 📈 Phase 5 補強（W24+，非阻塞，觀察期後評估）

WIRE-0/WIRE-1 + DL-1/DL-2 + JS-1 + 5-01~03 已全部 ✅。下面是原 backlog 精度提升項：

- [ ] 5-04~07 DL-1 Symbol Embedding + DL-2 Regime LSTM Shadow
- [ ] 5-08~09 JS+Scorer 整合 + correlation_pairs
- [ ] 5-10~13 E2 + E4 + QC + E5

---

## 🧰 WP Backlog（W24+，低優先 · 維護性）

詳細子項見 `docs/audits/2026-04-06_consolidated_remediation_report.md` §10。

### WP-F GUI（P2 ~10 項）

- [ ] WP-F/D-01 applyAIAdvice() 只 toast 無實效
- [ ] WP-F/UX-06 Submit 無 loading 狀態
- [ ] WP-F/UX-07~10 術語統一（Paper/Live/Session 各 Tab 標籤）
- [ ] WP-F/AH-05 Apply 標籤誤導
- [ ] WP-F/O-xx / AH-08~11（詳見 §10.1）
- [ ] `preferred_margin_mode` / `preferred_position_mode` GUI 入口

### WP-E4 測試覆蓋（13 項）

- [ ] T-P2-5 rest_poller / T-P2-6 quality_writer / T-P2-9 PyO3 bridge tests / T-P2-10 panic-path / T-P2-11 並發
- [ ] T-Q3/Q4/Q7/Q8 覆蓋品質
- [ ] T-I1~I4 tarpaulin / CI 門禁 / 文檔
- [ ] WP-E4/T-P1-1 殘餘 event_consumer 完整事件循環整合測試

### WP-E5 大文件

- [ ] tick_pipeline.rs 2117 行 — 留專屬 session
- [ ] governance_hub.py 1927 行 — 拆分需獨立 sprint + E2+E4

### WP-I 文檔衛生

- [ ] R4-NAME-1 / R4-MEM-1 / R4-REF-ST-1

---

## 📦 殘留延後（前 phase，非阻塞）

- [ ] **2-11** actual training（需足夠 trading.fills 累積）
- [ ] **ort crate** activation（首個 ONNX 模型訓練後）
- [ ] **4-06** LinUCB live warm-start deployment（script 已交付，等首次 v1→v2 遷移）
- [ ] **OC-4** MCP PostgreSQL 自然語言查詢
- [ ] **OC-5** FundingArb REST 資金費率輪詢（W22，解鎖 G-2）

### Phase 4-Conditional（觸發後）

- [ ] 4-1 PairsTrading（需 3 月協整）/ 4-2 Beta Hedging / 4-3 Kalman / 4-5 Mac Studio 遷移 / 4-10 Jump detection

---

## 🔧 2026-04-12 GUI/Metrics 修復時發現（非阻塞）

來源：`docs/worklogs/2026-04-12--gui_metrics_db_fallback_and_display_fixes.md`

- [ ] **QoL-1** Engine 重啟後 `paper_state` 計數器歸零 — `total_realized_pnl` / `total_fees` / `trade_count` 為純記憶體變量，引擎啟動時應從 DB `trading.fills` 恢復累計值（現靠 Python metrics 端點 DB 降級繞過，但引擎內 snapshot 仍為 0）
- [ ] **QoL-2** Demo AI cost 無追蹤 — `tab-demo.html` 硬編碼 `'N/A'`，後端無 per-engine AI 調用成本歸因機制（需 H1-H5 AI 治理層接通後才有意義，依賴 G-1）
- [ ] **QoL-3** PyO3 `.so` 部署不統一 — `maturin develop` 默認裝到系統 venv（`~/.venv`），API server 用 `control_api_v1/.venv`，Rust struct 改動需手動 `maturin develop` 到正確 venv。應自動化或統一 venv
- [x] **QoL-4** ~~Paper PnL 異常大（497,199 USDT，初始 10,000）~~ — **不是風控配置問題**。根因為 `on_tick.rs` 5 條 close 路徑（L168 fast_track / L196 H0-stops / L304 paused-stops / L907 strategy_close / L1053 risk_close）誤用 `event.last_price`（觸發 tick 的單一 symbol 價）對所有 symbol 平倉，跨 symbol 平倉時 PnL 被放大 1000-10000 倍。Smoking gun: 8 個 fast_track fills 全部 price=2301.205 套用到 8 個不同 symbol（FFUSDT 真實 ~$0.50 被以 $2301 平倉 → -$757K；DOGEUSDT 真實 ~$0.20 被以 $2301 平倉 → +$750K）。修復：commit `2a422fa` PNL-FIX-1，新增 `close_position_at_symbol_market()` helper 統一從 `paper_state.latest_price(sym)` 取對應 symbol 價，並 fallback 至 entry_price（零 PnL 平倉）。+2 regression tests。DB 已按 Option B 清理（zero realized_pnl + 標記 invalid 後綴）

---

## 🔧 2026-04-12 PNL-FIX-1 後續（commit 2a422fa 觸發）

來源：DB 清理後的乾淨基線揭露多個失真假設。

- [x] **PNL-1** ✅ Phase 5 reframing 完成（同日，本 commit）— CLAUDE.md §三 Phase 5 段落重寫 + `project_phase5_promotion_edge_crisis.md` memory 重寫 + MEMORY.md 索引更新。Post-cleanup 真相寫入：所有活躍策略 gross edge **負數**（bb_reversion -0.46 / ma_crossover -2.64 / grid_trading -0.67 bps），Phase 5 cost_gate 工作暫停等策略重做
- [x] **PNL-2** ✅ Fee underreporting 修復（同日，本 commit）— 根因確認：`emit_close_fill` 寫 `fee: 0.0`，註解謊稱「accrued separately」但 `paper_state.close_position()` 完全不收費。所有 5 條 close 路徑（fast_track / H0-stops / paused / strategy_close / risk_close）共 653 筆 fill 全部 fee=$0（vs opens 742 筆共 $648 真實費用 → 真實 round-trip 應為 ~$2483，**漏報 4×**）。修復：新增 `paper_state.charge_fee()` helper + `emit_close_fill` 計算 `qty * price * fee_rate` 並 (a) 扣餘額 (b) 寫 DB。+2 regression tests（charge_fee garbage rejection + close fee charge end-to-end）
- [x] **PNL-3** ✅ Per-strategy edge breakdown 完成（同日，本 commit）— FIFO open-close pairing on 1395 paper fills（trading.fills.realized_pnl 已被 PNL-FIX-1 cleanup 修復）：

  | 策略 | round trips | gross PnL | rt fee real | net | gross bps | net bps |
  |---|---|---|---|---|---|---|
  | bb_reversion | 62 | -$9.71 | $115 | -$125 | -0.46 | -5.96 |
  | ma_crossover | 148 | -$119.88 | $250 | -$370 | -2.64 | -8.14 |
  | grid_trading | 446 | -$248.80 | $2032 | -$2280 | -0.67 | -6.17 |
  | bb_breakout | 0 | — | — | — | — | — |
  | **總計** | 656 | **-$378** | **$2397** | **-$2775** | — | — |

  **結論**：4 策略無任何 positive-edge 起點。bb_breakout 在乾淨基線從未平倉（疑：from never opened or held all positions until cleanup），需單獨驗證。**bb_breakout 需另開 TODO 確認是否完全 dead**

- [x] **PNL-4** ✅ fast_track 觸發根因（同日，本 commit）— 代碼追蹤已盡可能：`evaluate_fast_track(level, 0.0, 0.0)` 中 `price_drop_pct` 與 `margin_utilization_pct` 為硬編 `0.0`（comments 寫 "computed externally" 但**從未真的 externally computed**），閃崩+保證金分支為**死碼**。唯一可觸發 CloseAll 的是 `risk_level ≥ CircuitBreaker`。**04-11 18:51 logs 已隨 22:39 引擎重啟丟失**，無法 log 追蹤誰把 risk level 升到 CB。**已加觀測**：`on_tick.rs` fast_track CloseAll 分支現會 `tracing::warn!` 記錄 risk_level / ts / position count / 觸發 tick 的 symbol+price，下次觸發必留痕跡。**留尾**：(a) 調查是否要 wire price_drop / margin_util 真實計算，或乾脆刪除死碼；(b) 確認 04-11 那次是 Reconciler 升級、operator manual SetTier、還是某個未知路徑（無 log 不可考）

### 留尾追蹤項

- [ ] **PNL-5** bb_breakout 是否完全 dead — PNL-3 表中 round_trips=0；可能 (a) `on_tick()` 從未產生 Open intent、(b) 產生但全被 cost_gate / Guardian 攔下、(c) 開了倉但持續持有未平倉。檢查最近 7d signals/intents 表
- [ ] **PNL-6** fast_track 死碼決議 — `fast_track::evaluate_fast_track` 的 `price_drop_pct` / `margin_utilization_pct` 兩條分支：要嘛真實接線（從 paper_state 計算 margin util、從 black_swan_detector 計算閃崩 pct），要嘛刪除死碼。當前唯一觸發路徑（CB 升級）已有 reconciler 自動處理，flash/margin 邏輯重複度低

---

## 🔍 Gap 排期索引（2026-04-10 審計，10 項全錄）

| Gap | 描述 | 複雜度 | 排期週 | 依賴 | Live 阻塞 |
|-----|------|--------|--------|------|----------|
| **G-1** | AI Agent 5 stub（H1-H5 AI 治理層無效）| XL | W22(R-02) + W23(R-06) | G-3, G-7 | — |
| **G-2** | FundingArb.on_tick() 永遠 vec![] | M | W22 | OC-5 | — |
| **G-3** | ~~IPC socket 無認證（SEC-08）~~ | M | W19 ✅ | — | ~~✅ 阻塞~~ |
| **G-4** | Cookie secure=False（SEC-21）| S | W22 | HTTPS 部署 | ⚠️ 前置 |
| **G-5** | ~~API Rate Limiting 全局缺失~~ | M | W19 ✅ | — | ~~✅ 阻塞~~ |
| **G-6** | ML edge 基於噪音數據（重訓路徑）| S | W19-W20 | PH5-VERIFY-1 7d | — |
| **G-7** | ClaudeTeacher disabled + 學習閉環斷路 | M | W23 | E3 audit · G-3 · 21d paper | — |
| **G-8** | cost_gate 可信度低 | S | W21 評估 | G-6 | — |
| **G-9** | ~~HMAC dead import 確認~~ | S | W20 ✅ | SEC-04/06/13 | — |
| **G-10** | Calibration.py 骨架 | M | W23 | fills 累積 | — |

---

## 📚 已完成歸檔索引

- **W19 + W20 + Phase 6 + 3E-E2 Fix Rounds A-G + 晚間 Audit BLOCKERs**：`docs/archive/2026-04-11--completed_todo_w19_w20_phase6.md`（2026-04-12 追加 Phase 6 PM 驗收 + Audit B-1/B-2/M-1~4）
- **3E-ARCH 三引擎並行 + 3E-E2 Fix Rounds A-G（完整版）**：`docs/archive/2026-04-11--completed_todo_3e_arch.md`（2026-04-11 歸檔，S0-S13 + 10 BLOCKER + 7 MAJOR）
- **Live GUI P0~P6 + DEAD-PY-1/2 + 1C-4 收尾**：`docs/archive/2026-04-10--completed_todo_live_gui_dead_py.md`
- **Phase 5 P0 promotion + WIRE chain**：commits `5d7d673` → `0e848fa` → `638afa3` → `563d54a` → `5e760be`
- **ARCH-RC1 Session 1A → 1C-4 WRAP**：`docs/worklogs/2026-04-08--arch_rc1_1c_history_archive.md` + `docs/archive/2026-04-08--main_docs_1c3_1c4_narrative.md`
- **Phase 4 (4-00 ~ 4-21 + 4.1)**：`docs/audits/2026-04-07_phase4_final_signoff_audit.md`
- **Session 11 之前**：`docs/worklogs/phase5_arch_rc1/2026-04-06--completed_todo_archive_l3_phases.md`
- **Phase 0/1/2/3 + Rust migration**：`docs/worklogs/phase5_arch_rc1/2026-04-04--completed_todo_archive_phase0123_rust.md`
- **已知問題清單**：`docs/KNOWN_ISSUES.md`
- **Bybit API 字典手冊**：`docs/references/2026-04-04--bybit_api_reference.md`

---

## ⚙️ 工作流程速查

```
E1/E1a 並行（最多 5 路）→ E2 審查（強制）→ E4 回歸（強制）→ PM 確認 → commit
角色定義詳見 CLAUDE.md §八
```

**Bybit API 開發必查**：先讀 `docs/references/2026-04-04--bybit_api_reference.md`。

**風控參數修改強制原則**：所有風控/止損/cost-gate/regime 參數必須透過 IPC `patch_risk_config` 單一通道更新。
