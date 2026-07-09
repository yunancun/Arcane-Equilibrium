# Scanner-Driven ALR Todo Stub And Loop Prompt

Date: 2026-07-09
Owner: PM
Status: `DONE_WITH_CONCERNS`
Scope: docs/todo-stub/prompt only
Boundary label: `SOURCE_ONLY_OFFLINE_P0_P1`

## PM Sign-Off

PM SIGN-OFF: CONDITIONAL PASS.

The scanner-driven ALR stub is executable as a foreground Codex
source-development loop under `SOURCE_ONLY_OFFLINE_P0_P1`. It can select the
active boundary row, then controller contracts, then P0-A/B/C source-only work,
with effect review, durable state packet, narrow commit, and automatic
continuation.

It grants no runtime, PG, IPC, Bybit/MCP, scheduler, Decision Lease,
order/probe, Cost Gate, serving, proof, promotion, live/mainnet, or delete
authority.

## Final Artifacts

- Todo stub: `docs/CCAgentWorkSpace/PM/workspace/ai_ml_todo_stub/2026-07-09--scanner_driven_alr/README.md`
- Machine manifest: `docs/CCAgentWorkSpace/PM/workspace/ai_ml_todo_stub/2026-07-09--scanner_driven_alr/manifest.json`
- Ordered queue: `docs/CCAgentWorkSpace/PM/workspace/ai_ml_todo_stub/2026-07-09--scanner_driven_alr/queue.md`
- Boundaries: `docs/CCAgentWorkSpace/PM/workspace/ai_ml_todo_stub/2026-07-09--scanner_driven_alr/boundaries.md`
- Loop contract: `docs/CCAgentWorkSpace/PM/workspace/ai_ml_todo_stub/2026-07-09--scanner_driven_alr/loop_contract.md`
- Retention contract: `docs/CCAgentWorkSpace/PM/workspace/ai_ml_todo_stub/2026-07-09--scanner_driven_alr/retention_guardian_contract.md`
- Startup prompt: `docs/CCAgentWorkSpace/PM/workspace/ai_ml_todo_stub/2026-07-09--scanner_driven_alr/startup_prompt.md`

## Dispatch

Adversarial review chain:

| Role | Agent id | Verdict | Key correction |
|---|---|---|---|
| `CC(default)` | `019f441f-521f-7d81-af6a-361b4cf5651d` | `DONE_WITH_CONCERNS` | Codex source-development loop only; scanner is evidence only; hard stop on runtime contamination. |
| `FA(default)` | `019f441f-528d-7762-8d3d-c47465e63c0c` | `DONE_WITH_CONCERNS` | Add durable ALR cursor/contracts before P0-A/B/C and make queue executable. |
| `QC(default)` | `019f441f-5312-7881-a0c7-ccd058ae4422` | `CONDITIONAL_PROCEED` | P0 optimizes `expected_value_of_information`, not trade PnL; missing proof is `DEFER_EVIDENCE`. |
| `MIT(default)` | `019f441f-538c-7862-9077-f182c36c005a` | `DONE_WITH_CONCERNS` | RetentionGuardian is dry-run manifest only; protect disputed/proof/negative/lineage artifacts. |
| `AI-E(default)` | `019f441f-540b-7920-94b4-d2aa47b1f252` | `APPROVE_WITH_CORRECTIONS` | No model training/serving in P0; add anti-hallucinated maturity fields. |
| `E3(explorer)` | `019f441f-5556-7391-93c7-e2e3885f3eab` | `APPROVE_WITH_CONCERNS` | Add changed-file allowlist/static checks; no scheduler/runtime actor. |
| `BB(default)` | `019f4423-7cc1-75e3-9c32-cbf197f1f7be` | `CONDITIONAL_PASS` | No Bybit/MCP/public REST contact and no inheritance from prior exact-scope approvals. |
| `PA(default)` | `019f442c-726c-7a03-93ef-d4f54eafd523` | `CONDITIONAL_PASS` | Commit stub, pin boundary-packet target, add `STOP_DISPATCH_BLOCKED`. |

## Resulting Work Order

The final queue intentionally starts with governance/cursor work before
implementation:

1. `P0-AIML-ALR-BOUNDARY-PACKET`
2. `P0-AIML-ALR-CONTROLLER-CONTRACTS`
3. `P0-AIML-ALR-LEARNING-TARGET-ARBITER`
4. `P0-AIML-ALR-OUTCOME-BRIDGE`
5. `P0-AIML-ALR-RETENTION-GUARDIAN-DRY-RUN`

The first row's primary output target is fixed:

`docs/CCAgentWorkSpace/PM/workspace/ai_ml_todo_stub/2026-07-09--scanner_driven_alr/boundary_packet.md`

The first row must not write `docs/adr/`, `docs/amd/`, migrations, root
`TODO.md`, or runtime config unless a future explicit PM scope authorizes the
exact target.

## Hard Boundaries

- ALR P0/P1 is source-only, offline, local-artifact engineering.
- It is not trading P0/P1, Demo final-window, runtime prep, bounded probe, or
  order-capable work.
- Scanner output is intake evidence only and cannot become proof, order
  permission, risk verdict, or runtime admission.
- P0 scoring optimizes `expected_value_of_information`.
- Candidate-matched after-cost proof is required for edge claims.
- RetentionGuardian P0 is dry-run manifest only.
- If role dispatch is unavailable, stop as `STOP_DISPATCH_BLOCKED`; do not
  silently substitute single-agent implementation.

## Verification

Performed:

- `python3 -m json.tool .../manifest.json`
- `git diff --check -- docs/CCAgentWorkSpace/PM/workspace/ai_ml_todo_stub/2026-07-09--scanner_driven_alr`
- keyword presence check for `SOURCE_ONLY_OFFLINE_P0_P1`, `official MCP`,
  `expected_value_of_information`, `alr_loop_state_packet_v1`, and
  `STOP_RETENTION_RISK`

Not performed:

- no production code tests, because this is docs/stub/prompt only
- no runtime SSH
- no PG read/write
- no Bybit/API/MCP/network call
- no Decision Lease
- no order/probe/live/mainnet action
- no Cost Gate, `_latest`, model serving, proof, promotion, or cleanup apply
