# OpenClaw TODO — 工作計劃清單

最後更新：2026-04-08 深夜（**ARCH-RC1 1C-4 WRAP COMPLETE**）
測試基準線：**engine lib 769 · core 387 · types 27 · ml_training 35 · Python control_api 2678 passed (1 pre-existing fail · 0 regression)**

> compact 後從此文件恢復工作狀態。第一個 `[ ]` 即為下一步起點。
> ARCH-RC1 1A→1C-3-F 詳細歷史已歸檔到 `docs/worklogs/2026-04-08--arch_rc1_1c_history_archive.md` + `docs/CLAUDE_CHANGELOG.md`。

---

## 🎯 下一步起點

### 🔥🔥 P0 — Phase 5 提前啟動（2026-04-08 Edge 危機）

**根因實證**：tab-paper / tab-demo 4 筆 round-trip 全部 realized pnl 0.01–0.04%（SOLUSDT/DOGEUSDT），但 fee=0.055% 雙邊 break-even=0.11% → 結構性負期望值。Diag log（`tick_pipeline.rs:1864` warn 已永久化）證實 paper 平倉 100% 為 `COST EDGE: ratio 2.5–20+, pnl 0.01–0.04%`。

**Cost_gate 為何沒攔住**（`intent_processor.rs:558`）：
```
EV = atr × confidence × qty
(qty 與 fee 兩邊約掉 → gate 與 size 無關)
EV/fee = atr_pct × conf / (2 × fee_rate)
```
公式錯誤地把 ATR（range，非 directional edge）當期望盈利，而且 `confidence` 是策略自評未對照歷史 → 高估 ~13×（DOGE 案例：predict 0.052% vs realized 0.004%）。

**hand-roll C+D（in-house realized-edge tracker）已被否決**：跟 Phase 5 (DL-1/2 + James-Stein) 重疊 ~70%，會被淘汰。決定**直接把 Phase 5 提到 P0**。

- [x] **PH5-PROMOTE-1** 確認 Phase 5 spec 目前位置 + 把 W16-18 的目標重新排序到「立即啟動」
- [x] **PH5-DL-1** K 線 replay 確認可從 DB 直接用 paper fills（2693 筆），無需歷史 replay 基礎設施
- [x] **PH5-DL-2** Per (strategy × symbol) realized edge distribution 統計 — `realized_edge_stats.py` 交付（全部負 edge：-4 to -33 bps）
- [x] **PH5-JS-1** James-Stein shrinkage estimator — `james_stein_estimator.py` 交付，寫入 `learning.james_stein_estimates`（8 rows）+ `settings/edge_estimates.json`
- [x] **PH5-WIRE-0** cost_gate cold-start 阻尼 0.2 已上線（`intent_processor.rs`），Rust 769 pass, Python 2694 pass，0 regression
- [ ] **PH5-WIRE-1** `intent_processor` cost_gate 改用 shrunk realized edge 取代 `atr × conf`，cold-start 仍 fallback ATR×conf×0.2（全部 JS 估計為負，先觀察 paper 改善後再接線）
- [ ] **PH5-VERIFY-1** 跑 7d paper observation 看 fills / realized pnl 分布是否改善（同時也是 Live blocker 觀察期）

**參考文件**：`docs/references/2026-04-04--*.md` 系列 ML/Phase 5 設計（James-Stein / Teacher-Student），需要在 PH5-PROMOTE-1 階段彙整重讀。

**Edge 概念釐清備忘**：edge = 扣成本前的單筆期望淨收益（bps）。當前實證 realized edge ≈ 2 bps，fee = 11 bps → Net EV ≈ −9 bps。修 cost_gate 公式 ≠ 修策略；要修策略只能靠 backtest 找出真有 edge 的 (strategy, symbol) 子集。

---

### ✅ P0 — ConfigStore disk persistence（2026-04-08 完成）

完成 commits：CFG-PERSIST-1 `5d7d673` · CFG-COST-EDGE-1（含 Task #8）`0e848fa` · cost_edge revert + diag log `638afa3`。
- [x] CFG-PERSIST-1 atomic TOML write-back
- [x] CFG-PERSIST-3 max_cost_edge_ratio dead-write 修復（routed to BudgetConfig via patch_budget_config）
- [x] CFG-PERSIST-3 殘留：`max_correlated_exposure_pct` + `allowed_categories` GUI 入口已補入 tab-risk.html Position Limits 卡（數字輸入 + 逗號分隔文字輸入，連 loadAll / savePositionSettings / Current Values 全接線）；`preferred_margin_mode` / `preferred_position_mode` 延後（Rust 僅存儲，未執行，移入 WP-F 後端 backlog）

---

### 🔥 P0 — ConfigStore disk persistence（已完成保留 narrative，下面為原條目）

`rust/openclaw_engine/src/config/store.rs:9` 註釋寫「不負責落盤，是 1C 載入器的工作」，但 1C loader 從來只實作載入，**從來沒實作回寫**。後果：所有 GUI patch（risk/learning/budget）只在 in-memory ConfigStore 生效，引擎重啟後 TOML reload → 全部 reset。違反 CLAUDE.md §三「Rust ConfigStore 為權威 + 禁止 restart-to-apply」。

- [ ] **CFG-PERSIST-1** `ConfigStore::replace`/`apply_patch` 成功後 spawn debounced task（仿 `persistence.rs` 5s 模式），把 `toml::to_string(&new)` 原子寫回（temp file + rename），覆蓋 risk / learning / budget 三個 store
- [ ] **CFG-PERSIST-2** 加 test：patch → 模擬重啟 → reload TOML → 值還在
- [ ] **CFG-PERSIST-3** GUI 寫入面字段死洞清理（2026-04-08 全欄位審計順手發現）：
  - `max_correlated_exposure_pct`：後端完備但 GUI 無入口
  - `allowed_categories` / `preferred_margin_mode` / `preferred_position_mode`：後端完備但 GUI 無入口
  - `max_cost_edge_ratio`：Pydantic 接受但 `_GLOBAL_TO_RUST` 沒對應，靜默 drop
  - 決定：補 GUI 入口 OR 從 Pydantic/mapping 移除

### ARCH-RC1 1C-3 + 1C-4 WRAP COMPLETE ✅（2026-04-08）

完整 narrative：`docs/archive/2026-04-08--main_docs_1c3_1c4_narrative.md`
1C-4 wrap commit chain：A1 `03fee49` · B1 `e840003` · B2 `36335d7`→`ab1e0d8`→`9811bf3` · 熱重載 e2e `4780b04` · E-Merge-4 `06742b3` · 1C-3-D 留尾 `8554779` · doc sync `f882473`。

**1C-4 真正剩餘**：
- [ ] **A2** NewsPipeline `run_once` 60s scheduler spawn（延後：等 4-09 router decision + provider wire-up，~120-200 行）
- [ ] E2 + E4 + QA Audit + 文檔同步（doc sync wrap 之後的最終驗收）

### 1C-4 留尾 · Python app/ 死代碼大掃除（DEAD-PY-1，~7h，非阻塞）

掃描範圍：`program_code/exchange_connectors/bybit_connector/control_api_v1/app/*.py`，1C-3 → 1C-4 wave 後遺留 ~42 個候選項，分 4 階段：

**Phase 1 — SAFE-DELETE（0 callers，~2h，零風險）：**
- [x] `paper_trading_wiring.py:40` `PAPER_STORE = None` 連同 2 個 import 點
- [x] `paper_trading_wiring.py:70` `ENGINE = None` 連同 3 個 `if ENGINE is not None` dead branch（含 line 398-406 注入區塊）
- [x] `legacy_routes.py:150,576` `if PAPER_ENGINE is None` dead branch（改直接返回 error）
- [x] `strategy_wiring.py:491` 整個 `if PAPER_ENGINE is not None` 區塊（unreachable）
- [x] `governance_routes.py:447` `if ENGINE is not None and hasattr(...)` dead branch
- [x] `bridge_core.py:309` `deactivate()` 已移除（0 callers）；`activate()` / `on_tick()` 保留（test callers）
- [x] `governance_routes.py:1268-1319` 3 個 whitelist 410-Gone stub 端點 + `_WHITELIST_DEPRECATED_DETAIL` 常量
- [ ] `strategist_agent.py:982-995` `collect_pending_intents()`（TD-2 deprecated）— SKIP：有 test caller
- [ ] `bridge_stats.py:560+` `on_tick_result()`（依賴 deprecated bridge.on_tick）— SKIP：有 test caller

**Phase 2 — CHECK-ROUTES（先看 access log，~1h）：**
- [x] `learning_auto_pipeline.py` `apply_ai_consultation()` + route 已刪除（0 API hits 確認，2 tests 同刪）
- [ ] `governance_hub.py` 5 個 RC-11 deprecated 方法 — SKIP：`trigger_risk_upgrade` guardian_agent.py 生產呼叫；`check_learning_tier_capability` 內部呼叫 line 948；其餘 3 個有 test callers，churn 不值得
- [ ] `layer2_cost_tracker.py:557-576` `record_ollama_call()` deprecated 包裝 — SKIP：test callers 存在，churn 不值得

**Phase 3 — STALE-COMMENT 整合（~3h，doc-only）：**
- [x] `paper_trading_routes.py` RC-10/RC-12 markers 清理
- [x] `bridge_core.py` DEPRECATED 注釋保留（activate/on_tick 有 test callers，docstring 有意義）
- [x] `strategy_wiring.py:964,991,993` RC-12 + 1C-3-D 注釋去重
- [x] `strategy_read_routes.py` RC-11 markers 替換為現狀描述
- [x] `main.py` RC-10 / ARCH-RC1 migration markers 清理
- [ ] state_*.py / pnl_ops.py "Wave A/B/C" 標籤（生產 3+ 月）→ 移到 git history（低優先）
- [ ] `main.py:176` "WP-ARCH-RC1 RC1-2" 舊命名（低優先）

**Phase 4 — GUI HTML/JS 清理（~1h）：**
- [ ] `static/tab-governance.html:310-322` whitelist UI 區塊 → 移至 WP-CLEANUP-WHITELIST-UI（太大，獨立 session）
- [x] `static/tab-risk.html:38` 1C-3-C "Loss Cooldown" 注釋
- [x] `static/tab-system.html:84,404,458` RC-12 market feed 注釋
- [x] `static/tab-paper.html:161-202` RC-10 session control disabled 注釋
- [x] `static/app.js:2396-2518` RC-10 manual orders disabled 注釋

**KEEP（不要動）：**
- `risk_view_client.py:196-197` `force_governor_tier_*` stub — 1C-3-B-2 已實現，是真實方法
- `apply_ai_consultation` 在 access log 確認前不可動
- `governance_hub.py` RC-11 DEPRECATED docstrings — 方法仍在，docstring 正確標注狀態
- `bridge_core.py` activate() / on_tick() DEPRECATED docstrings — test callers 存在

**驗收**：Phase 1+3+4 complete，Python 2680 passed（21 pre-existing fail，0 regression）。
報告來源：sub-agent dead-code audit 2026-04-08（4 phase plan，risk LOW）。


---

## 📅 Phase 4 follow-up（CODE-COMPLETE，等觀察期）

完成記錄：`docs/audits/2026-04-07_phase4_final_signoff_audit.md`（4-00 ~ 4-21 + 4.1 全部 SHIPPED · CONDITIONAL APPROVE）

### Live 前 blocker
- [ ] **7+ days paper trading 數據累積** — calendar-time 觀察期 / DoD A/C/E metrics
- [ ] **多通道告警上線** — 1C-4 B2 降級後，position drift 只進 V014，需要 operator 通知通道（OC-3 多通道告警）才能保證偏差被即時看見。Phase 6 自動收縮上線後此項可解除（屆時自動動作 + 告警雙保險）。

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
- [x] 刪除 20 個調用不存在方法的測試（`_write_pnl` / `_write_market_tickers` / `_write_system_health` / `_write_trade_executions` — 已於 Rust 遷移中移除或重命名為 `_from_rust` 後綴）；保留 10 個仍通過的測試。測試基準線：21 fail → 1 fail

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

### Phase 6 自動收縮（Position Reconciler 自動 governor 動作層）

> **背景**：1C-4 B2 Position Reconciler 已部署 30s Bybit 真相輪詢 + 5 級漂移分類 + V014 audit，但**自動 governor 收縮被降級移除**（QA+E2 審查發現原設計與 B1 operator cooldown 語義衝突）。漂移目前只進審計，等 operator 看 V014 後人工處理。Phase 6 補上這一層自動動作。

**目標規格（必須達成才能視為完成）：**

- [ ] **6-RC-1 動作通道隔離** — 新增 `PaperSessionCommand::ReconcilerAutoContract { from_tier, to_tier, drift_kind, symbol, side, baseline_qty, current_qty, notes }`，handler 直接呼叫 `governance.risk.de_escalate_to`，**完全繞過** operator manual override 白名單與 step-rule guard（reconciler 不是 operator 動作）。
- [ ] **6-RC-2 V014 event_type 隔離** — 寫入 V014 用 `event_type="reconciler_auto_contract"`（與 `governor_de_escalate` 區隔），讓 B1 `load_governor_cooldown_from_audit` 的 SQL filter 永不會把 reconciler 行誤計入 24h operator cooldown。同步補 SQL filter 的安全網（顯式 `AND payload->>'reason_code' IN (operator_whitelist)`）。
- [ ] **6-RC-3 動作策略** — Major/Orphan/Ghost → step one tier looser；連續 N 個 cycle (≥3) 持續漂移 → 直跳 Defensive；任何 cycle 觀察到 ≥5 個獨立 (symbol,side) 漂移 → 直跳 CircuitBreaker（系統性事件）。
- [ ] **6-RC-4 自身冷卻** — reconciler 自動動作獨立 cooldown：同 (symbol,side) 30 分鐘內不重複 trigger；全局每 5 分鐘最多 1 次自動收縮，避免 REST 抖動或時鐘錯誤造成連續降級。
- [ ] **6-RC-5 絕對 dust floor (per-symbol minQty)** — 從 instrument_info 讀取每個 symbol 的 `lotSizeFilter.minOrderQty`，閾值固定為 `1.5 × minQty`。**禁止**用全局魔法數（0.0001 對 BTC 與 PEPE 的意義截然不同）。低於該值的漂移降級為 MinorDrift 不論百分比，避免 sub-cent residual 觸發風暴。
- [ ] **6-RC-6 多通道告警** — 自動動作前必先發告警（OC-3 多通道告警依賴），讓 operator 有機會在動作生效前介入；告警延遲 15s 後若 operator 未 ACK 才執行動作。**⚠️ 阻塞依賴**：必須先完成 OC-3「長期整合」段的多通道告警基礎設施，否則本項無法落地。Phase 6 排程時 6-RC-6 必須晚於 OC-3。
- [ ] **6-RC-7 整合測試** — 必須有 e2e 測試斷言觸發路徑真的進到 `apply_de_escalation`（非 `_rejected`），覆蓋：單筆 Major 觸發 step looser / 5 筆漂移觸發 CircuitBreaker / 30 分鐘冷卻拒絕重複 / 告警未 ACK 後才動作。
- [ ] **6-RC-8 Live blocker 解除** — 完成上述後，從 Live blocker 清單移除「Bybit REST `/v5/position/list` 必須可達」的隱含依賴項（屆時 reconciler 失敗只代表 audit 缺失，不影響風控）。
- [ ] **6-RC-9 Baseline staleness 政策** — `PositionView` / 對帳器狀態加 `last_fetch_ms` 欄位。若 `now - last_fetch_ms > N 分鐘`（建議 N=10）則下一次成功 REST 走 warmup-reseed 路徑（靜默播種、不分類），避免長時間 REST outage 後 baseline 全面陳舊導致 cycle 1 把所有期間合法變化誤判為一波 drift。**6-RC-1 落地前必須先完成此項**，否則自動動作層會在 REST 恢復時的第一個 cycle 產生大量誤觸發。

**設計原則對齊：**
- 根原則 #5 #6（生存優先 + 失敗默認收縮）：自動收縮恢復後系統真正具備「不確定時自動降風險」能力
- 根原則 #11（Agent 自主權）：reconciler 是系統級觀察員而非 Agent，動作通道與 operator/Agent 路徑完全分離
- 不違反 1C-3 ConfigStore 權威模型：reconciler 不修改任何 config，只觸發 governance state machine 轉換

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
