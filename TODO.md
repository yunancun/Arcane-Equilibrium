# OpenClaw TODO — 工作計劃清單

最後更新：2026-04-13（G-SR-1 v2.5 FINAL · 5 輪 52 項修正 · 7 Session 實施計劃）
測試基準線：**Rust engine lib 1083 + bin 5 + core 366 + e2e 29 + promotion 32 = 1515 · Python program_code 2852 passed (5 skipped · 0 fail) · ml_training 135 passed (6 skipped)**

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
| W22 | 05-05~09 | **G-SR-1 S1-S4** Phase A 信號源收緊（~18h）· LG-2/3 | ⬜ |
| W23 | 05-12~16 | **G-SR-1 S5-S7** Phase B Agent 接線（~14h）· G-7 Teacher · G-10 Cal · LG-4/5 | ⬜ |
| W24+ | 05-19+ | G-SR-1-RESEARCH 策略研究 · R-06 全 5 agent · Phase 5 補強 · Backlog | ⬜ |

**關鍵路徑**：`~~G-3 → OC-3 → 6-RC-6 → 6-01~13 → 3E-ARCH~~ ✅ → LG-1(05-01) → LG-2 → LG-4 → Live`
**最早 Live 日期**：W23 末（～2026-05-16）

---

## 🔴 2026-04-12 全程序鏈審計 ✅ P0/P1/P2 全部完成（2026-04-12 歸檔）

歸檔：`docs/archive/2026-04-12--completed_todo_full_program_audit.md`（P0 8/8 + P1 19/19 + P2 Rust 7/7 + P2/P3 Session 3.3 全修 + PNL-1~4 + QoL-4）。
PM 確認報告：`docs/audits/2026-04-12--full_audit_fix_plan_pm_confirmed.md`

### 餘下 P2（大工程，W22+ 排期）

- FIX-01 — H1-H5 AI Agent 接入（= G-1 R-02/R-06）
- FIX-02 — Decision Lease Rust 接入（與 FIX-01 一起）
- FIX-12 — CSP nonce 遷移（長期）

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

### G-SR-1 Signal Tightening + R-02 Agent Wiring（計劃 FINAL，5 輪 52 項修正）

方案文件：`docs/references/2026-04-12--g_sr1_signal_tightening_plan_v2.5.md`
Phase A ~23h（信號源收緊）+ Phase B ~18h（Agent 接線）= ~41h 總實施量

#### Session 1 — A0 基礎模組提取 ✅（2026-04-13）

- [x] **A0-a** 從 `grid_trading.rs` 提取 `grid_helpers.rs`（~130 行純函數）
- [x] **A0-b** 建立 `confluence.rs` 共享模組（~549 行：PersistenceTracker + compute_score + score_to_qty_pct + ConfluenceConfig）
- [x] **A0-E2** S1 E2 審查 PASS

#### Session 2 — A0-c + A1 + A2 + A3 ✅（2026-04-13）

S2 完成全部計劃項 + A2 提前實施。1024 lib + 33 integration = 1057 tests pass, 0 fail。

- [x] **A0-c** ConfluenceConfig 初始化路徑 + `#[serde(default)]` 全覆蓋
  - 3 TOML Params struct（MaCrossover/BbReversion/BbBreakout）加 confluence 字段 + build_confluence_config()
  - StrategyFactory 接線 + R4-7 update_params rebuild
- [x] **A1** 時間制信號持續性過濾器（MA/BBR=120000ms, BBB=60000ms）
  - PersistenceTracker.check() 接入 3 策略 on_tick() entry path，close 免檢，clear() 已接線
- [x] **A3** Grid 趨勢冷卻（1x-6x 動態倍率）
  - compute_trend_adjusted_cooldown()：ADX 60% + Hurst 40%，3 TOML 參數 + factory 接線
- [x] **A2**（提前實施）加權匯合評分接入 3 策略
  - compute_score() 4 分量 65 分制 + score_to_qty_pct() 平滑插值 + breakout 10% 底線
  - 冷啟動 adx&&rsi None→全倉退化 + min_notional guard
- [x] **S2-E2** 全項事實審計 PASS（A0-c/A1/A2/A3 逐條核對計劃規格）

#### Session 3 — A-PARAMS + 收尾（~3h）

A2 已在 S2 完成，S3 僅需 A-PARAMS。

- [x] **A-PARAMS** 擴展 4 個 Params struct param_ranges()（MA+BBR+BBB +10 confluence + Grid +3 cooldown）+ threshold ordering validation + grid cooldown bounds validation
- [x] **S3-E2** E2 自審 PASS（compile clean, all ranges match struct fields）

#### Session 4 — A-TEST 測試 + E4 回歸（~4h）

**可並行**：confluence 單元測試 / persistence 測試 / integration 測試 三路。

- [x] **A-TEST-1** confluence.rs 單元測試 — 27 existing + 12 S4 edge-case = 39 total
- [x] **A-TEST-2** PersistenceTracker 單元測試 — 7 existing + 1 clear test = 8 total
- [x] **A-TEST-3** 策略 param validation + grid cooldown 測試 — MA 7 + BBR 6 + BBB 6 + Grid 9 = 28 new
- [x] **A-E4** E4 回歸 PASS — **1065 lib + 33 e2e = 1098** (baseline 1024+33=1057, +41 new)
- [x] **A-E5** E5 性能審查 PASS — `.to_string()` 熱路徑分配為 pre-existing 模式（非 Phase A 引入）；PersistenceTracker 無界增長建議 future 加 LRU cap。無阻塞項。

#### Session 5 — B0+B1+B1.5 Rust 側 Agent 基礎設施 ✅（2026-04-13）

B0 ‖ B1 並行開發，B1.5 依賴 B1。1083 lib + 33 e2e = 1116 tests pass, 0 fail。

- [x] **B0** `strategist_scheduler.rs` — tokio 後台任務 + DB metrics 查詢（R4-6, R5-3, R5-4）+ 指數退避（R4-2: 5m→30m→60m→4h）+ validate_recommendation（range + delta ±30% + weight_sum=65 + weight exempt）+ 10 tests
- [x] **B1** `ai_service_client.rs` — AiServiceClient（100ms connect timeout + per-method TTL）+ newline JSON-RPC + fail-closed + 8 tests（含 mock server roundtrip）
- [x] **B1.5** AIServiceListener 啟動接線（R4-3）— `app.on_event("startup")` + stale socket cleanup + shutdown hook + app.state 引用保持
- [x] **S5-E2** E2 審查 PASS（10/10 checklist：bilingual / no hardcoded paths / fail-closed / file size / param validation / thread safety / cross-platform / JSON-RPC protocol / security / backoff）

#### Session 6 — B2+B3+B4 Agent 真實接線 + 驗收（~6h）

**順序為主**：B2→B3→B4 有依賴鏈。

- [ ] **B2** ai_service.py stub→real wiring（strategist_evaluate + guardian_check）
- [ ] **B3** Strategist 驗證層（range + delta ±30% + weight sum=65，weight params 免 delta cap）
- [ ] **B4** Guardian L1 信息層（事件分類 via Ollama L1，MessageBus relay）
- [ ] **B-E2** E2 審查
- [ ] **B-E4** E4 回歸（全基線）
- [ ] **B-E5** E5 性能審查（Phase B 完成，強制）

#### Session 7 — Phase C stub + PM 驗收（~2h）

- [ ] **C1-C2** Analyst attribution + Scout intelligence stub 接線（Phase C 為 W23 R-06 依賴）
- [ ] **G-SR-1-PM** PM 端到端驗收：Fragment signal 過濾率 / Grid 降頻效果 / Strategist 參數調整確認

**Sub-agent 並行策略總結**：
| Session | 並行路數 | 方式 |
|---------|---------|------|
| S1 | 2 路 | A0-a ‖ A0-b ✅ |
| S2 | 3 路 | A0-c ‖ A1 ‖ A3 + A2 提前完成 ✅ |
| S3 | 1 路 | A-PARAMS（A2 已在 S2 完成） |
| S4 | 3 路 | 三組測試（不同 test 文件） |
| S5 | 2 路 | B0 ‖ B1（不同新文件） |
| S6 | 1 路 | B2→B3→B4 順序鏈 |
| S7 | 1 路 | 收尾 |

---

- [ ] **G-1 / R-02** Strategist + Guardian 真實接線（= G-SR-1 Phase B，上方 S5-S6）
  - 前置：G-3 IPC 認證 ✅ + G-SR-1 Phase A 完成
- [ ] **G-SR-1-RESEARCH** 策略研究（Phase B 後）— Strategist Agent 分析 fills/PnL/regime，生成策略改進提案
  - 前置：G-SR-1 全部完成 + 足夠 fills 數據（LG-1 21d 後）
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

詳細子項見 `docs/audits/2026-04-06--consolidated_remediation_report.md` §10。

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
- [x] **QoL-4** ~~Paper PnL 異常大~~ ✅ commit `2a422fa` PNL-FIX-1（歸檔至 `docs/archive/2026-04-12--completed_todo_full_program_audit.md`）

---

## 🔧 2026-04-12 PNL-FIX-1 後續（commit 2a422fa 觸發）

來源：DB 清理後的乾淨基線揭露多個失真假設。

- [x] **PNL-1~4** ✅ 全部完成（歸檔至 `docs/archive/2026-04-12--completed_todo_full_program_audit.md`）

### 留尾追蹤項

- [x] **PNL-5** bb_breakout 近乎 dead ✅ 調查完成（2026-04-12）— 3 天僅 2 fills / 2 intents（ARIAUSDT Sell + RAVEUSDT Buy），零 round-trip。對比 grid_trading 3418 / ma_crossover 766 / bb_reversion 422。根因：三重入場門檻（squeeze→expansion 序列 + volume_ratio≥1.5 + Donchian 突破）+ 30min 窗口過嚴。**結論：非完全 dead 但參數過嚴致觸發率 ~0，等 G-SR-1 策略研究一起重新評估參數**
- [x] **PNL-6** fast_track 已真實接線 ✅ 調查完成（2026-04-12）— FIX-03/04 已將 `price_drop_pct`（PriceTracker.max_drop_pct()）和 `margin_utilization_pct`（positions notional/balance×100）真實接線。三條路徑（CloseAll/ReduceToHalf/PauseNewEntries）全有真實邏輯 + exchange dispatch + PNL-4 forensic logging。**TODO 描述已過時，不再是死碼**

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
- **Phase 4 (4-00 ~ 4-21 + 4.1)**：`docs/audits/2026-04-07--phase4_final_signoff_audit.md`
- **Session 11 之前**：`docs/archive/2026-04-06--completed_todo_archive_l3_phases.md`
- **Phase 0/1/2/3 + Rust migration**：`docs/archive/2026-04-04--completed_todo_archive_phase0123_rust.md`
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
