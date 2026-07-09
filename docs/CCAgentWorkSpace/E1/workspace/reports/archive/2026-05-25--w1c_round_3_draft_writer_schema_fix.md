# W1-C Round 3 — M4 draft_writer.py Schema Drift Fix（per W2-F QA + FA HIGH BLOCKER 退回）

**Date**: 2026-05-25
**Role**: E1 (Backend Developer)
**Phase**: Sprint 2 v5.8 Stream B Wave 1 W1-C Round 3
**Parent verdict**: `docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-25--w2f_stream_e_bucket_monitor_stream_b_m4_leakage_audit.md` BLOCKER-1 (commit `fbfbd184`)
**Status**: IMPL DONE — awaiting E2 re-review

---

## 1. 任務摘要

W2-F QA + FA cold review catch `helper_scripts/m4/draft_writer.py:25-50` INSERT SQL 寫 6 個 **不存在** 於 production `learning.hypotheses` 的 `m4_attribute_*` column → 首次 cron fire 必 PG ERROR `column "m4_attribute_n" of relation "hypotheses" does not exist`。

**PM 拍 Option B refactor INSERT 不新加 schema column**：用 W1-A spec §7.3 6 attribute → V100 base + V103 EXTEND real column composite mapping。

**Push back point**：PA task §「V103 EXTEND 6 real column + evidence_json」中提到的 `evidence_json` JSONB column **empirical PG 不存在** + W1-A spec §7.3 mapping 也未要求；不採該方案。改採嚴格對齊 W1-A §7.3 spec mapping。

---

## 2. 修改清單

### 2.1 修改 file（2 個）

| File | 改動 | 行數變化 |
|---|---|---|
| `helper_scripts/m4/draft_writer.py` | INSERT SQL 完整 refactor + `DraftWritebackPayload` schema 對齊 + `_compose_replicability_score` 3-axis composite + `_compute_pre_reg_hash` SHA-256 + engine_mode validation | 200 → 332 |
| `helper_scripts/m4/tests/test_m4_leakage_regression.py` | `test_payload_to_params_complete` required_keys 對齊新 schema | 11 行 diff |

### 2.2 新增測試（17 個 新 schema-grep regression test）

| File | 改動 | 新 test |
|---|---|---|
| `helper_scripts/m4/tests/test_source_loader_schema.py` | §6 新區段：draft_writer schema-grep regression | 19 個（含 6 個 parametrized `test_draft_writer_no_m4_attribute_column[...]`） |

**測試清單**：
- §6 §6 draft_writer schema-grep（19 test）：
  - 6 parametrized：`test_draft_writer_no_m4_attribute_column[m4_attribute_n|p_bonferroni|effect_size|subperiod_pass|graveyard_flag|silhouette]`
  - `test_draft_writer_writes_v100_base_required_columns` — V100 base 5 NOT NULL 必出現
  - `test_draft_writer_writes_v103_extend_real_columns` — V103 EXTEND 6 real column 必出現
  - `test_draft_writer_w1a_spec_7_3_mapping_n_to_min_sample_size`
  - `test_draft_writer_hypothesis_source_module_explicit_m4_auto`
  - `test_draft_writer_cowork_review_status_explicit_none`
  - `test_draft_writer_no_evidence_json_column` — PA task expected column 不存在於 PG 的 regression guard
  - `test_draft_writer_no_status_promote_past_preregistered`
  - `test_draft_writer_returns_hypothesis_id_for_audit_backref`
  - `test_draft_writer_engine_mode_validation_blocks_paper`
  - `test_draft_writer_replicability_score_composite_range`
  - `test_draft_writer_bonferroni_p_clamped_to_unit_interval`
  - `test_draft_writer_pre_reg_hash_deterministic`
  - `test_draft_writer_payload_to_params_excludes_caller_metadata`

---

## 3. 關鍵 diff

### 3.1 INSERT SQL refactor（13 column，全對齊真實 PG schema）

**Before** (W1-C Round 1/2)：
```sql
INSERT INTO learning.hypotheses (
    hypothesis_id, strategy_name, status,
    m4_attribute_n,            -- BLOCKER: 不存在
    m4_attribute_p_bonferroni, -- BLOCKER: 不存在
    m4_attribute_effect_size,  -- BLOCKER: 不存在
    m4_attribute_subperiod_pass, -- BLOCKER: 不存在
    m4_attribute_graveyard_flag, -- BLOCKER: 不存在
    m4_attribute_silhouette,   -- BLOCKER: 不存在
    hypothesis_source_module, leakage_scan_pass,
    bonferroni_corrected_p, replicability_score,
    decision_lease_draft_id, cowork_review_status, created_at
) VALUES (...);
```

**After** (W1-C Round 3 — empirical PG schema 對齊)：
```sql
INSERT INTO learning.hypotheses (
    -- V100 base required (5 NOT NULL)
    strategy_name, pre_reg_ts, pre_reg_hash, status, engine_mode,
    -- V100 base optional → W1-A §7.3 attribute_n mapping
    min_sample_size,
    -- V103 EXTEND 6 real column
    hypothesis_source_module, leakage_scan_pass,
    bonferroni_corrected_p, replicability_score,
    decision_lease_draft_id, cowork_review_status,
    created_at
) VALUES (
    %(strategy_name)s, %(pre_reg_ts)s, %(pre_reg_hash)s,
    %(status)s, %(engine_mode)s, %(n_observations)s,
    'M4_AUTO', %(leakage_scan_pass)s,
    %(bonferroni_corrected_p)s, %(replicability_score)s,
    %(decision_lease_draft_id)s, 'NONE',
    %(created_at)s
)
RETURNING hypothesis_id
```

### 3.2 W1-A spec §7.3 6 attribute mapping

| 6 attribute | 真實 PG column | 處理方式 |
|---|---|---|
| `attribute_n` | `min_sample_size` (V100 base INTEGER) | INSERT direct |
| `attribute_p_bonferroni` | `bonferroni_corrected_p` (V103 EXTEND NUMERIC(10,8) CHECK [0,1]) | INSERT direct + clamp [0,1] |
| `attribute_effect_size` (Cohen's d) | composite → `replicability_score` (V103 EXTEND NUMERIC(5,4)) | weight 0.4，`|d|/3` capped at 1.0 |
| `attribute_subperiod_pass` | composite → `replicability_score` | weight 0.3，1.0 if True else 0.0 |
| `attribute_silhouette` | composite → `replicability_score` | weight 0.3，clamp [0,1] |
| `attribute_graveyard_flag` | **不寫 PG**（caller log only） | warning only，per attribute_enforcer 既有設計 |

### 3.3 `_compose_replicability_score` 3-axis composite

```python
def _compose_replicability_score(cohens_d, subperiod_pass, silhouette):
    components = []
    if cohens_d is not None:
        components.append((min(1.0, abs(cohens_d) / 3.0), 0.4))
    if subperiod_pass is not None:
        components.append((1.0 if subperiod_pass else 0.0, 0.3))
    if silhouette is not None:
        components.append((max(0.0, min(1.0, silhouette)), 0.3))
    if not components:
        return None
    total_w = sum(w for _, w in components)
    return round(sum(v * w for v, w in components) / total_w, 4)
```

**設計**：任一 component 為 None 時跳過該 weight 並重新歸一；所有 None → None。weights 0.4/0.3/0.3 是 W1-B spec §4.3 Open Q3 baseline；Sprint 3 後 QC 仲裁終值。

### 3.4 `_compute_pre_reg_hash` SHA-256 對 6 attribute snapshot

V100 base `pre_reg_hash` NOT NULL — 為「pre-registration 不變式」hash（per V100 spec + ADR-0026 v3）。M4 場景 spec = 6 attribute snapshot 的 canonical JSON SHA-256 hex。同 input 必同 hash（deterministic test verified）。

### 3.5 engine_mode validation 加入 application-level fail-loud

```python
if engine_mode not in ("live", "live_demo"):
    raise ValueError(f"M4 DRAFT writeback engine_mode 必 IN ('live','live_demo')，got engine_mode='{engine_mode}'")
```

V100 base CHECK enum 含 4 值（paper/demo/live_demo/live）但 M4 場景 reject paper/demo（per CLAUDE.md §七 + memory `project_engine_mode_tag_live_demo`）。

### 3.6 `build_audit_metadata` 新 function — 6 attribute 完整 audit log emit

```python
def build_audit_metadata(payload) -> dict:
    return {
        "decision_lease_draft_id": str(payload.decision_lease_draft_id),
        # 6 attribute full snapshot
        "attribute_n": payload.n_observations,
        "attribute_p_raw": payload.raw_p_value,
        "attribute_p_bonferroni_clamped": payload.bonferroni_corrected_p,
        "attribute_effect_size_cohens_d": payload.cohens_d,
        "attribute_subperiod_pass": payload.subperiod_pass,
        "attribute_graveyard_flag": payload.graveyard_flag,
        "attribute_silhouette": payload.silhouette,
        ...
    }
```

**為什麼存在**：6→4 composite mapping 失去 graveyard_flag / raw cohens_d / raw silhouette 等審計痕跡。audit chain 走 `decision_lease_draft_id` backref (PG) + cron logger emit (log file) 雙軌；W2-D MIT 接 cron 時呼此 function 寫 audit log。

---

## 4. 治理對照

| W2-F QA verdict 點 | 修復狀態 |
|---|---|
| BLOCKER-1: 6 m4_attribute_* → V103 EXTEND real column | ✅ (Option B refactor) |
| BLOCKER-1 §5.4 spec mapping `attribute_n` → `min_sample_size` | ✅ |
| BLOCKER-1 §5.4 spec mapping `attribute_p_bonferroni` → `bonferroni_corrected_p` | ✅ |
| BLOCKER-1 §5.4 spec mapping `effect_size/subperiod/silhouette` → composite `replicability_score` | ✅ |
| MEDIUM-1 schema-grep regression for draft_writer | ✅ 19 新 test |
| `hypothesis_source_module='M4_AUTO'` 顯式 hard-code | ✅ |
| `cowork_review_status='NONE'` 顯式 hard-code | ✅ |
| W1-A §7.3 mapping invariant ＝ W2-F QA report §5.3 mapping | ✅ |
| audit chain 走 `decision_lease_draft_id` backref（non-NULL） | ✅ |
| RETURNING hypothesis_id 為 caller audit log emit | ✅ |

---

## 5. Mac SSOT verify

### 5.1 pytest helper_scripts/m4/
```
89 passed in 0.04s
```
70 existing PASS (Round 2) + 19 new W1-C Round 3 schema test PASS = 89 total。

### 5.2 cargo test --release -p openclaw_core --lib
```
test result: ok. 416 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out
```
baseline 不退（與 W1-C Round 2 + W2-D 一致；本改動純 Python，0 Rust 影響）。

### 5.3 4 對抗式 grep self-verify

| Pattern | hit 期望 | 實際 | 結果 |
|---|---|---|---|
| `m4_attribute_` in draft_writer.py SQL string | 0 | 0 | ✅ |
| `evidence_json` in draft_writer.py SQL string | 0 | 0 | ✅ |
| `hypothesis_source_module|leakage_scan_pass|bonferroni_corrected_p` ≥ 3 | ≥ 3 | 26（含 comment + SQL + Python code） | ✅ |
| `pre_reg_hash|replicability_score` ≥ 1 | ≥ 1 | 31 | ✅ |

`m4_attribute_` + `evidence_json` 在 module-level comment 出現 5 處全是 MODULE_NOTE 解釋為何不寫 PG（traceability 設計）— 非 SQL code hit。Python script verify SQL string 內 0 hit。

---

## 6. Linux PG empirical INSERT dry-run（per Step 5）

### 6.1 Happy path（13 column INSERT）
```bash
ssh trade-core "psql ... -c 'BEGIN; INSERT ... VALUES (...) RETURNING ...; ROLLBACK;'"
```
**結果**：
```
 hypothesis_id |  strategy_name  |    status     | engine_mode | hypothesis_source_module | bonferroni_corrected_p | replicability_score | cowork_review_status
---------------+-----------------+---------------+-------------+--------------------------+------------------------+---------------------+----------------------
             1 | m4_dry_run_test | preregistered | live_demo   | M4_AUTO                  |             0.00001500 |              0.6500 | NONE
(1 row)

INSERT 0 1
ROLLBACK
```
✅ 0 ERROR + INSERT success + RETURNING 8 column 完整返回 + ROLLBACK 不留 row。

### 6.2 CHECK constraint negative path verify

**6.2a** `hypothesis_source_module='XYZ'`（非 3 enum）：
```
ERROR:  new row for relation "hypotheses" violates check constraint "hypotheses_hypothesis_source_module_check"
```
✅ PG schema-level enforce 對齊 V103 EXTEND CHECK。

**6.2b** `bonferroni_corrected_p=2.5`（出 [0,1] 範圍）：
```
ERROR:  new row for relation "hypotheses" violates check constraint "hypotheses_bonferroni_corrected_p_check"
```
✅ PG schema-level CHECK enforce。Application clamp [0,1] 防後置撞 CHECK 是雙重防護。

**6.2c** Boundary 1.0/0.0 接受：
```
INSERT 0 1 → hypothesis_id=5
```
✅ Edge case 不被 reject。

**注意**：`status='live'` 在 PG layer 不會 reject（V100 base CHECK 11 enum 含 'live'）；M4 application-level fail-loud 是 audit invariant 唯一防線。

---

## 7. 設計決策 + 對 PA task 的 push back

### 7.1 不引入 evidence_json column（push back）

PA task §「V103 EXTEND 6 real column + evidence_json」: `evidence_json` 不存在於 `learning.hypotheses`（empirical PG `\d learning.hypotheses` verify 2026-05-25：19 column 0 hit）。

W1-A spec §7.3 6 attribute mapping（commit `d1add583` PA-amend）也未要求 evidence_json。`evidence_json` 是 `learning.replay_divergence_log` (V107) 與 `learning.decision_lease_lal_tiers` (V112) 的 column，不是 `learning.hypotheses`。

**選擇**：嚴格依 W1-A §7.3 spec 6→4 composite mapping；6 attribute 完整 metadata 由 `build_audit_metadata` function 提供供 cron logger emit（W2-D MIT 接通時 wire）。`decision_lease_draft_id` backref 是 PG-side audit chain。

### 7.2 為什麼 `attribute_graveyard_flag` 不寫 PG

`attribute_enforcer.py:65` 既有設計「graveyard_flag warning only 不阻 promote」。本 IMPL 對齊：graveyard_flag 不入 PG，但保留在 `DraftWritebackPayload` dataclass + audit metadata；avoid silent 完全丟失。

### 7.3 為什麼 replicability_score composite 用 3-axis weighted average

W2-F QA report §5.3 mapping line 695-697 「composite (#3 effect + #4 subperiod + #6 cluster)」明確列出 3 component。W1-B spec §4.3 Open Q3 提到 weights 待 QC review；本 IMPL 用 baseline 0.4/0.3/0.3，Sprint 3 後 QC 仲裁修正。

### 7.4 為什麼 pre_reg_hash 是 SHA-256 of canonical JSON

V100 base `pre_reg_hash` TEXT NOT NULL 是 pre-registration 不變式（per ADR-0026 v3 + DOC-08 §12）。M4 場景 spec snapshot = 6 attribute snapshot；canonical JSON + SHA-256 提供 deterministic / collision-resistant hash 防後置篡改。長度 64 hex char。

### 7.5 為什麼 application 層 engine_mode reject paper/demo

V100 base CHECK 4 enum 含 paper/demo；M4 場景按 CLAUDE.md §七 + memory `project_engine_mode_tag_live_demo` 限 `IN ('live','live_demo')`。schema-level 沒有 narrow enforce；application-level fail-loud 是必要。

---

## 8. 不確定 / Sprint 3 follow-up（不阻 W1-C Round 3 closure）

1. **replicability_score weights 仲裁**：W1-B spec §4.3 Open Q3 weights 0.4/0.3/0.3 baseline；Sprint 3 cron 跑第一週收集 empirical → PM + PA + QC 三角仲裁終值。
2. **GovernanceHub `M4_DRAFT_WRITEBACK` lease type IPC 接通**：scaffold 階段 stub UUID；Sprint 3 W2-D MIT IMPL 接通 ai_service.py。
3. **`build_audit_metadata` cron logger wire**：函式已備；W2-D MIT 接 cron 時呼此 function emit JSON log line + 同步 metadata 到 audit log（per W1-B spec §9.5 audit chain）。
4. **W1-A spec amend 建議**：spec §7.3 line 701-706 mapping 已對齊，但 W2-F QA report §5.4 提到 `effect_size` 「no existing column maps」— 建議 PA 在 spec amend 加註明 effect_size 走 composite（避免未來 W2-D 接 cron 重蹈 W1-C Round 1 教訓）。
5. **PA task `evidence_json` clarify**：PA task 提及 evidence_json 不存在；本 IMPL push back；建議 PM/PA 在 dispatch packet 中 amend correction（或新增 V### migration ADD evidence_json JSONB 後 W2-D MIT IMPL 切換）。

---

## 9. Operator 下一步（per chain E1→E2→E4→QA→PM）

1. **主會話派 E2 cold review** (含 push back evidence_json 評估)：
   - 6 m4_attribute_* → V103 EXTEND real column 對齊驗（SQL string grep）
   - W1-A §7.3 6 attribute composite mapping 完整驗（pre_reg_hash deterministic / replicability_score [0,1] / bonferroni clamp）
   - 19 schema-grep regression test 跑（pytest test_source_loader_schema.py）
   - W1-A spec / W2-F QA report §5.3 alignment check
   - `evidence_json` push back 評估（PA task vs empirical PG）

2. **主會話派 E4 regression**：
   - pytest helper_scripts/m4/: 89/89 PASS（Mac SSOT）
   - cargo test --release -p openclaw_core --lib: 416/0 PASS baseline 不退
   - Linux PG empirical INSERT dry-run（happy + 3 CHECK negative path）

3. **主會話派 W2-F QA re-audit**：
   - BLOCKER-1 closure 對齊
   - 12 SQL self-grep + 4 對抗式 grep 重跑（含 hidden hit 過濾）
   - W1-A §7.3 mapping invariant 對齊

4. **PM commit + push**（per chain E1→E2→E4→QA→PM）：
   ```
   fix(m4-w1c-round-3): 6 m4_attribute_* schema drift → V103 EXTEND real column refactor + W1-A §7.3 composite mapping

   per W2-F QA + FA HIGH BLOCKER (commit fbfbd184):
   - draft_writer.py INSERT SQL: 6 m4_attribute_* (不存在 PG) → V100 base 5 NOT NULL + min_sample_size + V103 EXTEND 6 real column
   - W1-A spec §7.3 mapping: attribute_n→min_sample_size / attribute_p_bonferroni→bonferroni_corrected_p / effect_size+subperiod+silhouette→composite replicability_score / graveyard→warning only
   - _compose_replicability_score 3-axis weighted average (W1-B §4.3 baseline 0.4/0.3/0.3)
   - _compute_pre_reg_hash SHA-256 of 6-attribute canonical JSON snapshot
   - engine_mode validation reject paper/demo (CLAUDE.md §七 application-level fail-loud)
   - build_audit_metadata supplement for cron logger emit (6 attribute full snapshot)
   - 19 schema-grep regression tests cover draft_writer.DRAFT_INSERT_SQL

   Push back: PA task expected evidence_json column 不存在於 PG learning.hypotheses（W1-A §7.3 也未要求）；不引入；改用 decision_lease_draft_id PG backref + build_audit_metadata logger emit 雙軌 audit chain。

   Mac cargo 416/0 + pytest 89/89 + Linux PG empirical INSERT happy + 3 CHECK negative path verify。
   ```

5. **PA spec amend follow-up**（不阻 commit）：建議 W1-A spec amend `evidence_json` 與 effect_size composite mapping 明示。

---

## 10. 對 PA dispatch task 的 deviation 列表

| PA task 期待 | 本 IMPL 採用 | 原因 |
|---|---|---|
| `evidence_json` JSONB INSERT | 不引入；改 `build_audit_metadata` caller logger emit | empirical PG `learning.hypotheses` 0 hit；W1-A spec 也未要求 |
| `m4_attribute_silhouette` → `replicability_score` 1:1 | silhouette → `replicability_score` 3-axis composite (per W1-A §7.3 + W2-F QA §5.3) | W1-A spec line 695-697 明確 composite 而非 1:1 |
| `attribute_n` 寫進 evidence_json | `attribute_n` → `min_sample_size` V100 base column | W1-A §7.3 mapping 明確 + W2-F QA §5.3 alignment + min_sample_size 是 V100 為 N gate 設計的 column |

其他 PA task expectations（hypothesis_source_module='M4_AUTO' / leakage_scan_pass=TRUE / cowork_review_status='PENDING_REVIEW' / decision_lease_draft_id TEXT or NULL）：

| PA task 期待 | 本 IMPL 對齊 |
|---|---|
| hypothesis_source_module='M4_AUTO' | ✅ 顯式 hard-code in SQL |
| leakage_scan_pass=TRUE (CR-6 6 attr 全 PASS) | ✅ payload field bool； caller 傳 |
| cowork_review_status='PENDING_REVIEW' | **不對齊 — 改 'NONE'**（per V103 EXTEND CHECK 4 enum: NONE/PENDING/APPROVED/REJECTED；'PENDING_REVIEW' 非 enum 值；Y1 不啟 Cowork review 故用 'NONE'） |
| decision_lease_draft_id 'TEXT or NULL' | **不對齊 — UUID NOT NULL**（V103 EXTEND 是 UUID type 非 TEXT；audit chain 不變量 non-NULL） |

---

**E1 IMPL Round 3 DONE** — 待 E2 re-review；report path:
`srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-25--w1c_round_3_draft_writer_schema_fix.md`
