//! G1-06 follow-up — Live `paper_state.balance` sync verification end-to-end.
//! G1-06 後續：Live `paper_state.balance` 同步路徑端到端驗證。
//!
//! MODULE_NOTE (EN): G1-06 wires `RiskAction::HaltSession(SESSION DRAWDOWN: …)`
//!   → `should_revoke()` → `revoke_live_authorization()` so a Live drawdown
//!   halt also deletes `authorization.json`. The decision math reads
//!   `paper_state.drawdown_pct() = (peak − balance) / peak * 100`. The whole
//!   guarantee depends on `paper_state.balance` being kept in sync with the
//!   real Bybit equity on Live — otherwise drawdown is permanently 0 and the
//!   revoke path never fires.
//!
//!   This integration test pins down the contract observed in the production
//!   wiring (sub-agent verified Case A on 2026-04-24):
//!
//!     1. `startup/mod.rs:680` REST `refresh_balance` (3 retries, hard-fail
//!        no-fallback) seeds `bybit_balance` Arc and aborts the pipeline if
//!        the Bybit wallet call never succeeds — Live can never silently
//!        boot on a hard-coded 10000.
//!     2. `startup/mod.rs:778` spawns a 5-minute REST refresh loop writing
//!        the same Arc, defending against a silent WS wallet topic.
//!     3. `event_consumer/loop_handlers.rs:768-786` reads the Arc on every
//!        tick and (a) calls `paper_state.set_bybit_sync_balance(bal)` and
//!        (b) for `pipeline_kind.is_exchange()` (Demo + Live, see
//!        `tick_pipeline/mod.rs:121`) calls
//!        `paper_state.reconcile_balance_from_exchange(bal)` which sets
//!        `balance = exchange_balance` and lifts `peak_balance =
//!        peak_balance.max(exchange_balance)` whenever drift > 0.1%.
//!     4. `tick_pipeline/on_tick/step_6_risk_checks.rs:69` reads the synced
//!        `paper_state.drawdown_pct()` and threads it through
//!        `risk_checks::check_position_on_tick`, which emits the
//!        `RiskAction::HaltSession("SESSION DRAWDOWN: x% >= y%")` reason.
//!     5. `step_6_risk_checks.rs:454` calls
//!        `crate::drawdown_revoke::should_revoke(&reason, pipeline_kind)` and
//!        on a Live revoke decision invokes `revoke_live_authorization()`,
//!        deleting the file so `live_auth_watcher` (5s poll) tears down the
//!        Live slot.
//!
//!   Each test below isolates one link of that chain so a regression in any
//!   single component would surface here, even if the production startup
//!   flow stays green at the integration level.
//!
//! MODULE_NOTE (中文): G1-06 接線「Live 回撤觸發 HaltSession → 刪除
//!   `authorization.json`」。整條保護鏈依賴 Live 上 `paper_state.balance` 真
//!   實同步 Bybit equity；若不同步，`drawdown_pct()` 永遠 0，撤銷不觸發。
//!   2026-04-24 sub-agent 已驗證 Case A：
//!     1. 啟動 REST 抓初始餘額（3 次重試 + 硬失敗，無 10000 fallback）
//!     2. 5 分鐘 REST 餘額刷新 daemon 對抗 WS 靜默
//!     3. 每 tick 從 Arc 讀餘額 → set_bybit_sync_balance + （exchange 管線）
//!        reconcile_balance_from_exchange 寫進 paper_state.balance 並抬升
//!        peak_balance；drift > 0.1% 才修正避免雜訊
//!     4. risk_checks 讀同步後的 drawdown_pct，超閾值即 HaltSession
//!     5. should_revoke + revoke_live_authorization 對 Live 觸發、Demo/Paper 不觸發
//!   本檔逐項拆解 invariants，任一鏈節 regression 都會在此 fail。

use openclaw_engine::config::RiskConfig;
use openclaw_engine::drawdown_revoke::{
    revoke_live_authorization, should_revoke, RevokeOutcome, DRAWDOWN_REASON_PREFIX,
};
use openclaw_engine::paper_state::PaperState;
use openclaw_engine::risk_checks::{check_position_on_tick, RiskAction};
use openclaw_engine::tick_pipeline::PipelineKind;
use std::sync::Mutex as StdMutex;

// ── Env-mutating tests serialized to avoid clobbering each other and the
// `live_authorization` / `drawdown_revoke` unit tests sharing the binary.
// Pattern lifted from `live_auth_watcher::tests::ENV_GUARD`.
// 改動 OPENCLAW_SECRETS_DIR 的測試串行化，避免互相污染。
static ENV_GUARD: StdMutex<()> = StdMutex::new(());

// ── §1 reconcile_balance_from_exchange wires Bybit equity into paper_state ─
//
// EN: Verifies the *exchange-side* Bybit equity overwrites the local
// `paper_state.balance`, so a real Bybit drawdown becomes a real
// `drawdown_pct()`. Drift > 0.1% triggers the correction; this is the only
// path on Demo/Live by which paper_state ever sees the exchange number.
// 中：驗證交易所餘額會覆寫本地 `paper_state.balance`，讓 Bybit 真實回撤反映
// 在 `drawdown_pct()`；drift > 0.1% 才觸發，這是 Demo/Live 上 paper_state
// 唯一感知交易所數字的路徑。
#[test]
fn reconcile_translates_exchange_drop_into_drawdown() {
    let mut ps = PaperState::new(10_000.0);
    assert!(
        ps.drawdown_pct().abs() < 1e-9,
        "fresh PaperState must report 0 drawdown"
    );

    // Simulate the WS / REST refresh loop: Bybit reports a 15% equity drop.
    // 模擬 WS / REST 刷新：Bybit 報告 15% 回撤
    let exchange_after_loss = 8_500.0;
    let prev_local = ps
        .reconcile_balance_from_exchange(exchange_after_loss)
        .expect("drift > 0.1% must trigger correction (drift = 1500 / 10000 = 15%)");
    assert!(
        (prev_local - 10_000.0).abs() < 1e-9,
        "old balance returned for audit must be the pre-correction local value"
    );

    // After correction, drawdown_pct must reflect the synced equity.
    // 校正後 drawdown_pct 必須反映同步進來的 equity。
    assert!(
        (ps.balance() - 8_500.0).abs() < 1e-9,
        "balance must equal the exchange-reported equity after reconcile"
    );
    assert!(
        (ps.peak_balance() - 10_000.0).abs() < 1e-9,
        "peak_balance must NOT drop on a loss — it stays at the prior high so drawdown is real"
    );
    assert!(
        (ps.drawdown_pct() - 15.0).abs() < 1e-9,
        "(10000 − 8500) / 10000 * 100 = 15.0%, got {}",
        ps.drawdown_pct()
    );
}

// ── §2 small drift is absorbed (no per-tick noise correction) ──────────────
//
// EN: A < 0.1% drift between local and exchange must NOT trigger a balance
// rewrite — otherwise every tick would noisily reshape `peak_balance` and
// `drawdown_pct` on top of normal price-mark math.
// 中：< 0.1% 的 drift 不應觸發修正，避免每 tick 抖動 paper_state。
#[test]
fn reconcile_ignores_sub_threshold_drift() {
    let mut ps = PaperState::new(10_000.0);
    // 0.05% drift (well under the 0.1% threshold).
    // 0.05% drift（遠小於 0.1% 閾值）。
    let outcome = ps.reconcile_balance_from_exchange(10_005.0);
    assert!(
        outcome.is_none(),
        "drift below 0.1% must be a silent no-op, got correction {:?}",
        outcome
    );
    assert!(
        (ps.balance() - 10_000.0).abs() < 1e-9,
        "balance unchanged when drift below threshold"
    );
}

// ── §3 reconcile lifts peak_balance on a gain (so future drawdowns are real) ─
//
// EN: A *gain* must lift `peak_balance` so the next dip is measured against
// the new high. This protects against a bug where `peak` would silently
// freeze at startup balance and forever under-report drawdown.
// 中：上漲必須抬升 `peak_balance`，避免 peak 凍結在啟動餘額而長期低估回撤。
#[test]
fn reconcile_lifts_peak_on_exchange_gain() {
    let mut ps = PaperState::new(10_000.0);
    let prev = ps
        .reconcile_balance_from_exchange(11_500.0)
        .expect("15% gain must trigger correction");
    assert!((prev - 10_000.0).abs() < 1e-9);
    assert!(
        (ps.balance() - 11_500.0).abs() < 1e-9,
        "balance must follow the exchange equity up"
    );
    assert!(
        (ps.peak_balance() - 11_500.0).abs() < 1e-9,
        "peak_balance must climb on a gain so future drawdowns measure from the new high"
    );
    // No drawdown right after the climb.
    // 攀升後立即無回撤。
    assert!(
        ps.drawdown_pct().abs() < 1e-9,
        "drawdown right after a peak rise must be 0"
    );
}

// ── §4 risk_checks emits the expected SESSION DRAWDOWN HaltSession reason ──
//
// EN: Sanity-check the reason format (the exact prefix is the contract
// `should_revoke` matches against). Synthetic inputs only.
// 中：rsbi check 反向：給 risk_checks 真實 drawdown_pct，驗證它吐出
// `SESSION DRAWDOWN: …` reason —— 此前綴是 `should_revoke` 的契約。
#[test]
fn risk_checks_emits_session_drawdown_halt() {
    let cfg = RiskConfig::default(); // session_drawdown_max_pct = 15.0 by default
    // Set an open position with no PnL/time/cost trigger so only Priority 7
    // (session drawdown) can fire. We pass a drawdown above the threshold.
    // 設置無 PnL / 時間 / 成本觸發的持倉，只讓 Priority 7（session drawdown）能觸發。
    let action = check_position_on_tick(
        /* pnl_pct */ 0.0,
        /* peak_pnl_pct */ 0.0,
        /* holding_hours */ 0.0,
        /* cost_ratio */ 0.0,
        /* regime */ "neutral",
        /* atr_pct */ Some(1.0),
        /* symbol */ "BTCUSDT",
        /* entry_ts_ms */ 0,
        /* consecutive_losses */ 0,
        /* daily_loss_pct */ 0.0,
        /* session_drawdown_pct */ 15.5,
        /* cost_edge_max_ratio */ 0.2,
        /* min_profit_to_close_pct */ 0.3,
        /* exit_features */ None,
        &cfg,
    );

    match action {
        RiskAction::HaltSession(reason) => {
            assert!(
                reason.starts_with(DRAWDOWN_REASON_PREFIX),
                "reason must start with `SESSION DRAWDOWN` — this is the contract \
                 `drawdown_revoke::should_revoke` matches against. got: {:?}",
                reason
            );
            // The format is `SESSION DRAWDOWN: 15.50% >= 15.00%`. Don't pin
            // the exact float formatting (Rust default), just confirm both
            // numbers are present so a future format change is loud.
            // 不固定浮點格式，但確認兩個數字都出現。
            assert!(reason.contains("15.50"), "actual drawdown should appear: {}", reason);
            assert!(reason.contains("15.00"), "limit should appear: {}", reason);
        }
        other => panic!("expected HaltSession on session drawdown, got {:?}", other),
    }
}

// ── §5 end-to-end Live: synced equity drop → HaltSession → revoke ───────────
//
// EN: Compose §1 + §4 + drawdown_revoke. This is the live-pipeline guarantee
// in one test: a Bybit equity drop reconciled into paper_state produces the
// HaltSession reason that should_revoke accepts, which then triggers the
// authorization.json deletion. If any link breaks, this test fails.
// 中：把 §1 + §4 + drawdown_revoke 串起來：Bybit equity 跌 → paper_state
// 同步 → HaltSession → should_revoke 接受 → 刪除 authorization.json。任一
// 鏈節 regression 都會 fail。
#[test]
fn live_balance_sync_drives_drawdown_revoke_end_to_end() {
    let _g = ENV_GUARD.lock().unwrap_or_else(|e| e.into_inner());
    let tmp = tempfile::tempdir().expect("tmp dir");
    let prev_secrets = std::env::var("OPENCLAW_SECRETS_DIR").ok();
    std::env::set_var("OPENCLAW_SECRETS_DIR", tmp.path());

    // Seed a placeholder authorization.json under live/ — production writes
    // an HMAC-signed blob via _write_signed_live_authorization, but G1-06
    // only cares whether the file exists; it does not parse it.
    // 種子一個 authorization.json 占位符 — G1-06 只關心檔案存在與否，不解析內容。
    let live_dir = tmp.path().join("live");
    std::fs::create_dir_all(&live_dir).expect("mkdir live/");
    let auth_path = live_dir.join("authorization.json");
    std::fs::write(&auth_path, "{\"version\":1,\"placeholder\":true}").expect("seed auth file");
    assert!(
        auth_path.exists(),
        "fixture sanity: seeded authorization.json must exist before drawdown"
    );

    // Step 1 — simulate the per-tick reconcile loop on Live: Bybit equity
    // drops 16% (above the 15% session drawdown threshold).
    // 步驟 1 — 模擬 Live 上每 tick 對賬：Bybit 跌 16%（超過 15% 閾值）
    let mut ps = PaperState::new(10_000.0);
    let prev = ps
        .reconcile_balance_from_exchange(8_400.0)
        .expect("16% drop must trigger correction");
    assert!((prev - 10_000.0).abs() < 1e-9);

    let dd_pct = ps.drawdown_pct();
    assert!(
        dd_pct >= 15.0 && dd_pct <= 17.0,
        "drawdown must be ~16% after sync, got {}",
        dd_pct
    );

    // Step 2 — risk_checks must produce a HaltSession with SESSION DRAWDOWN.
    // 步驟 2 — risk_checks 必須產出 SESSION DRAWDOWN 的 HaltSession。
    let cfg = RiskConfig::default();
    let action = check_position_on_tick(
        0.0, 0.0, 0.0, 0.0, "neutral", Some(1.0), "BTCUSDT", 0, 0, 0.0,
        dd_pct, 0.2, 0.3, None, &cfg,
    );
    let reason = match action {
        RiskAction::HaltSession(r) => r,
        other => panic!("expected HaltSession, got {:?}", other),
    };

    // Step 3 — should_revoke accepts this reason on Live.
    // 步驟 3 — should_revoke 在 Live 上接受這個 reason。
    let decision = should_revoke(&reason, PipelineKind::Live)
        .expect("Live + SESSION DRAWDOWN must trigger revoke decision");

    // Step 4 — revoke deletes the seeded authorization.json.
    // 步驟 4 — revoke 刪除種子檔案。
    let outcome = revoke_live_authorization(&decision);

    // Restore env BEFORE asserts so a panic does not pollute later tests.
    // 還原 env 後再 assert，避免 panic 污染後續測試。
    match prev_secrets {
        Some(v) => std::env::set_var("OPENCLAW_SECRETS_DIR", v),
        None => std::env::remove_var("OPENCLAW_SECRETS_DIR"),
    }

    match outcome {
        RevokeOutcome::Removed { path } => {
            assert!(!path.exists(), "auth file must be gone after Removed");
            assert!(path.ends_with("live/authorization.json"));
        }
        other => panic!(
            "expected Removed (file existed before revoke), got {:?}",
            other
        ),
    }
}

// ── §6 Demo path: same equity drop produces HaltSession but NO revoke ─────
//
// EN: Counter-test confirming `pipeline_kind.is_exchange()` covers Demo too
// (so reconcile fires) but `should_revoke` is Live-only — Demo halt closes
// positions without touching authorization.json. Catches a regression where
// either the wiring leaks revoke to Demo or stops syncing balance on Demo.
// 中：對照測試確認 Demo 也走 reconcile（is_exchange），但 should_revoke 僅
// Live。Demo halt 關倉但不動 authorization.json。
#[test]
fn demo_balance_sync_halts_but_does_not_revoke() {
    let _g = ENV_GUARD.lock().unwrap_or_else(|e| e.into_inner());
    let tmp = tempfile::tempdir().expect("tmp dir");
    let prev_secrets = std::env::var("OPENCLAW_SECRETS_DIR").ok();
    std::env::set_var("OPENCLAW_SECRETS_DIR", tmp.path());

    let live_dir = tmp.path().join("live");
    std::fs::create_dir_all(&live_dir).expect("mkdir live/");
    let auth_path = live_dir.join("authorization.json");
    std::fs::write(&auth_path, "{\"version\":1}").expect("seed auth file");

    // Same Demo-pipeline reconcile + drawdown.
    // Demo 管線同樣對賬 + 觸發回撤。
    let mut ps = PaperState::new(10_000.0);
    ps.reconcile_balance_from_exchange(8_400.0)
        .expect("Demo also goes through is_exchange() → reconcile fires");
    let dd_pct = ps.drawdown_pct();
    assert!(dd_pct >= 15.0);

    // HaltSession is still emitted for Demo (positions close), but
    // should_revoke MUST refuse for Demo.
    // Demo 仍會 HaltSession 平倉，但 should_revoke 必須拒絕。
    let cfg = RiskConfig::default();
    let action = check_position_on_tick(
        0.0, 0.0, 0.0, 0.0, "neutral", Some(1.0), "BTCUSDT", 0, 0, 0.0,
        dd_pct, 0.2, 0.3, None, &cfg,
    );
    let reason = match action {
        RiskAction::HaltSession(r) => r,
        other => panic!("expected HaltSession, got {:?}", other),
    };
    assert!(
        should_revoke(&reason, PipelineKind::Demo).is_none(),
        "Demo drawdown must NEVER revoke authorization (Demo has no live auth concept)"
    );

    // Restore env BEFORE final assert.
    // 還原 env 後再做最終 assert。
    let auth_still_exists = auth_path.exists();
    match prev_secrets {
        Some(v) => std::env::set_var("OPENCLAW_SECRETS_DIR", v),
        None => std::env::remove_var("OPENCLAW_SECRETS_DIR"),
    }
    assert!(
        auth_still_exists,
        "authorization.json must remain untouched on Demo halt"
    );
}

// ── §7 PipelineKind::is_exchange covers Demo + Live (reconcile gate) ───────
//
// EN: Tiny invariant test pinning the gate that the per-tick loop in
// `event_consumer/loop_handlers.rs:775` uses to decide whether to call
// `reconcile_balance_from_exchange`. If a future refactor splits Live from
// `is_exchange()`, this test will catch it before the silent-drawdown
// regression hits production.
// 中：固定 `loop_handlers.rs:775` 的 gate —— 防止未來 refactor 把 Live 從
// `is_exchange()` 拿掉導致 paper_state 不再同步、drawdown 永遠 0。
#[test]
fn pipeline_kind_is_exchange_covers_live_and_demo() {
    assert!(
        PipelineKind::Live.is_exchange(),
        "Live must be an exchange pipeline so per-tick reconcile fires"
    );
    assert!(
        PipelineKind::Demo.is_exchange(),
        "Demo must be an exchange pipeline (uses Bybit Demo endpoint)"
    );
    assert!(
        !PipelineKind::Paper.is_exchange(),
        "Paper must NOT be an exchange pipeline (no Bybit account to reconcile against)"
    );
}
