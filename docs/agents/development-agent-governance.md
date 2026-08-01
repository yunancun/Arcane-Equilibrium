# Development-Agent Governance Module

Status: active Interface, 2026-07-30
ADR: `docs/adr/0050-development-agent-governance.md`,
`docs/adr/0052-gpt56-bounded-multi-agent-execution.md`

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

Registry 同時持有 exact `model_routing_v1`，renderer 把 model 與 reasoning effort
明寫進每個 native TOML，controller 再把 requested identity 綁入 call receipt。預設
subagent 是 `gpt-5.6-terra/medium`；`CC/E2/E3/MIT/PA/PM/QC` 的高歧義、對抗或
關鍵判斷使用 `gpt-5.6-sol/high`。`max`/`xhigh` 不可由 parent 繼承，也沒有隱式
critical 例外；若未來需要，必須先成為 Registry 中具名、測試覆蓋的 node policy。
Claude saved workflow 另由 `saved_workflow_model_policy_v1` 精確釘住
`claude-sonnet-5` 與逐角色 effort；controller config、task 欄位與 session inheritance
都不能覆蓋它。

跨角色共通的 authority/context/economy/permission/effect/web/capture/output 規則只存在於
`native_operating_contract_v1`，由單一 renderer helper 投影；role lens、activation、
Own、Refuse、judgment 與 E4 verifier/writer identity 仍逐角色保留。Exact-once renderer
tests 防止「為了縮 prompt 刪掉 invariant」或重新複製共通 prose。

新增的兩個 preset：

- `OPS(explorer)`：唯讀 preflight、rollback、postcheck、source-build pin、RCA。
- `IB(explorer)`：IBKR Broker Compatibility Adapter reviewer，守 ADR-0048/TWS/
  session/entitlement/paper-shadow typed denial。

`OPS` 不 apply；`IB` 不 contact。Effect 只能走下方 deterministic Adapter。

### Context Interface

```text
compile_context(
  role,
  task_facts_with_optional_evidence_state,
  execution_dag=exact_call_producing_nodes,
) -> context_plan_v1
```

Context capsule 分三層：

1. immutable exact core：user objective/scope、acceptance、hard stops、baseline、
   direct Interface、上一輪 failure/concern。
2. task evidence：由 role/surface 選 context pack，附 path、selector、digest。
3. expandable history：role memory、舊 report、archive 只由 exact `history_refs`
   點名直接相關的 Markdown H2 section，最多四段。

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
`dirty_scope`、可選 `verification_scope`、direct interfaces、previous failure、
可選 `history_refs` 與 verdict-relevant `claim_inputs` 正規化成
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

`active_state` 不再投影整個 `TODO.md`：compiler 只讀 exact
`S2E 當前 ACTIVE 派發` 表，選唯一 ACTIVE row 與 direct dependency rows，最多
8 KiB，並對投影 bytes 計 digest。`history_refs` 每項綁 allowlisted safe path、exact H2
heading 與 digest，單段 16 KiB、總量 32 KiB；glob、whole-file、symlink、traversal、
未選 section 均拒絕。因而無關 TODO/history 變更不再破壞 shared Context/cache key。

Budget 分開管理 single-call planned lower bound、exact prompt bytes、workflow planned
lower bound、unique nodes、call attempts 與 retry：

- `target` 是正常高效路徑，不是內容 cap。
- `quality reserve` 專供 hard-risk、矛盾、低置信、跨語言/runtime、second thought。
- `target + quality_reserve` 以上、但仍低於 per-call planned/byte caps 的 reviewed band
  可在有明確 rationale 時保留單一高品質 call，避免拆分後重複載入 core/source；到 cap
  才拆任務或升 context，絕不截斷 mandatory content。
- Full Audit 有更大的 envelope。
- budget 用完但 evidence 未閉合，只能 `NEEDS_CONTEXT/UNVERIFIED/BLOCKED`。

Context plan 另綁 `context_execution_dag_binding_v1`：exact canonical nodes、
predecessor edges、DAG digest、node count 與 edge count。省略 `execution_dag` 時 compiler
綁 deterministic routed call-producing DAG；generic `agent-wave` 若加入 adaptive nodes，
PM 必須在 materialize 前把完整 wave DAG 傳入 compiler。Generic caller DAG 可以是合法
superset，但必須逐欄保留每個 canonical routed call-producing node 的 identity、
role/native、predecessors、class 與 permission；省略或用同 node id 替換其 core 都拒絕。
Full Audit 與 Profit Diagnosis 無論 implicit 或 explicit 都只接受 fixed graph。若
specialized route 另含 `business_acceptance`、`security_gate`、`ops_observation` 或其他
固定圖外 call，compiler 在 materialize 前回傳 typed
`SPECIALIZED_WORKFLOW_SPLIT_REQUIRED`、surface 與排序後的 extra node ids；PM 只依
`error_code` 分流。Typed split 只在 Registry/artifact metadata、完整 routed
obligations、canonical ASCII node ids、native bindings、acyclic topology 全部 exact
時成立；mixed metadata、omission/substitution 或 malformed `requires` 一律是普通 DAG
failure。PM 重新 compile 固定 saved-workflow 及 non-specialized generic/host
兩份 fresh Context，不得切割、重簽或重試被拒 artifact。普通 DAG mismatch 或混合
omission/substitution 不是 split signal。兩個 saved workflow 亦在 call 1 前做同一精確
判別，不能以 superset 或 mixed tamper 啟動 partial wave。Compiler 先依
task risk/surface 取 base
envelope，再按 exact node count 選最小可容納 envelope；四節點仍是 narrow，五節點會合法
提升為 standard。Materializer 與獨立 validator 都重算 binding 和最小 envelope；只改
authority/self-digest、縮 node/edge count 或換 DAG bytes 都不能自鑄升級。使用 injected
Registry 時 compile、materialize、validate 必須傳同一份已通過治理驗證的 Registry；
Context plan 額外綁 canonical Registry content digest，generated saved-workflow 亦只接受
checked-in generation，禁止中途 ambient reload、刪除 axes 或跨 generation 重用 artifact。

`agent-wave` 不接受裸 legacy task array 或 raw `contextPath`。每個 admitted node 只帶一份
`context_artifact_v1`：Python compiler 保留完整 canonical envelope 供 closure 重驗，另產
authenticated shared semantic capsule + role delta 作為 prompt/cache prefix；receipt/ambient
dirty metadata 不污染 repository-derived semantic key，但 verdict evidence 的 TTL/trust 會。
Workflow 在 JS 端獨立重算 semantic digests。Wave 與 infrastructure retry 重用 admission bytes，
不 reopen path，避免 substitution/TOCTOU。Role/digest
必須相符，`omitted_mandatory=[]`、`unresolved_sources=[]`、所有 source 都有 byte-backed
digest、`budget.pass_allowed=true` 才執行。Inline artifact 仍可能被每個 agent ingest；cache
收益只按平台實測記錄，不能宣稱「只付一次」。

Closure capture 會把 `workflow_wave_record_v1.admitted_tasks` 的 ordered execution-node
core 與 `dag_digest` exact-compare 到已驗證 Context 的
`context_execution_dag_binding_v1`。因此在 Context 之後追加節點，即使同步重算
call records、manifest、wave 與所有 packet-local digest，也不能被舊 Context 接受；
合法擴 DAG 必須先重新 compile/materialize Context。

每一次 model call（含 infrastructure retry）都由 controller 產
`workflow_call_record_v1`，綁 workflow contract、logical call/node/role/payload、requested
model/effort/isolation、prompt、context/task/dirty-scope/focus/response-schema digest、exact
native agent/node class/permission、DAG predecessors/topological wave、producer generation、
execution surface、history mode/boundary/exception、attempt/retry parent、timestamps、
null state 與 exact parsed-result digest。Dependencies 只有在
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
direct interfaces、previous failure、可選 `history_refs` 與可選
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
runtime code change 機械式增加 review。沒有 intervening effect 的 read-only/source lane
只產一個 `ops_observation`；只有 admitted effect 才保留 separated preflight →
effect Adapter → postcheck。

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
- read-only runtime claim 或 operational observation → 一個 `OPS ops_observation`。
- operational effect/deploy → `OPS preflight`；deploy 再經 PM/operator exact intent →
  Deploy Adapter contract → `OPS postcheck`；trusted local probe
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

Envelope 在完整 required-node DAG 建成後才選擇／提升，不能用 pre-route 猜測後再產出
不可執行的 node set。`narrow` 同時最多 2 個 model calls，其餘目前最多 3 個；每個
generated workflow 透過同一 rolling bounded worker pool 執行 first attempts、retries
與其他 runnable calls。任一 call 完成即補下一個 factory，不等待同一固定 slice 的最慢
call；active calls 仍永不超過 Registry `max_concurrent_calls`，首錯後停止 dequeue 並先
settle 已在途 calls。

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

同一 Implementation 現另投影 `execution_budget_policy_v1` 與
`execution_surface_profile_v1`。Route、Context、requested agent、call manifest 和 wave
receipt 必須綁同一 policy/surface digest。唯一 watcher 的 event ledger 只接受 surface
明示 attested 的 event kinds，並驗 exactly-one root、parent/depth/node lineage、unique
event ID、call-record exact coverage、terminated lineage 與 distinct delegated-node cap。
Event admission 與 standalone ledger validation 都必須收到 ledger digest 所綁的
exact surface profile；缺失或不匹配一律 fail closed。Canonical wave builder 會在首次
admission 前驗完整 call manifest，並從所有 validated records 導出唯一、Registry-canonical
的 uniform surface profile。這條 post-hoc receipt path 使用明確的 structural-only
assembler；不 mint／消耗 controller capability，而且同一 manifest 可重建相同 bytes。

Live pre-action admission 是另一條 internal seam，必須持有從 pristine empty ledger 建立的
non-serializable controller capability；mint 不在 facade/public Interface，且 policy 與
surface 會精確比對 live Registry。同一 `root_execution_id` 必須在 process-lifetime lock
內原子 single-claim；tombstone 不隨 controller GC 釋放。Controller 私有保存唯一
last-head 與 Registry policy/surface 的 frozen canonical authority；每次 cap／coverage
decision 都只從該私有 bytes 重建 ordinary mapping，caller-owned mutable mapping 只可做
exact precheck，不能成為 transition authority。Factory 只讀一次 Registry generation
來同時導出 policy/surface authority；每次 admission 亦在同一 per-instance lock 內、任何
validation/read 前把完整 caller ledger 與 event 各自 canonical-detach 成唯一 plain-JSON
snapshot，再原子執行 compare、validate、append/reject、advance。同一 head 的競爭 caller
只容許一方前進。目前沒有 managed host 把這個 mint seam 接成 general-purpose runtime
authority。

Ledger self-digest 與 standalone validator 只證明離線結構／診斷，沒有 resume
authority。Caller 不能傳入 expected previous digest 或自行重封截斷 ledger 來重置
budget；controller 不能從 non-pristine ledger 重建，persisted ledger 在沒有原
in-process capability 時一律不得繼續 admission。這個 process-local monotonic guard
不是 host/provider attestation，也不把 workflow receipt 升級為
`PLATFORM_OR_EXTERNAL_ATTESTED`。Caller 也不能只改 root/watcher 經 public facade
取得新 budget；general-purpose live mint 要等 future managed-host-attested
capability 提供不可自報的 task/root authority。Structural receipt rebuild 不持有
capability，不能拿來繼續 live ledger。
Saved workflow 目前 exact-cover root/model call/retry；call/model-turn/follow-up/wait/
no-delta/concurrency/unique-node/spawn-depth 的 count/state cap 在下一 admitted action 前
拒絕並留下 terminal reason。預設 history 是 ephemeral `none`；bounded history 需要
source thread、boundary turn 與 admitted exception digest，`all` 或欄位缺失皆拒絕。

Surface capability 必須誠實投影。Saved workflow 可 enforce selector/history/
ephemeral fork/concurrency；Codex native collaboration 目前只有 concurrency 與 disabled
interruption message 可由 project config enforce，native selector/history/fork 仍是
`reported_only`，且 repo 沒有 host adapter 可把 collaboration tool call attested 到 closure。
因此 Codex native 與 generic host 都是 mandatory-role `EXTERNAL_LIMIT`／advisory-only，
不能冒充 PA/E4 native execution。`max_wall_clock_ms`、`max_call_duration_ms` 與
`max_wave_duration_ms` 只是 Registry-declared ceilings；目前沒有 monotonic clock、
in-flight timeout/cancel Adapter，故 per-call/wave deadline/cancellation 與 platform token
telemetry 都固定 `unavailable`／`EXTERNAL_LIMIT`。Model-visible interruption message 在
governed Codex calls 中關閉，避免未進 receipt 的 context mutation。

Liveness 的 pure adjudicator 是 caller-claim classifier，不是 host-evidence verifier。
它不接受 caller 自報 `now` 或 caller 注入 verifier，而是內部讀可信 system UTC。
Registry 的 `agent_liveness_policy_v1` 以 digest 綁定 60 秒
`max_observation_age_seconds` 與零 future skew；age 恰好 60 秒仍 fresh，任何正 excess
即 stale。結果把 claim 的 `observed_at` canonicalize 成 UTC `Z`，並保留 trusted
`adjudicated_at`、freshness、policy ID/digest 與 max age。

Freshness 只描述 caller timestamp 與可信 clock 的距離，不能證明 host acquisition。
因此 caller mapping 即使聲稱 fresh `RUNNING`、`WAITING` 或 terminal，結果也固定為
`UNKNOWN + CALLER_ACTIVITY_UNVERIFIED + EXTERNAL_LIMIT`；caller 額外塞入 identity、
sequence 或 head 會因 exact contract 被拒絕，不能充當 monotonic proof。Future
host-attested activity acquisition 必須由 managed out-of-band host Adapter 取得
activity，綁定 stable identity 與 monotonic sequence/head，並拒絕 replay、rollback、
fabrication；屆時使用新的 verified contract，不能放寬此 current saved-workflow pure
Interface。

Missing private JSONL 保持 diagnostic `UNAVAILABLE`，size/mtime 也只作 diagnostic；
repo 尚無 host activity-acquisition/controller Adapter，故實際 wait/no-delta/stop
integration 是 `EXTERNAL_LIMIT`，不可因 helper 存在就宣稱已接入。Transcript 超過
10 MiB 只可形成 `RUNAWAY_SUSPECT` 供 PM adjudicate，永不自動 stop，也永不冒充
actual token usage。

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

#### AIML S0.3 trusted-host program-adoption finalizer

S0.3 唯一 production 收口介面是：

```text
python3 helper_scripts/maintenance_scripts/agent_governance.py aiml-trusted-finalize \
  --packet <closure.json> \
  --execution-bundle <trusted_execution_bundle_v1.json> \
  --execution-signature <trusted_execution_bundle_v1.json.sig> \
  --github-token-fd <inherited-fd>
```

三個 path input 必須是 finalizer effective user 擁有、不可 group/world write 的 regular
file；reader 不 follow symlink 且有 size bound。GitHub credential 只可由 inherited owner-only
regular-file/pipe FD 傳入，不得放進 argv、JSON、repo artifact 或輸出。Production facade 只收
packet、bundle、detached signature 與 credential bytes；caller 不能注入 clock、repo root、
Git/GitHub verifier、transport、API origin、CA roots 或 trust key。
Pipe credential 是單一 `newline-framed` frame（closed pipe 仍可用 EOF 結束），且 reader 必須
在固定 deadline 內完成；保留 write end 不得令 finalizer 無限等待 EOF。
GitHub transport 固定 `2022-11-28` REST API version，以維持 merged PR 的
`merge_commit_sha` projection；version drift 必須先經 live-shape compatibility review。

Execution bundle 的 reviewed source trust root 固定為 identity
`aiml-s03-operator-v1`、Ed25519 fingerprint
`SHA256:uGJ9veN7PoE6BBgfsSP2aiMndrwgbt7o/7/YfdzNzCQ`、SSHSIG namespace
`arcane-equilibrium-aiml-s03`。Matching private key 永遠不落在 Linux trusted-finalizer host，
只能在獨立 Operator host 對 canonical bundle bytes 做 out-of-band detached signing；caller
不得選 key/identity/namespace。Bundle 必須 exact-bind task-contract、Context、DAG 與每一份
被 Closure 消費的 attested artifact，且通過 issued/expires freshness、canonical ordering 與
exact-consumption 檢查。

`POST_MERGE_FINALIZATION` 是 read-only admission，禁止持有 writer lease。Packet 必須綁 final
merged source generation、S0.1/S0.2 receipt、program-adoption receipt、CC / E2 / E3 / E4 / MIT / QA / R4
七個 mandatory review fragment，以及其完整 authenticated call/wave execution evidence；source
或 ledger write 階段仍須正常 linked-worktree writer lease，不能沿用 read-only exception。

Source verifier 對 final merge generation 執行 `merge-base --is-ancestor`、exact commit/blob
manifest 與 bounded object capture，並拒絕 shallow、replace/graft、alternate/promisor 與 path
escape。GitHub verifier 只連 fixed API origin，使用 system CA、禁 proxy inheritance/redirect，
並 live 驗 repository identity、default-branch ref、reviewed/merge commits、compare ancestry、
effective ruleset 與 exact required checks/integration IDs。`github_capture_projection_v2` 另須
分頁擷取 reviewed head 的 associated PR inventory、exact merged PR detail 與
`check-runs?filter=latest`：唯一匹配 PR 必須由同 repo 的 exact reviewed head 合併到 main，
`merge_commit_sha` 等於 merge head，merge commit 直接含 reviewed head parent；每個 required
`(context,integration_id)` 只可有一個 completed/success run，且完成時間不得晚於 PR
`merged_at`。Packet-local attestation、merge 後補跑的 check、cached policy JSON 或
caller-selected endpoint 都不能替代這條外部驗證。
Two-parent merge 的第二個 parent 必須是 exact reviewed head；第一個 parent 必須是合法且互異的
base parent，但不得綁 PR API 的 `base.sha`。Check Run 的 `pull_requests` 可為空（權威綁定是
exact `head_sha`）；若非空則必須包含目標 PR。這組 REST evidence 分別證明 exact merged PR、
合併前 successful checks 與 finalization 當下的 live ruleset，不宣稱 ruleset 在歷史 merge
時刻連續生效；該宣稱另需 platform audit/event attestation。

只有 finalizer 回傳 `status=PASS` 且帶 exact `program_adoption_receipt_digest` 時，該 receipt
才可代表 `PROGRAM_ADOPTED`；任何 signature/source/GitHub/reviewer/freshness/consumption 錯誤皆
fail closed 且不得宣稱 adoption。此介面只認證 S0.3 program adoption，不新增 ML5/ML6、runtime
deploy、broker/order/live、Decision Lease 或任何交易 effect authority；authority limits 與
four-zero-effects 持續為 const-false。

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
- `pg_observer_bootstrap_adapter_v1`（S2.0 WP2 SOURCE seam）：Registry status
  `declared_production_apply_disabled_until_operator_sshsig`。它從一張 exact typed
  `pg_observer_bootstrap_intent_v1` 投影**一組**結構化 allowlist（enum key
  `observer_read_only_v1`，絕非呼叫端 raw SQL）產出的**最小唯讀 least-privilege observer 角色**
  （`CREATE ROLE NOLOGIN NOSUPERUSER NOCREATEROLE NOCREATEDB NOREPLICATION NOBYPASSRLS` +
  `GRANT USAGE ON SCHEMA` + 對 exact observed relations 的 `GRANT SELECT`；role-level 釘死
  `default_transaction_read_only=on` 與 `search_path=pg_catalog`；peer/ident local auth，no
  password ingress）。對生產 PG 的真 apply **恆 fail-closed**：即使帶一張 VALID SSHSIG，WP2 source
  lane 也絕不開生產 socket，回傳一個 typed `EXTERNAL_VERIFICATION_PENDING` result（**永不**假成功），
  直到一張 exact source-pinned、**domain-separated** 的 operator SSHSIG 存在（identity
  `aiml-s2-observer-bootstrap-operator-v1`、namespace
  `arcane-equilibrium-aiml-s2-observer-bootstrap`；operator 私鑰既不在 Mac 也不在 trade-core）。applier
  != 獨立 postcheck verifier（role/node/process/capture 皆相異），closure binding 綁 verifier 自己的
  governed `command_capture_v2`（三方 digest 交叉核對）並要求 exact restoration（pre == post catalog
  projection、observer 消失）。此 binding 為 **SOURCE-only**：未接入 live `route_task` effect 節點，亦不注入
  closure effect 綁定，真正的活化屬 **S2.0 EFFECT session**。Evidence：可拋棄叢集 apply 為
  `LOCAL_REPRODUCIBLE`（真 `initdb`/`42501`/`28P01`，nothing mocked），platform/external attestation
  DEFERRED；nine authorities 恆 false，任何 receipt 不序列化機密。完整活化 ADR deferred 給 S2.0 EFFECT
  session。
- `alr_quiesce_fence_adapter_v1`（S2.1 WP3 SOURCE seam）：Registry status
  `declared_production_fence_disabled_until_s20_effect_and_operator_sshsig`。它對 **system-level**
  `arcane-equilibrium-aiml-engine-scanner.service`（host system manager 擁有 lifecycle；PR #134
  realigned，normative 源=operator-merged corrected S2.4 §8 + ADR-0050 2026-07-25 增補）做
  owner-scoped、可逆的 quiesce fence：只有 multi-signal ownership predicate 確認
  `CONFIRMED_SINGLE_OWNER` 才 fence，且 fence 是該 unit 自己的 system-level `systemctl stop`
  （永不 `--user`、永不 pkill/kill-by-name/pattern/pid），restore 是同 unit 的 system-level
  `systemctl start` + stable-identity pre==post 復原 crux。production/live fence **恆 fail-closed**：
  回 typed `EXTERNAL_VERIFICATION_PENDING`，直到 `S2.0@EFFECT_DONE` + S2.1 EFFECT session 的
  exact source-pinned、domain-separated operator SSHSIG（identity
  `aiml-s2-quiesce-fence-operator-v1`、namespace `arcane-equilibrium-aiml-s2-quiesce-fence`）存在，
  並依 §1.2 修正後 effect DAG 排在 S2.4 install（`EFFECT_DONE_INACTIVE`）+ S2.5A start 之後。
  已知開放對齊項（blocking S2.1 EFFECT drill，非 W0/W1 source admission）：WP3 C1 invocation
  fingerprint／env-hash 契約與 S2.4 §8.3 rendered ExecStart（`launches/<digest>` + `-B` + 完整
  application/launch/topology 參數與十個環境變數）尚未逐位對齊，須由 W2 unit renderer 定案
  argv 後以 WP3-side fingerprint amendment 收口。九項 authority 恆 false；EFFECT 時所需
  root/polkit `manage-units` 屬 operator 動作。
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
- actual session spend 目前只有 repo 端可驗的 structural count/state caps（calls/model
  turns/follow-ups/waits/no-delta/concurrency/unique nodes/spawn depth）與 planned prompt
  caps；wall/call/wave duration、in-flight cancellation 與 provider total-token cap 都是
  machine-detectable `EXTERNAL_LIMIT`，不能被 repo 自報值取代。
  operator platform usage limit 仍是聚合 backstop；監測用 transcript-size proxy（見
  sub-agent-hygiene-sop 的
  Background-wave liveness 節，proxy 永不得充當 actual-usage accounting）；真 cap 延後至
  runner 提供 token/cancellation capability 或 platform-attested telemetry 可得時再議。
- Closure 後另以 immutable closure digest 綁 `closure_quality_followup_v1`，追蹤 reopen、
  rework、false closure、decision-changing findings 與 realized value；measured follow-up
  必須有 caller-trusted platform/external attestation，缺失保持 scheduled/unavailable，不補 0。

節約判斷以 durable accepted closure 為分母，同時看 reopen/rework、false closure、P0/P1
recall 與 lead time；不得用低報 usage 或少開 verifier 製造虛假效率。

`multi_agent_efficiency_evaluation_v1` 對同一 case 比較 current、single-agent 與
bounded-role 三個 profile。先判 closure quality/required coverage/decision-changing
finding 的 non-inferiority，再比較 elapsed、input/output/cached tokens、calls、waits、
retries、compactions、reopen/rework。Non-inferiority threshold 由 Registry exact policy
固定為：

- `max_closure_quality_score_drop=0.0`
- `minimum_required_coverage_ratio=1.0`
- `max_reopen_count_increase=0`
- `max_rework_count_increase=0`
- `max_false_closure_count_increase=0`
- `minimum_p0_p1_recall_ratio=1.0`
- `minimum_decision_changing_findings_retention_ratio=1.0`

Registry authority 以 `allow_nan=false` canonical JSON bytes 做 type-sensitive 比對；
重簽 digest 不能把 `0.0` 換成 integer `0`，也不能把 boolean `false` 換成 integer
`0`。evaluation payload 不可自訂。Quality PASS 仍不等於 efficiency：Registry 的
`all_axes_non_worse_and_one_strictly_better_v1` 要求 `elapsed_time_ms`、
`input_tokens`、`output_tokens`、`cache_read_tokens`、`calls`、`waits`、`retries`
與 `compactions` 八個 raw-value 軸全部小於或等於 current baseline，且至少一軸嚴格
較小；任一軸缺值、全部相等或任一軸變差都不產生 efficiency candidate。這個 Pareto
門同時約束 synthetic `benchmark_only_candidates` 與 measured claim；synthetic fixture
仍只驗 schema 與 adjudicator，永遠不能成為 measured savings。

實際節省另需 typed attestation index 綁唯一 run IDs、不可跨 run 重用且逐 profile
長度 exact 等於已報告 `metrics.calls` 的 call-record inventory、metrics/attestation/index
digests，再由帶外 trusted-host verifier 認證 exact index。`metrics.calls=0` 唯一匹配
空 inventory；partial profile 的 `metrics.calls=null` 也只能綁空 inventory，不能一面
聲稱 call count 不可得、一面列出未能 exact-cover 的 calls。每個已報告 call count 的
profile 另須滿足 `retries <= calls`。Free-form ref 或 packet self-digest 永不解鎖
measured；standalone CLI 固定 `EXTERNAL_LIMIT`。

## 7. Full Audit controller and consumption policy

Full Audit 保留獨立 discovery、negative space、seam critic、原始 finding 與
coverage holes。saved workflow 的執行面固定為 13 axes + seam；data-dependent
verification/fix 另屬 fresh host-attested phase：

- 任何 model call 前先重驗 inline compiler-produced Context、exact task prompt/hard stops、
  source freshness、Registry full-audit budget authority，以及完整 14-node execution DAG
  的 node identity／native role／predecessors／class／permission／count／digest；caller
  自簽 cap、平行欄位或 DAG mismatch 以 0 calls fail closed。
- baseline 必須是 structured object，包含 exact 40-hex source HEAD、dirty/untracked
  sha256；runtime-claim surfaces 再要求 runtime HEAD + observed_at。Truthy label 不算
  frozen generation。
- discovery axes 包含獨立 source-review `E2`，且只接受 read-only audit presets；E4 與
  TW 不在此 saved-workflow DAG，不能冒充 discovery axis 或由 post-call finding 動態加入。
- `scheduler=full` 跑完整 13 discovery axes，這也是目前唯一可執行／closure 的模式。
  Reduced `scheduler=adaptive`、`adaptive_shadow` 或 `full` 下的 axes subset 在首次
  model call 前一律以 `EXTERNAL_LIMIT_RECALL_AUTHORITY` 拒絕。Task-contract
  `claim_inputs`、boolean、self-digest、`claim_evidence` 或一般 execution attestation
  都不是 recall/non-inferiority authority。只有未來獨立的
  `PLATFORM_OR_EXTERNAL_ATTESTED` recall Adapter 加上帶外 host verifier 才可重新開啟；
  standalone workflow／Closure 不能自行解鎖。Focused/no-finding 的 14→6 目前只是假設
  candidate，不是可執行或已實現的節省。
- exact duplicate claim 只作 presentation grouping；同 symbol 的不同 assertion 不合併。
  deterministic structural check 後，每個 zero-outcome decision claim 均保存為 typed
  `staged_claim_verification` debt，exact 綁定 `MAE-005`、
  `REQUIRES_HOST_CAPABILITY_PHASE` 與 sorted unique `bound_axes`。它是
  `UNVERIFIED`，不是已驗證的 dispute；跨 axis exact duplicate 共用一個 claim/debt，
  其 binding 必須 exact-cover 全部原始 axis。
- current saved workflow 不執行 verifier、third vote、E1 fix 或 E2 fix-review。任何此類
  call 都必須建立新 task、由 host 取得 `MAE-005 /
  EXTERNAL_LIMIT_NATIVE_SELECTOR_ATTESTATION` authority、先 compile 當輪 exact DAG；
  否則呼叫數固定為 0，不能把缺席的 host phase 宣稱成 verification outcome。
- Closure validator 仍可重算由「另行 admission、且 receipts exact-cover 新 DAG」產生的
  typed verifier votes；這不授權 current saved workflow 自行生成那些節點。
- `max_unique_nodes`、`max_call_attempts`、`retry_budget`、per-call exact UTF-8 byte cap 與
  UTF8-bytes/4 planned lower-bound caps 是不同 authority；後者不是 provider actual token
  telemetry，更不能把 residual claim 變 PASS。
- current admission accounting 只涵蓋 13 audit first attempts、全局有界 audit
  infrastructure retries 與 seam critic；不存在 verifier/fix speculative reserve。
  Planned authority ceiling 與 actual telemetry 分開。
- budget/agent cap 到達時留下 explicit coverage debt；結果至多 CONDITIONAL/UNVERIFIED。
- Registry Full Audit policy 的 44 unique / 46 attempts 是未來 separately admitted
  host phase 可用的 authority ceiling，不是 current 14-node workflow 的 reservation 或
  actual usage。`fix=true` 只新增 MAE-005 host-phase debt，不產生 writer/reviewer call。
  current 結果輸出 `full_audit_split_recommendation_v1` 與 exact coverage-debt digest；
  它不是 verdict authority。
  下一輪必須建立新 task、重新 compile Context 並重建 evidence，不接受 caller checkpoint、
  inherited vote/fix 或 saved-workflow resume。這個 cold restart 刻意縮小未使用的 trust surface。
- Workflow 另產唯一 `full_audit_control_v1` controller fragment 與 ordered exact
  14-node `closure_admissions`：13 個 `role_fragment` axis admissions 加最後一個
  `nested_payload` `seam:critic` admission，且其 DAG core 與 Context binding 完全一致；
  並附全 call manifest/wave record。Controller baseline、expected/admitted/deferred axes、debt/holes、
  assumptions/disputes、seam 與 eligibility 由 Closure validator 重算；任何 reduced
  selection 在缺少帶外 platform recall verifier 時直接保持 `EXTERNAL_LIMIT`。任一 admitted
  axis 都需 controller-bound fragment digest，seam 有內容 digest，current
  `verification_outcomes` 固定為空；debt 用 canonical JSON lossless 投影。Low/INFO
  finding 可保留，但任何 debt、缺軸或 decision-changing finding 都
  不能被 PM 省略成 global PASS。
- Raw finding 缺 title/assertion/evidence/file/symbol anchor 時不會消失；validator 由內容產生
  stable claim debt，要求一對一投影。current workflow 的 `fixes=[]`、`regression=null`；
  E4 不得替不存在或未整合的 host-phase candidate 製造 regression PASS。
- `scheduler=full` backstop 與 candidate adaptive run 進相同
  `multi_agent_efficiency_evaluation_v1`；必須先證 closure quality/recall
  non-inferiority，並由帶外 host verifier 驗證 exact typed attestation，才可在未來啟用
  adaptive 或把較少 calls/tokens/elapsed 視為收益。Caller-provided policy ref、
  self-digest 或 synthetic evaluation 永遠不足。

追蹤：accepted decision-changing findings/token、P0/P1 recall、false positive、verdict
reversal、reopen rate、time-to-evidence、cache validity、retry/rework；不以 raw finding
count 作主要績效。

一般 delegated review 使用 `review_control_v1` 作 scope admission：finding 必須分類為
`in_scope_blocker`、`regression_blocker`、`out_of_scope_followup` 或 `pre_existing`，
severity 不參與 blocker 裁定。每個 reviewer 只允許一次 initial review 與一次針對原
blocker ID 的 exact recheck；task contract 不變，每輪綁定完整 frozen repository
generation。新 finding、第三輪或 generation drift 都停止而不自動擴張 task。

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
python3 helper_scripts/maintenance_scripts/agent_governance.py efficiency-evaluation @evaluation.json
python3 helper_scripts/maintenance_scripts/codex_memory_policy_probe.py
python3 helper_scripts/maintenance_scripts/role_memory_compaction.py --check
```

## 10. Acceptance

- Registry lint + generated views zero drift。
- Narrow source work 不啟動 QA/full regression ceremony；E2/E4 hard edge 仍在。
- Authority/runtime/venue/e2e facts 觸發正確 verifier 與 Adapter。
- Mandatory context 永不被 budget 截斷。
- Context/task contract、side-effect class、fragment 與 closure digest 全鏈一致。
- Uncertainty 缺失、native identity/class/permission mismatch、DAG dependency 未完成時 0 calls fail closed。
- Verdict-relevant `claim_inputs`、call manifest/wave、producer task/context/role/result 全鏈一致。
- Requested model/effort/surface/history 與 execution-policy digest 全鏈一致，cap 後無下一 call。
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
- Adaptive/full/single-agent efficiency 比較先過 quality non-inferiority；synthetic fixture
  不可冒充平台實測節省。
- Full/Profit inline Context 或 compiler budget authority 不相符時在首次 model call 前拒絕。
- 重複結論不增長 role memory/per-role reports。
