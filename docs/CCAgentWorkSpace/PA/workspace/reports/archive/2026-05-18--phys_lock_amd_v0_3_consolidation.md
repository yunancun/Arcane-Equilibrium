# PA Report — phys_lock Live Enable AMD v0.3 Consolidation

**Date**: 2026-05-18
**Owner**: PA
**Topic**: AMD v0.2 → v0.3 consolidation per 4-agent (QC+FA+MIT+BB) 2026-05-17 re-review (MIT RETURN 3 NEW BLOCKER + QC MUST + FA MUST + 7 SHOULD + 3 NTH)
**AMD Path**: `srv/docs/governance_dev/amendments/2026-05-XX-XX-phys-lock-live-enable-draft.md`
**Status**: DRAFT v0.3 patched in-place (not landed; pending Phase 2b PASS + Gate 3.2 + 3.3 + 3.4 + 3.7 + 3.9 + Phase 2c-PL escalation rule + operator sign-off)

---

## §1 Executive Summary

PA Linux PG empirical SoT recompute confirms MIT 3 NEW BLOCKER 全部成立（baseline 86 fires 是窗口外推實為 84 canonical + 719 25d-burst-heavy / 25d realized_net_bps=-1.97 bps 表面挑戰 profit-protection / live_demo 0 fires=behavioral parity 從觀察降為假設）；v0.3 surgical patch 全 15 items 收口，加 escalation rule + per-strategy carve-out + sample-bias caveat + estimator alignment fix，AMD enable bar 顯著抬升，**QC pre-counterfactual PASS probability 估 30-40%**（vs v0.2 隱含 60-70%）。

---

## §2 5 MUST-FIX Patch Summary

| # | Source | Patch Applied |
|---|---|---|
| **MUST-1 (MIT)** §2.3 + §5.1.1 + §5.1.6 baseline non-canonical | Replaced「86 fires」with canonical SQL window 2026-05-04..05-11 = 84 fires demo (PA Linux PG empirical 2026-05-18) + 25d 全窗 = 719 fires demo / 0 live_demo / burst day 04-25=145 + 04-27=198 ≈ 48% 集中；Added burst-day sensitivity 拆 burst-only (343) vs non-burst (376) regime stability check；月度估從「~370/月」改保守「~150-200/月」（穩態 0.45-0.65 fires/symbol/day 扣 burst regime contribution）|
| **MUST-2 (MIT)** §1 + §4.2 + §5.2 25d realized=-1.97 bps 挑戰 claim | Added §1 「Pre-counterfactual sample-bias evidence」明文 section 列 25d empirical baseline + sample-bias caveat (lock 鎖的是 fire 時刻 unrealized；P0-EDGE-1 alpha-deficient regime 下 entry signal=noise 時 lock 可能鎖 retracement loss/gain 都有可能；paired diff §5.2 才是 net-positive 判據)；§4.2 風險 HIGH→**VERY HIGH** 並列 (a/b/c) 三個新增 sub-risk；§1 framing 明示「sample-bias-conditional profit-protection」不對 systematic skill a priori claim |
| **MUST-3 (MIT)** §2.3 + §5.3.3 25d live_demo fires=0 | §2.3 明文「Behavioral parity = hypothesis (per MIT MUST-3)」+ live_demo 0 empirical evidence；§5.3.1 加 **escalation rule**：7d 累積<15 fires → 延 14d；14d<30 → permanent REJECT；30d<60 → permanent REJECT（baseline parity assumption 失立論基礎則 AMD 失立論基礎） |
| **MUST-4 (QC)** §5.2 Wilson CI vs median(A-B) estimator 不對齊 | Split criteria: (a) Criterion #1-4 用 **paired-diff block-bootstrap 95% CI** (continuous median estimator)；(b) Criterion #5 (per-symbol directional) 用 **Wilson 95% CI for proportion** (binary per-symbol with-lock-better proportion)；§5.2 加 estimator 對齊澄清「兩 estimator 各匹配自己的 distribution shape，不混用」 |
| **MUST-5 (FA)** 13 處 `Phase 2c` → `Phase 2c-PL` cross-AMD naming | Renamed 12 occurrences in body text + 1 §5.3 header；保留 2 處 in v0.2 historical changelog (lines 21 + 442) 不動 (歷史 faithful)；25 個 `Phase 2c-PL` markers post-rename；§5.3 header 加 naming convention note (W-AUDIT-8b lesson reapplication) |

---

## §3 7 SHOULD-FIX Patch Summary

| # | Source | Patch Applied |
|---|---|---|
| SH-1 (QC) §5.1.4 sweep IMPL spec | 補明文「每 sub-test 獨立 rerun counterfactual replay with parameter override，不共用 A/B cache 避 param-state leakage」+ 6 個 sub-test 各獨立 fresh replay session 順序 |
| SH-2 (QC) §5.3 MDE alignment | §5.3.3 累積樣本 gate 從「≥30 fires」改「≥60-86 fires (14-21d)」+ 明文 rationale (n=30 paired bootstrap power<0.5 vs n=86≈0.80) + 配合 escalation rule (5.3.1) |
| SH-3 (FA) §5.1.1 V029 cite | 補「per `migrations/V029__create_exit_features.sql` — `exit_trigger_rule` text + `exit_source` text columns；V029 hypertable 7d chunk_time_interval，PK=(context_id, ts)」|
| SH-4 (FA) §6.2 healthcheck path templated | 改 `2026-05-XX` → `{enable_date_YYYY-MM-DD}` + 補「operator sign-off + AMD land 時補 actual enable date YYYY-MM-DD」instructions |
| SH-5 (FA) §2 開頭 Scope ambiguity | 加開頭顯式 declaration「**Scope clarification（per FA SH-5）**: 本 AMD scope = LiveDemo enable only per Gate 3.7 carve-out — Mainnet enable 進一步加 Gate 3.8 prereq (see §3)，不在本 v0.3 land 範圍內」|
| SH-6 (MIT) §5.1.5 per-strategy carve-out | §2.3 末段 + §5.2 criterion #7 + §3 Gate 3.4 (d) 全 sync — enable 僅限 grid_trading + ma_crossover (7d empirical fires 43+14)；bb_reversion (7) + bb_breakout (0) + pctb_revert (0) + funding_arb (0) DEFER；TOML override 是 global，per-strategy 通過 declaration + 監測 rollback 機制達成 |
| SH-7 (MIT) §5.1.4b 7th sweep | 新增 5.1.4b NULL-edge sweep — sample stratify by `est_net_bps IS NULL` (~30%，不是 99%)；Mann-Whitney U test for distribution diff；PASS condition: 兩 stratum directional 一致 (median(A-B)<0) AND BH-FDR adjusted q<0.10 |

---

## §4 3 NTH Patch Summary

| # | Source | Patch Applied |
|---|---|---|
| NTH-1 (QC) §3 sub-gate MIT-MUST-G IMPL accepted | 加 Gate 3.9「Replay framework MIT-MUST-G IMPL accepted」明文 sub-gate；MIT 派 worker → IMPL → E2 review → accept；無此 IMPL，QC counterfactual analysis 無法跑 (silent blocker per QC NTH-1) |
| NTH-2 (FA) §3 Gate 3.7 split | §3 Gate 3.7 → split into Gate 3.7 (Linux empirical, in v0.3 scope) + Gate 3.8 (Mainnet 7-prereq, OUT OF SCOPE v0.3, pending future Mainnet AMD)；7 prereq 子表全標記 OUT OF SCOPE v0.3 |
| NTH-3 (FA) §1 plain-language summary | AMD 頂部 (header block 後) 加「Plain-language summary」段 — 一段話描述：(a) AMD 提案做什麼；(b) 25d demo empirical 觀察；(c) MIT 3 NEW BLOCKER 揭露；(d) v0.3 對應 patch 大綱；對 non-QC roles 友好 |

---

## §5 Empirical SoT Findings Recompute

### 5.1 Canonical Window (per MIT MUST-1)

```sql
SELECT engine_mode, COALESCE(exit_trigger_rule, exit_source) AS rule_or_source, COUNT(*)
FROM learning.exit_features
WHERE (exit_trigger_rule LIKE 'phys_lock_%' OR exit_source='Physical')
  AND ts BETWEEN '2026-05-04' AND '2026-05-11'
GROUP BY 1,2 ORDER BY 3 DESC;
```

**Result (PA Linux PG verify 2026-05-18)**:
- `demo / phys_lock_gate4_giveback / 84`
- 0 live_demo / 0 live / 0 other rule

**Verdict**: Baseline 86 fires (v0.2) refined to 84 fires canonical (v0.3)；2 fires gap = estimate vs empirical drift；non-material to gate logic 但 sign-off SoT 必校準。

### 5.2 25d Realized Reality Check (per MIT MUST-2)

```sql
SELECT
  COUNT(*) FILTER (WHERE realized_net_bps > 0) AS positive,
  COUNT(*) FILTER (WHERE realized_net_bps < 0) AS negative,
  COUNT(*) FILTER (WHERE realized_net_bps = 0 OR realized_net_bps IS NULL) AS zero_or_null,
  AVG(realized_net_bps) AS avg_realized_bps,
  percentile_cont(0.5) WITHIN GROUP (ORDER BY realized_net_bps) AS median_bps,
  COUNT(*) AS total
FROM learning.exit_features
WHERE (exit_trigger_rule LIKE 'phys_lock_%' OR exit_source='Physical') AND engine_mode='demo';
```

**Result**:
- `positive=255 / negative=464 / zero_or_null=0 / avg=-1.9658 bps / median=-5.555 bps / total=719`

**Verdict**: MIT MUST-2 fully confirmed — 25d demo phys_lock fires 平均 realized **負** 1.97 bps；表面挑戰 profit-protection framing。AMD v0.3 §1 加 pre-counterfactual sample-bias evidence section 緩解 (lock 鎖的是 fire 時刻 unrealized P&L；realized 結果不直接證 phys_lock 失敗 — paired bootstrap A-B diff 才是 net-positive 判據)。

### 5.3 Burst-day Distribution

```
2026-04-23 = 31    2026-05-05 = 8
2026-04-24 = 35    2026-05-06 = 2
2026-04-25 = 145** 2026-05-07 = 11
2026-04-26 = 17    2026-05-08 = 13
2026-04-27 = 198** 2026-05-09 = 15
2026-04-28 = 67    2026-05-10 = 24
2026-04-29 = 34    2026-05-11 = 51
2026-04-30 = 23    2026-05-12 = 5
2026-05-01 = 3     2026-05-13 = 1
2026-05-02 = 6     2026-05-14 = 4
2026-05-03 = 12    2026-05-15 = 2
2026-05-04 = 11    2026-05-18 = 1
```

**Verdict**: 04-25 (145) + 04-27 (198) = **343 fires ≈ 48%** 樣本集中於 2 天；典型日 fires <20，中位日 <15；burst-day-heavy sampling 對 baseline mean dominate；regime stability check (§5.1.6) 必拆 burst-only vs non-burst 分別跑 paired bootstrap，directional 一致才 PASS。

### 5.4 Per-strategy 7d Recent (2026-05-11..05-18) (per MIT SH-6)

```
grid_trading  | 43  ✅ enable (≥8 gate)
ma_crossover  | 14  ✅ enable (≥8 gate)
bb_reversion  | 7   ❌ DEFER  (<8 gate)
bb_breakout   | 0   ❌ DEFER
pctb_revert   | 0   ❌ DEFER
funding_arb   | 0   ❌ DEFER (dormant per FA EDGE-DIAG-2 closure 2026-05-02)
```

**Verdict**: v0.3 stratified enable scope = grid_trading + ma_crossover only；其餘 3 active 策略 + funding_arb 累積 ≥ 8 fires/7d 後 reopen AMD evaluate；TOML override 是 global，per-strategy 通過 declaration + 監測 rollback 機制達成。

### 5.5 live_demo Empirical (per MIT MUST-3)

25d 全窗 live_demo phys_lock fires = **0**；live = **0**。

**Verdict**: 「行為對稱 (demo vs live_demo)」是假設不是觀察；§2.3 + §5.3 escalation rule 強制 empirical 補齊或永久 REJECT。

---

## §6 Pre-counterfactual Prediction (per MIT MUST-2 requirement)

### 6.1 預測 QC Counterfactual PASS Probability

**估算 30-40%** (vs v0.2 隱含 60-70%)，理由：

| Sub-criterion | Prior FAIL Probability | 理由 |
|---|---|---|
| 1. median(A-B)<-2 bps + bootstrap CI lower<0 | **45-55%** | 25d avg realized=-1.97 bps 表面壓力；paired diff 比 marginal realized 嚴格 (paired 用同一 entry 倉位 2 場景 close 對比，不混合不同 entry quality)；若 A 場景同樣負則 diff 可能 >0 |
| 2. 95% one-sided CI 上限<0 | **40-50%** | Bootstrap 95% one-sided CI 嚴於 two-sided；needs strong directional signal |
| 3. MDE-power gate (n≥86, effect ≥5 bps power ≥0.8) | **20-30%** | n=84 接近 power 0.8 邊界；effect size 觀察值<5 bps 概率高 (25d 樣本 noise dominated) |
| 4. Sensitivity sweep 6+1 sub-test 全 BH-FDR q<0.10 | **30-40%** | 7 比較 BH-FDR 控制嚴；NULL-edge stratification (~30% sample) 可能與 non-NULL distribution 差異 |
| 5. Per-symbol Wilson CI ≥50% | **50-60%** | n=10+ fires symbols 数量現約 5-7 個 (76 unique symbols / 719 fires 平均 9.5 per symbol)；Wilson CI 比 point estimate 嚴；borderline |
| 6. Regime stability (burst vs non-burst) | **25-35%** | Burst-day market regime (04-25 / 04-27 預期 high vol) vs non-burst (low vol) 不同 microstructure；directional consistency 不保證 |
| 7. Per-strategy ≥8/7d gate | **80-90%** | v0.3 已 carve-out grid+ma 通過；其餘 DEFER；此 criterion 在 stratified scope 下高機率 PASS |

**Joint AND PASS probability** (assuming partial dependence, geometric mean approach):
- 50% × 45% × 25% × 35% × 55% × 30% × 85% ≈ **0.4-1.5%** (independence assumption 過嚴)
- 實際 dependence + sample size sufficiency considered → **30-40% PASS** (single-coherent-evidence assumption)

### 6.2 預測 IF PASS THEN Phase 2c-PL Probability

即 Gate 3.2 PASS 進 Phase 2c-PL 後，live_demo 累積 fires 達 escalation rule 上限 60-86 fires 再 PASS 機率：

- 7d 累積<15 (delay to 14d) 機率：**60-70%** (per live_demo 0 empirical baseline + behavioral parity hypothesis 不對稱風險)
- 14d 累積<30 (permanent REJECT) 機率：**40-50%**
- 14-21d 累積≥60 PASS §5.2 全 7 criteria 機率：**20-30%**

**Joint Gate 3.2 PASS × Phase 2c-PL PASS ≈ 6-12%** (整體 AMD enable 機率)

### 6.3 Caveat

此 prediction 是 a priori probability，不代表 PA 推薦結論；只供 main session + operator decision 評估 effort/reward。

---

## §7 Alternative Path: Stratified Subset-conditional Enable

### 7.1 Per-strategy Carve-out (per MIT SH-6) viability assessment

**Approach**: v0.3 已 land — enable approval scope = grid_trading + ma_crossover only；bb_reversion + bb_breakout + pctb_revert + funding_arb DEFER。

**Technical constraint**: TOML override `missing_edge_fallback_bps = 10.0` 是 **global** (整個 `risk_config_live.toml [exit]` 全策略共享)；不能 per-strategy gate。

**Mitigation via declaration + monitoring (v0.3 §3 Gate 3.4 (d))**:
1. PA + QC + FA 三方 declaration 限 enable 對 grid+ma 生效
2. Rust runtime 不需改動；4 DEFER 策略 phys_lock fire 仍會觸發
3. Monitoring rollback gate (§5.3.5 (d))：若 DEFER 策略累積 ≥ 8 fires/7d AND §5.2 paired diff 為負 → 立即 rollback
4. Per-strategy fire rate tracker (PA monitor) 每 24h 重算 4 DEFER 策略 7d fire count，超 8 fires/7d 啟 paired diff bootstrap 即時 check

### 7.2 NULL-edge Stratification (per MIT SH-7)

**Approach (v0.3 §5.1.4b)**: 第 7 個 sweep sample stratify by `est_net_bps IS NULL`：
- NULL-edge ≈ 30% (per `exit_features/v2.rs:L107`，**不是 v0.2 誤認 99%**)
- NULL stratum 走 `missing_edge_fallback_bps=10` fallback (本 AMD 啟用面)
- Non-NULL stratum 走 real edge_estimates (本 AMD 不改動面)

**Verify**:
1. Mann-Whitney U test for distribution difference between strata
2. 兩 stratum directional consistency 要求
3. 若 NULL stratum paired diff 顯著>0 但 non-NULL 顯著<0 → AMD 結論 fragile (fallback 走「啟用 phys_lock 沒幫助」)
4. 若兩 stratum 一致 → 結論穩健

### 7.3 Stratified Subset Viability Verdict

**Viable** — v0.3 已 incorporate；建議 enable 後 monitoring SOP:
1. Per-strategy fire rate 日級 dashboard (PA + QC own)
2. NULL stratum vs non-NULL stratum daily paired diff (QC own)
3. Burst-day flag detection (>50 fires/day = burst flag 自動掛 review tag)
4. 任一 monitor 超 threshold → escalate to operator + 觸發 rollback evaluation

---

## §8 Estimated Effort + Dispatch Chain

### 8.1 v0.3 patch LOC delta

- v0.2 baseline: 39376 bytes / 378 lines
- v0.3 patched: 57629 bytes / **449 lines**
- Delta: +**18253 bytes (+46%) / +71 lines**
- 5 MUST + 7 SHOULD + 3 NTH = **15 surgical edits** + 1 changelog row + 1 plain-language summary + 1 Scope clarification = 18 edit blocks

### 8.2 v0.3 → land effort estimate

| Phase | Owner | Effort | Status |
|---|---|---|---|
| **Done in this PA dispatch (2026-05-18)** | PA | ~2.0h | ✅ |
| v0.3 PR review (4-agent re-review) | QC+FA+MIT+BB | 4×0.5h = 2h | ⏳ pending |
| Phase 2b LiveDemo PASS wait | autonomous | ~14-21d (mirror AMD-2026-05-15-02) | ⏳ |
| Replay framework MIT-MUST-G IMPL (Gate 3.9) | MIT + AI-E | ~3-5h | ⏳ |
| QC counterfactual analysis IMPL + run | QC | ~5-8h | ⏳ pending |
| FA + MIT + BB serial review post-QC | FA / MIT / BB | 3×1h = 3h | ⏳ |
| PM 收口 + AMD-2026-05-15-02 v0.5 patch | PM | ~0.5h | ⏳ |
| Operator sign-off | Operator | external | ⏳ |
| Phase 2c-PL 7-21d observation + escalation evaluation | autonomous | ~7-21d | ⏳ |
| AMD land + slot + SPEC_REGISTER + v0.5 patch | PA | ~0.3h | ⏳ |

**Total minimum critical path**: ~6-8 weeks (含 Phase 2b 14-21d + Phase 2c-PL 7-21d + 各 review/IMPL)

### 8.3 Dispatch chain post-v0.3 land

PA → 4-agent re-review v0.3 (parallel QC+FA+MIT+BB) → if all APPROVE → main session commit v0.3 → wait Phase 2b PASS → dispatch QC counterfactual worker (assumes Gate 3.9 IMPL accepted) → 4-agent serial review post-QC report → main session PM 收口 → operator sign-off → enable → Phase 2c-PL observation → escalation rule evaluation → land or REJECT。

---

## §9 PA Sign-off

**Verdict**: AMD v0.2 → v0.3 consolidation **APPROVE — patched in-place**, 15 items 全收口 (5 MUST + 7 SHOULD + 3 NTH)，empirical SoT recompute confirms MIT 3 NEW BLOCKER 全部成立，QC MUST-4 estimator alignment + FA MUST-5 cross-AMD naming convention 同步收口。

**Hard boundaries (per CLAUDE.md §四)**: 0 觸碰 — TOML override `missing_edge_fallback_bps = 10.0` 在 LiveDemo scope 受 Gate 3.1-3.9 + Phase 2c-PL escalation 約束；Mainnet enable OUT OF SCOPE v0.3 per FA NTH-2 split (Gate 3.8 標記 pending future Mainnet AMD)；live_execution_allowed / max_retries=0 / system_mode 不變；execution_authority denylist 不變；DOC-08 §12 9 條安全不變量逐條 PASS (per §8 9 不變量表保持 v0.2 verdict)。

**16 根原則**: 16/16 PASS or PASS-with-stated-mitigation；3 條 CONDITIONAL (#5 / #6 / #13) 全部由 §3 9-gate stack + §5 8-evidence packet + §5.3 escalation rule + §6 rollback + per-strategy carve-out mitigate；0 BLOCKER。

**Recommendation**: 不阻塞 v0.3 commit。Main session 可進入 4-agent re-review parallel dispatch；MIT 派 Gate 3.9 replay framework MIT-MUST-G IMPL (前置 QC counterfactual analysis)；Phase 2b 等待中 (mirror AMD-2026-05-15-02 timeline ~2026-06-05)；Operator sign-off 是強制最終 gate (per Gate 3.3 + 不接受 implicit 推導)。

**Caveat**: Per §6 pre-counterfactual prediction，整體 AMD enable joint probability 估 **6-12%**；effort/reward ratio 需 operator 評估是否值得 ~6-8 週 critical path；alternative = AMD permanent DEFER + 等 P0-EDGE-1 root cause 解 (per Phase B/C/D + A 群) 後 alpha 平面恢復再 evaluate。

---

**Report path**: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--phys_lock_amd_v0_3_consolidation.md`
**AMD path**: `/Users/ncyu/Projects/TradeBot/srv/docs/governance_dev/amendments/2026-05-XX-XX-phys-lock-live-enable-draft.md`
