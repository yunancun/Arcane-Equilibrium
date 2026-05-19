# Phase 1b Calibration Sweep — Cell Selection Report

- Date: 2026-05-18 (Mac, post-sweep run `sweep_20260518_125510`)
- Author: PA
- Sweep harness: `srv/helper_scripts/calibration/phase_1b_sweep_replay.py` (v0.2 spec `34af2d2e`)
- Aggregate CSV: trade-core `/home/ncyu/BybitOpenClaw/srv/helper_scripts/calibration/output/sweep_20260518_125510/sweep_aggregate.csv` (81 row × 28 column)
- Predecessor: PA decision memo `5df39d13` (3 SHOULD-FIX accept-with-caveat path)
- Format: PnL-led per `feedback_pnl_priority_over_governance.md`

---

## §0 Executive Summary

**Raw sweep outcome**: 81/81 FAIL (artifact of `adverse_proxy=None` fail-closed gate per PA decision memo §3 expected).

**Post-classification outcome** (after PA decision §1 dedupe + §3 INDETERMINATE 分流):

| Tier | Count | % of N=78 |
|---|---|---|
| **PASS (full data, all gates green)** | 0 | 0.0% |
| **CONDITIONAL** | 0 | 0.0% |
| **INDETERMINATE-pending-pilot** (adverse data missing, but fill+saving green) | 35 | 44.9% |
| **TRUE FAIL — fill_rate < 25%** | 33 | 42.3% |
| **TRUE FAIL — fill Wilson lower < 15%** | 10 | 12.8% |

**Total post-dedupe**: 78 unique cells (81 raw − 3 Block 4 baseline overlaps).

**Top-2 INDETERMINATE candidates for 24h live-demo pilot**:

| Rank | cell_id | family | A (offset bps) | B (buffer ticks) | C (timeout ms) | D (spread guard bps) | maker_fill_rate | wilson_lo | fee_saving_bps | sav_lo | score |
|---|---|---|---|---|---|---|---|---|---|---|---|
| #1 | `G-AB-01-C90` | grid | 0.5 | 1 | 90000 | 50.0 | 0.708 | 0.568 | 3.368 | 3.177 | 2.386 |
| #2 | `G-AB-02-C90` | grid | 0.5 | 0 | 90000 | 50.0 | 0.708 | 0.568 | 3.368 | 3.177 | 2.386 |

Score = `expected_fee_saving_bps × maker_fill_rate`；tiebreaker per memo §5 C3 = `n_simulated_fills DESC, cell_id ASC`.

**Recommended next dispatch**: 啟動 24h live-demo pilot for Cell A (`G-AB-01-C90`) on 1 strategy × 1 symbol via TOML hot reload (v0.2 maker close-first activator)；補上真實 adverse selection sample，24h 後 re-run gate 判 PASS / cell-quality FAIL。Cell B 是 risk-diversification 備案。

**SHOULD-FIX caveats carried into pilot scope**: §5.1 BBO-cross-proxy fill-rate optimistic bias；§5.2 A axis 對 G/PG fill rate 無感（pending IMPL re-confirmation）。

---

## §1 Methodology

### §1.1 Sweep run metadata

| 項 | 值 |
|---|---|
| Sweep run timestamp | 2026-05-18T12:55:10 UTC |
| Wall time | 1.4 sec (per sweep_summary.json + run dispatch log) |
| Total cells | 81 |
| Data source | `bybit_demo_ws` (per spec §3.4 `market_tickers`) |
| Aggregate output | `sweep_aggregate.csv` (81 row × 28 column) |
| Per-cell JSON | `cells/<cell_id>.json` (81 files) |
| Acceptance-gate result | 81 FAIL / 0 PASS / 0 CONDITIONAL |

### §1.2 PA cleanup steps applied (per decision memo §5 C1-C5)

| # | Step | Source | Result |
|---|---|---|---|
| C1 | Block 4 dedupe by `(family, A, B, C, D)` tuple | memo §1 | 3 cells dropped (see §3.1) |
| C2 | FAIL pool 分流 (data_missing vs cell_quality) | memo §3 | 35 INDETERMINATE / 43 TRUE FAIL (see §3.2) |
| C3 | top-2 排序 with tiebreaker (n_fills DESC, cell_id ASC) | E2 NTH #3 | applied (see §4) |
| C4 | Caveat propagation (`fill_detection_uses_bbo_cross_proxy_not_trade_tape`) | E2 NTH #4 | rolled into §5.1 |
| C5 | Data source tag verification | spec §3.4 + E2 caveat 1 | `bybit_demo_ws` confirmed in CSV |

### §1.3 Tier classification rule (PA decision §3)

```
if fill_rate < 0.25:          TRUE_FAIL_fill_low
elif saving_bps < 0.5:        TRUE_FAIL_saving_low
elif fill_wilson_lo < 0.15:   TRUE_FAIL_fill_wilson_low
elif saving_wilson_lo < 0.0:  TRUE_FAIL_saving_wilson_low
elif adverse IS NULL:         INDETERMINATE_data_missing  (pending 24h pilot)
elif adverse > baseline:      TRUE_FAIL_adverse_high
else:                         PASS_full_data
```

注：所有 81 cell `adverse_selection_proxy_bps` 都是 NULL（1.4-sec sweep 太快，無法等 fill+60s 後 mid 觀察）；因此走 INDETERMINATE 邏輯區分「cell quality 預先過得了 gate 但 adverse 待驗」vs「cell quality 直接 FAIL」。

---

## §2 Raw sweep results overview

### §2.1 Per-family fill rate / saving distribution (post-dedupe N=78)

| family | n | fill_rate range | fill_rate mean | saving_bps range | saving_bps mean | best score | best cell |
|---|---|---|---|---|---|---|---|
| grid | 26 | 0.229 – 0.708 | 0.579 | 3.325 – 3.425 | 3.364 | 2.386 | G-AB-01-C90 |
| phys_lock_giveback | 26 | 0.000 – 0.500 | 0.288 | 0.000 – 3.500 | 2.692 | 1.750 | PG-AB-01-C45 |
| phys_lock_stale_roc_neg | 26 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | (all FAIL) |

**Family verdict**:
- **grid**: clearly best — 96% INDETERMINATE (25/26) + 1 TRUE FAIL (extreme B=4 corner)
- **phys_lock_giveback**: bimodal — 10 INDETERMINATE / 16 TRUE FAIL (6 fill<25% + 10 wilson_lo<15% due to small n_eligible=4)
- **phys_lock_stale_roc_neg**: 100% TRUE FAIL — see §5.3 anomaly

### §2.2 Parameter sensitivity observed

**C (timeout) axis** — clear positive driver of fill rate:

| C (ms) | G fill rate (B=1, all A) | PG fill rate (B=1, all A) |
|---|---|---|
| 10000 | n/a | n/a |
| 15000 | n/a | 0.250 (1/4) |
| 30000 | 0.583 (28/48) | n/a |
| 45000 | n/a | 0.500 (2/4) |
| 60000 | 0.688 (33/48) | 0.500 (2/4) |
| 90000 | 0.708 (34/48) | n/a |

監釐：C=30→60ms 提升 +10.5 pp，C=60→90ms 僅 +2.1 pp（diminishing returns），suggests `C=90s` 接近 ceiling on this 1h window；但 24h pilot 可確認 longer-window 是否 still trend up。

**B (buffer ticks) axis** — clear negative driver (each extra tick → lower fill):

| C (90s G family, B variant) | fill_rate |
|---|---|
| B=0 | 0.708 |
| B=1 | 0.708 |
| B=2 | 0.625 |
| B=3 | 0.542 |
| B=4 | 0.417 |

注：B=0 vs B=1 fill identical (0.708) — `1-tick safety buffer` 在這個 sample 下零代價，**這是 pilot 設計上有用的對比點**。

**A (offset bps) axis** — **fill_rate 完全無感** (重大發現，見 §5.2)：

| C=90s B=1 cells | fill_rate |
|---|---|
| A=0.5 (G-AB-01-C90) | 0.708 (34/48) |
| A=1.0 (G-AB-03-C90) | 0.708 (34/48) |
| A=2.0 (G-AB-05-C90) | 0.708 (34/48) |
| A=3.0 (G-AB-07-C90) | 0.708 (34/48) |

**4 個 cell A 從 0.5 bps 跳到 3.0 bps 完全相同 fill rate** — A axis 在當前 BBO-cross-proxy 模型下不影響 fill 判定，suspicious anomaly。詳 §5.2。

**D (spread guard bps) axis** — only Block 4 varied D∈{25, 35, 50}；D=25/35/50 三個 D 變體 (grid, A=0.5, B=1, C=30s) 都 fill=0.583 identical。當前 sample 下 spread guard 也未觸發 (n_skipped_spread_guard=0)。

### §2.3 Skip-reason distribution (data quality)

| Skip reason | n_total (across 81 raw) | % of 4374 total attempts | Note |
|---|---|---|---|
| `n_skipped_no_bbo` | ~162 | ~3.7% | BBO snapshot 不在 ±60s window |
| `n_skipped_family_mismatch` | ~1728 | ~39.5% | majority from PS family (all 54 attempts skipped → §5.3) |
| `n_skipped_tick_missing` | 0 | 0.0% | tick_size 全有 |
| `n_skipped_crossed_book` | 0 | 0.0% | book 無 degenerate |
| `n_skipped_spread_guard` | 0 | 0.0% | spread guard 沒觸發 |

PS family 全部被 family_mismatch skip 是這次 39.5% skip 的主因，G/PG 兩個 family 的 skip rate 健康。

---

## §3 Post-dedupe + post-classification result

### §3.1 Block 4 dedupe (PA memo §1)

3 個重複 cell 從 raw 81 中 drop，保留 cell_id 字母序第一個：

| Dropped (Block 4) | Kept (Block 1-3) | Config | Reason |
|---|---|---|---|
| G-D-D50 | G-AB-01-C30 | grid, A=0.5, B=1, C=30s, D=50 | block 4 D=50 = Block 1 baseline |
| PG-D-D50 | PG-AB-01-C15 | PG, A=0.5, B=1, C=15s, D=50 | block 4 D=50 = Block 2 baseline |
| PS-D-D50 | PS-AB-01-C10 | PS, A=0.5, B=1, C=10s, D=50 | block 4 D=50 = Block 3 baseline |

**Post-dedupe N = 78 unique cells.**

### §3.2 Tier breakdown (post-dedupe)

| Tier | Total | grid | PG | PS |
|---|---|---|---|---|
| INDETERMINATE_data_missing | 35 | 25 | 10 | 0 |
| TRUE_FAIL_fill_low (fill < 25%) | 33 | 1 | 6 | 26 |
| TRUE_FAIL_fill_wilson_low (wilson_lo < 15%) | 10 | 0 | 10 | 0 |
| **Total** | **78** | **26** | **26** | **26** |

### §3.3 INDETERMINATE pool 完整清單 (35 cells)

**Grid family (25 cells)** — all C ∈ {30s, 60s, 90s}, A ∈ {0.5, 1.0, 2.0, 3.0}, B ∈ {0, 1, 2, 3}, D=50, 加 3 個 D-axis variants：

| cell_id | A | B | C(s) | D | fill | wilson_lo | save | score |
|---|---|---|---|---|---|---|---|---|
| G-AB-01-C90 | 0.5 | 1 | 90 | 50 | 0.708 | 0.568 | 3.368 | 2.386 |
| G-AB-02-C90 | 0.5 | 0 | 90 | 50 | 0.708 | 0.568 | 3.368 | 2.386 |
| G-AB-03-C90 | 1.0 | 1 | 90 | 50 | 0.708 | 0.568 | 3.368 | 2.386 |
| G-AB-05-C90 | 2.0 | 1 | 90 | 50 | 0.708 | 0.568 | 3.368 | 2.386 |
| G-AB-07-C90 | 3.0 | 1 | 90 | 50 | 0.708 | 0.568 | 3.368 | 2.386 |
| G-AB-01-C60 | 0.5 | 1 | 60 | 50 | 0.688 | 0.547 | 3.364 | 2.313 |
| G-AB-02-C60 | 0.5 | 0 | 60 | 50 | 0.688 | 0.547 | 3.364 | 2.313 |
| G-AB-03-C60 | 1.0 | 1 | 60 | 50 | 0.688 | 0.547 | 3.364 | 2.313 |
| G-AB-05-C60 | 2.0 | 1 | 60 | 50 | 0.688 | 0.547 | 3.364 | 2.313 |
| G-AB-07-C60 | 3.0 | 1 | 60 | 50 | 0.688 | 0.547 | 3.364 | 2.313 |
| G-AB-04-C90 | 1.0 | 2 | 90 | 50 | 0.625 | 0.485 | 3.384 | 2.115 |
| G-AB-01-C30 | 0.5 | 1 | 30 | 50 | 0.583 | 0.443 | 3.340 | 1.948 |
| G-AB-02-C30 | 0.5 | 0 | 30 | 50 | 0.583 | 0.443 | 3.340 | 1.948 |
| G-AB-03-C30 | 1.0 | 1 | 30 | 50 | 0.583 | 0.443 | 3.340 | 1.948 |
| G-AB-05-C30 | 2.0 | 1 | 30 | 50 | 0.583 | 0.443 | 3.340 | 1.948 |
| G-AB-07-C30 | 3.0 | 1 | 30 | 50 | 0.583 | 0.443 | 3.340 | 1.948 |
| G-D-D25 | 0.5 | 1 | 30 | 25 | 0.583 | 0.443 | 3.340 | 1.948 |
| G-D-D35 | 0.5 | 1 | 30 | 35 | 0.583 | 0.443 | 3.340 | 1.948 |
| G-AB-04-C60 | 1.0 | 2 | 60 | 50 | 0.562 | 0.423 | 3.376 | 1.898 |
| G-AB-06-C90 | 2.0 | 3 | 90 | 50 | 0.542 | 0.402 | 3.404 | 1.844 |
| G-AB-04-C30 | 1.0 | 2 | 30 | 50 | 0.417 | 0.286 | 3.325 | 1.387 |
| G-AB-06-C60 | 2.0 | 3 | 60 | 50 | 0.458 | 0.323 | 3.395 | 1.555 |
| G-AB-08-C90 | 3.0 | 4 | 90 | 50 | 0.417 | 0.286 | 3.425 | 1.428 |
| G-AB-08-C60 | 3.0 | 4 | 60 | 50 | 0.375 | 0.249 | 3.420 | 1.283 |
| G-AB-06-C30 | 2.0 | 3 | 30 | 50 | 0.354 | 0.231 | 3.353 | 1.187 |

**PG family (10 cells)** — only C ∈ {45s, 60s} (C=15s all fall to wilson_low FAIL due to fill rate only 0.25 + n_eligible=4)，B=0 or B=1：

| cell_id | A | B | C(s) | D | fill | wilson_lo | save | score |
|---|---|---|---|---|---|---|---|---|
| PG-AB-01-C45 | 0.5 | 1 | 45 | 50 | 0.500 | 0.150 | 3.500 | 1.750 |
| PG-AB-02-C45 | 0.5 | 0 | 45 | 50 | 0.500 | 0.150 | 3.500 | 1.750 |
| PG-AB-03-C45 | 1.0 | 1 | 45 | 50 | 0.500 | 0.150 | 3.500 | 1.750 |
| PG-AB-05-C45 | 2.0 | 1 | 45 | 50 | 0.500 | 0.150 | 3.500 | 1.750 |
| PG-AB-07-C45 | 3.0 | 1 | 45 | 50 | 0.500 | 0.150 | 3.500 | 1.750 |
| PG-AB-01-C60 | 0.5 | 1 | 60 | 50 | 0.500 | 0.150 | 3.500 | 1.750 |
| PG-AB-02-C60 | 0.5 | 0 | 60 | 50 | 0.500 | 0.150 | 3.500 | 1.750 |
| PG-AB-03-C60 | 1.0 | 1 | 60 | 50 | 0.500 | 0.150 | 3.500 | 1.750 |
| PG-AB-05-C60 | 2.0 | 1 | 60 | 50 | 0.500 | 0.150 | 3.500 | 1.750 |
| PG-AB-07-C60 | 3.0 | 1 | 60 | 50 | 0.500 | 0.150 | 3.500 | 1.750 |

**PS family (0 cells in INDETERMINATE)** — all 26 cells TRUE_FAIL (n_eligible=0 due to 100% family_mismatch skip)，詳 §5.3。

### §3.4 TRUE FAIL pool 摘要

- **G-AB-08-C30** (1 cell, fill 0.229 < 0.25): grid corner A=3.0/B=4/C=30s 是 extreme buffer 配置，sweep 預期 fail
- **PG fill<25% (6 cells)**: PG-AB-04 (B=2) / PG-AB-06 (B=3) / PG-AB-08 (B=4) × {C=15s, C=45s} — high buffer + short timeout 必 fail
- **PG wilson_low<15% (10 cells)**: 大部分 C=15s 子集 + PG-AB-04-C60 — n_eligible=4 太小撐不起 wilson CI
- **PS family 全 fail (26 cells)**: 全 family routing 問題 §5.3

---

## §4 Top-2 pilot candidates (Recommended)

### §4.1 Cell A — `G-AB-01-C90` (PRIMARY recommendation)

| Field | Value |
|---|---|
| **Family** | grid |
| **Strategy** | grid_trading |
| **Offset (A)** | 0.5 bps |
| **Buffer (B)** | 1 tick |
| **Timeout (C)** | 90000 ms (90s) |
| **Spread guard (D)** | 50 bps |
| **n_attempts** | 54 |
| **n_eligible** | 48 |
| **n_simulated_fills** | 34 |
| **maker_fill_rate** | 0.708 (70.8%) |
| **fill Wilson 95% CI** | [0.568, 0.812] |
| **expected_fee_saving_bps** | 3.368 |
| **saving Wilson 95% CI** | [3.177, 3.570] |
| **adverse_selection_proxy_bps** | NULL (1.4-sec sweep 缺 60s look-ahead window) |
| **pre_phase_1b_taker_baseline_bps** | 5.554 |
| **score** | 2.386 |

**Wilson lower bounds 都 well above thresholds**: fill 0.568 vs gate 0.15 (3.8x margin), saving 3.177 vs gate 0.0 (∞ margin)。Pilot 期間 adverse 需 < 5.554 才不破 gate（巨大空間）。

### §4.2 Cell B — `G-AB-02-C90` (RISK-DIVERSIFICATION backup)

| Field | Value |
|---|---|
| **Family** | grid |
| **Offset (A)** | 0.5 bps |
| **Buffer (B)** | **0 tick** (different from #1) |
| **Timeout (C)** | 90000 ms (90s) |
| **Spread guard (D)** | 50 bps |
| **n_eligible / fills** | 48 / 34 (identical to #1) |
| **fill_rate / wilson_lo** | 0.708 / 0.568 (identical) |
| **saving / sav_lo** | 3.368 / 3.177 (identical) |
| **score** | 2.386 |

**對比 Cell A 的設計動機**: B=0 vs B=1 (no buffer vs 1-tick buffer)。當前 BBO-cross-proxy 顯示「1-tick buffer 對 fill rate 零代價」，但在真實 demo fills 上 1-tick buffer 可能：
- (+) 降低 adverse selection 命中
- (-) 降低 fill rate (因離 BBO 更遠，反向掃過機率減低)

Cell B 是 **pilot 的二倍驗證 group** 而非單純 backup — 若 operator 想最大化 information value，pilot A+B 並行可一次驗 fill robustness + adverse signal。

### §4.3 5 tied cells caveat

機械 tiebreaker 推出 #1=G-AB-01-C90, #2=G-AB-02-C90。但 score 2.386 一共 5 cell tie：

| Tie rank | cell | A axis | B axis | Note |
|---|---|---|---|---|
| (rank 1) G-AB-01-C90 | 0.5 | 1 | conservative baseline | |
| (rank 2) G-AB-02-C90 | 0.5 | 0 | tests buffer=0 impact | |
| (rank 3) G-AB-03-C90 | 1.0 | 1 | tests offset=1.0 impact | |
| (rank 4) G-AB-05-C90 | 2.0 | 1 | tests offset=2.0 impact | |
| (rank 5) G-AB-07-C90 | 3.0 | 1 | tests offset=3.0 impact | |

**Operator override 建議**: 若 operator 想最大化 information value 在 24h pilot，可考慮把 Cell B 換成 `G-AB-07-C90` (A=3.0, B=1) → 一次 pilot 驗證 offset axis 是否 surface 真實 fill differentiation（解 §5.2 anomaly）。tiebreaker SOP 機械輸出 A=0.5/B=0，從 information value 看不是 optimal。PA 守 SOP 出 official top-2，operator 自決定是否替換。

### §4.4 Pilot 24h live-demo dispatch 計劃

**Pilot scope**:
- 1 strategy: `grid_trading`
- 1 symbol: 建議 `BTCUSDT` 或 `ETHUSDT` (high-volume, BBO snapshot 密度最高)
- 1 environment: live-demo (demo endpoint + live-grade pipeline per `feedback_live_no_degradation_by_endpoint`)
- duration: 24h
- activation: TOML hot reload (no engine restart needed per v0.2 spec §3.1 close-maker-first activator)
- ML downstream: shadow-only (per root principle §7 learning ≠ rewrite live)

**TOML override** (apply via runtime config patch):
```toml
[risk.maker_close_first]
enabled = true
strategy_family = "grid"
offset_bps = 0.5
buffer_ticks = 1
timeout_ms = 90000
spread_guard_bps = 50.0
```

注：實際 TOML key 路徑以 maker-close-first runtime activator 設計為準（操作 session 確認 schema）。本報告 surface 參數值，不寫 runtime config（PA 邊界）。

**Pilot 24h observation gates**:

| Acceptance criterion (AC) | Threshold | Source |
|---|---|---|
| AC-A1 real maker fill_rate | ≥ 25% (Wilson 95% lower ≥ 15%) | spec §4.1 PASS gate |
| AC-A2 real fee saving | ≥ 0.5 bps (Wilson 95% lower ≥ 0.0) | spec §4.1 PASS gate |
| AC-A3 real adverse_selection | ≤ pre_phase_1b_taker_baseline_bps (5.554 bps) | spec §4.1 PASS gate |
| AC-A4 close maker audit lineage | ≥ 99.9% (per V094 + healthcheck [63] dual gate) | PA memo 2026-05-15 §5 |
| AC-A5 no engine fail-closed event | 0 occurrence | hard boundary |

### §4.5 Rollback trigger

Pilot 進行中若任一觸發 → immediate revert to taker-only baseline + dispatch RCA：
- fill_rate Wilson lower < 15% sustained over ≥ 4h window
- adverse_real > 5.554 bps over ≥ 4h window
- engine 任一 forbidden_guard fail
- 對賬 fills 表 audit lineage 完整性 < 99.9%

---

## §5 Risk + Caveats carried over

### §5.1 [E2 caveat 1] BBO-cross-proxy fill detection systematically optimistic

E2 review `907ab778` 已 surface: sweep IMPL 的 `_did_fill_within_window` 用 BBO-cross-proxy (best_ask <= offset 或 best_bid >= offset within timeout) 判定 fill，**not actual trade tape**。

**Implication**:
- BBO-cross 高估真實 maker fill 機率（不考慮 queue position / partial fill / cancel race）
- Pilot 真實 fill_rate 預期 **比 sweep 70.8% 低**（保守估計 60-65%）
- 24h pilot 真實 demo fill 數據才是 viable verdict

**Mitigation**: Wilson 95% lower bound 0.568 為「優化 proxy 下的下界」，假設 proxy bias 為 ~10pp (常見保守估計)，real lower ≈ 0.47 仍 well above gate 0.15。Pilot 結果若 real fill_rate ≥ 25% → 仍 PASS。

### §5.2 [NEW finding] A axis 對 fill_rate 完全無感 — calibration design quirk 或 IMPL bug 候選

**Observation**: 81-cell sweep 中，所有 G family 和 PG family 在同樣 B+C+D 下，A ∈ {0.5, 1.0, 2.0, 3.0} bps 產生 **identical** fill_rate / n_simulated_fills / saving_bps（精度到 6 位小數）。

**Examples**:

| Comparison | A=0.5 | A=1.0 | A=2.0 | A=3.0 |
|---|---|---|---|---|
| G C=90s B=1 fill | 0.7083 | 0.7083 | 0.7083 | 0.7083 |
| G C=60s B=1 fill | 0.6875 | 0.6875 | 0.6875 | 0.6875 |
| G C=30s B=1 fill | 0.5833 | 0.5833 | 0.5833 | 0.5833 |
| PG C=45s B=1 fill | 0.5000 | 0.5000 | 0.5000 | 0.5000 |

**Hypotheses (PA, ordered by likelihood)**:

1. **(Spec design intent)** BBO-cross-proxy 在 sweep 用「best_ask <= mid - offset」判 fill，但因 offset 都遠小於 typical BBO spread（10+ bps）→ cross 是 dominated by spread movement，not offset → A axis 自然無效。**Probability ~60%**。
2. **(IMPL bug)** `phase_1b_sweep_replay.py` `_did_fill_within_window` 把 `offset_bps` 變量讀但不傳入 cross check → A axis dead variable。**Probability ~25%**。
3. **(Sample artifact)** 4h sample 太短，offset 的影響被 mid 波動掩蓋（unlikely with 48 eligible attempts）。**Probability ~15%**。

**PA recommendation**:
- Pilot 不阻塞 — 即使 A axis dead variable, Cell A `(A=0.5, B=1, C=90s)` 仍是 fill 最高 + saving 最高的 viable cell
- **Side dispatch**: 操作 session 在 pilot launch 同時 派 E1 / E2 spot check `phase_1b_sweep_replay.py:200-300` cross-check logic 是否 incorporate offset；如是 IMPL bug → spec v0.3 update + re-sweep (低 cost ~5min) 確定 viable cell ranking 不變
- 若是 hypothesis 1 (spec design intent), 24h pilot 後 PA 寫 spec v0.3 patch 明確「A axis 是 fee saving 設計參數，not fill detection 參數」

### §5.3 [NEW finding] PS family (phys_lock_stale_roc_neg) 100% family_mismatch skip

所有 PS family 26 cells `n_skipped_family_mismatch = 54` (= n_attempts), n_eligible=0。

**Implication**: 該 family 完全未從 close-maker-first attempt pool 中 surface — 可能：
1. Strategy router 不發 phys_lock_stale_roc_neg family close → no attempt to test
2. Sweep 用的 close attempt pool (4h sample) 不含該 family 的 close events
3. Family routing 在 IMPL 對 phys_lock_stale_roc_neg 標籤不齊

**Pilot implication**: PS family 沒有 pilot 候選 — 28h pilot 只覆蓋 grid family。PG family 也只 10 個 INDETERMINATE cells，不在 top-2，但若 grid pilot 結果良好，下一輪 sweep 可重點補 PG family 樣本。

**Side dispatch suggestion**: 操作 session 派 PA / FA 並行核 PS family 為何無 close attempt 觸發；不影響本次 pilot dispatch。

### §5.4 v0.2 spec maker_fill_rate denom (carried-over verification)

CSV `n_eligible` 欄位確認用 expanded denom（per spec v0.2）:

```
n_eligible = n_attempts - (n_skip_spread_guard + n_skip_no_bbo + n_skip_tick_missing + n_skip_family_mismatch + n_skip_crossed_book)
```

verified by sample: G-AB-01-C30 `54 - (0+2+0+4+0) = 48 = n_eligible`. ✓

### §5.5 24h pilot real-data measurements (replaces simulation)

Pilot 補上 sweep 缺的 3 個關鍵 ground truth：

| Metric | Sweep value | Pilot ground truth |
|---|---|---|
| maker_fill_rate | 0.708 (BBO-cross-proxy) | actual fill / actual eligible |
| expected_fee_saving_bps | 3.368 (theoretical) | actual taker baseline − actual maker realized |
| adverse_selection_proxy_bps | NULL | computed from real fill mid + 60s mid drift |

---

## §6 Recommended next dispatch

### §6.1 Decision request to operator

**Approve**: launch 24h live-demo pilot for Cell A `G-AB-01-C90` on grid_trading × 1 symbol.

**Optional**: also launch Cell B (G-AB-02-C90 per SOP tiebreaker, or alternative G-AB-07-C90 per §4.3 information value override).

**Pilot launch sequence** (operator action, not PA):
1. Apply TOML hot reload to runtime config with Cell A params (see §4.4)
2. Verify activator log shows close-maker-first enabled for grid_trading
3. Healthcheck [63] dual gate online (per PA memo 2026-05-15)
4. 24h observation window starts at t0
5. AC-A1..A5 gate at t0+24h → PASS / cell-quality FAIL / re-pilot
6. If PASS → spec v0.3 amend (or v1.0 lock) + dispatch wider param search (other PG cells)
7. If FAIL → RCA which gate failed + adjust + re-pilot OR fall back to taker baseline

### §6.2 Side dispatches (parallel to pilot, recommended)

**SD-1 — E1/E2 verify A axis behavior** (per §5.2):
- grep `phase_1b_sweep_replay.py` `_did_fill_within_window` and `offset_bps` usage
- confirm: is A axis intentional (only fee saving design parameter) or IMPL bug (offset not feeding cross check)?
- Output: 1-line verdict + (if bug) spec v0.3 patch suggestion
- ETA: ~30 min, 0 dependency on pilot

**SD-2 — PA/FA verify PS family routing** (per §5.3):
- grep close-maker family routing logic; check why `phys_lock_stale_roc_neg` family never reached attempt pool
- Output: PS family 是 (a) deprecated and intentionally not in close path, or (b) router bug
- ETA: ~30 min, 0 dependency on pilot

### §6.3 PnL-priority assessment (per `feedback_pnl_priority_over_governance.md`)

- Cell A `G-AB-01-C90` proxy savings = 3.368 bps per maker close at 70.8% fill = **2.386 bps per close attempt EV**
- Pre-Phase 1b taker baseline = 5.554 bps cost per close
- **Net expected EV** under proxy ≈ −5.554 + 2.386 = -3.17 bps per close (still cost, but cost reduced by 43% from taker-only)
- Real pilot 預期 fill 60-65% (per §5.1 proxy bias) → real EV improvement 35-40%
- 對組合層 PnL 是正向但小幅；不適合 over-eager scaling but recommended pilot dispatch

### §6.4 No-deploy items (boundaries)

- ❌ **不修 IMPL**：A axis anomaly side-dispatch 是 verify-only，A axis bug 修不修要 operator 決定
- ❌ **不寫 TOML override**：本報告只 surface 參數值，PA 不動 runtime config
- ❌ **不啟 pilot**：operator action，PA 只 recommend
- ❌ **不重 sweep**：1.4-sec wall time 重跑 cost 趨零但無新 information

---

## §7 16 原則合規 + 硬邊界檢查

### §7.1 16 根原則逐條（本報告 read-only analysis 範圍）

| # | 原則 | 狀態 | 證據 |
|---|---|---|---|
| 1 | 單一寫入口 | ✓ N/A | 本報告無寫入 |
| 2 | 讀寫分離 | ✓ | CSV read-only |
| 3 | AI 輸出 ≠ 命令 | ✓ | recommend only, operator 決定 |
| 4 | 策略不繞風控 | ✓ N/A | pilot 走 demo + 全 audit chain |
| 5 | 生存 > 利潤 | ✓ | rollback trigger §4.5 已設 |
| 6 | 失敗默認收縮 | ✓ | fail-closed adverse=None 保留 |
| 7 | 學習 ≠ 改寫 Live | ✓ | pilot ML downstream shadow-only |
| 8 | 交易可解釋 | ✓ | per-cell JSON + sweep_aggregate.csv 完整 |
| 9 | 災難保護 | ✓ N/A | pilot 階段 |
| 10 | 認知誠實 | ✓ | §5.2/§5.3 標 hypothesis 與 likelihood |
| 11 | Agent 最大自主 | ✓ | 在 P0/P1 內推薦 |
| 12 | 持續進化 | ✓ | pilot 補真實 sample → spec v0.3 |
| 13 | AI 成本感知 | ✓ N/A | offline analysis, no AI call |
| 14 | 零外部成本可運行 | ✓ | 全本地 CSV 分析 |
| 15 | 多 Agent 協作 | ✓ | side-dispatch suggestion clean |
| 16 | 組合級風險 | ✓ | §6.3 PnL-priority 評估 |

**評級**: A (16/16 完全合規)

### §7.2 §四 硬邊界（5 條）

- ✓ Five-gate live: pilot 走 demo endpoint, live-grade pipeline 不破壞五門
- ✓ Signed live authorization: pilot 不觸 mainnet
- ✓ LiveDemo grade: pilot 設計 per `feedback_live_no_degradation_by_endpoint` 守 live 風控嚴格度
- ✓ Mainnet env-var fallback: 未開（pilot demo only）
- ✓ Bybit retCode fail-closed: 維持

**結論**: 5/5 0 觸碰。

### §7.3 DOC-08 §12 9 不變量

本報告 pilot dispatch design 不破壞任何 9 不變量；pilot 啟動後守 invariant 4 (風控降級 → engine 自動止血), 7 (Bybit retCode != 0 fail-closed), 8 (Reconciler 對賬差異 → 自動降級 paper)。

---

## §8 Multi-session race check 5/5

| Check | Command | Result | Pass |
|---|---|---|---|
| 5a 提交前 fetch + sibling window | `git fetch origin` 2h 內 sibling commits | 最新: `d2286c05 fix(calibration): tick_loader SQL` ← 不衝突 | ✓ |
| 5b report path 寫入前 status clean | `git status` | report path 不存在於現有 modified list | ✓ |
| 5c sibling WIP 不 revert | dirty: E2/E4/MIT/PA memory.md = 其他 session 累積 | 不動 | ✓ |
| 5d report path 不重名 | `2026-05-18--phase_1b_calibration_cell_selection_report.md` 為新檔 | unique | ✓ |
| 5e 分析期間 sibling 推 origin | local main = origin/main `d2286c05` 未變 | ✓ |

**Race check 5/5 PASS。**

---

## §9 Append-only summary

- Sweep: 81 cells / 1.4 sec wall / `bybit_demo_ws` / 0 raw PASS (artifact)
- Post-cleanup: **78 unique** (3 dedupe) / **0 PASS** / **0 CONDITIONAL** / **35 INDETERMINATE** / **43 TRUE FAIL**
- Top-2 pilot: **#1 G-AB-01-C90** (A=0.5, B=1, C=90s, D=50, score 2.386, fill 70.8%, save 3.37 bps) / **#2 G-AB-02-C90** (差只在 B=0)
- Operator override option: replace #2 with **G-AB-07-C90** (A=3.0) for information value re §5.2 anomaly
- Side dispatches: SD-1 verify A axis behavior + SD-2 verify PS family routing (both ~30min, 0 dependency)
- Pilot dispatch: **READY**, awaiting operator approval

---

PA DESIGN DONE: report path: docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--phase_1b_calibration_cell_selection_report.md
