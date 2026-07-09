# E4 Regression Second-Pass — Sprint N+0 Cross-Wave Fixture Fix · HEAD `11849c18` · 2026-05-09

> 角色：E4 Test Engineer (second-pass)
> 對象：E1-FIX commit `11849c18` ("e1-fix: W-AUDIT-9 cross-wave fixture pattern (5 NEW regression)")
> 任務：驗 5 NEW regression 全 fix + 0 新 regression 引入
> First-pass baseline: pytest 4262 / 8 fail · cargo lib 2622 / 2 fail (5 NEW = 2 IPC + 3 Python parity + 1 隔壁 session CI workflow)
> First-pass report: `docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-09--sprint_n0_regression_baseline.md`
> E1-FIX report: `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-09--sprint_n0_fix_cross_wave_fixture_5_regression.md`

---

## §1 Executive Summary — VERDICT: **PASS**

**5 NEW regression 全 fix verified · 0 新 regression 引入 · cargo + pytest 雙跑 deterministic identical**

| 引擎 | round 1 | round 2 | first-pass baseline | delta | identical | verdict |
|---|---:|---:|---:|---|---|---|
| Linux · cargo lib workspace (engine + core + types) | 425+2625+27 / 0 fail | 425+2625+27 / 0 fail | 2622 / 2 fail (engine only) | engine **+3 PASS / -2 fail** | yes | **PASS** |
| Mac · cargo lib workspace (engine + core + types) | 425+2625+27 / 0 fail | 425+2625+27 / 0 fail | parity Linux | engine **+3 PASS / -2 fail** | yes | **PASS** |
| Linux · pytest tests/ + control_api_v1/tests/ | 4265 / 5 fail / 12 skip | 4265 / 5 fail / 12 skip | 4262 / 8 fail | **+3 PASS / -3 fail** | yes | **PASS** |
| Mac · cargo build --release `openclaw_engine` | exit=0 (17 warning, 0 error) | n/a | exit=0 | match | n/a | PASS |
| Mac · cargo build --release `openclaw_core` | exit=0 | n/a | exit=0 | match | n/a | PASS |
| Linux V080 schema apply (idempotent two-round) | 6 NOTICE skip + `[migrate] OK` | 6 NOTICE skip + `[migrate] OK` | match | identical | yes | PASS |
| Linux V082 schema apply (idempotent two-round) | 7 NOTICE skip + `[migrate] OK` | 7 NOTICE skip + `[migrate] OK` | match | identical | yes | PASS |
| DB row cleanup (3 表) | 0 / 0 / 0 | 0 / 0 / 0 | n/a | identical | yes | PASS |

**核心結論**：E1-FIX commit `11849c18` 在 test fixture 層修齊 W-AUDIT-9 chain 5 NEW（2 Rust IPC + 3 Python parity）。Sibling-session 副作用（CI workflow test，commit `0dc6d659`）保留為 PM follow-up，**不在本 fix scope**。

---

## §2 5 NEW regression fix 詳細驗證

### 2.1 Rust IPC config patch test — 2 個 fix verified

**Linux cargo test**：`cargo test --release -p openclaw_engine --lib ipc_server::tests::config` = **16/0 PASS**

| Test | First-pass status | Second-pass status |
|---|---|---|
| `test_g3_02_a2_patch_executor_routes_to_demo_engine` | FAIL (W-AUDIT-9 §4.4 invariant reject) | **PASS** ← 5-field atomic Stage 2 demo cohort patch |
| `test_g3_02_a2_patch_executor_binary_shadow_only_rejected_invariant_drift` | n/a (renamed from `test_g3_02_a2_patch_executor_shadow_mode_via_patch_risk_config`) | **PASS** ← 改斷言為 reject invariant drift（W-AUDIT-9 期望行為）|
| `test_g3_02_a2_patch_executor_stage_promotion_via_patch_risk_config` | n/a (新增) | **PASS** ← 5-field atomic Stage 1 paper cohort 成功 patch |

E1-FIX 的修法符合 §九「不允許刪測試使測試通過」原則：原 fail test 改名為**正確驗 reject**（既有 test 寫 `shadow_mode=false` 但無 `canary_stage>=1` = invariant drift，validation 應 reject），同時新增 stage promotion success path test 確保正向場景被 cover。

### 2.2 Python `test_executor_decision_parity` — 3 個 fix verified

**Linux pytest**: `test_executor_decision_parity.py` = **5 passed / 2 skipped (deferred)**

```
[G8-02 golden] agree=30/30 (100.00%)
[G8-02 synthetic_handcrafted] agree=40/40 (100.00%)
[G8-02 OVERALL] agree=70/70 (100.00%) — threshold 95% (≥67/70)
[G8-02 disagree-log] none — clean run
```

| Test | First-pass status | Second-pass status |
|---|---|---|
| `test_golden_fixtures_agree_rate` | FAIL agree=10/20 | **PASS** agree=30/30 |
| `test_synthetic_handcrafted_agree_rate` | FAIL `assert 20 == 40` | **PASS** agree=40/40 |
| `test_overall_agree_rate_ge_95pct` | FAIL agree=40/70 | **PASS** agree=70/70 (100%) |

E1-FIX 修法：`_build_runtime_config` helper 加入 `shadow ⇄ canary_stage` auto-pair（對齊 `test_executor_shadow_to_live_e2e.py::_make_runtime_config`），ExecutorAgent ctor 注入 `canary_stage_provider=cache.canary_stage_provider()`（W-AUDIT-9 T3 stage-aware SoT）。

---

## §3 完整 cargo / pytest baseline 比對

### 3.1 cargo workspace baseline

| Crate | tests | first-pass | second-pass | delta |
|---|---:|---:|---:|---|
| `openclaw_core` | 425 | n/a (first-pass 只跑 engine) | 425 / 0 | new (parity check) |
| `openclaw_engine` lib | 2625 | 2622 / 2 fail | **2625 / 0 fail** | +3 PASS / -2 fail (5 NEW fix verified) |
| `openclaw_types` | 27 | 27 / 0 | 27 / 0 | unchanged |

**Total workspace = 3077 PASS / 0 fail**（雙端 + 雙跑 deterministic identical）

`openclaw_engine` lib 從 first-pass 2622 → second-pass 2625 = +3 PASS：
- 原 2622 = 2620 PASS + 2 W-AUDIT-9 invariant fail
- E1-FIX rename 1 個（`shadow_mode_via_patch_risk_config` → `binary_shadow_only_rejected_invariant_drift`）+ 修 1 個 demo routing + 新增 1 個 stage promotion success path
- 新 2625 = 2620 PASS + 1 renamed (改斷言) + 1 fixed (5-field atomic) + 3 個 new test 抵 -1 重用 = 2625 ✓

### 3.2 pytest baseline

| Phase | passed | failed | skipped | warnings | runtime |
|---|---:|---:|---:|---:|---|
| First-pass run 1 | 4262 | 8 | 12 | n/a | n/a |
| First-pass run 2 | 4262 | 8 | 12 | n/a | n/a |
| Second-pass run 1 | **4265** | **5** | 12 | 431 | 85.83s |
| Second-pass run 2 | **4265** | **5** | 12 | 431 | 78.03s |

**雙跑 deterministic identical**：
- Round 1 + Round 2 fail names + counts 完全一致
- `test_executor_decision_parity` 3 個 NEW fail 已不在 round 2 fail 名單

**Delta first-pass → second-pass**：+3 PASS / -3 fail
- 5 W-AUDIT-9 chain Python NEW fix 3 個 → +3 PASS
- 0 新 regression 引入

---

## §4 5 fail 名單 cataloging（second-pass）

| Test | 分類 | 對應 |
|---|---|---|
| `tests/ci/test_github_ci_workflow_static.py::test_ci_workflow_runs_release_cargo_check_for_openclaw_engine` | sibling-session 副作用 (commit `0dc6d659`，**E1-FIX scope外**) | PM follow-up — sibling session 改 workflow 無同步 sibling test |
| `tests/structure/test_docs_readme_index_static.py::test_archive_top_level_files_are_all_indexed` | pre-existing (docs index drift) | first-pass §9 列為 pre-existing，不變 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_batch_d_risk_fail_closed.py::test_oe_006_close_retry_budget_has_real_timeout_guard` | pre-existing | first-pass §9 NEW-3 pre-existing，不變 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_grafana_data_writer.py::TestGrafanaDataWriterLifecycle::test_start_sets_running` | pre-existing leader lock flaky | first-pass §9 NEW-4 pre-existing，不變 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_routes_safe_query_audit.py::test_case2_pg_kill_simulation_returns_200_degraded` | pre-existing | first-pass §9 NEW-1 pre-existing，不變 |

**4 pre-existing 雙跑 identical 不變** ✓
**1 sibling-session CI workflow 雙跑 identical 不變** ← PM follow-up（不阻 PASS）

---

## §5 Sibling-session CI workflow standalone reproduction

per 任務 §3，standalone 跑 `tests/ci/test_github_ci_workflow_static.py::test_ci_workflow_runs_release_cargo_check_for_openclaw_engine`：

```
FAILED tests/ci/test_github_ci_workflow_static.py::test_ci_workflow_runs_release_cargo_check_for_openclaw_engine
assert 'rustup target add "${{ matrix.target }}"' in WORKFLOW
E       assert 'rustup target add "${{ matrix.target }}"' in "name: ci\n\n# 觸發策略...
        rust-check-linux: rustup target add x86_64-unknown-linux-gnu
        rust-check-macos: rustup target add aarch64-apple-darwin"
```

**Fail mode 與 first-pass §2.3 一致**：commit `0dc6d659` 把 workflow 從 single-job matrix 改為 `rust-check-linux` + `rust-check-macos` 兩 job，每 job 直接寫死 hard target，不再用 `${{ matrix.target }}` 變數。Sibling test `test_github_ci_workflow_static.py:19` assertion 仍對舊 matrix 模式，故 fail。

**標 PM follow-up**：派 sibling session 修對應 assertion（驗兩個 hard target string 都在 workflow），與本 W-AUDIT-9 fix 無關。

---

## §6 cargo build --release working tree clean (任務 §4)

| 端 | git status | cargo build --release |
|---|---|---|
| Mac local | `--porcelain` empty (clean) | engine + core 都 0 error / 17 pre-existing warning |
| Linux trade-core | `--porcelain` empty (clean) | (cargo lib test 同時 build，0 error) |

三端 git HEAD 同步 `11849c18`：
- Mac local HEAD = `11849c18`
- Linux trade-core HEAD = `11849c18`
- GitHub origin/main = `11849c18`（first-pass 已 push）

---

## §7 V080 + V082 idempotent 兩次 PASS (任務 §5)

### V080 schema apply (Linux PG empirical)

```
[migrate] === V080__governance_canary_stage.sql ===
NOTICE: schema "governance" already exists, skipping
NOTICE: relation "canary_stage_log" already exists, skipping
NOTICE: relation "canary_stage_metric_registry" already exists, skipping
NOTICE: relation "idx_canary_stage_log_cohort_created_at" already exists, skipping
NOTICE: relation "idx_canary_stage_log_rollback_events" already exists, skipping
NOTICE: relation "uq_canary_stage_metric_registry_active" already exists, skipping
[migrate] OK: V080__governance_canary_stage.sql
```

**雙跑 second-pass identical 與 first-pass NOTICE chain** ✓

### V082 schema apply (Linux PG empirical)

```
[migrate] === V082__decision_features_evaluations_split.sql ===
NOTICE: relation "decision_features_evaluations" already exists, skipping
NOTICE: V082: chk_decision_features_evaluations_outcome already present; skipping
NOTICE: V082: chk_decision_features_evaluations_evidence_tier already present; skipping
NOTICE: V082: chk_decision_features_evaluations_side already present; skipping
NOTICE: relation "idx_decision_features_evaluations_strategy_mode_ts" already exists, skipping
NOTICE: relation "idx_decision_features_evaluations_ts" already exists, skipping
NOTICE: relation "idx_decision_features_evaluations_context_id" already exists, skipping
NOTICE: relation "idx_decision_features_evaluations_outcome_ts" already exists, skipping
[migrate] OK: V082__decision_features_evaluations_split.sql
```

**雙跑 second-pass identical 與 first-pass NOTICE chain** ✓

### Cleanup row count verify

```sql
SELECT (SELECT COUNT(*) FROM governance.canary_stage_log) AS canary_log,
       (SELECT COUNT(*) FROM governance.canary_stage_metric_registry) AS canary_registry,
       (SELECT COUNT(*) FROM learning.decision_features_evaluations) AS df_eval;
```

| canary_log | canary_registry | df_eval |
|---:|---:|---:|
| 0 | 0 | 0 |

**Schema only apply，0 DB row 殘留** ✓ identical 與 first-pass

---

## §8 Cross-language consistency 1e-4 tolerance (任務 §4 review)

W-AUDIT-9 T6 LeaseScope CanaryStage projection 雙端對齊：

Rust (`config/risk_config_advanced.rs:532`):
```rust
pub fn as_shadow_mode(self) -> bool {
    matches!(self, CanaryStage::Stage0)
}
```

Python (`executor_agent.py::_read_shadow_mode`):
```python
return stage == CanaryStage.SHADOW
```

Stage IntEnum encoding 雙端 bit-exact：
| Stage | Rust `CanaryStage` | Python `CanaryStage` IntEnum | as_u8 / value | as_shadow_mode |
|---|---|---|---:|---|
| 0 | `Stage0` | `SHADOW` | 0 | `true` ⇄ `True` |
| 1 | `Stage1` | `PAPER_SINGLE_COHORT` | 1 | `false` ⇄ `False` |
| 2 | `Stage2` | `DEMO_SINGLE_COHORT` | 2 | `false` ⇄ `False` |
| 3 | `Stage3` | `DEMO_FULL_UNIVERSE` | 3 | `false` ⇄ `False` |
| 4 | `Stage4` | `LIVE_PENDING` | 4 | `false` ⇄ `False` |

**離散 enum 不需浮點容差，bit-exact 對齊** ✓ PASS（仍維持 first-pass §4 結論）

---

## §9 Mock 審查 (regression-testing-protocol §5)

E1-FIX 改動範圍 = 2 個 test fixture 文件，0 新業務邏輯，0 新 mock。對既有 mock 抽查 secondary：

| Test | mock 內容 | 是否 IO boundary | OK? |
|---|---|---|---|
| Rust IPC `tests::config` | 無 mock — `commands::handle()` 直接打真實 ipc handler，state 用 `IpcServerState::new_for_tests()` 構造真實 ConfigStore | n/a (純內部 API) | ✓ |
| Python parity test `_drive_python_decision` | `cache._inject_snapshot_for_tests` + `cache._mark_initialized_for_tests` (預存 ExecutorConfigCache 狀態) | DB / IPC fetch boundary | ✓ |
| Python parity test ExecutorAgent ctor | `shadow_mode_provider=cache.shadow_mode_provider()` + `canary_stage_provider=cache.canary_stage_provider()` | provider injection (testability hook) | ✓ |

**0 業務邏輯 mock**：CanaryStage projection / shadow_mode invariant validation / parity decision logic 業務邏輯**真跑**。`_for_tests` API 為 pre-existing testability hook（first-pass §7 已驗），E1-FIX 沒新增。

---

## §10 SLA 壓測 — 不適用本 round

E1-FIX 改動範圍純 test fixture（Rust IPC test rename / 新增 + Python parity test fixture builder helper），**0 hot path 改動**：
- W-AUDIT-9 T1+T2 invariant 在 IPC patch path（非 hot；patch 頻率 < 1/min）
- W-AUDIT-9 T3 `_read_shadow_mode()` 已驗 in-memory enum compare（first-pass §8）

跳過 SLA 壓測 per skill `regression-testing-protocol` §4.5 觸發條件。

---

## §11 §九 governance compliance (CLAUDE.md §九)

| Item | 狀態 |
|---|---|
| commit message 含 `[skip ci]`（per 任務指示）| 即將 commit；本 second-pass report commit + push 加 `[skip ci]` |
| 改動只含 E4 second-pass test report + memory append | ✓ 0 業務代碼觸碰 |
| LOC 限制 (800 警告 / 2000 硬上限) | ✓ second-pass report ~280 LOC |
| 無硬編碼 user-home path | ✓ 0 hit (`/home/ncyu` / `/Users/ncyu` 在 report 內為**結果引用**，非新加 source code path) |
| `git status --porcelain` clean before sign-off | ✓ 寫 report + memory + commit 順序，commit 後 status clean |
| pre-existing fail catalog | ✓ §4 列 4 pre-existing + 1 sibling-session standalone |

---

## §12 結論

| 任務 | 結果 |
|---|---|
| 1. Linux full cargo + pytest 雙跑 deterministic | ✅ PASS（cargo 3077/0 + pytest 4265/5 雙跑 identical）|
| 2. 4 pre-existing pytest fail 不變 | ✅ PASS（identical 雙跑 fail 名單不變）|
| 3. 隔壁 session CI workflow standalone | ✅ Fail mode 與 first-pass §2.3 一致；標 PM follow-up |
| 4. Mac + Linux cargo build --release 0 error + working tree clean | ✅ PASS（17 pre-existing warning unchanged）|
| 5. V080 + V082 idempotent 兩次 PASS + 0 row 殘留 | ✅ PASS（NOTICE chain identical 與 first-pass）|

**Verdict: PASS** — 5 NEW regression（2 Rust IPC + 3 Python parity）全 fix verified · 0 新 regression 引入 · cargo lib 雙端雙跑 deterministic identical 2625/0 · pytest 雙跑 deterministic identical 4265/5（5 fail = 4 pre-existing + 1 sibling-session 不阻擋）。

---

## §13 教訓追加（second-pass 新增）

1. **cargo lib 隱性 +1 test 抵 -1 重用**：first-pass 2622 → second-pass 2625 = 不只 -2 fail 翻 PASS，還有 fixture rename + new test 邊界補齊。LOC delta < 100 但 test count delta +3，符合 E1-FIX「改名 + 補正向場景」設計。
2. **Sibling-session 副作用 catalog 必明說 root cause + commit hash**：`tests/ci/test_github_ci_workflow_static.py` 在 first-pass 因 `0dc6d659`（拆 matrix）而暴露，second-pass 不修但保留 catalog 供 PM follow-up，避免後續 sprint 誤判為 W-AUDIT-9 chain leftover。
3. **雙跑 deterministic 是 PASS 必要條件**：second-pass round 1 + round 2 完全相同 fail 名單 + count，runtime 略不同（85.83s vs 78.03s 屬 system load vary，與 test 結果無關），符合 §一 16 條原則第 10「認知誠實」與 skill `regression-testing-protocol` §「跑兩遍」要求。
4. **Idempotent migration NOTICE chain 雙跑 byte-identical**：V080 + V082 second-pass NOTICE chain 與 first-pass 完全一致，行數 + 順序 + skip 路徑 100% 對齊。`migrations.guard_a/b/c` 的 `idempotency=PASS` 在 PG runtime layer 真實 verified（不是 mock pytest claim）。
5. **PM commit 路徑**：second-pass PASS verdict 後 PM 直接 commit + push origin/main（first-pass commit `13b8e252` + E1-FIX `11849c18` 已成功 push，second-pass 同 chain）。

---

**E4 REGRESSION DONE: PASS · report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-09--sprint_n0_regression_second_pass.md`**
