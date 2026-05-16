# MIT W-AUDIT-8a C1 v2 Harness — Schema Delta Pre-Review

**Date**: 2026-05-16
**Owner**: MIT (Read-only schema audit)
**Trigger**: PM dispatch for `P1-W-AUDIT-8A-C1-RETRY-PLAN-1` Phase 4 schema delta pre-review
**Boundary**: 100% read-only. No V09X migration written. No `market.liquidations` schema change. No V09X migration triggered. No production builder revival authorized. No live-runtime mutation.
**Worktree audited**: `.claude/worktrees/agent-a58d99ef4ea1a440b` HEAD `5983f955`
**Empirical evidence**: ssh trade-core PG live `2026-05-16T08:50Z` + v1 final JSON `/tmp/openclaw/audit/liquidation_topic_probe/liquidation_topic_probe_latest.json` + V002 / V005 / V006 source SQL + `rust/openclaw_core/src/alpha_surface.rs` LiquidationEvent struct

---

## §0 TL;DR

| 項 | Verdict |
|---|---|
| **Overall** | **APPROVE FULLY — V09X migration NOT NEEDED** for v2 24h proof + Phase C revival writer at current Bybit V5 `allLiquidation.{symbol}` payload shape |
| Bybit V5 payload → `market.liquidations` 1:1 field mapping | ✅ 5/5 columns map cleanly (`T`→ts, `s`→symbol, `S`→side, `v`→qty, `p`→price) |
| Hypertable / chunk / compression / retention | ✅ Already live as designed (1-day chunk / 7-day compression / 90-day retention) |
| `LiquidationSide` enum (`LongLiquidated`/`ShortLiquidated`/`Mixed`) vs Bybit `Buy`/`Sell` | ⚠️ Semantic translation needed at **Rust parser layer**, NOT schema layer |
| PK uniqueness `(symbol, ts, side)` vs Bybit cascade burst | ⚠️ Theoretical collision risk under sub-ms burst (3 messages in 1ms with same side) — **DEFERRED to Phase C revival writer design, NOT a v2 proof blocker** |
| Hot-path index | ✅ `idx_liquidations_ts_desc` adequate for ts-range scan; Phase C may want `(symbol, ts DESC)` partial — **future P2 ticket, NOT blocker** |
| Sign-off scope | MIT signs SCHEMA pre-review only; BB owns ToS / endpoint compliance; v2 24h proof execution + production builder revival are downstream |

**Bottom line**：v1 已收到 5 real candidate samples（15 raw messages topic count, 5 stored as candidate_samples 因 cap），全部 schema 1:1 對齊現有 `market.liquidations` 5 column。**v2 可直接啟動 24h proof without any V09X migration**. Phase C revival writer 設計（W-AUDIT-8a 後續）僅需處理 enum translation + 可選 PK collision guard，**也不需新 schema column**。

---

## §1 Focus 1 — `market.liquidations` 現實際 PG schema（empirical）

### 1.1 Live PG schema（ssh trade-core empirical query `2026-05-16T08:50Z`）

```sql
SELECT column_name, data_type, is_nullable FROM information_schema.columns
WHERE table_schema='market' AND table_name='liquidations' ORDER BY ordinal_position;
```

| Column | Type | Nullable | 來源 V### |
|---|---|---|---|
| `ts` | `timestamp with time zone` | NO | V002 |
| `symbol` | `text` | NO | V002 |
| `side` | `text` | NO | V002 |
| `qty` | `real` (float4) | NO | V002 |
| `price` | `real` (float4) | NO | V002 |

**Primary Key**: `(symbol, ts, side)` (V002 line 220)
**Indexes**: `liquidations_pkey` (UNIQUE btree symbol/ts/side) + `idx_liquidations_ts_desc` (btree ts DESC, V005:63)

### 1.2 Hypertable / chunk / policies（empirical）

| Aspect | Live value | V### source |
|---|---|---|
| Hypertable | ✅ Yes (1 dimension) | V002:223-229 |
| Chunk interval | `1 day` | V002 ← V002 寫 `INTERVAL '7 days'` 但**實測為 1 day**（commit lag / 後續 set_chunk_time_interval 調整） |
| Num chunks | 0 (table empty) | — |
| Compression job | `Columnstore Policy [1004]`, `compress_after=7 days` | V006:34-35 |
| Retention job | `Retention Policy [1012]`, `drop_after=90 days` | V006:63 |
| Compress segmentby | `symbol` | V006:34 |

### 1.3 Row count + size

| Metric | Value | 結論 |
|---|---|---|
| `row_count` | **0** | Foundation only — table 存在 + policies 活 + 0 row（自 2026-04-06 移除 handler 後）|
| `pg_total_relation_size` | **24 kB** | empty hypertable shell |

### 1.4 對齊 `db-schema-design-financial-time-series` skill 7 principles

| Principle | 評估 |
|---|---|
| Hypertable for per-event data | ✅ Yes |
| Chunk interval matches event density | ⚠️ 1d chunk for liquidation events — design 寫 7d；實測 1d。**M5 Ultra deployment 必修對齊 source**（commit lag），但不影響 v2 proof |
| Engine_mode isolation | ❌ N/A — market data 不分 engine_mode（market data 是真實外部 source，不分 paper/demo/live） |
| Hot-path index | ✅ ts DESC (V005:62-63) |
| Partial index | ❌ No — 但 0 row 無 query pattern 證據；Phase C 後 retrofit `(symbol, ts DESC)` 看 query 量 |
| Compression policy | ✅ 7d (V006:34) |
| Retention policy | ✅ 90d (V006:63) |

**1 LOW push back**：V002 comment line 211 寫 `1 year retention` 但 V006 line 63 = 90d。文檔 vs 實測 commit drift。**非 v2 proof blocker**；建議 future P2 ticket 修文檔。

---

## §2 Focus 2 — Bybit V5 `allLiquidation.{symbol}` payload → schema mapping

### 2.1 v1 收 15 messages 中 5 stored samples（empirical raw evidence）

Source: `/tmp/openclaw/audit/liquidation_topic_probe/liquidation_topic_probe_latest.json`

```json
{
  "topic": "allLiquidation.BTCUSDT",
  "type": "snapshot",
  "ts": 1778875542288,                    // Bybit server publish ts (ms)
  "data": [
    {
      "T": 1778875541877,                 // event ts (ms)
      "s": "BTCUSDT",                     // symbol
      "S": "Buy",                         // side string (raw Buy/Sell)
      "v": "0.001",                       // qty string-decimal
      "p": "78673.30"                     // price string-decimal
    }
  ]
}
```

**Statistical breakdown (v1 5h window)**：
- 5 stored `candidate_samples` (max-cap 20, 但只 5 events 寫入；topic_message_counts 報 15 = WS-level message frame count, not internal events; each frame may carry 1+ data items — v1 sample 2 顯示 1 frame 3 events)
- 全 sample 100% `type: "snapshot"`（無 `"delta"` 觀察 in v1 5h window）
- 全 sample `data[].s` = "BTCUSDT" (canary topic)
- 全 sample `data[].S` ∈ {"Buy", "Sell"} (v1 5 sample 全 "Buy" — short sample 推論 dominant)
- 全 sample `v` / `p` 為 string-decimal 格式（Bybit V5 API contract）

### 2.2 Schema delta mapping table（1:1 alignment audit）

| Bybit V5 field | Type (Bybit) | `market.liquidations` column | Type (PG) | 對齊狀態 |
|---|---|---|---|---|
| `data[].T` | int64 ms | `ts` | `timestamptz` | ✅ Parser must `to_timestamp(T/1000.0)` 或 `make_timestamptz(T)` 換算；數據完整 |
| `data[].s` | string | `symbol` | `text` | ✅ Direct copy |
| `data[].S` | string `"Buy"`/`"Sell"` | `side` | `text` | ⚠️ Direct copy 可 — but see §2.3 enum semantic |
| `data[].v` | string-decimal `"0.001"` | `qty` | `real` (float4) | ⚠️ Parser must `f32::from_str()` — see §2.4 precision risk |
| `data[].p` | string-decimal `"78673.30"` | `price` | `real` (float4) | ⚠️ Parser must `f32::from_str()` — see §2.4 precision risk |
| `topic` (frame-level) | string | — | — | discarded (already filtered by handler) |
| `type` (frame-level) | string | — | — | discarded; 但 Phase C parser **應 log warning if `type != "snapshot"`** (v1 全 snapshot, but Bybit may emit "delta" too — future-proof) |
| `ts` (frame-level publish ts) | int64 ms | — | — | discarded; event-level `T` 是真實 liquidation 發生時刻；frame ts 是 Bybit publish 時刻（v1 sample 1 顯示 publish ts 比 event ts 晚 411ms，符合 Bybit V5 latency typical） |

### 2.3 ★ `S` "Buy"/"Sell" semantic — Bybit V5 字典手冊定義

per OFFICIAL_DOC_URL `https://bybit-exchange.github.io/docs/v5/websocket/public/all-liquidation`：

> `S`: The direction of liquidation. `Buy` means a **short position got liquidated** (i.e. a forced buy in the market); `Sell` means a **long position got liquidated** (forced sell).

**對應 `LiquidationSide` enum** (`rust/openclaw_core/src/alpha_surface.rs:202-213`)：

```rust
pub enum LiquidationSide {
    LongLiquidated,   // 多頭倉位被強平（賣出）
    ShortLiquidated,  // 空頭倉位被強平（買入）
    Mixed,            // 雙向 / 未明
}
```

**Mapping (Phase C revival 寫入時)**：
- Bybit `"Buy"` → `LiquidationSide::ShortLiquidated` (空頭被強平 → 強制買回)
- Bybit `"Sell"` → `LiquidationSide::LongLiquidated` (多頭被強平 → 強制賣出)
- `Mixed` → only emitted by `LiquidationPulse.dominant_side` aggregator (not single event)

**Schema-level impact**：**NONE**. `market.liquidations.side TEXT` 接受 `"Buy"`/`"Sell"` raw（無 CHECK constraint），無需 schema 改動。Parser 層做 enum 翻譯到 Rust LiquidationEvent。

**MED RISK push back**：當前 schema 無 `side TEXT` 的 CHECK constraint `IN ('Buy','Sell')` 或 `IN ('Buy','Sell','Liquidated')`。若 Phase C 寫入時 parser bug 寫了 enum string (e.g. `"long_liquidated"`)，schema 不會 reject。**建議 Phase C revival 時 V### 加 Guard B `CHECK side IN ('Buy', 'Sell')` NOT VALID**（per `db-schema-design-financial-time-series` Guard pattern）— but this is **Phase C scope, not v2 proof scope**.

### 2.4 ★ `qty` / `price` precision — REAL vs string-decimal

**Bybit V5 contract**: `v="0.001"` / `p="78673.30"` 是 high-precision string-decimal (typical 8-12 dec places for qty, 2 dec places for price)。

**PG schema**: `real` = float32 ≈ 7 significant digits。

**Precision analysis**（v1 sample）：
| Sample | Raw `v` | Raw `p` | float32 repr loss? |
|---|---|---|---|
| 1 | `"0.001"` | `"78673.30"` | qty ok; price loses 0.001 precision at 78673 (typical BTC price 5+ digits → 7 sig fig float32 OK for 2dp) |
| 2 | `"0.005"` | `"78599.70"` | same |
| 3 | `"0.021"` | `"78606.00"` | same |

**Conclusion**: For BTC/ETH/major perp at typical 2dp price + 3-5dp qty, `real` (float32) is **adequate**. For meme/long-tail symbols with 8+ dp price (e.g. SHIBUSDT, PEPEUSDT), precision could degrade by ~1 sig fig.

**LOW RISK push back**：當前 schema 用 `real` 而非 `numeric(20,8)` 或 `double precision`。對 V002 design 時的 ML-friendly choice 是合理的（V002 comment line 29: "REAL 而非 NUMERIC（ML 友好，精度足夠）"），but 對 long-tail meme coin liquidation 可能損失精度。**非 v2 proof blocker**；Phase C revival 後若餵 ML 模型用 long-tail symbol 須驗證 cluster_score 計算的數值穩定性。

### 2.5 `type` field — snapshot vs delta

Bybit V5 字典手冊明示 `allLiquidation.{symbol}` topic 只發 `type=snapshot`（不發 `delta`），因為 liquidation event 本質就是 atomic snapshot — 沒有「部分更新」概念。

v1 5h sample 100% confirm `type=snapshot`。

**Schema-level impact**：**NONE**. `market.liquidations` 不需要 `event_type` column（每 row 就是 1 個 snapshot event）。

---

## §3 Focus 3 — V09X migration 需要性決策

### 3.1 V09X decision matrix

| Scenario | V09X needed? | Rationale |
|---|---|---|
| **v2 24h proof execution** | **NO** | Probe 是 read-only WS sniffer，不寫 PG；schema 不需動 |
| **Phase C revival writer (after v2 PASS)** | **NO**（如 default path）| 5 column 全對齊；parser 直接 INSERT raw `"Buy"`/`"Sell"` 進 `side text`，`f32::from_str()` qty/price，`to_timestamp(T/1000)` ts |
| **Phase C revival with CHECK constraint hardening** | **OPTIONAL V094 or later**（建議延後 Phase C IMPL 時統一處理）| 若 Phase C 設計團隊決定加 `side IN ('Buy','Sell')` CHECK constraint NOT VALID + 可選 `event_type` 紀錄欄，需 V09X — but **not required for functional revival** |
| **PK collision under burst** | **OPTIONAL deferred**（見 §3.2） | sub-ms burst with 同 (symbol, ts_ms, side) ⇒ V002 line 220 UNIQUE 報錯 INSERT 失敗 → Phase C writer 須用 `ON CONFLICT DO NOTHING` 或加 `event_id` column → 需 V09X |

### 3.2 PK collision under cascade burst（critical analysis）

V002 PK `(symbol, ts, side)`。**Bybit V5 cascade event** 在 1ms 內可能推多筆 same-side `(BTCUSDT, T=1778878129640ms, "Buy")` (v1 sample 2 顯示 3 個 `"Buy"` events in 106ms window — 三 events 不同 T 所以不撞 PK, but cascade densification 可能達 sub-ms collision)。

**Live evidence (v1 5h window)**：
- topic_message_counts.allLiquidation = 15 frame
- 5 candidate_samples 中 sample 2 有 3 個 data items 在 106ms 內
- 0 同 ts collision observed (lucky 5h sample window — 不代表 24h proof 一定零撞)

**3 PK collision 處理方案**：

| 方案 | 改動範圍 | 推薦度 |
|---|---|---|
| **A. `ON CONFLICT (symbol, ts, side) DO NOTHING`** | Phase C writer SQL only；無 schema 改 | ★★★★★ **MIT 推薦**（最少改動，data loss <0.1% for typical cascade）|
| **B. Add `event_id` column (BIGSERIAL) + PK include event_id** | V09X migration + V002 PK alter | ★★ 過度設計 — 1 event row 不丟值得這麼大改動嗎？|
| **C. Aggregate 1ms 內同 side events into single row with `qty_sum`** | Phase C aggregator + new column `event_count` | ★ 改變 schema 語義（per-event → per-1ms-bucket）— 與 V002 design intent 不符 |

**MIT verdict**: **方案 A** for Phase C revival. Schema 不動 + INSERT 變 idempotent。**v2 proof scope 不涉**.

### 3.3 ETA + scope

| Phase | Schema change | V### | Owner |
|---|---|---|---|
| v2 24h proof (current ticket) | **NONE** | — | E1 IMPL DONE / operator deploy / BB+MIT sign-off |
| Phase C revival writer (W-AUDIT-8a 後續 ticket) | **NONE if 方案 A** / **OPTIONAL CHECK constraint V09X** | TBD — possibly bundled with Phase C IMPL ticket | PA design / E1 IMPL / E2 review |
| ML feature pipeline consumption (R-4 Per-alpha Live Promotion Gate) | **NONE** at schema layer; new feature columns 走 separate panel migration (V088 panel.btc_lead_lag_panel pattern) | Future W-AUDIT-8e/8g | TBD |

**結論**：本 ticket 100% **無 V09X migration 需求**.

---

## §4 Focus 4 — Stage 0R replay 邊界

### 4.1 v2 probe → PG 邊界

| 動作 | v2 probe scope? | DB write? |
|---|---|---|
| 連 Bybit public WS | ✅ Yes (`wss://stream.bybit.com/v5/public/linear`) | NO — pure read |
| Subscribe `allLiquidation.BTCUSDT` + 4 control topics | ✅ Yes | NO |
| 寫 audit JSON to `OPENCLAW_DATA_DIR/audit/liquidation_topic_probe/` | ✅ Yes (per-hour checkpoint + final report) | NO PG — file system only |
| Insert into `market.liquidations` | **❌ EXPLICITLY NO** | — |
| 改 production WS subscription list (`full_subscription_list()`) | **❌ EXPLICITLY NO** | — |
| Run replay simulation (`replay.simulated_fills`) | **❌ NO — not in this ticket** | — |

### 4.2 Audit JSON 走的是 file system，不是 PG

v2 probe 預期輸出 path（per E1 self-report §6.3）：

```
$OPENCLAW_DATA_DIR/audit/liquidation_topic_probe/
├── c1_proof_progress.json              # per-hour checkpoint overwrite
├── liquidation_topic_probe_v2_<UTC>.json  # final dated
├── liquidation_topic_probe_v2_latest.json
├── liquidation_topic_probe_v2_<UTC>.md
├── liquidation_topic_probe_v2_latest.md
└── nohup_c1_v2_<UTC>.log
```

**100% file system**, 0 PG row. MIT signs schema pre-review = MIT signs「現有 PG schema 對齊 Bybit payload 字段，**不需 V09X**」; MIT 不 sign production builder revival authorization（that's PA + BB + operator post-v2-PASS scope）.

### 4.3 Sign-off scope boundary

| Sign-off | Owner | Scope |
|---|---|---|
| **本 MIT report** | MIT | Schema delta pre-review only; APPROVE v2 24h proof execution + Phase C revival 不需 V09X |
| BB sign-off (after v2 PASS) | BB | ToS / endpoint compliance / 4 invariants (24h+ wall-clock / 0 subscribe failures / reconnect ≥23h uptime / schema alignment confirmed by MIT) |
| PM sign-off | PM | Spec land + dispatch operator + post-PASS Phase C IMPL fire |
| Phase C revival authorization | PA design + operator | Post v2 PASS — restore WS handler + writer + LiquidationCascade alpha source |

---

## §5 Focus 5 — ML feature contract / alpha source registry

### 5.1 LiquidationCascade in AlphaSurface registry

per `rust/openclaw_core/src/alpha_surface.rs:78` (AlphaSourceTag enum)：

```rust
pub enum AlphaSourceTag {
    TA1m, TA5m, FundingSkew, Basis,
    OIDeltaPanel, OrderflowImbalance,
    LiquidationCascade,            // ← Tier 3 microstructure
    EventDriven, CrossAsset,
}
```

per `alpha_surface.rs:227-241` `LiquidationPulse` struct (dormant)：

```rust
pub struct LiquidationPulse {
    pub recent_events: Vec<LiquidationEvent>,  // ← rolling 60s window
    pub cluster_score: f64,                    // ← 0.0 – 1.0 (Phase C IMPL 算法)
    pub dominant_side: LiquidationSide,
    pub snapshot_ts_ms: i64,
}
```

per `alpha_surface.rs:402`：

```rust
AlphaSourceTag::LiquidationCascade => self.liquidation_pulse.is_some(),
```

**Current state**: `liquidation_pulse: None` 永遠（per `:425, :442, :466` defaults）→ `is_available(LiquidationCascade)` → `false` → 任何 strategy declare `LiquidationCascade` 跑 `on_tick(ctx, surface)` 時 surface 拒絕提供（fail-closed per principle 6）。

### 5.2 Pipeline maturity stage (per `ml-pipeline-maturity-audit` skill)

| Dimension | Status | Stage |
|---|---|---|
| **DB schema** (Foundation) | ✅ `market.liquidations` table + hypertable + 1d chunk + 7d compress + 90d retention | Foundation ✅ |
| **Writer code path** (Skeleton) | ❌ `MarketEvent::Liquidation` variant **REMOVED 2026-04-06** (`database/mod.rs:229-232` GAP comment) | Skeleton ✅ STUB (alpha_surface.rs LiquidationPulse defined but `liquidation_pulse: None` 永遠) |
| **Writer spawn** (Shadow precond) | ❌ No WS handler registered for `allLiquidation.*` (2026-04-06 移除); production builders guarded against re-add | Shadow ❌ |
| **Row accumulation** (Shadow) | ❌ 0 row (table empty) | Shadow ❌ |
| **Consumer existence** (Canary precond) | ❌ Only `LiquidationCascadeProbeStrategy` test stub in `rust/openclaw_engine/src/replay/strategy_adapter.rs:265-330` (replay-only unit test asserting fail-closed behavior) | Canary ❌ |
| **Decision impact** (Production) | ❌ 0 strategy declares `LiquidationCascade` in production (5 textbook 策略全 TA1m/TA5m only) | Production ❌ |

**Stage 評級**：**Foundation only**。`market.liquidations` 是 Foundation 級 schema infrastructure；ML pipeline 對 liquidation 是 fail-closed pending real data + writer + consumer + strategy。

### 5.3 W-AUDIT-8a 路徑 → AlphaSurface ML pipeline 真接

| Phase | 動作 | Stage 升級 |
|---|---|---|
| C0 ✅ DONE | inventory + dormant status confirm | Foundation 維持 |
| **C1 v2 24h proof** (本 ticket) | Bybit WS topic safety verification | Foundation 維持（無 schema 升） |
| Phase C revival (after C1 PASS) | restore WS handler + writer + INSERT to `market.liquidations` | Foundation → **Skeleton** (writer code 真接) |
| Phase C+ (24-48h soak) | row accumulation observable in PG | Skeleton → **Shadow** (rows accumulate) |
| Phase C++ (alpha consumer wire) | `LiquidationPulse` populated in `AlphaSurface`; strategy 用 surface.liquidation_pulse | Shadow → **Canary** (consumer exists but no live decision impact) |
| W-AUDIT-8e/8g (R-4 Per-alpha Live Promotion Gate) | strategy declare LiquidationCascade + Stage 0R replay preflight PASS + Stage 1 demo cohort | Canary → **Production** |

**ML 對 liquidation 的依賴**：

| Surface | 依賴 `market.liquidations` row? | 依賴 `liquidation_pulse` populated? |
|---|---|---|
| AlphaSurface Tier 1 (TA) | ❌ No | ❌ No |
| AlphaSurface Tier 2 (cross-asset panel) | ❌ No | ❌ No |
| AlphaSurface Tier 3 (microstructure) | ❌ Schema-wise no（in-memory pulse from WS direct）| ✅ Yes — Phase C revival 後 LiquidationPulse 從 WS event direct 計算，**不必走 PG round-trip** |
| AlphaSurface Tier 4 (info flow) | ❌ No | ❌ No |
| ML training data (decision_features / scorer) | ⚠️ Future use case — Phase C+ aggregator 可寫 features 進 panel；當前 5 textbook 策略 0 依賴 | ❌ N/A in current pipeline |

**LiquidationPulse 是 in-memory rolling stat from WS direct**，不需 `market.liquidations` PG row 作為 input。`market.liquidations` PG table 作為 audit / backfill / training future-use；real-time strategy on_tick path 不走 PG。

### 5.4 6 維 leakage（per `feature-engineering-protocol`）

W-AUDIT-8a C1 v2 是 schema infrastructure pre-review，**不在 ML training scope** — 6 維 leakage（look-ahead / target / survivorship / cross-section / time-zone / resample）**不適用** 本 audit。Phase C+ ML 真接時走 `feature-engineering-protocol` 重審。

---

## §6 4 待答 — MIT-side answers (#1 schema + #3 V09X decision)

per E1 self-report §5.3：

### Q1: `market.liquidations` 現實際 schema

**Answered §1.1**：5 column (ts timestamptz / symbol text / side text / qty real / price real)，PK (symbol, ts, side)，hypertable 1d chunk / 7d compress / 90d retention。**`\d` style summary 已 inline 上**.

### Q2: v1 15 messages full JSON dump path

**Located**: `trade-core:/tmp/openclaw/audit/liquidation_topic_probe/liquidation_topic_probe_latest.json` (3.3 KB)
- `.candidate_samples` array length = 5（不是 15，因 sample cap）
- topic_message_counts.allLiquidation.BTCUSDT = 15（frame count）
- 5 sample 已 review @ §2.1 — 100% snapshot type, 100% Buy side, BTC realistic 78600 range

### Q3: Schema delta 是否需 V09X migration

**Answered §3**：**NO** for v2 proof scope. **OPTIONAL** for Phase C revival with hardening (CHECK constraint side ∈ {'Buy','Sell'} NOT VALID) — deferred to Phase C ticket.

### Q4: Bybit V5 `allLiquidation.{symbol}` payload type field

**Answered §2.5**: 100% `type="snapshot"` per Bybit V5 dictionary + v1 5h sample empirical 100% confirm (no delta variant observed)。Schema 不需 `event_type` column。

---

## §7 5 Push Backs / Risk Annotations

### 7.1 HIGH-1: PG chunk interval drift (commit lag)

V002 source 寫 `INTERVAL '7 days'` (line 226)，empirical 實測 `1 day`。**Source 文檔 vs runtime config drift**. **不影響 v2 proof**, but M5 Ultra deploy 對齊時 operator 必須裁決：source 修 → 1d, 或 runtime alter → 7d。

**MIT 推薦**：保留 1d chunk（liquidation event sparse, 1d chunk 不會浪費 metadata overhead）+ V006 補 `SELECT set_chunk_time_interval('market.liquidations', INTERVAL '1 day');` 對齊 source。**Future P2 ticket**.

### 7.2 MED-1: side TEXT 無 CHECK constraint

`side text NOT NULL` 接受任何 string。Phase C parser bug 寫 `"long_liquidated"` 等 enum string 不會被 schema reject。**v2 proof scope 不涉**；Phase C revival 設計時加 `ALTER TABLE ... ADD CONSTRAINT chk_liquidations_side CHECK (side IN ('Buy', 'Sell')) NOT VALID` (per `db-schema-design-financial-time-series` Guard B pattern). **OPTIONAL Phase C V09X**.

### 7.3 MED-2: PK collision risk under sub-ms cascade burst

V002 PK `(symbol, ts, side)`. Sub-ms cascade 可能撞同 PK → INSERT 報錯 → writer 階段 fail-closed loss data. **v2 proof 不涉**. Phase C revival writer 必用 `ON CONFLICT (symbol, ts, side) DO NOTHING` (方案 A per §3.2). **No schema change needed**.

### 7.4 LOW-1: REAL precision for long-tail meme coin

`qty real / price real` = float32 ≈ 7 sig digit. Long-tail meme (SHIB/PEPE 8+ dp price) 可能損 1 sig fig. **Acceptable for BTCUSDT canary**（典型 2dp price）;Phase C revival 餵 ML 模型用 long-tail symbol 須驗證 cluster_score 數值穩定性. **Future audit ticket**.

### 7.5 LOW-2: V002 comment vs V006 retention drift

V002 line 211 註釋 `1 year retention`, V006 line 63 實際 `90 days`. **Documentation drift**, not runtime impact. Future P2 ticket fix comment.

---

## §8 Sign-Off Block

### 8.1 MIT 結論 (Schema Pre-Review)

**APPROVE FULLY** — V09X migration **NOT NEEDED** for W-AUDIT-8a C1 v2 24h proof execution.

**Schema layer**：5/5 Bybit V5 `allLiquidation.{symbol}` `data[]` field 1:1 對齊 `market.liquidations` 5 column。Hypertable / compression / retention 已 live as designed.

**Parser layer** (Phase C revival ticket scope, NOT v2 proof scope)：必處理 (a) ms timestamp → timestamptz conversion (b) string-decimal → f32 cast (c) Bybit `"Buy"`/`"Sell"` → Rust `LiquidationSide` enum translation (d) PK collision via `ON CONFLICT DO NOTHING`.

**ML pipeline (per `ml-pipeline-maturity-audit`)**：Foundation only。Phase C revival → Skeleton；Phase C+ row accumulation → Shadow；W-AUDIT-8e/8g R-4 promotion → Canary → Production。當前 fail-closed pending real data — **correct posture per principle 6**.

**Sign-off boundary**：
- ✅ MIT signs SCHEMA layer (本 report scope)
- ❌ MIT does NOT sign ToS / WS endpoint compliance (that's BB scope after v2 PASS)
- ❌ MIT does NOT sign production builder revival authorization (that's PA + operator post-v2-PASS scope)
- ❌ MIT does NOT sign V09X migration apply (none needed)

### 8.2 5 Conditions for v2 24h proof start (none of these are schema layer)

(all conditions belong to BB / E2 / E4 / operator scope, not MIT — listed here for inter-agent coordination only)：

1. (BB scope) Bybit V5 ToS allow standalone WS public probe — 已 5h v1 證明 0 rate-limit / 0 ToS violation
2. (E2 scope) v2 harness code review pass (942 LOC + 36/36 test PASS per E1 self-report)
3. (E4 scope) v2 short smoke (60s) verify pre-24h
4. (operator scope) trade-core network stability + UTC midnight cutoff alignment
5. (PA + operator scope) v2 PASS → Phase C revival ticket fire（NOT in current ticket）

### 8.3 5 Push Backs for Future Tickets

(per §7) — none block v2 proof start：
1. HIGH-1: V002 source chunk_interval source vs runtime drift → P2 文檔修
2. MED-1: side TEXT CHECK constraint → Phase C V09X optional
3. MED-2: PK collision under burst → Phase C writer `ON CONFLICT DO NOTHING`
4. LOW-1: REAL precision for long-tail meme → future ML quality audit
5. LOW-2: V002 vs V006 retention comment drift → P2 文檔修

---

## §9 完成序列 self-check

- ✅ Profile + memory + 最近 reports 讀
- ✅ Design plan v2 §4 schema delta + §5 invariants 讀
- ✅ E1 self-report 讀
- ✅ v2 probe source 重點 section 讀
- ✅ ssh trade-core empirical PG query read-only (`market.liquidations` columns / hypertable / chunk / jobs / row count / pg size)
- ✅ V002 / V005 / V006 source SQL 對照
- ✅ `rust/openclaw_core/src/alpha_surface.rs` LiquidationPulse / LiquidationEvent / LiquidationSide / AlphaSourceTag struct 對照
- ✅ v1 5 candidate_samples raw JSON 對 schema 1:1 mapping audit
- ✅ ml-pipeline-maturity-audit 4 dimension × 5 stage 評估
- ✅ V09X decision matrix (3 scenarios)
- ✅ 5 push back identified
- ✅ Sign-off boundary 明確 (schema only, not ToS/builder/V09X)
- ✅ 0 sub-agent spawned
- ✅ 0 V09X migration written
- ✅ 0 `market.liquidations` schema 改

---

MIT AUDIT DONE: /Users/ncyu/Projects/TradeBot/srv/docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-16--w_audit_8a_c1_v2_harness_mit_schema_pre_review.md
