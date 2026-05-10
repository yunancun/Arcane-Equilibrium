# Amendment AMD-2026-05-10-03 — invariant 5 Wording 對齊 N+0 Actual IMPL（Option A）+ invariant 5b N+1 預告

**對應 spec**: TODO v19 §5.1 invariant 5 · W-AUDIT-4b ML 基座
**Supersedes**: invariant 5 v19 original wording（FA §4 spec："feature_baselines first → mlde_edge_training_rows → scorer_predictions → 3 advisor 並行"）
**Cross-references**:
- AMD-2026-05-09-02 (operator decision audit closure)
- AMD-2026-05-09-03 (graduated canary default)
- ADR-0011 (V### migration Linux PG dry-run mandatory)
- DOC-08 §12 (9 條安全不變量)
- CLAUDE.md §七 (SQL migration Guard A/B/C)

**日期**: 2026-05-10
**作者**: PA（Sprint N+0 sign-off invariant 17 派發鏈內附帶）
**狀態**: Accepted — option A per operator 2026-05-10 sign-off discussion；commit `0b9a03ef` 已 land
**索引**: `docs/README.md` Amendments index
**TODO 連結**: §5.1 invariant 5 / W-AUDIT-4b N+0 IMPL chain

---

## 1. Background

### 1.1 invariant 5 原文（FA spec）

TODO v19 §5.1 invariant 5 v19 original wording（FA `2026-05-09--todo_qctodo_merge_business_chain_advice.md` §4）：

> W-AUDIT-4b N+0 IMPL chain 已串行 land（**feature_baselines first** →
> mlde_edge_training_rows → scorer_predictions → 3 advisor 並行）

**FA 原意**：spec 規範「ML drift detection chain 入口必先有 feature_baselines
writer」，因為 mlde_edge_training_rows 是 view 而非 producer-target，
scorer_predictions 是上層消費者，3 advisor (mlde_shadow / mlde_demo /
cost_edge) 是 advisor 層。整鏈以 feature_baselines drift events 為 trigger。

### 1.2 N+0 actual IMPL chain（W-AUDIT-4b M1/M2/M3）

Sprint N+0 W-AUDIT-4b 實際 land 的 IMPL chain（per MIT review
`2026-05-10--sprint_n0_final_review.md` §2.1 + commit chain
`4a90966a` → `404174a4` → `e93a6e5c` → `a01d05ed`）：

| Step | Producer call site | Source | Target | LANDED |
|---|---|---|---|---|
| 1 (M1) | `emit_decision_feature_intent_emitted` (paper success) | step_4_5_dispatch.rs ~713 | `learning.decision_features` (intent-only) | ✅ `4a90966a` |
| 1 (M1) | `emit_decision_feature_intent_emitted` (exchange success) | step_4_5_dispatch.rs ~510 | `learning.decision_features` (intent-only) | ✅ `4a90966a` |
| 1 (M1) | `try_emit_evaluation_log` (predictor disabled fallback) | intent_processor/mod.rs | `learning.decision_features_evaluations` | ✅ V082 + writer |
| 2 (M2) | `trading_writer::flush_fills` | trading writer | `trading.fills` with `entry_context_id` | ✅ `404174a4` (V083 NOT VALID + cron backfill) |
| 3 (M3) | `emit_decision_feature_intent_rejected` × 3 paths (pre_risk + exchange + paper) | step_4_5_dispatch.rs (3 hits) | `learning.decision_features` with `label_close_tag='rejected_governance'` | ✅ `e93a6e5c` + `a01d05ed` (V084 + 6 Rust file FIX-W2) |

**MIT verdict**（同報告 §2.2）：

> Current Sprint N+0 sequence does NOT match FA invariant 5 strict ordering.
> - W-AUDIT-4b M1 → M2 → M3 (decision_features producer + fills writer +
>   reject negative label) is the actual sequence implemented
> - `feature_baselines` is NOT in Sprint N+0 scope — it's a Sprint N+1 P1
>   candidate (memory 2026-05-09 v2 final state)
> - mlde_edge_training_rows is a VIEW (not a producer-target) — populated
>   transitively through underlying tables

**MIT push-back to PM**（同報告 §2.2 結論）：

> Either (a) N+0 invariant 5 reword to match actual M1→M2→M3 sequence, or
> (b) cancel feature_baselines requirement from N+0 to N+1 explicitly.

### 1.3 Operator 2026-05-10 sign-off discussion

Operator 在 Sprint N+0 sign-off 討論中拍板 **option A — 文字改寫對齊 N+0
actual IMPL**：

理由：
1. Sprint N+0 actual IMPL 與 invariant 5 strict ordering 撞牆，不可改寫 IMPL
   去配 spec（IMPL is correct, spec is misaligned）
2. feature_baselines / mlde_edge_training_rows / scorer_predictions / 3 advisor
   屬 ML drift detection 上層 chain，與 N+0 「decision_features producer
   + entry_context_id INSERT trigger + reject negative label」屬不同層
3. invariant 5 wording 對應 N+1 IMPL 範圍（W-AUDIT-8f Hypothesis Pipeline
   IMPL 同 wave 內 land 6 表 INSERT path），故拆 invariant 5 / 5b 兩條更清晰

---

## 2. 修訂內容

### 2.1 invariant 5 wording 改寫（option A）

**修訂後 wording**（已 land commit `0b9a03ef` 2026-05-10 11:04 UTC）：

> W-AUDIT-4b N+0 IMPL chain 已串行 land（M1 decision_features producer 改
> intent-only emit + V082 拆 `decision_features_evaluations` 表 → M2 fill
> writer `entry_context_id` enforcement + V083 NOT VALID CHECK → M3 reject
> negative label + V084 `mlde_sample_weight` UDF + 6 Rust producer file
> `emit_decision_feature_intent_rejected` 5 hits）

**驗證項**：
- commit ordering 驗 (`4a90966a` → `404174a4` → `e93a6e5c` → `a01d05ed`)
- grep 5 hits（`emit_decision_feature_intent_rejected` 在
  `rust/openclaw_engine/src/`）
- pytest 真 19/19 PASS

**來源備註**：FA-2 (N+0 actual IMPL 對齊；feature_baselines /
mlde_edge_training_rows / scorer_predictions / 3 advisor 6 表 INSERT path 留
**N+1 invariant 5b**)。

### 2.2 invariant 5b N+1 預告

新建 invariant 5b 將於 W-AUDIT-8f IMPL（R-3 Hypothesis Pipeline + W-AUDIT-4
ML 6 dead schema 併入，per TODO v19 row 20）N+5 sprint 串行 IMPL 結束後加入
TODO §5.1：

**預期 wording**（待 N+5 W-AUDIT-8f IMPL land 後拍板）：

> W-AUDIT-4b N+1+ IMPL chain 已串行 land（feature_baselines writer first
> → drift_events emit → scorer_predictions producer → 3 advisor
> (mlde_shadow / mlde_demo / cost_edge) 並行 IMPL）

**驗證項**：
- 6 表（feature_baselines / drift_events / scorer_predictions /
  mlde_shadow_advisor / mlde_demo_advisor / cost_edge_advisor）row count
  從 0 翻為 active growth
- F-08 5 ML cron 24h fire 驗 (`[Xc] ml_training_cron_active` PASS)
- W-AUDIT-8f IMPL commit chain land

**Sprint 時點**：N+1 P1 candidate（per TODO v19 §11.2 P1-INSERT-PATH-1..6）→
N+5 W-AUDIT-8f IMPL 完整 land。

### 2.3 Supersedes 文字

invariant 5 v19 original wording（"feature_baselines first → mlde_edge_training_rows
→ scorer_predictions → 3 advisor 並行"）改寫為 §2.1。**不改 invariant 編號**
（仍是 invariant 5）。新建 invariant 5b 在 N+1+ 加入。

---

## 3. Sign-off Invariant 對齊（TODO v19 §5）

| TODO §5 invariant | 修訂前後 | Sprint 時點 |
|---|---|---|
| invariant 5 | 改寫對齊 N+0 actual IMPL（option A） | Sprint N+0 sign-off 必驗 |
| invariant 5b（新建）| feature_baselines first → ... → 3 advisor 並行 | Sprint N+5 W-AUDIT-8f IMPL 完整 land 後加入 |

---

## 4. §二 16 原則合規確認

| # | 原則 | 是否相容 | 說明 |
|---|---|---|---|
| 1 | 單一寫入口 | ✅ | invariant wording 改寫不影響 IntentProcessor |
| 2 | 讀寫分離 | ✅ | TODO.md 是讀寫文件，正常 governance update |
| 8 | 交易可解釋 | ✅ | invariant 5 / 5b 拆兩條更清晰，audit 更可重建 |
| 10 | 認知誠實 | ✅ | 區分 N+0 actual IMPL vs N+1+ planned scope，避免 spec drift |

---

## 5. Non-Goals

This amendment does not:

- 改任何 W-AUDIT-4b M1/M2/M3 source code / IMPL（commit `0b9a03ef` 純 TODO.md wording）
- 改 W-AUDIT-8f Hypothesis Pipeline 的 N+5 IMPL 計劃
- 改 V082/V083/V084 schema 或 Linux PG 部署狀態
- approve true live, MAG-083, or MAG-084
- 改 graduated canary stage 或 cohort 配置
- 改 Strategist 30%→50% wide adjustment skill (ADR-0022)

---

## 6. 後續動作

| # | 動作 | Owner | 時點 |
|---|---|---|---|
| 1 | TODO §5.1 invariant 5 wording amend ✅ DONE (`0b9a03ef` 2026-05-10 11:04 UTC) | PM | DONE |
| 2 | invariant 5b N+1+ wording 待 W-AUDIT-8f IMPL land 後拍板加入 TODO §5.1 | PM + FA | Sprint N+5 W-AUDIT-8f IMPL 完整 land 後 |
| 3 | docs/README.md Amendments index 加 AMD-2026-05-10-03 entry | PA + TW | Sprint N+0 W2 sign-off chain |
| 4 | Sprint N+0 sign-off report 明文記入 invariant 5 amend rationale | PM | Sprint N+0 sign-off 時 |

---

## 7. Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| MIT | `2026-05-10--sprint_n0_final_review.md` §2.2 verdict | 2026-05-10 | ✅ Push back 採納 |
| Operator | Sprint N+0 sign-off discussion 拍板 option A | 2026-05-10 | ✅ Accepted |
| PA | 本文件作者 | 2026-05-10 | ✅ Drafted |
| FA | TODO v19 §5.1 invariant 5 來源 | 2026-05-10 | ✅ N+1 5b 預告同意 |
| PM | TBD（本 amendment commit 後通知）| 2026-05-10 | 🟡 Pending sign-off post-commit |

---

*OpenClaw / Arcane Equilibrium Governance Amendment AMD-2026-05-10-03*
