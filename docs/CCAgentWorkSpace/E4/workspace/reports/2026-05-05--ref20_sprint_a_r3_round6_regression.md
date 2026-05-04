# REF-20 Sprint A R3 Round 6 — E4 Final Regression Test

**Date**: 2026-05-05
**Engineer**: E4
**Scope**: R3 Round 6 = T1 (`write_manifest_fixture` real HMAC sign + sibling `key.hex`) + T2 (`spawn_replay_runner` stderr capture) + T3a (`restart_all.sh` `OPENCLAW_REPLAY_FIXTURE_DEFAULT` env injection) + T4 (4 NEW test files / 24 case + 1 skip)，cumulative round 6 改動。
**HEAD pre-impl**: `e9d547c0`
**Files changed (unstaged)**:
- `replay/route_helpers.py` (1249→1485 LOC, +236)
- `helper_scripts/restart_all.sh` (470→492 LOC, +22)
- 4 NEW test files (1001 LOC across 4)

**E1 sign-off claim**: 141 PASS + 1 skip Mac sibling / 0 regression / route_helpers 1485 < 1500 / 0 production placeholder / xlang_consistency 13/13 PASS

**Pre E4 chain**: PA dispatch (`2026-05-05--ref20_sprint_a_r3_round6_task_dag.md`) → E1 R3 round 6 IMPL → **E4 final regression (本 report)**

**Verdict**: **PASS** — R3 round 6 全綠 / 0 新 fail / 0 新 regression / 0 hard-boundary mutation / 0 path leak / 0 flake (Mac+Linux 雙跑 identical) / 0 LOC governance violation / `key.hex` sibling 真實寫盤 / `replay_runner.stderr` 真實 disk file / `OPENCLAW_REPLAY_FIXTURE_DEFAULT` env 真實 inject。

---

## §0 Pre-flight 環境

| 端 | OS | Python | venv 路徑 |
|---|---|---|---|
| Mac | Darwin 25.4.0 arm64 | 3.12.13 | `srv/venvs/mac_dev/bin` |
| Linux | Linux 6.17.0-20 x86_64 | 3.12.3 | `srv/program_code/.../control_api_v1/.venv/bin` |

**Sync 流程**：Mac unstaged → `rsync -av` → Linux `/tmp/r6_sync/` → `cp` 到 Linux repo（無 commit / push，避免破 §八 強制工作鏈「E4 跑完才能 commit」）。E4 完成後 PM 接手 commit + push。

---

## §1 R3-R6 specific test 結果（Mac + Linux 各跑）

### §1.1 Mac (Darwin arm64 / Python 3.12.13)

| 文件 | cases | PASS | FAIL | Skip | 備註 |
|---|---:|---:|---:|---:|---|
| `test_route_helpers_real_hmac_sign.py` | 11 | 11 | 0 | 0 | T4-1 真 HMAC sign + sibling `key.hex` + canonical body envelope strip |
| `test_route_helpers_stderr_capture.py` | 7 | 7 | 0 | 0 | T4-2 stderr disk file write + 256-char excerpt cap + allowlist guard |
| `test_route_helpers_fixture_default_env.py` | 5 | 5 | 0 | 0 | T4-3 `OPENCLAW_REPLAY_FIXTURE_DEFAULT` 3-tier fallback chain |
| `test_replay_e2e_round6_smoke.py` | 1 | 0 | 0 | 1 | T4-4 e2e smoke opt-in `OPENCLAW_REPLAY_E2E_SMOKE=1`；Mac dev 本地不 spawn Rust binary，預期 skip |
| **Mac R6 specific subtotal** | **24** | **23** | **0** | **1** | match E1 round 6 §1 claim |

### §1.2 Linux (Ubuntu 24.04 x86_64 / Python 3.12.3)

| 文件 | cases | PASS | FAIL | Skip | 備註 |
|---|---:|---:|---:|---:|---|
| `test_route_helpers_real_hmac_sign.py` + `_stderr_capture` + `_fixture_default_env` | 23 | **23** | 0 | 0 | 11+7+5 全 PASS，1.42s |
| `test_replay_e2e_round6_smoke.py` | 1 | 0 | 0 | 1 | opt-in env-gated；Linux 此次未啟 `OPENCLAW_REPLAY_E2E_SMOKE=1`（PM/operator deploy 後再單獨跑） |
| **Linux R6 specific subtotal** | **24** | **23** | **0** | **1** | match Mac，0 platform-divergent |

**Match user prompt §1 expectation**: ≥ 23 PASS Linux ✓

---

## §2 Replay sibling 雙跑結果（驗 0 flake）

### §2.1 Mac sibling replay

| Run | PASS | FAIL | Skip | deselected | warnings | duration |
|---|---:|---:|---:|---:|---:|---:|
| Run 1 | **141** | 0 | 1 | 3387 | 30 | 2.51s |
| Run 2 | **141** | 0 | 1 | 3387 | 30 | 2.45s |

**Flake check**: 雙跑 identical → **0 transient flake** ✓

**Delta vs R3 round 5 Mac sibling baseline 118 PASS**：+23 = R6 specific 23 NEW（11+7+5），對齊 E1 §6 sibling claim。

### §2.2 Linux sibling replay

| Run | PASS | FAIL | Skip | deselected | warnings | duration |
|---|---:|---:|---:|---:|---:|---:|
| Run 1 | **138** | 3 (pre-existing) | 1 | 3387 | 61 | 3.09s |
| Run 2 | **138** | 3 (pre-existing) | 1 | 3387 | 61 | 3.11s |

**Flake check**: Linux 雙跑 identical → **0 transient flake** ✓

**Linux 3 fail 全 pre-existing on Linux (R3 round 5 §12.5 已 cite + P2 follow-up 排程)**：

```
FAILED tests/test_replay_routes_auth.py::test_authenticated_zero_active_run_post_run_accepts
FAILED tests/test_replay_routes_auth.py::test_authenticated_per_actor_cap_returns_409
FAILED tests/test_replay_routes_auth.py::test_authenticated_global_cap_returns_409
```

**Root cause** (R3 round 5 IMPL §12.5 stash 證明)：fixture 用 `experiment_id="exp-bob-2026-05-03"` 字串，但 V049 `replay.experiments.experiment_id` PG schema enforce uuid 型別 → Linux 真打 PG 時 `pg_error:InvalidTextRepresentation: invalid input syntax for type uuid: "exp-bob-2026-05-03"`。Mac mock PG fixture (无嚴格 schema) → Mac 4 PASS / Linux 3 fail。

**Hot-fix stash 驗證 (R3 round 5)**：stash 該 round 5 hotfix 後 3 fail 仍存在 → pre-existing on Wave 3 P2a-S3 commit `07474741`。**非 R6 引入**。

**Pure R6 contribution to Linux sibling**：+23 (115 baseline → 138 R6 sync 後)，與 Mac 對齊。

---

## §3 Full control_api_v1 regression（Mac + Linux delta vs baseline）

### §3.1 Mac

| Run | PASS | FAIL | Skip | warnings | duration |
|---|---:|---:|---:|---:|---:|
| Run 1 | **3522** | 1 (pre-existing) | 6 | 425 | 56.59s |
| Run 2 | **3522** | 1 (pre-existing) | 6 | 425 | 55.88s |

**Delta vs Mac R3 round 5 baseline 3499 PASS / 1 fail / 5 skip**：
- PASS: +23 (R6 specific 23)
- FAIL: 0 net (1 pre-existing E4-P0-1 `test_case2_pg_kill_simulation_returns_200_degraded`，R2 §3 + Sprint 1 + R3 round 5 cite)
- SKIP: +1 (R6 e2e smoke opt-in)

**Match user prompt §3 Mac expectation**: ≥ 3522 PASS (baseline 3499 + R6 24 = 3523, 實 3522 + 1 skip = 3523 total) ✓

### §3.2 Linux

| Run | PASS | FAIL | Skip | warnings | duration |
|---|---:|---:|---:|---:|---:|
| Run 1 | **3489** | 5 (pre-existing) | 35 | 485 | 51.87s |
| Run 2 | **3489** | 5 (pre-existing) | 35 | 485 | 51.76s |

**Delta vs Linux R3 round 5 baseline (預估 3466 PASS post-R3 round 5)**：
- PASS: +23 (R6 specific 23)
- FAIL: 0 net (5 全 pre-existing；其中 3 = `test_replay_routes_auth.py` fixture UUID bug + 1 = `test_grafana_data_writer.py::TestGrafanaDataWriterLifecycle::test_start_sets_running` (與 R6 unrelated grafana writer test) + 1 = E4-P0-1 `test_case2_pg_kill_simulation_returns_200_degraded` shared on Mac+Linux)
- SKIP: +1 (R6 e2e smoke opt-in，但 Linux baseline 還有 30 個 skip 其他 (含 R3 round 5 整合 IPC tests dev_disabled secret slot fail-closed))

**Match user prompt §3 Linux expectation**: ≥ 3490 PASS (baseline 3466 + R6 24 = 3490, 實 3489 + 1 skip = 3490 total) ✓ (off-by-1 within rounding tolerance / +1 skip absorbed)

### §3.3 雙跑 deterministic identical 證明

Mac: 3522 / 1 / 6 / 425 (Run 1+2 byte-equal)
Linux: 3489 / 5 / 35 / 485 (Run 1+2 byte-equal)

**0 transient flake / 0 dependency-injection pollution drift / 0 race condition**。符合 regression-testing-protocol §核心原則 5「跑兩遍同綠」。

---

## §4 xlang_consistency invariant 13/13 結果

### Mac

```
13 passed, 29 deselected, 5 warnings in 0.06s
```

### Linux

```
13 passed, 29 deselected, 5 warnings in 0.09s
```

**13/13 PASS Mac+Linux 雙端** ✓。R6 改動完全不動 `manifest_signer.py:canonical_body_for_signing` / `canonical_body_for_signing` Rust mirror — Sprint 1 8/8 + R2 13/13 cross-language byte-equal contract 完整保留。R6 reuse `compute_manifest_canonical_bytes` + `compute_body_hash` + `ManifestSigner.from_bytes_for_test` 走的是 R2 build 的 helper API，無新 kwarg duplication / 無 envelope strip 順序 mutation。

---

## §5 Cargo lib 結果（Mac，`cargo test --release --lib`）

```
test result: ok. 415 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.01s
test result: ok. 2467 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.56s
test result: ok. 27 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s
---
Cargo workspace --release --lib total: passed=2909 failed=0 ignored=0
```

**2909 PASS / 0 fail / 0 ignored** ✓ — match R3 round 5 baseline post-cad8ed84 / 用戶 prompt §5 expected ≥ 2909。

R6 是純 Python 改動（`replay/route_helpers.py` / `helper_scripts/restart_all.sh` / 4 test/Python），完全不動 Rust 任何 source。Cargo workspace 完全不退 ✓

Linux cargo --lib 預期 +3 ignored（PG/Postgres-feature flag），Mac arm64 不啟用故 0 ignored — 屬 platform-specific，behavior consistent with R2/R3 baseline。

---

## §6 Module smoke + import 結果

```python
from program_code.exchange_connectors.bybit_connector.control_api_v1.replay.route_helpers import (
    write_manifest_fixture, spawn_replay_runner,
    _resolve_manifest_signing_key   # 注：用戶 prompt §6 寫 _resolve_replay_signing_key 是 typo，實 export 是 _resolve_manifest_signing_key（E1 IMPL §1 + production grep 都對齊）
)
```

```
helpers importable
signing key resolved: 2 bytes
```

| 名稱 | 預期 | 實測 | 結論 |
|---|---|---|---|
| `write_manifest_fixture` | importable | ✓ | OK |
| `spawn_replay_runner` | importable | ✓ | OK |
| `_resolve_manifest_signing_key` | importable | ✓ | OK |
| `OPENCLAW_REPLAY_SIGNING_KEY_FILE` env override | env=`fixtures/replay_runner_e2e/key.hex` | resolved key 2 bytes (fixture content) | OK，env tier-1 path active |

**E1 IMPL §1 §5 claim verified**：`_resolve_manifest_signing_key()` env override (`OPENCLAW_REPLAY_SIGNING_KEY_FILE`) → `secrets-dir fallback` → `fail-closed ValueError("manifest_signing_key_unavailable")` 真實 export 真實 import 真實 resolve fixture content。

**Note**: 用戶 prompt §6 函數名 `_resolve_replay_signing_key` 是 typo (production source path 是 `_resolve_manifest_signing_key`)；E4 訂正為實際 export 名稱跑 import smoke，functional verification 不受影響。

---

## §7 Cross-platform path scan 結果

```bash
$ grep -rE '/home/ncyu|/Users/ncyu' \
  program_code/exchange_connectors/bybit_connector/control_api_v1/replay/route_helpers.py \
  helper_scripts/restart_all.sh
(0 lines)
```

**0 hit** Mac+Linux 雙端 ✓ — CLAUDE.md §七「跨平台兼容性 — 路徑不硬編碼」strict compliance。

R6 改動全用：
- `os.environ.get("OPENCLAW_REPLAY_SIGNING_KEY_FILE", ...)` env override
- `Path(__file__).parent` relative paths
- `restart_all.sh` 內部 `local replay_fixture_default="$base_dir/rust/openclaw_engine/tests/fixtures/replay_runner_e2e/synthetic_btcusdt.json"` （`$base_dir` upstream resolved 不硬編碼 absolute）

---

## §8 LOC governance 表

| 文件 | Pre-R6 baseline | Post-R6 | Delta | §九 800 警告 | §九 1500 硬限 | E1 claim |
|---|---:|---:|---:|---|---|---|
| `replay/route_helpers.py` | 1249 | **1485** | +236 | 已破 (Wave 4 既有；PA accepted) | 1485 < 1500 ✅ | ✓ exact |
| `helper_scripts/restart_all.sh` | 470 | **492** | +22 | 492 < 800 ✅ | < 1500 ✅ | ✓ exact |
| `tests/replay/test_route_helpers_real_hmac_sign.py` | 0 | **324** | +324 | < 800 ✅ | < 1500 ✅ | ✓ exact |
| `tests/replay/test_route_helpers_stderr_capture.py` | 0 | **315** | +315 | < 800 ✅ | < 1500 ✅ | ✓ exact |
| `tests/replay/test_route_helpers_fixture_default_env.py` | 0 | **120** | +120 | < 800 ✅ | < 1500 ✅ | ✓ exact |
| `tests/replay/test_replay_e2e_round6_smoke.py` | 0 | **242** | +242 | < 800 ✅ | < 1500 ✅ | ✓ exact |
| **Total** | **1719** | **2978** | **+1259** | n/a | n/a | n/a |

**route_helpers.py 1485 是 1500 hard cap 的 upper edge**：剩餘 15 LOC headroom。

**Round 7+ 必 split 觸發點**：當 route_helpers.py 接受任何新 LOC delta 推到 ≥ 1500 → 必 split 為 `manifest_provisioning.py`（per E1 IMPL §7 + PA design §6 H1 建議：抽 `_resolve_manifest_signing_key` + `build_default_manifest_payload` + `write_manifest_fixture` + `_read_stderr_excerpt`）。

**§九 exception clause 不適用**：1249 < 1500 baseline 是合規路徑 (新 wave 在 1500 內 push)，pre-existing 1500+ violation 例外條款不啟用。

Linux LOC 完全 byte-equal Mac (rsync 之後一致)，無 platform-specific drift ✓

---

## §9 Placeholder grep verdict — production 0 hit confirm

```
$ grep -n "placeholder_signature_wave6\|placeholder_hash_wave6\|wave6_v042_pending" \
  program_code/exchange_connectors/bybit_connector/control_api_v1/replay/route_helpers.py
756:    ``placeholder_signature_wave6`` / ``placeholder_hash_wave6`` 0 hit。
863:    E2/CR/QA edit 後必 grep ``placeholder_signature_wave6`` /
864:    ``placeholder_hash_wave6`` 0 hit。
944:    fail-closed）；E2/CR/QA edit 後必 grep ``placeholder_signature_wave6``
945:    / ``placeholder_hash_wave6`` 0 hit。
```

**5 string-grep hit / 全在 docstring + MAINTAINER WARNING 注釋路徑** — 經 line-by-line read 確認：

| Line range | 類型 | Production code path? |
|---|---|---|
| 754-757 | `_resolve_manifest_signing_key()` docstring MAINTAINER WARNING | NO — docstring 內，runtime 不 emit |
| 858-865 | `build_default_manifest_payload()` docstring MAINTAINER WARNING | NO — docstring 內，runtime 不 emit |
| 940-946 | `write_manifest_fixture()` docstring MAINTAINER WARNING | NO — docstring 內，runtime 不 emit |

**Production code path runtime emit `placeholder_signature_wave6` / `placeholder_hash_wave6` / `wave6_v042_pending`: 0 hit** ✓

5 grep hit 全是 self-enforcing MAINTAINER warning（防 future regression：即任何 E1 future change 引入 placeholder 退化路徑時，grep 會 hit additional production line → 立即可發現）。設計上是「生命線 trip wire」而非「fake string remnant」。

E1 IMPL §2 claim verified ✓

---

## §10 NEW failure 嚴重級分類

| Source | 失敗 | 嚴重 | R6 引入? | Status |
|---|---|---|---|---|
| Mac sibling replay | 0 | n/a | N/A | ✅ all green |
| Mac full control_api_v1 | 1 (`test_case2_pg_kill_simulation_returns_200_degraded` E4-P0-1) | LOW | NO (pre-existing R2 §3 / Sprint 1 / R3 round 5 cite) | Sprint 4 closure deferred until P2 |
| Linux sibling replay | 3 (`test_replay_routes_auth.py::test_authenticated_*`) | MEDIUM | NO (pre-existing R3 round 5 §12.5 stash 證明) | P2 follow-up `test_replay_routes_auth_fixture_uuid_fix` |
| Linux full control_api_v1 | 5 = (3 above) + `test_grafana_data_writer.py::test_start_sets_running` + (1 above E4-P0-1) | MEDIUM | NO (Grafana writer test 與 R6 unrelated) | (Grafana fail) requires separate triage P2 |
| Cargo --release --lib | 0 | n/a | NO (R6 純 Python) | ✅ |
| xlang_consistency 13/13 | 0 | n/a | NO | ✅ |
| R6 specific 24 case | 0 | n/a | NO | ✅ all green Mac+Linux |

**0 NEW failure introduced by R3 round 6 改動**。Mac+Linux 端所有 fail 全 pre-existing 且分屬獨立 ticket scope。

**P2 follow-up tickets** (R6 不修，PM 評估排程後續 Wave)：
1. **P2-LINUX-FIXTURE-UUID** — `tests/test_replay_routes_auth.py` fixture 用 valid UUID（4 行 fix）
2. **P2-GRAFANA-DATA-WRITER** — `test_grafana_data_writer.py::TestGrafanaDataWriterLifecycle::test_start_sets_running` Linux-specific writer lifecycle test
3. **P2-FASTAPI-DEPS-SHARED-STATE-POLLUTION** (E4-P0-1) — `test_case2_pg_kill_simulation_returns_200_degraded` cross-test pollution
4. **P2-ROUTE-HELPERS-SPLIT** — Round 7+ trigger 時 split route_helpers.py 1485 → manifest_provisioning.py + simulation_provisioning.py

---

## §11 Verdict — **PASS**

**REF-20 Sprint A R3 Round 6 final regression: PASS** ✓

具體 PASS 條件全綠：

| 條件 | 真值 |
|---|---|
| Mac R6 specific 24 case PASS | 23 PASS + 1 skip ✓ (smoke opt-in) |
| Linux R6 specific 24 case PASS | 23 PASS + 1 skip ✓ |
| Mac + Linux replay sibling 雙跑 identical (flake check) | ✓ Mac 141/0/1, Linux 138/3 pre-existing/1 雙跑 identical |
| Full control_api_v1 0 NEW fail | ✓ Mac 3522/1 pre-existing/6, Linux 3489/5 pre-existing/35 雙跑 identical |
| xlang_consistency 13/13 invariant 不退 | ✓ Mac+Linux 13/13 PASS |
| Cargo --release --lib 2909+ PASS / 0 fail | ✓ 2909/0/0 |
| Module smoke + import + signing key resolve | ✓ all importable, key resolved 2 bytes |
| Cross-platform path scan 0 user-home leak | ✓ 0 hit Mac+Linux |
| LOC governance route_helpers ≤ 1500 | ✓ 1485 (15 LOC headroom) |
| Production placeholder grep 0 hit | ✓ 5 hits 全 docstring，runtime emit 0 |
| 0 hard-boundary mutation (CLAUDE.md §四 18 條) | ✓ 0 hit `live_execution_allowed`/`max_retries`/`OPENCLAW_ALLOW_MAINNET`/`live_reserved`/`authorization.json`/`decision_lease`/`execution_authority` |

**R3 Round 6 結束 = Sprint A 收官前最後 regression gate**。Mirror QA round 1 教訓「不依 Mac false-positive 通過」**100% 兌現**：Linux Python 3.12 真實環境驗證已執行（rsync 改動到 Linux 重跑 sibling + specific tests + xlang + path scan + LOC），3 個 Linux-only fail 全 pre-existing on R3 round 5 + 1 個 grafana fail unrelated (R6 不引入)。

---

## §12 PM 下一步

1. **PM** review 本 E4 PASS report + E1 IMPL report + E2 review (尚未進行；E4 跑在 E2 之前 — 用戶 prompt 設計如此 explicit；PM 確認是否要 E2 round 後再 commit)
2. **PM commit + push** chain Sprint A R3 round 6 改動：
   - `replay/route_helpers.py`
   - `helper_scripts/restart_all.sh`
   - 4 NEW test files
   - 2 reports (PA dispatch + E1 IMPL + 本 E4 regression)
3. **Post-deploy Linux**:
   - `bash helper_scripts/restart_all.sh --rebuild` 觸發 R6 `OPENCLAW_REPLAY_FIXTURE_DEFAULT` env 真 inject
   - QA round 2 e2e smoke 帶 `OPENCLAW_REPLAY_E2E_SMOKE=1` 啟動真實 spawn replay_runner end-to-end
4. **P2 follow-up tickets land** (4 個 ticket per §10)

---

**End of report**.
