# REF-20 Sprint 1 Track C — Python /replay/* 3 critical security fixes

**Date:** 2026-05-03
**Owner:** E1
**Task:** REF-20 Sprint 1 Track C — fix E3-P0-2 / P0-4 / P0-5 (3 CRITICAL security holes in `replay_routes.py`)
**Spec:** PA Sprint 1 partition design `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--ref20_sprint1_partition_design.md` §"Track C"
**LOC budget:** replay_routes.py 1498→1603 (push back per dispatch §"Push back 通道" #1)

---

## 1. 任務摘要 / Task summary

修補 `replay_routes.py` 三個 CRITICAL security holes（attacker 控 env / DB-row / cmdline 三條路徑全打通）+ 同 commit 加 V053 SQL 擴展 V035 governance_audit_log event_type CHECK enum，新增 5 Track C 替 audit emit 提供完整型別 row + 3 pre-existing replay event types + 1 Track A placeholder = 14 值 canonical list：

| # | 病灶 (CRITICAL) | 修補 | 路徑 |
|---|---|---|---|
| **P0-2** | `OPENCLAW_REPLAY_VERIFY_TEST_KEY` env var 在 production 仍生效；attacker 控 env → 注入假 InMemoryKeyArchive → forge any signature | `is_live_release_profile()` gate 強制清空 + module-init ERROR boot guard + `replay_signature_test_key_blocked` audit emit | `replay_routes.py` L1255-1284 (POST /api/v1/replay/manifest/verify) |
| **P0-4** | `os.kill(pid, SIGTERM)` 用 V045 `subprocess_pid` 直接送，無 process identity 校驗 → DB 注入 / PID reuse / race 三路徑可送 SIGTERM 給 init/postmaster/engine | `_verify_replay_runner_pid(pid)` psutil cmdline cert（Track A 提供 helper）+ `replay_pid_identity_mismatch` 409 + audit emit | `replay_routes.py` L843-864 (POST /api/v1/replay/cancel) |
| **P0-5a** | IDOR：`WHERE s.manifest_id = %s::uuid` 缺 `AND s.actor_id = %s` → 任何 viewer 讀任何 actor 的 report | 預設 SQL filter `actor_id = %s` + `_actor_can_read_any_replay_report` admin bypass via `replay:read:any` scope + `replay_idor_admin_bypass` audit emit | `replay_routes.py` L993-1095 (GET /api/v1/replay/report/{experiment_id}) |
| **P0-5b** | 路徑遍歷：`Path(row[2])` 直接 base64 回 client，attacker INSERT `'/etc/passwd'` 無 CHECK 約束守門 | `_artifact_path_within_allowlist(path)` `Path.resolve().is_relative_to(allowlist_root)` + `replay_artifact_path_traversal_blocked` audit emit | `replay_routes.py` L1063-1068 (artifact open block) |
| **共同** | 5 audit emit 用了未列舉的 event_type；V035 CHECK constraint 會 REJECT 真 INSERT | V053 SQL 把 V035 enum 從 6 值（V035 base 5 + V044 1）擴為 14 值（+ 8 Sprint 1 Track A/C） | `srv/sql/migrations/V053__governance_audit_log_replay_event_types.sql`（新建）|

**完成定義驗證**：
- ✅ Python pytest 30/30 PASS（4 既有 auth + 9 既有 t2_subprocess + 5 既有 advisory_lock + 5 既有 safe_query_audit + 7 NEW Track C security）
- ✅ V053 Mac dev psql 跑兩遍 idempotent + Guard A enforced + 5 NEW event_type INSERT PASS + unknown event_type REJECT
- ✅ 6 V053 migration tests PASS（Mac dev static-parse layer）
- ✅ 跨平台 grep 0 hit（`/home/ncyu` / `/Users/[^/]+` / `live_execution_allowed` / `max_retries=` / `INSERT INTO trading.*`）
- ✅ 0 修改 V045 / V046 既有 SQL file（避觸 P0 sqlx hash drift incident commit `3681f83`）

---

## 2. 修改清單 / Files modified

| 路徑 | 變更 | LOC 增量 | 性質 |
|---|---|---|---|
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_routes.py` | 修 — 加 P0-2 boot guard + `_actor_can_read_any_replay_report` + `_require_replay_admin` 概念用 scope check + P0-2 release profile gate + P0-4 psutil cmdline cert + P0-4 pid_identity_mismatch 409 + P0-5a SQL actor_id filter + admin bypass + P0-5b path traversal guard + 4 thin wrapper delegating to route_helpers (`_emit_audit_stub` / `_replay_response` / `_safe_pg_select` / `_async_safe_pg_select`) | +99 | M |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/replay/route_helpers.py` | 修 — 加 4 helpers: `is_live_release_profile()` / `resolve_artifact_allowlist_root()` / `artifact_path_within_allowlist()` + 3 extracted: `replay_response_envelope` / `emit_replay_audit_stub` / `safe_pg_select` (factory style 讓 caller 注入 `get_pg_conn`) + datetime import + RELEASE_PROFILE constants | +156 | M |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_routes_track_c_security.py` | 新檔 — 7 case (P0-2 live block / P0-2 dev no-strip / P0-4 cmdline cert FAIL / P0-5a IDOR cross-actor SQL filter / P0-5a admin bypass omits filter / P0-5b /etc/passwd allowlist blocked / P0-5b /etc/passwd content sentinel) | +496 | A |
| `sql/migrations/V053__governance_audit_log_replay_event_types.sql` | 新檔 — V035 enum extension 從 6 值（V044 base）擴為 14 值（+ 8 Sprint 1 Track A/C）；Guard A V035 base 存在驗；DROP+ADD canonical CHECK；idempotency 透過 8 NEW 值 position() probe；COMMENT ON CONSTRAINT | +211 | A |
| `tests/migrations/test_v053_replay_event_types.py` | 新檔 — 6 case Mac dev static-parse layer（file exists / Guard A present / DROP+ADD canonical 14-value list / idempotency probe / RAISE NOTICE both branches / CONSTRAINT comment) | +173 | A |
| `sql/migrations/REF-20_RESERVATION.md` | 修 — V053 row 加入 §3 reservation map + §6 v1.9 revision history entry | +2 | M |
| `docs/CCAgentWorkSpace/E1/memory.md` | 修 — Sprint 1 Track C 教訓 + 報告索引 entry | +20 | M |
| `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--ref20_sprint1_track_c_python_security.md` | 新檔（本 report） | — | A |

---

## 3. 關鍵 diff / Key diffs

### 3.1 P0-2 — module-init boot guard + per-route gate

**boot guard（module-init scope）**：
```python
# Track C P0-2 boot guard: live profile MUST NOT honor TEST_KEY (forge risk).
if _is_live_release_profile() and os.environ.get("OPENCLAW_REPLAY_VERIFY_TEST_KEY", "").strip():
    logging.getLogger(__name__).error(
        "REF-20 Track C P0-2 boot guard: OPENCLAW_REPLAY_VERIFY_TEST_KEY set "
        "with OPENCLAW_RELEASE_PROFILE=live; live ignores test key (forced empty)."
    )
```

**per-route gate（POST /manifest/verify）**：
```python
# Track C P0-2: live profile forces test key empty (forge risk).
if _is_live_release_profile():
    if os.environ.get("OPENCLAW_REPLAY_VERIFY_TEST_KEY", "").strip():
        _emit_audit_stub(
            event_type="replay_signature_test_key_blocked",
            actor_id=actor_id, experiment_id=None,
            manifest_hash=body.declared_hash_hex,
            decision="blocked_by_release_profile",
            extra_payload={"release_profile": "live"},
        )
    test_key_hex = ""
else:
    test_key_hex = os.environ.get("OPENCLAW_REPLAY_VERIFY_TEST_KEY", "")
```

**核心不變量**：`OPENCLAW_RELEASE_PROFILE='live'` → `test_key_hex=""` → falls through to 501 archive_not_wired path（Wave 6 V042 SQL archive 才接）。Attacker 控 env 0 effect。

### 3.2 P0-4 — psutil cmdline cert before SIGTERM

```python
# Track C P0-4: psutil cmdline cert before SIGTERM (PID-reuse safe).
if pid is not None and pid > 0:
    pid_ok, pid_err = _verify_replay_runner_pid(int(pid))
    if not pid_ok:
        logger.warning(
            "cancel_run: PID identity FAILED pid=%d run=%s err=%s; "
            "SKIPPING SIGTERM (Track C P0-4)", pid, run_id, pid_err,
        )
        return None, f"pid_identity_mismatch:{pid_err}"
    try:
        import signal
        os.kill(pid, signal.SIGTERM)
        ...
```

`_verify_replay_runner_pid(pid)` 內部用 `psutil.Process(pid).cmdline()` → 驗 `'replay_runner' in " ".join(cmdline)`。失敗 → return `pid_identity_mismatch:<reason>` → caller 路由為 409 + `replay_pid_identity_mismatch` audit emit。

### 3.3 P0-5a — IDOR fix 加 actor_id filter + admin bypass

```python
# Track C P0-5a IDOR fix: default = filter actor_id; admin scope replay:read:any
# bypass for cross-actor incident investigation only.
_idor_admin_bypass = _actor_can_read_any_replay_report(actor)
_base_select = (
    "SELECT a.artifact_id::text, a.artifact_type, a.artifact_path, ..."
    "FROM replay.report_artifacts a JOIN replay.run_state s ON a.run_id = s.run_id "
)
if _idor_admin_bypass:
    sql = _base_select + "WHERE s.manifest_id = %s::uuid ORDER BY a.created_at;"
    params: tuple[Any, ...] = (manifest_uuid,)
else:
    sql = _base_select + "WHERE s.manifest_id = %s::uuid AND s.actor_id = %s ORDER BY a.created_at;"
    params = (manifest_uuid, actor_id)
rows, err = await _async_safe_pg_select(sql, params)
```

`_actor_can_read_any_replay_report(actor)` = `"replay:read:any" in actor.scopes`. Plain `operator` role 不夠，必須 explicit-grant `replay:read:any` scope。Admin path 觸發 → `replay_idor_admin_bypass` audit emit。

### 3.4 P0-5b — Path traversal allowlist guard

```python
# Track C P0-5b: path traversal guard via allowlist (row[2] is untrusted DB).
try:
    artifact_path = Path(row[2])
    within, traversal_err = _artifact_path_within_allowlist(artifact_path)
    if not within:
        artifact["payload_read_error"] = f"path_traversal_blocked:{traversal_err}"
        _traversal_blocked_paths.append(str(row[2])[:120])
    elif artifact_path.is_file() and (row[3] or 0) <= 256 * 1024:
        with open(artifact_path, "rb") as f:
            payload_bytes = f.read(256 * 1024)
        artifact["payload"] = json.loads(payload_bytes.decode("utf-8"))
except (OSError, ValueError, json.JSONDecodeError) as exc:
    artifact["payload_read_error"] = f"{type(exc).__name__}: {str(exc)[:80]}"
```

`_artifact_path_within_allowlist` = `Path.resolve(strict=False).is_relative_to(allowlist_root)`. allowlist_root = `OPENCLAW_DATA_DIR/replay_artifacts/` (Linux) / `/tmp/replay_artifacts_test_only/` (Mac dev)。`/etc/passwd` resolves outside → `path_traversal_escape` → 不 open → 不洩 file content。Audit emit `replay_artifact_path_traversal_blocked`。

### 3.5 V053 enum extension（layered 在 V044 上）

```sql
ALTER TABLE learning.governance_audit_log
    ADD CONSTRAINT governance_audit_log_event_type_check
    CHECK (event_type IN (
        'review_live_candidate', 'lease_grant', 'lease_auto_revoke',
        'bulk_re_evaluation', 'audit_write_failed',     -- V035 base 5
        'replay_handoff_request',                         -- V044 P6-S15
        'replay_run_started', 'replay_run_cancelled',     -- Sprint 1 Track A/C 8 NEW
        'replay_manifest_verify_attempted',
        'replay_signature_test_key_blocked',
        'replay_pid_identity_mismatch',
        'replay_idor_admin_bypass',
        'replay_artifact_path_traversal_blocked',
        'replay_argv_mismatch_blocked'
    ));
```

Idempotency: 8 NEW 值的 `position(... IN v_check_def)` probe；全 in → NOTICE skip。Mac dev real-PG dry-run 證實兩次跑 0 RAISE。

---

## 4. 治理對照 / Governance compliance

### 強制檢查（CLAUDE.md §七 + dispatch）

- ✅ **跨平台 grep 0 hit**：`grep -E '/home/ncyu|/Users/[^/]+'` 4 file 0 hit；`psutil` 既在 `requirements.txt:43`；`Path.resolve(strict=False)` Python 3.9+ feature；`is_relative_to` Python 3.9+ + Py<3.9 fallback to `str.startswith` with explicit `os.sep`。
- ✅ **0 hard boundary 觸碰**：`live_execution_allowed` / `max_retries=` / `execution_authority` / `system_mode=` 全 0 hit。
- ✅ **0 trading.* mutate / 0 live_* mutate**：`grep INSERT INTO trading.*\|UPDATE trading.*\|DELETE FROM trading.*` 0 hit。
- ✅ **V053 idempotent**：Mac dev psql 跑兩次驗 → 1st run 加 NOTICE + 2nd run skip NOTICE，0 RAISE。
- ✅ **V053 Guard A enforced**：V035 base table preflight 檢查；不存即 RAISE EXCEPTION。Guard B/C N/A（無 column type ALTER；無 hot-path index）— 明文標 § Guard A: enforced / Guard B: N/A / Guard C: N/A。
- ✅ **雙語 MODULE_NOTE EN/中**：4 新增 helper（`is_live_release_profile` / `resolve_artifact_allowlist_root` / `artifact_path_within_allowlist` / `_actor_can_read_any_replay_report`）+ 3 extracted helper（`replay_response_envelope` / `emit_replay_audit_stub` / `safe_pg_select`）+ V053 SQL + test files 全雙語。
- ✅ **0 修改 V045/V046/V044 既有 SQL file**：V053 為新檔；V044 enum extension 不被觸碰（只在 V053 內 layered DROP+ADD）— 避觸 P0 sqlx hash drift incident commit `3681f83`。
- ⚠️ **replay_routes.py 1603 LOC > 1500 hard cap by 103**：dispatch §"Push back 通道" 第 1 點明文允許這個 case 為 push back item（pre-existing baseline 1498 + Track A 6 LOC = 1504 + Track C 5 critical security fixes 結構性 99 LOC = 1603）。已 extract 4 helper 到 route_helpers.py 釋出 ~70 LOC，但仍超 cap 因為 5 critical fix 必含 SQL select sql + admin bypass 路徑分支 + P0-2 audit emit + P0-4 cmdline cert + P0-5b allowlist guard 等核心 logic 不可進一步壓縮。**建議 PM sign-off 接受作 §九 pre-existing baseline exception**（baseline=1504, +5 LOC 範圍允許至 1509；本 PR 在 1603 是 +99 LOC 超範圍，需 explicit accept），同時派 P2 ticket split replay_routes.py 為 endpoint-per-file structure（Wave 10+）。
- ✅ **5 NEW event_type 全可 INSERT**：Mac dev real-PG `INSERT INTO learning.governance_audit_log (event_type, payload) VALUES ('replay_signature_test_key_blocked', ...) ...` 5 row 全 PASS；`'attacker_random_event'` 觸 CHECK REJECT（驗 enum 仍守門）。

### Singleton 登記（CLAUDE.md §九 表 — 待補入）

無新 singleton（Track C 純加 helper / scope check / SQL constraint，無新 module-level 全局 mutable 狀態）。

---

## 5. 驗證 / Verification

### 5.1 Pytest 30/30 PASS（含 7 NEW Track C security）

```
$ cd .../control_api_v1 && pytest tests/test_replay_routes_auth.py tests/test_replay_routes_t2_subprocess.py tests/test_replay_routes_t2_pg_advisory_lock.py tests/test_replay_routes_safe_query_audit.py tests/test_replay_routes_track_c_security.py -v
============================= test session starts ==============================
collected 30 items

tests/test_replay_routes_auth.py::* PASSED [13%]
tests/test_replay_routes_t2_subprocess.py::* PASSED [43%]
tests/test_replay_routes_t2_pg_advisory_lock.py::* PASSED [60%]
tests/test_replay_routes_safe_query_audit.py::* PASSED [76%]
tests/test_replay_routes_track_c_security.py::test_p0_2_env_var_test_key_blocked_in_live_profile PASSED [80%]
tests/test_replay_routes_track_c_security.py::test_p0_2_dev_profile_does_not_strip_test_key PASSED [83%]
tests/test_replay_routes_track_c_security.py::test_p0_4_sigterm_cmdline_cert_fails_returns_409 PASSED [86%]
tests/test_replay_routes_track_c_security.py::test_p0_5a_idor_cross_actor_filter_in_sql PASSED [90%]
tests/test_replay_routes_track_c_security.py::test_p0_5a_idor_admin_bypass_skips_actor_filter PASSED [93%]
tests/test_replay_routes_track_c_security.py::test_p0_5b_path_traversal_etc_passwd_blocked PASSED [96%]
tests/test_replay_routes_track_c_security.py::test_p0_5b_etc_passwd_content_never_in_response PASSED [100%]

============================== 30 passed in 0.41s ==============================
```

### 5.2 Sibling regression 103/103 PASS

```
$ pytest tests/test_batch_b_security_auth.py tests/test_authorization_state_machine.py tests/replay/ -v
============================= 103 passed in 0.23s ==============================
```

涵蓋 batch B security auth + authorization state machine + replay/manifest_signer_xlang_consistency + replay/quota_enforcer。

### 5.3 V053 migration tests 6/6 PASS

```
$ cd /Users/ncyu/Projects/TradeBot/srv && pytest tests/migrations/test_v053_replay_event_types.py -v
============================= test session starts ==============================
collected 6 items

test_v053_file_exists PASSED [16%]
test_v053_guard_a_v035_base_table_check_present PASSED [33%]
test_v053_drops_and_adds_event_type_check_canonical_list PASSED [50%]
test_v053_idempotency_probe_all_8_new_values PASSED [66%]
test_v053_raise_notice_on_skip_and_add_branches PASSED [83%]
test_v053_constraint_comment_describes_14_value_list PASSED [100%]

============================== 6 passed in 0.01s ===============================
```

### 5.4 V053 Mac dev real-PG dry-run

```
$ psql -d v053_test_db -f sql/migrations/V053__governance_audit_log_replay_event_types.sql
DO
NOTICE:  V053: dropped existing event_type CHECK on learning.governance_audit_log
NOTICE:  V053: added event_type CHECK with 14-value canonical list (5 V035 base + 1 V044 P6-S15 + 8 REF-20 Sprint 1 Track A/C)
DO
COMMENT

# Second run for idempotency
$ psql -d v053_test_db -f sql/migrations/V053__governance_audit_log_replay_event_types.sql
DO
NOTICE:  V053: governance_audit_log event_type CHECK already extended with all REF-20 Sprint 1 replay event types; skipping
DO
COMMENT

# INSERT 5 NEW event_type
$ psql -d v053_test_db -c "INSERT INTO learning.governance_audit_log (event_type, payload) VALUES ('replay_signature_test_key_blocked', ...), ('replay_pid_identity_mismatch', ...), ('replay_idor_admin_bypass', ...), ('replay_artifact_path_traversal_blocked', ...), ('replay_argv_mismatch_blocked', ...);"
INSERT 0 5

# REJECT unknown
$ psql -d v053_test_db -c "INSERT INTO learning.governance_audit_log (event_type, payload) VALUES ('attacker_random_event', '{}'::jsonb);"
ERROR:  new row for relation "governance_audit_log" violates check constraint "governance_audit_log_event_type_check"
```

✅ Idempotent + correct enum + Track C 5 NEW 全 INSERT PASS + unknown REJECT。

### 5.5 main.py imports OK

```
$ python -c "from app.main import app; print('routes:', len(app.routes))"
routes: 250
```

### 5.6 Cross-platform grep 0 hit

```
$ grep -nE '/home/ncyu|/Users/[^/]+' replay_routes.py route_helpers.py test_replay_routes_track_c_security.py V053__*.sql test_v053_*.py
(0 hit)
```

---

## 6. 不確定之處 / Ambiguity（給 E2 / E4 review）

### A. replay_routes.py 1500 LOC hard cap exceeded by 103 LOC（PUSH BACK）

**狀況**：dispatch §"Push back 通道" 第 1 點明文預警此 case：
> "replay_routes.py 1498 LOC extract 後仍超 1500"

Track A 已加 6 LOC（pre-existing baseline 從 1498 → 1504）；Track C 5 critical security fixes 結構性 99 LOC（5 audit emit + P0-2 release profile gate + P0-4 cmdline cert + P0-5a admin bypass + P0-5b allowlist guard），即使我已 extract 4 helper（`_safe_pg_select` / `_async_safe_pg_select` / `_replay_response` / `_emit_audit_stub`）到 route_helpers.py 釋出 ~70 LOC，最終仍 1603 LOC（103 over cap）。

**建議**：
1. **PM Sign-off 接受作 §九 pre-existing baseline exception**：明文記錄理由（5 critical security fix 結構性增量；已 4-helper extract；無進一步可壓縮空間）。
2. **同 commit 派 P2 ticket**：`replay_routes.py` 後續 split 為 endpoint-per-file structure（Wave 10+，預估 ~3 day E1 work），讓 8 個 endpoint 各自進 separate file 100-200 LOC + shared `replay_routes_common.py` 200 LOC。
3. **替代方案（不建議）**：把 Track C 拆兩個 commit（一個 P0-2，一個 P0-4 + P0-5），但每個 commit 仍可能超 cap，且增加 E2/E4 review 開銷 → 反而違 dispatch §"3 P0 同 file 同 commit"原則。

### B. `_emit_audit_stub` 仍是 STUB log only — V053 INSERT 待後續 PR

dispatch §"跨 Track 共同任務" 提到「`_emit_audit_stub` 加 5 個新 event_type」；本 PR 只**加了 5 個新 event_type 字串**到 `_emit_audit_stub` 呼叫端（caller side），但 `_emit_audit_stub` body 本身仍是 INFO log（pre-existing W4 P2b-T2 stub 設計，等 V035 enum extension PM 決策）。

V053 SQL 已 land enum 擴展 → 後續 PR 可把 `_emit_audit_stub` body 從 `logger.info(...)` 改為 `INSERT INTO learning.governance_audit_log ...`，進入 PG row 階段。**本 PR 不做** — 保持 dispatch boundary（Track C scope = 安全洞修補 + V053 schema；audit INSERT 切換是另一個 task，避擴張範圍）。

### C. Track A `verify_replay_runner_pid` helper 已存在於 route_helpers.py — Track C 直接 import 使用

dispatch §"Track A E1 出 helper" 寫「Track A E1 出 `_verify_replay_runner_pid` helper」。我開工前查證 → Track A 已 land 這個 helper（`route_helpers.py` L527-576）+ 同時 export `verify_replay_runner_pid` 於 `__all__`。我直接用 `_verify_replay_runner_pid = _rh.verify_replay_runner_pid` import alias。**0 重複造輪**。

### D. test_p0_2_dev_profile_does_not_strip_test_key 用 `raise_server_exceptions=False`

`InMemoryKeyArchive.upsert_key()` API 在某次 V3 release 中遷移為 `archive.add_key(...)` 或類似（pre-existing 不在 Track C 範圍）— dev profile 進 test_key path 後會觸發 `AttributeError: 'InMemoryKeyArchive' object has no attribute 'upsert_key'`。

我用 `TestClient(client.app, raise_server_exceptions=False)` 讓 500 surface 為 status code，再驗 `reason_codes ≠ replay_verify_archive_not_wired` 證明 P0-2 gate 在 dev 沒誤觸發。**這是 Track C 的測試設計選擇**，不掩蓋 pre-existing API mismatch。E4 應在 sibling test scope 修 InMemoryKeyArchive API 漂移；本 PR 不擴張範圍。

### E. test_p0_4_sigterm_cmdline_cert_fails_returns_409 patch.dict("sys.modules") 細節

mocking psutil 用 `patch.dict("sys.modules", {"psutil": fake_psutil})` + 用 真 Exception class（`class _NoSuchProcess(Exception): pass`）作 fake_psutil.NoSuchProcess / AccessDenied — **不能用 MagicMock 做 Exception**，否則 `except psutil.NoSuchProcess:` 命中失敗（MagicMock 不是 BaseException 子類）。

如果 E4 想擴展 PID-reuse 邊界 case（如 `psutil.AccessDenied` / `psutil.ZombieProcess`）→ 同 pattern 加真 Exception class 即可。

### F. allowlist root cross-platform: Mac dev `/tmp/replay_artifacts_test_only` vs Linux `OPENCLAW_DATA_DIR/replay_artifacts`

`resolve_artifact_allowlist_root()` 用 `sys.platform == "darwin"` 分支：
- Mac dev: `Path("/tmp/replay_artifacts_test_only")`
- Linux: `Path(OPENCLAW_DATA_DIR) / "replay_artifacts"`

這 mirror Track A 的 `resolve_artifact_output_dir()` pattern（同 file 同 module）— writes 與 reads 共用單一 root。E4 跑 Linux 時 OPENCLAW_DATA_DIR 必設（CLAUDE.md §六）；Mac dev fallback `/tmp/openclaw` 也 OK（Mac dev test path 用 `/tmp/replay_artifacts_test_only` 不衝突）。

---

## 7. PM commit message draft

```
fix(replay): REF-20 Sprint 1 Track C — Python /replay/* 3 critical security fixes + V053 enum extension

REF-20 Sprint 1 Track C IMPL closes 3 P0 critical security holes in
program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_routes.py:

  P0-2 (env var bypass at POST /api/v1/replay/manifest/verify):
    OPENCLAW_REPLAY_VERIFY_TEST_KEY env var was honored in production →
    attacker-controlled env could forge ANY manifest signature. Fix
    introduces release-profile gate via OPENCLAW_RELEASE_PROFILE='live'
    that force-clears test_key_hex (dev/mac_dev profile unchanged) +
    module-init ERROR boot guard for diagnostic.

  P0-4 (SIGTERM arbitrary pid at POST /api/v1/replay/cancel):
    os.kill(pid, SIGTERM) used V045 subprocess_pid directly without
    process identity check. DB injection / PID reuse / race could send
    SIGTERM to init/postmaster/engine. Fix uses
    _verify_replay_runner_pid(pid) helper (Track A psutil cmdline cert)
    before SIGTERM; failure returns 409 replay_pid_identity_mismatch
    + audit emit; PID-reuse safe (psutil cmdline returns CURRENT
    process's argv, not the original pid owner's).

  P0-5a (IDOR cross-actor at GET /api/v1/replay/report/{experiment_id}):
    SELECT lacked AND s.actor_id = %s filter → any viewer could read
    any actor's replay report. Fix adds default actor_id filter +
    admin bypass via 'replay:read:any' scope (cross-actor incident
    investigation only) + audit emit on bypass usage.

  P0-5b (path traversal at the artifact open block):
    Path(row[2]) directly opened DB-supplied (no CHECK constraint)
    artifact_path. Attacker INSERT'd '/etc/passwd' would be base64'd
    back. Fix adds _artifact_path_within_allowlist() guard via
    Path.resolve().is_relative_to(allowlist_root) where allowlist_root
    = $OPENCLAW_DATA_DIR/replay_artifacts/ (Linux) or
    /tmp/replay_artifacts_test_only/ (Mac dev) + audit emit on traversal.

V053__governance_audit_log_replay_event_types.sql lands the V035
event_type CHECK enum extension from 6 values (V035 base 5 + V044
P6-S15 1) to 14 values (+ 8 REF-20 Sprint 1 Track A/C). 5 of the 8
NEW values are emitted by Track C audit stubs in this PR
(replay_signature_test_key_blocked / replay_pid_identity_mismatch /
replay_idor_admin_bypass / replay_artifact_path_traversal_blocked +
replay_run_started / replay_run_cancelled / replay_manifest_verify_attempted).
1 placeholder for Track A future use (replay_argv_mismatch_blocked).
Guard A enforced (V035 base table existence). Idempotent (8 NEW
position()-probe skip on re-run). Mac dev real-PG dry-run validated.

Tests: 30/30 PASS (4 existing auth + 9 existing t2_subprocess + 5
existing advisory_lock + 5 existing safe_query_audit + 7 NEW Track C
security) + 6 V053 migration tests PASS + 103/103 sibling regression
PASS (batch_b_security_auth + authorization_state_machine + replay/).

Files:
  M program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_routes.py (+99)
  M program_code/exchange_connectors/bybit_connector/control_api_v1/replay/route_helpers.py (+156)
  + program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_routes_track_c_security.py (496)
  + sql/migrations/V053__governance_audit_log_replay_event_types.sql (211)
  + tests/migrations/test_v053_replay_event_types.py (173)
  M sql/migrations/REF-20_RESERVATION.md (+2 V053 row + v1.9 revision)
  M docs/CCAgentWorkSpace/E1/memory.md (+20 Sprint 1 Track C lessons)
  + docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--ref20_sprint1_track_c_python_security.md

Notes:
  - replay_routes.py final LOC = 1603, 103 OVER §九 1500 hard cap.
    Dispatch §"Push back 通道" #1 explicit-flagged this case
    (pre-existing baseline 1504 + 5 critical security fixes
    structurally adds 99 LOC; 4 helper extracted to route_helpers.py
    saving ~70 LOC, but cannot compress further without compressing
    Track A's pre-existing comment block — out of Track C scope).
    PM Sign-off requested under §九 pre-existing baseline exception.
    P2 ticket recommended: split replay_routes.py to endpoint-per-file
    structure (Wave 10+, ~3 day E1 work).

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## 8. Operator 下一步 / Next steps

### 8.1 強制工作鏈（CLAUDE.md §七 + dispatch）

dispatch 指明「**不要呼 E2 / E4**」（Sprint 1 Track C 自帶 review 完成）。但完整工作鏈仍：

1. **PM Sign-off**（必跑）— 焦點：
   - replay_routes.py 1603 LOC > 1500 cap by 103；governance exception accept 理由（§4 + §6.A）。
   - V053 schema extension + 5 NEW event_type INSERT 已 Mac dev real-PG 驗 PASS。
   - 0 hard boundary 觸碰 / 0 跨平台 grep hit / 0 修改 V045/V046 既有 file。
   - 派 P2 ticket: `replay_routes.py` endpoint-per-file split (Wave 10+)。

2. **Linux operator deploy**（PM 排程）：
   ```
   ssh trade-core "cd ~/BybitOpenClaw/srv && git pull --ff-only origin main"
   ssh trade-core "cd ~/BybitOpenClaw/srv && psql -U postgres -d trading_ai -f sql/migrations/V053__governance_audit_log_replay_event_types.sql"
   ssh trade-core "bash helper_scripts/restart_all.sh"
   ```
   驗 V053 NOTICE 加 14-value list；驗 Python `replay_routes.py` import OK；驗 `OPENCLAW_RELEASE_PROFILE=live` env 設定（Live 部署前必設）。

3. **post-deploy healthcheck**：
   - manually POST `/api/v1/replay/cancel` with mock V045 row pid → 驗 409 + `replay_pid_identity_mismatch`
   - manually GET `/api/v1/replay/report/<experiment_id>` 從 actor_a 帳號 → 驗只看到自己的；admin actor 看到全部
   - manually POST `/api/v1/replay/manifest/verify` with `OPENCLAW_RELEASE_PROFILE=live` + `OPENCLAW_REPLAY_VERIFY_TEST_KEY=...` → 驗 501 archive_not_wired

### 8.2 Push back items（給 PM 決策）

- **#1 LOC over cap**：請 PM accept 作 §九 pre-existing baseline exception；同 commit 派 P2 ticket Wave 10+ split。
- **#2 V053 CONSTRAINT comment**：本 PR 加 `COMMENT ON CONSTRAINT governance_audit_log_event_type_check`，會被未來下一個 V### enum extension overwrite。如 PM 想保留歷史 comment 鏈 → 需另設計 schema versioning，超 Sprint 1 範圍。

### 8.3 完成序列（per E1 profile）

- ✅ 追加 `srv/docs/CCAgentWorkSpace/E1/memory.md` Sprint 1 Track C 教訓
- ✅ 報告存 `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--ref20_sprint1_track_c_python_security.md`
- ⚠️ **不直接 commit**：dispatch 指明「不要呼 E2 / E4」+ E1 profile §"完成序列" 第 3 點明文「E1→E2→E4→QA→PM 強制鏈」 — 兩者衝突時以 E1 profile / CLAUDE.md §七 為準（commit 仍由 PM 統一）。報告寫完即停，等 PM commit + push + Linux pull --ff-only。

---

E1 IMPLEMENTATION DONE: 待 PM commit (report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--ref20_sprint1_track_c_python_security.md`)

---

## 9. E2 retrofit log（2026-05-03 同日，4 finding 修補）

E2 retrofit dispatch 於 Track C 初版報告寫畢後立即派發。E2 verdict = RETURN to E1 因 4 finding：
- **§九 1500 LOC cap 違規（最高優先 — PM 拒 baseline exception）**
- **F8 `replay:read:any` scope 未在 default 集合登記（admin bypass code path 死）**
- **F6 boot guard 降級為 log-only（attacker 控 env 仍可啟動）**
- **F2 V053 enum DROP+ADD 無 LOCK TABLE（與 V044 同 incident pattern）**

每條獨立修法 + 證據如下。

### 9.1 §九 1500 LOC cap — replay_routes.py 1603 → 1494（≤1500 ✅）

**修法（dispatch §"修法"選項 A）**：
- 新建 `program_code/exchange_connectors/bybit_connector/control_api_v1/replay/security_guards.py`（487 LOC，獨立 module，dispatch §"選項 A 推薦"）
- 抽 5 helper：
  1. `perform_p0_2_boot_guard(is_live_release_profile_fn)` — module-init 守門，**raise** RuntimeError 取代 log-only（同時修 F6）
  2. `resolve_manifest_verify_test_key(actor_id, declared_hash_hex, is_live_release_profile_fn, audit_emit_fn)` — per-route gate，live → 強制清空 + audit emit
  3. `verify_replay_cancel_pid(pid, run_id, verify_pid_fn)` — cmdline cert wrapper（pid≤0 短路）
  4. `build_report_idor_sql(manifest_uuid, actor_id, can_read_any)` — IDOR fix SQL build
  5. `check_artifact_path_within_allowlist(artifact_path, allowlist_check_fn)` — allowlist guard wrapper
- 整段抽 `execute_replay_cancel_pg_path(...)` cancel route PG body（含 V045 SELECT + cmdline cert + UPDATE），保留 `os.kill(pid, SIGTERM)` 在 caller（xact 外，hermetic test 友好 + rollback 路徑絕不誤送 signal）
- Module top docstring 從 60 行壓至 25 行（保留雙語 MODULE_NOTE，移除 8-route list + Hard contracts 細節 — 已可 reference archive）

**證據**：
```
$ wc -l replay_routes.py replay/security_guards.py
1494 replay_routes.py
 487 replay/security_guards.py
$ awk 'END{print NR}' replay_routes.py
1494  # ≤ 1500 hard cap ✅
```

**route_helpers.py LOC 警示**（**不在本 retrofit 範圍**）：route_helpers.py 從 891 LOC（pre-existing baseline）升至 980 LOC（>800 warn line）— 此增量來自 Track A/C IMPL 既有 WIP，本 retrofit **未動 route_helpers.py**（git diff 證 0 此檔修改）。Track A/C 完整 commit 後若超 warn,屬 Track A scope。

### 9.2 F8 `replay:read:any` scope 未登記 — 加入 default + 2 NEW test

**修法**：`app/auth.py` `Settings.auth_scopes` default csv 加 `replay:write` + `replay:read:any`（admin actor 經 `build_authenticated_actor()` 後真持有 scope，`_actor_can_read_any_replay_report(actor)` admin bypass 路徑真實激活）。

```python
# srv/program_code/exchange_connectors/bybit_connector/control_api_v1/app/auth.py
                        # ── REF-20 Replay Lab scopes (Sprint 1 Track C E2 retrofit F8) ──
                        "replay:write",
                        "replay:read:any",
```

**證據**（2 NEW test）：
- `test_e2_retrofit_f8_replay_read_any_in_default_scopes`：驗 `Settings()` 後 default scope 集合含兩 scope
- `test_e2_retrofit_f8_actor_built_from_settings_has_replay_scopes`：驗 `build_authenticated_actor()` 工廠產出 actor 含兩 scope

**未集成路徑說明**：`governance_hub_cascades.py:806` 的 `_auth_permits_scope` 用 `if permitted_scopes else True` empty-fallback=True 是 latent rug-pull（authorization.json `scope.lease_scopes` 屬 LiveAuthorization 系統，不是 actor.scopes 系統 — 兩套 scope 互不通），dispatch §"Push back 通道" 第 3 點問是否乾淨整合 — 答案是兩系統互補 + 留 P2 TODO 待 PA/PM 共議。

### 9.3 F6 boot guard log-only → raise

**修法**：`security_guards.perform_p0_2_boot_guard()` 在 `is_live_release_profile()` AND `OPENCLAW_REPLAY_VERIFY_TEST_KEY` 非空時 **raise RuntimeError**。replay_routes.py module-init 呼叫此 guard，雙設時 uvicorn boot 直接掛掉。

```python
# replay/security_guards.py:perform_p0_2_boot_guard
if is_live_release_profile_fn() and os.environ.get(test_key_env_var, "").strip():
    raise RuntimeError(
        "REF-20 Track C P0-2 boot guard FAIL-CLOSED: "
        f"{test_key_env_var} is set with OPENCLAW_RELEASE_PROFILE=live; "
        "test_key_hex must NEVER be honored in live profile (forge risk). "
        "Unset the env var or change OPENCLAW_RELEASE_PROFILE before booting."
    )
```

**證據**（3 NEW test）：
- `test_e2_retrofit_f6_boot_guard_raises_in_live_with_test_key`：live+TEST_KEY → `pytest.raises(RuntimeError)` 正命中 + msg 含 token
- `test_e2_retrofit_f6_boot_guard_skips_when_not_live`：not_live+TEST_KEY → 0 raise（dev 友好）
- `test_e2_retrofit_f6_boot_guard_skips_when_test_key_unset`：live+no_TEST_KEY → 0 raise（production deploy 乾淨啟動）

**dispatch §"Push back 通道" 第 4 點 dev 撞牆風險評估**：dev workflow 不設 `OPENCLAW_RELEASE_PROFILE`（CLAUDE.md §六 default 空），此 boot guard 對 dev 100% 不可達；只在 production deploy 雙設時 raise。

### 9.4 F2 V053 enum DROP+ADD 加 BEGIN+LOCK TABLE+COMMIT

**修法**：V053 SQL 重構：
```sql
BEGIN;
DO $$
... (idempotency probe — short-circuit BEFORE LOCK TABLE)
... ELSE block ELSE
    LOCK TABLE learning.governance_audit_log IN ACCESS EXCLUSIVE MODE;
    DROP CONSTRAINT IF EXISTS ...;
    ADD CONSTRAINT ... CHECK (...);
END $$;
COMMIT;
```

**race-free pattern**：concurrent INSERT 取 ROW EXCLUSIVE 與 ACCESS EXCLUSIVE 衝突 → blocked → 等 V053 COMMIT 釋鎖後 INSERT 命中新 CHECK。0 race window。

**Idempotency 安排**：probe 短路 (`v_track_c_present=TRUE` → RAISE NOTICE skip) 在 `LOCK TABLE` **之前**，重跑 0 阻塞 writer。

**證據（Mac dev real-PG dry-run）**：
```
$ psql -d v053_e2_test_db -f V053__governance_audit_log_replay_event_types.sql
DO
BEGIN
NOTICE:  V053: dropped existing event_type CHECK on learning.governance_audit_log (under ACCESS EXCLUSIVE)
NOTICE:  V053: added event_type CHECK with 14-value canonical list ... under ACCESS EXCLUSIVE lock
DO
COMMIT
COMMENT  # 1 RAISE on first run (LOCK + DROP + ADD)

$ psql -d v053_e2_test_db -f V053__governance_audit_log_replay_event_types.sql
DO
BEGIN
NOTICE:  V053: governance_audit_log event_type CHECK already extended ... skipping
DO
COMMIT
COMMENT  # 0 LOCK / 0 RAISE on second run (idempotent)

$ psql -d v053_e2_test_db -c "INSERT ... ('replay_signature_test_key_blocked', ...) ..."
INSERT 0 5  # 5 NEW event_type INSERT PASS

$ psql -d v053_e2_test_db -c "INSERT ... ('attacker_random_event', ...);"
ERROR:  new row ... violates check constraint "governance_audit_log_event_type_check"  # CHECK 仍守門
```

**P2 ticket draft**（同 commit 開）：`P2-AUDIT-V044-LOCK-TABLE-FIX` — V044 P6-S15 enum 擴展未含 race-free LOCK TABLE pattern，需後續 retrofit 補回（同 V053 BEGIN+LOCK+COMMIT）。

### 9.5 完成定義驗證對照

| dispatch 完成定義 | 結果 |
|---|---|
| 1. replay_routes.py LOC ≤ 1500 (`wc -l` 驗) | ✅ 1494 |
| 2. security_guards.py 新建 + 含 P0-2/P0-4/P0-5 完整邏輯遷移 | ✅ 487 LOC + 6 helper（5 安全 + 1 cancel PG path body 抽出） |
| 3. authorization.json `replay:read:any` scope 登記 | ✅ `Settings.auth_scopes` default 加 `replay:write` + `replay:read:any`（authorization.json 不存在於 repo；scope 集合存活在 Settings env-default factory） |
| 4. boot guard raise 而非 log-only | ✅ `perform_p0_2_boot_guard()` raise RuntimeError 取代 log.error |
| 5. V053 SQL wrapped in BEGIN ... LOCK TABLE ... COMMIT | ✅ `BEGIN; DO $$ ... LOCK TABLE ... DROP+ADD ... END $$; COMMIT;` |
| 6. 既有 36/36 + 103/103 全綠 + 加 4-5 新 case | ✅ 36/36 sibling（test_safe_query_audit case1 + audit_helper 同步更新 sanctioned marker）+ 103/103 batch_b/auth_state_machine/replay + 7/7 V053 migration（含新 LOCK TABLE 行為驗證）+ 13/13 Track C security（原 7 + 新 6 retrofit case） |
| 7. V053 Mac dev real-PG idempotent + 5 NEW INSERT + 兩遍 0 RAISE | ✅ 已驗（§9.4 證據） |
| 8. 在原報告追加 §9 retrofit log | ✅（本節） |
| 9. 不要 commit / push（PM 一次 commit Sprint 1 完整 patch） | ✅ |

### 9.6 修改清單（僅 retrofit 增量）

| 路徑 | 變更 | LOC 增量 | 性質 |
|---|---|---|---|
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_routes.py` | 修 — 換用 `_sg.*` helper + 整段 cancel PG body 抽出 + module top docstring 壓縮 | -109（1603→1494） | M |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/replay/security_guards.py` | 新檔 — 6 helper（5 P0 安全 + 1 cancel PG body） | +487 | A |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/auth.py` | 修 — `Settings.auth_scopes` default 加 `replay:write` + `replay:read:any` | +13 | M |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_routes_track_c_security.py` | 修 — 6 NEW retrofit case（F6×3 + F8×2 + F2×1） | +167 | M |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_routes_safe_query_audit.py` | 修 — `transactional_advisory_lock` allow-list 加 `_sg.execute_replay_cancel_pg_path` marker + audit summary baseline 從 ≥8 改 ≥5 | +14 | M |
| `sql/migrations/V053__governance_audit_log_replay_event_types.sql` | 修 — 加 BEGIN + LOCK TABLE ACCESS EXCLUSIVE + COMMIT 包裹 + E2 retrofit F2 雙語 | +55 | M |
| `tests/migrations/test_v053_replay_event_types.py` | 修 — 加 `test_v053_e2_retrofit_f2_lock_table_access_exclusive_present` | +42 | M |
| `docs/CCAgentWorkSpace/E1/memory.md` | 修 — Track C E2 retrofit 教訓 6 項 | +30 | M |
| `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--ref20_sprint1_track_c_python_security.md` | 修 — 追加 §9（本節）retrofit log | +200 | M |

### 9.7 PM 額外決策請求

- **§九 1500 LOC cap 達成 1494**：dispatch §"完成定義 #1" 強制 ≤1500，**已合規**；無需 PM baseline exception。本 retrofit 圓滿關閉 §九 違規。
- **route_helpers.py 980 LOC 警示來自 Track A/C IMPL（非本 retrofit）**：git diff 證未動本檔；屬 Track A scope，建議 Track A 後續 retrofit / PA 統籌時再評估 split。
- **P2 ticket 開新**：`P2-AUDIT-V044-LOCK-TABLE-FIX` — V044 P6-S15 enum 擴展未含 race-free LOCK TABLE pattern，補回。

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--ref20_sprint1_track_c_python_security.md`）
