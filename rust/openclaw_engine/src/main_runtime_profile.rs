//! Persisted engine runtime-profile resolution and public-only lifecycle.

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use openclaw_engine::ws_client::public_only::PublicMarketDataOnlyWsClient;
use openclaw_types::PriceEvent;
use tokio::sync::mpsc;
use tokio::task::{JoinError, JoinSet};
use tokio_util::sync::CancellationToken;

const REQUEST_RELATIVE_PATH: &str = "runtime/engine_runtime_profile.request.json";
const REQUEST_SCHEMA_VERSION: &str = "engine_runtime_profile_request_v1";
const PUBLIC_ONLY_PROFILE: &str = "public_market_data_only_v1";
const REQUEST_WRITER: &str = "tradebot_operator_project_helper_v1";
const MAX_REQUEST_BYTES: u64 = 4096;
const STATUS_FILENAME: &str = "engine_runtime_profile_status.json";

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}

/// Only `Absent` may enter the existing Full engine boot path.
#[derive(Debug)]
pub(crate) enum RuntimeProfileRequestResolution {
    Absent,
    ValidPublicOnly(ResolvedPublicOnlyRequest),
    PresentInvalid(String),
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub(crate) struct RequestFileIdentity {
    dev: u64,
    ino: u64,
    uid: u32,
    mode: u32,
    nlink: u64,
    size_bytes: u64,
    mtime_ns: i128,
    ctime_ns: i128,
    sha256: String,
}

#[derive(Debug)]
pub(crate) struct ResolvedPublicOnlyRequest {
    request_path: PathBuf,
    source_head: String,
    identity: RequestFileIdentity,
}

struct ProfileTelemetry {
    started_at_wall_ms: u64,
    monotonic_origin: Instant,
    last_tick_wall_ms: AtomicU64,
    last_tick_monotonic_ns_plus_one: AtomicU64,
    drained_event_count: AtomicU64,
}

impl ProfileTelemetry {
    fn new() -> Self {
        Self {
            started_at_wall_ms: now_ms(),
            monotonic_origin: Instant::now(),
            last_tick_wall_ms: AtomicU64::new(0),
            last_tick_monotonic_ns_plus_one: AtomicU64::new(0),
            drained_event_count: AtomicU64::new(0),
        }
    }

    fn record_tick(&self) {
        let elapsed_ns = self
            .monotonic_origin
            .elapsed()
            .as_nanos()
            .min(u64::MAX as u128) as u64;
        self.last_tick_monotonic_ns_plus_one
            .store(elapsed_ns.saturating_add(1), Ordering::Release);
        self.drained_event_count.fetch_add(1, Ordering::Relaxed);
        self.last_tick_wall_ms.store(now_ms(), Ordering::Release);
    }

    fn last_tick_monotonic_age_ms(&self) -> Option<u64> {
        let encoded = self.last_tick_monotonic_ns_plus_one.load(Ordering::Acquire);
        if encoded == 0 {
            return None;
        }
        let recorded_ns = encoded - 1;
        let current_ns = self
            .monotonic_origin
            .elapsed()
            .as_nanos()
            .min(u64::MAX as u128) as u64;
        Some(current_ns.saturating_sub(recorded_ns) / 1_000_000)
    }
}

#[derive(Debug, Serialize)]
struct PublicOnlyStatusV1 {
    schema_version: &'static str,
    profile: &'static str,
    build_source_head: String,
    request_path: String,
    request_identity: RequestFileIdentity,
    public_ws_endpoint: &'static str,
    public_ws_topics: &'static [&'static str],
    public_ws_transport_config_immutable: bool,
    started_at_ms: u64,
    observed_at_ms: u64,
    last_tick_wall_clock_ms: Option<u64>,
    last_tick_monotonic_age_ms: Option<u64>,
    drained_event_count: u64,
    private_rest_active: bool,
    private_ws_active: bool,
    auth_watcher_active: bool,
    database_active: bool,
    ipc_active: bool,
    scanner_runner_active: bool,
    execution_pipelines_active: bool,
    order_channels_active: bool,
    decision_lease_authority: bool,
    trading_mutation_authority: bool,
    private_mutation_authority: bool,
}

fn build_status_snapshot(
    request: &ResolvedPublicOnlyRequest,
    telemetry: &ProfileTelemetry,
) -> PublicOnlyStatusV1 {
    let last_tick_wall_ms = telemetry.last_tick_wall_ms.load(Ordering::Acquire);
    PublicOnlyStatusV1 {
        schema_version: "engine_runtime_profile_status_v1",
        profile: PUBLIC_ONLY_PROFILE,
        build_source_head: request.source_head.clone(),
        request_path: request.request_path.display().to_string(),
        request_identity: request.identity.clone(),
        public_ws_endpoint: PublicMarketDataOnlyWsClient::endpoint(),
        public_ws_topics: PublicMarketDataOnlyWsClient::topics(),
        public_ws_transport_config_immutable: true,
        started_at_ms: telemetry.started_at_wall_ms,
        observed_at_ms: now_ms(),
        last_tick_wall_clock_ms: (last_tick_wall_ms != 0).then_some(last_tick_wall_ms),
        last_tick_monotonic_age_ms: (last_tick_wall_ms != 0)
            .then(|| telemetry.last_tick_monotonic_age_ms())
            .flatten(),
        drained_event_count: telemetry.drained_event_count.load(Ordering::Relaxed),
        private_rest_active: false,
        private_ws_active: false,
        auth_watcher_active: false,
        database_active: false,
        ipc_active: false,
        scanner_runner_active: false,
        execution_pipelines_active: false,
        order_channels_active: false,
        decision_lease_authority: false,
        trading_mutation_authority: false,
        private_mutation_authority: false,
    }
}

#[cfg(unix)]
fn openat_file(
    directory_fd: std::os::fd::RawFd,
    name: &std::ffi::CStr,
    flags: libc::c_int,
    mode: libc::mode_t,
) -> std::io::Result<std::fs::File> {
    use std::os::fd::FromRawFd;

    // `O_CREAT | O_EXCL` plus mode 0600 is the descriptor-bound equivalent of
    // `OpenOptions::create_new(true).mode(0o600)`; no temp pathname is resolved.
    let fd = unsafe { libc::openat(directory_fd, name.as_ptr(), flags, mode as libc::c_uint) };
    if fd < 0 {
        return Err(std::io::Error::last_os_error());
    }
    Ok(unsafe { std::fs::File::from_raw_fd(fd) })
}

#[cfg(unix)]
fn renameat_same_directory(
    directory_fd: std::os::fd::RawFd,
    source: &std::ffi::CStr,
    target: &std::ffi::CStr,
) -> std::io::Result<()> {
    let result =
        unsafe { libc::renameat(directory_fd, source.as_ptr(), directory_fd, target.as_ptr()) };
    if result == 0 {
        Ok(())
    } else {
        Err(std::io::Error::last_os_error())
    }
}

#[cfg(unix)]
fn unlinkat_file(directory_fd: std::os::fd::RawFd, name: &std::ffi::CStr) {
    unsafe {
        libc::unlinkat(directory_fd, name.as_ptr(), 0);
    }
}

#[cfg(unix)]
fn persist_status_atomically(data_dir: &Path, status: &PublicOnlyStatusV1) -> Result<(), String> {
    persist_status_atomically_with_hook(data_dir, status, || {})
}

#[cfg(unix)]
fn persist_status_atomically_with_hook<F>(
    data_dir: &Path,
    status: &PublicOnlyStatusV1,
    after_directory_admission: F,
) -> Result<(), String>
where
    F: FnOnce(),
{
    use std::os::fd::AsRawFd;
    use std::os::unix::fs::{MetadataExt, OpenOptionsExt, PermissionsExt};

    let runtime_dir = data_dir.join("runtime");
    let directory = std::fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_DIRECTORY | libc::O_NOFOLLOW | libc::O_CLOEXEC)
        .open(&runtime_dir)
        .map_err(|error| format!("status directory admission open failed: {error}"))?;
    let directory_metadata = directory
        .metadata()
        .map_err(|error| format!("status directory admission fstat failed: {error}"))?;
    let expected_euid = unsafe { libc::geteuid() } as u32;
    if !directory_metadata.is_dir()
        || directory_metadata.uid() != expected_euid
        || directory_metadata.nlink() == 0
    {
        return Err("status directory is not a same-euid linked directory".to_string());
    }
    let expected_directory_dev = directory_metadata.dev();
    let expected_directory_ino = directory_metadata.ino();
    let expected_directory_mode = directory_metadata.permissions().mode() & 0o7777;
    let directory_fd = directory.as_raw_fd();
    after_directory_admission();

    let temp_name = std::ffi::CString::new(format!(
        ".{STATUS_FILENAME}.tmp.{}.{}",
        std::process::id(),
        uuid::Uuid::new_v4()
    ))
    .map_err(|_| "status temp name contains NUL".to_string())?;
    let final_name = std::ffi::CString::new(STATUS_FILENAME)
        .map_err(|_| "status final name contains NUL".to_string())?;
    let bytes =
        serde_json::to_vec(status).map_err(|error| format!("status JSON failed: {error}"))?;
    let result = (|| -> Result<(), String> {
        let mut file = openat_file(
            directory_fd,
            &temp_name,
            libc::O_WRONLY | libc::O_CREAT | libc::O_EXCL | libc::O_NOFOLLOW | libc::O_CLOEXEC,
            0o600,
        )
        .map_err(|error| format!("status temp openat failed: {error}"))?;
        let metadata = file
            .metadata()
            .map_err(|error| format!("status temp fstat failed: {error}"))?;
        if !metadata.is_file()
            || metadata.uid() != expected_euid
            || metadata.nlink() != 1
            || (metadata.permissions().mode() & 0o7777) != 0o600
        {
            return Err("status temp is not same-euid regular single-link exact-0600".to_string());
        }
        let expected_dev = metadata.dev();
        let expected_ino = metadata.ino();
        file.write_all(&bytes)
            .map_err(|error| format!("status write failed: {error}"))?;
        file.sync_all()
            .map_err(|error| format!("status file sync failed: {error}"))?;
        let sealed = file
            .metadata()
            .map_err(|error| format!("status post-write metadata failed: {error}"))?;
        if sealed.dev() != expected_dev
            || sealed.ino() != expected_ino
            || sealed.uid() != expected_euid
            || sealed.nlink() != 1
            || sealed.size() != bytes.len() as u64
            || (sealed.permissions().mode() & 0o7777) != 0o600
        {
            return Err("status temp identity changed during write".to_string());
        }
        drop(file);
        renameat_same_directory(directory_fd, &temp_name, &final_name)
            .map_err(|error| format!("status atomic renameat failed: {error}"))?;
        directory
            .sync_all()
            .map_err(|error| format!("status directory sync failed: {error}"))?;
        let installed_file = openat_file(
            directory_fd,
            &final_name,
            libc::O_RDONLY | libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK | libc::O_NOCTTY,
            0,
        )
        .map_err(|error| format!("status installed openat failed: {error}"))?;
        let installed = installed_file
            .metadata()
            .map_err(|error| format!("status installed fstat failed: {error}"))?;
        if installed.dev() != expected_dev
            || installed.ino() != expected_ino
            || installed.uid() != expected_euid
            || !installed.is_file()
            || installed.nlink() != 1
            || installed.size() != bytes.len() as u64
            || (installed.permissions().mode() & 0o7777) != 0o600
        {
            return Err("status installed identity does not match synced temp".to_string());
        }
        let directory_after = directory
            .metadata()
            .map_err(|error| format!("status directory post-write fstat failed: {error}"))?;
        if !directory_after.is_dir()
            || directory_after.dev() != expected_directory_dev
            || directory_after.ino() != expected_directory_ino
            || directory_after.uid() != expected_euid
            || directory_after.nlink() == 0
            || (directory_after.permissions().mode() & 0o7777) != expected_directory_mode
        {
            return Err(format!(
                "status directory identity changed during persistence: expected dev={expected_directory_dev} ino={expected_directory_ino} uid={expected_euid} linked=true mode={expected_directory_mode:o}, got dev={} ino={} uid={} nlink={} mode={:o}",
                directory_after.dev(),
                directory_after.ino(),
                directory_after.uid(),
                directory_after.nlink(),
                directory_after.permissions().mode() & 0o7777,
            ));
        }
        Ok(())
    })();
    if result.is_err() {
        unlinkat_file(directory_fd, &temp_name);
    }
    result
}

#[cfg(not(unix))]
fn persist_status_atomically(_data_dir: &Path, _status: &PublicOnlyStatusV1) -> Result<(), String> {
    Err("public-only status persistence is unsupported on non-Unix targets".to_string())
}

type StatusWriter = Arc<dyn Fn(&PublicOnlyStatusV1) -> Result<(), String> + Send + Sync>;

#[derive(Debug, Clone, Copy)]
struct LifecycleTiming {
    status_interval: Duration,
    startup_freshness_grace: Duration,
    stale_after: Duration,
    freshness_poll_interval: Duration,
    join_timeout: Duration,
}

impl LifecycleTiming {
    fn production() -> Self {
        Self {
            status_interval: Duration::from_secs(5),
            startup_freshness_grace: Duration::from_secs(90),
            stale_after: Duration::from_secs(90),
            freshness_poll_interval: Duration::from_secs(5),
            join_timeout: Duration::from_secs(10),
        }
    }

    #[cfg(test)]
    fn for_test() -> Self {
        Self {
            status_interval: Duration::from_secs(60),
            startup_freshness_grace: Duration::from_secs(60),
            stale_after: Duration::from_secs(60),
            freshness_poll_interval: Duration::from_secs(60),
            join_timeout: Duration::from_secs(1),
        }
    }
}

#[derive(Debug, PartialEq, Eq)]
struct LifecycleOutcome {
    joined_tasks: usize,
}

#[derive(Debug, PartialEq, Eq)]
struct LifecycleFailure {
    reason: String,
    joined_tasks: usize,
}

impl std::fmt::Display for LifecycleFailure {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{} (joined_tasks={})", self.reason, self.joined_tasks)
    }
}

struct TaskExit {
    name: &'static str,
    result: Result<(), String>,
}

fn record_join_result(
    joined: Result<TaskExit, JoinError>,
    completed_before_cancel: bool,
    errors: &mut Vec<String>,
) {
    match joined {
        Ok(exit) => match exit.result {
            Ok(()) if completed_before_cancel => {
                errors.push(format!("{} task exited unexpectedly", exit.name));
            }
            Ok(()) => {}
            Err(error) => errors.push(format!("{} task failed: {error}", exit.name)),
        },
        Err(error) if error.is_cancelled() && !completed_before_cancel => {}
        Err(error) => errors.push(format!("profile task join failed: {error}")),
    }
}

async fn join_every_profile_task(
    tasks: &mut JoinSet<TaskExit>,
    timing: LifecycleTiming,
    first: Option<Result<TaskExit, JoinError>>,
    first_completed_before_cancel: bool,
) -> (usize, Vec<String>) {
    let mut joined_tasks = 0;
    let mut errors = Vec::new();
    if let Some(first) = first {
        joined_tasks += 1;
        record_join_result(first, first_completed_before_cancel, &mut errors);
    }

    let deadline = tokio::time::Instant::now() + timing.join_timeout;
    while !tasks.is_empty() {
        let remaining = deadline.saturating_duration_since(tokio::time::Instant::now());
        match tokio::time::timeout(remaining, tasks.join_next()).await {
            Ok(Some(joined)) => {
                joined_tasks += 1;
                record_join_result(joined, false, &mut errors);
            }
            Ok(None) => break,
            Err(_) => {
                errors.push("profile task join timeout; remaining tasks aborted".to_string());
                tasks.abort_all();
                while let Some(joined) = tasks.join_next().await {
                    joined_tasks += 1;
                    record_join_result(joined, false, &mut errors);
                }
                break;
            }
        }
    }
    (joined_tasks, errors)
}

async fn drain_public_events(
    mut event_rx: mpsc::Receiver<PriceEvent>,
    telemetry: Arc<ProfileTelemetry>,
    cancel: CancellationToken,
) -> Result<(), String> {
    loop {
        tokio::select! {
            biased;
            _ = cancel.cancelled() => return Ok(()),
            event = event_rx.recv() => match event {
                Some(_event) => telemetry.record_tick(),
                None => return Err("public market-data event channel closed".to_string()),
            },
        }
    }
}

async fn persist_status_periodically(
    request: Arc<ResolvedPublicOnlyRequest>,
    telemetry: Arc<ProfileTelemetry>,
    cancel: CancellationToken,
    timing: LifecycleTiming,
    status_writer: StatusWriter,
) -> Result<(), String> {
    let mut interval = tokio::time::interval(timing.status_interval);
    interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
    interval.tick().await;
    loop {
        tokio::select! {
            biased;
            _ = cancel.cancelled() => return Ok(()),
            _ = interval.tick() => {
                status_writer(&build_status_snapshot(&request, &telemetry))?;
            }
        }
    }
}

async fn enforce_monotonic_freshness(
    telemetry: Arc<ProfileTelemetry>,
    cancel: CancellationToken,
    timing: LifecycleTiming,
) -> Result<(), String> {
    tokio::select! {
        biased;
        _ = cancel.cancelled() => return Ok(()),
        _ = tokio::time::sleep(timing.startup_freshness_grace) => {}
    }
    loop {
        match telemetry.last_tick_monotonic_age_ms() {
            Some(age_ms) if age_ms <= timing.stale_after.as_millis() as u64 => {}
            Some(age_ms) => {
                return Err(format!("public market data stale for {age_ms}ms"));
            }
            None => return Err("no public market data received within startup grace".to_string()),
        }
        tokio::select! {
            biased;
            _ = cancel.cancelled() => return Ok(()),
            _ = tokio::time::sleep(timing.freshness_poll_interval) => {}
        }
    }
}

async fn supervise_public_only_profile<Factory, TransportFuture, SignalFuture>(
    request: ResolvedPublicOnlyRequest,
    transport_factory: Factory,
    signal: SignalFuture,
    timing: LifecycleTiming,
    status_writer: StatusWriter,
) -> Result<LifecycleOutcome, LifecycleFailure>
where
    Factory: FnOnce(mpsc::Sender<PriceEvent>, CancellationToken) -> TransportFuture,
    TransportFuture: std::future::Future<Output = Result<(), String>> + Send + 'static,
    SignalFuture: std::future::Future<Output = Result<(), String>> + Send,
{
    let request = Arc::new(request);
    let telemetry = Arc::new(ProfileTelemetry::new());
    if let Err(reason) = status_writer(&build_status_snapshot(&request, &telemetry)) {
        return Err(LifecycleFailure {
            reason: format!("initial status persistence failed: {reason}"),
            joined_tasks: 0,
        });
    }

    let cancel = CancellationToken::new();
    let (event_tx, event_rx) = mpsc::channel::<PriceEvent>(256);
    let transport = transport_factory(event_tx, cancel.clone());
    let mut tasks = JoinSet::new();
    tasks.spawn(async move {
        TaskExit {
            name: "transport",
            result: transport.await,
        }
    });

    let drain_telemetry = Arc::clone(&telemetry);
    let drain_cancel = cancel.clone();
    tasks.spawn(async move {
        TaskExit {
            name: "drain",
            result: drain_public_events(event_rx, drain_telemetry, drain_cancel).await,
        }
    });

    let status_request = Arc::clone(&request);
    let status_telemetry = Arc::clone(&telemetry);
    let status_cancel = cancel.clone();
    let periodic_writer = Arc::clone(&status_writer);
    tasks.spawn(async move {
        TaskExit {
            name: "status",
            result: persist_status_periodically(
                status_request,
                status_telemetry,
                status_cancel,
                timing,
                periodic_writer,
            )
            .await,
        }
    });

    let freshness_telemetry = Arc::clone(&telemetry);
    let freshness_cancel = cancel.clone();
    tasks.spawn(async move {
        TaskExit {
            name: "freshness",
            result: enforce_monotonic_freshness(freshness_telemetry, freshness_cancel, timing)
                .await,
        }
    });

    tokio::pin!(signal);
    tokio::select! {
        biased;
        first = tasks.join_next() => {
            cancel.cancel();
            let (joined_tasks, errors) = join_every_profile_task(
                &mut tasks,
                timing,
                first,
                true,
            ).await;
            Err(LifecycleFailure {
                reason: errors.join("; "),
                joined_tasks,
            })
        }
        signal_result = &mut signal => {
            cancel.cancel();
            let (joined_tasks, mut errors) = join_every_profile_task(
                &mut tasks,
                timing,
                None,
                false,
            ).await;
            if let Err(error) = signal_result {
                errors.insert(0, format!("signal listener failed: {error}"));
            }
            if errors.is_empty() {
                Ok(LifecycleOutcome { joined_tasks })
            } else {
                Err(LifecycleFailure {
                    reason: errors.join("; "),
                    joined_tasks,
                })
            }
        }
    }
}

#[cfg(unix)]
async fn wait_for_shutdown_signal() -> Result<(), String> {
    let mut terminate = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
        .map_err(|error| format!("SIGTERM listener setup failed: {error}"))?;
    let mut interrupt = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::interrupt())
        .map_err(|error| format!("SIGINT listener setup failed: {error}"))?;
    tokio::select! {
        _ = terminate.recv() => Ok(()),
        _ = interrupt.recv() => Ok(()),
    }
}

#[cfg(not(unix))]
async fn wait_for_shutdown_signal() -> Result<(), String> {
    tokio::signal::ctrl_c()
        .await
        .map_err(|error| format!("interrupt listener failed: {error}"))
}

pub(crate) async fn run_public_only_profile(
    data_dir: &Path,
    request: ResolvedPublicOnlyRequest,
) -> Result<(), String> {
    let status_data_dir = data_dir.to_path_buf();
    let status_writer: StatusWriter =
        Arc::new(move |status| persist_status_atomically(&status_data_dir, status));
    let transport_factory = |event_tx, cancel| async move {
        PublicMarketDataOnlyWsClient::new(event_tx, cancel)
            .run()
            .await
            .map_err(|error| error.to_string())
    };
    supervise_public_only_profile(
        request,
        transport_factory,
        wait_for_shutdown_signal(),
        LifecycleTiming::production(),
        status_writer,
    )
    .await
    .map(|_outcome| ())
    .map_err(|failure| failure.to_string())
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct RuntimeProfileRequestV1 {
    schema_version: String,
    profile: String,
    source_head: String,
    writer: String,
}

#[cfg(unix)]
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct StableFileMetadata {
    dev: u64,
    ino: u64,
    uid: u32,
    mode: u32,
    nlink: u64,
    size_bytes: u64,
    mtime_sec: i64,
    mtime_nsec: i64,
    ctime_sec: i64,
    ctime_nsec: i64,
}

#[cfg(unix)]
fn metadata_snapshot(metadata: &std::fs::Metadata) -> StableFileMetadata {
    use std::os::unix::fs::MetadataExt;

    StableFileMetadata {
        dev: metadata.dev(),
        ino: metadata.ino(),
        uid: metadata.uid(),
        mode: metadata.mode(),
        nlink: metadata.nlink(),
        size_bytes: metadata.size(),
        mtime_sec: metadata.mtime(),
        mtime_nsec: metadata.mtime_nsec(),
        ctime_sec: metadata.ctime(),
        ctime_nsec: metadata.ctime_nsec(),
    }
}

fn invalid(reason: impl Into<String>) -> RuntimeProfileRequestResolution {
    RuntimeProfileRequestResolution::PresentInvalid(reason.into())
}

fn known_source_head(source_head: &str) -> bool {
    source_head.len() == 40
        && source_head
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

/// Resolve the fixed persisted request through one descriptor-bound read.
/// Missing alone returns `Absent`; every present-but-unreadable or invalid
/// state is explicit so callers cannot fail open into the Full engine.
#[cfg(unix)]
pub(crate) fn resolve_runtime_profile_request(
    data_dir: &Path,
    expected_build_source_head: &str,
) -> RuntimeProfileRequestResolution {
    resolve_runtime_profile_request_with_hooks(data_dir, expected_build_source_head, || {}, || {})
}

#[cfg(unix)]
fn resolve_runtime_profile_request_with_hooks<F, G>(
    data_dir: &Path,
    expected_build_source_head: &str,
    after_lstat: F,
    after_read: G,
) -> RuntimeProfileRequestResolution
where
    F: FnOnce(),
    G: FnOnce(),
{
    use std::os::unix::fs::{OpenOptionsExt, PermissionsExt};

    let request_path = data_dir.join(REQUEST_RELATIVE_PATH);
    let path_metadata = match std::fs::symlink_metadata(&request_path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            return RuntimeProfileRequestResolution::Absent;
        }
        Err(error) => return invalid(format!("request metadata unavailable: {error}")),
    };
    let before_path = metadata_snapshot(&path_metadata);
    after_lstat();

    let mut file = match std::fs::OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW | libc::O_CLOEXEC | libc::O_NONBLOCK | libc::O_NOCTTY)
        .open(&request_path)
    {
        Ok(file) => file,
        Err(error) => return invalid(format!("request secure open failed: {error}")),
    };
    let before_read_metadata = match file.metadata() {
        Ok(metadata) => metadata,
        Err(error) => return invalid(format!("request descriptor metadata failed: {error}")),
    };
    let before_read = metadata_snapshot(&before_read_metadata);
    let expected_euid = unsafe { libc::geteuid() } as u32;
    if before_path != before_read {
        return invalid("request changed during descriptor binding");
    }
    if !before_read_metadata.is_file()
        || before_read.uid != expected_euid
        || before_read.nlink != 1
        || (before_read_metadata.permissions().mode() & 0o7777) != 0o600
    {
        return invalid("request must be same-euid regular single-link exact-0600 file");
    }
    if before_read.size_bytes > MAX_REQUEST_BYTES {
        return invalid("request exceeds bounded byte limit");
    }

    let mut raw = Vec::with_capacity(before_read.size_bytes as usize);
    if let Err(error) = (&mut file)
        .take(MAX_REQUEST_BYTES + 1)
        .read_to_end(&mut raw)
    {
        return invalid(format!("request descriptor read failed: {error}"));
    }
    if raw.len() as u64 > MAX_REQUEST_BYTES {
        return invalid("request exceeds bounded byte limit");
    }
    after_read();
    let after_read_metadata = match file.metadata() {
        Ok(metadata) => metadata,
        Err(error) => return invalid(format!("request post-read metadata failed: {error}")),
    };
    let after_read = metadata_snapshot(&after_read_metadata);
    if after_read != before_read {
        return invalid("request descriptor identity changed during read");
    }

    let request: RuntimeProfileRequestV1 = match serde_json::from_slice(&raw) {
        Ok(request) => request,
        Err(error) => return invalid(format!("request JSON invalid: {error}")),
    };
    if request.schema_version != REQUEST_SCHEMA_VERSION {
        return invalid("request schema_version is not exact");
    }
    if request.profile != PUBLIC_ONLY_PROFILE {
        return invalid("request profile is not exact");
    }
    if request.writer != REQUEST_WRITER {
        return invalid("request writer is not exact");
    }
    if !known_source_head(expected_build_source_head)
        || !known_source_head(&request.source_head)
        || request.source_head != expected_build_source_head
    {
        return invalid("request source_head does not match known embedded build head");
    }

    let digest = hex::encode(Sha256::digest(&raw));
    RuntimeProfileRequestResolution::ValidPublicOnly(ResolvedPublicOnlyRequest {
        request_path,
        source_head: request.source_head,
        identity: RequestFileIdentity {
            dev: before_read.dev,
            ino: before_read.ino,
            uid: before_read.uid,
            mode: before_read.mode & 0o7777,
            nlink: before_read.nlink,
            size_bytes: before_read.size_bytes,
            mtime_ns: before_read.mtime_sec as i128 * 1_000_000_000
                + before_read.mtime_nsec as i128,
            ctime_ns: before_read.ctime_sec as i128 * 1_000_000_000
                + before_read.ctime_nsec as i128,
            sha256: digest,
        },
    })
}

#[cfg(not(unix))]
pub(crate) fn resolve_runtime_profile_request(
    data_dir: &Path,
    _expected_build_source_head: &str,
) -> RuntimeProfileRequestResolution {
    if data_dir.join(REQUEST_RELATIVE_PATH).exists() {
        invalid("runtime profile request is unsupported on non-Unix targets")
    } else {
        RuntimeProfileRequestResolution::Absent
    }
}

#[cfg(all(test, unix))]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;

    const TEST_BUILD_HEAD: &str = "0123456789abcdef0123456789abcdef01234567";

    fn request_json(head: &str) -> String {
        format!(
            "{{\"schema_version\":\"engine_runtime_profile_request_v1\",\"profile\":\"public_market_data_only_v1\",\"source_head\":\"{head}\",\"writer\":\"tradebot_operator_project_helper_v1\"}}"
        )
    }

    fn write_valid_request(root: &Path) -> ResolvedPublicOnlyRequest {
        let runtime_dir = root.join("runtime");
        std::fs::create_dir_all(&runtime_dir).expect("runtime dir");
        let request_path = runtime_dir.join("engine_runtime_profile.request.json");
        std::fs::write(&request_path, request_json(TEST_BUILD_HEAD)).expect("request write");
        std::fs::set_permissions(&request_path, std::fs::Permissions::from_mode(0o600))
            .expect("request mode");
        match resolve_runtime_profile_request(root, TEST_BUILD_HEAD) {
            RuntimeProfileRequestResolution::ValidPublicOnly(request) => request,
            other => panic!("expected valid request, got {other:?}"),
        }
    }

    fn write_raw_request(root: &Path, raw: &[u8], mode: u32) -> PathBuf {
        let runtime_dir = root.join("runtime");
        std::fs::create_dir_all(&runtime_dir).expect("runtime dir");
        let request_path = runtime_dir.join("engine_runtime_profile.request.json");
        let _ = std::fs::remove_file(&request_path);
        std::fs::write(&request_path, raw).expect("request write");
        std::fs::set_permissions(&request_path, std::fs::Permissions::from_mode(mode))
            .expect("request mode");
        request_path
    }

    fn assert_present_invalid(root: &Path, expected_head: &str) {
        assert!(matches!(
            resolve_runtime_profile_request(root, expected_head),
            RuntimeProfileRequestResolution::PresentInvalid(_)
        ));
    }

    fn ok_status_writer() -> StatusWriter {
        Arc::new(|_status| Ok(()))
    }

    async fn hold_sender_until_cancel(
        tx: mpsc::Sender<PriceEvent>,
        cancel: CancellationToken,
    ) -> Result<(), String> {
        let _event_sender = tx;
        cancel.cancelled().await;
        Ok(())
    }

    async fn profile_failure<Factory, TransportFuture>(
        transport_factory: Factory,
        timing: LifecycleTiming,
        status_writer: StatusWriter,
    ) -> LifecycleFailure
    where
        Factory: FnOnce(mpsc::Sender<PriceEvent>, CancellationToken) -> TransportFuture,
        TransportFuture: std::future::Future<Output = Result<(), String>> + Send + 'static,
    {
        let root = tempfile::tempdir().expect("temp data dir");
        supervise_public_only_profile(
            write_valid_request(root.path()),
            transport_factory,
            std::future::pending::<Result<(), String>>(),
            timing,
            status_writer,
        )
        .await
        .expect_err("scripted profile failure must be nonzero")
    }

    #[test]
    fn missing_request_is_the_only_absent_state() {
        let root = tempfile::tempdir().expect("temp data dir");
        assert!(matches!(
            resolve_runtime_profile_request(root.path(), TEST_BUILD_HEAD),
            RuntimeProfileRequestResolution::Absent
        ));
    }

    #[test]
    fn strict_request_schema_rejects_duplicates_unknowns_and_nonexact_values() {
        let root = tempfile::tempdir().expect("temp data dir");
        let invalid_payloads = [
            format!(
                "{{\"schema_version\":\"engine_runtime_profile_request_v1\",\"schema_version\":\"engine_runtime_profile_request_v1\",\"profile\":\"public_market_data_only_v1\",\"source_head\":\"{TEST_BUILD_HEAD}\",\"writer\":\"tradebot_operator_project_helper_v1\"}}"
            ),
            format!(
                "{{\"schema_version\":\"engine_runtime_profile_request_v1\",\"profile\":\"public_market_data_only_v1\",\"source_head\":\"{TEST_BUILD_HEAD}\",\"writer\":\"tradebot_operator_project_helper_v1\",\"extra\":true}}"
            ),
            format!(
                "{{\"schema_version\":\"wrong\",\"profile\":\"public_market_data_only_v1\",\"source_head\":\"{TEST_BUILD_HEAD}\",\"writer\":\"tradebot_operator_project_helper_v1\"}}"
            ),
            format!(
                "{{\"schema_version\":\"engine_runtime_profile_request_v1\",\"profile\":\"full\",\"source_head\":\"{TEST_BUILD_HEAD}\",\"writer\":\"tradebot_operator_project_helper_v1\"}}"
            ),
            format!(
                "{{\"schema_version\":\"engine_runtime_profile_request_v1\",\"profile\":\"public_market_data_only_v1\",\"source_head\":\"{TEST_BUILD_HEAD}\",\"writer\":\"unknown\"}}"
            ),
            "{}".to_string(),
        ];
        for raw in invalid_payloads {
            write_raw_request(root.path(), raw.as_bytes(), 0o600);
            assert_present_invalid(root.path(), TEST_BUILD_HEAD);
        }

        let stale_head = "fedcba9876543210fedcba9876543210fedcba98";
        let raw = request_json(stale_head);
        write_raw_request(root.path(), raw.as_bytes(), 0o600);
        assert_present_invalid(root.path(), TEST_BUILD_HEAD);
        assert_present_invalid(root.path(), "unknown");
    }

    #[test]
    fn unsafe_request_files_are_present_invalid_never_absent() {
        use std::os::unix::fs::symlink;

        let root = tempfile::tempdir().expect("temp data dir");
        let valid_raw = request_json(TEST_BUILD_HEAD);

        write_raw_request(root.path(), valid_raw.as_bytes(), 0o644);
        assert_present_invalid(root.path(), TEST_BUILD_HEAD);

        let request_path = write_raw_request(root.path(), valid_raw.as_bytes(), 0o600);
        let second_link = root.path().join("second-link.json");
        std::fs::hard_link(&request_path, &second_link).expect("hard link");
        assert_present_invalid(root.path(), TEST_BUILD_HEAD);
        std::fs::remove_file(&second_link).expect("hard link cleanup");

        let target = root.path().join("target.json");
        std::fs::rename(&request_path, &target).expect("move target");
        symlink(&target, &request_path).expect("request symlink");
        assert_present_invalid(root.path(), TEST_BUILD_HEAD);

        write_raw_request(
            root.path(),
            &vec![b'x'; MAX_REQUEST_BYTES as usize + 1],
            0o600,
        );
        assert_present_invalid(root.path(), TEST_BUILD_HEAD);
    }

    #[test]
    fn request_replacement_between_lstat_and_open_is_present_invalid() {
        let root = tempfile::tempdir().expect("temp data dir");
        let request =
            write_raw_request(root.path(), request_json(TEST_BUILD_HEAD).as_bytes(), 0o600);
        let replacement = root.path().join("replacement.json");
        std::fs::copy(&request, &replacement).expect("replacement copy");
        std::fs::set_permissions(&replacement, std::fs::Permissions::from_mode(0o600))
            .expect("replacement mode");

        let resolution = resolve_runtime_profile_request_with_hooks(
            root.path(),
            TEST_BUILD_HEAD,
            || std::fs::rename(&replacement, &request).expect("replace request"),
            || {},
        );
        assert!(matches!(
            resolution,
            RuntimeProfileRequestResolution::PresentInvalid(_)
        ));
    }

    #[test]
    fn request_metadata_change_during_fd_read_is_present_invalid() {
        let root = tempfile::tempdir().expect("temp data dir");
        let request =
            write_raw_request(root.path(), request_json(TEST_BUILD_HEAD).as_bytes(), 0o600);

        let resolution = resolve_runtime_profile_request_with_hooks(
            root.path(),
            TEST_BUILD_HEAD,
            || {},
            || {
                std::fs::set_permissions(&request, std::fs::Permissions::from_mode(0o400))
                    .expect("mutate request metadata")
            },
        );
        assert!(matches!(
            resolution,
            RuntimeProfileRequestResolution::PresentInvalid(_)
        ));
    }

    #[test]
    fn status_snapshot_is_atomic_owner_only_and_denies_every_trading_surface() {
        let root = tempfile::tempdir().expect("temp data dir");
        let request = write_valid_request(root.path());
        let runtime_dir = root.path().join("runtime");
        let telemetry = ProfileTelemetry::new();
        let status = build_status_snapshot(&request, &telemetry);

        persist_status_atomically(root.path(), &status).expect("status persist");

        let status_path = runtime_dir.join("engine_runtime_profile_status.json");
        let metadata = std::fs::metadata(&status_path).expect("status metadata");
        assert_eq!(metadata.permissions().mode() & 0o7777, 0o600);
        let persisted: serde_json::Value =
            serde_json::from_slice(&std::fs::read(&status_path).expect("status read"))
                .expect("status json");
        assert_eq!(persisted["profile"], PUBLIC_ONLY_PROFILE);
        let denied = persisted
            .as_object()
            .expect("status object")
            .iter()
            .filter(|(field, _)| field.ends_with("_active") || field.ends_with("_authority"));
        assert_eq!(denied.count(), 11);
        assert!(persisted
            .as_object()
            .unwrap()
            .iter()
            .filter(|(field, _)| field.ends_with("_active") || field.ends_with("_authority"),)
            .all(|(_, value)| value == false));
    }

    #[test]
    fn status_writer_rejects_symlinked_runtime_dir_without_external_mutation() {
        use std::os::unix::fs::symlink;

        let source = tempfile::tempdir().expect("status source data dir");
        let request = write_valid_request(source.path());
        let status = build_status_snapshot(&request, &ProfileTelemetry::new());
        let root = tempfile::tempdir().expect("target data dir");
        let external = tempfile::tempdir().expect("external decoy dir");
        let sentinel = external.path().join("sentinel.txt");
        std::fs::write(&sentinel, b"must remain byte-identical").expect("sentinel write");
        symlink(external.path(), root.path().join("runtime")).expect("runtime symlink");

        let result = persist_status_atomically(root.path(), &status);

        assert!(
            result.is_err(),
            "symlinked runtime directory must fail closed"
        );
        assert_eq!(
            std::fs::read(&sentinel).expect("sentinel read"),
            b"must remain byte-identical"
        );
        let mut external_entries = std::fs::read_dir(external.path())
            .expect("external dir read")
            .map(|entry| entry.expect("external entry").file_name())
            .collect::<Vec<_>>();
        external_entries.sort();
        assert_eq!(
            external_entries,
            vec![std::ffi::OsString::from("sentinel.txt")]
        );
    }

    #[test]
    fn status_writer_remains_bound_to_admitted_dirfd_across_runtime_path_swap() {
        use std::os::unix::fs::symlink;

        let root = tempfile::tempdir().expect("target data dir");
        let request = write_valid_request(root.path());
        let status = build_status_snapshot(&request, &ProfileTelemetry::new());
        let admitted_path = root.path().join("runtime");
        let held_admitted_path = root.path().join("runtime-admitted");
        let decoy = tempfile::tempdir().expect("replacement decoy dir");
        let sentinel = decoy.path().join("sentinel.txt");
        std::fs::write(&sentinel, b"must remain byte-identical").expect("sentinel write");

        persist_status_atomically_with_hook(root.path(), &status, || {
            std::fs::rename(&admitted_path, &held_admitted_path)
                .expect("move admitted directory after dirfd binding");
            symlink(decoy.path(), &admitted_path).expect("install runtime replacement symlink");
        })
        .expect("dirfd-bound persistence must survive path replacement");

        assert!(held_admitted_path.join(STATUS_FILENAME).is_file());
        assert!(std::fs::symlink_metadata(&admitted_path)
            .expect("replacement metadata")
            .file_type()
            .is_symlink());
        assert_eq!(
            std::fs::read(&sentinel).expect("sentinel read"),
            b"must remain byte-identical"
        );
        let mut decoy_entries = std::fs::read_dir(decoy.path())
            .expect("decoy dir read")
            .map(|entry| entry.expect("decoy entry").file_name())
            .collect::<Vec<_>>();
        decoy_entries.sort();
        assert_eq!(
            decoy_entries,
            vec![std::ffi::OsString::from("sentinel.txt")]
        );
    }

    #[test]
    fn status_writer_cleans_relative_temp_after_rename_failure() {
        let root = tempfile::tempdir().expect("target data dir");
        let request = write_valid_request(root.path());
        let status = build_status_snapshot(&request, &ProfileTelemetry::new());
        let runtime_dir = root.path().join("runtime");
        let final_path = runtime_dir.join(STATUS_FILENAME);
        std::fs::create_dir(&final_path).expect("blocking final directory");

        let result = persist_status_atomically(root.path(), &status);

        assert!(result.is_err(), "rename over a directory must fail closed");
        assert!(final_path.is_dir(), "existing final directory must remain");
        let leftover_temps = std::fs::read_dir(&runtime_dir)
            .expect("runtime dir read")
            .map(|entry| entry.expect("runtime entry").file_name())
            .filter(|name| {
                name.to_string_lossy()
                    .starts_with(&format!(".{STATUS_FILENAME}.tmp."))
            })
            .collect::<Vec<_>>();
        assert!(
            leftover_temps.is_empty(),
            "temp cleanup must be dirfd-relative"
        );
    }

    #[tokio::test]
    async fn signal_cancels_and_joins_all_four_profile_tasks_with_success() {
        let root = tempfile::tempdir().expect("temp data dir");
        let request = write_valid_request(root.path());
        let transport_joined = Arc::new(std::sync::atomic::AtomicBool::new(false));
        let marker = Arc::clone(&transport_joined);
        let transport_factory = move |_tx, cancel: CancellationToken| async move {
            cancel.cancelled().await;
            marker.store(true, Ordering::Release);
            Ok(())
        };
        let status_writer = ok_status_writer();

        let outcome = supervise_public_only_profile(
            request,
            transport_factory,
            std::future::ready(Ok(())),
            LifecycleTiming::for_test(),
            status_writer,
        )
        .await
        .expect("signal is a successful disposition");

        assert_eq!(outcome.joined_tasks, 4);
        assert!(transport_joined.load(Ordering::Acquire));
    }

    #[tokio::test]
    async fn transport_failure_cancels_and_joins_all_four_profile_tasks() {
        let failure = profile_failure(
            |_tx, _cancel| async { Err("scripted transport failure".to_string()) },
            LifecycleTiming::for_test(),
            ok_status_writer(),
        )
        .await;
        assert_eq!(failure.joined_tasks, 4);
        assert!(failure.reason.contains("scripted transport failure"));
    }

    #[tokio::test]
    async fn drain_failure_cancels_and_joins_all_four_profile_tasks() {
        let failure = profile_failure(
            |tx, cancel| async move {
                drop(tx);
                cancel.cancelled().await;
                Ok(())
            },
            LifecycleTiming::for_test(),
            ok_status_writer(),
        )
        .await;
        assert_eq!(failure.joined_tasks, 4);
        assert!(failure.reason.contains("event channel closed"));
    }

    #[tokio::test]
    async fn initial_status_failure_starts_no_profile_tasks() {
        let status_writer: StatusWriter =
            Arc::new(|_status| Err("scripted initial status failure".to_string()));
        let failure = profile_failure(
            hold_sender_until_cancel,
            LifecycleTiming::for_test(),
            status_writer,
        )
        .await;
        assert_eq!(failure.joined_tasks, 0);
        assert!(failure.reason.contains("initial status persistence failed"));
    }

    #[tokio::test]
    async fn periodic_status_failure_cancels_and_joins_all_four_profile_tasks() {
        let writes = Arc::new(AtomicU64::new(0));
        let writes_for_sink = Arc::clone(&writes);
        let status_writer: StatusWriter = Arc::new(move |_status| {
            if writes_for_sink.fetch_add(1, Ordering::AcqRel) == 0 {
                Ok(())
            } else {
                Err("scripted periodic status failure".to_string())
            }
        });
        let timing = LifecycleTiming {
            status_interval: Duration::from_millis(1),
            ..LifecycleTiming::for_test()
        };
        let failure = profile_failure(hold_sender_until_cancel, timing, status_writer).await;
        assert_eq!(failure.joined_tasks, 4);
        assert!(
            failure.reason.contains("scripted periodic status failure"),
            "unexpected failure: {}",
            failure.reason
        );
        assert!(writes.load(Ordering::Acquire) >= 2);
    }

    #[tokio::test]
    async fn startup_staleness_cancels_and_joins_all_four_profile_tasks() {
        let timing = LifecycleTiming {
            startup_freshness_grace: Duration::from_millis(5),
            stale_after: Duration::from_millis(5),
            freshness_poll_interval: Duration::from_millis(1),
            ..LifecycleTiming::for_test()
        };
        let failure = profile_failure(hold_sender_until_cancel, timing, ok_status_writer()).await;
        assert_eq!(failure.joined_tasks, 4);
        assert!(failure.reason.contains("startup grace"));
    }

    #[tokio::test]
    async fn monotonic_tick_staleness_cancels_and_joins_all_four_profile_tasks() {
        let timing = LifecycleTiming {
            startup_freshness_grace: Duration::from_millis(2),
            stale_after: Duration::from_millis(5),
            freshness_poll_interval: Duration::from_millis(1),
            ..LifecycleTiming::for_test()
        };
        let failure = profile_failure(
            |tx, cancel| async move {
                tx.send(PriceEvent::new("BTCUSDT".to_string(), 1.0, 1))
                    .await
                    .map_err(|_| "scripted event send failed".to_string())?;
                cancel.cancelled().await;
                Ok(())
            },
            timing,
            ok_status_writer(),
        )
        .await;
        assert_eq!(failure.joined_tasks, 4);
        assert!(failure.reason.contains("public market data stale for"));
    }
}
