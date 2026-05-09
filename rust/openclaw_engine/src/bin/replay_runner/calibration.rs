//! Replay runner execution calibration extraction helpers.

pub(crate) fn maker_fill_cap_from_manifest(
    blob: Option<&serde_json::Value>,
) -> Result<Option<f64>, Box<dyn std::error::Error>> {
    let Some(value) = blob else {
        return Ok(None);
    };
    let Some(raw) = value
        .get("recommended_maker_fill_probability_cap")
        .and_then(|item| item.as_f64())
    else {
        return Ok(None);
    };
    if !raw.is_finite() || !(0.0..=1.0).contains(&raw) {
        return Err(format!(
            "replay_runner: manifest.execution_calibration.\
             recommended_maker_fill_probability_cap={} invalid; must be \
             finite and within [0, 1]",
            raw
        )
        .into());
    }
    Ok(Some(raw))
}

pub(crate) fn latency_ms_from_manifest(
    blob: Option<&serde_json::Value>,
) -> Result<Option<u64>, Box<dyn std::error::Error>> {
    let Some(value) = blob else {
        return Ok(None);
    };
    let raw = value
        .get("recommended_latency_ms")
        .and_then(|item| item.as_u64())
        .or_else(|| {
            value
                .get("latency_ms")
                .and_then(|latency| latency.get("q50"))
                .and_then(|item| item.as_u64())
        });
    let Some(latency_ms) = raw else {
        return Ok(None);
    };
    if latency_ms > 60_000 {
        return Err(format!(
            "replay_runner: manifest.execution_calibration latency={}ms invalid; \
             must be <= 60000ms",
            latency_ms
        )
        .into());
    }
    Ok(Some(latency_ms))
}
