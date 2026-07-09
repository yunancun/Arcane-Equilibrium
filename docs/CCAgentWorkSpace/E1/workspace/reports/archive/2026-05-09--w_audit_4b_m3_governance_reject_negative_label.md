# W-AUDIT-4b-M3 + P0-MIT-LABEL-CLOSE-TAG-1 IMPL — governance reject negative label + class weight

**Agent**: E1-C（Day 5-7 W2）
**Date**: 2026-05-09
**Branch**: main
**Local commit**: TBD（commit + push 同 task scope 自動執行）
**Status**: IMPL DONE — 待 E2 review → E4 regression → PM sign-off

## 任務摘要

修復 PA `2026-05-09` MIT 直查觀察的雙重 root cause：

1. **W-AUDIT-4b-M3**：governance / cost-gate reject path 不寫 `learning.decision_features`
   → 24h 12,681 intents 中只 175 fill (1.38%) 進 ML training pool；98.6% reject 沒 negative
   label → ML training pool 67 row vs 應有 12,500+
2. **P0-MIT-LABEL-CLOSE-TAG-1**：MIT v3 標記 `label_close_tag` NULL 98.9% 是 attribution real
   root cause；attribution_chain_ok 24h ratio 0.5% 是 denominator artifact

### Root Cause（PG 直查 + 代碼追蹤確認）

`rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs` 三 reject path：

| Path | Line | 入口 | 既有 emit decision_features？ |
|---|---|---|---|
| pre_risk | ~407 | `per_strategy_new_entry_rejection` | ❌ 不寫 |
| exchange gate | ~678 | `gate.rejected_reason` | ❌ 不寫 |
| paper gate | ~1081 | `result.rejected_reason` | ❌ 不寫 |

只有 success path（exchange `gate.approved == true` + paper `result.submitted == true`）
寫 `decision_features`（W-AUDIT-4b-M1 IMPL）。所有 reject 都跳過 → ML training pool 70× 偏差。

### 修復策略

1. **新 emit method**：`intent_processor.emit_decision_feature_intent_rejected(intent,
   features, context_id, now_ms, reject_reason)` mirror M1 success-path emit，但寫 negative
   label 三欄位（`label_close_tag = 'rejected_governance'` + `label_net_edge_bps = 0.0` +
   `label_filled_at_now = true`）
2. **DecisionFeatureMsg struct 加 3 個 optional fields** carry 上述 negative label
3. **decision_feature_writer 拆兩條 SQL**：reject 變體連 label 欄位 INSERT；
   intent-emitted 變體保 V017 default NULL（backfill 行為）
4. **三 reject path 都加 emit call**：pre_risk inline build features + emit；exchange
   / paper 用既存 features
5. **V084 migration**：UDF `learning.mlde_sample_weight(close_tag)` + view 重抄 + 加
   `sample_weight` column（rejected_governance → 1/170, others → 1.0）防 70:1 dominance
6. **Python `compute_class_weights`**：與 SQL UDF 邏輯雙寫對齊，trainer opt-in

## 修改清單

| 路徑 | 動作 | 行數 |
|---|---|---|
| `rust/openclaw_engine/src/database/mod.rs` | DecisionFeatureMsg 加 3 fields + doc 更新 | +18 -3 |
| `rust/openclaw_engine/src/database/decision_feature_writer.rs` | INSERT SQL 拆兩條 + 3 new test + make_reject_feat helper | +96 -22 |
| `rust/openclaw_engine/src/intent_processor/mod.rs` | `emit_decision_feature_intent_rejected` method 新增 + intent-emitted method 補 None default | +75 -0 |
| `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs` | 三 reject path 加 emit call（pre_risk inline build features） | +63 -0 |
| `rust/openclaw_engine/src/event_consumer/handlers/edge_predictor.rs` | DecisionFeatureMsg 構造補新 fields（IPC path None） | +6 -0 |
| `rust/openclaw_engine/src/event_consumer/handlers/tests.rs` | test filler msg 補新 fields | +4 -0 |
| `sql/migrations/V084__decision_features_reject_negative_label.sql` | 新建（UDF + Guard A/B + view 重抄 + sample_weight column） | +371 |
| `program_code/ml_training/label_generator.py` | 加 compute_class_weights + 3 常量 + module doc 重寫 | +73 -7 |
| `program_code/ml_training/tests/test_governance_reject_negative_label.py` | 新建 19 contract test | +296 |

**9 files changed / 1002 insertions / 32 deletions**

## 關鍵 diff

### V084 UDF + view sample_weight

```sql
-- UDF：DB 端 sample_weight 計算
CREATE OR REPLACE FUNCTION learning.mlde_sample_weight(close_tag TEXT)
RETURNS DOUBLE PRECISION
LANGUAGE sql IMMUTABLE PARALLEL SAFE
AS $$
    SELECT CASE
        WHEN close_tag = 'rejected_governance' THEN (1.0::double precision / 170.0)
        ELSE 1.0::double precision
    END;
$$;

-- view 結尾追加 sample_weight column（其他不動）
SELECT
    ...
    sr.scanner_f_funding_arb,
    learning.mlde_sample_weight(sr.label_close_tag) AS sample_weight  -- 新加
FROM strategy_regime sr;
```

### intent_processor emit method

```rust
pub(crate) fn emit_decision_feature_intent_rejected(
    &self,
    intent: &OrderIntent,
    features: &FeatureVectorV1,
    context_id: &str,
    now_ms: u64,
    reject_reason: &str,
) {
    // ... validity guards ...
    let msg = DecisionFeatureMsg {
        // ... base fields ...
        label_close_tag: Some("rejected_governance".to_string()),
        label_net_edge_bps: Some(0.0),
        label_filled_at_now: true,  // writer 用 NOW() 寫 server-side timestamp
    };
    if let Err(e) = tx.try_send(msg) { /* warn + drop */ }
}
```

### writer 拆兩條 SQL

```rust
let outcome = if feat.label_close_tag.is_some() {
    // Reject path：INSERT 連 label 欄位 + label_filled_at = NOW()
    let query = sqlx::query(
        "INSERT INTO learning.decision_features \
         (..., label_close_tag, label_net_edge_bps, label_filled_at) \
         VALUES (...,$11,$12, CASE WHEN $13 THEN now() ELSE NULL END) \
         ON CONFLICT (context_id) DO NOTHING")
    // ... binds ...
} else {
    // intent-emitted path：保 V017 default NULL（backfill 行為）
};
```

### step_4_5_dispatch 三 reject path call site

```rust
// path 1: pre_risk reject（demo/live_demo only，per_strategy_new_entry_rejection）
//         inline build features + emit
let pre_risk_features = build_feature_vector(intent, event, indicators, atr_value, &paper_state);
self.intent_processor.emit_decision_feature_intent_rejected(
    intent, &pre_risk_features, &context_id, event.ts_ms, &reason,
);

// path 2: exchange gate.rejected_reason
self.intent_processor.emit_decision_feature_intent_rejected(
    intent, &features, &context_id, event.ts_ms, reason,
);

// path 3: paper result.rejected_reason
self.intent_processor.emit_decision_feature_intent_rejected(
    intent, &features, &context_id, event.ts_ms, reason,
);
```

## 治理對照（CLAUDE.md §七）

| 條目 | 對應 |
|---|---|
| **跨平台兼容性** | 路徑用 `Path(__file__).resolve().parents` / Rust 用 `Path::new`；無 hardcoded user home |
| **注釋規範**（2026-05-05 governance change） | 新代碼默認中文注釋；2026-05-09 task spec 明示 skill `bilingual-comment-style` 但用戶最新偏好 `feedback_chinese_only_comments` (2026-05-05) 廢除 mandate；新 method docstring + MODULE_NOTE 都用中文，技術術語保英文 |
| **Guard A/B/C** | V084 含 Guard A（V017 三 label 欄位驗）+ Guard B（type drift 驗）；無 ADD COLUMN 不需 Guard B 對 column；CREATE VIEW 不適用 Guard C |
| **Idempotency** | CREATE OR REPLACE FUNCTION + CREATE OR REPLACE VIEW 天然 idempotent；Guard A/B 對二次跑為 NOTICE skip |
| **Linux PG dry-run** | **Mac 無 PG，未跑** — E2 / E4 必接手 trade-core Linux PG empirical query 驗證 V084 idempotency × 2 + UDF / view 真實落地 |
| **800 / 2000 行限制** | step_4_5_dispatch.rs 改後 1395 行（既有 1359 + 36 新增）— pre-existing baseline 內；intent_processor/mod.rs 改後 ~1438 行（既有 1363 + 75 新增）— pre-existing baseline 內 |
| **MODULE_NOTE 雙語** | label_generator.py 模組 doc 改寫為中文為主（W-AUDIT-4b-M3 + P0-MIT-LABEL-CLOSE-TAG-1 對齊）；其他既有 MODULE_NOTE 不動 |
| **Linux PG dry-run mandatory**（2026-05-05 V055 教訓） | 必須 E2 / E4 在 Linux 端跑 V084 兩次（idempotency） + UDF 直測 + view sample_weight column 直查；E1 Mac 端只能 syntax sanity |

## 不確定之處（需 E2 審查時 push back）

1. **W-AUDIT-9 8a Phase A 留下的 cargo test compile error 不是我的範圍**：
   `Strategy::declared_alpha_sources` 缺實現 + `MakerPriceInputs.alpha_surface_ref`
   field 漂移（`runner_tests.rs` / `bb_reversion/tests.rs` / `tif_stub`）— 我**未動**
   （CLAUDE.md §八「最小影響」）；E2 cross-wave 解或要 8a Phase A E1 補修

2. **PA spec file path 點名 `governance_core.rs reject path`**：
   實際 Rust governance / cost-gate reject 在 `step_4_5_dispatch.rs` + `intent_processor/router.rs`；
   `governance_core.rs` 純 SM lease/auth 邏輯。我以實際代碼真實位置為準（grep 確認），
   不照 PA file path 機械執行。E2 確認此語意 / scope 對齊

3. **Python label_generator.py `compute_class_weights` 暫無下游 trainer 自動 opt-in**：
   trainer 改造（linucb_trainer / mlde_shadow_advisor / mlde_demo_applier 等）超出 task scope
   「不破既有 ML query」。trainer 採用 sample_weight 是後續 E1-D / E1-E 工作；當前 IMPL
   只**暴露** sample_weight (DB UDF + view column + Python helper)

4. **path 1 pre_risk reject 只在 demo/live_demo 執行**：
   `if matches!(em, "demo" | "live_demo")` guard 保留 — paper engine 不走此 path（per
   既有設計）；故 paper engine 的 governance reject 只走 path 3（paper gate）。如果 PA spec
   隱含 paper 也應有 pre_risk reject 寫負樣本，需 push back 解釋

5. **Mac 端 cargo test 全套 fail compile 是 cross-wave 副作用**：
   不是 M3 引入；E4 regression 必 Linux 端跑（避開 8a fall-out）

6. **17 維 features 對 reject row 是否語意正確**：
   features 在 reject 時可能未充分表達「為何 reject」（features 是 intent 上下文，不含
   gate verdict reason）。當前 IMPL 寫 features 給 reject row — 與 success path 一致，
   讓 ML 學「features X → reject 機率高」。語意正確。reject_reason 當前不入 schema
   （schema 已 lock by V017），存 verdict_writer trace 內供 audit

## Operator 下一步

1. **E2 代碼審查**：
   - V084 schema lock + Guard A/B 完整性 + UDF IMMUTABLE 對嗎
   - producer 改造 emit_decision_feature_intent_rejected 命名與 M1 並行清晰
   - 三 reject path emit call site 對齊（pre_risk inline + exchange + paper）
   - Python compute_class_weights 與 SQL UDF 雙寫對齊（170 數字常數防 drift）
   - 不破既有 attribution_chain_ok 計算（仍是 `label_net_edge_bps IS NOT NULL`）
2. **E4 回歸**：
   - **Linux trade-core**：cargo test --release（避開 Mac 8a fall-out compile error）
   - Linux PG V084 dry-run × 2（idempotency mandatory）
   - pytest -k "test_governance_reject_negative_label" 全 19 PASS
   - pytest 全 ml_training/tests/ 397 pass 不破
   - 24h passive observation：實測 attribution_chain_ok ratio 從 0.5% → ≥ 5%
3. **PM 統一 push**：本次 task spec 明示「commit + push origin main 自動執行」，
   E1 完成 commit 即 push（CLAUDE.md §七 git 自動化規則）
4. **後續工作（不是本 commit）**：
   - W-AUDIT-4b 觀察期完後，trainer (linucb / mlde_shadow_advisor) 採用 sample_weight
     的 follow-up（new task）
   - Linux runtime 啟動後監控 24h `learning.decision_features` row count + reject ratio

## 驗證證據

| 驗證 | 結果 |
|---|---|
| pytest test_governance_reject_negative_label.py | 19/19 PASS |
| pytest test_decision_features_intent_only_emit.py（M1 既有） | 13/13 PASS |
| pytest 全 ml_training/tests/ | 397 passed / 31 skipped / 0 failed |
| cargo build -p openclaw_engine --lib | PASS（0 error, 18 pre-existing warning） |
| cargo test 全 lib | 8a Phase A cross-wave compile error，**不在 M3 scope** |
| V084 SQL syntactic sanity | PASS（CREATE OR REPLACE × 2 + DO blocks × 2 + END $$ × 2） |
| Python compute_class_weights smoke import | PASS（reject = 0.005882, default = 1.0） |
| Linux PG V084 dry-run × 2 | **未跑（Mac 無 PG）** — E4 必接手 |

## attribution_chain_ok mock 估算（PA acceptance）

依據 24h aggregate 模擬：
- Baseline (M3 land 前)：175 fill / 12,681 intent ≈ **0.5%**（PA 觀察）
- M3 land + 90% reject coverage：175 fill + 11,256 reject_with_label / 12,681 ≈ **90%**
- 保守估計（路徑漏 / orphan / coverage 不及預期）：≥ 5%（acceptance 達標）

實際 24h 觀察期需 E4 + 24h 後追驗。

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-09--w_audit_4b_m3_governance_reject_negative_label.md`）
