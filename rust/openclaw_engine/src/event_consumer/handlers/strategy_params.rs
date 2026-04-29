//! Strategy-parameter IPC command handlers (UpdateStrategyParams /
//! GetStrategyParams / GetParamRanges). Extracted from the legacy monolith
//! as part of E5-P1-3.
//!
//! 策略參數 IPC 命令處理器 — E5-P1-3 從 handlers.rs 拆出。
//!
//! MODULE_NOTE (EN): Each helper preserves the pre-split command envelope and
//!   response shape; CONF-D now stages typed validation before applying
//!   `conf_scale` so mixed payloads stay atomic.
//! MODULE_NOTE (中): 各 helper 保留拆分前命令封包與回應形狀；CONF-D 改為先跑
//!   類型化驗證再套用 `conf_scale`，避免混合 payload 部分成功。

use crate::persistence::DualStateWriter;
use crate::tick_pipeline::TickPipeline;
use tracing::info;

fn merge_strategy_params_json(current_json: &str, incoming_json: &str) -> Result<String, String> {
    let mut current: serde_json::Value = serde_json::from_str(current_json)
        .map_err(|e| format!("current params JSON invalid: {e}"))?;
    let incoming: serde_json::Value =
        serde_json::from_str(incoming_json).map_err(|e| format!("params JSON invalid: {e}"))?;

    match (&mut current, incoming) {
        (serde_json::Value::Object(current_map), serde_json::Value::Object(incoming_map)) => {
            for (key, value) in incoming_map {
                current_map.insert(key, value);
            }
            Ok(current.to_string())
        }
        (_, other) => Err(format!(
            "params JSON must be an object, got {}",
            match other {
                serde_json::Value::Null => "null",
                serde_json::Value::Bool(_) => "bool",
                serde_json::Value::Number(_) => "number",
                serde_json::Value::String(_) => "string",
                serde_json::Value::Array(_) => "array",
                serde_json::Value::Object(_) => "object",
            }
        )),
    }
}

/// Phase 3b · CONF-D · EN: Update one strategy's typed parameters via IPC.
///   Pre-processes the JSON to extract optional `conf_scale`; typed
///   `update_params_json` is validated/applied first, then `conf_scale` is
///   applied. If only `conf_scale` was sent (stripped body == "{}"), typed
///   update is skipped.
/// Phase 3b · CONF-D · 中文：透過 IPC 更新策略類型化參數；先跑剩餘 JSON 的
///   類型化更新，再套用 conf_scale；若僅含 conf_scale 則跳過類型化更新。
pub(super) fn handle_update_strategy_params(
    strategy_name: String,
    params_json: String,
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
    snapshot_writer: &mut DualStateWriter,
) {
    // CONF-D: pre-process params JSON — strip optional "conf_scale" key.
    // We intentionally stage typed validation first; `conf_scale` is applied
    // only after typed update succeeds so mixed payloads are atomic.
    // CONF-D：預處理抽出 conf_scale。先跑類型化驗證，成功後才套用 conf_scale；
    // 混合 payload 不再出現「部分生效」。
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
            // If the stripped JSON is just "{}" and we did set conf_scale,
            // skip the typed update to avoid unnecessary churn / parse errors.
            let need_typed_update = effective_json != "{}" || conf_scale_opt.is_none();
            if need_typed_update {
                let merged_json = match merge_strategy_params_json(
                    &strategy.get_params_json(),
                    &effective_json,
                ) {
                    Ok(json) => json,
                    Err(e) => {
                        let _ = response_tx.send(Err(format!("validation failed: {e}")));
                        return;
                    }
                };
                match strategy.update_params_json(&merged_json) {
                    Ok(()) => {
                        if let Some(scale) = conf_scale_opt {
                            strategy.set_conf_scale(scale);
                        }
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
                if let Some(scale) = conf_scale_opt {
                    strategy.set_conf_scale(scale);
                }
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
