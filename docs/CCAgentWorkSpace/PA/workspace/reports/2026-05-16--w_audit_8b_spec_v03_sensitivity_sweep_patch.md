# PA — W-AUDIT-8b Spec v0.3 Sensitivity Sweep Patch + Round 2 Run Plan

**Date**: 2026-05-16
**Author**: PA(default)
**Status**: PA DESIGN DONE — Phase 1 v0.3 spec patch land + Phase 2 round 2 run plan deferred to panel ≥ 7d
**Inputs**:
- v0.2 spec base `srv/docs/execution_plan/2026-05-15--w_audit_8b_funding_skew_directional_spec.md`
- RED RCA `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_stage0r_red_rca_and_next_step.md`
- Round 1 run plan `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_stage0r_run_plan.md`
- Round 1 verdict (RED) `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_stage0r_replay_packet_verdict.md`
- Linux PG empirical query 2026-05-16 19:00Z（panel funding 205,051 rows, 5.98d span；OI 205,821 rows）
- AMD-2026-05-15-02 §8 condition 3 strict AND 3-gate

**Verdict**：Phase 1 spec v0.3 patch land；Round 2 sweep run plan deferred 至 panel ≥ 7d window (~2026-05-17 23:30Z calendar +1.02d)。**不破** AMD-2026-05-15-02 §8 condition 3 wording。**不 tombstone** W-AUDIT-8b（Option A 未走完，過早 tombstone 浪費 sibling 已 land 1034 LOC + 4-agent hardening assets）。**不 pivot** 8c/8a Phase D（per RCA §4 "no near-term acceleration available"）。

---

## §1 Phase 1 結果：spec v0.2 → v0.3 patch land

### 1.1 Patch summary

`docs/execution_plan/2026-05-15--w_audit_8b_funding_skew_directional_spec.md` 由 v0.2 195 行擴至 v0.3 501 行（+306 行，1.57x growth），新增以下 SBT：

| 新增節 | 行範圍 | 主旨 |
|---|---:|---|
| `## Stage 0R v0.3 Trigger Gate Sensitivity Sweep` | 161-437 | 4-z sensitivity 全節（277 LOC）|
| `## Changelog` | 479-501 | v0.2 → v0.3 變更紀錄 |
| Header status update | 1-9 | v0.2 → v0.3 / patch context note |
| Open Questions Q4-Q6 | 466-470 | v0.3 PA/QC/MIT 簽 OFF 點 |
| Acceptance For Spec v1 amend | 472-477 | QC/MIT 簽 OFF 範圍擴展含 v0.3 items |

### 1.2 v0.3 §"Stage 0R v0.3 Trigger Gate Sensitivity Sweep" 6 子節分解

#### Subsection §a — 起源與動機

明確紀錄 RED RCA 結論「65% signal failure 主導 + 35% sample 邊際次要」，並 cite spec v0.2 fixed parameter family 未證偽 funding skew hypothesis（只證偽極端 gate combination）。Trigger rate 0.0017% 是 self-imposed scarcity by design choice，不是 strategy fail。

#### Subsection §b — Sweep Methodology

**Z gate sensitivity dimension**: 4 cells

| z_cell_id | z_hi | trigger 預期 ratio | rationale |
|---|---|---|---|
| `z_relaxed` | 1.0 | ~10x vs z=1.5 | 低門檻 / 高 trigger / 低 power per signal |
| `z_moderate` | 1.2 | ~3-5x | 中間 |
| `z_baseline` | 1.5 | 1.0 (ref) | v0.2 fixed family 對齊 |
| `z_strict` | 2.0 | ~0.3x | 高門檻 / 低 trigger / 高 power per signal |

Pre-empirical assertion magnitude assertion 已寫入 spec（rerun 時做 reality check，偏離 > 2x 必 PA + QC verdict 分析）。

**同維 sweep 範圍保留 v0.2**（不擴 p_hi / p_lo / oi_min / horizon），確保 K_new 增加可控。

**4-cell × 2-branch × per-symbol output matrix** 4 維度：
1. Per-z-cell aggregated（8 top-level cells）
2. Per-z-cell × per-branch × per-symbol（200 rows）
3. Best primary cell per (z_cell, branch)（8 best cells）
4. Sweep-wide cross-z comparison（50 rows × 4 z column）

#### Subsection §c — K_total per-cell minimum 要求

**Preserve K_prior + K_new_min floor**：K_total floor 保留，但 K_new_min 從 v0.2 4050 升 v0.3 **5400**（+33%；4 z × ...）。strict K_prior 保持 0（empirical 2026-05-16 query 確認）。

**Cell-level n_eff stratified by z**：
- z_relaxed / moderate / baseline：100 / 50 / 300 floor（保持 v0.2）
- z_strict（diagnostic only）：30 / 15 / 75 降 floor，僅作 diagnostic eligible hint，**不解 promotion gate**（pooled n_eff ≥ 300 仍 strict）

**Funding cycle / day-share floor 對所有 z 維持**（`>= 14 cycles`, `<= 25% share`）。

#### Subsection §d — Output Format Spec

4 JSON blocks（per-z-cell aggregated / per-symbol / best-primary-per-z-branch / cross-z-comparison）schema 完整定義含 `wilson_ci_95_n_eff_share`, `trigger_rate`, `trigger_rate_vs_z_baseline_ratio`, `eligibility_fail_reasons`, `plateau_neighbors_pass`, `monotonic_drop_in_n_eff` 等 25+ fields。

#### Subsection §e — Wilson CI Computation per Cell

公式定義（Wilson Score Interval 95%，p_hat = n_eff / n）；用途三維（per-symbol n_eff share variability / avg_net_bps CI 補充 / promotion gate optional addition）。v0.3 **不強制 Wilson CI 進 eligibility floor**，留 PA verdict 評估 round 3 zoom-in 時 reference。

#### Subsection §f — Pre-rerun Linux PG Empirical Query Template

5 SQL queries（panel funding span / OI span / K_prior strict / K_prior relaxed / cycles distinct）+ 4 條 empirical assertion gates（panel ≥ 7d / sym=25 / K_prior strict=0 / cycles ≥ 21）。Rerun 必先 PA solo 跑 Linux PG empirical query 通過再 dispatch round 2。

#### Subsection §g — Output / Storage / Audit + 接受 / Reject 條件

- Output JSON 路徑：`/tmp/openclaw/w_audit_8b_stage0r_v0_3_sweep_<YYYYMMDD>_<HHMM>_pa.json`（Linux ssh-only write）
- 報告：`docs/CCAgentWorkSpace/PA/workspace/reports/<YYYY-MM-DD>--w_audit_8b_stage0r_round2_sensitivity_sweep_verdict.md`
- Mac mirror：scp 拿回 `docs/audits/2026-05-XX--w_audit_8b_round2_sweep_artifact.json` 作審計副本
- **No** runtime / TOML / RiskConfig / Operator / authorization / engine env mutation. **No** AMD §8 wording mutation. **No** Stage 1 demo canary opens.

接受 / Reject 條件 3 級：
- Accept = 任一 (z_cell, branch) 過 eligibility floor（z_relaxed/moderate/baseline 全 floor 過 OR z_strict diagnostic-only + 標 promotion_pending_pooled_n_eff_300）
- Reject = 全 4 z × 2 branch = 8 cells 全 RED → 觸發 PA 新 RCA + 建議 AMD-2026-05-15-02 §8 condition 3 wording 修訂
- Open = 1-3 個邊際 pass / 4-7 個 RED → PA + QC + MIT + BB 4-agent review 決定 round 3 zoom-in vs archive tombstone；AMD 暫不動

### 1.3 v0.2 → v0.3 Open Questions resolution

| Q | v0.2 原問 | v0.3 解 |
|---|---|---|
| Q1 | v0.2 fixed 5m sufficient? | v0.2 fixed 5m sufficient for round 1 已跑 RED；round 2 sweep 不再擴 price-action 變體 |
| Q2 | MIT define K_prior query | Empirical confirm `funding_skew%` strict = 0 / `funding%` relaxed = 9；MIT 簽 strict K_prior=0 |
| Q3 | BB sign funding interval / source_mode | Round 1 report 已含；BB 無 push back；round 2 sweep 保持 `ws_current` |
| Q4 (v0.3 new) | PA confirm pre-empirical assertion magnitude（z=1.0 ~10x trigger）對 Bybit funding 分布合理性 | Round 2 rerun 時 PA 比對 actual vs predicted；偏離 > 2x → PA 補 verdict 段分析 |
| Q5 (v0.3 new) | QC sign z-stratified n_eff floor 統計 power justification | Round 2 dispatch 前 QC review v0.3 spec patch + 簽 OFF |
| Q6 (v0.3 new) | MIT sign Wilson CI computation + K_total 5400 對 DSR sr_benchmark = √(2 ln 5400) = 4.14 變動極小 | Round 2 dispatch 前 MIT review |

### 1.4 副作用識別

| 模塊 | 影響 | 嚴重性 |
|---|---|---|
| `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_metrics.py` | 必 patch 加 z sweep loop（4 z cells × 既有 grid logic） | 高 — round 2 IMPL 必動 |
| `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_report.py` | 必 patch 加 sweep output 4 blocks JSON serialization | 高 — round 2 IMPL 必動 |
| `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_smoke.py` | 必 patch 加 sweep 邏輯測試（4 z cells 各 fixture）| 中 |
| `helper_scripts/reports/w_audit_8b_funding_skew_stage0r.py`（entry wrapper） | 可能 patch CLI 加 `--sweep` flag | 低 |
| `sql/queries/w_audit_8b_funding_skew_stage0r_features.sql` | **不動** — SQL z 過濾在 Python 層做，SQL 本身只 fetch raw features | 0 |
| Spec v0.2 既有 §"Hypothesis" / §"Data Contract" / §"Signal Formula Draft" / §"Replay-First Validation" / §"Implementation Boundary" | **不動** | 0 |
| Spec v0.2 §"Open Questions" / §"Acceptance For Spec v1" | 擴展 Q4-Q6 + Acceptance items | 低 |
| AMD-2026-05-15-02 §8 condition 3 wording | **不動** | 0 |
| `panel.funding_rates_panel` / `panel.oi_delta_panel` | **不動**（read-only） | 0 |
| `learning.strategy_trial_ledger` | **不動**（read-only） | 0 |
| 16 root principles (CLAUDE.md §二) | **0 觸碰** | 0 |
| 硬邊界 (CLAUDE.md §四) | **0 觸碰** | 0 |
| DOC-08 §12 安全不變量 | **不適用**（無交易） | 0 |

### 1.5 16-root-principles + 硬邊界 + DOC-08 compliance（patch 範圍）

| # | 原則 | 觸碰? | 證據 |
|---|---|---|---|
| 1 | 單一寫入口 | ❌ 否 | spec patch 不涉 IntentProcessor |
| 2 | 讀寫分離 | ❌ 否 | spec patch + Linux PG empirical query 純 SELECT |
| 3 | AI 輸出 ≠ 命令 | ❌ 否 | spec 不涉 lease |
| 4 | 策略不繞風控 | ❌ 否 | spec 不下單 |
| 5 | 生存 > 利潤 | ❌ 否 | spec 不下單 |
| 6 | 失敗默認收縮 | ✅ 維持 | reject 條件 = 全 RED → 觸發 RCA + AMD wording 修訂建議，**不** auto-promote |
| 7 | 學習 ≠ 改寫 Live | ❌ 否 | replay output JSON only；不寫 ML training table |
| 8 | 交易可解釋 | ❌ 否 | spec 不下單 |
| 9 | 災難保護 | ❌ 否 | spec 不下單 |
| 10 | 認知誠實 | ✅ 維持 | spec 顯式區分 RCA 事實 / pre-empirical 預測 / accept/reject 條件 |
| 11 | Agent 最大自主 | ❌ 否 | spec 不涉 cognitive_modulator |
| 12 | 持續進化 | ✅ 維持 | round 2 sensitivity sweep = 進化路徑 |
| 13 | AI 成本感知 | ❌ 否 | tooling 純 PG query 0 AI 調用 |
| 14 | 零外部成本可運行 | ✅ 維持 | tooling 純 Linux PG，無 Ollama/Claude 依賴 |
| 15 | 多 Agent 協作 | ✅ 維持 | Phase 2 run plan 強制 PA → E1 → E2+A3 → E4 → QC+MIT+BB → PA 鏈 |
| 16 | 組合級風險 | ❌ 否 | spec 不影響 portfolio_risk |

**硬邊界 (CLAUDE.md §四) 對照**：所有項目 0 觸碰（`live_execution_allowed` / `max_retries` / `system_mode` / `execution_state` / `decision_lease_emitted` / `OPENCLAW_ALLOW_MAINNET` / `live_reserved` / `authorization.json` / Operator 角色繞過）。

**DOC-08 §12 9 條安全不變量**：全 9 條 N/A（不涉交易）。

**AMD-2026-05-15-01**：`eligible_for_demo_canary=true/false` 唯一輸出，本 packet **不執行 Stage 1 demo micro-canary**，**不開** `Environment::Demo`，**不觸** OPENCLAW_ENABLE_PAPER（保持 0），**不開** authorization。

**評級**：A 級 — 16/16 完全合規 + 0 硬邊界觸碰 + 0 DOC-08 不變量觸碰。

---

## §2 Phase 2：Round 2 Sensitivity Sweep Rerun Run Plan（DEFERRED）

### 2.1 啟動條件 / Pre-empirical assertion gate

Phase 2 rerun **不立即跑**。必待 panel `funding_rates_panel` + `oi_delta_panel` 累積 ≥ 7d window + 4 條 assertion 全過。

#### Calendar ETA

當前 panel 起點 fixed `2026-05-10 23:30Z`；每日 grow ~1d；最新 `2026-05-16 18:56:53Z`（span 5.98d）。

| Window 目標 | 達成日 (calendar UTC) | calendar offset |
|---|---|---|
| 7d | **2026-05-17 23:30Z** | +1.02d from 2026-05-16 19:00Z |
| 7.5d | 2026-05-18 11:30Z | +1.52d |
| 10d | 2026-05-20 23:30Z | +4.02d |

**Phase 2 dispatch 預期觸發時點**：2026-05-17 23:30Z + 1h safety margin = **2026-05-18 00:30Z（calendar +1.06d from PA verdict）**。

#### Linux PG empirical query checklist（rerun 前 PA solo 必跑）

```bash
ssh trade-core "PGPASSWORD='' psql -h localhost -U trading_admin -d trading_ai -c \"
SELECT
  to_timestamp(MIN(snapshot_ts_ms)/1000) AS funding_min_ts,
  to_timestamp(MAX(snapshot_ts_ms)/1000) AS funding_max_ts,
  EXTRACT(EPOCH FROM (to_timestamp(MAX(snapshot_ts_ms)/1000) - to_timestamp(MIN(snapshot_ts_ms)/1000)))/86400 AS span_days,
  COUNT(*) AS total_rows,
  COUNT(DISTINCT symbol) AS sym_count
FROM panel.funding_rates_panel;
\""

ssh trade-core "PGPASSWORD='' psql -h localhost -U trading_admin -d trading_ai -c \"
SELECT
  to_timestamp(MIN(snapshot_ts_ms)/1000) AS oi_min_ts,
  to_timestamp(MAX(snapshot_ts_ms)/1000) AS oi_max_ts,
  COUNT(*) AS oi_rows
FROM panel.oi_delta_panel;
\""

ssh trade-core "PGPASSWORD='' psql -h localhost -U trading_admin -d trading_ai -c \"
SELECT count(DISTINCT candidate_key)::int AS k_prior_strict_funding_skew
FROM learning.strategy_trial_ledger
WHERE candidate_key IS NOT NULL
  AND (strategy_name ILIKE '%funding_skew%' OR trial_family ILIKE '%funding_skew%' OR candidate_key ILIKE '%funding_skew%');
\""

ssh trade-core "PGPASSWORD='' psql -h localhost -U trading_admin -d trading_ai -c \"
SELECT count(DISTINCT candidate_key)::int AS k_prior_funding_related
FROM learning.strategy_trial_ledger
WHERE candidate_key IS NOT NULL
  AND (strategy_name ILIKE '%funding%' OR trial_family ILIKE '%funding%' OR candidate_key ILIKE '%funding%');
\""

ssh trade-core "PGPASSWORD='' psql -h localhost -U trading_admin -d trading_ai -c \"
SELECT COUNT(DISTINCT next_funding_ms)::int AS distinct_cycles_in_panel
FROM panel.funding_rates_panel
WHERE next_funding_ms IS NOT NULL;
\""
```

#### Assertion gate（任一 fail → halt rerun，PA escalate PM）

| # | Assertion | Expected | Action if fail |
|---|---|---|---|
| 1 | `funding span_days >= 7.0` AND `oi span_days >= 7.0` | both ≥ 7.0 | defer rerun +12h re-check |
| 2 | `funding sym_count = 25` AND `oi rows >= funding rows × 0.95` | sym=25 + parity | PM escalate panel writer issue |
| 3 | `k_prior_strict_funding_skew = 0` | = 0 | PM escalate ledger drift |
| 4 | `distinct_cycles_in_panel >= 21` | ≥ 21 | defer +12h panel grow |

#### Source sync check

```bash
git status --porcelain
ssh trade-core "cd ~/BybitOpenClaw/srv && git log --oneline -5"
# Verify Mac main == Linux main; defer rerun if drifted
```

### 2.2 Rerun Command Shape（mirror Phase 1）

```bash
ssh trade-core "cd ~/BybitOpenClaw/srv && \
OPENCLAW_DATABASE_URL=postgresql://trading_admin@localhost:5432/trading_ai \
OPENCLAW_STAGE0R_STATEMENT_TIMEOUT_MS=600000 \
timeout 1800 python3 helper_scripts/reports/w_audit_8b_funding_skew_stage0r.py \
  --window-days 7 \
  --format json \
  --sweep \
  --z-cells 1.0,1.2,1.5,2.0 \
  --out /tmp/openclaw/w_audit_8b_stage0r_v0_3_sweep_$(date -u +%Y%m%d_%H%M)_pa.json \
  > /tmp/openclaw/w_audit_8b_stage0r_v0_3_sweep_$(date -u +%Y%m%d_%H%M).log 2>&1"
```

**注**：
- `--sweep` flag 是 v0.3 IMPL 必加（round 2 dispatch 時 E1 必 IMPL）；當前 entry wrapper 是否已支持需 E1 確認 IMPL diff
- `--z-cells 1.0,1.2,1.5,2.0` 列出 4 sensitivity cells；E1 IMPL 加 argparse parsing
- timeout 從 round 1 `1200s` 升至 `1800s`（30 min），預期 4 z × full grid = 4x cell count → 預期 runtime 4x；7d window vs 5.98d 額外 +17% data → 安全 margin

### 2.3 4-cell sensitivity sweep matrix verbose output expected

Round 2 sweep 預期 4 z cells × 2 branches = 8 top-level cells 全 RED (高概率)；理由：

| z_cell | 預期 trigger n | 預期 pooled n_eff | 預期 RED 主因 |
|---|---:|---:|---|
| z_relaxed (z=1.0) | ~70-100（vs round 1 7 of z=1.5） | ~15-25 | **n_eff 仍 < 300 floor**；pooled DSR 也大概率 < 0.95 |
| z_moderate (z=1.2) | ~21-35 | ~5-10 | n_eff < 300, DSR < 0.95 |
| z_baseline (z=1.5) | ~9-12 (vs round 1 7 in 5.72d) | ~2-3 | n_eff << 300, branch n=0 for crowded_long_fade 大概率 |
| z_strict (z=2.0) | ~2-4 | ~0-1 | n_eff < 30 even with stratified floor |

**Predicted Sweep verdict**: **RED** with **z_relaxed (z=1.0) closest to marginal**。但 pooled n_eff ~15-25 仍 far from 300 floor → 即使 z_relaxed 也大概率全 RED。

如果 verdict 全 RED：
1. PA 在 sweep verdict 中明文紀錄 **「panel 7d window + 4-z sweep 全 RED」**
2. 觸發 PA 補新 RCA 報告 + 建議 AMD-2026-05-15-02 §8 condition 3 wording 修訂
3. 修訂建議 wording：「W-AUDIT-8b Stage 0R passed OR a formal tombstone amendment archives W-AUDIT-8b after exhaustive sensitivity sweep」
4. PM + 4-agent (QC/MIT/BB/FA) 再 sign-off wording 修訂

如果 verdict 部分 pass（1-3 cells 邊際）：
1. PA verdict 標 Open
2. PA + QC + MIT + BB 4-agent review 決定 round 3 zoom-in 範圍 vs archive tombstone
3. AMD 暫不動

如果 verdict 全 accept（極低概率，但保留可能性）：
1. PA verdict 標 ACCEPT-DIAGNOSTIC
2. 派 next-Wave packet design Stage 1 Demo micro-canary（per AMD-2026-05-15-01 + 3-gate condition 3 first sub-gate）

### 2.4 Pre-empirical assertion：trigger rate sweep

Spec v0.3 §"Pre-empirical assertion" 已寫入 expected ratios（z=1.0 ~10x trigger vs z=1.5）。Round 2 rerun 時 PA 比對 actual vs predicted：

| z cell | Round 1 (z=1.5) actual | Round 2 (predicted) | Round 2 (TBD) | Δ vs predicted |
|---|---:|---:|---|---|
| z_relaxed (z=1.0) | n/a | 70 (~10x) | TBD | TBD |
| z_moderate (z=1.2) | n/a | 21-35 (~3-5x) | TBD | TBD |
| z_baseline (z=1.5) | 7 (5.72d) | ~9 (7d / 5.72d × 7) | TBD | TBD |
| z_strict (z=2.0) | n/a | 2-3 (~0.3x) | TBD | TBD |

**Round 2 verdict 必含 "Pre-empirical Reality Check" 段**：偏離 > 2x → PA 補 Bybit funding tail-heavy 分布分析。

### 2.5 Wave 4-B Run Plan step-by-step

| Step | Owner | Description | Output | Dependency | Estimate |
|---|---|---|---|---|---|
| **0** | PA | Phase 1 v0.3 spec patch land（本 PA report）| spec v0.3 + 本 verdict | — | **DONE** |
| **1** | PA | Linux PG empirical assertion gate check（panel ≥ 7d + sym=25 + K_prior=0 + cycles ≥ 21） | gate result（PASS/FAIL）| Panel ≥ 7d wait（+1.02d）| 0.5h / PA solo |
| **2** | PA | Mac/Linux source sync verify（`git status` + ssh `git log -5`）| sync state | Step 1 PASS | 0.25h / PA solo |
| **3** | E1 | IMPL sweep logic patch（`funding_skew_stage0r_metrics.py` 加 z sweep loop + `funding_skew_stage0r_report.py` 加 4 JSON blocks + `funding_skew_stage0r_smoke.py` 加 4-z fixture + entry wrapper 加 `--sweep` `--z-cells` argparse） | code patch + smoke pass | Step 2 verified clean | 1d / E1 |
| **3a** | E2 + A3 | 對抗審 sweep logic + Wilson CI 公式 + per-z stratification 邏輯 + plateau check vs sweep | E2 + A3 verdicts | Step 3 IMPL done | 0.5d / 並行 |
| **3b** | E4 | Regression smoke：4-z fixture pass + leak-free shift(1) compliance + K_total 5400 計算正確性 | E4 verdict | Step 3a APPROVE | 0.5d / E4 |
| **4** | E1 | 跑 round 2 sweep（Linux PG）`python3 helper_scripts/reports/w_audit_8b_funding_skew_stage0r.py --sweep --z-cells 1.0,1.2,1.5,2.0 --window-days 7 --format json --out ...` | round 2 JSON + log | Step 3b PASS | 1h / E1 |
| **5** | PA + QC + MIT + BB | 並行 review round 2 sweep verdict | 4 agent verdicts | Step 4 done | 0.5d / 並行 |
| **6** | PA | 寫 round 2 verdict report（含 sweep-wide cross-z comparison + pre-empirical reality check + accept/reject/open verdict） | `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-XX--w_audit_8b_stage0r_round2_sensitivity_sweep_verdict.md` | Step 5 done | 0.5d / PA |
| **7** | PM | PM sign-off + push to `Operator/`copy | PM sign-off report | Step 6 | 0.5h / PM |

**Wave 4-B 總估時**：~2-2.5 worker-days（calendar 4-5 days post-panel-7d-wait，依 round 2 verdict 決定後續）

### 2.6 Adversarial review 強制覆蓋面

#### E2 對抗審（Step 3a）— 新增點

1. Z sweep loop 邏輯（4 z cells iteration + per-cell grid logic preservation）
2. Wilson CI 公式 IMPL（`p_hat (1-p_hat) / n + z^2/(4n^2)` 數值穩定性 in small-n）
3. z_strict stratified floor 邏輯（30/15/75 而非 100/50/300）
4. K_new = 5400 計算正確性（25 × 2 × 4 × 3 × 3 × 3）
5. trigger_rate_vs_z_baseline_ratio 計算 + monotonic_drop_in_n_eff 判定
6. Output JSON 4 blocks schema serialization 完整性
7. Leak-free shift(1) compliance（per `feedback_indicator_lookahead_bias.md`）— 4 z cell 全 inherit v0.2 leak-free contract，但 E2 必確認 sweep loop 不引入新 leak

#### A3 對抗審（Step 3a）— 新增點

1. Wilson CI 95% formula 正確性（與 Bailey-Sample-Test bench 比對）
2. z-stratified n_eff floor 統計 power justification（30/15/75 floor for z_strict 是否合理）
3. K_total = 5400 對 DSR sr_benchmark = √(2 ln 5400) = 4.14 變動極小（與 v0.2 4050 對應 4.07 比較）
4. Plateau check 在 4-z sweep 視窗下定義（adjacent cells 跨 z 還是 within-z）
5. Pre-empirical assertion magnitude 預測法（10x trigger vs 1.5 對 Bybit funding 分布合理性 sanity check）

#### E4 regression（Step 3b）— 新增點

1. 4-z fixture pass（既 360 ts × 3 symbols 數據合成 4 z 版本，verify 4 z 路徑全跑）
2. K_new 5400 計算正確性 unit test
3. Wilson CI bench fixture（n=10, n_eff=2 預期 CI ~ [0.05, 0.55]）
4. Sweep output 4 blocks JSON deserialize round-trip test
5. z_strict stratified floor 邏輯反例測試（n_eff=29 with z_strict → fail, n_eff=30 with z_strict → diagnostic eligible）

#### QC adversarial（Step 5）— sweep verdict 視角

1. 4-z sweep verdict matrix 數學讀（每 cell DSR/PBO/n_eff/Wilson 是否一致）
2. Pre-empirical assertion magnitude 對齊 actual 偏離量分析
3. Sweep-wide cross-z comparison plateau pattern interpretation

#### MIT adversarial（Step 5）— sweep verdict 視角

1. Per-z-cell raw panel as-of join consistency
2. K_prior strict=0 unchanged confirmation
3. Funding attribution `excluded` 全 4 z cell 一致
4. As-of join + leak-free shift(1) compliance 全 4 z 一致

#### BB adversarial（Step 5）— sweep verdict 視角

1. funding interval / source_mode 全 4 z cell 一致（`ws_current` / per-symbol funding_interval_min）
2. WS-first posture 不破（純 PG SELECT；不打 Bybit REST）
3. funding semantics 正負方向一致（positive funding = longs pay shorts）對 crowded_short_squeeze 判斷正確

### 2.7 Decision Tree（Round 2 verdict → next-step）

```
Round 2 verdict matrix（8 cells）
│
├── ACCEPT（任一 (z_cell, branch) eligibility floor 過）
│   ├── PA emit ACCEPT-DIAGNOSTIC verdict
│   ├── Update AMD §8 condition 3 first sub-gate（W-AUDIT-8b passed）satisfied
│   ├── Next-Wave packet: Stage 1 Demo micro-canary design（per AMD-2026-05-15-01）
│   └── AMD wording 不修訂
│
├── OPEN（1-3 個邊際 pass / 4-7 個 RED）
│   ├── PA emit OPEN verdict
│   ├── PA + QC + MIT + BB 4-agent review
│   ├── Decision: round 3 zoom-in（z 1.05 / 1.1 / 1.15 等 sub-z）vs archive tombstone
│   ├── AMD 暫不動
│   └── 若 round 3 仍 RED → 走 reject path
│
└── REJECT（全 8 cells RED）
    ├── PA emit RED-FINAL verdict
    ├── PA 補新 RCA + 建議 AMD wording 修訂
    │   建議 wording: "W-AUDIT-8b Stage 0R passed OR a formal tombstone amendment
    │   archives W-AUDIT-8b after exhaustive sensitivity sweep"
    ├── 4-agent (QC/MIT/BB/FA) sign-off wording 修訂
    └── PM final approval; archive W-AUDIT-8b as tombstone post-AMD-rev
```

---

## §3 16-root-principles + 硬邊界 + DOC-08 compliance（PA verdict 範圍）

per §1.5 + §2 全程：

| Layer | 觸碰? |
|---|---|
| CLAUDE.md §二 16 原則 | 0 觸碰 |
| CLAUDE.md §四 硬邊界 | 0 觸碰 |
| DOC-08 §12 9 條安全不變量 | 不適用（無交易）|
| AMD-2026-05-15-01 canary rebase | 不觸（不啟 Stage 1 demo）|
| AMD-2026-05-15-02 §8 condition 3 strict AND 3-gate | **不破** wording；Phase 2 conditional 觸發點預留 reject path |
| `panel.funding_rates_panel` / `panel.oi_delta_panel` | read-only |
| `learning.strategy_trial_ledger` | read-only |
| `risk_config*.toml` / OPENCLAW_* env / `authorization.json` | 0 觸碰 |

**評級**：A 級 — 16/16 完全合規 + 硬邊界 0 觸碰 + DOC-08 不適用。

---

## §4 Files Touched / Referenced

### 1.5.1 Phase 1（已 land）

**Edited**:
- `srv/docs/execution_plan/2026-05-15--w_audit_8b_funding_skew_directional_spec.md`（v0.2 195 行 → v0.3 501 行；+306 行 / +1.57x growth）

**Created**:
- `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_spec_v03_sensitivity_sweep_patch.md`（本 verdict report）

### 1.5.2 Phase 2（將來 round 2 dispatch 時 E1 動）

**Will edit**（pending Wave 4-B Step 3 dispatch）:
- `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_metrics.py`（+z sweep loop）
- `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_report.py`（+4 JSON blocks）
- `helper_scripts/reports/w_audit_8b/funding_skew_stage0r_smoke.py`（+4-z fixture）
- `helper_scripts/reports/w_audit_8b_funding_skew_stage0r.py`（+`--sweep` `--z-cells` CLI args）

**Will not edit**（per v0.3 spec scope）:
- `sql/queries/w_audit_8b_funding_skew_stage0r_features.sql`（z 過濾在 Python 層）
- 任何 `settings/risk_control_rules/*.toml`
- 任何 `program_code/exchange_connectors/bybit_connector/control_api_v1/*`
- 任何 Rust engine source / Cargo.toml
- 任何 DB schema migration（`sql/migrations/*`）
- 任何 `learning.strategy_trial_ledger` row insert

### 1.5.3 Referenced

- `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_stage0r_red_rca_and_next_step.md`（RED RCA 上輪）
- `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_stage0r_run_plan.md`（round 1 run plan）
- `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_stage0r_replay_packet_verdict.md`（round 1 RED verdict）
- `srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--w_audit_8b_stage0r_gap_closure.md`（sibling tooling gap closure）
- `srv/docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-16--w_audit_8b_adversarial_hardening.md`（sibling 4-agent hardening）
- `srv/docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md`（AMD §8 strict AND 3-gate）
- `srv/docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md`（canary rebase context）
- Linux PG runtime empirical query 2026-05-16 19:00Z

---

## §5 Summary

### 5.1 Phase 1（DONE）

- spec v0.2 → v0.3 patch land；+306 行 / 6 子節 / 完整 sensitivity sweep methodology + K_total / output schema / Wilson CI / Linux PG empirical query template / accept/reject/open conditions
- changelog 加 v0.3 + v0.2 對照
- Open questions Q4-Q6 (PA/QC/MIT v0.3 sign-off items) 加入
- Acceptance For Spec v1 擴展含 v0.3 items
- 0 觸 spec v0.2 既有 §"Hypothesis" / §"Data Contract" / §"Signal Formula Draft" / §"Replay-First Validation" / §"Implementation Boundary"
- 0 觸 AMD-2026-05-15-02 §8 condition 3 wording
- A 級 16/16 合規 + 硬邊界 0 觸 + DOC-08 N/A

### 5.2 Phase 2（DEFERRED to panel ≥ 7d, ETA 2026-05-18 00:30Z calendar +1.06d）

- Wave 4-B Run Plan 完整（8 steps，5 worker-days，calendar ~4-5d post-panel-wait）
- Pre-rerun Linux PG empirical assertion gate（4 條 + source sync）
- Rerun command shape ready
- 4-z sweep matrix verbose output expected RED 預測（z_relaxed closest to marginal but pooled n_eff still << 300）
- Decision tree: ACCEPT / OPEN / REJECT 3 paths 明確
- E2 + A3 + E4 + QC + MIT + BB adversarial coverage 7 軸新增點全列

### 5.3 Hand-off

- **Phase 1 → PM**：spec v0.3 land + verdict report 同 commit push；PM 視為 Wave 4-A Step 1 PA spec patch DONE
- **Phase 2 → 自動觸發**：calendar 2026-05-17 23:30Z 後 PA solo 跑 §2.1 Linux PG empirical assertion gate；4 條全 PASS → PA solo Step 1+2 後 Hand-off PM dispatch Step 3 `@E1` IMPL
- 若 panel grow stall（runtime panel writer 異常）→ PA escalate PM；defer +12h 重 check；連 3 次 fail → PM 評估是否手動延 dispatch

---

PA DESIGN DONE: report path: `/Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-16--w_audit_8b_spec_v03_sensitivity_sweep_patch.md`
