//! Shared REST client + instrument info + fee-rate tasks init.
//! 共享 REST 客戶端 + 品種規格 + 費率任務初始化。
//!
//! MODULE_NOTE (EN): Extracted from `main.rs` (G1-03 Wave 1). The
//!   `init_shared_clients_and_instruments` fn:
//!     1. Picks the highest-priority exchange pipeline (Live > Demo) to own
//!        the shared REST client + AccountManager for scanner / fee tasks.
//!     2. Runs the INSTR-WIRE-1 fail-closed startup refresh — returns 0
//!        symbols or network failure triggers `cancel.cancel()` + 500ms
//!        drain + `std::process::exit(1)` so systemd/watchdog can restart.
//!        Replaces panic!-in-async (ambiguous shutdown ordering) with a
//!        predictable exit path that lets spawned tasks clean up IPC socket
//!        + flush tracing.
//!     3. Resolves paper initial balance (MAJOR-4 priority chain).
//!     4. Spawns periodic 4h instrument refresh + fee rate tasks.
//! MODULE_NOTE (中): 從 `main.rs` 抽出（G1-03 Wave 1）。
//!   `init_shared_clients_and_instruments`：
//!     1. 選最高優先交易所管線（Live > Demo）作為 scanner / fee 任務的共享
//!        REST + AccountManager。
//!     2. 跑 INSTR-WIRE-1 fail-closed 啟動刷新 — 回 0 或網路錯誤 → cancel +
//!        500ms drain + `exit(1)`，讓 systemd/watchdog 重啟。取代
//!        panic!-in-async（關機順序曖昧），改走可預期的 exit 路徑讓子任務
//!        有機會清 IPC socket + flush tracing。
//!     3. 解析紙盤初始餘額（MAJOR-4 優先鏈）。
//!     4. 啟動每 4h 品種刷新 + 費率任務。

use crate::startup::{resolve_paper_initial_balance, ExchangePipelineBindings};
use crate::tasks;
use openclaw_engine::account_manager::AccountManager;
use openclaw_engine::bybit_rest_client::BybitRestClient;
use openclaw_engine::instrument_info::InstrumentInfoCache;
use std::sync::Arc;
use tokio_util::sync::CancellationToken;
use tracing::{error, info, warn};

/// Outputs of `init_shared_clients_and_instruments`.
/// `init_shared_clients_and_instruments` 的輸出。
pub(crate) struct SharedClientsBundle {
    pub shared_client: Option<Arc<BybitRestClient>>,
    pub shared_account_manager: Option<Arc<AccountManager>>,
    pub shared_instruments: Option<Arc<InstrumentInfoCache>>,
    pub paper_balance: f64,
}

/// Build shared REST client + instrument cache; spawn 4h instrument refresh +
/// fee rate tasks. Returns `SharedClientsBundle`. On fail-closed paths
/// (0 symbols / Err) calls `cancel.cancel()` + 500ms sleep + `exit(1)`.
///
/// EN: The `exit(1)` rather than `panic!` is deliberate — async runtime panic
///   has undefined shutdown ordering across tokio workers. `exit(1)` runs
///   atexit handlers (tracing flush, libc stdio) but does NOT unwind the
///   Rust stack. The 500ms sleep is a bounded window for spawned tasks (IPC
///   server at engine.sock, live_auth_watcher, etc.) to observe cancel +
///   cleanup their sockets — without it the next startup fails with
///   EADDRINUSE.
/// 中: `exit(1)` 代替 `panic!` 是刻意選擇 — async runtime panic 跨 tokio
///   worker 關機順序不定。`exit(1)` 跑 atexit handler（tracing flush / libc
///   stdio）但不 unwind Rust stack。500ms sleep 給子任務時間接 cancel + 清
///   socket（否則下次啟動 EADDRINUSE）。
pub(crate) async fn init_shared_clients_and_instruments(
    cancel: &CancellationToken,
    live_bindings: &Option<ExchangePipelineBindings>,
    demo_bindings: &Option<ExchangePipelineBindings>,
) -> SharedClientsBundle {
    // 3E-ARCH: Shared REST client = highest-priority exchange pipeline's client.
    // Used by Scanner, InstrumentRefresh, fee refresh tasks.
    // 共享 REST 客戶端 = 最高優先級交易所管線的客戶端。
    let shared_client: Option<Arc<BybitRestClient>> = live_bindings
        .as_ref()
        .map(|b| Arc::clone(&b.rest_client))
        .or_else(|| demo_bindings.as_ref().map(|b| Arc::clone(&b.rest_client)));

    let shared_account_manager: Option<Arc<AccountManager>> = live_bindings
        .as_ref()
        .map(|b| Arc::clone(&b.account_manager))
        .or_else(|| {
            demo_bindings
                .as_ref()
                .map(|b| Arc::clone(&b.account_manager))
        });

    let mut shared_instruments: Option<Arc<InstrumentInfoCache>> = None;

    // R-05 + INSTR-WIRE-1: Load instrument info cache using shared client.
    //
    // INSTR-WIRE-1 (2026-04-23) fail-closed startup:
    //   - Ok(0)          → graceful cancel + exit(1) (universe empty)
    //   - Err(e)         → graceful cancel + exit(1) (exchange unreachable)
    //   - Ok(n) n<100    → warn but continue (health threshold; conservative)
    //   - Ok(n) n>=100   → info
    //
    // INSTR-WIRE-1-GRACEFUL (2026-04-23, E2 review): replaced panic! with
    // cancel.cancel() + tokio::time::sleep(500ms) + std::process::exit(1).
    // Rationale — see module doc header above for the full design rationale;
    // short version: panic! inside async runtime has ambiguous shutdown
    // semantics across tokio workers; explicit cancel + bounded sleep +
    // exit gives predictable IPC-socket cleanup + tracing flush before
    // the supervising process (systemd / restart_all.sh) restarts us.
    //
    // INSTR-WIRE-1 啟動 fail-closed：缺 universe 等於 M-1 全拒單，不如當場
    // 炸掉讓 operator 立即發現，而非假裝跑著實則全啞。
    // 詳細設計 rationale 見 module doc header。
    if let Some(ref client) = shared_client {
        let instrument_cache = Arc::new(InstrumentInfoCache::new());
        match instrument_cache.refresh(&**client, "linear").await {
            Ok(0) => {
                error!(
                    "instrument info startup refresh returned 0 symbols — \
                     fail-closed (refusing to start trading with empty universe) / \
                     啟動拉取合約信息回傳 0 — 空 universe 拒絕啟動交易引擎"
                );
                cancel.cancel();
                // Bounded window (500ms) for child tasks to observe cancel +
                // cleanup IPC socket + tracing flush.
                // 500ms 給子任務時間清理 IPC socket + tracing flush。
                tokio::time::sleep(std::time::Duration::from_millis(500)).await;
                std::process::exit(1);
            }
            Ok(count) if count < 100 => {
                shared_instruments = Some(Arc::clone(&instrument_cache));
                warn!(
                    symbols = count,
                    threshold = 100,
                    "instrument info loaded but count below health threshold \
                     — continuing but expect reduced coverage / \
                     合約信息加載但低於健康門檻，繼續但覆蓋受限"
                );
            }
            Ok(count) => {
                shared_instruments = Some(Arc::clone(&instrument_cache));
                info!(symbols = count, "instrument info loaded / 品種規格已加載");
            }
            Err(e) => {
                error!(
                    error = ?e,
                    "instrument info startup refresh failed — \
                     fail-closed (refusing to start trading without universe) / \
                     啟動拉取合約信息失敗 — 無 universe 拒絕啟動交易引擎"
                );
                cancel.cancel();
                tokio::time::sleep(std::time::Duration::from_millis(500)).await;
                std::process::exit(1);
            }
        }

        // Spawn fee rate refresh + staleness monitor using shared client's account manager.
        if let Some(ref acct) = shared_account_manager {
            tasks::spawn_fee_rate_tasks(acct, client, cancel);
        }
    } else {
        info!(
            "no exchange clients — skipping instrument/fee setup / 無交易所客戶端，跳過品種/費率設定"
        );
    }

    // MAJOR-4: Paper balance uses unified priority.
    // 紙盤餘額統一優先級解析。
    let paper_balance = resolve_paper_initial_balance().await;

    // R-05: Periodic instrument info refresh (every 4 hours)
    if let (Some(ref icache), Some(ref client)) = (&shared_instruments, &shared_client) {
        tasks::spawn_instrument_refresh(icache, client, cancel);
    }

    SharedClientsBundle {
        shared_client,
        shared_account_manager,
        shared_instruments,
        paper_balance,
    }
}
