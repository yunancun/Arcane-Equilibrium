# ADR-0050: Development-Agent Governance Module

Status: Accepted
Date: 2026-07-10

## Context

開發 sub-agent 已形成 18 個名稱、Claude/Codex/profile 三層定義、固定 chain、每角色
memory/report、兩種收尾協議與 universal preload。實測 declared Codex boot 約 40 萬
chars，role chain 在讀 task/source 前已暴露約 0.8M token 級內容；`.codex/MEMORY.md`
偏離約 300 行目標至近 2,000 行；role reports 超過 3,000 檔。

主要問題是淺 Interface 重複，而非模型不夠智能：

- wrapper/canonical/profile 已漂移，權限與完成序列相互矛盾。
- 固定 4k/task、30k/session 與複雜工作一次做對的需要衝突。
- 固定 chain 同時又被其他規則描述為 conditional。
- PM 同時 supervise deploy 與 final sign-off，operations 無獨立 owner。
- BB 只覆蓋 Bybit，但 ADR-0048 IBKR lane 已有真實 queue。
- Full Audit verification fan-out 無 admission envelope；contextPath 被錯稱只付一次。
- 每角色自寫 memory/report 造成 token annuity、dirty-tree race 與 dissent 遺失。

開發 sub-agent 與 Local 5-Agent trading runtime 是不同 vocabulary；本 ADR 不新增第六個
trading Agent，也不授予任何 order/Decision Lease authority。

## Decision

採用一個深的 `Development-Agent Governance Module`，暴露四個 Interface：Registry、
Context、Dispatch、Closure。機器正本為 `.codex/agent_registry_v1.json`，可執行工具為
`helper_scripts/maintenance_scripts/agent_governance.py`。

### Role model

角色名稱改為四個 execution mode 上的 capability preset：Conductor、Investigator、
Builder、Verifier。Claude/Codex/profile 都由 Registry 生成；平台 runtime type 不代表
智能等級。

新增 `OPS(explorer)` 與 `IB(explorer)` preset：

- OPS 僅負責 operations preflight/rollback/postcheck/RCA，絕不 apply。
- IB 是 Broker Compatibility Interface 的 IBKR Adapter reviewer；BB 是 Bybit Adapter。

兩者都唯讀。任何 Deploy/broker contact 只有在 closure-admissible deterministic effect
Adapter 存在時才可能進入 effect；目前 deploy 是 intent-only、broker contact unsupported。

### Dispatch

固定 chain 改為 hybrid risk-DAG。Implementation→E2→E4、authority/security、runtime/
operations、venue adapter、quant/ML semantics、E2E acceptance 是 hard facts 驅動的 edge；
其他 node 依 expected decision gain 與 residual risk advisory 加入。Unknown risk fail-safe
升 full-audit envelope。任何 skip 記 reason/residual risk/owner。

### Context and consumption

Universal preload 退役。Context Interface 保留 exact task prompt、user objective/scope/
acceptance/hard stops、必填 uncertainty、baseline/direct interfaces/previous failure。Concrete source 由 compiler 讀 bytes；
virtual evidence 必須是 source/observed-at typed、byte-backed artifact，caller digest 只是
assertion。Saved workflow 不再信任 raw contextPath，而是直接驗證 Python-canonical context
bytes 並消費同一份 inline artifact，retry 不 reopen path，也不做跨語言 canonicalization。
Budget 使用 elastic target/reserve + reviewed band，並分開 exact prompt-byte、UTF8/4 planned
lower-bound、workflow、unique-node、attempt、retry authority；到 cap 才拆分或升級，不截
mandatory context。Planned lower bound 不冒充 actual provider tokens。Full Audit 可合理使用
更大 reserve；超 cap 僅輸出 non-authoritative split recommendation，下一輪以新 task/Context
cold restart，沒有 checkpoint resume 或 inherited verdict。

Write task shape 在 routing 即 deterministic derive repo/docs/test side-effect class；不得以
implicit `none` 跑完整輪後才由 Closure 發現 mutation。

Compiler 另把 task/surface/risk、runtime/E2E claim、`side_effect_class`、objective/scope/
acceptance/hard stops、source baseline、direct interfaces、previous failure 與 verdict-relevant
`claim_inputs` 固化成 canonical
`task_contract`。Digest 同時綁 Context artifact、每個 role fragment 與 closure；closure 在
adjudication 時重驗 exact bytes、producer/freshness/baseline/budget authority，不能靠後來 prompt
改 scope、criterion、claim input 或 effect class。Unknown/contradictory effect class fail closed；沒有
closure-grade Adapter 的 `private_external_contact`/broker effect 形成 mandatory
unsupported node；`public_web_read` 則是要求 opened URL + citation/capture provenance
的 read-only evidence class，平台工具 availability 與 authority 分開判斷。純 deploy
不虛構 source builder；只有 source-plus-deploy 才走 builder/review/regression。

每次 saved-workflow call 都產 canonical `workflow_call_record_v1`，綁 task/context/node/role/
schema/result/retry、exact native identity/class/permission、DAG requires/topological wave 與
producer generation；dependency 完成前不可呼叫。完整 call manifest 再由 `workflow_wave_record_v1` 封存 admitted nodes、
calls/retries/nulls、result digests、coverage debt、planned input lower bounds 與 controller
overhead boundary。Closure 的 orchestrator structural ledger 必須 exact-cover capture index
全部 waves；ghost/omitted/extra/duplicate wave identity 都 fail closed。Self-digest 只證
canonical integrity，不是 provider/model authenticity。

主要成本指標為 `cost per durable accepted closure`，同時看 recall、false closure、
reopen/rework、lead time、accepted decision-changing findings、token/cache/tool/retry/fan-out。
Actual usage 只能是 `PLATFORM_OR_EXTERNAL_ATTESTED` telemetry-backed `measured/partial` 或
不帶假數字的 `unavailable`；orchestrator wave 只提供 calls/retries/fan-out/null/planned lower
bound 的 structural partial，且 refs exact-cover 所有 captured waves。Closure 重算 admissible
sums 與 quality reserve，planned estimate 不冒充 actual usage。
Closure 後另以 `closure_quality_followup_v1` + immutable closure digest 累積 reopen/rework/
false-closure/realized-value；沒有 caller-trusted platform/external attestation 就保持
scheduled/unavailable，不補 0。

### Authority and closure

Authority 改為 typed partial order：normative policy、implementation contract、active work
state、runtime observation、external policy、claim evidence。每個 claim 綁 subject、canonical
value、source digest、scope、strength、observed_at、class TTL/expiry 與 self-digest；repository
authority 的 value 必須是 exact pinned Context bytes 的 deterministic identity projection，
不得以同 digest 替換語義；解釋性 claim 改用 typed claim evidence。只在同
class/subject/scope 內比較。過期/偽造/同級歧義或跨類衝突標 DRIFT/CONFLICT 並阻止 PASS。
Runtime observation 不得合法化 policy denial。

STATUS/VERDICT/report 合併為 `closure_packet_v1`；work status、gate verdict、disposition
分離。所有 delegated preset 產同一 lossless `role_fragment_v1`，role-specific 結果留在
`payload_kind/payload`。Closure 綁定重算後的 canonical delegated-execution projection、
required/admitted node IDs、requires、waves 與同一 dag digest；任一 mandatory
fragment 缺失或 FAIL/UNVERIFIED/CONDITIONAL 均不得 PASS。PM closure 保留 dissent；memory
只在 closure 後 promote 新 durable lesson。

Route 與 adaptive admission 在 spawn 前綁 `role + native_agent + node_class + permission`；
PA/E4 writer 與 read-only verifier 是不同 native TOML identity。多 writer repo mutation 以
canonical writer order 證明；每個 node-owned scope non-empty/disjoint，shared-worktree
writer transitively serialized。Receipt 同時捕獲 owned mutation 與 task-wide generation，
相鄰 writer exact G0 -> G1 -> ... -> Gn，且 Gn/owned after current。單一 mixed-role
record 不得替代兩個 writer receipts。

Evidence assurance 分三層：`LOCAL_REPRODUCIBLE` repo/command capture、
`ORCHESTRATOR_BOUND` controller provenance、`PLATFORM_OR_EXTERNAL_ATTESTED` runtime/
external/outcome/actual-usage capture。Acceptance 不接受 generic/self-authored digest 或跨類
替代：unit test 不是 E2E、source 不是 runtime。`EXECUTED`/`REUSED` 都需 command capture；
repo mutation 必須由每個 admitted writer 各產一份 task/role/node/scope-bound
`repository_change_record_v1`，並以 ordered chain 重驗 exact before/after captures；單一
snapshot/source-change summary 不證 causality。

### Evidence reuse

Test evidence 使用 source/diff/untracked/command/test/toolchain/lock/OS/arch/env/config/
runtime/auth content signature + TTL。Critical/flaky/expired/failed 或任一 transitive input
變更不得重用。第二遍只在 critical、failed、known-flaky、release gate。

### Governed deep workflows

Full Audit controller 的 Registry backstop axes 加入 E2；每個 decision claim 由 source/impact
typed vote，必要時加第三份 reachability vote，closure 重算 confirmed/refuted/disputed、dissent
與 latent。結構不完整 finding 轉 stable content-derived debt。E1 只能產 hash-bound isolated
candidate，E2 review 同一 candidate；沒有 `APPLIED_VERIFIED` integration 就維持 debt，不能
啟動成功 regression 敘事。

Profit diagnosis 使用 `profit_diagnosis_control_v1` 綁 baseline、canonical current priors、
Registry mandatory evidence/probe axes、admitted/deferred partition、fragment digests、coverage
debt、PA map/unverified projection 與含 worst-case bounded retry 的 envelope。Controller validator
重算 `decision_ready/pass_eligible`；negative result 可接受，coverage hole 不可偽裝成 ready。

## Alternatives considered

1. **保留 18 套手工 persona，只修文字**：拒絕；刪除 Registry 後漂移仍會重現，
   deletion test 失敗。
2. **新增獨立 Context/Dispatch/Completion daemon**：拒絕；四個淺 Module 會再造配置
   drift。它們是同一深 Module 的 Interface。
3. **完全 advisory routing**：拒絕；effectful/source path 仍需 hard independent edge。
4. **完全固定 chain**：拒絕；docs/narrow work 的 ceremony 成本與延遲無 outcome 收益。
5. **OPS 可 gated apply**：拒絕；會破壞 maker/checker。Apply 留 Deploy Adapter。
6. **不設 IB role，只把 BB 參數化**：拒絕；IBKR 有獨立 phase gate、session/
   entitlement/TWS/live-denial judgment，已是第二個真實 reviewer capability surface；這不
   等於 contact/effect Adapter。
7. **token hard cap**：拒絕；會 Goodhart 成少讀證據與反覆重工。

## Consequences

Positive:

- role Interface 單一、平台 view 可 lint/重生。
- 保留完整智能與對抗深度，同時縮短無風險路徑。
- Runtime/venue effect boundary 有明確 seam；未實作能力保持 blocked，PM 不再以文字批准
  取代 maker/checker。
- Closure 與 test reuse 可機器驗真，report/memory annuity 大幅下降。

Costs/risks:

- Registry/renderer 成為關鍵 build surface，必須 CI/static test。
- Bash allowlist 是保守 policy；未命中命令需拆分或明示 Adapter intent。
- Direct `psql` 即使看似 SELECT 也停用，直到 local-socket/read-only-identity Adapter 排除
  ambient `psqlrc`/`PG*` routing；PG claim 否則需另有 attested artifact 或保持 UNVERIFIED。
- Deploy contract 需 immutable `deployment_intent_v1` 綁 source HEAD/clean tree/host/TTL/
  typed confirm/component digest、safe runtime identity 與不同 OPS pre/post evidence。目前
  repository 沒有 trusted local runtime identity probe，故 intent validation 可用但 apply
  必須在 component invocation 前 fail closed；只有補齊可重現 probe 後，才可能以
  canonical-integrity `effect_adapter_result_v1` + platform/external attestation + 唯一
  verified marker 形成 closure proof。底層 build/restart 腳本
  本身不是授權。
- `broker_probe_adapter_v1` 目前是 `declared_fail_closed_unsupported` seam。IBKR runtime paths
  是 gated operator reference，Bybit 沒有 development-agent contact entrypoint；兩者都不是
  本 Module 可執行的 broker Adapter。
- Adaptive Full Audit 需 shadow recall benchmark，未證明前不能宣稱不劣於固定模式。
- Full Audit 的 controller、axis admissions/fragments 與 coverage debt 全部 closure-bound；
  adaptive selection/recall authority、seam、verification outcomes 與 canonical debt projection
  也由 validator 重算；top-level `pass_eligible` 自報不能取代內容綁定。
- Full Audit/Profit 在首次 model call 前重驗 inline compiler Context、task prompt/hard stops、
  source freshness 與 Registry budget authority；caller 自簽 cap/mismatch 以 0 calls 拒絕。
- 歷史 role memories/reports 保留作 archive，短期磁碟體積不會立即消失；但不再 universal
  preload 或自動增長。

## Invariants

- Root Principles/Hard Boundaries 不因成本、盈利或 runtime observation 放寬。
- Dev sub-agent 不具 order/Decision Lease authority。
- Reviewer 不修被審 Implementation，也不直接 repo/runtime/broker effect。
- PM approval 不等於 independent verification；hard-gate dissent 不可靜默覆蓋。
- Evidence missing、budget exhausted、cache stale、coverage skipped 均不得 PASS。
- Missing uncertainty、native identity/class/permission mismatch 或未完成 DAG predecessor
  均在 spawn/call 前 fail closed。
- Fake/unbound usage、generic/evidence-class substitution、stale authority、無 producer call/wave
  binding 或 task-contract/claim-input drift 均不得 PASS。
- Bybit 是唯一 active live execution venue；IBKR live/tiny-live 仍 denied。

## Verification

- `tests/structure/test_development_agent_governance.py`
- `tests/structure/test_agent_governance_context_adversarial.py`
- `tests/structure/test_agent_governance_truth_receipts.py`
- `tests/structure/test_agent_governance_truth_receipts_adversarial.py`
- `tests/structure/test_agent_governance_full_audit_adversarial.py`
- `tests/structure/test_agent_governance_profit_control.py`
- `tests/structure/test_agent_governance_deploy_environment.py`
- `tests/structure/test_agent_governance_security_static.py`
- `agent_governance.py validate`
- `agent_governance.py render --check`
- Node syntax checks for saved workflows
- R4 generated-view/index audit
