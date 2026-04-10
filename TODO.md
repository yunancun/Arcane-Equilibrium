# OpenClaw TODO — 工作計劃清單

最後更新：2026-04-10（Live GUI P0~P6 全完畢 + 縮倉監控 + OPENCLAW_ALLOW_MAINNET 鎖移除 + DB Signal Diamond 規劃）
測試基準線：**Rust engine lib 840 · Python control_api 2692 passed (1 pre-existing fail · 1 skipped) · ml_training 135 passed (6 skipped)**

> compact 後從此文件恢復工作狀態。第一個 `[ ]` 即為下一步起點。
> 歷史歸檔索引在文件末尾。詳細完成度視角見 README.md。

---

## 🎯 當前焦點（按執行順序）

### 0. 🔴 Live GUI + Per-Engine Risk + API Key 管理（新工作 2026-04-10 排入）

目標：Live 頁面功能完備可測試、風控按引擎分離、GUI 可安全填入/替換 API key。
物理隔離原則：Live key 槽（`secrets/secret_files/bybit/live/`）目前填另一個 Demo 帳號，上線時換 key，零代碼改動。

#### P0 — GUI 框架 + API key 管理（不需改 Rust，可立即做）

- [x] **LIVE-P0-1** `tab-settings.html` 加 API Key 管理區塊 ✅ (commit c680ffd)
  - `GET /api/v1/settings/api-key/{slot}` → 返回 `{has_key, key_hint: "****XXXX", last_modified}`（永不返回明文）
  - `POST /api/v1/settings/api-key/{slot}` → validate via test REST call → 寫入 `secrets/secret_files/bybit/{slot}/` → `chmod 600` → 返回 `{saved, validated, key_hint}`
  - `settings_routes.py` 新建 + `main.py` 注册 + `tab-settings.html` 加 UI 卡片 + 替換彈窗

- [x] **LIVE-P0-2** `tab-live.html` 前置條件動態化 ✅ (commit c680ffd)
  - 前置條件清單改為 API 動態查詢（`/api/v1/governance/status` + `/api/v1/paper/session/status` + `/api/v1/settings/api-key/live`），動態顯示 ✓/⬜/⚠
  - Phase badge 更新為當前真實 Phase（Phase 5 觀察期 → Phase 6 待實施）

- [x] **LIVE-P0-3** `tab-live.html` 實盤儀表板框架（解鎖後顯示）✅ (commit c680ffd)
  - 鎖定條件：`execution_authority != "granted"`，顯示鎖定頁
  - 解鎖後：顯示完整儀表板（positions、orders、PnL、緊急停止、倉位表格）
  - 視覺：紅色邊框主題 + 大號 PnL 卡片強調真實資金風險
  - 獨立啟停按鈕（獨立於 tab-trading.html）；P1-3 session routes 佔位 stub

#### P1 — Rust TradingMode::Live + 槽位感知 key 讀取

- [x] **LIVE-P1-1** `bybit_rest_client.rs`：`read_secret_file(slot, name)` 槽位感知 ✅ (commit 11283c7)
  - 現在硬編碼 `bybit/demo/`，改為接受 `slot: &str` 參數
  - `BybitRestClient::new()` 新增 `slot: Option<&str>` 參數，默認 `"demo"`

- [x] **LIVE-P1-2** `config/mod.rs`：`TradingMode` 加 `Live` variant ✅ (commit 11283c7)
  - `PaperOnly` | `Demo`（原 Exchange 改名）| `Live`（Mainnet + live key slot）
  - `main.rs` 依 mode 選 `BybitEnvironment::Demo` 或 `Mainnet` + 對應 key slot

- [x] **LIVE-P1-3** Python `/api/v1/live/session/start|stop|status` 路由 ✅ (commit 11283c7)
  - 與 paper_trading_routes.py 平行，但目標是 Live engine state
  - `start` 需確認 `execution_authority = granted`（硬鎖，不可繞過）
  - `stop` → 平倉 + cancel orders + 進入 observation

#### P2 — Per-Engine RiskConfig 分離

- [x] **LIVE-P2-1** Rust：三個獨立 RiskConfig 文件 ✅ (commit 006d905)
  - `risk_config_paper.toml`、`risk_config_demo.toml`、`risk_config_live.toml`
  - Env var 覆蓋路徑：`OPENCLAW_RISK_CONFIG_PAPER` / `_DEMO` / `_LIVE`
  - IPC `patch_risk_config` 加 `engine: "paper"|"demo"|"live"` 路由到對應 store

- [x] **LIVE-P2-2** GUI 風控頁 per-engine tab ✅ (commit 006d905)
  - `tab-risk.html` 頂部加 Engine 選擇器（Paper / Demo / Live）
  - 每個 engine 顯示/修改各自的 RiskConfig
  - Live risk tab 加額外警示：修改實盤風控需二次確認彈窗

- [x] **LIVE-P2-3** E2 + E4 全量回歸 + commit ✅ (commit 006d905)

#### P3 — Gov-P1 + 全阻隔移除 + 縮倉監控（2026-04-10）

- [x] **LIVE-P3-1** Gov-P1：`post_live_session_start` 自動授予 `execution_authority`；`_submit_live_governance_request()` 向 GovernanceHub 提交 PENDING 審計記錄；`post_live_session_resume` 改為 global_mode 二次確認 ✅ (commit 045e79c)
- [x] **LIVE-P3-2** 移除 `OPENCLAW_ALLOW_MAINNET=1` Rust hard guard（`bybit_rest_client.rs` 9 行）；更新 `config/mod.rs` docstring + `main.rs` banner ✅ (commit 25b5d73)
- [x] **LIVE-P3-3** `_live_contraction_monitor()`：每 5 分鐘輪詢 peak/equity；5% warn / 15% halt（revoke auth + close all + freeze GovernanceHub）；`tab-live.html` 縮倉 badge ✅ (commit 25b5d73)

#### P4 — Live-Demo 槽位 + 指標端點（2026-04-10）

- [x] **LIVE-P4-1** `settings_routes.py` `live_demo` 虛擬槽位（validate via demo server，寫入 live path）；`tab-settings.html` 3 API key 卡片 + peek + 上下文警示 ✅ (commit 25b5d73)
- [x] **LIVE-P4-2** `GET /api/v1/live/metrics` 新端點；paper `/metrics` 修復（`compute_full_metrics()` 完整指標）；`tab-live.html` Performance Metrics 區塊 ✅ (commit 25b5d73)

---

### 1. 🟢 觀察期 — 等數據（無開發動作，只需維運）

Phase 5 cost_gate 改造已全部上線（mode-aware exploration + JS shrinkage + cold-start damping）。
現在唯一阻擋 Live 的是**時間**：需要 ARCH-RC1 後乾淨數據累積。

- [ ] **PH5-VERIFY-1** 7d paper observation — 看 fills / realized pnl 分布是否改善（同時也是 Live blocker 觀察期）
- [ ] **2026-04-11 JS 滾動重跑** `PG_PASSWORD=... python3 -m program_code.ml_training.james_stein_estimator --days 3`
  - 之後每週重跑，窗口逐步拉長（7d → 14d → 30d）直到估計穩定
  - 若某 cell 轉正 → 下次引擎重啟後 mode-aware gate 自動對該 pair 生效
  - `settings/edge_estimates.json` 更新後需重啟引擎才生效（無 hot-reload）
- [ ] **LG-1** Paper Trading 穩定運行 21 天（Live Gate 前置）

### 2. ✅ 1C-4 最終收尾（DONE）

ARCH-RC1 1C-4 wrap commit chain 已完成（A1/B1/B2/熱重載 e2e/E-Merge-4/doc sync）。

- [x] **A2** NewsPipeline `run_once` 60s scheduler spawn ✅ — 3 providers (CryptoPanic + 2 RSS) + 4-09 router + config hot-reload gate
- [x] **1C-4 最終驗收** E2 + E4 + QA Audit + 文檔同步 ✅

### 3. ✅ DEAD-PY-1 死代碼清理（DONE）

Phase 1+2+3+4 全部完成。

- [x] **Phase 3 殘留** state_*.py / pnl_ops.py 「Wave A/B/C」標籤 → 移到 git history ✅
- [x] **Phase 3 殘留** `main.py:176` 「WP-ARCH-RC1 RC1-2」舊命名 ✅
- [x] **Phase 4 殘留** whitelist UI 全量移除（tab-governance.html 220 行 + governance.js 19 行）✅

**KEEP（不要動）**：`risk_view_client.py:196-197` force_governor_tier_* / `apply_ai_consultation` / `governance_hub.py` RC-11 docstrings / `bridge_core.py` activate/on_tick docstrings — 全有 test callers 或生產呼叫。

---

## 🛡️ Live 前必做（SEC 安全 + 告警基礎設施）

### 安全（架構性，必做）
- [x] **SEC-05 / WP-B/SEC-05** GUI `innerHTML` XSS ✅ — safeText()→ocEsc() 委託 + 逐文件 ocEsc() 包裹（app.js / linucb_card.html / tab-ai.html）
- [ ] **SEC-08** IPC socket 無認證
- [x] **SEC-17** `OPENCLAW_ALLOW_MAINNET` 架構決策 ✅ — 決策：移除 env var guard，API key 填入 = 唯一上線條件（commit 25b5d73）
- [ ] **SEC-21** Cookie `secure=True`（HTTPS 上線後）
- [ ] **SEC-04 / 06 / 13** 深度 E3 審查（4 項）
- [ ] WP-CC/FS-1 / BI-1 / P9 / SM-1（4 項 CC）

### 告警通道（Phase 6 reconciler 自動收縮的硬依賴）
- [ ] **OC-3** 多通道分級告警（P0→緊急群 / P1→常規群）— **阻塞 6-RC-6**
- [ ] 1C-4 B2 Position Reconciler 已上線 30s 真相輪詢 + V014 audit，但只進審計。在 OC-3 + Phase 6-RC-1~9 完成前，operator 必須人工看 V014 處理漂移。

---

## 📈 Phase 6 — 漸進放權 + Reconciler 自動收縮 + 驗收（W19-20）

### 6-RC（Reconciler 自動 governor 動作層）

> **背景**：1C-4 B2 已部署觀察層（30s 輪詢 + 5 級漂移分類 + V014 audit），自動 governor 收縮被降級移除（QA+E2 發現原設計與 B1 operator cooldown 語義衝突）。Phase 6 補上動作層。

- [ ] **6-RC-9 Baseline staleness 政策** — `PositionView` 加 `last_fetch_ms`，>10min 走 warmup-reseed（**6-RC-1 前必須先做**，否則 REST 恢復第一個 cycle 會誤觸發）
- [ ] **6-RC-1 動作通道隔離** — 新增 `PaperSessionCommand::ReconcilerAutoContract`，handler 直呼 `governance.risk.de_escalate_to`，**繞過** operator override 白名單與 step-rule guard
- [ ] **6-RC-2 V014 event_type 隔離** — `event_type="reconciler_auto_contract"` 與 `governor_de_escalate` 區隔；補 SQL filter 安全網（顯式 `AND payload->>'reason_code' IN (operator_whitelist)`）
- [ ] **6-RC-3 動作策略** — Major/Orphan/Ghost → step one tier looser；連續 ≥3 cycle 持續漂移 → Defensive；單 cycle ≥5 個獨立漂移 → CircuitBreaker
- [ ] **6-RC-4 自身冷卻** — 同 (symbol,side) 30 分鐘內不重複；全局 5 分鐘最多 1 次
- [ ] **6-RC-5 Per-symbol minQty dust floor** — 從 instrument_info 讀 `lotSizeFilter.minOrderQty`，閾值 `1.5 × minQty`（**禁止**全局魔法數）
- [ ] **6-RC-6 多通道告警 + 15s 介入窗口** — 動作前先告警，15s 未 ACK 才執行 ⚠️ 阻塞於 OC-3
- [ ] **6-RC-7 整合測試** — e2e 斷言進入 `apply_de_escalation`，覆蓋 4 場景
- [ ] **6-RC-8 Live blocker 解除** — 完成後從 Live blocker 清單移除「Bybit REST `/v5/position/list` 必須可達」隱含依賴

### 6-Phase（漸進放權 + 驗收）
- [ ] 6-01~03 漸進放權管線 + 畢業邏輯 + Live 審批
- [ ] 6-04~06 全管線回放 + 壓測 + sync_commit Live 驗證
- [ ] 6-07~08 EvolutionEngine deprecated + 文檔
- [ ] 6-09~13 E2 + E4 + QA 端到端 + E5 + PM

---

## 🚦 Live Gate（前置：Phase 6 + 21 天 paper + Alpha > 0）

- [ ] LG-1 Paper Trading 穩定運行 21 天（同上）
- [ ] LG-2 H0 Gate blocking 驗證（shadow → blocking）
- [ ] LG-3 provider pricing table 正式綁定
- [ ] LG-4 M 章 Supervised Live Gate
- [ ] LG-5 N 章 Constrained Autonomous Live

---

## 📈 Phase 5 補強（功能已交付，這些是後續精度優化，非阻塞）

WIRE-0/WIRE-1 + DL-1/DL-2 + JS-1 + 5-01~03 已全部 ✅。下面是原 Phase 5 backlog 中尚未做的精度提升項，待觀察期過後評估是否還需要：

- [ ] 5-04~07 DL-1 Symbol Embedding + DL-2 Regime LSTM Shadow
- [ ] 5-08~09 JS+Scorer 整合 + correlation_pairs
- [ ] 5-10~13 E2 + E4 + QC + E5

---

## 🧰 WP Backlog（低優先 · 維護性）

詳細子項見 `docs/audits/2026-04-06_consolidated_remediation_report.md` §10。

### WP-F GUI（P2 ~10 項）
- [ ] WP-F/D-01 applyAIAdvice() 只 toast 無實效（Phase 4 Teacher 完成後修）
- [ ] WP-F/UX-06 Submit 無 loading 狀態
- [ ] WP-F/UX-07~10 術語混亂（Demo/Paper/Session）
- [ ] WP-F/AH-05 Apply 標籤誤導
- [x] WP-F/AH-06 ✅ Risk-tab dirty-tracking 防止 15s loadAll 覆蓋用戶輸入
- [ ] WP-F/O-xx / AH-08~11（詳見 §10.1）
- [ ] `preferred_margin_mode` / `preferred_position_mode` GUI 入口（Rust 僅存儲未執行）

### WP-E4 測試覆蓋（13 項）
- [ ] T-P2-5 rest_poller / T-P2-6 quality_writer / T-P2-9 PyO3 bridge tests / T-P2-10 panic-path / T-P2-11 並發
- [ ] T-Q3/Q4/Q7/Q8 覆蓋品質
- [ ] T-I1~I4 tarpaulin / CI 門禁 / 文檔
- [ ] WP-E4/T-P1-1 殘餘 event_consumer 完整事件循環整合測試

### WP-E5 大文件
- [ ] tick_pipeline.rs 2117 行 — 已抽 decision_context_producer + position_risk_evaluator，剩 on_tick Step 0/0.5/1/4+5/dispatch loop borrow checker 重度，留專屬 session
- [ ] governance_hub.py 1927 行 — 拆分需獨立 sprint + E2+E4

### ✅ WP-CLEANUP-WHITELIST-UI（DONE · commit 7602656）
- [x] tab-governance.html whitelist card + modal + CSS + JS + init (−220 lines)
- [x] governance.js 3 個 dead API wrappers (−19 lines)
- [ ] governance_routes.py 3 個 410 stub + Pydantic class（保留：後端 stub 無害，移除需額外 E4）

### WP-I 文檔衛生（minor 命名 3 項）
- [ ] R4-NAME-1 / R4-MEM-1 / R4-REF-ST-1

---

## 📦 殘留延後（前 phase，非阻塞）

- [ ] 2-11 actual training（需引擎運行收集 trading.fills）
- [ ] ort crate activation（首個 ONNX 模型訓練後）
- [x] 3b-07 BH-FDR 多重比較校正
- [x] 3b-08 Grid 多目標 Pareto
- [x] CONF-D conf scaling 暴露給 agent via IPC `update_strategy_params`
- [ ] 4-06 LinUCB live warm-start deployment（script 已交付，等首次 v1→v2 遷移）

## Phase 4-Conditional（觸發後）

- [ ] 4-1 PairsTrading（需 3 月協整）/ 4-2 Beta Hedging（HedgingEngine 1 月穩定）/ 4-3 Kalman / 4-5 Mac Studio 遷移 / 4-10 Jump detection

## 長期整合（非緊急）

- [ ] OC-3 多通道分級告警（同 Live 前必做段，是 6-RC-6 阻塞依賴）
- [ ] OC-4 MCP PostgreSQL 自然語言查詢
- [ ] OC-5 FundingArb REST 資金費率輪詢

---

## 📚 已完成歸檔索引

- **Phase 5 P0 promotion + WIRE chain**：commits `5d7d673` → `0e848fa` → `638afa3` → `563d54a` → `5e760be`
- **ARCH-RC1 Session 1A → 1C-4 WRAP**：`docs/worklogs/2026-04-08--arch_rc1_1c_history_archive.md` + `docs/archive/2026-04-08--main_docs_1c3_1c4_narrative.md`
- **Phase 4 (4-00 ~ 4-21 + 4.1)**：`docs/audits/2026-04-07_phase4_final_signoff_audit.md` + `docs/references/2026-04-06--phase4_execution_plan_v2.md`
- **Session 12 PNL/DB-RUN/CONF**：commits `ed01bf5`..`6608ab7`（詳見 CLAUDE_CHANGELOG.md）
- **Session 13 R3 backlog 收尾**：`docs/audits/2026-04-06_consolidated_remediation_report.md`
- **Session 11 之前**：`docs/worklogs/2026-04-06--completed_todo_archive_l3_phases.md`
- **Phase 0/1/2/3 + Rust migration**：`docs/worklogs/2026-04-04--completed_todo_archive_phase0123_rust.md`
- **L3 整合審計**：`docs/audits/2026-04-06_consolidated_remediation_report.md`
- **CFG-PERSIST 三件套（已完成）**：CFG-PERSIST-1 `5d7d673` · CFG-COST-EDGE-1 `0e848fa` · diag log `638afa3`
- **DEAD-PY-1 全部完成**：Wave labels `b7f644b` + whitelist UI + A2 scheduler `7602656`
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
