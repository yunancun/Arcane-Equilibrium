# Session 11 — R1 收尾 + R2 批次

日期：2026-04-06
Commits：`8d5793b` → `957d174`（含 docs commit）

## 完成項

### R1 收尾
- **WP-MIT P1-6** drift_detector PG 接線（commit `8d5793b`）
  - `fetch_active_baselines` / `fetch_latest_features` / `DriftMonitorState`
  - feature_collector 新增 `FEATURE_NAMES[34]` 索引映射
  - PSI 滑動窗口計算 + burn-in 期 log-only
  - +3 tests · engine 428 → 431

### R2 批次
- **R2-1 PF-1 IPC update_strategy_params** — 已存在（Phase 3b pre-fixes 已實現），plan 文件 stale
- **R2-2 Idle writers #1/#2** producer aggregators（commit `2cf7ebf`）
  - 新模組 `database/aggregators.rs`：`TradeAggregator` + `ObAggregator`
  - 1 分鐘 UTC 對齊桶，跨分鐘自動 flush
  - `ws_client.parse_trade_item` 注入 side/qty 到 metadata
  - `ws_client.parse_orderbook_snapshot` 注入 L5 levels JSON 到 metadata
  - `TickPipeline.on_tick` 按 metadata["type"] 派發到 aggregator
  - +9 tests · engine 431 → 440
  - **#3 liquidations 未做**：WS topic 在 `29fc1ef` 已移除（毒連線），需手動驗證 V5 `allLiquidation` topic
- **R2-3 I-22 完整拆分**（commit `0519265`）
  - 提取 PaperSessionCommand match arm 到 `event_consumer/handlers.rs`
  - mod.rs 912 → **785**（< 800 警告線）
  - 0 行為變更，440 tests 全綠
- **R2-4 WP-E4 P1 tests** 5/6 項（commit `957d174`）
  - **T-P1-1** event_consumer handlers +5 tests（Pause/Resume/Reset/GetParams unknown/UpdateRiskConfig clamp）
  - **T-P1-5** strategies/mod.rs +5 tests（trait defaults / set_active / on_rejection / ParamRange serde / step=None）
  - **T-P1-6** database/fallback.rs +3 tests（open failure no-panic / counter unchanged on repeated failures / rotate 重置 per-file 計數）
  - **T-P1-2/3/4** Python smoke +11 tests（layer2_engine init / reset client / l1_triage fallback；ai_service socket path / handlers / dispatch unknown；ipc_client init / env socket / disconnected raises）
  - engine 440 → **453** · control_api +11 Py smoke

## 測試摘要
| 模組 | 之前 | 現在 | Δ |
|---|---|---|---|
| openclaw_engine | 428 | **453** | +25 |
| openclaw_core | 411 | 411 | 0 |
| ml_training | 35 | 35 | 0 |
| control_api smoke | 0 | **+11** | +11 |

全綠 0 failures。

## 延後 / 留待

- **Idle writer #3 liquidations**：需手動 Bybit V5 WS 驗證 `allLiquidation` topic 是否可用
- **WP-E4/T-P1-1 殘餘**：event_consumer 完整事件循環整合測試（需 fixture harness，獨立 sprint）
- **Idle writers #5/#6**：drift / quality（同樣是 producer 側未寫入）

## 關鍵決策

1. **PF-1 stale plan**：原 cryptic-doodling-eich.md 計劃文件中的 IPC strategy params 已在 Phase 3b pre-fixes 完成，從待辦移除而非重做
2. **Liquidations 不盲改 topic**：寧可延後也不在無 Bybit 驗證的情況下重新訂閱可能毒連線的 topic
3. **I-22 拆分策略**：選擇從 select! arm 提取 match body 而非重構主 loop state 為 struct，零行為變更、低風險
4. **Aggregator 設計**：用 PriceEvent.metadata 字符串夾帶 side/qty/L5 JSON，避免跨包修改 PriceEvent 結構

## Commit 鏈
```
8d5793b feat(WP-MIT P1-6): wire drift_detector to PG
2c0e2ff docs(session11): drift_detector closure
2cf7ebf feat(idle-writers): trade_agg_1m + ob_snapshots producers
0519265 refactor(I-22): mod.rs 912 → 785
957d174 test(WP-E4 P1): strategies/handlers/fallback/Py smoke
```
