# QC PREREQUISITE SPEC — L2 Phase 3b `beta_neutral_check` (B1) + altcap basket

Date: 2026-06-09 · Owner: QC (PM-persisted; QC Write disabled by profile) · Status: **B1 numbers FINALIZED (sign-off-ready); altcap basket design-complete, E1-build-blocked only on building the producer (data does not exist).**

Cross-validated with MIT P3b spec (`2026-06-09--l2-p3b-leak-producers-m4-benchmark-spec.md`) — MIT runtime finding folded into Number 2/3c (down-sub-sample window).

## 1. B1 FOUR FINAL NUMBERS (sign-off-ready deterministic constants)

| # | Constant | FINAL value | Fail mode |
|---|---|---|---|
| 1 | factor set | **BTC + altcap dual, MANDATORY** (`r_strat = α + β_btc·r_btc + β_alt·r_altcap + ε`) | BTC-only → **DEFER** (not pass — 3/5 dead candidates were alt-down-beta; BTC-only passes the masquerade by construction) |
| 2 | beta window | **90d** rolling min; bar = **daily or 4h**, pinned per candidate (NOT 1m — attenuation bias) | <90d aligned → **DEFER** |
| 3 | `BETA_NEUTRAL_THRESHOLD` | **0.15** on `|β_btc|` AND `|β_alt|` AND `|β_down|` | any \|β\| ≥ 0.15 → **fail** |
| 3c | down-market def | **30d drawdown >8% OR 7d return <−5%**, BTC anchor, **lagged-PIT** (label@t uses data ≤t only; NEVER forward "was-followed-by-drop") | — |
| 3c-window | **down sub-sample span** | **≥180d** (MIT runtime: 90d=only 23 down-bars <30; 729d has 309). **β_down estimated on down sub-sample drawn from ≥180d span**; <30 down-bars → **DEFER** | <30 down-bars → **DEFER** |
| 4 | `BETA_UPPER_CAP` | **`β + 1.96·SE < 0.20`** (all three betas) — kills "small but noisy β" pass | any upper bound ≥ 0.20 → **fail** |

**E1 build note**: `residual_alpha_gate._fit_factor_beta:619-624` returns point coeffs only (reuse the OLS). B1 must additionally compute **coefficient SE** = residual-var × diag((X'X)⁻¹); escalate to HAC (Newey-West) SE if Durbin-Watson on residual < 1.5. Down-mask: derive from raw BTC daily closes (V127 `aeg_regime_labels.ret_30d` as corroborating cross-check, NOT binding → decouples B1 verdict from classifier_version).

## 2. ★ ALTCAP BASKET — EQUAL-WEIGHT (recommendation; operator-ratify)

**Data ground**: market-cap data DOES NOT EXIST (0 hits `market_cap`/`circulating_supply` over srv; Bybit perp has no cap; V125 = funding/OI/LS only). **Equal-weight needs only daily closes (`market.klines`) + FND-2 membership — both exist.**

- **Weighting = EQUAL-WEIGHT, daily-rebalanced.** Reject cap-weight: (a) cap data only via external CoinGecko/CMC = new dependency (vs Root Principle 14) + PIT restatement-leak (vendor backfills historical supply); (b) **empirical: funding-tilt PCA PC1 ~69% (N_eff~2.0) ⇒ basket return dominated by common alt move ⇒ weighting is second-order (equal/cap/volume ~0.95+ corr).** Reject OI-weight (regime-driven, contaminates with the cascade signal B1 must be orthogonal to) + volume-weight (regime-correlated, marginal).
- **Universe = FND-2 PIT universe, ex-BTC, ex-stablecoin.** Launch scope = **CORE25 ex-BTC = 24 survivorship-vetted symbols** (`fnd2_pit_universe/cohorts.py:27-33`). Widen to full FND-2 `included` set later.
- **Return series**: `r_altcap_t = mean over PIT-alive constituents of (close_s_t/close_s_{t-1} − 1)`, daily equal-weight.
- **★ PIT discipline (non-negotiable)**: constituents + membership at bar `t` = **PIT-alive set at `t`** (FND-2 `alive_from`/`alive_to` walk-forward, NOT today's survivors). New listing enters at `alive_from`; delisted exits after `alive_to` (no zombie forward-fill). **The survivorship walk-forward is the one impl hot-spot for MIT M3 review.**
- **Persistence: on-the-fly / research-artifact (CSV mirroring FND-2), NO persisted table, NO V137.** Deterministic function of (FND-2 membership + daily closes); recompute per B1 run = cheap + leak-free-by-construction. V137 stays reserved-not-used (reopen only if persisted basket wanted for replay → owes Linux dry-run).

## 3. Q1 — `N_trades_oos ≥ 50` → DEFER (confirmed). Maps to `dsr_gate.compute_dsr(min_observations=50)` → `insufficient_observations` → DEFER. Three-state honesty (DEFER ≠ FAIL).

## 4. Leak-free PIT — confirmed for all 3 inputs (BTC factor / altcap basket / down-label all backward-looking). Down threshold = absolute scalar (8%/5%), NOT full-sample percentile (avoids the `data_loader.py:300` ML-training vol-tercile leak class). `residual_alpha_gate` enforces train-end<eval-start (`:552`).

## 5. Residual ratification points
- **operator**: lock altcap = equal-weight (vs cap-tilt). If cap-tilt insisted → only defensible = frozen single-date CMC snapshot as sensitivity-check-only, never binding (reopens Root-Principle-14).
- **E1 build (MIT-owned producers + QC-owned gate)**: altcap basket producer (net-new, biggest gap); B1 add coefficient SE; down sub-sample ≥180d span.
- **operator/runtime**: V127 `--write-db` (corroboration, not blocking — B1 down-mask computable from market.klines directly); seed agent.lessons dead-modes for M4 bad-set.
- **V137 reserved-not-used** (altcap on-the-fly).

## 6. Sign-off posture
B1 four numbers FINALIZED. Altcap = equal-weight ex-BTC CORE25, daily-rebal, on-the-fly, PIT walk-forward. Q1 confirmed. QC signs off **B1 final at P3b implementation** (chain PA→E1→E2→**QC(B1 final+leak-free PIT)**→MIT(M3+M4)→E4→QA). Replication-crisis check: equal-weight = 0 free params; thresholds fixed deterministic (not swept); gate designed to REJECT not discover = correct unattended-gate posture.
