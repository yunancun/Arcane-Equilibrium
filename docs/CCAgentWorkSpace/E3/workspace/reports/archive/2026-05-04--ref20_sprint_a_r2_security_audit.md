# E3 Security Audit Report — REF-20 Sprint A Wave R2

**Date:** 2026-05-04
**Auditor:** E3
**Scope:** R2 Manifest Registry + Verification Repair (`/experiments/register` new module + `/run` FK fix + `/manifest/verify` SQL archive)
**Audit type:** Design-layer + grep on existing code (E1 IMPL still in flight; verdict subject to IMPL diff cross-check next round)
**Persistence note:** Persisted by PM per E3 closure protocol (E3 agent SDK does not auto-write).

---

## §1 Executive Verdict

**PASS-WITH-FIX (conditional on E1 IMPL satisfying §9 conditions)**

| Severity | Count | Items |
|---|---|---|
| CRITICAL | 0 | — |
| HIGH | 1 | H-1 (manifest_jsonb size cap) |
| MEDIUM | 4 | M-1 (idempotency uniqueness), M-2 (rate limit per-actor), M-3 (canonical_bytes nesting drift), M-4 (FOR SHARE tx scope) |
| LOW | 3 | L-1 (audit emit not wired to V053 INSERT), L-2 (test key path still possible in non-live profile), L-3 (release-profile env validation) |

**Key takeaway:** R2 design is sound. The existing R0/R1 base (commit `c1ab7ea9`) already includes the foundational guards (auth + path allowlist + IDOR + boot guard + cmdline cert + V052 FK). R2 must extend without weakening these. **The existing `/run` UUID5-derive without a `replay.experiments` row WILL FK-violate as soon as V052 is applied** — confirming R2-T2 is necessary for runtime. PM should treat 1 HIGH as blocker until size cap is wired.

---

## §2 Auth Bypass — PASS

**Evidence (grep verified):**
- `replay_routes.py:49` imports `require_scope_and_operator` from `app.auth`
- `replay_routes.py:182-189` defines `_require_replay_write(actor)` → `require_scope_and_operator(actor, "replay:write")`
- All 3 mutating routes already call it: `/run` (line 315), `/cancel` (769), `/manifest/verify` (1146)
- `auth.py:319-324` `require_scope_and_operator` does both `require_operator_role` + `require_scope` (defense in depth — fails 401 if no operator role, 403 if scope missing)
- `auth.py:239-240` registers `replay:write` + `replay:read:any` in `auth_scopes` default (Sprint 1 Track C E2 retrofit F8 land already)

**Recommendation for R2:** New `/experiments/register` route MUST also call `_require_replay_write(actor)` — same as `/run`. PM should require E1's `experiment_registry.py` register handler to first line `_require_replay_write(actor)`.

**Status:** Pattern is already correct in existing code; R2 just needs to follow it.

---

## §3 IDOR + Cross-Actor Manifest Theft — PASS-WITH-FIX

**Evidence:**
- `audit_actor_id(actor)` at `auth.py:327-331` returns `getattr(actor, "actor_id", "unknown")` — **server-side only, never trusts envelope.operator_id without verify_operator_identity()**
- `replay_routes.py:316` for `/run`: `actor_id = str(actor.actor_id)` — server-derived, immutable
- IDOR fix already lands in `build_report_idor_sql` (`security_guards.py:395-435`): default branch adds `AND s.actor_id = %s`; admin branch requires `replay:read:any` scope
- V045 INSERT at `replay_routes.py:401` uses `actor_id` from server-derived `actor.actor_id`, not from request body

**R2 conditions PM must enforce on E1:**
1. `/experiments/register` body MUST NOT accept `actor_id` / `created_by` from client. All 3 fields (`actor_id`, `created_by`, `created_at`) must be server-derived.
2. List/get manifest queries must follow IDOR pattern: default `WHERE actor_id = %s`, admin override only with `replay:read:any`. New SQL needs `build_experiments_idor_sql(...)` mirror.
3. **idempotency_key uniqueness MUST include actor_id.** `UNIQUE (actor_id, idempotency_key)` not just `UNIQUE (idempotency_key)`. → MEDIUM finding M-1.

---

## §4 FK Race + Advisory Lock — MEDIUM-4

**Existing race surface (V052 FK to `replay.experiments`):**
- `/run` INSERTs into `replay.run_state(manifest_id)` referencing V049
- If `/experiments/register` and `DELETE /experiments/{id}` race: register completes → /run INSERT begins → DELETE row fires → /run INSERT FK-violates ⇒ rollback
- Worse race: register completes → another actor calls `DELETE` → /run inserts cascade-NULL or falls back to in-memory, breaking audit trail

**PM-mandated fix (already in plan):** `/run` SELECT FROM `replay.experiments WHERE experiment_id = %s FOR SHARE` within same xact as INSERT into run_state.

**Audit verdict:** `FOR SHARE` is correct semantics — readers (run starters) can run concurrently but block any concurrent `DELETE` (which needs `FOR UPDATE`-equivalent lock). However:
- M-4: existing `/run` has `_do_pg_path()` opening cursor at line 334; the FOR SHARE SELECT MUST happen **inside** this same cursor before the `INSERT INTO replay.run_state`. If E1 puts the SELECT before opening the cursor or commits between SELECT and INSERT, the lock releases and the race re-opens.
- Advisory lock keys (`replay_run_global` + `replay_run_actor:<id>` at `route_helpers.py:100-101`) are already xact-scoped via `pg_try_advisory_xact_lock`. They guard run cap, not experiments row. **No conflict** with new `FOR SHARE` lock.

**R2 condition for E1:** `_do_pg_path()` MUST keep the V049 SELECT FOR SHARE → V045 INSERT in **one cursor without intermediate commit**.

---

## §5 Signature + Secrets File Fallback — PASS-WITH-FIX

**Existing guards (verified):**
- Boot guard (`security_guards.py:101-149`): `OPENCLAW_REPLAY_VERIFY_TEST_KEY` set + `OPENCLAW_RELEASE_PROFILE=live` ⇒ uvicorn startup raises RuntimeError (fail-closed).
- Per-route gate (line 152-203): live profile + env set → emit `replay_signature_test_key_blocked` audit + return empty test key (forces non-test path).
- ManifestSigner ctor (`manifest_signer.py:271-318`) does fingerprint mismatch check before HMAC → prevents key drift attack.
- `_constant_time_eq` uses `hmac.compare_digest` (timing-oracle proof).

**R2-T3 fix scope (replace test key path with secrets file fallback):**

The existing path-allowlist helper (`artifact_path_within_allowlist`) is for **artifact paths**, not secrets paths. **E3 finding L-3:** R2-T3 needs a **new** path-allowlist helper for secrets paths.

**Required E1 IMPL:**

1. New helper `secrets_path_within_allowlist(path: Path) -> Tuple[bool, Optional[str]]` in `security_guards.py`:
   - Resolve `$OPENCLAW_SECRETS_DIR` (or `$OPENCLAW_SECRETS_ROOT/secret_files/replay`) once.
   - For `<env>` from `OPENCLAW_RELEASE_PROFILE`, validate `<env>` is one of allowlist `{"paper", "demo", "live", "live_demo"}` BEFORE building the path.
   - `Path.resolve()` + `is_relative_to(secrets_root)` — same pattern as `artifact_path_within_allowlist`.
   - Reject any `<env>` value that is None / contains `..` / contains `/` / contains null byte.

2. `/manifest/verify` 410 path (when env is live and SQL archive not yet wired) MUST `raise HTTPException(status_code=410, detail={...})` and **never** return 200.

**E3 verdict:** R2-T3 design implicitly assumes "live profile + secrets file present → use secrets file → 200." This is **safe IF**:
- The secrets path is fully validated against allowlist before any read
- `<env>` is validated against the 4-value allowlist
- File mode (`stat().st_mode & 0o777`) checked ≤ `0o600` before reading

If E1 IMPL ships R2-T3 without these 3 sub-checks: **HIGH finding** that should send back to E1.

---

## §6 Path Injection / canonical_bytes Drift — MEDIUM-3

**Path injection — PASS:**
`replay_models.py:69-81` — `_validate_experiment_id` enforces `[a-zA-Z0-9_-]+` allowlist + max 128 chars. Same allowlist must be applied to `symbol`, `strategy`, `signature_key_ref`.

**R2 condition for E1:** New `RegisterManifestRequest` Pydantic model MUST mirror this allowlist for **every** TEXT-typed field. Pydantic Unicode/control char defense: `Field(min_length=1, max_length=N)` does NOT reject control chars by default. Recommend adding a `_validate_no_control_chars` validator that rejects `c.isprintable()==False` or contains `\x00`.

**canonical_bytes drift — MEDIUM-3:**

Cross-language byte-equal invariant verified in `manifest_signer.rs:524-531` and Python `manifest_signer.py:365`:
- Python: `json.dumps(stripped_dict, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf-8')`
- Rust: `serde_json::to_vec(&value)` with default BTreeMap

**Drift risk in R2:** When `/experiments/register` enriches `actor_id` + `created_at` server-side, those fields should NOT be in the `manifest_jsonb` body that gets hashed. The hashed `canonical_bytes` is the **client-supplied body only** (after Pydantic validation). Server enrichment fields go to **separate columns** (`actor_id` TEXT col, `created_at` TIMESTAMPTZ col), not into `manifest_jsonb`.

**E1 IMPL must:**
1. Hash `canonical_bytes(client_body_dict)` BEFORE adding `actor_id`/`created_at`/`experiment_id` (server-generated).
2. Store `manifest_jsonb` = client_body_dict (no server enrichment).
3. Store `actor_id`/`created_at`/`experiment_id` as separate V049 columns.

If E1 puts server fields into `manifest_jsonb` before hashing, **the cross-language invariant breaks**.

---

## §7 Leak Surface + Rate Limit + Idempotency Replay

**Leak surface — PASS:**
- `_emit_audit_stub` logs: `actor_id`, `experiment_id`, `manifest_hash` (first 16 chars max), `decision`, `extra_payload`. Does not log raw signature, raw key, or raw HMAC.
- **R2 condition for E1:** `/experiments/register` response body MUST be `{"experiment_id": <uuid>, "manifest_hash": <hex>}`. Never include `actor_id`, `signing_key`, `manifest_signature`, or full request body echo. Audit emit must redact `manifest_jsonb` content (only emit hash, not full body).

**Rate limit — MEDIUM-2:**
- Global: `_rate_limit_default = "120/minute"` per IP via `slowapi`.
- **No per-actor or per-route limit on replay routes.** A single authenticated actor can post 120 register requests per minute — each with up to 256 KB `manifest_jsonb` = 30 MB/min PG write pressure.

**E3 finding M-2:** `/experiments/register` should be limited to a tighter rate (e.g. `10/minute` per-actor). Add `@limiter.limit("10/minute", key_func=lambda r: r.actor_id_from_session)` decorator.

**Idempotency replay attack — HIGH-1 + MEDIUM-1:**

**HIGH-1: manifest_jsonb size cap NOT enforced anywhere visible.** `replay_models.py:60-67` only caps `idempotency_key` at 128 chars. The plan says "256 KB cap" — but there is **no** Pydantic validator enforcing this nor a FastAPI body-size middleware.

**E1 IMPL must:**
1. Add Pydantic `manifest_jsonb` validator: `len(json.dumps(v).encode('utf-8')) <= 256 * 1024` (raise 422 with structured error).
2. OR: add FastAPI middleware capping request body to 512 KB for `/api/v1/replay/*` POST routes.

**MEDIUM-1: Idempotency replay (different body, same key):**
- New `/experiments/register` MUST: when `idempotency_key` matches existing row for this actor, compare `manifest_hash` of incoming body vs stored row's `manifest_hash`. **Hash mismatch ⇒ raise 409 idempotency_replay_attack** (do NOT silently overwrite or return cached row).
- Idempotency_key TTL: V049 has `expires_at` column — register MUST set a sane TTL (V3 §5 says 30d) so that idempotency keys eventually free.

---

## §8 OWASP Top 10 (2021) Mapping Table

| OWASP # | Status | R2 Finding mapped | Fix path |
|---|---|---|---|
| **A01 Broken Access Control** | PASS | §2 — `_require_replay_write` enforced; new register handler MUST call same | Pattern exists |
| **A02 Cryptographic Failures** | PASS | HMAC-SHA256 + 256-bit key + `compare_digest` + cross-language byte-equal verified | OK |
| **A03 Injection** | PASS-WITH-FIX | §6 — Pydantic allowlist + control-char defense recommended for new TEXT fields | Add Pydantic validators |
| **A04 Insecure Design** | PASS-WITH-FIX | §4 FOR SHARE tx scope + §6 canonical_bytes contract + §7 idempotency-replay defense | E1 must implement all 3 |
| **A05 Security Misconfiguration** | MEDIUM | L-3 — secrets path needs `<env>` allowlist + path-resolve check | Add `secrets_path_within_allowlist` helper |
| **A06 Vulnerable Components** | N/A | No new dependencies | — |
| **A07 Identification/Authentication** | PASS | `actor_id` server-side; `audit_actor_id()` enforced | OK |
| **A08 Software/Data Integrity** | PASS-WITH-FIX | §6 canonical_bytes drift; §3 idempotency uniqueness with actor_id | E1 condition |
| **A09 Logging Failures** | LOW | L-1 — `_emit_audit_stub` STILL log-only (V053 deployed but writer not wired) | Track in P2; not R2 blocker |
| **A10 SSRF** | N/A | No outbound URL from replay routes | — |

---

## §9 Conditions to Send Back to E1 (PASS-WITH-FIX → PASS path)

Before E2 round 1 PASS, E1 IMPL must satisfy **all 7** of these:

1. `/experiments/register` calls `_require_replay_write(actor)` as first line (Auth A01)
2. `actor_id`, `created_at`, `experiment_id` are server-derived; NEVER read from request body (A07)
3. `UNIQUE (actor_id, idempotency_key)` constraint on V049 (or check via SELECT before INSERT in same xact) — prevent cross-actor key collision (A08)
4. **manifest_jsonb size cap 256 KB enforced** at Pydantic validator OR body-size middleware. **HIGH blocker.** (A04 DoS)
5. `/run` SELECT FROM `replay.experiments WHERE experiment_id = %s FOR SHARE` in same cursor as INSERT into run_state — no intermediate commit (A04 race)
6. R2-T3 secrets file fallback validates `<env>` against 4-value allowlist + path-resolve `is_relative_to($OPENCLAW_SECRETS_DIR)` + file mode check `0o600` (A05)
7. canonical_bytes hash computed on client body BEFORE server enrichment. `manifest_jsonb` column stores client body only; server fields go to separate V049 columns (A08)

**Plus 2 MEDIUM that PM may downgrade to P2 ticket:**

8. Per-actor rate limit `@limiter.limit("10/minute")` on `/experiments/register`
9. Idempotency replay defense: same key + different body hash ⇒ 409 not 200

---

## §10 Residual Risks (PM Acceptable)

These are **not R2 blockers** but PM should track:

- **L-1: Audit emit is STILL log-only** — Acceptable for R2 (Sprint A scope is registry, not audit pipeline).
- **L-2: Test key path still reachable in non-live profile** — by design. R2 does not need to remove this.
- **L-3 partial: `<env>` from `OPENCLAW_RELEASE_PROFILE` is global env** — mitigated by systemd unit env lock in production.
- **Existing `/run` UUID5-derive WILL FK-violate after V052 + V049 deploy** (this is what R2-T2 fixes): PM should ensure R2-T2 lands BEFORE next deploy.

---

## §11 Cross-Check Note for PM

**E1 IMPL not yet committed at audit time:**
- `replay/experiment_registry.py` does not exist (verified `ls -la`)
- `/experiments/register` route not in `replay_routes.py` (verified grep)
- `OPENCLAW_REPLAY_VERIFY_TEST_KEY` test path still in lines 1182-1240 of `replay_routes.py`

**Therefore §1-§10 verdicts are design-layer only.** PM should request E3 cross-check against E1's IMPL diff before E2 round 1 PASS.

---

E3 AUDIT DONE: 0 CRITICAL / 1 HIGH / 4 MEDIUM / 3 LOW · design-layer · awaits IMPL diff cross-check
