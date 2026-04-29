//! Runtime secret resolution helpers.
//!
//! MODULE_NOTE (EN): Reads high-value runtime secrets from direct env vars or
//! companion `*_FILE` env vars. Batch B launch scripts pass only file paths for
//! DB URLs and IPC HMAC secrets, keeping secret values out of long-lived process
//! environments while preserving legacy direct-env compatibility.
//!
//! MODULE_NOTE (中): 從直接 env 或 `*_FILE` companion env 讀取 runtime secret。
//! Batch B 啟動腳本只傳 DB URL / IPC HMAC secret 的 file path，避免 secret 值
//! 留在長壽命 process env，同時保留舊 direct-env 相容性。

pub fn var_or_file(name: &str) -> Option<String> {
    if let Ok(value) = std::env::var(name) {
        if !value.is_empty() {
            return Some(value);
        }
    }

    let file_var = format!("{name}_FILE");
    let path = std::env::var(file_var).ok()?;
    if path.trim().is_empty() {
        return None;
    }

    let raw = std::fs::read_to_string(path).ok()?;
    let value = raw.trim_end_matches(&['\r', '\n'][..]).to_string();
    if value.is_empty() {
        None
    } else {
        Some(value)
    }
}
