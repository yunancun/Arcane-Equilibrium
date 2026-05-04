# E3 Security Audit Report — REF-20 Sprint A Wave R3

**Date**: 2026-05-04
**Auditor**: E3
**Scope**: R3 First Real E2E Evidence (`simulated_fills_writer.py` 602 LOC + `run_finalize_route.py` 551 LOC + thin handler 36 LOC + 19 tests)
**Audit type**: Diff + grep on real IMPL committed to working tree (post-E1 sign-off)
**Persistence**: Persisted by PM per E3 closure protocol.

---

## §1 Executive Verdict

**PASS-WITH-FIX (conditional on E1 round 2 patch addressing 1 MEDIUM + 1 documentation drift; 4 LOW deferrable to P2 ticket)**

| Severity | Count | Items |
|---|---|---|
| CRITICAL | 0 | — |
| HIGH | 0 | — |
| MEDIUM | 2 | M-1 (V046 dual-row race in multi-worker uvicorn finalize), M-2 (statement_timeout wiring drift: docs say 5s, runtime is 2s) |
| LOW | 4 | L-1 (PID-reuse cmdline check is grep-only, no `create_time()` strict identity), L-2 (V046 byte_size accepted without server-side cap), L-3 (artifact_type='pnl_summary' semantic mismatch), L-4 (parser size check TOCTOU; mitigated by read cap) |

**Key takeaway**: R3 IMPL is clean for the foundational invariants — auth, IDOR enum-oracle close, evidence_source_tier allowlist enforce, payload size cap, parameterized SQL, atomic xact rollback, OWASP A01/A03/A07/A08 — all PASS. R2 cross-language invariant (canonical_bytes / manifest_signer / manifest_hash) **0 modifications** in R3 — verified by grep. xlang fixture not at risk.

---

## §2 Untrusted JSON Parsing Risk — PASS

Threat model: `replay_report.json` written by trusted Rust subprocess but lives on disk between Rust write and Python read. Theoretical attacker with FS access could swap the file. R3 must fail-closed on every malformed shape.

Verified controls:
1. Path-traversal allowlist double-locked: `resolve_artifact_output_dir(run_id)` server-derives + `artifact_path_within_allowlist(report_path)` `Path.resolve().is_relative_to(root)` check. Traversal escape → 410 `replay_report_artifact_missing`.
2. File DoS bound: `MAX_REPORT_BYTES = 16 MB` checked via stat BEFORE open. Read uses bounded `f.read(MAX_REPORT_BYTES)`.
3. Schema_version pinning: `SUPPORTED_REPORT_SCHEMA_VERSIONS = frozenset({1})` hard-coded.
4. Top-level type check: rejects JSON arrays / scalars at top level.
5. Nested missing-key check: `result` not dict → ValueError; fills not list → ValueError.
6. Per-fill required key probe: missing keys → row skipped (NOT INSERTed).

Fail-closed proof: all parse exceptions propagate to handler exception block → `conn.rollback()` + 410 with no partial INSERT. Test `test_finalize_atomic_xact_rollback_on_writer_failure` confirms commit count = 0 on writer raise.

LOW-4 (TOCTOU): between stat and open, file could swap; `f.read(MAX_REPORT_BYTES)` cap protects. Not worth fix.

---

## §3 evidence_source_tier Allowlist + Payload Size Cap — PASS

evidence_source_tier allowlist: `V050_ALLOWED_TIER_VALUES = {"calibrated_replay", "synthetic_replay", "counterfactual_replay"}` matches V050 sql:228 CHECK enum exactly. Enforce **before** INSERT in `map_fill_to_v050_row`. Test confirms.

payload size cap: `MAX_PAYLOAD_BYTES = 4096` per fill. Oversize → truncated marker preserves observability fields (ts_ms / symbol / side). DoS bound: 16 MB report / 200 byte/fill = ~80k fills max; 80k × 4.5 KB = 360 MB worst case PG storage per finalize (acceptable for replay lab).

A03 injection: payload `json.dumps()` then `%(payload)s::jsonb` cast. psycopg2 handles JSON escape; cannot SQL-inject through this path.

---

## §4 SQL Injection / Parameterization — PASS

bulk INSERT: pure named-parameter (`%(name)s`); no string concat; type casts `::uuid`/`::jsonb` are SQL-side; executemany via per-call bind (no plan-cache poisoning); strip pseudo-keys before psycopg2.

`lookup_strategy_name_from_v049` and `_select_run_state_for_finalize_sync` and `_mark_run_finalized` and `register_artifact_in_db` all parameterized. No dynamic SQL identifier interpolation. Schema name `replay.*` is literal string.

---

## §5 IDOR Enum-Oracle Close on Finalize — PASS

Three collapse paths to single 404 reason_code `replay_run_not_found`:
1. SELECT 0 row
2. SELECT row exists but `row.actor_id != caller.actor_id`
3. Error message intentionally unifies both

No timing oracle: both 404 paths run identical SELECT + comparison + error mapping. `not_finalizable` 409 requires `actor_id == caller`, so cross-actor caller never sees 409.

Mirror /report H-IDOR-ENUM round 3 pattern.

---

## §6 PID-Reuse + Multi-Worker Race Arbitration

### LOW-1 — verify_replay_runner_pid uses cmdline-only check (E1 push-back #2/#3)

Current: `psutil.Process(pid).cmdline()` joined string-search for "replay_runner" substring. PID-reuse coincidence false positive: statistically negligible (PID space recycled in seconds; "replay_runner" substring is project-specific). Threat impact: false `is_alive=True` → 409 transient → retry. No data loss / corruption / privilege escalation.

E3 verdict: PASS-WITH-LOW. P2 future strengthen with `proc.create_time()` matched against V045 `started_at` (requires V045 column add).

### MEDIUM-1 — Multi-worker uvicorn finalize race produces double V046 INSERT

**Verified attack surface**:
1. Two parallel finalize calls on same run_id from same actor token (browser tabs <1ms apart)
2. Worker A SELECT run_state status='running', actor matches → no row lock
3. Worker B parallel SELECT also sees status='running' (A hasn't committed)
4. Worker A: V046 INSERT row1 + N×V050 INSERT + UPDATE V045 → commit
5. Worker B: V046 INSERT row2 (different artifact_id, no UNIQUE constraint on (run_id, artifact_type)) + V050 hits ON CONFLICT DO NOTHING + UPDATE V045 returns 0 → 409 `replay_run_finalize_race`

**Outcome**:
- V045 single row finalized — OK
- V050 fills unique by `(experiment_id, idempotency_key)` — OK
- V046 has 2 rows for same run_id with different artifact_id, both pointing to same file — **pollution**

**Severity reclassification**: NOT cosmetic.
1. Audit trail confusion: GET /report SELECT returns 2 rows
2. V3 §5 quota_enforcer storage cap: double-count file size accelerates eviction
3. Any reader counting "artifacts per run" gets misled

**E3 recommendation**: PUSH BACK to E1 round 2.

Option A (preferred): Add `SELECT ... FOR UPDATE` on V045 row in `_select_run_state_for_finalize_sync`. ~3 LOC. Worker B blocks on row lock until A commits, then sees status='completed' → `not_finalizable` 409.

Option B: Add `UNIQUE (run_id, artifact_type)` constraint on V046 in fresh V0XX migration (heavier).

PM should accept Option A as round 2 patch.

---

## §7 Atomic xact Rollback — PASS

Single-cursor transactional invariant verified. Single commit at end. Exception pathway: OSError/ValueError → 410 (file/parse error); any other → 503 (PG fail-closed). Both rollback wrapped in try/except.

Test `test_finalize_atomic_xact_rollback_on_writer_failure` confirms commit count = 0 + HTTP 503 + rollback called on writer raise.

`_mark_run_finalized` race: SELECT-to-UPDATE window protected by `WHERE status IN ('starting','running')` filter; returns False on race → rollback + 409 `replay_run_finalize_race`. Atomic xact preserved.

---

## §8 canary_writer Reuse Side-Effect — PASS

Pattern: instantiates `canary_writer.WriteResult` directly (bypasses filesystem write because Rust binary already wrote file). Calls `register_artifact_in_db` on existing file.

Security implications:
1. No file write in finalize = no new on-disk attack surface
2. artifact_id is server-side fresh `uuid.uuid4().hex`
3. byte_size from `Path.stat().st_size` — server-side fact
4. is_mock derived from V045 row's runtime_environment (server-side at run-spawn time)
5. Rust crash mid-write → partial JSON → JSONDecodeError → 410 with rollback

Idempotent retry: file remains on disk if first finalize raises 503; retry reads V045 still 'running', V046 absent (rolled back). On-disk file is retry-friendly, NOT attack surface.

LOW-2 — V046 byte_size unconstrained at SQL level: real bound is upstream 16 MB MAX_REPORT_BYTES. P2 documentation note: V046 should add `CHECK (byte_size BETWEEN 0 AND 67108864)` (64 MB) for defense-in-depth.

---

## §9 V046 'pnl_summary' Semantic Mismatch (E1 push-back #1) — PASS-WITH-LOW

V046 CHECK enum: `{'canary', 'diagnostic', 'pnl_summary', 'fill_log', 'baseline_compare'}`. `'replay_report'` NOT in allowlist. E1 substituted `'pnl_summary'` (closest in-allowlist).

Semantic analysis: replay_report.json carries pnl_summary AS WELL AS fills + diagnostics. Calling whole envelope "pnl_summary" is partially correct but misleading because it also carries fill_log content. Future R5 `WHERE artifact_type='fill_log'` query won't find this file.

Impact:
- No security risk: V046 CHECK protects schema integrity
- Data taxonomy risk: downstream R5+ readers might miss the file. **LOW-3 documentation/data-modeling debt**

E3 recommendation:
- Round 2 not blocked — accept E1 substitution
- P2 ticket: V0XX migration add `'replay_report'` to V046 enum + Guard B + ALLOWED_ARTIFACT_TYPES update
- Document in CLAUDE.md §九 Non-training surfaces note

---

## §10 OWASP Top 10 (2021) Mapping

| OWASP # | Status | Verified |
|---|---|---|
| **A01 Broken Access Control** | PASS | `_require_replay_write(actor)` first line; same auth pattern as /run, /cancel, /manifest/verify, /experiments/register |
| **A02 Cryptographic Failures** | N/A | R3 doesn't touch HMAC / authorization paths; grep confirmed 0 hits on signing_key/test_key/hmac |
| **A03 Injection** | PASS | All SQL parameterized (named params); jsonb adapter; no f-string SQL |
| **A04 Insecure Design** | PASS-WITH-FIX | Atomic xact + payload cap + report cap + finalize pid guard; **MEDIUM-1 V046 dual-row** |
| **A05 Security Misconfiguration** | PASS | Path allowlist double-locked; statement_timeout enforced (M-2 doc drift) |
| **A06 Vulnerable Components** | N/A | No new deps |
| **A07 Identification/Authentication** | PASS | actor.actor_id server-side; never reads from request body |
| **A08 Software/Data Integrity** | PASS | V050 evidence_source_tier enum CHECK enforced both at writer Python AND DB SQL; idempotency_key UNIQUE protects re-finalize |
| **A09 Logging Failures** | PASS | All logger calls use placeholders; structured payload via dict; no raw secrets |
| **A10 SSRF** | N/A | No outbound URL |

---

## §11 Cross-Language Invariant Maintenance — PASS

Verified 0 modifications to manifest_signer.py / .rs / canonical_bytes / manifest_hash. xlang fixture untouched. R3 is post-execution evidence persistence (V050 simulated_fills + V045 status flip + V046 register); does NOT compute manifest hashes / sign payloads / interact with signing key path. R2 canonical_bytes contract stands.

Test count: 3498 PASS / 1 pre-existing fail / 5 skip — same as R2 baseline + 19 new R3 (no new pre-existing fail).

---

## §12 Conditions to Send Back to E1 (PASS-WITH-FIX → PASS path)

Before E2 round 2 PASS, E1 IMPL should:

1. **MEDIUM-1 (recommended block)**: Add `SELECT ... FOR UPDATE` to `_select_run_state_for_finalize_sync` so Worker B blocks on V045 row lock during finalize, eliminating V046 dual-row race. ~3 LOC + new test asserting concurrent finalize against same run_id produces exactly 1 V046 row.

2. **MEDIUM-2 (documentation drift fix)**: Either (a) change thin handler to pass `statement_timeout_ms=5_000` matching documented "5s for finalize" intent (add `_FINALIZE_STATEMENT_TIMEOUT_MS = 5_000` constant), OR (b) update sign-off + run_finalize_route.py docstring to say production wiring is 2s. Pick one.

**These 4 LOW items can defer to follow-up tickets** (PM acceptable):

3. **LOW-1 (P2 ticket)**: future R6+ strengthen `verify_replay_runner_pid` with `psutil.Process.create_time()` matched against V045 stored `started_at`. Schema add: V045 column.

4. **LOW-3 (P2 ticket)**: V0XX migration to add `'replay_report'` to V046 CHECK enum + update `canary_writer.ALLOWED_ARTIFACT_TYPES` + flip `ARTIFACT_TYPE_REPLAY_REPORT` constant. Resolves semantic mismatch.

---

## §13 Residual Risks (PM Acceptable)

- L-2 (V046 byte_size unconstrained): real bound today is 16 MB upstream cap. NOT R3 blocker. P2 future.
- L-4 (TOCTOU stat-then-read): swap window <1 ms; read cap protects. NOT worth fixing.
- PG single-row lock missing on `_mark_run_finalized` UPDATE: relies on `WHERE status IN ('starting','running')` filter to be race-safe. Combined with M-1 fix, full multi-worker safety achieved.
- V050 fills_skipped == fills_seen edge case: if all fills fail validation, fills_inserted=0 + V046 row + V045 still flipped to 'completed'. Acceptable (successful finalize that found no valid fills); operator reads response and investigates.

---

E3 AUDIT DONE: 0 CRITICAL / 0 HIGH / 2 MEDIUM / 4 LOW · M-1 push back to E1 round 2 recommended; M-2 docs drift fix; 4 LOW → P2 ticket
