# CC — Root Principle Compliance Audit (campaign 2026-05-17, run 2026-05-30)

**Auditor**: CC (Compliance Checker) — cold READ-ONLY adversarial pass, Phase 2 of PM cold audit.
**Intended baseline**: frozen commit `187704f6`, branch main.
**Observed working-copy HEAD**: `9c3d5593` (v85 PM checkpoint). FACT: `187704f6` IS an ancestor of HEAD; only **4 commits** separate them (`9c3d5593`, `8d1890a8`, `14361a66`, `d9128e22`) and **all four are `docs(todo+reports) … [skip ci]`** — i.e. **zero source/Rust/Python/SQL/TOML change** between baseline and HEAD. The audited **source tree is therefore identical to the baseline**; the worktree delta is TODO/report docs only (operator WIP). I audited the tree as-is.
**Run**: 2026-05-30.

---

## VERDICT: **B (conditional compliance)** — P0 = 0 · P1 = 1 · P2 = 1 · P3 = 0

Materially compliant on the load-bearing surfaces (Authority Chain, 5-gate live boundary, LiveDemo non-downgrade, Decision Lease, GUI fake-success guards, Bybit retCode fail-closed). One **carry-forward governance P1** (ADR-0046 phantom funding_arb revive-gate) and one **P2** (Bybit-only wording vs registered read-only venue stubs — prior CC-RP-003 class). Prior CC P1s (CC-RP-001 cancel-all, CC-RP-004 ADR register drift) **VERIFIED FIXED at source this run**.

### Honesty note (principle #10/#9 — full disclosure of a corrected false start)
An **earlier draft of this same report file asserted a P0 "skeleton checkout / no source exists."** That was **WRONG** — a cwd artifact: my first discovery batch ran from the parent dir `/Users/ncyu/Projects/TradeBot` (no `.git`), not the real repo root `/Users/ncyu/Projects/TradeBot/srv` (`.git` + `rust/` 580 `.rs` + `program_code/` 10,649 `.py` + full 269-line `CLAUDE.md` + 136 KB `TODO.md`). The closure-archive "14 files MISSING" was likewise a path-mapping error (archive used a hypothetical `python/openclaw/...` layout; this repo uses `program_code/.../control_api_v1/app/*.py` + `rust/openclaw_{core,engine}/src/...`). **That P0 is retracted and overwritten by this version.** Recording it because honest-reporting requires it, and because it is itself a process lesson (verify cwd/`git rev-parse --show-toplevel` before declaring absence).

---

## Deep-dive findings (grep-verified at enforcement point this run)

### #2 Authority Chain — PASS (no bypass / no Python fake-success on the live cancel path)
- **FACT** Python live cancel-all REST is **gone**: `…/app/live_session_routes.py:686-690` — "P1-03：原 `_sweep_live_orphan_orders`（live 槽 Python REST cancel-all）已移除。Live 取消掛單改走 Rust IPC `cancel_all_orders {engine:"live"}` … live 寫入（含風險收縮取消單）必須過 Rust 執行權威。" This is the exact file the prior CC-RP-001 P1 flagged → **fix held**. The live REST fallback is now a hard `HTTPException(409, _LIVE_REST_FALLBACK_DISABLED_DETAIL)` (live_session_routes.py:605) telling the operator to restore signed live_reserved + go through the Rust pipeline (L576-585).
- **FACT** the live stop path now calls the IPC route: `…/app/live_session_endpoints.py:351-374` issues `(IPC cancel_all_orders, engine=live, settleCoin=USDT) BEFORE close` with comment "CC/operator 裁定 live 寫入必過 Rust"; on IPC failure it records `{"skipped":True,"reason":"cancel_all_orders_failed"}` and appends to `errors` (→ partial_failure, not silent success).
- **FACT** Rust side routes the IPC through PipelineCommand with fail-closed handling: `ipc_server/dispatch.rs:210` `"cancel_all_orders" =>` builds `PipelineCommand::CancelAllOrders{…}` (L230); `event_consumer/loop_handlers.rs:653` intercepts it; paper mode = log-only (no client, L663-664), unknown category = "skipped fail-closed" (L679); the sync facade in `event_consumer/handlers/mod.rs:72-83` panics-by-assert if reached un-intercepted ("should be intercepted in handle_pipeline_command") — i.e. it cannot silently no-op. `order_manager.rs:509` documents the `cancel_all_orders("linear", settleCoin="USDT")` semantics.
- **Evidence cmd**: `rg -n "cancel-all|cancel_all|_LIVE_REST_FALLBACK_DISABLED" program_code/.../app/{live_session_routes,live_session_endpoints,bybit_rest_client}.py` ; `rg -n "CancelAllOrders|cancel_all_orders" rust/openclaw_engine/src`.
- **INFERENCE**: full StrategySignal→StrategistDecision→GuardianVerdict→ExecutionPlan→Lease→ExecutionReport chain not exhaustively re-walked this run, but (a) the previously-flagged Python bypass is closed, (b) Decision-Lease gating is present (step_4_5_dispatch.rs lease acquire/release), (c) the IPC path is fail-closed at every branch. No new fake-lineage found.

### #3 Live / LiveDemo boundary — PASS (5-gate documented + enforced; LiveDemo NOT treated as low-risk; execution_authority is denylist-not-auth per principle)
- **FACT** the 5 gates are enumerated and enforced across the Python auth/preflight layer:
  - `strategist_promote_routes.py:37-38, 493-494` documents the full 5-gate set "Operator + live_reserved + OPENCLAW_ALLOW_MAINNET + secret slot + authorization.json HMAC/expiry/env_allowed".
  - `live_reserved` is checked as an **exact global-mode** value, not substring: `state_compiler.py:210/266/318/538` compare `global_execution_mode_switch == "live_reserved"` (equality) and `live_session_routes.py:585` requires "Global Mode exactly live_reserved" → consistent with prior P1-02 substring-fix.
  - Mainnet: `bybit_rest_client.py:253` `if is_mainnet and os.environ.get("OPENCLAW_ALLOW_MAINNET","") != "1":` → hard block (L257-260, `guard:"OPENCLAW_ALLOW_MAINNET"`).
  - Secret slot + signed authorization.json: enforced in the live-auth path (governance_hub live-candidate review reads `authorization.json` scope; `live_preflight.py` / `executor_routes.py` Gate sequence).
- **FACT** LiveDemo is **explicitly live-grade, NOT downgraded**: `executor_routes.py:188,226` and `live_preflight.py:257` show LiveDemo skips **only** Gate 3 (OPENCLAW_ALLOW_MAINNET — correct, since LiveDemo hits a demo endpoint, not mainnet) and **comment cites "per CLAUDE.md §四"**. All other gates (operator, live_reserved, secret slot, signed authorization.json, TTL, risk, audit) still apply. `live_demo` appears in `ALLOWED_SLOTS` (settings_routes.py:82) and engine-mode allowlists (risk_routes.py:894) as a first-class live-grade engine, NOT a relaxed demo. No `skip/bypass/relax/low-risk` shortcut for `live_demo` beyond the documented Gate-3-only skip. Matches CLAUDE §四 L86-87 and memory `feedback_live_no_degradation_by_endpoint`. **Compliant.**
- **FACT** `execution_authority` in Rust is a denylist/string-constant surface, used as metadata not as the gate: `claude_teacher/applier.rs:212` lists `"execution_authority"` as a denied/controlled field name; `tick_pipeline/mod.rs:223` notes cancel ops "不需 Decision Lease，且 execution_authority revoke 後仍須可用（cancel 不開新倉）"; the real gate is the `LiveActive` authority check + signed authorization. Exactly as CLAUDE §四 L91-92 mandates. **Compliant.**
- **Evidence cmd**: `rg -n "live_reserved|OPENCLAW_ALLOW_MAINNET|authorization\.json|5-gate|live_demo|LiveDemo" program_code/.../app/` ; `rg -n "execution_authority" rust/openclaw_engine/src`.

### #7 GUI fake-success — PASS (live mutation surfaces classify real outcome, no synthetic green)
- **FACT** Python live route computes a real sync flag and partial-failure path rather than always-200: `…/app/live_session_routes.py` has `rust_synced = bool(...)` and `partial_failure` handling (L686+ region). Front-end `…/static/live-session.js` uses `classifyLiveMutation` to avoid showing green on residual error — matches closure P1-04/P2-15 ("residual 不顯綠" persistent red banner).
- **Evidence cmd**: `rg -rln "classifyLiveMutation" program_code` → `…/static/live-session.js` ; `rg -n "rust_synced|partial_failure" …/app/live_session_routes.py`.
- **INFERENCE**: not all ~93 GUI write endpoints re-audited this run; the high-risk live-mutation path is compliant. No new fake-success surface surfaced.

### Decision Lease + Bybit retCode (invariants 2 & 7) — PASS (spot-checked)
- **FACT** `decision_lease_required(&self) -> bool { true }` (rust engine) → lease is structurally required.
- **FACT** Bybit checked helpers fail closed on nonzero `retCode` via `into_result()` (consistent with prior run + closure P1-07); no hidden retry-to-fill found in scope.

---

## FINDINGS (open)

### P1-CC-A — ADR-0046 cited as the funding_arb revival gate but the ADR file + register row are ABSENT (governance integrity #8 / #10)
- **Severity**: **P1** (governance/traceability; latent — funding_arb is **Retired closed** per AMD-2026-05-26-01 with three-env TOML `active=false` hard-lock + `#[deprecated]` marker + runtime fail-closed guard, so **no live-money path is active**, but a future revive would cite governance cover that does not exist). Tag: **FACT** (absence directly verified + independently corroborated by R4 today).
- **Affected paths**:
  - **Citation (FACT)**: `TODO.md` §6 row 5 — funding_arb revive path stated as "AMD amendment + **ADR-0046 Accepted** + 5-gate + Stage 0R replay preflight" (`rg -n "ADR-0046 Accepted" TODO.md`). The three `settings/strategy_params_{live,demo,paper}.toml` revive comments say "AMD amendment + **n Accepted** + 5-gate" (they use the placeholder name `n`, not ADR-0046) — so there is **internal inconsistency**: TODO calls the revive ADR "ADR-0046", the TOMLs call it "n (Proposed)".
  - **Absence (FACT)**: `ls docs/adr/` ends at `0045-m4-hypothesis-discovery-governance.md` — there is **no `0046-*.md`**. `docs/governance_dev/SPECIFICATION_REGISTER.md` "Active ADR" list ends at **ADR-0045 + n (PROPOSED)** — **no ADR-0046 row**. ADR-0018 (funding-arb-v2-deprecation-watch) names the revive slot "`n (Proposed)` future redesign", not ADR-0046.
- **Evidence cmd**: `ls docs/adr/ | grep 0046` (empty) ; `rg -n "ADR-0046 Accepted" TODO.md` (1 hit — the revive gate) ; `rg -n "0046" docs/governance_dev/SPECIFICATION_REGISTER.md` (empty) ; `rg -n "n Accepted|n \(Proposed\)" settings/strategy_params_*.toml docs/adr/0018-*.md`.
- **Impact**: The funding_arb revival gate references an ADR (**ADR-0046**) that **does not exist as a file or register row**, while the canonical TOML lock + ADR-0018 name the slot "n (Proposed)". A future funding_arb re-activation invoking "ADR-0046 Accepted" would satisfy a **phantom gate**, and the naming split (ADR-0046 vs n) makes the gate ambiguous/unauditable. Violates principle #8 (every decision reconstructable) and #10 (adversarial verifiability). Same *class* as the prior CC-RP-004 register-drift P1, recurring as a forward-referenced ADR number.
- **Why real, not false-positive**: `ls docs/adr/` provably ends at 0045; the register's Active-ADR enumeration provably ends at 0045+n; the TODO revive gate provably says "ADR-0046 Accepted"; and an **independent role (R4) flagged the identical gap in its 2026-05-30 cold report** — cross-corroborated, not a CC artifact. (Note: a raw `rg ADR-0046 .` returns many lines, but on inspection those are display-mangled matches of `ADR-0018`/`n` text plus the TODO revive gate — the only *substantive* ADR-0046 citation is the TODO revive gate; no `docs/adr/0046` and no register row exist.)
- **Fix direction**: reconcile the naming to ONE identifier. Either (a) the revive ADR is genuinely "ADR-0046" → **author `docs/adr/0046-*.md`** (funding_arb revival gate, QC math/edge preconditions) + add the SPECIFICATION_REGISTER row + repoint the three TOMLs from "n" to "ADR-0046"; or (b) the revive slot is "n (Proposed)" (as TOML + ADR-0018 say) → **strike the "ADR-0046 Accepted" wording from TODO §6 row 5** and use "n Accepted". Do not leave a revive gate citing a non-existent ADR number. Extend the P1-15 register path-existence lint to also catch forward-referenced ADR numbers in TODO/specs.
- **Fix owner role**: R4 + PA (+ QC for the revival math content if ADR is authored). **Verifier role**: R4 + CC.

### P2-CC-B — Bybit-only boundary wording vs registered non-Bybit read-only venue stubs (carry-forward CC-RP-003 class; principle #8 clarity)
- **Severity**: **P2** (governance clarity; no active non-Bybit trading — `order_router` defers Binance). Tag: **INFERENCE** (carry-forward from prior run; closure P2-16 claims CLAUDE/README wording was reconciled to "Bybit-only execution; ADR-approved non-Bybit read-only data exception"; I did not re-diff the wording vs `asset_venue.rs` stubs this run).
- **Affected paths to re-confirm**: `CLAUDE.md` §一/L27-region, `README.md`, `docs/adr/0036-adr-0009-bybit-binance-amendment.md` (Binance read-only amendment — FACT present), `rust/openclaw_types/src/asset_venue.rs`, `rust/openclaw_engine/src/order_router.rs` (Binance → `VenueDeferred`).
- **Impact**: residual ambiguity over whether "Bybit-only" means execution-only or all exchange integration. Low risk; track to closure.
- **Fix owner role**: R4 + TW. **Verifier role**: R4 + CC + BB.

---

## Per-principle / per-invariant status THIS RUN

| # | Principle | Status | Evidence |
|---|---|---|---|
| 1 | single write entry | **PASS** | Python live cancel-all removed (live_session_routes.py:686); sole path = Rust IPC `cancel_all_orders` |
| 2 | read/write separation | **PASS** | same; GUI live mutations classify real outcome (classifyLiveMutation) |
| 3 | AI≠command / Decision Lease | **PASS** | `decision_lease_required → true`; lease/authority gating present |
| 4 | strategy can't bypass Guardian | **PASS (light)** | `guardian.rs`/`guardian_agent.py` present; no bypass found (not exhaustively re-walked) |
| 5 | survival>profit | **PASS (carry)** | prior PASS; reduce-only close retains survival-exception retry |
| 6 | fail-closed | **PASS** | Bybit retCode → into_result() error; auth gates fail-closed |
| 7 | learning≠live | **PASS (carry)** | P1-10 paper→demo promotion frozen (prior verified) |
| 8 | explainable/governance | **AT RISK (P1+P2)** | **P1-CC-A ADR-0046 phantom**; P2-CC-B wording |
| 9 | disaster double-rail | **PASS (carry)** | local StopManager dual-rail + exchange conditional (prior) |
| 10 | cognitive honesty | **PASS w/ note** | self-corrected a false-start P0; ADR-0046 caught + cross-corroborated |
| 11 | max autonomy in P0/P1 | **PASS (carry)** | no capability-throttling violation |
| 12 | continuous evolution | **PASS (carry)** | evidence lanes intact (trading.fills V094) |
| 13 | AI cost awareness | **PASS (carry)** | P1-13 paid-ledger fail-closed (prior) |
| 14 | zero-external-cost runnable | **PASS (carry)** | Route A defaults local/free (Ollama) |
| 15 | multi-agent | **PASS** | FACT: 3 sibling Phase-2 reports (BB/R4/TW) landed 2026-05-30; role docs present |
| 16 | portfolio risk | **PASS (carry)** | no new bypass |

**Hard boundaries (CLAUDE §四 L79-100)**: 5-gate live = **enforced** (live_reserved exact + operator + MAINNET + secret slot + signed authorization.json); LiveDemo non-downgrade = **enforced** (L332-333); `execution_authority` denylist-not-auth = **honored**; Bybit retCode fail-closed = **enforced**; "do not fake … lineage/healthcheck/test results" = no violation found (and the repo's own `8d1890a8` "revert hallucinated V104 already-applied claim" shows the project self-polices this boundary). **0 hard boundaries touched.**

**9 safety invariants (TODO §5 dashboard / DOC-08 §12)**: load-bearing ones verified via the deep-dives this run — Inv-2 (lease before execution) PASS (`decision_lease_id` + `release_decision_lease_for_governance` in step_4_5_dispatch.rs), Inv-3 (report→fills; evidence in trading.fills V094) PASS-by-prior, Inv-5 (auth expiry→shutdown) auth-gate present, Inv-6 (Mainnet needs MAINNET=1) PASS (bybit_rest_client.py:253-260 hard guard), Inv-7 (retCode fail-closed) PASS (account_manager.rs:270/345, instrument_info.rs:206/351 all `if resp.ret_code != 0 { return Err }`), **Inv-8 (reconciler mismatch → defensive degrade) PASS this run** (reconciler_tests.rs:75-88 + earn_reconciliation.rs HEALTH_DEGRADED), Inv-9 (operator + live_reserved both required) PASS (require_role("operator") + exact live_reserved). Inv-1 (pre-trade replay must-on) + Inv-4 (risk-degrade auto-stop) **carry-forward / not re-grepped 1-by-1** — flag for re-run if full-invariant certification is required.

---

## New 2026-05-29/30 work — compliance read (per TODO §0 v85)
- **FACT (from TODO §0 + git log)**: 110017 D1/D2 reconciler, 4-track, basis_panel writer (V115, max=115), risk.rs split, gap-cleanup are **DEPLOYED** into engine PID 251791 (binary SHA `e9f01569`), verified by build-commit `ec995160` ancestry; `8d1890a8` corrected the only hallucination (a false "V104 already-applied" claim — now reverted; V104 confirmed a free migration hole to be written fresh, not silently applied). **No fake-deploy / no migration drift** survived into the ledger after the correction.
- **FA independent gap audit (TODO L511)**: "真實閉環 ✅ 0 BLOCKER / 0 安全不變量違反 / 0 overstated DONE"; adversarial chain caught 3 real bugs pre-merge (BB D2 real-money mis-delete, QC silent-stat, E1 btc_lead_lag prod bug) — corroborates that the new-work review chain was not skipped.
- **FACT (reconciler degrade path verified this run)**: the position reconciler escalates RiskLevel on persistent drift — `rust/openclaw_engine/src/event_consumer/tests/reconciler_tests.rs:75-88` drives `Normal → Cautious → Reduced → Defensive` on "persistent drift ≥3 cycles" and asserts `snapshot_level() == RiskLevel::Defensive`; IPC `run_reconciler_escalate`/`de_escalate` commands exist. The Earn reconciler (`cron/earn_reconciliation.rs`) emits `[HEALTH_WARN]`/`[HEALTH_DEGRADED]` + V100 `reconciliation_status='mismatch'` on ≥3-day cumulative diff, with the self-fail (Bybit timeout/PG error) explicitly **not** counted to avoid double-punishment. This satisfies invariant #8 (reconcile mismatch → defensive degrade) — **PASS**, and is a *new-work strengthening* not a regression.
- **CC residual**: risk.rs split internals not exhaustively re-walked, but the split is into well-named per-concern modules (`risk_checks.rs`, `risk_cusum.rs`, `config/risk_config_{regime,advanced,fast_track,cost_edge}.rs`) with lock tests (`risk_checks_per_strategy_tests.rs` includes a test asserting **retired funding_arb must not live in RiskConfig overrides** + `RiskConfig::validate()` must PASS) — consistent with FA's "0 安全不變量違反" finding. No gate-weakening observed.

---

## Did prior CC remediation hold?
**YES for the items re-grepped this run.** CC-RP-001 (Python live cancel-all) → **fixed** (removed; Rust IPC + LiveActive authority). CC-RP-004 (ADR-0036..0041 register dead paths) → **fixed** (all 6 register paths resolve to real files; `ls docs/adr/` confirms 0036-0041 exist). CC-RP-002 (`learning.close_maker_audit`) → **reclassified as intended** (canonical evidence in trading.fills V094, no dead table by design). CC-RP-003 → carried as P2-CC-B. Net: prior remediation **held** where verifiable; the *new* governance gap is ADR-0046 (a recurrence of the same register-drift class on a forward-referenced ADR).

---

## Blockers / escalation
- **P1-CC-A (ADR-0046 phantom funding_arb revive-gate) → operator/PM governance decision + R4/PA**: author ADR-0046 (+register row) or remove the citation. Not a deploy blocker for current state (funding_arb dormant) but **must clear before any funding_arb revival**. Cross-ref R4's 2026-05-30 index report (same finding) — recommend R4 own the fix, CC verify.
- **P2-CC-B (Bybit-only wording) → R4 + TW**: re-confirm CLAUDE/README wording vs asset_venue stubs (closure P2-16 claims done).
- **Optional re-run scope (not blocking)**: full 9-invariant 1-by-1 grep + D1/D2 reconciler degrade-to-paper + risk.rs-split gate-preservation, if a hard A-grade certification is wanted. This run gives **B (conditional)** with high confidence on the live-money-critical surfaces.
- No `ssh trade-core` runtime mutation performed (READ-ONLY honored).

**Bottom line**: P0 = 0. Live-money-critical compliance (authority chain, 5-gate, LiveDemo non-downgrade, fake-success guards, retCode fail-closed) is **materially enforced and prior CC fixes held**. The single open P1 is a governance-traceability gap (ADR-0046), independently corroborated by R4 — needs an operator/R4 decision, not code on the hot path.
