//! Common utilities shared across exchange-facing modules.
//! 交易所層共享的通用工具模組。
//!
//! MODULE_NOTE (EN): Hosts dedup'd primitives extracted from ws_client /
//!   bybit_private_ws / bybit_rest_client. Current contents:
//!     * `ws_backoff` — exponential reconnect delay with saturation + cap
//!     * `bybit_signer` — HMAC-SHA256 helpers for Bybit V5 REST and WS auth
//!   Behavior MUST remain byte-identical to the pre-extraction call sites;
//!   see E1-P0-3 spec (jitter defaults to 0 = RNG disabled, signer returns
//!   lowercase hex, saturating_pow semantics preserved).
//! MODULE_NOTE (中): 承載從 ws_client / bybit_private_ws / bybit_rest_client
//!   提取的去重原語。目前內容：
//!     * `ws_backoff` — 指數退避重連延遲（帶飽和保護 + 上限）
//!     * `bybit_signer` — Bybit V5 REST 與 WS 認證的 HMAC-SHA256 輔助函數
//!   行為必須與提取前的調用點字節級一致；詳見 E1-P0-3 規格
//!   （jitter 預設為 0 = 停用隨機源、簽名器回傳小寫 hex、保留 saturating_pow 語意）。

pub mod bybit_signer;
pub mod ws_backoff;
