//! Strategy-parameter IPC command handlers (UpdateStrategyParams /
//! GetStrategyParams / GetParamRanges). Extracted from the legacy monolith
//! as part of E5-P1-3.
//!
//! 策略參數 IPC 命令處理器 — E5-P1-3 從 handlers.rs 拆出。
//!
//! MODULE_NOTE (EN): Each helper preserves the pre-split behaviour bit-for-bit,
//!   including the CONF-D `conf_scale` strip-and-apply pre-processing.
//! MODULE_NOTE (中): 各 helper 行為與拆分前完全一致，包括 CONF-D conf_scale
//!   抽取處理。

use crate::persistence::DualStateWriter;
use crate::tick_pipeline::TickPipeline;
use tracing::info;

/// Phase 3b · CONF-D · EN: Update one strategy's typed parameters via IPC.
///   Pre-processes the JSON to extract an optional `conf_scale` key and apply
///   it through `Strategy::set_conf_scale`; the remaining JSON is forwarded to
///   the strategy's typed `update_params_json`. If only `conf_scale` was sent
///   (stripped body == "{}"), the typed update is skipped.
/// Phase 3b · CONF-D · 中文：透過 IPC 更新策略類型化參數；預先抽出 conf_scale
///   套用後再轉發剩餘 JSON；若僅含 conf_scale 則跳過類型化更新。
pub(super) fn handle_update_strategy_params(
    strategy_name: String,
    params_json: String,
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
    snapshot_writer: &mut DualStateWriter,
) {
    // CONF-D: pre-process params JSON — strip optional "conf_scale" key and
    // apply via Strategy::set_conf_scale, then forward the remaining JSON to
    // the strategy's typed update_params_json. If only conf_scale was sent,
    // skip the typed update entirely (empty object).
    // CONF-D：預處理 — 抽出 conf_scale 套用後再轉發剩餘 JSON。
    let (effective_json, conf_scale_opt): (String, Option<f64>) =
        match serde_json::from_str::<serde_json::Value>(&params_json) {
            Ok(serde_json::Value::Object(mut map)) => {
                let cs = map.remove("conf_scale").and_then(|v| v.as_f64());
                let stripped = serde_json::Value::Object(map);
                (stripped.to_string(), cs)
            }
            _ => (params_json.clone(), None),
        };

    let result = match pipeline.orchestrator.find_strategy_mut(&strategy_name) {
        Some(strategy) => {
            if let Some(scale) = conf_scale_opt {
                strategy.set_conf_scale(scale);
            }
            // If the stripped JSON is just "{}" and we did set conf_scale,
            // skip the typed update to avoid unnecessary churn / parse errors.
            let need_typed_update = effective_json != "{}" || conf_scale_opt.is_none();
            if need_typed_update {
                match strategy.update_params_json(&effective_json) {
                    Ok(()) => {
                        info!(
                            strategy = %strategy_name,
                            conf_scale = ?conf_scale_opt,
                            "strategy params updated via IPC / 策略參數已通過 IPC 更新"
                        );
                        snapshot_writer.force_write(&pipeline.snapshot());
                        Ok(format!("params updated for {}", strategy_name))
                    }
                    Err(e) => Err(format!("validation failed: {e}")),
                }
            } else {
                info!(
                    strategy = %strategy_name,
                    conf_scale = ?conf_scale_opt,
                    "strategy conf_scale updated via IPC / 策略 conf_scale 已通過 IPC 更新"
                );
                snapshot_writer.force_write(&pipeline.snapshot());
                Ok(format!("conf_scale updated for {}", strategy_name))
            }
        }
        None => Err(format!("strategy not found: {strategy_name}")),
    };
    let _ = response_tx.send(result);
}

/// EN: Return the current params JSON for the named strategy.
/// 中文: 取得指定策略的當前參數 JSON。
pub(super) fn handle_get_strategy_params(
    strategy_name: String,
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
) {
    let result = match pipeline.orchestrator.find_strategy_mut(&strategy_name) {
        Some(strategy) => Ok(strategy.get_params_json()),
        None => Err(format!("strategy not found: {strategy_name}")),
    };
    let _ = response_tx.send(result);
}

/// EN: Return the agent-tunable parameter ranges JSON for the named strategy.
/// 中文: 取得指定策略可供 Agent 調整的參數範圍 JSON。
pub(super) fn handle_get_param_ranges(
    strategy_name: String,
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
) {
    let result = match pipeline.orchestrator.find_strategy_mut(&strategy_name) {
        Some(strategy) => Ok(strategy.param_ranges_json()),
        None => Err(format!("strategy not found: {strategy_name}")),
    };
    let _ = response_tx.send(result);
}
