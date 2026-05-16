# TODO v36 Completion Cleanup Archive

Date: 2026-05-16
Role: PM
Scope: TODO.md active-queue cleanup only. No runtime, DB, auth, risk, strategy,
paper, demo, LiveDemo, or live mutation was performed by this cleanup.

## Cross-Validation Method

PM cross-checked completed TODO entries against:

- local git commits referenced by TODO (`git cat-file -e <sha>^{commit}`)
- PM / PA / E2 / E4 / BB reports under `docs/CCAgentWorkSpace/*/workspace/reports/`
- current TODO v35 top state showing runtime/code-bearing sync at `5f6f3edf`
- existing archive/report files for 2026-05-15 and 2026-05-16

All completion items moved out below had either a matching commit, matching
report, or an existing superseding active row. Items still active, blocked,
watch-only, or dependency-bearing were retained in TODO as compact active rows.

## Active Items Intentionally Kept in TODO

- `P0-EDGE-1`
- `P0-LG-1`, `P0-LG-2`, `P0-LG-3`
- `P0-OPS-1..4`
- `LG-1`, `LG-2`, `LG-3` implementation chain rows
- `W-F`, `W-G`, `W-AUDIT-4`, `W-AUDIT-8a`, `W-AUDIT-8b`, `W-AUDIT-8c`,
  `W-AUDIT-8e`, `W-AUDIT-8f`, `W-AUDIT-8g`, `W-AUDIT-8h`, `W-AUDIT-10`
- `EDGE-P2-3 Phase 1b` plus unresolved prereqs / follow-ups
- `P1-WAVE-3-5-LINUX-MIGRATION-BACKLOG`
- `P1-BBMF3-WIRE-1`
- WP-11 Phase 2 residual P2 work and WP-12 deferred state
- all P2 backlog rows that are not completed

## §0.0 Update Log Archived

The detailed 2026-05-15..16 update bullets were moved out of active TODO:

- W-AUDIT-3b runtime smoke completed 2026-05-15.
- A4-C spec v1.4 / W2 report CLI rebased to Stage 0R diagnostic output.
- `[55]` source-cleared by `P1-HEALTHCHECK-55-INVARIANT`.
- A4-C Step 5a and Step 5b Stage 0R remained GATE-RED.
- OI-confirmed 5m packet and feasibility probe remained non-promotional.
- `[67]` feature baseline readiness was restored by `P1-WA4B-INSERT-1`.
- `[27]` intent-freeze source/deploy/post-grace closure completed 2026-05-15.
- W-AUDIT-8a Phase C0 source/doc inventory closed.
- TODO v30 source-sync closed.
- A4-C RCA closed no-revive; `P1-A4C-REV-1` not opened.
- W-AUDIT-8b Funding Skew design approved only for read-only Stage 0R.
- v35 WP-13 leftover source/test/deploy closure completed at runtime/code-bearing head `5f6f3edf`.

Correction applied during v36 cleanup:

- Stale active wording that said W-AUDIT-8a C1 proof was still running was
  removed. The current fact is `FAIL_CONNECTION` at `2026-05-16T00:37:25Z`
  after `17055.2s/86400s`; the run saw 15 candidate messages and 0 subscribe
  failures but is not C1 proof-eligible.

## Completed Wave Rows Archived

The following wave rows were removed from the active roster because their
closure is no longer actionable in TODO:

- `W-A` Executor fake-live runtime smoke, DONE 2026-05-07
- `W-B` Runtime decision-spine lineage wiring, DONE 2026-05-08
- `W-C` MAG-082 Stage 2 evidence window, WINDOW_PASS 2026-05-11
- `W-D` MAG-083 / MAG-084, DONE 2026-05-11
- `W-E` OpenClaw read-only observability, DONE 2026-05-07
- `W-AUDIT-1` Docs sync + governance compliance, DONE 2026-05-09
- `W-AUDIT-2` Security IMPL, DONE 2026-05-09
- `W-AUDIT-3` ExecutorAgent fake-live, SOURCE/SMOKE CLOSED 2026-05-15
- `W-AUDIT-5a/5b` performance / structure / CI / portability, DONE 2026-05-15
- `W-AUDIT-6` strategy + quant promotion gate source/test closures
- `W-AUDIT-7` AI stack + GUI/UX ops closure, 2026-05-15
- `W-AUDIT-8d` A4-C BTC->Alt Lead-Lag, DONE + GATE-RED + RCA no-revive
- `W-AUDIT-9` Graduated Canary Foundation IMPL, DONE, with paper stage frozen

Dependency facts retained in active TODO:

- W-C / W-D closure does not unlock true-live.
- A4-C remains diagnostic-only and cannot be rerun without a materially new,
  preregistered predictive variable.
- Paper promotion remains blocked by AMD-2026-05-15-01.

## P0 / P1 Closed Rows Archived

Removed from active §10:

- `P0-AGENT-1..4`
- `P1-STABLE-ID-1`
- `P1-RCA-1`
- `P1-W-AUDIT-3b-SMOKE`
- `P1-LG-DESIGN`
- `P1-FILL-LINEAGE-DROP`
- `P1-FILL-LINEAGE-MONITOR`
- `P1-HEALTHCHECK-55-INVARIANT`
- `P1-INTENT-FREEZE-27`
- `P2-DUAL-RAIL-ORDER-ID`
- `P2-RUNTIME-SHADOW-SPLIT`
- `P1-STARTUP-BURST-MITIGATION`
- `P1-V083-HALT-SESSION-CTX`
- `P0-MIT-LABEL-CLOSE-TAG-1`
- `P0-DECISION-AUDIT-1..7`
- `P0-NEW-ISSUE-1`
- `P0-NEW-VULN-1..2`
- `P0-AUDIT-NEW-LG-X-05`
- `P0-V2-NEW-1-DONCHIAN-LEAK-BIAS`
- `P0-V2-NEW-2-STRATEGIST-CAP-NO-GATE`
- `P0-V2-NEW-3-DSR-PBO-EVIDENCE-CRON`
- `P0-V3-MIT-ROOT-CAUSE`
- `P0-V3-V079-NOT-APPLIED`
- `P0-V3-CRON-NOT-INSTALLED`
- `P0-V3-PA-SPEC-FIX`
- `P0-V3-ADR-0021-ARCH-04`
- `P0-V3-ENGINE-RESTART`

Dependency facts retained in active TODO:

- residual edge risk stays under `P0-EDGE-1`
- LG implementation gates stay under `LG-1/2/3` and `P0-LG-1/2/3`
- ops gates stay under `P0-OPS-1..4`

## W-AUDIT-4b Completed Row Archived

Removed:

- `P1-WA4B-INSERT-1`, DONE 2026-05-15, restored 646 active
  `observability.feature_baselines` rows across 19 symbols and 34 feature names.

Retained:

- `P1-WA4B-INSERT-2`
- `P1-WA4B-INSERT-3`
- `P1-WA4B-VIEW-1`
- `P1-WA4B-VIEW-2`
- `P1-WA4B-DROP-1`

## P1 Other Active Completed Rows Archived

Removed from §11.3:

- `P1-W6-5-ML-METRICS`
- `P1-CRON-ML-1`
- `P1-AUDIT-RUNTIME-3`
- `P1-AUDIT-PERF-5`
- `P1-AUDIT-AI-UX-7`
- `P1-FAKE-1` / `P1-OPENCLAW-3/6/7` / `P1-AGENT-OBS-1` /
  `P1-AGENT-RUNTIME-1` / `P1-DATA-4` / `P1-REPLAY-1/2`
- `P1-MA-KAMA-FALLBACK-GATE`, verified by E4 report
  `2026-05-15--kama_fallback_gate_e4_regression.md`
- `P1-MAKER-FILL-RATE-BASELINE`, closed by commit `b98706d5`
- `P1-EDGE-P2-3-PH1B-AMD-REVIEW`
- `P1-EDGE-P2-3-PH1B-AMD-V02-PATCH` / later spec+AMD patch chain
- `P0-EDGE-P2-3-PH1B-REJECT-COOLDOWN-SPLIT`, closed by `27f02a07`
  with E4 regression `8321b4b7` and E2 report
  `2026-05-16--bbmf3_retroactive_review.md`
- `P1-FILLS-MAKER-CLOSE-AUDIT-MIGRATION`
- `P1-EDGE-P2-3-PH1B-PORTFOLIO-EXPOSURE`
- `P1-EDGE-P2-3-PH1B-LINEAGE-GUARD`
- `P1-BYBIT-DICT-PH1B-UPDATE`

New retained follow-up created from E2/BB review evidence:

- `P1-BBMF3-WIRE-1`: Phase 1b main implementation must wire production
  `rejectReason` / maker-rejection events into strategy callbacks and
  `arm_close_cooldown`; the prereq split is verified but currently
  plumbing-only.

## EDGE-P2-3 Completed Prep Archived

Moved out of active §11.5:

- Wave 1 Track A1/A3/A4/E1/E3 closures
- Wave 1.5 spec v1.2 + AMD v0.3 closure
- Wave 2a V094 migration spec closure
- Wave 2b reject cooldown split closure
- Wave 2c-2 E4 regression closure
- Wave 2c-1 E2 retroactive review closure
- Wave 3a 4-agent short re-review closure
- Wave 1.5b spec v1.3 + AMD v0.4 closure
- Wave 3b Bybit dictionary 6-update closure
- completed 7-track prep table

Retained in active TODO:

- Wave 3.5 Linux V081/V091/V092/V093 backlog migration apply work
- 3-gate status
- Phase 1b implementation kickoff chain
- `P1-BBMF3-WIRE-1`

## 12-Agent Full System Audit Closure Archived

Moved out of active §11.6:

- WP-01 through WP-10 DONE entries
- WP-13 DONE entry
- Wave 1, Wave 2, Wave 3, and Wave 4 Phase 1 closure details
- Mac verification baselines already reflected in TODO status and PM report

Retained:

- WP-11 Phase 2 residuals as P2 backlog
- WP-12 ONNX deferred note

Primary reports:

- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--12-agent-audit-pm-signoff.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--v35_three_side_sync_rebuild.md`

## P2 Completed Rows Archived

Removed:

- `P2-V19-CYCLE`
- `P2-N2-1`
- `P2-N2-2`
- `P2-N2-3`
- `P2-N2-4`

Retained:

- new P2 follow-ups created by WP-07 and WP-11 / Wave 1 reviews
- P2 maintenance items that are not complete

## Cleanup Boundaries

This cleanup did not:

- remove any active P0 true-live blocker
- remove any pending Stage 0R / C1 / Phase 1b dependency
- mark any replay, demo, LiveDemo, or live gate as passed
- re-enable Paper promotion
- alter strategy/risk/config values
- run migrations or change runtime state
