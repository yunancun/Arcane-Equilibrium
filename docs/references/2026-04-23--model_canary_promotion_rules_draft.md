# Model Canary Promotion Rules — Draft

**Status**: DRAFT — not auto-enforced. Operator-driven transitions only in
Phase 1a/2/3. Auto-promote cron job is a Phase 4 second-half deliverable.

**Scope**: `learning.model_registry` (V023 migration) state-machine
transitions. Applies to the ONNX quantile predictor trio produced by
`run_training_pipeline.py::_run_quantile_pipeline`.

**Owners**: Operator (manual promote) · Phase 4 auto-promote cron (future).

---

## State machine

```
          register                      operator                    operator
    ∅ ─────────────►  shadow  ──────────────► promoting ────────────────► production
                          │                       │                            │
                          │                       │                            │
                          └───── operator ────────┘                            │
                                  │                                            │
                                  ▼                                            │
                              rejected  ◄──────────────── (terminal)           │
                          (terminal)                                           │
                                                                               │
                                                                               ▼
                                                         operator    retired (terminal)
                                                         ─────────►
```

- **shadow** (default) — model registered, not yet approved for any use. ONNX
  artifact on disk + `_current` symlink updated automatically by training
  pipeline. Rust reader ignores shadow rows (only queries production/
  promoting).
- **promoting** — operator has approved for Phase 2 shadow observation via
  `combine_exit_decision`. ML inference runs on each close fill but does not
  influence execution (`ml_override_high=2.0` sentinel ensures no override).
  Data flows into `learning.decision_shadow_exits` for agreement-metric
  collection.
- **production** — operator has approved for Phase 3+ live inference. Rust
  OnnxModelManager loads this artifact on next SIGHUP/restart. `ml_override_
  high` tunable is tightened (Phase 3 plan: 0.95 → 0.85 → 0.75 per
  TODO.md DUAL-TRACK-EXIT-1 §Phase 3).
- **retired** — model superseded by a newer production model. Audit row
  retained for historical replay. `retired_at` + `retirement_reason` set.
- **rejected** — model rejected during shadow/promoting phase (Brier drift,
  feature skew, excessive disagreement, etc.). Never saw production traffic.
  Symmetric terminal to `retired` but carries the "never shipped" signal.

Python state-machine validator: `program_code.ml_training.model_registry.
transition_canary_status`. Rust reader: `openclaw_engine::ml::registry::
resolve_latest_production_artifact`. API route: `POST /api/v1/ml/model_
promote` (Operator gate).

---

## Registration criteria

Row is inserted when all of:

1. `run_training_pipeline.py::_run_quantile_pipeline` completes successfully.
2. `export_quantile_trio_to_onnx` writes the ONNX artifact with
   `verdict != 'no_ship'`.
3. `register_quantile_trio_from_onnx_out` commits the row with initial
   `canary_status = 'shadow'`.

Skipped when:

- DB unavailable (logged; training still succeeds, artifact on disk)
- `verdict = 'no_ship'` (quantile report fails n≥500 or 6 metrics gate)

Re-training the same slot refreshes `artifact_path / artifact_size / sha256 /
acceptance_report / verdict / training_sample_size` via ON CONFLICT DO UPDATE
but **preserves** `canary_status / promoted_at / retired_at` — operator's
transition decisions are sticky across retrains.

---

## Phase-gated promotion criteria

### Phase 2 shadow → promoting (Operator, manual)

Eligibility:

- `verdict = 'should_ship'` or `verdict = 'shadow_only'` (no_ship never
  registered; both are eligible because shadow_only is specifically meant
  to fire in shadow before graduating)
- `training_sample_size >= 200` (hard minimum from quantile_reports.py)
- `feature_schema_hash` matches the running Rust engine's
  `FEATURE_NAMES_V1_HASH` (no schema drift — Rust tract will refuse load
  otherwise per onnx_exporter.py `_META_SCHEMA_HASH` guard)
- Row exists in registry ≥ 1 day (Operator had time to review
  `acceptance_report` JSONB)

Operator action: `POST /api/v1/ml/model_promote { row_id, to_status: 'promoting' }`.

### Phase 2 promoting → production (Operator, manual in Phase 2; cron in Phase 4)

Eligibility (all must hold for ≥ 7 consecutive days of shadow data):

- Row has ≥ 500 observations in `learning.decision_shadow_exits` for the
  same (strategy, engine_mode) — statistical power minimum
- Shadow agreement ratio (Track P pure decision vs Combine-with-mock-ML)
  ≥ 60% — target set in DUAL-TRACK-EXIT-1 §Phase 2 completion standard
- Brier score on shadow predictions does not exceed 1.15 × baseline
  (heuristic: guards against miscalibration regression)
- Feature drift PSI for all 7 Track P dimensions < 0.25 vs training
  distribution (drift_detector.rs ADWIN threshold; Phase 4 will add model-
  specific PSI)

Operator action: `POST /api/v1/ml/model_promote { row_id, to_status: 'production' }`.

Rust reader picks up the new row on next SIGHUP or startup. No auto-reload
yet (Phase 4 auto-promote cron will emit SIGHUP after the UPDATE).

### Any → rejected (Operator, manual; auto-rejection criteria below)

Trigger conditions (any one):

- Shadow agreement < 40% after 3 days (disagrees more often than it agrees)
- Brier score > 1.5 × baseline for 2 consecutive days
- Feature drift PSI ≥ 0.25 on any dim
- Operator override (e.g. post-incident review concludes model is
  untrustworthy regardless of metrics)

Operator action:
```
POST /api/v1/ml/model_promote
{
  "row_id": N,
  "to_status": "rejected",
  "retirement_reason": "<audit-trail text>",
  "confirm": true
}
```

Terminal — no further transitions allowed. Artifact on disk stays for
forensic replay.

### production → retired (Operator, manual)

Trigger: a newer model reaches production for the same slot. Old model
retired same operator-transaction:

1. `POST /model_promote { row_id: OLD, to_status: 'retired', retirement_reason: 'superseded by row_id=NEW', confirm: true }`
2. `POST /model_promote { row_id: NEW, to_status: 'production' }`

Rust reader's "latest production" query returns NEW on next SIGHUP.

---

## Auto-promote cron (Phase 4 deliverable — **not in INFRA-PREBUILD-1**)

Planned workflow:

1. Nightly cron `scripts/auto_promote_canary.py` runs.
2. For each (strategy, engine_mode) with a `promoting` row:
   - Query last 7d of `learning.decision_shadow_exits`
   - Compute: agreement_pct, brier, per-dim PSI
   - If all thresholds met → issue `POST /model_promote` to transition to
     production + fire SIGHUP to engine
   - If any threshold violated severely → issue `POST /model_promote` to
     reject + alert channel
3. Log every decision to `learning.canary_promotion_decisions` (table not
   yet created — design placeholder for Phase 4).

Implementation deferred to Phase 4 second-half per DUAL-TRACK-EXIT-1
§Phase 4 plan. INFRA-PREBUILD-1 ships the state-machine foundation so
Phase 4 cron only has to author the thresholds + cron driver, no schema or
state-machine work needed.

---

## Operator playbook summary

```
# list all shadow models waiting for review
GET /api/v1/ml/model_registry?canary_status=shadow

# list in-flight promoting models
GET /api/v1/ml/model_registry?canary_status=promoting

# resolve which model would load today for this slot
GET /api/v1/ml/model_info?strategy=ma_crossover&engine_mode=demo&quantile=q50

# promote shadow → promoting (after reviewing acceptance_report)
POST /api/v1/ml/model_promote { row_id: N, to_status: "promoting" }

# promote promoting → production (after ≥7d of shadow observations meet gates)
POST /api/v1/ml/model_promote { row_id: N, to_status: "production" }

# reject a shadow/promoting model
POST /api/v1/ml/model_promote {
  row_id: N,
  to_status: "rejected",
  retirement_reason: "Brier drift on demo after 3d",
  confirm: true
}

# retire a prior production model when a new one is ready
POST /api/v1/ml/model_promote {
  row_id: OLD,
  to_status: "retired",
  retirement_reason: "superseded by row_id=NEW",
  confirm: true
}
```

All promote endpoints require Operator role auth (`_require_operator_role`
gate in `governance_routes.py`). Non-Operator callers get 403.

---

## Open questions

- **Threshold calibration**: 60% / 500 observations / 7 days are
  placeholders. Real numbers come from Phase 2 dry-run data when shadow
  first fires on demo.
- **Per-strategy overrides**: ma_crossover may need different thresholds
  than bb_breakout (different tick cadence, different sample rates).
  Phase 4 cron may add `strategy_overrides` YAML.
- **Automated retire on superseded**: when a new production model is
  promoted, should the old one auto-retire in the same transaction?
  Current design keeps them separate for audit clarity. Revisit when
  operators start doing N-per-week promotions and find this tedious.
- **Rollback semantics**: if a production model is found faulty post-
  deployment, what's the flow? Current design: retire + promote a
  prior-known-good model (manual). Phase 4 may add a "rollback" state
  that inverts a retired → production transition without re-training.

---

## References

- `sql/migrations/V023__model_registry.sql` — schema
- `program_code/ml_training/model_registry.py` — Python writer + state machine
- `rust/openclaw_engine/src/ml/registry.rs` — Rust reader (pure-fn resolver)
- `program_code/exchange_connectors/bybit_connector/control_api_v1/app/ml_routes.py`
  — `/api/v1/ml/*` endpoints
- `docs/worklogs/2026-04-18--dual_track_exit_design.md` — upstream design

---

## Shadow observation ↔ canary promotion linkage

INFRA-PREBUILD-1 audit L2-7 (2026-04-23) identified that this draft spelled
out both the `canary_status` state machine and the per-phase eligibility
gates, but never explained **how an operator is supposed to coordinate**
`ExitConfig.shadow_enabled` (Part A) with `canary_status` (Part B) during
Phase 2 activation. This section closes that gap with the concrete
playbook — what to flip first, what each disagreement percentage means
under Phase 1a, and the one-line diagnostic commands.

INFRA-PREBUILD-1 審計 L2-7（2026-04-23）：原 draft 有 canary 狀態機與
phase 晉升閾值，但沒有「shadow_enabled（A 部）與 canary_status（B 部）
一起如何操作」的 playbook。本節補齊 Phase 2 啟動流程 + disagreement%
解讀 + 門檻對應 + 一鍵診斷。

### 1. Phase 2 啟動流程對照表（shadow flag state vs registry state）

```
Step 1 · initial state
  shadow_enabled = false                  (全三環境 TOML)
  model_registry  = all rows canary_status='shadow'
  runtime effect  = 0 shadow exit rows, mock ML 不跑

Step 2 · operator review acceptance_report
  operator 比對 shadow rows 的 disagreement% / agreement breakdown，
  判定某個 strategy × engine_mode × quantile slot 的 shadow model 可
  進入 Phase 2 觀察。觀察完成 → 呼叫
  POST /api/v1/ml/model_promote (canary_status: shadow → promoting)

Step 3 · open observation window
  operator 同時在 risk_config_demo.toml 把 [exit].shadow_enabled = true
  （或走 IPC patch_risk_config 熱重載），Combine Layer 開始寫
  learning.decision_shadow_exits。**此時** shadow_enabled 與 promoting
  slot 才真正聯動。

Step 4 · 7d/14d observation
  每 6h 跑 passive_wait_healthcheck.py → check [8] 顯示 disagreement%
  + engine breakdown。累積 n ≥ 500 rows 後：
    - agreement ≥ 60% → 呼 POST /model_promote
      (canary_status: promoting → production)
      shadow_enabled 可保 true（觀察下一 slot）或 flip false
    - agreement < 40% 持續 3d → POST /model_promote
      (canary_status: promoting → shadow 或直接 retired)
      shadow_enabled flip false，重訓 + 調 mock 或 veto path
```

### 2. disagreement% 解讀 cheat sheet（Phase 1a 限制下）

⚠️ **Phase 1a 警告留尾** — 當前 `ml_override_high=2.0` sentinel 不可達，
所有 Hold→Lock 升級路徑對 ML 封閉。這意味著 disagreement **實質只是
"Physical→Hybrid tag 差異"**（同樣產出 Lock 信號，只是 source 欄位從
`Physical` 變 `Hybrid`），不是真正的 ML 與 Track P「該不該平倉」分歧。

```
disagreed = 0%
  → mock score < 0.70 for all rows → edge_estimates 全 below confirm
  → 要嘛 JS cells 過度保守，要嘛 edge 估計偏負
  → 行動：查 settings/edge_estimates.json 的 grand_mean_bps，若 <-5 bps
         代表 fee drag 壓制 edge，正常；若 >0 bps 但 shrunk_bps 全 <4 bps
         需檢查 JS estimator 的 shrinkage 強度（k in shrinkage_weight）

disagreed = 30–50%
  → 部分 PHYS-LOCK fire 時 score ≥ 0.70 → Combine 產 Hybrid source
  → Hybrid confirm 對 Lock 決策是一致的（不改信號）但可用於信心加成
  → 行動：觀察 Hybrid vs Physical 平均 net_pnl 差異，Hybrid 若無額外
         信息增益（差距 < 1 bps）代表 mock 尚未提供價值；Hybrid 若平均
         淨賺多 2+ bps 代表 confirm threshold 0.70 可用於 Phase 3+ veto

disagreed > 70%
  → mock score 經常 ≥ 0.70（edge_estimates 偏高）
  → 行動：mock 的 (shrunk+10)/20 公式假設 ±10 bps 典型域；若 cells 普遍
         >+8 bps 代表 clamp 經常撞 1.0，線性映射失真
         → 考慮重校 build_ml_inference_shadow 的中心點/寬度，或先收緊
         edge estimator 的 shrinkage（避免極端 cells 落到域外）

disagreed % volatile day-to-day（±20% 跳動）
  → 樣本量不足 / cells 冷啟動中
  → 行動：n ≥ 500 前不下結論，待 7d 穩態再決策
```

### 3. 決策門檻對應（連動 Phase 3 `ml_override_high` 收緊）

```
Phase 2 exit criteria（any slot 進 production 的必要條件）：
  (a) shadow n ≥ 500                    (樣本量)
  (b) 7d rolling agreement ≥ 60%        (一致性)
  (c) Hybrid avg net_pnl ≥ Physical     (無負向偏差；Phase 1a 下通常持平)
  (d) healthcheck [8] 連續 ≥ 7d no FAIL (silent-dead 指紋歸零)

(a)–(d) 全 PASS → 呼 POST /model_promote (promoting → production)
         同時 CLAUDE.md §三 記 milestone：「Phase 2 shadow PASS → Phase 3 入口」

Phase 3 entry（production model 上線真 ONNX 推論）：
  (e) 切 real ONNX 訓練 pipeline   → model_registry 寫第一筆 ONNX artifact
  (f) ml_override_high 0.95 → 0.85  → 解鎖 Hold → Lock 升級路徑
  (g) build_ml_inference_shadow 退役 → combine_layer 直接讀 OnnxModelManager

Phase 3 reject criteria（slot 降級）：
  (h) agreement < 40% 持續 3d     → reject current shadow → retired
  (i) Hybrid avg net_pnl < Physical - 2 bps → mock 注入負向偏差 → retired
  (j) healthcheck [8] FAIL 連續 ≥ 2 次 → writer/channel 問題 → 立即 flip
      shadow_enabled=false，RCA 先於下一輪 promote
```

### 4. Operator 一鍵診斷指令

```bash
# 當前三環境 shadow flag 狀態
grep "shadow_enabled" settings/risk_control_rules/risk_config_*.toml

# 當前 registry 各 slot 狀態（list + per-slot resolver）
curl -sS http://localhost:8000/api/v1/ml/model_registry | jq '.rows[] | [.strategy, .engine_mode, .quantile, .canary_status, .train_date]'

# 24h disagreement 分布（per engine_mode）
psql "${OPENCLAW_DATABASE_URL}" -c "
  SELECT engine_mode,
         COUNT(*) AS total,
         COUNT(*) FILTER (WHERE disagreed) AS disagreed_n,
         ROUND(100.0 * COUNT(*) FILTER (WHERE NOT disagreed) / NULLIF(COUNT(*),0), 1) AS agreement_pct
    FROM learning.decision_shadow_exits
   WHERE ts > now() - interval '7 days'
   GROUP BY engine_mode
   ORDER BY engine_mode;
"

# 整體 runtime 健康（含 [8] shadow_exits + [9] model_registry）
python3 helper_scripts/db/passive_wait_healthcheck.py

# 若 [8] FAIL（silent-dead 指紋）→ 先 flip shadow_enabled=false 再 RCA
#   1. 編 settings/risk_control_rules/risk_config_demo.toml [exit].shadow_enabled=false
#   2. 或 IPC 熱重載：curl -X POST .../api/v1/risk/patch -d '{"exit":{"shadow_enabled":false}}'
#   3. 查 engine log：journalctl -u openclaw-engine -n 200 | grep -iE "shadow|ShadowExit"
```

### 5. Audit L2-1 警告留尾（誠實告知 operator）

⚠️ **Phase 1a disagreement 非真 ML disagreement。** 當前
`ml_override_high=2.0` sentinel 使 mock ML 永遠無法觸發 `Hold → Lock`
升級，`combine_exit_decision` 對 ML 輸入的唯一可觀測反應是 `Lock` 路徑
的 source 欄位由 `Physical` 變 `Hybrid`（信號完全相同）。因此：

- 本節所有 disagreement% 數字，物理意義等同於「mock score ≥ 0.70 的比率」
- Phase 3+ 切真 ONNX + `ml_override_high` 收到 0.85 後，disagreement
  才開始帶上「ML 認為該 Hold 但 Track P 認為該 Lock」這類有意義的
  決策分歧語意
- 目前 disagreement% 可當作 **mock 穩定性 proxy + edge_estimates 校準
  警報**，但 **不代表 ML 本身對交易結果的實際影響**
- Phase 3 入口前，operator 不應用 disagreement% 推論「ML 能否改善 PnL」—
  那是 Phase 3+ 才有的問題

L2-1 警告同步寫入 `model_canary_promotion_rules_draft.md`（本檔）與
`CLAUDE.md §三`（當下次 §三 snapshot 歸檔時），避免 Phase 2 狀態
在 operator/audit round-trip 之間丟失。
- TODO.md INFRA-PREBUILD-1 section
