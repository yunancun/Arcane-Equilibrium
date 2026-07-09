# ADR 0046: funding_arb V3 Redesign Slot（Basis Observation vs Execution Split）

Date: 2026-05-25（BB APPROVE 候選 proposal）· 2026-05-26（隨 AMD-2026-05-26-01 確立為 revive-gate placeholder）
Status: **Proposed**（decision TBD；尚未 Accepted）

> **定位說明**：funding_arb V2 已 **Retired closed**（per ADR-0018 + AMD-2026-05-26-01）。本 ADR 是 funding_arb 「未來重設計」的占位 slot 與 **revive 硬閘**：`funding_arb.rs` 模組保留不刪，運行時 `active=false` 經 TOML config-load 強制（三端 `[funding_arb].active = false`，`registry.rs` 載入時不掛載 entry）；任何 revive 必須先讓本 ADR 從 Proposed 升 Accepted（含 V3 IMPL + V117 migration spec 全 land）。**本 ADR 目前未 Accepted，不得作為 funding_arb 重新上線的依據。**

## Context

`funding_arb` V2 在 2026-05-26 被 operator 終結為 Retired closed（`P0-FUNDING-ARB-DECISION-FORCE` 選 (D) 3C TOML deprecation closure）。終結理由（per QC EA-3 / AMD-2026-05-26-01）：

- V2 delta-neutral 數學在 Bybit 結構性不成立：spot lending 缺失 + 34 bps cost / 1.5 bps funding mean → 7.6 day break-even infeasible。
- 不是「參數沒調對」可救活；是 design 層面 stuck。

但 AMD-2026-05-26-01 明確 **不** retire 重設計的可能性：保留 `funding_arb.rs` 作為 future redesign slot，並把「重設計屬於哪個治理載體」這個問題指向本 ADR-0046。2026-05-25 BB review 提出候選方向 **basis observation vs execution 分維**（scope 限 funding_arb；cross-venue + options 列 Future Work），24-30 hr IMPL，預估 Sprint 1A-δ/ε 平行 land。本 ADR 把該 slot 正式登記為 Proposed，使 ADR-0018 / AMD / TOML / 各 docs 對「ADR-0046」的引用有可載入的 artifact，而非懸空 ID。

## Decision

**Proposed — decision TBD。** 本 ADR 尚未對「funding_arb 是否重設計、如何重設計」下最終決定；它先固定以下兩件事：

1. **Slot 保留契約**：`funding_arb.rs` 模組保留不刪（72 unit tests 保留為 dormant 結構驗），運行時 dormant 由 TOML config-load `active=false` 強制。AMD-2026-05-26-01 §3.2 曾規劃 `#[deprecated]` marker + `update_params()` runtime fail-closed guard，**但該 D+7 E1 IMPL 從未 land**（per `2026-06-14--cold_audit_validated_fix_plan` 治理漂移訂正）——當前唯一 enforcement = TOML config-load active=false，無 runtime IPC `active=true` 注入 guard。本 slot 屬 dormant 非 active risk_config，故不補 guard；revive 時若需 fail-closed guard 應在 ADR-0046 升 Accepted 的 V3 IMPL 內一併設計。本 ADR 記錄此 slot 作為 V3 redesign 前置基礎。
2. **Revive 硬閘**：funding_arb 任何形式重新上線，必須同時滿足三條 hard gate：
   - 新 AMD super-cedes AMD-2026-05-26-01，附 V3 design rationale；
   - **本 ADR-0046 升 Accepted**（V3 IMPL + V117 migration spec 全 land）；
   - 5-gate + Stage 0R replay preflight PASS（per AMD-2026-05-15-01）。

候選設計方向（**尚未拍板，僅記錄供未來決策**）：basis observation 與 execution 兩維分離 —— 觀測層持續累積 funding/basis 證據（不下單），執行層在獨立、可被 5-gate 約束的路徑下評估是否值得進場。此方向是否採納、V117 schema 細節、cross-venue / options 是否納入，均為本 ADR 升 Accepted 時才定案的內容。

## Consequences

- **治理 anchor 補完**：ADR-0018 §Decision、AMD-2026-05-26-01、TOML deprecation 註記、`docs/README.md` 對 ADR-0046 的引用，現有可載入檔對應，消除「revive gate 懸空於不存在 ID」的風險。
- **不授予任何交易權限**：本 ADR Proposed 狀態不放寬 Stage / 5-gate 任何約束，不等於 funding_arb 可上線。
- **D+30 PA follow-up**：per AMD-2026-05-26-01，PA 在 D+30 評估本 slot 是否仍 actively referenced，或可同步 retire（連帶觸發 `funding_arb.rs` hard-delete cascade）。若決定 retire，本 ADR 改 Status: Superseded/Rejected 並記錄理由。
- **dead-code-with-marker 風險**：slot 長期 Proposed 而不 land 會變成「帶 marker 的死碼」（R4 已標 LOW 風險）；mitigation = D+30 follow-up 強制二選一（land V3 或 retire slot）。

## Alternatives Considered

| Alternative | 棄因（記錄於 AMD-2026-05-26-01） |
|---|---|
| Hard-delete `funding_arb.rs` + 移除 registry/params/mod.rs 註冊 | SQL V031/V034/V084/V086/V090/V101 6 migration enum/case 含 `'funding_arb'` 硬編碼，historical row 仍需 query；72 unit tests 損失；Rust mod tree 拔除高風險。若採此路徑則本 ADR 無存在意義 |
| R-02 Strategist 直接重評 V2 參數 | V2 在 Bybit 結構性無法 break-even；非參數問題。重設計必須走本 ADR slot，不是 V2 closure 的延伸 |
| 立即 Accept 一個完整 V3 設計 | 證據不足；basis/execution 分維方向尚未經 QC 數學 + E4 test 驗；先 Proposed 占位，待 Sprint 1A-δ/ε 評估 |

## References

- ADR-0018 funding_arb V2 Retired: `docs/adr/0018-funding-arb-v2-deprecation-watch.md`
- AMD-2026-05-26-01 funding_arb Deprecation Closure: `docs/governance_dev/amendments/2026-05-26--AMD-2026-05-26-01-funding-arb-deprecation.md`（§5 Decision 3 — Future Redesign Slot Preservation）
- Workflow F Phase 1 cascade spec: `docs/archive/2026-07-09--execution_plan_v58_closed/specs/2026-05-26--funding-arb-deprecation-cascade.md`
- AMD-2026-05-15-01 Stage 0R replay preflight（revive gate）: `docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md`
- BB APPROVE 候選方向（basis observation vs execution 分維）: `docs/audits/2026-05-25--v1_to_v58_full_consolidation_drift.md`（§B workflow）
- v5.8 ADR roster（ADR-0046 proposed 2026-05-25）: `docs/execution_plan/2026-05-20--execution-plan-v5.8.md`

## Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| Operator | `P0-FUNDING-ARB-DECISION-FORCE` (D) 3C closure；slot 保留 directive | 2026-05-26 | ✅ Slot 保留已批；V3 設計 decision TBD |
| BB | basis observation vs execution 分維候選方向 APPROVE | 2026-05-25 | ✅ 方向 APPROVE（候選） |
| QC | V3 delta-neutral 數學 + per-strategy σ 適用性 review | TBD（Sprint 1A-δ/ε） | 🟡 PENDING |
| TW | 本 ADR 起草（revive-gate placeholder 登記） | 2026-05-31 | ✅ Drafted |
| PA | D+30 follow-up — slot 仍 active 或同步 retire 決策 | TBD（D+30） | 🟡 PENDING |
| PM | V3 IMPL dispatch + Accepted 升格仲裁 | TBD | 🟡 PENDING |

---

*OpenClaw / Arcane Equilibrium ADR-0046 — funding_arb V3 Redesign Slot（Basis Observation vs Execution Split candidate）· Proposed (decision TBD) · revive-gate placeholder per AMD-2026-05-26-01；未 Accepted 不得作為 funding_arb 上線依據*
