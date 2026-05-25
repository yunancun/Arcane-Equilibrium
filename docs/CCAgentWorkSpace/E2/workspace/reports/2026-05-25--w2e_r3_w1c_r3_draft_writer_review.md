# W2-E-R3 — E2 Cold Review of W1-C-R3 draft_writer Schema Fix + PM 3 Push Back Verdict

**Date**: 2026-05-25
**Role**: E2 (Senior Backend Code Reviewer + Adversarial Auditor)
**Phase**: Sprint 2 v5.8 Stream B Wave 1 W1-C-R3 → E2 cold review
**Parent commit**: `b2febd43` (E1 IMPL)
**Parent E1 report**: `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-25--w1c_round_3_draft_writer_schema_fix.md`
**Source BLOCKER**: `docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-25--w2f_stream_e_bucket_monitor_stream_b_m4_leakage_audit.md` §5.2 + §7
**Status**: REVIEW DONE — verdict APPROVE-WITH-CONDITIONS

---

## 1. TL;DR verdict

**APPROVE-WITH-CONDITIONS** — allow commit to land for unblocking Wave 3 dispatch, with 1 HIGH spec drift documented as Sprint 3 mandatory follow-up.

- 3 PM push back: E1 **2/3 fully correct** + **1/3 partial correct** (PM Option B partial right but spec wording was loose).
- 6 attribute mapping: **5/6 correct** + **1/6 spec deviation HIGH** (`replicability_score` formula invented, not in W1-A/W1-B spec).
- Mac pytest 89/89 non-flaky.
- 4 對抗 grep all PASS (SQL string 0 hit forbidden tokens).
- 16#7/#3/#8 + hard boundary all aligned.
- Sprint 3 detector wire-up dispatch: **CONDITIONAL READY** — requires (a) PA spec amend on replicability_score formula + (b) PM verdict on whether Sprint 2 ships with E1's invented formula or NULL placeholder.

**No CRITICAL finding. No BLOCKER on commit. Net positive vs W1-C-R1/R2 dead-on-arrival state.**

---

## 2. 3 PM Push Back Verify (SSH PG empirical)

### 2.1 Push back 1 — `evidence_json` column

**PM dispatch task wording**: "V103 EXTEND 6 real column + evidence_json"
**E1 push back**: empirical PG `learning.hypotheses` 0 hit `evidence_json`; W1-A spec §7.3 + V103 EXTEND spec §2.2 also don't reference it.

**E2 SSH PG empirical verify** (run 2026-05-25 from Mac via `ssh trade-core`):

```
column_name              | data_type | is_nullable
-------------------------+-----------+------------
hypothesis_id            | bigint    | NO
strategy_name            | text      | NO
pre_reg_ts               | timestamp | NO
pre_reg_hash             | text      | NO
status                   | text      | NO
expected_sharpe          | real      | YES
expected_dd              | real      | YES
capacity_estimate_usdt   | bigint    | YES
t_stat_min               | real      | YES
min_sample_size          | integer   | YES
engine_mode              | text      | NO
created_at               | timestamp | NO
updated_at               | timestamp | NO
hypothesis_source_module | text      | NO
leakage_scan_pass        | boolean   | NO
bonferroni_corrected_p   | numeric   | YES
replicability_score      | numeric   | YES
decision_lease_draft_id  | uuid      | YES
cowork_review_status     | text      | NO
(19 rows)
```

**Empirical 19 column 0 hit `evidence_json`.** ✅

V103 EXTEND spec (`docs/execution_plan/2026-05-21--v103_extend_m4_hypothesis_columns_schema_spec.md`) §2.2 line 38 lists 6 EXTEND columns, none is `evidence_json`. `evidence_json` exists in `learning.replay_divergence_log` (V107) + `learning.decision_lease_lal_tiers` (V112).

**Verdict**: **E1 correct, PM Option B partial wrong** — PM task wording carried `evidence_json` reference but the actual production schema doesn't have it. E1's design choice (decision_lease_draft_id UUID PG backref + build_audit_metadata function logger emit) is sound.

**E2 finding**: PM Option B dispatch packet wording should be amended (or PA spec follow-up) to remove the spurious `evidence_json` reference. Not blocking commit.

---

### 2.2 Push back 2 — `cowork_review_status='PENDING_REVIEW'`

**PM dispatch task wording**: "cowork_review_status='PENDING_REVIEW'"
**E1 push back**: V103 EXTEND CHECK constraint enum is `('NONE', 'PENDING', 'APPROVED', 'REJECTED')`. 'PENDING_REVIEW' not in enum.

**E2 SSH PG empirical verify** (CHECK constraint reflection):

```
hypotheses_cowork_review_status_check
CHECK (cowork_review_status = ANY (ARRAY['NONE'::text, 'PENDING'::text, 'APPROVED'::text, 'REJECTED'::text]))
```

**Empirical 4 enum: NONE / PENDING / APPROVED / REJECTED. 0 'PENDING_REVIEW' allowed.** ✅

E1 picked 'NONE' because Y1 doesn't activate Cowork review (per W1-A spec §9.4 + V103 EXTEND spec §2.2). 'NONE' is the spec-defined default and only legal Y1 value.

**Verdict**: **E1 fully correct, PM Option B wrong** — 'PENDING_REVIEW' would have raised PG CHECK violation on first cron fire. Picking 'NONE' is correct.

---

### 2.3 Push back 3 — `decision_lease_draft_id 'TEXT or NULL'`

**PM dispatch task wording**: "decision_lease_draft_id 'TEXT or NULL'"
**E1 push back**: V103 EXTEND real type = UUID. Application invariant non-NULL (per W1-B spec §9.5 audit chain).

**E2 SSH PG empirical verify**:

```
decision_lease_draft_id | uuid | YES (PG nullable)
```

V103 EXTEND spec line 95 confirms: `decision_lease_draft_id | UUID | NULL | — | M4 DRAFT writeback lease backref; FK 暫不加`.

**Empirical type = UUID (NOT TEXT). PG nullable = YES.** ✅ partial

**Verdict**: **E1 partially correct** —
- Type: UUID, **NOT TEXT** → E1 push back correct.
- Nullability: PG layer NULL allowed; E1's application-level fail-loud `decision_lease_draft_id is None: raise ValueError` is an **invariant enforcement** layered on top of PG schema (per audit chain 16#8). This is **stricter than PG schema** but matches W1-B spec §9.5 + W1-A spec §10.2 invariant ("M4 DRAFT writeback lease_id backref"; spec table mark "YES" but invariant text says "必 backref Lease ID").

**E2 finding (LOW)**: chicken-egg analysis — at scaffold stage `GovernanceHubInterface.acquire_lease()` returns `uuid.uuid4()` synchronously before INSERT. No DB write happens before lease acquire. Caller wires:
```
lease_id = hub.acquire_lease()    # returns UUID immediately
payload = build_writeback_payload(..., decision_lease_draft_id=lease_id, ...)
PG INSERT (decision_lease_draft_id = lease_id)
hub.release_lease(lease_id)
```
**No chicken-egg** — UUID is generated client-side, no PG dependency on `governance.decision_lease` table existing first (FK暫不加 per spec). DRAFT writeback can write before Lease table exists. **PASS**.

---

### 2.4 3 push back summary table

| Push back | E1 verdict | PM Option B verdict | E2 verdict |
|---|---|---|---|
| 1. evidence_json column | empirical 0 hit | wording wrong | E1 correct |
| 2. cowork_review_status PENDING_REVIEW | enum violation | wording wrong | E1 correct |
| 3. decision_lease_draft_id UUID NOT NULL | type wrong (PG=UUID) + nullable=YES | wording wrong on type; nullable matches spec | E1 partially correct (type yes, nullable application-level stricter) |

**Push back composite verdict**: **E1 wins 2 fully + 1 partially**. PM Option B dispatch packet wording was loose on 3 of 4 schema details. E1's PG empirical verification + spec cross-reference saved a runtime PG ERROR + CHECK violation.

---

## 3. 6 Attribute Mapping Correct Verify

### 3.1 attribute_n → min_sample_size

**V100 base**: `min_sample_size INTEGER NULL allowed` (V100 line 296)
**V100 COMMENT** (line 460-462): "INTEGER pre-registered 最低樣本量 (Wilson CI + n>=200 統計守門 gate); 起始 NULL allowed."

**Semantic concern**: V100 spec intends `min_sample_size` as a **threshold for promotion** (n>=200 gate); E1 stores **actual sample count** (n_observations). These are different concepts.

**Mitigation**: scope of V100 COMMENT is "pre-registered 最低樣本量"; in M4 pre-registration context, the **pre-registered minimum = actual observation count at DRAFT time** (M4 spec §3.2 N>=30 gate). Reasonable interpretation. PA spec amend should clarify.

**E2 verdict**: ✅ ACCEPTABLE (W2-F QA report §5.4 Option B explicitly recommends this mapping). LOW finding for PA spec amend follow-up.

### 3.2 attribute_p_bonferroni → bonferroni_corrected_p

**V103 EXTEND**: `bonferroni_corrected_p NUMERIC(10,8) CHECK [0,1]`
**E1 IMPL**: `bonferroni_p_clamped = max(0.0, min(1.0, raw_p_value))` (line 274)

**E2 verdict**: ✅ CORRECT. Clamp [0,1] matches CHECK constraint. PG-level CHECK + application-level clamp = defense-in-depth. PG empirical dry-run verified (E1 report §6.2).

**Note**: E1 stores `raw_p` clamped, not Bonferroni-corrected. Column NAME is `bonferroni_corrected_p` but value is raw_p clamped. W1-B spec §4 line 353 says "raw_p_value (用 K=2500 比較 in DB-side derived)". This is a **spec/naming drift** — value is raw_p, comparison gate is K=2500 corrected. Acceptable per spec line 353 ("derived in DB" comparison), but naming is misleading. LOW.

### 3.3 attribute_effect_size → replicability_score (composite weight 0.4)

**E1 IMPL**: `if cohens_d is not None: components.append((min(1.0, abs(cohens_d) / 3.0), 0.4))` (line 174-175)

**Spec deviation**:
- W1-B spec §4.3 line 469-485 defines `replicability_score = 0.3*subperiod + 0.4*cross_asset_count/25 + 0.3*cross_timeframe_count/5`
- W1-A spec §10.2 line 630: "跨 sub-period stability + cross-asset / cross-timeframe robustness score"

**E1's formula uses cohens_d (effect size)** — neither W1-A nor W1-B spec includes cohens_d in replicability_score composite. Cohen's d is **effect strength**, not **replicability**.

**E1's rationale** (report §7.3): "W2-F QA report §5.3 mapping line 695-697 「composite (#3 effect + #4 subperiod + #6 cluster)」明確列出 3 component". E2 reviewed W2-F QA report — there's no "line 695-697" mapping text matching this composite. W2-F QA §5.4 actually says `m4_attribute_effect_size → no existing column maps`.

**Likely root cause of E1's invention**: W1-B spec §4.3 formula requires `cross_asset_count + cross_timeframe_count` which spec line 813 says is **Sprint 3 defer** (Sprint 2 ships 1-asset / same-timeframe only). E1 had to invent a Sprint 2-shippable formula. Pragmatic workaround but **NOT spec-aligned**.

**E2 finding (HIGH)**: **HIGH SPEC DRIFT** — `_compose_replicability_score` invents formula not in W1-A or W1-B spec. Better options were:
- (a) Write `replicability_score = NULL` (PG nullable=YES) since Sprint 2 lacks cross_asset/cross_timeframe data
- (b) Raise 4th push back to PM for spec amend before IMPL
- (c) Use only `subperiod_pass` weight=1.0 (Sprint 2 ships subperiod attribute only)

**Decision impact**: this formula is the **discriminative signal** for M4 promotion path. Storing an out-of-spec composite means:
- Sprint 3 QC arbitration will need to re-compute historical replicability_score from raw 6 attribute audit log (extra cost)
- Cowork review (when activated) will see misleading scores

**Mitigation in E1 IMPL**:
- ✅ E1 self-flagged in report §8.1 as "QC review pending"
- ✅ E1 documents in report §10 spec deviation table
- ✅ E1's `build_audit_metadata` function preserves raw 6 attribute values for retroactive recompute

**E2 verdict**: ⚠️ HIGH spec drift documented + audit log preserves raw values → Sprint 3 retroactive recompute possible → **not blocking commit but mandatory PA spec amend + PM verdict before Sprint 2 cron production fire**.

### 3.4 attribute_subperiod_pass → replicability_score (composite weight 0.3)

**E1 IMPL**: `if subperiod_pass is not None: components.append((1.0 if subperiod_pass else 0.0, 0.3))` (line 177-178)

**Spec alignment**: ✅ W1-B spec §4.3 line 481 uses `subperiod_pass weight 0.3`. **E1 weight = 0.3 matches spec.**

### 3.5 attribute_silhouette → replicability_score (composite weight 0.3)

**E1 IMPL**: `if silhouette is not None: components.append((sil_norm, 0.3))` where `sil_norm = max(0.0, min(1.0, silhouette))` (line 180-181)

**Spec deviation**: W1-B spec §4.3 does NOT include silhouette in replicability_score. Silhouette is a **clustering quality** measure not a **replicability** measure. W1-A spec §10.2 cluster silhouette is a 6th-attribute Stage 2 gate (skip in Sprint 2).

**E2 finding (MEDIUM)**: E1 conflates clustering with replicability. Same spec deviation as §3.3.

**Mitigation**: spec §3.6 (W2-F QA report) says "Sprint 2 Stage 1 = silhouette skip (None default)". In practice silhouette will always be None in Sprint 2 → this weight branch unreachable → effectively `replicability_score = composite(cohens_d, subperiod)` in Sprint 2. Reduces impact severity but still spec drift.

### 3.6 attribute_graveyard_flag → not in PG (warning only)

**E1 IMPL**: not in INSERT params; preserved in `DraftWritebackPayload` dataclass + `build_audit_metadata` (line 354)

**Spec alignment**: ✅ W1-A spec §3.2 line 267-268: "graveyard_flag 不參與 pass criterion，只作 warning"; `attribute_enforcer.py:65` already "warning only 不阻 promote".

**Audit chain trace**: graveyard_flag → `DraftWritebackPayload.graveyard_flag` dataclass field → `build_audit_metadata()` returns dict with `attribute_graveyard_flag` key → caller (W2-D MIT cron) emits JSON log line. **Audit trail preserved**. ✅

**E2 verdict**: ✅ CORRECT.

### 3.7 6-attribute mapping summary

| Attribute | Mapping | E2 Verdict |
|---|---|---|
| 1. attribute_n | → min_sample_size | ✅ acceptable (W2-F Option B aligned) |
| 2. attribute_p_bonferroni | → bonferroni_corrected_p clamped | ✅ correct (naming drift LOW) |
| 3. attribute_effect_size | → replicability_score composite weight 0.4 | ⚠️ **HIGH SPEC DRIFT** (cohens_d not in W1-A/W1-B replicability formula) |
| 4. attribute_subperiod_pass | → replicability_score composite weight 0.3 | ✅ correct (weight matches spec) |
| 5. attribute_silhouette | → replicability_score composite weight 0.3 | ⚠️ MEDIUM drift (silhouette not in replicability formula) |
| 6. attribute_graveyard_flag | → warning only, build_audit_metadata | ✅ correct (audit chain preserved) |

**Net**: 4 correct + 1 HIGH drift + 1 MEDIUM drift. HIGH drift is the discriminative replicability_score formula.

---

## 4. Audit Chain 雙軌 Review

E1 採「`build_audit_metadata` function + `decision_lease_draft_id` UUID PG backref」雙軌 audit chain。

### 4.1 PG-side audit chain (decision_lease_draft_id)

- `learning.hypotheses.decision_lease_draft_id` UUID column stores lease UUID
- `GovernanceHubInterface.acquire_lease()` returns UUID; same UUID written into PG INSERT
- Future Lease table (V### TBD) can FK back via UUID

**Reconstructability**: given any `hypothesis_id`, caller can query:
```sql
SELECT decision_lease_draft_id FROM learning.hypotheses WHERE hypothesis_id = ?;
```
→ get lease UUID → trace via Lease table (when wired) or via log files.

**Trade-off**: FK constraint not added yet (per V103 EXTEND spec line 631 "FK 暫不加"); orphan UUID risk theoretical until production Lease table land. Acceptable scaffold. ✅

### 4.2 Log-side audit chain (build_audit_metadata)

- `build_audit_metadata(payload)` returns dict with 6 full attribute values including those not in PG (graveyard_flag, raw cohens_d, raw silhouette, raw_p)
- W2-D MIT will wire cron to emit JSON log per writeback

**Audit completeness**: ✅ 6 attribute raw values preserved → Sprint 3 retroactive QC arbitration of replicability_score formula possible without losing original data.

**Trade-off**: log file is not transactional with PG INSERT. If log emit fails between INSERT commit and lease release, audit chain has gap. **MEDIUM concern** but matches existing OpenClaw audit log pattern (e.g., `audit_log` JSONL emit is not 2PC with PG).

### 4.3 Chicken-egg analysis (decision_lease_draft_id NOT NULL invariant)

**E1 application-level invariant** (line 257-263):
```python
if decision_lease_draft_id is None:
    raise ValueError("decision_lease_draft_id 必 non-NULL — Lease backref 是 audit chain 必要條件")
```

**Lifecycle**:
1. Caller calls `GovernanceHubInterface.acquire_lease(actor="m4_pattern_miner")` → returns `uuid.uuid4()` synchronously
2. Caller passes UUID to `build_writeback_payload(..., decision_lease_draft_id=lease_id)`
3. Payload INSERT to PG
4. Caller calls `release_lease(lease_id)` after INSERT commit

**No chicken-egg** ✅ — UUID generation is client-side, no PG dependency. PG nullable=YES means orphan rows are theoretically possible if a bug bypasses `build_writeback_payload`, but E1's fail-loud invariant catches that.

**E2 finding (LOW)**: production wire-up (W2-D MIT) should add unit test verifying `build_writeback_payload` raises if `decision_lease_draft_id=None`. Already covered by existing test `test_payload_to_params_complete` indirectly. Acceptable.

---

## 5. Mac Pytest Non-Flaky Verify

**Run 1**:
```
89 passed in 0.04s
```

**Run 2** (after sleep 5):
```
89 passed in 0.04s
```

✅ **Non-flaky**. 70 existing + 19 new = 89 total.

**Note**: Mac scaffold stage is SSOT per `feedback_v_migration_pg_dry_run`. Real PG INSERT verification happens on Linux runtime (E1 report §6 already covered Linux PG empirical dry-run: happy path + 3 CHECK negative path).

---

## 6. 4 對抗 Grep Results

| # | Pattern | Expected | Actual | Result |
|---|---|---|---|---|
| 1 | `m4_attribute_` in `draft_writer.py` SQL INSERT block | 0 SQL hit | 0 in SQL (2 hits in MODULE_NOTE comment line 12-13) | ✅ |
| 2 | `PENDING_REVIEW` in `draft_writer.py` | 0 | 0 | ✅ |
| 3 | `evidence_json` in `draft_writer.py` SQL string | 0 SQL hit | 0 in SQL (3 hits in MODULE_NOTE comment line 12, 23, 59) | ✅ |
| 4 | `build_audit_metadata|decision_lease_draft_id` count ≥ 2 | ≥ 2 | 19 | ✅ |

**All 4 grep PASS.** Comment hits (m4_attribute_/evidence_json) are intentional traceability documentation explaining **why** these columns are NOT used. PASS.

Isolated SQL block verify (line 60-91 `DRAFT_INSERT_SQL`):
```
=== isolate INSERT SQL block (line 60-91) ===
(empty — 0 hit on m4_attribute_/PENDING_REVIEW/evidence_json in SQL string)
```
✅ Clean SQL.

---

## 7. 16 原則 + Hard Boundary Scan

### 16#7 學習 ≠ Live state mutate
- `is_promotable()` enforces `status ∈ {draft, exploratory, preregistered}` (attribute_enforcer.py:77)
- `build_writeback_payload` raises if `status_candidate ∉ whitelist` (draft_writer.py:252-256)
- INSERT SQL uses `%(status)s` placeholder, no hard-coded 'live' / 'promoted' / 'rejected' constants
- ✅ DRAFT only, no auto-promote past 'preregistered'

### 16#3 AI ≠ command
- DRAFT writeback wraps in Decision Lease (lease_type='M4_DRAFT_WRITEBACK')
- `live_order_intent=FALSE` invariant documented (line 373)
- TTL ≤ 5 min (line 378)
- ✅ AI output → Decision Lease, doesn't auto execute

### 16#8 交易可解釋
- 6 attribute fully preserved: 3 in PG (min_sample_size, bonferroni_corrected_p, replicability_score components) + 6 in `build_audit_metadata` log emit (full raw values)
- `decision_lease_draft_id` UUID backref
- `pre_reg_hash` SHA-256 of canonical JSON (deterministic, collision-resistant)
- ⚠️ **PARTIAL** — replicability_score composite formula spec drift means raw effect_size/subperiod/silhouette weights cannot be reconstructed from PG alone (must consult `build_audit_metadata` log)
- ✅ provided log is preserved → audit chain reconstructable via log + PG

### Hard boundary 5-gate
- ❌ 0 touch on `live_execution_allowed` / `system_mode` / `OPENCLAW_ALLOW_MAINNET` / authorization.json / Operator role
- ❌ 0 touch on Rust trading authority
- ❌ 0 cross-platform path violation (`grep '/home/ncyu|/Users/[^/]+' draft_writer.py` → 0 hit)
- ✅ Pure DRAFT writeback, learning lane only

### File size
- `draft_writer.py` 394 LOC (well under 800 warn, 2000 cap) ✅

### Comment style (bilingual-comment-style)
- MODULE_NOTE present, Chinese-first ✅
- Function docstrings explain "為什麼" not just "做什麼" ✅
- Existing English-only comments not touched (per current rule) ✅

---

## 8. Sprint 3 Detector Wire-Up Dispatch Readiness

### 8.1 Wire-up integration surface

W2-D MIT will wire production cron with:
1. `pattern_miner_stage_1.run_stage_1(dry_run=False, ...)` actual PG ingest + statistical
2. Lease acquire/release via real `ai_service.py` IPC (replace stub)
3. INSERT via `draft_writer.payload_to_params()` + `DRAFT_INSERT_SQL`
4. `build_audit_metadata()` → log emit per writeback

### 8.2 Wire-up dispatch conditions

| Condition | Status |
|---|---|
| Schema drift fix (BLOCKER-1 W2-F QA) | ✅ resolved by W1-C-R3 |
| `m4_attribute_*` SQL drift | ✅ removed (0 SQL hit) |
| 19 schema-grep regression test | ✅ in `test_source_loader_schema.py` |
| Mac pytest 89/89 | ✅ PASS non-flaky |
| Linux PG empirical INSERT dry-run | ✅ done by E1 (report §6) |
| Engine restart not required | ✅ pure Python no Rust touch |
| `replicability_score` formula spec amend | ⚠️ **PENDING PA + PM** |
| `evidence_json` PA task wording amend | ⚠️ **PENDING PA + PM** (LOW) |
| `min_sample_size` semantic clarify | ⚠️ **PENDING PA** (LOW) |

### 8.3 Readiness verdict

**CONDITIONAL READY**:
- ✅ Code-level: ready to commit + Sprint 3 cron-wire
- ⚠️ Spec-level: 1 HIGH (replicability_score formula) + 2 LOW (evidence_json wording / min_sample_size semantic) need PA amend before production cron fire
- ✅ Audit chain reconstructable via `build_audit_metadata` log emit (Sprint 3 retroactive QC arbitration possible)

**Recommendation to PM**:
1. Approve commit + push for Wave 3 unblock
2. Open PA spec amend ticket: clarify replicability_score Sprint 2 formula (NULL placeholder OR keep E1 invented composite)
3. Open PA spec amend ticket: remove `evidence_json` references from PM dispatch packet
4. Sprint 3 QC arbitrate replicability_score formula based on first week empirical data

---

## 9. Findings Summary

| Severity | Location | Description | Recommended action |
|---|---|---|---|
| **HIGH** | `draft_writer.py:150-188` `_compose_replicability_score` | Formula invented (cohens_d + subperiod + silhouette weighted) not in W1-A/W1-B spec. W1-B §4.3 defines subperiod + cross_asset + cross_timeframe. | PA spec amend before Sprint 2 cron production fire. E1 documented in report §8.1 as Open Q3 (acceptable mitigation since `build_audit_metadata` preserves raw values for retroactive recompute). |
| MEDIUM | `draft_writer.py:_compose_replicability_score` weight 0.3 silhouette | Silhouette is clustering quality, not replicability. W1-A spec §10.2 lists it as 6th attribute Stage 2 gate, not replicability composite. | Same as HIGH — PA spec amend. Sprint 2 silhouette always None per W2-F QA §3.6, so practical impact reduced. |
| LOW | PM Option B dispatch packet | Wording reference to `evidence_json` column (PG 0 hit), `PENDING_REVIEW` enum (PG enum is `PENDING`), `decision_lease_draft_id 'TEXT'` (PG type is UUID) | PA amend dispatch template. Not blocking. |
| LOW | `draft_writer.py:274` bonferroni_corrected_p naming drift | Column name says "bonferroni_corrected_p" but value is raw_p clamped (per W1-B spec §4 line 353 "derived in DB" comparison). | Add comment clarifying semantic OR rename column in future V### migration. |
| LOW | `min_sample_size` semantic drift | V100 COMMENT says "Wilson CI + n>=200 gate (threshold)"; E1 stores actual sample count. | PA spec amend clarification. Not blocking. |
| LOW | Audit log not 2PC with PG INSERT | `build_audit_metadata` log emit can fail between PG commit and lease release; audit gap window. | Acceptable per existing OpenClaw audit log pattern. Document in W2-D MIT cron wire-up spec. |

**0 CRITICAL. 1 HIGH (mitigated). 1 MEDIUM (low practical impact). 4 LOW.**

---

## 10. Verdict + 退回 E1 修復清單

### 10.1 Verdict

**APPROVE-WITH-CONDITIONS** — allow commit to land + push origin main + Wave 3 dispatch.

**Rationale**:
- 3 PM push back: E1 2 fully correct + 1 partial correct (saved runtime PG ERROR/CHECK violation)
- 5/6 attribute mapping correct + 1 HIGH spec drift mitigated by audit log preservation
- 0 CRITICAL, 0 hard boundary violation, 0 cross-platform issue
- Mac pytest 89/89 non-flaky
- 4 對抗 grep all PASS (SQL string clean)
- Net positive vs W1-C-R1/R2 dead-on-arrival schema drift state

### 10.2 Mandatory follow-up (not blocking commit but blocking Sprint 2 cron production fire)

1. **PA spec amend** (HIGH): `_compose_replicability_score` formula — either (a) accept E1 invented Sprint 2 baseline + Sprint 3 QC arbitrate, or (b) revert to NULL placeholder + Sprint 3 wire cross_asset/cross_timeframe per W1-B §4.3 + spec §10. **PM decision required**.
2. **PA spec amend** (LOW): remove `evidence_json` references from M4 dispatch packets.
3. **PA spec amend** (LOW): clarify `min_sample_size` semantic in V100 COMMENT (M4 pre-reg stores actual N as pre-registered minimum).
4. **W2-D MIT cron wire-up spec** (LOW): document `build_audit_metadata` log emit ordering vs PG INSERT commit + lease release (audit gap window mitigation).

### 10.3 Pass to E4

E2 PASS to E4 — E4 to verify:
- Mac pytest 89/89 (regression baseline)
- cargo test --release -p openclaw_core --lib 416/0 (no Rust change baseline)
- Linux PG empirical INSERT dry-run replay (E1 report §6 already done; E4 spot-check)
- 19 schema-grep regression test enforce on `DRAFT_INSERT_SQL`

---

**E2 R3 REVIEW DONE: APPROVE-WITH-CONDITIONS**
**Report path**: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-25--w2e_r3_w1c_r3_draft_writer_review.md`
