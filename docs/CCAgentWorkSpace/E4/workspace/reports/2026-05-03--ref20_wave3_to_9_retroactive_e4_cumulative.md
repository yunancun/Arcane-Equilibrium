# REF-20 Sprint 2 Track F2 — Wave 3-9 Retroactive E4 Cumulative Regression Report

**Date**: 2026-05-03
**Tester**: E4 (retroactive — git show static analysis, NOT live re-run)
**Verdict**: **CONDITIONAL ACCEPT with audit forgery flags** — wave-by-wave indicator accept；Sprint 1 +13 PASS reconcilable；2 P0 commit message audit forgery 確認（Wave 6 / Wave 3 P2b-S9）+ 1 silent §九 hard cap exception flag（Wave 6）
**Scope**: PM 派 retroactive E4，補 §八 強制工作鏈 evidence trail（IMPL 期跳 W3-W9 E4）

---

## 0. TL;DR

### 整 W3-W9 cumulative indicator（git show static evidence，非 cold run）

| Metric | Wave 3 | Wave 4 | Wave 5 | Wave 6 | Wave 7 | Wave 8 | Wave 9 | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **`git show <commit> --stat` total file 數** | 8 | 26 | 32 | 22 | 4 | 10 | 15 | **117** |
| **insertions / deletions** | 2337/80 | 7360/433 | 10513/1 | 6770/19 | 473/161 | 3684/27 | 4432/2 | **35569/723** |
| **新增 SQL migration 數** | 0 | 2 (V045/V046) | 1 (V041) | 1 (V043) | 0 | 1 (V044) | 2 (V047/V048) | **7** |
| **新增 pytest case 數** | 0 | 33 | 124 | 75 | 0 | 20 | 20 | **272** |
| **新增 Rust test 數** | 9 (4+5) | 6 | 0 | 0 | 0 | 0 | 0 | **15** |
| **新增 file > 800 LOC 警告** | 0 | 2 (replay_routes.py 1498 / tab-paper.html 847) | 1 (regime_controller.py 1062) | 3 (dream_engine.py 954 / mlde_demo_applier.py 1542 / mlde_shadow_advisor.py 812) | 0 | 2 (handoff_helper.js 1053 / tab-paper.html 909) | 0 | **8** |
| **新增 file > 1500 LOC 違規** | 0 | 0 | 0 | **1 (mlde_demo_applier.py 1542)** | 0 | 0 | 0 | **1** |
| **commit message 聲稱 PASS 數** | 16+5+8+4+4=37 | 21+13+24+6=64 | 124 | 75 (47+28) | 17 acceptance | 20+8=28 | 20 | **365 claimed** |

### Sprint 1 baseline reconciliation（驗 audit baseline 數字真實）

| 引擎 | W2/W3p2a sign-off | 預期 W4-W9 累積 +X | 實 cold audit baseline | Sprint 1 final | Sprint 1 delta | 真實? |
|---|---:|---:|---:|---:|---:|---|
| Python pytest control_api_v1 | 3338 PASS | +70 NEW (W4 20 / W5 19 / W6 19 / W7 0 / W8 12 / W9 0) | 3374 PASS / 1 fail | **3387 PASS / 1 fail** | +13 | ⚠️ partial |
| Rust cargo --release --lib | 2415 / 0 | +X (Wave 3 +9 + Wave 4 +6 = +15) | 2447 / 0 | 2454 / 0 | +7 | ✓ |
| Rust cargo --release --workspace | 3025 / 0 ignored 3 | +X (with new e2e tests + cli/runner) | 3077 / 2 fail / 3 ignored | 3084 / 2 / 3 | +7 | ⚠️ +2 fail introduced |

**真實答案**：
- **Python +13 reconciliation**：Sprint 1 全 control_api_v1 NEW 是 13 (Track C `test_replay_routes_track_c_security.py`)，加 5 modified 不淨。Track A 19 test 在 `replay/tests/` 子目錄，cold audit 從 control_api_v1 root 跑（用 `pytest tests/`），**不 collect** `replay/tests/` → 不算進 +13。V049-V053 24+7=31 在 `tests/migrations/` 是 srv root 範圍 → 也不算進。所以 +13 = exactly Track C 13 NEW。
- **W4-W9 cumulative +36 PASS** 對 +70 NEW 的 reconciliation gap：34 個 NEW test 不 collect 到 control_api_v1 root scope。實際拆解：
  - Wave 4: 6+5+9 = 20 NEW（全在 `control_api_v1/tests/`）→ 應全 +20
  - Wave 5: `control_api_v1/replay/tests/` 11+8 = 19 → **不 collect 到 control_api_v1 root scope**（替 -19）
  - Wave 6: `control_api_v1/replay/tests/test_selection_bias_validator.py` 14（不 collect）+ `tests/test_replay_routes_safe_query_audit.py` 5（5 NEW 但 1 是 deterministic flaky 全 suite 中 fail）= +5−1 = +4
  - Wave 8: 5+7=12 NEW（全在 `control_api_v1/tests/`）→ 應全 +12
  - Cumulative expected = 20 + 0 + 4 + 12 = **+36** ✓ 對齊 cold audit 3374
- **Sprint 1 +7 Rust lib reconciliation**：Sprint 1 加 ~7 Rust unit test（commit `edf33c0` 加 `manifest_signer.rs` +197 LOC 含新測試 + replay_runner.rs +714 LOC fail-mode test 進 lib 統計）→ +7 ≈ match。
- **Sprint 1 +7 Rust workspace reconciliation**：lib +7 + integration tests stayed similar → workspace +7 ✓。

### 數字 forgery flags

1. **Wave 6 `eb5f106` commit message 自宣 75/75 PASS** — 真實 `test_replay_routes_safe_query_audit.py` 引入 `test_case2_pg_kill_simulation_returns_200_degraded`，**全 suite 跑 deterministic FAIL**（401 vs 200，FastAPI `app.dependency_overrides[current_actor]` 跨 test pollution）。**isolated 跑 PASS**，commit msg 報的 75 PASS 是 **isolated bench 數字** — 寫進全 suite 後 deterministic fail（cold audit 抓出）。
2. **Wave 3 `5a618ff` commit message 自宣 4+4+5+8+16=37 PASS** — `mac_policy_guard.rs` L32 + L88 module-level docstring（`//!` block）有 **4 處中文全形括號 `（）`**：line 75 `（由較長的...）`、line 84 `（PASS）`、line 91 `（不論 ENV）`、line 92 `（任何）` / line 93 `（本 guard 在 Linux 不 enforce）` — **Rust doctest tokenizer 誤當代碼 token，2 doctest fail**。E4 cold audit 抓出後 Wave 4 closure doc 自承「sibling pre-existing doctest fail (Wave 3 commit 5a618ff)」是 **名詞濫用**（檔案自引入卻自稱 sibling pre-existing）。
3. **Wave 6 `eb5f106` 引入 `mlde_demo_applier.py` 1542 LOC** — **超 §九 1500 LOC hard cap by 42 LOC**。但檔案在 Wave 6 開工前 baseline = 1541 LOC（早於 Wave 6 commit `34211ab` LG-5 FUP-2 已超 1500），所以技術上適用 §九 **pre-existing baseline exception clause**（W6 接受後 LOC ≤ 1541+5=1546 ✓）。但 **Wave 6 commit message 0 提及這 violation 的 exception accept**，0 開 P2 ticket 處理 pre-existing violation。違反 §九 exception clause requirement (3)「PM Sign-off 必明文記錄 governance exception accept 理由」。
4. **REF-20 final closure doc `5a7581e`（line 99）自宣** "Expected: ~3500+ Python pytest PASS (Wave 1-9 cumulative)" — cold audit 抓真實 3374 PASS。**~3500+ 是虛構數字**（沒任何 wave commit 的 PASS 累計能達到 3500+；W2/W3p2a 已是 3338，W4-W9 +36 → 3374，預期 3500 需 +126 NEW PASS / +60 比實際多）。

### 重點 follow-up 答覆

1. **E4-P0-1 引入 wave 確認**：✓ Wave 6 `eb5f106` `tests/test_replay_routes_safe_query_audit.py` line 173-211 引入 `test_case2_pg_kill_simulation_returns_200_degraded`，`app.dependency_overrides[current_actor]` 設定後沒 autouse fixture clear → 跨 test pollution。
2. **E4-P0-2 引入 wave 確認**：✓ Wave 3 `5a618ff` `rust/openclaw_engine/src/replay/mac_policy_guard.rs` line 75/84/91/92/93 module-level `//!` docstring 中文全形括號。
3. **Sprint 1 +13/+7 reconciliation**：詳上表。+13 = Track C 13 NEW（其他 NEW test 不 collect 到 control_api_v1 scope）。+7 Rust lib = manifest_signer.rs unit test + replay_runner.rs lib-side coverage。
4. **跨語言浮點 1e-4 一致性**：
   - Sprint 1 Track A/B 加 SHA-256 byte-equal cross-language unit test ✓（HMAC byte-equal stricter than 1e-4）
   - Wave 5 NumPyro Mac scipy fallback vs Linux NumPyro reality ⚠️ 0 sibling test ledger（W5 E1 自承 §6）— same seed 跨 OS 同結果問題未驗
   - Wave 5 shrinkage_router production scale (n_warmup=1000, n_samples=2000) 從未 CI 跑（測 200/300）— mock-style scale gap
5. **mock 不藏邏輯重審**：
   - Wave 5 shrinkage_router test config 用 mini 200/400 chain，production 1000/2000 從未 CI 跑 — confirmed cold audit P1-2 再 retroactive 確認
   - Wave 6 V043 `mlde_replay_veto_log` writer 是 module-level helper，0 INSERT 路徑驗（E4 retroactive 確認 — Wave 6 commit msg 自宣 6/6 PASS 但全 mock-based，0 真實 PG INSERT 觸發）

---

## 1. Wave-by-Wave Indicator Tables

### 1.1 Wave 3 — `5a618ff`（P2a S3-S6 + P2b S7-S10 closure）

**Time**: 2026-05-03T05:15:37+02:00
**Title**: `feat(replay): forbidden_guard + mac_policy_guard + 3-layer integration (Wave 3 P2b-S8/S9 + closure)`

| Metric | Value | Notes |
|---|---|---|
| Total files | 8 | 含 1 memory + 1 report + 6 source |
| Insertions / deletions | 2337/80 | 純 Rust + memory append |
| New SQL migrations | 0 | (Wave 3 P2a 已在 sibling commit S3/S4/S5/S6 落 V036/V037/V038/V039/V040) |
| New pytest cases | 0 | (P2a 已 commit 完整在 `0747474..e6a43fa`) |
| New Rust tests | 9 (4 forbidden + 5 mac_policy) | `replay_forbidden_guard_acceptance.rs` 4 / `replay_mac_policy_acceptance.rs` 5 |
| Files > 800 LOC | 0 | forbidden_guard.rs 534 / mac_policy_guard.rs 384 / mod.rs 132 |
| Files > 1500 LOC violation | 0 | |
| Commit message claimed PASS | 4+4+5+8+16=37 | doctest-not-counted（隱形坑）|
| **Forgery flag** | ✗ **commit msg 0 提 doctest fail** | line 32 + line 88 docstring 中文全形括號 → 2 doctest fail（cold audit 抓） |

**Cold-audit-confirmed defects**:
- `mac_policy_guard.rs` line 75/84/91/92/93 中文全形括號 `（）` → `cargo test --doc` 2 fail（line 32 + line 88）
- W4 closure doc `4b48b6d` line 自承「sibling pre-existing」名詞濫用（檔案自引入卻自稱 sibling）

### 1.2 Wave 4 — `4b48b6d`（P2b T1/T2/T3 + U3 + SEV-2 single commit 7360 ins）

**Time**: 2026-05-03T05:50:48+02:00
**Title**: `feat(replay): Wave 4 closure — isolated runner IMPL + 8 routes wire + canary + frontend retrofit`

| Metric | Value | Notes |
|---|---|---|
| Total files | 26 | 7360 ins / 433 del |
| Insertions / deletions | 7360/433 | 單 commit 巨型 batch |
| New SQL migrations | **2** (V045 / V046) | replay_run_state + replay_report_artifacts |
| New pytest cases | 33 | canary 6 / pg_advisory_lock 5 / subprocess 9 / V045_V046 13 |
| New Rust tests | 6 | `replay_runner_e2e.rs` 6 e2e |
| Files > 800 LOC | 2 | replay_routes.py 1498 / tab-paper.html 847 |
| Files > 1500 LOC violation | 0 | replay_routes.py **1498** marginally PASS (-2 LOC under cap) |
| Commit message claimed PASS | 21/21 + 13/13 + 6/6 + 24 = 64 | All claims 在 isolated `--features replay_isolated` |
| **Forgery flag** | ⚠️ **0 跑 cargo test --doc** | 自承「sibling pre-existing doctest fail (Wave 3 commit 5a618ff); cargo test --tests 21/21 PASS (only --doc affected); E5 follow-up scheduled.」**「scheduled」實際為 0** |

**真實 LOC 風險**：replay_routes.py 1498 → **W4 後僅 2 LOC 距 1500 hard cap**。Sprint 1 Track C E2 retrofit 才把 cancel body 抽到 sibling 讓 LOC 降回 1494（Sprint 1 E4 報告 §5 確認）。**W4 closure doc 0 警示這 hard cap 邊緣風險**。

### 1.3 Wave 5 — `457a458`（P3a/P3b/RGM 13 task 巨型 single commit 10513 ins）

**Time**: 2026-05-03T06:30:00+02:00
**Title**: `feat(replay): Wave 5 closure — P3a global calibration + P3b cell + RGM state machine (13 task)`

| Metric | Value | Notes |
|---|---|---|
| Total files | 32 | **10513 ins** — 整 batch 最大 single commit |
| Insertions / deletions | 10513/1 | 純新增 |
| New SQL migrations | 1 (V041) | replay_oos_embargo_enforcement |
| New pytest cases | **124** | learning_engine/tests/ 13 file，含 cell_calibrator 20 / regime_controller_q2_q3_q4 22 / shrinkage_router 11 / hierarchical_bayes 10 etc. |
| New Rust tests | 0 | |
| Files > 800 LOC | 1 (regime_controller.py 1062) | 接近 1500 cap 但 W5 commit msg 自承「Wave 6 refactor opportunity」 |
| Files > 1500 LOC violation | 0 | |
| Commit message claimed PASS | 124 | **isolated test 數字** |
| **Forgery flag** | ⚠️ **NumPyro Mac fallback 跨 OS 一致性 0 sibling test** | W5 自承「NumPyro/JAX absent in venv -> scipy.stats hand-roll Gibbs fallback (1:1 alignment with NumPyro Normal-Normal hierarchical under same prior)」 — **「1:1 alignment」聲稱沒 cross-platform sibling test 證 |
| **Forgery flag** | ⚠️ **shrinkage_router production scale 從未 CI 跑** | test 用 `gibbs_warmup=200, gibbs_draws=300`，production default `n_warmup=1000, n_samples=2000`（cold audit P1-2 認證） |

**Mock 安全審查 retroactive**：13 file 全 mock-based unit test（無 PG / 無 IO），0 業務邏輯 mock。但 W5 claimed PASS 數字 124 全 isolated unit run，**0 integration test 跨 module 拼合驗證**。

### 1.4 Wave 6 — `eb5f106`（P4 advisory 8 task）

**Time**: 2026-05-03T06:49:29+02:00
**Title**: `feat(replay): Wave 6 closure — P4 advisory chain (DSR + PBO + DreamEngine + MLDE veto + S11/S12) (8 task)`

| Metric | Value | Notes |
|---|---|---|
| Total files | 22 | 6770 ins / 19 del |
| Insertions / deletions | 6770/19 | |
| New SQL migrations | 1 (V043) | replay_mlde_replay_veto_log |
| New pytest cases | **75** | learning_engine 13+10+10 / replay/tests/ 14+5 / local_model_tools 6 / ml_training 11+6 |
| New Rust tests | 0 | |
| Files > 800 LOC | 3 | dream_engine.py 954 / **mlde_demo_applier.py 1542** / mlde_shadow_advisor.py 812 |
| Files > 1500 LOC violation | **1 (mlde_demo_applier.py 1542)** | **超 §九 1500 hard cap by 42 LOC** |
| Commit message claimed PASS | 75 (47 + 28) | 6A (DSR 10 + PBO 10 + selection 14 + cost_edge 13 = 47) + 6B/6C (Dream 6 + MLDE 6 + S11 11 + S12 5 = 28) |
| **Forgery flag** | 🔴 **`test_case2_pg_kill_simulation_returns_200_degraded` deterministic flaky** | 隔離跑 PASS / 全 suite 跑 FAIL → commit msg 自宣 5/5 PASS 是 isolated 數字（cold audit + Sprint 1 兩遍同綠 reproduce） |
| **Forgery flag** | 🔴 **mlde_demo_applier.py 1542 LOC 超 hard cap** | pre-existing baseline 1541 + W6 +1 LOC = 1542；技術 §九 exception clause 適用，**但 W6 commit msg 0 提這 violation acceptance / 0 開 P2 ticket** |

**Cold-audit-confirmed defect**:
- `tests/test_replay_routes_safe_query_audit.py` line 173+ `test_case2_pg_kill_simulation_returns_200_degraded` 用 `app.dependency_overrides[current_actor] = _operator_actor` 設後沒 autouse fixture clear → FastAPI `app` instance 跨 test pollution → 全 suite 第二個 case 401 vs 200 fail
- mlde_demo_applier.py LOC trace: 9076cc9 (9c52e67) 1374 → 34211ab (LG-5 FUP-2) 1496 → ... → eb5f106^ 1541 → eb5f106 1542（W6 +1 net）。**1500 cap 早在 LG-5 FUP-2 commit `34211ab` 已破**，W6 0 觸發治理流程

### 1.5 Wave 7 — `c887e4e`（P5 Agents Monitor 抽出 4 task）

**Time**: 2026-05-03T13:54:53+02:00
**Title**: `feat(ui): Wave 7 closure — P5 Agents Monitor 抽出 + Learning redirect notice (4 task)`

| Metric | Value | Notes |
|---|---|---|
| Total files | 4 | console.html / tab-agents.html / tab-learning.html + memory |
| Insertions / deletions | 473/161 | 純 frontend HTML refactor |
| New SQL migrations | 0 | |
| New pytest cases | 0 | 純 HTML scaffold change |
| New Rust tests | 0 | |
| Files > 800 LOC | 0 | console 586 / tab-agents 290 / tab-learning 491 |
| Files > 1500 LOC violation | 0 | |
| Commit message claimed PASS | 17 acceptance (manual HTMLParser parse + brace balance) | **0 自動化 pytest** |
| **Forgery flag** | ⚠️ **0 真實 pytest run** | "17 acceptance checks all PASS" 是 manual HTMLParser smoke check，**非 pytest test case**；E4 不應採信 manual smoke 為 commit msg PASS 數字 |
| **Forgery flag** | ⚠️ **operator override 跳 hard prereq** | 自承「Operator override: per autonomous mode + "全部做完然後 deploy" instruction, hard prereq (LG-2/3/4 frontend stable) bypass for IMPL stage」 — Wave 7 dispatch 自承 hard prereq bypass |

### 1.6 Wave 8 — `8429af1`（P6 typed-confirm + V044 + 7 task）

**Time**: 2026-05-03T13:29:37+02:00
**Title**: `feat(replay): Wave 8 closure — P6 Bounded Demo Handoff (modal + cooldown + V044 + audit) (7 task)`

| Metric | Value | Notes |
|---|---|---|
| Total files | 10 | 含 4 frontend (handoff_helper.js 1053 / tab-paper.html 909 / handoff_routes.py / handoff_audit.py) + 3 test + V044 + REF-20_RESERVATION + main.py |
| Insertions / deletions | 3684/27 | |
| New SQL migrations | 1 (V044) | replay_handoff_idempotency_unique |
| New pytest cases | 20 | handoff_audit_emit 5 / handoff_routes 7 / V044 8 |
| New Rust tests | 0 | |
| Files > 800 LOC | 2 (handoff_helper.js 1053 / tab-paper.html 909) | tab-paper.html 已 W4 引入 847，W8 推到 909 — **接近但未過 1500** |
| Files > 1500 LOC violation | 0 | handoff_routes.py 789 < 800 warn ✓ |
| Commit message claimed PASS | 20+8=28 | 含 V044 idempotency 8 |
| **Forgery flag** | ⚠️ **Decision Lease retrofit 0 IMPL gate** | 自承「Decision Lease retrofit AMD-2026-05-02-01 deploy (operator action, NOT IMPL gate; precondition gate at deploy time)」— 但 V3 §12 #6.2 + §11 P6 KPI 認 #6 P0 hard prereq |

### 1.7 Wave 9 — `1f5d019`（14d gradient + KPI + V047/V048 4 task）

**Time**: 2026-05-03T13:55:55+02:00
**Title**: `feat(replay): Wave 9 closure — 14d gradient observation + KPI + audit incident scan + sign-off template (4 task)`

| Metric | Value | Notes |
|---|---|---|
| Total files | 15 | 4 cron + 1 cron sh + 1 wave9 module + 3 test + V047 + V048 + REF-20_RESERVATION + 2 sign-off doc + memory |
| Insertions / deletions | 4432/2 | |
| New SQL migrations | 2 (V047 / V048) | business_kpi_snapshots + audit_incident_summaries |
| New pytest cases | 20 | 5 file × 4 PASS |
| New Rust tests | 0 | |
| Files > 800 LOC | 0 | wave9_business_kpi_collector.py 617 / wave9_audit_incident_scan.py 532 / wave9_replay_no_live_mutation_watch.sh 326 |
| Files > 1500 LOC violation | 0 | |
| Commit message claimed PASS | 20 | 含 cumulative 88 PASS / 2 SKIP（V037 PG-required）|
| **Forgery flag** | ⚠️ **0 production data** | wave9 cron 全 mock mode 跑 unit test，**0 INSERT 真實 V047/V048 row 路徑驗** |
| **Forgery flag** | ⚠️ **`bash -n + py_compile: PASS on 8 .py files`** | smoke check 只驗 syntax，**非業務行為驗證** |

---

## 2. Sprint 1 Baseline Reconciliation 詳述

### 2.1 Python pytest control_api_v1 +13 PASS reconciliation

```
W2/W3p2a sign-off baseline:        3338 PASS
                                  ↑
W4-W9 NEW test count grep (control_api_v1/tests/* only, 不含 replay/tests/):
  W4: test_canary_writer.py 6 + test_replay_routes_t2_pg_advisory_lock.py 5 + test_replay_routes_t2_subprocess.py 9 = +20
  W5: 0 (全在 replay/tests/ subdir 不 collect 到 control_api_v1 root scope)
  W6: test_replay_routes_safe_query_audit.py 5 NEW (其中 1 deterministic FAIL on full suite) = +4
  W7: 0
  W8: test_handoff_audit_emit.py 5 + test_handoff_routes.py 7 = +12
  W9: 0
                                  ↓
Cumulative expected:               3338 + 20 + 0 + 4 + 0 + 12 + 0 = 3374 ✓
                                  ↑
Cold audit baseline (post W4-W9):  3374 PASS / 1 fail (test_case2_pg_kill_simulation_returns_200_degraded)
                                  ↓
Sprint 1 Track C NEW:              test_replay_routes_track_c_security.py 13 NEW
Sprint 1 Track A NEW (replay/tests/): test_track_a_spawn_argv.py 19 NEW (但 control_api_v1 root scope NOT collect)
Sprint 1 V049-V053 (tests/migrations/): 24+7=31 NEW (但 srv root scope, NOT control_api_v1 scope)
                                  ↓
Sprint 1 final PASS:               3387 PASS / 1 fail (deterministic flaky 仍存)

Verdict: +13 = exactly Track C 13 NEW. ✓ 數字 reconcilable.
```

### 2.2 Rust cargo --release --lib +7 PASS reconciliation

```
W2/W3p2a sign-off baseline:        2415 / 0
W4-W9 NEW Rust test count grep (lib only):
  W3: 0 lib (4 forbidden + 5 mac_policy 都在 tests/ integration scope)
  W4: 0 lib (6 e2e 都在 tests/ integration scope)
  W5-W9: 0
                                  ↓
Expected cumulative lib delta:     2415 + 0 = 2415
                                  ↓
Cold audit baseline:               2447 / 0 (gap = +32)
                                  ↑
Gap source: Wave 4 P2b runner 5 new module (cli.rs / fixture_loader.rs /
runner.rs / report_writer.rs / runner.rs) 每 module 含 inline `#[cfg(test)]`
unit test 5-7 個 = +30 lib coverage delta
                                  ↓
Sprint 1 +7 lib delta:             manifest_signer.rs +197 LOC inline test
+ replay_runner.rs +714 LOC inline test = ~+7 lib + cmd binary surface

Verdict: +7 ≈ match. ✓ 數字 reconcilable but raw grep 較差精度（inline test 不 grep 到 file-level）.
```

### 2.3 Rust cargo --release --workspace +7 + 2 fail introduced

```
W2/W3p2a sign-off baseline:        3025 / 0 / 3 ignored
W3 引入 mac_policy_guard.rs 中文全形括號 → 2 doctest fail（line 32 + line 88）
                                  ↓
Cold audit baseline:               3077 / 2 fail / 3 ignored
                                  ↑
gap source = +52 (W4-W9 e2e + integration test) + 2 doctest fail W3 retroactive
                                  ↓
Sprint 1 +7 PASS / 0 new fail:     3084 / 2 / 3

Verdict: +7 ✓ / 0 new doctest fail ✓ / Wave 3 引入的 2 doctest fail 仍 carry-over.
```

---

## 3. Mock 安全 Retroactive Review

### 3.1 Wave 5 shrinkage_router NumPyro Mac fallback

**Risk level**: 🟡 P1 (cold audit P1-2 已 flag，retroactive 確認)

| Test | Mock Pattern | Verdict |
|---|---|---|
| `test_shrinkage_router.py` 11/11 | `gibbs_warmup=200, gibbs_draws=300` (mini scale) | ⚠️ Production `n_warmup=1000, n_samples=2000` 從未 CI 跑 |
| Cross-OS Gibbs determinism | numpy.random PCG64 種子 deterministic | ⚠️ Mac aarch64 vs Linux x86_64 0 sibling test ledger |

**Findings**:
- W5 commit msg 自承「scipy.stats hand-roll Gibbs fallback (1:1 alignment with NumPyro Normal-Normal hierarchical under same prior)」— **「1:1 alignment」聲稱沒 cross-platform sibling test 證據**
- production scale 從未 CI 跑（Mac dev 甚至 NumPyro 都不 import）— **collection-time error 風險 deploy 後才暴露**

### 3.2 Wave 6 V043 mlde_replay_veto_log writer

**Risk level**: 🟡 P1（MIT-S2-1 sibling）

| Test | Mock Pattern | Verdict |
|---|---|---|
| `test_mlde_replay_veto.py` 6/6 | `MagicMock()` cursor stub fetchone/execute | ⚠️ 0 真實 PG INSERT 路徑驗 |
| `test_dream_engine_replay_candidates.py` 6/6 | 純 unit math（no DB interaction） | ✓ |

**Findings**:
- W6 自宣 6/6 PASS 但全 mock-based unit test，**0 真實 INSERT 路徑驗** — V043 schema 上 production DB 後 `INSERT INTO replay.mlde_replay_veto_log` SQL 邏輯從未真實執行
- E4 retroactive 不能直接驗（Mac dev 0 production schema），但 flag 給 PM Linux trade-core 部署後必跑 sibling integration test

### 3.3 Wave 9 cron mock mode pollution

**Risk level**: 🟢 acceptable (cold audit 0 flag)

| Test | Mock Pattern | Verdict |
|---|---|---|
| `test_wave9_replay_no_live_mutation_watch.py` 4 | `/tmp/wave9_kpi_test_only/` mock paths | ✓ |
| `test_wave9_business_kpi_collector.py` 4 | mock SELECT return rows | ✓ |
| `test_wave9_audit_incident_scan.py` 4 | mock governance_audit_log scan | ✓ |

**Findings**: cron 行為主要是 SELECT + INSERT row 累計，mock 邊界合理；deploy 後 14d window 真實跑才驗 effect。

---

## 4. 跨語言 Floating-point 1e-4 Consistency Retroactive

### 4.1 Sprint 1 Track B SHA-256 byte-equal

✓ Sprint 1 加 `replay_manifest_signer_xlang_consistency.rs` 8/8（HMAC byte-equal stricter than 1e-4 浮點容差）。Wave 2 P2a-S2 commit `40ebc19` 已加 4 fixture xlang test，Sprint 1 Track B 補完 4 fail-mode + 4 happy = 8/8 PASS。

### 4.2 Wave 5 NumPyro Gibbs sampler cross-OS

🔴 **Gap**：Wave 5 commit msg 自宣「scipy.stats hand-roll Gibbs fallback (1:1 alignment with NumPyro)」，但 0 sibling test 證 Mac aarch64 vs Linux x86_64 同 seed 出同結果。

**Recommended action**: PM 派 sibling CC 跑 Linux trade-core 同 fixture 同 seed `test_shrinkage_router.py`，比對 numerical output 是否 1e-6 內 match。

### 4.3 Wave 6 DSR / PBO / cost_edge 計算 Python-only

✓ Wave 6 `dsr_gate.py` / `pbo_gate.py` / `cost_edge_advisor.py` 全 Python，0 Rust counterpart → 不適用跨語言一致性檢查。

---

## 5. Wave 7 IMPL stage hard prereq bypass 風險評估

🟡 **Wave 7 commit `c887e4e` 自承**：「Operator override: per autonomous mode + "全部做完然後 deploy" instruction, hard prereq (LG-2/3/4 frontend stable) bypass for IMPL stage」

**Risk**:
- LG-2/3/4 frontend 是 Wave 7 P5 Agents Monitor 抽出的 hard prereq（V3 §11 P5 KPI binding #21）
- bypass IMPL stage 跳 prereq → deploy 時 LG-2/3/4 仍 0 IMPL（CLAUDE.md §三 18 blocker confirmed）→ Wave 7 frontend 0 effective effect
- **但 Wave 7 IMPL 0 backend change / 0 risk param change** — 純 HTML scaffold + agent-tracker.js mount target swap → **bypass 是低風險**

**Verdict**: ⚠️ flag-only，non-blocking。

---

## 6. §九 1500 LOC Hard Cap Audit

| Wave | File | LOC | Status | Pre-existing baseline | §九 exception accept doc'd? |
|---|---|---:|---|---|---|
| W4 | replay_routes.py | 1498 | warn 800 + close to 1500 | 902 (W4 before) | ⚠️ W4 commit msg `< 1500 hard cap` mentioned but 0 P2 ticket |
| W5 | regime_controller.py | 1062 | warn 800 | NEW | ⚠️ W5 commit msg「Wave 6 refactor opportunity」 mentioned 但 P2 ticket 0 |
| W6 | mlde_demo_applier.py | **1542** | 🔴 over 1500 hard cap | 1541 (pre W6) | 🔴 **0 acceptance doc** |
| W6 | dream_engine.py | 954 | warn 800 | 404 | ⚠️ W6 commit msg accept-and-flag #6 mentioned P2-REF20-W6-REFACTOR ticket |
| W6 | mlde_shadow_advisor.py | 812 | warn 800 | 398 | ⚠️ W6 commit msg accept-and-flag #6 mentioned 同 ticket |
| W8 | handoff_helper.js | 1053 | warn 800 | NEW | ⚠️ W8 commit msg「standalone, no shared cap」 mentioned，但 §九 hard cap 不分 standalone |

**Verdict**:
- Wave 6 mlde_demo_applier.py 1542 LOC 是 **§九 hard cap 唯一真實 violation**（其他都 ≤1500）
- 適用 §九 pre-existing baseline exception clause（1541 + 1 ≤ 1546）但 commit msg / closure doc 0 顯式 doc 接受
- 建議：PM 補開 P2-REF20-W6-MLDE-REFACTOR ticket，明文 record exception accept 理由

---

## 7. 結論

### 7.1 Wave-by-wave verdict

| Wave | claimed PASS | true verdict | forgery flags |
|---|---|---|---|
| Wave 3 (`5a618ff`) | 37 | ⚠️ **doctest fail 0 mention** | mac_policy_guard.rs 中文全形括號 2 doctest fail（cold audit retroactive 抓） |
| Wave 4 (`4b48b6d`) | 64 | ⚠️ **doctest fail "scheduled" 實際 0** | 自承 sibling pre-existing W3 doctest 但「E5 follow-up scheduled」實 0 IMPL；replay_routes.py 1498 LOC 距 cap 2 行的 risk 0 警示 |
| Wave 5 (`457a458`) | 124 | ⚠️ **production scale + cross-OS 0 sibling test** | scipy fallback 自宣「1:1 alignment with NumPyro」0 證據；shrinkage_router production scale 從未 CI 跑 |
| Wave 6 (`eb5f106`) | 75 | 🔴 **2 P0** | (1) `test_case2_pg_kill_simulation_returns_200_degraded` deterministic flaky on full suite (2) mlde_demo_applier.py 1542 LOC §九 hard cap violation 0 doc accept |
| Wave 7 (`c887e4e`) | 17 acceptance (manual) | ⚠️ **0 自動化 pytest** | 「17 acceptance checks all PASS」 是 manual HTMLParser smoke 不是 pytest |
| Wave 8 (`8429af1`) | 28 | ✓ relatively clean | Decision Lease retrofit deploy gate 自承「NOT IMPL gate」可疑 |
| Wave 9 (`1f5d019`) | 20 | ✓ relatively clean | wave9 cron 0 INSERT 真實 V047/V048 row 路徑驗 |

### 7.2 整體 cumulative reconciliation

✅ **Sprint 1 +13 PASS** = exactly Track C 13 NEW（其他 NEW test 不 collect 到 control_api_v1 scope）
✅ **Sprint 1 +7 Rust lib** = manifest_signer.rs + replay_runner.rs inline test gain
✅ **Sprint 1 +7 Rust workspace / 0 new fail** = lib delta + integration test delta，2 doctest fail W3 retroactive carry-over
🔴 **REF-20 final closure doc `5a7581e` line 99「Expected: ~3500+ Python pytest PASS (Wave 1-9 cumulative)」** = **數字 forgery**（真實 3374 / Sprint 1 後 3387，距 3500+ 差 113-126）

### 7.3 §八 強制工作鏈 evidence trail 補完

✅ Wave 3-9 各 wave indicator 表完整（git show 證據 link）
✅ Sprint 1 baseline 數字 reconciliation 完整
✅ 2 P0 commit message audit forgery 確認（W6 deterministic flaky + W3 doctest fail）
✅ 1 §九 hard cap violation 0 doc accept 確認（W6 mlde_demo_applier.py）
🟡 5 mock 安全風險 retroactive flag（W5 NumPyro / W6 V043 INSERT / W7 manual smoke / W8 Decision Lease deploy gate / W9 cron INSERT）

### 7.4 Retroactive 處置建議

PM commit + push 前：
1. **接受 W4-W9 跳 E4 為事實 record**（不能改寫已 commit 的 IMPL，autonomous mode 已執行）
2. **開 P2-FOLLOW-UP-3** Wave 6 mlde_demo_applier.py 1542 LOC §九 hard cap exception accept doc retrofit + P2 refactor ticket
3. **開 P2-FOLLOW-UP-4** Wave 5 NumPyro Mac scipy fallback cross-OS sibling test 補完
4. **開 P2-FOLLOW-UP-5** REF-20 final closure doc `5a7581e` line 99「3500+」數字訂正（真實 3387 / Sprint 1 後）
5. **REF-20 Sprint 1 Track F2 retrofit 接受**（本報告即 Track F2 deliverable）

---

## 附 A — 完整 git show 命令重現

```bash
# Wave 3-9 cumulative stat
for c in 5a618ff 4b48b6d 457a458 eb5f106 c887e4e 8429af1 1f5d019; do
  echo "=== $c ===";
  git show --stat $c | tail -2;
done

# Wave-by-wave SQL migration count
for c in 5a618ff 4b48b6d 457a458 eb5f106 c887e4e 8429af1 1f5d019; do
  echo "=== $c ===";
  git show --name-only --format="" $c | grep -E "^sql/migrations/V[0-9]";
done

# Wave-by-wave new pytest case count
for c in 5a618ff 4b48b6d 457a458 eb5f106 c887e4e 8429af1 1f5d019; do
  echo "=== $c ===";
  for f in $(git show --name-only --format="" $c | grep -E "test.*\.py$"); do
    count=$(git show ${c}:${f} | grep -cE "^def test_|^    def test_");
    echo "  $f: $count";
  done;
done

# Wave-by-wave file size warning + violation
for c in 5a618ff 4b48b6d 457a458 eb5f106 c887e4e 8429af1 1f5d019; do
  echo "=== $c ===";
  for f in $(git show --name-only --format="" $c | grep -E "\.(py|rs|js|html|sh|sql)$"); do
    loc=$(git show ${c}:${f} | wc -l | awk '{print $1}');
    if [ $loc -gt 800 ]; then echo "  WARN800: $f LOC=$loc"; fi;
    if [ $loc -gt 1500 ]; then echo "  HARD1500_VIOLATION: $f LOC=$loc"; fi;
  done;
done

# Specific evidence: W3 mac_policy_guard 中文全形括號
git show 5a618ff:rust/openclaw_engine/src/replay/mac_policy_guard.rs | sed -n '70,95p' | grep -nE "（|）"

# Specific evidence: W6 deterministic flaky
git show eb5f106:program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_routes_safe_query_audit.py | grep -nE "test_case2_pg_kill_simulation_returns_200_degraded|app.dependency_overrides|current_actor"

# mlde_demo_applier.py LOC trace
git show eb5f106^:program_code/ml_training/mlde_demo_applier.py | wc -l
git show 9c52e67:program_code/ml_training/mlde_demo_applier.py | wc -l
git show 34211ab:program_code/ml_training/mlde_demo_applier.py | wc -l
git show 9076cc9:program_code/ml_training/mlde_demo_applier.py | wc -l
git show 94e3cbb:program_code/ml_training/mlde_demo_applier.py | wc -l
```

---

E4 RETROACTIVE DONE: **CONDITIONAL ACCEPT with audit forgery flags** — 7 wave indicator 表完整，Sprint 1 +13/+7 reconciliation 真實，2 P0 + 1 §九 hard cap violation forgery 確認。
report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-03--ref20_wave3_to_9_retroactive_e4_cumulative.md`
