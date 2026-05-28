# 2026-04-07 日匯總 — Phase 4 完成 + ARCH-RC1 1A/1B/1C-1/1C-2

## 一、完成項總覽

### Session 1: Phase 4 CODE-COMPLETE + W-3 LinUCB Hotfix
- [x] Phase 4 全 22 子任務（4-00~4-21）committed + W-1/2/3/4 wiring sweep
- [x] 4-21 multi-role audit CONDITIONAL APPROVE（pending 4.1 Claude API loop）
- [x] LinUCB signal→strategy whitelist + arm-not-found spam 修復
- [x] Engine lib tests 441 → 589（+148）

### Session 2: Phase 4.1 SHIPPED + E3 R6 Security Audit + P2 Partial
- [x] **Phase 4.1 Claude API Consumer Loop** — `TeacherConsumerLoop` round-robin 5 scopes, default-off, IPC toggle ready（`ee6fd00`）
- [x] **E3 R6 Security Audit CONDITIONAL GO** — 8 bypass vectors 全 SAFE + 3 P1 closed（`8762d1d`）
- [x] P2 tick_pipeline.rs 部分拆分：`decision_context_producer.rs`（294 行）+ `position_risk_evaluator.rs`（247 行）— 2211 → 2117 行（`e7ca473` / `aecea27`）
- [x] Live blockers 3 → 1（僅剩 7d paper 觀察期）

### Session 3: ARCH-RC1 1A + 1B — 死代碼清理 + 統一 Config 骨架
- [x] **1A 死代碼清理**：刪 MlConfig + attention_*_ms 5 欄位 + types::EngineConfig（~270 行刪除，`7f59e9b`）
- [x] **1B 統一 Config 骨架**：4 個新檔案 — `ConfigStore<T>` 泛型（ArcSwap 熱重載）+ `RiskConfig`（13 sub-struct）+ `LearningConfig`（5 sub-struct）+ `BudgetConfig`（5 sub-struct），共 +2632 行（`0523f17`）
- [x] 關鍵決策固化：3-Config + StrategyParams / AttentionTax 完全在 BudgetConfig / partial_tp 在 RiskConfig.agent / TOML on-disk + JSON IPC / ArcSwap tick-level 熱重載

### Session 4: ARCH-RC1 1C-1 + 1C-2-A/B/Opt-B/F — Call Site 遷移 + 熱重載接通
- [x] **1C-1 Batches 0-6 全部完成**：風控系統 7 → 2 套（1 個 Config 權威 + Python RiskManager 待空殼化）
  - core::RiskManagerConfig 物理刪除 + 9 檔案改讀 engine::RiskConfig（`2007b67`）
  - RuntimeConfig → EngineBootstrap 改名 + 8 風控欄位刪除（`6768381`）
  - types::risk 死代碼清理（`ef30bf1`）
- [x] **1C-2-A** TOML loader `load_toml_or_default<T>` + `save_toml` atomic write（`581e1e2`）
- [x] **1C-2-B** Pipeline wiring — `sync_risk_config_if_changed()` tick 頂部版本檢查 + `current_cost_edge_max_ratio()` 跨 Config 讀（`e3014ef`）
- [x] **Option B** `apply_risk_snapshot()` 單一傳播入口 — Guardian RMW 熱重載（`8240a25`）
- [x] **1C-2-F** 執行引擎收編三連：RiskGovernorSm cascade（`1a7fc8b`）+ H0Gate limits（`e7f00d4`）+ paper_state.stop_config（`91b5db8`）→ **5 個執行引擎全部 tick-level 熱重載**

### Session 5: ARCH-RC1 1C-2 完整收尾
- [x] **1C-2-C** 6 個 unified Config IPC 端點：get/patch_{risk,learning,budget}_config — generic `json_merge` + validate + replace（`5f87bca`）
- [x] **1C-2-E** V014 `observability.engine_events` audit 表 + fire-and-forget 寫入 hook（`de75191` / `b0fa2c6`）
- [x] **1C-2-D** legacy `operator_risk_config.json` → TOML 一次性遷移（`950f547`）
- [x] **1C-3 scope doc** 寫就（`docs/references/2026-04-07--arch_rc1_1c3_scope.md`）
- [x] CLAUDE.md / TODO.md / MEMORY.md 大清理（歷史歸檔，40K → ~25K）

## 二、關鍵決策

| # | 決策 | 結論 |
|---|------|------|
| 1 | Config 數量 | 3 個（Risk/Learning/Budget）+ 既有 StrategyParams = 4 IPC 寫入面 |
| 2 | 熱重載機制 | ArcSwap lock-free 讀 + Mutex 序列化寫，tick-level latency，禁止 restart-to-apply |
| 3 | StopManager 命運 | 保留作為 H0/pause 保護 fallback + backtest sizing utility（research agent 確認非死代碼） |
| 4 | Engine 合併策略 | 不追求單一引擎 — 1 個 Config 權威 + 多個職責清晰引擎（Guardian/H0Gate/RiskGovernorSm） |
| 5 | Python RiskManager | 1633 行 → ~150 行 RiskViewClient 純 IPC 讀（留 1C-3） |
| 6 | cost_edge_max_ratio | BudgetConfig 為權威，熱路徑跨 Config 每 tick 快照讀 |
| 7 | Phase 4.1 啟用方式 | default-off，IPC `set_teacher_loop_enabled {"enabled": true}` 手動啟用 |

## 三、Commits（本日 ~25 個）

```
# Phase 4 CODE-COMPLETE
d36116f  feat(4-00): Phase 4 Dashboard frontend
b4cfade  feat(4-15): AI Budget tracker (Rust) + V010
31fb227  feat(W1): Phase 4 wave 1 — 5 modules
996a0cb  feat(W2): Phase 4 wave 2 — 5 modules + ARCH-RC1
b16335f  feat(W3): Phase 4 wave 3 — outcome tracker + LinUCB + news
122239b  feat(W4a): News/DL-3 cards + decision_context columns
4a5ef41  test(4-19): Phase 4 e2e integration test
435930f  feat(W4b+wiring): Phase 4 wiring sweep + weekly report
83a9dc7  hotfix(W-3 linucb): signal→strategy whitelist fix

# Phase 4.1 + E3 R6 + P2
ee6fd00  feat(4.1): Claude API Consumer Loop + E3 R6 audit
8762d1d  feat(4.1): close E3 R6 P1 items + IPC teacher_loop
e7ca473  refactor(P2): extract DecisionContextMsg producer
aecea27  refactor(P2): extract per-position risk evaluator
e83024a  docs: Phase 4.1 + E3 R6 + P2 partial sync

# ARCH-RC1 1A/1B
7f59e9b  refactor(1A): dead code cleanup (~270 lines)
0523f17  feat(1B): unified Config skeleton (+2632 lines)

# ARCH-RC1 1C-1/1C-2
2007b67  refactor(1C-1): migrate call sites to unified RiskConfig (Batch 0-4)
6768381  refactor(1C-1): RuntimeConfig → EngineBootstrap (Batch 5)
ef30bf1  refactor(1C-1): delete dead duplicate risk types (Batch 6)
581e1e2  feat(1C-2-A): TOML loader + ConfigStore construction
e3014ef  feat(1C-2-B): pipeline wiring — hot reload live
8240a25  feat(1C-2 Opt-B): Guardian hot-reload + apply_risk_snapshot
1a7fc8b  feat(1C-2-F1): RiskGovernorSm reads RiskConfig.cascade
e7f00d4  feat(1C-2-F3): H0Gate reads RiskConfig.limits
91b5db8  feat(1C-2-F2): hot-reload paper_state.stop_config
5f87bca  feat(1C-2-C): 6 unified Config IPC endpoints
de75191  feat(1C-2-E): V014 engine_events audit table
950f547  feat(1C-2-D): legacy JSON → TOML migration
b0fa2c6  feat(1C-2-E): audit wiring — V014 rows on patch
```

## 四、測試基準線

```
Engine lib:    725 passed / 0 failed（Phase 4 baseline 441 → +284）
Engine core:   387 passed / 0 failed
Types:         27 passed / 0 failed
Integration:   36 passed / 0 failed
0 regression 全日
```

## 五、風控系統統一進度

```
1A 前：  7 套並行風控/配置系統
1A 後：  6（types::EngineConfig purged）
1B 後：  6（純加法骨架，雙軌並存）
1C-1 後：2（1 個 RiskConfig 權威 + Python RiskManager 待空殼化）
1C-2 後：★ 1 個 Config 權威 + 5 執行引擎 tick-level 熱重載 ★
剩餘：   Python RiskManager 空殼化（1C-3）
```

## 六、未解決項

1. **1C-3 Python 空殼化** — `risk_manager.py` 1633 → ~150 行 RiskViewClient，32 檔案 import 遷移
2. **1C-4 收尾** — Position Reconciler + NewsPipeline spawn + 熱重載 e2e 驗收 + E2/E4/QA
3. **tick_pipeline.rs** 仍 2117 行（超 §九 1200 行硬上限 917 行），Step 4+5 高 borrow-checker 風險待專門 session
4. **Live binary 未更新** — 引擎仍跑舊版（`83a9dc7`），需 1C-4 完成後重啟載入完整 ARCH-RC1
5. **7d paper 觀察期** — Phase 4.1 TeacherConsumerLoop 啟用前唯一 blocker（calendar-time）
