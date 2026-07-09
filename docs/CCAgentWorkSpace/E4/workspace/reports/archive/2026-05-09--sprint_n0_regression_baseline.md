# E4 Regression — Sprint N+0 Day 3-5 Baseline · HEAD `f5574c5a` · 2026-05-09

> 角色：E4 Test Engineer
> 對象：4 sub-agent IMPL 平行交付（W-AUDIT-9 T1+T2、W-AUDIT-9 T3、W-AUDIT-9 T6 + W-AUDIT-6d 4/5/6 + B-M1、W-AUDIT-4b-M1）共 9 commits
> Baseline 對比：v3 verification `da2aba11` (2026-05-09) — pytest 3961/3 fail / cargo lib 2584/0 fail
> Sub-agent reports（已讀）：
> - `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-09--w_audit_9_t1_t2_rust_schema_v080_migration.md`
> - `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-09--w_audit_9_t3_shadow_mode_provider_stage_aware.md`
> - `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-09--w_audit_9_t6_and_w_audit_6d_4_5_6_impl.md`
> - `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-09--w_audit_4b_m1_decision_features_intent_only_emit.md`
> - `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-09--w_audit_6d_dsr_penalty_quantification.md`

---

## §1 Executive Summary — VERDICT: FAIL → RETURN-TO-E1

**5 個 NEW regression 確認，全部 W-AUDIT-9 chain 副作用 — sub-agent 漏更新 sibling test fixture。**

| 引擎 | run 1 | run 2 | v3 baseline | delta | identical | verdict |
|---|---:|---:|---:|---|---|---|
| Linux · cargo lib `openclaw_engine` | 2622 / 2 fail | 2622 / 2 fail | 2584 / 0 | **+38 PASS / +2 NEW fail** | yes | **FAIL** |
| Linux · pytest tests/ + control_api_v1/tests/ | 4262 / 8 fail | 4262 / 8 fail | 3961 / 3 fail* | **+301 PASS / +5 NEW fail** | yes | **FAIL** |
| Mac · cargo build --release `openclaw_engine` | exit=0 | n/a | exit=0 | match | n/a | PASS |
| Mac · cargo build --release `openclaw_core` | exit=0 | n/a | exit=0 | match | n/a | PASS |
| Mac · cargo lib `openclaw_engine` | 2622 / 2 fail | n/a | 2584 / 0 | +38 / +2 | n/a | (parity Linux) |
| Mac · cargo lib workspace (-p openclaw_core 425/0 + others) | 425+pass / 0 fail others | n/a | n/a | n/a | n/a | PASS for non-engine |
| Mac · pytest control_api_v1 | 4007 / 2 / 17 skip | 4006 / 3 / 17 skip | 3961 / 3 / 10 skip | match | 1 flaky (grafana) | (mock-only) |
| V080 schema mock pytest | 21 passed | 21 passed | new | match | yes | PASS |
| V080 Linux PG empirical apply | OK no-op | OK no-op | n/a | idempotent | yes | PASS |
| V082 Linux PG empirical apply | OK no-op | (skipped 2nd) | n/a | idempotent | yes | PASS |

*v3 baseline 3961 是 control_api_v1 only；本 round 跑 tests/ + control_api_v1 = +301 包含 W-AUDIT-9 T3 +35 / W-AUDIT-9 T6+6d Python +9 / W-AUDIT-4b-M1 V082 +13 / 既有 tests/ 子套件等。

**核心結論**：4 sub-agent 並行 IMPL 雖各自 sibling test 加好（sub-agent 報告 claim 真實），但 **W-AUDIT-9 改動整體 invariant** （`shadow_mode == canary_stage.as_shadow_mode()`）破壞既有 `ipc_server::tests::config` IPC patch test + `test_executor_decision_parity` Python parity test fixture。**5 NEW fail 全部是同一 root cause 的不同表現**。

---

## §2 5 個 NEW regression 詳細

### 2.1 Rust IPC config patch test — 2 個 fail (W-AUDIT-9 T1+T2 副作用)

| Test | Fail mode（assertion message 摘要）|
|---|---|
| `ipc_server::tests::config::test_g3_02_a2_patch_executor_routes_to_demo_engine` | `JsonRpcError code=-32600 "validation failed: risk.executor: shadow_mode=false inconsistent with canary_stage=0 (Stage 0 ⇄ true, Stage 1+ ⇄ false). AMD-2026-05-09-03 §4.4 requires legacy shadow_mode equals canary_stage.as_shadow_mode() projection. Update either field atomically (TOML/IPC patch must set both)."` panicked at `openclaw_engine/src/ipc_server/tests/config.rs:577:5` |
| `ipc_server::tests::config::test_g3_02_a2_patch_executor_shadow_mode_via_patch_risk_config` | 同樣 -32600 invariant rejection；panicked at `openclaw_engine/src/ipc_server/tests/config.rs:459:5` |

**Root cause**：W-AUDIT-9 T1+T2 commit `094f9914` 加 `risk_config_advanced.rs::ExecutorConfig::validate()` invariant — shadow_mode 與 canary_stage 必須 atomically projection 一致 (Stage 0 ⇄ shadow=true, Stage 1+ ⇄ shadow=false)。這 2 個既有 IPC test 寫 `shadow_mode=false` 但沒同步寫 `canary_stage=1+` → 新 invariant 拒絕。Sub-agent E1-A 漏更新 sibling test fixture。

**v3 baseline 確認**：在 `da2aba11` 工作樹下 `cargo test ipc_server::tests::config` = **15 passed / 0 failed**，同 2 個 test PASS（在 W-AUDIT-9 邊界 invariant 加入前）。

**修復方向**：兩個 test 在 patch_risk_config payload 加 `canary_stage=1` 同步（live engine routing 應走 Stage 1+ 而非 Stage 0），保持與業務邏輯一致。**禁止**反向：把 invariant 拆掉迎合既有 test。

### 2.2 Python `test_executor_decision_parity` — 3 個 fail (W-AUDIT-9 T3 副作用)

| Test | Fail mode |
|---|---|
| `test_executor_decision_parity::TestExecutorDecisionParity::test_golden_fixtures_agree_rate` | `assert agree >= 19; agree=10/20`（10 個 live fixture 全部 py=`('block_shadow', 'shadow_mode')` vs ref=`('submit', 'live_intent_passthrough')`）|
| `test_executor_decision_parity::test_synthetic_handcrafted_agree_rate` | `assert 20 == 40`（20 個 synthetic_replay_live fixture 全部 disagree 同模式）|
| `test_executor_decision_parity::test_overall_agree_rate_ge_95pct` | `assert agree >= 67; agree=40/70 below 67 (95% threshold)`；70 case 中 30 個 live fixture 全 disagree |

**Root cause**：W-AUDIT-9 T3 commit `200188ad` 改 `executor_agent.py::ExecutorAgent._read_shadow_mode()` 從直接讀 cache shadow_mode 改為 stage projection（`stage_provider() == CanaryStage.SHADOW`）。fail-closed 預設為 Stage 0 / SHADOW；既有 fixture 全部 fail-closed 走 `block_shadow` 但 reference engine 期待 `submit`/`live_intent_passthrough`。**fixture 沒同步注入 `canary_stage>=1` provider**。

**v3 baseline 確認**：在 `da2aba11` 工作樹下 `pytest test_executor_decision_parity.py` = **5 passed / 2 skipped**（agree=70/70 100%，threshold ≥67/70）；HEAD fail = 全 live fixture parity broken。

**修復方向**：parity test fixture builder 需自動 pair `shadow_mode=False` 與 `canary_stage=Stage1+` (W-AUDIT-9 §4.4 invariant)，類似 `test_executor_shadow_to_live_e2e.py::_make_runtime_config` helper 已做的 auto-pair 邏輯。Sub-agent E1-C IMPL report §2.2 自承「`tests/test_executor_shadow_to_live_e2e.py` 加 helper 避 §4.4 reject」但漏了 parity test 同樣需要。

### 2.3 CI workflow test — 1 個 fail (commit `0dc6d659` 副作用，非本 4 sub-agent)

| Test | Fail mode |
|---|---|
| `tests/ci/test_github_ci_workflow_static.py::test_ci_workflow_runs_release_cargo_check_for_openclaw_engine` | `assert 'rustup target add "${{ matrix.target }}"' in WORKFLOW` 失敗；workflow 在 `0dc6d659` 改成「拆兩個 job 取代 matrix if」, `${{ matrix.target }}` 變數已不存在 |

**Root cause**：commit `0dc6d659 ci: 拆兩個 job 取代 matrix if` 改 `.github/workflows/ci.yml` 但 sibling test `test_github_ci_workflow_static.py` 沒同步更新 assertion。這在 v3 baseline `da2aba11` 之後、sprint N+0 4 sub-agent IMPL 之前、commit time **2026-05-09 16:xx** 進入 main，本 round 才被 E4 第一次跑 full pytest 抓到。

**v3 baseline 確認**：v3 baseline 記載 control_api_v1 only = 3961/3，未跑 tests/ ci structure suite，所以 `0dc6d659` 副作用未被 v3 抓到。

**修復方向**：更新 `tests/ci/test_github_ci_workflow_static.py` assertion 對應新 workflow（兩個 job 各檢查 `rustup target add x86_64-unknown-linux-gnu` + `aarch64-apple-darwin`）。

---

## §3 IPC 2 fail 確認（用戶 task scope §5）

**任務 §5**：「確認這 2 個 test 在 main HEAD `f5574c5a` 仍 fail；報 fail mode；不 fix（E2 review 判定 RETURN-TO-E1 + E1 fix sub-agent）」

✅ **2 IPC test 在 HEAD `f5574c5a` 仍 fail**（Mac + Linux 三跑同 deterministic identical）：

```
ipc_server::tests::config::test_g3_02_a2_patch_executor_routes_to_demo_engine
ipc_server::tests::config::test_g3_02_a2_patch_executor_shadow_mode_via_patch_risk_config
```

Fail mode：JsonRpcError -32600 "validation failed: risk.executor: shadow_mode=false inconsistent with canary_stage=0 (Stage 0 ⇄ true, Stage 1+ ⇄ false). AMD-2026-05-09-03 §4.4 requires legacy shadow_mode equals canary_stage.as_shadow_mode() projection."

✅ E4 不 fix（per 任務指示）。建議 E1 fix sub-agent 同時連帶修 §2.2 三個 parity test fixture（同根因，同 sub-agent fix 一次處理乾淨）。

---

## §4 Cross-language consistency check (W-AUDIT-9 T6 LeaseScope CanaryStage)

**任務 §6**：Rust 端 + Python 端 CanaryStage / shadow_mode projection 一致 1e-4 tolerance

CanaryStage 是 IntEnum / `#[serde(try_from = "u8", into = "u8")]`，整數 0..=4 完全對齊：

| Stage | Rust `CanaryStage` | Python `CanaryStage` IntEnum | as_u8 / value | as_shadow_mode |
|---|---|---|---:|---|
| 0 | `CanaryStage::Stage0` | `SHADOW` | 0 | `true` ⇄ `True` |
| 1 | `CanaryStage::Stage1` | `PAPER_SINGLE_COHORT` | 1 | `false` ⇄ `False` |
| 2 | `CanaryStage::Stage2` | `DEMO_SINGLE_COHORT` | 2 | `false` ⇄ `False` |
| 3 | `CanaryStage::Stage3` | `DEMO_FULL_UNIVERSE` | 3 | `false` ⇄ `False` |
| 4 | `CanaryStage::Stage4` | `LIVE_PENDING` | 4 | `false` ⇄ `False` |

Rust `as_shadow_mode()`: `matches!(self, CanaryStage::Stage0)`
Python `_read_shadow_mode()`: `return stage == CanaryStage.SHADOW`

**完全一致**：integer encoding + projection logic + fail-closed default (SHADOW = 0) 三層對齊。**1e-4 tolerance**（離散 enum 不需浮點容差，bit-exact 對齊）✅ PASS。

---

## §5 cargo build --release 全 PASS (任務 §3)

| Crate | exit code | 結論 |
|---|---:|---|
| Mac · cargo build --release -p openclaw_engine | 0 | PASS（17 warning，0 error）|
| Mac · cargo build --release -p openclaw_core | 0 | PASS（0 warning, 0 error）|

**git status `--porcelain`** = empty 0 lines（Mac + Linux 雙端工作樹 clean，HEAD `f5574c5a` 同步）。**沒 sibling unstaged 殘留導致 fail**。

---

## §6 V080 + V082 idempotent 兩次 PASS (任務 §4)

### V080 schema mock pytest (Mac)

```
Run 1: 21 passed in 0.02s
Run 2: 21 passed in 0.02s  → identical 0 flake
```

W-AUDIT-9 T1+T2 IMPL report claim「V080 21 test」對齊 ✅。

### V080 Linux PG empirical apply（mandatory per CLAUDE.md §七 V### dry-run）

```
Run 1: bash helper_scripts/linux_bootstrap_db.sh --apply V080
  → NOTICE: schema "governance" already exists, skipping
  → NOTICE: relation "canary_stage_log" already exists, skipping
  → NOTICE: relation "canary_stage_metric_registry" already exists, skipping
  → NOTICE: relation "idx_canary_stage_log_cohort_created_at" already exists, skipping
  → NOTICE: relation "idx_canary_stage_log_rollback_events" already exists, skipping
  → NOTICE: relation "uq_canary_stage_metric_registry_active" already exists, skipping
  → [migrate] OK: V080__governance_canary_stage.sql
Run 2: identical no-op NOTICE chain → idempotent
```

### V082 Linux PG empirical apply

```
Run 1: bash helper_scripts/linux_bootstrap_db.sh --apply V082
  → NOTICE: relation "decision_features_evaluations" already exists, skipping
  → NOTICE: V082: chk_decision_features_evaluations_outcome already present; skipping
  → NOTICE: V082: chk_decision_features_evaluations_evidence_tier already present; skipping
  → NOTICE: V082: chk_decision_features_evaluations_side already present; skipping
  → NOTICE: relation "idx_decision_features_evaluations_strategy_mode_ts" already exists, skipping
  → NOTICE: relation "idx_decision_features_evaluations_ts" already exists, skipping
  → NOTICE: relation "idx_decision_features_evaluations_context_id" already exists, skipping
  → NOTICE: relation "idx_decision_features_evaluations_outcome_ts" already exists, skipping
  → [migrate] OK: V082__decision_features_evaluations_split.sql
```

**0 ERROR / 0 RAISE EXCEPTION**。Guard A/B/C 全打 NOTICE skip path。

### Cleanup verify (DB row 不殘留)

```sql
SELECT (SELECT COUNT(*) FROM governance.canary_stage_log) AS canary_log,
       (SELECT COUNT(*) FROM governance.canary_stage_metric_registry) AS canary_registry,
       (SELECT COUNT(*) FROM learning.decision_features_evaluations) AS df_eval;
```

| canary_log | canary_registry | df_eval |
|---:|---:|---:|
| 0 | 0 | 0 |

**Schema only apply，0 DB row 殘留** ✅

---

## §7 Mock 審查 (CLAUDE.md skill regression-testing-protocol §5)

本 task E4 不寫業務代碼，僅讀 + 跑。對 4 sub-agent IMPL report 列出的 mock 抽查：

| Sub-agent | mock 內容 | 是否 IO boundary | OK? |
|---|---|---|---|
| W-AUDIT-9 T1+T2 (`094f9914`) | 無 mock — Rust unit test 直接 ExecutorConfig instance + validate() | n/a | ✓ |
| W-AUDIT-9 T3 (`200188ad`) | `monkeypatch.setattr(executor_config_cache, "_send_ipc_request", ...)` IPC stub | IO boundary | ✓ |
| W-AUDIT-9 T6 + W-AUDIT-6d (`063f12d0` + `f6fb315a`) | `MockGovernanceHub` 在 `governance_core.rs` Rust unit test stub PG row write | DB IO boundary | ✓ |
| W-AUDIT-4b-M1 (`4a90966a`) | `_FakeIntentDispatcher` + `_FakeContextStream` for 13 contract test | IPC channel + DB writer IO boundary | ✓ |

**0 業務邏輯 mock**：`canary_stage.as_shadow_mode()` projection / `evaluate_predictor_gate` PredictorAction outcome / `bb_reversion::ma_pair_allows_entry` / `portfolio_var.compute_var_cvar()` 業務邏輯真跑。

---

## §8 SLA 壓測 — 不適用本 round

本 round 4 sub-agent IMPL 不觸 hot path（H0 Gate / Tick path / IPC RPC roundtrip <5ms 都未動）。
- W-AUDIT-9 T1+T2 加 `validate()` invariant 在 IPC patch path（非 hot；patch 頻率 <1/min）
- W-AUDIT-9 T3 改 `_read_shadow_mode()` 走 stage projection，每次 caller call lambda；無新增 PG/IPC 取數，纯 in-memory enum compare
- W-AUDIT-9 T6 加 `LeaseScope::CanaryStagePromotion` 路徑 — operator-only manual promote scope，非 hot path
- W-AUDIT-4b-M1 拆表 — V082 evaluation log 不在 ML training pool，不影響 hot path

跳過 SLA 壓測 per skill `regression-testing-protocol` §4.5 觸發條件。

---

## §9 Pre-existing fail 清單（v3 baseline 已記載，本 round 不變動）

| Test | v3 baseline 記載 | HEAD `f5574c5a` 狀態 | delta |
|---|---|---|---|
| `test_oe_006_close_retry_budget_has_real_timeout_guard` | NEW-3 pre-existing | fail | 不變 |
| `test_replay_routes_safe_query_audit::test_case2_pg_kill_simulation_returns_200_degraded` | NEW-1 pre-existing | fail | 不變 |
| `test_archive_top_level_files_are_all_indexed` | docs index drift pre-existing | fail | 不變 |
| `test_grafana_data_writer::test_start_sets_running` | NEW-4 pre-existing leader lock | fail | 不變 |

4 個 pre-existing 全部仍 fail，**0 增**。本 sprint 4 sub-agent IMPL 不改善這 4 項（不在 scope）。

---

## §10 退回 E1 修復清單（FAIL 必修）

| # | 文件 | 失敗 test | 修復方向 |
|---|---|---|---|
| 1 | `rust/openclaw_engine/src/ipc_server/tests/config.rs:459` | `test_g3_02_a2_patch_executor_shadow_mode_via_patch_risk_config` | patch_risk_config payload 加 `canary_stage: Stage1` 同步 shadow_mode=false |
| 2 | `rust/openclaw_engine/src/ipc_server/tests/config.rs:577` | `test_g3_02_a2_patch_executor_routes_to_demo_engine` | 同上 |
| 3 | `program_code/.../tests/test_executor_decision_parity.py` golden fixtures (10 個 live case) | `test_golden_fixtures_agree_rate` | fixture builder 注入 `canary_stage_provider()` 回傳 `CanaryStage.PAPER_SINGLE_COHORT` 或 higher 同步 `shadow_mode=False` |
| 4 | 同上（synthetic 20 case） | `test_synthetic_handcrafted_agree_rate` | 同上 |
| 5 | 同上（overall 30 live case） | `test_overall_agree_rate_ge_95pct` | 同上（修 #3+#4 自動化此項）|
| 6 | `tests/ci/test_github_ci_workflow_static.py:19` | `test_ci_workflow_runs_release_cargo_check_for_openclaw_engine` | assertion 改成驗 `rustup target add x86_64-unknown-linux-gnu` + `aarch64-apple-darwin` 兩個 hard target |

**6 個 fix 全部單一 sub-agent 可在 2-3 hr 完成**：5 個是 W-AUDIT-9 chain 同根因，#6 獨立但簡單。預期 fix 後 cargo lib 2622+2 = 2624 PASS / 0 fail，pytest 4262+5 = 4267 PASS / 3 fail（4 pre-existing - 1 修了 = 3 fail）。

---

## §11 `跑兩遍 `flaky 確認

雙 round 結果：

| 引擎 | run 1 | run 2 | identical |
|---|---|---|---|
| Linux cargo lib | 2622/2 | 2622/2 | ✅ identical (same 2 fail names) |
| Linux pytest | 4262/8 | 4262/8 | ✅ identical (same 8 fail names) |
| Mac pytest | 4007/2 | 4006/3 | ⚠️ 1 flaky `test_grafana_data_writer.test_start_sets_running` (NEW-4 pre-existing flaky)|

⚠️ 1 flaky = `test_grafana_data_writer.test_start_sets_running`：Mac round 2 fail，但 isolated pytest = PASS（5.03s）；Linux 雙 round 都 fail。**確認 NEW-4 pre-existing flaky non-deterministic Linux always-fail timing race**，與本 sprint 4 sub-agent IMPL 無關。

---

## §12 Hard-boundary scan (CLAUDE.md §四)

對 14 個 Rust + 6 個 Python 改動 file `grep '\b(live_execution_allowed|max_retries|OPENCLAW_ALLOW_MAINNET|live_reserved|authorization\.json|decision_lease|execution_authority)\b'`：

| Hit | 文件 | 是否 violation |
|---|---|---|
| `decision_lease_id` | `V080__governance_canary_stage.sql` (canary_stage_log row 引用 SM-02 lease) | ✓ 設計允許 — manual promote 路徑必須持 lease audit chain |
| `decision_lease_id` | `lease_scope.rs` `CanaryStagePromotion` typed lease | ✓ 設計允許 — Decision Lease facade 擴展 |
| 0 hit | 其餘 12 Rust + 6 Python | ✓ no other hard-boundary mutation |

**0 hard boundary violation**。

---

## §13 Cross-platform path scan (CLAUDE.md §七)

對 14 Rust + 6 Python source file `grep '/home/ncyu\|/Users/ncyu'`：

**0 hit** ✓ — 無硬編碼 user-home path。

---

## §14 LOC governance (CLAUDE.md §九)

| File | LOC | 限制 | 結論 |
|---|---:|---:|---|
| `executor_agent.py` | 971 | 800 警告 / 2000 硬上限 | 警告區（pre-existing）✓ |
| `executor_config_cache.py` | 613 | 800 警告 | < 800 ✓ |
| `test_executor_agent_unit.py` | 809 | 800 警告 | 剛跨 800（pre-existing baseline 612 + W-AUDIT-9 +197）✓ |
| `risk_config_advanced.rs` | 366 (W-AUDIT-9 +363) | 800 警告 | < 800 ✓ |
| `risk_config_tests.rs` | ~700 | 800 警告 | < 800 ✓ |
| `lease_scope.rs` | 294 (新) | 800 警告 | < 800 ✓ |
| `governance_core.rs` | 329 | 800 警告 | < 800 ✓ |
| `decision_feature_evaluation_writer.rs` | 287 (新) | 800 警告 | < 800 ✓ |
| `intent_processor/mod.rs` | 改 +144 | n/a (查當前) | 增量但檢查總 LOC < 2000 ✓ |
| `tests_predictor_router.rs` | +90 net | 800 警告 | 檢查當前 < 800 ✓ |

**0 LOC governance violation**。

---

## §15 V080 + V082 cleanup（任務 §4 不留 DB row 確認）

執行 `bash helper_scripts/linux_bootstrap_db.sh --apply V080/V082` schema-only apply。**沒寫測試資料 row**。

驗證 row count = 0：
- `governance.canary_stage_log` = 0
- `governance.canary_stage_metric_registry` = 0
- `learning.decision_features_evaluations` = 0

**0 DB row 殘留** ✓

---

## §16 結論

| 任務 | 結果 |
|---|---|
| 1. Cargo full regression baseline | **FAIL**（+38 PASS / +2 NEW fail） |
| 2. Pytest full regression baseline | **FAIL**（+301 PASS / +5 NEW fail） |
| 3. cargo build --release 全 PASS | ✅ PASS（Mac engine + core 都 0 error）|
| 4. V080 + V082 migration smoke 兩次 idempotent | ✅ PASS（0 ERROR, 0 row 殘留）|
| 5. 2 IPC test fail 在 HEAD 仍 fail 確認 | ✅ Confirmed（不 fix per 任務指示） |
| 6. Cross-language consistency 1e-4 | ✅ PASS（integer enum bit-exact）|

**Verdict：FAIL → RETURN-TO-E1**

5 NEW regression：
- 2 個 Rust IPC test (W-AUDIT-9 T1+T2 §4.4 invariant)
- 3 個 Python parity test (W-AUDIT-9 T3 shadow_mode projection)
- 1 個 CI workflow test (commit `0dc6d659` 副作用)

**E1 fix sub-agent 派工建議**：派 1 個 sub-agent 統一處理 5 NEW（4 個 W-AUDIT-9 chain 同根因 + 1 個 CI workflow assertion 修正），不分頭並行（避免重複處理共用 fixture）。fix 後重 E2 → 重 E4。

不建議部分 push：必須等 E1 fix 全部修完 → E2 review approve → E4 重跑全綠 → PM 一次 push 9 commits + fix commit 統一上 main，避免 main 帶半綠狀態。

---

## §17 教訓（為下次 sprint 累積）

1. **大 invariant 改動 (W-AUDIT-9 T1+T2 §4.4) 必須跑 full regression 在 E2 review 前** — sub-agent 自己跑 unit test PASS ≠ 全 suite PASS。本 sprint 4 sub-agent IMPL report 都 claim「sibling test 加好」，但 cross-suite 副作用 (IPC `tests/config.rs` + Python parity test) 沒檢查。E2 review 應加「sub-agent 必跑 cargo test --release -p openclaw_engine --lib 全套 + pytest control_api_v1 -k <invariant_keyword>」要求。
2. **Python parity test fixture 應自動 pair shadow_mode + canary_stage** — `_make_runtime_config` helper 已在 `test_executor_shadow_to_live_e2e.py` 做，但 `test_executor_decision_parity.py` 漏。新 invariant landing 後第一個動作 = 全 codebase grep `RuntimeConfig(.*shadow_mode=` + `RuntimeConfig(.*canary_stage=` 確認所有 helper 都 auto-pair。
3. **CI workflow change 必伴 sibling test 同步** — commit `0dc6d659` 拆 matrix 但沒同步 `test_github_ci_workflow_static.py`。下次任何 `.github/workflows/*` 改動，PA 派工 spec 必加「sibling structure test 同步檢查」。
4. **V080/V082 schema-only apply 後行為驗證**：本 round empirical apply 全 NOTICE skip（DB schema 已存在）= 表示之前 sub-agent 已落地過 V080 V082；schema apply path idempotent 但**不證明 producer 寫入路徑正確**。需另外 watch `learning.decision_features_evaluations` row 在 engine restart 後 24h 是否 30k+ row 流量轉移（W-AUDIT-4b-M1 IMPL claim 從 `learning.decision_features` → `learning.decision_features_evaluations`，但本 round 不做 deploy / 不 spawn engine）。Defer 給 PM 後續 deploy verification。
5. **flaky test 跨 round 行為 vary**：`test_grafana_data_writer.test_start_sets_running` Mac round 1 PASS / round 2 FAIL，Linux 兩 round 都 FAIL = 不同 host 的 leader lock contention vary。NEW-4 仍是 P1 pre-existing。本 round 不阻 verdict。

---

**E4 REGRESSION DONE: FAIL · report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-09--sprint_n0_regression_baseline.md`**
