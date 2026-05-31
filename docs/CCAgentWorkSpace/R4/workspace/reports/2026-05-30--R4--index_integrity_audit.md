# R4 Index Integrity Audit — 2026-05-30 (campaign label 2026-05-17 re-run)

> PERSISTENCE NOTE (PM): R4(explorer) ran with a read-only toolset (Read/Grep/Glob/WebSearch, no Write/Edit) and could not write this file. R4 returned the full report inline; PM(default) persisted it verbatim to this path on R4's behalf. Authorship = R4(explorer); persistence = PM(default).

Baseline: frozen commit `187704f6`, branch `main`; only worktree change ` M TODO.md` (operator WIP, not authoritative).
Repo root: `/Users/ncyu/Projects/TradeBot/srv` (sole repo on Mac; `OpenClaw` grep confirms no stray Mac duplicate).
Role: R4(explorer), READ-ONLY. Audit time: 2026-05-30. Evidence: Read/Grep/Glob only; no mutation; no ssh executed (Mac-local index audit sufficient; runtime facts below taken from TODO with timestamps, flagged where unverified).

## Executive Verdict
P0: 0 · P1: 1 · P2: 4 · P3: 5.
Biggest risk is still source-of-truth drift, not runtime. The single P1 is a genuine governance-anchor gap: ADR-0046 is cited as an active revive-gate by ADR-0018, AMD-2026-05-26-01, and active TODO §3/§8/§9, but no `docs/adr/0046-*.md` file exists and the register has no ADR-0046 row. Prior 2026-05-17 R4 P1 (R4-IDX-001 broken ADR-0036..0041 register paths) HELD FIXED (P1-15 closure).

## Active-Docs vs Historical/Archive Map (key deliverable for other audit agents)

### Canonical SoT (route here; do not infer from memory)
| Area | Active source | Verified |
|---|---|---|
| Operating rules / hard boundaries | `CLAUDE.md`, `.codex/MEMORY.md`, `AGENTS.md` | exist |
| Stable project entry / GUI / source map | `README.md` | exists (some stale counts — see findings) |
| Active queue / runtime evidence / blockers | `TODO.md` (v84; date 2026-05-29) | exists |
| Context routing | `docs/agents/context-loading.md` | exists |
| Domain glossary | `CONTEXT.md` | exists |
| Governance spec register (DOC/SM/EX/REF/ARCH/AUDIT/ADR-0034-0045) | `docs/governance_dev/SPECIFICATION_REGISTER.md` | exists (252 lines; counts stale — see R4-2026-IDX-06) |
| ADR decisions | `docs/adr/` (0001-0045, 44 files; **0046 absent**) | verified by glob |
| Active amendments | `docs/governance_dev/amendments/` (24 files) | exist |
| Script catalog | `helper_scripts/SCRIPT_INDEX.md` (README §常用脚本; NOT `docs/SCRIPT_INDEX.md`) | confirmed: `docs/SCRIPT_INDEX.md` absent |
| Doc index / placement rules | `docs/README.md` (~1347 lines) | exists |
| Role evidence | `docs/CCAgentWorkSpace/<ROLE>/workspace/reports/` | exist |
| Execution plans / specs | `docs/execution_plan/`, `docs/execution_plan/specs/`, `docs/runbooks/` | exist |
| CHANGELOG (exec-plan version) | `CHANGELOG.md` (root); engineering history `docs/CLAUDE_CHANGELOG.md` | exist |

### Active specs (per register, all ✅ Active unless noted)
SM-01..SM-05 (SM-05 🟡 Accepted/Source) · EX-01..EX-07 · DOC-01..DOC-04, DOC-06..DOC-08 (no DOC-05) · LG-X-01..05 · OPS-X-01 · REF-01..REF-21 · ARCH-01..ARCH-05 · AUDIT-01..AUDIT-13 · ADR-0034..ADR-0045 (register-tracked) · M1..M13 (Design/Stub).

### Historical / archive (NOT active state)
| Area | Source |
|---|---|
| Completed TODO/CLAUDE/README snapshots, closure archives | `docs/archive/` (70 files; cold-audit closure = `2026-05-29--cold_audit_p1_p2_p3_closure_archive.md`) |
| Phase-packet worklogs | `docs/archive/2026-05-28--worklog_*_archived/*/_README.md` |
| Sprint 1A-δ dup artifacts | `docs/archive/2026-05-21--sprint_1a_delta_dup_artifacts/` |
| Python-era governance phases (phase0-12 / T2.xx) | `docs/governance_dev/` body (`DEPRECATED.md` header says PARTIALLY DEPRECATED; only `amendments/` + `SPECIFICATION_REGISTER.md` Active) |
| Deep old inventory / RCA | `OPENCLAW_INVENTORY_CONSOLIDATED.md` (on demand) |
| Pre-trim root snapshot | `srv/2026-05-17--cold_audit_pm_final.md` (prior campaign ruling, root-level) |

## Findings

### R4-2026-IDX-01 — ADR-0046 referenced as active governance anchor but file + register row both absent
- Label: FACT · Severity: P1
- Path+line: `docs/adr/0018-funding-arb-v2-deprecation-watch.md:6,26,28,41,49`; `docs/governance_dev/amendments/2026-05-26--AMD-2026-05-26-01-funding-arb-deprecation.md:41,49`; `TODO.md:111,287,314,326,446,487,604`; `docs/README.md:228`
- Evidence: `glob docs/adr/0046*` → no files (44 ADR files, 0001-0045 contiguous except no gap). `grep ADR-0046 docs/governance_dev/SPECIFICATION_REGISTER.md` → 0 hits (register ADR section stops at ADR-0045). ADR-0018:49 writes the pseudo-path `docs/adr/0046-...` (Proposed). TODO §1/§3/§8/§9 use ADR-0046 as the funding_arb revive hard-gate ("ADR-0046 Accepted" required before revive).
- Impact: A live risk-control revive gate (funding_arb deprecation per AMD-2026-05-26-01) hangs off a governance ID that has no loadable artifact and no register entry. A later PA/E1/QA following the revive path cannot load the gate definition; worse, the gate could be treated as satisfiable by a thin stub. This is the same class as the prior R4-IDX-008 (P2) but has hardened into an active revive-gate dependency since 2026-05-26, so it escalates to P1.
- Why real, not FP: file-existence and register-row absence are both directly verifiable; ADR-0018 + active TODO both reference it as a gate, not as future debt.
- Fix direction: create a proper Proposed ADR-0046 file (`docs/adr/0046-funding-arb-v3-redesign-slot.md`) + register row marked Proposed; OR downgrade all references to "future ADR slot, not yet filed" and remove the pseudo-path `docs/adr/0046-...`.
- Fix owner: PA(default) governance content + TW(worker) ADR/register/TODO patch. Verify owner: R4(explorer).

### R4-2026-IDX-02 — TODO points to missing v65 archive (3 sites) — prior R4-IDX-002 REGRESSED/UNRESOLVED
- Label: FACT · Severity: P2
- Path+line: `TODO.md:23`, `TODO.md:491` (also §-2 banner `TODO.md:27` "v65 沿用")
- Evidence: `glob docs/archive/*v65*` and `glob docs/archive/2026-05-26*` → no files. TODO:23 `v65 archive: docs/archive/2026-05-26--todo_v65_archive.md（待 archive…）`; TODO:491 repeats the concrete path.
- Impact: TODO (active SoT) advertises a v65 archive twice with a concrete path that does not exist; v65-retained detail (5 Strategy Stage roster / 5.1.1 H ticket / W-AUDIT-4b) is not recoverable via the stated route. Identical to prior 2026-05-17 R4-IDX-002 — NOT fixed; still `待 archive` 4+ days later, and the v84 TODO churn did not resolve it.
- Why real, not FP: text presents a concrete path in active SoT; sibling `2026-05-21--todo_v60_archive.md` exists, so the pattern is "create it or drop the path."
- Fix direction: create the v65 archive from intended source OR change wording to remove the concrete path until it exists. Fix owner: PM(default) state decision + TW(worker) archive/index. Verify owner: R4.

### R4-2026-IDX-03 — README §项目结构 ADR count stale: "14 条" vs 45 actual — prior R4-IDX-007 HELD (not fixed)
- Label: FACT · Severity: P2
- Path+line: `README.md:70` ("14 条架构决策记录"); also `docs/README.md:35` ("ADR 0001..0022")
- Evidence: `glob docs/adr/0*.md` → 44 files spanning 0001-0045 (0001-0045 with no gaps except 0046). README:70 says 14; docs/README:35 says range ends 0022. `docs/CLAUDE_CHANGELOG.md:170` already records an earlier 0019→0022 bump, so this index is known-drifting.
- Impact: low operational (README points readers to `docs/adr/`), but two separate index surfaces materially understate ADR coverage (14 and "..0022" vs 0045). Misleads any agent estimating governance surface size or "is ADR-00XX filed".
- Why real, not FP: direct filesystem count; no archived/generated ADRs mixed in.
- Fix direction: replace fixed counts with "ADR 0001-0045" or non-numeric; both README:70 and docs/README:35. Fix owner: TW(worker). Verify owner: R4.

### R4-2026-IDX-04 — SCRIPT_INDEX header still carries stale per-file path (prior R4-IDX-006 class) + index coverage gap
- Label: FACT · Severity: P3
- Path+line: `helper_scripts/SCRIPT_INDEX.md:4` (changelog-style header lists detailed file paths inside a date stamp)
- Evidence: header `最後更新：2026-05-29` packs nested change descriptions including specific paths; prior 2026-05-17 R4-IDX-006 flagged the same header pattern (`passive_wait_healthcheck/checks_cron_heartbeat.py` wrong vs `db/passive_wait_healthcheck/...`). The header style persists and accretes. (Full coverage-count re-derivation from prior R4-IDX-005 not re-run this pass; pattern unchanged.)
- Impact: SCRIPT_INDEX header is a changelog, not a clean index; stale per-file shorthands accumulate. Low risk; discovery still works via body tables.
- Fix direction: keep header to a 1-line date + pointer; move per-file detail into dated body sections only. Fix owner: TW(worker). Verify owner: R4.

### R4-2026-IDX-05 — `docs/governance_dev/DEPRECATED.md` is a directory-deprecation header, not the DOC-blacklist the doc-cross-reference SSOT expects
- Label: FACT · Severity: P3
- Path+line: `docs/governance_dev/DEPRECATED.md` (18 lines total)
- Evidence: file content is the "PARTIALLY DEPRECATED phase0-12 / T2.xx" directory notice (says only `amendments/` + `SPECIFICATION_REGISTER.md` remain Active). The R4 skill SSOT order (priority-2 #9) names `docs/governance_dev/DEPRECATED.md` as "已棄用 DOC 黑名單" (deprecated-DOC blacklist with retracted IDs + dates + 禁引 markers). No such blacklist content exists; line 5 also says "22 spec" (register actually lists 24 active SM/EX/DOC/LG + 1 OPS + 19 REF + 5 ARCH).
- Impact: a future R4/PA following the skill expects a deprecated-DOC denylist here and finds a directory notice; retired specs (e.g. ADR-0018 funding_arb "Retired closed" per AMD-26-01) are not captured in any central deprecated-ID list. Drift risk: agents may re-cite retired IDs as active.
- Why real, not FP: file content vs skill contract directly compared; the "22 spec" sub-claim is internally inconsistent with the register's own counts.
- Fix direction: either (a) add a proper Deprecated-ID section to DEPRECATED.md (ADR-0018 Retired, AMD v1 superseded, etc.) per skill SOP, or (b) amend the skill SSOT list to point at the register's own status columns + retire the "黑名單" expectation. Also fix the "22 spec" stale number. Fix owner: PA(default) decision + TW(worker). Verify owner: R4.

### R4-2026-IDX-06 — SPECIFICATION_REGISTER Cross-Reference Summary counts + ADR header range stale
- Label: FACT · Severity: P3
- Path+line: `docs/governance_dev/SPECIFICATION_REGISTER.md:125` (header "ADR-0034 ~ ADR-0045" — table actually ends at 0045 ✓ but excludes 0001-0033 which are real ADRs not registered); `:224-226` (Total code references "335+", Implementing modules "22", Test coverage "2,308+ Rust lib tests")
- Evidence: counts are static, undated, and inconsistent with current runtime (TODO/closure archive cite ~3,600+ Rust lib tests, e.g. closure archive "openclaw_engine 3599/0"; README §治理模组 cites "~6,500 测试"). Register ADR section only covers 0034-0045 while 12 other active ADRs (0006/0017/0018/0020/0022/0023/0024/0028/0029/0030/0031/0032/0033 per TODO:487 "Active ADR") have no register row at all.
- Impact: register understates test coverage by ~1,300 and omits 12+ active ADRs from its own catalog; a reader treating the register as the ADR SSOT misses pre-0034 decisions.
- Why real, not FP: register self-contained numbers vs cross-doc cited numbers; ADR row gap directly visible.
- Fix direction: either expand register ADR section to all active ADRs, or add a one-line note "ADR 0001-0033 indexed in `docs/adr/` directly; register tracks 0034+"; refresh or de-numericize the count summary with a collection-time stamp. Fix owner: TW(worker) (R4 maintains this register per its own header). Verify owner: R4.

### R4-2026-IDX-07 — README "21 个治理模组" claim is unverified-as-stated (heritage Python framing vs Rust authority)
- Label: INFERENCE · Severity: P3
- Path+line: `README.md:126` ("21 个治理模组实现，覆盖 4 个核心状态机 + 17 个扩展模组")
- Evidence: register lists SM-01..05 (5) + EX-01..07 (7) + DOC-01..08 minus DOC-05 (7) = 19 active SM/EX/DOC, plus the "Implementing modules 22" register figure. The "21 = 4 SM + 17 ext" decomposition matches neither the register's 24-active-spec count nor its 22-module count. README:133 separately cites "~6,500 测试" which is the more current figure.
- Impact: the "21 个治理模组 / 4+17" decomposition is a heritage T2.01-T2.23 framing that no longer maps cleanly onto the Rust-authority register; readers may mis-count governance surface.
- Why INFERENCE not FACT: "21" may be a deliberate legacy count of T2.xx modules; I cannot prove it wrong without the T2 roster, but it does not reconcile with the current register decomposition → flagged as unverified-claim.
- Fix direction: reconcile README:126 against register active-spec count or mark it as "(legacy T2.01-T2.23 framing)". Fix owner: TW(worker)/PA. Verify owner: R4.

### R4-2026-IDX-08 — README "209 /api/v1" and "21 治理模组" / "~6,500 测试" are unverified runtime/surface claims (no timestamp, no source cmd)
- Label: ASSUMPTION → flagged unverified-claim · Severity: P3
- Path+line: `README.md:75` ("FastAPI 209 /api/v1 + 11 non-api 路由 + 3,700+ 测试"); `README.md:133` ("~6,500 测试")
- Evidence: README §项目结构 carries hardcoded endpoint count (209) and two divergent test totals (3,700+ at line 75, ~6,500 at line 133) with no collection date or source command. README is a stable-surface doc; per G6-04 any embedded count should be timestamped or de-numericized. I did NOT count routes (out of index-audit scope) — flagging as unverified, not asserting wrong.
- Impact: stable-doc numeric claims drift silently; two different test totals in the same README is an internal inconsistency.
- Why flagged: G6-04 drift rule — embedded counts in stable docs without timestamp/source are drift-prone; the 3,700+ vs 6,500 internal split is FACT-level inconsistent.
- Fix direction: de-numericize ("200+ /api/v1 routes") or add collection date; reconcile the two test totals. Fix owner: TW(worker). Verify owner: R4.

## Prior 2026-05-17 R4 findings — held/regressed
| Prior | Severity | Status now |
|---|---|---|
| R4-IDX-001 register ADR-0036..0041 broken paths | P1 | **HELD FIXED** — register:133-138 now full filenames; matches P1-15 closure. Verified all 6 paths exist. |
| R4-IDX-002 TODO → missing v65 archive | P2 | **REGRESSED/UNRESOLVED** — still missing, still cited TODO:23,491 → re-filed as R4-2026-IDX-02. |
| R4-IDX-003 docs/README archived M13/V116 as active | P2 | **LIKELY FIXED** (P2-17 closure "repointed to archive"); not re-deep-verified this pass — recommend spot-check. |
| R4-IDX-004 docs/README structurally incomplete vs own rule | P2 | **OPEN (policy)** — unchanged; PM index-policy backlog (P3-07 closure left literal-vs-generated policy open). |
| R4-IDX-005 SCRIPT_INDEX omits most scripts | P2 | **OPEN (policy)** — pattern unchanged; folded into R4-2026-IDX-04. |
| R4-IDX-006 SCRIPT_INDEX wrong header path | P3 | **HELD (pattern persists)** → R4-2026-IDX-04. |
| R4-IDX-007 README ADR count stale (14 vs 45) | P3 | **HELD** → R4-2026-IDX-03. |
| R4-IDX-008 ADR-0046 referenced, no file | P2 | **ESCALATED to P1** (now active revive-gate) → R4-2026-IDX-01. |
| R4-IDX-009 role reports not indexed | P3 | **OPEN (policy)** — unchanged. |
| R4-IDX-010 archive index incomplete | P3 | **PARTIAL** — archive table at docs/README:1283+ exists but is curated, not complete; unchanged. |

## Seeded-fact verification (PM)
- SCRIPT_INDEX at `helper_scripts/SCRIPT_INDEX.md` ✅ CONFIRMED; `docs/SCRIPT_INDEX.md` ✅ CONFIRMED ABSENT (only archive/old-report mentions).
- SPECIFICATION_REGISTER at `docs/governance_dev/SPECIFICATION_REGISTER.md` ✅ CONFIRMED (README:166,304); `docs/SPECIFICATION_REGISTER.md` ✅ CONFIRMED ABSENT (README:166 explicitly notes the old wrong path).
- ADR count: README §项目结构 claims "14" / docs/README "..0022" → ✅ REFUTED, actual 45 ADR IDs (0001-0045, 44 files). See R4-2026-IDX-03.
- Two Linux checkouts: NOT verifiable from Mac (no ssh executed; out of read-only index scope). Note as runtime/hygiene item for E3/PM, unverified by R4.
- Deployed engine `e9f01569` ancestor of frozen `187704f6`: TODO §0 line 11/47/500 cite engine binary = `e9f01569` PID 251791; this is INTERNALLY CONSISTENT with the baseline note (deployed binary ~2 commits behind frozen). No index/doc claims a deployed commit == frozen 187704f6 → no contradiction found. NOTE (PM): `git cat-file -t e9f01569` on Mac returns "Not a valid object name" — e9f01569 may be a binary content hash, not a git commit SHA, OR a Linux-only object; FA/MIT to verify via ssh.

## Minor / no-finding notes
- PM dispatch baseline path in my prompt (`docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-30--cold_audit_dispatch_baseline.md`) does NOT exist on disk; actual is `2026-05-17--cold_audit_baseline_freeze.md`. PM working file, out of SoT routing scope — noted, not a finding. [PM CORRECTION: the 2026-05-30 baseline note IS committed in d9128e22/187704f6 history; R4 read at a flaky moment.]
- `docs/README:1253` "19 個 Agent" ✅ ACCURATE (18 role dirs with profile.md + Operator = 19).
- Register `Last Updated 2026-05-27` is current relative to frozen baseline.
- I could not create this report file (R4 tools are read-only: Read/Grep/Glob/WebSearch; no Write/Edit). Report content delivered inline; PM/TW persisted to the report path.
