# E4 Round 3 Narrowed Linux PG Regression — AUDIT-2026-05-02-P1-1

- **Date**: 2026-05-02 13:31 CEST
- **Verdict**: **PASS — ready for PM Sign-off**
- **Source mirror**: `.claude_reports/20260502_133122_e4_audit_p1_1_round3_narrowed.md`
- **Linux HEAD**: `6cb1c3b fix(audit-p1-1): V031 view shape-guard for V034-applied state (round 3)`

## Step summary

| Step | Status | Notes |
|---|---|---|
| 2N V031 first run | **PASS** | Shape-guard NOTICE-skip @ line 361, 0 ERROR |
| 2N V031 second run | **PASS** | Idempotent re-run, NOTICE-skip again, 0 ERROR |
| 3N Fixture (20 cases incl 3 round-3) | **PASS** | 20/20 TEST PASS, 0 FAIL/ERROR; isolated `v028_v034_guard_test` schema |
| 6N View col count | **PASS** | 53 cols preserved (V034 augment intact, not narrowed to 35) |
| 6N audit_migrations.py | **PASS** | `OK V031__ml_dream_edge_unblock.sql`, all canary present, 0 V031 drift |
| 7N passive_wait_healthcheck.py | **PASS** | WARN baseline same as round 2; 0 new FAIL |

## Round-3 fix verified

V031 line ~351-361 加 `DO $$ ... $$` shape-guard：先 query `information_schema.columns` 驗 `learning.mlde_edge_training_rows` 是否已含 V031 baseline cols；若是 → RAISE NOTICE + skip 整段 `CREATE OR REPLACE VIEW`；若否（fresh install 或被窄化）→ fall through to CREATE。三條 path 由 round-3 新加 fixture 完整覆蓋：
- `TEST V031/View-fresh: PASS fresh-install path falls through to CREATE`
- `TEST V031/View-extended: PASS view-extended path correctly identifies skip`
- `TEST V031/View-drift: PASS view-shape Guard A correctly raised on narrowed view`

E4 round 2 觀察的 deterministic FAIL `psql:V031:240: ERROR: cannot drop columns from view` 已消除。

## Production safety guarantees met

- 沒對 production DROP/TRUNCATE/UPDATE
- V034 53-col view shape 在兩次 V031 re-apply 後仍 = 53（zero downtime / zero schema drift）
- 沒寫 secrets / authorization
- 沒改 risk_config
- 沒 commit / push（PM 收）
- PG password 從 env / SSH heredoc 注入，未落 stdout / log / report

## Round-2 retained scope

V028 / V030 / V032 / V034 idempotent + 17 of 20 fixture cases 為 round 2 PASS，按 narrowed scope 未重跑。Round 3 fixture re-run 確認該 17 case 仍綠（fixture 整體 20/20 PASS）。

## Workflow next

`@PM` 接手 Sign-off + commit + push。建議 commit message 詳見 source mirror report Operator 下一步章節。

## Open items (non-blocking)

- `helper_scripts/db/audit_migrations.py` 報 `MISSING learning.model_registry:idx_model_registry_active` — 屬 V023 pre-existing gap，與本 audit 無關。建議 PM 視情況開 P3 ticket（V023 retrofit follow-up）。
- 任務 prompt 寫「fixture 共 21 case」實測 = 20（round 2 baseline 17 + round 3 新 3）；E4 評估為 prompt 筆誤，三條 view-shape path（fresh/extended/drift）已完整覆蓋，無缺第 4 case。
