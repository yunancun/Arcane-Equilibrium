---
spec: V115 — M12 OrderRouter Adaptive Routing Audit Schema (RESERVED placeholder)
date: 2026-05-21
author: PA (placeholder frontmatter + outline only; full DDL Sprint 6+ IMPL 階段)
phase: Sprint 1A-δ deliverable — frontmatter + outline only (50-100 lines)
status: SPEC-PLACEHOLDER-RESERVED（V### number 預留；body 全標 "Sprint 6+ IMPL phase 補 full DDL"；本 spec 不可進 sqlx migrate path 直至 Sprint 6 IMPL 階段補完 DDL + Linux PG dry-run）
parent specs:
  - srv/docs/adr/0039-m12-order-router-trait-and-maker-fill-rate-metric.md §Decision 3
  - srv/docs/execution_plan/2026-05-21--m12_order_router_design_spec.md §4
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §2 M12
related ADRs:
  - ADR-0039 (M12 OrderRouter trait — schema spec source of truth)
  - ADR-0010 (TimescaleDB hypertable + Guard migrations 範式)
  - ADR-0011 (V-migration PG dry-run mandatory)
  - ADR-0038 (M11 replay V107 與 V115 dedup OQ-4)
related V###:
  - V094 (fills_close_maker_audit — maker_fill 計算上游 column 範式)
  - V107 (M11 replay_divergence_log — 與 V115 dedup 範式)
  - V103/V104 (Earn / hypothesis / track schema spec — V### range head 對齊 reference)
mirror precedent:
  - srv/sql/migrations/V094__fills_close_maker_audit.sql (Guard A/B/C + NOT VALID CHECK + partial index 範式)
  - srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md (Guard A/C + idempotency 範式 + Linux PG dry-run protocol)
scope:
  - Frontmatter + 14 section outline only (50-100 lines)
  - 全 section body 標 "Sprint 6+ IMPL phase 補 full DDL"
  - 不寫 CREATE TABLE / ALTER / INDEX SQL
  - 不寫 Guard A/B/C DO blocks
  - 不執行 PG / 不 Linux dry-run
  - V### number = V115 reserved（pending V### head + V103/V104 land 後對齊）
out-of-scope:
  - Full DDL（Sprint 6+ IMPL 階段補；對齊 ADR-0039 §Decision 3 候選 schema）
  - sqlx migration file `V115__*.sql` 寫作
  - PG empirical 驗證
  - V### head reconciliation（V103 spec §4.1 PA C9 補資料 → V115 number 可能微調）
---

# V115 M12 OrderRouter Adaptive Routing Audit Schema（RESERVED placeholder）

## §0 TL;DR

- **V115 reserve 3 個 NEW table**（per ADR-0039 §Decision 3）：
  - `routing.adaptive_routing_audit`（per-decision audit log；UUID PK）
  - `routing.maker_fill_rate_30d_snapshots`（每日 EOD snapshot）
  - `routing.routing_tier_transitions`（tier 變化 event log）
- **schema 命名待 reconcile**：ADR-0039 §Decision 3 候選 `learning.*`；M12 design spec §4.2 提議改 `routing.*` 分離 routing audit 與 learning data。本 placeholder 採 `routing.*` 待 PA/MIT review。
- **V### number = V115 reserved**；具體 number 待 V103/V104 land + V### head 對齊後確認。
- **Sprint 1A-δ deliverable = frontmatter + outline only**；全 section body 標 "Sprint 6+ IMPL phase 補 full DDL"。

---

## §1 Background + Scope

**Sprint 6+ IMPL phase 補 full DDL**。

Hint：主表 `routing.adaptive_routing_audit`（per ADR-0039 audit schema）+ optional `routing.maker_fill_rate_30d_snapshots`。Schema 命名待 OQ-1（M12 design spec §8.2）reconcile。

詳見 M12 design spec §1 + ADR-0039 §Context。

---

## §2 Schema Changes

### 2.1 `routing.adaptive_routing_audit`（V115 Part 1）

**Sprint 6+ IMPL phase 補 full DDL**。

Hint per ADR-0039 §Decision 3：
- PK = `decision_id` TEXT (UUID per `route()` call)
- 必含 column：`ts` / `asset` / `venue` / `maker_taker` / `slice_count` / `slippage_bps_estimated` / `slippage_bps_realized` / `rebate_applied` / `engine_mode` / `route_reason`
- engine_mode CHECK 4 值（paper / demo / live_demo / live）
- 對齊 V094 / V095 既有 lossy-pk avoidance 範式

### 2.2 `routing.maker_fill_rate_30d_snapshots`（V115 Part 2）

**Sprint 6+ IMPL phase 補 full DDL**。

Hint per ADR-0039 §Decision 3：
- PK = `(snapshot_date, venue, asset_class)` composite
- 必含 column：`window_start_ts` / `window_end_ts` / `maker_fill_notional_usdt` / `total_fill_notional_usdt` / `maker_fill_ratio` / `current_tier` / `days_in_current_tier`
- Retention 365d（per H-22 R4 governance retention 規範）

### 2.3 `routing.routing_tier_transitions`（V115 Part 3）

**Sprint 6+ IMPL phase 補 full DDL**。

Hint per ADR-0039 §Decision 3：
- PK = `transition_id` TEXT
- 必含 column：`ts` / `venue` / `asset_class` / `from_tier` / `to_tier` / `maker_fill_ratio` / `alert_dispatched`

---

## §3 Guard A/B/C Templates

**Sprint 6+ IMPL phase 補 full DDL**。

Hint per V103/V104 spec §3 範式 + V094 mirror：
- Guard A：table existence + 既有 schema 對齊驗證；缺 column RAISE
- Guard B：不適用（V115 無 ALTER 既有 column）
- Guard C：CHECK constraint ENUM 值齊全 + index 對齊驗證；缺值 RAISE

---

## §4 V107 dedup（per ADR-0039 OQ-4）

**Sprint 6+ IMPL phase 補設計**。

Hint：V107（M11 replay_divergence_log per ADR-0038）與 V115（routing audit log）兩表正交並存；無 explicit FK；Replay 階段透過 `asset + ts ± window` 做 fuzzy join。CR-14 review 後決定是否加 explicit cross-reference column。

---

## §5 TimescaleDB Hypertable 判斷

**Sprint 6+ IMPL phase 補判斷**。

Hint：
- `routing.adaptive_routing_audit`：~1000-10000 row/day → 是否走 hypertable 待 Sprint 6 IMPL 階段量級評估 confirm
- `routing.maker_fill_rate_30d_snapshots`：~3-5 row/day → regular table（無時序壓力）
- `routing.routing_tier_transitions`：~10-50 row/yr → regular table

---

## §6 engine_mode CHECK 4 值齊全

**Sprint 6+ IMPL phase 補 DDL**。

per CLAUDE.md §七 + MIT memory baseline：engine_mode CHECK 必含 `paper / demo / live_demo / live` 4 值；training filter 必 `IN ('live','live_demo')`。3 V115 表全須含此 CHECK。

---

## §7 Linux PG Dry-Run Protocol

**Sprint 6+ IMPL phase 補執行**。

per CLAUDE.md §七 V055 mandate + `feedback_v_migration_pg_dry_run.md` + V094 §4 範式：V115 涉及 PG reflection + CHECK constraint runtime semantic + 跨 schema FK，必先 Linux PG empirical dry-run；禁 Mac mock pytest 代替。

詳見 V103/V104 spec §4 範式。

---

## §8 sqlx Checksum Repair SOP

**Sprint 6+ IMPL phase 補執行**。

per memory `project_2026_05_02_p0_sqlx_hash_drift`：V115 file edit 後 DB checksum 必同步；`cargo run --release --bin repair_migration_checksum -- --version 115`；engine restart 後驗證 sqlx migrate 不 panic。

---

## §9 IMPL Plan（簡）

**Sprint 6+ IMPL phase 補**。

Hint：E1 寫 V115.sql 含 Guard A/C + 3 CREATE TABLE + indexes；E2 review；E4 regression；ssh trade-core 跑 Linux PG dry-run × 2 round；restart_all --rebuild deploy；engine restart verify。

---

## §10 Backward Compat

**Sprint 6+ IMPL phase 補**。

Hint：V115 是 append-only schema migration；加 3 NEW table；0 ALTER 既有 column；0 DROP / RENAME。不破現有 SELECT / INSERT / UPDATE。

---

## §11 Rollback Path

**Sprint 6+ IMPL phase 補**。

Hint：DROP TABLE IF EXISTS routing.routing_tier_transitions → routing.maker_fill_rate_30d_snapshots → routing.adaptive_routing_audit（無 FK 依賴順序自由）。0 row loss（V115 apply 後立即 0 row）。

---

## §12 風險評估 + 16 原則 / DOC-08 §12 / §四 觸碰

**Sprint 6+ IMPL phase 補**。

Hint per M12 design spec §9：
- 16 原則全 ✅ 相容（cost 感知原則 13 是核心）
- DOC-08 §12 安全不變量 #1 / #2 / #3 / #7 直接相容
- §四 硬邊界 0 觸碰

---

## §13 Cross-References

- **M12 design spec**：`srv/docs/execution_plan/2026-05-21--m12_order_router_design_spec.md`（Sprint 1A-δ deliverable 同日 land；本 spec sibling）
- **ADR-0039**：`srv/docs/adr/0039-m12-order-router-trait-and-maker-fill-rate-metric.md`（V115 schema candidate source）
- **V103/V104 spec**：`srv/docs/execution_plan/2026-05-21--v103_v104_earn_hypotheses_schema_spec.md`（Guard 範式 + Linux PG dry-run protocol reference）
- **V094**：`srv/sql/migrations/V094__fills_close_maker_audit.sql`（lossy-pk avoidance + Guard 範式 baseline）
- **ADR-0010**：`srv/docs/adr/0010-timescale-hypertable-with-guard-migrations.md`（Guard 範式）
- **ADR-0011**：`srv/docs/adr/0011-v-migration-linux-pg-dry-run-mandatory.md`（Linux PG dry-run mandatory）
- **ADR-0038**：`srv/docs/adr/0038-m11-continuous-counterfactual-replay-and-liquidations-source.md`（V107 dedup OQ-4 來源）

---

## §14 Sign-off

| Role | Source | Date | Status |
|---|---|---|---|
| PA | 本 placeholder 起草（Sprint 1A-δ deliverable frontmatter + outline only）| 2026-05-21 | ✅ Drafted (placeholder) |
| Operator | 主會話 PM dispatch via Sprint 1A-δ deliverable | 2026-05-21 | 🟡 RESERVED-pending-IMPL |
| PA | Sprint 6+ IMPL phase 補 full DDL（schema 命名 OQ-1 reconcile + V### number 對齊 V103/V104 head 後 confirm） | TBD（Sprint 6+） | 🟡 PENDING |
| MIT | V115 schema 命名 reconciliation（`routing.*` vs `learning.*` per M12 design spec OQ-1）| TBD（Sprint 1A-δ V115 placeholder finalize）| 🟡 PENDING |
| E1 | Sprint 6+ IMPL writer + sqlx migration file | TBD（Sprint 6+） | 🟡 PENDING |
| PM | Sprint 6+ IMPL closure → V115 SPEC-FINAL | TBD（Sprint 6+） | 🟡 PENDING |

---

*OpenClaw / Arcane Equilibrium V115 Reserved Schema Spec — Sprint 1A-δ placeholder; full DDL Sprint 6+ IMPL phase per ADR-0039*
