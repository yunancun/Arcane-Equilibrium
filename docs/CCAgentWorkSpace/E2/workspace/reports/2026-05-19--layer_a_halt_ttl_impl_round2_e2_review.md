## E2 PR Adversarial Review (Round 2) — P0-ENGINE-HALTSESSION-STUCK-FIX Layer A · 2026-05-20

**Author**: E2
**Date**: 2026-05-20
**Round 1 review**: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-19--layer_a_halt_ttl_impl_e2_review.md` (verdict RETURN, 4 MUST-FIX + 3 SHOULD-FIX)
**E1 Round 2 report**: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-19--layer_a_halt_ttl_impl_round2_report.md`
**Branch state**: Dirty Mac worktree; HEAD at 7fb46387; uncommitted Layer A IMPL.
**Independent verification**: cargo test re-run (3264/0/3 PASS), Python writer 20/0 PASS, Linux PG integration **independently re-run** (3 rows INSERT + idempotent + clear_path↔event_type mapping all verified), source path/grep cross-check, multi-session race 5-check.

---

## 1. Verdict + Counts

**VERDICT: APPROVE → PASS to E4**

| Severity | Count |
|---|---|
| MUST-FIX-RETURN | 0 |
| SHOULD-FIX-FOLLOWUP | 0 |
| OBSERVATION | 3 |

All 6 Round 1 + Round 2 fixes verified closed. P1-16 invariant preserved (3/0 PASS). 9 + 16 hard boundaries 0 violation. Cross-platform path PASS. File sizes compliant. Multi-session race PASS. Round 2 IMPL is mergeable as-is; observations are informational and tracked for follow-up.

---

## 2. Fix-by-Fix Verification

### MUST-FIX-1 (CRITICAL): record_halt_cleared event_type mapping — **VERIFIED CLOSED**

**Source review** (`rust/openclaw_engine/src/halt_audit.rs:114-128`):

```rust
fn event_type_for_clear_path(clear_path: &str) -> &'static str {
    match clear_path {
        "auto_ttl" => "halt_session_auto_cleared",
        "ipc_resume" | "ipc_reset" | "ipc_system_mode_shadow" => "halt_session_manual_cleared",
        unknown => {
            error!(clear_path = unknown, "halt_audit: unknown clear_path → fallback halt_session_manual_cleared / 未知 clear_path，回退 manual_cleared");
            "halt_session_manual_cleared"
        }
    }
}
```

Helper correctly maps all 4 official paths + fail-safe defaults unknown to `manual_cleared` (not `auto_cleared`, the conservative direction — won't mislabel manual as auto).

**4 production caller sites grep + verified** (`record_halt_cleared` only — 6 hits total but 2 are in tests and 1 is module decl):

| File:Line | Caller | Path argument | Expected event_type |
|---|---|---|---|
| `event_consumer/handlers/lifecycle.rs:62` | `handle_resume` | `"ipc_resume"` | manual_cleared |
| `event_consumer/handlers/lifecycle.rs:156` | `handle_reset` | `"ipc_reset"` | manual_cleared |
| `tick_pipeline/commands.rs:1749` | `set_system_mode` ShadowOnly arm | `"ipc_system_mode_shadow"` | manual_cleared |
| `tick_pipeline/commands.rs:1850` | `check_and_clear_halt_expired` (auto-clear) | `"auto_ttl"` | auto_cleared |

All 4 sites pass literals matching helper allowlist. No production caller passes `"manual"` or any non-allowlist value.

**Unit tests**:
- `halt_audit::tests::test_event_type_for_clear_path_mapping` covers 4 official + 2 unknown (`future_unknown_path`, `""`).
- `halt_audit::tests::test_record_halt_cleared_event_type_mapping` writes JSONL via real `record_halt_cleared` call and verifies the `event` field per `clear_path` for all 4 paths + 1 unknown.

Both tests pass independently.

### MUST-FIX-2 (HIGH): paper_state restore halt_kind / halt_set_ts_ms — **VERIFIED CLOSED**

**Source review** (`rust/openclaw_engine/src/event_consumer/paper_state_restore.rs:185-315`):

`restore_halt_state_from_snapshot` is a `pub(crate) async fn` that:
1. Resolves `$OPENCLAW_DATA_DIR/pipeline_snapshot_<kind_tag>.json` (kind_tag = `pipeline.pipeline_kind.db_mode()`).
2. Reads file via `std::fs::read_to_string`; fail-soft on missing/IO error.
3. Parses as `serde_json::Value` (loose schema — avoids dragging PipelineSnapshot strict parsing into halt path).
4. Reads `mode_snapshots.<kind_tag>.halt_kind` + `.halt_set_ts_ms` + `.paper_paused` + `.session_halted`.
5. Restore rule: `halt_kind=Some(k) + halt_set_ts_ms > 0` → write pipeline state; `halt_kind=Some(k) + halt_set_ts_ms == 0` → fail-soft cold (defensive); `halt_kind=None` → no-op.

**Path match verification** (writer side ↔ reader side):
- **Emission path** (`commands.rs:1671-1691`, `snapshot()` method): writes to `mode_snapshots.<self.pipeline_kind.db_mode()>.halt_kind` + `.halt_set_ts_ms`.
- **File location** (`bootstrap.rs:906`): `pipeline_snapshot_{kind_tag}.json` in `$OPENCLAW_DATA_DIR` (or `/tmp/openclaw` fallback).
- **Reader** (`paper_state_restore.rs:187-188`): reads identical path + identical JSON path. **MATCH CONFIRMED**.

**Ordering verified** (`bootstrap.rs:323-328 → 947`): restore runs BEFORE initial snapshot write. Correct — restores from previous run's data before it's overwritten.

**5 integration tests** (cross-restart roundtrip + 3 fail-soft modes):
- `test_halt_state_restored_after_restart` — engine 1 snapshot → engine 2 restore → TTL fires from original T0
- `test_restore_halt_state_missing_snapshot_is_cold_start` — fail-soft 1
- `test_restore_halt_state_corrupted_json_is_cold_start` — fail-soft 2
- `test_restore_halt_state_kind_set_but_ts_zero_treated_as_cold` — defensive
- (also `test_snapshot_roundtrip_persist_halt_state` from Round 1 — confirms emission side)

All 5 pass. Fail-soft contract covers 4 of 4 failure modes I checked (missing file, corrupted JSON, missing mode_snapshots entry, halt_kind=null/None).

**Bootstrap wire-up verified** (`bootstrap.rs:325-328`):
```rust
// MUST-FIX-2 Round 2（2026-05-19/20）：從上輪 pipeline_snapshot 還原 halt_kind / halt_set_ts_ms
paper_state_restore::restore_halt_state_from_snapshot(&mut pipeline).await;
```

Chained after `restore_paper_counters`. P1-5 A2 `restore_checkpoint` (also halt-adjacent) runs inside `restore_paper_counters` separately — no order/dependency conflict.

### MUST-FIX-3 (HIGH): Python tail-writer + Linux PG integration — **VERIFIED CLOSED**

**Files created**:
- `helper_scripts/canary/halt_audit_pg_writer.py` (389 LOC)
- `helper_scripts/canary/test_halt_audit_pg_writer.py` (362 LOC)
- `helper_scripts/cron/halt_audit_pg_writer_cron.sh` (87 LOC)

**Functional review** (writer):
- Tails `halt_audit.log` JSONL → INSERT into `learning.governance_audit_log`. ✅
- Cursor tracking via state file `halt_audit_pg_writer_state.json`. ✅
- jsonschema validation against `halt_audit_schema.json` — fail-soft pass-through when schema absent (acceptable design; Linux deploy will pick schema up). ✅
- `event_type` derived from row payload + allowlist check (lines 234-241). ✅
- `decided_by = 'engine.halt_audit'` (line 268). ✅
- `rule_failures = '{}'::text[]` + `lease_revoke_triggers = '{}'::text[]` (line 258). ✅
- Idempotency: `WHERE NOT EXISTS` pattern on (event_type, process_pid, ts_ms) composite (lines 252-264). ✅
- File truncation/rotation handled (lines 301-308 rewind cursor if > file_size). ✅
- V098 not yet deployed → exit 0 + cursor NOT advanced (lines 338-344) — waits for V098 land. ✅

**Mac unit tests**: 20/0 PASS independently re-run.

**Linux PG integration — INDEPENDENTLY VERIFIED by E2** (`ssh trade-core 'bash /tmp/halt_audit_pg_writer_integration.sh'`):
```
=== writer integration test pid=881779230183 ==
fake halt_audit.log 3 lines written
[INFO] tail done: inserted=3 skipped=0 new_offset=902
writer rc=0
         event_type          | kind             | clear_path  | process_pid
-----------------------------+------------------+-------------+--------------
 halt_session_auto_cleared   | daily_loss       | auto_ttl    | 881779230183
 halt_session_manual_cleared | session_drawdown | ipc_resume  | 881779230183
 halt_session_set            | daily_loss       |             | 881779230183
ROW COUNT: 3 (expected 3)
[2nd run]: no new rows; cursor=902
ROW COUNT after second run: 3 (expected 3 — idempotent)
DELETE 3
=== integration test PASS ===
```

3 real INSERTs + idempotency + event_type↔clear_path mapping verified by independent SSH execution. **Not just E1 mock**.

**Cron wrapper** (`halt_audit_pg_writer_cron.sh`): uses `$HOME` / env vars; no hardcoded `/home/ncyu` or `/Users/*`. Reads secrets from `$OPENCLAW_SECRETS_ROOT/environment_files/basic_system_services.env`. mkdir-based lock prevents overrun. Source-only — operator manually adds to crontab.

**SCRIPT_INDEX.md updated** — verified entries for `halt_audit_pg_writer.py` + `_cron.sh` + `test_halt_audit_pg_writer.py` present with proper description (lines 5-7 of new 2026-05-20 section).

### MUST-FIX-4 (MEDIUM): risk_config_tests.rs split — **VERIFIED CLOSED**

**Before**: `risk_config_tests.rs` = 2076 LOC (over 2000 hard cap)
**After**:
- `risk_config_tests.rs` = 1917 LOC (under cap)
- `risk_config_halt_ttl_tests.rs` = 182 LOC (new sibling)

**Module registration**: `risk_config.rs:1303-1304`:
```rust
#[path = "risk_config_halt_ttl_tests.rs"]
mod halt_ttl_tests;
```

Path-relative `mod` declaration correctly under `#[cfg(test)]` scope.

**Test count preserved**: 9 tests in sibling, all run via `cargo test --lib config::risk_config::halt_ttl_tests`:
- 7 from independent halt TTL validate (drawdown, daily_loss 24h, 7d, above 7d, zero accepted, floor, default)
- 2 from TOML production validation (`test_live_daily_loss_sticky_enforcement`, `test_demo_paper_daily_loss_ttl_24h`)

Independent run: 9 passed / 0 failed / 0 ignored.

R2-H4 hypothesis **DISPROVED**: tests are not silently skipped — visible via `cargo test --lib config::risk_config::halt_ttl_tests`.

### E3 MEDIUM-1: NaN guard — **VERIFIED CLOSED**

**Helper** (`halt_audit.rs:95-99`):
```rust
fn json_number_or_null(value: f64) -> serde_json::Value {
    serde_json::Number::from_f64(value)
        .map(serde_json::Value::Number)
        .unwrap_or(serde_json::Value::Null)
}
```

`serde_json::Number::from_f64(NaN | ±Inf)` returns `None` (verified by serde_json docs) → helper returns `Value::Null`. No panic.

**All f64 fields in `record_halt_set` JSON wrapped** (grep + verified each):
- `peak_balance` (line 283) ✅
- `current_balance` (line 284) ✅
- `session_drawdown_pct` (line 285) ✅
- `loaded_drawdown_threshold` (line 288) ✅
- `loaded_daily_loss_threshold` (line 289) ✅
- Plus `paper_state_balance_history` peak + current entries (line 242-244 via `paper_state_balance_history` helper). ✅

**`record_halt_cleared` JSON has zero f64 fields** (only u64 ts_ms/elapsed + strings). No additional guard needed.

**`tracing::info!` macro at line 310-313**: uses f64 via `Display` (handles NaN as "NaN" string) — not a panic source. No additional guard needed.

**Unit tests**:
- `test_json_number_or_null_nan_inf_safe` — NaN/±Inf → Null; finite preserved as Number; 0/negative/extreme finite all preserved.
- `test_record_halt_set_with_nan_balance_does_not_panic` — full end-to-end with `PaperState::new(f64::NAN)`; writes JSONL line; verifies `peak_balance` or `current_balance` is null in output.

Both pass.

R2-H1 hypothesis **DISPROVED**: no off-by-one. Helper unconditionally maps non-finite → Null.

### SHOULD-FIX (spec §6.3): test_2026_05_19_incident_replay — **VERIFIED CLOSED**

**Location**: `rust/openclaw_engine/src/tick_pipeline/tests/halt_ttl.rs:462-609`

**Coverage** (14-step replay per spec §6.3):
- Step 1: Construct TickPipeline + demo RiskConfig (session_drawdown_max_pct=25, daily_loss_max_pct=15, daily_loss_halt_ttl_ms=24h, drawdown_halt_ttl_ms=0 sticky) ✅
- Step 2-5: Manually classify DAILY LOSS reason → `record_halt_set` → assert kind=DailyLoss + write JSONL set line + verify schema_version=1 + kind=daily_loss + reason + halt_set_ts_ms ✅
- Step 6: Advance 1h → on_tick → still paused ✅
- Step 7-8: Advance 24h+1s → on_tick → auto-clear → verify cleared line elapsed_ms ∈ [86399000, 86401000] + event_type=halt_session_auto_cleared + clear_path=auto_ttl ✅
- Step 9-12: Construct SESSION DRAWDOWN halt → advance 7d → still sticky ✅
- Step 13-14: schema_version=1 + pipeline_kind=paper + 6 quant-context field schema present ✅

**Note**: Test is "synthetic-construct" not "archived-snapshot replay". Per spec §6.3 wording ("Construct TickPipeline... Force-inject paper_state"), synthetic is acceptable.

R2-H6 hypothesis **DISPROVED**: test passes legitimately. Timing arithmetic (t0 + ttl + 1000 vs `elapsed >= ttl_ms` semantics) verified correct. State transitions match observed 2026-05-19 incident pattern.

Independent run: PASS.

---

## 3. OOS Additions Verification

### OOS-1: per_symbol_price_pnl.rs test env_lock + RAII guard

**Source review** (`rust/openclaw_engine/src/tick_pipeline/tests/per_symbol_price_pnl.rs:150-173`):

Added before existing test body:
- `let _env_guard = crate::event_consumer::paper_state_restore::env_test_lock();`
- Save `saved_log_env`, clear `OPENCLAW_HALT_AUDIT_LOG`
- `EnvRestoreGuard` struct with `Drop` impl to restore env even on panic

**Test semantics check**:
- Line 244-249: BTC close at 50500 (own price) — **unchanged**
- Line 253-257: ETH fallback to 3000 entry — **unchanged**
- Line 258-262: DOGE fallback to 0.20 entry — **unchanged**
- Line 264-268: position_count==0 — **unchanged**
- Line 269-273: session_halted==true — **unchanged**
- Line 278-283: entry_context_id assertion (V083-FIX-3) — **unchanged**

**Mocked positions / setup values / assertion thresholds**: all original P1-16 invariants verified intact. No scope creep. Pure env-thread-safety isolation.

**Independent P1-16 test run**: 3/0 PASS (test_close_position_at_symbol_market_uses_per_symbol_price + test_close_position_at_symbol_market_fallback_to_entry_when_no_latest_price + test_halt_session_uses_per_symbol_price_not_triggering_tick).

### OOS-2: parse_jsonl_robust helper

**Two implementations**:

1. **Rust test-only** (`tick_pipeline/tests/halt_ttl.rs:31-63`):
   - Used in 2 places within `test_2026_05_19_incident_replay` to handle concurrent multi-thread cargo test writes to same `halt_audit.log`.
   - Production halt_audit.rs `write_jsonl_line` does NOT use this parser — it only writes.
   - Production governance_audit_log writer (Python) uses its own parser.
   - **NOT in production hot path**. Confirmed via grep.
   - Failure semantics: skipped lines never push to `out`; no error swallowing — just best-effort parse.

2. **Python production** (`halt_audit_pg_writer.py:129-165`):
   - This IS production code (the writer's main parsing).
   - Handles edge case: rust engine's `writeln!` is `write_all(json) + write_all("\n")` — multi-process/thread append may interleave → "two JSON on one line" case.
   - Followed by `_validate_row` jsonschema gate + `_insert_row` allowlist gate (event_type + process_pid + ts_ms requirements).
   - Junk data → skipped at validate or INSERT level; cannot INSERT malformed rows.

R2 concern: **Both parsers do not mask real bugs**. They only handle the specific "glued JSON" race; truly malformed input still skipped silently with `seen` accumulator preventing duplicate yields.

---

## 4. Adversarial Hypotheses R2-H1 through R2-H6

| H | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| R2-H1 | NaN guard helper has off-by-one in floating-point comparison | **DISPROVED** | Helper uses `serde_json::Number::from_f64()` which is binary check on bit pattern (NaN/Inf vs finite); no comparison. Test `test_json_number_or_null_nan_inf_safe` covers all 3 non-finite cases + finite preservation. |
| R2-H2 | Python writer INSERT has SQL injection vector | **DISPROVED** | Lines 252-274 use psycopg2 parameterized `%s` placeholders consistently. `payload_json` passed as single bound parameter, NOT string-concatenated. Allowlist check on event_type (lines 234-241) prevents non-standard values. |
| R2-H3 | paper_state_restore wired but fail-loud on corrupt snapshot | **DISPROVED** | All 4 failure modes (missing file / corrupt JSON / missing kind entry / halt_kind=None) return early with `info!` / `warn!` + no panic / no Err returned. Test `test_restore_halt_state_corrupted_json_is_cold_start` proves engine continues cleanly. |
| R2-H4 | clear_path mapping fallback `_` writes wrong event_type | **DISPROVED** | Fallback arm (line 118-126) writes `halt_session_manual_cleared` (the conservative direction). Audit row for unknown path → manual (won't get falsely classified as "auto" which would suggest automation). Plus `tracing::error!` raises operator awareness. Test `test_event_type_for_clear_path_mapping` covers 2 unknown cases. |
| R2-H5 | cargo 3264 count includes silent `#[ignore]` on new tests | **DISPROVED** | `rg #[ignore]` over all 4 new/modified test files: **0 matches**. The 3 ignored count is the same 3 ignored as before (unrelated to this IMPL). |
| R2-H6 | spec §6.3 incident_replay test passes by mistake | **DISPROVED** | Timing arithmetic verified by inspection: `t0 + ttl_24h + 1000` vs `check_and_clear_halt_expired` with `elapsed < ttl_ms { return false }` semantics → `1000 >= 0` ms past ttl → fires. Drawdown 7d sticky verified: `HaltKind::SessionDrawdown` arm at `commands.rs:1813` immediately `return false` regardless of elapsed. State transitions match observed incident. |

Net: **0/6 hypotheses confirmed**. All Round 2 fixes survive adversarial probing.

---

## 5. Compliance Re-Verification

### 16 根原則
- #5「生存 > 利潤」: ✅ preserved (Live D1 sticky + drawdown 三環境 sticky)
- #6「失敗默認收縮」: ✅ preserved (HaltKind::Other fail-safe sticky + NaN guard fail-soft)
- #8「交易可重建可解釋」: ✅ **NOW CLOSED** (Python writer + cron → governance_audit_log INSERT chain verified)

### 9 條安全不變量
- `live_execution_allowed` / `max_retries=0` / `system_mode` / Bybit retCode / `OPENCLAW_ALLOW_MAINNET` / `live_reserved` / `authorization.json` write path / Reconciler / Operator role — **0 violations** across new + modified files
- P1-16 ETHUSDT -17M bps regression — **3/0 PASS** (independently verified)

### CLAUDE.md §九 File Sizes
- `risk_config_tests.rs`: **1917 LOC** (was 2076; now under 2000 cap) ✅
- `risk_config_halt_ttl_tests.rs`: 182 LOC ✅
- `halt_audit.rs`: 687 LOC ✅
- `halt_ttl.rs`: 609 LOC ✅
- `halt_audit_pg_writer.py`: 389 LOC ✅
- `test_halt_audit_pg_writer.py`: 362 LOC ✅
- `halt_audit_pg_writer_cron.sh`: 87 LOC ✅
- Files over 800 LOC (warn): `halt_audit.rs` 687 OK, `commands.rs` 1883 (pre-existing per Round 1)

### Cross-Platform Path
```bash
grep -E '(/home/ncyu|/Users/[^/]+)' \
    rust/openclaw_engine/src/halt_audit.rs \
    rust/openclaw_engine/src/event_consumer/paper_state_restore.rs \
    rust/openclaw_engine/src/tick_pipeline/tests/halt_ttl.rs \
    rust/openclaw_engine/src/config/risk_config_halt_ttl_tests.rs \
    helper_scripts/canary/halt_audit_pg_writer.py \
    helper_scripts/canary/test_halt_audit_pg_writer.py \
    helper_scripts/cron/halt_audit_pg_writer_cron.sh \
    sql/migrations/V098__governance_audit_log_halt_event_types.sql
```
→ **0 hits** across all new/modified files. PASS.

### Chinese-First Comment Style
- All new modules carry MODULE_NOTE with 模塊用途 / 主要函數 / 依賴 / 硬邊界 in Chinese.
- New function docs in Chinese (per `bilingual-comment-style` 中文優先 rule).
- Touched bilingual blocks: handled per skill (keep Chinese, remove redundant English where touched).
- PASS.

### Migration Guard A/B/C (V098)
- Guard A (V035 base table existence): present with RAISE EXCEPTION on absent.
- Guard B (V053+V054 lease_sm_transition baseline): present with RAISE on absent.
- Guard C (hot-path index): N/A.
- Idempotency probe (3-value substring match): RAISE NOTICE skip.
- ACCESS EXCLUSIVE pattern (mirror V053): present.
- PASS (modulo Round 1 SHOULD-FIX-1 SOP gap which is governance, not this fix).

### healthcheck Pairing
- Round 2 does not introduce passive wait without healthcheck; Layer A 24h watch is Operator-driven per spec §11.3 D2 with PG one-liner SQL (now functional since governance_audit_log INSERT is wired).
- PASS.

### Singleton / Module Registration
- `crate::halt_audit` is stateless (pure functions + enum) — not a singleton.
- `paper_state_restore::ENV_TEST_MUTEX` is `#[cfg(test)]` only — not a production singleton.
- `paper_state_restore` visibility changed to `pub(crate)` — within-crate only, no external API surface change.
- PASS.

### Bybit API
- No `/v5/*` REST / WS endpoints touched.
- N/A.

### Multi-session race check (§5 SOP)
- 5a (`git fetch --prune origin`): clean; no sibling push in last 2h on origin/main.
- 5b (`git status --porcelain`): all dirty files within Layer A IMPL scope + Operator/PA workspace memory + SCRIPT_INDEX (expected).
- 5c (unknown WIP): none detected.
- 5d (sign-off report path clean): N/A (this is the sign-off commit pending).
- 5e (sibling push during review): none.
- PASS.

---

## 6. Independent Test Verification

```
cd /Users/ncyu/Projects/TradeBot/srv/rust
cargo test -p openclaw_engine --release
→ aggregate: passed=3264 / failed=0 / ignored=3
→ matches E1 Round 2 claim (3255 → 3264, +9 new tests, all green)

cargo test -p openclaw_engine --release --lib per_symbol_price_pnl
→ 3 passed / 0 failed (P1-16 invariant PRESERVED)

cargo test -p openclaw_engine --release --lib halt
→ 57 passed / 0 failed (covers halt_audit + halt_ttl + risk_config halt_ttl_tests + lifecycle handlers + step_6 close_tags)

cargo test -p openclaw_engine --release --lib config::risk_config::halt_ttl_tests
→ 9 passed / 0 failed (sibling all green, none silently skipped)

cargo test -p openclaw_engine --release --lib test_2026_05_19_incident_replay
→ 1 passed / 0 failed (spec §6.3 incident replay green)

python3 helper_scripts/canary/test_halt_audit_pg_writer.py
→ Ran 20 tests in 0.019s — OK

ssh trade-core 'bash /tmp/halt_audit_pg_writer_integration.sh'
→ 3 INSERTs + idempotent re-run (rowcount=0) + clear_path↔event_type mapping verified + DELETE cleanup PASS
```

**E1 Round 2 self-report numbers match independent verification 100%**.

---

## 7. Observations (no action required)

### OBS-1: Layer B (watchdog inert probe) deferred until Layer A 24h observation closes (spec §11.3)
Spec §11.3 D2 dictates 24h passive watch on Linux post-deploy before Layer B begins. Acceptable; not a regression.

### OBS-2: 5/8 quant-context fields still NULL in record_halt_set payload
Same as Round 1 §6.6. Tracked via P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1 ticket. Adding helpers would require IndicatorEngine / PortfolioState wiring — out of Layer A scope per E1 minimum-impact principle. Schema is nullable so jsonschema validate passes.

### OBS-3: `risk_config_version_seen=0` placeholder remains
Round 1 SHOULD-FIX-2 / E1 caveat 6.3. `IntentProcessor::risk_config_version_seen()` accessor not added. Tracked via P2-FORENSIC-RISK-CONFIG-VERSION-SEEN. Forensic loses one cross-reference field but `governance_audit_log.patch_risk_config` events provide version trail elsewhere.

---

## 8. Recommendation

**PASS to E4** for regression + QA Audit per spec §11 hand-off.

E4 should re-run:
- `cargo test -p openclaw_engine --release` (Mac aarch64-apple-darwin + Linux x86-64)
- `python3 helper_scripts/canary/test_halt_audit_pg_writer.py`
- Linux PG integration script `/tmp/halt_audit_pg_writer_integration.sh` (or rerun manually with fresh PIDs)

QA Audit should confirm:
- Spec §10 X-1 through X-10 + A-1 through A-9 acceptance criteria green
- 16 根原則 + 9 條安全不變量 0 violation
- 3 environment TOML (paper / demo / live) independent + validate
- No alpha-deficient strategy attribution leakage

After QA → PM signs off → operator authorizes deploy.

**Do not bypass E4 / QA**. Strong work by E1 in Round 2; all 4 MUST-FIX + 1 E3 MEDIUM + 1 spec compliance closed cleanly with no scope creep.

---

E2 REVIEW DONE: PASS to E4 (0 MUST-FIX-RETURN; 0 SHOULD-FIX-FOLLOWUP; 3 informational OBSERVATIONS) · report path: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-19--layer_a_halt_ttl_impl_round2_e2_review.md`
