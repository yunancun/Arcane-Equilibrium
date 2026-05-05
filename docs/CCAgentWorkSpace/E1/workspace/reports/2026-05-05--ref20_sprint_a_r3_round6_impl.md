# REF-20 Sprint A R3 Round 6 — Real HMAC Sign + stderr Capture + Fixture Env IMPL

**Date**: 2026-05-05
**Owner**: E1 (Backend Developer)
**PA design**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-05--ref20_sprint_a_r3_round6_task_dag.md`
**Operator decision**: (A) — IMPL chain PA→E1→E2→E4→QA (operator launched 2026-05-05)
**HEAD pre-impl**: `e9d547c0`
**Status**: IMPL COMPLETE — pending E2 review → E4 regression → PM commit

---

## §1. 4 sub-task 完成清單

| # | Sub-task | Owner | Files | LOC delta | Tests | Status |
|---|---|---|---|---|---|---|
| R3-R6-T1 | `write_manifest_fixture` real HMAC sign + sibling key.hex | E1 | `replay/route_helpers.py` (1249 → 1485, +236) | +236 | 11 PASS (T4-1) | ✅ DONE |
| R3-R6-T2 | `spawn_replay_runner` stderr → disk file | E1 | `replay/route_helpers.py` (in same file as T1) | (within +236) | 7 PASS (T4-2) | ✅ DONE |
| R3-R6-T3a | `restart_all.sh` `OPENCLAW_REPLAY_FIXTURE_DEFAULT` env injection | E1 | `helper_scripts/restart_all.sh` (470 → 492, +22) | +22 | 5 PASS (T4-3) | ✅ DONE |
| R3-R6-T4 | 4 NEW test files | E1 | NEW test files (1001 LOC across 4) | +1001 | 23 PASS (Mac) + 1 skip (smoke; opt-in) | ✅ DONE |

**4/4 sub-task ACCEPT**. Ready for E2 review.

---

## §2. Placeholder signature retirement 證明

PA design §1 acceptance #1: `grep -n placeholder_signature_wave6_v042_pending` 0 hit on production code paths.

**Final grep across full codebase**:

```
$ grep -rn "placeholder_signature_wave6\|placeholder_hash_wave6\|placeholder_key_ref" \
  program_code/ rust/openclaw_engine/ --include="*.py" --include="*.rs"
```

5 hits total, ALL non-production-code:

| Hit | File | Line | Type | Justification |
|---|---|---|---|---|
| 1 | `replay/route_helpers.py` | 756 | MAINTAINER warning docstring | E1 self-doc enforcing future grep |
| 2 | `replay/route_helpers.py` | 864 | MAINTAINER warning docstring | E1 self-doc |
| 3 | `replay/route_helpers.py` | 945 | MAINTAINER warning docstring | E1 self-doc |
| 4 | `tests/replay/test_route_helpers_real_hmac_sign.py:189-190` | test assertion `not in written` | test gate |
| 5 | `tests/replay/test_route_helpers_real_hmac_sign.py:322-323` | test assertion `not in serialised` | test gate |

**Production code path runtime emit: 0 hits**. The MAINTAINER warning strings + test gate strings are the ONLY remaining occurrences, by design (they enforce future regression).

**`build_default_manifest_payload` body-only contract**:

```python
return {
    "experiment_id": experiment_id,
    "data_tier": "S3",
    "fixture_uri": (
        os.environ.get("OPENCLAW_REPLAY_FIXTURE_URI", "").strip()
        or os.environ.get("OPENCLAW_REPLAY_FIXTURE_DEFAULT", "").strip()
        or str(output_dir / "fixture.json")
    ),
}
```

3 keys returned; envelope 3 keys (signature / manifest_hash / signature_key_ref) are computed + injected by `write_manifest_fixture` AFTER real HMAC-SHA256 sign.

**Test verification**:

```
test_build_default_manifest_payload_body_only PASSED      # set(keys) == {experiment_id, data_tier, fixture_uri}
test_build_default_manifest_payload_no_placeholders PASSED # no placeholder strings in serialised output
test_write_manifest_fixture_real_hmac_with_env_override PASSED  # full xlang verify chain green
```

---

## §3. stderr capture 真實 file write 證明

PA design §2 acceptance: `replay_runner.stderr` 寫 disk + reason_code 含 stderr 摘要 + allowlist 守門。

**`spawn_replay_runner` flow change**:

| Before (Round 5) | After (Round 6) |
|---|---|
| `stderr=subprocess.DEVNULL` | `stderr=stderr_fh` (file `<output_dir>/replay_runner.stderr`) |
| `return None, f"spawn_died_early:exit={rc}"` | `return None, f"spawn_died_early:exit={rc}:stderr={excerpt[:256]}"` |
| 0 disk artifact for post-mortem | 2KB disk file persists; reason_code embeds 256-byte tail |
| `artifact_path_within_allowlist` not invoked | `artifact_path_within_allowlist(stderr_path)` defense-in-depth guard |

**Implementation**:

```python
stderr_path = output_dir / "replay_runner.stderr"
within, allowlist_err = artifact_path_within_allowlist(stderr_path)
if not within:
    return None, "stderr_path_outside_allowlist"

stderr_fh = open(stderr_path, "wb")
proc = subprocess.Popen(
    argv, env=child_env, stdout=subprocess.DEVNULL,
    stderr=stderr_fh, close_fds=True,
)
# parent closes own fh (try/finally); child keeps via fd inheritance
```

**`_read_stderr_excerpt(path, cap_bytes=2048)` helper**:
- Reads tail 2KB from disk file (handles file-too-small via SEEK_END / size calc)
- utf-8 decode with `errors="replace"` so binary bytes don't crash decode
- Sentinel `<stderr_file_missing>` / `<stderr_read_failed:ExcName>` for read-path errors

**Test evidence**:

```
test_spawn_writes_stderr_to_disk_on_early_death PASSED
  -> err.startswith("spawn_died_early:exit=1")
  -> "manifest_signer_verify_failed" in stderr_path.read_text()
  -> reason_code includes stderr= excerpt

test_spawn_stderr_excerpt_capped_at_256_chars PASSED
  -> 4KB stderr → reason_code excerpt suffix ≤ 256 char (JSON detail bounded)

test_spawn_stderr_disk_file_2kb_cap_on_read PASSED
  -> 64KB disk file → _read_stderr_excerpt returns exactly 2048 chars (tail)

test_spawn_stderr_excerpt_handles_missing_file PASSED
  -> Path nonexistent → returns "<stderr_file_missing>" (no exception)

test_spawn_stderr_path_outside_allowlist_blocked PASSED
  -> output_dir outside allowlist root → err == "stderr_path_outside_allowlist"

test_spawn_alive_path_stderr_file_exists PASSED
  -> alive runner: stderr file persists for post-mortem
```

---

## §4. Fixture env injection 對齊

PA design §3 acceptance: `OPENCLAW_REPLAY_FIXTURE_DEFAULT` env injected by `restart_all.sh` + 3-tier fallback chain in `build_default_manifest_payload`.

**`restart_all.sh::restart_api()` change** (lines 419-441):

```bash
local replay_fixture_default
replay_fixture_default="$base_dir/rust/openclaw_engine/tests/fixtures/replay_runner_e2e/synthetic_btcusdt.json"
if [ ! -f "$replay_fixture_default" ]; then
    replay_fixture_default=""
fi
OPENCLAW_BASE_DIR="$base_dir" \
    OPENCLAW_DATA_DIR="$DATA_DIR" \
    OPENCLAW_DATABASE_URL_FILE="$OPENCLAW_DATABASE_URL_FILE" \
    OPENCLAW_IPC_SECRET_FILE="$OPENCLAW_IPC_SECRET_FILE" \
    OPENCLAW_ENGINE_BINARY_SHA="$engine_sha" \
    OPENCLAW_REPLAY_FIXTURE_DEFAULT="$replay_fixture_default" \
    nohup "$API_VENV/bin/python3" "$API_VENV/bin/uvicorn" app.main:app \
    --host 0.0.0.0 --port 8000 --workers "$WORKERS" \
    > "$DATA_DIR/api.log" 2>&1 &
```

- `bash -n` syntax check PASS
- `if [ -f ]` guard + empty fallback: register handler M-3 path catches missing fixture and surfaces 503 fixture_uri_missing instead of leaking AttributeError
- Cross-platform: `$base_dir` resolved upstream (line 391); no `/home/ncyu` / `/Users/<x>/` hardcode

**`build_default_manifest_payload` 3-tier fallback** (route_helpers.py line 768-772):

```
1. OPENCLAW_REPLAY_FIXTURE_URI (env override; operator/test)
2. OPENCLAW_REPLAY_FIXTURE_DEFAULT (server-side default from restart_all.sh)
3. <output_dir>/fixture.json (legacy default)
```

**Test evidence (5 cases all PASS)**:

```
test_fixture_uri_env_override_highest_priority         # tier 1 wins over tier 2
test_fixture_uri_default_env_used_when_override_absent # tier 2 used when tier 1 absent
test_fixture_uri_legacy_fallback_when_no_env           # tier 3 (output_dir) when tier 1+2 absent
test_fixture_uri_default_env_whitespace_trimmed        # whitespace-only OPENCLAW_REPLAY_FIXTURE_DEFAULT skipped
test_fixture_uri_override_whitespace_trimmed_then_default_used # whitespace-only OPENCLAW_REPLAY_FIXTURE_URI skipped → tier 2
```

---

## §5. 真 HMAC sign 跑通 cross-language fixture 證明

PA design §1 acceptance #2 + #3 + #4 + §6 H2 + H8.

**`write_manifest_fixture` 5-step flow** (route_helpers.py line 819-918):

1. Validate input (run_id non-empty, manifest_data dict, no envelope leak)
2. Build body dict with run_id appended (deep-copy via JSON round-trip)
3. Resolve signing key via `_resolve_manifest_signing_key()`:
   - env override `OPENCLAW_REPLAY_SIGNING_KEY_FILE` → 1st priority
   - `load_signing_key_from_secrets_dir(env_label)` → 2nd priority
   - Fail-closed `ValueError("manifest_signing_key_unavailable")` else
4. Compute canonical bytes via `compute_manifest_canonical_bytes(body)` →
   `compute_body_hash(canonical_bytes)` → `ManifestSigner.from_bytes_for_test(...).sign(canonical_bytes)`
5. Assemble disk dict (3 body + run_id + 3 envelope = 7 keys) + write
   `<output_dir>/manifest.json` + drop sibling `<output_dir>/key.hex`
   (mode 0o600, trailing newline)

**Cross-language byte-equal invariant**:

| Step | Python side | Rust side |
|---|---|---|
| canonical bytes | `compute_manifest_canonical_bytes(body)` (sort_keys + compact + ensure_ascii=False) | `canonical_body_for_signing(disk_bytes)` (BTreeMap sort + compact serde_json) |
| envelope strip | body dict already lacks envelope at sign time | `ENVELOPE_KEYS_FOR_SIGNING.iter() { obj.remove(k) }` at verify time |
| signature | `ManifestSigner.sign(canonical_bytes)` HMAC-SHA256 | `ManifestSigner::verify(canonical_body, ...)` HMAC-SHA256 |
| body hash | `compute_body_hash(canonical_bytes)` SHA-256 | `compute_body_hash(&canonical_body)` SHA-256 |
| fingerprint | `compute_key_fingerprint(file_content_bytes)` SHA-256[:16] | `compute_key_fingerprint(key_file_content)` SHA-256[:16] |
| sibling key | `key_bytes.hex() + "\n"` 0o600 | `manifest_path.parent() / "key.hex"` |

**Sprint 1 8/8 + R2 13/13 cross-language regression test PASS**:

```
$ python3 -m pytest program_code/.../tests/replay/ -k xlang_consistency -q
13 passed, 29 deselected
```

This proves Round 6 reuse of `compute_manifest_canonical_bytes` did NOT break the canonical bytes contract.

**Self-test sanity (Python verify path)**:

```python
# After write_manifest_fixture, recompute + verify
body_only = {k: v for k, v in disk.items() if k not in ENVELOPE_KEYS_FOR_SIGNING}
canonical = compute_manifest_canonical_bytes(body_only)
expected_hash = compute_body_hash(canonical)
assert expected_hash == disk["manifest_hash"]  # matches

archive = InMemoryKeyArchive()
archive.insert(expected_fp, KeyStatus.ACTIVE)
signer = ManifestSigner.from_bytes_for_test(bytes.fromhex(TEST_KEY_HEX), expected_fp)
expected_sig = signer.sign(canonical)
assert expected_sig == disk["signature"]  # byte-equal
signer.verify(canonical, disk["manifest_hash"], disk["signature"], disk["signature_key_ref"], archive)
# verify passes — full xlang chain green
```

This is exactly the path Rust `replay_runner.rs::load_and_verify_manifest` follows; if Python verify passes, Rust verify will too (assuming the 8/8 + 13/13 xlang fixture invariant holds).

---

## §6. Sibling regression — 141 PASS

PA design §6 H5 acceptance: ≥ 118 PASS sibling.

```
$ python3 -m pytest program_code/.../tests/ -k replay --no-header -q
141 passed, 1 skipped, 3387 deselected, 30 warnings
```

| Test category | PASS |
|---|---:|
| New (R3 round 6): `test_route_helpers_real_hmac_sign.py` | 11 |
| New (R3 round 6): `test_route_helpers_stderr_capture.py` | 7 |
| New (R3 round 6): `test_route_helpers_fixture_default_env.py` | 5 |
| New (R3 round 6): `test_replay_e2e_round6_smoke.py` | 0 PASS + 1 skip (opt-in) |
| Existing replay sibling (Sprint 1 / 2 / 3 / 4 + R1+R2+R3 round 1-5) | 118 |
| **Total** | **141 + 1 skip** |

**Delta from PA baseline**: +23 (118 → 141), all from new R3-R6 tests; **0 regression**.

---

## §7. LOC governance

PA design §6 H1 acceptance: route_helpers.py < 1500.

| File | Baseline | Post | Delta | §九 800 警告 | §九 1500 硬限 |
|---|---:|---:|---:|---|---|
| `replay/route_helpers.py` | 1249 | **1485** | +236 | 已破（Wave 4 既有；PA accepted） | 1485 < 1500 ✅ |
| `helper_scripts/restart_all.sh` | 470 | 492 | +22 | < 800 ✅ | < 1500 ✅ |
| `tests/replay/test_route_helpers_real_hmac_sign.py` | 0 | 324 | +324 | < 800 ✅ | < 1500 ✅ |
| `tests/replay/test_route_helpers_stderr_capture.py` | 0 | 315 | +315 | < 800 ✅ | < 1500 ✅ |
| `tests/replay/test_route_helpers_fixture_default_env.py` | 0 | 120 | +120 | < 800 ✅ | < 1500 ✅ |
| `tests/replay/test_replay_e2e_round6_smoke.py` | 0 | 242 | +242 | < 800 ✅ | < 1500 ✅ |

**route_helpers.py 1485** is at upper edge of 1500 hard cap. **Round 7+ MUST split** (per PA design §6 H1; suggested split: extract `manifest_provisioning.py` for `_resolve_manifest_signing_key` + `build_default_manifest_payload` + `write_manifest_fixture` + `_read_stderr_excerpt`).

**Pre-existing baseline exception clause did NOT trigger** (1249 < 1500); we're operating within the standard 1500 hard cap.

---

## §8. Git status sign-off (clean對應檔)

```
$ git status --porcelain
 M docs/CCAgentWorkSpace/PA/memory.md
 M docs/CCAgentWorkSpace/QA/memory.md
 M docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-04--ref20_sprint_a_r3_smoke_e2e.md
 M helper_scripts/restart_all.sh
 M program_code/exchange_connectors/bybit_connector/control_api_v1/replay/route_helpers.py
?? docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-05--ref20_sprint_a_r3_round6_impl.md  (this report)
?? docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-05--ref20_sprint_a_r3_round6_task_dag.md
?? program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_replay_e2e_round6_smoke.py
?? program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_route_helpers_fixture_default_env.py
?? program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_route_helpers_real_hmac_sign.py
?? program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_route_helpers_stderr_capture.py
```

**Sign-off rule** (CLAUDE.md §七 P0-GOV-3): all listed files are this round's IMPL artifacts. The 3 modified upstream files (PA memory / QA memory / QA report) are sibling-CC artifacts from Round 5 closure that should not block Round 6 commit; PA's design report (also `??`) belongs with the 4-task DAG and is part of this commit chain. **0 unrelated WIP**; clean.

---

## §9. 預留問題 + Operator 下一步

### 給 E2 review 的關鍵點

1. **PA design §5 E2 review #1** — verify T1 signing key fallthrough order does NOT include placeholder fallthrough.
   - `_resolve_manifest_signing_key()` line 705-768: Step 1 env override → Step 2 secrets-dir → Step 3 `raise ValueError("manifest_signing_key_unavailable")`. **No placeholder fallthrough**. Confirm via grep.
2. **PA design §5 E2 review #2** — T2 stderr_path passes `artifact_path_within_allowlist`.
   - `spawn_replay_runner` line 991-998: `within, err = artifact_path_within_allowlist(stderr_path)` enforces guard before file open. **Guard active**.
3. **PA design §5 E2 review #3** — T1 reuses canonical/sign helpers; doesn't duplicate kwargs.
   - `write_manifest_fixture` line 870-873: imports `compute_manifest_canonical_bytes` from `experiment_registry` + `ManifestSigner` / `compute_body_hash` from `manifest_signer`. **No kwarg duplication**. xlang regression 13/13 PASS confirms.
4. **PA design §6 H8** — T1 strips envelope from canonical body.
   - `ENVELOPE_KEYS_FOR_SIGNING` constant matches Rust `["signature", "manifest_hash", "signature_key_ref"]`; canonical body computed BEFORE envelope inject (line 893-906). **Aligned**.
5. **PA design §6 H9** — placeholder grep 0 hit on production paths.
   - §2 above documents 5 hits all in MAINTAINER docstring + test assertion (intentional). **Production code 0 hit**.

### 給 E3 security audit 的關鍵點

1. `OPENCLAW_REPLAY_SIGNING_KEY_FILE` env override is **dev/test only**; live profile still goes through R2-T3 secrets-dir + symlink-injection guard (`load_signing_key_from_secrets_dir` honors `is_live_release_profile_fn=is_live_release_profile`). Verify live profile reachable secrets are still mode-checked + symlink-checked.
2. Sibling `key.hex` chmod 0o600 best-effort; Mac dev sandbox FS may keep 0o644 (test acknowledges via `mode in (0o600, 0o644)`). **Acceptable on dev**; Linux production runs under controlled $OPENCLAW_DATA_DIR (mode 0o700 dir) so sibling 0o600 enforced normally.
3. `OPENCLAW_REPLAY_FIXTURE_DEFAULT` is server-side resolved by `restart_all.sh` (line 419-423); not client-controllable. R4 UI client supplies via register payload's `manifest_jsonb.fixture_uri` (preempts env in fallback chain).
4. `replay_runner.stderr` file path bound by `artifact_path_within_allowlist`; allowlist root resolves to `/tmp/replay_artifacts_test_only` (Mac) or `$OPENCLAW_DATA_DIR/replay_artifacts` (Linux). **No path traversal**.

### 給 E4 regression 的關鍵點

1. **Round 5 mock-only 假綠教訓 (PA §5 E4 review #1)** — T4-4 (`test_replay_e2e_round6_smoke.py`) is opt-in via `OPENCLAW_REPLAY_E2E_SMOKE=1` env + spawns REAL Rust binary. E4 must run on Linux trade-core post-deploy: `OPENCLAW_REPLAY_E2E_SMOKE=1 python3 -m pytest .../test_replay_e2e_round6_smoke.py -xvs`.
2. **4 表 row > 0 binding** — full E2E smoke (register → run → finalize → SELECT 4 tables) is covered by sibling tests (`test_replay_run_finalize.py` + `test_replay_simulated_fills_writer.py`); Round 6 smoke is scoped to spawn-and-verify chain validation only. E4 should run those alongside on Linux.
3. **xlang_consistency 13/13** — Sprint 1 F1 retrofit canonical bytes contract; Round 6 reuses helpers without kwarg duplication. **Confirmed PASS** on Mac dev. E4 reruns on Linux for cross-platform parity.

### Operator 下一步

1. **PM**: review this report + PA design + commit chain (PA→E1→E2→E4 mandatory).
2. **E2**: code review per §9 review points; LOC at 1485/1500 → cleared but recommend P2 ticket for Round 7+ split.
3. **E4**: regression run on Mac + Linux; Linux smoke E2E with `OPENCLAW_REPLAY_E2E_SMOKE=1`.
4. **PM commit + push**: after E2 ACCEPT + E4 PASS.
5. **Post-deploy**: Linux trade-core `restart_all.sh --rebuild` to pick up new env injection + Python code; QA round 4 smoke E2E should now produce V045 status='succeeded' + V046 1 row + V050 N rows + V054 audit ≥ 3 rows.

---

## §10. Push back / open question (none)

PA design §1-§7 fully reachable with available helper APIs (`ManifestSigner.from_bytes_for_test` / `compute_body_hash` / `compute_key_fingerprint` / `load_signing_key_from_secrets_dir` / `compute_manifest_canonical_bytes` all exist as designed). No PM push back needed. canonical_bytes contract was reused as-is; no R2-T5 contract impact.

---

## §11. Round 7 fix log (2026-05-05) — FINDING-1 (HIGH) + FINDING-2 (LOW)

### §11.1 Scope

E2 round 6 review (`docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-05--ref20_sprint_a_r3_round6_e2_review.md`) RETURN to E1 with:

- **FINDING-1 (HIGH)**: `OPENCLAW_REPLAY_SIGNING_KEY_FILE` env override 缺 live profile gate (route_helpers.py:765-803 step 1). PA design §7 Q2 自承 "dev/test only" 但實作未對齊 Sprint 1 Track C P0-2 既有 pattern (`OPENCLAW_REPLAY_VERIFY_TEST_KEY` 在 production 由 `is_live_release_profile()` 阻斷)。
- **FINDING-2 (LOW)**: `spawn_died_early` reason_code 含 256 byte stderr excerpt → 進 HTTPException 503 detail JSON → 洩 server-side absolute path / fingerprint hex 給 API client。違反 §九 SEC-04 「detail=str(e) → 'Internal server error'」原則。

E4 round 6 regression PASS (Linux 3.12 parity); commit gate 卡 E2 RETURN。

### §11.2 FINDING-1 fix (HIGH)

**位置**: `route_helpers.py:765-803` (`_resolve_manifest_signing_key()` step 1)

**Diff 摘要**:

```python
# Before (Round 6):
override_path_str = os.environ.get(SIGNING_KEY_FILE_ENV_VAR, "").strip()
if override_path_str:
    override_path = Path(override_path_str)
    if not override_path.is_file():
        raise ValueError(...)
    # ... rest of step 1 ...

# After (Round 7):
override_path_str = os.environ.get(SIGNING_KEY_FILE_ENV_VAR, "").strip()
if override_path_str:
    if is_live_release_profile():
        log.warning(
            "signing key env override blocked under live profile: %s=%s",
            SIGNING_KEY_FILE_ENV_VAR, override_path_str,
        )
        raise ValueError(
            "signing_key_file_env_override_blocked_in_live_profile"
        )
    override_path = Path(override_path_str)
    if not override_path.is_file():
        raise ValueError(...)
    # ... rest of step 1 unchanged ...
```

`is_live_release_profile()` 是 route_helpers.py:1188-1205 既有 helper（讀 `OPENCLAW_RELEASE_PROFILE` env，case-insensitive 比對 "live"）。Round 7 step 1 開頭重用此 helper，complete align Sprint 1 Track C P0-2 SEC-08 pattern.

**Docstring** Priority 段落同步更新：標記 step 1 為 dev/test ONLY + 註明 live profile hard-block + 引用 P0-2 既有 pattern。

**Tests**:

加 2 個新 case 到 `test_route_helpers_real_hmac_sign.py`：

1. **`test_resolve_signing_key_env_override_blocked_in_live_profile`** — provision a valid-looking key file + set `OPENCLAW_RELEASE_PROFILE=live` + `OPENCLAW_REPLAY_SIGNING_KEY_FILE=<path>` → expect `ValueError("signing_key_file_env_override_blocked_in_live_profile")`. 證明 block 由 profile 驅動，不是由 file 內容驅動。
2. **`test_resolve_signing_key_env_override_works_outside_live_profile`** — counter-test：4 個 non-live profile (unset / demo / paper / live_demo) 下相同 env 仍正常 return (key_bytes, fingerprint)。證明 gate 範圍精準限縮。

PA brief 期 12 PASS（11+1）；實際加 2 case = 13 PASS（11 round 6 + 2 round 7 雙保險）。

### §11.3 FINDING-2 fix (LOW)

**位置 1**: `route_helpers.py:619-635` (`spawn_replay_runner` early-death return)

**Diff 摘要**:

```python
# Before (Round 6):
return None, f"spawn_died_early:exit={rc}:stderr={stderr_excerpt[:256]}"

# After (Round 7):
return None, f"spawn_died_early:exit={rc}"
# stderr_excerpt 仍 log.warning 寫 server log；disk file replay_runner.stderr
# 不變（operator 唯一診斷入口）。reason_code envelope-only。
```

**位置 2**: `app/replay_routes.py:674-687` (503 HTTPException detail message)

**Diff 摘要**:

```python
# Before (Round 6):
raise HTTPException(
    status_code=503,
    detail={
        "reason_codes": ["replay_runner_spawn_failed"],
        "message": f"replay_runner failed to spawn: {pg_err}",
    },
)

# After (Round 7):
raise HTTPException(
    status_code=503,
    detail={
        "reason_codes": ["replay_runner_spawn_failed"],
        "message": (
            "replay_runner failed to spawn; check server logs "
            "(replay_runner.stderr) for diagnosis"
        ),
    },
)
```

兩層共同收緊 (defense in depth)：

1. route_helpers.py 從根源剝離 stderr text 自 reason_code（envelope-only），確保 reason_code 永不含 server-side 資訊。
2. replay_routes.py detail message 改為靜態 operator-pointer，即使 reason_code 萬一重新含 server-side text 也不會 leak 進 API 回應 body。

**Tests**: 微調 + 升級既有 1 個 case，新增 0 case：

1. **`test_spawn_writes_stderr_to_disk_on_early_death`**（既有；微調）：assertion 從 `assert "manifest_signer_verify_failed" in err` 改為 `assert err == "spawn_died_early:exit=1"`。stderr text 改驗 disk file 內容（既有 line 141-142）。
2. **`test_spawn_stderr_excerpt_capped_at_256_chars` → `test_spawn_stderr_excerpt_not_in_reason_code`**（既有；升級）：原來測 256 char cap 在 round 7 後 reason_code 永遠 envelope-only < 30 char，cap 已自動滿足。改為測 SEC-04 invariant：reason_code **不含** stderr text / path / fingerprint。case 加長 stderr 包含 faux server path + fingerprint，verify reason_code 無 leak。

`test_route_helpers_stderr_capture.py` MODULE_NOTE 同步更新標明 Round 7 SEC-04 invariant。

### §11.4 Self-test 結果

| 測試 | Mac 結果 | Linux 結果 |
|---|---|---|
| `test_route_helpers_real_hmac_sign.py` | **13 PASS** (11 round 6 + 2 round 7) | **13 PASS** parity ✓ |
| `test_route_helpers_stderr_capture.py` | **7 PASS** (round 6 7 case 中 1 微調 + 1 升級 + 5 不變) | **7 PASS** parity ✓ |
| Round 6+7 合計 unit test | **20 PASS** | **20 PASS** parity ✓ |
| Sibling replay regression | **143 PASS / 1 skip / 0 fail** | **140 PASS / 3 fail (pre-existing P2-R3-FOLLOW-UP-6 fixture UUID bug) / 1 skip** |

**Linux 3 fail** 是 round 6 hotfix log 已記錄的 pre-existing fixture UUID bug (TODO P2-R3-FOLLOW-UP-6)，**與 Round 7 fix 無關**。已用 `git stash` 雙向驗證：stash round 7 改動跑 Linux baseline，3 fail 一致；證明非 round 7 引入。

### §11.5 LOC delta

| 檔 | Round 6 | Round 7 | Delta | §九 1500 hard cap |
|---|---:|---:|---:|---|
| `replay/route_helpers.py` | 1485 | **1499** | +14 | ≤ 1500 ✓（PA brief 預估 +5 但實際 +14；FINDING-1 production code +12 + docstring update +2） |
| `app/replay_routes.py` | 1499 | **1500** | +1 | ≤ 1500 ✓（FINDING-2 fix 注釋 7 行 + message 改靜態 4 行 - 既有 1 行 = +1 LOC margin tight） |
| `tests/replay/test_route_helpers_real_hmac_sign.py` | 324 | **392** | +68 | < 800 ✓（2 new case 共 +68 LOC docstring 雙語） |
| `tests/replay/test_route_helpers_stderr_capture.py` | 315 | **355** | +40 | < 800 ✓（1 case 升級 + MODULE_NOTE 更新） |

`replay/route_helpers.py` 1499/1500 + `app/replay_routes.py` 1500/1500 兩檔均碰 §九 1500 cap 邊緣。**Round 8+ 任何加碼必先抽部分行 to `replay/manifest_provisioning.py` 或 `replay/spawn_helpers.py` 拆檔**。Round 5 hotfix 已開 TODO P2-R3-FOLLOW-UP-7（"`app/replay_routes.py` 1499/1500 LOC margin 過薄"）；Round 7 後 follow-up 仍存在且更急切。

### §11.6 Placeholder + 跨平台 grep regression

```
$ grep -nE "placeholder_signature_wave6|placeholder_hash_wave6|wave6_v042_pending|placeholder_key_ref" \
  program_code/exchange_connectors/bybit_connector/control_api_v1/replay/route_helpers.py
759:    ``placeholder_signature_wave6`` / ``placeholder_hash_wave6`` 0 hit。
877:    E2/CR/QA edit 後必 grep ``placeholder_signature_wave6`` /
878:    ``placeholder_hash_wave6`` 0 hit。
958:    fail-closed）；E2/CR/QA edit 後必 grep ``placeholder_signature_wave6``
959:    / ``placeholder_hash_wave6`` 0 hit。
```

5 hits 全在 MAINTAINER warning docstring（self-doc enforcing future grep），production code path 0 hit。

```
$ grep -nE "/home/ncyu|/Users/ncyu" route_helpers.py replay_routes.py 2 test files
（無輸出）
```

跨平台路徑硬編碼 0 hit。

### §11.7 Linux 3.12 parity 確認

```
$ ssh trade-core "cd ~/BybitOpenClaw/srv && program_code/.../.venv/bin/pytest \
  test_route_helpers_real_hmac_sign.py test_route_helpers_stderr_capture.py \
  --no-header -q 2>&1 | tail -3"
20 passed, 5 warnings in 1.43s
```

Round 7 改動透過 scp 推到 Linux working tree（git status dirty，不過 git；等 PM commit + push 後 Linux git pull --ff-only 同步）。Linux 20 PASS = Mac 20 PASS parity。

### §11.8 Operator 下一步

1. **PM** review 此報告 (round 6 + round 7 累積 sign-off)。
2. **E2 round 7 brief verify** (~5 min focused review)：FINDING-1 step 1 live profile gate 對齊 P0-2 ✓ + FINDING-2 reason_code envelope-only + 503 detail static ✓。
3. **E4 round 7 brief regression** (~5 min smoke)：13 + 7 = 20 PASS Mac/Linux parity；sibling 143/140 PASS（3 fail pre-existing 不算 regression）。
4. **PM commit + push**：然後 Linux trade-core `restart_all.sh --rebuild` 部署。
5. **QA round 4 smoke E2E**：應 produce V045 status='succeeded' + V046 1 row + V050 N rows + V054 audit ≥ 3 rows。

### §11.9 不確定之處

- `replay_routes.py` LOC 1500 = exact cap，**無 margin**。若 Round 7 commit 過程中 PM 有任何 docstring 補充（commit message header 等等），會立即破 cap。建議 commit 完即啟動 P2-R3-FOLLOW-UP-7（抽 hotfix 警告塊到 `replay/MAINTAINER_NOTES.md` 外部檔回收 ~7 LOC）。

---

## §12. Round 9 Layer-6 fix（subprocess clean-exit sentinel pid=-1）

**Date**: 2026-05-05
**HEAD pre-impl**: `3a425447` (R8 deploy + Mac/Linux/origin sync)
**Status**: IMPL COMPLETE — pending E2 review → E4 regression → PM commit + Linux deploy → QA round 6 final acceptance
**PM brief**: round 9 task spec — Layer 6 blocker; route_helpers.py 1499 + replay_routes.py 1500 cap-tight；Mac LOC verified ≤1500；trim source = stale R6 placeholder doc-comment block (15 LOC saved)

### §12.1 Root cause + sentinel pid=-1 contract

**Layer-6 blocker（QA round 5 揭）**：subprocess 真實成功完成（exit=0）+ replay_report.json 真實寫 disk + key.hex + manifest_fixture.json 全在；BUT `route_helpers.py::spawn_replay_runner` 對 `rc == 0` 也 return `(None, "spawn_died_early:exit=0")`；`replay_routes.py::post_replay_run` 把這視為 failure → 503 → V045 status='failed' → 4 表 acceptance 1/1/0/0；Sprint A acceptance 不達。

**正確語意修正**：
- subprocess `rc == 0` within poll grace = **subprocess completed successfully**（synthetic walker 10 events typically <1.5s warm cache 跑完是常態）。Round 6/7/8 mistakenly treated as `spawn_died_early` failure。
- subprocess `rc != 0` within poll grace = real spawn_died_early failure（保 Round 6 行為不變）。
- subprocess still alive after poll grace = success path（保現有 OK 行為）。

**Round 9 sentinel pid=-1 contract**（route_helpers.py:631-640）：
```python
if rc is not None and rc == 0:
    # R9 Layer-6: rc=0 in poll grace = SUCCESS (synthetic walker
    # <1.5s); sentinel pid=-1 → caller UPDATE status='running' +
    # /finalize. R9 Layer-6：rc=0 grace 內 = 成功，sentinel -1。
    log.info(...)
    return -1, None
```

**Caller side** (`replay_routes.py::post_replay_run`)：
```python
if pid == -1:
    cur.execute(
        "UPDATE replay.run_state SET status='running' "
        "WHERE run_id=%s::uuid;",
        (run_id_local,),
    )
    conn.commit()
    return run_id_local, None, None, output_dir
```

**`/run` response envelope**（replay_routes.py 加 flag）：
```python
"subprocess_completed_in_poll": subprocess_pid is None,
```
True ⇒ subprocess 已在 poll grace 完成；caller 可直接呼 `/finalize` 不用 wait subprocess。

### §12.2 LOC delta（兩檔結尾值）

| File | Pre-R9 | Post-R9 | Delta | Cap | Margin |
|---|---:|---:|---:|---:|---:|
| `replay/route_helpers.py` | 1499 | **1498** | -1 | 1500 | 2 |
| `app/replay_routes.py` | 1500 | **1500** | 0 | 1500 | 0 (exact cap) |
| **Total** | 2999 | **2998** | -1 | 3000 | — |

**Trim source（replay_routes.py）**：`# 4) Resolve output_dir + write manifest fixture` 區段 21 LOC stale R6 placeholder doc-comment（描述 R6 前 placeholder behavior，已被 real HMAC sign 取代）→ 緊縮至 6 LOC，淨 -15 LOC，恰好用作 R9 sentinel branch (10 LOC) + envelope flag (4 LOC) 補充 budget；總 net 0 LOC。
**Trim source（route_helpers.py）**：原 `# Pathological: binary exited cleanly within grace window` 11 LOC 區塊改寫為 R9 sentinel return 10 LOC（淨 -1 LOC）；docstring 加 R9 contract 描述 +20 LOC，再緊縮回 +0 LOC。

**E2/E4 LOC verification command**：
```bash
wc -l program_code/exchange_connectors/bybit_connector/control_api_v1/replay/route_helpers.py \
       program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_routes.py
# expect ≤1500 both, total = 2998
```

### §12.3 Mac + Linux test PASS

**Mac side（venvs/mac_dev/bin/pytest）**：
```
test_route_helpers_stderr_capture.py: 8 passed (含新加的 test_spawn_clean_exit_in_poll_returns_sentinel_pid_minus_one)
test_route_helpers_real_hmac_sign.py: 13 passed
test_route_helpers_fixture_default_env.py: 5 passed
[replay 全集合]: 144 passed, 1 skipped (e2e smoke opt-in), 3387 deselected
```

**Linux side（trade-core .venv/bin/pytest）**：
```
[3 focal test files]: 26 passed (含 R9 sentinel test)
[replay 全集合]: 141 passed, 3 failed (pre-existing - 與 R9 無關), 1 skipped
```

**Pre-existing fail 確認**（與 R9 修改無關）：
- `tests/test_replay_routes_auth.py::test_authenticated_zero_active_run_post_run_accepts`
- `tests/test_replay_routes_auth.py::test_authenticated_per_actor_cap_returns_409`
- `tests/test_replay_routes_auth.py::test_authenticated_global_cap_returns_409`

**A/B verification done**：暫時 restore Linux 原始 4 檔（Mac 改 deploy 前的 Linux git HEAD `3a425447` 狀態）跑 `tests/test_replay_routes_auth.py` → 同樣 3 fail / 1 pass（即 fail set 與 R9 無關）；確認後再 redeploy R9 payload。Pre-existing fail root cause = `tests/test_replay_routes_auth.py:_build_client_with_actor` 用 `experiment_id="exp-2026-05-03-test"` 直送 V049 lookup → SQL `WHERE experiment_id = 'exp-2026-05-03-test'` 報 `invalid input syntax for type uuid`（V049 schema column type 是 UUID 不是 TEXT；預期 register endpoint 先返 UUID）— 是 R2 schema vs auth test fixture 對齊問題，不在 R9 scope。

### §12.4 Git status sign-off-clean

```
$ git status --porcelain | grep -E 'replay_routes|route_helpers|test_(replay_e2e|route_helpers_stderr)' | head
 M program_code/exchange_connectors/bybit_connector/control_api_v1/app/replay_routes.py
 M program_code/exchange_connectors/bybit_connector/control_api_v1/replay/route_helpers.py
 M program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_replay_e2e_round6_smoke.py
 M program_code/exchange_connectors/bybit_connector/control_api_v1/tests/replay/test_route_helpers_stderr_capture.py
```

R9 modified set = **4 檔**（route_helpers.py / replay_routes.py + 2 test files），全在 git status modified；待 PM commit + push + Linux deploy。

**No untracked R9 file leftover**：未 create new file（PA spec 指示「不抽 helper 新檔」遵守）。

### §12.5 預留問題（給 PM）— Layer 7 是否潛在？

**已 cleared 路徑** (R9 修完之後):
1. R6+R7+R8 cleared 部分維持不變（_resolve_manifest_signing_key / write_manifest_fixture / stderr capture / OPENCLAW_REPLAY_SIGNING_KEY_FILE env injection）。
2. R9 sentinel pid=-1 contract 加封 `spawn_replay_runner` clean-exit ↔ caller `post_replay_run` UPDATE V045 ↔ response envelope `subprocess_completed_in_poll` flag 三點對齊。
3. `/finalize` endpoint 在 sentinel 路徑下被 caller (operator GUI / QA round 6 e2e script) 呼叫；R3-T1 既有 `_fr.run_finalize_in_pg_xact` 不變（它讀 `replay_report.json` from disk + INSERT V046/V050），R9 sentinel 路徑下 V045 row status='running' + subprocess_pid NULL，符合 `_fr` finalize input 預期。

**Layer 7 潛在風險清單**（給 PM 判斷是否值得 round 10 預留）：

(a) **`/finalize` 對 subprocess_pid IS NULL 的容忍度**：R3-T1 finalize logic 是否假設 `WHERE run_id=X AND subprocess_pid IS NOT NULL`？若是 → R9 sentinel 路徑下會 0 row finalize → V050 仍 0。**建議**：QA round 6 first run 先驗證 V050 真寫入 ≥1 row；若 fail 則回 PA 派發 R10。預期不會 fail（finalize 通常 by run_id query 不 by pid，但需驗證）。

(b) **synthetic walker 是否真產出 V050 simulated_fills 形狀**：synthetic walker is `replay_runner` Rust binary 在 `synthetic_btcusdt.json` fixture 走 10 events；產出 `replay_report.json` 是 trades + simulated fills array；`run_finalize_route::run_finalize_in_pg_xact` 把 fills array 轉成 V050 INSERT。R9 修了 spawn return value 不影響此鏈條，但 R6 sign + verify drift 若有殘留可能讓 fills array 為 0。**建議**：QA round 6 額外 grep `replay_report.json` 內 fills array 長度 > 0 + 比對 V050 INSERT row count。

(c) **`subprocess_completed_in_poll` flag downstream consumer**：UI / GUI 對此 flag 的處理邏輯尚未 implement（GUI 仍 disabled per P1-1）；CLI / E2E test 不影響。**建議**：P2-R3-FOLLOW-UP-9（新建）追加 GUI subtab enable 後對此 flag 的 progress bar handling。

(d) **e2e smoke test (round6_smoke) acceptance change**：原 `assert err == "spawn_died_early:exit=0"` 改為 R9 contract `assert err is None and (pid > 0 or pid == -1)`；現 `OPENCLAW_REPLAY_E2E_SMOKE=1` env-gated opt-in。**建議**：QA round 6 跑 with `OPENCLAW_REPLAY_E2E_SMOKE=1` 設定，驗證 e2e smoke acceptance 與 4-table acceptance 同時 GREEN。

(e) **`replay_routes.py` LOC 1500 = exact cap**：R9 完成後 `app/replay_routes.py` 仍 1500 LOC，**0 margin**。任何後續微調必觸 cap → R10 起所有對 `replay_routes.py` 的改動必先抽部分到 `replay/` 子模組。**建議**：開 P2-R3-FOLLOW-UP-10「`app/replay_routes.py` LOC 1500 exact cap，下次改動前先 split」（與 R5 hotfix 後新開的 P2-R3-FOLLOW-UP-7 合併或 supersede）。

### §12.6 Operator 下一步

1. **E2 round 9** focused review (~10 min)：確認 sentinel pid=-1 contract 簡潔 + caller side 處理三分支正確（real fail / sentinel / alive）+ envelope flag 語意對齊 + 2 test (新加 R9 + e2e smoke 對齊)。
2. **E4 round 9** brief regression (~5 min)：Mac 144 PASS / 1 skip + Linux 141 PASS / 3 fail (pre-existing) / 1 skip 兩端 parity（fail set 經 A/B 驗證為 R2 schema vs auth test fixture 對齊問題，與 R9 無關）。
3. **PM commit + push**：`hotfix(replay): R9 Layer-6 — subprocess clean-exit sentinel pid=-1 (REF-20 Sprint A R3 round 9)`；commit 後 Linux trade-core `restart_all.sh --rebuild`。
4. **QA round 6 final acceptance**：opt-in `OPENCLAW_REPLAY_E2E_SMOKE=1` + 4-table acceptance 應達 1/1/N/N（V045 status='succeeded' + V046 1 row + V050 ≥1 row + V054 audit ≥3 rows）；若 V050 仍 0 row → 觸發 §12.5(a) Layer 7 prediction → reopen R10 finalize-side fix。

---

**End of report (round 6 + round 7 + round 9 cumulative sign-off)**.
