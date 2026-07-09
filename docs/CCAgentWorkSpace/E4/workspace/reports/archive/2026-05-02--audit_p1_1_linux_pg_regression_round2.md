# E4 Round 2 Linux PG Regression — AUDIT-2026-05-02-P1-1

- **Date**: 2026-05-02 13:08 CEST
- **Verdict**: **FAIL — RETURN TO E1**
- **Source mirror**: `.claude_reports/20260502_130800_e4_audit_p1_1_linux_regression_round2.md`

## Step summary

| Step | Status | Notes |
|---|---|---|
| 2 Apply V028+V030+V031+V032+V034 | **FAIL @ V031** | `ERROR: cannot drop columns from view` line 240 |
| 3 Fixture 17 cases | PASS | 17/17 NOTICE PASS, 0 FAIL/ERROR; isolated `v028_v034_guard_test` schema |
| 4 Idempotency (4 files; V031 excl) | PARTIAL PASS | V028/V030/V032/V034 second run 0 ERROR/RAISE; **V031 deterministic FAIL** |
| 5 Rust DESTRUCTIVE | SKIP | No separate test DB on Linux; would reset production |
| 6 audit_migrations.py | PASS | All 5 retrofit V### "ALL PRESENT OK"; V005 1-idx pre-existing gap unrelated |
| 7 passive_wait_healthcheck.py | PASS (WARN baseline) | Same baseline `[4][10][11][27][33][38][40][41]`; new `[23]` unrelated; `[22]` improved WARN→PASS |

## Root cause — V031 retrofit not idempotent on V034-extended state

V031 line 56 `CREATE OR REPLACE VIEW learning.mlde_edge_training_rows` 35-col body fails to replace V034-extended 53-col view in production. PG `CREATE OR REPLACE VIEW` rejects column drops by hard limitation. V031 retrofit author 注解假設 V034 還沒 land，但 production 已是 V031+V034 cumulative.

V034 production view actual shape: 53 cols incl. `scanner_market_regime` / `scanner_trend_phase` / `scanner_trend_score` / ... / `scanner_signed_dir_pct` (18 V034-only cols).

V031 second run (deterministic): `psql:V031:240: ERROR: cannot drop columns from view`.

**Violates CLAUDE.md §七 Migration Guard #4** — "每個新 migration 本地跑兩次 ... 第二次必須**不 RAISE**"。

## Recommended E1 fix

E4 推薦 **Option B**: V031 retrofit 加 `DO $$ ... $$` shape-guard 包 `CREATE OR REPLACE VIEW`：先驗 `information_schema.columns` 已是 V031+ 形狀則 skip 整段 view 重建，否則才執行。最符合 CLAUDE.md §七 Guard 模板精神 + V023 postmortem 對 legacy drift 的對偶 (對 future-shape drift 主動 skip 而非 RAISE)。

替代方案 (E1+FA 評估):
- A: V031 view body 直接加 V034 的 18 個 scanner_market_* 欄位 (簡單但未來 V035 +欄位再失敗)
- C: `DROP VIEW IF EXISTS` + `CREATE VIEW` 拒絕 — 短暫斷檔風險

## Workflow next

`@E1` Option B fix V031 → `@E2` 重審 idempotency claim 在 V034-applied state → `@E4` round 3 (range 縮為 V031 only):
1. Step 2 V031 single-file apply (must NOTICE-only)
2. Step 4 V031 second run (must NOTICE-only)
3. Step 6 audit (must V031 ALL PRESENT OK)

V028/V030/V032/V034 部分 PM 可記為「pre-validated round 2」，無需 round 3 全跑。

## Production safety guarantees met

- 沒對 production DROP/TRUNCATE/UPDATE
- 沒寫 secrets / authorization
- 沒改 risk_config
- 沒 commit / push
- Step 5 SKIP + 明示理由 (沒 test DB)
- PG password 從 env 讀，沒落到任何 stdout/log/report
