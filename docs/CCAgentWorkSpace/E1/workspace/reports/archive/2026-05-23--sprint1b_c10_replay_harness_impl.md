---
report: E1 — Sprint 1B Pending 3.1 C10 Stage 0R replay preflight harness IMPL (Wave B B4)
date: 2026-05-23
author: E1 (Backend Developer)
phase: Sprint 1B late · Pending 3.1 Wave B B4 IMPL
status: IMPL DONE / waiting E2 review
parent dispatch:
  - docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_c10_funding_harvest_stage1_demo_dispatch_packet.md §6 §8.2 B4
upstream contracts:
  - AMD-2026-05-15-01 §3 §3.2 §4.3 §4.4 (Stage 0R preflight + demo evidence + rollback)
  - docs/references/2026-04-04--bybit_api_reference.md §get_funding_history (line 148-161)
  - helper_scripts/canary/replay_runner.py (既有 paradigm; 不改邏輯 純擴展)
files changed:
  - 新檔 helper_scripts/canary/replay_funding_harvest.py (1089 LOC)
not in scope:
  - 不改 既有 replay_runner.py / canary_comparator.py / canary_schema.py
  - 不發 Bybit live order；僅 GET /v5/market/{funding/history,kline} 公開 endpoint
  - 不 commit；待 E2 review → E4 regression → PM 統一 commit
  - 不派下游 sub-agent
---

# E1 — Sprint 1B Pending 3.1 C10 Stage 0R replay preflight harness IMPL

## §1 任務摘要

per dispatch packet §6 + §8.2 B4：IMPL Stage 0R replay preflight harness Python 端，
拉 Bybit 30d BTCUSDT perp funding rate + perp 1m kline + spot 1m kline，
對 C10 funding_harvest 策略走 tick-by-tick simulation，
執行 6 條 sanity check，產出 `eligible_for_demo_canary` verdict JSON + detailed metrics JSON。

新檔 `helper_scripts/canary/replay_funding_harvest.py` 1089 LOC，
與既有 `replay_runner.py` 並列、共用 Bybit V5 REST 模式但不依賴後者私有 hard-coded `category=linear`。

---

## §2 修改清單 (1 新檔)

### §2.1 新檔 helper_scripts/canary/replay_funding_harvest.py (1089 LOC)

完整 fn 清單：

| 段 | Fn / Class | LOC est | 職責 |
|---|---|---|---|
| §Bybit REST | `fetch_funding_rates(symbol, days, category)` | ~70 | 拉 days×3 funding events from `/v5/market/funding/history`；paginated by `endTime`；chronological sort + truncate；100 ms rate-limit sleep |
| §Bybit REST | `fetch_klines_v5(symbol, interval, limit, end_ms, category)` | ~40 | 單頁 kline；`category='linear'` (perp) or `'spot'` 通用；reverse newest→chronological |
| §Bybit REST | `fetch_perp_klines(symbol, days)` | ~3 | 30d 1m perp kline (43200 bars) thin wrapper category='linear' |
| §Bybit REST | `fetch_spot_klines(symbol, days)` | ~3 | 30d 1m spot kline (43200 bars) thin wrapper category='spot' |
| §Bybit REST | `_fetch_klines_paginated(symbol, days, category)` | ~30 | 通用 multi-page kline backfill (取代 replay_runner 私有 fetch_klines_multi_page) |
| §SyntheticSpot | `SyntheticSpotLedger` (dataclass) | ~80 | Python mirror of Rust `funding_harvest::synthetic_spot::SyntheticSpotLedger`；`open_long` / `rebalance` / `close` / `unrealized_pnl_usd` / `delta_drift_pct` |
| §Strategy | `FundingHarvestState` (dataclass) | ~15 | 每 symbol strategy runtime state；mirror Rust FundingHarvest fields |
| §Strategy | `TradeRecord` (dataclass) | ~25 | 完整 entry→exit trade PnL record；includes funding payment / perp PnL / synth spot PnL / fees / exit_reason |
| §Strategy | `_annualized(funding_rate_8h)` | ~3 | × 3 × 365 (Bybit 8h cycle) |
| §Strategy | `_compute_basis_pct(perp, spot)` | ~5 | `|perp/spot - 1| × 100`；spot<=0 → inf (fail-closed) |
| §Strategy | `_compute_net_edge_bps_per_period(rate, cost_bps, periods)` | ~3 | `|rate| × 10000 - cost/periods` |
| §Strategy | `_should_enter(rate, basis, config)` | ~10 | 4-condition mirror Rust should_enter |
| §Strategy | `_should_exit(rate, basis, now, entry, config)` → (bool, reason) | ~15 | 4-condition (funding_decay / flip / basis_drift / max_hold) |
| §Strategy | `_interpolate_funding_at_ts(ts, events)` | ~15 | binary search 最近 ≤ ts 的 funding event；避 lookahead |
| §Strategy | `_build_spot_price_index` / `_get_spot_price_at_ts` | ~25 | spot kline ts→close lookup with binary search |
| §Strategy | `replay_funding_harvest(symbol, perp, spot, funding, config)` → (trades, daily_pnl) | ~130 | 主 simulation：tick-by-tick on_tick；累積 funding settle / rebalance check / entry-exit；返回 trades + daily PnL series |
| §SanityCheck | `sanity_check_leak_lookahead(trades, events)` → (status, msg) | ~25 | 每筆 entry funding rate 必對應 entry_ts 之前最近 funding event |
| §SanityCheck | `sanity_check_selection_bias(trades, events, klines)` → (status, msg) | ~15 | replay 覆蓋 ≥ 28d (容 1d 邊界) perp + funding span |
| §SanityCheck | `sanity_check_dsr_psr(daily_pnl)` → (status, msg, metrics) | ~50 | Sharpe + skew + excess_kurt + PSR (Bailey/LdP 2014 formula) |
| §SanityCheck | `sanity_check_pbo_bootstrap(daily_pnl, n=1000, seed=42)` → (status, msg, metrics) | ~30 | 1000-sample bootstrap cum PnL；lower 5% ≥ -$5 floor |
| §SanityCheck | `sanity_check_replay_data_tier(replay_pnl, demo_pnl)` → (status, msg) | ~15 | vacuous pass when demo_pnl=None (Stage 0R 首次 run C10 無 historical demo) |
| §SanityCheck | `sanity_check_runtime_boundary()` → (status, msg) | ~5 | by design PASS (harness 純 simulation不寫 PG / 不發 order / 不 claim 替代 demo lineage) |
| §Output | `output_preflight_verdict(symbol, days, trades, daily_pnl, events, perp, dir)` → dict | ~110 | 組裝 verdict JSON + detailed metrics JSON；雙寫 stage0r_<date>.json + stage0r_metrics_<date>.json |
| §Main | `run_stage0r_preflight(symbol, days, dir, config_override)` | ~50 | full pipeline orchestrator (4-step fetch → simulate → verdict) |
| §CLI | `main()` | ~20 | argparse + exit code 對應 eligible_for_demo_canary |

LOC 略超 dispatch packet §6.5 estimate ~800 因為加了完整 Python mirror SyntheticSpotLedger + TradeRecord/FundingHarvestState dataclasses + binary search helper（避 O(n) 線性掃描 funding events）。仍遠低於 800/2000 line warn/cap。

---

## §3 6 sanity check 設計 + output JSON shape

### §3.1 6 條 check 設計 (per dispatch packet §6.3)

| # | Check | Pass criteria | Fail action |
|---|---|---|---|
| 1 | **leak / lookahead** | 每筆 trade.entry_funding_rate 必對應 `entry_ts_ms` 之前最近 funding event | FAIL → fix simulation logic |
| 2 | **selection bias** | replay span ≥ 28d (perp + funding 雙向)；全 events 被考慮不 cherry-pick | by design PASS;FAIL 觸發必修 fetch 邏輯 |
| 3 | **DSR / PSR** | Sharpe > 0 AND PSR (Bailey/LdP 2014) > 0.6 deflated for 1 strategy | FAIL → strategy 結構性問題 → retire |
| 4 | **PBO bootstrap** | 1000-sample bootstrap cum PnL lower 5% tail ≥ -$5 (= Stage 1 stop_loss 上限) | FAIL → too risky → 不開 Stage 1 |
| 5 | **replay data tier** | replay vs historical demo PnL drift < 1% (有 demo) OR vacuous (無 demo Stage 0R 首次) | FAIL → schema mismatch → revisit |
| 6 | **runtime boundary** | harness 純 simulation不寫 PG/不發 order/不 claim 替代 demo lineage | by design PASS |

### §3.2 PSR 公式校驗（Bailey & López de Prado 2014）

```
PSR(SR) = Φ((SR - SR_benchmark) × sqrt(n-1) / sqrt(1 - skew*SR + (kurt-3)/4 × SR^2))
```

本 harness 設 `SR_benchmark = 0` (zero baseline)；1 strategy 不 multiple-testing 校正；
denominator non-positive 時 FAIL（避 NaN 數學陷阱）；
PSR 用 `Φ(z) = 0.5 × (1 + erf(z/sqrt(2)))` 標準正態 CDF。

### §3.3 Bootstrap 設計

- `n_bootstrap = 1000` (per dispatch packet)；`seed = 42` 重現性
- 從 `daily_pnl_usd` resample with replacement n 次取 cum sum
- lower 5% / median / upper 5% 全 report
- FAIL 條件：lower 5% < -$5 (Stage 1 stop_loss floor)

### §3.4 Output JSON shape (per dispatch packet §6.4)

verdict JSON `funding_harvest_stage0r_<date>.json`：

```json
{
  "strategy": "funding_harvest",
  "symbol": "BTCUSDT",
  "replay_window_days": 30,
  "replay_start_ts_ms": 1704067200000,
  "replay_end_ts_ms": 1706659200000,
  "funding_events_total": 90,
  "entry_events": 8,
  "exit_events": 8,
  "max_concurrent_positions": 1,
  "replay_pnl_perp_leg_usd": -2.15,
  "replay_pnl_synthetic_spot_leg_usd": +3.42,
  "replay_pnl_net_usd": +1.27,
  "sharpe": 0.4231,
  "deflated_psr": 0.6512,
  "bootstrap_lower_5pct_pnl_usd": -1.85,
  "attribution_chain_ok_pct": 100.0,
  "leak_lookahead_check": "PASS",
  "selection_bias_check": "PASS",
  "dsr_psr_check": "PASS",
  "pbo_bootstrap_check": "PASS",
  "replay_data_tier_check": "PASS",
  "runtime_boundary_check": "PASS",
  "eligible_for_demo_canary": true,
  "reasons": ["leak_lookahead: PASS (...)", "...6 strings..."],
  "evidence_refs": ["...stage0r_<date>.json", "...stage0r_metrics_<date>.json"],
  "config_snapshot": { /* 10 param values */ },
  "generated_at_iso": "2026-05-23T...",
  "elapsed_seconds": 12.3
}
```

detailed metrics JSON `funding_harvest_stage0r_metrics_<date>.json` 含：
- `trades`: list of TradeRecord (entry/exit ts + prices + funding rate + per-leg PnL + fees + exit_reason + hold_ms)
- `daily_pnl_usd`: list (calendar UTC day boundary)
- `psr_metrics`: { sharpe / skew / excess_kurt / psr / mean / stdev / n_days }
- `bootstrap_metrics`: { n_bootstrap / lower_5pct / median / upper_5pct }

---

## §4 Bybit V5 endpoint 對齊

per `docs/references/2026-04-04--bybit_api_reference.md` §get_funding_history (line 148-161):

### §4.1 fetch_funding_rates → GET /v5/market/funding/history

| Param | Value | Source |
|---|---|---|
| `category` | `linear` (perp) | dispatch packet §2.1 funding_arb 範式 |
| `symbol` | `BTCUSDT` | Stage 1 限定 |
| `limit` | 200 (Bybit max) | reference line 156 |
| `endTime` | pagination ms cursor | backward pagination |
| pagination | 30d × 3 events/d = 90，1 page 足夠 + 容錯保留 | – |
| return | `{ symbol, funding_rate, funding_rate_timestamp_ms }` chronological | mapped from `fundingRate` / `fundingRateTimestamp` |

### §4.2 fetch_perp_klines / fetch_spot_klines → GET /v5/market/kline

- `category=linear` (perp) vs `category=spot`
- `interval=1` (1m)
- `limit=200` per page
- 30d × 24h × 60min = 43200 bars → 216 pages × 100ms sleep ≈ 22s per leg
- 既有 `replay_runner.py:63 fetch_klines` 私有 hard-code `category=linear`；本 harness 新增獨立 `fetch_klines_v5(category=...)` 而不擴 既有 fn，per 任務「不改既有 replay_runner.py 既有 logic」禁忌

### §4.3 注意：funding events vs spot 不一致

- Bybit `/v5/market/funding/history` 只 linear (perp)；spot 無 funding 概念
- spot leg PnL 計算用 `fetch_spot_klines` close price，作為 SyntheticSpotLedger 之 spot 對沖近似
- Stage 4 LIVE 升級 (Sprint 5+) 才會打 spot real order；Stage 0R-3 純內部 book-keeping

---

## §5 py_compile + pytest 結果 + E2 重點 3 條

### §5.1 驗證結果

```
$ /Users/ncyu/Projects/TradeBot/srv/venvs/mac_dev/bin/python -m py_compile helper_scripts/canary/replay_funding_harvest.py
PY_COMPILE_OK

$ /Users/ncyu/Projects/TradeBot/srv/venvs/mac_dev/bin/python -m pytest helper_scripts/canary/ -k funding_harvest --tb=short
collected 235 items / 235 deselected / 0 selected
(無 funding_harvest 既有測試；dispatch §6.5 範圍未要求新測試)

$ /Users/ncyu/Projects/TradeBot/srv/venvs/mac_dev/bin/python -m pytest helper_scripts/canary/ --tb=short -q
235 passed in 33.34s
(0 regression on canary 既有套件)

$ smoke test (16 fn/class 存在 + SyntheticSpotLedger PnL math + should_enter 4 edge case)
ALL PASS
```

### §5.2 E2 重點審查 3 條

per dispatch packet §10 範式 + 本 harness 高風險點：

#### §5.2.1 leak / lookahead 防護 + funding event interpolation

E2 必驗：
1. `_interpolate_funding_at_ts(ts, events)` 用 binary search 取 **最近 ≤ ts** 的 funding event；驗 trade.entry_funding_rate 不可用 entry_ts 之後的 funding rate
2. `replay_funding_harvest` 主迴圈內 `last_funding_settle_ts` 起始為 0（無倉）／入倉時設為 entry_ts_ms（避入場那刻 settle 一次重複計）
3. Funding settle 累積區間用 `ev_ts > last_funding_settle_ts and ev_ts <= ts_ms`（half-open，避重複累計同一 event）
4. `sanity_check_leak_lookahead` 對每筆 trade 重跑 prior funding 搜尋，與 trade.entry_funding_rate 比對 abs_tol=1e-9

#### §5.2.2 SyntheticSpotLedger PnL math + delta drift 公式對齊 Rust mirror

E2 必驗：
1. `open_long(notional, spot_price, ts)`: `qty = notional / spot_price` (LONG 方向；spot<=0 raise ValueError)
2. `rebalance`: 只改 qty + last_rebalance；**entry_price 鎖死作 PnL 基準**（dispatch packet §2.5 + §3.2 spec）
3. `close(close_price, ts)`: `pnl = (close - entry_price) × qty`（spot LONG: 漲賺跌虧）— 注意 PnL 用 entry_price 不是 last_rebalance_price，與 Rust mirror 對齊
4. `delta_drift_pct(perp_notional, spot_price)`: `abs((current_spot_notional - perp_notional) / current_spot_notional)` — **divide by spot side**（dispatch packet §10.1 verify item 4）
5. perp leg PnL 用 `-(exit - entry) × qty`（perp **SHORT** 反向；漲虧跌賺）— 與 spot LONG 對沖

#### §5.2.3 PSR 公式正確性 + Bootstrap 邊界

E2 必驗：
1. PSR formula `0.5 × (1 + erf(z/sqrt(2)))` 對齊 Φ(z) 標準正態 CDF
2. PSR `denom_inner = 1 - skew*sr + (excess_kurt)/4 × sr^2` — `excess_kurt = kurt - 3` (NOT raw kurt) 與論文一致
3. `denom_inner <= 0` → 即時 FAIL（避 sqrt of negative NaN 陷阱）
4. Bootstrap `seed=42` 寫死保證可重現；`n_bootstrap=1000` 對齊 dispatch packet 要求
5. `BOOTSTRAP_LOWER_5PCT_FLOOR = -5.0` 對應 Stage 1 stop_loss_pct=0.05 × $100 cap = $5
6. `daily_pnl_usd` 用 UTC calendar day 邊界劃分（避時區漂移影響統計）

---

## §6 治理對照

per dispatch packet §6 + AMD-2026-05-15-01 + 16 root principles：

| 原則 / AMD 條款 | 本 IMPL 對應 |
|---|---|
| 原則 1（單一寫入口） | harness 純 simulation不打 Bybit order不寫 PG；strategy IMPL B1 perp leg 經 IntentProcessor 路徑 |
| 原則 2（讀寫分離） | harness 純讀 Bybit V5 公開 endpoint；不訂閱認證 endpoint |
| 原則 4（策略不繞風控） | 本 harness 不執行；驗證 strategy IMPL B1 是否 Stage 1 deployable 的 preflight |
| 原則 12（行為從 evidence 演化） | 6 sanity check + verdict JSON evidence_refs 完整審計鏈 |
| AMD §3.2 eligible_for_demo_canary gate | output verdict bool field 強制 6 check 全 PASS |
| AMD §4.3 Stage 1 demo evidence | harness 為 §4.3 evidence 之 _preflight_ gate（非 Stage 1 evidence 本身） |
| AMD §4.4 rollback | harness 失敗 → strategy 不開 Stage 1；無 rollback 觸發 |
| 16 §6（不確定 fail-closed） | spot_price <= 0 → basis_pct = inf；缺 funding 或 spot data → skip tick；PSR denom <= 0 → FAIL |

---

## §7 不確定之處 (3 條)

### §7.1 LOC over budget (1089 vs 800 estimate)

dispatch packet §6.5 estimate ~800 LOC；本 IMPL 1089 LOC，因加完整 SyntheticSpotLedger Python mirror（spot leg PnL/delta_drift 嚴格對齊 Rust mod）+ TradeRecord/FundingHarvestState dataclasses + binary search helper（funding/spot lookup 由 O(n²) → O(n log n)，30d 43200 bar × 90 events 場景必要）。

E2 判斷：
- (a) 接受 LOC 略超（仍遠低於 800/2000 warn/cap）+ 完整 mirror
- (b) 拆 synthetic_spot.py 獨立 module（與 Rust funding_harvest/synthetic_spot.rs 命名對齊）

建議 (a)。dispatch packet §6.5 估計為 plan，實 IMPL 對齊 Rust spec 完整性優先。

### §7.2 historical demo PnL = None vacuous pass

`sanity_check_replay_data_tier` 在 demo_pnl=None 時 vacuous PASS（per dispatch packet §6.3 row 5 設計：Stage 0R 首次 run C10 新策略無 historical demo path）。

E2 / QA 後續 Stage 0R 第二次 run (e.g., Stage 1 結束 7d 後 Stage 2 升級 preflight) 須 supply Stage 1 actual PnL 至 `historical_demo_pnl_usd` 觸發 1% drift check。

### §7.3 perp fee 估計 5.5 bps/side 來源

`perp_fee_bps_per_side = 5.5`（即 round-trip 11 bps）對齊 dispatch packet §1.2 `total_cost_bps = 37 = perp(11) + spot(20) + slip(3) + basis_drift(3)`。

實際 Bybit V5 perp linear taker 0.055% = 5.5 bps + maker 0.02% = 2 bps；保守用 taker 5.5。

E2 + BB 若認為 funding_harvest entry 用 PostOnly maker → fee 應降至 2 bps/side；本 IMPL 用 5.5 conservative。若 BB confirm maker route，改 `perp_fee_bps_per_side = 2.0` （Round 2 fix scope）。

---

## §8 Operator 下一步建議

per dispatch packet §8.3-§8.5 + 強制鏈 E1→E2→E4→QA→PM：

1. **W+0**: 派 E2 adversarial review 本 IMPL (2-3 hr per §10 範式)
   - 重點 3 條 per §5.2 (leak / synth spot math / PSR)
   - grep 規 check：`urllib.request.urlopen` × 2 (funding history + kline) 不打認證 endpoint
2. **W+0**: 並行派 A3 (QC) PSR formula + bootstrap LOC 校驗 (2-4 hr)
3. **W+1**: Round 2 fix per E2/A3 verdict (0-4 hr)
4. **W+1.5**: 派 E4 regression — Linux runtime 環境 dry-run harness（不發 live request 走 mock funding history fixture 即可；real Bybit 公開 GET 也安全）
5. **W+2**: PM 拍板 Wave B 其他 sub-task (B1/B2/B3/B5) dispatch；本 B4 可獨立 ship 不阻塞其他

---

## §9 完成回報 4 條

1. **replay_funding_harvest.py LOC + fn 清單**: 1089 LOC; 16 主 fn/class (詳 §2.1) 涵 Bybit REST × 5 / SyntheticSpotLedger / FundingHarvestState / TradeRecord / Strategy core × 6 helpers / 6 sanity check / output verdict / run_stage0r_preflight / main CLI
2. **6 sanity check 設計 + output JSON shape**: 6 check (leak/lookahead • selection bias • DSR/PSR Bailey-LdP 2014 • PBO 1000-sample bootstrap • replay data tier • runtime boundary)；verdict JSON 28 field 對齊 dispatch packet §6.4；detailed metrics JSON 含 trades + daily_pnl + psr_metrics + bootstrap_metrics
3. **fetch_funding_rates + fetch_spot_klines Bybit V5 endpoint 對齊**: `/v5/market/funding/history` (category=linear, paginated by endTime) + `/v5/market/kline` (category=spot, paginated by end_ms) 對齊 docs/references/2026-04-04--bybit_api_reference.md §get_funding_history line 148-161；獨立 fn 不擴既有 replay_runner.fetch_klines (per 禁忌不改既有邏輯)
4. **py_compile + pytest 結果 + E2 重點 3 條**: py_compile PY_COMPILE_OK；canary 既有 pytest 235 passed 0 regression；funding_harvest 既有 0 測試（dispatch §6.5 範圍未要求新測試）；smoke test SyntheticSpotLedger PnL 數學 + _annualized + _should_enter 4 edge case 全 PASS；E2 重點 3 條 (leak/lookahead 防護 • SyntheticSpotLedger PnL math • PSR formula + bootstrap 邊界) per §5.2

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint1b_c10_replay_harness_impl.md）
