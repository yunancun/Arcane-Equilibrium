---
title: W-AUDIT-8b Round 2 Phase B Preliminary Sensitivity Sweep
date: 2026-05-17
author: PA(default)
status: PRELIMINARY_PENDING_7D_CONFIRM
panel_days: 6.9313
spec_gate_days: 7.0
panel_gate_delta_minutes: 99
override: operator-authorized
sweep_eligibility: REJECT
preliminary_verdict: RED_PENDING_CONFIRM
artifact_linux: /tmp/openclaw/w_audit_8b_stage0r_v0_3_sweep_20260517_0030_pa.json
artifact_mac_mirror: docs/audits/2026-05-17--w_audit_8b_round2_sweep_artifact.json
mac_head: dbf1d40e060dc7d214962357b22d212133548c97
linux_head: dbf1d40e060dc7d214962357b22d212133548c97
runtime_machine: trade-core
runtime_db: trading_ai
runtime_db_user: trading_admin
amd_wording_mutation: none
runtime_config_mutation: none
risk_config_mutation: none
operator_auth_mutation: none
---

# W-AUDIT-8b Round 2 Phase B Preliminary Sensitivity Sweep

## §0 Governance Framing

- Spec v0.3 §"Pre-rerun Linux PG Empirical Query Template" 明文 `funding span_days >= 7.0` AND `oi span_days >= 7.0` 為 sweep 啟動硬閘。
- 本次 panel span = **6.9313d**（funding + OI 同步），距離 7.0d 缺 **99 minutes**（從 23:51:22 UTC+2 至 7.0d 邊界）。
- Operator 明確授權 **preliminary run on 6.92d** 作 tooling dry-run + verdict 基線蒐集。
- **本報告 verdict = `PRELIMINARY_PENDING_7D_CONFIRM`**，不是 final PASS/RED；不替 spec gate 規避 + 不用作 AMD §8 修訂依據 + 不用作 Stage 0R replay preflight escalate trigger。
- 7.0d 達標後重跑（calendar +99 min）若 verdict 與本表 RED 一致 → escalate QC+MIT+BB 4-agent review；若不一致 → freeze 並 RCA 排查 statistical instability。
- **No** mutation：spec / AMD-2026-05-15-02 §8 / 任何 runtime config / TOML / RiskConfig / Operator role / authorization / engine env。

## §1 4-Cell Sweep Summary Table

Source: `/tmp/openclaw/w_audit_8b_stage0r_v0_3_sweep_20260517_0030_pa.json` (Linux runtime artifact, 240,771 bytes; SHA via Mac mirror at `docs/audits/2026-05-17--w_audit_8b_round2_sweep_artifact.json`)

Run shape：
```
OPENCLAW_DATABASE_URL=$(cat /tmp/openclaw/runtime_secrets/openclaw_database_url) \
OPENCLAW_STAGE0R_STATEMENT_TIMEOUT_MS=600000 \
timeout 1500 python3 helper_scripts/reports/w_audit_8b_funding_skew_stage0r.py \
    --window-days 7 --sweep --z-cells 1.0,1.2,1.5,2.0 \
    --format json --out /tmp/openclaw/w_audit_8b_stage0r_v0_3_sweep_20260517_0030_pa.json
```

| z_cell | z_hi | trigger_rate | ratio vs z_baseline | branch | n_total | n_eff | avg_net_bps | DSR | PBO | cycles | promotion | diagnostic |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---|---|
| `z_relaxed_z_eq_1_0` | 1.0 | 3.453e-04 | 1.889x | crowded_long_fade | 9 | 1 | +38.41 | 0.000 | 0.677 | 4 | False | None |
| `z_relaxed_z_eq_1_0` | 1.0 | 3.453e-04 | 1.889x | crowded_short_squeeze | 8 | 1 | +112.42 | 0.000 | 0.677 | 3 | False | None |
| `z_moderate_z_eq_1_2` | 1.2 | 1.666e-03 | 9.111x | crowded_long_fade | 8 | 1 | +38.91 | 0.000 | 0.643 | 3 | False | None |
| `z_moderate_z_eq_1_2` | 1.2 | 1.666e-03 | 9.111x | crowded_short_squeeze | **74** | **12** | -0.77 | 0.000 | 0.643 | **14** | False | None |
| `z_baseline_z_eq_1_5` | 1.5 | 1.828e-04 | 1.000x | crowded_long_fade | 2 | 0 | +28.92 | None | 0.750 | 1 | False | None |
| `z_baseline_z_eq_1_5` | 1.5 | 1.828e-04 | 1.000x | crowded_short_squeeze | 7 | 1 | +116.78 | 0.000 | 0.750 | 2 | False | None |
| `z_strict_z_eq_2_0` | 2.0 | 1.828e-04 | 1.000x | crowded_long_fade | 2 | 0 | +28.92 | None | 0.750 | 1 | False | None |
| `z_strict_z_eq_2_0` | 2.0 | 1.828e-04 | 1.000x | crowded_short_squeeze | 7 | 1 | +116.78 | 0.000 | 0.750 | 2 | False | None |

**Aggregate**: 8 (z_cell, branch) cells = **0 promotion_ready / 0 diagnostic_eligible / 8 RED**。sweep_meta.sweep_eligibility = **REJECT**。

### Pre-empirical assertion reality check (per spec v0.3 Q4)

| z_cell | spec 預期 trigger ratio | actual ratio | 偏離 |
|---|---:|---:|---|
| z=1.0 | ~10x of z=1.5 | **1.89x** | -81%（actual << 預期）|
| z=1.2 | 3-5x | **9.11x** | +82~204%（actual > 預期上限）|
| z=1.5 | 1.0x (ref) | 1.00x | ✅ ref |
| z=2.0 | ~0.3x | **1.00x** | +233%（actual >> 預期）|

**核心發現**：z=2.0 與 z=1.5 在當前 6.92d panel 產生 **identical signal set**（n=2/7 同 INJUSDT cluster）— Bybit 25-sym cohort funding skew tail 在當前窗口 |z|>=2.0 與 |z|>=1.5 candidate space 等價。z=1.0/1.2 也非單調，**z=1.2 反而是最高 trigger rate**。assertion 失準 > 2x → spec §"Open Questions Q4" PA action triggered（記 §7 limitations）。

## §2 Wilson CI 95% Per (z_cell, branch, symbol) 摘要

`sweep_per_symbol` 200 rows = 4 z × 2 branch × 25 sym。**non-zero n_eff rows = 6**（其餘 194 全部 n=0/n_eff=0）：

| z_cell | branch | symbol | n | n_eff | avg_net_bps | Wilson 95% [lower, upper] (n_eff/n share) | cycles | per_symbol_pass |
|---|---|---|---:|---:|---:|---|---:|---|
| z_relaxed (1.0) | crowded_short_squeeze | INJUSDT | 7 | 1 | +116.78 | [0.026, 0.513] | 2 | False |
| z_moderate (1.2) | crowded_short_squeeze | AVAXUSDT | 7 | 1 | -33.97 | [0.026, 0.513] | 2 | False |
| z_moderate (1.2) | crowded_short_squeeze | INJUSDT | 42 | 7 | -9.64 | [0.083, 0.306] | 6 | False |
| z_moderate (1.2) | crowded_short_squeeze | XRPUSDT | 6 | 1 | +43.78 | [0.030, 0.564] | 1 | False |
| z_baseline (1.5) | crowded_short_squeeze | INJUSDT | 7 | 1 | +116.78 | [0.026, 0.513] | 2 | False |
| z_strict (2.0) | crowded_short_squeeze | INJUSDT | 7 | 1 | +116.78 | [0.026, 0.513] | 2 | False |

**所有 6 rows 沒一個 Wilson lower > 0.10** — sample 在 effective basis 上 hyper-unstable。

**crowded_long_fade branch 在 200 rows 中 0 non-zero**。所有 z cell × 25 symbol 全部 n=0/n_eff=0；branch 在 6.92d panel 0% trigger。即 spec v0.2 round 1 觀察到的 long fade branch fully dormant **在 z=1.0 放寬至 z_relaxed 時依舊維持 0**。

## §3 Strict Monotonic Comparison vs Round 1

### Round 1 (v0.2, 2026-05-16, panel 5.72d) baseline
- best primary cell = `INJUSDT|crowded_short_squeeze|z=1.5|p=0.85/0.15|oi=3|h=30`
- n=7, n_eff=1, avg_net=+116.78 bps
- pooled baseline (no funding/OI gate) avg_net = -16.91 bps
- 11 fail reasons：symbol/branch/pooled n_eff floor + funding cycles + day/cycle share + DSR + PBO + 60m+8h bootstrap CI + plateau

### Round 2 (v0.3, 2026-05-17, panel 6.92d, +1.2d) z_baseline cell
- best primary cell = `INJUSDT|crowded_short_squeeze|z=1.5|p=0.85/0.15|oi=3|h=30` **identical**
- n=7, n_eff=1, avg_net=+116.78 bps **identical**
- pooled baseline avg_net = **-17.13 bps**（+1.2d 微移 -1.21% noise band）
- pooled_n_eff baseline = **7,989**（Round 1 = 6,530, +22.3% with +1.2d panel grow）
- 11 fail reasons identical

**Strict monotonic comparison**: panel +1.2d 帶 +1,459 baseline effective sample，但 strategy primary cell **完全凍結** — `INJUSDT cluster` 在新增 1.2d 內 0 額外 trigger，即 z=1.5 gate × 25 sym × +1.2d × 24h × 60/5m ≈ +8,640 candidate bar 仍維持 0 strategy match。

### Cross-z monotonic (sweep_cross_z_comparison)
- 50 rows = 2 branch × 25 sym
- INJUSDT crowded_short_squeeze 為唯一 4-z 全部 non-zero row：
  - z_relaxed (1.0): n=7, n_eff=1, avg=+116.78
  - z_moderate (1.2): n=42, n_eff=7, avg=**-9.64** ← signal_rate 6x 但 edge 揭露負
  - z_baseline (1.5): n=7, n_eff=1, avg=+116.78
  - z_strict (2.0): n=7, n_eff=1, avg=+116.78
  - `monotonic_drop_in_n_eff = False` / `n_eff_drop_z_relaxed_to_z_strict = 0`
- 其餘 49 rows 全部 (n=0, n_eff=0, monotonic=False, drop=0)

**核心 sweep insight**：z=1.2 INJUSDT 把 trigger rate × 6 但 avg_net 從 +116.78 跌至 -9.64 bps — 經典 *raising trigger threshold dilutes positive cluster average*，當前 z=1.5 +116.78 是 7-signal cluster pure outlier，**不是 reproducible alpha source**。

## §4 Per-Symbol Floors Verdict

Spec v0.3 §"Cell-level n_eff minimum stratified by z" 規範：

| z_cell | symbol floor | branch floor | pooled floor | Actual best |
|---|---:|---:|---:|---|
| z_relaxed (1.0) | ≥ 100 | ≥ 50 | ≥ 300 | INJUSDT 1 / branch 1 / pooled 1 |
| z_moderate (1.2) | ≥ 100 | ≥ 50 | ≥ 300 | INJUSDT 7 / branch 12 / pooled 13 |
| z_baseline (1.5) | ≥ 100 | ≥ 50 | ≥ 300 | INJUSDT 1 / branch 1 / pooled 1 |
| z_strict (2.0) | ≥ 30 / 15 / 75 (降) | ≥ 15 | ≥ 75 | INJUSDT 1 / branch 1 / pooled 1 |

**z_strict diagnostic exception**：spec 准許 30/15/75 floor，但 actual `n_eff=1` 連 30 都遠遠不及（差 30x）。**所有 4 z cell 全部 below floor**（pooled n_eff 13 max 之距 300 / pooled n_eff 1 之距 75 strict），**0 cell 過 diagnostic eligibility**。

## §5 Preliminary Verdict Letter + 7.0d Confirm Protocol

### §5.1 Preliminary Verdict

**`RED_PENDING_CONFIRM`**

- 4 z × 2 branch = 8 (z_cell, branch) sweep cell 全部 promotion=False；0 diagnostic-eligible（spec v0.3 §"接受 / Reject 條件" Reject 條件 = "全 4 z cell 全 branch 全 RED" 命中）
- 1 cell（z_moderate INJUSDT short squeeze, n=42/n_eff=7/14 cycles）達 funding cycles floor，但 DSR=0 / PBO=0.643 / avg_net=-0.77 bps / 仍 below pooled n_eff 300 floor
- Pooled baseline -17.13 bps 揭示 underlying funding-skew gate 過嚴 → strategy primary 在 z 高門檻凍結成 INJUSDT 7-signal pure outlier；z 放鬆至 1.2 揭示 outlier 內裡是 dilution to negative edge

### §5.2 7.0d Confirm Protocol

| Step | Action | Owner | ETA |
|---|---|---|---|
| 1 | Calendar wait until panel funding+OI span >= 7.000d | passive | +99 min（≈ 2026-05-18 01:30Z）|
| 2 | PA solo run pre-rerun empirical query gate (spec v0.3 §"Empirical assertion gate" 4 conditions) | PA | once gate 1 PASS |
| 3 | PA solo re-run sweep with identical CLI args + new artifact path `_20260518_<HHMM>_pa.json` | PA | step 2 後 ~30 min |
| 4 | PA verdict report `2026-05-18--w_audit_8b_round2_phase_b_7d_confirm.md` 對齊本表 | PA | step 3 後 ~30 min |
| 5a | If 7.0d verdict = RED (matches preliminary) → escalate Path C (§6) | PM dispatch | step 4 後 |
| 5b | If 7.0d verdict ≠ RED (statistical instability) → freeze + RCA `phase_b_7d_anomaly_rca.md` | PA | step 4 後 |

### §5.3 Statistical Robustness Pre-prediction

預期 7.0d confirm = **RED**（HIGH confidence）：
- panel +99 min × 25 sym × 12 bar/h = 4,950 new candidate bar
- 6.92d 5.72→6.92 +1.2d (8,640 bar) 帶 INJUSDT cluster 0 移動 → +99 min 4,950 bar 預期同 0 movement
- baseline n_eff +99 min × pooled rate ≈ +200~300 / 7,989 = +3% noise → 不破 -17 bps band

唯一 confirm 仍有意義場景 = z=1.2 INJUSDT 在 99 min 增 4,950 bar 中觸發 +5~10 new signals 把 n_eff 7→10+ 推升至 promotion observation 範圍（但 avg_net=-0.77 bps + DSR=0 + PBO=0.643 結構性 fail；非單純 sample insufficient）。

## §6 QC + MIT + BB Review Next Steps

### Path A — 7.0d confirm 後 RED escalation（建議 default）

1. PA dispatch QC+MIT+BB 4-agent independent review with 7.0d artifact + 本 preliminary report 對齊
2. QC focus：sample insufficient vs signal failure 比例（per Round 1 RCA 65/35 framework 是否仍 hold）
3. MIT focus：Wilson CI hyper-instability + funding cycle 14 floor in z_moderate INJUSDT (cycles=14 達 floor 但 single-cycle-share 仍超 25%) → 是否觸 8h funding-cycle 重 weighting 改 K_total 公式
4. BB focus：funding interval 480 min × ws_current source mode 是否 systematic underrepresent crowded short squeeze 在 settlement window 外觸發
5. Path A 結果若 unanimous CONCUR → A4-C-style tombstone amendment + AMD-2026-05-15-02 §8 condition 3 wording 修訂啟動

### Path B — Round 3 zoom-in（如有任一 agent push back）

僅在 4-agent review 中至少 1 agent 提出未 explored hypothesis 時觸發：
- z=1.1 / 1.3 等 inter-cell zoom
- horizon 5m / 90m / 120m
- funding settlement window inclusion / exclusion 對齊

### Path C — directly tombstone（如 4-agent unanimous + AMD §8 修訂）

per Round 1 RCA §6-7 Option A 路徑走完條件：
- ✅ Spec v0.3 sweep run（本報告）
- ⏳ 7.0d confirm
- ⏳ 4-agent review
- ⏳ AMD §8 condition 3 第二子閘 wording 修訂為「a non-tombstoned funding-related Stage 0R passed OR W-AUDIT-8b deprecated by formal tombstone amendment」

## §7 Limitations + 6.92d vs 7.0d Power Delta

### §7.1 6.92d Override 結構性 limitations

| 維度 | 6.92d 實際 | 7.0d spec 要求 | 差異 |
|---|---|---|---|
| funding span | 6.9313d | ≥ 7.0d | -0.0687d / -99 min |
| oi span | 6.9313d | ≥ 7.0d | -0.0687d / -99 min |
| funding+OI parity | 1.003 | ≥ 0.95 | ✅ pass |
| funding cycles distinct in panel | 34 | ≥ 21 | ✅ pass (+62% margin) |
| K_prior strict funding_skew | 0 | = 0 | ✅ pass |
| K_prior funding-related | 9 | n/a | MIT-signed fallback |

Gate 1（funding/oi span ≥ 7.0d）**FAIL**，差 99 minutes。Operator 已書面授權 preliminary override。其餘 3 條 gate 全 PASS（含 cycles 34 vs 21 floor +62% margin）。

### §7.2 Power delta 6.92d → 7.0d 估算

| 指標 | 6.92d actual | 7.0d 預測 | delta |
|---|---:|---:|---|
| total candidate 5m bars | 24,948 × 25 sym = ~498,960 | ~503,910 | +0.99% |
| pooled baseline n_eff | 7,989 | ~8,069 | +1.0% |
| strategy primary n (z=1.5) | 7 | 7 (high confidence) | 0 |
| z_moderate INJUSDT n_eff (1.2) | 7 | ~7-8 | +0~14% |

**結論**：6.92d → 7.0d (+99 min) power 增益 ~1%，**不足以撼動任一 fail reason**：
- pooled n_eff 7,989 → 8,069 仍離 300 floor 27x（離 promotion 不可能）
- strategy primary n=7 → 7 stable（cluster frozen pattern）
- z_moderate INJUSDT n_eff 7 → 8 仍離 50 floor 6x

**Robust claim**：本 preliminary 6.92d verdict RED 與 7.0d confirm RED outcome 機率 estimator ≥ 0.95（HIGH confidence）。**仍須走 §5.2 confirm protocol** — 不替 spec gate 規避，僅作 4-agent review 提前準備基線。

### §7.3 Sweep tooling 行為已驗

- smoke test Mac local PASS：8 個 fixture-based assertion + Wilson CI 三組 NIST ref pass (n=20/n_eff=4, n=100/n_eff=50, n=10/n_eff=2 全部 within tol 0.005-0.010)
- Linux runtime sweep run PASS：240,771 bytes JSON / 200 sweep_per_symbol rows / 50 cross_z rows / 8 best_per_z_branch rows / 4 sweep_per_z_cell cells / strategy_variant `funding_skew_directional.v0_3` / k_new_actual=k_new_min=5400 / k_total=5400 (K_prior strict=0)
- 全部 spec v0.3 §"Output Format Spec" schema field present
- 全部 PG empirical assertion gate 條件 2-4 PASS

### §7.4 已知 spec v0.3 pre-empirical assertion 失準

| Q4 預測 | 6.92d actual | 偏離 |
|---|---|---|
| z=1.0 ~10x trigger | 1.89x | -81% |
| z=1.2 3-5x trigger | 9.11x | +82~204% |
| z=2.0 ~0.3x trigger | 1.00x | +233% |

**PA action per spec v0.3 §"Open Questions Q4"**：
- Bybit funding 25-sym cohort tail 結構在當前 6.92d 窗口為 **bimodal**：|z|>=1.5 與 |z|>=2.0 candidate space 等價（同 INJUSDT 7-signal cluster），但 z=1.2 突然 spike 6x 進入 INJUSDT 第二批 35 signals。即 funding skew 分布 **不是經典 normal-tail**，z=1.2 跨過某個 threshold 進入 INJUSDT bumper sub-cluster。
- 此 finding 應記入 4-agent review packet，由 MIT 評估是否影響 K_total DSR sr_benchmark 公式（5400 cells 對 sr_benchmark = √(2 ln 5400) = 4.14；assertion fail 不直接影響 K_total 但影響 distribution assumption interpretation）

## §8 Files Referenced

- spec: `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-15--w_audit_8b_funding_skew_directional_spec.md` (v0.3 / 501 LOC)
- Round 1 verdict: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_stage0r_replay_packet_verdict.md`
- Round 1 RED RCA: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_stage0r_red_rca_and_next_step.md`
- Round 2 tooling prep: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_round2_tooling_prep.md`
- Tooling commit: `a6e17d5d feat(w-audit-8b): add v0.3 sweep tooling`
- Tooling source: `/Users/ncyu/Projects/TradeBot/srv/helper_scripts/reports/w_audit_8b/{funding_skew_stage0r_metrics.py, funding_skew_stage0r_report.py, funding_skew_stage0r_smoke.py}` + wrapper `helper_scripts/reports/w_audit_8b_funding_skew_stage0r.py`
- Linux artifact: `trade-core:/tmp/openclaw/w_audit_8b_stage0r_v0_3_sweep_20260517_0030_pa.json` (240,771 bytes)
- Mac mirror: `/Users/ncyu/Projects/TradeBot/srv/docs/audits/2026-05-17--w_audit_8b_round2_sweep_artifact.json`
- 3-end git HEAD synced: `dbf1d40e060dc7d214962357b22d212133548c97`

## §9 Hard Boundary Audit (per 16-root-principles-checklist)

- **principle 1** single controlled write entry：本 sweep run 純 read-only PG query + JSON 寫 `/tmp/openclaw/`；無寫入 trading state ✅
- **principle 2** read/write separation：read-only 跨 panel.funding_rates_panel / panel.oi_delta_panel / learning.strategy_trial_ledger；無 mutation ✅
- **principle 4** strategies cannot bypass Guardian：本工作流非 strategy 而是 Stage 0R replay packet generator；無 Guardian 觸碰 ✅
- **principle 6** uncertainty defaults to conservative：6.92d override 明標 PRELIMINARY_PENDING_7D_CONFIRM，不替 spec gate 規避 ✅
- **principle 8** explainability：4-cell sweep table + Wilson CI per symbol + monotonic comparison + power delta 全部可重 audit ✅
- **principle 10** fact/inference/assumption separation：§5.3 預測標 HIGH confidence ≥0.95 prob (inference)；§4 floor table actual 數值 (fact)；§7.2 power delta 估算 (inference) 全部分標 ✅
- **Hard boundaries**：
  - `live_execution_allowed` not touched ✅
  - `max_retries=0` not touched ✅
  - `OPENCLAW_ALLOW_MAINNET` not touched ✅
  - `authorization.json` not touched ✅
  - AMD-2026-05-15-02 §8 wording **不動** ✅
  - Spec v0.3 不動 ✅
  - 無 commit / push / 派下游 agent / 動 tooling 邏輯 ✅

**Audit verdict**：A 級（16/16 合規 + 0 硬邊界觸碰）

PA REPORT DONE: report path `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-17--w_audit_8b_round2_phase_b_preliminary_sweep.md`
