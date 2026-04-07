# OpenClaw TODO — 工作計劃清單

最後更新：2026-04-07（ARCH-RC1 Session 1A+1B+1C-1 完成 · 1C-2 下一步）
測試基準線：**682 engine lib (+58 1B) + 386 core + 30 types + 35 ml_training + 11 control_api smoke** · 0 failures

> compact 後從此文件恢復工作狀態。第一個 `[ ]` 即為下一步起點。

---

## 🎯 ARCH-RC1 統一 Config（2026-04-07 啟動，多 session 工程）

**目標**：將 7 套重疊風控/配置系統統一為 3 個熱重載 Config（Risk/Learning/Budget）+ 既有 StrategyParams。Python RiskManager 1633 → ~150 行 RiskViewClient（純 IPC 讀）。永久契約見 memory/project_arch_rc1_unified_config.md。

- [x] **Session 1A 死代碼清理** — `7f59e9b` (-270 行)
  - 砍 MlConfig + attention_*_ms (5) + EngineConfig + ParamTemperature
  - 0 行為改變 / engine 624 + types 30 全綠
- [x] **Session 1B 統一 Config 骨架** — `0523f17` (+2632 行 / +58 tests)
  - config/store.rs 泛型 ConfigStore<T> + ArcSwap + all-or-nothing patch
  - config/risk_config.rs RiskConfig 13 sub-struct（含跨欄位 invariant）
  - config/learning_config.rs LearningConfig（Phase 4.1 default-off 收編）
  - config/budget_config.rs BudgetConfig（AttentionTax 整塊）
  - engine 624 → 682 / 0 regression
- [x] **Session 1C-1 Rust call site 遷移** — `2007b67` `6768381` `ef30bf1` (3 commits · +747/−1293 淨 −546 行)
  - B0: AntiCluster.max_same_direction 欄位校齊（guardian/IPC/GUI 活體，不可刪）
  - B1: openclaw_core/src/risk 瘦身 — 刪 RiskManagerConfig + checks.rs，拆出 regime.rs
  - B1b: 新建 openclaw_engine/src/risk_checks.rs（502 行 / 16 tests），check_order_allowed + check_position_on_tick 改讀 &RiskConfig + cost_edge 跨 Config 讀
  - B2-4: 5 檔案 call site 遷移 — tick_pipeline / intent_processor / position_risk_evaluator / event_consumer/setup / pipeline_types + tests；所有舊平欄位路徑改 sub-struct
  - B5: RuntimeConfig 刪 8 風控欄位 + 改名 EngineBootstrap + 過渡 deprecated type alias + 驗證邏輯重寫
  - B6: openclaw_types::risk 刪除死代碼（GuardianConfig/StopConfig/composite RiskConfig 全 0 consumer）
  - 測試：engine 682→708 / core 386→387 / types 30→27 · 0 regression
  - 風控並行系統 7→2 套（剩 RiskConfig 權威 + Python RiskManager 待 1C-3 空殼化）
- [ ] **Session 1C-2 IPC 接通 + JSON 遷移**（純加法 · 讓新 Config 真正 live）
  - 6 個 IPC 端點：update_risk_config / update_learning_config / update_budget_config + 對應 get_*
  - bulk patch all-or-nothing + mutex 序列化 + version + source 審計
  - operator_risk_config.json → risk_config.toml 一次性遷移（讀 → v2 schema → 寫 → 改名 .legacy）
  - sql/migrations/V014__engine_events.sql（startup/shutdown/config_patch/reconcile/crash 統一審計）
- [ ] **Session 1C-3 Python 空殼化**
  - risk_view_client.py 新建（~150 行純 IPC 讀）
  - risk_manager.py 1633 → 30 行 deprecation shim
  - 32 個 Python 檔案 import 遷移（13 業務 + 19 測試）
  - risk_routes.py GUI 寫操作改 IPC 轉發
- [ ] **Session 1C-4 收尾**
  - 熱重載驗收測試（tick 跑著改參數 → 下個 tick 生效，無 restart）
  - Position Reconciler（trading.open_positions 表 + Bybit 對帳 + cooldown 重建）
  - NewsPipeline run_once 60s spawn（順手）
  - E2 + E4 + QA Audit + 文檔同步 + commit + push

### 風控執行引擎收編（Phase 2 / 非強制）

**背景**：1C-1 + 1C-2 完成後，**Config 層**從 7 套收到 1 套（RiskConfig 權威），但**執行引擎層**還有 4-5 個並行。Operator 問題：「是否把引擎盡量合併一下更合理？」答：**部分合併合理，不必追求全部合併到 1 個**。下面是建議的拆分：

| 引擎 | 位置 | 獨特性 | 建議 |
|---|---|---|---|
| `risk_checks::check_order_allowed` | `openclaw_engine::risk_checks` | Gate 0 訂單准入 | **保留為主引擎** |
| `risk_checks::check_position_on_tick` | 同上 | tick 持倉 9 項檢查 | **保留** |
| `guardian::Guardian` | `openclaw_core::guardian` | direction_conflict + leverage **modify** verdict（不只是 reject，會 downsize qty/leverage）+ modification_size_factor | **保留**，1C-2-B 已改成從 RiskConfig hot-reload |
| `h0_gate::H0Gate` | `openclaw_core::h0_gate` | 健康檢查（cpu/memory/db_latency/network）+ eligibility | **保留**，但建議把 `max_open_positions` / `max_total_exposure_pct` / `allowed_categories` 三個重複欄位改成 read-through `RiskConfig.limits` |
| `stop_manager::StopManager` | `openclaw_core::stop_manager` | hard/trailing/time stop 邏輯 | **⚠️ 和 risk_checks::check_position_on_tick 功能重疊** — 其中一個應該死。建議：StopManager 廢掉，邏輯全收進 check_position_on_tick（已有對應 check） |
| `risk_governor_sm::RiskGovernorSm` | `openclaw_core::risk_governor_sm` | 6 級級聯狀態機 + hysteresis | **保留**，這是不同架構概念（狀態機 vs 單次檢查），無法合併 |
| Python `risk_manager.py` | program_code/ | 1633 行 GUI 路由 | **1C-3 空殼化**（已列入） |

**具體收編 TODO（不阻塞 1C-2/1C-3，可 Phase 2 做）：**
- [ ] **E-Merge-1**: StopManager 廢棄 — 驗證 risk_checks::check_position_on_tick 已覆蓋 hard/trailing/time stop 全部邏輯，搬出獨特功能（若有），刪除 openclaw_core::stop_manager
- [ ] **E-Merge-2**: H0Gate 欄位去重 — `H0GateConfig` 的 max_open_positions / max_total_exposure_pct / allowed_categories 改成從 RiskConfig.limits read-through（每 check 快照讀），H0GateConfig 只保留健康檢查欄位（cpu/memory/db_latency/network/health_snapshot_max_age）
- [ ] **E-Merge-3**: RiskGovernorSm 確認是否真的讀 RiskConfig.cascade（1B 規劃）還是有自己的 config（grep 驗證）；若否則接進 RiskConfig.cascade
- [ ] **E-Merge-4 (可選)**: Guardian 進一步去 config struct 化 — GuardianConfig 退化為 `RiskConfig.limits + anti_cluster + guardian_modify` sub-view；保留 Guardian 引擎但不再持有 owned struct。收益有限，只有在 Phase 2 清理代碼味時順手做
- **終局**：4-5 套 → **3 套執行引擎**（risk_checks 主引擎 / Guardian P0 modify 引擎 / H0Gate 健康檢查 / RiskGovernorSm 級聯狀態機），全部讀同一個 RiskConfig 真相源

---

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

#### WP-CLEANUP-GRAFANA-TESTS — test_grafana_data_writer.py dead tests（P2）
**現狀**：`b304809 feat: GUI data pipeline` 把 `GrafanaDataWriter` 重構為讀 Rust IPC，
方法名加了 `_from_rust` 後綴（`_write_pnl_from_rust` / `_write_system_health_from_rust`），
但 test 仍引用舊名 `_write_pnl` / `_write_system_health` → 20 個測試 AttributeError。
與 W2 無關，純 pre-existing test debt。

- [ ] 更新 `test_grafana_data_writer.py` 20 個測試對齊新方法名 + Rust IPC mock
- [ ] 或刪除整個 test 檔（writer 已 demo-only，可考慮直接 remove）

#### WP-CLEANUP-WHITELIST-UI — Symbol Whitelist GUI 殘留清理（P2）
**現狀**：T5.04 (35ab853 + f4663d3, 2026-04-01) 已移除 `risk_manager.py` 的 symbol whitelist enforce，
但 GUI 仍有 `tab-governance.html` whitelist card (~160 行) + `governance.js` 3 個 helper (~15 行)。
W2 commit 已將 backend 3 個 endpoints 改為 HTTP 410 Gone stub + GUI card 加 deprecation banner。
完整 UI 移除留待 P2 cleanup sprint。

- [ ] 移除 `tab-governance.html` whitelist card 全部 markup（line ~309-470，含 Add Form / 4 個 category divs / Remove Modal）
- [ ] 移除 `tab-governance.html` JS：`toggleWhitelist` / `loadSymbolWhitelist` / `submitAddWhitelist` / `submitRemoveWhitelist` / `showRemoveWhitelistModal` / `hideRemoveWhitelistModal`
- [ ] 移除 `governance.js` 3 個 helper：`govGetSymbolWhitelist` / `govAddSymbolWhitelist` / `govRemoveSymbolWhitelist`
- [ ] 移除 `governance_routes.py` 3 個 410 stub + `SymbolWhitelistAddRequest` Pydantic class（W2 留作過渡期）
- [ ] 跑全套 pytest + manual GUI smoke

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

## Phase 4 — Claude Teacher + LinUCB + News + DL-3（✅ CODE-COMPLETE 2026-04-07）

> ★★★★ **22/22 子任務全部 committed**（4-00 ~ 4-21） · commit range `945f4ad..435930f`
> 4-21 多角色 audit **CONDITIONAL APPROVE** (E2/E4/E5/QA/PM approve · AI-E conditional pending 4.1)
> 審計報告：`docs/audits/2026-04-07_phase4_final_signoff_audit.md`
> 執行計劃：`docs/references/2026-04-06--phase4_execution_plan_v2.md`
> 測試：engine lib **441 → 589 (+148)** · phase4_integration 3/3 · phase4 routes 24→29 · 0 regression

**Group 0 — Dashboard 骨架**
- [x] **4-00** Phase 4 Dashboard tab + `_dashboard_card.html` + `get_phase4_status` IPC stub — `d36116f`

**Group 1 — Claude Teacher**
- [x] **4-01** Teacher directive Rust 接口 + ExperimentLedger — `31fb227`
- [x] **4-02** Directive applier + GovernanceHub veto + P0/P1 denylist (15 tests，ARCH-RC1 sentinel) — `996a0cb`
- [x] **4-03** directive_executions outcome tracker + V012 + backfill + Teacher Card — `b16335f`

**Group 2 — LinUCB**
- [x] **4-04** LinUCB Rust inference + arm space v1_15 + versioned state + feature_schema_hash fail-closed — `31fb227`
- [x] **4-05** LinUCB Python trainer + 收斂監控 + BYTEA codec cross-language pin `sha256:07fe5f19cb66a0af` — `996a0cb`
- [x] **4-06** LinUCB warm-start migration (hierarchical §1.3.3 公式) + shadow compare + auto regret rollback + Card — `b16335f`

**Group 3 — News**
- [x] **4-07** News provider abstract + CryptoPanic free + RSS + mock — `31fb227`
- [x] **4-08** Headline dedup (SHA1[:16]+24h) + severity (keyword × source) + pipeline — `996a0cb`
- [x] **4-09** NewsRouter triple-route (Guardian/Regime/Learning) — `b16335f`
- [x] **4-10** News Card + provider quota 健康監控 — `122239b`

**Group 4 — DL-3 Foundation Models**
- [x] **4-11** TimesFM/Chronos async wrapper + foundation_model_features 表 (V011) — `31fb227`
- [x] **4-12** DL-3 A/B 框架 + decision matrix + fail-soft — `996a0cb`
- [x] **4-13** DL-3 Go/No-Go report generator + CLI wrapper — `b16335f`
- [x] **4-14** DL-3 Card + 決策展示 — `122239b`

**Group 5 — Cross-cutting**
- [x] **4-15** AI Budget tracker (Rust) + V010 + IPC + 三段降級 — `b4cfade`
- [x] **4-16** AI Budget GUI Risk-tab 區塊 + ARCH-RC1 reference path — `996a0cb`
- [x] **4-17** Provider pricing table 綁定 (`settings/ai_pricing.yaml`) — `31fb227`
- [x] **4-18** DecisionContextMsg +5 Phase 4 columns + INSERT SQL extended — `122239b`
- [x] **4-19** test_full_learning_loop 集成測試（3 e2e cases）— `4a5ef41`

**Group 6 — 週報 + 簽收**
- [x] **4-20** 週報 plain-English generator + V013 + operator approval flow — `435930f`
- [x] **4-21** 多角色 final sign-off audit (E2/E4/E5/AI-E/QA/PM) — CONDITIONAL APPROVE · audit doc committed

**W4 wiring sweep** — `435930f`
- [x] **W-1** GovernanceCoreWrapper + PaperSessionCommandSink production impls
- [x] **W-2** GuardianHaltCheckImpl + LearningContextSinkImpl + NewsContextSnapshot (shared halted atomic)
- [x] **W-3** LinUcbRuntime + intent_processor + tick_pipeline decision_context producer wiring
- [x] **W-4** DecisionContextMsg news_severity + hours_since_last_major_news populator
- [x] **main.rs Arc 構造** + EventConsumerDeps +2 fields (linucb_runtime, news_snapshot) + live boot log 驗證

### Phase 4 Live 前 blocker（P0）
- [x] **E3 Security Audit R6** — `docs/audits/2026-04-07_e3_r6_directive_applier_security_audit.md` CONDITIONAL GO，3 P1 minor 全部關閉（5 test cases + 2 doc comments，commit 後續）
- [x] **Phase 4.1 Claude API Consumer Loop** — `claude_teacher/consumer_loop.rs` (+480 行 / 10 tests) + `mod.rs::fetch_parse_persist` + `main.rs` Arc 接線 + IPC `set_teacher_loop_enabled` / `get_teacher_loop_status`（fail-soft uninitialized）— commit `ee6fd00` · **default-off**，operator IPC flip 即可上線
- [ ] **7+ days paper trading 數據累積** — DoD A/C/E metric 觀察期（calendar-time，唯一剩餘 blocker）

### Phase 4 P1/P2 follow-up（非 blocker）
- [ ] **4-06 LinUCB live warm-start deployment** — script 已交付，等第一次真實 v1→v2 遷移時觸發
- [ ] **tick_pipeline.rs refactor (partial)** — 2211 → **2117** 後仍超 §九 1200 行硬上限 917 行。已抽出 `decision_context_producer` (`e7ca473`) + `position_risk_evaluator` (`aecea27`)。剩餘 on_tick 區塊（Step 0/0.5/1/4+5/dispatch loop/exchange-confirmed-fill）重度 `&mut self`，留專屬 session 處理 borrow checker 協商
- [x] **DirectiveApplier main.rs 構造** — 隨 4.1 loop 一併接線（commit `ee6fd00`）
- [ ] **NewsPipeline periodic run_once task spawn** — provider 已交付但無 scheduler loop

殘留延後（前 phase 帶過來，非阻塞）：
- [ ] 2-11 actual training（需引擎運行收集 `trading.fills`）
- [ ] 2-PYO3-1 ContextDistiller PyO3 接入
- [ ] ort crate activation（首個 ONNX 模型訓練後一行啟用）
- [ ] 3b-07 BH-FDR 多重比較校正
- [ ] 3b-08 Grid 多目標 Pareto

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
