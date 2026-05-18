# Phase 1b Calibration Sweep — Spec

**Date**: 2026-05-18
**Author**: PA (Project Architect) — pre-prep design during 12H post-deploy test window observation-only block；spec design ≠ parameter change，符合 read-only constraint
**Status**: SPEC v0.1 DRAFT — pending PM sign-off + main session commit；NOT YET dispatched to E1
**Phase**: EDGE-P2-3 Phase 1b post-deploy parameter calibration（spec v1.3 IMPL 已 live；activator commit `18081551`；T+12H QA observation 顯示 4/4 close_maker_attempt 全 `fallback_reason=timeout_taker` = 0% maker fill = $0 fee saving）

**Supersedes / extends**:
- Phase 1b spec v1.3 `docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md` 為 IMPL SoT；本 spec 不改 spec v1.3，僅 propose parameter calibration sweep 以 unlock §1.2 預期 $50-200/year fee saving
- E2 RCA `docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-18--phase_1b_timeout_taker_rca.md` §3 5 條對抗性 hypothesis verdict + §4 Tune-1/2/3 建議 — 本 spec 是 PA 對 E2 §4 建議的 calibration 化收斂
- v48 TODO P0-PHASE-1B-PARAM-CALIBRATION-1 row (commit `eebda658`) — 6-step dispatch sequence + acceptance threshold SoT
- Phase 2c-CM counterfactual harness spec `docs/execution_plan/2026-05-18--phase_2c_livedemo_counterfactual_harness_spec.md` — 完全 orthogonal（Phase 2c-CM 是 LiveDemo 7d gate at fixed config；本 spec 是 Demo parameter tuning at pre-LiveDemo phase）

**對應 spec / TODO / memory**:
- P0-EDGE-1 / EDGE-P2-3 Phase 1b / DOC-01 §5.6 §5.9 / DOC-08 §12
- memory `feedback_pnl_priority_over_governance.md`（PnL-led framing；calibration 是 parameter tuning 不需 4-agent heavy review）
- memory `feedback_demo_loose_live_strict_policy.md`（Demo 是學習資料源可放寬）
- memory `feedback_v_migration_pg_dry_run.md`（本 spec 0 migration → 不適用）

---

## §0 Executive Summary（PnL-led，per `feedback_pnl_priority_over_governance.md`）

### 0.1 Problem Statement

Phase 1b runtime activator (commit `18081551`) T+12H 觀察：4/4 `close_maker_attempt=TRUE` rows 全 `fallback_reason=timeout_taker`，maker fill = **0%**，fee saving = **$0**。Code path 工作正常（state machine + cancel + fallback 100% per spec §5.2 Race B + §5.5 mandatory fallback），**root cause = parameter tuning, NOT IMPL bug**（E2 RCA §0 verdict HIGH confidence）。當前 TOML 全 8 個 whitelisted exit_reason 使用 `buffer_ticks=1 / offset_bps=0.5 / timeout_ms=30s/15s/10s` 一致參數，spec §1.2 line 44 conservative range 預估 close fill rate `15-25%`，0/4 在小 n 統計噪音 lower-bound 內，但 PnL impact 為零 → 需 calibration sweep 找 viable cell。

### 0.2 Target Outcome

依 v48 P0 acceptance threshold：

> ≥1 viable parameter cell with `maker_fill_rate ≥ 25%` AND `expected_fee_saving_bps ≥ 0.5` AND zero adverse selection signal (no `slippage_after_quote_move` > pre-Phase-1b baseline)

達標時解鎖 spec §1.2 預估 `$50-$200/year` Bybit fee saving（保守 range，per E3 empirical baseline `2026-05-15--maker_fill_rate_empirical_baseline.md`），對應 5 textbook 策略 30d net loss `-110.43 USDT (demo) / -27.31 USDT (live_demo)` 的執行成本掩蓋層（不救 alpha deficit 但消除 maker-vs-taker 噪音 → P0-EDGE-1 edge measurement 更乾淨）。

### 0.3 Why this moves PnL（per memory `feedback_pnl_priority_over_governance.md`）

- 當前 100% timeout = 0 maker fill = $0 fee saving = **0 PnL impact** of the entire Phase 1b activator deployment
- Calibration unlock ≥25% fill rate × 3.5 bps fee saving cap × ~150 close/week 系統 rate ≈ +$0.13/week direct fee saving + indirect edge measurement cleanup
- 路徑性質 = parameter tuning（已有 §1.2 預測 fee saving range + AC-19 14d gate），**非 architectural change** → 不需 4-agent heavy；light PA design → E1 replay harness IMPL → E2/E4/QA sign-off 即可
- 為何不等 T+72h n≥30 統計收斂（E2 §0 verdict）：operator override per v48 P0 row + memory framing — calibration sweep 自己會產 sample，不必先等 single-cell sample 收斂後才動

### 0.4 ETA Total

| 階段 | Owner | 估算 | 並行性 |
|---|---|---|---|
| §1 sweep matrix design | PA (this spec) | DONE | — |
| §2 replay harness IMPL | E1 | ~2 pd | 1 worktree |
| §3 sweep execution | E1 / batch | ~0.5 pd | 並行可，視 cell 數 |
| §4 acceptance gate + cell selection | PA + QA | ~0.5 pd | sequential |
| §5 operator pilot dispatch (1-2 cell × 24h live-demo) | operator + QA | 1d wall + 0.5 pd 監控 | sequential |
| §6 E4 regression | E4 | ~0.5 pd | 並行於 pilot |
| §7 PM sign-off + merge + restart | PM | ~0.2 pd | sequential |

**Total person-day estimate**: **3-5 pd**，wall-clock ~3-5 天（含 pilot 24h hold）。

---

## §1 Sweep Cell Matrix

### 1.1 Parameter Axes

依 v48 sweep dimensions + E2 RCA §4 Tune-1/2/3 + spec §4.2 baseline 統合，**4 維度**：

| Axis | Symbol | v48 寬向 values | E2 §4 內側向 values | Baseline (current) | Total per dimension |
|---|---|---|---|---|---|
| **A.** `offset_bps` | A | {1.0, 2.0, 3.0} | (none — 內側方向不適用 offset) | 0.5 | 4 (含 baseline) |
| **B.** `buffer_ticks` | B | {2, 3, 4} | {0} | 1 | 5 (含 baseline) |
| **C.** `timeout_ms` (grid family) | C-grid | {60000, 90000} | (none — extend only) | 30000 | 3 (含 baseline) |
| **C.** `timeout_ms` (phys_lock_gate4_giveback) | C-pl | {45000, 60000} | (none) | 15000 | 3 (含 baseline) |
| **C.** `timeout_ms` (phys_lock_gate4_stale_roc_neg) | C-pl-stale | {30000, 45000} | (none) | 10000 | 3 (含 baseline) |
| **D.** `CLOSE_MAKER_SPREAD_GUARD_BPS` | D | {25, 35} (E2 Tune-3 tighter) | (none — guard 朝 tighter 單向) | 50 | 3 (含 baseline) |

**v48 vs E2 axis 衝突的決議**（task ask 顯式要求）：

- v48 `buffer_ticks → {2,3,4}` 方向 = **更被動，朝 outside book 走** → 預期 fill rate ↓ 但 PostOnly reject 安全
- E2 Tune-1 `buffer_ticks → 0` 方向 = **AT inside book** → 預期 fill rate ↑ 但 PostOnly reject volume +
- **PA 決議：兩方向都試**，因為：
  1. 兩方向都是 1-LOC config 改動，sweep cost 邊際幾乎為零
  2. v48 寬向假設「demo 低流動性 → 等行情移過 1 tick 後成交」；E2 內側向假設「demo book 厚度不夠 → 同價 maker 才會被 taker hit」— 兩個假設都 plausible
  3. 寬向 + offset 寬化（`offset_bps={1.0,2.0,3.0}`）= 把 limit 放更遠，等 BBO 移過來；內側向（`buffer_ticks=0`）= 同價 maker 等 taker hit；**這是兩個不同的成交機制**
  4. E2 警告「buffer=0 增 PostOnly reject volume」用 **D 軸 spread_guard tighter** 補償（wide-spread book 跳過 maker → reduce reject 機會）

### 1.2 Full Cartesian Cell Count（pre-prune）

5 grid-family exit_reason × A(4) × B(5) × C-grid(3) × D(3) = 5 × 4 × 5 × 3 × 3 = **900 cells**
2 phys_lock exit_reason × A(4) × B(5) × C-pl/C-pl-stale(3) × D(3) = 2 × 4 × 5 × 3 × 3 = **360 cells**
1 bb_breakout family（bw_squeeze + pctb_revert merged AC carve-out cell）× ... 同 grid = **180 cells**

**Total pre-prune ≈ 1440 cells**。**遠 > task ask 100 cell ideal / 200 cell hard limit**，必 prune。

### 1.3 Prune 策略（必執行）

#### Prune Rule 1: Per-exit_reason scope
- **grid family**（grid_close_short / grid_close_long / bb_mean_revert / ma_reverse_cross / bw_squeeze / pctb_revert）共用 grid-baseline policy（spec §4.2 `buffer=1 offset=0.5 timeout=30000`）→ **合併 sweep**，每 cell 跨所有 grid-family exit_reason
- **phys_lock_gate4_giveback**（spec §4.2 `timeout=15000` 因 unfavourable drift bias）→ 獨立 sweep
- **phys_lock_gate4_stale_roc_neg**（spec §4.2 `timeout=10000` 因 ROC<0 + stale）→ 獨立 sweep
- **削減量**：grid family 6 → 1 + phys_lock 2 keep → **3 family**

#### Prune Rule 2: Axis D (spread_guard) decoupled from main grid
- D 軸（spread_guard 25/35/50）對 fill rate 影響弱（只跳過 wide-spread cell，不影響 narrow-spread book），主效應在 reject volume
- **獨立評估 D 軸**：固定 baseline A/B/C × D{25, 35, 50} = 3 cells per family × 3 families = **9 cells**
- **主 sweep prune D**：固定 D=50 baseline
- 削減量：1440 / 3 = 480 cells

#### Prune Rule 3: Axis A × B interaction reduction
- offset_bps 寬化 + buffer_ticks 寬化 同向（兩個都 increase passive distance）→ partial redundancy
- **保留 A × B full cartesian 但取對角 + 邊**：
  - Conservative wide（passive 增加）：A∈{0.5, 2.0}, B∈{1, 3}
  - Aggressive narrow（內側）：A∈{0.5}, B∈{0}
  - Mid-spectrum：A∈{1.0}, B∈{2}
  - = ~7-8 (A, B) combinations per family（取代 4×5=20 full grid）
- 削減量：480 / (20/8) → ~192 cells

#### Prune Rule 4: Axis C (timeout) coarse-grain
- C-grid: 3 values {30, 60, 90}s → keep all 3（E2 §4 Tune-2 重要 axis）
- C-pl: 3 values {15, 45, 60}s → keep all 3
- C-pl-stale: 3 values {10, 30, 45}s → keep all 3

### 1.4 Pruned Cell Matrix（final）

#### Block 1: Grid family A×B sweep (timeout C-grid baseline 30s, spread_guard D baseline 50bps)

| Cell ID | A offset_bps | B buffer_ticks | direction |
|---|---|---|---|
| G-AB-01 | 0.5 (baseline) | 1 (baseline) | baseline anchor |
| G-AB-02 | 0.5 | 0 | E2 Tune-1 inside |
| G-AB-03 | 1.0 | 1 | v48 mid offset, baseline buffer |
| G-AB-04 | 1.0 | 2 | v48 mid wide |
| G-AB-05 | 2.0 | 1 | v48 wide offset |
| G-AB-06 | 2.0 | 3 | v48 wide × wide |
| G-AB-07 | 3.0 | 1 | v48 max offset |
| G-AB-08 | 3.0 | 4 | v48 max × max wide |

**8 cells × 3 timeout C-grid values {30, 60, 90}s = 24 cells** for grid family A×B×C

#### Block 2: Phys_lock_gate4_giveback A×B sweep (timeout C-pl values)

同 Block 1 (A×B) 8 combos × 3 timeout C-pl {15, 45, 60}s = **24 cells**

#### Block 3: Phys_lock_gate4_stale_roc_neg A×B sweep

同 Block 1 (A×B) 8 combos × 3 timeout C-pl-stale {10, 30, 45}s = **24 cells**

#### Block 4: Spread guard D decoupled sweep（baseline A=0.5, B=1, C=baseline per family）

3 families × 3 D values {25, 35, 50}（含 baseline 50） = **9 cells**

#### Total = 24 + 24 + 24 + 9 = **81 cells**

≤ task ask 100 cell ideal target，**通過 prune 邊界**。

### 1.5 Per-cell expected outcome（先驗 quantitative estimate）

依 spec §1.2 conservative range + E3 empirical baseline + E2 §3 hypothesis verdict：

| Cell archetype | Expected maker_fill_rate | Expected fee_saving_bps | Likely PASS gate? |
|---|---|---|---|
| **Baseline G-AB-01 (0.5/1)** | 0-15% (current observation 0/4 = 0%) | <0.3 bps | UNLIKELY |
| **G-AB-02 inside book (0.5/0)** | 25-40%（E2 Tune-1 預估 +5-15% uplift） | 0.5-1.5 bps | LIKELY |
| **G-AB-03/04 v48 mid (1.0)** | 10-20% | 0.3-0.7 bps | MARGINAL |
| **G-AB-05/06 v48 wide (2.0)** | 5-15%（更被動，等更大行情移動）| 0.2-0.5 bps | UNLIKELY |
| **G-AB-07/08 v48 max (3.0)** | <5%（過於被動）| <0.2 bps | FAIL |
| **+C timeout 60s/90s** | 上方 fill rate +5-10%（更長等待） | +0.2-0.4 bps | upgrade MARGINAL → LIKELY |
| **D spread_guard 25bps** | 同上 fill rate +2-5%（跳過 hopeless cell） | +0.1-0.3 bps | minor uplift |

**核心 prior**：B-axis inside (buffer_ticks=0) + timeout extension 60s 是 most-likely viable region（E2 Tune-1 + Tune-2 結合，spread guard tighter D=25bps 作為 reject 降低補償）。

### 1.6 PnL Impact per Cell（per memory framing）

- **每 cell expected PnL uplift**（vs baseline 0% fill）= fill_rate × 3.5 bps × ~150 close/week × $300 avg notional ≈ fill_rate × **$0.16/week**
- 25% fill rate cell → ~$0.04/week × 52 = **$2.08/year per strategy** × ~5 strategies ≈ $10/year direct
- 結合 indirect edge measurement cleanup → **spec §1.2 預估 $50-200/year achievable**

---

## §2 Replay Counterfactual Harness Contract

### 2.1 Harness 性質

**純 simulation tool, NOT production code**。E1 IMPL 在 `helper_scripts/calibration/` 下，**不動** `rust/openclaw_engine/src/` 任何 production binary code（per `feedback_pnl_priority_over_governance.md` light review framing）。

### 2.2 Input

#### 2.2.1 Fill replay seed (n ≈ 4 + recent N=50)

```sql
-- Phase 1b post-deploy 4 fallback rows（precise replay anchor）
SELECT order_id, link_id, symbol, side, exit_reason, qty, price, ts,
       close_maker_attempt, close_maker_fallback_reason
  FROM trading.fills
 WHERE engine_mode = 'demo'
   AND close_maker_attempt = TRUE
   AND ts > '2026-05-17 23:54:36'  -- post-restart anchor
 ORDER BY ts ASC;

-- recent N=50 whitelist closes (pre-activator baseline + post-activator)
SELECT order_id, link_id, symbol, side, exit_reason, qty, price, ts,
       close_maker_attempt, close_maker_fallback_reason
  FROM trading.fills
 WHERE engine_mode = 'demo'
   AND exit_reason IN ('grid_close_short', 'grid_close_long',
                       'bb_mean_revert', 'phys_lock_gate4_giveback',
                       'phys_lock_gate4_stale_roc_neg', 'ma_reverse_cross',
                       'bw_squeeze', 'pctb_revert')
   AND ts > NOW() - INTERVAL '7 days'
 ORDER BY ts DESC LIMIT 50;
```

#### 2.2.2 Per-cell input

```python
@dataclass
class CalibrationCell:
    cell_id: str                      # "G-AB-02-C30"
    family: str                       # "grid" / "phys_lock_giveback" / "phys_lock_stale_roc_neg"
    offset_bps: float                 # axis A
    buffer_ticks: int                 # axis B
    timeout_ms: int                   # axis C
    spread_guard_bps: float = 50.0    # axis D, default baseline
```

### 2.3 Per-cell simulation algorithm

```
for each historical close fill F (from replay seed):
  1. 從 fill ts F.ts 前 30s 取 historical tick stream（§3 data source）
  2. 在 F.ts 模擬 PostOnly limit submission，price = compute_close_limit_price(
       position_is_long=(F.side='Sell'),  # if close BUY then position is short
       inputs={best_bid, best_ask, tick_size} at F.ts,
       policy={
         offset_bps: cell.offset_bps,
         buffer_ticks: cell.buffer_ticks,
         timeout_ms: cell.timeout_ms,
       },
       spread_guard_bps=cell.spread_guard_bps,
     )
  3. 若 compute returns None → mark "skipped_spread_guard" / 不計入 fill 分母
  4. 若 compute returns price → 在 F.ts ~ F.ts+timeout_ms 期間 replay tick stream，
     simulate: 該 limit price 是否會被 trade tape 觸發 fill？
     - For BUY limit at P: ask_price ≤ P within timeout → simulated_fill=True, fill_ts, fill_px
     - For SELL limit at P: bid_price ≥ P within timeout → simulated_fill=True, fill_ts, fill_px
     - Else timeout → fallback to taker market at F.ts+timeout_ms BBO mid
  5. Record (cell_id, F.order_id, simulated_fill, fill_ts, fill_px,
             actual_taker_px=F.price, fee_saving_bps=...,
             adverse_selection_proxy=...)
```

**Fee saving formula** per cell × fill:
```
fee_saving_bps = (taker_fee_bps - maker_fee_bps)
               - max(0, (simulated_fill_px - actual_taker_px) * direction_sign / actual_taker_px * 10000)
             = 3.5 bps (Bybit fee tier 0 maker 2.0 / taker 5.5 cap)
             - slippage_realized_bps (only if simulated_fill_px is worse than actual_taker_px)
```

**Adverse selection proxy** (per task ask AC):
```
adverse_selection_proxy_bps = mean over fills (
  (mid_price_at_fill_ts + 60s - simulated_fill_px) * direction_sign
  / simulated_fill_px * 10000
)
# positive = market moved against us after our fill = adverse selection
# threshold: > pre-Phase-1b 30d taker baseline = FAIL
```

### 2.4 Output per cell

```python
@dataclass
class CalibrationCellResult:
    cell_id: str
    n_attempts: int              # 4 + 50 = 54 typical
    n_simulated_fills: int       # of fills within timeout
    n_skipped_spread_guard: int  # spread guard 跳過
    maker_fill_rate: float       # n_simulated_fills / (n_attempts - n_skipped_spread_guard)
    fill_rate_wilson_ci_low: float    # 95% Wilson CI lower bound (per AC-14)
    fill_rate_wilson_ci_high: float
    expected_fee_saving_bps: float    # mean over fills
    fee_saving_wilson_ci_low: float
    adverse_selection_proxy_bps: float  # mean over fills
    pre_phase_1b_taker_baseline_bps: float  # pre-Phase-1b 30d demo taker slippage baseline
    pass_gate: str   # "PASS" / "MARGINAL" / "FAIL"
```

### 2.5 Estimated E1 IMPL LOC

| Component | File | Est LOC |
|---|---|---|
| Cell matrix + cartesian generator | `helper_scripts/calibration/phase_1b_sweep_cells.py` | ~100 |
| Tick stream loader (PG + WS replay glue) | `helper_scripts/calibration/phase_1b_tick_loader.py` | ~150 |
| Maker price simulator (port `compute_close_limit_price` to Python) | `helper_scripts/calibration/phase_1b_maker_price.py` | ~100 |
| Per-cell simulation engine | `helper_scripts/calibration/phase_1b_sweep_replay.py` | ~250 |
| Output aggregator + Wilson CI + acceptance gate | `helper_scripts/calibration/phase_1b_sweep_report.py` | ~150 |
| pytest 套件（per-cell unit + integration）| `helper_scripts/calibration/tests/` | ~200 |

**Total ~950 LOC** (E1 estimate ~750-1000 LOC range)。**Mac local 可跑**（純 Python + PG read-only）。

**Worktree branch name 建議**：`feature/phase-1b-calibration-sweep-harness`（與 v48 P0-PHASE-1B-PARAM-CALIBRATION-1 對齊）。

### 2.6 Why not Rust harness?

- 純 simulation，no production code touch（per `feedback_pnl_priority_over_governance.md`）
- Python 已有 PG / replay infrastructure（`helper_scripts/db/counterfactual_exit_replay.py` 是 prior art）
- `compute_close_limit_price` Rust 源碼簡潔（~100 LOC `maker_price.rs:159-226`），Python port 直接
- 不違反 `feedback_new_code_rust_first.md`：本 harness 是「研究/工具腳本」非「新獨立模組」（與 `ma_crossover_counterfactual_replay.py` 同層）

---

## §3 Tick-Stream Data Source

### 3.1 Primary source: PG `market.kline_1s` / `market.orderbook_50`

從 PG 取 historical tick stream，需確認 schema。**E1 IMPL prereq**：dispatch 前由 PA + E1 確認下列 table 存在 + 7d coverage：

| Table | 用途 | Fallback if missing |
|---|---|---|
| `market.orderbook_50` (or `market.bbo_snapshot`) | best_bid / best_ask at fill ts ± 30s | use `market.trades` aggregated minute-level mid |
| `market.trades` | trade tape replay for fill detection | use `trading.fills` 自反映射（lower fidelity） |
| `market.instruments` | tick_size lookup | hardcode 25 whitelist symbol tick_size table |

**Linux PG dry-run mandatory**（per `feedback_v_migration_pg_dry_run.md` — 雖然不是 V### migration，但同樣 PG runtime semantic 風險）：E1 IMPL phase 必 SSH `trade-core` 跑 EXPLAIN ANALYZE 確認 7d window query plan 不爆 PG cache（128GB RAM 但 PG 4-8GB share）。

### 3.2 Time window

Per fill F.ts:
- **Pre-fill snapshot**: F.ts - 60s（看 BBO + spread 環境）
- **Replay window**: F.ts ~ F.ts + max(timeout_ms) = F.ts + 90s（最長 timeout cell）
- **Post-fill drift**: F.ts + 60s ~ F.ts + 5min（adverse selection proxy 評估）

**Total per-fill data span**: ~6.5min × 54 fills = ~6h tick coverage required；25 whitelist symbol 視 fill 集中度。

### 3.3 Data quality requirements

- **Freshness**: replay seed 必 post-restart `2026-05-17 23:54:36` UTC（pure Phase 1b runtime data，避 pre-activator legacy 污染）
- **Coverage**: 25 whitelist symbol × 7d > 99% bar continuity for `market.orderbook_50`；若 <99% → fallback to `market.trades` aggregation
- **Latency**: snapshot ts ≤ 100ms from fill ts（per Bybit V5 WS 50ms typical）

### 3.4 Bybit demo vs mainnet caveat

per E2 RCA §6 BB cross-check 提示：demo endpoint orderbook depth 系統性 thinner than mainnet。**harness 必 explicitly tag** `data_source = 'bybit_demo_ws'` 在 output；calibration cell 選擇後仍須 §5 operator pilot 24h live-demo 驗證（非 demo replay 即決）。

---

## §4 Acceptance Criteria Mapping

依 v48 P0 row + Phase 1b spec v1.3 AC-19 + E2 RCA §0 verdict mapping：

### 4.1 PASS gate（per cell）

```
cell.pass_gate = "PASS" IF (
  cell.maker_fill_rate >= 0.25
  AND cell.fill_rate_wilson_ci_low >= 0.15  # AC-14 Wilson 95% CI lower bound
  AND cell.expected_fee_saving_bps >= 0.5   # v48 P0 threshold
  AND cell.fee_saving_wilson_ci_low >= 0.0  # directional positive 95% CI
  AND cell.adverse_selection_proxy_bps <= cell.pre_phase_1b_taker_baseline_bps
)
```

**Aggregate PASS**: ≥1 cell 滿足以上 → PASS → 進 §5 operator pilot dispatch（top-2 cells by `expected_fee_saving_bps × maker_fill_rate`）

### 4.2 CONDITIONAL gate

```
sweep.conditional = "CONDITIONAL" IF (
  no cell satisfies PASS
  AND >=1 cell satisfies:
    cell.maker_fill_rate >= 0.15
    AND cell.expected_fee_saving_bps >= 0.3
    AND cell.adverse_selection_proxy_bps <= cell.pre_phase_1b_taker_baseline_bps
)
```

→ Consider operator pilot dispatch 1-2 cells × 24h live-demo（low-confidence prior，需 24h empirical accumulate 再決 promote / reject）

### 4.3 FAIL gate

```
sweep.fail = "FAIL" IF (
  no cell satisfies CONDITIONAL minimum thresholds
  OR all viable cells fail adverse_selection_proxy
)
```

→ **Escalate to PA + operator** — parameter tuning insufficient，需架構級 design change：
- Option α: ATR-aware adaptive offset（spec §7.1 「Phase 1b+ 未來考量」）
- Option β: Demote Phase 1b to live-only after Bybit demo endpoint depth audit (BB)
- Option γ: Hybrid maker-on-mid (place at mid 而非 inside book)，需 spec amendment

### 4.4 Mapping to spec v1.3 AC

| Sweep gate | Maps to spec v1.3 AC | Notes |
|---|---|---|
| §4.1 PASS `maker_fill_rate ≥ 25%` | AC-19 14d `≥ 30%`（lower-bar 因 sample 24h-pilot scope） | sweep PASS 是 pre-pilot prior |
| §4.1 PASS `expected_fee_saving_bps ≥ 0.5` | AC-5 `+0.5 bps n≥50 / directional n<30` | 對齊 v1.3 patch |
| §4.1 PASS `adverse_selection_proxy ≤ taker baseline` | AC-1 `close maker 比例 ≥60%` + AC-17 `close_timeout_pre_stopout_rate ≤ 5%` | sweep proxy 是 pre-AC validation |
| §4.1 PASS `fill_rate_wilson_ci_low ≥ 15%` | AC-14 Wilson CI gate | spec consensus-MF-2 對齊 |
| §4.2 CONDITIONAL | 對應 spec §10 Phase 2a 14d 觀察期 lower-bound | 不直接 pilot 而 24h 過渡 |

### 4.5 PnL impact lens per outcome（per memory）

| Outcome | PnL impact | Decision |
|---|---|---|
| PASS top cell selected | unlock $50-200/year fee saving + edge measurement cleanup | dispatch pilot |
| CONDITIONAL marginal cell pilot | 50% prob unlock 50-200/year × discounted | dispatch pilot 風險可控 |
| FAIL escalate | $0 unlock, blocked at root cause | architectural change needed |

---

## §5 Dispatch Sequence（per v48 6-step）

### Step 1: PA spec — **DONE with this doc**

- Output: this spec file
- Commit chain: **NOT BY THIS PA SESSION**（per sub-agent boundary + multi-session race protocol）— main session 接手 `git commit --only` 限定範圍 commit

### Step 2: E1 replay harness IMPL

- **Owner**: E1
- **Worktree branch**: `feature/phase-1b-calibration-sweep-harness`
- **Dependencies**: 
  - PG read access to `market.orderbook_50` / `market.trades` (need PA + E1 schema verify Linux dry-run)
  - tick_size table (from `market.instruments` or hardcoded fallback)
  - V094 audit table present (already deployed per spec §4.4)
- **LOC est**: ~750-1000（§2.5 detail）
- **ETA**: 2 pd
- **Done criteria**: 
  - All 81 cells run successfully via CLI `python phase_1b_sweep_replay.py --all-cells`
  - Output JSON per cell + aggregate CSV
  - pytest 100% green (per-cell unit + integration)
- **E1 dispatch parallel**: NO（single E1，~750 LOC 可在 2 pd 內串行完成；> 2 E1 並行成本邊際）

### Step 3: Sweep execution

- **Owner**: E1（continue from Step 2）or batch script
- **Runtime per cell**: ≤30 sec on Mac local（~6h tick replay × 81 cell ≈ 30s × 81 = 40min 總 batch）
- **Output**: `helper_scripts/calibration/output/2026-05-XX--phase_1b_sweep_results.csv` + 81 per-cell JSON

### Step 4: PA acceptance gate + cell selection

- **Owner**: PA
- **ETA**: 0.5 pd
- **Done criteria**:
  - Read sweep results → apply §4.1/§4.2/§4.3 gate
  - Identify top-2 candidate cells (by `expected_fee_saving_bps × maker_fill_rate`)
  - Write PA selection report `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-XX--phase_1b_calibration_cell_selection.md`

### Step 5: Operator pilot dispatch

- **Owner**: operator + QA
- **ETA**: 1d wall + 0.5 pd 監控
- **Scope**: top-1 or top-2 cell × 24h live-demo
- **Done criteria**:
  - TOML override per-strategy（spec §3.1 `maker_close_price_offset_bps`, `maker_close_timeout_ms` + per-exit_reason `buffer_ticks` via §3.2 risk_config）
  - engine restart with `restart_all --rebuild`（per `feedback_restart_rebuild_flag_scope.md`）
  - 24h healthcheck [62][63][64][65] sample accumulate
  - QA verdict on actual vs predicted fill rate（per pilot replay seed extension）

### Step 6: E4 regression + QA + PM verdict

- **E4** (parallel with pilot): unit + integration tests + harness deterministic check（same seed → same output）
- **QA**: post-pilot 24h healthcheck pass + AC-1..AC-19 sub-set validation
- **PM**: sign-off + merge + restart cycle

### 5.1 Roll-out vs Phase 1b spec §10 alignment

本 calibration sweep + 24h pilot 是 spec §10.1 Phase 2a Demo (7d primary + 7d extended observation) 的 **pre-Phase-2a preparation 步驟**，不替代 14d Phase 2a。Pilot 24h 後若 PASS → continue Phase 2a 14d normal cadence；若 FAIL → §4.3 escalate path。

---

## §6 Owner Chain（per `feedback_pnl_priority_over_governance.md` light review）

```
PA spec (done)
  → E1 replay harness IMPL (~750-1000 LOC)
    → E2 review (light: 1-pass code review, ≤2h timebox)
      → E4 regression (unit + integration deterministic)
        → QA pilot verdict (24h healthcheck + AC sub-set)
          → PM sign-off + merge + restart
```

**4-agent heavy review SKIPPED**: per memory `feedback_pnl_priority_over_governance.md` 「calibration sweep 是 parameter tuning，不需 4-agent heavy review；light PA design → E1 IMPL → E2/E4/QA」。

**E2 review scope**: 純 harness simulation code，不動 production binary → E2 1-pass review timebox 2h（vs spec v1.3 IMPL 階段 ~8h 多 round 對抗審查）。

**A3 / BB / FA optional pass**: NOT triggered，per light review。

---

## §7 PnL Impact Lens（per memory framing）

### 7.1 Current state baseline

- Phase 1b activator deployed `18081551` + T+12H runtime
- maker_fill_rate = **0%** (4/4 timeout_taker)
- fee saving = **$0/year**
- Spec §1.2 預期 `$50-200/year` 解鎖 progress = **0%**

### 7.2 Post-sweep PASS top-cell projection

- Pre-prior: `maker_fill_rate ≈ 25-40%`（E2 Tune-1 inside book + Tune-2 timeout extend）
- Per-attempt fee saving: 3.5 bps × 25-40% fill × ~150 close/week × $300 avg notional
- Annual: ~$10-50/year direct fee saving × 5 strategies ≈ **$50-250/year (mid-range of spec §1.2 estimate)**

### 7.3 Post-sweep CONDITIONAL marginal cell projection

- Pre-prior: `maker_fill_rate ≈ 15-25%`
- Annual: ~$6-30/year × 5 strategies ≈ **$30-150/year**
- 仍 unlock spec §1.2 lower-bound estimate

### 7.4 Post-sweep FAIL escalate cost

- Sweep cost = 3-5 pd labor + 0 PnL gain
- 仍 surface root cause for architectural change（Option α/β/γ §4.3）
- 非 sunk cost — sweep evidence input 到 future spec amendment

### 7.5 Why this is high-leverage PnL work

- Total spec design (this doc) ~0.5 pd
- Total dispatch chain 3-5 pd
- Expected outcome PASS prob ~60-70%（per E2 §3 hypothesis verdict + spec §1.2 predicted range）
- Expected PnL unlock × prob = `$50-250 × 0.65 = $32-162/year` upside
- **PnL per pd labor = $10-30/year/pd**（acceptable per memory「平衡虧損與盈利」framing；不是「一味保守」）

---

## §8 Risk Register

### 8.1 Adverse Selection Risk（HIGHEST）

| Risk | 等級 | Mitigation |
|---|---|---|
| 更內側 offset (buffer=0) → informed taker hit → fill 在 unfavourable price | **HIGH** | §2.3 `adverse_selection_proxy_bps` ≤ pre-Phase-1b taker baseline 是 gate 強制條件；任何 cell FAIL 此 gate 不入 PASS pool |
| Demo endpoint adverse selection 行為 ≠ mainnet | MEDIUM | §3.4 data_source tag + §5 operator pilot 24h live-demo 二次驗 |
| phys_lock_gate4_giveback 朝 inside 走可能放大 unfavourable drift（spec §4.2 footnote QC-MF-2 警告）| HIGH | phys_lock family 獨立 sweep + 不混 grid family + 顯式 timeout cap shorter `{45, 60}s` 不擴展到 grid 90s |

### 8.2 PostOnly Reject Volume Risk

| Risk | 等級 | Mitigation |
|---|---|---|
| buffer_ticks=0 cell PostOnly reject rate ↑ → reduce_only close path expose 持倉風險 | MEDIUM | §5.3 Race C: PostOnly reject → 立即 market；不會 silent abandon；spec §5.5 mandatory fallback 保障；harness 必 simulate PostOnly reject rate 並計入 cell evaluation |
| reject volume 過高觸 D 軸 spread_guard 仍未充分過濾 | LOW | D 軸 sweep {25, 35, 50} 可動態調整；若 buffer=0 + D=50 cell PostOnly reject > 30% → 自動降為 D=25 試 |

### 8.3 Sweep Computational Cost

| Risk | 等級 | Mitigation |
|---|---|---|
| 81 cell × 54 fill × 6.5min tick replay = 過大 PG load | LOW | per fill data span ~6.5min 已 prune；Mac local pytest 跑 cache replay；PG side EXPLAIN ANALYZE Linux dry-run 確認 query plan |
| harness LOC ~750-1000 超出 E1 single-session token budget | LOW | E1 拆 5 sub-file（§2.5 detail）符合 single-file 800 line limit；總 token 控制在 30k 內 |

### 8.4 Per-Symbol Parameter Divergence

| Risk | 等級 | Mitigation |
|---|---|---|
| grid_close_short ALT (ARBUSDT/OPUSDT/XRPUSDT) vs phys_lock_gate4 large-cap (BTCUSDT 假設) optimal cell 不同 → 單一 cell 無法滿足全 family | MEDIUM | §1.3 Prune Rule 1 已將 phys_lock 獨立 sweep；per-symbol 細分 deferred to next iteration（per spec §7.1 ATR-aware Phase 1b+ scope） |
| 4 fallback row sample 集中 ALT 低市值 → demo book 系統性 thin → cell PASS 可能 high-cap 失效 | MEDIUM | §3.4 caveat + §5 operator pilot 必含 BTCUSDT/ETHUSDT large-cap 監控 |

### 8.5 v48 vs E2 Axis Direction Conflict

| Risk | 等級 | Mitigation |
|---|---|---|
| v48 寬向 (buffer 2-4) vs E2 內側向 (buffer 0) 同 sweep → 結果矛盾無法 prune | **MEDIUM-HIGH** | §1.1 PA 決議顯式兩方向都試（cost 邊際 = 0），輸出 per-direction PASS/FAIL；若兩方向都 PASS（不太可能）取 higher `fee_saving × fill_rate`；若一方向 PASS 一方向 FAIL 取 PASS 方向 |
| 對應 spec §4.2 baseline (buffer=1) 不在內側 nor 寬向 → calibration 偏離 spec baseline 可能違 §二 #6 失敗默認收縮 | LOW | calibration 不改 cold-boot default（仍 = baseline buffer=1）；只改 hot-reload TOML override per spec §3.1；保留 §10.2 kill-switch `use_maker_close=false` → ArcSwap 1 tick 回 market |

### 8.6 Multi-session race（per memory `feedback_workflow_audit_chain` + `feedback_git_commit_only_for_metadoc`）

| Risk | 等級 | Mitigation |
|---|---|---|
| 本 spec Write 期間隔壁 session 同步動 TODO.md / spec v1.3 → commit race | MEDIUM | PA sub-agent NOT commit；main session 接手 `git commit --only docs/execution_plan/2026-05-18--phase_1b_calibration_sweep_spec.md` 限定範圍 |
| dispatch E1 IMPL 前未 fetch → 隔壁 session 已開 worktree | MEDIUM | per memory `feedback_fetch_before_dispatch`：main session dispatch E1 前 `git fetch + git branch -r \| grep phase-1b-calibration` 驗 |

---

## §9 References

### 9.1 Primary SoT

- v48 TODO P0-PHASE-1B-PARAM-CALIBRATION-1 row, commit `eebda658`（acceptance threshold + 6-step dispatch sequence SoT）
- E2 RCA `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-18--phase_1b_timeout_taker_rca.md`（§3 hypothesis verdict + §4 Tune-1/2/3 建議 + §10 operator override reconciliation）
- Phase 1b spec v1.3 `srv/docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md`（§4.2 baseline, §5.2 race state, §11 AC SoT）
- AMD v0.7 `srv/docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md`

### 9.2 Source code reference

- `srv/rust/openclaw_engine/src/strategies/common/maker_price.rs:55` (`CLOSE_MAKER_SPREAD_GUARD_BPS = 50.0`)
- `srv/rust/openclaw_engine/src/strategies/common/maker_price.rs:85-106` (`close_maker_price_policy()` per-exit_reason policy)
- `srv/rust/openclaw_engine/src/strategies/common/maker_price.rs:159-226` (`compute_close_limit_price()` to port to Python harness)
- `srv/rust/openclaw_engine/src/event_consumer/pending_sweep.rs:34` (`CLOSE_MAKER_CANCEL_ACK_GRACE_MS = 2_000`)
- `srv/rust/openclaw_engine/src/event_consumer/pending_sweep.rs:75-87` (`MakerTimeoutCancel` 觸發邏輯)

### 9.3 PA prior reports

- `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--phase_1b_use_maker_close_runtime_activator_design.md`（activator design）
- `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--maker_fill_rate_empirical_baseline.md`（E3 empirical baseline，§7 PnL impact lens 引用）
- `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-15--close_maker_first_pa_verdict.md`（Phase 1b PA READY-FOR-SPEC verdict）

### 9.4 QA / sister reports

- `srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-18--phase_1b_24h_post_deploy_verification_update.md`（T+10.6h verification, 4/4 timeout_taker raw data SoT）
- `srv/docs/CCAgentWorkSpace/QA/workspace/reports/2026-05-18--phase_1b_24h_post_deploy_verification.md`（T+18min verification）

### 9.5 Memory feedback applied

- `feedback_pnl_priority_over_governance.md` — light PA → E1 → E2 → E4 → QA chain；PnL-led framing；不 4-agent heavy
- `feedback_demo_loose_live_strict_policy.md` — Demo 是學習資料源可放寬 cost_gate；本 sweep 朝 viable cell PASS 對應「平衡虧損與盈利」非「一味保守」
- `feedback_v_migration_pg_dry_run.md` — 本 spec 0 V### migration → 不適用；但 §3.1 PG query EXPLAIN ANALYZE Linux dry-run 仍 mandatory
- `feedback_fetch_before_dispatch.md` — main session dispatch E1 IMPL 前 fetch + branch grep
- `feedback_git_commit_only_for_metadoc.md` — main session 接手 commit 用 `git commit --only` 限定範圍

### 9.6 Cross-spec orthogonality verified

- Phase 2c-CM counterfactual harness spec `srv/docs/execution_plan/2026-05-18--phase_2c_livedemo_counterfactual_harness_spec.md`：完全 orthogonal scope（LiveDemo 7d gate at fixed config）— 本 sweep 是 pre-Phase-2a Demo parameter tuning，**先後序**：sweep PASS → §5 pilot 24h → Phase 2a 14d → Phase 2b LiveDemo 7d → Phase 2c-CM counterfactual gate → Phase 3 Live

---

## §10 PA push back / open questions

### 10.1 Push back items

1. **Sweep 81 cell ≤ 100 target 但 ≥ 50（v48 default 估算 24-cell footprint）** — PA judgment：若 operator 想 ≤50 cell 更激進 prune，可 drop §1.4 Block 4 spread guard D 軸獨立 sweep（9 cells）+ collapse C-grid timeout to {30, 90}s 而非 3 values → 24 + 24 + 24 = 72 cells；但 D 軸 spread guard 是 E2 §4 Tune-3 顯式 axis，省掉等於放棄一條改善路徑。**PA 推薦保留 81 cells**。

2. **buffer_ticks=0 朝 inside book 走是 E2 §4 顯式警告「+PostOnly reject volume」方向**，spec §4.2 baseline 是 buffer=1 — 本 sweep 把 buffer=0 加入 PASS pool 是否違 §二 #6 失敗默認收縮？PA 判 NO：calibration sweep 只變 hot-reload TOML override，cold-boot default 仍 = baseline buffer=1 + use_maker_close=false（spec §3 fail-safe 保留）。但若 buffer=0 cell PASS 並 promote 後，必同步 update spec §4.2 baseline + AMD patch（**§5 operator pilot 24h PASS 後本 spec 不直接成 SoT，需 PA + main session 推 AMD v0.8 patch**）。

3. **phys_lock_gate4_giveback 朝 inside 走違 spec §4.2 QC-MF-2 footnote「gate4 fire 時 unfavourable drift bias 條件機率高於隨機 walk，maker pending 期 expected fill price 嚴格 worse than 立即 market」** — PA 判 sweep 仍試但 acceptance gate `adverse_selection_proxy_bps ≤ pre-Phase-1b taker baseline` 必嚴格驗，若 phys_lock family 所有 cell 都 FAIL adverse selection → keep baseline + drop phys_lock from Phase 1b scope（spec amendment）。

### 10.2 Open questions（待 operator / main session 確認）

1. **Cell selection top-1 vs top-2 pilot?** — top-2 pilot ↑ statistical robustness 但 ↑ TOML override 複雜度（per-exit_reason × per-strategy 共 8 entry × 2 cell = 16 override）。PA 推薦 top-1 with fallback path：若 top-1 24h FAIL，operator 可手動 swap to top-2 不重 sweep。

2. **Sweep replay seed 是否 include pre-restart `2026-05-17 23:54:36` 之前的 7d demo data？** — pre-restart 是 pre-activator legacy，但 4 row post-restart sample 太小（n=4 vs typical 50）。PA 建議：seed = post-restart 4 + pre-restart 7d 內前 50 whitelist demo closes（標 tag `seed_source = 'post_restart' / 'pre_restart_baseline'`），harness 報告分層比較。

3. **Mac local harness vs Linux trade-core run?** — Mac local OK for Python harness（read-only PG via Tailscale）；但若 §3 tick replay 數據量 ≥ 500MB → SSH Linux 跑可能更快。PA 留 E1 IMPL phase 自行 benchmark 決定。

---

## §11 Multi-session race check（per memory）

- ✅ PA sub-agent NOT committing this spec — main session 接手 `git commit --only docs/execution_plan/2026-05-18--phase_1b_calibration_sweep_spec.md`
- ✅ Read-only on production code path (no rust/openclaw_engine/src/ touch, no TOML edit, no V### migration)
- ✅ No revert of隔壁 session WIP（memory + TODO + v48 commit `eebda658` 保留原狀）
- ✅ Spec design ≠ parameter change → 符合 12H test window observation-only constraint
- ✅ 不修改 v48 P0 row 或 v48 commit — 本 spec 是 v48 P0 row Step 1 「PA spec」的 deliverable
- ✅ PnL-led framing per memory 每 §開頭 / 結尾 quote PnL impact

---

## §12 Conclusion

**Spec status**: SPEC v0.1 DRAFT，pending main session commit。

**Deliverables**:
- 81-cell pruned matrix（§1.4）
- Replay harness contract（§2，~750-1000 LOC E1 IMPL estimate）
- Acceptance gate（§4，PASS / CONDITIONAL / FAIL）
- 6-step dispatch sequence（§5，per v48 P0 row）
- Owner chain light PA → E1 → E2 → E4 → QA（§6，per memory）

**Total ETA**: 3-5 pd labor，wall-clock 3-5 天（含 24h pilot hold）。

**Expected PnL unlock**: `$32-162/year` upside × ~65% PASS prior probability，**high-leverage parameter tuning work** per memory framing。

**Next step**: main session sign-off 後 dispatch E1 worktree `feature/phase-1b-calibration-sweep-harness`。
