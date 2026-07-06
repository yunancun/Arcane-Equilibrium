# 2026-07-06 AI/ML Roadmap Adversarial Audit

PM verdict: `PASS-WITH-CONDITIONS`

Scope: adversarial audit of
`docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-06--ai_ml_trade_engineering_roadmap_after_maker_challenge.md`.
This audit checks whether the roadmap is technically effective, implementable, and aligned with
repo hard boundaries. It is source-only. No runtime action, DB write, exchange/API/private read,
order/probe, MCP install/config, secret access, Cost Gate change, or live/mainnet action was
performed.

## Bottom Line

The roadmap is valid as an engineering direction, but only if treated as a gate-based sequence, not
a calendar promise.

No fatal contradiction was found. The plan correctly identifies the real blocker: missing
candidate-matched, after-cost, reconstructable outcomes. It also keeps AI/ML out of order authority
and keeps MCP source-only.

The plan is not implementation-ready if a worker interprets `ProofPacket`, `DemoMutationEnvelope`,
or "90 days" as already-existing complete surfaces. Those must be treated as contract work and gate
labels, not as current runtime capabilities.

## Evidence Reviewed

- `TODO.md`: active blocker remains
  `P0-STANDING-DEMO-LOSS-CONTROL-ENVELOPE-REFRESH-CURRENT-HEAD`; standing Demo auth expired at
  `2026-07-01T17:16:05Z`; current candidate still has zero candidate-matched fill/fee/slippage proof.
- AI/ML roadmap report from this session.
- `program_code/ml_training/candidate_evidence_manifest.py`
- `program_code/ml_training/candidate_evidence_manifest_builder.py`
- `helper_scripts/research/cost_gate_learning_lane/learning_event_contract.py` via test surface
  `helper_scripts/research/tests/test_cost_gate_learning_event_contract.py`
- `program_code/ml_training/parquet_etl.py`
- `program_code/ml_training/model_registry.py`
- `program_code/ml_training/run_training_pipeline.py`
- `program_code/ml_training/mlde_demo_applier.py`
- `rust/openclaw_engine/src/edge_predictor/ort_backend.rs`
- `rust/openclaw_engine/src/order_router.rs`
- `program_code/research/microstructure/fill_sim.py`

## Findings

### A1. The roadmap is effective only as a strict dependency graph

Severity: P0 guard.

The proposed order is correct:

1. standing envelope refresh,
2. bounded candidate-matched outcome,
3. PIT manifest / outcome ledger,
4. supervised advisory,
5. Demo bandits,
6. RL/MCP/niche work.

But the 0-14 / 15-30 / 31-60 / 61-90 timeline must not be used as authority to advance phases. If
WP0/WP1 do not produce candidate-matched outcomes, WP3/WP5 remain shadow/research-only.

Required correction for dispatch: replace calendar language in worker prompts with "earliest target
window; gate outcome overrides date."

### A2. `ProofPacket` is not yet a complete existing contract

Severity: P0 implementation prerequisite.

The repo has useful pieces:

- `candidate_evidence_manifest.py` validates candidate manifest lineage, hidden OOS, residual report,
  and hashes.
- LearningEvent contract wraps probe ledger/artifacts and protects authority boundaries.
- Demo learning lane and bounded probe surfaces exist.

But none of these is a complete ProofPacket carrying all fields the roadmap requires: order link id,
fill ids, entry/exit context ids, maker/taker role, fee, slippage, funding, markout, controls, and
proof exclusions.

Required correction for dispatch: first engineering ticket must be a source-only
`proof_packet_v1` contract / schema / validator / tests, then adapter wiring. Do not tell E1 to
"use existing ProofPacket."

### A3. PIT manifest work is mandatory, not optional hardening

Severity: P0 data blocker.

`parquet_etl.py` still has trailing-window and `now()` style data access in current training paths.
That is acceptable for research but not promotion-grade training. The roadmap correctly calls for
PIT manifests; this audit confirms that it is a real blocker.

Required correction for dispatch:

- every promotable dataset must record `as_of_ts`, query hash, source snapshot/hash, row ids/counts,
  min/max timestamps, schema hash, label hash, config hash, code commit, Rust build SHA, split ids,
  and proof exclusions;
- same manifest must rebuild the same row set/hash;
- failed rebuild, unpinned `now()`, or cleanup/unmatched fills must mark artifact research-only.

### A4. Registry-authorized serving is not fully current reality

Severity: P1 guard.

The q10/q50/q90 trio, ONNX metadata, Rust ORT loader, and registry writer already exist. The current
registry also has fail-loud support when required by the training pipeline. However, registry rows do
not yet fully carry all roadmap metadata, and serving authority is not yet fully modeled as
"registry row or fail-closed" across the whole path.

Required correction for dispatch:

- extend registry metadata before claiming Phase 3 completion;
- serving must require dataset manifest hash, label schema hash, split hash, leakage report hash,
  serving config hash, missingness policy, units, side handling, and artifact hashes;
- `_current` symlink is convenience only.

### A5. `DemoMutationEnvelope` must be formalized or mapped to existing applier records

Severity: P1 implementation prerequisite.

`mlde_demo_applier.py` has important protections: demo engine lock, bounded numeric deltas, dry-run
status, IPC path, live/live_demo rows not applied, and governed live candidate audit rows. But
`DemoMutationEnvelope` is not a clear canonical type in the inspected surface.

Required correction for dispatch:

- define a `demo_mutation_envelope_v1` contract or explicitly map it to the existing application
  record shape;
- require previous value, proposed value, bounded delta, source proposal id, governance verdict,
  rollback handle, IPC response, post-change review, and proof linkage;
- empty/dedupe/dry-run applications cannot count as learning success.

### A6. New-listing/event microstructure screen needs anti-cherry-pick controls

Severity: P1/P2 research guard.

`fill_sim.py` is good for explicit windows and current mature-universe analysis. It is not, by
itself, a listing-aware event study. The roadmap's new-listing/event screen is a valid challenge
lane only if it adds event-window provenance.

Required correction for dispatch:

- pre-register event/listing windows before looking at PnL;
- record symbol universe, listing/event timestamp source, inclusion/exclusion criteria, fee tier,
  and no-rebate assumption;
- require holdout or repeated sealed windows;
- gross spread alone is not evidence; adverse selection and fees remain mandatory.

### A7. M12 router is valid only after fee/rebate wording is corrected

Severity: P2 design guard.

`order_router.rs` is intentionally dormant and fail-loud, which matches the roadmap. However, the
comments/spec references still carry older maker-tier/rebate-oriented language. After the 2026-07-06
maker-first verdict, M12 must be scoped as execution cost reduction, not rebate capture or alpha.

Required correction for dispatch:

- first M12 ticket should be a design/spec refresh, not implementation;
- remove or quarantine any expectation of reachable retail maker rebates;
- acceptance should be measured realized cost reduction vs controls, not profitability.

### A8. MCP source-only matrix is safe, but must stay pinned/offline

Severity: P2 security guard.

The roadmap's MCP stance is safe: source-only inventory and deny-by-default classification. It
becomes unsafe if any worker runs an MCP server, uses credentials, relies on `@latest`, or treats MCP
output as proof/runtime truth.

Required correction for dispatch:

- use pinned repo/package version and source hash;
- no credentials, no server start, no exchange calls, no runtime integration;
- classify tools into public read, private read, trade write, account write, asset movement, denied;
- any future no-key public diagnostic still needs E3/BB review and cannot clear Cost Gate/proof.

## Effectiveness Check

The roadmap is effective because it attacks the highest-leverage failure mode:

- It stops model work from optimizing bad labels.
- It forces candidate-matched fills/fees/slippage before reward learning.
- It makes data point-in-time and rebuildable.
- It uses supervised advisory before RL.
- It keeps LLM/DreamEngine advisory-only.
- It keeps MCP outside runtime authority.
- It keeps maker-first NO-GO in force for mature perps while allowing narrow offline challenge lanes.

The roadmap would fail if:

- implementation skips WP0/WP1 and starts with models or bandits;
- `candidate_evidence_manifest` is mistaken for a complete ProofPacket;
- training still uses unsealed trailing `now()` datasets;
- `_current` artifacts are treated as serving authority;
- demo applier records are counted as success without real after-cost outcomes;
- new-listing screens are picked after seeing favorable windows;
- MCP is allowed to touch credentials, private reads, or orders.

## Dispatch Constraints For Next Work

The next concrete implementation should be one of:

1. `proof_packet_v1` source contract and tests,
2. PIT dataset manifest contract and tests,
3. current-head standing envelope refresh under existing E3/BB process.

Do not start with:

- RL,
- MCP runtime,
- M12 implementation,
- bandit runtime,
- model promotion,
- live/tiny-live,
- Cost Gate lowering.

## Final Verdict

`PASS-WITH-CONDITIONS`.

The roadmap is technically sound and worth pursuing, but its effectiveness depends on enforcing the
dependency gates above. The first safe engineering move remains evidence integrity, not model
sophistication.
