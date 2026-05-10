# E1 — W6 V086 SQL skeleton 預寫

**日期**：2026-05-10
**性質**：W6-3c IMPL 預寫；NOT_COMMITTED · NOT_DEPLOYED · NOT_RUN
**前置**：
- PA W6-3b enum spec final `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_3b_enum_spec_final_pa_decision.md`
- MIT W6-3a close_tag distribution audit `srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-10--w6_3a_close_tag_distribution_audit.md`
- PA P2 雙前綴 RCA `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--p2_decision_features_double_prefix_bug_audit.md`
- schema_guard_template.sql + V083/V084 既有 pattern reference

---

## §1 任務摘要

預寫 V086 SQL migration skeleton：
- learning.decision_features 新增 reject_reason_code + close_reason_code TEXT column
- 12 reject + 14 close NOT VALID CHECK constraint enum
- One-shot in-migration backfill 9757 row
- trading.fills.strategy_name 17 row 雙前綴 normalize 上游清理
- Guard A/A2/A3/B/C 三層完整

PM sign-off 後 D+1 W6 V086 IMPL 直接收（修小細節 + Linux PG dry-run + commit），不需 E1 從零寫。

## §2 修改清單

| Path | LOC | Status |
|---|---|---|
| `srv/sql/migrations/V086__governance_reject_close_reason_code.sql` | 483 | NEW · NOT_COMMITTED · NOT_DEPLOYED · NOT_RUN |

無 既有檔修改。

## §3 結構（acceptance criteria 對照）

| Criterion | Status | 證據 |
|---|---|---|
| **(1) V086 SQL file land 在指定 path** | PASS | `srv/sql/migrations/V086__governance_reject_close_reason_code.sql` 483 LOC |
| **(2) idempotency check** | PASS | ALTER TABLE `IF NOT EXISTS` (line 188-189) · ADD CONSTRAINT 走 DO block + `pg_constraint` exists check (line 240, 269) · UPDATE 含 `WHERE reason_code IS NULL` filter (line 369) · trading.fills REPLACE 含 `WHERE LIKE 'risk_close:risk_close:%'` filter (line 391) |
| **(3) Guard A/B/C 完整** | PASS | Guard A (decision_features) line 105-126 · Guard A2 (trading.fills) line 134-156 · Guard A3 (risk_verdicts) line 162-183 · Guard B (column type) line 199-225 · Guard C (post-backfill) line 397-441 |
| **(4) 12 reject + 14 close enum hardcoded** | PASS | 12 reject enum line 248-262 · 14 close enum line 273-291 (grep verified count=12+14) |
| **(5) backfill SQL deterministic** | PASS | CASE WHEN evaluation order per PA §4.4: ATR unavailable 必先於 JS-demo / cost_gate_other (line 320-322) · 雙前綴必先於單前綴 (line 354-358) · bare-name exact 必先於 prefix regex (line 339-345) |
| **(6) NO actual run** | PASS | file 寫好 sit on disk, 不跑 psql (per task 邊界) |
| **(7) Sign-off report** | PASS | 本 report |

## §4 12 reject + 14 close enum 對照 PA W6-3b spec final

### Reject enum (12, 11 + reject_other catch-all)
| # | enum value | PA spec § alignment |
|---|---|---|
| 1 | `cost_gate_js_demo_negative_edge` | §2 row 1 |
| 2 | `cost_gate_atr_unavailable` | §2 row 2 (post-V082 0 row, pilot reserved per A3 拍板) |
| 3 | `cost_gate_other` | §2 row 3 |
| 4 | `duplicate_position` | §2 row 4 |
| 5 | `direction_conflict` | §2 row 5 |
| 6 | `position_count_limit` | §2 row 6 |
| 7 | `scanner_market_gate` | §2 row 7 |
| 8 | `scanner_opportunity_canary` | §2 row 8 |
| 9 | `drawdown_breach` | §2 row 9 |
| 10 | `symbol_blocklist` | §2 row 10 |
| 11 | `risk_gate_other` | §2 row 11 |
| 12 | `reject_other` (catch-all) | §2 row 12 (renamed `other_reject` → `reject_other` per 命名對稱) |

### Close enum (14, 13 + close_other catch-all)
| # | enum value | PA spec § alignment |
|---|---|---|
| 1 | `strategy_close_grid` | §3 row 1 |
| 2 | `strategy_close_ma` | §3 row 2 |
| 3 | `strategy_close_bb` | §3 row 3 |
| 4 | `strategy_close_funding_arb` | §3 row 4 (29 sub-reason 合一 per A4 拍板) |
| 5 | `strategy_close_regime_shift` | §3 row 5 (1 row pilot per A5 拍板) |
| 6 | `strategy_close_legacy_bare_name` | §3 row 6 (615 row, 5 策略不拆 per A1 拍板) |
| 7 | `risk_close_phys_lock_gate4_giveback` | §3 row 7 (含雙前綴 normalize per A2 拍板) |
| 8 | `risk_close_phys_lock_gate4_stale` | §3 row 8 |
| 9 | `risk_close_cost_edge` | §3 row 9 |
| 10 | `risk_close_fast_track` | §3 row 10 |
| 11 | `risk_close_trailing_stop` | §3 row 11 |
| 12 | `risk_close_dynamic_stop` | §3 row 12 |
| 13 | `ipc_close_all` | §3 row 13 |
| 14 | `close_other` (catch-all) | §3 row 14 (renamed `other_close` → `close_other` per 命名對稱) |

## §5 預期 backfill row count

per W6-3a + PA P2 RCA:
- learning.decision_features 9757 labeled row 全 backfill (互斥不變式: rejected_governance → reject_reason_code; 其他 → close_reason_code)
  - rejected_governance row: ~6361 (per W6-3a §1.1)
  - 其他 labeled row: ~3396
- trading.fills.strategy_name **17 row** 雙前綴 REPLACE
- learning.decision_features label_close_tag **16 row** 雙前綴 → 不修 raw 字串 (per PA P2 §4 Option A: 保留歷史 bug fingerprint)，只在新 close_reason_code enum 收 normalize 後值 `risk_close_phys_lock_gate4_giveback` (per CASE WHEN line 354-355)

## §6 治理對照

| 項目 | Status | 證據 |
|---|---|---|
| CLAUDE.md §七 SQL migration Guard A/B/C 強制 | PASS | 5 個 Guard block (A/A2/A3/B/C) |
| CLAUDE.md §七 idempotency 強制 | PASS | 全 ADD COLUMN/CONSTRAINT/UPDATE/REPLACE 含 IF NOT EXISTS / DO block guard / WHERE filter |
| CLAUDE.md §七 Linux PG dry-run mandatory | DEFERRED | D+1 W6-3c IMPL phase 必跑 Linux PG empirical query 9757 row backfill timing 驗 (per `feedback_v_migration_pg_dry_run`); Mac mock 不夠 |
| CLAUDE.md §七 注釋默認中文 | PASS | 新檔注釋默認中文 (per `feedback_chinese_only_comments` 2026-05-05); 有少數 inline 英文 (canonical name `text` / `bigint` 等技術詞 + 模板對齊 V083/V084 既有英文 docstring 風格) |
| CLAUDE.md §九 文件 800 行警告 | PASS | 483 LOC, 在 800 警戒線下 |
| 不擴大 PA spec 範圍 | PASS | 只對 PA spec §4 + P2 RCA §4 補充清單；無 順手優化 |
| 不修既有 V### migration | PASS | 純新建 V086 file |
| Guard B 對應 V083/V084 既有 type check pattern | PASS | line 199-225 對齊 V083 line 117-127 + V084 line 92-125 |

## §7 不確定之處 / D+1 IMPL 階段需 E2 review 補充

1. **constraint name 命名約定**：本 file 用 `chk_reject_reason_code_enum` / `chk_close_reason_code_enum`。需 E2 確認對齊 V083/V084 既有 pattern (V083 用 `fills_close_must_have_entry_context_id` 描述式) 還是新 `chk_*_enum` pattern 都 acceptable。
2. **backfill UPDATE 是否拆分 reject path / close path 兩階段**：當前單一 UPDATE 一次寫兩 column (互斥邏輯)；若 Linux PG dry-run 9757 row 實測 lock window > 90 sec，需考慮拆兩 UPDATE 縮短 lock。建議 D+1 IMPL 先實測再決。
3. **risk_verdicts JOIN**：當前 INNER JOIN (FROM trading.risk_verdicts rv WHERE df.context_id = rv.context_id)。若 rejected_governance row 對應的 risk_verdicts row 缺失 (不應發生但 edge case)，該 row 不會被 update → reject_reason_code IS NULL → Guard C 會 RAISE。建議 D+1 PG dry-run 預先 query 「rejected_governance row 數 vs JOIN 命中 row 數」確認 0 mismatch；若 mismatch 需改 LEFT JOIN + ELSE catch-all to `reject_other`。
4. **producer dual-write race window** (per PA §6 #3)：V086 land 與 producer dual-write code (Rust step_4_5_dispatch + step_6_risk_checks) deploy 不能差 >5 min；本 file 不含 producer 部分 (W6-3c IMPL phase Rust 工作)。E2 必驗 deployment runbook 含 atomic deploy step。

## §8 Operator 下一步

1. **PM 21:30 UTC sign-off**：審本 V086 SQL skeleton + 對照 PA W6-3b spec final + PA P2 RCA + W6-3a audit
2. **Sign-off PASS 後**：commit V086 file 進 main branch（**不 deploy**），D+1 W6 V086 IMPL phase E1 接收
3. **D+1 W6 V086 IMPL phase**：
   - E1 Linux PG dry-run V086 (跑兩次驗 idempotent + 9757 row backfill 實測 timing)
   - E1 補 producer dual-write Rust code (step_4_5_dispatch + step_6_risk_checks)
   - E2 review (Guard A/B/C 完整性 + backfill SQL CASE WHEN 順序 + Linux PG dry-run report + atomic deploy runbook)
   - E4 regression test
   - PM commit + deploy
4. **D+2 14:00 UTC**: 24h dual-write drift healthcheck PASS verification
5. **D+2 14:30 UTC**: ALTER TABLE ... VALIDATE CONSTRAINT 兩 enum constraint (lock window <30 sec on 9757+ row)

---

## §9 NOT_COMMITTED · NOT_DEPLOYED · NOT_RUN 標記

- **NOT_COMMITTED**: V086 file sit on disk, 未 `git add` 未 commit
- **NOT_DEPLOYED**: 未跑 `psql -f V086__*.sql`，無 DB schema 改動
- **NOT_RUN**: 無 `cargo test` / 無 `pytest` / 無任何 runtime exec
- **PM sign-off 條件**: 等 21:30 UTC HIGH-5 12h watch sign-off 窗口；PM 對照本 report + V086 file 內容做最後 verdict

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-10--w6_v086_sql_skeleton_prewrite.md）
