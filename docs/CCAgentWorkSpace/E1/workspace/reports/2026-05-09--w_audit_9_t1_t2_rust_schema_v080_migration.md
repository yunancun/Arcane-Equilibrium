# W-AUDIT-9 T1+T2 — Rust Schema + V080 Migration (E1-A)

**Sprint**：N+0 Day 0-3
**Owner**：E1-A（this Mac CC instance）
**Source amendment**：`docs/governance_dev/amendments/2026-05-09--AMD-2026-05-09-03-graduated-canary-default.md`
**Local commit**：`094f9914`（unpushed — multi-session race rule）
**Date**：2026-05-09

---

## 1. 任務摘要 / Task Summary

W-AUDIT-9（Graduated Canary Foundation）兩個前置 sub-task 連續邏輯一個 E1 連做：

- **T1 Rust schema 升級**：把 `ExecutorConfig` 從 binary `shadow_mode: bool` 升級為 5-stage graduated canary（Stage 0 shadow / Stage 1 paper / Stage 2 demo / Stage 3 demo full / Stage 4 live pending），保 backward-compat projection
- **T2 V080 migration**：落 `governance.canary_stage_log` + `governance.canary_stage_metric_registry` 兩 audit table，含 Guard A/B/C + Linux PG dry-run

目的（per AMD §1.2-1.3）：解決 P0-EDGE-1 雞生蛋蛋生雞死循環 — 把 fail-closed 從 binary 邊界改為 stage 邊界，evidence 可在 stage 內 SLA 觀察期收集。

---

## 2. 修改清單 / Files Changed

| 檔 | 性質 | LOC delta |
|---|---|---|
| `rust/openclaw_engine/src/config/risk_config_advanced.rs` | M | +363 / -37 |
| `rust/openclaw_engine/src/config/risk_config.rs` | M | +6 / -3 |
| `rust/openclaw_engine/src/config/risk_config_tests.rs` | M | +360 / -7 |
| `sql/migrations/V080__governance_canary_stage.sql` | A | +386 |
| `tests/migrations/test_v080_governance_canary_stage.py` | A | +213 |
| `docs/CCAgentWorkSpace/E1/memory.md` | M | +49 (T1+T2 lesson entry) |
| **總計** | 6 檔 | **+1374 / -34** |

未碰 sibling sub-agent 範圍（intent_processor / tick_pipeline / decision_feature_evaluation_writer / V082 / 4 個 risk_config*.toml）— 守 multi-session race 守則。

---

## 3. 關鍵 Diff / Key Diffs

### 3.1 ExecutorConfig 升級（risk_config_advanced.rs）

```rust
pub struct ExecutorConfig {
    // legacy backward-compat projection（Stage 0 ⇄ true, Stage 1+ ⇄ false）
    pub shadow_mode: bool,
    pub max_position_pct: f64,
    pub per_symbol_position_cap: HashMap<String, f64>,
    // ── W-AUDIT-9 (AMD-2026-05-09-03) graduated canary 5-stage 升級 ──
    pub canary_stage: CanaryStage,                // Stage 0..=4
    pub canary_cohort: Option<CanaryCohort>,      // Stage 1/2 cohort scope
    pub stage_entered_at_ms: i64,                 // ms epoch
    pub observation_period_ms: u64,               // Stage 1=7d/2=14d/3=21d
}

#[derive(Serialize, Deserialize)]
#[serde(try_from = "u8", into = "u8")]
pub enum CanaryStage { Stage0, Stage1, Stage2, Stage3, Stage4 }

impl CanaryStage {
    pub fn as_shadow_mode(self) -> bool {
        matches!(self, CanaryStage::Stage0)
    }
}

pub struct CanaryCohort {
    pub strategy: String,
    pub symbol: String,
    pub environment: String,  // 'paper' | 'demo' | 'live_demo' | 'mainnet'
}
```

### 3.2 validate() 8 條 invariant

```rust
// AMD-2026-05-09-03 §4.4：legacy shadow_mode == projection 不變量
let projected_shadow = self.canary_stage.as_shadow_mode();
if self.shadow_mode != projected_shadow {
    return Err(format!(
        "risk.executor: shadow_mode={} inconsistent with canary_stage={} ...",
        self.shadow_mode, self.canary_stage.as_u8()
    ));
}

// AMD §2.2 Stage 1/2 必 1×1×env cohort
match self.canary_stage {
    CanaryStage::Stage0 => { /* cohort=None / ts=0 / period=0 */ }
    CanaryStage::Stage1 | CanaryStage::Stage2 => {
        let cohort = self.canary_cohort.as_ref().ok_or_else(...)?;
        // strategy + symbol + environment 必 match Stage 1=paper / Stage 2=demo
        // stage_entered_at_ms > 0 + observation_period_ms > 0
    }
    CanaryStage::Stage3 => { /* cohort=None / ts > 0 / period > 0 */ }
    CanaryStage::Stage4 => { /* cohort=None / ts > 0 / observation N/A */ }
}
```

### 3.3 V080 — manual_promote NOT NULL constraint（E2 audit point #2）

```sql
CONSTRAINT canary_stage_log_manual_promote_lease_required_chk
    CHECK (
        transition_kind != 'manual_promote'
        OR decision_lease_id IS NOT NULL
    )
```

PG 層強制 — Linux empirical query 驗證 `INSERT ... transition_kind='manual_promote' decision_lease_id=NULL` → REJECTED with `check_violation`.

### 3.4 V080 — UNIQUE active partial index

```sql
CREATE UNIQUE INDEX IF NOT EXISTS uq_canary_stage_metric_registry_active
    ON governance.canary_stage_metric_registry (stage, metric_name)
    WHERE active = TRUE;
```

PG 慣用 partial unique — 同一 (stage, metric_name) drift 偵測；audit-soft-delete 友好（active=false 保留歷史不違反 unique）。

---

## 4. 治理對照 / Governance Alignment

| AMD §/規範 | 落地 |
|---|---|
| AMD-2026-05-09-03 §2.1（5-stage 升級） | ✅ CanaryStage enum + CanaryCohort struct |
| AMD §2.2（每 stage 觀察期 + cohort 規範） | ✅ validate() 8 條 invariant |
| AMD §2.3（demo Stage 1 default after T1-T7 land） | ✅ schema 落地；TOML default 不變（Stage 0）|
| AMD §3.4（§二 16 原則合規）| ✅ Stage 0 fail-closed default + serde(default) backward-compat |
| AMD §4.2（PG 持久化 V### migration）| ✅ V080 governance.canary_stage_log + canary_stage_metric_registry |
| AMD §4.4（Rust schema 升級）| ✅ ExecutorConfig + 4 新欄位 |
| AMD §4.5（Decision Lease）| ✅ manual_promote 必伴 decision_lease_id（PG CHECK constraint）|
| AMD §7 audit point #1（_read_shadow_mode 不變量）| ✅ Rust validate()：shadow_mode != projection = reject |
| AMD §7 audit point #2（manual_promote NOT NULL PG-layer）| ✅ V080 CHECK constraint（不只 application 層）|
| CLAUDE.md §七 Guard A/B/C | ✅ Guard A×2（兩 table）+ Guard C×1（hot-path index ordering）|
| CLAUDE.md §七 Linux PG dry-run mandatory | ✅ ssh trade-core docker exec psql -f V080.sql empirical PASS |
| `feedback_v_migration_pg_dry_run.md` | ✅ Mac mock pytest 21/21 + Linux PG empirical 雙 layer 驗證 |
| `feedback_chinese_only_comments.md`（2026-05-05）| ✅ 新注釋默認中文；既有中英對照不主動清 |
| Multi-session race rule（`feedback_git_commit_only_for_metadoc.md`）| ✅ 只 commit 自己 5+1 檔；sibling intent_processor/V082 留 unstaged 給 sibling |

---

## 5. Verification Results

### 5.1 Rust unit tests

```
cargo test --lib -p openclaw_engine config::risk_config
test result: ok. 139 passed; 0 failed; 0 ignored; 2464 filtered out
```

新增 14 個 W-AUDIT-9 tests + 1 個既有 round-trip test 升級至 Stage 1 cohort + 1 個 real TOML files parse test。完整列表：

- `test_canary_stage_default_is_stage0`
- `test_canary_stage_serde_round_trip_stage0`
- `test_canary_stage_serde_round_trip_stage1_demo`
- `test_canary_stage_backward_compat_shadow_mode_projection`
- `test_canary_stage_inconsistent_shadow_mode_rejected`
- `test_canary_stage_stage1_without_cohort_rejected`
- `test_canary_stage_stage1_wrong_environment_rejected`
- `test_canary_stage_stage2_demo_cohort_passes`
- `test_canary_stage_stage3_demo_full_universe_passes`
- `test_canary_stage_stage3_with_cohort_rejected`
- `test_canary_stage_stage4_live_pending_passes`
- `test_canary_stage_invalid_integer_rejected`
- `test_canary_stage_stage0_with_nonzero_timestamp_rejected`
- `test_canary_cohort_empty_strategy_rejected`
- `test_canary_cohort_invalid_environment_rejected`
- `test_canary_stage_legacy_toml_without_canary_fields_works`（backward-compat）
- `test_w_audit_9_real_toml_files_parse_with_default_stage_zero`（4 個真 TOML 檔）
- `test_g3_02_executor_toml_roundtrip`（升級 Stage 1 paper cohort）

### 5.2 V080 mock pytest

```
pytest tests/migrations/test_v080_governance_canary_stage.py
21 passed in 0.02s
```

涵蓋 Guard A/B/C / idempotency / E2 audit point #2 / 不變量 / no-destructive-ops。

### 5.3 Linux PG empirical dry-run（ssh trade-core docker exec）

```
First apply (CREATE):  CREATE SCHEMA / CREATE TABLE×2 / CREATE INDEX×3 / DO×3 OK
Second apply (idempotent):  全部 NOTICE skip / 無 RAISE
Manual promote NULL lease:  REJECTED with check_violation
Manual promote with lease:  ACCEPTED
Auto promote NULL lease:  ACCEPTED
Stage=5 out-of-range:  REJECTED with check_violation
Cleanup:  DROP TABLE governance.canary_stage_{log,metric_registry} → tables_count=0
```

**DB 已回到 V080-未-apply 狀態**，per task spec「不 apply DB」。

### 5.4 Cargo build status

- **First run（在 sibling B-M1 partial commit 之前）**：`cargo build --release` 通過（27 個編譯單元 OK + 17 個無關 warning）
- **後 sibling 200188ad commit**：sibling 加 `decision_feature_evaluation_tx` 欄位但 `intent_processor/mod.rs` 還沒同步 → cargo build E0063 break。**不在 E1-A 責任範圍**，sibling sub-agent 完成 B-M1 IMPL 後自然修復。

---

## 6. 不確定之處 / Uncertainties

1. **Sibling B-M1 partial state**：sibling sub-agent 並行做的 V082 + decision_feature_evaluation_writer.rs + intent_processor/mod.rs 修改在我 IMPL 期間半完成，導致 release build 暫時 break。我**沒做任何**這些檔的修改 — 等 sibling 完成自身 commit 後 build 自然恢復。如 sibling 過程出錯需 PM 協調，但 T1+T2 自身已綠。
2. **W-AUDIT-9 T3 已完成（commit `200188ad`）**：sibling E1-C 的 Python `executor_config_cache.py` + `executor_agent.py` 升級已 commit 但 Mac/Linux 還沒 push。**T3 IPC schema 必與我的 T1 Rust schema 對齊** — 兩者均用 `canary_stage` 整數 0..=4 + `canary_cohort` (strategy/symbol/environment)。手動對齊驗證已在 T3 commit 訊息確認。E2 review 應 cross-check Rust serde + Python parse 一致性。
3. **healthcheck `[58]` 還沒 IMPL**：T4（E1-D）依賴 T2 完。我已在 V080 SQL/test 為 `[58]` 留好 hot-path index（cohort + created_at_ms DESC）+ schema invariant，T4 IMPL 時可直接用。
4. **GUI surface（T5）+ Decision Lease（T6）+ E4 regression（T7）**：尚未開工。T1+T2 land 後 T3-T7 可 parallel。

---

## 7. Operator 下一步 / Operator Next Steps

| # | 動作 | Owner |
|---|---|---|
| 1 | E2 review T1+T2（重點 audit 3 點 per AMD §7）：(a) shadow_mode 一致性 invariant；(b) PG-layer manual_promote NOT NULL CHECK；(c) Guard A/C 是否覆蓋所有 hot-path | E2 |
| 2 | E2 cross-check T1（Rust）+ T3（Python）IPC schema 對齊 — `canary_stage` 整數 0..=4 / `canary_cohort` 三欄位 | E2 |
| 3 | E4 regression：5-stage transition E2E test + auto-rollback metric trip + SM-04 ≥ L3 + healthcheck [58] PASS | E4 |
| 4 | PM 統一 push origin：T1+T2 commit `094f9914` + T3 commit `200188ad` + T6 commit `063f12d0` + sibling B-M1 完成後 commit | PM |
| 5 | Linux deploy：`OPENCLAW_AUTO_MIGRATE=1 bash helper_scripts/restart_all.sh --keep-auth --rebuild` 後驗 V080 真正 apply（檢 `_sqlx_migrations` row + `governance.canary_stage_log` 表存在）| operator |
| 6 | T4 healthcheck `[58]` IMPL（E1-D）→ T5 GUI surface（E1-E）→ T7 E4 regression | E1-D / E1-E / E4 |

---

## 8. Sign-off

E1-A IMPLEMENTATION DONE：T1（Rust schema）+ T2（V080 migration）皆完成。

- Local commit：`094f9914`（**unpushed**，per multi-session race rule）
- Cargo test：139 passed / 0 failed
- V080 mock pytest：21 passed
- Linux PG empirical dry-run：idempotent ×2 + 3 個 invariant test 全通過 + cleanup verified

**待 E2 審查 → E4 回歸 → PM 統一 push origin。**
