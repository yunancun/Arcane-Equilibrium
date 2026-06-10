---
name: project-2026-06-10-agents-skills-revamp
description: 18 agents + 24 skills 全面修訂（字面化模型適配/context 節儉/hot-facts）；根目錄 .claude 實為 symlink→srv/.claude 單副本；變更未 commit 待落地 main
metadata: 
  node_type: memory
  type: project
  originSessionId: f24d69ff-8ed3-407e-9b02-642e02da37d9
---

2026-06-10 完成 `.claude/agents`(18) + `.claude/skills`(24) 全面修訂（Opus 4.5 時代 prompt → 字面化現代模型適配，向下兼容 Opus 4.8+，prompt 內零模型名）。42 檔 +740/−999（agents 1330→1252 行，skills 4536→4357 行，82 行外移 portfolio-construction `references/governance-extract.md`）。

**結構性事實（修正舊認知）**：根目錄 `.claude/agents`、`.claude/skills` 是 **symlink → `srv/.claude/`**（2026-04-25 建），物理單副本——「雙端同步」不存在，改根目錄即改 srv git 工作樹。[[project_18_agent_runtime_wired]]

**落地的統一機制**：
- 模板A 條件化啟動序列（profile/memory 必讀，CLAUDE/README/context-loading(實位 `srv/docs/agents/`)/TODO 按任務觸發）
- 執行通則：BLOCKED/CONFLICT 報告制（subagent 不暫停等人）+ 小決策自選註明 + 審計類全量輸出（finding 全列+severity+confidence，過濾交下游）
- Hot-facts：漂移型事實一律「以 SSOT 為準」指針；R4 新增 .claude 配置漂移巡檢職責（doc-cross-reference 有執行細則）
- Canonical 正本表：MIT-MF-1 grep=E3.md、檔案大小 800/2000=E5、SLA=performance-profiling、5 hard gates+AgentTool 分類=16-root、G6-04=doc-cross-reference、方法黑名單=math-model-audit、Purge/Embargo/CSCV=time-series-cv、交互確認等級=gui-style-guide、業務鏈拆法=e2e-integration-acceptance
- E4 測試基線改 self-updating：SSOT=E4 memory.md `BASELINE: YYYY-MM-DD passed=N failed=M` 行（舊 2555/17 作廢已記入）
- 邊界劃清：CC=憲法層(16 原則+9 不變量+hard gates)、DOC-XX gap=FA 獨有；PA 出派發計劃/PM 持執行權；PM 新增派工模板(含 NO-OP 退出)+並行派工協議
- 事實修正：crypto-microstructure funding 改 per-symbol upper/lowerFundingRate+fundingInterval（消除 2026-05-31 誤判根源寫法）；AI-E/token-cost 清型號改即時查價；LUNA=2022-05、2021-05-19=BTC 礦禁崩盤

**Why**: Fable 5/Opus 4.7+ 字面遵循指令、工具默認保守——舊 prompt 的幽靈 agent(FM)、唯讀 agent 被令寫入、「ask PM」求援、強制全讀序列從無害變成卡死/空轉源。

**How to apply**: 改 agent/skill 配置=改 srv git 樹，commit 走 `git -C srv commit --only`；新 agent prompt 遵循模板A/B/C+模板D 權威序+hot-facts 指針模式；勿在 prompt 寫死會漂移的數字。

**未完成移交**：①變更未 commit——srv 當時在 superseded branch `feature/l2-critic-lessons-tools`（HEAD 標勿取檔）+57 個他務未提交檔，需切 main 後 `commit --only` .claude 路徑+兩個 workspace memory.md+references 新檔；②最大殘留 context 槓桿=workspace memory 無壓實機制（E4 memory.md 5384 行、BB 1218 行，啟動序列必讀=每 spawn 固定大成本），建議「最近 N 條+archive」結構，未動。
