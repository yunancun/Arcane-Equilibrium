# ADR-0051: Registry-Authorized Advisory Model Serving

Date: 2026-07-21
Status: Accepted — S0.2 source-policy authority; no runtime/adoption effect
Related: ADR-0017, ADR-0035, ADR-0049, AMD-2026-07-09-02,
AMD-2026-07-10-02, AMD-2026-07-10-03

## Context

ADR-0049 與三份 ALR AMD 正確地禁止 ALR、trainer、controller 與 challenger
自行 serving、promotion、覆寫 `_latest` 或取得交易權限。AI/ML V2 落地計畫同時要求
後續 ML5/ML5A 經由一條獨立、registry-authorized、hash-bound 的 Rust consumer path
消費已合格 model。若不先分開「產生 challenger」與「獲授權的 advisory consumer」兩種
actor，後續實作不是違反既有 no-serving 條款，就是把 no-authority 邊界含糊放寬。

本 ADR 已由 S0.2 review 接受為後續 Session 可實作的 source-policy authority contract。
S0.2 closure 的 immutable dependency 是
`docs/execution_plan/ai_ml_landing/receipts/S0.2-serving-authority-receipt-v1.json`；S0.3
必須消費該 exact receipt，不得由 ADR/AMD Accepted status 推論 program adoption。
Source-policy acceptance 不代表 ML5/ML6 source 已實作、runtime 已部署、model 已啟用、
Demo 已授權，或 program 已採納。

## Decision

### A1. Actor separation

ALR、trainer、natural-learning controller 與 challenger-registry writer 只可收集、fit、
evaluate，並寫入 immutable challenger 或 activation request。它們不得 load 或 apply
model、切換 active generation、寫 consumer ACK、改變 policy gate、鑄造 Decision Lease、
接觸 broker/exchange，或直接／間接發出 order。

`NEW_CHALLENGER` 只代表新的隔離候選。它不是 serving、activation、promotion、Demo、
live 或 trading authority。

### A2. Single hash-bound Rust consumer

在 current Rust engine scope，唯一可合格的 model consumer 是 Rust
`IntentProcessor + EdgePredictorStore`。Python、report、notebook、trainer、controller、
registry writer 或 legacy process 的讀取結果都不能滿足 serving gate。

Consumer 每次 load 必須同時驗證並綁定：

- `model_hash`；
- `feature_contract_hash`；
- `action_policy_hash`；
- `runtime_digest`；
- `landing_scope_id`；
- immutable `qualification_receipt_digest`；
- registry generation 與 immutable artifact identity。

`qualification_receipt_digest` 是 generation identity 的 immutable canonical lineage root；
它 transitively 綁定實際 PIT dataset/row identity、label revisions、code/data/config/model
hashes、fit environment、walk-forward/OOS/leakage evidence 與 qualification verdict。它必須
出現在 proposed generation、pending CAS、consumer ACK、committed active identity，以及
previous committed rollback identity；缺失、mismatch 或任何 transitive lineage 無法重算
都必須 fail closed。

Registry activation 採 two-phase protocol：先以 compare-and-swap（CAS）把完整 expected-
current identity 與完整 proposed generation identity 寫成一個 pending transition，再由
上述 Rust consumer 對同一組 hashes、scope、qualification lineage、generation 與
transition identity 寫入 ACK；只有 matching fresh ACK 被 commit 後才可成為 active。
DB/registry 單邊的 promotion row 不構成 active serving。

### A3. Advisory action is monotone

Model 的規範輸出集合只有 `NO_OP | VETO | SIZE_DOWN`。Serialized `ALLOW` 只可解析為
`NO_OP`，不得成為可把 baseline deny 改成 allow 的第四種 action。

Model contribution 只可套用於 Rust authoritative classifier 明確標為
`intent_position_effect_class=RISK_INCREASING_ENTRY` 的 entry intent。Reduce-only、close、
hedge、stop/protective、liquidation-prevention、Guardian/OMS/reconciliation/cancel 及任何
risk-reduction path 必須強制 `NO_OP` 或完全 bypass model；model 不得 veto、延遲或縮減
這些保護動作。Unknown/missing classification 必須停用 model contribution，但不得阻擋由
Rust/Guardian/OMS 已識別的 risk-reduction path。

對每一 decision event，實作必須滿足：

```text
final_allowed => baseline_allowed AND all_existing_gates_pass
final_notional <= baseline_notional
```

`NO_OP` 保留 baseline 與既有 gate 結果；`VETO` 只可拒絕；`SIZE_DOWN` 只可減少原本已
被允許的 notional。Model 不得改變 symbol、side、venue、instrument class、order type、
time-in-force 或把任何 false/deny/error/stale 狀態變成 allow。

### A4. Existing authority remains superior

Decision Lease、Guardian、Rust `RiskConfig`、global Cost Gate、OMS 與 immutable audit
仍是 superior authority。Model、registry、consumer ACK 或 action-policy receipt 均不能
覆寫、降低、跳過或替代它們。任一 superior gate deny、stale、missing、invalid 或
fail-closed 時，final decision 仍須 deny，且 model result 不能恢復 authority。

### A5. Exact scope confinement

每個可消費 generation 必須綁定一個 exact `landing_scope_id`，其內容至少包括：

- `platform_scope=(venue,instrument_class,strategy_family)`；
- hash-bound `policy_surface_id`；
- 明列的 covered `decision_cell=(symbol,side,horizon,regime)` 集合；
- 明列的 evidence-environment promotion edges；
- exact `intent_position_effect_class` classifier contract/digest、允許值及 per-value policy
  mapping；同一內容亦須被 `action_policy_hash` 覆蓋。

Unknown scope、mixed scope、uncovered cell、未聲明 promotion edge、scope/hash drift 或無法
重建的 policy surface，一律停用 model contribution，不能以較寬的 platform、strategy、
symbol 或 regime 推論補足。Unknown/missing `intent_position_effect_class` 同樣停用 model，
但 A3 的 risk-reduction non-interference 永遠優先。

### A6. Autonomous retraining boundary

Natural controller-triggered retraining 只有在 qualified、hash-bound evidence、budget、
cooldown 與 idempotency rules 全部成立時才可執行。每次 attempt 只可產生：

```text
NEW_CHALLENGER | NO_CHANGE | REJECT_NO_PROMOTION
```

三種結果都不得自行 activate、serve、改變 gate、擴張 scope、改變 live state 或進行
broker/order effect。`NO_CHANGE` 與 `REJECT_NO_PROMOTION` 是合法終局；
`NEW_CHALLENGER` 只可進入隔離 registry，並須重新通過後續 qualification 與 activation
authority。

### A7. Activation boundary

任何 shadow activation 都須通過 A2 的 exact CAS + matching consumer ACK。每一 pending
transition 必須綁定：

- exact expected-current committed identity，包括其 `qualification_receipt_digest`；
- exact proposed identity，包括新的 `qualification_receipt_digest`；
- 在同一 `landing_scope_id` 內唯一且嚴格遞增的 `activation_epoch`；
- unique、non-replayable `activation_request_id`。

Consumer ACK 必須綁定該 exact pending transition、expected/proposed identities、epoch、
request ID、consumer/process/runtime identity 與 freshness deadline。Stale、duplicate、
late 或跨 transition ACK、epoch regression、request replay，以及把任意已 superseded/retired
old generation 當成普通 activation 的要求，一律拒絕。Committed active identity 必須保存
qualification root、epoch、request ID 與 ACK digest，不能只保存 model path 或 generation
number。

任何會改變 bounded-Demo policy decision path 的 activation，另須在 effect 當下取得
fresh、同一 SHA/scope/generation/qualification/transition 綁定的 `PM -> E3 -> BB` gate，
並走後續已驗證的 effect Adapter。

Model generation activation 不等於 strategy、environment、Demo、live、broker 或 order
promotion。此 ADR 不提供 Operator authorization，也不使過期或 presentation-only review
重新有效。

### A8. Fail-closed rollback and fallback

Hash mismatch、stale/missing/corrupt artifact、scope drift、invalid registry state、missing
或 non-matching ACK、consumer deadline/SLO breach、restart-recovery failure 或 partial CAS
都必須保留 current committed identity，或只經 fault-triggered、audited、dedicated rollback
transition 原子回復到 immediately previous committed qualified identity。Rollback target
必須 exact-match 其原始 `qualification_receipt_digest` 與完整 identity，並產生新的 monotonic
`activation_epoch`、non-replayable request 與 fresh consumer ACK；不得選擇任意更舊
generation。Ordinary activation 不得冒充 rollback、downgrade 或 reactivation。

若沒有 valid previous committed generation，唯一可用的是 qualified、hash-bound
`action_policy_hash` fallback；對已分類的 risk-increasing entry，其預設 action 必須是
`VETO`。A3 所列 risk-reduction path 則一律 `NO_OP`/bypass model，不能被 fallback VETO
阻擋。Unknown classification 停用 model contribution，而不阻斷 protected risk reduction。
Fallback 不得放寬 baseline，也不得從 model path 猜測 action。永遠禁止 `_latest`、
path-only、hash-null、DB-only、unreviewed legacy writer/consumer 或未綁定 scope/qualification
lineage 的 artifact。

### A9. Permanent denial of direct trading authority

以下 denial 對 model、LLM、RL policy、ALR、trainer、controller、challenger、registry writer
與 model consumer 永久有效，不能由 evidence、performance、ACK 或本 ADR 自動解除：

- 不得接觸 exchange/broker 或呼叫 private/authenticated trading surface；
- 不得 create、submit、probe、cancel、modify、close 或 dispatch order；
- 不得 mint、alter 或 bypass Decision Lease；
- 不得 mutate、relax 或 bypass Guardian、Rust `RiskConfig`、global Cost Gate 或 OMS；
- 不得進入 live/mainnet、取得 credential authority 或自行批准 external effect；
- 不得直接 apply parameter、改寫 strategy/runtime config，或繞過 Rust authority path。

### A10. S0.2 has no effect authority

本 Session 的 `side_effect_class` 是 `NONE`。S0.2 不執行 runtime、deploy、migration、
PostgreSQL、broker、exchange 或 order effect，不實作 ML5/ML6，也不簽發
`PROGRAM_ADOPTED`。只有 S0.3 可在 scope/session/effect schemas、Registry/router/closure
integration 與 external repository-policy attestation 全部通過後簽發
`program_adoption_receipt_v1`。

## Clause-Level Supersession

本 ADR 的 accepted authority 只 supersede 下表所列文字的一種過寬解讀：把
「ALR/challenger 不得
serving/promotion」解讀為永遠禁止一個獨立、registry-authorized、符合 A1-A10 的 Rust
consumer 載入 qualified generation。歷史文件 bytes 不修改；其對 ALR、trainer、
controller、challenger、legacy path、direct trading authority 與 `_latest` 的 denial 全部
保留。

| Historical clause | Accepted exact disposition |
|---|---|
| ADR-0049 `Decision` 3 | 保留 scanner evidence 不是 serving/trading authority；不阻止 A2 的獨立 consumer。 |
| ADR-0049 `Decision` 6 | 對 ALR training/challenger 完整保留；只排除「任何獨立 authorized consumer 也永遠不能 serve」的過寬解讀。 |
| ADR-0049 `Explicit Non-Goals` 2 | 對 P2/ALR、auto-promotion、`_latest` 與 trading authority 完整保留；A2-A8 的 later gated consumer 不是 ALR auto-serving。 |
| ADR-0049 `2026-07-10 V3 Freshness And Learning Completion Addendum / Learning, Retention, And Terminal Truth` | Challenger-only 與 no-auto-serve/no-auto-promote 保留；後續 activation 必須另走 A2/A7。 |
| ADR-0049 `2026-07-10 Global Qualified Autonomous Learning Shadow V1 Addendum` | `CHALLENGER_ACCEPT` 無 serving/promotion authority 完整保留；它只能成為後續 qualification input。 |
| AMD-2026-07-09-02 `Invariants` 3 and 6 | 對 ALR outputs 與 ALR service authority counters 完整保留；獨立 consumer 的 authority/counters 必須另行治理。 |
| AMD-2026-07-09-02 `Prohibitions That Remain` 1 | ALR auto-serving/promotion、`_latest`、exchange/order/risk authority denial 完整保留。 |
| AMD-2026-07-10-02 `Qualified Learning Contract` bullet 3 | Challenger-only/no-auto-serving/no-auto-promotion 完整保留；A6 明確把 retraining 與 activation 分離。 |
| AMD-2026-07-10-02 `Hard Boundaries Retained` bullets 5 and 7 | 對 ALR、authority maps/counters 與 `_latest` 完整保留；不授予 consumer trading authority。 |
| AMD-2026-07-10-03 `Qualified completion contract` G6, G8 and G9 | `CHALLENGER_ACCEPT`、artifact consumability 與 AI-not-an-order 邊界完整保留；later consumer 仍受 A2-A9。 |
| AMD-2026-07-10-03 `External-effect gate retained` and `No-authority contract` | 完整保留；A7 只增加 future activation 的必要 gate，不提供 effect 或 broker/order authority。 |

## Consequences

- ML5/ML5A 有單一可驗證的 future serving path，不需要把 ALR 變成 serving actor。
- ML6 只能增加 veto 或縮小 size，不能形成新的 allow/risk/order authority。
- Natural retraining 與 activation 被拆成不同 authority/effect state machine。
- Safe rollback 具有 exact previous-generation lineage；沒有有效 generation 時預設 VETO。
- S0.2 source-policy acceptance 與 closure-bound receipt 只證明 authority lineage；兩者
  都不能作為 ML5/ML6 source、runtime、Demo、profit、live 或 program-adoption 證據。
