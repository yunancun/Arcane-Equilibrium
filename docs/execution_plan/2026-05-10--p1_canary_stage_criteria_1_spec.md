# P1-CANARY-STAGE-CRITERIA-1 — Stage 1→2→3 Promotion + Demote Criteria 寫死 Spec

**Status**: PA SPEC DRAFT 2026-05-10 ｜ Owner: PA design / E1 IMPL / E2+E4 review
**對應 dispatch**: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--sprint_n1_dispatch_draft.md` §3.3 W3-3 + §3.5 W5 P1 list
**對應 AMD**: AMD-2026-05-09-03 graduated canary default §2.2 + §4.4
**對應 healthcheck**: `[58] graduated_canary_stage_invariant`
**Cross-ref**: AMD-2026-05-02-01（SM-02 Lease）· DOC-08 §12 9 不變式 · §二 16 根原則

---

## 1. Background + Trigger

QC 在 Sprint N+1 dispatch v3 review 提了 **HIGH push back 2** — AMD-2026-05-09-03 §2.2 5-stage 表雖 list 出 promotion / rollback 條件文字，但 IMPL 落地時面臨歧義：

- §2.2 Stage 1 → Stage 2 寫「`entry_fills ≥ 10` AND `boundary_violation_count == 0`」+ 觀察期 7d wall-clock — 但兩個條件**沒明文 AND/OR 關係**：是「7d **AND** entry_fills≥10」（whichever later）還是「7d **OR** entry_fills≥10」（whichever earlier）？
- 「sample size n ≥ 200 OR wall-clock ≥ 72h whichever later」推薦字句出現在 dispatch §3.3 但 AMD 文未寫死，N+0 W-AUDIT-9 IMPL E1 無法解析
- §0.2.B post-V082 W6 baseline 揭露**真實 close fill 只有 9 條**，若 promote criteria 用 `entry_fills` 可能永遠不達 → 必須加 wall-clock floor（避免無限 dwell）+ 加 sample 上限 cap（避免 reject 樣本污染 entry 計數）

**核心目標**：把 §2.2 表所有 promotion + auto-rollback 條件落到 **healthcheck `[58]` 可執行 SQL** + Rust `shadow_mode_provider` stage-aware eval 程式可實作的精度。

---

## 2. Stage 1 → Stage 2 Promotion Criteria（寫死）

### 2.1 公式

```
Stage 1 → Stage 2 PROMOTE 觸發 ⇔
    (wall_clock_elapsed_ms ≥ 7 * 86_400_000)
    AND (entry_fills_count ≥ 10)
    AND (boundary_violation_count == 0)
    AND (sample_size_floor_ms ≥ 72 * 3_600_000)   # whichever later 語義
```

**「whichever later」精確語義**：wall_clock 與 sample_size_floor 都必達；entry_fills 是 quantitative gate，必獨立達 10。

### 2.2 Sample 計算（避 reject 污染）

`entry_fills_count` 計算 SQL（cohort = strategy_X × symbol_Y × environment_E）：

```sql
SELECT COUNT(*) AS entry_fills_count
FROM trading.fills f
WHERE f.strategy_name = $1                              -- cohort_strategy
  AND f.symbol = $2                                      -- cohort_symbol
  AND f.engine_mode = $3                                 -- cohort_environment
  AND f.ts >= to_timestamp($4 / 1000.0)                 -- stage_entered_at_ms
  AND COALESCE(f.exit_source, '') = ''                  -- entry only, exclude exits
  AND NOT EXISTS (                                       -- exclude rejected_governance fills
      SELECT 1 FROM trading.risk_verdicts rv
      WHERE rv.context_id = f.entry_context_id
        AND rv.reason ILIKE '%rejected_governance%'
  );
```

### 2.3 Wall-clock window

`wall_clock_elapsed_ms = current_ts_ms - stage_entered_at_ms`，**不**接受 IPC `patch_risk_config` 重啟 reset（per AMD-2026-05-09-03 §2.4 cohort 切換才 reset）。

`sample_size_floor_ms = 72h`（QC HIGH push back 2 推薦下界）— 即使 wall_clock 7d 達且 entry_fills≥10，若 stage entered <72h 仍 PENDING（防意外 cohort 切換 race）。

### 2.4 Boundary violation

per AMD-2026-05-09-03 §2.2 表的 rollback metric — 任一 trip 即 boundary_violation +1：

- lease IPC 失敗率 24h > 0.5%
- authorization invalid
- SM-04 ≥ L3 escalate
- `[40]` realized_edge_acceptance hard FAIL
- `[55]` chain_with_lease ratio drop ≥ 10%
- `[42b]` settled eligible ratio < 0.95
- 任一 healthcheck 收 hard FAIL

### 2.5 Fail conditions

`entry_fills_count` 在 14d wall-clock 仍 < 10 → **escalate WARN** 到 §4.2 GUI surface「stage_1_starvation」（不 auto-demote，operator 拍板是否切 cohort 或 archive）。

---

## 3. Stage 2 → Stage 3 Promotion Criteria

```
Stage 2 → Stage 3 PROMOTE 觸發 ⇔
    (wall_clock_elapsed_ms ≥ 14 * 86_400_000)
    AND (entry_fills_count ≥ 30)
    AND (gross_pnl_usdt > -5.0)
    AND (DSR > 0.5)                  # 由 W-AUDIT-6 acceptance pipeline 計算
    AND (boundary_violation_count == 0)
    AND (sample_size_floor_ms ≥ 168h)   # 7d hard floor for demo
```

**DSR 計算**：reuse W-AUDIT-6 SDR/PBO writer（per AMD-2026-05-02-01 + DOC-08 §6 acceptance）— cohort scope `(strategy, symbol, environment, stage_entered_at_ms..now)`。DSR=NULL → PROMOTE PENDING（不 fail）。

**Fail**：14d wall-clock 仍未滿足任一條件 → **escalate WARN** + operator 拍板（Stage 2 dwell extension 或 demote 至 Stage 1 重觀察）。

---

## 4. Stage 3 → Stage 4 Promotion Criteria

```
Stage 3 → Stage 4 PROMOTE 觸發 ⇔
    (wall_clock_elapsed_ms ≥ 21 * 86_400_000)
    AND (gross_pnl_usdt > 0)
    AND (DSR PASS by W-AUDIT-6 acceptance)
    AND (PBO ≤ 0.5)
    AND (attribution_chain_ok ratio ≥ 0.7)
    AND (boundary_violation_count == 0)
```

Stage 4 **不 auto-promote**（per AMD-2026-05-09-03 §2.2 表）— `[58]` healthcheck PASS 後寫 GUI surface「ready_for_stage_4_review」，operator 拍板 + signed authorization + Decision Lease + 5-gate live boundary 全鏈滿足才升 4。

---

## 5. Demote Criteria（任一 trip → fall back 1 stage）

| 來源 stage | Demote → | trip 條件（OR）|
|---|---|---|
| Stage 1 | Stage 0 | `boundary_violation_count > 0` OR `lease IPC 失敗率 1h > 1%` OR SM-04 ≥ L3 |
| Stage 2 | Stage 1 | `gross_pnl_usdt < -10.0` OR `DSR < 0` OR Stage 1 任一 rollback 條件持續 ≥ 6h |
| Stage 3 | Stage 2 | `gross_pnl_usdt < -20.0` OR `DSR < 0` OR `attribution_chain_ok ratio < 0.3` OR Stage 2 任一條件持續 ≥ 12h |
| Stage 4 | Stage 0（不是 Stage 3）| 任一 boundary 失敗 → cancel_token shutdown，per §2.2 表 |

**Demote 機制**：自動觸發 → write `governance.canary_stage_log` row `transition_kind='auto_rollback'` + `from_stage`/`to_stage` + `reason` 詳述 + `metric_snapshot`；觀察期 timer 重置為新 stage。

---

## 6. AMD Wording

**新 amendment AMD-2026-05-10-05** — Graduated Canary Promotion Criteria 寫死：

> §2.2 5-stage 表的 promotion 條件以 §3 spec 定義為**SoT**；§4 healthcheck `[58]` SQL 與 §3 spec 公式 1:1 對應；§4.5 manual_promote Decision Lease 必伴隨 cohort 字段檢查（驗 cohort 與 stage entry cohort 一致）。

land 路徑：`srv/docs/governance_dev/amendments/2026-05-10--AMD-2026-05-10-05-canary-stage-criteria-spec.md`（W5 IMPL phase E1 寫，PA review）。

---

## 7. IMPL Scope

### 7.1 Rust（E1-A）

- `rust/openclaw_engine/src/config/risk.rs` — `ExecutorRiskConfig` 加新 method `is_promote_eligible(stage: u8, metrics: &CanaryStageMetrics) -> PromoteVerdict`
- `rust/openclaw_engine/src/risk_control/canary_promotion.rs` (新檔, ~120 LOC) — 純 logic 對應 §2-§5 公式

### 7.2 Python（E1-B）

- `program_code/.../healthcheck/checks_governance.py` — `[58] check_58_graduated_canary_stage_invariant` 加 §2.2/§3/§4/§5 SQL 對應 `metric_kind='promote_condition'` 與 `metric_kind='rollback_trigger'`
- `program_code/.../shadow_mode_provider.py` — `_evaluate_promote_criteria()` 與 `_evaluate_rollback_criteria()` 兩 helper

### 7.3 PG（E1-C）

- 新 migration `V0XX__governance_canary_stage_metric_seed.sql`（Guard A/B/C + Linux PG dry-run）— INSERT 所有 stage × metric_kind 對應 SQL 到 `governance.canary_stage_metric_registry`（per AMD-2026-05-09-03 §4.2）

### 7.4 Healthcheck addition

`[58]` enrich 加 5 項細粒度檢查：每 cohort × stage 的 `promote_condition_met` (PASS/PENDING/FAIL) + `rollback_trigger_tripped` (true/false) + 各 metric 當前值 + threshold + margin（per §4.3 GUI surface 顯示元素 #2/#3）。

**LOC 估**：Rust ~120 + Python ~80 + SQL ~60 = **~260 LOC + ~80 LOC test**。

---

## 8. Acceptance Criteria

1. `rust/openclaw_engine/src/risk_control/canary_promotion.rs` PromoteVerdict enum (`Promote`, `Pending`, `Fail`, `Demote`) 對應 §2-§5 公式 100%
2. `[58]` healthcheck 跑 cohort 模擬資料 PASS / WARN / FAIL 各 ≥1 case unit test
3. `governance.canary_stage_metric_registry` seed 後 `SELECT COUNT(*) FROM governance.canary_stage_metric_registry WHERE stage IN (1,2,3,4)` ≥ 12 row（每 stage ≥3 metric）
4. `_evaluate_promote_criteria()` Python helper 對 W3 cohort grid_trading × BTCUSDT × demo 跑出 PromoteVerdict 與 `[58]` SQL 結果一致
5. AMD-2026-05-10-05 land + PA + QC + PM sign-off
6. E2 review confirm `boundary_violation_count` 計算與 §2.4 list 7 source 全對齊
7. E4 regression 驗 5 stage transition matrix 全 25 case (5×5)
8. 16 原則 / DOC-08 §12 / 硬邊界 5 項 0 觸碰
9. CLAUDE.md §三 active gates 加 `[58]` 描述 update 反映 promotion criteria 來源指 AMD-2026-05-10-05

---

## 9. Risk + Side Effect

- **與 W3 同窗依賴**：W5 此 spec IMPL 必先 close（spec land + AMD 起草 sign-off），W3 才能進 Stage 1 atomic patch；違反 = W3 IMPL 撞無 SoT
- **Backward compat**：legacy `entry_fills ≥ 10` 字面條件被 §2.2 嚴化為「AND wall_clock ≥ 7d AND boundary=0 AND sample_floor ≥ 72h」— 現有 mock test 若 fake `entry_fills=15` 但 `wall_clock=1h` 將 Pending（pre-spec 為 Promote），E2 必 update
- **Race condition**：cohort 切換瞬間 `stage_entered_at_ms` reset，metric SQL 需用 `WHERE ts >= stage_entered_at_ms` 而非「since cohort active」— 已在 §2.2 SQL 寫死

---

*PA spec for P1-CANARY-STAGE-CRITERIA-1, Sprint N+1 W5*
