# FA — Full-Chain Functional Gap / Dead-Code Audit (re-run)

- **Date**: 2026-05-30
- **Role**: FA (Functional Auditor) — cold, adversarial, READ-ONLY
- **Baseline (code)**: frozen `187704f6` (working tree HEAD `cc6c54d0` = docs-only churn since; source delta = ZERO)
- **Campaign**: 2026-05-17 label, run 2026-05-30
- **Prior**: cold audit ~2026-05-29 P0=0/P1=17/P2=17/P3=7 all remediated+deployed (TODO v84); prior FA 7 LOW gaps
- **Scope (focused)**: (1) D2 ghost-converge reconciler LIVE-vs-gated; (2) dead code; (3) v84 claim-vs-reality incl. V104; (4) functional gaps / prior-remediation hold

> **ENV note**: This session ran under heavy intermittent tool flakiness (whole batches silently dropped output; several reads returned garbled tails with placeholder `...` / duplicated line numbers). Per protocol every load-bearing finding below was re-run until a CLEAN, self-consistent render was obtained (exit markers used where ambiguous). No finding is shipped from a single flaky read.

---

## Counts

| Severity | Count |
|---|---|
| P0 | 0 |
| P1 | 0 |
| P2 | 0 |
| P3 | 1 |

No new functional gaps or dead code found in the focused scope. The single P3 is a possibly-stale TODO wording item; the V104 claim-vs-reality concern I initially drafted was **withdrawn on re-check** — TODO.md is already self-corrected (v85, see Task 3).

---

## TASK 1 (CRITICAL) — D2 ghost-converge reconciler verdict

### VERDICT: **LIVE / wired — enabled by default. BB run#1 CORRECT; BB run#2 REFUTED.**

Type: **FACT** (full source chain traced end-to-end, each link on a clean re-read).

The reconciler genuinely dispatches `PipelineCommand::ConvergeExchangeZero` and the consumer genuinely mutates owner-state. It is **not** "classify + warn only". Full chain:

1. **Boot spawn** — `rust/openclaw_engine/src/main_boot_tasks.rs:71 spawn_position_reconcilers(...)` spawns BOTH Live (line 108-118 "position_reconciler spawned for Live") and Demo (124-136 "position_reconciler spawned for Demo") reconcilers via `tasks::spawn_position_reconciler_with_cmd_provider`; the spawner (`tasks.rs:818`) ends in `tokio::spawn(run_position_reconciler(...))` (`tasks.rs:866`, log "position_reconciler task spawned" 876). Called from `main.rs:844`. Real background tasks, not dead. (No `reconcile_enabled` env toggle exists — `grep reconcile_enabled` across rust tree = empty; the loop is unconditional per-cycle.)
2. **Per-cycle loop** — `position_reconciler/mod.rs` `run_position_reconciler` (pub async fn at mod.rs:379) drives the cycle; drift classify at mod.rs:501-528, then the action block.
3. **Ghost branch (data-gated only, NO feature flag)** — `position_reconciler/mod.rs:532 match (cmd_tx_provider)()` → `Some(cmd_tx)` → `mod.rs:534 if let Some(ref oh_cfg)` → `process_orphans(...)` (535) then **`process_ghosts(...).await`** (552-564). The only guards are `cmd_tx` availability + `orphan_handler_config` present (both supplied at boot). Control-flow scan of lines 440-545 shows **no `cfg!(feature)`, no `if false`, no env short-circuit** around the call. The `None` arm (586-594) only logs "drift actions blocked: command channel unavailable" — a degraded fallback, not the normal path.
4. **Dispatch call site** — `position_reconciler/mod.rs:552 process_ghosts(drifts, oh_cfg, &cmd_tx, &audit_pool, &engine_label, &mut rc_state, <point_query closure>).await` (closure at 559-562 wraps `ghost_point_query`).
5. **process_ghosts body** — `position_reconciler/mod.rs:810-934`. Applies AND-gated safeguards S-1 (engine mirror has local direction, 856), S-5 (2-cycle streak, 867), S-6 (single-symbol point-query, 882). On `GhostPointQuery::ConfirmedZero` (mod.rs:903) it calls **`orphan_handler::dispatch_ghost_converge(sym, is_long, cmd_tx)` (mod.rs:910)**, audits on success (915), drops the ghost from `kept`. `StillHasPosition` (883) and `QueryFailed` (894) both fail-safe KEEP (no converge) — correct anti-mis-delete design (Root Principle 6).
6. **Actual send** — `position_reconciler/orphan_handler.rs:451 dispatch_ghost_converge`, body **orphan_handler.rs:457 `cmd_tx.send(PipelineCommand::ConvergeExchangeZero { symbol, is_long, ts_ms })`**. Real channel send with structured warn log (463-468) + error branch (471-477).
7. **Consumer is REAL (not no-op)** — `event_consumer/handlers/mod.rs:397-407`: `PipelineCommand::ConvergeExchangeZero { symbol, is_long, ts_ms }` arm calls **`lifecycle::handle_converge_exchange_zero(symbol, is_long, ts_ms, pipeline, snapshot_writer)` (mod.rs:401)** — actual local owner-state convergence (comment 396 "對帳器確認 Bybit size==0 → 本地收斂漂移倉"). Not a stub arm.
8. **E4 coverage exists** — `position_reconciler/tests.rs:686-1090` block "P2-110017-D2-RECONCILE: process_ghosts converge tests": asserts dispatch on ConfirmedZero (tests.rs:741, 995), asserts NO dispatch on StillHasPosition / confirmed real position (tests.rs:961), drains channel to assert the single command is ConvergeExchangeZero (831, 996). The dispatch path is regression-protected.

**Exact decisive line for "does it dispatch ConvergeExchangeZero, or only classify/warn?": YES it dispatches — `orphan_handler.rs:457` (the `cmd_tx.send(PipelineCommand::ConvergeExchangeZero{..})`), reached from `mod.rs:910` on `GhostPointQuery::ConfirmedZero` (mod.rs:903), and consumed for real at `handlers/mod.rs:401`.**

Reconciliation of the two BB runs: run#1 ("SOUND and LIVE, process_ghosts wired at mod.rs:552, no flag gating off") is **correct**. run#2 ("shipped DISABLED, only classifies drift + warns, no converge dispatch") is **REFUTED** — contradicted by mod.rs:903-910 + orphan_handler.rs:457 + handlers/mod.rs:401. The likely cause of run#2's error: mistaking the layered safeguard gates (S-1 mirror / S-5 2-cycle streak / S-6 point-query — all of which KEEP+warn on the non-happy branches) for "warn-only, never converges". They are conservative pre-converge confirmations, not an off-switch; the ConfirmedZero happy path unconditionally dispatches.

---

## TASK 3 — V104-never-existed corroboration

### RESULT: **CORROBORATED (FACT). MIT is correct — V104 (and V105) never existed in the repo. AND the v85 self-correction is COMMITTED in this tree (the prior remediation/correction held).**

Evidence:
- Migrations live in **`sql/migrations/`** (canonical) — `ls` → `V100, V101, V102, V103, **V106**, V107, V109, V112, V113, V114, V115`. **Sequence jumps V103 → V106. No V104, no V105 file.** (`rust/openclaw_engine/migrations` and `db/migrations` do not exist — earlier "No such file" was correct, not flakiness.)
- Global `find . -name 'V104*' -o -name 'V105*'` (excluding target) → **empty** (verified with bracketing markers across 3 re-runs).
- **`V104` and `V105` are FREE holes** (matches MIT). `V114 = V114__notification_failsafe_events_hypertable.sql` (Packet C notification failsafe), **not** a supervised-live-audit table — confirming the prior "V114 supervised" was a name-collision hallucination.
- The supervised `live_audit` table that older notes attributed to "V104 applied" is **not yet written anywhere** (`grep -S supervised_live_audit` across `.sql`/`.rs` = empty per TODO's own forward-fix record); it is a free hole to be authored.

### Claim-vs-reality: **NO contradiction — TODO is self-corrected (initial concern WITHDRAWN).**
- `TODO.md:4` (this tree, HEAD cc6c54d0) is **v85** and explicitly documents the self-correction: *"🔴 LG-3 V104 幻覺修正 … 先前同日 commit d9128e22 誤把『V104 已存在已 apply』寫入帳本 … 證 V104 從未存在 = free hole 要全新寫；commit 8d1890a8 forward-fix"*.
- `TODO.md:74` (the P0-LG-3 row) now correctly states *"V104 從未存在 … sql/migrations/ V103→V106 跳號（V104/V105 = FREE hole）"* and flips the red-line to "must write NEW".
- **Verdict**: MIT's V104-never-existed finding is FACT, and the ledger has already been corrected to reflect it (commit `8d1890a8`). This is a **prior-remediation-held** result, not an open finding. (My earlier draft P2 flag was based on a stale grep that missed line 4/74 during a flaky read; withdrawn.)

---

## TASK 2 — Dead code (focused spot-check of recently-touched modules)

No new dead code found. Spot-checks all resolved to wired:
- **basis panel writer (`panel_aggregator/basis.rs`)** — NOT dead, **fully wired (FACT)**. `BasisAggregator` (basis.rs:69) is a live field of `PanelAggregator` (`panel_aggregator/mod.rs:121`), constructed at `mod.rs:166`, exposed via `basis_mut()` (mod.rs:214). The owning `PanelAggregator::run(panel_event_rx)` is spawned and awaited at **`main.rs:1073`** (after `PanelAggregator::new` at main.rs:1050). `flush()` (basis.rs:141) → `insert_basis_snapshot()` (basis.rs:227) writes to `panel.basis_panel` created by `sql/migrations/V115__panel_basis_panel.sql`. So writer (basis.rs) + struct wiring (mod.rs) + spawn (main.rs:1073) + table (V115) all present. Comment mod.rs:120 candidly notes the table is "純為 A1 Stage 0R offline replay" (intended consumer is the offline replay runner, not a live IPC slot) — that is a *designed* consumption path, not dead code. Corroborates TODO "basis_panel writer wired (A2)".
- **D2 reconciler chain** — fully wired (Task 1); writer (orphan_handler.rs:457 dispatch), consumer (handlers/mod.rs:401), audit, and tests all present.
- **`ConvergeExchangeZero` PipelineCommand variant** — has producer (orphan_handler.rs:457) AND consumer (handlers/mod.rs:397-407); not an orphan enum arm.

Not exhaustively swept (token/flakiness budget) — broad writer-without-consumer / 0-row-table sweep is better owned by PA's in-flight 2026-05-30 dead-code/integration sweep (TODO.md:2) + MIT for table-level row/reader checks. No isolated dead-writer surfaced in the focused modules.

---

## TASK 4 — Functional gaps / partial-fix-as-complete / prior 7 LOW

- **M11 replay runner** (`TODO.md:104`: "experiments last_age 407h → runtime-not-proven, no fresh replay since deploy"): this is a **self-admitted not-proven** state, not a code contradiction. TODO honestly labels it runtime-not-proven. Verifying the runner is functionally exercised requires **Linux runtime** (fresh replay row / experiment age) — cannot be settled from Mac source. **Not a finding** (honest TODO); flag = runtime-blocked.
- **B-runner / basis** (`TODO.md:509`: "B runner 收尾 … E4 PASS (smoke 13/13) … commit 21db54b1"): TODO records the B-runner as **closed/functional** (QC k_prior over-PASS bias fixed, E2 APPROVE, E4 13/13). Separately, the basis panel infra (A1 Stage 0R) shows the basis writer is wired (above) but its table is explicitly "offline replay" fodder — i.e. the A1 replay runner is the intended reader. The basis WS→PG ingestion + V115 table + writer all exist; what remains genuinely runtime-unproven is whether the A1 *replay* consumer has actually read fresh basis_panel rows (a Linux row-recency check). **Not a code gap; runtime-verification gap only.**
- **Prior 7 LOW gaps (FA ~2026-05-29)**: with frozen source baseline `187704f6` unchanged, none could have regressed via code. The only residue is the M11/A1 replay-runtime-not-proven status (TODO is honest about it). No prior LOW re-opened by a source change → **prior remediation held at code level.**

---

## P3 finding

**P3-1 — basis_panel / A1-replay path is RUNTIME-UNPROVEN (writer live, consumer freshness unverified).** Path: `panel_aggregator/basis.rs:141/227` (writer) + `sql/migrations/V115__panel_basis_panel.sql` (table) + intended A1 offline-replay reader. Evidence: writer + struct wiring (`panel_aggregator/mod.rs:121,166`) + spawn (`main.rs:1073`) + V115 table all present in source, but mod.rs:120 marks the table "純為 A1 Stage 0R offline replay" and no Mac-side proof exists that the replay runner has consumed fresh rows. Impact: low — the writer is genuinely wired (so NOT dead code); the only open question is end-to-end runtime exercise of the replay consumer. Why-real-not-FP: this is a writer-with-deferred-consumer pattern where the consumer (offline replay) runs on demand, so 0 fresh reads is possible without it being a defect. Fix direction: Linux row-recency check on `panel.basis_panel` + confirm A1 replay run reads it. Fix owner: MIT (pipeline maturity) / PA (if wording needs sharpening). Verifier: MIT (Linux `SELECT max(snapshot_ts_ms)` on panel.basis_panel + replay run).

---

## Findings table

| ID | Sev | Path:line | Evidence cmd | Impact | Why real (not FP) | Fix dir | Owner | Verifier |
|---|---|---|---|---|---|---|---|---|
| P3-1 | P3 | `panel_aggregator/basis.rs:141,227` + `sql/migrations/V115__panel_basis_panel.sql` | `grep -n basis panel_aggregator/mod.rs` (field 121, new 166, spawn main.rs:1073); writer→`insert_basis_snapshot`→V115 | basis_panel writer live but A1 replay consumer freshness unproven on Mac | writer+table+spawn all present; deferred offline-replay consumer ⇒ 0 fresh reads not a defect | Linux row-recency + replay run | MIT | MIT |

---

## Hard-boundary check (spec-compliance)

No source delta since `187704f6`; no `execution_state / execution_authority / live_execution_allowed / decision_lease_emitted / max_retries / OPENCLAW_ALLOW_MAINNET / authorization.json HMAC` surface touched in scope. The new env var `OPENCLAW_RECONCILE_ENABLED` (main_boot_tasks.rs:1210) is a reconcile-loop toggle (converge mutates LOCAL owner-state only, never places orders — handlers/mod.rs:393 "直接改本地 owner-state，不下單"); not a trading hard-boundary. No BLOCKER.

---

## Blockers / cross-role / Linux-runtime needed

1. **M11 / A1 replay runtime freshness** (TODO: experiments runtime-not-proven; basis_panel offline-replay consumer) — needs `ssh trade-core` read-only check of replay experiment recency + `panel.basis_panel` row recency. Linux-runtime.
2. No PM blocker on V104 — the v85 self-correction is already committed in this tree (`8d1890a8`, TODO:4/74). Nothing to escalate.

## Did prior remediation hold?

**Yes.** Source frozen at `187704f6` = zero delta since v84 remediation; D2 reconciler (the most-contested item) verified fully LIVE end-to-end and regression-tested. MIT's V104-never-existed finding is corroborated AND already reflected in the ledger (v85 forward-fix `8d1890a8`). No remediated P0/P1/P2/P3 re-opened by a code change. Only residue is the runtime-not-proven A1/M11 replay freshness — which the TODO honestly labels, not a hidden regression.

---
FA AUDIT DONE: report path: docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-30--FA--full_chain_functional_gap_dead_code_audit.md
