//! Runtime evaluation loop for `strategist_scheduler`.
//! `strategist_scheduler` 的 runtime 評估迴圈。
//!
//! MODULE_NOTE (EN): Extracted from parent `mod.rs` by G5-08. This sibling owns
//! the five-minute runtime loop, metrics SQL, parameter IPC helpers, and the
//! `PairMetrics` DTO. Public `PairMetrics` is re-exported by `mod.rs` to keep
//! existing paths stable.
//! MODULE_NOTE (中): G5-08 從父 `mod.rs` 抽出。本 sibling 負責五分鐘 runtime
//! loop、metrics SQL、參數 IPC helper 與 `PairMetrics` DTO；`mod.rs` re-export
//! 保持外部路徑不變。

use super::{validate_recommendation_with_reason, StrategistScheduler};
use crate::strategies::ParamRange;
use crate::tick_pipeline::{PipelineCommand, PipelineKind};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::sync::atomic::Ordering;
use std::sync::Arc;
use std::time::Duration;
use tracing::{debug, error, info, warn};

const MAX_EVALS_PER_CYCLE: usize = 10;
const MIN_SAMPLE_COUNT: i64 = 30;
const NORMAL_INTERVAL: Duration = Duration::from_secs(300);
const NORMAL_PARAM_DELTA_SKILL_PCT: f64 = 0.30;

/// Per-strategy×symbol aggregated metrics from fills table.
/// 來自 fills 表的逐策略×symbol 聚合指標。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PairMetrics {
    pub strategy_name: String,
    pub symbol: String,
    pub fill_count: i64,
    pub avg_pnl: f64,
    pub win_rate: f64,
}

impl PairMetrics {
    /// Absolute deviation from target (higher = more in need of tuning).
    /// 與目標的絕對偏差（越高越需要調參）。
    pub fn deviation_score(&self) -> f64 {
        // Combine negative PnL and low win rate into a single score.
        // Win rate target = 0.5 (break-even), PnL target = 0.0.
        // 合併負 PnL 和低勝率為單一分數。
        let pnl_dev = self.avg_pnl.abs();
        let wr_dev = (self.win_rate - 0.5).abs() * 100.0; // scale to comparable range
        pnl_dev + wr_dev
    }
}

impl StrategistScheduler {
    /// Run the scheduler forever (until cancelled). Spawn via tokio::spawn.
    /// 永久運行排程器（直到取消）。通過 tokio::spawn 啟動。
    pub async fn run_forever(self: Arc<Self>) {
        info!(
            tune_target = ?self.tune_target,
            has_promote_channel = self.has_promote_channel(),
            "StrategistScheduler started (5-min cycle) / 策略師排程器已啟動（5 分鐘週期）",
        );

        loop {
            tokio::select! {
                _ = self.cancel.cancelled() => {
                    info!("StrategistScheduler cancelled / 策略師排程器已取消");
                    return;
                }
                _ = tokio::time::sleep(self.current_interval()) => {
                    // Run evaluation cycle / 執行評估週期
                }
            }

            match self.evaluate_cycle().await {
                Ok(evaluated) => {
                    self.consecutive_failures.store(0, Ordering::Relaxed);
                    debug!(
                        pairs_evaluated = evaluated,
                        "StrategistScheduler cycle complete / 評估週期完成"
                    );
                }
                Err(e) => {
                    let fails = self.consecutive_failures.fetch_add(1, Ordering::Relaxed) + 1;
                    error!(
                        consecutive_failures = fails,
                        error = %e,
                        "StrategistScheduler cycle failed / 評估週期失敗"
                    );
                }
            }

            // G3-11: stamp `last_cycle_ts_ms` on every iteration (Ok or Err)
            // so healthcheck `[16] strategist_cycle_fresh` can detect a wedged
            // scheduler even when AI service is down.
            // G3-11：每輪（無論成敗）更新 last_cycle_ts_ms 給 healthcheck 觀察。
            let now_ms = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_millis() as u64)
                .unwrap_or(0);
            self.cycle_counters.record_cycle_finish(now_ms);
        }
    }

    /// Compute current sleep interval with exponential backoff (R4-2).
    /// 計算當前睡眠間隔（含指數退避）。
    pub(super) fn current_interval(&self) -> Duration {
        let fails = self.consecutive_failures.load(Ordering::Relaxed);
        match fails {
            0 => NORMAL_INTERVAL,             // 5 min
            1 => Duration::from_secs(1_800),  // 30 min
            2 => Duration::from_secs(3_600),  // 60 min
            _ => Duration::from_secs(14_400), // 4h cap
        }
    }

    /// Single evaluation cycle: gather metrics → rank → evaluate → validate → apply.
    /// 單次評估週期：收集指標 → 排名 → 評估 → 驗證 → 應用。
    async fn evaluate_cycle(&self) -> Result<usize, Box<dyn std::error::Error + Send + Sync>> {
        // 1. Gather per-strategy×symbol metrics via DB query (R4-6, R5-3, R5-4)
        // 1. 通過 DB 查詢收集逐策略×symbol 指標
        let metrics = self.gather_strategy_metrics().await?;
        if metrics.is_empty() {
            debug!("no strategy metrics available (DB empty or unavailable) / 無策略指標");
            return Ok(0);
        }

        // 2. Rank by deviation and select top-N pairs (R2 H-5)
        // 2. 按偏差排名並選取 top-N 交易對
        let top_pairs = rank_by_deviation(&metrics);

        // 3. For each pair: fetch current params → IPC with context → validate → apply
        // 3. 對每個交易對：獲取當前參數 → 帶上下文 IPC → 驗證 → 應用
        let mut applied = 0usize;
        for pair in top_pairs.iter().take(MAX_EVALS_PER_CYCLE) {
            // 3a. Fetch current params + ranges BEFORE IPC (B3: context for Python AI)
            // 3a. IPC 前獲取當前參數 + 範圍（B3：為 Python AI 提供上下文）
            let (current_json, ranges_json) =
                match self.fetch_current_params(&pair.strategy_name).await {
                    Ok(v) => v,
                    Err(e) => {
                        warn!(
                            strategy = %pair.strategy_name,
                            error = %e,
                            "fetch_current_params failed, skipping pair / 獲取參數失敗，跳過"
                        );
                        continue;
                    }
                };

            // 3b. Serialize ranges for Python (B3: param_ranges in IPC payload)
            // 3b. 為 Python 序列化範圍（B3：IPC 負載中的 param_ranges）
            let ranges_value: Value =
                serde_json::to_value(&ranges_json).unwrap_or_else(|_| Value::Array(vec![]));

            let max_delta_pct = self.current_max_param_delta_pct();
            let params =
                build_strategist_eval_payload(pair, &current_json, ranges_value, max_delta_pct);

            let response = match self.ai_client.request("strategist_evaluate", params).await {
                Some(r) => r,
                None => {
                    // IPC failure — counted as cycle failure
                    // IPC 失敗 — 計為週期失敗
                    self.cycle_counters.record_reject("ipc_failed");
                    return Err("AI service IPC failed for strategist_evaluate".into());
                }
            };

            // 4. Validate recommendation against ranges, delta, weight sum.
            //    STRATEGIST-TUNE-TARGET-CONFIG-1: delta cap pulled from the
            //    RiskConfig store snapshot (or 0.30 fallback when no store wired).
            //    G3-11: every reject path tags a stable reason → CycleCounters
            //    `reject_by_reason` map → IPC `get_strategist_cycle_metrics`.
            // 4. 根據範圍、delta、權重總和驗證建議；delta cap 從 RiskConfig 取（缺 store=0.50）。
            //    G3-11：每條拒絕路徑都打 stable reason tag 到 CycleCounters。
            match validate_recommendation_with_reason(
                &response,
                &current_json,
                &ranges_json,
                max_delta_pct,
            ) {
                Ok(()) => {
                    // 5. Apply via PipelineCommand
                    // 5. 通過 PipelineCommand 應用
                    if let Err(e) = self.apply_params(&pair.strategy_name, &response).await {
                        warn!(
                            strategy = %pair.strategy_name,
                            error = %e,
                            "param apply failed / 參數應用失敗"
                        );
                        self.cycle_counters.record_reject("apply_failed");
                    } else {
                        info!(
                            strategy = %pair.strategy_name,
                            symbol = %pair.symbol,
                            "strategist params applied / 策略師參數已應用"
                        );
                        applied += 1;
                        let now_ms = std::time::SystemTime::now()
                            .duration_since(std::time::UNIX_EPOCH)
                            .map(|d| d.as_millis() as u64)
                            .unwrap_or(0);
                        self.cycle_counters.record_apply(now_ms);

                        // STRATEGIST-PARAMS-PERSIST-1 (2026-04-23): write audit row
                        // so engine restart restores tuned params instead of reverting
                        // to TOML baseline. Fail-soft: DB error → warn log + continue
                        // (tuning cycle still succeeded in-memory).
                        // STRATEGIST-PARAMS-PERSIST-1：寫 audit row，engine restart
                        // 恢復調諧參數而非 TOML baseline。Fail-soft：DB 錯誤僅 warn log，
                        // 不影響內存 tuning cycle。
                        if let Err(e) = self
                            .persist_applied_params(
                                &pair.strategy_name,
                                &current_json,
                                &response,
                                "top_deviation_pair",
                            )
                            .await
                        {
                            warn!(
                                strategy = %pair.strategy_name,
                                error = %e,
                                "persist_applied_params failed (fail-soft) / 持久化失敗（容錯跳過）"
                            );
                        }
                    }
                }
                Err(reason) => {
                    debug!(
                        strategy = %pair.strategy_name,
                        symbol = %pair.symbol,
                        reason = reason,
                        "recommendation rejected by validation / 建議被驗證拒絕"
                    );
                    self.cycle_counters.record_reject(reason);
                }
            }
        }

        Ok(applied)
    }

    /// Query fills table for per-strategy×symbol aggregated metrics (R4-6, R5-3, R5-4).
    /// 查詢 fills 表獲取逐策略×symbol 聚合指標。
    async fn gather_strategy_metrics(
        &self,
    ) -> Result<Vec<PairMetrics>, Box<dyn std::error::Error + Send + Sync>> {
        let pool = match self.db_pool.get() {
            Some(p) => p,
            None => {
                debug!("DB pool unavailable — skipping metrics / DB 連接池不可用");
                return Ok(vec![]);
            }
        };

        // R5-3: column names are ts, strategy_name (not created_at, strategy)
        // R5-4: HAVING count(*) >= 30 — skip low-fill pairs
        // STRATEGIST-SCHED-CLOSE-FILTER-1 (2026-04-23 EDGE-DIAG-1 RCA byproduct):
        // `trading.fills.strategy_name` mixes entry strategies
        // (grid_trading / ma_crossover / bb_* / funding_arb) with close-path
        // reasons (`risk_close:*` / `strategy_close:*` / `ipc_close*`). Pre-fix
        // the scheduler took the unfiltered DISTINCT set and called
        // `fetch_current_params(strategy=<entire reason string>)` for each →
        // `channel closed` error spam in engine.log every 5 min, masking real
        // failures. Three NOT LIKE prefixes cover all known close paths
        // (risk_checks.rs format!("risk_close:{}",) / strategy emit
        // `strategy_close:{tag}` / IPC close handler `ipc_close_symbol` /
        // `ipc_close:{tag}`).
        //
        // STRATEGIST-SCHED-CHANNEL-PAPER-ORPHAN-1 (2026-04-23): additional
        // `engine_mode = $2` filter aligns metrics source with `tune_target`.
        // Pre-fix the SQL was cross-engine (paper + demo + live_demo + live
        // mixed), which was incoherent in the Phase 5+ "Demo trains, Live
        // receives promoted params" architecture — if scheduler tunes Demo
        // engine, it should learn from Demo fills only (otherwise live_demo
        // behaviour pollutes demo tuning signal). Paper is tolerated in the
        // filter as a value even though the enum rejects it in `new()` — the
        // `db_mode()` string goes through as-is with no special-casing.
        // R5-3：列名為 ts, strategy_name（非 created_at, strategy）
        // R5-4：HAVING count(*) >= 30 — 跳過低成交對
        // STRATEGIST-SCHED-CLOSE-FILTER-1（EDGE-DIAG-1 副產品 2026-04-23）：
        // `trading.fills.strategy_name` 混合入場策略與三類 close-path reasons；
        // 修復前 scheduler 把整段 reason 當策略名 IPC 致每 5min 噴 channel-closed
        // WARN，掩蓋真正失敗。三條 NOT LIKE 涵蓋已知 close prefix。
        //
        // STRATEGIST-SCHED-CHANNEL-PAPER-ORPHAN-1（2026-04-23）：新增
        // `engine_mode = $2` filter 對齊 tune_target。原跨引擎 SQL 在
        // 「Demo 訓練、Live 受促升」架構下不合理 — 調 Demo 就該只學 Demo。
        //
        // FA-1 (2026-04-23 review follow-up): Live tune path NOT yet supported.
        // `PipelineKind::Live.db_mode() == "live"` but real LiveDemo fills write
        // `engine_mode = "live_demo"` (see memory/project_engine_mode_tag_live_demo.md
        // + mode_state.rs::effective_engine_mode). A single-value `= $2` filter
        // would silently miss 95%+ of Live-endpoint fills. Phase 5+
        // STRATEGIST-TUNE-TARGET-CONFIG-1 must widen this to
        // `engine_mode IN ('live','live_demo','live_testnet')` when enabling
        // Live tune. Until then, fail-fast at first real use (Demo only).
        // FA-1：Live tune 路徑尚未支援。db_mode() 回 "live" 但真 LiveDemo fills
        // 的 engine_mode = "live_demo"；單值 filter 會靜默丟 95%+ 資料。
        // Phase 5+ STRATEGIST-TUNE-TARGET-CONFIG-1 必須擴為 IN 多值。
        if !matches!(self.tune_target, PipelineKind::Demo) {
            return Err(format!(
                "STRATEGIST-SCHED gather_strategy_metrics: tune_target={:?} not supported \
                 in release builds — Live metrics require multi-mode filters and operator \
                 acceptance criteria before enabling",
                self.tune_target
            )
            .into());
        }
        let tune_mode = self.tune_target.db_mode();
        let rows = sqlx::query_as::<_, PairMetricsRow>(
            r#"
            SELECT
                strategy_name,
                symbol,
                count(*)::bigint AS fill_count,
                coalesce(avg(realized_pnl), 0.0)::float8 AS avg_pnl,
                coalesce(
                    sum(CASE WHEN realized_pnl > 0 THEN 1 ELSE 0 END)::float8
                    / nullif(count(*), 0)::float8,
                    0.0
                ) AS win_rate
            FROM trading.fills
            WHERE ts > now() - interval '7 days'
              AND engine_mode = $2
              AND strategy_name IS NOT NULL
              AND strategy_name NOT LIKE 'risk_close:%'
              AND strategy_name NOT LIKE 'strategy_close:%'
              AND strategy_name NOT LIKE 'ipc_close%'
            GROUP BY strategy_name, symbol
            HAVING count(*) >= $1
            ORDER BY avg_pnl ASC
            "#,
        )
        .bind(MIN_SAMPLE_COUNT)
        .bind(tune_mode)
        .fetch_all(pool)
        .await?;

        Ok(rows
            .into_iter()
            .map(|r| PairMetrics {
                strategy_name: r.strategy_name,
                symbol: r.symbol,
                fill_count: r.fill_count,
                avg_pnl: r.avg_pnl,
                win_rate: r.win_rate,
            })
            .collect())
    }

    /// Fetch current params + ranges for a strategy via PipelineCommand.
    /// 通過 PipelineCommand 獲取策略的當前參數和範圍。
    ///
    /// WP-13-LEFTOVER-1 (2026-05-16, FA-P1-11 補修)：3 處 `self.tune_cmd_tx`
    /// 直接呼叫改為 `self.tune_cmd_snapshot()`，每呼叫從 slot 讀最新 sender
    /// （生產路徑）或退回 owned（測試 / 直接呼叫）。詳 mod.rs 文檔。
    async fn fetch_current_params(
        &self,
        strategy_name: &str,
    ) -> Result<(Value, Vec<ParamRange>), Box<dyn std::error::Error + Send + Sync>> {
        // Get current params / 獲取當前參數
        let (params_tx, params_rx) = tokio::sync::oneshot::channel();
        self.tune_cmd_snapshot()
            .send(PipelineCommand::GetStrategyParams {
                strategy_name: strategy_name.to_string(),
                response_tx: params_tx,
            })?;
        let params_str = params_rx.await??;
        let current: Value = serde_json::from_str(&params_str)?;

        // Get param ranges / 獲取參數範圍
        let (ranges_tx, ranges_rx) = tokio::sync::oneshot::channel();
        self.tune_cmd_snapshot()
            .send(PipelineCommand::GetParamRanges {
                strategy_name: strategy_name.to_string(),
                response_tx: ranges_tx,
            })?;
        let ranges_str = ranges_rx.await??;
        let ranges: Vec<ParamRange> = serde_json::from_str(&ranges_str)?;

        Ok((current, ranges))
    }

    /// Apply validated params via PipelineCommand::UpdateStrategyParams.
    /// 通過 PipelineCommand::UpdateStrategyParams 應用已驗證的參數。
    async fn apply_params(
        &self,
        strategy_name: &str,
        recommendation: &Value,
    ) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
        let params_json = serde_json::to_string(recommendation)?;
        let (tx, rx) = tokio::sync::oneshot::channel();
        self.tune_cmd_snapshot()
            .send(PipelineCommand::UpdateStrategyParams {
                strategy_name: strategy_name.to_string(),
                params_json,
                response_tx: tx,
            })?;
        rx.await??;
        Ok(())
    }
}

fn build_strategist_eval_payload(
    pair: &PairMetrics,
    current_json: &Value,
    ranges_value: Value,
    max_delta_pct: f64,
) -> Value {
    serde_json::json!({
        "intel": {
            "symbol": &pair.symbol,
            "strategy": &pair.strategy_name,
            "win_rate": pair.win_rate,
            "avg_pnl": pair.avg_pnl,
            "fill_count": pair.fill_count,
        },
        // TODO(WP-04): 提取到 [strategist] TOML config — 目前硬編碼 l1_9b
        "model_tier": "l1_9b",
        "current_params": current_json,
        "param_ranges": ranges_value,
        "strategist_skill": {
            "name": "wide_parameter_adjustment",
            "normal_delta_pct": NORMAL_PARAM_DELTA_SKILL_PCT,
            "max_delta_pct": max_delta_pct,
            "description": "Use <=30% as the normal working range; use 30%-max only as a deliberate wide adjustment skill when evidence is poor enough to justify a larger move."
        }
    })
}

/// Rank pairs by deviation score, descending (worst-performing first).
/// 按偏差分數降序排名（表現最差的優先）。
pub(super) fn rank_by_deviation(metrics: &[PairMetrics]) -> Vec<&PairMetrics> {
    let mut ranked: Vec<&PairMetrics> = metrics.iter().collect();
    ranked.sort_by(|a, b| {
        b.deviation_score()
            .partial_cmp(&a.deviation_score())
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    ranked
}

/// sqlx row type for fills aggregation query.
/// fills 聚合查詢的 sqlx 行類型。
#[derive(sqlx::FromRow)]
struct PairMetricsRow {
    strategy_name: String,
    symbol: String,
    fill_count: i64,
    avg_pnl: f64,
    win_rate: f64,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_build_strategist_eval_payload_includes_wide_adjustment_skill() {
        let pair = PairMetrics {
            strategy_name: "ma_crossover".to_string(),
            symbol: "BTCUSDT".to_string(),
            fill_count: 42,
            avg_pnl: -1.25,
            win_rate: 0.31,
        };
        let current = serde_json::json!({"cooldown_ms": 100_000});
        let ranges = serde_json::json!([
            {
                "name": "cooldown_ms",
                "min": 1_000,
                "max": 1_000_000,
                "agent_adjustable": true
            }
        ]);

        let payload = build_strategist_eval_payload(&pair, &current, ranges, 0.50);

        assert_eq!(
            payload["strategist_skill"]["name"],
            "wide_parameter_adjustment"
        );
        assert_eq!(payload["strategist_skill"]["normal_delta_pct"], 0.30);
        assert_eq!(payload["strategist_skill"]["max_delta_pct"], 0.50);
        assert_eq!(payload["intel"]["fill_count"], 42);
        assert_eq!(payload["current_params"]["cooldown_ms"], 100_000);
    }
}
