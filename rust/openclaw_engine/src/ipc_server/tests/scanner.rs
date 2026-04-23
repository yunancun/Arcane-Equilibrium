//! Scanner IPC tests (IPC-SCAN-1).
//! 掃描器 IPC 測試（IPC-SCAN-1）。

use super::super::*;

fn make_scanner_registry() -> Arc<crate::scanner::registry::SymbolRegistry> {
    let pinned = vec!["BTCUSDT".to_string(), "ETHUSDT".to_string()];
    Arc::new(crate::scanner::registry::SymbolRegistry::new(
        vec![
            "BTCUSDT".to_string(),
            "ETHUSDT".to_string(),
            "SOLUSDT".to_string(),
        ],
        pinned,
    ))
}

/// get_active_symbols — uninitialized (None registry) returns fail-soft.
/// get_active_symbols — 未初始化時 fail-soft。
#[test]
fn test_get_active_symbols_uninitialized() {
    let resp = handle_get_active_symbols(serde_json::json!(1), &None);
    assert!(resp.error.is_none());
    let r = resp.result.expect("result");
    assert_eq!(r["status"], "uninitialized");
    assert_eq!(r["count"], 0);
}

/// get_active_symbols — registry wired: returns all symbols, correctly splits pinned/dynamic.
/// get_active_symbols — registry 已接線：返回所有交易對，正確區分固定/動態。
#[test]
fn test_get_active_symbols_wired() {
    let reg = make_scanner_registry();
    let resp = handle_get_active_symbols(serde_json::json!(2), &Some(reg));
    assert!(resp.error.is_none());
    let r = resp.result.expect("result");
    assert_eq!(r["status"], "ok");
    assert_eq!(r["count"], 3);
    let pinned = r["pinned"].as_array().expect("pinned");
    assert_eq!(pinned.len(), 2);
    let dynamic = r["dynamic"].as_array().expect("dynamic");
    assert_eq!(dynamic.len(), 1);
    assert_eq!(dynamic[0], "SOLUSDT");
}

/// get_scanner_status — uninitialized (None registry) returns fail-soft.
/// get_scanner_status — 未初始化時 fail-soft。
#[test]
fn test_get_scanner_status_uninitialized() {
    let resp = handle_get_scanner_status(serde_json::json!(3), &None);
    assert!(resp.error.is_none());
    let r = resp.result.expect("result");
    assert_eq!(r["status"], "uninitialized");
}

/// get_scanner_status — registry wired, no scan yet: last_scan is null.
/// get_scanner_status — registry 已接線，尚無掃描：last_scan 為 null。
#[test]
fn test_get_scanner_status_no_scan_yet() {
    let reg = make_scanner_registry();
    let resp = handle_get_scanner_status(serde_json::json!(4), &Some(reg));
    assert!(resp.error.is_none());
    let r = resp.result.expect("result");
    assert_eq!(r["status"], "ok");
    assert_eq!(r["active_count"], 3);
    assert!(r["last_scan"].is_null());
}
