# PAPER-STATE-DUST-RESTORE-AUDIT — PA design audit

**狀態**：✅ Design audit 完成（3 option 對比 + cross-env 安全性 + recommend Option B + healthcheck [2X] spec）
**派發來源**：PM Tier 6 Track 3（Tier 5 sign-off `f4c5bad` + EXIT-FEATURES-WRITER-BUG-1-FIX `af48ee1`+`83456e5` 完成後 follow-up #1）
**MIT audit 來源**：`docs/CCAgentWorkSpace/MIT/workspace/reports/2026-04-26--exit_features_writer_bug_audit.md` §6 follow-up #1
**Audit 範圍**：`paper_state::restore_from_db` + `import_positions` + dust-eviction + retriage + EventConsumer bootstrap
**Audit 日期**：2026-04-26 17:00 CEST
**結論一句話**：restore_from_db 不重建倉位；STRKUSDT dust spiral 與 restore 無關；推 **Option B（保持現狀）+ 補一條 healthcheck [2X] dust inventory 監控** + 將 P2 ticket scope 改寫。Option A 有 cross-env live safety risk，禁此實施。

---

## §1 背景

### 1.1 MIT §6 follow-up #1 重述

> `paper_state::restore_from_db` 為何 engine 重啟後沒清掉 0.1 dust（entry_notional=0 進入 fast_track ReduceToHalf spiral）？是否需要 startup-time evict dust？

PM 期望輸出：是 paper_state restore 階段 evict、還是 EventConsumer bootstrap 後再 sweep 還是純依賴 fast_track USD floor gate。並答覆跨 env 安全性。

### 1.2 與 EXIT-FEATURES-WRITER-BUG-1-FIX 關係

EXIT-FEATURES-FIX（commits `af48ee1` + `83456e5`）做了 4 件事：

1. **RCA-A path 1 A1**：`step_0_fast_track.rs:328-408` 加 layered dust filter（Gate 1 USD floor `ft_dust_qty_floor_usd` 預設 1.0 USD 在所有 branch active；Gate 2 ratio gate 只在 `entry_notional > 0` active）
2. **RCA-A path 1 A3**：`event_consumer/bootstrap.rs:294-317` 在 `import_positions()` 後 idempotent 呼 `migrate_legacy_entry_notional()`（防 Bybit REST `avg_price=0` 殘留留下 entry_notional=0）
3. **RCA-A schema**：新增 `RiskConfig.limits.ft_dust_qty_floor_usd` 預設 1.0 USD、3 env TOML 接線
4. **RCA-B path 2 B1**：`pipeline_helpers.rs:217 try_emit_exit_feature_row` 對 partial reduce tag skip EF emit

A3 是「防禦深度」，**已**對 import path 補了 entry_notional backfill；MIT 是問 PM「**還有沒有**其他遺漏的 dust source 路徑需要 startup evict」。本 audit 答：**沒有顯著新 source**；fix 已覆蓋；多餘 evict 對 live 反而危險。

---

## §2 現況路徑分析

### 2.1 paper_state restore 流程 trace（file:line）

| 步驟 | Caller | Callee | 動作 |
|---|---|---|---|
| 1 | `event_consumer/bootstrap.rs:281` | `paper_state_restore::restore_paper_counters` | 從 trading.fills 還原 cumulative counter（不重建倉位） |
| 2 | `paper_state_restore.rs:65` | `PaperState::restore_from_db` | SQL aggregate `SUM(fee)/SUM(realized_pnl)/COUNT(*)` 寫入 `total_fees/total_realized_pnl/trade_count` |
| 3 | `paper_state_restore.rs:97` | `paper_state::checkpoint::load_checkpoint` | 從 `trading.paper_state_checkpoint` 還原 `peak_balance + session_start_ts_ms`（**不還原倉位** — 這表只存 2 個 scalar） |
| 4 | `event_consumer/bootstrap.rs:286` | `pipeline.paper_state.import_positions(seed_positions)` | 從 Bybit REST snapshot 種倉，**這才是倉位來源** |
| 5 | `event_consumer/bootstrap.rs:308` | `paper_state.migrate_legacy_entry_notional()` | EXIT-FEATURES-FIX A3 idempotent backfill `entry_notional == 0 && qty > 0 → qty * entry_price` |
| 6 | `event_consumer/bootstrap.rs:329` | `paper_state.set_positions_mirror(mirror)` | 換成 main.rs 構造的 shared mirror handle |
| 7 | `event_consumer/bootstrap.rs:393` | `paper_state.triage_bybit_sync(...)` | **僅對 `owner_strategy == "bybit_sync"` 倉位** 走 dust gate（adopted/evicted/dust_frozen 三桶） |

**關鍵事實**：
- **`restore_from_db` 與 `load_checkpoint` 不重建 positions map** — `paper_state` 表 schema 只有 `(engine_mode, peak_balance, session_start_ts, updated_at)` 4 欄，**無倉位欄**（`paper_state/checkpoint.rs:51-72`）
- `restore_from_db` 跑 `SELECT SUM(fee), SUM(realized_pnl), COUNT(*) FROM trading.fills WHERE engine_mode = $1` 只還原 3 個 scalar counter（`fill_engine.rs:220-243`）
- 倉位**唯一**來源是 `import_positions(seed_positions)`（`fill_engine.rs:44-75`），seed_positions 在 main.rs 從 Bybit REST `GET /v5/position/list` 抓
- Bybit REST 對於部分平倉殘留 dust 通常返 `size=0.05 + avg_price=15.0` → `entry_notional = qty * entry_price = 0.75 USD > 0` → 不進 migrate path
- 但**邊角情境**：Bybit REST 偶爾對 stale dust 返 `avg_price=0` → `import_positions` line 48 guard `entry_price <= 0 continue` 直接 skip → **倉位根本不進 paper_state**；如果 guard 沒 skip（如 `avg_price=0.0001` 接近 0 但通過 `> 0` 檢查），entry_notional ≈ 0 → A3 backfill 會補成 `0.05 * 0.0001 = 0.000005 USD` 仍極小 → Gate 1 USD floor 1.0 USD 仍 catches

### 2.2 為何 0.1 dust 沒被 evict 的 root cause

**MIT audit §3 + STRKUSDT lineage 分析顯示 dust 不是 restore 來源**，而是 runtime 累積：

```
2026-04-23 19:30  ma_crossover entry qty=2269.1 → close 2269 (留 0.1 dust)
2026-04-24 03:14  grid_trading entry qty=2224.6 → close 2224.5 (留 0.1 dust)
2026-04-24 03:17 ~ 2026-04-26 07:37  engine 持續運作（無重啟），dust 持續積累
2026-04-26 07:37  fast_track_reduce_half 對這 0.1 qty 倉位下手 → spiral
```

**為何沒 evict**（root cause 鏈）：

1. **partial close 殘留 dust**：`reduce_position`（`fill_engine.rs:366-387`）關閉 2269.0 後留 `pos.qty = 0.1`；`if pos.qty < 1e-12` 才 remove → 0.1 qty 不夠小不被刪
2. **owner_strategy 仍是 ma_crossover/grid_trading（real strategy）**：dust 倉位的 `owner_strategy` 跟著 entry 階段設好，**reduce 不會改 owner_strategy** → 不在 `SYNTHETIC_OWNER_LABELS` 內 → `retriage_synthetic_owner` 直接 fast-path NoOp（`owner_attribution.rs:112-114`）
3. **entry_notional 在 reduce 路徑**：`apply_fill` 同向 accumulate 走 `fill_engine.rs` apply_fill 內 entry_notional 累加；reduce_position **不減 entry_notional**（MICRO-PROFIT-FIX-1 option 2 語義）— 但 spiral 起點 entry_notional=0 暗示**有某處 reset**（候選：apply_fill 反向關倉時 `pos.is_long != is_long` close path）。**未深查**因為 fix 已對 fast_track 套絕對 USD floor 兜底（不依賴 entry_notional 是否 > 0）
4. **strategy close signal 不 fire**：strategy（ma_crossover/grid_trading）的 SL/TP/exit signal 邏輯對 0.1 qty 殘留通常 evaluate `qty * price = 0.05 * X USD` 太小不觸發任何閾值 → 倉位永遠 stuck（dormant orphan with real strategy label）
5. **fast_track 是唯一 active 路徑**：fast_track Step 0 的 ReduceToHalf 對所有 paper_state.positions() 掃 → 對 0.1 qty 套 `entry_notional <= 0 → return true` (pre-fix MICRO-PROFIT-FIX-1 fail-open) → 半倉 → 0.05 → 0.025 → ...（37 次到 7.3e-13）

**總結 root cause**：dust 不是 restore 來源 → restore 怎麼修都救不了這個 spiral；**真正的修法是 EXIT-FEATURES-FIX 套的 fast_track Gate 1 USD floor**（已落地）+ 看 strategy close 為什麼對 dust 不發 close signal（**out-of-scope**，屬 strategy team 的 dust handling）。

---

## §3 Option A：startup-time dust eviction（加 migrate_legacy_dust_qty）

### 3.1 設計

鏡射 EXIT-FEATURES-FIX A3 `migrate_legacy_entry_notional` pattern，在 bootstrap.rs:308 之後加：

```rust
// PAPER-STATE-DUST-RESTORE-AUDIT (Option A): startup-time dust eviction
// 啟動時對 qty * latest_price < dust_floor_usd 的倉位 evict
let evicted = pipeline.paper_state.migrate_legacy_dust_qty(
    cfg_snapshot.dust_eviction_floor_usd,  // 預設 1.0 USD（與 fast_track Gate 1 一致）
    instrument_cache.as_ref(),
);
if evicted > 0 {
    warn!(
        kind = %pipeline_kind,
        evicted,
        "PAPER-STATE-DUST-RESTORE-AUDIT: startup dust eviction / 啟動時 dust 清理"
    );
}
```

新增 `paper_state/accessor.rs::migrate_legacy_dust_qty`：

```rust
pub fn migrate_legacy_dust_qty(
    &mut self,
    floor_usd: f64,
    instrument_cache: Option<&InstrumentCache>,
) -> usize {
    let symbols_to_evict: Vec<String> = self.positions
        .iter()
        .filter(|(sym, pos)| {
            let ref_price = self.latest_prices.get(sym.as_str())
                .copied()
                .filter(|v| *v > 0.0)
                .unwrap_or(pos.entry_price);  // fallback to entry_price (race window)
            let est_notional = pos.qty * ref_price;
            est_notional < floor_usd
        })
        .map(|(sym, _)| sym.clone())
        .collect();

    let mut count = 0;
    for sym in symbols_to_evict {
        // 先 dispatch CloseSymbol 給 reconciler，再 remove from paper_state
        // （注意：Live 端不可直接 remove，會引發 silent drift）
        self.positions_remove(&sym);
        count += 1;
    }
    count
}
```

### 3.2 評估

| 維度 | 評估 |
|---|---|
| **修哪些檔** | `paper_state/accessor.rs`（新增 fn ~30 LOC）+ `event_consumer/bootstrap.rs`（接線 ~10 LOC）+ `RiskConfig.limits` 加 `dust_eviction_floor_usd` 字段 + 3 env TOML + 5-8 unit tests |
| **跨 env 安全性** | **❌ FAIL** — Live 端有 user 真實小單（如 user 故意留 0.5 USD ATM 對沖 / scalper micro position），startup 一刀切 evict 會無聲消除 user 持倉 → 違反根原則 #5（生存>利潤）+ #8（交易可解釋） |
| **解決什麼** | restore 進來時就把 dust 清掉，省 fast_track Gate 1 兜底；架構上更乾淨 |
| **未解決** | dust 真正 source 是 runtime（partial close 殘留），restore 階段清不到 runtime 累積；只覆蓋 Bybit REST 邊角情境 |
| **副作用** | (1) Live 誤刪 user 持倉 (2) Demo/Paper 啟動 dust evict 後 paper_state 與 reconciler/exchange 短暫不一致 — 需先 dispatch CloseSymbol 走完一輪對賬才安全 (3) instrument_cache 在 bootstrap 早期 race window 可能未就緒 |
| **與 fast_track Gate 1 重疊** | Gate 1 已防 spiral；A 對 spiral 沒額外 ROI；只是讓 dust **更早**消失（一次性 vs 每 tick skip） |
| **複雜度** | 中等：需處理 dispatch CloseSymbol + race + cross-env guard |
| **可逆性** | 改 TOML `dust_eviction_floor_usd = 0.0` 即關 — 可逆 |

### 3.3 結論

**A 不推薦**。Live 安全性 hard fail。即使加 `if pipeline_kind == Paper` env guard 也僅 paper 受益，paper 本就低風險；**ROI 不足以蓋過 cross-env 風險**。

---

## §4 Option B：保持現狀（依賴 fast_track USD floor gate）

### 4.1 設計

**不動 paper_state restore 任何代碼**。依賴：

1. EXIT-FEATURES-FIX A1 已套的 `fast_track Gate 1 ft_dust_qty_floor_usd = 1.0 USD` — 防 spiral
2. EXIT-FEATURES-FIX A3 已套的 `migrate_legacy_entry_notional()` — 防 Bybit REST `avg_price=0` 邊角情境
3. EXIT-FEATURES-FIX B1 已套的 `try_emit_exit_feature_row` partial-reduce skip — 防 EF 污染

**新增**（防衛性）：
- 新 healthcheck `[2X] paper_state_dust_inventory`（純監控、不 mutate）— 偵測 dust spiral 復發 + paper_state 累積 dust 趨勢

### 4.2 評估

| 維度 | 評估 |
|---|---|
| **修哪些檔** | 純 healthcheck（`helper_scripts/db/passive_wait_healthcheck/checks_engine.py` 加 ~30 LOC） |
| **跨 env 安全性** | ✅ PASS — 不 mutate 任何 production state；healthcheck 是純讀 SQL |
| **解決什麼** | 監控 dust 累積趨勢；偵測 spiral 復發；給 operator 量化視窗 |
| **未解決** | 不主動清 runtime 累積的 dust；fast_track 每次 tick 都會觸發 Gate 1 skip（log spam in dust-heavy env） |
| **副作用** | 0 副作用 — 純監控 |
| **與 fast_track Gate 1 重疊** | 無重疊；healthcheck 是元觀察層 |
| **複雜度** | 低：1 SQL + 1 cron 條目 |
| **可逆性** | 改 SQL or 移除 check 即可 |

### 4.3 結論

**B 推薦為主路徑**。Cross-env safe + 已有完整防護鏈（Gate 1 + Gate 2 + A3 + B1）+ healthcheck 補上監控盲點 + 0 production state mutation 風險。

---

## §5 Option C：EventConsumer bootstrap 後 sweep（非 paper_state restore 內）

### 5.1 設計

不改 paper_state restore 邏輯，而是在 bootstrap.rs 末端（line ~457 triage 完成後、ready_tx send 前）加 post-bootstrap sweep：

```rust
// PAPER-STATE-DUST-RESTORE-AUDIT (Option C): post-bootstrap dust sweep
// 走 retriage 既有 dust gate 路徑（不另開 evict logic）
if pipeline_kind.is_exchange() {
    let now_ms = openclaw_core::now_ms();
    let symbols: Vec<String> = pipeline.paper_state.positions()
        .iter()
        .map(|p| p.symbol.clone())
        .collect();
    for sym in symbols {
        if let Some(price) = pipeline.paper_state.latest_price(&sym) {
            // 對所有倉位（含 real-strategy owner）跑一次 dust 檢查
            // - 若 qty * price < min_notional → flip owner_strategy 到 DUST_FROZEN_STRATEGY
            // - 後續 retriage_synthetic_owner per-tick 接管
            pipeline.maybe_freeze_dust_at_startup(&sym, price, now_ms);
        }
    }
}
```

**核心差異與 A**：不直接 evict，而是「**flip owner_strategy 到 DUST_FROZEN_STRATEGY**」讓 per-tick retriage 自然接管（Promote / Evict / Frozen 三選一決定）。

### 5.2 評估

| 維度 | 評估 |
|---|---|
| **修哪些檔** | `tick_pipeline/pipeline_helpers.rs`（新增 `maybe_freeze_dust_at_startup` ~20 LOC）+ `event_consumer/bootstrap.rs`（接線 ~15 LOC）+ 5 unit tests |
| **跨 env 安全性** | ⚠️ MEDIUM — 不刪倉位（safer than A），但 flip 真實策略 owner_strategy → DUST_FROZEN_STRATEGY 後，原 strategy 再也不對該倉發 close signal（label 已不是它的）；如果 user 在 live 的小單**被誤判**為 dust → strategy 接不回 → 永久卡 frozen（須 operator GUI 手動）。比 A 安全因為「不刪」、但仍有「卡 frozen」的真實風險 |
| **解決什麼** | dust 主動進 retriage 系統 → per-tick 自動評估 promote/evict/freeze；不依賴 fast_track 兜底 |
| **未解決** | 不 retroactive 清 runtime 累積 dust（除非每次重啟）— 大部分 dust 仍由 runtime 產生而非 restore |
| **副作用** | (1) flip real strategy → DUST_FROZEN 後即使後來 qty/price 上升回 above min_notional，retriage 升級到 KNOWN_STRATEGY_NAMES[0]（ma_crossover），**不一定是原 owner**；strategy 歸因失真 (2) 增 bootstrap latency（exchange-mode N×O(1) lookup） |
| **與 fast_track Gate 1 重疊** | 部分重疊 — C 主動 flip + retriage NeedsEviction 派 close；Gate 1 被動 skip。C 較積極但 path 較複雜 |
| **複雜度** | 中：要設計 freeze flip 條件 + 不衝撞 strategy ownership |
| **可逆性** | 改 startup_dust_freeze flag 即關 |

### 5.3 結論

**C 不推薦**。增複雜度、改變 ownership semantic（potentially breaks strategy attribution + audit log）、live 仍有「卡 frozen」風險。Per-tick `retriage_synthetic_owner` 已 cover synthetic-owner dust 自動處理；C 唯一新增的是「**對 real-strategy owner 也 flip**」這件事，但 real-strategy owner 應由策略自身管 lifecycle（§原則 #11），不該被 dust gate 強制接管。

---

## §6 Recommend

**選 Option B（保持現狀 + 加 healthcheck [2X]）** + **重寫 PAPER-STATE-DUST-RESTORE-AUDIT P2 ticket scope**。

**一句話理由**：dust spiral root cause 在 runtime（partial close 殘留 + strategy 不對 dust 發 close signal）非 restore；EXIT-FEATURES-FIX 已用 fast_track Gate 1 USD floor 從**消費端**徹底防 spiral；A/C 從**生產端**改 paper_state state，跨 env 安全性無法保證且 ROI 邊際小。**B 用 healthcheck 補監控盲點即可閉環**。

### 6.1 Cross-env 安全性 caveat

| 環境 | A 風險 | B 風險 | C 風險 |
|---|---|---|---|
| Paper | 低（純沙盒） | 0 | 低 |
| Demo | 低（虛擬資金） | 0 | 中（demo 也有 user 對賬期望） |
| Live | **FAIL — 誤刪 user 持倉** | 0 | **MEDIUM — 卡 frozen + ownership flip** |

**Hard requirement**：Operator 任務 `Hard rules > 跨 env 安全性是 hard requirement` 已明列「**不可建議任何會誤刪 live user 真實小單的方案**」— A/C 兩個 option 違背此 hard rule，**Reject A and C**。

### 6.2 殘留風險（B 採納後仍存）

1. **fast_track Gate 1 log spam**：dust-heavy env（如 STRKUSDT 0.1 + 其他 partial-close 殘留）每 tick 觸發 Gate 1 skip log；建議 follow-up（非本 audit scope）：對 same (sym, dust_state) 加 1h 去重 log
2. **Strategy 不對 dust 發 close signal**：real-strategy owner 對 0.1 qty dust 不發 SL/TP/exit；倉位永遠 stuck 由 fast_track Gate 1 skip 兜著 — `paper_state.positions()` 會持續累積 dust pollution；**operator 需週期性手動清 Bybit GUI** 或派 follow-up ticket（屬 strategy team scope，**非 paper_state**）
3. **Bybit REST `avg_price=0` 邊角情境**：A3 `migrate_legacy_entry_notional` 已防護；殘留風險 = `avg_price=0.0001` 之類「接近 0 但通過 `> 0` guard」的極端值 → entry_notional 仍極小 → fast_track Gate 1 1.0 USD floor 兜底
4. **Healthcheck [2X] 自身誤報**：dust=0 PASS 是 sweet spot；但 paper/demo 啟動初期可能短暫 dust > 0（B-1 Phase 2 import 後尚未走過第一輪 fast_track）— 需 grace period

---

## §7 執行 prompt template + healthcheck [2X] 補強建議

### 7.1 下次 session E1 prompt（純 healthcheck 補強，**不動 paper_state/*.rs 業務碼**）

```
PM Tier 6 Track 4 派發 — PAPER-STATE-DUST-RESTORE-AUDIT 落地（B 路線）

## 背景
PA 2026-04-26 audit（docs/CCAgentWorkSpace/PA/workspace/reports/
2026-04-26--paper_state_dust_restore_audit.md）推 Option B：保持現狀
+ 加一條 healthcheck [2X] 純監控 dust inventory。

## 任務
在 helper_scripts/db/passive_wait_healthcheck/checks_engine.py 加：

def check_paper_state_dust_inventory():
    """
    [2X] paper_state_dust_inventory — monitor runtime dust accumulation
    和 spiral 復發跡象（不 mutate state）。

    PASS / WARN / FAIL 條件：
    - 過去 1h trading.fills WHERE strategy_name LIKE 'risk_close:fast_track%'
      AND realized_pnl = 0 AND engine_mode IN ('demo','live','live_demo')：
        count = 0 → PASS
        count 1-10 → WARN（dust skip log，每筆代表 Gate 1 fired）
        count > 10 → FAIL（可能新 spiral path 出現，Gate 1 兜不住）
    - 同期 fast_track_reduce_half qty < 1.0 USD 觸發次數 ≥ 5 → WARN
      （hint dust 累積過量，operator 可能需手動清 GUI）
    """
    # NOTE (Amend 2026-04-26 per §13 Deviation Log): SQL 已落地為 E1 Tier 7
    # commit `8241133` 版本（drop partial_reduce_real_count + 加 FILTER 到
    # COUNT(DISTINCT symbol)；E2 評為 improvement not regression）。
    # 完整 deviation 解釋見 §7.2。
    sql = '''
    SELECT
      COUNT(*) FILTER (WHERE realized_pnl = 0) AS dust_spiral_count,
      COUNT(DISTINCT symbol) FILTER (WHERE realized_pnl = 0) AS distinct_dust_symbols
    FROM trading.fills
    WHERE strategy_name LIKE 'risk_close:fast_track%'
      AND ts > now() - interval '1 hour'
      AND engine_mode IN ('demo','live','live_demo');
    '''
    # ... return ("PASS"|"WARN"|"FAIL", message)

## 修哪些檔
1. helper_scripts/db/passive_wait_healthcheck/checks_engine.py — 加 check_paper_state_dust_inventory()
2. helper_scripts/db/passive_wait_healthcheck/__init__.py（or 主 register）— 註冊為 [19] dust inventory（[18] disabled_strategy_inventory 已在）
3. README.md or healthcheck doc — 加 [19] 說明
4. 不改任何 rust/openclaw_engine/src/paper_state/*.rs ✅

## Tests
- helper_scripts/db/tests/test_dust_inventory_healthcheck.py 新增 4 cases：
  · test_zero_dust_returns_pass
  · test_low_dust_count_returns_warn
  · test_spiral_threshold_returns_fail
  · test_distinct_symbols_warn_branch

## Commit message
healthcheck: [19] paper_state_dust_inventory — monitor dust spiral recurrence

PA 2026-04-26 audit (docs/CCAgentWorkSpace/PA/workspace/reports/
2026-04-26--paper_state_dust_restore_audit.md) recommended Option B
(no paper_state mutation, monitor only). This adds healthcheck [19]
covering MIT §6 follow-up #1 + EXIT-FEATURES-FIX防護鏈的 observability gap：

- Gate 1 USD floor (af48ee1) prevents spiral but is silent — no metric
- This check counts past-1h gate1_fired_count + partial_reduce_real_count
  + distinct_dust_symbols → PASS/WARN/FAIL classification
- Cross-env safe: pure SELECT, 0 mutation, fail-soft on PG unavail

## 完成標準
- pytest 4 cases 綠
- cron 跑一次回 PASS（demo 環境若無新 spiral）
- audit report follow-up 條目劃掉

Hard rules
- ❌ 不改 rust/openclaw_engine/src/paper_state/*.rs
- ❌ 不加任何 evict / mutate state 路徑
- ✅ commit + push 直接執行
- ✅ git commit --only 隔絕 multi-session race
```

### 7.2 healthcheck [2X] SQL spec（one-liner copy-paste 版）

> **Amend 2026-04-26**（per §13 Deviation Log）— 本節原 spec 含 `partial_reduce_real_count` 與 unfiltered `COUNT(DISTINCT symbol)`，已 amend 為 E1 Tier 7 commit `8241133` 落地版本（E2 評為 improvement not regression），與 production cron 一致。Slot 編號上線時實佔 **[21]**（[19] observer / [20] h_state_gateway 已被佔；本章節原寫 [19] 為 design-time placeholder）。

```sql
SELECT
  COUNT(*) FILTER (WHERE realized_pnl = 0) AS dust_spiral_count,
  COUNT(DISTINCT symbol) FILTER (WHERE realized_pnl = 0) AS distinct_dust_symbols
FROM trading.fills
WHERE strategy_name LIKE 'risk_close:fast_track%'
  AND ts > now() - interval '1 hour'
  AND engine_mode IN ('demo','live','live_demo');
```

**兩項 deviation 與 PA 原 spec 對比**：

1. **`COUNT(DISTINCT symbol)` 加 `FILTER (WHERE realized_pnl = 0)`**（PA 原 spec 為 unfiltered）
   - **EN**: Restricting the distinct-symbol count to dust-path rows (`realized_pnl = 0`) gives a **truer dust-spiral fan-out signal**. The unfiltered version would inflate `distinct_dust_symbols` whenever a partial-reduce real close (`realized_pnl != 0`) happened to land on a separate symbol within the same 1h window — that symbol is *not* part of the dust spiral, only the partial-reduce path. Filtering aligns the metric semantically with the verdict goal: "how many distinct symbols are exhibiting Gate-1-suppressed dust activity right now".
   - **中**：把 `distinct_dust_symbols` 限制在 dust 路徑（`realized_pnl = 0`）內，得到**更精確的 dust spiral fan-out 信號**。原 unfiltered 版本一旦同 1h 窗內有任意 symbol 出現 partial-reduce real close（`realized_pnl != 0`），該 symbol 也會計入 distinct_symbols — 但這 symbol *並非* dust spiral 一員，只是 partial-reduce path。加 FILTER 讓指標語意對齊 verdict 目標：「當前有多少 distinct symbol 正在出現 Gate-1 抑制的 dust 活動」。

2. **drop `partial_reduce_real_count` column**（PA 原 spec 多此 column）
   - **EN**: This column is **outside the [21] check's business scope**. The check's verdict logic only consumes `dust_spiral_count` + `distinct_dust_symbols`; `partial_reduce_real_count` is informational telemetry that belongs to a separate observability slice (e.g. partial-reduce path health is owned by EXIT-FEATURES B1 + reconciler EX-04, not this dust sentinel). Keeping it here only adds query cost (one extra `FILTER` aggregate per cron tick) without informing any downstream branch. Drop respects single-responsibility.
   - **中**：此 column **不在 [21] check 的業務邏輯範圍**內。Check 的 verdict 只消費 `dust_spiral_count` + `distinct_dust_symbols`；`partial_reduce_real_count` 屬於另一個 observability 切片的訊息（partial-reduce path 健康由 EXIT-FEATURES B1 + reconciler EX-04 負責，不是 dust 哨兵）。保留在此只增加 query cost（每次 cron tick 多一個 `FILTER` aggregate）而不影響任何 downstream 分支判斷。drop 符合 single-responsibility。

**Classification**（thresholds 與 PA 原 spec 不變，只欄位名換）：
- `dust_spiral_count = 0` → **PASS**（Gate 1 USD floor 工作中，無 spiral 跡象）
- `1 <= dust_spiral_count <= 10` AND `distinct_dust_symbols < 3` → **WARN**（Gate 1 可能還抓住但有 dust path 活動）
- `dust_spiral_count > 10` OR `distinct_dust_symbols >= 3` → **FAIL**（Gate 1 兜不住或新 spiral path 跨多 symbol 出現）

**重要**：`dust_spiral_count` 是 EXIT-FEATURES-FIX A1 Gate 1 skip 後仍漏入 fills 的 row count；**穩態下應為 0**（fix 後 partial reduce 整個 skip EF emit + Gate 1 skip 本身**不寫 fill**）— 如果 > 0 表示 fix 不完整或 spiral 路徑復活。**0 = 健康**。

實際上 EXIT-FEATURES-FIX 後 trading.fills 不該再有 `risk_close:fast_track%` 且 `realized_pnl = 0` 的 row（partial reduce path 仍寫 fill 但 realized_pnl != 0；Gate 1 整個 skip 不下單也不寫 fill）。所以這個 count `> 0` 即異常 alarm，**靈敏度高**。Linux production cron 16:09 UTC LIVE PASS 確認 0 spiral activity。

### 7.3 Healthcheck [19] cron 整合

加在現有 `passive_wait_healthcheck.py` 結尾，隨既有 6h cron 跑：

```python
# ... existing checks [1] - [18] ...

def check_19_paper_state_dust_inventory():
    """[19] PAPER-STATE-DUST-RESTORE-AUDIT (PA 2026-04-26 Option B)"""
    # ... 上面 SQL 實作 ...
    return ("PASS"|"WARN"|"FAIL", message)
```

### 7.4 重寫 PAPER-STATE-DUST-RESTORE-AUDIT P2 ticket（PM 採納時更新 TODO.md）

**原 ticket**：
> ### PAPER-STATE-DUST-RESTORE-AUDIT（P2，PA 派 E1）
> - **Owner**: PA design + E1 audit
> - **工時**: 0.5-1d
> - **內容**: paper_state::restore_from_db dust handling 邏輯 audit + 是否該 startup-time evict dust 倉位

**改為**：
> ### PAPER-STATE-DUST-INVENTORY-MONITOR（P2，已派 E1 healthcheck only）
> - **Owner**: E1（healthcheck only，~1h）
> - **PA 結論**: `docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--paper_state_dust_restore_audit.md` 推 **Option B**（不動 restore 業務碼）— restore 不重建倉位、dust 不來自 restore；Option A/C 對 live 有 user 持倉誤刪/誤卡風險，**Reject**。
> - **內容**: 加 healthcheck `[19] paper_state_dust_inventory` 純監控 EXIT-FEATURES-FIX 防護鏈的 observability gap；不改任何 paper_state 業務碼
> - **完成標準**: 4 unit tests 綠 + cron 跑回 PASS（demo 預期無新 spiral）

---

## §8 不確定 / 追加 audit follow-up

1. **runtime dust 真正 source 路徑**：`apply_fill` 反向 close path 是否在某 case 把 entry_notional reset 為 0？本 audit **未深查 apply_fill** 完整 close path 細節（Read 至 fill_engine.rs:280 截止）；若需追根可派 E1 sub-task。**但**：fast_track Gate 1 已對 entry_notional == 0 case 兜底（layered filter 設計），即使 root cause 完整 confirm 也不需動 paper_state。
2. **Strategy team dust handling**：ma_crossover/grid_trading 對 0.1 qty 殘留為何不發 SL/TP/exit？是 strategy 設計上 evaluate `qty * price` 太小直接 skip 還是有 bug？**屬 strategy team scope** — 建議 G2-strategy-dust-cleanup follow-up ticket 派 QC 評估
3. **Healthcheck [19] grace period**：B-1 Phase 2 import_positions 後 paper_state 可能短暫有 dust（fast_track 第一輪未跑），可能 false WARN；建議 first 5min 後才開始 check
4. **fast_track Gate 1 log dedup**：dust-heavy env 每 tick 觸發 Gate 1 skip 寫一行 info log，可能 log spam；follow-up（非 PAPER-STATE 範圍）：對 same (sym, dust_state) 加 1h log 去重
5. **Bybit REST 邊角值檢測**：是否有 `avg_price` 異常值 telemetry？建議 follow-up（非本 audit scope）：在 `import_positions` 對 `avg_price < 1e-6 || avg_price > 1e9` 增 warn-log，幫助偵測 Bybit 端異常

---

## §9 治理對照（CLAUDE.md §二 + DOC-08 §12）

| 原則 | Option B 影響 | Option A/C 影響 |
|---|---|---|
| #1 單一寫入口 | ✅ 不改寫入路徑 | ⚠️ 增 startup-time mutate path（A 直 remove / C flip owner） |
| #2 讀寫分離 | ✅ healthcheck 純讀 | ⚠️ A/C 啟動寫 |
| #5 生存>利潤 | ✅ 0 risk | **❌ A/C 可能誤刪 live user 持倉** |
| #6 失敗默認收縮 | ✅ healthcheck 失敗 silent log + 繼續 | A/C 失敗 → engine fail-closed shutdown 嗎？|
| #8 交易可解釋 | ✅ healthcheck 結果可重建 | ⚠️ A/C 啟動 evict 缺 audit log + operator 看不到 |
| #9 災難保護 | ✅ EXIT-FEATURES-FIX A1 已是雙軌 | A/C 引入第三軌反增複雜 |
| §四 5 項 live 硬邊界 | ✅ 全不觸碰 | ✅ 全不觸碰 |
| DOC-08 §12 #4 風控降級 | n/a | n/a |

**總評**：Option B 完全合規 **A 級**；A/C 在原則 #5/#8 有違反風險 → 即使加 cross-env env-guard 也是 **B-/C 級**。

---

## §10 沒做的事（E1/E2 領域）

- ❌ 沒寫 healthcheck [19] 實作代碼（純設計，prompt template 給 E1）
- ❌ 沒跑 cargo test / pytest
- ❌ 沒派 sub-agent（純 PA design 主 agent 串行讀+寫）
- ❌ 沒驗證 EXIT-FEATURES-FIX A1/A3 在 runtime 是否生效（屬 MIT/E4）
- ❌ 沒擴範圍到 strategy team dust handling（隔壁 ticket）
- ❌ 沒深查 apply_fill 反向 close 路徑 entry_notional reset 細節（屬本 audit follow-up）

---

## §11 教訓備忘

1. **「為何 X 重啟後沒清掉 Y」要先驗 X 是否重建 Y**：MIT §6 follow-up #1 預設 restore 路徑會重建倉位，但實際 `restore_from_db` 只還原 counter；倉位來自 `import_positions(seed_positions)`。**未來任何 restore 相關 audit 第一句先確認 SSOT 是 DB row 還是 in-memory**
2. **fix-by-skip vs fix-by-evict 的 cross-env 取捨**：fix-by-skip（fast_track Gate 1 skip ReduceToHalf）是純消費端防護、跨 env 0 risk；fix-by-evict（startup mutate state）是純生產端清理、跨 env 風險高。**未來 dust/orphan 類問題優先選 fix-by-skip**
3. **healthcheck 補 observability 是低風險高 ROI 模式**：當 production fix 已落地（fast_track Gate 1）但 silent（不寫 metric）→ 加 healthcheck SQL 量化是「無 mutation 風險的監控 patch」，比再開新 mutation path 安全很多
4. **PA design 報告必含 cross-env 安全性矩陣**：本 audit §6.1 表格清楚展示 paper/demo/live 三環境風險差異 → operator 一眼判斷；未來有 cross-env hard requirement 的 design audit 必含此格式

---

## §12 報告索引追加（PA memory 用）

| 日期 | 報告類型 | 文件位置 |
|---|---|---|
| 2026-04-26 | PAPER-STATE-DUST-RESTORE-AUDIT design audit（推 Option B + healthcheck [19]）| workspace/reports/2026-04-26--paper_state_dust_restore_audit.md |

---

**PA 簽核**：findings sound + 3 option 全 evaluated / cross-env safety 矩陣完整 / Option B 證據鏈強 / Option A/C 拒絕理由具體 / E1 prompt + healthcheck SQL 可直接 copy-paste

**PM 接收**：派 E1 加 healthcheck [19]（~1h），不啟動 paper_state 業務碼任何改動；TODO.md PAPER-STATE-DUST-RESTORE-AUDIT 改寫為 PAPER-STATE-DUST-INVENTORY-MONITOR；G2-strategy-dust-cleanup follow-up 列入 backlog（屬 strategy team）

---

## §13 Deviation Log（amend 歷史）

> **目的**：紀錄此 RFC 落地後相對原 spec 的偏差，避免未來 reader 誤以為實裝錯。RFC §1-§6 + §8-§12 結論不變；只 §7.x 的 SQL 載體已 amend 為 E1 落地版本。

| 日期 | Commit | Section | Deviation | E2 評語 | Source-of-truth |
|---|---|---|---|---|---|
| 2026-04-26 | E1 `8241133`（PAPER-STATE-DUST-INVENTORY-MONITOR healthcheck [21]）| §7.1 prompt SQL · §7.2 spec SQL | (A) `COUNT(DISTINCT symbol)` 加 `FILTER (WHERE realized_pnl = 0)`（PA 原 spec unfiltered） · (B) drop `partial_reduce_real_count` column | **Improvement not regression** — (A) 更精確 dust spiral fan-out signal、(B) drop 多餘 column 簡化邏輯（per E2 Tier 7 batch review T7-LOW-1 `b6dbc24`）| Linux production cron **2026-04-26 16:09 UTC LIVE PASS** `dust_spiral_count=0 — Gate 1 USD floor suppressing as designed` 確認 |
| 2026-04-26 | T7-FUP-DUST-SQL-DEVIATION-DOC（本 amend）| §7.1 + §7.2 | 同步 RFC 為 SSOT；§7.2 加雙語 deviation 解釋；§7.1 prompt SQL block 加 NOTE 指向 §13 + §7.2 | n/a（doc-only amend）| 本 commit |

**為何不重寫 §7.x**：保留原 PA design 推理過程（Option A/B/C 對比、cross-env safety 矩陣、Reject A/C 理由）作為 design-time decision artifact；§7 SQL 載體更新到落地版即可避免 production-vs-doc drift，且 verdict thresholds 完全不變（0=PASS / 1≤count≤10 AND distinct<3=WARN / >10 OR distinct≥3=FAIL）。

**Slot 編號修正**：§7.1-§7.4 寫 [19] 為 design-time placeholder；上線時 [19] observer / [20] h_state_gateway 已被佔，E1 正確找下個空 slot 落地為 **[21]**（per PM Tier 7 sign-off `13412db` Track 2 §3.4）。本 amend 在 §7.2 開頭已加 inline note；§7.1 / §7.3 / §7.4 文本中的 [19] 視為 design 階段的編號意圖，runtime SSOT 是 [21]。
