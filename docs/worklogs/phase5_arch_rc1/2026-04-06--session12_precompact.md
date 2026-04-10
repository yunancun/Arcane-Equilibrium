# Session 12 Pre-Compact Snapshot

日期：2026-04-06
最後 commit：`4880c67`（已 push）
測試基準線：**474 engine + 413 core + 35 ml_training + 11 control_api smoke** · 0 failures

## Session 12 完成項（時間順序）

| # | 工作 | Commit | Δ Tests |
|---|---|---|---|
| 1 | PNL-1 qty=0 幽靈倉拒絕 | `ed01bf5` | engine +2 |
| 2 | PNL-2 H0Gate boot log + invariant | `f7a0b31` | — |
| 3 | PNL-3 啟動冷卻 60s（env） | `5890311` | engine +2 |
| 4 | PNL-4 regime 動態化 Hurst→ADX | `1c5caa3` | engine +3 |
| 5 | PNL-5 Cost Gate k 三檔 | `821bd9c` | engine +2 |
| 6 | PNL-6 trailing RR 下限 ≥ 1:2 | `c4425ce` | core +2 |
| 7 | PNL-7 dynamic_stop → RiskManagerConfig | `5a8653e` | — |
| 8 | PNL-7 dynamic_stop knobs → IPC | `4175bf2` | engine +1 |
| 9 | Session 12 cleanup（cost_gate / ADX / cooldown 全進 IPC） | `07e2f7c` | engine +1 |
| 10 | docs Session 12 PNL 收尾 | `64a4420` | — |
| 11 | DB-RUN-1 signals 節流 | `b945eff` | engine +6 |
| 12 | DB-RUN-2 decision_context piggyback | `509a70b` | engine +1 |
| 13 | DB-RUN-3 emit_close_fill 5 站點 | `358e2aa` | engine +2 |
| 14 | DB-RUN-4 feature history by-design 文檔 | `ec91d31` | — |
| 15 | DB-RUN-5 BlackSwanDetector in-memory wiring | `2161ec1` | — |
| 16 | DB-RUN-6 context_writer epoch 0 guard | `78291ff` | engine +1 |
| 17 | DB-RUN-7 signals chunk 1d / compress 2d（V006 + live） | `6608ab7` | — |
| 18 | docs DB-RUN 收尾 | `4880c67` | — |

**Push 範圍**：`ed01bf5..4880c67`（18 commits 全部 push）
**測試淨增**：engine 453 → **474**（+21）· core 411 → **413**（+2）

## 關鍵決策

1. **PNL-2 結論：no bug**，H0Gate `total_checks=0` 是 stale binary，加 boot log + tick/check invariant 防呆，下次操作員啟動時一眼確認
2. **PNL-5 Cost Gate k 寫死分檔（3.0/2.0/1.5）**：k 由 notional tier 決定，**不**該與 vol 關聯（vol 已在 LHS 的 ATR 裡）
3. **PNL-6 trailing RR 下限**：locked profit ≥ `dyn_stop × 0.5`，避免贏 0.2% 輸 3% 倒掛
4. **PNL-7 magic number 全部進 RiskManagerConfig + IPC**：13 個風控字段全 agent-tunable，patch_* validators 範圍校驗
5. **強制原則寫入 TODO/CLAUDE**：後續 Agent 風控修改必須對齊 RiskManagerConfig + IPC update_risk_config，禁 hot path 寫死
6. **DB-RUN-1 設計**：per (symbol, strategy) state-change + 60s heartbeat dedup，預期 -95%
7. **DB-RUN-2 設計**：piggyback DB-RUN-1，本 tick 至少 1 個 signal 被持久化才寫 context，預期 -99.6%
8. **DB-RUN-3 真實 bug**：5 個 paper 模式 close 站點全部丟棄 realized_pnl 且不發 Fill，trading.fills 永遠只有 open
9. **DB-RUN-4 結論：no bug, by design**：features 沒有 history 表，訓練歷史走 decision_context.indicators_snapshot JSONB
10. **DB-RUN-5 兩個死代碼**：BlackSwanDetector 已接 in-memory + log（DB write 待 schema），ExperimentLedger 留 Phase 4
11. **DB-RUN-6 兩段修法**：context_writer guard + 已執行 `DELETE FROM trading.decision_context_snapshots WHERE ts_ms = 0` (5 rows)
12. **DB-RUN-7 live + migration 同步**：chunk_time_interval 7d→1d, compress_after 14d→2d, ANALYZE 已跑

## Agent 可調 RiskManagerConfig 字段（13 個）

透過 IPC `update_risk_config` 單一通道更新。所有都有 `patch_*` validator 校驗。

| 字段 | 默認 | 範圍 | 用途 |
|---|---|---|---|
| `dynamic_stop_base_ratio` | 0.6 | 0.05–1.0 | base = hard_stop × this |
| `dynamic_stop_cap_ratio` | 0.8 | 0.1–1.0 | cap = hard_stop × this |
| `trailing_min_rr_ratio` | 0.5 | 0.0–2.0 | PNL-6 鎖定盈利下限 |
| `cost_gate_min_confidence` | 0.15 | 0.0–1.0 | 信心硬地板 |
| `cost_gate_k_base` | 1.5 | 0.5–10.0 | k base (paper) |
| `cost_gate_k_medium` | 2.0 | 0.5–20.0 | k tier $50–$200 |
| `cost_gate_k_small` | 3.0 | 0.5–50.0 | k tier <$50 |
| `adx_trending_threshold` | 25.0 | 0.0–100.0 | ADX trending 閾值 |
| `boot_cooldown_ms` | 60_000 | ≤ 1h | PNL-3 啟動冷卻 |
| `signals_heartbeat_ms` | 60_000 | ≤ 1h | DB-RUN-1 signal 心跳 |
| 既有 4 個（hard_stop_pct / max_leverage / max_drawdown_pct / p1_risk_pct） | — | — | RRC-1 |

## 留待 / 延後

| 項目 | 原因 |
|---|---|
| BlackSwan DB write path | 需新增 `risk.black_swan_events` schema + TradingMsg::BlackSwanAlert variant |
| ExperimentLedger 接入 | 等 Phase 4 Claude Teacher，自然整合點 |
| ADX threshold IPC validation review | 範圍 0.0–100.0 留意：0 = 任何 ADX 都算 trending（intentional） |
| paper_state.set_take_profit_pct 1000.0 死 clamp | handlers 已先 clamp 0.0–10.0，1000 是死代碼，低優先 |
| Phase 4 啟動 | Claude Teacher + LinUCB + News + DL-3 |
| R3 backlog | SEC-05/09/11/17/21 / FA GAP / Idle writers #5/#6 / WP 子項 |

## 文件變更摘要（Session 12）

**新建：**
- `docs/worklogs/2026-04-06--session12_precompact.md`（本文件）

**修改（按 commit 順序）：**
- `rust/openclaw_engine/src/intent_processor.rs`（PNL-1/5/7/cleanup：qty=0 reject + cost_gate_k method + patch_dynamic_stop_params + patch_cost_gate_params）
- `rust/openclaw_engine/src/event_consumer/mod.rs`（PNL-2：H0Gate boot log + invariant）
- `rust/openclaw_engine/src/tick_pipeline.rs`（PNL-3/4/cleanup/DB-RUN-1/2/3/5：boot cooldown + derive_regime + 13 個風控字段 + signals throttle + emit_close_fill + BlackSwanDetector）
- `rust/openclaw_core/src/risk/checks.rs`（PNL-6/7：min RR floor + 配置化 dyn_stop）
- `rust/openclaw_core/src/risk/config.rs`（PNL-7/cleanup：8 個新字段）
- `rust/openclaw_core/src/risk/stops.rs`（PNL-7：cap_ratio 參數）
- `rust/openclaw_engine/src/event_consumer/handlers.rs`（cleanup/DB-RUN-1：6 + 1 個新 IPC 字段轉發）
- `rust/openclaw_engine/src/event_consumer/tests.rs`（測試構造補全 + Session 12 IPC round-trip 測試）
- `rust/openclaw_engine/src/ipc_server.rs`（cleanup/DB-RUN-1：6 + 1 個 JSON-RPC 解析）
- `rust/openclaw_engine/src/paper_state.rs`（DB-RUN-3：close_position 返回 Option<f64>）
- `rust/openclaw_engine/src/database/feature_writer.rs`（DB-RUN-4 文檔）
- `rust/openclaw_engine/src/database/context_writer.rs`（DB-RUN-6 epoch 0 guard）
- `sql/migrations/V006__timescaledb_policies.sql`（DB-RUN-7：1d chunk + 2d compress）
- `TODO.md`（Session 12 PNL/DB-RUN 全部標完成 + agent 強制原則）
- `CLAUDE.md`（Session 12 摘要 + 一句話狀態）

## DB 現場狀態（live）

```
trading.signals: 19 GB / 52.6M rows / 1 chunk (2026-04-02..04-09)
  chunk_time_interval: 1 day  ✓ (was 7 days)
  compress_after: 2 days       ✓ (was 14 days)
  ANALYZE: ✓ executed

trading.decision_context_snapshots: epoch-0 rows = 0 ✓ (deleted 5)
```

新 binary 部署後：
- DB-RUN-1 throttle 啟動 → signals 寫入 ~352/s → ~per-state-change (~1-5/min)
- DB-RUN-2 throttle 啟動 → context 寫入 ~25/s → ~per-state-change
- DB-RUN-3 emit_close_fill 啟動 → trading.fills 開始有非零 realized_pnl
- 4/9 後新 chunk 開始輪換（每天 1 個），4/11 起最早 chunk 開始壓縮

## 下一步候選（按優先度）

第一個 `[ ]` 起點：**R3 backlog 或 Phase 4 啟動**。

候選分組：
1. **R3 backlog** — SEC/FA/Idle writers/WP 子項（多數架構性，散落小修）
2. **Phase 4 啟動** — Claude Teacher + LinUCB + News + DL-3（W13-15 規模）
3. **BlackSwan DB write 補完** — V008 schema + TradingMsg variant + writer handler（中等規模，DB-RUN-5 自然延續）
4. **ExperimentLedger 接入** — Phase 4 子項

## Compact 後接手指引

1. 讀 `TODO.md` 找下一個 `[ ]`（PNL/DB-RUN 全部完成，往下看 R3/Phase 4）
2. 確認當前 commit 是 `4880c67`：`git log --oneline -1`
3. 確認測試基準線：`cd rust && cargo test -p openclaw_engine 2>&1 | grep "test result"`（應 474）
4. 如需歷史細節：`docs/worklogs/2026-04-06--completed_todo_archive_l3_phases.md` + 本文件
5. **重要**：CLAUDE.md §三 + §十一 已同步，TODO.md 已標完成，無孤兒狀態
