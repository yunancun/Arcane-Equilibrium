//! PHASE 0 AUTH-1：live-write capability token 強制執行（enforcer，非 authorizer）。
//!
//! MODULE_NOTE (中)：本模組是 dispatch chokepoint 的 live-write 授權強制層。
//!   5-gate 決策權威留在 Python（live_preflight.all_five_live_gates_ok）；Python
//!   過門後鑄造短 TTL、單次 nonce、綁操作內容的 `live_authz_token`，Rust 在
//!   `dispatch_request` 的 `match method` 之前對「engine==live 的 state-mutator
//!   method」強制驗 token，fail-closed。
//!
//!   主要組件：
//!   - `LIVE_WRITE_METHODS`：所有「engine==live 時會改 live 引擎風控/策略/runtime
//!     參數或開關狀態」的 IPC method allowlist（唯讀 method 一律豁免）。
//!   - `canonical_hash_for(method, params)`：決定性 JSON 序列化 → SHA256 hex。patch
//!     類 method 只 hash `params["patch"]`；非 patch 類 hash「params \ {token三欄, engine}」。
//!     數值字串化鏡像 Python `live_patch_token._rust_serde_float_str`（T12 跨語言一致性
//!     由 fixture 測試釘死；Python 端用同規則，禁 naive json.dumps）。
//!   - `verify_live_authz_token`：常數時間 HMAC-SHA256 verify（`Mac::verify_slice`，
//!     非 `==`），鏡像 connection.rs verify_ipc_token primitive。
//!   - `NonceLedger`：單次 nonce 帳本（Mutex<HashMap<nonce, ts>>，lazy TTL 驅逐，
//!     MAX_NONCE_LEDGER 硬上界 DoS 安全閥）。process-global singleton（已登記
//!     singleton-registry.md）。
//!   - `check_live_authz`：chokepoint 主入口，回 Ok(()) 或 Err(reject_reason)。
//!
//! 硬邊界：本模組不碰 live_execution_allowed / max_retries / system_mode /
//!   authorization.json；只新增 enforcer。secret 缺失 → verify 必失敗（fail-closed
//!   kill-switch，唯一緊急姿態 = 撤 OPENCLAW_LIVE_PATCH_SECRET）。

use hmac::{Hmac, Mac};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};

type HmacSha256 = Hmac<Sha256>;

/// US (Unit Separator, 0x1f) — bind-string 欄位分隔符，避免欄位邊界歧義。
const US: u8 = 0x1f;

/// Token TTL（秒）。≤30s 約束內留 5s 給 ts skew + 傳輸；mint→use 同機 <1s。
pub(crate) const LIVE_AUTHZ_TTL_SECS: i64 = 25;

/// Nonce 帳本硬上界（DoS 安全閥）。正常 TTL 窗內 live patch 次數極小（個位數），
/// 永不觸及；超限時拒新 token（`nonce_ledger_full`）並 error! 告警。
pub(crate) const MAX_NONCE_LEDGER: usize = 10_000;

/// 所有「engine==live 時會改變 live 引擎的風控/策略/runtime 參數或開關狀態」的
/// IPC method allowlist。唯讀 method（get_* / query_* / governance.get_* /
/// governance.is_authorized / governance.list_leases）一律豁免（不在此表）。
///
/// 維護紀律：未來新增任何 live-affecting IPC mutator → 必同步加入此表（CC review
/// checklist 一條）。本表由 dispatch.rs 親 grep 全 mutator 列舉而得（2026-06-17）。
pub(crate) const LIVE_WRITE_METHODS: &[&str] = &[
    // RiskConfig / ConfigStore 寫
    "patch_risk_config",
    "update_risk_config",
    // governor / dynamic-risk runtime 寫
    "force_governor_tier_looser",
    "force_governor_tier_tighter",
    "set_dynamic_risk_enabled",
    // exit / drawdown / loss-counter runtime 寫
    "restore_exit_config_defaults",
    "reset_drawdown_baseline",
    "clear_consecutive_losses",
    // strategy 寫（engine:live 時）
    "set_strategy_active",
    "update_strategy_params",
    // pipeline 控制（engine:live 時改 live runtime 狀態）
    "pause_paper",
    "resume_paper",
    "reset_paper_state",
    // 註：close_all_positions / cancel_all_orders / close_position / submit_paper_order
    //     是「平倉/下單」面，屬 lease/order authority 既有治理，非 RiskConfig 面；
    //     Phase 0 SCOPE = 「改 live param/runtime config」。平倉路徑 OUT-OF-SCOPE。
];

/// chokepoint 是否需要對此 (engine, method) 強制 live-write authz。
///
/// 為何用 `==("live")` 而非 contains：Phase 0 token 只為 live 鑄造；demo/paper
/// 完全不變（Demo 放寬 / Live 收緊政策）。engine 讀法必須與下游 match arm 逐字
/// 一致（`params.get("engine").as_str().unwrap_or("paper")`），否則 gate 判 paper
/// 而 arm 走 live = 繞過（U-P0-3）。
pub(crate) fn requires_live_authz(engine: &str, method: &str) -> bool {
    engine == "live" && LIVE_WRITE_METHODS.contains(&method)
}

// ---------------------------------------------------------------------------
// Canonical 決定性序列化（Python live_patch_token.py 必須位元一致）
// ---------------------------------------------------------------------------

/// 把 serde_json::f64 字串化成「ryu shortest」形式。serde_json 預設即用此規則；
/// 但我們需要一個明確的入口讓 Python 端有對齊基準（T12 fixture 親驗 byte-equal）。
///
/// 直接委派 serde_json::to_string 對 Number 的輸出（即 ryu）。Python 端的
/// `_rust_serde_float_str` 鏡像此規則（已對 22.5 萬個 f64 sweep 驗證 0 mismatch）。
fn push_number(n: &serde_json::Number, out: &mut String) {
    // serde_json::Number 的 Display / to_string 即 ryu shortest（整數走 i64/u64 原樣，
    // 浮點走 ryu）。直接複用，禁手寫格式化以免與 Python mirror drift。
    out.push_str(&n.to_string());
}

/// 遞迴決定性序列化 serde_json::Value：物件 key 字典序排序、緊湊輸出（無多餘空白）、
/// 字串用 serde_json escape（與 Python json.dumps ensure_ascii=False + 標準 escape 對齊）。
/// 鏡像 Python `canonical_json`（sort_keys + separators=(",",":") + 自訂 float 字串化）。
fn canonicalize(v: &serde_json::Value, out: &mut String) {
    use serde_json::Value;
    match v {
        Value::Null => out.push_str("null"),
        Value::Bool(b) => out.push_str(if *b { "true" } else { "false" }),
        Value::Number(n) => push_number(n, out),
        Value::String(s) => {
            // serde_json::to_string 對 String 產生標準 JSON escape（非 ASCII 原樣 UTF-8，
            // 與 Python ensure_ascii=False 對齊）。
            out.push_str(&serde_json::to_string(s).expect("string serialize never fails"));
        }
        Value::Array(arr) => {
            out.push('[');
            for (i, e) in arr.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                canonicalize(e, out);
            }
            out.push(']');
        }
        Value::Object(map) => {
            let mut keys: Vec<&String> = map.keys().collect();
            keys.sort_unstable();
            out.push('{');
            for (i, k) in keys.iter().enumerate() {
                if i > 0 {
                    out.push(',');
                }
                out.push_str(&serde_json::to_string(k).expect("key serialize never fails"));
                out.push(':');
                canonicalize(&map[*k], out);
            }
            out.push('}');
        }
    }
}

/// 計算 canonical bytes（公開供 fixture 測試與 hash 共用）。
pub(crate) fn canonical_bytes(v: &serde_json::Value) -> Vec<u8> {
    let mut out = String::new();
    canonicalize(v, &mut out);
    out.into_bytes()
}

/// 計算「這次要改什麼值」的 canonical hash（hex SHA256）。
///
/// 分支裁決（U-P0-4）：
/// - `patch` 類 method（params 帶 `patch` 物件）→ 只 hash `params["patch"]`（更窄、更精確）。
/// - 非 `patch` 類 mutator（update_risk_config / set_dynamic_risk_enabled / strategy 等的
///   可變內容在 params 旋鈕欄）→ hash「params \ {live_authz_token, live_authz_nonce,
///   live_authz_ts, engine}」（去 token 三欄 + engine 後排序序列化）。
///
/// Python minter 對應地對「即將送的 params（去 token 三欄、去 engine）」算同樣 hash。
pub(crate) fn canonical_hash_for(method: &str, params: &serde_json::Value) -> String {
    let _ = method; // method 已綁進 bind-string，hash 對象只看 patch / params 結構
    let target = if let Some(patch) = params.get("patch") {
        // patch 類：只 hash patch 物件本身
        patch.clone()
    } else if let serde_json::Value::Object(map) = params {
        // 非 patch 類：去 token 三欄 + engine
        let mut filtered = serde_json::Map::new();
        for (k, v) in map {
            if k == "live_authz_token"
                || k == "live_authz_nonce"
                || k == "live_authz_ts"
                || k == "engine"
            {
                continue;
            }
            filtered.insert(k.clone(), v.clone());
        }
        serde_json::Value::Object(filtered)
    } else {
        // params 非物件（不應發生於 live-write）：對原值算 hash，fail-closed 由 verify 兜底
        params.clone()
    };
    let bytes = canonical_bytes(&target);
    hex::encode(Sha256::digest(&bytes))
}

// ---------------------------------------------------------------------------
// Bind-string + 常數時間 HMAC verify
// ---------------------------------------------------------------------------

/// 組 bind-string：`canonical_patch_hash ∥0x1f∥ engine ∥0x1f∥ method ∥0x1f∥ ts ∥0x1f∥ nonce`。
/// engine 在 Phase 0 恆為 "live"（token 只為 live 鑄造）。
pub(crate) fn build_bind_bytes(
    canonical_patch_hash: &str,
    engine: &str,
    method: &str,
    ts: i64,
    nonce: &str,
) -> Vec<u8> {
    let mut b = Vec::new();
    b.extend_from_slice(canonical_patch_hash.as_bytes());
    b.push(US);
    b.extend_from_slice(engine.as_bytes());
    b.push(US);
    b.extend_from_slice(method.as_bytes());
    b.push(US);
    b.extend_from_slice(ts.to_string().as_bytes());
    b.push(US);
    b.extend_from_slice(nonce.as_bytes());
    b
}

/// 常數時間驗證 live_authz_token。
///
/// 為何 fail-closed + 常數時間：token 是 live RiskConfig 寫入的能力憑證；secret 空、
/// hex 解碼失敗、HMAC 不符一律回 false（不洩任何中間資訊）。復用 connection.rs 的
/// `Mac::verify_slice` primitive 防時序攻擊，**不**用 `==` 比 hex 字串。
pub(crate) fn verify_live_authz_token(secret: &str, bind_bytes: &[u8], token_hex: &str) -> bool {
    if secret.is_empty() {
        // secret 缺失 = kill-switch fail-closed（Python 也無法鑄 token）。
        return false;
    }
    let Ok(mut mac) = HmacSha256::new_from_slice(secret.as_bytes()) else {
        return false;
    };
    mac.update(bind_bytes);
    let Ok(token_bytes) = hex::decode(token_hex) else {
        return false;
    };
    mac.verify_slice(&token_bytes).is_ok()
}

// ---------------------------------------------------------------------------
// NonceLedger — 單次 nonce 帳本（process-global singleton）
// ---------------------------------------------------------------------------

/// 單次 nonce 帳本。key=nonce hex，value=mint ts（秒）。
///
/// 不變量：verify 成功且 TTL 內後，先 check nonce 不在帳本（在 → 拒 nonce_replay）→
/// 插入 → 才放行。每次插入順帶 lazy 驅逐 `now - ts > TTL` 的舊條目（避免背景 task）。
/// 硬上界 MAX_NONCE_LEDGER（DoS 安全閥）。
pub(crate) struct NonceLedger {
    seen: Mutex<HashMap<String, i64>>,
}

/// nonce check-and-insert 結果。
#[derive(Debug, PartialEq, Eq)]
pub(crate) enum NonceOutcome {
    /// nonce 首見，已記錄，放行。
    Fresh,
    /// nonce 已用過（TTL 內重放）。
    Replay,
    /// 帳本滿（DoS 安全閥觸發）。
    LedgerFull,
}

impl NonceLedger {
    pub(crate) fn new() -> Self {
        Self {
            seen: Mutex::new(HashMap::new()),
        }
    }

    /// check-and-insert：原子地檢查 nonce 是否已用、驅逐過期條目、插入新 nonce。
    /// `now` 為當前 Unix 秒。
    pub(crate) fn check_and_insert(&self, nonce: &str, ts: i64, now: i64) -> NonceOutcome {
        let mut map = match self.seen.lock() {
            Ok(g) => g,
            // 鎖中毒（panic 殘留）→ fail-closed，當作滿擋下。
            Err(_) => return NonceOutcome::LedgerFull,
        };
        // lazy 驅逐過期條目（now - ts > TTL）。
        map.retain(|_, &mut v| now - v <= LIVE_AUTHZ_TTL_SECS);
        if map.contains_key(nonce) {
            return NonceOutcome::Replay;
        }
        if map.len() >= MAX_NONCE_LEDGER {
            return NonceOutcome::LedgerFull;
        }
        map.insert(nonce.to_string(), ts);
        NonceOutcome::Fresh
    }

    #[cfg(test)]
    pub(crate) fn len(&self) -> usize {
        self.seen.lock().map(|m| m.len()).unwrap_or(0)
    }
}

/// Process-global NonceLedger singleton。登記於 singleton-registry.md §2。
/// 用 OnceLock 而非穿過 dispatch_request 已龐大的參數鏈（doc §0.1 明示二擇一）。
static NONCE_LEDGER: OnceLock<NonceLedger> = OnceLock::new();

/// 取 process-global NonceLedger（首次呼叫惰性建立）。
pub(crate) fn nonce_ledger() -> &'static NonceLedger {
    NONCE_LEDGER.get_or_init(NonceLedger::new)
}

// ---------------------------------------------------------------------------
// chokepoint 主入口
// ---------------------------------------------------------------------------

/// live-write authz reject 理由碼（與 Python 端 + V014 config_reject payload 對齊）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum LiveAuthzReject {
    MissingToken,
    TokenExpired,
    NonceReplay,
    NonceLedgerFull,
    BadToken,
}

impl LiveAuthzReject {
    pub(crate) fn code(self) -> &'static str {
        match self {
            LiveAuthzReject::MissingToken => "missing_token",
            LiveAuthzReject::TokenExpired => "token_expired",
            LiveAuthzReject::NonceReplay => "nonce_replay",
            LiveAuthzReject::NonceLedgerFull => "nonce_ledger_full",
            LiveAuthzReject::BadToken => "bad_token",
        }
    }
}

/// chokepoint 核心檢查：對 engine==live 的 LIVE_WRITE_METHODS 強制驗 token。
/// 回 Ok(()) 放行；Err(reject) fail-closed（caller 寫 V014 reject row + 回 ERR_INVALID_REQUEST）。
///
/// `now` 為當前 Unix 秒（caller 注入，便於測試）。`secret` 由 caller 經
/// `secret_env::var_or_file("OPENCLAW_LIVE_PATCH_SECRET")` 讀（None → ""，verify 必失敗）。
pub(crate) fn check_live_authz(
    method: &str,
    params: &serde_json::Value,
    secret: &str,
    now: i64,
    ledger: &NonceLedger,
) -> Result<(), LiveAuthzReject> {
    // 取 token 三欄；缺任一 → missing_token。
    let token = params
        .get("live_authz_token")
        .and_then(|v| v.as_str());
    let nonce = params
        .get("live_authz_nonce")
        .and_then(|v| v.as_str());
    let ts = params.get("live_authz_ts").and_then(|v| v.as_i64());
    let (token, nonce, ts) = match (token, nonce, ts) {
        (Some(t), Some(n), Some(s)) if !t.is_empty() && !n.is_empty() => (t, n, s),
        _ => return Err(LiveAuthzReject::MissingToken),
    };

    // TTL 檢查（|now - ts| > TTL → token_expired）。先於 HMAC 驗，避免對過期 token 做無謂計算。
    //
    // 為何用 i128 寬類型：`ts` 來自 attacker-controlled `params["live_authz_ts"]`
    // （serde_json as_i64 接受 i64::MIN..=i64::MAX）。i64 直接 `(now - ts).abs()` 對
    // ts=i64::MIN 在 debug / overflow-checks build 會 panic（減法溢位，且 .abs() 對
    // i64::MIN 二次溢位），使整個 fail-closed 不變量依賴「release 恰好關溢位檢查」這個
    // 脆弱前提。i128 提升後減法與 abs 永不溢位（i64 全域差落在 i128 安全範圍），極端
    // ts 一律落 TokenExpired fail-closed，永不 panic。
    if (now as i128 - ts as i128).abs() > LIVE_AUTHZ_TTL_SECS as i128 {
        return Err(LiveAuthzReject::TokenExpired);
    }

    // canonical hash + bind-string + 常數時間 HMAC verify。
    let canonical_hash = canonical_hash_for(method, params);
    let bind = build_bind_bytes(&canonical_hash, "live", method, ts, nonce);
    if !verify_live_authz_token(secret, &bind, token) {
        return Err(LiveAuthzReject::BadToken);
    }

    // verify 成功後才碰 nonce 帳本（單次性 + DoS 安全閥）。
    // 為何在 verify 後：未經驗證的 nonce 不應污染帳本（否則攻擊者可灌任意 nonce 撐爆）。
    match ledger.check_and_insert(nonce, ts, now) {
        NonceOutcome::Fresh => Ok(()),
        NonceOutcome::Replay => Err(LiveAuthzReject::NonceReplay),
        NonceOutcome::LedgerFull => Err(LiveAuthzReject::NonceLedgerFull),
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn mint(secret: &str, method: &str, params: &serde_json::Value, ts: i64, nonce: &str) -> String {
        let hash = canonical_hash_for(method, params);
        let bind = build_bind_bytes(&hash, "live", method, ts, nonce);
        let mut mac = HmacSha256::new_from_slice(secret.as_bytes()).unwrap();
        mac.update(&bind);
        hex::encode(mac.finalize().into_bytes())
    }

    // ── T12 canonical 跨語言 fixture（命門）──
    // 這些 bytes 必與 Python live_patch_token.canonical_json 對同一 JSON 的輸出位元一致。
    // Python 端 test_live_patch_token.py 用同一組 fixture 斷言相同 bytes/hash。
    #[test]
    fn t12_canonical_fixtures_stable() {
        // (JSON 輸入, 期望 canonical bytes) — 與 Python 對齊基準
        let cases: &[(serde_json::Value, &str)] = &[
            (
                json!({"limits":{"leverage_max":50.0,"per_trade_risk_pct":0.03},"agent":{"size_multiplier":1.0}}),
                r#"{"agent":{"size_multiplier":1.0},"limits":{"leverage_max":50.0,"per_trade_risk_pct":0.03}}"#,
            ),
            (
                json!({"b":2,"a":1,"中文键":"值","nested":{"z":0.1,"y":-0.0,"x":100000000.0}}),
                r#"{"a":1,"b":2,"nested":{"x":100000000.0,"y":-0.0,"z":0.1},"中文键":"值"}"#,
            ),
            (
                json!({"arr":[1,2.5,"three",{"k":0.03}],"flag":true,"none":null}),
                r#"{"arr":[1,2.5,"three",{"k":0.03}],"flag":true,"none":null}"#,
            ),
        ];
        for (v, expected) in cases {
            let got = String::from_utf8(canonical_bytes(v)).unwrap();
            assert_eq!(&got, expected, "canonical bytes mismatch for {v:?}");
        }
    }

    // 印出 fixture hash 供 Python 對齊（手動執行：cargo test print_t12 -- --nocapture）
    #[test]
    fn print_t12_fixture_hashes() {
        let fixtures: &[serde_json::Value] = &[
            json!({"limits":{"leverage_max":50.0,"per_trade_risk_pct":0.03},"agent":{"size_multiplier":1.0}}),
            json!({"cost_gate":{"k_taker":0.0000001,"min_confidence":0.625}}),
            json!({"b":2,"a":1,"中文键":"值","nested":{"z":0.1,"y":-0.0,"x":100000000.0}}),
            json!({"arr":[1,2.5,"three",{"k":0.03}],"flag":true,"none":null}),
            json!({"big":1e20,"small":1.5e-10,"whole":3.0,"neg":-42.75}),
        ];
        for (i, v) in fixtures.iter().enumerate() {
            let bytes = canonical_bytes(v);
            let h = hex::encode(Sha256::digest(&bytes));
            println!("RS[{i}] sha256={h} bytes={:?}", String::from_utf8_lossy(&bytes));
        }
    }

    #[test]
    fn canonical_hash_patch_branch_uses_only_patch() {
        // patch 類：token 三欄 + engine 變動不影響 hash（只看 patch）
        let p1 = json!({"engine":"live","patch":{"limits":{"leverage_max":50.0}},"source":"operator"});
        let p2 = json!({"engine":"live","patch":{"limits":{"leverage_max":50.0}},
                        "source":"operator","live_authz_token":"x","live_authz_nonce":"y","live_authz_ts":123});
        assert_eq!(
            canonical_hash_for("patch_risk_config", &p1),
            canonical_hash_for("patch_risk_config", &p2)
        );
        // patch 值不同 → hash 不同
        let p3 = json!({"engine":"live","patch":{"limits":{"leverage_max":60.0}}});
        assert_ne!(
            canonical_hash_for("patch_risk_config", &p1),
            canonical_hash_for("patch_risk_config", &p3)
        );
    }

    #[test]
    fn canonical_hash_nonpatch_branch_excludes_token_and_engine() {
        // 非 patch 類：去 token 三欄 + engine 後算 hash
        let p1 = json!({"engine":"live","enabled":true,"symbol":"BTCUSDT"});
        let p2 = json!({"engine":"live","enabled":true,"symbol":"BTCUSDT",
                        "live_authz_token":"x","live_authz_nonce":"y","live_authz_ts":99});
        assert_eq!(
            canonical_hash_for("set_dynamic_risk_enabled", &p1),
            canonical_hash_for("set_dynamic_risk_enabled", &p2)
        );
        // 旋鈕欄變動 → hash 不同
        let p3 = json!({"engine":"live","enabled":false,"symbol":"BTCUSDT"});
        assert_ne!(
            canonical_hash_for("set_dynamic_risk_enabled", &p1),
            canonical_hash_for("set_dynamic_risk_enabled", &p3)
        );
    }

    #[test]
    fn verify_constant_time_accepts_valid_rejects_tampered() {
        let secret = "test_live_patch_secret";
        let hash = "deadbeef";
        let bind = build_bind_bytes(hash, "live", "patch_risk_config", 1700000000, "nonce123");
        let mut mac = HmacSha256::new_from_slice(secret.as_bytes()).unwrap();
        mac.update(&bind);
        let token = hex::encode(mac.finalize().into_bytes());
        assert!(verify_live_authz_token(secret, &bind, &token));
        // 篡改 bind → 拒
        let bad_bind = build_bind_bytes(hash, "live", "update_risk_config", 1700000000, "nonce123");
        assert!(!verify_live_authz_token(secret, &bad_bind, &token));
        // 空 secret → 拒（kill-switch）
        assert!(!verify_live_authz_token("", &bind, &token));
        // 非 hex token → 拒
        assert!(!verify_live_authz_token(secret, &bind, "not-hex-zz"));
    }

    #[test]
    fn check_live_authz_happy_path() {
        let secret = "s3cr3t";
        let now = 1_700_000_000i64;
        let params = json!({
            "engine":"live",
            "patch":{"limits":{"leverage_max":50.0}},
            "source":"operator",
            "live_authz_nonce":"abc",
            "live_authz_ts": now,
        });
        let token = mint(secret, "patch_risk_config", &params, now, "abc");
        let mut params = params;
        params["live_authz_token"] = json!(token);
        let ledger = NonceLedger::new();
        assert_eq!(
            check_live_authz("patch_risk_config", &params, secret, now, &ledger),
            Ok(())
        );
    }

    #[test]
    fn check_live_authz_nonpatch_happy_path() {
        // FIX 2 interop（非-patch 類，analogous to T12）：證明 generalize 後的非-patch
        // mint↔verify 路徑成立——對 resume_paper{engine:live} / set_dynamic_risk_enabled
        // {engine:live} 這類 non-patch LIVE_WRITE_METHOD，用「params 去 token 三欄 + engine」
        // 的 canonical hash 鑄 token，check_live_authz 必 ACCEPT。Python call_params_with_token
        // 對同一份 params 走同一 hash 分支（hash_target_for），故跨語言互通。
        let secret = "s3cr3t";
        let now = 1_700_000_000i64;
        // resume_paper：params 只有 engine（去 engine 後 hash 對象 = {}）。
        let params_resume = json!({
            "engine":"live",
            "live_authz_nonce":"rp1",
            "live_authz_ts": now,
        });
        let token = mint(secret, "resume_paper", &params_resume, now, "rp1");
        let mut params_resume = params_resume;
        params_resume["live_authz_token"] = json!(token);
        let ledger = NonceLedger::new();
        assert_eq!(
            check_live_authz("resume_paper", &params_resume, secret, now, &ledger),
            Ok(()),
            "non-patch resume_paper mint↔verify must interop"
        );

        // set_dynamic_risk_enabled：params 有旋鈕欄 enabled（hash 對象 = {"enabled":true}）。
        let params_dyn = json!({
            "engine":"live",
            "enabled": true,
            "live_authz_nonce":"dr1",
            "live_authz_ts": now,
        });
        let token2 = mint(secret, "set_dynamic_risk_enabled", &params_dyn, now, "dr1");
        let mut params_dyn = params_dyn;
        params_dyn["live_authz_token"] = json!(token2);
        let ledger2 = NonceLedger::new();
        assert_eq!(
            check_live_authz("set_dynamic_risk_enabled", &params_dyn, secret, now, &ledger2),
            Ok(()),
            "non-patch set_dynamic_risk_enabled mint↔verify must interop"
        );
        // 旋鈕欄被竄改（enabled true→false）後拿原 token → bad_token（hash 綁旋鈕值）。
        let mut tampered = params_dyn.clone();
        tampered["enabled"] = json!(false);
        tampered["live_authz_nonce"] = json!("dr2"); // 換 nonce 避免 replay 混淆
        let ledger3 = NonceLedger::new();
        assert_eq!(
            check_live_authz("set_dynamic_risk_enabled", &tampered, secret, now, &ledger3),
            Err(LiveAuthzReject::BadToken),
            "tampered knob value must reject (hash binds the knob)"
        );
    }

    #[test]
    fn check_live_authz_missing_token() {
        let params = json!({"engine":"live","patch":{"limits":{"leverage_max":50.0}}});
        let ledger = NonceLedger::new();
        assert_eq!(
            check_live_authz("patch_risk_config", &params, "s", 1700000000, &ledger),
            Err(LiveAuthzReject::MissingToken)
        );
    }

    #[test]
    fn check_live_authz_expired_and_ttl_boundary() {
        let secret = "s3cr3t";
        let mint_ts = 1_700_000_000i64;
        let params_base = json!({
            "engine":"live","patch":{"limits":{"leverage_max":50.0}},
            "live_authz_nonce":"n1","live_authz_ts": mint_ts,
        });
        let token = mint(secret, "patch_risk_config", &params_base, mint_ts, "n1");
        let mut params = params_base.clone();
        params["live_authz_token"] = json!(token);

        // now = mint+24s → 過（≤25）
        let ledger = NonceLedger::new();
        assert_eq!(
            check_live_authz("patch_risk_config", &params, secret, mint_ts + 24, &ledger),
            Ok(())
        );
        // now = mint+26s → token_expired（>25），用新 nonce 避免 replay 混淆
        let mut params2 = params_base.clone();
        params2["live_authz_nonce"] = json!("n2");
        let token2 = mint(secret, "patch_risk_config", &params2, mint_ts, "n2");
        params2["live_authz_token"] = json!(token2);
        let ledger2 = NonceLedger::new();
        assert_eq!(
            check_live_authz("patch_risk_config", &params2, secret, mint_ts + 26, &ledger2),
            Err(LiveAuthzReject::TokenExpired)
        );
    }

    #[test]
    fn check_live_authz_extreme_ts_no_panic() {
        // FIX 1：attacker-controlled ts=i64::MIN / i64::MAX 必回 TokenExpired，
        // 不得 panic（debug / overflow-checks build 下 i64 `(now - ts).abs()` 會溢位 panic）。
        let secret = "s3cr3t";
        let now = 1_700_000_000i64;
        let ledger = NonceLedger::new();
        for extreme_ts in [i64::MIN, i64::MAX, i64::MIN + 1, i64::MAX - 1] {
            let params = json!({
                "engine":"live",
                "patch":{"limits":{"leverage_max":50.0}},
                "live_authz_token":"00",
                "live_authz_nonce":"k",
                "live_authz_ts": extreme_ts,
            });
            // TTL 檢查先於 HMAC verify → 極端 ts 必先落 TokenExpired，永不到 nonce/HMAC。
            assert_eq!(
                check_live_authz("patch_risk_config", &params, secret, now, &ledger),
                Err(LiveAuthzReject::TokenExpired),
                "extreme ts={extreme_ts} should fail-closed TokenExpired, not panic"
            );
        }
    }

    #[test]
    fn check_live_authz_nonce_replay() {
        let secret = "s3cr3t";
        let now = 1_700_000_000i64;
        let params_base = json!({
            "engine":"live","patch":{"limits":{"leverage_max":50.0}},
            "live_authz_nonce":"replay_me","live_authz_ts": now,
        });
        let token = mint(secret, "patch_risk_config", &params_base, now, "replay_me");
        let mut params = params_base;
        params["live_authz_token"] = json!(token);
        let ledger = NonceLedger::new();
        assert_eq!(
            check_live_authz("patch_risk_config", &params, secret, now, &ledger),
            Ok(())
        );
        // 第二次同 token/nonce → nonce_replay（TTL 內也擋）
        assert_eq!(
            check_live_authz("patch_risk_config", &params, secret, now, &ledger),
            Err(LiveAuthzReject::NonceReplay)
        );
    }

    #[test]
    fn check_live_authz_cross_method_reuse_rejected() {
        // 拿 patch_risk_config 的 token 送 update_risk_config → bad_token（bind method 不符）
        let secret = "s3cr3t";
        let now = 1_700_000_000i64;
        let params = json!({
            "engine":"live","patch":{"limits":{"leverage_max":50.0}},
            "live_authz_nonce":"x1","live_authz_ts": now,
        });
        let token = mint(secret, "patch_risk_config", &params, now, "x1");
        let mut params = params;
        params["live_authz_token"] = json!(token);
        let ledger = NonceLedger::new();
        assert_eq!(
            check_live_authz("update_risk_config", &params, secret, now, &ledger),
            Err(LiveAuthzReject::BadToken)
        );
    }

    #[test]
    fn check_live_authz_cross_patch_reuse_rejected() {
        // 拿改 leverage 的 token 送改 cost_gate 的 patch → bad_token（canonical_patch_hash 不符）
        let secret = "s3cr3t";
        let now = 1_700_000_000i64;
        let params = json!({
            "engine":"live","patch":{"limits":{"leverage_max":50.0}},
            "live_authz_nonce":"x2","live_authz_ts": now,
        });
        let token = mint(secret, "patch_risk_config", &params, now, "x2");
        let mut tampered = params.clone();
        tampered["patch"] = json!({"limits":{"leverage_max":99.0}});
        tampered["live_authz_token"] = json!(token);
        let ledger = NonceLedger::new();
        assert_eq!(
            check_live_authz("patch_risk_config", &tampered, secret, now, &ledger),
            Err(LiveAuthzReject::BadToken)
        );
    }

    #[test]
    fn check_live_authz_empty_secret_killswitch() {
        // secret 撤除 → 任何 token 都 fail-closed（bad_token）
        let now = 1_700_000_000i64;
        let params = json!({
            "engine":"live","patch":{"limits":{"leverage_max":50.0}},
            "live_authz_token":"00", "live_authz_nonce":"k","live_authz_ts": now,
        });
        let ledger = NonceLedger::new();
        assert_eq!(
            check_live_authz("patch_risk_config", &params, "", now, &ledger),
            Err(LiveAuthzReject::BadToken)
        );
    }

    #[test]
    fn nonce_ledger_evicts_expired_and_bounded() {
        let ledger = NonceLedger::new();
        // 插入一個過期 nonce（ts 很舊）
        assert_eq!(ledger.check_and_insert("old", 1000, 1000), NonceOutcome::Fresh);
        // now 遠超 TTL → 下次插入時 old 被驅逐，且 old 不再阻擋（可重用，因已過期）
        let now = 1000 + LIVE_AUTHZ_TTL_SECS + 100;
        assert_eq!(ledger.check_and_insert("new", now, now), NonceOutcome::Fresh);
        // old 已被 retain 驅逐 → 重插 old（用 fresh ts）應 Fresh 非 Replay
        assert_eq!(ledger.check_and_insert("old", now, now), NonceOutcome::Fresh);
        assert_eq!(ledger.len(), 2); // new + old（fresh），無無界增長
    }

    #[test]
    fn nonce_ledger_full_safety_valve() {
        let ledger = NonceLedger::new();
        let now = 1_700_000_000i64;
        // 灌滿到上界
        for i in 0..MAX_NONCE_LEDGER {
            assert_eq!(
                ledger.check_and_insert(&format!("n{i}"), now, now),
                NonceOutcome::Fresh
            );
        }
        // 超限 → LedgerFull
        assert_eq!(
            ledger.check_and_insert("overflow", now, now),
            NonceOutcome::LedgerFull
        );
    }

    /// FIX 3（contract test，sec-coverage MEDIUM）：對「本測試 curate 的 state-mutating
    /// `match method` arm 集合」逐一斷言每個 arm 必須「在 LIVE_WRITE_METHODS」或「在下方
    /// 明確、已 review 的豁免清單」二擇一（XOR）。把已知 mutator 拉出 allowlist 而未補豁免
    /// → 本測試紅，強制做分類決策（杜絕「已知 mutator 靜默漏掉 live gate = fail-open」退化）。
    ///
    /// **誠實邊界（re-review code MED）**：本測試「不」由 dispatch.rs `match method` 編譯期
    /// 自動衍生集合——它驗的是「本檔手維 curated 集合」的 XOR 不變式，**無法**自動抓到「作者
    /// 在 dispatch.rs 新增 arm 卻忘了登進本表」的漏列。理由：Rust 無廉價的編譯期反射可枚舉
    /// `match` arm 字面，硬接 dispatch.rs token 解析的成本/脆性遠高於收益。故改以「維護紀律」
    /// 兜底，並把 docstring 措辭從「every state-mutating arm」訂正為「curated 集合的 XOR」。
    ///
    /// 維護紀律（CC checklist，新增 dispatch mutator 必做）：在 dispatch.rs `match method`
    /// 新增任何 state-mutating arm 時，**必**(a) 把 method 名加進 LIVE_WRITE_METHODS（會被
    /// chokepoint 蓋）或下方 EXEMPT_MUTATORS（附豁免理由），且 (b) 同步把該 arm 名加進本測試
    /// STATE_MUTATING_ARMS。漏 (b) 不會讓本測試紅，但漏 (a) 會（一旦 arm 入了 STATE_MUTATING_ARMS）。
    /// 本表由 dispatch.rs `match method` 親 grep 列舉（2026-06-17，dispatch.rs:214-609）。
    #[test]
    fn contract_every_mutator_is_gated_or_explicitly_exempt() {
        // dispatch.rs `match method` 內所有「會改 runtime 狀態」的 arm（讀取型 get_*/query_*
        // 不列入）。
        const STATE_MUTATING_ARMS: &[&str] = &[
            // pipeline 控制
            "pause_paper",
            "resume_paper",
            "reset_paper_state",
            "close_all_positions",
            "cancel_all_orders",
            "close_position",
            // strategy 寫
            "update_strategy_params",
            "set_strategy_active",
            "submit_paper_order",
            // risk / governor / dynamic-risk / exit / drawdown / loss-counter 寫
            "update_risk_config",
            "clear_consecutive_losses",
            "reset_drawdown_baseline",
            "restore_exit_config_defaults",
            "set_dynamic_risk_enabled",
            "force_governor_tier_tighter",
            "force_governor_tier_looser",
            // config 寫
            "patch_risk_config",
            "patch_learning_config",
            "patch_budget_config",
            "reload_config",
            // governance lease 寫
            "governance.acquire_lease",
            "governance.release_lease",
            // 系統模式 / 預算 / teacher / AI usage / h-state 寫
            "set_system_mode",
            "update_ai_budget_config",
            "record_ai_usage",
            "set_teacher_loop_enabled",
            "invalidate_h_state",
            // advisory wake-up（無直接 mutation，僅喚醒既有 daemon 重讀）
            "trigger_live_auth_recheck",
            "reload_edge_estimates",
        ];

        // 明確、已 review 的豁免清單：這些 mutator 刻意不走 Phase 0 live-write token gate。
        // 豁免理由（Phase 0 SCOPE = 「改 live RiskConfig / runtime 風控旋鈕」）：
        const EXEMPT_MUTATORS: &[(&str, &str)] = &[
            // 平倉 / 下單 / 撤單面：屬 lease / order authority / Decision-Lease 既有治理，
            // 非 RiskConfig 面；且為生存 exit 路徑（緊急平倉/撤單必須永遠可達，不可被
            // live-write token 攔）。OUT-OF-SCOPE。
            ("close_all_positions", "order/lease authority; survival exit must never be token-gated"),
            ("cancel_all_orders", "order/lease authority; survival exit must never be token-gated"),
            ("close_position", "order/lease authority; survival exit must never be token-gated"),
            ("submit_paper_order", "paper-side order submit; order authority, not RiskConfig"),
            // 系統模式廣播：set_system_mode 是硬邊界（CLAUDE §四），由 Python live-auth
            // 路徑與既有 GUI gate 治理，且廣播全 pipeline（非 engine-specific），不在
            // engine==live 的 RiskConfig token 模型內。OUT-OF-SCOPE（不可碰硬邊界）。
            ("set_system_mode", "hard-boundary system_mode; broadcast all-pipeline, governed elsewhere"),
            // AI 預算 / learning config / AI usage / teacher loop：budget/learning/ai-config
            // 面，非 live 交易風控旋鈕；Phase 0 SCOPE 明示 OUT-OF-SCOPE。
            ("update_ai_budget_config", "AI budget config, out-of-scope (not live RiskConfig)"),
            ("record_ai_usage", "AI usage telemetry, out-of-scope"),
            ("set_teacher_loop_enabled", "teacher loop toggle, out-of-scope (not live RiskConfig)"),
            ("patch_learning_config", "learning config, out-of-scope (not live RiskConfig)"),
            ("patch_budget_config", "budget config, out-of-scope (not live RiskConfig)"),
            // reload_config：熱換 ConfigManager TOML（connection/WS/ConfigManager 參數，
            // ArcSwap），是真 runtime 狀態變更，但「不收」任何 engine 參數（非 engine-specific
            // 的 live RiskConfig 寫），不在 LIVE_WRITE_METHODS，也不碰 live 風控/生存旋鈕。
            // OUT-OF-SCOPE（Phase 0 SCOPE = 「改 live RiskConfig / runtime 風控旋鈕」）。
            ("reload_config", "hot-swaps ConfigManager TOML; takes NO engine param, not a live RiskConfig/survival mutator"),
            // governance lease 寫：lease lifecycle 由 GovernanceCore 治理，dormant（Python
            // flag OPENCLAW_LEASE_PYTHON_IPC_ENABLED 打開前不主動呼叫），不碰 RiskConfig。
            ("governance.acquire_lease", "lease lifecycle, GovernanceCore-governed, not RiskConfig"),
            ("governance.release_lease", "lease lifecycle, GovernanceCore-governed, not RiskConfig"),
            // h-state 失效：advisory 反向 IPC cache invalidation（env-gated），不改 RiskConfig。
            ("invalidate_h_state", "advisory cache invalidation, not RiskConfig"),
            // advisory wake-up：只 tx.try_send(()) 喚醒既有 daemon 重讀（live-auth watcher /
            // edge estimates reload），本身不直接改 runtime 狀態（真正的重讀/重載由被喚醒的
            // daemon 走其自身路徑），不收 engine 參數，非 live RiskConfig 寫。OUT-OF-SCOPE。
            ("trigger_live_auth_recheck", "advisory wake-up (tx.try_send), no direct state mutation"),
            ("reload_edge_estimates", "advisory wake-up (tx.try_send), no direct state mutation"),
        ];

        for &arm in STATE_MUTATING_ARMS {
            let gated = LIVE_WRITE_METHODS.contains(&arm);
            let exempt = EXEMPT_MUTATORS.iter().any(|(m, _)| *m == arm);
            assert!(
                gated ^ exempt,
                "mutator '{arm}' must be EITHER in LIVE_WRITE_METHODS OR on the exemption list \
                 (exactly one). gated={gated} exempt={exempt}. \
                 A new mutator must declare its classification — see this test's comment."
            );
        }

        // 反向：豁免清單不得列入根本不存在於 STATE_MUTATING_ARMS 的名字（防腐爛）。
        for (m, _) in EXEMPT_MUTATORS {
            assert!(
                STATE_MUTATING_ARMS.contains(m),
                "exemption '{m}' references a method not in STATE_MUTATING_ARMS — stale exemption?"
            );
        }
    }

    #[test]
    fn requires_live_authz_gating() {
        // engine==live + allowlist method → gated
        assert!(requires_live_authz("live", "patch_risk_config"));
        assert!(requires_live_authz("live", "update_strategy_params"));
        // demo/paper → 永不 gated（即使 allowlist method）
        assert!(!requires_live_authz("demo", "patch_risk_config"));
        assert!(!requires_live_authz("paper", "patch_risk_config"));
        // 唯讀 method → 不在 allowlist → 不 gated
        assert!(!requires_live_authz("live", "get_risk_config"));
        assert!(!requires_live_authz("live", "governance.get_status"));
    }
}
