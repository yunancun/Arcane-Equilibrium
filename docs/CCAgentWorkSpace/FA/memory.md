# FA Memory — 工作記憶

## 項目功能狀態快照（2026-03-31，Wave 5 完成後更新）

```
業務功能真正可用 ≈ 32%（Round 2 冷酷審核基準）→ Wave 5 後 ≈ 55%

逐環節（Wave 5 後）：
  自動掃描 = 95%（ScoutWorker 30 分鐘定時掃描 + Scout→Strategist bus.send 鏈路驗證）
  策略選擇 = 50%（shadow=False + H1-H3 Model Router，但無 Regime-aware + 無回測）
  AI 風險評估 = 75%（H1-H5 全接通，ThoughtGate blocking，但 Regime 分類未完整）
  下單 = 92%（治理 gate + OMS + G-05 Decision Lease 閉環）
  止損 = 95%（Wave 5b：止損同步平 Demo + 對賬引擎首次真正運行）
  學習 = 25%（Perception Plane register_data() 仍零調用 — FA-7 關鍵缺口）
  進化 = 30%（無策略自動優化）
```

## 重要發現記錄

### FA-1 端點角色矩陣（2026-03-31）
- 完成 28 個 governance 端點的角色驗證矩陣
- 發現 2 個 POST 端點缺少 Operator 驗證（已修復為 P2-NEW-7/8）
- **記住**：未來新增 governance 端點必須對照矩陣，狀態改變的 POST 端點必須有 `_require_operator_role()`

### FA-2 reconciliation 邊界值（2026-03-31）
- 發現 3 個 NaN/負數/inf 漏洞（已修復）
- **記住**：任何涉及財務數值計算的代碼，必須在 FA 審查時特別要求 math.isnan/isinf 防護

### FA-3 async/threading 混用（2026-03-31）
- scout_routes.py 5 個 async 路由阻塞 event loop（已修復）
- **記住**：FastAPI async 路由中使用 threading.Lock 的同步方法必須標記為高風險

### H1-H5 斷開（關鍵）
- H1-H5 代碼在 `ai_agents/bybit_thought_gate/` 是獨立腳本，與 app 層完全無連接
- `apply_ai_consultation()` 是純 stub，返回佔位字符串
- **記住**：這是系統最大的業務功能缺口，接通後業務可用度可從 32% 提升到 55%+

## 審計原則記憶

- 審計時不要只看代碼存在與否，要追蹤調用鏈是否真實走通
- 「功能可用」的定義：從 API 觸發，到最終業務結果，中間每一步都有數據流動

## Wave 5 功能驗收結論（2026-03-31 更新）

### B-MVP 逐項結果
- B-MVP-1 Scout→Strategist：✅ 完全通過（5 節點驗證，CC 早期誤判已糾正）
- B-MVP-2 shadow=False：✅ 完全通過（4 個前置條件全部確認後切換）
- B-MVP-3 H1 blocking + Regime：⚠️ 部分通過（ThoughtGate blocking 完成；Regime 分類未完整，以複雜度評分替代）
- B-MVP-4 H 鏈統一入口：✅ 完全通過（apply_ai_consultation 廢棄 + H1-H5 全接通）
- B-MVP-5 Ollama 追蹤：✅ 完全通過（record_ollama_call + get_ollama_stats 已實現）

### 16 條原則更新
- 原則 3（AI輸出≠即時命令）：部分 → **完全合規**（G-05 + H1-H5 接通）
- 原則 10（認知誠實）：部分 → **完全合規**（roi_basis: "paper_simulation_only" 加入所有 ROI API）
- 原則 13（AI資源成本感知）：部分 → **完全合規**（record_ollama_call + cost_edge_ratio 完整）
- 原則 15（多 Agent 協作）：部分 → **完全合規**（Scout→Strategist 鏈路驗證 + ScoutWorker 30 分鐘定時）
- 原則 12（持續進化）：仍未實施（Perception Plane register_data() 零調用，FA-7 關鍵缺口）
- 整體評級：B → 預期 B+/A-

### 功能缺口（Wave 5 後新識別）
- FA-6：H1 缺乏 Regime-aware 過濾（Regime 分類未接入 ThoughtGate，複雜度評分替代品）
- FA-7：Perception Plane register_data() 零調用【最高優先，阻塞學習管線】
- FA-8：cost_edge_ratio GUI 未處理 None（冷啟動顯示問題）
- FA-9：ScoutWorker interval 不可配置（P3 優先）
- FA-10：_ollama_stats 懶初始化，冷啟動可觀察性差
- FA-11（P2 繼承）：executor_agent.py 動態異常字符串
- FA-12：H1 冷卻字典無容量上限

### 業務功能可用度更新
- Wave 4 後：≈ 45%
- Wave 5 後：≈ 55%
- 瓶頸：學習（25%）> Regime-aware 策略選擇（50%） > 進化（30%）

## 2026-04-01 全鏈路功能審計（Phase 3 Batch 3A 後）

### 關鍵發現（必須跨 session 記住）

- **P0-FA-1 TruthSourceRegistry 從未注入到 Agents**：
  `set_truth_registry()` 存在於 StrategistAgent 和 AnalystAgent，但 phase2_strategy_routes.py 中零處調用。
  整個 Phase 2 Batch 2A 的 TruthSourceRegistry 在運行時是完全死代碼。
  **記住**：未來任何新模塊若有 setter 注入方法，必須在啟動 wiring 代碼中驗證是否被調用。

- **MessageBus Guardian→Executor 斷裂**：
  Guardian 發送 RISK_VERDICT 回 Strategist（非 APPROVED_INTENT 給 Executor）。
  ExecutorAgent 的 on_message(APPROVED_INTENT) handler 永遠不被觸發。
  實際下單路徑全走 pipeline_bridge 直接調用。
  **記住**：5-Agent MessageBus 全路徑是設計目標但尚未實現，下單靠 pipeline_bridge 直接調用。

- **BacktestEngine API 無數據源**：
  backtest_routes.py 的 singleton 未注入 KlineManager，API 回測返回空結果。
  **記住**：所有 Phase 2-3 的 routes.py 模塊若依賴外部組件，需在啟動時注入。

### 業務功能可用度更新（2026-04-01）

```
  自動掃描 = 92%
  策略選擇 = 50%
  AI 風險評估 = 78%
  下單 = 88%
  止損 = 93%
  學習 = 40%
  進化 = 35%
  加權平均業務可用度 ≈ 52%
```

### 瓶頸排序
1. 知識閉環斷裂（TruthSourceRegistry 死代碼）→ 0.5h 修復 → 學習+策略各升 10-15%
2. 回測 API 不通 → 1h 修復 → 進化鏈路啟動
3. MessageBus 全路徑不通 → 2h 修復 → Agent 架構完整性

## 報告索引

| 日期 | 報告類型 | 文件位置 |
|------|---------|---------|
| 2026-04-01 | 全鏈路功能 Gap 審計 | workspace/reports/2026-04-01--functional_gap_audit.md |
| 2026-03-31 | FA-1 端點角色矩陣 | ../E3/workspace/ (由 E3 存檔) |
| 2026-03-31 | FA-2/3/4 深度審計 | workspace/reports/2026-03-31--fa_deep_audit.md |
| 2026-03-31 | Wave 5 功能 Gap 分析 | workspace/reports/2026-03-31--wave5_gap_analysis.md |
| 2026-03-31 | Wave 5 功能驗收匯報 | workspace/reports/2026-03-31--wave5_functional_acceptance.md |

## 2026-04-24 全面 Audit 發現（TODO.md 4.24 版本）

### FA-13 PostOnly 配置反向（高優先度）
- **發現**：CLAUDE.md §三 敘述 `demo=true, live=false`，實際配置反向
  - `risk_config_demo.toml:40 post_only_limit = false` ❌
  - `risk_config_live.toml:42 post_only_limit = true` ❌
- **影響**：demo 環境無 PostOnly 費用控制，live 環境反向啟動（違反保守原則）
- **建議**：operator 確認設計意圖並修正 TOML；同時修正 CLAUDE.md 敘述
- **追蹤**：TODO.md 應新增「EDGE-P2-3 PostOnly 配置驗証」P0 項

### FA-14 edge_estimates.json 嚴重不足（高優先度）
- **發現**：`_meta.n_cells=1`（grid_trading::ORDIUSDT），遠低於預期 135-162 cells
  - mtime: 2026-04-20 23:50
  - grand_mean_bps: -45.7（負）— 符合當前 edge 危機狀態
- **根本原因**：edge_estimator_scheduler.py daemon 運行或 labels 累積速度遠不及預期
- **影響**：cost_gate / DL / JS 機械依賴充分邊際數據；1 cell 無法支撐 5 策略決策
- **建議**：
  1. 檢查 edge_estimator_scheduler 是否持續運行（cron/daemon）
  2. 確認 labels 累積進度（P1-7 C 當前 47/200）
  3. 若需加速，考慮人工觸發回填或提高 scheduler frequency
- **追蹤**：與 P1-7 LEARNING-PIPELINE-DORMANT-1 綁定；可能需延後 Phase 5 重評

### FA-15 StrategistAgent/ExecutorAgent 檔案位置異常（中優先度）
- **發現**：CLAUDE.md 敘述位置 `program_code/control_api_v1/app/`，實際位置 `program_code/exchange_connectors/bybit_connector/control_api_v1/app/`
- **影響**：無法驗證 StrategistAgent.shadow=False、ExecutorAgent._shadow_mode=True 預設值
- **根本原因**：DEDUP-PY-RUST Tier B Wave A-D 拆分後位置改變；CLAUDE.md §三 敘述未同步更新
- **建議**：補查新位置、驗證預設值、更新 CLAUDE.md 敘述
- **追蹤**：文檔準確度 P2 項

### FA-16 Track P v2 T4 wiring 無法定位（中優先度）
- **發現**：搜 `physical_micro_profit_lock_v2` 和 `TRACK-P-T4-WIRING` 無定位結果
- **推測**：實現位置可能在 `exit_features/` 或 `tick_pipeline/` 層，但檔案名或函數名異於搜尋項
- **建議**：補查 `grep -r "micro_profit\|phys_lock\|Priority 6" rust/openclaw_engine/src/{exit_features,tick_pipeline,signal_engine}/*.rs`
- **影響**：無法驗證 Priority 6 T4 closure 是否真實接線

### FA-17 INFRA-PREBUILD-1 Part B 函數名確認
- **發現**：`model_registry.py` 430 行（含 tests）；但搜 `resolve_latest_production_artifact` 無結果
- **推測**：函數名可能為 `resolve_latest_production` 或在 OnnxModelManager 內，需補查
- **建議**：補查 `grep -r "latest.*production\|resolve.*artifact" rust/openclaw_engine/src/ml/`

### 完全驗證通過的 6 項
- EDGE-DIAG-1-FUP-IPC（ipc_server/handlers/risk.rs:92-98 全 7 欄位）
- P1-11 FIX-26-DEADLOCK-1（bb_breakout/mod.rs:410-414 auto-clear + saturating_add）
- INFRA-PREBUILD-1 Part A shadow（shadow_exit_writer.rs 存在，dormant 預期）
- INFRA-PREBUILD-1 Part B Guard A（V023 DO block 驗證完整）
- Phase 4 counterfactual cron + [11]（healthcheck 3 態正確）
- engine_watchdog（watchdog.py 3-strike 回滾完整）

### 審計等級調整
- 前期 Wave 5 評級 B → 今日 B（功能實現 70% 完整，文檔準確度 60%）
- 關鍵瓶頸：edge_estimates 充分性 + PostOnly 配置一致性 + 文檔同步
- 下次審計應重點：P1-7 labels 累積進度、TOML 配置驗証、檔案位置對帳

---

## 2026-04-24 全程序鏈審計報告（34 新發現）

**報告位置**：`workspace/reports/2026-04-24--full_chain_audit_report.md`

### 報告索引更新

| 日期 | 報告類型 | 文件位置 |
|------|---------|---------|
| 2026-04-24 | 全程序鏈審計（34 新發現） | workspace/reports/2026-04-24--full_chain_audit_report.md |
| 2026-04-12 | 跨全系統審計 | workspace/reports/2026-04-12--full_chain_audit_report.md |
| 2026-04-03 | Rust 遷移文件覆蓋完整性 | workspace/reports/2026-04-03--rust_migration_file_coverage_audit.md |

### Critical 3 項（最優先，需 P1 回應）

- **FA-2026-04-24-C1 Layer 2 自主推理循環無生產觸發**
  - `Layer2Engine.run_session()` 只在 `layer2_routes.py:210` 有 GUI 手動觸發，無 scheduler/cron/event
  - **記住**：memory `project_layer2_agent_design.md` 的 Layer 2 gap 確認成立；H1-H5 代碼真實（非 stub），Layer 2 自主循環才是真正 gap

- **FA-2026-04-24-C2 ExecutorAgent `_shadow_mode=True` 硬寫死未配置化**
  - `executor_agent.py:482` 類屬性寫死；`ExecutorConfig` 無 shadow_mode 欄位
  - `strategy_wiring.py:468 ExecutorConfig()` 不傳參 → 永遠 shadow
  - 5-Agent 鏈最後一步實際 log-only；真實下單仍走 Rust tick pipeline 直接路徑
  - **記住**：Guardian APPROVE → APPROVED_INTENT bus → ExecutorAgent handler → _execute_via_ipc → `if self._shadow_mode: return shadow report`

- **FA-2026-04-24-C3 Decision Lease 在 Rust 真實交易路徑不存在**
  - Python `governance_hub.acquire_lease()` 實作完整（`governance_hub.py:693`）
  - Rust `intent_processor/` 全目錄 grep `Lease` = 0 命中
  - 唯一生產呼叫點在 `executor_agent.py:342`（受 C2 影響永遠 log-only）
  - **記住**：CLAUDE.md §五 架構圖 `[I Decision Lease]` 在真實交易中 0 觸發；原則 3 在 Rust 側未實現

### High 9 項（重要）

- **FA-H1 PerceptionPlane write-only** — register_data 有 2 處 production 調用（scout_routes.py:387,489），但 validate_for_decision 生產 0 調用
- **FA-H2 H0_GATE Python 實例 0 消費** — `paper_trading_wiring.py:290 H0_GATE=H0Gate()` 創建，但 H0_GATE.方法 grep 0 命中；H0HealthWorker 每 5s 採樣但從不被讀
- **FA-H3 openclaw_core 9/17 模組 engine 0 引用**（~4468 行 Rust 死代碼）：attention / attribution / backtest / cognitive / dream / message_bus / opportunity / order_match / portfolio 都僅 tests 覆蓋
- **FA-H4 6 張 learning 表 0 production INSERT**：rl_transitions / promotion_pipeline / symbol_clusters（完全 0）；cpcv_results / ml_parameter_suggestions / bayesian_posteriors / foundation_model_features（只有 ml_training/*.py 寫，無 scheduler）
- **FA-H5 ML 訓練腳本 silent-unscheduled**：thompson_sampling / optuna_optimizer / cpcv_validator / dl3_foundation / weekly_report_generator — 無 cron / systemd timer / scheduler；只有 test
- **FA-H6** `learning.exit_features.est_net_bps` 100% NULL write-side gap（承襲 P0-15）
- **FA-H7** strategy_auto_deployer IPC 部署路徑斷裂疑問（DEAD-PY-2 後無 bridge）
- **FA-H8** experiment_ledger_snapshot.json 結構異常（承襲 P1-7）
- **FA-H9** H1/H4 未 Regime-aware（承襲 FA-2026-03-31 FA-6）

### 已修閉的 2026-04-01 前輪發現（cross-confirm）

- ✅ **P0-FA-1 TruthSourceRegistry 注入**：已修（`strategy_wiring.py:806,812`）
- ✅ **MessageBus Guardian→Executor 斷裂**：Guardian 發 APPROVED_INTENT 已實作（`guardian_agent.py:456`）；但受 C2 Executor shadow 影響後半鏈仍無實質效果
- ✅ **Perception register_data 零調用**：部分修（scout_routes.py 2 處）
- 🔴 **FA-6 H1 Regime-aware 缺失**：仍未閉環（H9）

### 已驗證為真的 CLAUDE.md / TODO 宣稱（18 項）

WS-RETIRE-1 / INFRA-PREBUILD-1 A+B / EDGE-DIAG-1-FUP-IPC / P0-13 ATR scale / Priority 6 v2 / main_legacy.py 468 行 / 5-Agent 4552 行 / live gates Rust 4 項 / ArcSwap 熱重載 / ScoutWorker 30min 定時 / TruthSourceRegistry 注入 / PipelineBridge 退役 / PAPER-DISABLE-1 / LLM-ABC-MIGRATION-1 / engine lib test count / intent_processor/router.rs Guardian review 真實調用 / apply_ai_consultation deprecated / tick_pipeline/mod.rs 1012 行

### 審計方法論新原則（2026-04-24 記住）

- **「代碼死」（engine 0 引用） ≠ 「運行時 shadow」（代碼存在但 mode=shadow）** — 兩者混淆是常見誤判陷阱。本報告明確區分：(a) H3 openclaw_core 模組 = 真死代碼；(b) ExecutorAgent shadow = 代碼活但生產 log-only。
- **Mac CC session 限制**：無法驗證 Linux runtime 實測資料；DB rowcount / real fill 需 Linux ssh bridge 另做
- **grep 無命中 → 不列為發現**：避免推測誤判（例：先前 memory 曾誤標 H1-H5 全 stub，被 2026-04-23 實證更正）
- **cross-session race**：本輪與前輪 2026-04-24 session（FA-13~17）獨立進行；前輪專注 TOML/邊界資料，本輪專注 full chain wiring；兩輪互補非衝突

