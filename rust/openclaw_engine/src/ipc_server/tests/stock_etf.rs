//! ADR-0048 Stock/ETF IPC fixture tests.

use super::super::*;
use super::{
    empty_account_manager_slot, empty_budget_slot, empty_cost_edge_advisor_slot,
    empty_h_state_cache_slot, empty_teacher_slot, make_test_config, make_test_data_dir,
};
mod core_status_fixtures;
mod foundation_status_fixtures;
mod phase5_status_fixtures;
mod precontact_fixtures;
mod request_contracts;
mod status_fixtures;

#[tokio::test]
async fn stock_etf_status_methods_ignore_untrusted_params() {
    let methods = [
        "stock_etf.get_lane_status",
        "stock_etf.get_phase0_status",
        "stock_etf.get_readiness",
        "stock_etf.get_data_foundation_status",
        "stock_etf.get_policy_status",
        "stock_etf.get_authorization_status",
        "stock_etf.get_account_status",
        "stock_etf.get_evidence_status",
        "stock_etf.get_universe_status",
        "stock_etf.get_shadow_status",
        "stock_etf.get_paper_status",
        "stock_etf.get_reconciliation_status",
        "stock_etf.get_scorecard_status",
        "stock_etf.get_launch_status",
        "stock_etf.get_release_packet_status",
        "stock_etf.get_disable_cleanup_status",
    ];
    let untrusted_params = serde_json::json!({
        "asset_lane": "crypto_perp",
        "broker": "bybit",
        "environment": "live",
        "method": "stock_etf.submit_paper_order",
        "request_method": "submit_paper_order",
        "operation": "paper_order_submit",
        "ibkr_call_performed": true,
        "secret_slot_touched": true,
        "order_routed": true,
        "bybit_ipc_reused": true,
    });

    for method in methods {
        let empty_req =
            format!(r#"{{"jsonrpc":"2.0","method":"{method}","params":{{}},"id":49000}}"#);
        let untrusted_req = format!(
            r#"{{"jsonrpc":"2.0","method":"{method}","params":{},"id":49001}}"#,
            untrusted_params
        );

        let expected = dispatch_stock_etf_test_request(&empty_req).await;
        let actual = dispatch_stock_etf_test_request(&untrusted_req).await;

        assert!(expected.error.is_none(), "{method} empty params failed");
        assert!(actual.error.is_none(), "{method} untrusted params failed");
        assert_eq!(
            actual.result, expected.result,
            "{method} changed after untrusted params"
        );
    }
}

#[test]
fn stock_etf_ipc_status_fixture_assertions_stay_exact() {
    let sources = [
        include_str!("stock_etf.rs"),
        include_str!("stock_etf/core_status_fixtures.rs"),
        include_str!("stock_etf/precontact_fixtures.rs"),
        include_str!("stock_etf/foundation_status_fixtures.rs"),
        include_str!("stock_etf/status_fixtures.rs"),
        include_str!("stock_etf/phase5_status_fixtures.rs"),
    ];
    let forbidden = [
        "json_array_".to_string() + "contains(",
        [".iter().", "any(|item| item.as_str() == Some("].concat(),
        [".as_array().", "unwrap().", "len()"].concat(),
    ];

    for source in sources {
        for pattern in &forbidden {
            assert!(
                !source.contains(pattern),
                "stock_etf IPC status fixture tests must use exact ordered arrays, found {pattern}"
            );
        }
    }
}

fn assert_json_array_eq(value: &serde_json::Value, expected: &[&str]) {
    let actual: Vec<&str> = value
        .as_array()
        .expect("json array")
        .iter()
        .map(|item| item.as_str().expect("string item"))
        .collect();
    assert_eq!(actual, expected);
}

async fn dispatch_stock_etf_test_request(req: &str) -> JsonRpcResponse {
    let config = make_test_config();
    let dd = make_test_data_dir();
    dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
        &empty_account_manager_slot(),
    )
    .await
}
