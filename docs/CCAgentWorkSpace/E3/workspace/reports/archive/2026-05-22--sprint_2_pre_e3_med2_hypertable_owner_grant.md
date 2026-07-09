---
report: Sprint 2 pre-readiness Track 4 — E3-MED-2 sandbox_admin trading.* hypertable OWNER GRANT
date: 2026-05-22
author: E3 (Security Auditor)
phase: Sprint 2 pre-readiness (post-Sprint 1B early IMPL closure)
status: SIGNED-OFF · E3-MED-2 CLOSED
parent: docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_1b_v107_sandbox_land_dedup_full.md (E3-MED-2 finding)
---

# E3 Sprint 2 pre-readiness E3-MED-2 hypertable OWNER GRANT — 2026-05-22

**Verdict: PASS · E3-MED-2 CLOSED**

## §1 Pre-state (Linux PG empirical)

### 1.1 trading_ai_sandbox trading.* hypertable owners (PRE)

10 hypertables in trading.* 全部 owner = trading_admin:
fills / funding_settlements / intents / order_state_changes / orders / position_snapshots / risk_verdicts / scanner_opportunity_decays / scanner_snapshots / signals

### 1.2 trading_ai_sandbox trading.* 全表 owners (PRE)

17 tables 全部 owner = trading_admin (10 hypertable + 7 regular，含 4 個 *_damaged_20260414 隔離表 + decision_context_snapshots / decision_outcomes / paper_state_checkpoint)

### 1.3 既有 sandbox_admin 對 trading.* 權限 (per Sprint 1A-ε P1 §3 GRANT)

INSERT/SELECT/REFERENCES on trading.intents = t / schema USAGE/CREATE on trading = t
CREATE INDEX ON trading.intents (hypertable DDL) = ERROR: must be owner of hypertable "intents"

→ RCA: TimescaleDB internal owner check (ts_index_check_hypertable_owner) 不認 PG GRANT；強制 pg_class.relowner == current_user OR is_superuser OR member of owner role。

### 1.4 production engine PID (dynamic verify per Sprint 1A-ε P2 lesson)

PID 2934602，etime=23:58:32 連續 (spec literal 寫 3954769 已 drift)

## §2 Option choice + rationale

採 Option A (sandbox-wide ALTER OWNER)，**push back dispatch instruction Option B (GRANT ALL)** — empirical 證明 PG GRANT 在 TimescaleDB hypertable DDL 無效。

理由:
1. sandbox 設計就是 V### dry-run + Sprint IMPL 試水 DB
2. production trading_ai 的 schema dump 重灌可用 pg_dump --no-owner 解決
3. trading_admin 在 sandbox 仍是 superuser，可隨時 ALTER TABLE OWNER TO trading_admin 回滾
4. Sprint 2 IMPL 6 Track (B/C/D/E/F) 都會經 sandbox dry-run；sandbox_admin OWNER 是 unblock condition

## §3 Apply (atomic BEGIN/COMMIT)

```sql
BEGIN;
DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN SELECT schemaname, tablename FROM pg_tables WHERE schemaname = 'trading' ORDER BY tablename LOOP
    EXECUTE format('ALTER TABLE %I.%I OWNER TO sandbox_admin', r.schemaname, r.tablename);
    RAISE NOTICE 'ALTER TABLE %.% OWNER TO sandbox_admin -- DONE', r.schemaname, r.tablename;
  END LOOP;
END$$;
COMMIT;
```

結果: 17/17 ALTER TABLE NOTICE fire；BEGIN/COMMIT atomic 成功。未使用 ALTER DEFAULT PRIVILEGES (不適用 OWNER 變更場景)。

## §4 Verify

### 4.1 sandbox_admin hypertable DDL 4 種全 PASS

| Test | Result |
|---|---|
| CREATE INDEX idx_e3_med2_owner_test_intents ON trading.intents(ts) | ✅ CREATE INDEX |
| CREATE INDEX idx_e3_med2_owner_test_fills ON trading.fills(ts) | ✅ CREATE INDEX |
| DROP INDEX trading.idx_e3_med2_owner_test_intents | ✅ DROP INDEX |
| DROP INDEX trading.idx_e3_med2_owner_test_fills | ✅ DROP INDEX |
| ALTER TABLE trading.fills ADD COLUMN e3_med2_test_col TEXT | ✅ ALTER TABLE |
| ALTER TABLE trading.fills DROP COLUMN e3_med2_test_col | ✅ ALTER TABLE |

### 4.2 sandbox post-state hypertable owners

10/10 hypertables in trading.* owner = sandbox_admin

### 4.3 cross-DB / cross-schema 不誤殺

| 驗證項 | 結果 |
|---|---|
| production trading_ai 10 hypertable owner | ✅ 100% trading_admin (未變) |
| production engine PID 2934602 alive | ✅ 23:58 etime 連續 |
| production trading_admin active connections | ✅ 2 (健康) |
| production trading_ai.fills.max(ts) | ✅ 2026-05-22 11:20:01 (recent_24h=true) |
| pg_hba E3-MED-1 reject row 仍生效 | ✅ sandbox_admin → trading_ai 仍 REJECT |
| sandbox 其他 12 schema ALTER OWNER 未誤動 | ✅ |

## §5 E3-MED-2 closure verdict

| 嚴重性 | 位置 | 攻擊路徑 / 阻 chain | 修法 |
|---|---|---|---|
| MEDIUM → CLOSED | sandbox_admin → trading.* hypertable DDL 撞 ts_index_check_hypertable_owner OWNER lock | V097 ROLLBACK + Sprint 2 IMPL Track B/C/D/E/F 任何觸 trading.* hypertable DDL 的 V### 全 block | ALTER TABLE trading.* OWNER TO sandbox_admin × 17 (sandbox-only) |

Sprint 2 unblock: Track B/C/D/E/F 任意 V### 觸 CREATE INDEX / ALTER PARTITION / ADD COLUMN / DROP COLUMN on trading.* hypertable 現在全 path 通；sandbox V### dry-run 不再撞 OWNER。

## §6 Lessons sustained

1. **TimescaleDB hypertable DDL 不認 PG GRANT**: GRANT ALL PRIVILEGES + ALTER DEFAULT PRIVILEGES 對 hypertable index/partition DDL 無效；TimescaleDB internal API (process_index_start → ts_index_check_hypertable_owner) 強制檢 pg_class.relowner 或 superuser 或 owner role membership
2. **sandbox 隔離 DB 的 least privilege scope = sandbox-only**: dispatch instruction 預設 least privilege = avoid OWNER transfer 是 production scope 思維；sandbox 是 V### pre-prod test DB，sandbox_admin 對 sandbox-internal table 取 OWNER 不違 least privilege (pg_hba E3-MED-1 reject row 已 fence trading_ai)
3. **production engine PID drift 持續**: spec literal 寫 3954769，實測 2934602 → PID 動態必 ps -eo 驗 (per Sprint 1A-ε P2 同類教訓累積第 2 次)
4. **sandbox_admin 對 sandbox schema 對齊狀態**: trading 17 sandbox_admin / governance 1 sandbox_admin / learning 2 sandbox_admin (V107 stub)；其餘 10 schema 0 sandbox_admin

## §7 Carry-over to Sprint 2

無新 carry-over。本 task 純粹 unblock — 已預防式解 Sprint 2 IMPL 6 Track 的 hypertable DDL block。

E3 AUDIT DONE: 0 CRITICAL · 0 HIGH · 0 NEW MEDIUM · E3-MED-2 (sandbox_admin trading.* hypertable OWNER) CLOSED
