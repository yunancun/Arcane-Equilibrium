# W-AUDIT-8b Round 2 RED Final — 4-Agent Independent Review Packet

**Date**: 2026-05-{{DAY}}
**Round**: Round 2 (post-Round-1 RED, post-4-cell sensitivity sweep)
**Verdict to review**: `RED_FINAL` (pending 7.0d gate confirm alignment)
**Reviewers**: QC + MIT + BB + FA (4-agent independent, parallel)
**Source artifact**: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-17--w_audit_8b_round2_phase_b_preliminary_sweep.md`
**Linux artifact**: `trade-core:/tmp/openclaw/w_audit_8b_stage0r_v0_3_sweep_{{TIMESTAMP}}_pa.json`
**Author**: Main session PM + Conductor

> **Fill-in note**: `{{...}}` markers must be replaced with 7.0d-confirmed final values before dispatch.

---

## §1 Context for Reviewers

W-AUDIT-8b Funding Skew Directional 是 trading losses audit round 2 的 alpha source 候選 #1。Round 1 RED（signal failure 主導，strategy primary n=7 / n_eff=1 / baseline -16.91 bps / trigger rate 0.0017%）後，Round 2 設計 4-cell sensitivity sweep + Wilson 95% CI + per-symbol floors + strict monotonic comparison。

Preliminary sweep on 6.92d panel（operator-authorized override）+ 7.0d confirm alignment 後：

| z_cell | best branch | n / n_eff | avg_net_bps | DSR | PBO | Wilson lower | verdict |
|---|---|---|---|---|---|---|---|
| 1.0 | short_squeeze | {{n_1.0}} / {{neff_1.0}} | {{avg_1.0}} | {{dsr_1.0}} | {{pbo_1.0}} | {{wilson_1.0}} | RED |
| 1.2 | short_squeeze | {{n_1.2}} / {{neff_1.2}} | {{avg_1.2}} | {{dsr_1.2}} | {{pbo_1.2}} | {{wilson_1.2}} | RED |
| 1.5 | short_squeeze | {{n_1.5}} / {{neff_1.5}} | {{avg_1.5}} | {{dsr_1.5}} | {{pbo_1.5}} | {{wilson_1.5}} | RED |
| 2.0 | short_squeeze | {{n_2.0}} / {{neff_2.0}} | {{avg_2.0}} | {{dsr_2.0}} | {{pbo_2.0}} | {{wilson_2.0}} | RED |

**Key findings to challenge**:
1. **z=1.2 INJUSDT dilution**: trigger ×6 揭露 short_squeeze avg_net {{inj_avg_1.2}} bps；preliminary 為 -9.64
2. **z=1.5 ≡ z=2.0 identical signal set**: bimodal funding tail → 高 z 無增量信號
3. **crowded_long_fade dead trigger**: all z × all 25 sym n=0
4. **DSR=0 uniformly**: no cell promotion candidate
5. **PBO 0.64-0.75**: probability of backtest overfit 高

---

## §2 4-Agent Review Charter

每 agent 獨立 review，不參考其他 agent verdict。Output 結構統一：

1. **APPROVE / RETURN / RED_FLAG / OUT_OF_SCOPE**
2. **MUST-FIX**: blocking 條目（必修才能 final RED 進 archive）
3. **SHOULD-FIX**: 強烈建議
4. **NTH**: nice-to-have
5. **領域特定 verdict**（per agent 視角）

---

## §3 QC (Quantitative Consultant) — Mathematical Validity Review

**Scope**: Wilson CI semantics、DSR=0 normalization、PBO 0.64-0.75 統計意義、bimodal funding tail z=1.5/z=2.0 等價性、n_eff 計算方法

**Specific questions to address**:
1. Wilson CI 95% lower bound 在 small-n（n=7 / n_eff=1）下是否仍 reliable？是否該改 exact binomial CI？
2. DSR=0 是否反映「無 trade-able edge」 vs 「sample 不足無法 compute」？distinction？
3. PBO 0.64-0.75 落在哪個 reference distribution 區間（per Bailey-Lopez de Prado 2014）？
4. z=1.5 ≡ z=2.0 identical signal set 在 bimodal funding 是 expected behavior 還是 spec design bug？
5. n_eff 計算（n / autocorrelation-correction factor）是否考慮 panel cross-sectional clustering？
6. crowded_long_fade 全 n=0 是 signal design dead 還是 z threshold 太嚴？建議 floor 設定？

**Verdict expected**: APPROVE / RETURN / RED_FLAG（with specific math 引用）

---

## §4 MIT (Database + ML Pipeline + Data Calibration) — Pipeline + Calibration Review

**Scope**: panel.funding_rates_panel 完整性、snapshot_ts_ms vs asof_ts SoT、time-series CV design、data leakage check、feature engineering for funding skew、cross-sectional autocorrelation

**Specific questions to address**:
1. panel.funding_rates_panel 7.0d gate 是否足夠 statistical power？若 6.92d preliminary 已 confirm RED 那 power 是否 over-engineered？
2. funding skew feature engineering 是否有 look-ahead bias（per memory `feedback_indicator_lookahead_bias.md` rolling-window concern）？
3. z-score normalization 用 panel-level cross-sectional 還是 per-symbol time-series？哪個更合適 sentiment regime？
4. Wilson lower bound 在 binomial proportion + clustered sample 應否 hierarchical-Bayesian-correct？
5. crowded_long_fade 信號 dead 是否反映 panel funding_rates_panel sample 在 z>1.0 區間 sparse？
6. 7.0d → 28d / 56d 擴展 panel days 是否能 reverse verdict？建議 panel coverage 擴展 ROI？

**Verdict expected**: APPROVE / RETURN / RED_FLAG（with data SoT 引用）

---

## §5 BB (Bybit Broker Compatibility) — Exchange-Side Review

**Scope**: Bybit funding rate endpoint data SoT、funding interval consistency、funding crystallization timing impact on signal、Bybit-side rate limit on backfill query

**Specific questions to address**:
1. Bybit funding rate endpoint 是否 official 8h interval？funding tier 切換點對 funding skew signal 有 distortion 影響嗎？
2. funding crystallization timing (top of 8h) 對 signal trigger windowing 有 leak 風險嗎？
3. snapshot_ts_ms 在 Bybit funding rate query 是否 server-side or client-side？dual-source consistency check 有 done？
4. crowded_long_fade signal dead 是否 reflects Bybit demo testnet funding sample 不對稱（demo silent degradation per `feedback_demo_loose_live_strict_policy.md`）？
5. mainnet vs demo funding rate distribution 是否有 systematic offset 影響 z 計算？
6. 28d panel 擴展是否觸 Bybit rate limit on `/v5/market/funding/history` endpoint？

**Verdict expected**: APPROVE / RETURN / RED_FLAG（with Bybit API 引用 + dict v1.3 28c571c7 cross-ref）

---

## §6 FA (Functional Auditor) — Business Logic + Spec Compliance Review

**Scope**: spec v0.3 compliance、Round 1 → Round 2 narrative consistency、verdict letter accurate reflection of sweep table、AMD-2026-05-15-02 §8 condition 3 wording impact

**Specific questions to address**:
1. preliminary verdict `RED_PENDING_CONFIRM` → 7.0d final `RED_FINAL` 是否 spec v0.3 §verdict_protocol 明文許可？
2. crowded_long_fade signal dead 是否觸 spec §strategy_variant fallback design？
3. AMD-2026-05-15-02 §8 condition 3 wording 在 RED_FINAL 下需要哪些 wording 修訂？建議 patch 文字？
4. 4-cell sweep 是否符合 spec §sensitivity_design 數量 + 維度要求？
5. Stage 0R replay preflight `eligible_for_demo_canary` 在 RED_FINAL 下是否走 archive path 而非 retry?
6. AMD §8 condition 3 wording 修訂是否需要 dual-AMD（一個 retire signal、另一個 redirect to W-AUDIT-8c/8d）？

**Verdict expected**: APPROVE / RETURN / RED_FLAG（with spec line 引用 + AMD wording 對比）

---

## §7 Cross-Agent Reconciliation Checklist

After all 4 agents return, main session reconciles:

- [ ] 4 agent APPROVE / RETURN 分布
- [ ] MUST-FIX 條目去重 + cross-agent agreement matrix
- [ ] 衝突 verdict 識別（QC vs MIT 數學基礎、BB vs FA 對 exchange-side narrative 解讀）
- [ ] 共識 RED_FINAL 後 AMD §8 wording 修訂啟動
- [ ] dual-AMD strategy（retire + redirect）evaluate

---

## §8 Dispatch Protocol

**Trigger**: 7.0d panel confirm sweep 完成 + verdict 對齊 RED preliminary

**Dispatch**: 4 個 sub-agent parallel（QC / MIT / BB / FA），各自 background mode

**ETA**: 4-6h（per agent ~1-1.5h）

**Output integration**: main session 寫 consolidated verdict report `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-{{DAY}}--w_audit_8b_round2_red_final_4agent_consolidated.md`

**Next action chain**:
- RED_FINAL APPROVED by 4-agent → AMD §8 wording 修訂啟動 → archive W-AUDIT-8b Round 2 → redirect to W-AUDIT-8c/8a Phase B/C/D alpha source 軸
- RED_FINAL RETURNED → 主會話 RCA + 重新設計 W-AUDIT-8b Round 3 or retire

---

**Template END**. 7.0d confirm 後 fill-in `{{...}}` markers + dispatch.
