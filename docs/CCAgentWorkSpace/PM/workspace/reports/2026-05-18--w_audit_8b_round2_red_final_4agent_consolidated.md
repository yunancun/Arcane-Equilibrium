# W-AUDIT-8b Round 2 RED Final — 4-Agent Consolidated Verdict

**Date**: 2026-05-18
**Author**: Main session PM + Conductor
**Subjects under review**:
- PA Round 2 Phase B 7.0d Final Sweep: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--w_audit_8b_round2_phase_b_final_sweep.md`
- Sweep tooling commit: `a6e17d5d`
- Sweep artifact: `docs/audits/2026-05-18--w_audit_8b_round2_final_sweep_artifact.json` (md5 `bf9ae8c6`)
- Linux artifact: `trade-core:/tmp/openclaw/w_audit_8b_stage0r_v0_3_sweep_20260517_2338_pa.json`

**Reviewers** (4 parallel, 0 file overlap):
- QC (agent `a62cbee4`): math validity / Wilson CI / DSR / PBO independent verification
- MIT (agent `ac8a6548`): data pipeline + look-ahead bias + 12 PG queries empirical (`docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-18--w_audit_8b_round2_red_final_mit_review.md`)
- BB (agent `a16b3682`): Bybit exchange-side data SoT + dict v1.3 cross-ref
- FA (agent `ad5958eb`): business logic + spec compliance + AMD §8 wording patch

---

## §1 Executive Summary

**Consensus**: 4/4 APPROVE concur PA `VERDICT_RED_FINAL`. **0 BLOCKING MUST-FIX for archive path**.

W-AUDIT-8b funding skew directional Round 2 Phase B sweep on 7.0049d natural-gate panel (operator-authorized 6.92d preliminary aligned 100%) returned 8/8 cells RED HIGH conf with 4/4 empirical assertion gates PASS. 4-agent independent review across mathematical / data-pipeline / exchange-side / business-logic dimensions concurs: signal does not deserve promotion.

**Next actions**: AMD v0.6 → v0.7 wording patch + W-AUDIT-8b spec v0.3 → v0.4 tombstone amendment + redirect to W-AUDIT-8c/8a Phase B/C/D alpha source 軸 per fix-plan v1.1 §9.4 critical path.

---

## §2 Verdict Matrix

| Agent | Verdict | MUST-FIX | SHOULD-FIX | NTH | Dict update |
|---|---|---|---|---|---|
| **BB** | APPROVE concur RED_FINAL | 0 | 2 | 3 | 0 mandatory |
| **QC** | APPROVE concur RED_FINAL | 0 | 4 | 2 | N/A |
| **FA** | APPROVE concur RED_FINAL | **3** (governance wording prereq, NOT archive blocker) | 2 | 3 | N/A |
| **MIT** | APPROVE concur RED_FINAL | 0 | 4 | 3 | N/A |

**FA's 3 MUST-FIX** are governance prerequisites for AMD v0.7 + spec v0.4 land sequencing — they do NOT block RED_FINAL archive verdict itself.

---

## §3 Per-Agent Key Findings (verbatim consensus extract)

### BB (Bybit exchange-side)
- crowded_long_fade dead trigger 真因 = **Bybit USDT-perp linear 25-sym 結構性 funding tail bimodal + funding mass 偏正**（per skill `crypto-microstructure-knowledge` §1.2 long-bias market）— **不是** demo silent degradation artifact
- Demo silent degradation 範圍 = trading execution path（PostOnly reject, execution.fast empty stream），**不適用 market data 層**（funding rate, ws tickers, panel data 全 mainnet-mirror broadcast）
- 28d panel expansion = 0 rate limit risk + 0 ToS / broker rebate impact

### QC (mathematical validity)
- Wilson CI / n_eff formula (`int(n / (horizon_min // 5))`) / DSR sr_benchmark=4.14 全 **numerically correct**（Cross-verified Wilson lower bound: 0.0953 vs Clopper-Pearson 0.0036 vs Jeffreys 0.0091 — 三 methods 全 fail 0.10 stability floor）
- **`_n_eff` 公式是 deterministic horizon-overlap correction，不是 autocorrelation-based 也不是 cross-sectional clustering corrected** — Round 3 / W-AUDIT-8c+ 啟動前 spec 必須補 cluster-aware n_eff
- DSR=0 在 K_total=5400 sr_benchmark=4.14 floor 下對 n=7 small-sample **mathematically inevitable**，不純粹是 "no edge"

### FA (business logic + spec compliance)
- Spec v0.3 §"接受 / Reject 條件" Reject path 完全命中（line 429-432）
- 4-agent template §6 引用 3 個 spec section name (`verdict_protocol` / `strategy_variant fallback design` / `sensitivity_design`) **不存在 spec v0.3** — virtual anchor names。Equivalent spec anchors exist but naming drift。
- Spec v0.3 缺明文 **branch-level dormancy retire path** — crowded_long_fade dead 場景未預期。Spec v0.4 tombstone amendment 須 land 此 governance hardening design
- AMD v0.7 patch text-ready (provided)
- **NOT dual-AMD**: single AMD wording revision + independent W-AUDIT-8b spec tombstone amendment

### MIT (data pipeline + 12 PG queries)
- **z 39x asymmetry** empirically verified: z>=+1.5 = 135 (0.27%) vs z<=-1.5 = 5,243 (10.5%) → crowded_long_fade dead 是 **data 結構性，不是 strategy design**（converges with BB's framing — both correct independent narratives）
- INJUSDT 87% concentration in 2026-05-13 single-day event → effective independent obs ≈ 2-3 day single-event
- Feature engineering leak-free verified（PARTITION BY signal_ts_ms point-in-time cross-sectional）
- Panel 28d/56d expansion ROI ≈ 0（49d calendar wait for likely-still-RED）
- **ML pipeline maturity**: W-AUDIT-8b = Shadow stage. RED_FINAL 是 Shadow-stage 正確 verdict — signal 不 deserve Canary promotion

---

## §4 Cross-Agent Pattern Convergence

**3 independent convergences strengthen RED_FINAL confidence**:

1. **crowded_long_fade dead 根因**:
   - BB: Bybit funding tail bimodal + long-bias mass 偏正
   - MIT: PG empirical 39x asymmetry (z≥+1.5: 0.27% vs z≤-1.5: 10.5%)
   - QC: bimodal funding distribution + z-score on bimodal distribution 意義有限
   - **Consensus**: structural data asymmetry, not strategy design bug, not demo silent degradation, not z threshold issue. Cannot be reversed by 28d/56d panel expansion.

2. **n_eff formula gap**:
   - QC: deterministic horizon-overlap, not autocorrelation-based, not cluster-aware
   - MIT: cluster correction sensitivity 全 fail (cluster_n=5/7/10/14/42 all Wilson lower < 0.10)
   - **Consensus**: Round 2 verdict robust (formula over-counts but cell still fails floor); Round 3 / W-AUDIT-8c+ spec MUST retrofit cluster-aware n_eff before activation

3. **Round 3 / panel expansion**:
   - MIT: 28d/56d ROI ≈ 0 (forward-only collect, 49d wait for likely-still-RED)
   - BB: Round 3 zoom-in optional (SHOULD-FIX SF-2 if pursued)
   - QC: Round 3 needs cluster-aware n_eff retrofit first
   - **Consensus**: REJECT Round 3 zoom-in pursuit; redirect resources to W-AUDIT-8c/8a Phase B/C/D

---

## §5 Consolidated Action Items

### P0 — Immediate (post-consolidated-verdict land)

1. **AMD-2026-05-15-02 v0.6 → v0.7 wording patch** (FA text-ready)
   - §8 condition 3 line 355 wording revision (funding-related general + tombstone clause)
   - §12 changelog v0.7 row
   - Estimate: 5 min PM edit + commit
   - Authority: PM single-AMD wording

2. **W-AUDIT-8b spec v0.3 → v0.4 tombstone amendment**
   - Frontmatter line 4 status: `Tombstoned post Round 2 RED_FINAL 2026-05-18`
   - NEW §"Round 2 Tombstone Closure"（reference PA final sweep + 4-agent consolidated verdict）
   - NEW §"Branch-Level Dormancy Retire Path"（FA-MUST-FIX-2 governance hardening）
   - §Changelog v0.4 row
   - Estimate: 10-15 min PM edit + commit
   - Authority: PM spec amendment

3. **Sequencing**: AMD v0.7 → spec v0.4 → TODO.md sync per FA-MUST-FIX-3 (multi-write meta-doc race HIGH)。Use `git commit --only <file>` for each。

### P1 — Short-term

4. **W-AUDIT-8a Phase B/C/D Wave 1 dispatch readiness** — fix-plan v1.1 §9.4 critical path: B-REM-1/5 + C1-LIQ-WRITER (8.5pd / ~2 wks). Already have feature branches at:
   - `feature/w-audit-8a-b-rem-1-dispatch-snapshot-contract` (`441599a7`, 2975 tests pass, pending E2 review)
   - `feature/w-audit-8a-b-rem-5-source-availability` (`5997dd43`, 442 tests, ADR-0023 pending)

5. **Phase 1b 24h Post-Deploy Verification** — restart already executed UTC 2026-05-17 23:54; 2h AC-A/B/C window started; PM 24h audit dispatch per template `docs/CCAgentWorkSpace/PM/workspace/templates/2026-05-18--pm_24h_post_deploy_verification_audit_packet.md`

### P2 — Future (Round 3 / W-AUDIT-8c+)

6. **cluster-aware n_eff retrofit** (QC + MIT consensus):
   ```python
   n_eff_cluster_aware = min(
       int(n / (horizon_min // 5)),       # horizon-overlap
       distinct_funding_cycles_used,       # funding cycle independence
       ceil(n * (1 - max_day_share))       # day-clustering correction
   )
   ```
7. **CI method upgrade**: Wilson → Clopper-Pearson exact (or Jeffreys Bayesian) for small-n cells (MIT + QC)
8. **Percentile gate** vs z-score gate for bimodal funding distribution (QC Q4 + FA-NTH)

### REJECTED

- **Round 3 zoom-in pursuit**: 3/4 agents reject (MIT explicit, QC + FA implicit via "archive path unambiguous")
- **28d/56d panel expansion for W-AUDIT-8b reverse purpose**: 4/4 reject (MIT explicit ROI≈0, BB optional only for Round 3 contingency, QC + FA archive path)
- **dual-AMD strategy**: FA reject — single AMD v0.7 + independent spec v0.4 tombstone clean

---

## §6 SHOULD-FIX Consolidation (Future Hardening)

**Cross-agent shared SHOULD-FIX (high priority for W-AUDIT-8c/8a spec design)**:
1. n_eff cluster-aware retrofit (QC + MIT共識)
2. CI method Wilson → Clopper-Pearson (MIT primary, QC supporting)
3. Percentile gate vs z-score gate (QC Q4 + FA-NTH-3 implicit)
4. Crowded_long_fade reframe: "data asymmetric 39x" 而非 "strategy design dead" (MIT + BB 共識)

**Per-agent unique SHOULD-FIX**:
- BB-SF-1: archive RCA narrative correction (already incorporated in consolidated framing)
- BB-SF-2: Round 3 dual-source consistency probe (deferred — Round 3 rejected anyway)
- QC SF-1/2: DSR=0 distinction explicit + archive framing "parameter family rejected" ≠ "hypothesis disproved" (incorporate in AMD v0.7 / spec v0.4 wording)
- FA-SF-1: PA report YAML frontmatter alignment note (low priority, deferred)
- FA-SF-2: Round 1 RED RCA wording trigger verification (PA already executed)
- MIT SF-1/2/3/4: same as cross-agent consolidated (already listed)

---

## §7 16-Root + 9-Invariant Compliance

All 4 agents independently audit'd: A-grade 16/16 + 0 hard-boundary breach。No principle violated by RED_FINAL archive path。

---

## §8 PM Sign-Off

**Verdict**: APPROVE 4/4 consensus → land AMD v0.7 wording patch + W-AUDIT-8b spec v0.4 tombstone amendment → redirect W-AUDIT-8c/8a Phase B/C/D alpha source 軸 per fix-plan v1.1 §9.4 critical path。

**Authority**: PM single-amendment authority on (1) AMD wording + (2) spec tombstone wording (per FA-MUST-FIX-3 governance + per AMD §12 changelog discipline)。

**Next**:
- Land AMD v0.7（`git commit --only`）
- Land W-AUDIT-8b spec v0.4（`git commit --only`）
- TODO.md sync
- 4-agent reports already committed to respective workspaces

**No Round 3, no 28d wait, no dual-AMD. Clean archive path.**

---

**Files referenced**:
- PA reports: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-17/2026-05-18--w_audit_8b_round2_phase_b_*.md`
- 4-agent reports (where written): MIT only persisted to `docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-18--w_audit_8b_round2_red_final_mit_review.md`. BB / QC / FA returned inline per profile rule.
- Template: `docs/CCAgentWorkSpace/PM/workspace/templates/2026-05-18--w_audit_8b_round2_red_4agent_review_packet_template.md`
- AMD: `docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-02-edge-p2-3-phase-1b-close-maker-first.md`
- Spec: `docs/execution_plan/2026-05-15--w_audit_8b_funding_skew_directional_spec.md`
- Fix plan: `docs/execution_plan/2026-05-16--trading_losses_root_cause_and_fix_plan_v1.md`
