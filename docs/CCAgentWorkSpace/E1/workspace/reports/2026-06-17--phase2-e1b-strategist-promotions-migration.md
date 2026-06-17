# E1-B Report — Phase 2 migration: learning.strategist_promotions (V144)

- 日期: 2026-06-17
- 角色: E1 (Backend Developer)
- Wave: E1-B（SQL migration，spec §2.7 + §2.10 E1-B）
- 設計 SSOT: `srv/docs/execution_plan/2026-06-17--intelligent-param-adjusting-agent-master-spec.md` §2.6/§2.7
- 狀態: IMPLEMENTATION DONE — 待 E2 審查
- **不 commit**（強制鏈 E1→E2→E4→PM）

## 任務摘要

為 Phase 2（demo→live human-gated strategist param promotion）建立 fail-closed
audit lineage 表 `learning.strategist_promotions`。本 wave 只負責 migration 檔 +
Linux PG empirical dry-run（double-apply 冪等驗）。不碰 Rust criteria gate（E1-A）、
不碰 Python route（E1-C）、不碰任何硬邊界。

## 修改清單

| 檔 | 動作 | 內容 |
|---|---|---|
| `srv/sql/migrations/V144__strategist_promotions.sql` | 新增 | 16-欄 audit 表 + Guard A + 2 index + COMMENT（純 additive，無改既有表） |

無其他檔改動（嚴守 wave 邊界，multi-session dirty tree 只碰本 wave 檔）。

## 遷移號決策（migration 號 = git 看不見的全局命名空間）

- **prod `_sqlx_migrations` max(version) = 139**（ssh trade-core 親查 `docker exec
  trading_postgres psql -U trading_admin -d trading_ai -c "SELECT max(version)..."`）。
  最高 5 個 applied: 139 agent_memory_store / 138 research_fdr_tables /
  137 lease_ipc_soak_events / 136 l2_provenance_columns / 135 l2_gate_seam_log（全 success=t）。
- **repo file chain 最高 = V143**（`V143__l1_book_event_recorder.sql`）。V140 缺號；
  V141/V142/V143 file 尚未 apply 到 prod（applied 卡在 139）。
- **next-free = max(applied 139, file-chain 143) + 1 = V144**（與 spec §2.7 建議一致）。
  sqlx 在 boot 時會依序補 apply V141→V142→V143→V144（forward-only）。
- PG 容器=`trading_postgres`、user=`trading_admin`、db=`trading_ai`（docker inspect 為準，
  密碼經 `~/.pgpass`，不硬編碼；env 檔在
  `~/BybitOpenClaw/secrets/environment_files/basic_system_services.env`）。

## 精確欄位清單（scratch DB `\d` 實證）

| pos | column | type | nullable | default |
|---|---|---|---|---|
| 1 | id | bigint | NO | nextval(...id_seq) (BIGSERIAL PK) |
| 2 | action | text | NO | — ('promote'/'demote') |
| 3 | strategy_name | text | NO | — |
| 4 | symbol | text | YES | — (audit scope hint) |
| 5 | source_engine | text | NO | — ('demo'/'paper') |
| 6 | target_engine | text | NO | 'live' |
| 7 | pre_promotion_params_json | jsonb | NO | — (完整 live set,促升前/demote 還原目標) |
| 8 | promoted_params_json | jsonb | NO | — (完整促升後 set,demote precondition 基準) |
| 9 | criteria_verdict | text | NO | — (Eligible/Pending:r/Reject:r/demote_exempt) |
| 10 | criteria_input_json | jsonb | YES | — (EDGE-ANCHORED per-cell+coverage 快照,root#8) |
| 11 | actor_id | text | NO | — |
| 12 | gate_passed | boolean | NO | — (5-gate 結果) |
| 13 | applied_at | timestamptz | NO | now() |
| 14 | applied_at_ms | bigint | NO | — (client ts_ms ordering) |
| 15 | reverts_promotion_id | bigint | YES | — (demote 指回 promote id,FK-soft) |
| 16 | reason | text | YES | — |

**Indexes**: `strategist_promotions_pkey` (id) +
`idx_strategist_promotions_strategy_target_ts` (strategy_name, target_engine,
applied_at_ms DESC) + `idx_strategist_promotions_action_ts` (action,
applied_at_ms DESC)。非 hypertable。COMMENT 已落。

16 欄與 spec §2.6/§2.7 逐欄對齊（含 JSONB NOT NULL on pre/promoted params、
nullable criteria_input_json、target_engine DEFAULT 'live'、applied_at DEFAULT NOW()）。

## Linux PG empirical dry-run（MANDATORY，scratch DB 非 prod）

scratch DB `v144_scratch_<ts>`（`TEMPLATE template0` — 見下方環境陷阱），跑：
- **APPLY #1**: RC=0 — CREATE SCHEMA / CREATE TABLE / CREATE INDEX×2 / COMMENT 全成功。
- **APPLY #2 (double-apply)**: RC=0 — 全部 `NOTICE: ... already exists, skipping`
  （schema/relation/idx×2）+ COMMENT；**乾淨冪等 no-op，無錯**（Guard A / IF NOT EXISTS 生效）。
- **結構驗證**: `\d` + information_schema.columns 16 欄型別/NOT NULL/default 全對；
  PK on id；2 index DESC 排序正確；COMMENT 落；非 hypertable。
- **smoke INSERT**: promote row（id=1, JSONB params + criteria_input_json）+ demote row
  （id=2, reverts_promotion_id=1）皆成功；`(strategy,target_engine,applied_at_ms DESC)`
  index 查詢回正確時序（demote 在前）。
- **NOT NULL 強制**: 故意 omit `pre_promotion_params_json` → 正確 `ERROR: null value ...
  violates not-null constraint`（fail-closed 約束生效）。
- **cleanup**: scratch DB 已 `DROP DATABASE`（RC=0）；遠端 tmp + 容器內 SQL 全清；
  `SELECT count(*) ... WHERE datname LIKE 'v144_scratch%' OR 'v144_debug%'` = **0** leftover。
- **prod 未動**（不手 psql 打 prod，避 checksum 漂移；prod apply 走 sqlx auto-migrate
  at engine boot 或 operator-gated migrate）。

## 治理對照

- **硬邊界**: 0 觸碰 max_retries / live_execution_allowed / execution_authority /
  system_mode。本 migration 純 additive（新表），與硬邊界無交集。
- **Guard A/B/C**: Guard A 全用（CREATE SCHEMA/TABLE/INDEX IF NOT EXISTS）。無 type-sensitive
  ADD COLUMN → 不需 Guard B。index 即 Guard C 等價（hot-path 查詢索引 IF NOT EXISTS）。
- **冪等性**: double-apply 實證乾淨 no-op（CLAUDE Data 章要求）。
- **跨平台**: migration 檔無硬編碼 `/home/ncyu`/`/Users/...`/機器路徑（SQL DDL 無路徑）。
- **singleton 登記**: 不適用（DB 表非 mutable singleton）。
- **註釋規範**: 檔頭 MODULE-NOTE 級註釋全中文（英文僅保留 SQL schema 名 / sqlx /
  root #8 等技術識別符），符 bilingual-comment-style Chinese-first。
- **root #8**: criteria_input_json 完整保留促升當下 EDGE-ANCHORED 證據（per-cell edge +
  coverage），永久保留（非 hypertable，無 retention）→ 可重建促升量化依據。

## 不確定之處 / 偏差

1. **`TEMPLATE template0` 偏差（最小安全解）**: prod PG 的 `template1` 有 collation
   version 不符（host 環境條件：`ERROR: template database "template1" has a collation
   version, but no actual collation version could be determined`），直接 CREATE DATABASE
   失敗。**這是 host PG 環境問題，非我 migration 的問題**（migration DDL 本身與 collation
   無關）。我用 `CREATE DATABASE ... TEMPLATE template0` 繞過（template0 無 collation 標記），
   不 mutate template1（不碰 prod 環境狀態）。E4 在真 prod boot 時走 sqlx auto-migrate，
   不經 CREATE DATABASE 路徑（直接 apply 到既有 trading_ai），故此繞道不影響 prod apply。
   **但建議 operator/E3 留意 prod PG template1 collation 漂移**（可能影響未來任何 CREATE
   DATABASE，與本 task 無關的潛在運維議題）。
2. **denied-path row（spec §2.6 留 E1 裁量）**: 表 schema 已能容納 denied row（gate_passed
   BOOLEAN + criteria_verdict TEXT 可存 Reject/Pending），denied row 是否同步寫由 E1-C
   route 邏輯決定（spec 留 E1 裁量，QA 驗）。本 migration 不約束此決策。

## Operator / 下一步

1. **E2 審查**: 對照 spec §2.7 schema、Guard A 完整性、index 設計、冪等性。
2. **E1-C 依賴**: 表名 `learning.strategist_promotions` + 16 欄 schema 已釘死，E1-C route
   INSERT 可依此契約寫。E1-A 的 criteria_input_json 形狀（per-cell + coverage）對應欄 10。
3. **E4 Linux 真 integration**: 真 Live engine boot 走 sqlx auto-migrate apply V141→V144；
   親查 `learning.strategist_promotions` 真落 row（promote/criteria-reject/5-gate-fail/
   demote/precondition-fail 五場景，spec §2.6 QA MANDATORY，P8 風險）。
4. **prod apply**: operator-gated（engine boot sqlx auto-migrate 或 migrate 命令），不手打 prod。
