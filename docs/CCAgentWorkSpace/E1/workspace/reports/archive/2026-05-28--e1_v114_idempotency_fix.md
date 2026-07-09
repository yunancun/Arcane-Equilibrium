# E1 IMPL — V114 idempotency BLOCKER fix · 2026-05-28

## 任務摘要

MIT 第二輪 dry-run 雙跑抓到 V114 idempotency BLOCKER：上輪（2026-05-28）的
GRANT-before-compression reorder 只解 first-run，未解 re-apply。compressed twin
（`_compressed_hypertable_NN`）由 first-run 的 compression enable 建立後**跨 migration
run 持久存在**；second+ apply（engine restart sqlx migrate / 雙跑）重抵 column-level
`GRANT UPDATE (acked_at_utc, acked_by)` 時 twin 已存在 → TimescaleDB 把 column-level
grant 傳播到 twin → twin 無 `acked_at_utc` column → `ERROR: column "acked_at_utc" of
relation "_compressed_hypertable_NN" does not exist`（SQLSTATE 42703 undefined_column）
→ abort → migration 鏈卡死 engine 起不來。

採 **修法 (a)**：把 column-level `GRANT UPDATE` 單句包進 nested
`BEGIN ... EXCEPTION WHEN undefined_column THEN RAISE NOTICE; END;`。

## 修改清單

| 檔 | 改動 | 性質 |
|---|---|---|
| `srv/sql/migrations/V114__notification_failsafe_events_hypertable.sql` | Step 4 GRANT block：column-level `GRANT UPDATE` 句包 nested `BEGIN/EXCEPTION WHEN undefined_column/END` | idempotency fix（非 schema 改動） |
| 同檔 Step 4 header 註解 | 補「reorder 仍不夠 + nested EXCEPTION」FIX MIT-2026-05-29 段 | 註解（中文） |
| `srv/docs/CCAgentWorkSpace/E1/memory.md` | append 教訓 | memory |

**schema 一字未改**：CREATE TABLE 17 column / create_hypertable 7d chunk / 2 index /
event_type CHECK / compression policy 30d / Guard A/B/C 全部 byte-identical 未動。

## 關鍵 diff（V114 Step 4，line 239-257）

```sql
    -- UPDATE 限 acked_at_utc + acked_by 2 column (append-only enforcement)
    -- 為什麼包 nested BEGIN/EXCEPTION (FIX MIT-2026-05-29 idempotency blocker, 2nd-run-only):
    --   ... compression enable 建的 compressed twin 跨 migration run 持久存在 ...
    --   first-run 已把 grant 落 pg_attribute.attacl ... swallow undefined_column 即可保冪等
    BEGIN
        EXECUTE 'GRANT UPDATE (acked_at_utc, acked_by) ON observability.notification_failsafe_events TO trading_admin';
    EXCEPTION
        WHEN undefined_column THEN
            RAISE NOTICE
                'V114: column-level GRANT UPDATE skipped — compressed twin exists on '
                're-apply (grant already in pg_attribute.attacl from first-run; idempotent)';
    END;
```

外層 role-exists guard `DO $$`（line 224）已存在，故採 **inline nested BEGIN**，不新開
`DO $$`（PL/pgSQL 函數體內合法的巢狀 sub-block）。

## first-apply + re-apply 冪等邏輯靜態確認

**first-apply（clean DB）**：
- twin 尚未存在 → `GRANT UPDATE (acked_at_utc, acked_by)` 在 fresh table 合法執行 → grant
  落 `pg_attribute.attacl`（acked_at_utc/acked_by = w）。
- nested EXCEPTION 不觸發（無 undefined_column）→ 行為與 fix 前 first-run 等價，正確性不變。
- Step 5 compression enable 在 GRANT 之後（reorder 維持）→ twin 此時才建，column-level
  grant 已落，不受傳播影響。

**second+ apply（re-apply / 雙跑 idempotency / engine restart sqlx migrate）**：
- 表已存在 + twin 已存在。
- `GRANT UPDATE (acked_at_utc, acked_by)` 被 TimescaleDB 傳播到 twin → twin 無
  acked_at_utc → 拋 `undefined_column` (42703)。
- nested handler `WHEN undefined_column THEN RAISE NOTICE` 吞掉 → 不 abort。
- grant 已在 first-run 落 attacl，re-apply 無需再執行 → 語義冪等。
- handler **只** `WHEN undefined_column`：fresh table 上任何真正的 GRANT 失敗（role 缺 /
  object 缺）仍 re-raise fail-loud，不被誤吞。

**不變量靜態核對**：
- 5 `DO $$` = 5 `END $$;` 平衡（nested inner `BEGIN/END;` 無 `$$` 不計入）。
- 所有 GRANT/REVOKE 可執行句（line 237/250/260/264）行號 < compression enable
  `ALTER TABLE ... SET (timescaledb.compress ...)`（line 280-281）→ GRANT-before-compression
  reorder 維持。
- table-level GRANT SELECT,INSERT（237）+ GRANT USAGE ON SEQUENCE（260）+ REVOKE PUBLIC
  UPDATE/DELETE（264）保持原樣 — 本就冪等（table-level grant 不查 column，不傳播 twin）。
- Guard A（schema+V113+TimescaleDB）/ Guard B（chunk drift）/ Guard C（17 col + CHECK +
  hypertable + index + GRANT row）邏輯全未動。
- role-missing 早退 `RETURN`（line 233）保留。

## 治理對照

- CLAUDE.md §Data「Migration idempotency must be tested by applying twice」+ memory
  `feedback_v_migration_pg_dry_run`：本 fix 直接回應雙跑失敗。靜態通過 ≠ runtime apply
  通過，故 sign-off 權威仍歸 MIT 第三輪 Linux PG 雙跑。
- 硬邊界未碰：max_retries / live_execution_allowed / execution_authority / system_mode
  皆無關本 SQL；append-only 強制（column-level UPDATE 限 + PUBLIC REVOKE）語義保持。
- Guard A/B/C 標準維持（新 migration 必含 Guard A/B/C）。
- 註解默認中文（`bilingual-comment-style` / `feedback_chinese_only_comments`）。

## 不確定之處

- **靜態驗限制**：Mac 無生產 PG。本地 /tmp:5432 有 PG server 但缺 TimescaleDB extension +
  observability schema + V113 baseline + trading_admin role（Guard A 會先 RAISE
  EXCEPTION），無法 exercise twin-propagation 路徑。**未對任何 PG apply**（守禁線）。
- `undefined_column` (SQLSTATE 42703) 是 TimescaleDB column-level grant 傳播到 compressed
  twin 缺 column 時拋的精確錯誤類別（MIT 第二輪 empirical 確認錯誤訊息為此）。靜態信賴此
  SQLSTATE 對齊；MIT 第三輪重跑會 empirical 確認 handler 確實捕捉。

## 重申：MIT 第三輪重驗前置（必須）

本 fix **需 MIT 第三輪 Linux trade-core 重跑 4-step dry-run（含雙跑 idempotency）才能
sign-off**。operator 已 DROP 第二輪 dirty 殘留表（per MIT memory：partial-apply 留下表 +
twin，V114 未進 `_sqlx_migrations`，須 operator `DROP TABLE ... CASCADE` 後再 apply E1
修正版）。在 dirty 殘留未清前直接 sqlx migrate 仍會重撞同 error。

## C5 restricted-role follow-up（已記 report）

MIT 發現：`trading_admin` = 表 OWNER + superuser，隱式持全 17 column UPDATE
（`information_schema.column_privileges` 顯示全 column UPDATE）；column-level 限制只 bind
**非-owner 非-super** role。production GUI ack 路徑前置 = **provision restricted role**
（e.g. `failsafe_ack_role`，只 column UPDATE acked_* / acked_by，不可碰其他 column）。當前
DB 無此受限 role（僅 replay_writer_role / sandbox_admin / trading_admin）。**本 task 不建
role**（屬 C5 Sprint 3）；此處僅標記為 C5 GUI ack 路徑前置 follow-up。

## Operator 下一步

1. 派 E2 審查本 idempotency fix（nested EXCEPTION 邏輯 + 不變量）。
2. E2 通過後派 E4 regression。
3. MIT 第三輪 Linux trade-core 重跑 4-step dry-run（含雙跑 idempotency）—— operator 須先
   確認第二輪 dirty 殘留表已 DROP。
4. 全鏈綠後 PM 統一 commit（1 commit：V114 idempotency fix）+ push。
5. C5 Sprint 3：provision `failsafe_ack_role` restricted role（本 task 範圍外）。

---

E1 IMPLEMENTATION DONE：待 E2 審查（report path:
`srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-28--e1_v114_idempotency_fix.md`）
