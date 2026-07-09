# E2 Sprint N+0 Second-Pass Review — E1-FIX Cross-Wave Fixture Pattern (5 NEW)

- **日期**：2026-05-09
- **Mac local HEAD**：`11849c18` (E1-FIX commit)
- **review scope**：E1-FIX commit `11849c18` 是否覆蓋 first-pass §E1-A 3 條 RETURN scope（**不 re-review** 4 wave IMPL；first-pass APPROVE 已 land at `87f92e69`）
- **依據**：first-pass `2026-05-09--sprint_n0_first_pass_review.md` + E1-FIX report + E4 baseline `2026-05-09--sprint_n0_regression_baseline.md`

---

## TL;DR Verdict — APPROVE

| 項 | 結論 |
|---|---|
| **First-pass §E1-A 3 條 fix scope 覆蓋** | ✅ 1:1 對應 |
| **E4 §3.x 3 個 Python parity test 真 fix** | ✅ 70/70 (100.00%) |
| **22 invariant 9 (fail-closed Stage 0) 二次驗** | ✅ injection 正確 |
| **22 invariant 10 (Stage 0 binary fail-closed 4 範圍) 二次驗** | ✅ 仍保留 |
| **Backward-compat 0 break** | ✅ Optional kwarg |
| **隔壁 session CI workflow test** | flag PM (commit `0dc6d659` 副作用，不在本 fix scope) |
| **整體 verdict** | **APPROVE** sub-pass W-AUDIT-9 chain（除 P1 follow-up） |

---

## §1 First-Pass §E1-A 3 條 Fix Scope 覆蓋驗證

E1-FIX commit `11849c18` 對 `rust/openclaw_engine/src/ipc_server/tests/config.rs` 三處改動 1:1 對應 first-pass §1.2 Fix scope (a)：

| First-pass scope | E1-FIX 對應 | 驗證 |
|---|---|---|
| (1) `:426` 重命名 `test_g3_02_a2_patch_executor_shadow_mode_via_patch_risk_config` → `test_g3_02_a2_patch_executor_binary_shadow_only_rejected_invariant_drift` + 斷言 patch error | E1-FIX diff line 426-498 確實重命名 + `assert!(resp.error.is_some(), ...)` + `err_msg.contains("inconsistent with canary_stage")` + paper version 不變斷言 + paper.executor.shadow_mode 仍 true 斷言 | ✅ |
| (2) `:549` `test_g3_02_a2_patch_executor_routes_to_demo_engine` 改 5-field atomic + environment="demo" + canary_stage=2 | E1-FIX diff line 639-691 改 patch payload 為 5-field atomic（shadow_mode=false + canary_stage=2 + canary_cohort{strategy,symbol,environment="demo"} + stage_entered_at_ms + observation_period_ms=1209600000=14d）+ 加 demo.canary_stage==Stage2 + cohort.environment=="demo" + paper.canary_stage==Stage0 (untouched) 斷言 | ✅ |
| (3) 新增 `test_g3_02_a2_patch_executor_stage_promotion_via_patch_risk_config` Stage 1 promotion success | E1-FIX diff line 502-562 確實新增 — 5-field atomic（Stage 1 paper cohort 7d period=604800000）+ `resp.error.is_none()` + 全欄位 verify（canary_stage==Stage1 + cohort.strategy=="ma_crossover" + cohort.symbol=="BTCUSDT" + cohort.environment=="paper" + stage_entered_at_ms + observation_period_ms） | ✅ |

E2 重跑：`cargo test --lib --release -p openclaw_engine ipc_server::tests::config` = **16 passed / 0 failed** (was 13/2 fail at HEAD `f5574c5a`)。

E2 重跑：`cargo test --lib --release -p openclaw_engine` = **2625 passed / 0 failed**（從 2622+2 → 2625+0；+3 = 改名 1 + 新增 1 + 抵舊 1 重用，對齊 E1-FIX acceptance #4 預期）。

**結論**：first-pass §E1-A 3 條 RETURN scope **完整覆蓋**，無遺漏。

---

## §2 E4 §3.x 3 個 Python Parity Test 真 Fix 驗證

E1-FIX 對 `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_executor_decision_parity.py` 兩處改動：

### 2.1 `_build_runtime_config` stage auto-pair 邏輯正確

```python
shadow = bool(case_config["shadow_mode"])
canary_stage = CanaryStage.SHADOW if shadow else CanaryStage.PAPER_SINGLE_COHORT
return ExecutorRuntimeConfig(
    shadow_mode=shadow,
    canary_stage=canary_stage,
    ...
)
```

✅ 對齊 W-AUDIT-9 §4.4 invariant：shadow=True ⇄ Stage 0 (SHADOW)；shadow=False ⇄ Stage 1 (PAPER_SINGLE_COHORT) projection。
✅ 對齊 e2e helper `test_executor_shadow_to_live_e2e.py::_make_runtime_config` 既有 auto-pair pattern。
✅ 不違 first-pass §2.3 MED-1 邊界（legacy False → Stage 1 投影；既然 fixture 走 atomic stage-aware path，本 helper 直譯 stage 邏輯，不繞過）。

### 2.2 `_drive_python_decision` ExecutorAgent ctor injection

```python
agent = ExecutorAgent(
    config=ExecutorConfig(),
    ...,
    shadow_mode_provider=cache.shadow_mode_provider(),
    canary_stage_provider=cache.canary_stage_provider(),  # W-AUDIT-9 T3 SoT
)
```

✅ 同時注入兩 provider — `canary_stage_provider` 為 stage-aware SoT 主路徑（priority 1 per `_read_canary_stage` line 789），`shadow_mode_provider` 為 backward-compat 雙保險（priority 2 fallback）。
✅ 與 first-pass §2.3 MED-1 documented W-AUDIT-3b follow-up 一致（fixture 已 wired，production caller `strategy_wiring.py:549` 仍待補）。

### 2.3 agree_rate 70/70 100% PASS 數據可信

E2 重跑：`pytest test_executor_decision_parity.py -q` = **5 passed / 2 skipped**

```
[G8-02 golden] agree=30/30 (100.00%)
[G8-02 synthetic_handcrafted] agree=40/40 (100.00%)
[G8-02 OVERALL] agree=70/70 (100.00%) — threshold 95% (≥67/70)
```

✅ 從 30 disagree (E4 first-pass) → 0 disagree。E1-FIX claim 70/70 100% 與 E2 重跑一致。

---

## §3 22 Invariant 對應項補 Verdict

| # | Invariant | Second-pass 驗證 |
|---|---|---|
| 9 | fail-closed Stage 0（任何錯誤路徑） | ✅ E1-FIX 注入 `canary_stage_provider` 走 `_read_canary_stage` priority 1（line 789），exception → SHADOW (line 810)；priority 2 legacy fallback line 813-833；priority 3 雙 None → SHADOW line 836-843。三 critical path 全 fail-closed Stage 0 |
| 10 | Stage 0 binary fail-closed 4 範圍（DOC-08 §12 / SM-04 / Live 5-gate / §二 16）| ✅ 仍保留：4 TOML default `shadow_mode=true` + `canary_stage=0`；E1-FIX 不動 4 範圍硬不變式；hard-boundary scan 0 hit |
| Backward-compat | 既有 caller 0 break | ✅ ExecutorAgent ctor `canary_stage_provider: Optional[Callable] = None`（executor_agent.py:186）— 既有 caller 走 default None → fallback 到 legacy `shadow_mode_provider` projection；production caller `strategy_wiring.py:549` 未注入 = 仍走 legacy fallback 不破。Production runtime `shadow_mode_provider` 回 True (Stage 0 default) → fallback path 2a → SHADOW，行為一致 |

---

## §4 隔壁 Session CI Workflow Test Fail（不在本 fix scope）

### 4.1 Confirm commit `0dc6d659` 副作用

E2 git log 確認：commit `0dc6d659 ci: 拆兩個 job 取代 matrix if（修上次 workflow parse failure）` 在 W-AUDIT-9 chain（094f9914 / 200188ad / 063f12d0 / 4a90966a）**之前** push。E4 first-pass §2.3 抓出 `tests/ci/test_github_ci_workflow_static.py::test_ci_workflow_runs_release_cargo_check_for_openclaw_engine` 因 workflow 從 matrix 拆兩 job 後 `${{ matrix.target }}` 變數消失 → assertion fail。

### 4.2 與 W-AUDIT-9 chain 無關

✅ Confirm `0dc6d659` 副作用 standalone：
- root cause = `.github/workflows/ci.yml` 拆兩 job pattern 改變
- W-AUDIT-9 chain 4 commit 無動 `.github/workflows/*` 
- `tests/ci/test_github_ci_workflow_static.py:19` assertion 對舊 matrix structure；新拆兩 job 應 grep 兩個獨立 `rustup target add x86_64-unknown-linux-gnu` + `aarch64-apple-darwin`

### 4.3 PM follow-up 通知對應 session

E1-FIX report §5.1 已標明「不在本 fix scope」+ 通知對應 session 處理。E2 second-pass **flag PM**：派 sibling session（W-AUDIT-7c GUI round 3 chain 或 ci workflow owner）修 `tests/ci/test_github_ci_workflow_static.py:19` assertion。

**Fix 建議**：assertion 改成驗 `rustup target add x86_64-unknown-linux-gnu` + `aarch64-apple-darwin` 兩個獨立 hard target（per E4 first-pass §2.3）。

---

## §5 Follow-up 確認

### 5.1 W-AUDIT-3b runtime smoke 後 PA P1 follow-up（仍 active）

E2 first-pass §2.3 MED-1 documented 的 W-AUDIT-3b follow-up：

**仍待**：`strategy_wiring.py:549` 生產 caller 確認未注入 `canary_stage_provider`（E2 grep 確認 line 549-557 ExecutorAgent ctor 僅注入 `shadow_mode_provider=_EXECUTOR_CONFIG_CACHE.shadow_mode_provider()`）。

**狀態**：W-AUDIT-3b runtime smoke 後 PA 補 P1 follow-up：
```python
EXECUTOR_AGENT = ExecutorAgent(
    ...,
    shadow_mode_provider=_EXECUTOR_CONFIG_CACHE.shadow_mode_provider(),
    canary_stage_provider=_EXECUTOR_CONFIG_CACHE.canary_stage_provider(),  # ← TODO
    ...
)
```

**E2 verdict**：本 follow-up 不阻 second-pass APPROVE。理由：
1. 當前 production 4 TOML 全 `shadow_mode=true` + Stage 0 default → 走 `_read_canary_stage` path 2a（legacy True → SHADOW）保持 Stage 0 行為
2. 若 IPC patch 未來 atomic set Stage 1+，production caller 仍 fallback 至 legacy provider → 投影 Stage 1（不是真 Stage 1+/2/3）但本 trade-off 在 first-pass §2.3 MED-1 已 documented accept
3. fixture (parity test) 已 wired stage-aware injection，0 production exposure

**Acceptance criteria**：W-AUDIT-3b runtime smoke land 必含：「`strategy_wiring.py:549` ExecutorAgent ctor 必同時注入 `canary_stage_provider`」。

### 5.2 governance_core.rs 1838 LOC P2（first-pass MED-2）

不阻 second-pass。仍 P2 follow-up。

### 5.3 TODO.md v19 §7 DSR mu_0 文字修正（first-pass MED-3）

已在 `0944ec6c` commit 修（log₁₀ → ln）。E2 second-pass confirm。

### 5.4 V080 COMMENT 文字密度（first-pass LOW-1）

不阻 merge，P3 可選。

---

## §6 §九 + OpenClaw 9 條 Combined Checklist（fix delta）

### §九 8 條（PASS All）

| Item | 狀態 |
|---|---|
| 改動範圍與 PA 方案一致（E2 first-pass §1.2 Fix scope (a)）| ✓ 1:1 對應 |
| 沒有 except:pass / 靜默吞 | ✓ E1-FIX 0 引入 |
| 日誌 %s 格式 | N/A 本 fix 無新 log |
| 新 API 端點有 _require_operator_role | N/A |
| except HTTPException raise 在 except Exception 之前 | N/A |
| detail=str(e) 已改為 "Internal server error" | N/A |
| asyncio 路由中無 blocking threading.Lock | N/A 本 fix 無 lock |
| 沒有私有屬性穿透 ._xxx | ⚠️ `cache._inject_snapshot_for_tests / _mark_initialized_for_tests` pre-existing test API（per E1-FIX §4.1）— 用 `_for_tests` 命名約定保留，**不阻 merge** |

### OpenClaw 9 條（除 cross-session CI 外 All PASS）

| Item | 狀態 |
|---|---|
| 跨平台 grep（/home/ncyu / /Users/[^/]+） | ✓ E2 verify 0 hit on E1-FIX diff |
| 雙語注釋（默認中文）| ✓ 新加注釋中英對照（E1-FIX line 426-498 / line 502-562 / line 639-691 + Python helper docstring 中英並列）|
| Rust unsafe 零容忍 | ✓ 0 unsafe |
| 跨語言 IPC schema | ✓ 5-field atomic patch payload 對齊 Rust ExecutorConfig schema（canary_stage int 0..=4 / canary_cohort 三欄位 string / stage_entered_at_ms i64 / observation_period_ms u64）|
| Migration Guard A/B/C | N/A 本 fix 不動 SQL migration |
| healthcheck 配對 | N/A 本 fix 不新增「被動等待」TODO |
| Singleton 登記 §九 表 | ✓ 本 fix 0 新 singleton |
| 文件大小 800/2000 | ✓ `config.rs` ~700 (was ~600) < 800 ✓；`test_executor_decision_parity.py` Δ < 20 LOC < 800 ✓ |
| Bybit API 改動先查字典手冊 | N/A |

### 硬邊界 scan

```bash
grep -E '\b(live_execution_allowed|max_retries|OPENCLAW_ALLOW_MAINNET|live_reserved|authorization\.json|execution_authority)\b' <fix-scope>
# 0 hit ✓
```

✓ 0 hard-boundary mutation。`canary_stage` / `decision_lease_id` 引用為 graduated canary schema 設計範圍，per first-pass §6 invariant 11。

---

## §7 對抗反問 5 條（second-pass 限定）

### Q1：「E1-FIX 說 cargo test 16/16 PASS — E2 真重跑？」

A：✓ E2 重跑 `cargo test --lib --release -p openclaw_engine ipc_server::tests::config` = 16 passed / 0 failed / 2609 filtered out / finished in 0.00s。E2 重跑 full lib regression 2625/0 對齊 E1-FIX acceptance #4。**評估**：E1-FIX claim 真實。

### Q2：「E1-FIX 說 70/70 (100%) — 真 30 個 live fixture 都對齊？」

A：✓ E2 重跑 `pytest test_executor_decision_parity.py -q`：
```
[G8-02 golden] agree=30/30 (100.00%)
[G8-02 synthetic_handcrafted] agree=40/40 (100.00%)
[G8-02 OVERALL] agree=70/70 (100.00%) — threshold 95% (≥67/70)
```
從 30 disagree → 0 disagree。30 個 live fixture (10 golden live + 20 synthetic live) 全對齊。**評估**：E1-FIX claim 真實。

### Q3：「Backward-compat 真不破？production caller 仍 fallback 路徑工作？」

A：✓ E2 grep `strategy_wiring.py:549-557` 確認生產 caller 仍只注入 `shadow_mode_provider`（未注入 `canary_stage_provider`）。E2 trace `_read_canary_stage` priority chain：
- priority 1（`canary_stage_provider`）= None → skip
- priority 2（legacy `shadow_mode_provider`）= cache.shadow_mode_provider()（4 TOML default True → SHADOW）
- 結果：production runtime stage = SHADOW (Stage 0)，行為一致 4 TOML default

ExecutorAgent ctor `canary_stage_provider: Optional[Callable] = None`（line 186）= 既有 caller 0 break。**評估**：backward-compat 0 break verified。

### Q4：「invariant 9 Stage 0 fail-closed 真三 path 全保留？」

A：✓ `_read_canary_stage` priority chain：
- (priority 1.c) canary_stage_provider exception → catch → log warning → return SHADOW (line 810)
- (priority 2.c) shadow_mode_provider exception → catch → log warning → return SHADOW (line 833)
- (priority 3) 雙 None → log warning → return SHADOW (line 843)

三 critical path 全 SHADOW (Stage 0)。E1-FIX **不動** `_read_canary_stage` 邏輯（fix 只動 fixture 層 + injection），所以 first-pass §2.1 invariant 9 verdict 仍有效。**評估**：invariant 9 fail-closed Stage 0 嚴格保留。

### Q5：「invariant 10 Stage 0 binary fail-closed 4 範圍真不破？」

A：✓ E1-FIX 0 動 4 TOML risk_config*.toml；0 動 DOC-08 §12 / SM-04 / Live 5-gate / §二 16 原則代碼路徑；hard-boundary grep 0 hit。E1-FIX 改動限：
- `rust/openclaw_engine/src/ipc_server/tests/config.rs`（test fixture only）
- `tests/test_executor_decision_parity.py`（test fixture only）

0 source 改動。**評估**：invariant 10 嚴格保留。

---

## §8 Findings 總表

| 嚴重度 | 位置 | 描述 | 建議修法 | Owner |
|---|---|---|---|---|
| INFO-1 | `tests/ci/test_github_ci_workflow_static.py:19` | 隔壁 session commit `0dc6d659` 副作用（CI workflow 拆兩 job）| assertion 改成驗兩個獨立 `rustup target add x86_64-unknown-linux-gnu` + `aarch64-apple-darwin`；不在本 W-AUDIT-9 chain scope | PM 派 sibling session 處理 |
| FOLLOW-1 | `strategy_wiring.py:549` | production caller 仍未注入 `canary_stage_provider`（W-AUDIT-3b runtime smoke 後 P1 follow-up）| 加 `canary_stage_provider=_EXECUTOR_CONFIG_CACHE.canary_stage_provider()` 補 invariant 9 production wiring | PA after W-AUDIT-3b smoke |

### Severity 分級

- **CRITICAL**：0
- **HIGH**：0（first-pass HIGH-1 已被 E1-FIX 解，0 殘留）
- **MEDIUM**：0（first-pass MED-1/-2/-3 在 second-pass 範圍內 = MED-3 已 commit `0944ec6c` 修；MED-1/-2 為 documented follow-up 不阻 second-pass）
- **LOW**：0
- **INFO/FOLLOW**：2（隔壁 session CI workflow + W-AUDIT-3b runtime wiring）

---

## §9 PASS Rate（second-pass 限定）

- **E1-A 3 條 fix scope 覆蓋**：3/3 PASS
- **Python parity 3 個 fail test 真 fix**：3/3 PASS（70/70 agree=100%）
- **22 invariant 9 + 10 二次驗**：2/2 PASS
- **backward-compat**：0/0 break
- **隔壁 session CI workflow 副作用 confirm**：1/1 confirmed (commit `0dc6d659`)
- **整體**：5/5 acceptance criteria PASS

---

## §10 結論

**APPROVE** sub-pass W-AUDIT-9 chain（除 P1 follow-up）。

E1-FIX commit `11849c18` 完整覆蓋 first-pass §E1-A 3 條 RETURN scope；2 個 Rust IPC test rename + 改寫 + 1 個新增 stage promotion test、3 個 Python parity test fixture auto-pair + injection 全 verified；cargo lib 2625/0 + parity 70/70 真實。22 invariant 9 + 10 嚴格保留；backward-compat 0 break。

### Pass to E4 Round 2 Regression

E4 重跑 sprint N+0 full regression 預期：
- cargo lib `openclaw_engine` 2622+2 fail → 2625+0 fail（已 verified at HEAD `11849c18`）
- pytest tests/ + control_api_v1/tests/ 4262+8 fail → 4267+3 fail（4 pre-existing - 1 fix CI = 3 fail？取決於 PM 是否 dispatch sibling session 處理 `tests/ci/test_github_ci_workflow_static.py`）
- 預期 W-AUDIT-9 chain 5 NEW fail 全消，剩 4 pre-existing fail

### 不阻 second-pass approve

1. CI workflow test fail = 隔壁 session `0dc6d659` 副作用，PM 派對應 session 處理
2. W-AUDIT-3b runtime smoke 後 PA `strategy_wiring.py:549` 補 `canary_stage_provider` 仍 P1 follow-up
3. governance_core.rs 1838 LOC、V080 COMMENT、test_executor_agent_unit.py 809 LOC 三項 documented P2/P3 follow-up

### Final Verdict

**APPROVE** W-AUDIT-9 chain (T1+T2 / T3 / T6 / 6d-4/5/6 / W-AUDIT-4b-M1) = 4 wave first-pass APPROVE + 1 cross-wave fixture fix APPROVE = 全 sprint N+0 IMPL 可放行 E4 round 2 regression。

---

## §11 三端 git sync

```
Mac local HEAD (post-fix):  11849c18
GitHub origin/main:         待 push (此 second-pass commit + 11849c18 fix commit)
Linux trade-core:           待 PM 同步
```

E2 second-pass 完成 → commit + push origin/main → PM 通知 sibling session（CI workflow）+ Linux pull --ff-only。

---

E2 SECOND-PASS REVIEW DONE: **APPROVE** (E1-FIX cross-wave 5 NEW 全 verified；2 documented follow-up；0 阻 second-pass approve) · report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-09--sprint_n0_second_pass_review.md`
