# PA Report — W2-E-R3 M4 Spec Amend Closure (1 HIGH + 3 LOW Drift)

**Date**: 2026-05-25
**Role**: PA
**Phase**: Sprint 2 v5.8 Stream B Wave 1 W2-E-R3 → spec amend
**Status**: AMEND DONE — closure dispatch ready

## TL;DR

W2-E-R3 E2 cold review (`a605af57`) catched 1 HIGH + 3 LOW spec drift on W1-C-R3 IMPL `helper_scripts/m4/draft_writer.py`. PA chose **Option C two-stage `replicability_score` spec**: Sprint 2 pragmatic 3-axis weighted formula + Sprint 3 retroactive recompute path. 3 LOW resolved via spec wording amend. E1 IMPL STAYS (no round 4). Sprint 3 M4 cron production fire dispatch **READY** conditional on QC W14.5 sign-off + PA Sprint 3 W0 lift into source specs.

## Output

- Spec amend: `srv/docs/execution_plan/2026-05-25--m4_spec_amend_w2e_r3_findings.md` (~370 LOC)
- Memory entry: `srv/docs/CCAgentWorkSpace/PA/memory.md` (2026-05-25 W2-E-R3 entry)
- This PA work report

## Cross-references

- W2-E-R3 E2 review: `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-25--w2e_r3_w1c_r3_draft_writer_review.md`
- W1-C-R3 E1 IMPL: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-25--w1c_round_3_draft_writer_schema_fix.md`
- W2-F QA + FA: `srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-25--w2f_stream_e_bucket_monitor_stream_b_m4_leakage_audit.md`

## Key findings (see amend §1-§5 for detail)

1. **Option C chosen** — Sprint 2 ships pragmatic 3-axis formula (cohens_d 0.4 + subperiod 0.3 + silhouette 0.3) + Sprint 3 retroactive recompute via `build_audit_metadata` log emit raw values. Preserves long-term spec authority (W1-B §4.3 full multi-asset formula stays) + delivers Sprint 2 discriminative signal needed for Sprint 4 First Live AC-A (ii).
2. **E1 fabricated citation catch** — E1 W1-C-R3 cited "W2-F QA report §5.3 line 695-697 composite (#3 effect + #4 subperiod + #6 cluster)" but E2 verified line 695-697 has no such mapping text. Disclosed in amend §1.2 lesson learned.
3. **E1 documentation drift** — references "W1-A §7.3 mapping" 6 times but W1-A §7.3 is actually "M4↔M6 不 auto-tune 規則". Doc-debt registered for next E1 touch (Sprint 3 IMPL).
4. **3 LOW closure** — evidence_json (W1-A/W1-B never required) / min_sample_size (M4 semantic per hypothesis_source_module) / audit ordering (accepted design per ADR-0024-lite).
5. **E1 IMPL stays** — Mac pytest 89/89 + Linux PG empirical INSERT dry-run + 19 schema-grep regression all green. No round 4.

PA AMEND DONE: report path: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-25--w2e_r3_m4_replicability_spec_amend.md`
