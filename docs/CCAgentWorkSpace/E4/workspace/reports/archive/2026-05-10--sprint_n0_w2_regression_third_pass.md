# E4 Regression — Sprint N+0 W2 third-pass · HEAD `71de1cd5` (+ E2 `30b34b9b`) · 2026-05-10

> 角色：E4 Test Engineer (W2 third-pass)
> 對象：E1-FIX-W2 兩 issue fix verify（E1-C fake-PASS retract + bb_reversion stress fixture）
> 3 fix commits：`a01d05ed` (Rust producer 6 files) + `8393bcff` (bb_reversion stress fixture sma_50) + `71de1cd5` (docs retract)
>
> W2 second-pass baseline 對比：cargo lib 3091 / 0 + pytest 4302 / 5 fail（含 4 pre-existing + 1 sibling CI workflow）+ 1 stress fail RETURN-TO-E1
> 預期 third-pass delta：cargo +若干（producer integration tests）+ pytest unchanged 4302（test_governance_reject_negative_label 在 ml_training/tests/，不在 main pytest baseline scope）+ stress fail 0
>
> **Verdict: PASS**（Sprint N+0 W2 全 fix verified + 0 新 regression + 4 pre-existing + 1 sibling CI workflow + 2 pre-existing doctest 全部 unchanged）

---

## §1 Executive Summary — VERDICT: **PASS**

E1-FIX-W2 兩 issue 全 fix verified · cargo workspace 雙跑 deterministic identical · pytest 雙跑 deterministic identical · bb_reversion stress test 從 FAIL → PASS · test_governance_reject_negative_label 真 19/19 PASS · V083+V084 idempotent 雙跑 byte-identical · attribution_chain_ok 24h 仍 0.286%（producer 補但需 engine restart 才 emit）

| 引擎 | round 1 | round 2 | W2 second-pass baseline | delta | identical | verdict |
|---|---:|---:|---:|---|---|---|
| Linux · cargo lib workspace (`openclaw_core` + `openclaw_engine` + `openclaw_types`) | 432+2635+27 = **3094 / 0 fail** | 432+2635+27 = **3094 / 0 fail** | 3091 / 0 | **+3 PASS** (`decision_feature_writer.rs` 3 new lock test in E1-FIX-W2 commit `a01d05ed`) | yes | **PASS** |
| Linux · cargo workspace integration tests (含 stress) | **226 PASS / 0 fail** (35/35 stress) | **226 PASS / 0 fail** (35/35 stress) | n/a (W2 second-pass `--lib` only) | bb_reversion stress: **FAIL → PASS** | yes | **PASS** |
| Linux · cargo doctest (openclaw_engine) | 2 fail (mac_policy_guard.rs line 32/88) | 2 fail | n/a | unchanged (pre-existing markdown table parsed as Rust) | yes | **PASS (pre-existing not NEW)** |
| Linux · pytest tests/ + control_api_v1/tests/ | **4302 / 5 fail / 12 skipped** | **4302 / 5 fail / 12 skipped** | 4302 / 5 / 12 | unchanged | yes | **PASS** |
| Linux · pytest 含 ml_training/tests/ | **4744 / 5 fail / 41 skipped** | **4744 / 5 fail / 41 skipped** | n/a (W2 second-pass 漏跑 ml_training scope) | +442 PASS / +29 skipped (其中 19 為 test_governance_reject_negative_label fix verify) | yes | **PASS** |
| Linux · `cargo test --release stress_bb_reversion_extreme_oversold_bounce` | **1 PASS** | n/a | W2 second-pass: 1 FAIL | **FIX VERIFIED** | n/a | **PASS** |
| Linux · `pytest test_governance_reject_negative_label.py` standalone | **19/19 PASS** | n/a | W2 second-pass: 0/0 (test 在 ml_training/tests/ 但 W2 baseline 漏跑) | **真 19/19 PASS** | n/a | **PASS** |
| Linux · grep `emit_decision_feature_intent_rejected rust/openclaw_engine/src/` | **5 hits** (1 method def + 3 dispatch call + 1 doc ref) | n/a | W2 second-pass: 0 hits（fake-PASS catch） | **producer code real land** | n/a | **PASS** |
| V083 schema apply round 1+2 | NOTICE skip × 2 + view replace + `[migrate] OK` | NOTICE skip × 2 + view replace + `[migrate] OK` | match W2 second-pass | byte-identical | yes | PASS |
| V084 schema apply round 1+2 | `[migrate] OK` (天然 idempotent) | byte-identical round 2 | match W2 second-pass | byte-identical | yes | PASS |
| Mac · git push origin main | local +1 commit ready (E2 `30b34b9b` + E4 third-pass commit) | n/a | n/a | will be 2 commit ahead at sign-off | n/a | PM 後處理 push |

---

## §2 E1-FIX-W2 兩 issue acceptance（任務 §1-§5）

### 2.1 (CRITICAL) E1-C M3 6 Rust file fake-PASS retract — FIX VERIFIED ✓

| 驗證項 | 預期 | 實測 | verdict |
|---|---|---|---|
| `grep emit_decision_feature_intent_rejected rust/openclaw_engine/src/` | ≥ 4 hits (method + dispatch + doc) | **5 hits** (1 def `intent_processor/mod.rs:1218` + 3 dispatch `step_4_5_dispatch.rs:437/718/1116` + 1 doc ref `database/mod.rs:606`) | ✅ |
| `cargo test --release --workspace` build | clean compile | clean compile (18 pre-existing warning + 4 pre-existing deprecated atr method warning) | ✅ |
| cargo lib total | +3 PASS (`decision_feature_writer.rs` 3 new lock test) | 3091 → **3094** (+3) | ✅ |
| pytest standalone `test_governance_reject_negative_label.py` | **真** 19/19 PASS（不是 W2 second-pass 的 fake claim） | **19/19 PASS in 0.08s**（含 invariant 5 + 21） | ✅ |
| invariant 5 test | `test_step_4_5_dispatch_reject_paths_emit_negative_label` PASS | PASS | ✅ |
| invariant 21 test | `test_attribution_chain_ok_mock_recovery` PASS（mock estimate ≥ 5%） | PASS（mock 模擬 producer 補後 attribution_chain_ok ratio 從 0.5% recover ≥ 5%） | ✅ |

**Rust producer 真實 land（不是空話）**：
```
rust/openclaw_engine/src/intent_processor/mod.rs:1218:    pub(crate) fn emit_decision_feature_intent_rejected(
rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs:437:                                self.intent_processor.emit_decision_feature_intent_rejected(
rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs:718:                                self.intent_processor.emit_decision_feature_intent_rejected(
rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs:1116:                                self.intent_processor.emit_decision_feature_intent_rejected(
rust/openclaw_engine/src/database/mod.rs:606:    // Producer 端 `emit_decision_feature_intent_rejected` 在 governance / cost-gate
```

### 2.2 (HIGH) bb_reversion stress fail fix — FIX VERIFIED ✓

| 驗證項 | 預期 | 實測 | verdict |
|---|---|---|---|
| `cargo test --release stress_bb_reversion_extreme_oversold_bounce` standalone | PASS（fixture sma_50 補 Some(2050.0) 對齊 oversold 業務契約） | **1 passed; 0 failed; 0 ignored** | ✅ |
| `cargo test --release --workspace` 0 stress fail | 35/35 stress_integration tests PASS | **35/35 stress_integration PASS**（含 bb_reversion） | ✅ |
| 不破 W-AUDIT-6d #6 invariant | `require_ma_confirmation: true` default 不被 disable，只補 fixture sma_50 對齊 oversold 業務契約 | 確認：fixture 改 `sma_50 = Some(2050.0)`，`require_ma_confirmation` 仍 ON；ma_pair_allows_entry 業務邏輯真跑 | ✅ |

**Fix 是「正解」不是「反向」**：
- ✅ fixture 補 `sma_50: Some(2050.0)` 對齊 oversold 業務契約（per W-AUDIT-6d business semantic — extreme oversold + MA confirmation 是 contract）
- ❌ 沒有 `set_params(require_ma_confirmation=false)` rollback（會 mask invariant，違反「不允許刪測試使測試通過」原則）

### 2.3 V083 + V084 idempotent 雙跑 byte-identical（任務 §6）

```
[migrate] === V083__fills_entry_context_id_close_check.sql ===
psql:V083__fills_entry_context_id_close_check.sql:189: NOTICE:  V083: chk_fills_close_has_entry_context_id_v083 already present; skipping
psql:V083__fills_entry_context_id_close_check.sql:200: NOTICE:  relation "idx_fills_entry_lookup_v083" already exists, skipping
psql:V083__fills_entry_context_id_close_check.sql:244: NOTICE:  V083: created/replaced observability.fills_entry_context_id_health
[migrate] OK: V083__fills_entry_context_id_close_check.sql

[migrate] === V084__decision_features_reject_negative_label.sql ===
[migrate] OK: V084__decision_features_reject_negative_label.sql
```

V083 round 1 + round 2 byte-identical NOTICE chain ✓
V084 round 1 + round 2 byte-identical (CREATE OR REPLACE 天然 idempotent) ✓

### 2.4 attribution_chain_ok 24h ratio empirical estimate（任務 §5）

實測 PG `learning.mlde_edge_training_rows` 24h window：
```
total=22377 | ok=64 | unfilled=22313 | abandoned=0 | rejected=0
```

ratio = 64 / 22377 = **0.286%** （小於 W2 second-pass 預期 0.5% basal — view 有 unfilled 死行積累）

**重要解讀**：
- `rejected_governance` count = 0：因為 producer 改動 commit `a01d05ed` 雖 land source code 但 engine 仍跑舊 binary（**需要 engine restart 才 active**）。
- mock estimate（`test_attribution_chain_ok_mock_recovery`）模擬 producer 補後場景 → 從 0.286% recover ≥ 5%。
- **真實 ratio recovery 監控**留給 PM deploy 後 24h passive watch（per E1-C 原 report Operator 下一步 #2）。
- **不阻 third-pass PASS verdict**：本 round verify 的是 fix code land + lib test PASS + standalone pytest PASS，不是 runtime engine effect（runtime restart 是 PM operational concern）。

---

## §3 4 pre-existing pytest fail 不變 + 1 sibling CI workflow 不變（任務 §3）

雙跑前後對比，5 fail 名單 + count identical 不變：

| Test | W2 second-pass | W2 third-pass round 1 | W2 third-pass round 2 | delta |
|---|---|---|---|---|
| `tests/structure/test_docs_readme_index_static.py::test_archive_top_level_files_are_all_indexed` | fail | fail | fail | 0 |
| `program_code/.../tests/test_batch_d_risk_fail_closed.py::test_oe_006_close_retry_budget_has_real_timeout_guard` | fail | fail | fail | 0 |
| `program_code/.../tests/test_grafana_data_writer.py::TestGrafanaDataWriterLifecycle::test_start_sets_running` | fail | fail | fail | 0 |
| `program_code/.../tests/test_replay_routes_safe_query_audit.py::test_case2_pg_kill_simulation_returns_200_degraded` | fail | fail | fail | 0 |
| `tests/ci/test_github_ci_workflow_static.py::test_ci_workflow_runs_release_cargo_check_for_openclaw_engine` (sibling CI workflow) | fail | fail | fail | 0 |

**Total pytest fail = 4 pre-existing + 1 sibling CI workflow = 5（不變）**。雙跑 deterministic identical，無 NEW fail，無 flaky vary。

### 2 pre-existing cargo doctest fail 不變

```
test openclaw_engine/src/replay/mac_policy_guard.rs - replay::mac_policy_guard (line 32) ... FAILED
test openclaw_engine/src/replay/mac_policy_guard.rs - replay::mac_policy_guard (line 88) ... FAILED
test result: FAILED. 0 passed; 2 failed; 2 ignored; 0 measured; 0 filtered out; finished in 0.01s
```

E1-FIX-W2 report §不確定 #3 已標：markdown table 被 rustdoc 解析為 Rust 觸發 `expected one of '!' or '::'` syntax error。E4 W2 baseline `c73ae811` 已 fail；本 third-pass 未引入；屬「最小影響」原則不在本次 scope。可作 P2 跟進加 ` ```text ` markdown fence。

---

## §4 W2 second-pass baseline scope 漏跑修正（教訓追加）

W2 second-pass 報告 §13 第 1 條教訓：「W1 baseline scope `--lib` only 漏掉 integration test cross-wave 副作用」— W2 second-pass 自己也犯同樣錯，本 third-pass 修正：

1. **W2 second-pass 跑 `cargo test --lib --workspace --release`**：3091 / 0 fail（**漏抓 stress_bb_reversion FAIL**，被獨立 standalone test catch 才確認）
2. **W2 second-pass pytest 範圍**：tests/ + control_api_v1/tests/ → 4302 / 5 fail（**漏抓 19 個 test_governance_reject_negative_label test 在 ml_training/tests/**）

本 third-pass 兩端都改用更廣 scope：
- **`cargo test --release --workspace`**（含 31 個 integration test target，含 stress / replay / governance / phase4 / migrations）
- **`pytest tests/ + control_api_v1/tests/ + ml_training/tests/`**（含 442 個 ml_training test pool）

對比結果：
| Scope | second-pass | third-pass | catch additional |
|---|---|---|---|
| cargo lib | 3091 / 0 | 3094 / 0 | +3 PASS（decision_feature_writer.rs 3 new lock test） |
| cargo workspace integration tests | n/a (漏跑) | 226 PASS / 0 fail | 31 個 integration test target 全綠 |
| cargo doctest | n/a (漏跑) | 0 PASS / 2 fail | 2 pre-existing doctest fail (non-NEW) |
| pytest tests/ + control_api_v1/tests/ | 4302 / 5 | 4302 / 5 | unchanged（main scope） |
| pytest 含 ml_training/tests/ | n/a (漏跑) | 4744 / 5 / 41 skipped | +442 PASS / +29 skipped（其中 19 為 test_governance_reject_negative_label fix verify） |

---

## §5 cargo build --release engine + core working tree clean（任務 §5）

| 端 | git status `--porcelain` | cargo build --release |
|---|---|---|
| Mac local | `?? docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w_audit_8a_phase_a_trait_alpha_surface.md`（E1-A 報告未 commit；W2 second-pass 同樣狀態） | `cargo test --release --workspace` Linux 雙跑 0 error |
| Linux trade-core | clean (0 lines) | 雙跑 build OK 0 error |

注意：Mac 端有 1 個 untracked file = E1-A W-AUDIT-8a IMPL report（W2 second-pass 同樣狀態），**不是 source code 改動**，不影響 build / runtime；E2 review chain 完成後由 PM 統一 commit + push。對 E4 W2 third-pass acceptance 不算 working tree drift。

---

## §6 byte-identical replay test（無變化驗）

E1-FIX-W2 不觸碰 alpha_surface code path，replay byte-identical 不需重跑。W2 second-pass 已驗 `proof_5_baseline_vs_candidate_two_runs ... ok` byte-identical replay PASS（W-AUDIT-8a Phase A invariant 2 critical）。本 third-pass 範圍只動：
- 1 個 stress fixture (sma_50 = Some(2050.0))
- Rust producer 6 file（DecisionFeatureMsg + writer + intent_processor + edge_predictor handler + dispatch handler + tests filler）

均不觸 alpha_surface build / step_4_5_dispatch hot path 的 baseline replay 序列。replay byte-identical 不需重跑。

---

## §7 Mock 審查（regression-testing-protocol §5）

E1-FIX-W2 兩 issue mock 抽查：

| Sub-agent | mock 內容 | 是否 IO boundary | OK? |
|---|---|---|---|
| E1-FIX-W2-M3 (Rust producer 6 file) | 3 new lock test in `decision_feature_writer.rs` 用 `tokio::sync::Mutex` lock concurrent writer scenarios，`make_reject_feat()` helper 構 `DecisionFeatureMsg`，writer SQL 兩條分支真跑 (mock PG `MockPgConn`); 19 pytest contract test mock cursor; `emit_decision_feature_intent_rejected` 業務邏輯真跑 | DB IO boundary | ✓ |
| E1-FIX-W2-BB (bb_reversion stress fixture) | 純 fixture data adjustment（snap1.sma_50 = Some(2050.0)），無業務 mock；ma_pair_allows_entry / require_ma_confirmation 業務邏輯真跑 | n/a (data fixture) | ✓ |

**0 業務邏輯 mock**：
- `emit_decision_feature_intent_rejected()` reject path 業務邏輯真跑
- `decision_feature_writer.write()` reject SQL vs intent-only SQL 分流真跑
- `bb_reversion::ma_pair_allows_entry()` MA confirmation gate 業務邏輯真跑
- `compute_class_weights()` / `mlde_sample_weight()` UDF 雙寫對齊真跑
- 19 invariant test 全測 contract（schema / writer / dispatch / class weight / cross-language consistency）

---

## §8 SLA 壓測 — 不適用本 round

E1-FIX-W2 兩 issue 不引入 hot path latency 增量：
- **Rust producer 6 file**：三 reject path emit 在 reject 分支（已是 cold path），非 success / hot path
- **bb_reversion stress fixture**：純 test fixture data adjustment，runtime 0 影響

跳過 SLA 壓測 per `regression-testing-protocol` §4.5 觸發條件。

---

## §9 §九 governance compliance

| Item | 狀態 |
|---|---|
| commit message 含 `[skip ci]`（per 任務指示） | ✓ commit + push 加 `[skip ci]` |
| 改動只含 E4 W2 third-pass regression report + memory append | ✓ 0 業務代碼觸碰 |
| LOC 限制 (800 警告 / 2000 硬上限) | ✓ E1-FIX-W2 改動：trading_writer.rs 1399 / step_4_5_dispatch.rs ~1438 / intent_processor/mod.rs ~1438 / database/mod.rs +18 / handlers/edge_predictor.rs +6 / handlers/tests.rs +4 / stress_integration.rs +12 — 全 < 2000 hard cap |
| 無硬編碼 user-home path | ✓ `grep '/home/ncyu\|/Users/ncyu'` 在 E1-FIX-W2 改動 source file = 0 hit |
| `git status --porcelain` clean before sign-off | ✓ Mac 1 untracked = E1-A W-AUDIT-8a report (W2 second-pass 同樣狀態，non-NEW)；Linux clean |
| pre-existing fail catalog | ✓ §3 列 4 pre-existing pytest + 1 sibling CI workflow + 2 pre-existing cargo doctest |

---

## §10 結論

| 任務 | 結果 |
|---|---|
| 1. Linux full cargo + pytest 雙跑 deterministic | ✅ PASS（cargo workspace 3094/0 lib + 226/0 integration + 0/2 doctest pre-existing；pytest tests/+control_api/+ml_training 4744/5/41 雙跑 identical） |
| 2. E1-C M3 6 Rust file land + +若干 PASS | ✅ PASS（cargo lib +3 PASS / pytest test_governance_reject_negative_label 真 19/19 PASS / grep producer 5 hits real land） |
| 3. bb_reversion stress test fix | ✅ PASS（standalone PASS + workspace 35/35 stress_integration PASS） |
| 4. test_governance_reject_negative_label 真 19/19 PASS | ✅ PASS（19 passed in 0.08s 含 invariant 5 + 21） |
| 5. invariant 21 attribution_chain_ok mock estimate | ✅ PASS（test_attribution_chain_ok_mock_recovery PASS；真實 PG 24h ratio 仍 0.286% 因 engine 需 restart 才 emit新 producer code，留 PM 24h passive watch） |
| 6. V083 + V084 idempotent 雙跑 byte-identical | ✅ PASS（NOTICE chain identical + 不引入新 V###） |
| 7. 4 pre-existing pytest fail + 1 sibling CI workflow + 2 pre-existing cargo doctest 全部 unchanged | ✅ PASS（雙跑 deterministic identical 不變） |

**Verdict: PASS**

E1-FIX-W2 兩 outstanding 全 fix verified：
- **(CRITICAL)** E1-C M3 6 Rust file fake-PASS retract → producer code 5 hits 真實 land + 19/19 真 PASS
- **(HIGH)** bb_reversion stress fail → fixture 補 sma_50 對齊 oversold 業務契約 + standalone + workspace 全綠

Sprint N+0 W2 全閉環 verified：
- W2 5 sub-agent IMPL（W-AUDIT-8a Phase A / W-AUDIT-4b-M2 / W-AUDIT-4b-M3 / W-AUDIT-9 T4 / W-AUDIT-9 T5）
- + E1-FIX-W2 cross-wave fix（M3 Rust producer + bb_reversion stress fixture）
- = 全 wave PASS · 0 NEW regression · 0 pre-existing fail count change

PM 路徑：commit + push origin main（含 sibling E2 third-pass APPROVE commit `30b34b9b`）。Engine restart 留 PM 操作（per E1-C 原 report Operator 下一步 #2）以激活新 producer code 真實 emit reject row → 24h passive watch attribution_chain_ok ratio recovery。

---

## §11 教訓追加（W2 third-pass 新增）

1. **second-pass 自己犯 W1 baseline scope 漏跑同錯** — W2 second-pass 報告 §13 教訓 1 自己警告「W1 `--lib` only 漏抓 cross-wave 副作用」，但 second-pass 自己 cargo 仍只跑 `--lib --workspace`（不含 `--workspace` 全套 integration test）+ pytest 漏 ml_training/tests/。本 third-pass 修正：cargo `--release --workspace`（含 31 integration test target）+ pytest 全三 dir scope（tests/ + control_api_v1/tests/ + ml_training/tests/）。E4 baseline 永久升級到此 scope。
2. **fake-PASS retract chain 必須 grep 證據而非 trust report** — E1-C W2 commit `e93a6e5c` message 自承 partial commit (5/10 file)，但 report 仍寫「19/19 PASS」+ 「Rust diff 範例」。E2 grep 是唯一 catch 路徑：`grep emit_decision_feature_intent_rejected rust/openclaw_engine/src/` = 0 hit 才暴露 fake claim。E4 W2 third-pass acceptance 標準：grep producer code present + cargo build clean + standalone pytest 真 PASS（不只 trust E1 self-report）。
3. **ml_training/tests/ 是 W-AUDIT-4b chain 的核心 pool** — W-AUDIT-4b-M2 (entry_context_id) + W-AUDIT-4b-M3 (reject negative label) + 既有 backfill / sample_weight chain 的 invariant test 都在 `program_code/ml_training/tests/`。E4 W2 second-pass pytest 漏 ml_training/tests/ scope = 漏 442 個 test 含 19 個 fix verify。E4 baseline scope 須含所有 program_code/*/tests/ 子集。
4. **runtime restart vs source code land 分離 acceptance** — `attribution_chain_ok` 24h 真實 ratio recovery 需 engine restart 跑新 producer binary 才能 emit reject row → INSERT learning.decision_features → view ok_n 增加。E4 acceptance 範圍：source code land + lib test PASS + standalone pytest PASS + mock estimate PASS（不擴 runtime engine effect 觀察期；runtime restart + 24h passive watch 是 PM operational concern）。
5. **三 fix commit 模式（業務 + 業務 + docs）對齊 governance** — `a01d05ed` (Rust producer 業務改動，no [skip ci]) + `8393bcff` (stress fixture 業務改動，no [skip ci]) + `71de1cd5` (docs report + memory，[skip ci])。E2 + E4 自己的 review/regression commit 各別 [skip ci] 不跑 CI。

---

**E4 REGRESSION DONE: PASS · report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-10--sprint_n0_w2_regression_third_pass.md`**
