# REF-20 Wave 9 — 14d Gradient Observation Infrastructure (E1 Report)

**日期：** 2026-05-03
**Owner：** E1 (autonomous IMPL)
**契約上游：** workplan §4 Wave 9 (4 task) + V3 §11 P6 KPI 14d window + §12 #14
**Wave 1-8 status：** Wave 1-6 closed (commit refs in `2026-05-03--ref20_wave1_to_6_master_closure.md`)；Wave 7 DEFERRED；Wave 8 closed (per dispatch context commit `8429af1`)

---

## 1. 任務摘要

PM dispatch — Wave 9 Pre-deploy IMPL：14d gradient observation infrastructure + business KPI collection + audit incident scan + PM sign-off template。Operator deploy 之後 14d 自動觀察。

4 Task sequential 完成：

| Task | 名稱 | Status |
|---|---|---|
| **R20-W9-T1** | replay_no_live_mutation continuous validator (cron + module) | ✅ DONE |
| **R20-W9-T2** | Business KPI 7d/14d collection (cron + V047) | ✅ DONE |
| **R20-W9-T3** | governance_audit_log 14d 0 incident scan (cron + V048) | ✅ DONE |
| **R20-W9-T4** | PM Wave 9 sign-off template doc + REF-20_RESERVATION ledger v1.7 | ✅ DONE |

---

## 2. 修改清單

### NEW files

| Path | LOC | Purpose |
|---|---|---|
| `program_code/exchange_connectors/bybit_connector/control_api_v1/replay/wave9_continuous_validator.py` | 328 | TASK 1 module — `validate_no_live_mutation()` API + `ContinuousValidatorResult` dataclass |
| `helper_scripts/cron/wave9_replay_no_live_mutation_watch.sh` | 326 | TASK 1 hourly cron — DSN + psycopg2 + validator + audit emit + exit 1 violation |
| `helper_scripts/cron/wave9_business_kpi_collector.py` | 617 | TASK 2 daily 06:00 cron — 6 KPI sampler × 2 windows (7d/14d) + V047 UPSERT + Mac dev mock mode |
| `sql/migrations/V047__replay_business_kpi_snapshots.sql` | 271 | TASK 2 V047 migration — replay.business_kpi_snapshots schema + Guard A/C |
| `helper_scripts/cron/wave9_audit_incident_scan.py` | 532 | TASK 3 daily 06:30 cron — 3 scanner (handoff_rejected / key_rotation_due / audit_failed_other) + V048 UPSERT + exit 1 violation |
| `sql/migrations/V048__replay_audit_incident_summaries.sql` | 305 | TASK 3 V048 migration — replay.audit_incident_summaries schema + Guard A/C |
| `helper_scripts/cron/test_wave9_replay_no_live_mutation_watch.py` | 305 | TASK 1 pytest 4 case |
| `helper_scripts/cron/test_wave9_business_kpi_collector.py` | 418 | TASK 2 pytest 4 case |
| `helper_scripts/cron/test_wave9_audit_incident_scan.py` | 340 | TASK 3 pytest 4 case |
| `tests/migrations/test_v047_business_kpi_snapshots.py` | 158 | TASK 2 V047 pytest 4 case |
| `tests/migrations/test_v048_audit_incident_summaries.py` | 162 | TASK 3 V048 pytest 4 case |
| `docs/execution_plan/2026-05-03--ref20_wave9_pm_sign_off_template.md` | 274 | TASK 4 PM Wave 9 sign-off template (7 closure checklist + operator deploy 區 + 14d window 表) |

### MODIFIED files

| Path | Change |
|---|---|
| `sql/migrations/REF-20_RESERVATION.md` | v1.6 → v1.7：V047 + V048 buffer → land；ledger row purpose + status + revision history append |

**Total**: 12 NEW + 1 MODIFIED = 13 file artifacts。

---

## 3. 關鍵 Diff（要點）

### TASK 1 — wave9_continuous_validator.py API surface

```python
@dataclass(slots=True)
class ContinuousValidatorResult:
    ok: bool
    total_replay_source_rows: int
    first_violation_ts: Optional[datetime]
    details: dict[str, Any] = field(default_factory=dict)
    window_days: int = 14
    scanned_at: Optional[datetime] = None


def validate_no_live_mutation(
    cursor: Any, window_days: int = 14
) -> ContinuousValidatorResult:
    """純 SELECT 三表 (live_orders / fills / positions)；查 source LIKE 'replay_%'
    AND ts >= NOW() - INTERVAL '<N> days'。Graceful fallback: schema/table/source col 缺。"""
```

Per-table SELECT pattern (parameterised SQL, table name from controlled allowlist):

```python
sql = f"""
    SELECT COUNT(*), MIN(ts)
      FROM trading.{table}
     WHERE source LIKE %s
       AND ts >= NOW() - INTERVAL '%s days';
"""  # noqa: S608 — table from controlled allowlist
```

### TASK 2 — V047 schema critical bits

```sql
CREATE TABLE IF NOT EXISTS replay.business_kpi_snapshots (
    snapshot_id    UUID PRIMARY KEY,
    snapshot_date  DATE NOT NULL,
    window_type    TEXT NOT NULL,
    kpi_name       TEXT NOT NULL,
    kpi_value      DOUBLE PRECISION,
    sample_size    INT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE replay.business_kpi_snapshots
    ADD CONSTRAINT uq_kpi_snapshot_date_window_name
    UNIQUE (snapshot_date, window_type, kpi_name);

ALTER TABLE replay.business_kpi_snapshots
    ADD CONSTRAINT chk_kpi_window_type
    CHECK (window_type IN ('7d', '14d'));

CREATE INDEX idx_kpi_snapshot_date_window
    ON replay.business_kpi_snapshots (snapshot_date DESC, window_type);
```

### TASK 2 — collector 6 sampler 命名（V3 §11 P6 KPI list 對齊）

```python
KPI_NAMES = (
    "replay_routes_daily_request_count",      # V045 run_state count
    "manifest_verify_fail_mode_breakdown",    # V035 alert_type 4 fail mode
    "handoff_success_rate",                   # V044 success / total
    "quota_cap_hit_rate",                     # V035 alert_type prune storage_cap
    "cost_edge_ratio_p50",                    # V035 cost_regime_ratio percentile_cont
    "dsr_pbo_gate_fire_rate",                 # V035 review_live_candidate rule_failures
)
WINDOW_TYPES = ("7d", "14d")  # 12 row/day UPSERT
```

### TASK 3 — V048 schema critical bits

```sql
CREATE TABLE IF NOT EXISTS replay.audit_incident_summaries (
    summary_id          UUID PRIMARY KEY,
    scan_date           DATE NOT NULL,
    window_days         INT NOT NULL DEFAULT 14,
    incident_count      INT NOT NULL,
    severity            TEXT NOT NULL,
    event_type          TEXT NOT NULL,
    first_incident_ts   TIMESTAMPTZ,
    last_incident_ts    TIMESTAMPTZ,
    sample_payload      JSONB
);

ALTER TABLE replay.audit_incident_summaries
    ADD CONSTRAINT chk_audit_incident_severity
    CHECK (severity IN ('low', 'medium', 'high', 'critical'));

CREATE INDEX idx_audit_incident_scan_date_severity
    ON replay.audit_incident_summaries (scan_date DESC, severity);
```

**Invariant**: 0 incident → NOT 寫 row (有 row = 該日有 incident)。

### TASK 3 — 3 scanner severity 分級

| Scanner | event_type | Severity | Rationale |
|---|---|---|---|
| handoff_rejected | replay_handoff_request | high | rejected handoffs = operator config / security 違規 |
| key_rotation_due | replay_key_rotation_due | high | overdue rotation = manifest signature trust degraded |
| audit_failed_other | audit_write_failed | medium | 通用 audit write 失敗（schema drift, DB constraint 違規等） |

---

## 4. 治理對照

| 紅線 | 結果 | 證據 |
|---|---|---|
| 0 trading.* mutation (純 audit + monitoring) | ✅ PASS | grep `INSERT INTO trading\|UPDATE trading\.\|DELETE FROM trading` 0 hit (only SELECTs in validator + samplers) |
| 0 governance_hub.acquire_lease 直接 import | ✅ PASS | grep `governance_hub` 2 hit 但 全是 module docstring 文字注釋 (NOT Python import) |
| Idempotent cron (重跑 0 effect) | ✅ PASS | validator read-only；KPI / incident UPSERT pattern (ON CONFLICT DO UPDATE) |
| V047/V048 graceful absent fallback (cron 不 crash) | ✅ PASS | cron probe `_table_present()`; absent → log + exit 0 |
| 雙語 docstring | ✅ PASS | 全 module / function MODULE_NOTE EN + 中 + Spec source |
| V035 migration pattern | ✅ PASS | Guard A (CREATE 前驗欄位) + Guard C (pg_get_indexdef 比對 hot-path) |
| Mac dev env: write to /tmp/ test path | ✅ PASS | OPENCLAW_WAVE9_KPI_MOCK=1 → /tmp/wave9_kpi_test_only/snapshot.jsonl (no DB) |
| 0 既有 cron / module 改動 | ✅ PASS | 僅 NEW 12 個 + REF-20_RESERVATION.md ledger row 加 |
| File size cap < 800 LOC each | ✅ PASS | max 617 LOC (collector)，全文件均 < 800 |

### Hard checks (CLAUDE.md §七)

```
=== 1. trading.* mutation grep (expected: 0 INSERT/UPDATE/DELETE on trading.*) ===
(0 hit; only SELECTs)

=== 2. governance_hub grep (expected: 0 import) ===
program_code/.../wave9_continuous_validator.py:15  (docstring text "no governance_hub coupling")
program_code/.../wave9_continuous_validator.py:39  (中文 docstring)
(Both are doc comments NOT imports — PASS)

=== 3. Hardcoded path grep (expected: 0 /home/ncyu | /Users/ncyu hard-code) ===
(0 hit)
```

### pytest 結果

```
============================== 88 passed, 2 skipped in 0.73s ==============================

# Wave 9-specific subset (20/20 PASS):
helper_scripts/cron/test_wave9_replay_no_live_mutation_watch.py: 4/4 PASS
helper_scripts/cron/test_wave9_business_kpi_collector.py: 4/4 PASS
helper_scripts/cron/test_wave9_audit_incident_scan.py: 4/4 PASS
tests/migrations/test_v047_business_kpi_snapshots.py: 4/4 PASS
tests/migrations/test_v048_audit_incident_summaries.py: 4/4 PASS
```

### bash -n + py_compile

```
wave9_replay_no_live_mutation_watch.sh: BASH SYNTAX OK
ALL PY_COMPILE OK (8 files)
```

---

## 5. 不確定之處（PA / PM clarify）

1. **V035 event_type CHECK enum 'audit_write_failed' overload**: 多 cron (P2a-S1 key archive / P2a-S5 prune / Wave 9 watcher / Wave 9 audit incident) 都用 'audit_write_failed' enum slot + payload alert_type 區分。短期可行；長期是否該開新 task 擴 V035 enum 加 typed slot ('replay_no_live_mutation_violation' / 'replay_artifact_prune' 等)？建議 PM 評估：cost = 一個 V### migration + 沿用既有 audit_emit pattern；benefit = grafana / dashboard 過濾 alert_type 不必 join sub-key。本 task 不展開。
2. **V047 sample_size 對於 cost_edge_ratio_p50 的語意**: collector 把 `percentile_cont` 結果存 kpi_value、`COUNT(cost_regime_ratio)` 存 sample_size。但 V3 §11 P6 KPI list 沒明示 cost_edge_ratio 應為 p50 或其他 percentile (p10/p90/distribution)。本 task 取 p50 作 placeholder；若 PM 認為應收齊 distribution，需擴 collector 一個 KPI 拆 6 row (`_p10` / `_p25` / `_p50` / `_p75` / `_p90` / `_p95`) 或改 schema 加 percentile column。
3. **3 scanner severity 'medium' / 'high' 分級**: handoff_rejected + key_rotation_due 為 high，audit_failed_other 為 medium。是否應加 'critical' 等級？例如 handoff_rejected 配 reject_reason='manifest_signature_failed' 應 critical (signature trust 破壞)？本 task 未細分；建議 FA review。
4. **Wave 9 cron 排程衝突風險**: hourly watcher (`0 * * * *`) + daily KPI collector (`0 6 * * *`) + daily incident scan (`30 6 * * *`) + sibling cron (P2a-S5 prune `0 */6 * * *` + P2a-S1 key archive cleanup `30 9 * * *` + replay_key_rotation_check sibling)。是否需 `flock` leader election 或時段交錯 (06:00 KPI vs 06:30 incident vs 09:30 key archive vs 06:00 prune)？本 task 用 30-min offset；operator deploy 時可重排。
5. **14d window 起始 ts 計算**: workplan 沒明示 — 我預設「Linux trade-core sync 完 + cron crontab installed ts」為 window START。但若 V### apply 與 cron install 跨日，是否取「V### apply ts」或「cron 第一次成功 cycle ts」？sign-off template 留空 operator 填。

---

## 6. Operator 下一步

### 立刻可做（commit + Linux sync）

1. PM 確認本 IMPL 內容 → 統一 commit + push (per CLAUDE.md §七 強制鏈 E1→E2→E4→QA→PM)
2. Linux trade-core `git pull --ff-only` 同步 13 file artifacts

### Pre-deploy verification (可選)

3. Linux trade-core 上跑 pytest 既有 (per Wave 1-8 master closure ~3500+ baseline) + Wave 9 新 20 case，全 PASS
4. Linux trade-core 跑 `bash helper_scripts/cron/wave9_replay_no_live_mutation_watch.sh`（dry run；應 graceful exit 0 因為 trading 表還沒寫 replay-source row）

### Deploy

5. Linux trade-core apply migration in order:
   - V036 → 4 producer 切換 → V037
   - V038 → V039 → V040_healthcheck.sql → V040
   - V041 → V042 (env setup)
   - V043 → V044 → V045 → V046
   - **V047 → V048** (本 wave NEW)
6. Crontab install (3 entries):
   ```
   0 * * * * "$OPENCLAW_BASE_DIR/helper_scripts/cron/wave9_replay_no_live_mutation_watch.sh"
   0 6 * * * "$OPENCLAW_BASE_DIR/helper_scripts/cron/wave9_business_kpi_collector.py"
   30 6 * * * "$OPENCLAW_BASE_DIR/helper_scripts/cron/wave9_audit_incident_scan.py"
   ```
7. 14d window 觀察期間自然跑（無人工干預）
8. PM Wave 9 sign-off template 7 條 checklist 填寫 → REF-20 P6 closure 公告

### Reviewer chain

- @E2 review: 雙語注釋 + V035 enum slot fallback 是否觸發 sibling enum extension task + sample_payload 截斷 8KB 是否合理
- @E4 regression: Linux trade-core run pytest 既有 + 新 20 case 全 PASS + bash -n 全通過
- @MIT review: V047/V048 schema 與 V035 / V044 / V045 / V046 整合是否乾淨
- @FA review: 6 KPI sampler 是否完整對齊 V3 §11 P6 list；3 incident scanner severity 分級是否合理
- @QA review: 14d window cron 排程 (hourly + daily 06:00 + daily 06:30) 是否與既有 cron 衝突；7-item closure checklist 是否覆蓋 P6 closure 條件

---

## 7. PM commit message draft

單行 conventional commit per task constraints:

```
feat(replay): Wave 9 14d gradient observation + KPI collection + audit incident scan + PM sign-off template
```

(extended description optional)

```
- TASK 1: wave9_continuous_validator + hourly watch cron + 4 pytest
- TASK 2: V047 business_kpi_snapshots + daily collector cron + 4 pytest + 4 SQL test
- TASK 3: V048 audit_incident_summaries + daily incident scan cron + 4 pytest + 4 SQL test
- TASK 4: PM Wave 9 sign-off template + REF-20_RESERVATION ledger v1.7

20/20 PASS cumulative + bash -n + py_compile + 0 trading.* mutation grep
+ 0 governance_hub.acquire_lease import + cross-platform path clean.

Operator deploy + 14d gradient observation 觸發實際採集；PM Wave 9 sign-off
14d window END ts 後 issue → REF-20 P6 closure。
```

---

## 8. 附錄 — Cross-References

- **Workplan**: [Wave 9 §4](../../../execution_plan/2026-05-03--ref20_implementation_workplan_v1.md) row 1-4
- **V3 baseline**: [§11 P6 KPI + §12 #14](../../../execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md)
- **Wave 1-6 master closure**: [`2026-05-03--ref20_wave1_to_6_master_closure.md`](../../../execution_plan/2026-05-03--ref20_wave1_to_6_master_closure.md)
- **Wave 7 defer note**: [`2026-05-03--ref20_wave7_defer_note.md`](../../../execution_plan/2026-05-03--ref20_wave7_defer_note.md)
- **Wave 9 PM sign-off template**: [`2026-05-03--ref20_wave9_pm_sign_off_template.md`](../../../execution_plan/2026-05-03--ref20_wave9_pm_sign_off_template.md)
- **Migration ledger v1.7**: [`REF-20_RESERVATION.md`](../../../../sql/migrations/REF-20_RESERVATION.md)
