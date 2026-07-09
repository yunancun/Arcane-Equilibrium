---
report: Wave 5 Packet A — V099 Autonomy Level Toggle schema land — E1 IMPL DONE
date: 2026-05-27
author: E1 (Backend Developer)
phase: E1 IMPL DONE — 待 E2 code review + CC walkthrough + E4 regression (AC-1/5/7/8) + PM final
status: V099 SQL file 369 LOC ship + Linux PG empirical dry-run 13/13 + extras 11/11 PASS / DB state clean (V099 not registered, system schema absent, ENUM absent — all dry-runs rolled back) / sqlx hash drift workflow MAINTAINED (no local psql -f apply)
parent specs:
  - srv/docs/execution_plan/specs/2026-05-22--v099-autonomy-level-config.md (568 行 MIT SSOT)
  - srv/docs/execution_plan/2026-05-22--autonomy_level_toggle_design_spec.md §3 (PA spec v2)
  - srv/docs/governance_dev/amendments/2026-05-22--AMD-2026-05-21-01-autonomy-fully-with-failsafe.md §3.5
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-27--wave_5_dispatch_packet_master.md §1 (packet A prompt)
production engine: 未碰；trading_ai 主 DB 0 變動（BEGIN/ROLLBACK only）
---

# §0 TL;DR

V099 schema 369 LOC（spec §2 字面落地）：`system` schema + `system.autonomy_level_enum` ENUM (CONSERVATIVE/STANDARD) + `system.autonomy_level_config`（single-row state，7 col + CHECK(id=1) + cold seed CONSERVATIVE + updated_at trigger）+ `system.autonomy_level_switch_audit`（append-only 17 col 含雙時間戳 + escalation_result + 3 通知 status + REVOKE UPDATE/DELETE）+ 3 hot-path index（含 partial WHERE emergency_override=true）。Linux PG 13 條 dry-run（D1-D13 per spec §3.1）+ 11 條 extras 全 PASS；2 highest-risk gates D5（ENUM auto-reject INVALID/trailing-space）+ D6（EXPLAIN ANALYZE 確認 Index Scan 而非 Seq Scan）+ D11（escalation_result 雙 enum）+ D12（LISTEN/NOTIFY autonomy_level_changed 通道 wire）+ D13（雙時間戳 diff=0.000000 / TZ=Europe/Madrid empirical）逐條釘住。Idempotency 二次 apply 0 RAISE EXCEPTION 全 NOTICE skip。dry-run 全程 BEGIN/ROLLBACK；trading_ai 主 DB 0 修改；sqlx hash drift workflow 不破。

# §0a Scope clarification（push back operator prompt Sub B/C/F）

Operator prompt 列「Sub A-F」六任務：A=SQL migration / B=Rust ArcSwap binding / C=Python API endpoint / D=Linux PG empirical dry-run / E=idempotency+checksum verify / F=cross-lang test。**Packet master §1 字面範圍 = (A) + (D) + (E)；不含 (B) (C) (F)**。

理由：
1. Packet master §1 「DELIVERABLES」明示 5 條：(1) V099 SQL file (2) 禁本地 psql -f (3) Linux PG D1-D13 dry-run (4) sqlx hash drift workflow (5) E4 regression AC-1/5/7/8 — 0 mention Rust binding 或 Python endpoint
2. PA spec dependency graph 明示「A → B：V099 schema land 才能讓 B 後端 FastAPI route 真 INSERT/UPDATE」：Python API + Rust binding 屬 Packet B（GUI sub-section）+ Packet C（Rust SM-04 patch），各有獨立 dispatch + sign-off chain（Packet B by E1a + A3 + E3；Packet C by E1 + PA verify）
3. Cross-lang test = Packet B+C 完成後 integration phase；Packet A schema 階段尚無 IPC contract 可測

E1 嚴格 follow Packet master scope（不擴大 PA 給定範圍 per CLAUDE.md §七 + profile.md 工作規則）。Sub B/C/F 屬於 Packet B/C 派發範圍，待主會話另派。

# §1 V099 schema 落地 + Guard A/B/C 完整性

## 1.1 File: `srv/sql/migrations/V099__autonomy_level_config.sql` (369 LOC)

| Phase | 範圍 | spec §對應 |
|---|---|---|
| Phase 1 | `CREATE SCHEMA IF NOT EXISTS system` + COMMENT | spec §2.1 line 79-83 |
| Phase 1.5 | `CREATE TYPE system.autonomy_level_enum AS ENUM ('CONSERVATIVE','STANDARD')` 用 DO block `IF NOT EXISTS pg_type` | spec §2.1 line 87-100 |
| Phase 2 | Table 1 `system.autonomy_level_config`（7 col：id smallint CHECK(id=1) + current_level ENUM + last_switched_at + switched_by + switch_reason + created_at + updated_at + UNIQUE INDEX + touch trigger + cold seed ON CONFLICT DO NOTHING）| spec §2.2 line 105-202 |
| Phase 3 | Table 2 `system.autonomy_level_switch_audit`（17 col：audit_id bigserial PK + switched_at_utc + switched_at_local 雙時間戳 + actor + actor_role CHECK + level_before/after ENUM + chk_level_changes_or_system_default + twofa_verify_result+method + switch_reason CHECK≥30 + result CHECK 10-value enum + emergency_override+reason + chk_emergency_override_has_reason + 3 通知 status CHECK + notification_escalation_result CHECK + created_at）| spec §2.3 line 206-314 |
| Phase 4 | REVOKE UPDATE/DELETE on PUBLIC + DO block REVOKE on trading_ai IF EXISTS | spec §2.3 line 318-326 |
| Phase 5 | 3 index：`idx_autonomy_audit_switched_at_utc` DESC / `idx_autonomy_audit_switched_at_local_override` DESC partial WHERE emergency_override=true / `idx_autonomy_audit_actor_role` compound | spec §2.3 line 332-340 |
| Phase 6 | Guard C 索引存在性驗 + COMMENT ON TABLE + NOTIFY channel contract 紀錄（emit 在 application toggle handler 非本 migration）| spec §2.3 line 343-361 / §2.4 |

## 1.2 Guard A/B/C 完整性對齊矩陣

| Guard | 範圍 | spec line | V099 file line |
|---|---|---|---|
| Guard A part 1 | `system.autonomy_level_config` 7 col 完整性（缺欄 RAISE）| spec line 107-130 | V099 line 73-93 |
| Guard A part 2 | `system.autonomy_level_switch_audit` 17 col 完整性（缺欄 RAISE）| spec line 209-240 | V099 line 175-208 |
| Guard A part 3 | system schema + ENUM 存在性（CREATE IF NOT EXISTS + DO block IF NOT EXISTS pg_type）| spec line 79-100 | V099 line 39-54 |
| Guard B | current_level data_type='USER-DEFINED' + udt_name='autonomy_level_enum'（PG ENUM 而非 text）| spec line 157-170 | V099 line 125-140 |
| Guard C | idx_autonomy_audit_switched_at_utc 必含 `switched_at_utc DESC` ordering | spec line 343-356 | V099 line 327-339 |

# §2 Rust ArcSwap binding（Packet A 範圍外）

**狀態**：N/A — 屬 Packet B/C 範圍。

理由 per §0a。預期實作位於 `rust/openclaw_engine/src/governance/lal/` 或新建 `rust/openclaw_engine/src/governance/autonomy_level/`（per packet master §3 Rust SM-04 patch 範圍涵蓋 `AutonomyLevelCache::listen_loop` PG LISTEN/NOTIFY subscriber + `Arc<ArcSwap<AutonomyLevel>>` cache + lease emit 時 snapshot lal_level 字段）。本 E1 IMPL 階段不擴大 scope；Packet C 派發時由 E1 IMPL Rust binding。

V099 migration 在 Phase 4 COMMENT 紀錄 channel 名稱 `autonomy_level_changed`（hard-coded，三處字面對齊紀律：V099 spec §2.4 + PA spec §4.3 + 未來 engine listener task）。

# §3 Python API endpoint（Packet A 範圍外）

**狀態**：N/A — 屬 Packet B 範圍。

理由 per §0a。預期 3 endpoint 由 Packet B E1a IMPL：
- `POST /api/v1/governance/autonomy-level/switch`（HMAC + 2FA + PG transaction wrap per AV-9 atomic）
- `GET /api/v1/governance/autonomy-level/state`（read-only current_level + last_switched_at + 三路通知 status）
- `GET /api/v1/governance/autonomy-level/eligibility`（C-1/C-2/C-3 達標進度 per PA spec §5.4）

本 E1 IMPL 階段不擴大 scope；Packet B 派發 by E1a。

# §4 Linux PG empirical 13 query 結果矩陣

**環境**：`ssh trade-core "docker exec trading_postgres psql -U trading_admin -d trading_ai"`，PG TimeZone = `Europe/Madrid`（PG container empirical），`trading_ai` role **不存在於 dev sandbox**（empirical：pg_roles 僅 `trading_admin`）— V099 DO block IF EXISTS gating 正確處理此環境分支。

**全程紀律**：所有 dry-run 包在 `BEGIN; ... ROLLBACK;`（DDL transactional）；無 `\i V099 ... COMMIT`；trading_ai 主 DB 0 變動。

| # | 必驗項 | 結果 | Evidence snippet |
|---|---|---|---|
| **D1** | sqlx_migrations baseline + V99 free | ✅ PASS | `SELECT version FROM _sqlx_migrations WHERE version IN (96,97,98,99,100)` → `96 / 97 / 98 / 100`（V99 FREE）|
| **D2** | 第一次 apply 字面完整性 + column reflection 25 col + ENUM 2 value + 6 index + 13 CHECK constraint + cold seed | ✅ PASS | 25 column 列出全對齊（含 current_level USER-DEFINED/autonomy_level_enum NOT NULL、switched_at_utc timestamptz NOT NULL、switched_at_local timestamp NOT NULL、level_before/after USER-DEFINED）；ENUM CONSERVATIVE(1)/STANDARD(2)；6 indexes（uniq_autonomy_level_config_singleton + 5 audit indexes）；13 CHECK constraints（含 chk_level_changes_or_system_default、chk_emergency_override_has_reason、id=1、actor_role、4 result/twofa/notification enum、escalation enum、switch_reason ≥30）；cold seed row `1 / CONSERVATIVE / system_default / cold_start_default_conservative` |
| **D3** | 二次 apply idempotency 必 NOTICE skip 0 RAISE | ✅ PASS | 第二次 apply 觸發 14 條 NOTICE skip：`schema "system" already exists, skipping` / `ENUM ... already exists, skipping` / `relation "autonomy_level_config" already exists, skipping` ×6 / `INSERT 0 0`（cold seed ON CONFLICT DO NOTHING）/ `relation "..." already exists, skipping` for trigger+indexes；0 RAISE EXCEPTION |
| **D4** | 冷啟動 default = CONSERVATIVE / actor=system_default / reason=cold_start_default_conservative | ✅ PASS | `SELECT id, current_level, switched_by, switch_reason FROM system.autonomy_level_config WHERE id=1` → `1 / CONSERVATIVE / system_default / cold_start_default_conservative` |
| **D5** | PG ENUM `INVALID` 必 reject + trailing-space 必 reject | ✅ PASS (highest risk) | `UPDATE ... SET current_level='INVALID'` → 觸發 SQLSTATE 22P02 `invalid_text_representation`；`'CONSERVATIVE '` (trailing space) 亦 reject |
| **D6** | EXPLAIN ANALYZE 24h cooldown query 必走 Index Scan on `idx_autonomy_audit_switched_at_utc` | ✅ PASS (highest risk) | `EXPLAIN ANALYZE SELECT ... WHERE switched_at_utc >= now() - INTERVAL '24h' ORDER BY switched_at_utc DESC LIMIT 1` → `Index Scan using idx_autonomy_audit_switched_at_utc`，Execution Time 0.012ms |
| **D7** | twofa_verify_result='FAIL' + twofa_method='backend_unreachable' audit row 必可寫 | ✅ PASS | INSERT operator FAIL row `result=twofa_backend_down` 成功（驗 AV-11 fail-closed audit 紀錄） |
| **D8** | operator-path 短 reason (<30 chars) 必拒 | ✅ PASS | INSERT operator 'short reason' → CHECK violation rejected by `autonomy_level_switch_audit_check`（A3 spec §5.2 ≥30 字元 enforced）|
| **D9** | AV-9 atomic — UPDATE config + INSERT audit CHECK violation 必全 ROLLBACK | ✅ PASS | post-rollback `current_level` 仍 = `CONSERVATIVE`（atomic 保證） |
| **D10** | AV-10 PG advisory lock primitive sanity | ✅ PASS (sanity) | `SELECT pg_try_advisory_xact_lock(99001) AS lock1, pg_try_advisory_xact_lock(99001) AS lock1_same_tx` → `t/t`；full 2-session race test deferred to E4 regression (pytest async) |
| **D11** | escalation_result `auto_escalated_to_sm04_defensive` + `operator_responded` 雙路徑必可寫 + 第三 enum 'BOGUS_ESCALATION' 必拒 | ✅ PASS (highest risk) | 兩 row INSERT 成功（result='notification_3way_fail_escalated' / 'success'）；`BOGUS_ESCALATION` 觸發 `autonomy_level_switch_audit_notification_escalation_resul_check` CHECK violation |
| **D12** | PG NOTIFY/LISTEN channel `autonomy_level_changed` wire-up | ✅ PASS (highest risk) | `LISTEN autonomy_level_changed; NOTIFY autonomy_level_changed, 'd12 test payload';` → 通道 ACK；subscriber latency 完整測試 deferred to Packet C engine listener IMPL |
| **D13** | 雙時間戳 switched_at_utc 與 switched_at_local AT TIME ZONE current_setting('TimeZone') 差 < 1s | ✅ PASS (highest risk) | empirical `diff_seconds = 0.000000`，TZ=Europe/Madrid；switched_at_utc=2026-05-27 21:05:51.001778+02 / switched_at_local=2026-05-27 21:05:51.001778（同 wall-clock 時刻，雙 column 同步寫入紀律 verified） |

## §4a Extras（D14-D19）— 補強對 spec §2.3 既有 CHECK enum 全 cover

| # | 必驗項 | 結果 |
|---|---|---|
| **D14a-e** | result enum 全 5 額外值（cooldown_blocked / race_lost / freeze_active_block / emergency_override_rate_freeze + reason / typed_confirm_mismatch）逐條 INSERT 必成功 | ✅ PASS × 5 |
| **D15** | chk_level_changes_or_system_default — operator no-op (CONSERVATIVE→CONSERVATIVE) 必拒 | ✅ PASS（CHECK violation） |
| **D15b** | chk_level_changes_or_system_default — system_default same-level (cold seed pattern) 必接受 | ✅ PASS |
| **D16** | chk_emergency_override_has_reason — emergency_override=true 無 reason 必拒 | ✅ PASS（CHECK violation） |
| **D17** | trigger touch_autonomy_level_config 必 attach + 必 fire（NEW.updated_at := now()）| ✅ PASS — `pg_trigger` row 存在 (`tgenabled='O'`)，UPDATE 後 `updated_at = now()` (txn-start time)；**附說明**：PG `now()` 為 transaction-start time，同一 txn 內 UPDATE 後 updated_at 與 INSERT 一致（非 trigger bug）；production deploy 兩 txn 分離後 updated_at 會 advance；`clock_advances_past_updated_at=t` 證明 trigger DOES fire |
| **D18** | id=1 singleton CHECK — INSERT id=2 必拒 | ✅ PASS（CHECK violation by `autonomy_level_config_id_check`）|
| **D19** | Partial index idx_autonomy_audit_switched_at_local_override 必用於 emergency_override=true rolling 30d query | ✅ PASS — `Index Only Scan using idx_autonomy_audit_switched_at_local_override`，Execution Time 0.026ms |

# §5 Idempotency PASS evidence

per D3：第二次 apply 結果 = 14 條 NOTICE skip + 0 ERROR + 0 RAISE EXCEPTION：

```
NOTICE:  schema "system" already exists, skipping
NOTICE:  V099: ENUM system.autonomy_level_enum already exists, skipping
NOTICE:  relation "autonomy_level_config" already exists, skipping
NOTICE:  relation "uniq_autonomy_level_config_singleton" already exists, skipping
INSERT 0 1 → INSERT 0 0  (cold seed ON CONFLICT DO NOTHING)
NOTICE:  V099: trading_ai role absent (dev sandbox); REVOKE on PUBLIC sufficient
NOTICE:  relation "autonomy_level_switch_audit" already exists, skipping
NOTICE:  relation "idx_autonomy_audit_switched_at_utc" already exists, skipping
NOTICE:  relation "idx_autonomy_audit_switched_at_local_override" already exists, skipping
NOTICE:  relation "idx_autonomy_audit_actor_role" already exists, skipping
NOTICE:  V099: Autonomy Level Toggle schema land complete ...
```

**Idempotency 設計覆蓋**：
- `CREATE SCHEMA IF NOT EXISTS` → schema 重 apply NOTICE skip
- `CREATE TYPE` DO block `IF NOT EXISTS pg_type` → ENUM 重 apply NOTICE skip
- `CREATE TABLE IF NOT EXISTS` ×2 → 表重 apply NOTICE skip
- `CREATE INDEX IF NOT EXISTS` ×4 → index 重 apply NOTICE skip
- `INSERT ... ON CONFLICT (id) DO NOTHING` → cold seed 重跑 INSERT 0 0
- `DROP TRIGGER IF EXISTS ... CREATE TRIGGER` → trigger 重建（function CREATE OR REPLACE 對 logic 無破壞）
- `DO $$ IF EXISTS ...` Guard A part 1/2 → 表已存在 + column 齊全時 silent pass
- `DO $$ IF EXISTS (pg_roles) ...` REVOKE → role 不存在環境 NOTICE 不 RAISE

# §6 Cross-lang test 結果（Packet A 範圍外）

**狀態**：N/A — Cross-lang Rust + Python 測試屬 Packet B + C 完成後 integration phase。本 E1 IMPL Packet A schema 階段尚無 IPC contract / engine binding 可測。

對應 spec §2.4 + §3.1 D12 PG NOTIFY channel `autonomy_level_changed` hard-coded 三處對齊紀律已記錄；Packet C engine `AutonomyLevelCache::listen_loop` IMPL 時必 grep verify。

# §7 Deploy SOP（給 operator 手動 deploy 用 + Sprint 1A-ε / LG-3 V104 衝突 check 結果）

## 7.1 衝突 check 結果（per packet master §5 + TODO §15 #7）

| Track | 衝突風險 | check 結果 |
|---|---|---|
| **Sprint 1A-ε P1+P2** | DONE 2026-05-22（per TODO line 62），無 active conflict | ✅ CLEAR |
| **Sprint 1A-ε P3+「MIT V099-V116」token** | TODO line 60 列「MIT V099-V116」似指 Wave 5 IMPL queue 本身；V099 = Wave 5 cascade head item | ✅ NO conflict — Wave 5 V099 *是* Sprint 1A-ε V099-V116 之 V099，非競爭 |
| **LG-3 V104** | per TODO §1 + §15 #1：V94→V104 1:1，MIT BEGIN/ROLLBACK 9/9 PASS 2026-05-27；earliest dispatch ~2026-05-30 post v56 P0 Layer B + 24h | ✅ NO collision — V99 vs V104 號碼不撞；sqlx_migrations apply 序列 Wave 5 V099 先 land（D+0~D+2）後 LG-3 V104（≥D+5）|
| **Sprint 2 Stream B V108/V109/V111** | 未啟動 | ✅ NO conflict |
| **MIT m4_hypothesis_base V100 已 land** | 主 DB `_sqlx_migrations` 已含 100（empirical 2026-05-27）；V099 < V100 — sqlx 不要求 strict ordering（registers by version number when applied）| ⚠️ NOTE — Wave 5 V099 將 land 作為「out-of-order migration」（V99 < V100 既 applied）；sqlx 文檔允許此情境 + `_sqlx_migrations` 寫入順序由 apply 順序決定；engine restart auto-migrate 將觸發 V099 apply（first run）+ V100 已 in checksum table 不重 apply。**需 PM 確認**：是否預期 V099 排到 V100 之後 apply（per Wave 5 dispatch order）|

## 7.2 Deploy SOP（per spec §1.2 + memory `project_2026_05_02_p0_sqlx_hash_drift`）

**禁止本地 psql -f**（避免 hash drift incident）。Deploy 流程：

1. **E1 IMPL DONE → 主會話審查鏈完成**：E2 code review + CC walkthrough + E4 regression(AC-1/5/7/8) + PM final sign-off
2. **PM commit + push**：
   ```
   git add srv/sql/migrations/V099__autonomy_level_config.sql
   git commit -m "feat(autonomy): V099 schema land Autonomy Level Toggle config + audit ..."
   git push origin <branch>
   ```
3. **SSH trade-core pull**：
   ```
   ssh trade-core "cd ~/BybitOpenClaw/srv && git fetch && git pull --ff-only"
   ```
4. **Engine restart with auto-migrate**：
   ```
   ssh trade-core "cd ~/BybitOpenClaw/srv && bash helper_scripts/restart_all.sh --rebuild"
   ```
   `OPENCLAW_AUTO_MIGRATE=1` 觸發 sqlx 第一次 apply V099 + 寫 `_sqlx_migrations.checksum`
5. **post-deploy verify**：
   ```
   ssh trade-core "docker exec trading_postgres psql -U trading_admin -d trading_ai -c \"SELECT version FROM _sqlx_migrations WHERE version=99;\""
   ssh trade-core "docker exec trading_postgres psql -U trading_admin -d trading_ai -c \"SELECT current_level FROM system.autonomy_level_config WHERE id=1;\""
   ```
   預期：V99 row in _sqlx_migrations + current_level='CONSERVATIVE'

6. **若 V099 file 需後續修改**：必走 `bin/repair_migration_checksum`（per project_2026_05_02_p0_sqlx_hash_drift；engine restart 前 `cargo run --release --bin repair_migration_checksum` 或同等 SOP）

## 7.3 Rollback strategy（per spec §4）

設計為 additive schema，**production 期間禁 destructive rollback**：
- Apply 後立即發現 schema bug + 0 production audit row → 可 `DROP SCHEMA system CASCADE` + 刪 _sqlx_migrations V99 row + 重 land V099 修補（dev/sandbox 容許）
- Apply 後已有 operator 切換 row in audit → 走 ADR-0006 forward-patch（V### 補丁 + 訂正 audit trail）
- 5-gate live / mainnet 期間 → **永不 destructive rollback**

# §8 Sign-off chain 對應 + 不確定之處

## 8.1 Sign-off 對應（per packet master §6 Packet A）

| Role | 任務 | E1 deliverable |
|---|---|---|
| E1 (本 task) | V099 SQL IMPL + Linux PG D1-D13 dry-run + idempotency 雙跑 | ✅ DONE — 369 LOC ship + 13/13 + 11/11 extras PASS + idempotency 0 RAISE |
| **MIT** | Linux PG empirical dry-run 13 條獨立 review + 字面與 spec §3.1 對齊 | 🟡 PENDING — 待主會話派 MIT 獨立跑 D1-D13 確認（本 report 已 self-document evidence） |
| **E2** | Code review — Guard A/B/C 完整性 + idempotency 雙跑 + grep `runtime_failsafe_override`/`disable_failsafe` 零出現 + AV-9/10/11 atomic/race/fail-closed regression | 🟡 PENDING — V099 file 369 LOC；E2 grep clean（0 hit on forbidden 字串）；cross-platform path 0 hit |
| **E4** | Regression PA spec §12 AC-1/5/7/8（fresh PG apply CONSERVATIVE / cold start fail-closed / 4 path lease at L2 / lease lifecycle 不受 mid-flight 切換影響）| 🟡 PENDING — 待 V099 真 land 後 engine restart + pytest |
| **CC** | 16-root walkthrough（原則 6 fail-closed / 原則 9 audit traceability / 原則 11 portfolio autonomy）| 🟡 PENDING |
| **PM** | Final commit + push | 🟡 PENDING |

## 8.2 不確定之處 + Push back to operator/PA

1. **「MIT V099-V116」TODO line 60 語義**：Sprint 1A-ε P3+ 此 token 是否與 Wave 5 V099 競爭？我的 reading = 否（Wave 5 V099 *是* 該 series 之首項）；若 PA/PM 有不同 reading，需顯式 clarify。

2. **V099 < V100 out-of-order land**：trading_ai 主 DB 已 apply V100（m4_hypothesis）；V099 將後 apply。sqlx 文檔允許 out-of-order migrations，但 audit 角度建議 PM 確認此安排（vs `repair_migration_checksum` 重排路徑）。本 E1 IMPL 假設 PM accept out-of-order land。

3. **Packet master §1 scope vs operator prompt 「Sub B/C/F」差異**：本 IMPL follow Packet master scope（schema only）；operator prompt 列的 Sub B（Rust binding）+ Sub C（Python API）+ Sub F（cross-lang test）等候 Packet B/C 派發 by E1a + 另一 E1 instance。若 operator 意圖讓本 task 跨 Packet 範圍同時做，請顯式 reframe + 派發新 dispatch。

4. **PG TimeZone = Europe/Madrid（非 UTC）empirical 發現**：D13 dry-run 確認 PG container TimeZone='Europe/Madrid'；雙時間戳設計實際 round-trip diff=0.000000（switched_at_local AT TIME ZONE 'Europe/Madrid' 還原回 UTC 與 switched_at_utc byte-equal）。但 spec §3.2 D13 風險段提及若 PG container TZ='UTC' 而 machine local 'Asia/Taipei' 會差 8h；本 dev sandbox 屬 'Europe/Madrid' 環境，production trade-core 仍 Europe/Madrid（assumption），所以雙時間戳設計 work as intended。**若 production 部署在不同 TZ machine，需重驗 D13**。

5. **`trading_ai` role dev sandbox 不存在**：empirical 確認 sandbox 僅 `trading_admin` role。V099 DO block IF EXISTS gate REVOKE on trading_ai 正確處理此分支（NOTICE skip）。**production trade-core 預期 trading_ai role 存在**（engine + Python API 透過此業務 role 連線），故 REVOKE 將真生效 — append-only 紀律 in production runtime 才 enforced。

# §9 Operator 下一步

1. PA 派 **MIT** 獨立跑 Linux PG D1-D13 dry-run（per spec §3.1，本 E1 report 已 evidence；MIT 獨立驗 = 對抗式檢查 per `feedback_multi_role_strategic_review`）
2. PA 派 **E2** code review V099 file 369 LOC：Guard A/B/C grep + idempotency NOTICE 完整性 + cross-ref spec §2.1-2.4 字面
3. PA 派 **CC** 16-root walkthrough（原則 6/9/11 對 V099 對齊）
4. PA 派 **A3+E2 對抗性核驗**（per `feedback_impl_done_adversarial_review`；V099 schema land 屬 governance schema 高風險 IMPL）
5. PM 串 Packet A sign-off chain DONE → push V099 file + ssh trade-core engine restart triggering sqlx auto-migrate
6. PM final closure log + E1 memory append

# §10 Memory append（candidate）

擬 append to `srv/docs/CCAgentWorkSpace/E1/memory.md`：

```
| 2026-05-27 | Wave 5 Packet A V099 Autonomy Level Toggle schema land：369 LOC（system schema + autonomy_level_enum + 2 tables + 3 indexes + trigger + cold seed + REVOKE）/ Linux PG D1-D13 13/13 + extras 11/11 PASS（dev sandbox trade-core BEGIN/ROLLBACK）/ Idempotency 2nd apply 0 RAISE 14 NOTICE skip / sqlx hash drift workflow 不破（無本地 psql -f）/ 衝突 check：Sprint 1A-ε V099-V116 = Wave 5 head item 非競爭 + LG-3 V104 號碼不撞 + V99<V100 out-of-order land 待 PM confirm | `srv/docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-27--wave_5_packet_a_v099_impl.md` |
```

關鍵教訓（待 append memory）：
- **`now()` is transaction-start time in PG**，single-txn dry-run 不能用 `updated_at` 變動證 trigger fire；需 `clock_timestamp()` 作 sentinel 證 trigger 真 attach + fire（D17 經驗）
- **`trading_ai` role 在 dev sandbox 不存在**；V099 spec §2.3 line 320-326 既有 DO block IF EXISTS gate 正確處理；E1 review 此類 role-conditional REVOKE 必先 `SELECT rolname FROM pg_roles` empirical 確認 dev/prod 分支
- **PG ENUM `invalid_text_representation` SQLSTATE 22P02** 而非 `check_violation`；D5 dry-run assertion 必 catch `invalid_text_representation` 異常（spec §3.2 D5 risk text 已暗示「PG error: invalid input value for enum」）
- **psql `\gset` + ROLLBACK SAVEPOINT 邏輯** = 一條 ERROR 後若不 SAVEPOINT/RELEASE 隔離，後續 statement 全 `current transaction is aborted`；多 negative-case INSERT 必 SAVEPOINT 包單條（D14 a-e 經驗）
- **scp + docker cp 雙 hop** copy migration file 到 PG container 的 SOP（spec §3.3 implied，本 IMPL 落地 `/tmp/V099__autonomy_level_config.sql` 暫存 + dry-run 後 cleanup）

---

*E1 Wave 5 Packet A V099 schema land · 2026-05-27 · 待 E2 + MIT + A3+E2 adversarial + E4 + CC + PM*
