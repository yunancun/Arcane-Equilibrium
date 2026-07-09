# TW Doc Inventory / Dedup Audit (RE-RUN) — 2026-04-01..2026-05-15

Role: TW(worker)
Repo root: `/Users/ncyu/Projects/TradeBot/srv` (canonical, only repo root)
Task shape: cold, adversarial, READ-ONLY documentation inventory / dedup audit (Phase 1 of PM multi-agent cold audit)
Campaign label: "2026-05-17" · actual run date: 2026-05-30
Baseline freeze: commit `187704f6`, branch `main`; only worktree change ` M TODO.md` (operator WIP, untouched).
Prior closed run: label 2026-05-17 (run ~2026-05-29), TODO v84 DEPLOYED. Closure archive: `docs/archive/2026-05-29--cold_audit_p1_p2_p3_closure_archive.md`. Prior TW report: `docs/CCAgentWorkSpace/TW/workspace/reports/2026-05-17--doc_inventory_dedup_audit.md`.

---

## 0. Run Integrity / Evidence-Method Disclosure (FAIL LOUD)

ASSUMPTION/FACT: This TW sub-agent runtime has **no Bash tool**. The shell commands cited in my prior 2026-05-17 report (`find | perl`, `python3 hashlib`, `diff -u`, `wc -l`) could **not be re-executed** this run. Evidence this run is from `Read` / `Grep` / `Glob` only; SHA-256 / line-count / cross-file diff numbers are carried forward, not re-measured.

FACT: This run suffered **sustained intermittent tool degradation** — many `Read`/`Grep` calls returned empty/no-match on first attempt and content on retry (the closure archive itself read empty ~6 times, then loaded fully). `docs/worklogs/*` glob timed out repeatedly. Every claim below is tagged by how it was verified:

- **FRESH-VERIFIED** = a tool returned the confirming content/match THIS run.
- **CARRIED-FORWARD** = rests on prior-report evidence; current-state confirmatory read not completed this run.

I did not move, rename, merge, archive, fix, deploy, restart, migrate, edit auth/config, start trading, edit `TODO.md`, or update TW memory / indexes. Only this report file was written.

---

## 1. Prior-Run Closure Cross-Check (the decisive new evidence)

FACT (FRESH-VERIFIED, full read of `docs/archive/2026-05-29--cold_audit_p1_p2_p3_closure_archive.md`): The 2026-05-29 closure is the prior cold-audit (PA validated P0=0 / P1=17 / P2=17 / P3=7). It overlaps several of my prior TW findings:

- **P1-15** (commit `7909ca3d` + v83, R4 APPROVE): "SPECIFICATION_REGISTER ADR-0036..0041 死路徑修正（0 missing）；**Operator-mirror cmp=0**". This directly touches my prior TW-DOC-2026-05-17-02 (Operator mirror duplicates). Interpretation: the closure's "Operator-mirror cmp=0" appears to be a SPECIFICATION_REGISTER-scoped mirror-consistency check, NOT a removal of the 56 CCAgentWorkSpace `Operator/` byte-duplicates (those files are still present — §3).
- **P2-04** (`7909ca3d`): `bybit_api_reference` aligned to source. Unrelated to my findings.
- **P2-16/P2-17** (`7909ca3d`): CLAUDE/README Bybit-only wording + `docs/README` dead M13/V116 links repointed to archive + TODO archive entries. This is the same index-hygiene lane as my prior audits; treat as closed there.

INFERENCE: The closure focused on code/security/evidence-gate truthfulness. It did **not** target the CCAgentWorkSpace Operator-mirror duplication, the funding_arb audit-file staleness, the Phase 0a..6 packet, or the 2026-04-18 worklog fragmentation. So those prior TW items are NOT covered by the 2026-05-29 closure and remain open for this re-run.

---

## 2. Severity Summary (this run)

- P0: 0
- P1: 0  (the prior P1 mirror-drift is **downgraded to P2** this run — see §4.1 honesty note)
- P2: 4
- P3: 1

No P0. No finding this run is confirmed to actively mislead a live/safety decision (the one prior P1 candidate could not be re-confirmed as a live divergence — disclosed below).

---

## 3. Inventory Basis (what is FRESH-VERIFIED present)

FACT (FRESH-VERIFIED, directory listing): `docs/CCAgentWorkSpace/Operator/` still holds date-prefixed full mirror files in-range (e.g. `2026-04-01--pa_review.md`, `2026-04-01--pm_execution_plan.md`, plus BB/E3/E5/MIT/PA/PM 2026-05-08/09 audit mirrors). The Operator-mirror duplicate CLASS is structurally intact.

FACT (FRESH-VERIFIED, listing): Both same-day E5 reports co-exist: `E5/2026-04-12--optimization_assessment_report.md` + `E5/2026-04-12--e5_optimization_final_report.md`.

FACT (CARRIED-FORWARD): prior `python3 hashlib` census over the window = **1184 dated docs/text files**, **56 SHA-256-identical Operator-mirror groups (112 files, 56 redundant)**. Not re-runnable (no Bash).

---

## 4. Prior-Finding Re-Verification Ledger

| Prior ID | Topic | Prior Sev | This-run verdict | Basis |
|---|---|---|---|---|
| TW-DOC-2026-05-17-01 | Operator↔PA mirror drift on `liquidation_pulse` claim | P1 | **DOWNGRADE → P2 / divergence UNVERIFIED** | grep §4.1 |
| TW-DOC-2026-05-17-02 | 56 exact Operator-mirror duplicate groups | P2 | **HELD** (files present; not in 2026-05-29 closure scope) | listing + closure read |
| TW-DOC-2026-05-17-03 | FundingArb v1/v2 audit docs active-looking post-retirement | P2 | **HELD** (no SUPERSEDED header; recommendation text intact) | grep §4.2 |
| TW-DOC-2026-05-17-04 | Legacy Phase 0a..6 execution plan indexed active | P2 | **CARRIED-FORWARD / UNVERIFIED** | header re-read blocked |
| TW-DOC-2026-05-17-05 | 2026-04-18 worklog fragmentation + `-1--`/`-2--` naming | P2 | **PARTIALLY HELD** (README index has no 2026-04-18 row) | README lines 879-892 |
| TW-DOC-2026-05-17-06 | E5 2026-04-12 assessment/final pair unmerged | P3 | **HELD** | listing |

### 4.1 Honesty correction on the prior P1 (TW-DOC-2026-05-17-01)
FACT (FRESH-VERIFIED, grep): The PA canonical copy `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-09--full_loss_architectural_root_cause_redesign.md` STILL contains the `requires_revival` language — line 243 (`pub liquidation_pulse: Option<...> // requires_revival flag — handler 已 4 weeks ago deleted`) and line 259 (`liquidation_pulse 復活前置條件 ... R-1 IMPL 必須先付 +1 sprint 重接 WS handler`).

This **contradicts my prior report**, which claimed the PA copy carried a 2026-05-27 correction stating the revival claim is false and the signal is active. I could not find that correction in the PA copy this run (`2026-05-27` grep returned no match in the readable window). Two possibilities, disclosed honestly:
1. My prior report's "2026-05-27 correction in PA copy" was **wrong / overstated** (most likely — the source text still says requires_revival); OR
2. The correction lives elsewhere and was mis-attributed.

Consequence: I can no longer assert an Operator-vs-PA *safety-claim divergence*. Both copies appear to carry the same `requires_revival` stance (Operator-copy grep was tool-degraded this run, so "both identical" is INFERENCE not FACT). Therefore I **downgrade this from P1 to P2** and fold it into the generic mirror-duplication finding (-02). PM: the live-misleading risk I previously flagged is **not substantiated** this run.

### 4.2 FundingArb staleness — HELD with fresh evidence
FACT (FRESH-VERIFIED, grep on `docs/audits/2026-04-17--g2_funding_arb_clean_edge_v2.md`): `SUPERSEDED|RETIRED|HISTORICAL|AMD-2026-05-26` returned **0 matches**; the file still reads `❌ NEGATIVE EDGE` (line 35) and `建議：升 R-02 重評 funding_arb 入場/退場參數 ... 或考慮停用` (line 37). The governing retired-closed decision `AMD-2026-05-26-01` (out-of-primary-range, 2026-05-26) is NOT referenced from these in-range audit files. Stale-doc-vs-current-decision gap CONFIRMED.

---

## 5. Findings (this run)

### TW-DOC-2026-05-30-01 — Exact Operator Mirror Duplicates (incl. former mirror-drift) [P2]
- Label: FACT (files present) / CARRIED-FORWARD (56-group census)
- Affected: `docs/CCAgentWorkSpace/Operator/*` full set (prior report Appendix A); representative `PA/.../2026-04-26--three_p0_fixes_design.md` ↔ `Operator/2026-04-26--three_p0_fixes_design.md`. Includes the former -01 pair `2026-05-09--full_loss_architectural_root_cause_redesign.md` (Operator ↔ PA).
- Evidence: directory listing FRESH-VERIFIED; 56-group SHA census carried forward; 2026-05-29 closure "Operator-mirror cmp=0" is SPECIFICATION_REGISTER-scoped, does not remove these.
- Impact: doubles in-range inventory; drift risk on any future correction to a canonical copy.
- Direction (no moves): PM mirror policy — role `workspace/reports/` canonical; replace Operator byte-duplicates with short index stubs (status + 1-para + canonical link + "mirror" header). Covers the ongoing 2026-05-29/30 pairs too (§6).
- Fix owner: PM + TW · Verify owner: R4

### TW-DOC-2026-05-30-02 — FundingArb v1/v2 Audit Docs Active-Looking After Retired Closure [P2]
- Label: FACT (FRESH-VERIFIED §4.2)
- Affected: `docs/audits/2026-04-16--g2_funding_arb_clean_edge.md`, `docs/audits/2026-04-17--g2_funding_arb_clean_edge_v2.md`; governing `docs/governance_dev/amendments/2026-05-26--AMD-2026-05-26-01-funding-arb-deprecation.md` (out-of-primary-range).
- Evidence: grep 0 SUPERSEDED/AMD matches; "NEGATIVE EDGE"/"建議：升 R-02" intact (lines 35/37).
- Impact: stale "re-evaluate or disable" recommendation reads as active during strategy-roster / P0-EDGE triage, contradicting the retired-closed AMD + ADR-0018 Retired.
- Direction: SUPERSEDED header on v1/v2 → AMD-2026-05-26-01; v2 canonical historical closeout; archive/index both under funding_arb retirement lineage.
- Fix owner: TW + PA · Verify owner: R4 + QC

### TW-DOC-2026-05-30-03 — Legacy Phase 0a..6 Execution Plan Still Indexed As Active [P2]
- Label: FACT (prior) / CARRIED-FORWARD (current header re-read blocked this run)
- Affected: `docs/execution_plan/README.md`, `docs/execution_plan/phase_0a.md`, `docs/execution_plan/phase_6.md`.
- Evidence (prior): README routed "開始 Phase ..." not "historical baseline"; phase docs carried stale acceptance (`EvolutionEngine deprecated`, `4629+ tests`). Header re-read could not complete this run (tool degradation).
- Direction: HISTORICAL header + single active-successor pointer (TODO.md / current sprint+spec), or archive packet with README stub.
- Fix owner: PA + TW · Verify owner: R4 · **PM: route a clean re-read to confirm still-open before action.**

### TW-DOC-2026-05-30-04 — 2026-04-18 Worklog Fragmentation + Naming-Convention Conflict [P2]
- Label: FACT (README index) / CARRIED-FORWARD (worklogs dir glob timed out this run)
- Affected: `docs/worklogs/2026-04-18--dual_track_exit_design.md`, `...-04-18-1--dual_track_exit_feasibility.md`, `...-04-18-2--exit_features_table_design.md`, +3 more 2026-04-18 fragments (per prior `find`); index `docs/README.md` worklogs table.
- Evidence (FRESH-VERIFIED): README "worklogs/ — 頂層工作日志（…daily_summary 為當日權威）" table (lines 879-892) lists 2026-04-08..14 + 04-27 only — **no 2026-04-18 row at all**, so the six same-day 2026-04-18 fragments are unindexed; two carry the nonstandard `2026-04-18-1--`/`-2--` prefix (violates `YYYY-MM-DD--desc.md`; note README later sanctioned `YYYY-MM-DD-N--` for same-day governance amendments, but these worklogs predate and don't fit that exception).
- Direction: create `2026-04-18--daily_summary.md`/`_INDEX` linking the fragments; add README worklogs row; flag `-1--`/`-2--` as legacy aliases. **Primary in-range naming-convention conflict.**
- Fix owner: TW · Verify owner: R4

### TW-DOC-2026-05-30-05 — E5 2026-04-12 Assessment/Final Pair Still Unmerged [P3]
- Label: FACT (FRESH-VERIFIED listing)
- Affected: `E5/2026-04-12--optimization_assessment_report.md`, `E5/2026-04-12--e5_optimization_final_report.md`, `E5/memory.md`.
- Evidence: both present; assessment remains unmarked standalone alongside the corrected final report (which prior run found contained a verification correction that the original had multiple false claims).
- Direction: header `optimization_assessment_report.md` → corrected final, or merge with redirect stub.
- Fix owner: E5 + TW · Verify owner: R4

---

## 6. Secondary (out-of-primary-range) — the dedup practice is ONGOING

INFERENCE (FRESH-VERIFIED, content search): the Operator-mirror duplication continues past the fixed window:
- `Operator/2026-05-30--lg3_reality_check_and_corrected_packet.md` ↔ `PA/workspace/reports/2026-05-30--lg3_reality_check_and_corrected_packet.md` (exact-stem pair, out-of-primary-range).
- `Operator/2026-05-29--v115_basis_panel_dry_run.md` ↔ `MIT/workspace/reports/2026-05-29--v115_basis_panel_dry_run.md`.
- `Operator/2026-05-29--cold_audit_*` mirrors of PA pkgB/C cold-audit specs.

So Finding -01 is not just historical cleanup; the mirror-policy decision is an **active governance choice** for PM. (The 2026-05-29 closure's P1-15 "Operator-mirror cmp=0" is SPECIFICATION_REGISTER-scoped and did not change this.)

ASSUMPTION: TW memory report index shows a 2026-05-28 doc-cleanup phase 1/2 series + 2026-05-29 v80 cold-audit Wave 3 (P2-17 index drift, R4-dedup broken links). PM should reconcile this re-run against that lineage to avoid re-raising already-fixed index items.

---

## 7. Dedup / Merge / Archive Plan (proposals only — NO moves performed)

1. **Operator mirror policy (root cause)** — PM decides one canonical location (role `workspace/reports/`); replace Operator byte-duplicates with short index stubs. Covers -01 (incl. former mirror-drift pair) + ongoing 2026-05-29/30 pairs. *PM decide → TW execute → R4 verify.*
2. **FundingArb retirement lineage** — SUPERSEDED headers on `2026-04-16`/`2026-04-17` g2 audits → AMD-2026-05-26-01; v2 canonical historical; archive both. *TW+PA → R4+QC.* (Cleanest concrete fix; fully FRESH-VERIFIED open.)
3. **Phase 0a..6 legacy packet** — HISTORICAL header on `execution_plan/README.md` + phase docs + active-successor pointer, or archive with README stub (confirm still-open first). *PA+TW → R4.*
4. **2026-04-18 worklog closeout + naming fix** — `2026-04-18--daily_summary.md`/`_INDEX` + README worklogs row; flag `-1--`/`-2--` legacy aliases. *TW → R4.*
5. **E5 pair** (P3) — header `optimization_assessment_report.md` → corrected final, or merge w/ redirect stub. *E5+TW → R4.*

---

## 8. Counts

- P0: 0
- P1: 0
- P2: 4 (TW-DOC-2026-05-30-01 Operator mirrors; -02 funding_arb stale; -03 Phase 0a..6; -04 2026-04-18 worklogs)
- P3: 1 (TW-DOC-2026-05-30-05 E5 pair)

---

## 9. Honesty / Limitations Statement

- No Bash → prior hash/diff/find numbers carried forward, not re-measured.
- Tool degradation blocked current-state re-reads for -03 (Phase 0a..6 headers) and the -04 worklog directory listing; both rest on FRESH-VERIFIED *index* evidence + carried-forward file presence, flagged for clean re-read.
- **Self-correction (fail-loud):** my prior 2026-05-17 P1 "Operator-vs-PA `liquidation_pulse` corrected-claim divergence" is **NOT substantiated** this run — the PA copy still carries `requires_revival` (lines 243/259) and no 2026-05-27 correction was found. Downgraded to P2, folded into the generic mirror finding. PM should treat the previously-claimed live-misleading risk as retracted pending contrary evidence.
- The 2026-05-29 closure archive IS readable and complete; its "Operator-mirror cmp=0" (P1-15) is SPECIFICATION_REGISTER-scoped and does not dedup the CCAgentWorkSpace Operator mirrors.
- Net: prior TW remediation **largely HELD as open items** — only index-link hygiene (P2-17 lane) was closed by the 2026-05-29 run; the four substantive doc-hygiene findings (-01..-04 here) were not in that closure's scope.
