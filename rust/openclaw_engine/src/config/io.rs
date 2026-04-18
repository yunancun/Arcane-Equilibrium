//! TOML load/save helpers for ARCH-RC1 unified Configs.
//! ARCH-RC1 統一 Config 的 TOML 載入/儲存輔助函數。
//!
//! MODULE_NOTE (EN): Generic, schema-agnostic helpers so that `RiskConfig`,
//!   `LearningConfig`, and `BudgetConfig` can all share the same startup load
//!   path. Each helper is closure-polymorphic over validation so the store
//!   layer stays decoupled from any specific Config's invariants.
//!   File-not-found is handled via fall-through to `T::default()` which must
//!   then ALSO pass the validator (catches the "default is invalid" class
//!   of regressions at startup). Parent directories are auto-created on save.
//! MODULE_NOTE (中): 通用、schema 無關的輔助，讓 `RiskConfig` / `LearningConfig`
//!   / `BudgetConfig` 共用同一個啟動載入路徑。驗證透過閉包傳入，store 層不與
//!   任何特定 Config 的 invariant 耦合。檔案不存在時回退到 `T::default()`，
//!   但預設值也必須通過驗證（捕捉「預設值無效」這類啟動期退化）。
//!   儲存時父目錄自動建立。

use serde::{de::DeserializeOwned, Serialize};
use std::path::Path;

/// Load a Config from a TOML file, falling back to `T::default()` when the
/// file does not exist. Both the parsed and the default branches run through
/// the caller-provided validator.
/// 從 TOML 檔載入 Config；檔案不存在時回退到 `T::default()`。
/// 兩條分支都會跑 caller 傳入的驗證器。
pub fn load_toml_or_default<T, F>(path: &Path, validate: F) -> Result<T, String>
where
    T: DeserializeOwned + Default,
    F: FnOnce(&T) -> Result<(), String>,
{
    if !path.exists() {
        let default = T::default();
        validate(&default).map_err(|e| {
            format!(
                "default config failed validation at {}: {}",
                path.display(),
                e
            )
        })?;
        return Ok(default);
    }
    let content =
        std::fs::read_to_string(path).map_err(|e| format!("read {}: {}", path.display(), e))?;
    let config: T =
        toml::from_str(&content).map_err(|e| format!("parse {}: {}", path.display(), e))?;
    validate(&config).map_err(|e| format!("validate {}: {}", path.display(), e))?;
    Ok(config)
}

/// Serialise a Config to TOML and write atomically (best-effort: write to
/// temp file in the same dir, then rename). Parent directory is created if
/// missing.
/// 將 Config 序列化為 TOML 並儘量原子寫入（同目錄寫 temp → rename）。
/// 父目錄不存在時自動建立。
pub fn save_toml<T: Serialize>(path: &Path, value: &T) -> Result<(), String> {
    let content = toml::to_string_pretty(value).map_err(|e| format!("serialize toml: {}", e))?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|e| format!("mkdir {}: {}", parent.display(), e))?;
    }
    let tmp = path.with_extension("toml.tmp");
    std::fs::write(&tmp, content).map_err(|e| format!("write {}: {}", tmp.display(), e))?;
    std::fs::rename(&tmp, path)
        .map_err(|e| format!("rename {} -> {}: {}", tmp.display(), path.display(), e))?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde::Deserialize;

    #[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
    struct Dummy {
        #[serde(default = "default_val")]
        val: u32,
        #[serde(default)]
        name: String,
    }
    fn default_val() -> u32 {
        42
    }
    impl Default for Dummy {
        fn default() -> Self {
            Self {
                val: default_val(),
                name: String::new(),
            }
        }
    }

    fn always_ok(_c: &Dummy) -> Result<(), String> {
        Ok(())
    }
    fn reject_zero(c: &Dummy) -> Result<(), String> {
        if c.val == 0 {
            Err("val must be > 0".into())
        } else {
            Ok(())
        }
    }

    #[test]
    fn test_load_missing_file_returns_default() {
        let dir = std::env::temp_dir().join("oc_io_test_missing");
        let _ = std::fs::remove_dir_all(&dir);
        let path = dir.join("missing.toml");
        let cfg: Dummy = load_toml_or_default(&path, always_ok).unwrap();
        assert_eq!(cfg.val, 42); // from default_val
    }

    #[test]
    fn test_load_parses_existing_file() {
        let dir = std::env::temp_dir().join("oc_io_test_parse");
        let _ = std::fs::create_dir_all(&dir);
        let path = dir.join("cfg.toml");
        std::fs::write(&path, "val = 99\nname = \"hello\"\n").unwrap();
        let cfg: Dummy = load_toml_or_default(&path, always_ok).unwrap();
        assert_eq!(cfg.val, 99);
        assert_eq!(cfg.name, "hello");
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn test_load_invalid_toml_errors() {
        let dir = std::env::temp_dir().join("oc_io_test_bad");
        let _ = std::fs::create_dir_all(&dir);
        let path = dir.join("bad.toml");
        std::fs::write(&path, "not = = valid").unwrap();
        let res: Result<Dummy, _> = load_toml_or_default(&path, always_ok);
        assert!(res.is_err());
        assert!(res.unwrap_err().contains("parse"));
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn test_load_runs_validator_on_parsed() {
        let dir = std::env::temp_dir().join("oc_io_test_validate");
        let _ = std::fs::create_dir_all(&dir);
        let path = dir.join("zero.toml");
        std::fs::write(&path, "val = 0\n").unwrap();
        let res: Result<Dummy, _> = load_toml_or_default(&path, reject_zero);
        assert!(res.is_err());
        assert!(res.unwrap_err().contains("val must be > 0"));
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn test_save_then_load_round_trip() {
        let dir = std::env::temp_dir().join("oc_io_test_roundtrip");
        let _ = std::fs::create_dir_all(&dir);
        let path = dir.join("rt.toml");
        let original = Dummy {
            val: 7,
            name: "rt".into(),
        };
        save_toml(&path, &original).unwrap();
        let loaded: Dummy = load_toml_or_default(&path, always_ok).unwrap();
        assert_eq!(loaded, original);
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn test_save_creates_parent_dir() {
        let dir = std::env::temp_dir()
            .join("oc_io_test_mkdir")
            .join("nested")
            .join("deep");
        let _ = std::fs::remove_dir_all(std::env::temp_dir().join("oc_io_test_mkdir"));
        let path = dir.join("deep.toml");
        let val = Dummy {
            val: 3,
            name: "x".into(),
        };
        save_toml(&path, &val).unwrap();
        assert!(path.exists());
    }
}
