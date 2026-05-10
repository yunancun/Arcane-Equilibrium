# W2 IMPL sub-task 4 (E1-δ C-IMPL-2 final wire) — IMPL DONE Report

**Date**: 2026-05-11
**Agent**: E1 (Backend Developer, sub-agent)
**Wave**: Sprint N+1 W2 W-AUDIT-8c candidate fast-track BTC→Alt Lead-Lag — final wire
**Spec**: `srv/docs/execution_plan/2026-05-10--a4c_btc_alt_lead_lag_spec.md` v1.2 + dispatch v3.7 §3.1 chunk 4
**Branch**: main, **12 file staged 不 commit**（待 E2 + A3 + E4 audit；W-C Caveat 2 sibling WIP 共存於 working tree 不在我 scope）
**Reports linked**:
- W2 sub-task 1 (BtcLeadLagProducer + V088 writer): `2026-05-11--w2_impl_2_btc_lead_lag_producer_v088_writer.md`
- W1 sub-task 3 (panel_aggregator main loop, IPC slot pattern reference): commit `ddf0cebe`
- PA dispatch v3.7: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--sprint_n1_dispatch_draft.md`
- PA W1+W2 trait coordination: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-10--alpha_surface_trait_final_shape_w1_w2_coord.md`

---

## §1 任務摘要

把 W2 sub-task 1 (atomic commit `3d0ea347`) land 的「孤立 BtcLeadLagProducer」走到「runtime 真實 spawn + IPC slot late-inject + step_4_5_dispatch 從 surface.btc_lead_lag wire 通」三步完成。

**Sub-task scope (per dispatch v3.7 §3.1 chunk 4)**:
1. **IPC slot late-inject**: `BtcLeadLagPanelSlot = Arc<RwLock<Option<BtcLeadLagPanel>>>` typedef + IpcServer field/accessor/setter + re-export
2. **main.rs spawn**: BtcLeadLagProducer.run_loop pull pattern (60s timer 從 PG market.klines 拉 BTCUSDT + 7-sym alt cohort 1m close/volume) + slot 注入 IpcServer + 共享 cancel
3. **step_4_5_dispatch wire-up**: TickPipeline 加 btc_lead_lag_panel_slot field + ctor default None + setter；surface 構造改 paper-only fence (effective_engine_mode == "paper" → try_read else None) + AlphaSurface struct update syntax
4. **Unit tests**: 8 新增（IPC slot late-inject smoke + adaptor + PG INSERT fail-soft + run_loop cancel + cohort accessor）

---

## §2 修改清單（12 staged files, mine; W-C Caveat 2 sibling 改動同檔不歸屬）

| File | LOC delta (mine) | Description |
|---|---|---|
| `rust/openclaw_engine/src/ipc_server/slots.rs` | +21 | `BtcLeadLagPanelSlot` typedef at PA 預留 anchor (W2 insertion point) |
| `rust/openclaw_engine/src/ipc_server/mod.rs` | +1 | re-export `BtcLeadLagPanelSlot` |
| `rust/openclaw_engine/src/ipc_server/server.rs` | +33 | IpcServer `btc_lead_lag_panel` field + ctor default None + accessor + setter (鏡射 W1 funding_curve_panel pattern) |
| `rust/openclaw_engine/src/panel_aggregator/btc_lead_lag.rs` | +479 | `run_loop()` method (pull pattern 60s timer, PG market.klines fetch, INSERT V088, write IPC slot) + `snapshot_to_trait_panel()` adaptor + `insert_btc_lead_lag_snapshot()` writer + `create_btc_lead_lag_panel_slot()` factory + `cohort_symbols()` accessor + 7 new unit tests |
| `rust/openclaw_engine/src/panel_aggregator/mod.rs` | +12 | `create_btc_lead_lag_slot()` factory + import `BtcLeadLagPanelSlot` |
| `rust/openclaw_engine/src/main.rs` | +61 | `btc_lead_lag_alt_cohort()` (7 sym hardcoded per spec §2.2, BUSDT 排除 per ADR-0018) + slot 預建 + 注入 IpcServer + spawn BtcLeadLagProducer.run_loop 與 PanelAggregator 平行 + slot Arc clone for PipelineSpawnContext |
| `rust/openclaw_engine/src/main_pipelines.rs` | +28 | PipelineSpawnContext + LiveSpawnBundle 加 `btc_lead_lag_panel_slot` field + 三 spawn fn (paper/demo/live) + build_live_pipeline_spawner closure 全 propagate slot |
| `rust/openclaw_engine/src/event_consumer/types.rs` | +33 | EventConsumerDeps 加 `btc_lead_lag_panel_slot` field |
| `rust/openclaw_engine/src/event_consumer/bootstrap.rs` | +12 | destructure `btc_lead_lag_panel_slot` + `pipeline.set_btc_lead_lag_panel_slot(slot)` 緊跟 set_endpoint_env |
| `rust/openclaw_engine/src/tick_pipeline/mod.rs` | +26 | TickPipeline 加 `btc_lead_lag_panel_slot: Option<BtcLeadLagPanelSlot>` field + docstring |
| `rust/openclaw_engine/src/tick_pipeline/pipeline_ctor.rs` | +36 | with_balance ctor default None + `set_btc_lead_lag_panel_slot()` setter |
| `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs` | +30 (mine) | line 21 BtcLeadLagPanel import + line 189-216 surface 構造改 paper-only fence + AlphaSurface struct update syntax |

**Total mine LOC**: ~772 (含 7 unit tests, 注釋, struct field docstring)。
**主要產品 LOC** (without tests/docstring): ~250。

**Sibling W-C Caveat 2 hunks 不歸屬本 sub-task** (但同檔 working tree 共存):
- `step_4_5_dispatch.rs` line 626+ (~50 LOC): 4 個 Spine id 計算 + OrderDispatchRequest spine_* field 傳遞
- `step_4_5_dispatch.rs` line 1170+ (~10 LOC): paper shadow order 4 Spine id None
- 其他 `agent_spine/` `event_consumer/dispatch.rs` `loop_exchange.rs` `pending_sweep.rs` `tick_pipeline/commands.rs` `tick_pipeline/tests/dual_rail_dispatch.rs` 等 working tree unstaged，**不歸屬本 sub-task**

---

## §3 關鍵 diff

### §3.1 IPC slot typedef (slots.rs PA 預留 anchor)

```rust
/// W2 sub-task 4 (E1-δ, 2026-05-11): late-injected slot for BtcLeadLagPanel。
///
/// MODULE_NOTE：BtcLeadLagProducer run loop 每 60s tick 寫此 slot；下游
///   step_4_5_dispatch 在 paper-only fence 通過後 `try_read().ok()` 取
///   Option<BtcLeadLagPanel> 賽進 surface.btc_lead_lag。slot type 用 trait 端
///   `BtcLeadLagPanel` 而非 producer 端 `BtcLeadLagPanelSnapshot` — producer
///   負責 snapshot → trait struct adaptor，IPC slot 對齊 trait 契約。
pub type BtcLeadLagPanelSlot =
    Arc<RwLock<Option<openclaw_core::alpha_surface::BtcLeadLagPanel>>>;
```

### §3.2 main.rs spawn pattern (與 PanelAggregator 平行)

```rust
let btc_lead_lag_db_pool = Arc::clone(&db_pool);
let btc_lead_lag_cancel = cancel.clone();
let btc_lead_lag_alt_cohort_vec = btc_lead_lag_alt_cohort();
let btc_lead_lag_slot_for_producer = Arc::clone(&btc_lead_lag_panel_slot);
let btc_lead_lag_producer =
    openclaw_engine::panel_aggregator::BtcLeadLagProducer::new(btc_lead_lag_alt_cohort_vec.clone());
let _btc_lead_lag_handle = tokio::spawn(async move {
    btc_lead_lag_producer
        .run_loop(btc_lead_lag_db_pool, btc_lead_lag_slot_for_producer, btc_lead_lag_cancel)
        .await;
});
```

### §3.3 BtcLeadLagProducer.run_loop core (pull pattern, fail-soft)

```rust
pub async fn run_loop(
    mut self,
    db_pool: Arc<DbPool>,
    slot: BtcLeadLagPanelSlot,
    cancel: CancellationToken,
) {
    let mut tick_timer = tokio::time::interval(Duration::from_secs(RUN_LOOP_TICK_SECS));
    tick_timer.tick().await; // skip first immediate tick
    loop {
        tokio::select! {
            _ = cancel.cancelled() => return,
            _ = tick_timer.tick() => {
                let snapshot_ts_ms = openclaw_core::now_ms() as i64;
                // 1. PG fetch BTCUSDT 1m close + volume
                let Some((btc_close, btc_volume)) = fetch_latest_kline_close_volume(&db_pool, "BTCUSDT").await else {
                    continue; // fail-soft skip tick
                };
                // 2. alt cohort closes
                let mut alt_closes = HashMap::with_capacity(self.cohort_symbols.len());
                for sym in self.cohort_symbols.clone() {
                    if let Some((close, _)) = fetch_latest_kline_close_volume(&db_pool, &sym).await {
                        alt_closes.insert(sym, close);
                    }
                }
                // 3. on_tick (lookahead-free; metric calc before push current tick)
                let snapshot = self.on_tick(snapshot_ts_ms, btc_close, btc_volume, &alt_closes);
                // 4. PG INSERT V088 (fail-soft)
                let _ = insert_btc_lead_lag_snapshot(&db_pool, &snapshot).await;
                // 5. snapshot → trait struct adaptor → write IPC slot
                let trait_panel = snapshot_to_trait_panel(&snapshot);
                *slot.write().await = Some(trait_panel);
            }
        }
    }
}
```

### §3.4 step_4_5_dispatch surface wire (paper-only fence Layer 1)

```rust
// W2 sub-task 4 (E1-δ, 2026-05-11) btc_lead_lag wire-up
// paper-only fence Layer 1（主防線，per spec §6.1）：
//   - effective_engine_mode() == "paper" → 從 IPC slot try_read 取 panel
//   - 其他 (demo / live_demo / live) → 永遠 None（fence 主防線拒絕讀 slot）
// try_read fail-soft：reader 永不被 writer block；contention 時 None
let btc_lead_lag_panel_owned: Option<BtcLeadLagPanel> = match em {
    "paper" => self
        .btc_lead_lag_panel_slot
        .as_ref()
        .and_then(|slot| slot.try_read().ok().and_then(|guard| guard.clone())),
    _ => None,
};
let alpha_surface = AlphaSurface {
    btc_lead_lag: btc_lead_lag_panel_owned.as_ref(),
    ..AlphaSurface::tier1_only(indicators, indicators_5m.as_ref())
};
```

### §3.5 snapshot_to_trait_panel adaptor (主信號 N=120 propagate, shadow value 不 leak)

```rust
pub fn snapshot_to_trait_panel(snapshot: &BtcLeadLagPanelSnapshot) -> BtcLeadLagPanel {
    BtcLeadLagPanel {
        alt_symbols: snapshot.alt_symbols.clone(),
        btc_lead_return_pct: snapshot.btc_lead_return_pct,
        lead_window_secs: snapshot.lead_window_secs, // 鎖定 LEAD_WINDOW_SECS_MAIN=120
        alt_xcorr: snapshot.alt_xcorr.clone(),
        alt_expected_dir: snapshot.alt_expected_dir.clone(),
        snapshot_ts_ms: snapshot.snapshot_ts_ms,
        source_tier: snapshot.source_tier.clone(),
    }
}
```

### §3.6 V088 INSERT writer (arrays_aligned invariant + ON CONFLICT)

```rust
pub(crate) async fn insert_btc_lead_lag_snapshot(
    pool: &Arc<DbPool>,
    snapshot: &BtcLeadLagPanelSnapshot,
) -> SingleInsertOutcome {
    if !snapshot.arrays_aligned() {
        warn!("arrays_aligned invariant violated, drop INSERT");
        return SingleInsertOutcome::Failed;
    }
    let alt_xcorr_f32: Vec<f32> = snapshot.alt_xcorr.iter().map(|v| *v as f32).collect();
    let alt_expected_dir_i16: Vec<i16> = snapshot.alt_expected_dir.iter().map(|v| *v as i16).collect();
    let query = sqlx::query::<Postgres>(
        "INSERT INTO panel.btc_lead_lag_panel \
         (snapshot_ts_ms, lead_window_secs, btc_lead_return_pct, ...) \
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12) \
         ON CONFLICT (snapshot_ts_ms, lead_window_secs) DO UPDATE SET ...",
    ).bind(snapshot.snapshot_ts_ms).bind(snapshot.lead_window_secs as i32).bind(snapshot.btc_lead_return_pct as f32)
     .bind(snapshot.btc_lead_return_pct_60s as f32).bind(snapshot.btc_lead_return_pct_300s as f32)
     .bind(snapshot.btc_volume_z as f32).bind(snapshot.btc_book_imbalance as f32)
     .bind(snapshot.alt_symbols.clone()).bind(alt_xcorr_f32).bind(alt_expected_dir_i16)
     .bind(snapshot.regime_tag.clone()).bind(snapshot.source_tier.clone());
    exec_single_insert(pool, "panel.btc_lead_lag_panel", query).await
}
```

---

## §4 治理對照（CLAUDE.md §二 16 原則 + DOC-08 §12 + 硬邊界）

| 原則 | 影響 | 結論 |
|---|---|---|
| 1. 單一寫入口 | 0 | producer 不發 trade intent；只寫 panel.btc_lead_lag_panel + IPC slot |
| 2. 讀寫分離 | 0 | step_4_5_dispatch hot path 用 try_read 不 block writer |
| 3. AI 輸出 ≠ 即時命令 | 0 | producer 是 alpha source data collector，不是 AI 決策 |
| 4. 策略不能繞過風控 | 0 | btc_lead_lag panel = alpha source；strategy 在 paper engine 接 = shadow log only |
| 5. 生存 > 利潤 | 0 | paper-only fence 三層深度防禦保證 demo/live engine 永遠 surface.btc_lead_lag = None，不污染 5 策略 demo edge baseline |
| 6. 失敗默認收縮 | OK | run_loop fail-soft（PG 不可用 → skip tick / arrays_aligned 違反 → drop INSERT / panel writer 失敗 → slot 仍寫保持 producer emit 語義）|
| 7. 學習 ≠ 改寫 Live | 0 | btc_lead_lag panel 寫 PG 不寫 strategy_params*.toml |
| 8. 交易可解釋 | OK | source_tier='cross_asset_btc_lead_lag' + V088 schema 12 column 完整可重建 |
| 9-16 (其他原則) | 0 | 不觸及 |

**硬邊界 5 項**:
- max_retries = 0：✓ 不變
- live_execution_allowed：✓ 不變
- execution_authority：✓ 不變
- system_mode：✓ 不變
- decision_lease：✓ 不變

**DOC-08 §12 不變量**:
- arrays_aligned (alt_symbols.len == alt_xcorr.len == alt_expected_dir.len)：✓ writer 端 invariant 強制（test 4）
- lead_window_secs == 120 主信號鎖定：✓ adaptor 透過 const propagate
- regime_tag ∈ {"normal", "extreme"}：✓ producer compute_regime_tag enforce
- source_tier == "cross_asset_btc_lead_lag"：✓ producer 端 hardcoded
- strict shift(N) lookahead-free：✓ producer push current tick **after** metric calc，整鏈 (snapshot → adaptor → slot → surface) 不 introduce future leak

**paper-only fence 三層深度防禦**（per PA spec §6 + W1+W2 trait coord §5）:
- **Layer 1 主防線**：step_4_5_dispatch.rs `match em { "paper" => ..., _ => None }` ✓ 本 sub-task IMPL
- **Layer 2 (slot 端)**：BtcLeadLagPanelSlot 不知 fence，producer 全局 emit ✓ 對齊 PA spec
- **Layer 3 (strategy 端)**：`if let Some(panel) = surface.btc_lead_lag` 隱式 None → skip ✓ 等待 W2 sub-task 2 (C-IMPL-3)

**Bybit API 字典手冊**（CLAUDE.md §八）：本 sub-task 不直接呼叫 Bybit V5；Producer 走 PG market.klines pull pattern（市場 1m kline 由既有 market_writer 寫入）。Future Python writer (per spec line 475) 會走 Bybit V5 直拉，本 sub-task 不在範圍。

**SQL Guard A/B/C** (CLAUDE.md §七)：V088 已 deployed (W2 sub-task 1 atomic commit `3d0ea347`)；本 sub-task 不新建 V### migration。

**§九 文件大小限制**：所有改動檔均 < 1500 LOC 警告線；btc_lead_lag.rs 從 775 → 1254 LOC（< 1500 警告線；含 大量 docstring 注釋 + 7 新增 unit tests，high cohesion 內聚）。step_4_5_dispatch.rs 從 1557 → 1646 (含 W-C Caveat 2 sibling)，本 sub-task mine 部分 +30 LOC，sibling +50 LOC，**處於 pre-existing baseline exception clause** (per CLAUDE.md §九)，需 PM Sign-off 接受 governance exception。

**§九 Singleton 表更新**：本 sub-task 加新 BtcLeadLagPanelSlot 是 IPC slot type alias，不是新 singleton（既有 slot pattern of W1 funding/oi 對齊）；無需更新 §九 表。

---

## §5 不確定之處 / Caveats（必讀，影響 E2 review judgment）

### CAVEAT 1: step_4_5_dispatch.rs 同檔 W-C Caveat 2 sibling 共存
- **影響**：working tree 該檔 +89 LOC = mine ~30 LOC (line 21 + 189-216) + W-C ~50 LOC (line 626+ 1170+) + 9 LOC 既有抽 var 改名
- **buildable verified**：cargo build --release + cargo test --release 2776 PASS = 兩段共存 0 functional regression
- **attribution clarity**：mine = paper-only fence + AlphaSurface struct update syntax；W-C = 4 個 Spine id 計算 + OrderDispatchRequest spine_* field
- **E2 review 建議**：分別評估 mine vs W-C 兩段；W-C Caveat 2 sub-agent (per W-C fix Rust IMPL `2026-05-11--w_c_fix_rust_impl.md`) 應有獨立 audit
- **PM commit 建議**：兩段同 commit ok（W-C+W2-IMPL-5 同 wave window），但 message 必明標兩 sub-task 各自 contribution

### CAVEAT 2: 12 staged files 不含 test 行為修改
- **stage list**：12 file 全 production code + 1 test file (panel_aggregator/btc_lead_lag.rs 含 7 新增 unit tests in `#[cfg(test)] mod tests`)
- **未 stage 的 sibling working tree files**：`agent_spine/`, `event_consumer/{dispatch,loop_exchange,pending_sweep}.rs`, `event_consumer/handlers/tests.rs`, `event_consumer/tests/{mod,handlers_paper_cmd_tests,pending_registration_order_type_tests}.rs`, `tick_pipeline/commands.rs`, `tick_pipeline/tests/dual_rail_dispatch.rs`, `helper_scripts/db/{passive_wait_healthcheck/checks_agent_spine.py, test_agent_spine_healthcheck.py}` — 這些是 W-C Caveat 2 / W2-IMPL-3 sibling sub-agent 改動，**不歸屬本 sub-task**

### CAVEAT 3: PG market.klines pull pattern 對網路 / 量交流 RPS 影響
- run_loop 60s tick × (1 BTC + 7 alt) = 8 query/min（well under PG conn pool budget）
- 每 query 是 SELECT close, volume FROM market.klines WHERE ... ORDER BY ts DESC LIMIT 1 — 用 `(symbol, timeframe, ts)` PK index（既有 V002 schema）必 sub-ms
- pool 不可用 → fail-soft skip tick（producer 端 .latest() 維持上次 emit）
- **未驗證**: Linux PG production load 下 8 query/min × N producer pipeline 的 conn pool pressure；建議 N+1 D+1 deploy 後 24h 觀察 db_pool 統計

### CAVEAT 4: snapshot_ts_ms 對齊 1m grain
- producer run_loop tick 用 `now_ms()` epoch ms，**不對齊 1m bucket boundary**（不是 60_000 整數倍）
- spec §4.1 V088 schema 註：「snapshot_ts_ms BIGINT, 1m grain」是 **1m frequency 不是 1m alignment**；ON CONFLICT (snapshot_ts_ms, lead_window_secs) 在隨機 ts 不會撞，但 panel data 7d window 取樣有 ~1ms jitter
- **設計取捨**：嚴格 1m boundary 對 panel 信號質量影響微小（lead_window_secs=120s 內 ms-level jitter 可忽略），但 `tokio::time::interval` 已 enforce ~60s tick 間隔。如後續 evidence collection 需 strict 1m alignment，可加 `align_to_minute_boundary(ts) = (ts / 60_000) * 60_000`
- **未驗證**: Bybit V5 1m kline 寫 PG 的 ts 是 align bucket 的 (00:01:00.000 / 00:02:00.000)；producer 用 `now_ms()` 拉 close 時可能拿到「上次 align bucket 的 close」（最多 60s 舊）— W2 sub-task 1 spec §3.1 lead window 120s，舊 60s 在容忍範圍

### CAVEAT 5: Linux PG dry-run V088 idempotency 未驗證
- V088 已 deployed（per W2 sub-task 1 commit `3d0ea347`）
- 本 sub-task 不新增 migration
- 但 INSERT V088 ON CONFLICT 的 idempotency 未在 Linux 真實 PG empirical query 測試（per `feedback_v_migration_pg_dry_run`）
- **建議**：E4 regression 階段在 Linux trade-core 跑 `restart_all --rebuild` 後驗 panel.btc_lead_lag_panel 5min 內有新 row 寫入

---

## §6 Operator 下一步

### 6.1 E2 review (代碼審查) - 必跑
- **scope**: 12 staged files + 5 caveats（特別 Caveat 1 W-C Caveat 2 attribution）
- **focus**:
  - paper-only fence Layer 1 (step_4_5_dispatch.rs:189-216) 對齊 PA spec §6.1
  - try_read pattern 在 sync on_tick path 正確性（無 await deadlock 風險）
  - AlphaSurface struct update syntax (`..tier1_only(...)`) lifetime 'a 傳遞正確
  - V088 INSERT bind type 對齊 schema (REAL = f32, SMALLINT[] = i16[], BIGINT = i64)
  - arrays_aligned invariant 違反 fail-soft 不 panic
- **expected**: APPROVE 或 push back specific hunk（不阻 W-C Caveat 2 sibling）

### 6.2 A3 strategy interaction review - 必跑
- **scope**: AlphaSurface.btc_lead_lag = Some(&panel) 時 strategy on_tick 行為（W2 sub-task 2 CrossAsset tag 接收方）
- **focus**:
  - paper engine mode strategy on_tick 是否正確 fail-closed when surface.btc_lead_lag.is_none()
  - declared CrossAsset tag 與 surface.btc_lead_lag.is_some() 對齊
- **note**: 本 sub-task 不改 strategy 端；A3 review 是「W2 sub-task 4 wire 是否 strategy-ready」前置

### 6.3 E4 regression (Linux runtime smoke) - 必跑
- **scope**: 本 sub-task land 後 engine restart `restart_all --rebuild` smoke
- **expected**:
  - `[40] avg_net_bps` 不退化（paper-only fence Layer 1 阻 demo/live 讀 panel）
  - `panel.btc_lead_lag_panel` 5min 內有新 row 寫入（producer run_loop tick 工作）
  - `BtcLeadLagPanelSlot` IPC slot late-inject 成功（log `BtcLeadLagProducer spawning ...`）
  - 0 crash
- **PG 直查 verify**:
  ```sql
  SELECT COUNT(*), MAX(snapshot_ts_ms),
    EXTRACT(EPOCH FROM NOW()) * 1000 - MAX(snapshot_ts_ms) AS staleness_ms
  FROM panel.btc_lead_lag_panel
  WHERE snapshot_ts_ms > (EXTRACT(EPOCH FROM NOW()) * 1000)::BIGINT - 600000;
  -- expect: COUNT >= 5, staleness_ms < 70000
  ```

### 6.4 PM commit window
- **建議**: W2-IMPL-5 + W-C Caveat 2 + W2-IMPL-3 strategy paper shadow log + 任何 sibling sub-agent 同 wave 一起 commit（避免單獨 W2-IMPL-5 commit 漏接 W-C Caveat 2 PendingOrder 鏡射 fix）
- **commit message 建議**:
  ```
  W2 IMPL sub-task 4 + W-C Caveat 2 fix + W2-IMPL-3 strategy shadow log
  - W2-IMPL-5 (E1-δ): BtcLeadLagPanelSlot late-inject + main.rs spawn + step_4_5_dispatch wire (12 file, ~250 LOC mine + 7 unit tests)
  - W-C Caveat 2 (sibling sub-agent): Spine id propagation step_4_5_dispatch + agent_spine + event_consumer
  - W2-IMPL-3 (sibling sub-agent): ma_crossover + grid_trading paper shadow log if reaches dispatch v3.7 §3.1 chunk 5
  Co-Authored-By: Claude Opus 4.7 <noreply@anthropic.com>
  ```

### 6.5 後續 W2 + PA dispatch hints
- **W2 sub-task 2 (C-IMPL-3) strategy paper-only shadow log**: ma_crossover + grid_trading 在 paper engine mode 接 `BtcAltLeadLag` 為 `CrossAsset` tag, on_tick `if let Some(panel) = surface.btc_lead_lag { shadow_log(panel); }`
- **PA D+1 W1 surface wire-up**: funding_curve_panel + oi_delta_panel 在 step_4_5_dispatch 從 PanelAggregator slot pair `try_read` 賽進 surface（同 pattern with W2 btc_lead_lag）
- **healthcheck [69] btc_lead_lag_panel_writer_active**: 加入 helper_scripts/db/passive_wait_healthcheck cycle，N+1 D+5 監控 panel.btc_lead_lag_panel rows >= expected per 5min（60s tick × 5 = ~5 rows/5min；< expected → producer dormant alert）

---

## §7 Status

**E1 IMPLEMENTATION DONE: 待 E2 審查 (report path: srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-11--w2_impl_5_ipc_slot_main_spawn_step_4_5_wire.md)**

**Test results (release)**:
- panel_aggregator: 49/49 PASS（含 7 W2 sub-task 4 新增）
- tick_pipeline: 166/166 PASS
- alpha_surface: 9/9 PASS
- **lib full**: 2776/2776 PASS, 0 failed, 0 ignored
- cargo build --release: clean (10.75s, 2 既有 dead_code warnings)

**Files staged (12)**: 見 §2 表
**Not committed**: 等 E2 + A3 + E4 三方 PASS + PM commit window
**Sibling W-C Caveat 2 unstaged sub-agent WIP**: working tree 共存，不歸屬本 sub-task scope（CAVEAT 1）
