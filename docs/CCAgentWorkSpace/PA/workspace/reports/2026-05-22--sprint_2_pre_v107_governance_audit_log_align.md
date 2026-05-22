---
report: PA-DRIFT-1 — V107 spec governance.audit_log alignment patch verdict
date: 2026-05-22
author: PA (Project Architect)
phase: Sprint 2 pre-readiness Track 3
scope: docs/execution_plan/2026-05-21--v107_m11_replay_divergence_log_schema_spec.md (spec doc 對齊驗證)
parent finding: srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_1b_v107_sandbox_land_dedup_full.md（E1 Sprint 1B push back）
parent reconcile: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_1a_zeta_phase_3a_spec_reconcile.md（PA Phase 3a spec ↔ V098 baseline reconcile）
status: ✅ PA SPEC SCOPE CLOSED — V107 SQL drift CARRY-OVER E1
---

# PA-DRIFT-1 V107 governance.audit_log alignment verdict

## §1 結論一行話

**PA scope（spec doc）已對齊 → ✅ DONE**，無需再 patch；
**V107 SQL implementation 仍 drift 4 處 → 必 carry-over E1**（PA scope 不寫 SQL）。

E1 Sprint 1B push back 的 PA-DRIFT-1 finding 屬實，但 drift 位置不在 PA scope（spec doc）而在 E1 scope（V107 SQL）。Sprint 1A-ζ Phase 3a PA 已把 spec doc reconcile 完，當時未連帶 patch V107 SQL（因為 V107 SQL 由 E1 Track C 後續產出）。

## §2 Pre-state grep

### 2.1 Spec doc literal hit（target = `docs/execution_plan/2026-05-21--v107_m11_replay_divergence_log_schema_spec.md`）

- `learning.governance_audit_log`：**10 hit**（正確命名，PA Phase 3a reconcile 後通行 literal）
- `governance.audit_log`（嚴格 word-boundary）：**1 hit**（line 472）

唯一一處 `governance.audit_log`：

```
470:    -- learning.governance_audit_log 必須存在(M11 H-11 audit cross-ref 雖無 FK 但 query JOIN 需要)
471:    -- 2026-05-22 PA reconcile §4: V098 baseline 真實表名為 learning.governance_audit_log
472:    -- (per V035 baseline);本 spec 前版「governance.audit_log」屬概念命名漂移。
```

→ 這是 **PA Phase 3a 留下的歷史 reconcile 注釋**，明確標注「前版屬概念命名漂移」，是 audit trail 不是 active literal。不需要 patch（patch 反而會抹掉 reconcile trace）。

### 2.2 PG empirical schema 驗證（sandbox `trade-core:127.0.0.1`）

```
schemaname |        tablename         
-----------+--------------------------
 governance | audit_log               ← 遺留小表（5 column，無 hypertable，row=0）
 learning   | governance_audit_log    ← V035 baseline + V098 extension target（27 column，hypertable，FK mlde_param_applications）
 public    | audit_events
 replay    | audit_incident_summaries
```

V035 + V098 + V107 spec 一致指向：cross-ref target = `learning.governance_audit_log`（27 column 完整表）。

### 2.3 V098 baseline literal 確認

```bash
grep -n "learning\.governance_audit_log\|governance\.audit_log" sql/migrations/V098*.sql
```

→ V098 共 10 hit，**全部** `learning.governance_audit_log`，0 `governance.audit_log`（包含 Guard A check + LOCK TABLE + ALTER + COMMENT + RAISE NOTICE 全鏈）。

### 2.4 V035 baseline literal 確認

```bash
grep -n "learning\.governance_audit_log\|governance\.audit_log" sql/migrations/V035*.sql
```

→ V035 共 9 hit，**全部** `learning.governance_audit_log`，0 `governance.audit_log`（CREATE TABLE + Guard A + hypertable + index 全鏈）。

**結論**：`learning.governance_audit_log` 是 V035 baseline + V098 extension 的唯一 canonical 名稱；`governance.audit_log` 不是 V098 真實表，可能是早期某 schema 的遺留 stub。

## §3 V107 SQL literal 對齊狀態

Target = `sql/migrations/V107__replay_divergence_log.sql`

```bash
grep -nE 'governance\.audit_log' sql/migrations/V107__replay_divergence_log.sql
```

| line | 內容 | 屬性 |
|---|---|---|
| 23 | `--   - Guard A: TimescaleDB extension + governance.audit_log + learning.hypotheses` | Header 注釋 drift |
| 47 | `--   - V096 boundary (TimescaleDB extension) + V098 governance.audit_log +` | Header 注釋 drift |
| 127 | `    -- governance.audit_log 必須存在 (M11 H-11 audit cross-ref query target；` | Guard A 邏輯前注釋 drift |
| 134 | `            'V107 Guard A FAIL: governance.audit_log missing — V098 must '` | **RAISE EXCEPTION text 邏輯 drift（critical）** |

關鍵點 line 129-135 整段：

```sql
    -- governance.audit_log 必須存在 (M11 H-11 audit cross-ref query target；
    -- 非 schema FK；spec §1.4 + Guard A 要求 V098 已 land)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='governance' AND table_name='audit_log'
    ) THEN
        RAISE EXCEPTION
            'V107 Guard A FAIL: governance.audit_log missing — V098 must '
            'apply before V107 (cross-ref query target). Verify _sqlx_migrations.';
    END IF;
```

**驗證 logic correctness：**
- `table_schema='governance' AND table_name='audit_log'` → 在 sandbox 仍會回 TRUE（因 sandbox 有遺留 `governance.audit_log` 表）
- 但這個遺留表 5 column 無 hypertable，**不是** V098 真正定義的 cross-ref target
- 真正應該檢查的是 `table_schema='learning' AND table_name='governance_audit_log'`

**P1 risk**：如果某 PG 環境（fresh deploy / production）沒有遺留 `governance.audit_log` 表，V107 Guard A 會誤 raise；如果有遺留表，Guard A 會誤過（false negative），下游 cross-ref query 仍會跑空。

## §4 Patch decision

### 4.1 PA spec scope（本 ticket）

✅ **NO PATCH NEEDED** — spec doc line 472 是 PA Phase 3a reconcile audit trail；移除會抹掉漂移歷史。其餘 10 處 literal 全已對齊。

diff stat：0 file changed。

### 4.2 V107 SQL scope（carry-over E1）

**E1 必派 follow-up**，4 處 literal patch：

| line | 改動 | 邏輯影響 |
|---|---|---|
| 23 | `governance.audit_log` → `learning.governance_audit_log` | 注釋；無 runtime 影響 |
| 47 | `governance.audit_log` → `learning.governance_audit_log` | 注釋；無 runtime 影響 |
| 127 | `governance.audit_log` → `learning.governance_audit_log` | 注釋；無 runtime 影響 |
| 129-135 | `table_schema='governance' AND table_name='audit_log'` → `table_schema='learning' AND table_name='governance_audit_log'`；同步改 RAISE text | **runtime logic fix**（Guard A check 真實 target） |

副作用識別：
1. 改 Guard A check schema/table 名稱不影響 V107 schema 本身的 column / index / hypertable 定義（這些都在後續 DO 區塊）
2. 不影響 V107 上游 dependency（V096 TimescaleDB / V098 audit / V103 hypotheses）真實 cross-ref target
3. 不影響 V107 下游 reader（M11 audit JOIN query target）— reader 端假設的就是 `learning.governance_audit_log`
4. sandbox 已 V107 apply 過（per E1 Round 1 IMPL #2 finding）→ E1 patch 後需 idempotent re-apply 驗 0 RAISE；若 sandbox 走過舊版 Guard A path（遺留 `governance.audit_log` 表使 check 誤過），re-apply 走新版 Guard A path 應仍 PASS（learning.governance_audit_log 存在）

E1 工時估算：5-10 min（4 處 literal 替換 + 1 處 schema/table 條件改動 + 1 處 RAISE text 改動），Linux PG dry-run × 2 idempotent re-apply 驗 30 min。

## §5 Carry-over routing

**Sprint 1B E1 follow-up（NEW carry-over）**：

```
[CARRY-OVER #PA-DRIFT-1-V107-SQL] V107 SQL literal alignment patch
- File: sql/migrations/V107__replay_divergence_log.sql
- 4 location: governance.audit_log → learning.governance_audit_log
- 1 logic fix: Guard A schema/table check (line 129-135) + RAISE text
- Validation: Linux PG idempotent re-apply × 2，期望 0 RAISE / sandbox V107 仍 1 row
- Estimated: 5-10 min patch + 30 min validation = ~40 min E1
- Priority: P1（runtime logic 誤判風險，雖目前 sandbox 偶遇遺留表掩蓋）
- Parent: PA-DRIFT-1 Track 3 close → carry-over E1
- Sign-off: E2 audit + PA review patch
```

## §6 PA-DRIFT-1 closure verdict

| 項 | 狀態 |
|---|---|
| Spec doc (PA scope) | ✅ DONE — 0 patch needed |
| Spec doc literal hit count | 10× `learning.governance_audit_log` + 1× `governance.audit_log`（歷史 reconcile 注釋，保留） |
| V107 SQL drift（E1 scope） | ⚠️ CARRY-OVER E1 — 4 location patch needed |
| PG empirical 確認 | ✅ DONE — V035/V098 baseline = `learning.governance_audit_log` |
| Closure | ✅ PA SCOPE CLOSED + E1 CARRY-OVER OPEN |

**最終裁決：PA-DRIFT-1 spec scope ✅ DONE；V107 SQL drift 屬 E1 IMPL bug carry-over Sprint 1B 一併處理。**

不阻塞 Sprint 2 派發。E1 應於 Sprint 1B 收尾前完成 V107 SQL patch + Linux PG dry-run × 2。

---

**Notes**：
- 本 report 不改動任何 spec / SQL / TODO（純 verdict + carry-over routing）
- E1 follow-up patch 由 PM 派發決策（不在 PA dispatch scope）
- Memory 將更新「V107 SQL governance.audit_log drift = E1 carry-over Sprint 1B」教訓
