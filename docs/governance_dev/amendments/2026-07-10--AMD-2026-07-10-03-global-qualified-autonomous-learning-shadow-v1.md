# AMD-2026-07-10-03：Global Qualified Autonomous Learning Shadow V1

Date: 2026-07-10
Status: Accepted — implementation active
Related ADRs: ADR-0017, ADR-0035, ADR-0049
Supersedes: AMD-2026-07-10-02 `Terminal State And Exact Packet Binding`
and ALR P2 queue v2 terminal/SUI-consumption semantics only

## Decision

Operator 啟動持續 Codex Goal
`GLOBAL_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW_V1`。ALR 不得再以 freshness
soak、source-only 完成、單一 `DEFER_EVIDENCE`、無 eligible cache、backlog
exhausted，或等待舊 exact Demo packet 作為終點；Goal 必須持續推進至 G1-G9
均有當下 machine evidence。

本修訂只取代 AMD-2026-07-10-02 的舊 terminal／SUI packet binding，以及
`docs/execution_plan/2026-07-10--alr-operational-shadow-p2-queue-v2.md` 的相同
terminal 解讀。AMD-02 的 fresh-lane、truthful health、adversarial acceptance、
qualified-learning、retention、hard-boundary 條款全部保留有效。舊 queue、AMD、
packet 與 E3/BB reviews 保持 immutable historical evidence，不得編輯或刪除。

本 Goal 是工程與 learning-shadow 授權，不是尚未存在的候選、Demo、exchange、
order 或 risk authority。任何外部效果仍依本修訂的 fresh exact gate 執行。

## Qualified completion contract

`DONE_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW` 必須同時滿足：

1. **G1 Collection**：scanner、市場、decision/order/fill、fee/slippage/funding、
   risk context 具完整 identity、時間、hash、freshness、restart lineage。
2. **G2 Selection**：候選以 strategy+version/config hash、symbol、side、horizon、
   regime 與 decision context 完整識別；使用 distinct-entry `n_eff`、UTC-day /
   top-day / regime coverage、data quality、proof gap、EVI、compute/storage cost、
   cooldown；無合格候選時也必須 lawful global rotate/collect，不能停機。
3. **G3 Outcome**：至少一條真實 current candidate-matched PIT manifest ->
   controlled Rust order/fill -> actual fee/slippage/funding -> reconstruction ->
   `proof_packet_v1` -> `reward_ledger_v1` -> after-cost label 完整閉環。單一鏈只證
   integration，不等於 training sample sufficiency。
4. **G4 Training**：只有通過預註冊 sample eligibility 的資料可實際 fit；產出
   rebuildable artifact/features/metrics 及 code/data/config/model hashes，寫入隔離
   challenger registry；`model_training_performed=true` 不可由 fixture 或空 run 冒充。
5. **G5 Evaluation**：實際 walk-forward、purge/embargo、hidden OOS、matched
   controls、negative cells、regime/stress、leakage 與 dedup 防線全有 lineage。
6. **G6 Decision**：持久化 `DEFER`, `ROTATE`, `TRAIN`, `REJECT`,
   `CHALLENGER_ACCEPT`, `ROLLBACK`, `STOP` 的 reason 與 evidence hash。
   `CHALLENGER_ACCEPT` 只進隔離 registry，不是 serving/promotion/order authority。
7. **G7 Auto-evolution**：第二個 distinct evidence-delta hash 到達後，系統在
   cooldown/idempotency 規則下自動 re-evaluate/retrain/rotate，並留下可解釋 change。
8. **G8 Artifacts/retention**：event-driven consumer 有真實 transition、delta/dedupe/
   cooldown/budget；model/evaluation/registry/effect artifacts 可消費；retention 只可
   對 ALR-owned、rebuildable、unreferenced derived cache 執行 reference graph ->
   quarantine -> grace/recheck -> sweep。Proof/Reward/negative/dispute/OOS/control/
   order/fill/cost/audit/authorization/risk/reconciliation/lineage 永不 ordinary-delete。
9. **G9 Boundaries**：AI output 永遠不是交易指令；ALR 無 trade/live/RiskConfig/
   Guardian/global Cost Gate/Decision Lease/serving/promotion/`_latest`/direct parameter
   authority。Rust authority、Guardian、Decision Lease、GUI RiskConfig、audit 與本地+
   交易所側災難保護仍完整存在。

Training/inference 每輪另須記錄 compute cost、latency、energy/API budget，預設不使用
付費外部服務並保留 local zero-paid-service fallback；候選與 effect review 必須包含
portfolio exposure、correlation cluster、strategy overlap、capital allocation context。

## Work packages and loop state

Canonical queue:
`docs/CCAgentWorkSpace/PM/workspace/ai_ml_todo_stub/2026-07-10--global_qualified_autonomous_learning_shadow_v1/queue.md`。
WP0-WP7 依序涵蓋 governance/baseline、artifact churn、candidate arbiter、proof/reward
bridge、actual training/registry、OOS/decision、event-driven evolution/retention、final
adversarial audit。每輪必須更新 `queue.md`, `manifest.json`,
`loop_state_packet.json`, `effect_review.json`，以及 PM/Operator 摘要。

既有 V152/V153 bytes 不可修改；下一 migration 僅在 fresh collision scan 與 exact
E3/BB gate 後才可 reserve/create/apply。Source/test 工作走 `PA -> E1 -> E2 -> E4 ->
QA`；quant/ML semantics 走 `QC -> MIT -> AI-E`；governance/retention/authority 走
`CC -> FA -> PA`。

## Superseded SUI and NEAR evidence

舊 SUI packet：

```text
status=ROTATED_UNCONSUMABLE_STALE_PACKET
packet_sha256=1ab349a6f753e4d3846b0699d7404f18e231d8ca95b8f250bb19b9f89b7eabde
consumable=false
operator_decision_requested=false
reasons=[
  SOURCE_HEAD_DRIFT,
  CURRENT_CANDIDATE_NOT_SUI,
  CURRENT_GUI_RUST_RISKCONFIG_EQUITY_CAP_LINEAGE_INVALID,
  CURRENT_GUARDIAN_BBO_ORDER_SHAPE_LINEAGE_INVALID,
  E3_BB_REVIEWS_PRESENTATION_ONLY_AND_STALE
]
```

NEAR evidence：

```text
status=FROZEN_INVALIDATED_EFFECTIVE_SAMPLE
n_raw=5058
distinct_entry_ts=2
n_eff=1
utc_days=1
verdicts=[SAMPLE_INSUFFICIENT_AFTER_DEDUP,EXECUTION_REALISM_SUSPECT]
edge_claim_allowed=false
no_edge_claim_allowed=false
order_dispatch_allowed=false
```

重開任何候選須由新證據通過已落地的 WP-A.6 preregistered gates，並綁定當下完整
lineage；過往 READY/order-capable artifact 不可消費。

## Terminal states

合法 Goal terminal 只有：

- `DONE_QUALIFIED_AUTONOMOUS_LEARNING_SHADOW`：G1-G9 全部 current machine PASS。
- `HARD_BLOCKED_OPERATOR_ACTION_REQUIRED_CURRENT`：同一 hash-bound、當下仍有效、
  只能由 Operator 完成的 action 連續三個 Goal turns 重複成立，且 safe-work inventory
  每輪重掃均為空。
- `SAFETY_ABORT_BOUNDARY_CONFLICT`：具體 requested action 與 hard boundary 衝突，
  已列出未執行 action，且無安全 narrowing。

`ADVANCED`, `DEFER_EVIDENCE`, `NO_ELIGIBLE_CACHE`,
`WAIT_OPERATOR_DEMO_AUTH_EXACT`, `DONE_SOURCE_ONLY`,
`DONE_OPERATIONAL_SHADOW`, `BACKLOG_EXHAUSTED` 全部是 nonterminal。

## External-effect gate retained

本 Goal 不可替代 exact Operator authorization。任何未來 G3 Demo/order 取證必須先有
當下 qualified candidate，再取得 fresh SHA-bound E3/BB review 與 Operator 對同一
SHA 的明確批准，並在同一 invocation window 重驗 GUI/Rust RiskConfig、accepted
equity、Guardian、Decision Lease、fresh BBO/instrument/order shape、本地與交易所側保護、
audit 與 reconstruction。ALR 不得自行接觸 Bybit 或發出 order/probe/cancel/modify/close。

## No-authority contract

ALR may write only validated `learning.alr_*` evidence, challenger-registry,
health/state, and gated derived-cache retention records. ProofPacket/Reward
generation is evidence production, not promotion authority. ALR has no
exchange, trading, order/probe, Decision Lease, Guardian mutation, RiskConfig
mutation, global Cost Gate, live/mainnet, serving, promotion, `_latest`,
protected-evidence deletion, or direct parameter-apply authority.

## Sign-off

| Role | Status | Basis |
|---|---|---|
| Operator | Accepted | Explicit Goal directive on 2026-07-10 |
| PM | Active owner | Goal thread and WP0 state packets |
| CC | Conditional approve | Source-only reconciliation; no runtime/order authority |
| FA | Conditional accept | Same-checkpoint functional reconciliation required |
| PA | Accepted | WP0 architecture/dispatch PASS; WP1 suppression safety proof required |
