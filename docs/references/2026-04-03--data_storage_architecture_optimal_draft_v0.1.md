# Plan: 最優數據存儲架構 — 從記帳到因果學習（完整版）

## Context

OpenClaw 的「學習」系統是純記帳式比對（只計數 win/loss，不分析 WHY，不修改策略參數）。6 類關鍵數據完全在記憶體中，重啟即永久丟失。

用戶目標：設計 **3-5 年長期可用** 的最優數據基礎設施，為 DL/ML + AI-as-Advisor 三層學習體系建立數據根基。追求最優解，無視工程難度。

硬件：AMD AI MAX 395 · 128 GB RAM · Ubuntu · NVMe SSD（假設 2 TB）

---

## 真實數據量（V1 嚴重低估）

加入 orderbook L2 + trade tape 後，50 symbols 的真實數據量：

| 數據流 | 頻率 | 每日 raw | 每年 raw | 壓縮比 | 每年壓縮 |
|--------|------|---------|---------|--------|---------|
| raw_ticks | 3/sec/sym | 1.0 GB | 365 GB | 10x | 36 GB |
| **orderbook L2** (25 levels) | 1/sec/sym | **2.5 GB** | 912 GB | 20x | 46 GB |
| **public trades** (trade tape) | ~50/sec/sym | **2.0 GB** | 730 GB | 10x | 73 GB |
| klines (all TF) | per close | 14 MB | 5 GB | 10x | 0.5 GB |
| indicators (16×7TF) | per close | 40 MB | 15 GB | 12x | 1.5 GB |
| 其他 (regimes/signals/contexts/business) | 事件驅動 | ~10 MB | 3.6 GB | 5x | 0.7 GB |
| **Total** | | **~5.6 GB/day** | **~2 TB/year** | | **~158 GB/year** |

### 5 年累計

| 時間 | PG 活躍數據 | Parquet 歸檔 | 總磁碟 | 2TB NVMe？ |
|------|-----------|-------------|--------|-----------|
| 1 年 | ~14 GB | ~158 GB | ~172 GB | ✅ 1.8 TB 剩 |
| 3 年 | ~14 GB | ~474 GB | ~488 GB | ✅ 1.5 TB 剩 |
| 5 年 | ~14 GB | ~790 GB | ~804 GB | ✅ 1.2 TB 剩 |

**核心：PG 活躍數據永遠保持 ~14 GB**（因為 retention policy 把過期數據刪除，刪除前已 export 到 Parquet）。

---

## 核心架構：三層數據分級

```
   ┌─────────────────────────────────────────────────────────────────┐
   │                    寫入路徑 (不阻塞交易管線)                      │
   │                                                                 │
   │  Trading Pipeline (tick → kline → indicator → signal → order)   │
   │       │ 同步，純記憶體，<1ms SLA                                 │
   │       │                                                         │
   │       └──► Lock-free Ring Buffer (fire-and-forget)              │
   │                │                                                │
   │                ▼                                                │
   │  Background Writer Thread (每 1s flush，失敗不阻塞)              │
   │       │ batch INSERT (100-1000 rows/batch)                      │
   │       │ synchronous_commit = OFF (3-5x 吞吐提升)                │
   │       ▼                                                         │
   │  ═══════════════════════════════════════════════════════════     │
   │                                                                 │
   │  HOT (PG 未壓縮)         WARM (PG 壓縮)          COLD (Parquet) │
   │  ┌──────────────┐        ┌──────────────┐        ┌───────────┐  │
   │  │ raw_ticks 2h │ ─2h─► │  2h-30d      │ ─30d─► │ Parquet   │  │
   │  │ orderbook 2h │ ─2h─► │  2h-14d      │ ─14d─► │ archive   │  │
   │  │ trades   2h  │ ─2h─► │  2h-30d      │ ─30d─► │           │  │
   │  │ klines   7d  │ ─7d─► │  7d-forever  │        │ 年度 copy │  │
   │  │ indicators 3d│ ─3d─► │  3d-90d      │ ─90d─► │           │  │
   │  │ contexts 3d  │ ─3d─► │  3d-forever  │        │ 年度 copy │  │
   │  │              │        │              │        │           │  │
   │  │  ~2 GB       │        │  ~12 GB      │        │ 158 GB/yr │  │
   │  └──────────────┘        └──────────────┘        └───────────┘  │
   │      實時查詢                 歷史分析                ML 訓練    │
   │      Grafana 儀表盤           回測                  DuckDB 引擎  │
   │      策略決策                 審計                  PyTorch      │
   │                                                                 │
   │  每日 ETL cron (02:00 UTC):                                     │
   │    PG → Parquet export (T-1 day)                                │
   │    outcome 回填 (決策上下文的事後結果)                            │
   │    數據質量檢查 → data_quality_events 表                         │
   └─────────────────────────────────────────────────────────────────┘
```

**為什麼 PG 活躍數據永遠 ~14 GB？**
- raw_ticks 30d compressed: ~3.6 GB
- orderbook 14d compressed: ~1.3 GB
- trades 30d compressed: ~7.3 GB
- 永久保留的小表 (klines/regimes/contexts/business): ~1.5 GB
- 90d 中等表 (indicators/signals): ~0.5 GB

壓縮後合計 ~14 GB。TimescaleDB retention policy 自動刪除過期 chunks。

---

## 五層 Schema + 完整表設計

### Schema 結構

```
market.*     — 市場數據 (hypertables)
trading.*    — 交易 + 決策數據
agent.*      — Agent 通信 + AI 調用
learning.*   — 學習系統 + RL + 漸進放權
features.*   — 特徵存儲 + 版本管理
quality.*    — 數據質量監控（新增）
```

### market.* — 市場數據表

**market.raw_ticks** (hypertable, 1h chunks)
```
ts, ts_ms, receive_ts_ms, symbol,
last_price, mark_price, index_price,
best_bid, best_ask, bid_size, ask_size,
volume_24h, turnover_24h, spread_bps
```
壓縮: 2h後 | 保留: 30d | segmentby: symbol | orderby: ts DESC

**market.orderbook_l2** (hypertable, 1h chunks) ← **V1 缺口 #1**
```
ts, ts_ms, symbol,
-- 25 levels bid: bid_price_1..25, bid_size_1..25
-- 25 levels ask: ask_price_1..25, ask_size_1..25
-- 衍生指標
bid_depth_total, ask_depth_total,
imbalance_ratio,        -- bid_depth / (bid_depth + ask_depth)
weighted_mid_price,     -- (bid1*ask_size1 + ask1*bid_size1) / (bid_size1+ask_size1)
spread_bps
```
壓縮: 2h後 (20x ratio!) | 保留: 14d | segmentby: symbol

**market.public_trades** (hypertable, 1h chunks) ← **V1 缺口 #2**
```
ts, ts_ms, symbol,
price, qty, side,       -- Buy/Sell (taker side)
is_block_trade          -- 大宗交易標記
```
壓縮: 2h後 | 保留: 30d | segmentby: symbol

**market.klines** (hypertable, 1d chunks)
```
ts, open_ts_ms, close_ts_ms, symbol, timeframe,
open, high, low, close, volume, turnover, tick_count
```
壓縮: 7d後 | 保留: ∞ | segmentby: symbol | UNIQUE(symbol, timeframe, ts)

連續聚合: 自動從 klines(1m) 衍生 5m/15m/1h/4h/1d

**market.indicators** (hypertable, 1d chunks)
```
ts, ts_ms, symbol, timeframe,
sma_20, sma_50, ema_12, ema_26,
macd, macd_signal, macd_histogram,
rsi_14, stoch_k, stoch_d,
bb_upper, bb_middle, bb_lower, bb_bandwidth, bb_percent_b,
atr_5, atr_5_pct, atr_14, atr_14_pct,
kama, kama_er, adx, plus_di, minus_di,
hurst, hurst_regime, ewma_vol, vol_regime,
volume_ratio, donchian_upper, donchian_lower, donchian_width
```
全 16 指標一行（避免 JSONB 解析開銷）| 壓縮: 3d後 | 保留: 90d

**market.regime_snapshots** / **market.regime_transitions** — 永久保留
**market.funding_rates** / **market.open_interest** / **market.long_short_ratio** — 永久保留
**market.liquidations** — 保留 1 年

### trading.* — 核心：Decision Context Snapshot

**trading.decision_context_snapshots** (hypertable, 1d chunks) — **架構核心**

在每個決策點（signal_generated / intent_created / risk_review / order_submitted / fill_occurred / position_closed）捕獲完整世界狀態：

```
-- 身份
ts, ts_ms, context_id, decision_type, symbol

-- 即時價格
last_price, mark_price, best_bid, best_ask, spread_bps

-- 5m 指標（扁平化，直接映射 ML feature vector，避免 JSONB 開銷）
ind_5m_sma_20, ind_5m_sma_50, ind_5m_ema_12, ind_5m_ema_26,
ind_5m_macd, ind_5m_macd_signal, ind_5m_macd_hist,
ind_5m_rsi, ind_5m_stoch_k, ind_5m_stoch_d,
ind_5m_bb_upper, ind_5m_bb_lower, ind_5m_bb_width, ind_5m_bb_pctb,
ind_5m_atr_5, ind_5m_atr_14, ind_5m_atr_14_pct,
ind_5m_kama, ind_5m_kama_er, ind_5m_adx, ind_5m_plus_di, ind_5m_minus_di,
ind_5m_hurst, ind_5m_ewma_vol, ind_5m_vol_ratio, ind_5m_donchian_w

-- 其他 TF (JSONB，不固定有數據)
indicators_1m JSONB, indicators_15m JSONB,
indicators_1h JSONB, indicators_4h JSONB, indicators_1d JSONB

-- Regime 跨 TF
regime_5m, regime_5m_conf, regime_15m, regime_15m_conf,
regime_1h, regime_1h_conf, regime_4h, regime_4h_conf

-- 近期序列 (Transformer/CNN 直接輸入)
recent_closes_5m REAL[60], recent_volumes_5m REAL[60],
recent_highs_5m REAL[60], recent_lows_5m REAL[60],
recent_closes_1h REAL[24]

-- 持倉狀態
position_side, position_qty, position_entry,
position_unrealized, position_holding_ms, position_cost_edge

-- 組合級
total_equity, available_margin, margin_usage_pct,
drawdown_pct, open_position_count, daily_pnl_pct

-- 微觀結構
funding_rate, open_interest, oi_change_1h_pct,
long_short_ratio, liq_volume_1h

-- Orderbook 微觀 (V1 缺口 #1)
ob_imbalance_ratio, ob_bid_depth, ob_ask_depth,
ob_weighted_mid, ob_spread_bps

-- 決策本身
decision_payload JSONB

-- ★★★ 事後結果（cron 回填，ML 監督學習標籤）
outcome_price_1m, outcome_price_5m, outcome_price_15m,
outcome_price_1h, outcome_price_4h, outcome_price_24h,
outcome_return_1m, outcome_return_5m, outcome_return_15m,
outcome_return_1h, outcome_return_4h, outcome_return_24h,
outcome_max_favorable,    -- 24h 內最大有利移動
outcome_max_adverse,      -- 24h 內最大不利移動
outcome_regime_1h, outcome_vol_1h,
outcome_backfilled BOOLEAN DEFAULT FALSE
```

因果分析示例：
```sql
-- "為什麼 MA Crossover 有時贏有時輸？"
SELECT
    CASE WHEN outcome_return_1h > 0 THEN 'win' ELSE 'loss' END,
    avg(ind_5m_adx), avg(ind_5m_rsi), avg(ob_imbalance_ratio),
    mode() WITHIN GROUP (ORDER BY regime_1h)
FROM trading.decision_context_snapshots
WHERE decision_type = 'signal_generated'
  AND decision_payload->>'source' = 'MACrossoverStrategy'
GROUP BY 1;
-- → "ADX>25 時勝率 71%，ADX<20 時只有 32%"
```

其他 trading.* 表：
- **signals** / **intents** / **risk_verdicts** — 含 context_id FK
- **orders** + **order_state_changes** — 事件溯源
- **fills** / **position_snapshots**

### agent.* — Agent 通信

- **messages** — 所有 inter-agent 消息（當前完全記憶體丟失）
- **ai_invocations** — prompt_hash + response_summary + cost + context_id
- **state_changes** — agent 狀態轉換日誌

### learning.* — 學習 + RL + 漸進放權

**learning.rl_transitions** (hypertable, 7d chunks)
```
ts, episode_id, step_index,
context_id,                    -- FK to decision_context
state_vector REAL[~120],       -- 扁平化特徵向量，直接載入 PyTorch
action INTEGER,                -- 7 discrete actions
immediate_reward, shaped_reward,
next_context_id, next_state_vector REAL[],
done BOOLEAN
```

**learning.promotion_pipeline** — 四階段漸進放權
```
pipeline_id, strategy_name, model_name, model_version,
current_stage,  -- LEARNING → PAPER_SHADOW → DEMO_ACTIVE → LIVE_PENDING → LIVE_ACTIVE

-- Stage 1 Paper 指標
paper_start_ts, paper_trades, paper_win_rate,
paper_net_pnl_pct, paper_max_drawdown_pct, paper_sharpe,

-- Stage 2 Demo 指標
demo_start_ts, demo_trades, demo_win_rate,
demo_net_pnl_pct, demo_max_drawdown_pct, demo_sharpe,
demo_avg_slippage_bps, demo_api_reliability,

-- Stage 3 Live 審批
evaluation_report JSONB,       -- Claude AI 生成的完整報告
operator_decision,             -- APPROVED / REJECTED / EXTEND
approved_capital_pct, approved_max_leverage
```

畢業條件：
- Paper → Demo: 運行 ≥14d, 交易 ≥100, PnL>0, MaxDD<10%, Sharpe>0.5
- Demo → Live Pending: 運行 ≥21d, 交易 ≥200, PnL>0, MaxDD<8%, Sharpe>0.8
- Live Pending → Live: **必須** Claude AI 評估報告 + Operator 手動批准

**learning.ml_parameter_suggestions** — ML 模型 → 策略參數建議 → 治理審批
**learning.model_registry** — 模型版本管理 ← **V1 缺口 #3**
```
model_id, model_name, version, created_ts,
architecture,              -- 'transformer_regime_v1' / 'ppo_trading_v2'
training_data_range,       -- [start_date, end_date]
feature_version,           -- FK to features.versions
hyperparams JSONB,
metrics JSONB,             -- {val_sharpe, val_accuracy, test_sharpe, ...}
artifact_path,             -- /data/openclaw/models/{model_id}/
is_active BOOLEAN,
promoted_to_stage TEXT     -- NULL / PAPER / DEMO / LIVE
```

### quality.* — 數據質量監控 ← **V1 缺口 #4**

**quality.data_quality_events** (hypertable, 1d chunks)
```
ts, check_type, symbol, timeframe,
severity,        -- INFO / WARNING / CRITICAL
description,
details JSONB
```

自動檢測：
- **Gap**: 某 symbol 超過 5 分鐘沒有 tick（預期 <3s）
- **Anomaly**: 價格跳變 >5%（可能是錯誤數據）
- **Completeness**: 某 symbol 某天 1m bar 不足 1440（預期 1440）
- **Latency**: WS receive_ts - exchange_ts > 500ms
- **Stale**: indicator cache 超過 10 分鐘未更新

### features.* — 特徵存儲

**features.online_latest** — UPSERT，每次 kline close 更新
```
symbol, timeframe, updated_ts_ms,
feature_vector REAL[~120],     -- 與 RL state_vector 相同定義
feature_version TEXT
```

**features.versions** — 特徵版本管理
```
version, created_ts, description,
indicator_config JSONB,         -- 所有 16 指標的精確參數
normalization_params JSONB,     -- per-feature mean/std/min/max
is_active BOOLEAN
```

---

## PostgreSQL 深度調優（128 GB 統一記憶體 — LLM 優先）

### ★★ 記憶體分配（核心約束：本地 LLM 是大戶）

```
128 GB 統一記憶體分配
═════════════════════════════════════════════════
Ollama / LMStudio (本地推理)        40-70 GB  ← 最大消費者
  Qwen 27B FP16:                    ~54 GB
  Qwen 9B FP16:                     ~18 GB
  多模型並行:                       40-70 GB
─────────────────────────────────────────────────
PyTorch 訓練/推理                   10-20 GB
─────────────────────────────────────────────────
PG shared_buffers                   ★ 8 GB ★  ← 克制！不搶 LLM 記憶體
OS page cache (自動管理)             15-40 GB  ← 隨 LLM 用量浮動
PG effective_cache_size              50 GB     ← 告訴 planner cache 有多少
─────────────────────────────────────────────────
Python + Rust + Redis + Qdrant       ~5 GB
OS + kernel                          ~3 GB
═════════════════════════════════════════════════

為什麼 PG 8GB 就夠？
- PG 活躍數據只有 ~14 GB（retention 控制）
- 8GB shared_buffers 覆蓋最熱的數據（近 2h 未壓縮 chunks）
- 剩餘靠 OS page cache（Linux 會自動用空閒 RAM cache 磁碟）
- 壓縮 chunks 的讀取本來就走 OS page cache（不走 shared_buffers）
- NVMe SSD 隨機讀延遲 <100μs，cache miss 影響極小

動態平衡：
- LLM 不運行時 → OS page cache 自動擴張到 60+ GB → PG 受益
- LLM 運行時 → OS page cache 收縮 → PG 只用 8GB shared_buffers
- Linux 記憶體管理會自動處理這個平衡，無需手動介入
```

### postgresql.conf 關鍵配置

```ini
# Memory (LLM-aware allocation)
shared_buffers = '8GB'               # ★ 克制！不搶 LLM 的記憶體
effective_cache_size = '50GB'        # shared_buffers + 預期 OS cache
work_mem = '128MB'                   # 比 LLM-unaware 方案小，避免爆記憶體
maintenance_work_mem = '1GB'         # VACUUM, 壓縮 (LLM 運行時降級)
huge_pages = 'try'

# WAL (寫入密集型優化)
wal_level = 'replica'
max_wal_size = '8GB'                 # 比 16GB 保守（LLM 記憶體壓力）
wal_compression = 'zstd'             # PG15+ ZSTD 壓縮 WAL，省 40%
synchronous_commit = 'off'           # ★★ 3-5x 寫入吞吐提升
checkpoint_timeout = '15min'         # 比 30min 更頻繁（避免大 checkpoint 衝擊）
checkpoint_completion_target = 0.9

# NVMe SSD 優化
random_page_cost = 1.1
effective_io_concurrency = 200

# 並行查詢（節制，不搶 LLM CPU）
max_parallel_workers_per_gather = 2  # 減半（LLM 也用 CPU）
max_parallel_workers = 4
max_parallel_maintenance_workers = 2

# Autovacuum
autovacuum_max_workers = 3           # 從 5 降到 3（CPU 讓給 LLM）
autovacuum_naptime = '30s'
autovacuum_vacuum_cost_delay = '5ms' # 略微節流，避免 I/O 衝擊 LLM
autovacuum_vacuum_cost_limit = 1000

# TimescaleDB
timescaledb.max_background_workers = 4  # 從 8 降到 4
```

### OS 調優

```ini
vm.nr_hugepages = 4096     # 8GB / 2MB per page
vm.swappiness = 1          # 最小化 swap（LLM 被 swap 出去會災難性慢）
vm.dirty_ratio = 5         # 比默認更積極 flush（減少記憶體壓力）
vm.dirty_background_ratio = 2
vm.overcommit_memory = 0   # 保守模式，避免 OOM killer 殺掉 LLM
```

### PgBouncer（連接池）

```ini
pool_mode = transaction
default_pool_size = 15     # 比 LLM-unaware 少（省 PG backend 記憶體）
max_client_conn = 100
max_db_connections = 20
```

### 存儲分層（NVMe + 40TB NAS）

```
NVMe SSD (本地，低延遲)                     NAS 40TB (10GbE，高容量)
┌────────────────────────────┐              ┌──────────────────────────┐
│ PostgreSQL data directory  │              │ Parquet 長期歸檔          │
│   ~14 GB 活躍數據          │              │   market/klines/         │
│                            │              │   market/ticks/          │
│ PostgreSQL WAL             │  每日 ETL →  │   market/orderbook/      │
│   ~8 GB                    │              │   market/trades/         │
│                            │              │   features/v1/           │
│ 近期 Parquet (7天)         │   7天後遷移→ │   labels/                │
│   ~40 GB                   │              │   models/                │
│                            │              │   ~158 GB/year           │
│ DuckDB temp                │              │   5年: ~790 GB           │
│   ~5 GB                    │              │   40TB NAS: 50年+ 夠用   │
│                            │              │                          │
│ LLM 模型文件               │              │ LLM 模型備份              │
│   ~/.ollama/models/        │              │                          │
│   ~50-100 GB               │              │                          │
└────────────────────────────┘              └──────────────────────────┘

ML 訓練時的數據路徑：
  DuckDB → read_parquet('nas_mount/features/v1/**/*.parquet')
  10GbE 帶寬 ~1.2 GB/s → 讀取 100GB 特徵 ≈ 83 秒（可接受）
  或：先 rsync 到本地 NVMe 再訓練（更快但需空間）
```

---

## 長期性能保障

### 為什麼 3-5 年後仍然「零卡頓」？

1. **PG 活躍數據永遠 ~14 GB** — retention policy + Parquet export 確保不膨脹
2. **TimescaleDB 壓縮 10-20x** — 壓縮後數據完全在 OS page cache 中
3. **Chunk 數量控制在 ~1,200** — 遠低於 5,000 的退化閾值
4. **寫入異步不阻塞** — ring buffer + background thread + sync_commit=off
5. **讀寫不互相阻塞** — PostgreSQL MVCC 天然保證
6. **Parquet 做重活** — ML 訓練讀 Parquet（比 PG 快 10-100x），不查 PG
7. **索引精簡** — 高頻表只有 (symbol, ts DESC) 一個索引，減少寫入放大

### 性能退化邊界

| PG 活躍數據 | 影響 |
|-----------|------|
| <50 GB | 完全在 cache，零影響 |
| 50-200 GB | 冷查詢變慢但熱查詢不受影響 |
| 200-500 GB | VACUUM 變慢，需注意 |
| >1 TB | 需要加磁碟或分佈式 |

**我們的設計確保永遠停留在 <50 GB 區間。**

### 磁碟容量規劃

| 時間 | 動作 |
|------|------|
| Year 1-3 | 無需操作。2TB NVMe 夠用。 |
| Year 4 | 如果 NVMe >70%，加第二塊 2TB NVMe 掛載為 Parquet 目錄 |
| Year 5+ | 持續監控。考慮冷 Parquet 遷移到外部存儲 |

---

## 實施階段（8 週）

### Phase 1 (Week 1): TimescaleDB + Schema + PG 調優
1. 安裝 TimescaleDB · 應用 postgresql.conf · 設置 PgBouncer
2. 創建 6 個 schema · 所有表 · hypertable 配置
3. 壓縮策略 · 保留策略 · 連續聚合
4. Migration SQL: `docker_projects/monitoring_services/migrations/`

### Phase 2 (Week 2): 市場數據持久化（止血）
5. `kline_manager.py` → `market.klines`
6. `indicator_engine.py` → `market.indicators`（全 16 指標一行）
7. `bybit_public_ws_listener.py` → `market.raw_ticks`（async batch）
8. `market_regime.py` → `market.regime_snapshots/transitions`

### Phase 3 (Week 3): 新 Bybit 數據源 + Orderbook + Trade Tape
9. WS 訂閱: `liquidation.{symbol}`, `orderbook.25.{symbol}`, `publicTrade.{symbol}`
10. REST 定時: funding history (15m), OI (5m), L/S ratio (15m)
11. 新建 `bybit_market_data_capture.py`

### Phase 4 (Week 4): 交易 + Agent 持久化
12. signals → `trading.signals`
13. guardian verdicts → `trading.risk_verdicts`
14. agent messages → `agent.messages`
15. order state changes → `trading.order_state_changes`（事件溯源）

### Phase 5 (Week 5): Decision Context Snapshot（核心）
16. 新建 `decision_context_capture.py`（~300 行）
17. 在 pipeline_bridge / guardian / paper_engine 插入 capture
18. outcome 回填 cron job
19. 數據質量監控 cron（`quality.data_quality_events`）

### Phase 6 (Week 6): Feature Store + Model Registry
20. `features.online_latest` UPSERT 管線
21. 特徵版本管理
22. 模型生命週期管理（`learning.model_registry`）

### Phase 7 (Week 7): ML Pipeline
23. PG → Parquet 每日 ETL
24. DuckDB label 生成
25. PyTorch Dataset（memory-mapped Parquet）
26. RL episode tracker + state vector flattener
27. 時間切分 + embargo

### Phase 8 (Week 8): 漸進放權 + 驗證
28. `learning.promotion_pipeline` + 畢業邏輯
29. Claude AI 評估報告生成器
30. GovernanceHub ML 建議審批通道
31. 全管線回放驗證 + 性能測試

---

## 關鍵文件清單

**修改:**
- `kline_manager.py` · `indicator_engine.py` · `bybit_public_ws_listener.py` · `market_regime.py`
- `signal_generator.py` · `guardian_agent.py` · `multi_agent_framework.py`
- `paper_trading_engine.py` · `pipeline_bridge.py` · `grafana_data_writer.py`

**新建:**
- `migrations/*.sql` (6+ migration files)
- `decision_context_capture.py` · `bybit_market_data_capture.py`
- `ml/dataset.py` · `ml/rl_episode_tracker.py` · `ml/promotion_manager.py`
- `ml/evaluation_report_generator.py` · `ml/model_registry.py`
- `etl/pg_to_parquet.py` · `etl/generate_labels.py` · `ml/temporal_split.py`
- `quality/data_quality_checker.py`

## 驗證

1. Schema: `\dt market.*` 確認所有表
2. 寫入: 啟動 5min 後 `SELECT count(*) FROM market.klines WHERE ts > now()-'5m'`
3. 壓縮: `SELECT * FROM timescaledb_information.compression_settings`
4. Decision Context: 手動觸發 paper trade，確認完整行
5. ETL: 運行 pg_to_parquet.py → DuckDB 讀取確認 schema
6. 性能: tick 路徑 timing，確認 PG 寫入不阻塞（<0.1ms overhead）
7. 長期: `SELECT pg_size_pretty(pg_database_size('trading_ai'))` 監控
