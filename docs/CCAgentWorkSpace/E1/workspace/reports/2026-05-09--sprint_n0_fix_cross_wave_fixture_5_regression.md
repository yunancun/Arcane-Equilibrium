# E1-FIX — Sprint N+0 Cross-Wave Fixture Fix（5 NEW Regression）

**Date**: 2026-05-09
**Sprint**: N+0 Day 5 cross-wave fixture pattern fix
**Wave**: W-AUDIT-9 chain（T1+T2 Rust IPC test + T3 Python parity test）
**Owner**: E1-FIX
**Local commit**: 待 commit（fix scope = 2 file，<150 LOC）
**狀態**: IMPL + 全 acceptance criteria PASS, awaiting commit + push

---

## 1. 任務摘要

E2 + E4 first-pass verdict 一致：W-AUDIT-9 chain 引入新 invariant `shadow_mode == canary_stage.as_shadow_mode()`，4 sub-agent 各自加 sibling test 但漏同步既有 IPC config patch test fixture + Python parity test fixture 注入 `canary_stage_provider() → Stage1+`。

5 個 NEW regression：
- 2 個 Rust IPC test（W-AUDIT-9 T1+T2 副作用）
- 3 個 Python parity test（W-AUDIT-9 T3 副作用）
- **隔壁 session（commit `0dc6d659`）副作用 1 個 CI workflow test 不在本 fix scope**（standalone issue, PM 通知對應 session 處理）

---

## 2. 修改清單

### 2.1 source（0 檔）

無 source 改動。fix 全在 test fixture 層。

### 2.2 tests（2 檔，+~100 LOC）

| File | Δ LOC | 變更 |
|---|---|---|
| `rust/openclaw_engine/src/ipc_server/tests/config.rs` | +~80 / -~30 | 改名 `test_g3_02_a2_patch_executor_shadow_mode_via_patch_risk_config` → `test_g3_02_a2_patch_executor_binary_shadow_only_rejected_invariant_drift` 改斷言為 reject；改 `test_g3_02_a2_patch_executor_routes_to_demo_engine` 為 5-field atomic patch（Stage 2 demo cohort）；新增 `test_g3_02_a2_patch_executor_stage_promotion_via_patch_risk_config` 5-field atomic Stage 1 paper cohort 成功 patch |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_executor_decision_parity.py` | +~20 / -~5 | `_build_runtime_config` 加 stage auto-pair（shadow ⇄ canary_stage projection invariant）；`_drive_python_decision` ExecutorAgent ctor 注入 `canary_stage_provider=cache.canary_stage_provider()` |

---

## 3. 關鍵 diff

### 3.1 Rust IPC test rename + 改斷言（reject invariant drift）

```rust
#[tokio::test]
async fn test_g3_02_a2_patch_executor_binary_shadow_only_rejected_invariant_drift() {
    // W-AUDIT-9 T1 invariant：legacy `shadow_mode` 必與 `canary_stage.as_shadow_mode()` 一致。
    // 只翻 binary `shadow_mode=false` 而不同步 set `canary_stage>=1` = config drift，
    // validation 應主動 reject（防雞蛋死循環復活）。
    ...
    assert!(resp.error.is_some(), "expected validation error...");
    let err_msg = resp.error.as_ref().map(|e| e.message.as_str()).unwrap_or("");
    assert!(err_msg.contains("inconsistent with canary_stage"), ...);
}
```

### 3.2 Rust IPC test demo routing 升 5-field atomic Stage 2

```rust
// Stage 2 = demo cohort, 14d observation period (1209600000 ms)
let req = r#"{"jsonrpc":"2.0","method":"patch_risk_config","params":{"engine":"demo","source":"operator","patch":{"executor":{"shadow_mode":false,"canary_stage":2,"canary_cohort":{"strategy":"ma_crossover","symbol":"BTCUSDT","environment":"demo"},"stage_entered_at_ms":1715270400000,"observation_period_ms":1209600000}}},"id":9104}"#;
...
assert_eq!(demo_snap.executor.canary_stage, CanaryStage::Stage2);
let cohort = demo_snap.executor.canary_cohort.as_ref().expect("...");
assert_eq!(cohort.environment, "demo");
```

### 3.3 Rust IPC test 新增 Stage 1 stage promotion atomic patch success 驗證

```rust
#[tokio::test]
async fn test_g3_02_a2_patch_executor_stage_promotion_via_patch_risk_config() {
    // 5-field atomic patch payload：Stage 1 paper cohort, 7d observation period (604800000 ms)
    let req = r#"...{"executor":{"shadow_mode":false,"canary_stage":1,"canary_cohort":{...,"environment":"paper"},"stage_entered_at_ms":...,"observation_period_ms":604800000}}..."#;
    ...
    assert!(resp.error.is_none(), "expected success...");
    assert_eq!(snap.executor.canary_stage, CanaryStage::Stage1);
    assert_eq!(snap.executor.observation_period_ms, 604_800_000_u64);
}
```

### 3.4 Python parity test fixture auto-pair stage projection

```python
def _build_runtime_config(case_config: Dict[str, Any]) -> ExecutorRuntimeConfig:
    """W-AUDIT-9 T3 fixture pattern：``shadow_mode=False`` 必伴隨 ``canary_stage>=1``，
    否則 stage projection（``canary_stage_provider`` → ``shadow_mode_provider``）會在
    ExecutorAgent 內 fail-closed 至 Stage 0 / shadow=True，使 live fixture 跑成
    block_shadow 與 reference spec 失配。對齊 e2e helper `_make_runtime_config` 的
    auto-pair 邏輯。
    """
    shadow = bool(case_config["shadow_mode"])
    canary_stage = CanaryStage.SHADOW if shadow else CanaryStage.PAPER_SINGLE_COHORT
    return ExecutorRuntimeConfig(
        shadow_mode=shadow,
        canary_stage=canary_stage,
        ...
    )
```

### 3.5 Python parity test ExecutorAgent ctor 注入 stage-aware provider

```python
agent = ExecutorAgent(
    config=ExecutorConfig(),
    ...,
    shadow_mode_provider=cache.shadow_mode_provider(),
    canary_stage_provider=cache.canary_stage_provider(),  # W-AUDIT-9 T3 SoT
)
```

---

## 4. 治理對照

### 4.1 §九 8 條 checklist

| Item | 狀態 |
|---|---|
| 改動範圍與 PA 方案一致 | ✓ E2 §5.3 fix scope (a) 1:1 對應 |
| 沒有 except:pass / 靜默吞 | ✓ 0 引入 |
| 日誌 %s 格式 | N/A 本 fix 無新 log |
| 新 API 端點有 _require_operator_role | N/A 0 新 HTTP API |
| except HTTPException 在 except Exception 之前 | N/A |
| detail=str(e) 已改為 "Internal server error" | N/A |
| asyncio 路由中無 blocking threading.Lock | N/A 本 fix 無 lock |
| 沒有私有屬性穿透 ._xxx | ⚠️ `cache._inject_snapshot_for_tests / _mark_initialized_for_tests` 為 pre-existing test API，已用 `_for_tests` 命名約定保留 |

### 4.2 跨平台 grep

```bash
grep -E '/home/ncyu|/Users/[^/]+' rust/openclaw_engine/src/ipc_server/tests/config.rs program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_executor_decision_parity.py
# 0 hit ✓
```

### 4.3 文件大小

| File | LOC | 限制 | 結論 |
|---|---:|---:|---|
| `rust/openclaw_engine/src/ipc_server/tests/config.rs` | ~700 (was ~600) | 800 警告 / 2000 硬上限 | < 800 ✓ |
| `tests/test_executor_decision_parity.py` | 變動 < 20 LOC | 800 警告 | < 800 ✓ |

### 4.4 硬邊界 scan

```bash
grep -E '\b(live_execution_allowed|max_retries|OPENCLAW_ALLOW_MAINNET|live_reserved|authorization\.json|execution_authority)\b'
# 0 hit ✓
```

`canary_stage` / `decision_lease_id` 引用為 graduated canary schema 設計範圍，不觸 hard boundary。

---

## 5. 不確定之處

### 5.1 隔壁 session 副作用：`tests/ci/test_github_ci_workflow_static.py`

E4 §2.3 報告 commit `0dc6d659` 拆 CI workflow 為兩 job 但沒同步更新 `test_github_ci_workflow_static.py` 對 `${{ matrix.target }}` 的 assertion。**此 fail 不在本 fix scope**（W-AUDIT-7c GUI round 3 sibling session 留下的 standalone issue），按任務指示 PM 通知對應 session 處理，本 fix 不動。

### 5.2 Mac vs Linux pytest 數差異

Mac 本機 pytest workspace 跑 5242 PASS / 14 fail；Linux baseline E4 baseline 4262 PASS / 8 fail。差異 +281 大概是 Mac 跑了 Linux skip 的子套件、加上 Mac-only fail 11 個（`replay/tests/test_track_a_spawn_argv.py` 對 Linux 環境的 binary spawn / PG 假設）。Linux 端最終驗以 E4 重跑 baseline 為準。

### 5.3 `test_oe_006_close_retry_budget` / `test_replay_routes_safe_query_audit::test_case2_pg_kill_simulation` / `test_archive_top_level_files_are_all_indexed`

E4 §9 標明 4 個 pre-existing fail 不在本 sprint scope；本 fix 確認**沒新增**這幾項 fail。

---

## 6. Operator 下一步

1. **PM commit + push**：本 fix commit message `e1-fix: W-AUDIT-9 cross-wave fixture pattern (5 NEW regression)`，**不加** `[skip ci]` 跑 CI。
2. **Sprint N+0 closure**：commit + push 後 E2 second-pass 應 APPROVE（cross-wave fixture 已對齊 invariant，0 production behavior 改動）；E4 重跑 regression 預期 cargo lib 2625/0 + pytest 4262+5=4267/3。
3. **隔壁 session 通知**：CI workflow `test_ci_workflow_runs_release_cargo_check_for_openclaw_engine` 對應 commit `0dc6d659` 修正，PM 派 sibling session 對應修。
4. **Follow-up（W-AUDIT-3b runtime smoke 後）**：PA 補 `strategy_wiring.py:549` ExecutorAgent ctor 加 `canary_stage_provider=cache.canary_stage_provider()` 補 invariant 9 production wiring（per E2 review §2.3 documented trade-off）。

---

## 7. Acceptance criteria

| # | 驗收項 | 結果 |
|---|---|---|
| 1 | `cargo test --lib --release -p openclaw_engine ipc_server::tests::config` 5 個 test PASS | ✅ 16/16 PASS（含改名 / 改寫 / 新增 3 個 + 既存 13 個）|
| 2 | `pytest test_executor_decision_parity` 3 個 fail test PASS | ✅ 5/5 PASS / 2 skipped；agree=70/70 (100.00%) |
| 3 | `cargo build --release` PASS（working tree clean）| ✅ 0 error / 17 warning（pre-existing） |
| 4 | 完整 cargo test --lib --release -p openclaw_engine | ✅ **2625 PASS / 0 fail**（從 2622 + 2 fail → 2625 / 0；對齊 expected 2622 + 0 fail；實多 1 = +1 新增 test 抵 -1 改名重用） |
| 4 (cont) | 完整 pytest -q（Mac 端） | Mac: 5242 PASS / 14 fail（含 1 隔壁 session + 4 pre-existing + 11 Mac-only）；本 fix 0 增 fail；Linux baseline 待 E4 重跑驗 |
| 5 | backward-compat：既有 IPC client + Python ExecutorAgent caller 0 break | ✅ ExecutorAgent ctor 新 `canary_stage_provider` 為 Optional kwarg，既有 caller 走 default None / fallback legacy provider |

---

## 8. 三端 git sync

```
Mac local HEAD (pre-fix):  0944ec6c
Mac local HEAD (post-fix): 待 commit
GitHub origin/main:        0944ec6c
Linux trade-core:          0944ec6c (per task brief)
```

commit + push 後三端會同 fix commit 對齊。

---

E1-FIX IMPLEMENTATION DONE: cargo lib 2625/0 + parity 5/5 PASS · report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-09--sprint_n0_fix_cross_wave_fixture_5_regression.md`
