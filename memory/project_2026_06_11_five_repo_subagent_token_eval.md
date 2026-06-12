---
name: five-repo-subagent-token-eval
description: 2026-06-11 五 repo 評估+P0/P1 落地(rtk hook 全鏈/四態契約/25 descriptions/SessionStart 路由)— 裁決、落地紀錄、教訓;rtk PR#2399 待 CLA;P2 待拍
heat: 2
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

## 行動清單(2026-06-11 operator 拍板 P0+P1 即做)
- P0+P1 工作流項:**已落地**(見「落地紀錄」節)。
- 未落地殘項:analyze-token-usage.py 適配(小項擇機);BB 增量哨兵(前置=watchdog 告警通路仍 no-op);skill 觸發回歸套件(P2)。
- P2 待單獨拍板:runtime L2 PG 記憶層(5-7 session);mnemopi 試點;polymarket(綁 FinceptTerminal 裁決)。
- 不採用:裝 superpowers plugin、oh-my-pi 當 runner、snapcompact/TTSR、X cookie 爬鏈、自寫蒸餾器。

## 落地紀錄 (2026-06-11)
- 鏈:E1×4 並行(rtk patch/25 descriptions/hooks 接線/四態契約)→ E2 全量對抗(抓 1 HIGH:patch 放寬 bare-summary 啟發式,失敗測試 stdout 含「error in」會被誤捕成 summary→假 `No tests collected`)→ E1-A2 修(整行文法錨定 `is_bare_summary_line()`+last-match-wins,連 base 既有的 stdout 餌假全綠一併修)→ re-E2 PASS(殘留 1 病態自傷 LOW,exit 透傳兜底)→ E4 GREEN 9/9。主要產物入 main `4587f65f`(sibling session 提前打包 commit,E4 以 batch-paths diff=0 + post-commit 重驗轉移結論;同 commit 的 aeg_s3 22 檔歸 sibling 自鏈)。
- rtk:pin `6785a6c7`(上游默認 branch=**develop**)+ `tools/rtk/0001-fix-pytest-error-count.patch`;上游 PR https://github.com/rtk-ai/rtk/pull/2399(head `32561a0`);**owed:operator 簽 CLA** https://cla-assistant.io/rtk-ai/rtk?pullRequest=2399;Mac 裝 `~/.local/bin/rtk`(終驗 s3:`7 passed, 2 failed, 1 error`,error 計數在);上游 merge 後改回官方版並撤本地 patch 流程。
- hooks:`.claude/settings.json`(PreToolUse Bash→rtk-rewrite.sh,fail-open 三重守衛+不繞權限;SessionStart startup|clear|compact→session-start.sh 路由注入;env RTK_TELEMETRY_DISABLED=1),對新 session 生效;`.gitignore` 白名單 +3(settings.json/hooks)。
- 教訓:①`node --check` 對含 export 的 ESM 檔=無牙 no-op(壞語法也 exit 0),有牙檢法=剝 export+async wrapper(E4 報告有配方),涉 .js sign-off 一律用 wrapper;②`cmd | tail; echo $?` 捕的是 tail 的 exit——先存變量再管道;③多 session 下 sibling 可能把你的未 commit 工作提前打包——不 revert,E4 重驗轉移結論即可。

## P2 落地紀錄 (2026-06-12,commits `131bd560`/`9bc57548`/`d4994f6b`/`5e3820f3`)
四波 agent 鏈:設計波(PA L2 spec + BB 哨兵 advisory + QC polymarket discipline)→ 實作波(E1×4 並行,W 線被 API Overloaded 殺死續作棒收口)→ 審查波(E2-A 記憶層 / E2-B 哨兵+polymarket+小件 / E3 安全 / MIT schema ratify;退 2 MED+若干 LOW)→ 修復波(E1×2,中途被**月度限額**殺死,續作棒盤點「前棒源碼全做完、斷點=測試只寫宣告」收口)→ narrow re-E2 PASS 12/12 → E4 GREEN(Mac 全套 ×2 byte-identical + Linux scratch dry-run)。
- **L2 記憶層**(dormant,`OPENCLAW_L2_MEMORY_*` 全 0):V139 agent.agent_memory(append-only+supersede 軟刪鏈+DELETE REVOKE+tsvector('simple')+雙 GIN+embedding_meta);memory_distiller package(抽取+兩段式 dedup 雙 prompt 中文化,LocalLLMClient/Ollama qwen3.5:9b,fail-open-to-store 僅 dedup 段);cron daily 05:23 + seed CLI + manual V140 pgvector 緩裝 + healthcheck [88][89]。**Linux scratch 實證**:V138→V139 雙 apply 冪等、trading_admin `CREATE EXTENSION vector` 可裝、三語 word_similarity 0.3 真召回(en 0.732/zh 0.333/混 0.400)。借鑒 TencentDB-Agent-Memory(MIT),宿主框架同名「OpenClaw」巧合已清洗。
- **告警耐久 sink**:修 watchdog silent no-op(承 [[project_2026_06_05_engine_selfheal_bindhost_incident]] canary 無消費者);alert_sink.py sink-before-channel 落 alerts.jsonl + redactor(DSN/X-BAPI/key 遮蔽,sink+遠送雙路,E3 MED-1)+5MB 輪轉;自 engine_watchdog 抽出(2150→2100,pre-existing 2088 超頂,主檔拆分留 follow-up)。
- **BB 公告哨兵**(alert-only):GET /v5/announcements/index zero-credential;**去重鍵=正規化 url**(響應無 id 欄+列表序非 publishTime→禁 timestamp watermark,BB 實證);首輪 baseline 防洪;真煙測捕 TONUSDT 2026-06-15 delisting=P0。
- **polymarket 軸**(artifact-only):Gamma /events crypto 枚舉;QC 鐵則=賠率 corroborating-only 非主信號、零 relevance 截斷、append-only PIT、track-to-resolution 防 survivorship;進交易鏈前必走 quant 三段鏈。
- **小件**:analyze_token_usage.py(superpowers MIT,三會計修正);mnemopi 試點(FTS-only bank tradebot-dev,200 條 seed,零外連,.mcp.json 在 repo 外;MEMORY.md 仍 SSOT;兩週判準見 docs/references/2026-06-11--mnemopi_pilot_protocol.md)。
- **owed(operator-gated,代碼已三端同步 dormant 就緒)**:① rtk#2399 簽 CLA;② V138+V139 prod apply(prod sqlx head=137;連帶順序 V138→V139+checksum 預檢,MIT C-2);③ 三 cron 一鍵激活(installer APPLY-gated,未自行繞過——BB 哨兵會真告警/polymarket 真打外部 API/L2 依賴 V139,皆 outward-facing);④ bge-m3 pull(缺則 FTS-only 自動降級)。
- 教訓:① 月度限額殺 agent 與 desktop idle-kill 同類,續作棒「源碼盤點先於重做」省一輪;② installer APPLY-gate=runtime 行為改變的 operator 閘,PM 代按=繞過設計意圖,outward-facing 一律留 operator;③ engine_watchdog 2100 行 pre-existing 超頂,本批已盡量抽出。

關聯:[[project_2026_06_04_fincept_terminal_eval]]、[[project_2026_06_11_bg_subagent_idle_kill_rootcause]]、[[project_2026_06_05_engine_selfheal_bindhost_incident]]
