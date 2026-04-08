# OpenClaw TODO — 工作計劃清單

最後更新：2026-04-08 PM
測試基準線：**engine lib 748 · core 387 · types 27 · ml_training 35 · Python control_api 2944 passed (22 pre-existing fail · 0 regression)**

> compact 後從此文件恢復工作狀態。第一個 `[ ]` 即為下一步起點。
> ARCH-RC1 1A→1C-3-E F-mini 詳細歷史已歸檔到 `docs/worklogs/2026-04-08--arch_rc1_1c_history_archive.md`。

---

## 🎯 下一步起點

### 1C-3-F — Python paper engine 徹底退場（下個 session · ~5h · 需 fresh context）

完整接手指引：`docs/worklogs/2026-04-08--1c3e_fmini_handoff.md`

- [ ] **F-a** Rust 補 paper-side `submit_order` IPC RPC
  - tick_pipeline.rs `PaperSessionCommand::SubmitOrder` variant + oneshot response
  - event_consumer/handlers.rs handler arm (走現有 process_intent 路徑)
  - ipc_server.rs `submit_paper_order` dispatch entry (template: `handle_risk_runtime_status`)
  - event_consumer/tests.rs +2-3 e2e tests via `handle_paper_command`
- [ ] **F-b** `shadow_decision_builder.py` 改走 EngineIPCClient，移除 PaperTradingEngine 依賴（Layer 2 wire-ready 路徑保留）
- [ ] **F-c** 刪 `paper_trading_engine.py` (2248 行) + 14 個依賴測試檔
  - test_shadow_decision* / test_paper_trading* / test_winrate_param_fixes / test_batch10_learning_oms / test_batch12_e2e_smoke / test_integration_phase{2,7,9,11,governance} / test_session9_fixes
- [ ] **F-d** `paper_trading_wiring.py` 清理 PAPER_STORE / ENGINE / SHADOW_CONSUMER 模組級 stale 宣告
- [ ] **F-e** E4 全綠 + 文檔同步 + commit (建議拆 F-a / F-bcd / F-e 三個 commit)

### 1C-4 收尾（F 完成後）

- [ ] Position Reconciler（trading.open_positions + Bybit 對帳 + cooldown 重建）
- [ ] **Governor tier override cooldown PG 持久化**（1C-3-B-2 known limitation：目前 in-memory，重啟重置；live 前必做）
- [ ] NewsPipeline `run_once` 60s scheduler spawn
- [ ] 熱重載 e2e 驗收測試（tick 跑著改參數 → 下個 tick 生效，無 restart）
- [ ] E-Merge-4（可選）Guardian owned config struct 退化為 RiskConfig sub-view
- [ ] E2 + E4 + QA Audit + 文檔同步

---

## 📅 Phase 4 follow-up（CODE-COMPLETE，等觀察期）

完成記錄：`docs/audits/2026-04-07_phase4_final_signoff_audit.md`（4-00 ~ 4-21 + 4.1 全部 SHIPPED · CONDITIONAL APPROVE）

### Live 前唯一 blocker
- [ ] **7+ days paper trading 數據累積** — calendar-time 觀察期 / DoD A/C/E metrics

### P1/P2 follow-up（非 blocker）
- [ ] 4-06 LinUCB live warm-start deployment（script 已交付，等首次 v1→v2 遷移）
- [ ] tick_pipeline.rs refactor 殘餘 — 2117 行仍超 1200 硬上限。已抽 decision_context_producer + position_risk_evaluator，剩 on_tick Step 0/0.5/1/4+5/dispatch loop borrow checker 重度，留專屬 session
- [ ] NewsPipeline run_once scheduler spawn（與 1C-4 合併）

---

## 🛡️ Live 前必做（SEC 安全 / 架構性）

- [ ] **SEC-05 / WP-B/SEC-05** GUI `innerHTML` XSS（架構性，16 文件 133 處）
- [ ] **SEC-08** IPC socket 無認證
- [ ] **SEC-17** `OPENCLAW_ALLOW_MAINNET` 2FA 架構決策
- [ ] **SEC-21** Cookie `secure=True`（HTTPS 上線後）
- [ ] **SEC-04 / 06 / 13** 深度 E3 審查（4 項）
- [ ] WP-CC/FS-1 / BI-1 / P9 / SM-1（4 項 CC）

---

## 🧰 WP Backlog（低優先 · 維護性）

詳細子項見 `docs/audits/2026-04-06_consolidated_remediation_report.md` §10。

### WP-F GUI（P2 ~10 項）
- [ ] WP-F/D-01 applyAIAdvice() 只 toast 無實效（Phase 4 Teacher 完成後修）
- [ ] WP-F/UX-06 Submit 無 loading 狀態
- [ ] WP-F/UX-07~10 術語混亂（Demo/Paper/Session）
- [ ] WP-F/AH-05 Apply 標籤誤導
- [ ] WP-F/AH-06 ⚠️ Risk-tab 每 15s 強制覆蓋用戶輸入（需重寫 loadAll 防抖）
- [ ] WP-F/O-xx / AH-08~11（詳見 §10.1）

### WP-E4 測試覆蓋（13 項）
- [ ] T-P2-5 rest_poller / T-P2-6 quality_writer / T-P2-9 PyO3 bridge tests / T-P2-10 panic-path / T-P2-11 並發
- [ ] T-Q3/Q4/Q7/Q8 覆蓋品質
- [ ] T-I1~I4 tarpaulin / CI 門禁 / 文檔
- [ ] WP-E4/T-P1-1 殘餘 event_consumer 完整事件循環整合測試

### WP-E5 大文件（延後）
- [ ] tick_pipeline.rs 2117 行（見 Phase 4 follow-up）
- [ ] governance_hub.py 1927 行 — 拆分需獨立 sprint + E2+E4

### WP-CLEANUP-GRAFANA-TESTS（P2，20 個 AttributeError）
- [ ] 更新 `test_grafana_data_writer.py` 對齊 `_from_rust` 後綴新方法名 + Rust IPC mock；或整檔刪除

### WP-CLEANUP-WHITELIST-UI（P2）
- [ ] 移除 tab-governance.html whitelist card markup (~309-470)
- [ ] 移除 governance.js / tab JS 6 個 helper
- [ ] 移除 governance_routes.py 3 個 410 stub + Pydantic class

### WP-I 文檔衛生（minor 命名 3 項）
- [ ] R4-NAME-1 / R4-MEM-1 / R4-REF-ST-1

---

## 📈 Phase 5 — James-Stein + DL-1 + DL-2（W16-18）

- [ ] 5-01~03 James-Stein per-parameter shrinkage + k-means
- [ ] 5-04~07 DL-1 Symbol Embedding + DL-2 Regime LSTM Shadow
- [ ] 5-08~09 JS+Scorer 整合 + correlation_pairs
- [ ] 5-10~13 E2 + E4 + QC + E5

## 📈 Phase 6 — 驗收（W19-20）

- [ ] 6-01~03 漸進放權管線 + 畢業邏輯 + Live 審批
- [ ] 6-04~06 全管線回放 + 壓測 + sync_commit Live 驗證
- [ ] 6-07~08 EvolutionEngine deprecated + 文檔
- [ ] 6-09~13 E2 + E4 + QA 端到端 + E5 + PM

## Phase 4-Conditional（觸發後）

- [ ] 4-1 PairsTrading (需 3 月協整) / 4-2 Beta Hedging (HedgingEngine 1 月穩定) / 4-3 Kalman / 4-5 Mac Studio 遷移 / 4-10 Jump detection

---

## 🚦 Live Gate（前置：Phase 6 + Alpha > 0）

- [ ] LG-1 Paper Trading 穩定運行 21 天
- [ ] LG-2 H0 Gate blocking 驗證（shadow → blocking）
- [ ] LG-3 provider pricing table 正式綁定
- [ ] LG-4 M 章 Supervised Live Gate
- [ ] LG-5 N 章 Constrained Autonomous Live

---

## 📦 殘留延後（前 phase，非阻塞）

- [ ] 2-11 actual training（需引擎運行收集 trading.fills）
- [ ] 2-PYO3-1 ContextDistiller PyO3 接入
- [ ] ort crate activation（首個 ONNX 模型訓練後）
- [ ] 3b-07 BH-FDR 多重比較校正
- [ ] 3b-08 Grid 多目標 Pareto
- [ ] CONF-D conf scaling 暴露給 agent via IPC `update_strategy_params`

## 長期整合（非緊急）

- [ ] OC-3 多通道分級告警
- [ ] OC-4 MCP PostgreSQL 自然語言查詢
- [ ] OC-5 FundingArb REST 資金費率輪詢

---

## 📚 已完成歸檔索引

- **ARCH-RC1 Session 1A → 1C-3-E F-mini**：`docs/worklogs/2026-04-08--arch_rc1_1c_history_archive.md`（含 Session 1A 死代碼大屠殺 / 1B Config 骨架 / 1C-1 Rust call site / 1C-2 TOML+5 引擎熱重載 / 1C-3 Python 收編 全部詳細歷史 + commit hash）
- **Phase 4 (4-00 ~ 4-21 + 4.1)**：`docs/audits/2026-04-07_phase4_final_signoff_audit.md` + `docs/references/2026-04-06--phase4_execution_plan_v2.md`
- **Session 12 PNL-1~7 / DB-RUN-1~7 / CONF-A~C**：commits `ed01bf5`..`6608ab7`（詳見 CLAUDE_CHANGELOG.md）
- **Session 13 R3 backlog 收尾**：`docs/audits/2026-04-06_consolidated_remediation_report.md`
- **Session 11 之前**：`docs/worklogs/2026-04-06--completed_todo_archive_l3_phases.md`
- **Phase 0/1/2/3 + Rust migration**：`docs/worklogs/2026-04-04--completed_todo_archive_phase0123_rust.md`
- **L3 整合審計**：`docs/audits/2026-04-06_consolidated_remediation_report.md`
- **已知問題清單**：`docs/KNOWN_ISSUES.md`
- **Bybit API 字典手冊**：`docs/references/2026-04-04--bybit_api_reference.md`（開發前必查）

---

## ⚙️ 工作流程速查

```
E1/E1a 並行（最多 5 路）→ E2 審查（強制）→ E4 回歸（強制）→ PM 確認 → commit
角色定義詳見 CLAUDE.md §八
```

**Bybit API 開發必查**：先讀 `docs/references/2026-04-04--bybit_api_reference.md`，已有端點直接調用，新增端點完成後同步更新手冊。

**風控參數修改強制原則**：所有風控/止損/cost-gate/regime 參數必須對齊 Rust `RiskConfig` 並透過 IPC `patch_risk_config` 單一通道更新。禁止 hot path 寫死數值或繞過 patch 校驗。
