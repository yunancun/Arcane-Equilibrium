# E5 Optimization Review: main_legacy.py + learning_ops.py (Post Wave A-D)

**Date**: 2026-04-01
**Reviewer**: E5 (Optimization Engineer)
**Scope**: Code quality, dead code, duplication, performance, readability
**Files reviewed**:
- `app/main_legacy.py` (431 lines)
- `app/learning_ops.py` (1624 lines)

---

## Part 1: main_legacy.py (431 lines)

### Overall Assessment

The file is well-structured after Wave A-D refactoring. It correctly serves its purpose as a singleton hub + re-export facade. Most issues are minor.

### 1.1 Dead Code / Unused Re-exports

| # | Lines | Symbol | Issue | Severity |
|---|-------|--------|-------|----------|
| ML-1 | 133-134 | `REVIEW_PACKET_STATUSES`, `REVIEW_PACKET_TYPES` | Re-exported from state_compiler but never imported by any consumer (not used in learning_ops, legacy_routes, control_ops, or any other module). Dead re-exports. | LOW |
| ML-2 | 136 | `_MAX_PAYLOAD_SIZE` | Re-exported but never used outside state_compiler.py itself. | LOW |
| ML-3 | 138 | `_MAX_TEXT_REASON` | Re-exported but never used outside state_compiler.py itself. | LOW |
| ML-4 | 109 | `T` (TypeVar) | Re-exported from state_models but only used inside state_models.py for `ResponseEnvelope[T]`. No external consumer imports `T` via main_legacy. | LOW |
| ML-5 | 50-64 | `_AUTH_CREDENTIALS`, `_resolve_api_token`, `_split_csv` | Private auth internals re-exported but only consumed by legacy_routes.py, which imports directly from auth.py. The re-exports in main_legacy are therefore dead. Only `_load_auth_credentials`, `_login_fail_counts`, `_login_fail_lock`, `_LOGIN_*` constants are used by legacy_routes (and legacy_routes imports them from auth.py directly). | LOW |

**Recommendation**: These dead re-exports add ~15 lines of visual noise. They can be removed in a cleanup pass. However, since re-exports exist for backward compatibility and external test files might reference them, verify with a project-wide grep before removal.

### 1.2 Readability

| # | Lines | Issue | Severity |
|---|-------|-------|----------|
| ML-6 | 314 | `from slowapi.middleware import SlowAPIMiddleware` is an inline import placed between module-level code (after app creation, CORS setup). All other slowapi imports are at the top (lines 42-44). Move to top-level imports for consistency. | LOW |
| ML-7 | 112-116 | Empty lines + orphan comment `# NOTE: All Pydantic model classes...` is informational but adds 5 blank/comment lines that duplicate the MODULE_NOTE already at top. | TRIVIAL |
| ML-8 | 235-237, 271-273, 424-425 | Multiple consecutive blank lines (3+ in some places). PEP 8 recommends max 2 between top-level definitions. | TRIVIAL |

### 1.3 Performance

No significant performance issues. The file is loaded once at startup; re-exports have zero runtime cost.

### 1.4 Security Note (Informational)

Line 283-296: The CORS wildcard stripping logic is well-implemented. No issues found.

---

## Part 2: learning_ops.py (1624 lines)

### Overall Assessment

This file is **2x the 800-line warning threshold** (S14.1). It contains well-structured but highly repetitive code. The dominant pattern -- a 7-line preamble (scope/snapshot/identity/idempotency/replay/revision) repeated 9 times, plus duplicated response construction -- accounts for a large portion of the line count. The file is a strong candidate for splitting.

### 2.1 Dead Code

| # | Lines | Symbol | Issue | Severity |
|---|-------|--------|-------|----------|
| LO-1 | 1229 | `ts_key = f"last_{scan_type[:-1]...}"` | **Dead assignment.** This f-string computation is immediately overwritten by the if/elif/else block on lines 1230-1235. The f-string on line 1229 is never used. | LOW |

### 2.2 Possible Bug

| # | Lines | Issue | Severity |
|---|-------|-------|----------|
| LO-2 | 1557 | `decided[-_MAX_RECENT_ENTRIES:]` — After sorting `decided` newest-first (reverse=True), taking `[-20:]` returns the **last** 20 elements, which are the **oldest** 20 decided packets. This is likely intended to be `decided[:_MAX_RECENT_ENTRIES]` (the newest 20). If `decided` has 50 items sorted newest-first, `[-20:]` gives items 31-50 (the oldest), not 1-20 (the newest). | MEDIUM |

### 2.3 Duplication (Primary Issue)

This is the dominant optimization opportunity. Three categories of duplication:

#### 2.3.1 Standard Preamble (9 occurrences)

The following 7-line pattern appears identically in 9 functions (lines 89-96, 177-184, 263-270, 348-355, 447-454, 521-528, 592-599, 1184-1191, 1292-1299):

```python
require_scope(actor, "learning:write")  # or "learning:manage"
snapshot, _ = _base.get_latest_snapshot()
verify_operator_identity(envelope, actor)
replay = _check_idempotency(snapshot, envelope)
if replay is not None:
    replay["snapshot"] = snapshot
    return replay, "replayed"
_assert_revision(snapshot, envelope)
```

**Recommendation**: Extract a helper:
```python
def _standard_preamble(envelope, actor, scope="learning:write"):
    require_scope(actor, scope)
    snapshot, _ = _base.get_latest_snapshot()
    verify_operator_identity(envelope, actor)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return snapshot, ("replayed", replay)
    _assert_revision(snapshot, envelope)
    return snapshot, None
```
This would eliminate ~63 lines (7 lines x 9 occurrences, replaced by 1-line calls).

#### 2.3.2 Mutator Tail Pattern (9 occurrences)

Every mutator function ends with:
```python
audit_ref = _write_audit_fields(state, action_type=..., ...)
_bump_revision(state)
compiled = _compile_for_response(state)
response = {"audit_ref": audit_ref, "data": {...}, "snapshot": compiled}
_store_idempotent_response(compiled, envelope, response)
return compiled
```
Followed by post-mutator:
```python
final_state = _base.STORE.mutate(mutator)
return {
    "audit_ref": final_state["audit_context"]["last_write_action_audit_ref"],
    "data": {...},  # duplicated from inside mutator
    "snapshot": final_state,
}, "success"
```

The `data` dict is constructed **twice** identically -- once inside the mutator (for idempotent cache) and once outside (for the return value). This is error-prone (changes must be made in two places) and adds ~8 duplicated lines per function (~72 lines total).

**Recommendation**: The mutator could store its response data on a shared mutable container (e.g., `result = {}`) that the outer code reads, eliminating the second construction.

#### 2.3.3 Record-Finding Loops (3 occurrences)

Lines 462-471, 536-545, 609-619 all implement the same "find by ID in list" pattern:
```python
target_idx = -1
for idx, item in enumerate(some_list):
    if item.get("some_id") == target_id:
        # optional status check
        target_idx = idx
        break
if target_idx == -1:
    raise HTTPException(404, ...)
```

**Recommendation**: Extract a `_find_record_by_id(records, id_field, id_value)` helper returning `(record, index)` or raising 404.

### 2.4 Performance

| # | Lines | Issue | Severity |
|---|-------|-------|----------|
| LO-3 | 1214-1226 | `existing_hashes` set is rebuilt from scratch on every call to the mutator. For a large review_queue (hundreds of packets), this is fine. No action needed currently. | TRIVIAL |
| LO-4 | 1029-1036 | `generate_auto_observations` / `generate_auto_lessons` / `generate_auto_hypotheses` iterate observations multiple times (once in each generator). If called in sequence via apply_auto_generate, the snapshot is read fresh each time. Acceptable for current scale. | TRIVIAL |

### 2.5 Readability

| # | Lines | Issue | Severity |
|---|-------|-------|----------|
| LO-5 | 1449-1455 | Nested ternary for `new_status` is hard to read. The mutator already computes `packet["status"]` -- this should be extracted to a variable before the return, not re-derived via nested ternary. | LOW |
| LO-6 | 57 | `_MAX_RECENT_ENTRIES` comment says "shared with pnl_ops; duplicated here for independence." This is acceptable but worth noting: the constant is defined in two places (learning_ops and pnl_ops). A shared constants module would be cleaner. | TRIVIAL |

---

## Part 3: learning_ops.py Split Recommendation (S14.1)

The file has **three clear logical domains** that map well to separate modules:

### Proposed Split

| New Module | Functions | Lines (est.) | Description |
|------------|-----------|-------------|-------------|
| **learning_records.py** | `apply_learning_observation`, `apply_learning_lesson`, `apply_learning_hypothesis`, `apply_learning_experiment`, `apply_hypothesis_verdict`, `apply_experiment_approval`, `apply_experiment_completion` | ~585 | CRUD operations for the 4 learning record types (observation/lesson/hypothesis/experiment). All follow the same preamble+mutator+response pattern. |
| **learning_auto_pipeline.py** | `_content_hash`, `_build_review_packet`, `_build_ai_question_for_*` (3), `generate_auto_observations`, `generate_auto_lessons`, `generate_auto_hypotheses`, `apply_auto_generate`, `apply_review_decision`, `apply_ai_consultation` | ~790 | Auto-scan pipeline: packet generation, review queue write operations, AI consultation stub. |
| **learning_queries.py** | `build_review_queue`, `build_learning_feed`, `build_learning_experiments` | ~90 | Read-only query builders. Pure functions on snapshot data. |

### Line Count After Split

- `learning_records.py`: ~585 lines (under 800 warning)
- `learning_auto_pipeline.py`: ~790 lines (borderline, but under 800; extracting the preamble helper would bring it to ~750)
- `learning_queries.py`: ~90 lines

### Dependencies

```
learning_queries.py      <- copy, _MAX_RECENT_ENTRIES (zero write deps, simplest module)
learning_records.py      <- _base, auth, state_compiler, state_helpers, state_models
learning_auto_pipeline.py <- _base, auth, state_compiler, state_helpers, state_models, warnings
```

No circular dependencies. All three import from the same base modules. `learning_auto_pipeline` does NOT depend on `learning_records` (the "approve" path in `apply_review_decision` constructs records inline rather than calling the apply_* functions).

### Re-export Strategy

`learning_ops.py` could be retained as a thin re-export facade (like main_legacy.py is now), or the re-exports in main_legacy.py could be updated to point to the new modules directly. The facade approach is simpler and avoids updating main_legacy.py imports.

### Priority

- **learning_queries.py**: Easy win, 90 lines, zero risk, extract first.
- **learning_records.py**: Medium effort. Consider extracting `_standard_preamble()` helper simultaneously to reduce line count further.
- **learning_auto_pipeline.py**: Largest module. Extract after records, since it contains the most complex function (`apply_review_decision` at ~190 lines).

---

## Summary

| Category | Count | Severity Breakdown |
|----------|-------|--------------------|
| Dead code / unused symbols | 6 (ML-1~5, LO-1) | 6 LOW |
| Possible bug | 1 (LO-2) | 1 MEDIUM |
| Duplication | 3 patterns (LO preamble/tail/find) | Structural |
| Readability | 5 (ML-6~8, LO-5~6) | 2 LOW, 3 TRIVIAL |
| Performance | 2 (LO-3~4) | 2 TRIVIAL |
| **S14.1 violation** | learning_ops.py 1624 lines (2x threshold) | **WARNING** |

### Top 3 Actionable Items

1. **LO-2 (MEDIUM)**: Fix `decided[-_MAX_RECENT_ENTRIES:]` to `decided[:_MAX_RECENT_ENTRIES]` in `build_review_queue()` line 1557. This appears to return the oldest decided packets instead of the newest.

2. **S14.1 Split**: Split learning_ops.py into 3 modules (learning_records / learning_auto_pipeline / learning_queries) as described above. Estimated effort: 2-3 hours including re-export updates and test verification.

3. **Preamble Dedup**: Extract `_standard_preamble()` helper to eliminate 63 lines of copy-paste across 9 functions. Can be done during or after the split.
