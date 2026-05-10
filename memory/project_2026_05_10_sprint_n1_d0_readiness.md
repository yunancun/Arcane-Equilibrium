---
name: Sprint N+1 D+0 pre-dispatch readiness 2026-05-10
description: Sprint N+1 D+0 提前準備 25 項全 land；HEAD bf66f1b2；W7-3+W7-1+W2 trait skeleton PR ready NOT DEPLOYED；W6 RFC verdict draft + W2 v1.2 + W1 v1.1 + W5 三 P1 specs + V089/V090 reserved；CC A- 92.0% APPROVE-CONDITIONAL + E3 ALL PASS + R4 8 fix land；sign-off 後純執行
type: project
originSessionId: 4111ef84-e51d-4d16-99bf-f40bf3aa8fe8
---
## State (2026-05-10 19:30 UTC pre-signoff)

**HEAD**: `bf66f1b2`（chain: b6ed4975 → 786c1c68 → da2d2a46 → 4d0f6a55 → 35a28302 → 5cec3a3c → b42731f6 → c9fb0b8f → eca951e7 → da6c1f80 → 4bb5d485 → d914c02e → b1e5d6da → 1d9dccf1 → 28cbfeda → 9695b59a → bf66f1b2）

## Sprint N+1 D+0 提前準備清單（25 項全 land）

### Code change PR ready (NOT DEPLOYED)
1. **W7-3 Option B** (`b42731f6`): ma_crossover.on_rejection 識別 duplicate_position → sync self.positions, +48 LOC strategy_impl.rs + 152 LOC tests, E1+E2 APPROVE+E4 PASS
2. **W7-1 + W2 trait skeleton** (`c9fb0b8f`): TickContext.position_state per-iteration borrow + BtcLeadLagPanel + AlphaSurface field, 16 file +182 LOC, 0 borrow checker, 433+2640+35 PASS

### Specs / RFC drafts
3. W2 A4-C BTC→Alt Lead-Lag spec **v1.2** (5 conditions + dual-layer σ + PSR(0) Bailey-López de Prado skew/kurt + +15/+5-15/<+5 階梯 gate, V088 加 3 column)
4. W1 Phase B Tier 2 collector spec **v1.1** (BB WS-first revision, Rust panel_aggregator, rate 100→0 req/s ongoing)
5. W6-1 RFC final verdict draft (8 section, 4 條 verdict, Track A/B 拆分)
6. W6-3a close_tag distribution audit (12+14 enum + V086 spec preview)
7. W6-3b enum spec final (5 ambiguous A1-A5 全 ACCEPT MIT, V086 two TEXT column + one-shot 30-90s in-migration backfill)
8. W5 P1-CANARY-STAGE-CRITERIA-1 spec (340 LOC, AMD-2026-05-10-05 起草, [58] enrich)
9. W5 P1-CANARY-COHORT-FREQ-23 spec (360 LOC, AMD-2026-05-10-06, [63] healthcheck, **V089 governance.cohort_freq_cap_attempts**)
10. W5 P1-DYNAMIC-UNBLOCK-CHECK-1 spec (760 LOC, [64] healthcheck, **V090 governance.unblock_candidates**, reuse blocked_symbols_7d_counterfactual.py 改 30d)

### Audits + Reviews
11. PA #1 AlphaSurface trait coord (W1+W2 並行 0 file 重疊)
12. PA #2 W6 RFC PA-view (4 hold A + 6 dispatch update)
13. PA #3 P1-MA-CROSSOVER audit (HIGH confidence systemic, 升 P0 W7)
14. PA W7-4 5 策略 systemic position sync audit (HIGH×2 ma_cross + bb_reversion)
15. PA P2 雙前綴 RCA (4-23 已 fix 無需 P2 ticket; V086 同 migration 加 trading.fills 17 row UPDATE)
16. QC TONUSDT 7-30d structural edge replay (verdict C conditional path)
17. QC W6 RFC QC-view (4 hold A)
18. QC W2 alpha decay + DSR review (CONDITIONAL APPROVE 5 conditions)
19. MIT chain integrity 4-7d historical (chain 100% pre+post V083, mock baseline 誤讀)
20. MIT W6 baseline 預跑 (governance 沒 over-fit, real gap = metadata + imbalance + duplicate_intent)
21. MIT W6 RFC MIT-view (Q1 W6-5 category error 揭露 / Q3 18+ 類兩 column)
22. MIT C-3 σ verify (CONDITIONAL PASS, dual-layer reframe, kurt 7-12 必 PSR(0) skew/kurt formula)
23. BB W1+W2 rate budget review (PASS 99% headroom + W1 WS-first push back)
24. E4 W4 W-AUDIT-3b smoke design (push back 既有 9 case, RouterLeaseGuard Drop ~40 LOC, 4 invariant)

### Sign-off prep
25. N+0 sign-off + N+1 dispatch fire SOP

### v3.8 governance reviews
- CC compliance pre-check **APPROVE-CONDITIONAL Score A- 92.0%** (vs N+0 A 93.3%, -1.3pp)
  - 16 原則 13✅/3⚠️/0❌ / 5 硬邊界 5/5 / 22+23 invariant 21.5✅/1.5 DEFER
  - 5 conditions (D+0 deploy 前必檢): W7-3 deploy SOP / W2 paper-only fence Layer 1 / AMD-2026-05-1X-W6-1 verdict / AMD-2026-05-10-06 / ADR-0021 (N+2 前必寫)
- E3 security pre-audit **ALL PASS** (0 CRITICAL/HIGH/MEDIUM, 3 LOW backlog 不阻 D+0)
  - 5 hard gate 全綠 / Secret leak scan PASS
- R4 docs audit 8 fix CRITICAL+HIGH+MED 已 land (HEAD bf66f1b2)
  - docs/README.md 加 7 entry / CLAUDE.md §三 [40]/Active Blockers/§十 update / CLAUDE_CHANGELOG.md N+0 + N+1 D+0 entry

## V### 編號 reserved (V085-V090)

| V### | Wave | Purpose |
|---|---|---|
| V085 | W1 | funding_curve writer (WS broadcast → panel.funding_rates_panel 5m/15m/1h chunks) |
| V086 | W6 | reject_reason_code + close_reason_code two TEXT column (high priority, 12+14 enum + 30-90s in-migration backfill) |
| V087 | W1 | oi_delta_panel writer (WS broadcast → panel.oi_delta_panel 5m/15m/1h chunks) |
| V088 | W2 | panel.btc_lead_lag_panel + 3 column (60s/300s shadow + R²(N) decay support) |
| V089 | W5 | governance.cohort_freq_cap_attempts (P1-CANARY-COHORT-FREQ-23 invariant 23) |
| V090 | W5 | governance.unblock_candidates (P1-DYNAMIC-UNBLOCK-CHECK-1 30d cycle) |

## Sign-off 後 D+0 sub-agent dispatch (純執行)

**Phase 1 (21:30 UTC HIGH-5 sign-off + 5 min)**：
- 一次 restart_all --rebuild --keep-auth deploy W7-3 + W7-1 + W2 trait skeleton
- 30 min observation: ma_crossover INXUSDT reject < 10/min + chains_with_lease > 0 + bad_report_quality = 0

**Phase 2 (sign-off + 30 min~)**：派 9 wave 並行 sub-agent dispatch:
1. W7-2 (E1, ma_crossover entry path 用 ctx.position_state + bb_reversion 同 pattern, ~25 LOC + 4 unit test)
2. W7-4 (PA + E1, 5 策略 systemic audit using ctx.position_state, 1 day)
3. W7-5 (E1, on_fill + bootstrap import_positions, ~20 LOC + tests)
4. W6 RFC verdict 三角 sign-off (PA + QC + MIT 各 1.5h verify + 1h sync → AMD-2026-05-1X-W6-1 land)
5. W6 V086 IMPL (E1, two TEXT column + 30-90s in-migration backfill + trading.fills 17 row UPDATE)
6. W1 IMPL Rust panel_aggregator WS-first (E1-α leader broadcast migration + E1-β/γ rebase parallel + V085/V087)
7. W2 IMPL v1.2 (E1, lead-lag producer + V088 + ma_crossover/grid 接 BtcAltLeadLag paper-only shadow log)
8. W4 RouterLeaseGuard Drop test (E4, ~40 LOC Rust unit test)
9. W5 三 P1 IMPL (W5-E1-A/B/C, ~1460 LOC, V089/V090 + AMD-2026-05-10-05/06)

**W3 Stage 1 cohort 暫不派**（等 W6 + W7 完成 ~D+3-4 啟動）

## Critical realities (不可忽視, 4-agent loss audit consensus 維持)

1. **5 textbook 策略結構性 alpha-deficient**（grid + ma + bb_breakout + bb_reversion + funding_arb）— W6 governance 沒 over-fit 確認；真正解是 alpha source 補充（W2 A4-C / W-AUDIT-8a Phase B/C/D / 8b/8c/8d 候選）
2. **TONUSDT P1-CONDITIONAL-WATCH** 30d evidence 收集中（QC verdict C, 不立即 freeze 避 17→18 cells permanent dormant 負反饋）
3. **W6-5 LightGBM imbalance handling 撤回**（MIT category error: scorer_trainer 是 regression）— 改 sample_weight ratio sensitivity 試行
4. **W6-3 真實 18+ 類兩 column** (vs preliminary 3 類 single column)
5. **W6 ML retrain Track A/B 拆分** close PA Q3 vs MIT Q2 V086 timing 分歧；Track A regression scorer 微調 immediate (不需 V086)；Track B multi-class 4-gate (留 N+2/N+3)
6. **dual-layer σ acceptance**（raw market σ_60=4.54 vs net edge σ=50-80 bps）；W2 +15 bps gate 在 σ_net=80 bps marginal PASS

## 21:30 UTC sign-off SOP

詳 `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--n0_signoff_n1_dispatch_fire_sop.md`

## 重要 reference paths

- Sprint N+1 dispatch v3.7: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--sprint_n1_dispatch_draft.md`
- W2 A4-C spec v1.2: `srv/docs/execution_plan/2026-05-10--a4c_btc_alt_lead_lag_spec.md`
- W1 Phase B spec v1.1: `srv/docs/execution_plan/2026-05-10--w_audit_8a_phase_b_tier_2_collector_spec.md`
- W5 三 P1 spec: `srv/docs/execution_plan/2026-05-10--p1_canary_stage_criteria_1_spec.md` + `_p1_canary_cohort_freq_23_spec.md` + `_p1_dynamic_unblock_check_1_spec.md`
- W6-1 RFC verdict draft: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w6_1_rfc_final_verdict_draft.md`
- N+0 sign-off SOP: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--n0_signoff_n1_dispatch_fire_sop.md`
- W7-3 deploy SOP: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--w7_3_deploy_sop.md`
- CC pre-check: `srv/docs/CCAgentWorkSpace/CC/workspace/reports/2026-05-10--n1_d0_signoff_compliance_pre_check.md`
- E3 security audit: `srv/docs/CCAgentWorkSpace/E3/workspace/reports/2026-05-10--n1_d0_security_pre_audit.md`
- R4 docs audit: `srv/docs/CCAgentWorkSpace/R4/workspace/reports/2026-05-10--n1_d0_docs_audit_pre_signoff.md`

## Sprint N+1 estimated duration

7-10 day (per dispatch v3.7 §2 Wave 結構)；W7 從原 4 day 縮到 2-3 day（W7-1 + W7-3 提早 land 共省 1.5 day）；W6 5 day；W1 6 day；W2 7 day；W3 5 day（等 W6+W7）；W4 1 day；W5 分散
