# REF-20 Sprint A R1 — E4 Regression Test Report

**Date:** 2026-05-04
**Owner:** E4
**Scope:** R1 IMPL 落盤後 regression（5 R1-T5 new tests + replay/manifest/track_c sibling + module smoke + cross-platform import smoke + audit script + Sprint 1 F1 invariant）
**Inputs:**
- PA design DAG: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-04--ref20_sprint_a_task_dag.md`
- E1 IMPL sign-off: `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-04--ref20_sprint_a_r1_impl.md`
- Pre-flight baseline (TODO.md L5): Python pytest **3431 PASS** / 1 fail (pre-existing E4-P0-1) / 10 skip · Rust cargo workspace **3132 PASS** / 2 fail (pre-existing E4-P0-2) / 3 ignored
- E1 sign-off claim: pytest 5/5 PASSED on R1-T5 new tests
- Note: 本 task PA 派發 **不**派 E2 review 序列（任務文件直接從 R1 IMPL → E4 regression），E4 sign-off 後 PM 統一 commit

**Verdict:** **PASS** — R1 5 sub-task 全綠，0 新 fail / 0 新 regression / 0 hard-boundary mutation / 0 path leak / 0 flake (2-round identical)

---

## §1 R1-T5 5 case 結果（pytest -xvs）

5/5 PASS。雙跑 identical（0 transient flake）。

```
collected 5 items
test_env_override_takes_precedence              PASSED
test_workspace_release_preferred                PASSED
test_workspace_debug_fallback                   PASSED
test_legacy_release_fallback                    PASSED
test_all_paths_absent_returns_legacy_debug_path PASSED
============================== 5 passed in 0.02s ===============================
```

| Run | Result |
|---|---|
| Round 1 | 5 passed in 0.02s |
| Round 2 | 5 passed in 0.02s |

---

## §2 既有 replay test regression 結果

`pytest -k replay` 全 suite：**60 passed / 0 failed / 3387 deselected**，雙跑 identical。

E1 sign-off 對齊：既有 5 個 `test_replay_routes_*.py`（auth / safe_query_audit / t2_pg_advisory_lock / t2_subprocess / track_c_security）+ 其他 replay-keyword tests 0 import error / 0 assertion regression。

| Run | Result |
|---|---|
| Round 1 | 60 passed, 3387 deselected, 25 warnings in 1.15s |
| Round 2 | 60 passed, 3387 deselected, 25 warnings in 1.03s |

**全 suite Python pytest baseline**：

| Run | passed | failed | skipped | duration |
|---|---:|---:|---:|---:|
| Pre-R1 baseline (TODO.md L5) | 3431 | 1 | 10 | — |
| **R1 round 1** | **3436** | **1** | **10** | 55.80s |
| **R1 round 2** | **3436** | **1** | **10** | 54.90s |

**Delta vs baseline**：**+5 PASS**（=R1-T5 5 new tests）/ **+0 fail** / **+0 skip**。

**Pre-existing fail**：E4-P0-1（FastAPI dep_overrides shared-state pollution，Wave 6 commit `eb5f106` 引入；Sprint 1 cold audit 已 flag；Sprint 1/2/3/4 不承諾修；P2-FOLLOW-UP-1 cross-sprint ticket）— **本任務不引入也不修**，符合 "0 新 fail" 約定。

---

## §3 Module smoke 結果

### §3.1 Route 註冊（`/api/v1/replay/*`）

```
['/api/v1/replay/cancel',
 '/api/v1/replay/health',
 '/api/v1/replay/health/signature',
 '/api/v1/replay/list',
 '/api/v1/replay/manifest/verify',
 '/api/v1/replay/manifests',
 '/api/v1/replay/report/{experiment_id}',
 '/api/v1/replay/run',
 '/api/v1/replay/status']
```

驗：`/api/v1/replay/health` + `/api/v1/replay/health/signature` 兩條都註冊 ✓。`/health` 在 `/health/signature` 之前（PA plan ordering 一致）✓。route 總數 9（從 prior 8 升 1，與 E1 sign-off 一致）✓。

### §3.2 Pydantic backward compat（抽出 model 後 caller 無破）

| Class | `__module__` | from `app.replay_routes` import | from `replay.replay_models` import | identity |
|---|---|---|---|---|
| `ReplayRunRequest` | `replay.replay_models` | ✓ | ✓ | same class object (`is` true) |
| `ReplayCancelRequest` | `replay.replay_models` | ✓ | ✓ | same class object (`is` true) |
| `ReplayManifestVerifyRequest` | `replay.replay_models` | ✓ | ✓ | same class object (`is` true) |

3 class 仍可從 `app.replay_routes` import（透過 module-level alias re-export），亦可從新模組 `replay/replay_models.py` 直接 import；兩條路徑得到 **同一個 class object**，OpenAPI schema generation / 既有 5 個 `test_replay_routes_*.py` 0 行為改動 ✓。

---

## §4 跨平台 import smoke 結果（macOS）

```
resolved binary path: /Users/ncyu/Projects/TradeBot/srv/rust/target/release/replay_runner
exists: True

--- compute_replay_health_state probe ---
{
  "binary_path": "/Users/ncyu/Projects/TradeBot/srv/rust/target/release/replay_runner",
  "binary_exists": true,
  "binary_release_profile": "",
  "data_dir": "/Users/ncyu/.openclaw_runtime",
  "data_dir_writable": true,
  "pg_present": true,
  "v045_present": false,
  "v049_present": false,
  "wiring_status": "ready"
}
```

驗：
- `resolve_replay_runner_bin()` 命中 **fallback step 2** (`rust/target/release/replay_runner`) — 與 E1 sign-off §9-1 一致（前任 E1 在 audit script 跑 cargo build 後 binary 落盤於 workspace target）✓
- `compute_replay_health_state()` 9-field 全產出（PA design §1 表 1-1 一致）✓
- Mac PG runtime 真在跑（`pg_present=true`），但 `v045_present=false` / `v049_present=false`（Mac local PG 無 V045/V049 schema — Linux trade-core 是真實 deploy 點）→ `wiring_status="ready"` 仍判 PASS（因為主要 gate 是 binary_exists ∧ pg_present ∧ data_dir_writable，與 E1 sign-off §9-2 不確定點預期一致）✓
- 0 hardcoded `/home/ncyu` / `/Users/ncyu` 路徑透過 import 洩漏（path 由 env+`Path` 動態生成）✓

---

## §5 Audit script exit 結果

```
[replay_runner_symbol_audit] === replay_runner symbol audit start ===
[replay_runner_symbol_audit] srv root: /Users/ncyu/Projects/TradeBot/srv
[replay_runner_symbol_audit] platform: Darwin arm64
[replay_runner_symbol_audit] cargo build --release --bin replay_runner --features replay_isolated ...
    Finished `release` profile [optimized] target(s) in 0.10s
[replay_runner_symbol_audit] build OK
[replay_runner_symbol_audit] binary path: /Users/ncyu/Projects/TradeBot/srv/rust/target/release/replay_runner
[replay_runner_symbol_audit] platform=Darwin → nm -gU
[replay_runner_symbol_audit] symbol count: 414
[replay_runner_symbol_audit] AUDIT PASS: 0 forbidden symbol detected (414 symbols scanned)
exit=0
```

**exit=0 ✓ + 414 symbol scanned + 0 forbidden symbol**（與 E1 sign-off §5 R1-T4 acceptance 對齊；R1-T1 fallback chain step 2 workspace release 真實佈局生效）。

注：21 cargo warning 全部是 dead-code / unused-import warning，**屬 pre-existing**（與 R1 改動無關，`grep` 確認 21 warning 全在 `openclaw_engine` 而非 R1 改動的 Python 模組或 `replay_runner` binary 自身）→ 不在 R1 範圍。

---

## §6 Sprint 1 F1 invariant 維持證明

**F1 invariant 定義**（Sprint 1 retrofit `manifest_signer.py` Python 端 `_python_canonical_body_for_signing` 鏡像 Rust `canonical_body_for_signing`，sort_keys=True / separators=(',', ':') / ensure_ascii=False 三 lock 維持 byte-equal）。

驗 R1 抽出 model 後 canonical_bytes 計算路徑 0 影響：

```
$ grep -nE "from .replay_routes import|from \.replay_routes import|from .*replay_routes import" \
    replay/manifest_signer.py replay/route_helpers.py
(0 results)

$ grep -nE "import.*ReplayRunRequest|import.*ReplayCancelRequest|import.*ReplayManifestVerifyRequest" \
    replay/manifest_signer.py replay/route_helpers.py
(0 results)

$ grep -rnE "from .* import.*ReplayRunRequest" control_api_v1/
(0 results in non-replay_routes/replay_models scope)
```

**結論**：`replay/manifest_signer.py` 與 `replay/route_helpers.py` 0 個 import `replay_routes` 任何 model；R1 抽出 3 model 對 canonical_bytes 路徑 **完全 0 耦合 / 0 影響** ✓。Sprint 1 F1 retrofit invariant（HMAC-SHA256 byte-equal Rust↔Python 8/8 xlang fixture）**完整保留**。

---

## §7 NEW failure list

**0 new failure**。

| 類別 | 數量 | 細節 |
|---|---:|---|
| 嚴重級 BLOCKER | 0 | — |
| 嚴重級 HIGH | 0 | — |
| 嚴重級 MEDIUM | 0 | — |
| 嚴重級 LOW | 0 | — |

**Pre-existing fail**（不在本任務範圍 — Sprint 1 cold audit 已 flag，P2-FOLLOW-UP cross-sprint ticket）：
- E4-P0-1（Python pytest 1 fail）— FastAPI dep_overrides shared-state pollution，Wave 6 commit `eb5f106` 引入；deterministic（2 round 同 fail）；isolated run 5/5 PASS；不阻塞 R1 sign-off。
- E4-P0-2（Rust workspace 2 fail）— `mac_policy_guard.rs` Wave 3 commit `5a618ff` 中文全形括號 doctest；E4 cargo lib release 端（2467/0）不觸發 doctest，本任務未跑 workspace doctest 故不在本表展開；屬 P2-FOLLOW-UP-2。

**Hard-boundary scan**（CLAUDE.md §四 18 條紅線，R1 改動 6 file）：
```
$ grep -nE "live_execution_allowed|max_retries|OPENCLAW_ALLOW_MAINNET|live_reserved|authorization\.json|decision_lease|execution_authority" \
    program_code/.../app/replay_routes.py \
    program_code/.../replay/replay_models.py \
    program_code/.../replay/route_helpers.py \
    program_code/.../tests/test_replay_route_helpers_binary_resolution.py \
    helper_scripts/restart_all.sh \
    helper_scripts/ci/replay_runner_symbol_audit.sh
```
**0 hit ✓**。R1 完全沒改 live execution gate / Decision Lease / Risk envelope / Mainnet ALLOW 任何邊界 ✓。

**Cross-platform path scan**（CLAUDE.md §七 ★★，R1 改動 6 file）：
- E1 sign-off §6.2 已驗 0 真實命中，僅有 docstring 內政策反例引用（CLAUDE.md §七「政策反例引用不在此限」）✓。

---

## §8 Sign-off Verdict

**PASS** — R1 (Runtime Usability) 5 sub-task 全綠：

| Sub-task | 驗證點 | 結果 |
|---|---|---|
| R1-T1 `resolve_replay_runner_bin()` 5-step fallback | macOS env smoke：命中 step 2 workspace release | ✓ |
| R1-T2 `restart_all.sh::restart_api` env export | E1 sign-off claim + git diff 已 staged（本 task 不重 deploy）| ✓ |
| R1-T3 `/api/v1/replay/health` route + `compute_replay_health_state()` | 9-field digest probe + route 註冊 ordering | ✓ |
| R1-T4 `replay_runner_symbol_audit.sh::BIN_PATH_DEFAULT` | exit=0 + 414 symbol / 0 forbidden | ✓ |
| R1-T5 5 unit test 全綠 | 雙跑 identical 5/5 PASS | ✓ |

**回歸結論**：

- **Python pytest**：3436 PASS / 1 pre-existing fail / 10 skip（vs baseline 3431/1/10：**+5 PASS / +0 fail / +0 skip** — R1-T5 5 new test 全綠）
- **Rust engine lib**：2467 PASS / 0 fail（vs Sprint 1 cold audit baseline 2447：**+20 PASS / +0 fail** — Sprint 3 Track H + Sprint 4 累積）
- **既有 replay-keyword tests**：60 PASS / 0 fail，雙跑 identical
- **module smoke**：route + Pydantic backward compat 全綠
- **跨平台 import smoke (macOS)**：fallback chain step 2 命中 workspace release，9-field digest 全產出
- **audit script**：exit=0 / 0 forbidden symbol
- **Sprint 1 F1 invariant**：抽 3 model 後 0 個 caller 在 manifest_signer/route_helpers 引用，canonical_bytes 路徑完全 0 耦合
- **Hard-boundary scan**：0 紅線觸發
- **Cross-platform**：0 hardcoded path 洩漏
- **Mock 審查**：本 task 不寫業務代碼，僅讀 + 跑；E1 sign-off 已記載（5 R1-T5 test 用 `tmp_path` + `monkeypatch` env，0 業務邏輯 mock）✓
- **2-round flake check**：Python pytest 兩跑同數 (3436/1/10)；R1-T5 兩跑同數 (5/5)；replay subset 兩跑同數 (60/0)；0 transient flake

**建議 PM commit message**：
```
chore(ref20-sprint-a): R1 Runtime Usability — E4 regression PASS

R1 5 sub-task 全綠（T1 binary fallback + T2 env export + T3 /health route +
T4 audit script + T5 5 unit tests）。Python pytest 3436/1/10（+5 PASS / +0 fail
vs baseline 3431/1/10；R1-T5 5 new test 全綠）。Rust engine lib 2467/0（+20
cumulative Sprint 3+4 / +0 new fail）。Module smoke 全綠：/api/v1/replay/health
註冊 + Pydantic 3 model 透過 module alias backward compat（caller 0 行為改動）。
Cross-platform import smoke (macOS) fallback chain step 2 命中 workspace release。
Audit script exit=0 / 414 symbol / 0 forbidden。Sprint 1 F1 invariant 維持
（manifest_signer/route_helpers 0 import replay_routes model）。0 hard-boundary
mutation / 0 hardcoded path / 0 flake (2-round identical)。

R2 (Manifest Registry) + R3 (First Real E2E Evidence) 待 PA 啟動。

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## §9 不確定 / 後續觀察

1. **`/health` route 在 V049 absent 時的 wiring_status="ready"**：E1 sign-off §9-2 已 flag。Mac local probe 顯示 `v049_present=false` 仍判 ready（因主要 gate 是 binary+pg+data_dir）。若 PA 設計意圖是 V049 absent → degraded，需在 `compute_replay_health_state` 補一條 rule。本 task **不在 E4 範圍**，建議 PA / E2 review 時定奪。
2. **Mac dev 不跑 workspace doctest**：E4-P0-2 兩條 Rust workspace doctest fail 屬 pre-existing（Wave 3 commit `5a618ff`），本任務未跑 `cargo test --workspace --doc`；Linux runtime 端的 cumulative regression 已在 Sprint 1/2/3/4 chain 多次驗證 0 增 fail（保持 2 fail 不變）。
3. **R2/R3 task 待 PA 啟動**：本 sign-off **僅** cover R1 範圍；R2 (Manifest Registry) 是 PA DAG §2 高風險區（experiments INSERT + FK 兩階段 + signature path V042 archive），R3 是 Linux SSH bridge E2E run；屬於後續 sprint A 工作。
4. **Linux runtime 真實部署**：本 sign-off 僅在 Mac dev 跑；Linux trade-core 真實部署需透過 SSH bridge 跑 `restart_all.sh --rebuild` + Linux pytest + V049-V054 schema check。屬 PM 統一 commit 後的 Track I-style deploy 工作。

---

E4 REGRESSION DONE: PASS · report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-04--ref20_sprint_a_r1_regression.md`
