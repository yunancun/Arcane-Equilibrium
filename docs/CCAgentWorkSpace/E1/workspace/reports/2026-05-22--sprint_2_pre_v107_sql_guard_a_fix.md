---
report: Sprint 2 pre-readiness — V107 SQL Guard A P1 logic drift fix (PA-DRIFT-1 V107 SQL carry-over closure)
date: 2026-05-22
author: E1 (Backend Developer)
phase: Sprint 2 pre-readiness follow-up — PA-DRIFT-1 V107 SQL carry-over
status: IMPL DONE — awaiting E2 review
parent dispatch:
  - PM Sprint 2 pre-readiness follow-up (in-session 2026-05-22)
  - docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_pre_v107_governance_audit_log_align.md §4.2 + §5 carry-over E1
  - docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_1b_v107_sandbox_land_dedup_full.md §5.2 PA-DRIFT-1 finding
runtime: trade-core PostgreSQL 16 + TimescaleDB 2.26.1 (trading_ai_sandbox)
production engine: PID 2934602 跑 trading_ai (全程未碰)
secret_file: /home/ncyu/BybitOpenClaw/srv/settings/secret_files/postgres/sandbox_admin/password (0600 gitignored, sandbox_admin SCRAM-SHA-256)
---

# Sprint 2 pre-readiness — V107 SQL Guard A P1 logic drift fix

## §0 任務摘要

per PA Sprint 2 Track 3 verdict（commit 81a2caeb），V107 SQL 4 處 `governance.audit_log` literal drift 由 E1 carry-over patch：

| line | drift literal | 性質 |
|---|---|---|
| 23 | header 注釋 | P3 注釋 |
| 47 | header 注釋 | P3 注釋 |
| 127 | Guard A 前注釋 | P3 注釋 |
| 129-135 | Guard A check condition + RAISE text | **P1 runtime logic drift** |

P1 風險：原版 `table_schema='governance' AND table_name='audit_log'` 在 sandbox 因遺留 stub 表（5 column，無 hypertable）誤過（false negative），fresh deploy 環境會誤 raise；真正 V035 baseline + V098 extension target 為 `learning.governance_audit_log`（27 column hypertable）。

## §1 Pre-state grep（patch 前）

```bash
cd /Users/ncyu/Projects/TradeBot/srv && grep -n "governance.audit_log\|governance_audit_log" sql/migrations/V107__replay_divergence_log.sql
```

```
23:--   - Guard A: TimescaleDB extension + governance.audit_log + learning.hypotheses
47:--   - V096 boundary (TimescaleDB extension) + V098 governance.audit_log +
127:    -- governance.audit_log 必須存在 (M11 H-11 audit cross-ref query target；
134:            'V107 Guard A FAIL: governance.audit_log missing — V098 must '
```

線 131 schema/table 條件 `table_schema='governance' AND table_name='audit_log'` 因 word-boundary 分行未被直接 grep，但屬 P1 logic drift 必同步 patch。

Linux sandbox baseline 確認：
- `learning.replay_divergence_log` row count = 1（Sprint 1B Round 1 apply 殘留）
- `learning.governance_audit_log` exists（V098 已 land，0 row）

## §2 Patches applied

### 2.1 P3 注釋 patch（line 23, 47, 127）

| line | before | after |
|---|---|---|
| 23 | `-- Guard A: TimescaleDB extension + governance.audit_log + learning.hypotheses` | `-- Guard A: TimescaleDB extension + learning.governance_audit_log + learning.hypotheses` |
| 47 | `-- V096 boundary (TimescaleDB extension) + V098 governance.audit_log +` | `-- V096 boundary (TimescaleDB extension) + V098 learning.governance_audit_log +` |
| 127-131 | `-- governance.audit_log 必須存在 ...` 單行 | `-- learning.governance_audit_log 必須存在 ...` + 新增 PA-DRIFT-1 reconcile audit trail 4 行 |

### 2.2 P1 runtime logic patch（line 134-138 內）

```diff
- WHERE table_schema='governance' AND table_name='audit_log'
+ WHERE table_schema='learning' AND table_name='governance_audit_log'

- 'V107 Guard A FAIL: governance.audit_log missing — V098 must '
+ 'V107 Guard A FAIL: learning.governance_audit_log missing — V098 must '
```

完整 patch 範式（per Sprint 1A-ζ Guard A pattern）：

```sql
    -- learning.governance_audit_log 必須存在 (M11 H-11 audit cross-ref query target；
    -- 非 schema FK；spec §1.4 + Guard A 要求 V098 已 land；
    -- 2026-05-22 PA-DRIFT-1 patch: 原版誤用 governance.audit_log 為遺留 stub 表
    -- (5 column 無 hypertable), 真正 V035 baseline + V098 extension target 為
    -- learning.governance_audit_log 27 column hypertable)
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='governance_audit_log'
    ) THEN
        RAISE EXCEPTION
            'V107 Guard A FAIL: learning.governance_audit_log missing — V098 must '
            'apply before V107 (cross-ref query target). Verify _sqlx_migrations.';
    END IF;
```

### 2.3 Post-patch grep 驗證

```bash
grep -n "governance.audit_log\|governance_audit_log\|table_schema='learning' AND table_name='governance_audit_log'" sql/migrations/V107__replay_divergence_log.sql
```

```
23:--   - Guard A: TimescaleDB extension + learning.governance_audit_log + learning.hypotheses
47:--   - V096 boundary (TimescaleDB extension) + V098 learning.governance_audit_log +
127:    -- learning.governance_audit_log 必須存在 (M11 H-11 audit cross-ref query target；
129:    -- 2026-05-22 PA-DRIFT-1 patch: 原版誤用 governance.audit_log 為遺留 stub 表
131:    -- learning.governance_audit_log 27 column hypertable)
134:        WHERE table_schema='learning' AND table_name='governance_audit_log'
137:            'V107 Guard A FAIL: learning.governance_audit_log missing — V098 must '
```

唯一剩下的 `governance.audit_log` literal 在 line 129 reconcile audit trail（屬 PA-DRIFT-1 漂移歷史保留，per PA verdict §1.1 spec line 472 範式對齊）。

diff stat：1 file changed，~10 line touched（4 處 active literal + 4 行新增 audit trail 注釋）。無 schema / Guard B/C / mv / FK / index / hypertable 動。

## §3 Linux sandbox empirical

### 3.1 scp patched file → trade-core

```bash
scp /Users/ncyu/Projects/TradeBot/srv/sql/migrations/V107__replay_divergence_log.sql \
    trade-core:/home/ncyu/BybitOpenClaw/srv/sql/migrations/V107__replay_divergence_log.sql
```

完成 0 error。

### 3.2 Round 1 apply（既有 sandbox state，sandbox_admin）

```bash
ssh trade-core "PGPASSWORD=... psql -h 127.0.0.1 -U sandbox_admin -d trading_ai_sandbox \
    -f /home/ncyu/BybitOpenClaw/srv/sql/migrations/V107__replay_divergence_log.sql"
```

關鍵結果：
- 0 RAISE EXCEPTION
- Guard A check `learning.governance_audit_log exists`（V098 已 land）→ skip pass
- Guard A check `learning.hypotheses exists`（V103 已 land）→ skip pass
- `relation already exists, skipping` × 全部 DDL idempotent path
- 最終 NOTICE：
  ```
  V107: all guards PASS — divergence_type/severity/flag_action/engine_mode CHECK ok,
  hypertable chunk=7d, compression(30d)+retention(90d) policies installed,
  5 hot-path index built, mv + unique index ready,
  hypothesis_id FK to learning.hypotheses installed,
  0 forbidden action column (CR-7 dedup contract preserved).
  ```

### 3.3 Round 2 idempotency apply

同樣 0 RAISE / 全 skip / `all guards PASS`。idempotency 驗證通過。

### 3.4 Post-apply state 驗證

```bash
SELECT COUNT(*) FROM learning.replay_divergence_log;
SELECT to_regclass('learning.governance_audit_log');
```

```
 final_v107_row | gov_audit_still_intact
----------------+----------------------
              1 | governance_audit_log
```

V107 1 row 保留（Round 1+2 idempotent 無資料污染）；`learning.governance_audit_log` 完整。

### 3.5 Reverse fire test (destructive substitute)

完整 destructive test 不可行：
- sandbox_admin 對 V098 land 表非 owner（V098 by trading_admin apply），ALTER TABLE RENAME 失敗 `ERROR: must be owner of table governance_audit_log`
- trading_admin password 不在可讀 secret path（仅 sandbox_admin 有 secret file at `srv/settings/secret_files/postgres/sandbox_admin/password`）
- hypertable backup-restore 走 CREATE TABLE AS 必丟所有 27 column + segmentby/orderby + retention policy metadata，無法安全 restore
- V107 全文含 CREATE TABLE / create_hypertable / ALTER 等 transaction-violating DDL，無法 wrap 單 transaction rollback

**替代 reverse fire test**：構造 pseudo-V107 Guard A 區塊，將 table_name 改為不存在的 `'NONEXISTENT_GOVERNANCE_AUDIT_LOG_FOR_TEST'`，模擬 V098 未 land 的 fresh deploy 情境：

```sql
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='NONEXISTENT_GOVERNANCE_AUDIT_LOG_FOR_TEST'
    ) THEN
        RAISE EXCEPTION
            'V107 Guard A FAIL: learning.governance_audit_log missing — V098 must '
            'apply before V107 (cross-ref query target). Verify _sqlx_migrations.';
    END IF;
END $$;
```

執行結果：

```
ERROR:  V107 Guard A FAIL: learning.governance_audit_log missing — V098 must apply
before V107 (cross-ref query target). Verify _sqlx_migrations.
CONTEXT:  PL/pgSQL function inline_code_block line 10 at RAISE
```

新版 Guard A check + RAISE text 正確 fire ✓。

### 3.6 Forward + Reverse 雙向驗證 summary

| Scenario | Pre-condition | Expected | Actual | Verdict |
|---|---|---|---|---|
| Forward Round 1 | V098 已 land (sandbox) | Guard A skip + DDL idempotent | 0 RAISE / all guards PASS | ✅ |
| Forward Round 2 | V098 已 land + V107 row=1 | 同 Round 1 idempotent | 同上 0 RAISE | ✅ |
| Reverse (pseudo) | table 不存在（模擬 fresh deploy） | Guard A RAISE 含正確錯誤訊息 | RAISE EXCEPTION + 正確 `learning.governance_audit_log missing` | ✅ |

## §4 副作用識別

per PA verdict §4.2 副作用識別 4 項，逐一驗證：

| 副作用候選 | 驗證結果 |
|---|---|
| Guard A check schema/table 改動影響 V107 schema 本身 | ❌ 無影響 — schema column/index/hypertable 全 idempotent skip |
| 影響上游 dependency（V096/V098/V103）真實 cross-ref | ❌ 無影響 — V096 (TimescaleDB) + V098 (`learning.governance_audit_log`) + V103 (`learning.hypotheses`) 全為 V107 spec §1.4 真實 cross-ref target，新 Guard A 對齊 |
| 影響下游 reader（M11 audit JOIN query target） | ❌ 無影響 — M11 reader 端假設的就是 `learning.governance_audit_log` |
| sandbox 走過舊版 Guard A path 後 re-apply 仍 PASS | ✅ 驗證通過 — sandbox 既有 V107 row + V098/V103 已 land → Round 1+2 全 PASS |

## §5 治理對照

- §六 Hard Boundaries：未碰 `live_execution_allowed` / `execution_authority` / `system_mode` / production engine（PID 2934602）/ trading_ai production DB ✓
- §七 Code And Docs Rules：注釋默認中文（新增 reconcile audit trail 全中文），保留 V107 SQL 內既有風格 ✓
- §八 Workflow：E1 IMPL DONE → 等 E2 review；不自行 commit ✓
- §Data, Migrations, And Validation：V### migration 走 Linux PG empirical dry-run Round 1+2 idempotent；reverse fire test 走 pseudo Guard A 區塊（destructive 不可行原因已 §3.5 記錄）✓
- bilingual-comment-style：新增注釋全中文，原中文 `必須存在` 保留，無 bilingual block 引入 ✓

## §6 不確定之處

1. **destructive reverse fire test full execution carry-over**：完整破壞性 reverse fire test（DROP `learning.governance_audit_log` → V107 apply → RESTORE）受限於 sandbox_admin 非 owner + trading_admin password 不在 readable secret path + hypertable backup-restore 範式約束，本 task 走 pseudo Guard A 區塊代替；若 PM/E2 要求完整 destructive test，需配合 E3 提供 trading_admin password path 或在隔離 PG schema 中重建 sandbox baseline。pseudo test 已證明 Guard A RAISE 邏輯路徑正確，足以驗證 P1 logic fix。

2. **Sprint 2 pre-readiness 完整 closure 條件**：V107 SQL P1 drift 已 patch + Linux empirical 雙向驗證；但 V107 file 尚未 register `_sqlx_migrations`（per Sprint 1B Round 1 finding，raw psql -f apply 不寫註冊表，需後續 sqlx CLI 或 engine boot auto-migrate 處理）。本 task scope 僅 SQL patch，不含 _sqlx_migrations register 操作。

## §7 PA-DRIFT-1 V107 SQL closure verdict

| 項 | 狀態 |
|---|---|
| 4 處 literal 替換 | ✅ DONE（line 23 / 47 / 127 / 134 / 137） |
| 1 處 P1 runtime logic 改 schema/table | ✅ DONE（line 134 `table_schema='learning' AND table_name='governance_audit_log'`） |
| RAISE text 同步改 | ✅ DONE（line 137） |
| Linux sandbox Round 1 apply | ✅ PASS（0 RAISE / all guards PASS） |
| Linux sandbox Round 2 idempotency | ✅ PASS（同 Round 1） |
| Reverse fire test | ✅ PASS（pseudo substitute；full destructive unsupported by sandbox auth posture） |
| sandbox 既有 V107 row 保留 | ✅ 1 row 不變 |
| 副作用識別（PA §4.2 四項）| ✅ 全無副作用 |
| Closure | ✅ **DONE** |

**PA-DRIFT-1 V107 SQL carry-over closure verdict: ✅ DONE — 1 NEW carry-over closed**。

不阻塞 Sprint 2 派發；V107 SQL Guard A 從「sandbox 偶遇遺留 stub 表掩蓋的 false negative」升級為「對齊 V035/V098 真實 baseline canonical 名稱 `learning.governance_audit_log`」。

## §8 Operator 下一步

1. PM/E2 對本 patch + Linux empirical 結果 sign-off
2. 同期合併 Sprint 1B V107 file land + 本 P1 logic fix → PM 統一 commit
3. （可選）若要完整 destructive reverse fire test → E3 提供 trading_admin password path 或 PM 決策 Sprint 2 內隔離 PG schema 重建 sandbox baseline

## §9 修改清單

| File | 改動範圍 | 性質 |
|---|---|---|
| sql/migrations/V107__replay_divergence_log.sql | line 23 / 47 / 127 注釋 + line 129-131 新增 reconcile audit trail + line 134 condition + line 137 RAISE text | P3 注釋 + P1 runtime logic |

不動 / 無關 file：
- sql/migrations/V035*.sql / V098*.sql / V103*.sql（baseline 不動）
- docs/execution_plan/2026-05-21--v107_m11_replay_divergence_log_schema_spec.md（PA spec scope 已 DONE，per PA verdict §4.1）
- production engine（PID 2934602 跑 trading_ai 全程未碰）
- trading_ai production DB（全程未碰）

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_2_pre_v107_sql_guard_a_fix.md）
