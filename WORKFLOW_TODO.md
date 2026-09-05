# 工作流與多代理優化總帳

## 地位、邊界與目前真相

這是人工閱讀的來源限定總帳，不是可派發佇列；物理 queue 只在根目錄
[`TODO.md`](TODO.md)。截至此總帳，`ACTIVE` 為空。任何後續工作都要由使用者明確
啟動、在乾淨 checkpoint 重新 admission；本文件不能授權自動續跑、模型／政策採用、
runtime、服務、PG、broker、下單、交易或獲利宣稱。

W0/W1 是本地來源 checkpoint，尚未併入 `main` 或採用：W0 final
`c90408613d6ce436abae619437a0bdc4acf4787f`，W1 final
`86ae98c5bcbb50f5d897811327c8c118b0ff166f`。`23f76fe5efe2b28943c36a4696887b00e05273f0`
只是本次對齊承接基線；本總帳及 companion docs 尚未提交，是本機文件 candidate，
不是 current reviewed source checkpoint。下列歷史測試結果不是本次重跑或效能改善。
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
| W2 host admission、no-delta、depth/wait | DEFERRED | 同 task-owned digest 必須 `BLOCKED_NO_DELTA` 且無 wakeup/retry；超限可讀拒絕。|
| W3 Context micro-pack/去重 | DEFERRED | 必要事實、精確 task/DAG/Context bytes、claim input/source pointer 無損且可 replay；`WF6-01` 是 selector 子切片，`WF6-04` 是 exact core/doc loading。不得 full-TODO fallback。|
| W4 low-risk assurance lanes | DEFERRED，需 W2/W3 | 保留 conditional R4；E2/E4、硬 owner、權限事實不可為省 token 移除。`WF6-07` 的 routing 實驗只可在固定模型下比較，不能預先改寫本項。|
| W5 capture reuse/host verifier | DEFERRED | 完整精確 source/diff/command/toolchain/environment 簽章與 TTL 合格才可 `REUSED`；缺少、無效或過期 reuse receipt 則 `EXECUTED`。host verifier 未認證前，兩者仍須 trusted replay。`WF6-03` 只重用 inventory。|
| W6 immutable snapshot 平行化 | DEFERRED，需 W4/W5 與 HITL | 保留 snapshot-only deterministic E2/test fan-out、writer 串行與 ADR 0050/0052 的 HITL；不可由 A/B 繞過。|
| W7 三份 generated workflow drift | WAITING_USER_START | 窄修 `.claude/workflows/agent-wave.js`、`openclaw-full-audit.js`、`profit-diagnosis.js` 的 Registry block 一致性。歷史 codegen 為 `1 failed, 6 passed`：嵌入 digest `9ce2…300ff` 與 current Registry `0ab7…8b23` 不同。廣泛 generator redesign 延後。|
| W8 locality/lazy S2 + context_store | DEFERRED，需 W3/W7 | 先量測 retain/isolate/delete 與正確性，再決定 lazy/locality；不刪必要 Context。|
| W9 bootstrap profile | DEFERRED，需 W3 | 窄任務最小熱路徑；高風險/runtime/權限入口仍載入必要 normative source，缺 Context 即 `NEEDS_CONTEXT`。|
| W10 KnowledgePilot off critical path | DEFERRED，HITL | 保留 delta-gated、單一 Vault writer；需使用者批准政策修訂才可解耦。|
| W11 canary/adoption closure | DEFERRED | 原「W2…W10 全依賴」可另提議收窄為已完成、可比較的必要切片；尚非生效政策，須使用者批准。|
| WF6-02 priced economics | DEFERRED | cache-read 作為唯一不利軸的問題已由 W0 KPI/診斷界線處理；新增部分僅是價格、cache accounting、failed/reopened cohort 與 follow-up window。品質 gate 仍是 hard gate。|
| WF6-05 candidate profile | DEFERRED，需 W3/W9 範圍完成 | 新候選需既有 Registry/generated views、可機械 rollback、官方 compatibility 驗證；不靜默成為 default。|
| WF6-06 fixed-DAG model A/B | DEFERRED | 須有 completed WF6-02 economics、relevant WF6-03 host/usage evidence，以及 applicable W3/W9 instruction work 後的 qualified candidate/baseline 與 WF6-05；缺任何項為 WAITING、不得量測 run。固定 prompt/tools/DAG/corpus，事前綁定 call/time/spend cap、價格與外部付費授權、cold/warm protocol、failure accounting。結果只可為 adoption recommendation。|
| WF6-07 fixed-model routing A/B | DEFERRED / optional | 須有 qualified fixed model（包括明確保留的 baseline，無需強制 migration）；與 W4/W11 有比較面重疊，但模型固定後才比較 routing，且不阻擋正常 source cleanup。|

WF6 對齊摘要：`WF6-01 → W3`；`WF6-02 → W0 已修 cache 判定 + 新 economics increment`；
`WF6-03 → W1/W5 inventory`；`WF6-04 → W3 exact Context + W9 bootstrap`；
`WF6-05 → candidate profile`；`WF6-06 → fixed-DAG model A/B`；`WF6-07 → W4/W11 routing
comparison`。`WF6-03` 不另列為獨立調查：它是一次性 read-only evidence 更新，缺 provider
attestation 時以 `WAITING_EXTERNAL_LIMIT` 停止。模型 A/B 或 routing A/B 都不阻擋普通
source-overhead cleanup。

## 目前物理 queue 與下一步

`TODO.md` 的 workflow lane 保持 `ACTIVE` empty。唯一近期候選是 W7，但狀態為
`WAITING_USER_START`：使用者在新 session 明確點名 W7，並從乾淨 checkpoint fresh-admit
後才可處理。完成 W7 不自動啟動 W2/W3 或任何 WF6 項。所有後續 source unit 均需
literal scope、重新編譯 Context、按風險產生 E1→E2→E4 與必要 owner；無 commit、push、
merge 或 main sync 授權。

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
