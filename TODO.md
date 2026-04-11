# OpenClaw TODO — 工作計劃清單

最後更新：2026-04-11（晚間 audit + housekeeping。3E-ARCH S0-S13 + Fix Rounds A-G + W19 + W20 + Phase 6 已全部歸檔）
測試基準線：**Rust engine lib 931 + core 366 + e2e 18 · Python program_code 2792 passed (5 skipped · 0 fail) · ml_training 135 passed (6 skipped)**

> compact 後從此文件恢復工作狀態。第一個 `[ ]` 即為下一步起點。
> 歷史歸檔索引在文件末尾。詳細完成度視角見 README.md。

---

## 🏗️ 3E-ARCH — 三引擎並行架構 + trading_mode 清除 ✅ 完成（2026-04-11 歸檔）

**歸檔**：`docs/archive/2026-04-11--completed_todo_3e_arch.md` — 完整記錄 S0-S13 主實施 + Phase A-G Fix Rounds（10 BLOCKER + 7 MAJOR + MEGA-BLOCKER-0 全修，9/9 角色重審 PASS）。
**今日 worklog**：`docs/worklogs/2026-04-11--daily_summary.md`。
**計劃文件（保留參考）**：`docs/references/2026-04-11--three_engine_parallel_arch_plan.md`（v4，D1-D26）+ `docs/references/2026-04-11--3e_arch_session_execution_plan.md`（S0-S13）。
**審計報告**：`docs/audits/2026-04-11--3e_arch_e2_multi_role_review.md`（初審 633 行） + `docs/audits/2026-04-11--3e_arch_phase_g_reaudit.md`（重審 9/9 PASS）。

**殘留非阻塞**（2 MAJOR 文件大小監控，非阻塞，下次加 handler 前處理）：
- [ ] **M-1** `rust/openclaw_engine/src/ipc_server/handlers.rs` 1195 行
- [ ] **M-2** `rust/openclaw_engine/src/tick_pipeline/on_tick.rs` 1170 行（-2，監控）

<details>
<summary>原展開清單（已全部完成，保留折疊備查）</summary>

### 前置（S0，可立即做）
- [x] **3E-6** Sidebar 顯示修正 + D12 RwLock 審計 + D26 GovernanceCore 驗證（S0）✅

### Rust 基礎（S1-S2, Day 1）
- [x] **3E-1** `PipelineKind` + `GovernanceProfile` 枚舉 + D22 `PipelineCommand` rename（S1）✅
- [x] **3E-9** `StrategyFactory` + per-engine 策略參數 TOML（S2）✅ — create_all() 替代硬編碼

### Pipeline 構造（S3-S4, Day 2-3）
- [x] **3E-2a-α** IntentProcessor 治理分層 + `cost_gate_moderate` + GovernanceProfile param（S3）✅
- [x] **3E-2a-β** EventConsumerDeps 重構 + Pipeline kind-based 構造（S4）✅

### 三管線並行（S5-S7, Day 3-5 — 最高風險）
- [x] **3E-2b-α** main.rs spawn 骨架 + bounded fan-out + D12 parking_lot + D25 DB pool（S5）✅
- [x] **3E-2b-β** D21 per-engine private WS supervisor + D17 Live 獨立 runtime（S6）✅
- [x] **3E-2b-γ** D23 dual reconciler + D6 三級遞減收縮 + 有序 shutdown（S7）✅

### IPC + 清除（S8-S11, Day 5-6）
- [x] **3E-3** IPC Server `EngineCommandChannels` + per-engine 快照路由（S8）✅
- [x] **3E-4** `TradingMode` → `PipelineKind` 運行時清除（S9，config 保留過渡橋接）✅
- [x] **3E-5** Python 側 trading_mode 清除 + per-engine metrics 隔離（S10）✅
- [x] **3E-7+8** API Key 衝突偵測 409 + Watchdog multi-snapshot + Paper balance GUI（S11）✅

### 驗收（S12-S13, Day 7-8）
- [x] **3E-E2** Phase G 重審 **9/9 PASS** — 0 BLOCKER / 4 MAJOR（非阻塞）/ 10 MINOR。原 10B+7M 全確認修復。報告：`docs/audits/2026-04-11--3e_arch_phase_g_reaudit.md`
- [x] **3E-E4** E4 測試回歸 PASS — 929 lib + 366 core + 18 e2e = 1313 passed / 0 failed / 0 ignored

**排期**：W22（2026-05-05~12）—— 8 個工作日  
**Session 間恢復**：compact 後讀 TODO.md 找下一個 `[ ]` → 讀 plan 對應 § → `cargo test --lib | tail -3` 確認基線

---

**3E-E2 Fix Rounds A-G** ✅ 全部完成 — 已歸檔至 `docs/archive/2026-04-11--completed_todo_w19_w20_phase6.md`（10 BLOCKER + 7 MAJOR + MEGA-BLOCKER-0 全修）。

</details>

---

## 🔴 2026-04-11 晚間 Audit BLOCKERs（全部已修）

**起源**：用戶要求「仔細檢查現在的持倉和今天的交易，看看是否風控全都在有效接入」→ 9 角色 audit 發現 4 MAJOR + 2 BLOCKER。M-1~M-4 + B-1 + B-2 全部修復完畢。

- [x] **B-1 Demo/Live 快照 positions 空（startup 不導入既存倉 + WS PositionUpdate 未寫回）** ✅ FIXED 2026-04-12（commit f6e7afc, Phase 2）
  - **根因（最終）**：兩個獨立 wiring gap，必須一起修：
    1. **Startup seeding 缺失** — `build_exchange_pipeline()` 雖已調 `pos_mgr.get_positions()`，但只在 `auto_add_margin` 開啟時才呼叫，且結果只用於 `set_auto_add_margin`，從未寫進 paper_state。
    2. **WS PositionUpdate 不寫回** — 根本沒有 `ExchangeEvent::PositionUpdate` 變體，listener 的 `on_position_update` 只更新 `api_pnl` 共享狀態，事件從未轉發給 event consumer，因此即使新成交後 Bybit 推 position update，paper_state 也收不到。
  - **修復**：
    1. `paper_state.import_positions()` + `upsert_position_from_exchange()` 兩個新 API（含方向翻轉時保留/重置 `best_price` 邏輯，避免每次 WS 心跳重設 trailing stop）。
    2. `build_exchange_pipeline()` 一律抓持倉（無條件，結果同時餵 auto-add-margin 與 seed），透過 `ExchangePipelineBindings.seed_positions` → `EventConsumerDeps.seed_positions` → `run_event_consumer()` 在 `with_kind()` 後立即 seed。
    3. `ExchangeEvent::PositionUpdate(PositionUpdate)` 新增變體；`startup.rs` `on_position_update` 同時轉發給 `exchange_event_tx`。
    4. `event_consumer/mod.rs` 新增 PositionUpdate 處理 arm，按 `size==0` / `side=="None"` → remove，否則 upsert，並 force_write snapshot。
  - **驗證**：post-fix `pipeline_snapshot_demo.json` positions=12 + `pipeline_snapshot_live.json` positions=9 與 Bybit 帳戶一致；paper=0 不變。+2 paper_state 單元測試。935 engine lib tests pass（was 933）。

- [x] **B-2 total_fills 不遞增（exchange 模式）** ✅ FIXED 2026-04-11（commits 8e08c34 / b5e45f7 / 152d1f6）
  - **根因（最終）**：Bybit demo 端點**不支援** `execution.fast` topic — 只 mainnet 有。Demo 對 `execution.fast` 訂閱會回 `success:true` 但永遠不推資料 → `total_fills` 卡在 0 且無任何錯誤。歷史代碼還更早把 topic 寫成 `fast-execution`（typo），雙重 bug。
  - **修復**：(1) `BybitEnvironment::private_ws_topics()` 環境感知 — demo/testnet/live-demo → `execution`，mainnet → `execution.fast`；(2) parser 不再靜默吞掉 `op:subscribe` 回應，改為 info/error 記錄 success+ret_msg+conn_id；(3) 順手也從 demo topic 移除 `dcp`（demo 也不支援，每次重連會 ERROR）；(4) Live runtime worker_threads 2→4 解決 1808 條 lag warnings。
  - **驗證**：post-fix demo 6 min 收到 18 筆真實 WS fills（ETHUSDT/BTCUSDT/FARTCOINUSDT/FFUSDT/1000PEPEUSDT 等），真實 exec_id、價格、fee；後續 5 min 0 lag warning、0 subscribe rejection。

**互鎖解除**：B-1+B-2 都修好後，Demo/Live 兩條管線 fills 正確進來、positions 與 Bybit 一致、Reconciler 不再誤報、風控可基於真實 state 計算 daily_loss/position_size。Live 上線前 audit 兩大 BLOCKER 已全部清零。

---

### M-1~M-4 已修復（待 commit）

- [x] **M-1** `order_manager.validate_and_round` fail-closed 缺 spec + `dispatch.rs` Market 訂單 pre-flight 名義值檢查（消除 14 次 retCode=10001 round-trip / session）
- [x] **M-2** `grid_trading.on_rejection` per-symbol 30s 拒絕冷卻 + `on_tick.rs` 4 個 `recent_intents.push_back` 站點顯示 post-Guardian capped qty（GUI 不再顯示 1e9 sentinel）
- [x] **M-3** cost_gate 跨引擎驗證 — 日誌證據確認 paper exploration mode + demo cold-start 探索均按設計運作（無代碼變更）
- [x] **M-4** `risk_config_live.toml` 限額驗證 — stop_loss_max=15%, leverage_max=15, daily_loss_max=7%, position_size_max=15%, h0_shadow_mode=false 全部正確收緊

---

## 🗓️ 排期總覽（2026-04-10 基準）

| 週次 | 日期 | 主要焦點 |
|------|------|---------|
| W19 | 04-14~18 | **G-3** IPC 認證 · **G-5** Rate Limit · **OC-3** / **6-RC-6** 告警分級 |
| W20 | 04-21~25 | SEC-04/06/13 E3 審查 · **6-01~03** 漸進放權 |
| W21 | 04-28~05-02 | **6-04~13** Phase 6 完整驗收 · LG-1 倒計時 |
| W22 | 05-05~12 | **3E-ARCH** 三引擎並行 + trading_mode 清除（8d, 13 sessions）· LG-2/3 |
| W23 | 05-12~16 | **G-1 R-06** Agent 完整 · **G-7** Teacher 啟用 · **G-10** Calibration · LG-4/5 |
| W24+ | 05-19+ | Phase 5 補強 · Backlog |

**關鍵路徑**：`G-3 → OC-3 → 6-RC-6 → 6-01~13 → LG-1(21d到05-01) → 3E-ARCH(W22, 8d) → LG-2 → LG-4 → Live`
**最早 Live 日期**：W23 末（～2026-05-16）

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

## 📈 Phase 6 — 漸進放權 + Reconciler 自動收縮 ✅ 大部分完成

歸檔：同上（6-RC-1~10, 6-01~08）。剩餘：

- [ ] **6-09~13** E2 + E4 + QA 端到端 + E5 + PM 驗收（W21）

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

## 🔍 Gap 排期索引（2026-04-10 審計，10 項全錄）

| Gap | 描述 | 複雜度 | 排期週 | 依賴 | Live 阻塞 |
|-----|------|--------|--------|------|----------|
| **G-1** | AI Agent 5 stub（H1-H5 AI 治理層無效）| XL | W22(R-02) + W23(R-06) | G-3, G-7 | — |
| **G-2** | FundingArb.on_tick() 永遠 vec![] | M | W22 | OC-5 | — |
| **G-3** | IPC socket 無認證（SEC-08）| M | **W19** | — | ✅ 阻塞 |
| **G-4** | Cookie secure=False（SEC-21）| S | W22 | HTTPS 部署 | ⚠️ 前置 |
| **G-5** | API Rate Limiting 全局缺失 | M | **W19** | — | ✅ 阻塞 |
| **G-6** | ML edge 基於噪音數據（重訓路徑）| S | W19-W20 | PH5-VERIFY-1 7d | — |
| **G-7** | ClaudeTeacher disabled + 學習閉環斷路 | M | W23 | E3 audit · G-3 · 21d paper | — |
| **G-8** | cost_gate 可信度低 | S | W21 評估 | G-6 | — |
| **G-9** | HMAC dead import 確認 | S | W20 E3 審查 | SEC-04/06/13 | — |
| **G-10** | Calibration.py 骨架 | M | W23 | fills 累積 | — |

---

## 📚 已完成歸檔索引

- **W19 + W20 + Phase 6 + 3E-E2 Fix Rounds A-G**：`docs/archive/2026-04-11--completed_todo_w19_w20_phase6.md`（2026-04-11 晚間整理）
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
