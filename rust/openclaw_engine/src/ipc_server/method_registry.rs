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

/// Phase 2 demo→live 促升 EDGE-ANCHORED criteria gate（唯讀）。
/// slot=None：edge snapshot 由 `dispatch::PROMOTION_EDGE_SLOT` 程序級 OnceLock
/// 注入（鏡像 `live_authz::nonce_ledger()`），非 dispatch 參數鏈 slot，故此處
/// 標 None。readonly=true：**不在** `live_authz::LIVE_WRITE_METHODS`，token 豁免。
pub const EVALUATE_PROMOTION_CRITERIA: IpcMethodSpec = IpcMethodSpec {
    name: "evaluate_promotion_criteria",
    readonly: true,
    slot: IpcSlotRequirement::None,
};

pub const IPC_METHOD_REGISTRY: &[IpcMethodSpec] = &[
    QUERY_FEE_SOURCE,
    GET_AGENT_SPINE_CHANNEL_METRICS,
    EVALUATE_PROMOTION_CRITERIA,
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
}
