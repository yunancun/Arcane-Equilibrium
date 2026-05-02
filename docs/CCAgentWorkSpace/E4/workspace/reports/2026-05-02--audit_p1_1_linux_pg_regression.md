# E4 Linux PG End-to-End Regression Report — AUDIT-2026-05-02-P1-1

- **Date**: 2026-05-02 12:54 CEST
- **Scope**: V028 / V030 / V031 / V032 / V034 SQL migration retrofit + fixture `test_v028_v034_guards.sql`
- **Verdict**: **BLOCKED** (zero Step executed)
- **Source mirror**: `.claude_reports/20260502_125420_e4_audit_p1_1_linux_regression.md` (full 6-section)

## Summary table

| Step | Description | Status | Notes |
|---|---|---|---|
| 1 | Sync Linux working tree | NOT RUN | Linux clean main `4749e0c`, retrofit absent |
| 2 | Apply migrations to trading_ai_test | NOT RUN | depends on Step 1 |
| 3 | Fixture 17 cases all green | NOT RUN | fixture doesn't exist on Linux |
| 4 | Idempotency double-run × 5 files | NOT RUN | depends on Step 1 + 2 |
| 5 | Rust integration test (DESTRUCTIVE=1) | NOT RUN | needs PM-provided OPENCLAW_TEST_PG |
| 6 | Production audit_migrations.py | NOT RUN | depends on Step 2 |
| 7 | Healthcheck spot check | NOT RUN | gated until Step 1-6 complete |

## BLOCKED conditions

### B1 — Linux working tree missing retrofit
```
$ ssh trade-core "cd ~/BybitOpenClaw/srv && git status && git log --oneline -3"
clean main · 4749e0c Document eaf0c7e runtime redeploy

$ ssh trade-core "ls ~/BybitOpenClaw/srv/sql/migrations/tests/test_v028_v034_guards.sql"
no such file
```

Mac working tree retrofit complete (6 files, 1850 LOC, 51 guard markers, 46 fixture markers aligning 17 cases) but uncommitted. PM must commit + push, then `ssh trade-core "git pull --ff-only"`.

### B2 — Linux PG `trading_ai_test` credentials unknown
```
$ ssh trade-core "source <env> && psql -h 127.0.0.1 -U trading_admin -d trading_ai"
FATAL: password authentication failed for user "trading_admin"
```

`settings/environment_files/basic_system_services.env` lacks `POSTGRES_HOST`; fallback 127.0.0.1 + sourced password fails. `audit_migrations.py:280` uses identical pattern. Production runtime likely uses docker / pgpass / IPC socket. Per task SOP "如不確定，stop and ask PM，不要自己猜路徑" — not guessing.

## What PM needs to deliver

**A**: `git add` 6 retrofit files only (not entire working tree) → `git commit -m ...` → `git push` → `ssh trade-core "git pull --ff-only origin main"`

**B**: Confirm correct `OPENCLAW_TEST_PG=postgresql://...trading_ai_test` connection string (or instruction "run X to obtain it"). Must be `trading_ai_test` (not `trading_ai`) because Step 5 uses `OPENCLAW_TEST_PG_DESTRUCTIVE=1` reset.

## E4 restart playbook

7 ssh trade-core commands ready at `.claude_reports/20260502_125420_e4_audit_p1_1_linux_regression.md` § 6. Estimated runtime ~10 minutes once both BLOCKERs cleared.

## Anti-patterns avoided

- Did NOT commit + push entire working tree (contains audit memory + reports needing PM Sign-off)
- Did NOT `git pull / merge / rebase` Linux side (CC禁 these 3 ops per CLAUDE.md §七)
- Did NOT guess PG connection string (task explicit: "stop and ask PM")
- Did NOT modify retrofit fixture / migration to "make it pass" (E1's responsibility, not E4)
- Did NOT proceed with degraded validation — BLOCKED report immediately per `feedback_working_principles.md` 原則 4
