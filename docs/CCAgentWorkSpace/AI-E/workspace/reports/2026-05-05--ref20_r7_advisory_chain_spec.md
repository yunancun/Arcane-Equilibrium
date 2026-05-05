# AI-E ADVISORY — REF-20 R7 MLDE/Dream Advisory Chain Spec

**Date**: 2026-05-05 · **Author**: AI-E (AI Effectiveness Evaluator) · **HEAD**: `95beba74` Mac/Linux/origin synced
**Scope**: Read-only pre-DAG advisory · 0 code · 0 commit · 0 push · 1h time cap respected
**Sprint context**: Sprint C C1 in flight (R6-T0' V055 deployed `9e1872b5` + R6 W1+W2 land `286252d2`+`95beba74`). C1 closed 後啟 C2 R7 dispatch。**本 advisory 為 C2 R7-T0 deliverable**（per PA §13.5 路線圖 / §7.2 邊界）。
**Persistence**: PM persisted from AI-E final assistant message (AI-E role read-only, no Write tool).

---

## §1 真實 R7 producer call graph 確認

PA §2B 列 4 producer，PM grep 揭實 4 producer 全已 wired `verify_replay_evidence_and_insert`。AI-E 二次驗證 grep 結果（4 file × `verify_replay_evidence_and_insert` count）：

| Producer | 檔案 + 主寫入 function | 真實位點 | Trigger | 既有 evidence_source_tier | R7 升級對象 | R6 label 整合需求 |
|---|---|---|---|---|---|---|
| **dream_engine** | `program_code/local_model_tools/dream_engine.py::persist_dream_insights` | `dream_engine.py:413-488` (寫入 SQL `:447-487`) | `edge_estimator_scheduler.py:587-591` import + cycle interval 3600s = 每小時 1 次 | hardcoded `'real_outcome'` (line 462) + `replay_experiment_id NULL` (463) + `manifest_hash NULL` (464) + `expires_at NULL` (465) | **YES — primary R7-T1** | 從 R6 deliver `CalibrationResult.label` map 到 `evidence_source_tier='calibrated_replay'` + `expires_at = now() + label_to_ttl(label)` |
| **dream_engine** secondary | `program_code/local_model_tools/dream_engine.py::generate_replay_candidates` | `dream_engine.py:774-953` (line 786-790 文檔明寫 "function does NOT write...caller is responsible for routing accepted candidates through verify_replay_evidence_and_insert()") | replay_routes.py POST /api/v1/replay/run（caller side） | **N/A — pure compute** (0 DB write, 0 verify_replay caller in this function) | **NO direct change**（R7-T2 是 verify-only on caller side `replay_routes.py`） | caller 端負責 |
| **opportunity_tracker** | `program_code/local_model_tools/opportunity_tracker.py::persist_regret_summary` | `opportunity_tracker.py:200-282` (寫入 SQL `:247-278`) | `edge_estimator_scheduler.py:594-596` import + cycle interval 3600s = 每小時 1 次（per MIT §2.1 verified） | hardcoded `'real_outcome'` (line 260) + `NULL,NULL,NULL` replay metadata (261) | **YES — primary R7-T3** | 同 dream_engine pattern |
| **mlde_shadow_advisor** | `program_code/ml_training/mlde_shadow_advisor.py::_persist_recommendations` | `mlde_shadow_advisor.py:386-455` (寫入 SQL `:407-423`) | `generate_shadow_recommendations` (line 458-474) caller (scheduler 待查) | hardcoded `'real_outcome'` (line 420) + `NULL,NULL,NULL` (421) | **PA 漏列 — 詳 §2 補位** | 同 pattern |
| **mlde_demo_applier** | `program_code/ml_training/mlde_demo_applier.py::_insert_live_candidate` | `mlde_demo_applier.py:1189-1286` (寫入 SQL `:1260-1286`) | `_apply_one` `_record_application` 路徑（demo→live promotion） | hardcoded `'real_outcome'` (line 1273) + `NULL,NULL,NULL` (1274)；docstring `:1217-1230` 明確「LG-5 audit row legacy 路徑，與 replay 無關」 | **NO — legacy LG-5 audit row 路徑**（per PA §2B + MIT §2.1） | 不動 |

**4 producer 真實寫頻率**（per MIT §2.1）：dream 3-15 row/hr + opportunity 1 row/hr + mlde_demo_applier 4-15/cycle (legacy real_outcome) + mlde_shadow_advisor (cycle TBD) + linucb 0 row → daily ~96-456 row 進 calibrated_replay tier 後（dream + opportunity 升級後）。

---

## §2 mlde_shadow_advisor.py 補位（PA §2B 漏列）

**Critical finding**: PA report §2B 列「4 producer」實際 4 全 verify_replay_evidence_and_insert callers，但 PA 漏列 **mlde_shadow_advisor.py** 為獨立的第 5 個產生路徑（V031 view-feed 的 ranking + veto 路徑，與 dream/opportunity 的 trade history aggregation 路徑並行）。

### §2.1 真實 verify_replay_evidence_and_insert call 位點

`program_code/ml_training/mlde_shadow_advisor.py:386 _persist_recommendations(dsn, recommendations)`：
- SQL line 406-423 寫入透 V036 verify function
- 19 args 全傳，evidence_source_tier 寫 `'real_outcome'` (line 420)
- replay metadata 全 NULL (line 421-422)
- per-rec loop iterating ShadowRecommendation list（line 428-453）

### §2.2 既有寫入特性 vs dream_engine / opportunity_tracker 比對

| 屬性 | dream_engine | opportunity_tracker | **mlde_shadow_advisor** |
|---|---|---|---|
| `p_engine_mode` | hardcoded `cfg.engine_mode`（caller param） | `cfg.engine_mode` | **`rec.engine_mode`** （ShadowRecommendation dataclass field — variable per row） |
| `p_symbol` | NULL（strategy-wide） | NULL（regret aggregates） | **`rec.symbol`** (variable) |
| `p_strategy_name` | `insight.get('strategy_name')` | NULL（aggregates across strategies） | **`rec.strategy_name`** (variable) |
| `p_source` | hardcoded `'dream_engine'` | hardcoded `'opportunity_tracker'` | **`rec.source`** (variable — per V031 allowlist `{ml_shadow, dream_engine, opportunity_tracker, linucb}`) |
| `p_recommendation_type` | hardcoded `'parameter_proposal'` | hardcoded `'regret_summary'` | **`rec.recommendation_type`** (variable) |
| `p_created_by` | hardcoded `'mlde_dream_engine'` | hardcoded `'mlde_opportunity_tracker'` | hardcoded `'mlde_shadow_advisor'` |

**critical**：mlde_shadow_advisor `rec.source` 是 variable — 可能寫 `dream_engine` / `opportunity_tracker` / `ml_shadow` / `linucb` 任一值（per docstring line 392-396）。

### §2.3 R7 升級需求裁定

**結論**：**YES — 必加 R7-T1.5 task** 升級 `mlde_shadow_advisor._persist_recommendations`。

**理由**：
1. 與 dream_engine + opportunity_tracker 同型路徑（透 V036 verify_replay function 寫入 mlde_shadow_recommendations）
2. line 420 寫死 `'real_outcome'` → 未升級則 mlde_shadow_advisor 走 V031 view-feed 訓練 row 全 real_outcome tier，無法走 V051/V040 paired CHECK 的 calibrated_replay 路徑
3. mlde_shadow_advisor 的 source field 是 variable（`rec.source`）→ 升級時必驗 V031 source allowlist 與 evidence_source_tier 變動的相容性
4. **獨立路徑** vs dream_engine / opportunity_tracker：mlde_shadow_advisor 是 V031 view-feed 路徑（從 `mlde_edge_training_rows` view 算 ranking + veto），dream/opportunity 是 trade history aggregation 路徑，**3 個 producer 並行**

**修正 PA report**：PA §13.5 修訂路線圖列「R7 4 producer 升級」實際是 **5 producer 涉及**（4 verify_replay caller + linucb 0 caller），其中：
- R7-T1 dream_engine.persist_dream_insights 升級（寫 calibrated_replay）
- **NEW R7-T1.5** mlde_shadow_advisor._persist_recommendations 升級（寫 calibrated_replay）
- R7-T2 dream_engine.generate_replay_candidates verify-only（caller `replay_routes.py` review）
- R7-T3 opportunity_tracker.persist_regret_summary 升級（寫 calibrated_replay）
- R7-T4 LinUCB caller 確認（NO-OP，詳 §7）
- R7-T5+ 不變

**R7-T1.5 LOC 估**：~50 LOC Python（同 R7-T1/T3 pattern；caller 端從 R6 CalibrationResult 計 expires_at + R6 label → tier map）

### §2.4 R7-T1.5 與 sibling CC FUP-2 互動

mlde_shadow_advisor 寫入 row 是 `mlde_edge_training_rows` VIEW 的 source（per MIT §4.2 揭 view derives from mlde_shadow_recommendations）。FUP-2 (commit `34211ab4` PASS to E4) 處理 `attribution_chain_ok` 的 4 source column（`signal_id` / `context_id` / `signal_context_id` / `label_net_edge_bps`）。R7-T1.5 升級 evidence_source_tier 不影響 attribution_chain_ok view computation — **0 conflict**。

---

## §3 R7 4-producer 統一接口 spec

### §3.1 R7 producer 升級必傳 4 metadata

每個 R7 producer 升級時必傳：
| Arg | 型別 | 來源 | 計算方式 |
|---|---|---|---|
| `p_evidence_source_tier` | TEXT | R6 CalibrationResult.label map | `'calibrated_replay'` if label ∈ {Calibrated, Limited}; **discard not write** if label=None |
| `p_replay_experiment_id` | TEXT (UUID) | `lookup_replay_config_blob(experiment_id)` | `experiment_registry.py:566` → `replay.experiments.experiment_id` PK |
| `p_manifest_hash` | TEXT (BYTEA hex) | `lookup_replay_config_blob(experiment_id)` | `experiment_registry.py:566` → `replay.experiments.manifest_hash` BYTEA |
| `p_expires_at` | TIMESTAMPTZ | caller 從 R6 CalibrationResult.ttl 直接取 | `now() + label_to_ttl(label)` per QC §4.3：calibrated→7d / limited→3d / none→never_inserted |

### §3.2 統一 helper 設計建議

**建議 R7 IMPL 抽公共 helper**（避 4 producer 重複代碼）：

```python
# program_code/local_model_tools/replay_metadata_helper.py（新檔，~80 LOC）
def build_replay_metadata(
    *,
    experiment_id: str,
    calibration_result: CalibrationResult,  # from R6 deliver
    cur: Any,
) -> tuple[str, str, str, datetime] | None:
    """從 R6 CalibrationResult + experiment_registry helper 構造 4-tuple replay metadata。

    Returns:
        - None if calibration_result.label == ExecutionConfidence.None (caller skip)
        - (tier, replay_experiment_id, manifest_hash, expires_at) if Calibrated/Limited
    """
    if calibration_result.label == ExecutionConfidence.None_:
        return None
    blob = lookup_replay_config_blob(cur, experiment_id)  # FROM experiment_registry.py:566
    if blob is None:
        return None
    tier = "calibrated_replay"  # both Calibrated and Limited write same tier; differ in TTL
    expires_at = datetime.now(timezone.utc) + calibration_result.ttl
    return (tier, str(experiment_id), blob.manifest_hash.hex(), expires_at)
```

### §3.3 caller side IMPL pattern

**建議**：caller side 構造 metadata（不在 V055 function level 抽 helper，function body 已 land 不動）。caller 端從 R6 deliver 取 CalibrationResult，跑 build_replay_metadata 構造 4-tuple，調 V036 19-arg function 同時傳 calibrated_replay metadata。`evidence_source_tier='calibrated_replay'` 時必傳 4 metadata；`label=None` 時 skip insert。

### §3.4 cardinality 影響評估（per MIT §2.2）

R7 升級後 daily Block B traffic：
- dream_engine 3-15 row/hr × 24 = 72-360 row/day calibrated_replay
- opportunity_tracker 1 row/hr × 24 = 24 row/day calibrated_replay
- mlde_shadow_advisor (TBD cycle) ~ 24-72 row/day（保守估，per cycle 多筆推薦）
- linucb 0
- **Total daily**: 120-456 row/day calibrated_replay

7d expires_at TTL × 456 row/day = ~3200 row 同時 valid（< MIT §2.4 不洪水閾值）。Sprint D R8 retention 仍需處理（30d × calibrated_replay row 累積至 ~9k-13k row/month）。

---

## §7 LinUCB 0 caller 確認 (R7-T4 NO-OP)

### §7.1 二次驗證

AI-E grep 4 file × `verify_replay_evidence_and_insert\|verify_replay`：
- `program_code/ml_training/linucb_trainer.py`
- `program_code/ml_training/linucb_arm_migration.py`
- `program_code/ml_training/linucb_shadow_compare.py`
- `program_code/exchange_connectors/.../learning_routes_linucb.py`

**0 hit**。確認 MIT §2.1「linucb 0 producer wired into V036 verified function path」。

### §7.2 R7-T4 結論

**NO-OP**。R7 dispatch 不必動 LinUCB caller。

### §7.3 future-proofing 注意

memory `linucb_shadow_compare_retention.md`：「Phase 4 子任務 4-06 deferred；linucb_shadow_compare.py 保留至 Rust warm-start 實裝或 4-06 降級」。**若 future Sprint D / E LinUCB warm-start 加 verify_replay caller**，必同 sprint 對齊 `evidence_source_tier='calibrated_replay'` pattern（不能 hardcoded 'real_outcome'）。

---

## §11 R7 dispatch order 推薦

### §11.1 修訂後 R7 wave structure

```
Wave 0 (advisory, 1d): AI-E spec ✅ DONE (本 deliverable)

Wave 1 (並行 4-5 task, 1.5d):
  E1-A: R7-T1 dream_engine.persist_dream_insights upgrade (~50 LOC Python)
  E1-B: R7-T3 opportunity_tracker.persist_regret_summary upgrade (~50 LOC Python)
  E1-C: R7-T1.5 mlde_shadow_advisor._persist_recommendations upgrade (~50 LOC Python) [NEW per §2.3]
  E1-D: R7-T2 dream_engine.generate_replay_candidates 接線驗證 (verify-only, replay_routes.py review) [可歸 E2]
  E1-E: R7-T4 LinUCB caller grep 並裁定 [verify-only NO-OP per §7, 可歸 E2]
  + 共用 helper: replay_metadata_helper.py (~80 LOC, pre-Wave 1 dispatch)
  => 3 E1 IMPL + 2 E2 verify 並行（5 並行）

Wave 2 (並行 3 task, 1d):
  E1-A: R7-T5 evidence_filter capability probe test (~100 LOC)
  E1-B: R7-T7 FK chain + observability audit (~100 LOC; +per MIT §1.5 推薦 fetch_pending_sql_and_params 加 INFO log capability dump ~10-15 LOC, 順帶併入 R7-T7)
  E1-C: R7-T8 lookup_replay_config_blob reuse audit (~30 LOC)

Wave 3 (序列 1 task, 1.5d):
  E1-A: R7-T6 E2E integration test (~250 LOC)

Wave 4 (序列 1 task, 1d):
  E2 review (per PA §7.4 R7 必查 3 點 + AI-E 補：5 producer (含 mlde_shadow_advisor) 升級覆蓋)
  E4 regression PASS
```

**修訂後 Sprint C2 (R7) total wall**：1d (advisory) + 1.5d (W1) + 1d (W2) + 1.5d (W3) + 1d (W4) = **6d wall** （與 PA §4.2 一致；R7-T1.5 並行 W1 不增 wall）

---

## §12 AI-E 結論 + 對 PM 下一步

### §12.1 R7 dispatch GO 評估

| Item | 結論 |
|---|---|
| R7 task DAG (PA §4) | **GO with R7-T1.5 補位** |
| LinUCB caller status | **NO-OP confirmed** (grep 4 file 0 hit) |
| sibling CC FUP-2 status | **0 wait constraint** (commit `34211ab4` PASS to E4) |
| V055 + V051 chain integrity | **完整** |
| 4 producer 統一 helper 設計 | **建議 caller side `build_replay_metadata`** |
| capability probe 6/6 (HEAD `e5b5227c`) | **預期全 true → Block B 完整版** |
| TTL 7d/3d (calibrated/limited) | **per QC §4.3 / PM D2 decision** |
| 跨平台合規 | **0 風險** |

### §12.2 對 PM 下一步建議

1. **Accept this advisory** + 接 PA §13.5 路線圖（Sprint C2 R7 6d wall）
2. **Approve R7-T1.5 補位**（mlde_shadow_advisor.py，並行 W1）
3. **Dispatch R7 W0 closure** → 啟 C2 W1 並行 5 sub-agent（C1 closed sign-off 後）
4. **CLAUDE.md §三 18-blocker #11 update**：FUP-2 真實狀態 commit `34211ab4` PASS to E4（已 PM 接收，per CLAUDE.md §三 既登記）
5. **預備 Sprint D R8 retention policy task**：mlde_shadow_recommendations 30-60d retention for replay-derived row（per MIT §2.4）

### §12.3 Risk register summary

P0 BLOCKER：**0**
P1 RECOMMENDED：1（R7-T1.5 補位 per §2.3）
P2 NICE-TO-HAVE：3（observability log per MIT §1.5 / staged rollout 評估 / Sprint D R8 retention policy）

---

**AI-E ADVISORY DONE**
