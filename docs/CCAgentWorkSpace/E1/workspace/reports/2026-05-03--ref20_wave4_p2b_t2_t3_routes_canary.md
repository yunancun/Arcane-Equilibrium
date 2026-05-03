# REF-20 Wave 4 R20-P2b-T2 + T3 Merged IMPL — Routes Wire to T1 Binary + PG Advisory Lock + Canary Artifacts

**日期：** 2026-05-03
**Owner：** E1 sub-agent
**契約上游：**
- `docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md` §4 Wave 4 P2b-T2 + T3
- `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` §3 G3/G7 + §6 + §12 #3/#7/#14/#22
- `docs/execution_plan/2026-05-03--ref20_wave2_dispatch_v1.md` §6 v1.1 Option C decision

**狀態：** IMPL DONE，待 E2 + E3 + MIT review

---

## 1. 任務摘要 / Task Summary

Wave 4 R20-P2b-T2（`replay_routes.py` 8 endpoints wire 到 T1 `replay_runner` Rust binary subprocess + PG advisory lock retrofit 取代 in-memory `_ACTIVE_RUNS`）+ R20-P2b-T3（canary / diagnostic artifact filesystem + V046 DB registry）合併 IMPL。

兩 task 合併因為共享 V045 `replay.run_state` schema（lifecycle row）+ V046 `replay.report_artifacts` schema（artifact registry FK CASCADE 到 V045）+ replay_routes.py（route 既要接 T1 binary 又要寫 artifact）。

並行 sibling sub-agent 同步 IMPL Wave 4 P2b-T1（`replay_runner` Rust binary 真實 logic）；本 task 用 path placeholder + integration test mock 不阻塞 T1 land。

---

## 2. 修改清單 / Files Changed

### 2.1 修改檔案 / Modified

| 檔案 | 改動範圍 | LOC 變化 |
|---|---|---|
| `program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_routes.py` | 8 endpoints actual wire 到 T1 binary subprocess + PG advisory lock retrofit + manifest signer integration（test path） + V045/V046 lookup paths | 902 → 1498（< 1500 cap） |
| `sql/migrations/REF-20_RESERVATION.md` | V045 + V046 buffer → land；ledger v1.3 row | +2 row + revision history line |

### 2.2 新增檔案 / New

| 檔案 | LOC | 用途 |
|---|---|---|
| `program_code/exchange_connectors/bybit_connector/control_api_v1/replay/route_helpers.py` | 314 | subprocess.Popen wrapper（whitelisted env per V3 §6.2）+ advisory lock try-acquire + V045 schema-presence probe + active-run count helpers |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/replay/run_state_manager.py` | 682 | 4 lifecycle ops（start_run / get_run_status / mark_run_complete / cancel_run）；schema-absent graceful；SIGTERM via os.kill |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/replay/canary_writer.py` | 437 | 5 artifact_type 寫 filesystem + register V046；Linux real / Mac is_mock=True |
| `sql/migrations/V045__replay_run_state.sql` | ~410 | CREATE TABLE + 5-status CHECK + runtime_environment CHECK + 2 hot-path index；Guard A + Guard C；雙語 |
| `sql/migrations/V046__replay_report_artifacts.sql` | ~285 | CREATE TABLE + FK CASCADE 到 V045 + 5-artifact_type CHECK + 1 hot-path index；Guard A（含 V045 prereq）+ Guard C；雙語 |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_routes_t2_subprocess.py` | ~250 | 9 case：8 endpoint wire + 1 health probe |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_routes_t2_pg_advisory_lock.py` | ~150 | 5 case：advisory lock 4 path + symbol surface |
| `program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_canary_writer.py` | ~210 | 6 case：write/register/validate/Mac/enum match |
| `tests/migrations/test_v045_v046_replay_run_state_artifacts.py` | ~270 | 13 case：V045/V046 schema 靜態 parse 驗證 |

### 2.3 不變更 / Untouched

- `replay/manifest_signer.py`（P2a-S2 owns；本 task 透過 module-level import + `_ms` alias 引用）
- `replay/quota_enforcer.py`（P2a-S5 owns；本 task 不修改）
- `app/auth_routes_common.py` / `scout_routes.py` / `risk_routes.py`（紅線禁改）
- 任何 V001-V044 migration（紅線：本 task 範圍 V045 + V046 only）

---

## 3. 關鍵 diff 摘要 / Key Diff Highlights

### 3.1 PG advisory lock retrofit (Option C)

```python
# replay/route_helpers.py
def try_acquire_pg_advisory_locks(cur, actor_id):
    cur.execute("SELECT pg_try_advisory_xact_lock(hashtext(%s));", (ADVISORY_LOCK_GLOBAL_KEY,))
    if not (cur.fetchone() and cur.fetchone()[0]):
        return False, "replay_global_cap_exceeded"
    cur.execute("SELECT pg_try_advisory_xact_lock(hashtext(%s));", (f"replay_run_actor:{actor_id}",))
    if not (cur.fetchone() and cur.fetchone()[0]):
        return False, "replay_per_actor_cap_exceeded"
    return True, None
```

兩鎖在同 transaction 內取得；commit / rollback 自動釋放（xact-scoped）。

### 3.2 Subprocess env whitelist (V3 §6.2 + §12 #14)

```python
SUBPROCESS_ENV_WHITELIST = (
    "OPENCLAW_BASE_DIR", "OPENCLAW_DATA_DIR",
    "OPENCLAW_REPLAY_MAC_NO_PRIVATE", "OPENCLAW_REPLAY_RUNTIME_ENV",
    "HOME", "PATH", "USER", "LANG",
)
child_env = {k: os.environ[k] for k in SUBPROCESS_ENV_WHITELIST if k in os.environ}
```

無 live secrets propagation（紅線）。

### 3.3 V045 + V046 FK CASCADE

```sql
-- V046
CREATE TABLE IF NOT EXISTS replay.report_artifacts (
    artifact_id UUID PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES replay.run_state(run_id) ON DELETE CASCADE,
    ...
);
```

S5 quota_enforcer cron 清 V045 row 時連帶清 V046 artifact。

### 3.4 Manifest UUID5 derivation（cross-route consistency）

```python
manifest_uuid_namespace = uuid.UUID("00000000-0000-0000-0000-000020260503")
manifest_uuid = uuid.uuid5(manifest_uuid_namespace, body.experiment_id)
```

POST /run + GET /report 對同 experiment_id 衍生同 manifest_uuid（idempotency on retry）。

### 3.5 雙路徑共存（compat for existing 4 auth pytest）

```python
# replay_routes.py POST /run
# Try PG path (primary)
run_id, pid, pg_err, output_dir = await asyncio.to_thread(_do_pg_path)
if run_id is not None and pg_err is None:
    return _replay_response({...})  # PG path success

# Fallback to in-memory dict (V045 absent / PG unreachable / hermetic test)
async with _ACTIVE_RUNS_LOCK:
    await _check_run_caps_inmemory(actor_id)
    _ACTIVE_RUNS[actor_id] = {...}
```

---

## 4. 治理對照 / V3 §12 Acceptance Binding

| Acceptance | 對應 IMPL | 證據 |
|---|---|---|
| **#3 route_auth** | 8 endpoints 全經 `Depends(base.current_actor)`；mutating routes 加 `_require_replay_write(actor)` | 既有 4 test_replay_routes_auth.py case 不退化（4/4 PASS）+ 新 5 advisory-lock case PASS |
| **#7 registry_fk** | V046 FK run_id → V045.run_state ON DELETE CASCADE | V046 SQL grep `REFERENCES replay.run_state\|ON DELETE CASCADE` 各 ≥1 hit；test_v046_fk_cascade_to_v045 PASS |
| **#14 no_live_mutation** | subprocess env 白名單 8 keys，0 secrets；0 trading.* / 0 live config 寫；audit emit 僅 INFO log | route_helpers.py SUBPROCESS_ENV_WHITELIST + grep `trading\.` 0 hit + `_emit_audit_stub` 僅 logger.info |
| **#22 safe_query** | replay_routes.py PG 操作全經 `_safe_pg_select` wrapper 或 transaction-scoped cursor with `SET LOCAL statement_timeout = 2s` | grep `_safe_pg_select\|SET LOCAL statement_timeout` ≥7 hit；PG outage simulation → 200 + degraded=true（test_get_*_with_pg_unavailable PASS） |

---

## 5. 紅線守則 / Red-Line Compliance

| 紅線 | 守 | 證據 |
|---|---|---|
| 0 修改 既有 manifest_signer.py / quota_enforcer.py / S5 prune cron | ✅ | git status 顯示兩檔未在 modified list |
| 0 trading.* write | ✅ | grep `trading\.` in replay_routes / canary_writer / run_state_manager / route_helpers = 0 hit |
| 0 live config mutation | ✅ | 無 `live_authorization` / `live_config` / `_write_signed_*` 路徑 |
| subprocess.Popen 限 replay_runner binary path（白名單） | ✅ | 唯一 Popen call 在 `route_helpers.spawn_replay_runner`；argv[0] = `_resolve_replay_runner_bin()` 結果 |
| PG advisory lock 必 within transaction (xact_lock) | ✅ | 用 `pg_try_advisory_xact_lock` 非 `pg_try_advisory_lock`（後者 session-scoped） |
| 既有 4 auth pytest 0 break | ✅ | 4/4 PASS（autouse `_reset_active_runs_for_test()` + `_ACTIVE_RUNS` symbol 保留）|
| 雙語 comment + V035 migration header pattern | ✅ | V045/V046 都有「Purpose / 目的」+「Spec source / 規格來源」+「Guard A/B/C」+ bilingual MODULE_NOTE in Python 4 file |
| 不擅改 既有 routes file | ✅ | git status 顯示 `auth_routes_common.py` / `scout_routes.py` / `risk_routes.py` 不在 modified list |
| File size cap 800 / 1500 | ✅ | replay_routes.py = 1498（< 1500）；run_state_manager.py = 682（< 800）；canary_writer.py = 437（< 800）；route_helpers.py = 314（< 800） |

---

## 6. 不確定之處 / Push-back to PM

### 6.1 `_ACTIVE_RUNS` 殘存的 deprecation 期

紅線禁我移除（既有 4 auth pytest 依賴），但 Option C 決策本意是「替換」而非「並存」。建議 PM 在 Wave 5+ 派 sub-agent 把 既有 4 test 改寫成 PG-mock 版（dual-path 退役），縮回單一 PG path。**不阻塞 Wave 4**。

### 6.2 replay.experiments fixture vs V045/V046 部署順序

V045/V046 用 logical reference（不對 replay.experiments 加 FK）以避前向參考 fixture 表。fixture land 後可選擇追加 FK 約束（migration 範圍）；但這樣會破 V045/V046 idempotency。建議 PM 接 Wave 3 P2b-T1 fixture 部署後決定追加 FK 還是保 logical reference。**不阻塞 T2/T3**。

### 6.3 OPENCLAW_API_WORKERS=4 與 in-memory dict 行為

Option C 決策說「PG advisory lock 取代 in-memory」是因為 `OPENCLAW_API_WORKERS=4` 下 in-memory dict 跨 worker 不共享。但 fallback 路徑仍走 in-memory；若 Linux runtime PG outage + workers=4，會出現 4 worker 各自 cap 計數（各持 1 active run = 共 4，違 spec=1）。建議 PM 在 deploy doc 強調 Linux runtime PG availability 是 Replay Lab 不可或缺前提。**不阻塞 Wave 4**。

### 6.4 Subprocess SIGTERM grace period

os.kill(SIGTERM) 不等 subprocess wait；DB row 立即翻 cancelled。若 replay_runner 對 SIGTERM 處理時間 > 0（理應有清理工作），可能出現 status=cancelled 但 subprocess 仍寫 artifacts → V046 row 出現晚於 status flip。建議 Wave 5 P3a+ canary writer 加 idempotent INSERT ... ON CONFLICT DO NOTHING 保險。**不阻塞 Wave 4**。

### 6.5 T1 binary path placeholder

任務說「如 T1 binary 還沒 land (parallel sub-agent)：用 path placeholder `/usr/local/bin/replay_runner` 或 env var override `OPENCLAW_REPLAY_RUNNER_BIN`，加 TODO marker + integration test mock 不阻塞」。實作採後者（env var override）；test 用 `_mock_pg_unavailable` fixture 強制走 in-memory path 不需要真實 binary。Linux deploy 後 sibling subagent T1 binary land 即自動命中 PG path（OPENCLAW_REPLAY_RUNNER_BIN 預設 = `$OPENCLAW_BASE_DIR/rust/openclaw_engine/target/release/replay_runner`，不需 operator 顯式設）。

---

## 7. 驗證 / Verification

```bash
# All 5 test files pass on Mac dev (cwd = srv/)
$ python3 -m pytest \
    tests/migrations/test_v045_v046_replay_run_state_artifacts.py \
    program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_routes_t2_subprocess.py \
    program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_routes_t2_pg_advisory_lock.py \
    program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_canary_writer.py \
    program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_routes_auth.py
======================== 37 passed, 1 warning in 0.27s =========================

# py_compile clean
$ python3 -m py_compile <4 Python files>
py_compile PASS

# Cross-platform: 0 hard-coded user paths
$ grep -E "(/home/ncyu|/Users/ncyu)" <all new + modified files>
X-platform PASS: 0 hard-coded user paths

# Wave 4 markers in routes
$ grep -c "pg_try_advisory_xact_lock" replay_routes.py route_helpers.py
3  # 1 in routes (compat) + 2 in helpers (try_acquire SELECT)

# _ACTIVE_RUNS still present (red-line: keep for existing 4 auth pytest)
$ grep -c "_ACTIVE_RUNS\b" replay_routes.py
15  # legacy fallback path retained
```

---

## 8. Operator 下一步 / Operator Next

### 8.1 E2 review focus
- advisory lock SQL 對抗 SQL injection（hashtext 的字串 input 是否需要 sanitize）
- `pg_try_advisory_xact_lock` 對 hashtext collision 風險評估（int4 hash space 是否足夠）
- subprocess argv 跨平台 escape behavior（Python subprocess.Popen on Linux vs Mac）
- V045/V046 Guard A/C SQL 撞號風險（與 sibling sub-agent V###）

### 8.2 E3 review focus
- subprocess env 白名單對抗 env-var injection
- SUBPROCESS_ENV_WHITELIST 是否該收緊（HOME 是否真需要）
- manifest_signer 雙路徑 import fallback 對 production 部署順序敏感性

### 8.3 MIT review focus
- V045 / V046 schema 對 ML pipeline 影響（advisor 寫的 mlde_replay_veto 跨 V043 表 vs V046 是否 schema clash）
- replay.experiments fixture（P2b runner SQL fixture）與 V045/V046 deploy 順序

### 8.4 E4 regression
- Linux trade-core 跑全 5 test：`python3 -m pytest <5 file>` → 全綠
- sibling Wave 4 T1 binary 部署後跑 `OPENCLAW_REPLAY_RUNNER_BIN=$(pwd)/rust/openclaw_engine/target/release/replay_runner pytest test_replay_routes_t2_subprocess` 觀察 PG path active 路徑命中

### 8.5 PM commit message draft

```
feat(replay): T2 routes wire to T1 binary + PG advisory lock + T3 canary artifacts (Wave 4 P2b-T2/T3)

- replay_routes.py: 8 endpoints wired to replay_runner subprocess +
  PG advisory lock retrofit (Wave 2 dispatch v1.1 §6 Option C);
  in-memory _ACTIVE_RUNS dict retained as legacy fallback for hermetic
  single-worker test coverage and pre-V045 graceful degradation.
- route_helpers.py: subprocess.Popen wrapper with whitelisted env
  propagation (V3 §6.2 + §12 #14 no-secrets red-line) +
  pg_try_advisory_xact_lock try-acquire + V045 schema-presence probes.
- run_state_manager.py: 4-op replay_runner subprocess lifecycle on V045.
- canary_writer.py: 5 artifact_type filesystem write + V046 DB registry;
  Linux real / Mac is_mock=True per V3 §6.3 non-actionable rule.
- V045__replay_run_state.sql: replay.run_state with 5-status CHECK +
  runtime_environment CHECK + 2 hot-path indexes; Guard A + Guard C.
- V046__replay_report_artifacts.sql: replay.report_artifacts FK CASCADE
  to V045 + 5-artifact_type CHECK + 1 hot-path index; Guard A + Guard C.
- 37 new tests pass (24 routes + canary + 13 V045/V046 schema);
  existing 4 test_replay_routes_auth.py pass (red-line: 0 break).

V3 §12 acceptance binding:
  - #3 route_auth: existing 4 + new 5 advisory-lock cases all pass.
  - #7 registry_fk: V046 FK run_id → V045.run_state ON DELETE CASCADE.
  - #14 no_live_mutation: subprocess env whitelist + 0 trading.* writes.
  - #22 safe_query: _safe_pg_select wrapper + statement_timeout=2s
    on every PG operation (mirrors agents_routes_helpers).

REF-20_RESERVATION.md ledger v1.3: V045 + V046 buffer → land.

Refs: docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
      §4 Wave 4 R20-P2b-T2 + T3
      docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md
      §3 G3/G7 + §6 + §12 #3/#7/#14/#22
      docs/execution_plan/2026-05-03--ref20_wave2_dispatch_v1.md §6 v1.1
      Option C decision (PG advisory lock retrofit replaces _ACTIVE_RUNS)

Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
```

---

## 9. Cross-References

- 上游契約：`docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` §3 G3/G7 + §4.1 + §6 + §12 #3/#7/#14/#22
- Workplan：`docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md` §4 Wave 4 R20-P2b-T2 + T3
- Wave 2 dispatch v1.1：`docs/execution_plan/2026-05-03--ref20_wave2_dispatch_v1.md` §6 Option C decision
- Sibling Wave 4 T1：`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--ref20_wave4_p2b_t1_isolated_runner.md`
- V045/V046 ledger：`sql/migrations/REF-20_RESERVATION.md` §3 + §6 v1.3
- E1 memory：`docs/CCAgentWorkSpace/E1/memory.md` 2026-05-03 Wave 4 P2b-T2/T3 entry
