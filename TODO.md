# OpenClaw TODO — 工作計劃清單

最後更新：2026-04-06（Session 13 · R3 backlog 清完 — FA-GAP/SEC-11/idle writer 3/I-22/per-symbol fees）
測試基準線：**471 engine + 413 core + 35 ml_training + 11 control_api smoke** · 0 failures

> compact 後從此文件恢復工作狀態。第一個 `[ ]` 即為下一步起點。

**參考索引**
- 已完成歸檔（截至 Session 11）：`docs/worklogs/2026-04-06--completed_todo_archive_l3_phases.md`
- 之前的歸檔：`docs/worklogs/2026-04-04--completed_todo_archive_phase0123_rust.md`
- L3 整合審計：`docs/audits/2026-04-06_consolidated_remediation_report.md`
- 已知問題清單：`docs/KNOWN_ISSUES.md`
- Bybit API 字典手冊：`docs/references/2026-04-04--bybit_api_reference.md`（開發前必查）

---

## 當前狀態

R3 backlog（排除 WP / SEC live-prep / Phase 4 範圍）**已全部清空**。
Session 12 PNL-1~7 + DB-RUN-1~7 + Session 13 R3 收尾共 22 個 commits 全部 push。
下一步候選：
1. **Phase 4 啟動**（Claude Teacher + LinUCB + News + DL-3 · W13-15）
2. **SEC live-prep**（SEC-05 XSS 大改 / SEC-17 2FA / SEC-21 HTTPS 配套 — 上 live 前必做）
3. **WP backlog**（223 子項，分散小修，可以用作填空）

---

## P0/P1 — 引擎運行數據驅動

### 虧損根因（Session 10 · 真實虧損 ~$3.17 / 0.32%）

> 171 fills · 9 stops · ~15 次重啟 · BTC 僅 1.2% 波動區間

- [x] **PNL-1**（P0）qty=0 幽靈倉禁止開倉 — `ed01bf5`
- [x] **PNL-2**（P0）H0Gate observability — `f7a0b31`（根因為 stale binary，加 boot log + invariant）
- [x] **PNL-3**（P1）引擎重啟冷卻期 — `5890311`（默認 60s · env + IPC 可調）
- [x] **PNL-4**（P1）regime 動態化（Hurst → ADX → ranging）— `1c5caa3`
- [x] **PNL-5**（P1）Cost Gate 小帳戶收緊（k=3.0/2.0/1.5 三檔）— `821bd9c`
- [x] **PNL-6**（P2）止損 RR 失衡 — `c4425ce`（trailing 鎖定盈利下限 ≥ dyn_stop × 0.5）
- [x] **PNL-7**（P2）dynamic_stop base/cap → RiskManagerConfig + IPC — `5a8653e` `4175bf2`
- [x] **Session 12 cleanup**：cost-gate min_confidence/k 三檔 + ADX trending 閾值 + boot cooldown → IPC `07e2f7c`

> ⚠️ **後續 Agent 設置風控強制原則**：任何新增/修改的風控/止損/cost-gate/regime 參數
> 必須對齊 `openclaw_core::risk::config::RiskManagerConfig` 的字段，並透過 IPC
> `update_risk_config`（`event_consumer/handlers.rs::handle_paper_command`
> + `intent_processor::patch_dynamic_stop_params` / `patch_cost_gate_params`
> + `tick_pipeline::set_boot_cooldown_ms`）的單一通道更新。**禁止** 在 hot path
> 寫死數值或新增 const，**禁止** 繞過 `patch_*` 校驗直接寫 `risk_config` 字段。
> Agent 可調的 13 個參數見 `RiskManagerConfig` 註解。

### 數據庫運行治理（Session 10 · 12hr 觀察 · DB 19 GB · signals 15.2M）

- [x] **DB-RUN-1**（P0）signals 寫入節流 — `b945eff`（per-(symbol,strategy) state-change + 60s heartbeat）
- [x] **DB-RUN-2**（P0）decision_context piggyback DB-RUN-1 — `509a70b`
- [x] **DB-RUN-3**（P1）realized_pnl Fill 發送 — `358e2aa`（5 個 close 站點全部接通 emit_close_fill）
- [x] **DB-RUN-4**（P1）feature_writer history — `ec91d31`（no bug, by design：訓練歷史走 decision_context.indicators_snapshot JSONB）
- [x] **DB-RUN-5**（P2）writer 審計 + BlackSwanDetector 接線 — `2161ec1`（2 個死代碼：BlackSwan 已接 in-memory + log，ExperimentLedger 留 Phase 4）
- [x] **DB-RUN-6**（P2）epoch 0 防護 + 5 條歷史清理 — `78291ff`（context_writer guard + 已執行 DELETE）
- [x] **DB-RUN-7**（P3）signals hypertable chunk 7d→1d / compress 14d→2d + ANALYZE — `6608ab7`

### 策略 confidence 動態化（Session 13 完成）

- [x] **CONF-A** ma_crossover regime-aware（ADX 超額 + Hurst regime fit，entry/exit helper）
- [x] **CONF-B** grid_trading 動態（ranging+窄 BB→0.85 / trending→0.30，`compute_grid_confidence`）
- [x] **CONF-C** bb_reversion exit + bb_breakout %B vs bandwidth 分檔（殺 0.5 placeholder）
- [ ] **CONF-D** 暴露 conf scaling 給 agent via IPC `update_strategy_params` → 移至 Phase 4

---

## R3 Backlog（L3 審計剩餘 OPEN）

### 安全 / 架構性

- [ ] **SEC-05** GUI `innerHTML` XSS（架構性，16 文件 133 處）
- [ ] **SEC-09** `/startup-status` 認證（by-design，保持開放）
- [x] **SEC-11** Cost-Gate ATR=0 fail-closed — 兩處 intent_processor + 1 test（cold start 由 PNL-3 boot cooldown 保護）
- [ ] **SEC-17** `OPENCLAW_ALLOW_MAINNET` 2FA（2FA 架構）
- [ ] **SEC-21** Cookie `secure=True`（HTTPS 上線後）
- [x] **FA GAP-2** cost_ratio 接線（tick_pipeline → check_position_on_tick，公式 200×fee/pnl%）
- [x] **FA GAP-4** Kelly ATR% 接線（intent_processor 從 on_tick atr 計算 atr/price，REFERENCE_ATR_PCT 常量化）
- [x] **FA GAP-8** IPC `evaluate_strategy` / `get_risk_check` stub 刪除（dead code，無 Python caller）
- [x] **FA GAP-9** bb_reversion `use_limit` 強制 false + 從 param_ranges 移除（paper 無撮合，避免 silent PnL 失真）
- [ ] **FA GAP-10** Provider pricing table（Phase 4，等 LLM cost tracking）

### Idle Writers 殘留

- [x] **#3 liquidations** — dead infra 已刪除（writer + Msg variant + topic functions + extended_subscription_list）。`market.liquidations` 表保留 reserved-for-future。重新啟用前需 (1) 確認 Bybit V5 working topic 名稱 (2) 找到下游 consumer。
- [x] **#5 drift_events writer** — 調查結果：已正常運作（drift_detector.rs:478 自洽週期檢測，main.rs:875 spawn）
- [x] **#6 quality_events writer** — 調查結果：已正常運作（quality_writer.rs:69，event_consumer:600 atomic 接 tick）

### 測試覆蓋

- [ ] **WP-E4/T-P1-1 殘餘** event_consumer 完整事件循環整合測試（fixture harness，獨立 sprint）
- [x] **I-22 殘留** event_consumer mod.rs 785 → 628（dispatch.rs + setup.rs 提取）

### WP 真實 Open 清單（2026-04-06 審計後 · 103 項）

> ⚠️ 原始 backlog 223 項已在 Session 13 後實際核查。以下為真實仍存在的問題，
> **不要重新審計全部 223 項**，直接從下方清單執行。
> 詳細子項見 `docs/audits/2026-04-06_consolidated_remediation_report.md` §10。

#### WP-F — GUI（✅ P0/P1 核心已修，原 47，剩餘 P2 ~10 項低優先）
P0（4項，全已修 — `71e4770`）：
- [x] WP-F/D-05 Apply-AI 按鈕 disabled + tooltip（開發中）
- [x] WP-F/UX-01 刪除策略加 confirm guard（deleteStrategy 接 confirm()）
- [x] WP-F/UX-02 Danger Zone 快速導航 anchor 頂部（AH-01 合併修）
- [x] WP-F/UX-03 三個 Save 按鈕拆分為 saveStopSettings / savePositionSettings / saveCooldownSettings

P1（11/18 項已修 — `71e4770`）：
- [x] WP-F/D-02/03/04 Feed/Demo/Scanner 三按鈕 disabled + (只读/RO) tooltip
- [x] WP-F/D-07 index.html Legacy Bearer Token 面板 `display:none`，Logout 移出可見
- [x] WP-F/D-09 策略 Delete 按鈕加 confirm guard（已合併 UX-01）
- [x] WP-F/UX-04/05 Save/Submit 加 loading/disabled 狀態（_btnSaving helper）
- [x] WP-F/AH-01 Danger Zone 頂部快速導航 anchor link
- [x] WP-F/AH-04 Feed/Demo/Scanner disabled 移除 toggle 誤導外觀
- [x] WP-F/AH-07 Delete 與 Stop/Pause 之間加分隔線 + 虛線邊框
- [ ] WP-F/D-01 applyAIAdvice() 只有 toast，無實際效果（Phase 4 Teacher 完成後再修）
- [ ] WP-F/UX-06 Submit（param save）無 loading 狀態
- [ ] WP-F/UX-07/08/09/10 術語混亂（Demo/Paper/Session 多義）
- [ ] WP-F/AH-05 Apply 標籤誤導
- [ ] WP-F/AH-06 ⚠️ Risk-tab 每 15s 強制覆蓋用戶輸入（需重寫 loadAll 防抖）

P2（~10 項）：詳見報告 §10.1（O-xx / AH-08~11）

#### WP-G — 硬編碼（✅ 0 項，全部 43/43 完成 — `4187da6`）

#### WP-E4 — 測試覆蓋（13 項仍缺失，原 34）
- [ ] WP-E4/T-P2-5 rest_poller.rs 零測試
- [ ] WP-E4/T-P2-6 quality_writer.rs 零測試
- [ ] WP-E4/T-P2-9 PyO3 bridge 測試目錄完全缺失
- [ ] WP-E4/T-P2-10 Rust `#[should_panic]` panic-path 測試
- [ ] WP-E4/T-P2-11 Arc/Mutex 並發安全測試
- [ ] WP-E4/T-Q3/Q4/Q7/Q8 覆蓋品質（error-path / 並發 / smoke / PyO3）
- [ ] WP-E4/T-I1~I4 測試基礎設施（tarpaulin / CI 門禁 / 文檔）

#### WP-ARCH-RC1 — 雙風控系統統一（P1，live 前必修）
**現狀**：Python `RiskManager`（`risk_routes.py`）和 Rust engine 各自維護一份風控 config，
IPC 推送是 fire-and-forget，失敗不報錯，兩者隨時可能不同步。
Rust 是唯一實際執行引擎，Python RM 只是 GUI 的儲存層（技術債）。

**目標方案**：Rust 成為唯一 config authority
- [ ] RC1-1 Rust `update_risk_config` IPC 擴展：接受完整 GlobalConfig，更新後回寫 `operator_risk_config.json`（Rust 側，原子寫入）
- [ ] RC1-2 GUI save 路由改為 async，直接 await IPC → Rust；Rust 確認後再回 200
- [ ] RC1-3 GET `/risk/config` 改為從 Rust snapshot 讀（不再讀 Python RM file）
- [ ] RC1-4 Python `RiskManager` 降級為啟動時單次讀取 + 只讀快取，GUI 不再寫入 Python RM
- [ ] RC1-5 E2 + E4 + E3 審計（風控路徑修改強制安全審計）

> 背景：2026-04-06 發現代理未授權修改 operator_risk_config.json 後，GUI 值跳回問題暴露
> 此雙系統問題。修乾淨前維持現狀（Python RM 為輸入框真相源，`f3106d8`）。

#### WP-B+CC — 安全/合規（12 項仍存在，原 20）
- [ ] WP-B/SEC-05 GUI innerHTML XSS（架構性，136 處，live 前必修）
- [ ] WP-B/SEC-08 IPC socket 無認證（P1）
- [ ] WP-B/SEC-17 OPENCLAW_ALLOW_MAINNET 2FA（架構決策待定）
- [ ] WP-B/SEC-21 Cookie `secure=True`（HTTPS 上線後）
- [ ] WP-B/SEC-04/06/13 需深度 E3 審查（4 項）
- [ ] WP-CC/FS-1 / BI-1 / P9 / SM-1（4 項 CC 仍存在）

#### WP-E5 — 代碼品質（3 項，原 20，**80% 已完成**；大文件拆分延後）
- [ ] tick_pipeline.rs 2116 行（超限 1200）— 核心熱路徑，拆分需獨立 sprint + E2+E4
- [ ] governance_hub.py 1927 行（超限）— 同上，延後
- [ ] WP-E5/D1~D4 dead code（funding_arb/grid 保留 reserved，governance DEPRECATED by-design）

#### WP-BB — Bybit API（✅ 0 項，全部完成 — `44b0eee`）
- W-2：bybit_public_ws_listener.py + market_data_dispatcher.py 已刪除（RC-12，Rust WS 替代）
- S-1：bybit_rest_client.rs 新增 wait_if_rate_limited()，GET/POST 前主動退讓

#### WP-FA — 功能規格（0 項，原 5，**100% 已規劃**）
- ~~FA GAP-10 Provider pricing table~~ → 併入 Phase 4 子任務 **4-17**

#### WP-I — 文檔衛生（✅ P1 核心已完成 — `338b4f9`，原 42）
- [x] SCRIPT_INDEX.md 補建（6 腳本完整索引）
- [x] docs/audit 與 docs/audits 衝突 → 統一為 docs/audits/
- [x] 8 個 .DS_Store 清除
- [x] worklog 碎片合併為 2026-04-05--daily_summary.md
- [x] docs/README.md 索引更新（references/ + architecture/ + audits/）
- [x] CLAUDE_REFERENCE.md last-update 更新
- [x] governance_dev/ DEPRECATED.md 建立
殘餘低優先（R4-NAME-1 / R4-MEM-1 / R4-REF-ST-1 等 minor 命名 3 項）

#### WP-MIT — DB/ML（✅ 0 項，全部完成）

---

## Phase 4 — Claude Teacher + LinUCB + News + DL-3（W13-15）

> 22 子任務拆解見：`docs/references/2026-04-06--phase4_execution_plan_v2.md`
> Q1/Q2/Q3/Q4 operator 已拍板 · Q3=hierarchical warm-start (sufficient-statistics 父→子攤分 + γ=0.5 + shadow compare + 自動 regret 回滾)
> 原 CONF-D 已併入 4-15（IPC `update_strategy_params` 擴充承接 LinUCB confidence override）

**Group 0 — Dashboard 骨架**
- [ ] **4-00** Phase 4 Dashboard tab + 共用 `_dashboard_card.html` + `get_phase4_status` IPC stub (E1a · 1d)

**Group 1 — Claude Teacher**
- [ ] **4-01** Teacher directive Rust 接口 + ExperimentLedger 寫入 (E1 · 3d)
- [ ] **4-02** Directive 解析 + GovernanceHub 風控過濾（最高風險，E3 強制介入）(E1 · 2d)
- [ ] **4-03** directive_executions 效果追蹤 + Teacher Card (E1+E1a · 2d)

**Group 2 — LinUCB**
- [ ] **4-04** LinUCB Rust inference + arm space v1_15 + versioned state + feature_schema_hash fail-closed (E1 · 3d)
- [ ] **4-05** LinUCB Python trainer + 收斂監控 (E1 · 2d)
- [ ] **4-06** Model Performance rolling + LinUCB Card + arm dropdown + warm-start migration script + shadow compare + 自動 regret 回滾 (E1+E1a · 3d)

**Group 3 — News**
- [ ] **4-07** News provider abstract + CryptoPanic free + CoinTelegraph RSS + Google News RSS + mock (E1 · 3d)
- [ ] **4-08** Headline dedup (SHA1[:16] + 24h) + severity (keyword × source) (E1 · 2d)
- [ ] **4-09** Triple-route 消費（Guardian halt ≥0.8 / Regime feature / Learning context）(E1 · 2d)
- [ ] **4-10** News Card + provider quota 健康監控 (E1a · 1d)

**Group 4 — DL-3 Foundation Models**
- [ ] **4-11** TimesFM/Chronos async wrapper + foundation_model_features 表 (E1 · 3d)
- [ ] **4-12** DL-3 A/B 框架 vs Phase 3 Scorer baseline (E1 · 2d)
- [ ] **4-13** DL-3 降級邏輯 + Go/No-Go 報告腳本（AI-E 簽核）(E1+AI-E · 1d)
- [ ] **4-14** DL-3 Card + 決策展示 (E1a · 1d)

**Group 5 — Cross-cutting**
- [ ] **4-15** AI Budget tracker (Rust) + V010 (ai_budget_config + ai_usage_log + linucb_state versioning alter + linucb_state_archive + linucb_migrations) + IPC `update_ai_budget_config` / `get_ai_budget_status` + 三段降級 ($80/$95/$100) + CONF-D `update_strategy_params` 擴充 (E1 · 3d)
- [ ] **4-16** Q1 GUI: Risk-tab AI Budget 區塊（綠/黃/紅進度條 + per-agent 配額 + reset month）(E1a · 2d)
- [ ] **4-17** Provider pricing table 綁定 (Anthropic/OpenAI/Local · 原 FA GAP-10) (E1 · 1d)
- [ ] **4-18** Decision_context 接線（claude_directive_id / linucb_arm_id / linucb_confidence_bound + news 欄位）(E1 · 1d)
- [ ] **4-19** test_full_learning_loop 集成測試（3 個端到端 case）(E4 · 2d)

**Group 6 — 週報 + 簽收**
- [ ] **4-20** 週報 plain-English generator + operator approval flow + weekly_review_log (E1+E1a · 2d)
- [ ] **4-21** E2 + E4 + E5 + AI-E + QA + PM 最終簽收 (2d)

殘留延後（前 phase 帶過來，非阻塞）：
- [ ] 2-11 actual training（需引擎運行收集 `trading.fills`）
- [ ] 2-PYO3-1 ContextDistiller PyO3 接入
- [ ] ort crate activation（首個 ONNX 模型訓練後一行啟用）
- [ ] 3b-07 BH-FDR 多重比較校正
- [ ] 3b-08 Grid 多目標 Pareto

## Phase 5 — James-Stein + DL-1 + DL-2（W16-18）

- [ ] 5-01~03：James-Stein per-parameter shrinkage + k-means 聚類
- [ ] 5-04~07：DL-1 Symbol Embedding(4D/8D/12D) + DL-2 Regime LSTM Shadow
- [ ] 5-08~09：JS+Scorer 整合 + correlation_pairs 寫入
- [ ] 5-10~13：E2 + E4 + QC + E5

## Phase 6 — 驗收（W19-20）

- [ ] 6-01~03：漸進放權管線 + 畢業邏輯 + Live 審批
- [ ] 6-04~06：全管線回放 + 壓測 + sync_commit Live 驗證
- [ ] 6-07~08：EvolutionEngine deprecated + 完整文檔
- [ ] 6-09~13：E2 + E4 + QA 端到端 + E5 + PM 確認

## Phase 4-Conditional（觸發後執行）

- [ ] 4-1 PairsTrading（需 3 月協整驗證）
- [ ] 4-2 Beta Hedging（需 HedgingEngine 穩定 1 月）
- [ ] 4-3 Kalman Filter（KAMA 表現不佳時）
- [ ] 4-5 Mac Studio 遷移 + 大模型（硬件到手）
- [ ] 4-10 Jump detection（K 線 body > 3σ 加寬止損）

---

## Live Gate（前置：Phase 6 + Alpha > 0）

- [ ] **LG-1** Paper Trading 穩定運行 21 天
- [ ] **LG-2** H0 Gate blocking 驗證（shadow → blocking）
- [ ] **LG-3** provider pricing table 正式綁定
- [ ] **LG-4** M 章 Supervised Live Gate
- [ ] **LG-5** N 章 Constrained Autonomous Live

---

## 長期整合（非緊急）

- [ ] **OC-3** 多通道分級告警（OC-1 webhook + OC-2 router 已完成）
- [ ] **OC-4** MCP PostgreSQL 自然語言查詢
- [ ] **OC-5** FundingArb REST 資金費率輪詢（Rust 接入）

---

## 工作流程速查

```
E1/E1a 並行（最多 5 路）→ E2 審查（強制）→ E4 回歸（強制）→ PM 確認 → commit
角色定義詳見 CLAUDE.md §八
```

**Bybit API 開發必查**：先讀 `docs/references/2026-04-04--bybit_api_reference.md`，已有端點直接調用，新增端點完成後同步更新手冊。
