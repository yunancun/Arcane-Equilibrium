//! LG-2 T2 (2026-05-11) — Live spawn pricing binding assertion。
//!
//! MODULE_NOTE：
//!   build_exchange_pipeline 對 Live (Mainnet + LiveDemo) 路徑加裝的 pre-check，
//!   位於 fee_rate 首次 refresh 之後 / Bybit private WS spawn 之前。
//!   三項斷言：
//!     A. `wait_for_first_refresh_or_timeout(30s)`：在 fee_rate refresh
//!        被 build_exchange_pipeline 內 await 過後，仍要 last_fee_refresh_ms > 0
//!        才視為「至少有一條路徑（BybitApi 或 seed_default）成功」。
//!     B. `fee_rate_count() ≥ MIN_REQUIRED_FEE_RATE_COUNT`（25 active）。
//!     C. per-symbol `FeeSource` 對照 env + cold_default_acceptable_modes：
//!        - Mainnet：任一 symbol 非 BybitApi → reject（per LG-3 RFC §2.3
//!          mainnet hard-block；不論 modes 怎麼設）。
//!        - LiveDemo：engine_mode_label = "live_demo"；若 `live_demo` 在
//!          cold_default_acceptable_modes 內 → 不 enforce per-symbol；
//!          若不在 → 任一 symbol 非 BybitApi → reject。
//!
//! 失敗時：寫 structured tracing audit log（target=
//!   `openclaw_engine::live_spawn_audit`）+ build_exchange_pipeline 回 None
//!   → pipeline 拒絕啟動。設計選擇：startup-time pre-check 在 db_pool 連線
//!   前，無法寫 PG audit row；採 systemd journalctl / engine.log 留證據，
//!   下游 healthcheck `[45]` pricing_binding 接力（runtime drift detection）。
//!
//! 不影響 paper / demo 路徑（per PA tech plan §2.5 risk #1）。
//!
//! 對齊 CLAUDE.md §四 hard boundary：本 module 是 Live spawn 第 6 個 gate，
//! 與既有 5 個 gate（HMAC + freshness + env_allowed + secret slot +
//! OPENCLAW_ALLOW_MAINNET）並列；任一失敗即 fail-closed。
//!
//! 上游：startup::build_exchange_pipeline (mod.rs:496)
//! 下游：tracing audit log + healthcheck `[45]` pricing_binding

use crate::account_manager::{AccountManager, FeeSource};
use crate::bybit_rest_client::BybitEnvironment;
use crate::event_consumer::SYMBOLS;
use crate::mode_state::effective_engine_mode;
use crate::tick_pipeline::PipelineKind;
use openclaw_types::PricingConfig;
use std::time::Duration;
use tracing::{error, info, warn};

/// 最少要求的 fee_rate cache size（per PA tech plan §2.2 第 2 點）。
///
/// 25 對應 funding_curve / oi_delta panel aggregator 既有 25-symbol cohort
/// 設計（panel_aggregator/funding_curve.rs:36）。實際 Bybit V5
/// `/account/fee-rate?category=linear` 通常回幾百個 symbol，正常啟動遠超 25；
/// < 25 表示 refresh 路徑（BybitApi 或 seed_default）嚴重缺陷。
pub const MIN_REQUIRED_FEE_RATE_COUNT: usize = 25;

/// `wait_for_first_refresh_or_timeout` 預設等待上限（per PA §2.5 risk #2）。
/// 對齊「fee_rate refresh 已在 build_exchange_pipeline 同步 await 過」的前提：
/// 30s 是 defensive 重試窗口（即使 refresh path 失敗，acct 至少注入了
/// seed_default → last_fee_refresh_ms > 0）。
pub const DEFAULT_FIRST_REFRESH_TIMEOUT: Duration = Duration::from_secs(30);

/// `wait_for_first_refresh_or_timeout` 內部 poll 間隔（毫秒）。
const POLL_INTERVAL_MS: u64 = 200;

/// 失敗類別 — 寫入 audit log 的 reason code，與 healthcheck `[45]` 對齊
/// （per LG-2 T3 跨語言 source 字串集）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LivePricingBindingError {
    /// 30s 後仍 last_fee_refresh_ms == 0 — fee refresh path（BybitApi +
    /// seed_default）兩條都未成功。
    NoRefresh,
    /// fee_rate_count() < MIN_REQUIRED_FEE_RATE_COUNT — cache 異常小。
    InsufficientSymbolCoverage { count: usize },
    /// Mainnet 環境下某 symbol 非 BybitApi（含 ColdDefault / DemoConservativeDefault
    /// 兩種非真實 API 來源）— mainnet hard-block。
    MainnetNonApiSource {
        symbol: &'static str,
        source: FeeSource,
    },
    /// LiveDemo 環境且 cold_default_acceptable_modes 不含 "live_demo" 時，
    /// 某 symbol 非 BybitApi — LiveDemo 嚴格模式下的 fail-closed。
    LiveDemoNonApiSourceWhenStrict {
        symbol: &'static str,
        source: FeeSource,
    },
}

impl LivePricingBindingError {
    /// 失敗類別字串 — 對應 tracing audit log + healthcheck reason code。
    pub fn reason_code(&self) -> &'static str {
        match self {
            Self::NoRefresh => "no_refresh",
            Self::InsufficientSymbolCoverage { .. } => "insufficient_symbol_coverage",
            Self::MainnetNonApiSource { .. } => "mainnet_non_api_source",
            Self::LiveDemoNonApiSourceWhenStrict { .. } => "live_demo_non_api_source_when_strict",
        }
    }
}

impl std::fmt::Display for LivePricingBindingError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::NoRefresh => write!(
                f,
                "fee_rate refresh path failed: last_fee_refresh_ms == 0 after \
                 timeout / 費率刷新路徑失敗：超時後 last_fee_refresh_ms 仍為 0"
            ),
            Self::InsufficientSymbolCoverage { count } => write!(
                f,
                "fee_rate cache size {} < {} (MIN_REQUIRED_FEE_RATE_COUNT) \
                 / 費率快取大小 {} 低於最小要求 {}",
                count, MIN_REQUIRED_FEE_RATE_COUNT, count, MIN_REQUIRED_FEE_RATE_COUNT
            ),
            Self::MainnetNonApiSource { symbol, source } => write!(
                f,
                "mainnet symbol {} has non-BybitApi fee source: {} \
                 / 主網 symbol {} 之 fee 來源非 BybitApi：{}",
                symbol,
                source.as_str(),
                symbol,
                source.as_str()
            ),
            Self::LiveDemoNonApiSourceWhenStrict { symbol, source } => write!(
                f,
                "LiveDemo symbol {} has non-BybitApi fee source {} while \
                 cold_default_acceptable_modes excludes 'live_demo' \
                 / LiveDemo symbol {} 之 fee 來源為 {} 但 cold_default_acceptable_modes \
                 不包含 'live_demo'",
                symbol,
                source.as_str(),
                symbol,
                source.as_str()
            ),
        }
    }
}

impl std::error::Error for LivePricingBindingError {}

/// 等待 first fee_rate refresh 完成（含 demo seed_default 注入路徑）。
///
/// 設計：fee refresh 已在 build_exchange_pipeline `refresh_fee_rates`
/// 同步 await 過；該 await 內部 demo/LiveDemo 不支援端點時也會走
/// `seed_default_fee_rates` fallback。本函式作為 defensive net：
/// 即使 refresh await 抛異常（網路超時、Bybit 端 500 等），給 30s 重試
/// 窗，避免極端情境下 spawn 直接拒絕。
///
/// 若 30s 後仍 `last_fee_refresh_ms == 0` → 兩條路徑都失敗 → 回 Err。
///
/// Poll-based 是刻意選擇（不引入 oneshot channel + retry hook）：避免
/// account_manager.rs 內 cross-thread notify 接線，poll 200ms 對 startup
/// 路徑無延遲影響（最差等 30s = 150 次 poll）。
///
/// SAFETY / 不變量：
/// - 純讀 AtomicU64，無 lock 競爭。
/// - tokio::time::sleep 200ms × N 次，受 build_exchange_pipeline 上層
///   cancel token 控制（呼叫端可 abort）。
pub async fn wait_for_first_refresh_or_timeout(
    account_manager: &AccountManager,
    timeout: Duration,
) -> Result<(), LivePricingBindingError> {
    // 快路徑：refresh 已完成（最常見） — 立即回 Ok 不 sleep
    if account_manager.last_fee_refresh_ms() > 0 {
        return Ok(());
    }

    let start = std::time::Instant::now();
    let poll = Duration::from_millis(POLL_INTERVAL_MS);

    while start.elapsed() < timeout {
        tokio::time::sleep(poll).await;
        if account_manager.last_fee_refresh_ms() > 0 {
            return Ok(());
        }
    }

    Err(LivePricingBindingError::NoRefresh)
}

/// 對 Live spawn 執行 pricing binding 三項斷言（per PA tech plan §2.2 第 2 點）。
///
/// 順序：
///   1. fee_rate_count() ≥ MIN_REQUIRED_FEE_RATE_COUNT
///   2. per-symbol FeeSource 對照 env + cold_default_acceptable_modes：
///        - Mainnet：任一 symbol 非 BybitApi → reject
///        - LiveDemo：mode_label = "live_demo"；若在 acceptable_modes 內
///          → 全 accept；若不在 → 任一 symbol 非 BybitApi → reject
///
/// 預期呼叫端先呼 `wait_for_first_refresh_or_timeout` 確保 first refresh
/// 已成功，再呼本函式。
///
/// SAFETY / 不變量：
/// - SYMBOLS 是 5 個 const &'static str，per-symbol check 是 5 次 read lock，
///   startup 一次性、非 hot path。
/// - mode_label 走 `effective_engine_mode(PipelineKind::Live, Some(env))`，
///   與 engine_mode tag 寫入 PG (per memory `engine_mode_tag_live_demo`)
///   字串集一致。
pub fn assert_pricing_binding_for_live_spawn(
    env: BybitEnvironment,
    account_manager: &AccountManager,
    pricing_config: &PricingConfig,
) -> Result<(), LivePricingBindingError> {
    // ---------- Assertion B：fee_rate_count >= 25 ----------
    let count = account_manager.fee_rate_count();
    if count < MIN_REQUIRED_FEE_RATE_COUNT {
        return Err(LivePricingBindingError::InsufficientSymbolCoverage { count });
    }

    // ---------- Assertion C：per-symbol FeeSource ----------
    let mode_label = effective_engine_mode(PipelineKind::Live, Some(env));
    // mode_label ∈ {"live", "live_demo", "live_testnet"} for PipelineKind::Live
    // Mainnet 對應 "live"；LiveDemo 對應 "live_demo"

    let is_mainnet = matches!(env, BybitEnvironment::Mainnet);
    let mode_in_acceptable = pricing_config
        .cold_default_acceptable_modes
        .iter()
        .any(|m| m == mode_label);

    for &symbol in SYMBOLS {
        let source = account_manager.fee_source(symbol);

        // Mainnet：硬規則，任何非 BybitApi 都 reject（per CLAUDE.md §四 + LG-3 RFC §2.3）
        if is_mainnet {
            if !matches!(source, FeeSource::BybitApi) {
                return Err(LivePricingBindingError::MainnetNonApiSource { symbol, source });
            }
            continue;
        }

        // LiveDemo（含其他 non-Mainnet Live env）：
        //   - acceptable_modes 含 mode_label → 全 accept（不檢查 source）
        //   - 不含 → 與 mainnet 同嚴格，非 BybitApi reject
        if !mode_in_acceptable && !matches!(source, FeeSource::BybitApi) {
            return Err(LivePricingBindingError::LiveDemoNonApiSourceWhenStrict {
                symbol,
                source,
            });
        }
    }

    Ok(())
}

/// 寫 structured tracing audit log（用於 systemd journalctl / engine.log 留證）。
///
/// target = `openclaw_engine::live_spawn_audit`，方便 grep 與 healthcheck 解析。
/// 失敗時 level=error；成功時 level=info（pass 紀錄留證據鏈）。
pub fn write_audit_log(
    env: BybitEnvironment,
    result: &Result<(), LivePricingBindingError>,
    fee_rate_count: usize,
    last_fee_refresh_ms: u64,
) {
    let mode_label = effective_engine_mode(PipelineKind::Live, Some(env));
    match result {
        Ok(()) => {
            info!(
                target: "openclaw_engine::live_spawn_audit",
                event = "lg2_t2_pricing_assert_pass",
                env = ?env,
                engine_mode = mode_label,
                fee_rate_count = fee_rate_count,
                last_fee_refresh_ms = last_fee_refresh_ms,
                "LG-2 T2 pricing binding assertion PASS / pricing 斷言通過"
            );
        }
        Err(e) => {
            error!(
                target: "openclaw_engine::live_spawn_audit",
                event = "lg2_t2_pricing_assert_fail",
                env = ?env,
                engine_mode = mode_label,
                fee_rate_count = fee_rate_count,
                last_fee_refresh_ms = last_fee_refresh_ms,
                reason_code = e.reason_code(),
                error = %e,
                "LG-2 T2 pricing binding assertion FAIL — refusing live spawn \
                 / pricing 斷言失敗 — 拒絕啟動 live 管線"
            );
        }
    }
}

/// 寫 wait_for_first_refresh_or_timeout 之 audit log（單獨函式，因 fee_rate_count
/// 在 wait 失敗時為 0 但語意明確「未進到 per-symbol check」）。
pub fn write_wait_timeout_audit(env: BybitEnvironment, elapsed_secs: u64) {
    let mode_label = effective_engine_mode(PipelineKind::Live, Some(env));
    warn!(
        target: "openclaw_engine::live_spawn_audit",
        event = "lg2_t2_wait_first_refresh_timeout",
        env = ?env,
        engine_mode = mode_label,
        elapsed_secs = elapsed_secs,
        reason_code = "no_refresh",
        "LG-2 T2 wait_for_first_refresh_or_timeout exhausted before any fee \
         refresh path succeeded — refusing live spawn / 等待首次 fee 刷新超時 — \
         拒絕啟動 live 管線"
    );
}

// ============================================================================
// Unit tests — 11 個 covering wait + assert + reason_code + audit logic。
// ============================================================================
#[cfg(test)]
mod tests {
    use super::*;
    use crate::account_manager::AccountManager;

    /// 構造 PricingConfig with custom acceptable_modes（測試輔助）。
    fn make_pricing_config(acceptable_modes: Vec<&str>) -> PricingConfig {
        PricingConfig {
            max_age_warn_minutes: 30,
            max_age_fail_minutes: 720,
            cold_default_acceptable_modes: acceptable_modes.iter().map(|s| s.to_string()).collect(),
        }
    }

    // -----------------------------------------------------------------------
    // Test 1：last_fee_refresh_ms == 0 → wait_for_first_refresh 超時 → Err
    // -----------------------------------------------------------------------
    #[tokio::test]
    async fn test_wait_first_refresh_timeout_when_never_refreshed() {
        let acct = AccountManager::new();
        // last_fee_refresh_ms == 0 by default

        let result = wait_for_first_refresh_or_timeout(&acct, Duration::from_millis(500)).await;
        assert!(matches!(result, Err(LivePricingBindingError::NoRefresh)));
    }

    // -----------------------------------------------------------------------
    // Test 2：last_fee_refresh_ms 已 set → 快路徑立即 Ok
    // -----------------------------------------------------------------------
    #[tokio::test]
    async fn test_wait_first_refresh_fast_path_when_already_refreshed() {
        let acct = AccountManager::new();
        acct.set_last_fee_refresh_ms_for_test(1_700_000_000_000);

        let result = wait_for_first_refresh_or_timeout(&acct, Duration::from_secs(30)).await;
        assert!(result.is_ok());
    }

    // -----------------------------------------------------------------------
    // Test 3：mid-wait refresh 完成 → 中途 Ok（驗 poll 邏輯）
    // -----------------------------------------------------------------------
    #[tokio::test]
    async fn test_wait_first_refresh_midwait_completion() {
        let acct = std::sync::Arc::new(AccountManager::new());
        let acct_writer = acct.clone();

        // 600ms 後 set，wait 給 5s timeout
        tokio::spawn(async move {
            tokio::time::sleep(Duration::from_millis(600)).await;
            acct_writer.set_last_fee_refresh_ms_for_test(1_700_000_000_000);
        });

        let result = wait_for_first_refresh_or_timeout(&acct, Duration::from_secs(5)).await;
        assert!(result.is_ok(), "midwait completion 應 Ok，得 {:?}", result);
    }

    // -----------------------------------------------------------------------
    // Test 4：Demo / LiveDemo 不在本 module scope；assertion 只對 Live env 跑
    //   → LiveDemo + seed_default 含 25+ symbols（DemoConservativeDefault for
    //   SYMBOLS const）+ acceptable_modes 含 live_demo → spawn OK
    // -----------------------------------------------------------------------
    #[test]
    fn test_live_demo_accepts_demo_conservative_default_when_in_modes() {
        let acct = AccountManager::new();
        // seed 30 個非 SYMBOLS 之外符號（達 count >= 25）+ 再 seed SYMBOLS
        // 5 個（讓 SYMBOLS 每個 symbol 都有 DemoConservativeDefault 記錄）
        let extras: Vec<String> = (0..25).map(|i| format!("EXTRA{}USDT", i)).collect();
        let extras_refs: Vec<&str> = extras.iter().map(|s| s.as_str()).collect();
        let _ = acct.seed_default_fee_rates(extras_refs.iter().copied());
        let _ = acct.seed_default_fee_rates(SYMBOLS.iter().copied());

        let cfg = make_pricing_config(vec!["paper", "demo", "live_demo"]);

        let result = assert_pricing_binding_for_live_spawn(
            BybitEnvironment::LiveDemo,
            &acct,
            &cfg,
        );
        assert!(
            result.is_ok(),
            "LiveDemo + DemoConservativeDefault + modes 含 live_demo 應接受，得 {:?}",
            result
        );
    }

    // -----------------------------------------------------------------------
    // Test 5：LiveDemo + ColdDefault（SYMBOLS 未 seed）+ acceptable_modes 含 live_demo
    //         → spawn OK（acceptable_modes 含 live_demo 即放寬，per LG-2 T4 設計）
    // -----------------------------------------------------------------------
    #[test]
    fn test_live_demo_accepts_cold_default_when_in_modes() {
        let acct = AccountManager::new();
        // 注入 30 個非 SYMBOLS 之外符號 — SYMBOLS 5 個都 ColdDefault
        let non_overlap: Vec<String> = (0..30).map(|i| format!("FOO{}USDT", i)).collect();
        let refs: Vec<&str> = non_overlap.iter().map(|s| s.as_str()).collect();
        let _ = acct.seed_default_fee_rates(refs.iter().copied());

        let cfg = make_pricing_config(vec!["paper", "demo", "live_demo"]);

        let result = assert_pricing_binding_for_live_spawn(
            BybitEnvironment::LiveDemo,
            &acct,
            &cfg,
        );
        assert!(
            result.is_ok(),
            "LiveDemo + ColdDefault + modes 含 live_demo 應接受，得 {:?}",
            result
        );
    }

    // -----------------------------------------------------------------------
    // Test 6：LiveDemo + ColdDefault + acceptable_modes **不含** live_demo
    //         → reject (LiveDemoNonApiSourceWhenStrict)
    // -----------------------------------------------------------------------
    #[test]
    fn test_live_demo_rejects_cold_default_when_not_in_modes() {
        let acct = AccountManager::new();
        let non_overlap: Vec<String> = (0..30).map(|i| format!("FOO{}USDT", i)).collect();
        let refs: Vec<&str> = non_overlap.iter().map(|s| s.as_str()).collect();
        let _ = acct.seed_default_fee_rates(refs.iter().copied());
        // SYMBOLS 5 個都 ColdDefault

        // acceptable_modes 只含 paper / demo，不含 live_demo（嚴格模式）
        let cfg = make_pricing_config(vec!["paper", "demo"]);

        let result = assert_pricing_binding_for_live_spawn(
            BybitEnvironment::LiveDemo,
            &acct,
            &cfg,
        );
        assert!(
            matches!(
                result,
                Err(LivePricingBindingError::LiveDemoNonApiSourceWhenStrict { .. })
            ),
            "LiveDemo + ColdDefault + modes 不含 live_demo 應 reject，得 {:?}",
            result
        );
    }

    // -----------------------------------------------------------------------
    // Test 7：Mainnet + 任一 symbol = ColdDefault → reject 無論 modes
    // -----------------------------------------------------------------------
    #[test]
    fn test_mainnet_rejects_cold_default_always() {
        let acct = AccountManager::new();
        let non_overlap: Vec<String> = (0..30).map(|i| format!("FOO{}USDT", i)).collect();
        let refs: Vec<&str> = non_overlap.iter().map(|s| s.as_str()).collect();
        let _ = acct.seed_default_fee_rates(refs.iter().copied());

        // 即使 modes 含所有 mode label，mainnet hard-block
        let cfg = make_pricing_config(vec!["paper", "demo", "live_demo", "live"]);

        let result =
            assert_pricing_binding_for_live_spawn(BybitEnvironment::Mainnet, &acct, &cfg);
        assert!(
            matches!(
                result,
                Err(LivePricingBindingError::MainnetNonApiSource { .. })
            ),
            "Mainnet + ColdDefault 應 reject，得 {:?}",
            result
        );
    }

    // -----------------------------------------------------------------------
    // Test 8：Mainnet + 全 symbol = DemoConservativeDefault → reject
    // -----------------------------------------------------------------------
    #[test]
    fn test_mainnet_rejects_demo_conservative_default() {
        let acct = AccountManager::new();
        // seed SYMBOLS 5 個 + 25 個額外 — 全部都 DemoConservativeDefault
        let mut all: Vec<&str> = SYMBOLS.to_vec();
        let extra: Vec<String> = (0..25).map(|i| format!("EXT{}USDT", i)).collect();
        let extra_refs: Vec<&str> = extra.iter().map(|s| s.as_str()).collect();
        all.extend(extra_refs.iter());
        let _ = acct.seed_default_fee_rates(all.iter().copied());

        let cfg = make_pricing_config(vec!["paper", "demo", "live_demo"]);

        let result =
            assert_pricing_binding_for_live_spawn(BybitEnvironment::Mainnet, &acct, &cfg);
        assert!(
            matches!(
                result,
                Err(LivePricingBindingError::MainnetNonApiSource {
                    source: FeeSource::DemoConservativeDefault,
                    ..
                })
            ),
            "Mainnet + DemoConservativeDefault 應 reject 且 source=DemoConservativeDefault，得 {:?}",
            result
        );
    }

    // -----------------------------------------------------------------------
    // Test 9：fee_rate_count < 25 → reject (InsufficientSymbolCoverage)
    // -----------------------------------------------------------------------
    #[test]
    fn test_rejects_when_fee_rate_count_below_min() {
        let acct = AccountManager::new();
        // 只 seed SYMBOLS 5 個（不足 25）
        let _ = acct.seed_default_fee_rates(SYMBOLS.iter().copied());

        let cfg = make_pricing_config(vec!["paper", "demo", "live_demo"]);

        let result = assert_pricing_binding_for_live_spawn(
            BybitEnvironment::LiveDemo,
            &acct,
            &cfg,
        );
        assert!(
            matches!(
                result,
                Err(LivePricingBindingError::InsufficientSymbolCoverage { count: 5 })
            ),
            "fee_rate_count=5 < 25 應 reject，得 {:?}",
            result
        );
    }

    // -----------------------------------------------------------------------
    // Test 10：reason_code 字串正確（healthcheck 對接契約）
    // -----------------------------------------------------------------------
    #[test]
    fn test_reason_code_strings_aligned() {
        assert_eq!(LivePricingBindingError::NoRefresh.reason_code(), "no_refresh");
        assert_eq!(
            LivePricingBindingError::InsufficientSymbolCoverage { count: 5 }.reason_code(),
            "insufficient_symbol_coverage"
        );
        assert_eq!(
            LivePricingBindingError::MainnetNonApiSource {
                symbol: "BTCUSDT",
                source: FeeSource::ColdDefault,
            }
            .reason_code(),
            "mainnet_non_api_source"
        );
        assert_eq!(
            LivePricingBindingError::LiveDemoNonApiSourceWhenStrict {
                symbol: "BTCUSDT",
                source: FeeSource::ColdDefault,
            }
            .reason_code(),
            "live_demo_non_api_source_when_strict"
        );
    }

    // -----------------------------------------------------------------------
    // Test 11：Display impl 包含中英對照（不爆破 to_string()）
    // -----------------------------------------------------------------------
    #[test]
    fn test_display_format_safe() {
        let e1 = LivePricingBindingError::NoRefresh;
        assert!(e1.to_string().contains("last_fee_refresh_ms"));
        assert!(e1.to_string().contains("費率刷新"));

        let e2 = LivePricingBindingError::InsufficientSymbolCoverage { count: 3 };
        let s2 = e2.to_string();
        assert!(s2.contains("3 < 25"));

        let e3 = LivePricingBindingError::MainnetNonApiSource {
            symbol: "BTCUSDT",
            source: FeeSource::ColdDefault,
        };
        assert!(e3.to_string().contains("BTCUSDT"));
        assert!(e3.to_string().contains("cold_default"));

        let e4 = LivePricingBindingError::LiveDemoNonApiSourceWhenStrict {
            symbol: "ETHUSDT",
            source: FeeSource::DemoConservativeDefault,
        };
        let s4 = e4.to_string();
        assert!(s4.contains("ETHUSDT"));
        assert!(s4.contains("demo_conservative_default"));
        assert!(s4.contains("cold_default_acceptable_modes"));
    }
}
