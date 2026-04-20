---
name: Paper 管線 2026-04-16 起預設關閉
description: 2026-04-16 起 Paper 管線 opt-in via OPENCLAW_ENABLE_PAPER=1；預設關閉以停止噪音污染；3E-ARCH 結構保留，僅 runtime spawn 被 gate
type: project
originSessionId: abb660ab-97c1-4057-990d-57e49d15432b
---
**事實**：2026-04-16 commit（PAPER-DISABLE-1）起，Paper 管線**預設不啟動**。環境變數 `OPENCLAW_ENABLE_PAPER=1` 才 spawn；否則：
1. `paper_health` 設 `PipelineHealth::Disabled = 3`
2. 寫入 `/tmp/openclaw/paper_state.json` + `pipeline_snapshot_paper.json` 含 `disabled: true` + `disabled_since_ms` 標記
3. Spawn 最小 drain task 消費 `paper_event_rx` + `paper_cmd_rx`（避免 scanner/phase4/IPC 的 sender clone 累積到 unbounded channel）
4. `paper_ready_tx.send(())` 立即通知 fan-out barrier，demo/live 不等 paper

**Why**：2026-04-14~16 兩天觀察：
- Paper balance $783 → **-$292**（137% drawdown，穿倉仍持續刷 intent，因無負餘額守門）
- Paper 5055 fills / -$1076 net（demo 同期 3295 / -$63）
- 同策略 grid_close_short：paper 745 fills/-$218 vs demo 28 fills/-$0.06（27x fills, 3600x 虧損差）
- 根因三層：(1) `risk_config_paper.toml` 刻意寬鬆（"maximum exploration"：position_size 50%、leverage 100x、h0_shadow_mode=true、min_confidence 0.05）; (2) `on_tick.rs:752` 走 `process_with_features` 合成 fill at `event.last_price`，零延遲/零 reject; (3) 無負餘額守門
- 結論：Agent 未上線（W22+ Strategist stub），paper 現只產噪音污染 DB + edge data；下游（edge / ML / audit）早已明確排除 paper 數據（見 `feedback_demo_over_paper_for_edge.md` + `project_edge_data_isolation.md`）

**How to apply**：
- 引擎重啟後預期：log 出現 `paper pipeline DISABLED`；`trading.fills WHERE engine_mode='paper'` 停止累積
- 如需重新啟用 paper（W22+ Agent 探索階段）：`export OPENCLAW_ENABLE_PAPER=1` + `restart_all.sh --rebuild`
- 3E-ARCH 結構保留 — `PipelineKind::Paper`、`risk_stores.paper`、`per_engine_predictors.paper`、`paper_positions_mirror`、`strategy_params_paper.toml`、`risk_config_paper.toml` 全部保留；只有 runtime spawn 被 gate
- 同時新增 **Gate 1.6 負餘額守門**（`intent_processor/router.rs`）：`balance() <= 0 && get_position(symbol).is_none() → reject "insufficient_balance"`。Paper 專用觸發（demo/live 由交易所保證金檢查兜底），反向平倉仍允許

**Python GUI 側**：`ipc_state_reader.get_paper_state()` 讀 `pipeline_snapshot_paper.json.paper_state`，現含 `disabled: true` flag；若要顯示 DISABLED banner 需 Python 側讀此 flag（尚未加 UI，留待後續優化；暫時 GUI 顯示 balance=0 + 0 positions 即代表禁用）

**不清理歷史 paper 資料**：保留 `/tmp/openclaw/paper_state.json` 原有 raw state 供事後 audit；啟動時直接覆寫為 DISABLED marker（若需回溯最後一次 paper 狀態需查 `pipeline_snapshot_paper.json` 的更早 backup 或 git log）
