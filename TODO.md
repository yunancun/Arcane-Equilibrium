# OpenClaw TODO — 工作計劃清單

最後更新：2026-04-11（3E-ARCH v4 計劃 + 13-session 執行計劃錄入）
測試基準線：**Rust engine lib 879 + e2e 18 · Python program_code 2792 passed (5 skipped · 0 fail) · ml_training 135 passed (6 skipped)**

> compact 後從此文件恢復工作狀態。第一個 `[ ]` 即為下一步起點。
> 歷史歸檔索引在文件末尾。詳細完成度視角見 README.md。

---

## 🏗️ 3E-ARCH — 三引擎並行架構 + trading_mode 清除（P0 · W22 首要）

**背景**：當前系統是「單一 TickPipeline + 模式切換」（Signal Diamond Phase 3 中間態）。用戶目標是 Paper / Demo / Live 三管線**同時並行**，各自接入對應 API，各自寫 DB，由 `system_mode` 統一治理。`trading_mode` 全局配置是單引擎遺物，三引擎世界中無意義，需徹底移除。

**計劃文件**：`docs/references/2026-04-11--three_engine_parallel_arch_plan.md`（v4，26 設計決策 D1-D26）  
**Session 執行計劃**：`docs/references/2026-04-11--3e_arch_session_execution_plan.md`（13 sessions，S0-S13）

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
- [ ] **3E-5** Python 側 trading_mode 清除 + per-engine metrics 隔離（S10）
- [ ] **3E-7+8** API Key 衝突偵測 409 + Watchdog multi-snapshot + Paper balance GUI（S11，可與 S10 並行）

### 驗收（S12-S13, Day 7-8）
- [ ] **3E-E2** E2 代碼審查 — D1-D26 全量 checklist（S12）
- [ ] **3E-E4** E4 測試回歸 + ~40 新增 tests（S13，基線：879 lib + 18 e2e + 2792 Python）

**排期**：W22（2026-05-05~12）—— 8 個工作日  
**Session 間恢復**：compact 後讀 TODO.md 找下一個 `[ ]` → 讀 plan 對應 § → `cargo test --lib | tail -3` 確認基線

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

## 🛡️ W19 — 安全 + 告警（Live 前必做）

### W19-P0：IPC 認證 + Rate Limiting（無依賴，立即可做）

- [x] **SEC-05** GUI `innerHTML` XSS ✅ — ocEsc() 全量包裹
- [x] **SEC-17** `OPENCLAW_ALLOW_MAINNET` 移除 ✅ — API key 填入 = 唯一上線條件
- [x] **G-3 / SEC-08** IPC socket HMAC-SHA256 認證 ✅ (commit W19)
  - verify_ipc_token()（常數時間 mac.verify_slice）+ handle_connection auth 區塊 + Python _authenticate() + fail-closed + 向後兼容（無 env var 跳過）
- [x] **G-5** API Rate Limiting 全局覆蓋 ✅ — 驗證 main_legacy.py:304-307 default_limits=[120/min]+SlowAPIMiddleware 已覆蓋全部 214 路由（login 5/min 保留嚴格限制）

### W19-P0：告警通道（阻塞 6-RC-6）

- [x] **OC-3** 多通道分級告警 ✅ (commit W19) — reconciler_alert_monitor() 每 30s 輪詢 get_risk_runtime_status；CIRCUIT_BREAKER/MANUAL_REVIEW→P0；CAUTIOUS/REDUCED/DEFENSIVE→P1；asyncio.to_thread 包裹 sync alert；main.py startup create_task
- [x] **6-RC-6** 多通道告警 + governor tier 升降告警 ✅ (commit W19) — OC-3 實施覆蓋 6-RC-6 需求；CloseAll/CB 觸發時 P0 alert 已接線
- [x] Phase 6 自動降級動作層完成（6-RC-1~5,7,8,9,10）✅

### W20：深度安全審查

- [ ] **SEC-21** Cookie `secure=True`（HTTPS 上線後，W22 依賴 HTTPS 部署）
- [x] **SEC-04 / 06 / 13** 深度 E3 審查 ✅ — SEC-04 safe (parameterized queries), SEC-06 fixed (HttpOnly cookie), SEC-13 fixed (saturating cast)
- [x] **G-9** HMAC dead import 確認 ✅ — NOT dead, `hmac.compare_digest()` used at L171 for auth token verification
- [x] **WP-CC/FS-1 / BI-1 / P9 / SM-1** ✅ — FS-1 tests extracted (1083→742 lines), BI-1 MODULE_NOTE 12 files, P9 dual-rail stop wired, SM-1 compliant

---

## 📈 Phase 6 — 漸進放權 + Reconciler 自動收縮（W20-W21）

### 6-RC（Reconciler 自動 governor 動作層）

- [x] **6-RC-1** 動作通道隔離 ReconcilerEscalate/DeEscalate ✅
- [x] **6-RC-2** V014 event_type 隔離 ✅
- [x] **6-RC-3** 動作策略（MajorDrift→Cautious / burst→CB+CloseAll）✅
- [x] **6-RC-4** 自身冷卻（per-symbol 30min + 全局 5min + hybrid 恢復）✅
- [x] **6-RC-5** Per-symbol minQty dust floor ✅
- [x] **6-RC-6** 多通道告警 + governor tier 升降告警 ✅ (W19 OC-3 覆蓋)
- [x] **6-RC-7** 整合測試（7 場景 reconciler_e2e.rs）✅
- [x] **6-RC-8** Live blocker 解除 ✅
- [x] **6-RC-9** Baseline staleness 政策 ✅
- [x] **6-RC-10** REST 失敗升級（≥10 次→Cautious）✅

### 6-Phase（漸進放權 + 驗收，W20-W21）

- [x] **6-01~03** 漸進放權管線 + 畢業邏輯 + Live 審批 ✅ — promotion_pipeline.py (PromotionGate + 5 stages + graduation gates + operator approval) + 3 API endpoints + 27 tests
- [x] **6-04** 集成測試（合成場景模擬器 7 新場景：MinorDrift 不重設/SideFlip/Ghost/冷卻/全局冷卻/多級恢復/REST 漸進）✅
- [x] **6-05** 壓測（Rust 4 場景：100 cycle 快速翻轉 / 50 symbols 爆發 / handler 快速升降 / 性能 <100ms；Python 5 場景：並發 register/promote/metrics）✅
- [x] **6-06** sync_commit Live 驗證 PASS — global `synchronous_commit=on`（V006:90）已保護 orders/fills，per-session 分層優化歸 WP Backlog
- [x] **6-07~08** EvolutionEngine 保留（用於 DL/AI agent 學習），與 PromotionPipeline 分工文檔化 ✅
- [ ] **6-09~13** E2 + E4 + QA 端到端 + E5 + PM（W21）

---

## 🤖 AI 治理層補強（W22-W23）

> 背景：`ai_service.py` 5 個 handler 全為 stub（返回保守固定值），H1-H5 AI 判決輸入為空值。系統目前完全靠 H0 + Rust 規則驅動。
> R-02 = Strategist + Guardian 接線；R-06 = Analyst + Conductor + Scout + FundingArb IPC。

- [ ] **G-1 / R-02** Strategist + Guardian 真實接線（ai_service.py → multi_agent_framework，優先這兩個關鍵角色，W22）
  - 前置：G-3 IPC 認證完成
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
- [x] WP-F/AH-06 Risk-tab dirty-tracking ✅
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
