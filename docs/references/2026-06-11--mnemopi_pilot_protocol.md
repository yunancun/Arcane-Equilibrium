# mnemopi dev-memory 召回索引試點協議（Mac 開發機）

> 狀態：PILOT（2026-06-11 起兩週，至 2026-06-25 評估）
> Owner：PM（評估）/ operator（去留拍板）
> 範圍：僅 Mac 開發機本地。不進 Linux runtime、不碰 engine / PG / 交易面。

## 1. 定位與不變式

- **SSOT 不變**：`srv/memory/MEMORY.md` + topic 檔仍是記憶唯一權威。mnemopi 庫
  只是**衍生召回索引**（derived index），任何時刻可整個刪掉、從 SSOT 重建，
  不持有任何獨有狀態。
- **FTS-only**：`MNEMOPI_NO_EMBEDDINGS=1` 強制 SQLite FTS（BM25）召回；
  零 embedding、零模型下載、零網路（外連審計見 §5）。
- **獨立 bank**：`tradebot-dev`，落盤
  `~/.local/share/mnemopi-tradebot/banks/tradebot-dev/mnemopi.db`（repo 外）。
- **不進 git 的部分**：`<project-root>/.mcp.json`（Mac 本地 MCP 接線，位於 srv
  repo 之外）；數據目錄。進 git 的只有 seed 腳本、本協議、SCRIPT_INDEX 登記。

## 2. 構成

| 構件 | 位置 | 說明 |
|---|---|---|
| npm 包 | `@oh-my-pi/pi-mnemopi@15.11.2`（全域，`--ignore-scripts` 安裝） | MIT；CLI + MCP stdio server |
| 運行時 | bun 1.3.14（Homebrew bottled） | 包硬依賴 `bun:sqlite`，Node 無法替代 |
| seed 腳本 | `helper_scripts/mnemopi_seed_from_memory.py` | 遍歷 `srv/memory/*.md`（跳 archive/、README.md），topic 檔每檔一條 + MEMORY.md 索引逐 bullet 一條；重跑=整 bank 重建（冪等） |
| MCP 接線 | `<project-root>/.mcp.json`（非 srv 內） | `mnemopi mcp --bank tradebot-dev` stdio；env 鎖 FTS-only + LLM off |

種子規模（2026-06-11 首跑）：101 topic 條 + 99 索引 bullet 條 = **200 條**。

## 3. 試點判準（兩週）

- **指標**：PM 日常召回任務（「之前那個 X 事故的結論是什麼」類查詢）中，
  `mnemopi_recall` top-5 是否命中正確 topic 檔，對照基線=純 MEMORY.md 索引
  人工掃行。
- **記法**：PM 在試點期間遇到召回任務時雙軌查（先 mnemopi 後索引），粗記
  命中/未命中與省時感受；不要求正式計量基礎設施（試點成本紀律）。
- **加分項**：中文查詢命中率（FTS 對中文分詞弱是已知風險，bullet 內含英文
  技術詞可部分緩解）；劣於索引時直接記負分。

## 4. 退出條件與整刪程序

劣於或打平純 MEMORY.md 索引 → 整刪，零殘留：

```sh
npm rm -g @oh-my-pi/pi-mnemopi
rm -rf ~/.local/share/mnemopi-tradebot
# 刪 <project-root>/.mcp.json 內 "mnemopi" server 條目（或整檔，若無其他 server）
# 可選：brew uninstall bun（若無其他用途）
```

優於 → operator 拍板是否轉正（屆時才考慮 Linux 側、週期 re-seed cron 等，
試點期一律不做）。

## 5. 風險聲明與外連審計

- **本地 SQLite**：所有數據在本機單檔 SQLite；無 server、無端口監聽
  （stdio transport only）。
- **零外連（源碼審計 @15.11.2，安裝後複核與 /tmp 參考一致）**：包內全部
  3 個網路調用點及其關閉機制——
  1. `core/embeddings.ts` `embedApi`（預設 OpenRouter `/embeddings`）：
     `MNEMOPI_NO_EMBEDDINGS=1` 在 `embed()`/`embedQuery()` 入口短路，永不可達；
  2. `core/local-llm.ts` `callRemoteLlm`（`/chat/completions`）：
     `MNEMOPI_LLM_BASE_URL` 預設空字串→直接 return null，另設
     `MNEMOPI_LLM_ENABLED=0` + `MNEMOPI_HOST_LLM_ENABLED=0` 雙保險；
  3. `core/extraction/client.ts` `ExtractionClient`：全包只有測試構造，
     runtime 死碼。
  fastembed 的 HuggingFace 模型下載同被 (1) 的短路擋住。無 telemetry /
  analytics / sentry / posthog 命中。防禦縱深：seed 腳本與 .mcp.json env
  均不傳遞且主動剝除 `OPENROUTER_API_KEY` / `OPENAI_API_KEY` 等鑰匙。
  實證：seed 後 stats `vectors: 0, vec_type: "none"`。
- **供應鏈**：版本 pin 15.11.2 + `--ignore-scripts`（被跳過的 postinstall=
  `onnxruntime-node` 原生二進制下載；FTS-only 路徑在 darwin 對它是死碼，
  store/recall 實測完好）。升級必須重新過一次外連 grep 審計。
- **隱私邊界**：seed 內容=已入 git 的 memory 檔文本，無新增敏感面；但
  mnemopi 庫不在 repo 管控內，試點結束不轉正就刪。
- **SSOT 漂移風險**：mnemopi 內容是 seed 時點快照，會落後於 MEMORY.md 更新；
  緩解=召回結果永遠回讀 SSOT topic 檔確認（content 首行即帶
  `[memory/<file>]` 指針），且可隨時重跑 seed 腳本重建（週期性 re-seed，
  試點期手動）。

## 6. 已知限制（試點期接受）

- 包要求 bun 運行時（`bun:sqlite`）——多裝一個 61.6MB runtime 是本試點的
  真實成本之一，評估時計入。
- CLI 無 `--version` 子命令（上游設計），版本驗證用 `npm ls -g`。
- CLI `store`/`recall` 不帶 `--bank` 旗標，只有 MCP 工具支援 per-call bank；
  seed 腳本因此走 MCP stdio。
- FTS 對純中文長句查詢弱（無中文分詞）；查詢建議帶英文技術詞。
