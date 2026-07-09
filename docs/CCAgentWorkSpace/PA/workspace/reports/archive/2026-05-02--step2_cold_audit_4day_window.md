# PA Step 2 Cold Audit — 2026-04-28 → 2026-05-01 codex window

Source-of-truth report: `/Users/ncyu/Projects/TradeBot/srv/.claude_reports/20260502_134432_pa_step2_audit.md`

## Summary

162 commits / 581 files / +64k LOC reviewed. **0 P1 / 1 P2 / 4 P3.** No stabilization wave needed. Continue PRE-LIVE-3 edge observation track.

## Findings

| ID | Sev | Component |
|---|---|---|
| LOC-GOV-1 | P2 | commands.rs (1343) + scanner/scorer.rs (1437) breach §九 1200 hard cap (pre-window baselines were within limit) |
| DRY-1 | P3 | commands.rs `is_legacy_close_tag` duplicated lines 203/576 (854cae1) |
| SCANNER-PAPER-CMD-1 | P3 (pre-existing) | scanner queries paper_cmd_tx for open positions; PAPER-DISABLE-1 makes oneshot timeout → empty set |
| SCRIPT-PROC-1 | P3 | helper_scripts/restart_all.sh + 3 sibling use Linux `/proc/<pid>/cwd` (5db4e29); Mac silently degrades |
| TEST-WATCHER-SLOT-1 | P3 | live_auth_watcher_tests.rs has no end-to-end slot write/clear assertion |

## Verified-real wirings (no orphan/dead code found)

- LIVE-AUTH-WATCHER slot pattern: full chain wired (watcher teardown clear → spawner closure write → fan-out per-tick read → IPC live_snapshot try_read → position_reconciler closure provider → strategist_scheduler with_promote_cmd_slot)
- close_sizing: 3 close paths in commands.rs + 1 fast-track partial reduce path
- scanner_snapshots: producer (runner.rs:278) → collector (trading_writer.rs:1025) → writer (flush_scanner_snapshots line 743)
- STRATEGY-WIRING-SPLIT: module attribute re-export in strategy_wiring.py:563/657-659
- Schema v2 authorization: Rust + Python signer aligned on `version|tier|...|approved_system_mode|env_allowed_csv` payload format

## Architecture posture verdict

**Healthy.** Audit window net-positive: tests +16, hard boundaries tightened (live REST close fallback removed, schema v2), Rust SSOT held, 16 root principles intact.

## PM next dispatch (priority order)

1. COMMANDS-RS-LOC-SPLIT P2 (resolves LOC-GOV-1 + DRY-1 in one wave) — PA→E1→E2→E4
2. SCANNER-SCORER-LOC-SPLIT P2 — PA+QC design → E1→E2→E4
3. SCRIPT-PROC-1 P3 — E1→E2→E4 (Mac+Linux smoke)
4. TEST-WATCHER-SLOT-1 P3 — E1→E4
5. SCANNER-PAPER-CMD-1 P3 (observe-first) — MIT add 7d healthcheck before fix
