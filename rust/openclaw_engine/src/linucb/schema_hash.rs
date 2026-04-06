//! Feature schema hash — fail-closed identity for context vector layout.
//! 特徵 schema 雜湊 — context 向量佈局的 fail-closed 身分。
//!
//! MODULE_NOTE (EN): Computes sha256("name1\nname2\n...")[:16] as a stable
//!   identifier for the ordered feature list. Any reordering or rename produces
//!   a different hash, which the state_io loader uses to refuse mismatched DB rows.
//! MODULE_NOTE (中): 計算 sha256("name1\nname2\n...")[:16]，作為有序特徵列表
//!   的穩定身分。任何重排或重命名都會產生不同雜湊，供 state_io 載入器拒絕
//!   不匹配的 DB row。

use sha2::{Digest, Sha256};

/// Compute "sha256:<first 16 hex chars>" of newline-joined feature names.
/// 計算換行串接後特徵名的 "sha256:<前 16 十六進制字元>"。
pub fn compute_feature_schema_hash(feature_names: &[&str]) -> String {
    let mut hasher = Sha256::new();
    for name in feature_names {
        hasher.update(name.as_bytes());
        hasher.update(b"\n");
    }
    let digest = hasher.finalize();
    let hex: String = digest.iter().map(|b| format!("{:02x}", b)).collect();
    format!("sha256:{}", &hex[..16])
}

/// Convenience alias / 簡寫別名
pub fn compute(feature_names: &[&str]) -> String {
    compute_feature_schema_hash(feature_names)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_compute_feature_schema_hash_deterministic() {
        let h1 = compute_feature_schema_hash(&["atr", "rsi", "regime"]);
        let h2 = compute_feature_schema_hash(&["atr", "rsi", "regime"]);
        assert_eq!(h1, h2);
        assert!(h1.starts_with("sha256:"));
        assert_eq!(h1.len(), "sha256:".len() + 16);
    }

    #[test]
    fn test_compute_feature_schema_hash_order_sensitive() {
        let h1 = compute_feature_schema_hash(&["atr", "rsi"]);
        let h2 = compute_feature_schema_hash(&["rsi", "atr"]);
        assert_ne!(h1, h2);
    }
}
