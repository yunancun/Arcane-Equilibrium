# MIT Short Re-Review — phys_lock Live Enable AMD DRAFT

**Reviewer**: MIT (DB schema + ML pipeline + Data calibration auditor)
**Date**: 2026-05-16
**Subject**: AMD `2026-05-XX-XX-phys-lock-live-enable-draft.md` v0.1
**Mode**: Short focused re-review — counterfactual statistical rigor + ML pipeline impact + schema reality verify
**Method**: AMD DRAFT 全文 + `learning.exit_features` V029 schema + `exit_features/v2.rs:100-203` ExitConfig + ML training/*.py grep + replay engine counterfactual support grep
**Verdict**: **APPROVED-CONDITIONAL** — 7 MUST-FIX + 2 SHOULD-FIX + 0 BLOCKER

> 註：MIT agent read-mostly；本檔由主會話按 MIT agent 返回原文存檔。

---

## §1 Counterfactual analysis 統計嚴謹性

**4-criterion sample power 計算** (n=86 fires):

- median(A-B) < -2 bps + 95% one-sided CI 上限 < 0: paired bootstrap 1000 resample n=86 對 effect size > 5 bps（典型 phys_lock 鎖利幅度）有 ~80% power if true median ≤ -5 bps; effect size 2-5 bps power 降至 30-50% → **MUST-FIX A**: AMD §5.2 必明文 minimum detectable effect (MDE) 計算 — 寫死「PASS 要求 with-lock 平均優勢至少 X bps，n=86 power ≥ 0.8」否則 86 fires 對小 effect 是 underpowered

- sensitivity sweep `min_hold_secs ± 50%` / `giveback_floor ± 0.1` / `peak_atr_norm ± 0.2`: 3 維 × 3 levels = 27 cells，每 cell n=86 跑同樣 bootstrap → **Bonferroni 27 倍 family-wise error** AMD 沒提；單側 95% CI 在 27 比較下 family-wise α ≈ 0.74，**幾乎必然有 cell 因隨機 cross 0** → **MUST-FIX B**: §5.2 sensitivity sweep PASS 條件必加 FDR 控制（BH q=0.10）

- **per-symbol 70% directional positive 數學上不可行**（CRITICAL）: 86 fires / 25 symbols = avg 3.44 fires/symbol，pigeonhole 下最多 17 symbols 達 ≥5 fires 門檻；若只 10-12 symbols carve-out qualifies，70% = 7-9 個必須 positive，**single fire dominate symbol pass/fail**。**MUST-FIX C**: §5.2 per-symbol 必加 Wilson-CI sample-size gate（n<5 → NEUTRAL 不計入分母；mirror MIT round-2 F-MIT-2 健康檢查 [62] 規則）

- Wilson-CI lower bound vs point estimate at small sample: 業界 mature practice = 小樣本必用 Wilson lower bound，**AMD §5.2 全篇用 median 點估 + 95% CI 跨 0**判 fail，**未引入 Wilson lower bound 對保守 lower 跟 threshold 比** → **MUST-FIX D**: §5.2 PASS / FAIL 邊界用 Wilson 95% CI lower bound 比 threshold

---

## §2 ML pipeline non-training surface invariant

**Schema 命名錯誤（HIGH，BLOCK-IMPL）**: AMD §5.1.1 / §6.1 / §7 #8 / §8 #1 全部寫 **`exit_features.physical_decision_logs`** — **此表不存在**。Linux PG empirical reality：唯一 phys_lock audit table 是 `learning.exit_features` (V029 hypertable, 7d chunk, PK=(context_id,ts))；exit_source / exit_trigger_rule 兩 column 識別 phys_lock fire（如 `exit_trigger_rule='PHYS-LOCK'`）。

**MUST-FIX E**: AMD 全篇 `exit_features.physical_decision_logs` → 改 `learning.exit_features WHERE exit_trigger_rule LIKE 'phys_lock_%' OR exit_source='Physical'`。命名 bug 不修 = E1 IMPL 撈不到資料 + counterfactual evidence 不能跑。

**ML pipeline leakage 風險評估**（HIGH confidence）: grep `program_code/ml_training/*.py` + `program_code/learning_engine/*.py` 全掃 → `fee_execution_calibrator.py:172` + `half_life_estimator.py:216` 對 `learning.exit_features` 是 **future IMPL placeholder**（fixture-driven，未生產 reader）；無 LinUCB / scorer / quantile / MLDE / DL3 SELECT `learning.exit_features` 路徑 → **當前 0 silent leakage 風險**。但 future IMPL 將 read `learning.exit_features` cell-level realized_net_bps → phys_lock fire 將成為 ML feature/label 計算 sample。

**MUST-FIX F**: AMD 必加 non-training surface invariant 明文，類似 W094 spec §1.4 banned scope — phys_lock fire 的 `exit_source` / `exit_trigger_rule` / Gate 1-4 decision metadata 是 ops audit，**禁餵 ML training feature space**；但 `realized_net_bps` (ex-post 真實 label) 是合法 label source（fee_execution_calibrator 既定設計）。E3 grep guard rule: `grep -nrE '(linucb|scorer|quantile|mlde|dl3).*exit_trigger_rule|exit_source.*phys_lock' program_code/` 必 0 hit。

---

## §3 既有 ML pipeline 影響評估

**`mlde_edge_training_rows` VIEW**: V031/V034/V084 grep → JOIN `trading.intents` + `learning.decision_features` + `learning.mlde_shadow_recommendations` + `learning.decision_outcomes`；**完全 NOT JOIN `learning.exit_features`** → phys_lock fire metadata 對此 VIEW **0 曝露**

**5 ML cron 影響**：grep ml_training/ → linucb_trainer / quantile_trainer / mlde_shadow_advisor / mlde_demo_applier / dl3_ab_runner 全 0 reference `learning.exit_features` 為 SELECT source → **零 phys_lock signal feed 進入 ML training pipeline**

**結論**: AMD 啟用 = 純 Rust deterministic policy 改動 + audit row 量擴大；對既有 5 ML cron training 無 schema / feature / label 影響；non-training surface 邊界乾淨。

---

## §4 Counterfactual replay 設計

**Replay engine counterfactual support reality check**: grep `rust/openclaw_engine/src/replay/*.rs` → counterfactual semantic **僅限「rejected qty=0 ghost row」** for fee/slippage TIF counterfactual（apply_fill.rs:371-490）；**0 native support 「disable phys_lock at fire ts and continue simulation」**。

AMD §5.1.2 「QC 跑 historical replay」對 phys_lock fire 跑 counterfactual A 場景：**現有 replay engine 不支援 phys_lock-disabled re-simulation** → **MUST-FIX G**: AMD §5.1.2 必明文 IMPL 前置 = replay framework 必支援 ExitConfig override at replay session level（pass `missing_edge_fallback_bps=-10.0` 強制 Gate 1 fail-safe Hold for the counterfactual run）；否則 QC counterfactual analysis 無法執行。

**`replay.simulated_fills` tier 衝突風險**: AMD §5.1.2 指定 `evidence_source_tier='counterfactual_replay'`，per V050 enum 是 allowed value；counterfactual_replay 屬可餵 ML tier，**設計上不誤觸 ML pipeline non-training invariant**；但需確保 QC 跑 counterfactual 用 `'counterfactual_replay'` tag，**禁誤 tag 為 `'synthetic_replay'`** — **SHOULD-FIX H**: AMD §5.1.2 加 evidence_source_tier writer mandate + E3 grep guard

---

## §5 DB schema impact

**Schema 改動需求評估**: AMD §2.1 「唯一改動 = `risk_config_live.toml` 一個 override」+ §6.3 「無 schema migration」**正確** — 純 TOML hot-flag，無 V### migration 需求

**`learning.exit_features` 容量**: V029 7d chunk + V075 retention 14d compress + 90d retain；月度 ~370 fires/月 額外 row × 25 symbols × 5 strategies → 月度 ~9k row 增長對 hypertable + compression 是 trivial scale

**enum / column 改動**: phys_lock fire 的 `exit_trigger_rule` 值已在 V086 close_reason_code enum allowlist 內 → **0 schema enum 改動需求**

**結論**: §5 完全乾淨；唯一 schema-adjacent risk = MUST-FIX E 提的 `physical_decision_logs` 命名 bug。

---

## §6 Linux PG dry-run 必要性

**TOML override 純行為改動**: 不需 V### migration → V055/V083/V084 incident precedent **不直接適用**

**Counterfactual evidence packet 跑 replay 是否需 Linux PG support**: HIGH 必要 — counterfactual analysis 需要 (a) dump 86 fires from `learning.exit_features` (Linux PG empirical, 不是 Mac mock); (b) cross-join `trading.fills` for actual close fill price (Linux PG); (c) replay session 寫 `replay.simulated_fills` with `evidence_source_tier='counterfactual_replay'` (Linux PG insert path); (d) paired bootstrap 用 86 真實 fires 對應的 actual_lock_pnl_bps vs counterfactual_pnl_bps — 全 Linux runtime 路徑 → **MUST-FIX I**: AMD §5.1.2 / §5.3 必明文 evidence packet 跑 Linux PG empirical + sqlx checksum verify + replay session evidence_id tracked

---

## §7 MIT verdict

**APPROVED-CONDITIONAL** — 7 MUST-FIX (A/B/C/D/E/F/G) + 2 SHOULD-FIX (H/I) + 0 BLOCKER

### must-fix (block IMPL dispatch 7 條)

- **MUST-A** §5.2 加 MDE + power calculation（n=86 對小 effect underpowered）
- **MUST-B** §5.1.4 sensitivity sweep 27 cells 加 BH-FDR q=0.10 family-wise correction
- **MUST-C** §5.2 per-symbol 70% directional 加 Wilson-CI sample-size gate（n<5 NEUTRAL）
- **MUST-D** §5.2 PASS/FAIL 邊界用 Wilson 95% CI lower bound 比 threshold
- **MUST-E** AMD 全篇 `exit_features.physical_decision_logs` → 改 `learning.exit_features WHERE exit_trigger_rule LIKE 'phys_lock_%' OR exit_source='Physical'`（schema 命名 bug）
- **MUST-F** 加 non-training surface invariant 明文 + E3 grep guard（phys_lock metadata 禁餵 ML feature；`realized_net_bps` 仍合法 label source）
- **MUST-G** §5.1.2 replay framework 必先支援 ExitConfig override at replay session level

### should-fix (pre-IMPL 補件 2 條)

- **SHOULD-H** §5.1.2 加 evidence_source_tier writer mandate（`counterfactual_replay` 不誤 tag `synthetic_replay`）
- **SHOULD-I** §5.1.2 / §5.3 evidence packet 加 Linux PG dry-run snapshot mandate + sqlx checksum verify + replay session evidence_id tracked

### advisory (P3)

- 若 Phase 2b 7d 後 demo 86 fires 樣本擴展（demo 累積到 ~150-200 fires/2w）→ counterfactual analysis statistical power 顯著改善，建議 AMD §5.1 加 footnote「若 demo 樣本 ≥ 150 fires，§5.2 PASS gate 自動升級 — MDE 從 5 bps 降至 3 bps，per-symbol carve-out threshold 從 n≥5 改 n≥7」

### MIT confidence 評級

- **HIGH** confidence (§1-§6): AMD 文本 + schema empirical (V029 + V086) + ml_training grep + replay engine grep 全直驗
- **MED** confidence (§6 Linux PG dry-run necessity): 基於 V055/V083/V084 incident precedent
