# mnemopi dev-memory 召回索引試點落地 — 2026-06-11

任務：在 Mac 開發機落地 mnemopi（oh-my-pi SQLite memory engine，MIT）作 dev 側召回索引試點。
MEMORY.md（srv/memory/）保持 SSOT；mnemopi=可整刪重建的衍生索引；FTS-only 零 embedding 零網路。
未 commit（鏈 E1→E2→E4→QA→PM）。

## 任務摘要（五步全完成）

| 步驟 | 結果 |
|---|---|
| 1 供應鏈安裝 | `@oh-my-pi/pi-mnemopi@15.11.2` `--ignore-scripts` 全域裝成功；**需另裝 bun 1.3.14（Homebrew bottled）**，見偏差 D1 |
| 2 配置 | FTS-only（`MNEMOPI_NO_EMBEDDINGS=1`）+ bank `tradebot-dev`；數據 `~/.local/share/mnemopi-tradebot/`（repo 外） |
| 3 seed | **200 條**（101 topic 檔 + 99 MEMORY.md 索引 bullet），0 失敗；重跑冪等（整 bank 重建仍 200）|
| 4 MCP 接線 | `/Users/ncyu/Projects/TradeBot/.mcp.json`（專案根，srv repo 外=不進 git）；stdio 煙測 PASS |
| 5 協議檔 | `docs/references/2026-06-11--mnemopi_pilot_protocol.md`（srv 內，入 git）|

## 修改清單

**入 git（srv 內，待 E2）**：
- 新 `helper_scripts/mnemopi_seed_from_memory.py`（~270 行，stdlib-only，中文註釋+MODULE_NOTE）
- 改 `helper_scripts/SCRIPT_INDEX.md`（append 自己的 dated section + 最新補充行擴一句）
- 新 `docs/references/2026-06-11--mnemopi_pilot_protocol.md`
- 改 `docs/CCAgentWorkSpace/E1/memory.md`（append 1 條目）
- 新 本報告

**不入 git（Mac 本地）**：
- `/Users/ncyu/Projects/TradeBot/.mcp.json`（新建，先前不存在；位於 srv repo 之外）
- `~/.local/share/mnemopi-tradebot/banks/tradebot-dev/mnemopi.db`（數據落盤）
- 全域：bun 1.3.14（brew）、`@oh-my-pi/pi-mnemopi@15.11.2`（npm -g，109 packages）

**未動**：`srv/.claude/settings.json`（任務明令）、任何 production 代碼、PG、engine。

## 裝機證據

```
$ bun --version                       → 1.3.14
$ npm install -g @oh-my-pi/pi-mnemopi@15.11.2 --ignore-scripts
  added 109 packages in 15s
$ npm ls -g @oh-my-pi/pi-mnemopi      → @oh-my-pi/pi-mnemopi@15.11.2
$ mnemopi --version                   → "Unknown command: --version" exit=2（上游 CLI 無此子命令，非故障）
$ mnemopi help                        → 正常列出 store/recall/.../mcp 全命令面
```

registry integrity：`sha512-n/Ix2vJ8uh2qquFBkCjrqWMEJCY2lLSCJm42XwZ+UGbdvRy3wqdZCSuErAaFaDqBstdQEi4EByegG99Lfl3hfA==`

`--ignore-scripts` 跳過的 postinstall：`onnxruntime-node@1.24.3`（`node ./script/install`=原生 ORT 二進制下載）。
FTS-only 模式下它是死碼：embeddings.ts 只在 `process.platform === "win32"` import onnxruntime-node（darwin 被 Bun 靜態消除），fastembed 路徑被 `embeddingsDisabled()` 短路。store/recall 實測完好 → **不需放寬 --ignore-scripts**。

## 外連審計結果（源碼級，15.11.2 安裝後複核與 /tmp/repo-eval 15.11.0 參考一致）

全包恰 3 個網路調用點，全部 gate-off：

| # | 調用點 | 目標 | 關閉機制 |
|---|---|---|---|
| 1 | `core/embeddings.ts:268` `embedApi` | `{MNEMOPI_EMBEDDING_API_URL\|默認 openrouter.ai}/embeddings` | `MNEMOPI_NO_EMBEDDINGS=1` 在 `embed()`/`embedQuery()` 入口短路（embedApi 不可達）|
| 2 | `core/local-llm.ts:334` `callRemoteLlm` | `{MNEMOPI_LLM_BASE_URL}/chat/completions` | `MNEMOPI_LLM_BASE_URL` 默認空→`return null`；另設 `MNEMOPI_LLM_ENABLED=0`+`MNEMOPI_HOST_LLM_ENABLED=0` 雙保險 |
| 3 | `core/extraction/client.ts:103` `ExtractionClient` | openrouter `/chat/completions` | **全包僅 test 檔構造**（`grep "new ExtractionClient"` 只命中 test/）= runtime 死碼 |

- fastembed HuggingFace 模型下載：`getLocalModel()` 被 `embeddingsDisabled()` 短路 → 不觸發。
- telemetry/analytics/posthog/sentry：grep 0 命中。
- 防禦縱深：seed 腳本與 .mcp.json env 均主動剝除/不傳 `OPENROUTER_API_KEY`/`OPENAI_API_KEY`/`MNEMOPI_*_API_KEY` 等（gate 漂移也無鑰匙可用）。
- 實證：seed 後 `mnemopi_stats` 回 `episodic.vectors: 0, vec_type: "none"`（零向量落盤）。

## seed 計數

```
topic 檔條目: 101（103 *.md − MEMORY.md − README.md;跳 archive/）
MEMORY.md 索引 bullet 條目: 99
合計/已 seed: 200 / 200（0 失敗）
bank 'tradebot-dev' working memory total: 200
重跑驗證: 仍 200（整 bank 重建,非疊加 400）→ 冪等 PASS
```

召回品質抽測（3 個 PM 風格查詢全部 rank-1 命中正確 topic）：
`watchdog bind host engine down incident`→bindhost 事故、`sqlx migration checksum drift`→hash drift、`phantom position fill accounting race`→幽靈倉位修復。

## MCP 煙測輸出

以 .mcp.json 精確 command/args/env（`env -i` 純淨環境）echo 兩行 JSON-RPC：

```
→ {"jsonrpc":"2.0","id":1,"method":"initialize",...}
← {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"2024-11-05","serverInfo":{"name":"mnemopi","version":"3.1.2"},"capabilities":{"tools":{}}}}
→ {"jsonrpc":"2.0","id":2,"method":"tools/list"}
← tools: 23 | mnemopi_recall exposed: True | mnemopi_remember exposed: True
exit=0
```

另完成 tools/call 往返：`mnemopi_remember`→stored + `mnemopi_recall`→命中（score 0.528）+ `mnemopi_forget` 清除 smoke 條目。

## 協議檔路徑

`docs/references/2026-06-11--mnemopi_pilot_protocol.md` — 兩週試點（至 2026-06-25）；判準=PM 召回命中率 vs 純 MEMORY.md 索引；退出=整刪三步（`npm rm -g` + `rm -rf ~/.local/share/mnemopi-tradebot` + 刪 .mcp.json 條目）；風險聲明（本地 SQLite stdio-only/零外連/SSOT 不變/衍生品週期 re-seed）。

## 治理對照與偏差

- **D1（必要前置，非默默放寬）**：包硬依賴 bun 運行時——`bin` shebang `#!/usr/bin/env bun` + 全源 `import "bun:sqlite"`（Bun 內建模組，Node 26 type-stripping 也無法替代）+ `engines: {bun: ">=1.3.14"}`。無 bun=試點結構性無法進行 → 經 Homebrew 裝 bun 1.3.14（bottled，可審計通道，非 curl|bash）。與 `--ignore-scripts` 無關（該項驗證後不需放寬）。
- **D2（base SHA）**：任務述 repo @ `39b7ff73`，實際 main HEAD=`15d3a593`（`39b7ff73` 存在但已不可達於任何 branch=多 session 推進）。我的改動全為新增檔+兩個 append，無 base 衝突；以當前 HEAD 為準=最小安全解。
- **D3（seed 粒度小決策）**：MEMORY.md 不整檔一條（巨型索引文檔會 FTS 命中一切、永佔 top-k 污染召回），改逐 bullet；README.md 跳過（目錄結構說明非記憶內容）。topic 檔嚴格按任務「每檔一條」。
- **D4（--dry-run 默認方向）**：house 慣例「默認 dry-run」適用於 DB/DSN 寫入面；本腳本唯一寫入目標=repo 外可整刪的本地衍生 SQLite，故默認執行、`--dry-run` 可選。
- 跨平台路徑：腳本用 `Path(__file__).resolve().parents[1]`+`Path.home()`，0 硬編 user 路徑（grep 自證；.mcp.json 內絕對路徑屬 Mac-local 不入 git 配置，恰是機器特定值該在的地方）。
- 硬邊界 0 觸碰：無 migration、無 Rust/IPC、無 singleton、無交易面。
- docs/README.md 索引未加條目（多 session 髒樹 1000+ 行共享檔,留 PM 收口時併入;協議檔 placement/命名已符 references/ 慣例）。

## 不確定之處

1. FTS 對純中文長句查詢弱（無中文分詞）；抽測用英文技術詞查詢全中。試點判準已把中文查詢列為觀察軸。
2. mnemopi 庫內容=seed 時點快照,落後於 MEMORY.md 後續更新;緩解=content 首行帶 `[memory/<file>]` 指針回讀 SSOT + 手動重跑 seed(試點期不建 cron)。
3. `.mcp.json` 是否被本機 Claude Code 自動拾取尚待下次 session 實證(協議層已用精確 launch config 煙測 PASS)。

## Operator 下一步

1. 下次在專案根開 Claude Code session 時確認 mnemopi MCP server 被拾取（`/mcp`），用一次 `mnemopi_recall` 真實召回。
2. 兩週內（至 2026-06-25）按協議檔雙軌記命中率；劣於/打平→整刪三步。
3. （PM）E2 審查本批 5 個 srv 內檔案後依鏈 commit。
