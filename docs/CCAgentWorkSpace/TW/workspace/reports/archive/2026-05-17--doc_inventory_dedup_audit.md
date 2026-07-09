# TW Doc Inventory / Dedup Audit — 2026-04-01..2026-05-15

Role: TW(worker)  
Repo root: `/Users/ncyu/Projects/TradeBot/srv`  
Task shape: read-only documentation inventory / dedup audit  
Report date prefix: `2026-05-17--` per operator request  

## Scope And Constraints

FACT: This report inventories docs whose path contains a date in the fixed range `2026-04-01` through `2026-05-15`. It also rechecks known unresolved findings from prior TW audits against the current workspace state.

FACT: Only this report file was created. I did not move, rename, merge, archive, fix, deploy, restart, migrate, edit auth, edit live/demo/paper config, start trading, edit `TODO.md`, or update TW memory / docs indexes.

FACT: The cold baseline freeze notes local/source drift and unrelated dirty files. It also says PM/TODO tracking edits are allowed at line 82, but the operator prompt for this TW task is stricter, so this audit treats report creation as the only allowed mutation.

Evidence command / inspection method:

```bash
rg -n "Actual PM freeze timestamp|HEAD|dirty worktree|Report Naming Rules|Assumption|TODO" \
  docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-17--cold_audit_baseline_freeze.md

find docs -type f \( -name '*.md' -o -name '*.txt' \) \
  | perl -ne 'print if /2026-0[45]-[0-9]{2}/' \
  | perl -ne 'if (/(2026-0[45]-[0-9]{2})/){$d=$1; print if $d ge "2026-04-01" && $d le "2026-05-15"}' \
  | wc -l
```

Inventory result: `1184` dated docs/text files in the requested window.

## Severity Summary

P0: 0  
P1: 1  
P2: 4  
P3: 1  

There are no P0 findings.

Several prior TW 2026-05-08 / 2026-05-09 issues are now fixed or superseded by later docs cleanup: REF-20 / REF-21 / g_sr1 superseded file placement is not re-raised here because the 2026-05-28 cleanup moved those old versions into archive stubs and rewired active references.

---

## Finding TW-DOC-2026-05-17-01 — Operator Mirror Drift On PA Redesign

Label: FACT  
Severity: P1  
Affected path + line:
- `docs/CCAgentWorkSpace/Operator/2026-05-09--full_loss_architectural_root_cause_redesign.md:259`
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md:260`

Evidence command or inspection method:

```bash
diff -u \
  docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md \
  docs/CCAgentWorkSpace/Operator/2026-05-09--full_loss_architectural_root_cause_redesign.md \
  | sed -n '1,120p'
```

Impact: The Operator copy still says `liquidation_pulse` requires revival / a new WS handler before use, while the PA copy has a 2026-05-27 correction saying that claim is false and `liquidation_pulse` is active. A reader using the Operator brief as the action source could plan an unnecessary revival sprint or apply the wrong R-1 precondition.

Why this is real, not false positive: This is not just duplicate text. The two copies now diverge exactly at a corrected safety / architecture claim. `wc -l` also shows the two files are not identical (`482` vs `479` lines), and the diff shows the PA correction is absent from Operator.

Suggested fix direction: Do not move files as part of this audit. Plan: convert the Operator copy to a short index / brief that links to the PA canonical report and its current correction, or add the same correction block to Operator and then freeze future Operator copies as stubs only.

Fix owner role: TW + PM  
Verification owner role: R4

---

## Finding TW-DOC-2026-05-17-02 — Exact Operator Mirror Duplicates

Label: FACT  
Severity: P2  
Affected path + line:
- Representative: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--three_p0_fixes_design.md:1`
- Representative mirror: `docs/CCAgentWorkSpace/Operator/2026-04-26--three_p0_fixes_design.md:1`
- Full duplicate set: Appendix A, all listed files at line 1.

Evidence command or inspection method:

```bash
python3 - <<'PY'
from pathlib import Path
import hashlib, re
by = {}
for p in Path("docs").rglob("*"):
    if p.is_file() and p.suffix in {".md", ".txt"}:
        s = str(p)
        m = re.search(r"2026-0[45]-[0-9]{2}", s)
        if m and "2026-04-01" <= m.group(0) <= "2026-05-15":
            by.setdefault(hashlib.sha256(p.read_bytes()).hexdigest(), []).append(s)
pairs = [(h, items) for h, items in by.items() if len(items) > 1]
print("duplicate_hash_groups", len(pairs))
print("duplicate_files", sum(len(items) for _, items in pairs))
print("duplicate_redundant_files", sum(len(items)-1 for _, items in pairs))
print("operator_groups", sum(1 for _, items in pairs if any("/Operator/" in x for x in items)))
PY
```

Observed result: `56` duplicate hash groups, `112` duplicate files, `56` redundant files, and all groups include `docs/CCAgentWorkSpace/Operator/`.

Impact: The Operator folder carries many full-text mirrors instead of short briefs. This doubles inventory volume and creates drift risk; Finding 01 is the concrete example where a mirrored doc fell behind after the canonical PA copy was corrected.

Why this is real, not false positive: The detection is SHA-256 byte identity, not fuzzy similarity. These are exact content duplicates, not merely same-topic reports.

Suggested fix direction: Do not move files in this audit. Plan a mirror policy: keep role workspace reports canonical; replace Operator exact copies with short index stubs containing status, 1-paragraph summary, and canonical link. Preserve audit trail via path redirects or explicit "Operator brief mirrors canonical" headers.

Fix owner role: PM + TW  
Verification owner role: R4

---

## Finding TW-DOC-2026-05-17-03 — FundingArb V1/V2 Audit Docs Remain Active-Looking After Retired Closure

Label: FACT  
Severity: P2  
Affected path + line:
- `docs/audits/2026-04-16--g2_funding_arb_clean_edge.md:33`
- `docs/audits/2026-04-16--g2_funding_arb_clean_edge.md:35`
- `docs/audits/2026-04-17--g2_funding_arb_clean_edge_v2.md:35`
- `docs/audits/2026-04-17--g2_funding_arb_clean_edge_v2.md:37`
- Current governing decision: `docs/governance_dev/amendments/2026-05-26--AMD-2026-05-26-01-funding-arb-deprecation.md:30`

Evidence command or inspection method:

```bash
rg -n "NEGATIVE EDGE|建議：升 R-02|Demo .*funding_arb.active|Retired closed|AMD-2026-05-26-01|ARCHIVE|SUPERSEDED" \
  docs/audits/2026-04-16--g2_funding_arb_clean_edge.md \
  docs/audits/2026-04-17--g2_funding_arb_clean_edge_v2.md \
  docs/governance_dev/amendments/2026-05-26--AMD-2026-05-26-01-funding-arb-deprecation.md \
  docs/README.md
```

Impact: Both old audit files still read like active recommendations to re-evaluate or disable funding_arb, while the current AMD says the strategy is retired closed and the docs/spec cascade marked it retired. This creates stale-doc ambiguity during strategy roster or P0-EDGE triage.

Why this is real, not false positive: The old audit files lack a top-of-file `SUPERSEDED`, `RETIRED`, or archive pointer, and their recommendation language predates AMD-2026-05-26-01. The current README and AMD point to a later retired-closed state.

Suggested fix direction: Do not move files in this audit. Merge/archive plan: keep v2 as the canonical historical closeout, add a top header to v1/v2 pointing to AMD-2026-05-26-01, then archive or index both as historical evidence under funding_arb retirement lineage.

Fix owner role: TW + PA  
Verification owner role: R4 + QC

---

## Finding TW-DOC-2026-05-17-04 — Legacy Phase 0a..6 Execution Plan Still Indexed As Active

Label: FACT  
Severity: P2  
Affected path + line:
- `docs/execution_plan/README.md:22`
- `docs/execution_plan/README.md:30`
- `docs/execution_plan/phase_0a.md:1`
- `docs/execution_plan/phase_6.md:1`
- `docs/execution_plan/phase_6.md:4`

Evidence command or inspection method:

```bash
rg -n "Phase 0a|Phase 6|開始 Phase|HISTORICAL|SUPERSEDED|R-07|EvolutionEngine deprecated|4629" \
  docs/execution_plan/README.md \
  docs/execution_plan/phase_0a.md \
  docs/execution_plan/phase_6.md
```

Impact: `docs/execution_plan/README.md` still routes readers to phase files as if they are the execution entry for Phase 0a..6. The phase docs contain old W1/W19-W20 calendar language and stale acceptance surfaces (`EvolutionEngine deprecated`, `4629+ tests`) that no longer match current TODO/runtime evidence.

Why this is real, not false positive: The files do not carry `HISTORICAL` or `SUPERSEDED` headers in the inspected lines, and the README wording says "開始 Phase ..." rather than "historical baseline". Current active state is explicitly routed through `TODO.md` and newer sprint/spec docs.

Suggested fix direction: Do not move files in this audit. Plan: add historical headers and a single active-successor pointer, or move the whole phase_0a..6 packet into archive with a README stub. Keep any still-useful schema history as lineage only.

Fix owner role: PA + TW  
Verification owner role: R4

---

## Finding TW-DOC-2026-05-17-05 — 2026-04-18 Worklog Fragmentation And Naming Conflict

Label: FACT  
Severity: P2  
Affected path + line:
- `docs/README.md:878`
- `docs/worklogs/2026-04-18--dual_track_exit_design.md:1`
- `docs/worklogs/2026-04-18-1--dual_track_exit_feasibility.md:1`
- `docs/worklogs/2026-04-18-2--exit_features_table_design.md:1`
- `docs/worklogs/2026-04-18--live_gate_binding_1_implementation.md:1`
- `docs/worklogs/2026-04-18--live_gate_fallback_1_implementation.md:1`
- `docs/worklogs/2026-04-18--session_progress_p06_permanent_fix.md:1`

Evidence command or inspection method:

```bash
find docs/worklogs -maxdepth 1 -type f -name '2026-04-18*.md' | sort
rg -n "daily_summary 為當日權威|2026-04-18--daily_summary|2026-04-18-1--|2026-04-18-2--" \
  docs/README.md docs/worklogs
```

Impact: README states top-level worklogs use `daily_summary` as the day's authority, but there is no `2026-04-18--daily_summary.md`. Instead, six same-day fragments exist, and two use the nonstandard date prefix form `2026-04-18-1--` / `2026-04-18-2--`. This makes the day hard to consume and breaks the normal `YYYY-MM-DD--topic.md` naming pattern.

Why this is real, not false positive: The `find` command shows six 2026-04-18 top-level worklogs and no daily summary file. Later docs reference these fragments directly, so they are not orphaned; the issue is missing merge/index structure and naming consistency.

Suggested fix direction: Do not move files in this audit. Plan: create a `2026-04-18--daily_summary.md` or `_INDEX` closeout that links the six fragments in reading order, then mark the `-1--` / `-2--` names as legacy aliases in the index. Future cleanup can archive fragments after redirect coverage is verified.

Fix owner role: TW  
Verification owner role: R4

---

## Finding TW-DOC-2026-05-17-06 — E5 2026-04-12 Assessment/Final Pair Still Unmerged

Label: FACT  
Severity: P3  
Affected path + line:
- `docs/CCAgentWorkSpace/E5/2026-04-12--optimization_assessment_report.md:1`
- `docs/CCAgentWorkSpace/E5/2026-04-12--e5_optimization_final_report.md:1`
- `docs/CCAgentWorkSpace/E5/2026-04-12--e5_optimization_final_report.md:11`
- `docs/CCAgentWorkSpace/E5/memory.md:51`

Evidence command or inspection method:

```bash
wc -l \
  docs/CCAgentWorkSpace/E5/2026-04-12--e5_optimization_final_report.md \
  docs/CCAgentWorkSpace/E5/2026-04-12--optimization_assessment_report.md

rg -n "optimization_assessment_report|e5_optimization_final_report|Verification correction|原報告存在多項失真" \
  docs/CCAgentWorkSpace/E5/2026-04-12--e5_optimization_final_report.md \
  docs/CCAgentWorkSpace/E5/2026-04-12--optimization_assessment_report.md \
  docs/CCAgentWorkSpace/E5/memory.md \
  docs/README.md
```

Impact: Two same-day E5 root-level reports remain side by side. The final report contains a verification correction stating the original report had multiple false claims, while E5 memory indexes only the final report. The assessment report can still be found as an unmarked standalone doc.

Why this is real, not false positive: This was called out by prior TW audit and remains true in current state: the final report is 159 lines, the assessment is 380 lines, and there is no `SUPERSEDED` / merge pointer on the assessment in the inspected evidence.

Suggested fix direction: Do not move files in this audit. Plan: add a top header to `optimization_assessment_report.md` pointing to the corrected final report, or merge both into a single historical closeout and leave a redirect stub.

Fix owner role: E5 + TW  
Verification owner role: R4

---

## Appendix A — Exact Duplicate Operator Mirror Groups

Each row is one SHA-256 identical duplicate group from the 2026-04-01..2026-05-15 path-date inventory. All affected files are line 1 for purposes of duplicate detection.

| Duplicate group |
|---|
| `docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-08--bybit_api_compatibility_audit.md` / `docs/CCAgentWorkSpace/Operator/2026-05-08--BB_bybit_api_compatibility_audit.md` |
| `docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-09--bybit_compatibility_verification_v2.md` / `docs/CCAgentWorkSpace/Operator/2026-05-09--bb_v2_verification_M5_critical_blockers.md` |
| `docs/CCAgentWorkSpace/E3/workspace/reports/2026-05-08--full_chain_security_audit.md` / `docs/CCAgentWorkSpace/Operator/2026-05-08--full_chain_security_audit.md` |
| `docs/CCAgentWorkSpace/E3/workspace/reports/2026-05-09--security_verification_v3.md` / `docs/CCAgentWorkSpace/Operator/2026-05-09--e3_security_verification_v3.md` |
| `docs/CCAgentWorkSpace/E5/workspace/reports/2026-05-08--full_chain_optimization_audit.md` / `docs/CCAgentWorkSpace/Operator/2026-05-08--e5_full_chain_optimization_audit.md` |
| `docs/CCAgentWorkSpace/Operator/2026-05-09--mit_db_ml_verification_v2.md` / `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-09--db_ml_verification_v2.md` |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-01--pa_technical_review.md` / `docs/CCAgentWorkSpace/Operator/2026-04-01--pa_review.md` |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--edge_p1b_7dim_bind_rfc.md` / `docs/CCAgentWorkSpace/Operator/2026-04-26--edge_p1b_7dim_bind_rfc.md` |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--edge_p2_flip_sop_rfc.md` / `docs/CCAgentWorkSpace/Operator/2026-04-26--edge_p2_flip_sop_rfc.md` |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--g2_03_option_b_rfc.md` / `docs/CCAgentWorkSpace/Operator/2026-04-26--g2_03_option_b_rfc.md` |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--g2_06_bb_breakout_disposal_rfc.md` / `docs/CCAgentWorkSpace/Operator/2026-04-26--g2_06_bb_breakout_disposal_rfc.md` |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--strkusdt_dust_spiral_rca.md` / `docs/CCAgentWorkSpace/Operator/2026-04-26--strkusdt_dust_spiral_rca.md` |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--three_p0_fixes_design.md` / `docs/CCAgentWorkSpace/Operator/2026-04-26--three_p0_fixes_design.md` |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g3_08_phase4_5agent_design_rfc.md` / `docs/CCAgentWorkSpace/Operator/2026-04-27--g3_08_phase4_5agent_design_rfc.md` |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-27--g8_01_cognitive_e2e_design.md` / `docs/CCAgentWorkSpace/Operator/2026-04-27--g8_01_cognitive_e2e_design.md` |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-28--strategist_singleton_pollution_investigation.md` / `docs/CCAgentWorkSpace/Operator/2026-04-28--strategist_singleton_pollution_investigation.md` |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-29--strategy_name_attribution_cleanup_design.md` / `docs/CCAgentWorkSpace/Operator/2026-04-29--strategy_name_attribution_cleanup_design.md` |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--lg5_live_candidate_eval_contract_rfc.md` / `docs/CCAgentWorkSpace/Operator/2026-05-02--lg5_live_candidate_eval_contract_rfc.md` |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--lg5_w3_fup2_fix2_r_meta_window_3d_amendment_rfc.md` / `docs/CCAgentWorkSpace/Operator/2026-05-02--lg5_w3_fup2_fix2_r_meta_window_3d_amendment_rfc.md` |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-02--step2_cold_audit_4day_window.md` / `docs/CCAgentWorkSpace/Operator/2026-05-02--pa_step2_cold_audit_4day_window.md` |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-05--ref20_sprint_b_task_dag.md` / `docs/CCAgentWorkSpace/Operator/2026-05-05--ref20_sprint_b_task_dag.md` |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-08--full_audit_pa_fix_plan.md` / `docs/CCAgentWorkSpace/Operator/2026-05-08--full_audit_pa_fix_plan.md` |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--AMD-2026-05-09-03-graduated-canary-design.md` / `docs/CCAgentWorkSpace/Operator/2026-05-09--AMD-2026-05-09-03-graduated-canary-design.md` |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--todo_qctodo_merge_analysis.md` / `docs/CCAgentWorkSpace/Operator/2026-05-09--todo_qctodo_merge_analysis.md` |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--track_a_dispatch_plan.md` / `docs/CCAgentWorkSpace/Operator/2026-05-09--track_a_dispatch_plan.md` |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--a4c_btc_alt_lead_lag_spec.md` / `docs/CCAgentWorkSpace/Operator/2026-05-10--a4c_btc_alt_lead_lag_spec.md` |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--governance_4docs_invariant17_closure.md` / `docs/CCAgentWorkSpace/Operator/2026-05-10--pa_governance_4docs_invariant17_closure.md` |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_1_rfc_pa_signoff_verdict.md` / `docs/CCAgentWorkSpace/Operator/2026-05-10--w6_1_rfc_pa_signoff_verdict.md` |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--lg_3_spec_v1.md` / `docs/CCAgentWorkSpace/Operator/2026-05-11--lg_3_spec_v1.md` |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p0_22h08_deploy_edge_regression_rca.md` / `docs/CCAgentWorkSpace/Operator/2026-05-11--p0_22h08_deploy_edge_regression_rca.md` |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p1_strategist_params_persist_ma_crossover_rca.md` / `docs/CCAgentWorkSpace/Operator/2026-05-11--p1_strategist_params_persist_ma_crossover_rca.md` |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p1_v083_ipc_close_fix_design.md` / `docs/CCAgentWorkSpace/Operator/2026-05-11--p1_v083_ipc_close_fix_design.md` |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--f_fa_3_w_c_caveat_2_guard_tests_design.md` / `docs/CCAgentWorkSpace/Operator/2026-05-15--f_fa_3_w_c_caveat_2_guard_tests_design.md` |
| `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--v094_schema_migration_spec_pa_verdict.md` / `docs/CCAgentWorkSpace/Operator/2026-05-15--v094_schema_migration_spec_pa_verdict.md` |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-01--pm_execution_plan.md` / `docs/CCAgentWorkSpace/Operator/2026-04-01--pm_execution_plan.md` |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--a_f_final_sync_redeploy_status.md` / `docs/CCAgentWorkSpace/Operator/2026-04-29--a_f_final_sync_redeploy_status.md` |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_a_e_gap_reassessment.md` / `docs/CCAgentWorkSpace/Operator/2026-04-29--batch_a_e_gap_reassessment.md` |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_a_f_release_gate_reverification.md` / `docs/CCAgentWorkSpace/Operator/2026-04-29--batch_a_f_release_gate_reverification.md` |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_d_risk_config_fail_closed_signoff.md` / `docs/CCAgentWorkSpace/Operator/2026-04-29--batch_d_risk_config_fail_closed_signoff.md` |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_e_operator_runtime_ownership_signoff.md` / `docs/CCAgentWorkSpace/Operator/2026-04-29--batch_e_operator_runtime_ownership_signoff.md` |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-04-29--batch_f_ml_agent_autonomy_signoff.md` / `docs/CCAgentWorkSpace/Operator/2026-04-29--batch_f_ml_agent_autonomy_signoff.md` |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-06--agenttodo_m0_contract_freeze_integration.md` / `docs/CCAgentWorkSpace/Operator/2026-05-06--agenttodo_m0_contract_freeze_integration.md` |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-06--agenttodo_m0_doc_sync.md` / `docs/CCAgentWorkSpace/Operator/2026-05-06--agenttodo_m0_doc_sync.md` |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-06--arcane_equilibrium_gui_brand_cleanup.md` / `docs/CCAgentWorkSpace/Operator/2026-05-06--arcane_equilibrium_gui_brand_cleanup.md` |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-06--arcane_equilibrium_soft_rename.md` / `docs/CCAgentWorkSpace/Operator/2026-05-06--arcane_equilibrium_soft_rename.md` |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-06--ref21_v1_3_p0_ref21_4_pg_dry_run.md` / `docs/CCAgentWorkSpace/Operator/2026-05-06--ref21_v1_3_p0_ref21_4_pg_dry_run.md` |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-07--agenttodo_mag061_execution_plan_generation.md` / `docs/CCAgentWorkSpace/Operator/2026-05-07--agenttodo_mag061_execution_plan_generation.md` |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-07--agenttodo_mag062_execution_plan_lease_binding.md` / `docs/CCAgentWorkSpace/Operator/2026-05-07--agenttodo_mag062_execution_plan_lease_binding.md` |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-07--agenttodo_mag063_execution_report_quality_metrics.md` / `docs/CCAgentWorkSpace/Operator/2026-05-07--agenttodo_mag063_execution_report_quality_metrics.md` |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-09--f08_ml_cron_scope_correction.md` / `docs/CCAgentWorkSpace/Operator/2026-05-09--f08_ml_cron_scope_correction.md` |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-09--keep_auth_missing_auth_rca.md` / `docs/CCAgentWorkSpace/Operator/2026-05-09--keep_auth_missing_auth_rca.md` |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-09--new_vuln_3_4_cookie_phase4.md` / `docs/CCAgentWorkSpace/Operator/2026-05-09--new_vuln_3_4_cookie_phase4.md` |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-09--openconfirmmodal_a11y.md` / `docs/CCAgentWorkSpace/Operator/2026-05-09--openconfirmmodal_a11y.md` |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-09--three_blockers_runtime_closure.md` / `docs/CCAgentWorkSpace/Operator/2026-05-09--three_blockers_runtime_closure.md` |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-09--w_audit_3_partial_f15_f17_sm05.md` / `docs/CCAgentWorkSpace/Operator/2026-05-09--w_audit_3_partial_f15_f17_sm05.md` |
| `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-09--w_audit_5_f12_true_runner_split.md` / `docs/CCAgentWorkSpace/Operator/2026-05-09--w_audit_5_f12_true_runner_split.md` |

