//! Stock/ETF 風控 TOML loader（source-of-record 顯示面）。
//!
//! 從 `handlers/stock_etf.rs` 抽出的 sibling 模組：把「路徑解析 + load/parse +
//! 進程級快取 + fail-closed denied 回退」集中於此，讓 handler 檔案本體不再含
//! std::fs / std::path::Path / read_to_string 等 runtime material 讀取，維持
//! 純顯示語義。handler 經 `super::stock_etf_risk_policy::{...}` 跨 sibling 呼叫。

use openclaw_types::{
    AssetLane, Broker, BrokerEnvironment, StockEtfRiskPolicySourceConfigV1, StockEtfRiskPolicyV1,
};
use std::sync::OnceLock;

/// stock_etf 風控 TOML 的進程級快取（load-once）。
///
/// 為什麼 OnceLock<Result<..>>：source-of-record 只需 boot 後載入一次；失敗也
/// 快取為 Err 以維持 fail-closed（呼叫端回退 denied fallback + 標 reason）。
static STOCK_ETF_RISK_POLICY: OnceLock<Result<StockEtfRiskPolicyV1, String>> = OnceLock::new();

/// 純載入器：從指定 dir 讀取並解析 risk_config_stock_etf_paper.toml，轉為
/// StockEtfRiskPolicyV1（顯示面 source-of-record）。
///
/// 為什麼收 dir 參數而非讀 env：把「路徑解析」與「load+parse+from_source_config
/// glue」拆開，讓測試能以真實 repo TOML 直接驗證 caps 確實被載入，繞過進程級
/// OnceLock 與 OPENCLAW_RISK_CONFIG_DIR 全域狀態（避免與同 binary 的 startup
/// 測試搶 env 造成 order-fragile）。
///
/// 為什麼回 Err 而非捏值：檔案缺失或解析失敗時**不得**捏造寬鬆 caps；呼叫端
/// 必回退 denied fallback 並標 reason（fail-closed）。
pub(in crate::ipc_server) fn load_stock_etf_risk_policy_from_dir(
    dir: &std::path::Path,
) -> Result<StockEtfRiskPolicyV1, String> {
    let path = dir.join("risk_config_stock_etf_paper.toml");
    let raw = std::fs::read_to_string(&path)
        .map_err(|e| format!("read {} failed: {e}", path.display()))?;
    let source: StockEtfRiskPolicySourceConfigV1 =
        toml::from_str(&raw).map_err(|e| format!("parse {} failed: {e}", path.display()))?;
    Ok(StockEtfRiskPolicyV1::from_source_config(&source))
}

/// 解析 settings-dir 後委派 pure loader（進程級 OnceLock 的載入來源）。
///
/// 路徑解析沿用 startup::load_unified_configs 同一套 settings-dir 約定（優先
/// OPENCLAW_RISK_CONFIG_DIR，否則相對 settings/risk_control_rules），不硬編碼
/// 平台路徑，維持跨平台可攜。
fn load_stock_etf_risk_policy() -> Result<StockEtfRiskPolicyV1, String> {
    use std::path::PathBuf;
    let base = std::env::var("OPENCLAW_RISK_CONFIG_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from("settings/risk_control_rules"));
    load_stock_etf_risk_policy_from_dir(&base)
}

/// 進程級快取存取（load-once）；返回 &'static Result 供呼叫端 clone。
/// 首次載入失敗時 warn 一次（OnceLock 保證只發生一次，避免每次 IPC 洗版）。
pub(in crate::ipc_server) fn stock_etf_risk_policy() -> &'static Result<StockEtfRiskPolicyV1, String>
{
    STOCK_ETF_RISK_POLICY.get_or_init(|| {
        let loaded = load_stock_etf_risk_policy();
        if let Err(e) = &loaded {
            tracing::warn!(
                error = %e,
                "stock_etf risk policy load failed; using denied fallback / 顯示面回退 denied"
            );
        }
        loaded
    })
}

/// fail-closed 顯示回退：TOML 載入失敗時使用的 denied policy。
///
/// 為什麼不用裸 default()：default() 的 allow_* 皆為 true（雖 validate() 仍判為
/// blocker），GUI 直接顯示會誤導成「允許保證金/做空」。此處顯式全 false，確保
/// 載入失敗時顯示面**不**出現任何寬鬆 cap/flag（NEVER fabricate permissive caps）。
pub(in crate::ipc_server) fn denied_stock_etf_risk_policy_fallback() -> StockEtfRiskPolicyV1 {
    StockEtfRiskPolicyV1 {
        asset_lane: AssetLane::StockEtfCash,
        broker: Broker::Ibkr,
        environment: BrokerEnvironment::Paper,
        enabled: false,
        shadow_only: true,
        allow_margin: false,
        allow_short: false,
        allow_options: false,
        allow_cfd: false,
        allow_transfer: false,
        allow_live: false,
        bybit_live_execution_unchanged: true,
        ..StockEtfRiskPolicyV1::default()
    }
}
