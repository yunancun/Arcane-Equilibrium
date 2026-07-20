# Development-Agent Governance Module

Status: active Interface, 2026-07-20
ADR: `docs/adr/0050-development-agent-governance.md`

本文件是開發 sub-agent 工作流的人類入口。機器正本是
`.codex/agent_registry_v1.json`，可執行 Implementation 是
`helper_scripts/maintenance_scripts/agent_governance.py`。Claude、Codex 與
`docs/CCAgentWorkSpace/*/profile.md` 都只是由 Registry 生成的 Adapter。

Public CLI 保持單一；command permission 與 deploy intent 是同 Module 的內部
Implementation/Effect Adapter 檔，讓 reviewer 可按 Interface 局部讀取，避免巨型檔
token annuity。它們不形成第二套 Registry 或 authority。

## 1. 目標函數

治理目標不是「最少 token」，而是：

```text
Net workflow value
= expected risk-adjusted profit
+ avoided loss
+ operator/engineering time saved
- token/API cost
- expected rework
- coordination latency
- false-closure loss
```

主要衡量單位是 `cost per durable accepted closure`。Token、速度與 fan-out
只有在 hard boundary、recall、evidence truthfulness、reopen rate 不惡化時才是
收益。禁止把 finding 數、DONE 數、cache hit rate、spawn 數或 prompt 長度當成
單獨 KPI。

## 2. 一個深 Module，四個 Interface

### Registry Interface

```text
load_registry() + render_views(registry) -> generated platform/profile Adapters
```

Registry 只持穩定結構：role ID、execution mode、activation/skip、能力 pack、
permission、context pack、output schema、budget envelope、charter rules。專業深度留在
role skills；Root Principles、ADR、broker 官方規則不複製進 Registry。

四個 execution mode：

- `Conductor`：任務事實、最小充分 DAG、整合與 closure。
- `Investigator`：提出方案、發現 gap、建立可驗證假設。
- `Builder`：在明確 scope 內產出 source/test/docs patch。
- `Verifier`：獨立判定，不修被審的 Implementation。

既有 PM/PA/E1/QC 等名稱是 capability preset。所有 preset 都使用可用的完整模型
智能；`default/explorer/worker` 只是 runtime substrate，不是智能等級。

新增的兩個 preset：

- `OPS(explorer)`：唯讀 preflight、rollback、postcheck、source-build pin、RCA。
- `IB(explorer)`：IBKR Broker Compatibility Adapter reviewer，守 ADR-0048/TWS/
  session/entitlement/paper-shadow typed denial。

`OPS` 不 apply；`IB` 不 contact。Effect 只能走下方 deterministic Adapter。

### Context Interface

```text
compile_context(role, task_facts_with_optional_evidence_state) -> context_plan_v1
```

Context capsule 分三層：

1. immutable exact core：user objective/scope、acceptance、hard stops、baseline、
   direct Interface、上一輪 failure/concern。
2. task evidence：由 role/surface 選 context pack，附 path、selector、digest。
3. expandable history：role memory、舊 report、archive 僅在直接相關時讀。

Concrete repo source 永遠先安全 resolve、拒絕 symlink escape、讀 bytes 並重算 digest/
token estimate；`evidence_state` 對它只能是 expected-digest assertion，不能覆寫內容或把
`planned_tokens` 壓成 0。Virtual source（current diff/direct callers/official source 等）
必須指向安全 repo-relative `context_evidence_artifact_v1`。Artifact bytes 內綁 exact
`logical_source`、typed `capture_kind`、timezone-aware `observed_at`、content digest；同一 raw
檔案或另一 logical source 的 artifact 不能交叉冒充。Compiler 重算 artifact/content digest、
bytes/tokens。Digest-only、missing concrete source、未知 evidence key 或 mismatch 都保留為
`unresolved_sources`，Context plan 不得 `pass_allowed`。

Context 不是一段可任意重寫的 prompt。Compiler 先把 exact `task_prompt`、task
shape/surfaces/risk、必填 `low|medium|high|unknown` uncertainty、runtime/E2E claim、
`side_effect_class`、objective/scope/acceptance/hard stops、三欄 source baseline、
`dirty_scope`、可選 `verification_scope`、direct interfaces、previous failure 與
verdict-relevant `claim_inputs` 正規化成
`task_contract`。`claim_inputs` 是 name→canonical digest map；任何會影響結論的 prior/
evidence 都必須在 admission 時綁定，不能藏在 free-form prompt 內替換。其 canonical
SHA-256 以 `task_contract_digest` 同時綁在 plan、artifact、每個 `role_fragment_v1` 與最終
closure。Closure 在 `adjudicated_at` 重新驗 artifact exact fields、canonical bytes、source
bytes/digest、producer、capture-kind TTL、baseline 與 compiler-derived budget authority；
role、scope、criterion 或 claim input 不能在 dispatch 後偷換。

`verification_scope` 是 optional canonical、sorted/unique、literal safe repo-relative
path list，只用於 read-only command-capture generation 與 trusted replay。它只在 routed
verifier `path_scope` 為空時採用，並先於 `dirty_scope` fallback。它不是
writer ownership、mutation authority 或 ACL，也不能取代 writer `dirty_scope` 或 whole-repo
generation checks。

Budget 分開管理 single-call planned lower bound、exact prompt bytes、workflow planned
lower bound、unique nodes、call attempts 與 retry：

- `target` 是正常高效路徑，不是內容 cap。
- `quality reserve` 專供 hard-risk、矛盾、低置信、跨語言/runtime、second thought。
- `target + quality_reserve` 以上、但仍低於 per-call planned/byte caps 的 reviewed band
  可在有明確 rationale 時保留單一高品質 call，避免拆分後重複載入 core/source；到 cap
  才拆任務或升 context，絕不截斷 mandatory content。
- Full Audit 有更大的 envelope。
- budget 用完但 evidence 未閉合，只能 `NEEDS_CONTEXT/UNVERIFIED/BLOCKED`。

`agent-wave` 不接受裸 legacy task array 或 raw `contextPath`。每個 admitted node 只帶一份
`context_artifact_v1`：Python compiler 保留完整 canonical envelope 供 closure 重驗，另產
authenticated shared semantic capsule + role delta 作為 prompt/cache prefix；receipt/ambient
dirty metadata 不污染 repository-derived semantic key，但 verdict evidence 的 TTL/trust 會。
Workflow 在 JS 端獨立重算 semantic digests。Wave 與 infrastructure retry 重用 admission bytes，
不 reopen path，避免 substitution/TOCTOU。Role/digest
必須相符，`omitted_mandatory=[]`、`unresolved_sources=[]`、所有 source 都有 byte-backed
digest、`budget.pass_allowed=true` 才執行。Inline artifact 仍可能被每個 agent ingest；cache
收益只按平台實測記錄，不能宣稱「只付一次」。

每一次 model call（含 infrastructure retry）都由 controller 產
`workflow_call_record_v1`，綁 workflow contract、logical call/node/role/payload、requested
model/effort/isolation、prompt、context/task/dirty-scope/focus/response-schema digest、exact
native agent/node class/permission、DAG predecessors/topological wave、producer generation、
attempt/retry parent、timestamps、null state 與 exact parsed-result digest。Dependencies 只有在
所有 predecessor 完成後才可呼叫。Role fragment 的身份/
task fields 由 controller 注入，model 只返回 judgment payload；fragment 必須指回產生它的
call record。所有 call 依序進唯一 `workflow_call_manifest_v1`，再由
`workflow_wave_record_v1` 封存 admitted tasks、每次 call/retry/null、final-null、result
fragment digests、coverage debt、planned input lower bounds、budget authority 與 controller
overhead accounting boundary。Canonical self-digest 只證明內容完整，並非 provider/model
簽章或 producer authenticity。Closure 若以 orchestrator receipt 記 structural consumption，
`wave_record_refs` 必須恰好覆蓋 capture index 的全部 wave；多放、少放或重複 digest/ID 都
fail closed，不能把成功但昂貴的 ghost wave 從成本與 dispatch lineage 隱去。

### Dispatch Interface

```text
route_task(task_facts) -> hybrid_execution_dag_v1 + digest + pre-spawn role/native/class/permission bindings
```

這是 hybrid DAG，不是固定角色儀式。

Task-facts seam 是 typed、fail-closed：exact `task_prompt`、`task_shape`、`risk`、
必填 `uncertainty`、`surfaces`，以及
`runtime_claim` / `end_to_end_claim` boolean 使用 Registry compiler 已知字彙；objective、
scope、acceptance、hard stops、baseline、`dirty_scope`、可選 `verification_scope`、
direct interfaces、previous failure 與可選
`evidence_state` 供 Context Interface 使用；verdict-relevant prior/evidence 另由
`claim_inputs` 以 canonical digest 固定。`continuation_mode` 缺省只正規化為
`finite`；只有 exact Operator request 第一控制行精確等於 `/loop` 才可用
`operator_loop`，並將 marker 綁入原始 admitted task contract digest。
`side_effect_class` 必須明示為 `none`、repo/test/
docs write、deploy、`public_web_read` 或 private external/broker effect 類別，並與 task shape/surface 相容；source/docs/
test write shape 分別 deterministic derive `repo_write`/`docs_write`/`local_test`，不能默認
`none` 再等 Closure 發現 mutation。未知 field、
surface、effect 類別或互相矛盾的組合通常代表 typo 或
未建模風險，必須先修正／擴充 compiler，不能靜默跳過角色。`runtime` surface 只表示
需要 runtime context；只有 `runtime_claim=true`、deploy，或 service/cron/PG/
runtime-effect/incident-RCA 等 operational surface 才觸發 OPS，避免 source-only
runtime code change 機械式增加兩次 runtime review。

`public_web_read` 僅是 read-only evidence acquisition：必須實際開啟 public URL，保留
citation/capture provenance；平台是否提供 WebSearch/WebFetch 是另一個 availability fact，
不能當作 authority。Web 工具只投影給 E3/QC/MIT/AI-E/BB/IB，且只有 task contract
明示 `public_web_read` 並擁有 acquisition node 時可用；claim 必須落成 host-verified
`external_evidence_capture_v1`。只有 URL、自報或 generic repo digest 均保持 debt/INFERENCE。
`private_external_contact` 包含 authenticated/private communication、
transaction 或 broker effect，現階段一律 fail-closed unsupported。純 `task_shape=deploy`
只走 OPS/effect；只有 source-plus-deploy 才保留 builder -> E2 -> E4。

Hard edges：

- source Implementation → independent `E2` → relevant `E4` tests。
- authority/live/risk/auth → `CC` + `E3`；Implementation 仍需 E2/E4。
- runtime claim 或 operational change/deploy → `OPS preflight`；deploy 再經
  PM/operator exact intent → Deploy Adapter contract → `OPS postcheck`；trusted local probe
  source 已存在，但 apply 仍因 rollback binding 與 stable observation-window controls 未綁定，
  在 component invocation 前 fail closed。
- Bybit surface → `BB`；IBKR/TWS/stock_etf_cash → `IB`；不可互代。
- quant/ML semantic change → `QC`/`MIT`。
- end-to-end claim → `QA`。
- docs-only write → `TW` → `R4`；test-only write → `E4` → independent `E2`。
- functional/performance/GUI-visible claim → `FA`/`E5`/`A3`，不再讓這些能力永遠 dormant。

PA、FA、E5、A3、R4、AI-E 等其他 node 由 risk、uncertainty、surface、expected
decision gain 觸發。PM 可增加 node，但必須在 closure dispatch 的
`admitted_role_nodes` 綁定 unique node ID、Registry role、exact native agent、
`work|verification` class、permission 與 reason；同一 tuple 在 spawn 前重驗並進 DAG
digest。它隨即是 mandatory coverage，不能只在成功時留下 fragment。跳過時記
reason、residual risk、owner。未知
risk 進 full-audit envelope，不可自動當 low-risk。

再加入一個 node 的條件：在保留 quality reserve 後，預期 decision gain（降低風險、
解鎖盈利或避免重工）大於 token/time/opportunity cost。停止條件是 mandatory coverage
已完成，且下一 node 的 novelty 或 verdict-reversal value 低於成本。

### Evidence assurance and claim-class matrix

Trust tier 與 authority/evidence class 是兩個維度，不能互相替代：

| Trust tier | 可證明 | 不可推導 |
|---|---|---|
| `LOCAL_REPRODUCIBLE` | governance producer 直接捕獲、可重新比對的 repo bytes、command argv/output/exit | model/provider 身份、runtime/external 真實性 |
| `ORCHESTRATOR_BOUND` | controller 實際要求的 task/context/node/role/schema，以及收到的 exact result、retry/null/wave coverage 結構 lineage | execution authenticity、provider signature、actual token/cache/tool/time、external fact；packet-local receipt 不可自證執行 |
| `PLATFORM_OR_EXTERNAL_ATTESTED` | 由 platform/provider/external verifier attested 的 runtime、external-policy/outcome 或 actual-usage fact | policy permission 或其他 authority class |

Self-digest 是 canonical integrity check，永遠不等同 authenticity。Local capture +
orchestrator-bound independent verifier 可完成 source/test claim；runtime、E2E business
outcome、external policy 與 actual usage 必須有第三級 capture。

Claim-class substitution 一律 fail closed：

| Claim | Closure-admissible direct evidence | 明確不接受 |
|---|---|---|
| source/content | scoped `repository_capture_v1` + call-bound verifier | generic digest、model summary |
| repository mutation | 每個 admitted writer 一份 task/role/node/scope-bound change record，形成 final-current ordered chain | 單一 snapshot、斷鏈、diff/source-change summary |
| test/check | matching Context-bound `command_capture_v2`；`REUSED` 再加 reuse eligibility lineage | 自報 EXECUTED/REUSED、空 check |
| runtime/PG/process | `PLATFORM_OR_EXTERNAL_ATTESTED` runtime capture | source、unit test、raw local/SSH summary |
| E2E/business outcome | `PLATFORM_OR_EXTERNAL_ATTESTED` outcome capture + QA | unit/integration test 冒充 business outcome |
| actual consumption | attested telemetry record bound to subject call IDs | budget、estimate、wave lower bound、model self-report |

`command_capture_v2` 是單次 Adapter invocation：從 immutable Context 重算 route，導出
exact native identity、node/task digest；routed verifier `path_scope` 為空時先採 optional
`verification_scope`，再 fallback 到 `dirty_scope`，只接受 `--` 後 argv 並以 `shell=false`
執行。stdout/stderr 是 bounded redacted readable preview + exact bytes/digest；repo generation
以 streaming staged/unstaged diff 與不追蹤 symlink 的 untracked manifest 綁 task/whole repo。
Closure admission 會在相同 task/baseline/scope 下做 trusted local replay，claimed
PASS 無法重現或 replay 造成 task/whole-repo mutation 即拒絕；無 host verifier 時因此是
capture + replay，不能宣稱 one total execution。`effect_enforcement=repository_policy_only`
只表示 argv allowlist/mutation detection，不是 OS network/no-contact attestation。E4 只經保守的
`local_test_adapter` 執行已授權 test/check argv。Replay contract 為 deterministic read 的
`EXACT_OUTPUT`、只正規化測試 duration 的 `CANONICAL_TEST_OUTPUT_V1`，或無 semantic output
channel 的 `RESULT_ONLY`；重算 self-digest 不能替換 command output 語義。`EXECUTED` 與 `REUSED` check 都必須指向
有效 command capture；後者仍需保留原 execution/signature/TTL assessment，不能只改
status label。

### Task Execution Control Implementation

Task Execution Control 是 Dispatch 與 Closure 共用的內部 Implementation，不是第五套
public controller/daemon。它有 Git common-dir 原子 task-admission store、filesystem
writer-lease store，以及 writer lease 的測試用 in-memory store；`git_loop_guard.py` 是唯讀
consumer，只驗證既有 writer lease。

普通 task 的唯一預設是 `finite`，不具排下一 turn 或 `ScheduleWakeup` 的 authority。
明示 `operator_loop` 先取得 persisted task admission；其 private fencing token 綁原始
task contract 與 preceding snapshot，caller 不能替換。每個 turn boundary 都重新讀
task-owned source scope；generic progress 只比較其實際 bytes。Context/external/work caller
payload、blocker、lifecycle status、whole-repo HEAD、round/timestamp 和 unrelated drift
不算 progress。相同 digest 直接輸出
`BLOCKED_NO_DELTA + schedule_wakeup=false + next_action=null`。只有 exact ACTIVE queue
item 可被派工，IN_PROGRESS 已被 claim；WAITING/DEFERRED/CLOSED 必須先由新 delta 或
Operator reopen 形成新的 ACTIVE
admission。

Canonical snapshot producer 由 persisted normalized task contract 的 `dirty_scope` 讀取
實際 repository bytes；continuation 從 store 取回原始 control/digest/preceding snapshot。
任意 caller-supplied contract、previous snapshot、digest、receipt 或新編 loop control 都不是
有效 delta/authority。External-only delta 必須由獨立 validated Adapter 或 reviewed
task-owned artifact 落入 admitted scope。

每個 writable task 只持有一個 attached non-main linked-worktree lease，帶 task/owner、
branch、TTL 與 random fencing token。Acquire 要求 clean worktree；renew/release 在同一
atomic lock 內重驗 owner/token/expiry；collision fail closed。刪除此 slice 會讓 finite/
loop、no-delta、queue selection、terminal next action 與 writer exclusivity 再散落到
routing/Closure/workflows/Git/docs，通過 deletion test，具有足夠 Depth、Leverage 與
Locality；因此保留一個 Module 內的 Interface/Seam/Adapter，而非增加 shallow daemon。

低風險、低不確定性、無 effect/runtime/E2E/hard surface 的 `task_shape=query` 只走
PM triage/closure，且永遠 finite。任何 authority/security/broker/private-effect fact 都
拒絕此捷徑並回到完整 route。

### Closure Interface

```text
validate_closure(packet, execution_attestation_verifier=trusted_host_capability)
+ project_closure(packet) -> validated closure view
```

`execution_attestation_verifier` 是 host 提供、不可序列化進 packet 的 capability，
以 exact digest 驗 Context、delegated wave、runtime/outcome 與 effect。Standalone CLI
沒有此 capability，只能做離線 shape/integrity/fail-closed 檢查，不能認證 `PASS`；
packet-local self-digest/receipt 即使全自洽也只屬 structural evidence。

不再同時維護 STATUS、VERDICT、per-role report、Operator copy 四套 authority。
`closure_packet_v1` 同時包含人可讀摘要與機器 manifest：

- `work_status`: DONE / DONE_WITH_CONCERNS / NEEDS_CONTEXT / BLOCKED /
  BLOCKED_NO_DELTA
- `gate_verdict`: PASS / FAIL / CONDITIONAL / NOT_APPLICABLE / UNVERIFIED
- `disposition`: CHANGED / NO_CHANGE_NEEDED / DEFERRED

`DONE + FAIL` 合法：review 已完成，被審物失敗。任何 blocked/no-delta + PASS 非法。
DONE/DONE_WITH_CONCERNS 沒有真實後續時可用 `next_action=null`；BLOCKED/NEEDS_CONTEXT
仍須 owner/action；BLOCKED_NO_DELTA 必須是 null，不能虛構「再跑一次」。

Packet 還需 adjudicated_at、baseline/head/diff hash、完整 PM admission context artifact、
route digest/deterministic required nodes/PM-added `admitted_role_nodes`（含 exact native
identity/class/permission）、typed authority refs、
acceptance→evidence mapping、lossless `role_fragment_v1`、executed/reused/skipped checks、
repository/command/call-manifest/wave/attested evidence、runtime freshness、side effects、
unverified scope、skipped role、consumption，以及 terminal-null 或真實 next owner/action。

Route-bound PASS 不能用 `NOT_APPLICABLE` 把 verifier 消失：Implementation、test/docs
write 等 work-only node 可用 `NOT_APPLICABLE` 表示它不自我 gate，但 E2/E4/CC/E3/
OPS/QA/venue/specialist verification node 必須明確 PASS。任何 OPS route 都需 fresh
runtime evidence，且每個 OPS fragment 直接引用它；`end_to_end_claim=true` 需由 passed
acceptance 與 QA 同時引用 test/data/runtime/external outcome evidence。Mandatory Effect
Adapter 另需 canonical-integrity `effect_adapter_result_v1` + platform/external attestation，綁 exact intent
authority、baseline HEAD、host/environment、component marker/binary digest 與 15 分鐘
evidence window。Receipt、OPS preflight、OPS postcheck 必須是三份不同 evidence；passed
acceptance 同時引用 receipt 與獨立 postcheck，且 closure 如實標 `CHANGED` +
`runtime_contact=true`。Preflight typed payload 綁 intent/source/component；postcheck 再綁
receipt digest 與 running binary SHA。Generic/其他部署的 runtime observation、改名 evidence
或 role fragment 都不能替代這條鏈。

每個 routed E4 node 另需直接引用 `scope=test` evidence，且同一 evidence 必須被
`EXECUTED` check 或有效的 hash-pinned `test_evidence_reuse_v2` receipt 綁定，且兩者
都必須引用 matching `command_capture_v2`；只有
source digest、空 checks 或自報 `REUSED` 都不能完成 regression hard edge。

Generic source/runtime/data digest 不再能自證 PASS。每個 fragment 先以 producer call/wave
record 驗 task/context/node/role/result binding，再依上表驗 evidence class/trust tier。
Acceptance PASS 至少引用 closure 重驗的 direct capture，並由同一 refs 的 independent
call-bound FACT verifier 支持。Repo mutation 必須由每個 admitted writer 恰好一個
task/role/node/scope-bound `repository_change_record_v1` 依 canonical writer order 組成；
node-owned scopes 必須 non-empty/disjoint、writer transitively serialized；每份 receipt
同時綁 owned mutation 與 task-wide generation，形成 exact G0 -> G1 -> ... -> Gn，且
Gn/owned after current。單一 mixed record、snapshot 或 legacy summary 不證明 mutation。

Closure 只接受 deterministic required node 或明確 admitted node 的 fragment。任何
admitted verification FAIL/CONDITIONAL/UNVERIFIED/缺席都阻止 global PASS；因此
second thought、adaptive Full Audit 或臨時 specialist 的 dissent 不會因它不在靜態
hard-gate role set 而消失。

每個 reviewer 回 immutable fragment；Report Sink 可原子投影一份 task closure，但不得
覆寫 dissent。只有 closure 後的新 durable lesson 才升 memory。日常查證與重複結論不
自動產 report/memory。

## 3. Typed authority matrix

Authority 是 partial order，不是總排序。每個 claim 都明示 subject、canonical JSON value、
exact `source_ref`/source digest、scope、strength、observed_at、expiry 與 self-digest；repo
authority 必須指回 exact pinned Context bytes，且 `value` 必須是該 bytes 的 deterministic
identity projection（UTF-8/JSON 保留 exact content；base64 保留 encoding+content），不能把
同一 digest 配上另一個語義。需要判斷或外加語義的 claim 改走 task `claim_inputs`/validated
capture，不冒充 repository authority。Runtime/external authority 必須指回 attested capture。
短效 class 必須在各自 TTL 內，過期、future-dated、scope 不同或 hash 不符都 fail closed：

| Class | 能回答的問題 |
|---|---|
| `normative_policy` | 允許／禁止什麼 |
| `implementation_contract` | source/schema/test 實作了什麼 |
| `active_work_state` | 現在 owner/blocker/next action 是什麼 |
| `runtime_observation` | 某 host/environment 在某時間觀測到什麼 |
| `external_policy` | broker/供應商官方規則在何時為何 |
| `claim_evidence` | 某個 hash-pinned claim 有何 proof |

只在同 class、同 subject、同 scope 內依 evidence strength 再依 freshness 選擇；同級同時
不同值或跨 class 不一致輸出 `DRIFT/CONFLICT`，保留雙方。Runtime observation 永遠不能
合法化 normative denial；closure PASS 必須沒有 stale/invalid/unresolved authority conflict。

## 4. Permission 與 effect seam

Read-only preset：CC、FA、E2、E3、E5、A3、R4、BB、IB、QC、MIT、AI-E、QA、
OPS。它們不 edit/stage/commit，不直接寫 memory/report；verification argv 只經一個
Context-bound `capture-command` call 執行，不先 authorize 再另跑。允許 repo read、local tests、governance read-only compiler、
governed local read-only probe；拒 git/PG/service/filesystem mutation、private broker effect、
未授權 external contact、Linux cargo。

Direct `psql` 目前整體禁用，即使 query 看似 SELECT；在 local-socket/read-only-identity
Adapter 能排除 ambient `psqlrc` 與 `PG*` routing 前，PG claim 只能消費另外授權的
`PLATFORM_OR_EXTERNAL_ATTESTED` artifact，否則保持 UNVERIFIED。

這層 enforcement 是 repository policy + command preflight，not an OS/platform sandbox。
Shell/tool 在技術上可能仍比 role profile 寬；generated binding、preflight 與平台可用
sandbox 是不同層，文件不得把 policy allowlist 宣稱成強隔離。

特殊 write scope：

- E1/E1a：task-owned source + focused tests。
- mixed GUI/backend：E1a 只擁有 frontend/GUI `path_scope`，E1 擁有 backend
  scope；兩者 non-empty/disjoint，固定 E1 backend -> E1a frontend 序列化，
  independent E2 必須等待兩個 builder。
- E4：tests/fixtures/test-only helpers，禁止 business Implementation。
- PA：task-owned spec/ADR only。
- TW：task-owned docs/comment/index projection only。
- PM：governance/closure/approved intent；不寫 business Implementation。

Effect Adapters：

- `deploy_adapter_v1` contract：只接受 PM/operator 批准的 exact-SHA
  `deployment_intent_v1`，並定義 typed runtime-environment attestation 與
  `effect_adapter_result_v1` receipt。Repository 現已有 local-only、non-secret、fail-closed
  `runtime_environment_probe_v1` source seam；Deploy Adapter 會獨立重跑，並與任何 supplied
  `runtime_environment_attestation_v1` exact reconcile。這不是 platform runtime attestation，
  也不提供 remote SSH capture transport。Intent-only 仍回
  `INTENT_VALIDATED_APPLY_DISABLED`；任何通過 probe reconciliation 的 `--apply` 仍回
  `DEPLOY_RECOVERY_CONTROLS_UNBOUND`，因 exact rollback binding 與 stable observation-window
  controls 尚未分別實作和驗證，故在 `build_then_restart_atomic.sh` component invocation 前
  unconditionally fail closed。
- `p0b_alr_rollforward_adapter_v1` 是獨立的 purpose-built ALR effect seam，不能以
  `deploy_adapter_v1` receipt、handwritten approval 或 `context_plan_v1` 代替。`stage` 與
  `cutover` 各自需要新 route、PM materialized `context_artifact_v1`、PA/E3/OPS role fragment
  與 command capture、fresh OPS attestation、exact claim inventory、dynamic local HEAD = fresh
  `origin/main`，以及單向 hash-bound `phase_runtime_bindings_v1`。Runtime-bindings artifact
  是 pre-admission capture，不 backlink authorization/task digest，避免
  `authorization_digest ↔ artifact_digest` hash cycle；authorization 再綁其 exact path、bytes
  與 argv。Stage 保持 `openclaw-alr-shadow.service` identity 不變，只封存 target-head lineage、
  board 與 offline private observer dependencies。Cutover 只可作用該 unit，先輸出
  `PHASE2_PROVISIONAL_CUTOVER_READY`；observer v2 對 exact input/兩個自然 cycles/durable
  decision 回 `OBSERVER_V2_EXACT_POSTCHECK_PASS` 後，Adapter 才可形成
  `PHASE2_APPLIED_POSTCHECK_PASS`；其後 Closure PASS 仍須 independent OPS postcheck 單向綁定
  該 final effect receipt。此 Adapter 不授權 broker、
  order、Decision Lease、live/mainnet 或其他 user-manager/service effect。
- `broker_probe_adapter_v1` 目前只是 Registry 中的
  `declared_fail_closed_unsupported` seam，**不是可執行 Adapter**。IBKR paths 是 gated
  operator/runtime reference surface；Bybit 是 runtime-owned 且沒有 development-agent
  contact entrypoint。`broker_probe`、private broker effect 或
  `private_external_contact` route 會
  產 mandatory unsupported-effect node，不能 closure PASS。
- `report_sink_v1`：`project-closure` 先驗證再投影單一 deterministic Markdown；
  原始 packet、fragment、dissent 與 evidence index 全部保留。

## 5. Test evidence reuse

Evidence signature 至少包括：source HEAD、dirty diff、relevant untracked hash、command、
selected tests、toolchain、dependency lock、OS/arch、env/secret mode、config、runtime head、
authorization hash。任一直接或 transitive input 改變即 cache miss。

Capsule 必標 `EXECUTED` 或 `REUSED`，兩者均引用 task/node/role/command-bound
`command_capture_v2`；`REUSED` 另附原 execution evidence、assessment 與 created/expiry
lineage（最長 24h）。失敗、過期、flaky、signature mismatch、未簽名額外 input 不得重用；critical
evidence 需不同 role/evidence digest/timestamp 的 independent recheck，不能用 boolean
自證。Closure 消費 `REUSED` 時還需 assessor 產出的 hash-pinned receipt，綁 check
signature、referenced execution evidence digest、assessment/adjudication/expiry lineage；
packet 形狀本身不是 cache proof。第二遍測試只在 critical、已失敗、已知 flaky、
release gate；critical flaky 是 FAIL。

這個 E4 scheduling 規則與 Closure assurance replay 分開計價：目前缺 host
CommandCaptureVerifier，Closure 對 capture 做 trusted re-execution，故非 critical 也會有
一次驗證 replay。這是刻意的高保證 constraint，不得在 consumption accounting 中稱為
single execution；未來只能由 host-attested verifier 取代，不能由 packet self-report 跳過。

## 6. Consumption truth contract

每個 fragment 與 closure 的 usage 只能是 `measured`、`partial` 或 `unavailable`：

- actual `measured/partial` 只接受 `PLATFORM_OR_EXTERNAL_ATTESTED` platform telemetry/
  provider usage，綁 exact telemetry ref/digest/subject call IDs；`partial` 精確列出未提供 metrics。
- closure 可用 orchestrator wave receipt 報 partial structural accounting：calls、retries、
  fan-out、nulls 與 planned input lower bound；其 refs 必須 exact-cover capture index 的所有
  waves，不得漏掉 ghost/retry/specialist wave，也不得宣稱 actual token/cache/tool/time。
- `unavailable` 必須寫原因，且不能同時夾帶 token/tool/time 數字或假 telemetry。
- Closure 不信任手填總數：input/output/cache/tool/retry/rework 依 attested fragment 重算；wall time
  不得小於任何已知 fragment；fan-out 等於 bound fragment 數；partial aggregate 不得隱藏
  已知 metrics。Planned tokens 與 actual usage 分開，`quality_reserve_used` 由 route envelope
  重算。
- 目前 saved-workflow runtime 沒有完整可信 actual token/cache/tool telemetry，因此這些欄位
  必須 honest partial/unavailable；compiler estimate、budget cap 或模型 self-report 不是實測。
- actual session spend 目前設計上**無 repo 端 cap**：邊界由 admission caps（fan-out /
  retry / per-call planned prompt fail-closed）+ operator platform usage limit 聚合
  backstop 構成；監測用 transcript-size proxy（見 sub-agent-hygiene-sop 的
  Background-wave liveness 節，proxy 永不得充當 actual-usage accounting）；真 cap 延後至
  runner 提供 turn/token limit 選項或 platform-attested telemetry 可得時再議。
- Closure 後另以 immutable closure digest 綁 `closure_quality_followup_v1`，追蹤 reopen、
  rework、false closure、decision-changing findings 與 realized value；measured follow-up
  必須有 caller-trusted platform/external attestation，缺失保持 scheduled/unavailable，不補 0。

節約判斷以 durable accepted closure 為分母，同時看 reopen/rework、false closure、P0/P1
recall 與 lead time；不得用低報 usage 或少開 verifier 製造虛假效率。

## 7. Full Audit controller and consumption policy

Full Audit 保留獨立 discovery、negative space、seam critic、原始 finding、雙質疑者與
coverage holes。改進的是 scheduler，不是砍深度：

- 任何 model call 前先重驗 inline compiler-produced Context、exact task prompt/hard stops、
  source freshness 與 Registry full-audit budget authority；caller 自簽 cap 或平行欄位 mismatch
  以 0 calls fail closed，不能先花資源再等 Closure 拒絕。
- baseline 必須是 structured object，包含 exact 40-hex source HEAD、dirty/untracked
  sha256；runtime-claim surfaces 再要求 runtime HEAD + observed_at。Truthy label 不算
  frozen generation。
- discovery axes 包含獨立 source-review `E2`，且只接受 read-only audit presets；E4 是 fix
  後 regression phase，TW 是 writer，兩者不能冒充 discovery axis。
- scope/risk 觸發 mandatory axes，保留 rotating negative-space axis。
- exact duplicate claim 可共用 deterministic evidence；同 symbol 的不同 assertion 不合併。
- deterministic check 先於 LLM verification。
- HIGH/CRITICAL outcome 至少有 source/impact 兩份 typed verifier vote；兩票分歧、CRITICAL
  或高風險 defect 才要求第三份 reachability vote。Confirmed/refuted/disputed、dissent、
  reachability 與 latent 狀態全部由 Closure validator 從 `verifier_votes` 重算，不能由
  workflow boolean 自報。
- `max_unique_nodes`、`max_call_attempts`、`retry_budget`、per-call exact UTF-8 byte cap 與
  UTF8-bytes/4 planned lower-bound caps 是不同 authority；後者不是 provider actual token
  telemetry，更不能把 residual claim 變 PASS。
- admission accounting 必須涵蓋 audit、worst-case infrastructure relay、seam critic、
  verifier reserve、optional E1/E2 fix pair 與 E4 regression；任何 phase 不得游離在
  max calls/tokens 之外。Planned reserve 與 actual telemetry 分開。
- budget/agent cap 到達時留下 explicit coverage debt；結果至多 CONDITIONAL/UNVERIFIED。
- Full Audit ceiling 使用 44 unique / 46 attempts（13 discovery + seam + 13 claims 的 two-view
  challenge + 1 global risk-conditioned third vote + 3-node atomic fix chain，另含 2 retry attempts）；
  這是 worst-case ceiling，不是每輪 target。`fix=true` 在 claim admission 前原子預留
  E1 fix + E2 exact review + E4 regression。超出的 verification/fix work 只輸出
  `full_audit_split_recommendation_v1` 與 exact coverage-debt digest；它不是 verdict authority。
  下一輪必須建立新 task、重新 compile Context 並重建 evidence，不接受 caller checkpoint、
  inherited vote/fix 或 saved-workflow resume。這個 cold restart 刻意縮小未使用的 trust surface。
- Workflow 另產唯一 `full_audit_control_v1` controller fragment 與 exact
  `closure_admissions`，並附全 call manifest/wave record。Controller baseline、expected/admitted/deferred axes、debt/holes、
  assumptions/disputes、seam 與 eligibility 由 Closure validator 重算；adaptive selection
  由 routed surfaces + run sequence 重算，並需 hash-pinned recall authority。任一 admitted
  axis 都需 controller-bound fragment digest，seam 與 verification outcome 也有內容 digest；
  debt 用 canonical JSON lossless 投影。Low/refuted finding 可保留為
  `PASS + DONE_WITH_CONCERNS`，但任何 debt、缺軸、dissent 或 decision-changing finding 都
  不能被 PM 省略成 global PASS。
- Raw finding 缺 title/assertion/evidence/file/symbol anchor 時不會消失；validator 由內容產生
  stable claim debt，要求一對一投影。Optional E1 fix 只產 isolated、base/candidate head +
  patch/diff digest 綁定的 candidate；E2 必須 review 同一 candidate。沒有外部
  `APPLIED_VERIFIED` integration 就保持 `NOT_INTEGRATED` debt，E4 不得替未整合 candidate
  製造 regression PASS。
- adaptive 模式先 shadow benchmark；每 10 次或 30 日跑一次固定 backstop，直到 recall
  non-inferiority 已證明。

追蹤：accepted decision-changing findings/token、P0/P1 recall、false positive、verdict
reversal、reopen rate、time-to-evidence、cache validity、retry/rework；不以 raw finding
count 作主要績效。

## 8. Profit-diagnosis controller

`profit_diagnosis` 不是自由 fan-out brainstorming。`profit_diagnosis_control_v1` 綁 closure
baseline、scope/focus、canonical priors digest、Registry 規定的 OPS/MIT/AI-E evidence axes、
QC/BB/IB/MIT/AI-E/EXT probe axes、admitted/deferred partition、每個 fragment digest、PA map、
coverage debt、unverified projection、完整 call manifest/wave record 與 governed envelope。Mandatory evidence、deferred/missing
probe、evidence gap、map 不 ready 都必須有 typed debt；controller 的 `decision_ready`/
`pass_eligible` 由 bound fragments 與 debt 重算。

Envelope 計入 mandatory evidence、PA map、所有 admitted probes 與 worst-case bounded retry，
且 exact 等於 inline Context 的 compiler/Registry authority；workflow-local或caller cap 不可
另開第二套預算。Mandatory OPS/MIT/AI-E + PA map 不得因成本消失。Current priors 必須以
task-contract `claim_inputs.profit_priors` +
canonical SHA-256 typed authority claim 綁定，
不能沿用未驗證的內建 verdict snapshot。Top moves 可以為空；有完整 negative search 與下次
review condition 比強造機會更有價值。

## 9. CLI

```bash
python3 helper_scripts/maintenance_scripts/agent_governance.py validate
python3 helper_scripts/maintenance_scripts/agent_governance.py render --check
python3 helper_scripts/maintenance_scripts/agent_governance.py route @task_facts.json
python3 helper_scripts/maintenance_scripts/agent_governance.py context --role E2 @task_facts.json
python3 helper_scripts/maintenance_scripts/agent_governance.py closure @closure.json
python3 helper_scripts/maintenance_scripts/agent_governance.py project-closure @closure.json
python3 helper_scripts/maintenance_scripts/agent_governance.py authority @claims.json
python3 helper_scripts/maintenance_scripts/agent_governance.py evidence-key @test_facts.json
python3 helper_scripts/maintenance_scripts/agent_governance.py capture-command --native-agent E2 --node-id independent_review --context-artifact @context.json -- rg --version
python3 helper_scripts/maintenance_scripts/agent_governance.py closure-quality @followup.json
```

## 10. Acceptance

- Registry lint + generated views zero drift。
- Narrow source work 不啟動 QA/full regression ceremony；E2/E4 hard edge 仍在。
- Authority/runtime/venue/e2e facts 觸發正確 verifier 與 Adapter。
- Mandatory context 永不被 budget 截斷。
- Context/task contract、side-effect class、fragment 與 closure digest 全鏈一致。
- Uncertainty 缺失、native identity/class/permission mismatch、DAG dependency 未完成時 0 calls fail closed。
- Verdict-relevant `claim_inputs`、call manifest/wave、producer task/context/role/result 全鏈一致。
- Orchestrator structural ledger exact-cover 所有 captured waves；ghost/duplicate/omitted wave 不可 PASS。
- `DONE+FAIL` valid；hard-gate FAIL 不可被 closure PASS 覆蓋。
- Self-digest 只證 integrity；evidence-class substitution、stale authority 與假 consumption 不可支撐 PASS。
- Repo authority value 非 exact Context-byte identity projection、repo mutation 無 exact before/after
  change record、EXECUTED/REUSED 無可 trusted-replay command capture 時不可 PASS。
- Test signature 任一 source/diff/toolchain/env/config/runtime/auth 變動即 miss。
- Read-only Bash mutation 被拒；OPS/IB 無 effect capability。
- Deploy apply 即使通過 trusted local probe reconciliation，仍在 rollback binding 與 stable
  observation-window controls 未綁定時於 component invocation 前 fail closed；broker/external
  effect route 不可 PASS。
- Adaptive Full Audit 或 profit diagnosis 未完成 coverage/controller binding 時不能 PASS。
- Full/Profit inline Context 或 compiler budget authority 不相符時在首次 model call 前拒絕。
- 重複結論不增長 role memory/per-role reports。
