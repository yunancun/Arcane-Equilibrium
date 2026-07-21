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

2026-07-20 在同一 Module 內加入 `Task Execution Control` Implementation，供 Dispatch
與 Closure 共用；它不是第五個 public Interface 或常駐 daemon。此 slice 集中 finite/
explicit-loop continuation、semantic no-delta fuse、queue selection 與 exclusive writer
lease。Filesystem 與 in-memory store 是同一 Seam 的兩個真實 Adapter。若刪除它，規則會
重新散落至 routing、Closure、saved workflow、Git guard 與 TODO selector，複雜度不會
消失；此 deletion test 證明其 Depth、Leverage 與 Locality。

### Role model

角色名稱改為四個 execution mode 上的 capability preset：Conductor、Investigator、
Builder、Verifier。Claude/Codex/profile 都由 Registry 生成；平台 runtime type 不代表
智能等級。

新增 `OPS(explorer)` 與 `IB(explorer)` preset：

- OPS 僅負責 operations preflight/rollback/postcheck/RCA，絕不 apply。
- IB 是 Broker Compatibility Interface 的 IBKR Adapter reviewer；BB 是 Bybit Adapter。

兩者都唯讀。任何 Deploy/broker contact 只有在 closure-admissible deterministic effect
Adapter 存在時才可能進入 effect；目前 deploy 是 intent-only、broker contact unsupported。

2026-07-18 增補一個 narrow exception：`p0b_alr_rollforward_adapter_v1` 是 ALR 專用、
兩階段、closure-admissible Effect Adapter，不改變 generic deploy 的 intent-only 狀態。
`stage`/`cutover` 必須各自重新編譯 route 與 materialized Context，綁 exact PA/E3/OPS、
dynamic source/origin、phase-runtime capture、typed intent 與 claim inputs。Stage 不停 ALR；
cutover 只改 `openclaw-alr-shadow.service`，並以 provisional -> observer-v2 exact PASS ->
independent postcheck 的單向 DAG 收口。它不授予 broker/order/live/mainnet authority。

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
acceptance/hard stops、source baseline、`dirty_scope`、可選 `verification_scope`、direct
interfaces、previous failure 與 verdict-relevant
`claim_inputs`，以及 exact `continuation_mode` 固化成 canonical
`task_contract`。Digest 同時綁 Context artifact、每個 role fragment 與 closure；closure 在
adjudication 時重驗 exact bytes、producer/freshness/baseline/budget authority，不能靠後來 prompt
改 scope、criterion、claim input 或 effect class。Unknown/contradictory effect class fail closed；沒有
closure-grade Adapter 的 `private_external_contact`/broker effect 形成 mandatory
unsupported node；`public_web_read` 則是要求 opened URL + citation/capture provenance
的 read-only evidence class，平台工具 availability 與 authority 分開判斷。純 deploy
不虛構 source builder；只有 source-plus-deploy 才走 builder/review/regression。

`verification_scope` 決定為 optional canonical、sorted/unique、literal safe repo-relative
path list，只可作 read-only command-capture generation 與 trusted replay boundary。Scope
只在 routed verifier `path_scope` 為空時採 `verification_scope`，再 fallback 到
`dirty_scope`；它不是
writer ownership、mutation authority 或 ACL，且不取代 writer `dirty_scope` 或 whole-repo
generation checks。因 `task_contract` 採 exact-field 驗證，本欄位是刻意的 current-generation
migration：Python routing/context validation、command capture、Closure capture binding/replay、
workflow capture callers，以及三個由 `CONTEXT_ADMISSION_V1` fragment 生成的 saved-workflow
consumer 必須同代更新；舊 generation 缺欄位不得被靜默接受。

`continuation_mode` omission 唯一正規化結果是 `finite`，且 finite 在 turn boundary 永不
排新 turn。只有 exact Operator request 的第一控制行精確等於 `/loop` 才可設
`operator_loop`；marker 綁 exact prompt 與 admitted task-contract digest，TODO row、filename、prior session、model
text 或 next_action 都不能推斷。原 task contract 與 preceding snapshot 由 Git common-dir
task-admission store 持久化並以 private fencing token 綁定；continuation caller 不能重填。
serialized prompt/digest 本身不是 Operator provenance；generic CLI 不得核發
`operator_loop` admission，只有 embedding host 的 out-of-band trusted Operator-request
verifier 對 exact normalized contract 回傳真實驗證後才可核發。
每次 boundary 重新讀 `dirty_scope` owned bytes，generic progress digest 只包含其實際內容；
lifecycle/blocker status、whole-repo HEAD、round/timestamp、caller receipt 與 unrelated-repo
noise 都不算 progress。External-only delta 必須由獨立 validated domain Adapter 或 reviewed
task-owned artifact 提供；
相同 digest 結案為 `BLOCKED_NO_DELTA`，不得 PASS、wakeup 或 executable next action。

Queue 的 ACTIVE/WAITING/CLOSED lane 與 role work status 分離；只有 exact ACTIVE 可被
selector 消費，IN_PROGRESS 已被 claim，不能重派。WAITING/DEFERRED 要有 named delta 並
重新 admission，CLOSED 永不 replay。每個
writable task 另需 Git common-dir atomic store 中一個 attached non-main linked-worktree
lease，帶 random fencing token/owner/task/branch/TTL；Git guard 僅唯讀驗證，不能 acquire、
steal 或自動修復。不同 writer 必須使用不同 linked worktree。

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

DONE/DONE_WITH_CONCERNS 沒有真實 follow-up 時允許 `next_action=null`；BLOCKED/
NEEDS_CONTEXT 仍需 owner/action。`BLOCKED_NO_DELTA` 只存在於 packet-level task closure，
必須 `next_action=null` 且永遠不能 PASS，避免 schema 迫使 controller 虛構工作。

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

#### 2026-07-21 amendment: AIML S0.3 trusted-host finalization

Program adoption 是上述 Closure Interface 的高權限特化，不新增第五個 public Interface。
唯一 production entry point 是：

```text
python3 helper_scripts/maintenance_scripts/agent_governance.py aiml-trusted-finalize \
  --packet <closure.json> \
  --execution-bundle <trusted_execution_bundle_v1.json> \
  --execution-signature <trusted_execution_bundle_v1.json.sig> \
  --github-token-fd <inherited-fd>
```

Secure path inputs 必須 owner-controlled、regular、non-symlink、non-group/world-writable 且
bounded；GitHub credential 只能由 inherited owner-only FD 消費，不進 argv、artifact 或輸出。
Production caller 不能替換 time、repo、transport、Git/GitHub verifier、API origin、CA roots 或
execution trust root。Reviewed root 固定為 `aiml-s03-operator-v1`、fingerprint
`SHA256:uGJ9veN7PoE6BBgfsSP2aiMndrwgbt7o/7/YfdzNzCQ`、SSHSIG namespace
`arcane-equilibrium-aiml-s03`；matching private key 不得存在 Linux finalizer host，只在獨立
Operator host 對 canonical bundle 做 detached signing。

`POST_MERGE_FINALIZATION` 是唯讀 admission 且不得持 writer lease。Complete packet 必須綁
final merged source、S0.1/S0.2/program receipt、CC / E2 / E3 / E4 / MIT / QA / R4 七個 mandatory
review fragment 與 authenticated execution bundle。Bundle exact-bind task/Context/DAG/artifact，
freshness 與 consumption 必須閉合。Source verifier 要求 `merge-base --is-ancestor` 與 exact
commit/blob manifest，並拒絕 shallow/replace/graft/alternate/promisor/path escape；GitHub verifier
以 fixed-origin/system-CA/no-proxy/no-redirect live 驗 repository/default ref/reviewed merge lineage/
effective ruleset/required checks。`github_capture_projection_v2` 進一步 exact-bind paginated
associated PR、merged PR detail、two-parent merge commit 與 paginated
`check-runs?filter=latest`；PR head/merge/base/repository 必須等於 receipt lineage，每個 ruleset
required `(context,integration_id)` 必須唯一 completed/success 且在 `merged_at` 前完成。
Merge commit 的第二個 parent 必須是 exact reviewed head；第一個 parent 只要求為合法且互異的
base parent，不能把 PR API 的 `base.sha` 誤當成歷史 pre-merge parent。Check Run 的
`pull_requests` 可為空（exact `head_sha` 是權威綁定）；若非空則必須包含該 exact PR。
Self-authored packet、merge 後補跑的 checks 或 cached GitHub JSON 不能替代 external verification。
這組 REST evidence 分別證明 exact merged PR、pre-merge successful checks 與 finalization 當下
live ruleset；它不宣稱 ruleset 在歷史 merge 時刻從未停用，後者需 platform audit/event
attestation。

只有 trusted finalizer `PASS` 且輸出 exact receipt digest 才可宣稱 `PROGRAM_ADOPTED`。任一
signature、source、GitHub、seven-reviewer、freshness 或 exact-consumption mismatch 都 fail closed。
本 amendment 不授予 ML5/ML6、deploy、broker/order/live、Decision Lease 或交易 effect；
authority-limits const-false、source-adoption-only 與 four-zero-effects 不變。

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
8. **只改 persona/prompt**：拒絕；沒有 executable continuation、queue 或 writer
   enforcement，下一個 controller 仍可重開同一狀態。
9. **把所有 drift 都當 progress**：拒絕；artifact timestamps 與 unrelated whole-repo
   change 會永久製造假 delta。

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
  typed confirm/component digest、safe runtime identity 與不同 OPS pre/post evidence。
  Repository 現已有 local-only、non-secret、fail-closed `runtime_environment_probe_v1`
  source seam；Deploy Adapter 獨立重跑並 exact reconcile supplied
  `runtime_environment_attestation_v1`。這不是 platform runtime attestation，也不提供 remote
  SSH capture transport。即使 probe reconciliation 通過，apply 仍在 exact rollback binding
  與 stable observation-window controls 分別實作、驗證前，於 component invocation 前
  unconditionally fail closed。底層 build/restart 腳本本身不是授權。
- P0-B ALR 的 purpose-built contract 使用獨立 intent/result schemas 與 exact phase claim
  sets。Runtime-bindings 是 pre-admission typed artifact；authorization 單向綁 artifact
  digest/path/argv，artifact 不 backlink authorization 或 task digest，避免不可構造 hash
  cycle。Final cutover receipt 必須先綁 provisional digest、observer-v2 exact PASS、兩個
  distinct natural cycles 與 durable decision；其後 Closure PASS 再要求 independent OPS
  postcheck 綁定該 final receipt。任一環缺失一律 FAIL。
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
- `tests/structure/test_agent_governance_task_control.py`
- `tests/structure/test_git_loop_guard.py`
- `agent_governance.py validate`
- `agent_governance.py render --check`
- Node syntax checks for saved workflows
- R4 generated-view/index audit
