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
    canonical_body_for_signing, compute_body_hash, compute_key_fingerprint, InMemoryKeyArchive,
    KeyStatus, ManifestSigner,
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

    // Step 2b: REF-20 Sprint 1 Track A — self-verify embedded run_id matches
    // output_dir basename (PA push back #2 invariant). When the manifest does
    // not declare a run_id (legacy fixtures pre-Track A) we skip the assertion;
    // when it does declare one and basename mismatches, we abort fail-closed.
    // The basename is taken from `args.output_dir` because Python writes
    // manifest fixture under `OPENCLAW_DATA_DIR/replay_artifacts/<run_id>/`
    // (or `/tmp/replay_artifacts_test_only/<run_id>/` on Mac); `<run_id>` is
    // the V045 PK Python embeds in `manifest.run_id`. If they diverge,
    // V045 row would track wrong artifact directory → audit chain corruption.
    //
    // Step 2b：REF-20 Sprint 1 Track A — 自驗 embedded run_id 與 output_dir
    // basename 一致（PA push back #2 不變量）。manifest 未宣告 run_id（Track A
    // 之前的舊 fixture）時 skip 不變量；宣告但 basename 不符即 fail-closed。
    // basename 取自 `args.output_dir`，因 Python 寫 manifest fixture 至
    // `OPENCLAW_DATA_DIR/replay_artifacts/<run_id>/`（Mac 為
    // `/tmp/replay_artifacts_test_only/<run_id>/`）；`<run_id>` 即 Python 嵌入
    // `manifest.run_id` 的 V045 PK。兩者漂移 → V045 row 對到錯 artifact 目錄 →
    // audit chain 腐化。
    if let Some(declared_run_id) = manifest.run_id.as_deref() {
        let basename = args
            .output_dir
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("");
        if basename != declared_run_id {
            return Err(format!(
                "replay_runner: run_id self-verify failed (PA push back #2): \
                 manifest.run_id='{}' but output_dir basename='{}' \
                 (path={})",
                declared_run_id,
                basename,
                args.output_dir.display(),
            )
            .into());
        }
    }

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

/// Minimal manifest body shape consumed by `replay_runner` (Wave 4 T1 +
/// REF-20 Sprint 1 Track B verify path tightening).
///
/// `replay_runner` 消費的最小 manifest body 形狀（Wave 4 T1 + REF-20
/// Sprint 1 Track B verify 路徑收緊）。
///
/// Wave 4 T1 deliberately ships only the fields the runner actually reads
/// (`experiment_id`, `data_tier`, `fixture_uri`, `signature`,
/// `manifest_hash`, optional `signature_key_ref`, optional `run_id`). Wave 5+
/// extends with calibration/embargo windows once those fields drive runner
/// behaviour.
///
/// Wave 4 T1 刻意僅出貨 runner 實際讀的欄位（`experiment_id`、`data_tier`、
/// `fixture_uri`、`signature`、`manifest_hash`、選用 `signature_key_ref`、
/// 選用 `run_id`）。Wave 5+ 待 calibration/embargo window 驅動 runner 行為
/// 時延伸。
///
/// REF-20 Sprint 1 Track B 變更（移除 `#[allow(dead_code)]`）：
/// `signature` 與 `manifest_hash` 從「parse 但 unused」改成 verify path 的
/// expected 輸入；不再 self-sign 重簽然後對比（那是 tautology fail-open）。
/// REF-20 Sprint 1 Track B change (remove `#[allow(dead_code)]`):
/// `signature` and `manifest_hash` upgraded from "parsed but unused" to
/// verify-path expected inputs; no longer self-sign-then-compare (that was
/// a tautology fail-open).
#[derive(serde::Deserialize, Debug)]
struct ReplayManifest {
    experiment_id: String,
    data_tier: String,
    fixture_uri: String,
    /// Hex-encoded HMAC-SHA256 signature over the canonical manifest body
    /// (the body with envelope fields `signature`, `manifest_hash`,
    /// `signature_key_ref` stripped, then re-serialized via
    /// `serde_json::to_vec` — same canonicalisation as the Python sibling
    /// signer's `json.dumps(sort_keys=True, separators=(',', ':'),
    /// ensure_ascii=False)`).
    ///
    /// 對 canonical manifest body 的 hex HMAC-SHA256 簽名（body = 整個
    /// manifest 剝除 envelope 欄位 `signature` / `manifest_hash` /
    /// `signature_key_ref` 後，以 `serde_json::to_vec` 重序列化 — 與 Python
    /// sibling signer 的 `json.dumps(sort_keys=True, separators=(',', ':'),
    /// ensure_ascii=False)` 同 canonicalisation）。
    ///
    /// REF-20 Sprint 1 Track B：本欄位從 `#[allow(dead_code)]` placeholder
    /// 升級為 verify path 的 expected signature — 不再對 disk content 重簽
    /// 然後 verify（那是 tautology）。攻擊面：拿到 signing key 即可造任意
    /// manifest；唯一防線是 fail-closed verify。
    pub signature: String,
    /// Hex-encoded SHA-256 of the canonical body (declared by the signer).
    /// Verified by computing `compute_body_hash(canonical_body_for_signing(
    /// disk_bytes))` and byte-comparing against this declared value.
    ///
    /// canonical body 的 hex SHA-256（由 signer 宣告）。
    /// 驗證方式：對磁碟 bytes 跑 `canonical_body_for_signing` → `compute_body_hash`，
    /// 重算結果與此宣告值 byte 比對。
    ///
    /// REF-20 Sprint 1 Track B：本欄位從 `#[allow(dead_code)]` 升級為 verify
    /// path 的 expected hash — 確保 disk content 與簽名時的 body 一致（防
    /// post-sign tampering of body fields outside `signature`/`manifest_hash`）。
    pub manifest_hash: String,
    /// Optional signature key fingerprint (must match the disk key's
    /// fingerprint for the verify path to find a key in the in-memory
    /// archive). When absent the verify path falls back to the disk-key's
    /// own fingerprint (V042 SQL archive landing in Wave 6 will tighten this).
    ///
    /// 選用 signature key fingerprint（必與磁碟 key 的 fingerprint 相符，
    /// verify 路徑才能在 archive 找到 key）。缺時 fallback 到磁碟 key 自算
    /// fingerprint（V042 SQL archive 於 Wave 6 land 後會收緊此路徑）。
    #[serde(default)]
    pub signature_key_ref: Option<String>,
    /// Optional run id (Track A `_write_manifest_fixture` writes this from
    /// the V045 PK so the Rust binary can self-verify
    /// `manifest.run_id == output_dir.basename()` per PA Push Back #2).
    ///
    /// `#[serde(default)]` for backward-compatibility with existing fixtures
    /// that pre-date Track A (e.g. `tests/fixtures/replay_manifest_signer/`
    /// stripped-body fixtures).
    ///
    /// 選用 run id（Track A `_write_manifest_fixture` 從 V045 PK 寫入，使
    /// Rust binary 可自驗 `manifest.run_id == output_dir.basename()`，依
    /// PA Push Back #2）。
    ///
    /// `#[serde(default)]` 為向後相容既有 fixture（如
    /// `tests/fixtures/replay_manifest_signer/` stripped-body fixture）。
    #[serde(default)]
    pub run_id: Option<String>,
}

/// Load the manifest JSON and run the manifest_signer verify path.
///
/// 載入 manifest JSON 並跑 manifest_signer 驗證路徑。
///
/// Semantics (EN, REF-20 Sprint 1 Track B FAIL-CLOSED rewrite):
///   1. Read `manifest_path` as UTF-8 JSON.
///   2. Parse into `ReplayManifest` (rejects on schema mismatch; rejects when
///      `signature` / `manifest_hash` envelope fields are absent — Wave 4 T1
///      placeholder behaviour was to skip verify here, which is the E3-P0-1
///      fail-open vulnerability this rewrite closes).
///   3. Locate sibling `key.hex` next to the manifest. If ABSENT → return
///      `Err("manifest_signer_key_missing: ...")`. Sprint 1 closes the
///      previous fail-open path that returned `Ok(manifest)` with a stderr
///      warning. V042 SQL-backed archive (Wave 6) will replace this sibling-
///      key fallback; until V042 lands, dev fixture + production deploy
///      operator MUST place a `key.hex` next to every signed manifest.
///   4. Verify via `ManifestSigner::verify`:
///      - Use `canonical_body_for_signing(disk_bytes)` to reproduce the
///        canonical signing payload (envelope fields stripped + sorted keys).
///      - Pass `manifest.signature` (from disk) as the `signature_hex`
///        argument — NOT a freshly-computed signature (the previous tautology
///        was: `let sig = signer.sign(body); signer.verify(body, hash, sig)`
///        which can never fail).
///      - Pass `manifest.manifest_hash` (from disk) as the
///        `manifest_declared_hash` argument.
///      - Resolve fingerprint: prefer `manifest.signature_key_ref` if present
///        (audit chain marker); else use disk-key's own fingerprint.
///   5. Verify path emits a typed `SignatureFailMode` on mismatch — convert
///      to a `Box<dyn Error>` with the fail-mode label so the binary exits
///      non-zero with audit-distinguishable stderr.
///
/// 語意（中，REF-20 Sprint 1 Track B FAIL-CLOSED 重寫）：
///   1. 以 UTF-8 JSON 讀 `manifest_path`。
///   2. parse 為 `ReplayManifest`（schema 不符即拒；缺 `signature` /
///      `manifest_hash` envelope 欄位即拒 — Wave 4 T1 placeholder 行為是
///      skip verify，這是本 rewrite 修的 E3-P0-1 fail-open）。
///   3. 找 sibling `key.hex`。缺即 `Err("manifest_signer_key_missing: ...")`。
///      Sprint 1 修掉舊有的「印 warning + return Ok」fail-open 路徑。V042
///      SQL-backed archive（Wave 6）將替代 sibling-key fallback；V042 land 前
///      dev fixture 與 production deploy operator 必須在每個 signed manifest
///      旁放一個 `key.hex`。
///   4. 透過 `ManifestSigner::verify` 驗證：
///      - 用 `canonical_body_for_signing(disk_bytes)` 重 canonicalize 出
///        簽名 payload（envelope 剝除 + sorted keys）。
///      - `manifest.signature`（from disk）為 `signature_hex` 參數 — 非新
///        重簽（舊 tautology：`let sig = signer.sign(body); signer.verify(
///        body, hash, sig)` 永不會 fail）。
///      - `manifest.manifest_hash`（from disk）為 `manifest_declared_hash`
///        參數。
///      - fingerprint 解析：若 `manifest.signature_key_ref` 存在優先（audit
///        chain marker）；否則用磁碟 key 自算 fingerprint。
///   5. verify 失敗回 typed `SignatureFailMode` → 轉成 `Box<dyn Error>` 帶
///      fail-mode label，使 binary 非 0 結束並印 audit-distinguishable stderr。
///
/// # E3-P0-1 root-cause closed by Sprint 1 Track B
/// E3-P0-1 by Sprint 1 Track B 修補的根因
///
/// Pre-Sprint-1 path (DELETED):
///   ```text
///   let signature_hex = signer.sign(canonical_body);  // self-sign
///   signer.verify(canonical_body, &body_hash, &signature_hex, ...) // verify-self
///   ```
/// → recomputed sig with same key + same canonical body == declared sig
///   trivially. Verify always Ok. Attacker with the signing key (or in any
///   directory without a sibling key.hex) could mint manifests that pass.
///
/// Sprint 1 Track B path:
///   - canonical body = strip envelope fields + sorted-keys serde_json.
///   - signer.verify(canon_body, manifest.manifest_hash, manifest.signature,
///                   fingerprint, archive)
///   - sig comes from disk file (was put there by Python sibling signer);
///     hash comes from disk file; canonical body comes from disk file;
///     verify recomputes HMAC over canonical body and compares to disk sig.
///   - Tautology closed.
fn load_and_verify_manifest(
    manifest_path: &Path,
) -> Result<ReplayManifest, Box<dyn std::error::Error>> {
    // Read + parse / 讀 + 解析。
    let raw = std::fs::read_to_string(manifest_path)?;
    let manifest: ReplayManifest = serde_json::from_str(&raw)?;

    // Look for sibling `key.hex` (matches the fixture layout used by
    // `tests/fixtures/replay_manifest_signer/`). REF-20 Sprint 1 Track B:
    // ABSENT → hard error (was: stderr warning + Ok fall-through, which is
    // the E3-P0-1 fail-open vulnerability).
    //
    // 尋找 sibling `key.hex`（對齊 `tests/fixtures/replay_manifest_signer/`
    // 的 fixture layout）。REF-20 Sprint 1 Track B：缺即 hard error
    // （舊路徑：印 stderr warning + Ok fall-through，是 E3-P0-1 fail-open）。
    //
    // V042 SQL-backed archive notes:
    // - V042 reserved at workplan level but unscheduled until Wave 6+.
    // - Until V042 lands, sibling key.hex fallback is the ONLY production
    //   key source; operator MUST place a key.hex next to every manifest
    //   (PA Push Back #3 surfaces this as an operator runbook contract +
    //   adds the `check_replay_manifest_key_presence()` healthcheck).
    let key_hex_path = manifest_path
        .parent()
        .map(|p| p.join("key.hex"))
        .unwrap_or_else(|| std::path::PathBuf::from("key.hex"));
    if !key_hex_path.exists() {
        return Err(format!(
            "manifest_signer_key_missing: sibling key.hex absent at {}; \
             production path requires either (a) operator-deployed sibling \
             key.hex per V042 archive deploy runbook (Wave 6+) or (b) V042 \
             SQL-backed KeyArchive (not yet landed) — fail-closed",
            key_hex_path.display()
        )
        .into());
    }

    // Read key file / 讀 key 檔案。
    let key_file_content = std::fs::read(&key_hex_path)?;
    let key_hex_str = std::str::from_utf8(&key_file_content)?.trim().to_string();
    let key_bytes = hex::decode(&key_hex_str).map_err(|e| {
        format!(
            "manifest_signer_key_invalid_hex: key.hex at {} not valid hex: {}",
            key_hex_path.display(),
            e
        )
    })?;
    if key_bytes.len() != 32 {
        return Err(format!(
            "manifest_signer_key_invalid_length: key.hex must decode to \
             32 bytes (got {} bytes at {})",
            key_bytes.len(),
            key_hex_path.display()
        )
        .into());
    }
    let disk_fingerprint = compute_key_fingerprint(&key_file_content);
    let signer = ManifestSigner::new_from_bytes_for_test(key_bytes, disk_fingerprint.clone());

    // Resolve verify fingerprint:
    //   - If manifest declares `signature_key_ref` → use that (audit chain
    //     marker; production V042 archive lookup keys on this).
    //   - Else fall back to disk-key's own fingerprint (Track A
    //     `_write_manifest_fixture` may omit `signature_key_ref` in dev mode).
    //
    // 解析 verify fingerprint：
    //   - manifest 宣告 `signature_key_ref` → 用宣告值（audit chain；prod V042
    //     archive 以此 key 查 status）。
    //   - 否則 fallback 為磁碟 key 自算 fingerprint（Track A
    //     `_write_manifest_fixture` 在 dev 模式可省 `signature_key_ref`）。
    let verify_fingerprint = manifest
        .signature_key_ref
        .clone()
        .unwrap_or_else(|| disk_fingerprint.clone());

    // 不變量 / Invariant: archive 必含 verify_fingerprint with status=Active —
    //   Wave 4 T1 用 in-memory archive 自填當前 disk-key fingerprint 即可
    //   （Wave 6 V042 SQL archive 落地後改用真實 status）。
    //   若 manifest.signature_key_ref 與磁碟 fingerprint 不一致 → archive
    //   lookup miss → KeyMissing fail-mode（保留 audit-distinguish）。
    let archive = {
        let mut a = InMemoryKeyArchive::new();
        a.insert(disk_fingerprint.clone(), KeyStatus::Active);
        a
    };

    // REF-20 Sprint 1 Track B canonical body path:
    //   strip envelope fields (signature / manifest_hash / signature_key_ref)
    //   + sorted-keys serde_json::to_vec → byte-equal Python sibling signer.
    //
    // canonicalize 路徑（REF-20 Sprint 1 Track B）：
    //   strip envelope 欄位 + sorted-keys serde_json::to_vec → 與 Python
    //   sibling signer byte-equal。
    let canonical_body =
        canonical_body_for_signing(raw.as_bytes()).map_err(|e| {
            format!(
                "manifest_signer_canonicalize_failed: {} (manifest body must \
                 be top-level JSON object per V3 §5)",
                e
            )
        })?;

    // Sanity gate / 完整性 gate: declared manifest_hash must match the
    // actual hash of the canonical body. This catches body-tampering after
    // sign even when the (still-correct) signature happens to verify against
    // a partially-tampered body — `manifest_hash` is the redundant integrity
    // anchor V3 §5 requires (mode 2/4 = `manifest_hash_mismatch`).
    //
    // Note: this gate fires BEFORE `signer.verify(...)` so the error label
    // reflects the actual semantic failure (declared hash drift) rather than
    // SignatureMismatch (which would surface only because the recomputed
    // sig over the tampered body differs from the disk-stored sig).
    let actual_body_hash = compute_body_hash(&canonical_body);
    if actual_body_hash != manifest.manifest_hash {
        return Err(format!(
            "manifest_signer_verify_failed: mode={} declared={} actual={}",
            "manifest_hash_mismatch", manifest.manifest_hash, actual_body_hash
        )
        .into());
    }

    // Final verify: HMAC sig + body hash + archive gates (per V3 §5 verify
    // order). Caller-supplied disk values are the expected inputs; this is
    // the key inversion vs the pre-Sprint-1 self-sign tautology.
    //
    // 最終 verify：HMAC sig + body hash + archive gate（V3 §5 順序）。
    // caller 提供的磁碟值為 expected 輸入；這是相對 Sprint 1 前 self-sign
    // tautology 的關鍵反轉。
    if let Err(fail) = signer.verify(
        &canonical_body,
        &manifest.manifest_hash,
        &manifest.signature,
        &verify_fingerprint,
        &archive,
    ) {
        return Err(format!(
            "manifest_signer_verify_failed: mode={} fingerprint={} \
             manifest={}",
            fail.audit_label(),
            verify_fingerprint,
            manifest_path.display()
        )
        .into());
    }
    Ok(manifest)
}

// ---------------------------------------------------------------------------
// REF-20 Sprint 1 Track B — fail-closed manifest verify tests
// REF-20 Sprint 1 Track B — fail-closed manifest 驗證測試
//
// Five mandatory tests bind to PA Sprint 1 dispatch §4 (改點 #4):
//   (a) tautology defense: post-sign body tampering surfaces (was: silently
//       passed pre-Sprint-1).
//   (b) key.hex absent → hard error (was: stderr warning + Ok fall-through).
//   (c) signature tampered (1 byte) → SignatureMismatch surfaced.
//   (d) declared manifest_hash drifted (1 byte) → manifest_hash_mismatch.
//   (happy) full single-file manifest with correct sig + hash → Ok.
//   (xlang) canonical_body_for_signing byte-equal to Python sibling.
//
// PA dispatch §4 改點 #4 4 fail-mode + 1 happy + 1 xlang sanity 共 6 test。
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use tempfile::TempDir;

    /// 64 hex char (32 bytes) deterministic fixture key — checked into
    /// tests directory; NEVER used in production.
    /// 64 hex char (32 bytes) 確定性 fixture key — 僅 test 用。
    const FIXTURE_KEY_HEX: &str =
        "00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff";

    /// 寫 sibling key.hex 檔案到 tmp dir，回 (key file path, fingerprint)。
    /// helper script `printf '%s\n' "$KEY_HEX" > key.hex` 等價，含 trailing
    /// newline，鏡像 production deploy 檔案格式。
    ///
    /// Write a sibling key.hex file into tmp dir, return (path, fingerprint).
    /// Equivalent to helper script `printf '%s\n' "$KEY_HEX" > key.hex`
    /// (with trailing newline, mirrors production file format).
    fn write_fixture_key(dir: &Path) -> (std::path::PathBuf, String) {
        let path = dir.join("key.hex");
        let content = format!("{}\n", FIXTURE_KEY_HEX);
        let mut f = std::fs::File::create(&path).expect("create key.hex");
        f.write_all(content.as_bytes()).expect("write key.hex");
        let fingerprint = compute_key_fingerprint(content.as_bytes());
        (path, fingerprint)
    }

    /// 用 fixture key 簽指定 body，產出對應 (sig_hex, hash_hex)。
    /// Sign the given body with fixture key, return (sig_hex, hash_hex).
    fn sign_body(body: &[u8], fingerprint: &str) -> (String, String) {
        let key_bytes = hex::decode(FIXTURE_KEY_HEX).unwrap();
        let signer =
            ManifestSigner::new_from_bytes_for_test(key_bytes, fingerprint.to_string());
        let sig = signer.sign(body);
        let hash = compute_body_hash(body);
        (sig, hash)
    }

    /// 寫一個含 sig + hash 的單檔 manifest 到 tmp dir，回 manifest 檔路徑。
    /// 模擬 Track A `_write_manifest_fixture(...)` 寫法。
    ///
    /// Write a single-file manifest containing sig + hash to tmp dir, return
    /// the path. Mimics Track A `_write_manifest_fixture(...)`.
    fn write_full_manifest(
        dir: &Path,
        body_fields: &[(&str, serde_json::Value)],
        fingerprint: &str,
        run_id: Option<&str>,
    ) -> std::path::PathBuf {
        // 1. 組 stripped body（無 sig/hash）。
        let mut body = serde_json::Map::new();
        for (k, v) in body_fields {
            body.insert((*k).to_string(), v.clone());
        }
        if let Some(rid) = run_id {
            body.insert("run_id".to_string(), serde_json::Value::String(rid.to_string()));
        }
        // 2. canonical body bytes for signing (sorted-keys + compact)。
        let canon =
            serde_json::to_vec(&serde_json::Value::Object(body.clone())).unwrap();
        // 3. 算 sig + hash。
        let (sig, hash) = sign_body(&canon, fingerprint);
        // 4. 把 sig + hash + signature_key_ref envelope 加進 body 寫成完整 manifest。
        body.insert("manifest_hash".to_string(), serde_json::Value::String(hash));
        body.insert("signature".to_string(), serde_json::Value::String(sig));
        body.insert(
            "signature_key_ref".to_string(),
            serde_json::Value::String(fingerprint.to_string()),
        );
        let full = serde_json::to_vec_pretty(&serde_json::Value::Object(body)).unwrap();
        let path = dir.join("manifest.json");
        std::fs::write(&path, full).expect("write manifest.json");
        path
    }

    /// Happy path: 寫合法 manifest + key.hex，verify 成功。
    /// Happy path: write valid manifest + key.hex, verify succeeds.
    #[test]
    fn happy_path_full_manifest_verifies() {
        let tmp = TempDir::new().unwrap();
        let (_key_path, fingerprint) = write_fixture_key(tmp.path());
        let manifest_path = write_full_manifest(
            tmp.path(),
            &[
                ("experiment_id", serde_json::json!("exp_happy")),
                ("data_tier", serde_json::json!("S2_paper_full_truth")),
                ("fixture_uri", serde_json::json!("fixtures/happy/")),
                ("manifest_version", serde_json::json!(1)),
            ],
            &fingerprint,
            Some("run_happy_001"),
        );

        let result = load_and_verify_manifest(&manifest_path);
        assert!(
            result.is_ok(),
            "happy path must verify, got error: {:?}",
            result.err().map(|e| e.to_string())
        );
        let manifest = result.unwrap();
        assert_eq!(manifest.experiment_id, "exp_happy");
        assert_eq!(manifest.run_id.as_deref(), Some("run_happy_001"));
    }

    /// Fail mode (a) — tautology defense: post-sign body tampering must
    /// surface as a verify error. Pre-Sprint-1 path (`let sig = signer.sign(
    /// body); signer.verify(body, sig, ...)`) would silently pass because
    /// the recomputed sig always matches itself.
    ///
    /// Fail mode (a) — tautology defense：post-sign body tampering 必須
    /// surface 為 verify 錯誤。Sprint-1 前的路徑（`let sig = signer.sign(
    /// body); signer.verify(body, sig, ...)`）會 silently pass，因為重簽
    /// 結果永遠等於自己。
    #[test]
    fn fail_mode_a_tautology_defense_body_drift() {
        let tmp = TempDir::new().unwrap();
        let (_key_path, fingerprint) = write_fixture_key(tmp.path());
        let manifest_path = write_full_manifest(
            tmp.path(),
            &[
                ("experiment_id", serde_json::json!("exp_taut_orig")),
                ("data_tier", serde_json::json!("S2")),
                ("fixture_uri", serde_json::json!("fixtures/x/")),
                ("manifest_version", serde_json::json!(1)),
            ],
            &fingerprint,
            None,
        );

        // 手動把 body 內 fixture_uri 改一字（不更 sig/hash），模擬 body
        // post-sign tampering 攻擊。
        // Mutate fixture_uri without updating sig/hash, simulating post-sign
        // body tampering.
        let raw = std::fs::read_to_string(&manifest_path).unwrap();
        let tampered =
            raw.replace("\"fixtures/x/\"", "\"fixtures/ATTACKER_PATH/\"");
        std::fs::write(&manifest_path, tampered).unwrap();

        let err = load_and_verify_manifest(&manifest_path)
            .err()
            .map(|e| e.to_string())
            .unwrap_or_default();
        assert!(
            err.contains("manifest_signer_verify_failed"),
            "expected verify_failed, got: {}",
            err
        );
        // hash gate fires first when body bytes change → label is
        // manifest_hash_mismatch (the redundant integrity anchor catches it
        // before signer.verify gets a chance to surface signature_mismatch).
        // body 改動 → canonical body hash drift → hash gate 先抓到（manifest_hash
        // 是冗餘完整性錨，比 signer.verify 更早 surface 錯誤）。
        assert!(
            err.contains("manifest_hash_mismatch"),
            "expected manifest_hash_mismatch (hash gate fires first), got: {}",
            err
        );
    }

    /// Fail mode (b) — sibling key.hex absent → hard error.
    /// Pre-Sprint-1 path returned `Ok(manifest)` with stderr warning (E3-P0-1
    /// fail-open). Sprint 1 changes this to fail-closed.
    ///
    /// Fail mode (b) — sibling key.hex 缺 → hard error。
    /// Pre-Sprint-1 路徑回 `Ok(manifest)` 並印 stderr warning（E3-P0-1
    /// fail-open）。Sprint 1 改為 fail-closed。
    #[test]
    fn fail_mode_b_key_hex_missing_hard_errors() {
        let tmp = TempDir::new().unwrap();
        // 故意不寫 key.hex / Deliberately do not write key.hex.
        // 用一個假 fingerprint，因為 key.hex 不存在 verify path 不會走到 archive。
        // Use a dummy fingerprint; key.hex absent path returns Err before archive.
        let fingerprint = "deadbeefdeadbeef".to_string();
        let manifest_path = write_full_manifest(
            tmp.path(),
            &[
                ("experiment_id", serde_json::json!("exp_no_key")),
                ("data_tier", serde_json::json!("S2")),
                ("fixture_uri", serde_json::json!("fixtures/")),
                ("manifest_version", serde_json::json!(1)),
            ],
            &fingerprint,
            None,
        );

        let err = load_and_verify_manifest(&manifest_path)
            .err()
            .map(|e| e.to_string())
            .unwrap_or_default();
        assert!(
            err.contains("manifest_signer_key_missing"),
            "expected manifest_signer_key_missing fail-closed, got: {}",
            err
        );
    }

    /// Fail mode (c) — signature tampered (1 byte) → SignatureMismatch.
    /// 簽名第 1 byte 改寫，body + hash 仍對 → 必走 signature_mismatch 而非
    /// hash gate（hash gate 對 disk 內容算 ok）。
    ///
    /// Fail mode (c) — signature tampered (1 byte) → SignatureMismatch.
    /// Mutate sig first byte; body + declared_hash still consistent → must
    /// fall through to signature_mismatch (not hash gate).
    #[test]
    fn fail_mode_c_signature_tampered_signature_mismatch() {
        let tmp = TempDir::new().unwrap();
        let (_key_path, fingerprint) = write_fixture_key(tmp.path());
        let manifest_path = write_full_manifest(
            tmp.path(),
            &[
                ("experiment_id", serde_json::json!("exp_sig_tamper")),
                ("data_tier", serde_json::json!("S2")),
                ("fixture_uri", serde_json::json!("fixtures/")),
                ("manifest_version", serde_json::json!(1)),
            ],
            &fingerprint,
            None,
        );

        // Parse manifest, tamper signature 1 byte, write back.
        // 讀回 manifest，改 signature 第 1 byte，寫回。
        let raw = std::fs::read_to_string(&manifest_path).unwrap();
        let mut value: serde_json::Value = serde_json::from_str(&raw).unwrap();
        let sig = value["signature"].as_str().unwrap().to_string();
        let mut tampered = sig.into_bytes();
        tampered[0] = if tampered[0] == b'a' { b'b' } else { b'a' };
        let tampered_sig = String::from_utf8(tampered).unwrap();
        value["signature"] = serde_json::Value::String(tampered_sig);
        let new_raw = serde_json::to_vec_pretty(&value).unwrap();
        std::fs::write(&manifest_path, new_raw).unwrap();

        let err = load_and_verify_manifest(&manifest_path)
            .err()
            .map(|e| e.to_string())
            .unwrap_or_default();
        assert!(
            err.contains("manifest_signer_verify_failed"),
            "expected verify_failed, got: {}",
            err
        );
        assert!(
            err.contains("signature_mismatch"),
            "expected signature_mismatch (hash gate must NOT fire when only \
             sig is tampered), got: {}",
            err
        );
    }

    /// Fail mode (d) — declared manifest_hash tampered (1 byte) → returns
    /// manifest_hash_mismatch error label (sanity gate fires before
    /// signer.verify).
    ///
    /// Fail mode (d) — declared manifest_hash 改 1 byte → manifest_hash_mismatch
    /// label 直接由 sanity gate（在 signer.verify 之前）回。
    #[test]
    fn fail_mode_d_declared_hash_tampered_manifest_hash_mismatch() {
        let tmp = TempDir::new().unwrap();
        let (_key_path, fingerprint) = write_fixture_key(tmp.path());
        let manifest_path = write_full_manifest(
            tmp.path(),
            &[
                ("experiment_id", serde_json::json!("exp_hash_tamper")),
                ("data_tier", serde_json::json!("S2")),
                ("fixture_uri", serde_json::json!("fixtures/")),
                ("manifest_version", serde_json::json!(1)),
            ],
            &fingerprint,
            None,
        );

        // Parse manifest, tamper manifest_hash 1 byte, write back.
        // 讀回 manifest，改 manifest_hash 第 1 byte，寫回。
        let raw = std::fs::read_to_string(&manifest_path).unwrap();
        let mut value: serde_json::Value = serde_json::from_str(&raw).unwrap();
        let hash = value["manifest_hash"].as_str().unwrap().to_string();
        let mut tampered = hash.into_bytes();
        tampered[0] = if tampered[0] == b'a' { b'b' } else { b'a' };
        let tampered_hash = String::from_utf8(tampered).unwrap();
        value["manifest_hash"] = serde_json::Value::String(tampered_hash);
        let new_raw = serde_json::to_vec_pretty(&value).unwrap();
        std::fs::write(&manifest_path, new_raw).unwrap();

        let err = load_and_verify_manifest(&manifest_path)
            .err()
            .map(|e| e.to_string())
            .unwrap_or_default();
        assert!(
            err.contains("manifest_hash_mismatch"),
            "expected manifest_hash_mismatch (sanity gate fires before \
             signer.verify), got: {}",
            err
        );
    }

    /// Cross-language byte-equal sanity:
    /// canonical_body_for_signing(disk single-file manifest) reproduces
    /// the exact bytes that Python sibling signer signed (sorted-keys +
    /// compact + envelope stripped). This is THE invariant Track A's Python
    /// `_write_manifest_fixture` MUST honor for verify to succeed.
    ///
    /// 跨語言 byte-equal 健全性：對 disk 單檔 manifest 跑
    /// canonical_body_for_signing，重現 Python sibling signer 簽時的精確
    /// bytes（sorted-keys + compact + envelope stripped）。這是 Track A
    /// `_write_manifest_fixture` 必對齊以使 verify 成功的核心不變量。
    #[test]
    fn canonical_body_byte_equal_to_python_sibling() {
        // 這個 byte sequence 必對應 Python:
        //   json.dumps(stripped, sort_keys=True, separators=(',', ':'),
        //              ensure_ascii=False).encode('utf-8')
        // 對 stripped = {"data_tier":"S2","experiment_id":"x","manifest_version":1}.
        let disk_full = br#"{
            "experiment_id": "x",
            "data_tier": "S2",
            "manifest_version": 1,
            "signature": "deadbeef",
            "manifest_hash": "cafebabe",
            "signature_key_ref": "fp_x"
        }"#;
        let canon = canonical_body_for_signing(disk_full).unwrap();
        let expected = br#"{"data_tier":"S2","experiment_id":"x","manifest_version":1}"#;
        assert_eq!(
            canon, expected,
            "canonical body drift: got {} expected {}",
            std::str::from_utf8(&canon).unwrap(),
            std::str::from_utf8(expected).unwrap()
        );
    }
}
