//! U4：以暫存簽名輸入啟動真正的 replay_runner，固定缺省接線與拒絕行為。
#![cfg(feature = "replay_isolated")]
use openclaw_engine::replay::manifest_signer::{
    canonical_body_for_signing, compute_body_hash, compute_key_fingerprint, ManifestSigner,
};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::{
    fs,
    process::{Command, Output},
};

struct BinaryCase {
    dir: tempfile::TempDir,
    fixture: std::path::PathBuf,
}
impl BinaryCase {
    fn new(rows: Vec<Value>) -> Self {
        let dir = tempfile::tempdir().unwrap();
        let fixture = dir.path().join("fixture.json");
        fs::write(
            &fixture,
            serde_json::to_vec(
                &json!({"schema_version":1,"source":"s2_bybit_public","events":rows}),
            )
            .unwrap(),
        )
        .unwrap();
        Self { dir, fixture }
    }
    fn body(&self) -> Value {
        json!({"experiment_id":"u4-test","data_tier":"S2","fixture_uri":self.fixture})
    }
    fn sign(&self, mut body: Value) {
        // 金鑰只存在每個測試自己的暫存目錄。
        let raw = vec![42_u8; 32];
        let key = format!("{}\n", hex::encode(&raw));
        fs::write(self.dir.path().join("key.hex"), &key).unwrap();
        let signer =
            ManifestSigner::new_from_bytes_for_test(raw, compute_key_fingerprint(key.as_bytes()));
        let canonical = canonical_body_for_signing(&serde_json::to_vec(&body).unwrap()).unwrap();
        body["signature"] = json!(signer.sign(&canonical));
        body["manifest_hash"] = json!(compute_body_hash(&canonical));
        fs::write(
            self.dir.path().join("manifest.json"),
            serde_json::to_vec(&body).unwrap(),
        )
        .unwrap();
    }
    fn run(&self) -> Output {
        Command::new(env!("CARGO_BIN_EXE_replay_runner"))
            .env("OPENCLAW_REPLAY_MAC_NO_PRIVATE", "1")
            .args([
                "--manifest",
                self.dir.path().join("manifest.json").to_str().unwrap(),
                "--output-dir",
                self.dir.path().join("out").to_str().unwrap(),
            ])
            .output()
            .unwrap()
    }
    fn report(&self) -> std::path::PathBuf {
        self.dir.path().join("out/replay_report.json")
    }
}
fn event(ts: u64, symbol: &str) -> Value {
    json!({"ts_ms":ts,"symbol":symbol,"open":100,"high":101,"low":99,"close":100,"volume":1})
}
fn success(output: Output) {
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
}
fn rejected(case: &BinaryCase, message: &str) {
    let output = case.run();
    assert!(!output.status.success());
    assert!(
        String::from_utf8_lossy(&output.stderr).contains(message),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(!case.report().exists());
}

fn default_case(mode: &str) {
    let mut rows = vec![
        event(60_000, "BTCUSDT"),
        event(120_000, "BTCUSDT"),
        event(180_000, "BTCUSDT"),
    ];
    if mode == "quotes" {
        rows.push(event(180_000, "ETHUSDT"));
        for row in &mut rows {
            row["best_bid"] = json!(99.);
            row["best_ask"] = json!(101.);
            row["bid_size"] = json!(100.);
            row["ask_size"] = json!(100.);
            row["bid_depth_5"] = json!(1000.);
            row["ask_depth_5"] = json!(1000.);
        }
    }
    let c = BinaryCase::new(rows);
    let mut body = c.body();
    if mode != "synthetic" && mode != "s3" {
        body["strategy"] = json!("ma_crossover");
    }
    if mode == "params" {
        body["strategy_params"] =
            serde_json::to_value(openclaw_engine::strategies::StrategyParamsConfig::default())
                .unwrap();
        body["risk_overrides"] =
            serde_json::to_value(openclaw_engine::config::RiskConfig::default()).unwrap();
    }
    if mode == "latency" {
        body["execution_calibration"] = json!({"recommended_latency_ms":25});
    }
    if mode == "full_chain" {
        body["mode"] = json!("full_chain");
    }
    if mode == "s3" {
        body["data_tier"] = json!("S3");
        let mut fixture: Value = serde_json::from_slice(&fs::read(&c.fixture).unwrap()).unwrap();
        fixture["source"] = json!("s3_synthetic");
        fs::write(&c.fixture, serde_json::to_vec(&fixture).unwrap()).unwrap();
    }
    c.sign(body);
    let first = c.run();
    if mode == "params" {
        let stderr = String::from_utf8_lossy(&first.stderr);
        assert!(stderr.contains("strategy_params_supplied=true"));
        assert!(stderr.contains("risk_overrides_supplied=true"));
    }
    success(first);
    let before = fs::read(c.report()).unwrap();
    let report: Value = serde_json::from_slice(&before).unwrap();
    assert_eq!(report["result"]["status"]["kind"], "completed");
    for key in ["stage1", "parameter_provenance", "parameter_overrides"] {
        assert!(report.get(key).is_none(), "unexpected {key} in {mode}");
    }
    // 移除舊報告，確保第二次執行確實產生新輸出。
    fs::remove_file(c.report()).unwrap();
    success(c.run());
    let after = fs::read(c.report()).unwrap();
    // 僅移除時間戳所在行，不重新序列化 JSON 或忽略其他欄位。
    let stable = |bytes: &[u8]| -> Vec<u8> {
        let report: Value = serde_json::from_slice(bytes).unwrap();
        assert!(report["generated_at_ms"].as_u64().is_some());
        let lines: Vec<&[u8]> = bytes.split_inclusive(|b| *b == b'\n').collect();
        let prefix = b"  \"generated_at_ms\": ";
        assert_eq!(
            lines.iter().filter(|line| line.starts_with(prefix)).count(),
            1
        );
        lines
            .into_iter()
            .filter(|line| !line.starts_with(prefix))
            .flatten()
            .copied()
            .collect()
    };
    assert_eq!(
        stable(&before),
        stable(&after),
        "{mode} report bytes changed"
    );
}
#[test]
fn default_synthetic_is_stable() {
    default_case("synthetic");
}
#[test]
fn default_strategy_params_and_risk_are_stable() {
    default_case("params");
}
#[test]
fn default_execution_latency_is_stable() {
    default_case("latency");
}
#[test]
fn default_s3_is_stable() {
    default_case("s3");
}
#[test]
fn default_full_chain_is_stable() {
    default_case("full_chain");
}
#[test]
fn default_multi_symbol_quotes_are_stable() {
    default_case("quotes");
}
#[test]
fn extension_requires_explicit_strategy() {
    let c = BinaryCase::new(vec![event(1, "BTCUSDT")]);
    let mut body = c.body();
    body["include_replay_metadata"] = json!(true);
    c.sign(body);
    rejected(&c, "require an explicit strategy");
}
fn invalid_selector(value: Value, message: &str) {
    let mut row = event(1, "BTCUSDT");
    row["selector_decision"] = value;
    let c = BinaryCase::new(vec![row]);
    let mut body = c.body();
    body["strategy"] = json!("ma_crossover");
    c.sign(body);
    rejected(&c, message);
}
#[test]
fn oversized_selector_is_rejected() {
    invalid_selector(
        json!({"action":"SIZE_DOWN","size_factor":2}),
        "SIZE_DOWN size_factor must be finite in (0,1]",
    );
}
#[test]
fn explicit_null_selector_is_rejected() {
    invalid_selector(Value::Null, "invalid type: null");
}
#[test]
fn provenance_and_overrides_round_trip_with_correct_fixture_hash() {
    let c = BinaryCase::new(vec![event(1, "BTCUSDT"), event(2, "BTCUSDT")]);
    let mut body = c.body();
    body["strategy"] = json!("ma_crossover");
    body["parameter_provenance"] = json!({"source_kind":"caller_snapshot","fixture":{"sha256":hex::encode(Sha256::digest(fs::read(&c.fixture).unwrap()))}});
    body["parameter_overrides"] = json!([{"path":"strategy_params.ma_crossover.use_maker_entry","before":true,"after":false,"reason":"test explicit taker"}]);
    body["strategy_params"] = json!({"ma_crossover":{"use_maker_entry":false}});
    c.sign(body.clone());
    success(c.run());
    let report: Value = serde_json::from_slice(&fs::read(c.report()).unwrap()).unwrap();
    assert_eq!(report["parameter_provenance"], body["parameter_provenance"]);
    assert_eq!(report["parameter_overrides"], body["parameter_overrides"]);
    assert!(report["stage1"].is_object());
}
#[test]
fn signed_body_tampering_fails_signature_verification() {
    let c = BinaryCase::new(vec![event(1, "BTCUSDT")]);
    c.sign(c.body());
    let path = c.dir.path().join("manifest.json");
    let mut signed: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
    signed["experiment_id"] = json!("tampered");
    fs::write(&path, serde_json::to_vec(&signed).unwrap()).unwrap();
    rejected(&c, "manifest_hash_mismatch");
    // 即使竄改者重算公開雜湊，原 HMAC 仍必須驗證失敗。
    let canonical = canonical_body_for_signing(&serde_json::to_vec(&signed).unwrap()).unwrap();
    signed["manifest_hash"] = json!(compute_body_hash(&canonical));
    fs::write(&path, serde_json::to_vec(&signed).unwrap()).unwrap();
    rejected(&c, "signature_mismatch");
}
