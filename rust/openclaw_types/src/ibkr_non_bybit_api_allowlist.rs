//! IBKR non-Bybit API allowlist contract for ADR-0048.
//!
//! This source-only contract pins the IB Gateway/TWS API read, paper-write, and
//! denied action matrix. It performs no socket I/O, no secret lookup, no IBKR
//! client construction, and no broker order routing.

use serde::{Deserialize, Serialize};

use crate::ibkr_phase2_gate::IbkrApiBaseline;

pub const NON_BYBIT_API_ALLOWLIST_CONTRACT_ID: &str = "non_bybit_api_allowlist_v1";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NonBybitApiAction {
    ServerTimeRead,
    ConnectionHealthRead,
    AccountSummarySnapshotRead,
    PortfolioPositionsSnapshotRead,
    ContractDetailsRead,
    MarketDataSnapshotRead,
    MarketDataSubscriptionRead,
    HistoricalBarsRead,
    OpenPaperOrdersRead,
    PaperExecutionsCommissionsRead,
    PaperOrderSubmit,
    PaperOrderCancel,
    PaperOrderReplace,
    LiveOrderSubmit,
    LiveAccountQuery,
    AccountTransfer,
    MarginEnablement,
    ShortBorrow,
    OptionsTrading,
    CfdTrading,
    MarketDataEntitlementPurchase,
    AccountManagementWrite,
    ClientPortalWebApiUse,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NonBybitApiDenialReason {
    LiveOrderDenied,
    LiveAccountFingerprintDenied,
    AccountTransferDenied,
    MarginDenied,
    ShortDenied,
    OptionsDenied,
    CfdDenied,
    MarketDataEntitlementPurchaseDenied,
    AccountManagementWriteDenied,
    ClientPortalWebApiDenied,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct NonBybitApiAllowlistDecision {
    pub action: NonBybitApiAction,
    pub allowed_after_external_gate: bool,
    pub requires_external_surface_gate: bool,
    pub requires_session_attestation: bool,
    pub requires_paper_order_gates: bool,
    pub denied: bool,
    pub denial_reason: Option<NonBybitApiDenialReason>,
}

impl NonBybitApiAllowlistDecision {
    const fn allowed_read(action: NonBybitApiAction, requires_session_attestation: bool) -> Self {
        Self {
            action,
            allowed_after_external_gate: true,
            requires_external_surface_gate: true,
            requires_session_attestation,
            requires_paper_order_gates: false,
            denied: false,
            denial_reason: None,
        }
    }

    const fn paper_write(action: NonBybitApiAction) -> Self {
        Self {
            action,
            allowed_after_external_gate: false,
            requires_external_surface_gate: true,
            requires_session_attestation: true,
            requires_paper_order_gates: true,
            denied: false,
            denial_reason: None,
        }
    }

    const fn denied(action: NonBybitApiAction, denial_reason: NonBybitApiDenialReason) -> Self {
        Self {
            action,
            allowed_after_external_gate: false,
            requires_external_surface_gate: false,
            requires_session_attestation: false,
            requires_paper_order_gates: false,
            denied: true,
            denial_reason: Some(denial_reason),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct NonBybitApiAllowlistV1 {
    pub contract_id: String,
    pub source_version: u32,
    pub api_baseline: IbkrApiBaseline,
    pub read_actions: Vec<NonBybitApiAction>,
    pub paper_write_actions: Vec<NonBybitApiAction>,
    pub denied_actions: Vec<NonBybitApiAction>,
    pub client_portal_web_api_denied: bool,
    pub live_order_denied: bool,
    pub account_transfer_denied: bool,
    pub margin_short_options_cfd_denied: bool,
    pub market_data_entitlement_purchase_denied: bool,
    pub account_management_write_denied: bool,
    pub ibkr_contact_performed: bool,
    pub secret_content_serialized: bool,
    pub bybit_live_execution_protected: bool,
}

impl Default for NonBybitApiAllowlistV1 {
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            api_baseline: IbkrApiBaseline::IbGatewayTwsApi,
            read_actions: Vec::new(),
            paper_write_actions: Vec::new(),
            denied_actions: Vec::new(),
            client_portal_web_api_denied: false,
            live_order_denied: false,
            account_transfer_denied: false,
            margin_short_options_cfd_denied: false,
            market_data_entitlement_purchase_denied: false,
            account_management_write_denied: false,
            ibkr_contact_performed: false,
            secret_content_serialized: false,
            bybit_live_execution_protected: false,
        }
    }
}

impl NonBybitApiAllowlistV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            contract_id: NON_BYBIT_API_ALLOWLIST_CONTRACT_ID.to_string(),
            source_version: 1,
            api_baseline: IbkrApiBaseline::IbGatewayTwsApi,
            read_actions: vec![
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
            ],
            paper_write_actions: vec![
                NonBybitApiAction::PaperOrderSubmit,
                NonBybitApiAction::PaperOrderCancel,
                NonBybitApiAction::PaperOrderReplace,
            ],
            denied_actions: vec![
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
            ],
            client_portal_web_api_denied: true,
            live_order_denied: true,
            account_transfer_denied: true,
            margin_short_options_cfd_denied: true,
            market_data_entitlement_purchase_denied: true,
            account_management_write_denied: true,
            ibkr_contact_performed: false,
            secret_content_serialized: false,
            bybit_live_execution_protected: true,
        }
    }

    pub fn validate(&self) -> NonBybitApiAllowlistVerdict {
        use NonBybitApiAllowlistBlocker as Blocker;

        let mut blockers = Vec::new();
        if self.contract_id != NON_BYBIT_API_ALLOWLIST_CONTRACT_ID {
            blockers.push(Blocker::ContractIdMismatch);
        }
        if self.source_version != 1 {
            blockers.push(Blocker::SourceVersionMismatch);
        }
        if self.api_baseline != IbkrApiBaseline::IbGatewayTwsApi {
            blockers.push(Blocker::ApiBaselineMismatch);
        }
        validate_allowlist_actions(self, &mut blockers);
        if !self.client_portal_web_api_denied {
            blockers.push(Blocker::ClientPortalWebApiNotDenied);
        }
        if !self.live_order_denied {
            blockers.push(Blocker::LiveOrderNotDenied);
        }
        if !self.account_transfer_denied {
            blockers.push(Blocker::AccountTransferNotDenied);
        }
        if !self.margin_short_options_cfd_denied {
            blockers.push(Blocker::MarginShortOptionsCfdNotDenied);
        }
        if !self.market_data_entitlement_purchase_denied {
            blockers.push(Blocker::MarketDataEntitlementPurchaseNotDenied);
        }
        if !self.account_management_write_denied {
            blockers.push(Blocker::AccountManagementWriteNotDenied);
        }
        if self.ibkr_contact_performed {
            blockers.push(Blocker::IbkrContactPerformed);
        }
        if self.secret_content_serialized {
            blockers.push(Blocker::SecretContentSerialized);
        }
        if !self.bybit_live_execution_protected {
            blockers.push(Blocker::BybitLiveExecutionNotProtected);
        }

        NonBybitApiAllowlistVerdict {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct NonBybitApiAllowlistVerdict {
    pub accepted: bool,
    pub blockers: Vec<NonBybitApiAllowlistBlocker>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NonBybitApiAllowlistBlocker {
    ContractIdMismatch,
    SourceVersionMismatch,
    ApiBaselineMismatch,
    ActionMissing,
    ActionDuplicated,
    ActionInWrongBucket,
    ClientPortalWebApiNotDenied,
    LiveOrderNotDenied,
    AccountTransferNotDenied,
    MarginShortOptionsCfdNotDenied,
    MarketDataEntitlementPurchaseNotDenied,
    AccountManagementWriteNotDenied,
    IbkrContactPerformed,
    SecretContentSerialized,
    BybitLiveExecutionNotProtected,
}

pub const fn classify_non_bybit_api_action(
    action: NonBybitApiAction,
) -> NonBybitApiAllowlistDecision {
    use NonBybitApiAction as Action;
    use NonBybitApiDenialReason as Deny;

    match action {
        Action::ServerTimeRead
        | Action::ConnectionHealthRead
        | Action::ContractDetailsRead
        | Action::MarketDataSnapshotRead
        | Action::MarketDataSubscriptionRead
        | Action::HistoricalBarsRead => NonBybitApiAllowlistDecision::allowed_read(action, false),
        Action::AccountSummarySnapshotRead
        | Action::PortfolioPositionsSnapshotRead
        | Action::OpenPaperOrdersRead
        | Action::PaperExecutionsCommissionsRead => {
            NonBybitApiAllowlistDecision::allowed_read(action, true)
        }
        Action::PaperOrderSubmit | Action::PaperOrderCancel | Action::PaperOrderReplace => {
            NonBybitApiAllowlistDecision::paper_write(action)
        }
        Action::LiveOrderSubmit => {
            NonBybitApiAllowlistDecision::denied(action, Deny::LiveOrderDenied)
        }
        Action::LiveAccountQuery => {
            NonBybitApiAllowlistDecision::denied(action, Deny::LiveAccountFingerprintDenied)
        }
        Action::AccountTransfer => {
            NonBybitApiAllowlistDecision::denied(action, Deny::AccountTransferDenied)
        }
        Action::MarginEnablement => {
            NonBybitApiAllowlistDecision::denied(action, Deny::MarginDenied)
        }
        Action::ShortBorrow => NonBybitApiAllowlistDecision::denied(action, Deny::ShortDenied),
        Action::OptionsTrading => NonBybitApiAllowlistDecision::denied(action, Deny::OptionsDenied),
        Action::CfdTrading => NonBybitApiAllowlistDecision::denied(action, Deny::CfdDenied),
        Action::MarketDataEntitlementPurchase => {
            NonBybitApiAllowlistDecision::denied(action, Deny::MarketDataEntitlementPurchaseDenied)
        }
        Action::AccountManagementWrite => {
            NonBybitApiAllowlistDecision::denied(action, Deny::AccountManagementWriteDenied)
        }
        Action::ClientPortalWebApiUse => {
            NonBybitApiAllowlistDecision::denied(action, Deny::ClientPortalWebApiDenied)
        }
    }
}

pub const fn required_non_bybit_api_actions() -> &'static [NonBybitApiAction] {
    &[
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
        NonBybitApiAction::PaperOrderSubmit,
        NonBybitApiAction::PaperOrderCancel,
        NonBybitApiAction::PaperOrderReplace,
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
}

fn validate_allowlist_actions(
    allowlist: &NonBybitApiAllowlistV1,
    blockers: &mut Vec<NonBybitApiAllowlistBlocker>,
) {
    use NonBybitApiAllowlistBlocker as Blocker;

    for action in required_non_bybit_api_actions() {
        let read_count = count_action(&allowlist.read_actions, *action);
        let paper_count = count_action(&allowlist.paper_write_actions, *action);
        let denied_count = count_action(&allowlist.denied_actions, *action);
        let total_count = read_count + paper_count + denied_count;
        if total_count == 0 {
            blockers.push(Blocker::ActionMissing);
        }
        if total_count > 1 {
            blockers.push(Blocker::ActionDuplicated);
        }

        let decision = classify_non_bybit_api_action(*action);
        let in_correct_bucket = if decision.denied {
            denied_count == 1 && read_count == 0 && paper_count == 0
        } else if decision.requires_paper_order_gates {
            paper_count == 1 && read_count == 0 && denied_count == 0
        } else {
            read_count == 1 && paper_count == 0 && denied_count == 0
        };
        if total_count > 0 && !in_correct_bucket {
            blockers.push(Blocker::ActionInWrongBucket);
        }
    }
}

fn count_action(actions: &[NonBybitApiAction], expected: NonBybitApiAction) -> usize {
    actions.iter().filter(|action| **action == expected).count()
}
