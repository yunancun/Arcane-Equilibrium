# P2-ENTRY-CLOSE-MAKER-REAL-FILL-FIX 分析報告

**Auditor**: FA (Functional Auditor)
**Date**: 2026-05-20
**Scope**: entry-close maker path 的 limit placement / order lifetime / cancel-fallback sequencing 之 evidence-based 改善建議
**Constraint**: Phase 1b 14d observation 中（reset @2026-05-18 13:50 UTC，至 ~2026-06-01 UTC），**禁動 runtime / 禁寫 patch**；只出源碼分析 + evidence inventory
**SoT 對照**: `CLAUDE.md` §二 + §四 / `SPECIFICATION_REGISTER.md` v2026-05-15 / Phase 1b spec v1.3 / V094 audit schema / 2026-05-18 E2 RCA / 2026-05-18 PA calibration report / v55 archive entry-path RCA

---

## §1 當前 source 行為（細部追蹤）

### §1.1 close-maker 觸發決策樹

**入口檔**: `srv/rust/openclaw_engine/src/tick_pipeline/commands.rs:109-154`

```
close_order_dispatch_shape(symbol, position_is_long, dispatch_price, event, trigger_tag)
  ├─ if !use_maker_close → CloseOrderDispatchShape::market()        [Line 117]
  ├─ if close_maker_price_policy(trigger_tag) is None → market()     [Line 121]
  └─ compute_close_limit_price(...) → maker() or market()            [Line 145]
```

`use_maker_close` 是 ArcSwap runtime flag（`commands.rs:91-103`），cold-default false；只允許 Demo pipeline 啟用（Demo guard line 92-100）。當前 demo TOML `use_maker_close=true`、live `=false`、paper `=false`。

### §1.2 trigger_tag 來源（兩條獨立路徑）

**Path A — strategy-driven close（`oc_risk_*` is_primary=true）**:
- 來源檔 `srv/rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs:1606-1644`
- 流程: 策略發 `StrategyAction::Close { symbol, confidence, reason }`（無 limit_price / time_in_force）
- tag 格式: `format!("strategy_close:{reason}")` line 1615/1635/1676/1699
- 已知 reason: `grid_close_short` / `grid_close_long` / `bb_mean_revert` / `ma_reverse_cross` / `bw_squeeze` / `pctb_revert`

**Path B — risk-driven close（`oc_risk_*` is_primary=true）**:
- 來源檔 `srv/rust/openclaw_engine/src/tick_pipeline/on_tick/step_6_risk_checks.rs:275-431`
- tag 格式: `build_risk_close_tag(reason)` → `"risk_close:{reason}"`（已防 double-prefix line 263-275）
- 已知 reason: `HARD STOP / TRAILING STOP / TIME STOP / DYNAMIC STOP / TAKE PROFIT / COST EDGE / DAILY LOSS / DRAWDOWN / CONSECUTIVE LOSS / fast_track_* / halt_session_* / phys_lock_gate4_giveback / phys_lock_gate4_stale_roc_neg`

**Path C — IPC/operator override close（`oc_ipc_close_*`）**:
- `ipc_close_all` (`commands.rs:1240-1359`) / `ipc_close_symbol` (`commands.rs:1404+`) / `close_position_at_symbol_market`
- tag 格式: `"ipc_close_all"` / `"ipc_close_symbol"`（line 1287, 1471 vicinity）

### §1.3 limit placement 演算法（單一 helper，4 維輸入）

**核心檔**: `srv/rust/openclaw_engine/src/strategies/common/maker_price.rs:164-211 compute_close_limit_price`

```
1. spread guard: if spread_bps > CLOSE_MAKER_SPREAD_GUARD_BPS (50.0) → None (跳 market)
2. crossed/locked book: ask <= bid → None (line 174-186)
3. 否則: compute_post_only_price(!position_is_long, inputs, offset_bps, buffer_ticks, ...)
```

**positional inversion**: line 164-211 — close 是反向交易，`!position_is_long` 傳入 compute_post_only_price，所以：
- 平多倉（position_is_long=true）→ sell limit @ `best_ask + buffer_ticks × tick_size`
- 平空倉（position_is_long=false）→ buy limit @ `best_bid - buffer_ticks × tick_size`

**價格嚴格被動**:
- BBO 雙側有 → `bid - buffer×tick`（買）/ `ask + buffer×tick`（賣）（line 287-317）
- 單側報價 → `cross_buffer = (buffer_ticks==0 ? tick_size : buffer)`（line 286, 290, 305）— **buffer=0 仍至少 1 tick 退讓**
- 無 BBO / tick_size 缺 → None → strict skip 走 market fallback（line 245-262）

### §1.4 per-reason CloseMakerPricePolicy（calibrated 2026-05-18）

**檔**: `maker_price.rs:85-111 close_maker_price_policy`

| reason 群 | buffer_ticks | offset_bps | timeout_ms |
|---|---|---|---|
| grid_close_short / grid_close_long / bb_mean_revert / ma_reverse_cross / bw_squeeze / pctb_revert | 0 | 0.5 | **90_000**（calibrated 2026-05-18 from 30s; G-AB-01-C90 winner）|
| phys_lock_gate4_giveback | 1 | 0.5 | 15_000 |
| phys_lock_gate4_stale_roc_neg | 1 | 0.5 | 10_000 |
| 其他（HARD/TRAILING/TIME/STOP/TAKE PROFIT/COST EDGE/halt/ipc/...）| (不適用，None → market) | - | - |

**「strategy_close:*」 / 「risk_close:*」 envelope 剝除**: `canonical_close_maker_reason()` 用 loop 反覆 strip prefix（line 68-81），可處理巢套；無 prefix 視為裸 reason。

### §1.5 order lifetime / TTL / cancel sequencing（pending sweep state machine）

**檔**: `srv/rust/openclaw_engine/src/event_consumer/pending_sweep.rs` + `loop_handlers.rs:741-895`

state diagram（同檔 line 41-54）:
```
Submitted → Working (Bybit accept as PostOnly resting)
  │
  ├─ elapsed < maker_timeout_ms → Keep
  ├─ elapsed >= maker_timeout_ms (且 cancel_requested_ts=None)
  │    → MakerTimeoutCancel
  │      → tokio::spawn(cancel_resting_maker_order)
  │      → 標記 cancel_requested_ts_ms=now（pending_sweep.rs:75-77，loop_handlers.rs:870-874）
  │
  ├─ cancel_requested_ts != None
  │    ├─ elapsed_since_cancel < grace → Keep
  │    └─ elapsed_since_cancel >= grace → MakerCancelGraceExpired
  │
  └─ WS event-driven cleanup（並行 race）:
       - OrderUpdate filled → emit_confirmed_fill（含 close_maker_audit details）
       - OrderUpdate Cancelled/Rejected → tracker remove
       - dispatch_failed (REST 提交失敗) → dispatch_close_maker_fallback_from_pending
```

**grace 常數**（pending_sweep.rs:21-34）:
- `MAKER_CANCEL_ACK_GRACE_MS = 60_000`（entry maker；長 grace 以匹配 race fill）
- `CLOSE_MAKER_CANCEL_ACK_GRACE_MS = 2_000`（close maker；短 grace 因 close 是 exposure 降低 intent，不容拖延）
- `PARTIAL_FILL_REMAINDER_GRACE_MS = 5_000`（entry partial fill 後切短 timeout；明示 skip close `tighten_postonly_entry_after_partial:120-137`）

**sweep 頻率**: 每 `pending_timeout`（loop_handlers.rs:755）；當前部署 5_000ms（v55 「5s soft warn / 60s hard remove」legacy）。

### §1.6 cancel-fallback sequencing（10 個 fallback reason）

**檔**: `srv/rust/openclaw_engine/src/strategies/maker_rejection.rs:107-145 + 219-258`

```
CloseMakerFallbackEvent → CloseMakerFallbackReason 映射表（maker_rejection.rs:222-258）

Timeout                       → TimeoutTaker
CancelGraceExpired            → CancelGraceExpired
PostOnlyReject (EC_PostOnly..)→ PostOnlyReject
TooManyPendingPerSymbol       → RateLimitBackoffPerSymbol (cooldown=true, per-symbol)
TooManyPendingGlobal          → RateLimitPauseGlobal (cooldown=true, global pause 300s)
EngineShutdown                → EngineShutdownSafety
UnknownReject (EC_Others 等)  → AckLost
FastEscalateSafetyUpgrade     → FastEscalateSafetyUpgrade
                  (額外: NotAttemptedSafetyPath / FallbackToTakerMandatory)
```

**fallback enforcement invariant**: `requires_market_fallback(self)` 對所有 reason 除 `NotAttemptedSafetyPath` 都回 true（line 148-150）。**即 close 一旦被啟動 maker 路徑後，幾乎沒有「靜默放棄 close」的合法分支**。

**fallback dispatch**: `loop_handlers.rs:94-168 dispatch_close_maker_fallback_from_pending`
- 條件: `fallback_reason.requires_market_fallback() && po.is_close && po.time_in_force == PostOnly && audit 仍未含 fallback_reason && position 仍 open && cum_filled < 99.9%`（line 102-136）
- 重複 fallback 抑制: `state.close_maker_fallback_dispatched: HashSet<order_link_id>`（line 137-150）
- fallback qty: `(po.qty - po.cum_filled_qty).max(0.0)` 或退到 `position.qty`（partial fill 後只追 remainder）（line 152-156）
- 派發: `pipeline.dispatch_close_maker_market_fallback(...)` → `commands.rs:1082-1205` 走 `oc_close_mf_fb_*` prefix

**per-symbol exponential backoff**（maker_rejection.rs:388-461）:
- 初始 1s → ×2 倍增 → 上限 60s
- 5min quiet → reset 回 1s
- 60s window 內 10 個 distinct symbol 觸發 EC_ReachMaxPendingOrders → 全域 pause 300s + 清空 per-symbol state

### §1.7 audit columns（V094 schema）

**檔**: `srv/sql/migrations/V094__fills_close_maker_audit.sql`

新欄位 (trading.fills):
- `close_maker_attempt BOOLEAN NOT NULL DEFAULT FALSE`（hot column；attempt=TRUE 即實際派 PostOnly close maker）
- `close_maker_fallback_reason TEXT NULL`（10-value NOT VALID CHECK enum）
- `idx_fills_close_maker_attempt_v094` partial index `(engine_mode, ts DESC) WHERE close_maker_attempt=TRUE`
- `details JSONB` 內含 `close_initial_limit_price` / `close_final_fill_price` / `close_maker_eligible_reason` / `rate_limit_scope`（commands.rs:786-794）

**writer**: `srv/rust/openclaw_engine/src/database/trading_writer.rs:431` INSERT 含全 26 欄；market close path 帶 cold defaults (line 1026/1163/1292/1328)。

---

## §2 Evidence inventory（有 / EVIDENCE-GAP 分類）

### §2.1 PG schema evidence — 可用

| Table / column | 證據可得 | 對 fix 用途 |
|---|---|---|
| `trading.fills.close_maker_attempt` (V094) | ✅ hot column + partial index | 區分 maker 嘗試 vs market close |
| `trading.fills.close_maker_fallback_reason` (V094) | ✅ 10-value enum CHECK | 量化 fallback 模式分佈 |
| `trading.fills.details JSONB` (V094) | ✅ `close_initial_limit_price` / `close_final_fill_price` / `rate_limit_scope` | 量化 maker price vs actual fill price gap |
| `trading.fills.liquidity_role` (V028) | ✅ enum `maker/taker/unknown/paper_sim` | 真實 maker 成交確認（非僅 attempt） |
| `trading.fills.reference_price / ts_ms / source` (V028) | ✅ | dispatch 時刻 BBO 對比；close 路徑 source=`dispatch_last_fallback`（commands.rs:1007-1011）|
| `trading.fills.fill_latency_ms` (V028) | ✅ | maker 派發 → 成交 latency；close 路徑可區分快/慢 fill |
| `trading.fills.slippage_bps` (V028) | ✅ | adverse slippage signed bps |
| `trading.fills.fee / fee_rate` (V008) | ✅ | maker (-0.0001) vs taker (+0.00055) 區分 |
| `trading.fills.exit_reason` (V033) | ✅ free-text 退場原因 | 群組 fill rate by reason |
| `trading.orders + trading.order_state_changes` (V003) | ✅ ts / status / filled_qty / avg_price / reason | full order lifecycle replay（status transition: Submitted → Working → Cancelled (reason=self_cancel)）|
| `market.market_tickers.best_bid / best_ask / spread_bps / bid_size / ask_size` (V002) | ✅ | dispatch ts ±N sec 內 BBO 復原 |

### §2.2 EVIDENCE-GAP — 顯著缺口

| 缺項 | 影響 | 為何缺 |
|---|---|---|
| **Trade tape / public_trades L1**（`market.trades` 不存在） | 無法判斷 maker 限價是否被「taker hit 過」（queue priority 真實實現需要 trade ticks vs my limit） | V002 只有 `trade_agg_1m` 1 分鐘聚合，no per-tick trade events table |
| **L2 orderbook depth snapshots** | 無法看 my order 在 queue 內第幾位 / 前面有多少 size | 無 `market.orderbook_*` table；只 `market_tickers` 提供 BBO + size 但無 deeper levels |
| **Bybit-reported queue position** | 無法用 ws 提供的 cumulative size at price level | 引擎未訂閱 / 未寫 DB |
| **PostOnly reject 計數細粒度（per-reason within close path）** | 無法區分 PostOnly cross vs RateLimit vs Other 在 close path 內的分佈（aggregated 在 healthcheck [65] 但不分 entry/close） | helper script 有 `65_reject_sample_healthcheck.py` 但本身 SQL aggregator 未明確過濾 close path |
| **maker order placement → first fill latency 分佈**（無 dedicated column） | 無法問「placed maker 在多少 ms 內收到第一次 fill 訊號」 | `fill_latency_ms` 是 dispatch→fill 端到端，未拆 placement→ack vs ack→first_fill |
| **dispatch 同時刻的 spread / queue 狀態快照（與 fill outcome 配對）** | 計算「placement 時的 spread_bps × buffer_ticks 對 fill outcome 的回歸分析」需要 per-attempt BBO snapshot；目前需要 `JOIN market_tickers ON closest ts`（會有 ±100ms 不確定性） | 結構上未把 placement-time BBO 寫進 `details` JSONB；只有 dispatch 後 emit 時的 reference_price |
| **partial fill 在 maker timeout 內的 fill ladder**（OrderUpdate 細粒度） | 無法看「90s 內第幾秒有部分 fill / cum_filled_qty 增量曲線」 | order_state_changes 的 filled_qty 是每次更新的累計值，但僅在 status 轉變時寫；無 timeline 細密度 |
| **同窗 entry 端 PostOnly attempt 對比（用作 control group）** | sweep 看 close 但 entry 是 not-attempted in current schema 區分 | `close_maker_attempt=TRUE` 標明 close maker；entry 端無對等 boolean column，要靠 `strategy_name NOT LIKE '%_close%' AND time_in_force='PostOnly'` 推斷 |

**FA 明確標**: 任何「queue-aware placement / queue position model / 真實 trade-tape latency 對齊」改善 sub-task **均落在 EVIDENCE-GAP 區**，需先補資料層（不在本 P2 task scope 內）。

---

## §3 問題模式（綁 evidence）

### §3.1 PM-1: timeout 後 100% 走 market fallback 是設計如預期，不是 bug

**Evidence**:
- E2 RCA 2026-05-18 §3 Hypothesis 1-5: state machine 4/4 timeline 與 spec §5.2 Race B 完全一致（PostOnly 提交 → Working → Cancelled (self_cancel) → market fallback within 80-90ms of cancel ack）
- Wilson CI for n=4, 0 fills = [0%, 49%]，**包含 spec §1.2 設計預期區間 15-25%**
- spec §1.2 line 44 自承「悲觀 (close-path conservative discount 25-40%): ~0.66 bps per close attempt (assumes close fill rate ≈ 20%, 15-25% range)」

**意涵**: AC-19 14d 30% gate 是設計上預測「達不到也要 spec amendment 而非 code fix」。當前 n 太小無法判 fix-required。

### §3.2 PM-2: sweep BBO-cross proxy 對 close path 系統性樂觀

**Evidence**:
- PA calibration report 2026-05-18 §5.1: sweep `_did_fill_within_window` 用 BBO-cross-proxy（best_ask <= offset 或 best_bid >= offset within timeout）判 fill，**不是真實 trade tape**
- Sweep G-AB-01-C90 fill rate 0.708 vs 24h post-deploy 0/4 = 0% (E2 RCA)
- sample velocity ~0.44 grid_close/hr（v55 archive §0），需 T+72h ~96h~120h（2026-05-22~23 UTC）才到 n≥30

**意涵**: 不可用 sweep proxy 推論 placement / timeout 改變的真實 fill rate 影響。**這正是本 P2 task v55 治理 invariant**（禁用 sweep proxy 調 runtime）。

### §3.3 PM-3: close path 與 strategy entry path 共用 helper 但 trigger 時刻不同 → placement 條件異質

**Evidence**:
- entry path: strategy 主動算 `entry_order = resolve_entry_order(ctx, is_long)` 回 `(order_type, limit_price, time_in_force, maker_timeout_ms)`（grid_trading/signal.rs:304-309, 343-358, 375-388）— 限價在策略決策時刻用 ctx 同時刻 BBO 算
- close path: 策略只發 `StrategyAction::Close { symbol, confidence, reason }`（無 limit_price），**限價在 commands.rs:962-968 的 dispatch tick 時刻**用 event BBO 反算
- 結果：entry 是「策略邏輯時刻」決策；close 是「dispatch tick 時刻」決策；兩者可能差 0-N ticks（取決於 strategy.handle_tick 與 step_4_5_dispatch 之間的 borrow boundary）

**意涵**: close maker placement 對「dispatch 時刻 BBO 是否仍然 healthy」非常敏感；entry path 較不敏感因為策略可在自己 ctx 內驗 BBO + skip。**evidence-based 改善需測「placement 時刻 BBO 與真實 fill outcome 之間的相關性」**。

### §3.4 PM-4: phys_lock family `stale_roc_neg` reason 在 sweep 100% n_eligible=0 — 是 router 缺口或當前無 close 觸發

**Evidence**:
- PA calibration report 2026-05-18 §5.3: 全 26 cells PS family `n_skipped_family_mismatch=54` (= n_attempts), `n_eligible=0`
- 推測（PA report 列 3 個原因）:
  - (1) Router 不發 phys_lock_stale_roc_neg family close
  - (2) Sweep 用的 4h sample 不含該 family close events
  - (3) Family routing 對該標籤未齊
- **EVIDENCE-GAP**: 需 Linux PG empirical query 看 `trading.fills.exit_reason='phys_lock_gate4_stale_roc_neg'` 14d window 的 count；若 0 → 配置上沒觸發；若 >0 但 maker_attempt=0 → router 缺口

**意涵**: 此項是 sweep 副產發現，但在源碼 grep 結果 maker_price.rs:104-108 該 reason 有完整 policy 條目（10_000ms / 1 buffer / 0.5 offset）。需 Linux 驗 fill 數據才能定 router 缺口 vs 0 觸發。

### §3.5 PM-5: maker_timeout_ms=90_000ms（grid family）期間倉位曝險窗 vs ATR — 原則 #5 緩解仍未量化

**Evidence**:
- FA round 1 verdict 2026-05-15 §4 #5 CONDITIONAL: maker timeout 期 (45s default 當時，90s 現) 倉位仍 expose；若 spot-vol spike，可能 1-3 個 ATR 移動
- FA round 1 緩解建議: AC 必含 `close_timeout_pre_stopout_rate ≤ 5%`（在 maker timeout 內被 hard stop 搶先觸發的比例）
- AMD-2026-05-15-02 + Phase 1b spec v1.3 **未把此 AC 寫進 14d gate**（grep AMD-03 / spec v1.3 無 `close_timeout_pre_stopout_rate` 命名）
- E2 RCA §4 Tune-2: 「extend timeout 30→45s 風險 close exposure window 長 = §二 #5 生存 > 利潤 trade-off」明示此 trade-off 但 18-MAY calibration 把 timeout 推到 90s 而沒寫對應 AC

**意涵**: 90s timeout 已 calibrated 部署，但「90s 內 hard stop 觸發搶在 maker fill 前的比例」**沒有 SQL 監測**。這是 §四 hard boundary 邊緣的 governance gap。

### §3.6 PM-6: V094 fallback_reason 10 enum 中 NotAttemptedSafetyPath / FastEscalateSafetyUpgrade / EngineShutdownSafety 派發路徑 evidence 缺失

**Evidence**:
- maker_rejection.rs:111-126 列 10 個 enum value；CHECK constraint V094 line 142-155 enforce 10 個 valid string
- grep `maker_rejection|FallbackReason::FastEscalate|FallbackReason::NotAttempted|FallbackReason::EngineShutdown` in src/ 命中 maker_rejection.rs definitions + tests，**production 觸發點 grep 0**：
  - `FastEscalateSafetyUpgrade` 僅 close_maker_fallback_decision() match arm（line 223-227）+ tests
  - `NotAttemptedSafetyPath` 僅 requires_market_fallback() carve-out（line 149）+ enum tests
  - `EngineShutdownSafety` 僅 close_maker_fallback_decision() match arm（line 249-253）+ tests
- 對應的 `CloseMakerFallbackEvent::{FastEscalateSafetyUpgrade, EngineShutdown}` 在 production code 也 grep 0 emit point

**意涵**: 三個 fallback reason **enum 存在但無 production producer**，類似 FA memory FA-H3「代碼活但 0 引用」反模式。是 dead enum 還是「未來路徑保留」需 PM/PA 決議是否 schema-level deprecation。

### §3.7 PM-7: A-axis（offset_bps）在 sweep 對 fill rate 完全無感 — 待源碼 verify

**Evidence**:
- PA report 2026-05-18 §5.2: A=0.5/1.0/2.0/3.0 在同樣 B+C+D 下 fill_rate 完全 identical（6 位小數）
- 3 個 hypothesis:
  - (1) 60% probability — spec design intent，BBO-cross 由 spread 主導
  - (2) 25% probability — `_did_fill_within_window` IMPL bug，offset 變量未進入 cross 判定
  - (3) 15% probability — 4h sample 太短
- SD-1 dispatch in PA report 已建議 spot check `phase_1b_sweep_replay.py:200-300`

**意涵**: 若是 hypothesis 2，offset 在 sweep 是 dead variable；推論「offset 對真實 fill 影響」全部無效。當前部署用 offset=0.5 是「sweep tied 中 conservative pick」，**真實價值需 trade-tape 驗證**。

### §3.8 PM-8: 24h post-deploy 4/4 timeout_taker 之觀察 sample 集中 UTC 05:00-06:30 asia-pre-open thin liquidity window

**Evidence**:
- E2 RCA 2026-05-18 §1 觀察: 3 of 4 fallback rows 在 UTC 05:00-06:30
- 該 1.5h window = Bybit demo asia-pre-open，book depth 通常較稀
- E2 RCA §3 Hypothesis 4 列 demo entry side 24h baseline: 156 PostOnly entries → 23 filled = 14.7%，同管線同合約

**意涵**: 樣本時段集中 → 真實 PnL-bearing window（UTC 12:00-22:00 高活躍）fill rate 可能不同。**evidence 需 stratify by hour-of-day**；當前 healthcheck [62] SQL（62_close_maker_fill_rate.py:104-118）**沒做 hour-of-day stratification**。

### §3.9 PM-9: close maker 觸發 trigger_tag 規範化中存在「strategy_close: 雙剝」歷史 patch — 對未知 reason 是否 fail-closed 已 carved 但需 trade-tape verify

**Evidence**:
- `canonical_close_maker_reason()` maker_price.rs:68-81 使用 loop strip prefix（防雙 prefix drift）
- `is_close_maker_market_only_reason()` line 115-148 enforces 25 個 case + raw_lower contains 7 個 keyword
- close_maker_price_policy line 109 `_ => None`（fail-closed 走 market）— 未明文 reason 必 fall-through
- 測試 `close_policy_rejects_negative_whitelist_and_unknown` line 561-600 釘住 negative 25 條 + unknown 1 條 = 26 cases

**意涵**: source 層 enforcement 強，但「實際 14d 內出現過幾個 unique exit_reason」需 PG 查 `SELECT DISTINCT exit_reason FROM trading.fills WHERE ts > NOW()-INTERVAL '14 days'`。如有 spec 未列的 reason 落入 maker path (positive whitelist 命中) 或 fail-closed (None case) — 兩種行為都需 audit。

---

## §4 改善建議（綁 evidence，不寫 patch）

> 約束: 任何「runtime 參數調整」改善禁出此 P2 sprint；任何「PG migration」改善 Phase 1b 觀察期內 freeze；以下都是 **source / spec / 觀測層** 改善建議。

### §4.1 OBS-1（P1）: 補 placement-time BBO 進 V094 audit `details` JSONB

**為何改**:
- §3.3 PM-3: entry vs close path 在 placement 時刻 BBO 不同；close path 當前 reference_price = dispatch_last_fallback（commands.rs:1007-1011），是 dispatch 時刻自身計算的 limit_price，**不是 BBO 同時刻 snapshot**
- §3.7 PM-7: A-axis 在 sweep 無感 — 真實 spread 是否吃掉 offset 是 BBO 同時刻才可驗
- §2.2 EVIDENCE-GAP「placement 時刻 BBO snapshot」直接覆蓋

**Evidence 支持**:
- `commands.rs:962-968` 已從 event 抽出 (best_bid, best_ask)
- `commands.rs:786-794` close_maker_details JSONB 已建立 4 個 key；補 `placement_best_bid` / `placement_best_ask` / `placement_spread_bps` / `placement_tick_size` 是 append-only schema-compat 改動，**V094 已含 details JSONB column（V094 line 14 設計 reserve）**

**改什麼**:
- 在 commands.rs:786-794 close_maker_audit JSONB serializer 內補 4 個 placement-time BBO 欄位（從 close_order_dispatch_shape 已抽出的 (best_bid, best_ask) + tick_size）
- 改 spec：spec §11 AC-A SQL 補一條 stratification by placement_spread_bps quartile（例：`< 5bps / 5-15bps / 15-30bps / 30-50bps`）

**為何不是 runtime 改動**: append 新 JSONB key 不影響 placement 邏輯本身；不改 cooldown / not 觸發 user-visible behavior change。是純觀測層加碼。

**Out of scope**: 此改動 source 修改不在本報告範圍（FA 不寫 patch）。建議下 sprint PA + E1 IMPL。

---

### §4.2 OBS-2（P1）: 補 `close_timeout_pre_stopout_rate` healthcheck（覆蓋 FA round 1 緩解 #5）

**為何改**:
- §3.5 PM-5: 90s timeout 部署但「90s 內 hard stop 觸發搶在 maker fill 前」無 SQL 監測
- FA round 1 verdict §4 #5 CONDITIONAL 緩解 (c) 已明列 AC，**Phase 1b 部署時未掛上**

**Evidence 支持**:
- `trading.orders` 含 `order_link_id` (PK) → 可 join `state_changes` 看「PostOnly close order 是否在 timeout 內被同 symbol 的 risk-close 取代」
- close-maker fallback `oc_close_mf_fb_*` prefix 與 strategy-close `oc_risk_*` prefix 區分明確（commands.rs:927 / 1108）
- 已存在 helper script pattern：`helper_scripts/canary/healthchecks/63_close_maker_fallback_audit.py`，新檔 `[71] close_maker_pre_stopout_rate.py` 可仿格式

**改什麼**:
- 新 healthcheck script 計：
  - 分子 = 14d 內 `strategy_name LIKE 'risk_close:HARD STOP%' OR LIKE 'risk_close:TRAILING%' OR LIKE 'risk_close:TIME%'` fill 之前 `< 90_000ms` 有相同 symbol 的 `close_maker_attempt=TRUE` PostOnly cancel
  - 分母 = 14d 內 `close_maker_attempt=TRUE` 總嘗試
  - 觀測 gate（不阻 deploy）：`pre_stopout_rate ≤ 5%`
- 寫 `helper_scripts/canary/healthchecks/71_close_maker_pre_stopout_rate.py` + run cron 每 4h
- 把 gate 寫進 spec §11 AC-19a（無新 fail 行為，純監測）

**為何不動 runtime**: SQL 只讀，無 placement / cancel / fallback 邏輯改動。是純觀測加碼。

---

### §4.3 OBS-3（P1）: stratify [62] close_maker_fill_rate.py by hour-of-day + day-of-week

**為何改**:
- §3.8 PM-8: 3/4 fallback sample 在 UTC 05:00-06:30 asia-pre-open thin window；可能高估 system-wide fill failure
- 真實 PnL-bearing window 是高活躍時段，需分離 sample

**Evidence 支持**:
- `helper_scripts/canary/healthchecks/62_close_maker_fill_rate.py:103-118` SQL 已 group by engine_mode；補一層 `EXTRACT(HOUR FROM ts AT TIME ZONE 'UTC')` 即可
- `trading.fills.ts` 是 TIMESTAMPTZ（V003 line 271 hypertable column）
- 6 個 close reason × 24 hour × 7 dow 矩陣樣本量需大 — Wilson CI 仍走 `min_sample=30` per cell（過小落 INSUFFICIENT_SAMPLE 不阻 deploy）

**改什麼**:
- 改 `62_close_maker_fill_rate.py` 加 `--stratify {hour,dow,both,none}` flag（cold-default `none` 維持 backward-compat）
- 加 emit `result.cells_stratified` JSONB
- 新增 dashboard chart「fill_rate by UTC hour」便操作 visual

**為何不動 runtime**: 純 SQL aggregation 改動；不影響任何 deploy gate。

---

### §4.4 SPEC-1（P1）: 把 §3.6 三個 dead enum 從 V094 CHECK constraint 拆出來決議

**為何改**:
- §3.6 PM-6: `FastEscalateSafetyUpgrade` / `NotAttemptedSafetyPath` / `EngineShutdownSafety` 在 production 0 emit point；V094 CHECK constraint 含 10 個 enum，3 個 dead 是 governance debt
- FA memory 「代碼活但 0 引用」反模式

**Evidence 支持**:
- `grep -r "FallbackReason::FastEscalateSafetyUpgrade\|FallbackReason::NotAttemptedSafetyPath\|FallbackReason::EngineShutdownSafety" srv/rust/openclaw_engine/src/` 命中：
  - maker_rejection.rs:115-125 (enum definition)
  - maker_rejection.rs:130-149 (as_str/requires_market_fallback impl)
  - maker_rejection.rs:222-258 (close_maker_fallback_decision match arms)
  - maker_rejection.rs:580+ (tests)
- 全 0 actual production caller (production = 非 tests 子目錄、非 mod tests)
- `CloseMakerFallbackEvent::FastEscalateSafetyUpgrade` 在 production code 也 0 emit point

**改什麼**:
- PA + PM 決議：
  - 選項 A：留 enum + V094 CHECK 但寫 ADR-XX「保留待 Phase 2 IMPL」+ 加 reservation note
  - 選項 B：sunset enum + V094 next migration 縮到 7 個 valid value（不可逆破 audit log）
- FA 建議選 A，因 V094 CHECK 改動是 P0 schema change，14d observation window 內絕對禁；同時 enum 不寫 dead code marker 會繼續被 sub-agent 誤用

**為何不動 runtime**: spec + 文檔 / ADR 改動；無 runtime 影響。

---

### §4.5 EVID-1（P2）: 補 trade-tape table（market.public_trades）+ L2 orderbook snapshot table 設計 ADR

**為何改**:
- §2.2 EVIDENCE-GAP 多項依賴於 trade-tape / L2 book 數據
- 任何「queue position model / placement-aware adjustment」改善都 blocked 於此

**Evidence 支持**:
- 當前無 `market.trades` 表（V002 只有 trade_agg_1m 聚合）
- 當前無 `market.orderbook_l2_snapshot`（V002 只有 market_tickers 含 L1）
- Bybit V5 WS 已含 `publicTrade` + `orderbook.50.{symbol}` topics（infra 已有 WS）
- DB 寫盤負荷需評估：`publicTrade` ~1k events/symbol/hour × 25 symbol = ~600k rows/day（依 timescale 1day chunks 是可吃）

**改什麼**:
- PA + MIT 起 ADR：「market.public_trades 與 market.orderbook_l2_snapshot 寫盤策略」
- 含：
  - 寫盤頻率（per-tick vs sampling）
  - retention（trade-tape 1 week hot / 4 week cold；L2 snapshot 1 day hot only）
  - storage 估算（每 symbol 每天 size）
  - 用途：queue position model / placement-aware adverse selection / 替代 BBO-cross-proxy
- ADR 寫完後 → MIT 設計 V### migration → 先 demo 啟 7d 觀察 → 寫盤穩定後 live

**為何不動 runtime**: 純文檔層 ADR；migration apply 仍需 14d obs window 結束後

---

### §4.6 EVID-2（P2）: stratify A-axis (offset_bps) IMPL bug check

**為何改**:
- §3.7 PM-7: PA report 標 25% probability 是 IMPL bug — 6位小數同分太可疑

**Evidence 支持**:
- PA report 2026-05-18 §6.2 SD-1 已建議「E1/E2 verify A axis behavior」（line 426-430）
- ETA ~30 min；0 dependency on pilot

**改什麼**:
- E1 / E2 spot-check `srv/helper_scripts/calibration/phase_1b_sweep_replay.py` `_did_fill_within_window` function 用 `offset_bps` 變量的方式
- 對比文獻：spec §3.4 line 應該定義「BBO-cross 是用 limit_price 還是 limit_price ± offset」
- 若是 IMPL bug → patch + 重 sweep（calibration 步驟）；若是 design intent → spec v0.3 amend 標明「A axis 是 fee saving design parameter, not fill detection parameter」

**為何不動 runtime**: 純 simulation harness IMPL/spec verify；無 runtime 改動

---

### §4.7 SPEC-2（P2）: Phase 1b spec §4.3 補 `phys_lock_gate4_stale_roc_neg` 觸發點審計子任務

**為何改**:
- §3.4 PM-4: sweep 100% n_eligible=0；router 是否真有 emit 此 reason 缺驗證

**Evidence 支持**:
- spec v1.3 §4.3 將 `phys_lock_gate4_stale_roc_neg` 列入正白名單
- maker_price.rs:104-108 有完整 policy（10_000ms / 1 buffer / 0.5 offset）
- production grep `phys_lock_gate4_stale_roc_neg` 在 step_6_risk_checks.rs 應該有 emit；需驗

**改什麼**:
- PA 加 SD（已在 PA report §6.2 SD-2）：派 PA/FA 並行核 production emit 路徑 + 14d 真實 trigger 計數
- 若 trigger=0 → 列 ADR governance debt（dead positive whitelist）
- 若 trigger>0 且 maker_attempt=0 → router / strategy_close: envelope drift → bug ticket

**為何不動 runtime**: 純 audit；14d observation window 後再考慮 spec / router 改

---

### §4.8 改善建議優先序總表

| ID | 類別 | 優先 | 是否需 runtime | Phase 1b 期內可動 | 依賴 EVIDENCE-GAP |
|---|---|---|---|---|---|
| OBS-1 | source append-only audit | P1 | NO（append details JSONB） | ❌ 14d freeze | NO |
| OBS-2 | new healthcheck | P1 | NO（純 SQL） | ✅ 可動 | NO |
| OBS-3 | healthcheck stratification | P1 | NO（純 SQL） | ✅ 可動 | NO |
| SPEC-1 | enum / ADR cleanup | P1 | NO | ❌ migration 改動禁 | NO |
| EVID-1 | new schema ADR | P2 | NO | ✅ ADR 可寫 | YES（trade-tape gap） |
| EVID-2 | sim harness check | P2 | NO（calibration tool） | ✅ 可動 | NO |
| SPEC-2 | spec audit | P2 | NO | ✅ 可動 | NO |

---

## §5 Open questions / 需要 operator/PM 決議

### §5.1 OQ-1: P2-ENTRY-CLOSE-MAKER-REAL-FILL-FIX scope 是否包含 EVID-1（trade-tape schema ADR）？

**爭議**: 本 task 名為 "REAL FILL FIX"，但 evidence 顯示真實 fill rate 改善需要 queue-aware placement 或 trade-tape feedback；兩者都 blocked 於 §2.2 EVIDENCE-GAP。
- 選項 A：scope 限制在「現有 evidence 內的 fix」→ OBS-1/OBS-2/OBS-3/SPEC-1 共 4 條；P2 完工
- 選項 B：scope 擴大 到「補 evidence layer 解 fill rate root cause」→ 加 EVID-1（新表設計 + ADR）+ EVID-2（sim harness verify）；P2 變多 sprint
- **FA 推薦**：選項 A — 因 trade-tape ADR 是獨立 backlog，不應與 close-maker fill rate 改善綁定（兩者 timing 不同步）

### §5.2 OQ-2: 90s timeout 部署期間 `close_timeout_pre_stopout_rate` 監測上線是否阻 14d obs clock 不重啟？

**爭議**:
- FA round 1 §4 #5 CONDITIONAL 明示需要此 AC，但 deploy 已開（2026-05-18 13:50 UTC reset 14d clock）
- 補 healthcheck（OBS-2）是純觀測層 → FA 認為不該 reset clock
- 但若補完發現 pre_stopout_rate > 5% → 需 PM/operator 決議是否 rollback timeout 從 90s 退到 30s
- 兩個風險: (a) 補 AC 後反向觸發必 rollback (b) 不補 AC 持續無監測就 14d obs PASS
- **FA 推薦**：補 healthcheck（OBS-2）不算改 runtime；但 PM 必先聲明「OBS-2 結果若 FAIL，policy 是 spec amendment vs rollback runtime」邊界

### §5.3 OQ-3: §3.6 三個 dead enum（FastEscalate / NotAttempted / EngineShutdown）的 governance posture

**爭議**:
- 三 enum 在 maker_rejection.rs 有完整 impl + test 但 production 0 emit point
- V094 CHECK constraint 已 enforce 10 個 valid string
- 選項 A：留 + 寫 ADR 標 reservation（FA 推薦，最低風險）
- 選項 B：sunset + V094 next migration 縮 enum（high cost，影響 audit log）
- 選項 C：補 production emit point（design intent 未明 — engineShutdown 應該誰觸發？）
- **FA 推薦**：A；若 PM 想清理請排 Sprint N+X，禁與 Phase 1b 14d obs 並行

### §5.4 OQ-4: A-axis (offset_bps) IMPL verify timing — 等 14d obs 完成 vs 立即 spot-check

**爭議**:
- §3.7 PM-7 + PA report §6.2 SD-1: 30min spot-check 可定 hypothesis
- 立即驗 risk: 若是 IMPL bug，可能影響當前 deployed offset=0.5 是「sweep tied 中隨機選」非「真實 evidence-based」決定 → 推翻 calibration 決議
- 等 obs 完成 risk: 14d 觀察期內若是 bug 不修，14d real fill outcome 全部偏 noise
- **FA 推薦**：立即 spot-check（不動 runtime）；若是 IMPL bug，補 patch 到 simulation harness 而非 runtime；14d clock 不重啟（observation 用 real fills，不依賴 sweep）

### §5.5 OQ-5: Phase 1b spec §11 AC 是否需新增 EVIDENCE-source declaration?

**爭議**:
- 當前 AC-A SQL 直接 query `trading.fills`；無明文標「sample 必須跨 24h diversify (不集中 asia-pre-open)」
- §3.8 PM-8 顯示 sample 集中時段風險真實存在
- 若不加 declaration，AC-A PASS 可能基於 biased sample
- **FA 推薦**：spec v1.4 patch 加一條 secondary AC「14d 觀察 sample 在 UTC hour distribution 跨度 ≥ 18h 各時段都有 ≥3 attempts」，否則 observation 不算 conclusive

---

## §6 16 根原則合規 / 9 安全不變量檢查

### §6.1 16 根原則

| # | 原則 | 本報告 / 提議行為狀態 | 證據 |
|---|---|---|---|
| #1 單一寫入口 | ✅ | 報告 read-only；提議都是 audit/spec layer |
| #2 讀寫分離 | ✅ | 純讀 source / DB schema |
| #3 AI→Lease→複核→執行 | ✅ N/A | 不觸 lease |
| #4 策略不繞風控 | ✅ | OBS-2 補風控盲區 (pre_stopout_rate) 是強化 |
| #5 生存 > 利潤 | ✅ | OBS-2 直接覆蓋此原則 carved-out 緩解 |
| #6 失敗默認收縮 | ✅ | 提議都是 observation 強化，無 loosen |
| #7 學習 ≠ 改寫 Live | ✅ | 不觸 ML / DreamEngine |
| #8 交易可解釋 | ✅ | OBS-1 直接覆蓋此原則（補 placement BBO） |
| #9 災難保護 | ✅ | EngineShutdownSafety 在 SPEC-1 顯式處理 |
| #10 認知誠實 | ✅ | EVIDENCE-GAP 明確標 |
| #11 P0/P1 自主 | ✅ N/A | 純 audit |
| #12 持續進化 | ✅ | 提議建立 evidence 補完 chain |
| #13 AI cost 感知 | ✅ N/A | 無 AI 呼叫 |
| #14 零外部成本 | ✅ | 都本地 |
| #15 多 Agent 協作 | ✅ | OQ section 明指 PM/PA/operator decision points |
| #16 組合級風險 | ✅ | §3.5 PM-5 直接屬此維度 |

**評級**: 16/16 PASS

### §6.2 9 條安全不變量

| 不變量 | 是否觸碰 | 說明 |
|---|---|---|
| execution_state | NO | 報告 read-only |
| execution_authority | NO | 無 |
| live_execution_allowed | NO | 14d obs window freeze 期間禁啟 live |
| decision_lease_emitted | NO | 不觸 lease |
| max_retries | NO | 無 |
| OPENCLAW_ALLOW_MAINNET | NO | 環境變數不變 |
| authorization.json HMAC | NO | 不觸認證 |
| live_reserved global mode | NO | 不接 Python live_reserved |
| Bybit retCode != 0 fail-closed | ✅ PASS | OBS-2/3 不引入新 retry |

**結論**: 9/9 PASS

### §6.3 BLOCKER 清單

無 BLOCKER。

---

## §7 業務鏈完整度評分（Phase 1b close-maker 為觀察單元）

| 環節 | 當前狀態 | 提議 OBS-1+OBS-2+OBS-3 落地後 |
|---|---|---|
| 下單 (close path placement) | 93%（V094 audit 完整，但 placement-time BBO snapshot 缺） | 95%（+OBS-1） |
| 止損 (90s timeout 期間 risk_close 搶占監測) | 92%（無 pre_stopout_rate metric） | 95%（+OBS-2） |
| 觀察（fee audit completeness） | 90%（cells stratification 缺） | 93%（+OBS-3） |
| 學習（trade-tape 缺，BBO-cross proxy 不準） | 65%（受 EVIDENCE-GAP 限制） | 65%（不變 — 需 EVID-1） |

**整體業務鏈**：63% → 預期 OBS triple 落地後 65%

---

## §8 報告索引

- 報告位置: `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-20--entry_close_maker_real_fill_fix_analysis.md`
- 配套 references:
  - `srv/docs/CCAgentWorkSpace/E2/workspace/reports/2026-05-18--phase_1b_timeout_taker_rca.md` — E2 4/4 timeout RCA
  - `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-18--phase_1b_calibration_cell_selection_report.md` — sweep G-AB-01-C90 pick
  - `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-15--close_maker_first_fa_verdict.md` — FA round 1 verdict 含 #5 CONDITIONAL（覆蓋 OBS-2）
  - `srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-15--amd_2026_05_15_02_4agent_review_fa.md` — AMD round 2
  - `srv/docs/execution_plan/2026-05-15--edge_p2_3_phase_1b_close_maker_first_spec.md` — spec v1.3
  - `srv/docs/execution_plan/2026-05-15--v094_close_maker_first_audit_schema_spec.md` — V094 audit schema spec
  - `srv/docs/archive/2026-05-19--todo_v55_translation_archive.md` — v55 entry-path RCA + P2 backlog 出處

**關鍵 source pointers（後續 IMPL 必讀）**:
- `srv/rust/openclaw_engine/src/tick_pipeline/commands.rs:109-154`（close_order_dispatch_shape — placement 決策入口）
- `srv/rust/openclaw_engine/src/tick_pipeline/commands.rs:786-794`（close_maker_audit details JSONB — OBS-1 改動點）
- `srv/rust/openclaw_engine/src/strategies/common/maker_price.rs:85-211`（policy + compute_close_limit_price）
- `srv/rust/openclaw_engine/src/event_consumer/pending_sweep.rs:21-117`（timeout + cancel grace + sweep classifier）
- `srv/rust/openclaw_engine/src/event_consumer/loop_handlers.rs:94-168`（dispatch_close_maker_fallback_from_pending — fallback orchestrator）
- `srv/rust/openclaw_engine/src/strategies/maker_rejection.rs:107-461`（10-value enum + fallback decision + per-symbol backoff）
- `srv/sql/migrations/V094__fills_close_maker_audit.sql`（audit schema SoT）
- `srv/helper_scripts/canary/healthchecks/62_close_maker_fill_rate.py`（OBS-3 改動點）
- `srv/helper_scripts/canary/healthchecks/63_close_maker_fallback_audit.py`（OBS-2 parallel pattern reference）

---

**P2-ENTRY-CLOSE-MAKER-REAL-FILL-FIX 分析 DONE**
- 7 條 evidence-based 建議（OBS-1/OBS-2/OBS-3/SPEC-1/EVID-1/EVID-2/SPEC-2）
- 8 條 EVIDENCE-GAP（trade-tape / L2 book / queue position / PostOnly reject 細粒度 / placement→ack vs ack→first_fill 拆分 / dispatch-time BBO 與 fill 配對 / partial fill timeline / entry maker control group column）
- 5 條 Open Question 待 operator 或 PM 決議
- 16/16 root principles + 9/9 safety invariants PASS
- BLOCKER: 0

**PM 決議（已 inline operator approve 2026-05-20）**：
- OQ-1: 選 A（scope 限現有 evidence）
- OQ-2: 補 healthcheck 不 reset clock；FAIL → spec amendment 而非 rollback
- OQ-3: 選 A（留 enum + ADR reservation）
- OQ-4: 立即 spot-check sim harness
- OQ-5: 加 secondary AC（UTC hour distribution ≥ 18h cover）
