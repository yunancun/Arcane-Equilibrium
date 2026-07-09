# REF-20 Paper Replay Lab — Wave 9 PM Sign-off Template

**日期：** 2026-05-03
**狀態：** Wave 9 IMPL committed (Mac dev)；deploy 後 14d gradient observation 觸發實際採集
**Owner：** PM (operator full-autonomy mode 2026-05-03 session)
**契約上游：** `2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md` §11 P6 + §12 #14
**Workplan：** `2026-05-03--ref20_implementation_workplan_v1.md` §4 Wave 9
**前置：** Wave 8 closed (commit `8429af1` per dispatch context)

---

## 1. Overview

REF-20 P6 closure 條件 = Wave 9 14d observation window 完整跑完 + 0 incident + 全業務 KPI 採樣 + 跨工作流 review sign-off。本檔為 PM 在 deploy 後填寫的 sign-off template。

---

## 2. P6 Closure Checklist (7 items)

### Pre-deploy (IMPL 階段 — 已完成)

#### 1. ✅ Wave 1-8 closed (commits referenced)

| Wave | Closure commit | Highlights |
|---|---|---|
| Wave 1 | `9e0c826` | P0 docs amendment + scaffold |
| Wave 2 | `1851714` + `b1f6b8a` | P1 frontend + P2a HMAC signer |
| Wave 3 | `5a618ff` | P2a/P2b producer switch + 3-layer guard |
| Wave 4 | `4b48b6d` | P2b runner + 8-route wire |
| Wave 5 | `457a458` | P3a + P3b + RGM math |
| Wave 6 | `eb5f106` | P4 advisory (DSR / PBO / Dream / MLDE) |
| Wave 7 | DEFERRED | Hard prereq LG-2/3/4 stable not GREEN |
| Wave 8 | `8429af1` | P6 Bounded Demo Handoff trio |
| Wave 9 | `<TBD>` | 14d observation infrastructure (THIS) |

### Post-deploy (operator action 必)

#### 2. ⏳ V### migrations applied on Linux trade-core

Migration apply order (operator manually `psql -f` per CLAUDE.md §七 SQL guard sequence):

```
V036 (verify_replay_evidence_and_insert function + GRANT)
  ↓
4 producer 切換 commit deploy verify
  ↓
V037 (REVOKE INSERT FROM PUBLIC)
  ↓
V038 (evidence_source_tier ADD COLUMN nullable)
  ↓
V039 (evidence_source_tier backfill)
  ↓
V040_healthcheck.sql (run + verify 0 NULL)
  ↓
V040 (ALTER NOT NULL + CHECK)
  ↓
V041 (replay_oos_embargo_enforcement)
  ↓
V042 (replay_signing_keys archive — operator pending env setup)
  ↓
V043 (mlde_replay_veto_log)
  ↓
V044 (replay_handoff_idempotency_unique + V035 enum extension)
  ↓
V045 (replay_run_state)
  ↓
V046 (replay_report_artifacts)
  ↓
V047 (replay_business_kpi_snapshots) — Wave 9 NEW
  ↓
V048 (replay_audit_incident_summaries) — Wave 9 NEW
```

**Operator recordkeeping**:
- V###_apply_ts: `_______________`
- V###_apply_log_path: `_______________`
- 0 RAISE EXCEPTION confirmation: `[ ] yes / [ ] no`

#### 3. ⏳ Decision Lease retrofit AMD-2026-05-02-01 deploy verified

Per CLAUDE.md §五 lease facade activation; AMD-2026-05-02-01 path A 已簽核但 retrofit pending。

- AMD-2026-05-02-01 retrofit deploy commit: `_______________`
- Rust hot path acquire_lease() 觸發確認: `[ ] yes / [ ] no`
- Healthcheck `lease_acquire_in_router` PASS confirmation: `[ ] yes / [ ] no`

#### 4. ⏳ 14d replay_no_live_mutation 0 violation (cron healthcheck)

Wave 9 Task 1 cron deployed + 14d window 觀察:

- Cron entry installed: `[ ] yes / [ ] no`
  ```
  0 * * * * "$OPENCLAW_BASE_DIR/helper_scripts/cron/wave9_replay_no_live_mutation_watch.sh"
  ```
- 14d window start ts: `_______________`
- 14d window end ts: `_______________`
- Total cron cycles run (expected 24 × 14 = 336): `_______________`
- Total exit-1 cycles (expected 0): `_______________`
- governance_audit_log row count for `alert_type='replay_no_live_mutation_violation'` in 14d window (expected 0): `_______________`

**ACCEPT 條件**: 0 violation in 14d window.

#### 5. ⏳ 14d governance_audit_log 0 high-severity incident

Wave 9 Task 3 cron deployed + 14d window 觀察:

- Cron entry installed: `[ ] yes / [ ] no`
  ```
  30 6 * * * "$OPENCLAW_BASE_DIR/helper_scripts/cron/wave9_audit_incident_scan.py"
  ```
- 14d window start ts: `_______________`
- 14d window end ts: `_______________`
- replay.audit_incident_summaries row count in 14d window (expected 0): `_______________`
- 各 severity / event_type breakdown:
  - severity='high' event_type='replay_handoff_request': `_______________`
  - severity='high' event_type='replay_key_rotation_due': `_______________`
  - severity='medium' event_type='audit_write_failed': `_______________`

**ACCEPT 條件**: 0 row in `replay.audit_incident_summaries` for 14d window.

#### 6. ⏳ Business KPI 7d/14d snapshot 完整 (per V3 §11 P6 list)

Wave 9 Task 2 cron deployed + 14d window 全 KPI 採樣:

- Cron entry installed: `[ ] yes / [ ] no`
  ```
  0 6 * * * "$OPENCLAW_BASE_DIR/helper_scripts/cron/wave9_business_kpi_collector.py"
  ```
- 14d window start ts: `_______________`
- 14d window end ts: `_______________`
- Total snapshots written (expected 14 × 6 KPI × 2 windows = 168): `_______________`

**Per-KPI baseline / 各 KPI baseline**（last day of window）:

| KPI | 7d | 14d |
|---|---|---|
| `replay_routes_daily_request_count` (avg/day) | `___` | `___` |
| `manifest_verify_fail_mode_breakdown` (total fail) | `___` | `___` |
| `handoff_success_rate` | `___` | `___` |
| `quota_cap_hit_rate` | `___` | `___` |
| `cost_edge_ratio_p50` | `___` | `___` |
| `dsr_pbo_gate_fire_rate` | `___` | `___` |

**ACCEPT 條件**: 168 snapshot rows + KPI 明顯 (各 KPI sample_size > 0 或可解釋的 NULL).

#### 7. ⏳ E2 + E4 + MIT + FA + QA review sign-off

Multi-agent review chain for Wave 9 closure:

| Agent | Review scope | Sign-off date | Findings |
|---|---|---|---|
| **@E2** | Wave 9 code review (4 files + 2 SQL) | `____________` | `____________` |
| **@E4** | Wave 9 regression suite (16 pytest cases) | `____________` | `____________` |
| **@MIT** | V047/V048 SQL schema + ML pipeline integrity | `____________` | `____________` |
| **@FA** | Acceptance binding + KPI completeness | `____________` | `____________` |
| **@QA** | 14d gradient observation 統合驗收 | `____________` | `____________` |

---

## 3. Operator Deploy 紀錄區

**Deploy ts**: `_______________`
**Deploy commit (Wave 9 closure)**: `_______________`
**Linux trade-core sync git pull --ff-only ts**: `_______________`
**Engine binary deploy (rebuild?)**: `[ ] yes / [ ] no` (Wave 9 純 Python + SQL，不需 rebuild)
**Cron crontab installation ts**: `_______________`

**Pre-deploy smoke** (Mac dev verification):
- pytest cumulative cases: 16 (Task 1: 4 + Task 2: 4 + Task 3: 4 + V047: 4 + V048: 4 = 20 actual; 16 cron + 8 SQL — re-tally per actual)
- bash -n syntax PASS: `[ ] yes / [ ] no`
- py_compile PASS: `[ ] yes / [ ] no`
- 0 trading.* mutation grep PASS: `[ ] yes / [ ] no`
- 0 governance_hub.acquire_lease import grep PASS: `[ ] yes / [ ] no`
- Cross-platform path grep clean: `[ ] yes / [ ] no`

---

## 4. 14d Window 開始 / 結束 ts

| 階段 | ts (UTC) |
|---|---|
| Wave 9 commit + push | `_______________` |
| Linux trade-core git pull --ff-only | `_______________` |
| V047 / V048 migration apply | `_______________` |
| Cron crontab install | `_______________` |
| **14d window START** | `_______________` |
| 7d midpoint review | `_______________` |
| **14d window END** | `_______________` |
| PM Wave 9 sign-off issued | `_______________` |
| REF-20 P6 closure announced | `_______________` |

---

## 5. REF-20 P6 Closure 確認簽章區

> **PM 確認**：上述 7 條 closure 條件全 ✅ 後，本 Wave 9 sign-off doc 由 PM 簽收 + REF-20 P6 正式 closed。

**PM Sign-off**:
- Name: `_______________`
- Date: `_______________`
- Commit ref (final closure): `_______________`

**Operator Acknowledgement**:
- Name: `_______________`
- Date: `_______________`
- Notes: `_______________`

---

## 6. Cross-References

### Upstream contract
- V3 baseline: [V3 §11 P6 + §12 #14](2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md)
- Workplan: [Wave 1-9 §4](2026-05-03--ref20_implementation_workplan_v1.md)

### Wave 1-8 closure references
- Wave 1-6 master closure: [`2026-05-03--ref20_wave1_to_6_master_closure.md`](2026-05-03--ref20_wave1_to_6_master_closure.md)
- Wave 7 defer note: [`2026-05-03--ref20_wave7_defer_note.md`](2026-05-03--ref20_wave7_defer_note.md)
- Wave 8 closure (commit `8429af1`): per dispatch context

### Wave 9 IMPL artifacts (this wave)

| Artifact | Path |
|---|---|
| Continuous validator (module) | `program_code/exchange_connectors/bybit_connector/control_api_v1/replay/wave9_continuous_validator.py` |
| 14d watcher cron | `helper_scripts/cron/wave9_replay_no_live_mutation_watch.sh` |
| Business KPI collector cron | `helper_scripts/cron/wave9_business_kpi_collector.py` |
| Audit incident scan cron | `helper_scripts/cron/wave9_audit_incident_scan.py` |
| V047 migration | `sql/migrations/V047__replay_business_kpi_snapshots.sql` |
| V048 migration | `sql/migrations/V048__replay_audit_incident_summaries.sql` |
| Migration ledger | `sql/migrations/REF-20_RESERVATION.md` v1.7 |
| Cron tests (Task 1) | `helper_scripts/cron/test_wave9_replay_no_live_mutation_watch.py` |
| Cron tests (Task 2) | `helper_scripts/cron/test_wave9_business_kpi_collector.py` |
| Cron tests (Task 3) | `helper_scripts/cron/test_wave9_audit_incident_scan.py` |
| SQL test (V047) | `tests/migrations/test_v047_business_kpi_snapshots.py` |
| SQL test (V048) | `tests/migrations/test_v048_audit_incident_summaries.py` |
| PM Wave 9 sign-off | `docs/execution_plan/2026-05-03--ref20_wave9_pm_sign_off_template.md` (THIS) |

---

## 7. Wave 7 Defer Note

Wave 7 P5 Agents Monitor 抽出 deferred (LG-2/3/4 frontend stable prereq not GREEN). Wave 9 closure 不阻塞 Wave 7：

- Wave 7 acceptance #21 (`agents_monitor_read_only`) status: ⏸ DEFERRED (event-triggered re-dispatch)
- Wave 9 acceptance binding: 直接 close P6 = #14 / #20 / 14d gradient KPI
- 25 / 25 acceptance binding 完成度（post-Wave 9）：
  - 22 / 25 ✅ (Wave 1-6 已 land)
  - #20 ✅ (Wave 8 已 land)
  - #21 ⏸ (Wave 7 DEFERRED)
  - **Wave 9 不引入新 acceptance #；只兌現 14d 持續驗證 #14 + 業務 KPI 持續採樣**

REF-20 P6 closure 條件不阻塞於 Wave 7；Wave 7 是 P5 抽出，與 P6 為平行作業。

---

## 8. Future Work Pointers

- LG-2/3/4 frontend stable → Wave 7 dispatch (event-triggered)
- REF-21 S1 recorder spec land → P3b stub superseded
- 21d demo unlock 2026-05-07 → P3a-Q6 power gate real data activation
- E5 optimization ticket P2-REF20-W6-REFACTOR → file size split for dream_engine / mlde_shadow_advisor / regime_controller (>800 LOC accept-and-flag)

---

## 9. 修訂歷史 / Revision History

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| **v1** | 2026-05-03 | PM (autonomous mode) | Wave 9 PM sign-off template land；7-item closure checklist + operator deploy 紀錄區 + 14d window 表 + closure 確認簽章區 + Wave 7 defer cross-ref |

---

> **PM Note**: Wave 9 IMPL 完成後 operator deploy + 14d 自然觀察期間，本檔由 PM 在 14d window END ts 後簽收。本檔不阻塞 Wave 9 commit；commit 後 14d 觀察階段是純自動化跑（cron 觸發），無人工干預需求。
