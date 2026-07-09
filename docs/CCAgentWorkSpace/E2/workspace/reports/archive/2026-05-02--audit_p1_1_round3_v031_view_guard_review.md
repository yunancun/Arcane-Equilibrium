# E2 Round 3 — V031 view-shape Guard A retrofit review

> AUDIT-2026-05-02-P1-1 round 3 · target = E1 round 3 self-report `srv/.claude_reports/20260502_131741_e1_audit_p1_1_round3_v031_view_guard.md`

## 結論
**PASS to E4 round 3 narrowed scope** — V031 single-file Step 2 + Step 4 + Step 6 audit on Linux production DB（V034-applied state，commit `e858ae2` baseline）。0 CRITICAL / 0 HIGH / 1 MEDIUM（test fixture 946 LOC follow-up split）/ 1 LOW（self-report LOC delta 偏差 indent-only）。

## 8 條檢查 verdict
1. v_v031_cols 對外 SELECT alias 對齊 — ✅ 34/34 PASS（cross-check V034 同 baseline 一致）
2. DO block 三路徑邏輯 — ✅ Path 1/2/3 + 第 4 邊界（fresh-state 第二跑）皆綠
3. Idempotency — ✅ Mac PG 16.13 fresh-install 路徑驗證；V034-applied state 必交 E4 Linux production-state empirical
4. PG DO/EXECUTE 語法 + dollar-quoting + 單引號 — ✅ 4 對 `$$/$migration$/$view$/$cmt$` 全配對；view body verbatim（whitespace-normalized diff 唯一差 = 結尾分號）
5. Test fixture 3 case — ✅ View-extended/drift 高質量；View-fresh 接受設計（同 V034 noop pattern）；schema isolation OK
6. Scope creep — ✅ 只 2 檔（V031 + test）；後段 mlde_shadow_recommendations Guard A 不動；view body 0 業務邏輯改動
7. §七 雙語 + 跨平台 + LOC — ✅ V031 464 / test 946（MED follow-up）；中英對照齊；0 user-home hardcode
8. Report governance — ✅ E1 .claude_report 113 行 6 節中文；workspace report 61 行；Mac PG caveat 明示 Linux 補驗

## Findings 詳情
- **MED-1 (test fixture LOC 946 > 800)**：per pre-existing baseline exception clause 不 BLOCK；建議 follow-up `TEST-FIXTURE-SPLIT P3` 拆 `test_v028_guards.sql` + `test_v030_v031_v032_guards.sql` + `test_v034_v031_view_guards.sql`
- **LOW-1 (E1 self-report `+173/-8` vs git numstat `+314/-196`)**：indent-only line 計算口徑差，不影響業務邏輯結論；E1 memory append lesson 即可

## E4 round 3 必跑
1. `ssh trade-core "psql -U trading_admin -d trading_ai -v ON_ERROR_STOP=1 -f sql/migrations/V031__ml_dream_edge_unblock.sql"` 跑兩次 — 必見 NOTICE `V031 view-shape guard: learning.mlde_edge_training_rows already contains all V031 baseline cols (likely extended by V034+); skipping CREATE OR REPLACE VIEW`，0 ERROR；view col count 不變
2. `ssh trade-core "psql ... -f sql/migrations/tests/test_v028_v034_guards.sql 2>&1 | grep FAIL"` — 必 0 hit（21 case 全綠）
3. `ssh trade-core "OPENCLAW_TEST_PG=postgresql://... OPENCLAW_TEST_PG_DESTRUCTIVE=1 cargo test --release -p openclaw_engine --test migrations_test"` — 5/5 含 `fresh_db_applies_all_migrations_end_to_end` 真實 execute V001..V034

## 不確定 / 留給 E4
- **V034-applied state production-state empirical 驗證**：E2 Mac 無 TimescaleDB（V005/V010/V023/V026 部分 DDL 失敗 → 跑不到 V034 path）；DO block 邏輯路徑分析 + V034 既有 guard 同 baseline → 演繹必綠，但 E4 Linux 必補
- **Cargo migrations_test 5/5 in Mac wiring smoke**：無 OPENCLAW_TEST_PG 路徑只驗 parser + seed/canary detection；不證 SQL 真套到 PG。E4 必跑 destructive ack 版本

## E2 memory 教訓追加
12 條已 append（7-13 號），覆蓋：
- CREATE OR REPLACE VIEW 不 idempotent 反模式
- View 對外 column ≠ CTE alias
- whitespace-normalized diff 驗業務邏輯不變手法
- PG dollar-quoting single-quote 處置
- Test fixture LOC 警戒處置
- Idempotency 三步驗證模板
- 同一 view 多 migration baseline 一致性 cross-check
