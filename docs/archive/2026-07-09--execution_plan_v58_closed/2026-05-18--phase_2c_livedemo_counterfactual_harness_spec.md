# Phase 2c LiveDemo Counterfactual Verification Harness — Spec Design

**Date**: 2026-05-18
**Author**: PA single-agent restart dispatch (post-2026-05-18 multi-agent worktree race stop)
**Mode**: PA design spec — doc-only output；不寫業務代碼；不 commit；不派下游
**Status**: SPEC v0.1 DRAFT — pending operator sign-off + AMD-2026-05-15-02 v0.6 patch（namespace harmonization）+ Phase 2b LiveDemo PASS empirical evidence

**對應 spec / TODO**:
- EDGE-P2-3 Phase 1b close-maker-first（`docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md` v1.3）
- V094 close-maker audit schema（`docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md`）
- AMD-2026-05-15-02 v0.5（close-maker-first；§5.3 待開）
- phys_lock live-enable AMD draft `2026-05-XX-XX-phys-lock-live-enable-draft.md` §5.3（Phase 2c BLOCKER-level precedent）
- QC-SF-3 BLOCKER finding（QC `2026-05-16--phys_lock_live_enable_amd_qc_review.md` MUST-FIX-1）

---

## §1 Executive Summary

### 1.1 Phase 2c Naming Disambiguation（首要 push back）

**主會話 prompt 對 Phase 2c 定位有 cross-AMD 概念混淆，本 spec 修正並提請 operator 認可：**

| 概念 | 出處 | 對象 |
|---|---|---|
| **Phase 2c (phys_lock)** | `2026-05-XX-XX-phys-lock-live-enable-draft.md` §5.3 | phys_lock fire 後 with-lock vs without-lock counterfactual；7d observation；≥ 30 fires gate；FAIL → AMD 永久 REJECT |
| **Phase 2c (close-maker-first) NEW** | 本 spec proposed | close maker fill vs hypothetical taker market-fill counterfactual on LiveDemo 7d；Phase 1b promotion 從 Phase 2b LiveDemo PASS → Phase 3 Live 的中間 gate |

**為何兩個 Phase 2c 不能共用 harness**：
- phys_lock counterfactual transformation = 對 fire 樣本「假設不 lock，續持 hold age 終結時 market close 的 PnL」
- close-maker-first counterfactual transformation = 對 close fill「假設不走 maker，瞬時 taker market-fill 的 PnL」
- 不同對象、不同 baseline 構造、不同 data source（phys_lock 走 `learning.exit_features` JOIN `trading.fills`；close-maker 走 `trading.fills` audit + V094 hot column + JSONB details）

**結論（operator 取捨）**：
- (A) 同意本 spec 將 Phase 2c naming 擴展到 close-maker-first（需 AMD-2026-05-15-02 v0.6 patch 加 §5.3 BLOCKER）
- (B) 重命名為 **Phase 2c-CM (close-maker)** 與 phys_lock Phase 2c 區分（disambiguation by suffix）
- **PA 推薦 (B)**：避免 cross-AMD naming collision；本 spec 全篇文用 **Phase 2c-CM**

> **本 spec 全篇後續使用 Phase 2c-CM 指代 close-maker-first counterfactual gate；Phase 2c-PL 保留指 phys_lock Phase 2c**。

### 1.2 BLOCKER 結構繼承自 QC-SF-3

phys_lock Phase 2c-PL 是 QC-SF-3 catch 出的 BLOCKER-level live observation gate。Demo 7d/14d PASS + Phase 2b LiveDemo PASS **不充分驗 live regime 行為對稱**（per `feedback_demo_loose_live_strict_policy`），需 live/live_demo regime 二次 counterfactual 驗證。

**close-maker-first 是否需要等效 Phase 2c-CM？PA 判斷 YES，理由 3 條**：

1. **Demo silent degradation risk inherits**：close-maker-first Phase 2b LiveDemo 7d PASS = 走 demo endpoint，但 demo endpoint 對 `EC_PostOnlyWillTakeLiquidity` / `EC_ReachMaxPendingOrders` 等 reject 路徑可能 silent degrade（per AC-15 reject sample healthcheck 已 catch 部分但非充分）。
2. **Counterfactual 是 alpha-deficient regime 唯一驗證**：close-maker-first 雖然不是 alpha source（per AMD §1 framing），但其 fee saving claim「+0.5 bps net per close attempt」是 alpha-impact-adjacent — 如果 maker fill 在 live regime 因 BBO depth / latency 不一致 leak 更大 slippage，可能 net negative；Phase 2b AC-5/AC-11 directional gate **不充分排除「fee saving 被 unfavourable drift 吃光」**。
3. **AMD §5.1 multiple-testing protocol 已要求 BH-FDR 跨 phase**：Phase 2c-CM 加一個 phase 不增加 net多重比較負擔（FDR 已 control 48-cell；新 phase 增加 1 phase × 8 reason × 2 env = 16 cells，併入既有 BH adjustment table）。

### 1.3 Verification 目標 + Gate Semantics

**Phase 2c-CM 是 Phase 1b 落地驗證 final gate**：
- Phase 2a Demo 14d PASS → Phase 2b LiveDemo 7d PASS → **Phase 2c-CM LiveDemo 7d counterfactual** PASS → Phase 3 Live operator sign-off → flag flip
- PASS = counterfactual delta（actual close PnL − hypothetical taker baseline PnL）統計顯著為正（mean > 0 bps + Wilson CI lower > 0 + BH-FDR controlled）
- FAIL = Phase 1b promotion BLOCKED；rollback per AMD §10 + spec 修訂或 reject

**與 phys_lock Phase 2c-PL 的時序關係**：
- phys_lock Phase 2c-PL = phys_lock AMD live enable **後** 7d observation（post-enable，per-fire 即時 counterfactual）
- close-maker Phase 2c-CM = close-maker-first 進 Phase 3 Live **前** 7d offline counterfactual（pre-Phase 3，retrospective replay on Phase 2b LiveDemo 7d data）
- 兩 phase 完全獨立，無時序衝突；如 phys_lock AMD enable 落在 close-maker Phase 2c-CM 觀察窗內 → 必延期 close-maker Phase 2c-CM 至 phys_lock enable 後另 14d clean window（避免雙 flag 觀察 noise，per AMD §4.1 緩解 1 one-flag-per-phase）

---

## §2 Scope + Data Source

### 2.1 In-Scope

- **Data source**: `trading.fills` 過去 7d LiveDemo (`engine_mode IN ('live_demo')`) close fill rows + V094 audit hot columns + details JSONB keys
- **Counterfactual harness**: 新 Python script `helper_scripts/reports/phase_2c_cm_livedemo_counterfactual.py`
- **Statistical test**: paired delta + Wilson CI + BH-FDR
- **Verdict report**: Markdown to `docs/CCAgentWorkSpace/PM/workspace/reports/YYYY-MM-DD--phase_2c_cm_livedemo_counterfactual_verdict.md`
- **AC criteria**: 對齊 Phase 1b spec §11 AC-1..AC-19 + Phase 2c-CM new AC-20..AC-22

### 2.2 Out-of-Scope（顯式禁止）

- ❌ 不修改 V094 schema（V094 spec land 後不可變更）
- ❌ 不修改 close-maker-first Rust 代碼（spec §6 `compute_close_limit_price`）
- ❌ 不寫 counterfactual 結果到任何 `learning.*` table（W-C Caveat 2 carve-out + non-training invariant per AMD §7 #7）
- ❌ 不餵 counterfactual 結果到任何 ML training pipeline（mirror AMD §9 forbidden path）
- ❌ 不真實 dispatch order（counterfactual = 純統計推算，無 BB rate budget 消耗）
- ❌ 不修改 phys_lock counterfactual harness（`program_code/audit/counterfactual_exit_audit.py`）— 重用其 scaffolding 設計 pattern 但獨立 file

### 2.3 V094 Audit Data Schema 依賴

Phase 2c-CM harness 需 V094 schema 完整 applied + writer 完整接線（per V094 spec §6 `trading_writer.rs:430` details payload writer upgrade）：

| 欄位 | 用途 |
|---|---|
| `trading.fills.close_maker_attempt` (V094 column) | filter close maker fills（true）vs taker fills（false） |
| `trading.fills.close_maker_fallback_reason` (V094 column) | 識別 fallback path（timeout_taker / postonly_reject / ack_lost / rate_limit_pause / etc.）|
| `trading.fills.details.close_initial_limit_price` (V094 JSONB key) | reconstruct maker pending start price |
| `trading.fills.details.close_final_fill_price` (V094 JSONB key) | actual maker fill price |
| `trading.fills.details.close_maker_eligible_reason` (V094 JSONB key) | trigger_tag 鏡像，per-exit_reason breakdown |

**前置條件**：V094 IMPL + Linux PG dry-run × 2 round + `trading_writer.rs:430` details payload writer upgrade 全 land；Phase 2b LiveDemo 7d 跑完且 audit data 完整（NULL ladder PASS ≤ 0.1% per AC-6/AC-16）。

---

## §3 Counterfactual Transformation Method

### 3.1 三類 fill 分流

| Fill 類別 | 識別條件 | Counterfactual transformation |
|---|---|---|
| **(A) Maker success** | `close_maker_attempt=TRUE` AND `close_maker_fallback_reason IS NULL` | Actual maker fill PnL vs hypothetical taker market-fill PnL（at same instant，using BBO snapshot reconstruction）|
| **(B) Maker→taker fallback** | `close_maker_attempt=TRUE` AND `close_maker_fallback_reason IN ('timeout_taker', 'postonly_reject', 'rate_limit_pause', etc.)` | Actual taker market-fill PnL（fallback 後成交）vs hypothetical immediate taker market-fill PnL（at maker dispatch instant，pre-timeout）|
| **(C) Safety path / not attempted** | `close_maker_attempt=FALSE` OR `close_maker_fallback_reason IN ('not_attempted_safety_path', 'engine_shutdown_safety')` | Excluded from counterfactual analysis（baseline 不適用；safety path 即真風控 fail-closed）|

### 3.2 Counterfactual baseline 構造（Class A + B）

**Class A maker success**：
- Actual PnL = `(close_final_fill_price - entry_price) * qty * direction - fee_maker`（fee_maker = 2.0 bps per BB-SF-2）
- Counterfactual taker baseline PnL = `(taker_baseline_price - entry_price) * qty * direction - fee_taker`（fee_taker = 5.5 bps）
- `taker_baseline_price` = BBO at maker dispatch instant 的 opposite-side mid-fill price（假設 market order 立即吃 best-bid/best-ask 1-2 tick depth）
- Paired delta = Actual − Counterfactual baseline（per fill）

**Class B fallback**：
- Actual PnL = fallback 後 market fill 的 PnL（fee_taker = 5.5 bps）
- Counterfactual immediate-taker PnL = 假設 maker dispatch instant 立即走 market 的 PnL（使用 maker dispatch ts 對應 BBO snapshot）
- Paired delta = Actual − Counterfactual immediate-taker
- **語義**：delta > 0 = fallback overhead 比 immediate taker 還好（罕見，maker pending 期 favourable drift）；delta < 0 = fallback 比 immediate taker 慘（typical case，timeout adverse drift）

### 3.3 BBO snapshot reconstruction

**核心難點**：counterfactual taker baseline 需要 maker dispatch instant 的 BBO snapshot；Phase 2b LiveDemo 7d 跑時若無 BBO snapshot 持久化 → counterfactual 不可重建。

**Data source 候選（PA 評估）**：
1. **`market.klines_1m`**：1-min granularity；coarsened（同 phys_lock counterfactual_exit_audit.py 已用此 fallback）— **DEFAULT for Phase 2c-CM v0.1**
2. **`market.orderbook_snapshots`**（如存在 — 待 E1 verify schema）：sub-second granularity；理想但需 verify 7d 完整覆蓋
3. **WS replay buffer**（`bybit_business_event_replay_harness.py`）：sub-second；需 7d data persisted；最高 fidelity 但需 verify replay infra readiness

**v0.1 採用 1-min klines + reconstruction caveat**：
- 1-min klines `open/high/low/close` 推算 maker dispatch instant 的 reference_price（取 close price 或 vwap）
- Slippage estimate = ±0.5 tick * symbol tick_size（保守，per Bybit V5 market order typical depth-2 slippage）
- **明文 caveat**：1-min granularity 平滑 intra-bar spike → counterfactual delta 為「**改進下界**」（mirror `counterfactual_exit_audit.py` MODULE_NOTE 措辭）
- v0.2 upgrade path：如 `orderbook_snapshots` 7d 覆蓋完整 → 切 sub-second BBO reconstruction

### 3.4 排除規則

以下 fill 從 counterfactual 排除（per AMD §5.5 Phase 2b holdout 顯著性 + QC-SF-5 in-sample overfit 防護）：
- (i) Class C safety path / not_attempted（per §3.1）
- (ii) klines stale (> 24h before fill ts) → degraded mode（delta_bps=None, reason="klines_stale_fallback"；不入 statistical aggregation）
- (iii) Reject sample / abnormal fill latency (> 60s pending) → log 但 stratified（per AC-15）
- (iv) `fee_tier != 0` fills（mainnet promotion 前不混 fee tier；live_demo regime 預設 tier 0）

---

## §4 Statistical Test Protocol

### 4.1 Paired Delta Aggregation

**Per-fill paired delta**: `δ_i = ActualPnL_i − CounterfactualBaseline_i` (in bps)

**Aggregation levels (依優先序)**:
1. **Global**：`δ̄ = mean(δ_i) for all eligible fills` (Class A + B combined)
2. **Per-engine_mode**：`δ̄_demo` / `δ̄_live_demo`（cross-validate Phase 2a vs 2b regime stability）
3. **Per-strategy**：5 strategy（grid / bb_revert / ma / bb_breakout / funding_arb）
4. **Per-exit_reason**：8 exit_reason（per AMD §2.2 positive whitelist）
5. **Per-class**：Class A vs Class B 獨立判 PASS/FAIL

### 4.2 Wilson 95% CI Lower Bound（per AC-14 mechanism）

**用 Wilson CI 不用 normal approximation**：close fill paired delta 樣本 n 通常 < 200/env/7d（per Phase 1b spec §1.2 1.2/h × 24 × 7 = ~200 close fills/env）；Wilson CI 對小 n 更穩。

**SQL pattern**（mirror healthcheck [62] 既有 Wilson 計算 per AC-14 + AC-18）:

```sql
-- 對每個 aggregation cell 計算 Wilson 95% CI lower bound
WITH cell_stats AS (
  SELECT
    engine_mode,
    strategy_id,
    close_maker_eligible_reason,
    COUNT(*) AS n,
    AVG(paired_delta_bps) AS mean_delta,
    STDDEV_SAMP(paired_delta_bps) AS sd_delta
  FROM phase_2c_cm_counterfactual_tmp  -- harness 寫入的臨時表
  WHERE engine_mode = 'live_demo'
    AND fill_ts >= NOW() - INTERVAL '7 days'
  GROUP BY engine_mode, strategy_id, close_maker_eligible_reason
),
wilson_ci AS (
  SELECT
    *,
    -- Wilson CI lower bound (95%, z=1.96)
    -- 不用 binomial proportion Wilson；用 mean ± t-stat * SE 對 paired delta
    -- (paired delta 是 continuous, 非 proportion)
    -- 改用 paired t-test 95% CI lower
    mean_delta - 1.96 * (sd_delta / SQRT(n)) AS ci_lower_95,
    mean_delta + 1.96 * (sd_delta / SQRT(n)) AS ci_upper_95
  FROM cell_stats
)
SELECT * FROM wilson_ci;
```

**Note**: paired delta 是 continuous 不是 binomial proportion；嚴格意義上應用 paired t-test 95% CI（mean ± t * SE）而非 Wilson；本 spec §4.2 SQL 已調整為 paired t-test CI。**「Wilson-CI gating mechanism」對齊 AC-14/AC-18 的指 small-n 安全閾值，實質用 t-stat CI**（PA push back QC-SF-6 措辭：close-maker counterfactual 非 binomial 場景）。

### 4.3 BH-FDR Multiple Testing Correction

**Total cells**: 2 env × 5 strategy × 8 exit_reason × 2 class (A/B) = **160 cells**

**Plus existing Phase 2a/2b 48 cells (per AMD §5.1)**: cumulative cells = 48 + 160 = **208 cells**

**BH-FDR q = 0.10 across 208 cells**（per AMD §5.1 既有 protocol）:
- 對每 cell 算 p-value（paired t-test, H0: δ̄ = 0, H1: δ̄ > 0 one-sided）
- 全局 sort p-value asc → BH adjustment → q-value
- q < 0.10 cell = PASS（discovery）
- q ≥ 0.10 cell = NEUTRAL（不能宣稱 PASS）

**Output**: BH adjustment table 寫入 verdict report，每 cell 列 `n / mean_delta / p / q / verdict`，**禁 cherry-pick**。

### 4.4 Power + MDE（mirror phys_lock §5.1.7）

**MDE pre-calculation**:
- 樣本 estimate: Phase 2b LiveDemo 7d 預估 ~155 close fills/strategy × 5 strategy ≈ 775 total fills
- Class A maker success rate 預估 20-30% (per E3 conservative discount) = ~155-230 Class A fills
- Class B fallback rate 預估 70-80% = ~540-620 Class B fills
- For Class A: n=155 paired-test power for effect size 0.5 bps ≈ 0.4-0.6（borderline；mirror AC-5 small-n ladder）
- For Class B: n=540 paired-test power for effect size 0.5 bps ≈ 0.85-0.95（adequate）

**MDE explicit threshold**:
- Class A: MDE = 0.5 bps for n ≥ 50（PASS gate）；directional (≥ 0) only for n < 30
- Class B: MDE = 0.3 bps for n ≥ 200（taker fallback overhead detection）
- Global combined: MDE = 0.5 bps for n ≥ 250

**Power < 0.8 → CONDITIONAL**：n_eff 不足時，Phase 2c-CM 自動延長 7d → 14d；14d 仍不足 → 補測 LiveDemo Phase 2b 另 7d 直到 n_eff 滿足 MDE 0.5 bps + 80% power.

### 4.5 Regime Stability Check（mirror phys_lock §5.1.6）

**Stability sub-test**: 7d 按時序 split 前 3.5d / 後 3.5d，分別計算 `mean(δ)` directional consistency：
- Both halves directional positive (mean > 0) → PASS
- Either half flips sign → REGIME_FRAGILE warning；不直接 FAIL 但記入 verdict 報告
- 兩半都 negative → FAIL

---

## §5 Acceptance + Reject Criteria

### 5.1 New AC for Phase 2c-CM (建議追加至 Phase 1b spec §11.7 或新 §11.8)

| AC | 內容 |
|---|---|
| **AC-20** | **Global counterfactual mean delta > 0 bps**（per env 7d；Class A + B combined；point estimate primary gate）|
| **AC-21** | **Paired t-test 95% CI lower bound > 0 bps** for global aggregation（per env 7d；CI lower < 0 → BLOCKED）|
| **AC-22** | **BH-FDR 208-cell adjustment**：≥ 50% of eligible cells (n ≥ 50) achieve `q < 0.10`；無任何 cell 出現 `mean_delta < -1.5 bps AND q < 0.10`（顯著負 cell 立即 BLOCK）|
| **AC-23** | **Regime stability**：7d split 前 3.5d / 後 3.5d directional consistency（both halves mean > 0）；任一 half mean < 0 → REGIME_FRAGILE warning，PM 必須 review；兩 half < 0 → BLOCK |
| **AC-24** | **Class A maker success rate empirical ≥ 20%** of Phase 2b LiveDemo 7d close fills；< 20% → n_eff 不足 → 自動延長至 14d；14d 仍 < 20% → BLOCK + spec 修訂 |
| **AC-25** | **Sample power gate**：global n_eff ≥ 250 fills AND Class A n ≥ 50 AND Class B n ≥ 200；不足 → 延期 |

### 5.2 PASS (Promotion to Phase 3 Live)

**全 satisfied**：
1. AC-20 PASS (global mean δ > 0 bps)
2. AC-21 PASS (CI lower > 0)
3. AC-22 PASS (BH-FDR ≥ 50% cells discovery + 0 顯著負 cell)
4. AC-23 PASS (regime stable)
5. AC-24 PASS (Class A rate ≥ 20%)
6. AC-25 PASS (n_eff power adequate)

→ Phase 2c-CM PASS = Phase 1b promotion authorized to Phase 3 Live（per operator sign-off + AMD §11 Phase 3 AC）

### 5.3 REJECT / BLOCK

任一 trigger：
1. **AC-20 FAIL**: global mean δ ≤ 0 → Phase 1b promotion BLOCKED；spec 修訂或 reject
2. **AC-21 FAIL**: CI lower ≤ 0 → 統計顯著性不足；CONDITIONAL：延長至 14d；14d 仍 FAIL → BLOCK
3. **AC-22 FAIL** (signature negative cell): 任一 cell `mean_delta < -1.5 bps AND q < 0.10` → BLOCK（局部負 alpha 不允許繼續 promotion）
4. **AC-23 兩 half FAIL**: regime instability → BLOCK + RCA
5. **AC-24 FAIL**: Class A rate < 20% even after 14d → maker pending 路徑在 live regime 不可靠 → BLOCK + close-maker-first spec 重評
6. **AC-25 FAIL**: n_eff 不足 → 延期 / 補測

### 5.4 CONDITIONAL（局部 finding）

任一單 cell adverse 但不觸發 §5.3 BLOCK：
- (a) per-strategy cell mean_delta < 0 但 q ≥ 0.10 → NEUTRAL（不阻 Phase 3，但需在 verdict 報告 highlight + Phase 3 1-month monitoring 加 sub-check）
- (b) per-exit_reason cell `min_samples_gate=30` 未滿（n < 30）→ NEUTRAL，僅 directional gate
- (c) Class A n < 50 但 ≥ 30 → directional only (mean > 0 即可，無 CI 顯著性要求)

---

## §6 Harness IMPL Contract

### 6.1 File Location + Naming

**Python script**: `helper_scripts/reports/phase_2c_cm_livedemo_counterfactual.py`

**設計理由**: 
- 對齊 `helper_scripts/reports/` 既有 reports script convention（w2_paper_edge_report.py / w_audit_8b_funding_skew_stage0r.py）
- 不入 `program_code/audit/`（後者是 IMPL-time module；Phase 2c-CM 是 promotion gate one-shot script）
- 不是 Rust helper（無 hot-path requirement；純 statistical/SQL aggregation；Python pandas/scipy 更適合）

### 6.2 CLI Contract

```bash
python helper_scripts/reports/phase_2c_cm_livedemo_counterfactual.py \
    --mode {preflight|run|verify} \
    --env live_demo \
    --window-days 7 \
    --out /tmp/phase_2c_cm_verdict.json \
    --bbo-source {klines_1m|orderbook_snapshots|ws_replay} \
    --bh-fdr-q 0.10
```

| 參數 | 默認 | 說明 |
|---|---|---|
| `--mode preflight` | — | dry-run：驗 V094 schema applied / writer 接線 / sample 充足；無 statistical output |
| `--mode run` | — | 完整跑 counterfactual + BH-FDR；輸出 JSON artifact |
| `--mode verify` | — | 對已 run 的 JSON 重跑 invariant check（reproducibility regression）|
| `--env` | `live_demo` | 環境 filter；Phase 2c-CM 限 `live_demo`，但 helper 允許 `demo` 跑 control comparison |
| `--window-days` | `7` | 觀察窗；CONDITIONAL 時自動延長至 `14` |
| `--bbo-source` | `klines_1m` | v0.1 默認；v0.2 切 `orderbook_snapshots` |
| `--bh-fdr-q` | `0.10` | per AMD §5.1 |

### 6.3 Output Schema

**JSON artifact** (`/tmp/phase_2c_cm_verdict.json`):

```json
{
  "spec_version": "v0.1",
  "run_ts": "2026-MM-DDTHH:MM:SSZ",
  "env": "live_demo",
  "window": {"start": "...", "end": "...", "days": 7},
  "bbo_source": "klines_1m",
  "global": {
    "n_eligible": 775,
    "n_class_a": 180,
    "n_class_b": 595,
    "mean_delta_bps": 0.85,
    "ci_lower_95": 0.42,
    "ci_upper_95": 1.28,
    "ac_20": "PASS",
    "ac_21": "PASS",
    "ac_25_n_eff": "PASS"
  },
  "per_engine_mode": {...},
  "per_strategy": [
    {"strategy": "grid_trading", "n": 320, "mean_delta": 1.2, "ci_lower": 0.6, "p": 0.001, "q": 0.012, "verdict": "PASS"},
    ...
  ],
  "per_exit_reason": [...],
  "per_class": {"class_a": {...}, "class_b": {...}},
  "regime_stability": {
    "first_half_mean": 0.92,
    "second_half_mean": 0.78,
    "ac_23": "PASS"
  },
  "bh_fdr_table": {
    "total_cells": 208,
    "cells_q_below_010": 142,
    "discovery_rate": 0.683,
    "ac_22": "PASS",
    "adverse_cells": []
  },
  "ac_summary": {
    "ac_20": "PASS", "ac_21": "PASS", "ac_22": "PASS",
    "ac_23": "PASS", "ac_24": "PASS", "ac_25": "PASS"
  },
  "final_verdict": "PROMOTION_AUTHORIZED",
  "caveats": ["1-min klines reconstruction is improvement lower bound", ...]
}
```

**Markdown verdict report**: `docs/CCAgentWorkSpace/PM/workspace/reports/YYYY-MM-DD--phase_2c_cm_livedemo_counterfactual_verdict.md`

Structure (mirror existing PM verdict report convention):
- §1 Executive Summary (PASS / FAIL / CONDITIONAL)
- §2 Data Source + Eligible Fill Count
- §3 Global Counterfactual Delta + CI
- §4 Per-strategy / Per-exit_reason / Per-class Breakdown (含 BH-FDR table)
- §5 Regime Stability Check
- §6 AC Compliance Table (AC-20..AC-25)
- §7 Caveats + 1-min Granularity Lower-bound Statement
- §8 Recommendation (Promote / Delay / Reject)
- §9 PM Sign-off Placeholder

### 6.4 Effort Estimate

| Track | Effort | Owner |
|---|---|---|
| Python harness (核心統計 + SQL + BH-FDR) | 2.5 person-day | E1 |
| BBO reconstruction (klines_1m fallback) | 0.5 person-day | E1 |
| Unit test (3 fixture: pure-maker / mixed / all-fallback) | 0.5 person-day | E4 |
| E2 review (statistical correctness + non-training invariant grep) | 0.5 person-day | E2 |
| QA fixture validation (against Phase 2b synthetic data) | 0.5 person-day | QA |
| Total | **4.5 person-day** | full chain |

---

## §7 Cross-AMD Compliance

### 7.1 AMD-2026-05-15-02 v0.5 §5.3 Status

**現狀**: AMD-2026-05-15-02 v0.5 **沒有 §5.3** — Phase 2c-CM 是本 spec 提議的 NEW gate。

**v0.6 patch 提議（不在本 PA design scope 內，但本 spec recommend）**:
- 加 §5.3 「Phase 2c-CM LiveDemo Counterfactual Verification (BLOCKER-level per QC-SF-3 extension)」
- 對齊 §5 Stage 0R 表（mirror Stage 0R 但目標 = close-maker promotion 而非 alpha promotion）
- 加 cross-ref `2026-05-XX-XX-phys-lock-live-enable-draft.md` §5.3 為 BLOCKER precedent
- 同步加 §11 引用「§3 Rollout Posture」加 Phase 2c-CM 為 Phase 2b → Phase 3 中間 gate
- AC-1..AC-19 不動；AC-20..AC-25 為 Phase 2c-CM 專屬新 AC

**v0.6 patch effort**: 0.5 person-day（PA cosmetic wording）。

### 7.2 phys_lock AMD draft §5.3 Cross-Reference

本 spec §5 acceptance criteria 設計 mirror phys_lock §5.2 (PASS) + §5.3 (Phase 2c-PL gate) 結構：
- Wilson CI / paired bootstrap → Wilson CI lower (擴大為 paired t-test CI for continuous delta)
- BH-FDR 0.10 → 繼承同 q-value
- Regime stability check → 直接 mirror
- MDE 5 bps → 修為 0.5 bps（close-maker fee saving 量級 ~1 bps，5 bps 對 close-maker 是 unachievable）

### 7.3 QC-SF-3 BLOCKER Origin

QC-SF-3 原始 finding 是針對 phys_lock live enable AMD（QC report `2026-05-16--phys_lock_live_enable_amd_qc_review.md` MUST-FIX-1）。**本 spec 將 QC-SF-3 BLOCKER 結構鏡像到 close-maker-first**，理由 §1.2 三條。

**Operator 取捨 (per §1.1)**:
- 接受 (B): Phase 2c-CM 為新 gate；QC-SF-3 extension 入 AMD v0.6 §5.3
- 拒絕: 維持 close-maker-first 不加 Phase 2c-CM；Phase 2b PASS 直接進 Phase 3（接受 demo silent degradation risk + alpha-deficient regime live 未驗風險）

### 7.4 QC-MF-1 BH-FDR Multiple Testing 對齊

per AMD §5.1: 48-cell BH-FDR → 加 Phase 2c-CM 160-cell extend 到 **208-cell global BH table**。Phase 2c-CM verdict 必引用同一 BH table，不獨立 q-value。

---

## §8 Risk + Edge Cases

### 8.1 Top-2 Risk (per task ask)

| # | Risk | 等級 | Mitigation |
|---|---|---|---|
| 1 | **n_eff 不足 → Class A rate < 20% → counterfactual statistical power < 0.8** | HIGH | AC-24 + AC-25 強制 power gate；CONDITIONAL 延 14d；補測 Phase 2b 至 n_eff 達 MDE 0.5 bps + 80% power |
| 2 | **Demo silent degradation inflates counterfactual delta**（LiveDemo demo endpoint 對 PostOnly reject silent fallback 不對稱 live） | HIGH | mirror Phase 1b AC-15 mainnet probe (≥ 1 sample per reject category)；Phase 2c-CM verdict 必檢 AC-15 PASS 為前置 |

### 8.2 其他 Risk

| Risk | 等級 | Mitigation |
|---|---|---|
| **1-min klines reconstruction 低估 intra-bar volatility** | MEDIUM | 明文 caveat「improvement lower bound」（mirror phys_lock counterfactual_exit_audit.py MODULE_NOTE）；v0.2 upgrade orderbook_snapshots |
| Phase 1b cooldown 互動（per AMD §11.2 reject_cooldown entry/close split） | LOW | counterfactual 假設 cooldown 不變；Phase 2b 跑時 cooldown 已 land（per AMD §8 IMPL Prereq 6）|
| BB rate budget | LOW (0) | counterfactual 不真實 dispatch；只統計推算 |
| phys_lock AMD enable 落在 Phase 2c-CM 觀察窗 | MEDIUM | per §1.3 強制 phys_lock enable 後另 14d clean window；雙 flag 觀察 noise 不可分離 |
| Counterfactual 結果被誤餵 ML training | MEDIUM | E3 grep guard rule (mirror AMD §7 #7)：`grep -nrE '(linucb|scorer|quantile|mlde|dl3).*phase_2c_cm' program_code/` 命中即 reject；harness 不寫 `learning.*` |
| **AC-23 regime stability split 任一 half 翻負** | MEDIUM | NEUTRAL warning + PM review + Phase 3 monitoring 加 sub-check；不直接 BLOCK 但需 RCA |
| **Cherry-pick 風險（per-strategy 選性 report）** | MEDIUM | BH-FDR 208-cell global table 強制全 cell 列出；PM review 必審 cherry-pick；無 cell skip |
| **paired t-test 假設 normality** | LOW | n ≥ 50 CLT；額外 bootstrap CI 補充驗（v0.2 enhancement）|
| **close-maker-first Rust IMPL 未 land（前置依賴）** | BLOCK | 本 spec Phase 2c-CM IMPL 必 Phase 2b PASS 後派；前置 dep chain 完整 |

### 8.3 Edge Cases

| Edge case | 處理 |
|---|---|
| 7d 內 0 Class A fills（catastrophic maker fail） | AC-24 FAIL；自動 BLOCK；spec 修訂 |
| 7d 內 0 Class B fills（catastrophic maker success） | 跳過 Class B AC；Class A 獨立判 |
| `klines_1m` 7d 內有缺口 (> 24h staleness) | klines_stale_fallback；該 fill 排除；report stale rate |
| Fill ts 後 1-min kline 不存在 | 退用 entry 前最近 kline；caveat report |
| `fee_tier != 0` fills 出現（不該有 in live_demo）| 排除 + WARN log |
| operator override (per AMD §2.3 negative whitelist `'operator_force_close*'`) 計入 Class C | 直接排除（safety path） |
| Multi-leg orders (split fills 同 order_id) | 按 order_id GROUP aggregate；以 weighted average fill price 計算 |

---

## §9 ETA + Dispatch Chain

### 9.1 前置依賴

| 條件 | 狀態 | 預估 ready |
|---|---|---|
| V094 IMPL applied + writer upgrade | ⏳ pending E1 IMPL post-Phase 1b RUNTIME ACTIVATOR fix | 2026-05-20+ |
| Phase 1b close-maker-first Rust IMPL deploy | ⏳ pending（per AMD v0.5 §12 note：Phase 1b activator IMPL 卡在 main tree dirty）| 2026-05-19 deploy retry |
| Phase 2a Demo 14d PASS（AC-1..AC-7 + AC-17/18/19）| ⏳ pending Phase 2a 啟動 → 2026-06-02+ | 2026-06-02+ |
| Phase 2b LiveDemo 7d PASS（AC-8..AC-10b）| ⏳ pending Phase 2a PASS → 2026-06-09+ | 2026-06-09+ |
| AMD v0.6 §5.3 patch | ⏳ pending operator sign-off Phase 2c-CM extension | 2026-05-19 (PA cosmetic) |

### 9.2 Phase 2c-CM Dispatch Chain

**強制工作鏈**: `PA spec` (本 spec) → `operator sign-off + AMD v0.6` → `E1 harness IMPL` → `E2 review` → `E4 regression` → `QA fixture validation` → `Phase 2b PASS` → `Phase 2c-CM run` → `PM verdict sign-off`

| Stage | Owner | Effort | 階段 prereq |
|---|---|---|---|
| 1. PA spec v0.1 (本 spec) | PA | DONE | — |
| 2. Operator sign-off + AMD v0.6 patch | PM + Operator | 0.5 day | spec v0.1 land |
| 3. E1 harness IMPL | E1 | 2.5 day | AMD v0.6 + V094 IMPL land |
| 4. E2 review | E2 | 0.5 day | E1 IMPL |
| 5. E4 regression | E4 | 0.5 day | E2 PASS |
| 6. QA fixture validation | QA | 0.5 day | E4 PASS |
| 7. Phase 2b LiveDemo 7d 跑（外部觸發）| Linux runtime | 7d wall-clock | Phase 2a PASS |
| 8. Phase 2c-CM run + verdict | PM + QC | 1 day | Phase 2b PASS + harness ready |
| 9. PM sign-off | PM + Operator | 0.5 day | Phase 2c-CM verdict |

**Total person-day**: 6 person-day (excluding 7d wall-clock for Phase 2b)
**Critical path**: AMD v0.6 + V094 IMPL → E1 harness → Phase 2b → Phase 2c-CM run
**ETA Phase 2c-CM ready to run**: 2026-06-09+ (after Phase 2b PASS)
**ETA Phase 3 Live promotion authorized**: 2026-06-16+ (after Phase 2c-CM PASS + operator sign-off)

### 9.3 阻塞關係

```
PA spec v0.1 (本檔)
    └── Operator sign-off + AMD v0.6 §5.3 patch
            └── E1 harness IMPL (依賴 V094 schema 已 applied)
                    └── E2 review
                            └── E4 regression
                                    └── QA fixture validation
                                            └── Phase 2b LiveDemo 7d 結束（外部 wall-clock）
                                                    └── Phase 2c-CM run
                                                            └── PM verdict + sign-off
                                                                    └── Phase 3 Live promotion (per AMD AC-11..AC-13)
```

---

## §10 16-root + 9-invariant Compliance

### 10.1 16 條根原則

| 原則 | 判定 | 機制 |
|---|---|---|
| #1 單一寫入口 | PASS | Phase 2c-CM 不下單，純 read-only counterfactual |
| #2 讀寫分離 | PASS | 純 `trading.fills` + V094 + `market.klines_1m` read-only；無 INSERT/UPDATE |
| #3 AI 輸出 ≠ 即時命令 | PASS | Phase 2c-CM 不引入 AI 推理；純 statistical post-hoc analysis |
| #4 策略不繞風控 | PASS | counterfactual 不觸 Guardian / RiskConfig |
| #5 生存 > 利潤 | PASS | gate 機制保護 Phase 1b promotion 不在 statistical 不顯著時推 Live |
| #6 失敗默認收縮 | PASS | FAIL → Phase 1b BLOCKED；不允許 promote 即使 sample 不足 |
| #7 學習 ≠ 改寫 Live | PASS（強化）| counterfactual 結果**禁餵 ML training pipeline**（per AMD §7 #7 non-training invariant；本 spec §2.2 顯式禁止）；E3 grep guard rule mandatory |
| #8 交易可解釋 | PASS | counterfactual verdict 全 cell 寫入 JSON artifact + Markdown report；BH-FDR 208-cell table 不允 cherry-pick |
| #9 災難保護 | PASS | 不觸；harness 是 one-shot script 無 long-running state |
| #10 認知誠實 | PASS | 1-min klines reconstruction 明文「improvement lower bound」；regime stability check 不諱言 fragile |
| #11 Agent 最大自主 | PASS | counterfactual gate 不限 Agent 策略 / symbol / timing 自主；只是 Phase 1b promotion 額外 evidence gate |
| #12 持續進化 | PASS | Phase 2c-CM 失敗 → 推動 close-maker-first spec 修訂 + 重評；evidence-driven |
| #13 AI 成本感知 | PASS | counterfactual 無 AI 調用；純 Python pandas/scipy aggregation |
| #14 零外部成本可運行 | PASS | 純 PG + Python + scipy；無 LLM / 外部 API 依賴 |
| #15 多 Agent 協作 | PASS | 不變動 5-Agent；本 spec 是 PA → E1 → E2 → E4 → QA → PM 標準 dispatch chain |
| #16 組合級風險 | PASS | Phase 2c-CM 不引入新 portfolio risk vector；只統計 close fill 行為 |

**結論**: 16/16 PASS；**0 BLOCKER**。

### 10.2 9 條安全不變量

| # | 不變量 | 判定 | 機制 |
|---|---|---|---|
| 1 | Pre-trade audit/replay 必開 | PASS | 不觸（無 trade dispatch）|
| 2 | Lease 必在執行前已 acquired | PASS | 不觸 |
| 3 | 執行回報必落 fills 表 | PASS | V094 audit 已落；本 spec 純讀 |
| 4 | 風控降級 → engine 自動止血 | PASS | 不觸；本 spec 是 promotion gate 不是 runtime path |
| 5 | Authorization 過期 → engine cancel_token | PASS | 不觸 |
| 6 | Mainnet 無 OPENCLAW_ALLOW_MAINNET → spawn 拒絕 | PASS | 不觸 |
| 7 | Bybit retCode != 0 → fail-closed 不重試 | PASS | 不觸 |
| 8 | Reconciler 對賬差異 → 自動降級 paper | PASS | 不觸 |
| 9 | Operator 角色與 live_reserved 缺一即拒 | PASS | Phase 3 promotion 仍需 5-gate + operator sign-off（per AMD §四 hard boundary）|

**結論**: 9/9 PASS；**0 BLOCKER**。

### 10.3 W-C Caveat 2 不變式

- Phase 2c-CM harness **不寫** `agent_spine.*` 任何 table
- counterfactual 結果**不寫** `learning.*` 任何 table
- 純讀 `trading.fills` + `trading.fills.details` + `market.klines_1m` + V094 columns
- E3 grep guard rule（mandatory IMPL phase）:
  ```bash
  grep -nE 'INSERT.*INTO.*(agent_spine|learning)' helper_scripts/reports/phase_2c_cm_*.py
  # MUST be 0 hits
  ```

---

## §11 PA Sign-off

### 11.1 Spec Verdict

**PA verdict**: SPEC v0.1 DRAFT — READY-FOR-OPERATOR-REVIEW

**前置 condition land 後可 IMPL**:
- ⏳ Operator confirm §1.1 Phase 2c-CM naming 取捨 (PA recommend B: suffix disambiguation)
- ⏳ AMD-2026-05-15-02 v0.6 §5.3 patch land (0.5 day cosmetic)
- ⏳ V094 schema applied + writer upgrade land
- ⏳ Phase 1b RUNTIME ACTIVATOR fix (per AMD v0.5 §12 deploy retry)
- ⏳ Phase 2a Demo 14d PASS

### 11.2 主會話 prompt push back（強制呈報）

**Issue 1**: prompt 引用「AMD-2026-05-15-02 v0.5 §5.3 (QC-SF-3 BLOCKER)」**不存在於 close-maker-first AMD**；QC-SF-3 是 phys_lock AMD 的 BLOCKER。  
**PA 修正**: 本 spec proposed Phase 2c-CM 是 NEW gate 並引 QC-SF-3 BLOCKER **結構**到 close-maker-first；需 AMD v0.6 §5.3 patch。

**Issue 2**: prompt 對「Phase 2c」naming 不 disambiguate；phys_lock AMD draft 已用「Phase 2c」指 phys_lock live observation gate。  
**PA 修正**: 採 **Phase 2c-CM** (close-maker) + **Phase 2c-PL** (phys_lock) suffix disambiguation。

**Issue 3**: prompt 提「Wilson 95% CI lower bound」for paired delta；嚴格 Wilson CI 是 binomial proportion，paired delta (continuous) 應用 paired t-test 95% CI。  
**PA 修正**: §4.2 改 paired t-test CI；mechanism gating threshold 對齊 AC-14/AC-18 既有「Wilson-CI gating」措辭以保持 spec 一致性，但實質是 t-stat CI。

**Issue 4**: prompt 將「Wilson CI > 0」當 acceptance threshold；對於 paired delta（mean > 0 gate）正確；但 prompt 將「Wilson CI 跨 0 → 統計 insignificant → BLOCKED」當 reject，PA confirm 此 reject semantic 對齊 phys_lock §5.2 FAIL criteria 2「95% CI 跨 0」。

### 11.3 Required Approvals

| Role | Approval needed | Status |
|---|---|---|
| Operator | §1.1 naming 取捨 + AMD v0.6 §5.3 patch authorize | ⏳ Pending |
| PM | dispatch chain + 6 day effort estimate accept | ⏳ Pending |
| QC | §4 statistical protocol confirm (paired t-test vs Wilson clarification) | ⏳ Pending |
| FA | §10 16-root + 9-invariant compliance confirm | ⏳ Pending |
| MIT | §3.3 BBO reconstruction granularity acceptance (1-min klines lower bound) + non-training invariant E3 grep | ⏳ Pending |
| BB | §3.3 v0.2 orderbook_snapshots 7d 覆蓋 verify (BBO source authority) | ⏳ Pending |

---

## §12 變更歷史

| 日期 | 版本 | 變更 | 作者 |
|---|---|---|---|
| 2026-05-18 | v0.1 DRAFT | 初版 — PA single-agent restart dispatch post-multi-agent worktree race stop；§1.1 naming push back Phase 2c-CM vs Phase 2c-PL；§3 三類 fill 分流 (Class A maker success / B fallback / C safety path)；§4 paired t-test CI + BH-FDR 208-cell；§5 AC-20..AC-25 6 new AC；§6 helper_scripts/reports/phase_2c_cm_livedemo_counterfactual.py CLI contract；§7 cross-AMD compliance + AMD v0.6 §5.3 patch propose；§8 top-2 risk (n_eff 不足 + demo silent degradation) | PA |

---

**Spec total**: 12 sections / ~580 LOC / 6 person-day total effort
**Critical push back**: Phase 2c naming disambiguation + cross-AMD QC-SF-3 source clarification
**Output path**: `srv/docs/execution_plan/2026-05-18--phase_2c_livedemo_counterfactual_harness_spec.md`
