---
spec: V116 — M13 AssetClass / Venue Dim Schema Reserve (Placeholder Y2+ Phase)
date: 2026-05-21
author: PA Sprint 1A-δ (single sub-agent dispatch — schema placeholder reserve)
phase: v5.8 Sprint 1A-δ schema reserve
status: SPEC-PLACEHOLDER（frontmatter + 大綱 reserve only；不寫 V116.sql；不在 Mac 跑 SQL；不執行 PG；full DDL 在 M13 Y2+ phase land）
parent specs:
  - srv/docs/adr/0040-multi-venue-gate-spec.md (ADR-0040 multi-venue gate spec — 257 行；本 V116 reserve dim table 對應)
  - srv/docs/execution_plan/2026-05-21--m13_asset_class_venue_design_spec.md (M13 DESIGN spec — 同 Sprint 1A-δ deliverable；本 V116 為其 schema 反映)
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M13 (line 460-487)
mirror precedent:
  - srv/docs/execution_plan/2026-05-21--v113_m7_decay_signals_schema_spec.md (V113 placeholder + full DDL pattern 範式)
  - srv/docs/execution_plan/2026-05-21--v110_m6_reward_weight_history_schema_spec.md (V110 placeholder spec 結構範式)
scope: V116 placeholder spec only — 不寫 V116.sql；不在 Mac 跑 SQL；不執行 PG；full DDL land in M13 Y2+ phase
---

# V116 M13 AssetClass / Venue Dim Schema Migration Spec (PLACEHOLDER)

## §0 TL;DR

- **V116 新增 2 個 dim table**（per ADR-0040 + M13 DESIGN spec）：`reference.asset_class_dim` + `reference.venue_dim`
- **Hypertable 判斷：NO**（regular dim table；low cardinality — `asset_class_dim` ~5 rows / `venue_dim` ~5 rows；無 hypertable 需求）
- **既有資料種子 (Y1 baseline data)**：
  - `asset_class_dim`：(Perp / Spot / Option / Earn) **4 row Y1 active**；Structured **Y3+ reserved row** (`activation_aum_threshold_usd=75000`)
  - `venue_dim`：(BybitPerp / BybitSpot / BybitOption) **3 row Y1 active**；BinancePerp **Y2 market-data only / Y3+ trade defer** (`venue_market_data_only=TRUE`, `venue_trade_enabled=FALSE`, `activation_aum_threshold_usd=50000`)；BinanceOption **Y3+ reserved** (`venue_trade_enabled=FALSE`, `activation_aum_threshold_usd=75000`)
  - **DEX / Hyperliquid 不插入** （per ADR-0040 Decision 4 hardcode reject + ADR-0033 Decision 3 + CLAUDE.md §一 Bybit-only）
- **Sprint 1A-δ scope**：placeholder reserve only — frontmatter + 大綱；不寫 V116.sql；full DDL 在 M13 Y2+ phase（per v5.8 §3.2 Sprint 排期）
- **依賴**：無 V### prerequisite（純 dim table；不 FK 到其他 learning table）

---

## §1 Background

### 1.1 v5.8 §2 M13 module + ADR-0040 source

per M13 DESIGN spec §2 + §3 + ADR-0040 Decision 4 venue enum hardcode：

- AssetClass enum 5 variants：Perp / Spot / Option / Earn (Y1 active) + Structured (Y3+ reserved)
- Venue enum 5 variants：BybitPerp / BybitSpot / BybitOption (Y1 active) + BinancePerp (Y2 market-data only / Y3+ trade defer) + BinanceOption (Y3+ reserved)
- DEX / Hyperliquid hardcode reject（不在 enum + 不在 dim table）

V116 dim table 作為 **reference / lookup table**：
- 為應用層提供 venue / asset class 屬性查詢（venue_trade_enabled / venue_market_data_only / activation_aum_threshold_usd）
- 為 risk / governance gate 提供 `approved_per_5gate` 狀態追蹤
- 為未來 Y3+ Binance trade enable 提供 dim table updated source（ADR + DDL update 同步落地）

### 1.2 為什麼 placeholder spec 在 Sprint 1A-δ 落 + full DDL 延後 Y2+

per M13 DESIGN spec §1.4 interface reservation scope：

- Sprint 1A-δ 階段 = enum + Display + FromStr + serde derive only；無 venue dispatch logic
- 對應 V116 dim table = **schema reserve only**；無實際 INSERT statement；無 Y2+ Binance market-data ingestion 路徑接線
- Y2+ phase 才 land full DDL + initial Y1 baseline INSERT
- 與 V113 (M7) / V112 (M1 LAL) 不同：V116 不在 Sprint 1A-β / γ 期間落 full DDL；走 Sprint 1A-δ placeholder + Y2+ phase IMPL

### 1.3 Audit 來源

- PA dispatch consolidation：Sprint 1A-δ deliverable 行 165「M13 AssetClass + Venue enum (DEX/Hyperliquid hardcode 拒絕) + ADR-0040 (multi-venue gate spec + Y3+ Binance trade enable) + V116 reserved」
- ADR-0040 257 行 5 Decisions（land 2026-05-21）
- M13 DESIGN spec §2 + §3 enum 5 variants + §6 IMPL dispatch brief

---

## §2 Schema Outline (placeholder)

### 2.1 `reference.asset_class_dim` (regular dim table)

**Tables 大綱**：
- PK: `asset_class_id BIGSERIAL`
- Columns 大綱（~9 fields）：
  - `asset_class_id BIGSERIAL PRIMARY KEY`
  - `asset_class_name TEXT NOT NULL UNIQUE` (對齊 Rust `AssetClass` enum variant name — `'Perp'` / `'Spot'` / `'Option'` / `'Earn'` / `'Structured'`)
  - `availability_phase TEXT NOT NULL` (ENUM: `'Y1_active'` / `'Y2_active'` / `'Y3+_reserved'`)
  - `activation_aum_threshold_usd NUMERIC(18,2) NULL` (per v5.8 §5 capital-tier ladder；Y1 active = NULL；Y3+ reserved = 75000)
  - `approved_per_5gate BOOLEAN NOT NULL DEFAULT FALSE` (per ADR-0040 Decision 2 venue-aware 5-gate；Y1 active = TRUE for trading；Y3+ reserved = FALSE pending Operator approval)
  - `description TEXT NULL` (e.g. "Perpetual futures Bybit USDT perp")
  - `corresponding_adr TEXT NULL` (e.g. "ADR-0006 + ADR-0031 + ADR-0032 + ADR-0040")
  - `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
  - `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()` (per dim table best practice for audit；Y3+ enable 後 update timestamp)

**Constraints 大綱**：
- CHECK: `asset_class_name` ∈ 5 值 ENUM (`'Perp'` / `'Spot'` / `'Option'` / `'Earn'` / `'Structured'`)
- CHECK: `availability_phase` ∈ 3 值 ENUM (`'Y1_active'` / `'Y2_active'` / `'Y3+_reserved'`)
- CHECK: `activation_aum_threshold_usd >= 0 OR activation_aum_threshold_usd IS NULL`
- NOT NULL: asset_class_name, availability_phase, approved_per_5gate, created_at, updated_at
- UNIQUE: asset_class_name (single source of truth per asset class)

**Indexes 大綱**：
- PK index 內建
- `(availability_phase, approved_per_5gate)` partial index — `WHERE approved_per_5gate=TRUE` for runtime lookup

### 2.2 `reference.venue_dim` (regular dim table)

**Tables 大綱**：
- PK: `venue_id BIGSERIAL`
- Columns 大綱（~12 fields）：
  - `venue_id BIGSERIAL PRIMARY KEY`
  - `venue_name TEXT NOT NULL UNIQUE` (對齊 Rust `Venue` enum variant name — `'BybitPerp'` / `'BybitSpot'` / `'BybitOption'` / `'BinancePerp'` / `'BinanceOption'`)
  - `exchange_name TEXT NOT NULL` (e.g. `'Bybit'` / `'Binance'`)
  - `asset_class_id BIGINT NOT NULL REFERENCES reference.asset_class_dim(asset_class_id)` (e.g. BybitPerp → Perp asset_class_id)
  - `availability_phase TEXT NOT NULL` (ENUM: `'Y1_active'` / `'Y2_market_data_only'` / `'Y3+_reserved'`)
  - `venue_trade_enabled BOOLEAN NOT NULL DEFAULT FALSE` (per ADR-0040 Decision 1+2；Y1 active = TRUE for Bybit；Y2 market-data only + Y3+ reserved = FALSE)
  - `venue_market_data_only BOOLEAN NOT NULL DEFAULT FALSE` (per ADR-0033 §Decision 1 Y1 Binance market-data approved + ADR-0040 Y2 onwards extend；BinancePerp Y2 = TRUE)
  - `approved_per_5gate BOOLEAN NOT NULL DEFAULT FALSE` (per ADR-0040 Decision 2 venue-aware 5-gate；Y1 Bybit = TRUE；Y3+ Binance = FALSE pending Y3+ evaluation)
  - `activation_aum_threshold_usd NUMERIC(18,2) NULL` (per ADR-0040 Decision 3 + v5.8 §5；BinancePerp Y3+ trade enable = 50000；BinanceOption Y3+ = 75000)
  - `secret_slot_path TEXT NOT NULL` (per ADR-0040 Decision 2 per-venue secret slot；Bybit = `'$OPENCLAW_SECRETS_DIR/api_key'`；Binance = `'$OPENCLAW_SECRETS_DIR/external/binance/api_key'`)
  - `corresponding_adr TEXT NULL` (e.g. "ADR-0006 + ADR-0033 + ADR-0040")
  - `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
  - `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

**Constraints 大綱**：
- CHECK: `venue_name` ∈ 5 值 ENUM (`'BybitPerp'` / `'BybitSpot'` / `'BybitOption'` / `'BinancePerp'` / `'BinanceOption'`)
- CHECK: `exchange_name` ∈ 2 值 ENUM (`'Bybit'` / `'Binance'`) — per ADR-0040 Decision 4 enum hardcode；無 DEX / Hyperliquid
- CHECK: `availability_phase` ∈ 3 值 ENUM (`'Y1_active'` / `'Y2_market_data_only'` / `'Y3+_reserved'`)
- CHECK: `activation_aum_threshold_usd >= 0 OR activation_aum_threshold_usd IS NULL`
- CHECK: `venue_trade_enabled=FALSE OR (venue_trade_enabled=TRUE AND approved_per_5gate=TRUE)` — fail-closed schema invariant per ADR-0040 Decision 2
- CHECK: `venue_market_data_only=FALSE OR venue_trade_enabled=FALSE` — market_data_only AND trade_enabled mutually exclusive
- NOT NULL: venue_name, exchange_name, asset_class_id, availability_phase, venue_trade_enabled, venue_market_data_only, approved_per_5gate, secret_slot_path, created_at, updated_at
- UNIQUE: venue_name (single source of truth per venue)
- FK: asset_class_id → reference.asset_class_dim(asset_class_id)

**Indexes 大綱**：
- PK index 內建
- `(venue_trade_enabled, approved_per_5gate)` partial index — `WHERE venue_trade_enabled=TRUE AND approved_per_5gate=TRUE` for runtime trading gate lookup
- `(exchange_name, availability_phase)` for cross-venue aggregation queries
- `(asset_class_id)` for asset class → venue lookup join

### 2.3 ENUM 列表（per ADR-0040 Decision 4 + M13 DESIGN spec §2 + §3）

- `asset_class_name` ENUM 5 值 (`'Perp'` / `'Spot'` / `'Option'` / `'Earn'` / `'Structured'`) — 對齊 M13 DESIGN spec §2.1
- `venue_name` ENUM 5 值 (`'BybitPerp'` / `'BybitSpot'` / `'BybitOption'` / `'BinancePerp'` / `'BinanceOption'`) — 對齊 M13 DESIGN spec §3.1
- `exchange_name` ENUM 2 值 (`'Bybit'` / `'Binance'`) — per ADR-0040 Decision 4 hardcode (no DEX / Hyperliquid)
- `availability_phase` (asset) ENUM 3 值 (`'Y1_active'` / `'Y2_active'` / `'Y3+_reserved'`)
- `availability_phase` (venue) ENUM 3 值 (`'Y1_active'` / `'Y2_market_data_only'` / `'Y3+_reserved'`)

### 2.4 既有資料種子 (Y1 baseline INSERT — Y2+ phase land)

**Y1 = (BybitPerp / BybitSpot / BybitOption / Perp / Spot / Option / Earn)** active；DEX/Hyperliquid 不插入；BinancePerp Y2 market-data only / Y3+ trade defer；Structured + BinanceOption Y3+ reserved。

具體 INSERT statement 在 M13 Y2+ phase full DDL land；以下為 placeholder 數據對齊：

| Table | Row count | 內容預估 |
|---|---|---|
| `reference.asset_class_dim` | **5 row** | (Perp / Spot / Option / Earn — Y1 active + approved=TRUE) + (Structured — Y3+ reserved + approved=FALSE + activation_aum=75000) |
| `reference.venue_dim` | **5 row** | (BybitPerp / BybitSpot / BybitOption — Y1 active + trade_enabled=TRUE + approved=TRUE) + (BinancePerp — Y2 market-data only + trade_enabled=FALSE + market_data_only=TRUE + activation_aum=50000) + (BinanceOption — Y3+ reserved + trade_enabled=FALSE + market_data_only=FALSE + activation_aum=75000) |

**重要 NOT 插入**：
- ❌ `'Hyperliquid'` / `'Uniswap'` / `'DyDx'` / `'GMX'` / 任何 DEX venue 不插入 venue_dim
- ❌ `'OKX'` / `'Coinbase'` 等其他 CEX 不插入（per ADR-0040 Decision 4 末段「未來開放新 venue 必開新 ADR」）
- ❌ Read-only on-chain RPC query 不創 venue_dim row（per ADR-0033 §Decision 3 例外 — 走 ADR-0031 framework，非 M13 venue dim）

---

## §3 Guard A/B/C Templates 大綱

### Guard A — table existence + FK target 對齊驗證

- 若 2 表已存在：驗 column 完整；缺即 RAISE
- 驗 `reference` schema 存在（V### prerequisite — 不確定 prior V### 是否創 schema；M13 Y2+ phase 驗）
- 驗無循環 FK（venue_dim → asset_class_dim 單向 FK）

### Guard B — 不適用

V116 不 ALTER 既有 column type；本 spec 不設 Guard B 段。

### Guard C — CHECK constraint + ENUM 值齊全 + dim 種子驗證

- `asset_class_name` ENUM 5 值齊全 + 無 DEX/Hyperliquid string
- `venue_name` ENUM 5 值齊全 + 無 DEX/Hyperliquid string
- `exchange_name` ENUM 2 值齊全 (Bybit / Binance only)
- `availability_phase` 2 個 ENUM 各 3 值齊全
- FK constraint `venue_dim.asset_class_id → asset_class_dim.asset_class_id` 真存在
- UNIQUE constraint `venue_name` + `asset_class_name` 真存在
- Schema invariant CHECK `venue_trade_enabled=FALSE OR approved_per_5gate=TRUE` 真存在
- 5 indexes (asset_class_dim + venue_dim) 對齊
- Y1 baseline data INSERT 完成（5 + 5 = 10 row）

---

## §4 Linux PG Empirical Dry-Run Checklist (placeholder)

per M13 Y2+ phase IMPL；本 Sprint 1A-δ 階段不執行；以下為 Y2+ phase 預留 SOP：

### 4.1 必跑 SQL placeholder（M13 Y2+ phase 時 land）

```bash
# Linux only — ssh trade-core
# Round 1: existence reflection (Guard A baseline)
ssh trade-core "psql -d openclaw -c \"SELECT relname FROM pg_class WHERE relname IN ('asset_class_dim','venue_dim') AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname='reference')\""

# Round 2: schema applied (Guard C ENUM + FK + UNIQUE + CHECK)
ssh trade-core "psql -d openclaw -c \"SELECT column_name, data_type FROM information_schema.columns WHERE table_schema='reference' AND table_name='venue_dim' ORDER BY ordinal_position\""

# Round 3: Y1 baseline data 驗 (5 + 5 = 10 row)
ssh trade-core "psql -d openclaw -c \"SELECT venue_name, exchange_name, venue_trade_enabled, venue_market_data_only, approved_per_5gate FROM reference.venue_dim ORDER BY venue_id\""

# Round 4: DEX/Hyperliquid INSERT reject 驗 (empirical INSERT test — schema-level CHECK)
# 例：
# INSERT INTO reference.venue_dim (venue_name, ...) VALUES ('Hyperliquid', ...);
# Expected: ERROR: violates check constraint (CHECK constraint enforcement per ADR-0040 Decision 4)

# Round 5: Schema invariant 驗 (venue_trade_enabled=TRUE without approved_per_5gate=TRUE)
# 例：
# UPDATE reference.venue_dim SET venue_trade_enabled=TRUE WHERE venue_name='BinancePerp' AND approved_per_5gate=FALSE;
# Expected: ERROR: violates check constraint (fail-closed schema invariant)
```

### 4.2 Idempotent 雙跑驗

per V055 5-round loop + V083/V084 incident precedent，V116.sql 必跑兩次：第二次必 0 RAISE / 0 重複 INSERT / 0 重複 CHECK。

### 4.3 Engine restart 實測

per a19797d 教訓：
- `restart_all.sh --rebuild` 後驗 engine.log 無 sqlx panic
- 驗 `_sqlx_migrations.success=t` for V116
- 驗 venue / asset class dim table 可從 Rust IPC query（M13 Y2+ phase 接線後）

---

## §5 Cross-V### Dependencies

per CR-9 cross-V### dependency graph：

| V### | 依賴 | 理由 |
|---|---|---|
| V116 | 無 V### prerequisite | 純 dim table；不 FK 到其他 learning table |
| V116 | `reference` schema 創建 prerequisite | 若 prior V### 未創 `reference` schema，V116 需先 `CREATE SCHEMA IF NOT EXISTS reference` (M13 Y2+ phase 驗) |

**V116 為其他 module 提供 venue / asset class reference**：
- Y3+ Binance trade enable IMPL 期 update `venue_dim.venue_trade_enabled=TRUE WHERE venue_name='BinancePerp'`（per ADR-0040 Decision 3 6 criteria 通過後）
- M12 OrderRouter Sprint 6+ IMPL 可 join `venue_dim` for per-venue routing
- M13 PositionAggregator Sprint 8+ IMPL 可 join `venue_dim` for cross-venue position netting

**Sprint dispatch ordering**：
- Sprint 1A-δ：placeholder spec only（本 spec）
- M13 Y2+ phase：full DDL + Y1 baseline INSERT
- Y3+ Binance trade enable：UPDATE statement land（per Operator approval session）

---

## §6 Cross-References

### 6.1 Parent specs

- **ADR-0040**：`srv/docs/adr/0040-multi-venue-gate-spec.md`（257 行；5 Decisions ADR 權威；本 V116 dim table schema 對應）
- **M13 DESIGN spec**：`srv/docs/execution_plan/2026-05-21--m13_asset_class_venue_design_spec.md`（同 Sprint 1A-δ deliverable；本 V116 為其 schema 反映）
- **v5.8 execution plan**：`srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md` §2 M13 line 460-487
- **PA dispatch consolidation**：`srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-21--v58_dispatch_consolidation.md` §Sprint 1A-δ line 159-167

### 6.2 Mirror precedent

- **V113 (M7) placeholder + full DDL pattern**：`srv/docs/execution_plan/2026-05-21--v113_m7_decay_signals_schema_spec.md`
- **V110 (M6) placeholder pattern**：`srv/docs/execution_plan/2026-05-21--v110_m6_reward_weight_history_schema_spec.md`

### 6.3 ADR cross-ref

- **ADR-0006 Bybit-only baseline**：`srv/docs/adr/0006-bybit-only-exchange.md`（thesis 不變；venue_dim 不含 DEX）
- **ADR-0033 Binance amendment**：`srv/docs/adr/0033-adr-0006-bybit-binance-amendment.md`（§Decision 1 Binance market-data Y1 approved → BinancePerp Y2 market-data only row）
- **ADR-0034 LAL 4 venue change always operator**：venue_dim UPDATE 永遠走 LAL 4
- **CLAUDE.md §一 Bybit-only**：字面立場保留；venue_dim 不含 DEX / Hyperliquid / OKX / Coinbase

### 6.4 Skill cross-ref

- **`srv/.claude/skills/db-schema-design-financial-time-series`**：dim table best practice 對齊（regular table；無 hypertable；audit field updated_at）

---

## §7 Sign-off Table

| Role | Status | Date | Note |
|---|---|---|---|
| Operator | APPROVED-pending-spec-land | 2026-05-21 | 主會話 PM dispatch via PM final verdict §四 D4 + ADR-0040 sign-off |
| PA Drafted (placeholder) | DONE | 2026-05-21 | Placeholder frontmatter + 大綱 reserve + Y1 baseline data 設計 + Guard A/C templates 大綱 + Cross-V### dependency + ADR cross-ref |
| PA Sprint 1A-ε cross-ADR audit | PENDING | — | Sprint 1A-ε integration verify phase；驗 11 ADR cross-ref + V116 dependency graph |
| MIT / E5 consultant verify | PENDING | — | M13 Y2+ phase 才 IMPL full DDL；本 spec 僅 placeholder reserve |
| E1 | PENDING | — | M13 Y2+ phase land full DDL + Y1 baseline INSERT |
| E4 | PENDING | — | M13 Y2+ phase regression after IMPL |
| PM Sign-off | PENDING | — | Sprint 1A-δ closure |

---

**END V116 placeholder spec — Y1 baseline data 設計 + ADR-0040 5 Decisions 對齊；full DDL land in M13 Y2+ phase**

---

Sub-agent dispatch: PA Sprint 1A-δ M13 track
Completion: 2026-05-21
