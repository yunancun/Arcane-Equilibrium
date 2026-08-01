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
  '1. 路由:跑 agent_governance.py route/context 綁 task facts/role/context,勿直讀 registry JSON;skill 按對口 surface 載入,禁 universal preload。' \
  '2. hybrid DAG:source implementation 必有獨立 E2→E4;authority/runtime/venue/quant-ML/E2E 依 facts 加 owner;skip 留 residual risk。' \
  '3. closure_packet_v1 分 work_status/gate_verdict/disposition;DONE+FAIL 合法;缺 evidence/coverage 不得 PASS;禁無變更裸重試。' \
  '4. rtk:Bash 輸出已被 hook 壓縮;exit≠0 而摘要似綠→讀 [full output:] tee log 或 rtk proxy 重跑;測試記 passed/failed/skipped/error 四元組。' \
  '5. persistence:reviewer 不寫 per-role report/memory;closure 後只 promote 新 durable lesson;effect 走 approved deterministic Adapter,OPS/IB/BB 唯讀。' \
  '6. 等待一律事件驅動:禁 blocking TaskOutput 長輪詢/watch 迴圈/tail 自身 transcript;改單次查詢+task-notification/排程喚醒;BG wave 用 journal/checkpoint,禁盲重跑。' \
  '7. context 軟上限:cache_read/turn>300k 或 wall>8h→落帳 checkpoint 換 session;Session closure=合法停點(governance §11)。' \
  '</workflow-hot-rules>' \
  | jq -Rs '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: (. | rtrimstr("\n"))}}' 2>/dev/null) || exit 0

# jq 異常產出空字串時同樣靜默透傳,絕不輸出半截 JSON。
[ -n "$out" ] || exit 0
printf '%s\n' "$out"
