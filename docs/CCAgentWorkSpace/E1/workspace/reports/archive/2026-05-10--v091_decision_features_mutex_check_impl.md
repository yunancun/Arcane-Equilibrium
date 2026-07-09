# E1 IMPL — V091 decision_features reject_close mutex CHECK NOT VALID (MIT MUST 2)

**Date**: 2026-05-10
**Author**: E1 Backend Developer (sub-agent)
**Status**: IMPL DONE — local commit `50e75bff` (push 被 sandbox 攔截，PM 統一 push)
**Spec source**:
- MIT W6-1 RFC sign-off verdict §8 必修條件 #2
  `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--w6_1_rfc_mit_signoff_verdict.md`
- §3 「兩 column TEXT vs alternatives」末段 SQL 範例 (line 84)
**File**: `srv/sql/migrations/V091__decision_features_reject_close_mutex_check.sql` (215 LOC)

---

## §1 任務摘要 / Task Summary

per MIT MUST 2 (W6-1 RFC sign-off 2026-05-10 20:38 UTC)：寫 V091 schema-level
CHECK NOT VALID 互斥不變式，防 future producer code bug 同 row 同時寫
reject_reason_code + close_reason_code 兩 column。

V086 land 在 `learning.decision_features` 加兩 column (reject_reason_code +
close_reason_code) + 12/14 enum CHECK constraint，但**缺 schema-level 互斥
CHECK**；當前 overlap=0 純靠 backfill SQL CASE WHEN evaluation order +
producer code separation discipline 強制。

V091 加 `chk_reason_code_mutually_exclusive` CHECK constraint NOT VALID 模式：
- 不掃 existing row (V086 backfill 已產 0 violation)
- 對新 INSERT/UPDATE 強制
- D+2 14:30 UTC 24h dual-write drift PASS 後 manual ALTER VALIDATE CONSTRAINT
  收緊歷史 row enforcement (本 migration 不執行 VALIDATE)

**狀態**：NOT_RUN artifact (D+1 evening 同次 producer code restart deploy)。

---

## §2 修改清單 / Changes List

| # | 動作 | 路徑 | 行數 |
|---|---|---|---|
| 1 | 新增 SQL migration | `srv/sql/migrations/V091__decision_features_reject_close_mutex_check.sql` | +215 |

**Total**: 1 file changed, 215 insertions.

**未動的相關文件**（per 任務指示「不要改」）：
- `srv/sql/migrations/V086__governance_reject_close_reason_code.sql` (production deployed)
- `srv/sql/migrations/V082__decision_features_evaluations_split.sql`
- `srv/sql/migrations/V083__fills_entry_context_id_close_check.sql`
- 不 dispatch P1-1/P1-2 W7 propagation (out of scope)

---

## §3 關鍵 diff / Critical Diff

### Constraint 主體 (line 140-143)

```sql
ALTER TABLE learning.decision_features
    ADD CONSTRAINT chk_reason_code_mutually_exclusive
    CHECK (NOT (reject_reason_code IS NOT NULL AND close_reason_code IS NOT NULL))
    NOT VALID;
```

**設計選擇**：
- Constraint 名 `chk_reason_code_mutually_exclusive` 對齊 MIT verdict §3 line 84 example
- CHECK 表達式採 `NOT (A AND B)` 而非等價的 `(A IS NULL OR B IS NULL)` —
  前者語意更直觀「兩 column 不能同時非 NULL」業務規則，與 MIT verdict §3
  line 84 example 等價變體
- NOT VALID 模式：不掃 existing row，只對新 INSERT/UPDATE 強制
- D+2 14:30 UTC 後 manual ALTER VALIDATE CONSTRAINT (本 migration 不執行)

### Idempotency pattern (line 130-152) 對齊 V083:173-189

```sql
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint c
        JOIN pg_class t ON t.oid = c.conrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        WHERE n.nspname = 'learning'
          AND t.relname = 'decision_features'
          AND c.conname = 'chk_reason_code_mutually_exclusive'
    ) THEN
        ALTER TABLE learning.decision_features
            ADD CONSTRAINT chk_reason_code_mutually_exclusive
            CHECK (NOT (reject_reason_code IS NOT NULL AND close_reason_code IS NOT NULL))
            NOT VALID;
        RAISE NOTICE 'V091: added NOT VALID CHECK ...';
    ELSE
        RAISE NOTICE 'V091: chk_reason_code_mutually_exclusive already present; skipping (idempotent)';
    END IF;
END $$;
```

第二次 apply 同 SQL 時，IF NOT EXISTS 守衛發現 constraint 已存在 → SKIP (no-op)
→ 對齊 V083:173-189 既有 NOT VALID CHECK pattern。

### Guard A (line 79-106) 確認 V086 已 land

```sql
DO $$
DECLARE v_missing TEXT[];
BEGIN
    -- 表存在性檢查
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema='learning' AND table_name='decision_features'
    ) THEN
        RAISE EXCEPTION 'V091 Guard A FAIL: learning.decision_features missing — V017/V086 must have applied first.';
    END IF;

    -- 兩 column 存在性檢查 (V086 ALTER TABLE 已加)
    SELECT array_agg(c) INTO v_missing
    FROM unnest(ARRAY['reject_reason_code', 'close_reason_code']) AS c
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema='learning' AND table_name='decision_features'
          AND column_name=c
    );
    IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
        RAISE EXCEPTION 'V091 Guard A FAIL: learning.decision_features missing required columns: %. V086 must have applied first.', v_missing;
    END IF;
END $$;
```

**設計選擇**：合併「table 存在 + column 存在」為單 Guard A，減 RAISE 訊息冗餘
(V086 already validates upstream V017 schema; V091 只需驗 V086 land 即可)。

### Existing-row violation 預檢 (line 163-184)

```sql
DO $$
DECLARE v_count BIGINT;
BEGIN
    SELECT COUNT(*) INTO v_count
    FROM learning.decision_features
    WHERE reject_reason_code IS NOT NULL
      AND close_reason_code IS NOT NULL;

    IF v_count > 0 THEN
        RAISE WARNING 'V091: % existing row(s) violate ... D+2 ALTER VALIDATE CONSTRAINT 會 fail ...', v_count;
    ELSE
        RAISE NOTICE 'V091: 0 existing row violate mutex invariant ...';
    END IF;
END $$;
```

**設計選擇**：純 advisory diagnostic block — RAISE WARNING (非 EXCEPTION)
不 abort migration; NOT VALID constraint 不會 enforce 在 existing row, 此區
僅給 D+2 ALTER VALIDATE CONSTRAINT 的「掃 historical row」階段 ahead-of-time
warning。預期 0 row (V086 backfill 已 empirical overlap=0 verified 2026-05-10
20:35 UTC + 2026-05-10 後續 verify)。

---

## §4 治理對照 / Governance Mapping

### CLAUDE.md §七 SQL migration 規範

| 規則 | V091 對應 | 證據 |
|---|---|---|
| Guard A: `CREATE TABLE IF NOT EXISTS` 前驗欄位俱在 | N/A (V091 不 CREATE TABLE) | — |
| Guard A 變體: 確認 upstream V086 schema land | ✅ Guard A line 79-106 驗 reject/close column 存在 | line 92-105 ARRAY check |
| Guard B: 型別敏感 ADD COLUMN 前驗 data_type | N/A (V091 不 ADD COLUMN) | — |
| Guard C: hot-path 索引欄位選用 | N/A (V091 不 CREATE INDEX) | — |
| Idempotency: 重跑兩次必須 PASS | ✅ IF NOT EXISTS pre-check 對齊 V083 pattern | line 132-152 |
| BEGIN/COMMIT atomic transaction | ✅ Single transaction, atomic | line 73 / 197 |
| MODULE_NOTE 中文注釋默認 (2026-05-05 governance change) | ✅ 注釋默認中文，必要 SQL keyword 保英文 | line 1-71 header + 各 §註解 |
| `bilingual-comment-style` skill (本 task 指定) | ✅ Header 動機/範圍/不變式/Idempotency/E2 checklist 6 區塊全有 | line 1-71 |
| 跨平台 grep `/home/ncyu` `/Users/[^/]+` 0 hits | ✅ V091 0 hits | grep 確認 |

### MIT MUST 2 (W6-1 RFC sign-off verdict) 對應

| MIT 要求 | V091 對應 | 證據 |
|---|---|---|
| 加 schema-level CHECK 防 future producer bug | ✅ chk_reason_code_mutually_exclusive | line 140-143 |
| NOT VALID 模式不阻 existing row | ✅ NOT VALID keyword | line 143 |
| D+2 14:30 UTC ALTER VALIDATE CONSTRAINT (本 migration 不執行) | ✅ 僅 RAISE NOTICE 提及 | line 124-125 / 213-214 |
| Constraint 命名對齊 MIT verdict §3 line 84 範例 | ✅ chk_reason_code_mutually_exclusive | identical |
| 0 existing row violation 證明 (V086 backfill clean) | ✅ Advisory pre-check + RAISE NOTICE | line 163-184 |

### 任務 spec 「不要」清單

| 不要 | V091 對應 |
|---|---|
| 不要跑 ALTER TABLE ... VALIDATE CONSTRAINT | ✅ 僅 RAISE NOTICE 提及 D+2 後續 work，不執行 |
| 不要改 V086 SQL | ✅ V086 純讀引用 (line 8 reference) |
| 不要 deploy V091 (PM 統一決定 D+1 evening restart 同次) | ✅ 僅本 NOT_RUN artifact + report |
| 不要 dispatch P1-1/P1-2 W7 propagation | ✅ 純 SQL skeleton + report 範圍 |

---

## §5 不確定之處 / Uncertainties + Push Back

### 5.1 Task spec drift: target table 名 `learning.decision_features_evaluations` vs `learning.decision_features`

**Finding**：Task prompt 寫的是 `learning.decision_features_evaluations` 表
加 CHECK constraint，但 V086 實際 ALTER 對象是 `learning.decision_features` (V086 line 195)。

**Empirical verify** (ssh trade-core 2026-05-10):
```sql
SELECT table_schema, table_name, column_name, data_type
FROM information_schema.columns
WHERE column_name IN ('reject_reason_code', 'close_reason_code');

→ learning|decision_features|close_reason_code|text
   learning|decision_features|reject_reason_code|text
```

`learning.decision_features_evaluations` 表 (V082 split 創建) 沒有
reject_reason_code / close_reason_code 兩 column。

**MIT verdict cross-reference**：MIT W6-1 RFC verdict §3 line 84 SQL example：
```sql
ADD CONSTRAINT chk_reason_code_mutually_exclusive
  CHECK ((reject_reason_code IS NULL OR close_reason_code IS NULL))
  NOT VALID;
```
無明指 table，但 §3 標題「兩 column TEXT (12 + 14 enum)」+ §1 verdict 4
context = V086 land 對象 = `learning.decision_features`。

**E1 決策**：採 V086 ALTER TABLE 對象 = `learning.decision_features`
(production reality + MIT verdict context)，非 task prompt typo
`decision_features_evaluations`。

**Push back to PM**：task prompt 該段 (Background 第二段 + 任務描述) 應修正
table 名為 `learning.decision_features` (V086 ALTER TABLE 對象)，避免後續
sub-agent 誤讀。

### 5.2 Linux PG dry-run 未跑 (per task: 不需 SQL apply)

per task spec：「不需 SQL apply (NOT_RUN artifact, D+1 evening 同 restart deploy)」。
本 V091 為 SQL skeleton 預寫，per `feedback_v_migration_pg_dry_run.md` E1 SOP
要求「DB migration IMPL 必有 Linux PG dry-run 通過才標 IMPL DONE」原則 — 但
本 task 指示「PM 統一決定 D+1 evening restart 同次 deploy」屬 governance
exception accept。

**Push back to PM**：D+1 evening 同次 deploy 前，建議 PM (或 E1 D+1 morning
sub-agent) 跑 Linux PG dry-run apply 兩次驗 0 RAISE，再進 sqlx_migrations
register + restart_all --rebuild。

### 5.3 sandbox 攔截 git push

**Finding**：local commit `50e75bff` 已 land `git log` (1 file changed,
215 insertions)，但 `git push origin main` 被 sandbox 攔截 (Reason:
"Push to main branch bypasses PR review")。

**E1 動作**：per task 指示「如 push 被 sandbox 攔截，stage + report；PM 統一
commit」— 但已 local commit 完成，此處變為「local commit 完成 + push 被攔
+ 等 PM 統一 push」。

**Push back to PM**：請 PM 統一 push commit `50e75bff` (含 V091 SQL) 到
origin/main，或交 operator 手動 push (per CLAUDE.md §七 git 自動化規則)。

### 5.4 Empirical overlap=0 是 snapshot, 不是 future guarantee

**Finding**：當前 V086 backfill empirical overlap_both=0 (PASS) 但這是
producer code 未 deploy 前的 backfill SQL 產出。D+1 evening producer
dual-write code restart deploy 後若 producer 寫雙 column bug → V091 NOT VALID
CHECK 會 RAISE INSERT/UPDATE 失敗 (per CHECK constraint 設計預期行為)。

**期待**：V091 + producer dual-write code 配對 deploy 即時 catch producer
code bug；不會等到 D+2 14:30 UTC ALTER VALIDATE CONSTRAINT 才暴露問題。

**Push back to PM/W6 cycle**：D+1 evening producer dual-write code restart
deploy 後 24h passive observation 期間，加 healthcheck monitor 「V091 CHECK
RAISE 次數」(via PG log grep 或 trigger-based counter)；若非 0 即 producer
code bug 立即 P0 alert。

### 5.5 Constraint 等價變體 vs MIT verdict 範例字面不同

**Finding**：MIT verdict §3 line 84 範例：
```sql
CHECK ((reject_reason_code IS NULL OR close_reason_code IS NULL))
```
V091 採等價變體：
```sql
CHECK (NOT (reject_reason_code IS NOT NULL AND close_reason_code IS NOT NULL))
```

兩者**邏輯等價** (De Morgan's law)，但字面不同。

**E1 選擇變體理由**：
- (a) 業務語意更直觀「兩 column 不能同時非 NULL」
- (b) 直接對應「mutex」(mutual exclusion) constraint name
- (c) PG planner / explain 兩者等價，無 perf 差異

**Push back to E2**：若 E2 review 認為應嚴格對齊 MIT verdict 字面寫法
(`(A IS NULL OR B IS NULL)`)，可 1 行 patch 切回。本 E1 採變體，請 E2
判斷是否需強制對齊。

---

## §6 Operator 下一步 / Operator Next Steps

### 6.1 立即動作 (E2/A3 review)

1. **E2 review V091**：
   - 確認 Guard A 對應 V086 column (line 79-106) ✅ pre-checked
   - 確認 CHECK syntax (line 142) — push back 5.5 確認
   - 確認 NOT VALID 模式 (line 143) ✅ pre-checked
   - 確認 idempotent IF NOT EXISTS pre-check (line 132-152) ✅ pre-checked
   - **Linux PG dry-run apply 兩次** — per `feedback_v_migration_pg_dry_run.md`
     E1 SOP，必驗 0 RAISE
   - V086 column 已 land empirical confirm (V086 production deploy)
   - sqlx checksum register 待 D+1 evening 同 restart

2. **A3 adversarial review** (per `feedback_impl_done_adversarial_review.md`):
   - DB migration IMPL = 高風險 IMPL
   - sub-agent IMPL DONE 不接受單獨 sign-off
   - PM 派 A3+E2 並行核驗

### 6.2 D+1 evening sequence (PM 統一 deploy)

1. PM 統一 push commit `50e75bff` (V091 SQL) 到 origin/main
2. ssh trade-core git pull --ff-only
3. Linux PG dry-run apply V091 兩次 (0 RAISE 驗 idempotent)
4. INSERT _sqlx_migrations row (sha384sum file 算 checksum)
5. engine restart_all --rebuild --keep-auth (含 W6-3c producer dual-write code deploy)
6. 24h passive observation 期間 monitor V091 CHECK RAISE 次數 (期望 0)

### 6.3 D+2 14:30 UTC manual sequence

1. healthcheck verify 24h dual-write drift PASS (post-V091 INSERT 0 violation)
2. operator manual:
   ```sql
   ALTER TABLE learning.decision_features
       VALIDATE CONSTRAINT chk_reason_code_mutually_exclusive;
   ```
3. verify constraint convalidated=true (`pg_constraint.convalidated`)
4. 收緊歷史 row enforcement 完成

### 6.4 Memory 更新 (E1 完成序列)

E1 自身 memory 不在本 IMPL 範圍直接寫入 (此 IMPL 屬 V091 SQL skeleton + report;
教訓 已 V086/V082/V083 階段沉澱)。如後續 D+1/D+2 deploy 觸發新教訓，再
追加 E1 memory.md。

---

## §7 預期時間 vs 實際

| 階段 | 預期 | 實際 |
|---|---|---|
| 啟動序列 (profile/memory/recent reports/reference docs/V086 SQL/MIT verdict) | 5-10 min | ~10 min |
| Linux PG empirical 驗證 V086 land + 表名 drift catch | 5 min | ~5 min |
| V091 SQL 撰寫 (215 LOC) | 15-25 min | ~15 min |
| E2 self-review checklist | 5 min | ~3 min |
| Git stage + commit (push 被攔) | 2 min | ~2 min |
| Report 撰寫 (8 sections) | 10 min | ~15 min |
| **Total** | **30-45 min** | **~50 min** |

略超 task 預估，主因為 task spec drift catch (5.1) + Linux PG empirical
verify 額外時間。

---

## §8 Sign-off 必檢 git status (per CLAUDE.md §七 P0-GOV-3)

```
Branch: main
Local commit: 50e75bff (V091 SQL skeleton: decision_features reject_close mutex CHECK NOT VALID)
Remote sync: NOT pushed (sandbox blocked)
File state: 1 file changed, 215 insertions
git status sql/migrations/V091__decision_features_reject_close_mutex_check.sql: clean (committed)
```

**Awaiting**:
- E2 + A3 adversarial review (per `feedback_impl_done_adversarial_review.md`)
- PM 統一 push 50e75bff 到 origin/main
- D+1 evening Linux PG dry-run + sqlx register + restart_all 同次 deploy

---

E1 IMPLEMENTATION DONE: 待 E2 + A3 審查 (report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--v091_decision_features_mutex_check_impl.md`)
