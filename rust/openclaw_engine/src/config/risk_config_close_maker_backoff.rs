//! Close-maker rate-limit backoff / cascade config.
//! close-maker 限流退避 / 級聯配置。
//!
//! MODULE_NOTE (中): OOS-9 config 化。把 `strategies::maker_rejection` 中六個
//!   close-maker `EC_ReachMaxPendingOrders` 退避 / 級聯常數
//!   （BACKOFF_INITIAL / BACKOFF_MAX / BACKOFF_RESET_AFTER / CASCADE_WINDOW /
//!   CASCADE_SYMBOLS / GLOBAL_PAUSE）抽成可熱重載 sub-struct，對齊既有
//!   `[slippage]` / `[cusum]` 範式。預設值與原常數 **bit-identical**，TOML 缺
//!   `[close_maker_backoff]` section 時 `#[serde(default)]` 補回原值，引擎行為不變。
//!   `validate()` fail-closed：initial<=max、cascade_symbols>=1、各 ms>0 且有
//!   合理上界，拒 0（0 會讓退避退化成無退避 / 級聯窗口塌縮）。
//!   本檔為 schema + validate；strategy 側讀取見 `maker_rejection.rs`
//!   （const 保留作 default 來源，行為 bit-identical）。

use serde::{Deserialize, Serialize};

use crate::strategies::maker_rejection::{
    CLOSE_MAKER_BACKOFF_INITIAL_MS, CLOSE_MAKER_BACKOFF_MAX_MS, CLOSE_MAKER_BACKOFF_RESET_AFTER_MS,
    CLOSE_MAKER_GLOBAL_CASCADE_SYMBOLS, CLOSE_MAKER_GLOBAL_CASCADE_WINDOW_MS,
    CLOSE_MAKER_GLOBAL_PAUSE_MS,
};

// 預設值直接引用 `maker_rejection.rs` 原六個常數作單一來源（SSOT），保證
// bit-identical 且不會與代碼常數 drift。常數仍保留在 maker_rejection.rs 供
// 這裡與對照測試引用。
fn default_backoff_initial_ms() -> u64 {
    CLOSE_MAKER_BACKOFF_INITIAL_MS
}
fn default_backoff_max_ms() -> u64 {
    CLOSE_MAKER_BACKOFF_MAX_MS
}
fn default_backoff_reset_after_ms() -> u64 {
    CLOSE_MAKER_BACKOFF_RESET_AFTER_MS
}
fn default_global_cascade_window_ms() -> u64 {
    CLOSE_MAKER_GLOBAL_CASCADE_WINDOW_MS
}
fn default_global_cascade_symbols() -> usize {
    CLOSE_MAKER_GLOBAL_CASCADE_SYMBOLS
}
fn default_global_pause_ms() -> u64 {
    CLOSE_MAKER_GLOBAL_PAUSE_MS
}

// 合理上界（validate 用）：退避 / 暫停時長硬性 cap 24h，reset window cap 24h，
// cascade window cap 1h，cascade symbols cap 1000。這些上界只擋明顯 misconfig
// （單位打錯、天量值造成整策略永久暫停），不改任何預設語意。
const MAX_BACKOFF_MS: u64 = 24 * 3600 * 1_000;
const MAX_RESET_AFTER_MS: u64 = 24 * 3600 * 1_000;
const MAX_CASCADE_WINDOW_MS: u64 = 3600 * 1_000;
const MAX_GLOBAL_PAUSE_MS: u64 = 24 * 3600 * 1_000;
const MAX_CASCADE_SYMBOLS: usize = 1_000;

/// close-maker `TooManyPending` 退避 / 級聯參數。
///
/// 預設保持 OOS-9 前 `maker_rejection.rs` 硬編常數 bit-identical。
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CloseMakerBackoffConfig {
    /// 單一 symbol 初始退避（ms）。同 `CLOSE_MAKER_BACKOFF_INITIAL_MS`。
    #[serde(default = "default_backoff_initial_ms")]
    pub backoff_initial_ms: u64,
    /// 單一 symbol 指數退避上限（ms）。同 `CLOSE_MAKER_BACKOFF_MAX_MS`。
    #[serde(default = "default_backoff_max_ms")]
    pub backoff_max_ms: u64,
    /// symbol 靜默超過此時間後重置回初始退避（ms）。同
    /// `CLOSE_MAKER_BACKOFF_RESET_AFTER_MS`。
    #[serde(default = "default_backoff_reset_after_ms")]
    pub backoff_reset_after_ms: u64,
    /// distinct-symbol 級聯偵測窗口（ms）。同 `CLOSE_MAKER_GLOBAL_CASCADE_WINDOW_MS`。
    #[serde(default = "default_global_cascade_window_ms")]
    pub global_cascade_window_ms: u64,
    /// 窗口內觸發全域暫停所需 distinct symbol 數。同
    /// `CLOSE_MAKER_GLOBAL_CASCADE_SYMBOLS`。
    #[serde(default = "default_global_cascade_symbols")]
    pub global_cascade_symbols: usize,
    /// 級聯後全域 close-maker 暫停時長（ms）。同 `CLOSE_MAKER_GLOBAL_PAUSE_MS`。
    #[serde(default = "default_global_pause_ms")]
    pub global_pause_ms: u64,
}

impl Default for CloseMakerBackoffConfig {
    fn default() -> Self {
        Self {
            backoff_initial_ms: default_backoff_initial_ms(),
            backoff_max_ms: default_backoff_max_ms(),
            backoff_reset_after_ms: default_backoff_reset_after_ms(),
            global_cascade_window_ms: default_global_cascade_window_ms(),
            global_cascade_symbols: default_global_cascade_symbols(),
            global_pause_ms: default_global_pause_ms(),
        }
    }
}

impl CloseMakerBackoffConfig {
    /// 驗證跨欄位不變量與範圍（fail-closed）。
    ///
    /// 為什麼 fail-closed：這些值直接決定 close-maker 退避節奏與級聯暫停。0 會讓
    /// 退避 clamp 到 0（無退避）或級聯窗口塌縮成 always-cascade；initial>max 會讓
    /// `clamp` panic-adjacent 語意反轉；cascade_symbols=0 會讓任何一次拒絕立即
    /// 觸發全域暫停。任一非法值都應在 config 載入即拒絕，而非讓限流機制退化。
    pub(crate) fn validate(&self) -> Result<(), String> {
        if self.backoff_initial_ms == 0 {
            return Err("risk.close_maker_backoff.backoff_initial_ms must be > 0".into());
        }
        if self.backoff_max_ms == 0 {
            return Err("risk.close_maker_backoff.backoff_max_ms must be > 0".into());
        }
        if self.backoff_initial_ms > self.backoff_max_ms {
            return Err(
                "risk.close_maker_backoff.backoff_initial_ms must not exceed backoff_max_ms".into(),
            );
        }
        if self.backoff_max_ms > MAX_BACKOFF_MS {
            return Err(format!(
                "risk.close_maker_backoff.backoff_max_ms must be <= {} (24h)",
                MAX_BACKOFF_MS
            ));
        }
        if self.backoff_reset_after_ms == 0 {
            return Err("risk.close_maker_backoff.backoff_reset_after_ms must be > 0".into());
        }
        if self.backoff_reset_after_ms > MAX_RESET_AFTER_MS {
            return Err(format!(
                "risk.close_maker_backoff.backoff_reset_after_ms must be <= {} (24h)",
                MAX_RESET_AFTER_MS
            ));
        }
        if self.global_cascade_window_ms == 0 {
            return Err("risk.close_maker_backoff.global_cascade_window_ms must be > 0".into());
        }
        if self.global_cascade_window_ms > MAX_CASCADE_WINDOW_MS {
            return Err(format!(
                "risk.close_maker_backoff.global_cascade_window_ms must be <= {} (1h)",
                MAX_CASCADE_WINDOW_MS
            ));
        }
        if self.global_cascade_symbols < 1 {
            return Err("risk.close_maker_backoff.global_cascade_symbols must be >= 1".into());
        }
        if self.global_cascade_symbols > MAX_CASCADE_SYMBOLS {
            return Err(format!(
                "risk.close_maker_backoff.global_cascade_symbols must be <= {}",
                MAX_CASCADE_SYMBOLS
            ));
        }
        if self.global_pause_ms == 0 {
            return Err("risk.close_maker_backoff.global_pause_ms must be > 0".into());
        }
        if self.global_pause_ms > MAX_GLOBAL_PAUSE_MS {
            return Err(format!(
                "risk.close_maker_backoff.global_pause_ms must be <= {} (24h)",
                MAX_GLOBAL_PAUSE_MS
            ));
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::strategies::maker_rejection::{
        CLOSE_MAKER_BACKOFF_INITIAL_MS, CLOSE_MAKER_BACKOFF_MAX_MS,
        CLOSE_MAKER_BACKOFF_RESET_AFTER_MS, CLOSE_MAKER_GLOBAL_CASCADE_SYMBOLS,
        CLOSE_MAKER_GLOBAL_CASCADE_WINDOW_MS, CLOSE_MAKER_GLOBAL_PAUSE_MS,
    };

    #[test]
    fn default_validates() {
        assert!(CloseMakerBackoffConfig::default().validate().is_ok());
    }

    #[test]
    fn defaults_equal_original_consts_bit_identical() {
        // OOS-9：config 化不改任何值。逐一斷言 default == 原常數。
        let cfg = CloseMakerBackoffConfig::default();
        assert_eq!(cfg.backoff_initial_ms, CLOSE_MAKER_BACKOFF_INITIAL_MS);
        assert_eq!(cfg.backoff_max_ms, CLOSE_MAKER_BACKOFF_MAX_MS);
        assert_eq!(
            cfg.backoff_reset_after_ms,
            CLOSE_MAKER_BACKOFF_RESET_AFTER_MS
        );
        assert_eq!(
            cfg.global_cascade_window_ms,
            CLOSE_MAKER_GLOBAL_CASCADE_WINDOW_MS
        );
        assert_eq!(
            cfg.global_cascade_symbols,
            CLOSE_MAKER_GLOBAL_CASCADE_SYMBOLS
        );
        assert_eq!(cfg.global_pause_ms, CLOSE_MAKER_GLOBAL_PAUSE_MS);
    }

    #[test]
    fn toml_missing_section_uses_default() {
        // TOML 缺 [close_maker_backoff] 時 serde default 補回原值。
        let cfg: CloseMakerBackoffConfig = toml::from_str("").expect("parse empty");
        assert_eq!(cfg, CloseMakerBackoffConfig::default());
        assert!(cfg.validate().is_ok());
    }

    #[test]
    fn rejects_initial_greater_than_max() {
        let cfg = CloseMakerBackoffConfig {
            backoff_initial_ms: 60_001,
            backoff_max_ms: 60_000,
            ..CloseMakerBackoffConfig::default()
        };
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn rejects_zero_values() {
        for mutate in [
            |c: &mut CloseMakerBackoffConfig| c.backoff_initial_ms = 0,
            |c: &mut CloseMakerBackoffConfig| c.backoff_max_ms = 0,
            |c: &mut CloseMakerBackoffConfig| c.backoff_reset_after_ms = 0,
            |c: &mut CloseMakerBackoffConfig| c.global_cascade_window_ms = 0,
            |c: &mut CloseMakerBackoffConfig| c.global_cascade_symbols = 0,
            |c: &mut CloseMakerBackoffConfig| c.global_pause_ms = 0,
        ] {
            let mut cfg = CloseMakerBackoffConfig::default();
            mutate(&mut cfg);
            assert!(
                cfg.validate().is_err(),
                "expected err after zeroing a field"
            );
        }
    }
}
