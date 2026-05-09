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

#[path = "replay_runner/calibration.rs"]
mod calibration;
#[path = "replay_runner/config.rs"]
mod config;
#[path = "replay_runner/manifest.rs"]
mod manifest;
#[cfg(test)]
#[path = "replay_runner/manifest_tests.rs"]
mod manifest_tests;

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

use openclaw_core::guardian::GuardianConfig;
use openclaw_engine::config::RiskConfig;
use openclaw_engine::ml::kelly_sizer::KellyConfig;
use openclaw_engine::replay::cli;
use openclaw_engine::replay::fixture_loader::{self, FixtureSource};
use openclaw_engine::replay::forbidden_guard;
use openclaw_engine::replay::mac_policy_guard;
use openclaw_engine::replay::profile::ReplayProfile;
use openclaw_engine::replay::report_writer;
use openclaw_engine::replay::risk_adapter::{ReplayPaperSnapshot, ReplayRiskAdapter};
use openclaw_engine::replay::runner::{self, ReplayResult};
use openclaw_engine::replay::scanner_timeline::ReplayScannerTimeline;
use openclaw_engine::replay::strategy_adapter::ReplayStrategyAdapter;
use openclaw_engine::strategies::{Strategy, StrategyFactory, StrategyParamsConfig};

use calibration::{latency_ms_from_manifest, maker_fill_cap_from_manifest};
use config::{edge_estimates_from_manifest, scanner_config_from_manifest};
use manifest::load_and_verify_manifest;

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
    let scanner_timeline = if manifest.mode.as_deref() == Some("full_chain") {
        let scanner_config = scanner_config_from_manifest(manifest.scanner_config.as_ref())?;
        let edge_estimates = edge_estimates_from_manifest(manifest.edge_estimates.as_ref())?;
        Some(ReplayScannerTimeline::new(
            &events,
            &scanner_config,
            &edge_estimates,
        )?)
    } else {
        None
    };

    // Step 4: bootstrap the IsolatedPipeline + (optionally) wire adapters.
    // Step 4：建構 IsolatedPipeline + （選擇性）接 adapter。
    //
    // REF-20 Sprint B2 R5-T4 dispatch §11.1:
    //   When manifest declares `strategy` field, wire the real adapter path
    //   (StrategyFactory + ReplayStrategyAdapter + ReplayRiskAdapter +
    //   ReplayPaperSnapshot via IsolatedPipeline::with_adapter_pipeline).
    //   Otherwise fall back to synthetic walker (R5-T3 proof_1/4/5 baseline).
    //
    // Fail-loud: if `manifest.strategy = Some(name)` but factory cannot find
    // a matching strategy → exit non-zero with typed Box<dyn Error> so the
    // operator's CI shell branches via `$?` (CLAUDE.md §四 fail-closed).
    //
    // REF-20 Sprint B2 R5-T4 dispatch §11.1：
    //   manifest 宣告 `strategy` 時走真實 adapter 路徑（StrategyFactory +
    //   ReplayStrategyAdapter + ReplayRiskAdapter + ReplayPaperSnapshot 經
    //   IsolatedPipeline::with_adapter_pipeline 接入）。否則 fallback
    //   synthetic walker（R5-T3 proof_1/4/5 baseline）。
    //
    // Fail-loud：`manifest.strategy = Some(name)` 但 factory 找不到 → 非 0
    // 結束帶 typed Box<dyn Error>，operator CI shell 由 `$?` 分支
    // （CLAUDE.md §四 fail-closed）。
    let starting_balance = manifest
        .starting_balance
        .unwrap_or(runner::DEFAULT_STARTING_BALANCE);
    if !starting_balance.is_finite() || starting_balance <= 0.0 {
        return Err(Box::<dyn std::error::Error>::from(format!(
            "replay_runner: manifest.starting_balance={} invalid; must be finite and > 0",
            starting_balance
        )));
    }

    // Pull out a representative starting price from the first fixture event.
    // Used as the snapshot anchor so Gate 2.6 P1 cap has a real price; if the
    // first event is missing we cannot proceed (would silent-bypass Gate 2.6).
    //
    // 從首個 fixture event 取代表性起始價作為 snapshot 錨點，使 Gate 2.6
    // P1 cap 有真錨；首 event 缺即無法續（否則會 silent-bypass Gate 2.6）。
    let first_event_price = events.first().map(|e| e.close).ok_or_else(|| {
        Box::<dyn std::error::Error>::from(
            "replay_runner: manifest declared strategy but fixture has no \
             events to derive starting anchor price (R5-T4 invariant)",
        )
    });

    let mut pipeline = runner::build_isolated_pipeline(
        profile,
        manifest.experiment_id.clone(),
        tier_label,
        events,
    )?
    .with_starting_balance(starting_balance)?
    .with_execution_calibration(
        maker_fill_cap_from_manifest(manifest.execution_calibration.as_ref())?,
        latency_ms_from_manifest(manifest.execution_calibration.as_ref())?,
    );
    if let Some(timeline) = scanner_timeline {
        pipeline = pipeline.with_scanner_timeline(timeline);
    }
    if let Some(strategy_name) = manifest.strategy.as_deref() {
        // R5-T4 adapter path. Resolve a matching strategy from the factory.
        // `StrategyFactory::create_with_params(default)` returns 5 strategies
        // (one per registered impl); we pick by `Strategy::name()` match
        // against `manifest.strategy`. Sprint B2 pilot focuses grid_trading +
        // ma_crossover; the rest are still constructed but only the named
        // one is wrapped (zero strategy code change per E2 §6.2 isolation).
        //
        // R5-T4 adapter 路徑。從 factory 找對應策略。
        // `StrategyFactory::create_with_params(default)` 回 5 個策略
        // （各註冊 impl 各一）；以 `Strategy::name()` 對 `manifest.strategy`
        // 匹配。Sprint B2 pilot 聚焦 grid_trading + ma_crossover；其餘仍
        // 建構但僅對應名稱的那個被包裝（0 策略代碼變更，E2 §6.2 隔離）。
        let starting_price = first_event_price?;

        // ── REF-20 Sprint B2 R5-T4 round 2 — config blob deserialise ──
        // ── REF-20 Sprint B2 R5-T4 round 2 — 配置 blob 反序列化 ──
        //
        // When the manifest carries `strategy_params` / `risk_overrides`
        // (v0 register handler's `_replay_*` injection bridged to disk
        // fixture by Python `build_default_manifest_payload` later this
        // sprint), runner threads them through factory + adapter.
        // Otherwise R5-T4 round 1 default behaviour (StrategyParamsConfig
        // ::default + RiskConfig::default) is preserved.
        // Manifest 帶 blob 時接入 factory + adapter；無則退 R5-T4 round 1
        // 預設行為。
        //
        // Fail-loud: serde_json::from_value Err → typed Box<dyn Error>
        // with shape-mismatch reason; CI parses ``$?`` non-zero exit
        // (CLAUDE.md §四 fail-closed).
        let strategy_params_config: StrategyParamsConfig = match &manifest.strategy_params {
            Some(blob) => serde_json::from_value(blob.clone()).map_err(|e| {
                Box::<dyn std::error::Error>::from(format!(
                    "replay_runner: manifest.strategy_params shape \
                         mismatch (cannot deserialise into \
                         StrategyParamsConfig): {} (R5-T4 round 2 \
                         fail-closed; check fixture builder + register \
                         handler V049 _replay_strategy_params injection)",
                    e
                ))
            })?,
            None => StrategyParamsConfig::default(),
        };
        let risk_config: RiskConfig = match &manifest.risk_overrides {
            Some(blob) => {
                let cfg: RiskConfig = serde_json::from_value(blob.clone()).map_err(|e| {
                    Box::<dyn std::error::Error>::from(format!(
                        "replay_runner: manifest.risk_overrides shape \
                             mismatch (cannot deserialise into RiskConfig): \
                             {} (R5-T4 round 2 fail-closed; check fixture \
                             builder + register handler V049 \
                             _replay_risk_overrides injection)",
                        e
                    ))
                })?;
                // Cheap sanity: position_size_max_pct must be in (0, 100].
                // Catches obvious caller mistakes (e.g. negative / NaN) so
                // adapter doesn't proceed with poisoned config (Guardian
                // would reject downstream but loud-and-early surface beats
                // silent run that 100%-rejects intents).
                // 簡易完整性檢查：position_size_max_pct ∈ (0, 100]，
                // 防 caller 誤傳負/NaN，提早 fail-loud（否則 Guardian
                // 會在下游 100% reject）。
                let p = cfg.limits.position_size_max_pct;
                if !p.is_finite() || p <= 0.0 || p > 100.0 {
                    return Err(Box::<dyn std::error::Error>::from(format!(
                        "replay_runner: manifest.risk_overrides invariant \
                         violation: limits.position_size_max_pct = {p} not \
                         in (0, 100] (R5-T4 round 2 fail-closed)"
                    )));
                }
                cfg
            }
            None => RiskConfig::default(),
        };

        let pool: Vec<Box<dyn Strategy>> =
            StrategyFactory::create_with_params(&strategy_params_config);
        let chosen = pool
            .into_iter()
            .find(|s| s.name() == strategy_name)
            .ok_or_else(|| {
                Box::<dyn std::error::Error>::from(format!(
                    "replay_runner: manifest.strategy='{}' not in StrategyFactory \
                     registry (registered: grid_trading / ma_crossover / \
                     bb_breakout / bb_reversion / funding_arb)",
                    strategy_name,
                ))
            })?;

        let strategy_adapter = ReplayStrategyAdapter::new(chosen, profile).map_err(|e| {
            Box::<dyn std::error::Error>::from(format!(
                "replay_runner: ReplayStrategyAdapter::new failed: {:?}",
                e
            ))
        })?;
        // Sprint C R6-T3 — derive p1_risk_pct + KellyConfig from the
        // already-deserialised risk_config snapshot (replaces Sprint A
        // hardcoded 0.02 + `None::<KellyConfig>` baseline). Replay uses
        // SAME `compute_kelly_qty` formula + `KellyConfig` shape as live;
        // tier boundaries from `risk_config.kelly`, per-trade risk pct from
        // `risk_config.limits`. Composition at bin/ entry keeps the snapshot
        // explicit + auditable. SAFETY: 0 endpoint / IPC / lease — V3 §6.2
        // forbidden surface 0 觸碰。
        //
        // Sprint C R6-T3 — 從已反序列化的 risk_config 快照派生
        // p1_risk_pct + KellyConfig（取代 Sprint A 硬編 0.02 +
        // `None::<KellyConfig>` baseline）。Replay 用與 live 相同的
        // `compute_kelly_qty` 公式與 `KellyConfig` 形狀；分級邊界讀
        // `risk_config.kelly`，per-trade 風險百分比讀 `risk_config.limits`。
        // 於 bin/ entry 就地組合使 snapshot 顯式且可稽核。SAFETY：0
        // endpoint / IPC / lease — V3 §6.2 forbidden surface 0 觸碰。
        let p1_risk_pct = risk_config.limits.per_trade_risk_pct;
        let kelly_config = KellyConfig {
            young_threshold: risk_config.kelly.young_threshold,
            mature_threshold: risk_config.kelly.mature_threshold,
            ..KellyConfig::default()
        };
        let risk_adapter = ReplayRiskAdapter::new(
            profile,
            GuardianConfig::default(),
            risk_config.clone(),
            p1_risk_pct,
            Some(kelly_config),
        )
        .map_err(|e| {
            Box::<dyn std::error::Error>::from(format!(
                "replay_runner: ReplayRiskAdapter::new failed: {:?}",
                e
            ))
        })?;

        let snapshot = ReplayPaperSnapshot {
            balance: starting_balance,
            drawdown_pct: 0.0,
            positions: Vec::new(),
            latest_price: Some(starting_price),
            exposure_pct: 0.0,
            correlated_exposure_pct: 0.0,
            leverage: 0.0,
            daily_loss_pct: 0.0,
            trade_stats: None,
        };
        pipeline = pipeline
            .with_adapter_pipeline(strategy_adapter, risk_adapter, snapshot)
            .map_err(|e| {
                Box::<dyn std::error::Error>::from(format!(
                    "replay_runner: with_adapter_pipeline failed: {} \
                     (R5-T3 fail-loud snapshot rejected; check manifest \
                     starting_balance + first fixture event)",
                    e
                ))
            })?;
        // R6-T3 / REF-21 — wire fee/slippage context. account_manager=None
        // falls back to DEFAULT_*_FEE_RATE (byte-equal with live cold-boot path
        // before Bybit refresh). slippage_config = risk_config.slippage
        // (G7-07 hot-reloadable; default mirrors live SLIPPAGE_TIERS). The
        // third argument is only the cold-start fallback; adapter execution now
        // overwrites it per event from fixture turnover_24h or derived rolling
        // 24h turnover before each intent is filled.
        //
        // R6-T3 — 接入 fee/slippage context。account_manager=None 退回
        // DEFAULT_*_FEE_RATE（與 live 冷啟動路徑 byte-equal）。slippage_config
        // = risk_config.slippage（G7-07 可熱重載；預設鏡射 live SLIPPAGE_TIERS）。
        // 第三參數僅為冷啟動 fallback；adapter execute 會在每個 event 前用
        // fixture turnover_24h 或 rolling 24h turnover 覆寫。
        pipeline = pipeline.with_replay_fee_context(None, Some(risk_config.slippage.clone()), None);
        eprintln!(
            "replay_runner: adapter path engaged strategy={} \
             starting_balance={} starting_price={} \
             p1_risk_pct={} kelly_young={} kelly_mature={} \
             slippage_default_bps={} \
             strategy_params_supplied={} risk_overrides_supplied={}",
            strategy_name,
            starting_balance,
            starting_price,
            p1_risk_pct,
            risk_config.kelly.young_threshold,
            risk_config.kelly.mature_threshold,
            risk_config.slippage.default_rate * 10_000.0,
            manifest.strategy_params.is_some(),
            manifest.risk_overrides.is_some(),
        );
    } else {
        // Drop the unused first_event_price (no error surface — synthetic
        // walker path tolerates empty fixtures via AbortedFixtureExhausted).
        // 釋放 first_event_price（無錯誤表面 — synthetic walker 容忍空
        // fixture，由 AbortedFixtureExhausted 處理）。
        let _ = first_event_price;
        eprintln!(
            "replay_runner: synthetic walker path (manifest.strategy absent; \
             R5-T3 e2e proof_1/4/5 baseline)"
        );
    }
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
