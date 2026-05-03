# REF-20 Paper Replay Lab — Migration V036-V050 預留 Ledger

**契約上游：** `docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md`
**Workplan SoT：** `docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md`
**狀態：** 預留 (reserved)；任何 REF-20 sub-agent 不得使用 V036-V050 範圍以外的編號，本 ledger 是唯一 SSoT。
**Owner：** PM
**首次預留日期：** 2026-05-03（Wave 1 R20-P0-T5）

---

## 1. 用途 / Why this file exists

REF-20 V3 baseline 涵蓋 P2a/P2b/P3a/P3b/P4/P6 共 6 個 phase，每個 phase 都有 SQL migration。多 sub-agent 並行派發時若各自選號會撞號（V023 model_registry 事件殷鑑），故 PM 在 Wave 1 P0-T5 集中預留 V036-V050 共 15 個編號，逐一綁定 task ID + 用途。

REF-20 V3 baseline covers 6 phases (P2a/P2b/P3a/P3b/P4/P6). With multi-agent parallel dispatch, this PM-curated SSoT prevents migration number collisions (V023 model_registry incident, 2026-04-23) by reserving V036-V050 with explicit task binding.

---

## 2. 預留範圍 / Reservation Range

當前最高 migration：**V035__governance_audit_log.sql**（land 於 2026-05-XX）。
REF-20 預留：**V036-V050**（15 個編號）。
Buffer：**V045-V050** 暫不綁 task，留給 unknown unknowns。

---

## 3. 預留映射 / Reservation Map

| Migration | Task ID | Wave | 用途 / Purpose | 狀態 |
|---|---|---|---|---|
| **V036** | R20-P2a-S4 step 1 | Wave 3 | `replay_evidence_source_guard` — `verify_replay_evidence_and_insert()` PL/pgSQL function (SECURITY INVOKER) + GRANT EXECUTE TO replay_writer_role + PUBLIC fallback | **land 2026-05-03** (E1 sub-agent, 4 producer 同 commit 切換) |
| **V037** | R20-P2a-S4 step 3 | Wave 3 | `replay_evidence_revoke_public_insert` — REVOKE INSERT ON learning.mlde_shadow_recommendations FROM PUBLIC + GRANT INSERT TO replay_writer_role + REVOKE EXECUTE FROM PUBLIC（operator deploy 順序：先 V036 + producer 切換驗 → 再 V037） | **land 2026-05-03** (E1 sub-agent，等 operator 在 Linux trade-core deploy) |
| **V038** | R20-P2a-S6 step 1 | Wave 3 | `evidence_source_tier_add_column` — ADD COLUMN evidence_source_tier TEXT NULLABLE | **land 2026-05-03** (E1 sub-agent，等 operator 在 Linux trade-core deploy；3-step 步驟 1) |
| **V039** | R20-P2a-S6 step 2 | Wave 3 | `evidence_source_tier_backfill` — backfill via P0-T7 classification table → 'real_outcome' (3 sources: dream_engine / ml_shadow / opportunity_tracker; 27 ml_shadow `engine_mode='live'` audit row 同 tier)；同步寫 governance_audit_log batch row | **land 2026-05-03** (E1 sub-agent，等 operator deploy；3-step 步驟 2；依賴 V035 + V038) |
| **V040** | R20-P2a-S6 step 3 | Wave 3 | `evidence_source_tier_finalize` — ALTER NOT NULL + CHECK constraint allowlist (4 enum: real_outcome / calibrated_replay / synthetic_replay / counterfactual_replay) + sibling helper `V040_healthcheck.sql` (3 read-only probes: NULL count / tier distribution / constraint state) | **land 2026-05-03** (E1 sub-agent，等 operator deploy；3-step 步驟 3；依賴 V038 + V039；operator 必先跑 V040_healthcheck.sql 驗 0 NULL row 再 land V040) |
| **V041** | R20-P3a-Q2 | Wave 5 | `replay_oos_embargo_enforcement` — DB CHECK constraint `embargo_days >= GREATEST(7, CEIL(2.0 × half_life_days)::INTEGER)`；bootstrap stub for replay.experiments + ADD COLUMN IF NOT EXISTS half_life_days/embargo_days (P2b fixture-vs-migration order tolerant) | **land 2026-05-03** (E1 sub-agent, Wave 5 Batch 5A-B；雙語 Guard A + Guard B；pytest fixture `tests/migrations/test_v041_oos_embargo.py` 6/6 PASS Mac dev static-parse layer + cross-language alignment with `embargo_validator.py`) |
| **V042** | R20-P2a-S2 + G9 | Wave 3 | `replay_signing_keys` — key version archive table（key_version, generated_at, retired_at, expires_at 180d） | reserved |
| **V043** | R20-P4-Q5 | Wave 6 | `replay_mlde_replay_veto_log` — MLDE rank/veto advisory output sink | reserved |
| **V044** | R20-P6-S14 | Wave 8 | `replay_handoff_idempotency_unique` — UNIQUE(actor, idempotency_key) on handoff requests | reserved |
| **V045** | R20-P2b-T2 | Wave 4 | `replay_run_state` — replay_runner subprocess lifecycle table（PG advisory-lock concurrency-cap path 取代 in-memory _ACTIVE_RUNS, per Wave 2 dispatch v1.1 §6 Option C）；CHECK status enum + CHECK runtime_environment + 2 hot-path index (actor_id+status, status only) | **land 2026-05-03** (E1 sub-agent，Wave 4 P2b-T2 + T3 合併 IMPL) |
| **V046** | R20-P2b-T3 | Wave 4 | `replay_report_artifacts` — canary / diagnostic / pnl_summary / fill_log / baseline_compare artifact registry；FK run_id REFERENCES replay.run_state ON DELETE CASCADE；is_mock=true 標 Mac dev；CHECK artifact_type enum + 1 hot-path index (run_id+created_at) | **land 2026-05-03** (E1 sub-agent，Wave 4 P2b-T2 + T3 合併 IMPL) |
| **V047** | reserved buffer | — | unallocated（為 cross-wave 突發需求） | reserved (no task) |
| **V048** | reserved buffer | — | unallocated | reserved (no task) |
| **V049** | reserved buffer | — | unallocated | reserved (no task) |
| **V050** | reserved buffer | — | unallocated | reserved (no task) |

**註：** REF-20 自身 `replay` schema 核心表（experiments / manifests / artifacts / canary / handoff_requests）由 P2b runner land 時隨 binary 部署用 SQL fixture，不佔 migration 編號（per V3 §6 + workplan R20-P2b-T1）。如後續決定走 migration 路徑，從 V045 取號並 PM 更新本 ledger。

---

## 4. 變更協議 / Change Protocol

任何 sub-agent 派發前 PM 必查本 ledger：

1. **取號**：sub-agent 拿到 task ID + workplan §4 row → 對照本 §3 表 → 確認 V### 編號 → 寫 migration 檔。
2. **改用途**：sub-agent 不可改本 ledger；如預留用途與實作不符 → 回 PM clarify → PM 更新 ledger 後再 rerun。
3. **新增**：V051+ 任何新 migration 需 PM 在本 ledger 新增 row，禁止繞過。
4. **buffer 啟用**：V045-V050 任一啟用時，PM 必填 task ID + Wave + 用途 + 改 reserved → reserved (allocated)。
5. **檔案命名**：`V0XX__<short_kebab_descriptor>.sql`，遵守 `sql/migrations/templates/schema_guard_template.sql` Guard A/B/C 規範（雙語注釋強制）。

---

## 5. Audit / 稽核

| 動作 | 工具 | 預期 |
|---|---|---|
| 撞號偵測 | `ls sql/migrations/ \| grep -E '^V0(36\|37\|38\|39\|40\|41\|42\|43\|44\|45\|46\|47\|48\|49\|50)' \| wc -l` | ≤ 已 land 數量；每個 land 對應本 ledger row 已標 land |
| Ledger 一致性 | 本 ledger §3 row count vs 實際 land file count | 兩者匹配；漏 ledger row 視為 P0 阻塞 |
| Guard 規範 | `helper_scripts/db/audit_migrations.py` | 0 silent no-op；shape drift RAISE |

---

## 6. 修訂歷史 / Revision History

| 版次 | 日期 | 修訂者 | 摘要 |
|---|---|---|---|
| **v1** | 2026-05-03 | PM (R20-P0-T5) | 預留 V036-V050；綁定 9 個 reserved task migration + 6 個 buffer |
| **v1.1** | 2026-05-03 | E1 (R20-P2a-S4) | V036 + V037 file artifacts landed (3-PR sequence step 1 + step 3)；4 producer 切換同 commit；V038-V040/V041-V044 仍 reserved 待後續 task 派發 |
| **v1.2** | 2026-05-03 | E1 (R20-P2a-S6) | V038 + V039 + V040 file artifacts landed (3-step retrofit ADD nullable → backfill → ALTER NOT NULL+CHECK)；sibling helper `V040_healthcheck.sql` (3 read-only probes)；pytest fixture `tests/migrations/test_v038_v039_v040_evidence_source_tier.py` 17/17 PASS (Mac dev static-parse layer)；status reserved → land；V041-V044 仍 reserved 待後續 task 派發 |
| **v1.3** | 2026-05-03 | E1 (R20-P2b-T2 + T3 合併 IMPL) | V045 + V046 buffer 啟用（reserved → land）；V045 `replay_run_state` (run lifecycle + PG advisory-lock concurrency-cap path)；V046 `replay_report_artifacts` (FK CASCADE 到 V045)；雙語 Guard A + Guard C（V045 2 index, V046 1 index）；pytest fixture `tests/migrations/test_v045_v046_replay_run_state_artifacts.py` (Mac dev static-parse layer)；V047-V050 仍 reserved buffer 待後續 task 派發 |
| **v1.4** | 2026-05-03 | E1 (R20-P3a-Q2 Wave 5 Batch 5A-B) | V041 land (reserved → land)；`replay_oos_embargo_enforcement` — DB CHECK `embargo_days >= GREATEST(7, CEIL(2.0 × half_life_days)::INTEGER)`；bootstrap stub for `replay.experiments` 容忍 P2b fixture-vs-migration land 順序；雙語 Guard A（experiment_id 必存在）+ Guard B（half_life_days double precision / embargo_days integer type 驗證）；Python sibling validator `replay/embargo_validator.py` + cross-language alignment test；pytest fixture 6/6 PASS Mac dev static-parse；V042-V044 仍 reserved 待後續 task 派發 |

---

## 7. Cross-References

- 上游契約：[V3 baseline](../../docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md) §4 + §5 + §12
- Workplan SSoT：[Implementation Workplan V1](../../docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md) §4 Wave 1-9
- Migration 模板：`sql/migrations/templates/schema_guard_template.sql`
- 慘痛先例（撞號）：V023 model_registry 事件 2026-04-23（V004 pre-existing → IF NOT EXISTS silent skip）
