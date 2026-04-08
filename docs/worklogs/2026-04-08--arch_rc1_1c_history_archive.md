---
date: 2026-04-08
type: archive
scope: ARCH-RC1 Session 1A → 1C-3-E F-mini 詳細歷史
---

# ARCH-RC1 Session 1 全程詳細歷史歸檔

> 從 CLAUDE.md §三 + TODO.md ARCH-RC1 段切出。新 session 不需要讀此文件，僅供歷史查閱。
> 完整 commit 歷史見 `docs/CLAUDE_CHANGELOG.md`。

---

## Session 1A — 死代碼大屠殺（2026-04-07 · `7f59e9b` · -270 行 / 0 行為改變）

盤點 rust/ tree 發現 **7 套重疊風控/配置系統**：Python RiskManager / openclaw_core::RiskManagerConfig / openclaw_engine::RuntimeConfig / openclaw_types::EngineConfig / openclaw_types::risk / GuardianConfig / H0GateConfig。先砍 3 個確認純死的：
- `openclaw_engine::config::MlConfig`（從未接通；真實 ML 用 `ml::kelly_sizer::KellyConfig` + 構造參數）
- `openclaw_engine::config::attention_*_ms` 5 欄位（cognitive 系統用 scan_interval_s 不是這個）
- `openclaw_types::config::EngineConfig + ParamTemperature`（V3-PA-5 規劃，6 欄位全有替代實作）

## Session 1B — 統一 Config 骨架（2026-04-07 · `0523f17` · +2632 行 / +58 tests）

- `config/store.rs`：泛型 `ConfigStore<T>` = `Arc<ArcSwap<T>>` + mutex 序列化 + all-or-nothing patch + PatchSource (Operator/Agent/Migration/Startup)
- `config/risk_config.rs`：**RiskConfig 13 sub-struct**（meta/limits P1/overrides P0/per_strategy/agent P2 含 partial_tp/cascade 6 級/regime 5×3 從 hardcode 提升/cost_gate/dynamic_stop/market_gate 收編 9 欄位/anti_cluster/correlation/runtime/experimental），跨 sub-struct invariant：partial_tp ≤ take_profit_max_pct
- `config/learning_config.rs`：**LearningConfig** + Phase 4.1 default-off 收編 (`switches.teacher_loop_enabled = false`)
- `config/budget_config.rs`：**BudgetConfig** 含 AttentionTax 整塊（含 enabled / 4 burn_rate / 4 grade / cost_edge_max_ratio）
- `config.rs` → `config/mod.rs` 透過 git mv，零內容變動

**ARCH-RC1 契約（永久）**：所有交易/風控/學習/預算/市場參數由 Rust 權威持有，分 3 個獨立熱重載 Config + 既有 StrategyParams = 4 個 IPC 寫入面。Python 完全廢掉風控核心，只剩 IPC 讀取 adapter。**禁止 restart-to-apply**。

測試：engine lib **624 → 682** (+58, 0 fail) · core/types 全綠 · 0 regression。

## Session 1C-1 — Rust call site 遷移（2026-04-07 · `2007b67` `6768381` `ef30bf1` · 3 commits · +747/−1293 淨 −546 行）

- **B0** `2007b67`: AntiCluster.max_same_direction 欄位校齊（guardian/IPC/GUI 已用，不可刪）
- **B1** `2007b67`: `openclaw_core/src/risk/` 瘦身 — 刪 RiskManagerConfig + checks.rs，拆出 regime.rs（保留無狀態 regime fallback 供 stops.rs 使用）
- **B1b** `2007b67`: 新建 `openclaw_engine/src/risk_checks.rs`（502 行 / 16 tests），check_order_allowed + check_position_on_tick 改讀 &RiskConfig，cost_edge_max_ratio 跨 Config 讀 BudgetConfig（契約允許 runtime 跨讀，只禁校準耦合）
- **B2-4** `2007b67`: call site migration — tick_pipeline / intent_processor / position_risk_evaluator / event_consumer/setup / pipeline_types / tests；所有舊平欄位 (dynamic_stop_base_ratio / cost_gate_k_base / adx_trending_threshold 等) 改讀新 sub-struct 路徑
- **B5** `6768381`: RuntimeConfig 刪 8 個風控欄位（p1_risk_pct / max_stop_loss_pct / max_take_profit_pct / max_open_positions / max_total_exposure_pct / max_leverage / max_drawdown_pct / max_same_direction_positions）+ 改名 `EngineBootstrap`；deprecated type alias 過渡 1C-2
- **B6** `ef30bf1`: `openclaw_types::risk` 刪除死代碼 — GuardianConfig / StopConfig / composite RiskConfig 全 0 consumer

測試：engine lib 682 → 708 · core 386 → 387 · types 30 → 27 · 0 regression。**風控並行系統 7→2 套**。

## Session 1C-2 — TOML loader + 5 引擎熱重載（2026-04-07）

**1C-2-A** (`581e1e2`): 新 `config/io.rs` 泛型 TOML loader + 6 tests；main.rs `load_unified_configs()` 從 `settings/risk_control_rules/*.toml` 載入 3 個 Config 並包入 `Arc<ConfigStore<T>>`；missing-file fail-soft 回退到 Default + validate。

**1C-2-B** (`e3014ef`): ConfigStore handles 穿透 EventConsumerDeps → event_consumer → wire_pipeline → TickPipeline；新 fields `risk_store` / `budget_store` / `risk_config_version_seen` + setters；`sync_risk_config_if_changed()` 在 `on_tick()` 頂部 compare-and-pull（single atomic load，熱路徑零鎖）；`current_cost_edge_max_ratio()` 取代 1C-1 的硬編碼 0.8。

**1C-2 Option B** (`8240a25`): 抽出 `apply_risk_snapshot()` 作為**單一傳播入口**；Guardian 進入熱重載迴圈。

**1C-2-F Engine 收編**（3 個 commit，3 個執行引擎進入熱重載）：
- **F1** (`1a7fc8b`) E-Merge-3：RiskGovernorSm.thresholds 從 RiskConfig.cascade 同步（15 欄位 1-to-1 映射 + 命名差異）。之前永遠是硬編碼 default。
- **F3** (`e7f00d4`) E-Merge-2：H0Gate 的 3 個風控欄位 RMW 從 RiskConfig.limits 同步；`H0Gate::update_config()` setter 新建。
- **F2 降級** (`91b5db8`) E-Merge-1：StopManager 不是死代碼（H0/pause 保護 fallback 是故意設計），原計劃「殺 StopManager」降為「paper_state.stop_config 同步」，25 行 config 同步取代 6-7 小時刪檔 + port 測試。

**1C-2-C** (`5f87bca`): 6 個 unified Config IPC 端點 (`get/patch_{risk,learning,budget}_config`) — JSON 深合併 → 反序列化 → validate → `store.replace()` → tick-level hot reload。+6 tests。

**1C-2-E schema** (`de75191`): V014 `observability.engine_events` audit 表 + 3 indexes，applied to live PG。event_type ∈ {startup,shutdown,config_patch,config_reject,reconcile,crash}。

**1C-2-D** (`950f547`): 新 `config/legacy_migration.rs` — 啟動時若 `risk_config.toml` 不存在且 `operator_risk_config.json` 存在，從 `RiskConfig::default()` 起手映射 ~15 個 `global_config.*` 已知欄位 → save_toml → rename `.legacy`。+5 tests。

**1C-2-E audit wiring** (`b0fa2c6`): IpcServer 加 `audit_pool: AuditPoolSlot` 延後注入，main.rs 在 db_pool 就緒後 `replace(pg.clone())`。`handle_patch_config` 成功時 `tokio::spawn` INSERT V014 row。Fail-soft：DB 不可用 → audit 跳過，patch 仍成功。

**熱重載終局**：`apply_risk_snapshot()` **單一傳播入口**，每次 RiskConfig store 版本變化同步 **5 個下游執行引擎**：
1. `intent_processor.risk_config`（Gate 0 + tick check 主引擎）
2. `intent_processor.guardian`（P0 trade intent modify verdict）
3. `paper_state.stop_config`（H0/pause 保護 fallback）
4. `h0_gate.config`（健康 + 風控欄位）
5. `governance.risk.thresholds`（6-tier 級聯狀態機）

測試：engine **682 → 725** (+43) · core/types 不變 · 0 regression。

## Session 1C-3 — Python RiskManager 收編（2026-04-07~08）

**1C-3-A** (4/7): gap analysis + IPC surface design。

**1C-3-B** (`8447fbf`): `risk_view_client.py` (299 行) + `atr_tracker.py` (153 行) lift-and-shift + 15 tests。

**1C-3-C** (`c6fcd13`): `risk_routes.py` migrated to RiskViewClient（6 個 TestRiskRoutes 暫 skip 留尾，1C-3-D 處理）。

**1C-3-B-2** (`9f46b06`): operator manual governor override 三層防護：
- IPC: reason_code 白名單 / 單步 / 24h cooldown / CB&MR 鎖死
- SM: lookup_rule transition table + min_hold_time 5 min
- Audit: V014 engine_events (from/to/reason_code/notes)
- Rust 731→740 (+9) · Python 15→17 (+2) · 0 regression

**E2 三 commit review** — `docs/audits/2026-04-08--e2_review_1c3_bbc.md`：
- 1C-3-B APPROVED_WITH_NITS · 1C-3-C APPROVED_WITH_NITS · 1C-3-B-2 CHANGES_REQUIRED
- M-1 (test gap) + M-2 (audit hole) + N-5 (payload shape) 必修

**1C-3-D M-1 fix** (`f8772c0`): event_consumer/tests.rs 加 8 個 real guard tests via `handle_paper_command` + oneshot — 之前 governor override 的 IPC 守衛只有 path-level coverage，現在 reason_code 白名單 / 單步 / cooldown / CB&MR lockout 都有 end-to-end test。engine 740 → 748。

**1C-3-D M-2 + N-5 fix** (`a1cf772`): `spawn_governor_audit_row` 簽名重構 5-positional → `(pool, event_type, payload: serde_json::Value)`；rejected governor overrides 在 `Ok(Ok(Err(e)))` branch 也寫 V014（new event types `governor_escalate_rejected` / `governor_de_escalate_rejected`）。

**1C-3-D 主體** (`144f46f`): approach A aggressive cull
- `risk_manager.py` **1633 → 53 行** (-97%)：只剩 `REGIME_TIME_MULTIPLIERS` 常量 + `RiskManager(RiskViewClient)` 薄子類
- `paper_trading_wiring.py` 移除 `set_portfolio_risk_control` / `set_governance_hub` / `set_change_audit_log` 三個 RiskManager 注入點
- 刪除 9 檔 ~6900 行純 Python 風控/H0/Engine 測試（邏輯已 100% 在 Rust 748 tests 覆蓋）：`test_risk_manager{,_edge}` / `test_h0_gate{,_cooldown_integration}` / `test_paper_trading_engine{,_inverse}` / `test_trailing_stop_cost_constraint` / `test_integration_phase{5,8}`
- conftest 移除 4 個 risk fixtures · `test_integration_phase2::test_portfolio_risk_control_injected` 重寫為驗證 wiring singleton
- **+46 / -7882 淨 -7836** · Python 2944 passed · **0 regression**

**1C-3-E F-mini** (4/8 PM · `d8fb7f2` `cf3ff48`):
- step 1 (`d8fb7f2`): `bridge_core.py:294` `_engine.risk_manager._price_tracker` 死引用清除（ATR 由 Rust 權威）
- step 2 auto-resolved: 6 個 skipped `TestRiskRoutes` 隨 1C-3-D `test_risk_manager.py` 整檔 cull 一起消失
- F-mini 三小修 (`cf3ff48`): `paper_trading_routes.py` 砍 4 個 dead imports / `risk_routes.py::unhalt_session` 砍 deprecated PAPER_STORE.mutate / `_h0_db_probe` 改 `os.stat()`

## 風控收編軌跡終局

```
1A 前:      Python RiskManager 1633 + 6 套 Rust 並行 = 7 套
1A:         刪 3 套確認死碼 → 4 套
1C-1:       1 Rust Config 權威 + Python RiskManager 1633（待空殼化）
1C-2-F:     1 Config 權威 + 5 engines 同步熱重載
1C-3-D:     1 Rust ConfigStore 權威 + 53 行 Python RiskViewClient shim
1C-3-E F-mini: 邊角死代碼清除
1C-3-F:     【pending】Python paper_trading_engine.py (2248) 徹底退場
            → Rust 引擎成為 paper / demo / live 三模式唯一引擎
```

## 風控執行引擎收編子任務狀態

| 引擎 | 處理 | Commit |
|---|---|---|
| risk_checks::check_order_allowed | 主引擎，1C-1 完成 | `2007b67` |
| risk_checks::check_position_on_tick | 主引擎，1C-1 完成 | `2007b67` |
| Guardian | 1C-2-B hot-reload | `8240a25` |
| H0Gate | 1C-2-F E-Merge-2 RMW | `e7f00d4` |
| StopManager | 1C-2-F E-Merge-1 降級為 H0/pause fallback | `91b5db8` |
| RiskGovernorSm | 1C-2-F E-Merge-3 thresholds 同步 | `1a7fc8b` |
| Python RiskManager | 1C-3-D 53 行 shim | `144f46f` |

**E-Merge-4 (Phase 2 / 可選)**: Guardian 進一步去 config struct 化 — GuardianConfig 退化為 `RiskConfig.limits + anti_cluster + guardian_modify` sub-view。收益有限，Phase 2 順手做。

## 留尾未完成

- **1C-3-F**（~5h fresh context）: Python paper_trading_engine.py 2248 行徹底退場 — 詳細接手指引見 `docs/worklogs/2026-04-08--1c3e_fmini_handoff.md`
- **1C-4 收尾**: Position Reconciler / Governor cooldown PG 持久化 / NewsPipeline run_once 60s spawn / 熱重載 e2e 驗收測試 / E2+E4+QA
