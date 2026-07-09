# LG-5-IMPL-2 ROUND 2 — Consumer review_live_candidate fixes (2 HIGH + 2 MEDIUM)

Date: 2026-05-02
Owner: E1
Round: 2 (E2 round-1 RETURN)
Spec: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--lg5_live_candidate_eval_contract_rfc_v2.md`
Status: Implementation done; await E2 round-2 review.

## Round 1 baseline → Round 2 LOC delta

| Path | Round 1 | Round 2 | Delta |
|---|---|---|---|
| `app/governance_hub_live_candidate_review.py` | 1373 | **1496** | +123 |
| `helper_scripts/learning/lg5_re_evaluate_pending.py` | 508 | **532** | +24 |
| `tests/test_lg5_review_live_candidate.py` | 450 | **731** | +281 (10 new tests) |

Consumer file 1496 < 1500 hard cap (CLAUDE.md §九).

## HIGH-1 — R6 data gap silently passes (FIXED)

**Bug**: `evaluate_r6` used `n_snap >= 7 AND n_neg >= 7`; data gap (`n_snap < 7`) fell through both clauses → returned `vetoed=False` → R1-R5 then evaluated → could grant approve. Violates RFC §3 R6 line 320/347 fail-closed.

**Fix**:
1. `evaluate_r6` strict equality: `n_snap == R6_DAILY_NEG_SNAPSHOTS_REQUIRED AND n_neg == R6_DAILY_NEG_SNAPSHOTS_REQUIRED` (line ~962). evaluator now only handles real veto conditions, not data sufficiency.
2. `review_live_candidate` adds data-gap pre-check before evaluate_r6 invocation (line ~1135 region):
   ```
   if n_snap < R6_DAILY_NEG_SNAPSHOTS_REQUIRED:
       verdict = _make_verdict("defer", "defer_data_insufficient",
                               rule_failures=["R6_data_gap"], ...)
       _emit_audit_row(...); return
   ```

**Tests added** (4 evaluator + 3 caller):
- `TestR6DataGapRound2`: n_snap=5 / 6 / 8 → vetoed=False; 7/7 still vetoes; 7/3 mixed not negative-veto
- `TestReviewLiveCandidateRound2.test_high1_data_gap_n_snap_5_defers`
- `..._seven_days_mixed_continues_to_approve` (regression — 7/3 reaches approve path)
- `..._seven_days_all_negative_rejects_hard_veto` (regression — 7/7 still hard-veto)

## HIGH-2 — Audit row decision_lease_id always NULL on approve (FIXED)

**Bug**: Round 1 issued 3 independent `conn.commit()` for the approve path:
1. `_emit_audit_row(..., verdict)` with hard-coded `None` for `decision_lease_id`
2. `hub.acquire_lease(...)`
3. `_persist_lease_to_candidate(candidate_id, lease_id)` (UPDATE candidate + secondary lease_grant audit)

Result: the `review_live_candidate` audit row's `decision_lease_id` column was always NULL even on approve; consumers had to JOIN against the secondary `lease_grant` row to find the lease. Violated RFC §2.3 line 215.

**Fix (E2 option b — single transaction)**:
1. **Order changed**: Step 4 = `hub.acquire_lease(...)` first; fail → defer + standalone audit (no lease persisted).
2. **New helper** `_emit_approve_audit_and_persist_lease_atomic(candidate_id, verdict, lease_id)`: single connection + single cursor + single `conn.commit()` for:
   - INSERT `review_live_candidate` audit row WITH `decision_lease_id=lease_id`
   - UPDATE `learning.mlde_param_applications.decision_lease_id`
   - INSERT `lease_grant` secondary audit row (back-compat)
   Failure (any step) → `conn.rollback()` + return False.
3. **Caller fail-closed**: atomic-commit fail → log orphan + downgrade verdict to `defer_audit_write_failed` (with `payload_snapshot.orphaned_lease_id`) + best-effort secondary audit on independent conn. Hub-side lease in memory is left to ExpiryGuardian TTL reaper (race acknowledged in code comment + memory log).
4. **Retired** `_persist_lease_to_candidate` (replaced by atomic helper).
5. `_emit_audit_row` non-approve path keeps `decision_lease_id=None` hard-coded — comment updated to clarify.

**Tests added**:
- `..._high2_atomic_commit_failure_downgrades_to_defer`: monkeypatch atomic helper to return False → verdict.decision="defer", reason="defer_audit_write_failed", payload_snapshot["orphaned_lease_id"]=lease_id
- `..._high2_lease_acquire_failure_defers_no_persist`: hub.acquire_lease returns None → atomic helper never invoked, defer_lease_acquisition_failed
- `..._seven_days_mixed_continues_to_approve` doubles as approve-path atomic-commit-success test (atomic_calls len==1, lease_id propagated)

## MEDIUM-1 — Bulk re-eval _StubHub.is_authorized=False masks all verdicts (FIXED)

**Bug**: `_StubHub.is_authorized()` returned `False` → `auth_effective=False` → R6 hard veto fires → all 24 pending candidates would be classified `reject / reject_hard_veto`, masking real R1-R5 / R-meta verdict distribution. Round 1 docstring "fail-closed safety" misread RFC §5.2 line 430.

**Fix**:
- `is_authorized()` → `True` (lets R1-R6 + R-meta evaluate against real data)
- `acquire_lease()` → `None` unchanged (triggers `defer_lease_acquisition_failed` even when R1-R5 pass; preserves real verdict in audit while declining lease)
- Docstring rewritten to explain RFC §5.2 line 430 intent ("don't auto-issue lease" ≠ "force reject")

No new unit tests for bulk script (CLI helper, integration coverage by E4 IMPL-4).

## MEDIUM-2 — Authorization scope binding gap (path (a) verified — flagged for PA)

### Investigation

Ran `ssh trade-core "cat ~/BybitOpenClaw/secrets/secret_files/bybit/live/authorization.json | python3 -m json.tool"`:
```
{
  "approved_system_mode": "live_reserved",
  "env_allowed": ["live_demo"],
  "expires_at_ms": 1777802683729,
  "issued_at_ms": 1777716283732,
  "operator_id": "demo-operator",
  "sig": "92f6b10ed239f9f6984ab2e1b2c88d96fb9f598f672f2cd0105d06c035b8f842",
  "tier": "T0_ENTRY",
  "version": 2
}
```

**No `scope` / `lease_scopes` field at all.**

Inspected `_auth_permits_scope` at `governance_hub_cascades.py:798-809`:
```python
permitted_scopes = auth_dict.get("scope", {}).get("lease_scopes", [])
return scope in permitted_scopes if permitted_scopes else True
```

When `permitted_scopes == []` (falsy), the conditional falls back to `True`. So **the dynamic `LIVE_CANDIDATE_APPLY:<strategy>:<target>` scope is currently permitted at runtime** — option (a)-equivalent behaviour today.

### Path adopted

Path (a) (current schema accepts dynamic scope by fallback) **+ KNOWN GAP comment** in `governance_hub_live_candidate_review.py` Step 4:
- Comment notes `_auth_permits_scope` empty-fallback-True semantics
- Notes that if operator later schema-binds `lease_scopes` without including `LIVE_CANDIDATE_APPLY` (or wildcard), this path will runtime-fail to `defer_lease_acquisition_failed` — fail-closed by existing infra
- Did **not** add scope-pre-register step (RFC design decision, PA scope)

### Flagged to PM

> RFC v2 §4 needs an explicit "authorization lease_scopes binding" requirement. Either:
> 1. PA writes RFC v2 follow-up requiring `lease_scopes` to include `LIVE_CANDIDATE_APPLY` (or wildcard) when operator schema-binds, OR
> 2. Operator decides current "empty lease_scopes = permit all" semantics is fine permanently and documents it
>
> Either way, the current consumer code is correct under both interpretations (KNOWN GAP comment self-documents the dependency).

## LOW findings (deferred per round-2 spec)

- LOW-1 (LOC near cap): consumer 1496 < 1500. Acceptable. Future `[42]` healthcheck callback addition will require split.
- LOW-2 (orphan lease on atomic-commit fail): downgrade-to-defer path now logs orphan + leaves lease to ExpiryGuardian TTL. P2 healthcheck `[42]` (LG-5-IMPL-3) will surface persistent orphans.

## Verification checklist

- [x] `python3 -m pytest tests/test_lg5_review_live_candidate.py -q` — **44 passed in 0.03s** (34 round 1 + 10 round 2 new)
- [x] `python3 -m pytest control_api_v1/tests/ -q --ignore=integration` — **3300 passed / 10 skipped in 54.12s** (round 1 baseline 3290 + round 2 new 10 = 3300, **0 regression**)
- [x] `python3 -m py_compile` 3 files — clean
- [x] `wc -l governance_hub_live_candidate_review.py` — **1496** (< 1500 hard cap)
- [x] `git diff --check` — 0 whitespace
- [x] `grep -E '/home/ncyu|/Users/[^/]+'` 3 files — 0 hit
- [x] Bilingual comments — all new functions / blocks have CN+EN

## E2 round-2 review checklist

1. **HIGH-1 evaluate_r6 strict equality**: `evaluate_r6` line ~962 uses `==` not `>=`. Caller pre-check at line ~1135 catches `n_snap < 7 → defer "defer_data_insufficient"` BEFORE invoking evaluate_r6. Audit row written.
2. **HIGH-2 atomicity**: approve path Step 4 = acquire_lease first; Step 5 = `_emit_approve_audit_and_persist_lease_atomic` single transaction. Atomic-commit failure → rollback + downgrade `defer_audit_write_failed`. `_persist_lease_to_candidate` retired.
3. **HIGH-2 audit row content**: V035 `decision_lease_id` column on `review_live_candidate` event row populated atomically (not just on `lease_grant` secondary row). E4 IMPL-4 integration test should verify SQL: `SELECT decision_lease_id FROM learning.governance_audit_log WHERE event_type='review_live_candidate' AND verdict_decision='approve' LIMIT 5` returns non-NULL.
4. **MEDIUM-1 stub semantics**: `_StubHub.is_authorized()` now `True`; `acquire_lease()` still `None`. Docstring explains RFC §5.2 line 430 intent.
5. **MEDIUM-2 KNOWN GAP comment**: `governance_hub_live_candidate_review.py` Step 4 comment block + memory entry document the empty-`lease_scopes` fallback semantics. Flagged to PA in this report.

## PM next-step

- E2 round 2 review.
- After E2 PASS → E4 IMPL-4 round-2 (integration tests should verify atomic commit on real DB).
- PM evaluate MEDIUM-2 path: ask PA to draft RFC v2 §4 scope-binding requirement, or accept current empty-fallback semantics permanently.
- No commit yet (PM unifies after E4 PASS per CLAUDE.md §七).
