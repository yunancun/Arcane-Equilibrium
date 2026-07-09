# Startup Prompt

Paste this prompt into a new Codex session from `/Users/ncyu/Projects/TradeBot`
to start the foreground source-development loop.

```text
You are Codex in /Users/ncyu/Projects/TradeBot. First read srv/AGENTS.md, then
treat /Users/ncyu/Projects/TradeBot/srv as the authoritative repo root. Follow
the mandatory PM boot order in srv/AGENTS.md exactly.

Goal: run a foreground, bounded, self-repeating Codex source-development loop
for the scanner-driven AI/ML ALR stub at:
srv/docs/CCAgentWorkSpace/PM/workspace/ai_ml_todo_stub/2026-07-09--scanner_driven_alr/

Boundary label: SOURCE_ONLY_OFFLINE_P0_P1.

This is a Codex source-development loop, not an application runtime loop. It may
repeat local source/test/report/commit iterations in this Codex session. It must
not create or modify cron, daemon, launchd, systemd, sidecar, scheduler,
background loop, scanner cadence, runtime service, runtime config, PG state, IPC
writer/listener, Bybit/official MCP calls, exchange private/public reads,
orders/probes/cancel/modify, Decision Lease, Cost Gate, model serving,
promotion, _latest, or live/mainnet authority.

Before acting:
1. Read the stub files README.md, manifest.json, queue.md, boundaries.md,
   loop_contract.md, retention_guardian_contract.md, and startup_prompt.md.
2. Read the source reports linked by README.md.
3. Run git status --short --branch and preserve unrelated dirty changes.
4. Treat this stub as PM-owned AI/ML queue, not root TODO authority unless PM
   explicitly imports a row. Root TODO.md remains active blocker truth.
5. Do not inherit any current trading P0 candidate context, standing Demo
   authorization, previous no-order public GET approval, prior BB exact-scope
   approval, operator-review-ready artifact, or cached exchange credential as
   authorization for ALR P0/P1.

Loop logic:
1. Recover the latest ALR state packet if one exists.
2. Select exactly one work item from queue.md: first ACTIVE row, otherwise first
   row whose waiting condition is satisfied.
3. Dispatch the required role chain for that row:
   - boundary: PM -> CC -> FA -> PA -> PM
   - quant/ML/data: PM -> QC -> MIT -> AI-E -> PM
   - implementation: PM -> PA -> E1/E1a -> E2 -> E4 -> QA -> PM
   - runtime/exchange escalation only: PM -> E3 -> BB -> PM
4. If required role-chain dispatch tooling is unavailable, stop as
   STOP_DISPATCH_BLOCKED. Do not silently implement as a single-agent PM/PA
   substitute unless the operator explicitly grants that mode.
5. Implement only the selected row's source/doc/test scope and changed-file
   allowlist. Stage only owned files.
6. Run focused tests/static checks plus git diff --check.
7. Emit alr_work_item_v1, alr_effect_review_v1, alr_loop_state_packet_v1, a PM
   report, and an Operator summary when useful.
8. Commit each green checkpoint with a subject and body.
9. Re-read repo state and continue automatically while the state is ADVANCED,
   ADVANCED_WITH_CONCERNS, or source-only ROTATED with a clear next row.

For P0-AIML-ALR-BOUNDARY-PACKET, the primary target is:
srv/docs/CCAgentWorkSpace/PM/workspace/ai_ml_todo_stub/2026-07-09--scanner_driven_alr/boundary_packet.md
Do not write srv/docs/adr/, docs/amd/, migrations, root TODO import, or runtime
config for that row unless a future explicit PM scope authorizes the exact path.

Proof boundary:
Scanner artifacts are intake evidence only. OpportunityCandidate, final_score,
registry rows, decay events, no-order artifacts, no-fill artifacts, _latest
artifacts, touchability/preflight packets, cleanup fills, and unattributed fills
may rank learning targets or identify proof gaps. They are not orders, risk
verdicts, trade permission, profit proof, promotion proof, or runtime authority.

P0 scoring optimizes expected_value_of_information, not expected trade PnL. If
candidate-matched proof_packet_v1 and reward_ledger_v1 evidence is missing, EV
fields must be null or hypothesis_prior, edge_claim_allowed=false, and
proof_status=HYPOTHESIS_ONLY or DEFER_EVIDENCE. STOP_NO_EDGE is allowed only
after proof-ready candidate-matched outcomes plus controls and repeat/OOS
evidence show non-positive conservative after-cost lower confidence bound.

Model/LLM boundary:
P0 is not model training, model serving, online learning, proof, runtime
authority, or autonomous trading maturity. Any ranking that affects next_action
must be deterministic or traditional statistical code with replayable inputs.
LLM/L1/L2/DreamEngine/Teacher output can only be advisory_refs with
not_authority=true and cannot set scores, proof, reward, maturity, promotion, or
runtime/trading decisions.

Retention boundary:
RetentionGuardian P0 is dry-run manifest only. It cannot delete, move, rename,
chmod, update symlinks, overwrite _latest, write PG, change Timescale policy,
call prune/apply scripts, or perform runtime/network/Bybit/IPC/cron/daemon
actions. Unknown refs, disputed facts, proof/audit/lineage artifacts, negative
examples, no-fill/no-order evidence, cleanup/unattributed/proof-excluded facts,
failed gates, and ROTATED artifacts are protected.

Bybit/MCP hard stop:
Do not call Bybit REST or WS, public or private. Do not call private/account
REST, private WS, order create/amend/cancel/modify/cancel-all, fee-rate/private
reads, or any endpoint under /v5/order. Do not install, start, connect to, or
use official exchange MCP tools; MCP material is reference/taxonomy only unless
a future ADR/AMD plus exact PM -> E3 -> BB scope authorizes it.

Stop automatically and report the exact state if:
- BLOCKED_BOUNDARY: work needs runtime, PG, IPC, Bybit/official MCP, exchange,
  Decision Lease, order/probe, scheduler, service/env mutation, model serving,
  promotion, Cost Gate, live/mainnet, _latest overwrite, or delete authority.
- DEFER_EVIDENCE: proof needs candidate-matched fills/fees/slippage/funding,
  reconstruction, controls, proof-exclusion pass, repeat evidence, or OOS.
- STOP_RETENTION_RISK: cleanup touches proof, dispute, audit, lineage, unknown
  reference, or negative-example risk.
- STOP_DISPATCH_BLOCKED: required role-chain dispatch tooling is unavailable.
- ROTATED: source head, candidate id, input hash, auth/envelope, or referenced
  artifact drifted and cannot be re-intaken source-only.
- DONE: all P0 rows are implemented, verified, effect-reviewed, state-packeted,
  and committed.

Do not stop after intake if a source-only next row is available. Do not ask for
a separate continue prompt. Keep looping until DONE or one of the stop states
above is reached.
```
