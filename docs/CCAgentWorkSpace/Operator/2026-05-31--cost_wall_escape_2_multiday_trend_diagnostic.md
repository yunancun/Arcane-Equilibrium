# MIT Diagnostic — Cost-Wall Escape #2: Low-Turnover Multi-Day Perp TREND (TSMOM)

**Date**: 2026-05-31 CEST · **Role**: MIT · **Mode**: READ-ONLY PG (docker exec), 0 write, 0 deploy
**Trigger**: operator directive — run cost-wall escape category #2 (low-turnover multi-day holds; amortize
11-27bps round-trip taker cost across multi-day 100s-1000s bps moves).
**Framing**: Alpha Tournament SSOT §4 scorecard + §5 gates. TSMOM is NOT in §3 candidate pool — this is a
fresh exploratory probe on whether it merits a slot.

---

## ONE-LINE VERDICT

**Feasibility: the dilution mechanism is mechanically VALIDATED (gross multi-day move dwarfs the cost wall),
but the 56-day data window yields at most ~8 independent time periods, so any weekly-or-longer strategy has
effective N_independent ≈ 8 and CANNOT robustly validate an edge. Verdict = `observe_more` + one structural
HINT worth re-running once data deepens. No edge may be claimed from this sample.**

---

## Fact / Inference / Assumption legend
- **[F]** = direct PG empirical this run. **[I]** = inference from [F]. **[A]** = assumption (flagged).

---

## 1. Data + Sample Feasibility  [F]

| Item | Value | Source |
|---|---|---|
| Window | **56 days** (2026-04-05 → 2026-05-31) | `market.klines` min/max ts |
| Collector onset | 2026-04-05 14:00 +02 (hard lower bound) | min(ts) all timeframes |
| Symbols (1m/5m/15m/1h) | 142 | `count(DISTINCT symbol)` |
| Symbols (4h) | 137 (6262 rows) | grouped count |
| klines schema | ts(tstz), open_ts_ms, close_ts_ms (bigint), symbol, timeframe, OHLC **real(float4)**, volume, turnover, tick_count | information_schema |

**1m coverage has gaps** [F]: BTCUSDT/ETHUSDT avg **1259 bars/day** (vs 1440 full), only **36/56 full
days**. DOGE/SOL/XRP avg 829-948 bars/day, 16 full days. → daily-close sampling (last closed 1m bar per UTC
day) is usable but research-grade-with-gaps, NOT pristine. 4h native bars are also incomplete (BTC 307/337
expected ≈ 91%; most symbols far fewer) → I used **1m → daily-close** rather than 4h (denser, gap-robust for
EOD sampling).

**Non-overlapping trade count math** [F, from sweep below]:

| Strategy form | Hold M | # non-overlapping periods | per-symbol trades |
|---|---|---|---|
| Per-symbol TSMOM | M=7 | ~6-7 | ~4-5 |
| Per-symbol TSMOM | M=14 | ~3 | ~1.5 |
| Per-symbol TSMOM | M=21 | ~2 | ~1 |
| Cross-sectional | M=14 | **2 rebalances** | n/a |
| Cross-sectional | M=5 (weekly, max periods) | **8 rebalances** | n/a |

**The binding constraint is the number of independent TIME periods (~8 max for weekly+), NOT symbol count.**
Cross-sectional pooling adds symbols-per-period but those legs are market-beta-correlated within a period →
effective independent draws ≈ # rebalances ≈ 8. This is below the SSOT §5 `n >= 30` sample gate.

---

## 2. Preliminary Diagnostic — (N,M) Sweep  [F]

Per-symbol TSMOM, 10 liquid symbols, non-overlapping entries, leak-free.
Cost model [A, conservative]: taker 5.5bps/leg × 2 = 11bps + 4bps slippage round-trip = **15bps** + **M bps**
funding approx (~1bp/day; real measured drag is smaller — see §5).

| N | M | n_tr | gross_bps | **abs_move_bps** | net_bps≈ | sd_bps | t_stat | win% |
|---|---|---|---|---|---|---|---|---|
| 7 | 7 | 47 | -70 | 648 | -92 | 1118 | -0.43 | 55 |
| 7 | 14 | 22 | -59 | 1213 | -88 | 1657 | -0.17 | 41 |
| 7 | 21 | 14 | +55 | 1159 | +19 | 1686 | 0.12 | 43 |
| 14 | 7 | 37 | +60 | 645 | +38 | 1184 | 0.31 | 49 |
| 14 | 14 | **15** | **+267** | 824 | +238 | 1471 | **0.70** | 47 |
| 14 | 21 | **7** | +591 | 591 | +555 | 585 | **2.67** | **100** |
| 30 | 7 | 18 | -235 | 389 | -257 | 449 | -2.22 | 33 |
| 30 | 14 | 6 | -375 | 612 | -404 | 579 | -1.58 | 17 |

**Key reads:**
1. **DILUTION THESIS VALIDATED [F→I]**: `abs_move_bps` is **389-1213 bps** across every cell. Total cost
   (15bps + M funding ≈ 29bps at M=14) is **~3-4% of the gross move**. At the multi-day horizon, **cost is NOT
   the binding constraint** — this is the genuine escape from the high-frequency cost wall the operator sought.
2. **NO COHERENT SIGNAL [F→I]**: sign of gross_bps flips incoherently across nearby (N,M) (7/7 negative, 14/7
   positive, 30/7 strongly negative). Real TSMOM exhibits monotone/coherent sign across adjacent parameters;
   this looks like **noise sampled at n=6-47**, not structure.
3. **The two "significant" cells are DEGENERATE artifacts**: 14/21 shows t=2.67 / **100% win** but **n=7** (a
   100% win rate at n=7 is a red flag, not evidence). 30/7 shows t=-2.22 (reversal) but is fragile and sign-
   inconsistent with 30/14. Neither survives multiple-comparison correction (8 cells tested → Bonferroni
   α=0.05/8=0.00625 → need |t|>~2.9-3.5 at these dfs; **none clear it**).

---

## 3. Cross-Sectional Momentum  [F]

Rank symbols by trailing N-day return, long top tercile / short bottom tercile, hold M days, non-overlapping.

| N | M | n_rebal | n_ls_legs | gross_bps | net_bps≈ | sd_bps | t_stat | win% |
|---|---|---|---|---|---|---|---|---|
| 14 | 14 | **2** | 14 | -321 | — | 2472 | -0.49 | 50 |
| 7 | 5 (max periods) | **8** | 59 | +54 | +34 | 1416 | 0.29 | 49 |

**8 rebalances is the hard ceiling** for weekly-or-longer in this window. Even with 59 long-short legs, the
independent time clusters = 8. t=0.29 / win 49% = **statistically dead**. Cross-sectional does NOT escape the
sparsity because period-count, not breadth, is binding.

---

## 4. Funding Reality  [F]  (`market.funding_rates`, 25 sym, 1890 rows, same 56d window)

| symbol | avg signed fr (bps/settle) | avg abs fr (bps/settle) | **avg daily drag (bps/day)** |
|---|---|---|---|
| BTCUSDT | 0.046 | 0.382 | 0.139 |
| ETHUSDT | 0.104 | 0.452 | 0.312 |
| XRPUSDT | 0.110 | 0.513 | 0.329 |
| SOLUSDT | 0.196 | 0.725 | 0.588 |
| DOGEUSDT | 0.264 | 0.629 | 0.793 |

Daily funding drag is **0.14-0.79 bps/day** (signed). My sweep used 1bp/day → slightly conservative (generous
to cost). At multi-day horizon vs 389-1213 bps moves, **funding is a rounding error** — further confirms
dilution. Sign nuance: TSMOM-long in uptrend typically pays funding (drag); short can earn it (credit). Either
way, immaterial at this horizon.

---

## 5. Leak-Free Guarantee  [F — empirically dumped]

Audited two BTCUSDT N=14/M=14 trades (entry_rn 15, 29):

| entry_rn | lookback_start | entry_d | exit_d | px_14d_ago | entry_px | exit_px | trail% | fwd% | lb_before_entry | exit_after_entry |
|---|---|---|---|---|---|---|---|---|---|---|
| 15 | 2026-04-05 | 2026-04-20 | 2026-05-04 | 68994.25 | 75832.70 | 79805.05 | 9.91 | 5.24 | **t** | **t** |
| 29 | 2026-04-20 | 2026-05-04 | 2026-05-18 | 75832.70 | 79805.05 | 76973.50 | 5.24 | -3.55 | **t** | **t** |

Concrete leak-free proof against all 6 leakage types:
- **Look-ahead**: trailing return uses only prices through entry day (`lb.rn = a.rn - N`, `lookback_before_entry=t`). No rolling stat includes the current/forward bar.
- **Target leakage**: forward return strictly `entry_d → entry_d+M` (`fw.rn = a.rn + M`, `exit_after_entry=t`); feature window (lookback) and target window (forward) do not overlap.
- **Resample boundary**: daily close = `DISTINCT ON (symbol, day) ... ORDER BY close_ts_ms DESC` = last **closed** 1m bar per UTC day → no partial-bar use.
- **Time-zone**: day boundary computed `AT TIME ZONE 'UTC'` from `close_ts_ms`; consistent UTC, no cross-tz leak.
- **Cross-section**: tercile rank computed within each rebalance date only (same-day cross-section, known at rebalance); no full-period standardization.
- **Survivorship**: window is short (56d); no symbol delisted within it. Universe = symbols with coverage; CAVEAT — restricting to symbols with full coverage is mild survivorship, but immaterial at this horizon. Non-overlapping enforced via `(rn-(N+1)) % M = 0`.

---

## 6. Alpha SSOT §4 Scorecard

| Field | Value |
|---|---|
| candidate_id | (none — exploratory; not in §3 pool) |
| alpha_thesis | TSMOM: per-symbol sign(trailing N-day ret) → hold M days. Falsifiable: net edge per multi-day trade > 0 AND gross >> cost wall. |
| data_window | 2026-04-05 → 2026-05-31 (56d); `market.klines` 1m→daily-close; `market.funding_rates` |
| engine_mode | N/A (price-data backtest on market.klines; market-data not per-engine) |
| n_events / n_fills | **6-59 raw; ~8 independent time periods max** (FAILS §5 `n>=30` independent) |
| gross_bps | -375 to +591 per multi-day trade; sign incoherent across (N,M) |
| fee_bps | 11 (Bybit VIP0 taker 5.5×2) |
| slippage_bps | 4 round-trip [A, conservative] |
| funding | 0.14-0.79 bps/day measured (immaterial at horizon) |
| net_bps | mechanically positive where gross positive (cost ~3-4% of move) but NOT statistically distinguishable from 0 |
| **abs gross move** | **389-1213 bps** — dilution thesis PASS |
| turnover | ~1-2 round-trips/symbol/month at M=14-21 (the intended low-turnover regime) |
| capacity_estimate | not estimable at this sample |
| replay_coverage | replayable on klines; but sample too thin for Stage 0R promotion grade |
| failure_mode | crowded published anomaly (McLean-Pontiff post-publication decay); regime-dependent; sign instability here suggests no current edge |
| **verdict** | **`observe_more`** |

### §5 Gate results
| Gate | Result |
|---|---|
| Data gate | PASS (rows ordered, closed-bar only, leak-free) — with gap caveat |
| Fee gate | PASS mechanically (cost << move) but MOOT (edge not significant) |
| **Sample gate** | **FAIL → observe_more** (≈8 independent periods << 30) |
| Replay gate | applicable but not promotion-grade at this sample |
| Governance gate | N/A (no IMPL proposed) |
| Portfolio gate | N/A |

McLean-Pontiff / DSR note: trend is a heavily-published, decay-prone anomaly. Proper validation needs DSR
deflation for the 8-cell parameter search. **56d is insufficient to robustly validate or deflate — honestly
flagged; no DSR computed because the underlying sample cannot support it.**

---

## 7. HINT (worth pursuing — NOT a conclusion)

The **mechanism** (cost amortization across multi-day moves) is real and validated: a ~824bps average 14-day
move vs ~29bps all-in cost means escape #2's core premise HOLDS. What is missing is **historical depth**, not
mechanism. To robustly estimate a TSMOM edge you need ≥6-12 months of daily data (≥50-100 independent 14-day
periods) to clear the sample gate and support DSR deflation.

**Recommendation:**
1. **Verdict `observe_more`** — re-run this exact diagnostic once `market.klines` history reaches ≥6 months
   (≈ 2026-10 at current collector onset). Same leak-free SQL; just deeper window.
2. **Do NOT enter Alpha Tournament IMPL now** — SSOT §3 prioritizes A1 (funding short v2) / A2 (liquidation
   cascade fade); TSMOM has no IMPL-grade evidence and would dilute engineering across an unproven idea (§2
   "1-2 candidates max").
3. **One cheap data action**: if operator wants to accelerate, backfill Bybit daily/4h klines for the liquid
   majors from exchange history (read-only market data, ADR-0033/0040-style exception) to get the ≥6-month
   window without waiting for live collector accumulation. This is the single highest-leverage unblock.

---

## Boundaries observed
- READ-ONLY: 0 writes, 0 schema changes, 0 deploy. All queries SELECT-only via `docker exec trading_postgres
  psql` (non-interactive SSH `DATABASE_URL` empty — used docker exec per prior-run finding).
- No edge claimed from sparse sample. fact/inference/assumption separated throughout.
- float4 OHLC cast to float8 before arithmetic; round() cast to numeric (PG 16 has no round(float8,int)).
- Did not touch QC's lane (alpha-significance verdict is shared: QC owns alpha-validity, MIT owns sample/
  leakage/feasibility). This report supplies the data feasibility + leakage clearance; the go/no-go alpha call
  for any future IMPL is a QC+MIT joint sign-off.

MIT AUDIT DONE: docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-31--cost_wall_escape_2_multiday_trend_diagnostic.md
