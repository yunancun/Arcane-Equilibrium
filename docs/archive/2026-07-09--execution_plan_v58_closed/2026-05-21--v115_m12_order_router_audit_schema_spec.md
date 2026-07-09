---
spec: V115 — M12 OrderRouter Adaptive Routing Audit Schema (Sprint 1A-δ placeholder reserve)
date: 2026-05-21
author: PA Sprint 1A-δ M12 track（sibling: M12 DESIGN spec）
phase: v5.8 Sprint 1A-δ schema reserve（placeholder frontmatter + 大綱 only；full DDL land Sprint 6+ IMPL phase per ADR-0039 §Decision 6）
status: SPEC-PLACEHOLDER（frontmatter + 大綱 reserve；不寫 V115.sql；不在 Mac 跑 PG SQL；full DDL 在 Sprint 6+ M12 IMPL phase 期補完）
parent specs:
  - srv/docs/adr/0039-m12-order-router-trait-and-maker-fill-rate-metric.md §Decision 3（V115 三表 audit log candidate schema 候選）
  - srv/docs/execution_plan/2026-05-21--m12_order_router_design_spec.md §4 + §3.4（M12 DESIGN sibling）
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M12 line 425-458
mirror precedent:
  - srv/docs/execution_plan/2026-05-21--v113_m7_decay_signals_schema_spec.md（V113 placeholder spec format range reference）
  - srv/docs/execution_plan/2026-05-21--v107_m11_replay_divergence_log_schema_spec.md（dedup target；本 spec OQ-3）
scope:
  - V115 三表 outline + column draft + hypertable 判斷 + retention / compression 範式 reference
  - 不寫 V115.sql、不寫 SQL DDL 細節（Sprint 6+ M12 IMPL 階段 land per ADR-0039 §Decision 6）
  - 不在 Mac 跑 PG SQL（Linux PG empirical dry-run mandatory per `feedback_v_migration_pg_dry_run`；Sprint 6+ phase）
out-of-scope:
  - 完整 DDL（Sprint 6+ M12 adaptive logic IMPL phase 期 land）
  - sqlx checksum 對齊（Sprint 6+ Linux PG empirical dry-run 期驗）
  - Mac → Linux deploy SOP（per `srv/CLAUDE.md` runtime reality；Sprint 6+ phase）
---

# V115 M12 OrderRouter Adaptive Routing Audit Schema Spec (PLACEHOLDER)

## §0 TL;DR

- **V115 新增 3 個 table**（per ADR-0039 §Decision 3 candidate schema）：
  - Part 1：`routing.order_routing_decisions`（per-route_order() decision audit log；hypertable）
  - Part 2：`routing.maker_fill_rate_30d_snapshots`（每日 EOD maker fill rate snapshot；regular table）
  - Part 3：`routing.routing_tier_transitions`（rebate tier transition event log；regular table）
- **schema namespace**：採 `routing.*`（per M12 DESIGN spec §4.2 提議；分離 routing audit 與 learning data；待 V115 finalize 期確認與 ADR-0039 §Decision 3 `learning.*` candidate 的 reconciliation per OQ-1）
- **依賴**：V094（fills_close_maker_audit existing column 範式 baseline）+ V107（M11 replay_divergence_log dedup target per OQ-3）+ TimescaleDB hypertable infra（Part 1 高頻採樣 mandatory）
- **Hypertable 判斷**：Part 1 = MUST hypertable（execution 級高頻 ~1000-10000 row/day）；Part 2 + Part 3 = regular table
- **Sprint 6+ IMPL phase schedule**：V094 既有 column 對齊 audit → V115 三表 IMPL → Linux PG empirical dry-run → engine restart 實測（per 2026-05-02 sqlx hash drift incident SOP）
- **Sprint 1A-δ scope**：本 placeholder spec frontmatter + 大綱 only；**禁寫 V115.sql / DDL / Mac PG query / sqlx migration**（per `feedback_v_migration_pg_dry_run` + dispatch packet 紅線）

---

## §1 Background

### 1.1 V115 出處 + ADR-0039 §Decision 3 對齊

per ADR-0039 §Decision 3 candidate schema：

- M12 OrderRouter Adaptive Routing Audit Schema 三表 first-class governance artifact（per ADR-0039 §Decision 3）
- BB 5.21 audit push back 增加 `maker_fill_rate_30d` metric → V115 Part 2 schema 對應 30d EOD snapshot
- ADR-0039 §Decision 3 候選 schema 採 `learning.*` namespace；本 spec §4.2 提議 `routing.*`（per OQ-1 reconciliation）

### 1.2 為什麼 Sprint 1A-δ 階段 reserve placeholder（full DDL 留 Sprint 6+）

per ADR-0039 §Decision 6 IMPL phase + M12 DESIGN spec §1.5：

1. **V115 full DDL 必對齊 ADR-0029 trade tape land 後** — Part 1 採樣源依賴 ADR-0029 fill tape + V094 既有 column；Sprint 1A-δ 不可預定 DDL detail
2. **Linux PG empirical dry-run mandatory**（per `feedback_v_migration_pg_dry_run.md` + 2026-05-02 sqlx hash drift incident）— Sprint 6+ phase 才有 capacity 跑 PG 實測
3. **V094 既有 schema audit 必須先做**（per Sprint 6+ MIT IMPL phase）— V094 `close_maker_attempt` + `close_maker_fallback_reason` 是否需 extend `notional_usdt` column 待 Sprint 6 IMPL 期 review（per ADR-0039 OQ-6）
4. **與 V107 (M11 replay_divergence_log) dedup 待 CR-14 finalize**（per ADR-0039 OQ-4）

### 1.3 本 spec 範圍邊界

- ✅ V115 三表 outline + column draft + hypertable 判斷
- ✅ Cross-V### dependency placeholder + Open Q ≥ 3
- ✅ Linux PG empirical dry-run protocol outline（Sprint 6+ phase）
- ✅ Sign-off chain placeholder
- ❌ V115.sql file 寫作（Sprint 6+ M12 IMPL phase E1 工作；本 spec 為 placeholder）
- ❌ Full DDL 細節（Sprint 6+ M12 IMPL phase 期 land）
- ❌ Mac 跑 PG SQL（Linux PG empirical mandatory；Sprint 6+ phase）
- ❌ sqlx migration 寫作（Sprint 6+ M12 IMPL phase E1 工作）

---

## §2 Schema Outline (placeholder)

### 2.1 V115 Part 1 — `routing.order_routing_decisions` (hypertable)

**per-decision audit log；每次 `route_order()` call emit 1 row**

**Tables 大綱**：
- PK 候選：`decision_id UUID NOT NULL`（per ADR-0039 §Decision 3 + per V094 lossy-pk avoidance 範式）
- Hypertable time index：`ts TIMESTAMPTZ NOT NULL`（per TimescaleDB best practice）
- Columns 大綱（11 fields per ADR-0039 §Decision 3 candidate schema）：
  - `decision_id UUID NOT NULL`（per `route_order()` call generated UUID；V115 PK）
  - `ts TIMESTAMPTZ NOT NULL`（hypertable time index）
  - `asset TEXT NOT NULL`（symbol；e.g. 'BTCUSDT'）
  - `venue TEXT NOT NULL`（per VenueId enum：BybitPerp / BybitSpot / BybitOption / BinancePerp / etc.）
  - `maker_taker TEXT NOT NULL CHECK IN ('maker', 'taker')`（chosen route per route_order() decision）
  - `slice_count SMALLINT NOT NULL DEFAULT 1`（1 = single-shot / 2+ = TWAP/iceberg；Sprint 7-8 slicing IMPL 後生效）
  - `slippage_bps_estimated REAL`（from `forecast_slippage()` Sprint 6+ IMPL）
  - `slippage_bps_realized REAL`（post-fill backfilled；nightly cron job per ADR-0039 §Consequences）
  - `rebate_applied BOOLEAN NOT NULL DEFAULT FALSE`
  - `engine_mode TEXT NOT NULL CHECK IN ('paper','demo','live_demo','live','replay')`（per ADR-0005 enum）
  - `route_reason TEXT NOT NULL`（enum：'default_postonly' / 'reverse_snipe_confirmed' / 'urgency_taker' / 'rebate_protection' / 'operator_override'；per ADR-0039 §Decision 4 + M12 DESIGN spec §2.3 RouteReason enum）

**Constraints 大綱**：
- CHECK: `maker_taker IN ('maker', 'taker')`
- CHECK: `engine_mode IN ('paper','demo','live_demo','live','replay')`
- CHECK: `route_reason IN (5 enum values)`
- CHECK: `slice_count BETWEEN 1 AND 100`
- NOT NULL: decision_id, ts, asset, venue, maker_taker, slice_count, rebate_applied, engine_mode, route_reason

**Indexes 大綱**：
- Hypertable time index 內建（`ts`）
- `(ts DESC, asset, venue)` — per-asset routing decision timeline
- `(ts DESC) WHERE route_reason='reverse_snipe_confirmed'` — reverse-snipe audit hot path partial index
- `(decision_id)` — PK lookup（已含 PK index）

### 2.2 V115 Part 2 — `routing.maker_fill_rate_30d_snapshots` (regular table)

**每日 EOD maker fill rate snapshot；per venue × asset_class 維度**

**Tables 大綱**：
- PK 候選：`(snapshot_date, venue, asset_class)` 複合
- Columns 大綱（10 fields per ADR-0039 §Decision 3 candidate schema + M12 DESIGN spec §3.2 MakerFillRateStats struct）：
  - `snapshot_date DATE NOT NULL`
  - `venue TEXT NOT NULL`（per VenueId enum）
  - `asset_class TEXT NOT NULL CHECK IN ('Perp','Spot','Option','Earn','Structured')`（per AssetClass enum per ADR-0040）
  - `window_start_ts TIMESTAMPTZ NOT NULL`（T - 30d）
  - `window_end_ts TIMESTAMPTZ NOT NULL`（T - 0）
  - `maker_fill_notional_usdt REAL NOT NULL`
  - `total_fill_notional_usdt REAL NOT NULL`
  - `maker_fill_ratio REAL NOT NULL`（NaN for cold start <7d）
  - `current_tier TEXT NOT NULL CHECK IN ('Tier1','Tier2','Default','BelowDefault','Provisional','Unknown')`（per M12 DESIGN spec §3.8 6-tier table）
  - `days_in_current_tier INTEGER NOT NULL`

**Constraints 大綱**：
- CHECK: `asset_class IN (5 enum values)`
- CHECK: `current_tier IN (6 enum values)`
- CHECK: `maker_fill_ratio BETWEEN 0.0 AND 1.0 OR maker_fill_ratio = 'NaN'::REAL`（cold start fallback）

**Retention**：365d（per H-22 R4 governance retention 規範；rebate tier 評估走年度級 trend）

**Indexes 大綱**：
- PK 複合 index
- `(venue, asset_class, snapshot_date DESC)` — per-venue × per-asset-class timeline hot path

### 2.3 V115 Part 3 — `routing.routing_tier_transitions` (regular table)

**rebate tier transition event log**

**Tables 大綱**：
- PK 候選：`transition_id UUID NOT NULL`
- Columns 大綱（8 fields per ADR-0039 §Decision 3 candidate schema）：
  - `transition_id UUID NOT NULL`
  - `ts TIMESTAMPTZ NOT NULL`
  - `venue TEXT NOT NULL`
  - `asset_class TEXT NOT NULL`
  - `from_tier TEXT NOT NULL`（per 6-tier enum）
  - `to_tier TEXT NOT NULL`
  - `maker_fill_ratio REAL NOT NULL`
  - `alert_dispatched BOOLEAN NOT NULL DEFAULT FALSE`（M3 HEALTH_WARN dispatched per CR-7 single health authority?）

**Constraints 大綱**：
- CHECK: `from_tier IN (6 enum)`
- CHECK: `to_tier IN (6 enum)`
- CHECK: `from_tier != to_tier`（transition 必跨 tier）

**Indexes 大綱**：
- PK index
- `(ts DESC, venue, asset_class)` — transition timeline hot path
- `(to_tier, ts DESC) WHERE alert_dispatched = FALSE` — pending alert audit partial index

### 2.4 Hypertable 判斷

| Table | Hypertable? | 量級估算 | 理由 |
|---|---|---|---|
| Part 1 `routing.order_routing_decisions` | **MUST hypertable** | ~1000-10000 row/day（per-strategy × per-symbol routing decision frequency）| execution 級高頻；30d chunk + 90-180d retention 設計考慮 |
| Part 2 `routing.maker_fill_rate_30d_snapshots` | regular table | ~3-5 row/day（per venue × asset_class combinations）| 每日 EOD snapshot；量級低；365d retention 無需 hypertable |
| Part 3 `routing.routing_tier_transitions` | regular table | ~10-50 row/yr（rebate tier 不頻繁切換）| 量極低；無需 hypertable |

**Part 1 Hypertable 配置候選（Sprint 6+ IMPL phase 期 land）**：

```sql
-- 概念性配置；Sprint 6+ 才寫真實 SQL
SELECT create_hypertable('routing.order_routing_decisions', 'ts',
    chunk_time_interval => INTERVAL '7 days',
    if_not_exists => TRUE);

ALTER TABLE routing.order_routing_decisions SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'asset, venue',
    timescaledb.compress_orderby = 'ts DESC'
);

SELECT add_compression_policy('routing.order_routing_decisions', INTERVAL '7 days');
SELECT add_retention_policy('routing.order_routing_decisions', INTERVAL '90 days');
-- 90d retention = M11 replay 60d window + 30d post-incident audit buffer
```

### 2.5 Guard A/B/C 範式

per `feedback_v_migration_pg_dry_run.md` + ADR-0010 + ADR-0011：

- **Guard A** — table existence + FK target 對齊驗證
  - 驗 `routing.*` schema 存在；缺即 CREATE SCHEMA IF NOT EXISTS
  - 驗 V094 fills_close_maker_audit 既有 column 存在（per OQ-6 audit 期）
  - 驗 TimescaleDB extension 存在
- **Guard B** — 不適用本 V115（V115 為新表，不 ALTER 既有 column type；本 spec 不設 Guard B 段）
- **Guard C** — CHECK constraint + ENUM + hypertable + retention + compression + index 對齊驗證
  - 三表 8 ENUM 齊全（venue / asset_class / maker_taker / engine_mode / route_reason / current_tier / from_tier / to_tier）
  - Part 1 hypertable + compression policy + retention 90d
  - Part 2 retention 365d
  - Part 3 retention TBD（governance audit 永久或 cleanup 1yr+）
  - Indexes（4 + 1 + 2 = 7）對齊

---

## §3 Cross-V### Dependencies

per CR-9 cross-V### dependency graph：

| V### | 依賴 | 理由 |
|---|---|---|
| V115 | V094 (fills_close_maker_audit) | maker_fill_notional_usdt 計算源；既有 column 範式 baseline |
| V115 | V107 (M11 replay_divergence_log) | dedup OQ-3 per ADR-0039 OQ-4；兩表正交並存；應用層 fuzzy join |
| V115 | V### head（待 Sprint 6+ IMPL 期確認 V### range） | 對齊 V### sequencing |
| V115 | TimescaleDB extension（V096 boundary） | Part 1 hypertable infra prereq |

**Sprint 6+ M12 IMPL phase dispatch ordering**：V094 audit → V115 三表 IMPL → Linux PG empirical dry-run → engine restart 實測

---

## §4 Linux PG Empirical Dry-Run Protocol (deferred to Sprint 6+)

per `feedback_v_migration_pg_dry_run.md` + 2026-05-02 sqlx hash drift incident SOP：

- **Linux PG empirical dry-run mandatory**（Sprint 6+ phase；不在 Mac 跑）
- 必跑 5-round SQL：reflection / schema applied / hypertable verify / compression + retention verify / index verify（per V113 範式）
- Idempotency 雙跑驗（second run 0 row change）
- Engine restart 實測（per `restart_all.sh --rebuild --keep-auth` + 驗 sqlx _sqlx_migrations V115 success=t + engine.log 0 panic）
- 若 sqlx checksum drift → 跑 `helper_scripts/db/repair_migration_checksum` binary（per 2026-05-02 incident SOP）

**Sprint 1A-δ scope = placeholder only；具體 Linux PG dry-run SQL 在 Sprint 6+ V115 IMPL phase E1 工作**。

---

## §5 Open Questions

### OQ-1: V115 schema namespace `routing.*` vs `learning.*`

- ADR-0039 §Decision 3 候選 schema 採 `learning.*`
- 本 spec + M12 DESIGN spec §4.2 提議改 `routing.*` 分離 routing audit 與 learning data
- 理由：`learning.*` 屬學習層（hypothesis registry / pre-registration / earn audit per V103）；`routing.*` 是 execution 層 audit
- **待 Sprint 6+ M12 IMPL phase + MIT review**：採 `routing.*` 還是 `learning.*`？
- **Owner**：MIT Sprint 6+ M12 IMPL phase 期決議

### OQ-2: V094 既有 schema 是否需 extend `notional_usdt` column

- V094 既有 `close_maker_attempt boolean NOT NULL` + `close_maker_fallback_reason text` enum 10 值
- V115 Part 2 計算分子 / 分母依賴 `notional_usdt` field；既有 fills schema 是否含？
- 若不含 → V### EXTEND 補 V094 schema（per ADR-0010 + Guard B 範式）
- **待 Sprint 6+ MIT review**：V094 既有 schema audit + 視需要 EXTEND
- **Owner**：MIT Sprint 6+ M12 IMPL phase 期 audit

### OQ-3: V115 與 V107（M11 replay_divergence_log）dedup

per ADR-0039 OQ-4：

- V107 是 M11 replay 結果比對 log；V115 是 M12 routing decision audit log
- 兩表正交並存；無 explicit FK
- Replay 階段透過 `asset + ts ± window` 做 fuzzy join；CR-14 review 後決定是否加 explicit cross-reference column
- V115 `decision_id` 在 M11 replay 時可作 join key
- **待 CR-14 finalize + PA Sprint 6+ M12 IMPL phase review**

### OQ-4: Part 1 retention 90d vs 180d

- 90d window 涵蓋 M11 replay 60d + 30d post-incident audit buffer
- 180d window 對齊 V113 decay_signals retention（per V113 spec §2.5）
- 路由 audit log 體量大；長 retention 影響 PG storage
- **建議起點**：90d；Sprint 6+ IMPL 期視 actual storage growth + audit query frequency 決定

### OQ-5: Part 2 hypertable 必要性

- Part 2 量級低（3-5 row/day × 365d = ~1.8k row/yr per venue × asset_class combinations）
- 不需 hypertable；regular table + PK index 足夠
- **建議起點**：regular table（per §2.4 表）；Sprint 6+ IMPL 期確認

### OQ-6: Part 3 retention 策略

- rebate tier transition log 是 governance event
- 不頻繁切換（~10-50 row/yr）
- governance audit 通常永久保留
- **建議起點**：無 retention policy（永久保留）；Sprint 6+ IMPL 期視 governance policy + PG storage 決定

---

## §6 Cross-References

- **ADR-0039**：`srv/docs/adr/0039-m12-order-router-trait-and-maker-fill-rate-metric.md`（§Decision 3 V115 candidate schema authoritative source）
- **M12 DESIGN spec (sibling)**：`srv/docs/execution_plan/2026-05-21--m12_order_router_design_spec.md`（M12 OrderRouter trait DESIGN partial；本 V115 spec sibling）
- **v5.8 §2 M12**：`srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md` line 425-458
- **V094 (fills_close_maker_audit)**：`srv/sql/migrations/V094__fills_close_maker_audit.sql`（既有 column 範式 baseline）
- **V107 (M11 replay_divergence_log)**：dedup target；per ADR-0039 OQ-4 + 本 spec OQ-3
- **V113 (M7 decay_signals)**：placeholder spec format reference；`srv/docs/execution_plan/2026-05-21--v113_m7_decay_signals_schema_spec.md`
- **ADR-0010 (TimescaleDB hypertable + Guard migrations)**：`srv/docs/adr/0010-timescale-hypertable-with-guard-migrations.md`
- **ADR-0011 (V-migration PG dry-run mandatory)**：`srv/docs/adr/0011-v-migration-linux-pg-dry-run-mandatory.md`
- **ADR-0029 (market.public_trades + L2 snapshot)**：`srv/docs/adr/0029-market-trade-tape-and-orderbook-l2-storage-policy.md`（Part 1 採樣源依賴）
- **`feedback_v_migration_pg_dry_run` memory**：Sprint 6+ M12 IMPL phase Linux PG empirical dry-run mandatory
- **`project_2026_05_02_p0_sqlx_hash_drift` memory**：engine restart 實測 SOP + sqlx checksum 對齊

---

## §7 Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| PA | 本 placeholder spec 起草（Sprint 1A-δ deliverable per ADR-0039 §Decision 3 + M12 DESIGN spec sibling）| 2026-05-21 | ✅ Drafted (SPEC-PLACEHOLDER) |
| Operator | 主會話 PM dispatch via Sprint 1A-δ deliverable | 2026-05-21 | 🟡 PROPOSED-pending-commit |
| MIT | V094 既有 schema audit + V115 schema namespace reconciliation（OQ-1 `routing.*` vs `learning.*`）+ V094 EXTEND review（OQ-2）| TBD（Sprint 6+ M12 IMPL phase）| 🟡 PENDING |
| E1 | V115 三表 sqlx migration file IMPL owner（Sprint 6+ M12 IMPL phase；非本 Sprint 1A-δ scope）| TBD（Sprint 6+）| 🟡 PENDING |
| E5 | hypertable + retention 90d + compression policy review（per ADR-0010）| TBD（Sprint 6+）| 🟡 PENDING |
| QC | maker_fill_rate calculation cold start fallback review（per ADR-0039 OQ-3 + M12 DESIGN spec §3.5）| TBD（Sprint 6+）| 🟡 PENDING |
| PM | Sprint 6+ M12 IMPL phase closure | TBD（Sprint 6+ end）| 🟡 PENDING |

---

**END V115 spec PLACEHOLDER（Sprint 1A-δ；frontmatter + 大綱 reserve；full DDL 在 Sprint 6+ M12 IMPL phase 期 land）**

---

Sub-agent dispatch: PA Sprint 1A-δ M12 track
完成時間: 2026-05-21
