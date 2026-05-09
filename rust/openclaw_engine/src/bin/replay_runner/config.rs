//! Replay runner manifest-to-runtime config adapters.

use openclaw_engine::edge_estimates::EdgeEstimates;
use openclaw_engine::replay::scanner_timeline::replay_default_scanner_config;
use openclaw_engine::scanner::ScannerConfig;

pub(crate) fn scanner_config_from_manifest(
    blob: Option<&serde_json::Value>,
) -> Result<ScannerConfig, Box<dyn std::error::Error>> {
    let mut config = match blob {
        Some(value) => serde_json::from_value::<ScannerConfig>(value.clone()).map_err(|e| {
            Box::<dyn std::error::Error>::from(format!(
                "replay_runner: manifest.scanner_config shape mismatch \
                 (cannot deserialise into ScannerConfig): {}",
                e
            ))
        })?,
        None => replay_default_scanner_config(),
    };
    if blob.is_none() {
        config.scheduling.scan_interval_secs = 60;
        config.scheduling.warmup_delay_secs = 0;
    }
    config.validate().map_err(|e| {
        Box::<dyn std::error::Error>::from(format!(
            "replay_runner: manifest.scanner_config invalid: {}",
            e
        ))
    })?;
    Ok(config)
}

pub(crate) fn edge_estimates_from_manifest(
    blob: Option<&serde_json::Value>,
) -> Result<EdgeEstimates, Box<dyn std::error::Error>> {
    let Some(value) = blob else {
        return Ok(EdgeEstimates::empty());
    };
    let raw = serde_json::to_string(value).map_err(|e| {
        Box::<dyn std::error::Error>::from(format!(
            "replay_runner: manifest.edge_estimates cannot be serialized: {}",
            e
        ))
    })?;
    EdgeEstimates::load_from_str(&raw).ok_or_else(|| {
        Box::<dyn std::error::Error>::from(
            "replay_runner: manifest.edge_estimates shape mismatch \
             (expected edge_estimates.json-compatible object)",
        )
    })
}
