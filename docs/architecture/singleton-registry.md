# OpenClaw Mutable Singleton Registry

Date: 2026-05-23
Status: Active — Singleton Registry SSOT (NEW location post 2026-05-02 CLAUDE.md trim)
Authority Source:
- `CLAUDE.md` §七 "New mutable singletons must be registered in the singleton table's current authority location before merge"
- `CLAUDE.md` §九 "New mutable singletons must be registered in the current singleton authority before merge"
- Sprint 4+ Wave B E2 round 2 MEDIUM-1 escalate (2026-05-23) — PA SSOT establishment finding

Cross-references:
- `docs/archive/2026-05-02--CLAUDE-pre-trim-snapshot.md` §九 Singleton 表（pre-trim 完整快照；Python H_STATE_INVALIDATOR / MARKET_SCANNER / HStateCacheSlot / CostEdgeAdvisorDbSlot 4 條尚未 re-ingest 進本 SSOT — 見 §6 carry-over）
- `docs/architecture/DATA_STORAGE_ARCHITECTURE_V1.md`（同類 ongoing inventory pattern）
- ADR-0042 M3 Health Monitoring（Wave A/B 6 singleton 治理 source）
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_pm_phase_3e_signoff.md` §4.1（Sprint 4+ Wave B 派發來源）

---

## §1 Purpose

本 doc = OpenClaw 全項目 mutable singleton 登記表 SSOT。CLAUDE.md §七 + §九 兩條 rule 規定「新 mutable singletons 合併前必登記在 singleton table 當前權威位置」；2026-05-02 CLAUDE.md trim 期間原 §九 inline table 被 archive 但未搬到新位置，造成 governance gap（pre-trim snapshot 仍存於 `docs/archive/2026-05-02--CLAUDE-pre-trim-snapshot.md` 但不再是 active SSOT）。本 doc 是 trim 後新權威位置。

### §1.1 範圍邊界（in scope）

- **In scope**：Rust `openclaw_engine` + Python `control_api_v1` 內 process-global 可變狀態（module-level `static`、`Arc<Mutex<...>>`、`Arc<RwLock<...>>`、`Arc<broadcast::Sender<...>>`、Python 模組級可變 binding 等）。
- **In scope**：跨 thread / 跨 tokio task 共享的可變 state container（多 task 並發 read-write 必需鎖或 channel）。

### §1.2 不屬本表範圍（out of scope）

- 純 function（無 mutable state，如 `is_live_release_profile()` / `table_present()`）。
- module-private sentinel `object()`（純 identity comparison，無 mutable state；如 strategist_singleton_pollution_fix_review 2026-04-28 確認）。
- struct-internal `Arc`（caller 端 own / inject pattern；非 process-global）。
- 編譯期常數 / `const` / `pub const`（如 `HEALTH_EVENT_CHANNEL_CAPACITY: usize = 256`）。
- 純 caller-injected 但全進程只構造一次的 `Arc<dyn ...>` trait object（除非該物件本身含 mutable state）。

### §1.3 登記欄位定義

對每 singleton 必登：

| 欄位 | 說明 |
|---|---|
| name | Singleton type / binding 名稱（精確 case） |
| type_signature | 完整 type signature（含 Arc / Mutex / 容器） |
| location | `file:line` 定義位置（struct/binding decl）；Rust 採 absolute repo-relative path |
| owner_lifecycle | 構造端 / 銷毀端（engine boot / engine shutdown / supervisor scope） |
| cross_task_pattern | 跨 task / thread 訪問 pattern（hot path push / scheduled emit / cascade subscribe …） |
| lock_primitive | std::sync::Mutex / parking_lot::Mutex / RwLock / tokio::broadcast / AtomicXxx 等 |
| visibility | `pub` / `pub(crate)` / `pub(super)` / private |
| caller_chain | 生產調用端列表（callsite file:line） |
| health_monitoring | 是否被 M3 health emitter 觀測（per ADR-0042 6 domain） |
| registered_date | 進本 SSOT 日期 |
| governance_authority | 所屬 ADR / spec / amend 來源 |
| migration_plan | 是否計劃改造（Sprint 5+ 升級 / 替換 / 拆分） |

---

## §2 Registered Singletons（active）

### §2.1 Sprint 4+ Wave A — Bybit Instrumentation（PA-DRIFT-4 IMPL closure 2026-05-23）

per Sprint 4+ first Live carry-over §4.1 item 3（PA-DRIFT-4 bybit_rest_client + bybit_private_ws instrumentation 補位）；commit chain 5acd36e6 + 4c84d1bb；Sprint 4+ Wave B 接線 commit 245216d1 + 4d4ff99f。

#### 2.1.1 RestLatencyHistogram

| 欄位 | 值 |
|---|---|
| name | `RestLatencyHistogram` |
| type_signature | `pub struct { samples: std::sync::Mutex<Vec<(Instant, u64)>> }` |
| location | `rust/openclaw_engine/src/bybit_rest_client.rs:335-339` |
| owner_lifecycle | `BybitRestClient::new()` 構造（rust/openclaw_engine/src/bybit_rest_client.rs:978）；engine shutdown 隨 Arc drop |
| cross_task_pattern | REST hot path 多 task 並發 `record_latency()` push；emitter 端 `RealApiLatencySourceProbe::current_rest_latency_*_60s_window()` 同步 read（60s sample 一次） |
| lock_primitive | `std::sync::Mutex<Vec<(Instant, u64)>>`；cap 8192；60s rolling window |
| visibility | `pub`（含 `#[doc(hidden)]` `inject_sample_with_timestamp` test helper） |
| caller_chain | producer: `BybitRestClient::request_with_retry()` REST hot path（get/post 路徑 record_latency 呼叫）；consumer: `RealApiLatencySourceProbe` Track D emitter probe；handle exposer: `BybitRestClient::latency_histogram_handle()`（rust/openclaw_engine/src/bybit_rest_client.rs:989） |
| health_monitoring | YES — ADR-0042 Decision 3 `api_latency` domain；V106 row `api_latency__rest_p50_ms` / `__rest_p95_ms` / `__rest_p99_ms` |
| registered_date | 2026-05-23 |
| governance_authority | ADR-0042 M3 Health Monitoring + PA-DRIFT-4 carry-over Sprint 2 §4.1 |
| migration_plan | 0 — Sprint 4+ first Live 標準配置；無計劃改造 |

#### 2.1.2 RetCodeCounter

| 欄位 | 值 |
|---|---|
| name | `RetCodeCounter` |
| type_signature | `pub struct { samples_4xx: std::sync::Mutex<Vec<Instant>>, samples_5xx: std::sync::Mutex<Vec<Instant>> }` |
| location | `rust/openclaw_engine/src/bybit_rest_client.rs:479-484` |
| owner_lifecycle | `BybitRestClient::new()` 構造（rust/openclaw_engine/src/bybit_rest_client.rs:979）；engine shutdown 隨 Arc drop |
| cross_task_pattern | REST 業務錯誤 hot path push（4xx client fault / 5xx venue fault 雙桶）；emitter probe 端 60s sample read |
| lock_primitive | 雙 `std::sync::Mutex<Vec<Instant>>`；cap 8192；60s rolling window |
| visibility | `pub` |
| caller_chain | producer: `BybitRestClient::request_with_retry()` 業務錯誤分類 `BybitApiError::Business` retCode 對映 4xx/5xx；consumer: `RealApiLatencySourceProbe` Track D emitter probe；handle exposer: `BybitRestClient::ret_code_counter_handle()`（rust/openclaw_engine/src/bybit_rest_client.rs:994） |
| health_monitoring | YES — ADR-0042 Decision 3 `api_latency` domain；V106 row `api_latency__ret_4xx_count` / `__ret_5xx_count` |
| registered_date | 2026-05-23 |
| governance_authority | ADR-0042 + PA-DRIFT-4 carry-over + ADR-0040 multi-venue gate 預留（4xx/5xx 分桶為 multi-venue 共通 transport-level 語意） |
| migration_plan | 0 — multi-venue 預埋；無近期改造計劃 |

#### 2.1.3 WsRttHistogram

| 欄位 | 值 |
|---|---|
| name | `WsRttHistogram` |
| type_signature | `pub struct { samples: std::sync::Mutex<Vec<(Instant, u64)>> }` |
| location | `rust/openclaw_engine/src/bybit_private_ws.rs:102-105` |
| owner_lifecycle | `BybitPrivateWs::new()` 內部構造（rust/openclaw_engine/src/bybit_private_ws.rs:564）；每次 supervisor reconnect attempt 新 Arc；engine shutdown 隨 supervisor 終結 drop |
| cross_task_pattern | WS main loop `"op":"pong"` 接收端 `record_rtt()` push；emitter probe 端 60s sample read（per Wave B status: production 端尚未透過外部 Arc 注入接通；本 round Wave B 走 placeholder fresh 0-state Arc — 見 §2.1.3.a） |
| lock_primitive | `std::sync::Mutex<Vec<(Instant, u64)>>`；cap 64（60s × 1 ping/20s ≈ 3 sample 上限預留 headroom） |
| visibility | `pub`（含 `#[doc(hidden)]` `inject_sample_with_timestamp` test helper） |
| caller_chain | producer: `BybitPrivateWs::run()` main loop pong handler；handle exposer: `BybitPrivateWs::rtt_histogram_handle()`（rust/openclaw_engine/src/bybit_private_ws.rs:577-585，Wave A 已實裝但 main_health_emitters.rs Wave B placeholder 未接） |
| health_monitoring | YES — V106 row `api_latency__ws_rtt_p50_ms` / `__ws_rtt_p99_ms`；BUT Wave B 階段 emit chain placeholder disconnected from production supervisor（見 §2.1.3.a） |
| registered_date | 2026-05-23 |
| governance_authority | ADR-0042 + PA-DRIFT-4 carry-over |
| migration_plan | Sprint 5+ Wave C：BybitPrivateWs supervisor signature 改造為「caller 注入 external Arc」pattern；main.rs Wave 接時拿 supervisor handle clone 替換 placeholder fresh Arc（per `rust/openclaw_engine/src/main_health_emitters.rs:174-205` 誠實揭露） |

##### §2.1.3.a Wave B placeholder 半實裝陷阱

per main_health_emitters.rs:206-220 + module note line 174-205（PA-DRIFT-4 round 2 MEDIUM-2 fix 揭露）：

- bybit_private_ws.rs:577-585 Wave A 已實裝 `rtt_histogram_handle()` expose accessor
- 但 main_health_emitters.rs:218-219 `build_real_api_latency_probe` 不呼叫 expose；每次走 `Arc::new(WsRttHistogram::new())` 0-state instance
- 後果：V106 `api_latency__ws_rtt_*` 30 天「全 0」染色不代表「WS 健康無 latency」，而是 emit chain 從 production supervisor disconnect
- Wave B 走 (a) doc 補注 + Sprint 5+ carry-over；本 round 不接 supervisor handle（needs `BybitPrivateWs::new()` signature 改造）

#### 2.1.4 WsDropoutCounter

| 欄位 | 值 |
|---|---|
| name | `WsDropoutCounter` |
| type_signature | `pub struct { samples: std::sync::Mutex<Vec<Instant>> }` |
| location | `rust/openclaw_engine/src/bybit_private_ws.rs:216-218` |
| owner_lifecycle | `BybitPrivateWs::new()` 內部構造（同 WsRttHistogram pattern）；每次 supervisor reconnect attempt 新 Arc |
| cross_task_pattern | WS run loop 6 接點 `record_dropout()` push（panic / disconnect / cancel 入口進 reconnect）；emitter probe 端 60s sample read（Wave B placeholder fresh Arc - 見 §2.1.4.a） |
| lock_primitive | `std::sync::Mutex<Vec<Instant>>`；cap 256；60s rolling window |
| visibility | `pub` |
| caller_chain | producer: `BybitPrivateWs::run()` 6 reconnect 入口；handle exposer: `BybitPrivateWs::dropout_counter_handle()`（rust/openclaw_engine/src/bybit_private_ws.rs:577-585，Wave A 已實裝但 main_health_emitters.rs Wave B placeholder 未接） |
| health_monitoring | YES — V106 row `api_latency__ws_dropout_count`；BUT Wave B 同 §2.1.3.a placeholder 半實裝 |
| registered_date | 2026-05-23 |
| governance_authority | ADR-0042 Decision 3 cascade gate 預警（dropout > 5 / 60s 升 CRITICAL）+ PA-DRIFT-4 carry-over |
| migration_plan | Sprint 5+ Wave C 同 WsRttHistogram supervisor handle 改造（見 §2.1.4.a） |

##### §2.1.4.a Wave B placeholder 半實裝陷阱

同 §2.1.3.a；30 天 V106 `api_latency__ws_dropout_count` 全 0 是 emit chain disconnect 副作用，非 production WS 健康指標反映「無 dropout」。

### §2.2 Sprint 4+ Wave B — Health Emitter Cache + Bus（2026-05-23 接線完成）

per Sprint 4+ Wave B IMPL（commit 245216d1 + 4d4ff99f + 82351b61），main.rs scheduler wire-up 完整接線。

#### 2.2.1 PortfolioStateCache

| 欄位 | 值 |
|---|---|
| name | `PortfolioStateCache` |
| type_signature | 包在 `Arc<parking_lot::Mutex<PortfolioStateCache>>`；內部 `{ realized_pnl_history: VecDeque<(u64, f64)>, equity_history: VecDeque<(u64, f64)>, latest_exposures: Vec<PositionExposure>, last_update_ts_ms: u64 }` |
| location | `rust/openclaw_engine/src/health/domains/risk_envelope_probe_impl.rs:129-141` |
| owner_lifecycle | `build_risk_envelope_emitter()` 內 `Arc::new(ParkingMutex::new(PortfolioStateCache::new()))` 構造（rust/openclaw_engine/src/main_health_emitters.rs:326）；返 cache handle 給 `spawn_metric_emitter_scheduler` caller；engine shutdown 隨 Arc drop |
| cross_task_pattern | producer: 300s tick task `spawn_portfolio_state_update_task` 呼 `update_from_pipeline_snapshot`（push fill realized_pnl + equity + position notional）；consumer: `RealRiskEnvelopeSourceProbe::sample_now()` 端 emitter 300s sample read 5 calculator |
| lock_primitive | `parking_lot::Mutex<PortfolioStateCache>`；lock 時段 < 1ms（5 calculator 純讀）；不走 tokio::sync::Mutex（cache update task 是 sync block；avoid await-on-lock pattern） |
| visibility | `pub`（PositionExposure / new / update_from_pipeline_snapshot / cum_pnl_24h_usd / max_dd_pct_24h / position_count_active / correlation_avg_pairwise / concentration_top1_pct） |
| caller_chain | producer: `spawn_portfolio_state_update_task`（rust/openclaw_engine/src/main_health_emitters.rs ~line 519，目前 Wave B placeholder no-op tick；Wave C / Sprint 5+ 接 PaperState SSOT）；consumer: `RealRiskEnvelopeSourceProbe::{current_portfolio_cum_pnl_24h_usd, current_portfolio_max_dd_pct, current_position_count_active, current_correlation_avg_pairwise, current_concentration_top1_pct}` |
| health_monitoring | YES — ADR-0042 Decision 3 `risk_envelope` domain；V106 row `risk_envelope__cum_pnl_24h_usd` / `__max_dd_pct` / `__position_count_active` / `__correlation_avg_pairwise` / `__concentration_top1_pct` |
| registered_date | 2026-05-23 |
| governance_authority | ADR-0042 + Sprint 2 Wave 2 Track F + PA-DRIFT-5 carry-over Sprint 2 §4.1 item 4 |
| migration_plan | Sprint 5+ Wave C：update task no-op → 接 PaperState SSOT；correlation calculator 接既有 `crate::scanner::scorer` correlation lookup 或新 rolling-window calculator（per risk_envelope_probe_impl.rs:101-105 doc）；可能加顯式 cap follow-up（per file line 113-128 burst 防禦留 caller throttle） |

##### §2.2.1.a F-2 NaN/inf sanitize（PA-DRIFT-5 round 2 P1）

cache update 端 `update_from_pipeline_snapshot` 對 NaN/inf realized_pnl / equity / notional fail-loud warn + skip push（rust/openclaw_engine/src/health/domains/risk_envelope_probe_impl.rs:201/217/235）；避 NaN 污染 24h sliding window sum 破壞 emitter classify ladder。

##### §2.2.1.b 三 mode (live/demo/paper) 共享 vs 獨立

per main_health_emitters.rs:305-316 — Wave B 採「engine-wide single cache」；既有 risk_verdict_ledger / position_snapshot 計算端是 per-engine 獨立但 emitter `risk_envelope__*` 共用 anomaly_id space（per spec §6.2）；Sprint 5+ PM 若拍板獨立 cache，本 fn 構造可加 mode 參數並各自 spawn update task。

#### 2.2.2 HealthEventBus

| 欄位 | 值 |
|---|---|
| name | `HealthEventBus` |
| type_signature | `pub struct { sender: tokio::sync::broadcast::Sender<HealthStateChangeEvent> }` |
| location | `rust/openclaw_engine/src/health/event_bus.rs:80-82` |
| owner_lifecycle | `spawn_metric_emitter_scheduler` 內 `Arc::new(HealthEventBus::new())` 構造（rust/openclaw_engine/src/main_health_emitters.rs:394）；返 event_bus handle 給 caller；engine shutdown 隨 Arc drop |
| cross_task_pattern | producer: M3 emitter scheduler / 6 DomainEmitter 內部 state transition fire `publish(event)`；consumer: Sprint 5 cascade subscriber（LAL Tier 降階 / Strategy reparam halt / alert routing；本 round 0 subscriber） |
| lock_primitive | `tokio::sync::broadcast::Sender` + capacity 256（per `HEALTH_EVENT_CHANNEL_CAPACITY`）；fail-soft publish — channel lagged 不算 fire fail（per spec §4.1 註） |
| visibility | `pub`（HealthStateChangeEvent / HealthEventBus / HealthEventSubscriber / new / with_capacity / publish / subscribe / receiver_count） |
| caller_chain | producer: M3 emitter 6 DomainEmitter `observe_classified` state transition 後 `publish`（per spec §4.1 step 5）；consumer: 本 round 0 production subscriber，仍 reserve subscribe interface 預埋 Sprint 5 cascade IMPL |
| health_monitoring | NO — bus 自身非 metric target；發布的 event 載荷是 6 domain transition（per HealthStateChangeEvent `domain` field 對應 ADR-0042 Decision 3 6 domain） |
| registered_date | 2026-05-23 |
| governance_authority | ADR-0042 Decision 5（cascade subscriber 上限 8） + Sprint 2 Wave 1 Track A scaffold + spec §4.1 + §3.1 step 5 |
| migration_plan | Sprint 5+ cascade IMPL：接 4-8 subscriber（LAL Tier / Strategy halt / Alert router / GUI）；per ADR-0042 Decision 5；本 round 不接 cross-process channel；Sprint 5 才接 |

### §2.3 GUI Bybit-first PnL — Python closed-PnL cache（2026-05-23）

per GUI Bybit-first PnL refactor Phase 2；backend-only endpoint `/api/v1/strategy/demo/closed-pnl` 用 Bybit REST 讀取後做 PG strategy reconcile，不寫 `trading.fills`。

#### 2.3.1 `_CLOSED_PNL_CACHE`

| 欄位 | 值 |
|---|---|
| name | `_CLOSED_PNL_CACHE` |
| type_signature | `app.bybit_pnl_cache.ClosedPnlCache | None`；內部 `{ _entries: dict[Hashable, _CacheEntry], _inflight: set[Hashable], _lock: threading.RLock, _ready: threading.Condition }` |
| location | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/strategy_ai_routes.py:32` binding；implementation `app/bybit_pnl_cache.py` |
| owner_lifecycle | `strategy_ai_routes._closed_pnl_cache()` lazy 構造；每個 uvicorn worker process-local；API worker exit 時 drop |
| cross_task_pattern | producer: `/demo/closed-pnl` cache miss 執行 Bybit `GET /v5/position/closed-pnl` 後 put；consumer: 同 endpoint cache hit / stale-cache degraded path；in-flight set 讓同 worker 同 key 只打一個 Bybit request |
| lock_primitive | `threading.RLock` + `threading.Condition`；TTL 8s；不跨 process 去重 |
| visibility | private module binding；route helper 間接使用 |
| caller_chain | producer/consumer: `strategy_ai_routes.get_demo_closed_pnl()`；Bybit read method: `bybit_rest_client.BybitClient.get_closed_pnl()`；PG reconcile/fallback 為 read-only SELECT `trading.fills` |
| health_monitoring | NO — GUI read cache；失敗以 route `source/degraded_reason/cache_age` 暴露，無 M3 health row |
| registered_date | 2026-05-23 |
| governance_authority | `docs/CCAgentWorkSpace/PM/workspace/reports/2026-05-23--gui_bybit_first_pnl_refactor_acceptance.md` + operator Q1/Q2/Q3 = A/A/A |
| migration_plan | 0 for current Phase 2；若未來多 worker 需要 cross-process cache，再另開 Redis/IPC design，不在本 scope |

---

### §2.4 Notification Fail-Safe Wire — Rust（C4 pipeline wire 2026-05-29，incident trigger 2026-05-31）

per `P2-PACKET-C-C4-PIPELINE-WIRE` + `P2-INCIDENT-POLICY-DISPATCH-TRIGGER`；把自主通知 fail-safe（AMD-2026-05-21-01 v2）接進 runtime。C4 watcher 仍是唯一 timer / SM-04 Defensive path；incident trigger 只餵 dispatch outcome。

#### 2.4.1 `SHARED_WATCHER`

| 欄位 | 值 |
|---|---|
| name | `SHARED_WATCHER`（`SharedFailsafeWatcher`）|
| type_signature | `OnceLock<SharedFailsafeWatcher>`；內部單一 timer state（`timer_armed_at_ms` + `escalated_for_current_arm`）|
| location | `rust/openclaw_engine/src/notification_failsafe/providers/single_watcher.rs`；`SharedFailsafeWatcher::init` boot 單點 |
| owner_lifecycle | `spawn_notification_failsafe_watcher`（`tasks.rs`）boot 構造一次，唯一 caller `main_boot_tasks.rs`（緊接 reconciler spawn）；engine process 生命週期；cancel token cascade 退出 |
| cross_task_pattern | producer: `incident_policy` 經 outcome feed `observe_dispatch(AllFail)` 武裝 timer；consumer: watcher select! loop `timer_expired_and_claim()`（claim-before-await，恰一次）→ 對 demo/live slot 發 `PipelineCommand::NotificationFailsafeEscalate` → owner task SM-04 transition |
| lock_primitive | 內部 `Mutex` guarded state；claim 在同一 lock hold 內判 + set，並發 idempotent |
| visibility | crate-internal；watcher loop 專用 |
| caller_chain | spawn: `tasks.rs::spawn_notification_failsafe_watcher`；escalate handler: `event_consumer/handlers/risk.rs::handle_notification_failsafe_escalate` |
| health_monitoring | NO（producer coverage 擴完後再評估 M3 emit）|
| registered_date | 2026-05-29 |
| governance_authority | spec `docs/execution_plan/specs/2026-05-29--packet-c-c4-pipeline-wire-spec.md` + E2 APPROVE-WITH-CONDITIONS C2 + QA ACCEPT C2 |
| migration_plan | incident-trigger 初步接入 auth invalid + Bybit fail-closed；2026-06-12 BB/E2 reviewed CORE+auth+Bybit path with no blocker；`sm_halt_stuck` source-live via runtime HaltSession producer but pending BB/E2/E4/QA review；drift / watchdog producer 仍待後續；E4/QA/full-chain review 待 producer coverage decision |

#### 2.4.2 `FAILSAFE_FEED_SENDERS`

| 欄位 | 值 |
|---|---|
| name | `FAILSAFE_FEED_SENDERS` |
| type_signature | `OnceLock<{ outcome_tx, ack_tx }>`（mpsc senders）|
| location | `rust/openclaw_engine/src/tasks.rs`（init 於 spawn watcher 時）|
| owner_lifecycle | boot 一次；保活 sender 端使 `outcome_rx`/`ack_rx` channel 不關（防 watcher select! busy-loop spin）|
| cross_task_pattern | `incident_policy` 取 `outcome_tx` 餵 dispatch outcome；C5 GUI ack 取 `ack_tx`。arm 類 incident 只有三路 dispatch 回 `AllFail` 且 push secret gate 通過時才餵；notify-only 不餵 |
| lock_primitive | OnceLock（set-once）|
| visibility | crate-internal getter |
| caller_chain | producer: `notification_failsafe/incident_policy.rs`; source callers: `live_auth_watcher.rs` auth invalid/resolved, `bybit_rest_client.rs` retCode fail-closed/resolved；C5 GUI ack pending |
| health_monitoring | NO |
| registered_date | 2026-05-29 |
| governance_authority | 同 2.4.1 |
| migration_plan | C5 GUI ack pending；producer coverage 後續補 SM-stuck / drift / watchdog notify-only |

#### 2.4.3 `INCIDENT_POLICY_LEDGER`

| 欄位 | 值 |
|---|---|
| name | `INCIDENT_POLICY_LEDGER` |
| type_signature | `OnceLock<parking_lot::Mutex<PolicyLedger>>`；內部 class-level `HashMap<IncidentClass, IncidentState>` + `current_armed_class` |
| location | `rust/openclaw_engine/src/notification_failsafe/incident_policy.rs` |
| owner_lifecycle | lazy init on first incident producer call；engine process lifetime；restart 清零（incident 若仍持續會重新 sustained） |
| cross_task_pattern | producer: auth watcher / Bybit REST async tasks call `report_incident` / `report_resolved`; consumer: same module decides sustained / throttle / 7d cooling / self-heal gating before feeding watcher |
| lock_primitive | `parking_lot::Mutex`；lock only covers ledger mutation, never held across notification dispatch await |
| visibility | private static；public helper functions expose constrained operations |
| caller_chain | `live_auth_watcher.rs::decide_once` auth invalid/resolved; `bybit_rest_client.rs::{get,post}` retCode fail-closed/resolved; dispatch target `SharedFailsafeWatcher::dispatch_3way_only` + `FAILSAFE_FEED_SENDERS.outcome_tx` |
| health_monitoring | NO（incident audit/GUI path remains V114 notification fail-safe audit + C5 pending） |
| registered_date | 2026-05-31 |
| governance_authority | PA spec `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-30--c4_incident_policy_dispatch_trigger_spec.md` + AMD-2026-05-21-01 v2 §3/§5 |
| migration_plan | If restart-persistent incident cooling is later required, add PG-backed ledger via new V### migration and Linux PG dry-run; current in-memory ledger matches PA §4.3 acceptance |

---

### §2.5 SM Option 2 收斂 step-(i) — Python divergence comparator sink（2026-06-02）

per `docs/CCAgentWorkSpace/Operator/2026-06-02--sm_option2_convergence_migration_design.md` §5 step-(i)：`governance_hub` lease 操作（acquire/release/get）+ acquire 開頭 auth-axis 比對在 flag-ON（`OPENCLAW_LEASE_PYTHON_IPC_ENABLED=1`）時以 Rust IPC 結果為權威，同時 *影子* 計算 Python SM 判定並送進本 comparator。comparator sink 是 module-level 可變狀態（in-memory ring buffer + 計數器），設計對齊 `governance_lease_bridge._DUAL_WRITE_MIRROR`（package-private、`threading.Lock` 保護、無 TTL/LRU/DB、僅透過 helper 變更）。step (iv) cleanup 會連同 dual-write mirror 一起移除本 sink。

> 同檔 `governance_lease_bridge._DUAL_WRITE_MIRROR` / `_DUAL_WRITE_LOCK`（Sprint 3 H E-3）為相同 pattern 的既有 sink，仍待補登（§6 carry-over hygiene；非本 E1b scope）。

#### 2.5.1 `_DIVERGENCE_RING`

| 欄位 | 值 |
|---|---|
| name | `_DIVERGENCE_RING` |
| type_signature | `list[dict[str, Any]]`（module-level）；FIFO ring，cap `_RING_CAP=2048` |
| location | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_divergence.py:68`（cap 定義 `_RING_CAP` 同檔 :66）|
| owner_lifecycle | import 時建空 list；API worker process-local；uvicorn worker exit 時隨 module drop。`reset_divergence_state()` 僅供測試隔離清空 |
| cross_task_pattern | producer: `record_divergence()`（由 `GovernanceHub.acquire_lease`/`release_lease`/`get_lease` flag-ON 路徑 + acquire 開頭 auth-axis 比對呼叫；同 worker 多 sync thread 可並發）；consumer: `get_divergence_snapshot()` / `get_mismatch_snapshot()`（healthcheck + soak 取證 + 測試）|
| lock_primitive | `threading.Lock`（`_DIVERGENCE_LOCK`）；append + FIFO evict 在同一 lock hold 內；無跨 await（純 sync）|
| visibility | private module binding（package-private；僅透過 `record_divergence` / `get_*` / `reset_divergence_state` helper 存取）|
| caller_chain | producer: `governance_hub.GovernanceHub._compare_auth_axis`（auth-axis）+ `acquire_lease`/`release_lease`/`get_lease` flag-ON 影子比對；consumer: soak/healthcheck 取 `get_divergence_counters`/`get_mismatch_snapshot`（step-(i) gate 讀 `divergences==0` 且 `total>=N`）|
| health_monitoring | NO — soak 期觀測儀器；step-(iv) cleanup 移除；非 M3 health row target |
| registered_date | 2026-06-02 |
| governance_authority | SM Option 2 convergence design §5 step-(i) + §3 |
| migration_plan | step (iv) cleanup 移除（與 dual-write mirror 同時）；soak 0 divergence 後排程退役 |

#### 2.5.2 `_COUNTERS`

| 欄位 | 值 |
|---|---|
| name | `_COUNTERS` |
| type_signature | `dict[str, int]`（keys: `total` / `matches` / `divergences`）；單調累加，不隨 ring FIFO evict 失真 |
| location | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_divergence.py:73` |
| owner_lifecycle | 同 `_DIVERGENCE_RING`（import 建、worker drop、`reset_divergence_state()` 測試清零）|
| cross_task_pattern | producer: `record_divergence()` 於 `_DIVERGENCE_LOCK` 內 `+=`；consumer: `get_divergence_counters()`（step-(i) gate 判讀）|
| lock_primitive | 共用 `_DIVERGENCE_LOCK`（與 ring 同鎖，原子更新）|
| visibility | private module binding |
| caller_chain | 同 §2.5.1 |
| health_monitoring | NO |
| registered_date | 2026-06-02 |
| governance_authority | 同 §2.5.1 |
| migration_plan | step (iv) cleanup 移除 |

#### 2.5.3 `_DIVERGENCE_LOCK`

| 欄位 | 值 |
|---|---|
| name | `_DIVERGENCE_LOCK` |
| type_signature | `threading.Lock` |
| location | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_divergence.py:69` |
| owner_lifecycle | import 時建；worker drop |
| cross_task_pattern | 守護 `_DIVERGENCE_RING` + `_COUNTERS` 的並發 append/evict/累加/snapshot；同 worker 多 sync thread 競用 |
| lock_primitive | `threading.Lock`（非 reentrant；helper 內無巢狀取鎖）|
| visibility | private module binding |
| caller_chain | 所有 §2.5.1 / §2.5.2 helper 內部持有 |
| health_monitoring | NO |
| registered_date | 2026-06-02 |
| governance_authority | 同 §2.5.1 |
| migration_plan | step (iv) cleanup 移除 |

#### 2.5.4 `_FLUSHER_LEADER_LOCK_FD`（P5-SM-OPTION2 B-3，2026-06-03）

per `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-03--p5_sm_soak_observability_redesign.md` §3 B-3：把 §2.5.2 comparator `_COUNTERS` best-effort 週期 UPSERT 到 PG 投影表 `learning.lease_ipc_divergence_snapshot`（V129），讓獨立 passive_wait_healthcheck cron 能以 SQL 讀 soak 信號。flusher 為 leader-elected 單一 writer，避免多 uvicorn worker 重複寫同一 'singleton' row。

| 欄位 | 值 |
|---|---|
| name | `_FLUSHER_LEADER_LOCK_FD` |
| type_signature | `int \| None`（module-level；flock 持有的檔案描述符，None=未取得/非 leader）|
| location | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_divergence_flush.py` |
| owner_lifecycle | lazy：首次 `_acquire_flusher_leader_lock()` 取得（flock `LOCK_EX\|LOCK_NB`）；API worker process lifetime；worker exit 隨 process 釋放。`_reset_flusher_leader_lock_for_tests()` 僅供測試清空 |
| cross_task_pattern | 單一 leader worker 持有；`divergence_snapshot_flusher` 背景協程每 30s 經 executor 跑 `flush_divergence_snapshot_once`（讀 §2.5.2 `_COUNTERS` snapshot → UPSERT V129 表）。非 leader worker 不 flush。對齊 `paper_trading_wiring._RECONCILER_ALERT_LOCK_FD` flock 範式 |
| lock_primitive | OS `fcntl.flock`（檔案鎖 `$OPENCLAW_DATA_DIR/lease_ipc_divergence_flusher.leader.lock`）；非 in-process lock。`OPENCLAW_LEASE_DIVERGENCE_FLUSHER_LEADER=0` 可強制本 worker 非 leader |
| visibility | private module binding（僅 `_acquire_flusher_leader_lock` / `_reset_flusher_leader_lock_for_tests` 變更）|
| caller_chain | producer: `main.py @app.on_event("startup")` → `asyncio.create_task(divergence_snapshot_flusher())` → `_acquire_flusher_leader_lock()`；consumer: cron `passive_wait_healthcheck` `[81] check_81_lease_ipc_soak` 讀 PG 投影（非讀此 fd）|
| health_monitoring | NO — soak 期觀測儀器；flusher 死 → snapshot stale → `[81]` freshness gate FAIL（R2 緩解）；step-(iv) cleanup 移除 |
| registered_date | 2026-06-03 |
| governance_authority | P5-SM-OPTION2 soak redesign §3 B-3 + operator O-1/O-2 |
| migration_plan | step (iv) cleanup 連同 comparator sink（§2.5.1-3）+ dual-write mirror 一起移除（soak 0 divergence 後）；屆時 DROP V129 表 |

#### 2.5.5 `_CANARY_COUNTERS` / `_CANARY_STATE` / `_CANARY_LOCK`（P5-SM soak 第二輪 E1-C，2026-06-10）

per `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-10--p5sm_soak_observability_redesign.md` §3.1/§3.2 + PM cadence 定案 `2026-06-10--p5sm_soak_cadence_decision.md`：唯讀 IPC canary（默認 120s ±10% jitter）打 `governance.is_authorized` + `governance.get_status` 兩個讀 arm 做結構驗證，計數器由 flusher（§2.5.4 同 leader 進程）投影 V129 `'canary'` row。

| 欄位 | 值 |
|---|---|
| name | `_CANARY_COUNTERS` + `_CANARY_STATE` + `_CANARY_LOCK` |
| type_signature | `dict[str, int]`（attempts/ok/fail/fail_streak_breaches，單調累加）+ `dict[str, Any]`（last_ok_ts/consecutive_failures/fail_streak_started_mono/streak_breach_recorded/in_backoff/in_flight）+ `threading.Lock` |
| location | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_ipc_canary.py` |
| owner_lifecycle | import 時建；API worker process-local；worker exit 隨 module drop（restart 歸零 = epoch 邊界，由 flusher `epoch_rollover` 事件搶救前值）。`reset_canary_state_for_tests()` 僅供測試隔離 |
| cross_task_pattern | producer: `run_canary_tick`（leader 進程內單一 asyncio task；single-flight `in_flight` 守衛）；consumer: `get_canary_counters()`（flusher 每 30s 讀後 UPSERT V129 `'canary'` row：total=attempts / matches=ok / divergences=fail）。**leader 同進程不變量（load-bearing）**：canary 複用 §2.5.4 同一把 flock → canary 與 flusher 必在同一進程，flusher 才能從同進程記憶體讀到真計數（雙鎖會選出不同進程 = silent 假死） |
| lock_primitive | `threading.Lock`（`_CANARY_LOCK`；計數 + 連段/退頻記帳在同一 hold 內，無跨 await 持鎖；log I/O 在鎖外）+ 復用 §2.5.4 flock（leader election） |
| visibility | private module binding（僅 `run_canary_tick` / `get_canary_counters` / `get_canary_runtime_state` / `reset_canary_state_for_tests` 存取） |
| caller_chain | producer: `main.py @startup` → `asyncio.create_task(governance_ipc_canary_loop())`（kill-switch `OPENCLAW_SM_IPC_CANARY_ENABLED` 嚴格 "1"，默認 OFF）；consumer: `governance_divergence_flush` → V129 → cron `[82]` soak-window check |
| health_monitoring | NO — soak 期觀測儀器；canary 死 → flusher 低頻 `canary_heartbeat` 事件（30min 攜 attempts 快照）持平/停更 → `[82]` heartbeat 連續性支路 FAIL（fail-closed；偵測粒度 = heartbeat 30min + cron 6h cadence，粗粒度兜底 = 累計 stall floor。E2 HIGH-2 修復前「attempts 不增長即 FAIL」宣稱過強：累積 ≥ floor 後中段死亡原不可見）；worst case = 只少觀測數據 |
| registered_date | 2026-06-10 |
| governance_authority | P5-SM soak 第二輪 PA 設計 §3.2/§5.2 + PM 五條 fire-機率防護 |
| migration_plan | step (iv) cleanup 連同 comparator sink（§2.5.1-4）+ V129/V137 + `[82]` 一起退役 |

#### 2.5.6 `_SOAK_TRACKERS`（P5-SM soak 第二輪 E1-B，2026-06-10）

per PA 設計 §3.1（flusher 擴充）：V137 `learning.lease_ipc_soak_events` 事件帳本的程內偵測 trackers——flag 變遷 / canary 失敗連段增量 / 計數器倒退 / epoch 起點 / 低頻 canary_heartbeat（E2 HIGH-2 修復），全部以「上次觀測值 vs 當下快照」比對偵測，事件 INSERT best-effort（V137 未 apply 全 fail-soft）。

| 欄位 | 值 |
|---|---|
| name | `_SOAK_TRACKERS` |
| type_signature | `dict[str, Any]`（last_flag_state / last_canary_breaches / canary_start_recorded / last_comparator_counts / last_canary_counts / epoch_start_recorded / last_heartbeat_mono） |
| location | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/governance_divergence_flush.py` |
| owner_lifecycle | import 時建；leader worker process-local；restart 歸零 = epoch 邊界語義（`epoch_rollover` 事件即為此而存在）。`_reset_soak_event_trackers_for_tests()` 僅供測試隔離 |
| cross_task_pattern | 只由 leader 進程的單一 flusher 協程順序讀寫（`record_epoch_start_events_once` 啟動一次 + `detect_and_record_soak_events_once` 每 30s 週期）；`run_in_executor` 逐次 await 的 happens-before 保證跨 executor thread 可見性 |
| lock_primitive | 無（單協程順序存取，無並發 writer；見 cross_task_pattern 論證）+ 隸屬 §2.5.4 flock leader 域（非 leader worker 永不觸碰） |
| visibility | private module binding（僅 `record_epoch_start_events_once` / `detect_and_record_soak_events_once` / `_reset_soak_event_trackers_for_tests` 存取） |
| caller_chain | producer: `divergence_snapshot_flusher` 協程（main.py @startup 排程）；consumer: V137 `learning.lease_ipc_soak_events` → cron `[82]` soak-window check 跨 epoch 重建連續窗 |
| health_monitoring | NO — soak 期觀測儀器；偵測層死 → 事件缺失 → `[82]` 在 active 下對「帳本空 / counter regression 交叉偵測」fail-closed FAIL |
| registered_date | 2026-06-10 |
| governance_authority | P5-SM soak 第二輪 PA 設計 §3.1 + §4 S3/S4 gate |
| migration_plan | step (iv) cleanup 連同 comparator sink（§2.5.1-5）+ V129/V137 + `[82]` 一起退役 |

---

### §2.6 L2 Advisory Mesh — D3 Provenance & Audit writer（Phase 1，2026-06-08）

per `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-08--l2-d3-phase1-tech-design.md` §F + 執行方案 `docs/execution_plan/2026-06-05--l2-advisory-mesh-execution-plan.md` §2 Phase 1。L2（Layer 2 AI 推理）D3 取證帳本的唯一 sanctioned 寫入口（INSERT-only），把單次模型呼叫的完整（已消毒）prompt/response 落 `agent.l2_calls`（V134），並提供 append-only 寫入口給 `agent.l2_consequential_marks`（V134 side-table）與 `learning.l2_gate_seam_log`（V135）。消毒（`l2_secret_redactor` secret-pattern + `error_sanitize` str(e)→classified code）在 INSERT 之前跑、sha256 算在已消毒文本上。

#### 2.6.1 `L2CallLedgerWriter`（module-level singleton `_WRITER`）

| 欄位 | 值 |
|---|---|
| name | `L2CallLedgerWriter`（module-level binding `_WRITER`）|
| type_signature | `L2CallLedgerWriter \| None`（module-level；holds `conn_provider` = `db_pool.get_pg_conn` 共享 psycopg2 ThreadedConnectionPool handle，與 `persist_lessons` 同源）|
| location | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/l2_call_ledger_writer.py:364`（`_WRITER` binding）；class `:99`；getter `get_l2_call_ledger_writer():367` |
| owner_lifecycle | lazy：首次 `get_l2_call_ledger_writer()` 構造；control_api worker process lifetime；無 live-trading lifecycle。`_reset_l2_call_ledger_writer_for_tests()` 僅供測試清空 |
| cross_task_pattern | append-only INSERT，在 L2 advisory 迴圈上（`Layer2Engine._record_l2_call_to_ledger` → D3 write）；read 路徑為 forensic SELECT（P2+ orchestrator/forensic 查詢，本 P1 不含 reader）|
| lock_primitive | 無 in-process lock：DB-level append-only（REVOKE UPDATE/DELETE，三表零 column-level UPDATE grant）為真正 guard；連線並發由 psycopg2 ThreadedConnectionPool 內部處理（per-borrow conn，短生命週期）|
| visibility | module-internal singleton；公共寫入口 `record_l2_call()` / `record_consequential_mark()` / `record_gate_seam()`（全 INSERT-only）|
| caller_chain | **producer**：`layer2_engine.py:323` `_record_l2_call_to_ledger`（def，內部 `:352` 呼 `get_l2_call_ledger_writer().record_l2_call(...)`）由 `_run_session_inner` `:655` 真接線（manual-trigger `POST /trigger` route → `run_session` → 首輪模型呼叫）（P1 已可達，非死碼）。**consumer**：forensic SELECT 讀者（`agent.l2_calls` / gate-seam / marks）為 P2+ orchestrator + fault-localization 協定查詢——P1 ledger reachable 由 producer 證明，reader 在 P2 接 |
| health_monitoring | NO（P1）—— 建議 YES（silent D3-write 失敗 = lineage gap = root-principle-8 違反）；本 P1 為 fail-soft（ok=False 不 raise），health emitter 觀測為 P2+ follow-up（見下 migration_plan）|
| registered_date | 2026-06-08 |
| governance_authority | `2026-06-08--l2-d3-phase1-tech-design.md` §F + design v4-final §D + 執行方案 Phase 1 |
| migration_plan | P2 接 reader（orchestrator forensic SELECT）+ lane appliers 呼 `record_consequential_mark`/`record_gate_seam`；建議 P2+ 補 health_monitoring（D3-write 失敗告警）；retention（§Q6 post-P1）落地時連同 drop 邏輯處理（P1 ledger 無 retention/compression）|

#### 2.6.2 `L2AdvisoryOrchestrator`（module-level singleton `_ORCHESTRATOR`，Phase 2，2026-06-08）

per `docs/CCAgentWorkSpace/PA/workspace/reports/2026-06-08--l2-p2-orchestrator-tech-design.md` §A/§K + 執行方案 §2 Phase 2。L2 advisory 迴圈的 conductor（root principle 15，非第六 trading agent）：trigger → admission → capability dispatch → PromptContract → out-of-bound guard → D3 write → result routing（proposal 進既有被閘管線，非執行）。擁有 `Layer2Engine` 作為「眾多 executor 之一」。

| 欄位 | 值 |
|---|---|
| name | `L2AdvisoryOrchestrator`（module-level binding `_ORCHESTRATOR`）|
| type_signature | `L2AdvisoryOrchestrator \| None`（module-level；holds registry cache + `_AdmissionState`（per-capability debounce/dedup 窗口）+ fail-safe state + 注入式 cost_tracker/registry_loader）|
| location | `program_code/exchange_connectors/bybit_connector/control_api_v1/app/l2_advisory_orchestrator.py`（class；`_ORCHESTRATOR` binding；getter `get_l2_advisory_orchestrator()`）|
| owner_lifecycle | lazy：首次 `get_l2_advisory_orchestrator()` 構造；control_api worker process lifetime；**無 live-trading lifecycle**。`_reset_l2_advisory_orchestrator_for_tests()` 僅供測試清空 |
| cross_task_pattern | conductor of advisory loop；admission 決策 + dispatch 經 `L2CallLedgerWriter` 寫 D3 gate-seam（`record_gate_seam(gate_id="admission")`）|
| lock_primitive | `threading.RLock`（reentrant；保護 fail-safe 狀態轉移 + registry reload + admission 窗口；`_admit` 持鎖再呼 `_cap_spend_today` 需重入）；per-capability in-process（無 DB lock；重啟乾淨 re-arm）|
| visibility | module-internal singleton；公共入口 `dispatch(...)` / `status()`（唯讀）/ `reload_registry()` / `report_call_outcome()` / `reset_fail_safe()` |
| caller_chain | **producer**：route `layer2_routes.py` `/orchestrator/status`（read）+ `/registry/reload`（operator write）+ `/orchestrator/fail-safe/reset`（operator write）→ `_get_orchestrator()` → singleton。**consumer**：經 `L2CallLedgerWriter.record_gate_seam` 寫 `learning.l2_gate_seam_log`（admission trigger_decision）。P3 接 event/schedule/threshold trigger surface 驅動 dispatch |
| health_monitoring | NO（P2）—— 建議 YES（silent dispatch 失敗 = 無 advisory；fail-safe worst=NO_ADVICE=今日 baseline）；P3+ follow-up |
| governance_authority | `2026-06-08--l2-p2-orchestrator-tech-design.md` §A + design v4-final §A.1/§F/§H + 執行方案 Phase 2 |
| migration_plan | none（無 DB 表；registry=TOML SSOT；admission/adjudication state in-memory + 記 V135 gate-seam）。P3 接各 capability executor + parsed_output guard 完整路徑 |

#### 2.6.3 admission controller — **orchestrator-internal state，無獨立 binding**

per PA §K：admission 的 per-capability debounce/dedup/coalesce 窗口實作為 `L2AdvisoryOrchestrator._admission`（`_AdmissionState` dataclass，§2.6.2 內部 state），**非獨立 singleton**。無 separate binding；生命週期隨 §2.6.2。

#### 2.6.4 conflict adjudicator — **stateless 純函數模塊，無 singleton row（§4.1 note）**

per PA §K：`l2_conflict_adjudicator` 是 stateless 純函數模塊（`adjudicate_vs_gate` / `adjudicate_cross_capability` + literal `PRECEDENCE` dict），**無 mutable singleton**，故不需 singleton row。設計鐵律：裁決函數內零 model 呼叫（CC stress-test 6）。同理 `l2_capability_registry`（loader + `LANE_DIRECTION` 常數 + `effective_autonomy` 純函數）、`l2_prompt_contract_registry`（versioned 常數 registry）、`l2_out_of_bound_guard`（純確定性函數）皆 stateless，無 singleton。

---

## §3 Registration Rules

### §3.1 新登記前必做（PA / E1 / E2 共同）

1. **grep verify name + signature 0 conflict**：repo 內未有同名 type / module-level binding
2. **caller_chain 必列舉 ≥ 1 producer + ≥ 1 consumer**（純 producer 無 consumer 屬 dead code，FAIL）
3. **health_monitoring 欄位必明示 YES/NO**：YES 必 link ADR-0042 6 domain 之一
4. **migration_plan**：明示 Sprint N+ 是否計劃改造；無計劃寫 `0`

### §3.2 E2 review 必檢條目

per `feedback_impl_done_adversarial_review` 2026-05-09 + `feedback_no_dead_params`：

1. caller_chain 真實 — grep production 端真實有 caller，不是「Wave N+ 接線時補」的承諾
2. lock_primitive 跨 await 邊界檢（async lock held across await 是 Track A round 1 MEDIUM-1 反模式）
3. fail-soft / fail-loud 是否與 spec 對齊（PortfolioStateCache F-2 NaN sanitize 是 fail-loud + skip；HealthEventBus publish 是 fail-soft；兩者非互換）
4. test-only helper（`inject_sample_with_timestamp`）走 `pub` + `#[doc(hidden)]` 而非 `#[cfg(test)]` 必註明原因（integration test crate visibility）

### §3.3 PA dispatch packet 必含

dispatch packet 中若 E1 IMPL 將引新 mutable singleton：

1. dispatch packet §X 條目「新 singleton 預登記」必列入：name / type_signature / location / cross_task_pattern
2. E1 IMPL DONE 後 PA / E2 / PM 收口任一方提示「補登 SSOT」task — 不能 skip 等下一輪 E2 catch（MEDIUM-1 escalate pattern）

### §3.4 反模式（禁忌）

per memory + 既往 E2 finding：

- **「struct-internal Arc 不需登記」誤判**：caller 端 own + inject pattern 雖然非 module-level static，但若 caller 構造的 Arc 跨 task 共享、engine 全週期 1 個 Arc instance、含 mutable state，仍登記（避「概念漏網」）
- **「placeholder fresh 0-state 等同接通 production」誤判**：WsRttHistogram / WsDropoutCounter Wave B 半實裝 — 30 天全 0 V106 row 不代表真實 production WS 健康（per §2.1.3.a / §2.1.4.a）；caller chain 必如實揭露「placeholder 未接 supervisor」
- **「test fixture mock 等同 production caller」誤判**：bybit_rest_client_tests.rs 內多處 `RestLatencyHistogram::new()` 是 mock fixture；caller_chain 必區分 mock 與 production
- **「ADR amend 必為單向 grow」誤判**：trim 是合理 governance 動作；但 trim 期間 SSOT 沒搬走 = 真實 gap（本 PA SSOT 建立修補此 gap）

---

## §4 Cross-reference with CLAUDE.md

### §4.1 CLAUDE.md §七 reference

CLAUDE.md `§七 Code And Docs Rules` line 165：

> New mutable singletons must be registered in the singleton table's current authority location before merge.

「current authority location」= 本 doc `docs/architecture/singleton-registry.md`（2026-05-23 PA 建立 SSOT 後）。

### §4.2 CLAUDE.md §九 reference

CLAUDE.md `§九 Code Structure Guardrails` line 196：

> New mutable singletons must be registered in the current singleton authority before merge.

「current singleton authority」= 本 doc。

### §4.3 是否修改 CLAUDE.md

**本 task PA verdict：不修改 CLAUDE.md inline**。理由：

1. CLAUDE.md trim 設計目標是「memory file 保持輕量 + 路由到 docs」；inline restore singleton 違 trim 意圖
2. 既有 §七 + §九 兩條 rule line literal 已含「current authority location」抽象表述；不依賴具體 path，加 cross-ref 後 path 變更不需動 CLAUDE.md
3. 替代 — `docs/README.md` index entry 增本 SSOT path（per docs governance R4 docs index sweep rule）= 路徑可達

### §4.4 path 變更需提醒處

未來如 SSOT 搬位（不建議；但若必），需同步更新：

- `docs/README.md` index entry
- 本檔 §4.1 + §4.2 path literal
- CLAUDE_CHANGELOG.md 記錄變更
- 若涉及 governance authority shift，補 ADR

---

## §5 Lessons Learned（本 PA SSOT 建立期間揭露）

### §5.1 CLAUDE.md trim 反模式

2026-05-02 trim 期間 §九 Singleton 表「收成單行」實際操作 = **整段 table 刪除沒搬位**。CLAUDE.md 保留 line 165 + 196 兩條 abstract rule 但 SSOT 0 hit。governance gap 維持 21 天才被 Sprint 4+ Wave B E2 round 2 MEDIUM-1 catch + escalate。

修法：trim 任何 inline reference table 時，**必同時**：

1. 建新 SSOT location（或選既有 location）
2. CLAUDE.md rule line 不變或加 cross-ref
3. CHANGELOG 明記「table moved to X」
4. archive snapshot 必註「new SSOT location = X」（archive 純被動快照不夠）

### §5.2 MEDIUM-1 不應在 E2 round 1 後才被 catch

E2 Wave B round 1 catch MEDIUM-1「6 new singleton 未登記」是合理；但根因「SSOT 0 hit」應在 dispatch packet 階段 PA 預判（per §3.3 規則 — PA dispatch packet 必含新 singleton 預登記條目）。Sprint 2 Wave 1+2 dispatch packet（2026-05-22）未含此項，是 PA gap。修法：本 SSOT 建立後 dispatch packet 模板必加「新 singleton 預登記」section（per §3.3）。

### §5.3 半實裝陷阱誠實揭露的價值

Wave B PA-DRIFT-4 round 2 揭露 WsRttHistogram / WsDropoutCounter placeholder 半實裝（§2.1.3.a / §2.1.4.a）— 不掩飾「V106 全 0」是 placeholder 副作用，不是真實 WS 健康。誠實揭露對 Wave C / Sprint 5+ wire-up scope 拍板極關鍵；caller_chain 欄位必反映此狀態。

---

## §6 Carry-over to Sprint 5+

### §6.1 Re-ingest archive 4 條 Python singleton

`docs/archive/2026-05-02--CLAUDE-pre-trim-snapshot.md` §九 line 77-80 4 條 Python singleton 仍在 production 跑：

1. `_H_STATE_INVALIDATOR` / `_LOCK` — h_state_invalidator.py（G3-08 Phase 1C 條件 spawn）
2. `MARKET_SCANNER` / `AUTO_DEPLOYER` / `_SCOUT_WORKER` — strategy_wiring_scanner.py
3. `HStateCacheSlot` — rust/openclaw_engine/src/ipc_server/slots.rs（Rust late-injected slot）
4. `CostEdgeAdvisorDbSlot` — rust/openclaw_engine/src/cost_edge_advisor_boot.rs（Rust late-injected slot）

本 task scope 嚴守 Wave A/B 6 新 singleton 登記；archive 4 條 re-ingest 屬 Sprint 5+ doc clean-up follow-up。建議 task：

- Owner: TW + PA
- Priority: P2 LOW（governance hygiene；non-blocker）
- Est: 1-2 hr（盤點 4 條當前 production state + 補 §1.3 完整欄位）
- 觸發條件: Sprint 5+ cascade IMPL 期間 docs/ doc-index sweep 順手

### §6.2 dispatch packet 模板補「新 singleton 預登記」section

本 task §5.2 + §3.3 邏輯衍生：dispatch packet 模板（docs/execution_plan/* / docs/agents/* 範本端）必加 section「新 mutable singleton 預登記」；E1 IMPL 前 PA 已明示。

- Owner: PA
- Priority: P2 (governance template hygiene)
- Est: 30 min (dispatch packet 模板 .md skeleton patch + 1 個 worked example)
- 觸發條件: 下次 Sprint dispatch packet 起草前

### §6.3 BybitPrivateWs supervisor signature 改造

per §2.1.3.a + §2.1.4.a Wave B 半實裝陷阱；Sprint 5+ Wave C 必：

1. `BybitPrivateWs::new()` signature 改 caller 注入 `Arc<WsDropoutCounter>` + `Arc<WsRttHistogram>`（替代當前內部 own）
2. main_health_emitters.rs `build_real_api_latency_probe` 從 supervisor handle clone Arc 替換 placeholder fresh Arc
3. 30 天 V106 `api_latency__ws_*` row 開始反映 production WS metric

- Owner: E1（Rust）+ E2（review）
- Priority: P1（unblocks 真實 WS health observability）
- Est: 4-6 hr E1 + 1 hr E2
- 觸發條件: Sprint 5+ cascade IMPL dispatch

### §6.4 PortfolioStateCache update task wire-up

per §2.2.1.b — Wave B placeholder no-op tick；Sprint 5+ Wave C 接 PaperState SSOT。

- Owner: E1 + PA
- Priority: P1（unblocks 真實 portfolio risk envelope V106 emit；當前 5 metric 全 0/baseline）
- Est: 4-6 hr E1 + 1 hr E2 + 0.5 hr PA spec amend（per-mode vs single cache 拍板）
- 觸發條件: Sprint 5+ cascade IMPL dispatch

---

## §7 Maintenance

- 新 singleton merge 前必 update 本 doc（per §3.1-§3.4 規則）
- E2 review 必檢條目（per §3.2）
- 每季度 PA 走一輪 audit：grep `pub struct.*Mutex|pub static\|lazy_static!\|once_cell::sync` 對齊本 doc list
- archive snapshot 不 reinstall（per §4.4）；歷史變遷追 git history + CLAUDE_CHANGELOG
- 路徑變更須同步 §4.4 4 處
