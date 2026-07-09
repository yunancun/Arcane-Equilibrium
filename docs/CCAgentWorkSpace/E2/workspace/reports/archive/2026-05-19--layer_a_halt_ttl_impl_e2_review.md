## E2 PR Adversarial Review — P0-ENGINE-HALTSESSION-STUCK-FIX Layer A · 2026-05-19

**Author**: E2
**Date**: 2026-05-19
**Spec**: `srv/docs/execution_plan/2026-05-19--engine_haltsession_ttl_and_watchdog_inert_probe_spec.md` v0.2
**E1 IMPL report**: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-19--layer_a_halt_ttl_impl_report.md`
**Branch state**: Dirty Mac worktree; uncommitted; HEAD at 7fb46387 (TODO 同步 commit)
**Independent verification**: cargo test re-run (3255/0/3 PASS), md5 V098, file LOC counts, code path grep

---

## 1. Verdict + Counts

**VERDICT: RETURN to E1**

| Severity | Count |
|---|---|
| MUST-FIX-RETURN | 4 |
| SHOULD-FIX-FOLLOWUP | 3 |
| OBSERVATION | 4 |

E1 may fix MUST-FIX 1+2 inline (typo-tier behavior bug + restore path); MUST-FIX 3+4 require operator policy decision but may be folded after PA acknowledgment. No bug compromises P1-16 invariant or hard boundaries.

---

## 2. E1 Self-Report 6 Caveats — Verification

### 2.1 V098 already landed Linux production DB (E1 §6.1) — **VERIFIED + SOP GAP CONFIRMED**

V098 file md5 verified: `ec12e857f2596b43456de3f8e9986bd5` matches E1 claim. SQL pattern is sound (Guard A/B + ACCESS EXCLUSIVE pattern + idempotency probe). The dry-run procedural gap is **real**: V053-style migrations contain inner `BEGIN; ... COMMIT;` so outer ROLLBACK wrapping is no-op. **V098 has been silently committed to trade-core DB before E2/QA approval.**

- **Forward-only risk assessment**: V098 is pure CHECK enum extension (adds 3 new allowlist values; does not remove old values; does not change column semantics). Acceptable forward-only risk.
- **Governance impact**: `feedback_v_migration_pg_dry_run` mandate not satisfied. E1 should have escalated PA round 3 or sought operator authorization before applying.
- **Recommendation**: SHOULD-FIX-FOLLOWUP — open `P2-GOV-V-MIGRATION-DRY-RUN-SOP-FIX` to update SOP for V053-style nested-COMMIT migrations (e.g., separate transactional vs DDL test scripts).

### 2.2 governance_audit_log INSERT by Python audit writer (E1 §6.2) — **REFUTED: NOT IMPLEMENTED**

Independent grep for any Python audit writer reading `halt_audit.log` → INSERT to `learning.governance_audit_log`:

```
rg -n "halt_session_set|halt_session_auto_cleared|halt_session_manual_cleared|halt_audit" --include='*.py'
```

**Zero hits in production Python code.** No tail-reader, no IPC channel writer, nothing.

**Impact**:
- AC A-6 (governance_audit_log every event 1 row) **FAILS** in production
- AC A-1-EV / A-2-EV / A-4-EV (MUST-4 operator EV queries) cannot work — no rows ever written
- V098 added the 3 event_type allowlist values that are never used

**Recommendation**: MUST-FIX-RETURN-3. Either:
(a) Add Python audit-writer task that tails halt_audit.log → INSERT to PG (preferred per E1 §6.2 design), OR
(b) Add async PG INSERT inline in `record_halt_set` / `record_halt_cleared` (couples engine to PG)

If deferred to Layer B / separate ticket, mark AC A-6 / A-1-EV / A-2-EV / A-4-EV as **deferred** in `TODO.md` with explicit follow-up SLA, do NOT claim "✅ unit" or "⏸️ design choice".

### 2.3 risk_config_tests.rs 2076 LOC > 2000 cap (E1 §6.4) — **VERIFIED + NO PRECEDENT**

Independent file size scan:
```
2076 rust/openclaw_engine/src/config/risk_config_tests.rs    ← only file > 2000
1981 step_4_5_dispatch.rs
1920 intent_processor/tests.rs
1883 commands.rs
```

No existing file in this codebase exceeds 2000 LOC. There is **NO documented pre-existing exception** per CLAUDE.md §九. E1's pre-existing baseline 1910 LOC + 165 LOC delta = 2076 breaches the hard cap.

**Recommendation**: MUST-FIX-RETURN-2. Split the 8 halt TTL validate tests + `test_live_daily_loss_sticky_enforcement` + `test_demo_paper_daily_loss_ttl_24h` (~165 LOC) into sibling `rust/openclaw_engine/src/config/risk_config_halt_ttl_tests.rs`. ~15 min mechanical refactor. Avoid setting a "first exception" precedent.

### 2.4 halt_audit.log default `/tmp/openclaw/` (E1 §6 caveat 4) — **VERIFIED**

Fallback chain in `halt_audit.rs::resolve_log_path()`:
1. `OPENCLAW_HALT_AUDIT_LOG` (explicit override)
2. `$OPENCLAW_DATA_DIR/halt_audit.log`
3. `/tmp/openclaw/halt_audit.log` (final fallback)

Per spec §5.3 + memory `project_paper_pipeline_disabled_by_default` — design intent verified. P2-FORENSIC-LOG-PATH-DEFAULT backlog ticket already noted by E1 + spec §12.2. **OBSERVATION** — acceptable for Layer A; revisit after 7d Linux observation.

### 2.5 risk_config_version_seen 缺失 (E1 §6.3) — **VERIFIED**

`step_6_risk_checks.rs:452` writes `let halt_risk_config_version: u64 = 0; // TODO(E2 review): IntentProcessor 暫無 risk_config_version_seen()`. Explicit TODO comment present + spec §3.8 audit table cross-reference acknowledged.

**OBSERVATION** — accept as P2 follow-up; track via `P2-FORENSIC-RISK-CONFIG-VERSION-SEEN`. Forensic loses one cross-reference field but `governance_audit_log` patch_risk_config events provide the version trail.

### 2.6 6 quant-context fields partial null (E1 §6.6) — **VERIFIED**

`halt_audit.rs::build_quant_context_payload` writes:
- `per_symbol_drawdown_max_pct`: NULL
- `per_symbol_drawdown_max_symbol`: NULL
- `consecutive_loss_max_count`: NULL
- `correlated_exposure_pct`: NULL
- `paper_state_recompute_ok`: real boolean
- `paper_state_balance_history`: `[peak, current]` 2-element fallback (not last-10 history)
- `per_strategy_drawdown_contribution_pct`: NULL
- `per_symbol_atr_pct`: NULL

5/8 quant fields NULL. `halt_audit_schema.json` properly types these as nullable so validation will pass.

**OBSERVATION** — accept as P2 follow-up; track in `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1` (which will reveal which NULLs actually obstruct RCA). Backlog adds are localized helpers (~10 LOC each), schema_version bump deferred.

---

## 3. PA Top-3 Risk Audit

### 3.1 Step 6 HaltSession arm preserves P1-16 fix — **PASS**

Independent verification:
```
cargo test -p openclaw_engine --release per_symbol_price_pnl
→ 3 passed / 0 failed (test_close_position_at_symbol_market_uses_per_symbol_price,
                        test_close_position_at_symbol_market_fallback_to_entry_when_no_latest_price,
                        test_halt_session_uses_per_symbol_price_not_triggering_tick)
```

Source review of `step_6_risk_checks.rs:434-490`:
- New code (lines 439-467) inserted **AFTER** `self.paper_paused = true` (line 438)
- New code inserted **BEFORE** `drawdown_revoke::should_revoke` (line 481), `all_pos` collection (line 491), and the `close_position_at_symbol_market` / `close_position_after_exchange_dispatch` loop (lines 500+)
- The P1-16 critical realized_pnl + per-symbol price fallback at lines 519-540 is untouched
- Inner `{ ... }` borrow scope at lines 453-467 correctly limits the `risk_config_for_audit: &RiskConfig` immutable borrow so it does not conflict with the subsequent `self.execute_position_close` mutable borrows

PA top-1 audit point **PASS**.

### 3.2 Option C on_tick TTL check correctness — **PASS**

`on_tick/mod.rs:106-122`:
- Placed at on_tick opening (line 122), BEFORE step_0, step_0.5, step_1+2, step_3
- Uses `event.ts_ms` (not wall-clock) — replay determinism preserved
- `check_and_clear_halt_expired` body uses `now_ms.saturating_sub(self.halt_set_ts_ms)` — clock-skew safe
- O(1) early exit when `halt_kind == None` — does not slow normal tick path
- Interaction with `step_0_fast_track` paper_paused: fast_track sets paper_paused without setting halt_kind → `check_and_clear_halt_expired` sees `halt_kind == None` and returns early (correct)

`test_clock_skew_no_panic` + `test_check_clear_zero_halt_set_ts_defensive` verify defensive paths. PA top-2 audit point **PASS**.

### 3.3 PipelineSnapshot schema upgrade backward compat — **PASS**

Independent grep for Python Pydantic strict-mode consumers of `PipelineSnapshot`:
```
rg -n "extra\s*=\s*['\"]forbid" --include='*.py' program_code
```
→ 5 hits, all in `strategist_decision_v2.py`, `agent_contracts.py`, `scanner_advisory_contracts.py`, `position_review_v2.py`. **None consume PipelineSnapshot.**

`ipc_state_reader.py::RustSnapshotReader` uses plain `json.load()` — tolerates extra fields by default. 3 new fields (`halt_kind`, `halt_set_ts_ms`, `halt_ttl_remaining_ms`) are additive; old consumers ignore them. New consumers (watchdog Layer B in upcoming spec scope) explicitly require them.

Cross-language IPC schema verified PASS via:
- `pipeline_types.rs:175` `#[serde(default, skip_serializing_if = "Option::is_none")]` (Rust producer tolerates None → field omitted)
- `RustSnapshotReader` json.load() (Python consumer tolerates new fields)
- `MODE_SNAPSHOTS::halt_kind` typed as `Option<crate::halt_audit::HaltKind>` deserializes from JSON string via `#[serde(rename_all = "snake_case")]` — robust to roundtrip

PA top-3 audit point **PASS**.

---

## 4. Adversarial Hypotheses H1-H6

| H | Hypothesis | Found | Detail |
|---|---|---|---|
| H1 | E1 silently changed unrelated function signatures to make tests pass | NOT FOUND | `git diff --stat` shows 22 file mods + 4 new files, all within PA spec scope; risk_checks.rs delta is one new pub const + comments only |
| H2 | V098 idempotency probe is a no-op on fresh DB | NOT FOUND | V098 fresh-DB run would RAISE on Guard A (`learning.governance_audit_log` missing → V035 not deployed); this is by design (cannot apply V098 before V035/V053/V054 baseline) |
| H3 | demo/paper TOML accidentally got `daily_loss_halt_ttl_ms = 0` | NOT FOUND | grep confirms demo=86400000, paper=86400000, legacy=86400000, live=0 (correct sticky semantics) |
| H4 | ModeStateSnapshot backward-compat broken | NOT FOUND for serialization; FOUND for restore path (see MUST-FIX-RETURN-1) | `#[serde(default)]` correctly handles missing fields on snapshot READ; but the actual restore code path is missing entirely — see §5 finding 1 |
| H5 | `check_and_clear_halt_expired` off-by-one in elapsed | NOT FOUND | uses `elapsed < ttl_ms` → fires only at `elapsed >= ttl_ms`; saturating_sub safe; tests cover both within-TTL and after-TTL boundaries |
| H6 | ShadowOnly clear path missing halt_audit::record_halt_cleared | NOT FOUND | `commands.rs:1741-1751` correctly calls `record_halt_cleared(..., "ipc_system_mode_shadow")` |

**Net**: 0/6 hypotheses confirmed as suspected, but H4 catalyzed discovery of a separate restore-path gap.

---

## 5. Critical Findings

### MUST-FIX-RETURN-1 — `record_halt_cleared` writes wrong event_type — CRITICAL

**File**: `rust/openclaw_engine/src/halt_audit.rs:289`

```rust
let payload = serde_json::json!({
    "schema_version": 1,
    ...
    "event": "halt_session_auto_cleared",   // ← HARDCODED, IGNORES clear_path
    ...
    "clear_path": clear_path,
});
```

`clear_path` parameter accepts `"auto_ttl"`, `"ipc_resume"`, `"ipc_reset"`, `"ipc_system_mode_shadow"` (per E1 doc-comment lines 271-275). But the `event` field is hardcoded to `"halt_session_auto_cleared"` regardless. This means:

1. **Spec §3.9 manual clear path audit row** writes `event=halt_session_auto_cleared` instead of `halt_session_manual_cleared`
2. **Spec §10 A-1-EV operator EV query** (`event_type IN ('halt_session_set','halt_session_auto_cleared')`) returns IPC-clear rows mixed in with auto-clear rows
3. **Spec §3.8 governance_audit_log payload distinction** is broken: ledger always records "auto", never "manual"
4. **V098 added `halt_session_manual_cleared` to CHECK allowlist** but nothing in production code ever emits this event_type
5. **`halt_audit_schema.json` enum on line 27 expects 3 values** — schema validation passes the current single-value emit but expectation is violated semantically

**Fix** (E1 should write):
```rust
let event_str = match clear_path {
    "auto_ttl" => "halt_session_auto_cleared",
    "ipc_resume" | "ipc_reset" | "ipc_system_mode_shadow" => "halt_session_manual_cleared",
    _ => "halt_session_auto_cleared", // defensive default
};
let payload = serde_json::json!({
    ...
    "event": event_str,
    ...
});
```

Also add unit test:
```rust
#[test]
fn record_halt_cleared_event_str_distinguishes_auto_vs_manual() {
    // Verify event_str matches clear_path semantics; auto_ttl → auto_cleared;
    // ipc_* → manual_cleared.
}
```

### MUST-FIX-RETURN-2 — Restart restore of halt_kind / halt_set_ts_ms missing — HIGH

**Files involved**:
- `rust/openclaw_engine/src/event_consumer/paper_state_restore.rs` (no halt-state restore)
- `rust/openclaw_engine/src/tick_pipeline/pipeline_ctor.rs:104-105` (always inits halt_kind=None, halt_set_ts_ms=0)
- Spec §3.7 explicit requirement: "restore path: `event_consumer/paper_state_restore.rs` 在 reconstruct ModeState 時把這兩欄位寫回 TickPipeline"

E1 test `test_snapshot_roundtrip_persist_halt_state` only verifies the **emission** side (PipelineSnapshot embeds halt_kind / halt_set_ts_ms correctly). It does NOT verify the **restore** side (engine restart reads back halt_kind / halt_set_ts_ms).

Independent grep:
```
rg -n "halt_kind|halt_set_ts_ms|ModeStateSnapshot" rust/openclaw_engine/src/event_consumer/
```
returns only `lifecycle.rs` (IPC clearers) — no restore reader.

**Impact**:
- **AC A-4 (restart 不重設 TTL 起點) FAILS in production**: every engine restart loses halt state regardless of prior elapsed time
- AC A-4-EV (`SELECT halt_kind, halt_set_ts_ms FROM mode_snapshots ... LIMIT 1`) cannot validate post-deploy because the value will always be reset on restart

E1 report §5.5 row A-4 incorrectly claims "✅ unit". Correction: A-4 is verified at serialization layer only; production-correct restore is missing.

**Fix**: Add to `paper_state_restore.rs` (or a new dedicated `halt_state_restore.rs` sibling) a restore function that reads the prior `pipeline_snapshot.json` / `mode_snapshots.<engine>.halt_kind` and writes back into TickPipeline. Fail-soft when snapshot file missing or fields absent (cold start → init defaults). Add integration test that simulates a full snapshot → write → drop → fresh-pipeline → restore → assert halt state preserved.

If snapshot persistence layer is not the right place (different ARCH choice), the spec needs amendment AND a designed alternative (e.g., periodic checkpoint to PG `mode_snapshots` row alongside QoL-1 `restore_from_db`).

### MUST-FIX-RETURN-3 — governance_audit_log INSERT writer missing — HIGH

See §2.2 above. AC A-6 / A-1-EV / A-2-EV / A-4-EV currently cannot be validated post-deploy. Either:

(a) Add Python tail-reader writer + service entry (preferred per E1 design choice)
(b) Add async PG write directly in `record_halt_set` / `record_halt_cleared`

Recommendation (a). Effort estimate: ~0.5 PD for E1a (Python) or ~0.3 PD if folded into existing audit writer.

**Acceptable interim**: If E1 + PA + operator agree to defer this to Layer B scope or `P1-HALT-TRIGGER-ROOT-CAUSE-INVESTIGATION-1`, explicitly document in `TODO.md` that AC A-6 / A-1-EV / A-2-EV / A-4-EV are deferred with concrete owner + SLA. Do not silently leave the gap.

### MUST-FIX-RETURN-4 — File size 2076 LOC > 2000 hard cap — MEDIUM

See §2.3 above. No precedent in codebase. Split out new tests to sibling `risk_config_halt_ttl_tests.rs` (~15 min mechanical).

---

## 6. Should-Fix-Followup

### SHOULD-FIX-1 — V053-style migration dry-run SOP gap

Open new ticket `P2-GOV-V-MIGRATION-DRY-RUN-SOP-FIX`. The `feedback_v_migration_pg_dry_run` memory currently mandates `BEGIN; \i V###; ROLLBACK;` but this is no-op for V053-style migrations containing inner `BEGIN; ... COMMIT;`. SOP needs separate guidance:
- For pure DML migrations: use outer transaction wrap
- For DDL migrations with inner COMMIT: require staging DB / snapshot revert plan / forward-only acceptance + explicit operator approval

### SHOULD-FIX-2 — `paper_state_recompute_ok` arbitrary tolerance

`halt_audit.rs:172`:
```rust
let paper_state_recompute_ok = peak.is_finite() && current.is_finite() && peak >= current * 0.999;
```

0.999 tolerance is arbitrary and undocumented. Also, the equation `peak >= current * 0.999` flags `recompute_ok=false` for any current marginally above peak (which can happen during the brief window between fill and peak update). Either:
- Use exact `peak >= current` and accept transient false-positives
- Add explicit comment justifying 0.999 tolerance + document the post-fill peak-update window

### SHOULD-FIX-3 — Forensic test `test_2026_05_19_incident_replay` deferred (spec §6.3)

Spec §6.3 mandated a 14-step incident replay test. E1 §10 row §6.3 marks this as "⏸️ 待 E4 補 / 或派 E1a 跑". Per spec wording "強制此測試" (mandatory), this should be in Layer A scope, not deferred to E4. Effort: ~0.5 PD.

Either:
- E1 adds it before final sign-off (recommended)
- PM + PA explicitly amend spec §6.3 to make this Layer A optional / Layer B prerequisite

---

## 7. Compliance Audit

### 16 根原則
- #5「生存 > 利潤」: preserved (Live daily_loss sticky D1 + drawdown 三環境 sticky)
- #6「失敗默認收縮」: preserved (HaltKind::Other fail-safe sticky path)
- #8「交易可重建可解釋」: PARTIAL — forensic log armed but governance_audit_log INSERT writer missing (MUST-FIX-3)

### 9 條安全不變量
- 0 violations of `live_execution_allowed` / `max_retries=0` / `system_mode` / Bybit retCode / `OPENCLAW_ALLOW_MAINNET` / `live_reserved` / `authorization.json` write path / Reconciler / Operator role
- P1-16 ETHUSDT -17M bps regression test 3/0 PASS (verified independently)

### CLAUDE.md §九 file size
- **VIOLATION**: `risk_config_tests.rs` 2076 > 2000 hard cap, no documented pre-existing exception → MUST-FIX-4

### Cross-platform path
- `grep -E '(/home/ncyu|/Users/[^/]+)'` over all 22 modified files + 4 new files → 0 hits in new code
- PASS

### Bilingual comment skill
- New code (halt_audit.rs, V098 SQL, halt_ttl.rs tests, lifecycle.rs delta) all carry Chinese-first MODULE_NOTE / function rationale comments
- Touched bilingual blocks not cleaned (acceptable per skill)
- PASS

### Migration Guard A/B/C
- V098 Guard A: `learning.governance_audit_log` existence check — present, RAISE if absent
- V098 Guard B: `lease_sm_transition` substring check — present, RAISE if V053/V054 not applied
- V098 Guard C (hot-path index): N/A (no index added)
- Idempotency probe: 3-value substring match → RAISE NOTICE skip
- ACCESS EXCLUSIVE pattern mirror V053 — race-free preserved
- PASS (modulo SHOULD-FIX-1 SOP gap)

### healthcheck pairing
- E1 report §8 lists 24h passive watch (D2) for Layer A — but no `[##]` healthcheck SQL was added to `TODO.md`
- Spec §11.3 Step 2 mandates 24h watch with PG query `WHERE event_type LIKE 'halt_session_%'`
- TODO maintenance per `docs/agents/todo-maintenance.md` — passive wait must have healthcheck OR review date OR named external action
- **OBSERVATION** for PM: track 24h watch in TODO.md with healthcheck SQL OR explicit watch date

### Singleton / sub-module registration
- New module `crate::halt_audit` is stateless (pure functions + enum) — not a singleton
- No new `Arc<Mutex<>>` introduced
- PASS

### Bybit API
- No `/v5/*` REST / WS endpoints touched
- N/A

---

## 8. Independent Test Verification

```
cd /Users/ncyu/Projects/TradeBot/srv/rust
cargo test -p openclaw_engine --release
→ aggregate: passed=3255, failed=0, ignored=3 (matches E1 claim exactly)

cargo test -p openclaw_engine --release per_symbol_price_pnl
→ test_close_position_at_symbol_market_uses_per_symbol_price ... ok
→ test_close_position_at_symbol_market_fallback_to_entry_when_no_latest_price ... ok
→ test_halt_session_uses_per_symbol_price_not_triggering_tick ... ok
→ 3 passed; 0 failed; 0 ignored (P1-16 invariant PRESERVED)
```

V098 file md5:
```
md5(V098__governance_audit_log_halt_event_types.sql) = ec12e857f2596b43456de3f8e9986bd5
(matches E1 claim exactly)
```

File LOC sanity:
```
2076  risk_config_tests.rs  ← exceeds 2000 hard cap
1981  step_4_5_dispatch.rs
1920  intent_processor/tests.rs
1883  commands.rs
422   halt_audit.rs (new)
256   V098 SQL (new)
221   halt_ttl.rs (new)
151   halt_audit_schema.json (new)
```

Multi-session race check (per CLAUDE.md `pr-adversarial-review` §5):
- 5a: `git fetch --prune origin` clean; no sibling push in last 2h on origin/main
- 5b: `git status --porcelain` shows only files within Layer A IMPL scope + memory.md changes from sibling agents (expected)
- 5c: No unknown WIP detected
- 5d: N/A (no sign-off commit yet)
- 5e: Re-fetched during review; no sibling push in last 30min

Multi-session race check **PASS**.

---

## 9. Recommendation

**RETURN to E1** with the following MUST-FIX list (sequential, no parallel):

1. **MUST-FIX-RETURN-1** (CRITICAL): Fix `record_halt_cleared` event_type mapping. Apply diff to `halt_audit.rs:285-298` mapping clear_path → event_str. Add unit test. ~10 min.
2. **MUST-FIX-RETURN-2** (HIGH): Implement halt-state restore path. Add halt_kind/halt_set_ts_ms restore in `paper_state_restore.rs` or sibling. Add integration test simulating round-trip restart. ~0.5 PD.
3. **MUST-FIX-RETURN-3** (HIGH): Implement governance_audit_log INSERT path. Either Python tail-writer (recommended) or async PG write in halt_audit.rs. ~0.3-0.5 PD depending on path. If deferred, MUST add explicit TODO.md follow-up entry.
4. **MUST-FIX-RETURN-4** (MEDIUM): Split `risk_config_tests.rs` (2076 LOC) → `risk_config_tests.rs` (1910) + `risk_config_halt_ttl_tests.rs` (165). Mechanical refactor, ~15 min.

**SHOULD-FIX (acceptable as follow-up backlog tickets)**:
5. SHOULD-FIX-1: V053-style migration SOP fix — open `P2-GOV-V-MIGRATION-DRY-RUN-SOP-FIX`
6. SHOULD-FIX-2: paper_state_recompute_ok tolerance comment/docs
7. SHOULD-FIX-3: Forensic incident replay test `test_2026_05_19_incident_replay` — spec §6.3 says "強制"; E1 either adds now or PA/PM amends spec

**OBSERVATIONS (no action required, track for awareness)**:
- /tmp/openclaw/ forensic log default path (P2-FORENSIC-LOG-PATH-DEFAULT backlog noted)
- risk_config_version_seen=0 placeholder (TODO comment present; track via P2 ticket)
- 5/8 quant-context fields NULL (acceptable v1 minimum)
- 24h passive watch healthcheck needs concrete entry in TODO.md

After E1 fix-back, re-submit to E2 for round 2 — round 2 will focus on MUST-FIX-1 + MUST-FIX-2 + MUST-FIX-4 verification + any new test failures. Once round 2 PASS, proceed to E4 regression + QA Audit per spec §11 hand-off.

**Do not proceed to E4 regression / QA / deploy with current IMPL.** P1-16 invariant + hard boundaries are safe, but AC A-4 / A-6 / EV queries fail in production as-is, defeating Spec §11.3 D2 24h passive watch ability (operator cannot query auto vs manual clears).

---

E2 REVIEW DONE: RETURN to E1 (4 MUST-FIX-RETURN, 3 SHOULD-FIX-FOLLOWUP) · report path: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-19--layer_a_halt_ttl_impl_e2_review.md`
