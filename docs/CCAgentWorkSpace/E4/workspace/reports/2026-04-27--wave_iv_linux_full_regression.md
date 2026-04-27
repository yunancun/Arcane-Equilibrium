# E4 Regression Test Report — Wave IV Linux full regression · 2026-04-27

## 範圍

Wave IV final acceptance for 3 主軸 + 補測（origin/main `6e466c8..7c32d1f`，5 commits）：

- `b8b5150` MAF-SPLIT impl（multi_agent_framework.py 1190→966 + scout_agent.py NEW 297）
- `d190acb` MAF-SPLIT docs
- `aca7ee3` G8-01 W1 CognitiveModulator dead-path fix（4 production diff + 6 new tests）
- `af66ac1` G3-09 Phase A daemon integration test（test_cost_edge_advisor_daemon.rs 6 tests）
- `7c32d1f` cross-agent memory updates

Linux SSOT-from-Mac via `ssh trade-core` per memory `feedback_ssh_bridge_workflow`. 工作模式：純 run remote tests，0 production code 改動。Linux repo 從 `6e466c8` fast-forward 至 `7c32d1f`（git status clean，0 untracked，純 ff-only）。Cargo binary @ `~/.cargo/bin/cargo`（rustup-managed），需 `source ~/.cargo/env`。Python interpreter = system `/usr/bin/python3` 3.12.3 + pytest 9.0.2（無 venv 需 activate）。Healthcheck 需 sourcing `~/BybitOpenClaw/secrets/environment_files/{basic_system_services,trading_services}.env` 取 PG password。

## Test 結果

### Rust（從 `~/BybitOpenClaw/srv/rust`，`cargo test --release`）

| 引擎 | passed | failed | baseline | delta | 跑 1 | 跑 2 |
|---|---:|---:|---:|---:|---|---|
| openclaw_engine --lib | 2290 | 0 | 2290 | 0 | ✅ | ✅ 同綠 |
| --test test_cost_edge_advisor_daemon | 6 | 0 | 0 (新增) | +6 | ✅ | (small fast deterministic, 1 run sufficient) |

新整合測試清單（G3-09 Phase A daemon）：
- `dual_safeguard_env_gate_off_skips_daemon`
- `daemon_cancellation_drains_within_one_second`
- `ipc_handler_returns_live_state_after_daemon_writes`
- `daemon_spawn_advances_state_off_uninitialized`
- `dual_safeguard_risk_config_disabled_short_circuits`
- `daemon_evaluate_cadence_within_tolerance`

### Python pytest（從 `~/BybitOpenClaw/srv` + `PYTHONPATH=.`，7 target 檔）

| 引擎 | passed | failed | Mac 對應 | delta | 跑 1 | 跑 2 |
|---|---:|---:|---:|---:|---|---|
| Python pytest（7 files） | 263 | 0 | 163 | +100 (Linux 收集到較多 case) | ✅ | ✅ 同綠 |

Mac 報 163，Linux 報 263，差異原因為 collection — Linux `/usr/bin/python3` 對 `test_strategist_agent.py` / `test_multi_agent_framework.py` 等檔成功 collect 全部 parametrize 化的 case，部份 Mac 上跳過的 cases 在 Linux 都跑了（無 fail，263 ≥ 163 為硬條件，達標）。

涵蓋檔（cmdline order）：
1. `test_strategist_cognitive_w1_fix.py`（G8-01 W1 +6 sanity）
2. `test_strategist_agent.py`
3. `test_scout_integration.py`（MAF-SPLIT post-extract integration）
4. `test_scout_audit_wiring.py`
5. `test_multi_agent_framework.py`
6. `test_h_state_query_handler.py`
7. `test_strategist_audit_wiring.py`

5 個 DeprecationWarning 為 `record_ollama_call` 棄用提示，非 regression（已在原 baseline）。

### 跑兩遍結果（flaky 檢查）

| 工程 | 1st run | 2nd run | flaky? |
|---|---|---|---|
| Rust lib | 2290/0 | 2290/0 | N |
| Python pytest 7 | 263/0 | 263/0 | N |

所有兩遍同綠，無 flake。

### Healthcheck full sweep（passive_wait_healthcheck.py）

`set -a; source secrets env files; set +a; python3 helper_scripts/db/passive_wait_healthcheck.py`

- **總計：32 PASS lines + 0 FAIL + 1 WARN**
- 唯一 WARN [11] `counterfactual_clean_window_growth`（post-P013-clean n_rows=226/200=113%, ETA ~0d at current rate）— 非本 wave 引入，被動等待 progress 正常；下次 cron 6h cycle 應升 PASS
- 新 G3-09 Phase A check `[30] cost_edge_advisor_status`：PASS（`OPENCLAW_COST_EDGE_ADVISOR=unset (≠'1') — env=0 dormant by design (Phase A: 0 trade impact even when activated); skip`）— 對應 PA 設計，Phase A 預期 dormant，G3-09 接線預檢通過
- 既有 28+ check 全 PASS，包括 [13] `edge_estimator_scheduler_fresh age=0.9h, cells=70` / [14] `exit_features_accumulation_rate ratio=7.66`（healthy）/ [Xa] `leader_election_health leader_pid=3090462 alive` / [27] `intents_counter_freeze` 三模 stale ≤21m

## 新增測試清單（本 wave）

| 文件 | tests | scope |
|---|---:|---|
| `rust/openclaw_engine/tests/test_cost_edge_advisor_daemon.rs` | 6 | 邊界 + 並發 + 安全（dual safeguard env+risk_config gating, cancellation drain, IPC live-state read after daemon write, cadence tolerance, env gate off skips spawn） |
| `program_code/.../tests/test_strategist_cognitive_w1_fix.py` | 6 | BUG-A rename + BUG-B caller wiring（CognitiveModulator dead-path 邊界 + 收斂） |

## Mock 審查

| Test | mock 內容 | OK? |
|---|---|---|
| `test_cost_edge_advisor_daemon.rs` | env vars + RiskConfig fragments only（no business logic mock）；daemon spawn 真跑 + IPC channel 真跑 + cancel token 真跑 | ✅ |
| `test_strategist_cognitive_w1_fix.py` | CognitiveModulator 真實化 init + caller 真實 call path；only stub Operator-injected upstream signals | ✅ |

無 mock 業務邏輯違規。

## 浮點一致性

本 wave 無 indicator / 計算函數變動 — N/A。

## SLA 壓測

本 wave 無 hot-path 變動（MAF-SPLIT 為純 file-level 抽取 + 0 邏輯變更；G8-01 W1 為 dead-path 救活非 hot-path 改動；G3-09 Phase A daemon 為背景 task gated by env，預設 dormant）— N/A，但 daemon test `daemon_evaluate_cadence_within_tolerance` 已對 cadence 做容差驗證。

## 結論

**PASS** — Wave IV 全綠，無 regression：
- Rust lib 2290/0 baseline 完美維持
- Rust 新 daemon 整合 6/0 全綠（兩條獨立 process safeguard 可驗）
- Python pytest 7 files 263/0 兩遍同綠
- Healthcheck 32 lines / 0 FAIL / 1 WARN（pre-existing [11]）
- 新增 [30] cost_edge_advisor_status check 預檢 dormant（per PA Phase A 設計）

LiveDemo runtime 不受影響（本 wave 0 Rust src diff 進 hot path，engine PID 1319839 / 2033577 series 無需 `--rebuild`；test binary rebuild 無關 runtime engine binary）。

## 退回 E1 修復清單

無 — Wave IV 不需打回 E1。
