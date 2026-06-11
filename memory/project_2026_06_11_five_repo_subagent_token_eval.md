---
name: five-repo-subagent-token-eval
description: 2026-06-11 五 repo 評估(rtk/superpowers/TencentDB-Agent-Memory/oh-my-pi/last30days)— 改善 subagent 運行+縮減 token;裁決與 P0-P2 行動清單;全部 MIT/Apache 無 AGPL
metadata: 
  node_type: memory
  type: project
  originSessionId: ebe9d4c8-377d-4ccc-bc7d-e9b8757baa68
---

# 五 repo 借用評估 (2026-06-11)

5 並行 agent 深挖 + rtk 真實實測(srv 唯讀)。License 全綠:rtk=Apache 2.0,其餘四個=MIT,無 AGPL。clones 留在 /tmp/repo-eval/(~176MB,可刪)。

## 裁決
1. **rtk-ai/rtk(61.2k★)= P0 採用**。CLI 輸出蒸餾代理,實測:cargo test 全綠 −97.6%、冷 cargo check(我們 236 crates)−86.5%、pytest 真實失敗場景 −74%、大 diff −98.8%;exit code 100% 透傳,git/psql/rustc 錯誤逐字節透傳;tee 機制失敗時全量落盤。**已證實缺陷:pytest error 計數消失**(`20 passed, 1 error`→`Pytest: 20 passed`,exit code 仍非零),根因 `src/cmds/python/pytest_cmd.rs` parse_summary_line 不解析 error,~12 行可修。方案:裝 + `rtk init -g`(PreToolUse hook 自動改寫,subagent 零感知)+ config `exclude_commands=["pytest"]` 直到 patch;前置=Mac 裝 ripgrep+jq(無 rg binary 時 rtk grep 輸出損壞,已實測);E4 補條款「exit≠0 而摘要全綠必查 tee log」。
2. **obra/superpowers(MIT)= 不裝 plugin,抄 4 機制**:①SessionStart hook(matcher 含 `compact`!)注入 ≤300 token 路由 meta-prompt → 我們 hooks 空白區;②skill description 只寫觸發條件禁摘要工作流(實證:摘要式 description 令模型跳過正文)→ 25 skill 改寫;③四態回報協議 DONE/DONE_WITH_CONCERNS/NEEDS_CONTEXT/BLOCKED + 升級階梯(換 context→換模型→拆→升級人類,禁同模型裸重試)+ 反假成功話術 → agent-wave/E1;④RED-GREEN skill 觸發測試法 + headless harness。另:tests/claude-code/analyze-token-usage.py 直接可抄(按主會話/subagent 分桶統計 token)。14 skill 中 9 個對我們重複或倒退(brainstorming HARD-GATE 與最少確認原則衝突)。
3. **TencentDB-Agent-Memory(5.3k★,MIT)= 借 prompt+schema 不借運行時**。落點 A(dev memory SOP,<1 session):topic 檔配額+強制 MERGE 三級預警、heat 計數、「演變軌跡/待確認矛盾」標準節。落點 B(runtime L2 PG 記憶層,5-7 session,dormant 起步):L1 抽取+兩段式 dedup 雙 prompt(MIT 全文可抄)、PG 移植(pgvector+tsvector+RRF)、召回注入協議(5s fail-open + cache 感知拆分:穩定塊→system 尾)。短板:無時間衰減/priority 不參與排序,須自加 recency。⚠️ 其宿主框架名「OpenClaw」與我們同名純屬巧合,搬代碼須清洗字樣。
4. **can1357/oh-my-pi(11.8k★,MIT)= 競品 runtime,70% 價值鎖死搬不動**(hashline/TTSR/snapcompact/compaction)。可借:mnemopi MCP memory server 可獨立試點(SQLite+FTS5,`mnemopi mcp`);yield 結構化收尾契約(全文落檔+inline ≤5000 字預覽);batch 共享 CONTEXT 段;outline-first 讀檔 SOP。**其 minimizer 移植自 rtk = rtk 正確性的獨立佐證**。⚠️ 其 Anthropic OAuth 模擬 Claude Code 客戶端身份+逆向計費 attestation = ToS 灰區,禁止拿我們訂閱跑它當廉價 subagent runner。
5. **mvanhorn/last30days-skill(39.4k★,MIT)= 不裝進鏈路,抄 4 模式**:①out-of-context 檢索蒸餾(過濾/去重/排序全在 Python 進程,模型只見 top-8);②store/watchlist 跨 run URL 去重+只在新發現時告警 → BB Bybit 公告追蹤藍圖(前置:watchdog 告警 silent no-op 須先修);③SKILL.md 對抗不遵從技法:LAW 前置(實證 line 1224 的規則=不存在)、具名災難案例、機器可驗自檢契約、`<untrusted_content>` 圍欄(BB 餵公告原文須加);④polymarket.py(786 行 MIT)— 接 FinceptTerminal 待決的 Polymarket 信號軸。⚠️ 默認探瀏覽器 cookie(opt-out),裝必須 FROM_BROWSER=off。

## 行動清單(待 operator 拍板)
- P0(~2-3 天):rtk 裝+hook(exclude pytest)→ pytest patch+上游 PR → 25 skill description 改寫 → SessionStart 路由 hook。
- P1:四態協議+共享 CONTEXT 進 agent-wave;memory SOP(配額/heat/演變軌跡);analyze-token-usage.py;BB 增量哨兵;spec-先於-質量審查順序。
- P2:runtime L2 PG 記憶層;mnemopi 試點;skill 觸發回歸套件;polymarket(等 FinceptTerminal 裁決)。
- 不採用:裝 superpowers plugin、oh-my-pi 當 runner、snapcompact/TTSR、X cookie 爬鏈、自寫蒸餾器。

關聯:[[project_2026_06_04_fincept_terminal_eval]]、[[project_2026_06_11_bg_subagent_idle_kill_rootcause]]
