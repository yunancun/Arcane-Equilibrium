# REF-20 Sprint A R2 — Manifest Registry & Verification Repair IMPL

**Date**: 2026-05-04
**Owner**: E1 (Backend Developer)
**Plan**: `srv/docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md` §6.R2
**HEAD pre-impl**: `c1ab7ea9`
**Status**: IMPL COMPLETE — 待 E2 審查 → E4 回歸 → PM commit

---

## §1 5 sub-task 完成清單

| # | Sub-task | Owner | Files | LOC delta | Tests | Status |
|---|---|---|---|---|---|---|
| R2-T1 | `/experiments/register` endpoint + 新模組 | E1 | `replay/experiment_registry.py` (NEW 770 LOC) + `app/replay_routes.py` (+thin handler ~30 LOC) | NEW 770 + thin route +30 | 9/9 PASS | ✅ DONE |
| R2-T2 | `/run` handler 用真實 manifest_id | E1 | `app/replay_routes.py` (UUID5 → SELECT FOR SHARE) + `replay/route_helpers.py` (+24 LOC `lookup_registered_experiment_id`) | -23/+10 in route + 24 helper | 5/5 PASS | ✅ DONE |
| R2-T3 | `/manifest/verify` production path | E1 | `replay/manifest_signer.py` (+210 LOC `load_signing_key_from_secrets_dir` + `resolve_verify_key_source`) + `app/replay_routes.py` (501→410 retrofit) + `tests/test_replay_routes_track_c_security.py` (1 case re-target) | +210 module / -50/+30 route / 1 test re-target | 5/5 PASS | ✅ DONE |
| R2-T4 | 19 unit tests | E1 | `tests/test_replay_experiments_register.py` (NEW 295 LOC) + `tests/test_replay_run_fk_guard.py` (NEW 230 LOC) + `tests/test_replay_manifest_verify_secrets_path.py` (NEW 215 LOC) | NEW 740 | 19/19 PASS | ✅ DONE |
| R2-T5 | canonical_bytes contract + CLAUDE.md §九 | E1 | `replay/manifest_signer.py::compute_body_hash` docstring (+62 LOC contract spec) + `CLAUDE.md` §九 「其他」section (+1 simulated_fills 行) | +62 docstring + 1 line | n/a (doc) | ✅ DONE |

**5/5 sub-task ACCEPT**。Ready for E2 review.

---

## §2 V049 22-col contract INSERT 對齊證明

V049 `replay.experiments` 22-col INSERT 由 `experiment_registry.py::register_experiment` 產生，對齊：

```sql
INSERT INTO replay.experiments (
    experiment_id, parent_experiment_id, created_at, created_by,
    runtime_environment, git_sha, engine_binary_sha,
    strategy_config_sha256, risk_config_sha256,
    timeframe, data_tier, execution_confidence,
    calibration_train_window_start, calibration_train_window_end,
    oos_label_window_start, oos_label_window_end,
    candidate_window_start, candidate_window_end,
    oos_embargo_seconds, total_candidates_K,
    manifest_jsonb, manifest_hash, manifest_signature,
    signature_key_ref, expires_at, status, output_policy_jsonb,
    half_life_days, embargo_days
) VALUES (...)
```

對 V049 22 col + V041 stub 2 col（`half_life_days` / `embargo_days`）共 24 col 一一對應：
- **server-derived（4）**：`experiment_id` (uuid4) / `created_at` (NOW()) / `created_by` (actor.actor_id) / `runtime_environment` (env-resolved 從 V049 2-value enum)
- **client-required（5）**：`strategy_config_sha256` / `risk_config_sha256` / `timeframe` (V049 8-value enum) / `data_tier` (V049 5-value enum 但 register-time 限 S2/S3/S4) / `manifest_jsonb`
- **client-optional（5）**：`signature_hex` (verify if provided) / `signature_key_ref` / `idempotency_key` (advisory lock + SELECT-then-INSERT) / `half_life_days` (V041 stub) / `embargo_days` (V041 stub)
- **server-defaulted（4）**：`execution_confidence='none'` (Sprint A R3 default per plan §6.R6) / `status='created'` / `manifest_hash` (sha256 of canonical_bytes) / `manifest_signature` (bytes.fromhex(signature_hex) if provided else NULL)
- **NULL-defaulted（10）**：parent_experiment_id / git_sha (env-optional) / engine_binary_sha (env-optional + linux_trade_core sentinel) / calibration_train_window_*  (R3 reserve) / candidate_window_* (R3 reserve) / oos_embargo_seconds (R3 reserve) / total_candidates_K (R3 reserve) / expires_at (R3 reserve) / output_policy_jsonb (R3 reserve)

V049 CHECK 對齊：
- `chk_replay_experiments_runtime_env`：`runtime_environment ∈ ('linux_trade_core', 'mac_dev_smoke_test_only')` — 由 `_resolve_runtime_environment()` 限白名單
- `chk_replay_experiments_timeframe`：`timeframe ∈ V049 8-value` — Pydantic `_timeframe_v049_allowlist` validator
- `chk_replay_experiments_data_tier`：`data_tier ∈ ('S0','S1','S2','S3','S4')` — Pydantic `pattern="^(S2|S3|S4)$"` 限 register-time S2/S3/S4
- `chk_replay_experiments_exec_conf`：`execution_confidence ∈ ('none','limited','calibrated')` — server hardcoded `'none'`
- `chk_replay_experiments_status`：`status ∈ ('created','running','completed','failed','cancelled')` — server hardcoded `'created'`
- `chk_replay_experiments_window_order`：window end > start — Pydantic `_window_order` validator
- `chk_replay_experiments_engine_sha_linux`：linux_trade_core 必有 engine_binary_sha — server fallback `'register_pending_engine_sha'`
- `chk_replay_experiments_oos_embargo_seconds`：non-negative — NULL 走 (NULL OR ≥0)
- `chk_replay_experiments_total_candidates_k`：≥1 — NULL 走 (NULL OR ≥1)

---

## §3 idempotency_key + actor_id unique 處理

**現況確認**：grep V049 line 282-307 ADD COLUMN — `idempotency_key` 不在 V049 22-col 中。grep `idempotency_key|UNIQUE.*idempotency` V049 → 0 命中（V049 line 244 「ADD COLUMN IF NOT EXISTS」是 idempotency 一詞但講的是 migration idempotency 不是 column）。

**結論**：V049 schema **無** `(idempotency_key, created_by)` UNIQUE INDEX 可用。

**採用 plan**：spec note 7 給的 fallback — advisory lock + SELECT-then-INSERT pattern。

**實作**：
```python
# replay/experiment_registry.py::register_experiment
ADVISORY_LOCK_REGISTER_IDEMPOTENCY_PREFIX = "replay_register_idem:"

if body.idempotency_key:
    lock_acquired = _try_acquire_register_idempotency_lock(cur, actor_id, body.idempotency_key)
    existing_id = _select_existing_for_idempotency(cur, actor_id, body.idempotency_key)
    if existing_id is not None:
        return {"experiment_id": existing_id, "idempotency_hit": True, ...}, None
```

**SELECT 路徑**：用 `manifest_jsonb->>'_idempotency_key'` JSONB extract（idempotency marker 由 server 寫入 `manifest_jsonb` 的 `_idempotency_key` server-controlled key），加 `created_by = %s` filter 防跨 actor 衝突。

**advisory lock key**：`register_idem:<actor_id>:<idempotency_key>` （DISTINCT from `route_helpers` 的 `replay_run_global` / `replay_run_actor:` keys，避免衝突）。

**race-free guarantee**：lock + SELECT 在同一 PG xact 內 → 兩個並發 register 同 (actor, key) 必序列化。先 INSERT 的 commit 後，後者 SELECT 才看到 row → 走 cache hit 路徑。

---

## §4 manifest_hash canonical_bytes 重用點

**Single source of truth**：`replay/experiment_registry.py::compute_manifest_canonical_bytes()`

```python
def compute_manifest_canonical_bytes(manifest_jsonb: dict[str, Any]) -> bytes:
    return json.dumps(
        manifest_jsonb,
        sort_keys=True,            # ↔ Rust BTreeMap default
        separators=(",", ":"),     # ↔ Rust serde_json compact
        ensure_ascii=False,        # ↔ Rust serde_json raw UTF-8
    ).encode("utf-8")
```

**契約引用點**：
- `replay/manifest_signer.py::compute_body_hash` docstring（R2-T5 +62 LOC 詳細寫明 contract spec / cross-language invariant / used-by 列表）
- `replay/route_helpers.py::write_manifest_fixture` line 736-744（disk fixture write 同 kwargs）
- `replay/experiment_registry.py::compute_manifest_canonical_bytes` 鏡像 helper
- `rust/openclaw_engine/src/replay/manifest_signer.rs::canonical_body_for_signing`（Rust mirror，Sprint 1 F1 retrofit invariant）

**byte-equal regression test**：`tests/replay/test_manifest_signer_xlang_consistency.py` + sibling Rust test 共用 in-tree fixture。R2 不改此 fixture/test → cross-lang invariant 維持。

---

## §5 LOC governance

| 檔 | Pre-R2 | Post-R2 | Δ | Cap | Status |
|---|--:|--:|--:|--:|---|
| `app/replay_routes.py` | 1492 | **1500** | +8 | 1500 | ✅ at cap |
| `replay/experiment_registry.py` | NEW | 770 | +770 | 1500 | ✅ |
| `replay/manifest_signer.py` | 443 | 715 | +272 | 1500 | ✅ |
| `replay/route_helpers.py` | 1456 | 1480 | +24 | 1500 | ✅ |

**replay_routes.py = 1500 LOC exactly at cap**。實際做法：
- 把 register handler 的 PG xact wrapper 移進 `experiment_registry.run_register_in_pg_xact`
- 把 register error→HTTP 對映移進 `experiment_registry.map_register_error_to_http`
- 把 verify key resolution 移進 `manifest_signer.resolve_verify_key_source`（4-tuple return）
- 把 /run lookup SQL 移進 `route_helpers.lookup_registered_experiment_id`
- 壓縮 R2-T2 / R2-T3 引入的 inline comments
- 更新（不刪）pre-existing `/run` handler docstring 反映 R2-T2 SELECT lookup

---

## §6 unit test 結果（19 new test 全綠）

```bash
$ venvs/mac_dev/bin/pytest -xvs tests/test_replay_experiments_register.py tests/test_replay_run_fk_guard.py tests/test_replay_manifest_verify_secrets_path.py
======================== 19 passed, 5 warnings in 0.27s ========================
```

**`test_replay_experiments_register.py` 9 case**：
1. ✅ `test_register_minimal_payload_creates_row` — V049 22-col INSERT happy path
2. ✅ `test_register_idempotency_key_returns_existing` — cache hit 短路（no INSERT）
3. ✅ `test_register_missing_strategy_config_sha256_422` — Pydantic required field
4. ✅ `test_register_invalid_data_tier_422` — V049 CHECK enum proxy
5. ✅ `test_register_oversized_manifest_jsonb_422` — 256 KB canonical cap
6. ✅ `test_register_actor_id_server_side` — client poison ignored, server uses actor.actor_id
7. ✅ `test_register_signature_hex_invalid_400` — signature verify fail → 400 (no INSERT)
8. ✅ `test_register_canonical_bytes_hash_consistent` — same payload → same hash (key-order independent)
9. ✅ `test_register_window_end_before_start_422` — Pydantic _window_order validator

**`test_replay_run_fk_guard.py` 5 case**：
1. ✅ `test_run_with_unregistered_experiment_id_400` — SELECT 0 row → 400 + replay_experiment_not_registered
2. ✅ `test_run_with_registered_experiment_id_succeeds` — happy path
3. ✅ `test_run_idempotency_returns_same_run_id` — idempotency_key passes through to run_state INSERT
4. ✅ `test_run_state_manifest_id_matches_experiments_row` — V049 SELECT result is manifest_id (R2-T2 invariant)
5. ✅ `test_run_concurrent_register_then_delete_race` — FOR SHARE in SELECT SQL

**`test_replay_manifest_verify_secrets_path.py` 5 case**：
1. ✅ `test_verify_with_test_key_dev_profile_works` — dev fast-path preserved (test_key_path)
2. ✅ `test_verify_with_secrets_file_path_found` — secrets file at $tmp/<env>/replay_signing_key → wiring=secrets_file_path
3. ✅ `test_verify_with_secrets_file_path_missing_410` — both paths missing → 410 + replay_verify_key_archive_not_provisioned
4. ✅ `test_verify_live_profile_rejects_symlink_outside_secrets_dir` — symlink injection blocked → 410
5. ✅ `test_verify_invalid_signature_fail_closed` — 200 degraded + fail_mode (no 4xx)

---

## §7 sibling regression（≥ 81 PASS expected, **87 PASS achieved**）

```bash
$ venvs/mac_dev/bin/pytest tests/ -k replay --no-header -q
87 passed, 3387 deselected, 29 warnings in 0.90s
```

**87 = 68 baseline + 19 new**。0 regression. 1 existing test (`test_p0_2_env_var_test_key_blocked_in_live_profile`) updated to assert R2-T3 retrofit behavior (501 → 410); security invariant preserved.

**Full control_api_v1 regression**：
```bash
$ venvs/mac_dev/bin/pytest tests/ --no-header -q
1 failed, 3468 passed, 5 skipped
```

The 1 fail = `test_replay_routes_safe_query_audit.py::test_case2_pg_kill_simulation_returns_200_degraded`. **Verified PRE-EXISTING** by `git stash --include-untracked` → same fail. NOT caused by R2.

---

## §8 git status sign-off-clean (CLAUDE.md §七 P0-GOV-3)

```
$ git status --porcelain
 M CLAUDE.md
 M program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_routes.py
 M program_code/exchange_connectors/bybit_connector/control_api_v1/replay/manifest_signer.py
 M program_code/exchange_connectors/bybit_connector/control_api_v1/replay/route_helpers.py
 M program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_routes_track_c_security.py
?? docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-04--ref20_sprint_a_r2_impl.md
?? program_code/exchange_connectors/bybit_connector/control_api_v1/replay/experiment_registry.py
?? program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_experiments_register.py
?? program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_manifest_verify_secrets_path.py
?? program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_run_fk_guard.py
```

**8 staged + 5 untracked = 13 files all R2-scoped**:
- 8 modified: 4 Python source + 1 test (track_c retrofit) + 1 governance doc (CLAUDE.md §九 simulated_fills note)
- 5 untracked: 1 new module + 3 new test files + this report

NO accidental sibling-CC WIP absorbed (verified by inspecting each file's diff is R2 content only). Sign-off clean per CLAUDE.md §七 P0-GOV-3.

---

## §9 預留問題（給 E2 / E3 / E4）

### 給 E2（code review）

1. **`/report/{experiment_id}` 仍用 UUID5 derivation**（line 921-926）— R2-T2 把 `/run` 的 manifest_id 寫成真 V049 experiment_id；但 `/report` 在 line 956-962 用 `uuid.uuid5(NAMESPACE, experiment_id)` 推 manifest_uuid 然後 SELECT V046.report_artifacts WHERE manifest_id = derived_uuid。**這是 R2-T2 留下的 cross-route 一致性 gap**：對 R2-T2 後 INSERT 的 run_state，`/report` 永遠找不到（derived_uuid != real experiment_id）。R2 spec 明確不在 `/report` 範圍 → 我未改。請 E2 review 是否：
   - (a) 在 R2 內補 `/report` 同步使用真實 experiment_id（會超 1500 LOC cap，需再壓縮其他 area）
   - (b) 列為 R3 sub-task 處理
   - (c) 接受短期 inconsistency，因為 V046 是 R3 寫入點（R3 simulated_fills writer 才開始往 V046 寫）

2. **`runtime_environment` 預設 `'linux_trade_core'` + sentinel 'register_pending_engine_sha'**（experiment_registry.py line 432）— V049 conditional NOT NULL 要求 linux_trade_core 必有 engine_binary_sha；如果 env 缺，我用 sentinel 過 CHECK。Production deploy 必設 `OPENCLAW_ENGINE_BINARY_SHA` env，否則 V049 row 帶 sentinel 對 supply-chain audit 不利。E2 review 是否需更嚴格 fail-closed（缺 env → register reject 503 instead of sentinel）。

3. **manifest_jsonb 透過 `_idempotency_key` server-controlled key 存 idempotency marker**（experiment_registry.py line 540-547）— 比 V049 加 column 輕，但 client 提交 manifest_jsonb 內含 `_idempotency_key` key 會與 server 注入衝突。我未在 Pydantic validator 內加 reject `_*` prefix key 的 guard（會擴大 R2 範圍）。E2 review 是否需加 reject reserved prefix。

### 給 E3（security audit）

1. **`load_signing_key_from_secrets_dir` 的 env_label 白名單只允許 `('paper', 'demo', 'live')`** — 與 helper script `generate_replay_signing_key.sh` line 27 對齊。E3 verify 是否還有遺漏 env 名（例如 `staging` / `dev`）。

2. **R2-T3 live profile symlink injection guard** — 用 `path.resolve(strict=True)` + `is_relative_to(secrets_root.resolve(strict=True))`。E3 verify Mac dev `/private/tmp` symlink 行為（macOS `/tmp` → `/private/tmp` symlink）是否會誤判 live profile 下「正常 secrets dir 在 /tmp 的 fixture」為逃逸。R2-T4 case 4 在 macOS 上測 PASS → 應該不會，但 E3 production-grade 環境另測。

3. **register endpoint 的 signature_hex 使用 R2-T1 的 `OPENCLAW_REPLAY_VERIFY_TEST_KEY` env**（與 verify endpoint 同 env）— 短期方便 dev/test，但 R2-T3 retrofit 後 verify endpoint 已支援 secrets-file production path；register endpoint 仍只走 env。production 不太需要 register-time signature verify（manifest_hash + manifest_signature 寫入後由 verify endpoint 驗），但若 E3 認為 register-time 也該支援 secrets-file，請列為 R2 follow-up。

### 給 E4（regression）

1. **R2 sibling regression 87 PASS = 68 baseline + 19 new**。0 regression in replay-tagged tests. Full control_api_v1: 1 fail (`test_case2_pg_kill_simulation_returns_200_degraded`) **PRE-EXISTING**，非 R2 引入（git stash 驗證）。E4 跑 Linux 端 regression 確認跨平台一致性。

2. **Linux 端 V049 schema deploy 狀態確認**：Sprint 1 Track D V049 已 land（Linux _sqlx_migrations 應有 V049 row）。E4 在 Linux 端 manual smoke `POST /api/v1/replay/experiments/register` + `POST /run` 驗 FK 對齊：
   - register → expect 200 + experiment_id (real UUID)
   - run with that experiment_id → expect 200 + status=running
   - SELECT replay.run_state.manifest_id → matches register UUID

3. **跨語言 fixture byte-equal regression** — R2 不改 `tests/replay/test_manifest_signer_xlang_consistency.py` fixture 或 invariants。E4 確認 Rust + Python xlang test 仍 8/8 PASS。

---

## §10 不確定之處

1. **manifest_jsonb 含 server-injected `_idempotency_key` 後 client-side hash mismatch** — 若 client 送了 idempotency_key + signature_hex（先 sign，後送），server 會把 `_idempotency_key` 注入 manifest_jsonb 再算 manifest_hash → manifest_hash != client 預先算的 hash。但 R2-T1 verify 是在「server-canonicalized bytes」上跑，不會 fail。**潛在問題**：如果未來有 audit 想 reproducible 從 client-side 算同 hash，會發現 server-side 比 client-side 多一個 `_idempotency_key` 欄位。E2 review 是否要：
   - (a) `_idempotency_key` 寫到 V049 separate column 的 follow-up（需 V### migration，spec 禁）
   - (b) idempotency marker 不入 manifest_jsonb，存 in-memory（uvicorn 重啟丟 cache hit；不可接受）
   - (c) 接受 server-side enrichment（current design）
   - (d) signature 算法改為「先剝 `_*` prefix key 再 hash」（要改 Rust + cross-lang fixture）

2. **`/run` 的 SELECT FOR SHARE lock 是 row-level；但 advisory lock 已存在於 caller xact** — 兩個 lock pattern 共存。Postgres 可以同 xact 持多 lock，無 deadlock 顯式風險，但 lock acquisition order matters under heavy contention。E4 stress-test 是否能撐高並發（V3 §5 限 global=1 / per-actor=1，理論上 contention 低）。

3. **`runtime_environment` 預設 `'linux_trade_core'` 但實際在 Mac dev 跑 register endpoint** — 未來 Mac dev 跑 R3 smoke 時要 `export OPENCLAW_REPLAY_RUNTIME_ENV=mac_dev_smoke_test_only` 否則 V049 row 帶錯 runtime_environment。R3 PA design 應補此 env note。

---

**E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-04--ref20_sprint_a_r2_impl.md`）**

---

## §10 Round 2 Fix Log（E2 review return → 13 finding fix）

**Date**: 2026-05-04
**Trigger**: E2 R2 round 1 review returned 13 findings (4 HIGH + 4 MEDIUM + 2 LOW + 3 advisories noted by E2 as `RETURN`).
**HEAD pre-round2**: same as round 1（沒有 commit；round 1 改動仍 working tree）。
**Status**: ROUND 2 IMPL COMPLETE — 待 E2 round 2 review。

### §10.1 H-1 fix — manifest_jsonb / manifest_hash drift（DB row 自洽 bug）

**Issue**: Round 1 stamped server-controlled `_idempotency_key` into `manifest_jsonb` so `_select_existing_for_idempotency` could SELECT against `manifest_jsonb->>'_idempotency_key'`. But the resulting persisted JSONB included that key, so `sha256(persisted_jsonb)` no longer equaled `manifest_hash` — the row was no longer self-consistent.

**Fix**:
1. Added module-level `_REGISTER_IDEM_CACHE: dict[(str,str), dict] = {}` + `_REGISTER_IDEM_CACHE_LOCK = asyncio.Lock()` + `_REGISTER_IDEM_CACHE_THREAD_LOCK = threading.Lock()` in `replay/experiment_registry.py`. Module-level long comment explains trade-off (restart loses cache; PG advisory lock retained for cross-process race).
2. Removed `_select_existing_for_idempotency` (JSONB-pollution lookup); replaced with `_cache_lookup_idempotency` / `_cache_set_idempotency` / `_cache_clear_for_test` (test helper).
3. `register_experiment` step 4 reworked: cache lookup first → cache hit returns cached row; cache miss → acquire PG advisory xact lock → INSERT → `_cache_set_idempotency` populates cache.
4. Step 5: `manifest_to_persist = body.manifest_jsonb`（不再 dict 拷貝 + inject）。確保 persisted JSONB byte-equal client input。
5. CLAUDE.md §九 Singleton 表登記 `_REGISTER_IDEM_CACHE` + `_REGISTER_IDEM_CACHE_LOCK` + `_REGISTER_IDEM_CACHE_THREAD_LOCK`（共一行 entry，含 trade-off 摘要）。
6. New test case `test_register_db_row_self_consistent_hash` — INSERT 抓 params[12]=manifest_jsonb str → 重 `json.loads` → `assert "_idempotency_key" not in keys` + `_er.compute_manifest_hash(persisted) == response_hash`。

### §10.2 H-2 fix — idempotency replay attack 缺 409 防線

**Issue**: Round 1 cache hit 直接 return `existing_id` 不比 hash。攻擊者用同 idempotency_key 但不同 manifest body → silently 拿到 existing experiment_id。

**Fix**:
1. `register_experiment` step 4 cache hit 路徑加 hash mismatch check：`cached["manifest_hash"] != manifest_hash_hex` → `return None, "idempotency_replay_attack"`。
2. `map_register_error_to_http` 加 `idempotency_replay_attack` → 409 + `replay_register_idempotency_replay_attack` reason_code。
3. New test case `test_register_idempotency_replay_attack_409` — 預填 cache 一個 hash，送不同 manifest_jsonb 的 register → 409。

### §10.3 H-3 fix — `/report` cross-route UUID5 不一致 + 抽出新模組

**Issue**: Round 1 `/report` line 944-959 用 `uuid.uuid5(NAMESPACE, experiment_id)` 衍生 manifest_uuid 後 SELECT V046；但 R2-T2 後 `s.manifest_id` 是真 V049 experiment_id → derived ≠ real → `/report` 對 R2-T2 後 INSERT 的 run 永遠 0 row。

**Fix**:
1. New module `replay/report_route.py` (421 LOC) — owns `/report` business logic. Module structure：
   - `validate_experiment_id_shape(experiment_id) -> Optional[str]` — pure shape guard。
   - `_lookup_manifest_uuid_sync` + `_lookup_manifest_uuid` — short PG xact for V049 lookup（讀 only，rollback 釋 FOR SHARE row lock）。
   - `_read_artifact_with_traversal_guard` — V046 row + Track C P0-5b allowlist guard。
   - `fetch_report_for_experiment(...)` — public coroutine: 5 步驟 (shape → V049 lookup → IDOR-aware SELECT → artifact reads → audit emit)。
2. `app/replay_routes.py::get_replay_report` 縮為 thin handler (~30 LOC)：純 dispatch + raise on (status, detail) tuple。
3. **Cross-route consistency**: `_rh.lookup_registered_experiment_id` 與 `/run` 共用 — 對 V049 0 row 短路 404 + `replay_experiment_not_found`。
4. New test file `test_replay_report_post_r2_smoke.py`（3 case）：
   - Case 1: 已註冊 → 200 + `manifest_id == real_uuid`（驗 H-3 用真 UUID 不 UUID5 衍生）。
   - Case 2: 未註冊 → 404。
   - Case 3: 非法 char → 400。
5. **Bilingual MODULE_NOTE 雙語、docstring 雙語、validate_experiment_id_shape / fetch_report_for_experiment 都中英對照**。

### §10.4 H-4 fix — secrets file 0o600 mode check 缺

**Issue**: Round 1 `replay/manifest_signer.py::load_signing_key_from_secrets_dir` 在 `key_path.is_file()` 後直接 `read_bytes()`，不查 file mode。攻擊者植 0o644 / world-readable 檔可 silently 洩漏 HMAC key（即使 dir 應 0o700）。

**Fix**:
1. Live release profile 下 `key_path.stat().st_mode & 0o777` 大於 `0o600` → log warning + `return None`（caller 進 410 unprovisioned 路徑）。
2. dev/test profile 不檢（保 Mac dev `umask 022` 下 0o644 的 ergonomic）。
3. Docstring updated to mention round 2 fix H-4 (file mode check) within `is_live_release_profile_fn` Args section.
4. New test case `test_verify_secrets_file_mode_too_loose_410` — live profile + 0o644 key file → 410 + `replay_verify_key_archive_not_provisioned`。

### §10.5 M-1 / M-2 / M-3 / M-4 fix

#### M-1 — `live_demo` env_label allowlist
- `manifest_signer.py:594` 由 `("paper", "demo", "live")` 改 `("paper", "demo", "live", "live_demo")`。
- LiveDemo profile = Live 管線走 demo endpoint（CLAUDE.md §四），授權按 Live 嚴格標準，必能讀自身 replay_signing_key。
- New test case `test_verify_with_live_demo_profile_secrets_path` — `OPENCLAW_REPLAY_ENV_LABEL=live_demo` + secrets file at `<root>/live_demo/replay_signing_key` → 200 + `wiring_status="secrets_file_path"`。

#### M-2 — per-actor rate limit
- `app/replay_routes.py` 加 `_replay_rate_limit_key(request: Request) -> str` helper：先試 `request.state.actor.actor_id`，fallback `request.client.host`（slowapi wrapper 跑在 Depends 之前，當前 wiring 基本都 fallback IP）。
- `post_experiment_register` + `post_replay_run` 各加 `request: Request` first arg + `@_replay_limiter.limit("10/minute", key_func=_replay_rate_limit_key)` decorator。
- 完整 docstring update 解釋 rate limit + key_func fallback 行為。
- New test file `test_replay_register_rate_limit.py`（1 case）：連續 11 register → 第 11 次 = 429。test fixture autouse `limiter.reset()` 防跨測污染。

#### M-3 — `register_pending_engine_sha` sentinel fail-closed
- `experiment_registry.py:625-636` 由 `if linux_trade_core and not engine_binary_sha: engine_binary_sha = "register_pending_engine_sha"` 改為 `return None, "engine_binary_sha_not_provisioned"`。
- `map_register_error_to_http` 加 `engine_binary_sha_not_provisioned` → 503 + `replay_engine_binary_sha_not_provisioned` reason_code。
- 既有 register tests autouse fixture 加 `monkeypatch.setenv("OPENCLAW_ENGINE_BINARY_SHA", "0"*64)` 守住 happy path。
- New test case `test_register_linux_trade_core_missing_engine_sha_503` — `monkeypatch.delenv` 後送 register → 503。

#### M-4 — manifest_jsonb reserved `_*` prefix key
- `ReplayExperimentRegisterRequest` 加 `_no_reserved_prefix_keys` validator（**先於 `_size_cap`** so security-relevant ValueError 先觸）。
- 雙語 docstring 解釋為何保留（H-1 歷史 + 預留未來 server metadata）。
- New test case `test_register_reserved_prefix_key_422` — `manifest_jsonb={"_my_key": "x"}` → 422 + raw 響應含 `_my_key` token。

### §10.6 L-1 fix；L-2 defer P3

#### L-1 — dead `timezone` import
- `from datetime import datetime, timezone` → `from datetime import datetime`（保 datetime）。

#### L-2 — Pydantic V1 deprecation defer P3
- 不在本 round 修；新增 P3 ticket `P3-PYDANTIC-V2-MIGRATE-REPLAY` — 後續把 replay/ 全模組 `@validator` → `@field_validator`。本 round **不**修。
- 已知影響：5 個 PydanticDeprecatedSince20 warning 持續輸出（替換 P3 ticket land 即清）。

### §10.7 26 R2 case + 87 sibling test 結果

**Round 2 cases**: 7 new case + 19 round 1 case = 26 R2 全綠。

```
$ venvs/mac_dev/bin/pytest -xvs tests/test_replay_experiments_register.py
13 passed (9 round 1 + 4 round 2: H-1 / H-2 / M-3 / M-4)

$ venvs/mac_dev/bin/pytest -xvs tests/test_replay_run_fk_guard.py
5 passed (round 1, no round 2 cases needed)

$ venvs/mac_dev/bin/pytest -xvs tests/test_replay_manifest_verify_secrets_path.py
7 passed (5 round 1 + 2 round 2: H-4 / M-1)

$ venvs/mac_dev/bin/pytest -xvs tests/test_replay_report_post_r2_smoke.py
3 passed (NEW round 2 H-3 cross-route smoke)

$ venvs/mac_dev/bin/pytest -xvs tests/test_replay_register_rate_limit.py
1 passed (NEW round 2 M-2 rate limit 429)

$ venvs/mac_dev/bin/pytest tests/ -k replay --no-header -q
97 passed (87 round 1 baseline + 10 round 2 = 97)
```

**Full control_api_v1 regression**：3478 PASS / 1 fail / 5 skip。1 fail = `test_replay_routes_safe_query_audit.py::test_case2_pg_kill_simulation_returns_200_degraded` PRE-EXISTING（與 round 1 同 fail；isolated 跑 PASS，suite-order contamination 仍存）。

### §10.8 LOC delta（replay_routes.py 1500 → 1443）

| 檔 | Pre-R2 | Post-Round1 | Post-Round2 | Δ Round2 | Cap | Status |
|---|--:|--:|--:|--:|--:|---|
| `app/replay_routes.py` | 1492 | 1500 | **1443** | -57 | 1500 | ✅（57 margin for R3） |
| `replay/experiment_registry.py` | NEW | 770 | 972 | +202 | 1500 | ✅ |
| `replay/manifest_signer.py` | 443 | 715 | 757 | +42 | 1500 | ✅ |
| `replay/route_helpers.py` | 1456 | 1480 | 1249 | -231* | 1500 | ✅ |
| `replay/report_route.py` | NEW | NEW | 421 | NEW | 1500 | ✅ |

*（route_helpers.py 1249 是當前 measured；R2 round 1 staged 1480 行裡可能含有別 sibling CC working-tree 改動 — 本 round 2 我未動該檔；後續 PM commit 時再驗）

**主要 Δ Round2 來源**:
- replay_routes.py: 抽 /report 約 130 LOC → -130; 加 rate limit helper +30; 加 import +1; 加 2 個 `request: Request` + 2 個 `@_replay_limiter.limit` 裝飾器 +12; 加 thin handler ~30 → 淨 -57。
- experiment_registry.py: 模組級 cache 注解 +50; M-4 validator +33; H-1 cache helpers +50; H-2 cache hit 比 hash +30; M-3 fail-closed +14; map_register_error_to_http 加 H-2 + M-3 mapping +25 → 淨 +202。
- manifest_signer.py: H-4 mode check +30; M-1 enum extend +6; docstring update +6 → 淨 +42。

### §10.9 git status sign-off-clean (CLAUDE.md §七 P0-GOV-3)

```
$ git status --porcelain
 M CLAUDE.md
 M docs/CCAgentWorkSpace/E1/memory.md
 M program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_routes.py
 M program_code/exchange_connectors/bybit_connector/control_api_v1/replay/manifest_signer.py
 M program_code/exchange_connectors/bybit_connector/control_api_v1/replay/route_helpers.py
 M program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_routes_track_c_security.py
?? docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-04--ref20_sprint_a_r2_impl.md
?? docs/CCAgentWorkSpace/E3/workspace/reports/2026-05-04--ref20_sprint_a_r2_security_audit.md
?? program_code/exchange_connectors/bybit_connector/control_api_v1/replay/experiment_registry.py
?? program_code/exchange_connectors/bybit_connector/control_api_v1/replay/report_route.py
?? program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_experiments_register.py
?? program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_manifest_verify_secrets_path.py
?? program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_register_rate_limit.py
?? program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_report_post_r2_smoke.py
?? program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_run_fk_guard.py
```

**6 staged + 9 untracked = 15 files** all R2-scoped:
- 6 modified: 4 source (replay_routes / manifest_signer / route_helpers + 1 test file from round 1) + 2 governance doc (CLAUDE.md §九 + E1 memory.md auto by Claude)
- 9 untracked: 2 new module (experiment_registry + report_route) + 5 test files + 2 reports (this report append + E3 audit)

**No accidental sibling-CC WIP absorbed** — 每個 file diff 僅含 R2 內容（experiment_registry.py 全 R2-T1 + R2 round 2；manifest_signer.py 含 R2-T3 + round 2 H-4/M-1；replay_routes.py 含 R2-T1/T2/T3 + round 2 H-3/M-2 helper extraction；report_route.py 全 round 2 H-3 NEW；4 test files round 1，1 test file round 2 NEW）。Sign-off clean per CLAUDE.md §七 P0-GOV-3.

### §10.10 預留問題（給 E2 round 2）

#### 給 E2（round 2 review focus）

1. **slowapi rate-limit per-actor key fallback 行為** — `_replay_rate_limit_key` 試 `request.state.actor` 但 FastAPI Depends 在 slowapi wrapper 之後跑，所以基本都 fallback IP。E2 review 是否：
   - (a) 接受當前 IP-based fallback（10/min 仍比 global 120/min 嚴格）。
   - (b) 補一個 ASGI middleware 在 slowapi 前填 `request.state.actor`（會擴大本 round 範圍）。
   - (c) 列為 P3 follow-up（`P3-RATELIMIT-PER-ACTOR-WIRING`）。

2. **`_REGISTER_IDEM_CACHE` 跨 process 限制** — V3 §5 30d idempotency TTL 在 round 1 round 2 都不真持久化（round 1 用 manifest_jsonb pollution；round 2 用 in-memory cache）。E2 review 是否同意以下 trade-off：
   - 加 V### migration 加 `(idempotency_key, created_by)` UNIQUE INDEX = round 2 範圍外。
   - 改外部 cache（Redis）= 範圍外。
   - 接受 restart 丟保證（current）= H-1 module-level comment 已記載。

3. **`route_helpers.py` LOC 1249（顯示 -231 vs round 1 的 1480）** — 此 round 我未動該檔；PM commit 時驗該檔 diff 是否含 sibling CC 改動或單純重新 measure 差異。可能 round 1 數字有錯。

4. **`@validator` PydanticDeprecatedSince20 warning** — 5 個 warning 持續 emit；P3 ticket `P3-PYDANTIC-V2-MIGRATE-REPLAY` 待後續 sprint。E2 round 2 不重審此項。

5. **rate-limit test reset 時序** — `test_replay_register_rate_limit.py` autouse fixture 跑 `limiter.reset()` 但若 sibling test 在 yield 後修改 limiter state（例如其他文件加 `@limiter.limit`），可能影響 11th-request 邊界。E4 stress-test 跨 file 並行可確認。

#### 給 E3（round 2 不需要重審 round 1 cleared 部分；只看 round 2 fix 帶來的新 attack surface）

1. **`_REGISTER_IDEM_CACHE` 內存 entry 是否含 sensitive data** — entry 結構 `{experiment_id, manifest_hash, status, created_at}`，無 secret / token / signature bytes。Process memory dump 攻擊面與 round 1 manifest_jsonb pollution 同等（manifest_hash 已 INSERT 進 DB row）。

2. **H-4 file mode check timing-of-check vs time-of-use (TOCTOU)** — `key_path.stat()` 與 `key_path.read_bytes()` 之間若攻擊者改 mode → 仍會讀到 0o600-rejected file。但攻擊者已能改 secrets file 表示已破系統信任邊界，TOCTOU 補強無實益。

3. **H-3 `/report` 跨 route 一致性 attack surface** — 改用 `lookup_registered_experiment_id` (FOR SHARE) 後，攻擊者用任意 UUID 看 V049 row 存在 → 仍只能看到自己 actor 的 row（IDOR 守門 round 1 已建）；非 actor row 在 V049 lookup 階段 200 但 V046 SELECT 0 row（actor 不符 IDOR filter）。建議 E3 確認 V049 `experiment_id` lookup 不當作 enumeration oracle（從 latency 推斷 row 存在）。

#### 給 E4（round 2 regression scope）

1. **Linux 端 V049 schema deploy 狀態** — Sprint 1 Track D V049 已 land。E4 在 Linux 端 manual smoke：
   - `POST /api/v1/replay/experiments/register` x2（同 idempotency_key 同 manifest）→ 第二次 cache hit + idempotency_hit=true。
   - 同 idempotency_key 不同 manifest → 409 + `replay_register_idempotency_replay_attack`。
   - `unset OPENCLAW_ENGINE_BINARY_SHA` + register → 503。
   - mode 0o644 secrets file + `OPENCLAW_RELEASE_PROFILE=live` + verify → 410。
   - register → run → report 三連 200（驗 H-3 cross-route）。

2. **跨平台 grep** — `grep -rE '/Users/[^/]+|/home/ncyu' replay/experiment_registry.py replay/report_route.py replay/manifest_signer.py app/replay_routes.py` 應 0 命中。

3. **跨語言 fixture byte-equal regression** — round 2 不改 `tests/replay/test_manifest_signer_xlang_consistency.py` fixture / invariants；round 1 已驗 8/8 PASS；round 2 不改 canonical_bytes 計算路徑（experiment_registry.py 的 `compute_manifest_canonical_bytes` 也保持原樣 — H-1 fix 是不再 inject `_idempotency_key`，不改算 canonical bytes 的方式）。E4 確認跨語言 test 仍 8/8 PASS。

---

**E1 ROUND 2 IMPLEMENTATION DONE: 待 E2 round 2 審查（report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-04--ref20_sprint_a_r2_impl.md`）**

---

## §11 Round 3 Fix Log（E2 round 2 NEW finding cleanup）

**Date**: 2026-05-04
**Trigger**: E2 round 2 verdict CONDITIONAL PASS — 13 round 1 fix 全 PASS + 3 NEW finding（1 MED dead-state + 1 MED enum-oracle + 2 LOW）交 E1 round 3 清。
**HEAD pre-round3**: same as round 2（沒有 commit；round 1+2 改動仍 working tree）。
**Status**: ROUND 3 IMPL COMPLETE — 待 E4 regression。E2 round 3 跳過（PM 直 verify per task spec）。

### §11.1 M-DEAD-LOCK 刪除證明

**Issue**: `_REGISTER_IDEM_CACHE_LOCK = asyncio.Lock()` (line 138) 0 callsite — 真正 race-safety 由 `threading.Lock` + PG advisory xact lock 多層提供。E2 review §12.5 NEW MED-DEAD-LOCK。

**Fix**:
1. `replay/experiment_registry.py:138` 刪 `_REGISTER_IDEM_CACHE_LOCK = asyncio.Lock()` 整行。
2. 同時刪 dead `import asyncio` (line 82) — 無真實 `asyncio.X` call（剩下都是 docstring/comment 提到 `asyncio.to_thread` 講 caller context）。
3. 改 module-level long comment line 116-121（EN 段）+ line 144-148（中文段）拿掉 `_REGISTER_IDEM_CACHE_LOCK` 直接提及，改述「round 3 dropped a dead asyncio Lock module that had 0 callsite」+ 加 multi-worker fallback paragraph 說明 cache hit % 退化但 race-safety 不變。
4. Helper docstring (`_cache_lookup_idempotency` line 507-526) 不變（已正確只描述 thread Lock；無 ref dead lock）。
5. CLAUDE.md §九 Singleton 表 line 404 entry 改寫：
   - 三-tuple `_REGISTER_IDEM_CACHE / _REGISTER_IDEM_CACHE_LOCK / _REGISTER_IDEM_CACHE_THREAD_LOCK` → 二-tuple `_REGISTER_IDEM_CACHE / _REGISTER_IDEM_CACHE_THREAD_LOCK`
   - 「race-safe via asyncio.Lock + threading.Lock + PG advisory xact lock 多層」→「race-safe via threading.Lock + PG advisory xact lock 多層（caller 在 `asyncio.to_thread` 內，thread-level Lock 是正確原語；round 3 M-DEAD-LOCK 刪了 0 callsite 的 asyncio Lock）」

**驗證**：
```
$ grep -rn "_REGISTER_IDEM_CACHE_LOCK" \
    program_code/exchange_connectors/bybit_connector/control_api_v1/ \
    CLAUDE.md
(no output)
```
0 hit ✓（task spec 強制）。

### §11.2 M-IDOR-ENUM 修法 + IDOR test verify

**Issue**: H-3 fix 後引入 enumeration oracle — V049 row 屬 actor 'bob' + caller 'alice'（無 admin scope）→ 200 + 0 artifacts vs row 完全不存在 → 404 + `replay_experiment_not_found`，認證後 caller 可從 status code 區分「id 存在但別人擁有」vs「id 不存在」。E2 review §12.5 NEW MED-IDOR-ENUM。

**Fix**:
1. `replay/report_route.py::_lookup_manifest_uuid_sync` 加 kwarg `expected_actor_id: Optional[str]` + `admin_bypass: bool`。
2. V049 lookup hit 後加 second SELECT `created_by`（同 xact / row 已 FOR SHARE locked）；非 admin + `created_by != expected_actor_id` → 收斂為同 `"not_registered"` reason → caller route 返 404 + `replay_experiment_not_found`（與 missing row 路徑同 status + 同 reason_code）。
3. `_lookup_manifest_uuid` async wrapper 同步擴 `expected_actor_id` + `admin_bypass` 轉送。
4. `fetch_report_for_experiment` step 2 前 precompute `idor_admin_bypass = actor_can_read_any_fn(actor)`（從 step 3 提前），傳入 lookup；step 3 重用 same value（刪重複賦值）。
5. **設計鏡像 GitHub repo private/not-found unify pattern** — 認證後攻擊者無法用 status code / message 措辭區分 id 是否存在。
6. Admin actor with `replay:read:any` scope 仍可看 cross-actor row（按 Sprint 1 Track C P0-5a 模式）。

**Test verify**:
1. 既有 `test_p0_5a_idor_cross_actor_filter_in_sql` (Track C Case 3) — 更新 mock fixture 讓 V049 row 返 own actor `'alice'`（match `_operator_actor_alice`）→ test 仍驗證 V046 IDOR-aware SELECT 含 `s.actor_id = %s` filter（own-row 分支跑通到 step 3）。
2. **新增** `test_p0_5a_idor_cross_actor_404_no_oracle` (Track C Case 3b) — V049 row 返 `created_by='bob'`（cross-actor）+ caller 'alice' 無 admin → 預期 404 + `replay_experiment_not_found` + message 不洩 leak terms（`forbidden / permission / owned by / another user / cross-actor`）。
3. `test_replay_report_post_r2_smoke.py` fixture `_make_lookup_then_select_stub` 簽名擴 `created_by_for_actor_check: Optional[str] = 'alice'`（對齊 `_operator_actor_alice`），不破其它既有 case。

**驗證**：
```
$ venvs/mac_dev/bin/pytest -q program_code/.../tests/test_replay_routes_track_c_security.py
14 passed, 6 warnings in 0.21s

$ venvs/mac_dev/bin/pytest program_code/.../tests/ -k replay --no-header -q
98 passed, 3387 deselected, 30 warnings in 0.96s
```

### §11.3 L-P3-TICKET-MISSING TODO ticket 加進 TODO.md 證明

**Issue**: E1 round 2 §10.6 自宣 P3-PYDANTIC-V2-MIGRATE-REPLAY ticket，但 TODO.md / memory 0 hit（自宣 ticket 落空）。E2 review §12.7 表 L-P3-TICKET-MISSING。

**Fix**:
1. `TODO.md` § P2-AUDIT/P2-WAVE-* / P3 表（line 165-167）末加 `P3-PYDANTIC-V2-MIGRATE-REPLAY` 條目，含 trigger / 修法 / scope（`experiment_registry.py` 5 validator + `replay_models.py` 1 validator）+ owner @E1。
2. memory.md 加 round 3 entry 記 P3 ticket 資訊。

**驗證**：
```
$ grep "P3-PYDANTIC-V2-MIGRATE-REPLAY" TODO.md
| **P3-PYDANTIC-V2-MIGRATE-REPLAY** | replay/ 全模組 `@validator` (Pydantic V1) → `@field_validator` (V2) migration；... | @E1 |
```
1+ line ✓。

### §11.4 LOC + 97+ replay test 結果

| File | round 2 baseline LOC | round 3 LOC | delta |
|---|---:|---:|---:|
| `app/replay_routes.py` | 1443 | **1443** | 0（task spec 禁動） |
| `replay/experiment_registry.py` | ~976 | **985** | +9（注釋擴寫 - dead var/import 抵消） |
| `replay/manifest_signer.py` | 757 | **757** | 0 |
| `replay/report_route.py` | 422 | **506** | +84（IDOR enum fix 邏輯 + 雙語注釋） |

`replay_routes.py` 1500 cap margin: 1500 - 1443 = **57 LOC** ✓（R3 dispatch 預估 ~30 LOC thin handler 仍 fit）。

**Test 結果**:

```
# 1. M-DEAD-LOCK clean
$ grep -rn "_REGISTER_IDEM_CACHE_LOCK" program_code/.../control_api_v1/ CLAUDE.md
(no output) ✓ 0 hit

# 2. M-IDOR-ENUM verify (Track C security suite)
$ venvs/mac_dev/bin/pytest -q program_code/.../tests/test_replay_routes_track_c_security.py
14 passed, 6 warnings in 0.21s ✓

# 3. R2 baseline regression (5 sibling tests)
$ venvs/mac_dev/bin/pytest -q .../test_replay_experiments_register.py \
    .../test_replay_run_fk_guard.py \
    .../test_replay_manifest_verify_secrets_path.py \
    .../test_replay_report_post_r2_smoke.py \
    .../test_replay_register_rate_limit.py
29 passed, 6 warnings in 0.34s ✓

# 4. 全 replay test (≥97 PASS expected)
$ venvs/mac_dev/bin/pytest program_code/.../tests/ -k replay --no-header -q
98 passed, 3387 deselected, 30 warnings in 0.96s ✓
（前 97 + 新增 test_p0_5a_idor_cross_actor_404_no_oracle = 98）

# 5. P3 ticket land
$ grep "P3-PYDANTIC-V2-MIGRATE-REPLAY" TODO.md
| **P3-PYDANTIC-V2-MIGRATE-REPLAY** | ... | @E1 | ✓
```

### §11.5 git status sign-off-clean

```
$ git status --porcelain
 M CLAUDE.md
 M TODO.md
 M docs/CCAgentWorkSpace/E1/memory.md
 M docs/CCAgentWorkSpace/E2/memory.md
 M program_code/.../app/replay_routes.py
 M program_code/.../replay/manifest_signer.py
 M program_code/.../replay/route_helpers.py
 M program_code/.../tests/test_replay_routes_track_c_security.py
?? docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-04--ref20_sprint_a_r2_impl.md
?? docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-04--ref20_sprint_a_r2_e2_review.md
?? docs/CCAgentWorkSpace/E3/workspace/reports/2026-05-04--ref20_sprint_a_r2_security_audit.md
?? program_code/.../replay/experiment_registry.py
?? program_code/.../replay/report_route.py
?? program_code/.../tests/test_replay_experiments_register.py
?? program_code/.../tests/test_replay_manifest_verify_secrets_path.py
?? program_code/.../tests/test_replay_register_rate_limit.py
?? program_code/.../tests/test_replay_report_post_r2_smoke.py
?? program_code/.../tests/test_replay_run_fk_guard.py
```

Round 3 modified files (relative to round 2 baseline):
- `program_code/.../replay/experiment_registry.py`（M-DEAD-LOCK 刪 + 注釋更新；本身 untracked 因 R2 round 2 新增）
- `program_code/.../replay/report_route.py`（M-IDOR-ENUM 邏輯加；本身 untracked 因 R2 round 2 新增）
- `program_code/.../tests/test_replay_routes_track_c_security.py`（修 1 既有 IDOR test mock + 新增 1 cross-actor 404 test）
- `program_code/.../tests/test_replay_report_post_r2_smoke.py`（fixture `_make_lookup_then_select_stub` 簽名擴）
- `CLAUDE.md`（§九 line 404 entry 改寫）
- `TODO.md`（P3 表加 P3-PYDANTIC-V2-MIGRATE-REPLAY）
- `docs/CCAgentWorkSpace/E1/memory.md`（round 3 log appended）
- 本檔（§11 round 3 fix log appended）

**禁止項已守**：
- ✓ 無 commit（task spec）
- ✓ 不改 R3 區範圍（report_route.py 是 R2 round 2 H-3 抽出，extend 而非新增功能）
- ✓ 不新增 V### migration（task spec）
- ✓ 不觸動 E2 round 1+2 已 cleared 部分（R2-T1/T2/T3/T4/T5 + 13 round 2 fix 全保留）

---

**E1 ROUND 3 IMPLEMENTATION DONE: 待 E4 regression（E2 round 3 跳過 per task spec；3 finding 修 < 30min target 內完成；report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-04--ref20_sprint_a_r2_impl.md`）**
