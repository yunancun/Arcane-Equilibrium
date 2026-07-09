# R4 Cross-Ref Audit — Workflow F funding_arb Deprecation Cascade

**Auditor**: R4 (Document Auditor — read-only)
**Date**: 2026-05-26
**Phase**: Workflow F Phase 2 R4 cross-ref audit (per PA spec §4)
**Baseline**: HEAD `6a20b9ea`；PA Phase 1 spec landed at `srv/docs/execution_plan/specs/2026-05-26--funding-arb-deprecation-cascade.md` (551 行)；TW Phase 2 in-flight at audit time
**Verdict**: **Pass A APPROVE-WITH-DRIFT** / **Pass B PENDING-NEEDS-TW-DISPATCH**

---

## A. Pass A — Baseline Cross-Ref Snapshot（pre-TW）

採集時間 2026-05-27 07:00+ UTC。基準 = 當前 worktree（PA spec land + TW cascade 未開工）。

### A.1 Ref count by source（pattern: `funding_arb` | `FundingArb`）

| Source | Files | 註 |
|---|---:|---|
| `docs/` *.md 全集 | 300+（head-limited） | 含 archive + CCAgentWorkSpace |
| `docs/` *.md 排除 archive / CCAgentWorkSpace | ~38 file | TW cascade scope 真正集合 |
| `rust/openclaw_engine/src/` | **60 files** | ⚠ PA spec §4.1 列 5-8 file — 嚴重 underspecified（drift #1）|
| `sql/migrations/` | **7 files** V031/V033/V034/V084/V086/V090/V101 | ⚠ PA §4.1 列 6 — V033 漏列（drift #2）|
| `settings/` | **4 files**（3 strategy_params + risk_config_demo）| ✅ match PA |
| `helper_scripts/` | **16 files** | ⚠ PA §4.1 列 3 — 含 cron / passive_wait / canary（drift #3）|
| `docs/audits/` | 12 files | 保留歷史 lineage per PA §4.3 ✅ 不更新 |
| `docs/archive/` | 31 files | 保留 per PA §4.3 ✅ 不更新 |
| `docs/CCAgentWorkSpace/` | 100+ files / 520 hits | agent 歷史 per PA §4.3 ✅ 不更新 |
| `docs/governance_dev/` | 10 files | 新 AMD-26-01 將是第 11 |

### A.2 Deprecation lineage anchor count

| Anchor | Count | State |
|---|---:|---|
| `AMD-2026-05-26-01` | **1 hit only**（PA spec 本身）| TW cascade **完全未開工** |
| `ADR-0018` + `AMD-2026-05-09-02` | 80+ files | 既有 lineage |

---

## B. Pass B — Verification Verdict

**Status**: **PENDING-NEEDS-TW-DISPATCH**（TW Phase 2 未啟動或未完工）

**判據**：
1. AMD-2026-05-26-01 file 不存在 `docs/governance_dev/amendments/` 下
2. PA spec §5 列 5 個 cascade target 親查均仍 pre-cascade baseline：
   - `docs/README.md:782` ADR-0018 entry 仍標 "W-AUDIT-6 cleanup pending"（未升 retired）
   - `docs/governance_dev/SPECIFICATION_REGISTER.md` ADR-0018 在 line 18/19 仍 lineage AMD-09-02/-03 為止
   - `docs/adr/0018-funding-arb-v2-deprecation-watch.md` §Decision 仍 "retire from active strategy set"
   - `docs/KNOWN_ISSUES.md:480` 仍 "5 textbook strategies ... funding_arb"
   - `docs/execution_plan/2026-05-20--execution-plan-v5.8.md` 3 hits 仍未改 4 textbook

**Pass B 派工觸發條件**：grep `AMD-2026-05-26-01` 在 ≥4 of 5 cascade target file 命中 + AMD file 存在 `docs/governance_dev/amendments/` 下。

---

## C. Drift Detection — PA spec §4.1 underspecified

| # | Source | 漏 / 錯 / 過期 | R4 建議 |
|---|---|---|---|
| 1 | `rust/openclaw_engine/src/` 60 files 含 funding_arb | PA §4.1 列「5-8 file」嚴重 underspecified；含 main.rs / fast_track.rs / scanner/* (8) / linucb/* / edge_predictor/* / ml/registry.rs / replay/* / decision_context_producer.rs / database/decision_feature_writer.rs / event_consumer/tests/funding_settlement_tests.rs 等 | 多數是 strategy enum string-match 不需動；E1 D+7 IMPL 需先 grep 全表確認 `#[deprecated]` marker 不致觸發 60 file warning storm；建議 PA spec amendment 補列 |
| 2 | `sql/migrations/V033__fills_exit_reason.sql` | PA §4.1 列 6 file，實際 **7 file** include V033 | TW 補 SQL header comment 必擴成 7 file；否則漏 V033 |
| 3 | `helper_scripts/` 16 file 含 cron / passive_wait / canary | PA §4.1 列 3 file，實際 16 file；含 `ml_training_maintenance_cron.sh` / `ml_training_maintenance.py` 屬 MIT D+7 retire scope（per PA §6.2 D+7 表）| MIT D+7 dispatch 對齊；多數 enum allowlist 不需動 |
| 4 | `docs/execution_plan/2026-05-25--ea3_funding_arb_sl_gate_p1_hotfix_spec.md` (33 hits) | PA §4.2 cross-ref graph **未列**；本 spec 是 PA overturn 為 P3 doc-only 的 EA-3 hotfix | TW cascade 加入 §5 次優先清單 + status 升 superseded |
| 5 | `docs/execution_plan/2026-05-09--w_audit_8b_strategist_alpha_orchestrator_spec.md` + `2026-05-15--w_audit_8b_funding_skew_directional_spec.md` | PA §4.2 未列 W-AUDIT-8B 系列 funding 相關 spec | 評估是否需 AMD-26-01 cross-ref（funding-skew 與 funding-arb 不同概念但同領域）|
| 6 | `docs/governance_dev/SPECIFICATION_REGISTER.md` Amendments table | TW 後須在 line 24+ 加 AMD-2026-05-26-01 row | per PA §5 priority 2 ✅ 已在計劃內 |

---

## D. TODO.md 漂移檢測

| 項 | 觀察 |
|---|---|
| TODO.md line 90 / 160 | `P1-FUNDING-ARB-DEPRECATION-CASCADE` row + Workflow F NEW row 已 land ✅ |
| TODO.md line 263 ADR-0046 (Proposed) | 與 PA spec §3.2 "Slot reserved for ADR-0046" 一致 ✅ |
| TODO.md line 378 LG-3 REFRAMED | 與 PA spec §0 decision lineage 一致 ✅ |
| TODO.md line 169 `P1-EDGE-2` (funding_arb) | 仍標 PA D3 升 P0；應在 cascade 後降為 archive | TW §5 priority cascade 待處理 |

---

## E. Verdict

- **Pass A**：**APPROVE-WITH-DRIFT** — baseline 完整；6 項 drift detection 對 PA spec §4.1 underspecification 提出 amendment 建議；不影響 PA spec 整體合規。
- **Pass B**：**PENDING-NEEDS-TW-DISPATCH** — TW Phase 2 未完工；TW 完成後再開 Pass B verification grep + 0 dangling verify + AMD-26-01 graph 完整性驗證。

---

## F. Recommendation 給主會話

1. **PA spec §4.1 underspecified 嚴重**（Rust 60 vs 5-8 / SQL 7 vs 6 / helper 16 vs 3）；建議：
   - (a) 在 TW round 1 完成後派 R4 Pass B，識別實際 cascade gap
   - (b) 若 TW round 1 漏改較多（>5 file），派 PA amendment + TW round 2
   - (c) Rust 60 file 多為 enum string-match，PA §1.3 已說明不需逐 file 改；D+7 E1 IMPL 階段才需 `#[deprecated]` warning suppression 評估
2. **EA-3 hotfix spec**（33 hits）漏在 PA §4.2 cross-ref graph，建議 TW round 2 補 cascade（status 升 superseded）。
3. **R4 Pass B trigger** = grep `AMD-2026-05-26-01` ≥4 of 5 cascade target hit + AMD file land in `docs/governance_dev/amendments/`。

---

**R4 DOC AUDIT DONE**: Pass A APPROVE-WITH-DRIFT / Pass B PENDING；6 drift items 待 PA amendment + TW round 2 評估。
