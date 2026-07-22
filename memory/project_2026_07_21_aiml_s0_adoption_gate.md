---
name: project_2026_07_21_aiml_s0_adoption_gate
description: AIML roadmap through V2 Sprint 0; forge-resistant source landed 2026-07-21 and trusted-host PROGRAM_ADOPTED issued 2026-07-22 with source-only, zero-authority boundaries.
metadata:
  node_type: memory
  type: project
  originSessionId: 07e83463-9c2c-4475-8221-65951702b432
  modified: 2026-07-22T09:33:14Z
---

> 這是 2026-07-21 source landing 的時點紀錄；當時尚待執行的 trusted-host
> finalization 已於 2026-07-22 完成，當前狀態見文末「演變軌跡」。本弧承接
> [[project_2026_07_07_ai_ml_maturity_roadmap]]，舊 topic 保留原始 WP1-WP7 歷史。

**AIML-LONG-LIVED-LANDING-V2 Sprint 0 landed (2026-07-21).** Continued the prior
session's stalled `agent/aiml-s0-3-adoption-v1` worktree and closed the S0
program-adoption gate as **source**, three-end synced at `0034a406089`.

- **S0.1** DONE (V2 planning, PR #100). **S0.2** DONE — advisory-serving authority:
  `docs/adr/0051-registry-authorized-advisory-model-serving.md` + `AMD-2026-07-21-01`
  + ADR-0049 addendum + `serving_authority_receipt_v1`. ADR-0051 A3 makes model
  output monotone (`NO_OP|VETO|SIZE_DOWN`, `final_notional<=baseline`); A9 permanently
  denies direct model→broker/order; Guardian/Decision-Lease/Cost-Gate stay superior.
- **S0.3** = `SOURCE_READY` (NOT `PROGRAM_ADOPTED`). Landed the 7 `aiml_gate_receipts`
  JSON schemas, fail-closed `program_code/ml_training/aiml_gate_receipt_validator.py`,
  Registry/router/closure integration, `terminal_receipt_sink_v1` contract-only
  (owner S1.2), and a strict GitHub repo-policy attestation contract. Merged PR #104
  (`b945fe0f8`); ledger projection PR #105 (`0034a406089`).
- **Review**: 7-role adversarial (E2 P1 = bind changed `agent_governance_execution.py`
  into the manifest; E4 P1×3 = negative tests locking authority_limits/7-reviewer/
  dep-graph invariants — both fixed + re-verified). Then the **Codex PR bot** (8th
  reviewer) found **3 real P1 forge-resistance gaps**; per PA min-coherent design all
  fixed + CC/E3/E2 re-review PASS: (1) route the 7 mandatory reviewers into the
  finalization DAG bound to authenticated PASS fragments (reuse `validate_closure`
  recomputed-generation + `validate_execution_attestations`); (2) `SourceManifestVerifier`
  contract must prove `git merge-base --is-ancestor reviewed_head merge_head`;
  (3) `session_attempt_v1` phase-conditional lease (read-only `POST_MERGE_FINALIZATION`
  uses `read_only_admission`, forbids writer lease).

**KEY: `PROGRAM_ADOPTED` emission is a trusted-host (Linux) step, not offline-mintable.**
The hardened gate requires the enforced closure path — 7 governed reviews authenticated
by an out-of-band `execution_attestation_verifier` + `source_manifest_verifier` ancestry
+ live GitHub ruleset. Per the Typed Authority Matrix the offline Mac CLI cannot
authenticate a closure PASS (ORCHESTRATOR_BOUND insufficient; needs PLATFORM_ATTESTED).
The exact follow-up recipe + accepted P2 coverage-debt are in
`docs/execution_plan/ai_ml_landing/PROGRESS.md` "Trusted-Host Follow-Ups". Next real
work = that Linux emission → then S1. See [[project_ssh_bridge_workflow]] for the
Codex-reviewer merge-gate. Boundary held throughout: authority_limits all-const-false,
`source_adoption_only`, four-zero-effects; no ML5/ML6/live/broker/order/Decision-Lease.

## 演變軌跡

- **2026-07-22 — `SOURCE_READY` → `PROGRAM_ADOPTED`:** Linux `trade-core` 已對
  reviewed head `1a933fcc28e9f7341e023b5d401c479957c14c5f` 與 merge head
  `fed223bebd278c50b0ab3330980e66441a30c9ed` 完成 trusted-host finalization；
  governed E4 `275/275`，finalizer closure
  `sha256:27f7b0041a418298ef49943f6f37283b603fce38f48f67f9a825f249f2615c63`，
  receipt `sha256:1a124bcaebb741a69c97e37a828e5b85c9b6499cdf053e8ef62451448878f93b`。
  原文「Next real work = that Linux emission」只描述 07-21 時點，現已被此事件推進；
  receipt 仍為 `source_adoption_only=true`、九項 authority grants 全 false，不代表
  runtime readiness、model promotion、broker/order 或任何 trading authority。權威證據見
  `docs/execution_plan/ai_ml_landing/PROGRESS.md` 的 2026-07-22 ledger 與
  「S0.3 Trusted-Host Finalization (completed)」。
- **索引合併:** 為守住 `memory/MEMORY.md` Project context ≤40 條，本 topic 吸收
  07-05~07 WP1-WP7 roadmap 的索引弧；原始內容仍完整保存在
  [[project_2026_07_07_ai_ml_maturity_roadmap]]，沒有刪除歷史。
