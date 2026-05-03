//! REF-20 Wave 4 R20-P2b-T1 — replay fixture loader (S2 Bybit public + S3 synthetic).
//! REF-20 Wave 4 R20-P2b-T1 — replay fixture 載入器（S2 Bybit 公開 + S3 合成）。
//!
//! MODULE_NOTE (EN):
//!   Loads market events for the isolated replay runner from S2 (Bybit
//!   public-data snapshot) or S3 (synthetic OHLC/tick) fixtures specified in
//!   the manifest's `data_tier` + `fixture_uri` fields.
//!
//!   V3 §6.2 contract bindings:
//!     - 0 network call (pure file IO; the S2 tier expects fixture files
//!       already curated by PA / operator under
//!       `srv/research_notes/replay_fixtures/` per workplan §7.1 #5).
//!     - 0 import of `intent_processor`, `ipc_server`, `bybit_*` (REST/WS),
//!       `governance_hub`, `decision_lease`, `canary_writer`, `database`.
//!     - Returns a flat `Vec<MarketEvent>`; the caller's `IsolatedPipeline`
//!       (in `runner.rs`) walks the vector deterministically.
//!
//!   Tier semantics:
//!     - `S2BybitPublic`: a JSON file with public Bybit OHLC/tick rows
//!       previously dumped by an operator. The schema is intentionally
//!       narrow (just enough to drive the in-memory pipeline) so we don't
//!       drag the live `bybit_rest_client` / `bybit_private_ws` types.
//!     - `S3Synthetic`: a JSON file with hand-crafted OHLC bars; same
//!       schema as S2 with `source: "synthetic"` so a downstream auditor can
//!       distinguish the tier without re-deriving from manifest. (V3 §11
//!       data_tier classification.)
//!
//!   Schema (both tiers share same `MarketEvent` shape):
//!     ```json
//!     {
//!       "schema_version": 1,
//!       "source": "s2_bybit_public" | "s3_synthetic",
//!       "events": [
//!         { "ts_ms": 1714521600000, "symbol": "BTCUSDT",
//!           "open": 65000.0, "high": 65100.0, "low": 64900.0,
//!           "close": 65050.0, "volume": 1.234 },
//!         ...
//!       ]
//!     }
//!     ```
//!
//!   Fail-closed behaviour:
//!     - Missing fixture file -> `FixtureNotFound`.
//!     - Unparseable JSON -> `FixtureFormat`.
//!     - Schema version mismatch (≠ 1) -> `FixtureFormat` with version
//!       diagnostic.
//!     - 0 events -> `FixtureEmpty` (replay over empty market is meaningless;
//!       caller should treat as a fixture authoring error not a 0-fill run).
//!     - On Mac with `runtime_environment = "linux_trade_core"` -> handled by
//!       `mac_policy_guard` upstream; this module trusts the guard ran.
//!
//! MODULE_NOTE (中):
//!   為 isolated replay runner 從 manifest `data_tier` + `fixture_uri` 指定
//!   的 S2（Bybit 公開資料快照）或 S3（合成 OHLC/tick）fixture 載入市場事件。
//!
//!   V3 §6.2 契約綁定：
//!     - 0 network call（純 file IO；S2 tier 預期 fixture 已由 PA / operator
//!       於 `srv/research_notes/replay_fixtures/` 預先策展，per workplan
//!       §7.1 #5）。
//!     - 0 import `intent_processor` / `ipc_server` / `bybit_*` (REST/WS) /
//!       `governance_hub` / `decision_lease` / `canary_writer` / `database`。
//!     - 回傳扁平 `Vec<MarketEvent>`；caller 的 `IsolatedPipeline`
//!       （`runner.rs`）確定性走訪 vector。
//!
//!   Tier 語意：
//!     - `S2BybitPublic`：含 Bybit 公開 OHLC/tick row 的 JSON file，由 operator
//!       事先 dump。schema 刻意極窄（僅足以推動 in-memory pipeline），不拖入
//!       live 的 `bybit_rest_client` / `bybit_private_ws` 型別。
//!     - `S3Synthetic`：含手工 OHLC bar 的 JSON file；schema 與 S2 相同，
//!       `source: "synthetic"` 讓下游 auditor 不需從 manifest 重推即可區分
//!       tier（V3 §11 data_tier 分類）。
//!
//!   Schema（兩 tier 共用 `MarketEvent` 形狀）：見 EN 區段。
//!
//!   Fail-closed 行為：
//!     - 找不到 fixture file -> `FixtureNotFound`。
//!     - JSON 無法解析 -> `FixtureFormat`。
//!     - Schema 版本不符（≠ 1）-> `FixtureFormat` 含版本診斷。
//!     - 0 event -> `FixtureEmpty`（空市場 replay 無意義；caller 視為 fixture
//!       撰寫錯誤而非 0-fill run）。
//!     - Mac 上若 `runtime_environment = "linux_trade_core"` 由上游
//!       `mac_policy_guard` 處理；本模組信任 guard 已跑。
//!
//! SPEC: REF-20 V3 §4.1 data_tier + §6.1 + §6.2 + workplan §4 Wave 4 R20-P2b-T1.

use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

// ─────────────────────────────────────────────────────────────────────────
// Public types / 公開型別
// ─────────────────────────────────────────────────────────────────────────

/// Single market event (OHLC + volume row) consumed by the in-memory
/// replay pipeline.
///
/// in-memory replay pipeline 消費的單一市場事件（OHLC + volume row）。
///
/// Field semantics (EN):
///   - `ts_ms`: unix millisecond timestamp (UTC).
///   - `symbol`: Bybit symbol (e.g. `BTCUSDT`); free-form string at this
///     layer because we do not validate symbol against an exchange-side
///     allowlist (replay binary has 0 exchange access).
///   - `open` / `high` / `low` / `close`: OHLC prices; finite f64 expected.
///   - `volume`: trading volume; finite f64 expected, may be 0.0 for thin
///     markets.
///
/// 欄位語意（中）：
///   - `ts_ms`: Unix 毫秒時戳（UTC）。
///   - `symbol`: Bybit symbol（如 `BTCUSDT`）；本層為自由字串，因 replay
///     binary 0 交易所存取，不驗 symbol 對應 exchange-side allowlist。
///   - `open` / `high` / `low` / `close`: OHLC 價格；預期有限 f64。
///   - `volume`: 交易量；預期有限 f64，瘦市場可能 0.0。
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
pub struct MarketEvent {
    pub ts_ms: i64,
    pub symbol: String,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: f64,
}

/// Fixture source enum mapping to manifest `data_tier`.
///
/// 對應 manifest `data_tier` 的 fixture 來源 enum。
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FixtureSource {
    /// S2 — Bybit public-data snapshot (operator-curated, sha-pinned).
    /// S2 — Bybit 公開資料快照（operator 策展 / sha-pin）。
    S2BybitPublic { path: PathBuf },
    /// S3 — synthetic OHLC/tick (hand-crafted; deterministic).
    /// S3 — 合成 OHLC/tick（手工撰寫 / 確定性）。
    S3Synthetic { path: PathBuf },
}

impl FixtureSource {
    /// Resolve fixture source from manifest `data_tier` + `fixture_uri`
    /// strings. `fixture_uri` is interpreted as a filesystem path (V3 §6.2
    /// allowlist: `replay://...` or `<runtime-local>` paths). Schemes
    /// other than the bare path form are rejected for Wave 4 (the
    /// `replay://` scheme is reserved for the future in-DB artifact lookup
    /// path which Wave 8 P6 handoff will reach for).
    ///
    /// 從 manifest `data_tier` + `fixture_uri` 字串解析 fixture 來源。
    /// `fixture_uri` 解讀為檔案系統路徑（V3 §6.2 allowlist：`replay://...`
    /// 或 `<runtime-local>` 路徑）。Wave 4 拒絕 bare path 以外的 scheme
    /// （`replay://` scheme 保留給未來 in-DB artifact lookup 路徑，
    /// Wave 8 P6 handoff 才用得到）。
    pub fn from_manifest_strings(
        data_tier: &str,
        fixture_uri: &str,
    ) -> Result<Self, FixtureError> {
        // Wave 4 only accepts plain-path fixture_uri; `replay://` reserved
        // for Wave 8 in-DB artifact lookup.
        // Wave 4 僅接受純路徑 fixture_uri；`replay://` 保留給 Wave 8 in-DB
        // artifact lookup。
        if fixture_uri.starts_with("replay://") {
            return Err(FixtureError::UnsupportedScheme {
                uri: fixture_uri.to_string(),
            });
        }
        let path = PathBuf::from(fixture_uri);
        match data_tier {
            "S2" => Ok(FixtureSource::S2BybitPublic { path }),
            "S3" => Ok(FixtureSource::S3Synthetic { path }),
            // S0 / S1 / S4 are not allowed in isolated replay (S0/S1 = private
            // runtime data, S4 = live ML labels — both forbidden by V3 §6.2 +
            // §6.3 Mac policy + §4.1 data_tier definition).
            // S0 / S1 / S4 不允許於 isolated replay（S0/S1 = private runtime
            // data，S4 = live ML labels — 皆被 V3 §6.2 + §6.3 Mac 政策 +
            // §4.1 data_tier 定義禁止）。
            other => Err(FixtureError::ForbiddenTier {
                tier: other.to_string(),
            }),
        }
    }

    /// Filesystem path to the fixture file.
    ///
    /// Fixture file 的 filesystem 路徑。
    pub fn path(&self) -> &Path {
        match self {
            FixtureSource::S2BybitPublic { path } => path,
            FixtureSource::S3Synthetic { path } => path,
        }
    }

    /// Tier label (`"S2"` / `"S3"`) for diagnostic logs and report writer.
    ///
    /// Tier label（`"S2"` / `"S3"`）供診斷日誌與 report writer 使用。
    pub fn tier_label(&self) -> &'static str {
        match self {
            FixtureSource::S2BybitPublic { .. } => "S2",
            FixtureSource::S3Synthetic { .. } => "S3",
        }
    }
}

/// Fixture loader failure modes.
///
/// Fixture loader 失敗模式。
#[derive(Debug)]
pub enum FixtureError {
    /// Fixture file path does not exist OR is not readable.
    /// Fixture file 路徑不存在或無法讀取。
    FixtureNotFound { path: PathBuf, source: std::io::Error },
    /// Fixture file exists but JSON cannot be parsed / schema mismatch.
    /// Fixture file 存在但 JSON 無法解析 / schema 不符。
    FixtureFormat { path: PathBuf, reason: String },
    /// Fixture file parsed OK but `events` array is empty.
    /// Fixture file 解析 OK 但 `events` 陣列為空。
    FixtureEmpty { path: PathBuf },
    /// `data_tier` enum value not allowed for isolated replay (S0/S1/S4).
    /// `data_tier` enum 值不允於 isolated replay（S0/S1/S4）。
    ForbiddenTier { tier: String },
    /// `fixture_uri` uses an unsupported scheme (Wave 4 only accepts plain path).
    /// `fixture_uri` 使用不支援的 scheme（Wave 4 僅接受純路徑）。
    UnsupportedScheme { uri: String },
}

impl std::fmt::Display for FixtureError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::FixtureNotFound { path, source } => write!(
                f,
                "FixtureError::FixtureNotFound{{path={}, io={}}}",
                path.display(),
                source
            ),
            Self::FixtureFormat { path, reason } => write!(
                f,
                "FixtureError::FixtureFormat{{path={}, reason={reason}}}",
                path.display()
            ),
            Self::FixtureEmpty { path } => write!(
                f,
                "FixtureError::FixtureEmpty{{path={}}} — replay over empty market is meaningless",
                path.display()
            ),
            Self::ForbiddenTier { tier } => write!(
                f,
                "FixtureError::ForbiddenTier{{tier={tier}}} — \
                 isolated replay only accepts S2 or S3 (V3 §6.2 + §4.1)"
            ),
            Self::UnsupportedScheme { uri } => write!(
                f,
                "FixtureError::UnsupportedScheme{{uri={uri}}} — \
                 Wave 4 only accepts plain filesystem path; `replay://` reserved for Wave 8"
            ),
        }
    }
}

impl std::error::Error for FixtureError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::FixtureNotFound { source, .. } => Some(source),
            _ => None,
        }
    }
}

/// On-disk fixture envelope.
///
/// 磁碟 fixture 包裹格式。
#[derive(Debug, Deserialize)]
struct FixtureEnvelope {
    schema_version: u32,
    #[allow(dead_code)] // Used only for diagnostic `source_label` echo on report.
    source: String,
    events: Vec<MarketEvent>,
}

// ─────────────────────────────────────────────────────────────────────────
// Public API / 公開 API
// ─────────────────────────────────────────────────────────────────────────

/// Load market events from a `FixtureSource`.
///
/// 從 `FixtureSource` 載入市場事件。
///
/// Semantics (EN):
///   - Reads the file at `source.path()` synchronously.
///   - Parses as `FixtureEnvelope` (schema_version + source + events).
///   - Asserts `schema_version == 1`.
///   - Asserts `events.len() > 0`.
///   - Returns `Vec<MarketEvent>` (cloned out of envelope).
///
/// 語意（中）：
///   - 同步讀 `source.path()` 檔案。
///   - 解析為 `FixtureEnvelope`（schema_version + source + events）。
///   - 斷言 `schema_version == 1`。
///   - 斷言 `events.len() > 0`。
///   - 回 `Vec<MarketEvent>`（從 envelope clone）。
///
/// SAFETY / 不變量:
///   - This function is read-only on filesystem; 0 mutate.
///   - Caller MUST have run `mac_policy_guard::enforce()` upstream when on
///     macOS (V3 §6.3); this module does not re-validate.
///
/// SAFETY / 不變量：
///   - 本函式對 filesystem 唯讀；0 mutate。
///   - macOS 上 caller 必先跑 `mac_policy_guard::enforce()`（V3 §6.3）；
///     本模組不重複驗。
pub fn load_fixtures(source: &FixtureSource) -> Result<Vec<MarketEvent>, FixtureError> {
    let path = source.path();
    let raw = std::fs::read_to_string(path).map_err(|e| FixtureError::FixtureNotFound {
        path: path.to_path_buf(),
        source: e,
    })?;
    let envelope: FixtureEnvelope =
        serde_json::from_str(&raw).map_err(|e| FixtureError::FixtureFormat {
            path: path.to_path_buf(),
            reason: format!("serde_json: {}", e),
        })?;

    if envelope.schema_version != 1 {
        return Err(FixtureError::FixtureFormat {
            path: path.to_path_buf(),
            reason: format!(
                "schema_version mismatch: got {}, expected 1",
                envelope.schema_version
            ),
        });
    }
    if envelope.events.is_empty() {
        return Err(FixtureError::FixtureEmpty {
            path: path.to_path_buf(),
        });
    }
    Ok(envelope.events)
}

// ─────────────────────────────────────────────────────────────────────────
// Module-internal unit tests / 模組內部 unit test
// ─────────────────────────────────────────────────────────────────────────
#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;

    fn write_fixture(content: &str) -> tempfile::NamedTempFile {
        let mut f = tempfile::NamedTempFile::new().unwrap();
        f.write_all(content.as_bytes()).unwrap();
        f
    }

    #[test]
    fn from_manifest_strings_s2_ok() {
        let src = FixtureSource::from_manifest_strings("S2", "/tmp/fix.json").unwrap();
        assert_eq!(src.tier_label(), "S2");
        assert_eq!(src.path(), Path::new("/tmp/fix.json"));
    }

    #[test]
    fn from_manifest_strings_s3_ok() {
        let src = FixtureSource::from_manifest_strings("S3", "/tmp/fix.json").unwrap();
        assert_eq!(src.tier_label(), "S3");
    }

    #[test]
    fn from_manifest_strings_forbidden_tier() {
        let err = FixtureSource::from_manifest_strings("S0", "/tmp/x.json").unwrap_err();
        assert!(matches!(err, FixtureError::ForbiddenTier { ref tier } if tier == "S0"));
        let err2 = FixtureSource::from_manifest_strings("S1", "/tmp/x.json").unwrap_err();
        assert!(matches!(err2, FixtureError::ForbiddenTier { .. }));
        let err3 = FixtureSource::from_manifest_strings("S4", "/tmp/x.json").unwrap_err();
        assert!(matches!(err3, FixtureError::ForbiddenTier { .. }));
    }

    #[test]
    fn from_manifest_strings_replay_scheme_rejected() {
        let err = FixtureSource::from_manifest_strings("S2", "replay://artifact_id/x").unwrap_err();
        assert!(matches!(err, FixtureError::UnsupportedScheme { .. }));
    }

    #[test]
    fn load_fixture_happy_path() {
        let fixture = write_fixture(
            r#"{
              "schema_version": 1,
              "source": "s3_synthetic",
              "events": [
                {"ts_ms": 1, "symbol": "BTCUSDT",
                 "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1.0},
                {"ts_ms": 2, "symbol": "BTCUSDT",
                 "open": 100.5, "high": 102.0, "low": 100.0, "close": 101.5, "volume": 2.0}
              ]
            }"#,
        );
        let src = FixtureSource::S3Synthetic {
            path: fixture.path().to_path_buf(),
        };
        let events = load_fixtures(&src).unwrap();
        assert_eq!(events.len(), 2);
        assert_eq!(events[0].ts_ms, 1);
        assert_eq!(events[1].close, 101.5);
    }

    #[test]
    fn load_fixture_missing_file() {
        let src = FixtureSource::S3Synthetic {
            path: PathBuf::from("/no/such/path/abc.json"),
        };
        let err = load_fixtures(&src).unwrap_err();
        assert!(matches!(err, FixtureError::FixtureNotFound { .. }));
    }

    #[test]
    fn load_fixture_empty_events() {
        let fixture = write_fixture(
            r#"{"schema_version": 1, "source": "s3_synthetic", "events": []}"#,
        );
        let src = FixtureSource::S3Synthetic {
            path: fixture.path().to_path_buf(),
        };
        let err = load_fixtures(&src).unwrap_err();
        assert!(matches!(err, FixtureError::FixtureEmpty { .. }));
    }

    #[test]
    fn load_fixture_bad_schema_version() {
        let fixture = write_fixture(
            r#"{"schema_version": 999, "source": "s3_synthetic", "events": [
                 {"ts_ms":1,"symbol":"X","open":1.0,"high":1.0,"low":1.0,"close":1.0,"volume":0.0}
               ]}"#,
        );
        let src = FixtureSource::S3Synthetic {
            path: fixture.path().to_path_buf(),
        };
        let err = load_fixtures(&src).unwrap_err();
        assert!(matches!(
            err,
            FixtureError::FixtureFormat { ref reason, .. } if reason.contains("schema_version")
        ));
    }

    #[test]
    fn load_fixture_bad_json() {
        let fixture = write_fixture("{not json");
        let src = FixtureSource::S3Synthetic {
            path: fixture.path().to_path_buf(),
        };
        let err = load_fixtures(&src).unwrap_err();
        assert!(matches!(err, FixtureError::FixtureFormat { .. }));
    }
}
