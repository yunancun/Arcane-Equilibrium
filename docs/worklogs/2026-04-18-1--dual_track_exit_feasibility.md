# DUAL-TRACK-EXIT-1 Step 0 可行性 Sprint — 結果

**日期**：2026-04-18
**作用域**：DUAL-TRACK-EXIT-1 TODO §Step 0 四不確定驗證
**結論**：**NO-GO 直推 Phase 1 全量**；建議拆 Phase 1a/1b，1a 可立即啟動

---

## 摘要

| # | 不確定 | 判定 | 備註 |
|---|---|---|---|
| 1 | james_stein estimator 跑通 + 寫 `edge_estimates.json` | ✅ 綠（機制） | 104 cells, grand_mean −2214 bps；**P1-14 bind blocker 獨立** |
| 2 | `decision_features` 7 維 schema 對齊（≥5/7） | 🔴 紅 | 實際 1/7 直接對齊；設計是 entry-time snapshot 非 exit-time peak/giveback |
| 3 | per-strategy ≥10k 樣本（≥2 策略） | ✅ 綠 | ma_crossover live_demo 2.23M / grid_trading live_demo 16.5k；小樣本策略強制 P-only |
| 4 | tick-level 7d replay 可行 | 🟡 黃 | 無 tick 表；kline 1-min 粒度；**且 `market.klines` 自 04-16 21:08 停寫**（獨立 bug）→ fallback #6 事後歸因 audit |

---

## 詳細結果

### 不確定 1 ✅（機制）

**驗證**：
```
PG_HOST=127.0.0.1 PG_PORT=5432 PG_DB=trading_ai PG_USER=trading_admin PG_PASSWORD=... \
  .venv/bin/python3 -m program_code.ml_training.james_stein_estimator --days 14 --out /tmp/js_test_output.json
```

**輸出**：
- `_meta.n_cells = 104`
- `_meta.grand_mean_bps = -2213.98`
- `shrunk_bps` median = **−1969.7 bps**, min = −18989, max = **−1940**
- **所有 104 cell 全負**

**判定**：estimator CLI 跑通，寫檔 non-empty，schema 與現有 `settings/edge_estimates.json` 一致。**機制 ✅ 但不可 bind** — 若 bind cost_gate 則 100% fail-closed（P1-14 EDGE-ESTIMATE-BIND-BLOCKED-1 已預警）。

**意涵**：
- P1-7 B scheduler 可以自動化（每小時 cron），只寫檔
- Rust side 的 `set_edge_estimates()` hot-reload 管線可以接，但 **閾值要等 P1-10 + Phase 5 edge 翻正後再 bind**

### 不確定 2 🔴

**Target 7 dims**：`est_net_bps / peak_pnl_pct / atr_pct / giveback_atr_norm / time_since_peak_ms / price_roc_short / entry_age_secs`

**現有 `learning.decision_features.features_jsonb`（17 keys）**：
`funding_rate, adx_1h, concurrent_positions, orderbook_imbalance_top5, tod_sin, tod_cos, realized_vol_1h, same_direction_cnt, side, atr_pct, confluence_score, is_funding_settlement_window, persistence_elapsed_ms, spread_bps, bb_width_pct, basis_bps, notional_pct_of_bal`

**對齊對照**：
| 7 維 | decision_features 覆蓋 | 評 |
|---|---|---|
| est_net_bps | 近似可從 `label_net_edge_bps` derive（但是 label，非 feature）| ❌ 非 feature |
| peak_pnl_pct | 無 | ❌ |
| atr_pct | 直接 ✅ | ✅ |
| giveback_atr_norm | 無 | ❌ |
| time_since_peak_ms | 無 | ❌ |
| price_roc_short | 無 | ❌ |
| entry_age_secs | `persistence_elapsed_ms` 近似（entry→decision 時間，非 entry→now） | ⚠️ 部分 |

**直接對齊 1/7 / 部分 1/7 / 缺 5/7**。目標 ≥5/7 **不達標**。

**根因**：`learning.decision_features` 設計是 **entry-time decision snapshot**（開倉瞬間的市場狀態），而 Track P 物理層規則需要的是 **exit-time position trajectory**（自開倉以來 tick 軌跡的 peak / giveback / ROC）。兩者是不同維度的特徵。

**額外發現**：
- `trading.decision_outcomes` 表有 `max_favorable / max_adverse` 欄位（**理論上直接對應 peak_pnl_pct / giveback_atr_norm 的原料**），但 113,400 條全為 NULL — **dead column**（寫 context_id 不填值）
- `trading.fills.details` jsonb 24h 內 **100% NULL**（除 fa_phantom_1 contamination 標籤外）

**修復成本**：
1. **新建 `learning.exit_features` 表**（或擴展 `trading.fills` jsonb） — 存 Rust 端 `PaperPosition` 收盤時的 peak/giveback/ROC/time_since_peak 等
2. **Rust 端 `paper_state` 加 `peak_reached_ts_ms` + `max_favorable_pnl_pct` 欄位**（已在 TODO Phase 1 軌道 1 列出）
3. **Exit handler 寫入 `exit_features` row**（新管線）
4. **背填歷史**：不可能（peak 需要 tick 軌跡，kline 1-min 粒度不足）→ 只能從 Phase 1a 部署日起累積

### 不確定 3 ✅

**Query**：`SELECT strategy_name, engine_mode, COUNT(*) FROM learning.decision_features WHERE engine_mode IN ('demo','live_demo') GROUP BY 1,2 ORDER BY 3 DESC`

| strategy | mode | n | Track L 適用 |
|---|---|---:|---|
| ma_crossover | live_demo | **2,230,728** | ✅ 遠超 10k |
| grid_trading | live_demo | **16,526** | ✅ 超 10k |
| grid_trading | demo | 1,737 | ❌ P-only |
| ma_crossover | demo | 693 | ❌ P-only |
| bb_reversion | live_demo | 609 | ❌ P-only |
| funding_arb | demo | 60 | ❌ P-only |
| bb_breakout | — | **0** | ❌ P-only（QA 守衛 #1 首當其衝） |

**判定**：至少 2 個 live_demo 策略遠超 10k，**Track L 有訓練料**。小樣本策略強制 P-only 路線（與 DUAL-TRACK QA 守衛 #1 一致）。

**注意**：ma_crossover live_demo 2.23M 是天量（相較 grid 16.5k 的 135×）— 可能是單純 tick 級 evaluation 的 row 爆炸，而非真正的獨立決策點。Phase 1b 接通 exit_features 後要檢查 unique exit event 數，不只 row 數。

### 不確定 4 🟡

**現有數據**：
- `market.klines`：1-minute 粒度，**2026-04-05 14:00 ~ 2026-04-16 21:08**，134,774 rows
- `market.trade_agg_1m`：1-minute aggregated（buy_volume/sell_volume/vwap/large_*_count），**不是 tick**
- 無 `market.ticks` 表

**嚴重問題**：`market.klines` **MAX(ts) = 2026-04-16 21:08（1 day 23:48 陳舊）** — 停電事件後 kline 寫入管線**從未恢復**。這是獨立的 P1 bug，需單獨追蹤。

**對 Phase 1 影響**：
- `price_roc_short` 若 lookback = 100~500ms，kline 1-min 粒度完全不夠 → **不能做嚴格 tick replay**
- `ATR` 可從 1-min kline 計算（退而求其次），但需先修 kline 寫入管線
- 符合 DUAL-TRACK 風險退路 #6：**轉事後歸因 audit** — 用 fills entry/exit 價 + 1-min kline 還原粗粒度 peak-to-exit 軌跡，不做逐 tick replay

**判定**：黃 — 不完全綠，但有 fallback 路徑；嚴格 7d tick replay 不可能，粗粒度 audit 可以。

---

## Go/No-Go 建議

**原計畫（TODO §DUAL-TRACK）**：Step 0 四綠 → Phase 1 W23 Day 4-7 軌道 1 + 軌道 2 同步推進。
**實際狀態**：2/4 綠 + 1/4 黃 + 1/4 紅 → **全量 Phase 1 不可推進**。

### 推薦修正計畫：Phase 1 拆 1a / 1b

**Phase 1a（立即啟動，不需 7 維全對齊）**：
- 軌道 2 P1-7 A/B/C（完全不阻塞）
  - A：Rust 接 `trading.intents` 持久化
  - B：`james_stein_estimator` scheduler 啟用（每小時 cron，**只寫檔不 bind**）
  - C：`run_training_pipeline.py` 首跑 grid_trading（P-only 訓練不需 exit_features，可用 decision_features 的 17 維做 entry-decision 模型）
- 軌道 1 Track P 物理層**骨架**：`peak_reached_ts_ms` 欄位加到 `PaperPosition` + `price_tracker.compute_roc()` + Combine Layer 骨架（**Track L 缺失時 P-only**）
- 修 **`market.klines` 停寫管線**（Phase 1 的 ATR 依賴 kline 新鮮度）

**Phase 1b（需 Phase 1a 部署開始累積 exit_features 資料後）**：
- 新建 `learning.exit_features` 表
- Rust exit handler 寫入 peak/giveback/ROC/time_since_peak
- 累積 ≥1 週 exit_features 資料
- Phase 2 Track L shadow 才有料可訓

**Phase 2 （shadow）** 時程影響：
- 原計畫 W24 上 shadow — 改為 **W24 Phase 1a 穩定 + Phase 1b 啟動累積**；**W25 才能真正 shadow**（需 ≥1 週 exit_features）
- 實際延後 **1 週**

### 需立即追加的 TODO 項

1. **MARKET-KLINES-STALE-1**（P1-CRITICAL）：`market.klines` 自 2026-04-16 21:08 停寫，當前 1d 23h 陳舊；查寫入管線（可能是停電後未重啟的 connector service 或 engine kline publisher）。**Phase 1 ATR 依賴此**。
2. **EXIT-FEATURES-TABLE-1**（P1-HIGH）：設計 + 建 `learning.exit_features` 表 schema；Rust exit handler 寫入 7 維。**Phase 1b 前置**。
3. **DECISION-OUTCOMES-DEAD-1**（P2）：`trading.decision_outcomes` 113k 條 `max_favorable / max_adverse` 全 NULL，寫 context_id 不填值，管線斷；可能是 Phase 5 背填作業從未真正跑過。可沿用此表而非新建 exit_features，但需先補寫入邏輯。

---

## 下一步 owner 決策

- **建議先做**：Phase 1a 軌道 2 P1-7 A/B/C（與 7 維對齊完全正交，可立即推進，產出可驗證）
- **建議同時做**：MARKET-KLINES-STALE-1 RCA（~1 小時工作，不修 Phase 1 ATR 永遠算不準）
- **建議延後**：Phase 1a 軌道 1 Track P 物理層骨架（等 MARKET-KLINES-STALE-1 修完）
- **建議延後更遠**：Phase 1b exit_features 累積（先做 A/B/C，exit_features 表設計可並行，累積等 Phase 1a 部署）
