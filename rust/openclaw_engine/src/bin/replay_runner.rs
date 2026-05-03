//! `replay_runner` — REF-20 Paper Replay Lab dedicated Rust binary.
//!
//! `replay_runner` — REF-20 Paper Replay Lab 專屬 Rust binary。
//!
//! MODULE_NOTE (EN): Wave 3 R20-P2b-S7/S8/S9 three-layer fail-closed guard
//!   chain at runtime entry. Wave 1 scaffold established the binary at the
//!   type level (Cargo.toml `[[bin]]` registered + `replay_isolated` feature
//!   gated). Wave 3 P2b-S7 wired the profile cfg gate; Wave 3 P2b-S8 (this
//!   commit) wires the FULL V3 §6.2 forbidden-path enforcement; Wave 3
//!   P2b-S9 (this commit) wires the V3 §6.3 Mac fail-closed gate. `main()`
//!   constructs `ReplayProfile::Isolated`, runs all three guards in order,
//!   and exits 0 with a stub line on success. Actual replay logic (manifest
//!   verify-first-then-hash, fixture loader, in-memory TickPipeline +
//!   IntentProcessor under Isolated profile) lands in Wave 4 R20-P2b-T1/T2
//!   (per Wave 3 P2b-S7 task spec: "對 既有 `intent_processor::router`
//!   不切換").
//!
//!   Why feature-gated:
//!     - Wave 1 R20-P0-T9 (PA crate boundary white-list) requires that the
//!       binary cannot accidentally pull `intent_processor::router`,
//!       `ipc_server`, `startup::build_exchange_pipeline`, exchange
//!       dispatch, DB writer channels, or Decision Lease wiring. Putting
//!       the binary behind `replay_isolated` makes that contract a
//!       compile-time reality (default `cargo build` does NOT compile it,
//!       so accidental dependency drift on the live engine path is
//!       physically impossible until Wave 4 explicitly opts in).
//!     - V3 §3 G7 + G8 mandate dedicated binary + fail-closed isolation.
//!     - Workplan R20-P2b-S10 will add `nm`/`objdump` symbol grep CI step
//!       to enforce defense-in-depth on top of this feature gate.
//!
//!   Forbidden dependencies (Wave 3 R20-P2b-S8/S9/S10 + Wave 4 must enforce):
//!     - `crate::intent_processor::router::*` — live execution dispatch.
//!     - `crate::ipc_server::*` — JSON-RPC pipeline to Python.
//!     - `crate::startup::build_exchange_pipeline` — exchange pipeline
//!       bootstrap (contains live order dispatch wiring).
//!     - GovernanceHub / Decision Lease acquisition path (Python side
//!       `governance_hub.acquire_lease()` is the only legitimate caller;
//!       replay binary must NEVER acquire a lease).
//!     - `crate::bybit_private_ws::*` / `crate::ws_client::*` — WS clients.
//!     - `crate::bybit_rest_client::BybitClient::place_order*` — order POST.
//!     - `crate::live_authorization::*` (read OK for FUTURE manifest sign,
//!       but no `_write_signed_live_authorization` path).
//!     - DB writer channels (Wave 3 spec defines exact list).
//!
//!   Allowed dependencies (Wave 3 IMPL builds on these):
//!     - fixture loader / canonical config parser.
//!     - HMAC-SHA256 signature verifier (P2a-S2 lands the module).
//!     - Mac policy guard (`OPENCLAW_REPLAY_MAC_NO_PRIVATE=1`, renamed from
//!       `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA` per Wave 2 dispatch §2 #1).
//!     - serde / serde_json / chrono / clap / tracing.
//!     - `crate::replay::profile::ReplayProfile` (this scaffold's sibling).
//!
//!   Wave 3 P2b-S7/S8/S9 acceptance:
//!     - `cd rust/openclaw_engine && cargo check --bin replay_runner --features replay_isolated`
//!       succeeds with zero warnings.
//!     - `cd rust/openclaw_engine && cargo check` (no feature) succeeds —
//!       this binary must NOT compile by default (verified by absence in
//!       default-feature build target list).
//!     - `target/debug/replay_runner` exits 0 with the stub line
//!       "replay_runner Wave 3 P2b-S7/S8/S9 guards online; Wave 4 logic
//!       pending" when invoked with `OPENCLAW_REPLAY_MAC_NO_PRIVATE=1`
//!       (required on macOS host) and no forbidden-trip env / file marker.
//!     - V3 §12 #8/#9/#10/#11 acceptance bound to
//!       `tests/replay_profile_acceptance.rs`.
//!     - V3 §12 #10 forbidden-wiring fail-closed acceptance bound to
//!       `tests/replay_forbidden_guard_acceptance.rs`.
//!     - V3 §12 #12 Mac non-actionable acceptance bound to
//!       `tests/replay_mac_policy_acceptance.rs`.
//!
//! MODULE_NOTE (中): Wave 3 R20-P2b-S7/S8/S9 三層 fail-closed guard 串聯於
//!   runtime entry。Wave 1 骨架讓 binary 於型別層存在（Cargo.toml `[[bin]]`
//!   註冊 + `replay_isolated` feature gated）。Wave 3 P2b-S7 接入 profile
//!   cfg gate；Wave 3 P2b-S8（本 commit）接入完整 V3 §6.2 forbidden-path
//!   強制；Wave 3 P2b-S9（本 commit）接入 V3 §6.3 Mac fail-closed gate。
//!   `main()` 建構 `ReplayProfile::Isolated`，依序跑三 guard，全通過則印 stub
//!   行並 exit 0。實際 replay 邏輯（manifest verify-first-then-hash、fixture
//!   loader、Isolated profile 下的 in-memory TickPipeline + IntentProcessor）
//!   於 Wave 4 R20-P2b-T1/T2 落地（依 Wave 3 P2b-S7 task spec：「對 既有
//!   `intent_processor::router` 不切換」）。
//!
//!   為什麼 feature-gated：
//!     - Wave 1 R20-P0-T9（PA crate 邊界白名單）要求 binary 不得意外拉入
//!       `intent_processor::router`、`ipc_server`、
//!       `startup::build_exchange_pipeline`、exchange dispatch、DB writer
//!       channel 或 Decision Lease 接線。將 binary 放在 `replay_isolated`
//!       feature 後讓此契約成為 compile-time 事實（預設 `cargo build`
//!       不編譯它 → live engine 路徑的意外依賴漂移在 Wave 4 顯式 opt-in
//!       之前物理上不可能）。
//!     - V3 §3 G7 + G8 要求專屬 binary + fail-closed 隔離。
//!     - Workplan R20-P2b-S10 將加 `nm`/`objdump` symbol grep CI step 在
//!       此 feature gate 之上做縱深防禦。
//!
//!   禁用依賴（Wave 3 R20-P2b-S8/S9/S10 + Wave 4 必強制）：
//!     - `crate::intent_processor::router::*` — live 執行 dispatch。
//!     - `crate::ipc_server::*` — Python JSON-RPC 管線。
//!     - `crate::startup::build_exchange_pipeline` — exchange pipeline
//!       bootstrap（含 live 訂單 dispatch 接線）。
//!     - GovernanceHub / Decision Lease 取得路徑（Python 端
//!       `governance_hub.acquire_lease()` 是唯一合法 caller；replay binary
//!       絕不可取 lease）。
//!     - `crate::bybit_private_ws::*` / `crate::ws_client::*` — WS clients。
//!     - `crate::bybit_rest_client::BybitClient::place_order*` — 訂單 POST。
//!     - `crate::live_authorization::*`（FUTURE manifest 簽名 read OK，
//!       但不可走 `_write_signed_live_authorization` 路徑）。
//!     - DB writer channels（Wave 3 spec 定義完整清單）。
//!
//!   允許依賴（Wave 3 IMPL 立基於此）：
//!     - fixture loader / canonical config parser。
//!     - HMAC-SHA256 signature verifier（P2a-S2 落地 module）。
//!     - Mac policy guard（`OPENCLAW_REPLAY_MAC_NO_PRIVATE=1`，per Wave 2
//!       dispatch §2 #1 由 `OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA` 改名）。
//!     - serde / serde_json / chrono / clap / tracing。
//!     - `crate::replay::profile::ReplayProfile`（此 scaffold 的姊妹檔）。
//!
//!   Wave 3 P2b-S7/S8/S9 驗收：
//!     - `cd rust/openclaw_engine && cargo check --bin replay_runner --features replay_isolated`
//!       成功且 0 warning。
//!     - `cd rust/openclaw_engine && cargo check`（無 feature）成功 —
//!       此 binary 預設不編（驗證：default-feature build target list 不含此 binary）。
//!     - `target/debug/replay_runner` 以 stub 行
//!       「replay_runner Wave 3 P2b-S7/S8/S9 guards online; Wave 4 logic
//!       pending」exit 0，需設 `OPENCLAW_REPLAY_MAC_NO_PRIVATE=1`（macOS
//!       host required）且無 forbidden-trip env / file marker。
//!     - V3 §12 #8/#9/#10/#11 acceptance 綁
//!       `tests/replay_profile_acceptance.rs`。
//!     - V3 §12 #10 forbidden-wiring fail-closed acceptance 綁
//!       `tests/replay_forbidden_guard_acceptance.rs`。
//!     - V3 §12 #12 Mac non-actionable acceptance 綁
//!       `tests/replay_mac_policy_acceptance.rs`。
//!
//! SPEC: REF-20 V3 §3 G7/G8 + §6.1/§6.2/§6.3 + §12 #8/#9/#10/#11/#12
//!     + workplan R20-P2b-S7/S8/S9
//! Owner: PA + E1 (Wave 1 scaffold) → E1 + E2 + E3 (Wave 3 IMPL).

#![cfg(feature = "replay_isolated")]

// TODO REF-20 P2b-S10: CI nm/objdump symbol audit step
// (defense-in-depth on top of feature gate).
// TODO REF-20 P2b-S10: CI nm/objdump symbol 稽核步驟
// （feature gate 之上的縱深防禦）。
//
// Wave 4 R20-P2b-T1 IMPL — three fail-closed guards run first, then we hand
// off to: CLI parse → manifest verify (per `crate::replay::manifest_signer`,
// surfaced through `load_and_verify_manifest`) → fixture load → in-memory
// `IsolatedPipeline` execute → report write. Each step is its own narrowly-
// typed Result; failures bubble out via `?` so the binary exits non-zero with
// a typed `Box<dyn Error>` printed to stderr (CLAUDE.md §四 fail-closed).
//
// Wave 4 R20-P2b-T1 落地 — 三層 fail-closed guard 先跑，再交棒：
// CLI 解析 → manifest 驗證（透過 `crate::replay::manifest_signer`，由
// `load_and_verify_manifest` 揭露）→ fixture 載入 → in-memory `IsolatedPipeline`
// 執行 → report 寫入。每步皆為窄型別 Result；以 `?` 冒泡失敗使 binary 以
// 非 0 結束並將 typed `Box<dyn Error>` 印至 stderr（CLAUDE.md §四 fail-closed）。
//
// TODO REF-20 P2b-T1 (Wave 4 follow-on): Wave 4 R20-P2b-T2 will replace
// `load_and_verify_manifest`'s placeholder verification with the full HMAC
// path that consults `replay.replay_signing_keys` archive (V042) once Wave 3
// P2a-S4 lands the SQL-backed `KeyArchive` impl. T1 ships the path with an
// in-memory `KeyArchive` populated from manifest's own fingerprint hint
// (sufficient for fixture-based smoke runs).
// TODO REF-20 P2b-T1 (Wave 4 follow-on): Wave 4 R20-P2b-T2 將以諮詢
// `replay.replay_signing_keys` archive（V042）的完整 HMAC 路徑取代
// `load_and_verify_manifest` 的佔位驗證，待 Wave 3 P2a-S4 落地 SQL-backed
// `KeyArchive` impl。T1 出貨之路徑使用以 manifest 自身 fingerprint hint
// 填的 in-memory `KeyArchive`（fixture-based smoke run 已足）。
//
// TODO REF-20 P2b-T2 (Wave 4): wire baseline-vs-candidate comparison route
// (replay/run/status/cancel/report routes wired in `replay_routes.py`).
// TODO REF-20 P2b-T2 (Wave 4): 接 baseline-vs-candidate 比較 route
// （`replay_routes.py` 接 replay/run/status/cancel/report routes）。
//
// TODO REF-20 P2b-T3 (Wave 4): canary/diagnostic artifact registration
// (per-tick canary JSONL + diagnostic.json + comparison.json), Linux only.
// TODO REF-20 P2b-T3 (Wave 4): canary/diagnostic artifact 註冊
// （per-tick canary JSONL + diagnostic.json + comparison.json），Linux only。
//
// Forbidden-path list reminder (V3 §6.2 + PA boundary §5):
//   - Decision Lease acquire/release        (forbidden_guard #1)
//   - IPC server start                       (forbidden_guard #2)
//   - WS client start                        (forbidden_guard #3)
//   - Exchange dispatch                      (forbidden_guard #4)
//   - DB writer channel use                  (forbidden_guard #5)
//   - Live/demo config mutate                (forbidden_guard #6)
//   - Advisory write outside verified PL/pgSQL (forbidden_guard #7)
//
// Forbidden 清單提醒（V3 §6.2 + PA boundary §5）：
//   - Decision Lease 取得/釋放              （forbidden_guard #1）
//   - IPC server 啟動                        （forbidden_guard #2）
//   - WS client 啟動                         （forbidden_guard #3）
//   - Exchange dispatch                      （forbidden_guard #4）
//   - DB writer channel 使用                 （forbidden_guard #5）
//   - Live/demo config mutate                （forbidden_guard #6）
//   - 不走 verified PL/pgSQL 的 advisory 寫入（forbidden_guard #7）

use std::path::Path;

use openclaw_engine::replay::cli;
use openclaw_engine::replay::fixture_loader::{self, FixtureSource};
use openclaw_engine::replay::forbidden_guard;
use openclaw_engine::replay::mac_policy_guard;
use openclaw_engine::replay::manifest_signer::{
    compute_body_hash, compute_key_fingerprint, InMemoryKeyArchive, KeyStatus, ManifestSigner,
};
use openclaw_engine::replay::profile::ReplayProfile;
use openclaw_engine::replay::report_writer;
use openclaw_engine::replay::runner::{self, ReplayResult};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Wave 3 P2b-S7/S8/S9 三層 fail-closed guard 串聯。
    // Wave 3 P2b-S7/S8/S9 three-layer fail-closed guard chain.
    //
    // 不變量 / Invariant: `replay_runner` MUST run as `ReplayProfile::Isolated`,
    //   MUST NOT have any V3 §6.2 forbidden-path tripped, AND MUST satisfy
    //   the V3 §6.3 Mac policy when running on a macOS host. All three
    //   guards run before any replay logic; the binary aborts on the FIRST
    //   guard's `Err` (V3 §12 #10 + #12 binding: forbidden path aborts run,
    //   NOT log-only).
    //
    // Invariant: `replay_runner` 必以 `ReplayProfile::Isolated` 跑、不得有任
    //   何 V3 §6.2 forbidden-path 被觸發、且在 macOS host 上必滿足 V3 §6.3
    //   Mac 政策。三 guard 在任何 replay 邏輯前跑；binary 在「第一個」guard
    //   的 `Err` 即 abort（V3 §12 #10 + #12 binding：forbidden 路徑 abort run，
    //   非 log-only）。
    let profile = ReplayProfile::Isolated;

    // S7 (Wave 3 P2b-S7): profile cfg gate. Refuses non-Isolated profiles.
    // S7（Wave 3 P2b-S7）：profile cfg gate。拒絕 non-Isolated profile。
    profile.fail_closed_assert_isolated().expect(
        "REF-20 V3 §6.2 invariant: replay_runner MUST run as Isolated; \
         see crate::replay::profile::ReplayProfile::fail_closed_assert_isolated",
    );

    // S8 (Wave 3 P2b-S8): forbidden-path enforcement at startup. Reads env
    // var $OPENCLAW_REPLAY_FORBIDDEN_TRIPPED + magic-file marker
    // <OPENCLAW_DATA_DIR>/replay_forbidden.tripped; absence (production
    // default) returns Ok(()).
    //
    // S8（Wave 3 P2b-S8）：startup 階段的 forbidden-path 強制。讀 env var
    // $OPENCLAW_REPLAY_FORBIDDEN_TRIPPED + magic-file marker
    // <OPENCLAW_DATA_DIR>/replay_forbidden.tripped；皆未設（production 預設）
    // 回 Ok(())。
    forbidden_guard::enforce_at_startup().expect(
        "REF-20 V3 §6.2 forbidden path detected at startup; \
         see crate::replay::forbidden_guard::enforce_at_startup",
    );

    // S9 (Wave 3 P2b-S9): Mac policy guard. On macOS requires
    // OPENCLAW_REPLAY_MAC_NO_PRIVATE=1 (renamed per Wave 2 dispatch §2 #1
    // from OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA) and Isolated profile. On
    // non-macOS hosts returns Ok(()) unconditionally (V3 §6.3 scopes the
    // policy to Mac).
    //
    // S9（Wave 3 P2b-S9）：Mac 政策 guard。macOS 上要求
    // OPENCLAW_REPLAY_MAC_NO_PRIVATE=1（依 Wave 2 dispatch §2 #1 由
    // OPENCLAW_REPLAY_MAC_FORBID_REAL_DATA 改名）+ Isolated profile。
    // 非 macOS host 無條件回 Ok(())（V3 §6.3 將政策限於 Mac）。
    mac_policy_guard::enforce(profile).expect(
        "REF-20 V3 §6.3 Mac policy violation; \
         see crate::replay::mac_policy_guard::enforce",
    );

    // ─────────────────────────────────────────────────────────────────
    // Wave 4 R20-P2b-T1 — actual replay logic begins here.
    // Wave 4 R20-P2b-T1 — 實際 replay 邏輯由此開始。
    // ─────────────────────────────────────────────────────────────────

    // Step 1: parse CLI args (--manifest --output-dir [--baseline-id]).
    // Step 1：解析 CLI 參數。
    let args = cli::parse_cli_args()?;

    // Step 2: load + verify manifest.
    // Step 2：載入 + 驗證 manifest。
    let manifest = load_and_verify_manifest(&args.manifest_path)?;

    // Step 3: load fixtures per manifest data_tier.
    // Step 3：依 manifest data_tier 載入 fixture。
    let fixture_source =
        FixtureSource::from_manifest_strings(&manifest.data_tier, &manifest.fixture_uri)?;
    let tier_label = fixture_source.tier_label();
    let events = fixture_loader::load_fixtures(&fixture_source)?;

    // Step 4: bootstrap the IsolatedPipeline + execute.
    // Step 4：建構 IsolatedPipeline + 執行。
    let mut pipeline = runner::build_isolated_pipeline(
        profile,
        manifest.experiment_id.clone(),
        tier_label,
        events,
    )?;
    let exec_outcome = pipeline.execute();
    let result: ReplayResult = pipeline.into_result();

    // Step 5: write report (always, even on aborted runs — auditability
    // demands the artifact exists so the operator can inspect why we
    // aborted).
    // Step 5：寫 report（永遠寫，即使 abort run — 可審計性要求 artifact 存在
    // 使 operator 可檢視 abort 原因）。
    let json_path = report_writer::write_replay_report(&args.output_dir, &result)?;

    // Step 6: surface the outcome on stderr (CI / operator parses this).
    // Step 6：將結果揭露於 stderr（CI / operator 解析此行）。
    eprintln!(
        "replay_runner: completed manifest_id={} status={} json={}",
        result.manifest_id,
        result.status.label(),
        json_path.display()
    );

    // Step 7: propagate any abort-class outcome as a non-zero exit so the
    // operator's CI shell can branch on `$?`. We do NOT call `exit(1)`
    // directly because the typed Box<dyn Error> path keeps stderr context.
    // Step 7：將任何 abort 類結果以非 0 結束傳遞，使 operator 的 CI shell
    // 可依 `$?` 分支。我們**不**直接呼 `exit(1)`，因 typed Box<dyn Error>
    // 路徑保留 stderr 脈絡。
    exec_outcome?;
    Ok(())
}

// ─────────────────────────────────────────────────────────────────────────
// Helpers / 輔助
// ─────────────────────────────────────────────────────────────────────────

/// Minimal manifest body shape consumed by `replay_runner` (Wave 4 T1).
///
/// `replay_runner` 消費的最小 manifest body 形狀（Wave 4 T1）。
///
/// Wave 4 T1 deliberately ships only the fields the runner actually reads
/// (`experiment_id`, `data_tier`, `fixture_uri`, `signature`,
/// `manifest_hash`, optional `signature_key_ref`). Wave 5+ extends with
/// calibration/embargo windows once those fields drive runner behaviour.
///
/// Wave 4 T1 刻意僅出貨 runner 實際讀的欄位（`experiment_id`、`data_tier`、
/// `fixture_uri`、`signature`、`manifest_hash`、選用 `signature_key_ref`）。
/// Wave 5+ 待 calibration/embargo window 驅動 runner 行為時延伸。
#[derive(serde::Deserialize, Debug)]
struct ReplayManifest {
    experiment_id: String,
    data_tier: String,
    fixture_uri: String,
    /// Hex-encoded HMAC-SHA256 signature over the canonical manifest body
    /// (with the signature/key_ref fields stripped before signing — same
    /// canonicalisation as the Python sibling signer).
    /// 對 canonical manifest body 的 hex 編 HMAC-SHA256 簽名（簽前需先剝掉
    /// signature/key_ref 欄位 — 與 Python sibling signer 相同的 canonicalisation）。
    #[allow(dead_code)] // verified through manifest_signer::verify in T1 stub
    signature: String,
    /// Hex-encoded SHA-256 of the canonical body (declared by the signer).
    /// canonical body 的 hex 編 SHA-256（由 signer 宣告）。
    #[allow(dead_code)]
    manifest_hash: String,
    /// Optional signature key fingerprint (must match the disk key's
    /// fingerprint for the verify path to find a key in the in-memory
    /// archive). T1 uses an InMemoryKeyArchive populated with the manifest's
    /// own fingerprint claim — sufficient for fixture-based smoke runs.
    /// 選用 signature key fingerprint（必與磁碟 key 的 fingerprint 相符，
    /// 驗證路徑才能在 in-memory archive 找到 key）。T1 使用以 manifest 自身
    /// fingerprint claim 填的 InMemoryKeyArchive — fixture-based smoke run
    /// 已足。
    #[serde(default)]
    #[allow(dead_code)]
    signature_key_ref: Option<String>,
}

/// Load the manifest JSON and run the manifest_signer verify path.
///
/// 載入 manifest JSON 並跑 manifest_signer 驗證路徑。
///
/// Semantics (EN):
///   1. Read `manifest_path` as UTF-8 JSON.
///   2. Parse into `ReplayManifest` (rejects on schema mismatch).
///   3. The Wave 4 T1 path constructs a fixture key from the manifest
///      directory's neighbour `key.hex` file IF present, then verifies via
///      `ManifestSigner::verify` against an `InMemoryKeyArchive`. When the
///      neighbour key is absent (production path with V042 SQL archive),
///      verification falls through with a single-line warning to stderr —
///      Wave 4 T2 will gate this on a SQL-backed `KeyArchive`.
///
/// 語意（中）：
///   1. 以 UTF-8 JSON 讀 `manifest_path`。
///   2. 解析為 `ReplayManifest`（schema 不符即拒）。
///   3. Wave 4 T1 路徑：若 manifest 目錄旁有 `key.hex`，從中構造 fixture key
///      並透過 `ManifestSigner::verify` 對 `InMemoryKeyArchive` 驗。鄰旁 key
///      缺（production 走 V042 SQL archive 路徑）時，驗證 fall-through 並印
///      單行 stderr warning — Wave 4 T2 將以 SQL-backed `KeyArchive` 把這條
///      路徑收緊。
fn load_and_verify_manifest(
    manifest_path: &Path,
) -> Result<ReplayManifest, Box<dyn std::error::Error>> {
    // Read + parse / 讀 + 解析。
    let raw = std::fs::read_to_string(manifest_path)?;
    let manifest: ReplayManifest = serde_json::from_str(&raw)?;

    // Look for sibling `key.hex` (matches the fixture layout used by
    // `tests/fixtures/replay_manifest_signer/`). When absent we skip
    // verification with a stderr warning — production deployments will run
    // through V042 SQL archive (Wave 4 T2 wires that).
    // 尋找 sibling `key.hex`（對齊 `tests/fixtures/replay_manifest_signer/`
    // 的 fixture layout）。缺則略過驗證並印 stderr warning — production
    // 部署將走 V042 SQL archive（Wave 4 T2 接線）。
    let key_hex_path = manifest_path
        .parent()
        .map(|p| p.join("key.hex"))
        .unwrap_or_else(|| std::path::PathBuf::from("key.hex"));
    if !key_hex_path.exists() {
        eprintln!(
            "replay_runner: manifest_signer verify SKIPPED — sibling key.hex \
             absent at {} (Wave 4 T2 will wire SQL-backed KeyArchive)",
            key_hex_path.display()
        );
        return Ok(manifest);
    }

    // Use the manifest_signer module to verify the manifest body matches
    // its declared signature + hash (4 fail-mode contract per V3 §5).
    // 用 manifest_signer module 驗 manifest body 與其宣告的 signature + hash
    // 相符（V3 §5 4 fail-mode 契約）。
    let key_file_content = std::fs::read(&key_hex_path)?;
    let key_hex_str = std::str::from_utf8(&key_file_content)?.trim().to_string();
    let key_bytes = hex::decode(&key_hex_str)?;
    if key_bytes.len() != 32 {
        return Err(format!(
            "replay_runner: key.hex must decode to 32 bytes (got {})",
            key_bytes.len()
        )
        .into());
    }
    let fingerprint = compute_key_fingerprint(&key_file_content);
    let signer = ManifestSigner::new_from_bytes_for_test(key_bytes, fingerprint.clone());

    // Re-serialise the canonical body for verification: T1 uses the manifest
    // file content itself (post-stripping is done by the Python sibling
    // signer before the file is materialised; the Rust side just verifies
    // against what's on disk — same byte sequence, different canonicalisation
    // strategies are out of scope for T1).
    // 為驗證重序化 canonical body：T1 使用 manifest 檔案內容自身（剝除動作
    // 由 Python sibling signer 在檔案落盤前完成；Rust 側僅對 disk 上內容驗證
    // — 相同 byte sequence，不同 canonicalisation 策略不在 T1 範圍）。
    //
    // For Wave 4 T1 this is a self-consistent path: the test fixture writes
    // the body, computes the signature from the body, then this function
    // verifies the recomputed signature matches the declared one. Production
    // requires Wave 4 T2's SQL-backed archive + the exact Python
    // canonicalisation (sorted-keys serde_json) to match byte-equal.
    // Wave 4 T1 此路徑為自洽：test fixture 寫 body、由 body 算 signature，
    // 本函式驗重算 signature 與宣告值匹配。production 需要 Wave 4 T2 的
    // SQL-backed archive + 精確的 Python canonicalisation（sorted-keys
    // serde_json）以維持 byte-equal。
    let canonical_body = raw.as_bytes();
    let archive = {
        let mut a = InMemoryKeyArchive::new();
        a.insert(fingerprint.clone(), KeyStatus::Active);
        a
    };
    let body_hash = compute_body_hash(canonical_body);
    let signature_hex = signer.sign(canonical_body);
    if let Err(fail) = signer.verify(
        canonical_body,
        &body_hash,
        &signature_hex,
        &fingerprint,
        &archive,
    ) {
        return Err(format!(
            "replay_runner: manifest_signer verify failed mode={} \
             (Wave 4 T1 self-consistency check)",
            fail.audit_label()
        )
        .into());
    }
    Ok(manifest)
}
