//! Strict fail-closed JSON parser for Claude Teacher directives.
//! Claude Teacher directive 的嚴格 fail-closed JSON parser。
//!
//! MODULE_NOTE (EN): Schema = `{type, scope, params, expiry, priority}`. Any
//!   unknown top-level field, unknown `type`, malformed shape, or expiry in the
//!   past is rejected with an error — never silently coerced. The parser is
//!   the **only** layer that decides whether a directive may proceed; the
//!   GovernanceHub veto layer (4-02) will sit downstream of this and add the
//!   actual P0/P1 boundary check.
//! MODULE_NOTE (中): Schema = `{type, scope, params, expiry, priority}`。
//!   任何未知頂層欄位、未知 `type`、形狀錯誤或過期 expiry 都會以錯誤拒絕，
//!   絕不靜默強制轉換。parser 是 **唯一** 決定 directive 能否繼續的層級；
//!   GovernanceHub veto 層（4-02）會在下游加上真正的 P0/P1 邊界檢查。

use serde::{Deserialize, Serialize};

/// Known directive action types — anything else is rejected.
/// 已知的 directive 動作類型 — 其他一律拒絕。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DirectiveType {
    /// Adjust strategy parameters in-place.
    /// 就地調整策略參數。
    AdjustParam,
    /// Pause a strategy (no new orders).
    /// 暫停策略（不再開新單）。
    PauseStrategy,
    /// Boost a LinUCB arm prior.
    /// 提升 LinUCB arm 先驗。
    BoostArm,
    /// Resume a previously paused scope.
    /// 恢復之前暫停的 scope。
    Unpause,
}

/// Parsed Teacher directive ready for governance + persistence.
/// 解析後的 Teacher directive，可送入 governance + persistence。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Directive {
    /// Action type / 動作類型
    #[serde(rename = "type")]
    pub directive_type: DirectiveType,
    /// Scope identifier — strategy name, symbol, or arm id.
    /// scope 識別 — 策略名、symbol 或 arm id。
    pub scope: String,
    /// Free-form parameter object (validated by downstream consumer).
    /// 自由形式參數物件（由下游消費者驗證）。
    pub params: serde_json::Value,
    /// UNIX seconds expiry. Past values rejected.
    /// UNIX 秒過期時間。過去值會被拒絕。
    pub expiry: i64,
    /// Priority 0–9 (higher = stronger nudge).
    /// 優先級 0–9（越高 = 越強）。
    pub priority: u8,
}

/// Parser error variants.
/// Parser 錯誤類型。
#[derive(Debug)]
pub enum ParserError {
    /// JSON failed to deserialise into Value.
    /// JSON 反序列化為 Value 失敗。
    InvalidJson(String),
    /// Top-level value is not an object.
    /// 頂層 value 不是 object。
    NotAnObject,
    /// Required field missing.
    /// 必填欄位缺失。
    MissingField(&'static str),
    /// Unknown extra field present (fail-closed).
    /// 出現未知額外欄位（fail-closed）。
    UnknownField(String),
    /// `type` value not in the known enum.
    /// `type` 值不在已知列舉中。
    UnknownType(String),
    /// Field had wrong JSON type.
    /// 欄位 JSON 類型錯誤。
    WrongType(&'static str),
    /// Expiry is in the past.
    /// expiry 在過去。
    ExpiryInPast(i64),
    /// Priority out of [0, 9] range.
    /// priority 不在 [0, 9] 範圍。
    PriorityOutOfRange(i64),
}

const ALLOWED_FIELDS: &[&str] = &["type", "scope", "params", "expiry", "priority"];

/// Parse a directive JSON string with strict fail-closed semantics.
/// 以嚴格 fail-closed 語義解析 directive JSON 字串。
pub fn parse_directive(json: &str) -> Result<Directive, ParserError> {
    let v: serde_json::Value =
        serde_json::from_str(json).map_err(|e| ParserError::InvalidJson(e.to_string()))?;
    let obj = v.as_object().ok_or(ParserError::NotAnObject)?;

    // Reject unknown fields up-front (fail-closed).
    // 先拒絕未知欄位（fail-closed）。
    for key in obj.keys() {
        if !ALLOWED_FIELDS.contains(&key.as_str()) {
            return Err(ParserError::UnknownField(key.clone()));
        }
    }

    let type_str = obj
        .get("type")
        .ok_or(ParserError::MissingField("type"))?
        .as_str()
        .ok_or(ParserError::WrongType("type"))?;
    let directive_type = match type_str {
        "adjust_param" => DirectiveType::AdjustParam,
        "pause_strategy" => DirectiveType::PauseStrategy,
        "boost_arm" => DirectiveType::BoostArm,
        "unpause" => DirectiveType::Unpause,
        other => return Err(ParserError::UnknownType(other.to_string())),
    };

    let scope = obj
        .get("scope")
        .ok_or(ParserError::MissingField("scope"))?
        .as_str()
        .ok_or(ParserError::WrongType("scope"))?
        .to_string();

    let params = obj
        .get("params")
        .ok_or(ParserError::MissingField("params"))?
        .clone();
    if !params.is_object() {
        return Err(ParserError::WrongType("params"));
    }

    let expiry = obj
        .get("expiry")
        .ok_or(ParserError::MissingField("expiry"))?
        .as_i64()
        .ok_or(ParserError::WrongType("expiry"))?;
    let now_secs = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0);
    if expiry <= now_secs {
        return Err(ParserError::ExpiryInPast(expiry));
    }

    let priority_i = obj
        .get("priority")
        .ok_or(ParserError::MissingField("priority"))?
        .as_i64()
        .ok_or(ParserError::WrongType("priority"))?;
    if !(0..=9).contains(&priority_i) {
        return Err(ParserError::PriorityOutOfRange(priority_i));
    }

    Ok(Directive {
        directive_type,
        scope,
        params,
        expiry,
        priority: priority_i as u8,
    })
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn future_secs() -> i64 {
        (std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_secs()
            + 86_400) as i64
    }

    // Test 1: a well-formed adjust_param directive parses cleanly.
    // 測試 1：格式正確的 adjust_param directive 可正常解析。
    #[test]
    fn test_parser_accepts_valid_adjust_param() {
        let json = format!(
            r#"{{"type":"adjust_param","scope":"ma_crossover","params":{{"fast":12,"slow":26}},"expiry":{},"priority":5}}"#,
            future_secs()
        );
        let d = parse_directive(&json).expect("should parse");
        assert_eq!(d.directive_type, DirectiveType::AdjustParam);
        assert_eq!(d.scope, "ma_crossover");
        assert_eq!(d.priority, 5);
        assert_eq!(d.params["fast"], 12);
    }

    // Test 2: unknown `type` value is rejected.
    // 測試 2：未知 `type` 值被拒絕。
    #[test]
    fn test_parser_rejects_unknown_type() {
        let json = format!(
            r#"{{"type":"hack_strategy","scope":"x","params":{{}},"expiry":{},"priority":1}}"#,
            future_secs()
        );
        let err = parse_directive(&json).expect_err("must reject");
        assert!(matches!(err, ParserError::UnknownType(_)));
    }

    // Test 3: extra unknown top-level field is rejected (fail-closed).
    // 測試 3：頂層多餘未知欄位被拒絕（fail-closed）。
    #[test]
    fn test_parser_rejects_extra_fields() {
        let json = format!(
            r#"{{"type":"unpause","scope":"s","params":{{}},"expiry":{},"priority":0,"backdoor":true}}"#,
            future_secs()
        );
        let err = parse_directive(&json).expect_err("must reject");
        match err {
            ParserError::UnknownField(f) => assert_eq!(f, "backdoor"),
            other => panic!("expected UnknownField, got {other:?}"),
        }
    }

    // Test 4: an expiry already in the past is rejected.
    // 測試 4：已過期的 expiry 被拒絕。
    #[test]
    fn test_parser_expiry_in_past_rejected() {
        let json =
            r#"{"type":"pause_strategy","scope":"s","params":{},"expiry":1000,"priority":2}"#;
        let err = parse_directive(json).expect_err("must reject");
        assert!(matches!(err, ParserError::ExpiryInPast(_)));
    }
}
