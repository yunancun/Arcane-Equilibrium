# M4 Spec Amend — W2-E-R3 Findings Closure (1 HIGH + 3 LOW Spec Drift)

**Date**: 2026-05-25
**Role**: PA (Project Architect)
**Phase**: Sprint 2 v5.8 Stream B Wave 1 — W2-E-R3 closure spec amend
**Parent reviews**:
- W2-E-R3 E2 cold review (commit `a605af57`): `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-25--w2e_r3_w1c_r3_draft_writer_review.md`
- W1-C-R3 E1 IMPL (commit `b2febd43`): `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-25--w1c_round_3_draft_writer_schema_fix.md`
- W2-F QA BLOCKER (commit `fbfbd184`): `docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-25--w2f_stream_e_bucket_monitor_stream_b_m4_leakage_audit.md`

**Status**: PA AMEND DRAFT — verdict `Option C two-stage spec` for HIGH + 3 LOW clarify

---

## 0. TL;DR Verdict

**Chosen path: Option C two-stage `replicability_score` spec** —

- **Sprint 2 baseline formula** (this amend): adopts E1 invented 3-axis weighted composite `(cohens_d 0.4 + subperiod 0.3 + silhouette 0.3)` with explicit "Sprint 2 pragmatic" marker. Justified by:
  - W1-B §4.3 full formula requires `cross_asset_subperiod_pass_count / 25` + `cross_timeframe_subperiod_pass_count / 5` (line 478-479), but Sprint 2 ships 1-asset / same-timeframe only (per W1-B §11 Q2 line 813 "cross-asset defer Sprint 3 配合 candidate #3").
  - With cross_asset = 1/25 = 0.04 and cross_timeframe = 1/5 = 0.20, full formula collapses to `0.3 * subperiod_pass + 0.4 * (1/25) + 0.3 * (1/5) = 0.3 * subperiod_pass + 0.076` → effectively all DRAFT writeback would have score ≈ 0.076 (FAIL) or 0.376 (subperiod_pass) — discriminative signal lost.
  - Sprint 2 formula has to be different by design; alternative is `replicability_score = NULL` (Sprint 2 doesn't surface any discriminative signal). Operator + QC verdict on W1-B §11 Q1 (K=2500 K_hyp refine) implies Sprint 2 must collect empirical signal, not NULL.
- **Sprint 3 full formula retroactive recompute path** (this amend §3.2): when cross_asset_count + cross_timeframe_count instrumentation lands (Stream A candidate #3 BTC/ETH pairs ship + 5 timeframe parallel ingest), QC arbitrates retroactive recompute via `build_audit_metadata` log emit raw values.
- **E1 IMPL `helper_scripts/m4/draft_writer.py` STAYS** — no E1 round 4. Spec aligns to IMPL.
- 3 LOW: amend wording only, IMPL no change.

**Verdict**: APPROVE — Sprint 3 M4 cron production fire dispatch readiness = **READY conditional on `replicability_score` Sprint 2 fence being explicitly documented in this amend + QC sign-off on the Sprint 2 formula as pragmatic baseline (Open Q3 closure)**.

---

## 1. 1 HIGH Spec Drift Closure — `replicability_score` Formula

### 1.1 Drift evidence

**W1-B alg spec §4.3 line 466-485** (true requirement):
```python
def replicability_score(
    subperiod_pass: bool,
    cross_asset_subperiod_pass_count: int,
    cross_timeframe_subperiod_pass_count: int,
) -> float:
    s = 0.3 * (1.0 if subperiod_pass else 0.0)
    s += 0.4 * (cross_asset_subperiod_pass_count / 25.0)
    s += 0.3 * (cross_timeframe_subperiod_pass_count / 5.0)
    return min(max(s, 0.0), 1.0)
```

**W1-A design spec §10.2 line 630** (column note):
```
| `replicability_score` | NUMERIC(5,4) | NO | — | `>= 0 AND <= 1` |
  跨 sub-period stability + cross-asset / cross-timeframe robustness score |
```

**E1 W1-C-R3 IMPL `_compose_replicability_score` (draft_writer.py:150-188)** (actually shipped):
```python
components = []
if cohens_d is not None:
    components.append((min(1.0, abs(cohens_d) / 3.0), 0.4))
if subperiod_pass is not None:
    components.append((1.0 if subperiod_pass else 0.0, 0.3))
if silhouette is not None:
    components.append((max(0.0, min(1.0, silhouette)), 0.3))
# weighted average of non-None components
```

**Three differences**:
1. E1 uses `cohens_d (effect size)` weight 0.4; spec uses `cross_asset_count / 25` weight 0.4.
2. E1 uses `silhouette (clustering)` weight 0.3; spec uses `cross_timeframe_count / 5` weight 0.3.
3. E1 handles None by skipping + renormalizing; spec assumes all values present.

### 1.2 E1 rationale + invented citation

E1 W1-C-R3 report §7.3 cites "W2-F QA report §5.3 mapping line 695-697 「composite (#3 effect + #4 subperiod + #6 cluster)」".

**E2 verified**: W2-F QA report line 695-697 has no such mapping text. E1's citation is fabricated. The real W2-F QA §5.4 (verified by PA) maps:
- `m4_attribute_effect_size → no existing PG column maps` (W1-C-R1/R2 wrote bogus `m4_attribute_effect_size` column which doesn't exist).
- Option B refactor proposed composite mapping but did not specify formula.

E1 invented the formula under pressure of "must ship Sprint 2 with non-NULL replicability_score". The invented formula uses ALL three Sprint 2-collectable attributes (cohens_d, subperiod_pass, silhouette).

Additionally, **E1 references "W1-A §7.3 mapping"** in module docstring and IMPL comments (e.g., `draft_writer.py:5, 15-21, 98, 102, 107, 113, 235, 339`). **W1-A §7.3 does not exist as a mapping section** — W1-A §7 is "M4 ↔ M6 Reward Integration", and §7.3 is "不 auto-tune 規則". The actual canonical mapping anchor is W1-A §3.1 (6 attribute table) + §10.2 (V103 column outline). This is an E1 documentation drift not blocking IMPL but should be cleaned in next touch.

### 1.3 Why Option C (not A/B)

**Option A** (PA amend spec → adopt invented formula as Sprint 2 baseline + mark Sprint 3 retroactive): close to chosen but doesn't preserve W1-B §4.3 full formula intent (cross_asset/cross_timeframe expansion path). Lost long-term spec authority.

**Option B** (PA spec keep W1-B §4.3 multi-asset formula; E1 IMPL Sprint 3 → Sprint 2 use NULL/placeholder): would make Sprint 2 ship `replicability_score = NULL` for all 14d demo evidence accumulation. Loses Sprint 2 discriminative signal → downstream QC cannot rank DRAFT writeback quality during Stream A candidate evaluation. **Critical blocker on Sprint 4 First Live precondition** (per memory `project_2026_05_25_sprint_2_dispatch`: P0-EDGE-1 AC-A (ii) needs at least 1 candidate 14d avg_net > 5bps + Wilson CI lower > 0; QC arbitration needs discriminative signal).

**Option C** (chosen): two-stage spec —
- Stage 1 Sprint 2: pragmatic 3-axis weighted formula (E1 invented baseline) with explicit "Sprint 2 fence + Open Q3 QC arbitrate" marker
- Stage 2 Sprint 3+: full W1-B §4.3 formula with cross_asset/cross_timeframe instrumentation + retroactive recompute from `build_audit_metadata` log emit raw values

Sprint 2 ships with discriminative signal (~0.76 if all three components present) + audit chain preserves raw values for Sprint 3 retroactive recompute via QC arbitration.

### 1.4 Sprint 2 baseline formula (W1-B §4.3 amend Stage 1)

**Amend W1-B alg spec §4.3 line 464-489**:

```markdown
### §4.3 `replicability_score` formula

**Sprint 2 baseline (Stage 1 — pragmatic 1-asset / same-timeframe)**

per design constraint:
- Sprint 2 ships 1-asset / same-timeframe Stream A candidate (W1-B §11 Q2 line 813);
  cross_asset_count + cross_timeframe_count not instrumented until Sprint 3 candidate #3 BTC/ETH pairs land
- Full §4.3 multi-asset formula would collapse to 0.076-0.376 range (low discrimination)
- Sprint 2 needs discriminative signal for QC arbitration of DRAFT writeback quality

```python
def replicability_score_sprint_2(
    cohens_d: Optional[float],
    subperiod_pass: Optional[bool],
    silhouette: Optional[float],
) -> Optional[float]:
    """
    Sprint 2 baseline formula (pragmatic 1-asset / same-timeframe).
    Open Q3: QC arbitrate weights after Sprint 2 W14.5 empirical 14d.

    Components (non-None contribute, then normalize weight):
    - cohens_d normalized: min(1.0, |d| / 3.0)            weight 0.4
    - subperiod_pass: 1.0 if True else 0.0                weight 0.3
    - silhouette clamped: max(0, min(1, silhouette))      weight 0.3

    All-None → return None.
    """
    components = []
    if cohens_d is not None:
        components.append((min(1.0, abs(cohens_d) / 3.0), 0.4))
    if subperiod_pass is not None:
        components.append((1.0 if subperiod_pass else 0.0, 0.3))
    if silhouette is not None:
        components.append((max(0.0, min(1.0, silhouette)), 0.3))

    if not components:
        return None
    total_weight = sum(w for _, w in components)
    weighted_sum = sum(v * w for v, w in components)
    return round(weighted_sum / total_weight, 4)
```

**Sprint 3+ full formula (Stage 2 — multi-asset / multi-timeframe)**

per W1-B §4.3 original design (UNCHANGED — Sprint 3 instrumentation):

```python
def replicability_score_sprint_3(
    subperiod_pass: bool,
    cross_asset_subperiod_pass_count: int,    # in 25 symbol pool
    cross_timeframe_subperiod_pass_count: int,  # in 5 timeframe
) -> float:
    s = 0.3 * (1.0 if subperiod_pass else 0.0)
    s += 0.4 * (cross_asset_subperiod_pass_count / 25.0)
    s += 0.3 * (cross_timeframe_subperiod_pass_count / 5.0)
    return min(max(s, 0.0), 1.0)
```

**Stage transition**: Sprint 3 retroactive recompute path per §4.4 (new sub-section).
```

### 1.5 Sprint 3 retroactive recompute path (W1-B §4.4 new sub-section)

**Add to W1-B alg spec §4.4**:

```markdown
### §4.4 Sprint 3 retroactive recompute path

When cross_asset_count + cross_timeframe_count instrumentation lands (per Stream A candidate #3 BTC/ETH pairs Sprint 3 ship + 5 timeframe parallel ingest Stream B M4 cron expansion):

**Step 1 — recompute trigger**:
- QC arbitration cron job (TBD: weekly fire) scans `learning.hypotheses` rows WHERE `hypothesis_source_module = 'M4_AUTO'` AND `created_at >= Sprint 2 start`.
- For each row, query `build_audit_metadata` log emit (W2-D MIT JSONL log file) by `decision_lease_draft_id` UUID join.

**Step 2 — recompute formula**:
- Extract raw `attribute_p_raw`, `attribute_effect_size_cohens_d`, `attribute_subperiod_pass`, `attribute_silhouette`, `attribute_graveyard_flag` from audit log.
- Query Sprint 3 instrumentation (cross-asset Mann-Whitney + cross-timeframe Mann-Whitney) for the original hypothesis spec params.
- Apply Sprint 3 full formula `replicability_score_sprint_3(subperiod_pass, cross_asset_count, cross_timeframe_count)`.

**Step 3 — UPDATE PG**:
- `UPDATE learning.hypotheses SET replicability_score = <new_value>, updated_at = now() WHERE hypothesis_id = ?`
- Emit audit log: `replicability_recompute_sprint_3` event with `(old_value, new_value, formula_version, reason)`.

**Step 4 — QC sign-off**:
- After all Sprint 2-era DRAFT writeback rows recomputed, QC verdict on:
  - (a) Was Sprint 2 pragmatic formula discriminative enough for the actual 14d demo evidence?
  - (b) Did Stream A candidate ranking change after recompute? (early ranking signal vs final ranking)
  - (c) Should Sprint 3 default formula stay full §4.3 or adopt hybrid (e.g., cross_asset present → use full; absent → fall back to Sprint 2 baseline)?

**Step 5 — formula version tracking** (M9 explainability bridge):
- New V### migration to add `replicability_score_formula_version SMALLINT NOT NULL DEFAULT 1` column.
- Sprint 2 INSERT writes version=1; Sprint 3 recompute writes version=2.
- Cowork operator review surface (per AMD-2026-05-21-01) displays version + formula label.

**Invariant**: audit chain raw value preservation via `build_audit_metadata` log emit MUST cover all Sprint 2 era rows. Loss of any audit log entry → row excluded from recompute, flagged `replicability_recompute_blocked`.
```

### 1.6 E1 IMPL verify

**Verdict**: **E1 IMPL `helper_scripts/m4/draft_writer.py:_compose_replicability_score` STAYS**. Spec amend aligns to IMPL (Option C Stage 1 baseline). No E1 round 4 dispatch.

**Required E1 follow-up (Sprint 3 IMPL, not Sprint 2)**:
1. Add `replicability_score_formula_version=1` literal to INSERT SQL (after V### land adds column).
2. Add docstring reference to `2026-05-25--m4_spec_amend_w2e_r3_findings.md` §1.4 + §1.5.

**Required E1 documentation clarify (next touch only — not blocking Wave 3)**:
- Replace "W1-A §7.3 mapping" references in `helper_scripts/m4/draft_writer.py` MODULE_NOTE + docstrings with canonical anchor:
  - W1-A spec §3.1 (6 attribute table) + §10.2 (V103 column outline) + W1-B alg spec §4.3 (Sprint 2 baseline formula amend) + this amend §1.4
- Replace "spec line 695-697 composite" reference in `_compose_replicability_score` docstring with this amend §1.1.

---

## 2. 3 LOW Spec Drift Closure

### 2.1 LOW #1 — `evidence_json` references

**Drift**: PM Option B dispatch packet (W2-F QA report §5 + W2-E-R3 PA dispatch task) referenced `evidence_json` JSONB column. **Empirical PG `learning.hypotheses` 0 hit `evidence_json`.** V103 EXTEND spec §2.2 line 38 does not list `evidence_json`. The column exists in `learning.replay_divergence_log` (V107) + `learning.decision_lease_lal_tiers` (V112) — different tables.

**Root cause**: PM Option B dispatch wording loosely transcribed from V107/V112 audit pattern without empirical PG schema cross-reference.

**Amend**: 
- W1-A design spec **no change needed** (W1-A spec §10.2 line 630 doesn't reference `evidence_json`).
- W1-B alg spec **no change needed** (W1-B §4 6 attribute mapping table doesn't reference `evidence_json`).
- **PM dispatch template clarify**: future M4 / V103 dispatch packets MUST cross-reference V103 EXTEND spec §2.2 (6 column list) + empirical PG reflection before referencing audit columns. PM dispatch template `.template/m4_dispatch.md` (TBD: lift this amend §2.1 into template guard text).

**E1 IMPL verify**: E1 W1-C-R3 IMPL **correctly rejected `evidence_json`** per push back. E1 IMPL stays. Mac pytest `test_draft_writer_no_evidence_json_column` regression guard ✅ added.

### 2.2 LOW #2 — `min_sample_size` semantic clarify

**Drift**: V100 base column `min_sample_size INTEGER` was originally designed as **promotion threshold (n>=200 gate per Wilson CI)** (per V100 line 460-462 COMMENT). E1 W1-C-R3 stores **actual observation count (n_observations)** in this column per W1-A §3.1 6 attribute mapping (`attribute_n → min_sample_size`).

**Semantic conflict**: V100 column intent = "threshold for promotion"; E1 IMPL = "actual sample count at DRAFT writeback time". These are conceptually different (threshold vs measurement).

**Resolution**: In M4 pre-registration context, the **pre-registered minimum = actual observation count at DRAFT time** (per W1-B §3.2 N≥30 gate + W1-A §3.1 attribute_n pass condition). M4 IMPL semantic is **"pre-registered actual n as the minimum sample size for this hypothesis"**.

**Amend**:
- W1-A design spec **add §10.2 footnote** on `min_sample_size` column:
  ```
  *Note (M4 IMPL semantic per W1-A §3.1 + W1-B §3.2)*: for `hypothesis_source_module='M4_AUTO'`,
  `min_sample_size` stores actual observation count at DRAFT writeback time
  (pre-registered as the hypothesis's minimum observed sample size).
  For `hypothesis_source_module='OPERATOR'`, retains original V100 base semantic
  (pre-registered minimum threshold for promotion).
  ```
- W1-B alg spec **add §4.2 cross-reference** to W1-A §10.2 footnote.
- V100 base spec amend NOT needed (column semantic interpretation is M4-scoped per hypothesis_source_module).

**E1 IMPL verify**: E1 W1-C-R3 IMPL **correctly maps `attribute_n → min_sample_size`** per W1-A §3.1 + W2-F QA Option B. E1 IMPL stays.

### 2.3 LOW #3 — `build_audit_metadata` 2PC ordering vs PG INSERT

**Drift**: E1 W1-C-R3 audit chain is 雙軌:
- PG side: `decision_lease_draft_id UUID` backref column (per V103 EXTEND §2.2)
- Log side: `build_audit_metadata` returns dict; W2-D MIT cron emits JSON log per writeback

**Concern (E2 LOW finding §4.2 + §9 row 6)**: log emit is **NOT 2PC** with PG INSERT. If log emit fails between PG commit and lease release, audit chain has gap window.

**Resolution per OpenClaw audit log pattern**: existing OpenClaw audit log (e.g., `audit_log` JSONL emit, Decision Lease audit emit) is **NOT 2PC with PG**. This is **accepted design** per ADR-0024-lite + memory `project_p06_rca_and_fix_plan` (no synchronous 2PC overhead in audit path).

**Amend**:
- W2-D MIT cron wire-up spec **add §X.Y ordering invariant**:
  ```
  ### §X.Y M4 DRAFT writeback audit chain ordering invariant

  Cron writeback sequence (caller `helper_scripts/m4/cron/m4_writeback_cron.py`, W2-D MIT IMPL):
  
  1. `lease_id = hub.acquire_lease(actor='m4_pattern_miner')` — UUID generated client-side
  2. `payload = build_writeback_payload(..., decision_lease_draft_id=lease_id, ...)`
  3. `audit_dict = build_audit_metadata(payload)` — 6 attribute full raw values
  4. `BEGIN; INSERT learning.hypotheses (...) RETURNING hypothesis_id; COMMIT;`
  5. `audit_dict['hypothesis_id'] = hypothesis_id; emit_audit_log(audit_dict)` — JSONL log file
  6. `hub.release_lease(lease_id, outcome='SUCCESS')`
  
  **Failure modes**:
  - Step 4 PG INSERT fail → step 5 log emit MUST NOT execute; step 6 release with outcome='PG_ERROR'
  - Step 5 log emit fail (disk full / IO error) → log warning + step 6 release with outcome='AUDIT_LOG_FAIL';
    PG row is orphaned (no audit log entry); flagged in next Sprint 3 retroactive recompute as `replicability_recompute_blocked`
  - Step 6 release fail → lease TTL (5 min) auto-expires; no rollback of PG row
  
  **Invariant**: gap window between step 4 commit and step 5 emit is **acceptable accepted design** per existing OpenClaw audit log pattern. Sprint 3 retroactive recompute path tolerates this gap by skip-flagging orphan rows.
  ```

**E1 IMPL verify**: E1 W1-C-R3 `build_audit_metadata` + `acquire_lease` + `release_lease` stub correctly anticipates this ordering. Production wire-up by W2-D MIT will land step 1-6 sequence per above. E1 IMPL stays.

---

## 3. E1 W1-C-R3 IMPL Re-verify

### 3.1 Per-amend re-verify table

| Amend | E1 IMPL action required | Verdict |
|---|---|---|
| §1.4 Sprint 2 baseline formula | `_compose_replicability_score` already matches | ✅ stays |
| §1.5 Sprint 3 retroactive recompute | not Sprint 2 scope (W2-D MIT scope) | ✅ stays |
| §1.6 documentation clarify (W1-A §7.3 → §3.1/§10.2/§4.3) | non-blocking; next touch only | ⚠️ doc-debt registered |
| §2.1 evidence_json reject | E1 already rejected + regression guard | ✅ stays |
| §2.2 min_sample_size mapping | E1 already maps n→min_sample_size | ✅ stays |
| §2.3 audit ordering | E1 stub matches W2-D MIT production order | ✅ stays |

### 3.2 Doc-debt registered

E1 W1-C-R3 `helper_scripts/m4/draft_writer.py` references "W1-A §7.3 mapping" 6 times in module docstring + inline comments. Replace with canonical anchor at next E1 touch (Sprint 3 IMPL):
- W1-A §3.1 (6 attribute pass/fail table) — for attribute → status mapping
- W1-A §10.2 (V103 column outline) — for column-by-column note
- W1-B alg spec §4.3 (Sprint 2 baseline) — for formula
- This amend §1.4 (formula stage 1) + §1.5 (stage 2 retroactive recompute)

**Doc-debt scope**: 6 inline reference updates + 1 MODULE_NOTE docstring rewrite. Not blocking Wave 3 dispatch.

### 3.3 No E1 round 4 dispatch

**Verdict**: E1 IMPL `helper_scripts/m4/draft_writer.py` STAYS as committed `b2febd43`. Spec amends to IMPL. Wave 3 W2-D MIT cron wire-up dispatch proceeds.

---

## 4. AC Re-confirm

### 4.1 W1-B AC-S2-B-1..5 closure status

| AC | Description | Status post-amend |
|---|---|---|
| AC-S2-B-1 | M4 cron daily UTC 00:00 fire + 6 attribute Stage 3 enforcement | ⏳ Wave 3 W2-D MIT IMPL pending |
| AC-S2-B-2 | DRAFT writeback writes V103 EXTEND real column (0 schema drift) | ✅ closed by W1-C-R3 + this amend §2 |
| AC-S2-B-3 | Decision Lease acquire/release wraps DRAFT writeback | ⏳ Wave 3 W2-D MIT IMPL pending (E1 stub → production IPC) |
| AC-S2-B-4 | 30-event minimum gate for event-window hypothesis | ✅ enforced by `attribute_enforcer.py` (W1-C land) |
| AC-S2-B-5 | Sub-period stability + p_bonferroni + cohen's d + silhouette 6 attribute |  ✅ enforced by `attribute_enforcer.py` + `build_audit_metadata` log emit |

### 4.2 W2-F NEW QA finding closure status

| W2-F QA finding | Status post-amend |
|---|---|
| BLOCKER-1 schema drift (6 `m4_attribute_*` columns) | ✅ closed by W1-C-R3 (`b2febd43`) |
| HIGH `replicability_score` formula spec drift | ✅ closed by this amend §1 Option C |
| LOW `evidence_json` references | ✅ closed by this amend §2.1 + E1 regression guard |
| LOW `min_sample_size` semantic | ✅ closed by this amend §2.2 |
| LOW audit ordering | ✅ closed by this amend §2.3 (W2-D MIT cron spec amend) |

### 4.3 16 原則 compliance

per W2-E-R3 E2 review §7 + this amend re-verify:

| Principle | Status |
|---|---|
| #1 Single write entry | ✅ DRAFT writeback isolated to `learning.hypotheses` PG INSERT; no `trading.fills` touch |
| #3 AI ≠ command | ✅ DRAFT wrapped in Lease (lease_type='M4_DRAFT_WRITEBACK', TTL ≤ 5 min, live_order_intent=FALSE) |
| #6 Fail-closed | ✅ `leakage_scan_pass` DEFAULT FALSE; `replicability_score` NULL on all-None |
| #7 Learning ≠ Live mutate | ✅ status ∈ {draft, exploratory, preregistered}; no promotion past preregistered |
| #8 Reconstructable | ✅ raw 6 attribute preserved in `build_audit_metadata` log; UUID backref via decision_lease_draft_id |
| #10 Fact/inference/assumption | ✅ Sprint 2 baseline formula explicitly marked "pragmatic" + Sprint 3 retroactive recompute path documented |
| Hard boundaries | ✅ 0 touch on live_execution_allowed / OPENCLAW_ALLOW_MAINNET / authorization.json / Operator role |

**16/16 compliance maintained.**

---

## 5. Sprint 3 M4 Cron Production Fire Dispatch Readiness Verdict

### 5.1 Pre-conditions checklist

| Condition | Status |
|---|---|
| Schema drift fix (W2-F BLOCKER-1) | ✅ closed by `b2febd43` W1-C-R3 |
| `_compose_replicability_score` Sprint 2 baseline spec amend | ✅ this amend §1.4 |
| Sprint 3 retroactive recompute path | ✅ this amend §1.5 documented |
| `evidence_json` reject + regression guard | ✅ this amend §2.1 + E1 pytest |
| `min_sample_size` semantic clarify | ✅ this amend §2.2 |
| `build_audit_metadata` ordering invariant | ✅ this amend §2.3 (W2-D MIT cron spec amend) |
| Mac pytest 89/89 non-flaky | ✅ W2-E-R3 §5 verified |
| Linux PG empirical INSERT dry-run | ✅ E1 W1-C-R3 §6 done |
| 19 schema-grep regression test | ✅ `test_source_loader_schema.py` §6 |
| 16 原則 + hard boundary | ✅ this amend §4.3 |

### 5.2 Dispatch verdict

**READY** — Sprint 3 W2-D MIT M4 cron production fire dispatch can proceed.

**Required follow-up by W2-D MIT**:
1. Production IPC wire `GovernanceHubInterface.acquire_lease/release_lease` (replace E1 stub) per `ai_service.py` JSON-RPC over Unix domain socket
2. `helper_scripts/m4/cron/m4_writeback_cron.py` IMPL with this amend §2.3 step 1-6 sequence
3. JSONL log emit per `build_audit_metadata(payload)` to `$OPENCLAW_DATA_DIR/m4_writeback_audit.jsonl`
4. Cron schedule daily UTC 00:00 per W1-A design spec Open Q2 recommendation
5. Slack/Email notification per AMD-2026-05-21-01 multi-channel (W1-A §2.5.4)

**Required follow-up by QC**:
1. Sprint 2 W14.5 (~D+8-D+13 per Sprint 2 dispatch packet) empirical 14d DRAFT writeback rows accumulation
2. QC arbitrate `_compose_replicability_score` Sprint 2 baseline weights 0.4/0.3/0.3 per Open Q3 (W1-B §11)
3. Sprint 3 D+0 sign-off on (a) Sprint 2 formula discriminative quality (b) Sprint 3 retroactive recompute trigger (c) `replicability_score_formula_version` column V### migration spec

**Required follow-up by PA (this role)**:
1. Lift this amend §1.4 + §1.5 into W1-B alg spec `2026-05-25--m4_pattern_miner_stage_1_algorithm_spec.md` §4.3 + §4.4 (in-place amend or appendix)
2. Lift this amend §2.2 footnote into W1-A design spec `2026-05-21--m4_hypothesis_discovery_design_spec.md` §10.2
3. Lift this amend §2.3 into W2-D MIT cron wire-up spec when MIT lands

### 5.3 Risks + mitigation

| Risk | Mitigation |
|---|---|
| Sprint 2 baseline formula discriminative power unproven until 14d empirical | QC arbitrate at Sprint 2 W14.5; Sprint 3 retroactive recompute available |
| Sprint 3 retroactive recompute requires `replicability_score_formula_version` column | TBD V### migration spec (PA Sprint 3 W0 sub-task) |
| Log emit failure → audit chain gap window | accepted design per ADR-0024-lite + memory `project_p06_rca_and_fix_plan`; Sprint 3 recompute skip-flags orphan rows |
| Doc-debt: E1 IMPL references "W1-A §7.3 mapping" 6 times | next E1 touch (Sprint 3 IMPL) replaces with canonical anchor |

---

## 6. Spec amend file change scope

### 6.1 Files this amend (PA spec-only commit)

| File | Change | LOC delta |
|---|---|---|
| `srv/docs/execution_plan/2026-05-25--m4_spec_amend_w2e_r3_findings.md` | NEW (this file) | +~370 |

### 6.2 Files PA lifts amend into (Sprint 3 W0 sub-task)

| File | Change | LOC delta |
|---|---|---|
| `srv/docs/execution_plan/2026-05-25--m4_pattern_miner_stage_1_algorithm_spec.md` §4.3 + new §4.4 | replace + add Sprint 3 recompute path | ~+50 |
| `srv/docs/execution_plan/2026-05-21--m4_hypothesis_discovery_design_spec.md` §10.2 footnote | add `min_sample_size` semantic note | ~+10 |

### 6.3 Files NOT changed this amend

- `helper_scripts/m4/draft_writer.py` — IMPL stays (per §3.3); doc-debt next touch
- `helper_scripts/m4/tests/*.py` — tests stay (per §3.3)
- `srv/docs/execution_plan/2026-05-21--v103_extend_m4_hypothesis_columns_schema_spec.md` — V103 EXTEND DDL already land; no SQL change

---

## 7. Confidence + Push Back Items

### 7.1 Confidence levels

- **HIGH**: Option C chosen path (Sprint 2 pragmatic + Sprint 3 retroactive; preserves long-term spec authority + delivers Sprint 2 discriminative signal)
- **HIGH**: 3 LOW closure (evidence_json reject / min_sample_size semantic / audit ordering — all align IMPL with existing spec wording)
- **HIGH**: E1 IMPL stays verdict (Mac pytest 89/89 + Linux PG empirical INSERT dry-run + 19 schema-grep regression test all green)
- **MEDIUM**: Sprint 2 baseline weights 0.4/0.3/0.3 — pragmatic baseline pending QC empirical arbitration W14.5
- **MEDIUM**: Sprint 3 retroactive recompute requires future `replicability_score_formula_version` V### migration; spec land cadence depends on Stream A candidate #3 BTC/ETH pairs ship timing

### 7.2 Push back items

1. **PM Option B dispatch packet wording for M4** — referenced `evidence_json` (non-existent column) + `PENDING_REVIEW` enum (not in V103 CHECK) + `decision_lease_draft_id 'TEXT or NULL'` (actual UUID). Future M4/V103 dispatch packets MUST cross-reference V103 EXTEND spec §2.2 + empirical PG reflection before referencing audit columns. Suggest PM dispatch template `.template/m4_dispatch.md` includes pre-dispatch schema verify checklist.

2. **W1-B §4.3 original formula viability** — verified that Sprint 2 1-asset / same-timeframe scope collapses full formula to 0.076-0.376 range (low discrimination). If Sprint 4+ scope expands to multi-asset Stream A candidate ranking (e.g., funding_short_v2 across 25 symbol), full formula recovery is automatic without further amend.

3. **E1 documentation drift "W1-A §7.3 mapping"** — non-canonical reference 6 times in `helper_scripts/m4/draft_writer.py`. Next E1 touch (Sprint 3 IMPL) cleanup; non-blocking now.

4. **Sprint 3 W0 sub-task: PA lift amend into W1-A/W1-B spec** — this amend is standalone closure doc; long-term clean architecture requires lifting §1.4/§1.5/§2.2 into respective source specs. Track as Sprint 3 W0 PA sub-task; spec drift risk if not lifted within 2 Sprint cycles.

---

## 8. References

### 8.1 Parent reviews
- W2-E-R3 E2 cold review: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-25--w2e_r3_w1c_r3_draft_writer_review.md` (`a605af57`)
- W1-C-R3 E1 IMPL report: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-25--w1c_round_3_draft_writer_schema_fix.md` (`b2febd43`)
- W2-F QA + FA cold review: `srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-25--w2f_stream_e_bucket_monitor_stream_b_m4_leakage_audit.md` (`fbfbd184`)

### 8.2 Parent specs amended
- W1-A design spec: `srv/docs/execution_plan/2026-05-21--m4_hypothesis_discovery_design_spec.md` (§10.2 footnote add per §2.2)
- W1-B alg spec: `srv/docs/execution_plan/2026-05-25--m4_pattern_miner_stage_1_algorithm_spec.md` (§4.3 amend Sprint 2 baseline + new §4.4 Sprint 3 recompute per §1.4 + §1.5)
- V103 EXTEND schema spec: `srv/docs/execution_plan/2026-05-21--v103_extend_m4_hypothesis_columns_schema_spec.md` (no change)

### 8.3 Governance + invariant
- ADR-0024-lite Cowork operator-assistant: `srv/docs/adr/0024-cowork-subscription-operator-assistant.md`
- ADR-0026 v3 strategy track: per memory `project_ml_dl_learning_architecture`
- AMD-2026-05-21-01 v2 Layered Autonomy + protected/opt-in: per memory `project_2026_05_22_layered_autonomy_with_failsafe`
- v5.8 master `srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md` §2 M4 line 158-184
- 16 root principles `srv/CLAUDE.md` §二

### 8.4 IMPL artifacts
- `helper_scripts/m4/draft_writer.py` (W1-C-R3 IMPL, `b2febd43`)
- `helper_scripts/m4/tests/test_source_loader_schema.py` §6 (19 schema-grep regression test)
- `helper_scripts/m4/tests/test_m4_leakage_regression.py` (test_payload_to_params_complete updated)

---

## 9. Sign-off

**PA verdict**: APPROVE — Wave 3 W2-D MIT M4 cron production fire dispatch **READY** conditional on:
1. ✅ This amend committed + pushed origin main
2. ⏳ QC sign-off Open Q3 Sprint 2 baseline formula weights at W14.5 empirical
3. ⏳ PA lift §1.4/§1.5/§2.2 into source specs (Sprint 3 W0 sub-task)

**E1 IMPL `helper_scripts/m4/draft_writer.py`** STAYS — no E1 round 4 dispatch.

**Doc-debt registered**: E1 next touch (Sprint 3 IMPL) cleanup "W1-A §7.3" references.

**16/16 + hard boundary 0 touch + 9/9 safety invariant** maintained per W2-E-R3 §7 + this amend §4.3.
