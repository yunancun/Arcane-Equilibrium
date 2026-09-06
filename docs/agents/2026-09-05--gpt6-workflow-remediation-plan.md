# GPT-6 workflow remediation：背景與受限候選

日期：2026-09-05  
狀態：subordinate planning background；不是 queue、admission 或採用授權。

本文件已由 [`WORKFLOW_TODO.md`](../../WORKFLOW_TODO.md) 的總帳承接。它只保留 GPT-6
候選的問題定義與驗收限制；原 planning worktree 的 `WF6-01→…→WF6-07` 順序、舊 base
startup/handoff 指令均已 superseded，不能啟動任何工作。

## 來源與限制

原始規劃來自 source baseline `b411435a0063ddcfacfa390cc199b62e05966645`，原草稿在
`/Users/ncyu/Projects/TradeBot/.worktrees/workflow-gpt6-plan-20260905`，四份未提交檔案的
hash 已由總帳的 claim input 記錄。它是 source-only lead，不證明 host capability、provider
usage、成本、runtime 或節省。所有實作必須由使用者另行啟動，在乾淨 checkpoint fresh-admit。

## 仍有效的候選要求

- `WF6-01` 是 W3 的 current-work-state selector 子切片：必須選正確支持 section、保留 S2E
  EMPTY 與 one-ACTIVE semantics，拒絕 full-TODO fallback。
- `WF6-02` 的 cache-read 唯一不利判定已由 W0 的 KPI/diagnostic 分界取代；新增工作才是
  fully-priced durable-closure economics。必須定義 input/cache-write/cache-read 是否重複計算，
  綁價格幣別/版本與 tool charge，將 failed/reopened task 放入固定 follow-up cohort。缺 price、
  usage、成熟 cohort 或 accepted-closure denominator 時是 unavailable/waiting；quality/recall
  failure 永遠是 FAIL。
- `WF6-03` 只做 W1/W5 已知能力與 telemetry 的 read-only inventory；每項列 capability、
  producer、provenance、retention、owner 和能改變狀態的新證據。外部 fingerprint 無變化即有限
  停止，不以 unsupported adapter 或零值清帳。
- `WF6-04` 只在 W3/W9 的既定 scope 中澄清 routine authorized work 與 material
  decision/permission uncertainty，採 exact-section loading；不得刪 hard invariant、provenance 或
  必要 review。
- `WF6-05` 是既有 Registry/generated adapters 中的 evaluable candidate。保留 intended role
  tiers、Claude saved-workflow mapping、Luna memory separation，且初始 effective reasoning effort
  不變；baseline、candidate、fallback/rollback 與 requested/actual identity 要分開。compatibility
  與 model/effort 組合在當次官方文件及 host evidence 下驗證，不能假定付費/API 授權，也不能
  靜默改 default。
- `WF6-06` 是固定 DAG 的 model A/B。相同 prompt、tools、route、corpus、quality gate 及條件
  下，只變模型/effort mapping；事前登記 corpus、manifest、call/time/spend cap、價格 pin、
  cold/warm cache protocol、random/counterbalanced order、failure accounting 和 observation window。
  外部 provider calls 或 spending 需要明示授權。結果僅可為 `ADOPT_CANDIDATE`、
  `KEEP_BASELINE` 或 `INCONCLUSIVE`，前者也不是 default-switch authority。
- `WF6-07` 在固定合格模型下才可比較 routing；E2/E4、hard owners 與 full-audit recall 仍保留。
  零預期值或沒有 measured gain 即停止並保留 baseline。

WF6-06 只在 completed WF6-02 economics、relevant WF6-03 host/usage evidence、applicable
W3/W9 instruction work 後的 qualified candidate/baseline 與 WF6-05 都存在時才可量測；缺項為
`WAITING`。WF6-07 的 fixed model 可是明確保留的 baseline，無需強制 model migration，且這些
實驗不阻擋正常 source-overhead cleanup。

所有候選以 W0 的 Q0/Q1、P0/P1、reopen/rework/false-closure gate 為上位限制；模型 A/B 或
routing A/B 不能延後 W2 的 host wait/stop/depth、W4 conditional R4、W5 verifier、W6
snapshot parallel、W8 locality 或 W10 KnowledgePilot HITL。
