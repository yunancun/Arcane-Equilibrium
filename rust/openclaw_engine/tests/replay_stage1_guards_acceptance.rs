//! U2：以真正 binary 與公開函式驗證單次 fixture 讀取、防護與失敗保全。
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
            serde_json::to_vec(&json!({"schema_version":1,"source":"s3_synthetic","events":rows}))
                .unwrap(),
        )
        .unwrap();
        Self { dir, fixture }
    }
    fn body(&self) -> Value {
        json!({"experiment_id":"u2-test","data_tier":"S3","fixture_uri":self.fixture})
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
            // 啟動守衛會讀這兩個來源的禁用標記；移除後子程序只看本案例的輸入。
            .env_remove("OPENCLAW_REPLAY_FORBIDDEN_TRIPPED")
            .env_remove("OPENCLAW_DATA_DIR")
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
#[test]
fn binary_hash_matches_and_single_byte_tamper_fails() {
    let c = BinaryCase::new(vec![event(1, "BTCUSDT"), event(2, "BTCUSDT")]);
    let mut body = c.body();
    body["strategy"] = json!("ma_crossover");
    body["parameter_provenance"] =
        json!({"fixture":{"sha256":hex::encode(Sha256::digest(fs::read(&c.fixture).unwrap()))}});
    c.sign(body);
    success(c.run());
    fs::remove_dir_all(c.dir.path().join("out")).unwrap();
    // 新增一個有效 JSON 空白位元組也必須使雜湊不符。
    use std::io::Write;
    fs::OpenOptions::new()
        .append(true)
        .open(&c.fixture)
        .unwrap()
        .write_all(b" ")
        .unwrap();
    rejected(&c, "fixture sha256 mismatch");
}
#[test]
fn binary_missing_fixture_keeps_typed_error_with_path() {
    let c = BinaryCase::new(vec![event(1, "BTCUSDT")]);
    c.sign(c.body());
    fs::remove_file(&c.fixture).unwrap();
    // 改為單次讀取後，仍須回報既有的具型別錯誤與檔案路徑，不能只剩作業系統訊息。
    rejected(&c, "FixtureNotFound");
    rejected(&c, "fixture.json");
}
#[test]
fn binary_non_string_fixture_hash_is_rejected() {
    let c = BinaryCase::new(vec![event(1, "BTCUSDT")]);
    for value in [json!(123), Value::Null, json!(["ab"])] {
        let mut body = c.body();
        body["strategy"] = json!("ma_crossover");
        body["parameter_provenance"] = json!({"fixture":{"sha256":value}});
        c.sign(body);
        rejected(&c, "fixture sha256 must be a string");
    }
}
#[test]
fn binary_legacy_without_hash_still_runs() {
    let c = BinaryCase::new(vec![event(1, "BTCUSDT")]);
    c.sign(c.body());
    success(c.run());
    let report: Value = serde_json::from_slice(&fs::read(c.report()).unwrap()).unwrap();
    assert!(report.get("stage1").is_none());
}
#[test]
fn binary_global_time_regression_rejected_only_in_next_mode() {
    let c = BinaryCase::new(vec![
        event(1, "BTCUSDT"),
        event(3, "BTCUSDT"),
        event(2, "ETHUSDT"),
        event(4, "ETHUSDT"),
    ]);
    let mut body = c.body();
    body["strategy"] = json!("ma_crossover");
    body["execution_timing"] = json!("next_symbol_open");
    c.sign(body.clone());
    rejected(&c, "nondecreasing global timestamps");
    body.as_object_mut().unwrap().remove("execution_timing");
    c.sign(body);
    success(c.run());
}
#[test]
fn binary_equal_timestamps_across_symbols_are_accepted_in_next_mode() {
    // 全域檢查只擋時間倒退；不同標的同一時間戳是合法的多標的輸入。
    let c = BinaryCase::new(vec![
        event(1, "BTCUSDT"),
        event(1, "ETHUSDT"),
        event(2, "BTCUSDT"),
        event(2, "ETHUSDT"),
    ]);
    let mut body = c.body();
    body["strategy"] = json!("ma_crossover");
    body["execution_timing"] = json!("next_symbol_open");
    c.sign(body);
    success(c.run());
    let report: Value = serde_json::from_slice(&fs::read(c.report()).unwrap()).unwrap();
    assert_eq!(report["stage1"]["execution_timing"], "next_symbol_open");
}
#[test]
fn binary_overrides_without_strategy_rejected_independently() {
    let c = BinaryCase::new(vec![event(1, "BTCUSDT")]);
    let mut body = c.body();
    body["parameter_overrides"] = json!([]);
    c.sign(body);
    rejected(&c, "parameter_overrides require an explicit strategy");
}

use openclaw_core::{
    alpha_surface::{AlphaSourceTag, AlphaSurface},
    guardian::GuardianConfig,
};
use openclaw_engine::{
    config::RiskConfig,
    intent_processor::OrderIntent,
    replay::{
        build_isolated_pipeline,
        fixture_loader::{load_fixtures, FixtureSource},
        profile::ReplayProfile,
        risk_adapter::{ReplayPaperSnapshot, ReplayRiskAdapter},
        runner::IsolatedPipeline,
        stage1::{extend_report, ExecutionTiming, Stage1Config},
        strategy_adapter::ReplayStrategyAdapter,
    },
    strategies::{Strategy, StrategyAction},
    tick_pipeline::TickContext,
};
use std::collections::HashMap;
struct Scripted {
    actions: HashMap<u64, Vec<StrategyAction>>,
}
impl Strategy for Scripted {
    fn name(&self) -> &str {
        "u2_probe"
    }
    fn is_active(&self) -> bool {
        true
    }
    fn set_active(&mut self, _: bool) {}
    fn declared_alpha_sources(&self) -> &[AlphaSourceTag] {
        &[]
    }
    fn on_tick(&mut self, ctx: &TickContext<'_>, _: &AlphaSurface<'_>) -> Vec<StrategyAction> {
        self.actions.remove(&ctx.timestamp_ms).unwrap_or_default()
    }
}
fn open(long: bool) -> StrategyAction {
    StrategyAction::Open(serde_json::from_value::<OrderIntent>(json!({"symbol":"BTCUSDT","is_long":long,"qty":1.,"confidence":0.99,"strategy":"u2_probe","order_type":"market","limit_price":null})).unwrap())
}
fn close() -> StrategyAction {
    StrategyAction::Close {
        symbol: "BTCUSDT".into(),
        confidence: 1.,
        reason: "exit".into(),
    }
}
fn library_case(rows: Vec<Value>, timing: ExecutionTiming) -> (IsolatedPipeline, Stage1Config) {
    let c = BinaryCase::new(rows);
    let src = FixtureSource::S3Synthetic {
        path: c.fixture.clone(),
    };
    let events = load_fixtures(&src).unwrap();
    let config = Stage1Config::from_fixture(&c.fixture, &events, timing, None, true).unwrap();
    (
        build_isolated_pipeline(ReplayProfile::Isolated, "u2-library".into(), "S3", events)
            .unwrap(),
        config,
    )
}
fn adapted(
    pipeline: IsolatedPipeline,
    script: Vec<(u64, Vec<StrategyAction>)>,
) -> IsolatedPipeline {
    let adapter = ReplayStrategyAdapter::new(
        Box::new(Scripted {
            actions: script.into_iter().collect(),
        }),
        ReplayProfile::Isolated,
    )
    .unwrap();
    let risk = ReplayRiskAdapter::new(
        ReplayProfile::Isolated,
        GuardianConfig::default(),
        RiskConfig::default(),
        0.02,
        None,
    )
    .unwrap();
    let snap = ReplayPaperSnapshot {
        balance: 10000.,
        drawdown_pct: 0.,
        positions: vec![],
        latest_price: Some(100.),
        latest_price_by_symbol: HashMap::new(),
        exposure_pct: 0.,
        correlated_exposure_pct: 0.,
        leverage: 0.,
        daily_loss_pct: 0.,
        trade_stats: None,
    };
    pipeline.with_adapter_pipeline(adapter, risk, snap).unwrap()
}
fn library_run(
    rows: Vec<Value>,
    script: Vec<(u64, Vec<StrategyAction>)>,
    timing: ExecutionTiming,
) -> openclaw_engine::replay::ReplayResult {
    let (p, c) = library_case(rows, timing);
    let mut p = adapted(p, script).with_stage1(c).unwrap();
    p.execute().unwrap();
    p.into_result()
}
#[test]
fn enabled_config_without_adapter_returns_error() {
    let (p, c) = library_case(vec![event(1, "BTCUSDT")], ExecutionTiming::NextSymbolOpen);
    // 固定原因：兩種誤用互換、或因別的原因報錯，都不能通過。
    let error = p.with_stage1(c).err().unwrap().to_string();
    assert!(error.contains("stage1 requires a strategy adapter"), "{error}");
}
#[test]
fn config_count_mismatch_returns_error_before_execution() {
    let (p, _) = library_case(vec![event(1, "BTCUSDT")], ExecutionTiming::NextSymbolOpen);
    let (_, c) = library_case(
        vec![event(1, "BTCUSDT"), event(2, "BTCUSDT")],
        ExecutionTiming::NextSymbolOpen,
    );
    let error = adapted(p, vec![]).with_stage1(c).err().unwrap().to_string();
    assert!(error.contains("stage1 fixture row mismatch"), "{error}");
}
#[test]
fn next_mode_zero_records_have_zero_price_and_legacy_veto_keeps_price() {
    let rows = vec![event(1, "BTCUSDT"), event(2, "BTCUSDT")];
    let mut limit = open(true);
    if let StrategyAction::Open(i) = &mut limit {
        i.order_type = "limit".into();
        i.limit_price = Some(100.);
    }
    for (actions, reason) in [
        (vec![limit], "unsupported_nonmarket"),
        (vec![open(true), open(true)], "pending_open_exists"),
        (vec![close()], "close_no_position"),
    ] {
        let r = library_run(
            rows.clone(),
            vec![(1, actions)],
            ExecutionTiming::NextSymbolOpen,
        );
        let zero = r.fills.iter().find(|f| f.fill_status == reason).unwrap();
        assert_eq!(zero.qty, 0.);
        assert_eq!(zero.price, 0., "{reason}");
    }
    let mut veto = rows;
    veto[0]["selector_decision"] = json!({"action":"VETO"});
    for timing in [
        ExecutionTiming::NextSymbolOpen,
        ExecutionTiming::CurrentBarClose,
    ] {
        let r = library_run(veto.clone(), vec![(1, vec![open(true)])], timing);
        assert_eq!(r.fills[0].fill_status, "selector_veto");
        assert_eq!(r.fills[0].qty, 0.);
        assert_eq!(
            r.fills[0].price,
            if timing == ExecutionTiming::NextSymbolOpen {
                0.
            } else {
                100.
            }
        );
    }
}
#[test]
fn close_and_reverse_open_same_signal_close_without_reversal() {
    let r = library_run(
        vec![
            event(1, "BTCUSDT"),
            event(2, "BTCUSDT"),
            event(3, "BTCUSDT"),
        ],
        vec![(1, vec![open(true)]), (2, vec![close(), open(false)])],
        ExecutionTiming::NextSymbolOpen,
    );
    assert_eq!(r.fills.len(), 3);
    assert!(r.fills[0].qty > 0.);
    assert_eq!(r.fills[1].qty, r.fills[0].qty);
    assert_eq!(r.fills[1].effective_ts_ms, Some(3));
    assert_eq!(r.fills[1].side, "short");
    assert_eq!(r.fills[2].fill_status, "reduction_position_changed");
    assert_eq!(r.fills[2].qty, 0.);
    assert_eq!(r.fills[2].price, 0.);
}
#[test]
fn extended_report_success_preserves_original_fields() {
    let dir = tempfile::tempdir().unwrap();
    let p = dir.path().join("report.json");
    fs::write(&p, b"{\"original\":17}").unwrap();
    extend_report(&p, Some(json!({"action_audit":[]})), None, None).unwrap();
    let r: Value = serde_json::from_slice(&fs::read(&p).unwrap()).unwrap();
    assert_eq!(r["original"], 17);
    assert_eq!(r["stage1"]["action_audit"], json!([]));
    assert_eq!(fs::read_dir(dir.path()).unwrap().count(), 1);
}
#[test]
#[cfg(unix)]
fn report_temp_write_failure_preserves_original_bytes() {
    use std::os::unix::fs::PermissionsExt;
    let dir = tempfile::tempdir().unwrap();
    let p = dir.path().join("report.json");
    let original = b"{\"original\":17}\n";
    fs::write(&p, original).unwrap();
    // 原檔可寫但父目錄不可建立暫存檔；直接截斷原檔的舊實作會讓此測試失敗。
    let permissions = fs::metadata(dir.path()).unwrap().permissions();
    fs::set_permissions(dir.path(), fs::Permissions::from_mode(0o555)).unwrap();
    // 以 root 執行時目錄權限不生效，無法用這個方式注入失敗；先探測，避免在那種環境假失敗。
    let probe = dir.path().join("probe");
    if fs::write(&probe, b"").is_ok() {
        fs::set_permissions(dir.path(), permissions).unwrap();
        eprintln!("skipped: directory permissions are not enforced for this user");
        return;
    }
    let result = extend_report(&p, Some(json!({"action_audit":[]})), None, None);
    fs::set_permissions(dir.path(), permissions).unwrap();
    assert!(result.is_err());
    assert_eq!(fs::read(&p).unwrap(), original);
}
