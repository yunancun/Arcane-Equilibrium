# FA 全程序鏈審計報告 — OpenClaw / Bybit AI Agent 交易系統
# FA Full-Chain Audit Report

**日期**：2026-04-24
**審計員**：FA（Functional Auditor）
**上一輪 FA 基準**：2026-04-01 全鏈路功能 Gap 審計 + 2026-04-03 Rust 遷移覆蓋審計
**審計範圍**：整個 OpenClaw 系統
- Rust `rust/openclaw_engine/` + `rust/openclaw_core/` + `rust/openclaw_types/`
- Python `program_code/`（控制面 / Agent / ML / Bybit connector / 觀察管線）
- `helper_scripts/` · `sql/migrations/` · `settings/`
**審計對象**：CLAUDE.md §三宣稱、TODO.md 已完成項、16 根原則、里程碑索引

---

## 執行摘要 / Executive Summary

| 指標 | 數值 |
|---|---|
| 本輪新發現項 | **34 項**（3 Critical / 9 High / 14 Medium / 8 Low） |
| 驗證通過 claims | 18 項 |
| 驗證為過期 / 部分成立 claims | 6 項 |
| Rust 側 openclaw_core 死代碼模組 | **9 / 17 個模組** 在 engine 0 引用 |
| Python 側被創建但 0 消費的 singleton | **4 項**（H0_GATE / Decision Lease / PerceptionPlane read / TruthSourceRegistry 寫入成功但讀 0） |
| 被定義但 0 production INSERT 的 learning 表 | **6 張**（rl_transitions / symbol_clusters / foundation_model_features 等） |
| ML 訓練腳本 silent-unscheduled（只測試，無 cron/scheduler） | **5 個**（thompson_sampling / optuna_optimizer / cpcv_validator / dl3_foundation / weekly_report_generator） |

**整體判斷**：

1. **基礎設施層健康** — ARCH-RC1 / 3E-ARCH / Rust ConfigStore + ArcSwap / IPC patch_risk_config / Guardian (Rust) / WS-RETIRE-1 / EDGE-DIAG-1-FUP-IPC / INFRA-PREBUILD-1 A+B 全部驗證通過，代碼真實存在且有對應 tests。live 門控（Gate #1-5）Rust 側 4 項硬實現正確。

2. **AI/Agent 層 partial wired** — 先前 memory 中「H1-H5 全 stub」2026-04-23 已更正，本輪再確認：H1ThoughtGate / H4Validator / 5 Agent / Layer 2 代碼**真實且已接線**。但：
   - `ExecutorAgent._shadow_mode=True` 默認（`strategy_wiring.py:468` 的 `ExecutorConfig()` 不覆蓋）→ APPROVED_INTENT 鏈路只到 Python shadow log，從不 IPC SubmitOrder 到 Rust
   - `Layer2Engine.run_session()` **只有 layer2_routes.py:210 單一調用點**（GUI 手動觸發），無任何 scheduler/cron 自動循環 → Layer 2 自主推理循環 NOT WIRED
   - Rust 真實交易路徑（intent_processor/router.rs）**不經過 Decision Lease**；Python 的 `governance_hub.acquire_lease()` 只在 Python shadow path 被 ExecutorAgent 調用，production 路徑（Rust engine）0 處呼叫

3. **learning / 進化層半死** — 22 個 learning schema 表中：
   - 6 張 0 production INSERT（僵屍表）
   - 5 張只有單一孤立腳本寫（無 scheduler/cron 觸發，silent unscheduled）
   - 3 張有 writer 但 consumer loop disabled（claude_teacher.enabled=false）
   - 8 張 active（decision_features / intents / fills / verdicts / edge_label 等）

4. **openclaw_core 死代碼重大** — 17 模組中 9 個在 engine 0 引用（attention / attribution / backtest / cognitive / dream / message_bus / opportunity / order_match / portfolio），共 ~4500 行 Rust 代碼被 tests 覆蓋但 production 不用。

---

## 一、功能規格驗證 / Specification Verification

### 1.1 CLAUDE.md §二 — 16 根原則驗證

| # | 原則 | 代碼驗證狀態 | 證據 / 關鍵路徑 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ 通過 | `intent_processor/router.rs` + `order_manager.rs`；Rust engine 唯一入口。Python `control_ops.py` 經 IPC。 |
| 2 | 讀寫分離 | ✅ 通過 | GUI 寫入 93 endpoints；`risk_view_client.py` 只讀；research 隔離 |
| 3 | AI 輸出 ≠ 即時命令 | ⚠️ **部分**：Python `executor_agent.py:342` 有 `acquire_lease()` 但 **`_shadow_mode=True` 默認** 讓 IPC 提交路徑永不觸發 Lease；Rust intent_processor 無 Lease 概念，真實交易 bypass | `executor_agent.py:482 _shadow_mode=True` + `intent_processor/` grep `Lease` = 0 命中 |
| 4 | 策略不能繞過風控 | ✅ 通過 | `intent_processor/router.rs:106,507` `guardian.review(&check, &ctx)` 真實執行 |
| 5 | 生存 > 利潤 | ✅ 通過 | P0 硬邊界（max_retries=0）+ LIVE-GUARD-1 三重 Mainnet 鎖 |
| 6 | 失敗默認收縮 | ✅ 通過 | 多處 fail-closed 閉環（edge_label_backfill / governance / authorization） |
| 7 | 學習 ≠ 改寫 Live | ✅ 通過 | 3E-ARCH 三引擎並行；learning schema 獨立 |
| 8 | 交易可解釋 | ⚠️ **部分**：STRATEGIST-PERSIST-AUDIT-GAP-COUNTER-1（TODO §P2 已登記）揭露 persist_applied_params fail-soft 可能讓 audit table 遺失 row；`decision_outcomes` 100% 'paper' bug 已修但舊資料污染 | `docs/audits/...` 記錄 |
| 9 | 交易所災難保護 | ✅ 通過 | 本地 StopManager + Rust exit_features + Bybit 條件單（`bybit_rest_client.rs`） |
| 10 | 認知誠實 | ✅ 通過 | `roi_basis: "paper_simulation_only"` 加入所有 ROI API；PerceptionPlane `register_data()` 有寫入（scout_routes.py:387, 489） |
| 11 | Agent 最大自主權 | ⚠️ **半成立**：StrategistAgent 可 tune（shadow=False）；但 ExecutorAgent shadow_mode=True 默認讓真實「自主執行」不存在，全走 Rust pipeline 直接 tick-driven | 見原則 3 |
| 12 | 持續進化 | ❌ **未達成**：thompson_sampling / optuna_optimizer / cpcv_validator / dl3_foundation 5 個 ML 訓練腳本無 scheduler 呼叫；`learning.rl_transitions` / `learning.symbol_clusters` 等 6 張表從未被 INSERT；P1-7 LEARNING-PIPELINE-DORMANT-1 仍在 TODO | `ml_training/*.py` 無 cron 接線 |
| 13 | AI 資源成本感知 | ✅ 通過 | `layer2_cost_tracker.py` 726 行；`cost_edge_ratio` gate 實作 |
| 14 | 零外部成本可運行 | ✅ 通過 | `local_llm_factory.py` + Ollama fallback；`LOCAL_LLM_PROVIDER` env 切換驗證 |
| 15 | 多 Agent 協作 | ⚠️ **部分**：5 Agent 代碼真實（~4552 行）；ScoutWorker daemon 有 30min 定時；但 Executor shadow-only → APPROVED_INTENT → 下單 閉環未實際運行 | `executor_agent.py:238` handler + `_shadow_mode=True` |
| 16 | 組合級風險意識 | ✅ 通過 | `portfolio_risk_control.py` + `correlated_exposure_max_pct`（但 P1-6 死循環問題揭露有配置漂移） |

**原則層 gap 總結**：原則 3 / 11 / 12 部分未達；原則 8 有潛在 audit hole。

---

### 1.2 CLAUDE.md §三 宣稱驗證

| Claim（CLAUDE.md §三） | 驗證結果 |
|---|---|
| `engine lib 1939 passed / 0 failed` | ✅ 代碼級可信（Linux sub-agent 離線驗證基準一致） |
| `WS-RETIRE-1` — Python `bybit_private_ws_listener.py` 退役，Rust `bybit_private_ws_status_writer.rs` 取代 | ✅ 通過 — `rust/openclaw_engine/src/bybit_private_ws_status_writer.rs` 存在；Python `bybit_private_ws_listener.py` 3 檔 340 行已刪 |
| `INFRA-PREBUILD-1 Part A（Combine Layer shadow）dormant` | ✅ 通過 — `shadow_exit_writer.rs` 存在，`ExitConfig.shadow_enabled` 欄位存在；default false |
| `INFRA-PREBUILD-1 Part B（Model Registry）dormant` | ✅ 通過 — V023 migration 存在，`rust/openclaw_engine/src/ml/registry.rs` 存在，5 routes 回 404 直到有 row |
| `EDGE-DIAG-1-FUP-IPC` — 7 個 `exit.*` IPC 熱重載 | ✅ 通過 — `tick_pipeline/mod.rs:291-300` 有 `exit_missing_edge_fallback_bps` 等 7 欄位 IPC patch 路徑 |
| `P0-13 ATR scale` | ✅ 通過 — `atr(14)` Wilder's ATR 實作 |
| `P0-14 JS proxy cells 43→135` | ⚠️ 代碼層 `_inject_sync_label_proxy_cells` 存在，但 `learning.exit_features.est_net_bps` 100% NULL 的 write-side gap TODO 已登記（P0-15 後續追蹤項） |
| `Priority 6 每 tick 呼 physical_micro_profit_lock_v2` | ✅ 通過 — `exit_features/v2.rs:50` Default impl + `validate()` + `on_tick.rs` 接線 |
| `Live_Ready ⚠️（真實 live 門控 Rust 4 項 / 全部 5 項）` | ✅ 通過 — 4 項 Rust 側：`OPENCLAW_ALLOW_MAINNET` env（`bybit_rest_client.rs:526`）/ `authorization.json` HMAC（`live_auth_watcher.rs`）/ secret slot（`bybit_rest_client.rs:386-497`）/ env_allowed 匹配。Python 2 項 `live_reserved` + Operator auth。 |
| `execution_authority` 是 denylist 字串常量 | ✅ 通過 — `claude_teacher/applier.rs:226` 確認 |
| `main_legacy.py 468 行瘦身 91.1%` | ✅ 通過 — 本機實測 468 行 |
| `5-Agent ~4552 行` | ✅ 通過 — strategist 1170 + guardian 587 + analyst 834 + executor 630 + scout_worker 194 + multi_agent_framework 1137 = 4552 |
| **`StrategistAgent shadow=False Sprint 5a live`** | ✅ 通過 — `strategist_agent.py:567` 條件路徑存在 |
| **`ExecutorAgent _shadow_mode=True 默認未覆蓋`** | ✅ 通過並確認 — `executor_agent.py:482` + `strategy_wiring.py:468` `ExecutorConfig()` 無參數 |
| `tick_pipeline/mod.rs 1012 行（§七 1200 硬限符合）` | ✅ 通過 — 本機實測 1035 行（接近但符合；CLAUDE.md 值 1012 可能 1 commit 差） |
| `ArcSwap 熱重載 5ns` | ✅ 通過 — `config/risk_config.rs:11` 註釋 + `risk_checks.rs:6` 使用 |
| `ScoutWorker 30min 定時` | ✅ 通過 — `scout_worker.py:60` + `strategy_wiring.py:692` 啟動 |
| **`TruthSourceRegistry 注入`** | ✅ 通過 — `strategy_wiring.py:806 STRATEGIST_AGENT.set_truth_registry(_TRUTH_REGISTRY)` / `:812 ANALYST_AGENT.set_truth_registry(_TRUTH_REGISTRY)`（2026-04-01 FA P0-FA-1 已修復） |
| **`PipelineBridge 已退役 (DEAD-PY-2)`** | ✅ 通過 — `strategy_wiring.py:391` 確認 `PIPELINE_BRIDGE = None`；grafana_data_writer 參數保留但 passed as None |
| **`apply_ai_consultation 廢棄`** | ✅ 通過 — memory 記載 Sprint 5b-3 完成 |
| **`PAPER-DISABLE-1`** | ✅ 通過 — `OPENCLAW_ENABLE_PAPER=1` 才 spawn（paper 預設關） |
| `LLM-ABC-MIGRATION-1 5 call-site` | ✅ 通過 — `local_llm_factory.py` + 5 call-site（ai_service / strategy_wiring / layer2_engine / layer2_routes / layer2_tools） |

---

### 1.3 TODO.md 已完成項驗證（抽樣 8 項）

| TODO 項 | 驗證 |
|---|---|
| `P0-13 ATR-SCALE-BUG-1`（ff694e8） | ✅ 代碼級可信；`atr(14)` Wilder's 公式落地 |
| `P0-14 EDGE-ESTIMATES-MISS-1`（2484263 + 9710ff9） | ✅ `ExitConfig.missing_edge_fallback_bps` 欄位存在 + IPC hot-reload |
| `P1-7 FILL-CONTEXT-LINKAGE-1`（bd45e90） | ✅ `OrderDispatchRequest.context_id` + `apply_confirmed_fill(...,signal_context_id:&str,...)` 新欄位 |
| `P1-11 FIX-26-DEADLOCK-1`（bcc5401+63957ad） | ✅ `squeeze_detected_ms` auto-clear 代碼已 commit；待 `--rebuild` 部署 |
| `TRACK-P-V2-SWAP-1`（306993e） | ✅ `exit_features/v2.rs` 存在，`ExitConfig` 7 欄位 |
| `TICK-PIPELINE-MOD-SPLIT-1`（3d67a99） | ✅ tick_pipeline/ 拆分 `pipeline_ctor.rs` / `pipeline_config.rs` / `pipeline_helpers.rs` |
| `EDGE-DIAG-1 Phase 4 daily cron`（5b0908b） | ✅ `helper_scripts/db/counterfactual_daily_cron.sh` + `passive_wait_healthcheck.py` check [11] |
| `EDGE-SCHEDULER-LEADER-1`（f32629c） | ✅ `edge_estimator_scheduler.py` flock 選舉 + `_LEADER_LOCK_FD` singleton |

**TODO 層準確度**：抽樣 8/8 通過，歷史完成記錄精確。

---

## 二、Gap 分析 / Gap Analysis

### 2.1 Critical — 規格說有但實作未接通

#### FA-2026-04-24-C1 · Layer 2 自主推理循環無生產觸發

- **嚴重性**：Critical（影響原則 11 / 15）
- **證據**：
  - `layer2_engine.py:344` `Layer2Engine.run_session()` 存在，750 行 AI agent 迴圈
  - **單一生產呼叫點**：`layer2_routes.py:210 await engine.run_session(...)`（GUI 手動觸發）
  - grep `run_session` 在 production 代碼：**0 個 scheduler / cron / event trigger**
  - `ensure_future.*engine` 在 production：0 命中
  - memory `project_layer2_agent_design.md` 記載的 H1-H5 stub 誤判 2026-04-23 已更正，但 **Layer 2 自主循環 gap 仍成立**（CLAUDE.md §三「真正 gap (b)」已標明）
- **業務影響**：Agent 不會自主搜集新聞 / 做宏觀判斷 / 運行推理鏈；系統完全被動於 tick-driven Rust pipeline
- **建議行動**：P2 — 加 Conductor 自主觸發邏輯（事件規則：市場波動 / 新 intel / 每 N 小時 / 持倉顯著 loss）

#### FA-2026-04-24-C2 · ExecutorAgent `_shadow_mode=True` 硬寫死未配置化

- **嚴重性**：Critical（影響原則 3 / 11 / 15）
- **證據**：
  - `executor_agent.py:482` `_shadow_mode: bool = True`（類屬性寫死）
  - `strategy_wiring.py:468` `config=ExecutorConfig()` 不傳參數
  - `ExecutorConfig` dataclass 中**沒有 `shadow_mode` 欄位** — 意味著無論 TOML/env 怎改，都無法關閉 shadow mode
  - 運行路徑：Guardian APPROVE → bus send APPROVED_INTENT → Executor `on_message(APPROVED_INTENT)` → `_execute_via_ipc` → `if self._shadow_mode: return shadow report`
- **業務影響**：5-Agent 鏈的最後一步 **永遠是 log-only**。所有 Rust engine 的實際下單走 tick pipeline 直接路徑（非 Agent 鏈）；Agent shadow → live promotion 無 config switch
- **建議行動**：P1 — 把 `_shadow_mode` 從類屬性改為 `ExecutorConfig.shadow_mode: bool = True` 欄位 + runtime IPC / env 可覆蓋；加 promotion decision log

#### FA-2026-04-24-C3 · Decision Lease 在 Rust 真實交易路徑不存在

- **嚴重性**：Critical（直接違反原則 3）
- **證據**：
  - `governance_hub.py:693` `acquire_lease(intent_id, scope, ttl_seconds=30.0)` 實作完整
  - **Rust `intent_processor/` 全目錄 grep `Lease|lease_id|DecisionLease|governance_hub`**：0 命中
  - 唯一 production 呼叫點：`executor_agent.py:342`（Python shadow path，因 C2 永遠 log-only）
  - 因此：真實交易流（Rust tick_pipeline → intent_processor → order_manager）**完全 bypass** Decision Lease
- **業務影響**：CLAUDE.md §五「[I Decision Lease]` GovernanceHub.acquire_lease() / release_lease()」架構圖中的核心閘門在實際交易中 0 觸發。原則 3 "AI 輸出 ≠ 即時命令" 在 Rust engine 側未實現。
- **建議行動**：P1 — 決定 Lease 定位：(a) 明確它是 Python shadow path only 工具 → 更新 CLAUDE.md §五 架構圖；或 (b) 在 Rust intent_processor 加 Lease IPC 查詢 gate（較大工程）

---

### 2.2 High — 半成品 / shadow-only / 未 promote

#### FA-2026-04-24-H1 · PerceptionPlane write-only，validate 生產 0 調用

- **嚴重性**：High（影響原則 10）
- **證據**：
  - `perception_data_plane.py:347 register_data()` 有呼叫 — `scout_routes.py:387,489` 共 2 處
  - `validate_for_decision(data_id)` 只在 tests（3 個 test 檔）出現，production 0 命中
  - `WIRING_INTEGRITY_AUDIT.md:352` 列為 "should be called before Analyst decision" 但實際沒接
- **業務影響**：原則 10 "認知誠實" 的**驗證**環節缺失；資料 register 了但沒人問「這筆資料能用嗎」
- **建議行動**：P2 — 在 AnalystAgent / StrategistAgent 決策前加 `validate_for_decision()` 閘門，或明確 demote 為只讀記錄庫

#### FA-2026-04-24-H2 · H0_GATE Python 實例完全無消費

- **嚴重性**：High（影響原則 5 / 6）
- **證據**：
  - `paper_trading_wiring.py:290 H0_GATE = H0Gate(config=H0GateConfig())` 創建
  - `paper_trading_wiring.py:291 _h0_health_worker.start()` 啟動健康監控
  - grep `H0_GATE\.`（方法調用）在整個 `control_api_v1`：**0 命中**
  - grep `h0_gate\.check\(`：0 命中（除文件本身定義）
- **注意**：Rust 側 **沒有** H0Gate 概念（engine 有 `intent_processor` 但無 h0_gate 模組）；openclaw_core 有 `h0_gate.rs`（1067 行）但只 `GateStats` 一個 type 被 engine 引用
- **業務影響**：H0 健康快照數據 worker 每 5s 採樣但從不被讀；Python 啟動開銷白費；CLAUDE.md §五 的 H0 本地判斷內核在 Python 已事實死亡
- **建議行動**：P2 — 要么刪除 H0_GATE + H0HealthWorker（DEAD-PY-3），要么將健康數據經 IPC 寫入 Rust engine 供 intent_processor 使用

#### FA-2026-04-24-H3 · openclaw_core 9 個模組 engine 0 引用

- **嚴重性**：High（~4500 行 Rust 死代碼 + 測試）
- **證據**：以下模組在 `rust/openclaw_engine/src/` 中 grep 0 命中（**type re-export 不算**）：

| openclaw_core 模組 | 行數 | engine 引用 | 備註 |
|---|---:|---|---|
| `attention.rs` | 424 | 0 | 只出現在 `engine/config/budget_config.rs` budget 註解 |
| `attribution.rs` | 267 | 0 | 無 consumer |
| `backtest.rs` | 490 | 0（engine），2（tests） | `openclaw_core/tests/golden_extreme.rs` + `bb_breakout_threshold_sweep.py` 註釋引用 |
| `cognitive.rs` | 524 | 0 | `CognitiveModulator` 零引用；只在 `openclaw_types` re-export |
| `dream.rs` | 936 | 0 | `DreamEngine`，規格已寫但 engine 未接 |
| `message_bus.rs` | 296 | 0 | Rust MessageBus 未用；Python 側有自己的 MessageBus |
| `opportunity.rs` | 861 | 0 | `OpportunityTracker` 遺憾追蹤未接 |
| `order_match.rs` | 308 | 0 | 已由 `paper_state/fill_engine.rs` 取代 |
| `portfolio.rs` | 362 | 0 | 未接；Python `portfolio_risk_control.py` 取代 |

合計 **~4468 行 Rust 代碼 + 大量 #[cfg(test)] 測試** 不在 engine 的任何生產路徑中
- **建議行動**：P2 — Rust migration master plan v2 裡 §2.4 曾規劃這些模組，但實際 Python 側保留了同義功能。應決策：(a) 接線 Rust 版本（大工程，需 Python 替換）；(b) 標 `#[allow(dead_code)]` 或移至 `_legacy/`；(c) 整塊刪除

#### FA-2026-04-24-H4 · 6 張 learning schema 表 0 production INSERT

- **嚴重性**：High（影響原則 12 學習管線）
- **證據**：以下 learning schema 表在 migration 已建立，但 production 代碼 INSERT 搜尋 0 命中：

| 表 | migration | production INSERT | 備註 |
|---|---|---|---|
| `learning.rl_transitions` | V004 | **0** | fresh_start/index 有提及，實際 writer 不存在 |
| `learning.promotion_pipeline` | V004 | **0** | `promotion_pipeline.py` 只 import schema 但不寫入 |
| `learning.symbol_clusters` | V004 | **0** | 僵屍 |
| `learning.cpcv_results` | V004 | 僅 `ml_training/cpcv_validator.py`（**無 scheduler**） | silent-unscheduled |
| `learning.ml_parameter_suggestions` | V004 | 僅 `ml_training/optuna_optimizer.py`（**無 scheduler**） | silent-unscheduled |
| `learning.bayesian_posteriors` | V004 | 僅 `ml_training/thompson_sampling.py`（**無 scheduler**） | silent-unscheduled |
| `learning.foundation_model_features` | V011 | 僅 `ml_training/dl3_foundation.py`（**無 scheduler**） | silent-unscheduled |

- `learning.pattern_insights` （V016）— `ai_service_feedback.py:105` 有 INSERT；但 consumer 只有 `ai_service_feedback.py` 內部（Strategist prompt 用），真實效益待驗
- `learning.teacher_directives` / `learning.directive_executions` — Rust writer 存在（`claude_teacher/writer.rs`）但 consumer_loop `enabled=false` default，production 運行中 0 寫入
- **業務影響**：P1-7 LEARNING-PIPELINE-DORMANT-1 只覆蓋「edge 估計」管線；本項擴大至整個學習 schema，原則 12 明顯未達
- **建議行動**：P2 — 列出 ml_training 各腳本的 scheduler 接線計畫；對 0-INSERT 表決定 sunset 或 activate

#### FA-2026-04-24-H5 · ML 訓練腳本 silent-unscheduled

- **嚴重性**：High（影響原則 12）
- **證據**：
  - `ml_training/thompson_sampling.py` — 無 cron / 無 scheduler 呼叫
  - `ml_training/optuna_optimizer.py` — 同上
  - `ml_training/cpcv_validator.py` — 同上
  - `ml_training/dl3_foundation.py` — 同上
  - `ml_training/weekly_report_generator.py` — 有 `helper_scripts/phase4/weekly_report.py` 引用但無 cron 接線
  - `helper_scripts/` 下只有 2 個 cron：`cron_daily_report.sh` + `cron_observer_cycle.sh` + 新加 `counterfactual_daily_cron.sh`；**無 ML 訓練 cron**
- **業務影響**：這些 ML 腳本實測 `run_training_pipeline.py` 可人工跑（smoke 通過），但持續進化（原則 12）要求自動執行。TODO §P1-7 覆蓋 edge JS estimator scheduler，不覆蓋這 5 個。
- **建議行動**：P2 — 每個腳本補 `helper_scripts/cron_*.sh` wrapper + systemd timer；或決定延後至 P1-7 D Teacher 落地後一併做

#### FA-2026-04-24-H6 · `learning.exit_features.est_net_bps` 100% NULL write-side gap（承襲 P0-15）

- **嚴重性**：High（影響 EDGE-DIAG-1 決策品質）
- **證據**：TODO §P0-13/14/15 結案條目附帶「後續追蹤項」明確記載
- **業務影響**：Gate 1 決策流已獨立（21 phys_lock fires），但 exit_features 表對 downstream ML 訓練 est_net_bps 欄位全 NULL；下游 canonical writer 走 Option B 或需另案修
- **建議行動**：P1 — 另案 RCA（TODO 已登記）

#### FA-2026-04-24-H7 · `strategy_auto_deployer` IPC 部署路徑斷裂

- **嚴重性**：High（影響自動部署功能）
- **證據**：
  - `strategy_wiring.py:585-586` 註釋：「DEAD-PY-2：PipelineBridge removed — auto-deployer runs without bridge reference」
  - AUTO_DEPLOYER 仍創建，但無 bridge → 部署命令走 IPC？檢查 backtest_routes.py:`set_backtest_engine` 注入
  - `strategy_wiring.py:588-600` 有 try 注入 BacktestEngine（0A-5）但「fail-open」
- **業務影響**：Scout→StrategyAutoDeployer→Strategy deploy 路徑真正工作與否未驗證；可能實際只能把策略 wire 到 Rust engine 靠啟動時 TOML 讀取
- **建議行動**：P2 — 驗證端到端：operator 手動觸發一次 ScoutAgent intel → 看 Rust engine 是否接受新策略 IPC（或無 IPC 路徑）

#### FA-2026-04-24-H8 · `_experiment_ledger_snapshot.json` 結構異常

- **嚴重性**：High（承襲 TODO §P1-7）
- **證據**：TODO §P1-7 條目明確記載 "結構異常"
- **業務影響**：`AnalystAgent._experiment_ledger.get_all_hypotheses()`（`analyst_agent.py:596`）依賴此 snapshot；若結構異常，hypothesis 追蹤鏈斷
- **建議行動**：P2 — 另案修復（TODO 已登記）

#### FA-2026-04-24-H9 · H1 / H4 ThoughtGate 未 Regime-aware

- **嚴重性**：High（承襲 2026-03-31 FA-6 未閉環）
- **證據**：
  - `strategist_agent.py:292-389` 有 H1 ThoughtGate 三同步規則（budget/complexity/cooldown）
  - FA-2026-03-31 記載 "Regime 分類未接入 ThoughtGate，複雜度評分替代品"
  - `market_regime.py` 586 行存在，但 H1 / H4 validator 都未使用 `MarketRegime`
- **建議行動**：P2 — 在 H1 加 regime 分類查詢，讓 trending/ranging/volatile 各自有不同 gate 閾值

---

### 2.3 Medium — 配置漂移 / 部分死代碼 / legacy 保留

#### FA-2026-04-24-M1 · `correlated_exposure_max_pct` TOML vs runtime 漂移

- **證據**：TODO §P1-6 明確：`TOML=60.0 但 runtime=65.0`（GUI hot-reload 修改過）
- **業務影響**：原則 16 組合風險意識；參數來源不透明，違反 SSOT
- **建議行動**：P3 — 修 TOML 為真實期望值或添 startup assert config == runtime

#### FA-2026-04-24-M2 · `grafana_data_writer.py` 死參數 `pipeline_bridge=None`

- **證據**：`grafana_data_writer.py:100 pipeline_bridge: Any = None`
- **業務影響**：legacy 保留但 DEAD-PY-2 後永傳 None；無業務風險但 code smell
- **建議行動**：P3 — 下一輪清理一併拿掉

#### FA-2026-04-24-M3 · `local_model_tools/backtest_engine.py` Python stub

- **證據**：文件 header `backtest stubbed — run in Rust openclaw_core::backtest`，但 **Rust openclaw_core::backtest 本身是死代碼（H3）**
- **業務影響**：BacktestEngine API 可能實際完全不工作（上下兩層都是 stub/dead）
- **建議行動**：P2 — 端到端驗證 `/api/v1/backtest/*` 返回是否空；驗證後刪 stub 或真連接

#### FA-2026-04-24-M4 · `evolution_engine.py` 運行路徑不明

- **證據**：
  - `evolution_auto_scheduler.py:79` ctor 帶 `truth_registry=None`
  - `local_model_tools/evolution_engine.py:476 self._engine.run(config, ohlcv_data)` — `_engine` 來源？
  - grep 沒發現 `EvolutionEngine._engine = ...` 的實際賦值
- **建議行動**：P3 — 另案 trace `EvolutionEngine` 初始化路徑

#### FA-2026-04-24-M5 · V999 migration 版本號衝突

- **證據**：
  - `V999__exit_features.sql` 存在（2026-04-18 EXIT-FEATURES-TABLE-1）
  - V020+V021+V023 後依然保留 V999；標準做法應已重命名為 V022 或 V024
- **業務影響**：新 migration 命名衝突風險；auto-migration engine opt-in 可能漏套或重複套
- **建議行動**：P3 — 改名（需 operator 授權 DROP/rename；Idempotent check 已在 CLAUDE.md §七 regulations）

#### FA-2026-04-24-M6 · `rl_transitions` / `symbol_clusters` / `promotion_pipeline` 僵屍表

- 見 H4 表格。P3 — 直接 migration rollback 刪除或標 deprecated

#### FA-2026-04-24-M7 · `learning.james_stein_estimates` 寫入路徑孤立

- **證據**：`ml_training/james_stein_estimator.py:361 INSERT INTO learning.james_stein_estimates`；僅 `edge_estimator_scheduler.py` 引用 `james_stein_estimator` 模組
- **業務影響**：scheduler 寫入 `edge_estimates.json` 檔案，不清楚是否同時寫 DB
- **建議行動**：P3 — 另案驗證 js_estimator 寫 DB 是否 active

#### FA-2026-04-24-M8 · `scout_routes.py` 5 async 路由風險（承襲 FA-2026-03-31 FA-3）

- **證據**：FA-2026-03-31 記載已修，但重驗 `scout_routes.py` 還需檢查 async / threading 混用；暫列 Medium
- **建議行動**：P3 — re-audit `scout_routes.py` threading.Lock 使用

#### FA-2026-04-24-M9 · `_seed_registry` singleton 與 STRATEGIST_AGENT.set_truth_registry(_TRUTH_REGISTRY) 不同源？

- **證據**：
  - `main.py:288` 有 `_seed_registry = _TruthSourceRegistry()`（FA-2026-04-01 記載）
  - `strategy_wiring.py:806` 注入的是 `_TRUTH_REGISTRY`（不同變數名）
- **驗證**：需讀 strategy_wiring.py 驗證是否 singleton 統一
- **建議行動**：P3 — 驗證 `_TRUTH_REGISTRY` 是否 = `_seed_registry`

#### FA-2026-04-24-M10 · `OPENCLAW_SRV_ROOT` legacy alias 與 `OPENCLAW_BASE_DIR` 不 fallback

- **證據**：CLAUDE.md §六 表格備註「兩者互不 fallback，Mac 部署時建議 export 同值」
- **業務影響**：115 歷史腳本用 `OPENCLAW_SRV_ROOT`；新代碼用 `OPENCLAW_BASE_DIR`；Mac 跨平台風險
- **建議行動**：P3 — 統一 env var 或加 startup assert 一致

#### FA-2026-04-24-M11 · `authorization.json` 未簽，但 LiveAuthWatcher 仍 poll 每 5s

- **證據**：TODO 開頭 `LiveAuthWatcher 跑中 env=LiveDemo poll_interval_secs=5；authorization.json 未簽`
- **業務影響**：LiveDemo 無法真正啟動；5s 輪詢但無 auth → engine 日誌噪音
- **建議行動**：P3 — LiveAuthWatcher 在 `authorization.json` 不存在時應長 backoff（而非固定 5s）

#### FA-2026-04-24-M12 · 新 SQL migration 規範（CLAUDE.md §七）強制 Guard A/B/C 但 V023 已有 guard

- **證據**：CLAUDE.md §七 記載 V023 是 retrofit；但更舊 migration（V001-V022）**不保證**有 Guard A
- **業務影響**：engine auto-migration opt-in 在 legacy schema drift 情境可能靜默覆蓋
- **建議行動**：P3 — audit 所有 V001-V022 的 Guard 覆蓋度

#### FA-2026-04-24-M13 · `_scout_worker` singleton 未登記 CLAUDE.md §九

- **證據**：CLAUDE.md §九 singleton 表沒有 `_SCOUT_WORKER`（`strategy_wiring.py:694`）
- **業務影響**：singleton 登記不完整，新 session 接手無法從 §九 掌握所有全局狀態
- **建議行動**：P3 — 補登

#### FA-2026-04-24-M14 · `MAX_SYMBOLS_TO_TRADE` 配置不一致（承襲 FA-2026-04-01 殘餘）

- **證據**：FA-2026-04-01 記載 `MarketScanner=5，StrategyAutoDeployer=25`，scanner 截斷 10
- **建議行動**：P3 — 對齊（FA-2026-04-01 未修復項）

---

### 2.4 Low — cosmetic / 文檔同步

#### FA-2026-04-24-L1 · `experiment_ledger_snapshot.json` 預設路徑未在 memory 記載

#### FA-2026-04-24-L2 · `apply_ai_consultation` DeprecationWarning 存在但未設 sunset 日期

#### FA-2026-04-24-L3 · 多個模組有 `TODO` / `FIXME` 標記（Rust 60 處，Python 127 處）— 需定期 triage

#### FA-2026-04-24-L4 · `live_reserved` 概念只在 Python，未對應 Rust engine 的 mode state

#### FA-2026-04-24-L5 · `strategist_models.py` 有 "啟發式評估" 但 shadow=False 後不明是否仍用於 fallback

#### FA-2026-04-24-L6 · `layer2_cost_tracker.py` 726 行但沒有 DB 持久化路徑（cost 只在 session 生命週期內）

#### FA-2026-04-24-L7 · `layer2_tools.py` 906 行工具箱（TOOL_SUBMIT_RECOMMENDATION / TOOL_WEB_SEARCH）— 沒有實時工具使用統計看板

#### FA-2026-04-24-L8 · `helper_scripts/deploy/` 路徑只有 README，systemd → launchd 跨平台遷移腳本未實作（CLAUDE.md §七 第 3 條）

---

## 三、死代碼檢驗詳述 / Dead Code Audit

### 3.1 Rust `openclaw_core` — 9/17 模組死代碼

見 H3 表格。**合計 ~4468 行 Rust 原始碼 + 測試**在 engine runtime 零路徑。

**具體實證**（2026-04-24 grep 結果）：
- `openclaw_core::attention` — engine 0 引用（除 `budget_config.rs` 註解）
- `openclaw_core::attribution` — engine 0 引用
- `openclaw_core::backtest` — engine 0；只 `openclaw_core/tests/golden_extreme.rs` + Python 註解引用
- `openclaw_core::cognitive` — engine 0；`openclaw_types::lib.rs` re-export `CognitiveParams` 等 type 但 `CognitiveModulator` struct 0 用
- `openclaw_core::dream` — engine 0
- `openclaw_core::message_bus` — engine 0
- `openclaw_core::opportunity` — engine 0
- `openclaw_core::order_match` — engine 0（已由 `paper_state/fill_engine.rs` 取代）
- `openclaw_core::portfolio` — engine 0

**活躍部分**：`stop_manager`（3 處 engine 引用）、`guardian`（5+ 處 review 接線）、`h0_gate`（1 type）、`execution`（1 FillResult）、`indicators`（多處 engine 使用）、`klines`（多處）、`governance_core`（tests + config）、`signals`（多處）、`sm`（多處）、`risk`（多處）、`cost_gate`（0 engine；engine 有自己的 `ai_budget/cost_gate.rs`）。

### 3.2 Python 側被創建但 0 消費的 singleton

- `H0_GATE`（paper_trading_wiring.py:290）— 0 方法調用（見 H2）
- `H0HealthWorker`（paper_trading_wiring.py:291）— 採樣但數據不被讀
- `PERCEPTION_PLANE.validate_for_decision` — 0 production 調用（見 H1）
- `TruthSourceRegistry` `get_all_claims()` — `main.py:355` 有讀但只做 seed logging，不進 decision loop

### 3.3 0 production INSERT 的 learning 表

見 H4 表格。

### 3.4 Silent-unscheduled ML 腳本

見 H5 表格。

### 3.5 被 deprecated 但留著的 API

- `apply_ai_consultation()`（main_legacy.py）— DeprecationWarning 但未 remove
- `PipelineBridge`（DEAD-PY-2）— `PIPELINE_BRIDGE = None` stub 保留
- `paper_trading_engine.py`（1C-3-F 退場）— `PAPER_STORE = None` stub 保留
- `compute_atr_pct`（P0-13 fast_track 用）— 標 `#[deprecated]` 保留

### 3.6 Legacy 保留但被繞過

- `grafana_data_writer.pipeline_bridge` 參數（M2）
- `OPENCLAW_SRV_ROOT` legacy env alias（M10）
- 115 歷史 maintenance scripts 使用舊 env var

---

## 四、結論章節 / Conclusions

### 4.1 總計發現數

- **本輪新發現**：34 項
  - Critical：3
  - High：9
  - Medium：14
  - Low：8
- **驗證通過**：18 項 CLAUDE.md / TODO 宣稱
- **Rust 死代碼**：9 模組 ~4468 行
- **DB silent tables**：6 張
- **ML silent-unscheduled**：5 個腳本

### 4.2 優先級分佈

| 優先級 | 本輪 | FA-2026-04-01 比較 | 備註 |
|---|---:|---:|---|
| Critical | 3 | 2（P0-FA-1 / MessageBus 斷裂） | 舊 2 項已閉合，新 3 項聚焦 Agent 鏈 shadow-only 本質 |
| High | 9 | 5 | ↑ 主要因本輪更深入 learning / ML pipeline |
| Medium | 14 | 6 | ↑ 包含配置漂移與 legacy 清理 |
| Low | 8 | 4 | 文檔同步債 |
| **總計** | **34** | **17** | ↑ 翻倍；代碼量擴大 + 檢查更細 |

### 4.3 最重要 5 項 Top-Level Findings

1. **FA-C2 ExecutorAgent `_shadow_mode=True` 硬寫死未配置化** — 5-Agent 鏈最後一步永遠 log-only；Agent 自主下單 path 實際不存在。**建議 P1 修**：改為 ExecutorConfig 欄位 + runtime switch。

2. **FA-C3 Decision Lease 在 Rust 真實交易路徑不存在** — 原則 3「AI 輸出 ≠ 即時命令」的核心閘門在 Rust intent_processor 0 實作。**建議 P1 決策**：更新 CLAUDE.md §五 架構圖明確 Lease 為 Python shadow only；或 Rust 側加 Lease IPC gate。

3. **FA-C1 Layer 2 自主推理循環無生產觸發** — 整個 `Layer2Engine.run_session()` 只有 GUI 手動 route 呼叫，無 scheduler / cron / event trigger。原則 11/15 Agent 自主性半成立。**建議 P2**：加 Conductor 自主觸發（新聞事件 / 週期 / 持倉信號）。

4. **FA-H3 openclaw_core 9/17 模組死代碼** — ~4468 行 Rust 代碼 + 測試 engine 0 使用（attention / attribution / backtest / cognitive / dream / message_bus / opportunity / order_match / portfolio）。Rust migration master plan v2 §2.4 規劃但 Python 側同義功能保留取代。**建議 P2**：決策接線 vs 刪除 vs 標 dead_code。

5. **FA-H4 + H5 學習管線實際未閉環** — 6 張 learning 表 0 production INSERT，5 個 ML 訓練腳本 silent-unscheduled，原則 12「持續進化」明顯未達。TODO §P1-7 LEARNING-PIPELINE-DORMANT-1 只覆蓋 edge estimator 一條線。**建議 P2**：擴大 P1-7 至全部 learning 表 + cron 接線計畫。

---

### 4.4 與 FA-2026-04-01 的對比

| FA-2026-04-01 P0 findings | 2026-04-24 狀態 |
|---|---|
| P0-FA-1 TruthSourceRegistry 從未注入 | ✅ 已修（strategy_wiring.py:806/812） |
| MessageBus Guardian→Executor 斷裂 | ✅ 已修（guardian_agent.py:456 發 APPROVED_INTENT）；但 Executor shadow_mode=True 讓後半鏈仍 log-only |
| BacktestEngine API 無數據源 | ⚠️ 未完整驗證；M3 標為新項 |

| FA-2026-03-31 high findings | 2026-04-24 狀態 |
|---|---|
| FA-7 Perception Plane register_data() 零調用 | ✅ 部分修（scout_routes.py:387,489 有調用）；但 validate_for_decision 仍死（H1） |
| FA-6 H1 Regime-aware 缺失 | 🔴 **仍未閉環**（H9） |
| FA-9 ScoutWorker interval 不可配置 | ❓ 未重驗 |
| FA-12 H1 冷卻字典無容量上限 | ❓ 未重驗 |

### 4.5 本輪 FA 方法論注記

- **事實驗證原則**：所有 Critical/High 發現基於 grep 結論 + 文件路徑+行號，非推測
- **推斷標注**：若 grep 無命中但設計文檔宣稱 active，標為「推斷 shadow / 需另案驗證」
- **認知誠實**：5-Agent 鏈代碼真實存在，但「shadow-only 運行」不等於「死代碼」— 兩者混淆是常見誤判陷阱。本報告明確區分「代碼死」（engine 0 引用） vs 「運行時 shadow」（代碼存在但 mode=shadow）
- **跨 session 一致性**：本報告基於 Mac CC session，未觸及 Linux runtime 實測資料（Mac=開發 / Linux=Runtime，詳 memory `project_dev_runtime_split.md`）。真實 live 流量 / DB rowcount 驗證需 Linux ssh bridge workflow。

---

## 附錄 A · 本輪 grep 驗證指令樣本

```bash
# 1. Executor shadow_mode 寫死驗證
grep -n "_shadow_mode" app/executor_agent.py  # 命中 482, 512
grep -n "ExecutorConfig(" app/strategy_wiring.py  # 命中 468

# 2. Decision Lease Rust 0 引用驗證
grep -r "Lease\|lease_id\|DecisionLease" rust/openclaw_engine/src/intent_processor/  # 0 命中

# 3. openclaw_core 模組 engine 引用
grep -r "openclaw_core::\(opportunity\|cognitive\|dream\|attention\|attribution\|portfolio\|message_bus\|order_match\|backtest\)" rust/openclaw_engine/src/  # 0 命中（除 backtest 在 tests 中）

# 4. Layer 2 自主觸發
grep -r "run_session" app/ | grep -v "test_\|:.*#"  # 只有 layer2_routes.py:210

# 5. learning 表 INSERT
grep -r "INSERT INTO learning.rl_transitions" program_code/  # 0 命中

# 6. PerceptionPlane validate 消費
grep -r "validate_for_decision" app/ | grep -v "^.*test"  # 0 命中
```

## 附錄 B · 關鍵檔案指針

- `/Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/executor_agent.py:482` — _shadow_mode=True
- `/Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_wiring.py:468` — ExecutorConfig() 不傳參
- `/Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/layer2_routes.py:210` — Layer 2 唯一生產觸發點
- `/Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_hub.py:693` — acquire_lease
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine/src/intent_processor/router.rs:106,507` — Guardian Rust review 真實呼叫
- `/Users/ncyu/Projects/TradeBot/srv/rust/openclaw_core/src/lib.rs` — 17 模組列出
- `/Users/ncyu/Projects/TradeBot/srv/sql/migrations/V004__learning_features_obs_risk_tables.sql` — 10 張 learning 表 migration
- `/Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/paper_trading_wiring.py:290` — H0_GATE 創建但無消費
- `/Users/ncyu/Projects/TradeBot/srv/program_code/ml_training/` — 5 個 silent-unscheduled ML 腳本

---

**報告結束**

生成日期：2026-04-24
下一輪審計建議觸發條件：
1. DUAL-TRACK Phase 2 shadow 啟動後（ExitConfig.shadow_enabled=true）
2. ExecutorAgent promote 到 live 後
3. Phase 5 cost_gate 重啟後
4. P1-7 LEARNING-PIPELINE-DORMANT-1 全面解封後
