---
report: PA design — Sprint 5+ Wave 1 §8.3 §4.2.2-4 cascade
date: 2026-05-23
author: PA
phase: Sprint 5+ Wave 1 (per Stage F §8.3 carry-over)
status: DESIGN-DONE-DISPATCH-READY
parent:
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--stage_a_to_e_overall_acceptance.md §8.3
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_4_first_live_carryover_pm_phase_3e_signoff.md §4.2
  - srv/docs/architecture/singleton-registry.md §6.1-§6.4 (4 carry-over)
spec_artifacts_planned:
  - srv/docs/execution_plan/specs/2026-05-23--sprint5_wave1_4_2_2_portfolio_state_cache_paper_state_ssot.md (新, ~400 LOC spec, E1 IMPL ~150-200 LOC)
  - srv/docs/governance_dev/templates/2026-05-23--pa_drift_lesson_template.md (新, ~200 LOC template + 6 PA-DRIFT lessons 摘要)
  - 無 §4.2.3 新 spec — Push back operator scope (詳 §3)
risk_grade: 中 (§4.2.2 P1 接 PaperState pipeline 獨佔邊界；§4.2.3 §4.2.4 P2 純 doc)
boundaries_touched: 0 hard / 16 原則 16/16 / DOC-08 §12 9/9
---

# §1 Executive Summary

§8.3 3 items 設計交付 + 對抗 operator scope 漂移 push back：

| # | item | PA verdict | IMPL phase scope |
|---|---|---|---|
| §4.2.2 | PortfolioStateCache PaperState SSOT 接線 | **DISPATCH-READY**（disk JSON SSOT 路徑解 pipeline 獨佔邊界）| E1 ~150-200 LOC 新 reader fn + spawn_portfolio_state_update_task fill-in；4-6 hr |
| §4.2.3 | archive **4 條 Python singleton** re-ingest（不是 sandbox stub）| **PUSH BACK + DISPATCH-READY**（operator prompt scope 漂移 — 真實任務是 doc-only ingest 4 條到 singleton-registry.md）| TW ~1-2 hr doc audit + entry append；無新 IMPL |
| §4.2.4 | dispatch template + PA-DRIFT lesson template | **DISPATCH-READY**（兩個獨立 doc：(a) PM dispatch boilerplate amend「新 singleton 預登記」+ (b) governance lesson template + 6 PA-DRIFT lessons 摘要）| PA + TW ~1.5-2 hr doc-only |

**核心 push back 1 條（強）**：operator prompt §4.2.3 把「sandbox `learning.hypotheses` stub conflict cleanup」誤併入 archive Python re-ingest scope。
- **真實 §4.2.3 (per singleton-registry.md §6.1)**：archive 4 條 Python singleton（`_H_STATE_INVALIDATOR` / `MARKET_SCANNER` / `HStateCacheSlot` / `CostEdgeAdvisorDbSlot`）re-ingest 到 `docs/architecture/singleton-registry.md` SSOT。**Owner: TW + PA。doc-only 無 IMPL。**
- **sandbox stub cleanup 是 §8.8（per Stage F §8.8 routing）**：由 **E3 + operator** 跑 9-step sandbox empirical chain + DROP TABLE CASCADE + 重 apply V100 → V103 chain；屬 sandbox empirical hygiene；**不是本 PA scope；不入 Sprint 5+ Wave 1 cascade**。
- **混淆危險**：若 PM dispatch 把 sandbox stub cleanup 派給 E1，會撞 §四 sandbox 操作硬約束（secret_file 0600 + sandbox_admin role + 9-step chain）；E1 無此授權；走 E3 ssh trade-core 路徑才合規。

**3 items 全合規**：16 原則 16/16；DOC-08 §12 9/9；0 硬邊界觸碰；改動風險 §4.2.2 中（pipeline_snapshot disk JSON read 引新 dep）/ §4.2.3 §4.2.4 低（純 doc）。

**Phase B E1 IMPL split 推薦**：3 items 互不重疊 file scope，可並行 3 sub-agent（E1 §4.2.2 / TW §4.2.3 / PA+TW §4.2.4）；但 operator 指示 4-5 hr single-thread → 走 sequential 派發即可（§4.2.2 E1 IMPL → E2 review → TW §4.2.3 + PA §4.2.4 doc-only 並行）。

---

# §2 §4.2.2 PortfolioStateCache PaperState SSOT 接線設計

## §2.1 既有狀態（Wave B 留下 placeholder no-op）

per `rust/openclaw_engine/src/main_health_emitters.rs:549-598`（Wave B IMPL commit 245216d1）：

```rust
pub(crate) fn spawn_portfolio_state_update_task(
    cache: Arc<ParkingMutex<PortfolioStateCache>>,
    cancel: &CancellationToken,
) {
    // ... 300s tick ...
    let equity_usd = 0.0_f64;                              // ← placeholder no-op
    let new_fills: Vec<(u64, f64)> = Vec::new();           // ← placeholder no-op
    let latest_exposures: Vec<PositionExposure> = Vec::new(); // ← placeholder no-op
    guard.update_from_pipeline_snapshot(now_ms, equity_usd, &new_fills, latest_exposures);
}
```

Wave B 設計注釋（line 515-535）顯示 PA 已知 3 個 SSOT 接入點全部不可走：
1. PaperState 在每個 TickPipeline 內部 own，main.rs 外無共享 Arc。
2. `trading_tx mpsc::Sender<TradingMsg>` 走 trading_writer → DB；無旁路 subscribe channel。
3. `positions_mirror` 只暴露 `HashMap<symbol, is_long>`，不含 qty / entry_price / unrealized_pnl。

V106 row 5 metric 全 OK band（cum_pnl=0 / max_dd=0 / position_count=0 / correlation=0 placeholder / concentration=0）— 路徑 alive 但完全不反映真實 portfolio。

## §2.2 設計路徑選擇 — Option A vs Option B vs Option C

### Option A: **disk-based pipeline_snapshot JSON 讀取（推薦）**

per `rust/openclaw_engine/src/event_consumer/bootstrap.rs:920-945` 每個 pipeline 已透過 `DualStateWriter` 把完整 `PipelineSnapshot`（含 `PaperStateSnapshot`）寫到磁盤：

| pipeline | path | debounce interval |
|---|---|---|
| Paper | `<data_dir>/pipeline_snapshot_paper.json` | 5000 ms |
| Demo | `<data_dir>/pipeline_snapshot_demo.json` | 5500 ms |
| Live | `<data_dir>/pipeline_snapshot_live.json` | 4500 ms |

`PipelineSnapshot.paper_state: PaperStateSnapshot` 含完整投影所需資料（per `pipeline_types.rs:96-170` + `paper_state/snapshots.rs:29-46`）：
- `balance` + `peak_balance` + `total_realized_pnl` + `total_fees` + `total_funding_pnl`
- `positions: Vec<PositionSnapshot>` 含 `symbol / is_long / qty / entry_price / unrealized_pnl + api_pnl`
- `bybit_sync_balance: Option<f64>`（live/demo mode 反映 Bybit Demo 真實 equity）

加 `recent_fills: Vec<TimestampedFill>`（last 50；含 `ts / symbol / qty / price / fee / realized_pnl / strategy`）即可投影 increment fill push。

**設計優點**：
- **不破 PaperState pipeline 獨佔邊界**（per Wave B 既有反模式 (a)「不改 既有寫入邏輯」）。
- **0 新 mutable singleton**（不入 singleton-registry.md；spawn_portfolio_state_update_task 持 cache Arc 即現狀）。
- **跨 3 pipeline 同步**：盤面 read 3 個 file 後 merge equity / aggregate exposures / dedupe fills；對齊 既有 spec line 332-334「caller 端 update task 注入合適來源解析（live/demo/paper merge to single emitter view）」。
- **disk JSON read cost 可忽略**：3 file × ~5KB / 5 min = 3KB/s I/O；對 NVMe 純 read 為 << 1 ms。

**設計缺點 + 緩解**：
- **debounce 4.5-5.5s vs update tick 300s**：snapshot 比 update tick 新 295s 後一定 stale-bounded（不破 24h sliding window 解析度）。
- **JSON parse cost**：3 file × ~100 position * `PositionSnapshot` derive 同 PaperPosition + extra（per `paper_state/containers.rs:18-273`）；serde_json deserialize ~ 1-3 ms × 3；可忽略。
- **磁盤未 ready / file missing**：`pipeline_snapshot_paper.json` 在 Paper disabled (OPENCLAW_ENABLE_PAPER=0) 時走 DISABLED marker（per `main_pipelines.rs:248-290`）— reader 端必須 fail-soft `Option<PaperStateSnapshot>`，None 視為 empty contribution。
- **race window**：StateWriter 寫盤同時 reader 讀 → 部分讀。緩解：JSON parse fail → skip this tick + fail-loud warn log + last_update_ts_ms 不 advance；下次 tick 重試。對齊 既有 `update_from_pipeline_snapshot` F-2 sanitize 範式。

### Option B: 新增 `Arc<RwLock<PaperStateSnapshot>>` mirror（不推薦）

讓 TickPipeline 在每次 `apply_fill` / 平倉後 push snapshot 到 main.rs scope 的 mirror Arc。

**設計缺點**：
- **破 既有反模式 (a)**：改動 PaperState 寫入路徑 + TickPipeline mutate side（per Wave A PA-DRIFT-5 dispatch §7.5 反模式 (a)（c）「不改 既有寫入邏輯」+ singleton-registry.md §3.4 反模式 2「半實裝 placeholder 不能成 SSOT」）。
- **新 mutable singleton**：1 條（`Arc<RwLock<HashMap<PipelineKind, PaperStateSnapshot>>>`）；必登記 singleton-registry.md；走 PM dispatch packet 新 singleton 預登記 SOP（per §6.2）。
- **3E-ARCH 跨 pipeline 一致性**：3 個 pipeline 寫同一 mirror → 寫端跨 task 競爭；需 lock free read 設計（RCU / ArcSwap）— 引新 dependency。

### Option C: 新增 broadcast::Sender<EngineEvent::FillCompleted>（不推薦）

擴 `EngineEvent` enum（per `tick_pipeline/mod.rs:152-157`）新增 `FillCompleted { kind, fill_event }` variant；spawn_portfolio_state_update_task 訂 broadcast Receiver。

**設計缺點**：
- **既有 cross_engine_tx 跨進程語意污染**：當前 EngineEvent 是 pipeline 級 emergency event（Crashed / CircuitBreakerTripped），不是 fill stream；混 fill 進此 channel 破契約。
- **broadcast lagged warn 風險**：300s tick 訂 broadcast，期間 ~ 0-300 個 fill 可能 lag overflow。
- **重新 instrument fill_engine**：apply_fill / close_position / reduce_position 3 處需新 send call；觸碰 PaperState mutate side。

**結論**：**選 Option A**。disk JSON pipeline_snapshot 是現成 SSOT；不破 PaperState 獨佔邊界 + 不擴 mutable singleton + 不改 既有 trading 邏輯。

## §2.3 接口設計（Option A 細節）

### §2.3.1 新 fn 在 `main_health_emitters.rs`

```rust
/// 從 disk 讀取 3 個 pipeline_snapshot_{kind}.json + merge 為 portfolio-level
/// equity / exposures / new_fills tuple；供 spawn_portfolio_state_update_task
/// 300s tick 注入 cache。
///
/// 為什麼 disk JSON 而非 in-process Arc mirror (per Option A reasoning §2.2):
///   - 不破 PaperState pipeline 獨佔邊界 (per Wave B 反模式 (a) + spec
///     line 515-535 SSOT 不暴露 main.rs 級 Arc handle)。
///   - 0 新 mutable singleton (不入 singleton-registry.md)。
///   - disk read cost 可忽略 (3 file × ~5KB / 300s)。
///
/// 為什麼跨 3 pipeline merge (per spec line 332-334):
///   - emitter metric_name `risk_envelope__*` 共用 anomaly_id space；3
///     engine equity / exposures / fills 必 merge to single view。
///   - merge 規則:
///     * equity_usd = sum(paper.balance + demo.balance + live.balance)；
///       per pipeline disabled / file missing fail-soft 跳過。
///     * latest_exposures = concat(paper.positions ++ demo.positions ++ live.positions)
///       投影為 PositionExposure { symbol, notional_usd = qty.abs() × entry_price.abs() }。
///     * new_fills 從 paper.recent_fills ++ demo.recent_fills ++ live.recent_fills 取
///       ts > last_update_ts_ms 增量 (`(fill.ts_ms, fill.realized_pnl)` 對映)。
///
/// fail-soft 路徑 (per spec §3.6):
///   - 任 pipeline file missing / json invalid / schema drift → skip this contribution
///     + tracing::warn fail-loud + last_update_ts_ms 不 advance。
///   - 全 3 pipeline 都 fail → cache 不更新；既有 sliding window drain 仍 work。
fn read_portfolio_state_from_pipeline_snapshots(
    data_dir: &str,
    last_update_ts_ms: u64,
) -> PortfolioStateBatch {
    // PortfolioStateBatch = struct { equity_usd: f64, new_fills: Vec<(u64, f64)>,
    //                                latest_exposures: Vec<PositionExposure> }
    let mut batch = PortfolioStateBatch::default();
    for kind in [PipelineKind::Paper, PipelineKind::Demo, PipelineKind::Live] {
        let path = format!("{}/pipeline_snapshot_{}.json", data_dir, kind.to_lowercase());
        match std::fs::read_to_string(&path) {
            Ok(content) => {
                match serde_json::from_str::<PipelineSnapshot>(&content) {
                    Ok(snap) => merge_snapshot_into_batch(&mut batch, &snap, last_update_ts_ms),
                    Err(e) => tracing::warn!(target = "m3.health.wireup",
                        kind = ?kind, error = %e,
                        "portfolio_state pipeline_snapshot JSON parse fail (skip contribution)"),
                }
            }
            Err(e) => tracing::warn!(target = "m3.health.wireup",
                kind = ?kind, error = %e,
                "portfolio_state pipeline_snapshot file read fail (skip contribution)"),
        }
    }
    batch
}
```

### §2.3.2 改動 `spawn_portfolio_state_update_task` 簽名 + 內部邏輯

**簽名 + 1 個參數 `data_dir: String`**（caller `main.rs:1460` 透傳 OPENCLAW_DATA_DIR）：

```rust
pub(crate) fn spawn_portfolio_state_update_task(
    cache: Arc<ParkingMutex<PortfolioStateCache>>,
    data_dir: String,  // ← 新增 (per §4.2.2 Sprint 5+ wire-up)
    cancel: &CancellationToken,
) { ... }
```

tick loop 內把 placeholder no-op block 換成：

```rust
let mut last_update_ts_ms = 0_u64;  // ← 跨 tick 持狀，dedupe fill
loop {
    tokio::select! {
        _ = interval.tick() => {
            let now_ms = ...;
            let batch = read_portfolio_state_from_pipeline_snapshots(&data_dir, last_update_ts_ms);
            {
                let mut guard = cache.lock();
                guard.update_from_pipeline_snapshot(
                    now_ms,
                    batch.equity_usd,
                    &batch.new_fills,
                    batch.latest_exposures,
                );
            }
            // 推進 last_update_ts_ms 為當前 tick 結束時間 (per 既有 F-2 對齊
            // 「tick 已執行」語意)
            last_update_ts_ms = now_ms;
        }
        _ = task_cancel.cancelled() => { ... }
    }
}
```

### §2.3.3 caller main.rs 改 1 行

`main.rs:1460`:

```rust
// BEFORE:
main_health_emitters::spawn_portfolio_state_update_task(portfolio_cache, &cancel);

// AFTER:
main_health_emitters::spawn_portfolio_state_update_task(
    portfolio_cache,
    data_dir_mount.clone(),  // ← 透傳 OPENCLAW_DATA_DIR
    &cancel,
);
```

## §2.4 4 AC

| AC | 描述 | verify 方法 |
|---|---|---|
| AC-1 | `read_portfolio_state_from_pipeline_snapshots` unit test：3 file → merge equity = sum / exposures = concat / fills = ts > last_update_ts_ms 增量 | cargo test --release --lib `m3_portfolio_state_disk_read` 4 case (paper-only / 2 pipeline / 3 pipeline / 全 missing fail-soft) |
| AC-2 | fail-soft：任 1 file missing / json invalid → warn log + skip contribution；其他 pipeline 仍 merge | cargo test --release --lib `m3_portfolio_state_fail_soft` |
| AC-3 | last_update_ts_ms 增量 dedupe：第 2 tick 不 push 同 fill 兩次 | cargo test --release --lib `m3_portfolio_state_dedupe` |
| AC-4 | production 30 min 5 metric V106 row 不全 0：cum_pnl_24h / position_count_active / concentration_top1_pct 至少一個非 0（demo trades 持續） | psql SQL：`SELECT metric_name, observation_value FROM learning.health_observations WHERE health_domain='risk_envelope' AND now() - obs_ts < interval '30 min' ORDER BY obs_ts DESC LIMIT 30;` 期望非 0 |

## §2.5 副作用清單

| 改動 | 副作用 | 阻擋 |
|---|---|---|
| `main_health_emitters.rs spawn_portfolio_state_update_task` 改簽名 | 1 caller (`main.rs:1460`) | E1 同 commit update caller；E2 grep verify |
| 新 fn `read_portfolio_state_from_pipeline_snapshots` + 新 struct `PortfolioStateBatch` | 0 external caller | new pub(crate) only |
| `pipeline_snapshot_{kind}.json` JSON read | disk I/O ~ 15KB / 5 min；fail-soft 路徑保護 read fail / parse fail | 對 NVMe 可忽略 |
| `PipelineSnapshot` serde Deserialize | 既有 deserialize 已用於 state restore 路徑（per `paper_state/checkpoint.rs`）；本場 reuse 既有 derive | 0 schema migration |
| F-2 sanitize | NaN/inf 已在 `PortfolioStateCache::update_from_pipeline_snapshot` 內部處理（per `risk_envelope_probe_impl.rs:194-241` PA-DRIFT-5 round 2 fix）| 0 新處理 |

## §2.6 改動風險評級 = 中

| 風險點 | 等級 | 緩解 |
|---|---|---|
| pipeline_snapshot.json schema 演化（已知 schema_version field per `pipeline_types.rs:97-100`）| 中 | reader 端 serde_json 寬鬆 deserialize；不依賴新增 field；fail-soft on parse error |
| 3 pipeline disk write 同步 race | 中 | StateWriter debounce 已 stagger（4.5/5/5.5s）；單 file read 是 atomic; partial write 觸 parse fail → skip + warn |
| `data_dir_mount` 環境變數空 | 低 | OPENCLAW_DATA_DIR 已在 `main.rs:1444-1446` 解析 + `unwrap_or_else("/tmp/openclaw")` 兜底 |
| f64 overflow on equity sum | 低 | 3 pipeline equity 在 USD ~ $10K-$1M 範圍；sum 不可能 overflow f64 |

**總體**：**中**（簽名變動 + disk read + 跨 3 pipeline merge），但每處都有既有 pattern 對齊（Wave A `read_to_string` 範式 / Wave B fail-soft / F-2 sanitize / `data_dir_mount` 對齊）。

## §2.7 16 原則 + DOC-08 §12 合規 checklist

| 原則 | 狀態 | 證據 |
|---|---|---|
| 1 單一寫入口 | ✅ | observability layer；不寫訂單 |
| 2 讀寫分離 | ✅ | pipeline_snapshot.json read-only；不 mutate PaperState |
| 3 AI 輸出 ≠ 命令 | ✅ | 無 AI 路徑 |
| 4 策略不繞風控 | ✅ | metric emit，無策略執行 |
| 5 生存 > 利潤 | ✅ | fail-soft skip + warn，不誤升 CRITICAL |
| 6 失敗默認收縮 | ✅ | read fail / parse fail → skip contribution + log |
| 7 學習 ≠ 改寫 Live | ✅ | learning.health_observations 寫入而已 |
| 8 交易可解釋 | ✅ | trace_id 透過 emitter scheduler 傳遞 |
| 9 災難保護 | ✅ | local + 交易所雙重防線無關 |
| 10 認知誠實 | ✅ | placeholder no-op vs 真實 SSOT 區分明示在 spec |
| 11 Agent 最大自主 | ✅ | P0/P1 內無觸碰 |
| 12 持續進化 | ✅ | 5 metric 真實採樣替 30 天連續 0 染色 |
| 13 AI 成本感知 | ✅ | 無 AI 呼叫 |
| 14 零外部成本 | ✅ | 本地 PG + disk only |
| 15 多 Agent 協作 | ✅ | observability 不破 5 Agent + Conductor |
| 16 組合級風險 | ✅ | **此 fix 直接服務原則 16**（portfolio-level 5 metric 真實採樣）|

DOC-08 §12 9 不變量：**0/9 觸碰**（觀測層；trading flow unchanged）。
§四 5 硬邊界：**0/5 觸碰**。

---

# §3 §4.2.3 push back + archive 4 Python singleton re-ingest 設計

## §3.1 Scope 漂移 push back

operator prompt §4.2.3 寫法：

> **§4.2.3 archive Python re-ingest** (P2) — sandbox stub conflict cleanup + 其他 archive Python re-ingest 路徑 (per PA-DRIFT-6 + Sprint 1A-ζ Track C IMPL #2 stub lesson)

**PA 強烈 push back**：此 wording 混淆兩個獨立 task。

### 真實 §4.2.3 scope（per singleton-registry.md §6.1 SSOT line 310-324）

```markdown
### §6.1 Re-ingest archive 4 條 Python singleton

`docs/archive/2026-05-02--CLAUDE-pre-trim-snapshot.md` §九 line 77-80 4 條 Python singleton 仍在 production 跑：

1. `_H_STATE_INVALIDATOR` / `_LOCK` — h_state_invalidator.py（G3-08 Phase 1C 條件 spawn）
2. `MARKET_SCANNER` / `AUTO_DEPLOYER` / `_SCOUT_WORKER` — strategy_wiring_scanner.py
3. `HStateCacheSlot` — rust/openclaw_engine/src/ipc_server/slots.rs（Rust late-injected slot）
4. `CostEdgeAdvisorDbSlot` — rust/openclaw_engine/src/cost_edge_advisor_boot.rs（Rust late-injected slot）

本 task scope 嚴守 Wave A/B 6 新 singleton 登記；archive 4 條 re-ingest 屬 Sprint 5+ doc clean-up follow-up。
- Owner: TW + PA
- Priority: P2 LOW（governance hygiene；non-blocker）
- Est: 1-2 hr（盤點 4 條當前 production state + 補 §1.3 完整欄位）
- 觸發條件: Sprint 5+ cascade IMPL 期間 docs/ doc-index sweep 順手
```

**核心特徵**：
- **doc-only**：append 4 entry 進 `docs/architecture/singleton-registry.md` §2.x
- **read-only audit**：grep 4 condition + state（construct path / lifecycle / lock primitive / caller_chain）→ 寫入 SSOT 12 欄位（per §1.3 標準）
- **0 IMPL 變動**：4 條 production 跑著的 singleton 不改一行代碼
- **0 sandbox 操作**：不入 sandbox env / 不 DROP TABLE / 不操作 PG role

### 誤併入的 sandbox stub cleanup（per Stage F §8.8）

operator prompt 把 §8.8 sandbox stub conflict cleanup 誤併進 §4.2.3。**§8.8 真實 scope**：

```markdown
### §8.8 NEW sandbox V100 stub conflict cleanup — P2 follow-up

cleanup 內容：
- DROP TABLE learning.hypotheses CASCADE in sandbox（含 hypothesis_preregistration / earn_movement_log dependent）
- 重新 apply V100 → V103 chain in sandbox 驗 idempotency
- 結果文檔化 input Sprint 1B early V107 sandbox empirical 範式

Owner：E3 + operator（sandbox_admin role + secret_file 0600 + 9-step sandbox empirical chain）
Priority：P2（不阻 production；sandbox empirical hygiene）
```

**核心特徵**：
- **sandbox IMPL**：DROP TABLE CASCADE + 重 apply V### chain（不是 production，但 sandbox PG empirical）
- **E3 + operator**：需 sandbox_admin role + secret_file 0600 + 9-step empirical chain（per Sprint 1A-ζ Phase 3a sandbox SOP）
- **不是 PA scope**：PA 不對 sandbox 跑 DROP/CREATE；走 PM → E3 ssh trade-core 路徑
- **不是 Sprint 5+ Wave 1**：屬 Sprint 5+ 後續 sandbox hygiene；不入本 cascade

### push back verdict

operator prompt §4.2.3 wording 應改為：

> **§4.2.3 archive 4 條 Python singleton re-ingest** (P2 LOW) — `docs/archive/2026-05-02--CLAUDE-pre-trim-snapshot.md` 4 條 Python singleton 補入 `docs/architecture/singleton-registry.md` SSOT；TW + PA doc-only audit + entry append。**§8.8 sandbox stub cleanup 不入本 cascade**（屬 E3 + operator §8.8 routing）。

## §3.2 archive 4 條 re-ingest 接口設計（doc-only）

### Target SSOT

`docs/architecture/singleton-registry.md` §2.x（既有 §2.1 Wave A 4 條 + §2.2 Wave B 2 條 共 6 條）；新增 §2.3「Archive Python singleton（pre-trim 2026-05-02）」section append 4 entry。

### Per-entry 12 欄位（per §1.3 標準）

對每 singleton 必填：

| 欄位 | 4 entry filling 來源 |
|---|---|
| name | per archive line 77-80 |
| type_signature | grep production source code 真實 type |
| location | grep production source code file:line（per archive 4 mention）|
| owner_lifecycle | grep production constructor / shutdown 路徑 |
| cross_task_pattern | 已知 from archive description (e.g., `_H_STATE_INVALIDATOR` = Python→Rust failure hint channel)|
| lock_primitive | grep production type signature |
| visibility | grep production source code |
| caller_chain | grep production producer + consumer + handle exposer 3 端 |
| health_monitoring | NO（4 條皆非 ADR-0042 M3 6 domain）|
| registered_date | 2026-05-23（補登）|
| governance_authority | 既有 governance reference（archive 描述含 G3-08 / G3-09 / STRATEGY-WIRING-SPLIT 等）|
| migration_plan | 0（既有 production；非 Sprint 5+ 改造計劃）|

### File scope

新建 / append section：
- `docs/architecture/singleton-registry.md`（既有 366 LOC → append ~150 LOC，~4 entry × ~30 LOC each + section header）

不碰：
- `docs/archive/2026-05-02--CLAUDE-pre-trim-snapshot.md`（archive snapshot 不 reinstall；per singleton-registry.md §4.4）
- production source code（不改一行）

## §3.3 副作用 + 風險

| 改動 | 副作用 | 阻擋 |
|---|---|---|
| singleton-registry.md +150 LOC | 0（doc-only）| 無 |
| grep production source code | 0（read-only）| 無 |
| cross-ref governance docs | 0 | 無 |

**改動風險評級 = 低**。

## §3.4 AC

| AC | 描述 |
|---|---|
| AC-1 | 4 entry × 12 欄位完整填入 singleton-registry.md §2.3；無 placeholder / TBD |
| AC-2 | 4 entry source location 對齊 production source code 真實 file:line（grep verify）|
| AC-3 | E2 / PA review 後 cross-ref 既有 §2.1-§2.2 6 entry pattern 對齊；無 schema drift |

Est: 1-2 hr TW + PA collaborative audit + append。

---

# §4 §4.2.4 dispatch template + PA-DRIFT lesson template 設計

operator prompt §4.2.4 表述模糊 — 拆兩個獨立 doc：

| 子 task | path | content | est |
|---|---|---|---|
| §4.2.4a | `docs/CCAgentWorkSpace/PM/race_dispatch_template.md` amend 新 §7「新 mutable singleton 預登記」section | per singleton-registry.md §6.2 規則：PM dispatch packet 起草前必含「新 singleton 預登記」section + worked example | 30 min PA |
| §4.2.4b | `docs/governance_dev/templates/2026-05-23--pa_drift_lesson_template.md` 新建 | governance lesson template + 6 PA-DRIFT lessons 摘要 | 1-1.5 hr PA + TW |

## §4.1 §4.2.4a — PM dispatch template amend「新 singleton 預登記」section

### 目的

per singleton-registry.md §5.2 + §6.2：

> E2 Wave B round 1 catch MEDIUM-1「6 new singleton 未登記」是合理；但根因「SSOT 0 hit」應在 dispatch packet 階段 PA 預判（per §3.3 規則 — PA dispatch packet 必含新 singleton 預登記條目）。Sprint 2 Wave 1+2 dispatch packet（2026-05-22）未含此項，是 PA gap。修法：本 SSOT 建立後 dispatch packet 模板必加「新 singleton 預登記」section。

### Amend 內容

新增 `docs/CCAgentWorkSpace/PM/race_dispatch_template.md` §7：

```markdown
## §7 新 mutable singleton 預登記（per singleton-registry.md §3.3）

PM dispatch packet 起草前必 grep 預判新 mutable singleton：

```bash
# 派發前 PA / PM grep helper：本 sprint scope 內預計新增的 singleton 候選
grep -rnE 'static\s+[A-Z_]+:|lazy_static!|once_cell::sync|Arc<.*Mutex|Arc<.*RwLock|Arc<.*broadcast::Sender' <sprint scope file path> | head -20
```

dispatch packet 必含 section：

```markdown
### §X 新 mutable singleton 預登記（per singleton-registry.md §3.3）

本 sprint IMPL 預計新增 N 個 mutable singleton（IMPL 後 PA 補登進 singleton-registry.md）：

| name | type signature (預判) | owner | location (預判) | health_monitoring | governance_authority |
|---|---|---|---|---|---|
| <Singleton-1> | Arc<parking_lot::Mutex<...>> | <module> | <file:line> | YES (per ADR-XXXX) / NO | <ADR-XXXX> |
```

PA 預判錯誤（IMPL 時實際 type 不同）→ amend SSOT 補正；非阻 sign-off，PA debt log。

**反模式**：dispatch packet 0 mention 新 singleton 但 E2 / E1 IMPL 加新 `Arc<Mutex>` → MEDIUM finding；走 SSOT escalate（per singleton-registry.md §5.2 教訓）。
```

### Worked example

附 1 個 worked example（Sprint 4+ Wave A PA-DRIFT-4 4 singleton 預登記示範）：

| name | type signature (預判) | owner | location (預判) | health_monitoring | governance_authority |
|---|---|---|---|---|---|
| RestLatencyHistogram | `pub struct { samples: Mutex<Vec<(Instant, u64)>> }` | bybit_rest_client | bybit_rest_client.rs:~335 | YES (ADR-0042 api_latency domain) | PA-DRIFT-4 + ADR-0042 |
| RetCodeCounter | `pub struct { samples_4xx: Mutex<Vec<Instant>>, samples_5xx: Mutex<Vec<Instant>> }` | bybit_rest_client | bybit_rest_client.rs:~480 | YES (ADR-0042 api_latency) | PA-DRIFT-4 + ADR-0040 |
| WsRttHistogram | `pub struct { samples: Mutex<...> }` | bybit_private_ws | bybit_private_ws.rs:~98 | YES (ADR-0042 api_latency) | PA-DRIFT-4 |
| WsDropoutCounter | `pub struct { samples: Mutex<...> }` | bybit_private_ws | bybit_private_ws.rs:~125 | YES (ADR-0042 api_latency) | PA-DRIFT-4 |

## §4.2 §4.2.4b — governance lesson template + 6 PA-DRIFT lessons 摘要

### Path

`docs/governance_dev/templates/2026-05-23--pa_drift_lesson_template.md`（新建 dir + file）

### Template skeleton

```markdown
---
template: PA-DRIFT governance lesson
date: <YYYY-MM-DD>
author: PA
status: TEMPLATE
parent_ssot: docs/governance_dev/templates/2026-05-23--pa_drift_lesson_template.md
---

# PA-DRIFT-X — <one-line title>

## §1 Discovery

- **觸發 sub-agent / role**：<E1 / E2 / E4 / QA / FA / ...>
- **discovery context**：<spec round / IMPL round / E2 review round / production deploy>
- **發現時 phase**：<DESIGN / IMPL / E2 review / E4 regression / production deploy>
- **發現方式**：<grep verify / PG empirical / runtime sample / cargo test>

## §2 Root Cause

- **錯誤模式 (5W)**：
  - What: <具體錯誤行為>
  - Where: <file:line / spec section>
  - When: <時間點 / phase>
  - Why: <根本原因>
  - Who: <派發 / 接收 agent>
- **錯誤類型分類**：
  - [ ] schema 命名漂移
  - [ ] V### file land 與 spec ref 不同步
  - [ ] half-IMPL placeholder 殘存
  - [ ] hypertable / PG 反射假設錯誤
  - [ ] singleton 未登記
  - [ ] caller 注入路徑 leak
  - [ ] 其他: <specify>

## §3 Fix Applied

- **fix scope**：<files changed>
- **fix LOC**：<lines added / removed>
- **commit chain**：<SHA list>
- **AC verify**：<list AC + verify method + status>

## §4 Cross-V### / Cross-Module 防線

- **影響範圍**：<list V### / spec / module 已 patch>
- **未來 V### 自動繼承 mechanism**：<spec doc COMMENT / SQL COMMENT / FK soft ref / dispatch template amend>
- **grep guard pattern**：<grep regex + helper script>
- **healthcheck reuse**：<既有 [N] healthcheck / 新 [N] healthcheck>

## §5 ADR Amend (if applicable)

- **ADR 影響**：<ADR-XXXX>
- **amend 方向**：<inline patch / new section / new ADR>
- **PM sign-off needed**：YES / NO

## §6 Lessons Learned + 反模式

- **3 條核心 lessons**：<bullet>
- **3 條反模式 (DO NOT)**：<bullet>
- **下次類似 design 預防 mandate**：<具體 PA / E1 / E2 SOP amend>

## §7 Cross-References

- Parent finding report
- IMPL report
- E2 review report
- Production deploy verify report
- 16 原則 + DOC-08 §12 + §四 5 硬邊界 verdict
```

### 6 PA-DRIFT lessons 摘要

template 後接 §8「6 PA-DRIFT lessons 摘要」section，每 lesson ~20 LOC：

#### PA-DRIFT-1 — governance.audit_log → learning.governance_audit_log schema 命名漂移

- **Discovery**：2026-05-22 E1 Sprint 1B push back（V107 sandbox land dedup 報告）
- **Root cause**：V103 base spec line 210/233/382 寫 `governance.audit_log`（spec typo）；production 真實表名 `learning.governance_audit_log`（per V035/V098 baseline）
- **Fix**：V100/V106/V107/V112 IMPL 全 patch 至 `learning.governance_audit_log`；V100 IMPL 繼承此 lesson
- **Cross-V### 防線**：V103 base spec doc COMMENT 保留 reconcile 注釋（audit trail）；未來 V### spec 設計必 grep production schema 確認真實表名
- **Source**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_pre_v107_governance_audit_log_align.md`

#### PA-DRIFT-2 — V103 file HARD BLOCKER drift

- **Discovery**：2026-05-22 Sprint 2 readiness signoff 預檢
- **Root cause**：V103 EXTEND outline (spec doc) → 真實 .sql 檔 land 之間有時間差；V### file 未 land 但 spec ref 指向；下游 Sprint 改 V### 撞 file scope overlap
- **Fix**：Sprint 2 6 Track 不碰 V103；新增 V### 走 V117+ reserved；Sprint 1B mid item 補 V103 真實 .sql 檔 land
- **Cross-V### 防線**：dispatch packet 必含「V### slot 真實佔用 audit」section；PA pre-IMPL 必 grep `sql/migrations/V### *.sql` 確認 file land state
- **Source**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_readiness_signoff.md` §3.1

#### PA-DRIFT-3 — （per 既有 PA workspace 報告，待確認 origin）

> **PA debt**：此 PA-DRIFT-3 在 memory + report grep 未找到獨立 origin；可能屬於早期治理 lesson 內部編號（懷疑與 PA-DRIFT-2 同源或為 PA-DRIFT-1 變體）。template §8 收錄時 mark `(merged into PA-DRIFT-2 / PA-DRIFT-1 — TBD by future audit)`。下次 PA workspace audit 時補正 origin。

#### PA-DRIFT-4 — bybit_rest_client + bybit_private_ws instrumentation 既有 hook claim FALSE

- **Discovery**：2026-05-22 Sprint 2 Wave 2 Track D E2 round 1 HIGH-3
- **Root cause**：PA dispatch packet §5.1 寫「既有 bybit hook」FALSE；E2 grep verify 0 hit；M3 ApiLatencySourceProbe trait 接 stub 而非 real source
- **Fix**：Sprint 4+ Wave A PA-DRIFT-4 並行 IMPL（5 工作項：RestLatencyHistogram / RetCodeCounter / WsRttHistogram / WsDropoutCounter / ApiLatencySourceProbe 接線）；commit 5acd36e6 + 4c84d1bb
- **Cross-V### 防線**：PA dispatch packet 「既有 X hook」claim 必 grep verify literal 真實存在；不可基於假設設計
- **Source**：`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint_4_pa_drift_4_bybit_instrumentation.md` + Sprint 2 Wave 2 Track D round 1 E2 report

#### PA-DRIFT-5 — RiskEnvelopeSourceProbe wire-up 半實裝

- **Discovery**：2026-05-22 Sprint 2 Track F round 2 P1 fix + Sprint 4+ Wave A round 1
- **Root cause**：Sprint 2 Track F PA design 走 stub probe（StubSourceProbe 注入）；production probe 待 Sprint 4+ wire-up；F-2 NaN/inf sanitize 守線未 land；F-4 correlation_avg_pairwise placeholder 0.0 設計未明示
- **Fix**：Sprint 4+ Wave A PA-DRIFT-5 round 1+2 IMPL（risk_verdict_ledger + position_snapshot SSOT calculator 接線 / F-1 cap comment / F-2 NaN/inf sanitize / F-3 batch helper / F-4 placeholder lookback amend defer to Sprint 5+）；commit 5acd36e6 + 4c84d1bb
- **Cross-V### 防線**：M3 emitter source probe 不可走 placeholder land production；半實裝必明示在 caller_chain 欄位 + module 頭注釋 + Sprint 後續 wire-up plan
- **Source**：`docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_4_pa_drift_5_risk_envelope_wireup.md`

#### PA-DRIFT-6 — TimescaleDB hypertable composite PK 不能作為 PostgreSQL FK target

- **Discovery**：2026-05-23 Production AUTO_MIGRATE=1 第一次 attempt（Stage E deploy）
- **Root cause**：V100 earn_movement_log.governance_approval_id FK target = `learning.governance_audit_log(id)`；但 `learning.governance_audit_log` 是 TimescaleDB hypertable + PK 是 (id, ts) composite；PostgreSQL FK constraint 不能 reference hypertable composite PK
- **Fix**：V100 SQL line 502-511 + COMMENT ON TABLE line 485-490 改 soft reference + Guard C 改 column check（不寫 FK constraint，僅 COMMENT 紀錄 cross-ref semantics）；commit 6ceb5814
- **Cross-V### 防線**：未來 V### spec 設計必查 FK target 表是否 TimescaleDB hypertable（grep `SELECT create_hypertable`）+ PK 是否 composite（reflect `pg_class.relkind = 'r' AND pg_index.indisprimary`）；若是 → 必走 soft reference + Guard C column check 路徑
- **Source**：`docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--stage_a_to_e_overall_acceptance.md` §5.2 + §6

### 反模式收錄（4 條跨 PA-DRIFT 共通）

1. **「既有 X hook / SSOT / 表 / column」claim 不 grep verify literal**（PA-DRIFT-1 / 2 / 4 共通）
2. **half-IMPL placeholder land production 但 caller_chain 未明示**（PA-DRIFT-5 + Wave B WS instrumentation 共通）
3. **Schema 命名 spec ≠ production reality 不 PG empirical 驗證**（PA-DRIFT-1 + PA-DRIFT-6 共通）
4. **新 mutable singleton 未走 SSOT 預登記 → E2 catch late**（PA-DRIFT-4 driving 1639506f singleton-registry.md 建立）

## §4.3 §4.2.4 副作用 + AC

| 改動 | 副作用 | 阻擋 |
|---|---|---|
| `docs/CCAgentWorkSpace/PM/race_dispatch_template.md` +1 section（~50 LOC）| 0 | TW + PA review |
| `docs/governance_dev/templates/2026-05-23--pa_drift_lesson_template.md` 新建（~200 LOC）| 新建 `templates/` 子目錄 | 走 `docs/README.md` placement rule |

| AC | 描述 |
|---|---|
| AC-1 | dispatch template §7 含「新 singleton 預登記」grep helper + worked example + 反模式 |
| AC-2 | governance lesson template 含 7 section 完整 skeleton + 6 lessons 摘要（PA-DRIFT-3 mark TBD audit）+ 4 反模式 |
| AC-3 | 兩個 doc cross-ref 對齊（dispatch template §7 → singleton-registry.md §3.3 + §6.2；governance lesson template §8 6 lessons 對齊既有 source report path）|

**改動風險評級 = 低**（純 doc）。

---

# §5 3 items combined AC + Phase split + dispatch readiness

## §5.1 3 items 合併 AC

| AC | 描述 | item |
|---|---|---|
| §4.2.2 AC-1/2/3 | cargo test --release --lib m3_portfolio_state_* 4 case PASS | §4.2.2 |
| §4.2.2 AC-4 | production 30 min 5 metric V106 row 不全 0 | §4.2.2 |
| §4.2.3 AC-1/2/3 | singleton-registry.md §2.3 4 entry × 12 欄位完整 + grep verify location + pattern 對齊 | §4.2.3 |
| §4.2.4 AC-1 | PM race_dispatch_template.md §7「新 singleton 預登記」section land + worked example | §4.2.4 |
| §4.2.4 AC-2/3 | pa_drift_lesson_template.md 7 section skeleton + 6 lesson 摘要 + 4 反模式 + 2 doc cross-ref | §4.2.4 |

## §5.2 IMPL phase split

per operator 「4-5 hr single-thread」指示，走 sequential 派發：

```
T+0   : PM dispatch §4.2.2 E1 IMPL (~150-200 LOC; 4-6 hr)
        - file scope: rust/openclaw_engine/src/main_health_emitters.rs (~+80 LOC) + main.rs (~1 line) + 新 fn + unit test ~+70 LOC

T+4h  : E1 §4.2.2 IMPL done → E2 round 1 review (~1 hr; 不阻並行)

T+4h  : PM 並行派 §4.2.3 TW + §4.2.4 PA
        - §4.2.3: TW + PA collaborative doc audit (1-2 hr; doc-only)
        - §4.2.4: PA spec + TW format polish (1.5-2 hr; doc-only)
        - 三 item file scope 0 重疊（main_health_emitters.rs vs singleton-registry.md vs race_dispatch_template.md + new pa_drift_lesson_template.md）

T+5h  : §4.2.2 E2 round 1 review done
        + §4.2.3 + §4.2.4 doc 並行 done
        → PM 驗 AC + sign-off

T+5.5h: PM commit chain push → Linux deploy --rebuild → 30 min production verify §4.2.2 AC-4
```

**Total wall-clock**：5-6 hr（含 §4.2.2 E1 IMPL + E2 review + production verify wait）

## §5.3 dispatch readiness verdict

**OPEN — dispatch-ready**：

| 前置條件 | 狀態 |
|---|---|
| 1. Wave A PA-DRIFT-5 `PortfolioStateCache` API surface 確立 | ✅ commit 5acd36e6 + 4c84d1bb |
| 2. Wave B `spawn_portfolio_state_update_task` placeholder land | ✅ commit 245216d1 + 4d4ff99f |
| 3. `pipeline_snapshot_{kind}.json` disk JSON SSOT 確立（既有 ~ 6 個月）| ✅ 既有 |
| 4. `PaperStateSnapshot` serde Deserialize 既有 derive | ✅ 既有 |
| 5. `singleton-registry.md` SSOT 建立（§6.1 + §6.2 + §6.4 carry-over 列入）| ✅ commit 1639506f |
| 6. `docs/archive/2026-05-02--CLAUDE-pre-trim-snapshot.md` archive 4 條 entry 已存 | ✅ archive line 77-80 |
| 7. 6 PA-DRIFT lessons origin reports 已存 | ✅（PA-DRIFT-3 待 audit 補正）|

**Risk grade 中（§4.2.2 主導）**：

- E1 IMPL 學習曲線：低（既有 `read_to_string + serde_json::from_str` 範式 + Wave A/B fail-soft pattern 對齊）
- E2 review 學習曲線：低（grep pattern 對齊 既有 Wave A/B + F-2 sanitize 已 land）
- production deploy 風險：中（disk read 引入新 I/O path；fail-soft 保護完整；30 min sample wait 觀測）

## §5.4 E2 重點審查 3 點

1. **`read_portfolio_state_from_pipeline_snapshots` fail-soft 路徑**：
   - file missing / read fail：tracing::warn + skip contribution；不 crash + 其他 pipeline 仍 merge
   - JSON parse fail：同 fail-soft；fail-loud warn 含 pipeline_kind + error detail
   - 全 3 pipeline 都 fail：cache 不 update（last_update_ts_ms 仍 advance；24h sliding window drain 仍 work）
   - **E2 必 grep `pipeline_snapshot_{kind}.json` reader 端不 unwrap / 不 panic / 不 expect**

2. **last_update_ts_ms 跨 tick 持狀 dedupe correctness**：
   - 第 1 tick：last_update_ts_ms = 0；merge 全部 recent_fills（注：last 50 限制下盲區 - per-pipeline 過去 5 min 100+ fill 會掉）
   - 第 2 tick：last_update_ts_ms = T1；只 merge ts > T1 增量
   - **E2 必驗 unit test `m3_portfolio_state_dedupe` 涵蓋 5 min 內 < 50 fill / 5 min 內 > 50 fill 兩 case**
   - **PA debt log**：recent_fills last 50 限制下，5 min 內 > 50 fill 會掉一些 sample；對 cum_pnl_24h sum 是輕度低估；對 portfolio risk OK band classify 影響可忽略（如需 100% 完整 fill，改走 PG fills table read 路徑為 Sprint 5+ amend follow-up）

3. **3 pipeline merge equity / exposures / fills 合理性**：
   - equity：sum 直接相加（per spec line 332-334 PM 拍板 single cache view）；live/demo/paper 不同 currency 不存在（皆 USDT）
   - exposures：concat；對 cross-pipeline 同 symbol（如 live + demo 都持 BTCUSDT）→ 2 行 PositionExposure；concentration_top1_pct 不受影響（per `concentration_top1_pct` 走 abs notional max 邏輯）
   - new_fills：concat；dedupe 走 ts > last_update_ts_ms（per pipeline 各自 ts 連續 + 跨 pipeline ts 不重疊）
   - **E2 必驗 3 file 全 present case 下 batch.equity_usd / .exposures.len() / .new_fills.len() 符合 sum / concat 預期**

---

# §6 完成回報（4 條 per operator format）

1. **§4.2.2 PortfolioStateCache PaperState SSOT 接線設計 + LOC est**：完成 — **Option A disk-based pipeline_snapshot JSON 讀取**（不破 PaperState pipeline 獨佔邊界 + 0 新 mutable singleton + fail-soft 完整）；新 fn `read_portfolio_state_from_pipeline_snapshots` + `spawn_portfolio_state_update_task` 簽名 +1 參數 + main.rs caller 改 1 行；E1 IMPL **~150-200 LOC**（80 LOC 新 fn + ~70 LOC unit test 4 case + ~10 LOC caller + 簽名 update）；4-6 hr E1 + ~1 hr E2 + 30 min production wait

2. **§4.2.3 archive Python re-ingest 設計 + scope**：**強 push back** — operator prompt scope 漂移；真實 §4.2.3 = **archive 4 條 Python singleton re-ingest** (`_H_STATE_INVALIDATOR` / `MARKET_SCANNER` / `HStateCacheSlot` / `CostEdgeAdvisorDbSlot`) 補入 `docs/architecture/singleton-registry.md` §2.3；**TW + PA doc-only audit + entry append ~150 LOC**；1-2 hr；**sandbox stub conflict cleanup 不入本 cascade**（屬 §8.8 E3 + operator routing）

3. **§4.2.4 dispatch template 設計 + template path + 6 PA-DRIFT lessons 收錄**：**拆兩個獨立 doc**：
   - **§4.2.4a** `docs/CCAgentWorkSpace/PM/race_dispatch_template.md` amend §7「新 mutable singleton 預登記」section（30 min PA + worked example）
   - **§4.2.4b** `docs/governance_dev/templates/2026-05-23--pa_drift_lesson_template.md` 新建（1-1.5 hr PA + TW；7 section skeleton + 6 PA-DRIFT lessons 摘要 + 4 反模式）
   - 6 lessons 摘要：PA-DRIFT-1 schema 命名漂移 / PA-DRIFT-2 V### file BLOCKER drift / **PA-DRIFT-3 待 audit 補正 origin** / PA-DRIFT-4 既有 hook claim FALSE / PA-DRIFT-5 半實裝 placeholder land production / PA-DRIFT-6 TimescaleDB hypertable composite PK FK

4. **3 items combined dispatch readiness + Phase B E1 IMPL split**：**OPEN — dispatch-ready**；7 前置全 land；**total wall-clock 5-6 hr** (T+0 §4.2.2 E1 IMPL → T+4h E2 review + §4.2.3 §4.2.4 並行 doc → T+5h sign-off → T+5.5h Linux deploy + 30 min verify)；**3 items 0 file scope 重疊**；改動風險中（§4.2.2 主導；§4.2.3 §4.2.4 低 doc-only）；**E2 重點 3 條**：(a) fail-soft 路徑無 unwrap/panic/expect (b) last_update_ts_ms dedupe correctness + last 50 fill 限制 PA debt log (c) 3 pipeline merge 跨 currency / concat / dedupe 合理性

---

# §7 Cross-References

## Parent reports
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--stage_a_to_e_overall_acceptance.md` §8.3
- `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_4_first_live_carryover_pm_phase_3e_signoff.md` §4.2
- `docs/architecture/singleton-registry.md` §6.1-§6.4

## Source code (§4.2.2 IMPL target)
- `rust/openclaw_engine/src/main_health_emitters.rs:549-598`（spawn_portfolio_state_update_task）
- `rust/openclaw_engine/src/main.rs:1437-1497`（caller）
- `rust/openclaw_engine/src/health/domains/risk_envelope_probe_impl.rs:74-380`（PortfolioStateCache + 5 SSOT calculator）
- `rust/openclaw_engine/src/event_consumer/bootstrap.rs:920-945`（pipeline_snapshot writer interval staggering）
- `rust/openclaw_engine/src/pipeline_types.rs:96-170`（PipelineSnapshot DTO）
- `rust/openclaw_engine/src/paper_state/snapshots.rs:29-89`（PaperStateSnapshot + export_state）

## Target docs (§4.2.3 + §4.2.4 IMPL targets)
- `docs/architecture/singleton-registry.md`（§4.2.3 append §2.3）
- `docs/CCAgentWorkSpace/PM/race_dispatch_template.md`（§4.2.4a amend §7）
- `docs/governance_dev/templates/2026-05-23--pa_drift_lesson_template.md`（§4.2.4b 新建）
- `docs/archive/2026-05-02--CLAUDE-pre-trim-snapshot.md` line 77-80（§4.2.3 source）

## 6 PA-DRIFT lessons origin
- PA-DRIFT-1: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_pre_v107_governance_audit_log_align.md`
- PA-DRIFT-2: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-22--sprint_2_readiness_signoff.md` §3.1
- PA-DRIFT-3: **TBD audit**（懷疑 merged into PA-DRIFT-2 / -1；本 template §8 mark needing future PA audit）
- PA-DRIFT-4: `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-23--sprint_4_pa_drift_4_bybit_instrumentation.md`
- PA-DRIFT-5: `docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-22--sprint_4_pa_drift_5_risk_envelope_wireup.md`
- PA-DRIFT-6: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--stage_a_to_e_overall_acceptance.md` §5.2 + §6

## Governance + 16 原則
- `srv/CLAUDE.md` §二 (16 root principles) + §四 (5 hard boundaries)
- `srv/.claude/skills/16-root-principles-checklist/SKILL.md`
- `docs/decisions/EX-01_..._V2.md` §2.1-§2.3 (P0/P1/P2 三層風控)
- ADR-0042 M3 Health Monitoring (4 entry health_monitoring=NO context)

---

**PA DESIGN DONE**

*OpenClaw / Arcane Equilibrium — Sprint 5+ Wave 1 §8.3 §4.2.2-4 cascade — 0 IMPL / 0 sub-agent / 0 commit*

PA DESIGN DONE: report path: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint5_wave1_cascade_4_2_design.md
