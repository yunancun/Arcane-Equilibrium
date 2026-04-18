//! ARCH-RC1 1C-2-C: unified Config IPC helpers — extracted from handlers.rs (§九 1200-line limit).
//! 統一 Config IPC 輔助 — 從 handlers.rs 提取（§九 1200 行硬上限）。

use super::*;

/// Recursively merge JSON `patch` into `base` (deep merge for objects, replace
/// for scalars/arrays). Used by `patch_*_config` to compute the next config
/// from a partial JSON patch + the current snapshot.
/// 將 JSON `patch` 遞歸合併進 `base`（物件深合併、純量/陣列覆蓋）。
/// 用於 `patch_*_config` 從部分補丁 + 當前快照計算下一版配置。
pub(super) fn json_merge(base: &mut serde_json::Value, patch: &serde_json::Value) {
    use serde_json::Value;
    match (base, patch) {
        (Value::Object(b), Value::Object(p)) => {
            for (k, v) in p {
                json_merge(b.entry(k.clone()).or_insert(Value::Null), v);
            }
        }
        (b, p) => *b = p.clone(),
    }
}

pub(super) fn parse_patch_source(s: &str) -> Result<PatchSource, String> {
    match s {
        "operator" => Ok(PatchSource::Operator),
        "agent" => Ok(PatchSource::Agent),
        "migration" => Ok(PatchSource::Migration),
        other => Err(format!("invalid source: {other}")),
    }
}

/// Generic GET handler — serialise current store snapshot + version.
/// 通用 GET handler — 序列化當前 store 快照 + 版本。
pub(super) fn handle_get_config<T>(
    id: serde_json::Value,
    store: &Option<Arc<ConfigStore<T>>>,
    config_name: &str,
) -> JsonRpcResponse
where
    T: serde::Serialize + Clone + Send + Sync + 'static,
{
    let store = match store {
        Some(s) => s,
        None => {
            return JsonRpcResponse::error(
                id,
                ERR_INTERNAL,
                format!("{config_name} store not configured"),
            )
        }
    };
    let snap = store.load();
    match serde_json::to_value(&*snap) {
        Ok(v) => JsonRpcResponse::success(
            id,
            serde_json::json!({
                "config": v,
                "version": store.version(),
            }),
        ),
        Err(e) => JsonRpcResponse::error(id, ERR_INTERNAL, format!("serialize failed: {e}")),
    }
}

/// Generic PATCH handler — JSON deep-merge into current → validate → atomic
/// replace via ConfigStore (bumps version, triggers tick-level hot reload).
/// All-or-nothing: any deserialise/validate failure leaves the store untouched.
/// 通用 PATCH handler — JSON 深合併進當前 → 驗證 → ConfigStore 原子替換
/// （遞增版本，觸發 tick-level 熱重載）。All-or-nothing：任何反序列化/驗證
/// 失敗 store 完全不變。
#[allow(clippy::too_many_arguments)]
pub(super) fn handle_patch_config<T, V>(
    id: serde_json::Value,
    store: &Option<Arc<ConfigStore<T>>>,
    params: &serde_json::Value,
    validate: V,
    config_name: &str,
    audit_pool: &Option<sqlx::PgPool>,
) -> JsonRpcResponse
where
    T: serde::Serialize + serde::de::DeserializeOwned + Clone + Send + Sync + 'static,
    V: Fn(&T) -> Result<(), String>,
{
    let store = match store {
        Some(s) => s,
        None => {
            return JsonRpcResponse::error(
                id,
                ERR_INTERNAL,
                format!("{config_name} store not configured"),
            )
        }
    };
    let patch = match params.get("patch") {
        Some(p) if p.is_object() => p,
        _ => {
            return JsonRpcResponse::error(
                id,
                ERR_INVALID_REQUEST,
                "missing 'patch' object parameter",
            )
        }
    };
    let source_str = params
        .get("source")
        .and_then(|v| v.as_str())
        .unwrap_or("operator");
    let source = match parse_patch_source(source_str) {
        Ok(s) => s,
        Err(e) => return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, e),
    };

    let old_version = store.version();
    let current = store.load();
    let mut merged = match serde_json::to_value(&*current) {
        Ok(v) => v,
        Err(e) => {
            return JsonRpcResponse::error(
                id,
                ERR_INTERNAL,
                format!("snapshot serialise failed: {e}"),
            )
        }
    };
    json_merge(&mut merged, patch);
    let next: T = match serde_json::from_value(merged) {
        Ok(t) => t,
        Err(e) => {
            return JsonRpcResponse::error(
                id,
                ERR_INVALID_REQUEST,
                format!("patched config deserialize failed: {e}"),
            )
        }
    };
    if let Err(e) = validate(&next) {
        return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, format!("validation failed: {e}"));
    }
    match store.replace(next, source) {
        Ok(outcome) => {
            info!(
                config = config_name,
                version = outcome.version,
                source = outcome.source.as_str(),
                "ARCH-RC1 config patched via IPC / 配置經 IPC 熱更新"
            );
            // ARCH-RC1 1C-2-E: fire-and-forget audit row to V014 engine_events.
            // ARCH-RC1 1C-2-E：fire-and-forget 寫一行 V014 engine_events 審計。
            if let Some(pool) = audit_pool.clone() {
                let cfg_name = config_name.to_string();
                let src = outcome.source.as_str().to_string();
                let new_v = outcome.version as i64;
                let old_v = old_version as i64;
                let payload = serde_json::json!({
                    "fields_changed": patch.as_object()
                        .map(|m| m.keys().cloned().collect::<Vec<_>>())
                        .unwrap_or_default(),
                });
                tokio::spawn(async move {
                    let ts_ms = std::time::SystemTime::now()
                        .duration_since(std::time::UNIX_EPOCH)
                        .map(|d| d.as_millis() as i64)
                        .unwrap_or(0);
                    let res = sqlx::query(
                        "INSERT INTO observability.engine_events \
                         (ts_ms, event_type, source, config_name, old_version, new_version, payload) \
                         VALUES ($1, 'config_patch', $2, $3, $4, $5, $6)",
                    )
                    .bind(ts_ms)
                    .bind(&src)
                    .bind(&cfg_name)
                    .bind(old_v)
                    .bind(new_v)
                    .bind(&payload)
                    .execute(&pool)
                    .await;
                    if let Err(e) = res {
                        warn!(error = %e, config = %cfg_name, "V014 audit insert failed / V014 審計寫入失敗");
                    }
                });
            }
            JsonRpcResponse::success(
                id,
                serde_json::json!({
                    "ok": true,
                    "config": config_name,
                    "version": outcome.version,
                    "source": outcome.source.as_str(),
                }),
            )
        }
        Err(e) => JsonRpcResponse::error(id, ERR_INTERNAL, format!("store replace failed: {e}")),
    }
}
