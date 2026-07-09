# ADR 0045: M4 Hypothesis Discovery Governance — Reserved Placeholder

Date: 2026-05-21
Status: **Reserved** (per R4 C-1 audit 2026-05-21 — M4 spec ADR-0042 → ADR-0045 reassignment due to ADR-0042 編號衝突 with M3 health monitoring；本 ADR 為 placeholder 待 Sprint 6+ M4 IMPL 階段 PM dispatch TW 補完整 Decision/Consequences/Sign-off)
Operator Sign-off: PENDING (Sprint 1A-ε 後續 / Sprint 6+ M4 IMPL 啟動前)
Related:
- `docs/archive/2026-07-09--execution_plan_v58_closed/2026-05-21--m4_hypothesis_discovery_design_spec.md` (877 行 PA design spec；§10 V103 EXTEND outline + §9 Cowork hybrid path)
- `docs/archive/2026-07-09--execution_plan_v58_closed/2026-05-21--m4_minimum_bar_and_leakage_protocol.md` (839 行 Wave 2 land；6 attribute minimum bar + leakage protocol baseline)
- `docs/archive/2026-07-09--execution_plan_v58_closed/2026-05-21--v103_extend_m4_hypothesis_columns_schema_spec.md` (pending MIT Sprint 1A-ε land；V103 EXTEND 6 column full DDL)
- ADR-0024 Cowork subscription operator-assistant
- ADR-0034 LAL (M1 LAL Tier 1-2 audit for M4 DRAFT writeback Decision Lease)
- ADR-0037 M9 A/B framework (M4 hypothesis 走 M9 cluster 4 exit logic variant test)
- AMD-2026-05-21-01 autonomy-vs-human-final-review (M4 DRAFT writeback opt-in scope)
- memory `feedback_indicator_lookahead_bias` (leakage 防護 mandatory)
- memory `project_ml_dl_learning_architecture` (LightGBM + Optuna + 3DL baseline)

## Context

### 起源 — R4 C-1 ADR-0042 編號衝突修正

R4 audit 2026-05-21 (a affd343f) catch ADR-0042 編號衝突：
- M3 health monitoring ADR (G.6 carry-over) 已 land 為 ADR-0042（commit `f75117ec`）
- M4 hypothesis discovery 兩 spec doc 預定 ADR-0042 為 M4 governance authority（5+7 occurrences）
- ADR-0043/0044 已引用 ADR-0042 = M3

**R4 推薦 (a)**：ADR-0042 保留 M3；M4 改用 **ADR-0045 reserved**。Operator 採納（Sprint 1A-ε commit `11e94d39` apply C-1 patch 12 occurrences）。

### 為什麼是 placeholder 不寫完整 ADR

- M4 module IMPL phase 從 **Sprint 6+ M4 Pattern Miner active**（per v5.8 §4 Sprint 6 timeline）
- M4 spec doc 已 land 877 行 + leakage protocol 839 行；governance 邊界已在 spec 內 establish
- ADR 完整 Decision/Consequences 撰寫 cost (~5-7 hr TW) 在 Sprint 1A-ε 階段不必要；Sprint 6+ M4 IMPL 啟動前 1-2 wk 再補
- Reserved placeholder = ADR list 編號連續性 + reverse-ref 不 dangling + M4 spec ref ADR-0045 不撞 ghost link

### Sprint 1A-ζ IMPL spike 不阻

- Sprint 1A-ζ spike Track A/B/C 不含 M4（M4 IMPL Sprint 6+）
- 本 ADR placeholder land 後 Sprint 1A-ζ 可 dispatch
- M4 Sprint 6+ IMPL 啟動前必先補完本 ADR (Status: Proposed → Operator Sign-off)

## Decision

**Reserved** — 完整 Decision 待 Sprint 6+ TW 補充。下列為 M4 spec + leakage protocol 已 established 的 governance baseline (本 ADR 完成後 promote 為 Decision)：

1. **M4 single hypothesis discovery authority** — M4 為 self-supervised hypothesis discovery 唯一 module；M9 A/B framework 不 generate hypothesis，只 test variant
2. **Minimum bar 6 attribute mandatory** per M4 leakage protocol baseline（sample N / shift(1) leak-free / OOS validation / decay window / Bonferroni 校正 / replicability）
3. **DRAFT writeback Decision Lease** — M4 hypothesis 不 auto-promote 到 Stage 0R；走 LAL Tier 1-2 audit + Cowork Y1 read-only review
4. **M4 ↔ M9 integration** — discovered hypothesis 走 M9 cluster 4 (exit logic variant) test；M4 不直接 IMPL strategy
5. **M4 ↔ M6 reward integration** — M4 DRAFT reward weight 從 M6 5 λ baseline；不獨立 reward model
6. **M4 ↔ M11 dedup** — M11 replay divergence 不算 M4 hypothesis source（避循環 generate）
7. **Cowork hybrid path** — Y1 read-only review only；Y2 LAL Tier 2 auto-suggest（per ADR-0024）；不 auto-promote
8. **V103 EXTEND 6 column** — hypothesis_source_module / leakage_scan_pass / bonferroni_corrected_p / replicability_score / decision_lease_draft_id / cowork_review_status (per V103 EXTEND spec)

### Wave 5 v2 Autonomy Level sync（2026-05-28）

M4 remains DRAFT-only under both Level 1 and Level 2. Autonomy Level Standard may allow eligible DRAFT writeback / review routing to proceed through fail-safe automation when the owning M4/M9/M6 gates pass, but it **does not** promote a hypothesis to Stage 0R, create live trading authority, bypass the six-attribute leakage minimum bar, or bypass Decision Lease audit. Any M3 health degradation, M7 freeze state, Guardian alert, 5-gate kill, M8 anomaly trigger, or regime-change freeze returns M4 actions to manual/frozen posture.

## Consequences

**Reserved** — 完整 Consequences 待 Sprint 6+ TW 補充。預期方向：

- 正面：M4 governance 集中 ADR-0045；Sprint 6+ M4 Pattern Miner IMPL 有明確 ADR 級邊界；DRAFT writeback Decision Lease 防 M4 fake-promote
- 負面：M4 spec 引 ADR-0045 reserved 而非 active ADR；M4 Sprint 6+ IMPL 前必先補完本 ADR；不補等於違反治理紀律

## Retirement Criteria

per M4 spec §12 Open Q + leakage protocol baseline：

- 條件 1：Y3 末 M4 Pattern Miner 0 production hypothesis discovered → 觸發本 ADR Superseded + M4 module sunset PR
- 條件 2：M4 被 M9 framework 收編（M9 A/B framework expansion 含 hypothesis generation） → ADR Superseded
- 條件 3：Sprint 8 M4 Stage 2 evidence 顯 M4 hypothesis FALSE POSITIVE rate > 80% → 重議 minimum bar 6 attribute + leakage protocol；可能觸發 ADR amendment

## Sign-off

| Role | Status | Date | Note |
|---|---|---|---|
| PA | DRAFT Outline ONLY | 2026-05-21 | per R4 C-1 ADR-0042 編號衝突修正；M4 governance authority 預留 ADR-0045 |
| PM | Reserved Placeholder | 2026-05-21 | Sprint 1A-ε land；Sprint 6+ M4 IMPL 啟動前必補完整 Decision/Consequences/Sign-off |
| TW | PENDING | — | Sprint 6+ M4 IMPL 1-2 wk 前 dispatch 補完整 ADR |
| MIT | PENDING | — | V103 EXTEND full DDL 對齊本 ADR Decision 8 |
| QC | PENDING | — | 6 attribute minimum bar + leakage protocol 數學 review |
| CC | PENDING | — | 16 root principles + 9 safety invariants compliance for M4 IMPL |

---

**END ADR-0045 — M4 Hypothesis Discovery Governance Reserved Placeholder**

**Note**：本 ADR 為 placeholder；不 carry-over PA dispatch consolidation §Sprint 1A-γ deliverable list（M4 ADR 在 R4 建議補 list 是 ADR-0042，後 C-1 修正為 ADR-0045）；Sprint 6+ M4 IMPL 啟動前必 dispatch TW 補完整版本。
