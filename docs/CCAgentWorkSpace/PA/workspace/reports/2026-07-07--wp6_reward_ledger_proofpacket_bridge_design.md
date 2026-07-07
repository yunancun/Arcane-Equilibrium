# WP6 Reward Ledger ProofPacket Bridge Design

Date: 2026-07-07
Role: PA(default)
Status: E1-READY_SOURCE_ONLY

## Selected Roadmap Work Item

`WP6-REWARD-LEDGER-PROOFPACKET-BRIDGE`

目標是新增 `reward_ledger_v1` source contract / validator / offline bridge，使 learning state 只消費：

- valid `proof_packet_v1` 且 `verdict == "proof_ready"` / `proof_ready=True`；
- candidate identity 完全匹配的 ProofPacket；
- valid `demo_mutation_envelope_v1` 且 `status == STATUS_COUNTABLE` / `effective_learning_countable=True`；
- append-only reward record，帶 candidate、strategy、symbol、side、fills、costs、controls、PIT/registry lineage、mutation envelope hash、effect window。

本輪是 source-only architecture/design pass。`RUNTIME_LOSS_CONTROL_BLOCKED` 仍有效，因此 WP6 不得讀 live PG、runtime file、exchange/private endpoint，不得產生真 outcome ingestion。

Dispatch chain: 使用者明確指定 PA；本輪是設計/架構 pass，未派 E1/E2/E4。E1 實作後仍需 E2 review + E4 focused regression。

## Current Source Interfaces

### `proof_packet_contract.py`

File: `program_code/ml_training/proof_packet_contract.py`

現況：

- `PROOF_PACKET_SCHEMA_VERSION = "proof_packet_v1"`
- `PROOF_READY = "proof_ready"`
- `NO_MATCHED_FILLS = "no_matched_fills"`
- `validate_proof_packet(packet)` 回傳 `ProofPacketValidation`
- `compute_proof_packet_hash(packet)` 對 canonical JSON 做 sha256，排除頂層 `proof_packet_hash`
- `extract_proof_packet(mapping)` 只讀 canonical `proof_packet`，不接受 alias

可消費條件：

- `validation.proof_ready is True`
- `validation.verdict == PROOF_READY`
- `validation.reason == "ok"`
- `execution_identity.candidate_matched is True`
- `execution_identity.fill_ids` 非空且無重複
- `candidate_identity.context_id == execution_identity.entry_context_id`
- `cost_identity` 完整帶 maker/taker fee、slippage、spread、funding、markout、realized net PnL
- `controls` 完整帶 matched controls、regime labels、OOS split，且 `proof_exclusions` empty
- `provenance.pit_dataset_manifest` valid and candidate-scope matched
- authority alias / promotion ready / cleanup / unattributed / proof-excluded 皆 fail-closed

不能消費條件：

- `NO_MATCHED_FILLS` 是 valid blocker，不是 reward label；
- `RESEARCH_ONLY` / `PENDING_SCHEMA` / `INVALID` 不得進 reward ledger；
- no-fill packet 不得帶 fill ids、cost identity 或 reward/label 欄位。

### `demo_mutation_envelope.py`

File: `program_code/ml_training/demo_mutation_envelope.py`

現況：

- `DEMO_MUTATION_ENVELOPE_SCHEMA_VERSION = "demo_mutation_envelope_v1"`
- `STATUS_COUNTABLE = "countable_after_review"`
- `STATUS_AUDIT_ONLY = "review_audit_only"`
- `STATUS_INVALID = "invalid"`
- `ENGINE_MODE_DEMO = "demo"`
- `validate_demo_mutation_envelope(envelope)` 重算 countability
- `compute_demo_mutation_envelope_hash(envelope)` 對 canonical JSON 做 sha256，排除頂層 `envelope_sha256`
- `extract_demo_mutation_envelope(mapping)` 只讀 canonical `demo_mutation_envelope`

可消費條件：

- `validation.valid is True`
- `validation.status == STATUS_COUNTABLE`
- `validation.effective_learning_countable is True`
- `engine_mode == "demo"`
- `application.status == "applied"`
- `dedupe == false`
- `dry_run == false`
- proposed patch / previous snapshot / bounded delta / concrete max-delta policy present
- governance review allowed, rollback handle present, IPC status success, post-change review passed, proof linkage valid
- no authority expansion aliases, no live/mainnet/non-demo scope aliases

不能消費條件：

- `STATUS_AUDIT_ONLY` 可以保留審計，但 reward ledger must reject；
- non-demo / live / live_demo / mainnet / paper invalid；
- default applier mapping 的 `max_delta_pct=None` 會 audit-only，不能 count。

### `demo_mutation_envelope_applier_mapping.py`

File: `program_code/ml_training/demo_mutation_envelope_applier_mapping.py`

現況：

- 將 `mlde_demo_applier._record_application(...)` input pure-map 成 envelope；
- 不讀 DB、不呼叫 IPC、不接 exchange/provider/secret、不 rollback；
- default governance / rollback / proof linkage 不足時只產 valid audit-only envelope；
- explicit concrete bounds + governance + rollback + post-review + proof linkage 才能 count。

WP6 應只消費 payload 中 canonical `demo_mutation_envelope`，不得重新解讀 `_record_application` row 作為 reward authority。

### Tests

Relevant current tests:

- `program_code/ml_training/tests/test_proof_packet_contract.py`
- `program_code/ml_training/tests/test_demo_mutation_envelope.py`
- `program_code/ml_training/tests/test_demo_mutation_envelope_applier_mapping.py`
- `program_code/ml_training/tests/test_pit_dataset_manifest.py`
- `program_code/ml_training/tests/test_registry_serving_contract.py`
- `program_code/ml_training/tests/test_run_training_pipeline.py`
- `program_code/ml_training/tests/test_model_registry.py`

Existing coverage already proves:

- proof-ready requires candidate-matched fills, PIT manifest lineage, costs, controls, and hash integrity;
- no-fill is blocker-only, not learning label;
- cleanup/unattributed/proof-excluded fills fail;
- mutation envelopes are countable only after Demo applied + concrete bound + review/proof linkage;
- dry-run/dedupe/non-demo/live/paper cannot count;
- registry contract is advisory-only and exact q10/q50/q90 trio-bound.

## Recommended E1 Implementation Files

Primary new file:

- `program_code/ml_training/reward_ledger.py`

Primary new tests:

- `program_code/ml_training/tests/test_reward_ledger.py`

Optional fixture helper only if test duplication becomes noisy:

- keep local helper builders in `test_reward_ledger.py` first;
- do not add shared fixture module unless E1 shows repeated builders across 3+ files.

Do not modify in E1 unless required by compile/import wiring:

- `proof_packet_contract.py`
- `demo_mutation_envelope.py`
- `demo_mutation_envelope_applier_mapping.py`
- `run_training_pipeline.py`
- `model_registry.py`

Reason: WP6 should be a bridge/consumer contract. The existing upstream validators already own their domains; changing them risks widening their authority surface.

## `reward_ledger_v1` Contract

Recommended public surface:

```python
REWARD_LEDGER_FIELD = "reward_ledger"
REWARD_LEDGER_SCHEMA_VERSION = "reward_ledger_v1"

REWARD_RECORD_READY = "reward_record_ready"
REWARD_RECORD_REJECTED = "reward_record_rejected"
PENDING_SCHEMA = "pending_schema"
INVALID = "invalid"

@dataclass(frozen=True)
class RewardLedgerValidation:
    reward_ready: bool
    verdict: str
    reason: str
    reasons: tuple[str, ...]
    append_only: bool = True
    authority_boundary_violation: bool = False

def compute_reward_record_hash(record: Mapping[str, Any]) -> str: ...
def validate_reward_record(record: Any) -> RewardLedgerValidation: ...
def build_reward_record_from_proof_and_mutation(
    *,
    proof_packet: Mapping[str, Any],
    demo_mutation_envelope: Mapping[str, Any],
    effect_window: Mapping[str, Any],
    registry_serving_contract: Mapping[str, Any] | None = None,
    acceptance_report_ref: Mapping[str, Any] | None = None,
) -> dict[str, Any]: ...
def extract_reward_record(mapping: Any) -> Any: ...
```

Recommended record shape:

```json
{
  "schema_version": "reward_ledger_v1",
  "record_id": "reward:grid_trading|ETHUSDT|Buy:<proof_hash_prefix>:<envelope_hash_prefix>",
  "append_only": true,
  "verdict": "reward_record_ready",
  "candidate_identity": {
    "candidate_id": "grid_trading|ETHUSDT|Buy",
    "strategy_name": "grid_trading",
    "symbol": "ETHUSDT",
    "side": "Buy",
    "context_id": "ctx-entry-1"
  },
  "execution_identity": {
    "order_link_id": "...",
    "entry_context_id": "...",
    "exit_context_id": "...",
    "fill_ids": ["...", "..."],
    "liquidity_role": "maker|taker|mixed"
  },
  "cost_identity": {
    "maker_fee_bps": 0.0,
    "taker_fee_bps": 0.0,
    "slippage_bps": 0.0,
    "spread_bps": 0.0,
    "funding_bps": 0.0,
    "markout_bps": 0.0,
    "realized_net_pnl_bps": 0.0,
    "realized_net_pnl_usdt": 0.0
  },
  "reward": {
    "reward_kind": "after_cost_realized_demo",
    "net_pnl_bps": 0.0,
    "net_pnl_usdt": 0.0,
    "sample_weight": 1.0,
    "no_fill_reward": false,
    "cleanup_reward": false,
    "dry_run_reward": false
  },
  "controls": {
    "matched_control_ids": [],
    "regime_labels": {},
    "oos_split": {},
    "proof_exclusions": []
  },
  "lineage": {
    "proof_packet_hash": "<64hex>",
    "mutation_envelope_hash": "<64hex>",
    "pit_dataset_manifest_hash": "<64hex>",
    "registry_serving_contract_hash": "<64hex or empty>",
    "acceptance_report_hash": "<64hex or empty>",
    "code_commit": "<git sha>",
    "rust_build_sha": "<git/build sha>"
  },
  "mutation": {
    "envelope_id": "...",
    "source_proposal_or_recommendation_id": "...",
    "application_type": "...",
    "target": "...",
    "bounded_delta_hash": "<64hex>"
  },
  "effect_window": {
    "window_id": "effect:<candidate>:<start>:<end>",
    "start_ts": "2026-07-06T10:00:00Z",
    "end_ts": "2026-07-06T10:05:00Z",
    "observation_count": 1,
    "window_source": "offline_fixture|bounded_demo_packet",
    "point_in_time": true
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
    "serving_reload": false,
    "symlink_promotion": false
  },
  "record_hash": "<64hex>"
}
```

Field guidance:

- `record_hash` excludes only top-level `record_hash`, mirroring upstream contracts.
- `lineage.proof_packet_hash` must equal `proof_packet["proof_packet_hash"]` and recomputed `compute_proof_packet_hash(proof_packet)`.
- `lineage.mutation_envelope_hash` must equal `demo_mutation_envelope["envelope_sha256"]` and recomputed `compute_demo_mutation_envelope_hash(envelope)`.
- `lineage.pit_dataset_manifest_hash` should come from `proof_packet.provenance.pit_dataset_manifest.manifest_hash`.
- `lineage.registry_serving_contract_hash` is optional for source bridge but required when the reward is used to evaluate a contract-bound training mutation.
- `reward.net_pnl_bps/usdt` must copy from ProofPacket `cost_identity.realized_net_pnl_*`; never recompute from free-text labels.
- `effect_window.point_in_time` must be true; missing or open-ended windows reject.
- `no_authority` flags must all be false. Any truthy authority alias anywhere in record rejects.

## Candidate / Envelope Matching Rules

E1 should implement explicit matching, not inferred matching:

1. ProofPacket candidate:
   - `candidate_id`
   - `strategy_name`
   - `symbol`
   - `side`
   - `context_id`
2. Mutation envelope source:
   - `engine_mode == "demo"`
   - `source.source_payload_hash`
   - `source_proposal_or_recommendation_id`
   - optional source payload fields if present: `strategy_name`, `symbol`, `side`, `candidate_id`
3. Proof linkage:
   - envelope `proof_linkage.valid is True`
   - envelope `proof_linkage.proof_packet_hash == proof_packet["proof_packet_hash"]`

If envelope source payload contains candidate fields, all present fields must match ProofPacket candidate fields. If it lacks candidate fields, the bridge may still build a record only when `proof_linkage.proof_packet_hash` is exact and the envelope is countable; otherwise reject as `mutation_candidate_scope_missing_or_unmatched`.

## Fail-Closed Cases

Required explicit test cases:

1. Invalid ProofPacket:
   - `validate_proof_packet(...).proof_ready is False` -> reject.
2. No-fill:
   - `NO_MATCHED_FILLS` / `no_fill_blocker=True` -> reject, never zero/negative reward.
3. Unmatched candidate:
   - candidate id / strategy / symbol / side / entry context mismatch -> reject.
4. Cleanup / proof-excluded:
   - cleanup, unattributed, `proof_excluded`, `controls.proof_exclusions` -> reject via upstream validator and reward validator.
5. Non-demo / live:
   - envelope `engine_mode != "demo"` or nested live/mainnet scope -> reject.
6. Non-countable DemoMutationEnvelope:
   - audit-only, invalid, dry-run, skipped, failed, dedupe, missing review, missing proof linkage, non-concrete max delta -> reject.
7. Dedupe / replay:
   - same `(proof_packet_hash, mutation_envelope_hash, effect_window.window_id)` must produce same `record_id`; builder should not append duplicate in-memory batch.
   - Source-only bridge can expose `dedupe_reward_records(records)` or `validate_reward_batch(records)`; no DB uniqueness in WP6.
8. Mismatched candidate / envelope:
   - envelope proof linkage hash not equal to ProofPacket hash -> reject.
   - envelope source candidate fields conflict with ProofPacket -> reject.
9. Missing PIT lineage:
   - missing ProofPacket PIT manifest, missing `manifest_hash`, or registry hash required by caller but absent -> reject/pending.
10. Missing registry lineage:
   - for contract-bound mutation-effect learning, missing `registry_serving_contract_hash` -> reject as `registry_lineage_missing`.
   - for pure execution reward record, allow empty registry hash only with `lineage.registry_optional_reason = "execution_reward_not_training_contract_bound"`.
11. Authority expansion:
   - any truthy authority flag/alias in reward record, ProofPacket, envelope, effect window, lineage, or acceptance report ref -> reject.

## Source-Only Test Matrix

Focused commands for E1:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m py_compile \
  program_code/ml_training/reward_ledger.py \
  program_code/ml_training/proof_packet_contract.py \
  program_code/ml_training/demo_mutation_envelope.py \
  program_code/ml_training/registry_serving_contract.py
```

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q \
  program_code/ml_training/tests/test_reward_ledger.py \
  program_code/ml_training/tests/test_proof_packet_contract.py \
  program_code/ml_training/tests/test_demo_mutation_envelope.py \
  program_code/ml_training/tests/test_demo_mutation_envelope_applier_mapping.py \
  -p no:cacheprovider
```

Adjacency regression:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q \
  program_code/ml_training/tests/test_pit_dataset_manifest.py \
  program_code/ml_training/tests/test_registry_serving_contract.py \
  program_code/ml_training/tests/test_run_training_pipeline.py \
  program_code/ml_training/tests/test_model_registry.py \
  -p no:cacheprovider
```

Static source-only guard:

```bash
rg -n "psycopg2|asyncpg|requests|httpx|urllib|socket|subprocess|one_shot_ipc_call|ipc_dispatch|place_order|create_order|cancel_order|submit_order|INSERT INTO|UPDATE learning|DELETE FROM|os.environ|getenv" \
  program_code/ml_training/reward_ledger.py
```

Diff hygiene:

```bash
git diff --check -- \
  program_code/ml_training/reward_ledger.py \
  program_code/ml_training/tests/test_reward_ledger.py
```

## Denied Actions And Boundary

Denied in WP6 source-only pass:

- product/runtime DB reads or writes;
- migrations;
- runtime file reads under `/home/ncyu/BybitOpenClaw` or `/var/openclaw`;
- exchange/private reads;
- credential or secret access;
- MCP runtime/server/config changes;
- order/probe/bounded Demo invocation;
- Cost Gate changes;
- deploy/restart/rebuild;
- live/mainnet;
- model reload;
- symlink promotion;
- learning state mutation from real outcomes.

Allowed:

- additive source contract and tests under `program_code/ml_training/`;
- offline fixture builders in tests;
- PA/E1/E2/E4/QA reports;
- no-authority source-only hashes and validators.

## Side Effects And Review Points

Risk level: medium. It is a new cross-contract bridge, but source-only and additive if kept in a new module.

E2 must review:

1. No-fill / audit-only / dry-run / dedupe records cannot become numeric reward.
2. Candidate/envelope matching uses exact fields and proof hash equality; no fallback to symbol-only or latest artifact.
3. `reward_ledger.py` contains no DB/runtime/exchange/env/secrets/import side-effect surface.

Rollback:

- remove `program_code/ml_training/reward_ledger.py`;
- remove `program_code/ml_training/tests/test_reward_ledger.py`;
- no migrations, no runtime state, no DB state, no service restart.

## PA Verdict

`WP6-REWARD-LEDGER-PROOFPACKET-BRIDGE` is E1-ready in source-only mode.

It should land as an additive `reward_ledger_v1` validator/bridge. It must not consume real runtime outcomes until a separate PM->E3->BB runtime/loss-control packet is READY and candidate-matched bounded Demo ProofPackets exist.

PA DESIGN DONE: report path: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-07-07--wp6_reward_ledger_proofpacket_bridge_design.md`
