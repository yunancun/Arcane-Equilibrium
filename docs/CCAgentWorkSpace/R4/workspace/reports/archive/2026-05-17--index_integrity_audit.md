# R4 Index Integrity Audit

Date prefix: `2026-05-17` per operator request.
Actual local audit time: 2026-05-29 Europe/Madrid.
Repo root: `/Users/ncyu/Projects/TradeBot/srv`.
Role: R4(explorer), read-only audit.

Baseline note read: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-17--cold_audit_baseline_freeze.md`.

## Scope And Evidence

- Mandatory context read: `AGENTS.md`, `CLAUDE.md`, `TODO.md`, `.codex/MEMORY.md`, `.codex/agents/INDEX.md`, `.codex/AGENT_DISPATCH_PROTOCOL.md`, `.codex/SUBAGENT_EXECUTION_RULES.md`, `.codex/agents/R4.md`, `.claude/agents/R4.md`, R4 profile/memory/latest report, `README.md`, `docs/agents/context-loading.md`, `docs/agents/todo-maintenance.md`, `docs/README.md`, `helper_scripts/SCRIPT_INDEX.md`, `docs/governance_dev/SPECIFICATION_REGISTER.md`, PM baseline freeze.
- Local HEAD during this audit: `9bf71423a0c3251ef56393c7b0e137f45f3127ff`.
- Worktree was already dirty before this report. Existing non-report changes were not touched.
- Evidence commands were read-only except creating this report file.

## Executive Verdict

No P0 found.

P1 found: 1.

The biggest integrity risk is not a runtime mutation risk; it is source-of-truth drift. The most concrete P1 is the governance specification register pointing ADR-0036 through ADR-0041 at non-existent filenames while matching ADR files exist under different names. Later roles following the register can land updates against dead paths or fail to load active decisions.

## Active Docs Map

Use these as active routing surfaces:

| Area | Active source |
|---|---|
| Operating / hard boundaries | `CLAUDE.md`, `.codex/MEMORY.md`, `AGENTS.md` |
| Codex role / dispatch | `.codex/agents/INDEX.md`, `.codex/agents/*.md`, `.codex/AGENT_DISPATCH_PROTOCOL.md`, `.codex/SUBAGENT_EXECUTION_RULES.md` |
| Stable project entry | `README.md`, `CONTEXT.md`, `docs/agents/context-loading.md` |
| Active queue / runtime state | `TODO.md` |
| TODO lifecycle | `docs/agents/todo-maintenance.md` |
| Governance register | `docs/governance_dev/SPECIFICATION_REGISTER.md` |
| Current ADR files | `docs/adr/0001-0045*.md`; ADR-0046 is referenced as Proposed but no file exists |
| Current execution plans | `docs/execution_plan/`, `docs/execution_plan/specs/` |
| Current amendments | `docs/governance_dev/amendments/` |
| Script catalog | `helper_scripts/SCRIPT_INDEX.md` |
| Role evidence | `docs/CCAgentWorkSpace/<ROLE>/workspace/reports/` |

## Historical Docs Map

Use these as historical / evidence surfaces, not active state:

| Area | Historical source |
|---|---|
| Completed TODO / old CLAUDE / README snapshots | `docs/archive/` |
| Archived phase worklogs | `docs/archive/2026-05-28--worklog_*_archived/` |
| Superseded REF-20 / REF-21 plans | `docs/archive/2026-05-28--ref20_*`, `docs/archive/2026-05-28--ref21_*` |
| Old daily worklogs | `docs/worklogs/` |
| Older agent evidence | role reports under `docs/CCAgentWorkSpace/*/workspace/reports/` |
| Deep old inventory / RCA | `OPENCLAW_INVENTORY_CONSOLIDATED.md` only on demand |

## Findings

### R4-IDX-001 — Governance Register ADR Paths Are Broken

- Label: FACT
- Severity: P1
- Affected path + line: `docs/governance_dev/SPECIFICATION_REGISTER.md:133`
- Evidence command or inspection method:
  - `nl -ba docs/governance_dev/SPECIFICATION_REGISTER.md | sed -n '124,140p'`
  - Python existence check for registered path versus actual ADR filenames.
  - Result: registered paths for ADR-0036, 0037, 0038, 0039, 0040, and 0041 are missing, while actual files exist with different filenames:
    - missing `docs/adr/0036-m8-anomaly-m10-tier-d-blacklist.md`; actual `docs/adr/0036-m8-anomaly-detection-and-m10-tier-d-model-blacklist.md`
    - missing `docs/adr/0037-m9-ab-framework.md`; actual `docs/adr/0037-m9-ab-framework-and-statistical-methodology.md`
    - missing `docs/adr/0038-m11-continuous-counterfactual-replay.md`; actual `docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md`
    - missing `docs/adr/0039-m12-orderrouter-trait-maker-fill-rate.md`; actual `docs/adr/0039-m12-order-router-trait-and-maker-fill-rate-metric.md`
    - missing `docs/adr/0040-m13-multi-venue-gate-y3.md`; actual `docs/adr/0040-multi-venue-gate-spec.md`
    - missing `docs/adr/0041-context-distiller-v4-doc-08-ai-cost-cap.md`; actual `docs/adr/0041-context-distiller-v4-and-ai-cost-cap-amendment.md`
- Impact: The formal governance register is the SSOT for spec lookup. A later PA/TW/R4 role can follow dead paths, miss active ADR content, or duplicate ADR entries.
- Why this is real, not false positive: The registered paths do not exist on disk; same-number ADR files do exist under different names, proving this is a stale target problem rather than a missing ADR family.
- Suggested fix direction: Update register path cells for ADR-0036 through ADR-0041 to the actual filenames, then run a path-existence check over every register path.
- Fix owner role: TW(worker) for doc patch, PA(default) if ADR naming intent needs arbitration.
- Verification owner role: R4(explorer).

### R4-IDX-002 — TODO Points To Missing v65 Archive

- Label: FACT
- Severity: P2
- Affected path + line: `TODO.md:17`
- Evidence command or inspection method:
  - `nl -ba TODO.md | sed -n '1,30p;458,466p'`
  - `test -f docs/archive/2026-05-26--todo_v65_archive.md`
  - Result: `docs/archive/2026-05-26--todo_v65_archive.md` is missing; TODO references it at lines 17 and 463.
- Impact: TODO is the active state authority. It advertises a historical archive that later roles cannot load, so v65 retained details are not recoverable through the stated route.
- Why this is real, not false positive: The text says `待 archive`, but it still presents a concrete path in the active source-of-truth file. The file is absent while sibling archives such as `2026-05-21--todo_v60_archive.md` exist.
- Suggested fix direction: Either create the v65 archive from the intended source or change TODO wording to remove the concrete path until the archive exists. Do not edit TODO during this R4 read-only report task.
- Fix owner role: PM(default) for active-state decision, TW(worker) for archive/index doc patch.
- Verification owner role: R4(explorer).

### R4-IDX-003 — docs/README Lists Archived M13/V116 Artifacts As Active execution_plan Files

- Label: FACT
- Severity: P2
- Affected path + line: `docs/README.md:340`
- Evidence command or inspection method:
  - `nl -ba docs/README.md | sed -n '332,346p'`
  - `test -e` checks for the listed paths and archived equivalents.
  - Missing active paths:
    - `docs/execution_plan/2026-05-21--m13_multi_venue_asset_class_design_spec.md`
    - `docs/execution_plan/2026-05-21--v116_m13_multi_venue_reserved_schema_spec.md`
  - Existing archived paths:
    - `docs/archive/2026-05-21--sprint_1a_delta_dup_artifacts/2026-05-21--m13_multi_venue_asset_class_design_spec.md`
    - `docs/archive/2026-05-21--sprint_1a_delta_dup_artifacts/2026-05-21--v116_m13_multi_venue_reserved_schema_spec.md`
- Impact: The docs index says these are active `execution_plan/` artifacts, but the only matching files are archived duplicate artifacts. A later role can read the wrong lifecycle state for M13/V116.
- Why this is real, not false positive: Adjacent lines 341 and 345 point to active replacement files that do exist; lines 340 and 344 are specifically the archived names.
- Suggested fix direction: Change these rows to archived paths with superseded/discarded wording, or remove them from the active Sprint 1A-delta table and keep only the active ADR-aligned M13/V116 files.
- Fix owner role: TW(worker).
- Verification owner role: R4(explorer).

### R4-IDX-004 — docs/README Coverage Is Structurally Incomplete Against Its Own Mandatory Rule

- Label: FACT
- Severity: P2
- Affected path + line: `docs/README.md:15`
- Evidence command or inspection method:
  - `nl -ba docs/README.md | sed -n '9,18p'`
  - Literal path inventory: `find docs -name '*.md'` plus membership check against `docs/README.md`.
  - Result: 2,288 markdown docs found; 1,781 markdown docs are not literally indexed by path in `docs/README.md`.
  - Major missing groups by first path segment: `CCAgentWorkSpace` 1,209; `archive` 145; `governance_dev` 135; `execution_plan` 76; `references` 64; `audits` 33.
- Impact: The document index is no longer a complete directory index despite declaring that every new/moved docs file must update it. This makes orphan and stale-link detection dependent on ad hoc R4 scripts instead of the advertised SSOT.
- Why this is real, not false positive: The count uses literal repo paths and the README's own mandatory rule. Some omissions may be intentionally summarized by directory, but the current rule does not say summaries are acceptable substitutes.
- Suggested fix direction: Decide whether `docs/README.md` should remain a literal complete index. If yes, generate/maintain complete sections. If no, amend the rule and create machine-readable sub-indexes for high-volume areas such as role reports and archives.
- Fix owner role: PM(default) for index policy decision, TW(worker) for implementation.
- Verification owner role: R4(explorer).

### R4-IDX-005 — helper_scripts/SCRIPT_INDEX Omits Most Script-Like Files

- Label: FACT
- Severity: P2
- Affected path + line: `helper_scripts/SCRIPT_INDEX.md:1`
- Evidence command or inspection method:
  - Script inventory over `helper_scripts/**/*` for `.sh`, `.py`, `.sql`, `.md`, `.toml`, and `Caddyfile.template`.
  - Result: 296 script-like/helper files found; 176 were not mentioned in `helper_scripts/SCRIPT_INDEX.md`.
  - Examples missing from index: `bybit/liquidation_topic_probe_v2.py`, `calibration/phase_1b_sweep_cli.py`, `canary/healthchecks/66_close_maker_pre_stopout_rate.py`, `cron/blocked_symbols_30d_unblock_check_cron.sh`, `db/post_restore_validation.sql`, `m4/pattern_miner_stage_1.py`, `reports/w_audit_8b_funding_skew_stage0r.py`.
- Impact: Later operators and agents cannot rely on `SCRIPT_INDEX.md` to discover available helpers. This is especially risky for healthcheck and cron surfaces where stale or hidden scripts affect passive waits and runtime evidence.
- Why this is real, not false positive: The inventory excludes caches and compares actual helper paths against the index text. The missing examples are real files under `helper_scripts/`.
- Suggested fix direction: Add generated per-subdir summaries or a complete inventory section, then define which test files and package markers are intentionally excluded.
- Fix owner role: TW(worker) for index maintenance, E1(worker) when script ownership details are needed.
- Verification owner role: R4(explorer).

### R4-IDX-006 — helper_scripts Index Contains A Wrong Path For checks_cron_heartbeat

- Label: FACT
- Severity: P3
- Affected path + line: `helper_scripts/SCRIPT_INDEX.md:4`
- Evidence command or inspection method:
  - `nl -ba helper_scripts/SCRIPT_INDEX.md | sed -n '1,8p'`
  - `test -e helper_scripts/passive_wait_healthcheck/checks_cron_heartbeat.py`
  - `test -e helper_scripts/db/passive_wait_healthcheck/checks_cron_heartbeat.py`
  - Result: line 4 says `passive_wait_healthcheck/checks_cron_heartbeat.py`; the actual path is `db/passive_wait_healthcheck/checks_cron_heartbeat.py`.
- Impact: Small but concrete wrong-target in the update header; someone following the header can inspect the wrong path.
- Why this is real, not false positive: The index later has the correct `db/passive_wait_healthcheck/checks_cron_heartbeat.py` entry, so this is a stale shorthand in the header, not a parser artifact.
- Suggested fix direction: Correct the header path or remove detailed file paths from the changelog-style header.
- Fix owner role: TW(worker).
- Verification owner role: R4(explorer).

### R4-IDX-007 — README ADR Count Is Stale

- Label: FACT
- Severity: P3
- Affected path + line: `README.md:70`
- Evidence command or inspection method:
  - `nl -ba README.md | sed -n '64,72p'`
  - `find docs/adr -maxdepth 1 -type f | wc -l`
  - Result: README says `14` ADR records; filesystem has 45 ADR markdown files.
- Impact: Low operational risk because README points readers to `docs/adr/`, but the project structure snapshot is materially stale.
- Why this is real, not false positive: The count is a direct filesystem count of `docs/adr/*.md`; no generated or archived ADRs are mixed in.
- Suggested fix direction: Replace the fixed count with "ADR 0001-0045" or a non-numeric description unless this count is automatically maintained.
- Fix owner role: TW(worker).
- Verification owner role: R4(explorer).

### R4-IDX-008 — ADR-0046 Is Referenced As Proposed But Has No ADR File Or Register Row

- Label: FACT
- Severity: P2
- Affected path + line: `TODO.md:459`
- Evidence command or inspection method:
  - `rg -n "ADR-0046|0046" docs README.md TODO.md CLAUDE.md .codex/MEMORY.md`
  - `find docs -path '*0046*' -o -path '*funding*redesign*'`
  - `find docs/adr -maxdepth 1 -type f | wc -l`
  - Result: TODO lists ADR-0046 as `PROPOSED 2026-05-25`; ADR-0018 line 49 points to `docs/adr/0046-...`; no `docs/adr/0046*.md` file exists; `SPECIFICATION_REGISTER.md` has ADR rows only through ADR-0045.
- Impact: Later funding_arb revival/redesign work has a governance anchor by number but no actual proposed ADR artifact to load. This is dangerous because ADR-0046 is used as a revive gate in funding_arb retirement docs.
- Why this is real, not false positive: Prior R4 notes treat ADR-0046 registration as future debt, but current active TODO and ADR-0018 both reference it. The absence of a file is verifiable.
- Suggested fix direction: Either create a proper Proposed ADR-0046 file and register it, or downgrade references to "future ADR slot, not yet filed" without a pseudo-path.
- Fix owner role: PA(default) for governance content, TW(worker) for ADR/register patch.
- Verification owner role: R4(explorer).

### R4-IDX-009 — Agent Workspace Reports Are Not Systematically Indexed

- Label: FACT
- Severity: P3
- Affected path + line: `docs/README.md:1250`
- Evidence command or inspection method:
  - `nl -ba docs/README.md | sed -n '1250,1275p'`
  - Inventory: `docs/CCAgentWorkSpace/*/workspace/reports/*.md` versus literal path membership in `docs/README.md`.
  - Result: 1,260 role report markdown files found; 963 are not literally indexed by path in `docs/README.md`.
- Impact: Role evidence discovery depends on grep and ad hoc knowledge. This is tolerable for high-volume reports only if the repo explicitly adopts per-role report indexes or directory-level indexing.
- Why this is real, not false positive: The files are real report artifacts under the canonical role workspace location. The docs README only lists selected reports plus role directories.
- Suggested fix direction: Add per-role generated report indexes, or amend `docs/README.md` to state that `CCAgentWorkSpace` is indexed by directory convention and latest report discovery uses `ls -1t`.
- Fix owner role: PM(default) for policy, TW(worker) for generated/manual indexes.
- Verification owner role: R4(explorer).

### R4-IDX-010 — Archive Index Is Incomplete

- Label: FACT
- Severity: P3
- Affected path + line: `docs/README.md:1278`
- Evidence command or inspection method:
  - `nl -ba docs/README.md | sed -n '1278,1295p'`
  - Inventory: `docs/archive/**/*.md` versus literal path membership in `docs/README.md`.
  - Result: 168 archive markdown files found; 145 are not literally indexed by path in `docs/README.md`.
- Impact: Historical lookup works only if the reader knows the archive folder shape or uses search. That is not fatal, but it weakens the archive references requested by TODO/context-loading.
- Why this is real, not false positive: Archive files are real markdown files under `docs/archive/`; the archive section lists only a small subset.
- Suggested fix direction: Add an archive `_README.md` or generated manifest, then have `docs/README.md` point to that manifest instead of trying to list everything inline.
- Fix owner role: TW(worker).
- Verification owner role: R4(explorer).

## No-Issue / Lower-Risk Notes

- `docs/archive/2026-05-28--worklog_*_archived/_README.md` links referenced by `docs/README.md:868-873` exist.
- README contextual references such as `canary/engine_watchdog.py` under the "Common Scripts" section resolve to `helper_scripts/canary/engine_watchdog.py`; I did not count those as broken README links.
- Runtime was not inspected or mutated; this audit is source-index integrity only.

## Suggested Verification Commands For Follow-Up

```bash
python3 - <<'PY'
from pathlib import Path

for p in [
    'docs/archive/2026-05-26--todo_v65_archive.md',
    'docs/adr/0046-basis-observation-execution-split.md',
]:
    print(('OK' if Path(p).exists() else 'MISSING'), p)
PY
```

```bash
python3 - <<'PY'
from pathlib import Path
idx = Path('helper_scripts/SCRIPT_INDEX.md').read_text(errors='ignore')
files = [p for p in Path('helper_scripts').rglob('*') if p.is_file() and p.name != 'SCRIPT_INDEX.md']
missing = [str(p.relative_to('helper_scripts')) for p in files if str(p.relative_to('helper_scripts')) not in idx]
print(len(files), len(missing))
PY
```

R4 DOC AUDIT DONE: report path: `docs/CCAgentWorkSpace/R4/workspace/reports/2026-05-17--index_integrity_audit.md`
