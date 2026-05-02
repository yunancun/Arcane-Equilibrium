# E1 Workspace Report — AUDIT-2026-05-02-P1-1 Guard A/B Retrofit Round 2

**Date**: 2026-05-02
**Topic**: V028 v_required ARRAY 補 entry_context_id；補 .claude_reports/ 本機 review 報告；如實揭露 round 1 行數偏差
**Status**: Round 2 fix done · 待 E2 重審

## 對應 .claude_report
`srv/.claude_reports/20260502_124336_e1_audit_p1_1_guard_retrofit.md`（6 節中文，per CLAUDE.md §七）

## E2 round-1 RETURN findings 處置
| Finding | Severity | Fix |
|---|---|---|
| F-1 V028 v_required ARRAY 漏 entry_context_id（與 V033 不一致）| LOW-MED · Code consistency | V028:51 補 `'entry_context_id'`、RAISE hint「V003/V008/V015/V021」→「V003/V008/V015/V017/V021」、上方 prose 註解同步補 V017 |
| F-2 漏寫 .claude_reports/ | GOVERNANCE | 補 6 節中文報告 |
| F-3 round 1 self-report 行數偏差（claim 475 / actual 733）| LOW · Self-report drift | 報告 §2/§5 如實揭露 17 test case / 733 行 |

## 改動最小範圍（不擴張）
- **動**：V028 1 檔（v_required ARRAY 1 行 + RAISE hint 1 行 + prose 註解 1 處）
- **不動**：V030/V031/V032/V034、test_v028_v034_guards.sql、V028 業務邏輯 CREATE/ALTER

## 驗證
| Check | Result |
|---|---|
| `grep entry_context_id V028` | hit 1 處 (line 51) ✅ |
| `cargo test -p openclaw_engine --test migrations_test --release` | 5 passed / 0 failed ✅（wiring smoke；無 PG 自動跳過 destructive case）|
| `ls .claude_reports/*audit_p1_1*.md` | 1 file ✅ |
| `git diff --check sql/migrations/V028__*.sql` | 無空白問題 ✅ |
| `git status --short sql/` | 5 M（V028/V030/V031/V032/V034）+ 1 ??（test fixture），無新無關檔 ✅ |

## 不確定 / E4 必補
1. Mac 本機無 PG → idempotent 雙跑未實測；E4 必跑 Linux `psql -f V028 ; psql -f V028` 兩次 0 RAISE
2. cargo test 5 passed 是 wiring smoke 不是 SQL execute；E4 必跑 `OPENCLAW_TEST_PG=postgresql://... cargo test --test migrations_test --release` end-to-end
3. F-1 prose comment 一併改 V017 屬 consistency 加碼，若 E2 認為超出 F-1 嚴格範圍可單獨 revert 那 1 處

## Operator 下一步
- E2 重審 round 2 fix
- E4 跑 Linux 真實 PG（idempotent + end-to-end）
- PM 統一收 commit + push
- 無需 operator 親自動手（純 SQL guard，無 risk_config / live auth / 交易參數改動）
