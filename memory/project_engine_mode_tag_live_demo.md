---
name: engine_mode 標籤 endpoint-aware 升級（live_demo）
description: 2026-04-16 起 Live 管線 + LiveDemo endpoint 在 DB 寫入 "live_demo" 而非 "live"；歷史 Live 資料是 LiveDemo 誤標為 live，ML/edge filter 需意識此分水嶺
type: project
originSessionId: abb660ab-97c1-4057-990d-57e49d15432b
---
**事實**：2026-04-16 起，`TickPipeline::effective_engine_mode()` 取代 `pipeline_kind.db_mode()` 作為所有 DB 寫入（trading.fills / trading.intents / trading.verdicts / learning.decision_features / learning.decision_contexts / learning.decision_shadow_fills / observability.engine_events）的 engine_mode 標籤來源。規則：

| PipelineKind | BybitEnvironment | 標籤 |
|---|---|---|
| Paper | (None) | "paper" |
| Demo  | Demo | "demo" |
| Live  | Mainnet | "live"（真實資金）|
| Live  | LiveDemo (api-demo.bybit.com) | **"live_demo"** |
| Live  | Testnet | "live_testnet" |

**Why**：Live 管線長期指向 demo endpoint（`settings/secret_files/bybit/live/bybit_endpoint` = `demo`），舊的 `db_mode()` 只認 PipelineKind 三枚舉，把 LiveDemo 誤標為 `live`。後果：`learning.decision_features` 裡 43k 條「live」rows 其實是 LiveDemo；ML 訓練若不過濾，會把 Production profile（cost_gate_live STRICT）全拒的資料當真 live history 灌進 train set。

**How to apply**：
- 2026-04-16 之前寫入的 `engine_mode='live'` 行實際上 **都是 LiveDemo**，不是真 mainnet（因為 Live mainnet API key 根本沒 `OPENCLAW_ALLOW_MAINNET=1`，未真正上線過）。
- ML 訓練 / edge snapshot / audit 分析需區分：分水嶺 commit 是修 engine_mode 標籤的那次 commit（檢查 git log 找 "endpoint-aware engine_mode" 或 "effective_engine_mode"）。
- 寫新的 DB 查詢 / 訓練 filter 時用 `IN ('live','live_demo')` 覆蓋歷史 + 新資料；若要明確區分真 live 行為，需結合 ts_ms 和資料量分佈判斷（Live+Mainnet 實際發生前，`live_demo` 才是全部）。
- `PipelineKind::db_mode()` 仍保留 3-variant（"paper"/"demo"/"live"），用於：檔名（`strategy_params_{mode}.toml`、`{kind_tag}_state.json`）、IPC engine filter、mode_snapshots HashMap key、edge_estimates 目錄分區。不要混用。

**沒有回填歷史 rows**：保留歷史 mistagged 資料原貌，分析時在查詢層處理；避免對 43k 條行做 UPDATE 影響 audit 連續性。
