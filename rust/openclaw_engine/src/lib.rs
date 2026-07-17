//! OpenClaw Engine — trading engine main body (R01).
//! OpenClaw 引擎 — 交易引擎主體。
//!
//! MODULE_NOTE (EN): Library crate re-exporting engine modules: config (ArcSwap hot-reload),
//!   ipc_server (Unix socket JSON-RPC 2.0), ws_client (Bybit WS with auto-reconnect).
//!   The binary entry point is in main.rs.
//! MODULE_NOTE (中): 庫 crate 重新導出引擎模組：config（ArcSwap 熱加載）、
//!   ipc_server（Unix 套接字 JSON-RPC 2.0）、ws_client（Bybit WS 自動重連）。
//!   二進制入口在 main.rs。

// P2-CLIPPY-CLEANUP-1：先把 Apple Silicon `cargo clippy -- -D warnings`
// gate 恢復為可執行；本 checkpoint 不重寫歷史文檔與交易路徑複雜度。
// 未列入的新增 lint 類別仍會失敗，需後續明確審查才可加入 allowlist。
#![allow(
    clippy::borrow_deref_ref,
    clippy::collapsible_if,
    clippy::collapsible_match,
    clippy::derivable_impls,
    clippy::doc_lazy_continuation,
    clippy::doc_overindented_list_items,
    clippy::drain_collect,
    clippy::empty_line_after_doc_comments,
    clippy::explicit_auto_deref,
    clippy::field_reassign_with_default,
    clippy::large_enum_variant,
    clippy::len_without_is_empty,
    clippy::manual_clamp,
    clippy::manual_contains,
    clippy::manual_inspect,
    clippy::manual_is_multiple_of,
    clippy::manual_range_patterns,
    clippy::match_like_matches_macro,
    clippy::needless_borrow,
    clippy::neg_cmp_op_on_partial_ord,
    clippy::new_without_default,
    clippy::question_mark,
    clippy::redundant_closure_call,
    clippy::result_large_err,
    clippy::should_implement_trait,
    clippy::too_many_arguments,
    clippy::type_complexity,
    clippy::unnecessary_map_or,
    clippy::unwrap_or_default,
    clippy::useless_conversion,
    clippy::useless_format
)]

pub mod account_manager;
pub mod agent_spine;
pub mod ai_budget;
pub mod ai_service_client;
// PA daily-kline backfill（2026-06-02）：日線歷史回填（timeframe='1d'）— 分頁取數 +
// C-3 strict-parse（fake-zero/非有限/損壞 bar 不寫）+ market.klines/provenance 寫層。
pub mod backfill;
// Sprint 1B Earn first stake B3（2026-05-23）：Flexible Saving only / 5 endpoint
// 走共用 BybitRestClient（HMAC + rate limit + retCode 觀測）。
pub mod bounded_probe_active_order;
pub mod bounded_probe_near_touch;
pub mod bybit_earn_client;
pub mod bybit_private_ws;
pub mod bybit_private_ws_status_writer;
pub mod bybit_rest_client;
// P0-1c boot/build SHA 可觀測面（2026-07-04）：build.rs 嵌入的 git SHA/build 時間
// 常量 + boot_history.jsonl append，讓運行進程的代碼世代可對表部署 HEAD。
pub mod boot_observability;
pub mod canary_writer;
// WP2-B B1：Cost Gate organic reject 的不可變候選 lineage/source 捕獲；純資料，零權限。
pub mod candidate_evaluation_source_snapshot;
pub mod candidate_event_context;
pub mod claude_teacher;
pub mod combine_layer;
pub mod common;
pub mod config;
pub mod cost_edge_advisor;
// Sprint 1B Earn first stake (2026-05-23)：cron-like scheduler 命名空間。
// 首個成員 `cron::earn_reconciliation` 每日 UTC 02:00 對 Bybit Earn 餘額 vs
// V100 `learning.earn_movement_log` 做 reconciliation。
pub mod cron;
pub mod database;
pub mod decision_context_producer;
pub mod demo_learning_lane;
pub mod demo_learning_lane_hot_path;
pub mod demo_learning_lane_ledger;
// P1-10 / operator D9:probe_ledger.jsonl 50MB 輪轉 + 14d retention + 跨段讀取
// 視圖。與 Python 側 ledger_rotation.py 共用段名契約與 flock 輪轉鎖。
pub mod demo_learning_lane_rotation;
// 2026-07-02 soak dispatch-edge containment §1.2:envelope 生命週期閘
// (30s TTL 緩存 + last_good 硬上界),step_4_5_dispatch withhold 判定用。
#[cfg(test)]
mod demo_learning_lane_hot_path_tests;
pub mod demo_learning_lane_soak_gate;
#[cfg(test)]
mod demo_learning_lane_tests;
pub mod demo_learning_lane_writer;
pub mod drawdown_revoke;
pub mod dynamic_risk_sizer;
pub mod edge_estimates;
pub mod edge_predictor;
pub mod event_consumer;
pub mod execution_listener;
pub mod exit_features;
pub mod fast_track;
pub mod feature_collector;
pub mod h_state_cache;
// P0-ENGINE-HALTSESSION-STUCK-FIX (2026-05-19): halt forensic logger.
// P0-ENGINE-HALTSESSION-STUCK-FIX（2026-05-19）：halt 取證記錄器。
pub mod halt_audit;
// Sprint 1A-ζ Phase 2 Track A：M1 Decision Lease LAL state machine skeleton。
// Sub-module `lal` 含 LalTier enum / from_i32 / numeric_value / Tier 0→1 transition stub
// + Tier 0 fill RETIRED blocker stub（per ADR-0034 Decision 6）。
pub mod governance;
// Sprint 1A-ζ Phase 2 Track B：M3 health monitoring 4-state ladder skeleton。
// engine_runtime domain IMPL + 5 stub (per ADR-0042 Decision 3) + amplification
// cap (per ADR-0042 Decision 4 + ADR-0036 1-anomaly = 1-state-change/24h)。
pub mod health;
// IBKR Phase 2 P1（AMD-2026-07-08-01）：secret_slot_contract fingerprint-only 純
// loader（scaffold-only leg，0 production caller；consumers = P5 attestation /
// healthcheck 於後續 phase 接入）。
pub mod ibkr_secret_slot_loader;
// IBKR Phase 2 P2/W2（AMD-2026-07-11-01）：external-surface gate producer + standalone
// `ibkr_phase2_seal` local control. Default is dry-run; immutable ledger writes require the
// bin's --apply plus OPENCLAW_IBKR_PHASE2_SEAL_APPLY=1 and owner-only typed inputs. It is not
// an activation/contact caller; boot, IPC, DB, GUI, and TWS remain outside this module.
pub mod ibkr_phase2_gate_producer;
// IBKR W3 TWS wire 層（W3-S1）：B1 §(a) 純 codec 抽此 + FrameReader（滾動窗 framing）+
// 錯誤分類橋 + timeout 正規化；無 I/O、無 socket、無 FSM。與 B1 同屬 default build 被 DCE 的
// TWS 連接器面（ibkr_g4_symbol_audit.sh 驗證符號缺席）。
pub mod ibkr_tws_wire;
// IBKR W3 TWS session FSM（W3-S2）：六態可恢復狀態機 + full-jitter 退避 + reqCurrentTime 心跳 +
// 排程感知（nightly restart / 週日重認證,America/New_York DST 由 chrono-tz 解）+ INV-1 connect-permit
// 掛點（EnvelopeRequiredStub 恆拒,W8 前無放行）。無 socket、無 async;純同步狀態機（注入時鐘/RNG）。
// 與 B1/wire 同屬 default build 被 DCE 的 TWS 連接器面（0 production caller;W4 IPC 才接消費者）。
pub mod ibkr_tws_session;
// IBKR W3 TWS pacing governor（W3-S3）：所有出站 framed 訊息的單一出口——主 msg-rate token
// bucket（rate = market_data_lines ÷ 2）+ 獨立 historical bucket（IB 現勘四規則）+ subscription
// lines 併發配額 + 有界排隊裁決（bounded FIFO,溢出/逾時即拒,禁無界排隊=OOM 教訓、禁 silent
// drop;order-verb 超限直拒不排隊）+ IB error-100 三次違規斷 session strike 計數。OutboundGrant
// 單一出口證明（mint 模塊私有）令出站送出編譯期必經 governor。S2 心跳出站經此接線。純同步、
// 注入時鐘、無 socket。與 B1/wire/session 同屬 default build 被 DCE 的 TWS 連接器面。
pub mod ibkr_tws_pacing;
// IBKR W3 TWS session driver（W3-S4）：端到端讀迴圈——承 B1 driver 範式,把 wire(S1)+FSM(S2)+
// pacing(S3) 用注入 TransportFactory（fake=tokio duplex / W8=TCP）串成 permit→connect→握手→Ready→
// 心跳（過 governor 單一出口 send_framed）→ 故障→重連對賬。production 恆撞 EnvelopeRequiredStub 停
// Disconnected（INV-1;granting provider 僅測試域）。零真 socket、零 production caller（W4 IPC 才接）→
// 與 B1/wire/session/pacing 同屬 default build 被 DCE 的 TWS 連接器面（g4 + fake 缺席審計驗證）。
pub mod ibkr_tws_driver;
// IBKR W5-S2 account/positions 消化層：reqAccountSummary/reqPositions 訂閱生命週期狀態機 +
// 入站行消化（W5-S1 typed row 契約,先契約後消化禁裸 map）+ typed staleness。G1 version 門控
//（position v<3 拒/serverVersion<101 blocker）、G2 哨兵 config 守衛、G3 單訂閱結構性不變量。
// 出站經 pacing 單一出口（OutboundClass::AccountData）。純同步、注入時鐘、零 socket——與
// wire/session/pacing/driver 同屬 default build 被 DCE 的 TWS 連接器面（B′ 姿態,g4 audit 保綠）。
pub mod ibkr_tws_account_data;
// IBKR W5-S3 open orders/executions/commissions 消化層：reqExecutions/reqOpenOrders/
// reqAllOpenOrders 唯讀對賬快照+推送恆在通道（End 界定;unsolicited reqId 承接計數禁丟棄）+
// W5-S1 executions/commissions row 契約消化 + exec↔commission execId either-order join（孤兒
// TTL 計量）+ orderStatus/openOrder head-prefix 最小 typed 快照（冪等去重/tail-discard audit）。
// DIVERGENT-1 floor/ceiling serverVersion 佈局窗、realizedPNL 哨兵→None 雙判別、exec_time
// grammar 白名單全 config 化 fail-closed。出站經 pacing 單一出口（OutboundClass::AccountData
// 主桶）;**絕不含下單/改單/撤單 builder**。純同步、注入時鐘、零 socket——與
// wire/session/pacing/driver 同屬 default build 被 DCE 的 TWS 連接器面（B′ 姿態,g4 audit 保綠）。
pub mod ibkr_tws_order_exec_data;
// IBKR W6-S1 contract details 消化層：reqContractDetails 全限定 STK 查詢（v8 builder;模糊
// 查詢=伺服端遞增 hold 面,結構性不送）→ IN 10 decode（message-version 硬 pin ==8 +
// per-field sv 門控表 + secIdList bounded skip + longName unicode-escape 最小實作）→ W6-S1
// instrument identity row 契約（identity_hash sha256 於此鑄造,preimage 單一定義點在 types）
// → IN 52 End 界定快照;IN 18 bondContractData typed-ignore 記帳丟棄。請求 timeout typed 化
//（expire_overdue 非懸掛）+ 單槽六態 staleness/世代重評/cap/audit（沿 W6-S0 慣例）。出站經
// pacing 單一出口（OutboundClass::AccountData 主桶);零行情面（reqMktData/regulatorySnapshot
// 歸 W6-S3 紅線)。純同步、注入時鐘、零 socket——與 wire/session/pacing/driver 同屬 default
// build 被 DCE 的 TWS 連接器面（B′ 姿態,g4 audit 保綠）。
pub mod ibkr_tws_contract_data;
// IBKR W6-S3 market data lane 消化層：reqMktData/cancelMktData/reqMarketDataType builder
//（STK-only；**regulatorySnapshot 資金效果封死**=builder 級常量 false,每次 0.01 USD 且
// paper 亦計費,結構上非 caller 可控;snapshot⊥genericTickList）→ IN tick 家族 decode
//（TICK_PRICE 合成去重/TICK_SIZE 嚴格 5 欄/per-reqId entitlement FSM/delayed provenance
// 標記）→ W6-S3 quote row 契約 + snapshot 11s 終態 timeout + lines semaphore（訂閱數配額,
// 與 W3 rate bucket 分軸）。出站經 pacing 單一出口（OutboundClass::MarketData）;**絕不含
// 下單/改單/撤單 builder**。純同步、注入時鐘、零 socket——與 wire/session/pacing/driver
// 同屬 default build 被 DCE 的 TWS 連接器面（B′ 姿態,g4 audit 保綠）。
pub mod ibkr_tws_market_data;
// IBKR W6-S2 trading calendar 解析器：消化 W6-S1 identity row 的 tradingHours/liquidHours/
// timeZoneId 原字串 → typed `IbkrTradingCalendarV1`(有序 session + 規範化 IANA tz +
// calendar_hash)。雙 grammar(TWS ≤969 舊 / 970+ 新)+ legacy→IANA 白名單映射(未知 fail-
// closed 拒)+ DST-aware 絕對時刻(chrono-tz 依 IANA tz 解,禁手寫偏移;跨午夜解次日)。
// `compute_calendar_hash` 導出供 W6-S3 provenance calendar_hash 綁真值(driver 接線 = S4)。
// 純函數、零 socket、零 I/O、零下單、零 wire——壞格式/未知 tz/亂序=typed blocker 不 panic。
pub mod ibkr_trading_calendar;
// IBKR W5-S4 session attestation producer：把 managedAccounts 實檢（DU* 白名單;
// `account_fingerprint_is_live` 禁聲明自填,唯一鑄造點=wire `managed_accounts_inspect`）+
// session 事實收斂為 typed `IbkrSessionAttestationV1`;契約 validate 全綠才產 attested 態,
// facts 缺席只可產 Blocked。純函數、注入時鐘、零 socket;production caller=W4 health emitter
// 的 Blocked 投影（不引用 driver → driver-absence audit 邊界不變）;attested 全路徑真消費=
// W6 IPC 投影。attestation 絕非活化授權（真活化=W8 envelope）。
pub mod ibkr_tws_session_attestation;
// IBKR W8a activation envelope 驗證器（readonly-scope 最小切片,AMD-2026-07-11-01 活化
// 鐵律消費面）：types `ibkr_activation_envelope_v1` shape 校驗 + build SHA/revocation/
// kill-switch epoch 姿態比對 + readonly order-verb 結構性拒 + seal≠活化 + nonce 原子消費
//（Mutex 帳本,防 replay）。**只驗不發**（簽發=EA 跑道 Operator 動作）;R16 起首個
// production caller = G4 readonly entry（feature `ibkr_g4_contact` gated;default build
// 仍零 caller/DCE）;不 impl ConnectPermitProvider、不觸 PermitToken——INV-1 不受影響;
// W8 全包以本驗證器替換 permit trait 位並吸收（共路徑,禁兩套語義漂移）。
pub mod ibkr_activation_envelope_check;
// IBKR W7-S0 order-verb transport-gating 骨架（恆拒地基，設計 §1 INV-ORDER）：在 pacing 單一出口
// （OutboundGrant，W3-S3）之上為 order-verb 出站增第二把型別鎖——`OrderFrame` newtype（bytes 私有，
// 唯 send_order_framed 可取，型別上非通用 frame）+ production 不可鑄的 `OrderEffectPermit`
// （mint 為 #[cfg(test)]，production 恆無 permit）+ 恆拒 provider `EffectEnvelopeRequiredStub`
// （對應 connect 面 EnvelopeRequiredStub，但兩線獨立）+ `broker_capability_registry_v1` machine-check
// （消費既有 types 契約，ADR 硬序閘）。**S0 = 恆拒地基，放行臂 S4、encoder S1**：不含任何 order
// encoder、不送任何 order 訊息、無放行臂。INV-ORDER 二元證明:permit production 零鑄造 + 0 production
// caller → default build DCE（沿 driver/g4 audit 家族）;不 impl ConnectPermitProvider、不觸 PermitToken
// → INV-1 不受影響。純同步、零 socket、零下單。
pub mod ibkr_tws_order_transport;
// IBKR W7-S1 訂單生命週期 runtime driver + append-only intent journal（不送出）：14-態狀態機
// 消費 openclaw_types 遷移矩陣（is_transition_allowed / is_operation_transition_allowed），單一
// mutator `apply_lifecycle_event`（Bybit 幻影倉教訓:絕無第二狀態寫入路徑;fill/cancel 共用、
// reduce-only fail-closed）+ hash-chain 意圖日誌 + nextValidId 管理（本地遞增,冪等真源=
// idempotency_key 非漂移的 order-id）+ ApiPending transient-pending 有界 timeout 分流 + 重啟
// recovery（未終態 → MarkStateUnknown）。純同步、注入時鐘、零 socket / 零 async / 零下單出線。
pub mod ibkr_tws_order_lifecycle;
// IBKR W7-S2 cash 約束引擎（deterministic pre-submit gate）：跑在 Rust authority accept 之後、
// order frame build 之前的最後一道 cash-correctness 閘。窮舉七道 gate（settled-funds T+1 台帳 /
// GFV free-riding / no-short 硬邊界 / RTH-only / order-type 白名單 LMT/MKT×DAY / fractional 拒 /
// LULD-halt pre-trade filter）;任一不確定即 fail-closed 拒。官方數值全歸 `CashAccountRules` 注入
// （T+1/GFV/LULD/RTH/order-type 待 IB 现勘,引擎不硬編）。純函數、注入時鐘 + config、零 socket/async/
// send（不觸 transport,INV-ORDER/INV-1 恆 HOLD）。default build DCE（真接線=S4 IPC submit handler）。
pub mod ibkr_cash_account_constraints;
// IBKR W7-S3 三向對賬引擎（P0 核心;Bybit 幻影倉根因防線）：broker 真值（reqOpenOrders+
// reqExecutions,W5-S3 唯讀 builder）× intent journal（S1）× 本地態三向對賬。無序 join tolerant
// （idempotency_key 優先 / order-id fallback / 孤兒 fail-closed 禁丟棄=P0-C）;差異 fail-closed;
// reduce-only 幻影防線經 S1 單一 mutator（P0-A）;unknown-terminal → ManualReview + 凍結 symbol
// （P0-B）;E2-LOW-2 結算台帳 disjoint 不變量（承 S2 carry）。純函數、注入時鐘、零 socket/async/
// send（不觸 transport,INV-ORDER/INV-1 恆 HOLD;一切遷移唯經 S1 mutator）。default build DCE
// （真接線=S4 IPC reconcile 迴路）。
pub mod ibkr_order_reconciliation;
// IBKR B1 只讀 TWS 連接器（ADR-0048 / AMD-2026-07-08-01，G4 首次接觸）：connect handshake
// + reqCurrentTime 最小首接觸；純 codec + generic driver + 3 層惰性 gate；唯一具體
// TcpStream::connect 於 `ibkr_g4_contact` feature 後（default build 無 socket、無 caller）。
pub mod ibkr_readonly_tws_client;
pub mod instrument_info;
pub mod intent_processor;
pub mod ipc_server;
pub mod linucb;
pub mod live_authorization;
// LG-2 T2 (2026-05-11)：Live spawn pricing binding assertion module。
// build_exchange_pipeline 對 Live (Mainnet + LiveDemo) 路徑加裝的 pre-check。
pub mod live_spawn_assert;
pub mod market_data_client;
pub mod ml;
pub mod mode_state;
// Sprint 1A-δ M5：ModelClient trait stub（6 method default panic）per ADR-0035。
pub mod model_client;
pub mod multi_interval_topics;
pub mod news;
// Wave 5 Packet C engine integration (2026-05-28) — wires
// `RiskEvent::NotificationFailsafeTimeout` to engine副作用鏈：3-way fail observe
// → 1h timer → SM-04 Defensive → active lock-profit → exchange conditional SL
// sync → audit emit `auto_escalated_to_sm04_defensive`。純邏輯 + 5 trait seam
// + 14 條 unit/integration mock 測試；尚未接 pipeline_ctor / tasks (下一 wave)。
pub mod notification_failsafe;
pub mod orchestrator;
pub mod order_manager;
// Sprint 1A-δ M12：OrderRouter trait stub（6 method default panic）per ADR-0039。
pub mod order_router;
pub mod paper_state;
// Sprint N+1 W1 + W2：cross-asset / cross-strategy panel aggregator namespace
// （funding_curve / oi_delta / btc_lead_lag panel collector + producer）。
pub mod panel_aggregator;
pub mod persistence;
pub mod pipeline_types;
pub mod platform_client;
pub mod position_manager;
pub mod position_reconciler;
pub mod position_risk_evaluator;
pub mod regime;
// REF-20 Wave 1 R20-P0-T3 — replay subsystem scaffold (spec only, no IMPL).
// Wave 3 R20-P2b-S7/S8/S9/S10 will add forbidden_guard + mac_policy_guard.
// REF-20 Wave 1 R20-P0-T3 — replay 子系統骨架（純規格，無 IMPL）。
// Wave 3 R20-P2b-S7/S8/S9/S10 將加 forbidden_guard + mac_policy_guard。
pub mod replay;
pub mod restart_kind;
pub mod risk_checks;
pub mod risk_cusum;
pub mod scanner;
pub mod secret_env;
// P0-LG-3 Wave 2.4.A T4：supervised-live 不可變稽核軌跡 writer（V104 supervised_live_audit）。
// T1 後續另加 `pub mod supervised_live_sm;`（SM 核心），兩者檔案零 overlap。
pub mod strategies;
pub mod strategist_scheduler;
pub mod supervised_live_audit_writer;
// LG-3 Wave 2.4.A T1（2026-05-30）：supervised-live 7-state 狀態機核心。
// supervised-live session 的 control-plane meta state（SoT #1）+ 30s 5-SoT 對賬
// reconciler。純狀態機，不下單、不繞 5-gate live 邊界、不繞 Decision Lease；
// audit 經 `AuditSink` trait seam 接 T4 的 V104 writer（T1 不寫 V104/writer 本體）。
pub mod supervised_live_sm;
pub mod tick_pipeline;
pub mod ws_client;
pub mod ws_unknown_handler_guard;

pub use openclaw_core;
pub use openclaw_types;

// P1-OPS-2-CI-FLAKINESS-TEST-LOCK（2026-05-29）：全 crate 共用的 env-mutating
// 測試互鎖。
//
// 為什麼必要：`cargo test --lib` 把 lib crate 的所有 `#[cfg(test)]` 測試編進
// 「單一」測試 binary，預設多執行緒並行跑。`std::env::set_var` /
// `std::env::remove_var` 是 process 全局且非執行緒安全（Rust 2024 起更直接
// 標 set_var 為 unsafe）。若各 module 各自宣告一把 local Mutex，A module 持
// 自己的鎖並不會排除 B module 持「另一把」鎖 → 兩者同時改 process env 仍 race
// （latent；24/24 實測未觸但 UB 存在）。本 module 提供單一入口，所有 lib 測試
// 統一鎖它，跨 module 真正串行。
//
// 邊界：僅涵蓋 lib 測試 binary。bin crate（main.rs + main_boot_tasks /
// live_auth_watcher / startup 等 `mod` 兄弟）是「獨立」compilation unit + 獨立
// 測試 process，無法存取本 `#[cfg(test)]` pub(crate) 項，也不與 lib 測試共享
// static，故不在此鎖範圍內（各自仍用其 module-local guard）。
#[cfg(test)]
pub(crate) mod test_env_lock {
    /// 全 crate（lib 測試 binary）唯一的 env-mutating 測試互鎖。
    static ENV_TEST_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

    /// 取共用鎖；poisoned（前一測試 panic 留下）時用 `into_inner` 強解 —
    /// 測試場景下毒化不影響 prod，且強解才能讓後續測試繼續串行而非連鎖 panic。
    pub(crate) fn guard() -> std::sync::MutexGuard<'static, ()> {
        ENV_TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner())
    }
}
