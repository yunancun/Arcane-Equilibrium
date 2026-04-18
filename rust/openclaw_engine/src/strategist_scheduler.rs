//! Strategist periodic configurator — Rust-side tokio background task (R3-1).
//! 策略師定時配置器 — Rust 側 tokio 後台任務。
//!
//! MODULE_NOTE (EN): Single-instance scheduler (R3-1 fix: moved from Python FastAPI to
//!   Rust engine — uvicorn --workers=4 would create 4 racing schedulers). Every 5 min:
//!   1) Query fills table for per-strategy×symbol metrics (R4-6, R5-3, R5-4)
//!   2) Rank top-10 pairs by absolute deviation from target (R2 H-5)
//!   3) IPC call to Python ai_service.sock → strategist_evaluate (judge_edge via Ollama)
//!   4) Validate response: param_ranges bounds + weight sum=65±0.1 + delta ≤±30% (R3-4)
//!   5) Apply via PipelineCommand::UpdateStrategyParams
//!   Exponential backoff on IPC failure: 5m→30m→60m→4h cap (R4-2).
//!   Fail-closed: any error → skip cycle, retain current params.
//! MODULE_NOTE (中): 單實例排程器（R3-1 修復：從 Python FastAPI 移至 Rust 引擎——
//!   uvicorn --workers=4 會創建 4 個競爭排程器）。每 5 分鐘：
//!   1) 查詢 fills 表獲取逐策略×symbol 指標
//!   2) 按偏差排名取 top-10
//!   3) IPC 調用 Python ai_service.sock → strategist_evaluate
//!   4) 驗證回應：param_ranges 範圍 + weight sum=65 + delta ≤±30%
//!   5) 通過 PipelineCommand::UpdateStrategyParams 應用
//!   IPC 失敗指數退避：5m→30m→60m→4h 上限。

use crate::ai_service_client::AiServiceClient;
use crate::strategies::ParamRange;
use crate::tick_pipeline::PipelineCommand;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::mpsc::UnboundedSender;
use tokio_util::sync::CancellationToken;
use tracing::{debug, error, info, warn};

/// Maximum pairs to evaluate per cycle (R2 H-5: top-10, not all 96).
/// 每輪評估的最大交易對數（R2 H-5：top-10，非全部 96）。
const MAX_EVALS_PER_CYCLE: usize = 10;

/// Maximum delta allowed for param updates (R3-4: ±30%).
/// 參數更新允許的最大 delta（R3-4：±30%）。
const MAX_PARAM_DELTA_PCT: f64 = 0.30;

/// Weight sum target for confluence weights (65-point scale).
/// 匯合權重目標總和（65 分制）。
const WEIGHT_SUM_TARGET: f64 = 65.0;

/// Weight sum tolerance / 權重總和容差
const WEIGHT_SUM_TOLERANCE: f64 = 0.1;

/// Minimum fills required for a pair to be evaluated (R5-4).
/// 交易對被評估所需的最少成交數（R5-4）。
const MIN_SAMPLE_COUNT: i64 = 30;

/// Normal cycle interval / 正常輪詢間隔
const NORMAL_INTERVAL: Duration = Duration::from_secs(300); // 5 min

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

/// Strategist scheduler configuration / 策略師排程器配置
pub struct StrategistScheduler {
    /// AI service IPC client / AI 服務 IPC 客戶端
    ai_client: Arc<AiServiceClient>,
    /// Pipeline command sender (paper — primary tuning target).
    /// 管線命令發送器（paper — 主要調參目標）。
    cmd_tx: UnboundedSender<PipelineCommand>,
    /// Database pool for fills query / 用於 fills 查詢的資料庫連接池
    db_pool: Arc<crate::database::pool::DbPool>,
    /// Consecutive IPC failure counter for exponential backoff (R4-2).
    /// IPC 連續失敗計數器，用於指數退避。
    consecutive_failures: AtomicU32,
    /// Cancellation token for graceful shutdown / 優雅關閉的取消令牌
    cancel: CancellationToken,
}

impl StrategistScheduler {
    /// Create a new scheduler. Does NOT start the background task.
    /// 創建新排程器。不啟動後台任務。
    pub fn new(
        ai_client: Arc<AiServiceClient>,
        cmd_tx: UnboundedSender<PipelineCommand>,
        db_pool: Arc<crate::database::pool::DbPool>,
        cancel: CancellationToken,
    ) -> Self {
        Self {
            ai_client,
            cmd_tx,
            db_pool,
            consecutive_failures: AtomicU32::new(0),
            cancel,
        }
    }

    /// Run the scheduler forever (until cancelled). Spawn via tokio::spawn.
    /// 永久運行排程器（直到取消）。通過 tokio::spawn 啟動。
    pub async fn run_forever(self: Arc<Self>) {
        info!("StrategistScheduler started (5-min cycle) / 策略師排程器已啟動（5 分鐘週期）");

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
        }
    }

    /// Compute current sleep interval with exponential backoff (R4-2).
    /// 計算當前睡眠間隔（含指數退避）。
    fn current_interval(&self) -> Duration {
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

            let params = serde_json::json!({
                "intel": {
                    "symbol": pair.symbol,
                    "strategy": pair.strategy_name,
                    "win_rate": pair.win_rate,
                    "avg_pnl": pair.avg_pnl,
                    "fill_count": pair.fill_count,
                },
                "model_tier": "l1_9b",
                "current_params": current_json,
                "param_ranges": ranges_value,
            });

            let response = match self.ai_client.request("strategist_evaluate", params).await {
                Some(r) => r,
                None => {
                    // IPC failure — counted as cycle failure
                    // IPC 失敗 — 計為週期失敗
                    return Err("AI service IPC failed for strategist_evaluate".into());
                }
            };

            // 4. Validate recommendation against ranges, delta, weight sum
            // 4. 根據範圍、delta、權重總和驗證建議
            if validate_recommendation(&response, &current_json, &ranges_json) {
                // 5. Apply via PipelineCommand
                // 5. 通過 PipelineCommand 應用
                if let Err(e) = self.apply_params(&pair.strategy_name, &response).await {
                    warn!(
                        strategy = %pair.strategy_name,
                        error = %e,
                        "param apply failed / 參數應用失敗"
                    );
                } else {
                    info!(
                        strategy = %pair.strategy_name,
                        symbol = %pair.symbol,
                        "strategist params applied / 策略師參數已應用"
                    );
                    applied += 1;
                }
            } else {
                debug!(
                    strategy = %pair.strategy_name,
                    symbol = %pair.symbol,
                    "recommendation rejected by validation / 建議被驗證拒絕"
                );
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
        // R5-3：列名為 ts, strategy_name（非 created_at, strategy）
        // R5-4：HAVING count(*) >= 30 — 跳過低成交對
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
              AND strategy_name IS NOT NULL
            GROUP BY strategy_name, symbol
            HAVING count(*) >= $1
            ORDER BY avg_pnl ASC
            "#,
        )
        .bind(MIN_SAMPLE_COUNT)
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
    async fn fetch_current_params(
        &self,
        strategy_name: &str,
    ) -> Result<(Value, Vec<ParamRange>), Box<dyn std::error::Error + Send + Sync>> {
        // Get current params / 獲取當前參數
        let (params_tx, params_rx) = tokio::sync::oneshot::channel();
        self.cmd_tx.send(PipelineCommand::GetStrategyParams {
            strategy_name: strategy_name.to_string(),
            response_tx: params_tx,
        })?;
        let params_str = params_rx.await??;
        let current: Value = serde_json::from_str(&params_str)?;

        // Get param ranges / 獲取參數範圍
        let (ranges_tx, ranges_rx) = tokio::sync::oneshot::channel();
        self.cmd_tx.send(PipelineCommand::GetParamRanges {
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
        self.cmd_tx.send(PipelineCommand::UpdateStrategyParams {
            strategy_name: strategy_name.to_string(),
            params_json,
            response_tx: tx,
        })?;
        rx.await??;
        Ok(())
    }
}

/// Rank pairs by deviation score, descending (worst-performing first).
/// 按偏差分數降序排名（表現最差的優先）。
fn rank_by_deviation(metrics: &[PairMetrics]) -> Vec<&PairMetrics> {
    let mut ranked: Vec<&PairMetrics> = metrics.iter().collect();
    ranked.sort_by(|a, b| {
        b.deviation_score()
            .partial_cmp(&a.deviation_score())
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    ranked
}

/// Validate a Strategist recommendation against param ranges, weight sum, and delta cap.
/// 根據參數範圍、權重總和和 delta 上限驗證策略師建議。
///
/// R3-4: Weight params (weight_adx, weight_regime, weight_volume, weight_momentum)
/// are exempt from the ±30% delta cap — the weight_sum=65 validation is sufficient.
/// R3-4：權重參數免除 ±30% delta 上限 — weight_sum=65 驗證已足夠。
pub fn validate_recommendation(
    recommendation: &Value,
    current_params: &Value,
    param_ranges: &[ParamRange],
) -> bool {
    let rec_obj = match recommendation.as_object() {
        Some(o) => o,
        None => {
            warn!("recommendation is not a JSON object / 建議不是 JSON 物件");
            return false;
        }
    };

    // Weight params exempt from delta cap (R3-4)
    // 權重參數免除 delta 上限
    let weight_param_names: &[&str] = &[
        "weight_adx",
        "weight_regime",
        "weight_volume",
        "weight_momentum",
    ];

    // Track weight sum for validation / 追蹤權重總和以驗證
    let mut weight_sum: f64 = 0.0;
    let mut has_weight_params = false;

    for range in param_ranges {
        if !range.agent_adjustable {
            continue;
        }
        let name = &range.name;
        let new_val = match rec_obj.get(name).and_then(|v| v.as_f64()) {
            Some(v) => v,
            None => continue, // param not in recommendation — keep current / 未在建議中 — 保留當前
        };

        // Range check / 範圍檢查
        if new_val < range.min || new_val > range.max {
            warn!(
                param = %name,
                value = new_val,
                min = range.min,
                max = range.max,
                "recommendation out of range / 建議超出範圍"
            );
            return false;
        }

        // Delta check (weight params exempt — R3-4)
        // Delta 檢查（權重參數免除）
        let is_weight = weight_param_names.contains(&name.as_str());
        if is_weight {
            weight_sum += new_val;
            has_weight_params = true;
        } else if let Some(cur_val) = current_params.get(name).and_then(|v| v.as_f64()) {
            if cur_val.abs() > f64::EPSILON {
                let delta_pct = ((new_val - cur_val) / cur_val).abs();
                if delta_pct > MAX_PARAM_DELTA_PCT {
                    warn!(
                        param = %name,
                        current = cur_val,
                        proposed = new_val,
                        delta_pct = format!("{:.1}%", delta_pct * 100.0),
                        "delta exceeds ±30% cap / delta 超過 ±30% 上限"
                    );
                    return false;
                }
            }
        }
    }

    // Weight sum check: must equal 65 ± 0.1 (if any weight params present)
    // 權重總和檢查：必須等於 65 ± 0.1（如果有權重參數）
    if has_weight_params && (weight_sum - WEIGHT_SUM_TARGET).abs() > WEIGHT_SUM_TOLERANCE {
        warn!(
            weight_sum,
            target = WEIGHT_SUM_TARGET,
            "weight sum out of tolerance / 權重總和超出容差"
        );
        return false;
    }

    true
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

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pair_metrics_deviation_score() {
        let m = PairMetrics {
            strategy_name: "ma_crossover".into(),
            symbol: "BTCUSDT".into(),
            fill_count: 100,
            avg_pnl: -0.5,
            win_rate: 0.3,
        };
        // pnl_dev = 0.5, wr_dev = |0.3-0.5|*100 = 20.0
        let score = m.deviation_score();
        assert!((score - 20.5).abs() < 0.01);
    }

    #[test]
    fn test_rank_by_deviation() {
        let metrics = vec![
            PairMetrics {
                strategy_name: "a".into(),
                symbol: "BTC".into(),
                fill_count: 50,
                avg_pnl: -0.1,
                win_rate: 0.48,
            },
            PairMetrics {
                strategy_name: "b".into(),
                symbol: "ETH".into(),
                fill_count: 50,
                avg_pnl: -2.0,
                win_rate: 0.2,
            },
        ];
        let ranked = rank_by_deviation(&metrics);
        assert_eq!(ranked[0].strategy_name, "b"); // worse deviation
    }

    #[test]
    fn test_validate_recommendation_passes_valid() {
        let rec = serde_json::json!({
            "cooldown_ms": 55000.0,
            "adx_threshold": 22.0,
        });
        let current = serde_json::json!({
            "cooldown_ms": 50000.0,
            "adx_threshold": 20.0,
        });
        let ranges = vec![
            ParamRange {
                name: "cooldown_ms".into(),
                min: 10000.0,
                max: 120000.0,
                step: Some(1000.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "adx_threshold".into(),
                min: 10.0,
                max: 40.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
        ];
        assert!(validate_recommendation(&rec, &current, &ranges));
    }

    #[test]
    fn test_validate_recommendation_rejects_out_of_range() {
        let rec = serde_json::json!({
            "cooldown_ms": 200000.0,  // above max 120000
        });
        let current = serde_json::json!({
            "cooldown_ms": 50000.0,
        });
        let ranges = vec![ParamRange {
            name: "cooldown_ms".into(),
            min: 10000.0,
            max: 120000.0,
            step: Some(1000.0),
            agent_adjustable: true,
            db_persisted: true,
        }];
        assert!(!validate_recommendation(&rec, &current, &ranges));
    }

    #[test]
    fn test_validate_recommendation_rejects_excessive_delta() {
        let rec = serde_json::json!({
            "cooldown_ms": 100000.0,  // +100% from 50000 > ±30%
        });
        let current = serde_json::json!({
            "cooldown_ms": 50000.0,
        });
        let ranges = vec![ParamRange {
            name: "cooldown_ms".into(),
            min: 10000.0,
            max: 120000.0,
            step: Some(1000.0),
            agent_adjustable: true,
            db_persisted: true,
        }];
        assert!(!validate_recommendation(&rec, &current, &ranges));
    }

    #[test]
    fn test_validate_recommendation_weight_params_exempt_from_delta() {
        // Weight params can change by any amount as long as sum = 65
        // 權重參數可以任意變化，只要總和 = 65
        let rec = serde_json::json!({
            "weight_adx": 30.0,      // was 25, +20% (would fail non-weight delta)
            "weight_regime": 15.0,   // was 20, -25%
            "weight_volume": 12.0,
            "weight_momentum": 8.0,  // sum = 65
        });
        let current = serde_json::json!({
            "weight_adx": 25.0,
            "weight_regime": 20.0,
            "weight_volume": 12.0,
            "weight_momentum": 8.0,
        });
        let ranges = vec![
            ParamRange {
                name: "weight_adx".into(),
                min: 0.0,
                max: 65.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "weight_regime".into(),
                min: 0.0,
                max: 65.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "weight_volume".into(),
                min: 0.0,
                max: 65.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "weight_momentum".into(),
                min: 0.0,
                max: 65.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
        ];
        assert!(validate_recommendation(&rec, &current, &ranges));
    }

    #[test]
    fn test_validate_recommendation_rejects_bad_weight_sum() {
        let rec = serde_json::json!({
            "weight_adx": 30.0,
            "weight_regime": 20.0,
            "weight_volume": 12.0,
            "weight_momentum": 8.0,  // sum = 70, not 65
        });
        let current = serde_json::json!({});
        let ranges = vec![
            ParamRange {
                name: "weight_adx".into(),
                min: 0.0,
                max: 65.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "weight_regime".into(),
                min: 0.0,
                max: 65.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "weight_volume".into(),
                min: 0.0,
                max: 65.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "weight_momentum".into(),
                min: 0.0,
                max: 65.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
        ];
        assert!(!validate_recommendation(&rec, &current, &ranges));
    }

    #[test]
    fn test_validate_recommendation_non_adjustable_skipped() {
        // Non-adjustable params in recommendation should be ignored
        // 不可調參數在建議中應被忽略
        let rec = serde_json::json!({
            "active": true,  // not agent_adjustable
            "cooldown_ms": 55000.0,
        });
        let current = serde_json::json!({
            "active": true,
            "cooldown_ms": 50000.0,
        });
        let ranges = vec![
            ParamRange {
                name: "active".into(),
                min: 0.0,
                max: 1.0,
                step: Some(1.0),
                agent_adjustable: false,
                db_persisted: false,
            },
            ParamRange {
                name: "cooldown_ms".into(),
                min: 10000.0,
                max: 120000.0,
                step: Some(1000.0),
                agent_adjustable: true,
                db_persisted: true,
            },
        ];
        assert!(validate_recommendation(&rec, &current, &ranges));
    }

    #[test]
    fn test_validate_empty_recommendation_passes() {
        // Empty recommendation = no changes = valid
        let rec = serde_json::json!({});
        let current = serde_json::json!({});
        let ranges = vec![ParamRange {
            name: "cooldown_ms".into(),
            min: 10000.0,
            max: 120000.0,
            step: Some(1000.0),
            agent_adjustable: true,
            db_persisted: true,
        }];
        assert!(validate_recommendation(&rec, &current, &ranges));
    }

    #[test]
    fn test_backoff_intervals() {
        // Verify the backoff intervals are correct
        let ai = Arc::new(AiServiceClient::new());
        let (tx, _rx) = tokio::sync::mpsc::unbounded_channel();
        let pool = Arc::new(crate::database::pool::DbPool::disconnected());
        let cancel = CancellationToken::new();
        let sched = StrategistScheduler::new(ai, tx, pool, cancel);

        assert_eq!(sched.current_interval(), Duration::from_secs(300));
        sched.consecutive_failures.store(1, Ordering::Relaxed);
        assert_eq!(sched.current_interval(), Duration::from_secs(1_800));
        sched.consecutive_failures.store(2, Ordering::Relaxed);
        assert_eq!(sched.current_interval(), Duration::from_secs(3_600));
        sched.consecutive_failures.store(5, Ordering::Relaxed);
        assert_eq!(sched.current_interval(), Duration::from_secs(14_400));
    }
}
