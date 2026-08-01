---
name: project_2026_08_01_framework_health_audit
description: 2026-08-01 框架健檢弧:主訴 session 久+用量飛耗→8 線調查 23/23 CONFIRMED→operator 裁決全項優化+三級模型分級→四 fw-* lane PR 落地;wave2 待辦清單
metadata:
  node_type: memory
  type: project
---

# 框架健檢 2026-08-01(23/23 CONFIRMED→全項裁決→四 lane 落地)

## 主訴與方法
operator 主訴「單一 session 用時很久+用量飛耗」,假說「工作流不再適配新模型(Opus 5)」。8 條並行調查線(usage/loop/agents/skills/memory/githist/governance/modelfit)+每線 top findings 獨立對抗核驗:**23/23 CONFIRMED、0 REFUTED**;全程 read-only。一句話裁決:**不是單點 bug,也不主要是模型的錯——是「為 Opus 4.x 世代設計的重治理 multi-agent 框架」×「Claude 5 世代模型行為(單請求更長/更愛派 subagent/thinking 不可關/Fable 5 兩倍單價)」×「規格明文要求的馬拉松 session」三者相乘**;loop 全是協議設計出的「合法結構性 loop」,非失控代碼迴圈。正本報告=健檢 scratchpad `FRAMEWORK_HEALTH_AUDIT_2026-08-01.md`(workflow run `wf_ab7f0feb-321`,16 agent 回傳全存 journal)。

## 關鍵量化(均經獨立複算)
- 月總 output 71.26M tokens,**65% 在 subagent**(1,100 個 transcript);月總 cache_read **10.86B tokens**=input 側 96.5%=最大單項。**63% 成本花在每 call 重讀 0.4-1M 巨型前綴**——cache 命中率 96.5% 良好,問題是 context 體積非 cache miss。
- AIML S2 三連 session effective input 6.22B tokens=**top6 肥 session 的 70.6%**,174 個 subagent,wall ~95-100h;單 session API 等值成本 $1,556-$2,754。
- 每 spawn 固定注入 ~80-84KB≈22-27k tokens(CLAUDE.md+MEMORY.md+skill 列表);六角色全鏈固定 context ≈168-195k tokens/任務(未含實際工作)。
- 模型分布:sonnet+haiku 合計僅 0.5%;fable-5(2× Opus 單價)跑日常開發 41/96 session;22 角色全 `model: inherit`、effort 全 high 硬編碼。
- thinking 只佔總成本 ~1%,不是槓桿;最大單 session(6.97M output/102 subagents)是 opus-4-8 跑的=模型非爆量主因,但 Claude 5 把每層放大(per-subagent 時長 ×3.1、訊息量 ×2.2-2.5)。

## 五個結構性 loop(全 CONFIRMED,皆協議設計非失控代碼)
1. **阻塞式輪詢**(時長主兇):單 session 62% wall 是 tool 等待(gh pr checks 540s 輪詢/TaskOutput block 600s timeout/tail 自身 session 目錄),每輪 poll 觸發一次 ~0.58M context call。
2. **馬拉松 session 是規格明文要求**:TODO.md「不得停止」條款+governance 明文 spend 無 repo 端 cap→60-126h session、median ~500k context、compact 0-3 次。
3. **review→fix→re-review 逐刀迴圈**:E2 hard edge 無迭代上限(政策層唯一無界迴圈);W5 receipt 再發射連鎖=任何新 schema 觸發全套 8 receipts+三腿投影+審查失效,實測 9 世代/6 輪審查/全 suite ≥10 次全量重跑。
4. **context artifact 全量重發**:「delta 輪」內容 +102 tokens 卻對 4 role 各重發 90,639 全量;單檔 86% 是共享段逐檔複製非引用;full_audit envelope 單 workflow 授權 4.416M planned tokens=部分飛耗是明文授權上限。
5. **「做完仍 BLOCKED」成新工作生成器**:S2 七 predicates 全 SOURCE_READY 後未移交 operator,反衍生 S2E 9 拆分包+LW1-LW5=18-19 個 PR 每個走完整 agent 鏈;BLOCKED_NO_DELTA 有一例實證誤判(殺 admission→接棒重付全額 intake)。

誠實負結果:無 error→原樣重試風暴;agent-wave bounded retry 安全有界;subagent 內部無相同-input 迴圈;agent 檔引用零 stale。

## 裁決與落地(2026-08-01)
operator 批准全部優化建議(P0 機制級:禁 blocking 輪詢/session 分段收攤/模型分級/review 批次收口/context artifact delta 化;P1 協議級:TODO 瘦身/W5 path 縮面/BLOCKED 凍結語義/full-audit 收斂/skill 砍半/治理機膨脹止血;P2 衛生:memory/GC/小修)+**三級模型分級**(T1 opus/high=PM,E1,E1a,E2,E3,CC,QC,MIT,PA;T2 opus/low=E4,FA,OPS,E5,QA,AI-E,BB,IB;T3 sonnet/medium=TW,R4,A3;政策正本 [[feedback_model_effort_tiering]])。四 lane 並行落地(branch,build 階段不 push):
- `agent/fw-protocol-slim-20260801`(P0 機制級+P1 協議級條款修訂)
- `agent/fw-model-tiering-20260801`(registry model/effort 欄+renderer 透傳)
- `agent/fw-skills-trim-20260801`(skill 教科書段壓縮/agent 檔整併/full-audit 數字修正)
- `agent/fw-memory-hygiene-20260801`(本檔所在 lane:P2-12 memory 衛生全項——治理頭廢 heat/三權威條更正/24 超限行壓縮/16 死 SHA 清除/鐵則退役+分級正本/topic 檔整併)

## wave2 待辦(裁決在案,未入本輪四 lane)
- WP-D context artifact delta 化(共享段 content-addressed 單發+引用;delta 輪只發真 delta;final 輪觀察型 role 改摘要)
- P1-7 W5-owned path 縮面(中央 schema 註冊移出或 receipt 綁 schema digest;全 suite 三方重跑改一方執行+兩方驗 capture digest)
- agent 檔 ceremony trim(共用 boilerplate 可省 ~40%/檔;**交易安全 gate 條款(CC/BB/IB/OPS/E3 refuses)逐字保留不可動**)
- 殭屍 session 清理+44 codex worktree(9.8GB)/58 本地 branch GC
- 附帶安全發現(另行處理軌,非本弧範疇):本地 settings allowlist 內嵌 PAT,已列撤銷/輪換待辦

## 教訓
- 條數 cap 不擋增長,只改變增長形狀(擠成行內膨脹)——cap 類治理必須配機械檢查(≤250 一行 python 可驗)。
- 治理規則不得引用死數據(heat 欄位從未回填卻是 MERGE 優先級依據)。
- 為舊世代模型可靠性補償而生的強制鏈/多重 adversarial 輪/超長 prescriptive skill,在新世代要重新计價:official migration 指引「separate verification steps…are likely redundant…this is a delete, not a rewrite」。
