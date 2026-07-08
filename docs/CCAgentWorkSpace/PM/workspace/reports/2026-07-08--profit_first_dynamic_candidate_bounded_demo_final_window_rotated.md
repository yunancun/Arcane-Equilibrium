# Profit-First Dynamic Candidate Bounded Demo Final-Window Rotated

Status: `ROTATED`

## Summary

The previously recorded `READY_FOR_BOUNDED_DEMO_FINAL_WINDOW` packet is no longer safe to consume as an exact-scope final-window input.

The selected side-cell key did not change: latest runtime artifacts still resolve to `ma_crossover|NEARUSDT|Buy` with avg net `64.983bps`. However, the runtime `_latest` false-negative candidate packet and autonomous proposal hashes advanced after the BB review. Because the current policy is dynamic candidate selection, final-window approval is hash-bound to the latest machine-readable evidence, not only to the candidate string.

## Drift Evidence

| Surface | BB review binding | Latest runtime value at rotation check |
|---|---|---|
| Source head | `da1a04ecac9e2de86a47a700b76e183509995362` at BB review; source later checkpointed at `f1ec838d5cd66b6cd5b4bdd6e0c52546529bfe32` | Mac/GitHub/Linux aligned at `f1ec838d5cd66b6cd5b4bdd6e0c52546529bfe32`; Linux clean |
| Candidate packet | `1387ae73d65c7ba5f476a8b562e787089673d484528c2d132e4789de11af67ae` | `47d4bccb4816e049a8959f27804fae3b9c6f996172e699f03c864e73a52cfddc`, generated `2026-07-08T12:32:25.662859+00:00` |
| Proposal packet | `676f6c3ec91aae33542314fd435bb929fa5140feaf3c3c12fedd4a1b7b260282` | `76c7846969af266528c658d76b26c0dd7aac3fef1aca79c221725e66b0911370`, generated `2026-07-08T12:32:25.789875+00:00` |
| Selected candidate | `ma_crossover|NEARUSDT|Buy` | `ma_crossover|NEARUSDT|Buy` |
| Standing auth | `05fe07f5ad4f92c459c4c6f67bfe534a04b0ea4b4e8f2d8aa43879d87009152f` | unchanged, active, no order/probe authority |
| Operator auth readiness | `0438247d3a696d420e8272bf16d549ead70403d773fc903d97639efc75f72bd4`, `decision=defer` | unchanged by this PM checkpoint |

## Decision

The old PM final-window-ready packet, BB request, and BB approval remain historical evidence only. They must not be consumed for same-window final gate execution.

Next machine-executable work is to restart from the current runtime `_latest` candidate/proposal hashes and regenerate the dynamic candidate-aligned gate chain or hash-refresh packet, then redispatch exact PM->E3/BB if all no-authority artifacts remain READY and source/runtime heads remain stable.

## Boundary

Not performed in this rotation checkpoint:

- No public/private Bybit call.
- No Decision Lease acquire/release.
- No order/probe/cancel/modify.
- No bounded Demo final window.
- No operator auth `authorize`.
- No adapter enablement.
- No service restart/build.
- No DB write/migration.
- No Cost Gate lowering.
- No live/mainnet.
- No proof/promotion.
