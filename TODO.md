# OpenClaw TODO — 工作計劃清單

最後更新：2026-04-06（Session 12 · PNL-1~7 + magic-number cleanup + DB-RUN-1~7）
測試基準線：**474 engine + 413 core + 35 ml_training + 11 control_api smoke** · 0 failures

> compact 後從此文件恢復工作狀態。第一個 `[ ]` 即為下一步起點。

**參考索引**
- 已完成歸檔（截至 Session 11）：`docs/worklogs/2026-04-06--completed_todo_archive_l3_phases.md`
- 之前的歸檔：`docs/worklogs/2026-04-04--completed_todo_archive_phase0123_rust.md`
- L3 整合審計：`docs/audits/2026-04-06_consolidated_remediation_report.md`
- 已知問題清單：`docs/KNOWN_ISSUES.md`
- Bybit API 字典手冊：`docs/references/2026-04-04--bybit_api_reference.md`（開發前必查）

---

## 當前狀態

L3 審計整改 R0+R1+R2 全部完成（Session 10/11，10 個 commits）。下一步候選：
1. **PNL 根因修復**（虧損分析 7 項，引擎運行數據驅動）
2. **DB 運行治理**（signals 寫入降頻 + decision_context 治理）
3. **Phase 4 啟動**（Claude Teacher + LinUCB + News + DL-3）
4. **R3 backlog 清掃**（SEC/FA/Idle writers/WP 子項）

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

### 待辦：策略 confidence 動態化

- [ ] 當前固定 0.50，低波動市場全被 cost gate 攔截。需根據 ATR/regime 動態化

---

## R3 Backlog（L3 審計剩餘 OPEN）

### 安全 / 架構性

- [ ] **SEC-05** GUI `innerHTML` XSS（架構性，16 文件 133 處）
- [ ] **SEC-09** `/startup-status` 認證（by-design，保持開放）
- [ ] **SEC-11** Cost-Gate ATR=0 fail-open（產品/風控決策）
- [ ] **SEC-17** `OPENCLAW_ALLOW_MAINNET` 2FA（2FA 架構）
- [ ] **SEC-21** Cookie `secure=True`（HTTPS 上線後）
- [ ] **FA GAP-2/4/8/9/10**（架構性，Phase 4 範圍）

### Idle Writers 殘留

- [ ] **#3 liquidations** — Bybit V5 `allLiquidation` topic 需手動 WS 驗證後再加（避免重蹈 `29fc1ef` 毒連線）
- [x] **#5 drift_events writer** — 調查結果：已正常運作（drift_detector.rs:478 自洽週期檢測，main.rs:875 spawn）
- [x] **#6 quality_events writer** — 調查結果：已正常運作（quality_writer.rs:69，event_consumer:600 atomic 接 tick）

### 測試覆蓋

- [ ] **WP-E4/T-P1-1 殘餘** event_consumer 完整事件循環整合測試（fixture harness，獨立 sprint）
- [x] **I-22 殘留** event_consumer mod.rs 785 → 628（dispatch.rs + setup.rs 提取）

### WP 子檢查清單回鏈（223 sub-items）

詳見 `docs/audits/2026-04-06_consolidated_remediation_report.md` §10：
- WP-F GUI 47 / WP-G hardcoded 43 / WP-E4 tests 34 / WP-I docs 42
- WP-E5 opt 20 / WP-B sec 12 / WP-CC 8 / WP-FA 5 / WP-BB 3

---

## Phase 4 — Claude Teacher + LinUCB + News + DL-3（W13-15）

- [ ] 4-01~03：Claude-as-Teacher → ExperimentLedger + 效果追蹤
- [ ] 4-04~06：LinUCB + Model Performance 監控 + Adversarial Validation
- [ ] 4-07~10：新聞 Agent 接口（mock，數據源暫緩）
- [ ] 4-11~14：DL-3 TimesFM/Chronos（異步 A/B，AUC<0.01 棄用）
- [ ] 4-15~20：集成測試 + E2 + E4 + CC/E3 + AI-E Go/No-Go + E5

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
