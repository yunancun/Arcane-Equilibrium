//! IPC method registry.
//! IPC method registry。
//!
//! This Module records Interface metadata that otherwise gets smeared across
//! dispatch arms, handler files, and tests. It starts with slot-bound methods
//! and can grow method-by-method without changing wire behaviour.
//! 本 Module 記錄過去散在 dispatch arm / handler / tests 的 Interface metadata。

/// Runtime slot a method depends on.
/// method 依賴的 runtime slot。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum IpcSlotRequirement {
    AccountManager,
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

pub const IPC_METHOD_REGISTRY: &[IpcMethodSpec] = &[QUERY_FEE_SOURCE];

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
    fn unknown_method_has_no_registry_entry() {
        assert!(method_spec("not_a_real_method").is_none());
    }
}
