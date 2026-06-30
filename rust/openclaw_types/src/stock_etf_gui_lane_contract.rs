//! Stock/ETF GUI lane contract for ADR-0048.
//!
//! This source-only validator defines the GUI boundary artifact shape. It does
//! not serve pages, contact IBKR, read secrets, route orders, or authorize lane
//! selection.

use serde::{Deserialize, Serialize};

use crate::ibkr_phase2_artifact::is_sha256_hex;
use crate::stock_etf_lane::AssetLane;

pub const STOCK_ETF_GUI_LANE_CONTRACT_ID: &str = "gui_lane_contract_v1";
pub const STOCK_ETF_GUI_READINESS_ENDPOINT: &str = "/api/v1/stock-etf/readiness";
pub const STOCK_ETF_GUI_LANE_STATUS_ENDPOINT: &str = "/api/v1/stock-etf/lane-status";
pub const STOCK_ETF_GUI_DATA_FOUNDATION_STATUS_ENDPOINT: &str =
    "/api/v1/stock-etf/data-foundation-status";
pub const STOCK_ETF_GUI_POLICY_STATUS_ENDPOINT: &str = "/api/v1/stock-etf/policy-status";
pub const STOCK_ETF_GUI_AUTHORIZATION_STATUS_ENDPOINT: &str =
    "/api/v1/stock-etf/authorization-status";
pub const STOCK_ETF_GUI_ACCOUNT_STATUS_ENDPOINT: &str = "/api/v1/stock-etf/account-status";
pub const STOCK_ETF_GUI_EVIDENCE_STATUS_ENDPOINT: &str = "/api/v1/stock-etf/evidence-status";
pub const STOCK_ETF_GUI_UNIVERSE_STATUS_ENDPOINT: &str = "/api/v1/stock-etf/universe-status";
pub const STOCK_ETF_GUI_SHADOW_STATUS_ENDPOINT: &str = "/api/v1/stock-etf/shadow-status";
pub const STOCK_ETF_GUI_PAPER_STATUS_ENDPOINT: &str = "/api/v1/stock-etf/paper-status";
pub const STOCK_ETF_GUI_RECONCILIATION_STATUS_ENDPOINT: &str =
    "/api/v1/stock-etf/reconciliation-status";
pub const STOCK_ETF_GUI_SCORECARD_STATUS_ENDPOINT: &str = "/api/v1/stock-etf/scorecard-status";
pub const STOCK_ETF_GUI_LAUNCH_STATUS_ENDPOINT: &str = "/api/v1/stock-etf/launch-status";
pub const STOCK_ETF_GUI_DISABLE_CLEANUP_STATUS_ENDPOINT: &str =
    "/api/v1/stock-etf/disable-cleanup-status";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfGuiLaneContractV1 {
    pub contract_id: String,
    pub source_version: u32,
    pub default_asset_lane: AssetLane,
    pub stock_etf_tab_registered: bool,
    pub readiness_endpoint: String,
    pub readiness_endpoint_get_only: bool,
    pub lane_status_endpoint: String,
    pub lane_status_endpoint_get_only: bool,
    pub data_foundation_status_endpoint: String,
    pub data_foundation_status_endpoint_get_only: bool,
    pub policy_status_endpoint: String,
    pub policy_status_endpoint_get_only: bool,
    pub authorization_status_endpoint: String,
    pub authorization_status_endpoint_get_only: bool,
    pub account_status_endpoint: String,
    pub account_status_endpoint_get_only: bool,
    pub evidence_status_endpoint: String,
    pub evidence_status_endpoint_get_only: bool,
    pub universe_status_endpoint: String,
    pub universe_status_endpoint_get_only: bool,
    pub shadow_status_endpoint: String,
    pub shadow_status_endpoint_get_only: bool,
    pub paper_status_endpoint: String,
    pub paper_status_endpoint_get_only: bool,
    pub reconciliation_status_endpoint: String,
    pub reconciliation_status_endpoint_get_only: bool,
    pub scorecard_status_endpoint: String,
    pub scorecard_status_endpoint_get_only: bool,
    pub launch_status_endpoint: String,
    pub launch_status_endpoint_get_only: bool,
    pub disable_cleanup_status_endpoint: String,
    pub disable_cleanup_status_endpoint_get_only: bool,
    pub display_only: bool,
    pub client_lane_state_untrusted: bool,
    pub local_storage_authority_denied: bool,
    pub query_param_authority_denied: bool,
    pub hidden_field_authority_denied: bool,
    pub no_login_success_selector: bool,
    pub no_post_routes: bool,
    pub no_order_widgets: bool,
    pub no_secret_widgets: bool,
    pub no_ibkr_contact_on_render: bool,
    pub paper_order_entry_hidden: bool,
    pub stock_live_disabled_display: bool,
    pub cfd_surface_hidden_or_fail_closed: bool,
    pub route_cache_partition_required: bool,
    pub auth_partition_required: bool,
    pub stale_cache_cross_lane_denied: bool,
    pub crypto_tabs_regression_passed: bool,
    pub decision_lease_risk_regression_passed: bool,
    pub static_source_hash: String,
    pub route_test_hash: String,
    pub crypto_regression_hash: String,
    pub denied_effect_operations: Vec<String>,
    pub ibkr_contact_performed: bool,
    pub secret_content_serialized: bool,
}

impl Default for StockEtfGuiLaneContractV1 {
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            default_asset_lane: AssetLane::CryptoPerp,
            stock_etf_tab_registered: false,
            readiness_endpoint: String::new(),
            readiness_endpoint_get_only: false,
            lane_status_endpoint: String::new(),
            lane_status_endpoint_get_only: false,
            data_foundation_status_endpoint: String::new(),
            data_foundation_status_endpoint_get_only: false,
            policy_status_endpoint: String::new(),
            policy_status_endpoint_get_only: false,
            authorization_status_endpoint: String::new(),
            authorization_status_endpoint_get_only: false,
            account_status_endpoint: String::new(),
            account_status_endpoint_get_only: false,
            evidence_status_endpoint: String::new(),
            evidence_status_endpoint_get_only: false,
            universe_status_endpoint: String::new(),
            universe_status_endpoint_get_only: false,
            shadow_status_endpoint: String::new(),
            shadow_status_endpoint_get_only: false,
            paper_status_endpoint: String::new(),
            paper_status_endpoint_get_only: false,
            reconciliation_status_endpoint: String::new(),
            reconciliation_status_endpoint_get_only: false,
            scorecard_status_endpoint: String::new(),
            scorecard_status_endpoint_get_only: false,
            launch_status_endpoint: String::new(),
            launch_status_endpoint_get_only: false,
            disable_cleanup_status_endpoint: String::new(),
            disable_cleanup_status_endpoint_get_only: false,
            display_only: false,
            client_lane_state_untrusted: false,
            local_storage_authority_denied: false,
            query_param_authority_denied: false,
            hidden_field_authority_denied: false,
            no_login_success_selector: false,
            no_post_routes: false,
            no_order_widgets: false,
            no_secret_widgets: false,
            no_ibkr_contact_on_render: false,
            paper_order_entry_hidden: false,
            stock_live_disabled_display: false,
            cfd_surface_hidden_or_fail_closed: false,
            route_cache_partition_required: false,
            auth_partition_required: false,
            stale_cache_cross_lane_denied: false,
            crypto_tabs_regression_passed: false,
            decision_lease_risk_regression_passed: false,
            static_source_hash: String::new(),
            route_test_hash: String::new(),
            crypto_regression_hash: String::new(),
            denied_effect_operations: Vec::new(),
            ibkr_contact_performed: false,
            secret_content_serialized: false,
        }
    }
}

impl StockEtfGuiLaneContractV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            contract_id: STOCK_ETF_GUI_LANE_CONTRACT_ID.to_string(),
            source_version: 1,
            default_asset_lane: AssetLane::CryptoPerp,
            stock_etf_tab_registered: true,
            readiness_endpoint: STOCK_ETF_GUI_READINESS_ENDPOINT.to_string(),
            readiness_endpoint_get_only: true,
            lane_status_endpoint: STOCK_ETF_GUI_LANE_STATUS_ENDPOINT.to_string(),
            lane_status_endpoint_get_only: true,
            data_foundation_status_endpoint: STOCK_ETF_GUI_DATA_FOUNDATION_STATUS_ENDPOINT
                .to_string(),
            data_foundation_status_endpoint_get_only: true,
            policy_status_endpoint: STOCK_ETF_GUI_POLICY_STATUS_ENDPOINT.to_string(),
            policy_status_endpoint_get_only: true,
            authorization_status_endpoint: STOCK_ETF_GUI_AUTHORIZATION_STATUS_ENDPOINT.to_string(),
            authorization_status_endpoint_get_only: true,
            account_status_endpoint: STOCK_ETF_GUI_ACCOUNT_STATUS_ENDPOINT.to_string(),
            account_status_endpoint_get_only: true,
            evidence_status_endpoint: STOCK_ETF_GUI_EVIDENCE_STATUS_ENDPOINT.to_string(),
            evidence_status_endpoint_get_only: true,
            universe_status_endpoint: STOCK_ETF_GUI_UNIVERSE_STATUS_ENDPOINT.to_string(),
            universe_status_endpoint_get_only: true,
            shadow_status_endpoint: STOCK_ETF_GUI_SHADOW_STATUS_ENDPOINT.to_string(),
            shadow_status_endpoint_get_only: true,
            paper_status_endpoint: STOCK_ETF_GUI_PAPER_STATUS_ENDPOINT.to_string(),
            paper_status_endpoint_get_only: true,
            reconciliation_status_endpoint: STOCK_ETF_GUI_RECONCILIATION_STATUS_ENDPOINT
                .to_string(),
            reconciliation_status_endpoint_get_only: true,
            scorecard_status_endpoint: STOCK_ETF_GUI_SCORECARD_STATUS_ENDPOINT.to_string(),
            scorecard_status_endpoint_get_only: true,
            launch_status_endpoint: STOCK_ETF_GUI_LAUNCH_STATUS_ENDPOINT.to_string(),
            launch_status_endpoint_get_only: true,
            disable_cleanup_status_endpoint: STOCK_ETF_GUI_DISABLE_CLEANUP_STATUS_ENDPOINT
                .to_string(),
            disable_cleanup_status_endpoint_get_only: true,
            display_only: true,
            client_lane_state_untrusted: true,
            local_storage_authority_denied: true,
            query_param_authority_denied: true,
            hidden_field_authority_denied: true,
            no_login_success_selector: true,
            no_post_routes: true,
            no_order_widgets: true,
            no_secret_widgets: true,
            no_ibkr_contact_on_render: true,
            paper_order_entry_hidden: true,
            stock_live_disabled_display: true,
            cfd_surface_hidden_or_fail_closed: true,
            route_cache_partition_required: true,
            auth_partition_required: true,
            stale_cache_cross_lane_denied: true,
            crypto_tabs_regression_passed: true,
            decision_lease_risk_regression_passed: true,
            static_source_hash: "1".repeat(64),
            route_test_hash: "2".repeat(64),
            crypto_regression_hash: "3".repeat(64),
            denied_effect_operations: vec![
                "ibkr_live_order_submit".to_string(),
                "ibkr_tiny_live".to_string(),
                "ibkr_secret_slot_creation".to_string(),
                "ibkr_api_contact_before_phase2_gate".to_string(),
            ],
            ibkr_contact_performed: false,
            secret_content_serialized: false,
        }
    }

    pub fn validate(&self) -> StockEtfGuiLaneVerdict<StockEtfGuiLaneBlocker> {
        use StockEtfGuiLaneBlocker as Blocker;

        let mut blockers = Vec::new();
        if self.contract_id.trim().is_empty() {
            blockers.push(Blocker::ContractIdMissing);
        } else if self.contract_id != STOCK_ETF_GUI_LANE_CONTRACT_ID {
            blockers.push(Blocker::ContractIdMismatch);
        }
        if self.source_version != 1 {
            blockers.push(Blocker::SourceVersionMismatch);
        }
        if self.default_asset_lane != AssetLane::CryptoPerp {
            blockers.push(Blocker::DefaultLaneNotCryptoPerp);
        }
        if !self.stock_etf_tab_registered {
            blockers.push(Blocker::StockEtfTabMissing);
        }
        if self.readiness_endpoint != STOCK_ETF_GUI_READINESS_ENDPOINT {
            blockers.push(Blocker::ReadinessEndpointMismatch);
        }
        if !self.readiness_endpoint_get_only {
            blockers.push(Blocker::ReadinessEndpointNotGetOnly);
        }
        if self.lane_status_endpoint != STOCK_ETF_GUI_LANE_STATUS_ENDPOINT {
            blockers.push(Blocker::LaneStatusEndpointMismatch);
        }
        if !self.lane_status_endpoint_get_only {
            blockers.push(Blocker::LaneStatusEndpointNotGetOnly);
        }
        if self.data_foundation_status_endpoint != STOCK_ETF_GUI_DATA_FOUNDATION_STATUS_ENDPOINT {
            blockers.push(Blocker::DataFoundationStatusEndpointMismatch);
        }
        if !self.data_foundation_status_endpoint_get_only {
            blockers.push(Blocker::DataFoundationStatusEndpointNotGetOnly);
        }
        if self.policy_status_endpoint != STOCK_ETF_GUI_POLICY_STATUS_ENDPOINT {
            blockers.push(Blocker::PolicyStatusEndpointMismatch);
        }
        if !self.policy_status_endpoint_get_only {
            blockers.push(Blocker::PolicyStatusEndpointNotGetOnly);
        }
        if self.authorization_status_endpoint != STOCK_ETF_GUI_AUTHORIZATION_STATUS_ENDPOINT {
            blockers.push(Blocker::AuthorizationStatusEndpointMismatch);
        }
        if !self.authorization_status_endpoint_get_only {
            blockers.push(Blocker::AuthorizationStatusEndpointNotGetOnly);
        }
        if self.account_status_endpoint != STOCK_ETF_GUI_ACCOUNT_STATUS_ENDPOINT {
            blockers.push(Blocker::AccountStatusEndpointMismatch);
        }
        if !self.account_status_endpoint_get_only {
            blockers.push(Blocker::AccountStatusEndpointNotGetOnly);
        }
        if self.evidence_status_endpoint != STOCK_ETF_GUI_EVIDENCE_STATUS_ENDPOINT {
            blockers.push(Blocker::EvidenceStatusEndpointMismatch);
        }
        if !self.evidence_status_endpoint_get_only {
            blockers.push(Blocker::EvidenceStatusEndpointNotGetOnly);
        }
        if self.universe_status_endpoint != STOCK_ETF_GUI_UNIVERSE_STATUS_ENDPOINT {
            blockers.push(Blocker::UniverseStatusEndpointMismatch);
        }
        if !self.universe_status_endpoint_get_only {
            blockers.push(Blocker::UniverseStatusEndpointNotGetOnly);
        }
        if self.shadow_status_endpoint != STOCK_ETF_GUI_SHADOW_STATUS_ENDPOINT {
            blockers.push(Blocker::ShadowStatusEndpointMismatch);
        }
        if !self.shadow_status_endpoint_get_only {
            blockers.push(Blocker::ShadowStatusEndpointNotGetOnly);
        }
        if self.paper_status_endpoint != STOCK_ETF_GUI_PAPER_STATUS_ENDPOINT {
            blockers.push(Blocker::PaperStatusEndpointMismatch);
        }
        if !self.paper_status_endpoint_get_only {
            blockers.push(Blocker::PaperStatusEndpointNotGetOnly);
        }
        if self.reconciliation_status_endpoint != STOCK_ETF_GUI_RECONCILIATION_STATUS_ENDPOINT {
            blockers.push(Blocker::ReconciliationStatusEndpointMismatch);
        }
        if !self.reconciliation_status_endpoint_get_only {
            blockers.push(Blocker::ReconciliationStatusEndpointNotGetOnly);
        }
        if self.scorecard_status_endpoint != STOCK_ETF_GUI_SCORECARD_STATUS_ENDPOINT {
            blockers.push(Blocker::ScorecardStatusEndpointMismatch);
        }
        if !self.scorecard_status_endpoint_get_only {
            blockers.push(Blocker::ScorecardStatusEndpointNotGetOnly);
        }
        if self.launch_status_endpoint != STOCK_ETF_GUI_LAUNCH_STATUS_ENDPOINT {
            blockers.push(Blocker::LaunchStatusEndpointMismatch);
        }
        if !self.launch_status_endpoint_get_only {
            blockers.push(Blocker::LaunchStatusEndpointNotGetOnly);
        }
        if self.disable_cleanup_status_endpoint != STOCK_ETF_GUI_DISABLE_CLEANUP_STATUS_ENDPOINT {
            blockers.push(Blocker::DisableCleanupStatusEndpointMismatch);
        }
        if !self.disable_cleanup_status_endpoint_get_only {
            blockers.push(Blocker::DisableCleanupStatusEndpointNotGetOnly);
        }
        if !self.display_only {
            blockers.push(Blocker::DisplayOnlyMissing);
        }
        if !self.client_lane_state_untrusted {
            blockers.push(Blocker::ClientLaneStateTrusted);
        }
        if !self.local_storage_authority_denied {
            blockers.push(Blocker::LocalStorageAuthorityNotDenied);
        }
        if !self.query_param_authority_denied {
            blockers.push(Blocker::QueryParamAuthorityNotDenied);
        }
        if !self.hidden_field_authority_denied {
            blockers.push(Blocker::HiddenFieldAuthorityNotDenied);
        }
        if !self.no_login_success_selector {
            blockers.push(Blocker::LoginSuccessSelectorPresent);
        }
        if !self.no_post_routes {
            blockers.push(Blocker::PostRoutePresent);
        }
        if !self.no_order_widgets {
            blockers.push(Blocker::OrderWidgetPresent);
        }
        if !self.no_secret_widgets {
            blockers.push(Blocker::SecretWidgetPresent);
        }
        if !self.no_ibkr_contact_on_render {
            blockers.push(Blocker::IbkrContactOnRenderAllowed);
        }
        if !self.paper_order_entry_hidden {
            blockers.push(Blocker::PaperOrderEntryVisible);
        }
        if !self.stock_live_disabled_display {
            blockers.push(Blocker::StockLiveDisabledDisplayMissing);
        }
        if !self.cfd_surface_hidden_or_fail_closed {
            blockers.push(Blocker::CfdSurfaceNotHiddenOrFailClosed);
        }
        if !self.route_cache_partition_required {
            blockers.push(Blocker::RouteCachePartitionMissing);
        }
        if !self.auth_partition_required {
            blockers.push(Blocker::AuthPartitionMissing);
        }
        if !self.stale_cache_cross_lane_denied {
            blockers.push(Blocker::StaleCacheCrossLaneNotDenied);
        }
        if !self.crypto_tabs_regression_passed {
            blockers.push(Blocker::CryptoTabsRegressionMissing);
        }
        if !self.decision_lease_risk_regression_passed {
            blockers.push(Blocker::DecisionLeaseRiskRegressionMissing);
        }
        if !is_sha256_hex(&self.static_source_hash) {
            blockers.push(Blocker::StaticSourceHashInvalid);
        }
        if !is_sha256_hex(&self.route_test_hash) {
            blockers.push(Blocker::RouteTestHashInvalid);
        }
        if !is_sha256_hex(&self.crypto_regression_hash) {
            blockers.push(Blocker::CryptoRegressionHashInvalid);
        }
        if !has_required_denial(&self.denied_effect_operations, "ibkr_live_order_submit") {
            blockers.push(Blocker::LiveOrderDenialMissing);
        }
        if !has_required_denial(&self.denied_effect_operations, "ibkr_secret_slot_creation") {
            blockers.push(Blocker::SecretSlotDenialMissing);
        }
        if !has_required_denial(
            &self.denied_effect_operations,
            "ibkr_api_contact_before_phase2_gate",
        ) {
            blockers.push(Blocker::PreGateContactDenialMissing);
        }
        if self.ibkr_contact_performed {
            blockers.push(Blocker::IbkrContactPerformed);
        }
        if self.secret_content_serialized {
            blockers.push(Blocker::SecretContentSerialized);
        }

        StockEtfGuiLaneVerdict::new(blockers)
    }
}

fn has_required_denial(denials: &[String], expected: &str) -> bool {
    denials.iter().any(|item| item == expected)
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfGuiLaneVerdict<B> {
    pub accepted: bool,
    pub blockers: Vec<B>,
}

impl<B> StockEtfGuiLaneVerdict<B> {
    fn new(blockers: Vec<B>) -> Self {
        Self {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfGuiLaneBlocker {
    ContractIdMissing,
    ContractIdMismatch,
    SourceVersionMismatch,
    DefaultLaneNotCryptoPerp,
    StockEtfTabMissing,
    ReadinessEndpointMismatch,
    ReadinessEndpointNotGetOnly,
    LaneStatusEndpointMismatch,
    LaneStatusEndpointNotGetOnly,
    DataFoundationStatusEndpointMismatch,
    DataFoundationStatusEndpointNotGetOnly,
    PolicyStatusEndpointMismatch,
    PolicyStatusEndpointNotGetOnly,
    AuthorizationStatusEndpointMismatch,
    AuthorizationStatusEndpointNotGetOnly,
    AccountStatusEndpointMismatch,
    AccountStatusEndpointNotGetOnly,
    EvidenceStatusEndpointMismatch,
    EvidenceStatusEndpointNotGetOnly,
    UniverseStatusEndpointMismatch,
    UniverseStatusEndpointNotGetOnly,
    ShadowStatusEndpointMismatch,
    ShadowStatusEndpointNotGetOnly,
    PaperStatusEndpointMismatch,
    PaperStatusEndpointNotGetOnly,
    ReconciliationStatusEndpointMismatch,
    ReconciliationStatusEndpointNotGetOnly,
    ScorecardStatusEndpointMismatch,
    ScorecardStatusEndpointNotGetOnly,
    LaunchStatusEndpointMismatch,
    LaunchStatusEndpointNotGetOnly,
    DisableCleanupStatusEndpointMismatch,
    DisableCleanupStatusEndpointNotGetOnly,
    DisplayOnlyMissing,
    ClientLaneStateTrusted,
    LocalStorageAuthorityNotDenied,
    QueryParamAuthorityNotDenied,
    HiddenFieldAuthorityNotDenied,
    LoginSuccessSelectorPresent,
    PostRoutePresent,
    OrderWidgetPresent,
    SecretWidgetPresent,
    IbkrContactOnRenderAllowed,
    PaperOrderEntryVisible,
    StockLiveDisabledDisplayMissing,
    CfdSurfaceNotHiddenOrFailClosed,
    RouteCachePartitionMissing,
    AuthPartitionMissing,
    StaleCacheCrossLaneNotDenied,
    CryptoTabsRegressionMissing,
    DecisionLeaseRiskRegressionMissing,
    StaticSourceHashInvalid,
    RouteTestHashInvalid,
    CryptoRegressionHashInvalid,
    LiveOrderDenialMissing,
    SecretSlotDenialMissing,
    PreGateContactDenialMissing,
    IbkrContactPerformed,
    SecretContentSerialized,
}
