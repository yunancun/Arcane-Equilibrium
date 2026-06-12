# E1 報告 — superpowers token 用量分析腳本適配 · 2026-06-11

任務：把 obra/superpowers（MIT）`tests/claude-code/analyze-token-usage.py` 適配進本 repo，
成為 `helper_scripts/analyze_token_usage.py`（主會話／subagent 分桶 token 統計）。
**未 commit**（PM 統一批次；E1→E2→E4→QA→PM 鏈）。

## 任務摘要

- 源腳本：`/tmp/repo-eval/superpowers/tests/claude-code/analyze-token-usage.py`
  （MIT License, Copyright (c) 2025 Jesse Vincent；pin repo HEAD
  `6fd4507659784c351abbd2bc264c7162cfd386dc` 2026-05-29 評估快照，該檔最後變更
  commit `991e9d4de93b17ee08646a8115e3f9f88dad2208`）。
- 目標：本機 Claude Code 專案 transcript 目錄默認、兼容 `subagents/agent-*.jsonl`、
  全 session 合計 + 按 agent 聚合 top-N、中文 MODULE_NOTE/註釋、stdlib-only、
  唯讀 + fail-open、SCRIPT_INDEX 登記、AI-E memory 一條。
- 結果：全部完成；本機真實 session 實測跑通（證據見下）。

## 修改清單

| 檔 | 動作 | 說明 |
|---|---|---|
| `helper_scripts/analyze_token_usage.py` | 新增（~490 行） | 主交付物；MODULE_NOTE 含出處/MIT/pin + 三個行為偏差宣告 |
| `helper_scripts/SCRIPT_INDEX.md` | 編輯 | 頭部補充行 + 新 section（2026-06-11 Claude Code session token 用量分析）；並行 session 已動過此檔（line 6 新增 panel exporter），以當前內容為錨只 append 自己的條目，0 覆蓋他人改動 |
| `docs/CCAgentWorkSpace/AI-E/memory.md` | append | 工具存在 + 一行用法（檔尾新 section） |
| `docs/CCAgentWorkSpace/E1/memory.md` | append | 完成序列結論 + 教訓 |

## 關鍵設計（對源腳本的三個行為偏差，皆本機實測驅動）

源腳本的解析模型：逐行讀 session jsonl，`type=assistant` 的 `message.usage` 累加為主會話；
`type=user` 的 `toolUseResult.usage` 按 `agentId` 累加為 subagent。對本機真實 transcript
probe 後發現兩個會計假設不成立，一個計價口徑誤導：

1. **message.id 去重（last-wins）**：同一 assistant 訊息（多 content block 流式寫入）被寫成
   多行、每行重複攜帶 usage。實測主會話 202 個 assistant 行只有 61 個唯一 `message.id`
   （單 id 最多 11 行）→ 源腳本逐行累加超計 ~3.3x。且 agent transcript 內同 id 各行
   `output_tokens` 流式遞增（實測首行 out=3 → 末行 out=15081），末行才是終值
   → 按 `message.id` 去重、取最後出現的 usage。id 缺失時退該行 uuid（不跨行去重，
   誠實多計勝過漏計）。
2. **subagent 用量以 `subagents/agent-*.jsonl` 為權威**：實測 `toolUseResult.usage`
   只是該 subagent「最後一次 API call」的 usage（與該 agent 最終 message 末行
   usage 逐欄位吻合：in=131/out=15081/cr=175897），不是累計（真累計 in=18161/
   out=48156/cr=8492432）；且該 session 18 個 agent transcript 檔只有 13 個
   toolUseResult——被中斷的後台 agent 沒有 toolUseResult，只留 transcript 檔
   （與 2026-06-11 BG-subagent 根因記憶「唯一信號=agent-*.jsonl」一致）。
   toolUseResult 僅在 transcript 檔缺失時作下限 fallback（輸出行 `≈` 前綴 + health
   計數），結構上不可能與 transcript 雙重計數（seen_ids 互斥）。
3. **cache-aware 成本估算**：源腳本把 cache 全價計入 input（本機 cache_read 動輒
   數億 token，全價計會給出荒謬的 $ 數字）。改按標準乘數 cache write=1.25x /
   read=0.1x input 基準費率（`--input-rate/--output-rate` 可覆蓋），輸出明標
   「粗估非帳單」。

其他適配點：

- 默認 transcript 目錄 = `~/.claude/projects/<專案根絕對路徑編碼名>`，由
  `Path(__file__).resolve().parents[2]` + 非英數字元折 `-` 動態推導——本機解析結果
  與任務指定的默認目錄完全一致，同時滿足跨平台紅線（腳本與本報告皆 0 個
  `/Users/`、`/home/` 字面，grep 自證）。`--dir` 可覆蓋（任務要求的參數覆蓋）。
- session 定位：UUID / UUID 前綴（唯一命中才接受，歧義列出候選報錯）/ .jsonl 路徑；
  無參數時取 mtime 最近 `--recent` 個（默認 1）。
- agent 標籤：`agent-*.meta.json` 的 `agentType` + `description`（fail-open，缺檔退
  toolUseResult 的 agentType/prompt 首行，再退 unknown）。
- fail-open 邊界：壞 json 行 / 非 dict 行計 `bad_json`；assistant 行缺 message/usage 計
  `missing_usage`；非數值 token 欄位當 0；單 session 不可讀（OSError）跳過不毀整批；
  每 session 輸出 parse health 行。
- 唯讀保證：全檔只有 `open(path, "r")`，0 寫入路徑、0 狀態檔、0 subprocess、0 網路。
- CJK display-width 對齊（`unicodedata.east_asian_width`，stdlib）讓中文 description
  的表格仍對齊。

## 實測證據（本機真實 session，2026-06-11）

`python3 -m py_compile helper_scripts/analyze_token_usage.py` → PASS。

`python3 helper_scripts/analyze_token_usage.py --recent 2`（節錄；session 1 完整表 +
全 session 合計 + 聚合 top-10 頭部）：

```
Session ebe9d4c8-377d-4ccc-bc7d-e9b8757baa68
  mtime 2026-06-11 21:46 | subagents 18
bucket             label                                   calls      input     output   cache_write    cache_read   est_usd
main               主會話 (coordinator)                       61     41,730    141,035       545,576    13,303,713      8.28
a54b9fce15c8b8ad8  [E2] E2 全量對抗審查本批 diff              55      7,463     62,844       365,706     7,722,879      4.65
a4554a09346f4adf5  [general-purpose] 深挖 rtk-ai/rtk 並…      63     18,161     48,156       181,970     8,492,432      4.01
a7822279f08e2cbd1  [general-purpose] 深挖 last30days-sk…      29     19,843     24,099       318,447     3,551,631      2.68
add895e6f8efc182e  [E1] E1-A rtk pytest 補丁+PR               46      7,981     51,677       133,558     4,411,934      2.62
…（共 18 個 subagent，依估算成本降序）
session total                                                580    253,002    794,320     3,529,100    68,763,661     46.54
  parse health: bad_json=0 missing_usage=0 fallback_agents=0

Session 4f0c8da8-744f-4f13-b2b7-13045382f0e9
  mtime 2026-06-11 11:21 | subagents 24
session total                                              1,192    372,916  1,509,491     9,816,837   206,978,283    122.67
  parse health: bad_json=0 missing_usage=0 fallback_agents=0

全 session 合計（2 個 session）
  API calls:               1,772
  input tokens:            625,918
  output tokens:           2,303,811
  cache creation tokens:   13,345,937
  cache read tokens:       275,741,944
  total input (incl cache): 289,713,799
  total tokens:             292,017,610
  估算成本: $169.20（基準 $3/$15 per MTok；cache write 1.25x / read 0.1x；粗估非帳單）

按 agentType 聚合 top-10（依估算成本降序；main=主會話）
E1                 14 run(s)                                 672    125,763    759,516     2,736,885    98,979,448     51.73
main               2 run(s)                                  223    209,234    460,761     5,824,984    71,146,667     50.73
E2                 7 run(s)                                  304     50,074    351,640     1,383,334    39,058,673     22.33
E4                 4 run(s)                                  226     36,980    220,076       716,142    30,838,994     15.35
general-purpose    5 run(s)                                  157    107,403    151,783     1,060,285    18,417,505     12.10
…（PA/CC/BB/FA/QA；其餘 1 類用 --top 調整）
```

邊界實測（synthetic + 真實）：

- UUID 前綴 `ebe9d4c8` 唯一解析 OK；不存在 token → stderr 訊息 + exit 1。
- 壞 jsonl fixture（非 json 行 / json array 行 / assistant 缺 message / token 欄位
  "garbage"）→ `bad_json=2 missing_usage=1`，同 id 兩行 output 5→99 去重取 99
  （非 104），exit 0 不中斷。
- toolUseResult-only agent（無 transcript 檔）→ `≈[E9]` 行 + `fallback_agents=1`
  註記，無雙重計數。

## 治理對照

| 規範 | 對照 |
|---|---|
| 硬邊界 token（max_retries 等） | 0 觸碰（grep 0 命中） |
| 跨平台路徑紅線 | 腳本 0 個 `/Users/`、`/home/`、user 字面（grep 自證）；目錄動態推導 |
| 零第三方依賴 | 純 stdlib（json/argparse/pathlib/collections/unicodedata/re/datetime）；系統 python3 直跑 |
| 唯讀 / 不寫狀態 | 全檔僅 read-mode open；無寫入/網路/subprocess |
| fail-open + 計數報告 | bad_json / missing_usage / fallback_agents 三計數 + per-session health 行 |
| MODULE_NOTE / 中文註釋 | 檔頭 MODULE_NOTE（用途/主函數/依賴/硬邊界/出處 MIT pin/三偏差）；全檔中文註釋，英文僅技術詞 |
| SCRIPT_INDEX 登記 | 已加 section + 頭部補充行（只 append，未動並行 session 改動） |
| 檔案大小 | ~490 行 < 800 review 線 |
| migration / singleton / SQL | 不適用（0 DB、0 singleton、0 migration） |
| 不 commit | 遵守；工作樹留 4 檔改動待 E2→E4→PM |

## 不確定之處（標註給 E2/PM）

1. **base SHA 偏差**：派工說 main @ `39b7ff73`，實際 main HEAD=`15d3a593` 且
   `39b7ff73` 不在 main 祖先鏈（commit 物件存在，疑為他端/worktree 視角 SHA）。
   本任務交付物=1 新檔 + 3 檔 append，零衝突面，照常完成。
2. **成本估算口徑**（小決策）：源腳本 cache 全價計入會在本機 cache-heavy 用量下
   給出誤導性 $ 數字，改 cache-aware 乘數並明標粗估；若 E2 認為應保留源語意，
   改回是 4 行 delta。
3. **聚合排序鍵**（小決策）：session 內 subagent 與 top-N 均按估算成本降序
   （源腳本按 agent id 排序）；成本排序對「誰最燒錢」的分析目的更直接。
4. 輸出表格的 CJK 對齊用 east_asian_width，ambiguous-width 字元（如 `…`）按 1 計，
   個別終端字型下可能偏 1 格（純外觀）。

## Operator 下一步

- E2 對抗審查本批 4 檔 → E4（無 runtime/DB 面，建議輕量：py_compile + 真實
  session 一跑）→ PM 統一 commit。
- 可選 follow-up（不在本 scope）：`--json` 機器可讀輸出供 AI-E 自動取數；
  Linux 端（`~/BybitOpenClaw` 對應編碼目錄）跑一次驗跨機推導。
