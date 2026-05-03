# REF-20 Final Closure — E4 Cold Test Reality Audit

**Date**: 2026-05-03
**Tester**: E4 (cold test reality auditor)
**Verdict**: **CONDITIONAL FAIL — 2 P0 + 2 P1 mis-statement in REF-20 closure doc**
**Scope**: 真實 reality check vs `2026-05-03--ref20_final_closure_and_deploy_guidance.md` 聲稱 + `2026-05-03--ref20_wave1_to_6_master_closure.md` baseline

---

## 0. TL;DR

REF-20 closure 聲稱「~3500+ Python pytest PASS / 0 fail」+「2415+ Rust lib PASS」，**Mac dev 端真實跑只有兩個聲稱對得上**：
- Rust lib `2447 PASS / 0 fail`（聲稱 `2415+` ✓ 多 +32 是 manifest_signer/replay 累積，**真實**）
- Rust integration（含 features replay_isolated）`2630 PASS / 0 fail / 0 ignored`（**真實**）

**但發現以下 mis-statement / 漏抓**：

| 級別 | 問題 | 詳情 |
|---|---|---|
| **P0** | 1 deterministic flaky pytest fail in full suite | `tests/test_replay_routes_safe_query_audit.py::test_case2_pg_kill_simulation_returns_200_degraded` 全 suite 跑 deterministic FAIL（401 vs 200），隔離跑 PASS。**REF-20 closure 自承為 pre-existing，但實則為 Wave 6 commit `eb5f106` 引入的 shared-state pollution**（`app.dependency_overrides` 跨 test 殘留）。closure doc 聲稱「0 fail」與真實衝突。 |
| **P0** | `mac_policy_guard.rs` 2 doctest fail 不是「sibling pre-existing」 | line 32 + line 88 doctest fail（中文全形括號 `（）` 在 doctest 模式被 tokenize 失敗）。**檔案是 Wave 3 commit `5a618ff` 自己寫的**，但 closure doc line 106 寫「mac_policy_guard sibling pre-existing doctest fail (Wave 3 commit 5a618ff line 32/88 ASCII matrix)」— **自引入卻聲稱 sibling pre-existing**，名詞濫用。 |
| **P1** | 4 個 wave (W4-W9) 缺 E4 regression report | E4 reports/ 只有 W2 Batch1 + W2b/W3p2a 兩份，W4-W9 commits（`4b48b6d`/`457a458`/`eb5f106`/`8429af1`/`c887e4e`/`1f5d019`/`5a7581e`）共 7 closure commit 完全沒走 E4 regression。closure doc §6 line 202 寫「⏳ E2 + E4 + MIT + FA + QA review sign-off」但實則 W4-W9 全部跳 E4。**違反 CLAUDE.md §八 強制工作鏈「E2 + E4 永不跳」**。 |
| **P1** | shrinkage_router test 用 mini 200/300 chain，production 1000/2000 從未跑過 | `test_shrinkage_router.py:67/260` 設 `gibbs_warmup=200, gibbs_draws=300`；`hierarchical_bayes.py:121/122` production default `n_warmup=1000, n_samples=2000`。**不是 mock 藏邏輯**（Gibbs sampler logic 同 path），但 production scale 從未驗證收斂或 Mac/Linux 跨平台 numpy.random RNG 一致性。 |

**真實 pytest count**: **3374 PASS / 1 fail / 10 skip**（control_api_v1 全 suite，flaky deterministic）
**真實 cargo lib count**: **2447 PASS / 0 fail / 0 ignored**
**真實 cargo workspace count**: **3077 PASS / 2 fail / 3 ignored**（其中 2 fail = mac_policy_guard doctest）
**真實 cargo integration（replay_isolated feature）count**: **2630 PASS / 0 fail / 0 ignored**

兩遍 reproducible（非 flaky in transient 意義；是 deterministic shared-state pollution）。

---

## 1. Reality vs Claim 對照

### 1.1 REF-20 closure doc claims

`docs/execution_plan/2026-05-03--ref20_final_closure_and_deploy_guidance.md` line 269-270 + master closure line 162-164:
```
| pytest cumulative (Mac dev verified) | ~3500+ PASS / 0 fail (post-Wave 5 baseline regression) |
| Rust cargo test cumulative           | 2415+ lib + ~50 integration replay tests PASS |
```

### 1.2 真實 cold run 數字（Mac dev, HEAD `5a7581e`）

| 引擎 | claim | 真實 | delta | 結論 |
|---|---|---|---|---|
| Python pytest control_api_v1 全 suite | ~3500+ PASS / 0 fail | **3374 PASS / 1 fail / 10 skip** | -126 PASS / +1 fail | **claim 高估** + **聲稱 0 fail 不實**（1 deterministic flaky） |
| Python pytest learning_engine（21 case 抽樣） | n/a | 21 PASS / 0 fail | n/a | OK |
| Rust cargo test --release --lib | 2415+ | **2447 / 0 / 0** | +32 | OK（累積真實） |
| Rust cargo test --release --tests --features replay_isolated | ~50 integration | **2630 / 0 / 0**（含 lib） | n/a | OK（claim 含糊但無實質衝突） |
| Rust cargo test --release --workspace | 不明 | **3077 / 2 fail / 3 ignored** | 2 fail | **claim 0 fail 隱瞞 doctest** |

### 1.3 W2/W3 E4 報告 baseline 對照

| 度量 | W2/W3 E4 報告（last sign-off） | 本次 cold run | delta |
|---|---|---|---|
| Python control_api_v1 PASS | 3338 | 3374 | +36（W4-W9 新增） |
| Python control_api_v1 fail | 0 | **1** | **+1 NEW REGRESSION** |
| Rust lib PASS | 2415 | 2447 | +32（W4-W9 新增） |
| Rust workspace PASS | 3025 | 3077 | +52 |
| Rust workspace fail | 0 | **2** | **+2 NEW REGRESSION**（mac_policy_guard doctest） |

---

## 2. P0-1 — Python pytest deterministic flaky fail

### 失敗 trace
```
FAILED tests/test_replay_routes_safe_query_audit.py::test_case2_pg_kill_simulation_returns_200_degraded
> assert resp.status_code == 200, f"expected 200, got {resp.status_code}"
E AssertionError: expected 200, got 401
E assert 401 == 200
E  +  where 401 = <Response [401 Unauthorized]>.status_code
tests/test_replay_routes_safe_query_audit.py:217: AssertionError
```

### 根因
test 結構：
```python
app = FastAPI()
app.include_router(replay_router)
app.dependency_overrides[current_actor] = _operator_actor
client = TestClient(app)
resp = client.get("/api/v1/replay/status")  # 期待 200, 收到 401
```

**`replay_router` 是 module-level 全域 singleton**（從 `app.replay_routes` import）。前面其他 test（似 strategist_agent 或 ai_invocations 系列）已改了它的 dependency state；新 `FastAPI()` instance 註冊 router 時 dependency_overrides 沒重置，導致 `current_actor` resolution 走錯 path → 401。

### 復現驗證（兩遍 reproducible）
- Round 1: `1 failed, 3374 passed, 10 skipped, 411 warnings in 53.85s`
- Round 2: `1 failed, 3374 passed, 10 skipped, 411 warnings in 54.49s`
- 隔離跑該 test 單檔 `5 passed`；只跑 strategist_agent + audit `53 passed`。

### Wave 起源
```
$ git log --oneline 1851714..HEAD -- tests/test_replay_routes_safe_query_audit.py
eb5f106 feat(replay): Wave 6 closure — P4 advisory chain (...)
```
**Wave 6 引入**，W2/W3 E4 baseline (3338) 沒含此 test → W4-W9 沒走 E4 → fail 漏抓直到 cold run。

### closure doc 自承不實
master closure line 105：「Pre-existing test fail: `test_insert_live_candidate_payload_carries_schema_version_and_lg5_subkeys`」— 但這個 test 已不存在（cold run -k 過濾 0 match，全 deselect）。closure doc 在虛構一個已修的 test 為「pre-existing」掩蓋真正的 flaky。

---

## 3. P0-2 — mac_policy_guard.rs doctest fail (自引入卻寫 sibling pre-existing)

### 失敗 trace
```
test openclaw_engine/src/replay/mac_policy_guard.rs - replay::mac_policy_guard (line 32) ... FAILED
test openclaw_engine/src/replay/mac_policy_guard.rs - replay::mac_policy_guard (line 88) ... FAILED
error: unknown start of token: \u{ff08} '（' looks like '(' but it is not
error: unknown start of token: \u{ff09} '）' looks like ')' but it is not
```

### 根因
`//!` doctest 中文「`（不論 ENV）`」「`（任何）`」「`（本 guard 在 Linux 不 enforce）`」全形括號 → Rust doctest 引擎當 raw doctest 嘗試 tokenize → fail。

### Wave 起源（自引入確認）
```
$ git log --oneline 1851714..HEAD -- rust/openclaw_engine/src/replay/mac_policy_guard.rs
5a618ff feat(replay): forbidden_guard + mac_policy_guard + 3-layer integration (Wave 3 P2b-S8/S9 + closure)
```
**檔案 Wave 3 P2b-S9 自己寫的，2 個 doctest fail 是它自己引入**。closure doc line 106 卻寫「mac_policy_guard sibling pre-existing doctest fail」— sibling pre-existing 本意是「sibling 模組 pre-existing 失敗」，這裡是**本檔自己引入**，名詞誤用 + 規避 baseline drift exception 申請。

### 修復
在中文 doctable 用 ascii fence 或 ` ``` ` markdown code block 包裹避開 Rust doctest tokenize：
```rust
//! ```text
//!   OS           | profile        | 結果
//!   macOS        | non-Isolated   | RealDataAttemptedOnMac（不論 ENV）
//! ```
```

---

## 4. P1-1 — W4-W9 跳 E4 regression report（CLAUDE.md §八 違反）

### 證據
E4 reports/ 目錄只有：
- `2026-05-03--ref20_wave2_batch1_e4_regression.md` (W2 Batch 1)
- `2026-05-03--ref20_wave2b_wave3p2a_e4_regression.md` (W2 Batch 2 + W3 P2a)

**W3 P2b/W4/W5/W6/W7/W8/W9 共 7 closure commit 完全沒 E4 report**：
```
4b48b6d feat(replay): Wave 4 closure — isolated runner IMPL + 8 routes wire + canary + frontend retrofit
457a458 feat(replay): Wave 5 closure — P3a global calibration + P3b cell + RGM state machine (13 task)
eb5f106 feat(replay): Wave 6 closure — P4 advisory chain (DSR + PBO + DreamEngine + MLDE veto + S11/S12) (8 task)
8429af1 feat(replay): Wave 8 closure — P6 Bounded Demo Handoff (modal + cooldown + V044 + audit) (7 task)
c887e4e feat(ui): Wave 7 closure — P5 Agents Monitor 抽出 + Learning redirect notice (4 task)
1f5d019 feat(replay): Wave 9 closure — 14d gradient observation + KPI + audit incident scan + sign-off template (4 task)
5a7581e docs(ref20): final IMPL closure + operator deploy guidance (Wave 1-9 全結)
```
13 個 Wave 5 task + 8 個 Wave 6 task + 7 個 Wave 8 task + 4 個 Wave 7 task + 4 個 Wave 9 task = ~36 task 直接由 PM autonomous mode commit-and-push，跳 E4 regression。

### 違反條款
CLAUDE.md §八「P0 快速通道：E2 + E4 永不跳」+ 「強制工作鏈：`@E2` 代碼審查 → `@E4` 測試回歸（兩者絕不可跳）」

### 後果
P0-1 + P0-2 兩處 fail 都是 W4-W9 引入但漏抓 → **如果 W4-W9 走 E4 regression，這 1+2 fail 會立刻 catch 並 block closure**，不會混進 baseline 然後 closure doc 用「pre-existing」掩蓋。

---

## 5. P1-2 — shrinkage_router production scale 從未跑

### 證據
```python
# test_shrinkage_router.py:67, 260
router = ShrinkageRouter(gibbs_warmup=200, gibbs_draws=300, gibbs_seed=7)

# program_code/learning_engine/hierarchical_bayes.py:121-122
DEFAULT_N_WARMUP: int = 1000
DEFAULT_N_SAMPLES: int = 2000
```

### 結論
- 不是 mock 藏邏輯（Gibbs sampler logic 同 code path）
- 但 production 1000/2000 chain Gibbs 收斂行為從未在 CI 驗證
- numpy.random.Generator + math.sqrt 跨平台 (Mac aarch64 ↔ Linux x86_64) 1e-4 容差驗證 0 row（沒有跨語言對等 Rust port，N/A 跨語言；但跨平台對等是另一風險）

### 緩解建議
新增 1 個 production-scale smoke test（`@pytest.mark.slow`）跑 1000/2000 一次，確認 r_hat <1.05，~30s wall。否則生產初次跑時收斂 issue 將是 surprise。

---

## 6. Mock 審查（OK）

| Test | mock 內容 | 業務邏輯純度 | OK? |
|---|---|---|---|
| `test_shrinkage_router.py` | 0 mock，直接構造 prior + observed dataset | Pure | ✓ |
| `test_hierarchical_bayes.py` | 0 mock | Pure | ✓ |
| `replay_runner_e2e.rs` | fixture-loaded（fixtures/synthetic_btcusdt.json + key.hex），不打 PG | Pure（fixture-based 屬合法 unit-fixture，非 mock 業務邏輯） | ✓ |
| `replay_manifest_signer_xlang_consistency.rs` | 0 mock，HMAC-SHA256 真算 | Pure | ✓ |
| `test_replay_routes_safe_query_audit.py` | monkeypatch `get_pg_conn` → None（**正當 IO mock**） | OK 但 dep_overrides race | 邏輯 OK 但 test infra flaky |

**結論**：mock 沒掩蓋業務邏輯。0 P0 mock issue。

---

## 7. SLA Pressure tests（OK，但 replay binary 沒測）

```
test stress_full_pipeline_extreme_prices ... ok
test stress_full_pipeline_zero_volume_ticks ... ok
test stress_three_pipeline_concurrent_snapshot_writes ... ok
test stress_config_hot_reload_during_ticks ... ok
test stress_three_pipeline_concurrent_isolation ... ok
test stress_tick_latency_benchmark ... ok
test stress_10k_ticks_no_panic ... ok
35 passed / 0 failed
```

**結論**：tick latency / hot path SLA 35 case PASS。**但 REF-20 引入的 replay_runner binary 走 batch path，不影響 hot tick** → 沒專門 SLA test 是合理（replay binary != hot path）。0 P0 SLA issue。

---

## 8. 跨語言一致性 / 跨平台 floats

`test_shrinkage_router.py` Gibbs sampler 用 `numpy.random.Generator`（PCG64）+ `math.sqrt`：
- `numpy.random.Generator(PCG64(seed))` 跨平台 deterministic（PCG64 spec 寫定）
- `math.sqrt` IEEE 754 deterministic
- ∴ 同 seed Mac aarch64 vs Linux x86_64 應出同結果 — 但 0 sibling test ledger 驗證

**建議**：W4-W9 closure 跑 `ssh trade-core "cd ~/BybitOpenClaw/srv && python3 -m pytest program_code/learning_engine/tests/test_shrinkage_router.py -v"` 取 sibling baseline，並對比 Mac result（可用 `pytest --collect-only` 比對 test name + outputs hash）。

---

## 9. 兩遍 reproducibility

| 引擎 | Run 1 | Run 2 | flaky? |
|---|---|---|---|
| Python control_api_v1 | 3374 P / 1 F | 3374 P / 1 F | ✗（**deterministic shared-state pollution**） |
| Rust cargo --release --lib | 2447 P / 0 F | 2447 P / 0 F | ✗ |

deterministic shared-state pollution 比 transient flaky 更糟 — **每次都失敗，但 isolation 跑就 PASS**，意味著 test order dependency 已穩定形成。

---

## 10. 結論 / 退回 E1 修復清單

### Verdict: **CONDITIONAL FAIL**

**P0 (block closure 直到修)**：
1. **P0-1 fix `test_case2_pg_kill_simulation_returns_200_degraded` shared-state**
   - 改用 `pytest fixture` (autouse) 在 test setup 中重新建 router（`importlib.reload(app.replay_routes)`）或在 test fn 內用 `from copy import deepcopy` 包裝 router
   - 或：將 dep_overrides 移到 fixture 並在 teardown 清空
   - E1 修 → E2 review → E4 重跑全 suite 兩遍

2. **P0-2 fix `mac_policy_guard.rs` doctest 中文括號**
   - 把 `//!` block 內中文 OS matrix 包進 ` ```text ... ``` ` markdown code fence（rustdoc 不會試 tokenize）
   - 或 把全形 `（）` 改半形 `()` （犧牲一點中文視覺）
   - E1 修 → E2 review → E4 重跑 cargo test --release --workspace

**P1 (accept-and-flag，下個 sprint 開 ticket)**：
3. **P1-1 W4-W9 補做 E4 regression sign-off**：本 cold audit 算第一次 E4 regression cover W4-W9，但需正式 retroactive sign-off + closure doc line 162-164 + 269-270 數字更正為 `3374 PASS / 1 fail` + `2447 + 2 doctest fail`，不可寫 0 fail
4. **P1-2 shrinkage_router production scale smoke**：開 ticket 加 1 case `@pytest.mark.slow` cover production 1000/2000 chain

**驗收後通過**：執行 PM commit + push 修 P0-1/P0-2 → 重 E4 → ALL GREEN → REF-20 closure 數字更新 → 真正 PASS。

---

## 附 A — 完整 cold run 命令

```bash
# Python (從 srv root)
cd /Users/ncyu/Projects/TradeBot/srv && python3 -m pytest program_code/learning_engine/tests/test_shrinkage_router.py program_code/learning_engine/tests/test_hierarchical_bayes.py -v --tb=short  # 21 PASS

cd /Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1 && python3 -m pytest tests/ --tb=no -q --ignore=tests/integration  # 3374 P / 1 F / 10 skip

# Rust (Mac aarch64 release)
cd /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine && cargo test --release --lib  # 2447 P / 0 F
cd /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine && cargo test --release --tests --features replay_isolated  # 2630 P / 0 F (含 lib)
cd /Users/ncyu/Projects/TradeBot/srv/rust && cargo test --release --workspace  # 3077 P / 2 F (mac_policy_guard doctest) / 3 ignored
```

## 附 B — Sibling 對照需求

REF-20 W4-W9 closure 至少需在 Linux trade-core 跑一次 baseline 對照確認 Mac fail 是否同樣 reproducible 在 Linux：
```bash
ssh trade-core "cd ~/BybitOpenClaw/srv/program_code/exchange_connectors/bybit_connector/control_api_v1 && python3 -m pytest tests/ --tb=no -q --ignore=tests/integration"
ssh trade-core "cd ~/BybitOpenClaw/srv/rust/openclaw_engine && cargo test --release --workspace"
```

---

E4 REGRESSION DONE: **CONDITIONAL FAIL** (2 P0 + 2 P1)
report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-03--ref20_final_closure_e4_cold_audit.md
