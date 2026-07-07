# WP7 Learning Effect Review Stop Loop Design

Date: 2026-07-07
Role: PA(worker)
Status: `E1_READY_SOURCE_ONLY`

## Grounding

已讀並遵守：

- `AGENTS.md`
- `CLAUDE.md`
- `.codex/MEMORY.md`
- `README.md`
- `docs/agents/context-loading.md`
- `TODO.md`
- `.codex/AGENT_DISPATCH_PROTOCOL.md`
- `.codex/SUBAGENT_EXECUTION_RULES.md`
- `.codex/agents/PM.md`
- `docs/CCAgentWorkSpace/PA/profile.md`
- `docs/CCAgentWorkSpace/PA/memory.md`
- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-07--ai_ml_downstream_closure_loop_design.md`
- WP2.1 / WP3.1 / WP6 PA 設計報告

Repo fact:

- Local HEAD at task start matched operator input: `27f2cdb51d1e15aa0cd95ed42d48ea17e388bab8`.
- Existing unrelated dirty files include `memory/*`, IBKR, and Bybit `control_api_v1`; WP7 design must not touch them.
- Runtime/loss-control remains blocked; bounded Demo outcome ingestion is denied in this task.

Scope:

- Design only. No implementation patch in this PA task.
- WP7 adds `learning_effect_review_v1` packet / validator / tests.
- Promotion remains `review-only`, with no order, live, Cost Gate, serving reload, symlink, model reload, runtime mutation, or DB authority.

## Current Source Interfaces

WP7 should consume source contracts already landed or designed in the AI/ML roadmap chain:

- `program_code/ml_training/reward_ledger.py`
  - `REWARD_LEDGER_SCHEMA_VERSION = "reward_ledger_v1"`
  - `REWARD_RECORD_READY = "reward_record_ready"`
  - `validate_reward_record(...)`
  - `validate_reward_batch(...)`
  - `compute_reward_record_hash(...)`
  - reward records already carry candidate identity, execution fills, costs, controls, lineage, effect window, source artifacts, and `no_authority` flags.
- `program_code/ml_training/proof_packet_contract.py`
  - ProofPacket hash and `PROOF_READY` semantics remain upstream-owned.
- `program_code/ml_training/demo_mutation_envelope.py`
  - Mutation envelope countability and `STATUS_COUNTABLE` remain upstream-owned.
- `program_code/ml_training/registry_serving_contract.py`
  - Registry contract remains advisory-only and exact artifact-bound.

Inference:

- WP7 should not reinterpret raw fills, `_record_application` rows, runtime ledger files, PG rows, or exchange outputs.
- WP7 should read only caller-supplied in-memory mappings. Any real bounded Demo outcome ingestion belongs to a later PM->E3->BB-reviewed runtime branch, not this source task.

## Target Files

Primary E1 files:

- `program_code/ml_training/learning_effect_review.py`
- `program_code/ml_training/tests/test_learning_effect_review.py`

Optional only if import/export conventions require it:

- `program_code/ml_training/__init__.py`

Do not edit:

- `program_code/exchange_connectors/bybit_connector/control_api_v1/*`
- `program_code/broker_connectors/ibkr_connector/*`
- `memory/*`
- runtime helper scripts, cron, migrations, Rust authority, Decision Lease, Guardian, Cost Gate, deployment files, or live/mainnet configuration.

## Public API

Add a pure source-only module:

```python
LEARNING_EFFECT_REVIEW_FIELD = "learning_effect_review"
LEARNING_EFFECT_REVIEW_SCHEMA_VERSION = "learning_effect_review_v1"

DECISION_CONTINUE = "continue"
DECISION_ROLLBACK = "rollback"
DECISION_ROTATE_CANDIDATE = "rotate_candidate"
DECISION_STOP_LOSS_CONTROL = "stop_loss_control"
DECISION_STOP_NO_EDGE = "stop_no_edge"
DECISION_STOP_EVIDENCE = "stop_evidence"
DECISION_PROMOTE_REVIEW_ONLY = "promote_review_only"

@dataclass(frozen=True)
class LearningEffectReviewValidation:
    valid: bool
    decision: str
    reason: str
    reasons: tuple[str, ...]
    review_only: bool = True
    authority_boundary_violation: bool = False

def compute_learning_effect_review_hash(packet: Mapping[str, Any]) -> str: ...

def validate_learning_effect_review(packet: Any) -> LearningEffectReviewValidation: ...

def build_learning_effect_review_packet(
    *,
    reward_records: Sequence[Mapping[str, Any]],
    loss_limits: Mapping[str, Any],
    controls: Mapping[str, Any],
    oos_repeat_tags: Mapping[str, Any],
    acceptance_report_refs: Sequence[Mapping[str, Any]] | None = None,
    review_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]: ...

def extract_learning_effect_review(mapping: Any) -> Any: ...
```

Implementation note:

- Keep helper functions private. Avoid adding a class hierarchy or runtime adapter.
- Reuse `validate_reward_record(...)`, `validate_reward_batch(...)`, and `compute_reward_record_hash(...)`.
- If E1 needs the same authority-alias scan as `reward_ledger.py`, copy a small local denylist rather than importing private helpers.

## Packet Shape

Recommended canonical packet:

```json
{
  "schema_version": "learning_effect_review_v1",
  "review_id": "effect:grid_trading|ETHUSDT|Buy:<batch_hash_prefix>",
  "review_only": true,
  "decision": "promote_review_only",
  "decision_reasons": ["profitable_after_cost_repeat_ready_for_operator_review"],
  "candidate_identity": {
    "candidate_id": "grid_trading|ETHUSDT|Buy",
    "strategy_name": "grid_trading",
    "symbol": "ETHUSDT",
    "side": "Buy"
  },
  "inputs": {
    "reward_ledger_refs": [
      {"record_id": "...", "record_hash": "..."}
    ],
    "proof_packet_refs": ["<64hex>"],
    "mutation_envelope_refs": ["<64hex>"],
    "acceptance_report_refs": [
      {"acceptance_report_hash": "<64hex>", "path": "optional/source-local/path"}
    ]
  },
  "effect_metrics": {
    "sample_count": 3,
    "net_pnl_bps_sum": 12.6,
    "net_pnl_usdt_sum": 1.26,
    "net_pnl_bps_mean": 4.2,
    "positive_sample_count": 3,
    "negative_sample_count": 0,
    "matched_control_count": 6,
    "control_outperformance_bps": 7.5,
    "mutation_effect_status": "passed",
    "oos_status": "passed",
    "repeat_status": "passed"
  },
  "controls": {
    "matched_control_required": true,
    "matched_control_ids": ["control-1", "control-2"],
    "regime_labels_required": true,
    "oos_required": true,
    "repeat_required_for_promotion": true
  },
  "loss_limits": {
    "max_cumulative_loss_bps": 20.0,
    "max_cumulative_loss_usdt": 5.0,
    "max_single_record_loss_bps": 10.0,
    "max_consecutive_negative_windows": 2,
    "breach": false
  },
  "oos_repeat_tags": {
    "oos": true,
    "repeat": true,
    "repeat_count": 2,
    "regime_tag": "sideways_medium_vol"
  },
  "source_artifacts": {
    "reward_records": []
  },
  "no_authority": {
    "runtime_mutation": false,
    "db_read": false,
    "db_write": false,
    "db_migration": false,
    "exchange_contact": false,
    "private_read": false,
    "secret_access": false,
    "order_or_probe": false,
    "cost_gate_change": false,
    "deploy": false,
    "live_or_mainnet": false,
    "promotion": false,
    "promotion_review_only": true,
    "model_reload": false,
    "serving_reload": false,
    "symlink_promotion": false
  },
  "review_hash": "<64hex>"
}
```

Hash rule:

- `review_hash` excludes only the top-level `review_hash`, matching the existing reward / proof / registry pattern.
- All source artifact hashes in refs must match recomputed hashes from embedded source artifacts when embedded artifacts are supplied.

## Decision Rules

Decision order must be fail-closed and deterministic:

1. Authority boundary violation anywhere in packet, reward records, source artifacts, controls, loss limits, or acceptance refs -> invalid packet / `stop_evidence` reason with `authority_boundary_violation=True`.
2. Missing or malformed `loss_limits`, explicit limit breach, cumulative loss below allowed floor, single-record loss breach, or consecutive negative-window breach -> `stop_loss_control`.
3. No reward records, no valid `reward_record_ready` records, no matched fills, missing ProofPacket refs, missing mutation envelope refs, hash mismatch, mixed candidates, open/non-PIT effect window, or invalid reward batch -> `stop_evidence`.
4. Missing controls, empty matched controls, missing regime labels, missing OOS tags required by policy, proof exclusions, or acceptance report hash mismatch -> `stop_evidence`.
5. Sample count below `review_policy.min_sample_count` -> `stop_evidence`.
6. Mutation effect failed, for example `mutation_effect_status == "failed"` or control outperformance is negative when required -> `rollback`.
7. After-cost aggregate EV negative with enough sample and no loss-limit breach -> `stop_no_edge`.
8. After-cost aggregate EV near zero or below configured edge floor and candidate rotation allowed -> `rotate_candidate`; otherwise `stop_no_edge`.
9. After-cost positive, controls pass, OOS pass, but repeat requirement not yet met -> `continue`.
10. After-cost positive, controls pass, OOS pass, repeat pass, and min sample satisfied -> `promote_review_only`.

Important semantics:

- `promote_review_only` is an operator-review packet, not promotion authority.
- `continue` means continue source/runtime evidence collection inside future approved gates; it grants no order/probe authority.
- `rollback` is a review decision that a future separately authorized rollback mechanism may consume. WP7 itself must not mutate runtime or invoke rollback.
- `rotate_candidate` is planning guidance only. It must not update candidate selection state or TODO by itself.

## Fail-Closed Validation Requirements

E1 must reject or stop on:

- reward record missing, invalid, duplicate, or non-ready;
- no matched fills / no-fill ProofPacket;
- mixed candidate identities across reward records;
- proof packet hash mismatch;
- mutation envelope hash mismatch;
- missing acceptance report ref when `review_policy.acceptance_report_required is True`;
- missing controls or empty matched controls;
- missing OOS/repeat tags when policy requires them;
- missing or malformed loss limits;
- any loss-limit breach;
- negative after-cost EV;
- failed mutation effect;
- insufficient sample;
- any truthy authority alias such as order/live/mainnet/Cost Gate/promotion/model reload/symlink;
- `review_only` not true;
- `no_authority.promotion_review_only` not true or any other no-authority field not false;
- review hash mismatch.

## Test Matrix

Required focused tests in `program_code/ml_training/tests/test_learning_effect_review.py`:

1. Profitable after-cost repeat:
   - valid reward batch, positive net PnL, controls pass, OOS pass, repeat pass;
   - decision is `promote_review_only`;
   - `review_only is True`;
   - all no-authority flags remain denied except `promotion_review_only`.
2. Positive but not repeat-ready:
   - positive after-cost evidence but repeat tag missing/false;
   - decision is `continue`.
3. Negative EV:
   - enough valid records but aggregate after-cost net is negative;
   - decision is `stop_no_edge`.
4. No matched fills:
   - no-fill ProofPacket or invalid reward input;
   - decision is `stop_evidence` or builder raises before packet creation.
5. Insufficient sample:
   - valid one-record batch with policy min sample above one;
   - decision is `stop_evidence`.
6. Missing controls:
   - remove matched controls / regime labels / OOS split;
   - decision is `stop_evidence`.
7. Failed mutation effect:
   - controls pass structurally but `mutation_effect_status="failed"` or control outperformance below zero;
   - decision is `rollback`.
8. Loss-limit breach:
   - cumulative or single-record loss limit exceeded;
   - decision is `stop_loss_control`.
9. Authority alias injection:
   - inject `order_allowed=true`, `promotion_allowed=true`, `model_reload=true`, or `cost_gate_lowered=true`;
   - validation fails with authority boundary violation.
10. Hash integrity:
   - mutate packet after computing `review_hash`;
   - validation rejects `review_hash_mismatch`.

Useful adjacency tests:

- Reward batch duplicate record id remains rejected.
- Mixed `candidate_id` / `symbol` / `side` across reward records rejects.
- Acceptance report hash mismatch rejects when supplied.

## Verification Commands

E1 focused source checks:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m py_compile \
  program_code/ml_training/learning_effect_review.py \
  program_code/ml_training/reward_ledger.py \
  program_code/ml_training/proof_packet_contract.py \
  program_code/ml_training/demo_mutation_envelope.py
```

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q \
  program_code/ml_training/tests/test_learning_effect_review.py \
  program_code/ml_training/tests/test_reward_ledger.py \
  program_code/ml_training/tests/test_proof_packet_contract.py \
  program_code/ml_training/tests/test_demo_mutation_envelope.py \
  -p no:cacheprovider
```

Diff hygiene:

```bash
git diff --check
```

No Linux runtime, PG, exchange, private-read, model reload, deploy, or service verification is required or allowed for source closure.

## E1 Prompt

```text
You are E1(worker) for /Users/ncyu/Projects/TradeBot/srv.

Task: implement WP7-EFFECT-REVIEW-AND-STOP-LOOP source-only contract from
docs/CCAgentWorkSpace/PA/workspace/reports/2026-07-07--wp7_learning_effect_review_stop_loop_design.md.

Allowed files:
- program_code/ml_training/learning_effect_review.py
- program_code/ml_training/tests/test_learning_effect_review.py
- program_code/ml_training/__init__.py only if needed for package export.

Use existing validators:
- reward_ledger.validate_reward_record / validate_reward_batch / compute_reward_record_hash
- upstream source artifacts embedded in reward records.

Do not perform runtime mutation, DB read/write/migration, exchange/private read, MCP server/config/credential/secret work, order/probe, Cost Gate change, deploy, live/mainnet, model reload/symlink, or bounded Demo outcome ingestion.

Implement:
- learning_effect_review_v1 packet constants;
- LearningEffectReviewValidation dataclass;
- compute_learning_effect_review_hash;
- validate_learning_effect_review;
- build_learning_effect_review_packet;
- extract_learning_effect_review.

Decision outputs:
continue, rollback, rotate_candidate, stop_loss_control, stop_no_edge,
stop_evidence, promote_review_only.

Tests must cover:
profitable after-cost repeat, positive but not repeat-ready, negative EV,
no matched fills, insufficient sample, missing controls, failed mutation effect,
loss-limit breach, authority alias injection, and review hash mismatch.

Run:
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m py_compile \
  program_code/ml_training/learning_effect_review.py \
  program_code/ml_training/reward_ledger.py \
  program_code/ml_training/proof_packet_contract.py \
  program_code/ml_training/demo_mutation_envelope.py

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q \
  program_code/ml_training/tests/test_learning_effect_review.py \
  program_code/ml_training/tests/test_reward_ledger.py \
  program_code/ml_training/tests/test_proof_packet_contract.py \
  program_code/ml_training/tests/test_demo_mutation_envelope.py \
  -p no:cacheprovider

git diff --check

Return status, changed files, test output, and any fail-closed concerns.
Do not stage or commit unless PM/operator separately asks.
```

## Acceptance Checklist

E1 implementation is acceptable only when:

- `learning_effect_review_v1` packet validates deterministically from caller-supplied source artifacts.
- Builder consumes only valid `reward_ledger_v1` records and recomputes record hashes.
- Inputs include reward ledger refs, ProofPacket refs, mutation envelope refs, acceptance report refs when required, controls, loss limits, and OOS/repeat tags.
- Decisions are exactly one of:
  - `continue`
  - `rollback`
  - `rotate_candidate`
  - `stop_loss_control`
  - `stop_no_edge`
  - `stop_evidence`
  - `promote_review_only`
- Loss-control and evidence failures outrank profitable decisions.
- `promote_review_only` cannot be misread as order/live/promotion authority.
- All no-authority flags deny runtime mutation, DB, exchange/private read, order/probe, Cost Gate, deploy, live/mainnet, model reload, serving reload, and symlink promotion.
- Focused tests cover the required matrix and pass locally.
- `git diff --check` passes.
- No unrelated dirty files are touched.

## E2 Review Focus

1. Decision priority:
   - `stop_loss_control` and `stop_evidence` must preempt `continue` / `promote_review_only`.
2. Authority language:
   - no truthy alias can smuggle order, live, Cost Gate, model reload, symlink, or direct promotion semantics.
3. Evidence honesty:
   - no-fill, insufficient sample, missing controls, and missing OOS/repeat cannot become zero/negative rewards or promotion-ready decisions.

## Boundary Confirmation

This design requires no denied action. If E1 finds that implementation would need runtime files, PG, exchange/private reads, order/probe, Cost Gate, deploy, live/mainnet, model reload/symlink, or bounded Demo outcome ingestion, E1 must stop and report `BLOCKED` with the exact reason.
