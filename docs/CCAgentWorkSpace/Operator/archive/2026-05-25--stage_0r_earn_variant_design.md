---
report: PA Stage 0R Earn variant design spec (Sprint 1B Earn Wave C carry-over 仲裁)
date: 2026-05-25
agent: PA (Project Architect)
phase: Sprint 1B late Pending 3.2 Earn Wave C — STAGE-0R-EARN-VARIANT-DESIGN-DRAFT
head: (Mac local, pre-commit)
trigger: PM Sprint 1B Earn Wave C 「Stage 0R Earn variant 仲裁」carry-over dispatch (per 2026-05-24 audit line 20/90)
verdict: DRAFT-DESIGN-DONE — 656 行 spec land + 5 AC 對齊 + 8 OQ 待 operator 拍板
---

# PA Stage 0R Earn Variant Design Report — 2026-05-25

## §1 Output

| Element | Value |
|---|---|
| Spec path | `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-25--stage_0r_earn_variant_design_spec.md` |
| Lines | 656 |
| Sections | §1-§10 完整 (Status / Scope / Replay harness design / 5 AC / 5-gate inheritance / Earn-specific risk / IMPL roadmap / Open Questions / Cross-refs / Sign-off) |
| 5 AC 對齊 | ✅ 完整 (AC-1 drift / AC-2 IntentProcessor branch / AC-3 V100 row deferred / AC-4 fail-closed reject / AC-5 ATR cap N/A + drawdown gate partial) |
| Open Questions | 8 條 (OQ-1 強制必跑 / OQ-2 Sprint 5+ defer / OQ-3 AC-3 deferred / OQ-4 sub-scope (o) / OQ-5 5% drift / OQ-6 live endpoint / OQ-7 不 retry / OQ-8 鏡像 audit_log) |
| Skip 條件 | 4 場景 (dust ≤ $10 / stable APY 7d Δ < 0.5% / emergency redeem / read-only query) |

## §2 Key Design Decisions

1. **Earn 不是 strategy** — Earn 沒有 alpha edge 可驗;5 sanity check 為 (a) APY drift 5% (b) 5-gate reject coverage (c) cron dry-run 3 cascade (d) liquidity gate latency (e) runtime boundary;移除 C10 範式 leak/bias/DSR/PSR/PBO 4 條
2. **Dry-run boundary** 5 不變量:不發 stake/redeem 寫單 / 不寫 V100 / 不動 demo balance / 不繞 5-gate / 不污染 V100 schema
3. **5-gate inheritance**:protected (b)/(e) 適用其他 N/A;opt-in (j) 適用 (m)/(n) partial Sprint 5+;**新 sub-scope (o) Earn asset write** 提案 Level 1+2 都 manual
4. **5 Earn-specific risk**:APY 變動 MEDIUM / Liquidity LOW / Withdrawal gate LOW / Cross-product cannibalize MEDIUM / Demo vs live drift LOW
5. **IMPL chain**:PA spec → QA+MIT+FA 3 cross-ref → E1 IMPL `replay_earn_preflight.py` (~4-6 hr) → E2 adversarial → E4 regression → QA acceptance → PM Phase 3e sign-off → Operator OP-1 key refresh → first stake

## §3 E2 重點審查 3 點

per PA profile.md「高風險警告:E2 必須重點審查的 3 個點」:

1. **harness exit code 邏輯 (AC-4)** — harness 若任 1 sanity check FAIL 必 exit 1;不可 exit 0;若漏條件 → Stage 0R fail-closed reject 機制破損 → Stage 1 Demo micro-canary 誤啟動
2. **Dry-run 邊界 §3.5 5 不變量** — grep 0 hit `subscribe_flexible` / `redeem_flexible` / `EarnMovementWriter.insert_placeholder`;若 harness 誤調 production writer → 污染 V100 schema
3. **Mock 5-gate reject path 完整性** — 5 個 fail injection 各觸 1 次 + audit event_type 對齊預期值;若 mock 只蓋部分 → 5-gate 機制覆蓋率失真

## §4 Risk Assessment

| Risk | Severity | Mitigation |
|---|---|---|
| Earn replay 模擬 ≠ 真實 Bybit Earn behavior | LOW | Stage 0R 不取代 demo Earn 7d 真實 fill-lineage;preflight + Stage 1 Demo 雙保險 |
| OQ-4 新 sub-scope (o) 提案 operator 拒採納 | MEDIUM | spec 預列 (b) 5-gate live boundary 子集 fallback path |
| OQ-2 Sprint 5+ stake/redeem/reparam variant defer 引入後延 | LOW | first stake variant 是 Sprint 1B 唯一硬阻塞;其他 variant Sprint 5+ 才解 |
| AC-1 5% drift threshold 偏鬆 | MEDIUM | Bybit Dynamic Settlement 動態 APR 容許 ±0.5%;5% 仍能 catch 結構性 drift |
| Cross-product cannibalize Sprint 5+ M10 未 land | MEDIUM | §6.4 spec 明示 mitigation deferred Sprint 5+ M10 capital tier evaluation |

## §5 Next Steps

per spec §7 IMPL roadmap:
1. PM 接受本 spec → dispatch QA+MIT+FA 三方 cross-ref (parallel, ~3-5 hr 各)
2. operator 拍板 8 OQ
3. E1 Wave C IMPL `helper_scripts/canary/replay_earn_preflight.py` (~4-6 hr)
4. E2 adversarial review (~2-3 hr)
5. E4 regression (~1-2 hr)
6. QA Stage 0R Earn variant acceptance (5 AC 逐條驗 empirical) (~2-3 hr)
7. PM Phase 3e sign-off (~1 hr)
8. Operator OP-1 Bybit Web UI key 重發 (~30-60 min)
9. Operator first stake $100-200 Flexible USDT 走 Wave E (~10-30 min)

## §6 Cross-Refs

- Spec: `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-25--stage_0r_earn_variant_design_spec.md`
- AMD-2026-05-15-01: `docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md`
- ADR-0034: `docs/adr/0034-decision-lease-layered-approval-lal.md`
- AMD-2026-05-21-01 v2: `docs/governance_dev/amendments/2026-05-22--AMD-2026-05-21-01-autonomy-fully-with-failsafe.md`
- earn_governance spec: `docs/execution_plan/2026-05-21--earn_governance_spec.md`
- C10 範式: `helper_scripts/canary/replay_funding_harvest.py`
- Earn Wave B IMPL: `rust/openclaw_engine/src/{bybit_earn_client,database/earn_movement_writer,cron/earn_reconciliation}.rs` (commit 875de212)

---

PA DESIGN DONE: report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-25--stage_0r_earn_variant_design.md
