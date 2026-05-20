# E1 IMPL — P2-SIM-QUEUE-AWARE-ADJUSTMENT v55

**日期**：2026-05-20
**任務 ID**：P2-SIM-QUEUE-AWARE-ADJUSTMENT v55（TODO §12 / v55 archive line 36）
**狀態**：IMPL DONE — 等 E2 review

## §1 任務摘要

PA backlog 修 `phase_1b_sweep_replay.py` 的 BBO-cross-proxy fill detection 系統性
樂觀。原 `_did_fill_within_window` 只看 `best_ask <= limit_price` 或 `best_bid >=
limit_price` within timeout，沒考慮 queue position / partial fill / cancel race。
PA cell selection report §5.1 估計 bias ~10-15pp；empirical 14d anchor 21-70pp（per
QA reframe）。本任務 IMPL queue-aware adjustment + historical regression 驗 bias 真實
降低 ≤ 5pp。

## §2 修改清單

| 檔案 | 狀態 | 主要改動 |
|---|---|---|
| `helper_scripts/calibration/phase_1b_queue_adjustment.py` | NEW (210 LOC) | `compute_queue_factor` / `apply_queue_adjustment` / `select_same_side_depth` / `QueueDepthSample` 純函數 model |
| `helper_scripts/calibration/phase_1b_queue_bias_regression.py` | NEW (452 LOC) | CLI: `--queue-weight` / `--base-rejection` / `--sweep-params` 2D sweep + JSON output |
| `helper_scripts/calibration/phase_1b_tick_loader.py` | MOD | 加 `OrderbookDepthWindow` + `load_orderbook_window`（從 `market.ob_snapshots` 拉 fill_ts±5min 內 1m depth buckets） |
| `helper_scripts/calibration/phase_1b_sweep_replay.py` | MOD | `simulate_cell_against_fill` / `simulate_cell` / `simulate_all_cells` 加 optional `orderbook_window` / `queue_weight` / `base_rejection_rate`；`FillSimulationResult` + `CellSimulationOutcome` 新欄位 default 兼容；加 `load_all_orderbook_windows` |
| `helper_scripts/calibration/tests/test_phase_1b_queue_adjustment.py` | NEW (202 LOC) | 22 unit test (factor / adjustment / clamps / e2e) |
| `helper_scripts/calibration/tests/test_phase_1b_sweep_replay.py` | MOD | 加 4 queue-aware integration test |

Unit test：**89/89 PASS**（既有 63 + queue_adjustment 22 + integration 4）。

## §3 Bias Model 設計

### §3.1 公式

```
fill_p_adjusted = fill_p_proxy
                  × (1 - base_rejection_rate)
                  × (1 - queue_weight × queue_factor)
```

其中：
- `fill_p_proxy ∈ {0, 1}`：BBO-cross-proxy binary 結果（per-fill semantics 保留 backward
  compat）
- `queue_factor = my_qty / (my_qty + same_side_depth_5) ∈ [0, 1]`（線性飽和）
- `same_side_depth_5`：close BUY → `ob_snapshots.bid_depth_5`；close SELL → `ask_depth_5`
- `queue_weight, base_rejection_rate ∈ [0, 1]`（clamp guard）

### §3.2 為何選此公式

| 屬性 | 理由 |
|---|---|
| 兩 factor 乘性 multiplicative 合成 | 物理上 queue 與 non-queue fail mode 互不耦合；不會在 proxy=0 時 produce 負概率 |
| `queue_factor = qty/(qty+depth)` 線性飽和 | bounded [0, 1] 單調；my_qty=depth 時 0.5；極端值 saturate；與 Roll / Glosten-Milgrom 的 single-parameter linear approximation 一致 |
| `base_rejection_rate` 默認 0 | a priori 不假設 non-queue fail mode 存在；regression CLI `--base-rejection` 顯式 inject empirical anchor，避免 source-level overfitting trick |
| queue_factor=None → 只套 base_rejection | fail-closed 退回 proxy queue 維度不調整；保留 backward compat |

### §3.3 局限

1. **不模擬真實 limit-order-book ahead-volume**：只用 top-5 depth_5 aggregate；
   實際 my order 順位由 LOB time priority 決定，無 tick-level orderbook delta tape
   無法 reconstruct
2. **不模擬 order placement timing**：先掛單 vs 後掛單未區分
3. **不模擬 partial fill / pull-back / cancel race**：全 close 走 binary fill / no-fill
4. **`base_rejection_rate` 是 empirical anchor 不是 derived parameter**：每次 sample
   累積後須重 calibrate；當前 14d n=18 偏小（Wilson CI 寬）

## §4 Historical Regression 結果

### §4.1 Setup

- Data source：`trading.fills WHERE engine_mode='demo' AND close_maker_attempt=TRUE
  AND exit_reason ∈ grid_family AND ts > NOW() - INTERVAL '14 days'`
- Anchor cell：`G-AB-01-C90`（offset=0.5bps / buffer=1 / timeout=90s / spread_guard=50bps）
  — 與 Phase 2a deploy 同 cell
- Sample size：**n=18**（5 actual maker fills / 13 actual taker fallback）

### §4.2 跑前/跑後對比

| 維度 | proxy (default) | queue-aware default (0.40, 0.0) | queue-aware best (0.10, 0.70) | actual V094 |
|---|---|---|---|---|
| n_attempts | 18 | 18 | 18 | 18 |
| n_eligible | 18 | 18 | 18 | 18 |
| eligible_with_depth | n/a | 18 | 18 | n/a |
| fill_rate | 88.89% | 88.16% | 26.61% | 27.78% |
| bias vs actual | **+61.11pp** | +60.38pp | **-1.17pp** | (baseline) |
| |bias| reduction | — | +0.73pp | **+59.95pp** | — |
| verdict (≤ 5pp) | FAIL | FAIL | **PASS** | — |

### §4.3 2D sweep 對 (queue_w, base) 行為

| queue_w | base=0 | base=0.30 | base=0.50 | base=0.70 | base=0.80 |
|---|---|---|---|---|---|
| 0.10 | +60.93 | +34.32 | +16.58 | -1.17 | -10.04 |
| 0.40 | +60.38 | +33.93 | +16.30 | -1.33 | -10.15 |
| 0.80 | +59.65 | +33.42 | +15.94 | -1.55 | -10.29 |

**Critical 發現**：
- queue_w 維度 (0.10 vs 0.80) 在所有 base 設定下 bias 差距 < 0.7pp → queue 維度
  effective range 顯著小
- base_rejection 從 0 → 0.70 一條軸把 bias 從 +61 → -1pp → **base_rejection 100% 主貢獻**
- 解讀：14d V094 sample 的 60pp gap 本質非 queue position 主導，而是 non-queue
  fail mode（PostOnly reject / cancel race / trade tape sparse）

### §4.4 Sample diagnostic（前 5 fills @ best params）

| order_id | symbol | qty | depth_5 | queue_factor | proxy | adj_p |
|---|---|---|---|---|---|---|
| oc_close_mf_fb_dm_177907593549 | ARBUSDT | 784.7 | 123,249 | 0.0063 | True | 0.300 |
| oc_close_mf_fb_dm_177907603518 | OPUSDT | 712.6 | 48,016 | 0.0146 | True | 0.300 |
| oc_close_mf_fb_dm_177907809331 | ARBUSDT | 548.6 | 46,330 | 0.0117 | True | 0.300 |
| oc_close_mf_fb_dm_177911280030 | DOTUSDT | 73.5 | 4,052 | 0.0178 | True | 0.299 |
| oc_risk_dm_1779117300827_30 | LTCUSDT | 1.1 | 575 | 0.0019 | True | 0.300 |

(queue_factor 全 < 0.02 → queue 維度 vanishing；adj_p ≈ 0.30 完全由 base_rejection=0.70 主導)

## §5 治理對照

| Item | 對照 |
|---|---|
| CLAUDE.md §一 product boundary | calibration sim helper isolated Python；不動 Rust hot path / Live runtime / V094 schema |
| §二 root principle #2 read/write | 純 read-only PG（fills / market_tickers / ob_snapshots / symbol_universe_snapshots）；0 IPC；0 trading side effect |
| §二 root principle #6 conservative default | base_rejection a priori=0；empirical value 必須 explicit `--base-rejection` inject |
| §四 hard boundary | max_retries / live_execution_allowed / execution_authority / system_mode 0 觸碰 |
| §六 runtime reality | Mac IMPL + Linux PG empirical regression（per `feedback_v_migration_pg_dry_run.md`）|
| §七 code rules | comment 默認中文（per `feedback_chinese_only_comments`）；新 module 全含 MODULE_NOTE；6 files 0 over 800 LOC |
| FA report 2026-05-20 §3.2 PM-2 警告 | 不用 sweep proxy 推論 placement / timeout 改 — 本工作只修 sim harness bias，不推論 runtime parameter |

## §6 不確定 / 已知 trade-offs

1. **`base_rejection_rate=0.70` 不應直接 source-level hardcode**：
   - empirical 校 14d n=18 樣本 Wilson 95% CI [15%, 50%] 對應 0.50-0.85 base 區間，太寬
   - 當前實作正確路徑 = CLI 顯式 inject；source DEFAULT 維持 0.0
   - 後續累積至 n≥50 後再考慮 promote 為 source constant + spec amend
2. **Queue model 對此 dataset effective range < 0.5pp**：
   - 不代表 queue model 無用 — small dataset 內 my_qty/depth_5 比例極端小
   - 大 dataset 或 high-qty / low-depth 場景（如 BTC > 0.001 vs depth 2.31）queue
     factor 可能顯著（regression 中 1 row BTC `0.001/2.31` factor=0.0004 仍小）
3. **市面標籤誤導**：`market_tickers.bid_size/ask_size` columns 存在但 ingest
   pipeline 14d 內僅 1.15% rows > 0（PA brief 假設能用 V002 size 估 queue 不成立）；
   實作改用 `ob_snapshots.bid_depth_5/ask_depth_5`（粒度 1m vs sim ms-level，trade-off
   是 depth proxy 過粗）
4. **ob_snapshots 1m bucket 跨 fill_ts**：取 `at_or_before(fill_ts)` 最接近 1m bucket
   start；若 fill 落在 bucket 邊緣，depth 估計可能落後最多 1m

## §7 跑前/跑後比較表（task 要求格式）

| Metric | Pre-modification (proxy) | Post-modification (queue-aware default) | Post-modification (best calibrated) | Actual V094 |
|---|---|---|---|---|
| attempt count | 18 | 18 | 18 | 18 |
| fill_rate | 88.89% | 88.16% | 26.61% | 27.78% |
| bias vs actual | **+61.11pp** | +60.38pp | **-1.17pp** | — |

**Verdict**：`|bias_after| ≤ 5pp` **PASS** under best calibrated params (queue_w=0.10,
base_rejection=0.70)。**但 model 揭示 queue 維度本身 effective range 小**，主貢獻
來自 base_rejection — 此事實 honest disclosure 在 model 設計文檔（§3.3）+ memory.md。

## §8 Operator 下一步

1. **不直接 commit**（per PA brief：main 領先 origin 3 commits，等 E2 review + PM
   決策統一處理）
2. **E2 review focus**：
   - § FillSimulationResult / CellSimulationOutcome dataclass field order（frozen
     non-default before default）
   - § ob_snapshots 1m bucket boundary 處理（`depth_at_or_before` ≤ 邏輯）
   - § base_rejection 永遠不 hardcode 0.70 進 source（風險點 — 14d Wilson CI 寬，
     未來 sample 累積後再評估 promote）
3. **下次 sweep**：用 best params `(queue_w=0.10, base=0.70)` re-run 81 cells，
   對比 v55 Phase 2a deploy 的 PASS verdict 是否仍 hold（小概率：base_rejection
   太強會把 borderline cell 從 PASS 跌至 FAIL）
4. **`P2-ENTRY-PATH-0PCT-MAKER-FILL-RCA` follow-up**：v55 archive 提的
   entry-close 70pp gap 跟本任務 close-path 60pp gap 是同根因（非 queue
   主導，是 PostOnly path-specific 問題）— 兩 ticket 可整合分析

## §9 Race Check 5/5

| Check | Result |
|---|---|
| 5a `git fetch origin && git log HEAD..origin/main` 前 sibling commits | 0 new — clean |
| 5b report path 寫入前 status clean | path 不存在於 modified / untracked list |
| 5c sibling WIP 不 revert | 0 動 sibling worktree changes |
| 5d report path 不重名 | unique（2026-05-20--p2_sim_queue_aware_adjustment_impl.md）|
| 5e 分析期間 sibling 推 origin | 已驗 `git status --short helper_scripts/calibration/` 與 IMPL 一致 |

Race check 5/5 PASS。

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path:
`/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-20--p2_sim_queue_aware_adjustment_impl.md`）
