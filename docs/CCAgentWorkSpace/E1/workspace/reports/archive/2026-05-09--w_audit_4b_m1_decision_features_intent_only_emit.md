# W-AUDIT-4b-M1 IMPL — decision_features intent-only emit + V082 evaluations 拆表

**Agent**: E1-E
**Date**: 2026-05-09
**Branch**: main
**Local commit**: `4a90966a`（**未 push origin**，per PA 指示）
**Status**: IMPL DONE — 待 E2 review → E4 regression → PM 統一 push

## 任務摘要

修復 PA 報告 root cause：`learning.decision_features` 24h 31,183 行中 **99.32%** 是 orphan candidate evaluation（無對應 `trading.intents` emit）。

### Root Cause（PG 直查 + 代碼追蹤確認）

`rust/openclaw_engine/src/intent_processor/mod.rs::evaluate_predictor_gate` 在 cost_gate / Reject 之前頂端就 emit `DecisionFeatureMsg`，無論 intent 是否真實 emit。`PredictorAction::Reject / RejectAdd / Fallback / use_legacy_no_predictor` 等 outcome 都已寫過 row 卻不會走到 step_4_5_dispatch 的 `persist_intent` → 99.32% orphan rows。

mlde_edge_training_rows view 用 `LEFT JOIN intents → decision_features ON context_id` — orphan 不會誤入 ML training pool（pool 不污染），但寫入路徑 IPC channel + 表空間都浪費，且 `attribution_chain_ok` ratio denominator 被 31x 放大致 0.5%。

### 修復策略

1. **拆表**：新建 `learning.decision_features_evaluations`（candidate evaluation log，BIGSERIAL PK），保 evaluation 流量為 producer-debug / gate 行為觀測，**禁作 ML training data**。
2. **producer 改造**：`evaluate_predictor_gate` 改寫 evaluation log 通道；`learning.decision_features` 改由 caller (step_4_5_dispatch) 在 success path 呼叫 `emit_decision_feature_intent_emitted` 才寫。
3. **denominator 縮 99%** → `attribution_chain_ok` 0.5% → 25-40%（PA spec 預期）。

## 修改清單

| 路徑 | 動作 | 行數 |
|---|---|---|
| `sql/migrations/V082__decision_features_evaluations_split.sql` | 新建 | +346 |
| `rust/openclaw_engine/src/database/decision_feature_evaluation_writer.rs` | 新建 | +287 |
| `rust/openclaw_engine/src/database/mod.rs` | 加 module + DecisionFeatureEvaluationMsg struct | +44 |
| `rust/openclaw_engine/src/intent_processor/mod.rs` | evaluate_predictor_gate 改寫 + 新 method | +144 -27 |
| `rust/openclaw_engine/src/intent_processor/tests_predictor_router.rs` | 4 既有 test 改名 + 5 new | +180 -90 |
| `rust/openclaw_engine/src/main.rs` | spawn 接線 | +5 |
| `rust/openclaw_engine/src/main_pipelines.rs` | WriterSenders + LiveSpawnBundle 加 field + 三 pipeline fan-out | +12 |
| `rust/openclaw_engine/src/tasks.rs` | spawn_db_writers 加新 channel + writer task | +27 |
| `rust/openclaw_engine/src/event_consumer/bootstrap.rs` | destructure + wire | +14 |
| `rust/openclaw_engine/src/event_consumer/types.rs` | EventConsumerDeps 加 field | +12 |
| `rust/openclaw_engine/src/tick_pipeline/mod.rs` | TickPipeline 加 field + doc | +13 |
| `rust/openclaw_engine/src/tick_pipeline/pipeline_ctor.rs` | ctor + setter + getter | +30 |
| `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs` | 兩 success path 加 emit_decision_feature_intent_emitted call | +28 |
| `program_code/ml_training/tests/test_decision_features_intent_only_emit.py` | 新建（13 contract test） | +260 |

**14 files changed / 1480 insertions / 85 deletions**

## 關鍵 diff

### V082 migration 核心

```sql
CREATE TABLE IF NOT EXISTS learning.decision_features_evaluations (
    evaluation_id           BIGSERIAL    PRIMARY KEY,
    context_id              TEXT         NOT NULL,
    ts                      TIMESTAMPTZ  NOT NULL,
    -- ... 標準 V017 對齊欄位 ...
    evaluation_outcome      TEXT         NOT NULL,  -- enum CHECK 7 values
    evidence_source_tier    TEXT         NOT NULL,  -- enum CHECK 2 values
    entry_context_id        TEXT,                   -- W-AUDIT-4b-M2 trigger 鋪路
    created_at              TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- evaluation_outcome enum：對齊 PredictorAction
CHECK (evaluation_outcome IN (
    'accept', 'reject', 'reject_add', 'shadow_fill',
    'fallback_use_legacy', 'fallback_fail_closed', 'use_legacy_no_predictor'
));

-- evidence_source_tier enum：故意與 V050 replay tier 不重疊
CHECK (evidence_source_tier IN ('evaluation_log', 'shadow_synthetic'));
```

### Producer 改造核心

```rust
// 舊：頂端 emit decision_feature（每次 gate eval）
if !context_id.is_empty() {
    if let Some(feats) = features {
        self.emit_decision_feature_snapshot(intent, feats, context_id, now_ms);
    }
}

// 新：頂端短路 + emit evaluation log（V082 enum）
let no_predictor = !cfg.use_edge_predictor || self.edge_predictor_store.is_none() || features.is_none();
if no_predictor {
    self.try_emit_evaluation_log(intent, features, context_id, now_ms,
        "use_legacy_no_predictor", "evaluation_log");
    return PredictorAction::UseLegacyGate;
}
// ... gate eval ...
let (outcome_str, evidence_tier) = match &outcome {
    PredictorGateOutcome::Accept => ("accept", "evaluation_log"),
    PredictorGateOutcome::Reject(_) => ("reject", "evaluation_log"),
    PredictorGateOutcome::RejectAdd(_) => ("reject_add", "evaluation_log"),
    PredictorGateOutcome::ShadowFill(_) => ("shadow_fill", "shadow_synthetic"),
    PredictorGateOutcome::Fallback(_) => match cfg.fallback_on_error {
        EdgePredictorFallback::Shrinkage => ("fallback_use_legacy", "evaluation_log"),
        EdgePredictorFallback::FailClosed => ("fallback_fail_closed", "evaluation_log"),
    },
};
self.try_emit_evaluation_log(intent, features, context_id, now_ms, outcome_str, evidence_tier);
```

### Caller 改造（step_4_5_dispatch）

```rust
// Paper success path (~line 713 result.submitted)
persist_intent(/* ... */);

// W-AUDIT-4b-M1：intent-only emit 到 production learning.decision_features
self.intent_processor.emit_decision_feature_intent_emitted(
    intent, &features, &context_id, event.ts_ms,
);

// Exchange success path (~line 510 gate.approved) 同樣 pattern
```

## 治理對照（CLAUDE.md §七）

| 條目 | 對應 |
|---|---|
| **跨平台兼容性** | 路徑用 `Path(__file__).parents` / 環境變數，無 hardcoded user home |
| **注釋規範** | 新代碼默認中文（2026-05-05 governance change），原有英文註釋未動 |
| **Guard A/B/C** | V082 含 Guard A2（learning.decision_features 必要欄位）+ Guard A3（drift 檢查）+ Guard C（hot-path index 欄位驗證） |
| **Idempotency** | Linux PG dry-run x2 PASS（NOTICE-only，0 RAISE），confirmed |
| **Linux PG dry-run** | trade-core (Linux runtime) 直接執行驗證 — 不靠 Mac mock pytest |
| **800 / 2000 行限制** | decision_feature_evaluation_writer.rs 287 行；intent_processor/mod.rs 改後 ~1300 行（既有 baseline 內，無新增超限） |
| **MODULE_NOTE 雙語** | decision_feature_evaluation_writer.rs 新檔頂部含 MODULE_NOTE（中文為主，2026-05-05 規範） |

## 不確定之處（需 E2 審查時 push back）

1. **process_with_features 的舊 test 行為改變**：
   `test_decision_feature_snapshot_emitted_when_predictor_disabled` 在新行為下 production 通道**不應**收到 message（IntentProcessor.process_with_features 直接呼叫 → success path 由 step_4_5_dispatch caller 處理）。我已改成新 test `test_intent_emitted_emit_writes_decision_features` + evaluation 通道收到驗證。如 E2 認為「舊 test 應保持期望 production 通道收到」，則需 caller-level integration test 補。

2. **shadow_mode=true 時的 outcome 字串**：當前選 `outcome_str` 對應 outcome enum（如 Accept → "accept"）。但 `cfg.shadow_mode=true` 時最終 PredictorAction 是 UseLegacyGate（observation only）— 寫入 evaluation_outcome 仍 = "accept" 但 evidence_source_tier = "evaluation_log"。這語意與 PA spec「shadow_mode 觀測」是否對齊需 E2 確認；可能該加新 outcome `shadow_mode_observation`。

3. **23 lift 既有 unsetable test (`stress_integration.rs E0063`)**：cargo check 顯示既有 `tests/stress_integration.rs` 缺 `indicators_5m` field — 不是我的範圍但可能 E1-A T2 schema 升級後新加的 field 連帶影響。E2 review 時可要求其他 wave 修。

4. **dry-run 副作用**：Linux PG 已被 dry-run 留下 `learning.decision_features_evaluations` 表（drop 過 + 重建 + 第二次 idempotent NOTICE skip）。當前留 schema empty 無 row。**正式 land 時 sqlx migrate 看到表已存 → CHECK 對齊 → NOTICE skip → idempotent 成功**。E2 review 時若想要 fresh state 可要求 cleanup。

5. **W-AUDIT-9 T1 fall-out 衝突**：commit `094f9914` E1-A 改了 risk_config 但 ipc_server tests 沒同步 → 2 baseline test fail。我**未修**（不在範圍）；E2 cross-wave 解。

## Operator 下一步

1. **E2 代碼審查**：
   - V082 schema lock + Guard A2/A3/C 完整性
   - producer 改造 process_with_features 內部行為改變的合理性
   - 新 method 命名清晰（emit_decision_feature_intent_emitted vs try_emit_evaluation_log）
   - tests_predictor_router 的 4 重命名 test 是否充分覆蓋舊行為
2. **E4 回歸**：
   - Mac cargo test --release 全套
   - pytest -k "test_decision_features_intent_only_emit" PA 指定 key
   - Linux runtime 啟動後監控 24h `learning.decision_features` row count drop 趨勢
3. **PM 統一 push**：等 E2 + E4 通過後 push 至 origin（commit `4a90966a`）
4. **後續工作（不是本 commit）**：
   - W-AUDIT-4b-M2：trigger 從 trading.fills 反向 update `decision_features_evaluations.entry_context_id`
   - W-AUDIT-4b-M3：attribution_chain rewire base on hypothesis_id
   - 24h passive observation：實測 attribution_chain_ok ratio 跳升

## 驗證證據

| 驗證 | 結果 |
|---|---|
| Mac cargo check + build --release | PASS |
| cargo test -p openclaw_engine --lib | 2622 passed / 2 failed (無關 — E1-A T1 fall-out) |
| decision_feature_evaluation_writer 9 tests | 9/9 PASS |
| predictor_wiring 24 tests (含 5 new + 4 改名) | 24/24 PASS |
| Python pytest test_decision_features_intent_only_emit.py 13 tests | 13/13 PASS |
| pytest program_code/ml_training/tests/ 全 | 378 passed / 0 fail |
| Linux PG V082 dry-run #1 | PASS（NOTICE-only, 5 indexes + 3 CHECK + 4 COMMENT） |
| Linux PG V082 dry-run #2（idempotency） | PASS（all NOTICE skip, 0 RAISE） |
| Linux PG schema verify | 15 columns / 5 indexes / 3 CHECK constraints 對齊預期 |
| ML training view query (mlde_edge_training_rows 24h) | 22,405 rows — view 不破 |

---

E1 IMPLEMENTATION DONE: 待 E2 審查（report path: `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-09--w_audit_4b_m1_decision_features_intent_only_emit.md`）
