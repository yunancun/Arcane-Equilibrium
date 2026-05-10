// MODULE_NOTE
// 模組目的：W5-E1-A P1-CANARY-STAGE-CRITERIA-1 純邏輯模組 — 把 spec
//          `docs/execution_plan/2026-05-10--p1_canary_stage_criteria_1_spec.md`
//          §2-§5 promotion / demote 公式落到 Rust pure-logic eval。`is_promote_eligible`
//          / `is_rollback_tripped` 接收 stage + CanaryStageMetrics snapshot，回 PromoteVerdict。
//
// 上游：W5-E1-B Python `_evaluate_promote_criteria()` 透過 IPC `eval_canary_stage`
//       handler 走 metric snapshot；Rust 側 `executor_config_cache` stage-aware
//       polling 也可呼叫此模組做本地預判。
// 下游：governance hub manual_promote 路徑 + `[58]` healthcheck enrich detail
//       輸出（promote_condition_met / rollback_trigger_tripped）。
//
// 不變量（per AMD-2026-05-09-03 §2.2 表 + spec §2-§5）：
//   - Stage 0 / Stage 4 永不 auto-promote（前者持續 fail-closed，後者 operator
//     拍板）— 任何 stage in (0, 4) 直接回 PromoteVerdict::PendingOperator
//   - Stage 1→2 條件 = (wall_clock ≥ 7d) AND (entry_fills ≥ 10) AND
//                     (boundary_violation_count == 0) AND (sample_floor ≥ 72h)
//   - Stage 2→3 條件 = (wall_clock ≥ 14d) AND (entry_fills ≥ 30) AND
//                     (gross_pnl_usdt > -5.0) AND (DSR > 0.5) AND
//                     (boundary_violation_count == 0) AND (sample_floor ≥ 168h)
//   - Stage 3→4 = ≥21d + gross_pnl > 0 + DSR PASS + PBO ≤ 0.5 +
//                attribution_chain_ok ≥ 0.7 + boundary=0；但回 ReadyForOperatorReview
//                （不 auto-promote），由 GUI surface flip
//   - DSR / PBO / attribution_chain_ok = None → Pending（不 fail，等下次 cycle）
//
// 不適用範圍（per AMD §3）：DOC-08 §12 9 條安全不變量、SM-04 ≥ L3、Live
//   boundary 5-gate、§二 16 原則硬不變式 — 這些由更上層 (Guardian / SM-04 ladder)
//   覆寫此模組輸出，本模組只負責 stage 條件 evaluation；rollback 判斷只看
//   spec §5 列舉之 demote trigger，不做 Live boundary 替代檢查。

use serde::{Deserialize, Serialize};

use crate::config::risk_config::CanaryStage;

// ---------------------------------------------------------------------------
// 觀察期常數（per AMD §2.2 + spec §2-§5）。
// 與 healthcheck `[58]` STAGE_OBSERVATION_PERIOD_MS 對齊。
// ---------------------------------------------------------------------------

/// Stage 1 wall-clock 觀察期 = 7 days。
pub const STAGE1_WALL_CLOCK_MS: i64 = 7 * 24 * 60 * 60 * 1000;
/// Stage 2 wall-clock 觀察期 = 14 days。
pub const STAGE2_WALL_CLOCK_MS: i64 = 14 * 24 * 60 * 60 * 1000;
/// Stage 3 wall-clock 觀察期 = 21 days。
pub const STAGE3_WALL_CLOCK_MS: i64 = 21 * 24 * 60 * 60 * 1000;

/// Stage 1 sample size floor = 72h（spec §2.3 QC HIGH push back 2 推薦下界）。
/// 即使 wall_clock 7d 達且 entry_fills≥10，stage_entered <72h 仍 Pending。
pub const STAGE1_SAMPLE_FLOOR_MS: i64 = 72 * 60 * 60 * 1000;

/// Stage 2 sample size floor = 7d hard floor for demo（spec §3）。
pub const STAGE2_SAMPLE_FLOOR_MS: i64 = 7 * 24 * 60 * 60 * 1000;

// ---------------------------------------------------------------------------
// Promote thresholds（per AMD §2.2 + spec §2-§5）。
// ---------------------------------------------------------------------------

/// Stage 1→2 entry_fills 閾值。
pub const STAGE1_ENTRY_FILLS_MIN: i64 = 10;
/// Stage 2→3 entry_fills 閾值。
pub const STAGE2_ENTRY_FILLS_MIN: i64 = 30;
/// Stage 2→3 gross_pnl 下界（USDT）。
pub const STAGE2_GROSS_PNL_FLOOR_USDT: f64 = -5.0;
/// Stage 2→3 DSR 下界。
pub const STAGE2_DSR_FLOOR: f64 = 0.5;
/// Stage 3→4 attribution chain ok ratio 下界。
pub const STAGE3_ATTRIBUTION_RATIO_FLOOR: f64 = 0.7;
/// Stage 3→4 PBO 上界。
pub const STAGE3_PBO_CEILING: f64 = 0.5;

/// Stage 1→0 demote — gross_pnl 下界（demote at first sign of trouble）。
/// spec §5 表第 1 列：「Stage 1 任一 boundary trip → Stage 0」，沒有 PnL 直接 trigger。
pub const STAGE1_PNL_DEMOTE_FLOOR_USDT: f64 = f64::NEG_INFINITY;

/// Stage 2→1 demote — gross_pnl 下界。
pub const STAGE2_PNL_DEMOTE_FLOOR_USDT: f64 = -10.0;
/// Stage 3→2 demote — gross_pnl 下界。
pub const STAGE3_PNL_DEMOTE_FLOOR_USDT: f64 = -20.0;
/// Stage 3→2 demote — attribution chain ok ratio 下界（低於即 demote）。
pub const STAGE3_ATTRIBUTION_DEMOTE_FLOOR: f64 = 0.3;

// ---------------------------------------------------------------------------
// CanaryStageMetrics — `is_promote_eligible` / `is_rollback_tripped` 輸入快照。
// ---------------------------------------------------------------------------

/// Cohort metric snapshot；由 Python `_evaluate_promote_criteria()` 讀 PG +
/// IPC fetch 後構造，傳給 Rust 端做純邏輯判斷。
///
/// 不變量：
/// - `current_ts_ms` / `stage_entered_at_ms` 都是 ms epoch（i64）
/// - `wall_clock_elapsed_ms` derive from `current_ts_ms - stage_entered_at_ms`
///   （allow caller 提供，用以單元測試 inject）
/// - DSR / PBO / attribution_chain_ok_ratio = None → Pending（等下次 cycle）
/// - boundary_violation_count = 0 才允許 promote；> 0 即 rollback trigger
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CanaryStageMetrics {
    /// 當前 ms epoch（caller 注入 SystemTime，方便測試）。
    pub current_ts_ms: i64,
    /// stage 進入時間 ms epoch（與 ExecutorConfig.stage_entered_at_ms 對齊）。
    pub stage_entered_at_ms: i64,
    /// cohort 內 entry-only fill count（spec §2.2 SQL 排除 reject_governance + exits）。
    pub entry_fills_count: i64,
    /// boundary violation 累計數（per spec §2.4 7 source 任一 trip → +1）。
    pub boundary_violation_count: i64,
    /// gross PnL（USDT，cohort 內全部 fills 累計）。
    pub gross_pnl_usdt: f64,
    /// DSR (Deflated Sharpe Ratio)；None = 樣本不足或 W-AUDIT-6 pipeline 未跑。
    pub dsr: Option<f64>,
    /// PBO (Probability of Backtest Overfitting)；None = pipeline 未跑。
    pub pbo: Option<f64>,
    /// attribution chain ok ratio（[55] healthcheck 同源 metric）；None = 未測。
    pub attribution_chain_ok_ratio: Option<f64>,
    /// SM-04 escalate level（0=normal, 1..=4 escalating）；≥3 = 強制 demote 至 Stage 0。
    pub sm04_level: u8,
}

impl CanaryStageMetrics {
    /// Wall-clock elapsed (ms) 推導；負值 clamp 至 0（防 stage_entered_at_ms 未來時間 race）。
    pub fn wall_clock_elapsed_ms(&self) -> i64 {
        (self.current_ts_ms - self.stage_entered_at_ms).max(0)
    }
}

// ---------------------------------------------------------------------------
// PromoteVerdict — `is_promote_eligible()` 回傳。
// ---------------------------------------------------------------------------

/// Stage promotion 判定結果。
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum PromoteVerdict {
    /// 全部條件 PASS → 允許 promote 至下一 stage。
    Promote,
    /// 部分條件未滿足（wall_clock / sample / metric 未達），等下次 cycle。
    /// `reason` 攜帶人讀說明（GUI surface 顯示）。
    Pending { reason: String },
    /// 在 spec wall-clock floor 後仍未達升級條件 → escalate WARN。
    /// 對 Stage 1 = 14d 仍 entry_fills < 10 / Stage 2 = 後處理同；
    /// 不 auto-demote，operator 拍板。
    Fail { reason: String },
    /// Stage 0 / Stage 4 永不 auto-promote — operator 顯式拍板。
    PendingOperator { reason: String },
    /// Stage 3→4 全條件達成 → 寫 GUI surface「ready_for_stage_4_review」（不 auto-promote）。
    ReadyForOperatorReview { reason: String },
}

/// Stage rollback 判定結果。
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum RollbackVerdict {
    /// 無 rollback trigger trip。
    Stable,
    /// 任一 demote trigger trip → 必 demote 至 spec §5 表指定下一 stage。
    Demote { reason: String, target_stage: CanaryStage },
}

// ---------------------------------------------------------------------------
// 核心 API — `is_promote_eligible` / `is_rollback_tripped`。
// ---------------------------------------------------------------------------

/// 對給定 stage + metric snapshot 評估 promote eligibility。
///
/// 對 Stage 1/2/3 走對應 wall_clock + entry_fills + sample_floor + metric 條件；
/// Stage 0 / Stage 4 直接回 PendingOperator（不 auto-promote per spec §1 + §4）。
pub fn is_promote_eligible(
    stage: CanaryStage,
    metrics: &CanaryStageMetrics,
) -> PromoteVerdict {
    match stage {
        CanaryStage::Stage0 => PromoteVerdict::PendingOperator {
            reason: "Stage 0 fail-closed default; operator must Settings tab toggle to Stage 1 \
                     (spec §1 + AMD §2.2)"
                .to_string(),
        },
        CanaryStage::Stage1 => evaluate_stage1_promote(metrics),
        CanaryStage::Stage2 => evaluate_stage2_promote(metrics),
        CanaryStage::Stage3 => evaluate_stage3_promote(metrics),
        CanaryStage::Stage4 => PromoteVerdict::PendingOperator {
            reason: "Stage 4 LIVE_PENDING; no auto-promote (spec §4 + AMD §2.2 — operator + \
                     signed authorization + Decision Lease + 5-gate live boundary required)"
                .to_string(),
        },
    }
}

/// Stage 1→2 promote eval（per spec §2.1）。
fn evaluate_stage1_promote(metrics: &CanaryStageMetrics) -> PromoteVerdict {
    let elapsed = metrics.wall_clock_elapsed_ms();

    // 14d wall-clock 仍 entry_fills < 10 = Fail（spec §2.5 stage_1_starvation）。
    if elapsed >= 14 * 24 * 60 * 60 * 1000
        && metrics.entry_fills_count < STAGE1_ENTRY_FILLS_MIN
    {
        return PromoteVerdict::Fail {
            reason: format!(
                "Stage 1 starvation: entry_fills={}<{} after wall_clock={}ms (>14d); \
                 operator review required (spec §2.5)",
                metrics.entry_fills_count,
                STAGE1_ENTRY_FILLS_MIN,
                elapsed
            ),
        };
    }

    // boundary_violation_count > 0 = 必 rollback，promote 路徑直接 reject。
    if metrics.boundary_violation_count > 0 {
        return PromoteVerdict::Pending {
            reason: format!(
                "boundary_violation_count={}>0; rollback path active (spec §2.4)",
                metrics.boundary_violation_count
            ),
        };
    }

    if elapsed < STAGE1_WALL_CLOCK_MS {
        return PromoteVerdict::Pending {
            reason: format!(
                "wall_clock={}ms<7d; need {} more ms (spec §2.1)",
                elapsed,
                STAGE1_WALL_CLOCK_MS - elapsed
            ),
        };
    }

    if elapsed < STAGE1_SAMPLE_FLOOR_MS {
        return PromoteVerdict::Pending {
            reason: format!(
                "stage_entered <72h; sample_floor not met (spec §2.3)"
            ),
        };
    }

    if metrics.entry_fills_count < STAGE1_ENTRY_FILLS_MIN {
        return PromoteVerdict::Pending {
            reason: format!(
                "entry_fills={}<{}; need more cohort fills (spec §2.1)",
                metrics.entry_fills_count, STAGE1_ENTRY_FILLS_MIN
            ),
        };
    }

    PromoteVerdict::Promote
}

/// Stage 2→3 promote eval（per spec §3）。
fn evaluate_stage2_promote(metrics: &CanaryStageMetrics) -> PromoteVerdict {
    let elapsed = metrics.wall_clock_elapsed_ms();

    // 28d 仍未達升級條件 = Fail。
    if elapsed >= 28 * 24 * 60 * 60 * 1000
        && (metrics.entry_fills_count < STAGE2_ENTRY_FILLS_MIN
            || metrics.gross_pnl_usdt <= STAGE2_GROSS_PNL_FLOOR_USDT)
    {
        return PromoteVerdict::Fail {
            reason: format!(
                "Stage 2 starvation: entry_fills={} gross_pnl={} after wall_clock={}ms (>28d); \
                 operator review required (spec §3)",
                metrics.entry_fills_count, metrics.gross_pnl_usdt, elapsed
            ),
        };
    }

    if metrics.boundary_violation_count > 0 {
        return PromoteVerdict::Pending {
            reason: format!(
                "boundary_violation_count={}>0; rollback path active (spec §3)",
                metrics.boundary_violation_count
            ),
        };
    }

    if elapsed < STAGE2_WALL_CLOCK_MS {
        return PromoteVerdict::Pending {
            reason: format!(
                "wall_clock={}ms<14d; need {} more ms (spec §3)",
                elapsed,
                STAGE2_WALL_CLOCK_MS - elapsed
            ),
        };
    }

    if elapsed < STAGE2_SAMPLE_FLOOR_MS {
        return PromoteVerdict::Pending {
            reason: "stage_entered <168h(7d); sample_floor not met (spec §3)".to_string(),
        };
    }

    if metrics.entry_fills_count < STAGE2_ENTRY_FILLS_MIN {
        return PromoteVerdict::Pending {
            reason: format!(
                "entry_fills={}<{}; need more cohort fills (spec §3)",
                metrics.entry_fills_count, STAGE2_ENTRY_FILLS_MIN
            ),
        };
    }

    if metrics.gross_pnl_usdt <= STAGE2_GROSS_PNL_FLOOR_USDT {
        return PromoteVerdict::Pending {
            reason: format!(
                "gross_pnl={}USDT<={}USDT (spec §3 floor)",
                metrics.gross_pnl_usdt, STAGE2_GROSS_PNL_FLOOR_USDT
            ),
        };
    }

    // DSR None → Pending（不 fail，等下次 cycle）— spec §3 explicit。
    let dsr = match metrics.dsr {
        Some(v) => v,
        None => {
            return PromoteVerdict::Pending {
                reason: "DSR=None; W-AUDIT-6 pipeline not yet computed (spec §3 PROMOTE PENDING)"
                    .to_string(),
            };
        }
    };

    if dsr <= STAGE2_DSR_FLOOR {
        return PromoteVerdict::Pending {
            reason: format!(
                "DSR={}<={} (spec §3 floor)",
                dsr, STAGE2_DSR_FLOOR
            ),
        };
    }

    PromoteVerdict::Promote
}

/// Stage 3→4 promote eval（per spec §4）。
/// spec §4 明示 Stage 4 不 auto-promote — 即使全條件達成也只回 ReadyForOperatorReview。
fn evaluate_stage3_promote(metrics: &CanaryStageMetrics) -> PromoteVerdict {
    let elapsed = metrics.wall_clock_elapsed_ms();

    if metrics.boundary_violation_count > 0 {
        return PromoteVerdict::Pending {
            reason: format!(
                "boundary_violation_count={}>0; rollback path active (spec §4)",
                metrics.boundary_violation_count
            ),
        };
    }

    if elapsed < STAGE3_WALL_CLOCK_MS {
        return PromoteVerdict::Pending {
            reason: format!(
                "wall_clock={}ms<21d; need {} more ms (spec §4)",
                elapsed,
                STAGE3_WALL_CLOCK_MS - elapsed
            ),
        };
    }

    if metrics.gross_pnl_usdt <= 0.0 {
        return PromoteVerdict::Pending {
            reason: format!(
                "gross_pnl={}USDT<=0 (spec §4 must be strictly positive)",
                metrics.gross_pnl_usdt
            ),
        };
    }

    let dsr = match metrics.dsr {
        Some(v) => v,
        None => {
            return PromoteVerdict::Pending {
                reason: "DSR=None; W-AUDIT-6 pipeline not yet computed (spec §4 PASS required)"
                    .to_string(),
            };
        }
    };

    if dsr <= 0.0 {
        return PromoteVerdict::Pending {
            reason: format!("DSR={}<=0; spec §4 requires DSR PASS", dsr),
        };
    }

    let pbo = match metrics.pbo {
        Some(v) => v,
        None => {
            return PromoteVerdict::Pending {
                reason: "PBO=None; W-AUDIT-6 pipeline not yet computed (spec §4)".to_string(),
            };
        }
    };

    if pbo > STAGE3_PBO_CEILING {
        return PromoteVerdict::Pending {
            reason: format!(
                "PBO={}>{} (spec §4 ceiling)",
                pbo, STAGE3_PBO_CEILING
            ),
        };
    }

    let attr = match metrics.attribution_chain_ok_ratio {
        Some(v) => v,
        None => {
            return PromoteVerdict::Pending {
                reason: "attribution_chain_ok_ratio=None; [55] healthcheck not yet computed \
                         (spec §4)"
                    .to_string(),
            };
        }
    };

    if attr < STAGE3_ATTRIBUTION_RATIO_FLOOR {
        return PromoteVerdict::Pending {
            reason: format!(
                "attribution_chain_ok_ratio={}<{} (spec §4 floor)",
                attr, STAGE3_ATTRIBUTION_RATIO_FLOOR
            ),
        };
    }

    // 全條件達成 — 但 spec §4 明示 Stage 4 不 auto-promote，回 ready 信號給 GUI。
    PromoteVerdict::ReadyForOperatorReview {
        reason: format!(
            "Stage 3→4 all criteria met (wall_clock={}ms gross_pnl={}USDT DSR={} PBO={} \
             attribution_chain_ok={}); GUI surface 'ready_for_stage_4_review' awaiting \
             operator + signed authorization + Decision Lease + 5-gate live boundary \
             (spec §4 + AMD §2.2)",
            elapsed, metrics.gross_pnl_usdt, dsr, pbo, attr
        ),
    }
}

/// 對給定 stage + metric snapshot 評估是否 demote。
///
/// per spec §5 表：每 stage 列舉 OR-trigger，任一 trip 即 fall back 1 stage（Stage 4 直回 0）。
pub fn is_rollback_tripped(
    stage: CanaryStage,
    metrics: &CanaryStageMetrics,
) -> RollbackVerdict {
    // SM-04 ≥ L3 跨 stage hard demote 至 Stage 0（per AMD §3.2 + spec §2.4 第 3 條）。
    if metrics.sm04_level >= 3 {
        return RollbackVerdict::Demote {
            reason: format!(
                "SM-04 escalate level={}>=3; demote across all cohorts to Stage 0 \
                 (AMD §3.2 + spec §2.4)",
                metrics.sm04_level
            ),
            target_stage: CanaryStage::Stage0,
        };
    }

    match stage {
        CanaryStage::Stage0 => RollbackVerdict::Stable,
        CanaryStage::Stage1 => evaluate_stage1_rollback(metrics),
        CanaryStage::Stage2 => evaluate_stage2_rollback(metrics),
        CanaryStage::Stage3 => evaluate_stage3_rollback(metrics),
        CanaryStage::Stage4 => evaluate_stage4_rollback(metrics),
    }
}

/// Stage 1→0 rollback eval（per spec §5 第 1 列）。
fn evaluate_stage1_rollback(metrics: &CanaryStageMetrics) -> RollbackVerdict {
    if metrics.boundary_violation_count > 0 {
        return RollbackVerdict::Demote {
            reason: format!(
                "boundary_violation_count={}>0; demote Stage 1→0 (spec §5)",
                metrics.boundary_violation_count
            ),
            target_stage: CanaryStage::Stage0,
        };
    }
    RollbackVerdict::Stable
}

/// Stage 2→1 rollback eval（per spec §5 第 2 列）。
fn evaluate_stage2_rollback(metrics: &CanaryStageMetrics) -> RollbackVerdict {
    if metrics.gross_pnl_usdt < STAGE2_PNL_DEMOTE_FLOOR_USDT {
        return RollbackVerdict::Demote {
            reason: format!(
                "gross_pnl={}USDT<{}USDT; demote Stage 2→1 (spec §5)",
                metrics.gross_pnl_usdt, STAGE2_PNL_DEMOTE_FLOOR_USDT
            ),
            target_stage: CanaryStage::Stage1,
        };
    }
    if let Some(dsr) = metrics.dsr {
        if dsr < 0.0 {
            return RollbackVerdict::Demote {
                reason: format!("DSR={}<0; demote Stage 2→1 (spec §5)", dsr),
                target_stage: CanaryStage::Stage1,
            };
        }
    }
    if metrics.boundary_violation_count > 0 {
        return RollbackVerdict::Demote {
            reason: format!(
                "boundary_violation_count={}>0; demote Stage 2→1 (spec §5 — Stage 1 trigger \
                 cascading)",
                metrics.boundary_violation_count
            ),
            target_stage: CanaryStage::Stage1,
        };
    }
    RollbackVerdict::Stable
}

/// Stage 3→2 rollback eval（per spec §5 第 3 列）。
fn evaluate_stage3_rollback(metrics: &CanaryStageMetrics) -> RollbackVerdict {
    if metrics.gross_pnl_usdt < STAGE3_PNL_DEMOTE_FLOOR_USDT {
        return RollbackVerdict::Demote {
            reason: format!(
                "gross_pnl={}USDT<{}USDT; demote Stage 3→2 (spec §5)",
                metrics.gross_pnl_usdt, STAGE3_PNL_DEMOTE_FLOOR_USDT
            ),
            target_stage: CanaryStage::Stage2,
        };
    }
    if let Some(dsr) = metrics.dsr {
        if dsr < 0.0 {
            return RollbackVerdict::Demote {
                reason: format!("DSR={}<0; demote Stage 3→2 (spec §5)", dsr),
                target_stage: CanaryStage::Stage2,
            };
        }
    }
    if let Some(attr) = metrics.attribution_chain_ok_ratio {
        if attr < STAGE3_ATTRIBUTION_DEMOTE_FLOOR {
            return RollbackVerdict::Demote {
                reason: format!(
                    "attribution_chain_ok_ratio={}<{}; demote Stage 3→2 (spec §5)",
                    attr, STAGE3_ATTRIBUTION_DEMOTE_FLOOR
                ),
                target_stage: CanaryStage::Stage2,
            };
        }
    }
    RollbackVerdict::Stable
}

/// Stage 4→0 rollback eval（per spec §5 第 4 列；任一 boundary 失敗 = Stage 0）。
fn evaluate_stage4_rollback(metrics: &CanaryStageMetrics) -> RollbackVerdict {
    if metrics.boundary_violation_count > 0 {
        return RollbackVerdict::Demote {
            reason: format!(
                "boundary_violation_count={}>0; Stage 4 cancel_token shutdown — demote 4→0 \
                 (spec §5)",
                metrics.boundary_violation_count
            ),
            target_stage: CanaryStage::Stage0,
        };
    }
    RollbackVerdict::Stable
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    /// Helper：產生一個 baseline metric snapshot（全部達升級條件）。
    fn happy_metrics(stage_entered_at_ms: i64) -> CanaryStageMetrics {
        CanaryStageMetrics {
            current_ts_ms: stage_entered_at_ms + 30 * 24 * 60 * 60 * 1000, // +30d
            stage_entered_at_ms,
            entry_fills_count: 50,
            boundary_violation_count: 0,
            gross_pnl_usdt: 5.0,
            dsr: Some(1.5),
            pbo: Some(0.2),
            attribution_chain_ok_ratio: Some(0.9),
            sm04_level: 0,
        }
    }

    // ── Stage 0 / Stage 4 永不 auto-promote ──

    #[test]
    fn stage0_never_auto_promote() {
        let m = happy_metrics(0);
        match is_promote_eligible(CanaryStage::Stage0, &m) {
            PromoteVerdict::PendingOperator { .. } => {}
            other => panic!("Stage 0 must PendingOperator, got {:?}", other),
        }
    }

    #[test]
    fn stage4_never_auto_promote_even_if_perfect() {
        let m = happy_metrics(0);
        match is_promote_eligible(CanaryStage::Stage4, &m) {
            PromoteVerdict::PendingOperator { .. } => {}
            other => panic!("Stage 4 must PendingOperator, got {:?}", other),
        }
    }

    // ── Stage 1→2 promote ──

    #[test]
    fn stage1_promote_happy_path() {
        let m = happy_metrics(0);
        assert_eq!(is_promote_eligible(CanaryStage::Stage1, &m), PromoteVerdict::Promote);
    }

    #[test]
    fn stage1_pending_when_wall_clock_short() {
        let mut m = happy_metrics(0);
        m.current_ts_ms = 6 * 24 * 60 * 60 * 1000; // 6d only
        match is_promote_eligible(CanaryStage::Stage1, &m) {
            PromoteVerdict::Pending { reason } => {
                assert!(reason.contains("wall_clock"), "reason={}", reason);
            }
            other => panic!("expected Pending, got {:?}", other),
        }
    }

    #[test]
    fn stage1_pending_when_sample_floor_short() {
        // wall_clock 7d 達但 sample_floor 72h — 用「stage_entered = 8d ago，但
        // current_ts_ms - stage_entered = 7d」這種 inconsistent state 不存在；
        // 真正 sample_floor 失敗 = wall_clock 7d 後但因為時間 race / cohort
        // 切換 reset 後實際 elapsed < 72h。
        // 用「current=72h-1ms 後」來測 — 但 wall_clock 也只 72h-1ms < 7d
        // 必先 wall_clock fail。實務上 sample_floor 是 72h、wall_clock 7d=168h，
        // sample_floor 永遠先達；這裡用 mocked metric 證明 elapsed=72h-1 時仍 Pending。
        let mut m = happy_metrics(0);
        m.current_ts_ms = 71 * 60 * 60 * 1000; // 71h (< 72h sample_floor 也 < 7d)
        match is_promote_eligible(CanaryStage::Stage1, &m) {
            PromoteVerdict::Pending { .. } => {} // wall_clock 先 fail，Pending 即可
            other => panic!("expected Pending, got {:?}", other),
        }
    }

    #[test]
    fn stage1_pending_when_entry_fills_short() {
        let mut m = happy_metrics(0);
        // 用 8d wall_clock（>7d 過了 promote 閾值，但 <14d 未撞 starvation Fail）
        m.current_ts_ms = 8 * 24 * 60 * 60 * 1000;
        m.entry_fills_count = 5; // < 10
        match is_promote_eligible(CanaryStage::Stage1, &m) {
            PromoteVerdict::Pending { reason } => {
                assert!(reason.contains("entry_fills"), "reason={}", reason);
            }
            other => panic!("expected Pending, got {:?}", other),
        }
    }

    #[test]
    fn stage1_pending_when_boundary_violation() {
        let mut m = happy_metrics(0);
        m.boundary_violation_count = 1;
        match is_promote_eligible(CanaryStage::Stage1, &m) {
            PromoteVerdict::Pending { reason } => {
                assert!(reason.contains("boundary"), "reason={}", reason);
            }
            other => panic!("expected Pending, got {:?}", other),
        }
    }

    #[test]
    fn stage1_fail_after_14d_low_fills() {
        let mut m = happy_metrics(0);
        m.current_ts_ms = 15 * 24 * 60 * 60 * 1000; // 15d
        m.entry_fills_count = 5; // < 10
        match is_promote_eligible(CanaryStage::Stage1, &m) {
            PromoteVerdict::Fail { reason } => {
                assert!(reason.contains("starvation"), "reason={}", reason);
            }
            other => panic!("expected Fail (stage_1_starvation), got {:?}", other),
        }
    }

    // ── Stage 2→3 promote ──

    #[test]
    fn stage2_promote_happy_path() {
        let m = happy_metrics(0);
        assert_eq!(is_promote_eligible(CanaryStage::Stage2, &m), PromoteVerdict::Promote);
    }

    #[test]
    fn stage2_pending_when_dsr_none() {
        let mut m = happy_metrics(0);
        m.dsr = None;
        match is_promote_eligible(CanaryStage::Stage2, &m) {
            PromoteVerdict::Pending { reason } => {
                assert!(reason.contains("DSR"), "reason={}", reason);
            }
            other => panic!("expected Pending(DSR=None), got {:?}", other),
        }
    }

    #[test]
    fn stage2_pending_when_dsr_low() {
        let mut m = happy_metrics(0);
        m.dsr = Some(0.3); // < 0.5 floor
        match is_promote_eligible(CanaryStage::Stage2, &m) {
            PromoteVerdict::Pending { reason } => {
                assert!(reason.contains("DSR"), "reason={}", reason);
            }
            other => panic!("expected Pending(DSR low), got {:?}", other),
        }
    }

    #[test]
    fn stage2_pending_when_pnl_at_floor() {
        let mut m = happy_metrics(0);
        // 用 15d wall_clock（>14d 過了 promote 閾值，但 <28d 未撞 starvation Fail）
        m.current_ts_ms = 15 * 24 * 60 * 60 * 1000;
        m.gross_pnl_usdt = -5.0; // == floor，spec § floor 是 strict > -5
        match is_promote_eligible(CanaryStage::Stage2, &m) {
            PromoteVerdict::Pending { reason } => {
                assert!(reason.contains("gross_pnl"), "reason={}", reason);
            }
            other => panic!("expected Pending(pnl floor), got {:?}", other),
        }
    }

    // ── Stage 3→4 ReadyForOperatorReview ──

    #[test]
    fn stage3_ready_for_operator_review_when_perfect() {
        let m = happy_metrics(0);
        match is_promote_eligible(CanaryStage::Stage3, &m) {
            PromoteVerdict::ReadyForOperatorReview { reason } => {
                assert!(reason.contains("Stage 3→4"), "reason={}", reason);
            }
            other => panic!("expected ReadyForOperatorReview, got {:?}", other),
        }
    }

    #[test]
    fn stage3_pending_when_attribution_low() {
        let mut m = happy_metrics(0);
        m.attribution_chain_ok_ratio = Some(0.5); // < 0.7 floor
        match is_promote_eligible(CanaryStage::Stage3, &m) {
            PromoteVerdict::Pending { reason } => {
                assert!(reason.contains("attribution"), "reason={}", reason);
            }
            other => panic!("expected Pending(attribution low), got {:?}", other),
        }
    }

    #[test]
    fn stage3_pending_when_pbo_high() {
        let mut m = happy_metrics(0);
        m.pbo = Some(0.7); // > 0.5 ceiling
        match is_promote_eligible(CanaryStage::Stage3, &m) {
            PromoteVerdict::Pending { reason } => {
                assert!(reason.contains("PBO"), "reason={}", reason);
            }
            other => panic!("expected Pending(PBO high), got {:?}", other),
        }
    }

    // ── Rollback paths ──

    #[test]
    fn rollback_stable_when_metrics_healthy() {
        let m = happy_metrics(0);
        for stage in [
            CanaryStage::Stage1,
            CanaryStage::Stage2,
            CanaryStage::Stage3,
        ] {
            assert_eq!(is_rollback_tripped(stage, &m), RollbackVerdict::Stable);
        }
    }

    #[test]
    fn rollback_sm04_l3_demotes_to_stage0_across_all() {
        let mut m = happy_metrics(0);
        m.sm04_level = 3;
        for stage in [
            CanaryStage::Stage1,
            CanaryStage::Stage2,
            CanaryStage::Stage3,
            CanaryStage::Stage4,
        ] {
            match is_rollback_tripped(stage, &m) {
                RollbackVerdict::Demote {
                    target_stage: CanaryStage::Stage0,
                    reason,
                } => {
                    assert!(reason.contains("SM-04"), "reason={}", reason);
                }
                other => panic!("expected SM-04 demote→Stage 0 from {:?}, got {:?}", stage, other),
            }
        }
    }

    #[test]
    fn rollback_stage1_boundary_violation_demotes_to_0() {
        let mut m = happy_metrics(0);
        m.boundary_violation_count = 2;
        match is_rollback_tripped(CanaryStage::Stage1, &m) {
            RollbackVerdict::Demote {
                target_stage: CanaryStage::Stage0,
                ..
            } => {}
            other => panic!("expected Stage 1→0 demote, got {:?}", other),
        }
    }

    #[test]
    fn rollback_stage2_pnl_lt_minus_10_demotes_to_1() {
        let mut m = happy_metrics(0);
        m.gross_pnl_usdt = -15.0;
        match is_rollback_tripped(CanaryStage::Stage2, &m) {
            RollbackVerdict::Demote {
                target_stage: CanaryStage::Stage1,
                reason,
            } => {
                assert!(reason.contains("gross_pnl"), "reason={}", reason);
            }
            other => panic!("expected Stage 2→1 demote, got {:?}", other),
        }
    }

    #[test]
    fn rollback_stage2_dsr_negative_demotes_to_1() {
        let mut m = happy_metrics(0);
        m.dsr = Some(-0.5);
        match is_rollback_tripped(CanaryStage::Stage2, &m) {
            RollbackVerdict::Demote {
                target_stage: CanaryStage::Stage1,
                ..
            } => {}
            other => panic!("expected Stage 2→1 demote, got {:?}", other),
        }
    }

    #[test]
    fn rollback_stage3_pnl_lt_minus_20_demotes_to_2() {
        let mut m = happy_metrics(0);
        m.gross_pnl_usdt = -25.0;
        match is_rollback_tripped(CanaryStage::Stage3, &m) {
            RollbackVerdict::Demote {
                target_stage: CanaryStage::Stage2,
                ..
            } => {}
            other => panic!("expected Stage 3→2 demote, got {:?}", other),
        }
    }

    #[test]
    fn rollback_stage3_attribution_lt_03_demotes_to_2() {
        let mut m = happy_metrics(0);
        m.attribution_chain_ok_ratio = Some(0.2);
        match is_rollback_tripped(CanaryStage::Stage3, &m) {
            RollbackVerdict::Demote {
                target_stage: CanaryStage::Stage2,
                reason,
            } => {
                assert!(reason.contains("attribution"), "reason={}", reason);
            }
            other => panic!("expected Stage 3→2 demote, got {:?}", other),
        }
    }

    #[test]
    fn rollback_stage4_boundary_demotes_to_0() {
        let mut m = happy_metrics(0);
        m.boundary_violation_count = 1;
        match is_rollback_tripped(CanaryStage::Stage4, &m) {
            RollbackVerdict::Demote {
                target_stage: CanaryStage::Stage0,
                ..
            } => {}
            other => panic!("expected Stage 4→0 demote, got {:?}", other),
        }
    }

    // ── Helper ──

    #[test]
    fn wall_clock_clamp_at_zero_for_negative_skew() {
        let m = CanaryStageMetrics {
            current_ts_ms: 100,
            stage_entered_at_ms: 1000, // future > current (clock skew)
            ..happy_metrics(0)
        };
        assert_eq!(m.wall_clock_elapsed_ms(), 0);
    }
}
