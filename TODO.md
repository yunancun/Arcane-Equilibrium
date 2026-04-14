# OpenClaw TODO — 工作計劃清單

最後更新：2026-04-14（ORPHAN-ADOPT-1 入列 W22+ · clean_restart.sh 交付）
測試基準線：**Rust engine lib 1091 + bin 5 + core 366 + e2e 33 + promotion 32 = 1527 · Python program_code 2852 passed (5 skipped · 0 fail) · ml_training 135 passed (6 skipped)**

> compact 後從此文件恢復工作狀態。第一個 `[ ]` 即為下一步起點。
> 歷史歸檔索引在文件末尾。詳細完成度視角見 README.md。

---

## 🏗️ 3E-ARCH — 三引擎並行架構 ✅ 完成（2026-04-11 歸檔）

歸檔：`docs/archive/2026-04-11--completed_todo_3e_arch.md`（S0-S13 + Fix Rounds A-G，9/9 角色重審 PASS）。

**殘留非阻塞**（文件大小監控）：
- [x] **M-1** `handlers.rs` 1195→1055 行（d16ed08 split + E5/EDGE 瘦身，< 1200 ✅）
- [x] **M-2** `on_tick.rs` 1170→1082 行（E5 TickContext + EDGE 瘦身，< 1200 ✅）

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
| W22 | 05-05~09 | **G-SR-1 S1-S4** Phase A 信號源收緊（~18h）· LG-2/3 | ✅（提前完成 04-13） |
| W23 | 05-12~16 | **G-SR-1 S5-S7** Phase B+C Agent 接線 + PM 驗收（~14h）· G-7 Teacher · G-10 Cal · LG-4/5 | ✅ G-SR-1（提前完成 04-13）· G-7/G-10/LG ⬜ |
| W24 | 05-19~23 | **EDGE-P0-1 止血** · EDGE-P1-1/P1-3 信號收緊 · EDGE-P1-2 Funding Rate | ⬜ |
| W25+ | 05-26+ | EDGE-P2 架構層 · R-06 全 5 agent · Phase 5 補強 · Backlog | ⬜ |

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

### 1. 🔴 策略 Edge 修復 — 最高優先（取代觀察期等待）

> **2026-04-13 診斷結論**：隔離後乾淨數據確認所有策略 gross edge ≈ 0，等再久也不會自然轉正。
> 必須先修策略再累積數據。JS 重跑暫緩（跑了只會確認全部 cell 為負）。
> 詳見下方「策略 Edge 修復」專節。

- [ ] **PH5-VERIFY-1** ~~7d observation~~ → **改為 EDGE-P0-1 修好後重新觀察**
- [ ] **JS 滾動重跑** — 暫緩，等 EDGE-P0-1 + P1 改善後再重跑
  - ↳ **G-6** / **G-8** 同步暫緩
- [ ] **LG-1** Paper Trading 穩定運行 21 天（Live Gate 前置）— 原 05-01 目標，視 EDGE 修復進度調整

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

#### Session 6 — B2+B3+B4 Agent 真實接線 + 驗收 ✅（2026-04-13）

B2→B3→B4 順序鏈完成。1083 lib + 33 e2e = 1116 tests pass, 0 fail · 2852 Python pass。

- [x] **B2** `ai_service.py` stub→real wiring — `_handle_strategist()` 接入 Ollama param tuning（build prompt from metrics + current_params + param_ranges → JSON param recommendations）；`_handle_guardian()` 接入 Ollama event classification（risk_level + assessment，informational only，NOT trade blocking）；OllamaClient lazy singleton + `asyncio.to_thread()` 非阻塞
- [x] **B3** Rust `evaluate_cycle()` 增強 — `fetch_current_params()` 移至 IPC 前，`current_params` + `param_ranges` 包含在 `strategist_evaluate` IPC 負載中，Python 側可基於上下文做更好推薦。S5 的 `validate_recommendation()` 不變
- [x] **B4** Guardian L1 信息層 — Ollama 事件分類（risk_level: low/medium/high/critical + assessment）；high/critical 事件通過 MessageBus 中繼給 Strategist（fail-open）；`create_ai_service_listener()` 注入 `MESSAGE_BUS` from strategy_wiring
- [x] **B-E2** E2 審查 PASS（10/10：bilingual / no hardcoded paths / fail-closed / file size 1080<1200 / cross-platform / security truncation / JSON-RPC compat / async threading / MessageBus lazy import / Rust compile clean）
- [x] **B-E4** E4 回歸 PASS — **1083 lib + 33 e2e = 1116** Rust · **2852** Python · 0 fail
- [x] **B-E5** E5 性能審查 PASS — 無熱路徑迴歸；Ollama 調用 async-threaded；5min/pair 不構成瓶頸；MessageBus relay 有界

#### Session 7 — Phase C stub + PM 驗收 ✅（2026-04-13）

C1-C2 接線 + PM 端到端驗收。1086 lib + 33 e2e = 1119 tests pass, 0 fail · 2852 Python pass。

- [x] **C1** `_handle_analyst()` 接入 AnalystAgent.analyze_trade() — 從 IPC trade_data 構建 TradeRecord → `asyncio.to_thread()` 調用 L1 分析 → 返回 strategy_metrics + strategy_rankings；agent 不可用時回退 stub
- [x] **C2** `_handle_scout()` 接入 ScoutAgent.get_recent_intel()/get_recent_alerts() — 序列化 IntelObject/EventAlert 為 JSON-safe dicts → symbol 過濾 → 返回 scout stats；agent 不可用時回退 stub
- [x] **C1-C2 injection** `create_ai_service_listener()` 注入 ANALYST_AGENT + SCOUT_AGENT from strategy_wiring（fail-open）
- [x] **G-SR-1-PM** PM 端到端驗收 **全部 PASS**：
  - ✅ Fragment signal 過濾：PersistenceTracker 正確接入 3 策略（check() 在 entry，clear() 在 close，Close 免檢）
  - ✅ Grid 降頻：compute_trend_adjusted_cooldown() ADX 60%+Hurst 40% 混合，1x-6x 動態倍率，3 TOML 參數
  - ✅ Confluence 評分：compute_score() 4 分量 65 分 + score_to_qty_pct() 平滑插值，3 策略 qty 調整
  - ✅ Strategist 鏈路：DB metrics → fetch_current_params → IPC(+params+ranges) → Ollama → validate_recommendation(range+delta+weight)
  - ✅ Guardian L1：Ollama 事件分類 → high/critical MessageBus 中繼 → informational only
  - ✅ C1-C2：Analyst/Scout agent 注入 + 真實調用 + stub fallback

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

- [x] **G-1 / R-02** Strategist + Guardian 真實接線（= G-SR-1 Phase B S5-S7 ✅）
  - 完成：Strategist Ollama param tuning + Guardian L1 classification + C1 Analyst + C2 Scout
- [x] **G-SR-1-RESEARCH** 策略 Edge 修復 P0+P1 全部完成 ✅ — P0-1/P0-2/P1-1~P1-4 全修，P2 待排
- [x] **G-1 / R-06-v2** Agent 價值交付 ✅ — Analyst→DB→Strategist 反饋閉環 + Guardian 拒絕統計 + Executor IPC 橋接（shadow） + Conductor real
  - 重新定義：原始 R-06 plumbing 為 0% value → R-06-v2 關閉學習回路
  - Step 2: Analyst PatternInsight → learning.pattern_insights → Strategist prompt
  - Step 3: Guardian rejection stats (trading.risk_verdicts JOIN intents) → Strategist prompt
  - Step 1: ExecutorAgent _paper_engine=None → Rust IPC SubmitOrder（shadow_mode=True 默認）
  - Step 4: Conductor stub→real（get_agent_health + degraded agent detection）
  - 不做：Rust→Python fire-and-forget / Conductor health polling / Rust→scout_scan
- [ ] **G-2** FundingArb 策略驗證 + 參數調優（OC-5 已解鎖，W22）
  - OC-5 ✅：FundingArb on_tick() 完整實現（entry/exit/cooldown/basis/edge），index_price TickContext 全鏈路
  - 現況：策略邏輯完成，待 paper 實盤驗證 edge + 參數調優
- [ ] **G-7** ClaudeTeacher 正式啟用（SEC-04/06/13 E3 審查 PASS 後 flip enabled AtomicBool，學習閉環接通，W23）
  - 現況：consumer_loop.rs `enabled = false`（啟動時 fail-closed）+ learning_store "currently has no consumer"
  - 前置：E3 審查 PASS + G-3 IPC 認證 + 21d paper 穩定
- [ ] **G-10** Calibration.py 整合（calibrate_isotonic → run_training_pipeline.py，加入 ECE < 0.05 門檻，W23）
  - 現況：ml_training/calibration.py 骨架，apply_calibration 缺整合入口
  - 前置：fills 累積 + 2-11 actual training

---

## 🔧 策略 Edge 修復（G-SR-1-RESEARCH，2026-04-13 診斷）

> **診斷背景**：隔離後 ~9h 乾淨數據確認 — demo gross edge +1.77 bps（被 fee 吞 → net -5.62），paper gross -1.35 bps（net -6.91）。
> 所有 4 策略 gross edge ≈ 0 或為負，fee（5.5 bps/side = 11 bps RT）是主要虧損源。
> fast_track ReduceToHalf 佔 demo 75% fills（2,685/3,567），每 tick 重複觸發幾何衰減。

### P0 — 止血（立即）

- [x] **EDGE-P0-1** fast_track ReduceToHalf one-shot guard ✅
  - `ft_reduced_symbols: HashSet<String>` in TickPipeline — per-symbol flag, reset when risk < Defensive
  - `on_tick.rs` filter positions by `!ft_reduced_symbols.contains()`, mark after reduce

### P1 — 策略信號改善

- [x] **EDGE-P0-2** min_persistence_ms 120s → 180s ✅
  - MA/BBR `min_persistence_ms` 120000→180000; Grid `cooldown_ms` 120000→180000
  - BBB stays at 60_000 (triple gate already strict)

- [x] **EDGE-P1-1** Grid 趨勢硬停 ✅
  - `grid_trading.rs on_tick()`: ADX > 30 || hurst regime == "trending" → return vec![]

- [x] **EDGE-P1-2** Funding Rate 信號源 ✅
  - PriceEvent + TickContext 加 `funding_rate: Option<f64>`；WS tickers 提取 + TickPipeline 緩存
  - bb_reversion: 極端正費率+做空→加成 / 極端負費率+做多→加成（方向對齊才觸發）
  - 可調參數：`funding_rate_threshold` (0.0005) / `funding_rate_boost` (0.08)
  - +5 tests (aligned/misaligned/below-threshold/validation)

- [x] **EDGE-P1-3** Confluence threshold 收緊 ✅
  - 35/45/55 → 45/52/58 across ConfluenceConfig + all strategy param defaults + mod.rs TOML defaults

- [x] **EDGE-P1-4** bb_breakout 參數放寬 ✅
  - `squeeze_bw` 0.02→0.03; `volume_threshold` 1.5→1.2; `squeeze_expiry_ms` 30min→45min

### P2 — 架構層

- [x] **EDGE-P2-1** risk_check 出場頻率審查 ✅ — close fill labeling bug 修復
  - **根因**：`emit_close_fill()` 對所有平倉（含策略出場）都寫 `risk_close:{reason}`，
    導致 327/435 看似都是風控強平，實際包含策略出場。Demo risk_config 閾值其實已寬鬆。
  - **修復**：close_tag 直接寫入 DB `strategy_name`，三類標籤明確區分：
    `strategy_close:*` / `risk_close:*` / `stop_trigger:*`
  - **影響**：`realized_edge_stats.py` 更新 + `close_fill_analysis.sql` 診斷腳本

- [ ] **EDGE-P2-2** OI + Liquidation 信號源 — 給 bb_breakout 加領先信號
  - Open Interest 急增 + 價格不動 → 即將爆發；Liquidation flow → 短期底部
  - 需要：接 Bybit WS `tickers` OI 字段 + `liquidation` stream
  - 工作量大，W24+ 排期

- [ ] **EDGE-P2-3** Maker order 支持 — fee 從 5.5 bps/side → ~1 bps/side
  - 策略發 post-only limit order 而非 market order
  - 需改動 IntentProcessor + order_manager + exchange execution layer
  - Round-trip fee 從 11 bps → 2 bps，根本性改變盈利方程式
  - 工作量大，W24+ 排期

### 執行順序與依賴

```
✅ EDGE-P0-1 ‖ P0-2 ‖ P1-1 ‖ P1-2 ‖ P1-3 ‖ P1-4 — P0+P1 全部完成（2026-04-13）
✅ EDGE-P2-1（close fill labeling 修復）— 2026-04-13
  → P2-2 / P2-3（W24+）
```

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

- [x] WP-F/D-01 applyAIAdvice() → clipboard copy（2026-04-13）
- [x] WP-F/UX-06 Submit loading 狀態：saveProviderKey + saveAIConfig（2026-04-13）
- [ ] WP-F/UX-07~10 術語統一（Paper/Live/Session 各 Tab 標籤）
- [x] WP-F/AH-05 btn-apply-ai 元素補齊 + 標籤改「Copy Advice」（2026-04-13）
- [ ] WP-F/O-xx / AH-08~11（詳見 §10.1）
- [ ] `preferred_margin_mode` / `preferred_position_mode` GUI 入口

### WP-E4 測試覆蓋（13 項）

- [x] T-P2-5 rest_poller（+9 tests）/ T-P2-6 quality_writer（+9 tests）（2026-04-13）
- [ ] T-P2-9 PyO3 bridge tests / T-P2-10 panic-path / T-P2-11 並發
- [ ] T-Q3/Q4/Q7/Q8 覆蓋品質
- [ ] T-I1~I4 tarpaulin / CI 門禁 / 文檔
- [ ] WP-E4/T-P1-1 殘餘 event_consumer 完整事件循環整合測試

### WP-E5 大文件

- [ ] tick_pipeline.rs 2117 行 — 留專屬 session
- [x] governance_hub.py 1052 行（已瘦身至 < 1200 ✅，原 1927 行）

### WP-I 文檔衛生

- [ ] R4-NAME-1 / R4-MEM-1 / R4-REF-ST-1

---

## 🛡️ Phase 6 擴展 — Reconciler Orphan 主動處理（W22+，非阻塞）

> 背景：當前 reconciler seed 完成後，對 orphan 倉「偵測但不動作」——只在 burst ≥5 drifts 連續 2 cycles → CircuitBreaker + CloseAll 才自動平倉。單一 orphan 會留在交易所自生自滅（無止損、funding 累積），直到 operator 手動干預。
> 設計參考：`helper_scripts/clean_restart_flatten.py`（PyO3 reduce_only 平倉模板）+ `position_reconciler/escalation.rs`（既有升級階梯保留作最後防線）。

- [ ] **ORPHAN-ADOPT-1** — 啟動 seed 完成後統一孤兒處理決策函數 `handle_orphan(pos) -> CloseOrAdopt`
  - **Stage A 硬安全（任一命中 → Close）**：距離強平 < 5×ATR · 全局 drawdown/CB 已 tripped · 名義值 > `max_order_notional_usdt` · symbol 不在 scanner active universe
  - **Stage B+C 軟評估（統一決策+執行）**：
    - 查 edge_estimates（demo 用 production 池，paper 用 `_paper.json`）
    - `shrunk_bps < 0` 且 unrealized PnL > 0 → 鎖利 Close
    - 策略在該 symbol 當下有同向信號 → Adopt（原子執行三件事：注入 `position_map` + 綁 hard/trailing stop + 寫 audit `ORPHAN_ADOPTED`，任一失敗降級 Close）
    - 其他曖昧情況 → 保守 Close（原則 #6「失敗默認收縮」）
  - **執行路徑**：reduce_only market（參考 `clean_restart_flatten.py` 的 place_order 模式）
  - **Audit**：統一 event `ORPHAN_HANDLED { action: Close|Adopt, reason: ... }`
  - **保留既有升級**：Cautious/Defensive/CB+CloseAll 作為 handle_orphan 失敗時的兜底防線
  - **測試**：startup seed race condition / Stage A 4 條分支 / Stage B edge lookup / Adopt 原子性（注入失敗降級 Close）/ 已接管倉位不觸發 re-entry
  - **依賴**：無硬依賴，但建議在 G-1 R-02（Strategist agent）接線後實施，讓「strategies 有同向信號」判斷更有意義

---

## 📦 殘留延後（前 phase，非阻塞）

- [ ] **2-11** actual training（需足夠 trading.fills 累積）
- [ ] **ort crate** activation（首個 ONNX 模型訓練後）
- [ ] **4-06** LinUCB live warm-start deployment（script 已交付，等首次 v1→v2 遷移）
- [ ] **OC-4** MCP PostgreSQL 自然語言查詢
- [x] **OC-5** FundingArb on_tick() 完整實現 + index_price TickContext ✅（2026-04-13，解鎖 G-2）

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
