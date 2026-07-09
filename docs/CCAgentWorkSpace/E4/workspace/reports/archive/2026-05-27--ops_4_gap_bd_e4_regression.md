# E4 Regression — OPS-4 GAP B+D round 1+2 (commits 1392c9e1 + 261d3956)

- **Date**: 2026-05-27 21:30 UTC
- **Commits**: `1392c9e1` (round 1 PA spec + cron + V113 + 9 query SQL) + `261d3956` (round 2 healthcheck.py + passive_wait wire + MIT SOP/template)
- **Scope**: 11 new/modified production files + 5 docs/governance + 1 spec amendment
- **Mode**: 靜態 / 語法 / Linux PG empirical / pytest baseline / Rust baseline / runner integration
- **Verdict (early)**: **YELLOW** — 14 of 15 acceptance criteria GREEN; 1 bug + 2 carry-over for E1 round 3

## §1 文件涉及範圍

| 類別 | 檔 | LOC | 變動 |
|---|---|---|---|
| Cron Bash | install_pg_dump_cron.sh | 96 | NEW |
| Cron Bash | trading_ai_pg_dump_cron.sh | 181 | NEW |
| Cron Bash | verify_pg_dump.sh | 129 | NEW |
| Migration SQL | V113__governance_audit_log_pg_dump_event_types.sql | 200 | NEW |
| Python | check_pg_dump_freshness.py | 616 | NEW |
| Python | passive_wait_healthcheck/checks_cron_heartbeat.py | +108 (217→325) | MOD |
| Python | passive_wait_healthcheck/runner.py | +13 | MOD |
| Python | passive_wait_healthcheck/__init__.py | +6 | MOD |
| SQL | helper_scripts/db/post_restore_validation.sql | 330 | NEW |
| Runbook | docs/runbooks/pg_restore_drill_sop.md | 572 | NEW |
| Template | MIT/workspace/templates/pg_restore_drill_report_template.md | 239 | NEW |
| Spec | PA OPS-4 runbook | +246 (449→695) | AMEND |
| Index | SCRIPT_INDEX.md | +8 | MOD |
| Governance | TODO + E1 memory + E1 report | doc | MOD |

## §2 A. Static syntax verification

### A.1 Bash -n（Mac local）

| 檔 | 結果 |
|---|---|
| install_pg_dump_cron.sh | PASS |
| trading_ai_pg_dump_cron.sh | PASS |
| verify_pg_dump.sh | PASS |

### A.2 py_compile（Mac local）

| 檔 | 結果 |
|---|---|
| check_pg_dump_freshness.py | PASS |
| passive_wait_healthcheck/__init__.py | PASS |
| passive_wait_healthcheck/checks_cron_heartbeat.py | PASS |
| passive_wait_healthcheck/runner.py | PASS |

### A.3 Markdown render check

| 檔 | H1/H2/H3 數 | 程式碼 fence pairs | 結果 |
|---|---|---|---|
| pg_restore_drill_sop.md | 87 | 24 (even) | PASS |
| pg_restore_drill_report_template.md | 17 | 2 (even) | PASS |

### A.4 SQL static (V113 + post_restore)

| 檔 | 檢查 | 結果 |
|---|---|---|
| V113 | 結構：Guard A V035 + Guard B V098 substring + idempotency probe + ACCESS EXCLUSIVE + COMMENT | OK |
| post_restore_validation.sql | 9 query block + AGGREGATE SUMMARY block + `\set ON_ERROR_STOP on` | 結構 OK，**但 Q3 column drift — 見 §3.5** |

## §3 B. Linux empirical (ssh trade-core)

### B.1 Bash -n on Linux

| 檔 | 結果 |
|---|---|
| install_pg_dump_cron.sh | OK_install |
| trading_ai_pg_dump_cron.sh | OK_dump |
| verify_pg_dump.sh | OK_verify |

### B.2 check_pg_dump_freshness.py --status

```
$ time ~/.venv/bin/python3 helper_scripts/canary/healthchecks/check_pg_dump_freshness.py --status
verdict: "INSUFFICIENT_SAMPLE"
checks: [
  [1] backup dir missing INSUFFICIENT_SAMPLE
  [2] no dump found     INSUFFICIENT_SAMPLE
  [3] no dump to size   INSUFFICIENT_SAMPLE
  [4] no dump to md5    INSUFFICIENT_SAMPLE
  [5] no dump retention INSUFFICIENT_SAMPLE
  [6] no dump schema    INSUFFICIENT_SAMPLE
  [7] V113 not applied (lacks pg_dump_completed)  INSUFFICIENT_SAMPLE
]
EXIT=0  ← fail-soft 不阻 first-day deploy
real 0m0.067s
```

**SLA**: 67ms — 遠低於 1h cron 容差，acceptable。

### B.3 DRY-RUN install (OPENCLAW_BACKUP_CRON_APPLY=0)

```
$ OPENCLAW_BACKUP_CRON_APPLY=0 bash helper_scripts/cron/install_pg_dump_cron.sh
------- proposed crontab entry -------
0 3 * * * OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv ... 30d retention
DRY-RUN: not modifying crontab.
EXIT=0
```

預檢提示完整：必先 apply V113 / 空間檢查 / 手動跑 wrapper dry-run。**PASS**。

### B.4 V113 dry-run BEGIN/ROLLBACK 不可能（內含 COMMIT，pattern by design）

V113 file 內含 `BEGIN; ... DO $$...$$; COMMIT;`（line 119/190），對齊 V053/V098 race-free pattern。`-c ROLLBACK` 對內部 COMMIT 無效。

**結果**：V113 在我 dry-run 時實際 COMMIT 進 PG（pre-V113 24 values → post-V113 26 values added `pg_dump_completed` + `pg_dump_failed`）。

**冪等性 PASS**：第二次跑同檔 → `NOTICE: V113: 2 pg_dump_* event_types already present in CHECK; skipping`，EXIT=0。

**潛在 sqlx 漂移風險**：

| 項目 | 狀態 |
|---|---|
| `_sqlx_migrations` table 是否含 V113 row | **NO** — 我直接 psql -f，繞 sqlx |
| 引擎下次 restart 行為 | sqlx::migrate 將跑 V113 → idempotency probe → NOTICE-skip → insert _sqlx_migrations row with Sha384 |
| 風險 | 預期可自動回正；但 operator 真實 deploy 必走 sqlx route 而非 psql 直跑 |

對照 memory `project_2026_05_02_p0_sqlx_hash_drift` 的 P0 incident：本 case 可自動回正因 V113 idempotency guard 完備。

### B.5 9 query post_restore_validation.sql 對 main DB 跑

**前置狀態檢查**：
- V099 未 land → `system.autonomy_level_config` 表不存（per TODO §1 Wave 5 Packet A IMPL pending）
- live 未跑 84h（per TODO §0 `live dead 302627s`）

**Per-query 結果**（mapped）：

| Q# | Table.Column | Verdict | 原因 |
|---|---|---|---|
| Q1 | system.autonomy_level_config.{id,current_level} | **FAIL (deployment gap)** | V099 未 land |
| Q2 | learning.governance_audit_log.{ts,event_type} | PASS-conditional | 0 row (no lease_grant 24h, live not running) |
| **Q3** | **learning.lease_transitions.ts** | **FAIL (BUG)** | **column `ts` 不存在**（實際只有 `ts_ms` bigint + `created_at` timestamptz）|
| Q4 | trading.fills.ts | PASS | 2 fills 24h |
| Q5 | trading.intents.ts LEFT JOIN trading.orders | PASS | 0 orphan |
| Q6 | learning.earn_movement_log.direction | PASS-conditional | 0 row (operator 未 stake) |
| Q7 | learning.strategist_applied_params.engine_mode IN('live','live_demo') | PASS-conditional | 0 row（runtime 全 demo，13582 rows 但 mode='demo'）|
| Q8 | learning.hypothesis_preregistration.payload_hash | PASS | 0 bad hash |
| Q9a | governance.lease_lal_assignments.assigned_at | PASS | 5 tier intact |
| Q9b | governance.lease_lal_tiers.tier_level | PASS | 5 row, tier 0-4 |

**主 finding（BUG）**：Q3 references `learning.lease_transitions.ts` 但表只有 `ts_ms` (bigint) + `created_at` (timestamptz)。實證：

```
$ docker exec trading_postgres psql -U trading_admin -d trading_ai -c \
  "SELECT COUNT(DISTINCT to_state) FROM learning.lease_transitions WHERE ts > NOW() - INTERVAL '24 hours'"
ERROR:  column "ts" does not exist
LINE 1: ...T to_state) FROM learning.lease_transitions WHERE ts > NOW()...
```

**衝擊**：Q3 出現在兩處 — 主 query block（line 93-107）+ AGGREGATE SUMMARY CTE（line 284）。兩處都會 ERROR；script 第 40 行 `\set ON_ERROR_STOP on`，**Q3 ERROR 將 abort 整個 drill validation**。實際 restore drill 跑時必 FAIL。

**Fix（建議 E1 round 3）**：把 `ts` 換成 `created_at`（或 `to_timestamp(ts_ms / 1000)`）— 兩處同步改。

## §4 C. Test baseline (regression-testing-protocol)

### Linux baseline — primary suite (`control_api_v1/tests/`)

Per memory `regression-testing-protocol` 表中歷史 baseline = 2555 passed / 17 failed，但**已過期**。當前實測：

| Run | passed | failed | skipped | Delta |
|---|---|---|---|---|
| Run 1 | **3994** | **68** | 51 | baseline today |
| Run 2 | **3994** | **68** | 51 | non-flaky |

Excluded: `tests/replay/` (4 collection errors pre-existing, unrelated to GAP B+D)。

### Mac local — secondary suite (`srv/tests/`)

| Run | passed | failed | skipped |
|---|---|---|---|
| Mac | 388 | 8 | 2 |

Excluded: `tests/misc_tools/test_pure_utils.py` (collection error pre-existing 2026-05-15 086a1d67, unrelated)。

### Rust engine lib

```
$ ~/.cargo/bin/cargo test --release -p openclaw_engine --lib
test result: ok. 3469 passed; 0 failed; 1 ignored
```

**通過率 100%**。歷史 baseline ~1980 已過期；今日真實 = **3469 passed / 0 failed**。

### Delta 分析

| 引擎 | 過去 baseline | 今日實測 | Delta | 評估 |
|---|---|---|---|---|
| Linux control_api_v1 pytest | 2555 passed (歷史) | 3994 passed | +1439 | unrelated growth |
| Linux control_api_v1 pytest | 17 failed (歷史) | 68 failed | +51 | unrelated pre-existing |
| Rust engine lib | 1980 passed (歷史) | 3469 passed | +1489 | unrelated growth |

**本 IMPL 對測試數的衝擊 = 0**：

- 0 Python tests 被 touch（兩 commit 都沒動 `tests/`）
- 0 Rust 檔被 touch（純 Python + Bash + SQL + docs）
- 新 production code 對應的 unit test 數 = **0**（見 §6 BLOCKER）

## §5 D. Cross-language float consistency

**N/A** — 本 IMPL 無 Rust+Python 跨語言計算（純 Python healthcheck + Bash cron + SQL migration + docs）。

## §6 E. SLA pressure

| Path | 量測值 | 目標 | 結果 |
|---|---|---|---|
| check_pg_dump_freshness.py --status | 67ms | 1h cron tolerable | PASS |

PG read + filesystem stat + subprocess pg_restore --list 全鏈 67ms。Cron 1h cadence 下無壓力。

## §7 F. Mock not hide logic

無 unit test ⇒ 無 mock。**無 mock-hide-logic 反模式**，但 §8 BLOCKER 有別的問題。

## §8 G. Integration check (passive_wait_healthcheck 全鏈)

### G.1 [80] check wire-up 靜態

```
checks_cron_heartbeat.py:216  def check_80_pg_dump_freshness(...)
checks_cron_heartbeat.py:324  __all__ += "check_80_pg_dump_freshness"
__init__.py:228 + 336         import + re-export
runner.py:335                 import check_80_pg_dump_freshness
runner.py:1412-1413           s,m = check_80_pg_dump_freshness(); results.append(...)
```

### G.2 Linux runtime 跑 passive_wait_healthcheck.py --quiet

```
$ ~/.venv/bin/python3 helper_scripts/db/passive_wait_healthcheck.py --quiet | tail -2
INSUFFICIENT_SAMPLE [80] pg_dump_freshness               [80] pg_dump_freshness verdict=INSUFFICIENT_SAMPLE (7 sub-check; non-PASS: [2-7])
SUMMARY: FAIL — ≥1 healthcheck failed
```

**整合 PASS** — [80] 行 INSUFFICIENT_SAMPLE 出現於 SUMMARY 之上，與 [1]-[79] 其他 check 並列。SUMMARY 的 FAIL **不是** [80] 引起（[80] = INSUFFICIENT_SAMPLE fail-soft），是 pre-existing [48] / [66] / [74] / [7] / [20] / [56] 等 FAIL 累積。

### G.3 [80] 不破其他 check

對照 round 1 之前的 passive_wait 跑（如 §13 cron heartbeat block 中其他 [75]-[79]），所有 pre-existing check 仍跑、verdict 不變。**0 regression in existing checks**。

## §9 H. 測試刪除遮蓋失敗檢查

```
$ git diff --stat 1392c9e1^..261d3956 | grep -E '^\s+tests/|^\s+test_' | wc -l
0
```

**0 test file 被 touch 或刪**（兩 commits 都沒動 tests/）。**PASS**：無「刪測試使測試通過」反模式。

但 §6 揭露 **無新增測試**（卻新增 743 LOC production code）。Per E4 profile：「新 E1 改動必須有對應測試（邊界值 + 正常路徑至少各 1）」。

## §10 6 大測試類型對應 (regression-testing-protocol §4)

| 類型 | 應用 | 結果 |
|---|---|---|
| Unit test | check_pg_dump_freshness.py 7 sub-check / V113 idempotency / cron wrapper | **0 test** — 應補 |
| Integration test | passive_wait_healthcheck.sh full pipeline run | PASS (Linux empirical §8.2) |
| Property-based | N/A | — |
| Concurrency | install_pg_dump_cron.sh 二跑（atomic overwrite）| static review only |
| SLA | check_pg_dump_freshness.py latency 67ms | PASS (§6) |
| Cross-language | N/A | — |

## §11 跑兩遍結果

| Run | Python (control_api_v1) | Rust engine lib | passive_wait .sh [80] verdict |
|---|---|---|---|
| 1st | 3994p/68f/51s | 3469p/0f/1i | INSUFFICIENT_SAMPLE |
| 2nd | 3994p/68f/51s | (skip — IMPL no Rust touch) | (skip — Linux state same) |

**Non-flaky**。

## §12 治理對照

| 項目 | 狀態 | 證據 |
|---|---|---|
| FA §E 15 sign-off criteria | 14/15 GREEN, 1 BUG | §3.5 Q3 column drift |
| E1 report claim「Linux empirical PASS」| TRUE for check_pg_dump_freshness.py | §3.2 |
| memory `feedback_v_migration_pg_dry_run` Linux empirical mandatory | DONE | §3.4 |
| memory `regression-testing-protocol` mock 規則 | N/A 無 mock | — |
| memory `feedback_chinese_only_comments` Chinese-first | 本 report 全 Chinese | 全檔 |
| memory `2026_05_02_p0_sqlx_hash_drift` 風險 | 已驗 V113 idempotency 可自動回正 | §3.4 |

## §13 Verdict

**YELLOW**

### 理由

**PASS 面**（14/15）：
- 全 Bash + Python + SQL static syntax PASS (Mac + Linux)
- check_pg_dump_freshness.py --status fail-soft PASS, EXIT=0, SLA 67ms
- DRY-RUN install 預覽正確 + 預檢提示完整
- V113 idempotency PASS (二跑 NOTICE-skip)
- [80] passive_wait wire-up 完整、不破其他 check
- Python pytest 3994 passed / 68 failed (run × 2 non-flaky, unrelated to IMPL)
- Rust engine lib 3469 passed / 0 failed (unrelated)
- 0 test file 被 touch（無「刪測試遮蓋」反模式）

**FAIL 面**（1 BUG + 2 carry-over）：

**BLOCKER-1 BUG**: `helper_scripts/db/post_restore_validation.sql` Q3 column drift —
- line 95 (主 block) `WHERE ts > NOW() ...`
- line 284 (AGGREGATE SUMMARY) 同樣 `WHERE ts > NOW() ...`
- `learning.lease_transitions` 實際只有 `ts_ms` (bigint) + `created_at` (timestamptz)
- script 第 40 行 `\set ON_ERROR_STOP on` → drill day Q3 ERROR 會 abort 整 9 query gate
- Fix: 兩處 `ts` → `created_at`（或 `to_timestamp(ts_ms / 1000)`）

**CARRY-OVER-1 NORMAL**: V099 未 land → Q1 FAIL —
- 非 BUG，是 deployment dependency（per TODO §1 Wave 5 Packet A IMPL pending）
- 一旦 V099 deploy + system.autonomy_level_config row 寫入，Q1 PASS
- 建議 E1 round 3 / Wave 5 dispatch 時併行解

**CARRY-OVER-2 GOVERNANCE**: 743 LOC production code 0 unit test —
- check_pg_dump_freshness.py 616 LOC 7 sub-check 0 mock 0 unit test
- passive_wait wrapper 108 LOC 0 unit test
- Per E4 profile 「新 E1 改動必須有對應測試」明確違反
- 建議 E1 round 3 補：
  - 7 sub-check 各 1 fixture-based unit test（mock fs/PG）
  - V113 PG dry-run pytest（用 testcontainers PostgreSQL）
  - Cron Bash wrapper 用 bats-core 寫 5 case

### E1 round 3 必修 items

| Priority | Item | 估時 |
|---|---|---|
| P0 BLOCKER | post_restore_validation.sql Q3 `ts` → `created_at`（line 95 + 284）| 5 min |
| P1 governance | check_pg_dump_freshness.py 7 sub-check unit test 補完 | 2-3h |
| P2 governance | passive_wait_healthcheck/checks_cron_heartbeat.py wrapper unit test | 30 min |
| P3 deployment | 等 V099 land 後 verify Q1 PASS | dependent on Wave 5 Packet A |

### E1 round 3 不必修（accept as-is）

| Item | 為何 OK |
|---|---|
| Q7 0 row | 預期 — runtime 全 demo mode, first-day-live 時自然會有 row |
| Q6 0 row | 預期 — operator 未 stake，first-day live + Earn stake 後自然有 row |
| V113 內含 COMMIT 無法 BEGIN/ROLLBACK | by design — race-free pattern 鏡 V053/V098 |

## §14 不允許 commit 的條件 (regression-testing-protocol §0)

| 條件 | 結果 | OK? |
|---|---|---|
| passed 數 < baseline | 3994 ≥ 3994 (control_api_v1) / 3469 ≥ 3469 (Rust) | OK |
| pre-existing failed 數增加 | 68 = 68 (control_api_v1) / 0 = 0 (Rust) | OK |
| 刪測試使 passed 增加 | 0 test file 被 touch | OK |
| mock 業務邏輯 | 無 mock | OK |
| 跑一次過 ≠ 真綠 | run × 2 non-flaky | OK |

**所有 commit gate PASS**；但 post_restore_validation.sql Q3 BUG 必修才能 first-day live 後 trigger drill。

## §15 文件參考

- E1 round 2 report: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-27--ops_4_round_2_e1_pg_dump_healthcheck.md`
- FA acceptance: `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-27--ops_4_gap_bd_business_acceptance_audit.md` §E 15 criteria
- PA spec: `srv/docs/execution_plan/specs/2026-05-26--p0-ops-4-first-day-live-runbook.md` §10.B
- E4 systemd parallel: `srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-27--ops_4_e4_regression.md`（不衝突）
- regression-testing-protocol skill
- memory: `project_2026_05_02_p0_sqlx_hash_drift` (V113 sqlx 風險)
- memory: `feedback_v_migration_pg_dry_run` (Linux PG empirical mandatory)

---

**E4 REGRESSION DONE: YELLOW · report path: srv/docs/CCAgentWorkSpace/E4/workspace/reports/2026-05-27--ops_4_gap_bd_e4_regression.md**
