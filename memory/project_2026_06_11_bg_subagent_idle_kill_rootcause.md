---
name: claude-desktop-bg-agent-idle-kill
description: 後台 subagent「卡死」根因三層：desktop 900s idle-pause 殺光 BG agent / PM 用錯活性信號誤殺 / 限額日 API 停頓 2-7min 假死
metadata: 
  node_type: memory
  type: project
  originSessionId: 6473ea7e-4cc7-4654-a5e5-3866546d2f80
---

2026-06-10 晚「派發 subagent 後台跑老是卡死」根因調查（證據全在 transcript+main.log，非推測）：

**層 1（主因）Desktop idle-pause 全滅**：Claude Desktop local-agent-mode `WarmLifecycle:session` idle timeout=900s。PM 派完 BG wave 結束 turn 後，session 視為 idle（**後台 subagent 跑動不算活動**），15 分鐘整 `Pausing session (idle_timeout)` → 所有 in-flight BG agent 同秒收 `[Request interrupted by user]` 死亡，不會 resume 自動續跑。實證兩波：22:41:41 pause→22:41:43 三 E1 全滅（E1-A 死前 7 秒剛 commit `eb035e4d`）；23:46:29 pause→23:46:31 另 session E1 死。resume 後 TaskList 殘留 "running"=殭屍，須 TaskStop 清掉。

**層 2 PM 誤殺（假活性偵測）**：PM 殺前用 task output file mtime 驗活性——該檔是 135B stub，**完成前永遠不更新**，必然誤判「零活動」→ TaskStop 誤殺兩個活 agent（75 秒前還在寫 transcript），PM 自己 3 分鐘後承認誤殺。worktree 檔案 mtime 同樣不可靠（閱讀/思考期不寫檔）。**唯一可靠活性信號 = `~/.claude/projects/<proj>/<sessionId>/subagents/agent-<id>.jsonl` 的 mtime/size 增長**。

**層 3 API 長停頓假死**：限額壓力日（06-10 當天撞 monthly spend limit、早上剛升級方案）單次 API 往返實測 5m38s，全日 60+ 次 >2min 停頓（retry/backoff 不寫 transcript，GUI 看是凍住）。另三種「即死型」非卡死（帶 API Error final text）：`monthly spend limit`、`Usage credits required for 1M context`（06-07 模型 [1m] 變體八連殺）、`socket connection closed`（06-08 過夜睡眠兩例 946min 殭屍）。

**Why**: 三層疊加成「老是卡死」感知：idle-pause 無聲全滅→看似永久卡住；API 停頓→活 agent 看似死→人工/PM 提前殺；誤殺循環浪費重派（重派/三派）。

**How to apply**: ①BG wave 飛行中 parent turn 不落地——派完立即逐個 `TaskOutput(block=true)` 等收（query 活著=idle 不計時，pause 不觸發），或 Monitor 駐留；**Monitor 要監「完成信號」（task output file 寫入完成內容）而非「假死信號」（worktree mtime）**。②TaskStop 前鐵則：先 stat subagents/agent-*.jsonl mtime，<5min 有寫=活著不殺；告警閾值 ≥30min。③resume 後先清殭屍 task。④派發勿用 [1m] 模型變體（除非有 credits）。⑤過夜 wave 先 `caffeinate` 防睡眠。承 [[project_2026_06_01_rust_python_boundary_simplification_audit]]（socket 斷後 agent 自標 completed 不可信）同族教訓。

**2026-06-11 落地（operator 拍板路線 B=留桌面）**：SOP shipped origin/main `558ded55`——CLAUDE.md §八 鐵則 + PM.md「後台 wave 防殺與降損」正本 + E1.md checkpoint 紀律 + `.claude/workflows/agent-wave.js`（journal 斷點續傳 wave runner，operator 核准常備）。Mac 本地四檔同內容未提交鏡像（symlink 即刻生效），main 收斂時自動歸零勿 revert；本地 main ahead-1 `88bddd03` 經 `git cherry` 確證=origin `175afa01` 等價補丁（殭屍指針），收斂=reset --hard origin/main 待 operator 批准。

**2026-06-11 追加驗證（治本/降損決策依據）**：①`SendMessage`（續作死 agent）在 desktop local-agent-mode **不存在**（ToolSearch select 精確查無）→ 被殺 agent 無法帶 context 復活，只能續作棒。②桌面 app config.json 等**無 idle timeout 設定旋鈕**，WarmLifecycle 900s 寫死 → 桌面內唯一解=turn 不落地；真治本=長 wave PM 移 tmux + 終端 CLI（無 WarmLifecycle；CLI 2.1.142 先 `claude update`）。③降損三件套：E1 dispatch 契約加「每里程碑 commit + 殘留進度可從 git log 重建」、續作棒（讀 worktree git log+diff 接力，禁重做）、wave 改 Workflow script 跑可 `resumeFromRunId` 重放（journal cache 只重跑未完成 agent）。
