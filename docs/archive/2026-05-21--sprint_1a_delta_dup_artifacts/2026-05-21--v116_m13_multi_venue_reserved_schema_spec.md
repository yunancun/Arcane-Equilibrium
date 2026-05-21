---
spec: V116 — M13 Multi-Venue / AssetClass Reserved Schema Migration Spec (PLACEHOLDER)
date: 2026-05-21
author: PA placeholder draft for Sprint 1A-δ V116 reserve frontmatter
phase: v5.8 Sprint 1A-δ schema number reservation
status: SPEC-PLACEHOLDER-RESERVED-Y3（frontmatter + outline only；不寫 V116.sql；不在 Mac 跑 SQL；不執行 PG；full DDL 在 Y3+ first quarter Binance trade enable 6-gate PASS 後開新 amendment ADR + Sprint land）
parent specs:
  - srv/docs/adr/0040-multi-venue-gate-spec.md（治理邊界 SoT；§Decision 2 per-venue 5-gate schema + §Decision 5 per-venue authorization 三元組綁定 為本 V116 預留意圖權威來源）
  - srv/docs/execution_plan/2026-05-21--m13_multi_venue_asset_class_design_spec.md（M13 module DESIGN spec；本 V116 為其 reserved migration placeholder）
  - srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md §9 line 799（V116 reserved for asset_class_venue_registry；IMPL Y3+ per ADR-0040 multi-venue Y3+ at earliest）
  - srv/docs/adr/0035-m5-online-learning-interface-reserved.md §Decision 2 V114 reserved placeholder（同 pattern；reserve frontmatter only）
mirror precedent:
  - srv/docs/execution_plan/2026-05-21--v113_m7_decay_signals_schema_spec.md（placeholder spec doc 範式）
scope: placeholder spec doc — Sprint Y3+ venue activation 後補 full DDL（per ADR-0040 §Decision 1 + §Decision 3）
---

# V116 M13 Multi-Venue / AssetClass Reserved Schema Migration Spec (PLACEHOLDER)

## §0 TL;DR

- **V116 status = SPEC-PLACEHOLDER-RESERVED-Y3**：reserve schema number only；Sprint 1A-δ 不寫 V116.sql / 不寫 full DDL / 不跑 PG。
- **Y3+ activation 觸發**：per ADR-0040 §Decision 1 + §Decision 3 — Binance trade enable 6-gate criteria 全 PASS（W105-W117）→ 開新 amendment ADR + V116 full DDL Sprint land。
- **主表 hint**：`routing.venue_lifecycle`（venue 啟用 / 停用 audit；per ADR-0040 §Decision 2 per-venue 5-gate schema + §Decision 5 三元組綁定）+ optional `routing.cross_venue_position_snapshots`（per v5.8 §2 M13 line 476-477）。
- **schema number planning 紀律**：V114 (M5) + V115 (M12) + V116 (M13) 三 reserved slot Sprint 1A-δ 一次保留；防 Y3+ activation 撞既有 V117-V200 已 land number（per ADR-0035 §Decision 2 + v5.8 §9 line 796-799）。

## §1 Background

Sprint Y3+ venue activation 後補 full DDL。v5.8 §9 line 796-799 明示 V116 為 interface-stub reserved schema；ADR-0040 §Decision 1 amend Y2 → Y3+ at earliest。sqlx migration 順序強制單向（per memory `project_2026_05_02_p0_sqlx_hash_drift`）；提前 reserve V116 + 不寫 DDL 是 schema number planning 受控路徑。明示禁止 Sprint 1A-δ 真寫 V116 SQL（同 sqlx checksum drift 風險）。

## §2 Schema Outline (Sprint Y3+ venue activation 後補 full DDL)

**主表 `routing.venue_lifecycle`** hint columns（per ADR-0040 §Decision 2 + §Decision 5）：venue + asset_class + state_action(6 值：enabled/disabled/6_gate_evaluating/6_gate_pass/6_gate_fail/permanently_retired) + event_ts + gate_criteria_evidence JSONB + lal_4_approval_id FK + operator_signature + authorization_secret_slot_path + environment_bound + engine_mode + decision_authority hard-lock 'operator' + previous_state_action + rationale。

**Optional `routing.cross_venue_position_snapshots`** hint：snapshot_id + snapshot_ts + symbol_key + venue + asset_class + symbol + position_size_signed + position_notional_usdt + cross_venue_netting_group_id + engine_mode（per v5.8 §2 M13 line 476-477）。

## §3 6 Trade Gate Criteria Schema Hint

`venue_lifecycle.gate_criteria_evidence` JSONB 對應 ADR-0040 §Decision 3 6 條 criterion (a)-(f)：gate_a Bybit alpha sustained / gate_b Binance market data alpha / gate_c operator arbitration / gate_d BB ToS+KYC / gate_e Copy Trading evidence land / gate_f AUM ≥ $50k sustained 30d。

## §4 ENUM Outline

`venue` CHECK 4 值 + `asset_class` CHECK 4 值（per M13 spec §3.1 + §2.1 hardcode）+ `state_action` CHECK 6 值 + `engine_mode` CHECK 4 值（per CLAUDE.md §七）+ `decision_authority` DEFAULT 'operator' hard-lock（per ADR-0034 LAL 4）。

## §5 Hypertable 判斷

`routing.venue_lifecycle` = regular table (~10-50 row/yr)；`routing.cross_venue_position_snapshots` 可能 hypertable（per-symbol-venue snapshot 高頻；待 Y3+ 評估 retention 6mo / compression）。

## §6 Guard A/B/C 大綱

Guard A 表已存在驗 column 完整 + governance.audit_log + M13 enum Rust 端 land prereq；Guard B Y3+ 真 ALTER 既有 column type 時走（本 placeholder 不寫）；Guard C ENUM 值齊全驗 + decision_authority DEFAULT CHECK 真存在 + FK 對齊。

## §7 Linux PG Empirical Dry-Run Checklist

Y3+ activation Sprint 補 3-5 條 ssh trade-core PG query（_sqlx_migrations head + TimescaleDB extension + governance.audit_log + decision_lease 存在性 + V116 apply 後驗 + decision_authority CHECK reject 非 'operator' empirical INSERT + venue/asset_class CHECK reject 第 5 值 + DEX/Hyperliquid string literal INSERT 必 RAISE per M13 spec §3.2 Layer 3）。per CLAUDE.md §七 + `feedback_v_migration_pg_dry_run.md` PG empirical × 2 round 必走。

## §8 sqlx Checksum Repair SOP

per memory `project_2026_05_02_p0_sqlx_hash_drift` + ADR-0035 §Decision 2 反模式 (a)：V116 不寫 DDL 即避免 sqlx checksum drift；Sprint 1A-δ 明示禁止真寫 V116 SQL。Y3+ activation 真寫 V116.sql 後任何 edit 必跑 `repair_migration_checksum --version 116`。

## §9 IMPL Plan

- Sprint 1A-δ：V116 reserve frontmatter only（本 placeholder draft + PM sign-off）；0 SQL；0 PG；0 IMPL
- Y1 末 (Sprint 10 W36-39)：retirement R1 first audit cycle；maintain reserve 狀態
- Y2 Q4-Y3 Q1 prep (W100-W104)：V116 full DDL spec draft 啟動
- Y3 Q1 evaluation (W105-W117)：6 gate criteria 評估；PASS → 新 amendment ADR + V116 full DDL Sprint land；FAIL → continue defer
- Y3 Q2+ activation IMPL (if Y3 Q1 PASS)：V116.sql 實檔 + Linux PG dry-run × 2 round + 部署；BinanceTrade enum variant trait method IMPL replace `unimplemented!()`

Sprint Y3+ venue activation 後補 full DDL。

## §10 Backward Compat

V116 placeholder Sprint 1A-δ land 對既有 schema 0 影響（無 DDL）；Y3+ activation 後真寫 V116 為 append-only。

## §11 Rollback Path

Y3+ activation 真寫 V116 後 rollback：`DROP TABLE IF EXISTS routing.cross_venue_position_snapshots; DROP TABLE IF EXISTS routing.venue_lifecycle;` 0 row loss。

## §12 風險評估 + 16 原則 / DOC-08 §12 / §四 觸碰

Sprint 1A-δ placeholder doc only；無 schema / 無 IMPL / 無 PG → 改動風險極低；16 原則合規 16/16（per M13 spec §9.2 對等繼承）；DOC-08 §12 觸碰 0/9；§四 5 硬邊界觸碰 0/5。詳細逐條合規列表 Y3+ venue activation 真寫 V116 時補完整 full DDL 後逐條複核。

## §13 開放問題 / Caveat

詳細 open Q 見 M13 spec §8.2；本 V116 placeholder 對應的具體 schema 級 open Q（Y3+ activation 仲裁）：(1) `routing.venue_lifecycle` 與既有 `governance.audit_log` column 重疊 vs subclass / event_type 路徑 vs 獨立表？(2) `cross_venue_position_snapshots` 是否真需獨立表 vs 走既有 `trading.positions` 加 venue field？(3) `state_action` ENUM 6 值充足 vs 細化為 8-10 值？

仲裁 owner 全為 PA + PM/MIT at Y3 Q1 prep。Sprint Y3+ venue activation 後補 full DDL。

## §14 關鍵文件指針

- 本 V116 placeholder：本檔
- M13 design spec：`srv/docs/execution_plan/2026-05-21--m13_multi_venue_asset_class_design_spec.md`
- ADR-0040：`srv/docs/adr/0040-multi-venue-gate-spec.md`（治理邊界 SoT）
- ADR-0035 + V114 placeholder pattern：`srv/docs/adr/0035-m5-online-learning-interface-reserved.md`
- V113 placeholder 範式：`srv/docs/execution_plan/2026-05-21--v113_m7_decay_signals_schema_spec.md`
- v5.8 §9 V114-V116 reserved：`srv/docs/execution_plan/2026-05-20--execution-plan-v5.8.md:796-799`
- memory `project_2026_05_02_p0_sqlx_hash_drift`（不寫 DDL 即避免 sqlx checksum drift 紀律）
- CLAUDE.md §七 V### migration 規範 + §Data, Migrations, And Validation

---

**END V116 M13 Multi-Venue / AssetClass Reserved Schema Migration Spec (PLACEHOLDER) draft v0**
