#!/usr/bin/env bash
# SessionStart hook:向 session 注入 workflow 熱規則(additionalContext)。
# matcher 涵蓋 startup|clear|compact —— compact 是關鍵:長 session 壓縮後
# 紀律性上下文會被沖掉,本 hook 負責在壓縮後重注入。
# 注入內容為 PM 定稿(≤300 token):只改下方 printf 的逐字行,不要在腳本裡擴寫。
# fail-open:jq 缺失或 jq 失敗 → exit 0 無輸出(session 照常啟動,只是少了注入)。
# 轉義手法:printf 逐行(單引號字面量)餵 jq -Rs,由 jq 做 JSON 轉義;
# 不用 heredoc 是避開 bash 5.3+ heredoc 在 hook 環境的掛死案例
# (參考 superpowers session-start 註記,obra/superpowers#571)。

if ! command -v jq &>/dev/null; then
  exit 0
fi

out=$(printf '%s\n' \
  '<workflow-hot-rules>' \
  '1. 路由:動手前先查對口 skill(.claude/skills,描述=觸發條件;1% 可能適用即調用)與對口 agent(.claude/agents)。' \
  '2. 代碼改動強制鏈:E1→E2(對抗)→E4(回歸)→PM 驗收,不可跳過;meta-doc commit 用 git commit --only;派工前必 git fetch+查遠端 branch。' \
  '3. subagent 收尾四態:DONE/DONE_WITH_CONCERNS/NEEDS_CONTEXT/BLOCKED;BLOCKED 升級階梯=補 context→換模型→拆任務→升級 operator,禁同模型無變更裸重試;說「做不到」永遠可以,爛活比沒活糟。' \
  '4. rtk:Bash 輸出已被 hook 自動壓縮;exit≠0 而摘要看似全綠→必讀輸出尾 [full output:] tee log 或 rtk proxy 重跑;測試基準線記 passed/failed/skipped/error 四元組。' \
  '5. memory:寫前查重;topic 檔超配額先 MERGE 再新增;結論被推翻→寫「演變軌跡」節,不改寫原文。' \
  '6. BG agent 死活唯一信號=subagents/agent-*.jsonl mtime;SOP 正本=CLAUDE.md §八+agents/PM.md。' \
  '</workflow-hot-rules>' \
  | jq -Rs '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: (. | rtrimstr("\n"))}}' 2>/dev/null) || exit 0

# jq 異常產出空字串時同樣靜默透傳,絕不輸出半截 JSON。
[ -n "$out" ] || exit 0
printf '%s\n' "$out"
