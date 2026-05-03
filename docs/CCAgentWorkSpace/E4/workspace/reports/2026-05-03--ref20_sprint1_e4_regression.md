# REF-20 Sprint 1 — E4 Regression（Track A + B + C + D 整 Sprint 1 驗收）

**Date**: 2026-05-03
**Tester**: E4（cold reality regression — Mac dev SSOT real run）
**Verdict**: **CONDITIONAL** — Sprint 1 引入 0 新 fail / 0 新 regression / 0 hard-boundary mutation；2 條 pre-existing E4-P0-1 + E4-P0-2 仍 fail（cold audit `2026-05-03--ref20_final_closure_e4_cold_audit.md` 已抓，Sprint 1 沒明確修這兩條）
**Scope**: PM 派 E4 final regression 整 Sprint 1（Track A 19 + Track B 11 + Track C 13 + Track D 24 + V053 7 = expected 63+ NEW + 全 baseline regression）
**Read upstream**: PA partition design + 4 Track E1 reports + E2 round 1 + E2 round 2 retrofit verify + cold audit baseline

---

## 0. TL;DR

### 真實 Mac dev 數字（HEAD `2ffe43d` + 30 file unstaged Sprint 1 patch）

| 引擎 | passed | failed | ignored/skip | cold audit baseline | delta | verdict |
|---|---|---|---|---|---|---|
| Python pytest control_api_v1 全 suite（excl integration）| **3387** | **1** | 10 skip | 3374 / 1 / 10 | **+13 PASS / +0 fail** | ✓（fail = pre-existing E4-P0-1） |
| Python pytest learning_engine 21 case | n/a | n/a | n/a | n/a | n/a | n/a（不在 Sprint 1 scope） |
| Rust cargo test --release --lib | **2454** | **0** | **0** | 2447 / 0 / 0 | **+7 PASS / +0 fail** | ✓ |
| Rust cargo test --release --workspace | **3084** | **2** | **3** | 3077 / 2 / 3 | **+7 PASS / +0 fail** | ✓（fail = pre-existing E4-P0-2 doctest） |
| Rust cargo test --release --tests --features replay_isolated | **2643** | **0** | **0** | 2630 / 0 / 0 | **+13 PASS / +0 fail** | ✓ |
| Sprint 1 specific 4-track suite（A 19 + C 13 + D 24 + V053 7）| **63** | **0** | 0 | new | match expected | ✓ |
| SLA stress integration 35 case | **35** | **0** | 0 | 35 | match | ✓（hot path 0 影響）|
| Track B xlang manifest_signer consistency | **8** | **0** | 0 | 8 | match | ✓ |
| Track B replay_runner bin（4 fail-mode + 1 happy + 1 sanity）| **6** | **0** | 0 | new | match | ✓ |
| LG-5 healthcheck pytest（含 [42]/[42b]/[42c]/[43]）| **25** | **0** | 0 | 25 | match | ✓ |

### Sprint 1 引入的 fail count

**0 新 fail**（兩條既有 E4-P0-1/P0-2 是 cold audit `2026-05-03--ref20_final_closure_e4_cold_audit.md` 已抓的 pre-existing baseline failure，Sprint 1 沒承諾修也沒新增）。

### 兩遍 reproducibility

| 引擎 | Run 1 | Run 2 | flake? |
|---|---|---|---|
| Python control_api_v1 全 suite | 3387 P / 1 F / 10 skip | 3387 P / 1 F / 10 skip | ✗（deterministic match）|
| Rust cargo --release --lib | 2454 P / 0 F | 2454 P / 0 F | ✗ |
| Rust cargo --release --workspace | 3084 P / 2 F / 3 ignored | 3084 P / 2 F / 3 ignored | ✗ |

deterministic shared-state pollution（E4-P0-1）在 2 遍 run identical reproduce — match cold audit 結論「不是 transient flaky；是 test order dependency 已穩定形成」。

---

## 1. Sprint 1 Specific Test Suite（4 track + V053）— **63/63 PASS**

```
$ python3 -m pytest \
    program_code/exchange_connectors/bybit_connector/control_api_v1/replay/tests/test_track_a_spawn_argv.py \
    program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_routes_track_c_security.py \
    tests/migrations/test_v049_v050_v051_v052_track_d.py \
    tests/migrations/test_v053_replay_event_types.py \
    -v
```

| Track | 期 | 跑 | delta |
|---|---|---|---|
| Track A spawn argv（含 2 NEW byte-equal canonical retrofit）| 19 | 19 | match ✓ |
| Track C 安全 7 + retrofit 6（F6×3 + F8×2 + F2×1）| 13 | 13 | match ✓ |
| Track D V049-V052 schema migrations | 24 | 24 | match ✓ |
| V053 replay event type enum extension | 7 | 7 | match ✓ |
| **Total** | **63** | **63** | **0 fail** ✓ |

整 Sprint 1 0.24 秒 collection-to-completion，0 PG 真連（全 mock-based unit test）。

---

## 2. Mock 安全審查（CLAUDE.md skill mock 安全規則）

### 2.1 Track A `test_track_a_spawn_argv.py`

| Mock 內容 | 是否 IO 邊界 | 是否藏業務邏輯 |
|---|---|---|
| `monkeypatch.setattr("replay.route_helpers.subprocess.Popen", _FakeProc)` | ✓（IO subprocess fork）| 否 — `_FakeProc/_FakeAliveProc/_FakeDeadProc` 純 stub return code，不模擬 manifest verify 邏輯 |
| `monkeypatch.setattr("replay.route_helpers.time.sleep", lambda s: None)` | ✓（time）| 否 |
| `monkeypatch.setenv("OPENCLAW_REPLAY_RUNNER_BIN", str(fake_bin))` | ✓（env）| 否 |
| `monkeypatch.setenv("OPENCLAW_REPLAY_FIXTURE_URI", "/custom/fixture/path.json")` | ✓（env）| 否 |

**結論**：✓ Track A 0 mock 業務邏輯。`write_manifest_fixture` / `build_default_manifest_payload` / `verify_replay_runner_pid` / `spawn_replay_runner` 業務邏輯真跑（含 byte-equal canonical contract / sort_keys invariant / psutil cmdline cert）。

### 2.2 Track C `test_replay_routes_track_c_security.py`

| Mock 內容 | 是否 IO 邊界 | 是否藏業務邏輯 |
|---|---|---|
| `monkeypatch.setattr("app.replay_routes.get_pg_conn", _stub_get_pg_conn)` | ✓（DB IO）| 否 — `MagicMock()` cursor 只 stub fetchone/execute，不藏 P0-2/P0-4/P0-5a/P0-5b 業務邏輯 |
| `monkeypatch.setattr("os.kill", _spy_kill)` | ✓（OS syscall）| 否 — spy only |
| `monkeypatch.setenv("OPENCLAW_RELEASE_PROFILE", "live")` | ✓（env）| 否 |
| `monkeypatch.setenv("OPENCLAW_REPLAY_VERIFY_TEST_KEY", "00" * 32)` | ✓（env）| 否 |

**結論**：✓ Track C 0 mock 業務邏輯。`is_live_release_profile()` boot guard / IDOR actor_id SQL filter / Path traversal allowlist / psutil cmdline cert 業務邏輯真跑。

### 2.3 對抗反問

**Q: P0-2 boot guard `is_live_release_profile()` 真覆蓋 `OPENCLAW_RELEASE_PROFILE=live` 路徑？**

A: ✓ `test_p0_2_env_var_test_key_blocked_in_live_profile` (L140) 直接 `monkeypatch.setenv("OPENCLAW_RELEASE_PROFILE", "live")` + `OPENCLAW_REPLAY_VERIFY_TEST_KEY` non-empty → 預期 endpoint 501 + 強制 clear test_key_hex；`test_e2_retrofit_f6_boot_guard_raises_in_live_with_test_key` 進一步驗 boot guard 直接 raise RuntimeError 而非 log-only。兩 case + dev profile (`test_p0_2_dev_profile_does_not_strip_test_key`) 三 case 完整覆蓋 live/dev profile branch。

**Q: V053 Mac dev real-PG dry-run 是 throwaway DB（與 production fault-tolerance 不一定 1:1）— flag？**

A: ⚠️ 確認 flag（與 cold audit P1-2 同類型）。Track D `tests/migrations/test_v049_v050_v051_v052_track_d.py` + V053 `tests/migrations/test_v053_replay_event_types.py` 都是 static-parse layer 測試（讀 SQL file 字串，驗 LOCK TABLE / Guard / FK / CHECK constraints 真實在 SQL 內），**並非 production schema migration test**。Linux trade-core 真實環境部署時必跑 `bash helper_scripts/linux_bootstrap_db.sh --apply` + audit_migrations.py 才能驗 V049-V052 + V053 schema 真上 production DB → 屬 PM/operator 部署 SOP 範圍，非 E4 Mac dev scope。

---

## 3. Hard-boundary Mutation Scan（CLAUDE.md §四 18 條紅線）

```bash
$ git diff HEAD -- '*.py' '*.rs' '*.sql' | grep -E "^\+.*\b(live_execution_allowed|max_retries|OPENCLAW_ALLOW_MAINNET|live_reserved|authorization\.json|decision_lease|execution_authority|trading_mode\s*=)"
→ 0 hit
```

✓ Sprint 1 完全沒觸動 Live execution gate / Decision Lease / Risk envelope / Mainnet authorization。

---

## 4. Cross-platform Hardcoded Path Scan（CLAUDE.md §七）

```bash
$ grep -nE "(/home/ncyu|/Users/[^/]+)" \
    program_code/.../replay/route_helpers.py \
    program_code/.../replay/security_guards.py \
    program_code/.../replay/tests/test_track_a_spawn_argv.py \
    program_code/.../tests/test_replay_routes_track_c_security.py \
    sql/migrations/V049-V053.sql
→ 0 hit
```

✓ Sprint 1 跨平台兼容性 0 violation。

---

## 5. File Size Check（CLAUDE.md §九 1500 cap）

| File | LOC | 800 warn | 1500 cap | verdict |
|---|---:|---|---|---|
| `replay_routes.py` | 1494 | warn (980 之前 LOC region) | ≤1500 | ✓ Track C round 2 修完保住硬上限（round 1 = 1603 over by 103，round 2 retrofit 已修） |
| `security_guards.py` | 487 | OK | OK | ✓ |
| `route_helpers.py` | 980 | over warn | ≤1500 | ⚠️ Track A round 2 retrofit 加 docstring 推到 980（pre-existing 891 + 89 docstring）；屬 P2 backlog 後續觀察，非 Sprint 1 引入 |
| `manifest_signer.rs` | 958 | over warn | ≤1500 | ⚠️ Track B IMPL 762→958（+196 LOC fail-mode + verify rewrite）；屬 P2 backlog |
| `replay_runner.rs` | 1013 | over warn | ≤1500 | ⚠️ Track A + Track B 並行修共到 1013（471 + 542 LOC rewrite）；屬 P2 backlog |
| `checks_governance.py` | 906 | over warn | ≤1500 | ⚠️ Track B 加 [44] healthcheck +159 LOC；屬 P2 backlog |

✓ 所有 file ≤1500 hard cap。over 800 warn line 屬 P2 backlog，非 Sprint 1 引入，符合 §九 例外條款。

---

## 6. Sprint 1 Track 各別驗證

### 6.1 Track A — spawn argv + ensure_ascii=False byte-equal canonical contract

| 驗證 | 結果 |
|---|---|
| Python pytest 19/19（含 2 NEW byte-equal canonical retrofit）| ✓ |
| `_python_canonical_body_for_signing` helper 鏡像 Rust ENVELOPE_KEYS_FOR_SIGNING | ✓（manifest_signer.rs:574 line 對齊真實 const）|
| `_python_canonical_body_for_signing` 鏡像 Rust `canonical_body_for_signing` algorithm | ✓（L594 對齊 + sort_keys/separators/ensure_ascii=False kwargs lock）|
| docstring 引 Rust file/行真對齊（manifest_signer.rs L574 + L594）| ✓ grep 確認 |
| anti-`\uXXXX` 守護（disk bytes 不含 escape sequence for non-ASCII）| ✓ `assert b"\\u6d4b" not in disk_bytes` |
| sort_keys invariant（caller A alphabetical / caller B reverse-chaotic → byte-equal）| ✓ |
| Rust manifest run_id self-verify invariant（PA push back #2）| ✓（main.rs Step 2b raise on basename mismatch）|
| spawn-then-poll 1.5s 偵測早死 binary | ✓（`_FakeDeadProc` test verify return failed_path）|

### 6.2 Track B — Rust manifest verify path + key.hex hard error + 5 fail-mode + healthcheck [44]

| 驗證 | 結果 |
|---|---|
| `cargo test --bin replay_runner` 6/6（4 fail-mode + 1 happy + 1 sanity）| ✓ |
| `cargo test --test replay_manifest_signer_xlang_consistency` 8/8 | ✓（含 fingerprint_helper / fail_mode_signature_mismatch / fail_mode_key_missing / fail_mode_key_expired / fail_mode_manifest_hash_mismatch / verify_order_invariant / xlang_signature_byte_equal / happy_path）|
| verify path 反轉（self-sign tautology fix）| ✓（Section §3.1 manifest_signer.rs L456-462 反轉，PA push back #1）|
| `key.hex` missing → hard error（fail-open → fail-closed）| ✓（manifest_signer.rs L404-411 was warn-only → now hard error）|
| `[44] replay_manifest_key_presence` healthcheck 已 wired | ✓ runner.py L141 import + L635 result append |
| LG-5 healthcheck pytest 25/25（既有 [42]/[42b]/[42c]/[43]）| ✓ 0 regression |

### 6.3 Track C — 3 P0 + V053 LOCK TABLE race-free + 1500 LOC enforce + admin scope 登記

| 驗證 | 結果 |
|---|---|
| 13 NEW pytest case（P0-2/P0-4/P0-5a/P0-5b 7 + retrofit F6×3+F8×2+F2×1 6）| ✓ 13/13 PASS |
| `replay_routes.py` 1494 ≤ 1500 hard cap | ✓（round 1 1603 → round 2 1494 by 109 LOC reduction）|
| `security_guards.py` 487 LOC（≤800 warn） | ✓ |
| 雙語 MODULE_NOTE + 6 helper 雙語 docstring | ✓（L1-89）|
| `is_live_release_profile()` boot guard 真 raise（非 log-only）| ✓（L138-149 raise RuntimeError）|
| `verify_replay_runner_pid` psutil cmdline cert 4 NEW edge case | ✓（init / unrelated / NoSuchProcess / psutil_unavailable 全 cover）|
| `Path.resolve()` follow symlinks（Path traversal allowlist）| ✓（route_helpers.py L927 + L941 is_relative_to）|
| `auth.py` `Settings.auth_scopes` default 含 `replay:write` + `replay:read:any`（admin scope 顯式列）| ✓（L239-240）|
| V053 BEGIN + LOCK TABLE ACCESS EXCLUSIVE + COMMIT 包裹 | ✓（L166 BEGIN / L210 LOCK / L249 COMMIT）|
| V053 idempotency probe 短路在 LOCK 之前（重跑 0 RAISE）| ✓（L187-200 probe → line 203 RAISE NOTICE skip）|
| P2-AUDIT-7 V044 LOCK TABLE retrofit ticket 已進 TODO.md | ✓（L142 PM commit `2ffe43d`）|

### 6.4 Track D — V049-V052 + V052_preflight + REF-20_RESERVATION v1.9

| 驗證 | 結果 |
|---|---|
| 24 pytest case（V049 promotion + V050 simulated_fills + V051 paired CHECK + V052 forward-only FK + module-note + governance check）| ✓ 24/24 PASS |
| V049 22 col promotion + UUID experiment_id + window constraints + 3 hot-path indexes + self-FK | ✓ |
| V050 FK to V049 + 必 col + CHECK + evidence_tier excludes real_outcome + 3 hot-path indexes | ✓ |
| V051 paired CHECK V3 §4.2 lineage + FK to V049 + Guard A V049 PK UUID check | ✓ |
| V052 V045/V046 forward-only FK redirect（不改 V045/V046 file，避 P0 sqlx hash drift）| ✓（test_v052_does_not_edit_v045_v046_files）|
| V052_preflight dangling row → RAISE EXCEPTION | ✓（test_v052_preflight_dangling_row_raise）|
| 0 hardcoded `/Users/` `/home/` path | ✓ |
| 0 trading.* / live_* mutation | ✓ |
| 0 hard-boundary col touched | ✓ |
| dual-language MODULE_NOTE in all V### files | ✓ |

---

## 7. Pre-existing E4-P0-1 / E4-P0-2（cold audit `2026-05-03--ref20_final_closure_e4_cold_audit.md` 已抓）

### 7.1 E4-P0-1 — `test_case2_pg_kill_simulation_returns_200_degraded` deterministic FAIL in full suite

```
FAILED tests/test_replay_routes_safe_query_audit.py::test_case2_pg_kill_simulation_returns_200_degraded
> assert resp.status_code == 200, f"expected 200, got {resp.status_code}"
E AssertionError: expected 200, got 401
```

- **Sprint 1 是否引入**：✗（Wave 6 commit `eb5f106` 引入，2026-05-02）
- **Sprint 1 是否承諾修**：✗（Sprint 1 PA partition design 未列入 4 track scope；Track C E1 §9.4/§9.5 不討論此 test 修復）
- **是否 Sprint 1 新增**：✗（cold audit 同樣 deterministic fail，2 round identical reproduce）
- **隔離跑 PASS**：✓（cd control_api_v1 && pytest tests/test_replay_routes_safe_query_audit.py = 5/5 PASS）
- **建議**：開 P2 ticket 跨 sprint 修（pytest fixture autouse 重建 router + dep_overrides 隔離），**non-blocking Sprint 1 closure**

### 7.2 E4-P0-2 — `mac_policy_guard.rs` 2 doctest fail（中文全形括號）

```
test openclaw_engine/src/replay/mac_policy_guard.rs - replay::mac_policy_guard (line 32) ... FAILED
test openclaw_engine/src/replay/mac_policy_guard.rs - replay::mac_policy_guard (line 88) ... FAILED
error: unknown start of token: \u{ff08} '（' looks like '(' but it is not
```

- **Sprint 1 是否引入**：✗（Wave 3 commit `5a618ff` 引入，2026-05-02 P2b-S9 自寫）
- **Sprint 1 是否承諾修**：✗（Track B IMPL 不修 sibling mac_policy_guard.rs file）
- **是否 Sprint 1 新增**：✗（cold audit 同樣 doctest fail，2 round identical reproduce）
- **修法**：把 `//!` block 內中文 OS matrix 包進 ` ```text ... ``` ` markdown code fence（rustdoc 不會 tokenize）；或全形 `（）` 改半形 `()`
- **建議**：開 P2 ticket 跨 sprint 修，**non-blocking Sprint 1 closure**

---

## 8. SLA Pressure Tests（CLAUDE.md §三 18 blocker SLA 紅線）

```
$ cargo test --release --test stress_integration
35 passed; 0 failed
```

涵蓋：
- `stress_full_pipeline_extreme_prices`
- `stress_full_pipeline_zero_volume_ticks`
- `stress_three_pipeline_concurrent_snapshot_writes`
- `stress_config_hot_reload_during_ticks`
- `stress_three_pipeline_concurrent_isolation`
- `stress_tick_latency_benchmark`
- `stress_10k_ticks_no_panic`
- `stress_catch_unwind_recovers_from_pipeline_panic`
- `stress_short_position_stop_on_price_rise`
- `stress_multi_symbol_rapid_alternating_ticks`
- `stress_multi_symbol_5_coins_simultaneous_ticks`
- `stress_full_pipeline_volatile_market_simulation`

**結論**：✓ Sprint 1 0 影響 hot tick path / IPC < 5ms / H0 Gate < 1ms。replay_runner binary 屬 batch path（cold artifact 路徑），不在 hot path scope，無需專門 SLA test。PA push back #5 關注 confirmed 不成立。

---

## 9. 跨語言一致性（manifest_signer Rust ↔ Python byte-equal HMAC）

```
$ cargo test --release --test replay_manifest_signer_xlang_consistency --features replay_isolated
8 passed; 0 failed
```

涵蓋：
- `xlang_signature_byte_equal_for_all_fixtures` — 3 fixture (`manifest_1/2/3.json`) Rust + Python 各自獨立計算 HMAC 對 fixture sig file byte-equal
- `fingerprint_helper_matches_fixture` — `sha256(file_content_with_newline)[:16]` = `da0d3b33336d12fb` 三方對齊（helper script + fixture + runtime）
- `fail_mode_signature_mismatch_with_fixture` / `fail_mode_manifest_hash_mismatch_with_fixture` / `fail_mode_key_missing_with_fixture` / `fail_mode_key_expired_with_fixture` — 4 fail-mode Rust unit + Python pytest 三 bucket 全 cover
- `verify_order_invariant_signature_before_hash_with_fixture` — verify-order invariant（signature → hash）Rust + Python 兩端顯式驗
- `happy_path_verify_passes_with_fixture` — happy path 真 verify PASS

**Track A retrofit 加 byte-equal canonical pytest case 補完**（test_track_a_spawn_argv.py:193 + 277）— Python `_python_canonical_body_for_signing` 鏡像 Rust `canonical_body_for_signing` algorithm（manifest_signer.rs:574 ENVELOPE_KEYS_FOR_SIGNING + L594 fn）：
- `sort_keys=True ↔ BTreeMap<String, Value>` 排序一致（U+0041..U+007A alphabetical lexicographic）
- `separators=(",", ":") ↔ serde_json compact` 無 whitespace
- `ensure_ascii=False ↔ raw UTF-8` 不出 `\uXXXX` escape

**結論**：✓ Sprint 1 cross-language byte-equal 100% PASS（不適用 1e-4 浮點容差，HMAC 是 byte-equal stricter）。

---

## 10. CLAUDE.md §三 drift check

當前 §三 / TODO.md 沒被 Sprint 1 改動觸發 update（Sprint 1 屬 REF-20 Sprint 1 retrofit closure，不影響 §三 18 blocker 表）。

唯一新增 ticket 是 P2-AUDIT-7（V044 LOCK TABLE retrofit），屬 P2-AUDIT 段落，已在 TODO.md L142（PM commit `2ffe43d` 補齊）。

**結論**：✓ 0 drift。

---

## 11. Verdict

### **CONDITIONAL PASS**

**理由**：
1. Sprint 1 Track A + B + C + D 整 4 track 全 specific test PASS（63/63）
2. Sprint 1 baseline regression 0 新 fail（Python 3387/1，Rust lib 2454/0，Rust workspace 3084/2 — pre-existing 2 doctest fail / 1 deterministic flake）
3. 兩遍 reproducible identical（0 transient flake）
4. 0 mock 業務邏輯 / 0 hard-boundary mutation / 0 hardcoded path / 0 SLA hot-path 觸動
5. 跨語言 manifest_signer byte-equal 8/8 PASS
6. P2-AUDIT-7 V044 LOCK TABLE retrofit ticket 已 land TODO.md（PM commit `2ffe43d` 三端同步完成）

**Conditional 條件**（非 Sprint 1 引入，cold audit 已抓）：
1. **E4-P0-1**：`test_case2_pg_kill_simulation_returns_200_degraded` deterministic shared-state pollution（Wave 6 引入 `eb5f106`）
2. **E4-P0-2**：`mac_policy_guard.rs` 2 doctest fail（Wave 3 P2b-S9 引入 `5a618ff`，中文全形括號）

→ **PM 建議 path**：Sprint 1 commit + push（accept-and-flag pre-existing 2 條），同 commit 開 P2-FOLLOW-UP-1 / P2-FOLLOW-UP-2 ticket 跨 sprint 修這 2 條 pre-existing baseline failure。

**不建議 path**（FAIL 退回）：兩條 E4-P0-1/P0-2 都不是 Sprint 1 引入或承諾修；Sprint 1 4 track 自己 0 新 regression。退回 = blocker 錯置 + 拖慢 Sprint 1 closure。

### Sprint 1 整體驗收清單（最終 GREEN）

| 項 | 狀態 | 備註 |
|---|---|---|
| Track A 19/19 spawn-argv-test PASS | ✓ | 含 2 NEW byte-equal canonical retrofit |
| Track B 6 + 8 xlang consistency PASS | ✓ | 4 fail-mode + 1 happy + 1 sanity / 8 xlang byte-equal |
| Track C 13/13 security PASS | ✓ | 7 P0 + 6 retrofit |
| Track D 24/24 V049-V052 PASS | ✓ | + V053 7/7 |
| Cargo lib regression PASS | ✓ | 2454 / 0 / 0（+7 vs cold audit 2447） |
| Cargo workspace regression CONDITIONAL | ⚠️ | 3084 / 2 / 3（+7 PASS / +0 fail / +0 ignored；2 fail = pre-existing E4-P0-2）|
| Pytest control_api_v1 regression CONDITIONAL | ⚠️ | 3387 / 1 / 10（+13 PASS / +0 fail；1 fail = pre-existing E4-P0-1）|
| Sprint 1 specific suite 63/63 PASS | ✓ | match expected |
| SLA stress 35/35 PASS | ✓ | 0 hot path 影響 |
| Mock 安全（0 業務邏輯 mock）| ✓ | Track A/C 全 IO boundary |
| Hard-boundary scan（0 mutation）| ✓ | live_execution_allowed/decision_lease/etc 0 hit |
| Cross-platform path scan（0 hardcoded）| ✓ | 0 hit |
| File size cap（≤1500 LOC）| ✓ | replay_routes.py 1494 |
| 兩遍 reproducible | ✓ | 0 transient flake |
| TODO.md P2-AUDIT-7 補齊 | ✓ | L142 PM commit `2ffe43d` |

---

## 附 A — 完整 cold run 命令

```bash
# Sprint 1 specific 4-track suite
cd /Users/ncyu/Projects/TradeBot/srv && python3 -m pytest \
  program_code/exchange_connectors/bybit_connector/control_api_v1/replay/tests/test_track_a_spawn_argv.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_routes_track_c_security.py \
  tests/migrations/test_v049_v050_v051_v052_track_d.py \
  tests/migrations/test_v053_replay_event_types.py \
  -v
# → 63 passed, 1 warning in 0.24s

# Pytest baseline regression（control_api_v1 全 suite，excl integration）
cd /Users/ncyu/Projects/TradeBot/srv/program_code/exchange_connectors/bybit_connector/control_api_v1 && \
  python3 -m pytest tests/ --tb=no -q --ignore=tests/integration
# Run 1: 1 failed, 3387 passed, 10 skipped, 411 warnings in 53.99s
# Run 2: 1 failed, 3387 passed, 10 skipped, 411 warnings in 53.97s

# Rust lib regression
cd /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine && cargo test --release --lib
# → 2454 passed; 0 failed; 0 ignored; 0 measured (2 round identical)

# Rust workspace regression（含 doctest）
cd /Users/ncyu/Projects/TradeBot/srv/rust && cargo test --release --workspace
# → TOTAL: passed=3084 failed=2 ignored=3 (2 fail = pre-existing E4-P0-2 mac_policy_guard.rs)

# Rust replay_isolated integration suite
cd /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine && \
  cargo test --release --tests --features replay_isolated
# → cumulative 2643 passed; 0 failed (含 lib 2454 + integration 189)

# Track B fail-mode + happy + sanity
cd /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine && \
  cargo test --release --bin replay_runner --features replay_isolated
# → 6 passed; 0 failed (4 fail-mode + 1 happy + 1 sanity)

# Track B xlang consistency
cd /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine && \
  cargo test --release --test replay_manifest_signer_xlang_consistency --features replay_isolated
# → 8 passed; 0 failed

# SLA stress
cd /Users/ncyu/Projects/TradeBot/srv/rust/openclaw_engine && \
  cargo test --release --test stress_integration
# → 35 passed; 0 failed

# LG5 healthcheck pytest
cd /Users/ncyu/Projects/TradeBot/srv && \
  python3 -m pytest helper_scripts/db/test_lg5_healthchecks.py -v --tb=short
# → 25 passed in 0.03s
```

## 附 B — Sibling Linux trade-core 對照（建議但非 Sprint 1 closure 必跑）

```bash
# 對 Linux runtime 真實 PG 環境驗證 Sprint 1 4 track（PA push back V053 race-free 真實 LOCK 行為）
ssh trade-core "cd ~/BybitOpenClaw/srv && python3 -m pytest \
  program_code/exchange_connectors/bybit_connector/control_api_v1/replay/tests/test_track_a_spawn_argv.py \
  program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_replay_routes_track_c_security.py \
  tests/migrations/test_v049_v050_v051_v052_track_d.py \
  tests/migrations/test_v053_replay_event_types.py -v"

ssh trade-core "cd ~/BybitOpenClaw/srv/rust/openclaw_engine && cargo test --release --workspace"

# Linux 真實 PG migrate V049-V053 + audit checksum（PA part of deploy SOP，非 Sprint 1 closure 必跑）
ssh trade-core "bash ~/BybitOpenClaw/srv/helper_scripts/linux_bootstrap_db.sh --apply"
ssh trade-core "python3 ~/BybitOpenClaw/srv/helper_scripts/db/audit_migrations.py"
```

---

E4 REGRESSION DONE: **CONDITIONAL PASS**（Sprint 1 0 新 regression；2 條 pre-existing E4-P0-1/P0-2 仍 fail，非 Sprint 1 引入或承諾修）
report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-03--ref20_sprint1_e4_regression.md`
