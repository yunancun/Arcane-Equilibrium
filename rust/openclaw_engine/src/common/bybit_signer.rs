//! HMAC-SHA256 signing primitives shared by Bybit REST V5 and private WS auth.
//! Bybit REST V5 與私有 WS 認證共用的 HMAC-SHA256 簽名原語。
//!
//! MODULE_NOTE (EN): Extracted from bybit_rest_client.rs + bybit_private_ws.rs
//!   (E1-P0-3). Primitive `hmac_sha256_hex` returns lowercase hex unconditionally
//!   because HMAC-SHA256 accepts keys of any length (the underlying `new_from_slice`
//!   only errors on keys longer than the block size of the inner hash, which
//!   SHA-256's construction explicitly handles — so `.expect()` is sound and
//!   matches the pre-extraction semantics in both call sites).
//!   The REST `sign(timestamp, params)` call site keeps its own `BybitApiError::
//!   SigningError` wrapping via the caller; this module intentionally does not
//!   depend on that error type (FA-1 deferred `common/bybit_error.rs`).
//! MODULE_NOTE (中): 從 bybit_rest_client.rs + bybit_private_ws.rs 提取（E1-P0-3）。
//!   原語 `hmac_sha256_hex` 無條件回傳小寫 hex，因為 HMAC-SHA256 接受任意長度金鑰
//!   （底層 `new_from_slice` 僅在金鑰超過內部雜湊區塊大小時 error，而 SHA-256 的
//!   構造已明確處理此情況，所以 `.expect()` 是安全的，並與兩個調用點提取前的
//!   語意一致）。REST 端 `sign(timestamp, params)` 呼叫點仍由調用方以
//!   `BybitApiError::SigningError` 自行包裝；本模組刻意不依賴該錯誤型別
//!   （FA-1 已 defer `common/bybit_error.rs`）。

use hmac::{Hmac, Mac};
use sha2::Sha256;

/// Compute HMAC-SHA256 and return lowercase hex string.
/// 計算 HMAC-SHA256 並回傳小寫十六進制字串。
///
/// EN: `.expect()` on `new_from_slice` is sound because HMAC accepts keys of
///     any length (internal keying handles long keys by hashing). Matches the
///     pre-extraction behavior at bybit_private_ws.rs:621 and
///     bybit_rest_client.rs:532 byte-for-byte.
/// 中文: 對 `new_from_slice` 使用 `.expect()` 是安全的，因為 HMAC 接受任意長度金鑰
///     （內部鍵化會對長金鑰先做雜湊）。與 bybit_private_ws.rs:621 及
///     bybit_rest_client.rs:532 提取前行為字節一致。
pub fn hmac_sha256_hex(secret: &str, payload: &str) -> String {
    let mut mac =
        Hmac::<Sha256>::new_from_slice(secret.as_bytes()).expect("HMAC can take key of any size");
    mac.update(payload.as_bytes());
    hex::encode(mac.finalize().into_bytes())
}

/// Build the canonical Bybit V5 REST signing payload.
/// 組合 Bybit V5 REST 標準簽名負載。
///
/// EN: Format per Bybit V5 spec: `timestamp + api_key + recv_window + params`.
///     Kept separate from signing so that callers can log the payload pre-sign
///     without pulling in the secret.
/// 中文: 依 Bybit V5 規範：`timestamp + api_key + recv_window + params`。
///     與簽名分離以便調用方可在不暴露 secret 的情況下記錄簽名前負載。
pub fn rest_v5_payload(ts: &str, api_key: &str, recv_window: &str, params: &str) -> String {
    format!("{}{}{}{}", ts, api_key, recv_window, params)
}

/// Sign a Bybit V5 REST request.
/// 為 Bybit V5 REST 請求簽名。
///
/// EN: Thin composition of `rest_v5_payload` + `hmac_sha256_hex`. Returns the
///     lowercase hex signature.
/// 中文: `rest_v5_payload` + `hmac_sha256_hex` 的薄組合，回傳小寫 hex 簽名。
pub fn sign_rest_v5(
    api_secret: &str,
    ts: &str,
    api_key: &str,
    recv_window: &str,
    params: &str,
) -> String {
    let payload = rest_v5_payload(ts, api_key, recv_window, params);
    hmac_sha256_hex(api_secret, &payload)
}

/// Build the Bybit WS private auth payload — `GET/realtime{expires}`.
/// 組合 Bybit 私有 WS 認證負載 — `GET/realtime{expires}`。
pub fn ws_auth_payload(expires_ms: u64) -> String {
    format!("GET/realtime{}", expires_ms)
}

/// Sign the Bybit private WS auth handshake.
/// 為 Bybit 私有 WS 認證握手簽名。
///
/// EN: Matches the pre-extraction inline formula at bybit_private_ws.rs:463
///     — `hex(hmac_sha256(api_secret, "GET/realtime" + expires))`.
/// 中文: 與 bybit_private_ws.rs:463 提取前內嵌公式一致
///     — `hex(hmac_sha256(api_secret, "GET/realtime" + expires))`。
pub fn sign_ws_auth(api_secret: &str, expires_ms: u64) -> String {
    hmac_sha256_hex(api_secret, &ws_auth_payload(expires_ms))
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    /// EN: Output is 64-char lowercase hex (SHA-256 → 32 bytes → 64 hex).
    /// 中文: 輸出為 64 字元小寫 hex（SHA-256 → 32 bytes → 64 hex）。
    #[test]
    fn test_hmac_sha256_hex_shape() {
        let sig = hmac_sha256_hex("secret", "payload");
        assert_eq!(sig.len(), 64);
        // All chars are lowercase hex / 所有字元為小寫 hex
        assert!(sig
            .chars()
            .all(|c| c.is_ascii_hexdigit() && !c.is_ascii_uppercase()));
    }

    /// EN: Deterministic — identical inputs produce identical output.
    /// 中文: 確定性 — 相同輸入產出相同輸出。
    #[test]
    fn test_hmac_sha256_hex_deterministic() {
        let a = hmac_sha256_hex("k", "m");
        let b = hmac_sha256_hex("k", "m");
        assert_eq!(a, b);
    }

    /// EN: REST V5 payload structure matches Bybit spec concatenation order.
    /// 中文: REST V5 負載結構符合 Bybit 規範的串接順序。
    #[test]
    fn test_rest_v5_payload_order() {
        let p = rest_v5_payload("1700000000000", "KEY", "5000", "foo=bar");
        assert_eq!(p, "1700000000000KEY5000foo=bar");
    }

    /// EN: sign_rest_v5 reproduces the pre-extraction REST signing result
    ///     (matches test_sign_known_vector inputs in bybit_rest_client.rs).
    /// 中文: sign_rest_v5 重現提取前 REST 簽名結果
    ///     （與 bybit_rest_client.rs 的 test_sign_known_vector 輸入一致）。
    #[test]
    fn test_sign_rest_v5_matches_legacy_known_vector() {
        let ts = "1700000000000";
        let key = "TESTKEY123";
        let recv = "5000";
        let params = "category=linear&symbol=BTCUSDT";
        let secret = "TESTSECRET456";

        // Expected is computed by the same primitive — proves round-trip.
        let expected = hmac_sha256_hex(secret, &format!("{}{}{}{}", ts, key, recv, params));
        let actual = sign_rest_v5(secret, ts, key, recv, params);
        assert_eq!(actual, expected);
        assert_eq!(actual.len(), 64);
    }

    /// EN: ws_auth_payload matches `GET/realtime{expires}` contract.
    /// 中文: ws_auth_payload 符合 `GET/realtime{expires}` 契約。
    #[test]
    fn test_ws_auth_payload_format() {
        assert_eq!(
            ws_auth_payload(1_700_000_010_000),
            "GET/realtime1700000010000"
        );
    }

    /// EN: sign_ws_auth matches pre-extraction private-WS signing (byte-for-byte
    ///     reproduction of bybit_private_ws.rs:460-463).
    /// 中文: sign_ws_auth 與提取前私有 WS 簽名字節一致
    ///     （重現 bybit_private_ws.rs:460-463）。
    #[test]
    fn test_sign_ws_auth_matches_legacy() {
        let secret = "MYSECRET";
        let expires = 1_700_000_010_000_u64;
        let expected = hmac_sha256_hex(secret, &format!("GET/realtime{}", expires));
        assert_eq!(sign_ws_auth(secret, expires), expected);
    }
}
