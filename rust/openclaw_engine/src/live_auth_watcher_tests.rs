// ---------------------------------------------------------------------------
// MODULE_NOTE
// 模組目的：live_auth_watcher 的單元測試，從主模組拆出以遵守 CLAUDE.md §九
//          1200 行硬上限（BLOCKER-1 E2 round-2，2026-04-27）。
// Module purpose: unit tests for live_auth_watcher, extracted from the
//   main module to comply with CLAUDE.md §九 1200-line hard cap
//   (BLOCKER-1, E2 round-2, 2026-04-27).
//
// 關聯文件：CLAUDE.md §九 · live_auth_watcher.rs
// 上游：live_auth_watcher（use super::*）
// 下游：cargo test --bin openclaw-engine
// ---------------------------------------------------------------------------

use super::*;
use crate::startup::{ExchangePipelineBindings, PrivateWsBindings};
use async_trait::async_trait;
use openclaw_engine::account_manager::AccountManager;
use openclaw_engine::bybit_rest_client::{BybitEnvironment, BybitRestClient};
use openclaw_engine::event_consumer::ExchangeEvent;
use openclaw_engine::live_authorization::{
    compute_signature, LiveAuthorization, APPROVED_SYSTEM_MODE_LIVE_RESERVED, SCHEMA_VERSION,
};
use std::sync::atomic::{AtomicBool, AtomicU8, AtomicUsize, Ordering};
use std::sync::Mutex as StdMutex;

const TEST_SECRET: &str = "phase3-test-ipc-secret-do-not-ship";

// ── mock SpawnOp ──────────────────────────────────────────────────
// Counts calls, flips is_spawned state, and returns user-scripted
// outcomes. All methods are `Send + Sync` since the watcher's
// `Arc<dyn SpawnOp>` field is erased behind a trait object.
// 計 call 數、切換 is_spawned 狀態、回指定結果。所有方法 Send+Sync，
// 配合 watcher 內的 `Arc<dyn SpawnOp>` trait 物件。

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[allow(dead_code)] // NotAvailable reserved for future scenarios; kept for symmetry.
enum ScriptedSpawn {
    Ok,
    BuildReturnedNone,
    NotAvailable,
    AlreadySpawned,
}

pub(super) struct MockSlotOp {
    pub(super) spawned: AtomicBool,
    pub(super) spawn_calls: AtomicUsize,
    pub(super) teardown_calls: AtomicUsize,
    /// Scripted sequence consumed front-to-back on each spawn; once
    /// exhausted, the last entry repeats.
    /// 每次 spawn 由前往後消耗；耗盡後最後一項重複。
    script: StdMutex<Vec<ScriptedSpawn>>,
}

impl MockSlotOp {
    pub(super) fn new(script: Vec<ScriptedSpawn>) -> Arc<Self> {
        Arc::new(Self {
            spawned: AtomicBool::new(false),
            spawn_calls: AtomicUsize::new(0),
            teardown_calls: AtomicUsize::new(0),
            script: StdMutex::new(script),
        })
    }
    fn next_outcome(&self) -> ScriptedSpawn {
        let mut guard = self.script.lock().unwrap();
        if guard.len() > 1 {
            guard.remove(0)
        } else {
            guard.first().copied().unwrap_or(ScriptedSpawn::Ok)
        }
    }
}

/// Construct a synthetic [`SpawnOutput`] for tests without invoking
/// `build_exchange_pipeline` or any Bybit REST/WS infrastructure.
///
/// Uses `BybitRestClient::new(LiveDemo, ...)` (credentials strings keep the
/// client from emitting a missing-credentials warn in test logs), a fresh
/// `AccountManager::new()`, and a tokio `unbounded_channel` for the
/// private-WS exchange event receiver. All fields are intentionally
/// minimal — the spawner callback only receives the `SpawnOutput` value
/// and does not make any API calls with it.
///
/// HIGH-2 (E2 round-2): this factory lets the mock's `try_spawn` return
/// `Ok(Some(_))` so the watcher's spawner-callback path can be exercised
/// in unit tests. Previous approach (`unreachable!`) left the most critical
/// regression path — spawner actually called + handle_slot populated —
/// completely uncovered.
///
/// 測試用合成 [`SpawnOutput`]，不呼叫 `build_exchange_pipeline` 或任何
/// Bybit REST/WS 基礎設施。
///
/// HIGH-2（E2 round-2）：此 factory 讓 mock `try_spawn` 回 `Ok(Some(_))`，
/// 使 watcher 的 spawner-callback 路徑可在單測中驗證。
pub(super) fn synthetic_spawn_output(parent: &CancellationToken) -> SpawnOutput {
    let rest_client = BybitRestClient::new(
        BybitEnvironment::LiveDemo,
        Some("test-key".into()),
        Some("test-secret".into()),
    )
    .expect("BybitRestClient::new(LiveDemo) must not fail in test environment");

    let (_, exchange_event_rx) = tokio::sync::mpsc::unbounded_channel::<ExchangeEvent>();
    let ws_bindings = PrivateWsBindings {
        bybit_balance: Arc::new(parking_lot::RwLock::new(None)),
        api_pnl: Arc::new(parking_lot::RwLock::new(std::collections::HashMap::new())),
        exchange_event_rx,
    };
    let bindings = ExchangePipelineBindings {
        env: BybitEnvironment::LiveDemo,
        rest_client: Arc::new(rest_client),
        account_manager: Arc::new(AccountManager::new()),
        taker_fee: None,
        initial_balance: 0.0,
        ws_bindings,
        risk_level: Arc::new(AtomicU8::new(0)),
        health: Arc::new(AtomicU8::new(0)),
        seed_positions: vec![],
    };
    SpawnOutput {
        bindings,
        slot_cancel_token: parent.child_token(),
    }
}

#[async_trait]
impl SpawnOp for MockSlotOp {
    fn is_spawned(&self) -> bool {
        self.spawned.load(Ordering::SeqCst)
    }
    async fn try_spawn(&self, _cfg: &SpawnConfig<'_>) -> Result<Option<SpawnOutput>, SpawnError> {
        self.spawn_calls.fetch_add(1, Ordering::SeqCst);
        match self.next_outcome() {
            ScriptedSpawn::Ok => {
                self.spawned.store(true, Ordering::SeqCst);
                // Return Ok(None) instead of Ok(Some(SpawnOutput))
                // because constructing a real SpawnOutput in tests
                // requires REST client + WS bindings infra. The
                // watcher's "no spawner injected" branch covers this
                // path with the same backoff.reset() + info log
                // observable behaviour, so test assertions
                // (spawn_calls / is_spawned) still hold.
                //
                // 回 Ok(None) 而非 Ok(Some(SpawnOutput)) — 構造真
                // SpawnOutput 需 REST + WS infra。Watcher 的「未注入
                // spawner」分支覆蓋此路徑，行為（backoff.reset() +
                // info log）與 Some 等價，測試斷言不變。
                Ok(None)
            }
            ScriptedSpawn::BuildReturnedNone => Ok(None),
            ScriptedSpawn::NotAvailable => Err(SpawnError::NotAvailable),
            ScriptedSpawn::AlreadySpawned => Err(SpawnError::AlreadySpawned),
        }
    }
    async fn teardown(&self) -> Result<(), TeardownError> {
        self.teardown_calls.fetch_add(1, Ordering::SeqCst);
        self.spawned.store(false, Ordering::SeqCst);
        Ok(())
    }
}

// ── auth file helper ─────────────────────────────────────────────
fn fresh_auth(now_ms: u64, ttl_ms: u64) -> LiveAuthorization {
    let mut auth = LiveAuthorization {
        version: SCHEMA_VERSION,
        tier: "T0_ENTRY".into(),
        issued_at_ms: now_ms,
        expires_at_ms: now_ms + ttl_ms,
        operator_id: "watcher_test".into(),
        approved_system_mode: APPROVED_SYSTEM_MODE_LIVE_RESERVED.into(),
        env_allowed: vec!["live_demo".into()],
        sig: String::new(),
    };
    auth.sig = compute_signature(&auth, TEST_SECRET);
    auth
}

/// Configure the process-wide env vars so `load_and_verify` reads
/// the authorization file under `secrets_dir/live/authorization.json`.
/// This is a test-only indirect — production reads the same env vars.
///
/// **Env var contention**: many tests mutate `OPENCLAW_SECRETS_DIR` /
/// `OPENCLAW_IPC_SECRET`; running watcher tests together (or with
/// other live_authorization tests) under a single test binary risks
/// interleaving. We serialize watcher tests via a mutex below.
/// 許多測試改 `OPENCLAW_SECRETS_DIR` / `OPENCLAW_IPC_SECRET`；
/// 同一 test binary 並行會交錯。下方 mutex 串行。
fn set_test_env(secrets_dir: &std::path::Path) {
    std::env::set_var("OPENCLAW_SECRETS_DIR", secrets_dir);
    std::env::set_var("OPENCLAW_IPC_SECRET", TEST_SECRET);
}
fn clear_test_env() {
    std::env::remove_var("OPENCLAW_SECRETS_DIR");
    std::env::remove_var("OPENCLAW_IPC_SECRET");
}

// Serialize all watcher tests to avoid env-var contention between
// parallel tests in the same binary.
// 串行化所有 watcher 測試，避免同 binary 內並行爭 env var。
static ENV_GUARD: StdMutex<()> = StdMutex::new(());

fn drop_auth_file(secrets_dir: &std::path::Path, auth: &LiveAuthorization) {
    let live_dir = secrets_dir.join("live");
    std::fs::create_dir_all(&live_dir).unwrap();
    let path = live_dir.join("authorization.json");
    std::fs::write(path, serde_json::to_string_pretty(auth).unwrap()).unwrap();
}

fn remove_auth_file(secrets_dir: &std::path::Path) {
    let path = secrets_dir.join("live").join("authorization.json");
    let _ = std::fs::remove_file(path);
}

// Minimal ConfigManager for tests — just loads default EngineBootstrap.
// 測試用最小 ConfigManager — 只載入預設 EngineBootstrap。
fn test_config() -> Arc<ConfigManager> {
    // ConfigManager::load(None) falls back to default on missing file.
    Arc::new(ConfigManager::load(None).expect("load config (defaults ok)"))
}

fn now_ms() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

// ── tests ────────────────────────────────────────────────────────

#[tokio::test]
async fn watcher_respawns_when_auth_becomes_valid() {
    let _guard = ENV_GUARD.lock().unwrap_or_else(|e| e.into_inner());
    let tmp = tempfile::tempdir().unwrap();
    set_test_env(tmp.path());
    let shutdown = CancellationToken::new();

    let mock = MockSlotOp::new(vec![ScriptedSpawn::Ok]);
    let (watcher, handle) = LiveAuthWatcher::with_params(
        Arc::clone(&mock) as Arc<dyn SpawnOp>,
        test_config(),
        BybitEnvironment::LiveDemo,
        shutdown.clone(),
        Duration::from_millis(50), // short poll for fast test
        Duration::from_millis(10),
        Duration::from_millis(100),
    );

    let watcher_task = tokio::spawn(watcher.run());

    // Slot is Empty and no auth exists — watcher stays idle.
    tokio::time::sleep(Duration::from_millis(80)).await;
    assert_eq!(mock.spawn_calls.load(Ordering::SeqCst), 0);

    // Drop a valid authorization file and poke the IPC trigger.
    let auth = fresh_auth(now_ms(), 3600_000);
    drop_auth_file(tmp.path(), &auth);
    let _ = handle.trigger();

    // Watcher should respawn on the trigger (fast-path, <50ms).
    // watcher 應以 IPC 快路徑 respawn（<50ms）。
    tokio::time::timeout(Duration::from_secs(2), async {
        while mock.spawn_calls.load(Ordering::SeqCst) == 0 {
            tokio::time::sleep(Duration::from_millis(5)).await;
        }
    })
    .await
    .expect("spawn must be attempted after trigger");

    assert!(
        mock.is_spawned(),
        "slot must be Spawned after successful spawn"
    );

    shutdown.cancel();
    let _ = watcher_task.await;
    clear_test_env();
    remove_auth_file(tmp.path());
}

#[tokio::test]
async fn watcher_tears_down_when_auth_invalidates() {
    let _guard = ENV_GUARD.lock().unwrap_or_else(|e| e.into_inner());
    let tmp = tempfile::tempdir().unwrap();
    set_test_env(tmp.path());
    let shutdown = CancellationToken::new();

    // Seed: valid auth on disk, slot already Spawned (simulate post-renewal).
    let auth = fresh_auth(now_ms(), 3600_000);
    drop_auth_file(tmp.path(), &auth);
    let mock = MockSlotOp::new(vec![ScriptedSpawn::Ok]);
    mock.spawned.store(true, Ordering::SeqCst);

    let (watcher, handle) = LiveAuthWatcher::with_params(
        Arc::clone(&mock) as Arc<dyn SpawnOp>,
        test_config(),
        BybitEnvironment::LiveDemo,
        shutdown.clone(),
        Duration::from_millis(50),
        Duration::from_millis(10),
        Duration::from_millis(100),
    );
    let watcher_task = tokio::spawn(watcher.run());

    // Yield so the watcher enters its loop. With valid auth + Spawned slot
    // this is the happy path; no actions expected.
    // 讓 watcher 進 loop。有效授權 + Spawned = 快樂路徑，無動作。
    tokio::time::sleep(Duration::from_millis(80)).await;
    assert_eq!(mock.teardown_calls.load(Ordering::SeqCst), 0);

    // Remove auth file (simulates operator revoke) + trigger.
    remove_auth_file(tmp.path());
    let _ = handle.trigger();

    tokio::time::timeout(Duration::from_secs(2), async {
        while mock.teardown_calls.load(Ordering::SeqCst) == 0 {
            tokio::time::sleep(Duration::from_millis(5)).await;
        }
    })
    .await
    .expect("teardown must be called after auth invalidates");

    assert!(!mock.is_spawned(), "slot must be Empty after teardown");

    shutdown.cancel();
    let _ = watcher_task.await;
    clear_test_env();
}

#[tokio::test]
async fn watcher_respects_backoff_on_spawn_failure() {
    let _guard = ENV_GUARD.lock().unwrap_or_else(|e| e.into_inner());
    let tmp = tempfile::tempdir().unwrap();
    set_test_env(tmp.path());
    let shutdown = CancellationToken::new();

    // Auth valid, every spawn fails → backoff should throttle.
    // 授權有效，但每次 spawn 失敗 → 退避節流。
    let auth = fresh_auth(now_ms(), 3600_000);
    drop_auth_file(tmp.path(), &auth);
    let mock = MockSlotOp::new(vec![ScriptedSpawn::BuildReturnedNone]);

    // Poll every 10ms, base backoff 100ms, max 500ms. In 250ms we
    // expect 1 spawn (tick 0) + maybe 1 more after 100ms backoff
    // expires (tick ~100+) + another after another 200ms doubling
    // (tick ~300+). Certainly NOT 25 spawns (one per 10ms tick).
    // 10ms 一 tick，退避 base=100ms / max=500ms；250ms 內預期 1~2 次
    // spawn 嘗試，絕非 25 次（每 tick 一次）。
    let (watcher, handle) = LiveAuthWatcher::with_params(
        Arc::clone(&mock) as Arc<dyn SpawnOp>,
        test_config(),
        BybitEnvironment::LiveDemo,
        shutdown.clone(),
        Duration::from_millis(10),
        Duration::from_millis(100),
        Duration::from_millis(500),
    );
    let watcher_task = tokio::spawn(watcher.run());

    // Kick with IPC trigger + let the watcher ride for 250ms.
    let _ = handle.trigger();
    tokio::time::sleep(Duration::from_millis(250)).await;

    let calls = mock.spawn_calls.load(Ordering::SeqCst);
    assert!(
        calls >= 1,
        "watcher must attempt at least one spawn; got {calls}"
    );
    assert!(
        calls <= 5,
        "backoff must throttle spawn attempts — got {calls} in 250ms \
         (unthrottled would be ~25)"
    );

    shutdown.cancel();
    let _ = watcher_task.await;
    clear_test_env();
    remove_auth_file(tmp.path());
}

#[tokio::test]
async fn watcher_breaks_on_engine_shutdown() {
    let _guard = ENV_GUARD.lock().unwrap_or_else(|e| e.into_inner());
    let tmp = tempfile::tempdir().unwrap();
    set_test_env(tmp.path());
    let shutdown = CancellationToken::new();

    let mock = MockSlotOp::new(vec![ScriptedSpawn::Ok]);
    let (watcher, _handle) = LiveAuthWatcher::with_params(
        Arc::clone(&mock) as Arc<dyn SpawnOp>,
        test_config(),
        BybitEnvironment::LiveDemo,
        shutdown.clone(),
        Duration::from_secs(60), // long poll — shouldn't matter
        Duration::from_secs(1),
        Duration::from_secs(60),
    );

    let watcher_task = tokio::spawn(watcher.run());

    // Cancel immediately.
    shutdown.cancel();

    tokio::time::timeout(Duration::from_secs(2), watcher_task)
        .await
        .expect("watcher must exit within 2s after shutdown")
        .expect("watcher task must not panic");
    clear_test_env();
}

#[tokio::test]
async fn ipc_trigger_coalesces_when_full() {
    // Trigger twice in a row before the watcher consumes. First send
    // must succeed, second must return Ok(false) (coalesced) — not an
    // error. This exercises the `TrySendError::Full` arm.
    // 連發兩次 trigger。第一次成功；第二次 Ok(false) 合併 — 不是錯誤。
    let _guard = ENV_GUARD.lock().unwrap_or_else(|e| e.into_inner());
    let tmp = tempfile::tempdir().unwrap();
    set_test_env(tmp.path());
    let shutdown = CancellationToken::new();
    let mock = MockSlotOp::new(vec![ScriptedSpawn::Ok]);
    // Long poll so the receiver doesn't drain before we probe.
    // 長輪詢避免 receiver 先於 probe 消耗。
    let (_watcher, handle) = LiveAuthWatcher::with_params(
        Arc::clone(&mock) as Arc<dyn SpawnOp>,
        test_config(),
        BybitEnvironment::LiveDemo,
        shutdown.clone(),
        Duration::from_secs(60),
        Duration::from_secs(1),
        Duration::from_secs(60),
    );

    let first = handle.trigger().expect("first trigger must succeed");
    assert!(first, "first trigger must be accepted");
    let second = handle
        .trigger()
        .expect("second trigger must be Ok (coalesced)");
    assert!(!second, "second trigger in a row must coalesce (Ok(false))");

    clear_test_env();
}

#[tokio::test]
async fn ipc_trigger_errors_when_watcher_dropped() {
    // Drop the watcher (and its receiver) — next trigger must
    // return Err(()) so callers can log loudly.
    // drop watcher/receiver — 下次 trigger 回 Err(())，讓呼叫端大聲 log。
    let _guard = ENV_GUARD.lock().unwrap_or_else(|e| e.into_inner());
    let tmp = tempfile::tempdir().unwrap();
    set_test_env(tmp.path());
    let shutdown = CancellationToken::new();
    let mock = MockSlotOp::new(vec![ScriptedSpawn::Ok]);

    let (watcher, handle) = LiveAuthWatcher::with_params(
        Arc::clone(&mock) as Arc<dyn SpawnOp>,
        test_config(),
        BybitEnvironment::LiveDemo,
        shutdown.clone(),
        Duration::from_secs(60),
        Duration::from_secs(1),
        Duration::from_secs(60),
    );
    drop(watcher);

    // After drop, the Sender can observe Closed on try_send.
    // drop 後 Sender 的 try_send 可觀察到 Closed。
    let res = handle.trigger();
    assert_eq!(res, Err(()), "trigger after watcher drop must return Err");

    clear_test_env();
}

#[tokio::test]
async fn spawn_output_already_spawned_treated_as_success() {
    // Scripted AlreadySpawned should be swallowed with debug log +
    // backoff reset. No teardown should fire on this path.
    // 腳本化 AlreadySpawned 應被 debug log 吞掉、重設退避，
    // 不觸發 teardown。
    let _guard = ENV_GUARD.lock().unwrap_or_else(|e| e.into_inner());
    let tmp = tempfile::tempdir().unwrap();
    set_test_env(tmp.path());
    let shutdown = CancellationToken::new();

    let auth = fresh_auth(now_ms(), 3600_000);
    drop_auth_file(tmp.path(), &auth);

    let mock = MockSlotOp::new(vec![ScriptedSpawn::AlreadySpawned]);
    let (watcher, handle) = LiveAuthWatcher::with_params(
        Arc::clone(&mock) as Arc<dyn SpawnOp>,
        test_config(),
        BybitEnvironment::LiveDemo,
        shutdown.clone(),
        Duration::from_millis(50),
        Duration::from_millis(10),
        Duration::from_millis(100),
    );
    let watcher_task = tokio::spawn(watcher.run());

    let _ = handle.trigger();
    tokio::time::timeout(Duration::from_secs(2), async {
        while mock.spawn_calls.load(Ordering::SeqCst) == 0 {
            tokio::time::sleep(Duration::from_millis(5)).await;
        }
    })
    .await
    .expect("spawn must be attempted");

    assert_eq!(mock.teardown_calls.load(Ordering::SeqCst), 0);
    shutdown.cancel();
    let _ = watcher_task.await;
    clear_test_env();
    remove_auth_file(tmp.path());
}

// ── 2026-04-27 LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN tests ──
// ── 2026-04-27 修復新增測試 ──

/// Mock SpawnOp that returns `Ok(None)` — used for tests that inject a
/// spawner but verify the *no-bindings* path (spawner callback NOT invoked).
/// 回 `Ok(None)` 的 mock，供注入 spawner 但驗證「無 bindings 路徑」的測試。
struct SpawnerExerciseMock {
    spawned: AtomicBool,
    spawn_calls: AtomicUsize,
    teardown_calls: AtomicUsize,
}

impl SpawnerExerciseMock {
    fn new() -> Arc<Self> {
        Arc::new(Self {
            spawned: AtomicBool::new(false),
            spawn_calls: AtomicUsize::new(0),
            teardown_calls: AtomicUsize::new(0),
        })
    }
}

#[async_trait]
impl SpawnOp for SpawnerExerciseMock {
    fn is_spawned(&self) -> bool {
        self.spawned.load(Ordering::SeqCst)
    }
    async fn try_spawn(&self, cfg: &SpawnConfig<'_>) -> Result<Option<SpawnOutput>, SpawnError> {
        self.spawn_calls.fetch_add(1, Ordering::SeqCst);
        self.spawned.store(true, Ordering::SeqCst);
        // Ok(None) keeps SpawnOutput construction off the test path —
        // the watcher's spawner-injected branch handles `Ok(Some(_))`
        // and the no-spawner branch handles `Ok(None)`. We test the
        // *injection* (handle slot updates) by hooking the spawner
        // directly via the synthetic_spawner_call_count below. Real
        // SpawnOutput construction lives in integration tests gated
        // on a live Bybit endpoint.
        //
        // 用 Ok(None) 避開 SpawnOutput 構造（需 REST + WS）。spawner
        // 注入測試藉由直接呼叫 spawner 的 synthetic count 驗證。完整
        // SpawnOutput 構造留給整合測試。
        let _ = cfg;
        Ok(None)
    }
    async fn teardown(&self) -> Result<(), TeardownError> {
        self.teardown_calls.fetch_add(1, Ordering::SeqCst);
        self.spawned.store(false, Ordering::SeqCst);
        Ok(())
    }
}

// ── HIGH-2 mock: returns Ok(Some(SpawnOutput)) ──────────────────────
// Unlike SpawnerExerciseMock (which returns Ok(None) to avoid bindings
// construction), this mock uses `synthetic_spawn_output` to provide a
// minimal but type-correct SpawnOutput so the watcher's spawner callback
// arm is actually entered. This is the critical happy-path regression
// coverage E2 required (HIGH-2, E2 round-2, 2026-04-27).
//
// SpawnerExerciseMock 回 Ok(None) 避開 bindings 構造；此 mock 使用
// `synthetic_spawn_output` 提供型別正確的 SpawnOutput，讓 watcher
// 的 spawner callback arm 真正進入 — HIGH-2 E2 要求的核心 regression 覆蓋。
struct HappyPathSpawnMock {
    spawned: AtomicBool,
    spawn_calls: AtomicUsize,
}

impl HappyPathSpawnMock {
    fn new() -> Arc<Self> {
        Arc::new(Self {
            spawned: AtomicBool::new(false),
            spawn_calls: AtomicUsize::new(0),
        })
    }
}

#[async_trait]
impl SpawnOp for HappyPathSpawnMock {
    fn is_spawned(&self) -> bool {
        self.spawned.load(Ordering::SeqCst)
    }
    async fn try_spawn(&self, cfg: &SpawnConfig<'_>) -> Result<Option<SpawnOutput>, SpawnError> {
        self.spawn_calls.fetch_add(1, Ordering::SeqCst);
        self.spawned.store(true, Ordering::SeqCst);
        // HIGH-2 (E2 round-2): return Ok(Some(SpawnOutput)) using the
        // synthetic factory so the watcher's (Some(spawner), Some(slot))
        // arm is entered and the spawner callback count + handle_slot
        // can be verified. This is the path that was 0% covered before.
        //
        // HIGH-2（E2 round-2）：用合成 factory 回 Ok(Some(_))，讓
        // watcher 的 (Some(spawner), Some(slot)) 分支真正進入。
        // spawner call count + handle_slot 的斷言驗證之前 0% 覆蓋的路徑。
        Ok(Some(synthetic_spawn_output(&cfg.parent_shutdown_token)))
    }
    async fn teardown(&self) -> Result<(), TeardownError> {
        self.spawned.store(false, Ordering::SeqCst);
        Ok(())
    }
}

/// Verify that injecting a `LivePipelineSpawner` does not break the
/// existing watcher state machine. The spawner is technically not
/// invoked here (the mock returns `Ok(None)`), but the watcher must
/// still drive the rest of the loop correctly when a spawner is
/// present.
/// 注入 spawner 不破現有 watcher 狀態機。本測試 spawner 不會被觸發
/// （mock 回 None），但 watcher 仍需正確驅動 loop。
#[tokio::test]
async fn watcher_with_spawner_handles_build_returned_none() {
    let _guard = ENV_GUARD.lock().unwrap_or_else(|e| e.into_inner());
    let tmp = tempfile::tempdir().unwrap();
    set_test_env(tmp.path());
    let shutdown = CancellationToken::new();

    let auth = fresh_auth(now_ms(), 3600_000);
    drop_auth_file(tmp.path(), &auth);

    let mock = SpawnerExerciseMock::new();
    let spawner_calls = Arc::new(AtomicUsize::new(0));
    let calls_for_closure = Arc::clone(&spawner_calls);
    let spawner: LivePipelineSpawner =
        Arc::new(move |_out: SpawnOutput| -> LivePipelineSpawnResult {
            calls_for_closure.fetch_add(1, Ordering::SeqCst);
            // Spawn a no-op OS thread so the handle is real.
            // 啟動空 OS 線程，handle 真實。
            Ok(std::thread::spawn(|| ()))
        });
    let handle_slot: LiveThreadHandleSlot = Arc::new(ParkingMutex::new(None));

    let (watcher, trigger) = LiveAuthWatcher::with_pipeline_spawner(
        Arc::clone(&mock) as Arc<dyn SpawnOp>,
        test_config(),
        BybitEnvironment::LiveDemo,
        shutdown.clone(),
        spawner,
        Arc::clone(&handle_slot),
    );
    let watcher_task = tokio::spawn(watcher.run());

    let _ = trigger.trigger();
    tokio::time::timeout(Duration::from_secs(2), async {
        while mock.spawn_calls.load(Ordering::SeqCst) == 0 {
            tokio::time::sleep(Duration::from_millis(5)).await;
        }
    })
    .await
    .expect("slot try_spawn must be attempted");

    // mock returns Ok(None) so the spawner callback is NOT invoked.
    // watcher must still backoff.record_failure() instead of panicking
    // on the missing-bindings path.
    // mock 回 Ok(None) → spawner 不被叫；watcher 走 backoff 失敗路徑。
    assert_eq!(spawner_calls.load(Ordering::SeqCst), 0);
    assert!(
        handle_slot.lock().is_none(),
        "no thread handle on Ok(None) path"
    );

    shutdown.cancel();
    let _ = watcher_task.await;
    clear_test_env();
    remove_auth_file(tmp.path());
}

/// Verify the watcher honours the `LiveThreadHandleSlot` contract — when
/// a spawner is NOT injected (Phase 3 path), the handle slot stays None
/// no matter what `slot_op.try_spawn` returns.
/// 不注入 spawner（Phase 3 路徑）時 handle slot 永遠為 None。
#[tokio::test]
async fn watcher_without_spawner_keeps_handle_slot_empty() {
    let _guard = ENV_GUARD.lock().unwrap_or_else(|e| e.into_inner());
    let tmp = tempfile::tempdir().unwrap();
    set_test_env(tmp.path());
    let shutdown = CancellationToken::new();

    let auth = fresh_auth(now_ms(), 3600_000);
    drop_auth_file(tmp.path(), &auth);

    let mock = MockSlotOp::new(vec![ScriptedSpawn::Ok]);
    // Phase 3 constructor — no spawner.
    // Phase 3 構造 — 無 spawner。
    let (watcher, trigger) = LiveAuthWatcher::with_params(
        Arc::clone(&mock) as Arc<dyn SpawnOp>,
        test_config(),
        BybitEnvironment::LiveDemo,
        shutdown.clone(),
        Duration::from_millis(50),
        Duration::from_millis(10),
        Duration::from_millis(100),
    );
    let watcher_task = tokio::spawn(watcher.run());

    let _ = trigger.trigger();
    tokio::time::timeout(Duration::from_secs(2), async {
        while mock.spawn_calls.load(Ordering::SeqCst) == 0 {
            tokio::time::sleep(Duration::from_millis(5)).await;
        }
    })
    .await
    .expect("slot try_spawn must be attempted");

    // Watcher has no handle slot; nothing to assert except no panic
    // and the slot is Spawned as the mock declared.
    // watcher 無 handle slot；除無 panic + slot Spawned 外無其他斷言。
    assert!(mock.is_spawned());

    shutdown.cancel();
    let _ = watcher_task.await;
    clear_test_env();
    remove_auth_file(tmp.path());
}

/// HIGH-2 (E2 round-2): Happy-path test — spawner callback is invoked.
///
/// Uses `HappyPathSpawnMock` (returns `Ok(Some(SpawnOutput))`) and
/// a real `LivePipelineSpawner` closure to verify:
///   1. `spawner_call_count == 1` after a single successful respawn.
///   2. `handle_slot` is `Some` after the spawner sets it.
///
/// This covers the previously-0%-covered
/// `(Some(spawner), Some(handle_slot))` arm in `decide_once`'s respawn
/// branch — the most critical regression path for the
/// LIVE-AUTH-WATCHER-EVENT-CONSUMER-SPAWN fix.
///
/// HIGH-2（E2 round-2）：Happy-path 測試 — spawner callback 被呼叫。
///
/// `HappyPathSpawnMock`（回 `Ok(Some(SpawnOutput))`）+ 真實 spawner
/// closure 驗證：
///   1. 單次成功 respawn 後 `spawner_call_count == 1`。
///   2. spawner 設定後 `handle_slot` 為 `Some`。
///
/// 覆蓋 `decide_once` respawn 分支中先前 0% 覆蓋的
/// `(Some(spawner), Some(handle_slot))` arm。
#[tokio::test]
async fn spawner_callback_invoked_and_handle_slot_populated_on_ok_some() {
    let _guard = ENV_GUARD.lock().unwrap_or_else(|e| e.into_inner());
    let tmp = tempfile::tempdir().unwrap();
    set_test_env(tmp.path());
    let shutdown = CancellationToken::new();

    // Drop a valid auth so the watcher enters the respawn arm.
    // 寫有效授權讓 watcher 進入 respawn arm。
    let auth = fresh_auth(now_ms(), 3600_000);
    drop_auth_file(tmp.path(), &auth);

    let mock = HappyPathSpawnMock::new();

    // Shared spawner call counter and handle slot.
    // 共享 spawner call 計數器與 handle slot。
    let spawner_call_count = Arc::new(AtomicUsize::new(0));
    let call_count_c = Arc::clone(&spawner_call_count);
    let handle_slot: LiveThreadHandleSlot = Arc::new(ParkingMutex::new(None));

    let spawner: LivePipelineSpawner =
        Arc::new(move |_out: SpawnOutput| -> LivePipelineSpawnResult {
            call_count_c.fetch_add(1, Ordering::SeqCst);
            // Spawn a no-op OS thread so the JoinHandle is real.
            // 啟動空 OS 線程，JoinHandle 真實。
            Ok(std::thread::spawn(|| ()))
        });

    let (watcher, trigger) = LiveAuthWatcher::with_pipeline_spawner(
        Arc::clone(&mock) as Arc<dyn SpawnOp>,
        test_config(),
        BybitEnvironment::LiveDemo,
        shutdown.clone(),
        Arc::clone(&spawner),
        Arc::clone(&handle_slot),
    );
    let watcher_task = tokio::spawn(watcher.run());

    // Kick the watcher via IPC trigger for immediate decision cycle.
    // 用 IPC trigger 踢 watcher，立即執行決策週期。
    let _ = trigger.trigger();

    // Wait until slot_op.try_spawn has been called (spawner mock sets
    // spawn_calls on every try_spawn invocation).
    // 等 slot_op.try_spawn 被呼叫（mock 在每次 try_spawn 計數）。
    tokio::time::timeout(Duration::from_secs(2), async {
        while mock.spawn_calls.load(Ordering::SeqCst) == 0 {
            tokio::time::sleep(Duration::from_millis(5)).await;
        }
    })
    .await
    .expect("slot try_spawn must be attempted within 2s");

    // Wait until spawner callback has been invoked.
    // 等 spawner callback 被呼叫。
    tokio::time::timeout(Duration::from_secs(2), async {
        while spawner_call_count.load(Ordering::SeqCst) == 0 {
            tokio::time::sleep(Duration::from_millis(5)).await;
        }
    })
    .await
    .expect("spawner callback must be invoked within 2s after Ok(Some) path");

    // Assertion 1: spawner callback call count == 1.
    // 斷言 1：spawner callback call count == 1。
    assert_eq!(
        spawner_call_count.load(Ordering::SeqCst),
        1,
        "spawner callback must be called exactly once per successful respawn"
    );

    // Assertion 2: handle_slot is Some after spawner runs.
    // 斷言 2：spawner 執行後 handle_slot 為 Some。
    assert!(
        handle_slot.lock().is_some(),
        "handle_slot must be Some after spawner successfully set the JoinHandle"
    );

    shutdown.cancel();
    let _ = watcher_task.await;
    clear_test_env();
    remove_auth_file(tmp.path());
}
