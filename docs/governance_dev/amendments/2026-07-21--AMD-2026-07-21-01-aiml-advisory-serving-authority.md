# AMD-2026-07-21-01: AIML Advisory Serving Authority

Date: 2026-07-21
Status: Accepted — S0.2 source-policy authority; no runtime/adoption effect
Related ADRs: ADR-0035, ADR-0049, ADR-0051
Amends by interpretation only: AMD-2026-07-09-02, AMD-2026-07-10-02,
AMD-2026-07-10-03

## Decision

S0.2 review 已接受本 AMD 與 ADR-0051 A1-A10，作為 future AIML model serving 的完整
source-policy authority envelope。它只建立 advisory-serving 的必要政策條件，不授予
runtime/deploy/activation/Demo/broker/order effect，也不代表 ML5/ML6 source 已實作或
`PROGRAM_ADOPTED`。S0.2 closure 的 immutable dependency 是
`docs/execution_plan/ai_ml_landing/receipts/S0.2-serving-authority-receipt-v1.json`；S0.3
必須消費該 exact receipt，不得由 ADR/AMD Accepted status 推論 adoption。

本 AMD 不修改三份 historical AMD 的 bytes。它只排除一個過寬解讀：既有
「ALR/challenger 不得 serving/promotion」不代表一個獨立、registry-authorized、hash-bound
且受 Rust superior gates 約束的 consumer 永遠不得在 later gated Session 載入 qualified
generation。所有 ALR/trainer/controller/challenger/legacy/direct-trading denial 保持原義。

## Binding Authority Projection

| Surface | Authorized only after all later gates | Still denied |
|---|---|---|
| Challenger production | ALR/trainer/controller 可產生 immutable qualified challenger/request | activation、serving、gate change、scope expansion、live mutation |
| Registry | 獨立 authority path 可在 later effect Session 對 exact expected-current/proposed identity 與 immutable `qualification_receipt_digest` 執行 epoch/request-bound CAS | `_latest`、path-only、hash-null、DB-only promotion、writer self-activation、replay/downgrade/任意 old-generation reactivation |
| Consumer | 只有 Rust `IntentProcessor + EdgePredictorStore` 可 exact-match model/feature/action-policy/runtime/scope/qualification lineage，並對 fresh pending transition ACK | Python/report/notebook/ALR/trainer/controller/legacy consumer 關閉 serving gate；stale/duplicate/cross-transition ACK |
| Policy output | 只對 Rust-classified risk-increasing entry 使用 `NO_OP`, `VETO`, `SIZE_DOWN`; serialized `ALLOW` 必須等同 `NO_OP` | deny-to-allow、size-up、symbol/side/venue/order-shape mutation，或干預 reduce-only/close/hedge/protective/liquidation-prevention/Guardian/OMS/reconciliation/cancel path |
| Rollback | Fault-triggered audited dedicated transition 只可回復 immediately previous committed qualified identity | ordinary activation 冒充 rollback、任意 downgrade 或 qualification-lineage substitution |
| Trading authority | 無 | exchange/broker contact、order、Decision Lease、risk/Cost Gate/Guardian/OMS bypass、live/mainnet、credential、direct parameter apply |

任何 later implementation 必須同時維持：

```text
final_allowed => baseline_allowed AND all_existing_gates_pass
final_notional <= baseline_notional
```

Decision Lease、Guardian、Rust `RiskConfig`、global Cost Gate、OMS 與 immutable audit
永遠優先。Model output、registry row、consumer ACK 或 performance evidence 都不能恢復被
任一 superior gate 拒絕的 authority。

## Scope And Consumer Protocol

1. 每個 generation 必須綁 exact `landing_scope_id`、`platform_scope`、
   `policy_surface_id`、covered `(symbol,side,horizon,regime)` decision cells、明列的
   evidence-environment promotion edges，以及 `intent_position_effect_class` classifier
   contract/digest、允許值和 policy mapping；相同 classification 內容也須被
   `action_policy_hash` 覆蓋。
2. Consumer load 必須 exact-match `model_hash + feature_contract_hash +
   action_policy_hash + runtime_digest + landing_scope_id + generation +
   qualification_receipt_digest`。Qualification root transitively 綁定 actual PIT dataset/
   rows、label revisions、code/data/config/model hashes、fit environment、walk-forward/OOS/
   leakage evidence 與 qualification verdict；缺失、mismatch 或無法重算即 fail closed。
3. Activation 必須為 `exact expected-current committed identity -> pending CAS -> matching
   Rust consumer ACK -> committed active identity`。Pending transition 同時綁 exact proposed
   identity/qualification root、scope-local unique monotonic `activation_epoch` 與 unique
   non-replayable `activation_request_id`。
4. ACK 必須 exact-bind pending transition、expected/proposed identities、epoch/request ID、
   consumer/process/runtime identity 與 freshness deadline。Stale、duplicate、late、cross-
   transition ACK、epoch regression、request replay、partial transition 或普通 reactivation
   任意 old generation 一律拒絕；active identity 保存 qualification root、epoch、request ID
   與 ACK digest。
5. Model contribution 只可用於 Rust-classified
   `intent_position_effect_class=RISK_INCREASING_ENTRY`。Reduce-only、close、hedge、
   stop/protective、liquidation-prevention、Guardian/OMS/reconciliation/cancel 及任何
   risk-reduction path 強制 `NO_OP`/bypass model。Unknown/missing classification 停用 model，
   但不得阻擋 protected risk reduction。
6. Unknown/mixed/uncovered scope、undeclared edge 或 hash drift 必須停用 model
   contribution；不得擴大推論。
7. 任何 bounded-Demo policy-affecting activation 另須 fresh、同一 SHA/scope/generation/
   qualification/transition 綁定的 `PM -> E3 -> BB` effect gate。Shadow activation 也不能
   省略 CAS/ACK。

## Retraining, Rollback And Fallback

Natural controller 只可在 qualified/hash-bound evidence、budget、cooldown、idempotency
成立時產生 `NEW_CHALLENGER | NO_CHANGE | REJECT_NO_PROMOTION`。三種 outcome 均無
activation/serving/gate/scope/live/broker/order authority；`NEW_CHALLENGER` 也只進隔離
registry。

Stale/missing/corrupt/mismatched artifact、qualification lineage failure、scope drift、
missing/non-matching ACK、SLO breach、restart-recovery failure 或 partial CAS 必須保留
current committed identity，或只經 fault-triggered、audited、dedicated rollback transition
回復 immediately previous committed qualified identity。Rollback exact-binds 該 identity 的
原始 `qualification_receipt_digest`，並使用新的 monotonic epoch、non-replayable request 與
fresh ACK；不得選任意舊 generation，ordinary activation 也不得冒充 rollback/downgrade。

若不存在 valid previous generation，只可使用 qualified、hash-bound `action_policy_hash`
fallback；已分類的 risk-increasing entry 預設 `VETO`，risk-reduction path 則固定
`NO_OP`/bypass model。Unknown classification 停用 model contribution，但不得阻斷 protected
risk reduction。`_latest`、path-only、hash-null、DB-only 與 unreviewed legacy path 永遠不得
作為 fallback 或 active identity。

## Exact Historical-Clause Binding

下列是本 AMD accepted authority 唯一允許的 supersession projection；未列出的 legacy
clause 不受影響：

| Source and exact clause label | Retained rule | Accepted narrow supersession |
|---|---|---|
| ADR-0049 `Decision` 3 | Scanner intake evidence 不是 serving/trading/profit authority。 | 不把 scanner 的 no-authority 擴張成 A2 independent consumer 的永久禁令。 |
| ADR-0049 `Decision` 6 | ALR training 只產 challenger；ALR 不得 serve/promote/`_latest`/risk/lease/decision。 | 不把 ALR actor denial 套用到 later A2 Rust consumer。 |
| ADR-0049 `Explicit Non-Goals` 2 | P2/ALR 無 model auto-serving/promotion、`_latest` 或 trading authority。 | A2-A8 future gated consumer 不被誤分類為 ALR auto-serving。 |
| ADR-0049 `2026-07-10 V3 Freshness And Learning Completion Addendum / Learning, Retention, And Terminal Truth` | Outputs challenger-only，永不 auto-serve/auto-promote。 | Qualified challenger 可成為 separate activation request input。 |
| ADR-0049 `2026-07-10 Global Qualified Autonomous Learning Shadow V1 Addendum` | `CHALLENGER_ACCEPT` 無 serving/promotion/lease/risk/order authority。 | 不禁止其後由 separate authority path 重新 qualification。 |
| AMD-2026-07-09-02 `Invariants` 3 | ALR output 不 auto-serve/promote/`_latest`。 | 不延伸到 A2 independent consumer。 |
| AMD-2026-07-09-02 `Invariants` 6 | ALR service 的 serving/promotion/trading authority counters 保持 zero。 | Independent consumer 必須有另行治理的 typed state，不能冒充 ALR counter。 |
| AMD-2026-07-09-02 `Prohibitions That Remain` 1 | ALR 無 exchange/order/risk/direct-serving authority。 | 無；本 prohibition 對 ALR 完整保留。 |
| AMD-2026-07-10-02 `Qualified Learning Contract` bullet 3 | Output challenger-only，無 auto-serving/auto-promotion/`_latest`。 | Separate later activation 不等於 retraining auto-promotion。 |
| AMD-2026-07-10-02 `Hard Boundaries Retained` bullet 5 | ALR 不 auto-serve/promote/`_latest`。 | 不延伸到符合 A1-A10 的 independent consumer。 |
| AMD-2026-07-10-02 `Hard Boundaries Retained` bullet 7 | ALR authority maps/counters 保持 false/zero。 | Independent consumer state 必須另行 hash-bound，不能覆寫此歷史 ALR truth。 |
| AMD-2026-07-10-03 `Qualified completion contract` G6 | `CHALLENGER_ACCEPT` 只進隔離 registry。 | 允許後續 separate qualification/activation request；不自動 active。 |
| AMD-2026-07-10-03 `Qualified completion contract` G8 | Artifact 可消費但受 lineage/retention contract。 | Consumer 只能依 A2/A5 exact identity 消費。 |
| AMD-2026-07-10-03 `Qualified completion contract` G9 | AI output 不是 trading instruction；Rust/gates/audit superior。 | 無；完整保留並由 advisory monotonicity 加強。 |
| AMD-2026-07-10-03 `External-effect gate retained` | Demo/order evidence 需 fresh exact E3/BB/Operator gate；ALR 無 Bybit/order action。 | A7 只增加 activation prerequisite，不消除任何 external-effect gate。 |
| AMD-2026-07-10-03 `No-authority contract` | ALR 無 serving/promotion/trading/direct-apply authority。 | 不把 ALR denial 延伸成 A2 independent consumer 的永久禁令。 |

## Permanent Denials

無論 model 類型、品質、PnL、review、registry status 或 consumer ACK，model、LLM、RL、
ALR、trainer、controller、challenger、registry writer 與 consumer 均不取得：

- exchange/broker/private trading contact；
- order create/probe/submit/cancel/modify/close/dispatch；
- Decision Lease mint/change/bypass；
- Guardian、Rust `RiskConfig`、global Cost Gate 或 OMS mutation/relaxation/bypass；
- live/mainnet、credential、external-effect approval；
- direct parameter apply、strategy/runtime config mutation 或 Rust authority bypass。

## S0.2 Effect And Adoption Boundary

```text
session_id=S0.2
side_effect_class=NONE
runtime_effect=false
deploy_effect=false
migration_effect=false
postgres_effect=false
broker_effect=false
order_effect=false
ml5_ml6_implementation=false
program_adopted=false
```

S0.2 closure 的 immutable、self-digested `serving_authority_receipt_v1` 寫入
`docs/execution_plan/ai_ml_landing/receipts/S0.2-serving-authority-receipt-v1.json`，並綁定
exact ADR/AMD bytes、review fragments、task contract、source generation 與上述 zero-effect
projection。S0.3 必須消費該 exact receipt，不得由 source-policy status 推論 adoption；
該 receipt 不是 runtime、activation、Demo 或 trading receipt。只有 S0.3 能在
governance schemas、Registry/router/closure integration 與 external GitHub repository-
policy attestation 通過後簽發 `program_adoption_receipt_v1`。

## Review And Sign-Off

| Role | Status | Accepted basis |
|---|---|---|
| PA | Accepted | Design: actor separation, single Rust consumer, monotone advisory authority and exact legacy-clause projection. |
| R4 | Accepted | ADR/AMD consistency PASS; `R4-S0.2-P1-INDEX-ACTIVE-STATE-DUPLICATION` repaired and exact-rechecked. |
| CC | Accepted | Risk-reduction non-interference and superior-authority preservation blockers resolved under `review_control sha256:2295f30022904282b723ddbbbbed0ac10ec3f77275b68fe83c770c646c1bbfb2`. |
| E3 | Accepted | CAS/ACK anti-replay, downgrade denial and dedicated rollback blockers resolved under `review_control sha256:2295f30022904282b723ddbbbbed0ac10ec3f77275b68fe83c770c646c1bbfb2`. |
| MIT | Accepted | Qualification-lineage and advisory-semantics blockers resolved under `review_control sha256:2295f30022904282b723ddbbbbed0ac10ec3f77275b68fe83c770c646c1bbfb2`. |
| QA | Accepted | Source-policy acceptance PASS using Context `sha256:f39c11b4db680dec6ee626e80a9a54c2b190dd6682eb0297fb0b1d0ace0dadb4`. |
| PM | Accepted | Final S0.2 source-policy adjudication; closure completes the exact receipt binding with `side_effect_class=NONE`. |

All required source-policy reviews are Accepted. The receipt at
`docs/execution_plan/ai_ml_landing/receipts/S0.2-serving-authority-receipt-v1.json` is the
immutable S0.3 dependency; S0.3 must consume that receipt rather than infer adoption from this
AMD's Accepted status.
