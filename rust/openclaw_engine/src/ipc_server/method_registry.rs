//! IPC method registry.
//! IPC method registry。
//!
//! This Module records Interface metadata that otherwise gets smeared across
//! dispatch arms, handler files, and tests.
//!
//! Descriptive metadata only, NOT an authorization/enforcement surface: the
//! registry never gates who may call a method or whether a call is permitted.
//! Real auth = connection HMAC (SEC-08) + the Python 5-gate. Adding or omitting
//! an entry here changes neither wire behaviour nor access control.
//! 本 Module 記錄過去散在 dispatch arm / handler / tests 的 Interface metadata。
//! 純描述性 metadata，非授權/強制面：不決定誰可呼叫、是否放行。真正授權 =
//! 連線 HMAC（SEC-08）+ Python 5-gate；增刪此處條目不改 wire 行為也不改存取控制。

/// Runtime slot a method depends on.
/// method 依賴的 runtime slot。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum IpcSlotRequirement {
    AccountManager,
    None,
}

/// Stable method metadata used by dispatch/tests.
/// dispatch/tests 使用的穩定 method metadata。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct IpcMethodSpec {
    pub name: &'static str,
    pub readonly: bool,
    pub slot: IpcSlotRequirement,
}

pub const QUERY_FEE_SOURCE: IpcMethodSpec = IpcMethodSpec {
    name: "query_fee_source",
    readonly: true,
    slot: IpcSlotRequirement::AccountManager,
};

pub const GET_AGENT_SPINE_CHANNEL_METRICS: IpcMethodSpec = IpcMethodSpec {
    name: "get_agent_spine_channel_metrics",
    readonly: true,
    slot: IpcSlotRequirement::None,
};

/// Sprint 1B Earn Wave D asset-movement entry.
/// readonly=false because the owner task may submit an Earn stake once the
/// Earn capability is wired. slot=None because the capability lives inside
/// the per-pipeline `IntentProcessor`, not an IPC-server global slot.
pub const PROCESS_EARN_INTENT: IpcMethodSpec = IpcMethodSpec {
    name: "process_earn_intent",
    readonly: false,
    slot: IpcSlotRequirement::None,
};

/// Phase 2 demo→live 促升 EDGE-ANCHORED criteria gate（唯讀）。
/// slot=None：edge snapshot 由 `dispatch::PROMOTION_EDGE_SLOT` 程序級 OnceLock
/// 注入（鏡像 `live_authz::nonce_ledger()`），非 dispatch 參數鏈 slot，故此處
/// 標 None。readonly=true：**不在** `live_authz::LIVE_WRITE_METHODS`，token 豁免。
pub const EVALUATE_PROMOTION_CRITERIA: IpcMethodSpec = IpcMethodSpec {
    name: "evaluate_promotion_criteria",
    readonly: true,
    slot: IpcSlotRequirement::None,
};

pub const STOCK_ETF_GET_LANE_STATUS: IpcMethodSpec = IpcMethodSpec {
    name: "stock_etf.get_lane_status",
    readonly: true,
    slot: IpcSlotRequirement::None,
};

pub const STOCK_ETF_GET_READINESS: IpcMethodSpec = IpcMethodSpec {
    name: "stock_etf.get_readiness",
    readonly: true,
    slot: IpcSlotRequirement::None,
};

pub const STOCK_ETF_GET_EVIDENCE_STATUS: IpcMethodSpec = IpcMethodSpec {
    name: "stock_etf.get_evidence_status",
    readonly: true,
    slot: IpcSlotRequirement::None,
};

pub const STOCK_ETF_GET_UNIVERSE_STATUS: IpcMethodSpec = IpcMethodSpec {
    name: "stock_etf.get_universe_status",
    readonly: true,
    slot: IpcSlotRequirement::None,
};

pub const STOCK_ETF_GET_SHADOW_STATUS: IpcMethodSpec = IpcMethodSpec {
    name: "stock_etf.get_shadow_status",
    readonly: true,
    slot: IpcSlotRequirement::None,
};

pub const STOCK_ETF_PREVIEW_PAPER_ORDER: IpcMethodSpec = IpcMethodSpec {
    name: "stock_etf.preview_paper_order",
    readonly: true,
    slot: IpcSlotRequirement::None,
};

pub const STOCK_ETF_SUBMIT_PAPER_ORDER: IpcMethodSpec = IpcMethodSpec {
    name: "stock_etf.submit_paper_order",
    readonly: false,
    slot: IpcSlotRequirement::None,
};

pub const STOCK_ETF_CANCEL_PAPER_ORDER: IpcMethodSpec = IpcMethodSpec {
    name: "stock_etf.cancel_paper_order",
    readonly: false,
    slot: IpcSlotRequirement::None,
};

pub const STOCK_ETF_REPLACE_PAPER_ORDER: IpcMethodSpec = IpcMethodSpec {
    name: "stock_etf.replace_paper_order",
    readonly: false,
    slot: IpcSlotRequirement::None,
};

pub const STOCK_ETF_IMPORT_PAPER_FILLS: IpcMethodSpec = IpcMethodSpec {
    name: "stock_etf.import_paper_fills",
    readonly: true,
    slot: IpcSlotRequirement::None,
};

pub const STOCK_ETF_EVALUATE_SHADOW_SIGNAL: IpcMethodSpec = IpcMethodSpec {
    name: "stock_etf.evaluate_shadow_signal",
    readonly: true,
    slot: IpcSlotRequirement::None,
};

pub const IPC_METHOD_REGISTRY: &[IpcMethodSpec] = &[
    QUERY_FEE_SOURCE,
    GET_AGENT_SPINE_CHANNEL_METRICS,
    PROCESS_EARN_INTENT,
    EVALUATE_PROMOTION_CRITERIA,
    STOCK_ETF_GET_LANE_STATUS,
    STOCK_ETF_GET_READINESS,
    STOCK_ETF_GET_EVIDENCE_STATUS,
    STOCK_ETF_GET_UNIVERSE_STATUS,
    STOCK_ETF_GET_SHADOW_STATUS,
    STOCK_ETF_PREVIEW_PAPER_ORDER,
    STOCK_ETF_SUBMIT_PAPER_ORDER,
    STOCK_ETF_CANCEL_PAPER_ORDER,
    STOCK_ETF_REPLACE_PAPER_ORDER,
    STOCK_ETF_IMPORT_PAPER_FILLS,
    STOCK_ETF_EVALUATE_SHADOW_SIGNAL,
];

pub fn method_spec(name: &str) -> Option<&'static IpcMethodSpec> {
    IPC_METHOD_REGISTRY.iter().find(|spec| spec.name == name)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn query_fee_source_declares_account_manager_slot() {
        let spec = method_spec("query_fee_source").expect("registered method");
        assert!(spec.readonly);
        assert_eq!(spec.slot, IpcSlotRequirement::AccountManager);
    }

    #[test]
    fn agent_spine_channel_metrics_declares_no_slot() {
        let spec = method_spec("get_agent_spine_channel_metrics").expect("registered method");
        assert!(spec.readonly);
        assert_eq!(spec.slot, IpcSlotRequirement::None);
    }

    #[test]
    fn unknown_method_has_no_registry_entry() {
        assert!(method_spec("not_a_real_method").is_none());
    }

    #[test]
    fn process_earn_intent_is_mutating_no_ipc_slot() {
        let spec = method_spec("process_earn_intent").expect("registered method");
        assert!(!spec.readonly, "Earn stake is an asset movement");
        assert_eq!(spec.slot, IpcSlotRequirement::None);
    }

    #[test]
    fn evaluate_promotion_criteria_is_readonly_no_slot() {
        let spec = method_spec("evaluate_promotion_criteria").expect("registered method");
        assert!(spec.readonly, "criteria gate is read-only (token-exempt)");
        assert_eq!(spec.slot, IpcSlotRequirement::None);
    }

    /// 安全不變量：promote criteria gate 是唯讀 method，**不可**進
    /// `live_authz::LIVE_WRITE_METHODS`（進了就會要求 live token，但它純讀不改
    /// state，且 Python promote route 在鑄 token 前就以此閘廉價拒——若需 token 會
    /// 死鎖判定順序）。fail-closed 方向相反：唯讀面不受 token 強制。
    #[test]
    fn evaluate_promotion_criteria_not_in_live_write_methods() {
        assert!(
            !crate::ipc_server::live_authz::LIVE_WRITE_METHODS
                .contains(&"evaluate_promotion_criteria"),
            "read-only criteria gate must stay token-exempt (NOT a live mutator)"
        );
    }

    #[test]
    fn stock_etf_methods_are_registered_as_lane_scoped_fixtures() {
        for name in [
            "stock_etf.get_lane_status",
            "stock_etf.get_readiness",
            "stock_etf.get_evidence_status",
            "stock_etf.get_universe_status",
            "stock_etf.get_shadow_status",
            "stock_etf.preview_paper_order",
            "stock_etf.submit_paper_order",
            "stock_etf.cancel_paper_order",
            "stock_etf.replace_paper_order",
            "stock_etf.import_paper_fills",
            "stock_etf.evaluate_shadow_signal",
        ] {
            let spec = method_spec(name).expect("stock_etf method registered");
            assert_eq!(spec.slot, IpcSlotRequirement::None);
            assert!(
                !crate::ipc_server::live_authz::LIVE_WRITE_METHODS.contains(&name),
                "stock_etf fixtures must not enter Bybit live-write token surface"
            );
        }
        assert_ne!(
            method_spec("stock_etf.submit_paper_order").unwrap().name,
            "submit_paper_order"
        );
    }

    #[test]
    fn stock_etf_registry_keeps_readonly_and_write_fixture_boundaries_explicit() {
        for name in [
            "stock_etf.get_lane_status",
            "stock_etf.get_readiness",
            "stock_etf.get_evidence_status",
            "stock_etf.get_universe_status",
            "stock_etf.get_shadow_status",
            "stock_etf.preview_paper_order",
            "stock_etf.import_paper_fills",
            "stock_etf.evaluate_shadow_signal",
        ] {
            let spec = method_spec(name).expect("stock_etf read fixture registered");
            assert!(spec.readonly, "{name} must remain a read-only fixture");
        }

        for name in [
            "stock_etf.submit_paper_order",
            "stock_etf.cancel_paper_order",
            "stock_etf.replace_paper_order",
        ] {
            let spec = method_spec(name).expect("stock_etf paper-write fixture registered");
            assert!(
                !spec.readonly,
                "{name} must stay visibly non-readonly until a separate Rust authority contract allows it"
            );
            assert_eq!(spec.slot, IpcSlotRequirement::None);
            assert!(
                !crate::ipc_server::live_authz::LIVE_WRITE_METHODS.contains(&name),
                "{name} must not enter the Bybit live-write token surface"
            );
        }

        for legacy_name in [
            "submit_paper_order",
            "cancel_paper_order",
            "replace_paper_order",
        ] {
            assert!(
                method_spec(legacy_name).is_none(),
                "{legacy_name} must not alias a Stock/ETF fixture"
            );
        }
    }
}
