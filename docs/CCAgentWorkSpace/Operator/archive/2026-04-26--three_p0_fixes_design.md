# PA — 3 個 P0 fix design（接 STRKUSDT dust spiral RCA 之後）

採集時間：2026-04-26 18:55 CEST · Linux HEAD `e5f1b2d` · 仍運行 binary 04:28 build (PID 2033577，af48ee1 fix 即將透過 restart_all.sh --rebuild 部署)

範圍：read-only 設計（不寫實作碼，E1 領域）。本報告 4 節：F3 phantom dust evict-on-dust 設計 / F4 trading_writer LIVE drop RCA + 設計 / F6 edge estimate reload 設計 / E1 派發 schedule。每節含 file:line 修改點 + 接口 + fail-closed 行為 + E1 子任務拆分 + E2 重點審查 3 點 + 工時 + Regression 風險。

---

## §1 F3 — Phantom dust paper_state evict-on-dust path 設計

### 1.1 RCA 補強（與 STRKUSDT RCA 對齊）

af48ee1 cohesive fix 已包：
- Gate 1 `step_0_fast_track.rs:374` 進入 reduce_half 前 `current_notional < ft_dust_qty_floor_usd` skip — **生產者端防 spawn 新 reduce intent**
- A3 `bootstrap.rs:308 migrate_legacy_entry_notional()` — startup-time **idempotent backfill**

**剩餘 gap（這次 design 範圍）**：
1. **Runtime evict path 缺**：af48ee1 對「已存在的 dust」**只做 boot-time 一次 backfill**。如果 Bybit funding 累計 / 殘餘 partial close / 跨重啟產生新 dust，沒有持續性 evict
2. **emit_close_fill / reduce_position 寫入時不驗 notional**：`fill_engine.rs:377` `if pos.qty < 1e-12` 是 qty-based evict，**對 STRKUSDT 7.27e-13 type 的 dust 才生效**，但對 1e-9 ~ 1e-6 範圍（USD < 1.0 但 qty > 1e-12）的 dust 無效
3. **Reconciler 沒看到**：dust qty 低於 Bybit min threshold → reconciler 5min poll 0 seeded
4. **Status reporter 仍看到**：`pipeline.snapshot()` 從 `paper_state.positions{}` 直讀 → status `positions=1` 與 reconciler `seeded=0` drift
5. **Strategy chicken-and-egg**：strategy `want_close` 計數 + 但 paper_state 沒對應 entry → 永遠卡死

### 1.2 設計：USD-denominated evict-on-dust runtime path

**核心原則**：USD 名目 < `ft_dust_qty_floor_usd`（默認 1.0 USD）的 position **無條件 evict**，不管產生路徑。fail-closed default = evict（與 §1.1 #5 strategy chicken-and-egg 一致）。

#### 1.2.1 Eviction trigger 條件（4 個觸發點）

| 觸發點 | 位置 | 條件 | 動作 |
|---|---|---|---|
| **T1 reduce_position 後** | `paper_state/fill_engine.rs:376-381` | partial close 後 `pos.qty * latest_price < dust_floor_usd` | 立即 `positions_remove(symbol)` + audit log |
| **T2 apply_fill 累加後** | `fill_engine.rs:300-313`（同向加倉路徑）+ `:282-290`（反向減倉殘餘）| 同上 | 同上 |
| **T3 startup boot reaper（一次性）** | `bootstrap.rs` 在 `migrate_legacy_entry_notional()` **後** 加 reaper | 對所有 positions 評 `qty * entry_price < dust_floor_usd` | 統一 evict + count log |
| **T4 status_writer poll-based reaper（守底）** | `event_consumer/loop_handlers.rs` status_interval arm（line ~354 周邊）| 每 status interval (~30s) scan paper_state + evict dust | 異步 fan-out PaperState handle |

**Strict order**：T3 在 T1/T2 之前作為 idempotent boot-time 兜底；T4 是運行時守底（funding accrue / restore 路徑）。T1/T2 是 hot path 直接 evict。

#### 1.2.2 接口（API 邊界）

```rust
// paper_state/fill_engine.rs 新方法（純函數 + side-effect inline）
impl PaperState {
    /// EVICT-ON-DUST: Returns true if symbol was evicted as dust.
    /// 若 USD 名目 < dust_floor_usd 即就地驅逐。冪等。
    pub(crate) fn evict_if_dust(
        &mut self,
        symbol: &str,
        latest_price: f64,
        dust_floor_usd: f64,
    ) -> Option<f64> {  // returns evicted_notional_usd if evicted
        if dust_floor_usd <= 0.0 || latest_price <= 0.0 {
            return None;  // gate disabled or stale price → no-op
        }
        if let Some(pos) = self.positions.get(symbol) {
            let notional = pos.qty * latest_price;
            if notional < dust_floor_usd {
                self.positions_remove(symbol);
                return Some(notional);
            }
        }
        None
    }

    /// EVICT-ON-DUST sweep: scan all positions, evict any dust. Returns count.
    /// 對所有 positions 一次性掃描驅逐。冪等。boot reaper + 守底 reaper 共用。
    pub fn evict_all_dust(&mut self, dust_floor_usd: f64) -> usize {
        if dust_floor_usd <= 0.0 {
            return 0;
        }
        let dust_symbols: Vec<(String, f64)> = self.positions.values()
            .filter_map(|p| {
                let last = self.latest_prices.get(&p.symbol).copied().unwrap_or(p.entry_price);
                if last > 0.0 {
                    let notional = p.qty * last;
                    if notional < dust_floor_usd {
                        return Some((p.symbol.clone(), notional));
                    }
                }
                None
            })
            .collect();
        let count = dust_symbols.len();
        for (sym, notional) in dust_symbols {
            tracing::warn!(
                symbol = %sym,
                evicted_notional_usd = notional,
                dust_floor_usd,
                "EVICT-ON-DUST: phantom dust position evicted / 殭屍 dust 倉位已驅逐"
            );
            self.positions_remove(&sym);
        }
        count
    }
}
```

#### 1.2.3 Reconciler 互動

**結論：不 trigger reconciler 重 seed**。理由：
- Reconciler EX-04 對 < min_notional 倉位本來就不發 close（dispatch.rs:386 reject）
- evict 後 paper_state.positions{} 沒了 → reconciler `seeded=0` 仍然，但 `stale=false`（一致性恢復）
- 真實 Bybit 端若仍有 dust（funding accrued）：operator 手動 GUI 清理（與既有 DUST_FROZEN_STRATEGY 行為一致）

#### 1.2.4 Idempotency + reboot 保證

T3 boot reaper 確保**任何 reboot 後**所有 dust 立即 evict。serde 反序列化 `paper_state.json` snapshot 後，緊接 `migrate_legacy_entry_notional` + `evict_all_dust(dust_floor)` 雙保險。重啟新 binary 看到歷史 dust → 立即清。

#### 1.2.5 Audit / observability

**結論：不寫 trading.fills（避免污染 ML 學習資料）**。理由：
- Evict 不是真實「平倉成交」，realized_pnl=0, 寫入會被誤標 strategy_close
- 寫入 `learning.exit_features.exit_source = 'evicted_dust'` 也會污染 ML training（`PAPER-STATE-DUST-RESTORE-AUDIT` §4 已確認此教訓）

**改寫 audit_log via warn!**（`tracing::warn!` 結構化 — symbol / evicted_notional_usd / dust_floor_usd）+ 計數 stats 進 `pipeline.stats.dust_evictions: u64`。grep-friendly + healthcheck SQL 偵測：

```sql
-- Healthcheck [20] EVICT-ON-DUST runtime liveness
SELECT COUNT(*) FROM ... -- N/A, evict 不寫 DB
-- 改 SQL based on stats:
-- engine 暴露 pipeline.stats via metrics endpoint /api/v1/paper/stats
-- 或 IPC get_paper_stats 加新 field dust_evictions
```

#### 1.2.6 修改點清單

| File:line | 動作 | LOC | 風險評級 |
|---|---|---|---|
| `rust/openclaw_engine/src/paper_state/fill_engine.rs:376-381` | reduce_position 後加 evict_if_dust call | +5 | 低 |
| `rust/openclaw_engine/src/paper_state/fill_engine.rs:282-290` | apply_fill 反向減倉殘餘加 evict_if_dust | +5 | 低 |
| `rust/openclaw_engine/src/paper_state/fill_engine.rs` 新 fn | evict_if_dust + evict_all_dust | +60 | 低 |
| `rust/openclaw_engine/src/paper_state/accessor.rs` re-export | pub use evict_all_dust | +2 | 低 |
| `rust/openclaw_engine/src/event_consumer/bootstrap.rs:316` | 加 evict_all_dust 在 migrate_legacy_entry_notional 後 | +6 | 低 |
| `rust/openclaw_engine/src/event_consumer/loop_handlers.rs:~354` | status interval arm 加 30s 週期 evict_all_dust call | +12 | 低 |
| `rust/openclaw_engine/src/risk_config.rs` | `ExitConfig.dust_floor_usd` field（**re-use ft_dust_qty_floor_usd** 不新增） | 0 | 低 |
| `rust/openclaw_engine/src/paper_state/tests.rs` | unit tests evict_if_dust × 4 + evict_all_dust × 3 | +120 | 低 |

**選擇：re-use `RiskConfig.limits.ft_dust_qty_floor_usd`**（af48ee1 已 land）— 對 reduce_half 的「不 spawn」門檻 + evict 路徑的「立即清」門檻是同一個 USD 名目概念，無 schema 重複。

### 1.3 接口 fail-closed 行為

| 異常 | 行為 |
|---|---|
| `dust_floor_usd <= 0.0`（disabled） | 完全 no-op，與既有行為一致 |
| `latest_price <= 0.0`（stale tick） | 跳過該 symbol（保留），下次 status interval 重 evaluate |
| `paper_state.positions{}` empty | no-op，O(1) early return |
| 同 symbol 並行 evict（race） | `positions_remove` 是 `HashMap::remove`，第二次回 None 安全 |

### 1.4 E1 派發拆分

| 子任務 | 範圍 | E1 instance | isolation | 工時 |
|---|---|---|---|---|
| **F3-1** evict_if_dust + evict_all_dust 純函數 + 7 unit tests | `fill_engine.rs` + `tests.rs` | E1-Alpha | **isolation: worktree**（避與 F3-2 hot-path 撞） | 1.5h |
| **F3-2** T1/T2 hot-path 接線（reduce_position + apply_fill 後叫 evict_if_dust） | `fill_engine.rs` 6 處 + 2 regression tests | E1-Alpha 或 E1-Beta | 主樹（同檔依賴 F3-1）| 1h |
| **F3-3** T3 boot reaper（bootstrap.rs:316 evict_all_dust 在 migrate_legacy_entry_notional 後）+ T4 status interval reaper（loop_handlers.rs ~354） | 跨檔接線 + 1 e2e test | E1-Beta | **isolation: worktree**（loop_handlers.rs 與 F4 Phase 2 撞）| 1.5h |
| **F3-4** healthcheck [20] dust eviction runtime liveness（passive_wait_healthcheck/checks_derived.py 新 fn） | Python healthcheck + cron registry | E1-Charlie | 主樹（純新檔 add） | 1h |

**4 子任務工時 ~5h** wall-clock（F3-1 → F3-2 串行；F3-3 + F3-4 與 F3-1/2 並行）。

### 1.5 E2 重點審查 3 點

1. **F3-2 hot path race**：T1 在 `reduce_position` 後調用 evict_if_dust 必須在 caller 釋放 `&mut self.positions` 後（borrow checker）；evict_if_dust 簽名收 `&mut self` 而 reduce_position 也是 `&mut self`，但 reduce_position 結束時 borrow 已釋。**E2 必查**：兩個 fn 在 same call-site 串行 OK，禁 nested call。
2. **T4 status interval reaper 性能**：`evict_all_dust` 對 25 symbols 是 O(N) scan，30s 一次可接受；但若被誤接到 hot path（per-tick）就 25× tick 量級放大。**E2 必查**：grep `evict_all_dust` 確保只有 T3（boot 一次）+ T4（status 週期）兩處 caller，**禁** in step_0/step_1/step_2 hot path。
3. **dust evict 對 stop_manager 的衝擊**：StopManager 訂閱 paper_state 的 positions snapshot 來追 trailing stop / hard stop。Evict 後 StopManager 對該 symbol 的 stop 紀錄會 orphan。**E2 必查**：`stop_manager.rs` 是否每 tick re-scan paper_state 重 sync stops（自然清理 orphan）還是 once-only init（**MUST FIX**）。

### 1.6 工時估計

5h E1（4 子任務）+ E2 review 1.5h + E4 regression 1.5h = **8h** 全鏈。

### 1.7 Regression 風險

- **低風險**：af48ee1 fix 已將 `ft_dust_qty_floor_usd` 默認 1.0 USD 部署；real position min notional ≥ 5.0 USD（Bybit min）→ 1.0 USD floor 不誤殺
- **邊界 case**：funding-accrued residue (~0.01 USD) 會被 evict — 預期行為（與既有 DUST_FROZEN_STRATEGY 設計對齊但更積極）
- **與 EX-04 reconciler 互動**：evict 後 `engine_positions_mirror` 同步更新 → reconciler 不再看到該 symbol → 自然「stop monitoring」
- **歷史資料一致性**：不寫 trading.fills 確保 ML 訓練資料純淨

---

## §2 F4 — Trading_writer drop LIVE WS fills RCA + 設計

### 2.1 RCA — drop 點不在 trading_writer，在 loop_handlers unmatched fill else branch

**Trading_writer 對 engine_mode 沒有 filter**（`database/trading_writer.rs:259-338`）— 無條件寫入 `live` / `live_demo` / `demo` / `paper`。F4 假設「writer 內 silent skip」**錯誤**。

**真正 RCA**（grep verified）：
- `startup/private_ws.rs:144-156` `set_on_fill` 收到 WS fill → emit `ExchangeEvent::Fill(exec)` 到 channel
- `event_consumer/loop_handlers.rs:406-560` `handle_exchange_event` arm `ExchangeEvent::Fill` 處理
- **Line 508** `if let Some(key) = matched_key { ... apply_confirmed_fill(...) ... }` 走 happy path → 寫 fills 表
- **Line 555-560** `else { tracing::warn!("exchange fill has no matching pending order"); }` → **silent return，不寫 fills 表**

**為何 LIVE 全部 unmatched**：
- LIVE 流量目前只有 Bybit 自動發的 funding payment WS fill（04:00/12:00/16:00 三次/天）+ 偶發 Bybit 自動補單（如 dust scrub）
- Python ExecutorAgent `_shadow_mode=True` hardcoded → 0 SubmitOrder IPC 進 Rust → 0 PendingOrder 建立 → 100% WS fill unmatched
- engine.log 顯示 `WS fill / engine=live exec_id=...` info 4 條（funding + 補單），但 trading.fills LIVE 0 條

### 2.2 設計 — 為 unmatched live/live_demo fill 落 unattributed_fill row

**核心原則**：**不掩蓋根本問題**（unmatched WS fill 仍是 architectural gap，需 G3-02/G3-03 ExecutorAgent 接線解決），但**至少落 audit row** 讓 Bybit 自主動作（funding / 補單）有可追溯紀錄。

#### 2.2.1 Fix scope 邊界

**範圍內**：
- 對 unmatched WS fill 落 `trading.fills` row，strategy_name = `"unattributed:bybit_auto"`，context_id = `"unattributed-{exec_id}"`，entry_context_id NULL
- **必加 engine_mode filter**：只對 `live` / `live_demo` / `demo` 觸發此 fallback（paper 不接 WS，不可能達到此 branch；防 future regression）
- 不改 `apply_confirmed_fill` 主路徑（保持 PendingOrder match 是 first-class path）
- realized_pnl = 0（無法重建 entry context；Bybit funding payment 本身 PnL 在 wallet update 反映）

**範圍外**（後續 ticket）：
- ExecutorAgent shadow→live 切換（G3-02/G3-03 Wave 2）
- Bybit funding payment 應用到 paper_state.balance 還是 wallet ledger（已由 `set_on_balance_update` 處理）
- 歷史 LIVE WS fills 從 engine.log 回填（**不做** — log scrape 不可靠 + 量小 ~12 條/週 audit 價值低；標 P3 backlog）

#### 2.2.2 接口 fail-closed 行為

```rust
// loop_handlers.rs line 555-560 修改
} else {
    // F4: emit unattributed_fill row instead of silent drop.
    // PaperEngine: never reaches here (no real WS).
    // Live/Demo: Bybit auto-action (funding payment / dust scrub) → audit-only row.
    let em = pipeline.effective_engine_mode();
    if matches!(em, "live" | "live_demo" | "demo") {
        if let Some(tx) = order_tx {
            let _ = tx.try_send(crate::database::TradingMsg::Fill {
                fill_id: format!("unattrib-{}", exec.exec_id),
                ts_ms: exec_ts,
                order_id: exec.order_id.clone(),
                symbol: exec.symbol.clone(),
                side: exec.side.clone(),
                qty: exec_qty,
                price: exec_price,
                fee: exec_fee,
                fee_rate: 0.0,  // unknown without TIF; audit-only
                realized_pnl: 0.0,  // funding / auto: no entry to compute against
                strategy_name: "unattributed:bybit_auto".to_string(),
                context_id: format!("unattrib-{}-{}", exec.exec_id, exec_ts),
                entry_context_id: String::new(),  // NULL in DB
                engine_mode: em.to_string(),
                exit_source: None,
            });
        }
    }
    tracing::warn!(
        symbol = %exec.symbol, side = %exec.side, exec_id = %exec.exec_id,
        engine_mode = %pipeline.effective_engine_mode(),
        "F4: exchange fill has no matching pending order — audit row emitted \
         / 交易所成交無匹配 pending order — 已落 audit row"
    );
}
```

#### 2.2.3 Healthcheck 補強

新 healthcheck `[21] live_ws_fill_audit_liveness`：
```sql
-- 7 天內 live engine_mode 應有 ≥3 funding payments × 1 symbol = ≥21 unattrib rows
-- 如果 LIVE WS fills 進來但這個 SQL 0 → drop 復發
SELECT
    engine_mode,
    COUNT(*) FILTER (WHERE strategy_name = 'unattributed:bybit_auto') AS audit_rows,
    COUNT(*) FILTER (WHERE strategy_name LIKE 'strategy:%' OR strategy_name LIKE 'risk_close:%') AS attributed_rows,
    MAX(ts) AS last_fill_ts
FROM trading.fills
WHERE engine_mode IN ('live', 'live_demo')
  AND ts > now() - interval '7 days'
GROUP BY engine_mode;
-- PASS: audit_rows >= expected (3 × 7 = 21 funding × 1+ symbol)
-- FAIL: WS fills in engine.log but DB rows = 0 (drop reproduced)
```

**Healthcheck 同時偵測**：
1. WS unattributed audit liveness（Bybit auto-action）
2. ExecutorAgent shadow→live 進度（attributed_rows 從 0 變正 = LIVE 流量啟動）
3. Engine.log vs DB drift（若 grep `WS fill / engine=live` 計數 vs DB count 不對等 → 仍有 drop）

#### 2.2.4 修改點清單

| File:line | 動作 | LOC | 風險評級 |
|---|---|---|---|
| `rust/openclaw_engine/src/event_consumer/loop_handlers.rs:555-560` | 替換 else branch 為 emit unattributed fill | +35 / -3 | 中 |
| `rust/openclaw_engine/src/event_consumer/loop_handlers.rs` tests | 新 unit test for unattributed fill emission（live + live_demo + demo + paper 4 case） | +120 | 低 |
| `helper_scripts/db/passive_wait_healthcheck/checks_derived.py` | 新 fn `check_live_ws_fill_audit_liveness` | +50 | 低 |
| `helper_scripts/db/passive_wait_healthcheck/runner.py` | 註冊 [21] check | +5 | 低 |
| `sql/migrations/V025__trading_fills_strategy_name_index.sql` | partial index `WHERE strategy_name LIKE 'unattributed:%'`（per CLAUDE.md §七 Guard A 規範） | +25 | 低 |

**注意**：trading.fills 已有 (engine_mode, ts) index 但無 strategy_name index — V025 加 partial index 為 healthcheck SQL 性能（rows 量級增長 P3 才需要）。**初版可省略**，等 attributed_rows ≥10K 再加。

### 2.3 E1 派發拆分

| 子任務 | 範圍 | E1 instance | isolation | 工時 |
|---|---|---|---|---|
| **F4-1** loop_handlers.rs else branch fix + 4 unit tests | `loop_handlers.rs` 修改 + `tests/loop_handlers_tests.rs`（新檔） | E1-Alpha | **isolation: worktree**（與 F3-3 T4 同檔撞）| 2h |
| **F4-2** healthcheck [21] live_ws_fill_audit_liveness | `checks_derived.py` + `runner.py` | E1-Beta | 主樹（純新 fn） | 1h |
| **F4-3** ML-FILTER：`learning.exit_features` / outcome_backfiller / ML training pipeline 過濾 `WHERE strategy_name NOT LIKE 'unattributed:%'` 確保不污染學習資料 | `helper_scripts/research/outcome_backfiller_v2.py` 等 | E1-Charlie | 主樹（純 SQL filter）| 1.5h |

**3 子任務工時 ~4.5h** wall-clock（全並行）。

### 2.4 E2 重點審查 3 點

1. **engine_mode filter**：`matches!(em, "live" | "live_demo" | "demo")` 必須完整，遺漏 `live_demo` → 16:00 funding fill 又會 drop。**E2 必查**：grep CLAUDE.md §三 `engine_mode_tag_live_demo upgrade` 確認 schema valid set 是這 4 個。
2. **ML training data hygiene**：F4-3 SQL filter 確保 unattributed rows 不進 LightGBM / Optuna 訓練樣本。**E2 必查**：grep `outcome_backfiller` `experiment_ledger` 等所有 ML pipeline 主路徑都有 `strategy_name NOT LIKE 'unattributed:%'`，否則 `attention_tax` / `cost_edge_ratio` 計算會被 funding noise 污染（與 PNL-FIX-1/2 教訓對齊）。
3. **fill_id uniqueness**：`format!("unattrib-{}", exec.exec_id)` 假設 `exec_id` 全 Bybit 不重複；trading.fills `ON CONFLICT (fill_id, ts) DO NOTHING` 保 idempotent，但若 WS reconnect 重發同 exec_id → 第二次 INSERT skip 是預期行為。**E2 必查**：`exec_id` 同 ts 重複是否會掉資料（**不會** — `seen_exec_set` dedup at line 409 早已 return）。

### 2.5 工時估計

4.5h E1（3 子任務全並行）+ E2 review 1.5h + E4 regression 1.5h = **7.5h** 全鏈。

### 2.6 Regression 風險

- **低風險**：unattributed fill 是 audit-only row，不接 paper_state.balance / strategy stats / Kelly stats / dynamic_risk
- **中風險點**：若 ExecutorAgent G3-02 切 live_mode 後 Python SubmitOrder 來不及建 PendingOrder → race condition unmatched → 落 unattrib row + 漏算 strategy → ML training 漏 row。**Mitigation**：ExecutorAgent 切 live 必須先確認 PendingOrder 建立 ack（`apply_confirmed_fill` 路徑）才能進 next intent；G3-02 設計時 PA 已標 P0 必驗
- **與既有 P0-2 dedup 配合**：`seen_exec_set.contains(&exec.exec_id)` 在 line 409 早於 `matched_key` 邏輯，保 unattrib branch 也 dedup

---

## §3 F6 — Edge estimate stuck reload 設計

### 3.1 RCA 確認

**現場 datapoint**（22:30 採集）：
- `settings/edge_estimates.json` mtime **2026-04-26 22:30:24** size 28338 bytes — scheduler 確實活躍每 ~1h 寫
- engine PID 2033577 boot 02:28 → boot-time inject `PH5-WIRE-1: edge estimates injected n_cells=210 grand_mean_bps=-12.83`（per 任務描述）
- engine.log 02:28 之後 **0 次** PH5-WIRE-1 reload log → 確認 boot-only inject

**Code path**:
- `event_consumer/bootstrap.rs:572-586` boot-time `EdgeEstimates::load_for_mode(&base, mode)` + `pipeline.set_edge_estimates(estimates)` — **無 reload IPC，無 reload daemon**
- `intent_processor/mod.rs:480` `set_edge_estimates()` 是 `&mut self` 的 setter，**沒有 IPC handler 呼叫過**
- `ipc_server/dispatch.rs` grep `set_edge_estimates` `reload_edge` `patch_edge` **0 條 method arm**

**結論**：F6 RCA 與 Phase 5 cost_gate 99.98% reject **真正 root cause**。Engine 內部 edge_estimates 從 02:28 起 stuck，scheduler 寫的最新值 engine 看不到。

### 3.2 設計：1h IPC reload daemon + manual reload IPC method

**核心原則**：
- **mirror G3-08 spawn_h_state_poller pattern**（main_boot_tasks.rs:368-412 已 land）
- daemon thread tokio::spawn + 1h timer + 讀 `settings/edge_estimates.json` mtime → 變更才 reload + 注入到所有 pipeline
- 加 manual IPC `reload_edge_estimates` method 給 operator + scheduler write-then-poke 路徑

#### 3.2.1 雙路徑設計（不二選一，互補）

| 路徑 | 觸發 | 用途 | 落差 |
|---|---|---|---|
| **A. 1h periodic reload daemon** | `tokio::time::interval(Duration::from_secs(3600))` | 守底自動更新 | 最壞 1h stale，可接受（edge cells 1d-rolling window） |
| **B. Manual `reload_edge_estimates` IPC method** | scheduler 寫完 JSON 後 fire IPC notification + operator on-demand | <1s 最新 | 0 stale，require scheduler 改動（小範圍）|

**B 路徑解阻**：scheduler 寫 JSON 後可以 fire-and-forget 呼 `reload_edge_estimates` IPC（類比 PIPELINE-SLOT-1 Phase 3 `trigger_live_auth_recheck` advisory pattern），engine <100ms 反應。**B 不依賴 A**，但 A 是「scheduler crash / IPC 失聯」的兜底。

#### 3.2.2 接口設計

```rust
// rust/openclaw_engine/src/main_boot_tasks.rs 新增
/// PH5-WIRE-1 RELOAD: spawn periodic edge estimates reload daemon.
/// Mirrors spawn_h_state_poller_if_enabled pattern (G3-08 Phase 1C).
/// Default interval = 1h (env override OPENCLAW_EDGE_RELOAD_INTERVAL_SECS).
/// PH5-WIRE-1 RELOAD：定期重載 edge estimates daemon。
pub(crate) fn spawn_edge_estimates_reloader(
    pipelines: Vec<Arc<Mutex<TickPipeline>>>,  // all pipelines (paper/demo/live)
    cancel: &CancellationToken,
    reload_signal_rx: tokio::sync::mpsc::Receiver<()>,  // path B trigger
) -> tokio::task::JoinHandle<()> {
    let interval_secs = std::env::var("OPENCLAW_EDGE_RELOAD_INTERVAL_SECS")
        .ok()
        .and_then(|s| s.parse::<u64>().ok())
        .unwrap_or(3600);  // 1h default
    let cancel = cancel.clone();
    tokio::spawn(async move {
        let mut interval = tokio::time::interval(Duration::from_secs(interval_secs));
        let mut last_mtime: Option<SystemTime> = None;
        loop {
            tokio::select! {
                _ = cancel.cancelled() => break,
                _ = interval.tick() => {},  // periodic path A
                _ = reload_signal_rx.recv() => {},  // manual path B
            }
            // Reload logic — mtime check + load + inject to all pipelines
            // mode-aware: paper → edge_estimates_paper.json, demo/live → edge_estimates.json
            for pipeline_arc in &pipelines {
                let mut pipeline = pipeline_arc.lock().await;
                let mode = pipeline.pipeline_kind.db_mode();
                let base = std::env::var("OPENCLAW_BASE_DIR")...;
                let new_estimates = EdgeEstimates::load_for_mode(&base, mode);
                if new_estimates.is_populated() {
                    let n = new_estimates.n_cells();
                    let gm = new_estimates.grand_mean_bps();
                    pipeline.set_edge_estimates(new_estimates);
                    info!(
                        mode, n_cells = n, grand_mean_bps = gm,
                        "PH5-WIRE-1 RELOAD: edge estimates refreshed / 邊際估計已刷新"
                    );
                }
            }
        }
    })
}
```

**IPC method**:
```rust
// ipc_server/dispatch.rs 加新 arm
"reload_edge_estimates" => handle_reload_edge_estimates(id, edge_reload_signal_tx).await,

// handlers/misc.rs（或新 handlers/edge.rs）
async fn handle_reload_edge_estimates(
    id: serde_json::Value,
    signal_tx: &Option<tokio::sync::mpsc::Sender<()>>,
) -> JsonRpcResponse {
    match signal_tx {
        Some(tx) => match tx.try_send(()) {
            Ok(()) => JsonRpcResponse::success(id, json!({"accepted": true})),
            Err(TrySendError::Full(_)) => JsonRpcResponse::success(id, json!({"accepted": false, "reason": "coalesced"})),
            Err(TrySendError::Closed(_)) => JsonRpcResponse::success(id, json!({"accepted": false, "reason": "reloader_closed"})),
        },
        None => JsonRpcResponse::success(id, json!({"accepted": false, "reason": "reloader_disabled"})),
    }
}
```

#### 3.2.3 Pipeline 多實例同步

3 pipeline (paper/demo/live) 各自 IntentProcessor。reloader 需要 hold 全部 pipeline `Arc<Mutex<TickPipeline>>` references。`main.rs:765-815` 已建好所有 pipelines（spawn_position_reconcilers + spawn_strategist_scheduler 兩個 spawn 點都拿到 pipelines Vec），spawn_edge_estimates_reloader 接同 vec。

**注意 mode 隔離**：paper 讀 `edge_estimates_paper.json`，demo/live 讀 `edge_estimates.json`（per `EdgeEstimates::load_for_mode` 既有邏輯，CLAUDE.md memory `feedback_demo_over_paper_for_edge` 強制）— reloader 對每個 pipeline 獨立 reload，**不混用**。

#### 3.2.4 IPC notification scheduler 接線（B 路徑）

`helper_scripts/research/edge_estimator_scheduler.py` 寫完 JSON 後新增：
```python
# After writing edge_estimates.json successfully
try:
    rpc_client.fire_and_forget("reload_edge_estimates", timeout=1.0)
    logger.info("Notified Rust engine to reload edge estimates")
except Exception as e:
    logger.warning(f"Engine reload notification failed (will rely on 1h periodic): {e}")
```

**fail-closed**：notification 失敗不阻塞 scheduler；A 路徑（1h periodic）兜底。

#### 3.2.5 Auto-deploy af48ee1 是否解決

**結論：不解決長期問題**。af48ee1 `restart_all.sh --rebuild` 後 engine boot inject 看到的是當下最新 edge_estimates.json（22:30 寫的版本，n_cells=210/162 取決於當下值），但**之後仍然 boot-only**。1h reload daemon 必須一起部署才解決長期 stuck 問題。

**派發層次**：F6 是 cost_gate 解阻關鍵（Phase 5 99.98% reject root cause）— 優先級 P0，必與 af48ee1 一起 land。

#### 3.2.6 修改點清單

| File:line | 動作 | LOC | 風險評級 |
|---|---|---|---|
| `rust/openclaw_engine/src/main_boot_tasks.rs` | 加 `spawn_edge_estimates_reloader` fn | +90 | 中 |
| `rust/openclaw_engine/src/main.rs` | 在 spawn_strategist_scheduler 後加 spawn_edge_estimates_reloader call | +12 | 低 |
| `rust/openclaw_engine/src/ipc_server/dispatch.rs` | 加 `"reload_edge_estimates"` arm | +6 | 低 |
| `rust/openclaw_engine/src/ipc_server/handlers/misc.rs` | 加 `handle_reload_edge_estimates` fn | +35 | 低 |
| `rust/openclaw_engine/src/edge_estimates.rs` | 新增 `mtime()` accessor（optional optimization）| +15 | 低 |
| `rust/openclaw_engine/src/main_boot_tasks.rs` tests | unit test for reloader spawn | +60 | 低 |
| `helper_scripts/research/edge_estimator_scheduler.py` | 寫完 JSON 後 fire IPC notification | +15 | 低 |
| `helper_scripts/db/passive_wait_healthcheck/checks_derived.py` | 強化 [13] check 加 「engine 內 edge_cells」 vs JSON cells 一致性比對 | +30 | 低 |

### 3.3 接口 fail-closed 行為

| 異常 | 行為 |
|---|---|
| `edge_estimates.json` 缺失 | reloader 跳過該 cycle，engine 沿用舊估計 |
| `edge_estimates.json` 解析失敗 | 同上 + warn log |
| Pipeline mutex 鎖爭（極短窗口）| reloader spawn 其實在 boot 後，pipeline 已 ready；await 即可 |
| IPC notification 失聯 | 1h periodic 兜底 |
| Scheduler 寫到一半 JSON corrupt | `EdgeEstimates::load_from_file` 解析失敗 → return None → 跳過（既有行為）|

### 3.4 E1 派發拆分

| 子任務 | 範圍 | E1 instance | isolation | 工時 |
|---|---|---|---|---|
| **F6-1** spawn_edge_estimates_reloader fn + unit test | `main_boot_tasks.rs` | E1-Alpha | **isolation: worktree**（與 F4-1 同檔風險低但保險）| 2h |
| **F6-2** main.rs spawn call + reload signal channel wiring | `main.rs` + `ipc_server/dispatch.rs` + `handlers/misc.rs` | E1-Beta | 主樹（依賴 F6-1） | 1.5h |
| **F6-3** Python scheduler IPC notification | `edge_estimator_scheduler.py` | E1-Charlie | 主樹（純新 RPC call） | 0.5h |
| **F6-4** healthcheck [13] 強化（engine vs JSON cell 一致性）| `checks_derived.py` | E1-Charlie | 主樹（純 SQL+RPC）| 1h |

**4 子任務工時 ~5h** wall-clock（F6-1 → F6-2 串行；F6-3 + F6-4 並行 with F6-1/2）。

### 3.5 E2 重點審查 3 點

1. **Mutex 鎖爭與 hot path**：reloader 要 lock pipeline 才能 set_edge_estimates。pipeline 主 hot path（`on_tick`）也是 `&mut self`。若 hot path 已 hold lock，reloader 等到 lock 釋放才能 inject。**E2 必查**：reloader call interval 1h 對 hot path 影響可忽略，但 manual reload 高頻呼叫（e.g. operator 連點按鈕）可能 contention。Mitigation：IPC notification 用 mpsc channel `try_send` capacity 1 coalesce 多次請求為一次（同 PIPELINE-SLOT-1 Phase 3 pattern）。
2. **Mode 隔離正確性**：reloader 對 paper pipeline 必讀 `edge_estimates_paper.json`，對 demo/live 必讀 `edge_estimates.json`。**E2 必查**：grep `EdgeEstimates::load_for_mode` 在 reloader 是否傳對 mode（pipeline_kind.db_mode()），否則 paper 探索噪音會污染 demo edge（CLAUDE.md memory `project_edge_data_isolation` 嚴禁）。
3. **Reload 期間 race**：reloader 正在 inject 新 estimates 時，hot path 正在讀舊 estimates 算 cost_gate。`intent_processor.set_edge_estimates(&mut self)` 是同步 swap（內部 `self.edge_estimates = estimates`），單個 pipeline 內 borrow checker 保證 atomic。但**多 IntentProcessor 競態**（cost_gate 讀 reload 進行到一半的 estimates）—— `set_edge_estimates` 不是 ArcSwap，是直接 replace，所以 lock holder 結束後 hot path 看到完整新 estimates，無 partial state。**E2 必查**：confirm `intent_processor.edge_estimates` field 是 plain field 不是 ArcSwap（既然不是 hot path 高頻 swap，無需 ArcSwap）— 已 verified。

### 3.6 工時估計

5h E1（4 子任務）+ E2 review 1.5h + E4 regression 1.5h = **8h** 全鏈。

### 3.7 Regression 風險

- **中風險點**：reloader 注入時序 — 若 `pipeline.set_edge_estimates` 在 `set_risk_store` / `set_budget_store` 之前 → 可能 inconsistent state。**Mitigation**：reloader 在 main.rs 順序明確（spawn_strategist_scheduler 之後），boot inject 已完成，所有 ConfigStore 已接好
- **低風險**：1h reload 對 cost_gate 影響：reload 後新 grand_mean / cells 立即生效；若 grand_mean 急跌 → cost_gate 突然 reject 增多 → strategy 短時 spawn 0 intent。預期行為（cost_gate 設計如此）
- **無風險點**：af48ee1 一起部署能立刻看到 engine n_cells 從 stuck 的 02:28 boot 值刷到 22:30 latest 值；之後 1h periodic 持續刷
- **與 Phase 5 reframe 對齊**：F6 部署後 cost_gate reject ratio 從 99.98% 應該逐步下降，配合 EDGE-DIAG-1 Phase 3 strategy-scoped fallback 雙管齊下

---

## §4 E1 派發 Schedule

### 4.1 三 P0 fix 並行能力矩陣

| Fix | 主檔 | E1 子任務數 | 同檔衝突 |
|---|---|---|---|
| F3 | `paper_state/fill_engine.rs` + `event_consumer/loop_handlers.rs`（T4 status arm）+ `bootstrap.rs`（T3）| 4 | ⚠️ F3-3 status arm 與 F4-1 else branch 同檔 `loop_handlers.rs` |
| F4 | `event_consumer/loop_handlers.rs` else branch（line 555-560）| 3 | ⚠️ 同上 |
| F6 | `main_boot_tasks.rs` + `main.rs` + `ipc_server/dispatch.rs` + `handlers/misc.rs` | 4 | F6-1 與 F4 / F3 不同檔 |

**衝突點**：F3-3（loop_handlers status arm 加 evict_all_dust 30s reaper）vs F4-1（loop_handlers else branch unmatched fill）— 同檔不同位置，但 isolation worktree 安全。

### 4.2 推薦 wave 派發 schedule

#### Wave 1（並行最大化，5h wall-clock）

| 子任務 | E1 instance | isolation | 依賴 | 開始時間 |
|---|---|---|---|---|
| F3-1 evict_if_dust + tests | E1-Alpha | **worktree-A** | 無 | t=0 |
| F3-3 boot reaper + status arm reaper | E1-Beta | **worktree-B**（loop_handlers 鎖區）| 無 | t=0 |
| F4-1 unmatched fill audit row + tests | E1-Charlie | **worktree-C**（loop_handlers 鎖區）| 無 | t=0 |
| F6-1 spawn_edge_estimates_reloader fn | E1-Delta | **worktree-D** | 無 | t=0 |
| F4-3 ML pipeline filter | E1-Echo | 主樹 | 無 | t=0 |

**5 個 E1 instance 同時跑**：F3-1（fill_engine.rs）/ F3-3（loop_handlers status）/ F4-1（loop_handlers else）/ F6-1（main_boot_tasks）/ F4-3（python ML）。F3-3 vs F4-1 同檔不同 line block，**必 isolation worktree**避撞。

**估計 t=2h 全部 done**。

#### Wave 2（依賴 Wave 1，3h wall-clock）

| 子任務 | E1 instance | isolation | 依賴 | 開始時間 |
|---|---|---|---|---|
| F3-2 hot-path 接 evict_if_dust | E1-Alpha | 主樹 | F3-1 done | t=2h |
| F6-2 main.rs spawn + IPC handler | E1-Beta | 主樹 | F6-1 done | t=2h |
| F3-4 healthcheck [20] | E1-Charlie | 主樹 | F3-1 done | t=2h |
| F4-2 healthcheck [21] | E1-Delta | 主樹 | F4-1 done | t=2h |
| F6-3 Python scheduler IPC notify | E1-Echo | 主樹 | F6-2 done | t=2h |
| F6-4 healthcheck [13] 強化 | E1-Foxtrot | 主樹 | F6-2 done | t=2h |

**估計 t=4h 全部 done**。

#### Wave 3（E2 review + E4 regression）

- **E2 batch review**：3 fix 一起 review（per-fix 30min × 3 + cohesive cross-fix 30min ≈ 2h）
- **E4 regression**：cargo test --release lib + 3 healthcheck dry-run（~1.5h）

**估計 t=7.5h 全部 done**。

### 4.3 Total wall-clock

**Wave 1（並行最大化）+ Wave 2（依賴後續）+ Wave 3（review）= 7.5h**

對比 串行（F3 8h + F4 7.5h + F6 8h = 23.5h）→ 派發並行省 **16h**。

### 4.4 沒做的事（其他 ticket 領域）

- **沒寫實作碼**（E1 領域全部留待派發）
- **沒 spawn sub-agent**（純 PA design）
- **沒派 E1 sub-agent**（等 PM 拍板上派）
- **沒擴範圍到** ExecutorAgent shadow→live 切換（G3-02/G3-03 Wave 2）/ ML-TRAINING-DATA-HYGIENE-1（隔壁 P2 ticket）/ Reconciler EX-04 對 spiral drift 補正（F2 P1 backlog）

### 4.5 16 原則對照

| 原則 | F3 影響 | F4 影響 | F6 影響 |
|---|---|---|---|
| #1 單一寫入口 | ✅ | ✅ unattributed 經 trading_writer | ✅ |
| #2 讀寫分離 | ✅ | ✅ 純 audit row | ✅ reload daemon 不寫策略狀態 |
| #4 策略不繞風控 | ✅ evict 是非交易動作 | ✅ unattrib 不算 strategy | ✅ |
| #5 生存 > 利潤 | ✅ 強化（dust 不再 spiral）| ✅ | ✅ |
| #6 失敗默認收縮 | ✅ fail-closed evict | ✅ engine_mode filter 限定 | ✅ fail-closed reload |
| #7 學習 ≠ 改寫 Live | ✅ evict 不寫 ML 表 | ✅ ML filter 阻 unattrib 進訓練 | ✅ reload 純讀 |
| #8 交易可解釋 | ✅ tracing::warn 結構化 | ✅ unattrib audit row 可重建 | ✅ |
| #9 災難保護 | ✅ status arm 30s 持續守底 | n/a | ✅ 1h periodic + manual fallback |
| #10 認知誠實 | ✅ | ✅ 不掩蓋根本問題 | ✅ 對 stuck root cause 命名清楚 |

3 fix 全不觸碰 §四 5 項 live 硬邊界（`live_execution_allowed` / `max_retries` / Mainnet env / authorization.json / Operator auth）。

---

## §5 教訓備忘（給未來 PA / 同類設計）

1. **「文件 mtime 新」≠「engine 看到新值」**：F6 RCA 第一波檢查若只看 `settings/edge_estimates.json` mtime fresh 會錯判沒問題；必須驗 engine 內部 inject 路徑（grep `set_edge_estimates` callsite）。runtime evidence 優於 file system evidence。
2. **「writer 沒 silent skip」≠「DB 有 row」**：F4 假設「writer skip live」是 trap；真正 drop 在更上游 `else { warn!(); }` branch。debug fill drop 必順鏈條從 `private_ws emit` → `event_consumer` → `apply_confirmed_fill` → `trading_writer` 全程查，不可只看 last hop。
3. **「dust evict via qty threshold」對 funding-accrued residue 無效**：`pos.qty < 1e-12` 在 STRKUSDT 7e-13 case 生效，但對 `qty * price < 1.0 USD` 但 `qty > 1e-12` 的 sub-cent residue 失效。USD-denominated floor 是更穩健 invariant（與 af48ee1 Gate 1 設計對齊）。
4. **「spawn_h_state_poller pattern」是大範圍 background daemon 的 reusable template**：spawn fn → main.rs spawn call → IPC notification → cancel_token shutdown。F6 reloader 沿用同 pattern 0 創新。未來任何 background daemon design 先 grep `spawn_h_state_poller` `spawn_strategist_scheduler` 找 reference 而不是重新發明。
5. **多 fix 派發前必 dependency-graph 全攤開**：本次 F3 / F4 / F6 三 fix 看似獨立，但 F3-3 與 F4-1 同檔同 fn 不同 line block，必 isolation worktree。派發前 `git diff main...HEAD --name-only` 比對所有 fix 主檔，撞區必標 isolation。

---

PA DESIGN DONE: report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--three_p0_fixes_design.md
