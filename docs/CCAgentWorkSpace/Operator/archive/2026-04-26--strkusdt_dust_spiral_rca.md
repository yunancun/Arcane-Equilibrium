# PA — STRKUSDT dust spiral + Demo silent RCA + fix 形狀（read-only）

採集時間：2026-04-26 18:30 CEST · Linux HEAD `b6dbc24` · 仍運行 binary 04:28 build (PID 2033577)

---

## §1 現場事實清單（時間軸 + DB + log 證據）

### 1.1 Binary / commit 時序（關鍵）

| 時點（CEST） | 事件 | 證據 |
|---|---|---|
| 04-26 04:28:56 | Engine PID 2033577 啟動，binary mtime 4月 26 04:29 | `ps lstart=04:28:56 2026` + `stat openclaw-engine` |
| 04-26 04:28:57 | Startup REST 抓到 `STRKUSDT Buy size=0.1 avg_price=0.04261` | engine.log L? `startup position captured / kind=demo symbol=STRKUSDT side=Buy size=0.1 avg_price=0.04261` |
| 04-26 04:28:58.906 | P0-6 triage 把 STRKUSDT 標記為 `dust_frozen` (qty=0.1, est_notional=0.004261, min_notional=5.0) | `DUST-EVICTION-GAP-1: bybit_sync position frozen ... operator must clear manually on Bybit GUI` |
| 04-26 06:00:00 | Funding payment WS fill: STRKUSDT Buy 0.1 @ 0.04019, **`exchange fill has no matching pending order`** → 不調 apply_fill | engine.log `WS fill / engine=demo` + warn 「無匹配 pending order」 |
| **04-26 07:37:59** | **Spiral 第 1 次 reduce_half: qty=0.05 @ 0.04261**（trigger `FAST_TRACK ReduceToHalf risk_level=Defensive held_drop_symbol=BTCUSDT held_drop_pct=8.9% sigma=1.55`） | `trading.fills` first row + engine.log `FAST_TRACK ReduceToHalf` |
| 04-26 07:37:59 - 08:13:59 | **37 次** halve, qty `0.05 → 0.025 → ... → 7.27e-13` (60s 間距 cooldown 觸發) | DB: 37 rows, COUNT=37 |
| 04-26 08:13:59 | **第 37 次 spiral end**：qty=7.27e-13 → reduce_position 觸發 `pos.qty < 1e-12` evict（fill_engine.rs:377-379），STRKUSDT 從 paper_state 移除 | demo_state.json L8-19 只剩 BTCUSDT |
| 04-26 08:13:59 → 18:30 (~10h15) | **demo 0 fills** 任何 strategy 都沒新單；engine **整路徑 alive** | `SELECT COUNT(*) FROM trading.fills WHERE engine_mode='demo' AND ts > '2026-04-26 06:13:59+00'` = **1**（08:13:59 那筆 spiral last 一筆） |
| 04-26 15:48:14 | Commit `af48ee1` "EXIT-FEATURES-WRITER-BUG-1-FIX cohesive 1+2 RCA repair" landed (但 binary **未重啟**) | git log + binary mtime 04:29 不變 |
| 04-26 18:18+ | engine.log 仍持續 print BTCUSDT MICRO-PROFIT-FIX-1 ratio gate skip → engine alive | engine.log tail |

### 1.2 BTCUSDT 對比（同一 binary、同一 ratio gate、結果相反）

```
07:37:59 起 BTCUSDT 同樣被 ReduceToHalf 觸發
07:40:59 起 BTCUSDT 被 MICRO-PROFIT-FIX-1: skip ReduceToHalf — notional below floor
  current_notional=9.74 floor_notional=19.02 entry_notional=76.08 ratio=0.25
（持續到 18:23+，gate 對 BTCUSDT 工作正常）
```

### 1.3 STRKUSDT 為何 ratio gate 失效（核心 RCA-A）

- `step_0_fast_track.rs` 既有 ratio gate 條件：`if ft_min_notional_ratio > 0.0 && *entry_notional > 0.0`
- **STRKUSDT entry_notional 在 ratio gate 觀感裡 = 0** → 條件 `> 0.0` 為 false → ratio gate **完全跳過 check** → spiral 通行
- 觀察證據：`grep STRKUSDT engine.log | grep MICRO-PROFIT-FIX-1` = **0 條**（vs BTCUSDT 18 小時持續 print）

**為何 STRKUSDT 的 entry_notional 為 0？**

未在運行 binary 中執行的修復（commit `af48ee1`）`bootstrap.rs:308 migrate_legacy_entry_notional()` defence-in-depth 才會在 import_positions 之後 idempotent backfill `entry_notional <= 0.0` 的 entries。MIT audit `2026-04-26--exit_features_writer_bug_audit.md` §6 第 1 條「**Engine 重啟為何沒清掉 0.1 dust** — paper_state::restore_from_db 讀取 dust qty 但 entry_notional = 0；查 dust handling 邏輯（PA 派 E1 audit）」直接點明這條 path 仍是 hypothesis。最 plausible 解釋：`import_positions` line 67 `entry_notional: qty * entry_price` 可能因某 Bybit REST 路徑回 `avg_price=0`（line 48 guard 並不 reject 因 `avg_price > 0` 是 entry_price > 0 的別名，guard 通），但 log 顯示 avg_price=0.04261。

**最終實證**：`grep STRKUSDT engine.log | grep MICRO-PROFIT-FIX-1` 0 條 → ratio gate 條件 false → 唯一可能是 `entry_notional == 0`。對比 BTCUSDT 18 小時 ratio gate 持續 print → BTCUSDT entry_notional=76.08 沒掉到 0。STRKUSDT entry_notional 為 0 但 BTCUSDT 為 76.08 的差異**結構上**只能是 import_positions 入 paper_state 的某條代碼路徑為 STRKUSDT 設了 0、為 BTCUSDT 設了 76.08。具體是哪條路徑現有 binary 中無 log 不可確認；**MIT audit follow-up §6.1 已 acknowledge 為未完成 audit**。但下面 RCA-A 的修法（Gate 1 USD floor + A3 backfill）對「entry_notional 為何為 0」的具體 path 不依賴 — Gate 1 fail-closed 永遠生效。

---

## §2 代碼路徑對比表（path A vs path B）

| 元素 | Path（同一條，無 fork） | file:line |
|---|---|---|
| 上游觸發 | `evaluate_fast_track` 算出 `FastTrackAction::ReduceToHalf` | `rust/openclaw_engine/src/fast_track.rs` |
| 進 step_0 | `TickPipeline::on_tick_step_0_fast_track` | `tick_pipeline/on_tick/step_0_fast_track.rs:45` |
| ReduceToHalf 分支 | Line 253 `if ft_action == ReduceToHalf` | step_0_fast_track.rs:253 |
| floor gate Gate 2 ratio (本檔已存在的 MICRO-PROFIT-FIX-1) | Line 391 `if ft_min_notional_ratio > 0.0 && *entry_notional > 0.0` | step_0_fast_track.rs:391-405 |
| floor gate Gate 1 USD (commit `af48ee1` 加，**binary 未含**) | Line 374 `if ft_dust_qty_floor_usd > 0.0 && current_notional < ft_dust_qty_floor_usd` | step_0_fast_track.rs:374-384 |
| 本地 reduce | `paper_state.reduce_position(sym, half_qty, close_price)` | step_0_fast_track.rs:446 → `paper_state/fill_engine.rs:366` |
| **emit_close_fill**（寫 trading.fills + 條件寫 EF） | `self.emit_close_fill(sym, *is_long, half_qty, close_price, ts_ms, pnl, "risk_close:fast_track_reduce_half", &ectx, snap)` | step_0_fast_track.rs:447-457 → 定義 `pipeline_helpers.rs:118` |
| **execute_position_close**（dispatch 到交易所） | `self.execute_position_close(sym, *is_long, half_qty, event, is_primary, "risk_close:fast_track_reduce_half")` | step_0_fast_track.rs:462-469 → 定義 `commands.rs:593` |
| dispatch reject | `event_consumer::dispatch.rs:386-396 if est_notional < spec.min_notional → continue;`（無補償，paper_state 已 reduce） | dispatch.rs:374-398 |

**關鍵架構釐清**：reduce_half 並非「另一條路徑」—— 它**就是** step_0_fast_track 的 ReduceToHalf 分支。傳給 emit_close_fill / execute_position_close 的 `trigger_tag = "risk_close:fast_track_reduce_half"` 字串就是兩個下游 sink（trading.fills + 交易所 dispatch）看到的 strategy_name。所以「為何走另一條 path」這個假設**錯誤**：BTCUSDT 與 STRKUSDT 走完全相同的 step_0_fast_track ReduceToHalf 分支，floor gate 也是同一個。差異是 **STRKUSDT entry_notional=0 觸發 ratio gate 條件 fail-open**，BTCUSDT entry_notional=76.08 觸發 ratio gate 正常 skip。

---

## §3 Reduce_half 切半邏輯解剖

### 3.1 切半的核心邏輯
- 位置：`step_0_fast_track.rs:428` `let half_qty = qty / 2.0;`
- 寫死 `0.5` 沒有 ratio 配置可調
- 觸發條件：每 60s 至少一次（FT_REDUCE_COOLDOWN_MS=60000）—— 為什麼 spiral 35 次 60s 間距而第 1/2 次是同 60s？看 `effective_cooldown_ms=60000` 在 log 中所有 trigger 都一致，drop_scoped=false（即非 sigma-scoped 路徑）。每 60s 一次精確等於 cooldown。

### 3.2 終止條件（多層 + 都失效於 STRKUSDT）

| 條件 | 邏輯位置 | STRKUSDT spiral 期間是否生效 |
|---|---|---|
| Gate 1 USD floor | step_0_fast_track.rs:374（`af48ee1` 才加） | **未生效**（binary 未含此 commit） |
| Gate 2 ratio gate | step_0_fast_track.rs:391 (`> 0.0` 條件) | **未生效**（entry_notional = 0 → 跳 if 主體） |
| `pos.qty < 1e-12` evict | `fill_engine.rs:377-379` | **僅最後一次生效**（37 reduces 後 7.27e-13/2 ≈ 3.6e-13 < 1e-12 evict） |
| `effective_cooldown_ms` per-symbol | `step_0_fast_track.rs:323` `ft_reduce_cooldown_expired` | 60s 間距，每分鐘 1 次合法 trigger |
| Bybit `min_notional=5.0` exchange-side guard | `dispatch.rs:386` | **生效**：dispatch 跳過 → 不真正下單到 Bybit；但 paper_state 已 reduce_position（雙寫不對賬） |
| Risk level transition (Defensive → Cautious → Normal) clear | step_0_fast_track.rs:233-241（Normal 才清空 ft_reduced_symbols） | 整 spiral 期 Defensive 沒退降 → guard 清不掉 → 60s 後再 trigger |

### 3.3 Bybit 雙寫不對賬

```
emit_close_fill (line 447) → trading_writer INSERT trading.fills 寫成功
execute_position_close (line 462) → mpsc → event_consumer::dispatch.rs:386 reject
                                  → continue;（無回滾，無 paper_state.unreduce）
```

trading.fills 37 條成功寫入；Bybit demo endpoint 0 條成交（dispatch reject 全部）。Reconciler 對賬時應發現 paper_state STRKUSDT 從 0.1 → 0（37 步）但 Bybit demo STRKUSDT 仍 0.1，理論應觸發 `EX-04 對賬差異 → 自動降級`，但實際沒發生。MIT audit §6.4 提到此 gap 但 P2 backlog。

### 3.4 為何 dispatch reject 仍寫 fill 表？

依 `emit_close_fill`（pipeline_helpers.rs:118）寫入時機在 `execute_position_close` 之前（step_0 line 447 vs 462）—— 寫 fill 表為「**本地 paper_state 已 reduce 的真實事實**」，dispatch 是另一條 best-effort 嘗試。即使 dispatch reject paper_state 仍從 0.1 → 0.05 → 0.025 → ... 真的減半，因此「寫 fill 表」是合理的（記錄本地 ledger 變動），不寫反而會掉帳本。但**這需要對賬機制兜底，否則 paper_state ↔ Bybit drift**。當前設計依賴 reconciler 5min 輪詢補正 — `b1_dust_reconciler` 在哪？grep 不到完整路徑，這是另一個 follow-up。

---

## §4 08:13 後 demo silent 因果判斷

### 4.1 假設 A/B/C 對照 + Evidence

| 假設 | 描述 | 驗證 |
|---|---|---|
| **A** | STRKUSDT dust 7e-13 持倉鎖死全 engine | **REJECTED** |
| **B** | 08:13 後 silent 是獨立原因（fresh-boot wedged / 別 cooldown） | **REJECTED** |
| **C** | reduce_half 持續 spawn intent，Bybit reject 推 engine 進降級模式 | **REJECTED** |
| **D（補）** | **STRKUSDT spiral 結束 + BTCUSDT entry_notional ratio gate 永久擋 ReduceToHalf + 沒有其他 strategy 在新開倉** | ✅ **CONFIRMED** |

### 4.2 對 A 的反證
- demo_state.json STRKUSDT 已從 positions 移除（08:13:59 last reduce 把 qty 降到 7.27e-13/2 ≈ 3.6e-13 < 1e-12 → fill_engine.rs:379 `positions_remove`）
- engine.log 18:18+ 仍有 BTCUSDT MICRO-PROFIT-FIX-1 print → on_tick 仍在 firing，無 global lock

### 4.3 對 B 的反證
- engine WS path 04:00 / 12:00 / 16:00 三次收到 STRKUSDT funding payment WS fill → engine.log 仍記錄 `WS fill / exchange fill received`
- 18:18+ 仍 print BTCUSDT MICRO-PROFIT-FIX-1 → fast_track step_0 仍每 tick 跑

### 4.4 對 C 的反證
- 06:13:59 之後 0 條 `FAST_TRACK ReduceToHalf` log 觸發
- 06:13:59 之後 0 條 `order dispatch skipped` log → spiral 結束後 engine 不再向 Bybit dispatch
- Bybit demo 仍接收 funding fills (04:00/12:00/16:00) → 連線正常

### 4.5 對 D 的證實（spiral 結束 + 新單缺席）
- BTCUSDT 持有量 0.000125（≈9.75 USD）entry_notional=76.08 持續被 MICRO-PROFIT-FIX-1 ratio gate 擋（floor=19.02，current=9.75 < 19.02 永遠 skip）
- 沒有 strategy 在 demo 上新開倉 — 對應 ma_crossover/grid/funding_arb 全 0 entry。**為何 0 entries 是另一個 question**（不是 spiral 因果）— 看 risk_level 是否仍 Defensive。06:13:59 後沒再 ReduceToHalf trigger → risk_level 應已退到 Normal 或 Cautious，但 ft_pause_new_entries 不再 active，理論可開新倉。
- 但實際 0 fills → 這是「策略選擇 0 開倉」（market regime / signal 沒 fire / 風控其他層擋住）而非 engine 故障

### 4.6 結論

**08:13 後 demo silent 不是 STRKUSDT 引起的次生災害**，而是 spiral 結束後 engine 進入「**只剩 BTCUSDT 1 個 stranded 倉位 + ma_crossover entry_notional 76.08 vs current 9.75 (dust 邊界但仍非 dust)**」的穩態。BTCUSDT 是 ma_crossover ownership（owner_strategy=ma_crossover），但 ma_crossover 沒在發 strategy_close 信號（log 中 `step_4_5_dispatch` 也沒 STRKUSDT/BTCUSDT 平倉信號），所以 BTCUSDT 永遠掛著。新開倉路徑為何也 0 — **獨立問題**（未在本 RCA 範圍）。

---

## §5 Fix design（不寫 patch，只設計）

### 5.1 Fix 已存在於 commit `af48ee1`（15:48）但 binary 未含

Operator 已在 15:48 commit `af48ee1` 落地完整 cohesive fix，包含：
- **A1 layered Gate 1+2** in step_0_fast_track.rs:328-408 (Gate 1 USD floor `current_notional < ft_dust_qty_floor_usd` 即 skip，**所有 branch active 包括 entry_notional==0 legacy path**)
- **A3 defence-in-depth** `migrate_legacy_entry_notional()` call in event_consumer/bootstrap.rs:308 after import_positions（idempotent backfill `entry_notional <= 0.0` 倉位）
- **schema** `RiskConfig.limits.ft_dust_qty_floor_usd: f64` (default 1.0 USD, range [0, 100_000])
- **B1** `is_partial_reduce_tag()` helper + emit_close_fill 路徑改 partial reduce skip EF emit (RCA-B)

**現有運行 binary 04:28 build 沒有此 fix，需要 `--rebuild` 部署**。

### 5.2 為什麼這條路（Gate 1 USD floor）是對的

| 維度 | Gate 1 USD floor (操作員選擇) | 替代 A：dust eviction 路徑 |
|---|---|---|
| 簡單 | ✅ 一個 if + log skip | ❌ 需要重組 reduce_half 流程 |
| Fail-closed | ✅ 不 reduce, fail-closed 留 dust | ✅ 平倉但需保證 Bybit 拒 reject 處理 |
| Hot-reloadable | ✅ TOML + IPC `patch_risk_config` | ❌ Schema 改動需 rebuild |
| Regression 風險 | 低（real position 名義 ≥5 USD min）| 高（誤殺 |Bybit 邊界倉位）|
| 對既有 ratio gate semantics 衝擊 | 並列 Gate 1 + Gate 2，semantics 互補 | 完全替代 ratio gate |

### 5.3 Hot-reloadable IPC schema 擴展（已 done in `af48ee1`）

| Field | Default | Range | 路徑 |
|---|---|---|---|
| `RiskConfig.limits.ft_dust_qty_floor_usd` | 1.0 | [0, 100_000] | `risk_config.rs:395 ft_dust_qty_floor_usd` |
| `RiskConfig.limits.ft_min_notional_ratio_of_entry` | 0.25 | [0, 1] | `risk_config.rs:375` (既存) |

### 5.4 Regression 風險分析（給未來 rollout 參考）

**會被擋**：
- 真實 reduce_half 對 Bybit 邊界小幣（current_notional < 1.0 USD）—— 但這類倉位 Bybit 本身就會 reject dispatch，擋住 = no-op + 留 dust 待 operator 清理（與既有 DUST-EVICTION-GAP-1 frozen 行為一致）

**不會被擋**：
- BTCUSDT 9.75 USD（vs 1.0 floor）—— 仍會 trigger reduce_half；但 ratio gate 76.08 × 0.25 = 19.02 floor 擋住（這是已生效的既有 gate）。所以 BTCUSDT 雙重保護順序：先 Gate 1 (1.0) 不擋 → Gate 2 (19.02) 擋 → skip

**邊界 case**：current_notional ∈ [1.0, 19.02] AND entry_notional ∈ [0, 4.0] → Gate 1 不擋 + Gate 2 entry_notional <= 0.0 之外不擋（ratio = 0.25 × entry, 若 entry=4.0, floor=1.0；current 1.0 = floor → 不擋）。罕見但可能存在 — 屬於 expected behavior（這類倉位仍正常 halve）。

### 5.5 Hotfix 範圍

**單一 commit `af48ee1` 已修完**（cohesive 1+2 cohesion）：
- 10 files / +755 / −19
- 12+5 = 17 new tests
- 加 `83456e5` regression-guard follow-up（1 file / +18 / −13）

**Hotfix 部署 = 純 `restart_all.sh --rebuild`**（無 schema migration、無 DB write、無 IPC service breakage）。

### 5.6 ★ 派發給 E1 的子任務（已不需派發 — fix 已 done）

> 通知 PM：本 RCA 的修復**已 in-tree**（`af48ee1` + `83456e5`），唯一動作 = **operator 觸發 `restart_all.sh --rebuild`** 把 04:28 binary 升級。

但若 PM 仍需 follow-up E1 工作，下面 3 子任務 **MIT audit §6 acknowledged but not yet done**：

| E1 子任務 | 範圍 | 工時 |
|---|---|---|
| **F1** 「STRKUSDT entry_notional=0 為何發生」深查 audit | grep import_positions / paper_state restore 路徑 + 驗證實際 binary 運行時 path → 確認是 Bybit REST 回 `avg_price=0` 路徑 vs 別的；不修代碼，只寫 audit | 0.5d |
| **F2** Reconciler 對 spiral 期間 paper_state ↔ Bybit drift 的補正路徑驗證 | 看 `EX-04 對賬` 為何 spiral 中 37 次 paper_state qty drop / Bybit 仍 0.1 沒被偵測 | 0.5d |
| **F3** Healthcheck [3] `exit_features_writer` 自動恢復觀察 | F1+F2 完 + binary `--rebuild` 後 24h 自動 PASS（37 noise rows age out 期）；補一條 `[19]` healthcheck dust spiral 偵測（MIT audit §6.6） | 0.5d |

3 子任務**全部 isolation 否**（純 audit + 1 個小 healthcheck check）。**並行排 1 wave 可完**（單 E1 串行 1.5d）。

### 5.7 PA 強建議（給 PM）

1. **立即執行**：operator `restart_all.sh --rebuild` 部署 `af48ee1` binary（fix 待轉成 runtime live）
2. **自動 ack**：commit `83456e5` regression-guard（已 in-tree）
3. **被動觀察 24h**：Healthcheck `[3] exit_features_writer` 24h 期內 noise rows age out 後自動 PASS（無需 backfill 歷史 noise；PAPER-STATE-DUST-RESTORE-AUDIT P2 ticket 處理歷史）
4. **F1-F3 留在 backlog**（P2，不阻塞 Live）

---

## §6 不確定之處 + 建議下一步

### 6.1 不確定（事實限制）

1. **STRKUSDT entry_notional 為何 = 0 的具體 path**：log 顯示 startup avg_price=0.04261 應有 entry_notional=0.004261。但 ratio gate 0 條 print 證明 entry_notional == 0。可能 path：(a) `import_positions` 後某條 callback path overwrite 為 0（線索：startup ts 02:28:57.480 → P0-6 dust_frozen ts 02:28:58.906 期間 0.5s 有什麼操作？）(b) Bybit REST avg_price=0 的某個 condition（log 顯示 0.04261，但 binary 內部 deserialise 可能不同）— 不在 log scope 內無法定論。MIT audit §6.1 已 acknowledge。
2. **08:13 後其他 strategy 為何 0 entries**：本 RCA 不深入；但確認**不是 STRKUSDT spiral 引起的次生災害**。可能 root cause：market regime / signal threshold / cost_gate / strategy params drift — 屬另一條 audit。
3. **Funding payment WS fills 路徑**：04:00/12:00/16:00 三次 WS fill 走 `no matching pending order` warn 不調 apply_fill —— 即不影響 paper_state。這對 Bybit 端 STRKUSDT qty 管理意義？不確定。Bybit 端可能在 spiral 期間因 funding 自動有 +0.1 qty 加倉，但 paper_state 完全不知 → drift 加劇。這是 reconciler 層的問題。

### 6.2 建議下一步

| Priority | Action | Owner |
|---|---|---|
| P0 立即 | Operator `restart_all.sh --rebuild` 部署 `af48ee1` 至 runtime | Operator |
| P0 6h 後 | 驗證 healthcheck [3] PASS（24h age-out window 內）| CC + PM |
| P1 一週 | E1 F1: STRKUSDT entry_notional=0 path 深查 audit | E1 |
| P1 一週 | E1 F2: Reconciler EX-04 對 spiral 期間 paper_state ↔ Bybit drift 補正 path 驗證 | E1 |
| P2 backlog | E1 F3: 加 `[19]` healthcheck check fast_track dust spiral 偵測 | E1 |
| P2 backlog | MIT/E1 ML-TRAINING-DATA-HYGIENE-1: 全期 EF table 中 dust spiral noise 量化 + 補回填 SQL | MIT + E1 |
| P2 backlog | E1 「08:13 後 demo strategy 0 entries」獨立 audit（與 STRKUSDT spiral 解耦） | E1 |

---

## §7 16 根原則對照

| 原則 | 對 spiral 的適用 | 是否被觸碰 |
|---|---|---|
| #1 單一寫入口 | emit_close_fill + execute_position_close 雙 sink 但都走唯一 IntentProcessor | ✅ 沒違反 |
| #4 策略不繞過風控 | fast_track 是風控（risk-driven close），不繞過 | ✅ 沒違反 |
| #5 生存 > 利潤 | spiral 邏輯本身是「fast_track 想救倉」但 fail-open 反而 noise，**Gate 1 USD floor 是更嚴格的生存保護**（對 dust）| ✅ Fix 強化 |
| #6 失敗默認收縮 | ratio gate 對 entry_notional=0 fail-**OPEN** 違反此原則 | ❌ Pre-fix 違反；af48ee1 修正 |
| #8 交易可解釋 | trading.fills 37 條 + entry_context_id NULL 可重建 | ✅ 沒違反 |
| #11 Agent 最大自主 | dust 倉位的 evict 策略仍由 Agent / fast_track 自主決定，operator 只設 floor | ✅ 沒違反 |

**結論**：af48ee1 fix 修補 #6 fail-closed，其他 15 條無觸碰。

---

PA DESIGN DONE: report path: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--strkusdt_dust_spiral_rca.md
