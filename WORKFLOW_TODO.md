# 工作流與多代理優化總帳

## 地位、邊界與目前真相

這是人工閱讀的來源限定總帳，不是可派發佇列；物理 queue 只在根目錄
[`TODO.md`](TODO.md)。`W1-local-collector` 已為 `CLOSED_LOCAL_COLLECTOR_SOURCE_ONLY`；W3 亦已為
`CLOSED_CONTEXT_MICRO_PACK_SOURCE_ONLY`，workflow lane 沒有 dispatchable row，不能推論 effective/host-selected
configuration、完整 W1、模型／政策採用、runtime、服務、PG、broker、下單、交易或獲利宣稱，也不授權
自動續跑或下一項。`W5-entry-source-binding` 仍是窄義
`CLOSED_ENTRY_SOURCE_BINDING_SOURCE_ONLY` checkpoint。

W0/W1 是本地來源 checkpoint，尚未併入 `main` 或採用：W0 final
`c90408613d6ce436abae619437a0bdc4acf4787f`，W1 final
`86ae98c5bcbb50f5d897811327c8c118b0ff166f`。`5a3666805187603c71318abe5b6dcd2c7b071457`
已是 committed ledger baseline；`e134c772e48aef74de2f585239e16a89b9816681` 是使用者核准的
W7 intermediate source checkpoint。W5 source checkpoint
`60bc55673f170a06ee4b93a2080c060160707566` 僅在本地，尚未併入 `main` 或採用；提交身份以 Git
紀錄為準。
下列歷史測試結果不是本次重跑或效能改善。
W0 initial source checkpoint 是 `9f9d277bf2ce2037c74597f065d41312f1ed53bc`；W1 initial probe
checkpoint 是 `9c34aa4b28e30e495146cdb880ae889d3ea59b4f`；W0 final E4 task digest 為
`931dc6a16de8d6d7613191afe0c6ce827f236f9ea051785b7319a4318255a9d0`，Registry 為
`0ab769848bb7490b9be067ae601b76b8e557d068bf0c481aca00b835e8ca8b23`。

不可削弱的骨架仍是：精確 task/Registry/DAG/Context 綁定、最小 dirty scope、單一
writer、來源與 runtime/effect 分列、full audit 的硬節點，以及缺可信 host verifier 時的
trusted replay。一次有限工作只做一個明確單元；無 task-owned delta 即
`BLOCKED_NO_DELTA`，不 wakeup、不重試。

## 成功基線與證據限制

已核准的 qualified-run 閘門是 Q0 ≤300 秒、Q1 ≤900 秒、P0/P1 missed=0，且
reopen、rework、false-closure 不得較基線變差。主 KPI 仍為 `elapsed_time_ms`、
`input_tokens`、`orchestration_load = calls + waits + 2*retries + 2*compactions`。
output/cache、duplicate exec/wait 僅是診斷；exec/spawn/message/followup coverage 為
`UNAVAILABLE/DEFERRED`。cached input 不能推導美元成本。

W0 的已檢查 corpus 仍是 `UNAVAILABLE/PENDING_CANDIDATE_RUNS`；沒有 platform-attested
usage、actual savings、full action coverage 或採用成效。其 final E4 是歷史
`65 passed / 30 deselected / 0 failed or denied`，不是候選 run 的量測。W1 的 public probe
可重播 caller-provided declaration snapshot，但沒有 production host verifier；實際 selected
config 仍是 `UNVERIFIED`／`COMPLETE_WITH_UNVERIFIED`。W1 final E2 `24 passed`、E4 combined
`84 passed` 同樣僅為歷史 source verification。

## 已完成 checkpoint

| 項目 | 狀態 | 保留成果與未關閉事實 |
|---|---|---|
| W0 基線與成功閘門 | CLOSED / source checkpoint | 固定 KPI、Q0/Q1 與品質 gate；不構成實際節省或採用。|
| W1 execution-surface truth probe | CLOSED / source checkpoint | 可重播來源快照與 fail-closed truth class；真實 selected config 未證實。|
| W1 local collector | CLOSED_LOCAL_COLLECTOR_SOURCE_ONLY | committed `b92417b7afed1de6a1913279af6e5743fb085b34`: E2 standards/spec PASS（4 repairs）；E4 exact-head `46/0/0/0`（22 collector + 24 existing probe），capture `sha256:f0c0083999b1b4262b004884b19f34f7b9c1728daa0fe41090cebcd3ee07f14d`，僅 `LOCAL_REPRODUCIBLE`。 |

### W7 narrow source checkpoint（current, source-only）

- `e134c772e48aef74de2f585239e16a89b9816681`：既有不變 generator 將三份 generated workflow 的
  Registry digest 由 `sha256:9ce2dbd2bca32268cac32b6941537c9e305458f97ea5fe6590cada78dad300ff`
  校正為 `sha256:0ab769848bb7490b9be067ae601b76b8e557d068bf0c481aca00b835e8ca8b23`；只有
  `agent-wave.js`、`openclaw-full-audit.js`、`profit-diagnosis.js` 各一行 generated block 改動。
- E1 完成生成、E2 獨立審查提交前同一份 source bytes PASS；E1 source record
  `sha256:b87cf06ba475ffe92ed1895737d7d01cc85a8b13c03ae9cd537504e395732ca0`；E4 `8 passed / 0 failed /
  0 skipped` 在已提交 `e134…` 上，capture `sha256:4ce8d1c76b37bef355c4ddb0ab51434eabbbff178eb5a9a139e0a072ce9641ea`，Context
  `sha256:547baf43d6933168f0a1dd7ab9347395bdc375e4c217a3f81ba6137564bbb025`。這只關閉來源一致性；
  不構成 runtime、effective config、session/performance、usage、模型採用或交易結論，也不授權 push、merge
  或下一單元。提交前驗證與 committed-tree-only capture 的差異僅為 W5 現場觀察／待評估，未新增任務或修改政策。

## W5 窄入口與來源綁定（已收口，source-only）

這是 master 對 physical queue 的人類說明，不是另一個 dispatch authority。W5 本次只處理
「entry/source binding」：未提交的驗證 subject 不得靜默改測舊 committed HEAD，同時保留 fixed
committed-tree 的安全語義。已依核准順序完成 docs checkpoint、實作／待驗證 subject checkpoint
及 exact-head verification；不產生 commit、push、merge、main sync 或下一項權限。

E2 已解決兩項真實 finding（dirty subject 的 trusted replay、LW2 缺少 trusted replay scope）；
E4 在 committed `60bc55673f170a06ee4b93a2080c060160707566` 執行，為 `120 passed / 0 failed /
0 skipped / 0 errors`，capture
`sha256:ae95998b8b0e92b17c3f17949f3011cfe68ce63b1df211fc7138df57f01eca43`，Context
`sha256:366be528a93eddb5e4904b183e301956ed8ae037324a71f44ec4d76a0ee2a78f`。這只關閉
`CLOSED_ENTRY_SOURCE_BINDING_SOURCE_ONLY`，不是完整 W5。capture reuse、toolchain/environment
signature、TTL、production host verifier 仍是 W5 residual；W7 broad generator residual 亦保持 open。

## W1 local declaration intake（已收口，source-only）

`W1-local-collector` 已收口為 `CLOSED_LOCAL_COLLECTOR_SOURCE_ONLY`：它讀取 repo
`.codex/config.toml` 和明確 supplied global `config.toml`，只取五個既有 allowlisted agent fields，
寫入既有 execution-surface probe request/truth report 的 logical source status 與 integrity metadata。
missing、rejected 或 no-data 必須保持 explicit；raw digest 只證 snapshot integrity，actual selection
仍為 `UNVERIFIED`。維持單一 canonical `agent_governance.py` CLI（mutually exclusive
`collect-local` mode），不另建 CLI/schema/Registry/permission，也不寫 settings 或推論 host-selected
configuration。E2 standards/spec 已在四項 batched repairs 後 PASS；E4 在 committed
`b92417b7afed1de6a1913279af6e5743fb085b34` 為 `46 passed / 0 failed / 0 skipped / 0 errors`
（22 collector、24 existing probe），capture
`sha256:f0c0083999b1b4262b004884b19f34f7b9c1728daa0fe41090cebcd3ee07f14d`，Context
`sha256:10d76af99625c9768f21edba44450c1d777bdceee4eb1aeb7c234ebf7931c5fc`；信任限於
`LOCAL_REPRODUCIBLE`，沒有 host attestation。2026-09-05T19:07:21Z 的 PM local observation
收集到五個 repo allowlisted fields；明確 supplied global config 為 `no_data`，collection digest
`sha256:5b2e839cbfe9c4b4b40dae2135f6ca30abba5df39389960471d4c62d25e6122d`、legacy replay
`EXACT_REPORT_MATCH`，結果 `COMPLETE_WITH_UNVERIFIED`；selected/instructions 仍
`UNVERIFIED`、profile=`CALLER_CLAIMED`。不產生自動 commit、push、merge、runtime 或下一項權限。

W1 residual 現只剩真正未 exposed 的 host-selected evidence，仍為
`WAITING_EXTERNAL_EVIDENCE`；不得把 fixture 的 `global=collected` 投影成 host fact。它不 blanket 阻擋
W2/W3/W5/W10 source slices。

歷史 `23f76…` 曾把 W2/W3/W5/W10 標成 READY；後來的 DEFERRED 是 queue aggregation，
不是那些來源課題的 technical regression。現在採用具名 blocker/owner/unblock condition，而不是
以 catch-all defer 淹沒差異。

### Historical W0 evidence ledger（未重跑）

- HITL Q0/Q1/P0/P1/reopen gate；initial admission `7328ef69a939c61c7487de70a95e8a88`、parent task
  `sha256:0cf10bb2ec2e0b034d028ce30a75cb27ef9fd113fe67579661efe6de8485441e`、DAG
  `sha256:470d27f060b347ccd899af87c3282448ad7c3a18563f8b4b64a2bde9309e6bdd`。
- final-semantics Context `sha256:a4b5bc4ecf1e1771499526b36fe86472cd81099f35501e3f06b8f12189a71c1b`、task
  `sha256:df36d299ef558d6e7f69355581404ae5d50b6ae023272a10f48e36a362c076e4`、metric catalog
  `sha256:d4a24d037aedc0b35f5ef51887f77adfc4abf1e27aa2723d72d95e48823ca43a`、policy
  `sha256:4a34349dbe2ef6e28da0167c3ba4a54d983cd6bada056716e4eafdf83cfa0068`、Registry
  `sha256:0ab769848bb7490b9be067ae601b76b8e557d068bf0c481aca00b835e8ca8b23`、corpus
  `sha256:c7fb2c8310f9f80009ae1332c5a3cc7f5f1418a701a1dca0c9cc1f637b32cd01`、manifest
  `sha256:b3039203d8c5b002ec2bb826b12f2a3d53aed92d219e730afbeb23611a3826e2`。
- AI-E two P1 經 bounded repair 後 AI-E/E2 PASS、focused `58 passed`。final E4 Context
  `sha256:6a1b7444b46e253edde3f7e3be3d35d6543a0a973dc4761cf0a1cfd3d5124b71`、task
  `sha256:931dc6a16de8d6d7613191afe0c6ce827f236f9ea051785b7319a4318255a9d0`，歷史結果
  `65 passed / 30 deselected / 0 failed or denied`；captures：efficiency
  `sha256:9c0c954f97b017bd4e6f6138e2cae592577fb99d1e6b31f7f24fe3b8e8541ef5`、registry
  `sha256:521510588f9e5e24425b9866b57b27d41c723f4f6eb21220cc291e8b5b9a120b`、validate
  `sha256:2ad6e2f28f23fafee9ba04348a0248cfcac6b0b466887baa8d9ed881111e8b95`、render
  `sha256:0756a626dc236cd75050233d122252edbe6f3de68f4ed797c8275f4ba5088227`、diff
  `sha256:7908a19fe343a87a7f3810a2160c32775b463ade550bf792dce0c3b6f824f02b`。
- initial E2 closed four P1（frozen diff `sha256:b1c32646aca3c4c01ab9d82ab2d23b99856cf6ac181dd3403b7f102e8526f724`）；
  initial E4 Context `sha256:09746b23f55a4dc3e96af4d2a97577e8540b619bcbc07978ed4fc1249a8d624d`
  的 `60 passed / 30 deselected / 0 fail or denied` 已被 final verdict superseded。residual：
  candidate measurements pending；historical next item W7，current dispatch 見 `TODO.md`，無 active implementation。

### Historical W1 evidence ledger（未重跑）

- initial probe `9c34aa4b28e30e495146cdb880ae889d3ea59b4f`，final repair
  `86ae98c5bcbb50f5d897811327c8c118b0ff166f`；admission `51e52ad9c349f21aa81a4d37e79dbfa0`；
  Context `sha256:1de49888093ee1808669cf363d8f01840a13319994b6eca45bc5106cbaa63698`、task
  `sha256:ec618559cfd5f84ffe7c763257a78f68c8146280799b9cf57025e77f5f990760`。
- initial E2 FAIL（2×P1）；final E2 PASS（P0/P1/P2=0、`24 passed`、capture
  `sha256:d6108aae9973524b35a4aac984f50a9a400a1e96d9366007b7b3dcaa2aed5be0`）；E4 combined
  `84 passed`（`sha256:4ed4015154a4408f5018bf026cab6089aab46519a04d53f0ef4499e244975e7e`）、probe
  `24 passed`（`sha256:71c9c8b074d56b33109f4aa1fa2f0c52b1a9deb0eebebef18440aa0fa91f24e8`）。standalone
  `py_compile` 是歷史 `SKIPPED/DENIED`；syntax/import 由已執行 pytest 重用，E1 另有 PASS。
- selected signal 不可得，故 `UNVERIFIED`／`COMPLETE_WITH_UNVERIFIED` 關閉；caller-provided
  replay snapshot 的 integrity 不證明 provenance/authenticity 或 actual file state。實作界線見
  [`docs/agents/2026-09-04--execution-surface-truth-probe.md`](docs/agents/2026-09-04--execution-surface-truth-probe.md)。

## 主交叉帳：每個舊項與 WF6 候選只出現一次

| 總帳工作 | 狀態／依賴 | 與 GPT-6 候選的對齊與有限出口 |
|---|---|---|
| W2-local existing control validation | CLOSED_LOCAL_SOURCE_ONLY；owner=PM | `1de695218e8fbf11a317a40396ad1713e940b930`：E2 PASS，`102 passed / 0 failed / 0 skipped / 0 errors`（26.29s，capture `sha256:7992b78f83698d9821d31422b19d2a9638bf09c99887513f71216c2d49e05965`）；AI-E PASS 僅 fixture（capture `sha256:124ae3f330ed4f54f5b93d1c4d86135d4eca0f6e78017e49a554c83800b36820`）。26k prompt fixture drift 已修（W9 後低於 cap），dynamic compiler boundary 保持 `final=false`／0 calls，production caps/source 不變。這僅驗證 existing local controls，不是 host/full W2；depth/wait 只為 structural ledger validation，`boundedParallel` source 已檢視但未由 selected 102 作 rolling-pool dynamic test，且沒有 actual usage/cost/time、host adoption、main/remote/runtime effect。|
| W2-host integration、no-delta、depth/wait | WAITING_EXTERNAL_HOST_INTEGRATION；owner=PM | 必須有實際 host preaction 的 spawn/wait/cancel/deadline integration，及非 caller 控制的證據；不得以 wrapper 替代。現有 depth/wait 只屬 structural ledger，非 native host enforcement；host unavailable。同 task-owned digest 必須 `BLOCKED_NO_DELTA` 且無 wakeup/retry；完成後仍 fresh-admit，超限可讀拒絕。|
| W3 Context micro-pack/去重 | CLOSED_CONTEXT_MICRO_PACK_SOURCE_ONLY；owner=PM | `1f87d68f9a0b8535e8fb46cba52858fa57fbb3d9`：`WF6-01` selector + W3-owned `WF6-04` exact loading；E2 PASS，E4 exact-head `206/0/1/0`（30.69s，capture `sha256:428920484ee8db4296d1c5e1d198cf660e18507866201cebf86688159d276fcd`）。Python/saved workflow parity 在 suite 內覆蓋；沒有 actual usage/time/cost savings、main/remote/adoption/runtime/model change。|
| W4 low-risk assurance lanes | WAITING_FRESH_ADMISSION；owner=PM | W2-local validated 與 W3 closed 已滿足；operator 已批准此 sequence，仍須 successor fresh-admit，不依賴 W2-host。保留 conditional R4；E2/E4、硬 owner、權限事實不可為省 token 移除。`WF6-07` 的 routing 實驗只可在固定模型下比較，不能預先改寫本項。|
| W5 entry/source binding | CLOSED_ENTRY_SOURCE_BINDING_SOURCE_ONLY；owner=PM | 未提交 subject 現於 pytest/provider 執行前拒絕、clean exact head 可驗證，且 fixed committed-tree security 保留。E2 PASS；E4 `120/0/0/0`，詳見上方。僅本地 source checkpoint，非完整 W5、非 main adopted、無下一項。|
| W5 capture reuse/host verifier residual | DEFERRED_TECHNICAL_DEPENDENCY；owner=PM | 依賴：W5 entry 已驗證及完整 source/diff/command/toolchain/environment 簽章與 TTL；合格才可 `REUSED`，否則 `EXECUTED`；production host verifier 未認證前兩者仍 trusted replay。`WF6-03` 只重用 inventory。|
| W6 immutable snapshot 平行化 | DEFERRED_TECHNICAL_DEPENDENCY；owner=PM | 依賴：W4、W5 reuse evidence 與 HITL；保留 snapshot-only deterministic E2/test fan-out、writer 串行與 ADR 0050/0052 的 HITL；不可由 A/B 繞過。|
| W7 三份 generated workflow drift | CLOSED_NARROW_SOURCE_CHECKPOINT；owner=PM | `e134…` 以既有 generator 校正三份 Registry block；E2 同 bytes 審查 PASS、E4 committed-head 測試 PASS，詳見上方 W7 evidence。無 runtime/adoption/performance claim；original broad generator redesign residual 仍待 PM gap-list assessment，不自動 re-design。|
| W8 locality/lazy S2 + context_store | DEFERRED_UNSTARTED；owner=PM | W3/W7 source seams 已 closed；仍須 fresh-admit measurement/independent parts 量測 retain/isolate/delete 與正確性，再決定 lazy/locality；不刪必要 Context。|
| W9 bootstrap profile | CLOSED_BOOTSTRAP_SOURCE_ONLY；human master=PM；PA→TW→R4→AI-E | reviewed source `bf6839c505d0083f9e1e5717b770347c597e69cf`; PA/R4/AI-E source-only PASS. Startup-only comparable bytes `37987→10494` (-72.4%); stable core `25266→9841`, planned `6509→2653`; docs `31870→16445`, planned `8172→4316`. Conditional manual illustrations: `15355` formal closure, `24939` delegated docs write+closure, `21138` readonly review+closure, `23981` runtime-claim review+closure; measurement capture `sha256:3bbd75d48e9a8f6388c1b6437a8f8b49c13b41a80af9ca904a0634637349dba0`. These exclude compiler artifact/other role adapters/evidence/code/tools/host telemetry: not actual tokens/cache/time/cost/quality outcomes. Residual: manual pointer compliance and no qualified host E2E run. No automatic next W; W2/W4 remain next admission work. |
| W10 KnowledgePilot off critical path | DEFERRED_OPERATOR_POLICY_DECISION；owner=Operator/PM | 依賴：明確批准的政策 amendment；保留 delta-gated、單一 Vault writer，未批准不得解耦。|
| W11 canary/adoption closure | DEFERRED_EXTERNAL_EVIDENCE_AND_OPERATOR_DECISION；owner=PM/Operator | 依賴：可比較的 qualified measurement/adoption evidence 與明確政策決策；原「W2…W10 全依賴」的移除只是 proposal，尚未生效。|
| WF6-02 priced economics | DEFERRED_EXTERNAL_EVIDENCE；owner=PM | 依賴：provider-attested price/usage、cache accounting、failed/reopened cohort 與 follow-up window；品質 gate 仍是 hard gate，不假稱 efficiency。|
| WF6-05 candidate profile | DEFERRED_TECHNICAL_DEPENDENCY；owner=PM | 依賴：W3/W9 scoped completion、既有 Registry/generated views、可機械 rollback 與官方 compatibility 驗證；不靜默成為 default。|
| WF6-06 fixed-DAG model A/B | DEFERRED_EXTERNAL_EVIDENCE；owner=PM/Operator | 依賴：WF6-02、relevant WF6-03 host/usage evidence、W3/W9 instruction work、qualified candidate/baseline、WF6-05 及外部付費授權；缺一即 WAITING、不得量測 run。固定 prompt/tools/DAG/corpus，事前綁定 call/time/spend cap、價格與外部付費授權、cold/warm protocol、failure accounting；結果只可為 adoption recommendation。|
| WF6-07 fixed-model routing A/B | DEFERRED_UNSTARTED / optional；owner=PM | 依賴：qualified fixed model（可保留 baseline）；模型固定後才比較 routing，且不阻擋 normal source cleanup。|

WF6 對齊摘要：`WF6-01 → W3`；`WF6-02 → W0 已修 cache 判定 + 新 economics increment`；
`WF6-03 → W1/W5 inventory`；`WF6-04 → W3 exact Context + W9 bootstrap`；
`WF6-05 → candidate profile`；`WF6-06 → fixed-DAG model A/B`；`WF6-07 → W4/W11 routing
comparison`。`WF6-03` 不另列為獨立調查：它是一次性 read-only evidence 更新，缺 provider
attestation 時以 `WAITING_EXTERNAL_LIMIT` 停止。模型 A/B 或 routing A/B 都不阻擋普通
source-overhead cleanup。

W3 evidence：E2 PASS；E4 exact-head `206 passed / 0 failed / 1 skipped / 0 errors` in 30.69s on
`1f87d68f9a0b8535e8fb46cba52858fa57fbb3d9`（capture
`sha256:428920484ee8db4296d1c5e1d198cf660e18507866201cebf86688159d276fcd`）；Darwin/Linux argv-cap
difference 是預期 skip。same-case docs `42909→31870` bytes（-25.7%）、planned `10933→8177`，core
`25266` bytes／`6522` planned 不變。direct E4 CLI check 為 allowlist denied；suite codegen parity 不是
獨立 CLI PASS。known unrelated global line cap 2060 與 `command_capture_v2` file hash 是 explicit residual，
不是 W3 regression 或 full-repo PASS。

## 目前物理 queue 與下一步

physical queue has zero workflow ACTIVE; W1 local collector、W2-local existing controls、W3、W5 entry 與 W9 bootstrap 均已 source-only 收口，但 W2-local 不是 host/full W2，W5 不是全 W5。
W3 只關閉 `WF6-01` 與 W3-owned `WF6-04` exact loading；W9 closes only W9-owned `WF6-04` bootstrap
work after PM→PA→TW→R4→AI-E source-only review, with no automatic successor. W2-host 保持 external waiting；下一 local admission 為 operator-approved sequence 的 W4 fresh-admit；roadmap 仍為 advisory：
並可獨立評估 `W8`，再到 `W5 reuse`、
`W6/W10 decisions`、最後 `W11 integration/adoption`。這只是規劃次序，沒有任何 auto-run
權限；未變的 hard policy 只能經明確批准 amendment 改變。每個後續 source unit 都需 literal
scope、重新編譯 Context、按風險產生 E1→E2→E4 與必要 owner；無 commit、push、merge 或 main
sync 授權。source complete、actually adopted、measured efficiency 仍是三種分開的結論。

## GPT-6 規劃來源與 supersession

此總帳整合了原始 handoff 的四份未提交草稿：planning base
`b411435a0063ddcfacfa390cc199b62e05966645`，位於
`/Users/ncyu/Projects/TradeBot/.worktrees/workflow-gpt6-plan-20260905`。原 four-path SHA-256
由本次 claim input 綁定：`TODO.md`
`9bf40f1f308a5b64609d55cfdf6fa45136bb69e407a69eee8120430f65652c75`、`docs/README.md`
`c8f7e64427a1456a04bf588a6891f8894df405ff0804b508dc7918cf48422dac`、
`docs/CLAUDE_CHANGELOG.md` `de9409fa81f57b72cb8a6e165cc77a020d85090f9011a7e36fe7751d6863bdb5`、
planning document `85038d79ad9beaa114ad3640428d4b5c7ab6f776a7fa0ec61cb7e4a5e1a49685`。原始草稿
是 immutable advisory；原規劃建議順序（從未授權自動執行）及舊 base startup/handoff 指令，
均由本總帳取代。背景與每項的禁止 shortcut 見
[`docs/agents/2026-09-05--gpt6-workflow-remediation-plan.md`](docs/agents/2026-09-05--gpt6-workflow-remediation-plan.md)。
