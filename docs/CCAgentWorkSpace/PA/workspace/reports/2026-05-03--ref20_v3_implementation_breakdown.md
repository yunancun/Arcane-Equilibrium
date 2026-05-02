# REF-20 V3 Phase 實作 Breakdown — PA 主筆

**日期：** 2026-05-03
**Owner：** PA
**Baseline 契約：** `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md`
**UX SoT：** `docs/execution_plan/2026-05-02--ref20_ux_subdoc_v1.md`
**規模：** 9 phase / 56 task / Wave 1-9 排程帶
**Read-only：** 不寫實作代碼，僅設計接口/派發/依賴/Wave

---

## §1. Phase 工作流 Overview（DAG）

```
P0 (docs only, 1 sprint)
 ├─→ P1 (UI shell, 1.5 sprint)
 │    └─→ [P5 entry guard: LG-2/3/4 frontend merged + 7d stable]
 │
 └─→ P2a (registry/auth/manifest, 2.5 sprint)
      ├──⫴ P2b (runner, 2 sprint)  ← 部分並行（schema land 後 runner 開工）
      │    └─→ P3a (global calibration, 2 sprint)
      │         ├──⫴ P3b (cell calibration, 1.5 sprint)  ← 並行
      │         │    └─→ P4 (MLDE/Dream advisory, 2 sprint)
      │         │         ├─→ P5 (Agents Monitor extract, 1 sprint, gated by entry)
      │         │         └─→ P6 (demo handoff, 2 sprint)
```

**關鍵並行邊界：**
- P2a → P2b：P2a 的 `replay.experiments` schema land + manifest signing route 上線後，P2b runner 可開工；剩下的 P2a 8-route auth scaffolding 與 runner 開工 **並行**。
- P3a → P3b：P3a global calibration writer schema 落 + 寫 1 個 strategy demo 後 P3b 開工，**70% 重疊**。
- P4 ← P3a/b：P4 advisory 不需要 P3 滿覆蓋，只需 calibration writer interface 穩定即可開工。
- P5 entry：取決於 LG-2/3/4 frontend 進度，**外部依賴**，不在本 breakdown 工時內。
- P6 entry：P4 deploy + applier source filter schema land + Guardian gate dry-run。

---

## §2. 各 Phase Task Table

### P0 — Amendments and Gates（docs-only，1 sprint）

| Task ID | Name | Files | Owner → Reviewer | Sprint | Gate | Exit / Acceptance |
|---|---|---|---|---|---|---|
| R20-P0-T1 | REF-19 v2 amendment | `docs/references/2026-05-03--ref19_v2_amendment.md` | PA → PM | 0.5 | G5 | §11 P0 exit #1 |
| R20-P0-T2 | REF-20 v2 amendment | `docs/references/2026-05-03--ref20_v2_amendment.md` | PA → PM | 0.5 | G5 | §11 P0 exit #1 |
| R20-P0-T3 | V3 baseline + UX subdoc 簽收 commit | `srv/docs/execution_plan/2026-05-03--*.md`（已存在）| PM → 七 agent | 0.5 | G10 | §11 P0 exit #1 |
| R20-P0-T4 | Migration V### 預留（PM 主表）| `docs/governance_dev/2026-05-03--migration_v_reservation_log.md` | PM → PA | 0.5 | G5 | §11 P0 exit；§3 G5 |
| R20-P0-T5 | Guard A/B/C templates 校核 | `sql/migrations/templates/schema_guard_template.sql`（review） | E2 → PA | 0.5 | G5 | §11 P0 exit |
| R20-P0-T6 | `replay_runner` Rust binary scaffold 設計（無代碼） | `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-04--replay_runner_scaffold_design.md` | PA + E1 設計 → PM | 1 | G7, G8 | §3 G7；§12 #8/#9/#10 |
| R20-P0-T7 | `ReplayProfile::Isolated` cfg gate 設計（feature flag 範圍 + 編譯/runtime 雙層）| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-04--replay_isolated_profile_cfg_gate.md` | PA → E1, E2 | 1 | G7, G8 | §3 G7/G8 |
| R20-P0-T8 | Baseline Snapshot Mechanism §6.4 設計確認 | `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-04--baseline_snapshot_design.md` | PA + E1a → PM | 0.5 | G13 | §12 #23 |
| R20-P0-T9 | QC + E3 indicator leak-free sweep kickoff（5 strategy 任務指派 + 期限） | `docs/CCAgentWorkSpace/QC/workspace/2026-05-04--ref20_indicator_sweep_kickoff.md` | QC + E3 → PA | 0.5 | G6 | §12 #13 |

**並行：** T1 ⫴ T2 ⫴ T3 ⫴ T4 ⫴ T5 ⫴ T6 ⫴ T7 ⫴ T8 ⫴ T9（全可並行；docs-only 無代碼衝突）。
**Phase 總時長：** ~1 sprint（並行）。
**P0 sub-task 互審序：** 引用 skill `pr-adversarial-review` — T6+T7 必須由 E1 + E2 雙審（E1 確認可執行性 / E2 確認硬邊界 grep 不洩）；T4 migration reservation 必須 PA 確認 V### 不撞已 reserved 號段。

---

### P1 — Paper Replay Lab IA（UI shell，1.5 sprint）

| Task ID | Name | Files | Owner → Reviewer | Sprint | Gate | Exit / Acceptance |
|---|---|---|---|---|---|---|
| R20-P1-T1 | Paper Tab shell IA 重組（Session/Replay/Compare/Handoff 4 sub-tab） | `program_code/.../static/learning_cockpit/paper_replay_lab.html` 新增 + `paper_routes.py` shell route | E1a → A3 → E2 | 2 | G10 | §11 P1 exit |
| R20-P1-T2 | 8 Mode Badges 元件（run mode / data tier / execution confidence / runtime env） | `static/learning_cockpit/components/mode_badges.{js,css}` | E1a → A3 → E2 | 1 | G10, G15 | §12 #19, UX §7 |
| R20-P1-T3 | Disabled State Contract 元件（phase/gate 文案）| `static/learning_cockpit/components/disabled_state_pill.js` | E1a → A3 | 1 | G10 | UX §8 |
| R20-P1-T4 | 移除 Paper 既有 manual submit/cancel 控件（或隔離至 legacy-only dev surface） | `static/paper_trading_dashboard.html` + `paper_routes.py` | E1a → E2 → BB（Bybit boundary） | 1 | G10 | §12 #19, UX §3 §11.3 |
| R20-P1-T5 | Session sub-tab 接 既有 paper session display API（read-only） | `static/learning_cockpit/sub_tabs/session.js` | E1a → E2 | 1 | G10 | §11 P1 exit |
| R20-P1-T6 | Replay/Compare/Handoff 三 sub-tab 假數據 mock + 4 badge 全展（mock state P2 啟用前用） | `static/learning_cockpit/sub_tabs/{replay,compare,handoff}.js` | E1a → A3 → E2 | 2 | G10, G15 | UX §11.5/§11.6 |
| R20-P1-T7 | UI regression test `paper_replay_lab_no_order_submit` | `tests/ui/test_paper_replay_lab_shell.py` | E4 → E2 | 1 | G10 | §12 #19 |

**依賴 DAG：**
```
T1 → T5 → T7
T1 → (T2 ⫴ T3 ⫴ T4) → T6 → T7
```
**並行：** T2 ⫴ T3 ⫴ T4 共 frontend pool；T5 與 mock 三件並行。
**Phase 總時長：** ~1.5 sprint。
**Hard gate：** P1 阻塞於 P0-T3（V3+UX subdoc 簽收）。

---

### P2a — Registry / Auth / Manifest Foundation（2.5 sprint）

| Task ID | Name | Files | Owner → Reviewer | Sprint | Gate | Exit / Acceptance |
|---|---|---|---|---|---|---|
| R20-P2a-T1 | Migration V### `replay.experiments` + 物理 window 欄位 + EXCLUDE GIST | `sql/migrations/V###__replay_experiments.sql` | E1 → E2 → MIT → PA | 2 | G1, G5 | §12 #1/#7 |
| R20-P2a-T2 | Migration V### `replay.report_artifacts` + FK constraint | `sql/migrations/V###__replay_report_artifacts.sql` | E1 → E2 → MIT | 1 | G2, G5 | §12 #7 |
| R20-P2a-T3 | Migration V### `replay.simulated_fills` + lineage columns（intent_id/lease_id/idempotency_key/engine_binary_sha）| `sql/migrations/V###__replay_simulated_fills.sql` | E1 → E2 → MIT → PA | 1 | G2, G5 | §12 #7 |
| R20-P2a-T4 | Migration V### `replay.evidence_tier_backfill_report` + retrofit 三步（preflight `SELECT DISTINCT` / report fill / classify）| `sql/migrations/V###__evidence_tier_backfill.sql` + `helper_scripts/db/replay_evidence_backfill.py` | E1 → MIT → PA → PM | 2 | G3, G5 | §12 #5 |
| R20-P2a-T5 | Migration V### `learning.mlde_shadow_recommendations` ALTER（`evidence_source_tier` + `replay_experiment_id` + `manifest_hash` + CHECK 約束）| `sql/migrations/V###__mlde_evidence_source_guard.sql` | E1 → MIT → PA | 1 | G3, G5 | §12 #5/#6 |
| R20-P2a-T6 | DB role REVOKE/GRANT + verified insert function（`replay.f_insert_evidence_advisory()`） | `sql/migrations/V###__replay_db_role_guard.sql` | E1 → MIT → PA | 2 | G4, G5 | §12 #6/#14 |
| R20-P2a-T7 | Manifest canonicalization + HMAC-SHA256 signer（server-side only） | `program_code/.../control_api_v1/app/replay_manifest.py` + `replay_signing_key.py` | E1 → E2 → PA | 2 | G9 | §12 #1/#2 |
| R20-P2a-T8 | 8 replay routes auth scaffolding（**1 task 不拆**：manifests/runs×{POST/GET/cancel}/reports；參考 `agents_routes.py` 的 `_safe_query` 退化模式）| `replay_routes.py` + `replay_routes_helpers.py` | E1 → E2 → PA → BB | 2 | G14 | §12 #3/#22 |
| R20-P2a-T9 | Manifest TTL/quota/prune（30d / actor 20 / global 1 / artifact storage cap） | `replay_quota_manager.py` + cron | E1 → E2 → A3 | 1 | G9 | §12 #4 |
| R20-P2a-T10 | 5 healthcheck `check_*` 接入 `passive_wait_healthcheck.py` | `helper_scripts/db/passive_wait_healthcheck.py` | E1 → E4 → PA | 1 | G3, G14 | §12 #5/#6/#7/#22 |

**依賴 DAG：**
```
T1 → T2 → T3 → T6
T1 → T4 → T5 → T6
T6 → T7 → T8 → T10
T7 → T9
```
**並行：** T1+T4 起頭並行（不同表）；T7 ⫴ T9（signer 與 quota 解耦）。
**Phase 總時長：** ~2.5 sprint。
**Hard gate：** T1-T6 任一 migration 撞 V### → PM 重新分配（T1 先做 dry-run on Linux 雙跑 idempotency）。
**Note replay routes 不拆**：8 routes 共享 `_safe_query` helper、auth decorator、idempotency middleware；拆 8 任務會引入 import 環 + helper 重複定義；E1 一人一週可完成同一檔上 800 LOC 內。

---

### P2b — Read-Only S2/S3 Smoke Replay（2 sprint）

| Task ID | Name | Files | Owner → Reviewer | Sprint | Gate | Exit / Acceptance |
|---|---|---|---|---|---|---|
| R20-P2b-T1 | `replay_runner` Rust bin target 增加（`Cargo.toml [[bin]] name="replay_runner"`） + main.rs scaffold | `rust/openclaw_engine/Cargo.toml` + `rust/openclaw_engine/src/bin/replay_runner.rs` | E1 → PA → E2 | 1 | G7 | §12 #8/#9/#10 |
| R20-P2b-T2 | `ReplayProfile::Isolated` enum + `requires_lease()=false` + 編譯 `cfg(replay_isolated)` gate | `rust/openclaw_core/src/profile.rs` + `rust/openclaw_engine/src/governance_hub/lease.rs` | E1 → PA → E2 | 2 | G7, G8 | §12 #8/#9 |
| R20-P2b-T3 | TickPipeline + IntentProcessor 在 `Isolated` profile 下走 in-memory paper state（無 IPC/WS/exchange/DB writer） | `rust/openclaw_engine/src/intent_processor/router.rs` + `pipeline_bridge.rs` | E1 → PA → E2 | 2 | G7, G8 | §12 #8/#10 |
| R20-P2b-T4 | S2 public Bybit data fetcher（運行於 runner 內，非 engine） | `rust/openclaw_engine/src/replay/s2_fetcher.rs` | E1 → BB → E2 | 1 | G7 | §3 G7 |
| R20-P2b-T5 | S3 synthetic OHLC/tick generator | `rust/openclaw_engine/src/replay/s3_synthetic.rs` | E1 → QC → E2 | 1 | G7 | §3 G7 |
| R20-P2b-T6 | runner 啟動 verify signature → verify hash → verify §7 sweep status fail-closed sequence | `rust/openclaw_engine/src/replay/preflight.rs` | E1 → PA → E2 | 1 | G8 | §12 #2/#10 |
| R20-P2b-T7 | Mac 側 `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA=1` enforce + S0/S1 access fail-close | `rust/openclaw_engine/src/replay/mac_guard.rs` + `replay_runner` main 入口 env 檢查 | E1 → PA → E2 | 1 | G11 | §12 #12 |
| R20-P2b-T8 | runner 寫 diagnostic artifact 到 allowlisted local path → 透過 `replay_routes` 註冊（runner **不直接**寫 DB） | `rust/openclaw_engine/src/replay/artifact_writer.rs` + Python `replay_routes.register_artifact()` | E1 → PA → E2 → MIT | 1 | G7, G8 | §12 #7/#8 |
| R20-P2b-T9 | Forbidden-path runtime + unit test + 可選 `nm`/`objdump` symbol grep（defense-in-depth）| `tests/rust/test_replay_isolation.rs` + `tests/ui/test_replay_resource_isolation.py` | E4 → PA → E2 | 2 | G8 | §12 #8/#9/#10 |
| R20-P2b-T10 | Compare sub-tab 接 baseline-vs-candidate report rendering（接 P1-T6 mock） | `static/learning_cockpit/sub_tabs/compare.js` + `replay_routes.compare_report()` | E1a → A3 → E2 | 1 | G10 | §11 P2b exit |

**依賴 DAG：**
```
T1 → T2 → T3
        ├─⫴ T4
        ├─⫴ T5
        └─→ T6 → T7 → T8 → T9 → T10
```
**Crate 邊界判定：** `replay_runner` 與 `openclaw-engine` **同 crate 不同 bin target**（共享 `openclaw_core` / `openclaw_types` + `tick_pipeline` / `intent_processor` / `paper_state` 模組）；**禁止共享** `main.rs::build_exchange_pipeline` / `ipc_server` / `websocket` / `bybit_rest_client` (live mode) / `db_writer` 模組。透過 `cfg(replay_isolated)` 編譯時排除 + `ReplayProfile::Isolated` runtime gate **雙層**。
**並行：** T4 ⫴ T5（不同檔不同模組）；T6 之後 sequential。
**Phase 總時長：** ~2 sprint，與 P2a T7-T10 並行。

---

### P3a — Global Execution Calibration（2 sprint）

| Task ID | Name | Files | Owner → Reviewer | Sprint | Gate | Exit |
|---|---|---|---|---|---|---|
| R20-P3a-T1 | S0 calibration label loader（依賴 FUP-2 attribution writer 已 deploy） | `program_code/.../learning/calibration/label_loader.py` | E1 → MIT → PA | 1 | G12 | §11 P3a exit |
| R20-P3a-T2 | OOS embargo 實作 `max(7d, 2*half_life)` per strategy | `learning/calibration/embargo.py` | E1 → QC → PA | 1 | G12 | §12 #15/#18 |
| R20-P3a-T3 | Fee model 接線（maker/taker rate 從 RiskConfig） | `learning/calibration/fee_model.py` | E1 → BB → E2 | 0.5 | G12 | §11 P3a exit |
| R20-P3a-T4 | Bootstrap CI（block bootstrap Politis-Romano 1000 iter）+ shrinkage method 宣告 | `learning/calibration/bootstrap.py` + `shrinkage.py` | E1 → QC → MIT | 2 | G12 | §11 P3a exit |
| R20-P3a-T5 | n>=200 strategy-window + age<=72h 雙 gate | `learning/calibration/power_gate.py` | E1 → QC → PA | 1 | G12 | §12 #15/#16 |
| R20-P3a-T6 | Calibration writer 落 `replay.experiments`（runtime_environment='linux_trade_core' / engine_binary_sha 必填） | `learning/calibration/writer.py` | E1 → MIT → PA | 1 | G3 | §11 P3a exit |
| R20-P3a-T7 | Compare sub-tab 接 calibration freshness + 95% CI 渲染（接 P1-T6 mock） | `static/learning_cockpit/sub_tabs/compare.js` （extend）| E1a → A3 → E2 | 1 | G10 | §11 P3a Business KPI |

**依賴：** T1 → T2 → T5 → T6；T3 ⫴ T4；T6 → T7。
**Phase 總時長：** ~2 sprint。**前置依賴：** FUP-2 attribution writer deploy（外部，非本 phase 工時）。

---

### P3b — Cell-Level Calibration（1.5 sprint，與 P3a 70% 並行）

| Task ID | Name | Files | Owner → Reviewer | Sprint | Gate | Exit |
|---|---|---|---|---|---|---|
| R20-P3b-T1 | Cell key 計算 `(strategy, symbol, side)` 維度 | `learning/calibration/cell_keying.py` | E1 → QC | 0.5 | G12 | §11 P3b exit |
| R20-P3b-T2 | n>=30 cell gate + 不足→`defer_data` verdict | `learning/calibration/cell_power_gate.py` | E1 → QC → PA | 0.5 | G12 | §12 #16 |
| R20-P3b-T3 | Hierarchical Bayes / James-Stein / Empirical Bayes 三選一 implementation（依 §8.2 decision tree） | `learning/calibration/shrinkage_impl.py` | E1 → QC → MIT | 2 | G12 | §11 P3b exit |
| R20-P3b-T4 | Regime 控制（CUSUM ±3σ + Kupiec POF n>=250 + PSR(0)<0.95 三窗 + warmup 500 fills） | `learning/calibration/regime_controls.py` | E1 → QC → PA | 2 | G12 | §12 #18 |
| R20-P3b-T5 | DSR(K)>0.95 + PBO<0.5（K>=10, total trades>=320）selection-bias gate | `learning/calibration/selection_bias.py` | E1 → QC → MIT | 1.5 | G12 | §12 #17 |
| R20-P3b-T6 | Cell calibration writer 接 `replay.experiments` + `report_artifacts`（cell-level metrics） | `learning/calibration/cell_writer.py` | E1 → MIT → PA | 1 | G3 | §11 P3b exit |

**並行：** P3a-T6 land 後 P3b-T1 即可開工；P3b-T1/T2/T3/T4 全並行。
**Phase 總時長：** ~1.5 sprint，**P3a + P3b 合計 ~3.5 sprint**（vs sequential 3.5+1.5=5）。

---

### P4 — MLDE / Dream Advisory（2 sprint）

| Task ID | Name | Files | Owner → Reviewer | Sprint | Gate | Exit |
|---|---|---|---|---|---|---|
| R20-P4-T1 | DreamEngine replay candidate proposal hook（不直接寫 DB；走 `f_insert_evidence_advisory()`）| `program_code/.../ai_engines/dream_engine.py` | E1 → MIT → PA | 1.5 | — | §12 #6 |
| R20-P4-T2 | MLDE rank/veto replay candidate hook | `learning/mlde/replay_ranker.py` | E1 → MIT → PA | 1.5 | — | §12 #6 |
| R20-P4-T3 | `f_insert_evidence_advisory()` source-guarded path（FK + manifest hash + tier + output policy 雙驗）| `sql/migrations/V###__verified_insert_function.sql`（若 P2a-T6 未含）+ Python wrapper | E1 → MIT → PA | 1 | G3, G4 | §12 #6/#14 |
| R20-P4-T4 | PBO/DSR metadata 落 manifest（K, total_trades, csccv_splits） | `replay_manifest.py` extend | E1 → QC → PA | 1 | G12 | §12 #17 |
| R20-P4-T5 | `mlde_demo_applier` 拒絕 unverified replay-derived rows（source filter schema land） | `learning/mlde_demo_applier.py` | E1 → MIT → PA | 1 | G3 | §11 P4 exit |
| R20-P4-T6 | `learning.governance_audit_log` row write per replay advisory（trace-able） | `learning/audit_writer.py` | E1 → MIT → PA | 1 | — | §11 P4 exit |
| R20-P4-T7 | Cost edge ratio gate（≥0.8 阻 LLM/ML 候選 loop） | `learning/replay/cost_gate.py` | E1 → AI-E → PA | 0.5 | G12 | §12 #24 |

**依賴：** T3 → T1 ⫴ T2；T4 ⫴ T7；T5 → T6。
**Phase 總時長：** ~2 sprint。**P4 不阻塞 P3b 完整覆蓋**（只需 P3a T6 calibration writer + verified insert function 即可開工）。

---

### P5 — Agents Monitor Extraction（1 sprint，gated by external entry）

**Entry guard（外部依賴）：** LG-2/3/4 frontend merged + 7d frontend stable。**等於 PA 於 P5 前**確認 LG-2/3/4 真實 IMPL（CLAUDE.md §三 18 Live Blocker #2/#3/#4）已 land。

| Task ID | Name | Files | Owner → Reviewer | Sprint | Gate | Exit |
|---|---|---|---|---|---|---|
| R20-P5-T1 | Agents Monitor 獨立路由抽出（從 Learning Cockpit 5-Agent panel） | `static/agents_monitor/index.html` + `agents_routes.py`（既有 read-only 路由保留，新增 view route） | E1a → A3 → E2 | 1 | — | §11 P5 exit |
| R20-P5-T2 | Learning Cockpit 5-Agent panel 移除 + 90d 重定向通知 | `static/learning_cockpit/sections/agents_panel.html` 刪 + `learning_routes.py` 加 redirect notice | E1a → A3 → E2 | 0.5 | — | §11 P5 exit |
| R20-P5-T3 | `agents_monitor_read_only` regression test（既有 5-Agent API 行為不變）| `tests/ui/test_agents_monitor_read_only.py` | E4 → E2 | 0.5 | — | §12 #21 |

**並行：** T1 ⫴ T2，T3 末段。
**Phase 總時長：** ~1 sprint（觸發後）。

---

### P6 — Bounded Demo A/B Handoff（2 sprint）

**Entry：** P4 deploy + applier source filter schema land + Guardian gate dry-run。

| Task ID | Name | Files | Owner → Reviewer | Sprint | Gate | Exit |
|---|---|---|---|---|---|---|
| R20-P6-T1 | `/api/v1/replay/candidates` POST `demo_candidate` route | `replay_routes.py` extend | E1 → E2 → PA | 1 | — | §12 #20 |
| R20-P6-T2 | Typed confirmation modal（UX subdoc §6 全 9 欄位）| `static/learning_cockpit/sub_tabs/handoff.js` extend | E1a → A3 → E2 | 1 | G10 | §12 #20, UX §6 |
| R20-P6-T3 | Idempotency key + bound validation server-side | `replay_handoff_validator.py` | E1 → E2 → PA | 1 | — | §12 #20 |
| R20-P6-T4 | Applier source guard（verified insert function 接 demo path） | `learning/mlde_demo_applier.py` extend | E1 → MIT → PA | 1 | G4 | §11 P6 exit |
| R20-P6-T5 | `learning.governance_audit_log` per handoff row + replay_experiment_id 反查 | `learning/audit_writer.py` extend | E1 → MIT → PA | 0.5 | — | §11 P6 exit |
| R20-P6-T6 | Reversibility（idempotent revert path） | `replay_handoff_revert.py` | E1 → MIT → PA → PM | 1.5 | — | §11 P6 exit |
| R20-P6-T7 | Live mutation negative test（ensure replay 不能 emit `live_approved`） | `tests/integration/test_replay_no_live_approval.py` | E4 → BB → PA | 1 | — | §12 #14 |
| R20-P6-T8 | 14d gradient deployment + 0 incident KPI 觀察 healthcheck | `helper_scripts/db/passive_wait_healthcheck.py` extend | E4 → PM | 0.5 | — | §11 P6 Business KPI |

**並行：** T1 ⫴ T3 ⫴ T4；T2 跟 T1；T5 ⫴ T6 ⫴ T7；T8 末段。
**Phase 總時長：** ~2 sprint。

---

## §3. 跨 Phase 並行機會 Matrix

| Phase 對 | 並行重疊 task | 條件 |
|---|---|---|
| **P2a ⫴ P2b** | P2a-T8/T9/T10 與 P2b-T1/T2/T3/T4 並行 | P2a-T7 (signer) land 即可（≈ P2a 中段）。runner 可寫 stub 路徑，待 schema 完整再接通。 |
| **P3a ⫴ P3b** | P3a-T6 land 後，P3b-T1/T2/T3/T4 全開工 | 70% 重疊；cell writer (P3b-T6) 等 P3a-T6 寫格式穩定 |
| **P4 ⫴ P3b** | P4-T1/T2/T3 在 P3b-T3/T4/T5 期間開工 | 只需 P3a-T6 writer + verified insert function；P4 不需 cell coverage 完成 |
| **P5 ⫴ P6** | P5-T1/T2 與 P6-T1~T4 並行 | P5 entry 滿足後；不同 surface（agents_monitor vs handoff）|
| **P1 ⫴ P2a** | P1-T2/T3 frontend mock 與 P2a backend 並行 | P0 完成後即可；P1 mock 用假數據 |

---

## §4. Wave / Sprint 整體排程建議

```
Wave 1 (sprint 1):  P0 全 9 task 並行（docs only）
  ├─ R20-P0-T1~T5 (PM/PA/E2): amendment + V### reservation + Guard templates
  ├─ R20-P0-T6/T7 (PA + E1): replay_runner scaffold + Isolated profile cfg gate 設計
  ├─ R20-P0-T8 (PA + E1a): baseline snapshot mechanism 設計
  └─ R20-P0-T9 (QC + E3): indicator sweep kickoff（外部任務派發，wave 2 期間執行）

Wave 2 (sprint 2-3):  P1 UI shell + P2a foundation 起頭
  ├─ R20-P1-T1~T7 (E1a + A3): IA / badges / disabled / mock / regression test
  └─ R20-P2a-T1/T2/T3 (E1 + MIT + PA): 三 schema migration land
  └─ R20-P2a-T4/T5 (E1 + MIT): evidence_tier backfill + ALTER

Wave 3 (sprint 3-5):  P2a 收尾 + P2b 起頭（並行）
  ├─ R20-P2a-T6/T7/T8/T9/T10 (E1 + E2 + PA): role guard + signer + 8 routes + quota + healthcheck
  └─ R20-P2b-T1/T2/T3 (E1 + PA + E2): replay_runner bin + Isolated profile + IntentProcessor 接線
  ⚠️ G6 indicator sweep 必須在 P2b-T3 開工前 PASS

Wave 4 (sprint 5-6):  P2b 收尾 + Compare/Mac
  └─ R20-P2b-T4~T10 (E1 + BB + QC + E4 + E1a)

Wave 5 (sprint 6-8):  P3a + P3b 並行（前置：FUP-2 attribution writer deploy）
  ├─ R20-P3a-T1~T7
  └─ R20-P3b-T1~T6 (P3a-T6 land 後開工)

Wave 6 (sprint 8-10):  P4 advisory（與 P3b 後段並行）
  └─ R20-P4-T1~T7

Wave 7 (待 LG-2/3/4 frontend 完成 + 7d stable):  P5 抽出
  └─ R20-P5-T1~T3

Wave 8 (sprint 10-12):  P6 demo handoff
  └─ R20-P6-T1~T8

Wave 9 (sprint 12-14):  14d gradient observation + KPI healthcheck
```

**總工時估算：** 14-18 個 sprint（含 P5 等待 LG-2/3/4 外部依賴），純本 phase 工時 ~12-14 sprint。

---

## §5. 風險 / Unknowns

### 高風險（PA 須 raise 給 PM）

1. **`replay_runner` 與 `openclaw-engine` crate 共享邊界**：V3 §6.1 寫「May share TickPipeline / IntentProcessor」但未明訂 *哪些 mod*。Wave 3 起 P2b-T1 設計 review 時，PA 必須 sign-off **明確 mod 白名單**（`tick_pipeline` / `intent_processor` / `paper_state` / `strategy/*` / `risk_envelope`）+ **黑名單**（`ipc_server` / `websocket` / `bybit_rest_client@live` / `db_writer` / `governance_hub::lease@acquire`），否則 G7/G8 fail-closed test 會抓不到細粒度違規。

2. **`ReplayProfile::Isolated` cfg gate 雙層複雜度**：P0-T7 設計時需釐清 `cfg(replay_isolated)` 是 **編譯時 feature** 還是 **runtime profile enum**。建議**雙層**：feature flag 排除 dispatch/IPC 模組編譯（避免 binary 帶 live code），runtime enum 控制邏輯分支（避免兩 binary 維護）。風險：feature flag 過多 → CI matrix 爆炸；建議僅 1 個 `replay_isolated` feature。

3. **DB role REVOKE/GRANT 變更時機（P2a-T6）**：撞既有 producer 寫入路徑 → live demo 寫 fail。**部署順序硬性**：(a) verified insert function land + grant 既有 producer EXECUTE → (b) 既有 producer 切換到 function → (c) REVOKE INSERT FROM PUBLIC。三步分 3 個 PR，Wave 3 中段執行；**禁止單 PR 一次 REVOKE**。

4. **`replay.evidence_tier_backfill_report` retrofit 三步**：preflight `SELECT DISTINCT source` 可能撈出 V3 §4.2 allowlist 之外的 source（已知 `dream_engine` / `ml_shadow` / `opportunity_tracker`，但 history 有未知 producer）。風險：classify 卡 weeks。**緩解：** P0-T9 即啟動 PG 撈 distinct source 報 PM，P2a-T4 開工前 classify 完成。

5. **G6 indicator sweep blocker**：P2b 阻塞於 5 strategy 全 PASS 或顯式 exclusion。已知 `bb_breakout` 14d 0 fires + `funding_arb` V2 棄策略，QC + E3 sweep 可能直接 retract 2 策略 → P2b 只能驗 3 策略。**這不是阻塞 P2b**，但 manifest 必須記錄 exclusion list。**Operator 已批 P0-DATA-INDICATOR-SWEEP 5/5 PASS，G6 解封**（input 已給）。

### 中風險

6. **P5 entry 外部依賴**：LG-2/3/4 frontend merged + 7d stable 是 hard date dependency。CLAUDE.md §三 顯示 LG-2/3/4 為 0 行 IMPL，最早 ~05-23 樂觀 / 05-30 中位 / 06-15 悲觀。**P5 無法保證 sprint 排入**；Wave 7 為「事件觸發」非 sprint 推進。

7. **Manifest TTL 30d vs key retention 180d 不一致**：V3 §5 寫 manifest TTL 30d 但 key retention 180d max；含義是 manifest 過期後 180d 內仍可驗 archived signature。P2a-T7 signer 設計需明訂 key version table + lookup path，避免 key rotation 後舊 manifest 全 fail。

8. **Mac fixture baseline 不可重現**：V3 §6.4 寫 `srv/research_notes/replay_fixtures/<date>_demo_baseline.toml` PM-curated。**這個目錄目前不存在**；Wave 1 期間必須由 PM 建立 + sha-pin 流程；否則 Mac smoke 第一個 baseline 就 block。

### 已 unblock

- ✅ **G6 indicator sweep 5/5 PASS**（input 已給，2026-05-03）→ P2b 進入 Wave 3 不卡前置。

---

## §6. E2 重點審查 3 點

PA 點名 E2 在 Wave 2-3 必查：

1. **P2b-T2/T3 cfg gate 雙層 grep**：`grep -nE 'acquire_lease|build_exchange_pipeline|ipc_server|bybit_rest_client.*live'` 在 `replay_runner.rs` 的依賴閉包必須 0；不靠 feature flag 假信任，runtime + unit test 雙驗證。

2. **P2a-T6 verified insert function 不可繞**：`grep -nE 'INSERT INTO learning\.mlde_shadow_recommendations'` 在所有 Python codepath 必須 0 直接 INSERT，全走 `f_insert_evidence_advisory()`；E2 必查 `mlde_demo_applier` / `dream_engine` / `ml_shadow` 三 producer。

3. **P2a-T8 8 routes safe_query 鏡像**：`grep -nE 'await.*pg.*fetch|psycopg' replay_routes.py` 命中項必經 `_safe_query` wrapper 而非 raw await；degraded path 永遠 200 + `{status:degraded}`，**禁** 5xx；E2 跑 PG kill simulation 驗 degrade。

---

## §7. 結論

**派發優先級：** Wave 1 P0 全並行 9 task → Wave 2 P1+P2a Foundation → Wave 3 起進入 backend 重活。
**首要 risk：** Crate 邊界 + DB role 變更時機 + Mac fixture infra 缺失。
**Live blocker 對應：** REF-20 P0-P4 為 LG-2/3/4 + Decision Lease retrofit 之外的 **獨立 track**（不阻塞 18 blocker），但 P5 entry 與 LG-2/3/4 frontend 強耦合。

**PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--ref20_v3_implementation_breakdown.md**
