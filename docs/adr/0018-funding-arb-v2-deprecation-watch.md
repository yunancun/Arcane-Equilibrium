# ADR 0018: Funding Arb V2 Retires From Active Strategy Set

Date: 2026-05-09（initial Accepted）· 2026-05-26（Status 升格 Retired per AMD-2026-05-26-01）
Status: **Retired closed** (upgraded 2026-05-26 per AMD-2026-05-26-01；原 2026-05-09 "Accepted - retire from active strategy set" 為前置條件)

> **2026-05-26 升格說明**：本 ADR §Decision 原為「retire from active set + W-AUDIT-6 cleanup pending」條件性語意。Operator 2026-05-26 對 `P0-FUNDING-ARB-DECISION-FORCE` 選 (D) 3C TOML deprecation closure，由 AMD-2026-05-26-01 將本 ADR 終結為 **Retired closed**。Revive 須走 AMD amendment + ADR-0046 (Proposed) Accepted + 5-gate + Stage 0R replay preflight（per AMD-2026-05-15-01）。

## Context

`funding_arb` produced poor demo evidence and operational noise. Current risk
configs prevent new funding_arb entries while preserving tighter handling for
legacy positions. `P0-DECISION-AUDIT-4` selected the PA-recommended strategy
verdict: retire `funding_arb` from active promotion and clean it from active
RiskConfig schema in W-AUDIT-6.

**2026-05-16 14d audit 證據追加**（`helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.py`）：n=18 dormant 確認 22d 0 新增 sample；governance 路徑 deadlock（無 closure path）→ 升 `P0-FUNDING-ARB-DECISION-FORCE`。

**2026-05-25 QC EA-3 verdict（per PA overturn 引用）**：V2 delta-neutral 數學在 Bybit 結構性不成立（spot lending 缺失 + 34 bps cost / 1.5 bps funding mean → 7.6 day break-even infeasible）。V2 不是「參數沒調對」可以救活；是 design 層面 stuck。

## Decision

**2026-05-26 升格 wording**（per AMD-2026-05-26-01）：

funding_arb V2 **Retired closed**。enforcement 在 TOML config-load 層：三端 `[funding_arb].active = false`（commit `a19797d` 已 land），engine 啟動時 `registry.rs` 經 `set_active(p.funding_arb.active)` 載入 → 不掛載任何 entry。72 unit tests 保留為 dormant 結構驗。

**doc-vs-code 訂正（2026-06-14 TW，per PA `2026-06-14--cold_audit_validated_fix_plan` funding 治理漂移家族 CC/FA MEDIUM）**：AMD-2026-05-26-01 §3.2 / cascade spec §1.2 規劃的「Rust 程式碼層 `#[deprecated]` marker + `update_params()` runtime fail-closed guard（拒絕 IPC `active=true` 注入）」屬 **D+7 E1 IMPL 範疇，從未 land**——`funding_arb.rs:156-177` `update_params()` 仍照 `self.active = params.active` 接受 IPC 注入；`registry.rs:240-251` 無 `#[allow(deprecated)]` 包裹也無強制 false。**當前唯一 enforcement = TOML config-load active=false；無 runtime IPC active=true 注入 guard。** 由於策略已 dormant（不在 active demo risk_config，無 live-money path），不補 guard（加 guard 屬擴 scope）；本訂正僅對齊文字陳述與代碼實態。W-AUDIT-6 RiskConfig cleanup 之 D+7 E1 IMPL 未執行。

`funding_arb.rs` 模組保留作為 ADR-0046 (Proposed) future redesign slot；ADR-0046 並存不 retire。Revive 路徑 3 hard gate：
1. 新 AMD super-cedes AMD-2026-05-26-01 + V3 design rationale
2. ADR-0046 Accepted（V3 IMPL + V117 migration spec 全 land）
3. 5-gate + Stage 0R replay preflight PASS

**原 2026-05-09 wording（歷史保留）**：
> Keep funding_arb new entries disabled across active runtime configs and retire it from active strategy promotion. W-AUDIT-6 may remove active RiskConfig schema entries after targeted source/test cleanup. The 2026-05-16 audit remains a verification artifact for historical impact and legacy-row handling, not the retirement decision gate.

## Consequences

- **W-AUDIT-6 cleanup completion = Workflow F (2026-05-26)** per AMD-2026-05-26-01 D+0/D+7/D+30 三階段。
- Replay/ML/training consumers should not promote funding_arb from immature or
  contaminated samples.
- Existing positions or historical rows remain auditable; PG retention 30d 自然 drop（不手動 DELETE，避免破壞 attribution lineage）。
- 5 textbook strategy roster → **4 textbook reframe**（funding_arb 移除）；TODO §1 P0-EDGE-1 AC cohort + execution-plan v5.8 + MIT MIN_SAMPLES gating 同步收斂。
- ADR-0046 future redesign slot 並存保留；D+30 PA follow-up 評估是否同步 retire。

## References

- AMD-2026-05-26-01: `docs/governance_dev/amendments/2026-05-26--AMD-2026-05-26-01-funding-arb-deprecation.md`
- PA Workflow F Phase 1 spec: `docs/execution_plan/specs/2026-05-26--funding-arb-deprecation-cascade.md`
- AMD-2026-05-09-02 W-AUDIT-6 strategy verdict: `docs/governance_dev/amendments/2026-05-09--operator_decision_audit_closure.md`
- AMD-2026-05-15-01 Stage 0R replay preflight (revive gate): `docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md`
- ADR-0046 funding_arb future redesign slot: `docs/adr/0046-funding-arb-v3-redesign-slot.md` (Proposed; PA Sprint 1A-δ/ε)
- 14d dormant evidence: `helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.py`
- 3C TOML commit: `a19797d` (2026-05-02 base_ratio 0.4→0.25 + funding_arb 3% override)
