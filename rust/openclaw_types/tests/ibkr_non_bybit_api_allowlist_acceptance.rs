//! ADR-0048 IBKR non-Bybit API allowlist acceptance tests.
//!
//! These tests validate source-only API action classification and denial
//! posture. They do not contact IBKR, inspect secrets, create clients, open
//! sockets, route orders, or mutate Bybit behavior.

use openclaw_types::{
    classify_non_bybit_api_action, required_non_bybit_api_actions, NonBybitApiAction,
    NonBybitApiAllowlistBlocker, NonBybitApiAllowlistV1, NonBybitApiDenialReason,
    NON_BYBIT_API_ALLOWLIST_CONTRACT_ID,
};

#[test]
fn default_allowlist_blocks_before_any_non_bybit_api_contact() {
    use NonBybitApiAllowlistBlocker as Blocker;

    let verdict = NonBybitApiAllowlistV1::default().validate();
    let mut expected_blockers = vec![Blocker::ContractIdMismatch, Blocker::SourceVersionMismatch];
    expected_blockers.extend(
        std::iter::repeat(Blocker::ActionMissing).take(required_non_bybit_api_actions().len()),
    );
    expected_blockers.extend([
        Blocker::ClientPortalWebApiNotDenied,
        Blocker::LiveOrderNotDenied,
        Blocker::AccountTransferNotDenied,
        Blocker::MarginShortOptionsCfdNotDenied,
        Blocker::MarketDataEntitlementPurchaseNotDenied,
        Blocker::AccountManagementWriteNotDenied,
        Blocker::BybitLiveExecutionNotProtected,
    ]);

    assert!(!verdict.accepted);
    assert_eq!(verdict.blockers, expected_blockers);
}

#[test]
fn accepted_allowlist_pins_required_actions_without_runtime_authority() {
    let allowlist = NonBybitApiAllowlistV1::accepted_fixture();
    let verdict = allowlist.validate();

    assert!(
        verdict.accepted,
        "unexpected blockers: {:?}",
        verdict.blockers
    );
    assert_eq!(allowlist.contract_id, NON_BYBIT_API_ALLOWLIST_CONTRACT_ID);
    assert_eq!(allowlist.source_version, 1);
    assert_eq!(
        allowlist.read_actions,
        vec![
            NonBybitApiAction::ServerTimeRead,
            NonBybitApiAction::ConnectionHealthRead,
            NonBybitApiAction::AccountSummarySnapshotRead,
            NonBybitApiAction::PortfolioPositionsSnapshotRead,
            NonBybitApiAction::ContractDetailsRead,
            NonBybitApiAction::MarketDataSnapshotRead,
            NonBybitApiAction::MarketDataSubscriptionRead,
            NonBybitApiAction::HistoricalBarsRead,
            NonBybitApiAction::OpenPaperOrdersRead,
            NonBybitApiAction::PaperExecutionsCommissionsRead,
        ]
    );
    assert_eq!(
        allowlist.paper_write_actions,
        vec![
            NonBybitApiAction::PaperOrderSubmit,
            NonBybitApiAction::PaperOrderCancel,
            NonBybitApiAction::PaperOrderReplace,
        ]
    );
    assert_eq!(
        allowlist.denied_actions,
        vec![
            NonBybitApiAction::LiveOrderSubmit,
            NonBybitApiAction::LiveAccountQuery,
            NonBybitApiAction::AccountTransfer,
            NonBybitApiAction::MarginEnablement,
            NonBybitApiAction::ShortBorrow,
            NonBybitApiAction::OptionsTrading,
            NonBybitApiAction::CfdTrading,
            NonBybitApiAction::MarketDataEntitlementPurchase,
            NonBybitApiAction::AccountManagementWrite,
            NonBybitApiAction::ClientPortalWebApiUse,
        ]
    );
    assert_eq!(
        required_non_bybit_api_actions().len(),
        allowlist.read_actions.len()
            + allowlist.paper_write_actions.len()
            + allowlist.denied_actions.len()
    );
    assert!(!allowlist.ibkr_contact_performed);
    assert!(!allowlist.secret_content_serialized);
    assert!(allowlist.bybit_live_execution_protected);

    let server_time = classify_non_bybit_api_action(NonBybitApiAction::ServerTimeRead);
    assert!(server_time.allowed_after_external_gate);
    assert!(server_time.requires_external_surface_gate);
    assert!(!server_time.requires_session_attestation);
    assert!(!server_time.requires_paper_order_gates);
    assert!(!server_time.denied);

    let account = classify_non_bybit_api_action(NonBybitApiAction::AccountSummarySnapshotRead);
    assert!(account.allowed_after_external_gate);
    assert!(account.requires_session_attestation);
    assert!(!account.requires_paper_order_gates);
    assert!(!account.denied);

    let submit = classify_non_bybit_api_action(NonBybitApiAction::PaperOrderSubmit);
    assert!(!submit.allowed_after_external_gate);
    assert!(submit.requires_external_surface_gate);
    assert!(submit.requires_session_attestation);
    assert!(submit.requires_paper_order_gates);
    assert!(!submit.denied);

    let live = classify_non_bybit_api_action(NonBybitApiAction::LiveOrderSubmit);
    assert!(live.denied);
    assert_eq!(
        live.denial_reason,
        Some(NonBybitApiDenialReason::LiveOrderDenied)
    );

    let client_portal = classify_non_bybit_api_action(NonBybitApiAction::ClientPortalWebApiUse);
    assert!(client_portal.denied);
    assert_eq!(
        client_portal.denial_reason,
        Some(NonBybitApiDenialReason::ClientPortalWebApiDenied)
    );
}

#[test]
fn allowlist_rejects_missing_duplicate_and_wrong_bucket_actions() {
    let mut missing = NonBybitApiAllowlistV1::accepted_fixture();
    missing
        .read_actions
        .retain(|action| *action != NonBybitApiAction::ServerTimeRead);
    assert_eq!(
        missing.validate().blockers,
        vec![NonBybitApiAllowlistBlocker::ActionMissing]
    );

    let mut duplicate = NonBybitApiAllowlistV1::accepted_fixture();
    duplicate
        .paper_write_actions
        .push(NonBybitApiAction::ServerTimeRead);
    assert_eq!(
        duplicate.validate().blockers,
        vec![
            NonBybitApiAllowlistBlocker::ActionDuplicated,
            NonBybitApiAllowlistBlocker::ActionInWrongBucket,
        ]
    );

    let mut wrong_bucket = NonBybitApiAllowlistV1::accepted_fixture();
    wrong_bucket
        .denied_actions
        .retain(|action| *action != NonBybitApiAction::LiveOrderSubmit);
    wrong_bucket
        .read_actions
        .push(NonBybitApiAction::LiveOrderSubmit);
    assert_single_blocker(
        wrong_bucket,
        NonBybitApiAllowlistBlocker::ActionInWrongBucket,
    );
}

#[test]
fn allowlist_rejects_denial_secret_contact_and_bybit_cross_wire_independently() {
    let mut client_portal = NonBybitApiAllowlistV1::accepted_fixture();
    client_portal.client_portal_web_api_denied = false;
    assert_single_blocker(
        client_portal,
        NonBybitApiAllowlistBlocker::ClientPortalWebApiNotDenied,
    );

    let mut live_order = NonBybitApiAllowlistV1::accepted_fixture();
    live_order.live_order_denied = false;
    assert_single_blocker(live_order, NonBybitApiAllowlistBlocker::LiveOrderNotDenied);

    let mut transfer = NonBybitApiAllowlistV1::accepted_fixture();
    transfer.account_transfer_denied = false;
    assert_single_blocker(
        transfer,
        NonBybitApiAllowlistBlocker::AccountTransferNotDenied,
    );

    let mut margin_short_options_cfd = NonBybitApiAllowlistV1::accepted_fixture();
    margin_short_options_cfd.margin_short_options_cfd_denied = false;
    assert_single_blocker(
        margin_short_options_cfd,
        NonBybitApiAllowlistBlocker::MarginShortOptionsCfdNotDenied,
    );

    let mut entitlement = NonBybitApiAllowlistV1::accepted_fixture();
    entitlement.market_data_entitlement_purchase_denied = false;
    assert_single_blocker(
        entitlement,
        NonBybitApiAllowlistBlocker::MarketDataEntitlementPurchaseNotDenied,
    );

    let mut account_write = NonBybitApiAllowlistV1::accepted_fixture();
    account_write.account_management_write_denied = false;
    assert_single_blocker(
        account_write,
        NonBybitApiAllowlistBlocker::AccountManagementWriteNotDenied,
    );

    let mut contact = NonBybitApiAllowlistV1::accepted_fixture();
    contact.ibkr_contact_performed = true;
    assert_single_blocker(contact, NonBybitApiAllowlistBlocker::IbkrContactPerformed);

    let mut secret = NonBybitApiAllowlistV1::accepted_fixture();
    secret.secret_content_serialized = true;
    assert_single_blocker(secret, NonBybitApiAllowlistBlocker::SecretContentSerialized);

    let mut bybit = NonBybitApiAllowlistV1::accepted_fixture();
    bybit.bybit_live_execution_protected = false;
    assert_single_blocker(
        bybit,
        NonBybitApiAllowlistBlocker::BybitLiveExecutionNotProtected,
    );
}

fn assert_single_blocker(allowlist: NonBybitApiAllowlistV1, blocker: NonBybitApiAllowlistBlocker) {
    let verdict = allowlist.validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![blocker],
        "expected only {blocker:?}; blockers: {:?}",
        verdict.blockers
    );
}
